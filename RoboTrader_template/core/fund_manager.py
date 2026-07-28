"""
자금 관리 시스템
================

공통 자금관리 인터페이스(FundManagerProtocol)와 실제 구현(FundManager)을 제공합니다.

C3 설계 원칙:
- FundManagerProtocol: typing.Protocol 기반 구조적 서브타이핑 인터페이스
  - reserve(amount, order_id) → bool
  - commit(order_id, actual_amount) → None   (예약 → 투자 확정)
  - release(amount, stock_code) → None       (매도 후 투자 회수)
  - realize(pnl) → None                      (실현 손익 반영)
  - available_balance → float                (즉시 사용 가능 자금)
  - total_invested → float                   (현재 투자 중 금액)
- FundManager: 실제 구현 (기존 API 유지 + Protocol 호환 프로퍼티 추가)
- MockFundManager: BacktestEngine용 인메모리 경량 구현
"""
import threading
from datetime import datetime
from typing import Callable, Dict, FrozenSet, Optional, Set, Tuple
try:
    from typing import Protocol, runtime_checkable
except ImportError:  # Python 3.7 호환
    from typing_extensions import Protocol, runtime_checkable  # type: ignore[assignment]
from utils.logger import setup_logger


# ============================================================================
# 공통 인터페이스 (Protocol)
# ============================================================================

@runtime_checkable
class FundManagerProtocol(Protocol):
    """
    자금관리 공통 인터페이스 (구조적 서브타이핑).

    VirtualTradingManager, BacktestEngine의 MockFundManager, FundManager 모두
    이 인터페이스를 구현해야 한다.

    메서드 의미:
        reserve(amount, order_id)    — 매수 전 자금 예약 (available_balance 감소)
        commit(order_id, actual)     — 체결 확인 (reserved → invested)
        release(amount, stock_code)  — 매도 후 자금 회수 (invested → available)
        realize(pnl)                 — 실현 손익 반영 (total 조정)
        available_balance            — 즉시 사용 가능 자금
        total_invested               — 현재 투자 중 금액 합계
    """

    def reserve(self, amount: float, order_id: str = "") -> bool:
        """자금 예약. 성공 시 True, 잔고 부족 시 False."""
        ...

    def commit(self, order_id: str, actual_amount: float) -> None:
        """예약 → 투자 확정 (체결 완료 시 호출)."""
        ...

    def release(self, amount: float, stock_code: str = "") -> None:
        """매도 완료 후 투자 자금 회수."""
        ...

    def realize(self, pnl: float) -> None:
        """실현 손익을 total에 반영 (양수=이익, 음수=손실)."""
        ...

    @property
    def available_balance(self) -> float:
        """즉시 사용 가능 자금."""
        ...

    @property
    def total_invested(self) -> float:
        """현재 투자 중 금액 합계."""
        ...


# ============================================================================
# BacktestEngine용 인메모리 경량 구현
# ============================================================================

class MockFundManager:
    """
    BacktestEngine용 인메모리 자금관리 (FundManagerProtocol 호환).

    DB/스레드락 없이 순수 파이썬 연산만 사용.
    동일 매매 시나리오에서 FundManager와 ±0.01% 이내 일치를 보장.

    Usage:
        mock_fm = MockFundManager(initial_capital=10_000_000)
        mock_fm.reserve(1_000_000, "ORD1")
        mock_fm.commit("ORD1", 950_000)
        mock_fm.release(950_000)
        print(mock_fm.available_balance)
    """

    def __init__(self, initial_capital: float = 0.0):
        self._total = initial_capital
        self._available = initial_capital
        self._invested = 0.0
        self._reserved: Dict[str, float] = {}

    # -- FundManagerProtocol 구현 --

    def reserve(self, amount: float, order_id: str = "") -> bool:
        amount = float(amount)
        if self._available < amount:
            return False
        self._available -= amount
        if order_id:
            self._reserved[order_id] = self._reserved.get(order_id, 0) + amount
        return True

    def commit(self, order_id: str, actual_amount: float) -> None:
        actual_amount = float(actual_amount)
        reserved = self._reserved.pop(order_id, 0.0)
        # 예약 해제 후 투자 이동; 차액은 available로 반환
        diff = reserved - actual_amount
        self._available += diff
        self._invested += actual_amount

    def release(self, amount: float, stock_code: str = "") -> None:
        amount = float(amount)
        self._invested = max(0.0, self._invested - amount)
        self._available += amount

    def realize(self, pnl: float) -> None:
        pnl = float(pnl)
        self._total = max(0.0, self._total + pnl)
        # available 조정: total 변화분을 available에 흡수
        self._available = max(0.0, self._available + pnl)

    @property
    def available_balance(self) -> float:
        return self._available

    @property
    def total_invested(self) -> float:
        return self._invested

    # -- 직접 접근 편의 프로퍼티 (BacktestEngine 내부용) --

    @property
    def total_funds(self) -> float:
        return self._total


class FundManager:
    """
    자금 관리 클래스
    
    주요 기능:
    1. 가용 자금 추적
    2. 주문 중 자금 예약
    3. 동시 매수시 자금 중복 계산 방지
    4. 포지션 사이징 관리
    5. 동시 보유 종목 수 제한 enforcement
    6. 실제 계좌와의 잔고 동기화
    7. 익절/손절 후 재매수 쿨다운 관리
    """
    
    def __init__(self, initial_funds: float = 0, max_position_count: int = 20,
                 max_daily_loss_ratio: float = 0.1,
                 strategy_max_pct_provider: Optional[Callable[[str], float]] = None,
                 max_daily_loss_ratio_per_strategy: float = 0.05):
        """
        초기화

        Args:
            initial_funds: 초기 자금 (0이면 API에서 조회)
            max_position_count: 동시 보유 최대 종목 수
            max_daily_loss_ratio: 일일 최대 손실 비율 (기본 10%)
            strategy_max_pct_provider: 전략명 → max_capital_pct 콜백 (다전략 환경에서 봇이 주입)
            max_daily_loss_ratio_per_strategy: 전략별 일일 최대 손실 비율 (기본 5%)
        """
        self.logger = setup_logger(__name__)
        self._lock = threading.RLock()

        # 자금 관리
        self.total_funds = initial_funds
        self.available_funds = initial_funds
        self.reserved_funds = 0.0  # 주문 중인 금액
        self.invested_funds = 0.0  # 투자 중인 금액

        # 주문별 예약 금액 추적
        self.order_reservations: Dict[str, float] = {}  # order_id -> reserved_amount

        # 전략별 투자 추적
        self._invested_by_strategy: Dict[str, float] = {}  # strategy_name -> invested amount
        self._strategy_max_pct_provider: Optional[Callable[[str], float]] = strategy_max_pct_provider

        # 설정
        self.max_position_ratio = 0.09  # 종목당 최대 투자 비율 (9%)
        self.max_total_investment_ratio = 0.9  # 전체 자금 대비 최대 투자 비율 (90%)

        # 동시 보유 종목 수 제한
        self.max_position_count = max_position_count
        # 보유 레지스트리 = (종목코드, owner) 엔트리 집합.
        # stock_code 단독 키였을 때는 두 전략이 같은 종목을 보유하다 한 전략이
        # 매도하면 discard 가 코드를 통째로 지워, 남은 전략의 보유가
        # position_count·can_add_position 한도에서 사라졌다(2026-07-28 라이브 실증:
        # 037230 = ma5 1433주 + ma20 141주 → ma5 매도 후 보유 30 vs 실보유 31).
        # owner=None 은 레거시(실주문 경로 등 owner 를 안전히 알 수 없는 호출).
        self._position_entries: Set[Tuple[str, Optional[str]]] = set()

        # 익절/손절 후 재매수 쿨다운 (종목코드 → 쿨다운 만료 시각)
        self._sell_cooldowns: Dict[str, datetime] = {}
        self.sell_cooldown_minutes = 30  # 매도 후 재매수 금지 시간 (분)

        # 잔고 동기화 추적
        self._last_sync_time: Optional[datetime] = None
        self._sync_discrepancy_count = 0  # 연속 불일치 횟수

        # 일일 실현 손실 추적
        self.max_daily_loss_ratio: float = max_daily_loss_ratio  # 일일 최대 손실 비율
        self.max_daily_loss_ratio_per_strategy: float = max_daily_loss_ratio_per_strategy
        self._daily_realized_loss: float = 0.0   # 당일 누적 실현 손실액 (양수 = 손실)
        self._daily_loss_date: str = ""           # 마지막 리셋 날짜 (YYYY-MM-DD)
        self._daily_realized_loss_by_strategy: Dict[str, float] = {}  # strategy_name -> loss

        self.logger.info(f"💰 자금 관리자 초기화 완료 - 초기자금: {initial_funds:,.0f}원, "
                        f"최대 보유: {max_position_count}종목")
    
    def update_total_funds(self, new_total: float) -> None:
        """총 자금 업데이트"""
        with self._lock:
            old_total = self.total_funds
            self.total_funds = new_total
            
            # 가용 자금 재계산
            self.available_funds = new_total - self.reserved_funds - self.invested_funds
            
            self.logger.info(f"총 자금 업데이트: {old_total:,.0f}원 → {new_total:,.0f}원 (가용: {self.available_funds:,.0f}원)")
    
    def get_max_buy_amount(self, stock_code: str) -> float:
        """
        종목별 최대 매수 가능 금액 계산
        
        Args:
            stock_code: 종목코드
            
        Returns:
            float: 최대 매수 가능 금액
        """
        with self._lock:
            # 종목당 최대 투자 금액
            max_per_stock = self.total_funds * self.max_position_ratio
            
            # 전체 투자 한도에서 현재 투자 중인 금액을 뺀 나머지
            max_total_investment = self.total_funds * self.max_total_investment_ratio
            remaining_investment_capacity = max_total_investment - self.invested_funds - self.reserved_funds
            
            # 가용 자금 한도
            available_limit = self.available_funds
            
            # 세 조건 중 가장 작은 값
            max_amount = min(max_per_stock, remaining_investment_capacity, available_limit)
            max_amount = max(0, max_amount)  # 음수 방지

            return max_amount
    
    def reserve_funds(self, order_id: str, amount: float, *, strategy_name: str = "") -> bool:
        """
        자금 예약 (주문 실행 전)

        Args:
            order_id: 주문 ID
            amount: 예약할 금액
            strategy_name: 전략명 (keyword-only). 지정 시 전략별 상한 체크.

        Returns:
            bool: 예약 성공 여부
        """
        with self._lock:
            amount = float(amount)

            # 전략별 자금 상한 체크
            if strategy_name and self._strategy_max_pct_provider is not None and self.total_funds > 0:
                max_pct = self._strategy_max_pct_provider(strategy_name)
                cap = self.total_funds * max_pct
                current = self._invested_by_strategy.get(strategy_name, 0.0)
                if current + amount > cap:
                    self.logger.info(
                        f"[{strategy_name}] 전략별 자금 상한 초과: "
                        f"현재투자 {current:,.0f}원 + 요청 {amount:,.0f}원 > 상한 {cap:,.0f}원 "
                        f"({max_pct:.0%})"
                    )
                    return False

            if self.available_funds < amount:
                self.logger.info(f"자금 부족: 요청 {amount:,.0f}원, 가용 {self.available_funds:,.0f}원")
                return False

            if order_id in self.order_reservations:
                self.logger.warning(f"⚠️ 이미 예약된 주문: {order_id}")
                return False

            # 자금 예약
            self.available_funds -= amount
            self.reserved_funds += amount
            self.order_reservations[order_id] = amount

            # 전략별 투자 누적
            if strategy_name:
                self._invested_by_strategy[strategy_name] = (
                    self._invested_by_strategy.get(strategy_name, 0.0) + amount
                )

            return True
    
    def confirm_order(self, order_id: str, actual_amount: float) -> None:
        """
        주문 체결 확인 (예약 → 투자)

        Args:
            order_id: 주문 ID
            actual_amount: 실제 체결 금액 (수수료 미포함 순수 체결 금액)

        Note:
            매수 수수료는 여기서 차감하지 않는다. 매도 시 실현손익 산식이
            buy_commission을 이미 포함하고 있고(order_monitor._handle_full_fill,
            order_timeout 매도 부분체결, trading_decision_engine 가상매도) 그
            손익은 adjust_pnl로 total_funds에 반영된다. 따라서 체결 시점에
            available_funds에서 또 차감하면 이중계상이며, total_funds는 손대지
            않으므로 정합성 등식
            (total == available + reserved + invested)이 매수 1건마다
            수수료만큼 깨진다. 그 갭은 다음 매도의 adjust_pnl 재계산으로 조용히
            지워져서, EOD 정합성 CRITICAL이 "당일 마지막 자금 이벤트가 매수인지
            매도인지"에 따라 비결정적으로 발화했다(2026-07-27 329원 / 07-21 69원).
            이 메서드는 자금을 계정 간 *이동*만 시키며 총액을 바꾸지 않는다.

            ⚠️ 되돌리지 말 것: 매수 수수료는 "매도 시 1회" 인식이 의도된 설계다.
            release_investment()는 순수 매수원가만 회수하도록 호출되고
            (order_monitor.py:387, order_timeout.py:226,
             trading_decision_engine.py:880, liquidation_handler.py:340)
            같은 자리의 pnl 산식이 buy_commission을 이미 포함한다. 그 결과
            체결~매도 구간 동안 total_funds/available_funds는 미청산 포지션의
            매수 수수료만큼 실제 현금을 과대표시하며(2억 북 기준 13,200원,
            0.0066%) 매도 시점에 정확히 자동 해소된다. 이 과대표시를 없애려고
            체결 시점 차감을 되살리면 수수료가 두 번 청구되고 위 등식이 다시
            깨진다.
        """
        with self._lock:
            actual_amount = float(actual_amount)

            if order_id not in self.order_reservations:
                self.logger.warning(f"⚠️ 예약되지 않은 주문: {order_id}")
                return

            reserved_amount = self.order_reservations[order_id]

            # 예약 해제
            self.reserved_funds -= reserved_amount
            del self.order_reservations[order_id]

            # 투자 금액으로 이동 (순수 체결 금액만 - 매도 시 정확한 회수를 위해)
            self.invested_funds += actual_amount

            # 차액 정산: 순수 체결금액 기준. 예약>체결이면 미체결분 환불,
            # 체결>예약이면 초과 체결분만 추가 차감. (수수료는 위 Note 참조)
            diff = reserved_amount - actual_amount
            self.available_funds += diff
            if diff < 0:
                # 예약보다 많이 체결 → 초과분 추가 차감
                self.logger.warning(f"💰 주문 체결: {order_id} - 투자: {actual_amount:,.0f}원, "
                                  f"예약: {reserved_amount:,.0f}원, "
                                  f"추가차감: {-diff:,.0f}원 (체결>예약)")
    
    def reverse_confirm(self, order_id: str, amount: float) -> None:
        """체결 확인 취소 (오탐지 복구용) - invested → reserved"""
        with self._lock:
            amount = float(amount)
            self.invested_funds = max(0, self.invested_funds - amount)
            self.order_reservations[order_id] = amount
            self.reserved_funds += amount
            self.logger.info(f"체결 확인 취소: {order_id}, 금액: {amount:,.0f}")

    def transfer_reservation(self, old_id: str, new_id: str) -> bool:
        """예약 ID 변경 (원자적 연산)"""
        with self._lock:
            if old_id not in self.order_reservations:
                return False
            amount = self.order_reservations.pop(old_id)
            self.order_reservations[new_id] = amount
            return True

    def has_reservation(self, order_id: str) -> bool:
        """주문 예약 존재 여부 확인"""
        with self._lock:
            return self.order_reservations.get(order_id, 0) > 0

    def cancel_order(self, order_id: str) -> None:
        """
        주문 취소 (예약 해제)

        Args:
            order_id: 주문 ID
        """
        with self._lock:
            if order_id not in self.order_reservations:
                self.logger.warning(f"⚠️ 예약되지 않은 주문: {order_id}")
                return
            
            reserved_amount = self.order_reservations[order_id]
            
            # 예약 해제
            self.reserved_funds -= reserved_amount
            self.available_funds += reserved_amount
            del self.order_reservations[order_id]
            
            self.logger.debug(f"💰 주문 취소: {order_id} - 환불: {reserved_amount:,.0f}원")
    
    def release_investment(self, amount: float, stock_code: str = "",
                           owner: Optional[str] = None) -> None:
        """
        투자 자금 회수 (매도 완료시)

        Args:
            amount: 회수할 금액
            stock_code: 종목코드 (보유 종목 추적용)
            owner: 소유 전략 표기 (슬롯 객체의 owner_strategy_name).
                   다중 소유 종목에서 남의 보유를 지우지 않으려면 필수.
        """
        with self._lock:
            amount = float(amount)
            # 음수 방지
            if amount > self.invested_funds:
                self.logger.warning(
                    f"⚠️ 회수 금액({amount:,.0f})이 투자금({self.invested_funds:,.0f})을 초과. "
                    f"invested_funds를 0으로 보정"
                )
                amount = self.invested_funds
            
            self.invested_funds -= amount
            self.available_funds += amount
            
            # 보유 종목에서 제거 (RLock 재진입 — remove_position 이 같은 락을 잡는다)
            if stock_code:
                self.remove_position(stock_code, owner)

            self.logger.info(f"💰 투자 회수: {amount:,.0f}원 "
                           f"(가용: {self.available_funds:,.0f}원, "
                           f"보유종목: {len(self.current_position_codes)}개)")

    def adjust_pnl(self, pnl: float) -> None:
        """매매 손익을 자금에 반영

        Args:
            pnl: 손익 금액 (양수=이익, 음수=손실)
        """
        with self._lock:
            pnl = float(pnl)
            self.total_funds = max(0, self.total_funds + pnl)
            self.available_funds = self.total_funds - self.reserved_funds - self.invested_funds
            if self.available_funds < 0:
                self.available_funds = 0
            self.logger.info(f"매매 손익 반영: {pnl:+,.0f}원 (총자금: {self.total_funds:,.0f}원)")
            # 손실 발생 시 일일 손실 누적
            if pnl < 0:
                self.record_realized_loss(-pnl)

    # =========================================================================
    # 일일 손실 한도 관리
    # =========================================================================

    def record_realized_loss(self, amount: float, strategy_name: str = "") -> None:
        """당일 실현 손실 기록

        Args:
            amount: 손실 금액 (양수값, 예: 50000 = 5만원 손실)
            strategy_name: 전략명 (지정 시 전략별 손실도 누적)
        """
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            if self._daily_loss_date != today:
                # 날짜가 바뀌면 자동 리셋
                self._daily_realized_loss = 0.0
                self._daily_realized_loss_by_strategy = {}
                self._daily_loss_date = today
            self._daily_realized_loss += float(amount)
            if strategy_name:
                self._daily_realized_loss_by_strategy[strategy_name] = (
                    self._daily_realized_loss_by_strategy.get(strategy_name, 0.0) + float(amount)
                )
            loss_ratio = (self._daily_realized_loss / self.total_funds) if self.total_funds > 0 else 0
            self.logger.info(
                f"일일 손실 누적: {self._daily_realized_loss:,.0f}원 "
                f"({loss_ratio*100:.1f}% / 한도 {self.max_daily_loss_ratio*100:.1f}%)"
                + (f" [{strategy_name}]" if strategy_name else "")
            )

    def is_daily_loss_limit_hit(self, strategy_name: Optional[str] = None) -> bool:
        """일일 손실 한도 초과 여부 확인

        Args:
            strategy_name: 전략명 지정 시 해당 전략의 손실 한도 체크.
                           None(기본)이면 전체 누적 손실 체크.

        Returns:
            bool: 한도 초과 시 True (매수 차단 필요)
        """
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            if self._daily_loss_date != today:
                # 날짜가 바뀌면 리셋 후 False
                self._daily_realized_loss = 0.0
                self._daily_realized_loss_by_strategy = {}
                self._daily_loss_date = today
                return False
            if self.total_funds <= 0:
                return False
            if strategy_name is not None:
                strat_loss = self._daily_realized_loss_by_strategy.get(strategy_name, 0.0)
                strat_ratio = strat_loss / self.total_funds
                return strat_ratio >= self.max_daily_loss_ratio_per_strategy
            loss_ratio = self._daily_realized_loss / self.total_funds
            return loss_ratio >= self.max_daily_loss_ratio

    def reset_daily_loss(self) -> None:
        """일일 손실 수동 리셋 (장 시작 시 또는 테스트용)"""
        with self._lock:
            self._daily_realized_loss = 0.0
            self._daily_realized_loss_by_strategy = {}
            self._daily_loss_date = datetime.now().strftime("%Y-%m-%d")
            self.logger.info("일일 손실 카운터 리셋")

    def calculate_buy_cost(self, amount: float) -> float:
        """매수 시 실제 비용 (주문금액 + 수수료)

        Args:
            amount: 주문 금액

        Returns:
            float: 수수료 포함 실제 비용
        """
        from config.constants import COMMISSION_RATE
        return amount * (1 + COMMISSION_RATE)

    def calculate_sell_proceeds(self, amount: float) -> float:
        """매도 시 실제 수령액 (매도금 - 수수료 - 거래세)

        Args:
            amount: 매도 금액

        Returns:
            float: 수수료/세금 차감 후 실제 수령액
        """
        from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE
        return amount * (1 - COMMISSION_RATE - SECURITIES_TAX_RATE)

    @property
    def current_position_codes(self) -> FrozenSet[str]:
        """현재 보유 종목 코드 집합 (distinct stock_code — 하위호환 뷰).

        내부 레지스트리는 (code, owner) 엔트리지만, 보유 "종목 수"의 의미는
        기존과 동일한 distinct 종목 수다(보유한도·리포트·텔레그램 표기).

        frozenset 을 돌려주는 것은 의도적이다 — 레거시 in-place 변이
        (codes.add(x) / codes.discard(x))가 스냅샷에 조용히 먹히는 대신
        AttributeError 로 드러나게 한다. 등록·해제는 add_position /
        remove_position 만 사용해야 owner 가 기록된다.
        """
        with self._lock:
            return frozenset(code for code, _ in self._position_entries)

    @current_position_codes.setter
    def current_position_codes(self, codes) -> None:
        """전체 교체 (하위호환) — 대입된 코드는 owner=None 엔트리로 등록."""
        with self._lock:
            self._position_entries = {(code, None) for code in (codes or set())}

    def can_add_position(self, stock_code: str = "") -> bool:
        """
        새 포지션 추가 가능 여부 확인
        
        Args:
            stock_code: 종목코드
            
        Returns:
            bool: 추가 가능 여부
        """
        with self._lock:
            codes = self.current_position_codes  # 스냅샷 1회 (property 재구성 방지)

            # 이미 보유 중인 종목이면 분할매수로 허용 (별도 체크)
            if stock_code and stock_code in codes:
                return True

            if len(codes) >= self.max_position_count:
                self.logger.warning(
                    f"⚠️ 동시 보유 종목 수 초과: 현재 {len(codes)}개 "
                    f"/ 최대 {self.max_position_count}개"
                )
                return False
            return True

    def add_position(self, stock_code: str, owner: Optional[str] = None) -> None:
        """보유 종목 추가

        Args:
            stock_code: 종목코드
            owner: 소유 전략 표기 (슬롯 객체의 owner_strategy_name).
                   같은 (code, owner) 재추가는 멱등. None 이면 레거시 엔트리.
        """
        with self._lock:
            self._position_entries.add((stock_code, owner or None))

    def remove_position(self, stock_code: str, owner: Optional[str] = None) -> None:
        """보유 종목 제거 (멱등)

        owner 를 지정하면 정확히 그 (code, owner) 엔트리만 제거한다. 없으면 no-op
        (한 번의 매도에 release_investment + remove_position 이 연달아 호출되는
        기존 이중제거 경로가 있으므로 멱등이 필수).

        owner 미지정 시에는 해당 종목의 엔트리가 정확히 1개일 때만 제거한다.
        2개 이상(다중 소유)에서의 모호한 제거가 이번 결함의 본질이므로,
        지우지 않고 경고만 남긴다.
        """
        with self._lock:
            owner = owner or None
            if owner is not None:
                self._position_entries.discard((stock_code, owner))
                return

            matched = [e for e in self._position_entries if e[0] == stock_code]
            if len(matched) == 1:
                self._position_entries.discard(matched[0])
            elif len(matched) > 1:
                owners = [e[1] for e in matched]
                self.logger.warning(
                    f"⚠️ [모호제거] {stock_code} 보유 owner {len(matched)}개({owners}) — "
                    f"owner 미지정 제거 요청을 보류합니다 (다중소유 오제거 방지)"
                )

    def set_sell_cooldown(self, stock_code: str, reason: str = "") -> None:
        """
        매도 후 재매수 쿨다운 설정
        
        Args:
            stock_code: 종목코드
            reason: 매도 사유 (손절/익절 등)
        """
        from utils.korean_time import now_kst
        from datetime import timedelta
        with self._lock:
            cooldown_until = now_kst() + timedelta(minutes=self.sell_cooldown_minutes)
            self._sell_cooldowns[stock_code] = cooldown_until
            self.logger.debug(
                f"💰 {stock_code} 재매수 쿨다운 설정: {self.sell_cooldown_minutes}분 "
                f"(사유: {reason})"
            )

    def is_sell_cooldown_active(self, stock_code: str) -> bool:
        """
        매도 후 재매수 쿨다운 활성 여부
        
        Args:
            stock_code: 종목코드
            
        Returns:
            bool: 쿨다운 활성 여부
        """
        from utils.korean_time import now_kst
        with self._lock:
            if stock_code not in self._sell_cooldowns:
                return False
            
            cooldown_until = self._sell_cooldowns[stock_code]
            if now_kst() >= cooldown_until:
                # 쿨다운 만료 → 정리
                del self._sell_cooldowns[stock_code]
                return False
            return True

    def sync_with_account(self, actual_available: float, actual_invested: float) -> None:
        """
        실제 계좌 잔고와 동기화
        
        Args:
            actual_available: 실제 가용 현금
            actual_invested: 실제 투자 금액 (평가금액)
        """
        from utils.korean_time import now_kst
        with self._lock:
            discrepancy = abs(
                (self.available_funds + self.reserved_funds) - actual_available
            )
            invest_discrepancy = abs(self.invested_funds - actual_invested)
            
            threshold = max(self.total_funds * 0.01, 10000)  # 1% 또는 1만원
            
            if discrepancy > threshold or invest_discrepancy > threshold:
                self._sync_discrepancy_count += 1
                self.logger.warning(
                    f"⚠️ 잔고 불일치 감지 (연속 {self._sync_discrepancy_count}회): "
                    f"내부 가용={self.available_funds:,.0f} vs 실제={actual_available:,.0f}, "
                    f"내부 투자={self.invested_funds:,.0f} vs 실제={actual_invested:,.0f}"
                )
                
                # 3회 연속 불일치 시 실제 계좌 기준으로 보정
                if self._sync_discrepancy_count >= 3:
                    old_available = self.available_funds
                    self.available_funds = actual_available - self.reserved_funds
                    self.invested_funds = actual_invested
                    self.total_funds = self.available_funds + self.reserved_funds + self.invested_funds
                    self.logger.warning(
                        f"🔧 잔고 강제 보정: 가용 {old_available:,.0f} → {self.available_funds:,.0f}"
                    )
                    self._sync_discrepancy_count = 0
            else:
                self._sync_discrepancy_count = 0
            
            self._last_sync_time = now_kst()

    def verify_fund_integrity(self) -> dict:
        """자금 정합성 검증 - 내부 등식 확인

        등식: total_funds == available_funds + reserved_funds + invested_funds

        Returns:
            dict: 검증 결과 (is_valid, discrepancy 등)
        """
        with self._lock:
            # 내부 등식: total = available + reserved + invested
            expected_total = self.available_funds + self.reserved_funds + self.invested_funds
            discrepancy = abs(self.total_funds - expected_total)

            result = {
                'total_funds': self.total_funds,
                'available_funds': self.available_funds,
                'reserved_funds': self.reserved_funds,
                'invested_funds': self.invested_funds,
                'calculated_total': expected_total,
                'discrepancy': discrepancy,
                'is_valid': discrepancy < 1.0,  # 1원 미만 오차 허용
                'position_count': len(self.current_position_codes),
            }

            if not result['is_valid']:
                self.logger.error(
                    f"자금 정합성 오류! total={self.total_funds:,.0f} != "
                    f"available({self.available_funds:,.0f}) + reserved({self.reserved_funds:,.0f}) + "
                    f"invested({self.invested_funds:,.0f}) = {expected_total:,.0f}, "
                    f"차이={discrepancy:,.0f}원"
                )

            return result

    # =========================================================================
    # FundManagerProtocol 호환 인터페이스 (C3)
    # =========================================================================
    # 기존 메서드(reserve_funds, confirm_order, release_investment, adjust_pnl)를
    # Protocol 표준명으로 위임한다. 기존 호출자는 영향 없음.

    def reserve(self, amount: float, order_id: str = "") -> bool:
        """FundManagerProtocol: reserve_funds 위임."""
        oid = order_id or f"_proto_{id(self)}"
        return self.reserve_funds(oid, amount)

    def commit(self, order_id: str, actual_amount: float) -> None:
        """FundManagerProtocol: confirm_order 위임."""
        self.confirm_order(order_id, actual_amount)

    def release(self, amount: float, stock_code: str = "") -> None:
        """FundManagerProtocol: release_investment 위임."""
        self.release_investment(amount, stock_code)

    def realize(self, pnl: float) -> None:
        """FundManagerProtocol: adjust_pnl 위임."""
        self.adjust_pnl(pnl)

    @property
    def available_balance(self) -> float:
        """FundManagerProtocol: available_funds 프로퍼티."""
        return self.available_funds

    @property
    def total_invested(self) -> float:
        """FundManagerProtocol: invested_funds 프로퍼티."""
        return self.invested_funds

    def get_status(self) -> Dict:
        """자금 현황 조회"""
        from utils.korean_time import now_kst
        with self._lock:
            # 만료된 쿨다운 정리
            _now = now_kst()
            expired = [k for k, v in self._sell_cooldowns.items() if _now >= v]
            for k in expired:
                del self._sell_cooldowns[k]

            return {
                'total_funds': self.total_funds,
                'available_funds': self.available_funds,
                'reserved_funds': self.reserved_funds,
                'invested_funds': self.invested_funds,
                'utilization_rate': (self.reserved_funds + self.invested_funds) / self.total_funds if self.total_funds > 0 else 0,
                'position_count': len(self.current_position_codes),
                'max_position_count': self.max_position_count,
                'active_cooldowns': len(self._sell_cooldowns),
                'last_sync_time': self._last_sync_time,
            }
