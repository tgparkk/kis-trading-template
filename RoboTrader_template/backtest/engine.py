"""
Backtest Engine
===============

일봉 DataFrame을 받아 전략의 generate_signal()을 재사용하는 백테스트 엔진.
DB 의존성 없이 동작하며, 수수료/세금을 반영한 매매 시뮬레이션을 수행합니다.

Usage:
    from backtest import BacktestEngine
    from strategies.sample.strategy import SampleStrategy

    engine = BacktestEngine(SampleStrategy(), initial_capital=10_000_000)
    result = engine.run(stock_codes=["005930", "000660"], daily_data=data)
    print(f"수익률: {result.total_return:.2%}, 승률: {result.win_rate:.2%}")

daily_data 형식:
    {
        "005930": pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"]),
        "000660": pd.DataFrame(...),
    }
    - "date" 컬럼은 str("YYYY-MM-DD") 또는 datetime 모두 허용
    - DataFrame은 날짜 오름차순 정렬 가정
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as DateType
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE, TRAILING_STOP_CALLBACK_RATE
from strategies.base import BaseStrategy, SignalType

# CandidateRepository는 make_screener_snapshot_provider 헬퍼에서 사용.
# DB 의존성이 없는 환경(순수 백테스트)에서는 import만 해두고 실제 호출은 provider 내부에서 발생.
try:
    from db.repositories.candidate import CandidateRepository as CandidateRepository
except ImportError:  # DB 패키지 없는 경량 환경
    CandidateRepository = None  # type: ignore[assignment,misc]


# KS11 일봉 시장환경 필터용 상수 (daily_candles.stock_code 값, 옵션 C 2026-05-19)
KOSPI_CODE = "KS11"


# ============================================================================
# 결과 데이터클래스
# ============================================================================

@dataclass
class BacktestResult:
    """백테스트 결과 요약.

    Attributes:
        total_return: 총 수익률 (예: 0.12 = +12%)
        win_rate: 승률 (수익 거래 / 전체 거래)
        avg_profit: 평균 수익률 (거래당)
        max_drawdown: 최대 낙폭 (MDD, 양수: 예 0.15 = -15%)
        sharpe_ratio: 샤프 비율 (무위험 수익률 0% 기준)
        calmar_ratio: 칼마 비율 (연환산 수익률 / MDD). MDD=0이면 0.
        sortino_ratio: 소르티노 비율 (하방 편차 기반, 무위험률 0% 가정).
        profit_loss_ratio: 손익비 (평균 수익 / 평균 손실)
        total_trades: 완료된 왕복 거래 수 (매수→매도 쌍)
        trades: 개별 거래 기록 리스트
        equity_curve: 일별 자산 변화 곡선 (초기 자본 기준)
    """
    total_return: float
    win_rate: float
    avg_profit: float
    max_drawdown: float
    sharpe_ratio: float
    calmar_ratio: float
    sortino_ratio: float
    profit_loss_ratio: float
    total_trades: int
    trades: List[Dict]
    equity_curve: List[float]
    sells_by_reason: Dict[str, int] = field(default_factory=dict)
    candidate_pool_hits: int = 0  # 후보 풀이 적용된 일자 수 (candidate_provider 사용 시)

    def summary(self) -> str:
        """결과 요약 문자열 반환."""
        reason_str = ""
        if self.sells_by_reason:
            parts = [f"{k}={v}" for k, v in sorted(self.sells_by_reason.items())]
            reason_str = f"  매도사유=({','.join(parts)})"
        pool_str = f"  후보풀적용={self.candidate_pool_hits}일" if self.candidate_pool_hits > 0 else ""
        return (
            f"총수익률={self.total_return:+.2%}  "
            f"승률={self.win_rate:.1%}  "
            f"평균수익={self.avg_profit:+.2%}  "
            f"MDD={self.max_drawdown:.2%}  "
            f"샤프={self.sharpe_ratio:.2f}  "
            f"칼마={self.calmar_ratio:.2f}  "
            f"소르티노={self.sortino_ratio:.2f}  "
            f"손익비={self.profit_loss_ratio:.2f}  "
            f"거래={self.total_trades}건"
            f"{reason_str}"
            f"{pool_str}"
        )


# ============================================================================
# 백테스트 엔진
# ============================================================================

class BacktestEngine:
    """
    전략의 generate_signal()을 재사용하는 백테스트 엔진.

    Args:
        strategy: BaseStrategy 인스턴스 (generate_signal 구현 필수)
        initial_capital: 초기 자본금 (원, 기본 10,000,000원)
        max_positions: 동시 최대 보유 종목 수 (기본 5)
        position_size_pct: 종목당 투자 비율 (기본 0.2 = 자본의 20%)
        commission_rate: 위탁수수료율 (매수/매도 각각, 기본 COMMISSION_RATE)
        tax_rate: 증권거래세율 (매도 시만, 기본 SECURITIES_TAX_RATE)

    Example:
        engine = BacktestEngine(SampleStrategy(), initial_capital=10_000_000)
        result = engine.run(["005930"], daily_data=data, start_date="2024-01-01")
        print(result.summary())
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = 10_000_000,
        max_positions: int = 5,
        position_size_pct: float = 0.2,
        commission_rate: float = COMMISSION_RATE,
        tax_rate: float = SECURITIES_TAX_RATE,
    ):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate

        self.logger = logging.getLogger(f"backtest.{strategy.name}")

        # 전략 파라미터 초기화 (on_init 없이 직접 사용)
        self._init_strategy_params()

    def _init_strategy_params(self) -> None:
        """generate_signal에 필요한 전략 내부 파라미터를 초기화."""
        params = self.strategy.config.get("parameters", {})
        # SampleStrategy 등에서 on_init에서 설정하는 파라미터 fallback
        if not hasattr(self.strategy, "_ma_short"):
            self.strategy._ma_short = params.get("ma_short_period", 5)
        if not hasattr(self.strategy, "_ma_long"):
            self.strategy._ma_long = params.get("ma_long_period", 20)
        if not hasattr(self.strategy, "_rsi_period"):
            self.strategy._rsi_period = params.get("rsi_period", 14)
        if not hasattr(self.strategy, "_rsi_oversold"):
            self.strategy._rsi_oversold = params.get("rsi_oversold", 30)
        if not hasattr(self.strategy, "_rsi_overbought"):
            self.strategy._rsi_overbought = params.get("rsi_overbought", 70)
        if not hasattr(self.strategy, "_volume_multiplier"):
            self.strategy._volume_multiplier = params.get("volume_multiplier", 1.5)
        if not hasattr(self.strategy, "_min_buy_signals"):
            self.strategy._min_buy_signals = params.get("min_buy_signals", 2)

        # BBReversionStrategy / BBReversionORStrategy fallback (on_init not called in backtest path)
        if not hasattr(self.strategy, "_bb_period"):
            self.strategy._bb_period = params.get("bb_period", 20)
        if not hasattr(self.strategy, "_bb_std"):
            self.strategy._bb_std = params.get("bb_std", 2.0)
        if not hasattr(self.strategy, "_adx_period"):
            self.strategy._adx_period = params.get("adx_period", 14)
        if not hasattr(self.strategy, "_adx_max"):
            self.strategy._adx_max = params.get("adx_max", 20)
        if not hasattr(self.strategy, "_adx_exit"):
            self.strategy._adx_exit = params.get("adx_exit", 30)
        if not hasattr(self.strategy, "_vol_ratio_min"):
            self.strategy._vol_ratio_min = params.get("volume_ratio_min", 1.2)
        if not hasattr(self.strategy, "_vol_ma_period"):
            self.strategy._vol_ma_period = params.get("volume_ma_period", 20)

        risk = self.strategy.config.get("risk_management", {})
        if not hasattr(self.strategy, "_stop_loss_pct"):
            self.strategy._stop_loss_pct = risk.get("stop_loss_pct", 0.05)
        if not hasattr(self.strategy, "_take_profit_pct"):
            self.strategy._take_profit_pct = risk.get("take_profit_pct", 0.10)
        if not hasattr(self.strategy, "_max_daily_trades"):
            self.strategy._max_daily_trades = risk.get("max_daily_trades", 5)

        # 포지션 상태 초기화
        if not hasattr(self.strategy, "positions"):
            self.strategy.positions = {}
        if not hasattr(self.strategy, "daily_trades"):
            self.strategy.daily_trades = 0

    def run(
        self,
        stock_codes: List[str],
        daily_data: Dict[str, pd.DataFrame],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        candidate_provider: Optional[Callable[[str, str], List[str]]] = None,
        force_eod_liquidation: Optional[bool] = None,
    ) -> BacktestResult:
        """
        백테스트 실행.

        Args:
            stock_codes: 백테스트할 종목 코드 리스트
            daily_data: {종목코드: OHLCV DataFrame} 딕셔너리
                        컬럼: date, open, high, low, close, volume
                        날짜 오름차순 정렬 필요
            start_date: 백테스트 시작일 ("YYYY-MM-DD"), None이면 데이터 전체
            end_date: 백테스트 종료일 ("YYYY-MM-DD"), None이면 데이터 전체
            candidate_provider: (strategy_name: str, scan_date: str) → List[str]
                                 매 일자의 진입 가능 종목 코드 리스트를 반환하는 콜백.
                                 None이면 stock_codes 전체를 universe로 사용 (기존 동작).
                                 반환 리스트가 비어있으면 해당 일자 진입 스킵 (보수적 fallback).
            force_eod_liquidation: EOD 청산 제어 옵션.
                None (기본): holding_period에 따라 자동 결정 (intraday→청산, swing→보유).
                True: 강제 EOD 청산 - swing 전략도 매일 청산.
                False: EOD 청산 비활성 - intraday 전략도 다음날 보유 가능.

        Returns:
            BacktestResult: 백테스트 결과
        """
        # 전체 날짜 유니온 추출
        all_dates = self._collect_dates(daily_data, start_date, end_date)
        if not all_dates:
            self.logger.warning("백테스트 날짜 없음. daily_data를 확인하세요.")
            return self._empty_result()

        # 상태 초기화
        cash = self.initial_capital
        positions: Dict[str, Dict] = {}  # {stock_code: {qty, entry_price, entry_date, entry_cost, peak_price}}
        completed_trades: List[Dict] = []
        equity_curve: List[float] = []
        sells_by_reason: Dict[str, int] = {
            "stop_loss": 0,
            "trailing": 0,
            "max_holding": 0,
            "take_profit": 0,
            "strategy_signal": 0,
            "eod": 0,
        }
        candidate_pool_hits: int = 0  # candidate_provider가 후보 풀을 반환한 일자 수

        # 전략 상태 초기화
        self.strategy.positions = {}
        self.strategy.daily_trades = 0

        min_len = self.strategy.get_min_data_length()

        # 전략 리스크 파라미터 (없으면 기본값)
        stop_loss_rate = getattr(self.strategy, "_stop_loss_pct", 0.05)
        take_profit_rate = getattr(self.strategy, "_take_profit_pct", 0.10)
        is_intraday = getattr(self.strategy, "holding_period", "intraday") == "intraday"

        # force_eod_liquidation 해석:
        #   None → holding_period 기반 자동 (is_intraday 사용)
        #   True  → 무조건 EOD 청산 (swing도 포함)
        #   False → 무조건 EOD 비활성 (intraday도 다일 보유 가능)
        if force_eod_liquidation is True:
            eod_active = True
        elif force_eod_liquidation is False:
            eod_active = False
        else:
            eod_active = is_intraday

        for date in all_dates:
            self.strategy.daily_trades = 0  # 일일 거래 카운터 초기화

            # 1) 매도 판단: 보유 종목에 대해 당일 데이터로 신호 확인
            for code in list(positions.keys()):
                df_slice = self._get_data_up_to(daily_data, code, date)
                if df_slice is None or len(df_slice) == 0:
                    continue

                row = df_slice.iloc[-1]
                day_high = float(row.get("high", row["close"]))
                day_low = float(row.get("low", row["close"]))
                day_close = float(row["close"])
                pos = positions[code]
                qty = pos["qty"]
                entry_price = pos["entry_price"]

                # 최고가 갱신 (트레일링스톱 추적)
                pos["peak_price"] = max(pos["peak_price"], day_high)
                peak_price = pos["peak_price"]

                sell_price: Optional[float] = None
                sell_reason: str = ""

                # owner_strategy 우선 (다전략 지원 대비), 없으면 self.strategy fallback
                _pos_strategy = pos.get("owner_strategy") or self.strategy

                # 우선순위 1: 손절 - 일봉 low가 손절가 이하
                stop_loss_price = entry_price * (1 - stop_loss_rate)
                if day_low <= stop_loss_price:
                    sell_price = stop_loss_price
                    sell_reason = "stop_loss"

                # 우선순위 2: 트레일링스톱 - 고가 대비 -3% (손절 미발동 시)
                elif peak_price > entry_price:
                    trailing_stop_price = peak_price * (1 - TRAILING_STOP_CALLBACK_RATE)
                    if day_low <= trailing_stop_price:
                        sell_price = trailing_stop_price
                        sell_reason = "trailing"

                # 우선순위 3: 보유기간 초과 (max_holding_days) - 영업일 기준
                if sell_price is None:
                    strategy_max_days = getattr(_pos_strategy, 'max_holding_days', None)
                    if strategy_max_days is not None:
                        entry_date_str = pos["entry_date"]
                        try:
                            from datetime import date as _date, datetime as _datetime
                            from utils.korean_holidays import count_trading_days_between
                            entry_dt = _date.fromisoformat(entry_date_str)
                            current_dt = _date.fromisoformat(date)
                            entry_dtime = _datetime(entry_dt.year, entry_dt.month, entry_dt.day)
                            current_dtime = _datetime(current_dt.year, current_dt.month, current_dt.day)
                            days_held = count_trading_days_between(entry_dtime, current_dtime)
                        except (ValueError, TypeError):
                            days_held = 0
                        if days_held >= strategy_max_days:
                            sell_price = day_close
                            sell_reason = "max_holding"

                # 우선순위 4: 익절 - 일봉 high가 익절가 이상
                if sell_price is None:
                    take_profit_price = entry_price * (1 + take_profit_rate)
                    if day_high >= take_profit_price:
                        sell_price = take_profit_price
                        sell_reason = "take_profit"

                # 우선순위 5: 전략 매도 신호 (데이터 충분 시에만)
                if sell_price is None and len(df_slice) >= min_len:
                    signal = _pos_strategy.generate_signal(code, df_slice, timeframe='daily')
                    if signal is not None and signal.is_sell:
                        sell_price = day_close
                        sell_reason = "strategy_signal"

                # 우선순위 6: EOD 청산 (eod_active 여부에 따라)
                if sell_price is None and eod_active:
                    sell_price = day_close
                    sell_reason = "eod"

                if sell_price is not None:
                    # 매도 비용 = 수수료 + 증권거래세
                    sell_cost = sell_price * qty * (self.commission_rate + self.tax_rate)
                    proceeds = sell_price * qty - sell_cost
                    cash += proceeds

                    pnl = proceeds - pos["entry_cost"]
                    pnl_pct = pnl / pos["entry_cost"]

                    completed_trades.append({
                        "stock_code": code,
                        "entry_date": pos["entry_date"],
                        "exit_date": date,
                        "entry_price": entry_price,
                        "exit_price": sell_price,
                        "quantity": qty,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "signal_type": sell_reason,
                        "reasons": [sell_reason],
                    })
                    sells_by_reason[sell_reason] = sells_by_reason.get(sell_reason, 0) + 1

                    del positions[code]
                    if code in self.strategy.positions:
                        del self.strategy.positions[code]

                    self.logger.debug(
                        f"[{date}] 매도({sell_reason}): {code} {qty}주 @ {sell_price:,.0f}원 "
                        f"(수익률 {pnl_pct:+.2%})"
                    )

            # 2) 매수 판단: 포지션 여유 있으면 미보유 종목 신호 확인
            available_slots = self.max_positions - len(positions)
            if available_slots > 0:
                # candidate_provider가 제공된 경우 해당 일자의 후보 풀로 universe 한정
                if candidate_provider is not None:
                    candidate_codes = candidate_provider(self.strategy.name, date)
                    if candidate_codes:
                        candidate_pool_hits += 1
                        candidate_set: Set[str] = set(candidate_codes)
                        buy_universe = [c for c in stock_codes if c in candidate_set]
                        self.logger.debug(
                            f"[{date}] 후보 풀 적용: {len(stock_codes)}종목 → {len(buy_universe)}종목"
                        )
                    else:
                        # 후보 풀 비어있으면 진입 스킵 (보수적 fallback)
                        self.logger.debug(f"[{date}] 후보 풀 없음 → 진입 스킵")
                        buy_universe = []
                else:
                    buy_universe = stock_codes

                for code in buy_universe:
                    if code in positions:
                        continue
                    if available_slots <= 0:
                        break

                    df_slice = self._get_data_up_to(daily_data, code, date)
                    if df_slice is None or len(df_slice) < min_len:
                        continue

                    signal = self.strategy.generate_signal(code, df_slice, timeframe='daily')
                    if signal is None:
                        continue

                    if signal.is_buy:
                        buy_price = float(df_slice["close"].iloc[-1])
                        invest_amount = cash * self.position_size_pct

                        # 자금 부족 시 스킵
                        if invest_amount < buy_price:
                            self.logger.debug(
                                f"[{date}] 매수 스킵: {code} 자금 부족 "
                                f"(필요={buy_price:,.0f}, 가용={invest_amount:,.0f})"
                            )
                            continue

                        qty = int(invest_amount // buy_price)
                        if qty <= 0:
                            continue

                        buy_cost_fee = buy_price * qty * self.commission_rate
                        total_cost = buy_price * qty + buy_cost_fee
                        cash -= total_cost

                        positions[code] = {
                            "qty": qty,
                            "entry_price": buy_price,
                            "entry_date": date,
                            "entry_cost": total_cost,
                            "peak_price": buy_price,
                            "owner_strategy": self.strategy,  # 다전략 지원 대비: 매수 시점 전략 기록
                        }
                        self.strategy.positions[code] = {
                            "quantity": qty,
                            "entry_price": buy_price,
                            "entry_time": None,
                        }
                        available_slots -= 1

                        self.logger.debug(
                            f"[{date}] 매수: {code} {qty}주 @ {buy_price:,.0f}원 "
                            f"(투자={total_cost:,.0f}원)"
                        )

            # 3) 당일 종가 기준 자산 평가
            portfolio_value = cash
            for code, pos in positions.items():
                df_slice = self._get_data_up_to(daily_data, code, date)
                if df_slice is not None and len(df_slice) > 0:
                    current_price = float(df_slice["close"].iloc[-1])
                    portfolio_value += current_price * pos["qty"]
                else:
                    # 데이터 없으면 취득원가로 평가
                    portfolio_value += pos["entry_cost"]

            equity_curve.append(portfolio_value)

        # 4) 남은 포지션 강제 청산 (마지막 날 종가)
        last_date = all_dates[-1]
        for code, pos in list(positions.items()):
            df_slice = self._get_data_up_to(daily_data, code, last_date)
            if df_slice is None or len(df_slice) == 0:
                continue
            sell_price = float(df_slice["close"].iloc[-1])
            qty = pos["qty"]
            sell_cost = sell_price * qty * (self.commission_rate + self.tax_rate)
            proceeds = sell_price * qty - sell_cost
            cash += proceeds

            pnl = proceeds - pos["entry_cost"]
            pnl_pct = pnl / pos["entry_cost"]
            completed_trades.append({
                "stock_code": code,
                "entry_date": pos["entry_date"],
                "exit_date": last_date,
                "entry_price": pos["entry_price"],
                "exit_price": sell_price,
                "quantity": qty,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "signal_type": "forced_exit",
                "reasons": ["백테스트 종료 강제청산"],
            })
            sells_by_reason["forced_exit"] = sells_by_reason.get("forced_exit", 0) + 1

        # equity_curve 마지막 값 업데이트 (강제청산 반영)
        if equity_curve and positions:
            equity_curve[-1] = cash

        return self._calculate_metrics(
            completed_trades=completed_trades,
            equity_curve=equity_curve,
            sells_by_reason=sells_by_reason,
            candidate_pool_hits=candidate_pool_hits,
        )

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _collect_dates(
        self,
        daily_data: Dict[str, pd.DataFrame],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> List[str]:
        """모든 종목에서 날짜를 수집해 정렬된 유니온 반환 (YYYY-MM-DD 문자열)."""
        date_set: set = set()
        for df in daily_data.values():
            if df is None or df.empty:
                continue
            dates = df["date"].astype(str).str[:10]
            date_set.update(dates.tolist())

        all_dates = sorted(date_set)

        if start_date:
            all_dates = [d for d in all_dates if d >= start_date[:10]]
        if end_date:
            all_dates = [d for d in all_dates if d <= end_date[:10]]

        return all_dates

    def _get_data_up_to(
        self,
        daily_data: Dict[str, pd.DataFrame],
        code: str,
        date: str,
    ) -> Optional[pd.DataFrame]:
        """
        특정 종목의 date 이전(포함) 데이터만 슬라이스해 반환.
        전략이 미래 정보를 사용하지 않도록 보장(look-ahead bias 방지).
        """
        df = daily_data.get(code)
        if df is None or df.empty:
            return None

        dates_str = df["date"].astype(str).str[:10]
        mask = dates_str <= date
        sliced = df[mask].copy()

        return sliced if not sliced.empty else None

    def _calculate_metrics(
        self,
        completed_trades: List[Dict],
        equity_curve: List[float],
        sells_by_reason: Optional[Dict[str, int]] = None,
        candidate_pool_hits: int = 0,
    ) -> BacktestResult:
        """성과 지표 계산."""
        total_trades = len(completed_trades)
        final_equity = equity_curve[-1] if equity_curve else self.initial_capital
        total_return = (final_equity - self.initial_capital) / self.initial_capital
        sells_by_reason = sells_by_reason or {}

        if total_trades == 0:
            mdd = self._calc_mdd(equity_curve)
            return BacktestResult(
                total_return=total_return,
                win_rate=0.0,
                avg_profit=0.0,
                max_drawdown=mdd,
                sharpe_ratio=0.0,
                calmar_ratio=0.0,
                sortino_ratio=0.0,
                profit_loss_ratio=0.0,
                total_trades=0,
                trades=completed_trades,
                equity_curve=equity_curve,
                sells_by_reason=sells_by_reason,
                candidate_pool_hits=candidate_pool_hits,
            )

        pnl_pcts = [t["pnl_pct"] for t in completed_trades]
        wins = [p for p in pnl_pcts if p > 0]
        losses = [p for p in pnl_pcts if p <= 0]

        win_rate = len(wins) / total_trades
        avg_profit = float(np.mean(pnl_pcts))

        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = abs(float(np.mean(losses))) if losses else 0.0
        profit_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else float("inf")

        mdd = self._calc_mdd(equity_curve)
        sharpe = self._calc_sharpe(equity_curve)
        calmar = self._calc_calmar(total_return, mdd, len(equity_curve))
        sortino = self._calc_sortino(equity_curve)

        return BacktestResult(
            total_return=total_return,
            win_rate=win_rate,
            avg_profit=avg_profit,
            max_drawdown=mdd,
            sharpe_ratio=sharpe,
            calmar_ratio=calmar,
            sortino_ratio=sortino,
            profit_loss_ratio=profit_loss_ratio,
            total_trades=total_trades,
            trades=completed_trades,
            equity_curve=equity_curve,
            sells_by_reason=sells_by_reason,
            candidate_pool_hits=candidate_pool_hits,
        )

    @staticmethod
    def _calc_mdd(equity_curve: List[float]) -> float:
        """최대 낙폭(MDD) 계산. 양수로 반환 (예: 0.15 = 15% 낙폭)."""
        if len(equity_curve) < 2:
            return 0.0
        arr = np.array(equity_curve, dtype=float)
        peak = np.maximum.accumulate(arr)
        drawdowns = (peak - arr) / peak
        return float(np.max(drawdowns))

    @staticmethod
    def _calc_sharpe(equity_curve: List[float], risk_free_rate: float = 0.0) -> float:
        """일별 수익률 기반 샤프 비율 계산 (연율화, 무위험수익률 기본 0%)."""
        if len(equity_curve) < 2:
            return 0.0
        arr = np.array(equity_curve, dtype=float)
        daily_returns = np.diff(arr) / arr[:-1]
        excess = daily_returns - risk_free_rate / 252
        if excess.std() == 0:
            return 0.0
        return float(excess.mean() / excess.std() * np.sqrt(252))

    @staticmethod
    def _calc_calmar(total_return: float, mdd: float, n_days: int) -> float:
        """칼마 비율 계산 (연환산 수익률 / MDD).

        Args:
            total_return: 누적 수익률 (예: 0.12 = +12%).
            mdd: 최대 낙폭 (양수, 예: 0.15 = 15%).
            n_days: 백테스트 일수 (연율화 기준).

        Returns:
            CAGR / MDD. MDD가 0이면 0 반환.
        """
        if mdd <= 0 or n_days <= 0:
            return 0.0
        years = n_days / 252.0
        # 복리 연환산: (1 + total_return)^(1/years) - 1
        cagr = (1.0 + total_return) ** (1.0 / years) - 1.0
        return float(cagr / mdd)

    @staticmethod
    def _calc_sortino(equity_curve: List[float], risk_free_rate: float = 0.0) -> float:
        """소르티노 비율 계산 (하방 편차 기반, 연율화, 무위험률 기본 0%).

        하방 편차 = 음수 초과 수익률의 표준편차.
        """
        if len(equity_curve) < 2:
            return 0.0
        arr = np.array(equity_curve, dtype=float)
        daily_returns = np.diff(arr) / arr[:-1]
        excess = daily_returns - risk_free_rate / 252
        downside = excess[excess < 0]
        if len(downside) == 0:
            # 손실 일자 없으면 무한대 → 실용상 큰 값 반환
            return float(excess.mean() * np.sqrt(252)) if excess.mean() > 0 else 0.0
        downside_std = float(np.std(downside))
        if downside_std == 0:
            return 0.0
        return float(excess.mean() / downside_std * np.sqrt(252))

    def _get_trading_days_range(self, start_date: str, end_date: str) -> List[str]:
        """start_date~end_date 범위의 거래일 목록 반환 (YYYYMMDD 포맷).

        한국 영업일 캘린더가 없으면 pandas BusinessDay(주말 제외) fallback.
        """
        try:
            from utils.korean_holidays import get_trading_days
            return [d.strftime("%Y%m%d") for d in get_trading_days(start_date, end_date)]
        except Exception:
            s = pd.Timestamp(f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}")
            e = pd.Timestamp(f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}")
            return [d.strftime("%Y%m%d") for d in pd.date_range(s, e, freq="B")]

    def _empty_result(self) -> BacktestResult:
        """데이터 없을 때 반환하는 빈 결과."""
        return BacktestResult(
            total_return=0.0,
            win_rate=0.0,
            avg_profit=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            calmar_ratio=0.0,
            sortino_ratio=0.0,
            profit_loss_ratio=0.0,
            total_trades=0,
            trades=[],
            equity_curve=[],
            sells_by_reason={},
        )

    # ========================================================================
    # 분봉 백테스트 (T+0 intraday)
    # ========================================================================

    @staticmethod
    def _apply_buy(
        price: float,
        qty: int,
        slip_bps: float,
        fee_pct: float,
    ) -> Tuple[float, float]:
        """매수 슬리피지·수수료 적용.

        Returns:
            (체결가, 총 차감액 = 체결가*qty + 수수료)
        """
        fill = price * (1.0 + slip_bps / 10_000.0)
        gross = fill * qty
        fee = gross * fee_pct
        return fill, gross + fee

    @staticmethod
    def _apply_sell(
        price: float,
        qty: int,
        slip_bps: float,
        fee_pct: float,
        tax_pct: float,
    ) -> Tuple[float, float]:
        """매도 슬리피지·수수료·거래세 적용.

        Returns:
            (체결가, 순 수익 = 체결가*qty - 수수료 - 거래세)
        """
        fill = price * (1.0 - slip_bps / 10_000.0)
        gross = fill * qty
        fee = gross * fee_pct
        tax = gross * tax_pct
        return fill, gross - fee - tax

    def _simulate_day_minute(
        self,
        trade_date: str,
        candidates: List[str],
        positions: Dict[str, Dict],
        cash: float,
        strategy: BaseStrategy,
        minute_data: Dict[str, pd.DataFrame],
        max_positions: int,
        slip_bps: float,
        fee_buy_pct: float,
        fee_sell_pct: float,
        tax_sell_pct: float,
        eod_time: str,
        stop_loss_pct: float,
        take_profit_pct: float,
        trail_pct: Optional[float],
        verbose: bool,
    ) -> Tuple[float, List[Dict], Dict[str, int]]:
        """단일 거래일 분봉 시뮬레이션.

        Args:
            trade_date: 거래일 'YYYYMMDD'
            candidates: 그 날의 매수 후보 종목 리스트
            positions: 보유 포지션 dict (in/out 모두 반영). 키: stock_code.
                각 값: {qty, entry_price, entry_time, entry_cost, high_water, capital_allocated}
            cash: 현재 보유 현금
            strategy: 전략 인스턴스
            minute_data: {stock_code -> DataFrame(datetime, open, high, low, close, volume, ...)}
            max_positions: 최대 동시 보유 종목 수
            slip_bps: 슬리피지 (bp)
            fee_buy_pct: 매수 수수료
            fee_sell_pct: 매도 수수료
            tax_sell_pct: 거래세
            eod_time: EOD 강제청산 시각 'HH:MM'
            stop_loss_pct: 손절 비율 (0.01 = 1%)
            take_profit_pct: 익절 비율 (0.02 = 2%)
            trail_pct: 트레일링 비율 (None이면 비활성)
            verbose: 상세 로그 여부

        Returns:
            (new_cash, trades_today, sells_by_reason_delta)
        """
        trades_today: List[Dict] = []
        sells_by_reason_delta: Dict[str, int] = {}
        # 당일 이미 진입했던 종목 - 청산 후 재진입 차단 (종목당 일일 1회 진입)
        entered_today: set = set()

        # EOD 시각 파싱 (HH:MM → 분 단위 정수, 비교용)
        eod_h, eod_m = (int(x) for x in eod_time.split(":"))

        # 모든 관련 종목 분봉 수집: 후보 + 보유 중
        all_codes = list(set(candidates) | set(positions.keys()))
        # minute_data는 이미 로드된 상태로 전달됨

        # --- 성능 최적화: datetime → index 변환 ---
        # df[df["datetime"]==ts] O(N) 탐색 → .loc[ts] O(log N) 으로 단축
        indexed_data: Dict[str, pd.DataFrame] = {}
        for code in all_codes:
            df = minute_data.get(code)
            if df is not None and not df.empty and "datetime" in df.columns:
                df_idx = df.set_index("datetime", drop=False)
                df_idx = df_idx[~df_idx.index.duplicated(keep="last")]
                indexed_data[code] = df_idx

        # 전체 분봉 타임스탬프 유니온 구성 (정렬)
        ts_set: set = set()
        for df_idx in indexed_data.values():
            ts_set.update(df_idx.index.tolist())
        all_timestamps = sorted(ts_set)

        for ts in all_timestamps:
            ts_h = ts.hour
            ts_m = ts.minute

            # 09:00 이전 분봉 건너뜀
            if ts_h < 9:
                continue

            is_eod_bar = (ts_h > eod_h) or (ts_h == eod_h and ts_m >= eod_m)

            # --- 보유 포지션 청산 판단 ---
            for code in list(positions.keys()):
                df_idx = indexed_data.get(code)
                if df_idx is None or df_idx.empty:
                    continue

                if ts not in df_idx.index:
                    continue

                bar = df_idx.loc[ts]
                # Series일 수도 있고 DataFrame일 수도 있음 (중복 제거했으므로 Series)
                bar_high = float(bar["high"])
                bar_low = float(bar["low"])
                bar_close = float(bar["close"])

                pos = positions[code]
                entry_price = pos["entry_price"]
                qty = pos["qty"]

                # 분봉 결손(VI/거래정지): high==low==0 이면 건너뜀
                if bar_high == 0 and bar_low == 0:
                    continue

                sell_price: Optional[float] = None
                sell_reason: str = ""

                # EOD 강제청산 최우선
                if is_eod_bar:
                    sell_price = bar_close
                    sell_reason = "eod_t0"
                else:
                    # 손절: bar_low가 손절가 이하
                    sl_price = entry_price * (1.0 - stop_loss_pct)
                    if bar_low <= sl_price:
                        sell_price = sl_price
                        sell_reason = "intraday_sl"
                    # 익절: bar_high가 익절가 이상
                    elif bar_high >= entry_price * (1.0 + take_profit_pct):
                        sell_price = entry_price * (1.0 + take_profit_pct)
                        sell_reason = "intraday_tp"
                    # 트레일링: high_water 갱신 후 하락
                    elif trail_pct is not None:
                        pos["high_water"] = max(pos["high_water"], bar_high)
                        trail_trigger = pos["high_water"] * (1.0 - trail_pct)
                        if bar_low <= trail_trigger and pos["high_water"] > entry_price:
                            sell_price = trail_trigger
                            sell_reason = "intraday_trail"
                    # 전략 매도 신호
                    if sell_price is None:
                        # .loc[:ts] - copy 없이 뷰로 슬라이스 (O(log N))
                        df_slice = df_idx.loc[:ts]
                        if not df_slice.empty:
                            sig = strategy.generate_signal(code, df_slice, timeframe="minute")
                            if sig is not None and sig.is_sell:
                                sell_price = bar_close
                                sell_reason = "signal_sell"

                if sell_price is not None:
                    fill_price, net_proceeds = self._apply_sell(
                        sell_price, qty, slip_bps, fee_sell_pct, tax_sell_pct
                    )
                    entry_cost = pos["entry_cost"]
                    pnl = net_proceeds - entry_cost
                    pnl_pct = pnl / entry_cost if entry_cost > 0 else 0.0
                    cash += net_proceeds

                    trades_today.append({
                        "stock_code": code,
                        "entry_date": trade_date,
                        "exit_date": trade_date,
                        "entry_time": pos.get("entry_time"),
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": fill_price,
                        "quantity": qty,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "signal_type": sell_reason,
                        "reasons": [sell_reason],
                    })
                    sells_by_reason_delta[sell_reason] = (
                        sells_by_reason_delta.get(sell_reason, 0) + 1
                    )
                    del positions[code]
                    entered_today.add(code)  # 청산 후 당일 재진입 차단

                    if verbose:
                        self.logger.info(
                            f"[{trade_date} {ts.strftime('%H:%M')}] 매도({sell_reason}): "
                            f"{code} {qty}주 @ {fill_price:,.0f}원 PnL={pnl_pct:+.2%}"
                        )

            # EOD 이후엔 신규 매수 없음
            if is_eod_bar:
                continue

            # --- 신규 매수 판단 ---
            available_slots = max_positions - len(positions)
            if available_slots <= 0:
                continue

            for code in candidates:
                if code in positions:
                    continue
                if code in entered_today:  # 당일 청산 후 재진입 차단
                    continue
                if available_slots <= 0:
                    break

                df_idx = indexed_data.get(code)
                if df_idx is None or df_idx.empty:
                    continue

                if ts not in df_idx.index:
                    continue

                bar = df_idx.loc[ts]
                bar_close = float(bar["close"])
                bar_high = float(bar["high"])
                bar_low = float(bar["low"])

                # 분봉 결손 건너뜀
                if bar_high == 0 and bar_low == 0:
                    continue

                # 전략 신호 확인: .loc[:ts] - copy 없이 뷰로 슬라이스
                df_slice = df_idx.loc[:ts]
                if df_slice.empty:
                    continue

                sig = strategy.generate_signal(code, df_slice, timeframe="minute")
                if sig is None or not sig.is_buy:
                    continue

                # 자본 배분: cash / max_positions (슬롯당 균등)
                capital_per_slot = cash / max_positions if max_positions > 0 else cash
                if capital_per_slot < bar_close:
                    continue

                qty = int(capital_per_slot // bar_close)
                if qty <= 0:
                    continue

                fill_price, total_cost = self._apply_buy(bar_close, qty, slip_bps, fee_buy_pct)
                if total_cost > cash:
                    continue

                cash -= total_cost
                positions[code] = {
                    "qty": qty,
                    "entry_price": fill_price,
                    "entry_time": ts,
                    "entry_cost": total_cost,
                    "high_water": fill_price,
                    "capital_allocated": total_cost,
                }
                entered_today.add(code)  # 진입 기록 - 당일 재진입 차단
                available_slots -= 1

                if verbose:
                    self.logger.info(
                        f"[{trade_date} {ts.strftime('%H:%M')}] 매수: "
                        f"{code} {qty}주 @ {fill_price:,.0f}원 (투자={total_cost:,.0f}원)"
                    )

        return cash, trades_today, sells_by_reason_delta

    def run_minute(
        self,
        stock_codes: List[str],
        start_date: str,
        end_date: str,
        candidate_provider: Optional[Callable[[str], List[str]]] = None,
        initial_capital: float = 10_000_000,
        max_positions: int = 5,
        slip_bps: float = 5.0,
        fee_buy_pct: float = 0.00015,
        fee_sell_pct: float = 0.00015,
        tax_sell_pct: float = 0.0018,
        eod_time: str = "15:20",
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.02,
        trail_pct: Optional[float] = None,
        skip_dates: Optional[Set[str]] = None,
        verbose: bool = False,
    ) -> BacktestResult:
        """T+0 분봉 백테스트.

        매일 09:00~eod_time 분봉 단위로 시뮬레이션합니다.
        - 동시 N종목 FIFO 큐, 종목당 cash/max_positions 자본 배분
        - EOD eod_time 일괄청산 (sell_reason='eod_t0')
        - Intraday SL/TP/trail 트리거 (분봉 high/low로 판정)
        - strategy.generate_signal(stock_code, df, timeframe='minute') 호출
        - 분봉 결손(VI/거래정지)은 해당 분봉 신호 무시

        Args:
            stock_codes: 백테스트 대상 종목 코드 리스트
            start_date: 시작일 'YYYYMMDD'
            end_date: 종료일 'YYYYMMDD'
            candidate_provider: (trade_date: str) -> [codes] 콜백. None이면 stock_codes 전체.
            initial_capital: 초기 자본금
            max_positions: 최대 동시 보유 종목 수
            slip_bps: 슬리피지 (bp, 매수+/매도-)
            fee_buy_pct: 매수 수수료율
            fee_sell_pct: 매도 수수료율
            tax_sell_pct: 거래세율 (매도 시)
            eod_time: EOD 강제청산 시각 'HH:MM'
            stop_loss_pct: 손절 비율
            take_profit_pct: 익절 비율
            trail_pct: 트레일링 비율 (None이면 비활성)
            skip_dates: 건너뛸 거래일 set. 'YYYYMMDD' 완전 일치 또는 prefix 지원.
            verbose: 상세 로그 출력 여부

        Returns:
            BacktestResult
        """
        # PriceRepository 지연 import (DB 없는 환경에서도 engine 로드 가능)
        try:
            from db.repositories.price import PriceRepository
            price_repo = PriceRepository()
        except Exception as e:
            self.logger.error(f"PriceRepository 초기화 실패: {e}")
            return self._empty_result()

        # 거래일 목록 생성 (start_date~end_date 범위, YYYYMMDD 포맷)
        trading_days = self._get_trading_days_range(start_date, end_date)

        if not trading_days:
            self.logger.warning("run_minute: 거래일 없음.")
            return self._empty_result()

        # === ORB v2 외부 데이터 사전로드 (KS11 일봉 → kospi_market_up bool 플래그) ===
        # 전략이 set_daily_context를 사용하는 경우에만 의미 있음. 비용은 작음(쿼리 1번).
        # minute_candles에 KOSPI 분봉이 없어 daily_candles(KS11)로 대체. 시장환경 정의:
        #   당일 ctx["kospi_market_up"] = (직전 거래일 KS11 종가 > 그 전 거래일 종가)
        # look-ahead 방지: 당일 KS11 일봉은 사용하지 않음.
        kospi_market_up_by_date: Dict[str, bool] = {}
        try:
            max_d = max(trading_days)
            from db.connection import DatabaseConnection
            with DatabaseConnection.get_connection() as _conn:
                _cur = _conn.cursor()
                _cur.execute(
                    """SELECT stck_bsop_date, stck_clpr FROM daily_candles
                       WHERE stock_code = %s
                         AND stck_bsop_date <= %s
                       ORDER BY stck_bsop_date ASC""",
                    (KOSPI_CODE, max_d),
                )
                ks11_rows = _cur.fetchall()
                _cur.close()
            if ks11_rows:
                _ks11 = []
                for _d, _c in ks11_rows:
                    try:
                        _ks11.append((str(_d), float(_c)))
                    except (TypeError, ValueError):
                        continue
                for _trade_d in trading_days:
                    _prior = [(d, c) for d, c in _ks11 if d < _trade_d]
                    if len(_prior) >= 2:
                        _, prev_close = _prior[-1]
                        _, prev_prev_close = _prior[-2]
                        kospi_market_up_by_date[_trade_d] = prev_close > prev_prev_close
                    # else: 키 누락 → 전략에서 fallback 통과
        except Exception as _exc:
            self.logger.warning(f"run_minute: KS11 일봉 사전로드 실패 - kospi_market_up 결손 ({_exc})")

        # skip_dates 전처리: prefix와 완전 일치 모두 지원
        skip_set: Set[str] = set()
        skip_prefixes: List[str] = []
        if skip_dates:
            for sd in skip_dates:
                if len(sd) == 8:
                    skip_set.add(sd)
                else:
                    skip_prefixes.append(sd)

        # 상태 초기화
        cash = initial_capital
        positions: Dict[str, Dict] = {}
        completed_trades: List[Dict] = []
        equity_curve: List[float] = [initial_capital]  # 초기자본을 curve[0]에 포함 (docstring 준수)
        sells_by_reason: Dict[str, int] = {
            "eod_t0": 0,
            "intraday_sl": 0,
            "intraday_tp": 0,
            "intraday_trail": 0,
            "signal_sell": 0,
        }
        candidate_pool_hits: int = 0

        # 전일 OHLC 캐시: {(stock_code, trade_date) -> {"open", "high", "low", "close"}}
        # 거래일 N개에 대해 SQL N회로 줄임 (기존: N x 종목수 회)
        _prev_ohlc_cache: Dict[Tuple[str, str], dict] = {}

        for trade_date in trading_days:
            # skip_dates 처리
            if trade_date in skip_set:
                continue
            if any(trade_date.startswith(p) for p in skip_prefixes):
                continue

            # === per-day daily context for strategy ===
            if hasattr(self.strategy, "set_daily_context"):
                # 당일 후보 종목 결정 (candidate_provider 우선)
                if candidate_provider is not None:
                    _today_codes = candidate_provider(trade_date)
                else:
                    _today_codes = list(stock_codes) if stock_codes else []

                # 전일 일봉 거래량 조회 (당일 후보만)
                # 1차: daily_candles, 2차 fallback: minute_candles 일별 sum(volume)
                _prev_vol: Dict[str, float] = {}
                try:
                    if _today_codes:
                        from db.connection import DatabaseConnection
                        with DatabaseConnection.get_connection() as _conn:
                            _cur = _conn.cursor()
                            # 1차: daily_candles
                            _cur.execute(
                                """SELECT stock_code, acml_vol FROM daily_candles
                                   WHERE stock_code = ANY(%s)
                                     AND stck_bsop_date = (
                                       SELECT MAX(stck_bsop_date) FROM daily_candles
                                       WHERE stock_code = ANY(%s) AND stck_bsop_date < %s
                                     )""",
                                (_today_codes, _today_codes, trade_date),
                            )
                            for _code, _vol in _cur.fetchall():
                                try:
                                    _v = float(_vol or 0.0)
                                except (TypeError, ValueError):
                                    _v = 0.0
                                if _v > 0:
                                    _prev_vol[_code] = _v

                            # 2차 fallback: 1차에서 누락/0인 종목은 minute_candles 일별 sum(volume)
                            _missing = [c for c in _today_codes if c not in _prev_vol]
                            if _missing:
                                _td = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
                                _cur.execute(
                                    """SELECT stock_code, SUM(volume)::bigint AS vol
                                       FROM minute_candles
                                       WHERE stock_code = ANY(%s)
                                         AND datetime::date = (
                                           SELECT MAX(datetime::date) FROM minute_candles
                                           WHERE stock_code = ANY(%s) AND datetime::date < %s
                                         )
                                       GROUP BY stock_code""",
                                    (_missing, _missing, _td),
                                )
                                for _code, _vol in _cur.fetchall():
                                    try:
                                        _v = float(_vol or 0.0)
                                    except (TypeError, ValueError):
                                        _v = 0.0
                                    if _v > 0:
                                        _prev_vol[_code] = _v
                            _cur.close()
                except Exception as _exc:
                    self.logger.warning(f"run_minute: {trade_date} prev_day_volume 조회 실패 ({_exc})")

                ctx: Dict[str, Any] = {"prev_day_volume": _prev_vol}
                if trade_date in kospi_market_up_by_date:
                    ctx["kospi_market_up"] = kospi_market_up_by_date[trade_date]
                # 키 누락 시 전략은 fallback 통과
                self.strategy.set_daily_context(trade_date, ctx)

            # 후보 종목 결정
            if candidate_provider is not None:
                day_candidates = candidate_provider(trade_date)
                if day_candidates:
                    candidate_pool_hits += 1
                else:
                    day_candidates = []
            else:
                day_candidates = list(stock_codes)

            # 분봉 일괄 로드: 후보 + 보유 중 종목
            all_codes_today = list(set(day_candidates) | set(positions.keys()))
            if not all_codes_today:
                equity_curve.append(cash)
                continue

            minute_data = price_repo.get_minute_prices_bulk(all_codes_today, trade_date)

            # 전일 OHLC를 minute_data[code].attrs 에 주입 (support_resistance / red_to_green 전략 지원)
            # trading_days 인덱스로 전일 거래일 결정 (캘린더 기반, 안전)
            trade_idx = trading_days.index(trade_date)
            prev_trade_date: Optional[str] = trading_days[trade_idx - 1] if trade_idx > 0 else None
            if prev_trade_date is not None:
                # 캐시에 없는 종목만 bulk 조회
                missing_codes = [
                    c for c in all_codes_today
                    if (c, prev_trade_date) not in _prev_ohlc_cache
                ]
                if missing_codes:
                    prev_minute_data = price_repo.get_minute_prices_bulk(missing_codes, prev_trade_date)
                    for code in missing_codes:
                        df_prev = prev_minute_data.get(code)
                        if df_prev is not None and not df_prev.empty:
                            _prev_ohlc_cache[(code, prev_trade_date)] = {
                                "open":  float(df_prev["open"].iloc[0]),
                                "high":  float(df_prev["high"].max()),
                                "low":   float(df_prev["low"].min()),
                                "close": float(df_prev["close"].iloc[-1]),
                            }

                for code in all_codes_today:
                    df_cur = minute_data.get(code)
                    if df_cur is None or df_cur.empty:
                        continue
                    ohlc = _prev_ohlc_cache.get((code, prev_trade_date))
                    if ohlc is None:
                        continue
                    df_cur.attrs["prev_close"] = ohlc["close"]
                    df_cur.attrs["prev_day_ohlc"] = ohlc

            # 단일 거래일 시뮬레이션
            cash, day_trades, day_sells = self._simulate_day_minute(
                trade_date=trade_date,
                candidates=day_candidates,
                positions=positions,
                cash=cash,
                strategy=self.strategy,
                minute_data=minute_data,
                max_positions=max_positions,
                slip_bps=slip_bps,
                fee_buy_pct=fee_buy_pct,
                fee_sell_pct=fee_sell_pct,
                tax_sell_pct=tax_sell_pct,
                eod_time=eod_time,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                trail_pct=trail_pct,
                verbose=verbose,
            )
            completed_trades.extend(day_trades)
            for reason, cnt in day_sells.items():
                sells_by_reason[reason] = sells_by_reason.get(reason, 0) + cnt

            # 일별 자산 평가 (현금 + 미청산 포지션 종가 평가)
            portfolio_value = cash
            for code, pos in positions.items():
                df = minute_data.get(code)
                if df is not None and not df.empty and "close" in df.columns:
                    last_close = float(df["close"].iloc[-1])
                    portfolio_value += last_close * pos["qty"]
                else:
                    portfolio_value += pos["entry_cost"]
            equity_curve.append(portfolio_value)

        # 마지막 날 미청산 포지션 강제청산 (최종 종가)
        if positions:
            last_date = trading_days[-1]
            for code, pos in list(positions.items()):
                last_data = price_repo.get_minute_prices_bulk([code], last_date)
                df = last_data.get(code)
                if df is not None and not df.empty and "close" in df.columns:
                    sell_price = float(df["close"].iloc[-1])
                else:
                    sell_price = pos["entry_price"]

                qty = pos["qty"]
                _, net_proceeds = self._apply_sell(
                    sell_price, qty, slip_bps, fee_sell_pct, tax_sell_pct
                )
                pnl = net_proceeds - pos["entry_cost"]
                pnl_pct = pnl / pos["entry_cost"] if pos["entry_cost"] > 0 else 0.0
                cash += net_proceeds

                completed_trades.append({
                    "stock_code": code,
                    "entry_date": last_date,
                    "exit_date": last_date,
                    "entry_time": pos.get("entry_time"),
                    "exit_time": None,
                    "entry_price": pos["entry_price"],
                    "exit_price": sell_price,
                    "quantity": qty,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "signal_type": "forced_exit",
                    "reasons": ["백테스트 종료 강제청산"],
                })
                sells_by_reason["forced_exit"] = sells_by_reason.get("forced_exit", 0) + 1

            if equity_curve:
                equity_curve[-1] = cash

        return self._calculate_metrics(
            completed_trades=completed_trades,
            equity_curve=equity_curve,
            sells_by_reason=sells_by_reason,
            candidate_pool_hits=candidate_pool_hits,
        )


# ============================================================================
# 헬퍼 팩토리: screener_snapshots DB 기반 candidate_provider 생성
# ============================================================================

def make_screener_snapshot_provider(
    strategy_name: str,
    params_hash: Optional[str] = None,
) -> Callable[[str, str], List[str]]:
    """
    screener_snapshots DB 테이블에서 날짜별 후보 코드 리스트를 반환하는
    candidate_provider 콜백을 생성합니다.

    Usage:
        from backtest.engine import BacktestEngine, make_screener_snapshot_provider

        provider = make_screener_snapshot_provider("SampleStrategy")
        result = engine.run(
            stock_codes=all_codes,
            daily_data=data,
            candidate_provider=provider,
        )

    Args:
        strategy_name: screener_snapshots.strategy 컬럼값 (예: "SampleStrategy")
        params_hash: 특정 파라미터 해시로 한정할 경우 지정. None이면 해당 날짜의
                     모든 파라미터 해시 스냅샷을 합산해 후보 풀 구성.

    Returns:
        (strategy_name: str, scan_date: str) → List[str] 형태의 콜백.
        DB 조회 실패 또는 스냅샷 없는 날짜는 빈 리스트를 반환합니다.
    """
    # 조회 결과를 날짜별로 캐싱해 반복 DB 호출 방지
    _cache: Dict[str, List[str]] = {}

    def _provider(strategy: str, scan_date: str) -> List[str]:
        if scan_date in _cache:
            return _cache[scan_date]

        try:
            if CandidateRepository is None:
                raise ImportError("db.repositories.candidate 패키지를 사용할 수 없습니다")

            repo = CandidateRepository()
            parsed_date = DateType.fromisoformat(scan_date)

            if params_hash:
                rows = repo.get_screener_snapshot(strategy_name, parsed_date, params_hash)
                codes = [r["stock_code"] for r in rows]
            else:
                df = repo.get_snapshot_date_range(
                    strategy=strategy_name,
                    start_date=parsed_date,
                    end_date=parsed_date,
                    params_hash=None,
                )
                codes = df["stock_code"].tolist() if not df.empty else []

            _cache[scan_date] = codes
            return codes

        except Exception as e:
            logging.getLogger("backtest.screener_provider").warning(
                f"screener_snapshots 조회 실패 [{scan_date}]: {e}"
            )
            _cache[scan_date] = []
            return []

    return _provider
