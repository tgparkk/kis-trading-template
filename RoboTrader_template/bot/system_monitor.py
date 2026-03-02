"""
시스템 모니터링 모듈
시스템 상태 모니터링 및 주기적 작업을 담당합니다.
"""
import asyncio
from typing import TYPE_CHECKING

from utils.logger import setup_logger
from utils.korean_time import now_kst, is_market_open
from config.market_hours import MarketHours
from scripts.daily_trading_summary import print_today_trading_summary

if TYPE_CHECKING:
    from main import DayTradingBot


class SystemMonitor:
    """시스템 모니터링 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self.bot = bot
        self.logger = setup_logger(__name__)
        self._last_daily_report_date = None

        # 대시보드 초기화
        self._init_dashboard()

    def _init_dashboard(self):
        """시장현황 대시보드 초기화"""
        self._dashboard = None
        try:
            from market_dashboard.dashboard import MarketDashboard
            from market_dashboard.global_market import GlobalMarketCollector
            from market_dashboard.domestic_market import DomesticMarketCollector
            from config.constants import GLOBAL_MARKET_CACHE_TTL, DOMESTIC_MARKET_CACHE_TTL

            self._dashboard = MarketDashboard(
                domestic_collector=DomesticMarketCollector.from_kis_api(
                    cache_ttl_seconds=DOMESTIC_MARKET_CACHE_TTL
                ),
                global_collector=GlobalMarketCollector(
                    cache_ttl_seconds=GLOBAL_MARKET_CACHE_TTL
                ),
            )
            self.logger.info("시장현황 대시보드 초기화 완료")
        except Exception as e:
            self.logger.warning(f"시장현황 대시보드 초기화 실패 (무시): {e}")

    async def run_system_monitoring_task(self) -> None:
        """시스템 모니터링 태스크"""
        try:
            self.logger.info("시스템 모니터링 태스크 시작")

            last_api_refresh = now_kst()
            last_market_check = now_kst()
            last_portfolio_snapshot = now_kst()

            while self.bot.is_running:
                current_time = now_kst()

                # API 24시간마다 재초기화
                if (current_time - last_api_refresh).total_seconds() >= 86400:  # 24시간
                    await self._refresh_api()
                    last_api_refresh = current_time

                # 08:30 전일 데이터 수집 및 08:55 퀀트 스크리닝 실행 (장 시작 전)
                await self._handle_premarket_tasks(current_time)

                # 15:35 장 마감 후 일일 매매 리포트 생성
                await self._handle_postmarket_tasks(current_time)

                # 30분마다 포트폴리오 스냅샷 저장 (장중에만)
                if (current_time - last_portfolio_snapshot).total_seconds() >= 30 * 60:
                    if is_market_open():
                        await self._save_portfolio_snapshot(current_time)
                    last_portfolio_snapshot = current_time

                # 시스템 모니터링 루프 대기 (5초 주기)
                await asyncio.sleep(5)

                # 30분마다 시스템 상태 로깅
                if (current_time - last_market_check).total_seconds() >= 30 * 60:
                    await self._log_system_status()
                    last_market_check = current_time

        except Exception as e:
            self.logger.error(f"시스템 모니터링 태스크 오류: {e}")
            await self.bot.telegram.notify_error("SystemMonitoring", e)

    async def _handle_premarket_tasks(self, current_time) -> None:
        """장 시작 전 태스크 처리"""
        # 전략의 get_target_stocks()를 통한 후보 종목 자동 등록
        await self._register_strategy_target_stocks()

        # 장전 브리핑 (하루 1회)
        await self._run_premarket_briefing()

    async def _register_strategy_target_stocks(self) -> None:
        """전략의 get_target_stocks()에서 후보 종목을 가져와 등록"""
        try:
            # 이미 등록했으면 스킵 (하루에 1회)
            if hasattr(self, '_strategy_stocks_registered_date'):
                today = now_kst().date()
                if self._strategy_stocks_registered_date == today:
                    return
            
            strategy = getattr(self.bot, 'strategy', None)
            if not strategy or not hasattr(strategy, 'get_target_stocks'):
                return

            target_stocks = strategy.get_target_stocks()
            if not target_stocks:
                return

            trading_manager = getattr(self.bot, 'trading_manager', None)
            if not trading_manager or not hasattr(trading_manager, 'add_selected_stock'):
                return

            self.logger.info(f"전략 후보 종목 {len(target_stocks)}개 등록 시작")
            registered = 0
            for stock_code in target_stocks:
                try:
                    success = await trading_manager.add_selected_stock(
                        stock_code=stock_code,
                        stock_name=stock_code,  # 종목명은 나중에 업데이트됨
                        selection_reason=f"{strategy.name} get_target_stocks()"
                    )
                    if success:
                        registered += 1
                except Exception as e:
                    self.logger.warning(f"전략 후보 종목 등록 실패 ({stock_code}): {e}")

            self._strategy_stocks_registered_date = now_kst().date()
            self.logger.info(f"전략 후보 종목 등록 완료: {registered}/{len(target_stocks)}개")

        except Exception as e:
            self.logger.error(f"전략 후보 종목 등록 오류: {e}")

    async def _run_premarket_briefing(self) -> None:
        """장전 브리핑 실행 (하루 1회)"""
        if self._dashboard is None:
            return
        if self._dashboard.is_briefing_done_today():
            return
        try:
            import asyncio
            await asyncio.to_thread(self._dashboard.generate_premarket_briefing)
            self.logger.info("장전 브리핑 출력 완료")
        except Exception as e:
            self.logger.warning(f"장전 브리핑 오류 (무시): {e}")

    async def _handle_postmarket_tasks(self, current_time) -> None:
        """장 마감 후 태스크 처리"""
        if current_time.hour == 15 and current_time.minute >= 35:
            if self._last_daily_report_date != current_time.date():
                self.logger.info(f"15:35+ 장 마감 후 일일 매매 리포트 생성 ({current_time.strftime('%H:%M:%S')})")
                try:
                    print_today_trading_summary()
                    self._last_daily_report_date = current_time.date()
                    self.logger.info("일일 매매 리포트 생성 완료")
                except Exception as report_err:
                    self.logger.error(f"일일 매매 리포트 생성 오류: {report_err}")

    async def _save_portfolio_snapshot(self, current_time) -> None:
        """포트폴리오 스냅샷 저장 -- 미구현"""
        self.logger.debug("포트폴리오 스냅샷 저장 기능 미구현 (스킵)")

    async def _log_system_status(self) -> None:
        """시스템 상태 로깅"""
        try:
            current_time = now_kst()
            from utils.korean_time import get_market_status
            market_status = get_market_status()

            # 주문 요약
            order_summary = self.bot.order_manager.get_order_summary()

            # 데이터 수집 상태
            candidate_stocks = self.bot.data_collector.get_candidate_stocks()
            data_counts = {stock.code: len(stock.ohlcv_data) for stock in candidate_stocks}

            # API 통계 수집
            from api import kis_auth
            api_stats = kis_auth.get_api_statistics()

            # API 매니저 통계
            api_manager_stats = (
                self.bot.broker.get_api_statistics()
                if hasattr(self.bot.broker, 'get_api_statistics')
                else {}
            )

            # 후보 선정 통계
            selection_stats = {}

            status_lines = [
                f"시스템 상태 [{current_time.strftime('%H:%M:%S')}]",
                f"  - 시장 상태: {market_status}",
                f"  - 미체결 주문: {order_summary['pending_count']}건",
                f"  - 완료 주문: {order_summary['completed_count']}건",
                f"  - 데이터 수집: {data_counts}",
                f"  - API 통계: 총 {api_stats['total_calls']}회 호출, "
                f"성공률 {api_stats['success_rate']}%, "
                f"속도제한 {api_stats['rate_limit_errors']}회 ({api_stats['rate_limit_rate']}%)"
            ]

            # 후보 선정 통계 추가
            if selection_stats and selection_stats.get('total_analyzed', 0) > 0:
                status_lines.append(
                    f"  - 후보 선정: 전체 {selection_stats['total_analyzed']}개 분석, "
                    f"1차 통과 {selection_stats['passed_basic_filter']}개 "
                    f"({selection_stats.get('basic_filter_rate', 0)}%), "
                    f"최종 선정 {selection_stats['final_selected']}개 "
                    f"({selection_stats.get('final_selection_rate', 0)}%)"
                )

            self.logger.info("\n".join(status_lines))

            # 시장현황 대시보드 출력
            await self._run_market_dashboard()

        except Exception as e:
            self.logger.error(f"시스템 상태 로깅 오류: {e}")

    async def _run_market_dashboard(self) -> None:
        """시장현황 대시보드 출력"""
        if self._dashboard is None:
            return
        try:
            import asyncio
            await asyncio.to_thread(self._dashboard.generate_dashboard)
        except Exception as e:
            self.logger.warning(f"시장현황 대시보드 오류 (무시): {e}")

    async def _refresh_api(self) -> None:
        """API 재초기화"""
        try:
            self.logger.info("API 24시간 주기 재초기화 시작")

            # API 매니저 재초기화
            if not await self.bot.broker.connect():
                self.logger.error("API 재초기화 실패")
                await self.bot.telegram.notify_error("API Refresh", "API 재초기화 실패")
                return False

            self.logger.info("API 재초기화 완료")
            await self.bot.telegram.notify_system_status("API 재초기화 완료")
            return True

        except Exception as e:
            self.logger.error(f"API 재초기화 오류: {e}")
            await self.bot.telegram.notify_error("API Refresh", e)
            return False

    def get_last_daily_report_date(self) -> None:
        """마지막 리포트 날짜 반환"""
        return self._last_daily_report_date

    def set_last_daily_report_date(self, date) -> None:
        """마지막 리포트 날짜 설정"""
        self._last_daily_report_date = date
