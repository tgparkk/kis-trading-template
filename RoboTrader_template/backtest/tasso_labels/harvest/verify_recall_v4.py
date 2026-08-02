"""회수율 대조 — **연도별로 「본문 ∪ 제목」 대비 각각의 회수율**.

한쪽 추출기의 회수율은 그 추출기로 잴 수 없다. 놓친 항목은 산출물에 흔적을 남기지 않기 때문이다
(v1 가온칩스 사고). 여기서는 서로를 기준으로 삼아 **어느 쪽이 어느 해에 상대를 놓치는지**를 본다.

추가로, 합집합조차 놓치는 잔여 경로를 센다: 산문에만 있는 거래
(*"이외 한화투자증권은 진입했으나 … 차트 미첨부 합니다"*). 이건 **자동 편입하지 않는다** —
같은 문단에 *"검색기에 태양금속도 포착되었는데요. 태양금속은 아쉽게 거래를 하지 못했습니다"*
처럼 **거래하지 않은 종목**도 섞여 있어 정확 판별이 안 된다. 크기만 보고한다.
"""
import collections
import csv
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROSE = re.compile(r"이외[^.\n]{0,80}?(진입|매수|매매|공략)")


def norm(s):
    return re.sub(r"\s+", "", s)


def main() -> int:
    T = {(r["post_date"], norm(r["stock_name"])) for r in
         csv.DictReader(open("titles_labels.csv", encoding="utf-8-sig"))}
    B = {(r["post_date"], norm(r["stock_name"])) for r in
         csv.DictReader(open("body_labels.csv", encoding="utf-8-sig"))}
    have_body = {os.path.basename(f)[:8] for f in glob.glob("text/*.txt")
                 if os.path.getsize(f) > 200}
    have_body = {f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in have_body}

    U = T | B
    per = collections.defaultdict(lambda: collections.Counter())
    for d, n in U:
        y = d[:4]
        if d not in have_body:          # 본문이 없는 글은 본문 회수율 분모에서 뺀다
            per[y]["union_nobody"] += 1
            continue
        per[y]["union"] += 1
        per[y]["title"] += ((d, n) in T)
        per[y]["body"] += ((d, n) in B)
        per[y]["both"] += ((d, n) in T and (d, n) in B)

    print("=== 회수율 대조 (분모 = 본문이 있는 글의 「본문 ∪ 제목」) ===")
    print(f"{'연도':<6}{'합집합':>8}{'제목':>7}{'회수%':>8}{'본문':>7}{'회수%':>8}"
          f"{'both':>7}{'제목전용':>9}{'본문전용':>9}{'본문無글의라벨':>14}")
    for y in sorted(per):
        c = per[y]
        u = c["union"] or 1
        print(f"{y:<6}{c['union']:>8}{c['title']:>7}{c['title']/u*100:>7.1f}%"
              f"{c['body']:>7}{c['body']/u*100:>7.1f}%{c['both']:>7}"
              f"{c['union']-c['body']:>9}{c['union']-c['title']:>9}"
              f"{c['union_nobody']:>14}")
    tot = collections.Counter()
    for c in per.values():
        tot.update(c)
    u = tot["union"] or 1
    print(f"{'계':<6}{tot['union']:>8}{tot['title']:>7}{tot['title']/u*100:>7.1f}%"
          f"{tot['body']:>7}{tot['body']/u*100:>7.1f}%{tot['both']:>7}"
          f"{tot['union']-tot['body']:>9}{tot['union']-tot['title']:>9}"
          f"{tot['union_nobody']:>14}")

    # 합집합조차 놓치는 잔여 — 산문 언급
    prose = collections.Counter()
    for f in sorted(glob.glob("text/*.txt")):
        y = os.path.basename(f)[:4]
        txt = open(f, encoding="utf-8").read()
        hits = PROSE.findall(txt)
        if hits:
            prose[y] += len(hits)
            prose["_글"] += 1
    print("\n=== 합집합이 놓치는 잔여: 산문에만 있는 거래 (\"이외 … 진입/매수\") ===")
    print("⚠️ 자동 편입하지 않는다 — 같은 형식으로 **거래하지 않은** 종목도 언급된다.")
    for y in sorted(k for k in prose if not k.startswith("_")):
        print(f"   {y}: {prose[y]}건")
    print(f"   해당 글 {prose['_글']}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
