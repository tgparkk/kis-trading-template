"""포트폴리오 백테스트 엔진 — Phase 4.

단일 종목 PIT 엔진(Phase 2) 위에 포트폴리오 레이어를 얹는다.

루프 불변 순서 (매 거래일 D):
  1. PIT 컨텍스트 (as_of_date=D)
  2. 보유 포지션 청산 검사:
     - holding_cap.should_force_exit_by_age → 강제 청산 (다음 거래일 시가)
     - exit_rule.should_exit → 청산
     - 일중 TP/SL은 일봉 high/low로 시뮬 (pit_engine 패턴 재사용)
  3. 리밸런싱 일이면:
     - Universe.select(ctx) → corp_events.filter_universe 자동 적용
     - scorer.score → max_positions개 선정
     - 현재 포지션 차집합 → 사라진 종목은 다음 거래일 시가 매도,
       새로 들어온 종목은 다음 거래일 시가 매수 (regime + signal_gen 통과 필요)
  4. 일별 평가금 기록: cash + sum(position.qty * close)
  5. 포트폴리오 스톱:
     - daily PnL ≤ portfolio_pause_pct → 다음날 신규 진입 차단
     - daily PnL ≤ portfolio_stop_pct → 다음 거래일 시가 전량 청산
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import psycopg2

from RoboTrader_template.multiverse.data import corp_events as _corp_events
from RoboTrader_template.multiverse.data import pit_reader
from RoboTrader_template.multiverse.data.pit_reader import backtest_session
from RoboTrader_template.multiverse.engine.pit_engine import (
    BUY_FEE_BPS,
    SELL_FEE_BPS,
    Trade,
    PITContext,
    _calc_exec_price_and_fee,
    _is_limit_up_down,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# 데이터클래스
# ------------------------------------------------------------------ #

@dataclass
class PortfolioPosition:
    symbol: str
    qty: int
    entry_price: float
    entry_date: date
    held_days: int = 0      # 매일 +1
    atr_at_entry: float | None = None
    lock_step: int = 0
    paramset_id: str = ""
    trailing_high: float = 0.0  # 트레일링 스톱용 포지션 진입 후 최고가 추적


@dataclass
class PortfolioBacktestResult:
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    daily_equity: List[Tuple[date, float]]   # 평가금 시계열
    trades: List[Trade]                       # Phase 2의 Trade 재사용
    skipped_signals: List[Tuple[date, str, str]]  # (date, symbol, reason)
    rebalance_dates: List[date]               # 리밸런싱이 실제 트리거된 날짜
    paramset_id: str
    paused_until: date | None                 # portfolio_pause로 차단 중이면 마지막 차단 종료일
    precision: float = 0.0                   # 신호 → 라벨 양성(+5% 도달) 비율 (0~1)
    expectancy: float = 0.0                  # 거래당 평균 손익 (원)


# ------------------------------------------------------------------ #
# 내부 헬퍼
# ------------------------------------------------------------------ #

def _get_portfolio_trading_dates(
    start_date: date,
    end_date: date,
    candidate_symbols: list[str],
) -> List[date]:
    """start_date ~ end_date 사이 거래일 목록 반환.

    모든 후보 종목의 거래일 합집합을 단일 SELECT DISTINCT 쿼리로 조회.
    read_daily() 루프 제거 — 종목마다 DataFrame 생성 + 신규 연결 비용 없음.
    빈 결과 시 평일 fallback.
    """
    import pandas as pd

    if candidate_symbols:
        sql = r"""
            SELECT DISTINCT date
            FROM daily_prices
            WHERE stock_code = ANY(%(symbols)s)
              AND date BETWEEN %(start_date)s AND %(end_date)s
              AND date::text ~ '^\d{4}-\d{2}-\d{2}$'
            ORDER BY date
        """
        try:
            conn = psycopg2.connect(
                **pit_reader._QUANT_DB_DEFAULTS,
                database=pit_reader._QUANT_DB,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        dict(
                            symbols=candidate_symbols,
                            start_date=start_date.isoformat(),
                            end_date=end_date.isoformat(),
                        ),
                    )
                    rows = cur.fetchall()
                conn.commit()
            finally:
                conn.close()

            dates = [r[0] if isinstance(r[0], date) else r[0].date() for r in rows]
            dates = sorted(dates)
            if dates:
                return dates
        except Exception as exc:
            logger.warning(
                "[portfolio_engine] _get_portfolio_trading_dates DB 조회 실패, fallback 사용: %s", exc
            )

    # fallback: 평일 목록
    days = pd.bdate_range(start=start_date, end=end_date)
    return [d.date() for d in days if start_date <= d.date() <= end_date]


def _should_rebalance(trade_date: date, frequency: str, prev_date: date | None) -> bool:
    """리밸런싱 주기 판단.

    frequency:
      - "daily": 매 거래일
      - "weekly": 월요일(또는 그 주 첫 거래일)
      - "biweekly": 격주 월요일
      - "monthly": 매월 첫 거래일
    """
    if frequency == "daily":
        return True

    if frequency == "weekly":
        # 이전 거래일과 weekday가 다른 주 또는 월요일이 오늘
        if prev_date is None:
            return True
        # 이전 거래일과 이번 거래일이 다른 주 (ISO week 기준)
        return trade_date.isocalendar()[1] != prev_date.isocalendar()[1]

    if frequency == "biweekly":
        if prev_date is None:
            return True
        prev_week = prev_date.isocalendar()[1]
        curr_week = trade_date.isocalendar()[1]
        if prev_week == curr_week:
            return False
        # 주가 바뀐 경우 홀수 주에만 트리거
        return curr_week % 2 == 1

    if frequency == "monthly":
        if prev_date is None:
            return True
        # 이전 거래일과 월이 다르면 해당 월의 첫 거래일
        return trade_date.month != prev_date.month

    return True  # 알 수 없는 frequency는 매일 리밸런싱


def _prev_close_price(symbol: str, trade_date: date) -> Optional[float]:
    """trade_date 직전 거래일 종가 반환."""
    df = pit_reader.read_daily(
        symbol=symbol,
        as_of_date=trade_date,
        lookback_days=5,
    )
    if df.empty:
        return None
    return float(df["close"].iloc[-1])


def _position_to_dict(pos: PortfolioPosition, current_price: Optional[float] = None) -> dict:
    """exit_rule / holding_cap 인터페이스용 dict 변환.

    current_price: 당일 시가(또는 직전 종가). None이면 entry_price로 폴백.
    trailing_high: 트레일링 스톱용 최고가 추적값.
    """
    return {
        "symbol": pos.symbol,
        "qty": pos.qty,
        "entry_price": pos.entry_price,
        "entry_date": pos.entry_date,
        "held_days": pos.held_days,
        "atr_at_entry": pos.atr_at_entry,
        "lock_step": pos.lock_step,
        "current_price": current_price if current_price is not None else pos.entry_price,
        "trailing_high": pos.trailing_high,
    }


# ------------------------------------------------------------------ #
# 메인 엔진
# ------------------------------------------------------------------ #

def run_portfolio_backtest(
    *,
    strategy,                              # ComposableStrategy
    candidate_symbols: list[str],
    start_date: date,
    end_date: date,
    initial_capital: float,
    use_minute: bool = False,
    market_cap_top_pct_map: dict[str, bool] | None = None,
    universe_filter: str = "all",
) -> PortfolioBacktestResult:
    """포트폴리오 백테스트 — 상위 N 종목 동시 보유.

    Parameters
    ----------
    strategy:
        ComposableStrategy 인스턴스 (8 모듈 조립체).
    candidate_symbols:
        후보 풀 종목코드 목록.
    start_date:
        백테스트 시작일.
    end_date:
        백테스트 종료일.
    initial_capital:
        초기 자본 (원).
    use_minute:
        True면 분봉 모드 — 슬리피지 +20bp 추가.
    market_cap_top_pct_map:
        symbol → bool. True면 시총 상위 30% 가정 → 슬리피지 25bp.
    universe_filter:
        "all" (기본값, 기존 동작 유지) 또는 "kospi200_pit".
        "kospi200_pit" 지정 시 리밸런싱 시점마다 KOSPI200 PIT 교집합 필터 적용.
    """
    ps = strategy.paramset
    paramset_id = ps.paramset_id() if hasattr(ps, "paramset_id") else ""
    mkt_map: dict[str, bool] = market_cap_top_pct_map or {}

    trades: List[Trade] = []
    skipped_signals: List[Tuple[date, str, str]] = []
    daily_equity: List[Tuple[date, float]] = []
    rebalance_dates: List[date] = []

    cash = initial_capital
    positions: Dict[str, PortfolioPosition] = {}   # symbol → PortfolioPosition

    # 다음 거래일 시가 대기 주문 큐
    # {"symbol": str, "side": "BUY"|"SELL", "reason": str}
    pending_orders: list[dict] = []

    # portfolio_pause / portfolio_stop 제어
    paused_until: date | None = None
    full_exit_pending: bool = False        # portfolio_stop → 다음 거래일 전량 청산

    # 이전 평가금 (daily PnL 계산용)
    prev_equity: float = initial_capital

    # 리밸런싱 주기 추적
    prev_trade_date: date | None = None

    # precision / expectancy 추적용 내부 누산기
    # symbol → (entry_price, qty, buy_fee, entry_date)
    _entry_tracker: Dict[str, Tuple[float, int, float, date]] = {}
    _pnl_list: List[float] = []           # 거래당 실현 손익 (원)
    _precision_total: int = 0             # precision 분모 (BUY 체결 건수)
    _precision_hits: int = 0             # precision 분자 (entry 당일 고가 ≥ entry*1.05)

    # 패치 #1 (5/9 stall fix): trading_dates 계산을 session 밖으로 — DB 포화 회피
    trading_dates = _get_portfolio_trading_dates(start_date, end_date, candidate_symbols)

    logger.debug(
        "[portfolio_engine] %s~%s — %d 거래일, %d 후보 종목",
        start_date, end_date, len(trading_dates), len(candidate_symbols),
    )

    with backtest_session():  # 단일 DB 연결 재사용 — connect() 비용(~220ms/call) 제거
        return _run_portfolio_loop(
            strategy=strategy,
            candidate_symbols=candidate_symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            use_minute=use_minute,
            market_cap_top_pct_map=market_cap_top_pct_map,
            universe_filter=universe_filter,
            ps=ps,
            paramset_id=paramset_id,
            mkt_map=mkt_map,
            trades=trades,
            skipped_signals=skipped_signals,
            daily_equity=daily_equity,
            rebalance_dates=rebalance_dates,
            cash=cash,
            positions=positions,
            pending_orders=pending_orders,
            paused_until=paused_until,
            full_exit_pending=full_exit_pending,
            prev_equity=prev_equity,
            prev_trade_date=prev_trade_date,
            trading_dates=trading_dates,
            _entry_tracker=_entry_tracker,
            _pnl_list=_pnl_list,
            _precision_total=_precision_total,
            _precision_hits=_precision_hits,
        )


def _run_portfolio_loop(
    *,
    strategy,
    candidate_symbols,
    start_date,
    end_date,
    initial_capital,
    use_minute,
    market_cap_top_pct_map,
    universe_filter,
    ps,
    paramset_id,
    mkt_map,
    trades,
    skipped_signals,
    daily_equity,
    rebalance_dates,
    cash,
    positions,
    pending_orders,
    paused_until,
    full_exit_pending,
    prev_equity,
    prev_trade_date,
    trading_dates,
    _entry_tracker,
    _pnl_list,
    _precision_total,
    _precision_hits,
) -> "PortfolioBacktestResult":
    """거래일 루프 실행 — backtest_session() 컨텍스트 안에서 호출됨."""

    for trade_date in trading_dates:

        # ----------------------------------------------------------
        # 보유 포지션 held_days +1
        # ----------------------------------------------------------
        for pos in positions.values():
            pos.held_days += 1

        # ----------------------------------------------------------
        # 1. portfolio_stop 전량 청산 대기 처리
        # ----------------------------------------------------------
        if full_exit_pending:
            full_exit_pending = False
            for sym in list(positions.keys()):
                pending_orders.append({"symbol": sym, "side": "SELL", "reason": "portfolio_stop"})

        # ----------------------------------------------------------
        # 2. 대기 주문 체결 (오늘 시가)
        # ----------------------------------------------------------
        for order in pending_orders:
            sym = order["symbol"]
            side = order["side"]
            reason = order["reason"]
            is_top30 = mkt_map.get(sym, False)

            open_price = pit_reader.read_open(symbol=sym, date=trade_date)
            if open_price is None:
                skipped_signals.append((trade_date, sym, "no_open_price_for_pending"))
                continue

            prev_close = _prev_close_price(sym, trade_date)

            if side == "SELL":
                if sym not in positions:
                    continue  # 이미 청산됨
                pos = positions[sym]
                exec_price, fee = _calc_exec_price_and_fee(
                    open_price=open_price,
                    prev_close=prev_close,
                    side="SELL",
                    qty=pos.qty,
                    market_cap_top_pct=is_top30,
                    use_minute=use_minute,
                )
                cash += exec_price * pos.qty - fee
                trades.append(Trade(
                    date=trade_date,
                    side="SELL",
                    price=exec_price,
                    qty=pos.qty,
                    fee=fee,
                    reason=reason,
                ))
                logger.debug(
                    "[portfolio_engine] %s %s SELL(pending:%s) qty=%d price=%.2f",
                    trade_date, sym, reason, pos.qty, exec_price,
                )
                # expectancy 추적: 매도 실현 손익 계산
                if sym in _entry_tracker:
                    _ep, _eq, _ef, _ed = _entry_tracker.pop(sym)
                    _pnl_list.append(exec_price * pos.qty - fee - (_ep * _eq + _ef))
                del positions[sym]

            elif side == "BUY":
                if sym in positions:
                    continue  # 이미 보유
                # 진입 가드: 관리종목/거래정지
                if _corp_events.is_administrative(sym, trade_date):
                    skipped_signals.append((trade_date, sym, "administrative"))
                    continue
                if _corp_events.is_halted(sym, trade_date):
                    skipped_signals.append((trade_date, sym, "halted"))
                    continue
                # 상한가/하한가 가드
                if prev_close is not None and _is_limit_up_down(open_price, prev_close):
                    skipped_signals.append((trade_date, sym, "limit_up_or_down"))
                    continue
                # max_positions 상한
                if len(positions) >= ps.max_positions:
                    skipped_signals.append((trade_date, sym, "max_positions_reached"))
                    continue

                exec_price, fee = _calc_exec_price_and_fee(
                    open_price=open_price,
                    prev_close=prev_close,
                    side="BUY",
                    qty=order.get("qty", 10),
                    market_cap_top_pct=is_top30,
                    use_minute=use_minute,
                )
                qty = order.get("qty", 10)
                cost = exec_price * qty + fee
                if cash < cost:
                    skipped_signals.append((trade_date, sym, "insufficient_cash"))
                    continue

                cash -= cost
                positions[sym] = PortfolioPosition(
                    symbol=sym,
                    qty=qty,
                    entry_price=exec_price,
                    entry_date=trade_date,
                    held_days=0,
                    paramset_id=paramset_id,
                )
                trades.append(Trade(
                    date=trade_date,
                    side="BUY",
                    price=exec_price,
                    qty=qty,
                    fee=fee,
                    reason=reason,
                ))
                logger.debug(
                    "[portfolio_engine] %s %s BUY qty=%d price=%.2f",
                    trade_date, sym, qty, exec_price,
                )
                # precision 추적: 매수 당일 고가 ≥ entry_price * 1.05 여부
                _entry_tracker[sym] = (exec_price, qty, fee, trade_date)
                _precision_total += 1
                _buy_high_low = pit_reader.read_high_low(symbol=sym, date=trade_date)
                if _buy_high_low is not None:
                    _buy_high, _ = _buy_high_low
                    if _buy_high >= exec_price * 1.05:
                        _precision_hits += 1

        pending_orders.clear()

        # ----------------------------------------------------------
        # 3. PIT 컨텍스트 생성 (as_of_date=trade_date)
        # ----------------------------------------------------------
        ctx = PITContext(as_of_date=trade_date)

        # ----------------------------------------------------------
        # 4. 보유 포지션 청산 검사 (holding_cap / exit_rule / 일중 TP/SL)
        # ----------------------------------------------------------
        for sym in list(positions.keys()):
            pos = positions[sym]

            open_price = pit_reader.read_open(symbol=sym, date=trade_date)
            high_low = pit_reader.read_high_low(symbol=sym, date=trade_date)

            # trailing_high 갱신: 당일 고가 > 현재 trailing_high 이면 업데이트
            if high_low is not None:
                today_high, _ = high_low
                if today_high > pos.trailing_high:
                    pos.trailing_high = today_high

            # current_price: 당일 시가 우선, 없으면 entry_price 폴백
            pos_dict = _position_to_dict(pos, current_price=open_price)

            # 4a. 보유기간 상한 초과 → 다음 거래일 강제 청산 예약
            if strategy.holding_cap.should_force_exit_by_age(pos_dict, trade_date, strategy.paramset):
                pending_orders.append({"symbol": sym, "side": "SELL", "reason": "holding_cap_exceeded"})
                logger.debug(
                    "[portfolio_engine] %s %s 보유기간 초과 — 다음 거래일 강제 청산 예약",
                    trade_date, sym,
                )
                continue

            # 4b. exit_rule 청산 신호
            should_exit, exit_reason = strategy.exit_rule.should_exit(ctx, pos_dict, strategy.paramset)
            if should_exit:
                pending_orders.append({"symbol": sym, "side": "SELL", "reason": exit_reason or "exit_rule"})
                continue

            # 4c. 일중 TP/SL (일봉 high/low 기준)
            if open_price is not None and high_low is not None:
                high, low = high_low
                # hard_stop_pct 기반 SL 가격 계산
                sl_price = pos.entry_price * (1 + ps.hard_stop_pct) if ps.hard_stop_pct else None

                sl_hit = sl_price is not None and low <= sl_price
                if sl_hit:
                    is_top30 = mkt_map.get(sym, False)
                    prev_close = _prev_close_price(sym, trade_date)
                    fee = sl_price * pos.qty * (SELL_FEE_BPS / 10000)  # type: ignore[operator]
                    cash += sl_price * pos.qty - fee  # type: ignore[operator]
                    trades.append(Trade(
                        date=trade_date,
                        side="SELL",
                        price=sl_price,  # type: ignore[arg-type]
                        qty=pos.qty,
                        fee=fee,
                        reason="stop_loss",
                    ))
                    logger.debug(
                        "[portfolio_engine] %s %s SL 체결 price=%.2f",
                        trade_date, sym, sl_price,
                    )
                    # expectancy 추적: SL 실현 손익 계산
                    if sym in _entry_tracker:
                        _ep, _eq, _ef, _ed = _entry_tracker.pop(sym)
                        _pnl_list.append(sl_price * pos.qty - fee - (_ep * _eq + _ef))  # type: ignore[operator]
                    del positions[sym]

        # ----------------------------------------------------------
        # 5. 리밸런싱 (should_rebalance=True인 날만)
        # ----------------------------------------------------------
        do_rebalance = strategy.rebalancer.should_rebalance(trade_date, strategy.paramset) \
            if hasattr(strategy.rebalancer, "should_rebalance") else \
            _should_rebalance(trade_date, ps.rebalance_frequency, prev_trade_date)

        is_paused = paused_until is not None and trade_date <= paused_until

        if do_rebalance and not is_paused:
            rebalance_dates.append(trade_date)

            # 5a. regime 체크
            regime_ok = strategy.regime.is_risk_on(ctx, strategy.paramset)

            if regime_ok:
                # 5b. Universe 선정 + corp_events 필터
                selected = strategy.universe.select(ctx, strategy.paramset)

                # KOSPI200 PIT 교집합 필터 (universe_filter="kospi200_pit" 시 적용)
                if universe_filter == "kospi200_pit":
                    from RoboTrader_template.multiverse.data.kospi200_pit import get_kospi200_pit
                    kospi200_codes = set(get_kospi200_pit(trade_date))
                    selected = [s for s in selected if s in kospi200_codes]

                # corp_events 자동 필터 적용
                filtered = _corp_events.filter_universe(selected, trade_date)

                # 5c. 스코어 산출 → 상위 max_positions개
                scored: list[tuple[float, str]] = []
                for sym in filtered:
                    score = strategy.scorer.score(ctx, sym, strategy.paramset)
                    scored.append((score, sym))
                scored.sort(key=lambda x: x[0], reverse=True)
                target_symbols = [sym for _, sym in scored[: ps.max_positions]]

                current_symbols = set(positions.keys())
                target_set = set(target_symbols)

                # 사라진 종목 → 다음 거래일 시가 매도
                for sym in current_symbols - target_set:
                    pending_orders.append({"symbol": sym, "side": "SELL", "reason": "rebalance_exit"})

                # 새로 들어온 종목 → regime + signal_gen 통과 시 다음 거래일 시가 매수
                for sym in target_set - current_symbols:
                    # signal_gen 진입 확인
                    try:
                        decision = strategy.signal_gen.generate(ctx, sym, strategy.paramset)
                    except Exception:
                        decision = "HOLD"

                    if decision == "BUY":
                        score = next(
                            (s for s, n in scored if n == sym), 0.0
                        )
                        try:
                            qty = strategy.sizer.size(cash, score, strategy.paramset)
                        except Exception:
                            qty = 10
                        if qty > 0:
                            pending_orders.append({
                                "symbol": sym,
                                "side": "BUY",
                                "qty": qty,
                                "reason": "rebalance_entry",
                            })
                        else:
                            skipped_signals.append((trade_date, sym, "sizer_zero_qty"))
                    else:
                        skipped_signals.append((trade_date, sym, "signal_gen_no_buy"))

        prev_trade_date = trade_date

        # ----------------------------------------------------------
        # 6. 일별 평가금 기록 (close 대신 open 사용 — PIT 원칙)
        # ----------------------------------------------------------
        holdings_value = 0.0
        for sym, pos in positions.items():
            open_price = pit_reader.read_open(symbol=sym, date=trade_date)
            if open_price is not None:
                holdings_value += pos.qty * open_price
            else:
                holdings_value += pos.qty * pos.entry_price

        equity = cash + holdings_value
        daily_equity.append((trade_date, equity))

        # ----------------------------------------------------------
        # 7. 포트폴리오 스톱 / 포즈 판단
        # ----------------------------------------------------------
        if prev_equity > 0:
            daily_pnl_pct = (equity - prev_equity) / prev_equity
        else:
            daily_pnl_pct = 0.0

        if daily_pnl_pct <= ps.portfolio_stop_pct:
            logger.info(
                "[portfolio_engine] %s portfolio_stop 트리거 (daily_pnl=%.4f <= stop=%.4f) — 다음 거래일 전량 청산",
                trade_date, daily_pnl_pct, ps.portfolio_stop_pct,
            )
            full_exit_pending = True

        elif daily_pnl_pct <= ps.portfolio_pause_pct:
            paused_until = trade_date + timedelta(days=1)
            logger.info(
                "[portfolio_engine] %s portfolio_pause 트리거 (daily_pnl=%.4f <= pause=%.4f)",
                trade_date, daily_pnl_pct, ps.portfolio_pause_pct,
            )

        prev_equity = equity

    final_equity = daily_equity[-1][1] if daily_equity else initial_capital

    # precision / expectancy 최종 계산
    _precision_val = _precision_hits / _precision_total if _precision_total > 0 else 0.0
    _expectancy_val = sum(_pnl_list) / len(_pnl_list) if _pnl_list else 0.0

    return PortfolioBacktestResult(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_equity=final_equity,
        daily_equity=daily_equity,
        trades=trades,
        skipped_signals=skipped_signals,
        rebalance_dates=rebalance_dates,
        paramset_id=paramset_id,
        paused_until=paused_until,
        precision=_precision_val,
        expectancy=_expectancy_val,
    )
