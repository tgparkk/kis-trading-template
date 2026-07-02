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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE, TRAILING_STOP_CALLBACK_RATE
from strategies.base import BaseStrategy, SignalType
from backtest import metrics
from backtest.result import BacktestResult  # noqa: F401
from backtest.engine_minute import BacktestMinuteMixin, KOSPI_CODE  # noqa: F401


# ============================================================================
# 백테스트 엔진
# ============================================================================

class BacktestEngine(BacktestMinuteMixin):
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

    # 하위호환 별칭: 본문은 backtest/metrics.py로 이동(2026-07-02 Phase2).
    # BacktestEngine._calc_* / self._calc_* 호출부(내부·테스트·연구) 무수정 보존.
    _calc_mdd = staticmethod(metrics.calc_mdd)
    _calc_sharpe = staticmethod(metrics.calc_sharpe)
    _calc_calmar = staticmethod(metrics.calc_calmar)
    _calc_sortino = staticmethod(metrics.calc_sortino)

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


# ============================================================================
# 헬퍼 팩토리: screener_snapshots DB 기반 candidate_provider 생성
# core/screener_snapshot_provider.py로 승격됨 (2026-07-02 Phase2).
# 운영 코드(core/candidate_selector.py)는 새 경로로 직접 import하며,
# 아래는 연구/테스트 호환을 위한 re-export만 유지.
# ============================================================================

from core.screener_snapshot_provider import make_screener_snapshot_provider  # noqa: E402,F401
