"""PIT 백테스트 엔진 — 단일 종목.

시계열 원칙:
  - T-1 종가까지의 데이터로 Signal 결정 (PIT 강제)
  - T일 시가 체결 (BUY/SELL)
  - T일 일중 TP/SL 시뮬 (고가/저가 기준)
  - 체결 가드: 상한가/하한가, 관리종목/거래정지, 시초가 갭 슬리피지

루프 불변 순서:
  1. PITContext 진입 (as_of_date=D)
  2. signal_fn 호출 → Signal (T-1 종가까지 데이터만 노출)
  3. PITContext 종료
  4. 체결 가드 (상한가/관리종목/거래정지) 통과 시 T일 시가 체결
  5. 일중 TP/SL 시뮬 (T일 high/low)
  6. 일별 평가금 기록
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Literal, Optional, Tuple

from RoboTrader_template.multiverse.data import corp_events as _corp_events
from RoboTrader_template.multiverse.data import pit_reader

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 거래비용 상수
# ------------------------------------------------------------------ #
BUY_FEE_BPS: int = 15       # 매수 수수료 0.15%
SELL_FEE_BPS: int = 245     # 매도 수수료+세금 2.45% (증권거래세 포함)
SLIPPAGE_TOP30_BPS: int = 25    # 시총 상위 30% 슬리피지
SLIPPAGE_OTHER_BPS: int = 50    # 그 외 슬리피지
SLIPPAGE_MINUTE_EXTRA_BPS: int = 20  # 분봉 모드 추가 슬리피지

# 상한가/하한가 기준 비율
LIMIT_UP_DOWN_THRESHOLD: float = 0.30  # ±30%

# 시초가 갭 슬리피지 추가 트리거 기준
GAP_SLIPPAGE_THRESHOLD: float = 0.05   # ±5% 초과 시 적용


# ------------------------------------------------------------------ #
# 데이터클래스
# ------------------------------------------------------------------ #

@dataclass(frozen=True)
class Signal:
    """전략이 T-1 종가 시점에 만들어 T일 액션을 지시하는 시그널.

    T-1 종가까지의 데이터만으로 결정됨(PIT 강제).
    """
    action: Literal["BUY", "SELL", "HOLD"]
    qty: int = 0
    take_profit: Optional[float] = None   # 일중 TP 가격 (고가 도달 시 체결)
    stop_loss: Optional[float] = None     # 일중 SL 가격 (저가 도달 시 체결)


@dataclass(frozen=True)
class Trade:
    date: date
    side: Literal["BUY", "SELL"]
    price: float
    qty: int
    fee: float  # 거래비용+슬리피지 합산 (원)
    reason: str  # "signal" / "take_profit" / "stop_loss" / "halted_force_exit" / "administrative_force_exit"


@dataclass
class BacktestResult:
    symbol: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    daily_equity: List[Tuple[date, float]]  # 날짜별 평가금
    trades: List[Trade]
    skipped_signals: List[Tuple[date, str]]  # (날짜, 사유)


# ------------------------------------------------------------------ #
# PITContext
# ------------------------------------------------------------------ #

class PITContext:
    """signal_fn에 전달되는 PIT 강제 컨텍스트.

    내부에서 pit_reader / corp_events 호출 시 자동으로 as_of_date 주입.
    의사결정에는 T-1 종가까지의 데이터만 노출됨.
    """

    def __init__(self, as_of_date: date) -> None:
        self.as_of_date = as_of_date

    def read_daily(self, symbol: str, lookback_days: int = 252):
        """T-1 종가까지의 일봉 OHLCV DataFrame 반환."""
        return pit_reader.read_daily(
            symbol=symbol,
            as_of_date=self.as_of_date,
            lookback_days=lookback_days,
        )

    def read_minute(self, symbol: str, as_of_time, lookback_minutes: int = 390):
        """T일 as_of_time 직전 분봉까지 반환."""
        return pit_reader.read_minute(
            symbol=symbol,
            as_of_date=self.as_of_date,
            as_of_time=as_of_time,
            lookback_minutes=lookback_minutes,
        )

    def read_financial_ratio(self, symbol: str):
        """분기재무비율 (공시 lag 60일 적용) 반환."""
        return pit_reader.read_financial_ratio(
            symbol=symbol,
            as_of_date=self.as_of_date,
        )

    def is_administrative(self, symbol: str) -> bool:
        """관리종목 여부 (as_of_date 기준)."""
        return _corp_events.is_administrative(symbol, self.as_of_date)

    def is_halted(self, symbol: str) -> bool:
        """거래정지 여부 (as_of_date 기준)."""
        return _corp_events.is_halted(symbol, self.as_of_date)


# ------------------------------------------------------------------ #
# 내부 헬퍼
# ------------------------------------------------------------------ #

def _get_trading_dates(start_date: date, end_date: date, symbol: str) -> List[date]:
    """start_date ~ end_date 사이 거래일 목록 반환.

    pit_reader.read_daily 의 date 컬럼을 활용.
    데이터가 없으면 start~end 의 평일 목록을 fallback.
    """
    import pandas as pd
    # end_date 이후로 충분한 lookback — 5년치 이상
    lookback = (end_date - start_date).days + 10
    df = pit_reader.read_daily(
        symbol=symbol,
        as_of_date=end_date,
        lookback_days=lookback,
    )

    dates: List[date] = []

    if not df.empty:
        dates = [d for d in df["date"].tolist() if start_date <= d <= end_date]
        dates.sort()

    if not dates:
        # fallback: 평일 목록 (데이터 없거나 범위 내 날짜가 없는 경우)
        days = pd.bdate_range(start=start_date, end=end_date)
        return [d.date() for d in days if start_date <= d.date() <= end_date]

    # end_date 자체 포함 — pit_reader는 as_of_date 미만만 반환하므로
    # end_date 당일 데이터는 빠짐. end_date 를 단순 추가(체결/평가 불가면 무시).
    if dates and dates[-1] < end_date:
        # end_date 가 거래일인지 알 수 없으므로 포함 시도 — open/high_low 조회 실패 시 스킵
        dates.append(end_date)

    return dates


def _prev_close(symbol: str, trade_date: date) -> Optional[float]:
    """trade_date 직전 거래일 종가 반환."""
    df = pit_reader.read_daily(
        symbol=symbol,
        as_of_date=trade_date,
        lookback_days=5,
    )
    if df.empty:
        return None
    return float(df["close"].iloc[-1])


def _calc_exec_price_and_fee(
    open_price: float,
    prev_close: Optional[float],
    side: Literal["BUY", "SELL"],
    qty: int,
    market_cap_top_pct: bool,
    use_minute: bool,
) -> Tuple[float, float]:
    """체결 가격 및 수수료 계산.

    Returns
    -------
    (exec_price, fee)
    """
    slippage_bps = SLIPPAGE_TOP30_BPS if market_cap_top_pct else SLIPPAGE_OTHER_BPS
    if use_minute:
        slippage_bps += SLIPPAGE_MINUTE_EXTRA_BPS

    # 시초가 갭 슬리피지 추가
    if prev_close is not None and prev_close > 0:
        gap_pct = (open_price - prev_close) / prev_close
        if abs(gap_pct) > GAP_SLIPPAGE_THRESHOLD:
            slippage_bps += abs(gap_pct) * 0.5 * 10000  # bps 환산

    if side == "BUY":
        exec_price = open_price * (1 + slippage_bps / 10000)
        fee = exec_price * qty * (BUY_FEE_BPS / 10000)
    else:
        exec_price = open_price * (1 - slippage_bps / 10000)
        fee = exec_price * qty * (SELL_FEE_BPS / 10000)

    return exec_price, fee


def _is_limit_up_down(open_price: float, prev_close: float) -> bool:
    """T일 시가가 T-1 종가 대비 ±30% 도달 여부."""
    if prev_close <= 0:
        return False
    gap = abs((open_price - prev_close) / prev_close)
    return gap >= LIMIT_UP_DOWN_THRESHOLD


# ------------------------------------------------------------------ #
# 메인 엔진
# ------------------------------------------------------------------ #

def run_backtest(
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    initial_capital: float,
    signal_fn: Callable[[PITContext], Signal],
    use_minute: bool = False,
    market_cap_top_pct: bool = False,
) -> BacktestResult:
    """D-N→D 시계열 순회 강제. 셔플 절대 금지.

    각 거래일 D에 대해:
      1. PITContext 진입 (as_of_date=D)
      2. signal_fn 호출 → Signal 결정 (T-1 종가까지의 데이터만 노출)
      3. PITContext 종료
      4. 체결 가드 통과 시 T일 시가 체결
      5. 일중 TP/SL 시뮬 (T일 high/low)
      6. 일별 평가금 기록

    Parameters
    ----------
    symbol:
        종목코드 (예: '005930')
    start_date:
        백테스트 시작일 (거래일 기준)
    end_date:
        백테스트 종료일 (거래일 기준)
    initial_capital:
        초기 자본 (원)
    signal_fn:
        전략 콜백. PITContext → Signal. T-1 종가까지의 데이터만 접근 가능.
    use_minute:
        True면 분봉 모드 — 슬리피지 +20bp 추가
    market_cap_top_pct:
        True면 시총 상위 30% 가정 → 슬리피지 25bp (False면 50bp)
    """
    trades: List[Trade] = []
    skipped_signals: List[Tuple[date, str]] = []
    daily_equity: List[Tuple[date, float]] = []

    cash = initial_capital
    position_qty: int = 0
    position_price: float = 0.0  # 평균 진입 단가

    # 현재 보유 포지션에 연결된 TP/SL (마지막 BUY Signal 기준)
    active_tp: Optional[float] = None
    active_sl: Optional[float] = None

    # 관리종목/거래정지로 인한 강제 청산 대기 플래그
    pending_force_exit: Optional[str] = None  # "administrative_force_exit" or "halted_force_exit"

    # 거래일 목록 확보 (시계열 순서 강제)
    trading_dates = _get_trading_dates(start_date, end_date, symbol)

    logger.debug(
        "[pit_engine] %s %s~%s — %d 거래일",
        symbol, start_date, end_date, len(trading_dates),
    )

    for trade_date in trading_dates:
        # ----------------------------------------------------------
        # 1. 시가 / 고저가 조회
        # ----------------------------------------------------------
        open_price = pit_reader.read_open(symbol=symbol, date=trade_date)
        high_low = pit_reader.read_high_low(symbol=symbol, date=trade_date)

        if open_price is None:
            # 해당 날짜 데이터 없음 — 평가금만 기록
            equity = cash + position_qty * position_price
            daily_equity.append((trade_date, equity))
            continue

        prev_close = _prev_close(symbol, trade_date)

        # ----------------------------------------------------------
        # 2. 강제 청산 대기 처리 (B3 — 전 날 관리종목/거래정지 편입 → 오늘 시가 청산)
        # ----------------------------------------------------------
        if pending_force_exit is not None and position_qty > 0:
            exec_price, fee = _calc_exec_price_and_fee(
                open_price=open_price,
                prev_close=prev_close,
                side="SELL",
                qty=position_qty,
                market_cap_top_pct=market_cap_top_pct,
                use_minute=use_minute,
            )
            cash += exec_price * position_qty - fee
            trades.append(Trade(
                date=trade_date,
                side="SELL",
                price=exec_price,
                qty=position_qty,
                fee=fee,
                reason=pending_force_exit,
            ))
            logger.info(
                "[pit_engine] %s %s 강제청산(%s) qty=%d price=%.2f",
                symbol, trade_date, pending_force_exit, position_qty, exec_price,
            )
            position_qty = 0
            position_price = 0.0
            active_tp = None
            active_sl = None
            pending_force_exit = None

        # ----------------------------------------------------------
        # 3. 관리종목/거래정지 체크 (오늘 시점 — 다음 거래일 강제청산 예약)
        # ----------------------------------------------------------
        is_admin = _corp_events.is_administrative(symbol, trade_date)
        is_halt = _corp_events.is_halted(symbol, trade_date)

        if (is_admin or is_halt) and position_qty > 0:
            reason = "administrative_force_exit" if is_admin else "halted_force_exit"
            pending_force_exit = reason
            logger.info(
                "[pit_engine] %s %s — 관리종목/거래정지 감지, 다음 거래일 강제청산 예약",
                symbol, trade_date,
            )

        # ----------------------------------------------------------
        # 4. PITContext → signal_fn 호출 (as_of_date=trade_date)
        #    신호 결정 단계 — T-1 종가까지의 데이터만 노출
        # ----------------------------------------------------------
        ctx = PITContext(as_of_date=trade_date)

        try:
            signal = signal_fn(ctx)
        except Exception as exc:
            logger.warning(
                "[pit_engine] %s %s signal_fn 오류: %s",
                symbol, trade_date, exc,
            )
            signal = Signal(action="HOLD")

        # ----------------------------------------------------------
        # 5. 체결 가드 + 시가 체결
        # ----------------------------------------------------------
        if signal.action == "BUY" and signal.qty > 0 and position_qty == 0:
            # B3: 관리종목/거래정지 매수 거부
            if is_admin:
                skipped_signals.append((trade_date, "administrative"))
                logger.debug("[pit_engine] %s %s BUY 거부 — 관리종목", symbol, trade_date)
            elif is_halt:
                skipped_signals.append((trade_date, "halted"))
                logger.debug("[pit_engine] %s %s BUY 거부 — 거래정지", symbol, trade_date)
            # B2: 상한가/하한가 ±30% 매수 거부
            elif prev_close is not None and _is_limit_up_down(open_price, prev_close):
                skipped_signals.append((trade_date, "limit_up_or_down"))
                logger.debug(
                    "[pit_engine] %s %s BUY 거부 — 상/하한가 (open=%.2f prev_close=%.2f)",
                    symbol, trade_date, open_price, prev_close,
                )
            else:
                # 정상 매수 체결
                exec_price, fee = _calc_exec_price_and_fee(
                    open_price=open_price,
                    prev_close=prev_close,
                    side="BUY",
                    qty=signal.qty,
                    market_cap_top_pct=market_cap_top_pct,
                    use_minute=use_minute,
                )
                cost = exec_price * signal.qty + fee
                if cash >= cost:
                    cash -= cost
                    position_qty = signal.qty
                    position_price = exec_price
                    active_tp = signal.take_profit
                    active_sl = signal.stop_loss
                    trades.append(Trade(
                        date=trade_date,
                        side="BUY",
                        price=exec_price,
                        qty=signal.qty,
                        fee=fee,
                        reason="signal",
                    ))
                    logger.debug(
                        "[pit_engine] %s %s BUY qty=%d price=%.2f fee=%.2f",
                        symbol, trade_date, signal.qty, exec_price, fee,
                    )
                else:
                    skipped_signals.append((trade_date, "insufficient_cash"))

        elif signal.action == "SELL" and position_qty > 0:
            # SELL 신호 — 상/하한가라도 종가 기준 처리 (명세 B2)
            # 시가 체결 시도 (관리종목이어도 SELL은 허용)
            exec_price, fee = _calc_exec_price_and_fee(
                open_price=open_price,
                prev_close=prev_close,
                side="SELL",
                qty=position_qty,
                market_cap_top_pct=market_cap_top_pct,
                use_minute=use_minute,
            )
            cash += exec_price * position_qty - fee
            trades.append(Trade(
                date=trade_date,
                side="SELL",
                price=exec_price,
                qty=position_qty,
                fee=fee,
                reason="signal",
            ))
            logger.debug(
                "[pit_engine] %s %s SELL qty=%d price=%.2f fee=%.2f",
                symbol, trade_date, position_qty, exec_price, fee,
            )
            position_qty = 0
            position_price = 0.0
            active_tp = None
            active_sl = None

        # ----------------------------------------------------------
        # 6. 일중 TP/SL 시뮬 (B6)
        # ----------------------------------------------------------
        if position_qty > 0 and high_low is not None:
            high, low = high_low

            tp_hit = active_tp is not None and high >= active_tp
            sl_hit = active_sl is not None and low <= active_sl

            if sl_hit or tp_hit:
                # SL 우선 (보수적)
                if sl_hit:
                    exit_price = active_sl  # type: ignore[assignment]
                    reason = "stop_loss"
                else:
                    exit_price = active_tp  # type: ignore[assignment]
                    reason = "take_profit"

                _, fee = _calc_exec_price_and_fee(
                    open_price=exit_price,
                    prev_close=open_price,  # 갭 슬리피지 기준은 시가로
                    side="SELL",
                    qty=position_qty,
                    market_cap_top_pct=market_cap_top_pct,
                    use_minute=use_minute,
                )
                # exit_price 에는 슬리피지 이미 없음 (가격 자체가 TP/SL 수준)
                # fee만 SELL_FEE_BPS 기반으로 적용
                fee = exit_price * position_qty * (SELL_FEE_BPS / 10000)
                cash += exit_price * position_qty - fee
                trades.append(Trade(
                    date=trade_date,
                    side="SELL",
                    price=exit_price,
                    qty=position_qty,
                    fee=fee,
                    reason=reason,
                ))
                logger.debug(
                    "[pit_engine] %s %s %s qty=%d price=%.2f fee=%.2f",
                    symbol, trade_date, reason.upper(), position_qty, exit_price, fee,
                )
                position_qty = 0
                position_price = 0.0
                active_tp = None
                active_sl = None

        # ----------------------------------------------------------
        # 7. 일별 평가금 기록
        # ----------------------------------------------------------
        if position_qty > 0 and high_low is not None:
            # 보유 중 — 종가(high/low 평균 근사 대신 open_price 사용, 종가 미노출)
            # 실제 종가 미조회 (PIT 원칙) — open_price 로 mark
            equity = cash + position_qty * open_price
        elif position_qty > 0:
            equity = cash + position_qty * position_price
        else:
            equity = cash

        daily_equity.append((trade_date, equity))

    # 최종 평가금 — 마지막 daily_equity
    final_equity = daily_equity[-1][1] if daily_equity else initial_capital

    return BacktestResult(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_equity=final_equity,
        daily_equity=daily_equity,
        trades=trades,
        skipped_signals=skipped_signals,
    )
