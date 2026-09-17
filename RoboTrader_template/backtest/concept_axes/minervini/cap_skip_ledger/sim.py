"""가상 진입·가상 청산 — 순수 함수(DB 없음). 결과는 «%» 뿐, 원화 환산 없음.

🔴 이건 «라이브 체결 재현»이 아니라 **일봉만으로 그린 근사**다. 가정은 행마다 `assumptions` 칸에 찍는다.

진입 (라이브 근거: `core/trading_decision_engine.py` 실시간가 → 밴드 검증 · 밴드 이탈이면 스킵 후 다음 틱 재시도)
  - 기준가 ref = 신호의 `metadata['close']`(= 라이브 `_check_buy` 가 넘긴 마지막 확정봉 종가)
  - 밴드   = 신호의 `entry_min_price`/`entry_max_price` 를 «그대로» 쓴다(여기서 %를 다시 곱하지 않는다)
  - D 시가가 밴드 안   → 진입가 = D 시가            (basis=D_open)
  - 시가 이탈·장중 복귀 → 진입가 = 밴드 경계값       (basis=band_touch · 체결 시각 불명)
  - 장중 내내 밴드 밖   → 체결 불가                  (entry=unfillable)
  - D 봉 없음           → 체결 불가                  (entry=no_bar)

청산 (라이브 근거: `core/trading/position_monitor.py` — 보유기간 → 익절 → 손절, 실시간가 체결)
  - 보유일 k = 진입일 D 로부터의 거래일 수(D=0). 매 봉 «시작»에 `max_hold_fn(k)` (= 라이브
    `MinerviniVolumeDryupStrategy.evaluate_sell_conditions`) 가 참이면 그 봉 시가로 청산(max_hold).
  - 갭: 시가 ≥ 익절가 → 시가로 익절 · 시가 ≤ 손절가 → 시가로 손절 (첫 가격이라 순서가 확실하다)
  - 장중: 저가 ≤ 손절가 ∧ 고가 ≥ 익절가 → **손절 우선**(순서 불명 · 보수적) · 한쪽만 닿으면 그 값
  - 진입일 D: basis=D_open 이면 D 봉 전체가 진입 «이후»라 D 고저를 본다(갭 규칙 없음).
              basis=band_touch 면 진입 시각을 모르므로 D 는 건너뛰고 D+1 부터 본다.
  - 봉이 끝나도 청산 안 됐으면 `open`(보유 중) · 마지막 종가로 평가수익률.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence

ENTRY_FILLED = "filled"
ENTRY_UNFILLABLE = "unfillable"
ENTRY_NO_BAR = "no_bar"

EXIT_SL = "sl"
EXIT_TP = "tp"
EXIT_MAX_HOLD = "max_hold"
EXIT_OPEN = "open"


@dataclass
class Bar:
    d: date
    open: float
    high: float
    low: float
    close: float


@dataclass
class Entry:
    status: str
    price: Optional[float] = None
    basis: str = ""
    note: str = ""


@dataclass
class Exit:
    status: str                 # closed | open | n/a
    reason: str = ""            # sl | tp | max_hold | open
    exit_date: Optional[date] = None
    price: Optional[float] = None
    ret_pct: Optional[float] = None
    hold_days: Optional[int] = None
    notes: List[str] = field(default_factory=list)


def simulate_entry(bar: Optional[Bar], band_min: Optional[float], band_max: Optional[float]) -> Entry:
    if bar is None:
        return Entry(ENTRY_NO_BAR, note="D 일봉 없음(정지·결측)")
    o, h, lo = float(bar.open), float(bar.high), float(bar.low)
    if o <= 0:
        return Entry(ENTRY_NO_BAR, note="D 시가 ≤ 0")
    above = band_max is not None and o > band_max
    below = band_min is not None and o < band_min
    if not above and not below:
        return Entry(ENTRY_FILLED, o, "D_open")
    if above and lo <= band_max:
        return Entry(ENTRY_FILLED, float(band_max), "band_touch",
                     f"시가 {o:g} > 상한 {band_max:g} · 장중 복귀(체결 시각 불명)")
    if below and h >= band_min:
        return Entry(ENTRY_FILLED, float(band_min), "band_touch",
                     f"시가 {o:g} < 하한 {band_min:g} · 장중 복귀(체결 시각 불명)")
    if above:
        return Entry(ENTRY_UNFILLABLE, note=f"저가 {lo:g} > 상한 {band_max:g} (장중 내내 밴드 위)")
    return Entry(ENTRY_UNFILLABLE, note=f"고가 {h:g} < 하한 {band_min:g} (장중 내내 밴드 아래)")


def simulate_exit(entry_price: float, entry_basis: str, entry_bar: Optional[Bar],
                  later: Sequence[tuple], sl_pct: float, tp_pct: float,
                  max_hold_fn: Callable[[int], bool]) -> Exit:
    """later: D 이후 거래일 순서의 (k, Bar|None). k=1,2,…  Bar 가 None 이면 그날 봉 결측."""
    sl_px = entry_price * (1.0 - sl_pct)
    tp_px = entry_price * (1.0 + tp_pct)

    # 라이브 position_monitor 와 같은 «수익률» 비교식(가격 비교는 부동소수 오차로 경계가 어긋난다):
    #   profit_rate = (px − buy) / buy ; 익절 profit_rate ≥ tp · 손절 profit_rate ≤ −sl
    def _rate(px: float) -> float:
        return (float(px) - entry_price) / entry_price

    def _is_tp(px: float) -> bool:
        return _rate(px) >= tp_pct

    def _is_sl(px: float) -> bool:
        return _rate(px) <= -sl_pct

    def _ret(px: float) -> float:
        return _rate(px) * 100.0

    notes: List[str] = []
    # ── 진입일 D (k=0) ──
    if entry_bar is not None and entry_basis == "D_open":
        hit_sl = _is_sl(entry_bar.low)
        hit_tp = _is_tp(entry_bar.high)
        if hit_sl:
            if hit_tp:
                notes.append("D 당일 손절·익절 모두 닿음 → 손절 우선")
            return Exit("closed", EXIT_SL, entry_bar.d, sl_px, _ret(sl_px), 0, notes)
        if hit_tp:
            return Exit("closed", EXIT_TP, entry_bar.d, tp_px, _ret(tp_px), 0, notes)
    elif entry_basis != "D_open":
        notes.append("진입 시각 불명 → D 당일 고저 미사용(D+1 부터)")

    last_bar: Optional[Bar] = entry_bar
    last_k = 0
    pending_max_hold = False
    for k, bar in later:
        if bar is None:
            if max_hold_fn(k):
                pending_max_hold = True
            last_k = k
            continue
        if pending_max_hold or max_hold_fn(k):
            if pending_max_hold:
                notes.append("보유기한 도달일 봉 결측 → 다음 봉 시가")
            return Exit("closed", EXIT_MAX_HOLD, bar.d, bar.open, _ret(bar.open), k, notes)
        if _is_tp(bar.open):
            notes.append("갭 익절(시가)")
            return Exit("closed", EXIT_TP, bar.d, bar.open, _ret(bar.open), k, notes)
        if _is_sl(bar.open):
            notes.append("갭 손절(시가)")
            return Exit("closed", EXIT_SL, bar.d, bar.open, _ret(bar.open), k, notes)
        hit_sl = _is_sl(bar.low)
        hit_tp = _is_tp(bar.high)
        if hit_sl:
            if hit_tp:
                notes.append("같은 날 손절·익절 모두 닿음 → 손절 우선")
            return Exit("closed", EXIT_SL, bar.d, sl_px, _ret(sl_px), k, notes)
        if hit_tp:
            return Exit("closed", EXIT_TP, bar.d, tp_px, _ret(tp_px), k, notes)
        last_bar, last_k = bar, k

    mtm = last_bar.close if last_bar is not None else entry_price
    notes.append("보유 중 — 마지막 종가 평가")
    return Exit("open", EXIT_OPEN, last_bar.d if last_bar else None, mtm, _ret(mtm), last_k, notes)


def summarize_exits(exits: Sequence[Exit]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for e in exits:
        out[e.reason] = out.get(e.reason, 0) + 1
    return out
