"""B(3) price-gap 분할 탐지 + DART 대조 가드.

읽기 전용(DB SELECT). DB 쓰기 없음.

🔴 새 판정 규칙을 만들지 않는다. `collectors/split_factor_infer.py` 의 **검증된**
   액면가비율 화이트리스트 스냅(`_snap_to_face_ratio`)과 캘린더 간격 상한을 그대로
   import 해서 쓴다. 그 파일은 읽기만 하고 수정하지 않는다(라이브 디렉토리).
   그 로직은 corp_events 의 pykrx 백필 105건을 정답지로 실측 확정된 것이다
   (rel_tol=0.03 에서 TP=4/FP=0; "정수 근처" 규칙은 채택분 50%가 오탐이었다).

가드:
  G1 (134380형, 지시받은 것)
     구간 내 price-gap 분할이 있는데 **DART 주식수가 그 시점에 대응해 변하지 않았다**
     → DART 가 분할을 미갱신한 종목 → 종목 전 구간 SUSPECT 강등.
     134380 실측: 2024-03-20 close 69,900→7,070(정확히 1/10), market_cap 연속,
     그런데 DART 는 2023-11~2026-05 보고서 전부 istc=2,199,268 로 불변.

  G2 (후방조정 오염)
     DART 주식수는 분할 배수로 변했는데 **price-gap 이 없다** → close 가 후방조정된
     것이므로 그 이전 구간 행의 기준계가 시점 주식수와 다르다 → 종목 전 구간 SUSPECT.
     000860 실측: 2025-04-30 분할인데 close 연속(후방조정), adj_factor 2.0.

⚠️ `adj_factor` 를 이 판정의 단독 근거로 쓰지 말 것 — 195990 은 실제 10:1 병합인데
   `adj_factor=1.0` 이었고 134380 도 실제 분할인데 1.0 이다. 즉 누락이 있다.

usage:
  PYTHONUTF8=1 python scripts/dart_mcap_b3_split_guard.py --scan-from 2021-01-01
"""
import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dart_mcap_common import OUT_DIR, db_conn  # noqa: E402
# 라이브 모듈은 **읽기 전용 재사용** — 수정하지 않는다.
from collectors.split_factor_infer import (  # noqa: E402
    _MAX_GAP_CALENDAR_DAYS, _snap_to_face_ratio,
)

GAPS_JSON = os.path.join(OUT_DIR, "b3_price_gaps.json")


def scan_gaps(prices):
    """전 구간의 모든 clean 기업행위 갭. → [(date_iso, factor, direction)]

    split_factor_infer._first_clean_gap 은 '첫' 갭만 반환한다(공시일 기준 90일 창
    용도). 여기서는 다년 구간을 훑어야 하므로 같은 판정식으로 끝까지 스캔한다.
    판정 규칙 자체(_snap_to_face_ratio, 캘린더 간격 상한)는 그대로 재사용한다.
    """
    out = []
    for (d_prev, c_prev), (d_cur, c_cur) in zip(prices, prices[1:]):
        if c_cur <= 0 or c_prev <= 0:
            continue
        if (date.fromisoformat(d_cur) - date.fromisoformat(d_prev)).days > _MAX_GAP_CALENDAR_DAYS:
            continue
        fwd = _snap_to_face_ratio(c_prev / c_cur)
        if fwd is not None:
            out.append((d_cur, fwd, "split"))
            continue
        rev = _snap_to_face_ratio(c_cur / c_prev)
        if rev is not None:
            out.append((d_cur, rev, "merge"))
    return out


def load_gaps(codes, date_from, date_to):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, date, close FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND date >= %s AND date <= %s AND close > 0 "
        "ORDER BY stock_code, date",
        (list(codes), date_from, date_to),
    )
    series = {}
    for sc, d, c in cur.fetchall():
        series.setdefault(sc, []).append((d, float(c)))
    conn.close()
    return {sc: g for sc, g in ((sc, scan_gaps(p)) for sc, p in series.items()) if g}


def dart_changed_across(stlm_tl, gap_date):
    """gap_date 를 사이에 둔 DART 주식수 변화가 있는가.

    stlm_tl: [(stlm_yyyymmdd, istc)] 오름차순.
    gap_date 직전 보고서와 직후 보고서를 비교한다. 한쪽이 없으면 None(판정 불가).
    """
    g = gap_date.replace("-", "")
    before = [v for d, v in stlm_tl if d < g]
    after = [v for d, v in stlm_tl if d >= g]
    if not before or not after:
        return None
    return before[-1] != after[0]


def build_guard(stlm_timelines, gaps, window_from, window_to):
    """→ (demoted: {stock: reason}, detail: [...])"""
    demoted, detail = {}, []
    for sc, tl in stlm_timelines.items():
        g_in = [g for g in gaps.get(sc, []) if window_from <= g[0] <= window_to]
        # G1: 갭은 있는데 DART 가 안 변했다
        for gdate, factor, direction in g_in:
            ch = dart_changed_across(tl, gdate)
            if ch is False:
                demoted[sc] = f"G1 price-gap {gdate} x{factor:g} {direction} but DART unchanged"
                detail.append((sc, "G1", gdate, factor, direction))
                break
        if sc in demoted:
            continue
        # G2: DART 는 분할 배수로 변했는데 갭이 없다 (close 후방조정 의심)
        gap_dates = {g[0] for g in g_in}
        for (d1, v1), (d2, v2) in zip(tl, tl[1:]):
            if not v1 or not v2 or v1 == v2:
                continue
            if not (window_from.replace("-", "") <= d2 <= window_to.replace("-", "")):
                continue
            ratio = max(v1, v2) / min(v1, v2)
            if _snap_to_face_ratio(ratio) is None:
                continue  # 증자·감자 등 비(非)분할 변화는 close 를 소급 변경하지 않는다
            near = any(abs((date.fromisoformat(gd) - date(int(d2[:4]), int(d2[4:6]), int(d2[6:]))).days) <= 150
                       for gd in gap_dates)
            if not near:
                demoted[sc] = (f"G2 DART x{ratio:.3g} at {d2} but no price-gap "
                               "(close back-adjusted)")
                detail.append((sc, "G2", d2, ratio, "adj"))
                break
    return demoted, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-from", default="2021-01-01")
    ap.add_argument("--scan-to", default="2026-08-06")
    args = ap.parse_args()

    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM daily_prices "
                "WHERE date >= '2021-01-01' AND date <= '2023-12-31'")
    codes = sorted(r[0] for r in cur.fetchall())
    conn.close()

    gaps = load_gaps(codes, args.scan_from, args.scan_to)
    with open(GAPS_JSON, "w", encoding="utf-8") as f:
        json.dump(gaps, f, ensure_ascii=False)

    n_gaps = sum(len(v) for v in gaps.values())
    print(f"스캔 {len(codes)}종목 {args.scan_from}~{args.scan_to}")
    print(f"price-gap 기업행위 탐지: {n_gaps}건 / {len(gaps)}종목")
    by_dir = {}
    for v in gaps.values():
        for _, _, d in v:
            by_dir[d] = by_dir.get(d, 0) + 1
    print(f"  방향별: {by_dir}")
    in_win = {sc: [g for g in v if g[0] <= '2023-12-31'] for sc, v in gaps.items()}
    in_win = {k: v for k, v in in_win.items() if v}
    print(f"  2021~23 구간 내: {sum(len(v) for v in in_win.values())}건 / {len(in_win)}종목")
    print(f"  134380 탐지: {gaps.get('134380')}")
    print(f"저장: {GAPS_JSON}")


if __name__ == "__main__":
    main()
