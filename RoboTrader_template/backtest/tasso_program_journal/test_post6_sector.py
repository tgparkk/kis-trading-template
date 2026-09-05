# -*- coding: utf-8 -*-
"""`SEC-` 축 post6 판정 모드 — **분모 필터 가드** (DB 불필요 · 빠른 테스트).

🔴 이 테스트가 지키는 것은 «값»이 아니라 **분모의 정의**다:
  ① 배선 점검(post1~5)의 분모가 원장 append 로 «움직이지 않는다»
  ② post6 판정의 분모가 **신규 `exact` 10건**이고 PD-2 후속 2건이 «정의로» 빠진다
  ③ 두 모드의 필터가 **명시**돼 있고 서로 «배타»다

🔑 ***「그 글은 아직 없다」는 「필터가 필요 없다」가 아니다*** — 홀드아웃 필터는 글이 오기 «전»에
   넣어야 하고, 들어간 뒤에는 «테스트»가 그것을 지켜야 한다.

실행: `python -m pytest test_post6_sector.py -q` (DB 접속 없음 · 원장 CSV 만 읽는다)
"""
from __future__ import annotations

import run_sector as S
from run_ranking import approx_items, build_codes, exact_items, load_ledger

# 🔒 동결본이 적은 값 — `FREEZE_SECTOR_2026-09-03.md` §2 「대상 표본」 · `INTAKE_2026-09-04_post6.md` §1
TRAIN_EXACT = 18
TRAIN_BY_POST = {2: 2, 3: 3, 4: 6, 5: 7}
TRAIN_APPROX = 2
TRAIN_DATES = 11
POST6_EXACT = 10
POST6_APPROX = 0
POST6_DATES = 8
POST6_NONE = {"광전자", "삼양바이오팜"}          # PD-2 후속 2건 — 등록일 축 분모 «밖»


def _items():
    rows = load_ledger("post6")                   # 🔴 전 행(필터 없음) — 필터는 이 축이 «따로» 건다
    codes, _ = build_codes(include_post6=True)
    items, post_idx = exact_items(rows, codes)
    return rows, items, approx_items(rows, codes, post_idx)


def test_train_denominator_is_frozen_against_ledger_growth():
    """① 원장에 post6 이 붙어도 배선 점검 분모는 «18건 / 11일»로 고정이다."""
    _rows, items, ap = _items()
    train = [i for i in items if i["post"] in S.TRAIN_POSTS]
    train_ap = [i for i in ap if i["post"] in S.TRAIN_POSTS]
    assert len(train) == TRAIN_EXACT
    assert len(train_ap) == TRAIN_APPROX
    assert len({i["reg"] for i in train}) == TRAIN_DATES
    by_post = {}
    for i in train:
        by_post[i["post"]] = by_post.get(i["post"], 0) + 1
    assert by_post == TRAIN_BY_POST
    # 🔴 원장이 실제로 자란 «뒤»여야 이 테스트가 의미가 있다 — 그 전제도 같이 확인한다.
    assert len(items) > TRAIN_EXACT, "post6 이 원장에 없다면 이 가드는 아무것도 지키지 않는다"


def test_post6_denominator_is_ten_new_exact():
    """② post6 판정 분모 = 신규 `exact` 10건 · 등록일 8일 · `approx` 0건."""
    _rows, items, ap = _items()
    p6 = [i for i in items if i["post"] == S.POST6_IDX]
    assert len(p6) == POST6_EXACT
    assert len({i["reg"] for i in p6}) == POST6_DATES
    assert len([i for i in ap if i["post"] == S.POST6_IDX]) == POST6_APPROX
    assert {i["log_no"] for i in p6} == {S.POST6_LOG_NO}
    assert all(i["code"] for i in p6), "post6 10건은 코드가 «전부» 있어야 한다(사유 ① 0건)"


def test_pd2_continuations_are_excluded_by_definition():
    """② PD-2 후속 2건은 `reg_date_precision = none` 이라 «정의로» 분모 밖이다(값 판단 아님)."""
    rows, items, ap = _items()
    none_rows = [r for r in rows
                 if r["post_log_no"] == S.POST6_LOG_NO and r["reg_date_precision"] == "none"]
    assert {r["stock_name"] for r in none_rows} == POST6_NONE
    assert all(r["reg_date"] == "" for r in none_rows), "후속 2건은 `reg_date` 가 비어 있어야 한다"
    named = {i["name"] for i in items + ap if i["post"] == S.POST6_IDX}
    assert not (named & POST6_NONE), "후속 2건이 `exact`/`approx` 분모에 들어왔다"


def test_two_mode_filters_are_explicit_and_disjoint():
    """③ 두 모드 필터가 «명시»돼 있고 서로 배타이며, 합쳐도 남는 글이 없다."""
    assert S.TRAIN_POSTS == (1, 2, 3, 4, 5)
    assert S.POST6_IDX == 6
    assert S.POST6_IDX not in S.TRAIN_POSTS
    _rows, items, ap = _items()
    every = {i["post"] for i in items + ap}
    assert every <= set(S.TRAIN_POSTS) | {S.POST6_IDX}, f"모드가 못 덮는 글이 있다: {every}"


def test_code_mappings_from_two_modules_agree():
    """두 독립 매핑(`run_ranking.POST6_CODES` ↔ `run_regday_post6.POST6_NEW`)이 같은지."""
    codes, _ = build_codes(include_post6=True)
    for name, code, _reg in S.POST6_NEW:
        assert codes.get(name) == code, f"{name}: {codes.get(name)} ≠ {code}"


def test_frozen_constants_not_silently_moved():
    """동결 상수(시드·반복·문턱·주 갈래)를 «값을 보고» 바꾸지 않았는지."""
    assert (S.SEED, S.NREP, S.X1_REP) == (20260815, 20_000, 200)
    assert (S.P_THR, S.B2_THR, S.QTOP_THR, S.UP_MULT) == (0.05, 0.50, 0.135, 1.15)
    assert abs(S.G1_THR - 1.0 / 3.0) < 1e-12
    assert (S.MAIN_N, S.MAIN_M) == (3, "SEC-M1")
    assert S.MIN_EXACT == 3
    assert S.NS == (2, 3, 5) and S.MEAS == ("SEC-M1", "SEC-M2", "SEC-M3")


def test_binom_ge_half_matches_prereg_table():
    """§4-2 (가) 표의 산술을 그대로 재현하는지 — 사전등록이 «값 보기 전»에 적은 칸들."""
    assert abs(S.binom_ge_half(3, 0.135) - 0.0498) < 5e-4    # 경계 행
    assert abs(S.binom_ge_half(3, 0.121) - 0.0404) < 5e-4
    assert abs(S.binom_ge_half(3, 0.409) - 0.3650) < 5e-4
    assert S.binom_ge_half(3, 0.135) < S.P_THR               # 🔒 발화 조건의 근
