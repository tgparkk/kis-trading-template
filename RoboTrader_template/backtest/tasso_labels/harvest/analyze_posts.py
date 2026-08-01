"""44건 텍스트 정량화 — 체제 분류·종목/수익률 추출·손실 거래 공개 여부."""
import collections
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# "1. 종목명 / 방법 / 수익률 12.3%, 4.5% ~"  형태의 종목 헤더
ITEM = re.compile(r"^\s*\d+[.,]\s*(.+?)\s*/\s*(.+?)\s*/\s*수익률\s*(.+?)\s*$", re.M)
PCT = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")


def main() -> int:
    files = sorted(glob.glob("text/*.txt"))
    regimes = collections.Counter()
    presets = collections.Counter()
    all_rets, neg_rets = [], []
    trades = 0
    per_post = []

    for f in files:
        date = os.path.basename(f)[:8]
        txt = open(f, encoding="utf-8").read()
        items = ITEM.findall(txt)

        if "주도주 검색기" in txt or "실시간 검색순위" in txt:
            regime = "2024단타"
        elif "자동매매" in txt:
            regime = "자동매매"
        elif "계산기" in txt:
            regime = "스윙-계산기"
        else:
            regime = "기타"
        regimes[regime] += 1

        post_rets = []
        for _name, method, rets in items:
            trades += 1
            for pre in ("안정형", "하이브리드", "공격형", "통계기반 자동매매", "통계 기반 계산기"):
                if pre in method:
                    presets[pre] += 1
            vals = [float(v) for v in PCT.findall(rets)]
            post_rets.extend(vals)
        # 프리셋은 본문 별도 줄에도 등장
        for pre in ("안정형", "하이브리드", "공격형"):
            presets[pre] += len(re.findall(rf"계산기[^\n]*{pre}", txt))

        all_rets.extend(post_rets)
        neg_rets.extend([v for v in post_rets if v < 0])
        per_post.append((date, regime, len(items), len(post_rets),
                         min(post_rets) if post_rets else None))

    print(f"{'날짜':<10}{'체제':<14}{'종목':>5}{'수익률수':>9}{'최저%':>9}")
    for d, rg, ni, nr, mn in per_post:
        print(f"{d:<10}{rg:<14}{ni:>5}{nr:>9}{('' if mn is None else f'{mn:.2f}'):>9}")

    print(f"\n=== 체제 분포 === {dict(regimes)}")
    print(f"=== 프리셋 언급 === {dict(presets)}")
    print(f"\n종목-거래 헤더 총 {trades}건 · 수익률 수치 총 {len(all_rets)}개")
    if all_rets:
        print(f"수익률 범위 {min(all_rets):.2f}% ~ {max(all_rets):.2f}% · 평균 {sum(all_rets)/len(all_rets):.2f}%")
    print(f"🔴 음수 수익률: {len(neg_rets)}개 ({len(neg_rets)/max(1,len(all_rets))*100:.1f}%)")
    if neg_rets:
        print(f"   음수 표본: {sorted(neg_rets)[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
