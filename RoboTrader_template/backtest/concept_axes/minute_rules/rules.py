"""장중 진입 규칙 레지스트리 — 🔒 동결 `e2945ee` §4 와 같은 정의·문턱(`DRAFT = False` · 개정 = amendment 문서로만).

출처(정본) = `docs/prereg_2026-11-11_minute_rules.md` §4-1(주 가족 dt 6 · R1·R3·R7·R6·R4·R5) · §4-2(독립 가족 2 ·
H②-hist → `H2_HIST` · H+2% → `H_PLUS2`). 기준 arm 2 = `R0`(≥09:02) · `R0_0905`(≥09:05) · 합계 10 항목.

시점 규칙(kind='timing') = `pred(view, ctx) -> True | False | None`. `view = engine.view_upto(bars, t)`:
  행 0..t-1 = 완성 봉(open·high·low·close·volume·amount) · 행 t = 종가(현재가)만 · t 뒤 봉 없음.
  ⇒ t = len(view) - 1 · 시각 = `engine.idx_to_time(t)`. 엔진이 밴드 검사를 먼저 하고 그 다음 pred 를 부른다.
  True = 이 분에 산다 · False = 그 분 skip · **None = 판단 불가 → 그 분 skip**(엔진이 로트 단위
  `undetermined_minutes` 로 셈). 짝 = 기준 arm `R0`.
거르기 규칙(kind='filter') = `label(view_0905, ctx) -> keep | filter | undetermined`(09:05 view 로 하루 한 번 ·
  `engine.label_day`). 남김·걸러짐 **두 군 모두 기준 arm `R0_0905`**(09:05 이후 첫 밴드 안 분)로 진입해 ret 를 잰다
  (초안 §4-1 · Δ = keep 평균 − filter 평균 · `undetermined` 는 주 분석 제외·건수 인쇄 · 리뷰 M1·M5).
family = 'baseline' | 'main'(§4-1 Holm m=6) | 'independent'(§4-2 Holm m=2 · 주 가족과 합치지 않음 · 결과 봉인 §8).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from .engine import (BASE_R0, BASE_R0_0905, F_CLOSE, F_HIGH, F_LOW, F_OPEN, F_VOL, IDX_FILTER_AT, LABEL_FILTER,
                     LABEL_KEEP, LABEL_UNDETERMINED, DayCtx, DayResult, Label, Pred, label_day, run_day)

DRAFT = False                # 동결(e2945ee · 1단계 코드 4fff028 과 정의 같음) — 수정 1 문서 N4

FAMILY_BASELINE = "baseline"
FAMILY_MAIN = "main"
FAMILY_INDEPENDENT = "independent"

R1_OPEN_MULT = 1.02          # 현재가 > 당일 시가 × 1.02 → 그 분 skip
R3_ORB_END = 4               # 09:00~09:04 = 시가 범위(행 0..4)
R3_FIRST, R3_LAST = 5, 30    # 09:05~09:30 에만 진입
R7_DRAWDOWN = 0.95           # 현재가 ≤ 그때까지 고가 × 0.95 → skip
R6_LOOKBACK = 5              # 직전 5분 최저
R6_SPIKE = 0.03              # 현재가 ÷ 직전 5분 최저 − 1 ≥ 3% → skip
R4_DROP = -0.02              # 09:04 종가 ÷ 시가 − 1 ≤ −2% → filter
R5_VOL_FRAC = 0.02           # Σvolume(09:00~09:04) < 전일 거래량 × 2% → filter
H2_FIRST = 10                # 분 시작 ≥ 09:10 인 첫 밴드 안 분
H_PLUS2_MULT = 1.02          # 현재가 > 전일(D) 종가 × 1.02 → 그 분 skip


@dataclass(frozen=True)
class Rule:
    rule_id: str
    kind: str                         # baseline | timing(시점) | filter(거르기)
    desc: str
    pred: Optional[Pred] = None       # baseline·timing
    label: Optional[Label] = None     # filter
    base: str = BASE_R0               # 진입 기준 arm(engine.BASE_ARMS 키)
    family: str = FAMILY_MAIN
    draft: bool = DRAFT


REGISTRY: Dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    if rule.rule_id in REGISTRY:
        raise ValueError(f"규칙 id 중복: {rule.rule_id}")
    if (rule.kind == "filter") != (rule.label is not None) or (rule.kind != "filter") != (rule.pred is not None):
        raise ValueError(f"규칙 형 불일치(filter=label · 그 밖=pred): {rule.rule_id}")
    REGISTRY[rule.rule_id] = rule
    return rule


def rule_ids() -> List[str]:
    return list(REGISTRY)


# ── 보조(완성 봉만 본다) ───────────────────────────────────────────────────

def _t(view: np.ndarray) -> int:
    return len(view) - 1


def _price(view: np.ndarray) -> float:
    return float(view[-1, F_CLOSE])


def _first_finite(a: np.ndarray) -> float:
    fin = a[np.isfinite(a)]
    return float(fin[0]) if fin.size else float("nan")


def day_open(view: np.ndarray) -> float:
    """당일 시가 = 완성 봉 중 첫 유한 시가(09:00 봉이 보통) · 없으면 NaN.

    첫 거래가 지금 분 t 이면 그 분 시가는 계약상 숨겨져 있어 «모름»(NaN) — 라이브는 `stck_oprc` 로 안다.
    그 분은 R1 판단 불가(None → skip · 셈) · 영향 미미(그날 첫 거래 분 1개뿐)."""
    return _first_finite(view[:-1, F_OPEN])


def _nanmax(a: np.ndarray) -> float:
    a = a[np.isfinite(a)]
    return float(a.max()) if a.size else float("nan")


def _nanmin(a: np.ndarray) -> float:
    a = a[np.isfinite(a)]
    return float(a.min()) if a.size else float("nan")


def _check_filter_view(view: np.ndarray) -> None:
    if _t(view) < IDX_FILTER_AT:
        raise ValueError(f"거르기 라벨은 09:05 view(t ≥ {IDX_FILTER_AT})에서만 — t={_t(view)}")


# ── 기준 arm ──────────────────────────────────────────────────────────────

def r0_baseline(view: np.ndarray, ctx: DayCtx) -> Optional[bool]:
    return True


# ── 시점 규칙(주 가족) ─────────────────────────────────────────────────────

def r1_above_open(view: np.ndarray, ctx: DayCtx) -> Optional[bool]:
    """p_t > O × 1.02 → skip · p_t = O × 1.02 정확히 같으면 허용. 시가 모름 → None(`day_open` 참고)."""
    o = day_open(view)
    if not np.isfinite(o):
        return None
    return not (_price(view) > o * R1_OPEN_MULT)


def r3_orb_breakout(view: np.ndarray, ctx: DayCtx) -> Optional[bool]:
    t = _t(view)
    if not R3_FIRST <= t <= R3_LAST:
        return False
    orb_high = _nanmax(view[: R3_ORB_END + 1, F_HIGH])
    if not np.isfinite(orb_high):
        return None
    return _price(view) > orb_high


def r7_off_high(view: np.ndarray, ctx: DayCtx) -> Optional[bool]:
    """그때까지 고가 = 완성 봉 고가 최대와 현재가 중 큰 값(t 분 고가는 모른다 — 계약)."""
    p = _price(view)
    hi = _nanmax(np.append(view[:-1, F_HIGH], p))
    if not np.isfinite(hi):
        return None
    return not (p <= hi * R7_DRAWDOWN)


def r6_spike(view: np.ndarray, ctx: DayCtx) -> Optional[bool]:
    """p_t ÷ min(저가 max(09:00, t−5)~t−1) − 1 ≥ +3% → skip(정확히 +3% 도 skip). 창에 저가 없음 → None."""
    t = _t(view)
    lo = _nanmin(view[max(0, t - R6_LOOKBACK): t, F_LOW])
    if not np.isfinite(lo) or lo <= 0:
        return None
    return not (_price(view) / lo - 1.0 >= R6_SPIKE)


# ── 거르기 규칙(주 가족 · 09:05 view 라벨) ─────────────────────────────────

def r4_first5_drop(view: np.ndarray, ctx: DayCtx) -> str:
    """09:04 분 종가 ÷ O − 1 ≤ −2% → filter. O(행 0..4 첫 유한 시가)·09:04 종가 모름 → undetermined."""
    _check_filter_view(view)
    o = _first_finite(view[: R3_ORB_END + 1, F_OPEN])
    c904 = float(view[R3_ORB_END, F_CLOSE])
    if not (np.isfinite(o) and np.isfinite(c904) and o > 0):
        return LABEL_UNDETERMINED
    return LABEL_FILTER if c904 / o - 1.0 <= R4_DROP else LABEL_KEEP


def r5_first5_volume(view: np.ndarray, ctx: DayCtx) -> str:
    """Σvolume(09:00~09:04) < V_D × 2% → filter. V_D = 일봉 원값 × adj(D)/adj(D+1)(data.py).

    undetermined = `ctx.corp_event` 참(리뷰 M4 · adj NULL 은 1.0 으로 보고 사유 아님 — 관리자 재결정 11-10) ·
    전일 거래량 자체가 없음/≤0(값이 없어 계산 불가).
    09:00~09:04 거래 없음(거래량 NaN/0) = 0 으로 셈 → filter(판단 가능한 값)."""
    _check_filter_view(view)
    if ctx.corp_event or ctx.prev_day_volume is None or not ctx.prev_day_volume > 0:
        return LABEL_UNDETERMINED
    v5 = float(np.nansum(view[: R3_ORB_END + 1, F_VOL]))
    return LABEL_FILTER if v5 < ctx.prev_day_volume * R5_VOL_FRAC else LABEL_KEEP


# ── 시점 규칙(독립 가족 §4-2) ──────────────────────────────────────────────

def h2_hist(view: np.ndarray, ctx: DayCtx) -> Optional[bool]:
    """분 시작 ≥ 09:10 인 첫 밴드 안 분에 진입 · 그 전 분은 skip."""
    return _t(view) >= H2_FIRST


def h_plus2(view: np.ndarray, ctx: DayCtx) -> Optional[bool]:
    """p_t > C_D(`ctx.prev_close`) × 1.02 → 그 분 skip · 전일 종가 모름 → None."""
    if ctx.prev_close is None or not ctx.prev_close > 0:
        return None
    return not (_price(view) > ctx.prev_close * H_PLUS2_MULT)


# ── 실행 ──────────────────────────────────────────────────────────────────

def run_rule(bars: np.ndarray, ctx: DayCtx, rule: Rule, tp: float, sl: float) -> DayResult:
    """규칙 1개 · code-day 1개. 거르기 = R0_0905 진입 결과 + `label` · 그 밖 = pred 로 `rule.base` 진입."""
    if rule.kind == "filter":
        # 단건 편의용 — 2단계 run.py 는 R0_0905 결과를 로트당 1번 만들고 R4·R5 에는 라벨만 붙인다(재계산 없음)
        res = run_day(bars, ctx, r0_baseline, tp, sl, base=rule.base)
        res.label = label_day(bars, ctx, rule.label)
        return res
    return run_day(bars, ctx, rule.pred, tp, sl, base=rule.base)


BASELINE = register(Rule("R0", "baseline", "규칙 없음 — 첫 밴드 안 분(≥09:02)", r0_baseline,
                         family=FAMILY_BASELINE))
BASELINE_0905 = register(Rule("R0_0905", "baseline", "규칙 없음 — 09:05 이후 첫 밴드 안 분(거르기 두 군 공통)",
                              r0_baseline, base=BASE_R0_0905, family=FAMILY_BASELINE))
register(Rule("R1", "timing", "현재가 > 당일 시가 × 1.02 → 그 분 skip", r1_above_open))
register(Rule("R3", "timing", "09:00~09:04 진입 금지 · 09:05~09:30 에 09:00~09:04 고가 돌파 첫 분 · 없으면 skip",
              r3_orb_breakout))
register(Rule("R7", "timing", "현재가 ≤ 그때까지 고가 × 0.95 → 그 분 skip", r7_off_high))
register(Rule("R6", "timing", "현재가 ÷ 직전 5분 최저 − 1 ≥ 3% → 그 분 skip", r6_spike))
register(Rule("R4", "filter", "09:04 분 종가 ÷ 시가 − 1 ≤ −2% → filter(두 군 R0_0905 진입)",
              label=r4_first5_drop, base=BASE_R0_0905))
register(Rule("R5", "filter", "Σvolume(09:00~09:04) < 전일 일봉 거래량 × 2% → filter(두 군 R0_0905 진입)",
              label=r5_first5_volume, base=BASE_R0_0905))
register(Rule("H2_HIST", "timing", "분 시작 ≥ 09:10 인 첫 밴드 안 분 진입 · 그 전 분 skip", h2_hist,
              family=FAMILY_INDEPENDENT))
register(Rule("H_PLUS2", "timing", "현재가 > 전일 종가 × 1.02 → 그 분 skip", h_plus2, family=FAMILY_INDEPENDENT))
