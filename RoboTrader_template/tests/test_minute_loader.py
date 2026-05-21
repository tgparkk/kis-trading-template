"""
Phase 1A 분봉 데이터 로더 테스트

- PriceRepository.get_minute_prices
- PriceRepository.get_minute_prices_bulk
- MinuteCache (hit/miss/evict)
- UnifiedDataLoader.load_minute_data

실 DB 연결 필요 (127.0.0.1:5433 / robotrader).
slow 마커 테스트는 -m "not slow" 로 제외 가능.
"""
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

import pandas as pd
import pytest

# ── 프로젝트 루트를 sys.path에 추가 ──────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── DB 모듈 격리 fixture ─────────────────────────────────────────────────────
# test_database.py가 psycopg2를 mock으로 무조건 교체하므로,
# 이 파일의 테스트 실행 전에 오염된 모듈 캐시를 제거해 실제 psycopg2를 사용한다.
_DB_MODULES_TO_RESET = [
    'psycopg2',
    'psycopg2.pool',
    'psycopg2.extras',
    'psycopg2.extensions',
    'db.connection',
    'db.repositories.base',
    'db.repositories.price',
    'utils.unified_data_loader',
    'utils.minute_cache',
]


@pytest.fixture(autouse=True)
def _reset_db_modules():
    """다른 테스트가 psycopg2를 mock으로 교체했을 때 격리.
    각 테스트 전에 DB 관련 모듈 캐시를 제거하여 실제 psycopg2로 fresh import."""
    # 테스트 실행 전: 오염된 모듈 캐시 제거
    saved = {}
    for mod in _DB_MODULES_TO_RESET:
        if mod in sys.modules:
            saved[mod] = sys.modules.pop(mod)
    yield
    # 테스트 실행 후: 원래 상태로 복원 (다른 테스트에 영향 최소화)
    for mod in _DB_MODULES_TO_RESET:
        sys.modules.pop(mod, None)
    sys.modules.update(saved)

# ── 상수 ─────────────────────────────────────────────────────────────────────
TRADE_DATE = "20260515"          # DB에 실 데이터 존재
TRADE_DATE_DASH = "2026-05-15"   # YYYY-MM-DD 형식
STOCK_CODE = "005930"            # 삼성전자 (389행 확인)
BULK_CODES = ["319400", "440110", "178320", "247540", "348340"]  # 390행씩

EXPECTED_COLUMNS = {"datetime", "open", "high", "low", "close", "volume", "amount"}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PriceRepository.get_minute_prices — 삼성전자 1일치
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetMinutePrices:
    """PriceRepository.get_minute_prices 단위 테스트"""

    def test_삼성전자_1일치_조회(self):
        """005930 한 거래일 조회 → 행 수 > 100, 필수 컬럼 포함"""
        from db.repositories.price import PriceRepository

        repo = PriceRepository()
        df = repo.get_minute_prices(STOCK_CODE, TRADE_DATE)

        assert isinstance(df, pd.DataFrame), "반환 타입은 DataFrame이어야 함"
        assert not df.empty, "결과가 비어 있으면 안 됨"
        assert len(df) > 100, f"행 수가 100 이하: {len(df)}"

        missing = EXPECTED_COLUMNS - set(df.columns)
        assert not missing, f"누락 컬럼: {missing}"

    def test_날짜_형식_YYYY_MM_DD(self):
        """YYYY-MM-DD 형식도 동일하게 동작"""
        from db.repositories.price import PriceRepository

        repo = PriceRepository()
        df_yyyymmdd = repo.get_minute_prices(STOCK_CODE, TRADE_DATE)
        df_dash = repo.get_minute_prices(STOCK_CODE, TRADE_DATE_DASH)

        assert len(df_yyyymmdd) == len(df_dash), \
            "YYYYMMDD와 YYYY-MM-DD 결과 행 수가 달라야 하지 않음"

    def test_빈결과_존재하지않는_종목(self):
        """존재하지 않는 종목/날짜 → 빈 DataFrame"""
        from db.repositories.price import PriceRepository

        repo = PriceRepository()
        df = repo.get_minute_prices("XXXXX", TRADE_DATE)

        assert isinstance(df, pd.DataFrame)
        assert df.empty, "존재하지 않는 종목은 빈 DataFrame이어야 함"

    def test_datetime_컬럼_타입(self):
        """datetime 컬럼이 pandas datetime 타입인지 확인"""
        from db.repositories.price import PriceRepository

        repo = PriceRepository()
        df = repo.get_minute_prices(STOCK_CODE, TRADE_DATE)

        assert not df.empty
        assert pd.api.types.is_datetime64_any_dtype(df["datetime"]), \
            "datetime 컬럼은 datetime64 타입이어야 함"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PriceRepository.get_minute_prices_bulk — 5종목
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetMinutePricesBulk:
    """PriceRepository.get_minute_prices_bulk 단위 테스트"""

    def test_5종목_일괄_조회(self):
        """5종목 한 날짜 → dict 5개 키 모두 존재"""
        from db.repositories.price import PriceRepository

        repo = PriceRepository()
        result = repo.get_minute_prices_bulk(BULK_CODES, TRADE_DATE)

        assert isinstance(result, dict)
        assert set(result.keys()) == set(BULK_CODES), \
            f"반환 키가 입력과 다름: {set(result.keys())}"

        for code in BULK_CODES:
            df = result[code]
            assert isinstance(df, pd.DataFrame), f"{code}: DataFrame이 아님"
            assert not df.empty, f"{code}: 결과가 비어 있음"
            assert len(df) > 100, f"{code}: 행 수 부족 ({len(df)})"

    def test_빈_리스트_입력(self):
        """빈 리스트 → 빈 dict"""
        from db.repositories.price import PriceRepository

        repo = PriceRepository()
        result = repo.get_minute_prices_bulk([], TRADE_DATE)

        assert result == {}

    def test_존재하지않는_종목_포함(self):
        """존재하지 않는 종목 포함 시 해당 종목은 빈 DataFrame"""
        from db.repositories.price import PriceRepository

        repo = PriceRepository()
        codes = [STOCK_CODE, "XXXXX"]
        result = repo.get_minute_prices_bulk(codes, TRADE_DATE)

        assert not result[STOCK_CODE].empty
        assert result["XXXXX"].empty


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MinuteCache — hit / miss / evict
# ═══════════════════════════════════════════════════════════════════════════════

class TestMinuteCache:
    """MinuteCache 단위 테스트 (실 DB 불필요 — 임시 디렉토리 사용)"""

    def _make_cache(self, tmp_path: Path, mem_limit_mb: int = 200):
        from utils.minute_cache import MinuteCache
        return MinuteCache(root_dir=tmp_path, mem_limit_mb=mem_limit_mb)

    def _sample_df(self, rows: int = 10) -> pd.DataFrame:
        return pd.DataFrame({
            "datetime": pd.date_range("2026-05-15 09:00", periods=rows, freq="1min"),
            "open": [100.0] * rows,
            "high": [105.0] * rows,
            "low": [95.0] * rows,
            "close": [102.0] * rows,
            "volume": [1000] * rows,
            "amount": [100000] * rows,
        })

    def test_miss_then_hit_mem(self, tmp_path):
        """같은 (code, date) 두 번 get → 첫 번째 miss, 두 번째 mem hit"""
        cache = self._make_cache(tmp_path)
        df = self._sample_df()

        # 첫 조회: miss
        result = cache.get("005930", "20260515")
        assert result is None
        assert cache.stats()["miss"] == 1

        # put 후 두 번째 조회: mem hit
        cache.put("005930", "20260515", df)
        result2 = cache.get("005930", "20260515")
        assert result2 is not None
        assert cache.stats()["hit_mem"] == 1

    def test_disk_hit(self, tmp_path):
        """put → 새 캐시 인스턴스(메모리 비어있음) → disk hit"""
        from utils.minute_cache import MinuteCache

        df = self._sample_df()
        cache1 = MinuteCache(root_dir=tmp_path)
        cache1.put("005930", "20260515", df)

        # 새 인스턴스 — 메모리 없음
        cache2 = MinuteCache(root_dir=tmp_path)
        result = cache2.get("005930", "20260515")
        assert result is not None
        assert cache2.stats()["hit_disk"] == 1
        assert len(result) == len(df)

    def test_evict_on_mem_limit(self, tmp_path):
        """mem_limit_mb=1 + 큰 DataFrame 여러 개 put → evict 카운트 > 0"""
        cache = self._make_cache(tmp_path, mem_limit_mb=1)

        # 각 DataFrame: 약 700KB (10만행 × 7컬럼)
        for i in range(5):
            big_df = pd.DataFrame({
                "datetime": pd.date_range("2026-05-15", periods=100_000, freq="1s"),
                "open": [100.0] * 100_000,
                "high": [105.0] * 100_000,
                "low": [95.0] * 100_000,
                "close": [102.0] * 100_000,
                "volume": [1000] * 100_000,
                "amount": [100000] * 100_000,
            })
            cache.put(f"CODE{i}", "20260515", big_df)

        assert cache.stats()["evict"] > 0, "evict가 발생해야 함"

    def test_empty_df_not_cached(self, tmp_path):
        """빈 DataFrame put → 캐시 저장 안 됨 (miss 유지)"""
        cache = self._make_cache(tmp_path)
        cache.put("005930", "20260515", pd.DataFrame())

        result = cache.get("005930", "20260515")
        assert result is None, "빈 DataFrame은 캐시 저장하지 않아야 함"

    def test_date_normalization(self, tmp_path):
        """YYYYMMDD / YYYY-MM-DD 혼용해도 같은 캐시 항목 조회"""
        cache = self._make_cache(tmp_path)
        df = self._sample_df()

        cache.put("005930", "20260515", df)
        result = cache.get("005930", "2026-05-15")
        assert result is not None, "날짜 형식 정규화로 같은 항목 조회되어야 함"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. UnifiedDataLoader.load_minute_data
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnifiedLoaderLoadMinuteData:
    """UnifiedDataLoader.load_minute_data 통합 테스트"""

    def test_실DB_데이터_반환(self):
        """load_minute_data('005930', '20260515') → DataFrame 반환"""
        from utils.unified_data_loader import UnifiedDataLoader

        loader = UnifiedDataLoader()
        df = loader.load_minute_data(STOCK_CODE, TRADE_DATE)

        assert df is not None, "DataFrame이 None이면 안 됨"
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert len(df) > 100

        missing = EXPECTED_COLUMNS - set(df.columns)
        assert not missing, f"누락 컬럼: {missing}"

    def test_존재하지않는_종목_None_반환(self):
        """존재하지 않는 종목 → None 반환"""
        from utils.unified_data_loader import UnifiedDataLoader

        loader = UnifiedDataLoader()
        result = loader.load_minute_data("XXXXX", TRADE_DATE)
        assert result is None

    def test_캐시_두번째_호출_메모리hit(self):
        """같은 종목 두 번 호출 → 두 번째는 메모리 캐시에서"""
        from utils.unified_data_loader import UnifiedDataLoader, _minute_cache

        loader = UnifiedDataLoader()
        # 첫 호출 (DB or disk)
        df1 = loader.load_minute_data(STOCK_CODE, TRADE_DATE)
        stats_before = dict(_minute_cache.stats())

        # 두 번째 호출
        df2 = loader.load_minute_data(STOCK_CODE, TRADE_DATE)
        stats_after = dict(_minute_cache.stats())

        assert df1 is not None and df2 is not None
        assert stats_after["hit_mem"] > stats_before["hit_mem"], \
            "두 번째 호출은 메모리 hit이어야 함"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. slow 마커 — 대용량 조회 성능
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
def test_minute_prices_bulk_100종목_30초이내():
    """100종목 1일치 bulk 조회가 30초 이내에 완료되어야 함"""
    import time
    import psycopg2

    conn = psycopg2.connect(
        host="127.0.0.1", port=5433,
        database="robotrader", user="robotrader", password="1234"
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT stock_code FROM minute_candles "
        "WHERE trade_date = %s LIMIT 100",
        (TRADE_DATE,)
    )
    codes = [r[0] for r in cur.fetchall()]
    conn.close()

    from db.repositories.price import PriceRepository
    repo = PriceRepository()

    start = time.time()
    result = repo.get_minute_prices_bulk(codes, TRADE_DATE)
    elapsed = time.time() - start

    assert len(result) == len(codes)
    assert elapsed < 30.0, f"30초 초과: {elapsed:.1f}초"
