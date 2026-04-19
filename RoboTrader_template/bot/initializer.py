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
        # 테스트 기간: 가상매매 모드로 항상 1000만원 설정
        if self.bot.decision_engine.is_virtual_mode:
            total_funds = 10000000  # 가상매매 모드: 1천만원
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
