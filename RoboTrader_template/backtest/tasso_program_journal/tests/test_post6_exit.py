# -*- coding: utf-8 -*-
"""`run_exit_v2_post6.py` 회귀 테스트 — 동결분이 코드에 «그대로» 들어갔는지.

이 테스트가 지키는 것(전부 계산 «전» 동결분):
  · `LABELS_2026-09-04_post6.md` 집계 — `TP` 9 · `SL` 1 · `MIX` 2 · `MANUAL` 0
  · `INTAKE_2026-09-04_post6.md` §1 — 레그 47(신규 37 · 후속 10) · 「손실률」 레그 5
  · `PREREG_POST6.md` §1-8 — `EXIT-X2`/`X8` 의 「마지막」은 «원» 시퀀스(`EXIT-X6` 미적용)
  · `PREREG_EXIT_V2.md` §2·§3 — ε=0.05%p 는 «증가»에만 적용 · 문턱 90%/80%
  · `EXIT-X6` 적용 범위 = E1·E4 뿐 · 아난티는 적용 후 레그 0 ⇒ 분모 밖
  · `PREREG_POST6.md` §4 #19 — `EXIT-E3`/`X7` 최소 n = `SL` 시퀀스 **3** ·
    ⛔ 판정 불가 조건 = 「범위만 · 시퀀스 < 3」 ⇒ 이번 글(시퀀스 1)은 **⛔** ·
    관측 1/1 은 «인쇄»(⛔ 는 선언 금지이지 인쇄 금지가 아니다)

DB 없이 돈다(저자 서술만). 라이브 트리 import 0건.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import run_exit_v2_post6 as R  # noqa: E402


def _by(name):
    return [t for t in R.TRADES if t[R.NAME].startswith(name)][0]


# ── 동결분이 그대로 옮겨졌나 ───────────────────────────────────────────────
def test_label_counts_frozen():
    c = {x: sum(1 for t in R.TRADES if t[R.LABEL] == x)
         for x in ("TP", "SL", "MIX", "MANUAL")}
    assert c == {"TP": 9, "SL": 1, "MIX": 2, "MANUAL": 0}
    assert sum(1 for t in R.TRADES if t[R.NEW]) == 10
    assert sum(1 for t in R.TRADES if not t[R.NEW]) == 2


def test_leg_totals_frozen():
    assert sum(len(t[R.LEGS]) for t in R.TRADES) == 47
    assert sum(len(t[R.LEGS]) for t in R.TRADES if t[R.NEW]) == 37
    assert sum(sum(t[R.LOSSM]) for t in R.TRADES) == 5
    assert sum(1 for t in R.TRADES if t[R.BE]) == 4          # breakeven_note
    assert sum(1 for t in R.TRADES if t[R.TILDE]) == 0       # `~` 표기 0건 (PD-4)
    assert sum(1 for t in R.TRADES if t[R.RANGE]) == 0       # RANGE_ONLY 0건 (PD-10)


def test_open_ended_by_narrative():
    """PD-4 — 서술 기준 미완결 4건(`TP` 3 + `SL` 1)."""
    op = {t[R.NAME].split()[0] for t in R.TRADES if t[R.OPEN_N]}
    assert op == {"한라캐스트", "아난티", "지투파워", "우리기술투자"}


# ── ε 은 «증가»에만 걸린다 ────────────────────────────────────────────────
def test_eps_applies_to_increase_only():
    assert R.nonincreasing([-2.87, -2.89]) == []      # 하락 0.02%p — 위반 아님
    assert R.nonincreasing([13.09, 13.06]) == []      # 하락 0.03%p — 위반 아님
    assert R.nonincreasing([1.00, 1.04]) == []        # 증가 0.04%p ≤ ε — 위반 아님
    assert len(R.nonincreasing([1.00, 1.06])) == 1    # 증가 0.06%p > ε — 위반
    assert R.eps_pairs([1.00, 1.04]) == [(1.00, 1.04)]
    assert R.eps_pairs([-2.87, -2.89]) == []
    assert R.EPS == 0.05 and R.E1_MIN == 0.90 and R.E2_MIN == 0.80


def test_no_eps_used_in_this_post():
    """3글 연속 ε 사용 0회 — 이번 글도 0."""
    assert sum(len(R.eps_pairs(t[R.LEGS])) for t in R.TRADES) == 0


# ── EXIT-X6 (E1·E4 한정) ─────────────────────────────────────────────────
def test_x6_narrative_drops_last_leg():
    assert R.x6_legs(_by("지투파워"), "narr") == [10.14, 7.36, 7.25]
    assert R.x6_legs(_by("아난티"), "narr") == []          # 레그 0 ⇒ E1 분모 밖
    assert R.x6_legs(_by("원익"), "narr") == _by("원익")[R.LEGS]


def test_x6_tilde_basis_is_noop_this_post():
    """`~` 문자 기준은 이번 글 적용 0건 ⇒ 원 시퀀스 그대로."""
    for t in R.TRADES:
        assert R.x6_legs(t, "tilde") == list(t[R.LEGS])


# ── EXIT-X2 는 «원» 시퀀스의 마지막 (X6 미적용 · §1-8) ────────────────────
def test_x2_uses_original_sequence():
    v, pos = R.x2_leg(*[_by("광전자")[i] for i in (R.LEGS, R.LOSSM)])
    assert (v, pos) == (0.11, 2)                            # 「손실률」 2레그 제외
    v, pos = R.x2_leg(*[_by("삼양")[i] for i in (R.LEGS, R.LOSSM)])
    assert (v, pos) == (0.88, 3)
    v, pos = R.x2_leg(*[_by("비에이치")[i] for i in (R.LEGS, R.LOSSM)])
    assert (v, pos) == (3.70, 6)                            # 손실 레그 없음 ⇒ 마지막
    # 미완결 건이라도 규칙 자체는 «원» 시퀀스 마지막을 가리킨다(분모엔 안 들어간다)
    v, _ = R.x2_leg(*[_by("지투파워")[i] for i in (R.LEGS, R.LOSSM)])
    assert v == 5.19


def test_x2_main_denominator_is_new_complete_tp():
    x2t = [t for t in R.TRADES if t[R.NEW] and t[R.LABEL] == "TP" and not t[R.OPEN_N]]
    assert len(x2t) == 6
    assert {t[R.NAME].split()[0] for t in x2t} == {
        "헥토파이낸셜", "아이티센글로벌", "현대약품", "원익", "쿠콘", "비에이치"}
    assert sum(sum(t[R.LOSSM]) for t in x2t) == 0           # ⇒ EXIT-X8 구성상 0


# ── 판정값 (기계 산출물과 같은 계산) ─────────────────────────────────────
def test_headline_numbers():
    tp_new = [t for t in R.TRADES if t[R.NEW] and t[R.LABEL] == "TP"]
    e1 = [R.x6_legs(t, "narr") for t in tp_new]
    e1 = [L for L in e1 if L]
    assert len(e1) == 8 and sum(1 for L in e1 if not R.nonincreasing(L)) == 8

    e4 = [L for L in e1 if len(L) >= 3]
    assert len(e4) == 5 and sum(1 for L in e4 if not R.nonincreasing(L)) == 5

    be = [t for t in R.TRADES if t[R.BE]]
    assert sum(1 for t in be if abs(t[R.LEGS][-1]) < R.BE_MAX) == 1          # E2 1/4
    assert len([t for t in be if t[R.NEW]]) == 2

    x2t = [t for t in R.TRADES if t[R.NEW] and t[R.LABEL] == "TP" and not t[R.OPEN_N]]
    hit = sum(1 for t in x2t if abs(R.x2_leg(t[R.LEGS], t[R.LOSSM])[0]) < R.BE_MAX)
    assert (hit, len(x2t)) == (1, 6)                                        # X2 1/6

    x8 = sum(1 for t in x2t if R.x2_leg(t[R.LEGS], t[R.LOSSM])[0] != t[R.LEGS][-1])
    assert x8 == 0                                                          # 구분 불가

    sl = [t for t in R.TRADES if t[R.LABEL] == "SL"]
    loss = [v for v, m in zip(sl[0][R.LEGS], sl[0][R.LOSSM]) if m]
    assert len(sl) == 1 and loss == [-2.87, -2.89] and not R.nonincreasing(loss)


def test_omission_bias_ratio():
    tp_new = [t for t in R.TRADES if t[R.NEW] and t[R.LABEL] == "TP"]
    new = [t for t in R.TRADES if t[R.NEW]]
    assert (sum(1 for t in tp_new if t[R.OPEN_N]), len(tp_new)) == (3, 9)
    assert (sum(1 for t in new if t[R.OPEN_N]), len(new)) == (4, 10)


# ── EXIT-E3 / EXIT-X7 — §4 #19 최소 n 게이트 ────────────────────────────
E3_MIN_SEQ = 3          # `PREREG_POST6.md` §4 #19 최소 n = `SL` 시퀀스 3 (동결)


def _sl_sequences():
    """`SL` ∧ 「시퀀스」(손절 레그 값 2개 이상 · 범위 아님)인 건의 손절 레그 목록."""
    out = []
    for t in R.TRADES:
        if t[R.LABEL] != "SL" or t[R.RANGE]:
            continue
        loss = [v for v, m in zip(t[R.LEGS], t[R.LOSSM]) if m]
        if len(loss) >= 2:
            out.append(loss)
    return out


def test_e3_verdict_is_blocked_below_min_n():
    """(a) `SL` 시퀀스 1 < 3 ⇒ 판정은 ⛔ 로 «표기»되어야 한다."""
    assert len(_sl_sequences()) == 1 < E3_MIN_SEQ
    for f in ("RESULTS_EXIT_V2_POST6_NUMBERS.md", "RESULTS_EXIT_V2_POST6.md"):
        doc = (BASE / f).read_text(encoding="utf-8")
        assert "⛔ **판정 불가**" in doc, f
        assert "§4 #19" in doc, f
        # 철회된 옛 문구가 남아 있으면 안 된다
        assert "3건 미만 보류」 게이트가 «없다»" not in doc, f
        assert "출처 없는 새 문턱" not in doc, f


def test_e3_observation_is_printed_even_though_blocked():
    """(b) ⛔ 라도 관측값 1/1 · n=1 은 인쇄한다."""
    loss = _sl_sequences()[0]
    assert loss == [-2.87, -2.89] and not R.nonincreasing(loss)
    for f in ("RESULTS_EXIT_V2_POST6_NUMBERS.md", "RESULTS_EXIT_V2_POST6.md"):
        doc = (BASE / f).read_text(encoding="utf-8")
        assert "1/1" in doc and "n = 1" in doc, f


def test_e3_opens_at_three_sequences():
    """(c) 시퀀스가 3건이면 판정이 «열린다» — 문턱은 3 이고 그 위에서만 판정."""
    def blocked(n_seq):
        return n_seq < E3_MIN_SEQ
    assert blocked(0) and blocked(1) and blocked(2)
    assert not blocked(3) and not blocked(4)
    assert E3_MIN_SEQ == 3


def test_no_live_tree_import():
    src = (BASE / "run_exit_v2_post6.py").read_text(encoding="utf-8")
    for bad in ("psycopg2", "from core", "import core", "from utils", "import utils",
                "from strategies", "import pandas", "import numpy"):
        assert bad not in src, bad
