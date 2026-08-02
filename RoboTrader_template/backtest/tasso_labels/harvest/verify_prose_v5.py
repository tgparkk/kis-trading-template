"""v5 검증 — (1) v4 회귀 (2) 편입 전건 회수표 (3) 플래그 (4) 최종 규모.

🔑 **회수율은 「독립적으로 얻은 목록」과 대조해서 잰다.** 놓친 항목은 산출물에 흔적을 남기지 않는다.
여기서 독립 목록은 `prose_only_candidates.csv` 의 **문장 157건**이고, 대조 대상은 `labels_v5.csv` 다.
`prose_incorporation.csv` 는 그 사이의 전건 원장이다.

🔴 결과변수는 계산하지 않는다. 이 스크립트는 DB 를 건드리지 않는다.
"""
import collections
import csv
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
V4COLS = ["post_date", "logNo", "stock_code", "stock_name", "regime", "searcher",
          "preset", "preset_base", "preset_mode", "preset_mode_src",
          "src", "title_truncated", "bars_pre", "bars_post",
          "in_db_year", "usable", "method"]


def main() -> int:
    v4 = list(csv.DictReader(open("../labels_v4.csv", encoding="utf-8-sig")))
    v5 = list(csv.DictReader(open("../labels_v5.csv", encoding="utf-8-sig")))
    led = list(csv.DictReader(open("prose_incorporation.csv", encoding="utf-8-sig")))
    cand = list(csv.DictReader(open("prose_only_candidates.csv", encoding="utf-8-sig")))
    names = list(csv.DictReader(open("prose_names.csv", encoding="utf-8-sig")))

    # ---- (1) v4 회귀 ----
    print("=== (1) v4 회귀 — v4 2,252행이 v5 에 값 그대로 들어갔는가 ===")
    idx = collections.defaultdict(list)
    for r in v5:
        idx[(r["post_date"], r["logNo"], r["stock_code"], r["stock_name"])].append(r)
    miss, diff = [], []
    for r in v4:
        k = (r["post_date"], r["logNo"], r["stock_code"], r["stock_name"])
        if k not in idx:
            miss.append(k)
            continue
        t = idx[k][0]
        for c in V4COLS:
            if c == "src":
                if t["src"].split("+")[0] != r["src"]:
                    diff.append((k, c, r[c], t[c]))
            elif t[c] != r[c]:
                diff.append((k, c, r[c], t[c]))
    print(f"  미포함 {len(miss)}건 · 값 변경 {len(diff)}건 (둘 다 0 이어야 한다)")
    for d in diff[:10]:
        print("   ", d)
    print(f"  v5 행수 {len(v5)} = v4 {len(v4)} + 신규 {len(v5)-len(v4)}")

    # ---- (2) 전건 회수표 ----
    print("\n=== (2) 산문 후보 전건 회수 ===")
    print(f"  문장 {len(cand)}건 · 글 {len({c['logNo'] for c in cand})}건")
    print(f"  부류: {dict(collections.Counter(c['class'] for c in cand))}")
    print(f"  (문장,종목) {len(names)}건 · 고유이름 {len({n['name'] for n in names})}")
    ent = [r for r in led if r["role"] in ("entry", "order_placed")]
    print(f"\n  [편입 대상] role=entry/order_placed  {len(ent)}건")
    oc = collections.Counter(r["outcome"] for r in ent)
    for k, v in oc.most_common():
        print(f"    {k:<16}{v:>5}")
    created = [r for r in v5 if r["src"] == "prose"]
    nomap = [r for r in created if not r["stock_code"]]
    nobar = [r for r in created if r["stock_code"] and r["usable"] != "True"]
    print(f"\n  [처치군 표본에 못 들어가는 사유 — 배타 분해]")
    print(f"    종목명 추출 실패      "
          f"{sum(1 for c_i, c in enumerate(cand, 1) if c['class']=='진입' and not [n for n in names if int(n['idx'])==c_i]):>5}"
          f"   문장 단위. 진입으로 분류됐으나 종목이 없는 문장")
    print(f"    매핑 실패           {len(nomap):>5}   행은 생성(usable=False) — 생존편향 지표")
    print(f"    DB 미보유/봉 부족     {len(nobar):>5}   매핑은 됐으나 ±40역일에 15거래일 미달")
    print(f"    중복(기존라벨과 일치)  {oc.get('중복(src갱신)',0):>5}   * 라벨 손실 아님 — src 갱신")
    print(f"    -> usable 신규       "
          f"{sum(1 for r in created if r['usable']=='True'):>5}")

    print(f"\n  [제외 — 관리자 판정] role != entry")
    for role in ("notrade", "ambiguous", "reference", "entry_misclassified"):
        g = [r for r in led if r["role"] == role]
        if g:
            print(f"    {role:<20}{len(g):>4}  (기존 라벨과 (날짜,코드) 일치 "
                  f"{sum(1 for r in g if r['matched_existing'])}건)")

    # ---- (3) 플래그 ----
    print("\n=== (3) 플래그 ===")
    for r in v5:
        if r["notrade_decl"] == "True":
            print(f"  notrade_decl  {r['post_date']} {r['stock_name']} "
                  f"({r['stock_code']}) src={r['src']} usable={r['usable']}")
    for r in v5:
        if "prose_ambiguous" in r["regime_note"]:
            print(f"  prose_ambiguous {r['post_date']} {r['stock_name']} "
                  f"({r['stock_code']}) usable={r['usable']}")
    for r in v5:
        if r["regime_note"] and "prose_ambiguous" not in r["regime_note"]:
            print(f"  note  {r['post_date']} {r['stock_name']}: {r['regime_note'][:90]}")

    print("\n  [중복 — src 갱신된 행]")
    for r in led:
        if r["outcome"] == "중복(src갱신)":
            hit = [x for x in v5 if x["post_date"] == r["post_date"]
                   and x["stock_code"] == r["code"]][0]
            print(f"    {r['post_date']} {r['name']} -> 기존 '{r['matched_existing']}' "
                  f"src={hit['src']} trade_confirmed={hit['trade_confirmed']} "
                  f"usable={hit['usable']}")

    # ---- (4) 최종 규모 ----
    print("\n=== (4) 최종 규모 ===")
    print(f"{'체제':<12}{'라벨':>7}{'usable':>8}{'종목블록':>9}{'날짜':>7}{'prose행':>8}")
    for rg in ("초기", "검색기단타", "스윙박스권", "스윙계산기", "자동매매"):
        g = [r for r in v5 if r["regime"] == rg]
        u = [r for r in g if r["usable"] == "True"]
        print(f"{rg:<12}{len(g):>7}{len(u):>8}{len({r['stock_code'] for r in u}):>9}"
              f"{len({r['post_date'] for r in u}):>7}"
              f"{sum(1 for r in g if 'prose' in r['src']):>8}")

    T = [r for r in v5 if r["regime"] == "검색기단타" and r["usable"] == "True"]
    T4 = [r for r in v4 if r["regime"] == "검색기단타" and r["usable"] == "True"]
    print(f"\n처치군 N_T  {len(T4)} -> {len(T)}  (+{len(T)-len(T4)})")
    print(f"  종목블록 {len({r['stock_code'] for r in T4})} -> {len({r['stock_code'] for r in T})}"
          f"  · 날짜 {len({r['post_date'] for r in T4})} -> {len({r['post_date'] for r in T})}")
    print(f"\n{'연도':<6}{'v4행':>7}{'v5행':>7}{'증분':>6}{'v5종목':>8}{'v5날짜':>8}")
    p4 = collections.defaultdict(list)
    p5 = collections.defaultdict(list)
    for r in T4:
        p4[r["post_date"][:4]].append(r)
    for r in T:
        p5[r["post_date"][:4]].append(r)
    for y in sorted(p5):
        print(f"{y:<6}{len(p4[y]):>7}{len(p5[y]):>7}{len(p5[y])-len(p4[y]):>6}"
              f"{len({r['stock_code'] for r in p5[y]}):>8}"
              f"{len({r['post_date'] for r in p5[y]}):>8}")

    print(f"\n{'src':<16}{'행':>7}{'usable':>8}")
    for s, n in collections.Counter(r["src"] for r in v5).most_common():
        u = sum(1 for r in v5 if r["src"] == s and r["usable"] == "True")
        print(f"{s:<16}{n:>7}{u:>8}")
    print(f"\n{'trade_confirmed':<16}{'행':>7}{'usable':>8}")
    for s, n in collections.Counter(r["trade_confirmed"] for r in v5).most_common():
        u = sum(1 for r in v5 if r["trade_confirmed"] == s and r["usable"] == "True")
        print(f"{s:<16}{n:>7}{u:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
