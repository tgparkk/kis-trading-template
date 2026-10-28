# -*- coding: utf-8 -*-
"""`run_exit_v2_post10.py` 가드 시험 (post9 판 구조 승계 · 짧게 · DB 접속 0).

  P1  `TRADES` = 원장 post10 12행의 레그·완결·note·신규·「손실률」 마스크 · 라벨 = 원장 narrative 선두(`라벨 TP`/`라벨 MIX`)
  N1  대칭 — 레그 한 칸을 흔들면 P1 비교가 잡는다
  N2  대칭 — 약한 자리 단독 대안 = 「그 건만 미완결 플래그를 뒤집은 사본의 `denoms`」 와 같은 집합
  P2  상류 재사용 — 통계 핵·`denoms`·`recount` 가 «그 객체»
  P3  구성 사실 — 분모 7/6/2/4(서술) · 7/3/7((P)) · 미완결 3/7 (PD-5 표)
  P4  🔒 배선 — E1 (P) 계수 · E4 (P) 민감도 열 · X2 계수 갈래 5(서술·(P)·단독 대안 2·좁은 분모) · 둘 다 대안·MIX 확장·후속 확장 인쇄만
  P5  의무 인쇄 줄 — 창 종료·`max(date)`·§0-1 라이브 금지 문언(PREREG_POST10 `:56`·`:58` 축자)·D-2 세 수·D-3·`P9-공통독법`·
      `F-3` 신고 줄·충돌 신고 두 줄·D-5 표 전 행 세 쪽 · 등급 이름 0 · `nan` 0
  P6  판정값 스냅샷(구조 값만 — 값 스냅샷은 실행 뒤 보강)
  R1  재실행 byte 동일(메모리 → 임시 파일)
  R2  상류·post9 산출물이 `8e014ca` 블롭과 byte 동일 · 옛 원장 행 불변(접두 일치) + 대칭(그 ref 에 post10 스크립트 없음)
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
import run_exit_v2_post10 as E10

BASE = Path(__file__).resolve().parent
NUMBERS10 = BASE / "RESULTS_EXIT_V2_POST10_NUMBERS.md"
BASE_REF = "8e014ca"
LOG10 = "224429747319"
GRADE_NAMES = ["충족·참고용", "조건 미달", "낡음(재실행 금지)", "GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F"]


def _t10():
    assert NUMBERS10.exists(), "run_exit_v2_post10.py 를 먼저 돌린다"
    return NUMBERS10.read_text(encoding="utf-8")


def _ledger():
    with open(BASE / "ledger_trades.csv", encoding="utf-8") as f:
        tr = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG10]
    with open(BASE / "ledger_legs.csv", encoding="utf-8") as f:
        lg = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG10]
    out = []
    for r in tr:
        legs = [(float(x["ret_pct"]), int(x["is_loss"])) for x in lg if x["item_no"] == r["item_no"]]
        out.append((r["stock_name"], [v for v, _m in legs], [m for _v, m in legs], r["open_ended"] == "1",
                    r["breakeven_exit"] == "1", r["reg_date_precision"] != "none", r["narrative"].split(" ")[1]))
    return out


def _mine(trades):
    return [(t[E10.NAME].split()[0], list(t[E10.LEGS]), list(t[E10.LOSSM]), t[E10.OPEN_N], t[E10.BE], t[E10.NEW],
             t[E10.LABEL]) for t in trades]


def test_P1_trades_match_ledger():
    assert len(E10.TRADES) == 12 and _mine(E10.TRADES) == _ledger()
    assert {t[E10.LABEL] for t in E10.TRADES} == {"TP", "MIX"} and not any(t[E10.RANGE] for t in E10.TRADES)
    assert all(len(t[E10.LOSSM]) == len(t[E10.LEGS]) for t in E10.TRADES)
    assert sum(sum(t[E10.LOSSM]) for t in E10.TRADES) == 2 and sum(len(t[E10.LEGS]) for t in E10.TRADES) == 34


def test_N1_symmetric_mutation():
    bad = [list(t) for t in E10.TRADES]
    bad[8][E10.LEGS] = [16.93, 12.36, 7.65, 7.63]      # HT 5레그 → 4레그
    assert _mine([tuple(b) for b in bad]) != _ledger(), "흔든 칸을 잡아야 한다"


def test_N2_weak_alternatives_match_flag_flip():
    DN = E10.denoms(E10.TRADES)
    base = {t[E10.NAME] for t in DN["x2"]}
    for nm in E10.WEAK_ONLY:
        flipped = [tuple(t[:E10.OPEN_N]) + (True,) + tuple(t[E10.OPEN_N + 1:]) if t[E10.NAME] == nm else t
                   for t in E10.TRADES]
        got = {t[E10.NAME] for t in E10.denoms(flipped)["x2"]}
        assert got == base - {nm} and len(got) == 3, nm


def test_P2_upstream_reuse():
    assert E10.nonincreasing is E6.nonincreasing and E10.x6_legs is E6.x6_legs and E10.x2_leg is E6.x2_leg
    assert E10.denoms is E8.denoms and E10.recount is E8.recount and E10.e1_ok is E8.e1_ok and E10.mark is E8.mark
    assert (E10.TP_MIN_N, E10.E4_MIN_N, E10.E2_MIN_N, E10.X2_MIN_N, E10.E3_MIN_N) == (3, 3, 3, 3, 3)
    assert (E10.EPS, E10.E1_MIN, E10.E2_MIN, E10.BE_MAX) == (0.05, 0.90, 0.80, 1.0)


def test_P3_construction_facts():
    DN, DP = E10.denoms(E10.TRADES), E10.denoms(E10.TRADES, basis="tilde")
    assert (DN["tp_n"], DN["e1_n"], DN["e4_n"], DN["x2_n"], DN["om"]) == (7, 6, 2, 4, 3)
    assert (DP["e1_n"], DP["e4_n"], DP["x2_n"], DP["om"]) == (7, 3, 7, 0)
    assert {t[E10.NAME].split()[0] for t in DN["x2"]} == {"범한퓨얼셀", "서산", "성호전자", "뷰노"}
    sa = [t for t in DN["x2"] if t[E10.BE]]
    assert {t[E10.NAME].split()[0] for t in sa} == {"범한퓨얼셀", "서산", "뷰노"}
    be_all = [t for t in E10.TRADES if t[E10.BE]]
    assert len(be_all) == 6 and len([t for t in be_all if t[E10.NEW]]) == 5
    assert len([t for t in be_all if t[E10.NEW] and t[E10.LABEL] == "TP" and not t[E10.OPEN_N]]) == 3


def _d5(t):
    sec = t.split("## §12.")[1].split("### §12-2.")[0]
    return {tuple(c.strip() for c in ln.strip("|").split("|")[:2]): [c.strip() for c in ln.strip("|").split("|")]
            for ln in sec.splitlines() if ln.startswith("| `EXIT-")}


def test_P4_lock_wiring():
    d = _d5(_t10())
    assert d[("`EXIT-E1`", "(P) 민감도 갈래")][4].startswith("계수"), "확인 8 — E1 은 두 갈래 최소 n ⇒ 갈림 검사"
    assert d[("`EXIT-E4`", "(P) 민감도 갈래")][4].startswith("민감도 열"), "확인 8 — E4 (P) 는 여는 데 쓰지 않는다"
    x2 = {k[1]: v for k, v in d.items() if k[0] == "`EXIT-X2`"}
    counted = [k for k, v in x2.items() if v[4].startswith("계수") and "미달" not in v[4]]
    assert len(counted) == 5, counted                         # (서술) · (P) · 단독 대안 둘 · 좁은 분모
    assert [int(x2[k][2]) for k in x2 if k in counted] == [4, 7, 3, 3, 3]
    assert x2["약한 자리 둘 다 미완결"][4].startswith("인쇄만") and x2["약한 자리 둘 다 미완결"][2] == "2"
    assert x2["`MIX` 확장"][4].startswith("인쇄만") and x2["후속 확장 (서술)"][4] == "인쇄만(계수 안 함)"
    for ax in ("`EXIT-E1`", "`EXIT-E4`"):
        assert d[(ax, "후속 확장 (서술)")][4] == "인쇄만(계수 안 함)"
    assert d[("`EXIT-E2` 누적", "「샌즈 제외」(🔒 #1 ⓐ)")][4].startswith("인쇄만"), "🔒 #1 ⓐ — 샌즈 제외는 계수 아님"
    DN = E10.denoms(E10.TRADES)
    assert DN["e4_n"] == 2 < E10.E4_MIN_N and DN["e1_n"] == 6 >= E10.TP_MIN_N


def test_P5_mandatory_lines():
    t = _t10()
    pre = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert pre[55] == E10.LIVE_39 and pre[57] == E10.LIVE_41
    lines = t.splitlines()
    assert E10.LIVE_39 in lines and E10.LIVE_41 in lines
    assert "**창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · `END` · 전 축(`WRC-` 포함) · PD-1**" in lines
    assert "**실행 시 `max(date)` = 2026-10-07 · 그 날짜 행수 2,767 — 기록만(창 아님)**" in t
    assert "**미등록 형: 없음**" in t and "`EXIT-E1` **6** · `EXIT-E4` **2** · `EXIT-X2` **4**" in t
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 E1 6 · E4 2 · X2 4 / `approx` 포함 분모 E1 6 · E4 2 · X2 4」" in t
    assert re.search(r"「`P9-공통독법`: 답 = 판정 · \(나\)4 결과 = 대상 없음", t)
    assert "*「`P10-기업행위봉`: 기업행위 건 0/9 — " in t and "`adj_factor` 산술 0 · 처리 = (나)」*" in t
    assert "답(참고) · 세지 않는다" in t
    assert "1. **후속 확장 갈래 — post7 셈 ↔ post8 안 셈**" in t and "2. **§1-8 문자 ↔ post6 PD-4**" in t
    for key, cells in _d5(t).items():
        assert len(cells) == 5 and all(cells) and cells[2] != "—" and cells[3] != "—", key
    assert "nan" not in t and not [g for g in GRADE_NAMES if g in t]
    assert "라이브 채택 대상이 아니다" in t


def test_P6_structure_snapshot():
    t = _t10()
    assert "| 라벨 동결 | `TP` **10**(신규 7 · 후속 3) · `MIX` **2**" in t
    assert "재계산 불일치 **0건**" in t, "옛 회차 재계산 ↔ 동결 인용값(post9 행 포함)"
    assert "연결 지점 증가 1/3 관측" in t
    assert "- **`EXIT-E1` (서술) 주 = 6/6 = 100.0%** ⇒ **✅ 지지**" in t
    assert "답이 **같다 — 갈리지 않는다**" in t and "- ⇒ (서술) 주 n = 2 < 3 ⇒ **⛔ 최소 n 미달" in t
    assert "- **`EXIT-X2` (서술) 주 = 2/4 = 50.0%** ⇒ **❌ 불성립**" in t
    assert "- `EXIT-X2`: 최소 n 을 채운 계수 갈래 **5개** ⇒ 전부 같은 답(❌) — **갈리지 않는다**" in t
    assert "- `EXIT-E1`: 최소 n 을 채운 계수 갈래 **2개** ⇒ 전부 같은 답(✅) — **갈리지 않는다**" in t
    assert "| **누적 (가)** | **42/42 = 100.0%** | **38/38 = 100.0%** | **23/23 = 100.0%** | **15/25 = 60.0%** |" in t
    assert "- `EXIT-E2`(병기 축 · 판정 아님): 최소 n 을 채운 계수 갈래 **4개** ⇒ 🔴 갈린다" in t
    assert "⛔ 두 규칙 구분 불가" in t and "6글 연속" in t
    assert "= **1 < 3**(§4 **#19**)" in t, "E3 누적 = post6 1 + 이후 0"
    assert "누적 `EXIT-E2` (가) **" in t and "7글 연속" in t


def test_R1_rerun_byte_identical():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "N.md"
        E10.main(numbers=out)
        assert out.read_bytes() == NUMBERS10.read_bytes()


def _blob(rel):
    out = subprocess.run(["git", "show", f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/{rel}"],
                         cwd=BASE, capture_output=True)
    assert out.returncode == 0, rel
    return out.stdout


def _lf(b):
    return b.replace(bytes([13, 10]), bytes([10]))      # Windows `write_text` 가 CRLF 로 쓴다 — 줄끝 차이는 내용 차이가 아니다


def test_R2_upstream_untouched():
    for rel in ("run_exit_v2_post4.py", "run_exit_v2_post5.py", "run_exit_v2_post6.py", "run_exit_v2_post7.py",
                "run_exit_v2_post8.py", "run_exit_v2_post9.py", "RESULTS_EXIT_V2_POST7_NUMBERS.md",
                "RESULTS_EXIT_V2_POST8_NUMBERS.md", "RESULTS_EXIT_V2_POST9_NUMBERS.md"):
        assert hashlib.md5(_lf((BASE / rel).read_bytes())).hexdigest() == hashlib.md5(_lf(_blob(rel))).hexdigest(), rel
    for rel in ("ledger_trades.csv", "ledger_legs.csv"):          # 옛 원장 행 불변 — 현재 파일이 그 ref 의 접두를 그대로 품는다
        assert _lf((BASE / rel).read_bytes()).startswith(_lf(_blob(rel))), rel
    miss = subprocess.run(["git", "cat-file", "-e",
                           f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/run_exit_v2_post10.py"],
                          cwd=BASE, capture_output=True)
    assert miss.returncode != 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
