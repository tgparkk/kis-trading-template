"""체제 판별용 마커 빈도 — **연도별**. 기계 집계는 사람 정독의 보조일 뿐이다.

두 개의 함정을 먼저 제거한다(둘 다 실측으로 걸렸다):

1) 🔴 **판촉 푸터가 마커를 오염시킨다.** 글 말미의 책·강의 소개에 「종가베팅」·「통계 데이터」가
   그대로 들어 있어, 순진하게 세면 2022년 217글 **전부**가 "종가베팅 217 / 통계 217" 로 나온다.
   실제로는 방법 변화가 아니라 **푸터가 그 해에 붙기 시작한 것**이다.

2) 🔴 **콤마 표기 변화가 「가격 명시」를 가짜로 바꾼다.** `\\d{1,3},\\d{3}원` 으로 세면
   2021년 7건 → 2022년 86건으로 급증하는데, 2022 본문은 *"직전의 고점인 **2475원**을 돌파"* 처럼
   **콤마 없이** 쓴다. 즉 관행 변화가 아니라 **정규식이 콤마를 요구한 것**이다.
   ⇒ 절대가는 콤마 유무와 무관하게 센다.
"""
import collections
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 푸터 시작 표지 — 가장 먼저 나오는 것에서 자른다
CUTS = [
    "-------------------------------------------------------------",
    "※ 당일 단타가 어려운 분들에게",
    "단타가 어려운 분들에게 추천해 줄 책",
    # 2025~2026 판 푸터. 없으면 "검색기" 마커가 2025년 92%로 뜨는데
    # 실측상 그 11건은 **전부 책 소개("스윙 트레이딩 전략서 : 검색기 / 박스권…")** 였다.
    "※ 주식투자가 어려운 분들에게",
    "주식투자가 어려운 분들에게 추천해 줄 책",
    "※ 직장인 스윙부터 전업 단타까지",
    "태쏘 책 사러가기",
    "태쏘 유튜브 구독하기",
    "책 사러가기",
    "관련 동영상",
    "아래 홈페이지 접속",
]
# 콤마 유무 무관. 두 형태를 **명시적으로 나눠** 쓴다 —
# `\d{3}(?:,?\d{3})*` 한 방에 쓰면 "2475원"(4자리 무콤마)이 조용히 안 잡힌다(실제로 그랬다).
PRICE = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d{3,7})\s*원")
PCT = re.compile(r"\d+(?:\.\d+)?\s*%")

MARKERS = {
    "이등분선": ["이등분선"],
    "검색기": ["검색기", "검색식"],
    "돌파": ["돌파"],
    "계산기": ["계산기"],
    "분할매수": ["분할매수", "분할 매수"],
    "프리셋": ["하이브리드", "안정형", "공격형", "표준형"],
    "고점대비": ["고점대비", "고점 대비", "하락률"],
    "자동매매": ["자동매매"],
    "9시30분내종료": ["9시 30분", "9시30분", "10시께", "오전 매매 종료"],
}


def strip_footer(txt: str) -> str:
    idx = len(txt)
    for c in CUTS:
        i = txt.find(c)
        if 0 <= i < idx:
            idx = i
    return txt[:idx]


def main() -> int:
    per = collections.defaultdict(collections.Counter)
    n = collections.Counter()
    for f in sorted(glob.glob("text/*.txt")):
        y = os.path.basename(f)[:4]
        body = strip_footer(open(f, encoding="utf-8").read())
        if len(body) < 100:
            continue
        n[y] += 1
        for label, kws in MARKERS.items():
            if any(k in body for k in kws):
                per[y][label] += 1
        if PRICE.search(body):
            per[y]["절대가"] += 1
        per[y]["_절대가건수"] += len(PRICE.findall(body))
        per[y]["_길이"] += len(body)

    cols = list(MARKERS) + ["절대가"]
    print("본문 있는 글 기준 · **비율(%)**  (푸터 제거 후)")
    print(f"{'연도':<6}{'글':>5}{'평균자수':>8}" + "".join(f"{c[:8]:>10}" for c in cols))
    for y in sorted(per):
        g = n[y]
        print(f"{y:<6}{g:>5}{per[y]['_길이']//g:>8}" +
              "".join(f"{per[y][c]/g*100:>9.0f}%" for c in cols))
    print(f"\n{'연도':<6}{'절대가 총건수':>14}{'글당':>8}")
    for y in sorted(per):
        print(f"{y:<6}{per[y]['_절대가건수']:>14}{per[y]['_절대가건수']/n[y]:>8.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
