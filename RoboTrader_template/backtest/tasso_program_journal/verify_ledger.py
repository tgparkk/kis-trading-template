# -*- coding: utf-8 -*-
"""원장 회수율 게이트 — 원문 3글 ↔ ledger_legs.csv ↔ ledger_trades.csv 대칭 검증.

라이브 트리 import 0건(표준 라이브러리만). `utils.logger` 를 건드리지 않는다.

게이트:
  G-A  저자 항목번호가 각 글에서 1..N 연속인가 (결번 = 누락)
  G-B  원문의 매매행 수 == ledger_trades 행 수 (양방향)
  G-C  원문의 모든 퍼센트 수치 == ledger_legs 수치 (다중집합 양방향)
  G-D  ledger_trades.n_legs == ledger_legs 실제 레그 수 (건별)

실패하면 비영(非零) 종료한다.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
# 🔴 원문 평문은 저장소에 없다(본문 전문 인용 = 타인 저작물, .gitignore 참조).
#    보관소를 먼저 보고, 없으면 로컬 raw/ 로 떨어진다. 둘 다 없으면 게이트는 재현 불가다.
ARCHIVE = Path(r"D:/archive/tasso-program-journal-20260814")
RAW = ARCHIVE if ARCHIVE.is_dir() else BASE / "raw"

POSTS = {
    "224364189017": "2026-07-31",
    "224371400049": "2026-08-07",
    "224378680510": "2026-08-14",
}

ITEM_MARK = "통계기반 자동매매"
# 항목 번호는 마침표/쉼표 둘 다 쓰이고, 아예 없는 행도 있다(가온칩스).
NUM_RE = re.compile(r"^\s*(\d+)\s*[.,]\s*")
PCT_RE = re.compile(r"-?\d+\.\d+")

failures: list[str] = []


def parse_raw():
    """원문에서 (log_no -> [(item_no|None, stock, [pct...])]) 를 뽑는다."""
    out: dict[str, list] = {}
    for log_no in POSTS:
        path = RAW / f"post_{log_no}.txt"
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if ITEM_MARK not in line:
                continue
            parts = [p.strip() for p in line.split("/")]
            if len(parts) < 3:
                failures.append(f"[parse] {log_no}: '/' 구분 실패 -> {line!r}")
                continue
            head = parts[0]
            m = NUM_RE.match(head)
            item_no = int(m.group(1)) if m else None
            stock = NUM_RE.sub("", head).strip()
            pcts = [float(x) for x in PCT_RE.findall(" / ".join(parts[2:]))]
            rows.append((item_no, stock, pcts))
        out[log_no] = rows
    return out


def load_csv(name):
    with (BASE / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    raw = parse_raw()
    legs = load_csv("ledger_legs.csv")
    trades = load_csv("ledger_trades.csv")

    # ---- G-A: 항목번호 1..N 연속 -------------------------------------------
    for log_no, rows in raw.items():
        nums = [n for n, _, _ in rows if n is not None]
        n_total = len(rows)
        expected = set(range(1, n_total + 1))
        got = set(nums)
        missing = sorted(expected - got - {1})  # 1번은 번호 없이 쓰인 사례가 있다
        if missing:
            failures.append(f"[G-A] {log_no}: 항목번호 결번 {missing} (총 {n_total}행)")
        if len(nums) != len(set(nums)):
            dup = [k for k, v in Counter(nums).items() if v > 1]
            failures.append(f"[G-A] {log_no}: 항목번호 중복 {dup}")

    # ---- G-B: 매매행 수 양방향 ---------------------------------------------
    for log_no, rows in raw.items():
        n_raw = len(rows)
        n_led = sum(1 for t in trades if t["post_log_no"] == log_no)
        if n_raw != n_led:
            failures.append(f"[G-B] {log_no}: 원문 {n_raw}행 != trades {n_led}행")

    # ---- G-C: 퍼센트 다중집합 양방향 ---------------------------------------
    for log_no, rows in raw.items():
        raw_c = Counter(round(p, 2) for _, _, pcts in rows for p in pcts)
        led_c = Counter(
            round(float(l["ret_pct"]), 2) for l in legs if l["post_log_no"] == log_no
        )
        only_raw = raw_c - led_c
        only_led = led_c - raw_c
        if only_raw:
            failures.append(f"[G-C] {log_no}: 원문에만 있는 수치 {sorted(only_raw.elements())}")
        if only_led:
            failures.append(f"[G-C] {log_no}: 원장에만 있는 수치 {sorted(only_led.elements())}")

    # ---- G-D: 건별 레그 수 --------------------------------------------------
    leg_cnt: dict[tuple, int] = defaultdict(int)
    for l in legs:
        leg_cnt[(l["post_log_no"], l["item_no"])] += 1
    for t in trades:
        key = (t["post_log_no"], t["item_no"])
        if leg_cnt.get(key, 0) != int(t["n_legs"]):
            failures.append(
                f"[G-D] {key} {t['stock_name']}: n_legs={t['n_legs']} != 실제 {leg_cnt.get(key, 0)}"
            )

    # ---- 요약 ---------------------------------------------------------------
    print(f"글 {len(raw)}개 / 매매건 {len(trades)} / 매도레그 {len(legs)}")
    for log_no, date in POSTS.items():
        rows = raw[log_no]
        n_legs = sum(1 for l in legs if l["post_log_no"] == log_no)
        print(f"  {date} {log_no}: {len(rows)}건 {n_legs}레그")
    loss = sum(1 for l in legs if l["is_loss"] == "1")
    print(f"손실 레그 {loss} / 익절 레그 {len(legs) - loss}")
    print(f"미완결(~) 레그 {sum(1 for l in legs if l['leg_open_ended'] == '1')}")

    if failures:
        print("\n=== 게이트 실패 ===")
        for f in failures:
            print(" ", f)
        return 1
    print("\n모든 게이트 통과 (G-A/B/C/D)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
