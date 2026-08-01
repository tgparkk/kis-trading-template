"""매수·매도 타이밍/가격이 본문에 얼마나 있는지 전수 집계.

지금까지는 헤더줄(종목/방법/수익률)만 파싱했다. 본문 산문에는
「3차 매수 체결」「62,000원부터 66,300원까지 분할매도」「(12일)」 같은
체결 차수·매도 가격대·날짜가 들어 있다. 그 회수 가능량을 먼저 잰다.
"""
import collections
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ITEM = re.compile(r"^\s*(?:\d+\s*[.,]?\s*)?([^/\n]{2,24}?)\s*/\s*([^/\n]{2,40}?)\s*/\s*수익률", re.M)
PAT = {
    "매수차수":   re.compile(r"(\d)\s*차\s*(?:매수)?\s*(?:체결|까지|진입|매수)"),
    "매도가격대": re.compile(r"([\d,]{3,})\s*원\s*(?:부터|에서|~)\s*([\d,]{3,})\s*원"),
    "분할매도":   re.compile(r"분할\s*매도"),
    "전량/익절":  re.compile(r"전량\s*매도|일괄\s*매도|익절"),
    "손절":       re.compile(r"손절|손실\s*률|스탑"),
    "날짜언급":   re.compile(r"\(\s*\d{1,2}\s*일\s*\)|\d{1,2}월\s*\d{1,2}일"),
    "보유/미청산": re.compile(r"보유\s*중|미\s*청산|홀딩|잔여"),
}


def regime_of(t):
    if "주도주 검색기" in t or "실시간 검색순위" in t:
        return "2024단타"
    if "자동매매" in t:
        return "자동매매"
    return "스윙"


def main() -> int:
    stat = collections.defaultdict(lambda: collections.Counter())
    tot = collections.Counter()
    samples = collections.defaultdict(list)

    for f in sorted(glob.glob("text/*.txt")):
        txt = open(f, encoding="utf-8").read()
        rg = regime_of(txt)
        ms = list(ITEM.finditer(txt))
        for i, m in enumerate(ms):
            blk = txt[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(txt)]
            blk = "\n".join(l for l in blk.split("\n") if not l.strip().startswith("▲"))
            tot[rg] += 1
            for k, p in PAT.items():
                hit = p.search(blk)
                if hit:
                    stat[rg][k] += 1
                    if len(samples[k]) < 3 and rg == "스윙":
                        s = " ".join(blk.split())
                        j = hit.start()
                        samples[k].append(f"{os.path.basename(f)[:8]} …{s[max(0,j-45):j+65]}…")

    keys = list(PAT)
    print(f"{'체제':<10}{'종목':>5}" + "".join(f"{k:>11}" for k in keys))
    for rg in ("2024단타", "스윙", "자동매매"):
        if not tot[rg]:
            continue
        print(f"{rg:<10}{tot[rg]:>5}" + "".join(f"{stat[rg][k]:>11}" for k in keys))

    print("\n=== 스윙 체제 표본 ===")
    for k in keys:
        if samples[k]:
            print(f"\n[{k}]")
            for s in samples[k]:
                print("  ", s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
