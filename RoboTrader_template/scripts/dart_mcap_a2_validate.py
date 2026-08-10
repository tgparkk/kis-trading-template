"""A(2) DART 분기 주식수 × close 로 계산한 시총 vs 실측 market_cap 오차 측정.

🔴 이것이 백필 방식의 게이트다. 통과시키는 게 목적이 아니라 오차 크기를 재는 게 목적.

정답지 : daily_prices 2024-01-01 ~ 2026-08-06 중 market_cap > 0 인 행
비교값 : DART stockTotqySttus 의 시점별 주식수 × 같은 날 close
look-ahead 방지: 각 날짜에 대해 rcept_no 앞 8자리(접수일) <= 그 날짜 인 가장 최근 보고서만 사용

읽기 전용 — DB 는 SELECT 만. UPDATE/INSERT/DELETE 없음.

usage:
  PYTHONUTF8=1 python scripts/dart_mcap_a2_validate.py            # 수집 + 분석
  PYTHONUTF8=1 python scripts/dart_mcap_a2_validate.py --analyze  # 캐시로 분석만
"""
import argparse
import json
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import (  # noqa: E402
    OUT_DIR, DartBlocked, DartClient, db_conn, load_dart_key, parse_num,
)

SEED = 20260806
N_SAMPLE = 250
DATE_FROM = "2024-01-01"
DATE_TO = "2026-08-06"

MAP_JSON = os.path.join(OUT_DIR, "a1_corpcode_map.json")
SAMPLE_TXT = os.path.join(OUT_DIR, "a2_sample_stocks.txt")
CACHE_JSON = os.path.join(OUT_DIR, "a2_dart_cache.json")
CHECKPOINT_JSONL = os.path.join(OUT_DIR, "a2_dart_checkpoint.jsonl")
ROWS_CSV = os.path.join(OUT_DIR, "a2_rows.csv")
REPORT = os.path.join(OUT_DIR, "a2_report.txt")

# (bsns_year, reprt_code) 조합. 호출 낭비를 줄이기 위해 창(2024-01-01~) 에서 실제로
# 선택될 수 있는 보고서만 부른다.
#   2023 Q3(11014) : 2024-01-02 ~ 2024-03월 사업보고서 제출 전까지 유효한 직전 보고서
#   2023 FY(11011) : 2024-03월 제출
#   2023 Q1/H1     : 2023 Q3 보다 항상 이전이라 절대 선택되지 않음 → 부르지 않음
#   2026           : Q1(11013, 5월 제출)만. 반기(8월 중순)·3분기·사업보고서는 미래.
YEAR_REPRTS = (
    [("2023", rc) for rc in ("11014", "11011")]
    + [("2024", rc) for rc in ("11013", "11012", "11014", "11011")]
    + [("2025", rc) for rc in ("11013", "11012", "11014", "11011")]
    + [("2026", "11013")]
)


def pick_sample():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, count(*) FROM daily_prices "
        "WHERE date >= %s AND date <= %s AND market_cap > 0 AND close > 0 "
        "GROUP BY stock_code HAVING count(*) >= 100",
        (DATE_FROM, DATE_TO),
    )
    universe = sorted(r[0] for r in cur.fetchall())
    conn.close()

    with open(MAP_JSON, encoding="utf-8") as f:
        cmap = json.load(f)
    eligible = [c for c in universe if c in cmap]
    rng = random.Random(SEED)
    sample = sorted(rng.sample(eligible, min(N_SAMPLE, len(eligible))))
    with open(SAMPLE_TXT, "w", encoding="utf-8") as f:
        f.write(f"# seed={SEED} n={len(sample)} universe={len(universe)} eligible={len(eligible)}\n")
        for c in sample:
            f.write(f"{c}\t{cmap[c]}\n")
    return sample, cmap, len(universe), len(eligible)


def _load_checkpoint():
    """JSONL 체크포인트에서 이미 수집한 종목 복원 (차단 재발 시 재개용)."""
    done = {}
    if not os.path.exists(CHECKPOINT_JSONL):
        return done
    with open(CHECKPOINT_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            done[rec["stock_code"]] = rec["entries"]
    return done


def collect(sample, cmap, interval):
    """순차 수집 + 종목 단위 체크포인트.

    🔴 동시요청 금지 — 2026-08-06 에 4스레드로 돌렸다가 opendart 가 IP 를 통째로
       리셋했다(루트 페이지까지 curl reset). 그 상태에서 계속 돌면 전 종목이
       HTTP_FAIL 로 채워지면서 '수집 완료' 처럼 보인다.
    """
    key = load_dart_key()
    if not key:
        raise SystemExit("OPENDART_API_KEY 없음")
    client = DartClient(key, min_interval=interval)

    cache = _load_checkpoint()
    todo = [sc for sc in sample if sc not in cache]
    print(f"체크포인트 복원 {len(cache)}종목 / 남은 {len(todo)}종목 "
          f"(예상 호출 {len(todo)*len(YEAR_REPRTS):,})", flush=True)

    if todo and not client.probe():
        print("opendart 차단 상태 — 해제 대기 시작", flush=True)
        if not client.wait_until_unblocked():
            raise DartBlocked("대기 한도 내 차단 미해제")
        print("차단 해제 확인 — 수집 시작", flush=True)

    ck = open(CHECKPOINT_JSONL, "a", encoding="utf-8")
    try:
        for i, sc in enumerate(todo, 1):
            cc = cmap[sc]
            entries = []
            for year, rc in YEAR_REPRTS:
                while True:
                    try:
                        status, msg, rows = client.stock_totqy(cc, year, rc)
                        break
                    except DartBlocked:
                        print(f"  차단 감지({sc}) — 해제 대기", flush=True)
                        if not client.wait_until_unblocked():
                            raise
                        print("  해제 확인 — 재개", flush=True)
                entries.append({"year": year, "reprt": rc, "status": status,
                                "msg": msg, "rows": rows})
            cache[sc] = entries
            ck.write(json.dumps({"stock_code": sc, "entries": entries},
                                ensure_ascii=False) + "\n")
            ck.flush()
            if i % 10 == 0 or i == len(todo):
                print(f"  ... {i}/{len(todo)} 종목, calls={client.calls}, "
                      f"status={client.status_counts}, resets={client.conn_resets}",
                      flush=True)
    finally:
        ck.close()

    meta = {"calls": client.calls, "status_counts": client.status_counts,
            "http_errors": client.http_errors, "conn_resets": client.conn_resets,
            "block_waits": client.block_waits}
    with open(CACHE_JSON, "w", encoding="utf-8") as f:
        json.dump({"cache": cache, **meta}, f, ensure_ascii=False)
    return cache, meta


def _is_common(se: str) -> bool:
    s = (se or "").replace(" ", "")
    if "우선" in s or "합계" in s or "비고" in s:
        return False
    return "보통" in s


def _is_total(se: str) -> bool:
    s = (se or "").replace(" ", "")
    return "합계" in s


def _has_pref(se: str) -> bool:
    return "우선" in (se or "").replace(" ", "")


def build_timelines(cache):
    """stock_code → {'rcept': [(pubdate, distb, istc, tag)], 'stlm': [...]} (오름차순)."""
    timelines = {}
    se_values = defaultdict(int)
    fallback_total = 0
    no_common = 0
    for sc, entries in cache.items():
        pts = {}   # rcept_dt → (distb, istc, tag)
        spts = {}  # stlm_dt  → (distb, istc, tag)
        for e in entries:
            if e["status"] != "000" or not e["rows"]:
                continue
            rows = e["rows"]
            for r in rows:
                se_values[(r.get("se") or "").strip()] += 1
            common = [r for r in rows if _is_common(r.get("se", ""))]
            tag = "common"
            if not common:
                # 보통주 라벨이 없고 우선주 행도 없으면 단일 주식종류 → 합계 사용
                if not any(_has_pref(r.get("se", "")) for r in rows):
                    common = [r for r in rows if _is_total(r.get("se", ""))]
                    if common:
                        tag = "total_fallback"
                        fallback_total += 1
                if not common:
                    no_common += 1
                    continue
            distb = sum(v for v in (parse_num(r.get("distb_stock_co")) for r in common) if v)
            istc = sum(v for v in (parse_num(r.get("istc_totqy")) for r in common) if v)
            rcept = (common[0].get("rcept_no") or "")[:8]
            stlm = (common[0].get("stlm_dt") or "").replace("-", "")
            if not distb and not istc:
                continue
            if len(rcept) == 8 and rcept.isdigit():
                prev = pts.get(rcept)
                # 같은 접수일에 여러 보고서면 나중 회계기간 우선 (stlm 큰 쪽)
                if prev is None or stlm >= prev[3]:
                    pts[rcept] = (distb, istc, tag, stlm)
            if len(stlm) == 8 and stlm.isdigit():
                spts[stlm] = (distb, istc, tag, rcept)
        if not pts:
            continue
        timelines[sc] = {
            "rcept": sorted((k, v[0], v[1], v[2]) for k, v in pts.items()),
            "stlm": sorted((k, v[0], v[1], v[2]) for k, v in spts.items()),
        }
    return timelines, se_values, fallback_total, no_common


def _lookup(tl, ymd):
    """ymd(YYYYMMDD) 이하 중 가장 최근 시점. 없으면 None."""
    best = None
    for d, distb, istc, tag in tl:
        if d <= ymd:
            best = (d, distb, istc, tag)
        else:
            break
    return best


def pctl(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def analyze(sample, timelines, meta):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, date, close, market_cap FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND date >= %s AND date <= %s "
        "AND market_cap > 0 AND close > 0 ORDER BY stock_code, date",
        (list(sample), DATE_FROM, DATE_TO),
    )
    db_rows = cur.fetchall()
    conn.close()

    errs_distb, errs_istc, errs_stlm = [], [], []
    per_stock = defaultdict(list)
    per_stock_share_ratio = defaultdict(list)
    rows_no_report = 0
    stocks_hit = set()
    csv_lines = ["stock_code,date,close,actual_mcap,dart_date,distb,istc,calc_distb,calc_istc,relerr_distb,relerr_istc,implied_shares,shares_ratio_distb"]

    for sc, d, close, mcap in db_rows:
        tl = timelines.get(sc)
        if not tl:
            continue
        ymd = d.replace("-", "")
        hit = _lookup(tl["rcept"], ymd)
        if hit is None:
            rows_no_report += 1
            continue
        stocks_hit.add(sc)
        pub, distb, istc, tag = hit
        calc_d = distb * close
        calc_i = istc * close
        e_d = abs(calc_d - mcap) / mcap
        e_i = abs(calc_i - mcap) / mcap if istc else float("nan")
        errs_distb.append(e_d)
        if istc:
            errs_istc.append(e_i)
        per_stock[sc].append(e_d)
        implied = mcap / close
        if distb:
            per_stock_share_ratio[sc].append(implied / distb)

        shit = _lookup(tl["stlm"], ymd)
        if shit is not None and shit[1]:
            errs_stlm.append(abs(shit[1] * close - mcap) / mcap)

        csv_lines.append(
            f"{sc},{d},{close},{mcap},{pub},{distb},{istc},{calc_d:.0f},{calc_i:.0f},"
            f"{e_d:.6f},{e_i:.6f},{implied:.1f},{(implied/distb if distb else float('nan')):.6f}"
        )

    with open(ROWS_CSV, "w", encoding="utf-8") as f:
        f.write("\n".join(csv_lines) + "\n")

    def dist(name, arr):
        a = sorted(arr)
        n = len(a)
        if not n:
            return f"{name}: 행 0"
        le1 = sum(1 for x in a if x <= 0.01) / n
        le5 = sum(1 for x in a if x <= 0.05) / n
        gt10 = sum(1 for x in a if x > 0.10) / n
        return (f"{name}: n={n:,}  median={pctl(a,0.5)*100:.4f}%  p90={pctl(a,0.9)*100:.4f}%  "
                f"p99={pctl(a,0.99)*100:.4f}%  max={a[-1]*100:.2f}%  "
                f"|  <=1%: {le1*100:.2f}%  <=5%: {le5*100:.2f}%  >10%: {gt10*100:.2f}%")

    lines = []
    add = lines.append
    add("=== A(2) DART 분기 주식수 방식 검증 ===")
    add(f"seed={SEED}  표본종목={len(sample)}  구간={DATE_FROM}~{DATE_TO}")
    add(f"universe(mcap>0 & >=100행)={meta['universe']}  그중 corp_code 매핑됨={meta['eligible']}")
    add(f"DART 호출 수={meta['calls']:,}  status 분포={meta['status_counts']}")
    add(f"  http 재시도실패={meta['http_errors']}  연결리셋={meta['conn_resets']}  "
        f"차단대기(회)={meta['block_waits']}  수집완료종목={meta['collected']}")
    add("")
    add(f"DB 비교대상 행(market_cap>0)  : {len(db_rows):,}")
    add(f"타임라인 확보 종목            : {len(timelines)} / {len(sample)}")
    add(f"  DART 응답 없어 계산불가 종목: {len(sample) - len(timelines)}")
    add(f"실제 오차 계산된 종목         : {len(stocks_hit)}")
    add(f"보고서 이전 날짜라 스킵된 행  : {rows_no_report:,}")
    add(f"se 라벨 분포                  : {dict(sorted(meta['se_values'].items(), key=lambda kv: -kv[1])[:12])}")
    add(f"합계 폴백(단일주식종류) 보고서: {meta['fallback_total']}   보통주 행 못찾음: {meta['no_common']}")
    add("")
    add("--- 상대오차 |계산-실측|/실측 ---")
    add(dist("[주] distb_stock_co(유통주식수) x close, 접수일 기준", errs_distb))
    add(dist("[참] istc_totqy(발행주식총수)  x close, 접수일 기준", errs_istc))
    add(dist("[참] distb_stock_co x close, 결산일 기준(소급허용)", errs_stlm))
    add("")

    # 종목별 중앙오차 상위 10
    ranked = sorted(((sorted(v)[len(v)//2], sc, len(v)) for sc, v in per_stock.items()), reverse=True)
    add("--- 오차 큰 상위 10종목 (종목별 중앙오차, distb 기준) ---")
    add("stock  median_err   n행   implied/dart 주식수비(중앙)  min~max")
    for med, sc, n in ranked[:10]:
        rr = sorted(per_stock_share_ratio.get(sc, []))
        rmed = rr[len(rr)//2] if rr else float("nan")
        rmin = rr[0] if rr else float("nan")
        rmax = rr[-1] if rr else float("nan")
        add(f"{sc}  {med*100:9.3f}%  {n:5d}   {rmed:10.4f}   {rmin:.4f}~{rmax:.4f}")
    add("")
    ok = sum(1 for med, _, _ in ranked if med <= 0.01)
    add(f"종목별 중앙오차 <=1% 종목: {ok}/{len(ranked)} ({ok/max(len(ranked),1)*100:.1f}%)")
    ok5 = sum(1 for med, _, _ in ranked if med <= 0.05)
    add(f"종목별 중앙오차 <=5% 종목: {ok5}/{len(ranked)} ({ok5/max(len(ranked),1)*100:.1f}%)")
    add("")
    add(f"행 단위 CSV: {ROWS_CSV}")

    txt = "\n".join(lines)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze", action="store_true", help="체크포인트/캐시로 분석만")
    ap.add_argument("--interval", type=float, default=1.0, help="요청 간 최소 간격(초)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    sample, cmap, n_uni, n_elig = pick_sample()
    print(f"표본 {len(sample)}종목 선정 (seed={SEED}) → {SAMPLE_TXT}", flush=True)

    if args.analyze:
        cache = _load_checkpoint()
        meta = {"calls": -1, "status_counts": {}, "http_errors": -1,
                "conn_resets": -1, "block_waits": -1}
        if os.path.exists(CACHE_JSON):
            with open(CACHE_JSON, encoding="utf-8") as f:
                blob = json.load(f)
            cache = cache or blob["cache"]
            meta = {k: blob.get(k, -1) for k in meta}
    else:
        print("DART 수집 시작(순차)...", flush=True)
        cache, meta = collect(sample, cmap, args.interval)

    timelines, se_values, fallback_total, no_common = build_timelines(cache)
    analyze(sample, timelines, dict(
        meta, se_values=se_values, fallback_total=fallback_total,
        no_common=no_common, universe=n_uni, eligible=n_elig,
        collected=len(cache),
    ))


if __name__ == "__main__":
    main()
