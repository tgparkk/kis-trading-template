"""D4 — 5년 범위 데이터 품질 회귀 테스트.

일봉 SSOT(resolve_daily_source_db(), 기본 kis_template.daily_prices)를 대상으로
연속성·종목 풀·컬럼 무결성·adj_factor·갭 경계를 검증한다.

주의:
  - date 컬럼은 TEXT 타입. 정규식 필터 필수 (malformed 102건 존재).
  - OHLC 위반 0.77% 는 실 데이터 한계로 허용 범위 내 처리.
  - 🔴 daily_prices 에는 **종목이 아닌 지수 행**이 섞여 있다(KOSPI·KOSDAQ·KS11·KQ11).
    「종목 수」를 세는 단언은 전부 SQL_STOCK_ONLY 로 걸러야 한다. → lib/universe_filter.py
  - 2025-10-02 ~ 2025-10-10 은 **진짜 공휴일 연휴**다(아래 사실 확인 참조).
  - DB 연결: resolve_daily_source_db() (**항상** kis_template), host 127.0.0.1:5433

2026-07-16(연구 소스 통일): 자체 env(TIMESCALE_QUANT_DB)로 DB 를 지정하던 것을
공용 resolver 로 수렴했다.
2026-08-17: 남아 있던 공용 스위치(KIS_DATA_SOURCE)까지 폐지됐다 — 레거시 두 DB 는
2026-07-10 동결이었고 `robotrader` 는 삭제된다. 이제 소스 스위치는 **없다**.

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
2026-08-03 (2차) — 선행 실패 4건 정리. **임계값은 하나도 완화하지 않았다**
--------------------------------------------------------------------------------
위 정정 이전부터 실패하던 4건을 정리했다. 넷 다 원인이 같은 계열이다:
**「그때 그 소스에서 관측된 값」을 불변식인 것처럼 단언에 박아 뒀다.**
소스가 kis_template(매일 수집)으로 바뀌거나 시간이 흐르면 자동으로 거짓이 된다.
그래서 임계값을 낮추는 게 아니라 **비교 대상의 정의**를 바꿨다.

  1) test_max_date_is_20260430 -> test_max_date_is_recent
     핀 '2026-04-30' 은 작성 시점(2026-05-07) 레거시 ETL 의 마지막 날짜였다.
     불변식은 「최대일이 특정 날짜인가」가 아니라 **「수집이 살아 있는가」** 다.
     -> 절대 날짜 핀을 _MAX_STALENESS_DAYS 상대 조건으로 교체.
     -> 옛 핀이 우연히 막아주던 「미래 날짜 행」은 test_no_future_dated_rows 로 분리.
  2) test_monthly_trading_days_in_normal_range   (임계 13, 유지)
  3) test_monthly_distinct_stocks_above_1500     (임계 1,500, 유지)
     -> 둘 다 **진행 중인 당월**을 완결된 달처럼 셌다(실측 2026-08 = 거래일 1일).
        임계값은 그대로 두고 _completed_months() 로 **비교 대상에서 당월만 제외**했다.
        경계 규약과 두 임계값의 출처는 각각 그 함수/테스트 docstring 에 적었다.
  4) test_adj_factor_default_is_1 -> test_adj_factor_is_monotone_applied_metadata
     "전 행이 1.0 이어야 한다"는 **전제가 거짓**이었다. adj_factor 는 「이 행의 close
     에 이미 적용된 조정 배수」를 기록하는 메타데이터이고, 실측 66,964행(92종목)이
     2~50 의 분할비를 정상적으로 들고 있다. 레거시 robotrader_quant 에도 65,662행이
     있으므로 **소스 전환과 무관하게 처음부터 실패해 온 단언**이다.
     증거(035720 카카오 5:1, 2021-04-15): 분할 전 close 112,000(=원시 558,000/5,
     adj_factor=5) -> 분할 후 120,500(adj_factor=1) 로 **이미 연속**이다.
     -> 참인 구조 불변식(1 미만 불가 · 시간에 대해 되돌아가지 않음)으로 교체.

🔴 그 과정에 **신규 데이터 결함**이 드러났다 (고치지 않음, 카나리로 기록):
   adj_factor 전환 97건 중 **33건에서 인접 거래일 close 가 ±30%(KRX 가격제한폭)를
   넘게 튄다.**
   -> TestKnownDefectCanaries.test_split_adjustment_cliffs_still_present

--------------------------------------------------------------------------------
2026-08-03 (3차) — 위 33건의 **원인 규정을 재검정**했다. 숫자는 유지, 서술을 교체
--------------------------------------------------------------------------------
1차 서술은 33건을 「조정 미적용 5 / 역방향 오적용 28」로 규정했다. 그 뒤 *"인접쌍의
한쪽이 volume=0 인 캐리포워드 행이므로 절벽은 정지 아티팩트다"* 라는 반론이 제기됐다.
**둘 다 그대로는 쓸 수 없다.** 실측으로 셋을 분리했다:

  ① 「한쪽 volume=0」은 **판별력이 0이다.** 절벽 33건만이 아니라 **전환 97건 전부**가
     한쪽 이상 volume=0 이다(좌측 0 = 95건, 양쪽 0 = 2건, **양쪽 거래 = 0건**).
     기업행위 전후로 KRX 가 매매를 정지시키므로 당연하다. 즉 이 지표로는 절벽군과
     정상군을 **구분할 수 없다** — 「volume=0 이니까 아티팩트」는 성립하지 않는다.
  ② 정지 행을 **건너뛰고** 다시 재도 절벽은 그대로다. 전환 직전의 마지막 **실거래**
     종가(volume>0)와 직후의 첫 실거래 종가로 앵커를 옮기면, 캐리포워드 값이 곧
     마지막 실거래 종가와 **같은 값**이라 33건 중 31건이 크기까지 동일하게 남는다.
     (예: 011930 은 2026-04-23 에 74,153,623주가 실제로 거래된 종가 3,995 →
      정지 15거래일 → 2026-05-15 첫 실거래 종가 39,950. 정확히 10.0000배 = adj_factor.)
  ③ 그 31건의 점프는 **기록된 adj_factor 와 일치한다.** 실거래 앵커 비 r 에 대해
     {r, r×f, r/f} 중 1 에 가장 가까운 것을 고르면 95건(판정 가능분) 중
     **64건은 r 자신**(조정 정합) · **31건은 r×f 또는 r/f**(조정이 안 걸림).
     두 군은 겹치지 않는다 — 정합군의 |ln r| 최댓값 0.2646(+30.3%) < 결함군의
     |ln r| 최솟값 0.4309(+53.9%).

⇒ **결론: 원인 규정은 유지된다.** 33건 중 **31건은 실제 조정 미적용**이고(분할이면
  아래로, 액면병합이면 위로 튄다), **2건만이 판정 불가한 정지 스텁**이다:
    · 260970 (2021-01-29) — 전환 이전에 **실거래 행이 하나도 없다**(OHLC=0·volume=0
      스텁이 close=379,700 을 캐리포워드). 반론이 든 바로 그 예시이고, **이 1건에
      한해 반론이 맞다.** 1차 서술이 이걸 「조정 미적용 5건」에 넣은 것은 오류다.
    · 380540 (2026-05-21) — 전환 **이후**에 실거래 행이 없다(계속 정지 중).

🔑 재사용 규칙: **「그 행들이 정지 구간이다」는 그 자체로 아티팩트의 증거가 아니다.**
   정지는 기업행위마다 항상 일어나므로 결함군·정상군 **양쪽에 다 있다**. 판정하려면
   정지를 건너뛴 **실거래 앵커**로 다시 재고, 남은 점프가 adj_factor 와 일치하는지까지
   봐야 한다. 여기서는 판별력 0인 지표로 원인 규정이 뒤집힐 뻔했다.
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

# ------------------------------------------------------------------ #
# 최신성 임계 — 「MAX(date)가 어느 날짜인가」가 아니라 「수집이 살아 있는가」
# ------------------------------------------------------------------ #
# 🔑 근거(임의값 아님). 허용해야 할 최대 지연 = (최장 휴장) + (EOD 수집 타이밍 여유):
#   ① 최장 휴장 — 실측(2021-01~2026-08, 종목 기준 연속 거래일 간격)의 최댓값은
#      **8칼력일**(2025-10-02 -> 2025-10-10: 개천절·주말·추석·한글날). 그 다음이 7일 2건.
#      ⚠️ 데이터 범위 밖이지만 KRX 는 더 길어진 적이 있다 — 2017 추석 임시공휴일
#      (2017-09-29 -> 2017-10-10 = **11칼력일**). 재발 가능하므로 8이 아니라 11을 쓴다.
#   ② EOD 수집은 장 마감 후에 돈다 — 거래일 **오전**에 이 테스트를 돌리면 MAX(date)는
#      아직 전 거래일이다. 여기에 EOD 가 하루 실패하고 다음 날 복구되는 경우까지 감안해
#      +3일(주말 길이)을 얹는다.
#   => 11 + 3 = 14.
# ⚠️ 이 값을 줄여서 "더 엄격하게" 만들지 말 것 — 긴 연휴 다음 날 오전마다 거짓 실패한다.
#    수집 중단을 더 빨리 잡고 싶으면 이 테스트가 아니라 모니터링의 몫이다.
_MAX_STALENESS_DAYS = 14

# KRX 일일 가격제한폭 ±30% (2015-06-15 이후 전 종목). 인접 거래일 종가가 이 폭을
# 넘게 움직였다면 그건 시세가 아니라 **시계열 연속성이 깨진 것**이다.
# 🔑 실측이 이 경계에 정확히 떨어진다 — adj_factor 전환 97건 중 정상군의 최댓값이
#    **30.00%**(상한가 정확히)이고 결함군의 최솟값이 **35.01%** 다. 임의 임계가 아니다.
_KRX_PRICE_LIMIT_PCT = 30

# 미해결 「분할 조정 절벽」 허용 상한 (카나리 전용, 실제 품질 목표는 0).
#
# 🔴 2026-08-03 근거 재작성. 옛 근거는 *"전환 ≈18건/년 · 현재 오류율 34%(33/97)
#    이므로 월 ~0.5건씩 는다 → 상한 40 이면 약 14개월 버틴다"* 였다. **전제가 거짓이다.**
#    33건은 정상 발생률이 아니라 **한 번의 버스트**다 — 실측 분포:
#      전환/년: 2021=12 · 2022=11 · 2023=10 · 2024=18 · 2025=10 · 2026(~08-03)=36
#      결함(실거래 앵커 기준 31건)의 시점: 2023-07 **1건** · 2026-04 9건 · 2026-05 21건
#    즉 **30/31 이 2026-04-24 ~ 2026-05-22 의 4주 안에 몰려 있고**, 그 창 밖의 기저
#    발생률은 **5.5년에 1건**(≈0.2건/년)이다. 「월 0.5건씩 증가」를 지지하는 관측이 없다.
#
# 🔑 그래서 이 상한은 **유도된 값이 아니다.** 정직하게 적는다:
#      상한 40 = 관측치 33 + 여유 7. 근거는 발생률이 아니라 다음 한 가지뿐이다 —
#      **같은 규모의 버스트(31건)가 한 번 더 나면 64 가 되어 반드시 실패한다.**
#      반대로 기저 발생률(0.2건/년)로는 수십 년간 트립하지 않는다.
#    여유 7 의 크기 자체에는 근거가 없다. 버스트 감지가 목적이므로 정밀도가 필요 없다.
# ⚠️ 실패했다고 이 값을 올리지 말 것. 올린다는 건 결함이 악화되는 걸 승인하는 것이다.
_KNOWN_SPLIT_CLIFF_MAX = 40

# 「판정 불가한 정지 스텁」 허용 상한 — 위와 **성격이 다르므로 따로 센다.**
# 전환 경계의 한쪽에 volume>0 행이 하나도 없어 조정 정합을 판정할 수 없는 건수다
# (실측 2026-08-03: 2건 — 260970 · 380540). 조정 미적용과 달리 **volume>0 필터를
# 걸면 사라지므로**, 같은 상한으로 묶으면 서로의 증감을 가린다.
# 🔑 상한 10 역시 유도값이 아니다 — 실측 2 에서 개별 종목 사유(장기 정지·상폐 직전)로
#    몇 건 늘 수 있는 폭만 준 것이고, 자릿수가 바뀌면(=수집기가 캐리포워드를 양산)
#    잡힌다는 것 이상은 주장하지 않는다.
_KNOWN_HALT_STUB_MAX = 10


def _completed_months(rows):
    """월별 집계 결과에서 **진행 중인 월**을 잘라낸다.

    🔑 경계 규약: **완결 월 = MAX(date)가 속한 월보다 이른 월.**

      · MAX(date)의 월은 정의상 진행 중이다. 오늘이 8/3 이면 2026-08 은 거래일 1일뿐이고,
        설령 월말이더라도 그날 EOD 수집이 아직 안 돌았을 수 있다.
      · 그보다 이른 월은 「그 월이 끝난 뒤에도 수집이 계속됐다」는 증거(더 늦은 날짜의 행)를
        데이터 자체가 들고 있다. 그래서 완결로 본다.
      · **CURRENT_DATE 가 아니라 MAX(date) 기준인 이유**: 수집이 통째로 멈추면 그 이후의
        달은 행이 0이라 GROUP BY 결과에서 **아예 사라진다**. CURRENT_DATE 기준으로 자르면
        "빈 달은 검사되지 않음"이 되어 조용히 통과한다. 멈춤 감지는
        test_max_date_is_recent 의 책임으로 분리한다.

    ⚠️ 이 규약이 걸러주지 **못하는** 것: 월말 EOD 가 한 번 실패해 직전 월이 하루 모자란
       경우. 거래일 임계(13)로도 안 잡힌다(1일 결손은 임계 안쪽). 그건 이 테스트가 아니라
       최신성 테스트와 운영 모니터링의 몫이다.
    ⚠️ 이 규약은 **보수적 방향으로만 틀린다** — 월초 첫 거래일 전(MAX 가 아직 전월 말일)에는
       직전 월을 한 달 늦게 검사하기 시작한다. 거짓 실패를 만들지는 않는다.
    """
    if not rows:
        return []
    in_progress = max(month for month, _ in rows)
    return [(month, value) for month, value in rows if month < in_progress]


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
        (레거시 롤백 시엔 2021-01-12 였는데, 그 롤백 경로는 2026-08-17 폐지됐다.)
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

    def test_max_date_is_recent(self, quant_conn):
        """종목 일봉이 최신이어야 한다 — MAX(date)가 오늘로부터 14일 이내.

        🔴 2026-08-03 재설계. 옛 이름은 ``test_max_date_is_20260430`` 이고 단언은
        ``MAX(date) == '2026-04-30'`` 이었다. 그 상수는 작성 시점(2026-05-07)의
        레거시 robotrader_quant ETL 마지막 날짜다. SSOT 가 **매일 수집되는**
        kis_template 으로 옮겨간 뒤로 이 핀은 날짜가 하루 지날 때마다 깨진다.

        **불변식: 일봉 수집이 살아 있어서 데이터가 최신이다.**
        「최대일이 특정 날짜인가」가 아니다. 그래서 절대 날짜 핀을 상대 조건으로 바꿨다.
        임계 _MAX_STALENESS_DAYS(=14)의 유도 근거는 그 상수 정의부에 적어 뒀다.

        지수(KOSPI/KS11/KQ11)가 아니라 **종목** 기준으로 잰다. 지수 행은 다른 수집기가
        쓰고 실제로 더 늦게까지 밀린다(실측 2026-08-03: 지수 MAX 2026-07-31 vs
        종목 MAX 2026-08-03) — 지수를 포함하면 종목 수집이 멈춰도 가려질 수 있다.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(date), CURRENT_DATE - MAX(date)::date
                FROM daily_prices
                WHERE {_VALID_DATE} AND {SQL_STOCK_ONLY};
                """
            )
            max_date, staleness_days = cur.fetchone()

        assert max_date is not None, "종목 일봉이 한 행도 없음"
        assert staleness_days <= _MAX_STALENESS_DAYS, (
            f"종목 MAX(date) = {max_date} 로 {staleness_days}일 지연 "
            f"(허용 {_MAX_STALENESS_DAYS}일) — 일봉 수집이 멈췄는지 확인할 것. "
            "긴 연휴가 원인이라면 _MAX_STALENESS_DAYS 유도 근거(최장 휴장 11일)를 "
            "먼저 실측으로 갱신하고, 그냥 늘리지 말 것"
        )

    def test_no_future_dated_rows(self, quant_conn):
        """미래 날짜 행이 0건이어야 한다.

        옛 ``MAX(date) == '2026-04-30'`` 핀이 **우연히** 막아 주던 것이라 상대 조건으로
        바꾸면서 별도 단언으로 분리했다. 미래 날짜 행은 PIT 백테스트에 look-ahead 를
        직접 주입한다(as-of 필터가 통과시켜 버린다).

        ⚠️ ``date`` 는 TEXT 라 malformed 값이 섞여 있다. 캐스팅하면 그 행에서 터지므로
           ISO 포맷끼리의 **텍스트 비교**로 판정한다.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*), MAX(date)
                FROM daily_prices
                WHERE {_VALID_DATE} AND date > TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD');
                """
            )
            future_rows, worst = cur.fetchone()

        assert future_rows == 0, (
            f"미래 날짜 행 {future_rows}건 (최대 {worst}) — "
            "PIT 백테스트에 look-ahead 가 새어든다"
        )

    def test_monthly_trading_days_in_normal_range(self, quant_conn):
        """**완결된** 월의 종목 거래일 수 ≥ 13.

        **불변식: 완결된 달은 한국 증시 최소 영업일 수를 채운다.**
        「모든 달」이 아니라 「완결된 달」이다 — 진행 중인 달은 적은 게 정상이다.

        🔴 2026-08-03 수정 — **진행 중인 당월을 완결된 달처럼 세고 있었다.**
        실측 2026-08 은 거래일 1일이라 매월 1~12일경 구조적으로 실패한다.
        임계값 13 은 그대로 두고 _completed_months() 로 **비교 대상**만 좁혔다
        (경계 규약 = 그 함수 docstring).

        🔑 임계 13 의 출처 — 최초 커밋(cfde3ff, 2026-05-07) 주석 *"실제 최소:
           2021-01 = 14일"* 에서 나온 **관측 최솟값 + 여유 1일**이다. 그런데 그
           2021-01 은 **부분 수집 월**이다(데이터가 2021-01-12 부터 시작).
           실측(2026-08-03) **완결 월의 진짜 최솟값은 17일**(2026-02, 설 연휴).
           즉 13 은 "정상 하한"이 아니라 "첫 부분 월까지 통과시키는 하한"이다.
           2021-01 이 백필되면 17~18로 조여도 된다.
        ⚠️ 반대로 이 값을 **더 낮추지 말 것** — 낮출 이유가 생겼다면 그건 데이터가
           나빠졌다는 신호다.

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
        completed = _completed_months(rows)
        assert completed, (
            f"완결된 월이 하나도 없음 — 데이터가 한 달치뿐인가? (수집 월: {rows})"
        )
        low_months = [(m, d) for m, d in completed if d < 13]
        assert not low_months, (
            f"거래일 < 13인 **완결** 월 발견 (알려진 특이점 외 데이터 이슈 의심): "
            f"{low_months} — 임계값을 낮추지 말고 그 달의 수집 로그를 볼 것"
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
        """**완결된** 월의 distinct 종목 수 ≥ 1,500 — 종목 풀 붕괴 감지.

        **불변식: 완결된 달에는 백테스트가 성립할 최소한의 종목 풀이 존재한다.**

        🔴 2026-08-03 수정 — **진행 중인 당월을 완결된 달처럼 셌다.**
        실측 2026-08(장중)은 80종목이라 매월 초 구조적으로 실패한다. 임계값 1,500 은
        그대로 두고 _completed_months() 로 **비교 대상**만 좁혔다.

        🔑 임계 1,500 의 출처 — 최초 커밋(cfde3ff, 2026-05-07) 주석 *"실제: 2021-01 =
           1,739종목이 최솟값"* 에서 나온 **관측 최솟값 − 약 14% 여유**다.
           외부 기준(KRX 상장종목 수 등)에서 유도한 값이 **아니다.**

        🔴 그래서 이 임계값이 **못 하는 일**을 명시해 둔다.
           1,500 은 2021~2023 구간(월별 1,739~1,957)을 **전부 통과시킨다.** 그런데 그
           구간은 2024-03 이후(2,341~2,578)보다 ~600종목 적고, 이건 성장 곡선이 아니라
           **알려진 결손**이다:
             · 원인 규명 완료 — `scripts/etl_backfill_daily_prices.py` 가 자체 유니버스
               목록 없이 원천(strategy_analysis.daily_candles, 2,113종목)을 그대로 복사.
               누락 468종목 중 원천에 있던 건 2건뿐이다.
             · 2024-02(1,969) -> 2024-03(2,341) 의 한 달 +372 는 유기적 증가가 아니라
               KIS 본수집이 2024-03-13 에 시작한 **이음새**다.
           즉 **이 테스트는 그 결손을 탐지하지 못한다.** 탐지는 TestKnownDefectCanaries
           의 몫이다. 이 테스트가 통과하는 것을 "2021년 유니버스가 정상"의 근거로
           **쓰지 말 것.**
        ⚠️ 유니버스 복구가 끝나면 이 임계는 2,300대로 조여야 의미가 생긴다.

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
        completed = _completed_months(rows)
        assert completed, (
            f"완결된 월이 하나도 없음 — 데이터가 한 달치뿐인가? (수집 월 수: {len(rows)})"
        )
        low_months = [(m, s) for m, s in completed if s < 1500]
        assert not low_months, (
            f"종목 수 < 1,500인 **완결** 월 발견: {low_months} — "
            "임계값을 낮추지 말고 그 달의 수집 범위를 볼 것"
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

    def test_split_adjustment_cliffs_still_present(self, quant_conn):
        """카나리 — adj_factor 전환 지점의 「가짜 절벽」 33건이 아직 고쳐지지 않았다.

        🔴 **2026-08-03 신규 발견 · 미해결.** test_adj_factor_default_is_1 의 거짓 전제를
        걷어내다 드러났다. 옛 단언(``adj_factor != 1 인 행 == 0``)은 이 결함을 **볼 수
        조차 없었다** — 컬럼에 값이 있는지만 셌고 close 와 맞는지는 안 봤다.

        무엇이 관측됐나: adj_factor 가 바뀌는 인접 거래일에서 close 가 ±30%(KRX
        가격제한폭)를 넘게 튄다. 실측 전환 **97건 중 33건**. 인접쌍 기준 분리도가
        제도 경계에 떨어진다 — 정상군 최댓값 **29.9966%**, 결함군 최솟값 **35.01%**.

        ------------------------------------------------------------------
        원인 규정 (2026-08-03 3차 재검정 — 모듈 docstring 에 실측 근거)
        ------------------------------------------------------------------
        ⚠️ **「한쪽 volume=0 이니 정지 캐리포워드 아티팩트」로 넘기지 말 것.** 그 지표는
           판별력이 0이다 — 절벽 33건이 아니라 **전환 97건 전부**가 한쪽 이상 volume=0
           이다(양쪽 다 거래된 전환 = **0건**). 기업행위 전후에 KRX 가 매매를 정지시키니
           당연하고, 따라서 결함군과 정상군을 나누지 못한다.

        정지 행을 **건너뛴 실거래 앵커**(전환 직전 마지막 volume>0 종가 → 직후 첫
        volume>0 종가)로 다시 재면 결론이 나온다. 판정 가능 95건 중:
          · **64건** — 앵커 비 r 이 그대로 1 근처 = 조정이 제대로 걸렸다.
          · **31건** — r 이 아니라 r×f 또는 r/f 가 1 근처 = **조정이 안 걸렸다.**
            분할이면 아래로(001130 x11 -90.86%), 액면병합이면 위로(011930 x10 +900.00%)
            튄다. 액면병합도 back-adjusted 시계열로는 과거 행을 **곱해야** 하므로 틀렸다.
          두 군은 겹치지 않는다 — 정합군 |ln r| 최댓값 0.2646 < 결함군 최솟값 0.4309.

        나머지 2건은 **판정 불가한 정지 스텁**이다(한쪽에 실거래 행이 아예 없다):
          · 260970(2021-01-29) — 전환 이전 실거래 행 0. OHLC=0·volume=0 스텁이
            close=379,700 을 캐리포워드했을 뿐이다. **이 1건은 진짜 아티팩트**이고,
            1차 서술이 이걸 「조정 미적용」에 넣은 것은 오류였다.
          · 380540(2026-05-21) — 전환 이후 실거래 행 0(계속 정지 중).

        🟡 **추측(미확증)**: 결함 31건 중 **30건이 2026-04-24 ~ 2026-05-22 4주에** 몰려
           있다(나머지 1건은 2023-07). 뒷받침되는 숫자 둘 — ① 그 두 달의 전환 자체가
           34건으로 연 10~18건 기저의 몇 배다 ② 종목 전체에서 volume=0 이 하루라도
           있는 종목 수가 2026-04 250 · 05 229 로 2026-01~03 의 90~104 대비 ~2.4배다.
           **다만 정지 자체는 원인 지표가 못 된다** — 정합군도 정지 3~38일(평균 11.3)을
           끼고 있어 결함군(9~19일, 평균 15.7)과 겹친다. 「수집/적재 사건」은 여전히
           가설이며 수집 로그로 확인되지 않았다.

        ------------------------------------------------------------------
        영향 — **「정지 구간이니 무해하다」가 아니다**
        ------------------------------------------------------------------
        행은 실재하므로, volume 을 안 거르고 **종가 대 종가**로 수익률을 재는 코드는
        그 -91% ~ +1,200% 를 그대로 먹는다. 성격이 바뀌었을 뿐 영향은 남는다:
          · 31건은 실거래 앵커로도 남으므로 volume 필터로 **제거되지 않는다.**
          · 2건은 volume>0 필터를 걸면 사라진다.
        (유니버스 복구 트랙의 차단 조건 *"adj_prc 정합이 분할 종목으로 미검증 —
         어긋나면 분할일 가짜 절벽"* 은 **이미 실현돼 있다**. 31건이 그 실현분이다.)

        ------------------------------------------------------------------
        단언 3축 — 성격이 다르므로 따로 센다
        ------------------------------------------------------------------
          A) `unadjusted` (실측 31) — 실거래 앵커로도 남는 **진짜 조정 미적용**.
             밴드로 지킨다. 0 이 되면 복구, 상한을 넘으면 버스트 재발.
          B) `halt_stub` (실측 2) — 판정 불가한 정지 스텁. 아티팩트 규모 추적용.
          C) **엄격 게이트**: A + B 가 절벽 33건을 **전부** 설명해야 한다.
             남는 게 생기면 = 위 두 가지로 설명되지 않는 **제3의 실패 모드**다.
             ⚠️ 여기가 깨지면 상한을 만지지 말고 그 건을 먼저 분류할 것.
             (「양쪽 다 거래된 전환에서의 절벽」을 엄격 게이트로 쓰지 않은 이유:
              분모가 0/97 이라 **구조적으로 vacuous** 하다. 절대 실패하지 않는
              단언은 게이트가 아니다.)
        """
        # 상관 서브쿼리 안에서는 컬럼에 별칭이 붙으므로 술어도 별칭을 맞춰 준다.
        valid_p = _VALID_DATE.replace("date ~", "p.date ~")
        valid_n = _VALID_DATE.replace("date ~", "n.date ~")
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                WITH seq AS (
                    SELECT stock_code,
                           date::date AS d,
                           close::numeric AS c,
                           adj_factor,
                           LEAD(date::date) OVER w AS next_d,
                           LEAD(close::numeric) OVER w AS next_c,
                           LEAD(adj_factor) OVER w AS next_adj
                    FROM daily_prices
                    WHERE {_VALID_DATE} AND {SQL_STOCK_ONLY} AND close > 0
                    WINDOW w AS (PARTITION BY stock_code ORDER BY date)
                ),
                boundary AS (
                    SELECT stock_code, d, next_d,
                           adj_factor::numeric AS f,
                           ABS(next_c / c - 1) * 100 AS abs_move_pct
                    FROM seq
                    WHERE adj_factor IS NOT NULL
                      AND next_adj IS NOT NULL
                      AND next_adj <> adj_factor
                      AND next_c > 0
                ),
                -- 정지(캐리포워드) 행을 건너뛴 **실거래 앵커**
                anchored AS (
                    SELECT b.*,
                           (SELECT p.close::numeric FROM daily_prices p
                             WHERE p.stock_code = b.stock_code AND {valid_p}
                               AND p.date::date <= b.d
                               AND p.volume > 0 AND p.close > 0
                             ORDER BY p.date DESC LIMIT 1) AS prev_c,
                           (SELECT n.close::numeric FROM daily_prices n
                             WHERE n.stock_code = b.stock_code AND {valid_n}
                               AND n.date::date >= b.next_d
                               AND n.volume > 0 AND n.close > 0
                             ORDER BY n.date ASC LIMIT 1) AS next_c2
                    FROM boundary b
                ),
                scored AS (
                    SELECT abs_move_pct, f,
                           CASE WHEN prev_c IS NULL OR next_c2 IS NULL OR prev_c <= 0
                                THEN NULL ELSE next_c2 / prev_c END AS r
                    FROM anchored
                )
                SELECT
                    COUNT(*)                                                  AS transitions,
                    COUNT(*) FILTER (WHERE abs_move_pct > {_KRX_PRICE_LIMIT_PCT})
                                                                              AS cliffs,
                    -- A) 실거래 앵커로도 남고, 점프가 adj_factor 로 설명된다
                    COUNT(*) FILTER (
                        WHERE abs_move_pct > {_KRX_PRICE_LIMIT_PCT}
                          AND r IS NOT NULL AND r > 0 AND f > 0
                          AND LEAST(ABS(LN(r * f)), ABS(LN(r / f))) < ABS(LN(r))
                    )                                                         AS unadjusted,
                    -- B) 한쪽에 실거래 행이 아예 없다 = 판정 불가한 정지 스텁
                    COUNT(*) FILTER (
                        WHERE abs_move_pct > {_KRX_PRICE_LIMIT_PCT} AND r IS NULL
                    )                                                         AS halt_stub
                FROM scored;
                """
            )
            transitions, cliffs, unadjusted, halt_stub = cur.fetchone()

        assert transitions > 0, (
            "adj_factor 전환이 0건 — 카나리가 vacuous 하다 (실측 2026-08-03: 97건)"
        )

        # C) 엄격 게이트 — 두 축이 절벽을 전부 설명해야 한다.
        unclassified = cliffs - unadjusted - halt_stub
        assert unclassified == 0, (
            f"어느 축으로도 분류되지 않은 절벽 {unclassified}건 "
            f"(절벽 {cliffs} = 조정 미적용 {unadjusted} + 정지 스텁 {halt_stub} 이어야 함) — "
            "알려진 두 실패 모드(조정 미적용 / 판정 불가 정지 스텁) 중 어느 쪽도 아닌 "
            "**제3의 실패 모드**다. 상한을 만지지 말고 그 건을 먼저 분류할 것. "
            "장기 정지를 낀 정상 시세 변동일 수도 있다(그 경우 실거래 앵커 간격을 함께 볼 것)"
        )

        # A) 진짜 조정 미적용 — 실거래 앵커로도 남는다
        assert unadjusted > 0, (
            f"조정 미적용 절벽 {unadjusted}건 — 🎉 복구된 것으로 보인다(실측 당시 31건). "
            "다음을 함께 갱신할 것: ① 이 카나리를 삭제하고 `unadjusted == 0` 인 "
            "실제 품질 게이트로 승격 ② 모듈 docstring 의 3차 재검정 기록 갱신"
        )
        assert cliffs <= _KNOWN_SPLIT_CLIFF_MAX, (
            f"adj_factor 전환 절벽이 {cliffs}건으로 늘었다 "
            f"(실측 33 = 조정 미적용 31 + 정지 스텁 2 / 상한 {_KNOWN_SPLIT_CLIFF_MAX}, "
            f"전환 총 {transitions}건, 현재 조정 미적용 {unadjusted} · 정지 스텁 {halt_stub}) — "
            "2026-04~05 규모의 버스트가 재발했는지 수집 로그를 볼 것. "
            "상한을 올려서 통과시키지 말 것"
        )

        # B) 정지 스텁 — 규모만 추적한다(원인이 다르므로 A 와 같이 세지 않는다)
        assert halt_stub <= _KNOWN_HALT_STUB_MAX, (
            f"판정 불가한 정지 스텁이 {halt_stub}건으로 늘었다 "
            f"(실측 2 / 상한 {_KNOWN_HALT_STUB_MAX}) — 실거래 행이 한 번도 없는 종목에 "
            "캐리포워드 행만 쌓이고 있다는 뜻이다. volume>0 필터로 걸러지긴 하지만, "
            "종가 대 종가로 재는 코드에는 그대로 새어든다"
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

    def test_adj_factor_is_monotone_applied_metadata(self, quant_conn):
        """adj_factor 는 「이미 적용된 조정 배수」 표식 — 1 미만이 될 수 없고 되돌아가지 않는다.

        🔴 2026-08-03 전면 재작성. 옛 이름은 ``test_adj_factor_default_is_1`` 이고
        단언은 ``adj_factor != 1.0 인 행 == 0`` + 주석 *"D2 ETL이 수정주가를
        daily_prices에 직접 쓰지 않는 구조이므로 전 행이 1.0(기본값)이어야 한다"* 였다.

        **그 전제가 거짓이다.** 실측(2026-08-03) 66,964행·92종목이 2·2.5·5·6.25·10·
        11·25·50 의 **분할비**를 정상적으로 들고 있다. 레거시 robotrader_quant 에도
        65,662행이 있으므로 SSOT 전환과 무관하게 **처음부터 실패해 온 단언**이다.

        의미 확정 증거 — 035720(카카오) 5:1 분할, 효력 2021-04-15:
            2021-04-14  close=112,000  adj_factor=5   <- 원시 558,000 을 이미 5로 나눈 값
            2021-04-15  close=120,500  adj_factor=1
        즉 close 는 **이미 조정된 연속 시세**이고 adj_factor 는 "이 행에 몇으로 나눈
        조정이 이미 적용됐다"는 **기록**이다. 그래서 곱하면 안 된다(곱하면 560,000 이
        되어 분할일 -78.5% 가짜 절벽 = 가격제한 ±30% 초과 = 물리적 불가).
        같은 사실을 test_null_adj_factor_does_not_corrupt_price_path 가 NULL 쪽에서
        이미 기록해 뒀다 — 2026-07-16 에 그 형제만 고치고 이쪽은 남아 있었다.

        **그래서 지킬 불변식을 「전부 1.0」에서 「메타데이터로서 앞뒤가 맞는가」로 바꾼다:**
          ① adj_factor >= 1 — 조정 배수는 1 미만일 수 없다 (실측 위반 0건)
          ② 한 종목 안에서 시간에 대해 **비증가** — 과거에 일어난 분할이 나중 행에서
             더 커질 수는 없다. 최신 행일수록 1 에 가까워진다 (실측 위반 0건)
        vacuous 아님: 실측 전환 97건이 이 단언을 실제로 통과한다.

        🔴 이 테스트가 검사하지 **않는** 것 — close 가 그 전환 지점에서 실제로 연속인가.
           실측 97건 중 **33건이 불연속**이며(가격제한 초과), 이는 미해결 데이터 결함이라
           TestKnownDefectCanaries.test_split_adjustment_cliffs_still_present 에
           카나리로 분리해 뒀다. 여기서 조용히 통과시킨 게 아니다.
        """
        with quant_conn.cursor() as cur:
            cur.execute(
                f"""
                WITH seq AS (
                    SELECT stock_code, adj_factor,
                           LEAD(adj_factor) OVER (
                               PARTITION BY stock_code ORDER BY date
                           ) AS next_adj
                    FROM daily_prices
                    WHERE {_VALID_DATE} AND {SQL_STOCK_ONLY}
                )
                SELECT
                    COUNT(*) FILTER (WHERE adj_factor IS NOT NULL
                                       AND adj_factor < 1)              AS below_one,
                    COUNT(*) FILTER (WHERE adj_factor IS NOT NULL
                                       AND next_adj IS NOT NULL
                                       AND next_adj > adj_factor)       AS went_back_up,
                    COUNT(*) FILTER (WHERE adj_factor IS NOT NULL
                                       AND next_adj IS NOT NULL
                                       AND next_adj <> adj_factor)      AS transitions
                FROM seq;
                """
            )
            below_one, went_back_up, transitions = cur.fetchone()

        assert below_one == 0, (
            f"adj_factor < 1 인 행 {below_one}건 — 조정 배수가 1 미만일 수 없다. "
            "역조정 메타가 손상됐거나 곱셈/나눗셈 방향이 뒤집혔다"
        )
        assert went_back_up == 0, (
            f"adj_factor 가 시간이 지나며 되돌아 커지는 전환 {went_back_up}건 — "
            "이미 적용된 조정이 나중 행에서 더 커질 수는 없다. 수집기가 같은 종목의 "
            "과거/현재 행에 서로 다른 기준을 쓰고 있는지 확인할 것"
        )
        assert transitions > 0, (
            "adj_factor 전환이 0건 — 위 두 단언이 vacuous 하다. 컬럼이 통째로 "
            "NULL/1.0 으로 덮였는지 확인할 것 (실측 2026-08-03: 97건)"
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
