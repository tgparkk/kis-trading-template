"""「후보 선정이 뉴스 기반」 주장을 전수 검증.

관리자가 실제로 읽은 건 2건뿐인데 22건(스윙 체제) 전체에 대한 주장을 했다.
종목 헤더마다 뒤따르는 설명 블록을 잘라 촉매/뉴스 표지가 있는지 전수로 센다.
"""
import collections
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ITEM = re.compile(r"^\s*\d+[.,]\s*(.+?)\s*/\s*(.+?)\s*/\s*수익률.*$", re.M)
# 촉매/뉴스 표지
NEWS = ["보도", "공시", "소식", "뉴스", "발표", "계약", "수주", "실적", "승인", "출시",
        "체결", "선정", "기대감", "이슈", "테마", "언급", "리포트", "전망", "특징주",
        "상향", "인수", "합병", "증설", "공급", "허가", "임상", "수출", "협약"]
CALC = ["계산기", "통계 기반", "통계기반", "하이브리드", "안정형", "공격형"]


def regime_of(txt):
    if "주도주 검색기" in txt or "실시간 검색순위" in txt:
        return "2024단타"
    if "자동매매" in txt:
        return "자동매매"
    return "스윙"


def main() -> int:
    per_regime = collections.defaultdict(lambda: {"items": 0, "news": 0, "calc": 0,
                                                  "chars": [], "posts": set()})
    samples = []
    for f in sorted(glob.glob("text/*.txt")):
        date = os.path.basename(f)[:8]
        txt = open(f, encoding="utf-8").read()
        rg = regime_of(txt)
        ms = list(ITEM.finditer(txt))
        for i, m in enumerate(ms):
            start = m.end()
            end = ms[i + 1].start() if i + 1 < len(ms) else len(txt)
            blk = txt[start:end]
            # 차트 캡션 줄(▲ …)은 설명이 아니므로 제거
            blk = "\n".join(l for l in blk.split("\n") if not l.strip().startswith("▲"))
            d = per_regime[rg]
            d["items"] += 1
            d["posts"].add(date)
            d["chars"].append(len(blk.strip()))
            hasnews = any(k in blk for k in NEWS)
            d["news"] += hasnews
            d["calc"] += any(k in blk for k in CALC)
            if rg == "스윙" and hasnews and len(samples) < 6:
                one = " ".join(blk.split())[:110]
                samples.append(f"{date} {m.group(1).strip()}: {one}")

    print(f"{'체제':<10}{'글':>4}{'종목':>6}{'설명有':>8}{'뉴스표지':>9}{'계산기언급':>11}{'설명 중앙길이':>13}")
    for rg in ("2024단타", "스윙", "자동매매"):
        d = per_regime[rg]
        if not d["items"]:
            continue
        ch = sorted(d["chars"])
        med = ch[len(ch) // 2]
        nonempty = sum(1 for c in d["chars"] if c > 40)
        print(f"{rg:<10}{len(d['posts']):>4}{d['items']:>6}"
              f"{nonempty:>8}{d['news']:>9}{d['calc']:>11}{med:>13}")

    print("\n=== 스윙 체제 표본 (뉴스표지 있는 블록) ===")
    for s in samples:
        print(" •", s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
