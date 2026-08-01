"""계산기에서 가려진 「하락 구간(%)」이 본문 텍스트에 있는지 전수 집계.

발단: 2026-05-13 글에 "평균 고점대비 하락률 18.8% 하락폭 신뢰구간 17.7% ~ 23.1%" 가
평문으로 적혀 있다. 이는 계산기 캡처에서 블러 처리된 바로 그 컬럼(d_lo~d_hi)이다.
있으면 H = B_hi/(1-d_lo) 로 앵커가 **직접** 나온다.
"""
import collections
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ITEM = re.compile(r"^\s*(?:\d+\s*[.,]?\s*)?([^/\n]{2,24}?)\s*/\s*([^/\n]{2,40}?)\s*/\s*수익률", re.M)
CI = re.compile(r"신뢰\s*구간\s*([\d.]+)\s*%\s*[~∼-]\s*([\d.]+)\s*%")
AVG = re.compile(r"(?:평균\s*)?고\s?점\s?대비\s*(?:하락률)?\s*([\d.]+)\s*%")
BOX = re.compile(r"박스권\s*하단부?\s*([\d,]{3,})\s*원\s*[~∼-]\s*([\d,]{3,})\s*원")
BUYWIN = re.compile(r"\[\s*(\d{1,2}/\d{1,2})\s*[~∼-]\s*(\d{1,2}/\d{1,2})\s*\]\s*까지\s*분할\s*매수")


def regime_of(t):
    if "주도주 검색기" in t or "실시간 검색순위" in t:
        return "2024단타"
    if "자동매매" in t:
        return "자동매매"
    return "스윙"


def main() -> int:
    rows, cnt = [], collections.Counter()
    for f in sorted(glob.glob("text/*.txt")):
        date = os.path.basename(f)[:8]
        txt = open(f, encoding="utf-8").read()
        rg = regime_of(txt)
        ms = list(ITEM.finditer(txt))
        for i, m in enumerate(ms):
            blk = txt[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(txt)]
            blk = " ".join(l for l in blk.split("\n") if not l.strip().startswith("▲"))
            ci, avg, box, win = CI.search(blk), AVG.search(blk), BOX.search(blk), BUYWIN.search(blk)
            if not (ci or avg or box):
                continue
            cnt[rg] += 1
            if ci:
                cnt["신뢰구간"] += 1
            if avg:
                cnt["평균하락률"] += 1
            if box:
                cnt["박스권가격"] += 1
            if win:
                cnt["매수기간"] += 1
            rows.append({
                "date": date, "regime": rg, "stock": m.group(1).strip(),
                "d_lo": float(ci.group(1)) if ci else None,
                "d_hi": float(ci.group(2)) if ci else None,
                "d_avg": float(avg.group(1)) if avg else None,
                "px_hi": int(box.group(1).replace(",", "")) if box else None,
                "px_lo": int(box.group(2).replace(",", "")) if box else None,
                "buywin": f"{win.group(1)}~{win.group(2)}" if win else "",
            })

    print(f"하락률 정보가 있는 종목-건 {len(rows)}건")
    print(f"  신뢰구간(d_lo~d_hi) {cnt['신뢰구간']} · 평균하락률 {cnt['평균하락률']} "
          f"· 박스권 가격 {cnt['박스권가격']} · 매수기간 {cnt['매수기간']}")
    print(f"  체제별: " + ", ".join(f"{k}={cnt[k]}" for k in ('2024단타', '스윙', '자동매매') if cnt[k]))

    full = [r for r in rows if r["d_lo"] and r["px_hi"]]
    print(f"\n=== 🔑 신뢰구간 + 박스권가격 둘 다 있는 {len(full)}건 -> H 직접 역산 가능 ===")
    for r in full:
        h1 = r["px_hi"] / (1 - r["d_lo"] / 100)
        h2 = r["px_lo"] / (1 - r["d_hi"] / 100)
        print(f"  {r['date']} {r['stock']:<14} d {r['d_lo']}~{r['d_hi']}% · "
              f"px {r['px_hi']:,}~{r['px_lo']:,} -> H={h1:,.0f} / {h2:,.0f} "
              f"(불일치 {abs(h1-h2)/h1*100:.2f}%)")

    print(f"\n=== 하락률만 있는 것 (상위 12) ===")
    for r in [x for x in rows if not (x["d_lo"] and x["px_hi"])][:12]:
        print(f"  {r['date']} {r['stock']:<14} 평균 {r['d_avg']}% · CI {r['d_lo']}~{r['d_hi']} "
              f"· px {r['px_hi']} · 매수기간 {r['buywin']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
