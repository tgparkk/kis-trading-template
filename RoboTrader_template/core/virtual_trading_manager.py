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
from typing import Dict, List, Optional, Tuple
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

        # buy_time 추적: (stock_code, buy_record_id) → buy_time(KST datetime)
        # DB의 virtual_trading_records.timestamp(BUY 행)과 동기화됨.
        # ⚠️ stock_code 단독 키였을 때, 두 전략(owner)이 같은 종목을 보유하면
        # buy_time 이 서로 덮어써지거나 한쪽 매도 시 통째로 삭제되어 보유기간이
        # 오귀속됐다(_position_owner 와 동일 결함, f4c3683 참조). 매수기록ID(BUY 행 PK)로
        # 슬롯을 유일 식별해 격리한다.
        self._buy_times: Dict[Tuple[str, Optional[int]], datetime] = {}

        # ── 전략별 자금 격리 원장 (할당 시에만 활성) ────────────────────────
        # 키는 전략 폴더키(StrategyLoader self.strategies dict 키)와 동일해야 함.
        # 원장이 비어 있으면(레거시/단일전략) 기존 단일 virtual_balance 경로로 동작.
        self._strategy_balances: Dict[str, float] = {}   # 폴더키 → 잔여 현금
        self._strategy_invested: Dict[str, float] = {}   # 폴더키 → 투자중 금액
        self._strategy_positions: Dict[str, List[str]] = {}  # 폴더키 → 보유 종목코드 목록
        self._strategy_initial: Dict[str, float] = {}    # 폴더키 → 초기 할당 자본
        # (종목코드, 매수기록ID) → 소유 전략 폴더키.
        # 전략별 완전독립 포지션(2026-06-16 B안)은 같은 종목을 여러 전략이 동시
        # 보유하는 것을 허용하므로(stock_state_manager 슬롯), 종목코드 단독 키로는
        # 소유권을 표현할 수 없다(먼저/나중 매수가 서로를 덮어씀).
        self._position_owner: Dict[Tuple[str, Optional[int]], str] = {}

        # Emergency Sell Path: DB 저장 실패 시 재시도 큐
        self._pending_sell_records: List[Dict] = []
        self._max_retries = 10
        # 전략별 종목당 투자금액 오버라이드 (yaml risk_management.paper_investment_per_stock).
        # 미설정 전략은 기존 virtual_investment_amount(가상 100만) 기본값 — 기존 전략 무영향.
        self._strategy_investment_amounts: Dict[str, float] = {}
        self._fallback_path = os.path.join("logs", "pending_sells_fallback.json")
        self._last_retry_time: Optional[datetime] = None
        self._last_pending_log_time: Optional[datetime] = None

        # 잔고 초기화
        self._initialize_balance()

    def _initialize_balance(self) -> None:
        """잔고 초기화 (가상/실전 모드에 따라 다르게 처리)"""
        try:
            if self.paper_trading:
                # 가상매매 모드: 전일 EOD 잔고 이월, 없으면 1000만원 fallback
                self.virtual_investment_amount = 1000000  # 종목당 100만원
                carried = self._load_paper_eod_balance()
                if carried is not None:
                    self.virtual_balance = carried
                    self.initial_balance = carried
                    self.logger.info(
                        f"가상 잔고 이월 (paper_trading_state): {self.virtual_balance:,.0f}원 "
                        f"(종목당: {self.virtual_investment_amount:,.0f}원)"
                    )
                else:
                    self.virtual_balance = 10000000  # 1천만원 (첫 실행 fallback)
                    self.initial_balance = self.virtual_balance
                    self.logger.info(
                        f"가상 잔고 설정 (초기/fallback): {self.virtual_balance:,.0f}원 "
                        f"(종목당: {self.virtual_investment_amount:,.0f}원)"
                    )
            else:
                # 실전 모드: 실제 계좌 잔고 조회
                self._initialize_real_balance()

        except Exception as e:
            self.logger.error(f"잔고 초기화 오류: {e}")
            # 오류 시 기본값 사용
            self.virtual_balance = 10000000
            self.initial_balance = self.virtual_balance
            self.virtual_investment_amount = 1000000

    def _load_paper_eod_balance(self) -> 'Optional[float]':
        """paper_trading_state에서 가장 최근 EOD 잔고 조회.

        Returns:
            float: 저장된 잔고, 없거나 DB 없으면 None
        """
        if not self.db_manager:
            return None
        try:
            return self.db_manager.get_latest_paper_eod_balance()
        except Exception as e:
            self.logger.warning(f"paper EOD 잔고 로드 실패 (fallback 사용): {e}")
            return None

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

    # =========================================================================
    # 전략별 자금 격리 원장
    # =========================================================================

    def allocate_strategy_capital(self, strategy_name: str, amount: float,
                                  max_positions: int = None) -> None:
        """전략별 가상 초기자본을 명시 할당하고 집계 잔고를 동기화.

        이번 세션 시작 시점에 전략 폴더키별 초기자본을 지정하는 용도.
        carryover로 이월된 집계 잔고가 있어도 할당이 우선한다(설계 단순화).
        전략별 영속화는 미구현이므로 carryover와 충돌 시 WARNING.

        Args:
            strategy_name: 전략 폴더키 (StrategyLoader self.strategies dict 키와 동일)
            amount: 초기 할당 자본 (원)
            max_positions: 전략 최대 동시 보유 종목수(K). 지정 시 종목당 기본
                예산 = amount/K (균등 K분할 — 백테스트 균등복리 K분할과 정합,
                2026-06-11 사장님 결재 A안). yaml paper_investment_per_stock이
                있으면 이후 set_strategy_investment_amount가 덮어쓴다.
        """
        if not strategy_name:
            self.logger.warning("allocate_strategy_capital: 빈 전략명 무시")
            return
        # carryover된 집계 잔고와 충돌 경고 (할당이 우선)
        carried = self.initial_balance if self.initial_balance > 0 else 0
        if carried and not self._strategy_balances:
            self.logger.warning(
                f"전략 자금 할당이 carryover 집계({carried:,.0f}원)를 덮어씀 "
                f"(전략별 영속화 미구현 — 할당 우선): {strategy_name} {amount:,.0f}원"
            )
        amount = float(amount)
        self._strategy_balances[strategy_name] = amount
        self._strategy_invested[strategy_name] = 0.0
        self._strategy_positions.setdefault(strategy_name, [])
        self._strategy_initial[strategy_name] = amount
        if max_positions and int(max_positions) > 0:
            self._strategy_investment_amounts[strategy_name] = amount / int(max_positions)
        self._sync_aggregate_from_strategies()
        self.logger.info(
            f"전략 자금 할당: {strategy_name} {amount:,.0f}원 "
            f"(집계 {self.virtual_balance:,.0f}원)"
        )

    def set_strategy_investment_amount(self, strategy_name: str, amount: float) -> None:
        """전략별 종목당 투자금액 설정 (yaml risk_management.paper_investment_per_stock).

        get_max_quantity 가 min(이 값, 전략 잔여 budget) 으로 수량을 산정한다.
        미설정 전략은 기존 virtual_investment_amount(100만) — 기존 전략 거동 불변.
        (배경: 사이징 시나리오 검증 dev20_sizing_scenarios.tsv — S2=자본/K 가 스위트스팟)
        """
        if not strategy_name or amount is None or float(amount) <= 0:
            return
        self._strategy_investment_amounts[strategy_name] = float(amount)
        self.logger.info(
            f"전략 종목당 투자금액 설정: {strategy_name} {float(amount):,.0f}원"
        )

    def restore_strategy_ledger_from_records(
        self,
        initial_per_strategy: float,
        trade_sums: Dict[str, Dict[str, float]],
        open_positions: List[dict],
    ) -> None:
        """재시작 시 전략 원장을 매매기록에서 재구성.

        전략별 현금은 매매기록의 순수 함수이므로 별도 영속화 없이 재구성한다:
            cash[전략] = initial
                         − buy_gross*(1+COMMISSION_RATE)
                         + sell_gross*(1−COMMISSION_RATE−SECURITIES_TAX_RATE)
        매수비용은 cash 식에서만 차감하고(이중차감 방지), open_positions 루프는
        invested/positions/_position_owner만 복원한다.

        Args:
            initial_per_strategy: 전략별 초기 할당 자본 (보통 VIRTUAL_CAPITAL_PER_STRATEGY)
            trade_sums: {strategy: {'buy_gross':.., 'sell_gross':..}} (get_strategy_trade_sums)
            open_positions: [{stock_code, strategy(폴더키), quantity, buy_price,
                              buy_record_id}, ...]
                buy_record_id(BUY 행 PK)는 다owner 동일종목의 소유권 구분에 쓰인다.
                없으면 종목코드 단독으로 폴백하므로 같은 종목의 소유권 1건만 남는다.
        """
        # 하위호환: 원장 미사용(레거시/단일전략/실전)이면 no-op.
        if not self._strategy_balances and not trade_sums and not open_positions:
            return

        from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE

        trade_sums = trade_sums or {}
        open_positions = open_positions or []
        initial = float(initial_per_strategy)

        # 활성 전략 = 이번 세션에 allocate_strategy_capital 로 사전 할당된 폴더키(config 기반).
        # 격리 원장 모드(활성 집합 비어있지 않음)에서는 활성 전략만 재구성하고,
        # 매매기록·포지션에 섞인 비활성(과거/형제프로젝트/테스트) 전략은 무시한다.
        # → 유령 전략마다 initial(=10M)이 더해져 집계가 폭증하던 버그(174.8M) 차단.
        active_keys = set(self._strategy_balances)
        if active_keys:
            keys = active_keys
        else:
            # 레거시(할당 없음): 기존 동작 — 매매기록/포지션에서 키 구성.
            keys = set(trade_sums)
            for pos in open_positions:
                owner = pos.get('strategy')
                if owner:
                    keys.add(owner)

        # 1) 현금 재구성 (매수비용은 여기서만 차감)
        for key in keys:
            sums = trade_sums.get(key, {})
            buy_gross = float(sums.get('buy_gross', 0.0))
            sell_gross = float(sums.get('sell_gross', 0.0))
            cash = (
                initial
                - buy_gross * (1.0 + COMMISSION_RATE)
                + sell_gross * (1.0 - COMMISSION_RATE - SECURITIES_TAX_RATE)
            )
            self._strategy_balances[key] = cash
            self._strategy_initial.setdefault(key, initial)
            self._strategy_invested[key] = 0.0
            self._strategy_positions[key] = []

            # self.strategies(활성 전략)에 없는 키 = 삭제된 전략 (고아자금 회수)
            if key not in trade_sums and not any(
                p.get('strategy') == key for p in open_positions
            ):
                # 기존 할당만 있고 기록/포지션 없음 → 첫 실행 또는 신규 전략
                pass

        # 2) 미청산 포지션 복원 (현금은 추가 차감 안 함 — 이중차감 방지)
        for pos in open_positions:
            owner = pos.get('strategy')
            if not owner:
                continue
            # 격리 원장 모드: 비활성 전략이 소유한 포지션은 무시(오염 차단).
            if active_keys and owner not in active_keys:
                continue
            code = pos.get('stock_code')
            try:
                qty = int(pos.get('quantity', 0))
                buy_price = float(pos.get('buy_price', 0.0))
            except (TypeError, ValueError):
                continue
            # owner 키가 cash 루프에서 누락됐다면(예: trade_sums에만 없던 경우) 보강
            if owner not in self._strategy_balances:
                self._strategy_balances[owner] = initial
                self._strategy_initial.setdefault(owner, initial)
                self._strategy_invested[owner] = 0.0
                self._strategy_positions[owner] = []
            if code:
                # 매수기록ID 로 키잉 — 입력이 timestamp DESC 순서라
                # (db/repositories/trading.py) 종목코드 단독 키였을 땐 먼저 산
                # 전략이 마지막에 순회되어 나중 매수자의 소유권을 덮어썼다.
                self._position_owner[
                    self._owner_key(code, pos.get('buy_record_id'))
                ] = owner
                self._strategy_positions.setdefault(owner, []).append(code)
            self._strategy_invested[owner] = (
                self._strategy_invested.get(owner, 0.0)
                + qty * buy_price * (1.0 + COMMISSION_RATE)
            )

        # 3) 집계 잔고 = Σ 전략 현금
        self._sync_aggregate_from_strategies()
        self.logger.info(
            f"전략 원장 재구성 완료: {len(self._strategy_balances)}개 전략 "
            f"(집계 {self.virtual_balance:,.0f}원)"
        )

    # ------------------------------------------------------------------
    # 포지션 소유권 (다owner 동일종목 지원)
    # ------------------------------------------------------------------

    @staticmethod
    def _owner_key(stock_code: str, buy_record_id) -> Tuple[str, Optional[int]]:
        """_position_owner 키 정규화: (종목코드, 매수기록ID).

        매수기록ID는 BUY 행의 DB PK로 포지션(슬롯)을 유일하게 식별한다.
        """
        try:
            rid = int(buy_record_id) if buy_record_id is not None else None
        except (TypeError, ValueError):
            rid = None
        return (stock_code, rid)

    def _resolve_position_owner(self, stock_code: str, buy_record_id,
                                strategy: str) -> Optional[str]:
        """매도 대상 포지션의 소유 전략 폴더키를 결정 (없으면 None).

        우선순위:
          1) 호출자가 준 strategy 가 원장 폴더키면 그대로 신뢰한다.
             호출자(trading_decision_engine)는 슬롯별 owner_strategy_name 을
             넘기므로 다owner 동일종목에서도 이미 올바른 per-slot 값이다.
          2) 폴더키가 아니면(호출자가 클래스명을 넘기는 상위 경로 버그) 매수 시
             기록한 (종목코드, 매수기록ID) 소유자로 정규화한다. BUY(폴더키)와
             SELL 이 동일 폴더키로 DB 에 기록되어야 재시작 재구성
             (get_strategy_trade_sums 의 strategy 컬럼 그룹핑)이 라운드트립을
             한 버킷으로 합산한다.
          3) 매수기록ID 가 불일치/미상이면 해당 종목의 소유자가 유일할 때만
             정규화한다. 소유자가 여럿이면 오귀속 위험이 있으므로 포기한다.

        Returns:
            소유 전략 폴더키. None 이면 원장 귀속 불가 → 레거시 단일 잔고 경로.
        """
        if not self._strategy_balances:
            return None
        # 1) 호출자의 per-slot 전략을 신뢰
        if strategy and strategy in self._strategy_balances:
            return strategy
        # 2) 매수기록ID 로 실소유자 식별 → 폴더키 정규화
        owner = self._position_owner.get(self._owner_key(stock_code, buy_record_id))
        if owner is not None and owner in self._strategy_balances:
            return owner
        # 3) 소유자가 유일할 때만 종목코드로 정규화
        owners = {
            o for (code, _), o in self._position_owner.items() if code == stock_code
        }
        if len(owners) == 1:
            only = next(iter(owners))
            if only in self._strategy_balances:
                return only
        return None

    def _pop_position_owner(self, stock_code: str, buy_record_id,
                            owner: str) -> None:
        """청산된 포지션의 소유권 항목 하나를 제거 (타 전략 항목은 보존)."""
        key = self._owner_key(stock_code, buy_record_id)
        if self._position_owner.get(key) == owner:
            self._position_owner.pop(key, None)
            return
        # 매수기록ID 불일치/미상: 같은 종목·같은 소유자 항목 하나만 제거
        for k, v in list(self._position_owner.items()):
            if k[0] == stock_code and v == owner:
                self._position_owner.pop(k, None)
                return

    def _has_strategy_ledger(self, strategy_name: str = "") -> bool:
        """전략 원장 활성 여부. strategy_name이 주어지면 해당 전략 할당 여부.

        strategy_name이 비어 있으면 원장이 1건이라도 있으면 True.
        """
        if not self._strategy_balances:
            return False
        if strategy_name:
            return strategy_name in self._strategy_balances
        return True

    def _sync_aggregate_from_strategies(self) -> None:
        """전략 잔고 합계로 집계 virtual_balance를 동기화.

        전략 할당이 1건이라도 있으면 virtual_balance = sum(_strategy_balances).
        (레거시 경로에서는 호출되지 않으므로 단일 잔고가 보존됨.)
        """
        if self._strategy_balances:
            self.virtual_balance = sum(self._strategy_balances.values())

    def get_strategy_balance(self, strategy_name: str) -> Optional[float]:
        """전략 잔여 현금 반환. 미할당이면 None."""
        return self._strategy_balances.get(strategy_name)

    def get_strategy_positions(self, strategy_name: str) -> List[str]:
        """전략 보유 종목코드 목록 반환 (미할당이면 빈 리스트)."""
        return list(self._strategy_positions.get(strategy_name, []))
    
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
    
    def get_max_quantity(self, price: float, strategy_name: str = "") -> int:
        """주어진 가격에서 최대 매수 가능 수량.

        Args:
            price: 매수 단가
            strategy_name: 전략 폴더키. 원장에 할당돼 있으면 해당 전략 잔여 한도 기준,
                           없으면(레거시) 기존 단일 virtual_balance 기준.
        """
        try:
            if price <= 0:
                return 0
            if self._has_strategy_ledger(strategy_name):
                budget = self._strategy_balances[strategy_name]
            else:
                budget = self.virtual_balance
            per_stock = self._strategy_investment_amounts.get(
                strategy_name, self.virtual_investment_amount)
            max_amount = min(per_stock, budget)
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

            # 전략 원장 활성 여부 (strategy 인자가 폴더키로 할당돼 있을 때만)
            use_ledger = self._has_strategy_ledger(strategy)

            # 잔고 확인 (수수료 포함)
            if use_ledger:
                strat_balance = self._strategy_balances[strategy]
                if strat_balance < total_cost_with_fee:
                    self.logger.warning(
                        f"⚠️ 전략 가상 잔고 부족 [{strategy}]: "
                        f"{strat_balance:,.0f}원 < {total_cost_with_fee:,.0f}원"
                    )
                    return None
            elif not self.can_buy(total_cost_with_fee):
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
                    if use_ledger:
                        # 전략 원장 차감 + 집계 동기화
                        self._strategy_balances[strategy] -= total_cost_with_fee
                        self._strategy_invested[strategy] = (
                            self._strategy_invested.get(strategy, 0.0) + total_cost_with_fee
                        )
                        self._strategy_positions.setdefault(strategy, []).append(stock_code)
                        # 매수기록ID 로 키잉 — 다른 전략이 같은 종목을 이미 보유해도
                        # 서로의 소유권을 덮어쓰지 않는다.
                        self._position_owner[
                            self._owner_key(stock_code, buy_record_id)
                        ] = strategy
                        self._sync_aggregate_from_strategies()
                    else:
                        # 가상 잔고에서 매수 금액 + 수수료 차감 (레거시 단일 잔고)
                        self.update_virtual_balance(total_cost_with_fee, "매수")

                    # buy_time 메모리에 기록 (DB timestamp와 동기화).
                    # 매수기록ID 로 키잉 — 다른 전략이 같은 종목을 이미 보유해도
                    # 서로의 buy_time 을 덮어쓰지 않는다.
                    self._buy_times[self._owner_key(stock_code, buy_record_id)] = now_kst()

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

            # 소유 전략 원장으로 복구 (할당된 종목일 때만), 아니면 단일 잔고.
            # 소유자 판정은 _resolve_position_owner 로 분리 — 호출자의 per-slot
            # strategy 를 우선 신뢰하고, 폴더키가 아닐 때만 매수기록ID 로 정규화한다.
            owner = self._resolve_position_owner(stock_code, buy_record_id, strategy)
            if owner is not None:
                # DB 기록 strategy 를 폴더키로 통일 — BUY 와 SELL 이 같은 키여야
                # 재시작 재구성(get_strategy_trade_sums 의 strategy 컬럼 그룹핑)이
                # 라운드트립을 한 버킷으로 정확히 합산한다.
                strategy = owner
                self._strategy_balances[owner] += net_received
                # invested 감소 (매수 시 적립한 cost 추적치). 음수 방지.
                self._strategy_invested[owner] = max(
                    0.0, self._strategy_invested.get(owner, 0.0) - net_received
                )
                # 같은 종목을 여러 전략이 보유해도 소유 전략 목록에서만 1건 제거.
                positions = self._strategy_positions.get(owner)
                if positions and stock_code in positions:
                    positions.remove(stock_code)
                self._pop_position_owner(stock_code, buy_record_id, owner)
                self._sync_aggregate_from_strategies()
            else:
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

            # buy_time 메모리에서 제거 (포지션 청산). 매수기록ID 로 해당 슬롯만
            # 제거 — 같은 종목을 다른 전략이 보유 중이면 그 buy_time 은 보존한다.
            self._pop_buy_time(stock_code, buy_record_id)

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

    def _resolve_buy_time_key(self, stock_code: str,
                              buy_record_id=None) -> Optional[Tuple[str, Optional[int]]]:
        """buy_time 조회 키 결정. 매수기록ID 로 정확 매칭하고, 미상/불일치면
        같은 종목 항목이 유일할 때만 폴백한다(다owner 모호 시 None → 오귀속 방지).

        레거시 in-memory 잔재(베어 stock_code 키)도 폴백에서 함께 처리한다.
        """
        key = self._owner_key(stock_code, buy_record_id)
        if key in self._buy_times:
            return key
        # 구체적 매수기록ID 가 주어졌는데 없으면(이미 청산된 슬롯 등) None —
        # 타 슬롯으로 폴백하면 그게 바로 오귀속이므로 금지.
        if key[1] is not None:
            return None
        # 매수기록ID 미상(legacy): 같은 종목 항목이 유일할 때만 폴백
        matches = [
            k for k in self._buy_times
            if (k[0] if isinstance(k, tuple) else k) == stock_code
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def _pop_buy_time(self, stock_code: str, buy_record_id=None) -> None:
        """청산된 슬롯의 buy_time 하나만 제거 (타 전략의 동일종목 항목은 보존)."""
        key = self._owner_key(stock_code, buy_record_id)
        if key in self._buy_times:
            self._buy_times.pop(key, None)
            return
        # 구체적 매수기록ID 가 주어졌는데 정확 키가 없으면(이미 청산된 슬롯 등)
        # 아무것도 지우지 않는다 — 타 owner 의 동일종목 항목을 지우면 그게 바로
        # 오귀속이다(read 경로 _resolve_buy_time_key 와 대칭).
        if key[1] is not None:
            return
        # 매수기록ID 미상(legacy): 같은 종목 항목 하나만 제거(베어키 포함)
        for k in list(self._buy_times):
            if (k[0] if isinstance(k, tuple) else k) == stock_code:
                self._buy_times.pop(k, None)
                return

    def restore_buy_time(self, stock_code: str, buy_time: datetime,
                         buy_record_id=None) -> None:
        """봇 재시작 시 DB timestamp(BUY 행)로 buy_time 복원 (state_restorer 호환)

        Args:
            stock_code: 종목코드
            buy_time: DB에서 읽은 매수 시각 (timezone-aware 권장)
            buy_record_id: BUY 행 PK. 다owner 동일종목 슬롯 구분에 사용(없으면 legacy).
        """
        if buy_time is not None:
            self._buy_times[self._owner_key(stock_code, buy_record_id)] = buy_time

    def get_position_buy_time(self, stock_code: str,
                              buy_record_id=None) -> Optional[datetime]:
        """종목의 매수 시각 반환 (없으면 None)"""
        key = self._resolve_buy_time_key(stock_code, buy_record_id)
        return self._buy_times.get(key) if key is not None else None

    def get_days_held(self, stock_code: str, buy_record_id=None) -> int:
        """종목 보유 영업일 수 계산 (주말·공휴일 제외)

        Returns:
            int: 보유 영업일 수 (buy_time 없으면 0)
        """
        buy_time = self.get_position_buy_time(stock_code, buy_record_id)
        if buy_time is None:
            return 0
        from utils.korean_holidays import count_trading_days_between
        today = now_kst()
        buy_naive = buy_time.replace(tzinfo=None) if buy_time.tzinfo else buy_time
        today_naive = today.replace(tzinfo=None)
        return max(0, count_trading_days_between(buy_naive, today_naive))

    def is_stale_position(self, stock_code: str, buy_record_id=None) -> bool:
        """보유 일수가 STALE_POSITION_DAYS 이상인지 확인

        Returns:
            bool: True면 장기보유(stale), False면 정상 보유
        """
        from config.constants import STALE_POSITION_DAYS
        return self.get_days_held(stock_code, buy_record_id) >= STALE_POSITION_DAYS

    def save_paper_trading_state(self) -> bool:
        """현재 가상 잔고를 오늘 날짜로 paper_trading_state에 UPSERT.

        EOD 처리 완료 시점에 liquidation_handler가 호출한다.

        Returns:
            bool: 저장 성공 여부
        """
        if not self.db_manager:
            self.logger.warning("DB 매니저 없음 — paper EOD 잔고 저장 생략")
            return False
        try:
            today = now_kst().date()
            ok = self.db_manager.upsert_paper_eod_balance(today, self.virtual_balance)
            if ok:
                self.logger.info(
                    f"paper EOD 잔고 저장: {today} {self.virtual_balance:,.0f}원"
                )
            return ok
        except Exception as e:
            self.logger.error(f"paper EOD 잔고 저장 오류: {e}")
            return False

    def get_cumulative_profit_info(self) -> dict:
        """DB 전체 누적 실현손익 기반 성과 정보 반환 (P2 보조 메서드).

        virtual_trading_records의 is_test=TRUE SELL 레코드의 profit_loss 합계.
        profit_loss는 (sell_price - buy_price) * qty — 수수료/세금 미포함.
        수수료+거래세 추정치를 차감하여 순손익을 근사한다.

        Returns:
            dict: cumulative_gross_pnl, cumulative_net_pnl (추정), trade_count,
                  current_balance, initial_balance (=10,000,000)
        """
        # 세션 시작 잔고를 기준으로 누적 수익률 계산 (D-1 이월 잔고 또는 최초 10M)
        session_base = self.initial_balance if self.initial_balance > 0 else 10_000_000
        result = {
            'cumulative_gross_pnl': 0.0,
            'cumulative_net_pnl': 0.0,
            'trade_count': 0,
            'current_balance': self.virtual_balance,
            'initial_balance': session_base,
        }
        if not self.db_manager:
            return result
        try:
            from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE
            # source 필터: 형제 프로젝트 RoboTrader 레코드(macd_cross_alt 등)가
            # 손익 집계에 섞이지 않도록 kis-template 출처만 합산한다.
            source_tag = self.db_manager.trading_repo.SOURCE_KIS_TEMPLATE
            with self.db_manager.trading_repo._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT
                        COALESCE(SUM(s.profit_loss), 0)            AS gross_pnl,
                        COALESCE(SUM(s.price * s.quantity), 0)     AS total_sell_value,
                        COALESCE(SUM(b.price * s.quantity), 0)     AS total_buy_value,
                        COUNT(*)                                    AS trade_count
                    FROM virtual_trading_records s
                    JOIN virtual_trading_records b ON s.buy_record_id = b.id
                    WHERE s.action = 'SELL' AND s.is_test = TRUE
                      AND s.source = %s
                ''', (source_tag,))
                row = cursor.fetchone()
            if row:
                gross_pnl = float(row[0])
                total_sell_value = float(row[1])
                total_buy_value = float(row[2])
                trade_count = int(row[3])
                # 수수료: 매수·매도 각 COMMISSION_RATE, 거래세: 매도에 SECURITIES_TAX_RATE
                estimated_fees = (
                    total_buy_value * COMMISSION_RATE
                    + total_sell_value * (COMMISSION_RATE + SECURITIES_TAX_RATE)
                )
                net_pnl = gross_pnl - estimated_fees
                result.update({
                    'cumulative_gross_pnl': gross_pnl,
                    'cumulative_net_pnl': net_pnl,
                    'trade_count': trade_count,
                })
        except Exception as e:
            self.logger.warning(f"누적 손익 조회 실패: {e}")
        return result

    def log_cumulative_profit(self) -> None:
        """누적 실현손익을 INFO 로그에 한 줄 출력 (EOD 또는 필요 시점에 호출)."""
        info = self.get_cumulative_profit_info()
        net = info['cumulative_net_pnl']
        gross = info['cumulative_gross_pnl']
        count = info['trade_count']
        base = info['initial_balance']
        net_rate = (net / base * 100) if base > 0 else 0.0
        self.logger.info(
            f"[누적손익] {count}건 실현 | 순손익(추정) {net:+,.0f}원 ({net_rate:+.2f}%, 페이퍼 전체누적) "
            f"| 총손익(수수료전) {gross:+,.0f}원 | 현재잔고 {self.virtual_balance:,.0f}원"
        )

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
            self.logger.error(f"가상 잔고 정보 조회 오류: {e}")
            return {}