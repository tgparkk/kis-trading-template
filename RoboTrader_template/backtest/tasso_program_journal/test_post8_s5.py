# -*- coding: utf-8 -*-
"""`run_s5_post8.py` 가드 시험 — **DB 접속 0건**(원장·산출물 파일만 읽는다).

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 가드가 «통과»하는 것만이 아니라
   일부러 흔든 사본에서 «운다»는 것도 같이 본다.
🔴 원본 파일은 고치지 않는다. 흔들기는 전부 메모리 사본에서 한다.

실행: `python -m pytest test_post8_s5.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

import run_s5_post7 as S7
import run_s5_post8 as S8

BASE = Path(__file__).resolve().parent
NUMBERS = BASE / "RESULTS_S5_POST8_NUMBERS.md"


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def git_clean(rel):
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=str(BASE),
                       capture_output=True)
    return r.returncode == 0


VINT = dict(win_max="2026-09-23 15:46:25.855518", win_min="2026-09-23 15:45:10.623955",
            read_max="x", read_min="y", read_date_max="2026-09-11",
            next_sweep="2026-09-28 15:35 예정", dplus1_ok=True)


def static_lines():
    return (S8.header_lines("2026-09-24", "2026-09-23", 2764, VINT) + S8.contamination_lines()
            + S8.precision_lines(3, 5) + S8.duty_misc_lines() + S8.limits_lines()
            + [S8.d3_line(4, 6, 3, 5), "D-5 갈래", "max(rcept_dt)"])


# ── P1 동결 상수 ────────────────────────────────────────────────────────────
def test_p1_constants_are_frozen_values():
    assert S8.POST_LOG == "224416253270"
    assert S8.POST_DATE == "2026-09-18" == S8.DB_UPTO == S8.PIT_CUTOFF
    assert S8.PIT_STATUS == "000" == S7.PIT_STATUS
    assert S8.TOP_PCT == 99.0 == S7.TOP_PCT
    assert S8.SEED == 20260815
    assert S8.MIN_JUDGEABLE == 3 and S8.BAND_PP == 10
    assert S8.PROG_VER == "1.0.42"
    assert S8.LABELS == ("(S5-성립)", "(S5-이탈)", "(S5-보류)")


def test_p1_sample_matches_intake_section1():
    assert S8.EXACT4 == [("우리로", "046970", "2026-09-11"), ("JW신약", "067290", "2026-09-01"),
                         ("액스비스", "0011A0", "2026-09-11"), ("우리기술", "032820", "2026-09-09")]
    assert [(n, c) for n, c, *_ in S8.APPROX2] == [("헥토파이낸셜", "234340"), ("코데즈컴바인", "047770")]
    assert all(len(d) == 7 for *_x, d in S8.APPROX2), "「8월말」 = 거래일 7일(PD-4 2번)"
    assert S8.NONE1 == [("원익", "032940")] and len(S8.FOLLOWUP3) == 3
    assert S8.NO_FIN_CODES == {"0011A0"}
    judge = [c for _n, c, _d in S8.EXACT4 if c not in S8.NO_FIN_CODES]
    assert len(judge) == 3, "판정 가능 예고 3 (PD-15)"


def test_p1_ledger_guard_passes_on_real_ledger_and_bites_on_shaken_copy():
    rows = S8.ledger_rows()
    assert len(rows) == 10
    assert S8.assert_ledger_matches(rows)
    shaken = [dict(r) for r in rows]
    shaken[5]["reg_date"] = "2026-09-02"          # JW신약 등록일을 흔든다
    with pytest.raises(AssertionError):
        S8.assert_ledger_matches(shaken)
    shaken2 = [dict(r) for r in rows]
    shaken2[0]["prog_ver"] = "1.0.41"
    with pytest.raises(AssertionError):
        S8.assert_ledger_matches(shaken2)


# ── P2 판정 규칙 (§2 동결) — 경계·대칭 ──────────────────────────────────────
def test_p2_label_boundary_is_inclusive_10pp():
    # 선정 2/3 = 66.67% · 대조군 56.67% ⇒ 차 = 정확히 10%p ⇒ 성립(≤)
    assert S8.s5_label(2, 3, Fraction(200, 3) - 10) == "(S5-성립)"
    assert S8.s5_label(2, 3, Fraction(200, 3) + 10) == "(S5-성립)"
    # 경계를 한 호흡 넘으면 이탈 — 비교자가 상수가 아니다(대칭)
    assert S8.s5_label(2, 3, Fraction(200, 3) - 10 - Fraction(1, 1000)) == "(S5-이탈)"
    assert S8.s5_label(2, 3, Fraction(200, 3) + 10 + Fraction(1, 1000)) == "(S5-이탈)"


def test_p2_hold_when_judgeable_below_three():
    assert S8.s5_label(1, 2, Fraction(50)) == "(S5-보류)"
    assert S8.s5_label(0, 0, None) == "(S5-보류)"
    assert S8.s5_label(1, 3, Fraction(33)) != "(S5-보류)", "3 이면 보류가 아니다(대칭)"


def test_p2_final_label_requires_unanimity():
    a, b = "(S5-이탈)", "(S5-성립)"
    assert S8.final_label([a, a, a, a]) == a
    assert S8.final_label([a, a, b, a]) == S8.AMBIG
    assert S8.final_label([a, None, a, a]) == S8.AMBIG


def test_p2_ctrl_rate_pooled_vs_mean_differ_in_general():
    ents = [(1, 2), (9, 10)]
    assert S8.ctrl_rate(ents, True) == Fraction(1000, 12)
    assert S8.ctrl_rate(ents, False) == (Fraction(50) + Fraction(90)) / 2
    assert S8.ctrl_rate(ents, True) != S8.ctrl_rate(ents, False)
    assert S8.ctrl_rate([(0, 0)], True) is None


# ── P3 가드가 «실제로» 무는가 ─────────────────────────────────────────────────
def test_p3_labels_only_in_verdict_section():
    L = static_lines() + [S8.VERDICT_BEGIN, "⇒ **최종: (S5-이탈)**", S8.VERDICT_END]
    assert S8.assert_labels_only_in_verdict(L)
    with pytest.raises(AssertionError):
        S8.assert_labels_only_in_verdict(L + ["§6 approx ⇒ (S5-성립)"])


def test_p3_static_blocks_have_no_label_outside_verdict():
    assert S8.assert_labels_only_in_verdict(static_lines())


def test_p3_no_grade_names_guard():
    assert S8.assert_no_grade_names(static_lines())
    for bad in ("GT-D", "조건 미달", "충족·참고용", "낡음(재실행 금지)"):
        with pytest.raises(AssertionError):
            S8.assert_no_grade_names(static_lines() + [bad])


def test_p3_duty_markers_present_and_guard_bites():
    L = static_lines()
    assert S8.assert_duties(L)
    for m in ("D-9 ①", "D-9 ⑤", "`approx` 포함 시 최소 n 이 차는 축:", "주 표본 n"):
        cut = [ln.replace(m, "") for ln in L]
        with pytest.raises(AssertionError):
            S8.assert_duties(cut)


def test_p3_both_n_is_post7_guard_object():
    L = S8.precision_lines(3, 5)
    body = "\n".join(L)
    assert "주 표본 n = 4" in body and "민감도 판 n = 6" in body
    assert S7.assert_both_n(L)
    with pytest.raises(AssertionError):
        S7.assert_both_n([ln for ln in L if "민감도 판 n" not in ln])


def test_p3_d3_line_is_symmetric():
    assert "축: **없음**" in S8.d3_line(4, 6, 3, 5)
    assert "축: **S5**" in S8.d3_line(4, 6, 2, 4), "exact 판정 가능 < 3 ≤ approx 포함이면 S5 를 신고"
    assert "축: **없음**" in S8.d3_line(4, 6, 2, 2)


def test_p3_axbis_reason_is_not_name_mismatch_nor_0806_stop():
    r = S8.no_fin_reason("0011A0")
    assert "미수록" in r and "이름 매칭 실패" in r and "아니다" in r
    assert "0011A0" in r
    assert "08-06 정지" in r and "적지 않는다" in r, "해치텍 사유(08-06 정지)를 옮겨 쓰지 않는다"
    assert "미수록" not in S8.no_fin_reason("999999")


# ── P4 재사용 (새 코드 0줄) · post7 회귀 ──────────────────────────────────────
def test_p4_reuses_post7_objects():
    assert S8.S7 is S7
    src = (BASE / "run_s5_post8.py").read_text(encoding="utf-8")
    for fn in ("S7.pit_row", "S7.control_top1", "S7.loss_rate", "S7.news_hits", "S7.assert_both_n"):
        assert fn in src, fn
    assert "def pit_row" not in src and "def control_top1" not in src, "동결 SQL 을 다시 쓰지 않았다"


def test_p4_pit_cutoff_context_restores_even_on_error():
    before = S7.PIT_CUTOFF
    assert before == "2026-09-12"
    with S8.pit_cutoff("2026-09-18"):
        assert S7.PIT_CUTOFF == "2026-09-18"
    assert S7.PIT_CUTOFF == before
    with pytest.raises(RuntimeError):
        with S8.pit_cutoff("2000-01-01"):
            raise RuntimeError("x")
    assert S7.PIT_CUTOFF == before


def test_p4_post7_files_untouched():
    for f in ("run_s5_post7.py", "RESULTS_S5_POST7_NUMBERS.md", "RESULTS_S5_POST7.md",
              "test_post7_s5.py", "PREREG_S5_FUND_NEWS_OOS.md", "FREEZE_S5_2026-09-16.md"):
        assert git_clean(f), f"{f} 가 HEAD 와 다르다"


def test_p4_frozen_prereg_md5_equals_freeze_table():
    # `FREEZE_S5_2026-09-16.md` §2-1 작업트리 md5 — 본문 0바이트 변경의 기계 증거
    assert md5(BASE / "PREREG_S5_FUND_NEWS_OOS.md") == "cb9485d37f6e7ff3d6e09dd7449a9f4e"


def test_p4_script_writes_only_its_own_numbers():
    src = (BASE / "run_s5_post8.py").read_text(encoding="utf-8")
    targets = re.findall(r'BASE / "([^"]+)"\)\.write_text', src)
    assert targets == ["RESULTS_S5_POST8_NUMBERS.md"], targets
    assert "RESULTS_S5_POST8.md\").write" not in src, "산문은 사람이 쓴다"


# ── P5 산출물 구조 (파일이 있으면) ────────────────────────────────────────────
@pytest.mark.skipif(not NUMBERS.exists(), reason="산출물 아직 없음")
def test_p5_numbers_structure():
    L = NUMBERS.read_text(encoding="utf-8").splitlines()
    body = "\n".join(L)
    assert L[0].startswith("# RESULTS_S5_POST8_NUMBERS — 기계 생성 (수정 금지)")
    assert S8.assert_labels_only_in_verdict(L)
    assert S8.assert_no_grade_names(L)
    assert S8.assert_duties(L)
    assert S7.assert_both_n(L)
    fin = [ln for ln in L if ln.startswith("- ⇒ **최종: ")]
    assert len(fin) == 1
    assert any(lab in fin[0] for lab in S8.LABELS + (S8.AMBIG,))
    assert "주 표본 n = 4" in body and "민감도 판 n = 6" in body
    assert "판정 불가·모호" in body, "모호 규칙 문장이 인쇄된다"
    # 네 셈법이 전부 인쇄된다
    for tag in ("(가) pooled", "(나) 날짜별", "(다) pooled", "(라) 날짜별"):
        assert tag in body, tag
    # post7 행은 판정 없음
    assert "**—**(판정 없음 · 소급 금지)" in body
    # 분 단위 시각이 본문에 없다(바이트 결정론) — 날짜만
    assert not re.search(r"실행일 \*\*2026-\d\d-\d\d \d\d:\d\d", body)
