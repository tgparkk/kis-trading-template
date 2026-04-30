"""
가상매매 관리 클래스
가상 잔고, 가상 매수/매도 등 가상매매 관련 로직을 담당

Emergency Sell Path (2026-03-01):
  DB 저장 실패 시에도 가상 매도는 메모리에서 완료 처리.
  실패한 DB 기록은 pending queue에 보관 후 비동기 재시도.
"""
import json
import os
from datetime import date, datetime
from typing import Dict, List, Optional
from utils.logger import setup_logger
from utils.rate_limited_logger import RateLimitedLogger
from utils.korean_time import now_kst


class VirtualTradingManager:
    """가상매매 전용 관리 클래스 (실전/가상 모드 지원)"""

    def __init__(self, db_manager=None, broker=None, paper_trading: bool = True):
        """
        초기화

        Args:
            db_manager: 데이터베이스 관리자
            broker: KISBroker (계좌 정보 조회용)
            paper_trading: 가상매매 모드 여부 (True: 가상, False: 실전)
        """
        self.logger = RateLimitedLogger(setup_logger(__name__))
        self.db_manager = db_manager
        self.broker = broker
        self.paper_trading = paper_trading

        # 잔고 관리
        self.virtual_investment_amount = 10000  # 기본값 (실제 계좌 조회 실패시 사용)
        self.virtual_balance = 0  # 현재 잔고 (가상 또는 실전)
        self.initial_balance = 0  # 시작 잔고 (수익률 계산용)

        # buy_time 추적: stock_code → buy_time(KST datetime)
        # DB의 virtual_trading_records.timestamp(BUY 행)과 동기화됨
        self._buy_times: Dict[str, datetime] = {}

        # Emergency Sell Path: DB 저장 실패 시 재시도 큐
        self._pending_sell_records: List[Dict] = []
        self._max_retries = 10
        self._fallback_path = os.path.join("logs", "pending_sells_fallback.json")
        self._last_retry_time: Optional[datetime] = None
        self._last_pending_log_time: Optional[datetime] = None

        # 잔고 초기화
        self._initialize_balance()

    def _initialize_balance(self) -> None:
        """잔고 초기화 (가상/실전 모드에 따라 다르게 처리)"""
        try:
            if self.paper_trading:
                # 🎯 가상매매 모드: 1000만원으로 설정
                self.virtual_balance = 10000000  # 1천만원
                self.initial_balance = self.virtual_balance
                self.virtual_investment_amount = 1000000  # 종목당 100만원
                self.logger.info(f"💰 가상 잔고 설정 (가상매매 모드): {self.virtual_balance:,.0f}원 (종목당: {self.virtual_investment_amount:,.0f}원)")
            else:
                # 🎯 실전 모드: 실제 계좌 잔고 조회
                self._initialize_real_balance()

        except Exception as e:
            self.logger.error(f"❌ 잔고 초기화 오류: {e}")
            # 오류 시 기본값 사용
            self.virtual_balance = 10000000
            self.initial_balance = self.virtual_balance
            self.virtual_investment_amount = 1000000

    def _initialize_real_balance(self) -> None:
        """실전 모드: 실제 계좌 잔고로 초기화"""
        try:
            if not self.broker:
                self.logger.warning("⚠️ API 매니저가 없어 실제 잔고 조회 불가 - 기본값 사용")
                self._use_default_balance()
                return

            # 실제 계좌 잔고 조회
            account_info = self.broker.get_account_balance()

            # KISBroker returns dict, KISAPIManager returns AccountInfo
            available = (account_info.get('available_cash', 0) if isinstance(account_info, dict)
                         else getattr(account_info, 'available_amount', 0))
            if account_info and available > 0:
                self.virtual_balance = available
                self.initial_balance = self.virtual_balance
                # 종목당 투자금액: 가용 잔고의 5% (최대 200만원, 최소 50만원)
                self.virtual_investment_amount = max(500000, min(2000000, self.virtual_balance * 0.05))
                self.logger.info(f"💰 실전 잔고 설정: {self.virtual_balance:,.0f}원 (종목당: {self.virtual_investment_amount:,.0f}원)")
            else:
                self.logger.warning("⚠️ 실제 잔고 조회 실패 - 기본값 사용")
                self._use_default_balance()

        except Exception as e:
            self.logger.error(f"❌ 실전 잔고 초기화 오류: {e}")
            self._use_default_balance()

    def _use_default_balance(self) -> None:
        """기본 잔고 설정 (조회 실패 시)"""
        self.virtual_balance = 10000000
        self.initial_balance = self.virtual_balance
        self.virtual_investment_amount = 1000000
        self.logger.warning(f"⚠️ 기본 잔고 사용: {self.virtual_balance:,.0f}원")

    def refresh_balance(self) -> None:
        """잔고 새로고침 (실전 모드에서 실제 잔고 재조회)"""
        if not self.paper_trading and self.broker:
            try:
                account_info = self.broker.get_account_balance()
                available = (account_info.get('available_cash', 0) if isinstance(account_info, dict)
                             else getattr(account_info, 'available_amount', 0))
                if account_info and available > 0:
                    old_balance = self.virtual_balance
                    self.virtual_balance = available
                    self.logger.info(f"💰 실전 잔고 새로고침: {old_balance:,.0f}원 → {self.virtual_balance:,.0f}원")
                    return True
            except Exception as e:
                self.logger.error(f"❌ 잔고 새로고침 오류: {e}")
        return False
    
    def update_virtual_balance(self, amount: float, transaction_type: str) -> None:
        """
        가상 잔고 업데이트
        
        Args:
            amount: 변경 금액 (양수: 입금, 음수: 출금)
            transaction_type: 거래 유형 ("매수", "매도")
        """
        try:
            old_balance = self.virtual_balance
            
            if transaction_type == "매수":
                # 매수 시 잔고 차감
                self.virtual_balance -= amount
            elif transaction_type == "매도":
                # 매도 시 잔고 증가
                self.virtual_balance += amount
            else:
                self.logger.warning(f"⚠️ 알 수 없는 거래 유형: {transaction_type}")
                return
            
            self.logger.debug(f"💰 가상 잔고 업데이트: {old_balance:,.0f}원 → {self.virtual_balance:,.0f}원 ({transaction_type}: {amount:,.0f}원)")
            
        except Exception as e:
            self.logger.error(f"❌ 가상 잔고 업데이트 오류: {e}")
    
    def get_virtual_balance(self) -> float:
        """현재 가상 잔고 반환"""
        return self.virtual_balance
    
    def get_virtual_profit_rate(self) -> float:
        """가상매매 수익률 계산
        
        Note: 현재 실현 손익(잔고 변동)만 반영됩니다.
        미실현 P&L(보유 포지션 평가손익)은 포함되지 않습니다.
        포지션 정보는 TradingStockManager에서 관리하므로,
        총 자산 기준 수익률은 별도로 계산해야 합니다.
        """
        try:
            if self.initial_balance > 0:
                return ((self.virtual_balance - self.initial_balance) / self.initial_balance) * 100
            return 0.0
        except Exception:
            return 0.0
    
    def can_buy(self, required_amount: float) -> bool:
        """매수 가능 여부 확인"""
        return self.virtual_balance >= required_amount
    
    def get_max_quantity(self, price: float) -> int:
        """주어진 가격에서 최대 매수 가능 수량"""
        try:
            if price <= 0:
                return 0
            max_amount = min(self.virtual_investment_amount, self.virtual_balance)
            qty = int(max_amount / price)
            return qty if qty > 0 else 0
        except Exception:
            return 0
    
    def execute_virtual_buy(self, stock_code: str, stock_name: str, price: float,
                          quantity: int, strategy: str, reason: str,
                          target_profit_rate: float = None,
                          stop_loss_rate: float = None) -> Optional[int]:
        """
        가상 매수 실행

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            price: 매수가격
            quantity: 매수수량
            strategy: 전략명
            reason: 매수사유
            target_profit_rate: 익절률 (None이면 DB에 NULL 저장)
            stop_loss_rate: 손절률 (None이면 DB에 NULL 저장)

        Returns:
            int: 매수 기록 ID (성공시) 또는 None (실패시)
        """
        try:
            price = float(price)
            quantity = int(quantity)
            from config.constants import COMMISSION_RATE
            total_cost = quantity * price
            commission = total_cost * COMMISSION_RATE
            total_cost_with_fee = total_cost + commission

            # 잔고 확인 (수수료 포함)
            if not self.can_buy(total_cost_with_fee):
                self.logger.warning(f"⚠️ 가상 잔고 부족: {self.virtual_balance:,.0f}원 < {total_cost:,.0f}원")
                return None

            # DB에 가상 매수 기록 저장
            if self.db_manager:
                buy_record_id = self.db_manager.save_virtual_buy(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    price=price,
                    quantity=quantity,
                    strategy=strategy,
                    reason=reason,
                    target_profit_rate=target_profit_rate,
                    stop_loss_rate=stop_loss_rate
                )
                
                if buy_record_id:
                    # 가상 잔고에서 매수 금액 + 수수료 차감
                    self.update_virtual_balance(total_cost_with_fee, "매수")

                    # buy_time 메모리에 기록 (DB timestamp와 동기화)
                    self._buy_times[stock_code] = now_kst()

                    profit_rate = self.get_virtual_profit_rate()
                    self.logger.info(f"💰 가상 매수 완료: {stock_code}({stock_name}) "
                                   f"{quantity}주 @{price:,.0f}원 (총 {total_cost:,.0f}원) "
                                   f"잔고: {self.virtual_balance:,.0f}원 ({profit_rate:+.2f}%)")

                    return buy_record_id
                else:
                    self.logger.error(f"❌ 가상 매수 DB 저장 실패: {stock_code}")
                    return None
            else:
                self.logger.warning("⚠️ DB 매니저가 없어 가상 매수 기록을 저장할 수 없음")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ 가상 매수 실행 오류: {e}")
            return None
    
    def execute_virtual_sell(self, stock_code: str, stock_name: str, price: float,
                           quantity: int, strategy: str, reason: str, buy_record_id: int) -> bool:
        """
        가상 매도 실행 (Emergency Sell Path 적용)

        핵심 원칙: 가상매매에서는 매도 판단이 DB 기록보다 중요하다.
        DB 저장이 실패해도 메모리 상태(잔고, 포지션)는 반드시 업데이트하고,
        실패한 DB 기록은 pending queue에 보관하여 비동기 재시도한다.

        Returns:
            bool: 매도 성공 여부 (메모리 업데이트 기준, DB 실패와 무관)
        """
        try:
            # 1단계: 메모리 상태 먼저 업데이트 (잔고 반영, 수수료+거래세 차감)
            from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE
            price = float(price)
            quantity = int(quantity)
            total_received = quantity * price
            sell_commission = total_received * COMMISSION_RATE
            sell_tax = total_received * SECURITIES_TAX_RATE
            net_received = total_received - sell_commission - sell_tax
            self.update_virtual_balance(net_received, "매도")

            profit_rate = self.get_virtual_profit_rate()
            self.logger.info(f"💰 가상 매도 완료 (메모리): {stock_code}({stock_name}) "
                           f"{quantity}주 @{price:,.0f}원 (총 {total_received:,.0f}원) "
                           f"잔고: {self.virtual_balance:,.0f}원 ({profit_rate:+.2f}%)")

            # 2단계: DB에 가상 매도 기록 저장 시도
            db_saved = False
            if self.db_manager:
                try:
                    db_saved = self.db_manager.save_virtual_sell(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        price=price,
                        quantity=quantity,
                        strategy=strategy,
                        reason=reason,
                        buy_record_id=buy_record_id
                    )
                except Exception as db_err:
                    self.logger.warning(
                        f"⚠️ {stock_code} 가상 매도 DB 저장 실패 - 메모리 큐에 보관: {db_err}"
                    )

            # 3단계: DB 저장 실패 시 pending queue에 보관
            if not db_saved:
                self.logger.warning(
                    f"⚠️ {stock_code} 가상 매도 DB 저장 실패 - 메모리 큐에 보관"
                )
                pending_record = {
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'price': float(price),
                    'quantity': int(quantity),
                    'strategy': strategy,
                    'reason': reason,
                    'buy_record_id': int(buy_record_id) if buy_record_id else None,
                    'sell_time': now_kst().isoformat(),
                    'retry_count': 0,
                }
                self._pending_sell_records.append(pending_record)

            # buy_time 메모리에서 제거 (포지션 청산)
            self._buy_times.pop(stock_code, None)

            # 메모리 업데이트는 이미 완료했으므로 항상 True 반환
            return True

        except Exception as e:
            self.logger.error(f"❌ 가상 매도 실행 오류: {e}")
            return False
    
    # =========================================================================
    # Emergency Sell Path: 재시도 큐 관리
    # =========================================================================

    def get_pending_sells_count(self) -> int:
        """대기 중인 미저장 매도 기록 수 반환"""
        return len(self._pending_sell_records)

    def retry_pending_sells(self) -> None:
        """
        pending queue의 매도 기록을 DB에 재저장 시도

        - 성공 시: queue에서 제거, INFO 로그
        - 실패 시: retry_count 증가, queue에 유지
        - 10회 초과 시: fallback JSON 파일에 저장 후 queue에서 제거
        """
        if not self._pending_sell_records:
            return

        if not self.db_manager:
            return

        succeeded = []
        fallback_records = []

        for i, record in enumerate(self._pending_sell_records):
            try:
                db_saved = self.db_manager.save_virtual_sell(
                    stock_code=record['stock_code'],
                    stock_name=record['stock_name'],
                    price=record['price'],
                    quantity=record['quantity'],
                    strategy=record['strategy'],
                    reason=record['reason'],
                    buy_record_id=record['buy_record_id']
                )
                if db_saved:
                    self.logger.info(
                        f"✅ {record['stock_code']} 미저장 매도 기록 DB 저장 성공 "
                        f"(재시도 {record['retry_count']}회 후)"
                    )
                    succeeded.append(i)
                else:
                    record['retry_count'] += 1
                    if record['retry_count'] >= self._max_retries:
                        self.logger.error(
                            f"❌ {record['stock_code']} 매도 기록 DB 저장 {self._max_retries}회 실패 "
                            f"- fallback JSON에 저장"
                        )
                        fallback_records.append(i)

            except Exception as e:
                record['retry_count'] += 1
                self.logger.warning(
                    f"⚠️ {record['stock_code']} 매도 기록 재저장 실패 "
                    f"(시도 {record['retry_count']}/{self._max_retries}): {e}"
                )
                if record['retry_count'] >= self._max_retries:
                    self.logger.error(
                        f"❌ {record['stock_code']} 매도 기록 DB 저장 {self._max_retries}회 실패 "
                        f"- fallback JSON에 저장"
                    )
                    fallback_records.append(i)

        # fallback JSON 파일에 저장
        if fallback_records:
            self._save_to_fallback_json(
                [self._pending_sell_records[i] for i in fallback_records]
            )

        # 성공 및 fallback 완료된 레코드 제거 (역순으로 제거하여 인덱스 보존)
        indices_to_remove = sorted(set(succeeded + fallback_records), reverse=True)
        for idx in indices_to_remove:
            self._pending_sell_records.pop(idx)

        self._last_retry_time = now_kst()

    def _save_to_fallback_json(self, records: List[Dict]) -> None:
        """재시도 한도 초과 레코드를 JSON 파일에 저장"""
        try:
            existing = []
            if os.path.exists(self._fallback_path):
                try:
                    with open(self._fallback_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                except (json.JSONDecodeError, IOError):
                    existing = []

            existing.extend(records)

            os.makedirs(os.path.dirname(self._fallback_path), exist_ok=True)
            with open(self._fallback_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2, default=str)

            self.logger.info(
                f"📁 미저장 매도 기록 {len(records)}건 fallback 파일에 저장: "
                f"{self._fallback_path}"
            )

        except Exception as e:
            self.logger.error(f"❌ fallback JSON 저장 실패: {e}")

    def log_pending_sells_summary(self) -> None:
        """대기 중인 미저장 매도 기록 요약 로그 출력 (장중 30분마다 호출)"""
        count = self.get_pending_sells_count()
        if count == 0:
            return

        max_retries = max(
            (r.get('retry_count', 0) for r in self._pending_sell_records),
            default=0
        )
        self.logger.info(
            f"📋 미저장 매도 기록: {count}건 대기 중 (최대 재시도: {max_retries}회)"
        )
        self._last_pending_log_time = now_kst()

    # =========================================================================
    # buy_time / days_held / is_stale 추적
    # =========================================================================

    def restore_buy_time(self, stock_code: str, buy_time: datetime) -> None:
        """봇 재시작 시 DB timestamp(BUY 행)로 buy_time 복원 (state_restorer 호환)

        Args:
            stock_code: 종목코드
            buy_time: DB에서 읽은 매수 시각 (timezone-aware 권장)
        """
        if buy_time is not None:
            self._buy_times[stock_code] = buy_time

    def get_position_buy_time(self, stock_code: str) -> Optional[datetime]:
        """종목의 매수 시각 반환 (없으면 None)"""
        return self._buy_times.get(stock_code)

    def get_days_held(self, stock_code: str) -> int:
        """종목 보유 캘린더일 수 계산 (state_restorer와 동일 기준: 캘린더일)

        Returns:
            int: 보유 일수 (buy_time 없으면 0)
        """
        buy_time = self._buy_times.get(stock_code)
        if buy_time is None:
            return 0
        today = now_kst()
        if buy_time.tzinfo:
            delta = today - buy_time
        else:
            delta = today.replace(tzinfo=None) - buy_time
        return max(0, delta.days)

    def is_stale_position(self, stock_code: str) -> bool:
        """보유 일수가 STALE_POSITION_DAYS 이상인지 확인

        Returns:
            bool: True면 장기보유(stale), False면 정상 보유
        """
        from config.constants import STALE_POSITION_DAYS
        return self.get_days_held(stock_code) >= STALE_POSITION_DAYS

    def get_virtual_balance_info(self) -> dict:
        """가상매매 잔고 정보 반환"""
        try:
            profit_amount = self.virtual_balance - self.initial_balance
            profit_rate = self.get_virtual_profit_rate()
            
            return {
                'current_balance': self.virtual_balance,
                'initial_balance': self.initial_balance,
                'profit_amount': profit_amount,
                'profit_rate': profit_rate,
                'investment_amount_per_stock': self.virtual_investment_amount
            }
        except Exception as e:
            self.logger.error(f"❌ 가상 잔고 정보 조회 오류: {e}")
            return {}