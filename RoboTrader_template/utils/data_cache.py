"""
[DEPRECATED] 데이터 캐싱 유틸리티
이 모듈은 더 이상 사용되지 않습니다.
분봉 데이터는 TimescaleDB minute_prices 테이블에 직접 저장됩니다.

Migration Guide:
    - DataCache.save_data() -> PriceRepository.save_minute_data()
    - DataCache.load_data() -> PriceRepository.get_minute_data()
    - DataCache.has_data() -> PriceRepository.has_minute_data()
"""
import warnings
import pandas as pd
from typing import Optional
from utils.logger import setup_logger
from db.repositories.price import PriceRepository


class DataCache:
    """
    [DEPRECATED] 파일 기반 데이터 캐시 관리자

    이 클래스는 더 이상 사용되지 않습니다.
    분봉 데이터는 TimescaleDB minute_prices 테이블에 직접 저장됩니다.

    하위 호환성을 위해 인터페이스를 유지하지만,
    내부적으로 PriceRepository를 호출합니다.

    권장 마이그레이션:
        # 기존 코드
        cache = DataCache()
        cache.save_data(stock_code, date_str, df)
        df = cache.load_data(stock_code, date_str)

        # 새 코드 (권장)
        from db.repositories.price import PriceRepository
        repo = PriceRepository()
        repo.save_minute_data(stock_code, date_str, df)
        df = repo.get_minute_data(stock_code, date_str)
    """

    def __init__(self, cache_dir: str = "cache/minute_data"):
        """
        [DEPRECATED] DataCache 초기화

        Args:
            cache_dir: 무시됨 (하위 호환성을 위해 유지)
        """
        self.logger = setup_logger(__name__)
        self.logger.warning(
            "[DEPRECATED] DataCache는 더 이상 사용되지 않습니다. "
            "PriceRepository를 직접 사용하세요."
        )
        self.price_repo = PriceRepository()
        # 하위 호환성을 위해 cache_dir 속성 유지 (사용되지 않음)
        self._cache_dir = cache_dir

    def _get_cache_file(self, stock_code: str, date_str: str):
        """
        [DEPRECATED] 캐시 파일 경로 생성

        Note:
            이 메서드는 하위 호환성을 위해 유지되지만,
            실제로는 사용되지 않습니다. DB 기반 저장으로 전환되었습니다.
        """
        self.logger.warning(
            "[DEPRECATED] _get_cache_file() - 파일 기반 캐시는 더 이상 사용되지 않습니다."
        )
        return None

    def has_data(self, stock_code: str, date_str: str) -> bool:
        """
        [DEPRECATED] 캐시된 데이터 존재 여부 확인

        PriceRepository.has_minute_data() 사용을 권장합니다.

        Args:
            stock_code: 종목 코드
            date_str: 날짜 문자열 (YYYYMMDD 형식)

        Returns:
            데이터 존재 여부
        """
        self.logger.warning(
            "[DEPRECATED] has_data() -> PriceRepository.has_minute_data() 사용 권장"
        )
        return self.price_repo.has_minute_data(stock_code, date_str)

    def save_data(self, stock_code: str, date_str: str, df_minute: pd.DataFrame) -> bool:
        """
        [DEPRECATED] 1분봉 데이터 저장

        PriceRepository.save_minute_data() 사용을 권장합니다.

        Args:
            stock_code: 종목 코드
            date_str: 날짜 문자열 (YYYYMMDD 형식)
            df_minute: 분봉 데이터 DataFrame

        Returns:
            저장 성공 여부
        """
        self.logger.warning(
            "[DEPRECATED] save_data() -> PriceRepository.save_minute_data() 사용 권장"
        )
        return self.price_repo.save_minute_data(stock_code, date_str, df_minute)

    def load_data(self, stock_code: str, date_str: str) -> Optional[pd.DataFrame]:
        """
        [DEPRECATED] 캐시된 1분봉 데이터 로드

        PriceRepository.get_minute_data() 사용을 권장합니다.

        Args:
            stock_code: 종목 코드
            date_str: 날짜 문자열 (YYYYMMDD 형식)

        Returns:
            분봉 데이터 DataFrame 또는 None
        """
        self.logger.warning(
            "[DEPRECATED] load_data() -> PriceRepository.get_minute_data() 사용 권장"
        )
        return self.price_repo.get_minute_data(stock_code, date_str)

    def clear_cache(self, stock_code: str = None, date_str: str = None):
        """
        [DEPRECATED] 캐시 정리

        Note:
            DB 기반 저장으로 전환되어 이 메서드는 더 이상 작동하지 않습니다.
            데이터 삭제가 필요한 경우 DB에서 직접 삭제하세요.

        Args:
            stock_code: 종목 코드 (무시됨)
            date_str: 날짜 문자열 (무시됨)
        """
        self.logger.warning(
            "[DEPRECATED] clear_cache() - DB 기반 저장으로 전환되어 "
            "이 메서드는 더 이상 작동하지 않습니다. "
            "데이터 삭제가 필요한 경우 DB에서 직접 삭제하세요."
        )
        # No-op: DB 데이터는 이 클래스에서 삭제하지 않음

    def get_cache_size(self) -> dict:
        """
        [DEPRECATED] 캐시 크기 정보

        Note:
            파일 기반 캐시가 아닌 DB 기반으로 전환되어
            이 메서드는 항상 0을 반환합니다.

        Returns:
            캐시 크기 정보 (항상 0)
        """
        self.logger.warning(
            "[DEPRECATED] get_cache_size() - DB 기반 저장으로 전환되어 "
            "파일 캐시 크기는 항상 0입니다."
        )
        return {
            'total_files': 0,
            'total_size_mb': 0,
            'cache_dir': self._cache_dir,
            'note': 'DB 기반 저장으로 전환됨 (minute_prices 테이블)'
        }
