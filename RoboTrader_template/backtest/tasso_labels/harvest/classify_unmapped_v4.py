"""미매핑 이름 227건을 A(표기오류·축약) / B(사명변경) / C(조회불가) / D(판정불가) 로 분류.

🔴 **진단 전용.** `code_map*.json` · `labels_v*.csv` 를 읽기만 하고 **쓰지 않는다.**
🔴 **결과변수(forward 수익률)는 계산하지 않는다.** 세는 것은 「봉이 몇 개 있나」뿐이다.

--------------------------------------------------------------------------------
왜 이 분류가 필요한가
--------------------------------------------------------------------------------
README §생존편향과 PREREG §5.1 은 연도별 손실률(42.4/30.6/22.9/12.8%)을 실으면서
**매핑 실패를 전부 「상폐·사명변경」으로** 읽었다. 그런데 매핑 실패에는
**저자 표기 오류**가 섞여 있다(퓨처켐 -> 퓨쳐켐, 오스템임플란드 -> 오스템임플란트 …).
표기 오류는 생존편향이 아니다 — 데이터는 그대로 있고 이름만 안 맞았다.

--------------------------------------------------------------------------------
증거 채널 (강한 것부터)
--------------------------------------------------------------------------------
E1 **자기쌍(self-pair)**   같은 라벨셋 안에서 저자가 **다른 곳에 올바로 쓴** 이름과 편집거리<=2.
                           (예: 오스템임플란드/오스템임플란트가 **같은 글**에 둘 다 있다)
                           -> 저자 오타의 **직접 증거**. 외부 지식이 필요 없다.
E2 **코드 census**         `daily_prices` 2,606 코드를 네이버에 **코드로** 물어 얻은 현재 이름.
                           접두 조회가 원리적으로 못 보는 **앞에 붙는 사명변경**을 잡는다
                           (효성첨단소재 -> HS효성첨단소재 298050).
E3 **접두 조회 후보**       `probe_unmapped_v4.json`. 접두 매칭이라 10건에서 잘린다.
E4 **로컬 풀**             `stock_list.json`(코스피 마스터) + `namemap_v4.tsv`(DB 이름).

--------------------------------------------------------------------------------
A / B 를 가르는 규칙 (🟡 **휴리스틱임을 명시한다**)
--------------------------------------------------------------------------------
  A-self   E1 자기쌍                                     -> 오타 (가장 강함)
  A-sub    편집거리<=2 · 공통접두>=3 · |길이차|<=2         -> 오타 (칼/컬, 엔/앤, 처/쳐)
  A-append 후보 = 이름 + 뒤에 덧붙음                       -> 저자의 **축약** 표기
  B-pre    후보 = 앞에 붙은 것 + 이름                      -> **사명변경**(그룹 브랜드 부착: HS·롯데·KG·LS·HL)
  B-know   위에 안 걸리지만 코드 동일성이 확인된 사명변경    -> 개별 근거를 `RENAME_TABLE` 에 적는다
  C        어떤 접두에서도 후보 0건 · census 에도 유사 이름 없음
  D        후보가 여럿이라 못 정함 / 유사하지만 규칙 미충족

⚠️ **A 와 B 의 경계는 무르다**(앞에 붙으면 사명변경, 뒤에 붙으면 축약 — 실제 관행이지 법칙이 아니다).
   그래서 **보정 손실률은 A·B 를 합쳐서만** 쓴다. A/B 분리는 「저자의 표기 정확도」 서술에만 쓰고
   그 서술에는 이 무름을 병기한다.
⚠️ **A·B 로 분류해도 라벨을 살리지 않는다.** 복구 가능 행수는 **보고만** 한다(표본 변경은 사장님 결정).
"""
import argparse
import collections
import csv
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"
PRE = FWD = 40          # build_labels_v5.py 와 같은 값
MIN_BARS = 15


# ── 사명변경 표 (E2 로 코드가 확인된 것만. 근거를 반드시 적는다) ────────────────
# 형식: 저자 표기 -> (코드, 현재이름, 근거)
# 🔴 근거는 전부 **코드 조회 실측**이다: q=<code> 가 현재 이름을 돌려주고,
#    그 코드의 daily_prices 가 라벨 시점을 덮는다(= 그 시절 그 이름으로 거래되던 종목).
#    ⚠️ 「옛 이름 X 가 이 코드였다」 자체는 네이버로 확인되지 않는다 -> `추정` 으로 표기한다.
RENAME_TABLE = {}       # 실행 중 E2 매칭으로 채운다 (하드코딩 지식 주입 없음)


def norm(s):
    return "".join(s.split())


def edit(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cpx(a, b):
    return len(os.path.commonprefix([a, b]))


def sql(q):
    env = dict(os.environ, PGPASSWORD="1234")
    open("_qcls.sql", "w", encoding="utf-8").write(q)
    r = subprocess.run([PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "robotrader",
                        "-d", "kis_template", "-tAF\t", "-f", "_qcls.sql"],
                       capture_output=True, env=env)
    err = r.stderr.decode("utf-8", "replace").strip()
    if err:
        print("SQL stderr:", err[:400])
    os.remove("_qcls.sql")
    return r.stdout.decode("utf-8", "replace")


def coverage(pairs):
    """(code, date) -> (bars_pre, bars_post). build_labels_v5.coverage 와 같은 쿼리."""
    out = {}
    pairs = sorted(set(pairs))
    for i in range(0, len(pairs), 400):
        chunk = pairs[i:i + 400]
        vals = ",".join("('{}','{}'::date)".format(c, d) for c, d in chunk)
        q = ("WITH lab(code,d) AS (VALUES " + vals + ") "
             "SELECT lab.code, lab.d, "
             f"count(*) FILTER (WHERE p.date BETWEEN to_char(lab.d-{PRE},'YYYY-MM-DD') "
             "AND to_char(lab.d,'YYYY-MM-DD')) AS pre, "
             "count(*) FILTER (WHERE p.date > to_char(lab.d,'YYYY-MM-DD') "
             f"AND p.date <= to_char(lab.d+{FWD},'YYYY-MM-DD')) AS post "
             "FROM lab LEFT JOIN daily_prices p ON p.stock_code=lab.code "
             f"AND p.date BETWEEN to_char(lab.d-{PRE},'YYYY-MM-DD') "
             f"AND to_char(lab.d+{FWD},'YYYY-MM-DD') GROUP BY 1,2;")
        for line in sql(q).strip().split("\n"):
            p = line.split("\t")
            if len(p) == 4:
                out[(p[0], p[1])] = (int(p[2]), int(p[3]))
    return out


# ── 소스 적재 ────────────────────────────────────────────────────────────────
def load_universe(base, harvest):
    """현재 이름 -> [(code, 출처)] . 같은 이름에 코드가 여럿이면 전부 남긴다."""
    uni = collections.defaultdict(set)

    census = {}
    p = os.path.join(harvest, "codename_census.json")
    if os.path.exists(p):
        census = json.load(open(p, encoding="utf-8"))
        for code, v in census.items():
            if v.get("listed") and v.get("name"):
                uni[norm(v["name"])].add((code, "census"))

    p = os.path.join(harvest, "probe_unmapped_v4.json")
    probes = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    for rec in probes.values():
        for c in rec.get("candidates", []):
            uni[norm(c["name"])].add((c["code"], "probe"))

    master = os.path.join(base, "..", "..", "stock_list.json")
    if os.path.exists(master):
        for s in json.load(open(master, encoding="utf-8"))["stocks"]:
            uni[norm(s["name"])].add((s["code"], "master"))

    p = os.path.join(harvest, "namemap_v4.tsv")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            q = line.rstrip("\n").split("\t")
            if len(q) == 2 and q[0].strip() and q[1].strip():
                uni[norm(q[1])].add((q[0].strip(), "localdb"))
    return uni, census, probes


def load_resolved(base, harvest):
    """저자가 **다른 곳에 올바로 쓴** 이름 (자기쌍 E1 용) -> name -> code."""
    res = {}
    for p in (os.path.join(base, "code_map.json"),
              os.path.join(harvest, "code_map_v4.json"),
              os.path.join(harvest, "code_map_prose.json")):
        if os.path.exists(p):
            for k, v in json.load(open(p, encoding="utf-8")).items():
                res.setdefault(norm(k), v["code"])
    return res


def is_pref(name):
    """우선주 표기."""
    return name.endswith("우") or name.endswith("우B") or name.endswith("우C")


def lcs_len(a, b):
    """최장 공통 **부분문자열** 길이."""
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def near_misses(n, uni, k=4):
    """C·D 로 남은 이름에 대한 **사람 검토용** 근접 후보.

    🔴 자동 분류에 쓰지 않는다. 접두·접미 규칙이 못 보는 사명변경
    (일진머티리얼즈 -> 롯데에너지머티리얼즈: 공통 부분문자열 '머티리얼즈')을
    사람이 판단할 수 있게 **보여만 준다.**
    """
    out = []
    for cn, codes in uni.items():
        if len(cn) < 3:
            continue
        L = lcs_len(n, cn)
        if L >= 4 and L / len(n) >= 0.5:
            code = sorted(codes)[0][0]
            out.append((L / len(n), L, cn, code))
    out.sort(reverse=True)
    return out[:k]


# ── 분류 ─────────────────────────────────────────────────────────────────────
# 티어 -> (우선순위, 최종 분류). `AB` = **복구 가능하나 A/B 를 못 가름**.
# 🔑 **접두 포함 관계를 치환보다 앞에 둔다.** 그러지 않으면 `아이티센` 이
#    올바른 `아이티센글로벌`(접두확장) 대신 `아이티켐`(1글자 치환)에 붙는다 — 실제로 그랬다.
TIER = {
    "EXACT":    (0, "A"),    # 현재 상장명과 글자 그대로 같다 (= 이름 색인 누락)
    "A-self":   (1, "A"),    # 저자가 **다른 라벨에 올바로 쓴** 이름과 1글자 차 -> 오타 직접 증거
    "A-abbr":   (2, "A"),    # 뒤에 1~2자만 덧붙음 -> 저자 축약
    "AB-abbr":  (3, "AB"),   # 뒤에 3자 이상 -> 축약인지 사명변경인지 **못 가름**
    "A-typo":   (4, "A"),    # 편집거리 1
    "A-typo2":  (5, "A"),    # 편집거리 2 (긴 이름에서만)
    "B-pre":    (6, "B"),    # 앞에 <=4자 부착 (HS·KT·HD·롯데…) -> 사명변경 관행
    "B-trunc":  (7, "B"),    # 뒤 <=4자 탈락 -> 사명변경 관행
}


def _tier(n, cn):
    """이름 n 과 현재이름 cn 의 관계를 티어로. 아니면 None.

    🟡 A 와 B 의 경계는 **관행이지 법칙이 아니다**(앞에 붙으면 사명변경, 뒤에 조금 붙으면 축약).
       그래서 3자 이상 덧붙는 경우는 `AB` 로 빼서 **못 가른다고 표시**한다.
    """
    if cn == n:
        return "EXACT"
    d = edit(n, cn)
    dl = abs(len(n) - len(cn))
    if len(n) >= 3 and dl <= 1 and cpx(n, cn) >= 2:
        if d <= 1:
            return "A-typo"
        if d == 2 and len(n) >= 6:            # 짧은 이름의 2글자 차는 딴 회사인 경우가 많다
            return "A-typo2"                  # (하이트론/하이트진로 · 코리아센터/코리아나)
    if len(n) >= 3 and cn.startswith(n):
        return "A-abbr" if len(cn) - len(n) <= 2 else "AB-abbr"
    if len(n) >= 4 and cn.endswith(n) and len(cn) - len(n) <= 4:
        return "B-pre"
    if len(n) >= 5 and n.startswith(cn) and len(cn) >= 4 and len(n) - len(cn) <= 4:
        return "B-trunc"
    return None


def classify(name, uni, resolved, probes):
    n = norm(name)
    ev = []

    # E1 자기쌍 — 저자가 올바로 쓴 이름과 1글자 차 (외부 지식 불필요)
    for rn, code in resolved.items():
        if rn != n and len(n) >= 3 and abs(len(n) - len(rn)) <= 1 \
                and cpx(n, rn) >= 2 and edit(n, rn) <= 1:
            ev.append(("A-self", rn, code, f"저자가 다른 라벨에 올바로 씀(편집거리 1)"))

    # E2~E4 현재 이름 전체 집합과 대조
    for cn, codes in uni.items():
        t = _tier(n, cn)
        if not t:
            continue
        for code, src in codes:
            ev.append((t, cn, code, f"{src}"))

    # 우선주 후보는 보통주 형제가 있으면 버린다
    base_names = {e[1] for e in ev if not is_pref(e[1])}

    def is_pref_dup(nm):
        return is_pref(nm) and any(nm[:-k] in base_names for k in (1, 2))

    ev = [e for e in ev if not is_pref_dup(e[1])]

    if not ev:
        ncand = len(probes.get(name, {}).get("candidates", []))
        return ("C", None, None, f"접두 후보 {ncand}건 · 현재이름 유사 0건", ev)

    ev.sort(key=lambda e: (TIER[e[0]][0], len(e[1])))
    best = ev[0]
    same_tier = [e for e in ev if e[0] == best[0]]
    codes = {e[2] for e in same_tier}
    if len(codes) > 1:
        return ("D", None, None,
                "동급 후보 %d개 경합: %s" % (len(codes),
                                        ", ".join(f"{e[1]}({e[2]})" for e in same_tier[:5])), ev)
    return (TIER[best[0]][1], best[2], best[1], f"{best[0]}({best[3]})", ev)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="../labels_v4.csv")
    ap.add_argument("--extra-labels", default="../labels_v5.csv")
    ap.add_argument("--out-csv", default="unmapped_classified_v4.csv")
    ap.add_argument("--out-json", default="unmapped_classified_v4.json")
    args = ap.parse_args()

    base = ".."
    harvest = "."
    uni, census, probes = load_universe(base, harvest)
    resolved = load_resolved(base, harvest)
    print(f"현재이름 집합 {len(uni)} (census 상장 "
          f"{sum(1 for v in census.values() if v.get('listed'))} / 코드 {len(census)}) · "
          f"저자 확정명 {len(resolved)} · 접두조회 {len(probes)}")

    rows = list(csv.DictReader(open(args.labels, encoding="utf-8-sig")))
    unmapped_rows = [r for r in rows if not r["stock_code"]]
    names = sorted({r["stock_name"] for r in unmapped_rows})
    # v5(산문 편입)에서 새로 생긴 미매핑 이름도 분류해 둔다 — 집계에서 '?' 가 남지 않게.
    if args.extra_labels and os.path.exists(args.extra_labels):
        extra = {r["stock_name"] for r in csv.DictReader(
            open(args.extra_labels, encoding="utf-8-sig")) if not r["stock_code"]}
        names = sorted(set(names) | extra)
    print(f"미매핑 이름 {len(names)} · 미매핑 행 {len(unmapped_rows)}\n")

    out = {}
    for nm in names:
        cls, code, cand, why, ev = classify(nm, uni, resolved, probes)
        out[nm] = {"cls": cls, "code": code, "cand": cand, "why": why,
                   "evidence": [list(e) for e in ev[:8]],
                   "probe_cand": len(probes.get(nm, {}).get("candidates", [])),
                   "probe_saturated": probes.get(nm, {}).get("saturated_any", False)}
        if cls in ("C", "D"):
            out[nm]["near"] = [list(x) for x in near_misses(norm(nm), uni)]

    # 복구 가능성 — 봉 수만 센다 (🔴 수익률·forward 는 계산하지 않는다)
    bar_rows = list(unmapped_rows)
    if args.extra_labels and os.path.exists(args.extra_labels):
        seen = {(r["stock_name"], r["post_date"]) for r in unmapped_rows}
        for r in csv.DictReader(open(args.extra_labels, encoding="utf-8-sig")):
            if not r["stock_code"] and (r["stock_name"], r["post_date"]) not in seen:
                bar_rows.append(r)
    pairs = [(out[r["stock_name"]]["code"], r["post_date"])
             for r in bar_rows if out.get(r["stock_name"], {}).get("code")]
    cov = coverage(pairs) if pairs else {}
    for r in bar_rows:
        o = out.get(r["stock_name"])
        if o and o["code"]:
            pre, post = cov.get((o["code"], r["post_date"]), (0, 0))
            o.setdefault("bars", {})[r["post_date"]] = (pre, post)

    with open(args.out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock_name", "class", "cand_code", "cand_name", "evidence",
                    "n_labels", "years", "probe_cands", "probe_saturated",
                    "recoverable_rows"])
        cnt = collections.Counter(r["stock_name"] for r in unmapped_rows)
        yrs = collections.defaultdict(collections.Counter)
        for r in unmapped_rows:
            yrs[r["stock_name"]][r["post_date"][:4]] += 1
        for nm in names:
            o = out[nm]
            rec = 0
            for r in unmapped_rows:
                if r["stock_name"] != nm or not o["code"]:
                    continue
                pre, post = o.get("bars", {}).get(r["post_date"], (0, 0))
                rec += int(pre >= MIN_BARS and post >= MIN_BARS)
            o["recoverable_rows"] = rec
            w.writerow([nm, o["cls"], o["code"] or "", o["cand"] or "", o["why"],
                        cnt[nm], ";".join(f"{y}:{c}" for y, c in sorted(yrs[nm].items())),
                        o["probe_cand"], o["probe_saturated"], rec])

    json.dump(out, open(args.out_json, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    c = collections.Counter(o["cls"] for o in out.values())
    print("이름 기준 분류:", dict(c))
    rowc = collections.Counter(out[r["stock_name"]]["cls"] for r in unmapped_rows)
    print("행 기준 분류:", dict(rowc))
    print("->", args.out_csv, "/", args.out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
