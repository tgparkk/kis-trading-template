"""labels_v5 = labels_v4 + **산문 전용 진입**(prose) 편입.

🔴 결과변수(forward 수익률·성과)는 계산하지 않는다. DB 조회는 v4 와 **동일한 두 가지**만:
   (a) 게시일 ±40역일의 거래일 수(`bars_pre`/`bars_post`)  (b) 그 해 `daily_prices` 행 존재(`in_db_year`)
   `usable` 정의도 v4 그대로(`code 있음 && pre>=15 && post>=15`). **새 기준을 만들지 않는다.**

## 왜 편입하나 — 회수율이 아니라 편향

> *"이외 그리드위즈 진입하였으나 **본전으로 차트 미첨부**합니다"* (2024-08-20)

구조화 보고(수익률 줄)에서 빠지는 거래는 **결과가 밋밋한 쪽으로 치우친다.** 구조화분만 쓰면
라벨셋이 「그가 언급할 만하다고 본 거래」로 편향된다. 결과는 우리가 DB 에서 재므로 넣는 것이 맞다.
(지난 라운드에 같은 이유로 제목 전용 7건을 편입해 151→160 으로 갔다.)

## 편입 기준 (관리자 판정)

🔑 **라벨의 기준은 「그가 골랐는가」이지 「그가 체결됐는가」가 아니다.**
라벨 단계에서 체결 조건화를 다시 들이면 5차 GATE_FAIL 의 「체결 조건화」 교훈을 정면으로 어긴다.
⇒ `role=entry`(진입 문장) + `role=order_placed`(2021-10-25 두산중공업, 주문은 넣었고 미체결) 만 편입.
   `notrade`(지켜만 봄·패스·매수가 미도달)는 **선별의 결과가 부정**이므로 제외.
   `ambiguous` 6문장은 제외 + `prose_ambiguous` 플래그(편입하면 편향 방향을 모른다).

## 문장 단위로 처리한다

같은 날 한 문장은 진입, 다른 문장은 미거래인 사례가 실재한다(`2021-02-10`·`2021-10-19`).
날짜 단위로 뭉치면 틀린다. 그래서 키는 (문장 idx, 종목명)이고, 라벨 병합만 (날짜, 코드)로 한다.

## 새 컬럼 3개

| 컬럼 | 뜻 |
|---|---|
| `trade_confirmed` | 거래 확인 경로. `body_item`(구조화 항목=수익률 줄) > `prose`(산문 진술) > `title_only`(제목에만) |
| `notrade_decl` | 그가 **산문에서 「거래 안 했다」고 선언**한 (날짜, 종목)에 붙는다. PREREG §2.2 오염 정리용 |
| `regime_note` | 자유 메모. J1(단타 대신 스윙으로 갈음) · `prose_ambiguous` · `parser_artifact` 등 |

`src` 규약은 유지하고 뒤에 `+prose` 를 붙인다: `both`/`body`/`title_only` → `both+prose` 등.
신규 행은 `prose`.
"""
import argparse
import collections
import csv
import datetime
import io
import json
import os
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"
FWD = 40
PRE = 40
MIN_BARS = 15

# build_labels_v4.ALIAS 승계. **자동 유사매칭이 아니라** 개별 확인된 표기변형만.
ALIAS = {
    "삼기에너지솔루션": "419050",   # = 삼기에너지솔루션즈
    "아이빔테크놀러지": "460470",   # = 아이빔테크놀로지 (본문 오타)
    "렙지노믹스": "084650",        # = 랩지노믹스 (한 글자 오타, 경합 후보 없음)
}

REGIMES = [
    ("초기",       datetime.date(2017, 1, 1),  datetime.date(2020, 4, 20)),
    ("검색기단타",  datetime.date(2020, 4, 21), datetime.date(2024, 12, 31)),
    ("스윙박스권",  datetime.date(2025, 1, 1),  datetime.date(2025, 12, 31)),
    ("스윙계산기",  datetime.date(2026, 1, 1),  datetime.date(2026, 6, 30)),
    ("자동매매",    datetime.date(2026, 7, 1),  datetime.date(2099, 1, 1)),
]

# 직전 작업이 지목한 감사 대상. (post_date, stock_name) -> regime_note
MANUAL_NOTES = {
    ("2022-11-29", "그린케미칼"):
        "J1 단타 대신 스윙으로 갈음(본문 「일 때문에 단기매매를 하지 못하고 대신 스윙투자로 갈음」). "
        "라벨 유지 — method='추세 돌파' 는 C-B 풀 유형(직전고/전일고 돌파·이평선 반등)에 없으므로 "
        "PREREG §4.2 규칙이 C-B 표본 밖으로 자동 처리한다",
    ("2019-12-16", "SK바이오랜드 외 6개"): "J6 파서 산출물(제목 「외 6개」). 미매핑·usable=False",
    ("2021-07-07", "직전고 돌파, 신고가"): "J6 파서 산출물(트리거 문구가 종목명 자리에). 미매핑·usable=False",
}


def norm(s):
    return re.sub(r"\s+", "", s)


def regime_of(d):
    for name, lo, hi in REGIMES:
        if lo <= d <= hi:
            return name
    return "?"


def searcher_of(suffix):
    s = suffix or ""
    if "주도주" in s and "검색기" in s:
        return "주도주검색기"
    if "실시간 검색" in s or "실시간검색" in s or "실시간 종목순위" in s:
        return "실시간검색순위"
    if "신고가" in s:
        return "신고가검색기"
    if "장초반" in s:
        return "장초반검색기"
    if "검색기" in s:
        return "기타검색기"
    if "스윙" in s:
        return "스윙"
    return "기타"


def sql(query: str) -> str:
    env = dict(os.environ, PGPASSWORD="1234")
    path = "_q5.sql"
    open(path, "w", encoding="utf-8").write(query)
    r = subprocess.run([PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "robotrader",
                        "-d", "kis_template", "-tAF\t", "-f", path],
                       capture_output=True, env=env)
    err = r.stderr.decode("utf-8", "replace").strip()
    if err:
        print("SQL stderr:", err[:800])
    os.remove(path)
    return r.stdout.decode("utf-8", "replace")


def coverage(pairs):
    """(code, date) -> (bars_pre, bars_post). v4 와 **문자 그대로 같은 쿼리**."""
    if not pairs:
        return {}
    vals = ",".join("('{}','{}'::date)".format(c, d) for c, d in pairs)
    q = ("WITH lab(code,d) AS (VALUES " + vals + ") "
         "SELECT lab.code, lab.d, "
         f"count(*) FILTER (WHERE p.date BETWEEN to_char(lab.d-{PRE},'YYYY-MM-DD') "
         "AND to_char(lab.d,'YYYY-MM-DD')) AS pre, "
         "count(*) FILTER (WHERE p.date > to_char(lab.d,'YYYY-MM-DD') "
         f"AND p.date <= to_char(lab.d+{FWD},'YYYY-MM-DD')) AS post "
         "FROM lab LEFT JOIN daily_prices p ON p.stock_code=lab.code "
         f"AND p.date BETWEEN to_char(lab.d-{PRE},'YYYY-MM-DD') "
         f"AND to_char(lab.d+{FWD},'YYYY-MM-DD') GROUP BY 1,2;")
    cov = {}
    for line in sql(q).strip().split("\n"):
        p = line.split("\t")
        if len(p) == 4:
            cov[(p[0], p[1])] = (int(p[2]), int(p[3]))
    return cov


def year_have(codes):
    if not codes:
        return {}
    q2 = ("SELECT stock_code, substr(date,1,4) AS y, count(*) FROM daily_prices "
          "WHERE stock_code IN (" + ",".join("'%s'" % c for c in sorted(codes)) + ") "
          "GROUP BY 1,2;")
    have = collections.defaultdict(int)
    for line in sql(q2).strip().split("\n"):
        p = line.split("\t")
        if len(p) == 3:
            have[(p[0], p[1])] = int(p[2])
    return have


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--v4", default="../labels_v4.csv")
    ap.add_argument("--out", default="../labels_v5.csv")
    args = ap.parse_args()

    v4 = list(csv.DictReader(open(args.v4, encoding="utf-8-sig")))
    prose = list(csv.DictReader(open("prose_names.csv", encoding="utf-8-sig")))
    titles = list(csv.DictReader(open("titles_labels.csv", encoding="utf-8-sig")))
    suffix_of = {r["logNo"]: r["title_suffix"] for r in titles}
    trunc_of = {r["logNo"]: r["truncated"] == "True" for r in titles}

    pmap = {}
    if os.path.exists("code_map_prose.json"):
        pmap = {norm(k): v["code"] for k, v in
                json.load(open("code_map_prose.json", encoding="utf-8")).items()}

    # 이름 -> 코드. 네이버 정확일치가 1순위, 실패 시에만 승계 ALIAS(개별 확인분).
    alias_used = []

    def code_of(name):
        c = pmap.get(norm(name))
        if c:
            return c, "naver"
        c = ALIAS.get(norm(name))
        if c:
            alias_used.append(name)
            return c, "alias"
        return "", "none"

    # ---- 기존 v4 행: 값 보존 + 새 컬럼 3개 ----
    # ⚠️ CSV 에서 읽으면 `usable` 은 문자열 `"False"` 이고 **파이썬에서 truthy** 다.
    #    그대로 집계하면 「전부 가용」이 되어 N_T 가 조용히 부풀어 오른다(실제로 한 번 그랬다).
    #    쓰기 시점에 다시 `True`/`False` 문자열이 되므로 v4 포맷은 그대로 유지된다.
    rows = []
    for r in v4:
        rr = dict(r)
        rr["bars_pre"] = int(r["bars_pre"])
        rr["bars_post"] = int(r["bars_post"])
        for c in ("in_db_year", "usable", "title_truncated"):
            rr[c] = (r[c] == "True")
        rr["trade_confirmed"] = "body_item" if r["src"] in ("body", "both") else "title_only"
        rr["notrade_decl"] = False
        rr["regime_note"] = MANUAL_NOTES.get((r["post_date"], r["stock_name"]), "")
        rows.append(rr)
    # 병합 키는 **둘** 이다.
    #  key1 (날짜, 코드)  — v4 의 표기중복 제거 키.
    #  key2 (날짜, 정규화 이름) — 🔴 **미매핑 행은 코드가 빈 문자열이라 key1 로는 절대 안 걸린다.**
    #       실제로 KPX생명과학·맥스트·에코바이오 3건은 이미 라벨이 있는데 key1 만 쓰면
    #       「매핑 실패로 새로 탈락」처럼 보고된다(= 없는 손실을 보고하고, 중복을 놓친다).
    by_key, by_name = {}, {}
    for rr in rows:
        if rr["stock_code"]:
            by_key.setdefault((rr["post_date"], rr["stock_code"]), rr)
        by_name.setdefault((rr["post_date"], norm(rr["stock_name"])), rr)

    def find(date_s, code, name):
        if code and (date_s, code) in by_key:
            return by_key[(date_s, code)]
        return by_name.get((date_s, norm(name)))

    # ---- 산문 편입 ----
    ledger = []                       # 전건 회수표
    new_rows, seen_new = [], {}
    for p in prose:
        code, how = code_of(p["name"])
        rec = {"idx": p["idx"], "post_date": p["post_date"], "logNo": p["logNo"],
               "class": p["class"], "name": p["name"], "role": p["role"],
               "code": code, "code_src": how, "outcome": "", "reason": "",
               "matched_existing": ""}
        if p["role"] not in ("entry", "order_placed"):
            rec["outcome"] = "제외"
            rec["reason"] = {"notrade": "미거래 선언(선별 결과가 부정)",
                             "ambiguous": "애매 — 편입 시 편향 방향 불명(J5)",
                             "reference": "그가 거래한 종목이 아님(참조)",
                             "entry_misclassified":
                                 "거래한 종목이나 문장 분류가 진입이 아님 — 이번 편입 권한 밖"
                             }[p["role"]]
            hit = find(p["post_date"], code, p["name"])
            if hit is not None:
                rec["matched_existing"] = hit["stock_name"]
            ledger.append(rec)
            continue
        tgt = find(p["post_date"], code, p["name"])
        if tgt is not None:
            if "prose" not in tgt["src"]:
                tgt["src"] = tgt["src"] + "+prose"
            if tgt["trade_confirmed"] == "title_only":
                tgt["trade_confirmed"] = "prose"
            rec["outcome"] = ("중복(src갱신)" if tgt["src"].split("+")[0] != "prose"
                              else "중복(산문 내부)")
            rec["reason"] = ("기존 라벨과 (날짜,코드) 일치"
                             if code and tgt["stock_code"] == code
                             else "기존 라벨과 (날짜,이름) 일치 — 코드 없이 병합")
            if code and not tgt["stock_code"]:
                rec["reason"] += f" ⚠️ 산문은 {code} 를 얻었으나 v4 행 코드는 건드리지 않음"
            rec["matched_existing"] = tgt["stock_name"]
            ledger.append(rec)
            continue
        rec["outcome"] = "라벨신규" if code else "라벨신규(미매핑)"
        if not code:
            rec["reason"] = ("매핑 실패(네이버 정확일치 없음 — 상폐·사명변경·오타 추정). "
                             "v4 규약대로 행은 남긴다 — 버린 것도 산출물이다. usable=False")
        d = datetime.date(*map(int, p["post_date"].split("-")))
        nr = {"post_date": p["post_date"], "logNo": p["logNo"], "stock_code": code,
              "stock_name": p["name"], "regime": regime_of(d),
              "searcher": searcher_of(suffix_of.get(p["logNo"], "")),
              "preset": "", "preset_base": "", "preset_mode": "", "preset_mode_src": "",
              "src": "prose", "title_truncated": trunc_of.get(p["logNo"], False),
              "bars_pre": 0, "bars_post": 0, "in_db_year": False, "usable": False,
              "method": "",
              "trade_confirmed": "prose", "notrade_decl": False,
              "regime_note": ("J2 주문체결 안 됨 — 선별은 완료(체결 조건화 금지)"
                              if p["role"] == "order_placed" else "")}
        if code:
            by_key[(p["post_date"], code)] = nr
        by_name[(p["post_date"], norm(p["name"]))] = nr
        seen_new[(p["post_date"], code or norm(p["name"]))] = nr
        new_rows.append(nr)
        ledger.append(rec)

    rows.extend(new_rows)

    # ---- 미거래 선언 / 애매 플래그 ----
    # 🔴 **구조화 항목(수익률 줄)이 있는 행에는 `notrade_decl` 을 붙이지 않는다.**
    #    실측으로 걸린 유일한 후보가 2021-11-01 위메이드맥스인데, 그 글엔
    #      제목 `[큐브엔터, 위메이드맥스]` + 항목 `위메이드맥스 / 직전고 돌파(신고가) / 수익률 3.x%`
    #    가 있고 산문은 *"**한번 더** 트레이딩할 수 있었는데 … 신중히 했습니다"* 다.
    #    = 거래는 했고 **추가** 거래를 안 한 것이다. 이걸 미거래로 찍으면 **멀쩡한 라벨을 깎는다**.
    #    ⇒ 부정 진술은 「그 라벨의 거래 증거를 반박할 때만」 플래그가 된다.
    for p in prose:
        code, _ = code_of(p["name"])
        tgt = find(p["post_date"], code, p["name"])
        if tgt is None:
            continue
        has_item = tgt["trade_confirmed"] == "body_item"
        if p["role"] == "notrade":
            if has_item:
                tag = "prose_notrade_extra(추가 거래 미실행 진술 — 구조화 항목이 거래를 별도 확인)"
            else:
                tgt["notrade_decl"] = True
                tag = "prose_notrade_decl"
        elif p["role"] == "ambiguous":
            tag = "prose_ambiguous" + ("(구조화 항목 존재 — 라벨 자체는 거래 확인됨)"
                                       if has_item else "")
        else:
            continue
        if tag.split("(")[0] not in tgt["regime_note"]:
            tgt["regime_note"] = ((tgt["regime_note"] + " | " if tgt["regime_note"] else "")
                                  + tag)

    # ---- DB (허용된 두 가지만) ----
    #  신규 행만 새로 계산하고, **기존 행은 v4 값을 그대로 보존**한다.
    #  단 규약 동일성을 실증하기 위해 기존 행도 다시 재서 대조한다(값은 덮지 않는다).
    all_mapped = [r for r in rows if r["stock_code"]]
    cov = coverage([(r["stock_code"], r["post_date"]) for r in all_mapped])
    have = year_have({r["stock_code"] for r in all_mapped})

    mismatch = 0
    for r in rows:
        pre, post = cov.get((r["stock_code"], r["post_date"]), (0, 0))
        in_y = have.get((r["stock_code"], r["post_date"][:4]), 0) > 0
        usable = bool(r["stock_code"]) and pre >= MIN_BARS and post >= MIN_BARS
        if r["src"].startswith("prose"):
            r["bars_pre"], r["bars_post"] = pre, post
            r["in_db_year"], r["usable"] = in_y, usable
        else:
            if (str(r["bars_pre"]) != str(pre) or str(r["bars_post"]) != str(post)
                    or str(r["in_db_year"]) != str(in_y) or str(r["usable"]) != str(usable)):
                mismatch += 1
                if mismatch <= 5:
                    print(f"  ⚠️ v4 재계산 불일치: {r['post_date']} {r['stock_name']} "
                          f"v4=({r['bars_pre']},{r['bars_post']},{r['in_db_year']},{r['usable']}) "
                          f"재계산=({pre},{post},{in_y},{usable})")

    rows.sort(key=lambda r: (r["post_date"], r["stock_name"]))

    cols = ["post_date", "logNo", "stock_code", "stock_name", "regime", "searcher",
            "preset", "preset_base", "preset_mode", "preset_mode_src",
            "src", "title_truncated", "bars_pre", "bars_post",
            "in_db_year", "usable", "method",
            "trade_confirmed", "notrade_decl", "regime_note"]
    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows([{c: r[c] for c in cols} for r in rows])

    with open("prose_incorporation.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["idx", "post_date", "logNo", "class", "name",
                                           "role", "code", "code_src", "outcome",
                                           "reason", "matched_existing"])
        w.writeheader()
        w.writerows(ledger)

    # ---- 보고 ----
    print(f"\n=== v4 값 재계산 대조: 불일치 {mismatch}/{len(v4)} "
          f"(0 이어야 규약 동일) ===")
    print(f"ALIAS 승계 적용 이름 {len(set(alias_used))}종: {sorted(set(alias_used))} "
          f"(네이버 정확일치 실패분에만, 개별 확인된 표기변형)")

    print(f"\n=== 편입 결과 (후보 = 진입/order_placed {sum(1 for p in prose if p['role'] in ('entry','order_placed'))}건) ===")
    oc = collections.Counter(r["outcome"] for r in ledger
                             if r["role"] in ("entry", "order_placed"))
    for k in ("라벨신규", "라벨신규(미매핑)", "중복(src갱신)", "중복(산문 내부)"):
        print(f"  {k:<18}{oc.get(k,0):>5}")
    m = [r for r in new_rows if r["stock_code"]]
    print(f"  └ 매핑된 신규 {len(m)}행 중 usable {sum(1 for r in m if r['usable'])} "
          f"· DB미보유/봉부족 {sum(1 for r in m if not r['usable'])}")
    print(f"  └ 미매핑 신규 {len(new_rows)-len(m)}행 — 전부 usable=False (구조적)")

    print(f"\n=== 매핑 실패 전량 (생존편향 지표) ===")
    fails = [r for r in ledger
             if r["role"] in ("entry", "order_placed") and not r["code"]]
    for r in fails:
        print(f"  {r['post_date']} {r['name']:<14} {r['outcome']}")
    print(f"  계 {len(fails)}건 · 고유 {len({r['name'] for r in fails})}개")

    print(f"\n=== 플래그 ===")
    print(f"  notrade_decl=True {sum(1 for r in rows if r['notrade_decl'])}행 "
          f"(미거래 선언이 기존 라벨과 (날짜,코드) 일치)")
    print(f"  prose_ambiguous  {sum(1 for r in rows if 'prose_ambiguous' in r['regime_note'])}행")
    print(f"  수동 노트        {sum(1 for r in rows if r['regime_note'] and 'prose_ambiguous' not in r['regime_note'])}행")

    print(f"\n=== 최종 규모 ===")
    print(f"라벨 {len(rows)} (v4 {len(v4)} + 신규 {len(new_rows)})")
    print(f"{'체제':<12}{'라벨':>7}{'매핑':>7}{'usable':>8}{'종목블록':>9}{'날짜':>7}")
    for rg, _, _ in REGIMES:
        g = [r for r in rows if r["regime"] == rg]
        u = [r for r in g if r["usable"]]
        if g:
            print(f"{rg:<12}{len(g):>7}{sum(1 for r in g if r['stock_code']):>7}"
                  f"{len(u):>8}{len({r['stock_code'] for r in u}):>9}"
                  f"{len({r['post_date'] for r in u}):>7}")

    T = [r for r in rows if r["regime"] == "검색기단타" and r["usable"]]
    print(f"\n=== 처치군(검색기단타 & usable) ===")
    print(f"N_T = {len(T)}  (v4: 1271)  · 종목블록 {len({r['stock_code'] for r in T})}"
          f" · 날짜 {len({r['post_date'] for r in T})}")
    print(f"{'연도':<6}{'행':>6}{'종목':>7}{'날짜':>7}{'prose기여':>10}")
    per = collections.defaultdict(list)
    for r in T:
        per[r["post_date"][:4]].append(r)
    for y in sorted(per):
        g = per[y]
        print(f"{y:<6}{len(g):>6}{len({r['stock_code'] for r in g}):>7}"
              f"{len({r['post_date'] for r in g}):>7}"
              f"{sum(1 for r in g if 'prose' in r['src']):>10}")
    print(f"\n-> {args.out} · prose_incorporation.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
