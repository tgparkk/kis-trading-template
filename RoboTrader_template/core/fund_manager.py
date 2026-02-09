"""
자금 관리 시스템
"""
import threading
from datetime import datetime
from typing import Dict, Optional, Set
from utils.logger import setup_logger


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
    
    def __init__(self, initial_funds: float = 0, max_position_count: int = 20):
        """
        초기화
        
        Args:
            initial_funds: 초기 자금 (0이면 API에서 조회)
            max_position_count: 동시 보유 최대 종목 수
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
        
        # 설정
        self.max_position_ratio = 0.09  # 종목당 최대 투자 비율 (9%)
        self.max_total_investment_ratio = 0.9  # 전체 자금 대비 최대 투자 비율 (90%)
        
        # 동시 보유 종목 수 제한
        self.max_position_count = max_position_count
        self.current_position_codes: Set[str] = set()  # 현재 보유 종목 코드
        
        # 익절/손절 후 재매수 쿨다운 (종목코드 → 쿨다운 만료 시각)
        self._sell_cooldowns: Dict[str, datetime] = {}
        self.sell_cooldown_minutes = 30  # 매도 후 재매수 금지 시간 (분)
        
        # 잔고 동기화 추적
        self._last_sync_time: Optional[datetime] = None
        self._sync_discrepancy_count = 0  # 연속 불일치 횟수
        
        self.logger.info(f"💰 자금 관리자 초기화 완료 - 초기자금: {initial_funds:,.0f}원, "
                        f"최대 보유: {max_position_count}종목")
    
    def update_total_funds(self, new_total: float):
        """총 자금 업데이트"""
        with self._lock:
            old_total = self.total_funds
            self.total_funds = new_total
            
            # 가용 자금 재계산
            self.available_funds = new_total - self.reserved_funds - self.invested_funds
            
            self.logger.info(f"💰 총 자금 업데이트: {old_total:,.0f}원 → {new_total:,.0f}원")
            self.logger.info(f"💰 가용 자금: {self.available_funds:,.0f}원")
    
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
            
            self.logger.debug(f"💰 {stock_code} 최대 매수 가능: {max_amount:,.0f}원 "
                            f"(종목한도: {max_per_stock:,.0f}, 투자여력: {remaining_investment_capacity:,.0f}, "
                            f"가용자금: {available_limit:,.0f})")
            
            return max_amount
    
    def reserve_funds(self, order_id: str, amount: float) -> bool:
        """
        자금 예약 (주문 실행 전)
        
        Args:
            order_id: 주문 ID
            amount: 예약할 금액
            
        Returns:
            bool: 예약 성공 여부
        """
        with self._lock:
            if self.available_funds < amount:
                self.logger.warning(f"⚠️ 자금 부족: 요청 {amount:,.0f}원, 가용 {self.available_funds:,.0f}원")
                return False
            
            if order_id in self.order_reservations:
                self.logger.warning(f"⚠️ 이미 예약된 주문: {order_id}")
                return False
            
            # 자금 예약
            self.available_funds -= amount
            self.reserved_funds += amount
            self.order_reservations[order_id] = amount
            
            self.logger.info(f"💰 자금 예약: {order_id} - {amount:,.0f}원 "
                           f"(가용: {self.available_funds:,.0f}원)")
            
            return True
    
    def confirm_order(self, order_id: str, actual_amount: float):
        """
        주문 체결 확인 (예약 → 투자)
        
        Args:
            order_id: 주문 ID
            actual_amount: 실제 체결 금액
        """
        with self._lock:
            if order_id not in self.order_reservations:
                self.logger.warning(f"⚠️ 예약되지 않은 주문: {order_id}")
                return
            
            reserved_amount = self.order_reservations[order_id]
            
            # 예약 해제
            self.reserved_funds -= reserved_amount
            del self.order_reservations[order_id]
            
            # 투자 금액으로 이동
            self.invested_funds += actual_amount
            
            # 차액은 가용 자금으로 반환
            refund = reserved_amount - actual_amount
            if refund > 0:
                self.available_funds += refund
            
            self.logger.info(f"💰 주문 체결: {order_id} - 투자: {actual_amount:,.0f}원, "
                           f"환불: {refund:,.0f}원")
    
    def cancel_order(self, order_id: str):
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
            
            self.logger.info(f"💰 주문 취소: {order_id} - 환불: {reserved_amount:,.0f}원")
    
    def release_investment(self, amount: float, stock_code: str = ""):
        """
        투자 자금 회수 (매도 완료시)
        
        Args:
            amount: 회수할 금액
            stock_code: 종목코드 (보유 종목 추적용)
        """
        with self._lock:
            # 음수 방지
            if amount > self.invested_funds:
                self.logger.warning(
                    f"⚠️ 회수 금액({amount:,.0f})이 투자금({self.invested_funds:,.0f})을 초과. "
                    f"invested_funds를 0으로 보정"
                )
                amount = self.invested_funds
            
            self.invested_funds -= amount
            self.available_funds += amount
            
            # 보유 종목에서 제거
            if stock_code and stock_code in self.current_position_codes:
                self.current_position_codes.discard(stock_code)
            
            self.logger.info(f"💰 투자 회수: {amount:,.0f}원 "
                           f"(가용: {self.available_funds:,.0f}원, "
                           f"보유종목: {len(self.current_position_codes)}개)")

    def can_add_position(self, stock_code: str = "") -> bool:
        """
        새 포지션 추가 가능 여부 확인
        
        Args:
            stock_code: 종목코드
            
        Returns:
            bool: 추가 가능 여부
        """
        with self._lock:
            # 이미 보유 중인 종목이면 분할매수로 허용 (별도 체크)
            if stock_code and stock_code in self.current_position_codes:
                return True
            
            if len(self.current_position_codes) >= self.max_position_count:
                self.logger.warning(
                    f"⚠️ 동시 보유 종목 수 초과: 현재 {len(self.current_position_codes)}개 "
                    f"/ 최대 {self.max_position_count}개"
                )
                return False
            return True

    def add_position(self, stock_code: str):
        """보유 종목 추가"""
        with self._lock:
            self.current_position_codes.add(stock_code)

    def remove_position(self, stock_code: str):
        """보유 종목 제거"""
        with self._lock:
            self.current_position_codes.discard(stock_code)

    def set_sell_cooldown(self, stock_code: str, reason: str = ""):
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
            self.logger.info(
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

    def sync_with_account(self, actual_available: float, actual_invested: float):
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

    def get_status(self) -> Dict:
        """자금 현황 조회"""
        with self._lock:
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
