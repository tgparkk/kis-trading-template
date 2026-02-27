"""시장현황 종합 대시보드

수집기들을 조합하여 장전 브리핑과 장중 대시보드를 생성하는 오케스트레이터.
"""
import logging
from datetime import datetime, date
from typing import Optional, List, Callable

from .models import (
    MarketDashboardData,
    PremarketBriefing,
    PositionSummary,
    DomesticMarketSnapshot,
    GlobalMarketSnapshot,
)
from .global_market import GlobalMarketCollector
from .domestic_market import DomesticMarketCollector
from .formatters import ConsoleFormatter

try:
    from utils.logger import setup_logger
except ImportError:
    def setup_logger(name):
        return logging.getLogger(name)


class MarketDashboard:
    """시장현황 종합 대시보드 (범용 모듈)"""

    def __init__(
        self,
        domestic_collector: Optional[DomesticMarketCollector] = None,
        global_collector: Optional[GlobalMarketCollector] = None,
        position_fn: Optional[Callable[[], List[PositionSummary]]] = None,
    ):
        """
        Args:
            domestic_collector: 국내시장 수집기 (없으면 빈 수집기)
            global_collector: 해외시장 수집기 (없으면 새 인스턴스)
            position_fn: 포지션 조회 콜백 (없으면 빈 리스트)
        """
        self.logger = setup_logger(__name__)
        self._domestic = domestic_collector or DomesticMarketCollector()
        self._global = global_collector or GlobalMarketCollector()
        self._position_fn = position_fn
        self._briefing_done_date: Optional[date] = None

    # ------------------------------------------------------------------
    # 장전 브리핑
    # ------------------------------------------------------------------

    def generate_premarket_briefing(self) -> str:
        """장전 브리핑 생성 (하루 1회)

        해외시장 스냅샷 + 전일 국내시장 마감 데이터를 조회하여
        ConsoleFormatter로 포맷한 뒤 로거로 출력하고, 결과 문자열을 반환합니다.
        이미 오늘 브리핑이 완료된 경우 빈 문자열을 반환합니다.

        Returns:
            포맷된 브리핑 문자열 (실패 또는 중복 시 빈 문자열)
        """
        today = date.today()
        if self._briefing_done_date == today:
            self.logger.debug("오늘 장전 브리핑 이미 완료")
            return ""

        try:
            # 해외시장 스냅샷
            global_snapshot: Optional[GlobalMarketSnapshot] = None
            try:
                global_snapshot = self._global.fetch_snapshot()
            except Exception as e:
                self.logger.warning("해외시장 데이터 조회 실패: {}".format(e))

            # 전일 국내시장 마감 데이터
            domestic_snapshot: Optional[DomesticMarketSnapshot] = None
            try:
                domestic_snapshot = self._domestic.fetch_snapshot(use_cache=False)
            except Exception as e:
                self.logger.warning("국내시장 데이터 조회 실패: {}".format(e))

            briefing = PremarketBriefing(
                global_market=global_snapshot,
                domestic_prev_close=domestic_snapshot,
                briefing_time=datetime.now(),
            )

            result = ConsoleFormatter.format_premarket_briefing(briefing)
            self.logger.info(result)

            self._briefing_done_date = today
            return result

        except Exception as e:
            self.logger.error("장전 브리핑 생성 실패: {}".format(e))
            return ""

    # ------------------------------------------------------------------
    # 장중 대시보드
    # ------------------------------------------------------------------

    def generate_dashboard(self) -> str:
        """장중 대시보드 생성

        국내시장 스냅샷과 보유 포지션을 조회하여
        ConsoleFormatter로 포맷한 뒤 로거로 출력하고, 결과 문자열을 반환합니다.

        Returns:
            포맷된 대시보드 문자열 (실패 시 빈 문자열)
        """
        try:
            # 국내시장 스냅샷
            domestic_snapshot: Optional[DomesticMarketSnapshot] = None
            try:
                domestic_snapshot = self._domestic.fetch_snapshot()
            except Exception as e:
                self.logger.warning("국내시장 데이터 조회 실패: {}".format(e))

            # 포지션 조회
            positions: List[PositionSummary] = []
            if self._position_fn is not None:
                try:
                    positions = self._position_fn()
                except Exception as e:
                    self.logger.warning("포지션 조회 실패: {}".format(e))

            # 손익 합계 계산
            total_pnl = sum(p.profit_loss for p in positions)
            total_eval = sum(p.current_price * p.quantity for p in positions)

            dashboard_data = MarketDashboardData(
                domestic=domestic_snapshot,
                positions=positions,
                total_profit_loss=total_pnl,
                total_eval_amount=total_eval,
                dashboard_time=datetime.now(),
            )

            result = ConsoleFormatter.format_dashboard(dashboard_data)
            self.logger.info(result)
            return result

        except Exception as e:
            self.logger.error("장중 대시보드 생성 실패: {}".format(e))
            return ""

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    def is_briefing_done_today(self) -> bool:
        """오늘 브리핑 완료 여부를 반환합니다."""
        return self._briefing_done_date == date.today()
