"""청산 재현 — 순수(DB·전략 인스턴스 없음 · 데이터 청산은 주입된 탐침). 8전략 공통 1벌(스펙 검증표 #2).

라이브 하루의 청산 순서 (2026-09-19 코드 실측)
  07:40 복원  days_held = k — count_trading_days_between(매수시각, 07:40)(bot/state_restorer.py:388-392)
  09:00~      position_monitor 매 반복(core/trading/position_monitor.py:200-335)
                ① 보유기간  days_held ≥ strategy.max_holding_days → 현재가 매도        (:251-285)
                ② 익절      (현재가 − 평단)/평단 ≥ target_profit_rate                   (:314-323)
                ③ 손절      09:05 이후만(:219-224 · :326) · (현재가 − 평단)/평단 ≤ −stop_loss_rate (:327-335)
  09:0x       on_tick 매도 루프 → generate_signal(D-1 확정봉, 'daily') → 보유 분기 → _check_sell (strategies/base.py:739-761)
  ⇒ 일봉 근사: [보유기간 → 갭 익절](시가 · phase=open0900) → [데이터 청산](시가) → [갭 손절](시가 · 라이브는 09:05 이후
     가격 → 플래그) → 장중 고저 터치(동시면 손절 우선) — 뒤의 셋은 phase=after0902.
  평단 = position.avg_price(:215) ⇒ B2 는 합산 평단을 `Pos.entry_price` 로 넣는다.
갭 손절·장중 터치·동시 터치 손절 우선은 `cap_skip_ledger/sim.py::simulate_exit`(:87-153)를 봉 1개씩 불러 그대로 쓴다.
진입일(k=0): 탐침 1회(라이브는 매수 직후 같은 날 on_tick 매도 루프가 D-1 확정봉으로 `_check_sell`) → 진입 «이후» 고저만
  터치 판정 — basis=D_open 은 D 일봉 전체 · after_lift(D3′)는 진입 분봉 뒤 분봉만 모은 봉(`Pos.touch_bar`) ·
  band_touch·actual(시각 불명)은 진입일 고저를 쓰지 않는다.
D3′(급락 게이트 = 풀린 뒤 산다): `lift_entry` 가 해제 시각 뒤 분봉을 차례로 `sim.simulate_entry` 에 넣어 첫 체결을 찾는다.
  분봉이 없으면(LIFT_NO_MINUTE) 「안 산 것」이 아니라 「모른다」(A3) — 하한 = 안 삼 · 상한 = `lift_upper_bound`(D 일봉).
🔴 일봉으로 안 되는 것 — 갭다운 손절 체결가(라이브 09:05 가격) · 폴링이 놓친 짧은 꼬리 · 같은 날 청산 후 재진입 — 플래그로만.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import sim as S
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

BASIS_D_OPEN = "D_open"
BASIS_BAND = "band_touch"
BASIS_ACTUAL = "actual"
BASIS_LIFT = "after_lift"
BASIS_UPPER = "daily_upper_bound"    # A3 상한 민감도 — 분봉 없는 해제 뒤 진입을 D 일봉으로 «체결로 본» 가격

PHASE_OPEN = "open0900"        # 09:00 — position_monitor 보유기간·갭 익절(09:02 진입 «전»)
PHASE_AFTER = "after0902"      # 09:02~ — 데이터 청산·갭 손절·장중 터치
PHASE_ENTRY = "entry_day"      # 진입 당일

EXIT_TP = S.EXIT_TP
EXIT_SL = S.EXIT_SL
EXIT_MAX_HOLD = S.EXIT_MAX_HOLD
EXIT_OPEN = S.EXIT_OPEN

FLAG_GAP_TP = "gap_tp_open"
FLAG_SL_GAP_0905 = "sl_gap_open(라이브는 09:05 이후 가격)"
FLAG_SL_TP_BOTH = "sl_tp_same_bar(손절 우선)"
FLAG_K0_DATA = "k0_data_exit(가격=진입가 근사)"
FLAG_BAR_MISSING = "bar_missing"
FLAG_MAXHOLD_DEFERRED = "max_hold_deferred(결측 다음 봉 시가)"
FLAG_NO_D_TOUCH = "entry_day_touch_skipped(진입 시각 불명)"
FLAG_TOUCH_SKIPPED_ADD = "add_day_touch_skipped(band_touch 추가매수)"
FLAG_LIFT_ADD = "add_after_lift(그날 청산 판정은 기존 평단으로 먼저)"
FLAG_MTM = "mark_to_market(마지막 종가)"

LIFT_FILLED = "filled"
LIFT_UNFILLABLE = "unfillable"
LIFT_NO_MINUTE = "no_minute_data"
LIFT_NOT_LIFTED = "not_lifted"
LIFT_NO_BAR = "no_bar"               # A3 상한 — D 일봉 없음(정지·결측)


@dataclass(frozen=True)
class ExitRules:
    tp: float
    sl: float
    max_hold_days: int
    source: str = ""


@dataclass
class Pos:
    code: str
    entry_date: date
    entry_time: datetime
    entry_price: float
    qty: int
    entry_basis: str
    touch_bar: Optional[Bar] = None      # after_lift — 진입 뒤 분봉만 모은 D 봉(진입일 터치용)


@dataclass
class ExitOut:
    status: str                      # closed | open
    reason: str                      # tp | sl | max_hold | <데이터 청산 exit_reason> | open
    exit_date: Optional[date]
    price: Optional[float]
    ret_pct: Optional[float]
    hold_days: Optional[int]
    flags: List[str] = field(default_factory=list)
    phase: str = ""

    @property
    def closed(self) -> bool:
        return self.status == "closed"


Probe = Callable[[Pos, date], Optional[str]]
PathT = Sequence[Tuple[int, date, Optional[Bar]]]
MinuteBar = Tuple[str, Bar]          # (분봉 시작 HH:MM:SS, OHLC)


def _never(_k: int) -> bool:
    return False


def _rate(entry: float, px: float) -> float:
    return (float(px) - float(entry)) / float(entry)


def _closed(reason: str, d: date, px: float, pos: Pos, k: int, flags: List[str], phase: str) -> ExitOut:
    return ExitOut("closed", reason, d, float(px), _rate(pos.entry_price, px) * 100.0, k, list(flags), phase)


def _from_sim(ex: S.Exit, k: int, phase: str) -> Optional[ExitOut]:
    if ex.status != "closed":
        return None
    flags: List[str] = []
    if "갭 손절(시가)" in ex.notes:
        flags.append(FLAG_SL_GAP_0905)
    if "갭 익절(시가)" in ex.notes:
        flags.append(FLAG_GAP_TP)
    if any("모두 닿음" in n for n in ex.notes):
        flags.append(FLAG_SL_TP_BOTH)
    return ExitOut("closed", ex.reason, ex.exit_date, ex.price, ex.ret_pct, k, flags, phase)


def open_phase(pos: Pos, rules: ExitRules, k: int, bar: Bar, pending_max_hold: bool = False) -> Optional[ExitOut]:
    """09:00 — position_monitor 보유기간 → 익절(시가). 손절은 09:05 전이라 여기서 안 본다."""
    if pending_max_hold or k >= rules.max_hold_days:
        return _closed(EXIT_MAX_HOLD, bar.d, bar.open, pos, k,
                       [FLAG_MAXHOLD_DEFERRED] if pending_max_hold else [], PHASE_OPEN)
    if _rate(pos.entry_price, bar.open) >= rules.tp:
        return _closed(EXIT_TP, bar.d, bar.open, pos, k, [FLAG_GAP_TP], PHASE_OPEN)
    return None


def after_open(pos: Pos, rules: ExitRules, k: int, day: date, bar: Bar, probe: Probe,
               touches: bool = True) -> Optional[ExitOut]:
    """09:0x 데이터 청산(시가) → (touches 면) 갭 손절·장중 터치(sim.simulate_exit 봉 1개)."""
    r = probe(pos, day)
    if r:
        return _closed(r, day, bar.open, pos, k, [], PHASE_AFTER)
    if not touches:
        return None
    return _from_sim(S.simulate_exit(pos.entry_price, BASIS_BAND, None, [(k, bar)], rules.sl, rules.tp, _never),
                     k, PHASE_AFTER)


def entry_day(pos: Pos, rules: ExitRules, bar: Optional[Bar], probe: Probe) -> Optional[ExitOut]:
    """k=0 — 진입 당일. 터치는 진입 «이후» 고저만(D_open = D 봉 · after_lift = touch_bar · 그 밖 = 안 봄)."""
    if bar is None:
        return None
    r = probe(pos, pos.entry_date)
    if r:
        return _closed(r, pos.entry_date, pos.entry_price, pos, 0, [FLAG_K0_DATA], PHASE_ENTRY)
    touch = bar if pos.entry_basis == BASIS_D_OPEN else pos.touch_bar
    if touch is None:
        return None
    return _from_sim(S.simulate_exit(pos.entry_price, BASIS_D_OPEN, touch, [], rules.sl, rules.tp, _never),
                     0, PHASE_ENTRY)


def mark_to_market(pos: Pos, last: Optional[Tuple[int, date, Bar]], flags: Sequence[str] = ()) -> ExitOut:
    if last is None:
        return ExitOut("open", EXIT_OPEN, None, None, None, None, list(flags) + ["no_bar"])
    k, day, bar = last
    return ExitOut("open", EXIT_OPEN, day, float(bar.close), _rate(pos.entry_price, bar.close) * 100.0, k,
                   list(flags) + [FLAG_MTM])


def simulate_lot(pos: Pos, rules: ExitRules, path: PathT, probe: Probe) -> ExitOut:
    """로트 1개(B1 · A_sim · 청산 충실도) — path[0] 은 진입일(k=0)."""
    if not path:
        return ExitOut("open", EXIT_OPEN, None, None, None, None, ["no_path"])
    _, d0, bar0 = path[0]
    touch_ok = pos.entry_basis == BASIS_D_OPEN or pos.touch_bar is not None
    flags: List[str] = [] if touch_ok else [FLAG_NO_D_TOUCH]
    ex = entry_day(pos, rules, bar0, probe)
    if ex is not None:
        ex.flags = flags + ex.flags
        return ex
    last: Optional[Tuple[int, date, Bar]] = (0, d0, bar0) if bar0 is not None else None
    pending = False
    for k, day, bar in list(path)[1:]:
        if bar is None:
            flags.append(f"{FLAG_BAR_MISSING}:{day}")
            if k >= rules.max_hold_days:
                pending = True
            continue
        ex = open_phase(pos, rules, k, bar, pending) or after_open(pos, rules, k, day, bar, probe)
        if ex is not None:
            ex.flags = flags + ex.flags
            return ex
        last = (k, day, bar)
    return mark_to_market(pos, last, flags)


@dataclass
class LiftEntry:
    status: str                          # filled | unfillable | no_minute_data | not_lifted | no_bar
    price: Optional[float] = None
    time: str = ""                       # 체결로 본 분봉의 시작 시각 — 늘 'HH:MM:SS'(상한은 "" — 시각 불명)
    basis: str = ""                      # minute_open | minute_band_touch | daily_upper_bound
    touch_bar: Optional[Bar] = None      # 진입 «이후» 분봉만 모은 D 봉(시가 = 진입가)
    window: str = ""                     # 진입을 허용한 게이트 열린 구간 'HH:MM:SS~HH:MM:SS'(끝 없음 = 'HH:MM:SS~')


def _hhmmss(t: object) -> str:
    """비교용 'HHMMSS' — 'HH:MM:SS'(로그 해제 시각)·'HHMMSS'(DB `minute_candles.time`)·'H:MM:SS'·'HMMSS' 허용.

    형식이 섞인 채 문자열로 비교하면 조용히 틀린다('2' < ':' → 전부 탈락, 또는 해제 전 봉 체결) ⇒ 모르는 형식은 ValueError.
    """
    s = str(t).strip().replace(":", "")
    if len(s) == 5:
        s = "0" + s
    if len(s) != 6 or not s.isdigit():
        raise ValueError(f"시각 형식 불명: {t!r} ('HH:MM:SS' 또는 'HHMMSS')")
    return s


def _colon(s: str) -> str:
    return f"{s[:2]}:{s[2:4]}:{s[4:]}"


def lift_entry(d: date, minutes: Sequence[MinuteBar], lift_hhmmss: str, band_min: Optional[float],
               band_max: Optional[float], windows: Optional[Sequence[Tuple[str, str]]] = None) -> LiftEntry:
    """D3′ — 급락 게이트가 «열려 있는» 동안의 첫 매수 밴드 안 가격(스펙 「추가 결정」 · 과제 9 I1 «라이브와 같게»).

    `windows` = 게이트가 열린 구간 [(시작, 끝)] — 끝 "" = 장 끝까지. 없으면(None) 기본 [(lift_hhmmss, "")] = 첫 해제 뒤
    전부(재차단 무시 · 옛 동작). 주어지면 그것만 본다(lift_hhmmss 는 안 씀) · 빈 목록 = 해제 없음.
    시각은 분봉·구간 모두 `_hhmmss` 로 맞춘 뒤 비교한다(DB 'HHMMSS' · 로그 'HH:MM:SS') · `LiftEntry.time` 은 'HH:MM:SS'.
    진입 후보 = 분봉 시작 시각이 어느 구간의 [시작, 끝) 안인 봉(해제 시각이 든 분봉엔 해제 전 가격이 섞인다 · 재차단
    시각에 시작하는 봉은 이미 막힌 뒤다). 각 분봉을 `sim.simulate_entry` 에 그대로 넣는다 — 시가가 밴드 안이면 그
    시가(basis=minute_open), 시가 밖·봉 안 복귀면 밴드 경계값(minute_band_touch · 그 분 안 시각 불명). 끝까지 없으면
    unfillable. 진입일 터치용 봉은 minute_open 이면 그 분봉부터, band_touch 면 «다음» 분봉부터 «전부» 모은다
    (청산은 게이트가 막지 않는다 — 재차단 구간 분봉도 들어간다).
    """
    if windows is None:
        windows = [(lift_hhmmss, "")] if lift_hhmmss else []
    if not windows:
        return LiftEntry(LIFT_NOT_LIFTED)
    wins = [(_hhmmss(a), _hhmmss(b) if b else "") for a, b in windows]
    if not minutes:
        return LiftEntry(LIFT_NO_MINUTE)
    norm: List[Tuple[str, Bar]] = [(_hhmmss(t), b) for t, b in minutes]
    for i, (s, b) in enumerate(norm):
        win = next(((a, e) for a, e in wins if a <= s and (not e or s < e)), None)
        if win is None:
            continue
        ent = S.simulate_entry(b, band_min, band_max)
        if ent.status != S.ENTRY_FILLED:
            continue
        rest = norm[i:] if ent.basis == BASIS_D_OPEN else norm[i + 1:]
        touch = (Bar(d, float(ent.price), max(x.high for _, x in rest), min(x.low for _, x in rest),
                     float(rest[-1][1].close)) if rest else None)
        return LiftEntry(LIFT_FILLED, float(ent.price), _colon(s),
                         "minute_open" if ent.basis == BASIS_D_OPEN else "minute_band_touch", touch,
                         f"{_colon(win[0])}~{_colon(win[1]) if win[1] else ''}")
    return LiftEntry(LIFT_UNFILLABLE)


def lift_upper_bound(bar: Optional[Bar], band_min: Optional[float], band_max: Optional[float]) -> LiftEntry:
    """A3 상한 민감도 — 분봉이 없어 해제 뒤 체결을 «모르는» 행(`LIFT_NO_MINUTE`)을 D 일봉으로 «샀다고» 본 진입.

    D [저가, 고가]가 밴드와 겹치면(경계 포함 · None 쪽은 열림) 체결 — 가격 = D 종가가 밴드 안이면 종가, 밖이면
    종가에 가까운 밴드 경계값. 체결 시각 불명이라 진입일 터치는 쓰지 않는다(`touch_bar=None` → `simulate_lot` 이
    `FLAG_NO_D_TOUCH`). 겹치지 않으면 `LIFT_UNFILLABLE` · 봉이 없으면 `LIFT_NO_BAR`(둘 다 상한에서도 미체결).
    """
    if bar is None:
        return LiftEntry(LIFT_NO_BAR)
    lo, hi, px = float(bar.low), float(bar.high), float(bar.close)
    if (band_max is not None and lo > band_max) or (band_min is not None and hi < band_min):
        return LiftEntry(LIFT_UNFILLABLE)
    if band_max is not None and px > band_max:
        px = float(band_max)
    elif band_min is not None and px < band_min:
        px = float(band_min)
    return LiftEntry(LIFT_FILLED, px, "", BASIS_UPPER, None)
