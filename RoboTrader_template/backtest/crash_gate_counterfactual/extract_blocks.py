# -*- coding: utf-8 -*-
"""급락게이트 차단 이벤트 추출 — `PREREG.md` §1 그대로.

🔑 **모집단은 `매수 판단 스킵: 시장급락`(`trading_context`) 줄이다.**
   `[시장방향성필터] 매수 차단` 줄은 60초 캐시 «미스»에만 남아 실제의 ~1/9 만 잡는다
   (2026-08-03 실측: 차단줄 323 vs 실제 2,909).

라이브 트리 import 0건(표준 라이브러리만) · DB 미사용 · 로그는 읽기만 한다.
"""
from __future__ import annotations

import glob
import re
import sys
from collections import Counter
from pathlib import Path

LOGS = Path(__file__).resolve().parents[2] / "logs"

# `2026-08-03 09:02:33 | trading_context | INFO | 매수 판단 스킵: 시장급락 (KOSPI -3.43% (임계값: -2.5%))`
RE_SKIP = re.compile(
    r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) \| (\S+) \| INFO \| "
    r"매수 판단 스킵: 시장급락 \((\w+) ([-\d.]+)%")
# `... | strategy.MinerviniVolumeDryupStrategy | INFO | [on_tick] 매수신호: 093370(BUY, ...`
RE_ONT = re.compile(
    r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \| strategy\.(\w+) .*\[on_tick\] 매수신호: (\w+)\(BUY")
# `... | strategy.Xxx | INFO | 🧾 [PAPER] 매수 시그널: 093370 @ 9,000 (추천 333주) | ...`
RE_SIG = re.compile(
    r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \| strategy\.(\w+) .*매수 시그널: (\w+) @ ([\d,]+)")

BACK_ONT = 3   # §1: 스킵 줄 기준 위로 ≤3줄
BACK_SIG = 5   # §1: 위로 ≤5줄


def extract() -> tuple[list[dict], Counter]:
    """(이벤트 목록, 결측 카운터). 이벤트는 (날짜,시각,전략,종목) 중복 제거된 원자 단위."""
    seen: set = set()
    ev: list[dict] = []
    miss = Counter()
    # 🔴 한 날짜에 로그 파일이 2~3개 있다(봇 재기동) — 전수 글로브 후 키로 중복 제거.
    for f in sorted(glob.glob(str(LOGS / "robotrader_template_2026*.log"))):
        lines = Path(f).read_text(encoding="utf-8", errors="replace").split("\n")
        for i, ln in enumerate(lines):
            m = RE_SKIP.match(ln)
            if not m:
                continue
            date, time, logger, index, chg = m.groups()
            if logger == "__main__":
                miss["구로그(종목 귀속 불가)"] += 1
                continue
            code = strat = None
            for j in range(i - 1, max(-1, i - 1 - BACK_ONT), -1):
                o = RE_ONT.match(lines[j])
                if o:
                    strat, code = o.groups()
                    break
            if code is None:
                miss["매수신호 줄 없음"] += 1
                continue
            price = None
            for j in range(i - 1, max(-1, i - 1 - BACK_SIG), -1):
                s = RE_SIG.match(lines[j])
                # 🔴 종목·전략이 «둘 다» 일치할 때만 채택 (대칭 확인)
                if s and s.group(2) == code and s.group(1) == strat:
                    price = float(s.group(3).replace(",", ""))
                    break
            if price is None:
                miss["시그널가 없음"] += 1
                continue
            key = (date, time, strat, code)
            if key in seen:
                miss["중복(로그 파일 겹침)"] += 1
                continue
            seen.add(key)
            ev.append(dict(date=date, time=time, strategy=strat, code=code,
                           price=price, index=index, chg=float(chg)))
    return ev, miss


def first_per_stock_day(ev: list[dict]) -> list[dict]:
    """§2 — 단위 = (날짜, 종목). 진입가는 «첫» 차단 시각의 시그널가."""
    best: dict = {}
    for e in ev:
        k = (e["date"], e["code"])
        if k not in best or e["time"] < best[k]["time"]:
            best[k] = e
    return [best[k] for k in sorted(best)]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ev, miss = extract()
    uniq = first_per_stock_day(ev)
    print(f"차단 이벤트 {len(ev):,}건 · 결측 {dict(miss)}")
    print(f"고유 (날짜,종목) {len(uniq):,}건 · 차단일 {len({e['date'] for e in ev})}일 "
          f"· 고유 종목 {len({e['code'] for e in ev})}개")
    per = Counter(e["date"] for e in ev)
    print("일자별:", dict(sorted(per.items())))
