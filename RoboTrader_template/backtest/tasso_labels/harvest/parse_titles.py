"""제목 기반 라벨 추출 — 본문과 **독립된** 회수 기준선.

왜 제목이 독립 기준인가: 구조화 본문 추출기의 회수율은 추출기 자신으로는 측정할 수 없다.
놓친 항목은 산출물에 흔적을 남기지 않기 때문이다(v1 가온칩스 사고). 제목 목록은
추출기와 무관하게 얻어지므로 대조 기준으로 쓸 수 있다.

실측(858건):
  - 대괄호가 없는 글 **0건** — 제목 파서가 전 기간에 적용 가능하다.
  - 말미가 "외/등"으로 잘린 글 **21건(2.4%)** — 이 글에서는 제목이 상한이 아니다.

출력: titles_labels.csv (post_date, logNo, stock_name, title_suffix, truncated)
"""
import argparse
import collections
import csv
import datetime
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BRACKET = re.compile(r"^\s*\[([^\]]+)\]")
# 🔴 `&` 를 구분자에 넣지 말 것 — 858건 실측상 대괄호 안 `&` 13개는 **전부 상호의 일부**다
#    (SM C&C · F&F홀딩스 · 세림B&G · 신세계I&C · 대림B&Co · 백금T&A · 무림P&P · KH E&T).
#    구분자로 쓰면 12개 글의 종목명이 "SM C"/"C" 처럼 두 동강 나고 매핑이 조용히 실패한다.
#    실제 구분자 빈도: `,` 1,290 / `&` 13(전부 상호) / `/`·`·`·`ㆍ` 0.
SPLIT = re.compile(r"[,/·ㆍ]")
TRAIL = re.compile(r"\s*(그\s*외|외|등)\s*$")
# 종목명이 아닌 꼬리표 (제목 대괄호 안에 섞여 들어오는 것들)
NOT_A_NAME = {"외", "등", "그외", "그 외", "스윙", "단타", "자동매매", "종목"}

# 표기 정규화 — finalize_v3.ALIAS 와 같은 규약(오타/표기변형 -> 정식 표기).
# 코드 매핑은 resolve 단계에서 하고, 여기서는 이름 표기만 통일한다.
NAME_FIX = {
    "아이빔테크놀러지": "아이빔테크놀로지",
    "렙지노믹스": "랩지노믹스",
    "삼기에너지솔루션": "삼기에너지솔루션즈",
}


def norm(name: str) -> str:
    """대조·매핑용 키. 공백만 무시한다(유사매칭 아님 — 정확 일치의 표기 정규화)."""
    return re.sub(r"\s+", "", name)


def parse_title(title: str):
    """(names, suffix, truncated) 반환. 대괄호가 없으면 ([], title, False)."""
    m = BRACKET.match(title)
    if not m:
        return [], title.strip(), False
    inner = m.group(1)
    suffix = title[m.end():].strip()
    truncated = bool(TRAIL.search(inner.strip())) or bool(
        re.search(r"(외|등)\s*$", inner.strip()))
    names = []
    for part in SPLIT.split(inner):
        p = TRAIL.sub("", part.strip()).strip()
        # 내부 공백은 **지우지 말고** 하나로만 접는다 — 상호의 일부다
        # (KG ETS · NHN KCP · YG PLUS · SM Life Design · 포스코 ICT · CJ CGV).
        # 대조·매핑은 norm() 으로 공백 무시하되, 표기는 원형을 남긴다.
        p = re.sub(r"\s+", " ", p).strip()
        if len(norm(p)) < 2 or norm(p) in {norm(x) for x in NOT_A_NAME}:
            continue
        names.append(NAME_FIX.get(p, p))
    # 같은 제목 안 중복 제거(순서 유지)
    out, seen = [], set()
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out, suffix, truncated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="titles_labels.csv")
    args = ap.parse_args()

    posts = json.load(open("tasso_postlist.json", encoding="utf-8"))
    rows, no_bracket, trunc = [], 0, 0
    per_year = collections.Counter()
    per_year_posts = collections.Counter()
    for p in posts:
        dt = datetime.datetime.fromtimestamp(p["addDate"] / 1000)   # KST 유지
        names, suffix, tr = parse_title(p["title"])
        per_year_posts[dt.year] += 1
        if not names:
            no_bracket += 1
        if tr:
            trunc += 1
        for n in names:
            rows.append({"post_date": f"{dt:%Y-%m-%d}", "logNo": p["logNo"],
                         "stock_name": n, "title_suffix": suffix,
                         "truncated": tr})
            per_year[dt.year] += 1

    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["post_date", "logNo", "stock_name",
                                           "title_suffix", "truncated"])
        w.writeheader()
        w.writerows(rows)

    print(f"글 {len(posts)} · 제목라벨 {len(rows)} · 고유종목 "
          f"{len({r['stock_name'] for r in rows})}")
    print(f"종목 0건으로 파싱된 글 {no_bracket} · 절단('외/등') 글 {trunc}")
    print(f"\n{'연도':<6}{'글':>6}{'제목라벨':>9}")
    for y in sorted(per_year_posts):
        print(f"{y:<6}{per_year_posts[y]:>6}{per_year[y]:>9}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
