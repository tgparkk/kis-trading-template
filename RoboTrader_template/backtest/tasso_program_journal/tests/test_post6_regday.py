# -*- coding: utf-8 -*-
"""`run_regday_post6.py` 회귀 테스트 — 등록일 축(`Q1-R2`·`P6-M1′`·`P6-M2′`·`P6-M3′`·`REG-M4`·`REG-M5`).

사전등록이 «문언으로» 못박은 것만 시험한다(값이 아니라 **장치**를 시험한다):
  · `PREREG_POST6.md` §3-1 — 문턱 `≥ 5/6` · 귀무 시드 20260815 · 20,000 반복
  · `PREREG_POST6.md` §3-2 — 무리 대역(`r ≥ −1%` · `r ≤ −5%`) · 전제 문턱 2 · `G* = maxgap/range`
  · `PREREG_POST6.md` §1-6 — 절단가드 문턱 1/3 · §5-2 — `drop_rate` 가드 1%
  · `PREDECISION_2026-09-04_post6.md` PD-2 — 후속 2건은 등록일 축 분모 «밖»
  · 🔑 *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다*(`tests/test_s5_fixes.py` 승계)

DB 없이 도는 테스트만 모았다(합성 데이터 + 저장소 파일). 라이브 트리 import 0건.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import run_regday_post6 as R6           # noqa: E402


# ── 1. 동결 상수 ─────────────────────────────────────────────────────────────
def test_frozen_constants():
    assert R6.DB_UPTO == "2026-09-04"          # PD-1 · 발행 당일 봉 포함
    assert R6.WIN == 20                        # [D−19, D] · D 포함
    assert R6.NREP == 20_000                   # §4-1 승계
    assert R6.NULL_SEED == 20260815            # 동결분 승계
    assert R6.M1_RATIO == pytest.approx(5 / 6)  # §3-1 AND 규칙의 비율 문턱
    assert R6.R2_RATIO == 0.50                 # PREREG_Q1_V2 §3 R2
    assert R6.ALPHA == 0.05
    assert R6.MIN_N == 3 and R6.MIN_PULL == 3
    assert R6.CLUSTER_MIN == 2                 # §3-2 신규 문턱(양 무리 각 ≥2)
    assert R6.TRUNC_GUARD == pytest.approx(1 / 3)   # §1-6 3 (REC-Y3 차용)
    assert R6.DROP_GUARD == 0.01               # §5-2 신규 문턱 1%
    assert R6.UP_MULT == 1.15                  # n_up 정의
    assert R6.BAND_UP == 0.03                  # REG-M5 라이브 밴드 병기
    assert R6.NUP_CITE_BAN == 30               # REG-M4 재판정 문턱


# ── 2. 분모 (PD-2) ──────────────────────────────────────────────────────────
def test_denominator_is_ten_new_items_only():
    codes = [c for _n, c, _d in R6.POST6_NEW]
    assert len(R6.POST6_NEW) == 10 and len(set(codes)) == 10
    # 후속 2건(광전자 017900 · 삼양바이오팜 0120G0)은 등록일 축 분모에 «없어야» 한다
    assert "017900" not in codes and "0120G0" not in codes
    # 재진입 2건은 분모 «안»에 있다(§1-5 1: 분모에 넣는다)
    assert set(R6.REENTRY) <= set(codes)
    assert R6.PD3_FLAG == {"388050": 1, "004310": 0}


# ── 3. 무리 대역 (§3-2 동결 대역) ────────────────────────────────────────────
@pytest.mark.parametrize("r,want", [
    (0.0, "상한가형"), (-0.0099, "상한가형"), (-0.01, "상한가형"),
    (-0.0101, "🔴 중간대"), (-0.03, "🔴 중간대"), (-0.0499, "🔴 중간대"),
    (-0.05, "되밀림형"), (-0.12, "되밀림형"),
])
def test_bucket_boundaries(r, want):
    assert R6.bucket(r) == want


# ── 4. G* ───────────────────────────────────────────────────────────────────
def test_gstar_basic():
    # [0, 1, 5] → 간극 1·4 · 범위 5 ⇒ 4/5
    assert R6.gstar([0.0, 1.0, 5.0]) == pytest.approx(0.8)
    # 등간격이면 1/(n−1)
    assert R6.gstar([0.0, 1.0, 2.0, 3.0]) == pytest.approx(1 / 3)


def test_gstar_degenerate():
    assert R6.gstar([2.0, 2.0, 2.0]) == 0.0        # 범위 0 ⇒ 간극이 «없다»
    assert np.isnan(R6.gstar([1.0]))               # n<2 ⇒ 정의 불가


def test_gstar_rows_matches_gstar():
    rng = np.random.default_rng(7)
    M = rng.normal(size=(50, 6))
    got = R6.gstar_rows(M.copy())
    want = np.array([R6.gstar(row) for row in M])
    assert np.allclose(got, want)


# ── 5. 귀무 — 결정성(시드 고정) ──────────────────────────────────────────────
def test_null_gstar_a_is_deterministic():
    cands = [np.linspace(-0.2, 0.0, 40), np.linspace(-0.15, 0.0, 33),
             np.linspace(-0.1, 0.0, 25)]
    a = R6.null_gstar_a(cands, np.random.default_rng(R6.NULL_SEED))
    b = R6.null_gstar_a(cands, np.random.default_rng(R6.NULL_SEED))
    assert a.shape == (R6.NREP,) and np.array_equal(a, b)


def test_null_gstar_b_reports_replacement_fallback():
    small = np.linspace(-0.2, 0.0, 4)          # 집합 크기 4 < n 5 ⇒ 복원 추출 대체
    big = np.linspace(-0.2, 0.0, 40)
    vals, repl = R6.null_gstar_b([small, big], 5, np.random.default_rng(R6.NULL_SEED))
    assert vals.shape == (2 * R6.NREP,)
    assert repl == [4]                          # 그 사실을 «인쇄»할 수 있게 돌려준다


def test_null_p_deterministic_and_bounded():
    rows = [dict(hit=True, win_is20h=np.array([1.0, 0.0, 0.0, 0.0]),
                 win_high=np.array([9.0, 5.0, 5.0, 5.0])) for _ in range(3)]
    obs1, p1, _r, per1 = R6.null_p(rows, np.random.default_rng(R6.NULL_SEED), "move")
    obs2, p2, _r2, per2 = R6.null_p(rows, np.random.default_rng(R6.NULL_SEED), "move")
    assert obs1 == 1.0 and p1 == p2 and per1 == per2
    assert 0.0 <= p1 <= 1.0
    # 고정창은 「창 최고와 같은 봉」만 1 ⇒ 여기선 이동창과 같은 기저확률(1/4)
    _o, _p, _rr, perf = R6.null_p(rows, np.random.default_rng(R6.NULL_SEED), "fixed")
    assert perf == [pytest.approx(0.25)] * 3


# ── 6. AND 결정규칙 (§3-1) — ✅ 에 반드시 ⛔ 가 있다 ─────────────────────────
@pytest.mark.parametrize("ratio_ok,p_ok,want", [
    (True, True, "✅ 지지"),
    (True, False, "🟡 부분 충족 — **지지로 인용 금지**"),
    (False, True, "🟡 부분 충족 — **지지로 인용 금지**"),
    (False, False, "⛔ 불성립"),
])
def test_verdict_and(ratio_ok, p_ok, want):
    assert R6.verdict_and(ratio_ok, p_ok) == want


# ── 7. 산출물 문구 (§7-B #12·#13 · §3-1 필수 단서) ──────────────────────────
NUMBERS = BASE / "RESULTS_REGDAY_POST6_NUMBERS.md"


@pytest.mark.skipif(not NUMBERS.exists(), reason="아직 실행 전")
@pytest.mark.parametrize("needle", [
    "라이브 채택 대상이 아니다",                       # §7-B #12
    "창 종료 2026-09-04 = 발행 당일 봉 «포함»",        # PD-1 · §7-B #13
    "D 를 «포함»한 직전 20거래일",                     # §1-6 7 봉수 표기 규약
    "등록일이 급등일」은 같은 진술이 아니다",           # §3-1 필수 단서
    "`P6-PRIOR_CYCLE_IN_WINDOW`",                      # §1-5 3 의무 인쇄
    "`P6-절단가드-A`",                                 # §1-6 3
    "`drop_rate`",                                     # §5-2 5열
])
def test_numbers_file_contains_mandatory_phrases(needle):
    assert needle in NUMBERS.read_text(encoding="utf-8")
