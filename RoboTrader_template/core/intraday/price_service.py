"""
장중 현재가 조회 서비스 모듈

매도 판단용 실시간 현재가 조회 및 캐시 관리를 담당합니다.
"""
from typing import Dict, Optional, Any, TYPE_CHECKING

from utils.logger import setup_logger
from utils.korean_time import now_kst
from api.kis_market_api import get_inquire_price

if TYPE_CHECKING:
    from core.intraday_stock_manager import IntradayStockManager

logger = setup_logger(__name__)


class PriceService:
    """
    현재가 조회 서비스 클래스

    매도 판단용 실시간 현재가 조회 및 캐시 관리를 담당합니다.
    """

    def __init__(self, manager: 'IntradayStockManager') -> None:
        """
        Args:
            manager: IntradayStockManager 인스턴스
        """
        self.manager = manager
        self.logger = setup_logger(__name__)

    def get_current_price_for_sell(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        매도 판단용 실시간 현재가 조회

        Args:
            stock_code: 종목코드

        Returns:
            Dict: 현재가 정보 또는 None
        """
        try:
            # J (KRX) 시장으로 현재가 조회
            price_data = get_inquire_price(div_code="J", itm_no=stock_code)

            if price_data is None or price_data.empty:
                self.logger.debug(f"❌ {stock_code} 현재가 조회 실패")
                return None

            row = price_data.iloc[0]

            current_price_info = {
                'stock_code': stock_code,
                'current_price': float(row.get('stck_prpr', 0)),
                'change_rate': float(row.get('prdy_ctrt', 0)),
                'change_price': float(row.get('prdy_vrss', 0)),
                'volume': int(row.get('acml_vol', 0)),
                'high_price': float(row.get('stck_hgpr', 0)),
                'low_price': float(row.get('stck_lwpr', 0)),
                'open_price': float(row.get('stck_oprc', 0)),
                'prev_close': float(row.get('stck_sdpr', 0)),
                'market_cap': int(row.get('hts_avls', 0)),
                'update_time': now_kst()
            }

            return current_price_info

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 현재가 조회 오류: {e}")
            return None

    def get_cached_current_price(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        캐시된 현재가 정보 조회

        Args:
            stock_code: 종목코드

        Returns:
            Dict: 캐시된 현재가 정보 또는 None

        주의(2026-08-12): 이 캐시(`current_price_info`)는 `rebalancing_mode=true`
        (`config/trading_config.json`) 인 동안 절대 채워지지 않는다. 유일한 writer는
        `_update_current_price_data`(realtime_updater.py:436)인데, 이 함수는
        `batch_update_realtime_data`(realtime_updater.py:326)에서만 호출되고
        그 함수의 프로덕션 호출자는 0건이다. 따라서 이 함수는 항상 None을 반환하며,
        모든 호출부는 이 함수 뒤에 반드시 실제 폴백(캐시 실패 시 원가로 되돌리지
        말 것)을 두어야 한다.
        """
        try:
            with self.manager._lock:
                if stock_code not in self.manager.selected_stocks:
                    return None

                stock_data = self.manager.selected_stocks[stock_code]
                return stock_data.current_price_info

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 캐시된 현재가 조회 오류: {e}")
            return None
