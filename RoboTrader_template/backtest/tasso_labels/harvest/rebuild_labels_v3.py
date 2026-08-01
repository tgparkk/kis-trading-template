"""라벨 v3 — 구조화 항목 + 제목 전용 종목까지 회수.

v1: `^\\d+[.,]` 를 요구해 번호 없는 헤더를 놓침.
v2: 번호 선택적. 3건 회수했으나 구분자가 공백인 경우 이름에 숫자가 섞임.
v3: (a) 이름 앞 숫자 잔재 제거, (b) **제목에만 있고 본문 구조화 항목이 없는 종목**을 추가.
    (b)가 중요한 이유: "이외 그리드위즈 진입하였으나 본전으로 차트 미첨부" 처럼
    **결과가 밋밋한 거래가 구조화 보고에서 빠진다** — 구조화분만 쓰면 라벨셋이
    「언급할 만한 거래」 쪽으로 편향된다. 결과는 우리가 DB 에서 재므로 넣는 게 맞다.
"""
import collections
import csv
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ITEM = re.compile(r"^\s*(?:\d+\s*[.,]?\s*)?([^/\n]{2,24}?)\s*/\s*([^/\n]{2,40}?)\s*/\s*수익률", re.M)
LEAD_NUM = re.compile(r"^\d+\s*[.,]?\s*")
TITLE = re.compile(r"^\s*\[([^\]]+)\]")
NOISE = re.compile(r"\s*(외|등|그 외)\s*$")


def regime_of(txt):
    if "주도주 검색기" in txt or "실시간 검색순위" in txt:
        return "2024단타"
    if "자동매매" in txt:
        return "자동매매"
    return "스윙"


def preset_of(method, txt, name):
    blk = txt.split(name, 1)[-1][:600] if name in txt else ""
    for p in ("하이브리드", "안정형", "공격형"):
        if p in blk or p in method:
            return p
    return ""


def main() -> int:
    rows, title_only = [], 0
    for f in sorted(glob.glob("text/*.txt")):
        date = os.path.basename(f)[:8]
        txt = open(f, encoding="utf-8").read()
        rg = regime_of(txt)
        pd = f"{date[:4]}-{date[4:6]}-{date[6:]}"

        body = {}
        for name, method in ITEM.findall(txt):
            name = LEAD_NUM.sub("", name.strip()).strip()
            if len(name) >= 2 and name not in body:
                body[name] = method

        for name, method in body.items():
            rows.append({"post_date": pd, "stock_name": name, "regime": rg,
                         "preset": preset_of(method, txt, name), "src": "body"})

        m = TITLE.match(txt.split("\n", 1)[0])
        if m:
            for p in m.group(1).split(","):
                p = NOISE.sub("", p.strip()).strip()
                if len(p) >= 2 and p not in body and p not in ("외", "등"):
                    rows.append({"post_date": pd, "stock_name": p, "regime": rg,
                                 "preset": "", "src": "title_only"})
                    title_only += 1

    seen, uniq = set(), []
    for r in rows:
        k = (r["post_date"], r["stock_name"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)

    print(f"v3 라벨 {len(uniq)} (구조화 {len(uniq)-title_only} + 제목전용 {title_only})")
    print("체제별:", dict(collections.Counter(r["regime"] for r in uniq)))
    print(f"\n=== 제목전용 {title_only}건 (구조화 보고에서 빠진 거래) ===")
    for r in uniq:
        if r["src"] == "title_only":
            print(f"  {r['post_date']}  {r['stock_name']}  [{r['regime']}]")

    with open("labels_v3_names.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["post_date", "stock_name", "regime", "preset", "src"])
        w.writeheader()
        w.writerows(uniq)
    print("\n-> labels_v3_names.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
