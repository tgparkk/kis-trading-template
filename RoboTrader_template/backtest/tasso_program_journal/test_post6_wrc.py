# -*- coding: utf-8 -*-
"""`WRC-` 축 post6 판정 회차의 **가드 테스트** — DB 없이 도는 것만 담는다.

목적은 셋이다:
  1. **판정 분모가 값을 보고 정해지지 않았다**는 것을 기계로 다시 확인한다
     (원장 재측정 = `INTAKE_2026-09-04_post6.md` §5 의 «계산 전» 예측 5건).
  2. **탐색본(`RESULTS_WRC_EXPLORE.md`·`wrc_explore/`)이 원장 append 로 움직이지 않았다**를
     `FREEZE_WRC_2026-09-02.md` §2 의 md5 로 확인한다.
  3. `run_wrc_explore.py` 의 **post6 «명시» 제외 필터**가 살아 있고, 그 필터가 없으면
     탐색 분모가 실제로 오염된다는 것을 **양방향으로** 보인다(가드가 죽지 않았음의 증명).

🔴 DB 접속·라이브 import 0건. `pytest test_post6_wrc.py -q` 로 돈다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import run_wrc_explore as W
import run_wrc_post6 as P

BASE = Path(__file__).resolve().parent
EXPLORE_UPTO = "2026-08-29"      # run_wrc_explore.main() 의 필터 값과 같은 값을 여기 적는다


def _cases(upto=None):
    tr, legs = W.read_ledger()
    if upto:
        tr = [r for r in tr if r["post_date"] <= upto]
    return W.build_cases(tr, legs)


def test_post6_denominator_matches_intake_prediction():
    """§6-1 게이트 재측정 = 인테이크의 «계산 전» 예측 5건."""
    cases = _cases()
    gate = [c for c in cases if c["gate"] and c["log_no"] == P.POST_LOG]
    assert sorted(c["name"] for c in gate) == sorted(P.INTAKE_DENOM_PRED)
    assert len(gate) == 5


def test_post6_gate_rule_is_the_frozen_one():
    """분모 정의 = `exact` ∧ `fill_n ≥ 2` ∧ 서로 «다른» 값 레그 ≥ 3 — 세 조건 전부가 문다."""
    p6 = [c for c in _cases() if c["log_no"] == P.POST_LOG]
    assert {c["name"] for c in p6 if c["prec"] != "exact"} == {"광전자", "삼양바이오팜"}
    assert {c["name"] for c in p6 if c["fill_n"] == 1} == {"헥토파이낸셜", "아난티", "쿠콘"}
    assert {c["name"] for c in p6
            if c["prec"] == "exact" and c["fill_n"] and c["fill_n"] >= 2 and c["distinct"] < 3} \
        == {"아이티센글로벌", "현대약품"}


def test_explore_denominator_unchanged_by_ledger_append():
    """필터를 걸면 탐색 분모가 동결본(50/18/2/4/2/10)과 «정확히» 같다."""
    cases = _cases(EXPLORE_UPTO)
    exact = [c for c in cases if c["prec"] == "exact"]
    gate = [c for c in cases if c["gate"]]
    assert len(cases) == 50
    assert len(exact) == 18
    assert len([c for c in exact if c["fill_n"] is None]) == 2
    assert len([c for c in exact if c["fill_n"] == 1]) == 4
    assert len([c for c in exact
                if c["fill_n"] and c["fill_n"] >= 2 and c["distinct"] < 3]) == 2
    assert len(gate) == 10
    assert {c["post"] for c in gate} == {"post4", "post5"}


def test_guard_is_not_dead_filter_actually_bites():
    """🔴 필터가 «없으면» 오염된다 — 가드가 실제로 무는지 반대 방향으로 확인한다."""
    unfiltered = [c for c in _cases() if c["gate"]]
    assert len(unfiltered) == 15                       # 10(post4·5) + 5(post6)
    assert len([c for c in unfiltered if c["log_no"] == P.POST_LOG]) == 5


def test_explore_filter_line_present_in_script():
    """필터가 코드에 «문언으로» 남아 있다 — 지워지면 이 테스트가 먼저 운다."""
    src = (BASE / "run_wrc_explore.py").read_text(encoding="utf-8")
    assert 'EXPLORE_UPTO = "2026-08-29"' in src
    assert 'r["post_date"] <= EXPLORE_UPTO' in src


def test_frozen_explore_artifacts_byte_identical():
    """`FREEZE_WRC_2026-09-02.md` §2 md5 — 탐색본과 사전등록은 «불변»이어야 한다."""
    must_hold = ["RESULTS_WRC_EXPLORE.md", "wrc_explore/bands.tsv",
                 "wrc_explore/controls_summary.json", "wrc_explore/universe_snapshot.json",
                 "wrc_explore/remeasure_2_5.json", "PREREG_WEIGHTED_RECON.md",
                 "reconstruct_prices.py", "run_reconstruct_post5.py", "run_reconstruct_post4.py",
                 "run_selection.py", "run_tests.py"]
    for f in must_hold:
        got = hashlib.md5((BASE / f).read_bytes()).hexdigest()
        assert got == P.FREEZE_MD5[f], f"{f} 가 동결 md5 와 다르다"


def test_expected_change_set_is_declared_and_bites():
    """🔴 «바뀌는 것이 정상»인 파일은 실제로 바뀌어 있어야 한다(단언의 양쪽 방향)."""
    assert set(P.EXPECTED_CHANGE) == {"run_wrc_explore.py", "regen_gate.py"}
    for f in P.EXPECTED_CHANGE:
        got = hashlib.md5((BASE / f).read_bytes()).hexdigest()
        assert got != P.FREEZE_MD5[f], f"{f} 는 바뀌었어야 하는데 동결 md5 그대로다"


def test_ledger_is_not_pinned_by_whole_file_md5():
    """🔴 원장(공유 파일)의 **통째 md5** 는 어느 상수에도 없어야 한다.

    있으면 남의 `narrative` 편집만으로 이 산출물이 재현 불가가 된다(실제로 그 일이 있었다)."""
    assert "ledger_trades.csv" not in P.FREEZE_MD5
    assert "ledger_legs.csv" not in P.FREEZE_MD5
    assert "narrative" not in P.RNK_KEY and "narrative" not in P.WRC_KEY
    assert "narrative" not in P.LEG_KEY


def test_ledger_prefix_fingerprints_match_freeze():
    """prefix(= post6 «전» 행)는 동결 md5 그대로여야 한다 — 과거 행 불변의 증거."""
    for f, (n, want) in P.LEDGER_PREFIX.items():
        assert P.prefix_md5(BASE / f, n) == want, f"{f} 의 앞 {n}줄이 움직였다"


def test_prefix_is_the_right_instrument_whole_md5_already_moved():
    """🔴 «양방향» — 통째 md5 는 이미 움직였고(append + narrative 정정) prefix 는 안 움직였다.

    두 값이 같아지면 이 테스트가 먼저 운다 = prefix 가 «구분력 있는» 잣대라는 증명."""
    for f, (n, want) in P.LEDGER_PREFIX.items():
        whole = hashlib.md5((BASE / f).read_bytes()).hexdigest()
        assert whole != want, f"{f} 통째 md5 가 동결값과 같다 — 이 회차의 전제(append)가 깨졌다"


def test_read_field_fingerprint_covers_what_this_axis_reads():
    """🔴 `WRC_KEY` 는 분모를 정하는 열을 «전부» 덮어야 한다 — `RNK_KEY` 만으로는 부족하다."""
    must = {"fill_n", "fill_level", "open_ended", "reg_date_precision", "prog_ver"}
    assert must <= set(P.WRC_KEY)
    assert must & set(P.RNK_KEY) == {"reg_date_precision"}      # RNK 잣대만으론 안 덮인다
    rows = P.csv_rows("ledger_trades.csv")
    p6 = [r for r in rows if r["post_log_no"] == P.POST_LOG]
    assert len(p6) == 12
    assert P.field_key(p6, P.WRC_KEY) != P.field_key(p6, P.RNK_KEY)


def test_thresholds_are_imported_not_redefined():
    """문턱을 이 축이 «새로» 만들지 않았다 — 전부 동결본에서 import 한 같은 객체다."""
    assert (P.BAND_THR, P.G1_THR, P.N_THR, P.SEED, P.NREP, P.THR) == \
           (W.BAND_THR, W.G1_THR, W.N_THR, W.SEED, W.NREP, W.THR)
    assert P.BAND_THR == 3.0 and P.N_THR == 0.50 and P.SEED == 20260815 and P.NREP == 20000
