"""
시장별 거래시간 설정
해외주식 확장을 고려한 시장별/날짜별 거래시간 관리

경계 시간대 구분 (MarketPhase):
- 08:30~09:00 동시호가 (pre_auction)
- 09:00~09:05 장 시작 직후 보호 (opening_protection)
- 15:20~15:30 장 마감 직전 (closing_cutoff)
- 15:20~15:30 동시호가 (closing_auction)
- EOD 청산 시간 (eod_liquidation)
- 서킷브레이커/VI 대응

⚠️ 위는 **구간 정의**일 뿐 전부가 주문을 막는 건 아니다. 실제 주문 경로에 걸린 것만:
- `can_place_order()` → pre_market/pre_auction(장 시작 전), closing_cutoff·closing_auction,
  시장 전체 서킷브레이커, 종목 VI. **opening_protection 은 차단하지 않는다**
  (`is_opening_protection()` 은 프로덕션 호출자 0건 — 09:00~09:05 에도 주문된다).
- `is_eod_liquidation_time()` → EOD 청산 + 그 시각 이후 intraday 전략 신규매수 차단.
- `should_stop_buying()`/`is_new_buy_blocked()`(buy_cutoff_hour) → **결선 안 됨. 호출자 0건.**
보호장치를 인용하기 전에 호출자부터 확인할 것 (2026-08-06 거짓 배너 사건).
"""
from datetime import time, datetime, timedelta
from typing import Dict, Optional, List
from enum import Enum
import pytz


class MarketPhase(Enum):
    """장 상태 단계"""
    CLOSED = "closed"                   # 장 마감 / 주말
    PRE_MARKET = "pre_market"           # 장 시작 전 (~08:30)
    PRE_AUCTION = "pre_auction"         # 동시호가 (08:30~09:00)
    OPENING_PROTECTION = "opening_protection"  # 장 시작 직후 보호 (09:00~09:05)
    MARKET_OPEN = "market_open"         # 정규장 (09:05~15:20)
    CLOSING_CUTOFF = "closing_cutoff"   # 매수 차단 (15:20~15:30, 설정에 따라 다름)
    CLOSING_AUCTION = "closing_auction" # 장 마감 동시호가 (15:20~15:30)
    POST_MARKET = "post_market"         # 장 마감 후


class CircuitBreakerState:
    """서킷브레이커/VI 상태 추적 (thread-safe)

    메인 루프, 텔레그램, 시스템 모니터가 동시에 접근할 수 있으므로
    threading.Lock으로 보호합니다.
    """

    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self._active_circuit_breakers: Dict[str, datetime] = {}  # stock_code -> triggered_at
        self._market_wide_halt: bool = False
        self._market_halt_until: Optional[datetime] = None

    def trigger_vi(self, stock_code: str, triggered_at: Optional[datetime] = None):
        """개별 종목 VI 발동 기록"""
        if triggered_at is None:
            triggered_at = datetime.now(pytz.timezone('Asia/Seoul'))
        with self._lock:
            self._active_circuit_breakers[stock_code] = triggered_at

    def release_vi(self, stock_code: str):
        """개별 종목 VI 해제"""
        with self._lock:
            self._active_circuit_breakers.pop(stock_code, None)

    def is_vi_active(self, stock_code: str) -> bool:
        """개별 종목 VI 발동 여부 확인 (2분 후 자동 해제)"""
        with self._lock:
            if stock_code not in self._active_circuit_breakers:
                return False
            triggered_at = self._active_circuit_breakers[stock_code]
            if triggered_at:
                from utils.korean_time import now_kst
                elapsed = (now_kst() - triggered_at).total_seconds()
                if elapsed > 120:  # 2분 경과 시 자동 해제
                    self._active_circuit_breakers.pop(stock_code, None)
                    return False
            return True

    def trigger_market_halt(self, duration_minutes: int = 20, triggered_at: Optional[datetime] = None):
        """시장 전체 서킷브레이커 발동"""
        if triggered_at is None:
            triggered_at = datetime.now(pytz.timezone('Asia/Seoul'))
        with self._lock:
            self._market_wide_halt = True
            self._market_halt_until = triggered_at + timedelta(minutes=duration_minutes)

    def release_market_halt(self):
        """시장 전체 서킷브레이커 해제"""
        with self._lock:
            self._market_wide_halt = False
            self._market_halt_until = None

    def is_market_halted(self, dt: Optional[datetime] = None) -> bool:
        """시장 전체 거래 중단 여부"""
        with self._lock:
            if not self._market_wide_halt:
                return False
            if self._market_halt_until and dt:
                if dt >= self._market_halt_until:
                    self._market_wide_halt = False
                    self._market_halt_until = None
                    return False
            return self._market_wide_halt

    def get_active_vi_stocks(self) -> List[str]:
        """VI 발동 중인 종목 목록 (2분 만료 필터 적용)"""
        from utils.korean_time import now_kst
        with self._lock:
            _now = now_kst()
            expired = []
            active = []
            for stock_code, triggered_at in self._active_circuit_breakers.items():
                if triggered_at and (_now - triggered_at).total_seconds() > 120:
                    expired.append(stock_code)
                else:
                    active.append(stock_code)
            for code in expired:
                self._active_circuit_breakers.pop(code, None)
            return active

    def clear_all(self):
        """모든 상태 초기화 (일일 리셋)"""
        with self._lock:
            self._active_circuit_breakers.clear()
            self._market_wide_halt = False
            self._market_halt_until = None


# 싱글턴 서킷브레이커 상태
_circuit_breaker_state = CircuitBreakerState()


def get_circuit_breaker_state() -> CircuitBreakerState:
    """전역 서킷브레이커 상태 반환"""
    return _circuit_breaker_state


def arm_circuit_breaker_from_info(stock_code: str, info: Optional[Dict],
                                  cb_state: Optional['CircuitBreakerState'] = None) -> bool:
    """라이브 KIS 종목 기본정보로 런타임 VI 상태를 arm한다.

    프로덕션에 trigger_vi 프로듀서가 없어 VI/거래정지 매수 가드가 영구 no-op
    이던 문제를 해소한다(사전-실전 감사 BLOCKER #6, 2026-06-24). 매수 시점에
    호출해 해당 종목이 VI/거래정지면 trigger_vi 로 표기 → is_vi_active 가드 발효.

    KIS inquire-price(FHKST01010100) 값 계약 — 2026-08-09 전 유니버스 2,574종목 실측:
    - vi_cls_code: 'N' 미발동이 **2,574/2,574 관측**(일요일 채록이라 VI 사건이 있을
      수 없는 시각이었다). ❌ '1'/'2'/'3' 은 한 건도 나오지 않아 옛 계약은 반증됨
      (숫자로 읽으면 항상 False 라 가드가 영구 no-op 이 된다 — 실제로 그랬다).
      🔴 'Y' == 발동 은 **미관측 추정**이다(KIS 명명 규칙 기반 추론). 장중 첫 VI
      사건에서 확증할 것.
    - iscd_stat_cls_code: '58' = 거래정지 (122종목, 전건 거래량 0으로 교차확인).
      ❌ '09' 는 유니버스에 존재하지 않는 값. '55'가 아닌 값 = 이상, 도 아니다
      ('57' 증거금100% 가 1,584종목으로 최다이며 정상 거래된다).
    - temp_stop_yn: 'Y' = 임시정지.

    실제 KIS 보고에만 arm 하므로 오탐(정상거래 차단) 위험이 없다.
    info 가 비었으면(조회 실패) arm 하지 않아 위험축소가 아닌 신규매수만 영향.

    Returns:
        True if VI/거래정지로 arm 됨, 아니면 False.
    """
    if not info:
        return False
    cb = cb_state if cb_state is not None else get_circuit_breaker_state()

    def _f(key: str) -> str:
        # .strip()/.upper() 를 빼지 말 것(KIS 가 값에 공백을 붙여 보낸다).
        # NaN 도 «값 없음» — pandas 경유(df.iloc[0].to_dict())면 결측이 NaN 이라,
        # 안 막으면 'NAN' 이라는 판정 가능한 값처럼 읽힌다.
        value = info.get(key)
        if value is None or value != value:
            return ''
        return str(value).strip().upper()

    vi = _f('vi_cls_code')
    halted = _f('iscd_stat_cls_code') or _f('stat_cls_code')
    if vi == 'Y' or halted == '58' or _f('temp_stop_yn') == 'Y':
        cb.trigger_vi(stock_code)
        return True
    return False


class MarketHours:
    """시장별 거래시간 설정"""

    # 마감 동시호가 시작 기본값 = **주문이 실제로 막히는 시각**.
    # `get_market_phase()`(게이트)와 `get_today_info()`(배너)가 반드시 같은 값을
    # 봐야 배너가 실제 동작과 어긋나지 않으므로 한 곳에서만 정의한다.
    DEFAULT_CLOSING_AUCTION_START = time(15, 20)

    # 시장별 기본 거래시간 설정
    MARKET_CONFIG = {
        'KRX': {  # 한국거래소
            'timezone': 'Asia/Seoul',
            'default': {
                'market_open': time(9, 0),      # 09:00
                'market_close': time(15, 30),   # 15:30
                'buy_cutoff_hour': 12,          # 12시 이후 매수 중단
                'eod_liquidation_hour': 15,     # 15시 시장가 일괄매도
                'eod_liquidation_minute': 0,    # 15:00 정각
                'pre_auction_start': time(8, 30),    # 동시호가 시작
                'opening_protection_end': time(9, 5), # 장 시작 직후 보호 종료
                'closing_auction_start': time(15, 20), # 마감 동시호가 시작
                'new_buy_cutoff': time(15, 20),  # 신규 매수 차단 시각
            },
            'special_days': {
                # 수능일 (2025년)
                '2025-11-13': {
                    'market_open': time(10, 0),     # 10:00
                    'market_close': time(16, 30),   # 16:30
                    'buy_cutoff_hour': 13,          # 13시 이후 매수 중단
                    'eod_liquidation_hour': 16,     # 16시 시장가 일괄매도
                    'eod_liquidation_minute': 0,    # 16:00 정각
                    'reason': '수능일 (1시간 지연)'
                },
                # 향후 특수일 추가 가능
                # '2025-12-31': { ... },  # 연말 단축거래
            }
        },

        # 나중에 해외 시장 추가
        'NYSE': {  # 뉴욕증권거래소
            'timezone': 'America/New_York',
            'default': {
                'market_open': time(9, 30),
                'market_close': time(16, 0),
                'buy_cutoff_hour': 15,          # 3PM ET
                'eod_liquidation_hour': 15,
                'eod_liquidation_minute': 55,
            },
            'special_days': {}
        },

        'NASDAQ': {  # 나스닥
            'timezone': 'America/New_York',
            'default': {
                'market_open': time(9, 30),
                'market_close': time(16, 0),
                'buy_cutoff_hour': 15,
                'eod_liquidation_hour': 15,
                'eod_liquidation_minute': 55,
            },
            'special_days': {}
        },

        'TSE': {  # 도쿄증권거래소
            'timezone': 'Asia/Tokyo',
            'default': {
                'market_open': time(9, 0),
                'market_close': time(15, 0),    # 점심시간 11:30-12:30 있음 (추후 구현)
                'buy_cutoff_hour': 14,
                'eod_liquidation_hour': 14,
                'eod_liquidation_minute': 55,
            },
            'special_days': {}
        }
    }

    @classmethod
    def get_market_hours(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> Dict:
        """특정 날짜의 시장 거래시간 반환

        Args:
            market: 시장 코드 (KRX, NYSE, NASDAQ, TSE 등)
            dt: 확인할 날짜 (None이면 오늘)

        Returns:
            거래시간 설정 딕셔너리
        """
        if market not in cls.MARKET_CONFIG:
            raise ValueError(f"Unknown market: {market}")

        market_config = cls.MARKET_CONFIG[market]

        # 날짜가 없으면 오늘 날짜 사용
        if dt is None:
            tz = pytz.timezone(market_config['timezone'])
            dt = datetime.now(tz)

        # 해당 날짜의 특수일 설정 확인
        date_str = dt.strftime('%Y-%m-%d')
        special_days = market_config.get('special_days', {})

        if date_str in special_days:
            # 특수일 설정 사용
            special_config = special_days[date_str].copy()
            special_config['timezone'] = market_config['timezone']
            special_config['is_special_day'] = True
            return special_config
        else:
            # 기본 설정 사용
            default_config = market_config['default'].copy()
            default_config['timezone'] = market_config['timezone']
            default_config['is_special_day'] = False
            return default_config

    @classmethod
    def is_market_open(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> bool:
        """장중 시간인지 확인 (주말 + 공휴일 체크)

        Args:
            market: 시장 코드
            dt: 확인할 시간 (None이면 현재)

        Returns:
            장중이면 True
        """
        hours = cls.get_market_hours(market, dt)
        tz = pytz.timezone(hours['timezone'])

        if dt is None:
            dt = datetime.now(tz)
        elif dt.tzinfo is None:
            dt = tz.localize(dt)

        # 평일만 확인 (월-금)
        if dt.weekday() >= 5:  # 토요일(5), 일요일(6)
            return False

        # 공휴일 체크 (KRX만 — 해외시장은 별도 캘린더 필요)
        if cls._is_holiday(market, dt):
            return False

        market_open = hours['market_open']
        market_close = hours['market_close']
        current_time = dt.time()

        return market_open <= current_time <= market_close

    @classmethod
    def _is_holiday(cls, market: str, dt: datetime) -> bool:
        """공휴일 여부 확인 (내부 헬퍼)

        KRX: holidays.KR 백엔드 + 근로자의 날 수동 보완 (korean_holidays 모듈)
        NYSE/NASDAQ: holidays.NYSE 백엔드
        TSE: holidays.JP 백엔드
        fallback: import 실패 시 False 반환 (주말 체크는 호출부에서 별도 수행)
        """
        if market == 'KRX':
            try:
                from utils.korean_holidays import is_fixed_holiday, is_lunar_holiday, is_special_holiday
                return is_fixed_holiday(dt) or is_lunar_holiday(dt) or is_special_holiday(dt)
            except ImportError:
                return False

        if market in ('NYSE', 'NASDAQ'):
            try:
                import holidays as _hlib
                nyse = _hlib.NYSE(years=dt.year)
                d = dt.date() if hasattr(dt, 'date') else dt
                return d in nyse
            except Exception:
                return False

        if market == 'TSE':
            try:
                import holidays as _hlib
                jp = _hlib.JP(years=dt.year)
                d = dt.date() if hasattr(dt, 'date') else dt
                return d in jp
            except Exception:
                return False

        return False

    @classmethod
    def is_before_market_open(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> bool:
        """장 시작 전인지 확인"""
        hours = cls.get_market_hours(market, dt)
        tz = pytz.timezone(hours['timezone'])

        if dt is None:
            dt = datetime.now(tz)
        elif dt.tzinfo is None:
            dt = tz.localize(dt)

        # 평일이 아니면 False
        if dt.weekday() >= 5:
            return False

        # 공휴일이면 False
        if cls._is_holiday(market, dt):
            return False

        market_open = hours['market_open']
        current_time = dt.time()
        return current_time < market_open

    @classmethod
    def get_market_status(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> str:
        """시장 상태 반환

        Returns:
            'weekend', 'pre_market', 'market_open', 'after_market'
        """
        hours = cls.get_market_hours(market, dt)
        tz = pytz.timezone(hours['timezone'])

        if dt is None:
            dt = datetime.now(tz)
        elif dt.tzinfo is None:
            dt = tz.localize(dt)

        if dt.weekday() >= 5:
            return "weekend"
        elif cls._is_holiday(market, dt):
            return "holiday"
        elif cls.is_before_market_open(market, dt):
            return "pre_market"
        elif cls.is_market_open(market, dt):
            return "market_open"
        else:
            return "after_market"

    @classmethod
    def should_stop_buying(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> bool:
        """매수 중단 시간인지 확인 (buy_cutoff_hour 이후)

        🔴 **이 함수는 현재 매매 경로에 결선돼 있지 않다** — 프로덕션 호출자 0건
        (`is_new_buy_blocked()` 와 테스트만 호출하며, `is_new_buy_blocked()` 자체도
        프로덕션 호출자가 없다). 따라서 `buy_cutoff_hour`(KRX 기본 12시)는 실매매에
        아무 영향이 없고, 실제로 12시 이후 신규 매수가 계속 체결된다
        (2026-08-06 실측: 14거래일 166매수 중 8건이 12시 이후, 최대 15:09).

        결선하려면: 주문 경로의 유일한 시간 게이트인 `can_place_order()` 에 이 판정을
        추가해야 한다(`core/orders/order_executor.place_buy_order` 가 호출하는 함수).
        결선할 경우 `get_today_info()` 배너도 함께 고칠 것 — 배너는 `can_place_order()`
        가 실제로 보는 조건만 적기로 돼 있고, 테스트가 둘의 일치를 강제한다.

        Args:
            market: 시장 코드
            dt: 확인할 시간 (None이면 현재)

        Returns:
            매수 중단 시간이면 True
        """
        hours = cls.get_market_hours(market, dt)
        tz = pytz.timezone(hours['timezone'])

        if dt is None:
            dt = datetime.now(tz)
        elif dt.tzinfo is None:
            dt = tz.localize(dt)

        buy_cutoff_hour = hours.get('buy_cutoff_hour', 12)
        return dt.hour >= buy_cutoff_hour

    @classmethod
    def is_eod_liquidation_time(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> bool:
        """장마감 일괄청산 시간인지 확인 (eod_liquidation_hour 이후)

        Args:
            market: 시장 코드
            dt: 확인할 시간 (None이면 현재)

        Returns:
            청산 시간이면 True
        """
        hours = cls.get_market_hours(market, dt)
        tz = pytz.timezone(hours['timezone'])

        if dt is None:
            dt = datetime.now(tz)
        elif dt.tzinfo is None:
            dt = tz.localize(dt)

        eod_hour = hours.get('eod_liquidation_hour', 15)
        eod_minute = hours.get('eod_liquidation_minute', 0)

        # 지정된 시간 이후인지 확인
        if dt.hour > eod_hour:
            return True
        elif dt.hour == eod_hour and dt.minute >= eod_minute:
            return True
        else:
            return False

    @classmethod
    def get_market_phase(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> MarketPhase:
        """현재 장 단계(phase) 반환

        Returns:
            MarketPhase enum
        """
        hours = cls.get_market_hours(market, dt)
        tz = pytz.timezone(hours['timezone'])

        if dt is None:
            dt = datetime.now(tz)
        elif dt.tzinfo is None:
            dt = tz.localize(dt)

        if dt.weekday() >= 5:
            return MarketPhase.CLOSED

        # 공휴일은 CLOSED
        if cls._is_holiday(market, dt):
            return MarketPhase.CLOSED

        current_time = dt.time()
        market_open = hours['market_open']
        market_close = hours['market_close']
        pre_auction_start = hours.get('pre_auction_start', time(8, 30))
        opening_protection_end = hours.get('opening_protection_end', time(9, 5))
        closing_auction_start = hours.get('closing_auction_start', cls.DEFAULT_CLOSING_AUCTION_START)

        if current_time < pre_auction_start:
            return MarketPhase.PRE_MARKET
        elif current_time < market_open:
            return MarketPhase.PRE_AUCTION
        elif current_time < opening_protection_end:
            return MarketPhase.OPENING_PROTECTION
        elif current_time < closing_auction_start:
            return MarketPhase.MARKET_OPEN
        elif current_time <= market_close:
            return MarketPhase.CLOSING_CUTOFF
        else:
            return MarketPhase.POST_MARKET

    @classmethod
    def is_new_buy_blocked(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> bool:
        """신규 매수 차단 시간인지 확인

        장 마감 직전(15:20 이후), 동시호가, 장 시작 보호 시간에는 신규 매수 차단.
        서킷브레이커/VI 발동 중에도 차단.

        🔴 **이 함수는 현재 매매 경로에 결선돼 있지 않다** — 프로덕션 호출자 0건
        (테스트만 호출). "이 함수가 있으니 12시 이후엔 안 산다"고 읽지 말 것.
        실제 매수를 막는 유일한 시간 게이트는 `can_place_order()` 이고, 거기엔
        `should_stop_buying`(12시 컷오프)이 들어 있지 않다.

        결선하려면: `can_place_order()` 를 고쳐야 한다
        (`core/orders/order_executor.place_buy_order` 가 호출하는 함수). 결선하면
        신규 매수가 12시부터 멈추므로 **라이브 매매 동작이 바뀐다** — 사장님 승인 없이
        결선하지 말 것. 결선 시 `get_today_info()` 배너도 함께 고칠 것.

        Returns:
            True면 신규 매수 불가
        """
        phase = cls.get_market_phase(market, dt)
        if phase in (
            MarketPhase.CLOSED, MarketPhase.PRE_MARKET, MarketPhase.PRE_AUCTION,
            MarketPhase.CLOSING_CUTOFF, MarketPhase.CLOSING_AUCTION, MarketPhase.POST_MARKET
        ):
            return True

        # 서킷브레이커 확인
        cb = get_circuit_breaker_state()
        if cb.is_market_halted(dt):
            return True

        # should_stop_buying도 체크
        return cls.should_stop_buying(market, dt)

    @classmethod
    def is_opening_protection(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> bool:
        """장 시작 직후 보호 시간대인지 확인 (09:00~09:05)"""
        return cls.get_market_phase(market, dt) == MarketPhase.OPENING_PROTECTION

    @classmethod
    def is_pre_auction(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> bool:
        """동시호가 시간대인지 확인 (08:30~09:00)"""
        return cls.get_market_phase(market, dt) == MarketPhase.PRE_AUCTION

    @classmethod
    def is_closing_auction(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> bool:
        """마감 동시호가 시간대인지 확인 (15:20~15:30)"""
        phase = cls.get_market_phase(market, dt)
        return phase in (MarketPhase.CLOSING_CUTOFF, MarketPhase.CLOSING_AUCTION)

    @classmethod
    def can_place_order(cls, stock_code: str = None, market: str = 'KRX',
                        dt: Optional[datetime] = None) -> bool:
        """주문 가능 시간인지 확인 (동시호가 + 개별 종목 VI 포함)

        동시호가 시간대(08:30~09:00, 15:20~15:30)에는 주문 불가.

        Args:
            stock_code: 종목코드 (None이면 시장 전체만 체크)
            market: 시장 코드
            dt: 확인할 시간

        Returns:
            True면 주문 가능
        """
        if not cls.is_market_open(market, dt):
            return False

        # 동시호가 시간대 차단 (15:20~15:30 마감 동시호가)
        phase = cls.get_market_phase(market, dt)
        if phase in (MarketPhase.CLOSING_CUTOFF, MarketPhase.CLOSING_AUCTION):
            return False

        cb = get_circuit_breaker_state()
        if cb.is_market_halted(dt):
            return False

        if stock_code and cb.is_vi_active(stock_code):
            return False

        return True

    @classmethod
    def get_today_info(cls, market: str = 'KRX', dt: Optional[datetime] = None) -> str:
        """오늘 거래시간 정보를 문자열로 반환 (로깅용)

        🔴 **이 배너는 실제로 주문 경로에 결선된 제약만 적는다.** 근거는 두 곳뿐이다:

        1) `can_place_order()` — 주문의 유일한 시간 게이트.
           `core/orders/order_executor.place_buy_order`(매수) 와
           `place_sell_order(force=False)`(매도) 가 호출한다. 검사 항목:
           `is_market_open`(평일·비공휴일 + market_open~market_close) →
           마감 동시호가(`closing_auction_start` 이후) 차단 → 시장 전체 서킷브레이커 →
           종목 VI.
        2) `MarketHours.is_eod_liquidation_time()` — `core/trading_context` 의 매수
           판단이 이 시각 이후 `holding_period == "intraday"` 전략의 신규 매수만 막고,
           `bot/liquidation_handler` 의 일괄청산도 `should_liquidate_eod()` 기본구현에
           따라 intraday 보유분만 청산한다. swing 전략은 둘 다 해당 없음.

        ⚠️ `buy_cutoff_hour`(=`should_stop_buying`, KRX 기본 12시)는 **적지 않는다** —
        프로덕션 호출자가 0건이라 실매매에 걸리지 않기 때문이다. 예전 배너가
        "매수 중단: 12:00 이후"로 적혀 있었으나 반증이 매일 로그에 찍히고 있었다
        (2026-08-06 실측: 14거래일 166매수 중 8건이 12시 이후, 최대 15:09:32).
        배너에 제약을 추가하려면 **그 제약을 실행하는 프로덕션 호출자가 있는지부터
        확인할 것.** `tests/test_buy_stop_banner_matches_gate.py` 가 배너와
        `can_place_order()` 의 일치를 강제한다.

        Args:
            market: 시장 코드
            dt: 기준 날짜 (None이면 오늘). 특수일 설정 반영·테스트용.
        """
        hours = cls.get_market_hours(market, dt)

        info = f"[{market}] "
        if hours.get('is_special_day', False):
            reason = hours.get('reason', '특수일')
            info += f"[!] {reason}\n"

        # 주문이 막히는 시각 = get_market_phase() 가 CLOSING_CUTOFF 로 넘어가는 시각.
        # can_place_order() 가 그 phase 를 차단하므로 이 값이 실효 주문 마감이다.
        order_cutoff = hours.get('closing_auction_start', cls.DEFAULT_CLOSING_AUCTION_START)

        info += f"장 시작: {hours['market_open'].strftime('%H:%M')}\n"
        info += f"장 마감: {hours['market_close'].strftime('%H:%M')}\n"
        info += (
            f"주문 가능: {hours['market_open'].strftime('%H:%M')}~{order_cutoff.strftime('%H:%M')} "
            f"(이후 마감 동시호가 — 매수·매도 주문 모두 차단, EOD 청산만 force 로 예외)\n"
        )
        info += (
            "신규 매수: 위 주문 가능 시간 내내 허용 — 시각 기준 매수 컷오프 없음 "
            "(서킷브레이커·종목 VI 발동 시에만 차단)\n"
        )
        info += (
            f"일괄 청산: {hours['eod_liquidation_hour']:02d}:{hours['eod_liquidation_minute']:02d} "
            f"— intraday 전략 보유분만 청산하며 이 시각 이후 intraday 신규매수도 차단 "
            f"(swing 전략은 해당 없음)"
        )

        return info


# 하위 호환성을 위한 전역 함수들 (기존 코드와의 호환성 유지)
def now_kst() -> datetime:
    """현재 한국 시간 반환"""
    return datetime.now(pytz.timezone('Asia/Seoul'))


def is_market_open(dt: datetime = None) -> bool:
    """장중 시간인지 확인 (KRX 기준)"""
    return MarketHours.is_market_open('KRX', dt)


def is_before_market_open(dt: datetime = None) -> bool:
    """장 시작 전인지 확인 (KRX 기준)"""
    return MarketHours.is_before_market_open('KRX', dt)


def get_market_status() -> str:
    """시장 상태 반환 (KRX 기준)"""
    return MarketHours.get_market_status('KRX')


# 편의 함수
KST = pytz.timezone('Asia/Seoul')
