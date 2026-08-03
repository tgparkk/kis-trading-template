"""D4 — 5년 범위 데이터 품질 회귀 테스트.

일봉 SSOT(resolve_daily_source_db(), 기본 kis_template.daily_prices)를 대상으로
연속성·종목 풀·컬럼 무결성·adj_factor·갭 경계를 검증한다.

주의:
  - date 컬럼은 TEXT 타입. 정규식 필터 필수 (malformed 102건 존재).
  - OHLC 위반 0.77% 는 실 데이터 한계로 허용 범위 내 처리.
  - 🔴 daily_prices 에는 **종목이 아닌 지수 행**이 섞여 있다(KOSPI·KOSDAQ·KS11·KQ11).
    「종목 수」를 세는 단언은 전부 SQL_STOCK_ONLY 로 걸러야 한다. → lib/universe_filter.py
  - 2025-10-02 ~ 2025-10-10 은 **진짜 공휴일 연휴**다(아래 사실 확인 참조).
  - DB 연결: resolve_daily_source_db() (기본 kis_template), host 127.0.0.1:5433

2026-07-16(연구 소스 통일): 자체 env(TIMESCALE_QUANT_DB)로 DB 를 지정하던 것을
공용 resolver 로 수렴했다 — 소스 스위치는 KIS_DATA_SOURCE 하나만 남는다.

================================================================================
2026-08-03 정정 — 「알려진 특이점」주석 2건이 거짓이었다
================================================================================
🔴 삭제한 거짓 주석:
    "2024-02-29 ~ 2024-03-13 (한국 공휴일 클러스터, ~9영업일)은 알려진 특이점."

   **공휴일이 아니다.** 이 구간의 휴장은 2024-03-01(금, 삼일절) **하루뿐**이고
   2024-03-02·03 은 주말이다. 나머지 2024-03-04·05·06·07·08·11·12 **7일은 전부
   정상 거래일**이며, 그 증거로 7일 모두 daily_prices 에 KOSPI·KS11·KQ11 행이
   거래량 3.8~4.6억으로 존재한다(2024-03-01 은 행 자체가 0건).

   진짜 원인은 **수집 이음새**다:
     · 과거 백필(strategy_analysis 유래)이 2024-02-29 에 끝난다
       (신형우선주 10종 `00088K`·`37550L` 등의 마지막 행이 전부 이 날짜다)
     · KIS 본수집이 max_count=500 절단 때문에 2024-03-13 에야 시작한다
       (2024-03-13 종목 2,331 vs 2024-03-12 종목 186)
     · 그 사이 7거래일은 파일럿 168~186종목만 보유
   → 관련 코드: scripts/etl_backfill_daily_prices.py (백필 측),
     collectors/ 일봉 수집 경로(max_count 절단 측).

🔴 같은 성격의 두 번째 거짓 주석은 test_min_date_is_20210104 안에 있었다
   ("kis_template 은 8일 더 이른 2021-01-04 부터 보유한다 … 이력이 늘어난 것").
   그 8일(2021-01-04~01-11, 6거래일)은 **KOSPI 지수 1행씩뿐이고 종목은 0** 이다.
   종목 기준 MIN(date)는 레거시와 같은 2021-01-12 — 늘어난 이력은 없다.

✅ 사실 확인을 통과한 주석: "2025-10-02 ~ 2025-10-10 추석 연휴".
   같은 방식으로 실측했고 **참이다** — 10-03 개천절 / 10-04·05 주말 /
   10-06·07·08 추석 연휴 / 10-09 한글날로 결손 거래일이 0이고,
   구간 양 끝(10-02, 10-10)은 종목 2,475로 정상이다.

🔑 재사용 규칙: 「알려진 특이점」이라고 적힌 주석은 **날짜별 실측으로 반증하기
   전까지 근거가 아니다.** 여기서는 그 주석이 회귀 테스트의 임계값을 정당화하는
   데 쓰였고, 그래서 결함이 「정상」으로 고정돼 있었다.

--------------------------------------------------------------------------------
⚠️ 이 파일에는 **이 정정 작업과 무관한 선행 실패 3건**이 남아 있다 (미수정)
--------------------------------------------------------------------------------
아래는 2026-08-03 정정 이전부터 실패하던 것이며, 원인·수정 범위가 달라 손대지
않았다. 실패를 이번 변경 탓으로 오귀속하지 말 것.

  1) test_max_date_is_20260430 — 핀이 낡았다. 실제 MAX(date) = 2026-08-03.
     수집이 계속되므로 날짜 상수를 핀으로 박는 설계 자체가 매일 깨진다.
  2) test_monthly_trading_days_in_normal_range (임계 13)
  3) test_monthly_distinct_stocks_above_1500  (임계 1,500)
     -> 둘 다 **진행 중인 당월**을 완결된 달처럼 센다. 실측 2026-08 은 거래일 1일
        ·종목 37(지수 포함해도 38)이라 매월 1~12일경 구조적으로 실패한다.
        지수 필터 유무와 무관하다(실측으로 확인).

이 3건의 올바른 수정 방향은 임계값 완화가 아니라 **비교 대상 정의**다
(당월 제외, MAX(date)는 상수 대신 "최근 영업일 이내" 같은 상대 조건).
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
from lib.universe_filter import SQL_STOCK_ONLY  # noqa: E402

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

# ------------------------------------------------------------------ #
# 알려진 수집 이음새 등록부 — **공휴일이 아니다**
# ------------------------------------------------------------------ #
# 🔑 이 등록부의 목적은 결함을 「정상」으로 고정하는 게 아니라, 결함을
#    **날짜와 종목 수로 좁게 특정**해 두고 복구되면 카나리가 실패하게 만드는 것이다.
#    (아래 TestKnownDefectCanaries 참조 — 복구 시 카나리가 먼저 깨진다.)
_KNOWN_COLLECTION_SEAMS = {
    date(2024, 2, 29): (
        "과거 백필(strategy_analysis 유래) 종료일. 2024-03-04~03-12 7거래일은 "
        "파일럿 168~186종목만 존재하고 KIS 본수집은 2024-03-13 에 시작한다. "
        "실측(2026-08-03) 이 날짜에서 90종목이 2025~2026년으로 건너뛴다."
    ),
    date(2026, 5, 13): (
        "🔴 2026-08-03 신규 발견 · 원인 미규명 · 미해결. 구형우선주 성격의 26종목"
        "(000105·001045·003545 등)이 2026-05-13 -> 2026-06-15 로 33일 건너뛴다."
    ),
}

# 한 날짜에 이만큼 이상의 종목이 동시에 끊기면 개별 종목 사유(거래정지·재상장)가
# 아니라 **수집 이음새**다. 실측 분리도가 크다: 이음새 90종목·26종목 vs 개별 1종목.
_SYSTEMIC_SEAM_MIN_CODES = 10


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
        """MIN(date) = 2021-01-04 — 테이블 전체(지수 포함) 시작일.

        🔴 2026-08-03 주석 정정. 이전 주석은 이렇게 적혀 있었다:
            "레거시 robotrader_quant 는 2021-01-12 부터였고 kis_template 은 8일 더
             이른 2021-01-04 부터 보유한다(상위집합). 즉 이 변화는 **이력이 늘어난
             것**이지 결손이 아니다."
        **거짓이다.** 그 8일(2021-01-04~01-11, 6거래일)에 있는 행은 KOSPI 지수
        1행씩 총 6행뿐이고 **종목은 0건**이다(실측 2026-08-03).
        종목 기준 MIN(date)는 레거시와 같은 2021-01-12 — 늘어난 종목 이력은 없다.
        아래 test_min_stock_date_is_20210112 가 그 사실을 별도로 못 박는다.

        이 단언 자체(테이블 전체 MIN = 2021-01-04)는 참이므로 유지한다.
        (KIS_DATA_SOURCE=legacy 롤백 시엔 2021-01-12 가 되므로 기본 소스 기준이다.)
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"SELECT MIN(date) FROM daily_prices WHERE {_VALID_DATE};"
            )
            result = cur.fetchone()[0]
        assert result == "2021-01-04", f"MIN(date) 기대 2021-01-04, 실제: {result}"

    def test_min_stock_date_is_20210112(self, quant_conn):
        """종목(지수 제외) 기준 MIN(date) = 2021-01-12.

        위 테스트의 2021-01-04 와 이 테스트의 2021-01-12 가 **함께 있어야**
        "8일이 늘어난 게 아니라 지수만 8일 더 있다"는 사실이 표현된다.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"SELECT MIN(date) FROM daily_prices "
                f"WHERE {_VALID_DATE} AND {SQL_STOCK_ONLY};"
            )
            result = cur.fetchone()[0]
        assert result == "2021-01-12", (
            f"종목 MIN(date) 기대 2021-01-12, 실제: {result} — "
            "2021-01 초 종목 데이터가 백필됐다면 카나리 "
            "test_202101_index_only_prefix_still_present 도 함께 갱신할 것"
        )

    def test_max_date_is_20260430(self, quant_conn):
        """MAX(date) = 2026-04-30 — ETL 마지막일 확인."""
        with quant_conn.cursor() as cur:
            cur.execute(
                f"SELECT MAX(date) FROM daily_prices WHERE {_VALID_DATE};"
            )
            result = cur.fetchone()[0]
        assert result == "2026-04-30", f"MAX(date) 기대 2026-04-30, 실제: {result}"

    def test_monthly_trading_days_in_normal_range(self, quant_conn):
        """월별 **종목 거래일** 수 ≥ 13 (한국 최소 영업일 — 1월/설 연휴 월 허용).

        🔴 SQL_STOCK_ONLY 추가(2026-08-03). 이전에는 지수 행만 있는 날도 거래일로
        세어 2021-01 이 20일로 나왔다 — 그런데 같은 함수의 주석은 "실제 최소:
        2021-01 = 14일"이라 적혀 있었다. 즉 **주석의 숫자와 쿼리가 세는 대상이
        달랐다.** 지수를 빼면 실측 14일로 주석과 일치한다.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT TO_CHAR(date::date, 'YYYY-MM') AS month,
                       COUNT(DISTINCT date) AS trading_days
                FROM daily_prices
                WHERE {_VALID_DATE} AND {SQL_STOCK_ONLY}
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
        """매월 distinct 종목 수 ≥ 1,500 — 충분한 종목 풀.

        🔴 SQL_STOCK_ONLY 추가(2026-08-03) — 지수 행이 종목으로 세어지고 있었다.
        실측 2021-01: 필터 전 1,740 / 필터 후 **1,739**(주석의 수치와 일치).
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT TO_CHAR(date::date, 'YYYY-MM') AS month,
                       COUNT(DISTINCT stock_code) AS stocks
                FROM daily_prices
                WHERE {_VALID_DATE} AND {SQL_STOCK_ONLY}
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

    def test_no_unregistered_collection_seam(self, quant_conn):
        """등록되지 않은 **수집 이음새**가 없어야 한다.

        🔴 2026-08-03 전면 재작성. 옛 이름은
        ``test_no_single_stock_gap_over_10_business_days`` 였고 다음이 문제였다:

        ① **주석이 거짓이었다** — "2024-02-29 → 2024-03-13: 한국 공휴일 클러스터
           (~9 영업일)". 공휴일은 2024-03-01 하루뿐이고 나머지 7일은 정상 거래일
           이다(모듈 docstring 에 실측 근거). 즉 수집 결손을 「공휴일」로 적어
           놓고 그 서술로 임계값을 정당화하고 있었다.
        ② **임계값이 결함을 통과시켰다** — 그 이음새는 13 칼력일이라 `> 14` 조건에
           애초에 걸리지 않는다. 테스트는 결함을 「본 적이 없다」.
        ③ **단언 대상이 원리적으로 틀렸다** — 개별 종목의 결측은 거래정지·재상장
           으로 얼마든지 길어질 수 있다(그래서 222810 을 화이트리스트에 넣어야
           했다). 개별 종목 결측 길이에 상한을 두는 건 불변식이 아니다.
        ④ **지수 행이 종목으로 세어졌다** — KS11·KQ11 의 2026-06-22→07-08 결손이
           종목 결손으로 잡혔다.

        그래서 단언 대상을 **개별 종목 → 이음새(같은 날짜에 다수 종목이 동시에
        끊기는 사건)** 로 바꿨다. 이쪽이 진짜 불변식이다:
          - 같은 날짜에 _SYSTEMIC_SEAM_MIN_CODES(=10)종목 이상이 동시에 끊긴다
            = 개별 사유일 수 없다 = 수집 파이프라인 사건
          - 새 이음새가 생기면 **즉시** 실패한다(종목 신원과 무관하게)
          - 알려진 이음새는 _KNOWN_COLLECTION_SEAMS 에 날짜로 등록하고,
            복구되면 TestKnownDefectCanaries 가 실패해 갱신을 강제한다

        임계값 10 은 임의값이 아니라 실측 분리도에서 나왔다: 이음새는 90종목·26종목
        인데 개별 사건은 전부 1종목이다(9배 이상 간격).

        개별 종목 결손(< 10종목)은 여기서 단언하지 않고 실패 메시지에 참고로만
        싣는다. 실측(2026-08-03) 4건이며 전부 장기 거래정지로 보인다:
        105840(2026-01-02→06-15) · 023590(2025-12-30→05-04) ·
        417310(2025-12-15→02-23) · 011300(2026-04-17→05-04).
        """
        with quant_conn.cursor() as cur:
            # calendar gap > 14일 = ~10 영업일(주말 4일 제외). 지수 행 제외.
            cur.execute(
                f"""
                WITH ordered AS (
                    SELECT stock_code,
                           date::date AS d,
                           LEAD(date::date) OVER (
                               PARTITION BY stock_code ORDER BY date
                           ) AS next_d
                    FROM daily_prices
                    WHERE {_VALID_DATE} AND {SQL_STOCK_ONLY}
                )
                SELECT d, COUNT(DISTINCT stock_code) AS n_codes,
                       MIN(next_d) AS first_resume, MAX(next_d) AS last_resume
                FROM ordered
                WHERE next_d IS NOT NULL AND (next_d - d) > 14
                GROUP BY d
                ORDER BY n_codes DESC
                """
            )
            rows = cur.fetchall()

        systemic = [r for r in rows if r[1] >= _SYSTEMIC_SEAM_MIN_CODES]
        isolated = [r for r in rows if r[1] < _SYSTEMIC_SEAM_MIN_CODES]

        unregistered = [
            (str(d), n, str(first), str(last))
            for d, n, first, last in systemic
            if d not in _KNOWN_COLLECTION_SEAMS
        ]
        assert not unregistered, (
            f"등록되지 않은 수집 이음새 발견 — 같은 날짜에 "
            f"{_SYSTEMIC_SEAM_MIN_CODES}종목 이상이 동시에 끊겼다: {unregistered}\n"
            f"공휴일로 넘겨짚지 말고 그 날짜의 지수 행(KOSPI/KS11/KQ11) 존재 여부로 "
            f"실제 거래일인지 먼저 확인할 것. 수집 결함이면 _KNOWN_COLLECTION_SEAMS "
            f"에 원인과 함께 등록하고 카나리를 추가할 것.\n"
            f"(참고: 개별 종목 결손 {len(isolated)}건 — "
            f"{[(str(d), n) for d, n, _, _ in isolated[:5]]})"
        )


# ================================================================== #
# (b-2) 알려진 결함 카나리 — **복구되면 실패한다**
# ================================================================== #

class TestKnownDefectCanaries:
    """미복구 데이터 결함을 숫자로 고정한다.

    🔑 목적이 거꾸로다. 보통의 회귀 테스트는 「정상」을 지키지만, 이 클래스는
    **「아직 고장나 있음」을 지킨다.** 데이터가 복구되면 이 테스트들이 실패하고,
    그러면 누군가 반드시 이 파일과 _KNOWN_COLLECTION_SEAMS 를 갱신하게 된다.

    ⚠️ 실패했다고 롤백하지 말 것. 실패 = 복구 성공일 가능성이 높다.
       먼저 데이터를 확인하고, 복구가 맞으면 해당 카나리를 **삭제**하라.
    ⚠️ 임계값을 실측치에 딱 맞춰 핀으로 박지 않았다 — 일상 수집으로는 절대
       움직이지 않는 과거 구간이지만, 여유를 둬서 거짓 실패를 막는다.
    """

    def test_20240304_collection_seam_still_broken(self, quant_conn):
        """카나리 — 2024-03-04~03-12 수집 결손이 아직 복구되지 않았다.

        복구되면(= 이 7거래일에 정상 종목 수가 채워지면) 실패한다.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT date, COUNT(DISTINCT stock_code)
                FROM daily_prices
                WHERE date BETWEEN '2024-03-04' AND '2024-03-12'
                  AND {SQL_STOCK_ONLY}
                GROUP BY date ORDER BY date
                """
            )
            seam = cur.fetchall()

        assert len(seam) == 7, (
            f"2024-03-04~03-12 거래일 수 기대 7, 실제 {len(seam)} — "
            "구간 정의가 바뀌었다. 카나리를 갱신할 것"
        )
        worst = max(n for _, n in seam)
        assert worst < 1000, (
            f"2024-03-04~03-12 최대 종목 수 {worst} >= 1000 — "
            "🎉 수집 결손이 복구된 것으로 보인다. 다음을 함께 갱신할 것: "
            "① 이 카나리 삭제 ② _KNOWN_COLLECTION_SEAMS[2024-02-29] 삭제 "
            "③ 모듈 docstring 의 정정 기록 갱신 "
            f"(실측 당시 168~186종목, 현재 {[(str(d), n) for d, n in seam]})"
        )

    def test_20240301_is_the_only_holiday_in_the_seam(self, quant_conn):
        """카나리의 근거 — 결손 구간이 공휴일이 **아님**을 데이터로 고정한다.

        2024-03-01(삼일절)만 행이 0이고, 나머지 7일은 지수 행이 존재한다
        (= KRX 가 열렸다). 이 단언이 깨지면 「공휴일이었다」는 옛 서술이
        되살아날 수 있으므로 반드시 함께 재검토할 것.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE date = '2024-03-01';"
            )
            holiday_rows = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT date)
                FROM daily_prices
                WHERE date BETWEEN '2024-03-04' AND '2024-03-12'
                  AND NOT ({SQL_STOCK_ONLY})
                """
            )
            index_days = cur.fetchone()[0]

        assert holiday_rows == 0, (
            f"2024-03-01(삼일절)에 {holiday_rows}행 존재 — 휴장일 데이터 유입 의심"
        )
        assert index_days == 7, (
            f"2024-03-04~03-12 중 지수 행이 있는 날 {index_days} != 7 — "
            "이 7일이 실제 거래일이라는 증거가 사라졌다. "
            "결손 원인 서술(수집 이음새 vs 공휴일)을 재확인할 것"
        )

    def test_202101_index_only_prefix_still_present(self, quant_conn):
        """카나리 — 2021-01-04~01-11 은 KOSPI 지수뿐이고 종목이 0이다.

        종목이 백필되면 실패한다. 그때 test_min_date_is_20210104 /
        test_min_stock_date_is_20210112 의 주석도 함께 갱신해야 한다.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FILTER (WHERE {SQL_STOCK_ONLY})       AS stock_rows,
                       COUNT(*) FILTER (WHERE stock_code = 'KOSPI')   AS kospi_rows,
                       COUNT(*)                                       AS all_rows
                FROM daily_prices
                WHERE date BETWEEN '2021-01-04' AND '2021-01-11'
                """
            )
            stock_rows, kospi_rows, all_rows = cur.fetchone()

        assert stock_rows == 0, (
            f"2021-01-04~01-11 종목 행 {stock_rows}건 — "
            "🎉 초기 구간이 백필된 것으로 보인다. 이 카나리와 "
            "test_min_stock_date_is_20210112(기대 2021-01-12)를 함께 갱신할 것"
        )
        assert kospi_rows == all_rows == 6, (
            f"2021-01-04~01-11 행 구성이 바뀌었다 "
            f"(KOSPI {kospi_rows} / 전체 {all_rows}, 기대 6/6)"
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
    """알려진 갭 경계 날짜의 종목 수 정상 확인.

    🔴 두 쿼리 모두 SQL_STOCK_ONLY 추가(2026-08-03) — 지수 행이 종목 수에
    포함돼 있었다(실측 각 날짜당 지수 3종 + 우선주 10종 = 13행).
    """

    def test_stock_count_on_20230425(self, quant_conn):
        """2023-04-25 종목 수 ≥ 1,800 (갭 전 날짜 — 데이터 정상 수집 확인).

        실측(2026-08-03, 지수 제외): 1,896.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(DISTINCT stock_code) FROM daily_prices "
                f"WHERE date = '2023-04-25' AND {SQL_STOCK_ONLY};"
            )
            count = cur.fetchone()[0]
        assert count >= 1800, (
            f"2023-04-25 종목 수 {count} < 1,800 — 갭 전 수집 이상"
        )

    def test_stock_count_on_20240229(self, quant_conn):
        """2024-02-29 종목 수 ≥ 1,800 — **수집 이음새** 직전 날짜.

        🔴 이전 주석은 "공휴일 클러스터 갭 전 날짜"라고 적혀 있었으나 거짓이다
        (모듈 docstring 정정 참조). 이 날은 과거 백필의 마지막 날이다.
        실측(2026-08-03, 지수 제외): 1,969 → 다음 수록일 2024-03-04 는 168.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(DISTINCT stock_code) FROM daily_prices "
                f"WHERE date = '2024-02-29' AND {SQL_STOCK_ONLY};"
            )
            count = cur.fetchone()[0]
        assert count >= 1800, (
            f"2024-02-29 종목 수 {count} < 1,800"
        )
