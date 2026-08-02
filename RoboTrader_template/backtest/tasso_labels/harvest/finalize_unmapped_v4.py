"""미매핑 227(+v5 16) 이름의 **최종 분류**. 세 채널을 합치고 **전부 기계 재검증**한다.

채널 (독립 3개)
  ① 같은 글 오타쌍   같은 `logNo` 안에 **매핑된 올바른 표기**가 함께 있다 -> 저자 오타의 직접 증거
  ② 문자열 증거      `classify_unmapped_v4.py` (코드 census + 접두조회 + 로컬풀 대조)
  ③ 웹 조사          에이전트 3본. 🔴 **자기보고를 그대로 쓰지 않는다** — 아래 V1~V3 를 통과해야 채택

기계 재검증
  V1 `ac?q=<code>` 가 그 코드를 돌려주는가  -> **현재 이름** 또는 **미색인(상폐 추정)**
  V2 에이전트가 적은 현재 이름이 V1 과 같은가 -> 다르면 주장 신뢰도 강등
  V3 그 코드의 `daily_prices` 가 라벨 날짜 전후를 덮는가 (봉 >= 15/15) -> **복구 가능 여부**

분류 정의 (🔑 **「왜 매핑이 실패했나」가 아니라 「지금 그 회사가 있나」로 가른다**)
  A  현재 상장돼 있고, 저자 표기가 현재 이름의 오타·축약
  B  현재 상장돼 있고, 저자 표기는 그 시절 정식 이름 (사명변경)
  C  현재 상장 안 됨 (상폐·합병소멸)                     <- **이것만 생존편향**
  D  코드를 못 정함
⚠️ A 와 C 는 배타적이지 않다 — `오스템임플란드`(오타)의 회사는 2023 자진상폐라 **C 로 넣고**
   오타였음을 `note` 에 남긴다. 라벨 복구 가능성은 결국 데이터 유무(V3)가 정한다.
"""
import argparse
import collections
import csv
import io
import json
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"
PRE = FWD = 40
MIN_BARS = 15


# ── 사람이 개별 확인해 뒤집은 판정 (독립 검토 지적 → 관리자 실측으로 확정) ──────────
# 형식: 이름 -> (분류, 코드 or None, 근거). **근거 없는 항목을 넣지 말 것.**
OVERRIDE = {
    # 저자 본문에 **117,400원**이 두 번 적혀 있다(`text/20240826_223560889282.txt`).
    # 2024-08-26 시세: 237690 에스티팜 109,600~119,800 / 122640 예스티 15,600~16,270 (7.3배 차)
    # ⇒ `예스티팜` 은 「예스티」의 축약이 아니라 **「에스티팜」의 오타**다.
    # (README §v3 이 *「예스티 vs 에스티팜 경합」* 이라 적고 매핑을 보류했던 바로 그 건 —
    #  경합은 본문 절대가로 풀린다.)
    "예스티팜": ("A", "237690", "본문 117,400원 = 에스티팜(237690) 당일 저가~고가 안, 예스티는 7.3배 밖"),
    # 「이루다」는 네이버 이름조회 미색인이고 「이루온(065440)」은 **별개의 생존 회사**다.
    # 문자열 1글자 차이만으로 붙였던 것 -> 코드 근거 없음 ⇒ 판정 불가로 되돌린다.
    "이루다": ("D", None, "이루온(065440)은 별개 회사. 이 이름의 코드를 어느 채널도 대지 못함"),
}


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


def similar(a, b):
    """저자 표기 a 와 현재 이름 b 가 「같은 이름의 **표기 차이**」로 볼 만한가.

    🔴 초판은 `편집거리<=2 & 길이차<=2` 만 봤다가 **두 글자 이름이 전부 통과**했다:
       광림/안랩 · 바올/금양 · 삼본전자/아남전자 · 피비파마/한국파마 가 A 로 붙었다.
       공통접두 조건과 최소길이 조건을 넣어 막는다.
    🟡 앞에 글자가 붙는 것(HS효성첨단소재·KT지니뮤직)은 **표기 차이가 아니라 사명변경 관행**이라
       여기서 False 를 돌려주고 B 로 보낸다. 뒤에 <=2자 덧붙는 것만 저자 축약(A)으로 본다.
    """
    a, b = norm(a), norm(b)
    if a == b:
        return True
    if len(a) < 3 or len(b) < 2:
        return False                                  # 2자 이름은 이 방법으로 판정 불가
    d = edit(a, b)
    dl = abs(len(a) - len(b))
    cp = len(os.path.commonprefix([a, b]))
    if d == 1 and dl <= 1 and (cp >= 1 or len(a) >= 4):
        return True                                   # 이렌텍/이랜텍, 태경케미칼/태경케미컬
    if d == 2 and dl <= 1 and cp >= 2 and min(len(a), len(b)) >= 5:
        return True                                   # LG헬로지번/LG헬로비전
    return b.startswith(a) and len(b) - len(a) <= 2    # 저자 축약 (아즈텍/아즈텍WB)


def sql(q):
    env = dict(os.environ, PGPASSWORD="1234")
    open("_qfin.sql", "w", encoding="utf-8").write(q)
    r = subprocess.run([PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "robotrader",
                        "-d", "kis_template", "-tAF\t", "-f", "_qfin.sql"],
                       capture_output=True, env=env)
    err = r.stderr.decode("utf-8", "replace").strip()
    if err:
        print("SQL stderr:", err[:400])
    os.remove("_qfin.sql")
    return r.stdout.decode("utf-8", "replace")


def coverage(pairs):
    out = {}
    pairs = sorted(set(pairs))
    for i in range(0, len(pairs), 400):
        vals = ",".join("('{}','{}'::date)".format(c, d) for c, d in pairs[i:i + 400])
        q = ("WITH lab(code,d) AS (VALUES " + vals + ") SELECT lab.code, lab.d, "
             f"count(*) FILTER (WHERE p.date BETWEEN to_char(lab.d-{PRE},'YYYY-MM-DD') "
             "AND to_char(lab.d,'YYYY-MM-DD')), "
             "count(*) FILTER (WHERE p.date > to_char(lab.d,'YYYY-MM-DD') "
             f"AND p.date <= to_char(lab.d+{FWD},'YYYY-MM-DD')) "
             "FROM lab LEFT JOIN daily_prices p ON p.stock_code=lab.code "
             f"AND p.date BETWEEN to_char(lab.d-{PRE},'YYYY-MM-DD') "
             f"AND to_char(lab.d+{FWD},'YYYY-MM-DD') GROUP BY 1,2;")
        for line in sql(q).strip().split("\n"):
            p = line.split("\t")
            if len(p) == 4:
                out[(p[0], p[1])] = (int(p[2]), int(p[3]))
    return out


def by_code(code, cache):
    """코드 -> {'listed':bool,'name':str}. census 를 1차로 쓰고 없으면 네이버에 묻는다."""
    if code in cache:
        return cache[code]
    url = "https://ac.stock.naver.com/ac?q=" + code + "&target=stock"
    r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace")).get("items", [])
    except Exception:
        return None
    hit = [i for i in items if i.get("code") == code and i.get("nationCode") == "KOR"]
    cache[code] = {"listed": bool(hit), "name": hit[0]["name"] if hit else ""}
    time.sleep(1.0)
    return cache[code]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default="web_claims.tsv")
    ap.add_argument("--mech", default="unmapped_classified_v4.json")
    ap.add_argument("--out", default="unmapped_final_v4.csv")
    ap.add_argument("--out-json", default="unmapped_final_v4.json")
    args = ap.parse_args()

    mech = json.load(open(args.mech, encoding="utf-8"))
    cache = {}
    if os.path.exists("codename_census.json"):
        for k, v in json.load(open("codename_census.json", encoding="utf-8")).items():
            if v.get("listed") is not None:
                cache[k] = {"listed": bool(v["listed"]), "name": v.get("name", "")}
    print(f"census {len(cache)} · 기계분류 {len(mech)}")

    claims = collections.defaultdict(list)
    for line in open(args.claims, encoding="utf-8"):
        p = [x.strip() for x in line.rstrip("\n").split("\t")]
        if len(p) >= 5 and p[0]:
            claims[p[0]].append({"cls": p[1], "code": p[2], "cur": p[3],
                                 "conf": p[4], "src": p[5] if len(p) > 5 else ""})

    # ── 라벨 행·같은 글 오타쌍 ────────────────────────────────────────────────
    rows4 = list(csv.DictReader(open("../labels_v4.csv", encoding="utf-8-sig")))
    rows5 = list(csv.DictReader(open("../labels_v5.csv", encoding="utf-8-sig")))
    allrows = rows4 + [r for r in rows5
                       if (r["stock_name"], r["post_date"]) not in
                       {(x["stock_name"], x["post_date"]) for x in rows4}]
    bylog = collections.defaultdict(set)
    for r in allrows:
        if r["stock_code"]:
            bylog[r["logNo"]].add((r["stock_name"], r["stock_code"]))
    samepost = {}
    for r in allrows:
        if r["stock_code"]:
            continue
        for nm, cd in bylog[r["logNo"]]:
            if similar(r["stock_name"], nm) and r["stock_name"] != nm:
                samepost[r["stock_name"]] = (cd, nm)

    dates = collections.defaultdict(list)
    for r in allrows:
        if not r["stock_code"]:
            dates[r["stock_name"]].append(r["post_date"])
    names = sorted(dates)
    print(f"미매핑 고유 이름 {len(names)} · 같은 글 오타쌍 {len(samepost)}")

    # ── 코드 후보 결정 ───────────────────────────────────────────────────────
    out = {}
    for nm in names:
        cands = []
        if nm in samepost:
            cands.append(("동일글오타쌍", samepost[nm][0], samepost[nm][1], "high"))
        for c in claims.get(nm, []):
            if c["code"].isdigit() and len(c["code"]) == 6:
                cands.append(("웹:" + c["src"], c["code"], c["cur"], c["conf"]))
        m = mech.get(nm, {})
        if m.get("code"):
            cands.append(("문자열", m["code"], m.get("cand", ""), "mech"))
        out[nm] = {"cands": cands}

    # ── V1·V2 ────────────────────────────────────────────────────────────────
    for nm, o in out.items():
        ver = []
        for src, code, claimed, conf in o["cands"]:
            info = by_code(code, cache)
            if info is None:
                ver.append({"src": src, "code": code, "claimed": claimed, "conf": conf,
                            "v1": "조회실패", "cur": "", "v2": ""})
                continue
            ver.append({"src": src, "code": code, "claimed": claimed, "conf": conf,
                        "v1": "상장" if info["listed"] else "미색인",
                        "cur": info["name"],
                        "v2": ("일치" if norm(info["name"]) == norm(claimed)
                               else "불일치") if claimed else ""})
        o["ver"] = ver

    # ── V3 봉 수 (OVERRIDE 로 새로 들어온 코드도 포함해야 한다) ────────────────
    pairs = [(v["code"], d) for nm, o in out.items() for v in o["ver"]
             for d in dates[nm]]
    for nm, (_c, ocode, _r) in OVERRIDE.items():
        if ocode and nm in dates:
            pairs += [(ocode, d) for d in dates[nm]]
    cov = coverage(pairs) if pairs else {}

    # ── 최종 분류 ────────────────────────────────────────────────────────────
    for nm, o in out.items():
        # 코드 득표: 서로 다른 채널이 같은 코드를 가리키면 신뢰도가 오른다
        votes = collections.Counter(v["code"] for v in o["ver"])
        chosen, tier, note = None, "", ""
        if votes:
            top, n = votes.most_common(1)[0]
            multi = [c for c, k in votes.items() if k == n]
            if len(multi) > 1:
                # 채널마다 코드가 다르다 -> 오타쌍 > 웹 high > 문자열 순으로 채택
                pri = {"동일글오타쌍": 0, "웹": 1, "문자열": 2}
                o["ver"].sort(key=lambda v: (pri.get(v["src"].split(":")[0], 3),
                                             0 if v["conf"] == "high" else 1))
                top = o["ver"][0]["code"]
                note = "채널간 코드 불일치(" + ",".join(sorted(votes)) + ")"
            chosen = top
            srcs = sorted({v["src"] for v in o["ver"] if v["code"] == chosen})
            tier = "+".join(srcs)
        v = next((x for x in o["ver"] if x["code"] == chosen), None)

        if not chosen:
            wc = [c for c in claims.get(nm, []) if c["cls"] == "C"]
            if wc:
                cls, why = "C", "웹: 상폐 서술 (코드 미확인)"
            else:
                mc = mech.get(nm, {})
                cls = "D"
                why = mc.get("why", "후보 없음")
                if mc.get("cls") == "C":
                    why = "어느 채널도 코드를 못 냄 · " + why
        elif v["v1"] == "미색인":
            cls = "C"
            why = f"코드 {chosen} 네이버 미색인 = 현재 미상장"
            if nm in samepost:
                note = (note + " / " if note else "") + f"오타(정타 「{samepost[nm][1]}」 동일 글)"
        elif v["v1"] == "상장":
            cls = "A" if similar(nm, v["cur"]) else "B"
            why = f"코드 {chosen} 현재 「{v['cur']}」"
            if cls == "A" and norm(nm) == norm(v["cur"]):
                why += " 🔴 이름 동일 — 정확일치가 실패했어야 할 이유 없음(파이프라인 이상)"
        else:
            cls, why = "D", "코드 조회 실패"

        # 확신도 — 독립 채널이 몇 개나 같은 코드를 가리켰는가
        nch = len({x["src"].split(":")[0] for x in o["ver"] if x["code"] == chosen})
        if not chosen:
            conf = "없음"
        elif nch >= 2:
            conf = "high(채널 %d)" % nch
        elif o["ver"] and o["ver"][0]["src"].startswith("웹"):
            conf = "mid(웹 단독)"
        elif chosen and any(x["src"] == "동일글오타쌍" for x in o["ver"]):
            conf = "mid(동일글 단독)"
        else:
            conf = "🟡low(문자열 단독)"

        if nm in OVERRIDE:                       # 사람이 개별 확인해 뒤집은 판정
            cls, ocode, oreason = OVERRIDE[nm]
            chosen = ocode
            why = "OVERRIDE: " + oreason
            conf = "high(사람 실측)" if ocode else "없음(사람 판단)"
            info = by_code(ocode, cache) if ocode else None
            v = {"cur": info["name"] if info else ""}

        rec = 0
        for d in dates[nm]:
            pre, post = cov.get((chosen, d), (0, 0)) if chosen else (0, 0)
            rec += int(pre >= MIN_BARS and post >= MIN_BARS)
        o.update({"conf": conf,
                  "cls": cls, "code": chosen or "", "cur": v["cur"] if v else "",
                  "why": why, "tier": tier, "note": note, "recoverable": rec,
                  "mech": mech.get(nm, {}).get("cls", ""),
                  "web": ",".join(sorted({c["cls"] for c in claims.get(nm, [])})),
                  "bars": {d: cov.get((chosen, d), (0, 0)) for d in dates[nm]} if chosen else {}})

    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock_name", "final_class", "code", "current_name", "n_labels",
                    "years", "confidence", "evidence", "why", "note", "mech_class",
                    "web_class", "channels_agree", "recoverable_rows"])
        for nm in names:
            o = out[nm]
            ys = collections.Counter(d[:4] for d in dates[nm])
            ag = ""
            if o["mech"] and o["web"] and o["web"] != "?":
                ag = "O" if o["mech"][0] == o["web"][0] else "X"
            w.writerow([nm, o["cls"], o["code"], o["cur"], len(dates[nm]),
                        ";".join(f"{y}:{k}" for y, k in sorted(ys.items())),
                        o["conf"], o["tier"], o["why"], o["note"], o["mech"],
                        o["web"], ag, o["recoverable"]])
    json.dump(out, open(args.out_json, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    c = collections.Counter(o["cls"] for o in out.values())
    print("\n이름 기준 최종 분류:", dict(c))
    rc = collections.Counter()
    for nm, o in out.items():
        rc[o["cls"]] += len(dates[nm])
    print("행 기준(v4+v5 합집합):", dict(rc))
    print("->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
