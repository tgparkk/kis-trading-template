"""진입일(k=0) 분봉 진입·당일 청산 — 순수 함수(DB·전략 인스턴스 없음).

분봉 배열 레이아웃 = `[381, 6]`(float) — 행 0..379 = 09:00..15:19 분(분 «시작» 시각) · 행 380 = 15:30 봉(종가 단일가 ·
2026-09 부터 대부분 없음 → NaN). 열 = open · high · low · close · volume · amount(**당일 누적 거래대금**).
빈 분은 `data.assemble_day` 가 직전 종가로 평평하게 채운다(그날 첫 거래 전은 NaN = 가격 없음 = 안 삼).

진입(설계 10-08 §3 · EXPERT_SYSTEM 바뀌는 점 #4)
  기준 arm 시작 분(`BASE_ARMS`) ~ 15:19 분을 차례로 보며 «현재가(그 분 종가) → `round_to_tick` → 밴드 검사 → 규칙 훅
  `pred`» 가 처음 참인 분 t 에 산다. 기준 arm = `R0`(≥09:02 · 시점 규칙의 짝) · `R0_0905`(≥09:05 · 거르기 규칙 R4·R5 의
  남김·걸러짐 두 군 공통 진입 규약 · 이동 몫 = R0_0905 − R0). 반올림 뒤 밴드 검사는 라이브 순서
  (`core/trading_decision_engine.py:507-519`)를 따른다.
  `pred` 반환 = True(산다) · False(그 분 skip) · None(판단 불가 → 그 분 skip · `DayResult.undetermined_minutes` 로 셈).
  거르기 규칙은 `label_day` 가 09:05 view(행 0..4 완성 봉 + 09:05 종가)로 keep|filter|undetermined 를 한 번 낸다.
  민감도:
  (b) `px_next_open` = t+1 분 시가(반올림) — **밴드 안일 때만 · 밴드 밖이면 None(결측)**. 다음 분으로 넘기지 않는다
      (그 로트는 (b) 열에서 결측 · 건수 인쇄). t 가 15:19 면 다음 분이 없어 None.
  (c) `find_entry_band_edge` = pred 가 참이고 그 분 고저가 밴드에 닿은 첫 분 — **종가가 밴드 안이면 그 종가(반올림)**,
      밖이면 닿은 **경계값**(= 일봉 `band_touch` 의 분 단위판 · 성적 상한 · 본 진입보다 이른 분일 수 있어
      `DayResult.band_edge` 로 따로 돌려준다).
🔑 룩어헤드 계약: `pred` 는 `view_upto(bars, t)` 만 받는다 — 행 0..t-1 = 완성 봉 전체 · 행 t = **종가(현재가)만**
  (open·high·low·volume·amount = NaN) · t 뒤 봉 0개. 테스트가 «미래 봉을 흔들어도 판정 불변»으로 고정한다.

당일 청산(설계 §4) — 진입 다음 분(t+1)부터 15:19 분까지 1분씩
  익절: 시가 ≥ 선 → 시가(`gap_tp_open`) · 고가 ≥ 선 → 선 가격.
  손절: **09:05 분부터**(라이브 `position_monitor` 09:05 전 생략) · 시가 ≤ 선 → 시가(`sl_gap_open`) ·
        저가 ≤ 선 → 선 가격.
  같은 분에 둘 다 → 손절 우선 + `sl_tp_same_minute`(시가가 익절선 위 = 갭 익절 조건이어도 저가가 손절선에 닿으면 손절 ·
  그 경우 `gap_tp_overridden` 도 붙여 건수를 따로 인쇄한다 · 초안 §3).
  ⚠ 사전등록 결정(초안 §3)이다 — k≥1 일봉 경로(ledger8 → `cap_skip_ledger/sim.py:135-147`)는 «갭 익절(시가) → 갭 손절
  (시가) → 장중 손절 우선» 순이라 시가 갭 익절이 먼저다. 두 경로 규약이 다름을 알고 쓴다(리뷰 A2).
  09:05 전에 선 아래로 갔으면 `sl_deferred_pre0905`.
  15:30 봉은 보지 않는다(15:20~ 신규 주문 불가). 미청산이면 `DayResult.pos`(ledger8 `exitsim8.Pos`)를 돌려준다 —
  k≥1 은 `continue_daily` 가 `exitsim8.simulate_lot` 일봉 경로로 넘긴다(2단계 · A1: k=0 탐침은 `k0_probe` 1회 ·
  simulate_lot 은 k=0 터치·탐침을 다시 보지 않음).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from backtest.concept_axes.ledger8.exitsim8 import (FLAG_K0_DATA, FLAG_NO_D_TOUCH, PHASE_ENTRY, Bar, ExitOut, ExitRules,
                                                    PathT, Pos, Probe, simulate_lot)
from backtest.concept_axes.ledger8.sizing import arm_b_qty
from utils.price_utils import round_to_tick

# ── 배열 레이아웃 ─────────────────────────────────────────────────────────
F_OPEN, F_HIGH, F_LOW, F_CLOSE, F_VOL, F_AMT = range(6)
N_FIELDS = 6
N_CONT = 380                 # 09:00..15:19 연속장 분
IDX_1530 = 380               # 15:30 종가 단일가 봉
N_SLOTS = 381
IDX_ENTRY_START = 2          # 09:02 — 첫 on_tick 실측(설계 §3-2)
IDX_ENTRY_0905 = 5           # 09:05 — 거르기 규칙 정보 완성(09:04 봉 완성) 뒤 첫 분
IDX_FILTER_AT = 5            # 거르기 라벨 판정 view = view_upto(bars, 5)
IDX_ENTRY_END = 379          # 15:19 — 15:20~ 동시호가
IDX_SL_START = 5             # 09:05 — position_monitor 손절 시작
_HIDDEN_AT_T = [F_OPEN, F_HIGH, F_LOW, F_VOL, F_AMT]

BASIS_M_CLOSE = "m_close"
EXIT_TP = "tp"
EXIT_SL = "sl"
FLAG_GAP_TP = "gap_tp_open"
FLAG_SL_GAP = "sl_gap_open"
FLAG_SL_TP_SAME = "sl_tp_same_minute"
FLAG_GAP_TP_OVERRIDDEN = "gap_tp_overridden"   # 같은 분 손절 중 시가가 익절선 이상(갭 익절 조건)이었던 건
FLAG_SL_DEFERRED = "sl_deferred_pre0905"

SKIP_NO_PRICE = "no_price"           # 창 안에 가격 있는 분이 하나도 없음
SKIP_NO_ENTRY = "no_entry"           # 가격은 있었지만 밴드∧pred 가 끝까지 거짓

BASE_R0 = "R0"
BASE_R0_0905 = "R0_0905"
BASE_ARMS: Dict[str, int] = {BASE_R0: IDX_ENTRY_START, BASE_R0_0905: IDX_ENTRY_0905}

LABEL_KEEP = "keep"
LABEL_FILTER = "filter"
LABEL_UNDETERMINED = "undetermined"


def idx_to_time(i: int) -> str:
    """행 번호 → 'HHMMSS'(분 시작)."""
    if i == IDX_1530:
        return "153000"
    if not 0 <= i < N_CONT:
        raise ValueError(f"분 행 범위 밖: {i}")
    m = 9 * 60 + i
    return f"{m // 60:02d}{m % 60:02d}00"


def time_to_idx(hhmmss: str) -> Optional[int]:
    """'HHMMSS' → 행 번호. 09:00~15:19 와 15:30 만 · 나머지(15:20~15:29 · 장 전 · 초≠00)는 None."""
    s = str(hhmmss).strip()
    if len(s) != 6 or not s.isdigit() or s[4:] != "00":
        return None
    if s == "153000":
        return IDX_1530
    i = int(s[:2]) * 60 + int(s[2:4]) - 9 * 60
    return i if 0 <= i < N_CONT else None


@dataclass(frozen=True)
class DayCtx:
    """code-day 하나의 정적 문맥(장 시작 전에 아는 것만)."""
    code: str
    day: date
    band_lo: Optional[float] = None      # 반올림된 현재가가 이 값 이상이어야 함(None = 하한 없음)
    band_hi: Optional[float] = None      # 이 값 이하(None = 상한 없음)
    prev_close: Optional[float] = None
    prev_day_volume: Optional[float] = None   # 전일 일봉 거래량(진입일 주식 단위 · data.py)
    corp_event: bool = False             # D~D+1 사이 corp_event → R5 undetermined


Pred = Callable[[np.ndarray, DayCtx], Optional[bool]]     # None = 판단 불가(그 분 skip · 셈)
Label = Callable[[np.ndarray, DayCtx], str]               # keep | filter | undetermined


def view_upto(bars: np.ndarray, t: int) -> np.ndarray:
    """룩어헤드 계약 — 행 0..t 사본(float64) · 행 t 는 종가만 남기고 나머지 NaN."""
    v = np.array(bars[: t + 1], dtype=np.float64, copy=True)
    v[t, _HIDDEN_AT_T] = np.nan
    return v


def in_band(px: float, ctx: DayCtx) -> bool:
    if ctx.band_lo is not None and px < ctx.band_lo:
        return False
    if ctx.band_hi is not None and px > ctx.band_hi:
        return False
    return True


@dataclass
class EntryFill:
    idx: int
    time: str
    px_raw: float                        # 그 분 종가(원값 · 반 호가 2.84% 대비)
    px: float                            # round_to_tick(종가) — 체결가(경계 모델은 경계값)
    px_next_open: Optional[float] = None


@dataclass
class DayExit:
    closed: bool
    reason: Optional[str] = None         # tp | sl | None(미청산)
    idx: Optional[int] = None
    time: str = ""
    px: Optional[float] = None
    ret_pct: Optional[float] = None
    flags: List[str] = field(default_factory=list)


@dataclass
class DayResult:
    entered: bool
    skip_reason: str = ""
    entry: Optional[EntryFill] = None
    exit: Optional[DayExit] = None
    pos: Optional[Pos] = None            # 미청산 → k≥1 로 넘길 포지션
    band_edge: Optional[EntryFill] = None   # 민감도 (c) 경계 모델 진입(청산은 2단계)
    base: str = "R0"                     # 기준 arm(진입 시작 분 · BASE_ARMS 키)
    undetermined_minutes: int = 0        # 시점 규칙 pred = None 이라 skip 한 밴드 안 분 수(진입 전까지)
    label: Optional[str] = None          # 거르기 규칙 라벨(keep|filter|undetermined) — 시점 규칙은 None


def _finite(x: float) -> bool:
    return bool(np.isfinite(x))


def _scan_entry(bars: np.ndarray, ctx: DayCtx, pred: Pred, start: int) -> Tuple[Optional[EntryFill], int]:
    """(진입, 판단 불가 분 수) — 판단 불가 = 밴드 안인데 pred 가 None 을 돌려준 분(진입 전까지만 셈)."""
    undetermined = 0
    for t in range(start, IDX_ENTRY_END + 1):
        raw = float(bars[t, F_CLOSE])
        if not _finite(raw) or raw <= 0:
            continue
        px = round_to_tick(raw)
        if not in_band(px, ctx):
            continue
        ok = pred(view_upto(bars, t), ctx)
        if ok is None:
            undetermined += 1
            continue
        if not ok:
            continue
        fill = EntryFill(t, idx_to_time(t), raw, px)
        if t + 1 <= IDX_ENTRY_END and _finite(float(bars[t + 1, F_OPEN])):
            nxt = round_to_tick(float(bars[t + 1, F_OPEN]))
            fill.px_next_open = nxt if in_band(nxt, ctx) else None
        return fill, undetermined
    return None, undetermined


def find_entry(bars: np.ndarray, ctx: DayCtx, pred: Pred, start: int = IDX_ENTRY_START) -> Optional[EntryFill]:
    """밴드 안 ∧ pred 가 처음 참인 분(start~15:19 · 기본 09:02). 없으면 None."""
    return _scan_entry(bars, ctx, pred, start)[0]


def find_entry_band_edge(bars: np.ndarray, ctx: DayCtx, pred: Pred,
                         start: int = IDX_ENTRY_START) -> Optional[EntryFill]:
    """민감도 (c) — pred 참 ∧ 그 분 [저가, 고가]가 밴드와 겹친 첫 분. 종가 안 = 종가(반올림) · 밖 = 닿은 경계값.

    pred 는 본 진입과 같은 view(p_t = 종가)로 판정한다 — 경계 체결 순간의 가격으로 다시 판정하지 않는다(None = skip)."""
    for t in range(start, IDX_ENTRY_END + 1):
        raw, h, lo = float(bars[t, F_CLOSE]), float(bars[t, F_HIGH]), float(bars[t, F_LOW])
        if not (_finite(raw) and _finite(h) and _finite(lo)) or raw <= 0:
            continue
        px = round_to_tick(raw)
        if in_band(px, ctx):
            edge = px
        elif ctx.band_hi is not None and px > ctx.band_hi and lo <= ctx.band_hi:
            edge = float(ctx.band_hi)
        elif ctx.band_lo is not None and px < ctx.band_lo and h >= ctx.band_lo:
            edge = float(ctx.band_lo)
        else:
            continue
        if pred(view_upto(bars, t), ctx) is True:
            return EntryFill(t, idx_to_time(t), raw, edge)
    return None


def label_day(bars: np.ndarray, ctx: DayCtx, label: Label) -> str:
    """거르기 규칙 라벨 — 09:05 view(행 0..4 완성 봉 + 09:05 종가)로 하루 한 번."""
    out = label(view_upto(bars, IDX_FILTER_AT), ctx)
    if out not in (LABEL_KEEP, LABEL_FILTER, LABEL_UNDETERMINED):
        raise ValueError(f"거르기 라벨 값 밖: {out!r}")
    return out


def _ret(entry: float, px: float) -> float:
    return (px - entry) / entry * 100.0


def simulate_day_exit(bars: np.ndarray, entry_idx: int, entry_px: float, tp: float, sl: float) -> DayExit:
    """진입 다음 분부터 15:19 분까지 분 단위 익절·손절(같은 분이면 손절 우선)."""
    tp_line = entry_px * (1.0 + tp)
    sl_line = entry_px * (1.0 - sl)
    flags: List[str] = []
    for m in range(entry_idx + 1, IDX_ENTRY_END + 1):
        o, h, lo = float(bars[m, F_OPEN]), float(bars[m, F_HIGH]), float(bars[m, F_LOW])
        if not (_finite(o) and _finite(h) and _finite(lo)):
            continue
        tp_hit = h >= tp_line
        sl_touch = lo <= sl_line
        if sl_touch and m < IDX_SL_START:
            if FLAG_SL_DEFERRED not in flags:
                flags.append(FLAG_SL_DEFERRED)
            sl_touch = False
        if sl_touch:
            gap = o <= sl_line
            px = o if gap else sl_line
            fl = flags + ([FLAG_SL_GAP] if gap else []) + ([FLAG_SL_TP_SAME] if tp_hit else [])
            if o >= tp_line:
                fl.append(FLAG_GAP_TP_OVERRIDDEN)
            return DayExit(True, EXIT_SL, m, idx_to_time(m), px, _ret(entry_px, px), fl)
        if tp_hit:
            gap = o >= tp_line
            px = o if gap else tp_line
            fl = flags + ([FLAG_GAP_TP] if gap else [])
            return DayExit(True, EXIT_TP, m, idx_to_time(m), px, _ret(entry_px, px), fl)
    return DayExit(False, flags=flags)


def neutral_touch_bar(pos: Pos) -> Bar:
    """진입가 평평 봉(시=고=저=종=진입가) — k=0 고저는 분봉 엔진이 이미 봤다는 표시(사전등록 §9 2단계 과제 A1).

    `exitsim8.entry_day` 는 basis ≠ D_open 이면 `pos.touch_bar` 로 터치를 본다 → 이 봉은 익절·손절 비율 0 이라
    (tp·sl > 0) 아무것도 닿지 않고, `touch_bar is not None` 이라 `FLAG_NO_D_TOUCH` 도 붙지 않는다."""
    px = float(pos.entry_price)
    return Bar(pos.entry_date, px, px, px, px)


def continue_daily(pos: Pos, rules: ExitRules, path: PathT, probe: Probe) -> ExitOut:
    """k ≥ 1 = `exitsim8.simulate_lot` 그대로(사전등록 §3) · k=0 은 다시 보지 않는다(A1).

    - k=0 데이터 청산 탐침은 호출자(`k0_probe`)가 분봉 청산 «전»에 1회 이미 돌렸다 → `simulate_lot` 에는
      진입일에 None 을 돌려주는 감싼 탐침을 넘긴다(`FLAG_K0_DATA` 중복 방지).
    - `touch_bar` = `neutral_touch_bar`(k=0 고저 재판정 없음 · `FLAG_NO_D_TOUCH` 없음) · path[0] 일봉은 끝까지 보유 때
      마감 평가(일봉 종가 · G2)로만 쓰인다.
    결과에 진입일 단계(`PHASE_ENTRY`)·두 플래그가 보이면 계약 위반 → RuntimeError."""
    if not (rules.tp > 0 and rules.sl > 0):
        raise ValueError(f"tp·sl 은 양수여야 평평 봉이 닿지 않는다: {rules}")
    p = Pos(pos.code, pos.entry_date, pos.entry_time, pos.entry_price, pos.qty, pos.entry_basis, neutral_touch_bar(pos))

    def probe_k1(q: Pos, day: date) -> Optional[str]:
        return None if day == q.entry_date else probe(q, day)

    ex = simulate_lot(p, rules, path, probe_k1)
    if ex.phase == PHASE_ENTRY or FLAG_NO_D_TOUCH in ex.flags or FLAG_K0_DATA in ex.flags:
        raise RuntimeError(f"k=0 재판정 흔적(A1 위반): {ex}")
    return ex


def k0_probe(pos: Pos, probe: Probe) -> Optional[str]:
    """진입 직후 데이터 청산 탐침 — 로트·체결 모델마다 정확히 1회(설계 10-08 §4 · 분봉 청산보다 먼저)."""
    return probe(pos, pos.entry_date)


def make_pos(ctx: DayCtx, idx: int, px: float) -> Pos:
    """진입 분 행 번호·체결가 → `Pos`(arm B 수량 · basis m_close · 진입 시각 = 분 시작)."""
    hh, mm = divmod(9 * 60 + idx, 60)
    return Pos(ctx.code, ctx.day, datetime.combine(ctx.day, time(hh, mm)), px, arm_b_qty(px).qty, BASIS_M_CLOSE)


def run_day(bars: np.ndarray, ctx: DayCtx, pred: Pred, tp: float, sl: float, base: str = BASE_R0) -> DayResult:
    """code-day 1개: 진입(기준 arm `base` 시작 분부터) → 당일 분 단위 청산 → 미청산이면 `Pos`(arm B 수량 · m_close)."""
    start = BASE_ARMS[base]
    fill, n_undet = _scan_entry(bars, ctx, pred, start)
    edge = find_entry_band_edge(bars, ctx, pred, start)
    if fill is None:
        window = bars[start: IDX_ENTRY_END + 1, F_CLOSE]
        return DayResult(False, SKIP_NO_ENTRY if np.isfinite(window).any() else SKIP_NO_PRICE, band_edge=edge,
                         base=base, undetermined_minutes=n_undet)
    ex = simulate_day_exit(bars, fill.idx, fill.px, tp, sl)
    pos = None if ex.closed else make_pos(ctx, fill.idx, fill.px)
    return DayResult(True, entry=fill, exit=ex, pos=pos, band_edge=edge, base=base, undetermined_minutes=n_undet)
