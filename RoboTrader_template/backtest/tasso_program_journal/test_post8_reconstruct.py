# -*- coding: utf-8 -*-
"""`run_reconstruct_post8.py` 의 «가드 시험» — 계기가 규약대로 돌았는지 본다 (post7 판 `test_post7_reconstruct.py` 승계).

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「일치한다」만 보이면 비교자가
   항상 통과하는 장식일 수 있으므로 **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *가드를 시험하지 않으면 그것도 장식이다* — `D-3`·`P8-갈래계수`·「재진입 의존」·D-9 ① 도장은
   순수 함수로 떼어 **양성·음성 입력**을 둘 다 넣는다.

실행: `python -m pytest test_post8_reconstruct.py -q -p no:cacheprovider`
      (라이브 트리 import 0건 · **DB 접속 0건** · `run_reconstruct_post8.py` 를 실행하지 않는다 — 산출물은 «읽기»만)

  P1 동결 상수 (창 종료 2026-09-18 = 발행 당일 · logNo · prog_ver · 원장 커밋 · 제도 경계 · REC-Z5 · 시드 = post7 값)
  P2 `TARGETS` = `INTAKE_2026-09-18_post8.md` §1 신규 7건 · 후속 3건 «없음» · 레그 = 원장 `ledger_legs.csv` post8 행
  P3 분모 — `exact` 4 / `approx` 2 / `none` 1 · `first_only` exact 4 · §1-5 재진입 exact 0 · `구조차단` = 우리로
  P4 `REC-Y1` 열림(exact 레그≥4 = 3) · 「우리로 제외」 2 < 3 · `approx` 포함 5 · N1 대칭(우리로를 빼면 닫힌다)
  P5 판정 함수(`a_y1`·`a_y3`·`a_z1`·`a_z3`) 문턱 경계 — 양성·음성
  P6 `D-3` 기계 검사(`d3_hit`) · `P8-갈래계수`(`gc_status`) · 「재진입 의존」(`re_dep_status`) — 양성·음성
  P7 D-9 ① 도장(`stamp_resolve`) — 같은 지문 = 시각 유지 ∧ 파일 다시 쓰지 않음 · 다른 지문 = 새 시각(대칭) ·
     🆕 정정 1차: `runs_kst` 누적 폐지(실행 기록은 stdout 전용) · stamp 파일에 `runs_kst` 가 없다
  P8 🔒 `REC-Z4` 판정 없음 · 결정 ④ 종결 목록 = post7 객체 · 귀무 미실행
  P9 동결 인쇄값(`FROZEN`)이 인용 파일:줄에 실제로 있다 · N2 흔든 사본에서 불일치
  P10 `approx` 창 규약 갈래 · 모순 갈래 · 직전 등록일 · 소수 자릿수 한계
  P11 소스 필수 문구 · import 허용 목록 · SELECT 뿐 · `adj_factor` 산술 0 · 쓰기 2곳 · 통계 핵 = post5·post6 «같은 객체»
  P12 산출물(`RESULTS_RECONSTRUCT_POST8_NUMBERS.md`) 인쇄 의무 — D-9 ①~⑤ · D-3 한 줄 · D-5 세 쪽 · 등급 이름 0 ·
      🆕 정정 1차(R-1): `approx` 포함 행에 판정어(성립·불성립·발동·무효·기각·지지·판정 불가) 0 · (나)4 검사 줄
  R1 post7 회귀 — `test_post7_reconstruct.py`(스크립트형)가 «그대로» 통과 · post4~7 스크립트·산출물 작업트리 무변경
     (🔴 정정 1차 C-1: 기준 ref = **`154b80c`**(post8 산출 «이전» 마지막 커밋) — `HEAD` 는 post8 WIP 커밋 뒤라
      작업트리를 자기 자신과 비교하는 검사력 0 시험이 된다)

🔴 어떤 원본 파일도 고치지 않는다. 보존값·인용값은 **메모리 사본**에서만 흔든다.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import run_reconstruct_post5 as P5M
import run_reconstruct_post6 as P6M
import run_reconstruct_post7 as P7M
import run_reconstruct_post8 as P8

BASE = Path(__file__).resolve().parent
SRC = (BASE / "run_reconstruct_post8.py").read_text(encoding="utf-8")
NUMBERS = BASE / "RESULTS_RECONSTRUCT_POST8_NUMBERS.md"
BASE_REF = "154b80c"   # 🔴 정정 1차 C-1 — post8 산출 «이전» 마지막 커밋(HEAD 는 post8 WIP 뒤라 검사력 0)
NM, CODE, D0, PREC, LEGS, TR, PRESET, LABEL, FO, REENT = range(10)

# INTAKE_2026-09-18_post8.md §1 (신규 7건) · PD-11 코드 · LABELS 라벨 — 테스트 쪽 독립 사본
INTAKE = {  # (코드, 등록일, 정밀도, 레그, 차수, 프리셋, 라벨, first_only, §1-5 재진입)
    "우리로": ("046970", "2026-09-11", "exact",
             [24.20, 19.94, 17.00, 16.26, 13.32, 12.44, 0.54], 1, "HDR60", "TP", True, False),
    "원익": ("032940", None, "none", [19.49, 17.61, 15.54, 13.14], 1, "HDR60", "MANUAL", True, True),
    "JW신약": ("067290", "2026-09-01", "exact", [16.28, 12.68, 11.05, 10.78], 1, "HDR60", "MANUAL", True, False),
    "헥토파이낸셜": ("234340", None, "approx", [5.84, 2.98, 1.39, -2.28], 1, "HDR60", "MIX", True, True),
    "액스비스": ("0011A0", "2026-09-11", "exact", [11.64, 0.31], 1, "HDR60", "TP", True, False),
    "코데즈컴바인": ("047770", None, "approx", [13.20, 11.05, 11.03, 8.71, 6.59], 2, "사분위수", "TP", False, True),
    "우리기술": ("032820", "2026-09-09", "exact", [8.47, 8.47, 8.23, 4.75], 1, "HDR60", "TP", True, False),
}


def fake(legs, iv=True, w=1.0, fo=True, tr=1, under=False, h0=100.0, hi=100.0, preset="HDR60", label="TP"):
    """판정 함수용 가짜 건(DB 없이 식만 흔든다)."""
    return dict(legs=legs, iv=[(1.0, 2.0)] if iv else [], iv_net=[(1.0, 2.0)] if iv else [],
                w=w if iv else None, fo=fo, tr=tr, under=under, h0=h0, HI=hi, preset=preset, label=label,
                pmin=90.0, pmax=91.0, L=80.0, b1=(1.0, 2.0) if iv else None)


# ── P1 ────────────────────────────────────────────────────────────────────
def test_P1_frozen_constants():
    assert P8.END == P8.DB_UPTO == "2026-09-18"          # PD-1 · 발행 당일 봉 포함
    assert P8.POST8_POST_DATE == "2026-09-18" and P8.POST8_LOG_NO == "224416253270"
    assert P8.PROG_VER == "1.0.42" and P8.LEDGER_COMMIT == "b302f7f"
    assert P8.BOUNDARY == "2026-09-14" and P8.WIN_START == "2026-07-24"
    assert P8.SWEEP_D1 == "2026-09-21 15:35:00"
    assert P8.THR_MAIN == 0.022 and P8.THR_SENS == 0.020
    assert (P8.SEED, P8.NREP) == (P7M.SEED, P7M.NREP) == (P6M.SEED, P6M.NREP) == (20260815, 20000)
    assert P8.END != P7M.END   # 🔴 창이 post7 에서 «전진»했다(09-11 → 09-18)


# ── P2 ────────────────────────────────────────────────────────────────────
def test_P2_targets_match_intake():
    got = {t[NM]: tuple(t[1:]) for t in P8.TARGETS}
    assert set(got) == set(INTAKE)
    for nm, exp in INTAKE.items():
        assert got[nm] == exp, nm
    assert sum(len(t[LEGS]) for t in P8.TARGETS) == 30            # INTAKE §1 「신규 7건 30」
    for nm, code, _ in P8.FOLLOWUPS:                               # 후속 3건 = TARGETS 밖(PD-2 2)
        assert all(t[CODE] != code for t in P8.TARGETS), nm
    assert got["액스비스"][0] == "0011A0" and got["우리기술"][0] == "032820"   # PD-11
    assert got["우리기술"][0] != "041190"                          # ≠ 우리기술투자


def test_P2b_legs_equal_ledger_rows():
    rows = [r for r in csv.DictReader(open(BASE / "ledger_legs.csv", encoding="utf-8"))
            if r["post_log_no"] == P8.POST8_LOG_NO]
    assert len(rows) == 37
    for t in P8.TARGETS:
        led = [float(r["ret_pct"]) for r in sorted((r for r in rows if r["stock_name"] == t[NM]),
                                                   key=lambda r: int(r["leg_idx"]))]
        assert led == t[LEGS], t[NM]
    # 대칭 — 흔든 사본(17.00 → 17.01)은 원장과 불일치한다
    shaken = [24.20, 19.94, 17.01, 16.26, 13.32, 12.44, 0.54]
    led_w = [float(r["ret_pct"]) for r in rows if r["stock_name"] == "우리로"]
    assert shaken != led_w


# ── P3 ────────────────────────────────────────────────────────────────────
def test_P3_denominators():
    ex = [t[NM] for t in P8.TARGETS if t[PREC] == "exact"]
    ap = [t[NM] for t in P8.TARGETS if t[PREC] == "approx"]
    nn = [t[NM] for t in P8.TARGETS if t[PREC] == "none"]
    assert sorted(ex) == sorted(["우리로", "JW신약", "액스비스", "우리기술"])
    assert sorted(ap) == sorted(["헥토파이낸셜", "코데즈컴바인"]) and nn == ["원익"]
    assert all(t[FO] for t in P8.TARGETS if t[PREC] == "exact")                  # exact 4 = 전부 1차
    assert [t[NM] for t in P8.TARGETS if t[PREC] == "exact" and t[REENT]] == []   # §1-5 재진입 exact 0
    assert set(P8.STRUCT_BLOCK) == {"우리로"} and "우리로" in ex                   # `구조차단`(WRC-R5)
    assert not dict((t[NM], t[REENT]) for t in P8.TARGETS)["우리로"]              # 두 플래그를 섞지 않는다


# ── P4 / N1 ───────────────────────────────────────────────────────────────
def test_P4_rec_y1_opens_and_symmetry():
    ex = [t for t in P8.TARGETS if t[PREC] == "exact"]
    ap = [t for t in P8.TARGETS if t[PREC] == "approx"]
    y1 = sorted(t[NM] for t in ex if len(t[LEGS]) >= 4)
    assert y1 == sorted(["우리로", "JW신약", "우리기술"]) and len(y1) >= 3          # 열림(post7 은 2)
    assert len([n for n in y1 if n not in P8.STRUCT_BLOCK]) == 2                    # 「우리로 제외」 2 < 3
    assert len(y1) + sum(1 for t in ap if len(t[LEGS]) >= 4) == 5                   # approx 포함 5
    assert not P8.d3_hit(3, len(y1), 5)                                             # D-3 신고 대상 «아님»
    # N1 — 우리로를 뺀 사본에서는 최소 n 이 닫히고, approx 를 넣어야만 차므로 D-3 이 «걸린다»
    assert P8.d3_hit(3, 2, 4)


# ── P5 ────────────────────────────────────────────────────────────────────
def test_P5_verdict_functions_boundaries():
    L4 = [5.0, 4.0, 3.0, 2.0]
    assert P8.a_y1({"a": fake(L4), "b": fake(L4)})[3] == "최소 n 미달"
    assert P8.a_y1({k: fake(L4, iv=False) for k in "abc"})[3] == "판정 불가"
    assert P8.a_y1({k: fake(L4, w=1.0) for k in "abc"})[3] == "성립"
    assert P8.a_y1({"a": fake(L4, w=1.0), "b": fake(L4, iv=False), "c": fake(L4, w=5.0)})[3] == "불성립"
    # REC-Y3 문턱 1/3 — 정확히 닿으면 발동(post7 2/6 전례) · 한 건 덜 비면 미발동
    assert P8.a_y3({"a": fake(L4, iv=False), "b": fake(L4), "c": fake(L4)})[3] == "발동"
    assert P8.a_y3({"a": fake(L4, iv=False), "b": fake(L4), "c": fake(L4), "d": fake(L4)})[3] == "미발동"
    assert P8.a_z1({"a": fake(L4, under=True), "b": fake(L4), "c": fake(L4)})[3] == "성립"
    assert P8.a_z1({"a": fake(L4, under=True), "b": fake(L4), "c": fake(L4), "d": fake(L4)})[3] == "불성립"
    assert P8.a_z3({"a": fake(L4, hi=101.0), "b": fake(L4)})[3] == "발동"            # 1/2 = 문턱
    assert P8.a_z3({"a": fake(L4, hi=101.0), "b": fake(L4), "c": fake(L4)})[3] == "미발동"


# ── P6 ────────────────────────────────────────────────────────────────────
def test_P6_d3_gc_redep_guards():
    # D-3 (`PREREG_POST8.md:253`) — 양성·음성
    assert P8.d3_hit(3, 2, 3) and P8.d3_hit(3, 0, 6)
    assert not P8.d3_hit(3, 3, 5) and not P8.d3_hit(3, 1, 2)
    # P8-갈래계수 — (갈래, n, 답, 최소 n 충족?, 범주)
    same = [("주", 4, "x", True, "A"), ("제외", 3, "x", True, "A")]
    split = [("주", 4, "x", True, "A"), ("제외", 3, "y", True, "B")]
    one = [("주", 3, "x", True, "A"), ("제외", 2, "y", False, "B")]
    zero = [("주", 1, "x", False, "A"), ("제외", 0, "y", False, "B")]
    nomin = [("주", 4, "x", None, "A"), ("제외", 3, "y", None, "B")]
    assert P8.gc_status(same)[1] is False and "안 갈렸다" in P8.gc_status(same)[0]
    assert P8.gc_status(split)[1] is True                          # 🔴 양성 — 가드가 실제로 발화한다
    assert P8.gc_status(one) == ("충족 갈래 1 ⇒ 그 답(`:340`) = A", False)
    assert ":341" in P8.gc_status(zero)[0] and P8.gc_status(zero)[1] is False
    assert "대상 밖" in P8.gc_status(nomin)[0]
    # 「재진입 의존」 — 판정 항목 · 비판정 항목 · 한쪽 미달
    assert P8.re_dep_status(split, True)[1] is True
    assert P8.re_dep_status(nomin, True)[1] is True                # 최소 n 없는 판정 항목(REC-Y3 형)도 걸린다
    assert P8.re_dep_status(nomin, False)[1] is False              # 기록·관측 항목(REC-Y4·Z4)은 걸리지 않는다
    assert P8.re_dep_status(one, True) == ("답은 다르나 한쪽이 최소 n 미달 — 인쇄만", False)
    assert P8.re_dep_status(same, True) == ("같다", False)


# ── P7 ────────────────────────────────────────────────────────────────────
def test_P7_stamp_resolve_symmetric():
    fp = dict(umax="2026-09-23 15:46:25.855518", snap="2026-09-23")
    st1, t1, w1 = P8.stamp_resolve(None, fp, "T1")
    assert t1 == "T1" and w1 is True                                # 처음 ⇒ 새로 쓴다
    st2, t2, w2 = P8.stamp_resolve(st1, dict(fp), "T2")
    assert t2 == "T1" and w2 is False and st2 == st1                 # 같은 지문 ⇒ 최초 시각 유지 · 다시 쓰지 않는다
    assert "runs_kst" not in st1 and "runs_kst" not in st2          # 🆕 실행 기록은 stdout 전용(누적 폐지)
    st3, t3, w3 = P8.stamp_resolve(st2, dict(fp, umax="2026-09-28 15:46:00"), "T3")
    assert t3 == "T3" and w3 is True                                # 🔴 대칭 — 지문이 움직이면 새 시각 · 다시 쓴다
    disk = json.loads(P8.STAMP.read_text(encoding="utf-8"))
    assert set(disk) == {"fingerprint", "first_query_kst"}          # 🆕 stamp 파일 = 최초 시각 1개


# ── P8 ────────────────────────────────────────────────────────────────────
def test_P8_rec_z4_not_judged_and_decision4():
    assert "즉시 L 판정" not in SRC and "즉시 판정한다" not in SRC and "관측 인쇄만" in SRC
    assert P8.CLOSED_BY_DECISION4 is P7M.CLOSED_BY_DECISION4 and len(P8.CLOSED_BY_DECISION4) == 11
    assert "import random" not in SRC
    z4 = sorted(t[NM] for t in P8.TARGETS if t[PREC] == "exact" and t[FO] and len(set(t[LEGS])) >= 3)
    assert z4 == sorted(["우리로", "JW신약", "우리기술"])            # PD-13 「3건」(초판 2 정정)
    assert len(set(dict((t[NM], t[LEGS]) for t in P8.TARGETS)["우리기술"])) == 3   # 8.47 동률 = 같은 값


# ── P9 / N2 ───────────────────────────────────────────────────────────────
def _line(fname, n):
    return (BASE / fname).read_text(encoding="utf-8").splitlines()[n - 1]


CITED = [  # (파일, 줄, 그 줄에 있어야 하는 동결 인쇄값 문자열)
    ("RESULTS_RECONSTRUCT_POST7_NUMBERS.md", 117, "**2/6 = 33.3%**"),
    ("RESULTS_RECONSTRUCT_POST7_NUMBERS.md", 136, "gross **2/6** · net **2/6**"),
    ("RESULTS_RECONSTRUCT_POST7_NUMBERS.md", 140, "**1/6 = 16.7%**"),
    ("RESULTS_RECONSTRUCT_POST7_NUMBERS.md", 160, "**`REC-Z3` = 6/6 = 100.0%**"),
    ("RESULTS_RECONSTRUCT_POST6_NUMBERS.md", 103, "**5/10 = 50.0%**"),
    ("RESULTS_RECONSTRUCT_POST6_NUMBERS.md", 125, "gross **5/10** · net **5/10**"),
    ("RESULTS_RECONSTRUCT_POST6_NUMBERS.md", 129, "**3/10 = 30.0%**"),
    ("RESULTS_RECONSTRUCT_POST6_NUMBERS.md", 153, "**`REC-Z3` = 6/10 = 60.0%**"),
    ("RESULTS_RECONSTRUCT_POST5_NUMBERS.md", 72, "**4/6 = 66.7%**"),
    ("RESULTS_RECONSTRUCT_POST5_NUMBERS.md", 90, "gross **4/6** · net **4/6**"),
    ("PREREG_POST6.md", 562, "**2/6 = 33.3%**"),
    ("PREREG_POST6.md", 568, "**3/6 = 50.0%**"),
    ("PREREG_ANCHOR_REDESIGN.md", 68, "| post4 (2026-08-22) | 0/6 |"),
]


def test_P9_frozen_values_are_read_not_invented():
    for f, n, s in CITED:
        assert s in _line(f, n), (f, n)
    assert P8.FROZEN["post7"] == dict(P8.FROZEN["post7"], y3="2/6", y4n="2/6", z1="1/6", z3="6/6")
    assert (P8.FROZEN["post6"]["y3"], P8.FROZEN["post6"]["z1"], P8.FROZEN["post6"]["z3"]) == ("5/10", "3/10", "6/10")
    assert (P8.FROZEN["post5"]["y3"], P8.FROZEN["post5"]["z1"], P8.FROZEN["post5"]["z3"]) == ("4/6", "2/6", "3/6")
    assert (P8.FROZEN["post4"]["y3"], P8.FROZEN["post4"]["z3"]) == ("1/6", "0/6")
    ex4 = (BASE / "RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md").read_text(encoding="utf-8")
    assert "| **오늘 정확법(A-11)** | 1/6 |" in ex4
    q = _line("RESULTS_RECONSTRUCT_POST7_NUMBERS.md", 216)
    assert "솔트룩스" in q and "[−0.90%, +2.47%]" in q and P8.QUOTED_SOLTLUX == (-0.90, 2.47)


def test_N2_shaken_copy_mismatches():
    txt = _line("RESULTS_RECONSTRUCT_POST7_NUMBERS.md", 160)
    shaken = txt.replace("6/6 = 100.0%", "5/6 = 83.3%")
    assert "**`REC-Z3` = 6/6 = 100.0%**" not in shaken
    assert "**`REC-Z3` = 6/6 = 100.0%**" in _line("RESULTS_RECONSTRUCT_POST7_NUMBERS.md", 160)   # 원본 그대로


# ── P10 ───────────────────────────────────────────────────────────────────
def test_P10_approx_branches_and_limits():
    exp = ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31"]
    assert P8.APPROX_BRANCHES == {"헥토파이낸셜": exp, "코데즈컴바인": exp}          # PD-4 2 실측
    wkend = {"2026-08-22", "2026-08-23", "2026-08-29", "2026-08-30"}
    assert not (wkend & set(exp))
    assert P8.CONTRADICT == {"헥토파이낸셜": exp[:5]}                               # 「한번 더」 ∧ 직전 08-28
    assert P8.PRIOR_REG["헥토파이낸셜"] == ["2026-08-28"]
    assert set(P8.PRIOR_REG["코데즈컴바인"]) == {"2026-08-21", "2026-08-19"}
    assert P8.DECIMAL_LIMIT == {"우리로": ("17%", 17.00, 0)}                         # PD-10 1
    assert P7M.DECIMAL_LIMIT == {"범한퓨얼셀": 10.8}                                 # post7 전례 불변


# ── P11 ───────────────────────────────────────────────────────────────────
def test_P11_source_hygiene():
    for phrase in ("# RESULTS_RECONSTRUCT_POST8_NUMBERS — 기계 생성 (수정 금지)", "발행 당일(금 · 거래일) 봉 «포함»",
                   "실행 시 `max(date)`", "그 날짜 행수", "라이브 채택 대상이 아니다", "새 예측을 만들지 않았다",
                   "A-1 ~ A-11 전부 승계", "구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)", "모호 지점",
                   "방향 자기신고", "구조차단", "재진입 의존", "항등", "소수 0자리", "혼합 빈티지",
                   "제도 경계 2026-09-14 를 걸친다", "`[D−19, D]`", "`[D, END]`", "D+1(09-21) sweep 이후 읽음",
                   "approx` 포함 시 최소 n 이 차는 축", "(갈래 이름, n, 답)", "「정규장만」 갈래는 열지 않는다"):
        assert phrase in SRC, phrase
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", SRC, re.M)
    allow = {"__future__", "hashlib", "itertools", "json", "sys", "pathlib", "psycopg2", "reconstruct_prices",
             "run_reconstruct_post4", "run_reconstruct_post5", "run_reconstruct_post6", "run_reconstruct_post7",
             "run_tests"}
    assert not [m for m in imports if m.split(".")[0] not in allow]
    assert not re.search("adj_" r"factor\s*[*/]|[*/]\s*adj_" r"factor|adj_factor\"\]", SRC)
    assert "SELECT adj_factor" not in SRC and "adj_factor FROM" not in SRC
    sqls = re.findall(r'"\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b', SRC, re.I)
    assert sqls and all(s.upper() == "SELECT" for s in sqls)
    assert SRC.count("write_text") == 2                               # 산출물 + D-9 ① 도장
    assert 'RESULTS_RECONSTRUCT_POST8_NUMBERS.md").write_text' in SRC and "STAMP.write_text" in SRC
    assert P8.STAMP == BASE / "reconstruct_post8" / "query_stamp.json"
    for fn in ("bars", "feasible_exact", "feasible_pointwise", "iv_max", "iv_measure",
               "iv_min", "min_residual", "sigma20"):
        assert getattr(P8, fn) is getattr(P5M, fn), fn                 # 새 코드 0줄 — 같은 객체
    for fn in ("dd_h", "fmt_pct", "med", "win_bars"):
        assert getattr(P8, fn) is getattr(P6M, fn), fn


# ── P12 ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def numbers():
    if not NUMBERS.exists():
        pytest.fail("RESULTS_RECONSTRUCT_POST8_NUMBERS.md 가 없다 — 스크립트를 먼저 돌려야 한다")
    return NUMBERS.read_text(encoding="utf-8")


def test_P12_output_print_obligations(numbers):
    t = numbers
    assert t.startswith("# RESULTS_RECONSTRUCT_POST8_NUMBERS — 기계 생성 (수정 금지)")
    assert re.search(r"\| D-9 ① 쿼리 실행 시각\(KST\) \| \*\*2026-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\+09:00\*\*", t)
    assert "D-9 ② 창 구간 `max(daily_prices.updated_at)`" in t
    assert "**09-18 봉은 D+1(09-21) sweep 이후 읽음**" in t
    assert re.search(r"창 구간 `min\(updated_at\)` = 2026-\S+ \S+ ≥ 2026-09-21 15:35: (예|아니오)", t)
    assert "실행 시 `max(date)` = " in t and "기록만(창 아님)" in t
    lines = re.findall(r"^- .+: \*「창 `\[\S+, \S+\]` 은 제도 경계 2026-09-14 를 걸친다 — "
                       r"경계 전 `\d+` 봉 / 후 `\d+` 봉 · 혼합 빈티지」\*$", t, re.M)
    assert len(lines) == 18                          # exact 4 × `[D, END]` + approx 2 × 7 갈래
    assert t.count("`[D−19, D]`(POST8 :546)") == 18 and t.count("`[D, END]`(ANC §2-1)") == 18   # 두 창 다
    assert "**「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 3 / `approx` 포함 분모 5」**" in t
    d5 = re.findall(r"^\| `(?:REC-[YZ]\d|Q1-R3|HDR-D1|P6-R1')`[^|]* \| [^|]*\(#\d+[^|]*\) \| [^|]+ \| [\d~_]+ \| ",
                    t, re.M)
    assert len(d5) == 12 * 5                         # 12 항목 × (주·제외·§1-5 항등·절단 항등·approx)
    assert "라이브 채택 대상이 아니다" in t and "새 예측을 만들지 않았다" in t
    assert not re.search(r"GT-[A-F]|충족·참고용|조건 미달|낡음\(재실행 금지\)", t)   # 등급 이름 0(§6 단계)
    assert "「정규장만」 갈래는 열지 않는다" in t and "`adj_factor` 산술 **0**" in t


def test_P12c_approx_rows_carry_no_verdict_words(numbers):
    """🆕 정정 1차 R-1 — `approx` 포함 값에 판정 언어 금지(`PREREG_POST8.md:248` (나)2) · 대칭: 주 행에는 판정어가 있다."""
    rows = [ln for ln in numbers.splitlines() if ln.startswith("| ") and "_`approx` 포함(헥토·코데즈 7×7 조합" in ln]
    assert len(rows) == 12
    bad = re.compile(r"성립|발동|무효|기각|지지|판정 불가")
    assert not [ln for ln in rows if bad.search(ln)], [ln for ln in rows if bad.search(ln)]
    main = [ln for ln in numbers.splitlines() if ln.startswith("| `REC-Z3` ") and "주(우리로 포함" in ln]
    assert main and bad.search(main[0])                              # 🔴 대칭 — 검사가 판정어를 실제로 잡는다
    assert sum("주 갈래와 같은 쪽 " in ln for ln in rows) == 10     # 판정 없는 `REC-Y4`·`REC-Z4` 는 「값만」
    assert "**`D-3` (나)4 검사**(`PREREG_POST8.md:250`" in numbers
    assert "판정 언어 없이" in numbers                                # 자기모순 해소: 선언과 행이 같은 말을 한다


def test_P12b_output_denominators_and_branches(numbers):
    t = numbers
    assert "레그>=4 **`exact` 대상 3건**" in t and "「우리로 제외」 갈래: 대상 **2건**" in t
    assert "§1-5 재진입 제외(등록 자체 2번째 · exact 0건 ⇒ 항등)" in t
    assert "절단 제외(`[D−19,D]`<20 또는 창5<5 · 0건 ⇒ 항등)" in t
    assert "`P6-절단가드-A`**(창 `[D-19, D]` 봉수 < 20) 분자 = **0**" in t
    assert "주 분모 **0/7** · `exact` 갈래 **0/4**" in t
    for tag in ("post4", "post5", "post6", "post7"):
        assert re.search(rf"^\| {tag} \| ", t, re.M), tag     # post4~7 같은 스냅샷 재계산 행


# ── R1 ────────────────────────────────────────────────────────────────────
def test_R1_post7_guard_suite_still_passes():
    r = subprocess.run([sys.executable, "-X", "utf8", str(BASE / "test_post7_reconstruct.py")],
                       cwd=str(BASE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0 and "ALL PASS" in r.stdout, r.stdout[-2000:]


def test_R2_prior_scripts_and_outputs_untouched():
    paths = ["run_reconstruct_post4.py", "run_reconstruct_post4_exact.py", "run_reconstruct_post5.py",
             "run_reconstruct_post6.py", "run_reconstruct_post7.py", "reconstruct_prices.py",
             "RESULTS_RECONSTRUCT_POST4_NUMBERS.md", "RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md",
             "RESULTS_RECONSTRUCT_POST5_NUMBERS.md", "RESULTS_RECONSTRUCT_POST6_NUMBERS.md",
             "RESULTS_RECONSTRUCT_POST7_NUMBERS.md", "RESULTS_RECONSTRUCT_POST7.md", "test_post7_reconstruct.py"]
    r = subprocess.run(["git", "diff", "--quiet", BASE_REF, "--"] + paths, cwd=str(BASE))
    assert r.returncode == 0                                   # 작업트리 = 154b80c(한 byte 도 안 고쳤다)
    # 🔴 대칭 — 같은 비교가 post8 파일에선 «다르다»를 낸다(154b80c 엔 이 스크립트가 없다 ⇒ 검사력 확인)
    r2 = subprocess.run(["git", "cat-file", "-e", f"{BASE_REF}:./run_reconstruct_post8.py"], cwd=str(BASE),
                        capture_output=True)
    assert r2.returncode != 0
