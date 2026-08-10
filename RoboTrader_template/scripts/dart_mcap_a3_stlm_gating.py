"""A(3) 결산일 기준 최선식 + 「정답지 없이」 사건 분기 게이팅 측정.

읽기 전용(DB SELECT + 로컬 체크포인트). DART 재호출 없음.

(2) 날짜 규약 정정
  이 백필은 신호 생성이 아니라 **과거 사실의 복원**이다. 2021-03-15 의 상장주식수는
  그날 이미 공개된 사실이고, 그 날짜를 감싸는 결산기 보고서로 그 사실을 알아내는 것은
  look-ahead 가 아니다. 금지할 것은 **미래 사건을 과거 날짜에 적용**하는 것뿐이다.
    - 접수일(rcept) 기준 : rcept_dt <= D 인 최근 보고서   (기존, 최대 ~5개월 지연)
    - 결산일(stlm) 기준  : stlm_dt >= D 인 최초 보고서    (D 를 감싸는 결산기의 期末 값)

(3) 정답지 없는 게이팅
  D 를 감싸는 구간의 **시작 보고서(직전 stlm)와 끝 보고서(감싸는 stlm)** 의 주식수가
  같으면 그 구간엔 사건이 없다 → SAFE. 다르면 사건 구간 → SUSPECT.
  이 판정에 실측 market_cap 은 쓰이지 않으므로 2021~23 에도 그대로 적용 가능하다.
  핵심 질문은 "SAFE 로 분류된 행에 큰 오차가 새어 들어오는가" 다.

usage:
  PYTHONUTF8=1 python scripts/dart_mcap_a3_stlm_gating.py
"""
import json
import os
import sys
from bisect import bisect_left
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import OUT_DIR, db_conn, parse_num  # noqa: E402
from dart_mcap_a2_variants import classify, dist, pctl  # noqa: E402

CHECKPOINT_JSONL = os.path.join(OUT_DIR, "a2_dart_checkpoint.jsonl")
REPORT = os.path.join(OUT_DIR, "a3_report.txt")
DATE_FROM = "2024-01-01"
DATE_TO = "2026-08-06"


def build_both_timelines(cache):
    """stock_code → {'rcept': [(rcept_dt, istc)], 'stlm': [(stlm_dt, istc)]} 오름차순."""
    out = {}
    for sc, entries in cache.items():
        rc_pts, st_pts = {}, {}
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
            rcept = (use[0].get("rcept_no") or "")[:8]
            stlm = (use[0].get("stlm_dt") or "").replace("-", "")
            if len(rcept) == 8 and rcept.isdigit():
                prev = rc_pts.get(rcept)
                if prev is None or stlm >= prev[1]:
                    rc_pts[rcept] = (istc, stlm)
            if len(stlm) == 8 and stlm.isdigit():
                # 같은 결산기의 정정 보고서는 나중 접수분 채택
                prev = st_pts.get(stlm)
                if prev is None or rcept >= prev[1]:
                    st_pts[stlm] = (istc, rcept)
        if rc_pts and st_pts:
            out[sc] = {
                "rcept": sorted((k, v[0]) for k, v in rc_pts.items()),
                "stlm": sorted((k, v[0]) for k, v in st_pts.items()),
            }
    return out


def lookup_rcept(tl, ymd):
    """rcept_dt <= ymd 인 최근 값."""
    best = None
    for d, v in tl:
        if d <= ymd:
            best = v
        else:
            break
    return best


def lookup_stlm(tl, ymd):
    """ymd 를 감싸는 결산기: stlm_dt >= ymd 인 최초 보고서.

    반환 (value, gate) — gate ∈ {SAFE, SUSPECT, TRAIL, LEAD}
      SAFE    : 직전 stlm 과 감싸는 stlm 의 주식수가 같다 = 그 구간에 사건 없음
      SUSPECT : 다르다 = 사건 구간
      TRAIL   : ymd 가 마지막 stlm 보다 뒤 = 감싸는 보고서가 아직 없음(미래 미제출).
                2021~23 백필에서는 발생하지 않는다(당시 이후 보고서가 이미 존재).
      LEAD    : ymd 가 첫 stlm 보다 앞 = 직전 보고서가 표본에 없음(수집 범위 문제)
    """
    dates = [d for d, _ in tl]
    i = bisect_left(dates, ymd)
    if i >= len(tl):
        return tl[-1][1], "TRAIL", "TRAIL"
    val = tl[i][1]
    if i == 0:
        return val, "LEAD", "LEAD"
    gate = "SAFE" if tl[i - 1][1] == val else "SUSPECT"
    # STRICT: 감싸는 구간부터 **최신 보고서까지** 주식수가 한 번도 안 변했는가.
    #   느슨한 SAFE 는 구간 내 사건만 본다. 그러나 D 이후의 분할·병합은 close 를
    #   후방조정해 **과거 행의 기준계를 바꾼다** — DART 는 그 시점 값이 옳으므로
    #   구간 내 비교로는 절대 안 잡힌다. 그래서 뒤쪽 전체를 함께 본다.
    strict = "SAFE_STRICT" if len({v for _, v in tl[i - 1:]}) == 1 else "SUSPECT_STRICT"
    return val, gate, strict


def main():
    cache = {}
    with open(CHECKPOINT_JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                cache[r["stock_code"]] = r["entries"]
    tl = build_both_timelines(cache)
    codes = sorted(cache)

    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, date, close, market_cap FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND date >= %s AND date <= %s "
        "AND market_cap > 0 AND close > 0 ORDER BY stock_code, date",
        (codes, DATE_FROM, DATE_TO),
    )
    db_rows = cur.fetchall()
    cur.execute(
        "SELECT DISTINCT stock_code FROM daily_prices "
        "WHERE stock_code = ANY(%s) AND adj_factor IS NOT NULL AND adj_factor <> 1",
        (codes,))
    ever_ca = {r[0] for r in cur.fetchall()}
    conn.close()

    dart_changed = {sc for sc in tl if len({v for _, v in tl[sc]["stlm"]}) > 1}

    err_rcept, err_stlm = [], []
    seg_r = defaultdict(list)
    seg_s = defaultdict(list)
    gate_err = defaultdict(list)
    gate_rows = defaultdict(int)
    gate_stock_rows = defaultdict(lambda: defaultdict(int))
    leak_examples = defaultdict(list)
    strict_err = defaultdict(list)
    strict_rows = defaultdict(int)
    strict_stock = defaultdict(lambda: defaultdict(int))
    strict_leak = defaultdict(list)
    total_rows = 0
    skipped = 0

    def seg_of(sc):
        if sc in ever_ca:
            return "분할O"
        return "분할X·주식수변동O" if sc in dart_changed else "분할X·주식수변동X"

    for sc, d, close, mcap in db_rows:
        t = tl.get(sc)
        if not t:
            continue
        total_rows += 1
        ymd = d.replace("-", "")
        vr = lookup_rcept(t["rcept"], ymd)
        vs, gate, strict = lookup_stlm(t["stlm"], ymd)
        if vr is None:
            skipped += 1
        else:
            e = abs(vr * close - mcap) / mcap
            err_rcept.append(e)
            seg_r[seg_of(sc)].append(e)
        es = abs(vs * close - mcap) / mcap
        err_stlm.append(es)
        seg_s[seg_of(sc)].append(es)
        gate_err[gate].append(es)
        gate_rows[gate] += 1
        gate_stock_rows[sc][gate] += 1
        if gate == "SAFE" and es > 0.10:
            leak_examples[sc].append((d, es))
        strict_err[strict].append(es)
        strict_rows[strict] += 1
        strict_stock[sc][strict] += 1
        if strict == "SAFE_STRICT" and es > 0.10:
            strict_leak[sc].append((d, es))

    L = []
    add = L.append
    add("=== A(3) 결산일 기준 최선식 + 정답지 없는 사건 게이팅 ===")
    add(f"표본 {len(codes)}종목 / 비교행 {total_rows:,} / 접수일 기준 계산불가 {skipped:,}")
    add(f"분할·병합 종목(adj_factor IS NOT NULL AND <>1): {len(ever_ca)}/{len(codes)}")
    add(f"DART 상장주식수가 창 안에서 변한 종목: {len(dart_changed)}/{len(tl)}")
    add("")
    add("--- (2) 날짜 규약 비교 (식 = istc_totqy x close) ---")
    add(dist("접수일 기준(look-ahead 방지)", err_rcept))
    add(dist("결산일 기준(감싸는 결산기)", err_stlm))
    add("")
    add("--- (2) 세그먼트별 ---")
    for seg in ("분할X·주식수변동X", "분할X·주식수변동O", "분할O"):
        n_st = len({sc for sc in tl if seg_of(sc) == seg})
        add(f"[{seg}] {n_st}종목")
        add(dist("   접수일", seg_r[seg]))
        add(dist("   결산일", seg_s[seg]))
    add("")
    add("--- (3) 정답지 없는 게이팅 (결산일 식 기준) ---")
    add(f"{'게이트':<10}{'행수':>10}{'행%':>9}   오차분포")
    for g in ("SAFE", "SUSPECT", "TRAIL", "LEAD"):
        if not gate_rows[g]:
            continue
        add(f"{g:<10}{gate_rows[g]:>10,}{gate_rows[g]/total_rows*100:>8.2f}%")
        add(dist(f"   {g}", gate_err[g]))
    add("")

    safe_a = sorted(gate_err["SAFE"])
    if safe_a:
        n = len(safe_a)
        add("🔴 핵심: SAFE 로 분류된 행의 오차 누수")
        add(f"   >10%: {sum(1 for x in safe_a if x>0.10)/n*100:.4f}%  "
            f"({sum(1 for x in safe_a if x>0.10):,}행)")
        add(f"   > 5%: {sum(1 for x in safe_a if x>0.05)/n*100:.4f}%  "
            f"> 1%: {sum(1 for x in safe_a if x>0.01)/n*100:.4f}%")
        add(f"   median={pctl(safe_a,0.5)*100:.4f}%  p99={pctl(safe_a,0.99)*100:.4f}%  "
            f"max={safe_a[-1]*100:.2f}%")
    add("")
    if leak_examples:
        add(f"누수 종목 {len(leak_examples)}개 — 상위 5:")
        for sc, ex in sorted(leak_examples.items(), key=lambda kv: -len(kv[1]))[:5]:
            worst = max(e for _, e in ex)
            add(f"   {sc}: {len(ex)}행 누수, 최대 {worst*100:.2f}%, "
                f"분할{'O' if sc in ever_ca else 'X'} "
                f"DART변동{'O' if sc in dart_changed else 'X'} 예시일 {ex[0][0]}")
    else:
        add("누수 종목 없음")
    add("")

    # 커버리지 — SAFE 만 채운다고 했을 때
    safe_rows = gate_rows["SAFE"]
    full_safe = sum(1 for sc, g in gate_stock_rows.items()
                    if g.get("SAFE", 0) == sum(g.values()))
    any_safe = sum(1 for sc, g in gate_stock_rows.items() if g.get("SAFE", 0) > 0)
    add("--- (3) SAFE 만 채웠을 때 커버리지 (2024~2026 실측) ---")
    add(f"   행 기준   : {safe_rows:,}/{total_rows:,} = {safe_rows/total_rows*100:.2f}%")
    add(f"   전 구간 SAFE 인 종목: {full_safe}/{len(gate_stock_rows)} "
        f"({full_safe/len(gate_stock_rows)*100:.1f}%)")
    add(f"   SAFE 행이 하나라도 있는 종목: {any_safe}/{len(gate_stock_rows)} "
        f"({any_safe/len(gate_stock_rows)*100:.1f}%)")
    add(f"   ※ TRAIL {gate_rows['TRAIL']:,}행({gate_rows['TRAIL']/total_rows*100:.2f}%) 은 "
        "'감싸는 보고서가 아직 미제출' 이라 오늘 시점에만 생긴다.")
    add("     2021~23 백필에는 해당 구간 이후 보고서가 이미 존재하므로 TRAIL 이 없다")
    add("     → 2021~23 실제 커버리지는 위 행% 보다 높을 것으로 **추정**(B단계 전 확정 불가).")
    add(f"   TRAIL 제외 시 행 커버리지: "
        f"{safe_rows/(total_rows-gate_rows['TRAIL'])*100:.2f}%")
    add("")

    # --- 게이트 강화: D 이후 전 구간 주식수 불변까지 요구 ---
    add("--- (3b) 강화 게이트: 감싸는 구간 ~ 최신 보고서까지 주식수 불변 ---")
    add("   (느슨한 SAFE 는 D 이후의 분할·병합이 close 를 후방조정해 생기는")
    add("    기준계 오염을 원리상 못 잡는다 — DART 는 그 시점 값이 옳기 때문)")
    for g in ("SAFE_STRICT", "SUSPECT_STRICT", "TRAIL", "LEAD"):
        if not strict_rows[g]:
            continue
        add(f"{g:<16}{strict_rows[g]:>10,}{strict_rows[g]/total_rows*100:>8.2f}%")
        add(dist(f"   {g}", strict_err[g]))
    ss = sorted(strict_err["SAFE_STRICT"])
    if ss:
        n = len(ss)
        add("")
        add("🔴 강화 게이트의 누수")
        add(f"   >10%: {sum(1 for x in ss if x>0.10)/n*100:.4f}%  "
            f"({sum(1 for x in ss if x>0.10):,}행)   "
            f"> 5%: {sum(1 for x in ss if x>0.05)/n*100:.4f}%   "
            f"> 1%: {sum(1 for x in ss if x>0.01)/n*100:.4f}%")
        add(f"   median={pctl(ss,0.5)*100:.4f}%  p90={pctl(ss,0.9)*100:.4f}%  "
            f"p99={pctl(ss,0.99)*100:.4f}%  max={ss[-1]*100:.2f}%")
        add(f"   커버리지(행): {strict_rows['SAFE_STRICT']:,}/{total_rows:,} = "
            f"{strict_rows['SAFE_STRICT']/total_rows*100:.2f}%")
        full = sum(1 for sc, g in strict_stock.items()
                   if g.get("SAFE_STRICT", 0) == sum(g.values()))
        add(f"   전 구간 통과 종목: {full}/{len(strict_stock)} "
            f"({full/len(strict_stock)*100:.1f}%)")
        if strict_leak:
            add(f"   누수 종목 {len(strict_leak)}개 — 상위 5:")
            for sc, ex in sorted(strict_leak.items(), key=lambda kv: -len(kv[1]))[:5]:
                add(f"      {sc}: {len(ex)}행, 최대 {max(e for _,e in ex)*100:.2f}%, "
                    f"분할{'O' if sc in ever_ca else 'X'} "
                    f"DART변동{'O' if sc in dart_changed else 'X'}")

    txt = "\n".join(L)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
