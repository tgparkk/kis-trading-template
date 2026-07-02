#!/usr/bin/env python3
"""
사와카미 전략 과거 데이터 시뮬레이션 하네스
============================================

실제 strategy.py + screener.py 코드를 import하여,
KIS API 대신 PostgreSQL 과거 데이터를 주입하는 mock으로 시뮬레이션.

Usage:
    python scripts/sawkami_simulation.py --start 2022-01-01 --end 2026-02-10 --capital 100000000
"""

import argparse
import logging
import math
import sys
import time
import os
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import pandas as pd
import numpy as np

# ── project root on sys.path ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
import psycopg2.extras

# ============================================================================
# DB connection
# ============================================================================
DB_PARAMS = dict(host="172.23.208.1", port=5433, user="postgres", dbname="strategy_analysis")


def get_db_conn():
    return psycopg2.connect(**DB_PARAMS)


# ============================================================================
# Logging
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sawkami_sim")


# ============================================================================
# HistoricalDataProvider
# ============================================================================
class HistoricalDataProvider:
    """KIS API를 대체하는 과거 데이터 제공자 — DB에서 bulk load."""

    def __init__(self, conn):
        self.conn = conn
        self.current_date: date = date.today()
        # {stock_code: DataFrame} — 전 기간 캔들 (lazy load per stock)
        self._candle_cache: Dict[str, pd.DataFrame] = {}
        # {stock_code: stock_name}
        self._name_map: Dict[str, str] = {}
        # All stock list [{code, name, market}]
        self._stock_list: List[Dict] = []
        # Trading dates sorted
        self._trading_dates: List[date] = []
        # yearly_fundamentals cache {(code, year): row}
        self._yf_cache: Dict[Tuple[str, int], Dict] = {}
        # financial_data cache {(code, year, account): amount}
        self._fd_cache: Dict[Tuple[str, int, str], int] = {}

    def load_all(self, start_date: date, end_date: date):
        """Bulk load everything needed."""
        logger.info("Loading historical data from DB...")
        t0 = time.time()

        cur = self.conn.cursor()

        # 1) Trading dates
        cur.execute(
            "SELECT DISTINCT trade_date FROM daily_candles "
            "WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date",
            (start_date, end_date),
        )
        self._trading_dates = [r[0] for r in cur.fetchall()]
        logger.info(f"  Trading dates: {len(self._trading_dates)} days")

        # 2) Stock list (distinct from daily_candles in range)
        cur.execute(
            "SELECT DISTINCT stock_code, stock_name, market FROM daily_candles "
            "WHERE trade_date BETWEEN %s AND %s",
            (start_date, end_date),
        )
        for code, name, market in cur.fetchall():
            self._name_map[code] = name
            self._stock_list.append({"code": code, "name": name, "market": market or "KOSPI"})
        logger.info(f"  Stocks: {len(self._stock_list)}")

        # 3) Load ALL candles into memory (bulk — ~2M rows, ~500MB pandas)
        # We load from 1 year before start_date to have lookback for 252-day high
        lookback_start = start_date - timedelta(days=400)
        cur.execute(
            "SELECT stock_code, trade_date, open_price, high_price, low_price, close_price, volume "
            "FROM daily_candles WHERE trade_date >= %s AND trade_date <= %s "
            "ORDER BY stock_code, trade_date",
            (lookback_start, end_date),
        )
        rows = cur.fetchall()
        logger.info(f"  Candle rows loaded: {len(rows):,}")

        # Build per-stock DataFrames
        from collections import defaultdict
        stock_rows = defaultdict(list)
        for code, td, o, h, l, c, v in rows:
            stock_rows[code].append((td, o, h, l, c, v))

        for code, data in stock_rows.items():
            df = pd.DataFrame(data, columns=["trade_date", "open", "high", "low", "close", "volume"])
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df = df.sort_values("trade_date").reset_index(drop=True)
            # Convert to float
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            self._candle_cache[code] = df

        # 4) yearly_fundamentals
        cur.execute("SELECT stock_code, year, pbr, roe, per, revenue_growth, op_margin, debt_ratio, market_cap_won FROM yearly_fundamentals")
        for row in cur.fetchall():
            code, year = row[0], row[1]
            self._yf_cache[(code, year)] = {
                "pbr": row[2], "roe": row[3], "per": row[4],
                "revenue_growth": row[5], "op_margin": row[6],
                "debt_ratio": row[7], "market_cap_won": row[8],
            }
        logger.info(f"  Yearly fundamentals: {len(self._yf_cache)} records")

        # 5) financial_data (영업이익 등)
        cur.execute("SELECT stock_code, year, account_name, amount FROM financial_data")
        for code, year, acct, amt in cur.fetchall():
            self._fd_cache[(code, year, acct)] = amt
        logger.info(f"  Financial data: {len(self._fd_cache)} records")

        logger.info(f"  Data load complete in {time.time()-t0:.1f}s")

    def get_trading_dates(self) -> List[date]:
        return self._trading_dates

    def get_stock_list(self) -> List[Dict]:
        return self._stock_list

    def get_stock_name(self, code: str) -> str:
        return self._name_map.get(code, code)

    def get_daily_ohlcv(self, stock_code: str, days: int = 252) -> Optional[pd.DataFrame]:
        """현재 시뮬레이션 날짜 기준으로 과거 days일 OHLCV 반환."""
        df = self._candle_cache.get(stock_code)
        if df is None or df.empty:
            return None
        mask = df["trade_date"] <= pd.Timestamp(self.current_date)
        subset = df.loc[mask].tail(days).copy()
        if subset.empty:
            return None
        return subset.reset_index(drop=True)

    def get_current_price(self, stock_code: str) -> Optional[float]:
        """현재 날짜의 종가 반환."""
        df = self._candle_cache.get(stock_code)
        if df is None:
            return None
        row = df.loc[df["trade_date"] == pd.Timestamp(self.current_date)]
        if row.empty:
            return None
        return float(row.iloc[0]["close"])

    def get_open_price(self, stock_code: str, target_date: date) -> Optional[float]:
        """특정 날짜의 시가 반환 (익일 시가 체결용)."""
        df = self._candle_cache.get(stock_code)
        if df is None:
            return None
        row = df.loc[df["trade_date"] == pd.Timestamp(target_date)]
        if row.empty:
            return None
        return float(row.iloc[0]["open"])

    def get_op_income_growth(self, stock_code: str) -> Optional[float]:
        """현재 시뮬레이션 날짜 기준 영업이익 YoY 성장률 (%)."""
        # Use the most recent available year <= current_date's year - 1
        # (annual data is available after fiscal year end)
        ref_year = self.current_date.year - 1
        for y in [ref_year, ref_year - 1]:
            cur_op = self._fd_cache.get((stock_code, y, "영업이익"))
            prev_op = self._fd_cache.get((stock_code, y - 1, "영업이익"))
            if cur_op is not None and prev_op is not None and prev_op != 0:
                return (cur_op - prev_op) / abs(prev_op) * 100
        return None

    def get_bps(self, stock_code: str) -> Optional[float]:
        """BPS 추정: 자본총계 / (시가총액/현재가) — 주당 순자산."""
        ref_year = self.current_date.year - 1
        for y in [ref_year, ref_year - 1]:
            equity = self._fd_cache.get((stock_code, y, "자본총계"))
            if equity and equity > 0:
                # 발행주식수 추정: market_cap / close_price
                yf = self._yf_cache.get((stock_code, y))
                if yf and yf.get("market_cap_won") and yf["market_cap_won"] > 0:
                    # 최근 종가로 주식수 역산
                    price = self.get_current_price(stock_code)
                    if price and price > 0:
                        shares = yf["market_cap_won"] / price
                        if shares > 0:
                            return equity / shares
                # Fallback: PBR에서 역산
                if yf and yf.get("pbr") and yf["pbr"] > 0:
                    price = self.get_current_price(stock_code)
                    if price and price > 0:
                        return price / yf["pbr"]
        return None

    def get_pbr(self, stock_code: str) -> Optional[float]:
        """DB의 PBR 직접 반환."""
        ref_year = self.current_date.year - 1
        for y in [ref_year, ref_year - 1]:
            yf = self._yf_cache.get((stock_code, y))
            if yf and yf.get("pbr") is not None:
                return yf["pbr"]
        return None


# ============================================================================
# HistoricalBroker
# ============================================================================
@dataclass
class Position:
    stock_code: str
    stock_name: str
    quantity: int
    avg_price: float
    entry_date: date


class HistoricalBroker:
    """가상 브로커 — 잔고, 포지션, 주문 처리."""

    SLIPPAGE = 0.003   # 0.3%
    COMMISSION = 0.00015  # 0.015%

    def __init__(self, initial_capital: float = 100_000_000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trade_log: List[Dict] = []
        self.equity_curve: List[Tuple[date, float]] = []

    @property
    def num_positions(self) -> int:
        return len(self.positions)

    def get_position_value(self, data_provider: HistoricalDataProvider) -> float:
        total = 0.0
        for code, pos in self.positions.items():
            price = data_provider.get_current_price(code)
            if price:
                total += price * pos.quantity
        return total

    def get_total_equity(self, data_provider: HistoricalDataProvider) -> float:
        return self.cash + self.get_position_value(data_provider)

    def execute_buy(self, stock_code: str, stock_name: str, price: float,
                    amount: float, exec_date: date) -> Optional[Dict]:
        """시장가 매수 (슬리피지 적용). amount=투자금액."""
        fill_price = price * (1 + self.SLIPPAGE)
        quantity = int(amount / fill_price)
        if quantity <= 0:
            return None
        cost = fill_price * quantity
        commission = cost * self.COMMISSION
        total_cost = cost + commission
        if total_cost > self.cash:
            # 자금 부족 시 수량 줄임
            quantity = int((self.cash - 100) / (fill_price * (1 + self.COMMISSION)))
            if quantity <= 0:
                return None
            cost = fill_price * quantity
            commission = cost * self.COMMISSION
            total_cost = cost + commission

        self.cash -= total_cost
        self.positions[stock_code] = Position(
            stock_code=stock_code, stock_name=stock_name,
            quantity=quantity, avg_price=fill_price, entry_date=exec_date,
        )
        trade = {
            "type": "BUY", "stock_code": stock_code, "stock_name": stock_name,
            "date": exec_date, "price": fill_price, "quantity": quantity,
            "amount": cost, "commission": commission,
        }
        self.trade_log.append(trade)
        return trade

    def execute_sell(self, stock_code: str, price: float, exec_date: date) -> Optional[Dict]:
        """시장가 매도 (슬리피지 적용). 전량 매도."""
        pos = self.positions.get(stock_code)
        if not pos:
            return None
        fill_price = price * (1 - self.SLIPPAGE)
        proceeds = fill_price * pos.quantity
        commission = proceeds * self.COMMISSION
        net_proceeds = proceeds - commission

        pnl = net_proceeds - (pos.avg_price * pos.quantity)
        pnl_pct = (fill_price - pos.avg_price) / pos.avg_price * 100

        self.cash += net_proceeds
        trade = {
            "type": "SELL", "stock_code": stock_code, "stock_name": pos.stock_name,
            "date": exec_date, "price": fill_price, "quantity": pos.quantity,
            "amount": proceeds, "commission": commission,
            "pnl": pnl, "pnl_pct": pnl_pct,
            "entry_price": pos.avg_price, "entry_date": pos.entry_date,
            "hold_days": (exec_date - pos.entry_date).days,
        }
        self.trade_log.append(trade)
        del self.positions[stock_code]
        return trade


# ============================================================================
# SimulationEngine
# ============================================================================
class SimulationEngine:
    """시뮬레이션 엔진 — 날짜별 순회."""

    def __init__(self, data_provider: HistoricalDataProvider, broker: HistoricalBroker,
                 start_date: date, end_date: date, max_positions: int = 10):
        self.dp = data_provider
        self.broker = broker
        self.start_date = start_date
        self.end_date = end_date
        self.max_positions = max_positions

        # Strategy config
        self._load_strategy_config()

        # Pre-compute fundamental candidates per year to avoid scanning 2000+ stocks daily
        self._yearly_fund_candidates: Dict[int, List[str]] = {}

    def _load_strategy_config(self):
        """Load params from config.yaml."""
        import yaml
        config_path = PROJECT_ROOT / "strategies" / "sawkami" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        params = self.config.get("parameters", {})
        self.op_growth_min = params.get("op_income_growth_min", 30.0)
        self.pbr_max = params.get("pbr_max", 1.5)
        self.high52w_drop_pct = params.get("high52w_drop_pct", -20.0)
        self.rsi_period = params.get("rsi_period", 14)
        self.rsi_oversold = params.get("rsi_oversold", 30)
        self.vol_ratio_min = params.get("volume_ratio_min", 1.5)
        self.vol_ma_period = params.get("volume_ma_period", 20)
        self.high52w_period = params.get("high52w_period", 252)

        risk = self.config.get("risk_management", {})
        self.take_profit_pct = risk.get("take_profit_pct", 0.15)
        self.stop_loss_pct = risk.get("stop_loss_pct", 0.15)
        self.max_hold_days = risk.get("max_hold_days", 40)
        self.max_per_stock = risk.get("max_per_stock_amount", 5_000_000)

    def _precompute_fundamental_candidates(self):
        """재무 필터를 연도별로 미리 계산 — 영업이익 YoY 30%↑ 종목."""
        logger.info("Pre-computing fundamental candidates per year...")
        stocks = self.dp.get_stock_list()
        stock_codes = set(s["code"] for s in stocks
                         if s.get("market") in ("KOSPI", "KOSDAQ")
                         and not s["code"].endswith("5"))

        for year in range(self.start_date.year - 1, self.end_date.year + 1):
            candidates = []
            for code in stock_codes:
                cur_op = self.dp._fd_cache.get((code, year, "영업이익"))
                prev_op = self.dp._fd_cache.get((code, year - 1, "영업이익"))
                if cur_op is not None and prev_op is not None and prev_op > 0:
                    growth = (cur_op - prev_op) / abs(prev_op) * 100
                    if growth >= self.op_growth_min:
                        candidates.append(code)
            self._yearly_fund_candidates[year] = candidates
            logger.info(f"  Year {year}: {len(candidates)} stocks pass op_income filter")

    def _get_fund_candidates_for_date(self, sim_date: date) -> List[str]:
        """현재 날짜 기준 사용 가능한 재무 후보."""
        # Use year-1 data (annual reports available after fiscal year)
        ref_year = sim_date.year - 1
        return self._yearly_fund_candidates.get(ref_year, [])

    def run(self):
        """메인 시뮬레이션 루프."""
        self._precompute_fundamental_candidates()

        trading_dates = [d for d in self.dp.get_trading_dates()
                        if self.start_date <= d <= self.end_date]
        if not trading_dates:
            logger.error("No trading dates in range")
            return

        logger.info(f"Simulation: {trading_dates[0]} ~ {trading_dates[-1]} ({len(trading_dates)} days)")
        logger.info(f"Initial capital: {self.broker.initial_capital:,.0f}")

        from utils.indicators import calculate_rsi

        pending_buys: List[Tuple[str, str, float]] = []  # (code, name, amount)
        pending_sells: List[str] = []  # codes to sell

        for i, sim_date in enumerate(trading_dates):
            self.dp.current_date = sim_date

            # ── Execute pending orders from previous day (at today's open) ──
            if pending_buys:
                for code, name, amount in pending_buys:
                    if code in self.broker.positions:
                        continue
                    if self.broker.num_positions >= self.max_positions:
                        break
                    open_price = self.dp.get_open_price(code, sim_date)
                    if open_price and open_price > 0:
                        result = self.broker.execute_buy(code, name, open_price, amount, sim_date)
                        if result:
                            logger.debug(f"  BUY {code}({name}) @ {result['price']:,.0f} x {result['quantity']}")
                pending_buys.clear()

            if pending_sells:
                for code in pending_sells:
                    open_price = self.dp.get_open_price(code, sim_date)
                    if open_price and open_price > 0:
                        result = self.broker.execute_sell(code, open_price, sim_date)
                        if result:
                            logger.debug(f"  SELL {code} @ {result['price']:,.0f} PNL={result['pnl_pct']:+.1f}%")
                pending_sells.clear()

            # ── Check SELL signals for held positions ──
            for code in list(self.broker.positions.keys()):
                pos = self.broker.positions[code]
                current_price = self.dp.get_current_price(code)
                if not current_price:
                    continue
                pnl_pct = (current_price - pos.avg_price) / pos.avg_price
                hold_days = (sim_date - pos.entry_date).days

                should_sell = False
                if pnl_pct >= self.take_profit_pct:
                    should_sell = True
                elif pnl_pct <= -self.stop_loss_pct:
                    should_sell = True
                elif hold_days >= self.max_hold_days:
                    should_sell = True

                if should_sell:
                    pending_sells.append(code)

            # ── Check BUY signals (only if slots available) ──
            if self.broker.num_positions < self.max_positions and not pending_sells:
                fund_candidates = self._get_fund_candidates_for_date(sim_date)
                if fund_candidates:
                    # Per-stock allocation
                    equity = self.broker.get_total_equity(self.dp)
                    per_stock_amount = min(
                        self.max_per_stock,
                        equity / self.max_positions,
                    )

                    buy_signals = []
                    for code in fund_candidates:
                        if code in self.broker.positions:
                            continue
                        if len(buy_signals) + self.broker.num_positions >= self.max_positions:
                            break

                        ohlcv = self.dp.get_daily_ohlcv(code, self.high52w_period + 30)
                        if ohlcv is None or len(ohlcv) < max(self.high52w_period, self.vol_ma_period, self.rsi_period) + 2:
                            continue

                        current_price = float(ohlcv["close"].iloc[-1])
                        if current_price <= 0:
                            continue

                        # Filter 1: PBR (from DB)
                        bps = self.dp.get_bps(code)
                        if not bps or bps <= 0:
                            continue
                        pbr = current_price / bps
                        if pbr >= self.pbr_max:
                            continue

                        # Filter 2: 52-week high drop
                        high_52w = float(ohlcv["high"].iloc[-self.high52w_period:].max())
                        if high_52w <= 0:
                            continue
                        drop_pct = (current_price - high_52w) / high_52w * 100
                        if drop_pct > self.high52w_drop_pct:
                            continue

                        # Filter 3: Volume ratio
                        volumes = ohlcv["volume"]
                        vol_ma = float(volumes.iloc[-self.vol_ma_period:].mean())
                        if vol_ma <= 0:
                            continue
                        current_vol = float(volumes.iloc[-1])
                        vol_ratio = current_vol / vol_ma
                        if vol_ratio < self.vol_ratio_min:
                            continue

                        # Filter 4: RSI
                        rsi_series = calculate_rsi(ohlcv["close"], self.rsi_period)
                        rsi_val = float(rsi_series.iloc[-1])
                        if pd.isna(rsi_val) or rsi_val >= self.rsi_oversold:
                            continue

                        # All conditions met — compute score
                        op_growth = self.dp.get_op_income_growth(code) or 30.0
                        score = self._score(op_growth, drop_pct, rsi_val, pbr, vol_ratio)
                        name = self.dp.get_stock_name(code)
                        buy_signals.append((code, name, score, per_stock_amount))

                    # Sort by score, take top
                    buy_signals.sort(key=lambda x: x[2], reverse=True)
                    slots = self.max_positions - self.broker.num_positions
                    for code, name, score, amount in buy_signals[:slots]:
                        pending_buys.append((code, name, amount))
                        logger.debug(f"  Signal BUY: {code}({name}) score={score:.1f}")

            # ── Record equity ──
            equity = self.broker.get_total_equity(self.dp)
            self.broker.equity_curve.append((sim_date, equity))

            # ── Progress ──
            if (i + 1) % 50 == 0 or i == len(trading_dates) - 1:
                ret = (equity / self.broker.initial_capital - 1) * 100
                logger.info(
                    f"[{sim_date}] Day {i+1}/{len(trading_dates)} | "
                    f"Equity: {equity:,.0f} ({ret:+.1f}%) | "
                    f"Positions: {self.broker.num_positions} | "
                    f"Cash: {self.broker.cash:,.0f}"
                )

        # Final equity
        final_equity = self.broker.get_total_equity(self.dp)
        logger.info(f"\nSimulation complete. Final equity: {final_equity:,.0f}")

    def _score(self, op_growth, drop_pct, rsi, pbr, vol_ratio):
        s = 0.0
        s += min(25.0, max(0.0, (op_growth - 30) / 170 * 25))
        s += min(25.0, max(0.0, (abs(drop_pct) - 20) / 40 * 25))
        s += min(20.0, max(0.0, (30 - rsi) / 30 * 20))
        s += min(15.0, max(0.0, (1.5 - pbr) / 1.5 * 15))
        s += min(15.0, max(0.0, (vol_ratio - 1.5) / 3.5 * 15))
        return s

    def save_results_to_db(self):
        """시뮬레이션 결과를 sawkami_trades에 저장."""
        conn = get_db_conn()
        conn.autocommit = True
        cur = conn.cursor()

        # Clear old sim data
        cur.execute("DELETE FROM sawkami_trades WHERE buy_reason LIKE '[SIM]%'")
        logger.info("Cleared old simulation trades from DB")

        count = 0
        sells = [t for t in self.broker.trade_log if t["type"] == "SELL"]
        for t in sells:
            buy_amount = t["entry_price"] * t["quantity"]
            sell_amount = t["price"] * t["quantity"]
            cur.execute("""
                INSERT INTO sawkami_trades
                    (stock_code, stock_name, status, buy_date, buy_price,
                     buy_quantity, buy_amount, buy_reason,
                     sell_date, sell_price, sell_amount, sell_reason,
                     pnl_amount, pnl_pct, hold_days)
                VALUES (%s, %s, 'CLOSED', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                t["stock_code"], t["stock_name"],
                t["entry_date"], t["entry_price"], t["quantity"], buy_amount,
                f"[SIM] sawkami",
                t["date"], t["price"], sell_amount,
                "TP" if t["pnl_pct"] >= self.take_profit_pct * 100 else
                "SL" if t["pnl_pct"] <= -self.stop_loss_pct * 100 else "TIMEOUT",
                t["pnl"], t["pnl_pct"], t["hold_days"],
            ))
            count += 1

        # Still-open positions
        for code, pos in self.broker.positions.items():
            buy_amount = pos.avg_price * pos.quantity
            cur.execute("""
                INSERT INTO sawkami_trades
                    (stock_code, stock_name, status, buy_date, buy_price,
                     buy_quantity, buy_amount, buy_reason)
                VALUES (%s, %s, 'HOLDING', %s, %s, %s, %s, %s)
            """, (
                code, pos.stock_name,
                pos.entry_date, pos.avg_price, pos.quantity, buy_amount,
                f"[SIM] sawkami",
            ))
            count += 1

        logger.info(f"Saved {count} trades to DB (sawkami_trades)")
        conn.close()

    def print_report(self):
        """결과 리포트 출력."""
        curve = self.broker.equity_curve
        if not curve:
            logger.warning("No equity curve data")
            return

        initial = self.broker.initial_capital
        final = curve[-1][1]
        total_return = (final / initial - 1) * 100

        # CAGR
        days = (curve[-1][0] - curve[0][0]).days
        years = days / 365.25
        cagr = ((final / initial) ** (1 / years) - 1) * 100 if years > 0 else 0

        # MDD
        peak = initial
        max_dd = 0
        for _, eq in curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Sharpe (annualized, using daily returns)
        equities = [e for _, e in curve]
        daily_returns = pd.Series(equities).pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        else:
            sharpe = 0

        # Win rate
        sells = [t for t in self.broker.trade_log if t["type"] == "SELL"]
        wins = [t for t in sells if t["pnl_pct"] > 0]
        win_rate = len(wins) / len(sells) * 100 if sells else 0
        avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0
        losses = [t for t in sells if t["pnl_pct"] <= 0]
        avg_loss = np.mean([t["pnl_pct"] for t in losses]) if losses else 0

        print("\n" + "=" * 70)
        print("🏯 사와카미 전략 시뮬레이션 결과")
        print("=" * 70)
        print(f"기간: {curve[0][0]} ~ {curve[-1][0]} ({days}일, {len(curve)}거래일)")
        print(f"초기 자금: {initial:>20,.0f}원")
        print(f"최종 자산: {final:>20,.0f}원")
        print(f"총 수익률: {total_return:>18.2f}%")
        print(f"CAGR:      {cagr:>18.2f}%")
        print(f"MDD:       {max_dd:>18.2f}%")
        print(f"Sharpe:    {sharpe:>18.2f}")
        print(f"총 거래:   {len(sells):>18d}건 (매도 기준)")
        print(f"승률:      {win_rate:>18.1f}%")
        print(f"평균 수익: {avg_win:>18.1f}% (승)")
        print(f"평균 손실: {avg_loss:>18.1f}% (패)")
        if self.broker.positions:
            print(f"미청산:    {len(self.broker.positions):>18d}종목")

        # 연도별 성과
        print("\n📅 연도별 성과:")
        print("-" * 50)
        yearly = defaultdict(list)
        for d, eq in curve:
            yearly[d.year].append((d, eq))

        prev_eq = initial
        for year in sorted(yearly.keys()):
            year_data = yearly[year]
            year_end_eq = year_data[-1][1]
            year_ret = (year_end_eq / prev_eq - 1) * 100
            # Year MDD
            yr_peak = prev_eq
            yr_mdd = 0
            for _, eq in year_data:
                if eq > yr_peak:
                    yr_peak = eq
                dd = (yr_peak - eq) / yr_peak * 100
                if dd > yr_mdd:
                    yr_mdd = dd
            yr_trades = len([t for t in sells if t["date"].year == year])
            print(f"  {year}: {year_ret:+8.2f}%  MDD: {yr_mdd:5.1f}%  거래: {yr_trades}건")
            prev_eq = year_end_eq

        # Top/worst trades
        if sells:
            print("\n🏆 Best trades:")
            for t in sorted(sells, key=lambda x: x["pnl_pct"], reverse=True)[:5]:
                print(f"  {t['stock_name']}({t['stock_code']}) {t['entry_date']}→{t['date']} "
                      f"PNL: {t['pnl_pct']:+.1f}% ({t['hold_days']}일)")
            print("\n💀 Worst trades:")
            for t in sorted(sells, key=lambda x: x["pnl_pct"])[:5]:
                print(f"  {t['stock_name']}({t['stock_code']}) {t['entry_date']}→{t['date']} "
                      f"PNL: {t['pnl_pct']:+.1f}% ({t['hold_days']}일)")

        print("=" * 70)


# ============================================================================
# Main
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="사와카미 전략 시뮬레이션")
    parser.add_argument("--start", default="2022-01-01", help="시작일 (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-02-10", help="종료일 (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=100_000_000, help="초기 자금")
    parser.add_argument("--max-positions", type=int, default=10, help="최대 보유 종목")
    parser.add_argument("--no-db-save", action="store_true", help="DB 저장 안함")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    # Data provider
    conn = get_db_conn()
    dp = HistoricalDataProvider(conn)
    dp.load_all(start_date, end_date)

    # Broker
    broker = HistoricalBroker(initial_capital=args.capital)

    # Engine
    engine = SimulationEngine(dp, broker, start_date, end_date, args.max_positions)
    engine.run()

    # Report
    engine.print_report()

    # Save to DB
    if not args.no_db_save:
        engine.save_results_to_db()

    conn.close()


if __name__ == "__main__":
    main()
