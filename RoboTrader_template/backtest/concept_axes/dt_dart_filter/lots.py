"""체결 · 정지 · 청산 — 스펙 §3-4.

- 체결 = `theme_rank.bandfill.band_fill`(시가 ≤ 상한 → 시가 · 시가 > 상한 ∧ 저가 ≤ 상한 → 상한 · 그 밖 미체결).
- 정지(거래량 ≤0 또는 결측) = 진입일이면 «진입 불가» · 보유 중이면 경로에서 빼서(봉 결측) 재개 뒤 첫 봉에서 판정.
- 청산 = `exitsim8.simulate_lot`(손절 우선) · 같은 봉 동시 터치 로트만 익절 우선 판으로 치환.
- 보유일 탐침 없음(KOSPI 달력 `open_phase` 만) — 계획 «스펙과 다른 점» 3.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, Set

import numpy as np
import pandas as pd

from backtest.concept_axes.candidate_ledger import run as R
from backtest.concept_axes.candidate_ledger.tool_calibration.run_calib import episodes
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import sizing as Z
from backtest.concept_axes.ledger8 import sources8 as SRC8
from backtest.concept_axes.theme_rank.bandfill import FILL_BAND, FILL_OPEN, band_fill

from . import settings as S

RULES = X.ExitRules(0.10, 0.10, 10, source="spec 2026-10-10 §3-4")


def _no_probe(pos, d):
    return None


def halt_dates(px: pd.DataFrame) -> Dict[str, Set[date]]:
    m = ~(px["volume"].astype(float) > 0)
    out: Dict[str, Set[date]] = defaultdict(set)
    for c, t in zip(px.loc[m, "stock_code"], px.loc[m, "date"]):
        out[str(c)].add(pd.Timestamp(t).date())
    return dict(out)


def simulate_candidate(env, code: str, scan_d: date, halts: Set[date], rules: X.ExitRules = RULES) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(stock_code=code, scan_date=scan_d)
    bars = env.bars(code)
    db = bars.get(scan_d)
    if db is None:
        return dict(base, status="no_scan_bar")
    hi = float(db.close) * (1.0 + S.BAND_UP)
    d1 = env.next_day(scan_d)
    if d1 is None:
        return dict(base, status="no_next_day")
    if d1 in halts:
        return dict(base, status="halt_entry", entry_date=d1)
    b1 = bars.get(d1)
    if b1 is None or (code, d1) in env.bad_open or not (b1.open > 0):
        return dict(base, status="no_bar", entry_date=d1)
    f = band_fill(float(b1.open), float(b1.low), hi)
    if f.status not in (FILL_OPEN, FILL_BAND):
        return dict(base, status="no_fill", entry_date=d1)
    price = float(f.price)
    basis = X.BASIS_D_OPEN if f.status == FILL_OPEN else X.BASIS_UPPER
    pos = X.Pos(code, d1, SRC8.aware(datetime.combine(d1, R.ENTRY_TIME)), price, Z.arm_b_qty(price).qty, basis)
    clean = {d: b for d, b in bars.items() if d not in halts}
    path = R.build_path(env.cal, env.cal_idx, clean, d1, rules.max_hold_days)
    ex = X.simulate_lot(pos, rules, path, _no_probe)
    both = X.FLAG_SL_TP_BOTH in list(ex.flags)
    ret_sl = float(ex.ret_pct) if ex.ret_pct is not None else float("nan")
    ret_tp = rules.tp * 100.0 if both else ret_sl
    return dict(base, status="filled", fill=f.status, entry_date=d1, entry_price=price, exit_date=ex.exit_date,
                exit_reason=ex.reason, hold_days=ex.hold_days, ret_sl=ret_sl, ret_tp=ret_tp, both=both,
                unresolved=not ex.closed, halted_in_path=any(b is None for _, _, b in path),
                flags=";".join(str(x) for x in ex.flags))


def episode_first(stock: np.ndarray, cal_i: np.ndarray) -> np.ndarray:
    """전략 1개 · 종목별 달력 순번이 직전 행과 1 넘게 벌어지면 새 에피소드(`run_calib.episodes` 그대로)."""
    codes = pd.factorize(np.asarray(stock))[0]
    _eid, first = episodes(np.zeros(len(codes), dtype=np.int64), codes.astype(np.int64),
                           np.asarray(cal_i, dtype=np.int64))
    return first
