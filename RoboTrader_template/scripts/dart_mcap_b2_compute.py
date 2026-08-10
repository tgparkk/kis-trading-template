"""B(2) 시총 추정값 계산 + 게이팅. A단계에서 확정된 규약 그대로.

읽기 전용(DB SELECT). DB 쓰기는 b4 가 담당한다.

규약 (A단계 실측으로 확정):
  1. 식      = istc_totqy x close        (distb_stock_co 금지: median 2.35% vs 0.029%)
  2. 날짜    = 결산일 기준 — 그 날짜를 감싸는 결산기(stlm_dt >= D 인 최초 보고서)
  3. 게이트  = SAFE_STRICT
       W1 직전 보고서와 감싸는 보고서의 주식수가 같다   (구간 내 사건 없음)
       W2 감싸는 보고서와 최신 보고서의 주식수가 같다   (이후 불변 — 후방조정 오염 차단)
       W3 b3 가드(G1/G2)에 걸린 종목이 아니다
  4. se 분류 = 보정판 (보통주/보통주식/의결권 있는 주식/종류주식/오타 포함)

게이트 v2 (사전등록 prereg-2026-08-10-mcap-gate-v2, 결과 보기 전 고정):
  주식수 변동을 「비율성(액면분할·병합·무상증자 — 주가 후방조정 동반)」과
  「점진적(스톡옵션·CB전환 — 조정 없음)」으로 갈라 **W1·W2 두 조건만** 좁힌다.
  v1 은 지우지 않는다. `--gate v1|v2` 로 둘 다 돌고 `--compare` 로 같은 표에 올린다.

--validate 모드: 2024~2026 구간(market_cap 실측 존재)에서 게이트 누수를 측정한다.
  게이트를 2021~23 에 적용하기 전에 **정답지가 있는 곳에서 먼저 재는** 절차다.

usage:
  PYTHONUTF8=1 python scripts/dart_mcap_b2_compute.py --validate
  PYTHONUTF8=1 python scripts/dart_mcap_b2_compute.py --validate --gate v2
  PYTHONUTF8=1 python scripts/dart_mcap_b2_compute.py --validate --compare
  PYTHONUTF8=1 python scripts/dart_mcap_b2_compute.py --emit [--gate v2]
"""
import argparse
import json
import os
import sys
from bisect import bisect_left
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import OUT_DIR, db_conn, parse_num  # noqa: E402
from dart_mcap_a2_variants import classify, dist, pctl  # noqa: E402
from dart_mcap_b3_split_guard import build_guard  # noqa: E402

A2_CHECKPOINT = os.path.join(OUT_DIR, "a2_dart_checkpoint.jsonl")
B1_CHECKPOINT = os.path.join(OUT_DIR, "b1_dart_checkpoint.jsonl")
FWD_CHECKPOINT = os.path.join(OUT_DIR, "b1_forward_checkpoint.jsonl")
GAPS_JSON = os.path.join(OUT_DIR, "b3_price_gaps.json")
EMIT_JSONL = os.path.join(OUT_DIR, "b2_estimates.jsonl")
VALIDATE_REPORT = os.path.join(OUT_DIR, "b2_validate_report.txt")
COMPARE_REPORT = os.path.join(OUT_DIR, "b2_gate_compare_report.txt")

# 🔒 사전등록 §6 합격 기준 — **사후에 낮추지 않는다.**
PASS_G1_LEAK10 = 0.35   # v2 >10% 누수율 상한 (v1 0.1717% x2)
PASS_G2_LEAK1 = 3.0     # v2 >1%  누수율 상한 (v1 2.0423% +1%p)
PASS_G3_SAFE = 57.0     # v2 SAFE 비율 하한 (v1 50.19% +7%p)


def gate_out_path(base, gate):
    """v1 산출물 경로는 그대로 두고 v2 만 따로 쓴다(기존 결과 덮어쓰기 방지)."""
    if gate == "v1":
        return base
    root, ext = os.path.splitext(base)
    return f"{root}_{gate}{ext}"


def load_checkpoints(paths):
    cache = defaultdict(list)
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    cache[rec["stock_code"]].extend(rec["entries"])
    return dict(cache)


def stlm_timeline(entries):
    """[(stlm_yyyymmdd, istc)] 오름차순. se 보정판 분류 사용."""
    pts = {}
    for e in entries:
        if e["status"] != "000" or not e["rows"]:
            continue
        rows = e["rows"]
        kinds = defaultdict(list)
        for r in rows:
            kinds[classify(r.get("se"))].append(r)
        use = kinds.get("common")
        if not use and not kinds.get("pref"):
            use = kinds.get("unknown") or [
                r for r in rows if "합계" in (r.get("se") or "").replace(" ", "")]
        if not use:
            continue
        istc = sum(v for v in (parse_num(r.get("istc_totqy")) for r in use) if v)
        if not istc:
            continue
        stlm = (use[0].get("stlm_dt") or "").replace("-", "")
        rcept = (use[0].get("rcept_no") or "")[:8]
        if len(stlm) == 8 and stlm.isdigit():
            prev = pts.get(stlm)
            if prev is None or rcept >= prev[1]:
                pts[stlm] = (istc, rcept, f"{e['year']}/{e['reprt']}")
    return sorted((k, v[0], v[2]) for k, v in pts.items())


"""W2 를 판정하려면 창 이후의 주식수를 알아야 한다. forward 스냅샷이 없는 종목은
'변동 없음'이 아니라 '판정 불가' 다 — 🔴 fail-closed 로 SUSPECT 처리한다.
(pykrx 가 예외 없이 n=0 을 돌려줘 죽었던 것과 같은 함정: 없음을 정상으로 읽지 말 것)"""
FORWARD_MIN_STLM = "20240630"

# 🔒 v2 자유모수 — 사전등록 §3 에서 **결과를 보기 전에** 고정된 값이다.
RATIO_MULTIPLES = (2, 3, 4, 5, 10, 20, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10, 1 / 20)
RATIO_TOL = 0.02        # 배수 대비 상대오차 ±2%
RATIO_HI = 2.0
RATIO_LO = 0.5


def change_kind(a, b):
    """연속한 두 보고서의 주식수 a→b 분류. → "none" | "ratio" | "gradual"

    🔒 사전등록(prereg-2026-08-10-mcap-gate-v2 §3)의 세 줄을 그대로 옮긴 것이다.
       r = b / a 일 때
       1. r 이 단순배수(2,3,4,5,10,20 및 그 역수) 중 하나의 ±2% 이내 → 비율성
       2. 아니어도 r >= 2.0 또는 r <= 0.5 → 비율성 (큰 변동은 보수적으로)
       3. 그 외(0.5 < r < 2.0 이면서 단순배수 아님)      → 점진적
       a == b 는 변동 없음.

    🔴 **결과를 보고 이 규칙을 조정하지 않는다.** 조정하면 그건 v3 이고 별도 사전등록이다.
    """
    if a == b:
        return "none"
    if not a or not b:
        return "ratio"      # 판정 불가는 보수적으로 비율성 (fail-closed)
    r = b / a
    if any(abs(r - m) <= RATIO_TOL * m for m in RATIO_MULTIPLES):
        return "ratio"
    if r >= RATIO_HI or r <= RATIO_LO:
        return "ratio"
    return "gradual"


def has_ratio_change_from(tl, i):
    """인덱스 i 이후(i→i+1 부터 끝까지) 어디엔가 비율성 변동이 있는가."""
    return any(change_kind(tl[j][1], tl[j + 1][1]) == "ratio"
               for j in range(i, len(tl) - 1))


def gate_row(tl, ymd, demoted_reason, gate="v1"):
    """→ (shares, gate, report_key, why)

    gate="v1": 주식수가 **바뀌기만 하면** W1/W2 SUSPECT.
    gate="v2": 그 두 조건만 「비율성 변동일 때만」으로 좁힌다(사전등록 §4).
               LEAD·TRAIL·forward fail-closed·W3 강등은 v1 과 **완전히 동일**하다.
    """
    dates = [d for d, _, _ in tl]
    if dates[-1] < FORWARD_MIN_STLM:
        i = bisect_left(dates, ymd)
        i = min(i, len(tl) - 1)
        return tl[i][1], "SUSPECT", tl[i][2], "W2 판정불가(forward 스냅샷 없음)"
    i = bisect_left(dates, ymd)
    if i >= len(tl):
        return tl[-1][1], "SUSPECT", tl[-1][2], "TRAIL(감싸는 보고서 없음)"
    shares, rkey = tl[i][1], tl[i][2]
    if i == 0:
        return shares, "SUSPECT", rkey, "LEAD(직전 보고서 없음)"
    if gate == "v2":
        if change_kind(tl[i - 1][1], shares) == "ratio":
            return shares, "SUSPECT", rkey, "W1 구간내 비율성 변동"
        if has_ratio_change_from(tl, i):
            return shares, "SUSPECT", rkey, "W2 이후 비율성 변동"
    else:
        if tl[i - 1][1] != shares:
            return shares, "SUSPECT", rkey, "W1 구간내 주식수 변동"
        if tl[-1][1] != shares:
            return shares, "SUSPECT", rkey, "W2 이후 주식수 변동"
    if demoted_reason:
        return shares, "SUSPECT", rkey, f"W3 {demoted_reason}"
    return shares, "SAFE_STRICT", rkey, ""


def prepare(cache, window_from, window_to):
    tls = {sc: stlm_timeline(e) for sc, e in cache.items()}
    tls = {sc: t for sc, t in tls.items() if t}
    gaps = {}
    if os.path.exists(GAPS_JSON):
        with open(GAPS_JSON, encoding="utf-8") as f:
            gaps = {k: [tuple(x) for x in v] for k, v in json.load(f).items()}
    tl2 = {sc: [(d, v) for d, v, _ in t] for sc, t in tls.items()}
    demoted, detail = build_guard(tl2, gaps, window_from, window_to)
    return tls, demoted, detail


def fetch_validate_rows(tls):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, date, close, market_cap FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND date >= '2024-01-01' AND date <= '2026-08-06' "
        "AND market_cap > 0 AND close > 0",
        (sorted(tls),))
    rows = cur.fetchall()
    conn.close()
    return rows


def measure(tls, demoted, rows, gate):
    """같은 행 위에서 게이트만 갈아 끼운다. → (cnt, err, why, leak)"""
    err = defaultdict(list)
    cnt = defaultdict(int)
    why = defaultdict(int)
    leak = defaultdict(list)
    for sc, d, close, mcap in rows:
        tl = tls.get(sc)
        if not tl:
            continue
        shares, g, _rk, w = gate_row(tl, d.replace("-", ""), demoted.get(sc), gate)
        e = abs(shares * close - mcap) / mcap
        err[g].append(e)
        cnt[g] += 1
        if g == "SUSPECT":
            why[w] += 1
        elif e > 0.10:
            leak[sc].append(e)
    return cnt, err, why, leak


def metrics(cnt, err, leak):
    """비교표에 올릴 지표. 누수율의 분모는 SAFE 행수(사전등록 §5 기준선과 동일)."""
    a = sorted(err["SAFE_STRICT"])
    tot = sum(cnt.values()) or 1
    n = len(a)
    frac = (lambda t: sum(1 for x in a if x > t) / n * 100) if n else (lambda t: float("nan"))
    return {
        "safe_rows": cnt["SAFE_STRICT"], "tot": tot,
        "safe_share": cnt["SAFE_STRICT"] / tot * 100,
        "leak10_rows": sum(1 for x in a if x > 0.10),
        "leak10": frac(0.10), "leak5": frac(0.05), "leak1": frac(0.01),
        "med": pctl(a, 0.5) * 100, "p90": pctl(a, 0.9) * 100,
        "p99": pctl(a, 0.99) * 100, "max": (a[-1] * 100) if n else float("nan"),
        "leak": leak,
    }


def report_single(tls, demoted, rows, gate, cnt, err, why, leak):
    L = []
    add = L.append
    tag = "" if gate == "v1" else f"({gate})"   # v1 은 기준선 리포트와 바이트 동일하게 둔다
    add(f"=== B(2) 게이트{tag} 사전검증 — A(2) 정답지(2024~2026) 위에서 ===")
    add(f"종목 {len(tls)} / 행 {len(rows):,}")
    add(f"b3 가드 강등 종목: {len(demoted)} {list(demoted)[:10]}")
    add("")
    tot = sum(cnt.values())
    for g in ("SAFE_STRICT", "SUSPECT"):
        add(f"{g}: {cnt[g]:,}행 ({cnt[g]/tot*100:.2f}%)")
        add(dist(f"   {g}", err[g]))
    add("")
    a = sorted(err["SAFE_STRICT"])
    if a:
        n = len(a)
        add("🔴 SAFE_STRICT 누수")
        add(f"   >10%: {sum(1 for x in a if x>0.10)/n*100:.4f}% ({sum(1 for x in a if x>0.10):,}행)"
            f"   >5%: {sum(1 for x in a if x>0.05)/n*100:.4f}%"
            f"   >1%: {sum(1 for x in a if x>0.01)/n*100:.4f}%")
        add(f"   median={pctl(a,0.5)*100:.4f}%  p90={pctl(a,0.9)*100:.4f}%  "
            f"p99={pctl(a,0.99)*100:.4f}%  max={a[-1]*100:.2f}%")
        add(f"   누수 종목: {len(leak)} " +
            str({k: f'{len(v)}행/최대{max(v)*100:.1f}%' for k, v in
                 sorted(leak.items(), key=lambda kv: -len(kv[1]))[:6]}))
    add("")
    add("SUSPECT 사유 분해:")
    for k, v in sorted(why.items(), key=lambda kv: -kv[1]):
        add(f"   {k:34s} {v:8,}행 ({v/tot*100:5.2f}%)")
    return "\n".join(L)


def report_compare(tls, demoted, rows, results):
    """v1·v2 를 **같은 표** 에 올린다. 한쪽만 재고 비교하지 않기 위한 모드."""
    m = {}
    for g in ("v1", "v2"):
        cnt, err, _why, leak = results[g]
        m[g] = metrics(cnt, err, leak)
    L = []
    add = L.append
    add("=== B(2) 게이트 v1 vs v2 — 같은 정답지·같은 행 위에서 동시 측정 ===")
    add(f"종목 {len(tls)} / 행 {len(rows):,} / b3 강등 {len(demoted)}")
    add("")
    add(f"{'지표':<22}{'v1':>14}{'v2':>14}   {'사전등록 §6 기준':<22}{'판정':>6}")
    add("-" * 84)

    def line(label, key, fmt, crit="", ok=None):
        v = f"{m['v1'][key]:{fmt}}", f"{m['v2'][key]:{fmt}}"
        verdict = "" if ok is None else ("PASS" if ok else "🔴FAIL")
        add(f"{label:<22}{v[0]:>14}{v[1]:>14}   {crit:<22}{verdict:>6}")

    line("SAFE 행수", "safe_rows", ",d")
    line("SAFE 비율", "safe_share", ".2f", "G3 >= 57.00",
         m["v2"]["safe_share"] >= PASS_G3_SAFE)
    line("누수 >10%", "leak10", ".4f", "G1 <= 0.3500",
         m["v2"]["leak10"] <= PASS_G1_LEAK10)
    line("누수 >10% (행)", "leak10_rows", ",d")
    line("누수 >5%", "leak5", ".4f")
    line("누수 >1%", "leak1", ".4f", "G2 <= 3.0000",
         m["v2"]["leak1"] <= PASS_G2_LEAK1)
    line("오차 median", "med", ".4f")
    line("오차 p90", "p90", ".4f")
    line("오차 p99", "p99", ".4f")
    line("오차 max", "max", ".2f")
    add("-" * 84)
    add("(SAFE 비율의 분모는 전체 행, 누수율의 분모는 SAFE 행)")
    add("")
    for g in ("v1", "v2"):
        lk = m[g]["leak"]
        add(f"[{g}] 누수(>10%) 종목 {len(lk)}: " +
            str({k: f'{len(v)}행/최대{max(v)*100:.1f}%' for k, v in
                 sorted(lk.items(), key=lambda kv: -len(kv[1]))}))
    add("")
    for g in ("v1", "v2"):
        why, tot = results[g][2], m[g]["tot"]
        add(f"[{g}] SUSPECT 사유 분해:")
        for k, v in sorted(why.items(), key=lambda kv: -kv[1]):
            add(f"   {k:34s} {v:8,}행 ({v/tot*100:5.2f}%)")
        add("")
    verdicts = [("G1 누수>10% <= 0.35", m["v2"]["leak10"] <= PASS_G1_LEAK10, m["v2"]["leak10"]),
                ("G2 누수>1%  <= 3.0", m["v2"]["leak1"] <= PASS_G2_LEAK1, m["v2"]["leak1"]),
                ("G3 SAFE    >= 57.0", m["v2"]["safe_share"] >= PASS_G3_SAFE,
                 m["v2"]["safe_share"])]
    add("🔒 사전등록 §6 판정 (셋 다 통과해야 v2 채택):")
    for name, ok, val in verdicts:
        add(f"   {name:24s} 실측 {val:8.4f}%   {'PASS' if ok else '🔴FAIL'}")
    add(f"   ⇒ 종합: {'v2 채택 가능' if all(o for _, o, _ in verdicts) else '🔴 v2 폐기 — v1 산출물로 간다'}")
    return "\n".join(L)


def run_validate(gate="v1", compare=False):
    cache = load_checkpoints([A2_CHECKPOINT])
    tls, demoted, _detail = prepare(cache, "2024-01-01", "2026-08-06")
    rows = fetch_validate_rows(tls)

    if compare:
        results = {g: measure(tls, demoted, rows, g) for g in ("v1", "v2")}
        txt = report_compare(tls, demoted, rows, results)
        out = COMPARE_REPORT
    else:
        cnt, err, why, leak = measure(tls, demoted, rows, gate)
        txt = report_single(tls, demoted, rows, gate, cnt, err, why, leak)
        out = gate_out_path(VALIDATE_REPORT, gate)
    with open(out, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)
    print(f"\n→ {out}")


def run_emit(gate="v1"):
    cache = load_checkpoints([B1_CHECKPOINT, FWD_CHECKPOINT])
    if not cache:
        raise SystemExit("b1 체크포인트 없음 — 먼저 수집하라")
    tls, demoted, detail = prepare(cache, "2021-01-01", "2023-12-31")
    out_jsonl = gate_out_path(EMIT_JSONL, gate)
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, date, close FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND date >= '2021-01-01' AND date <= '2023-12-31' "
        "AND close > 0 ORDER BY stock_code, date",
        (sorted(tls),))
    rows = cur.fetchall()
    conn.close()

    cnt = defaultdict(int)
    why = defaultdict(int)
    stock_gate = defaultdict(lambda: defaultdict(int))
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for sc, d, close in rows:
            tl = tls.get(sc)
            if not tl:
                continue
            shares, g, rkey, w = gate_row(tl, d.replace("-", ""), demoted.get(sc), gate)
            cnt[g] += 1
            stock_gate[sc][g] += 1
            if g == "SUSPECT":
                why[w] += 1
            f.write(json.dumps({
                "stock_code": sc, "date": d,
                # 🔴 SUSPECT 의 market_cap 은 NULL 이다. 0 금지.
                "market_cap": (shares * close) if g == "SAFE_STRICT" else None,
                "shares": shares if g == "SAFE_STRICT" else None,
                "source": "dart_istc_stlm", "report_key": rkey,
                "gate": g, "reason": w or None,
            }) + "\n")
    tot = sum(cnt.values())
    full = sum(1 for g in stock_gate.values()
               if g.get("SAFE_STRICT", 0) == sum(g.values()))
    print(f"산출 {tot:,}행  SAFE_STRICT {cnt['SAFE_STRICT']:,} "
          f"({cnt['SAFE_STRICT']/tot*100:.2f}%)  SUSPECT {cnt['SUSPECT']:,}")
    print(f"종목 {len(stock_gate)}  전 구간 통과 {full} ({full/len(stock_gate)*100:.1f}%)")
    print(f"b3 가드 강등 종목 {len(demoted)}")
    print("SUSPECT 사유:", dict(sorted(why.items(), key=lambda kv: -kv[1])))
    print(f"→ {out_jsonl}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--gate", choices=("v1", "v2"), default="v1")
    ap.add_argument("--compare", action="store_true",
                    help="--validate 와 함께: v1·v2 를 같은 행 위에서 재서 한 표에 올린다")
    a = ap.parse_args()
    if a.validate:
        run_validate(a.gate, a.compare)
    elif a.emit:
        run_emit(a.gate)
    else:
        ap.error("--validate 또는 --emit")


if __name__ == "__main__":
    main()
