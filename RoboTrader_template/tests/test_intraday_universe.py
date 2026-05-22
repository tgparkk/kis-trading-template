"""
분봉 universe 빌더 테스트 (test_minute_loader.py 패턴 준수)

- 합성 DataFrame 기반 단위 테스트 (DB 불필요, _apply_filters 직접 검증)
- 캐시 hit/miss 테스트 (tmp_path 사용)
- 실 DB 통합 테스트 (@pytest.mark.slow)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# ── 프로젝트 루트를 sys.path에 추가 ─────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── DB 모듈 격리 fixture ─────────────────────────────────────────────────────
# 주의: 'db.connection' 등 db.* 패키지 모듈은 reset 대상에서 제외한다.
# db.connection을 pop하면 부모 패키지 'db'에 stale 서브모듈 참조가 남아
# 이후 import 시 sys.modules에 None sentinel이 들어가고, 그 None이
# 다른 테스트 파일(test_backtest_engine_minute.py)로 새어나가 patch가 빗나간다.
# 이 파일 테스트는 'utils.intraday_universe.DatabaseConnection.get_connection'을
# 직접 patch하므로 db.* 모듈 자체를 reset할 필요가 없다.
_DB_MODULES_TO_RESET = [
    'psycopg2',
    'psycopg2.pool',
    'psycopg2.extras',
    'psycopg2.extensions',
    'utils.unified_data_loader',
    'utils.minute_cache',
    'utils.intraday_universe',
]


@pytest.fixture(autouse=True)
def _reset_modules():
    """각 테스트마다 db/psycopg2 모듈을 격리하고, 테스트 후 원상 복구.

    동작:
    1. setup: 테스트 진입 직전의 모듈 객체를 스냅샷(saved)한 뒤 모두 pop
       → 테스트는 다른 테스트가 남긴 mock에 오염되지 않은 fresh import를 받는다.
    2. teardown: 테스트가 import/mock한 모듈을 전부 제거한 뒤 saved를 복원
       → 각 테스트는 자기가 발견한 상태 그대로 남겨, 다른 테스트 파일
         (test_backtest_engine_minute.py 등)로 pollution이 새지 않는다.

    중요: sys.modules에는 실패한 서브모듈 import의 sentinel로 None이 들어갈 수
    있다. None을 그대로 복원하면 이후 `import db.connection`이 빈(None) 모듈을
    돌려줘 AttributeError가 난다. 따라서 saved에는 None이 아닌 모듈만 담는다.
    """
    saved = {
        mod: sys.modules[mod]
        for mod in _DB_MODULES_TO_RESET
        if sys.modules.get(mod) is not None
    }
    for mod in _DB_MODULES_TO_RESET:
        sys.modules.pop(mod, None)
    yield
    for mod in _DB_MODULES_TO_RESET:
        sys.modules.pop(mod, None)
    sys.modules.update(saved)


# ── 합성 데이터 헬퍼 ─────────────────────────────────────────────────────────

def _make_agg_df(rows: list[dict]) -> pd.DataFrame:
    """SQL 집계 결과와 동일한 스키마의 합성 DataFrame 생성.

    columns: stock_code, amount_sum, day_high, day_low, day_close
    """
    return pd.DataFrame(rows, columns=['stock_code', 'amount_sum', 'day_high', 'day_low', 'day_close'])


# ── _apply_filters 단위 테스트 ───────────────────────────────────────────────

class TestApplyFilters:
    """_apply_filters 헬퍼 단위 테스트 (DB 불필요)"""

    def _filters(self, **kwargs):
        from utils.intraday_universe import _apply_filters
        return _apply_filters(**kwargs)

    def test_filter_min_amount(self):
        """거래대금 100억 미만 종목 제외"""
        df = _make_agg_df([
            {'stock_code': 'A', 'amount_sum': 15_000_000_000, 'day_high': 11000, 'day_low': 9000, 'day_close': 10000},
            {'stock_code': 'B', 'amount_sum':  5_000_000_000, 'day_high': 11000, 'day_low': 9000, 'day_close': 10000},
        ])
        result = self._filters(
            df=df, min_amount=10_000_000_000, min_volatility_pct=0.0, min_price=0.0
        )
        assert list(result['stock_code']) == ['A'], "거래대금 미달 종목 B가 제외되어야 함"

    def test_filter_volatility(self):
        """변동성 3% 미만 종목 제외"""
        df = _make_agg_df([
            # 변동성 = (11000-9000)/10000 = 20% → 통과
            {'stock_code': 'A', 'amount_sum': 15_000_000_000, 'day_high': 11000, 'day_low': 9000, 'day_close': 10000},
            # 변동성 = (10100-9900)/10000 = 2% → 제외
            {'stock_code': 'B', 'amount_sum': 15_000_000_000, 'day_high': 10100, 'day_low': 9900, 'day_close': 10000},
        ])
        result = self._filters(
            df=df, min_amount=10_000_000_000, min_volatility_pct=0.03, min_price=0.0
        )
        assert list(result['stock_code']) == ['A'], "변동성 미달 종목 B가 제외되어야 함"

    def test_filter_min_price(self):
        """종가 5,000원 미만 종목 제외"""
        df = _make_agg_df([
            # 종가 10,000 → 통과
            {'stock_code': 'A', 'amount_sum': 15_000_000_000, 'day_high': 11000, 'day_low': 9000, 'day_close': 10000},
            # 종가 3,000 → 제외
            {'stock_code': 'B', 'amount_sum': 15_000_000_000, 'day_high': 3300, 'day_low': 2700, 'day_close': 3000},
        ])
        result = self._filters(
            df=df, min_amount=10_000_000_000, min_volatility_pct=0.0, min_price=5000.0
        )
        assert list(result['stock_code']) == ['A'], "저가주 B가 제외되어야 함"

    def test_three_filters_combined(self):
        """세 필터 동시 적용 — 조건 전부 만족하는 종목만 통과"""
        df = _make_agg_df([
            # 모든 조건 통과
            {'stock_code': 'OK', 'amount_sum': 20_000_000_000, 'day_high': 12000, 'day_low': 8000, 'day_close': 10000},
            # 거래대금 미달
            {'stock_code': 'LOW_AMT', 'amount_sum': 1_000_000_000, 'day_high': 12000, 'day_low': 8000, 'day_close': 10000},
            # 변동성 미달
            {'stock_code': 'LOW_VOL', 'amount_sum': 20_000_000_000, 'day_high': 10100, 'day_low': 9900, 'day_close': 10000},
            # 가격 미달
            {'stock_code': 'LOW_PRC', 'amount_sum': 20_000_000_000, 'day_high': 3300, 'day_low': 2700, 'day_close': 3000},
        ])
        result = self._filters(
            df=df, min_amount=10_000_000_000, min_volatility_pct=0.03, min_price=5000.0
        )
        assert list(result['stock_code']) == ['OK'], "3개 필터 중 하나라도 미달이면 제외"

    def test_empty_input(self):
        """빈 DataFrame 입력 → 빈 DataFrame 반환"""
        from utils.intraday_universe import _apply_filters
        result = _apply_filters(
            pd.DataFrame(columns=['stock_code', 'amount_sum', 'day_high', 'day_low', 'day_close']),
            min_amount=10_000_000_000,
            min_volatility_pct=0.03,
            min_price=5000.0,
        )
        assert result.empty

    def test_volatility_pct_column_added(self):
        """반환 DataFrame에 volatility_pct 컬럼이 추가되어야 함"""
        df = _make_agg_df([
            {'stock_code': 'A', 'amount_sum': 20_000_000_000, 'day_high': 11000, 'day_low': 9000, 'day_close': 10000},
        ])
        result = self._filters(
            df=df, min_amount=10_000_000_000, min_volatility_pct=0.0, min_price=0.0
        )
        assert 'volatility_pct' in result.columns
        assert abs(result.iloc[0]['volatility_pct'] - 0.20) < 1e-9


# ── build_universe_for_date 캐시 테스트 ──────────────────────────────────────

def _make_mock_cursor(df_agg: pd.DataFrame) -> MagicMock:
    """합성 DataFrame을 반환하는 cursor mock 생성."""
    mock_cursor = MagicMock()
    if df_agg.empty:
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = [
            ('stock_code',), ('amount_sum',), ('day_high',), ('day_low',), ('day_close',)
        ]
    else:
        mock_cursor.fetchall.return_value = [tuple(row) for row in df_agg.itertuples(index=False)]
        mock_cursor.description = [(col,) for col in df_agg.columns]
    return mock_cursor


def _make_mock_conn_ctx(mock_cursor: MagicMock):
    """cursor()를 반환하는 conn context manager mock 생성."""
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestBuildUniverseForDate:
    """build_universe_for_date 테스트 (DB mock)"""

    def _patched_universe(self, df_agg: pd.DataFrame, trade_date: str, **kwargs):
        """DatabaseConnection.get_connection을 patch하여 합성 데이터 반환."""
        from utils.intraday_universe import build_universe_for_date

        mock_cursor = _make_mock_cursor(df_agg)
        ctx = _make_mock_conn_ctx(mock_cursor)

        with patch('utils.intraday_universe.DatabaseConnection.get_connection', return_value=ctx):
            return build_universe_for_date(trade_date, **kwargs)

    def test_cache_hit(self, tmp_path):
        """같은 date 두 번 호출 → 두 번째는 캐시에서 (DB 미호출)"""
        df_agg = _make_agg_df([
            {'stock_code': 'AAA', 'amount_sum': 20_000_000_000, 'day_high': 12000, 'day_low': 8000, 'day_close': 10000},
        ])
        codes_first = self._patched_universe(df_agg, '20260515', cache_dir=tmp_path)
        assert codes_first == ['AAA']

        # 두 번째 호출: DB를 전혀 호출하지 않아도 캐시에서 반환되어야 함
        from utils.intraday_universe import build_universe_for_date
        with patch('utils.intraday_universe.DatabaseConnection.get_connection') as mock_db:
            codes_second = build_universe_for_date('20260515', cache_dir=tmp_path)
            mock_db.assert_not_called()

        assert codes_second == ['AAA'], "캐시 hit 시 같은 결과여야 함"

    def test_empty_date(self, tmp_path):
        """데이터 없는 일자 → 빈 리스트"""
        from utils.intraday_universe import build_universe_for_date

        empty_df = _make_agg_df([])
        codes = self._patched_universe(empty_df, '20201231', cache_dir=tmp_path)
        assert codes == [], "데이터 없는 날은 빈 리스트여야 함"

    def test_date_normalization_dash_format(self, tmp_path):
        """YYYY-MM-DD 형식도 정상 처리"""
        df_agg = _make_agg_df([
            {'stock_code': 'BBB', 'amount_sum': 20_000_000_000, 'day_high': 12000, 'day_low': 8000, 'day_close': 10000},
        ])
        codes = self._patched_universe(df_agg, '2026-05-15', cache_dir=tmp_path)
        assert 'BBB' in codes
        # 캐시 파일명은 YYYYMMDD
        cache_file = tmp_path / '20260515.parquet'
        assert cache_file.exists(), "캐시 파일명은 YYYYMMDD여야 함"


# ── build_universe_range 테스트 ───────────────────────────────────────────────

class TestBuildUniverseRange:
    """build_universe_range 테스트 (DB mock)"""

    def _make_range_ctx(self, date_rows: list[str], agg_df: pd.DataFrame):
        """build_universe_range용 cursor mock: 첫 호출=날짜목록, 이후=집계."""
        call_count = {'n': 0}

        def make_cursor():
            call_count['n'] += 1
            mock_cursor = MagicMock()
            if call_count['n'] == 1:
                # 첫 번째 cursor: DISTINCT trade_date 조회
                mock_cursor.fetchall.return_value = [(d,) for d in date_rows]
                mock_cursor.description = [('trade_date',)]
            else:
                # 이후 cursor: 일별 집계
                mock_cursor.fetchall.return_value = [tuple(row) for row in agg_df.itertuples(index=False)]
                mock_cursor.description = [(col,) for col in agg_df.columns]
            return mock_cursor

        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = make_cursor

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_conn)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    def test_build_universe_range_basic(self, tmp_path):
        """2일치 range 호출 → 두 키 모두 존재"""
        from utils.intraday_universe import build_universe_range

        agg_df = _make_agg_df([
            {'stock_code': 'AAA', 'amount_sum': 20_000_000_000, 'day_high': 12000, 'day_low': 8000, 'day_close': 10000},
        ])
        ctx = self._make_range_ctx(['20260514', '20260515'], agg_df)

        with patch('utils.intraday_universe.DatabaseConnection.get_connection', return_value=ctx):
            result = build_universe_range('20260514', '20260515', cache_dir=tmp_path)

        assert '20260514' in result, "20260514 키가 존재해야 함"
        assert '20260515' in result, "20260515 키가 존재해야 함"
        assert len(result) == 2

    def test_skip_dates(self, tmp_path):
        """skip_dates로 제외한 일자는 결과에 없어야 함"""
        from utils.intraday_universe import build_universe_range

        agg_df = _make_agg_df([
            {'stock_code': 'AAA', 'amount_sum': 20_000_000_000, 'day_high': 12000, 'day_low': 8000, 'day_close': 10000},
        ])
        ctx = self._make_range_ctx(['20260514', '20260515'], agg_df)

        with patch('utils.intraday_universe.DatabaseConnection.get_connection', return_value=ctx):
            result = build_universe_range(
                '20260514', '20260515',
                skip_dates={'20260514'},
                cache_dir=tmp_path,
            )

        assert '20260514' not in result, "skip된 날짜는 결과에 없어야 함"
        assert '20260515' in result


# ── top_n cap 테스트 ─────────────────────────────────────────────────────────

class TestTopNLimit:
    """build_universe_for_date top_n / rank_by 기능 단위 테스트 (DB mock)"""

    def _make_large_df(self, n: int) -> pd.DataFrame:
        """n개 종목 합성 DataFrame — volatility_pct와 amount_sum이 다양함."""
        rows = []
        for i in range(n):
            # 종목마다 거래대금·변동성을 달리 해서 순위 검증 가능하게 구성
            amount = 20_000_000_000 + i * 1_000_000_000  # 200억~(200+n)억
            day_high = 11000 + i * 10
            day_low = 9000
            day_close = 10000
            rows.append({
                'stock_code': f'{i:06d}',
                'amount_sum': amount,
                'day_high': day_high,
                'day_low': day_low,
                'day_close': day_close,
            })
        return _make_agg_df(rows)

    def _patched_universe(self, df_agg: pd.DataFrame, trade_date: str, **kwargs):
        from utils.intraday_universe import build_universe_for_date
        mock_cursor = _make_mock_cursor(df_agg)
        ctx = _make_mock_conn_ctx(mock_cursor)
        with patch('utils.intraday_universe.DatabaseConnection.get_connection', return_value=ctx):
            return build_universe_for_date(trade_date, **kwargs)

    def test_top_n_limit(self):
        """합성 입력 100종목 → top_n=10 → 10개 반환"""
        df_agg = self._make_large_df(100)
        codes = self._patched_universe(df_agg, '20260501', top_n=10)
        assert len(codes) == 10, f"top_n=10이면 10개여야 함, 실제: {len(codes)}"

    def test_top_n_rank_by_volatility(self):
        """top_n=5, rank_by='volatility_pct' → volatility_pct 기준 상위 5개 반환"""
        df_agg = self._make_large_df(20)
        from utils.intraday_universe import _apply_filters
        # 필터 통과 후 volatility_pct 계산
        df_filtered = _apply_filters(
            df_agg,
            min_amount=10_000_000_000,
            min_volatility_pct=0.0,
            min_price=0.0,
        )
        top5_expected = df_filtered.nlargest(5, 'volatility_pct')['stock_code'].tolist()

        codes = self._patched_universe(
            df_agg, '20260502',
            top_n=5, rank_by='volatility_pct',
        )
        assert len(codes) == 5
        assert set(codes) == set(top5_expected), (
            f"volatility_pct 상위 5개가 일치하지 않음.\n"
            f"  기대: {top5_expected}\n  실제: {codes}"
        )

    def test_top_n_zero_or_none_unlimited(self, tmp_path):
        """top_n=None이면 cap 없이 전체 반환"""
        df_agg = self._make_large_df(30)
        # top_n 미지정 (None) — 전체 30개 반환
        codes_none = self._patched_universe(df_agg, '20260503', top_n=None)
        assert len(codes_none) == 30, f"top_n=None이면 전체 30개여야 함, 실제: {len(codes_none)}"

    def test_top_n_cache_hit_applies_top_n(self, tmp_path):
        """캐시 hit 시에도 top_n 적용됨 (캐시에는 무제한 저장, 읽을 때 cap)"""
        df_agg = self._make_large_df(20)
        # 1) 캐시 없이 첫 호출 → 20개 캐시 저장
        codes_full = self._patched_universe(df_agg, '20260504', cache_dir=tmp_path)
        assert len(codes_full) == 20, "캐시 저장 시 무제한이어야 함"

        # 2) 캐시 hit + top_n=5 → 5개만 반환 (DB 미호출)
        from utils.intraday_universe import build_universe_for_date
        with patch('utils.intraday_universe.DatabaseConnection.get_connection') as mock_db:
            codes_top5 = build_universe_for_date('20260504', cache_dir=tmp_path, top_n=5)
            mock_db.assert_not_called()
        assert len(codes_top5) == 5, f"캐시 hit top_n=5이면 5개여야 함, 실제: {len(codes_top5)}"


# ── 실 DB 통합 테스트 ────────────────────────────────────────────────────────

@pytest.mark.slow
def test_real_db_20260515():
    """실 DB 1일치 universe 추출 — 50+ 종목 기대"""
    from utils.intraday_universe import build_universe_for_date

    codes = build_universe_for_date('20260515')

    assert isinstance(codes, list), "반환 타입은 list여야 함"
    assert len(codes) >= 50, (
        f"20260515일 universe가 50종목 미만: {len(codes)}종목\n"
        "데이터가 충분한지 DB 확인 필요"
    )
    # 종목코드 형식 검증 (6자리 숫자)
    for code in codes[:5]:
        assert len(code) == 6 and code.isdigit(), f"종목코드 형식 오류: {code}"

    print(f"\n[slow] 20260515 universe: {len(codes)}종목")


# ── dynamic provider 룩어헤드 편향 수정 테스트 ────────────────────────────────
#
# 배경 (확정된 근본 원인):
#   `_make_dynamic_provider`가 만드는 provider `_provider(trade_date)`가
#   `build_universe_for_date(trade_date)`를 거래 당일과 같은 날짜로 호출했다.
#   universe는 그날 종일 데이터(MAX(high)/MIN(low)/SUM(amount))로 변동성 상위 50을
#   뽑으므로 X일 09:00 트레이딩 시작 시점에 X일 종일 데이터를 미리 본 셈 = 룩어헤드.
# 수정: 거래일 X의 universe는 직전 거래일 P(D-1) 데이터로 만들어야 한다.

class TestPriorTradingDay:
    """_prior_trading_day 순수함수 단위 테스트 (DB 불필요)."""

    TRADING_DAYS = ['20250828', '20250829', '20250901', '20250902', '20250903']

    def _fn(self):
        from scripts.run_intraday_tournament import _prior_trading_day
        return _prior_trading_day

    def test_normal_prior_day(self):
        """캘린더에 존재하는 거래일 → 바로 직전 거래일 반환."""
        fn = self._fn()
        assert fn('20250901', self.TRADING_DAYS) == '20250829'
        assert fn('20250903', self.TRADING_DAYS) == '20250902'

    def test_first_day_returns_none(self):
        """캘린더 최초일 → 직전 거래일 없음 → None."""
        fn = self._fn()
        assert fn('20250828', self.TRADING_DAYS) is None

    def test_date_before_calendar_returns_none(self):
        """캘린더 시작보다 이전 날짜 → None."""
        fn = self._fn()
        assert fn('20250101', self.TRADING_DAYS) is None

    def test_date_between_trading_days(self):
        """두 거래일 사이의 (휴장) 날짜 → 가장 가까운 이전 거래일 반환."""
        fn = self._fn()
        # 20250830, 20250831은 거래일이 아님 → 직전 거래일은 20250829
        assert fn('20250831', self.TRADING_DAYS) == '20250829'

    def test_date_after_calendar(self):
        """캘린더 끝보다 이후 날짜 → 마지막 거래일 (엄격히 작은 최대값)."""
        fn = self._fn()
        assert fn('20251231', self.TRADING_DAYS) == '20250903'

    def test_empty_calendar_returns_none(self):
        """빈 캘린더 → None."""
        fn = self._fn()
        assert fn('20250901', []) is None


class TestDynamicProviderLookahead:
    """dynamic provider가 당일이 아닌 직전 거래일 데이터로 universe를 만드는지 검증.

    현재(버그) 코드에서는 build_universe_for_date가 trade_date 그대로 호출되어 실패(red),
    수정 후에는 직전 거래일 P로 호출되어 통과(green) 해야 한다.
    """

    TRADING_DAYS = ['20250828', '20250829', '20250901', '20250902']

    def test_provider_builds_with_prior_trading_day(self):
        """provider(X) 호출 시 build_universe_for_date가 X가 아닌 직전 거래일 P로 호출됨."""
        from scripts.run_intraday_tournament import _make_dynamic_provider

        called_dates = []

        def _fake_build(trade_date, **kwargs):
            called_dates.append(trade_date)
            return ['A00001', 'A00002']

        with patch(
            'scripts.run_intraday_tournament._load_trading_days',
            return_value=list(self.TRADING_DAYS),
        ), patch(
            'utils.intraday_universe.build_universe_for_date',
            side_effect=_fake_build,
        ):
            provider = _make_dynamic_provider(cache_dir='cache/intraday_universe', top_n=50)
            result = provider('20250901')

        assert result == ['A00001', 'A00002']
        # 핵심 단언: 거래 당일(20250901)이 아니라 직전 거래일(20250829)로 build 됨
        assert called_dates == ['20250829'], (
            f"build_universe_for_date가 직전 거래일이 아닌 날짜로 호출됨: {called_dates}. "
            f"룩어헤드 편향 — 거래일 X의 universe는 D-1로 만들어야 함."
        )

    def test_provider_first_day_returns_empty(self):
        """캘린더 최초일에는 직전 거래일이 없으므로 빈 리스트 반환, build 미호출."""
        from scripts.run_intraday_tournament import _make_dynamic_provider

        called_dates = []

        def _fake_build(trade_date, **kwargs):
            called_dates.append(trade_date)
            return ['X']

        with patch(
            'scripts.run_intraday_tournament._load_trading_days',
            return_value=list(self.TRADING_DAYS),
        ), patch(
            'utils.intraday_universe.build_universe_for_date',
            side_effect=_fake_build,
        ):
            provider = _make_dynamic_provider(cache_dir='cache/intraday_universe', top_n=50)
            result = provider('20250828')  # 캘린더 최초일

        assert result == []
        assert called_dates == [], "최초일에는 build_universe_for_date를 호출하면 안 됨"

    def test_provider_normalizes_dashed_date(self):
        """YYYY-MM-DD 입력도 정규화되어 직전 거래일로 build 됨."""
        from scripts.run_intraday_tournament import _make_dynamic_provider

        called_dates = []

        def _fake_build(trade_date, **kwargs):
            called_dates.append(trade_date)
            return ['A00001']

        with patch(
            'scripts.run_intraday_tournament._load_trading_days',
            return_value=list(self.TRADING_DAYS),
        ), patch(
            'utils.intraday_universe.build_universe_for_date',
            side_effect=_fake_build,
        ):
            provider = _make_dynamic_provider(cache_dir='cache/intraday_universe', top_n=50)
            result = provider('2025-09-02')

        assert result == ['A00001']
        assert called_dates == ['20250901'], (
            f"YYYY-MM-DD 정규화 실패 또는 직전 거래일 매핑 오류: {called_dates}"
        )


# ── Stocks-in-Play (D-1) universe 테스트 ──────────────────────────────────────
#
# spec-2026-05-22-sip-universe.md §3, §6 준수.
# build_stocks_in_play_universe는 daily_agg DataFrame을 주입받는 순수함수 —
# DB 없이 합성 데이터로 게이트/랭킹/룩어헤드 차단을 검증한다.


def _make_daily_agg(rows: list[dict]) -> pd.DataFrame:
    """일별 집계 결과와 동일한 스키마의 합성 DataFrame 생성.

    columns: stock_code, trade_date, volume, amount, close
    (stock_code, trade_date) 정렬.
    """
    df = pd.DataFrame(
        rows, columns=['stock_code', 'trade_date', 'volume', 'amount', 'close']
    )
    return df.sort_values(['stock_code', 'trade_date']).reset_index(drop=True)


def _gen_history(
    stock_code: str,
    dates: list[str],
    *,
    volume: float,
    amount: float,
    close: float,
) -> list[dict]:
    """한 종목의 균일 이력 행들을 생성 (게이트 분모 채우기용)."""
    return [
        {'stock_code': stock_code, 'trade_date': d,
         'volume': volume, 'amount': amount, 'close': close}
        for d in dates
    ]


# rvol_window=4를 쓰는 컴팩트 테스트 캘린더 (이력 요건 = window+1 = 5거래일)
_SIP_DATES = ['20260101', '20260102', '20260103', '20260104', '20260105']
_SIP_ASOF = '20260105'


class TestBuildStocksInPlayUniverse:
    """build_stocks_in_play_universe 순수함수 단위 테스트 (DB 불필요)."""

    def _fn(self):
        from utils.intraday_universe import build_stocks_in_play_universe
        return build_stocks_in_play_universe

    def _base_stock(
        self,
        code: str,
        *,
        base_volume: float = 1_000_000,
        asof_volume: float = 5_000_000,
        base_close: float = 10_000.0,
        asof_close: float = 11_000.0,
        asof_amount: float = 5e10,
    ) -> list[dict]:
        """한 종목의 5거래일 이력 생성.

        앞 4일: base_volume / base_close (RVOL 분모 + asof-1 close 제공),
        asof일: asof_volume / asof_close / asof_amount.
        기본값은 전 게이트 통과 (RVOL 5.0, 등락 10%, amount 5e10, close 11000).
        """
        prior = _SIP_DATES[:-1]  # 4일
        rows = _gen_history(
            code, prior,
            volume=base_volume, amount=5e10, close=base_close,
        )
        rows.append({
            'stock_code': code, 'trade_date': _SIP_ASOF,
            'volume': asof_volume, 'amount': asof_amount, 'close': asof_close,
        })
        return rows

    def test_rvol_gate(self):
        """RVOL < rvol_min 종목 제외."""
        fn = self._fn()
        rows = []
        # PASS: 분모 평균 1M, asof 3M → RVOL 3.0 >= 2.0
        rows += self._base_stock('PASS', base_volume=1_000_000, asof_volume=3_000_000)
        # FAIL: 분모 평균 1M, asof 1.5M → RVOL 1.5 < 2.0
        rows += self._base_stock('FAIL', base_volume=1_000_000, asof_volume=1_500_000)
        daily_agg = _make_daily_agg(rows)

        result = fn(
            _SIP_ASOF, daily_agg,
            rvol_min=2.0, abs_return_min=0.0,
            min_amount=0.0, min_price=0.0,
            rvol_window=4, top_n=30,
        )
        assert result == ['PASS'], f"RVOL 게이트 미적용: {result}"

    def test_abs_return_gate(self):
        """전일 등락(절대값) < abs_return_min 종목 제외."""
        fn = self._fn()
        rows = []
        # PASS: asof-1 close 10000 → asof close 11000 → 등락 +10%
        rows += self._base_stock('PASS', base_close=10_000.0, asof_close=11_000.0)
        # FAIL: asof-1 close 10000 → asof close 10100 → 등락 +1%
        rows += self._base_stock('FAIL', base_close=10_000.0, asof_close=10_100.0)
        daily_agg = _make_daily_agg(rows)

        result = fn(
            _SIP_ASOF, daily_agg,
            rvol_min=0.0, abs_return_min=0.03,
            min_amount=0.0, min_price=0.0,
            rvol_window=4, top_n=30,
        )
        assert result == ['PASS'], f"등락 게이트 미적용: {result}"

    def test_abs_return_gate_negative_direction(self):
        """등락은 절대값 — 하락도 임계값 이상이면 통과."""
        fn = self._fn()
        # asof-1 close 10000 → asof close 9000 → 등락 -10%, |등락|=10%
        rows = self._base_stock('DOWN', base_close=10_000.0, asof_close=9_000.0)
        daily_agg = _make_daily_agg(rows)

        result = fn(
            _SIP_ASOF, daily_agg,
            rvol_min=0.0, abs_return_min=0.03,
            min_amount=0.0, min_price=0.0,
            rvol_window=4, top_n=30,
        )
        assert result == ['DOWN'], "하락 종목도 |등락| 임계값 이상이면 통과해야 함"

    def test_amount_and_price_gate(self):
        """amount < min_amount 또는 close < min_price 종목 제외."""
        fn = self._fn()
        rows = []
        # PASS: amount 5e10, close 11000
        rows += self._base_stock('OK', asof_amount=5e10, asof_close=11_000.0)
        # FAIL_AMT: amount 1e9 < 1e10
        rows += self._base_stock('LOW_AMT', asof_amount=1e9, asof_close=11_000.0)
        # FAIL_PRC: close 2000 < 3000 (asof-1 close도 2000으로 등락 0이지만 abs_return_min=0이라 통과)
        low_prc = self._base_stock('LOW_PRC', asof_close=2_000.0)
        for r in low_prc:
            r['close'] = 2_000.0
        rows += low_prc
        daily_agg = _make_daily_agg(rows)

        result = fn(
            _SIP_ASOF, daily_agg,
            rvol_min=0.0, abs_return_min=0.0,
            min_amount=1e10, min_price=3000.0,
            rvol_window=4, top_n=30,
        )
        assert result == ['OK'], f"amount/price 게이트 미적용: {result}"

    def test_top_n_ranking_by_rvol(self):
        """통과 종목 > top_n → RVOL 내림차순 top_n 반환."""
        fn = self._fn()
        rows = []
        # 5종목, 분모 평균 동일(1M), asof volume만 다름 → RVOL 차등
        specs = [
            ('R2', 2_000_000),  # RVOL 2.0
            ('R5', 5_000_000),  # RVOL 5.0
            ('R3', 3_000_000),  # RVOL 3.0
            ('R8', 8_000_000),  # RVOL 8.0
            ('R4', 4_000_000),  # RVOL 4.0
        ]
        for code, av in specs:
            rows += self._base_stock(code, base_volume=1_000_000, asof_volume=av)
        daily_agg = _make_daily_agg(rows)

        result = fn(
            _SIP_ASOF, daily_agg,
            rvol_min=2.0, abs_return_min=0.0,
            min_amount=0.0, min_price=0.0,
            rvol_window=4, top_n=3,
        )
        assert result == ['R8', 'R5', 'R4'], (
            f"RVOL 내림차순 top_n=3 미적용: {result}"
        )

    def test_insufficient_history_excluded(self):
        """이력 < rvol_window + 1 종목 제외."""
        fn = self._fn()
        rows = []
        # FULL: 5거래일 이력 (window=4 → 요건 5) → 통과
        rows += self._base_stock('FULL')
        # SHORT: 3거래일 이력만 → 제외
        short_dates = _SIP_DATES[:2]  # 2일 prior
        rows += _gen_history(
            'SHORT', short_dates, volume=1_000_000, amount=5e10, close=10_000.0
        )
        rows.append({
            'stock_code': 'SHORT', 'trade_date': _SIP_ASOF,
            'volume': 5_000_000, 'amount': 5e10, 'close': 11_000.0,
        })
        daily_agg = _make_daily_agg(rows)

        result = fn(
            _SIP_ASOF, daily_agg,
            rvol_min=0.0, abs_return_min=0.0,
            min_amount=0.0, min_price=0.0,
            rvol_window=4, top_n=30,
        )
        assert result == ['FULL'], (
            f"이력 부족(rvol_window+1 미만) 종목이 제외되지 않음: {result}"
        )

    def test_no_lookahead_future_rows_ignored(self):
        """asof 이후 데이터를 추가해도 결과가 불변이어야 함 (룩어헤드 차단).

        함수가 daily_agg를 trade_date <= asof_date로 먼저 필터하므로
        asof 이후 행이 RVOL/등락/게이트 계산에 들어가면 안 된다.
        """
        fn = self._fn()
        base_rows = self._base_stock('STK', base_volume=1_000_000, asof_volume=3_000_000)
        daily_agg_clean = _make_daily_agg(base_rows)
        result_clean = fn(
            _SIP_ASOF, daily_agg_clean,
            rvol_min=2.0, abs_return_min=0.03,
            min_amount=1e10, min_price=3000.0,
            rvol_window=4, top_n=30,
        )

        # asof 이후 (미래) 행 추가 — 극단적 값으로 계산 오염 시도
        future_rows = list(base_rows) + [
            {'stock_code': 'STK', 'trade_date': '20260106',
             'volume': 999_999_999, 'amount': 1.0, 'close': 1.0},
            {'stock_code': 'STK', 'trade_date': '20260107',
             'volume': 0, 'amount': 0.0, 'close': 0.0},
        ]
        daily_agg_future = _make_daily_agg(future_rows)
        result_future = fn(
            _SIP_ASOF, daily_agg_future,
            rvol_min=2.0, abs_return_min=0.03,
            min_amount=1e10, min_price=3000.0,
            rvol_window=4, top_n=30,
        )

        assert result_future == result_clean, (
            f"룩어헤드 차단 실패 — asof 이후 행이 결과를 바꿈.\n"
            f"  asof 이하만: {result_clean}\n  asof 이후 포함: {result_future}"
        )

    def test_empty_input_returns_empty(self):
        """빈 daily_agg → 빈 리스트."""
        fn = self._fn()
        empty = _make_daily_agg([])
        result = fn(_SIP_ASOF, empty, rvol_window=4)
        assert result == []


# ── load_daily_aggregates 캐시 테스트 ─────────────────────────────────────────


class TestLoadDailyAggregates:
    """load_daily_aggregates parquet 캐시 동작 테스트."""

    _AGG_COLUMNS = ['stock_code', 'trade_date', 'volume', 'amount', 'close']

    def _make_agg_cursor(self, rows: list[tuple]) -> MagicMock:
        """일별 집계 SQL 결과를 반환하는 cursor mock."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_cursor.description = [(c,) for c in self._AGG_COLUMNS]
        return mock_cursor

    def test_cache_miss_then_hit(self, tmp_path):
        """첫 호출은 DB 집계 후 parquet 저장, 두 번째는 캐시 재사용 (DB 미호출)."""
        from utils.intraday_universe import load_daily_aggregates

        rows = [
            ('000001', '20260101', 1_000_000, 5e10, 10_000.0),
            ('000001', '20260102', 1_200_000, 6e10, 10_500.0),
            ('000002', '20260101', 2_000_000, 7e10, 20_000.0),
        ]
        mock_cursor = self._make_agg_cursor(rows)
        ctx = _make_mock_conn_ctx(mock_cursor)

        # 1) 캐시 miss → DB 집계 → parquet 저장
        with patch(
            'utils.intraday_universe.DatabaseConnection.get_connection',
            return_value=ctx,
        ):
            df_first = load_daily_aggregates(cache_dir=tmp_path)

        assert list(df_first.columns) == self._AGG_COLUMNS
        assert len(df_first) == 3
        cache_file = tmp_path / '_daily_agg.parquet'
        assert cache_file.exists(), "DB 집계 후 _daily_agg.parquet이 저장되어야 함"

        # 2) 캐시 hit → DB 전혀 호출 안 함
        with patch(
            'utils.intraday_universe.DatabaseConnection.get_connection'
        ) as mock_db:
            df_second = load_daily_aggregates(cache_dir=tmp_path)
            mock_db.assert_not_called()

        assert len(df_second) == 3, "캐시 hit 시 같은 행 수여야 함"
        assert list(df_second.columns) == self._AGG_COLUMNS
        pd.testing.assert_frame_equal(
            df_first.reset_index(drop=True),
            df_second.reset_index(drop=True),
        )

    def test_result_sorted_by_stock_and_date(self, tmp_path):
        """결과는 (stock_code, trade_date) 정렬."""
        from utils.intraday_universe import load_daily_aggregates

        # 일부러 뒤섞인 순서로 반환
        rows = [
            ('000002', '20260102', 2_000_000, 7e10, 20_000.0),
            ('000001', '20260102', 1_200_000, 6e10, 10_500.0),
            ('000002', '20260101', 2_100_000, 7e10, 19_000.0),
            ('000001', '20260101', 1_000_000, 5e10, 10_000.0),
        ]
        mock_cursor = self._make_agg_cursor(rows)
        ctx = _make_mock_conn_ctx(mock_cursor)

        with patch(
            'utils.intraday_universe.DatabaseConnection.get_connection',
            return_value=ctx,
        ):
            df = load_daily_aggregates(cache_dir=tmp_path)

        ordered = list(zip(df['stock_code'], df['trade_date']))
        assert ordered == [
            ('000001', '20260101'), ('000001', '20260102'),
            ('000002', '20260101'), ('000002', '20260102'),
        ], f"(stock_code, trade_date) 정렬 안 됨: {ordered}"
