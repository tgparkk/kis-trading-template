"""
주식 자동매매 시스템 메인 실행 파일
"""
import asyncio
import signal
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd

# Windows 콘솔 UTF-8 인코딩 설정 (이모지 출력 지원)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 프로젝트 경로 추가
sys.path.append(str(Path(__file__).parent))

from core.models import StockState
from core.data_collector import RealTimeDataCollector
from core.order_manager import OrderManager
from core.telegram_integration import TelegramIntegration
from core.intraday_stock_manager import IntradayStockManager
from core.trading_stock_manager import TradingStockManager
from core.trading_decision_engine import TradingDecisionEngine
from core.fund_manager import FundManager
from db.database_manager import DatabaseManager
from framework import KISBroker
from utils.logger import setup_logger
from utils.korean_time import now_kst, is_market_open
from utils.price_utils import check_duplicate_process, load_config
from config.market_hours import MarketHours
from config.constants import (
    OHLCV_LOOKBACK_DAYS,
    TASK_SUPERVISOR_MAX_RETRIES, TASK_SUPERVISOR_BASE_DELAY, TASK_SUPERVISOR_MAX_DELAY
)

# 리팩토링된 모듈 import
from bot.initializer import BotInitializer
from bot.trading_analyzer import TradingAnalyzer
from bot.system_monitor import SystemMonitor
from bot.liquidation_handler import LiquidationHandler
from bot.position_sync import PositionSyncManager
from bot.state_restorer import StateRestorer

# Strategy 시스템 import
from strategies.base import BaseStrategy
from strategies.config import StrategyLoader, StrategyConfigError


class DayTradingBot:
    """주식 자동매매 봇"""

    def __init__(self):
        self.logger = setup_logger(__name__)
        self.is_running = False
        self.pid_file = Path("robotrader.pid")
        self._last_eod_liquidation_date = None  # 장마감 일괄청산 실행 일자

        # 프로세스 중복 실행 방지
        check_duplicate_process(str(self.pid_file))

        # 설정 초기화
        self.config = load_config()

        # 핵심 모듈 초기화 (의존 순서 주의)
        self.broker = KISBroker()
        self.db_manager = DatabaseManager()
        self.telegram = TelegramIntegration(trading_bot=self)
        self.data_collector = RealTimeDataCollector(self.config, self.broker)
        self.order_manager = OrderManager(self.config, self.broker, self.telegram, self.db_manager)
        self.intraday_manager = IntradayStockManager(self.broker, self.config)
        self.trading_manager = TradingStockManager(
            self.intraday_manager, self.data_collector, self.order_manager, self.telegram
        )
        self.decision_engine = TradingDecisionEngine(
            db_manager=self.db_manager,
            telegram_integration=self.telegram,
            trading_manager=self.trading_manager,
            broker=self.broker,
            intraday_manager=self.intraday_manager,
            config=self.config
        )

        # TradingStockManager에 decision_engine 연결 (쿨다운 설정용)
        self.trading_manager.set_decision_engine(self.decision_engine)

        self.fund_manager = FundManager()

        # 일일 매매 리포트 초기화
        self._last_daily_report_date = None

        # 리팩토링된 핸들러 초기화
        self.bot_initializer = BotInitializer(self)
        self.trading_analyzer = TradingAnalyzer(self)
        self.system_monitor = SystemMonitor(self)
        self.liquidation_handler = LiquidationHandler(self)
        self.position_sync_manager = PositionSyncManager(self)

        # 상태 복원 헬퍼 초기화
        self.state_restoration_helper = StateRestorer(
            trading_manager=self.trading_manager,
            db_manager=self.db_manager,
            telegram_integration=self.telegram,
            config=self.config,
            get_previous_close_callback=self._get_previous_close_price,
            broker=self.broker,
        )

        # Strategy 시스템 초기화
        self.strategy: Optional[BaseStrategy] = None
        self._load_strategy()

        # 신호 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """시그널 핸들러 (Ctrl+C 등)"""
        self.logger.info(f"종료 신호 수신: {signum}")
        self.is_running = False

    def _load_strategy(self):
        """전략 로드 (config에서 지정된 전략 사용)"""
        try:
            # config에서 전략 이름 가져오기
            strategy_config = getattr(self.config, 'strategy', None)
            if isinstance(strategy_config, dict):
                strategy_name = strategy_config.get('name', 'sample')
                strategy_enabled = strategy_config.get('enabled', True)
            else:
                strategy_name = 'sample'
                strategy_enabled = True

            if not strategy_enabled:
                self.logger.info("전략 시스템 비활성화됨 (config.strategy.enabled=False)")
                return

            # 전략 로드
            self.strategy = StrategyLoader.load_strategy(strategy_name)
            self.logger.info(f"전략 로드 완료: {self.strategy.name} v{self.strategy.version}")

        except FileNotFoundError as e:
            self.logger.warning(f"전략 파일 없음 (기본 동작 사용): {e}")
            self.strategy = None
        except StrategyConfigError as e:
            self.logger.warning(f"전략 설정 오류 (기본 동작 사용): {e}")
            self.strategy = None
        except Exception as e:
            self.logger.warning(f"전략 로드 실패 (기본 동작 사용): {e}")
            self.strategy = None

    async def _initialize_strategy(self) -> bool:
        """전략 초기화 (on_init 호출)"""
        if self.strategy is None:
            return True  # 전략 없으면 성공으로 처리

        try:
            # 전략 초기화 - broker, data_provider, executor 전달
            init_result = self.strategy.on_init(
                broker=self.broker,
                data_provider=self.data_collector,
                executor=self.order_manager
            )

            if init_result:
                self.logger.info(f"전략 초기화 완료: {self.strategy.name}")
                return True
            else:
                self.logger.warning(f"전략 초기화 실패: {self.strategy.name}")
                self.strategy = None
                return True  # 시스템은 계속 동작

        except Exception as e:
            self.logger.warning(f"전략 초기화 오류: {e}")
            self.strategy = None
            return True  # 시스템은 계속 동작

    async def _call_strategy_market_open(self):
        """장 시작 시 전략 콜백 호출"""
        if self.strategy is None:
            return
        try:
            self.strategy.on_market_open()
            self.logger.info(f"전략 장시작 콜백 완료: {self.strategy.name}")
        except Exception as e:
            self.logger.warning(f"전략 장시작 콜백 오류: {e}")

    async def _call_strategy_market_close(self):
        """장 종료 시 전략 콜백 호출"""
        if self.strategy is None:
            return
        try:
            self.strategy.on_market_close()
            self.logger.info(f"전략 장종료 콜백 완료: {self.strategy.name}")
        except Exception as e:
            self.logger.warning(f"전략 장종료 콜백 오류: {e}")

    async def initialize(self) -> bool:
        """시스템 초기화"""
        # 기본 시스템 초기화
        if not await self.bot_initializer.initialize_system():
            return False

        # KISBroker 연결 (framework 전략 시스템용)
        if not await self.broker.connect():
            self.logger.warning("KISBroker 연결 실패 - 전략 시스템 없이 계속 운영")

        # 전략 초기화
        await self._initialize_strategy()

        # TradingDecisionEngine + TradingStockManager에 전략 연결
        if self.strategy:
            self.decision_engine.set_strategy(self.strategy)
            self.trading_manager.set_strategy(self.strategy)

        return True

    async def run_daily_cycle(self):
        """일일 거래 사이클 실행"""
        try:
            self.is_running = True
            self.logger.info("일일 거래 사이클 시작")

            # (태스크명, 코루틴팩토리, 필수여부) 정의
            task_definitions = [
                ("메인트레이딩루프", self._main_trading_loop, True),
                ("시스템모니터링", self.system_monitor.run_system_monitoring_task, False),
                ("텔레그램", self._telegram_task, False),
            ]

            # 감독 태스크로 래핑하여 실행
            supervised = [
                self._supervised_task(name, factory, critical)
                for name, factory, critical in task_definitions
            ]

            await asyncio.gather(*supervised)

        except Exception as e:
            self.logger.error(f"일일 거래 사이클 실행 중 오류: {e}")
        finally:
            await self.shutdown()

    async def _supervised_task(self, name: str, task_factory, critical: bool, max_retries: int = TASK_SUPERVISOR_MAX_RETRIES):
        """태스크 감독: 실패 시 재시작, 필수 태스크는 재시도 소진 후 시스템 종료"""
        retries = 0
        base_delay = TASK_SUPERVISOR_BASE_DELAY  # 초기 백오프
        max_delay = TASK_SUPERVISOR_MAX_DELAY   # 최대 백오프

        while self.is_running:
            try:
                self.logger.info(f"[{name}] 태스크 시작" + (f" (재시도 {retries}/{max_retries})" if retries > 0 else ""))
                await task_factory()
                # 정상 종료 (is_running=False 등)
                self.logger.info(f"[{name}] 태스크 정상 종료")
                return
            except Exception as e:
                retries += 1
                self.logger.error(f"[{name}] 태스크 오류 (시도 {retries}/{max_retries}): {e}", exc_info=True)

                # 텔레그램 알림
                try:
                    await self.telegram.notify_error(name, e)
                except Exception as tg_err:
                    self.logger.debug(f"텔레그램 에러 알림 실패: {tg_err}")

                if critical:
                    if retries >= max_retries:
                        msg = f"[{name}] 필수 태스크 {max_retries}회 재시도 실패 - 시스템 종료"
                        self.logger.critical(msg)
                        try:
                            await self.telegram.notify_system_status(msg)
                        except Exception as tg_err:
                            self.logger.debug(f"텔레그램 시스템 상태 알림 실패: {tg_err}")
                        self.is_running = False
                        return
                    # 지수 백오프
                    delay = min(base_delay * (2 ** (retries - 1)), max_delay)
                    self.logger.warning(f"[{name}] {delay}초 후 재시도...")
                    await asyncio.sleep(delay)
                else:
                    if retries >= max_retries:
                        self.logger.warning(f"[{name}] 비필수 태스크 {max_retries}회 재시도 실패 - 포기 (시스템 계속 운영)")
                        return
                    delay = min(base_delay * (2 ** (retries - 1)), max_delay)
                    self.logger.warning(f"[{name}] {delay}초 후 재시도...")
                    await asyncio.sleep(delay)

    async def _main_trading_loop(self):
        """메인 트레이딩 루프: 데이터수집 → 주문확인 → 포지션체크 → 매수판단 → EOD 순차 실행"""
        import time

        LOOP_INTERVAL = 3  # 기본 루프 간격 (초)
        BUY_SIGNAL_EVERY_N = 3  # 매수 판단은 N번째 반복마다 (≈9초)

        self.logger.info("메인 트레이딩 루프 시작")
        iteration = 0

        while self.is_running:
            loop_start = time.monotonic()

            try:
                if not is_market_open():
                    await asyncio.sleep(30)
                    continue

                iteration += 1

                # 각 단계를 독립적으로 실행하여, 한 단계 실패가 다른 단계에 영향 주지 않음
                # (예: 데이터 수집 실패해도 미체결 주문 확인, EOD 청산은 반드시 실행)

                # 1. 데이터 수집
                try:
                    await self.data_collector.collect_once()
                except Exception as e:
                    self.logger.error(f"[1/5] 데이터 수집 오류: {e}")

                # 2. 미체결 주문 확인 (P0: 주문 타임아웃 관리에 필수)
                try:
                    await self.order_manager.check_pending_orders_once()
                except Exception as e:
                    self.logger.error(f"[2/5] 미체결 주문 확인 오류: {e}")

                # 3. 보유종목 체크 (현재가 업데이트 + 매도 판단)
                try:
                    await self.trading_manager.check_positions_once()
                except Exception as e:
                    self.logger.error(f"[3/5] 보유종목 체크 오류: {e}")

                # 4. 매수 판단 (매 N번째 반복, ≈9초 간격)
                try:
                    if iteration % BUY_SIGNAL_EVERY_N == 0:
                        await self._check_buy_signals()
                except Exception as e:
                    self.logger.error(f"[4/5] 매수 판단 오류: {e}")

                # 5. 장마감 일괄청산 체크 (P0: 반드시 실행되어야 함)
                try:
                    await self._check_eod_liquidation()
                except Exception as e:
                    self.logger.error(f"[5/5] EOD 일괄청산 체크 오류: {e}")

            except Exception as e:
                self.logger.error(f"메인 트레이딩 루프 예기치 못한 오류: {e}")

            # 시간 보정 sleep
            elapsed = time.monotonic() - loop_start
            sleep_time = max(0, LOOP_INTERVAL - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        self.logger.info("메인 트레이딩 루프 종료")

    async def _check_buy_signals(self):
        """SELECTED 상태 종목 1회 매수 판단"""
        try:
            selected_stocks = self.trading_manager.get_stocks_by_state(StockState.SELECTED)

            for trading_stock in selected_stocks:
                if not self.is_running:
                    break

                # 매수 쿨다운 확인
                if trading_stock.is_buy_cooldown_active():
                    continue

                try:
                    await self._analyze_buy_decision(trading_stock)
                except Exception as e:
                    self.logger.error(f"매수 판단 오류 ({trading_stock.stock_code}): {e}")

        except Exception as e:
            self.logger.error(f"매수 판단 오류: {e}")

    async def _check_eod_liquidation(self):
        """장마감 전 EOD 일괄청산 체크"""
        try:
            current_time = now_kst()

            # 오늘 이미 실행했으면 스킵
            if self._last_eod_liquidation_date == current_time.date():
                return

            # 평일인지 확인
            if current_time.weekday() >= 5:
                return

            # 동적 청산 시간 확인
            if not MarketHours.is_eod_liquidation_time('KRX', current_time):
                return

            self.logger.info(f"EOD 일괄청산 시간 도달 ({current_time.strftime('%H:%M:%S')})")
            self._last_eod_liquidation_date = current_time.date()

            # liquidation_handler를 통해 청산 실행
            if hasattr(self, 'liquidation_handler') and self.liquidation_handler:
                await self.liquidation_handler.execute_end_of_day_liquidation()
                self.liquidation_handler.set_last_eod_liquidation_date(current_time.date())
            else:
                self.logger.warning("liquidation_handler가 설정되지 않음 - EOD 청산 스킵")

        except Exception as e:
            self.logger.error(f"EOD 일괄청산 체크 오류: {e}")

    async def _analyze_buy_decision(self, trading_stock, available_funds: float = None):
        """매수 판단 분석 (위임)"""
        await self.trading_analyzer.analyze_buy_decision(trading_stock, available_funds)

    async def _analyze_sell_decision(self, trading_stock):
        """매도 판단 분석 (위임)"""
        await self.trading_analyzer.analyze_sell_decision(trading_stock)

    async def _telegram_task(self):
        """텔레그램 태스크"""
        try:
            self.logger.info("텔레그램 태스크 시작")

            # 텔레그램 봇 폴링과 주기적 상태 알림을 병렬 실행
            telegram_tasks = [
                self.telegram.start_telegram_bot(),
                self.telegram.periodic_status_task()
            ]

            await asyncio.gather(*telegram_tasks, return_exceptions=True)

        except Exception as e:
            self.logger.error(f"텔레그램 태스크 오류: {e}")

    async def _system_monitoring_task(self):
        """시스템 모니터링 태스크 (위임)"""
        await self.system_monitor.run_system_monitoring_task()

    async def _liquidate_all_positions_end_of_day(self):
        """장 마감 직전 보유 포지션 전량 시장가 일괄 청산 (위임)"""
        await self.liquidation_handler.liquidate_all_positions_end_of_day()

    async def _execute_end_of_day_liquidation(self):
        """장마감 시간 모든 보유 종목 시장가 일괄매도 (위임)"""
        await self.liquidation_handler.execute_end_of_day_liquidation()

    async def _log_system_status(self):
        """시스템 상태 로깅 (위임)"""
        await self.system_monitor._log_system_status()

    def _get_previous_close_price(self, stock_code: str) -> float:
        """전날 종가 조회 (주말/공휴일 포함 안전 처리)"""
        try:
            daily_data = self.broker.get_ohlcv_data(stock_code, "D", OHLCV_LOOKBACK_DAYS)
            if daily_data is None or (hasattr(daily_data, "empty") and daily_data.empty):
                return 0.0

            if hasattr(daily_data, "sort_values"):
                daily_df = daily_data.sort_values("stck_bsop_date")
                dates = pd.to_datetime(daily_df["stck_bsop_date"], format="%Y%m%d", errors="coerce").dt.date
                daily_df = daily_df.assign(parsed_date=dates)

                if daily_df.empty:
                    return 0.0

                last_row = daily_df.iloc[-1]
                today = now_kst().date()

                if last_row["parsed_date"] == today and len(daily_df) >= 2:
                    return float(daily_df.iloc[-2]["stck_clpr"])

                return float(last_row["stck_clpr"])

            # 리스트 형태 대응 (fallback)
            if len(daily_data) >= 2:
                last_entry = daily_data[-1]
                return getattr(daily_data[-2], "close_price", 0.0)

            return 0.0

        except Exception as e:
            self.logger.debug(f"{stock_code} 전날 종가 조회 실패: {e}")
            return 0.0

    async def emergency_sync_positions(self):
        """긴급 포지션 동기화 (위임)"""
        await self.position_sync_manager.emergency_sync_positions()

    async def shutdown(self):
        """시스템 종료 (위임)"""
        self.broker._connected = False
        await self.bot_initializer.shutdown()


async def main():
    """메인 함수"""
    bot = DayTradingBot()

    # 시스템 초기화
    if not await bot.initialize():
        sys.exit(1)

    # 일일 거래 사이클 실행
    await bot.run_daily_cycle()


if __name__ == "__main__":
    try:
        # 로그 디렉토리 생성
        Path("logs").mkdir(exist_ok=True)

        # 메인 실행
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"시스템 오류: {e}")
        sys.exit(1)
