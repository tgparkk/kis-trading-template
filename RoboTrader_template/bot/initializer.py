"""
봇 초기화 모듈
시스템 초기화 및 설정 관련 로직을 담당합니다.
"""
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

    def __init__(self, bot: 'DayTradingBot'):
        self.bot = bot
        self.logger = setup_logger(__name__)

    def setup_signal_handlers(self):
        """시그널 핸들러 등록"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """시그널 핸들러 (Ctrl+C 등)"""
        self.logger.info(f"종료 신호 수신: {signum}")
        self.bot.is_running = False

    def check_duplicate_process(self, pid_file: Path):
        """프로세스 중복 실행 방지"""
        check_duplicate_process(str(pid_file))

    def load_config(self):
        """설정 로드"""
        return load_config()

    def log_rebalancing_mode(self, config):
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
            if not self.bot.api_manager.initialize():
                self.logger.error("API 초기화 실패")
                return False
            self.logger.info("API 매니저 초기화 완료")

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

    async def _initialize_fund_manager(self):
        """자금 관리자 초기화"""
        # 테스트 기간: 가상매매 모드로 항상 1000만원 설정
        if self.bot.decision_engine.is_virtual_mode:
            total_funds = 10000000  # 가상매매 모드: 1천만원
            self.bot.fund_manager.update_total_funds(total_funds)
            self.logger.info(f"자금 관리자 초기화 완료 (가상매매 모드): {total_funds:,.0f}원")
        else:
            balance_info = self.bot.api_manager.get_account_balance()
            if balance_info:
                total_funds = float(balance_info.account_balance) if hasattr(balance_info, 'account_balance') else 10000000
                self.bot.fund_manager.update_total_funds(total_funds)
                self.logger.info(f"자금 관리자 초기화 완료: {total_funds:,.0f}원")
            else:
                self.logger.warning("잔고 조회 실패 - 기본값 1천만원으로 설정")
                self.bot.fund_manager.update_total_funds(10000000)

    async def shutdown(self):
        """시스템 종료"""
        try:
            self.logger.info("시스템 종료 시작")

            # 데이터 수집 중단
            self.bot.data_collector.stop_collection()

            # 주문 모니터링 중단
            self.bot.order_manager.stop_monitoring()

            # 텔레그램 통합 종료
            await self.bot.telegram.shutdown()

            # API 매니저 종료
            self.bot.api_manager.shutdown()

            # PID 파일 삭제
            if self.bot.pid_file.exists():
                self.bot.pid_file.unlink()
                self.logger.info("PID 파일 삭제 완료")

            self.logger.info("시스템 종료 완료")

        except Exception as e:
            self.logger.error(f"시스템 종료 중 오류: {e}")
