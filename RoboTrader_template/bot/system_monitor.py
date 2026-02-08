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

    def __init__(self, bot: 'DayTradingBot'):
        self.bot = bot
        self.logger = setup_logger(__name__)
        self._last_daily_report_date = None
        self._last_eod_liquidation_date = None

    async def run_system_monitoring_task(self):
        """시스템 모니터링 태스크"""
        try:
            self.logger.info("DEBUG: _system_monitoring_task 시작됨")
            self.logger.info("시스템 모니터링 태스크 시작")

            last_api_refresh = now_kst()
            last_market_check = now_kst()
            last_portfolio_snapshot = now_kst()

            self.logger.info("DEBUG: while 루프 진입 시도")
            while self.bot.is_running:
                current_time = now_kst()

                # API 24시간마다 재초기화
                if (current_time - last_api_refresh).total_seconds() >= 86400:  # 24시간
                    await self._refresh_api()
                    last_api_refresh = current_time

                # 08:30 전일 데이터 수집 및 08:55 퀀트 스크리닝 실행 (장 시작 전)
                await self._handle_premarket_tasks(current_time)

                # 장마감 전 EOD 일괄청산 (동적 시간 적용)
                await self._handle_eod_liquidation(current_time)

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

    async def _handle_premarket_tasks(self, current_time):
        """장 시작 전 태스크 처리"""
        # 전략별 premarket 로직은 BaseStrategy.on_market_open()에서 처리
        pass

    async def _handle_eod_liquidation(self, current_time):
        """장마감 전 EOD 일괄청산 처리 (동적 시간 적용)"""
        try:
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
            if hasattr(self.bot, 'liquidation_handler') and self.bot.liquidation_handler:
                await self.bot.liquidation_handler.execute_end_of_day_liquidation()
                # liquidation_handler 자체의 날짜도 업데이트
                self.bot.liquidation_handler.set_last_eod_liquidation_date(current_time.date())
            else:
                self.logger.warning("liquidation_handler가 설정되지 않음 - EOD 청산 스킵")

        except Exception as e:
            self.logger.error(f"EOD 일괄청산 처리 오류: {e}")

    async def _handle_postmarket_tasks(self, current_time):
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

    async def _save_portfolio_snapshot(self, current_time):
        """포트폴리오 스냅샷 저장"""
        self.logger.info(f"포트폴리오 스냅샷 저장 ({current_time.strftime('%H:%M:%S')})")
        try:
            from scripts.save_portfolio_snapshot import save_portfolio_snapshot
            await asyncio.to_thread(save_portfolio_snapshot)
        except Exception as snapshot_err:
            self.logger.error(f"포트폴리오 스냅샷 저장 오류: {snapshot_err}")

    async def _log_system_status(self):
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

        except Exception as e:
            self.logger.error(f"시스템 상태 로깅 오류: {e}")

    async def _refresh_api(self):
        """API 재초기화"""
        try:
            self.logger.info("API 24시간 주기 재초기화 시작")

            # API 매니저 재초기화
            if not self.bot.broker.initialize():
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

    def get_last_daily_report_date(self):
        """마지막 리포트 날짜 반환"""
        return self._last_daily_report_date

    def set_last_daily_report_date(self, date):
        """마지막 리포트 날짜 설정"""
        self._last_daily_report_date = date
