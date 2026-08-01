"""라벨 회수율 측정 — 제목에 적힌 종목 vs 본문 번호헤더에서 뽑은 종목.

번호 헤더 없이 산문으로만 언급된 거래("이외 그리드위즈 진입하였으나 본전으로 차트 미첨부")는
ITEM 정규식이 놓친다. 제목 종목 목록을 독립 기준으로 삼아 누락을 센다.
"""
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ITEM = re.compile(r"^\s*\d+[.,]\s*(.+?)\s*/\s*(.+?)\s*/\s*수익률.*$", re.M)
TITLE = re.compile(r"^\s*\[([^\]]+)\]")
NOISE = re.compile(r"\s*(외|등|그 외)\s*$")


def main() -> int:
    tot_t = tot_b = tot_miss = tot_extra = 0
    rows = []
    for f in sorted(glob.glob("text/*.txt")):
        date = os.path.basename(f)[:8]
        txt = open(f, encoding="utf-8").read()
        first = txt.split("\n", 1)[0]
        m = TITLE.match(first)
        if not m:
            continue
        tnames = []
        truncated = False
        for p in m.group(1).split(","):
            p = p.strip()
            if NOISE.search(p) or p in ("외", "등"):
                truncated = True
                p = NOISE.sub("", p).strip()
            if p:
                tnames.append(p)
        bnames = [x.strip() for x, _ in ITEM.findall(txt)]
        miss = [n for n in tnames if n not in bnames]
        extra = [n for n in bnames if n not in tnames]
        tot_t += len(tnames)
        tot_b += len(bnames)
        tot_miss += len(miss)
        tot_extra += len(extra)
        if miss or truncated:
            rows.append((date, len(tnames), len(bnames), miss, truncated))

    print(f"제목 종목 총 {tot_t} · 본문 헤더 총 {tot_b} · "
          f"제목에만 있고 헤더 없음 {tot_miss} · 헤더에만 있음 {tot_extra}")
    print(f"\n=== 불일치/제목절단('외') 글 {len(rows)}건 ===")
    for d, nt, nb, miss, tr in rows:
        tag = " [제목에 '외' — 제목이 상한이 아님]" if tr else ""
        print(f"  {d} 제목{nt} 헤더{nb} 누락={miss}{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
