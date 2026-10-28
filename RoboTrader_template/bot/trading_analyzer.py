"""
매매 분석 모듈
매수/매도 판단 분석 로직을 담당합니다.
"""
import os
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Optional, Set, Tuple

from core.models import StockState
from config.constants import CANDIDATE_MIN_DAILY_DATA

from utils.logger import setup_logger
from utils.rate_limited_logger import RateLimitedLogger

if TYPE_CHECKING:
    from main import DayTradingBot


# 거절 로그 스로틀 창 — 같은 (종목, 사유) 는 이 간격에 1회만 INFO.
# 근거: 2026-08-19 라이브에서 '시장급락 매수차단' 이 하루 ~2,900회 발생했다.
# 마커 제외 목록만으로는 못 막는다(사유가 늘 때마다 목록을 고쳐야 하고,
# 무엇이 폭주할지는 사전에 모른다) → 창 기반 스로틀이 일반해다.
# 선례: strategies/base.py:549 `_should_log_ontick` (동일 간격·동일 키 구조).
REJECT_LOG_INTERVAL = timedelta(minutes=10)

# 스로틀을 «통과해도» INFO 로 안 올리는 사유. 라이브에서는
# '조건미충족'(core/trading_decision_engine.py:393)이 도달 불가다
# (TradingContext.buy 는 BUY 신호일 때만 부른다) — 그래도 백테/단일전략 경로가
# 이 문자열을 만들 수 있어 남겨 둔다. 비용이 없는 방어층이다.
HIGH_FREQUENCY_REJECT_MARKERS = ("조건미충족",)


def _is_high_frequency_reject(buy_reason) -> bool:
    """거절 사유가 고빈도 사유면 True (INFO 승격 대상에서 제외)."""
    text = str(buy_reason or "")
    return any(marker in text for marker in HIGH_FREQUENCY_REJECT_MARKERS)


def _reject_now() -> datetime:
    """스로틀 기준 시계 (테스트에서 갈아끼우는 이음매)."""
    return datetime.now()


def reject_throttle_key(stock_code: str, buy_reason) -> Tuple[str, str]:
    """스로틀 키 = (종목코드, 사유 «접두»).

    사유 문자열에는 가격·비율 같은 가변부가 붙는다
    (``... 스킵 (현재가 49,000 < 하한 50,000)``, ``... (KOSPI -5.29%)``).
    괄호 앞까지만 잘라 «같은 종류의 거절» 이 같은 키가 되게 한다. 그러지 않으면
    가격이 1틱만 달라져도 새 키가 되어 스로틀이 통째로 무력화된다.
    """
    text = str(buy_reason or "").strip()
    prefix = f"{stock_code} "
    if text.startswith(prefix):
        text = text[len(prefix):]
    head = text.split("(", 1)[0].strip()
    return (str(stock_code), (head or text)[:60])


def format_reject_log(stock_code: str, buy_reason) -> str:
    """거절 로그 한 줄: ``[매수거절] {stock_code} {사유}``.

    엔진 사유는 대부분 이미 ``"{code} ..."`` 로 시작한다
    (core/trading_decision_engine.py:356-429). 그대로 앞에 코드를 또 붙이면
    ``005930 005930 ...`` 이 되므로 «중복될 때만» 앞머리를 떼어낸다. 반대로
    코드가 없는 사유(예외 경로의 ``str(e)``)에는 코드가 반드시 붙는다 —
    종목 없는 거절 줄은 사후 추적에 쓸모가 없다.
    """
    text = str(buy_reason or "").strip()
    prefix = f"{stock_code} "
    if text.startswith(prefix):
        text = text[len(prefix):]
    return f"[매수거절] {stock_code} {text}".rstrip()


# ---------------------------------------------------------------------------
# [재매수-shadow] 로그 (10-29 창구 묶음 A ⑤ · 매매 동작 0)
#   10-22 패널 🔒 「측정 먼저」 — 판 종목을 다시 사는 건을 «기록만» 한다.
#   사전등록 docs/prereg_2026-10-28_window1_shadow_logs.md · 롤백 = env REBUY_SHADOW=off.
#   🔒 SR1: 손절 뒤(또는 사유를 모르는 손실 매도 뒤) 재매수는 매수가비 칸 «-».
# ---------------------------------------------------------------------------
REBUY_SHADOW_CACHE_TTL = timedelta(minutes=10)
_REBUY_SHADOW_OFF = ("off", "0", "false")


def _rebuy_shadow_now() -> datetime:
    """[재매수-shadow] 기준 시계 (테스트에서 갈아끼우는 이음매)."""
    from utils.korean_time import now_kst
    return now_kst()


def rebuy_shadow_enabled() -> bool:
    """env REBUY_SHADOW — 기본 on, off|0|false 면 조회·로그 전부 끔."""
    return os.environ.get("REBUY_SHADOW", "on").strip().lower() not in _REBUY_SHADOW_OFF


def classify_sell_reason(reason) -> str:
    """매도 사유 문자열 → 익절 / 손절 / MA20 이탈 / EMA 이탈 / 기타 (로그 분류 전용)."""
    text = str(reason or "")
    if "손절" in text:
        return "손절"
    if "익절" in text:
        return "익절"
    if "EMA" in text:
        return "EMA 이탈"
    m = re.search(r"(?<!E)MA(\d+)[^가-힣]*이탈", text)
    if m:
        return f"MA{m.group(1)} 이탈"
    return "기타"


def rebuy_trading_days_ago(sell_date, today, trading_dates) -> int:
    """매도일 → 오늘까지 KOSPI 거래일 차(같은 날 0 · 직전 거래일 1 …)."""
    if sell_date >= today:
        return 0
    return sum(1 for d in trading_dates if d >= sell_date)


def format_rebuy_shadow_line(code: str, strategy_name: str, last_sell: dict, today,
                             buy_price, same_strategy: bool) -> str:
    """``[재매수-shadow] {code} {strategy} 직전매도={전략}/{종류}/{YYYY-MM-DD HH:MM} 거래일차={n}
    같은전략={Y|N} 매수가비={+x.xx%|-}``."""
    ts = last_sell["timestamp"]
    kind = classify_sell_reason(last_sell.get("reason"))
    days = rebuy_trading_days_ago(ts.date(), today, last_sell.get("trading_dates") or [])
    loss = last_sell.get("profit_loss")
    sr1_blank = kind == "손절" or (kind == "기타" and loss is not None and loss < 0)
    sell_price = last_sell.get("price")
    ratio = "-"
    if not sr1_blank and buy_price and sell_price:
        ratio = f"{(float(buy_price) / float(sell_price) - 1) * 100:+.2f}%"
    return (f"[재매수-shadow] {code} {strategy_name} "
            f"직전매도={last_sell.get('strategy')}/{kind}/{ts.strftime('%Y-%m-%d %H:%M')} "
            f"거래일차={days} 같은전략={'Y' if same_strategy else 'N'} 매수가비={ratio}")


class TradingAnalyzer:
    """매매 판단 분석 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self.bot = bot
        self.logger = RateLimitedLogger(setup_logger(__name__))
        # 거절 로그 스로틀 상태: (종목코드, 사유접두) → 마지막 INFO 시각
        self._reject_log_times: Dict[Tuple[str, str], datetime] = {}
        # 억제 횟수 (2026-09-24 사전등록 ⑥ · `수량부족` 만): 같은 키의 직전 INFO 이후 억제된 횟수.
        # 다음 INFO 줄 끝에 「 외 N회」로 붙이고 비운다(새 줄 0).
        self._reject_suppressed: Dict[Tuple[str, str], int] = {}
        # [재매수-shadow] 상태: (종목, 오늘) → (조회 시각, 직전 매도 dict|None) ·
        # 이미 찍은 (종목, 전략, 직전매도 시각) · 예외 WARNING 1회 플래그.
        self._rebuy_shadow_cache: Dict[Tuple[str, object], Tuple[datetime, Optional[dict]]] = {}
        self._rebuy_shadow_logged: Set[Tuple[str, str, object]] = set()
        self._rebuy_shadow_warned = False

        # FundManager를 DecisionEngine에 연결 (main.py 수정 없이)
        if hasattr(bot, 'fund_manager') and hasattr(bot, 'decision_engine'):
            bot.decision_engine.set_fund_manager(bot.fund_manager)

    def _should_log_reject(self, stock_code: str, buy_reason) -> bool:
        """같은 (종목, 사유) 거절 INFO 를 10분에 1회만 허용 (로그 폭주 방지).

        strategies/base.py:549 `_should_log_ontick` 와 같은 구조다. 창의 «첫»
        발생은 반드시 통과시킨다 — 급락게이트처럼 대량 발생하는 사유도 종목별로
        표본이 남아야 사후에 무엇이 왜 막혔는지 셀 수 있다.
        """
        key = reject_throttle_key(stock_code, buy_reason)
        now = _reject_now()
        last = self._reject_log_times.get(key)
        if last is None or now - last >= REJECT_LOG_INTERVAL:
            self._reject_log_times[key] = now
            return True
        return False

    def _is_own_position(self, pos_stock, trading_stock, strategy_name: str) -> bool:
        """같은 종목의 POSITIONED 슬롯이 호출 전략 소유인가 (판정 불가면 True = 종전처럼 차단).

        owner 표기는 폴더키(복원)/클래스명(라이브 매수)으로 갈리므로 둘 다 «내 것»으로
        보고, 그 밖의 표기는 기존 해석 규칙(trading_manager.resolve_owner_strategy)으로
        인스턴스를 얻어 비교한다. 이름이 비었거나 해석이 안 되면 신원을 모르는 것이라
        보수적으로 차단한다 — 남의 보유로 잘못 막는 것보다 같은 전략 이중매수가 더 나쁘다.
        """
        if pos_stock is trading_stock or not strategy_name:
            return True
        caller = (getattr(self.bot, 'strategies', None) or {}).get(strategy_name)
        if caller is None:
            return True
        owner_name = getattr(pos_stock, 'owner_strategy_name', '') or ''
        if owner_name in (strategy_name, getattr(caller, 'name', None)):
            return True
        owner = getattr(pos_stock, 'owner_strategy', None)
        if owner is None:
            if not owner_name:
                return True
            owner = self.bot.trading_manager.resolve_owner_strategy(owner_name)
        return owner is None or owner is caller

    def _rebuy_shadow_buy_price(self, stock_code: str, signal) -> Optional[float]:
        """매수가 대용 = 캐시 현재가(API 호출 0) → 없으면 신호 참조가. 못 구하면 None."""
        try:
            im = getattr(self.bot.decision_engine, 'intraday_manager', None)
            info = im.get_cached_current_price(stock_code) if im is not None else None
            price = float(info.get('current_price', 0)) if isinstance(info, dict) else 0.0
            if price > 0:
                return price
        except Exception:
            pass
        try:
            from core.trading_decision_engine import signal_reference_price
            return signal_reference_price(signal)
        except Exception:
            return None

    def _is_same_strategy_label(self, label, strategy_name: str) -> bool:
        """DB strategy 칸(페이퍼 = 폴더키 · 실전 = 클래스명)이 호출 전략과 같은가."""
        if not label or not strategy_name:
            return False
        if label == strategy_name:
            return True
        strat = (getattr(self.bot, 'strategies', None) or {}).get(strategy_name)
        return strat is not None and label in (getattr(strat, 'name', None), type(strat).__name__)

    def _log_rebuy_shadow(self, trading_stock, strategy_name: str, signal) -> None:
        """[재매수-shadow] 1줄 (매매 동작 0 · 예외는 1회 WARNING 후 무시).

        직전 매도 = 같은 종목의 가장 최근 SELL(어떤 전략이든) · 오늘 이전 KOSPI 거래일
        REBUY_SHADOW_TRADING_DAYS 개 창 안. 조회는 (종목, 오늘) 캐시(TTL 10분)라 틱마다
        DB 를 때리지 않는다. 같은 (종목, 전략, 직전 매도)는 한 번만 찍는다.
        """
        if not rebuy_shadow_enabled():
            return
        try:
            from config.constants import REBUY_SHADOW_TRADING_DAYS
            code = trading_stock.stock_code
            now = _rebuy_shadow_now()
            today = now.date()
            key = (code, today)
            hit = self._rebuy_shadow_cache.get(key)
            if hit is not None and now - hit[0] < REBUY_SHADOW_CACHE_TTL:
                last_sell = hit[1]
            else:
                is_virtual = bool(getattr(self.bot.decision_engine, 'is_virtual_mode', True))
                last_sell = self.bot.db_manager.trading_repo.get_last_sell_within_trading_days(
                    code, today, REBUY_SHADOW_TRADING_DAYS, is_virtual=is_virtual)
                if not isinstance(last_sell, dict):
                    last_sell = None
                self._rebuy_shadow_cache[key] = (now, last_sell)
            if last_sell is None:
                return
            logged_key = (code, strategy_name, last_sell.get('timestamp'))
            if logged_key in self._rebuy_shadow_logged:
                return
            line = format_rebuy_shadow_line(
                code, strategy_name, last_sell, today,
                buy_price=self._rebuy_shadow_buy_price(code, signal),
                same_strategy=self._is_same_strategy_label(last_sell.get('strategy'), strategy_name),
            )
            self._rebuy_shadow_logged.add(logged_key)
            self.logger.info(line)
        except Exception as e:
            if not self._rebuy_shadow_warned:
                self._rebuy_shadow_warned = True
                self.logger.warning(f"[재매수-shadow] 기록 실패 — 이후 같은 오류는 무시(매매 영향 0): {e}")

    async def analyze_buy_decision(self, trading_stock, available_funds: float = None,
                                   signal=None, strategy_name: str = "") -> bool:
        """매수 판단 분석 (일봉 데이터 사용)

        Args:
            trading_stock: 거래 대상 주식
            available_funds: 사용 가능한 자금 (미리 계산된 값)
            signal: Signal 객체 (TradingContext.buy()에서 전달, target_price/stop_loss 활용)
            strategy_name: 전략 폴더키 (TradingContext.buy()에서 전달).
                           VirtualTradingManager 전략별 자금 격리 원장 조회 키로 사용.

        Returns:
            bool: 실제 매수가 체결(가상/실전)되면 True, 거부·실패·미체결이면 falsy.
                  호출자(TradingContext.buy)가 진입 쿨다운 무장 여부 판단에 사용한다 —
                  거부된 시도까지 쿨다운을 무장시키면 후속 진입을 굶긴다(2026-06-09 수정).
        """
        executed = False
        try:
            stock_code = trading_stock.stock_code
            stock_name = trading_stock.stock_name

            self.logger.debug(f"매수 판단 시작: {stock_code}({stock_name})")

            # 추가 안전 검증: «이 전략이» 이미 보유 중인 종목인지 다시 한번 확인.
            # 종목코드만 비교하면 다른 전략의 보유가 이 전략의 매수를 막는다
            # (2026-10-19 실례: book_envelope_200d 396300 보유 → daytrading 매수 차단).
            # 슬롯·원장·매도는 (종목, 전략) 단위라 전략이 다르면 각자 사는 것이 정상이다.
            positioned_stocks = self.bot.trading_manager.get_stocks_by_state(StockState.POSITIONED)
            same_code = [p for p in positioned_stocks if p.stock_code == stock_code]
            if any(self._is_own_position(p, trading_stock, strategy_name) for p in same_code):
                self.logger.info(f"보유 중인 종목 매수 신호 무시: {stock_code}({stock_name})")
                return
            if same_code:
                self.logger.debug(
                    f"{stock_code} 타전략 보유 중 — 전략별 독립 매수 판단 진행 "
                    f"(보유 owner={[p.owner_strategy_name for p in same_code]}, 호출={strategy_name})"
                )

            # 25분 매수 쿨다운 확인
            if trading_stock.is_buy_cooldown_active():
                remaining_minutes = trading_stock.get_remaining_cooldown_minutes()
                self.logger.debug(f"{stock_code}: 매수 쿨다운 활성화 (남은 시간: {remaining_minutes}분)")
                return

            # 일봉 데이터 가져오기 (daily_prices 테이블에서, PostgreSQL)
            daily_data = self.bot.db_manager.price_repo.get_daily_prices(stock_code, days=140)
            if daily_data is None or daily_data.empty:
                self.logger.warning(f"{stock_code} 일봉 데이터 없음 (daily_prices 테이블) - 매수 판단 불가")
                return

            if len(daily_data) < CANDIDATE_MIN_DAILY_DATA:
                self.logger.debug(f"{stock_code} 일봉 데이터 부족: {len(daily_data)}개 (최소 {CANDIDATE_MIN_DAILY_DATA}개 필요)")
                return

            self.logger.debug(f"{stock_code} 일봉 데이터 조회 완료: {len(daily_data)}건")

            # 전략별 regime_index 조회 (급락필터 분리). 폴더키로 인스턴스 조회, 미설정시 both.
            regime_index = "both"
            try:
                strat = (self.bot.strategies or {}).get(strategy_name) if strategy_name else None
                if strat is not None:
                    regime_index = getattr(strat, "regime_index", "both") or "both"
            except Exception:
                pass

            # [재매수-shadow] 기록 로그(10-29 창구 A · 동작 0) — 엔진 호출 «전» 1줄.
            self._log_rebuy_shadow(trading_stock, strategy_name, signal)

            # 매매 판단 엔진으로 매수 신호 확인 (일봉 데이터 사용)
            # owner_signal: on_tick에서 '올바른 전략'이 생성·검증한 신호를 그대로 전달해야
            # decision_engine이 단일 고정전략(Elder)으로 재판정하지 않는다(2026-06-09 ④ 수정).
            buy_signal, buy_reason, buy_info = await self.bot.decision_engine.analyze_buy_decision(
                trading_stock, daily_data, regime_index=regime_index, owner_signal=signal,
                strategy_name=strategy_name
            )

            # 매수 거절 계기(2026-08-27) — 거절 사유를 INFO 로 올린다.
            # 로그 파일 레벨이 INFO 라 DEBUG 로만 남기면 «거절이 로그에 한 줄도
            # 안 남는다». 2026-08-25 「진입 밴드 거절」 조사에서 계기 부재로
            # 확인 불가였던 자리다. 사유 문자열은 엔진 것을 그대로 실어 나른다
            # (문자열을 바꾸면 이 사유를 참조하는 다른 코드·문서가 깨진다).
            # 스로틀: 같은 (종목, 사유) 는 10분 1회 — '시장급락 매수차단' 이
            # 2026-08-19 에 하루 ~2,900회 발생했다. 억제된 건도 DEBUG 로는 남는다.
            # 「외 N회」(2026-09-24 사전등록 ⑥): _should_log_reject 는 결정당 «정확히 1회»만
            # 부른다(부를 때마다 _reject_log_times 를 갱신해 두 번 부르면 스스로 억제된다).
            # 창·억제 판정·DEBUG 줄 불변 · `수량부족` 외 사유는 접미 0.
            log_reject = (not buy_signal and not _is_high_frequency_reject(buy_reason)
                          and self._should_log_reject(stock_code, buy_reason))
            reject_tail = ""
            try:
                if not buy_signal and not _is_high_frequency_reject(buy_reason):
                    rkey = reject_throttle_key(stock_code, buy_reason)
                    if log_reject:
                        n_sup = self._reject_suppressed.pop(rkey, 0)
                        if n_sup > 0:
                            reject_tail = f" 외 {n_sup}회"
                    elif rkey[1].startswith("수량부족"):
                        self._reject_suppressed[rkey] = self._reject_suppressed.get(rkey, 0) + 1
            except Exception:
                reject_tail = ""
            if log_reject:
                self.logger.info(format_reject_log(stock_code, buy_reason) + reject_tail)
            else:
                self.logger.debug(f"{stock_code} 매수 판단 결과: signal={buy_signal}, reason='{buy_reason}'")
            if buy_signal and buy_info:
                self.logger.debug(
                    f"{stock_code} 매수 정보: 가격={buy_info['buy_price']:,.0f}원, "
                    f"수량={buy_info['quantity']:,}주, 투자금={buy_info['max_buy_amount']:,.0f}원"
                )

            if buy_signal and buy_info.get('quantity', 0) > 0:
                self.logger.info(f"{stock_code}({stock_name}) 매수 신호 발생: {buy_reason}")

                required_amount = buy_info['buy_price'] * buy_info['quantity']

                # 가상모드는 수량 재조정 금지: 수량은 decision_engine이 전략 원장
                # (VirtualTradingManager 격리 자본) 기준으로 이미 산정한 SSOT다.
                # FM 집계 가용으로 줄이면 유령 invested 누적 시 1~10주 잔편 매수가
                # 발생한다(2026-06-11 진단). FM 검증은 아래 reserve_funds가 담당.
                if not self.bot.decision_engine.is_virtual_mode:
                    # 실전: 매수 전 자금 확인 (전달받은 available_funds 활용)
                    if available_funds is not None:
                        # 전달받은 가용 자금 기준으로 종목당 최대 투자 금액 계산 (10%)
                        fund_status = self.bot.fund_manager.get_status()
                        max_buy_amount = min(available_funds, fund_status['total_funds'] * 0.1)
                    else:
                        # FundManager 기반 최대 매수 가능 금액 계산
                        max_buy_amount = self.bot.fund_manager.get_max_buy_amount(stock_code)

                    if required_amount > max_buy_amount:
                        self.logger.warning(
                            f"{stock_code} 자금 부족: 필요={required_amount:,.0f}원, 가용={max_buy_amount:,.0f}원"
                        )
                        # 가용 자금에 맞게 수량 조정
                        if max_buy_amount > 0:
                            adjusted_quantity = int(max_buy_amount / buy_info['buy_price'])
                            if adjusted_quantity > 0:
                                buy_info['quantity'] = adjusted_quantity
                                required_amount = buy_info['buy_price'] * adjusted_quantity
                                self.logger.info(
                                    f"{stock_code} 수량 조정: {adjusted_quantity}주 "
                                    f"(투자금: {required_amount:,.0f}원)"
                                )
                            else:
                                self.logger.warning(f"{stock_code} 매수 포기: 최소 1주도 매수 불가")
                                return
                        else:
                            self.logger.warning(f"{stock_code} 매수 포기: 가용 자금 없음")
                            return

                # FundManager 자금 예약.
                # 키는 반드시 make_reserve_id — place_buy_order 의 H4 중복방지가
                # has_reservation(같은 id) 로 이 예약을 감지해 2차 예약을 만들지
                # 않도록 해야 한다. 키가 어긋나면 2차 예약이 생기고 1차 예약이
                # 영구 누수된다(사전-실전 감사 BLOCKER #7, 2026-06-24).
                #
                # 종목코드 단독 키는 「같은 전략의 진짜 중복」과 「다른 전략의
                # 정당한 매수」를 구분하지 못한다(2026-08-14 Fix 4).
                # ⚠️ 정정(리뷰 F3): 이 수정만으로 「B 전략이 같은 종목을 살 수
                # 있게 된다」는 **아니다**. 실제로는 13줄 앞
                # (order_executor.place_buy_order 의 has_active_buy_order)에서
                # `중복 매수 주문 방지` 로 먼저 떨어진다 — _active_buy_stocks 가
                # 여전히 종목코드 단독 키이기 때문이다. 그건 선행 결함이고
                # 회귀가 아니며, 중복주문 가드를 푸는 건 버그 수정이 아니라
                # 위험 결정이라 손대지 않는다. 이 수정이 실제로 사는 자리는
                # on_tick 취소 경로다 — CancelledError 는 BaseException 이라
                # 아래 except Exception 이 안 잡고 예약이 남는데, 종전 키에서는
                # 그 유실 예약이 «다른 전략» 을 세션 내내 막았고 지금은 자기
                # 소유분만 막는다.
                # owner 는 인자(strategy_name=폴더키)가 아니라 **슬롯 객체**에서
                # 읽는다 — order_execution.execute_buy_order 가 place_buy_order 로
                # 넘기는 값과 문자 그대로 같아야 감지가 성립한다(표기-불변).
                from utils.korean_time import now_kst as _now_kst
                from core.fund_manager import make_reserve_id
                _reserve_id = make_reserve_id(
                    stock_code, trading_stock.owner_strategy_name)
                reserve_ok = self.bot.fund_manager.reserve_funds(_reserve_id, required_amount)
                if not reserve_ok:
                    self.logger.warning(f"{stock_code} 자금 예약 실패 - 매수 스킵")
                    return

                # 매수 전 종목 상태 확인.
                # 소유 전략은 인자(strategy_name=폴더키)가 아니라 **객체에서** 읽는다.
                # SELECTED owner 표기는 폴더키(다중전략 로더)/클래스명(단일전략 로더)
                # 으로 분열하므로(실증 2026-07-23, 01d336e) 폴더키 단독 조회는 클래스명
                # owner 형상에서 매칭 0 이 된다. 객체 조회는 표기-불변이고, 슬롯당
                # (code, owner) 가 유일하므로 [모호조회] WARNING 도 남지 않는다.
                # (analyze_sell_decision 및 execute_real_buy 와 동일 관례)
                current_stock = self.bot.trading_manager.get_trading_stock(
                    stock_code, strategy=trading_stock.owner_strategy_name or None
                )
                if current_stock:
                    self.logger.debug(f"매수 전 상태 확인: {stock_code} 현재상태={current_stock.state.value}")

                # 가상/실전 매매 분기
                # Signal 우선순위: 엔진 재생성 신호 > 호출자 전달 신호
                effective_signal = buy_info.get('signal') or signal
                if self.bot.decision_engine.is_virtual_mode:
                    # 가상 매수
                    try:
                        buy_ok = await self.bot.decision_engine.execute_virtual_buy(
                            trading_stock, None, buy_reason,
                            buy_price=buy_info['buy_price'],
                            quantity=buy_info['quantity'],
                            signal=effective_signal,
                            strategy_name=strategy_name
                        )
                        if not buy_ok:
                            # 유령 체결 차단: VTM 거부(전략 원장 부족 등) 시 자금
                            # 확정·상태 전이·쿨다운 없이 예약만 환원한다. 무조건
                            # confirm은 FM invested를 미체결분으로 오염시켜 잔편
                            # 매수·정합성 CRITICAL을 유발했다(2026-06-11 진단).
                            self.bot.fund_manager.cancel_order(_reserve_id)
                            self.logger.warning(
                                f"{stock_code} 가상 매수 미체결 — 예약 취소 (유령 체결 방지)"
                            )
                            return False
                        # 자금 확정 (가상매매는 즉시 체결로 간주)
                        self.bot.fund_manager.confirm_order(_reserve_id, required_amount)
                        # 보유 종목 추가 (FundManager 보유 레지스트리 추적).
                        # owner 는 인자(strategy_name)가 아니라 **슬롯 객체**에서 읽는다.
                        # owner 표기는 경로별로 폴더키/클래스명으로 분열하므로, 매도 측
                        # (trading_decision_engine:880·liquidation_handler:341)과
                        # 문자 그대로 동일한 식이어야 (code, owner) 엔트리가 일치한다
                        # (표기-불변, 01d336e). 인자 폴백을 두면 add/remove 가
                        # 비대칭이 되어 엔트리가 영구 잔류할 수 있다.
                        self.bot.fund_manager.add_position(
                            stock_code, trading_stock.owner_strategy_name or None
                        )
                        # 매수 쿨다운 설정
                        trading_stock.set_buy_time(_now_kst())
                        # 상태를 BUY_PENDING → POSITIONED 2단계로 전이 (실전 경로와 일관성).
                        # owner 는 인자(strategy_name=폴더키)가 아니라 **슬롯 객체**에서
                        # 읽는다 — 위 add_position(:197)·get_trading_stock(:159)·매도 실패
                        # 복원(:300) 과 문자 그대로 동일한 식이어야 한다(표기-불변, 01d336e).
                        # 인자를 넘기면 안 되는 이유는 추상적이지 않다: 바로 위
                        # execute_virtual_buy 가 trading_decision_engine:660 에서
                        # `owner_strategy_name = display_name`(전략 인스턴스 .name =
                        # **클래스명**)으로 이 객체의 owner 를 **덮어쓴 직후**다. 인자는
                        # 폴더키이므로 두 표기가 갈리고, _find_by_code 는 == 정확일치라
                        # 매칭 0 이 된다.
                        # ⚠️ change_stock_state 는 매칭 0 일 때 예외 없이 조용히 return
                        # 한다(stock_state_manager:158~159) → 이 try/except 는 무력하고
                        # 에러 로그도 남지 않는다. 그래서 종목이 SELECTED 로 남은 채
                        # EOD 청산 대상집합(POSITIONED)에서 통째로 빠졌다(2026-08-06 실측:
                        # 청산 대상 46 vs 실보유 55, 차 9 = 당일 매수 9건·전략별 6/6 일치).
                        # ⚠️ `or None` 을 붙이지 말 것 — "" 는 무기명 슬롯만 정확 매칭하는
                        # 가장 정밀한 키이고, None 은 필터를 해제해 남의 슬롯을 집는다.
                        try:
                            self.bot.trading_manager._change_stock_state(
                                stock_code, StockState.BUY_PENDING, "가상 매수 주문",
                                strategy=trading_stock.owner_strategy_name
                            )
                            self.bot.trading_manager._change_stock_state(
                                stock_code, StockState.POSITIONED, "가상 매수 체결",
                                strategy=trading_stock.owner_strategy_name
                            )
                        except Exception as e:
                            self.logger.debug(f"가상 매수 상태 변경 실패: {stock_code} - {e}")
                        self.logger.info(f"가상 매수 완료 처리: {stock_code}({stock_name}) - {buy_reason}")
                        executed = True
                    except Exception as e:
                        # 매수 실패 시 자금 예약 취소
                        self.bot.fund_manager.cancel_order(_reserve_id)
                        self.logger.error(f"가상 매수 처리 오류: {e}")
                else:
                    # 실전 매수
                    try:
                        success = await self.bot.decision_engine.execute_real_buy(
                            trading_stock, buy_reason,
                            buy_price=buy_info['buy_price'],
                            quantity=buy_info['quantity']
                        )
                        if success:
                            # 자금 확정은 체결 확인 시 OrderMonitor에서 처리 (이중 확정 방지)
                            self.logger.info(f"실전 매수 주문 접수: {stock_code}({stock_name}) - {buy_reason}")
                            executed = True
                        else:
                            # 매수 실패 시 자금 예약 취소
                            self.bot.fund_manager.cancel_order(_reserve_id)
                            self.logger.warning(f"실전 매수 실패: {stock_code}({stock_name})")
                    except Exception as e:
                        self.bot.fund_manager.cancel_order(_reserve_id)
                        self.logger.error(f"실전 매수 처리 오류: {e}")

            return executed

        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매수 판단 오류: {e}")
            import traceback
            self.logger.error(f"상세 오류 정보: {traceback.format_exc()}")
            return False

    async def analyze_sell_decision(self, trading_stock, signal=None) -> None:
        """매도 판단 분석 (1분봉 고가/저가 기준 익절/손절 + 3분봉 기술적 분석)

        Args:
            trading_stock: 거래 대상 주식
            signal: Signal 객체 (TradingContext.sell()에서 전달). 전략이 일봉
                데이터로 이미 매도를 결정한 경우 이 결정을 그대로 신뢰하고
                decision_engine 재판단을 건너뛴다. decision_engine의 재판단은
                1분봉(combined_data) 기반인데, rebalancing_mode=true 설정에서는
                분봉이 수집되지 않아 combined_data가 구조적으로 항상 None이라
                재판단 경로는 영구히 매도를 차단했다(D2 결함). signal=None이면
                기존 동작(재판단 경로)을 그대로 유지한다.
        """
        try:
            stock_code = trading_stock.stock_code
            stock_name = trading_stock.stock_name

            if signal is not None:
                from strategies.base import SignalType
                if signal.signal_type not in (SignalType.SELL, SignalType.STRONG_SELL):
                    # 매수성 신호가 매도를 유발해선 안 된다 — 아무 것도 하지 않는다.
                    return
                sell_signal = True
                sell_reason = ', '.join(signal.reasons) if signal.reasons else (
                    trading_stock.owner_strategy_name or signal.signal_type.value
                )
            else:
                # 1분봉 데이터 조회 (백테스팅과 동일한 방식)
                combined_data = self.bot.intraday_manager.get_combined_chart_data(stock_code)

                # 매매 판단 엔진으로 매도 신호 확인 (1분봉 데이터 전달)
                sell_signal, sell_reason = await self.bot.decision_engine.analyze_sell_decision(
                    trading_stock, combined_data
                )

            if sell_signal:
                # 매도 전 종목 상태 확인
                self.logger.debug(f"매도 전 상태 확인: {stock_code} 현재상태={trading_stock.state.value}")
                if trading_stock.position:
                    self.logger.debug(
                        f"포지션 정보: {trading_stock.position.quantity}주 "
                        f"@{trading_stock.position.avg_price:,.0f}원"
                    )

                # 가상/실전 매매 분기
                if self.bot.decision_engine.is_virtual_mode:
                    # 가상 매도
                    try:
                        # 매도가를 먼저 결정 (execute_virtual_sell과 PnL 계산에 동일 가격 사용)
                        # 원가(avg_price)로 미리 채우지 않는다 — 그러면 execute_virtual_sell의
                        # 자체 캐시→브로커→거부 폴백 체인(:827)이 무력화되어 매수가로 매도되고
                        # 실현손익이 항상 0으로 왜곡된다. 캐시 실패 시 None을 그대로 전달한다.
                        sell_price = None
                        if trading_stock.position:
                            try:
                                price_info = self.bot.intraday_manager.get_cached_current_price(stock_code)
                                if price_info and price_info.get('current_price', 0) > 0:
                                    sell_price = float(price_info['current_price'])
                            except Exception:
                                pass

                        # move_to_sell_candidate는 가상매도에서는 직접 호출
                        # 소유 전략을 명시해 다중소유 종목의 오귀속을 차단
                        self.bot.trading_manager.move_to_sell_candidate(
                            stock_code, sell_reason,
                            strategy=trading_stock.owner_strategy_name or None
                        )
                        # 확정된 매도가를 execute_virtual_sell에 전달
                        sell_ok = await self.bot.decision_engine.execute_virtual_sell(
                            trading_stock, sell_price, sell_reason
                        )
                        # fund_manager 업데이트는 execute_virtual_sell() 내부에서 일원화 처리
                        if not sell_ok:
                            trading_stock.is_selling = False
                            # 매도 실패 시 POSITIONED로 복원
                            self.bot.trading_manager._change_stock_state(
                                stock_code, StockState.POSITIONED, "가상 매도 실패 복원",
                                strategy=trading_stock.owner_strategy_name
                            )
                            self.logger.warning(f"{stock_code} 가상 매도 실패 - POSITIONED로 복원")
                        else:
                            self.logger.info(f"가상 매도 완료 처리: {stock_code}({stock_name}) - {sell_reason}")
                    except Exception as e:
                        self.logger.error(f"가상 매도 처리 오류: {e}")
                else:
                    # 실전 매도 (execute_real_sell 내부에서 move_to_sell_candidate 호출)
                    try:
                        sell_ok = await self.bot.decision_engine.execute_real_sell(
                            trading_stock, sell_reason
                        )
                        if sell_ok:
                            self.logger.info(f"실전 매도 주문 접수: {stock_code}({stock_name}) - {sell_reason}")
                        else:
                            self.logger.warning(f"실전 매도 실패: {stock_code}({stock_name})")
                    except Exception as e:
                        self.logger.error(f"실전 매도 처리 오류: {e}")
        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매도 판단 오류: {e}")
