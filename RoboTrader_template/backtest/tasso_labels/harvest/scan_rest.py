"""전문 정독하지 않은 20건에서 「메커니즘을 담은 문장」만 전수 추출.

정독 완료: 28_{20260729,20260207,20260306,20260415,20251204,20260728,20260115,20250622,20260122}
나머지 20건은 수치·규칙을 담은 문장만 뽑아 새 사실 유무를 확인한다.
"""
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

READ = {"20260729", "20260207", "20260306", "20260415", "20251204",
        "20260728", "20260115", "20250622", "20260122"}
# 메커니즘 신호어
SIG = re.compile(
    r"(상승폭|하락폭|반등폭|사분위|분위수|Q1|Q3|HDR|신뢰구간|고점\s?대비|계산기|"
    r"비중|차수|분할\s?매수|분할\s?매도|손절|평단|시가총액|거래대금|표본|건 중|데이터)")
NUM = re.compile(r"\d")


def main() -> int:
    hits = 0
    for f in sorted(glob.glob("text2/*.txt")):
        base = os.path.basename(f)
        if base[3:11] in READ:
            continue
        lines = [l.strip() for l in open(f, encoding="utf-8").read().split("\n")]
        picked = [l for l in lines
                  if SIG.search(l) and NUM.search(l) and 15 < len(l) < 220
                  and not l.startswith("▲")]
        if not picked:
            continue
        print(f"\n=== {base[:11]} ({len(picked)}문장) ===")
        for l in picked[:9]:
            print(f"  · {l}")
        hits += len(picked)
    print(f"\n총 {hits}문장 스캔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
