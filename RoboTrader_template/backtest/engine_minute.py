"""
Backtest Minute Engine (T+0 Intraday)
======================================

분봉(T+0 intraday) 백테스트 시뮬레이션. `backtest/engine.py`에서 분리
(2026-07-02 Phase2 god-file split). `_simulate_day_minute`·`run_minute`를
verbatim 이동해 `BacktestMinuteMixin`으로 묶고, `BacktestEngine`이 상속합니다.

주의: 이 Mixin의 메서드는 `self.strategy` · `self.logger` · `self._apply_buy` ·
`self._apply_sell` · `self._get_trading_days_range` · `self._empty_result` ·
`self._calculate_metrics` 등 `BacktestEngine.__init__`에서 만들어지는 속성/메서드에
의존합니다. `BacktestEngine(BacktestMinuteMixin)`으로 상속되어 런타임에 self를
공유하므로, 이 클래스 자체에는 `__init__`을 추가하지 않습니다.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pandas as pd

from strategies.base import BaseStrategy
from backtest.result import BacktestResult


# KS11 일봉 시장환경 필터용 상수 (daily_candles.stock_code 값, 옵션 C 2026-05-19)
# run_minute()의 ORB v2 kospi_market_up 사전로드에서만 사용 (2026-07-02 Phase2에서
# backtest/engine.py로부터 이동 — 이 상수의 유일한 소비처).
KOSPI_CODE = "KS11"


class BacktestMinuteMixin:
    """분봉(T+0 intraday) 백테스트 시뮬레이션 Mixin.

    `BacktestEngine`이 상속해 `self.strategy`/`self.logger`/`self._apply_buy` 등을
    공유합니다(공유 상태는 `BacktestEngine.__init__`에서 초기화됨).
    """

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
