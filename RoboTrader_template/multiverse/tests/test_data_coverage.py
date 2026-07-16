"""D4 — 5년 범위 데이터 품질 회귀 테스트.

일봉 SSOT(resolve_daily_source_db(), 기본 kis_template.daily_prices)를 대상으로
연속성·종목 풀·컬럼 무결성·adj_factor·갭 경계를 검증한다.

주의:
  - date 컬럼은 TEXT 타입. 정규식 필터 필수 (malformed 102건 존재).
  - OHLC 위반 0.77% 는 실 데이터 한계로 허용 범위 내 처리.
  - 2024-02-29 ~ 2024-03-13 (한국 공휴일 클러스터, ~9영업일)은 알려진 특이점.
  - 2025-10-02 ~ 2025-10-10 (추석 연휴, 8칼력일)도 알려진 특이점.
  - DB 연결: resolve_daily_source_db() (기본 kis_template), host 127.0.0.1:5433

2026-07-16(연구 소스 통일): 자체 env(TIMESCALE_QUANT_DB)로 DB 를 지정하던 것을
공용 resolver 로 수렴했다 — 소스 스위치는 KIS_DATA_SOURCE 하나만 남는다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import date

_TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
if str(_TEMPLATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_ROOT))

from config.constants import resolve_daily_source_db  # noqa: E402

# ------------------------------------------------------------------ #
# 연결 헬퍼 — pit_reader._conn_daily() 패턴 재사용
# ------------------------------------------------------------------ #
def _daily_db_defaults() -> dict:
    """가격 소스 접속 정보. DB명은 호출 시점 resolver 를 따른다."""
    return dict(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", "5433")),
        user=os.getenv("TIMESCALE_QUANT_USER", os.getenv("TIMESCALE_USER", "robotrader")),
        password=os.getenv("TIMESCALE_QUANT_PASSWORD", os.getenv("TIMESCALE_PASSWORD", "1234")),
        database=resolve_daily_source_db(),
    )


# valid date 필터 — malformed TEXT 제거
_VALID_DATE = "date ~ '^\\d{4}-\\d{2}-\\d{2}$'"


@contextmanager
def _conn_quant():
    conn = psycopg2.connect(**_daily_db_defaults())
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="module")
def quant_conn():
    """모듈 스코프 DB 연결 — 전체 커버리지 테스트에서 재사용."""
    try:
        conn = psycopg2.connect(**_daily_db_defaults())
    except Exception as exc:
        pytest.skip(f"일봉 소스 DB 연결 실패 (환경 없음): {exc}")
    yield conn
    conn.close()


# ================================================================== #
# (a) 5년 연속성
# ================================================================== #

class TestFiveYearContinuity:
    """5년 연속성 — MIN/MAX 날짜 및 월별 거래일 수 검증."""

    def test_min_date_is_20210104(self, quant_conn):
        """MIN(date) = 2021-01-04 — 일봉 SSOT(kis_template) 시작일 확인.

        2026-07-16 소스 통일로 기대치 갱신: 2021-01-12 → 2021-01-04.
        레거시 robotrader_quant 는 2021-01-12 부터였고 kis_template 은 8일 더
        이른 2021-01-04 부터 보유한다(상위집합). 즉 이 변화는 **이력이 늘어난 것**
        이지 결손이 아니다. (KIS_DATA_SOURCE=legacy 롤백 시엔 2021-01-12 가 되므로
        이 단언은 기본 소스 기준이다.)
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"SELECT MIN(date) FROM daily_prices WHERE {_VALID_DATE};"
            )
            result = cur.fetchone()[0]
        assert result == "2021-01-04", f"MIN(date) 기대 2021-01-04, 실제: {result}"

    def test_max_date_is_20260430(self, quant_conn):
        """MAX(date) = 2026-04-30 — ETL 마지막일 확인."""
        with quant_conn.cursor() as cur:
            cur.execute(
                f"SELECT MAX(date) FROM daily_prices WHERE {_VALID_DATE};"
            )
            result = cur.fetchone()[0]
        assert result == "2026-04-30", f"MAX(date) 기대 2026-04-30, 실제: {result}"

    def test_monthly_trading_days_in_normal_range(self, quant_conn):
        """월별 거래일 수 ≥ 13 (한국 최소 영업일 — 1월/설 연휴 월 허용).

        실제 최소: 2021-01 = 14일, 2021-01은 신년+부분수집으로 14일.
        13일로 여유 있게 설정.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT TO_CHAR(date::date, 'YYYY-MM') AS month,
                       COUNT(DISTINCT date) AS trading_days
                FROM daily_prices
                WHERE {_VALID_DATE}
                GROUP BY 1
                ORDER BY 1
                """
            )
            rows = cur.fetchall()

        assert rows, "월별 거래일 쿼리 결과가 비어 있음"
        low_months = [(m, d) for m, d in rows if d < 13]
        assert not low_months, (
            f"거래일 < 13인 월 발견 (알려진 특이점 외 데이터 이슈 의심): {low_months}"
        )

    def test_total_row_count_above_2m(self, quant_conn):
        """전체 행 수 ≥ 2,000,000 — 대규모 ETL 완료 확인."""
        with quant_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM daily_prices;")
            total = cur.fetchone()[0]
        assert total >= 2_000_000, f"총 행 수 {total} < 2,000,000"


# ================================================================== #
# (b) 종목 풀 안정성
# ================================================================== #

class TestSymbolPoolStability:
    """월별 종목 수 및 결측 streak 검증."""

    def test_monthly_distinct_stocks_above_1500(self, quant_conn):
        """매월 distinct 종목 수 ≥ 1,500 — KOSPI200 포함 충분한 종목 풀.

        실제: 2021-01 = 1,739종목이 최솟값.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT TO_CHAR(date::date, 'YYYY-MM') AS month,
                       COUNT(DISTINCT stock_code) AS stocks
                FROM daily_prices
                WHERE {_VALID_DATE}
                GROUP BY 1
                ORDER BY 1
                """
            )
            rows = cur.fetchall()

        assert rows, "월별 종목 수 쿼리 결과 없음"
        low_months = [(m, s) for m, s in rows if s < 1500]
        assert not low_months, (
            f"종목 수 < 1,500인 월 발견: {low_months}"
        )

    def test_no_single_stock_gap_over_10_business_days(self, quant_conn):
        """개별 종목의 연속 거래일 최대 결측 ≤ 10 영업일.

        알려진 특이점:
          - 2024-02-29 → 2024-03-13: 한국 공휴일 클러스터 (~9 영업일)
          - 2025-10-02 → 2025-10-10: 추석 연휴 (8 칼력일 ≈ 6 영업일)
        10 영업일 임계값은 이 특이점을 허용하면서 데이터 이슈를 포착.
        """
        with quant_conn.cursor() as cur:
            # calendar gap > 14일인 (stock_code, gap 구간)만 추출
            # 14 cal days = ~10 business days (주말 4일 제외)
            cur.execute(
                f"""
                WITH ordered AS (
                    SELECT stock_code,
                           date::date AS d,
                           LEAD(date::date) OVER (
                               PARTITION BY stock_code ORDER BY date
                           ) AS next_d
                    FROM daily_prices
                    WHERE {_VALID_DATE}
                )
                SELECT stock_code, d, next_d, (next_d - d) AS cal_gap
                FROM ordered
                WHERE next_d IS NOT NULL
                  AND (next_d - d) > 14
                ORDER BY cal_gap DESC
                LIMIT 20
                """
            )
            rows = cur.fetchall()

        # 알려진 222810 예외 (상장폐지 후 재상장 등 특수 케이스) 제외
        known_exceptions = {"222810"}
        violations = [
            (code, str(d), str(nd), gap)
            for code, d, nd, gap in rows
            if code not in known_exceptions
        ]
        assert not violations, (
            f"calendar gap > 14일 (≈10 영업일) 초과 종목 발견 "
            f"(알려진 예외 제외): {violations[:5]}"
        )


# ================================================================== #
# (c) 컬럼 무결성
# ================================================================== #

class TestColumnIntegrity:
    """NULL 비율 및 OHLC 일관성 검증."""

    def test_returns_1d_null_rate_below_1pct(self, quant_conn):
        """returns_1d NULL 비율 < 1% (전 기간).

        실제: 0.096% (각 종목 첫 행만 NULL — 정상).
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                """
                SELECT ROUND(
                    100.0 * COUNT(*) FILTER (WHERE returns_1d IS NULL) / COUNT(*),
                    4
                ) AS null_pct
                FROM daily_prices
                """
            )
            null_pct = float(cur.fetchone()[0])
        assert null_pct < 1.0, (
            f"returns_1d NULL 비율 {null_pct}% >= 1% — 비정상적으로 높음"
        )

    def test_ohlc_null_count_is_zero(self, quant_conn):
        """open/high/low/close NULL 건수 = 0."""
        with quant_conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE open  IS NULL) AS null_open,
                    COUNT(*) FILTER (WHERE high  IS NULL) AS null_high,
                    COUNT(*) FILTER (WHERE low   IS NULL) AS null_low,
                    COUNT(*) FILTER (WHERE close IS NULL) AS null_close
                FROM daily_prices
                """
            )
            row = cur.fetchone()
        null_open, null_high, null_low, null_close = row
        assert null_open == 0, f"open NULL {null_open}건"
        assert null_high == 0, f"high NULL {null_high}건"
        assert null_low == 0, f"low NULL {null_low}건"
        assert null_close == 0, f"close NULL {null_close}건"

    def test_market_cap_null_rate_below_5pct(self, quant_conn):
        """market_cap NULL 비율 < 5%.

        실제: 1.1% — 초기 수집 누락분으로 허용 범위 내.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                """
                SELECT ROUND(
                    100.0 * COUNT(*) FILTER (WHERE market_cap IS NULL) / COUNT(*),
                    4
                ) AS null_pct
                FROM daily_prices
                """
            )
            null_pct = float(cur.fetchone()[0])
        assert null_pct < 5.0, (
            f"market_cap NULL 비율 {null_pct}% >= 5%"
        )

    def test_ohlc_violation_rate_below_2pct(self, quant_conn):
        """OHLC 위반(high < close 또는 low > open 등) 비율 < 2%.

        실제: 0.77% — 실 데이터 수집 한계(틱 반올림 등)로 발생.
        0 요구는 과도하므로 2% 허용.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                """
                SELECT ROUND(
                    100.0 * COUNT(*) FILTER (
                        WHERE high < close
                           OR high < open
                           OR low  > close
                           OR low  > open
                    ) / COUNT(*),
                    4
                ) AS viol_pct
                FROM daily_prices
                """
            )
            viol_pct = float(cur.fetchone()[0])
        assert viol_pct < 2.0, (
            f"OHLC 위반 비율 {viol_pct}% >= 2% — 데이터 품질 저하 의심"
        )

    def test_malformed_date_count_below_threshold(self, quant_conn):
        """malformed date (TEXT, 정규식 불일치) 건수 < 200.

        현재 알려진 malformed: 2건('2026--0-3-', '2026--0-4-') × 51종목 = 102건.
        200을 임계값으로 신규 malformed 유입 감지.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM daily_prices "
                f"WHERE date !~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$';"
            )
            bad_count = cur.fetchone()[0]
        assert bad_count < 200, (
            f"malformed date 행 수 {bad_count} >= 200 — 신규 malformed 유입 의심"
        )


# ================================================================== #
# (d) adj_factor 일관성
# ================================================================== #

class TestAdjFactor:
    """adj_factor 컬럼 존재 및 기본값 1.0 검증 (D2 corp_events 런타임 보정 방식)."""

    def test_adj_factor_column_exists(self, quant_conn):
        """adj_factor 컬럼이 daily_prices에 존재해야 한다."""
        with quant_conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name   = 'daily_prices'
                  AND column_name  = 'adj_factor'
                LIMIT 1
                """
            )
            row = cur.fetchone()
        assert row is not None, "adj_factor 컬럼이 daily_prices에 없음"

    def test_adj_factor_default_is_1(self, quant_conn):
        """adj_factor 컬럼 기본값 1.0 — 미적용 행은 1.0 이어야 한다."""
        with quant_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM daily_prices
                WHERE adj_factor IS NOT NULL AND adj_factor != 1.0
                """
            )
            non_default = cur.fetchone()[0]
        # D2 ETL이 수정주가를 daily_prices에 직접 쓰지 않는 구조이므로
        # 전 행이 1.0(기본값)이어야 한다.
        assert non_default == 0, (
            f"adj_factor != 1.0 행 {non_default}건 — "
            "D2 ETL이 daily_prices를 직접 수정했는지 확인 필요"
        )

    def test_null_adj_factor_does_not_corrupt_price_path(self, quant_conn):
        """adj_factor NULL 은 무해해야 한다 — 가격 경로를 오염시키지 않는다.

        가드 목적 재정의 (2026-07-16). 기존 단언 ``NULL 건수 == 0`` 은
        "adj_factor 가 DEFAULT 1.0 으로 전부 채워져 **가격에 곱해도 안전하다**"는
        전제의 ETL 무결성 가드였다. 그 전제가 두 가지로 무효가 됐다:

        ① 곱셈 금지 규약 — adj_factor 는 **가격 산술에 쓰이지 않는다**.
           곱하면 분할일에 가짜 절벽이 생긴다(실측: 035720 2021-04-14
           close=112,000 × adj_factor=5 → 560,000 → 분할일 -78.5%, 가격제한
           ±30% 초과 = 물리적 불가). pit_reader·_load_daily_adj 모두 raw 사용.
           → NULL 이어도 곱할 일이 없으므로 NaN 전파 경로 자체가 없다.
        ② SSOT 가 kis_template 로 이동 — NULL 44,923행이 **정상 존재**한다
           (KOSPI 지수행 1,357개 전부 포함). robotrader_quant 는 같은 자리에 1.0.

        건수를 실측치(44,923)에 핀으로 박지 않는 이유: 수집이 진행될수록 계속
        늘어난다(실측 35,011 → 44,923). 핀을 박으면 다음 수집일마다 거짓 실패한다.

        따라서 건수가 아니라 **NULL 이 무해함**을 지킨다. 이 가드는 다음이 깨지면
        실패한다(= vacuous 아님):
          - NULL adj_factor 행의 가격(close)이 결측/비정상이 되면 → 가격 경로 오염
          - adj_factor 에 0/음수 쓰레기가 들어오면 → 어떤 산술에도 안전하지 않음
        실측(2026-07-16) 두 소스 모두 0건: kis_template·robotrader_quant 공통.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE adj_factor IS NULL AND (close IS NULL OR close <= 0)
                    ) AS null_adj_broken_close,
                    COUNT(*) FILTER (
                        WHERE adj_factor IS NOT NULL AND adj_factor <= 0
                    ) AS nonpositive_adj
                FROM daily_prices;
                """
            )
            null_adj_broken_close, nonpositive_adj = cur.fetchone()

        assert null_adj_broken_close == 0, (
            f"adj_factor NULL 이면서 close 가 결측/비정상인 행 {null_adj_broken_close}건 — "
            "NULL 이 가격 경로를 오염시키고 있다"
        )
        assert nonpositive_adj == 0, (
            f"adj_factor <= 0 인 행 {nonpositive_adj}건 — 역조정 메타 손상"
        )


# ================================================================== #
# (e) 갭 경계 특이점
# ================================================================== #

class TestGapBoundaryDates:
    """알려진 갭 경계 날짜의 종목 수 정상 확인."""

    def test_stock_count_on_20230425(self, quant_conn):
        """2023-04-25 종목 수 ≥ 1,800 (갭 전 날짜 — 데이터 정상 수집 확인)."""
        with quant_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT stock_code) FROM daily_prices "
                "WHERE date = '2023-04-25';"
            )
            count = cur.fetchone()[0]
        assert count >= 1800, (
            f"2023-04-25 종목 수 {count} < 1,800 — 갭 전 수집 이상"
        )

    def test_stock_count_on_20240229(self, quant_conn):
        """2024-02-29 종목 수 ≥ 1,800 (공휴일 클러스터 갭 전 날짜)."""
        with quant_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT stock_code) FROM daily_prices "
                "WHERE date = '2024-02-29';"
            )
            count = cur.fetchone()[0]
        assert count >= 1800, (
            f"2024-02-29 종목 수 {count} < 1,800"
        )
