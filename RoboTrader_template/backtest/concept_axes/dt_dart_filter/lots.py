"""체결 · 정지 · 청산 — 스펙 §3-4.

- 체결 = `theme_rank.bandfill.band_fill`(시가 ≤ 상한 → 시가 · 시가 > 상한 ∧ 저가 ≤ 상한 → 상한 · 그 밖 미체결).
- 정지일 = 거래량 ≤0(또는 결측) 행 ∪ 내부 결측 거래일(종목 첫 행~끝 행 사이 달력 거래일 중 행 없는 날 · 사장님 A-5 ·
  2024-03-13 공정 경계 전후 같은 정의) = 진입일이면 «진입 불가» · 보유 중이면 재개 첫 봉 «시가»로 무조건 청산
  (`halt_resume` · 스펙 :84 · 밴드 안 재개여도 계속 보유하지 않음) · 창 끝까지 정지면 마지막 값 + «미해소».
- 청산 = `exitsim8.simulate_lot`(손절 우선) · 같은 봉 동시 터치 로트만 익절 우선 판으로 치환.
- 보유일 탐침 없음(KOSPI 달력 `open_phase` 만) — 계획 «스펙과 다른 점» 3.
- `ca_path` = 진입 다음 거래일부터 k=1..10 고정 창 안 기업행위 의심 봉(critic B2 · 인쇄 전용 표시 · 청산 규칙 불변).
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, Sequence, Set

import numpy as np
import pandas as pd

from backtest.concept_axes.candidate_ledger import run as R
from backtest.concept_axes.candidate_ledger.tool_calibration.run_calib import episodes
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import sizing as Z
from backtest.concept_axes.ledger8 import sources8 as SRC8
from backtest.concept_axes.replayer import flags as FL
from backtest.concept_axes.theme_rank.bandfill import FILL_BAND, FILL_OPEN, band_fill

from . import settings as S

RULES = X.ExitRules(0.10, 0.10, 10, source="spec 2026-10-10 §3-4")
EXIT_HALT_RESUME = "halt_resume"          # 보유 중 정지 → 재개일 시가 강제 청산(스펙 :84)
FLAG_HALT_RESUME = "halt_resume_open"


def _no_probe(pos, d):
    return None


def interior_missing(px: pd.DataFrame, cal: Sequence[date]) -> Dict[str, Set[date]]:
    """종목별 «내부 결측 거래일» — 그 종목 첫 행 날짜와 끝 행 날짜 사이(양끝 제외) 달력 거래일 중 행이 없는 날(사장님 A-5).

    첫 행 앞(상장 전)·끝 행 뒤(상폐·창 끝)는 내부가 아니다. 달력 밖 날짜의 행(예: 일요일 1행)은 범위를 정할 때만 쓴다.
    """
    cal = sorted(cal)
    out: Dict[str, Set[date]] = {}
    for code, g in px.groupby("stock_code", sort=False):
        days = {pd.Timestamp(t).date() for t in g["date"]}
        lo, hi = min(days), max(days)
        miss = {d for d in cal[bisect.bisect_right(cal, lo):bisect.bisect_left(cal, hi)] if d not in days}
        if miss:
            out[str(code)] = miss
    return out


def halt_dates(px: pd.DataFrame, cal: Sequence[date]) -> Dict[str, Set[date]]:
    """정지일 = 거래량 ≤0(또는 결측) 행의 날 ∪ 내부 결측 거래일(`interior_missing` · 사장님 A-5)."""
    m = ~(px["volume"].astype(float) > 0)
    out: Dict[str, Set[date]] = defaultdict(set)
    for c, t in zip(px.loc[m, "stock_code"], px.loc[m, "date"]):
        out[str(c)].add(pd.Timestamp(t).date())
    for c, ds in interior_missing(px, cal).items():
        out[c] |= ds
    return dict(out)


def _simulate_with_halt_exit(pos: X.Pos, rules: X.ExitRules, path, halts: Set[date], price: float) -> X.ExitOut:
    """보유 중 첫 정지일 «전»까지 평소 규칙으로 돌리고, 그때까지 안 닫혔으면 재개 첫 봉 시가로 무조건 청산(스펙 :84).

    재개 봉이 창 안에 없으면(창 끝까지 정지) 평소대로 마지막 값 + 미해소.
    """
    hi = next((i for i, (_k, d, _b) in enumerate(path) if i > 0 and d in halts), None)
    if hi is None:
        return X.simulate_lot(pos, rules, path, _no_probe)
    ex = X.simulate_lot(pos, rules, path[:hi], _no_probe)
    if ex.closed:
        return ex
    res = next(((k, d, b) for k, d, b in path[hi:] if b is not None), None)
    if res is None:
        return X.simulate_lot(pos, rules, path, _no_probe)
    k, d, b = res
    px_open = float(b.open)
    return X.ExitOut("closed", EXIT_HALT_RESUME, d, px_open, (px_open - price) / price * 100.0, k,
                     [FLAG_HALT_RESUME], X.PHASE_OPEN)


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
    ex = _simulate_with_halt_exit(pos, rules, path, halts, price)
    both = X.FLAG_SL_TP_BOTH in list(ex.flags)
    ret_sl = float(ex.ret_pct) if ex.ret_pct is not None else float("nan")
    ret_tp = rules.tp * 100.0 if both else ret_sl
    end = ex.exit_date if ex.closed and ex.exit_date is not None else path[-1][1]   # 미해소 = 경로 마지막 날까지
    halted = any(d1 < h <= end for h in halts)
    return dict(base, status="filled", fill=f.status, entry_date=d1, entry_price=price, exit_date=ex.exit_date,
                exit_reason=ex.reason, hold_days=ex.hold_days, ret_sl=ret_sl, ret_tp=ret_tp, both=both,
                unresolved=not ex.closed, halted_in_path=halted,
                flags=";".join(str(x) for x in ex.flags))


def episode_first(stock: np.ndarray, cal_i: np.ndarray) -> np.ndarray:
    """전략 1개 · 종목별 달력 순번이 직전 행과 1 넘게 벌어지면 새 에피소드(`run_calib.episodes` 그대로)."""
    codes = pd.factorize(np.asarray(stock))[0]
    _eid, first = episodes(np.zeros(len(codes), dtype=np.int64), codes.astype(np.int64),
                           np.asarray(cal_i, dtype=np.int64))
    return first


def ca_flag_days(px: pd.DataFrame, cal_idx: Dict[date, int]) -> Dict[str, np.ndarray]:
    """종목별 «기업행위 의심 봉» 의 거래일 순번(오름차순) — critic B2.

    봉 = FD1 동결식 `flag_cliff`(`replayer.flags.compute_bar_flags` 그대로 · 문턱을 여기서 바꾸지 않음)
       ∨ adj_factor 계단 |adj_t − adj_{t−1}| > `S.CA_ADJ_EPS`(NULL = 1 · FD1 COALESCE 관례)
       ∨ |시가/전 종가 − 1| > `S.CA_JUMP` ∨ |종가/전 종가 − 1| > `S.CA_JUMP`.
    전 종가 = 그 종목 직전 «행» 의 종가(`compute_bar_flags` 의 gap_open·ret_1d 그대로). 입력 = 로더 순서((종목, 날짜) 오름차순).
    """
    if px.empty:
        return {}
    fl = FL.compute_bar_flags(px)
    adj = (px["adj_factor"].astype(float) if "adj_factor" in px.columns
           else pd.Series(1.0, index=px.index)).fillna(1.0)
    step = (adj - adj.groupby(px["stock_code"].to_numpy()).shift(1)).abs() > S.CA_ADJ_EPS
    jump = (fl["gap_open"].abs() > S.CA_JUMP) | (fl["ret_1d"].abs() > S.CA_JUMP)
    bad = (fl["flag_cliff"].astype(bool) | step | jump).to_numpy(dtype=bool)
    out: Dict[str, list] = defaultdict(list)
    for c, t in zip(px["stock_code"].to_numpy()[bad], px["date"].to_numpy()[bad]):
        i = cal_idx.get(pd.Timestamp(t).date())
        if i is not None:
            out[str(c)].append(i)
    return {c: np.array(sorted(v), dtype=np.int64) for c, v in out.items()}


def ca_path(flag_days: Dict[str, np.ndarray], code: str, entry: date, cal_idx: Dict[date, int],
            k: int = S.CA_WINDOW_TD) -> bool:
    """진입일 순번 e 에 대해 순번 e+1..e+k(고정 창 · 실제 청산과 무관) 안에 의심 봉이 하루라도 있으면 참."""
    arr = flag_days.get(str(code))
    e = cal_idx.get(entry)
    if arr is None or e is None or not len(arr):
        return False
    j = int(np.searchsorted(arr, e + 1, side="left"))
    return j < len(arr) and int(arr[j]) <= e + k
