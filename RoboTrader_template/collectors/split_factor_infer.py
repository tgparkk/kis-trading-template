# collectors/split_factor_infer.py
"""corp_events split 이벤트의 split_factor 추론 — 가격 불연속 기반.

scripts/10pct_strategy/p0_apply_adj_factor.py 의 검증된 price-gap 추론 로직을
운영 경로로 미러링하되, pykrx 가 아니라 kis_template.daily_prices 를 읽는다.

DART rcept_dt 는 '공시일'이라 실제 권리락(ex-date)은 수 주 뒤다. 따라서 공시일부터
+90일 구간의 일봉을 앞에서부터 스캔해 '첫 clean 갭'을 찾고, 그 갭이 발생한 날짜를
meta.effective_date 에 기록한다. event_date(PK, DART 공시일)는 절대 변경하지 않는다
(2026-07-06 code review 하드닝) — PK를 이동시키면 (a) 같은 슬롯이 재수집될 때 새
행이 다시 들어와 이중스탬프 위험이 생기고, (b) 기존 pykrx 백필 105건(effective_date
없이 event_date=ex-date로 이미 적재됨)과 PK 충돌 여지가 생긴다.
daily_adj.load_split_events 가 COALESCE(effective_date, event_date) 로 실제 조정
시점을 해석하므로 event_date 는 원본(공시일) 그대로 두는 것으로 충분하다.

아직 권리락 전이라 갭이 없으면 이번 실행에선 건너뛰고(멱등) 다음 실행에서 재시도한다.
가짜 갭 방지: 두 일봉 사이 캘린더 간격이 크면(거래정지 아닌 장기 결측 등) 후보에서
제외한다(001130 처럼 4일 거래정지 후 재개하는 정상 케이스는 통과).

방향: 정방향 분할(가격 하락)과 액면병합(가격 상승)을 모두 본다. 추론된 방향은
meta.direction ∈ {'split','merge'} 로 남기며 daily_adj._directional_factor 가 이 값으로
병합의 계수를 뒤집는다(2026-08-03). 병합은 event_type 도 'split' 이다 — 기존 pykrx
백필 53건이 그 규약이고 daily_adj 가 'split'만 소비하므로, 새 event_type 을 만들면
병합이 조용히 무시된다.

scope: event_type='split' 만 추론·스탬프한다(daily_adj 가 'split'만 소비하므로).
bonus_issue 는 corp_events 캡처는 유지하되(Item 2) 가격조정 스탬프는 의도적으로
하지 않는다 — 별도 후속 과제.

infer_and_stamp_split_factors(conn) 는 daily_adj.update_adj_factors 보다 먼저 호출되어야
당일 밤 adj_factor 에 즉시 반영된다(collectors/daily_collector.collect_daily 참조).
"""
import json
from datetime import date, timedelta

from utils.logger import setup_logger

logger = setup_logger(__name__)

_SCAN_DAYS = 90
_RATIO_MIN = 1.5
_RATIO_MAX = 50.0
# 두 일봉 사이 캘린더 간격 상한(일) — 초과하면 "거래정지 후 재개"가 아니라 장기
# 데이터 결측/미상장 구간일 가능성이 높아 분할 갭 후보에서 제외한다(2026-07-06 code
# review). 001130 실사례(거래정지 4일: 금 05-15 → 월 05-18)는 3일 간격이라 통과.
_MAX_GAP_CALENDAR_DAYS = 5

# ── 액면가 비율 화이트리스트 (2026-08-03, 실측으로 확정) ───────────────────────
# 옛 판정은 "round(ratio) 에 0.3 이내면 채택"(_NEAR_INT_TOL)이었다. 이 규칙을 역방향
# (병합)까지 대칭 확장하면 **오탐이 절반**이다 — corp_events 의 pykrx 백필 105건
# (direction·split_factor 확정)을 정답지로 실측한 결과:
#
#   near-int tol=0.3 (대칭 확장)        TP=6  FP=6   ← 채택분의 50%가 틀린 배수
#   액면비율 화이트리스트 rel_tol=0.03  TP=4  FP=0
#   액면비율 화이트리스트 rel_tol=0.05  TP=5  FP=2
#
# 원인: 기업행위 정지 해제일의 봉은 기준가에서 자유롭게 움직인다(105건 중 기준가에
# 정확히 착지한 건 2건뿐, ±30% 상하한 착지가 11건). 그래서 close/close 비율은
# "진짜 배수 × 그날의 등락"이라 정수 근처를 우연히 스쳐도 값이 틀린다. 실제로
#   115160 1:10 병합인데 해제일 +30% 상한 → 12.996 → round=13 (오차 0.004!)
# 로 tol 을 0.01 로 조여도 뚫린다. 즉 "정수 근처"는 판별력이 없는 기준이다.
#
# 대신 국내 액면가는 상법상 이산집합(100·200·500·1,000·2,500·5,000원)이라 분할·병합
# 배수도 그 비율로 한정된다. 절대오차(정수 근처)가 아니라 **상대오차**로 이 집합에
# 스냅하면 위 오탐이 전부 걸러진다(12.996 은 10 에서 30% 벗어남 → 거부).
# rel_tol 은 실측상 0.03 이 zero-FP 경계다(0.05 부터 001510 1:2 병합이 2.5 로 오인).
_FACE_VALUE_RATIOS = (2.0, 2.5, 3.0, 4.0, 5.0, 10.0, 20.0, 25.0, 50.0)
_RATIO_REL_TOL = 0.03


def _load_events_needing_factor(conn) -> list:
    """split_factor 미보유 split 이벤트 로드 → [(stock_code, event_type, event_date)].

    bonus_issue 는 의도적으로 제외한다(daily_adj 가 'split'만 소비 — 스탬프해도
    쓰이지 않고 매일 밤 불필요한 UPDATE 만 유발했다, 2026-07-06 code review).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_code, event_type, event_date FROM corp_events "
            "WHERE event_type = 'split' "
            "AND (meta->>'split_factor') IS NULL "
            "ORDER BY stock_code, event_date"
        )
        return list(cur.fetchall())


def _load_prices_window(conn, stock_code: str, start_iso: str, end_iso: str) -> list:
    """[start_iso, end_iso] 구간 일봉 (date, close) 오름차순. date 컬럼은 TEXT 'YYYY-MM-DD'."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT date, close FROM daily_prices "
            "WHERE stock_code = %s AND date >= %s AND date <= %s "
            "ORDER BY date",
            (stock_code, start_iso, end_iso),
        )
        return [(d, float(c)) for d, c in cur.fetchall() if c is not None]


def _snap_to_face_ratio(ratio: float):
    """가격비 → 액면가 비율 화이트리스트 스냅 (상대오차 _RATIO_REL_TOL 이내) | None."""
    if not (_RATIO_MIN <= ratio <= _RATIO_MAX):
        return None
    best = min(_FACE_VALUE_RATIOS, key=lambda f: abs(ratio / f - 1.0))
    return best if abs(ratio / best - 1.0) <= _RATIO_REL_TOL else None


def _first_clean_gap(prices: list):
    """연속 일봉쌍에서 첫 clean 기업행위 갭 탐지.

    → (effective_date_iso, factor:float, direction:'split'|'merge') | None

    양방향 대칭으로 본다:
      정방향 분할 → close 가 내려간다 → ratio = c_prev / c_cur   (direction='split')
      액면병합    → close 가 올라간다 → ratio = c_cur  / c_prev  (direction='merge')

    옛 코드는 c_prev/c_cur 만 봐서 병합(비율 0.1~0.67)을 조용히 흘렸다 — 그 결과
    생애 스탬프가 1건뿐이었고, 그 1건(001130)마저 배수가 틀렸다(아래 참조).

    채택 기준은 "정수 근처"가 아니라 액면가 비율 화이트리스트 스냅이다
    (_FACE_VALUE_RATIOS 주석에 실측 근거). 정리매매·급락과의 구분도 여기서 난다:
    ±30% 상하한 안의 일반 등락은 비율이 1.5 에 못 미쳐 _RATIO_MIN 에서 걸리고,
    상하한을 낀 기업행위 봉은 화이트리스트 상대오차에서 걸린다.

    캘린더 간격이 _MAX_GAP_CALENDAR_DAYS 를 넘는 쌍(거래정지 아닌 장기 결측 등)은 비율이
    그럴듯해도 후보에서 제외하고 다음 쌍으로 계속 스캔한다(스퓨리어스 갭 오탐 방지).
    """
    for (d_prev, c_prev), (d_cur, c_cur) in zip(prices, prices[1:]):
        if c_cur <= 0 or c_prev <= 0:
            continue
        gap_days = (date.fromisoformat(d_cur) - date.fromisoformat(d_prev)).days
        if gap_days > _MAX_GAP_CALENDAR_DAYS:
            continue
        forward = _snap_to_face_ratio(c_prev / c_cur)
        if forward is not None:
            return d_cur, forward, "split"
        reverse = _snap_to_face_ratio(c_cur / c_prev)
        if reverse is not None:
            return d_cur, reverse, "merge"
    return None


def infer_and_stamp_split_factors(conn) -> int:
    """split_factor 미보유 split 이벤트를 가격갭으로 추론·스탬프. 반환: 스탬프된 행 수.

    - 갭 발견: event_date(PK, 공시일)는 그대로 두고 meta 만 병합(split_factor /
      effective_date=갭 발생일 / split_factor_inferred). meta 다른 키는 보존(jsonb || 병합).
    - 갭 미발견(권리락 전 또는 캘린더 간격 초과로 거부): 건너뜀 → 멱등(다음 실행 재시도).
    """
    events = _load_events_needing_factor(conn)
    stamped = 0
    for stock_code, event_type, event_date in events:
        start_iso = event_date.isoformat()
        end_iso = (event_date + timedelta(days=_SCAN_DAYS)).isoformat()
        prices = _load_prices_window(conn, stock_code, start_iso, end_iso)
        if len(prices) < 2:
            continue
        found = _first_clean_gap(prices)
        if not found:
            continue
        eff_date_iso, factor, direction = found
        # direction 은 항상 남긴다 — daily_adj._directional_factor 가 이 값으로
        # 병합의 부호를 뒤집는다. 없으면 정방향으로 오해석된다.
        meta_patch = json.dumps({
            "split_factor": factor,
            "effective_date": eff_date_iso,
            "direction": direction,
            "split_factor_inferred": True,
        })
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE corp_events "
                    "SET meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb "
                    "WHERE stock_code = %s AND event_type = %s AND event_date = %s",
                    (meta_patch, stock_code, event_type, event_date),
                )
            conn.commit()
            stamped += 1
            logger.info(
                "split_factor 스탬프: %s %s 공시일=%s 권리락일=%s x%g direction=%s "
                "(event_date 불변)",
                stock_code, event_type, start_iso, eff_date_iso, factor, direction,
            )
        except Exception as e:  # noqa: BLE001 — 실패는 격리·다음행 진행
            conn.rollback()
            logger.warning("split_factor 스탬프 실패 %s %s: %s", stock_code, event_type, e)
    return stamped


if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from db.kis_db_connection import KisDbConnection

    with KisDbConnection.get_connection() as _conn:
        print({"stamped": infer_and_stamp_split_factors(_conn)})
