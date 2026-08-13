"""상태 복원 모듈

시스템 재시작 시 DB에서 오늘의 후보 종목 및 보유 종목을 복원합니다.
"""
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.logger import setup_logger
from utils.korean_time import now_kst, KST
from core.models import StockState
from config.constants import (
    DEFAULT_TARGET_PROFIT_RATE, DEFAULT_STOP_LOSS_RATE,
    STALE_POSITION_DAYS, STALE_DEFAULT_APPLY_DAYS,
    STALE_DEFAULT_TARGET_PROFIT, STALE_DEFAULT_STOP_LOSS,
    STATE_RESTORATION_AUTO_RECONCILE,
)
from db.connection import DatabaseConnection

logger = setup_logger(__name__)


class StateRestorer:
    """상태 복원 헬퍼 (간소화 버전)

    기능:
    1. 오늘 날짜의 후보 종목을 DB에서 복원
    2. 보유 종목 복원 (가상매매: DB, 실전매매: 실제 계좌)
    3. 실전매매 시 계좌-DB 불일치 감지
    """

    def __init__(
        self,
        trading_manager,
        db_manager,
        telegram_integration,
        config,
        get_previous_close_callback,
        broker=None,
        fund_manager=None,
        virtual_trading_manager=None,
        strategies=None,
    ) -> None:
        """
        Args:
            trading_manager: TradingStockManager 인스턴스
            db_manager: DatabaseManager 인스턴스
            telegram_integration: 텔레그램 통합
            config: 거래 설정
            get_previous_close_callback: 전날 종가 조회 콜백 함수
            broker: KISBroker (실전 모드에서 계좌 조회용)
            fund_manager: FundManager 인스턴스 (자금 동기화용)
            virtual_trading_manager: VirtualTradingManager 인스턴스 (가상 잔고 동기화용)
            strategies: {name: BaseStrategy} 딕셔너리 (owner_strategy 복원용)
        """
        self.trading_manager = trading_manager
        self.db_manager = db_manager
        self.telegram = telegram_integration
        self.config = config
        self.get_previous_close = get_previous_close_callback
        self.broker = broker
        self.fund_manager = fund_manager
        self.virtual_trading_manager = virtual_trading_manager
        self.strategies = strategies or {}

        # 가상/실전 모드 플래그
        self.is_paper_trading = getattr(config, 'paper_trading', True) if config else True

        # on_init() 이후 재주입할 복원 포지션 누적 저장소 ({owner: {code: pos}}).
        # _sync_strategy_positions 가 즉시 주입과 동시에 여기 병합해 두면,
        # main.py 가 strategy.on_init() 이후 apply_pending_strategy_positions() 를
        # 호출해 on_init 의 self.positions={} 초기화로 지워진 주입을 되살릴 수 있다
        # (두 호출부 _restore_holdings_from_db/_restore_holdings_from_real_account
        # 가 모두 여기로 병합된다).
        self._pending_strategy_positions: Dict[str, Dict[str, dict]] = {}

    async def restore_todays_candidates(self) -> None:
        """DB에서 후보 종목 및 보유 종목 복원"""
        try:
            today = now_kst().strftime('%Y-%m-%d')

            # 1. 오늘 날짜의 후보 종목 복원
            await self._restore_candidates(today)

            # 2. 보유 종목 복원 (가상/실전 모드에 따라 다른 소스 사용)
            if self.is_paper_trading:
                await self._restore_holdings_from_db()
            else:
                await self._restore_holdings_from_real_account()

        except Exception as e:
            logger.error(f"❌ 종목 복원 실패: {e}")

    def _resolve_owner_strategy(self, name: str):
        """전략 이름으로 strategies dict에서 인스턴스를 조회한다.

        1차: bot_strategies 키(폴더명)로 직접 조회
        2차: 전략 클래스명(strategy.name 속성)으로 보조 매핑 조회
        둘 다 실패하면 None 반환.

        Args:
            name: DB에 저장된 전략 식별자 (폴더명 또는 클래스명)

        Returns:
            BaseStrategy 인스턴스 또는 None
        """
        bot_strategies = self.strategies
        # 1차: 폴더명 키로 직접 조회
        matched = bot_strategies.get(name)
        if matched is not None:
            return matched
        # 2차: 클래스명(strategy.name 속성) 보조 매핑 — lazy 생성
        if not hasattr(self, '_by_class_name_cache'):
            self._by_class_name_cache = {
                s.name: s
                for s in bot_strategies.values()
                if getattr(s, 'name', None)
            }
        return self._by_class_name_cache.get(name)

    def _normalize_entry_time(self, buy_time):
        """복원 buy_time → 전략 self.positions['entry_time'] 용 tz-aware KST datetime.

        daytrading 등은 entry_time 을 now_kst()(tz-aware)와
        count_trading_days_between 으로 비교한다. naive/tz-aware 혼용 시
        TypeError 가 나 on_tick tick 이 손상되므로 KST tz 를 보장한다.
        변환 불가/None 이면 None(전략은 hold_days=0 으로 안전 처리).
        """
        if buy_time is None:
            return None
        try:
            if isinstance(buy_time, (int, float)):
                dt = datetime.fromtimestamp(buy_time, tz=KST)
            elif isinstance(buy_time, datetime):  # pandas.Timestamp 포함
                dt = buy_time
            else:
                import pandas as pd
                dt = pd.to_datetime(buy_time).to_pydatetime()
        except Exception:
            return None
        if getattr(dt, 'tzinfo', None) is None:
            try:
                dt = dt.replace(tzinfo=KST)
            except Exception:
                return None
        return dt

    def _sync_strategy_positions(self, by_owner: Dict[str, Dict[str, dict]]) -> None:
        """복원 포지션을 owner 전략별 self.positions 로 주입한다.

        재시작 시 전략 인스턴스의 self.positions 는 {}로 비어 generate_signal
        매도 분기(`stock_code in self.positions`)가 동작하지 않는다. 그 결과
        전략측 청산(max_hold 거래일·sl·tp·trail)이 복원 포지션에 영영 적용되지
        않는다(프레임워크 백스톱은 max_hold 강제청산을 하지 않음). 이 호출이
        그 공백을 메운다.

        Args:
            by_owner: {owner_name: {stock_code: {quantity, entry_price, entry_time}}}
                      owner 가 strategies dict 에서 해석되지 않으면(비활성) 스킵.
        """
        for owner_name, pos_map in by_owner.items():
            if not owner_name or not pos_map:
                continue
            # on_init() 이후 재주입용으로 누적 (두 호출부가 여기로 병합됨).
            self._pending_strategy_positions.setdefault(owner_name, {}).update(pos_map)

            strategy = self._resolve_owner_strategy(owner_name)
            if strategy is None or not hasattr(strategy, 'sync_positions'):
                continue
            try:
                strategy.sync_positions(pos_map)
            except Exception as e:
                logger.warning(f"[복원] {owner_name} sync_positions 주입 실패: {e}")

    def apply_pending_strategy_positions(self) -> int:
        """on_init() 이후 복원 포지션을 전략 self.positions 에 재주입한다.

        main.py 기동 순서상 StateRestorer(→_sync_strategy_positions 즉시 주입)가
        strategy.on_init() 보다 먼저 실행되는데, on_init 은 self.positions = {}
        로 초기화하므로 즉시 주입분이 지워진다(2026-08-12 라이브 실측: 61종목
        복원 성공 로그 직후 전략 초기화 로그가 같은 초에 찍혔고, 09:00:40
        "보유 종목 없음"으로 이어졌다). main.py 는 _initialize_strategy()
        (on_init 호출) 직후 이 메서드를 호출해 그 공백을 메운다.
        BaseStrategy.sync_positions 는 dict.update() 라 재호출은 멱등이다.

        Returns:
            int: 재주입에 성공한 전략 수
        """
        synced_count = 0
        for owner_name, pos_map in self._pending_strategy_positions.items():
            if not owner_name or not pos_map:
                continue
            strategy = self._resolve_owner_strategy(owner_name)
            if strategy is None or not hasattr(strategy, 'sync_positions'):
                continue
            try:
                strategy.sync_positions(pos_map)
                synced_count += 1
            except Exception as e:
                logger.warning(f"[재주입] {owner_name} sync_positions 재주입 실패: {e}")

        if synced_count:
            logger.info(
                f"[재주입] on_init 이후 전략 포지션 재주입 완료: {synced_count}개 전략"
            )

        return synced_count

    def _sync_fund_manager_for_position(self, stock_code: str, quantity: int, buy_price: float,
                                        owner: Optional[str] = None) -> float:
        """복원된 포지션에 대해 FundManager 자금을 동기화

        Args:
            stock_code: 종목코드
            quantity: 보유 수량
            buy_price: 매수 단가
            owner: 소유 전략 표기 (슬롯 객체의 owner_strategy_name).
                   같은 종목을 두 전략이 보유하면 (code, owner) 엔트리가 2개가 되어야
                   한 전략의 매도가 남은 전략의 보유를 지우지 않는다(2026-07-28).

        Returns:
            float: 동기화된 투자 금액
        """
        quantity = int(quantity)
        buy_price = float(buy_price)
        invested_amount = quantity * buy_price

        if not self.fund_manager:
            logger.warning(f"FundManager 미초기화 - {stock_code} 자금 동기화 스킵")
            return invested_amount

        try:
            with self.fund_manager._lock:
                self.fund_manager.invested_funds += invested_amount
                self.fund_manager.available_funds -= invested_amount

                # 가용자금이 음수가 되면 0으로 클램프
                if self.fund_manager.available_funds < 0:
                    logger.warning(
                        f"가용자금 음수 보정: {self.fund_manager.available_funds:,.0f}원 -> 0원 "
                        f"(총투자: {self.fund_manager.invested_funds:,.0f}원 > "
                        f"총자금: {self.fund_manager.total_funds:,.0f}원)"
                    )
                    self.fund_manager.available_funds = 0

            # 보유 종목 등록 (add_position은 내부에서 자체 lock 사용)
            self.fund_manager.add_position(stock_code, owner)

        except Exception as e:
            logger.error(f"FundManager 동기화 오류 ({stock_code}): {e}")

        return invested_amount

    def _sync_virtual_balance_for_position(self, quantity: int, buy_price: float) -> None:
        """복원된 포지션에 대해 VirtualTradingManager 가상 잔고를 동기화

        Args:
            quantity: 보유 수량
            buy_price: 매수 단가
        """
        if not self.virtual_trading_manager:
            return

        # 전략 원장 활성 시: 집계 차감은 restore_strategy_ledger_from_records가
        # 매매기록에서 재구성하므로 여기서 차감하면 이중차감이 된다 → 스킵.
        if getattr(self.virtual_trading_manager, '_strategy_balances', None):
            return

        try:
            quantity = int(quantity)
            buy_price = float(buy_price)
            invested_amount = quantity * buy_price
            self.virtual_trading_manager.update_virtual_balance(invested_amount, "매수")
        except Exception as e:
            logger.error(f"VirtualTradingManager 잔고 동기화 오류: {e}")

    def _reconstruct_strategy_ledger(self, restored_positions: list) -> None:
        """전략 원장을 매매기록에서 재구성하고 FundManager 를 재동기화.

        보유 0건(flat boot)과 보유 N건 경로가 **같은 코드**를 타야 한다. 재구성은
        매매기록의 순수 함수라 보유 유무와 무관하게 실행되어야 누적손익이 승계된다.

        Args:
            restored_positions: 복원된 미청산 포지션 목록. flat boot 이면 빈 리스트.

        가드: 전략 원장 미활성(_strategy_balances 공집합 = 레거시·단일전략·실전)이면
        no-op. 실전은 allocate_strategy_capital 을 호출하지 않으므로 자동 스킵된다.
        """
        vtm = self.virtual_trading_manager
        if not (vtm and getattr(vtm, '_strategy_balances', None)):
            return

        try:
            from config.constants import VIRTUAL_CAPITAL_PER_STRATEGY
            sums = self.db_manager.get_strategy_trade_sums()
            vtm.restore_strategy_ledger_from_records(
                VIRTUAL_CAPITAL_PER_STRATEGY, sums, restored_positions
            )
            # 종목당 투자금액을 재구성된 현재 자본 기준으로 재산정 (진짜 복리,
            # 2026-07-29 사장님 결재). 반드시 재구성 *뒤*여야 한다 — 이 시점에야
            # _strategy_balances/_strategy_invested 가 매매기록 기반 실자본이다.
            # 재산정 로직 자체는 원장 소유자인 vtm 이 갖는다(여기서는 호출만).
            if hasattr(vtm, 'recalculate_investment_amounts'):
                vtm.recalculate_investment_amounts()
            self._resync_fund_manager_to_ledger(vtm)
        except Exception as e:
            logger.error(f"[가상매매] 전략 원장 재구성 실패: {e}")

    def _resync_fund_manager_to_ledger(self, vtm) -> None:
        """전략 원장 재구성 결과에 맞춰 FundManager 자금 장부를 재동기화.

        기동 순서상 initializer._initialize_fund_manager 가 원장 *재구성 전에*
        실행되어 allocate_strategy_capital 직후의 집계(8전략×10M = 80,000,000)를
        total_funds 로 받는다. 그 뒤 restore_strategy_ledger_from_records 가
        매매기록에서 전략 현금을 재구성해 집계가 34,892,123 이 되지만 FundManager
        에는 반영되지 않아 가용자금이 1,694만원 과대표시됐다(2026-07-29 라이브:
        총자금 80,000,000 → 교정 후 63,059,833).

        invested_funds 는 건드리지 않는다. vtm 의 _strategy_invested 는
        qty*price*(1+COMMISSION_RATE) 기준이지만 FundManager.invested_funds 는
        순수 매수원가 기준이라(f22e16c) 섞으면 정합성 등식이 다시 깨진다.
        available 만 원장 현금에 맞추고 total 을 역산하면
        total == available + reserved + invested 가 구성상 보존된다.
        """
        fm = self.fund_manager
        if fm is None or vtm is None:
            return

        try:
            ledger_cash = vtm.get_virtual_balance()
            if ledger_cash is None or float(ledger_cash) <= 0:
                logger.warning(
                    f"[가상매매] 전략 원장 현금이 무효({ledger_cash}) - "
                    f"FundManager 재동기화 스킵 (총자금 {fm.total_funds:,.0f}원 유지)"
                )
                return

            ledger_cash = float(ledger_cash)
            # reserved/invested 읽기와 total 갱신을 한 임계구역에 묶는다. 읽은 뒤
            # update_total_funds 가 락을 다시 잡는 사이에 다른 스레드가 예약/체결을
            # 끼워넣으면 new_total 이 낡은 값으로 계산된다. _lock 은 RLock 이라
            # update_total_funds 의 중첩 획득은 안전하다(기능 변화 없음).
            with fm._lock:
                reserved = fm.reserved_funds
                invested = fm.invested_funds
                old_total = fm.total_funds
                new_total = ledger_cash + reserved + invested
                fm.update_total_funds(new_total)

            logger.info(
                f"[가상매매] FundManager 원장 재동기화: "
                f"총자금 {old_total:,.0f}원 → {new_total:,.0f}원 "
                f"(원장 현금 {ledger_cash:,.0f}원 + 예약 {reserved:,.0f}원 "
                f"+ 투자 {invested:,.0f}원)"
            )
        except Exception as e:
            logger.error(f"[가상매매] FundManager 원장 재동기화 실패: {e}")

    def _apply_stale_position_check(
        self, trading_stock, buy_time, target_profit_rate: float, stop_loss_rate: float
    ) -> tuple:
        """복원된 포지션의 보유 기간을 계산하고 장기보유 여부를 판정

        Args:
            trading_stock: TradingStock 인스턴스
            buy_time: 매수 시각 (datetime 또는 timestamp)
            target_profit_rate: 현재 적용된 익절률
            stop_loss_rate: 현재 적용된 손절률

        Returns:
            tuple: (target_profit_rate, stop_loss_rate) - 필요 시 기본값이 적용된 값
        """
        try:
            today = now_kst()

            # buy_time을 datetime으로 변환
            if isinstance(buy_time, (int, float)):
                buy_date = datetime.fromtimestamp(buy_time, tz=timezone.utc)
            elif isinstance(buy_time, datetime):
                buy_date = buy_time
            else:
                # 변환 불가 시 스킵
                return target_profit_rate, stop_loss_rate

            from utils.korean_holidays import count_trading_days_between
            buy_date_naive = buy_date.replace(tzinfo=None) if buy_date.tzinfo else buy_date
            today_naive = today.replace(tzinfo=None)
            days_held = count_trading_days_between(buy_date_naive, today_naive)
            trading_stock.days_held = max(0, days_held)

            stock_code = trading_stock.stock_code
            stock_name = trading_stock.stock_name

            # 30일 이상 보유: 장기보유 경고 + is_stale 마킹
            if days_held >= STALE_POSITION_DAYS:
                trading_stock.is_stale = True
                logger.warning(
                    f"⚠️ {stock_code}({stock_name}) 장기 보유 {days_held}일 - 청산 검토 필요"
                )

            # 7일 이상 보유 + 익절/손절 미설정: 방어적 기본값 적용
            if days_held >= STALE_DEFAULT_APPLY_DAYS:
                # 익절/손절이 DEFAULT_TARGET_PROFIT_RATE/DEFAULT_STOP_LOSS_RATE인 경우는
                # DB에 NULL이어서 기본값이 적용된 것이므로, 원래 NULL이었던 것을 체크
                # 여기서는 원래 값이 NaN/None이어서 기본값으로 대체된 경우를 처리
                # (이미 _restore_holdings_from_db에서 기본값 적용됨)
                # 별도로 stale 전용 기본값을 더 타이트하게 적용
                if target_profit_rate == DEFAULT_TARGET_PROFIT_RATE and stop_loss_rate == DEFAULT_STOP_LOSS_RATE:
                    target_profit_rate = STALE_DEFAULT_TARGET_PROFIT
                    stop_loss_rate = STALE_DEFAULT_STOP_LOSS
                    logger.warning(
                        f"⚠️ {stock_code} 익절/손절 미설정 - 기본값 적용 "
                        f"(익절 {STALE_DEFAULT_TARGET_PROFIT*100:.0f}%, "
                        f"손절 {STALE_DEFAULT_STOP_LOSS*100:.0f}%)"
                    )

        except Exception as e:
            logger.warning(f"장기보유 체크 오류 ({trading_stock.stock_code}): {e}")

        return target_profit_rate, stop_loss_rate

    def _log_stale_position_summary(self, stale_info: list) -> None:
        """장기보유 종목 요약 로그 출력

        Args:
            stale_info: list of dicts with keys:
                stock_code, stock_name, days_held, quantity, buy_price
        """
        try:
            if not stale_info:
                return

            stale_count = len(stale_info)
            total_invested = sum(s['quantity'] * s['buy_price'] for s in stale_info)
            avg_days = sum(s['days_held'] for s in stale_info) / stale_count

            logger.info(
                f"📊 장기보유 현황: {stale_count}개 종목 "
                f"({total_invested:,.0f}원), 평균 보유 {avg_days:.0f}일"
            )

            # 개별 종목 상세 (디버그 레벨)
            for s in stale_info:
                logger.debug(
                    f"  - {s['stock_code']}({s['stock_name']}): "
                    f"{s['days_held']}일, {s['quantity']}주 "
                    f"@{s['buy_price']:,.0f}원"
                )

        except Exception as e:
            logger.warning(f"장기보유 요약 로그 오류: {e}")

    def _log_fund_sync_summary(self, restored_count: int, total_invested: float, mode: str) -> None:
        """포지션 복원 후 자금 동기화 요약 로깅

        Args:
            restored_count: 복원된 종목 수
            total_invested: 총 투자 금액
            mode: 모드 문자열 (가상매매/실전매매)
        """
        if not self.fund_manager:
            logger.info(
                f"[{mode}] 포지션 복원 완료: {restored_count}개 종목, "
                f"투자금액: {total_invested:,.0f}원 (FundManager 미연결)"
            )
            return

        available = self.fund_manager.available_funds
        invested = self.fund_manager.invested_funds
        total = self.fund_manager.total_funds
        position_count = len(self.fund_manager.current_position_codes)
        max_positions = self.fund_manager.max_position_count

        logger.info(
            f"[{mode}] 포지션 복원 완료: {restored_count}개 종목, "
            f"투자금액: {invested:,.0f}원, 가용자금: {available:,.0f}원"
        )

        # ── 진단(2026-08-13) — 런타임 엔트리 ↔ DB 기준선 대조 ─────────────────
        # 목적은 «owner=None 탐지»가 «아니다». add_position 생산자 전수조사 결과
        # owner 를 빠뜨리는 경로는 실주문 2곳뿐이고(order_monitor.py:370 ·
        # order_timeout.py:294), order_monitor.py:364-365 가 스스로 적어놨다 —
        # "이 경로는 페이퍼 모드에선 pending_orders 자체가 비어 휴면이라 무해하나".
        # ⇒ 페이퍼 모드에서 owner 없음 0 은 «정상»이며 blocker 의 반증이 아니다.
        # 진짜 질문은 "런타임 엔트리가 DB 기준선과 일치하는가"이고, 불일치가
        # 나오면 그게 곧 다른 종류의 누수다.
        # 기준선(2026-08-13 종가 후 virtual_trading_records, 두 독립 방법이
        # 대칭 차분 양방향 0 으로 일치): 엔트리 48 / 고유 47종목 / owner 없음 0.
        # 대조 프로브: scripts/probe_position_entries.py
        # 진단 전용 — 프로덕션 동작 0줄이고, 어떤 예외도 복원 흐름으로
        # 전파시키지 않는다(실패 시 WARNING 만).
        try:
            from collections import Counter as _Counter
            _registry = getattr(self.fund_manager, '_position_entries', None)
            if isinstance(_registry, (set, frozenset)):
                with self.fund_manager._lock:
                    _entries = list(_registry)
                _dist = _Counter(owner or "(none)" for _, owner in _entries)
                logger.info(
                    f"[진단] 런타임 포지션 엔트리 {len(_entries)}건 / "
                    f"고유 {len({c for c, _ in _entries})}종목 / "
                    f"소유자별 {dict(_dist)} "
                    f"(DB 기준선 2026-08-13: 48건/47종목/owner없음 0)"
                )
        except Exception as e:
            logger.warning(f"[진단] 런타임 포지션 엔트리 분포 출력 실패: {e}")

        # 포지션 수 제한 초과 경고
        # 근거(2026-07-29 EOD): 이 한도를 실제로 강제하는 fund_manager.can_add_position()은
        # core/trading/order_execution.py의 실주문 경로에서만 호출된다. 페이퍼(가상) 매수는
        # strategy.*Strategy 로거 경로로 체결되어 이 게이트를 거치지 않으므로 신규 매수가
        # 차단되지 않는다(07-29 07:40 경고 발화 직후 24건 정상 체결로 실증). 문구를 "차단됩니다"로
        # 되돌리지 말 것 — 실전 모드에서만 사실이다.
        if position_count > max_positions:
            logger.warning(
                f"보유 종목 수({position_count})가 최대 한도({max_positions})를 "
                f"초과합니다. 기존 보유분이므로 모두 유지합니다. 이 한도는 실주문 경로"
                f"(order_execution.can_add_position)에서만 강제되므로, 페이퍼 매매에서는 "
                f"신규 매수가 차단되지 않고 실전 모드에서만 차단됩니다."
            )

        # 자금 정합성 검증
        expected_total = available + invested + self.fund_manager.reserved_funds
        discrepancy = abs(total - expected_total)
        if discrepancy > 1:  # 1원 이상 불일치
            logger.warning(
                f"자금 정합성 불일치: total_funds({total:,.0f}) != "
                f"available({available:,.0f}) + invested({invested:,.0f}) + "
                f"reserved({self.fund_manager.reserved_funds:,.0f}) = {expected_total:,.0f}"
            )

    async def _restore_candidates(self, today: str) -> None:
        """DB에서 오늘 후보 종목 복원"""
        try:
            # TimescaleDB에서 오늘 후보 종목 직접 조회
            rows = []
            try:
                with DatabaseConnection.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT DISTINCT stock_code, stock_name, score, reasons
                        FROM candidate_stocks
                        WHERE DATE(selection_date) = %s
                        ORDER BY score DESC
                    ''', (today,))
                    rows = cursor.fetchall()
            except Exception as db_err:
                logger.error(f"❌ 후보 종목 DB 조회 실패: {db_err}")
                return

            if not rows:
                logger.info(f"📊 오늘({today}) 후보 종목 없음")
                return

            logger.info(f"🔄 오늘({today}) 후보 종목 {len(rows)}개 복원 시작")
            restored_count = 0

            for row in rows:
                stock_code = row[0]
                stock_name = row[1] or f"Stock_{stock_code}"
                score = row[2] or 0.0
                reason = row[3] or "DB 복원"

                prev_close = self.get_previous_close(stock_code)

                success = await self.trading_manager.add_selected_stock(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    selection_reason=f"DB복원: {reason} (점수: {score})",
                    prev_close=prev_close,
                )

                if success:
                    restored_count += 1

            logger.info(f"✅ 오늘 후보 종목 {restored_count}/{len(rows)}개 복원 완료")

        except Exception as e:
            logger.error(f"❌ 후보 종목 복원 실패: {e}")

    async def _restore_holdings_from_db(self) -> None:
        """DB에서 보유 종목 복원.

        라이브(실전) 모드에서는 real_trading_records 를 읽는다. 실전 fallback이
        가상 테이블(is_test=true)을 읽으면 실보유 0건 복원→실포지션 고아화
        (사전-실전 감사 BLOCKER #3, 2026-06-24).
        """
        try:
            if self.is_paper_trading:
                holdings = self.db_manager.get_virtual_open_positions()
            else:
                holdings = self.db_manager.get_real_open_positions()
            if holdings.empty:
                logger.info("[가상매매] 보유 종목 없음")
                # 보유 0건이어도 원장 재구성은 반드시 실행한다. 여기서 그냥 return 하면
                # allocate_strategy_capital 이 쓴 8×10M 이 그대로 확정되어 누적손익이
                # fund_manager·vtm 양쪽에서 통째로 소멸한다(실현손실 −5,053,250 이면
                # 원장 현금 74,946,750 이어야 하는데 80,000,000 이 남는다).
                # 드문 경로가 아니다 — 세션 로그 100개 중 40개가 flat boot 이다.
                # 빈 포지션 목록으로 재구성하면 매매기록만으로 cash 를 승계하고
                # invested=0 / positions=[] 인 flat 상태가 정확히 표현된다.
                self._reconstruct_strategy_ledger([])
                return

            logger.info(f"[가상매매] 보유 종목 {len(holdings)}개 복원 시작")
            holding_restored = 0
            total_invested = 0.0
            stale_info = []  # 장기보유 종목 정보 수집
            restored_positions = []  # 전략 원장 재구성용 {stock_code, strategy, quantity, buy_price}
            by_owner = {}  # 전략 self.positions 주입용 {owner: {code: {qty, entry_price, entry_time}}}

            for _, holding in holdings.iterrows():
                stock_code = holding['stock_code']
                stock_name = holding['stock_name']
                quantity = int(holding['quantity'])
                buy_price = float(holding['buy_price'])
                buy_time = holding.get('buy_time')  # 매수 시각 (장기보유 체크용)
                raw_tp = holding.get('target_profit_rate')
                try:
                    tp_value = float(raw_tp) if raw_tp is not None else None
                    target_profit_rate = tp_value if (tp_value is not None and not math.isnan(tp_value)) else DEFAULT_TARGET_PROFIT_RATE
                except (ValueError, TypeError, OverflowError):
                    target_profit_rate = DEFAULT_TARGET_PROFIT_RATE
                raw_sl = holding.get('stop_loss_rate')
                try:
                    sl_value = float(raw_sl) if raw_sl is not None else None
                    stop_loss_rate = sl_value if (sl_value is not None and not math.isnan(sl_value)) else DEFAULT_STOP_LOSS_RATE
                except (ValueError, TypeError, OverflowError):
                    stop_loss_rate = DEFAULT_STOP_LOSS_RATE

                prev_close = self.get_previous_close(stock_code)

                # owner 전략을 등록 시점에 바인딩 → 같은 종목을 보유한 여러 전략이
                # 각자 독립 인스턴스로 복원되도록 한다(슬롯 저장소).
                raw_owner = holding.get('strategy', '')
                owner_name = raw_owner.strip() if (raw_owner and isinstance(raw_owner, str)) else ""

                success = await self.trading_manager.add_selected_stock(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    selection_reason=f"보유 종목 복원 ({quantity}주 @{buy_price:,.0f}원)",
                    prev_close=prev_close,
                    owner_strategy=owner_name,
                )

                if success:
                    trading_stock = self.trading_manager.get_trading_stock(
                        stock_code, strategy=(owner_name or None)
                    )
                    if trading_stock:
                        trading_stock.set_position(quantity, buy_price)

                        # DB에서 전략 이름 복원 (strategy 컬럼)
                        db_strategy = holding.get('strategy', '')
                        if db_strategy and isinstance(db_strategy, str) and db_strategy.strip():
                            name = db_strategy.strip()
                            trading_stock.owner_strategy_name = name
                            matched = self._resolve_owner_strategy(name)
                            if matched is not None:
                                trading_stock.owner_strategy = matched
                            else:
                                # 폴더명·클래스명 모두 불일치 → 비활성 전략
                                logger.warning(
                                    f"복원된 종목 {trading_stock.stock_code}의 owner 전략 "
                                    f"{name}이 비활성. 기본 정책 적용."
                                )

                        # 전략 원장 재구성용 포지션 수집 (폴더키=db_strategy)
                        db_strategy = holding.get('strategy', '')
                        pos_strategy = (
                            db_strategy.strip()
                            if (db_strategy and isinstance(db_strategy, str))
                            else ''
                        )
                        # buy_record_id(BUY 행 PK) = 포지션 유일 식별자. 다owner
                        # 동일종목에서 소유권이 서로 덮이지 않도록 함께 넘긴다.
                        raw_id = holding.get('id')
                        try:
                            buy_record_id = int(raw_id) if raw_id is not None else None
                        except (TypeError, ValueError):
                            buy_record_id = None
                        restored_positions.append({
                            'stock_code': stock_code,
                            'strategy': pos_strategy,
                            'quantity': quantity,
                            'buy_price': buy_price,
                            'buy_record_id': buy_record_id,
                        })

                        # 전략 self.positions 주입용 수집 (owner 있을 때만)
                        if owner_name:
                            by_owner.setdefault(owner_name, {})[stock_code] = {
                                'quantity': quantity,
                                'entry_price': buy_price,
                                'entry_time': self._normalize_entry_time(buy_time),
                            }

                        # 가상매수 기록 ID 복원
                        buy_record_id = int(holding.get('id', 0)) if holding.get('id') else None
                        if buy_record_id:
                            trading_stock.set_virtual_buy_info(buy_record_id, buy_price, quantity)

                        # 장기보유 체크 및 기본값 적용
                        if buy_time is not None:
                            target_profit_rate, stop_loss_rate = self._apply_stale_position_check(
                                trading_stock, buy_time,
                                target_profit_rate, stop_loss_rate,
                            )

                        trading_stock.target_profit_rate = target_profit_rate
                        trading_stock.stop_loss_rate = stop_loss_rate

                        self.trading_manager._change_stock_state(
                            stock_code,
                            StockState.POSITIONED,
                            f"DB 복원: {quantity}주 @{buy_price:,.0f}원 "
                            f"(익절:{target_profit_rate*100:.1f}% 손절:{stop_loss_rate*100:.1f}%)"
                            f"{' [장기보유]' if getattr(trading_stock, 'is_stale', False) is True else ''}",
                            strategy=trading_stock.owner_strategy_name,
                        )
                        holding_restored += 1

                        # FundManager 자금 동기화 (owner 는 슬롯 객체에서 — 표기-불변)
                        invested = self._sync_fund_manager_for_position(
                            stock_code, quantity, buy_price,
                            owner=trading_stock.owner_strategy_name or None,
                        )
                        total_invested += invested

                        # VirtualTradingManager 가상 잔고 동기화
                        self._sync_virtual_balance_for_position(quantity, buy_price)

                        # 장기보유 종목 정보 수집
                        ts_is_stale = getattr(trading_stock, 'is_stale', False) is True
                        ts_days_held = getattr(trading_stock, 'days_held', 0)
                        ts_days_held = ts_days_held if isinstance(ts_days_held, int) else 0

                        if ts_is_stale:
                            stale_info.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'days_held': ts_days_held,
                                'quantity': quantity,
                                'buy_price': buy_price,
                            })

                        logger.debug(
                            f"{stock_code} 포지션 복원: {quantity}주 @{buy_price:,.0f}원, "
                            f"익절가 {buy_price*(1+target_profit_rate):,.0f}원, "
                            f"손절가 {buy_price*(1-stop_loss_rate):,.0f}원"
                            f"{f', 보유 {ts_days_held}일' if ts_days_held > 0 else ''}"
                        )

            # 복원 포지션을 전략 self.positions 로 주입 (재시작 시 전략측 청산 복원)
            self._sync_strategy_positions(by_owner)

            # 전략 원장 활성 시: 매매기록에서 전략별 현금/포지션 재구성 (재시작 영속화)
            self._reconstruct_strategy_ledger(restored_positions)

            logger.info(f"[가상매매] 보유 종목 {holding_restored}/{len(holdings)}개 복원 완료")
            self._log_fund_sync_summary(holding_restored, total_invested, "가상매매")

            # 장기보유 종목 요약
            self._log_stale_position_summary(stale_info)

        except Exception as e:
            logger.error(f"[가상매매] 보유 종목 복원 실패: {e}")

    async def _restore_holdings_from_real_account(self) -> None:
        """실전매매 모드: 실제 계좌에서 보유 종목 조회 → DB 동기화 → 메모리 복원"""
        try:
            if not self.broker:
                logger.error("❌ [실전매매] broker가 없어 계좌 조회 불가 - DB 복원으로 대체")
                await self._restore_holdings_from_db()
                return

            logger.info("🔄 [실전매매] 실제 계좌에서 보유 종목 조회 중...")

            # 1. 실전 잔고 — 요약(총평가·종목수)과 보유 목록을 분리 조회 후 교차검증.
            #    get_holdings() 는 실패를 빈 리스트로 삼키므로(broker.py:313,326)
            #    요약 total_stocks 와 대조해야 「빈 계좌」와 「조회 실패」가 갈린다.
            #    (2026-08-14 P0 — 종전 코드는 요약 dict 의 없는 키 'positions' 를
            #     읽어 실보유가 항상 0건이었다)
            from utils.exceptions import LiveStartupAbort
            account_info = self.broker.get_account_balance()
            if not account_info or not isinstance(account_info, dict):
                raise LiveStartupAbort(
                    "실계좌 요약 조회 실패",
                    f"get_account_balance()={str(account_info)[:200]}")
            summary_stock_count = int(account_info.get('total_stocks', 0) or 0)
            real_holdings = self.broker.get_holdings()
            if summary_stock_count > 0 and not real_holdings:
                raise LiveStartupAbort(
                    "실계좌 보유 목록 조회 실패",
                    f"요약 total_stocks={summary_stock_count} 인데 get_holdings() 0건 — 오류 삼킴 의심")
            logger.info(f"📊 [실전매매] 실제 계좌 보유 종목: {len(real_holdings)}개")

            # 2. DB 보유 종목 조회 (실전 owner/buy_time 보강은 실거래 테이블에서)
            #    가상 테이블을 읽으면 실보유 owner 가 공백→전략별 청산 무력
            #    (사전-실전 감사 BLOCKER #4, 2026-06-24).
            db_holdings = self.db_manager.get_real_open_positions()
            db_holdings_dict = {}
            if not db_holdings.empty:
                for _, row in db_holdings.iterrows():
                    raw_tp = row.get('target_profit_rate')
                    raw_sl = row.get('stop_loss_rate')
                    try:
                        tp_val = float(raw_tp) if raw_tp is not None else None
                        tp_rate = tp_val if (tp_val is not None and not math.isnan(tp_val)) else DEFAULT_TARGET_PROFIT_RATE
                    except (ValueError, TypeError, OverflowError):
                        tp_rate = DEFAULT_TARGET_PROFIT_RATE
                    try:
                        sl_val = float(raw_sl) if raw_sl is not None else None
                        sl_rate = sl_val if (sl_val is not None and not math.isnan(sl_val)) else DEFAULT_STOP_LOSS_RATE
                    except (ValueError, TypeError, OverflowError):
                        sl_rate = DEFAULT_STOP_LOSS_RATE
                    code = row['stock_code']
                    if code in db_holdings_dict:
                        # 분할매수 합산: 수량 SUM · 매입가 가중평균.
                        # ORDER BY timestamp DESC 라 첫 행이 최신 — strategy/tp/sl/buy_time 은 최신 행 유지.
                        prev = db_holdings_dict[code]
                        add_qty = int(row['quantity'])
                        new_qty = prev['quantity'] + add_qty
                        if new_qty > 0:
                            prev['buy_price'] = (
                                prev['buy_price'] * prev['quantity']
                                + float(row['buy_price']) * add_qty) / new_qty
                        prev['quantity'] = new_qty
                    else:
                        db_holdings_dict[code] = {
                            'stock_name': row['stock_name'],
                            'quantity': int(row['quantity']),
                            'buy_price': float(row['buy_price']),
                            'buy_time': row.get('buy_time'),
                            'strategy': row.get('strategy', ''),
                            'target_profit_rate': tp_rate,
                            'stop_loss_rate': sl_rate,
                        }

            logger.info(f"📊 [실전매매] DB 보유 종목: {len(db_holdings_dict)}개")

            # 3. 불일치 감지 및 로깅
            await self._detect_holdings_mismatch(real_holdings, db_holdings_dict)

            # 4. 미체결 매도 주문 조회 (C7 fix: SELL_PENDING 중복 매도 방지)
            pending_sell_codes = set()
            try:
                if hasattr(self.broker, 'get_pending_orders'):
                    pending_orders = self.broker.get_pending_orders()
                    if pending_orders:
                        for po in pending_orders:
                            # 매도 미체결 주문의 종목코드 수집
                            order_type = po.get('order_type', '') if isinstance(po, dict) else getattr(po, 'order_type', '')
                            stock_code_po = po.get('stock_code', '') if isinstance(po, dict) else getattr(po, 'stock_code', '')
                            # 매도 주문 판별: "sell", "02" (KIS 매도코드), "SELL" 등
                            if str(order_type).lower() in ('sell', '02', 'sell_market'):
                                pending_sell_codes.add(stock_code_po)
                                logger.info(f"📋 [실전매매] 미체결 매도 주문 발견: {stock_code_po}")
            except Exception as pending_err:
                logger.warning(f"⚠️ [실전매매] 미체결 주문 조회 실패 (POSITIONED로 폴백): {pending_err}")

            # 5. 실제 계좌 기준으로 메모리에 복원
            holding_restored = 0
            total_invested = 0.0
            stale_info = []  # 장기보유 종목 정보 수집
            by_owner = {}  # 전략 self.positions 주입용 {owner: {code: {qty, entry_price, entry_time}}}

            for real_stock in real_holdings:
                stock_code = real_stock.get('stock_code', '')
                stock_name = real_stock.get('stock_name', f'Stock_{stock_code}')
                quantity = int(real_stock.get('quantity', 0))
                avg_price = float(real_stock.get('avg_price', 0))

                if quantity <= 0:
                    continue

                # DB에 해당 종목 정보가 있으면 익절/손절률 사용
                if stock_code in db_holdings_dict:
                    db_info = db_holdings_dict[stock_code]
                    target_profit_rate = db_info.get('target_profit_rate', DEFAULT_TARGET_PROFIT_RATE)
                    stop_loss_rate = db_info.get('stop_loss_rate', DEFAULT_STOP_LOSS_RATE)
                else:
                    target_profit_rate = DEFAULT_TARGET_PROFIT_RATE
                    stop_loss_rate = DEFAULT_STOP_LOSS_RATE
                    logger.warning(f"[실전매매] {stock_code} DB에 없음 - 기본 익절/손절률 적용")

                prev_close = self.get_previous_close(stock_code)

                # owner 전략을 등록 시점에 바인딩 (DB strategy 컬럼 기준)
                _raw_owner = db_holdings_dict.get(stock_code, {}).get('strategy', '') \
                    if stock_code in db_holdings_dict else ''
                owner_name = _raw_owner.strip() if (_raw_owner and isinstance(_raw_owner, str)) else ""

                success = await self.trading_manager.add_selected_stock(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    selection_reason=f"[실전] 보유 종목 복원 ({quantity}주 @{avg_price:,.0f}원)",
                    prev_close=prev_close,
                    owner_strategy=owner_name,
                )

                if success:
                    trading_stock = self.trading_manager.get_trading_stock(
                        stock_code, strategy=(owner_name or None)
                    )
                    if trading_stock:
                        trading_stock.set_position(quantity, avg_price)

                        # DB에서 전략 이름 복원 (이미 add_selected_stock에서 바인딩됨, 멱등 재확인)
                        if owner_name:
                            trading_stock.strategy_name = owner_name

                        # 장기보유 체크: DB에 buy_time이 있으면 사용
                        buy_time = db_holdings_dict.get(stock_code, {}).get('buy_time') if stock_code in db_holdings_dict else None
                        if buy_time is not None:
                            target_profit_rate, stop_loss_rate = self._apply_stale_position_check(
                                trading_stock, buy_time,
                                target_profit_rate, stop_loss_rate,
                            )

                        trading_stock.target_profit_rate = target_profit_rate
                        trading_stock.stop_loss_rate = stop_loss_rate

                        # 전략 self.positions 주입용 수집 (owner 있을 때만)
                        if owner_name:
                            by_owner.setdefault(owner_name, {})[stock_code] = {
                                'quantity': quantity,
                                'entry_price': avg_price,
                                'entry_time': self._normalize_entry_time(buy_time),
                            }

                        # C7 fix: 매도 미체결이 있으면 SELL_PENDING으로 복원
                        if stock_code in pending_sell_codes:
                            restore_state = StockState.SELL_PENDING
                            state_label = "SELL_PENDING (미체결 매도 존재)"
                        else:
                            restore_state = StockState.POSITIONED
                            state_label = "POSITIONED"

                        ts_is_stale = getattr(trading_stock, 'is_stale', False) is True
                        ts_days_held = getattr(trading_stock, 'days_held', 0)
                        ts_days_held = ts_days_held if isinstance(ts_days_held, int) else 0

                        self.trading_manager._change_stock_state(
                            stock_code,
                            restore_state,
                            f"[실전] 계좌 복원: {quantity}주 @{avg_price:,.0f}원 "
                            f"(익절:{target_profit_rate*100:.1f}% 손절:{stop_loss_rate*100:.1f}%) "
                            f"[{state_label}]"
                            f"{' [장기보유]' if ts_is_stale else ''}",
                            strategy=trading_stock.owner_strategy_name,
                        )
                        holding_restored += 1

                        # FundManager 자금 동기화 (owner 는 슬롯 객체에서 — 표기-불변)
                        invested = self._sync_fund_manager_for_position(
                            stock_code, quantity, avg_price,
                            owner=trading_stock.owner_strategy_name or None,
                        )
                        total_invested += invested

                        # 장기보유 종목 정보 수집
                        if ts_is_stale:
                            stale_info.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'days_held': ts_days_held,
                                'quantity': quantity,
                                'buy_price': avg_price,
                            })

                        logger.info(
                            f"[실전] {stock_code}({stock_name}) 복원({state_label}): {quantity}주 @{avg_price:,.0f}원, "
                            f"익절가 {avg_price*(1+target_profit_rate):,.0f}원, "
                            f"손절가 {avg_price*(1-stop_loss_rate):,.0f}원"
                            f"{f', 보유 {ts_days_held}일' if ts_days_held > 0 else ''}"
                        )

            # 복원 포지션을 전략 self.positions 로 주입 (재시작 시 전략측 청산 복원)
            self._sync_strategy_positions(by_owner)

            if real_holdings:
                logger.info(f"[실전매매] 보유 종목 {holding_restored}/{len(real_holdings)}개 복원 완료")
                self._log_fund_sync_summary(holding_restored, total_invested, "실전매매")

                # 장기보유 종목 요약
                self._log_stale_position_summary(stale_info)
            else:
                logger.info("[실전매매] 보유 종목 없음")

        except LiveStartupAbort:
            # 실계좌 조회 실패 = 기동 중단(2026-08-14 P0) — DB 폴백으로 계속하지 않는다.
            raise
        except Exception as e:
            logger.error(f"[실전매매] 보유 종목 복원 실패: {e}")
            logger.warning("DB 복원으로 대체합니다...")
            await self._restore_holdings_from_db()

    async def _detect_holdings_mismatch(self, real_holdings: List[Dict], db_holdings_dict: Dict[str, Dict]) -> None:
        """실제 계좌와 DB 간 보유 종목 불일치 감지 및 자동 조정 (STATE_RESTORATION_AUTO_RECONCILE=True 시)"""
        try:
            mismatches = []
            real_codes = set()
            # 자동조정 대상 수집: (종류, 종목코드, 종목명, 실계좌정보, DB정보)
            reconcile_tasks = []

            for real_stock in real_holdings:
                stock_code = real_stock.get('stock_code', '')
                real_qty = int(real_stock.get('quantity', 0))
                stock_name = real_stock.get('stock_name', stock_code)
                avg_price = float(real_stock.get('avg_price', 0))

                if real_qty <= 0:
                    continue

                real_codes.add(stock_code)

                if stock_code not in db_holdings_dict:
                    mismatches.append(
                        f"⚠️ {stock_code}({stock_name}): 실제 계좌에만 존재 ({real_qty}주) - 외부 매수 또는 DB 누락"
                    )
                    reconcile_tasks.append(('real_only', stock_code, stock_name, real_stock, None))
                else:
                    db_qty = db_holdings_dict[stock_code]['quantity']
                    if real_qty != db_qty:
                        mismatches.append(
                            f"⚠️ {stock_code}({stock_name}): 수량 불일치 (실제: {real_qty}주, DB: {db_qty}주)"
                        )
                        reconcile_tasks.append(('qty_diff', stock_code, stock_name, real_stock, db_holdings_dict[stock_code]))

            for stock_code, db_info in db_holdings_dict.items():
                if stock_code not in real_codes:
                    mismatches.append(
                        f"⚠️ {stock_code}({db_info['stock_name']}): DB에만 존재 ({db_info['quantity']}주) - 외부 매도 또는 미체결"
                    )
                    reconcile_tasks.append(('db_only', stock_code, db_info['stock_name'], None, db_info))

            if mismatches:
                logger.warning(f"🚨 [실전매매] 계좌-DB 불일치 감지: {len(mismatches)}건")
                for m in mismatches:
                    logger.warning(m)

                reconcile_applied = False
                if STATE_RESTORATION_AUTO_RECONCILE and reconcile_tasks:
                    reconcile_applied = await self._reconcile_mismatches(reconcile_tasks)

                if self.telegram:
                    tag = " [자동 보정 적용]" if reconcile_applied else ""
                    alert_msg = f"🚨 계좌-DB 불일치 감지: {len(mismatches)}건{tag}\n\n"
                    for m in mismatches[:5]:
                        alert_msg += f"• {m}\n"
                    if len(mismatches) > 5:
                        alert_msg += f"... 외 {len(mismatches)-5}건"
                    await self.telegram.send_notification(alert_msg)
            else:
                logger.info("✅ [실전매매] 계좌-DB 보유 종목 일치 확인")

        except Exception as e:
            logger.error(f"❌ 불일치 감지 오류: {e}")

    async def _reconcile_mismatches(self, reconcile_tasks: list) -> bool:
        """불일치 항목을 DB INSERT로 자동 보정. 실패 시 raise 금지.

        Returns:
            bool: 하나 이상 성공적으로 보정되었으면 True
        """
        any_success = False
        now = now_kst()

        for task_type, stock_code, stock_name, real_info, db_info in reconcile_tasks:
            try:
                if task_type == 'real_only':
                    # 실계좌에만 있음 → 외부 매수로 간주, BUY 레코드 INSERT
                    avg_price = float(real_info.get('avg_price', 0))
                    real_qty = int(real_info.get('quantity', 0))
                    rec_id = self.db_manager.save_real_buy(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        price=avg_price,
                        quantity=real_qty,
                        strategy='EXTERNAL_MANUAL',
                        reason='자동조정: 실계좌에만 존재(외부매수)',
                        timestamp=now,
                    )
                    if rec_id is not None:
                        logger.info(
                            f"[자동조정] {stock_code} BUY 레코드 생성 (id={rec_id}, "
                            f"{real_qty}주 @{avg_price:,.0f}원, strategy=EXTERNAL_MANUAL)"
                        )
                        any_success = True
                    else:
                        logger.error(f"[자동조정] {stock_code} BUY INSERT 실패")

                elif task_type == 'db_only':
                    # DB에만 있음 → 외부 매도로 간주, 기존 BUY에 대응하는 SELL 레코드 INSERT
                    db_qty = int(db_info['quantity'])
                    buy_record_id = self.db_manager.get_last_open_real_buy(stock_code)
                    ok = self.db_manager.save_real_sell(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        price=0.0,          # 실제 매도가 불확정 → 0으로 마킹
                        quantity=db_qty,
                        strategy='EXTERNAL_SOLD_RECONCILE',
                        reason='자동조정: DB에만 존재(외부매도)',
                        buy_record_id=buy_record_id,
                        timestamp=now,
                    )
                    if ok:
                        logger.info(
                            f"[자동조정] {stock_code} SELL 레코드 생성 "
                            f"({db_qty}주, buy_id={buy_record_id}, strategy=EXTERNAL_SOLD_RECONCILE)"
                        )
                        any_success = True
                    else:
                        logger.error(f"[자동조정] {stock_code} SELL INSERT 실패")

                elif task_type == 'qty_diff':
                    # 수량 불일치 → 차분 처리
                    real_qty = int(real_info.get('quantity', 0))
                    avg_price = float(real_info.get('avg_price', 0))
                    db_qty = int(db_info['quantity'])
                    diff = real_qty - db_qty

                    if diff < 0:
                        # 실계좌 < DB → 부분 매도 간주
                        sold_qty = abs(diff)
                        buy_record_id = self.db_manager.get_last_open_real_buy(stock_code)
                        ok = self.db_manager.save_real_sell(
                            stock_code=stock_code,
                            stock_name=stock_name,
                            price=0.0,
                            quantity=sold_qty,
                            strategy='EXTERNAL_SOLD_RECONCILE',
                            reason=f'자동조정: 수량불일치 부분매도(실제{real_qty}주<DB{db_qty}주)',
                            buy_record_id=buy_record_id,
                            timestamp=now,
                        )
                        if ok:
                            logger.info(
                                f"[자동조정] {stock_code} 부분매도 SELL 레코드 생성 "
                                f"({sold_qty}주, buy_id={buy_record_id})"
                            )
                            any_success = True
                        else:
                            logger.error(f"[자동조정] {stock_code} 부분매도 SELL INSERT 실패")

                    else:
                        # 실계좌 > DB → 부분 추가매수 간주
                        added_qty = diff
                        rec_id = self.db_manager.save_real_buy(
                            stock_code=stock_code,
                            stock_name=stock_name,
                            price=avg_price,
                            quantity=added_qty,
                            strategy='EXTERNAL_MANUAL',
                            reason=f'자동조정: 수량불일치 부분매수(실제{real_qty}주>DB{db_qty}주)',
                            timestamp=now,
                        )
                        if rec_id is not None:
                            logger.info(
                                f"[자동조정] {stock_code} 부분매수 BUY 레코드 생성 "
                                f"(id={rec_id}, +{added_qty}주 @{avg_price:,.0f}원)"
                            )
                            any_success = True
                        else:
                            logger.error(f"[자동조정] {stock_code} 부분매수 BUY INSERT 실패")

            except Exception as e:
                # 자동조정 실패는 critical 로그 + 알림 없이 계속 진행
                logger.critical(f"[자동조정] {stock_code} ({task_type}) 처리 중 예외: {e}")

        return any_success
