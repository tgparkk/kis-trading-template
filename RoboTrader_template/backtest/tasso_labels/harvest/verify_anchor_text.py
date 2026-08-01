"""「앵커는 못 얻는다」 주장 재검증 — 고점대비 하락률이 텍스트에 있는가.

앵커 절대가(시작점·최고점)는 캡처에서 가려졌지만, 하락률(%)이 산문에 적혀 있다면
앵커를 *비율로* 복원할 여지가 생긴다. 7차 앵커 메모 §5.1-2 도 「1급 채점은 절대가가
아니라 하락률로」라고 못 박았으므로, 비율이면 충분할 수 있다.
"""
import collections
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# "고점대비 하락률 14.7%", "고점 대비 -22%", "고점대비 20% 내" 등
DROP = re.compile(r"고\s?점\s?대비[^\n]{0,24}?([0-9]{1,2}(?:\.[0-9]+)?)\s?%")
ANY_HIGH = re.compile(r"고\s?점\s?대비")
ITEM = re.compile(r"^\s*\d+[.,]\s*(.+?)\s*/\s*(.+?)\s*/\s*수익률.*$", re.M)


def regime_of(txt):
    if "주도주 검색기" in txt or "실시간 검색순위" in txt:
        return "2024단타"
    if "자동매매" in txt:
        return "자동매매"
    return "스윙"


def main() -> int:
    stat = collections.defaultdict(lambda: {"items": 0, "mention": 0, "numeric": 0})
    hits = []
    for f in sorted(glob.glob("text/*.txt")):
        date = os.path.basename(f)[:8]
        txt = open(f, encoding="utf-8").read()
        rg = regime_of(txt)
        ms = list(ITEM.finditer(txt))
        for i, m in enumerate(ms):
            blk = txt[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(txt)]
            s = stat[rg]
            s["items"] += 1
            if ANY_HIGH.search(blk):
                s["mention"] += 1
            vals = DROP.findall(blk)
            if vals:
                s["numeric"] += 1
                hits.append((date, rg, m.group(1).strip(), vals))

    print(f"{'체제':<10}{'종목':>6}{'「고점대비」 언급':>16}{'수치까지':>10}")
    for rg in ("2024단타", "스윙", "자동매매"):
        s = stat[rg]
        if s["items"]:
            print(f"{rg:<10}{s['items']:>6}{s['mention']:>16}{s['numeric']:>10}")

    print(f"\n=== 하락률 수치가 잡힌 {len(hits)}건 ===")
    for d, rg, name, vals in hits:
        print(f"  {d} [{rg}] {name}: {', '.join(v + '%' for v in vals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
