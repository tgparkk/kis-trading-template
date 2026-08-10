"""A(2) 보강 — 계산식 변형별 오차 비교 + 오차 원인 분해.

읽기 전용(DB SELECT + 로컬 체크포인트). DART 재호출 없음.

배경: 1차 측정에서 distb_stock_co x close 의 median 오차가 2.35%, p90 26.6% 로 났다.
그 오차가 (a) 분기 스냅샷 계단함수 때문인지 (b) 다른 구조적 이유인지 갈라야
판정을 내릴 수 있다. 실측 결과 (b) 가 지배적이었고 두 갈래다:

  B1. 주식수 정의 불일치 — 우리 market_cap 은 **상장주식수**(=istc_totqy) 기준인데
      과제 지시는 distb_stock_co(유통주식수, 자기주식 차감)였다.
  B2. 가격 기준 불일치 — daily_prices.close 는 **분할 후방조정** 시세인데
      DART 주식수는 **시점 실제 주식수**다. 분할 이후 시점에서 보면 과거 구간의
      close 는 1/factor 로 눌려 있어 시점 주식수를 그대로 곱하면 factor 배 틀린다.
      보정항이 곧 daily_prices.adj_factor 다.

      market_cap = close(조정) x shares(시점) x adj_factor

  ⚠️ 프로젝트 규약 "adj_factor 를 곱하지 말 것" 은 **가격**을 조정할 때의 규칙이다
     (close 는 이미 조정돼 있어 또 곱하면 가짜 절벽). 여기서는 가격이 아니라
     **시점 주식수를 조정가격 기준계로 옮기는** 용도라 곱하는 것이 산술적으로 필요하다.
     둘을 같은 규칙으로 묶지 말 것.

usage:
  PYTHONUTF8=1 python scripts/dart_mcap_a2_variants.py
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import OUT_DIR, db_conn, parse_num  # noqa: E402

CHECKPOINT_JSONL = os.path.join(OUT_DIR, "a2_dart_checkpoint.jsonl")
REPORT = os.path.join(OUT_DIR, "a2_variants_report.txt")
DATE_FROM = "2024-01-01"
DATE_TO = "2026-08-06"

_PREF = ("우선", "종류주", "의결권없", "의결권이없", "무의결권")
_COMM = ("보통", "의결권있", "의결권이있")
_SKIP = ("합계", "비고")


def _norm(se):
    return (se or "").replace(" ", "")


def classify(se):
    s = _norm(se)
    if any(k in s for k in _SKIP):
        return "skip"
    if any(k in s for k in _PREF):
        return "pref"
    if any(k in s for k in _COMM):
        return "common"
    return "unknown"


def build_timelines(cache):
    """stock_code → 접수일 오름차순 [(rcept_dt, distb, istc)]."""
    tl = {}
    stats = defaultdict(int)
    unknown_labels = defaultdict(int)
    for sc, entries in cache.items():
        pts = {}
        for e in entries:
            if e["status"] != "000" or not e["rows"]:
                stats["report_no_data"] += 1
                continue
            rows = e["rows"]
            kinds = {}
            for r in rows:
                k = classify(r.get("se"))
                kinds.setdefault(k, []).append(r)
                if k == "unknown":
                    unknown_labels[_norm(r.get("se"))] += 1
            use = kinds.get("common")
            if use:
                stats["common"] += 1
            elif not kinds.get("pref") and kinds.get("unknown"):
                # 우선주 행이 없고 라벨만 낯선 경우 → 그 행들을 보통주로 간주
                use = kinds["unknown"]
                stats["unknown_as_common"] += 1
            elif not kinds.get("pref"):
                # 단일 주식종류 → 합계 행 사용
                use = [r for r in rows if "합계" in _norm(r.get("se"))]
                if use:
                    stats["total_fallback"] += 1
            if not use:
                stats["unresolved"] += 1
                continue
            distb = sum(v for v in (parse_num(r.get("distb_stock_co")) for r in use) if v)
            istc = sum(v for v in (parse_num(r.get("istc_totqy")) for r in use) if v)
            if not distb and not istc:
                stats["zero_shares"] += 1
                continue
            rcept = (use[0].get("rcept_no") or "")[:8]
            stlm = (use[0].get("stlm_dt") or "").replace("-", "")
            if len(rcept) == 8 and rcept.isdigit():
                prev = pts.get(rcept)
                if prev is None or stlm >= prev[2]:
                    pts[rcept] = (distb, istc, stlm)
        if pts:
            tl[sc] = sorted((k, v[0], v[1]) for k, v in pts.items())
    return tl, stats, unknown_labels


def lookup(tl, ymd):
    best = None
    for d, distb, istc in tl:
        if d <= ymd:
            best = (d, distb, istc)
        else:
            break
    return best


def pctl(a, p):
    if not a:
        return float("nan")
    k = (len(a) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(a) - 1)
    return a[lo] + (a[hi] - a[lo]) * (k - lo)


def dist(name, arr):
    a = sorted(arr)
    n = len(a)
    if not n:
        return f"{name:52s} n=0"
    return (f"{name:52s} n={n:7,}  med={pctl(a,0.5)*100:8.4f}%  p90={pctl(a,0.9)*100:8.4f}%  "
            f"p99={pctl(a,0.99)*100:9.4f}%  max={a[-1]*100:10.2f}%  "
            f"<=1%:{sum(1 for x in a if x<=0.01)/n*100:6.2f}%  "
            f"<=5%:{sum(1 for x in a if x<=0.05)/n*100:6.2f}%  "
            f">10%:{sum(1 for x in a if x>0.10)/n*100:6.2f}%")


def main():
    cache = {}
    with open(CHECKPOINT_JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                cache[rec["stock_code"]] = rec["entries"]

    tl, stats, unknown_labels = build_timelines(cache)
    codes = sorted(cache)

    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, date, close, market_cap, adj_factor FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND date >= %s AND date <= %s "
        "AND market_cap > 0 AND close > 0 ORDER BY stock_code, date",
        (codes, DATE_FROM, DATE_TO),
    )
    db_rows = cur.fetchall()
    conn.close()

    V = {k: [] for k in ("distb", "istc", "distb_adj", "istc_adj")}
    seg_clean = {k: [] for k in V}
    seg_ca = {k: [] for k in V}
    per_stock = defaultdict(list)          # istc_adj 기준 종목별 오차
    per_stock_before = defaultdict(list)   # istc 기준(보정 전)
    skipped = 0
    ca_stocks, shares_changed = set(), set()

    # 종목별 분할/병합 존재 여부.
    # 🔴 정의는 `adj_factor IS NOT NULL AND adj_factor <> 1` 이다.
    #    NULL 을 ≠1 로 계상하면 2026-08-06 실측 기준 95종목이 2,488종목으로 부풀어
    #    "분할 없는 종목" 세그먼트가 3종목까지 쪼그라든다(무효 세그먼트).
    #    market_cap 결손을 NULL 로만 세면 9.65%/0 까지 세면 54.55% 였던 것과 같은
    #    클래스의 실수 — 방향만 반대다. NULL 은 "값 없음"이지 "≠1" 이 아니다.
    #    범위는 **전체 이력** 이다 — 창(2024~) 밖의 분할도 close 의 기준계를 바꾸므로
    #    창 안 행만 보면 놓친다(창 기준 5종목 / 전체 이력 기준 8종목).
    conn2 = db_conn()
    cur2 = conn2.cursor()
    cur2.execute(
        "SELECT DISTINCT stock_code FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND adj_factor IS NOT NULL AND adj_factor <> 1",
        (codes,))
    ca_stocks.update(r[0] for r in cur2.fetchall())
    conn2.close()
    for sc, pts in tl.items():
        if len({p[2] for p in pts}) > 1:
            shares_changed.add(sc)

    for sc, d, close, mcap, af in db_rows:
        t = tl.get(sc)
        if not t:
            continue
        hit = lookup(t, d.replace("-", ""))
        if hit is None:
            skipped += 1
            continue
        _, distb, istc = hit
        af = af or 1.0
        vals = {
            "distb": distb * close,
            "istc": istc * close,
            "distb_adj": distb * close * af,
            "istc_adj": istc * close * af,
        }
        bucket = seg_ca if sc in ca_stocks else seg_clean
        for k, v in vals.items():
            e = abs(v - mcap) / mcap
            V[k].append(e)
            bucket[k].append(e)
        per_stock[sc].append(abs(vals["istc_adj"] - mcap) / mcap)
        per_stock_before[sc].append(abs(vals["istc"] - mcap) / mcap)

    L = []
    add = L.append
    add("=== A(2) 보강: 계산식 변형별 오차 + 원인 분해 ===")
    add(f"표본 {len(codes)}종목 / 비교행 {len(db_rows):,} / 보고서前 스킵 {skipped:,}")
    add(f"se 분류 통계: {dict(stats)}")
    add(f"미상 se 라벨: {dict(sorted(unknown_labels.items(), key=lambda kv:-kv[1])[:10])}")
    add(f"분할·병합 종목(adj_factor≠1): {len(ca_stocks)} / {len(codes)}")
    add(f"DART 주식수가 창 안에서 변한 종목: {len(shares_changed)} / {len(tl)}")
    add("")
    add("--- 전체 표본 ---")
    add(dist("[지시] distb x close", V["distb"]))
    add(dist("[정의보정] istc  x close", V["istc"]))
    add(dist("[분할보정] distb x close x adj_factor", V["distb_adj"]))
    add(dist("[정의+분할보정] istc x close x adj_factor", V["istc_adj"]))
    add("")
    add(f"--- 분할·병합 없는 종목만 ({len(codes)-len(ca_stocks)}종목) = 순수 분기 계단함수 오차 ---")
    add(dist("[지시] distb x close", seg_clean["distb"]))
    add(dist("[정의보정] istc  x close", seg_clean["istc"]))
    add(dist("[정의+분할보정] istc x close x adj_factor", seg_clean["istc_adj"]))
    add("")
    add(f"--- 분할·병합 있는 종목만 ({len(ca_stocks)}종목) ---")
    add(dist("[지시] distb x close", seg_ca["distb"]))
    add(dist("[정의보정] istc  x close", seg_ca["istc"]))
    add(dist("[정의+분할보정] istc x close x adj_factor", seg_ca["istc_adj"]))
    add("")

    ranked = sorted(((sorted(v)[len(v)//2], sc, len(v)) for sc, v in per_stock.items()), reverse=True)
    add("--- 최선식(istc x close x adj_factor) 에서도 오차 큰 상위 10종목 ---")
    add("stock   median_err    보정전(istc)    n행   분할有  DART주식수변동")
    for med, sc, n in ranked[:10]:
        before = sorted(per_stock_before[sc])
        bmed = before[len(before)//2]
        add(f"{sc}   {med*100:9.3f}%   {bmed*100:11.3f}%  {n:5d}   "
            f"{'Y' if sc in ca_stocks else 'N':^5s}  {'Y' if sc in shares_changed else 'N'}")
    add("")
    for thr, label in ((0.01, "1%"), (0.05, "5%")):
        ok = sum(1 for med, _, _ in ranked if med <= thr)
        add(f"종목별 중앙오차 <={label} : {ok}/{len(ranked)} ({ok/len(ranked)*100:.1f}%)")

    txt = "\n".join(L)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
