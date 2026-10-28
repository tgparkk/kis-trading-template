# -*- coding: utf-8 -*-
"""`run_exit_v2_post9.py` 가드 시험 (post8 판 구조 승계 · 짧게 · DB 접속 0).

  P1  `TRADES` = 원장(30aed89) post9 6행의 레그·완결·note·신규 · 라벨 = LABELS(`TP` 6)
  N1  대칭 — 레그 한 칸을 흔들면 P1 비교가 잡는다
  P2  상류 재사용 — 통계 핵·`denoms`·`recount` 가 «그 객체»
  P3  🔒 #4 배선 — E1 (P) 계수(주·(P) 둘 다 최소 n) · E4 (P) 민감도 열(주 미달 ⇒ 열지 않음) · X2 (P) 인쇄만 · 후속 확장 인쇄만
  P4  의무 인쇄 줄 — 창 종료·`max(date)`·§0-1 라이브 금지 문언(PREREG_POST9 `:39`·`:41` 축자)·D-2 세 수·D-3·`P9-공통독법`·
      충돌 신고 두 줄·D-5 표 전 행 세 쪽 · 등급 이름 0 · `nan` 0
  P5  판정값 스냅샷
  R1  재실행 byte 동일(메모리 → 임시 파일)
  R2  상류·post8 산출물이 `30aed89` 블롭과 byte 동일 + 대칭(그 ref 에 post9 스크립트 없음)
"""
from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import run_exit_v2_post6 as E6
import run_exit_v2_post8 as E8
import run_exit_v2_post9 as E9

BASE = Path(__file__).resolve().parent
NUMBERS9 = BASE / "RESULTS_EXIT_V2_POST9_NUMBERS.md"
BASE_REF = "30aed89"
LOG9 = "224421214462"
GRADE_NAMES = ["충족·참고용", "조건 미달", "낡음(재실행 금지)", "GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F"]


def _t9():
    assert NUMBERS9.exists(), "run_exit_v2_post9.py 를 먼저 돌린다"
    return NUMBERS9.read_text(encoding="utf-8")


def _ledger():
    with open(BASE / "ledger_trades.csv", encoding="utf-8") as f:
        tr = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG9]
    with open(BASE / "ledger_legs.csv", encoding="utf-8") as f:
        lg = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG9]
    out = []
    for r in tr:
        legs = [float(x["ret_pct"]) for x in lg if x["item_no"] == r["item_no"]]
        out.append((r["stock_name"], legs, r["open_ended"] == "1", r["breakeven_exit"] == "1",
                    r["reg_date_precision"] != "none"))
    return out


def _mine(trades):
    return [(t[E9.NAME].split()[0], list(t[E9.LEGS]), t[E9.OPEN_N], t[E9.BE], t[E9.NEW]) for t in trades]


def test_P1_trades_match_ledger():
    assert _mine(E9.TRADES) == _ledger()
    assert {t[E9.LABEL] for t in E9.TRADES} == {"TP"} and not any(t[E9.TILDE] or t[E9.RANGE] for t in E9.TRADES)
    assert all(sum(t[E9.LOSSM]) == 0 and len(t[E9.LOSSM]) == len(t[E9.LEGS]) for t in E9.TRADES)


def test_N1_symmetric_mutation():
    bad = [list(t) for t in E9.TRADES]
    bad[4][E9.LEGS] = [3.80, 3.79]                  # 첨단 3레그 → 2레그
    assert _mine([tuple(b) for b in bad]) != _ledger(), "흔든 칸을 잡아야 한다"


def test_P2_upstream_reuse():
    assert E9.nonincreasing is E6.nonincreasing and E9.x6_legs is E6.x6_legs and E9.x2_leg is E6.x2_leg
    assert E9.denoms is E8.denoms and E9.recount is E8.recount and E9.e1_ok is E8.e1_ok and E9.mark is E8.mark
    assert (E9.TP_MIN_N, E9.E4_MIN_N, E9.E2_MIN_N, E9.X2_MIN_N, E9.E3_MIN_N) == (3, 3, 3, 3, 3)
    assert (E9.EPS, E9.E1_MIN, E9.E2_MIN, E9.BE_MAX) == (0.05, 0.90, 0.80, 1.0)


def _d5(t):
    sec = t.split("## §12.")[1].split("### §12-2.")[0]
    return {tuple(c.strip() for c in ln.strip("|").split("|")[:2]): [c.strip() for c in ln.strip("|").split("|")]
            for ln in sec.splitlines() if ln.startswith("| `EXIT-")}


def test_P3_lock4_wiring():
    d = _d5(_t9())
    assert d[("`EXIT-E1`", "(P) 민감도 갈래")][4].startswith("계수"), "#4-나 ⓓ — E1 은 두 갈래 최소 n ⇒ 갈림 검사"
    assert d[("`EXIT-E4`", "(P) 민감도 갈래")][4].startswith("민감도 열"), "#4-나 ⓓ — E4 (P) 는 여는 데 쓰지 않는다"
    assert d[("`EXIT-X2`", "(P) 민감도 열")][4].startswith("인쇄만(🔒 #4-가 ⓒ)")
    for ax in ("`EXIT-E1`", "`EXIT-E4`", "`EXIT-X2`"):
        assert d[(ax, "후속 확장 (서술)")][4] == "인쇄만(🔒 #4-다 ⓐ)"
    # 대칭 — 주 갈래가 최소 n 을 채웠다면 E4 (P) 는 계수(갈림 검사)로 바뀐다(배선이 조건부임을 확인)
    DN = E9.denoms(E9.TRADES)
    assert DN["e4_n"] == 2 < E9.E4_MIN_N and DN["e1_n"] == 5 >= E9.TP_MIN_N


def test_P4_mandatory_lines():
    t = _t9()
    pre = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").splitlines()
    assert pre[38] == E9.LIVE_39 and pre[40] == E9.LIVE_41
    lines = t.splitlines()
    assert E9.LIVE_39 in lines and E9.LIVE_41 in lines
    assert "**창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**" in lines
    assert "**실행 시 `max(date)` = 2026-09-29 · 그 날짜 행수 2,765 — 기록만(창 아님)**" in t
    assert "**미등록 형: 없음**" in t and "`EXIT-E1` **5** · `EXIT-E4` **2** · `EXIT-X2` **2**" in t
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 E1 5 · E4 2 · X2 2 / `approx` 포함 분모 E1 5 · E4 2 · X2 2」" in t
    assert re.search(r"「`P9-공통독법`: 답 = 판정 · \(나\)4 결과 = 대상 없음", t)
    assert "1. **후속 확장 갈래 — post7 셈 ↔ post8 안 셈**" in t and "2. **§1-8 문자 ↔ post6 PD-4**" in t
    for key, cells in _d5(t).items():
        assert len(cells) == 5 and all(cells) and cells[2] != "—" and cells[3] != "—", key
    assert "nan" not in t and not [g for g in GRADE_NAMES if g in t]


def test_P5_verdict_snapshot():
    t = _t9()
    assert "- **`EXIT-E1` (서술) 주 = 5/5 = 100.0%** ⇒ **✅ 지지**" in t
    assert "답이 **같다 — 갈리지 않는다**" in t
    assert "- ⇒ (서술) 주 n = 2 < 3 ⇒ **⛔ 최소 n 미달" in t
    assert "- **`EXIT-X2` (서술) 주 = 0/2 = 0.0%** ⇒ **⛔ 보류 — 완결 `TP` 2 < 3" in t
    assert "누적 `EXIT-E2` (가) **10/19 = 52.6%** ⇒ **❌ 불성립 — 6글 연속**" in t
    assert "| **누적 (가)** | **35/35 = 100.0%** | **32/32 = 100.0%** | **21/21 = 100.0%** |" in t
    assert "재계산 불일치 **0건**" in t and "🔴 **+8.84%p 증가**" in t
    assert "⛔ 두 규칙 구분 불가" in t and "**1 < 3**(§4 **#19**)" in t


def test_R1_rerun_byte_identical():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "N.md"
        E9.main(numbers=out)
        assert out.read_bytes() == NUMBERS9.read_bytes()


def _blob(rel):
    out = subprocess.run(["git", "show", f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/{rel}"],
                         cwd=BASE, capture_output=True)
    assert out.returncode == 0, rel
    return out.stdout


def test_R2_upstream_untouched():
    for rel in ("run_exit_v2_post4.py", "run_exit_v2_post5.py", "run_exit_v2_post6.py", "run_exit_v2_post7.py",
                "run_exit_v2_post8.py", "RESULTS_EXIT_V2_POST7_NUMBERS.md", "RESULTS_EXIT_V2_POST8_NUMBERS.md",
                "RESULTS_EXIT_V2_POST8.md"):
        assert hashlib.md5((BASE / rel).read_bytes()).hexdigest() == hashlib.md5(_blob(rel)).hexdigest(), rel
    # 원장은 post10 행이 뒤에 append 됐다(`0cc2e5e`) ⇒ 「post9 상태(= 기준 블롭)가 순수 prefix」 로 본다
    for rel in ("ledger_trades.csv", "ledger_legs.csv"):
        assert (BASE / rel).read_bytes().startswith(_blob(rel)), f"{rel}: {BASE_REF} 상태가 prefix 가 아니다"
    miss = subprocess.run(["git", "cat-file", "-e",
                           f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/run_exit_v2_post9.py"],
                          cwd=BASE, capture_output=True)
    assert miss.returncode != 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
