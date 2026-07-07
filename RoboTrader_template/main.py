"""
주식 자동매매 시스템 메인 실행 파일
"""
import asyncio
import logging
import signal
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

# Windows 콘솔 UTF-8 인코딩 설정 (이모지 출력 지원)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 프로젝트 경로 추가
sys.path.append(str(Path(__file__).parent))

# .env → os.environ 부트스트랩 (반드시 config/db import 보다 먼저).
# KIS_DATA_SOURCE 는 config.constants 가 import 시점에 읽고,
# TIMESCALE_DB 는 db.connection 이 런타임에 읽는다. stdlib 전용·무크래시.
from config.env_bootstrap import bootstrap as _bootstrap_env
_bootstrap_env()

from core.models import StockState
from core.candidate_selector import CandidateSelector
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
    TASK_SUPERVISOR_MAX_RETRIES, TASK_SUPERVISOR_BASE_DELAY, TASK_SUPERVISOR_MAX_DELAY,
)

# 리팩토링된 모듈 import
from bot.initializer import BotInitializer
from bot.trading_analyzer import TradingAnalyzer
from bot.system_monitor import SystemMonitor
from bot.liquidation_handler import LiquidationHandler
from bot.position_sync import PositionSyncManager
from bot.state_restorer import StateRestorer
from bot.candidate_loader import (
    CandidateLoader,
    should_use_volume_fallback,  # noqa: F401
    apply_volume_fallback_with_filter,  # noqa: F401
)

# Strategy 시스템 import
from strategies.base import BaseStrategy
from strategies.config import StrategyLoader, StrategyConfigError


def pid_file_name(instance_id: str) -> str:
    """Return the PID filename for the given instance_id.

    'default' preserves backward-compatible name 'robotrader.pid'.
    Any other value produces 'robotrader_{instance_id}.pid'.
    """
    if instance_id == "default":
        return "robotrader.pid"
    return f"robotrader_{instance_id}.pid"


class DayTradingBot:
    """주식 자동매매 봇"""

    def __init__(self):
        self.logger = setup_logger(__name__)
        self.is_running = False
        from config.settings import INSTANCE_ID
        self.pid_file = Path(pid_file_name(INSTANCE_ID))

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

        _max_daily_loss = getattr(
            getattr(self.config, 'risk_management', None), 'max_daily_loss', 0.1
        )
        self.fund_manager = FundManager(max_daily_loss_ratio=_max_daily_loss)
        self.order_manager.set_fund_manager(self.fund_manager)

        # 일일 매매 리포트 초기화
        self._last_daily_report_date = None

        # 리팩토링된 핸들러 초기화
        self.bot_initializer = BotInitializer(self)
        self.trading_analyzer = TradingAnalyzer(self)
        self.system_monitor = SystemMonitor(self)
        self.liquidation_handler = LiquidationHandler(self)
        self.position_sync_manager = PositionSyncManager(self)
        self.candidate_loader = CandidateLoader(self)

        # Strategy 시스템 초기화
        self.strategy: Optional[BaseStrategy] = None
        self.strategies: Dict[str, BaseStrategy] = {}
        self._load_strategies()
        self._allocate_strategy_capital()

        # 상태 복원 헬퍼 초기화 (strategies 로드 후 생성해야 참조 전달 가능)
        self.state_restoration_helper = StateRestorer(
            trading_manager=self.trading_manager,
            db_manager=self.db_manager,
            telegram_integration=self.telegram,
            config=self.config,
            get_previous_close_callback=self._get_previous_close_price,
            broker=self.broker,
            fund_manager=self.fund_manager,
            virtual_trading_manager=self.decision_engine.virtual_trading,
            strategies=self.strategies,
        )

        # CandidateSelector 초기화
        self.candidate_selector = CandidateSelector(self.config, self.broker, self.db_manager)
        self._candidates_loaded = False

        # 신호 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """시그널 핸들러 (Ctrl+C 등)"""
        self.logger.info(f"종료 신호 수신: {signum}")
        self.is_running = False

    def _load_strategies(self):
        """다중 또는 단일 전략 로드. backward compat 보장."""
        try:
            strategies_spec = getattr(self.config, 'strategies', None)

            if strategies_spec and isinstance(strategies_spec, list) and len(strategies_spec) > 0:
                # 다중 전략 모드
                self.strategies = StrategyLoader.load_strategies(strategies_spec)
                self.logger.info(f"다중 전략 로드: {list(self.strategies.keys())}")
            else:
                # backward compat: 단일 전략 모드
                strategy_config = getattr(self.config, 'strategy', None)
                if strategy_config is not None:
                    strategy_enabled = getattr(strategy_config, 'enabled', True)
                    if not strategy_enabled:
                        self.logger.info("전략 시스템 비활성화됨 (config.strategy.enabled=False)")
                        return
                    if isinstance(strategy_config, dict):
                        name = strategy_config.get('name', 'sample')
                    else:
                        name = getattr(strategy_config, 'name', 'sample') or 'sample'
                    self.strategies = {name: StrategyLoader.load_strategy(name)}
                    self.logger.info(f"단일 전략 로드(legacy): {name}")
                else:
                    self.strategies = {}
                    self.logger.warning("전략 미설정 — fallback 모드")

            # backward compat: self.strategy = 첫 전략
            if self.strategies:
                self.strategy = next(iter(self.strategies.values()))

        except FileNotFoundError as e:
            self.logger.warning(f"전략 파일 없음 (기본 동작 사용): {e}")
            self.strategy = None
            self.strategies = {}
        except StrategyConfigError as e:
            self.logger.critical(f"전략 설정 오류 (시스템 중단): {e}")
            raise
        except Exception as e:
            self.logger.warning(f"전략 로드 실패 (기본 동작 사용): {e}")
            self.strategy = None
            self.strategies = {}

    def _allocate_strategy_capital(self):
        """가상매매 모드 전략별 자본 할당 (위임)"""
        self.bot_initializer._allocate_strategy_capital()

    async def _initialize_strategy(self) -> bool:
        """전략 초기화 (on_init 호출) — 다중 전략 모드 지원"""
        if not self.strategies:
            return True  # 전략 없으면 성공으로 처리

        failed_names = []
        for name, strat in list(self.strategies.items()):
            try:
                init_result = strat.on_init(
                    broker=self.broker,
                    data_provider=self.data_collector,
                    executor=self.order_manager
                )
                if init_result:
                    self.logger.info(f"전략 초기화 완료: {strat.name}")
                else:
                    self.logger.warning(f"전략 초기화 실패: {strat.name}")
                    failed_names.append(name)
            except Exception as e:
                self.logger.warning(f"전략 초기화 오류 ({name}): {e}")
                failed_names.append(name)

        # 초기화 실패 전략은 제거
        for name in failed_names:
            del self.strategies[name]

        # backward compat: self.strategy 갱신
        if self.strategies:
            self.strategy = next(iter(self.strategies.values()))
        else:
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

        # 전략 초기화
        await self._initialize_strategy()

        # TradingDecisionEngine + TradingStockManager에 전략 연결
        if self.strategy:
            self.decision_engine.set_strategy(self.strategy)
            self.trading_manager.set_strategy(self.strategy)
        # 다중전략 맵 연결 — 체결 콜백·소유 표기를 소유 전략으로 라우팅.
        # (단일 set_strategy만 연결하면 전 전략 체결이 첫 전략(Elder)에 오귀속되어
        #  daily_trades 오염 → 매수 마비. 2026-06-11 진단)
        if getattr(self, 'strategies', None):
            self.decision_engine.set_strategies(self.strategies)
            # 실매매 체결 콜백도 소유 전략으로 라우팅 (완료 핸들러 owner-aware).
            # (단일 set_strategy만 연결되면 전 전략 실체결이 첫 전략에 오귀속.
            #  사전-실전 감사 BLOCKER #2, 2026-06-24)
            self.trading_manager.set_strategies(self.strategies)

        # FundManager + paper_trading 모드 전달
        self.trading_manager.set_fund_manager(self.fund_manager)
        is_paper = getattr(self.decision_engine, 'is_virtual_mode', False)
        self.trading_manager.set_paper_trading(is_paper)

        return True

    async def run_daily_cycle(self) -> None:
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

    def _create_trading_context(self, strategy_name: str = ""):
        """TradingContext 인스턴스 생성"""
        from core.trading_context import TradingContext
        from utils.tick_tracer import TickTracer
        tracer = TickTracer(base_dir=Path("logs/tick_trace"))
        return TradingContext(
            trading_manager=self.trading_manager,
            decision_engine=self.decision_engine,
            fund_manager=self.fund_manager,
            data_collector=self.data_collector,
            intraday_manager=self.intraday_manager,
            trading_analyzer=self.trading_analyzer,
            db_manager=self.db_manager,
            broker=self.broker,
            is_running_check=lambda: self.is_running,
            tracer=tracer,
            strategy_name=strategy_name,
            strategies_dict=self.strategies,
        )

    def ctx_for_strategy(self, strategy_name: str):
        """전략별 TradingContext 인스턴스 생성/캐싱.

        같은 strategy_name 호출 시 같은 인스턴스 반환 (메모리 절약).
        """
        if not hasattr(self, '_strategy_contexts'):
            self._strategy_contexts: Dict = {}
        if strategy_name not in self._strategy_contexts:
            self._strategy_contexts[strategy_name] = self._create_trading_context(
                strategy_name=strategy_name
            )
        return self._strategy_contexts[strategy_name]

    async def _main_trading_loop(self):
        """메인 트레이딩 루프: 데이터수집 -> 주문확인 -> 보유종목체크 -> on_tick/매수판단 -> EOD 순차 실행"""
        import time

        LOOP_INTERVAL = 3  # 기본 루프 간격 (초)
        ON_TICK_EVERY_N = 3  # on_tick은 N번째 반복마다 (≈9초)
        ON_TICK_TIMEOUT = 30  # on_tick 타임아웃 (초)

        self.logger.info("메인 트레이딩 루프 시작")
        iteration = 0

        while self.is_running:
            loop_start = time.monotonic()

            try:
                if not is_market_open():
                    await asyncio.sleep(30)
                    continue

                # 장 시작 후 최초 1회: 스크리너 후보 로드 + 전략 장시작 콜백
                if not self._candidates_loaded:
                    await self._load_screener_candidates()
                    await self._call_strategy_market_open()

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

                # 3. 보유종목 체크 (매 반복 실행 — 손절/익절 모니터링)
                try:
                    await self.trading_manager.check_positions_once()
                except Exception as e:
                    self.logger.error(f"[3/5] 보유종목 체크 오류: {e}")

                # 4. 전략 on_tick — 라운드로빈 (5전략이면 9초×5=45초마다 전부 순환)
                if self.strategies and iteration % ON_TICK_EVERY_N == 0:
                    strategy_names = list(self.strategies.keys())
                    idx = (iteration // ON_TICK_EVERY_N) % len(strategy_names)
                    name = strategy_names[idx]
                    strat = self.strategies[name]

                    # 안 B: EOD 청산 완료 후 intraday 전략 on_tick 스킵 (F1 재매수 사고 방지)
                    _eod_done_today = (
                        hasattr(self, 'liquidation_handler')
                        and self.liquidation_handler is not None
                        and self.liquidation_handler.get_last_eod_liquidation_date() == now_kst().date()
                    )
                    _is_intraday = getattr(strat, 'holding_period', 'intraday') == 'intraday'
                    if _eod_done_today and _is_intraday:
                        self.logger.debug(
                            f"[4/5] on_tick 스킵: EOD 청산 완료 후 intraday 전략 ({name})"
                        )
                    else:
                        ctx = self.ctx_for_strategy(name)
                        try:
                            await asyncio.wait_for(
                                strat.on_tick(ctx),
                                timeout=ON_TICK_TIMEOUT
                            )
                        except asyncio.TimeoutError:
                            self.logger.error(
                                f"전략 {name} on_tick 타임아웃 ({ON_TICK_TIMEOUT}초)"
                            )
                        except Exception as e:
                            self.logger.error(f"[4/5] on_tick 오류 ({name}): {e}")
                elif not self.strategies:
                    # 전략 없으면 기존 방식 fallback (매수 판단만 — 보유종목 체크는 위에서 이미 실행)
                    try:
                        if iteration % ON_TICK_EVERY_N == 0:
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

    async def reload_candidates(self) -> None:
        """후보 종목 강제 재로드 (위임)"""
        await self.candidate_loader.reload_candidates()

    async def _load_screener_candidates(self):
        """후보 종목 로드: 스크리너 우선, 없으면 거래량 순위 자동 수집 (위임)"""
        await self.candidate_loader._load_screener_candidates()

    async def _load_candidates_multi_strategy(self, max_per_strategy: int = 10) -> None:
        """다중 전략 모드 후보 로드 (위임)"""
        await self.candidate_loader._load_candidates_multi_strategy(max_per_strategy)

    async def _check_buy_signals(self):
        """SELECTED 상태 종목 1회 매수 판단"""
        try:
            # 시장 전체 서킷브레이커 발동 시 매수 판단 전체 스킵
            from config.market_hours import get_circuit_breaker_state
            cb_state = get_circuit_breaker_state()
            if cb_state.is_market_halted():
                self.logger.info("매수 판단 스킵: 시장 전체 서킷브레이커 발동 중")
                return

            # 시장 방향성 필터: 폭락장 매수 전체 스킵
            is_crashing, crash_reason = self.decision_engine.check_market_direction()
            if is_crashing:
                self.logger.info(f"매수 판단 스킵: 시장급락 ({crash_reason})")
                return

            selected_stocks = self.trading_manager.get_stocks_by_state(StockState.SELECTED)

            for trading_stock in selected_stocks:
                if not self.is_running:
                    break

                # VI 발동 종목 스킵
                if cb_state.is_vi_active(trading_stock.stock_code):
                    self.logger.debug(f"{trading_stock.stock_code} 매수 스킵: VI 발동 중")
                    continue

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
        """장마감 전 EOD 일괄청산 체크 (실패 시 재시도 포함)"""
        try:
            current_time = now_kst()

            # 평일인지 확인
            if current_time.weekday() >= 5:
                return

            if not hasattr(self, 'liquidation_handler') or not self.liquidation_handler:
                return

            last_eod_date = self.liquidation_handler.get_last_eod_liquidation_date()

            # EOD 청산 실패 종목이 있으면 재시도
            if (last_eod_date == current_time.date()
                    and self.liquidation_handler.has_failed_eod_stocks()):
                _last_retry = getattr(self, '_last_eod_retry_time', None)
                if _last_retry is None or (current_time - _last_retry).total_seconds() >= 10:
                    self._last_eod_retry_time = current_time
                    await self.liquidation_handler.retry_failed_eod_liquidation()
                return

            # 오늘 이미 실행했으면 스킵
            if last_eod_date == current_time.date():
                return

            # 동적 청산 시간 확인
            if not MarketHours.is_eod_liquidation_time('KRX', current_time):
                return

            self.logger.info(f"EOD 일괄청산 시간 도달 ({current_time.strftime('%H:%M:%S')})")
            self.liquidation_handler.set_last_eod_liquidation_date(current_time.date())

            # liquidation_handler를 통해 청산 실행
            await self.liquidation_handler.execute_end_of_day_liquidation()

            # EOD 청산 완료 후 전략 장종료 콜백
            await self._call_strategy_market_close()

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

    async def emergency_sync_positions(self) -> None:
        """긴급 포지션 동기화 (위임)"""
        await self.position_sync_manager.emergency_sync_positions()

    async def shutdown(self) -> None:
        """시스템 종료 (위임)"""
        await self.bot_initializer.shutdown()


async def main() -> None:
    """메인 함수"""
    from bot.env_guard import assert_correct_environment
    assert_correct_environment(os.path.dirname(os.path.abspath(__file__)))

    bot = DayTradingBot()

    # 시스템 초기화
    if not await bot.initialize():
        sys.exit(1)

    # KIS chk-holiday 휴장일 동기화 (auth 완료 후 1회, 캐시 가드로 하루 1회만 API 호출)
    try:
        from utils.holiday_kis_sync import sync_today as _sync_holidays
        _sync_holidays()
    except Exception as e:
        logging.getLogger(__name__).warning(f"휴장일 동기화 스킵: {e}")

    # 일일 거래 사이클 실행
    await bot.run_daily_cycle()


if __name__ == "__main__":
    try:
        # 로그 디렉토리 생성
        Path("logs").mkdir(exist_ok=True)

        # 메인 실행
        asyncio.run(main())

    except KeyboardInterrupt:
        logging.getLogger(__name__).info("사용자에 의해 중단되었습니다.")
    except Exception as e:
        logging.getLogger(__name__).critical(f"시스템 오류: {e}", exc_info=True)
        sys.exit(1)
