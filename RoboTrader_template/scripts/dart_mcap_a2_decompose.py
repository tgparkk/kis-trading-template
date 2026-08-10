"""A(2) 최종 — 오차 원인 분해 및 「기준계 판별 가능성」 검정.

읽기 전용(DB SELECT + 로컬 체크포인트). DART 재호출 없음.

핵심 질문: shares(DART 시점값) x close 로 market_cap 을 복원할 수 있는가?
실측 결과 종목이 두 기준계로 갈린다.
  PLAIN : implied(=market_cap/close) ≈ DART 시점 주식수   → close 가 raw 기준
  ADJ   : implied ≈ DART 시점 주식수 x adj_factor          → close 가 후방조정 기준
두 기준계는 **같은 DB 컬럼으로는 구분되지 않는다**(둘 다 adj_factor≠1 을 가질 수 있다).
구분 불가면 2021~23 백필은 종목별로 factor 배 틀린 값을 쓰게 된다.
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import OUT_DIR, db_conn, parse_num  # noqa: E402
from dart_mcap_a2_variants import build_timelines, dist, lookup, pctl  # noqa: E402

CHECKPOINT_JSONL = os.path.join(OUT_DIR, "a2_dart_checkpoint.jsonl")
REPORT = os.path.join(OUT_DIR, "a2_decompose_report.txt")
DATE_FROM = "2024-01-01"
DATE_TO = "2026-08-06"


def med(a):
    a = sorted(a)
    return a[len(a) // 2] if a else float("nan")


def main():
    cache = {}
    with open(CHECKPOINT_JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                cache[r["stock_code"]] = r["entries"]
    tl, stats, _ = build_timelines(cache)
    codes = sorted(cache)

    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, date, close, market_cap, COALESCE(adj_factor,1.0) "
        "FROM daily_prices WHERE stock_code = ANY(%s) AND date >= %s AND date <= %s "
        "AND market_cap > 0 AND close > 0 ORDER BY stock_code, date",
        (codes, DATE_FROM, DATE_TO),
    )
    db_rows = cur.fetchall()

    # 전체 이력 기준 분할·병합 여부 (창 밖 사건도 close 기준계에 영향).
    # 🔴 정의 통일: `adj_factor IS NOT NULL AND adj_factor <> 1`.
    #    NULL 은 "값 없음"이지 "≠1" 이 아니다. NULL 을 ≠1 로 세면 95종목이 2,488종목이 된다.
    cur.execute(
        "SELECT DISTINCT stock_code FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND adj_factor IS NOT NULL AND adj_factor <> 1",
        (codes,))
    ever_ca = {r[0] for r in cur.fetchall()}
    conn.close()

    rows_by_stock = defaultdict(list)
    for sc, d, close, mcap, af in db_rows:
        rows_by_stock[sc].append((d, close, mcap, af))

    plain_err, adj_err = defaultdict(list), defaultdict(list)
    dart_changed = set()
    skipped = 0
    for sc, rs in rows_by_stock.items():
        t = tl.get(sc)
        if not t:
            continue
        if len({p[2] for p in t}) > 1:
            dart_changed.add(sc)
        for d, close, mcap, af in rs:
            hit = lookup(t, d.replace("-", ""))
            if hit is None:
                skipped += 1
                continue
            _, _distb, istc = hit
            if not istc:
                continue
            plain_err[sc].append(abs(istc * close - mcap) / mcap)
            adj_err[sc].append(abs(istc * close * af - mcap) / mcap)

    # 기준계 판별: 종목별 중앙오차가 더 작은 쪽
    bucket = {}
    for sc in plain_err:
        p, a = med(plain_err[sc]), med(adj_err[sc])
        if p <= 0.02 and a > 0.02:
            bucket[sc] = "PLAIN"
        elif a <= 0.02 and p > 0.02:
            bucket[sc] = "ADJ"
        elif p <= 0.02 and a <= 0.02:
            bucket[sc] = "BOTH(adj=1)"
        else:
            bucket[sc] = "NEITHER"

    cnt = defaultdict(int)
    for v in bucket.values():
        cnt[v] += 1

    L = []
    add = L.append
    add("=== A(2) 최종: 오차 원인 분해 ===")
    add(f"표본 {len(codes)}종목 / 비교행 {len(db_rows):,} / 보고서前 스킵 {skipped:,}")
    add(f"se 분류: {dict(stats)}")
    add(f"이력상 분할·병합 있는 종목(adj_factor≠1 존재): {len(ever_ca)}/{len(codes)}")
    add(f"창 안에서 DART 주식수가 변한 종목: {len(dart_changed)}/{len(tl)}")
    add("")
    add("--- 종목별 기준계 판별 (중앙오차 2% 임계) ---")
    for k in ("BOTH(adj=1)", "PLAIN", "ADJ", "NEITHER"):
        add(f"  {k:12s}: {cnt[k]:4d}종목  ({cnt[k]/len(bucket)*100:5.1f}%)")
    add("  * BOTH = adj_factor 가 1.0 이라 두 식이 같은 값 → 구분 불필요")
    add("  * PLAIN vs ADJ 가 동시에 존재하면 = 같은 컬럼으로 기준계를 못 가른다")
    add("")

    # PLAIN / ADJ 종목이 adj_factor 로 구분되는가?
    pl = [sc for sc, v in bucket.items() if v == "PLAIN"]
    aj = [sc for sc, v in bucket.items() if v == "ADJ"]
    ne = [sc for sc, v in bucket.items() if v == "NEITHER"]
    add(f"PLAIN 중 이력상 분할有: {sum(1 for s in pl if s in ever_ca)}/{len(pl)}")
    add(f"ADJ   중 이력상 분할有: {sum(1 for s in aj if s in ever_ca)}/{len(aj)}")
    add("  → 둘 다 '분할 있음' 이면 adj_factor 유무로는 판별 불가")
    add(f"PLAIN 예시: {pl[:8]}")
    add(f"ADJ   예시: {aj[:8]}")
    add(f"NEITHER 예시: {ne[:8]}")
    add("")

    # 사건이 전혀 없는 종목만 = 순수 분기 계단함수 오차의 하한
    clean = [sc for sc in plain_err if sc not in ever_ca and sc not in dart_changed]
    clean_rows = [e for sc in clean for e in plain_err[sc]]
    ca_only = [sc for sc in plain_err if sc not in ever_ca and sc in dart_changed]
    ca_rows = [e for sc in ca_only for e in plain_err[sc]]
    add(f"--- 세그먼트별 오차 (식 = istc x close) ---")
    add(dist(f"분할X·주식수변동X ({len(clean)}종목)", clean_rows))
    add(dist(f"분할X·주식수변동O ({len(ca_only)}종목)", ca_rows))
    add(dist(f"분할O ({len([s for s in plain_err if s in ever_ca])}종목)",
             [e for sc in plain_err if sc in ever_ca for e in plain_err[sc]]))
    add("")

    # 최선 시나리오: 기준계를 신탁으로 알려준다고 가정했을 때의 상한 성능
    oracle = []
    for sc in plain_err:
        src = adj_err[sc] if bucket[sc] == "ADJ" else plain_err[sc]
        oracle.extend(src)
    add("--- 상한(oracle): 종목별 기준계를 정답으로 알려줬다고 가정 ---")
    add(dist("oracle", oracle))
    add("  ※ 실제로는 2021~23 에 정답지가 없어 이 판별 자체가 불가능하다.")
    add("")

    ranked = sorted((med(plain_err[sc] if bucket[sc] != "ADJ" else adj_err[sc]), sc)
                    for sc in plain_err)[::-1]
    add("--- oracle 기준으로도 오차 큰 상위 10종목 ---")
    add("stock   median_err   기준계        분할有  DART변동")
    for m, sc in ranked[:10]:
        add(f"{sc}   {m*100:9.3f}%   {bucket[sc]:12s} {'Y' if sc in ever_ca else 'N':^6s} "
            f"{'Y' if sc in dart_changed else 'N'}")

    txt = "\n".join(L)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
