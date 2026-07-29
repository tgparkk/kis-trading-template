"""
봇 초기화 모듈
시스템 초기화 및 설정 관련 로직을 담당합니다.
"""
import json
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from utils.logger import setup_logger
from utils.korean_time import now_kst, get_market_status
from utils.price_utils import check_duplicate_process, load_config
from config.market_hours import MarketHours
from config.constants import VIRTUAL_CAPITAL_PER_STRATEGY

if TYPE_CHECKING:
    from main import DayTradingBot


class BotInitializer:
    """봇 초기화 담당 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self.bot = bot
        self.logger = setup_logger(__name__)

    def setup_signal_handlers(self) -> None:
        """시그널 핸들러 등록"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:
        """시그널 핸들러 (Ctrl+C 등)"""
        self.logger.info(f"종료 신호 수신: {signum}")
        self.bot.is_running = False

    def check_duplicate_process(self, pid_file: Path) -> None:
        """프로세스 중복 실행 방지"""
        check_duplicate_process(str(pid_file))

    def load_config(self) -> None:
        """설정 로드"""
        return load_config()

    def log_rebalancing_mode(self, config) -> None:
        """리밸런싱 모드 상태 로깅"""
        if getattr(config, 'rebalancing_mode', False):
            self.logger.info("리밸런싱 모드 활성화: 09:05 리밸런싱으로 매수, 장중 손절/익절 매도 판단 활성화")
        else:
            self.logger.info("하이브리드 모드: 리밸런싱 + 실시간 매수 판단 병행")

    def _allocate_strategy_capital(self) -> None:
        """가상매매 모드에서 각 전략 폴더키에 독립 초기자본을 할당.

        VirtualTradingManager 전략별 자금 격리 원장을 활성화한다.
        - 키는 self.bot.strategies의 폴더키 — TradingContext._strategy_key와 동일하게 매칭됨.
        - 할당이 1건이라도 있으면 집계 virtual_balance = 전략 잔고 합계로 동기화됨.
        - 실전 모드이거나 전략이 없으면 자금 할당은 하지 않음(레거시 단일 잔고 보존).

        부수 책임(2026-07-29): 같은 순회에서 읽은 전략별 K를 합산해
        fund_manager.max_position_count를 정정한다(_apply_total_k_position_limit).
        자금 할당은 가상 전용이지만 **한도 정정은 모드 무관**이므로, 순회를 가상
        게이트 바깥으로 끌어내고 할당 호출만 게이트 안에 둔다.
        """
        try:
            strategies = getattr(self.bot, 'strategies', None) or {}
            engine = getattr(self.bot, 'decision_engine', None)
            vtm = getattr(engine, 'virtual_trading', None)
            is_virtual = getattr(engine, 'is_virtual_mode', False)
            # 자금 할당 가능 여부(= 기존 조기 return 조건들과 동치).
            can_allocate = bool(
                strategies and is_virtual and vtm is not None
                and hasattr(vtm, 'allocate_strategy_capital')
            )

            k_by_strategy: dict = {}   # 유효 K가 확인된 전략만
            unknown_k: list = []       # K 미상 — 합계에서 제외(조용히 0으로 세지 않음)

            for key, strat in strategies.items():
                # 종목당 기본 예산 = 초기자본/K 균등분할 (A안, 2026-06-11 결재 —
                # 백테스트 균등복리 K분할 정합. Elder K20→50만/종목 등).
                # K는 yaml config에서 직접 읽는다 — _max_positions 속성은 각 전략
                # on_init()(bot.initialize 시점)에서야 설정되므로 여기(__init__)서는
                # 항상 부재 → K분할 전면 미적용이었음 (2026-06-12 라이브 확인).
                risk = ((getattr(strat, "config", None) or {})
                        .get("risk_management", {}) or {})
                k = risk.get("max_positions") or getattr(strat, '_max_positions', None)

                # 같은 K를 한도 합산에도 재사용 (별도 순회를 만들지 않는다).
                try:
                    k_int = int(k)
                except (TypeError, ValueError):
                    k_int = 0
                if k_int > 0:
                    k_by_strategy[key] = k_int
                else:
                    unknown_k.append(key)

                if not can_allocate:
                    continue

                vtm.allocate_strategy_capital(
                    key, VIRTUAL_CAPITAL_PER_STRATEGY, max_positions=k)
                # 전략별 종목당 투자금액 (yaml risk_management.paper_investment_per_stock).
                # 명시 시 K분할 기본값을 덮어씀 — 사이징 시나리오 검증값(예: deep_mr_dev20).
                try:
                    per_stock = ((getattr(strat, "config", None) or {})
                                 .get("risk_management", {})
                                 .get("paper_investment_per_stock"))
                    if per_stock and hasattr(vtm, "set_strategy_investment_amount"):
                        vtm.set_strategy_investment_amount(key, float(per_stock))
                except Exception as e:
                    self.logger.warning(f"전략 종목당 투자금액 설정 실패({key}): {e}")

            if can_allocate:
                self.logger.info(
                    f"전략별 가상 자금 할당 완료: {list(strategies.keys())} "
                    f"(전략당 {VIRTUAL_CAPITAL_PER_STRATEGY:,.0f}원, "
                    f"총 {vtm.get_virtual_balance():,.0f}원)"
                )
        except Exception as e:
            self.logger.warning(f"전략별 가상 자금 할당 실패 (단일 잔고 사용): {e}")
            return

        self._apply_total_k_position_limit(k_by_strategy, unknown_k)

    def _apply_total_k_position_limit(self, k_by_strategy: dict,
                                      unknown_k: list) -> None:
        """전략별 K 합계로 fund_manager.max_position_count를 정정 (2026-07-29).

        왜 필요한가 — main.py는 ``FundManager(max_daily_loss_ratio=...)``로만 생성해
        동시 보유 한도가 기본값 **20**이었다. 이 20은 **단일전략 시절의 레거시**다.
        현재는 8전략 독립 운영이라 전략별 K 합계가 58이고, 07-29 실보유는 40종목
        (한도 2배)이었다. 실전 전환 시 20에서 매수가 막히는 사고를 예방하는 것이 목적.

        ⚠️ 이 값을 페이퍼 매수 경로에 결선하지 말 것 — 한도를 실제로 강제하는
        fund_manager.can_add_position()은 core/trading/order_execution.py의 **실주문
        경로에만** 결선돼 있고, 그대로 두는 것이 사장님 결정(2026-07-29)이다. 전역
        한도는 2026-06-16 채택한 *전략별 완전독립 포지션(B안)* 설계와 충돌한다 —
        먼저 채운 전략이 나머지 전략을 굶기는 교차 간섭이 생긴다. 여기서 하는 일은
        **한도값 정정뿐이며 페이퍼 동작은 완전 불변**이다.

        가드:
        - K 미상 전략은 합계에서 제외하고 WARNING (조용히 0으로 세지 않는다).
        - max(기존값, ΣK) — 바닥을 둬서 어떤 경우에도 한도가 좁아지지 않게 한다.
          이 작업은 완화 방향이지 조임 방향이 아니다.
        - 전략이 없거나 ΣK<=0이면 기존값 유지 + WARNING.
        - 가상/실전 모드 무관 적용(실전에서 정확한 값이 필요한 게 목적).
        """
        try:
            fund_manager = getattr(self.bot, 'fund_manager', None)
            if fund_manager is None:
                self.logger.warning(
                    "동시 보유 한도 ΣK 정정 스킵: fund_manager 미연결")
                return

            if unknown_k:
                self.logger.warning(
                    f"동시 보유 한도 ΣK 합산에서 제외 (K 미상 = "
                    f"risk_management.max_positions·_max_positions 모두 부재/무효): "
                    f"{unknown_k}"
                )

            total_k = sum(k_by_strategy.values())
            current = int(getattr(fund_manager, 'max_position_count', 0) or 0)

            if total_k <= 0:
                self.logger.warning(
                    f"동시 보유 한도 ΣK 산출 불가 (유효 K 전략 0개) — "
                    f"기존 한도 {current}종목 유지"
                )
                return

            new_limit = max(current, total_k)
            breakdown = ", ".join(f"{k}={v}" for k, v in k_by_strategy.items())
            fund_manager.max_position_count = new_limit
            self.logger.info(
                f"동시 보유 한도 정정(ΣK): {breakdown} → 합계 {total_k}종목 / "
                f"기존 {current} → 적용 {new_limit}종목 "
                f"(max(기존, ΣK) — 한도는 좁아지지 않음)"
            )
        except Exception as e:
            self.logger.warning(f"동시 보유 한도 ΣK 정정 실패 (기존값 유지): {e}")

    async def initialize_system(self) -> bool:
        """시스템 초기화 (비동기)"""
        try:
            self.logger.info("주식 단타 거래 시스템 초기화 시작")

            # 0. 오늘 거래시간 정보 출력 (특수일 확인)
            today_info = MarketHours.get_today_info('KRX')
            self.logger.info(f"오늘 거래시간 정보:\n{today_info}")

            # 1. API 초기화
            self.logger.info("API 매니저 초기화 시작...")
            if not await self.bot.broker.connect():
                self.logger.error("API 초기화 실패")
                return False
            self.logger.info("API 초기화 완료")

            # 1.5. 자금 관리자 초기화 (API 초기화 후)
            await self._initialize_fund_manager()

            # 2. 시장 상태 확인
            market_status = get_market_status()
            self.logger.info(f"현재 시장 상태: {market_status}")

            # 3. 텔레그램 초기화
            await self.bot.telegram.initialize()

            # 4. DB에서 오늘 날짜의 후보 종목 복원
            await self.bot.state_restoration_helper.restore_todays_candidates()

            self.logger.info("시스템 초기화 완료")
            return True

        except Exception as e:
            self.logger.error(f"시스템 초기화 실패: {e}")
            return False

    async def _initialize_fund_manager(self) -> None:
        """자금 관리자 초기화"""
        if self.bot.decision_engine.is_virtual_mode:
            # 가상매매: VirtualTradingManager가 D-1 잔고를 이미 이월했으므로 그 값을 사용
            virtual_trading = getattr(self.bot.decision_engine, 'virtual_trading', None)
            total_funds = (
                virtual_trading.get_virtual_balance()
                if virtual_trading is not None
                else 0
            )
            if total_funds <= 0:
                total_funds = 10000000  # fallback: 1천만원
            self.bot.fund_manager.update_total_funds(total_funds)
            self.logger.info(f"자금 관리자 초기화 완료 (가상매매 모드): {total_funds:,.0f}원")
        else:
            balance_info = self.bot.broker.get_account_balance()
            if balance_info:
                # KISBroker returns dict, KISAPIManager returns AccountInfo
                if isinstance(balance_info, dict):
                    total_funds = float(balance_info.get('account_balance', 10000000))
                else:
                    total_funds = float(balance_info.account_balance) if hasattr(balance_info, 'account_balance') else 10000000
                self.bot.fund_manager.update_total_funds(total_funds)
                self.logger.info(f"자금 관리자 초기화 완료: {total_funds:,.0f}원")
            else:
                self.logger.warning("잔고 조회 실패 - 기본값 1천만원으로 설정")
                self.bot.fund_manager.update_total_funds(10000000)

    async def shutdown(self) -> None:
        """시스템 종료"""
        try:
            self.logger.info("시스템 종료 시작")

            # 데이터 수집 중단
            self.bot.data_collector.stop_collection()

            # 주문 모니터링 중단
            self.bot.order_manager.stop_monitoring()

            # 메모리 상태 DB/파일 flush (텔레그램 종료 전 — 실패해도 계속)
            self._flush_state_to_db()

            # 텔레그램 통합 종료
            await self.bot.telegram.shutdown()

            # 미체결 주문 취소
            await self._cancel_pending_orders()

            # API 매니저 종료
            self.bot.broker.shutdown()

            # PID 파일 삭제
            if self.bot.pid_file.exists():
                self.bot.pid_file.unlink()
                self.logger.info("PID 파일 삭제 완료")

            self.logger.info("시스템 종료 완료")

        except Exception as e:
            self.logger.error(f"시스템 종료 중 오류: {e}")

    def _flush_state_to_db(self) -> None:
        """종료 시 메모리 상태를 DB/파일에 flush.

        재시작 후 state_restorer가 올바른 익절/손절률과 최고가를 복원할 수 있도록
        POSITIONED/SELL_PENDING 포지션의 런타임 상태를 영속화합니다.
        실패해도 warning만 기록하고 shutdown을 중단하지 않습니다.
        """
        try:
            trading_manager = getattr(self.bot, 'trading_manager', None)
            if trading_manager is None:
                return

            from core.models import StockState
            is_virtual = getattr(
                getattr(self.bot, 'decision_engine', None), 'is_virtual_mode', True
            )

            # DB 업데이트 대상: POSITIONED 또는 SELL_PENDING 종목
            open_states = {StockState.POSITIONED, StockState.SELL_PENDING}
            open_stocks = [
                ts for ts in trading_manager.trading_stocks.values()
                if ts.state in open_states
            ]

            db_manager = getattr(self.bot, 'db_manager', None)
            trading_repo = (
                getattr(db_manager, 'trading', None) if db_manager else None
            )

            # 종목별 런타임 상태 수집 (JSON dump용)
            position_states = {}
            db_flush_count = 0

            for ts in open_stocks:
                stock_code = ts.stock_code
                position_states[stock_code] = {
                    'highest_price_since_buy': ts.highest_price_since_buy,
                    'trailing_stop_activated': ts.trailing_stop_activated,
                    'target_profit_rate': ts.target_profit_rate,
                    'stop_loss_rate': ts.stop_loss_rate,
                }

                # BUY 레코드의 익절/손절률 UPDATE (재시작 시 복원에 사용)
                if trading_repo is not None:
                    try:
                        buy_record_id = (
                            ts._virtual_buy_record_id if is_virtual
                            else getattr(ts, '_real_buy_record_id', None)
                        )
                        if buy_record_id is not None:
                            updated = trading_repo.update_open_position_state(
                                buy_record_id=buy_record_id,
                                target_profit_rate=ts.target_profit_rate,
                                stop_loss_rate=ts.stop_loss_rate,
                                is_virtual=is_virtual,
                            )
                            if updated:
                                db_flush_count += 1
                    except Exception as db_err:
                        self.logger.warning(
                            f"DB flush 실패 ({stock_code}): {db_err}"
                        )

            # FundManager 일일손실 누적값 포함하여 JSON 파일에 저장
            fund_state = {}
            fund_manager = getattr(self.bot, 'fund_manager', None)
            if fund_manager is not None:
                try:
                    today_str = now_kst().strftime('%Y-%m-%d')
                    fund_state = {
                        'date': today_str,
                        'daily_realized_loss': getattr(fund_manager, '_daily_realized_loss', 0.0),
                        'daily_loss_date': getattr(fund_manager, '_daily_loss_date', ''),
                        'total_funds': fund_manager.total_funds,
                    }
                except Exception as fe:
                    self.logger.warning(f"FundManager 상태 수집 실패: {fe}")

            # logs/state/ 하위에 JSON dump
            try:
                log_root = Path(__file__).parent.parent / 'logs' / 'state'
                log_root.mkdir(parents=True, exist_ok=True)
                date_str = now_kst().strftime('%Y-%m-%d')
                state_file = log_root / f'fund_state_{date_str}.json'
                payload = {
                    'timestamp': now_kst().strftime('%Y-%m-%d %H:%M:%S'),
                    'fund': fund_state,
                    'positions': position_states,
                }
                state_file.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
                self.logger.info(
                    f"종료 상태 flush 완료: DB {db_flush_count}건, "
                    f"JSON {len(position_states)}종목 → {state_file}"
                )
            except Exception as fe:
                self.logger.warning(f"상태 JSON 저장 실패: {fe}")

        except Exception as e:
            self.logger.warning(f"_flush_state_to_db 오류 (종료 계속): {e}")

    async def _cancel_pending_orders(self) -> None:
        """종료 시 미체결 주문 일괄 취소"""
        try:
            pending_orders = self.bot.order_manager.get_pending_orders()
            if not pending_orders:
                self.logger.info("미체결 주문 없음 - 취소 스킵")
                return

            self.logger.info(f"미체결 주문 {len(pending_orders)}건 취소 시작")

            for order in pending_orders:
                try:
                    order_id = getattr(order, 'order_id', None)
                    stock_code = getattr(order, 'stock_code', '')
                    if not order_id:
                        continue

                    result = self.bot.broker.cancel_order(
                        order_id=order_id,
                        stock_code=stock_code
                    )
                    if result and result.get('success'):
                        self.logger.info(f"주문 취소 성공: {order_id} ({stock_code})")
                    else:
                        msg = result.get('message', '알 수 없는 오류') if result else '응답 없음'
                        self.logger.warning(f"주문 취소 실패: {order_id} ({stock_code}) - {msg}")
                except Exception as cancel_err:
                    self.logger.error(f"주문 취소 오류 ({getattr(order, 'order_id', '?')}): {cancel_err}")

            self.logger.info("미체결 주문 취소 처리 완료")

        except Exception as e:
            self.logger.error(f"미체결 주문 일괄 취소 오류: {e}")
