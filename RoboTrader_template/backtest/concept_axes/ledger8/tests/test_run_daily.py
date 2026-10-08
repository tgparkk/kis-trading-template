"""run_daily — 창 고르기·쓰기 경로 가드·3전략 B1 요약(순수 · DB·라이브 로그 없음)."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from backtest.concept_axes.ledger8 import run_daily as RD

CAL = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]


def test_window_last_n_trading_days_including_date():
    assert RD.window(CAL, date(2026, 10, 8), 5) == CAL
    assert RD.window(CAL, date(2026, 10, 7), 3) == [date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 7)]
    with pytest.raises(ValueError):
        RD.window(CAL, date(2026, 10, 5), 5)          # 대체공휴일 — 달력에 없다


def test_live_tree_write_guard(tmp_path):
    assert RD._under(RD.LIVE_ROOT / "RoboTrader_template" / "x", RD.LIVE_ROOT)
    assert not RD._under(tmp_path, RD.LIVE_ROOT)
    assert RD.main(["2026-10-08", "--out-root", str(RD.LIVE_ROOT / "out")]) == 2   # DB 열기 전에 거절


def _lots(path: Path, rows):
    cols = ["arm", "tier", "strategy", "code", "entry_date", "notional_won", "pnl_won", "exit_status"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(dict(zip(cols, r)))


def test_render_sums_focus3_b1_main_and_splits_today(tmp_path):
    day, ma20, mnv = "daytrading_3methods_breakout", "book_pullback_ma20", "minervini_volume_dryup"
    p = tmp_path / "lots_b1.csv"
    _lots(p, [("B1", "main", day, "000001", "2026-10-07", "1000000", "50000", "closed"),
              ("B1", "main", day, "000002", "2026-10-08", "1000000", "-20000", "open"),
              ("B1", "main", ma20, "000003", "2026-10-08", "500000", "", "open"),           # 손익 불명
              ("B1_ext", "ext", day, "000004", "2026-10-08", "1000000", "99999", "open"),   # ext 제외
              ("B1", "main", "rs_leader", "000005", "2026-10-08", "1000000", "99999", "open")])  # 3전략 밖
    md = RD.render(date(2026, 10, 8), CAL, tmp_path, p, ["x 복사"])
    assert f"| {day} | 2 | +30,000 | 2,000,000 | +1.50% | 1(1) / 1 | 0 |" in md
    assert f"| {ma20} | 1 | +0 | 0 | — | 0(0) / 1 | 1 |" in md
    assert f"| {mnv} | 0 | +0 | 0 | — | 0(0) / 0 | 0 |" in md
    today = md.split("### 당일 진입분")[1]
    assert f"| {day} | 1 | -20,000 | 1,000,000 | -2.00% | 0(0) / 1 | 0 |" in today
    assert "**매수 체결만**" in md                                                    # 10-08 규칙
