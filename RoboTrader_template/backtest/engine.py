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
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE
from strategies.base import BaseStrategy, SignalType


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
    profit_loss_ratio: float
    total_trades: int
    trades: List[Dict]
    equity_curve: List[float]

    def summary(self) -> str:
        """결과 요약 문자열 반환."""
        return (
            f"총수익률={self.total_return:+.2%}  "
            f"승률={self.win_rate:.1%}  "
            f"평균수익={self.avg_profit:+.2%}  "
            f"MDD={self.max_drawdown:.2%}  "
            f"샤프={self.sharpe_ratio:.2f}  "
            f"손익비={self.profit_loss_ratio:.2f}  "
            f"거래={self.total_trades}건"
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
        positions: Dict[str, Dict] = {}  # {stock_code: {qty, entry_price, entry_date}}
        completed_trades: List[Dict] = []
        equity_curve: List[float] = []

        # 전략 상태 초기화
        self.strategy.positions = {}
        self.strategy.daily_trades = 0

        min_len = self.strategy.get_min_data_length()

        for date in all_dates:
            self.strategy.daily_trades = 0  # 일일 거래 카운터 초기화

            # 1) 매도 판단: 보유 종목에 대해 당일 데이터로 신호 확인
            for code in list(positions.keys()):
                df_slice = self._get_data_up_to(daily_data, code, date)
                if df_slice is None or len(df_slice) < min_len:
                    continue

                signal = self.strategy.generate_signal(code, df_slice, timeframe='daily')
                if signal is None:
                    continue

                if signal.is_sell:
                    sell_price = float(df_slice["close"].iloc[-1])
                    pos = positions[code]
                    qty = pos["qty"]

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
                        "entry_price": pos["entry_price"],
                        "exit_price": sell_price,
                        "quantity": qty,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "signal_type": signal.signal_type.value,
                        "reasons": signal.reasons,
                    })

                    del positions[code]
                    if code in self.strategy.positions:
                        del self.strategy.positions[code]

                    self.logger.debug(
                        f"[{date}] 매도: {code} {qty}주 @ {sell_price:,.0f}원 "
                        f"(수익률 {pnl_pct:+.2%})"
                    )

            # 2) 매수 판단: 포지션 여유 있으면 미보유 종목 신호 확인
            available_slots = self.max_positions - len(positions)
            if available_slots > 0:
                for code in stock_codes:
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

        # equity_curve 마지막 값 업데이트 (강제청산 반영)
        if equity_curve and positions:
            equity_curve[-1] = cash

        return self._calculate_metrics(
            completed_trades=completed_trades,
            equity_curve=equity_curve,
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
    ) -> BacktestResult:
        """성과 지표 계산."""
        total_trades = len(completed_trades)
        final_equity = equity_curve[-1] if equity_curve else self.initial_capital
        total_return = (final_equity - self.initial_capital) / self.initial_capital

        if total_trades == 0:
            return BacktestResult(
                total_return=total_return,
                win_rate=0.0,
                avg_profit=0.0,
                max_drawdown=self._calc_mdd(equity_curve),
                sharpe_ratio=0.0,
                profit_loss_ratio=0.0,
                total_trades=0,
                trades=completed_trades,
                equity_curve=equity_curve,
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

        return BacktestResult(
            total_return=total_return,
            win_rate=win_rate,
            avg_profit=avg_profit,
            max_drawdown=mdd,
            sharpe_ratio=sharpe,
            profit_loss_ratio=profit_loss_ratio,
            total_trades=total_trades,
            trades=completed_trades,
            equity_curve=equity_curve,
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

    def _empty_result(self) -> BacktestResult:
        """데이터 없을 때 반환하는 빈 결과."""
        return BacktestResult(
            total_return=0.0,
            win_rate=0.0,
            avg_profit=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            profit_loss_ratio=0.0,
            total_trades=0,
            trades=[],
            equity_curve=[],
        )
