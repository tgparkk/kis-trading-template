"""
[기업행위 의심] 기준가 불연속 경보 — 실전 전용 · 로그/텔레그램만 · 판정 불변

배경(2026-10-10 조사 · 사장님 승인 (d)+(a′)):
  보유 종목이 권리락·분할·병합·감자를 맞으면 평단은 그대로인데 현재가만 뚝 떨어져
  가짜 손절이 난다(페이퍼 000500 2026-06-30 09:05:11 −37.52%). 실전은 그 뒤 신주가
  계좌에 들어온 날 아침 대사(`bot/state_restorer.py` 계좌-DB 수량 불일치)에서
  LiveStartupAbort 로 기동이 멈춘다.
  KIS 현재가 응답의 기준가(`stck_sdpr`, price_service 의 `prev_close`)가 DB 전일종가와
  ±2% 넘게 다르면 「기준가가 조정됐다 = 기업행위」로 보고 **경보만** 낸다.

🔴 이 모듈은 매수·매도 판단·반환값·순서를 **하나도** 바꾸지 않는다. 손익절 보류는
   (a)안(10-16 EOD 뒤 사전등록)이다 — 여기서 하지 말 것.
🔴 페이퍼에선 호출부(`PositionMonitor`)가 먼저 돌려보낸다(DB 조회 0 · 로그 0).

킬 스위치: env `CORP_ACTION_PRICE_ALERT` = `on`(기본) | `off`/`0`/`false`/`no`/`disable`/`disabled`.
  `.env` 는 `config/env_bootstrap.py` 가 읽고 OS env 가 이긴다. 호출 시점에 읽는다.
  모르는 값은 `on` 으로 본다 — 판정을 바꾸지 않는 경보라, 오타로 경보가 조용히
  꺼지는 쪽이 더 위험하다(룰을 바꾸는 `RS_LEADER_CORP_ACTION_MODE` 와 방향이 반대인 이유).
"""
import asyncio
import math
import os
from datetime import date, datetime
from typing import Any, Dict, Optional, Set, Tuple

ALERT_PREFIX = "[기업행위 의심]"
DEFAULT_GAP_THRESHOLD = 0.02
KILL_SWITCH_ENV = "CORP_ACTION_PRICE_ALERT"
_OFF_VALUES = frozenset({"off", "0", "false", "no", "disable", "disabled"})
# 부동소수 오차 흡수 — 정확히 2%(예: 102/100)가 1.0200000000000000178 로 «넘었다» 판정되지 않게.
_EPS = 1e-9
# DB 전일종가 조회 창(달력일). 연휴 최장 ~10일을 덮는다.
_PREV_CLOSE_LOOKBACK_DAYS = 14


def is_alert_enabled(environ: Optional[Dict[str, str]] = None) -> bool:
    """킬 스위치 — `_OFF_VALUES` 일 때만 False (대소문자·앞뒤 공백 무시). 미설정·오타는 on."""
    env = os.environ if environ is None else environ
    raw = env.get(KILL_SWITCH_ENV)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _OFF_VALUES


def detect_base_price_gap(base_price: float, db_prev_close: float,
                          threshold: float = DEFAULT_GAP_THRESHOLD) -> Optional[float]:
    """기준가/DB전일종가 비율이 1±threshold 를 «넘으면» 그 비율, 아니면 None.

    정확히 threshold(2%)는 경보하지 않는다. 0·음수·NaN·숫자 아님 → None.
    """
    try:
        base = float(base_price)
        prev = float(db_prev_close)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(base) and math.isfinite(prev)) or base <= 0 or prev <= 0:
        return None
    ratio = base / prev
    if abs(ratio - 1.0) - threshold > _EPS:
        return ratio
    return None


class DailyOnceAlerter:
    """(거래일, 종목) 키당 하루 1번만 True. 날짜가 바뀌면 지난 키는 버린다."""

    def __init__(self) -> None:
        self._fired: Set[Tuple[date, str]] = set()

    def should_fire(self, trade_date: date, stock_code: str) -> bool:
        key = (trade_date, stock_code)
        if key in self._fired:
            return False
        # 지난 날 키 정리(메모리 무한 증가 방지)
        self._fired = {k for k in self._fired if k[0] == trade_date}
        self._fired.add(key)
        return True


def _would_trigger_exit(profit_rate: float, stop_loss_rate: Any,
                        target_profit_rate: Any) -> bool:
    """`position_monitor` 의 손절(:325-335)·익절(:310-323) 조건을 «읽기만» 따라 한다."""
    try:
        if stop_loss_rate and profit_rate <= -float(stop_loss_rate):
            return True
        if target_profit_rate and float(target_profit_rate) > 0 \
                and profit_rate >= float(target_profit_rate):
            return True
    except (TypeError, ValueError):
        return False
    return False


class CorpActionPriceAlertHook:
    """보유 종목 기준가 불연속 경보 상태(하루 단위 캐시 + 1일 1회 경보).

    - 기준가: `remember_base_price` 가 KIS 현재가 응답에서 받아 둔다(당일 값만 쓴다).
    - DB 전일종가: 종목·거래일당 1번만 조회해 캐시한다. 조회는 **이벤트 루프 밖**
      (기본 executor)에서 돌려 매도 판단 경로를 막지 않는다 — 캐시가 차기 전 틱은
      그냥 넘어간다(다음 틱 ≈3초 뒤 판정).
    """

    def __init__(self, logger: Any, threshold: float = DEFAULT_GAP_THRESHOLD) -> None:
        self.logger = logger
        self.threshold = threshold
        logger.info(f"{ALERT_PREFIX} 경보 활성 (임계 {threshold:.0%} · 킬스위치 {KILL_SWITCH_ENV})")
        self._day: Optional[date] = None
        self._base_prices: Dict[str, float] = {}
        self._prev_closes: Dict[str, Optional[float]] = {}
        self._inflight: Set[str] = set()
        self._gap_alerter = DailyOnceAlerter()
        self._exit_alerter = DailyOnceAlerter()
        self._pending: Set[Any] = set()   # 텔레그램 태스크·조회 future 참조(GC 방지)

    # ------------------------------------------------------------------ 상태
    def _roll_day(self, trade_date: date) -> None:
        if self._day != trade_date:
            self._day = trade_date
            self._base_prices.clear()
            self._prev_closes.clear()
            self._inflight.clear()

    def remember_base_price(self, stock_code: str, base_price: Any, trade_date: date) -> None:
        """KIS 기준가(stck_sdpr) 보관 — 0·이상값은 버린다."""
        self._roll_day(trade_date)
        try:
            value = float(base_price)
        except (TypeError, ValueError):
            return
        if math.isfinite(value) and value > 0:
            self._base_prices[stock_code] = value

    # ------------------------------------------------------------------ DB
    @staticmethod
    def _fetch_prev_close(stock_code: str, trade_date: date,
                          price_repo: Any) -> Tuple[Optional[float], Optional[str]]:
        """daily_prices 의 «직전 거래일» 종가(읽기 전용) → (종가, 생략 사유).

        날짜가 직전 거래일과 다르면(DB 가 밀림) 종가 None — 엉뚱한 날과 비교한 오경보 방지.
        executor 스레드에서 돌므로 이 함수는 로그를 남기지 않고 사유만 돌려준다. 단 `price_repo.get_daily_prices`
        는 DB 오류 때 자체적으로 ERROR(`일봉 데이터 조회 실패`)를 이 스레드에서 남기고 빈 DataFrame 을 돌려준다.
        """
        from utils.korean_holidays import get_previous_trading_day
        df = price_repo.get_daily_prices(stock_code, days=_PREV_CLOSE_LOOKBACK_DAYS)
        if df is None or getattr(df, "empty", True):
            return None, "DB 일봉 없음"
        import pandas as pd
        dates = pd.to_datetime(df["date"]).dt.date
        past = df[(dates < trade_date).values]
        if past.empty:
            return None, "DB 에 오늘 이전 일봉 없음"
        last_date = pd.to_datetime(past["date"].iloc[-1]).date()
        expected = get_previous_trading_day(
            datetime(trade_date.year, trade_date.month, trade_date.day)).date()
        if last_date != expected:
            return None, f"DB 최근 종가일 {last_date} ≠ 직전 거래일 {expected}"
        close = float(past["close"].iloc[-1])
        if not (math.isfinite(close) and close > 0):
            return None, f"DB 전일종가 이상값 {close}"
        return close, None

    def _prev_close_nonblocking(self, stock_code: str, trade_date: date,
                                price_repo: Any) -> Optional[float]:
        if stock_code in self._prev_closes:
            return self._prev_closes[stock_code]
        if price_repo is None:
            self._prev_closes[stock_code] = None   # 그날 1번만 남긴다
            self.logger.warning(f"기준가 점검 생략(경보 못 봄): {stock_code} price_repo 없음")
            return None
        if stock_code in self._inflight:
            return None
        loop = asyncio.get_running_loop()
        self._inflight.add(stock_code)
        fut = loop.run_in_executor(None, self._fetch_prev_close, stock_code, trade_date, price_repo)
        self._pending.add(fut)

        def _done(f: Any, code: str = stock_code, day: date = trade_date) -> None:
            self._pending.discard(f)
            if self._day != day:
                return  # 날이 바뀐 뒤 도착한 결과는 버린다
            self._inflight.discard(code)
            # 실패·생략도 그날은 캐시한다(DB 를 3초마다 두드리지 않는다) — 사유는 1번만 남는다.
            try:
                value, note = f.result()
            except Exception as e:
                value, note = None, f"DB 전일종가 조회 실패: {e}"
            self._prev_closes[code] = value
            if note:
                self.logger.warning(f"기준가 점검 생략(경보 못 봄): {code} {note}")

        fut.add_done_callback(_done)
        return None

    # ------------------------------------------------------------------ 경보
    def _send_telegram(self, telegram: Any, message: str) -> None:
        """기존 경로(`TelegramIntegration.notify_system_status`)로 «보내고 잊기». 기다리지 않는다."""
        notify = getattr(telegram, "notify_system_status", None) if telegram is not None else None
        if notify is None:
            return
        task = asyncio.get_running_loop().create_task(notify(message))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def check(self, *, trade_date: date, stock_code: str, stock_name: str,
              quantity: Any, avg_price: Any, profit_rate: float,
              stop_loss_rate: Any, target_profit_rate: Any,
              price_repo: Any, telegram: Any) -> Optional[float]:
        """기준가 불연속이면 비율을 돌려주고(경보는 하루 1번), 아니면 None."""
        self._roll_day(trade_date)
        base = self._base_prices.get(stock_code)
        if base is None:
            return None
        db_prev = self._prev_close_nonblocking(stock_code, trade_date, price_repo)
        if db_prev is None:
            return None
        ratio = detect_base_price_gap(base, db_prev, self.threshold)
        if ratio is None:
            return None

        name = f" {stock_name}" if stock_name else ""
        if self._gap_alerter.should_fire(trade_date, stock_code):
            self.logger.warning(
                f"{ALERT_PREFIX} {stock_code}{name} 기준가 {base:,.0f}원 vs DB 전일종가 "
                f"{db_prev:,.0f}원 (비율 {ratio:.4f}) 보유 {quantity}주 평단 {float(avg_price):,.0f}원 "
                f"— 권리락·분할·병합·감자 가능성 · 판정은 그대로(경보 전용)"
            )
            self._send_telegram(telegram, (
                f"🚨 기업행위 의심 — {stock_code}{name}\n"
                f"기준가 {base:,.0f}원 / DB 전일종가 {db_prev:,.0f}원 (비율 {ratio:.4f})\n"
                f"보유 {quantity}주 · 평단 {float(avg_price):,.0f}원\n"
                f"권리락·분할·병합·감자 가능성. 손익절 판정은 그대로 진행됨(경보 전용) — 수동 확인"
            ))

        if _would_trigger_exit(profit_rate, stop_loss_rate, target_profit_rate) \
                and self._exit_alerter.should_fire(trade_date, stock_code):
            self.logger.warning(
                f"{ALERT_PREFIX} {stock_code}{name} 손절/익절 조건 도달(09:05 전이면 손절은 유예 중 — 곧 실행될 수 있음) · 기업행위 때문일 수 있음 — 수동 확인 "
                f"(수익률 {profit_rate:.2%} · 기준가/전일종가 {ratio:.4f})"
            )
            self._send_telegram(telegram, (
                f"🚨 기업행위 의심 — {stock_code}{name}\n"
                f"손절/익절 조건 도달(09:05 전이면 손절은 유예 중 — 곧 실행될 수 있음) — 기업행위 때문일 수 있음, 수동 확인\n"
                f"신주·수량 변경 입고일 아침 실전 기동 중단 가능\n"
                f"수익률 {profit_rate:.2%} · 기준가/전일종가 {ratio:.4f}"
            ))
        return ratio
