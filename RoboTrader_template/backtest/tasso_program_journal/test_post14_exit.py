# -*- coding: utf-8 -*-
"""`run_exit_v2_post14.py` 가드 시험 — 구조·상수·문형 검사. 🔴 실제 `RESULTS_EXIT_V2_POST14_NUMBERS.md` 경로로 `main()` 재실행 0
(F-7 · post9 사고) — 결정성 시험은 «임시 경로» 로만 돌리고 실제 NUMBERS 는 읽기만 한다. DB 접속 0.

  P1  TRADES = 원장 post14 2행/8레그와 일치(라벨·레그·「손실률」 마스크·`breakeven_note`·`open_ended`) · `unknown` 0 · 형 `표준형` 2/2
  P2  분모 구성 — 신규 `TP` 2 · `EXIT-E1` 2 · `EXIT-E4` 2 · `EXIT-X2` 2 · 병기 `(약한 자리 미완결 독법)` X2 1 · 후속 0 · `MANUAL`·`SL` 0
  P3  옛 스크립트·옛 NUMBERS 작업트리 변경 0 · `EXIT-X6` 재사용 객체
  P4  (임시 경로) `main()` 결정적 — 두 번 돌려 byte 동일 · 실제 NUMBERS 와 같으면(있을 때) 일치
  P5  (NUMBERS) 의무 줄 — 감시 모드 머리 · `P12-착수상한` · 라이브 문언 · `P12-최소n갈림`
  P6  (NUMBERS) 구조 — 최소 n 미달 갈래 계수 · 병기 인쇄만 · 후속 확장 인쇄만 · `EXIT-E3`/`X7` ⛔(`I-4` 누적 경로)
실행: `python -m pytest test_post14_exit.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import pytest

import run_exit_v2_post8 as E8
import run_exit_v2_post14 as E14
from run_exit_v2_post6 import x6_legs

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_EXIT_V2_POST14_NUMBERS.md"
LOG = "224460275556"
NAME, LABEL, LEGS, LOSSM, OPEN_N, TILDE, BE, NEW = range(8)


def _txt():
    if not NUM.exists():
        pytest.skip("RESULTS_EXIT_V2_POST14_NUMBERS.md 가 아직 없다 — 러너 실행 «뒤» 시험")
    return NUM.read_text(encoding="utf-8")


def _ledger():
    rows = [r for r in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]
    legs = [r for r in csv.DictReader((BASE / "ledger_legs.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]
    return rows, legs


def test_P1_trades_match_ledger():
    rows, legs = _ledger()
    assert len(rows) == 2 == len(E14.TRADES) and len(legs) == 8 == sum(len(t[LEGS]) for t in E14.TRADES)
    for t, r in zip(E14.TRADES, sorted(rows, key=lambda r: int(r["item_no"]))):
        ls = [l for l in legs if l["item_no"] == r["item_no"]]
        assert t[NAME].split()[0] == r["stock_name"], (t[NAME], r["stock_name"])
        assert t[LEGS] == [float(l["ret_pct"]) for l in ls], t[NAME]
        assert t[LOSSM] == [int(l["is_loss"]) for l in ls], t[NAME]
        assert r["narrative"].startswith("라벨 %s" % t[LABEL]), (t[NAME], r["narrative"][:12])
        assert (r["breakeven_exit"] == "1") == t[BE], t[NAME]
        assert (r["reg_date_precision"] == "exact") == t[NEW], t[NAME]      # 신규 2/2 = `exact`(재진입 신규 `none` 0)
        assert (r["open_ended"] == "1") == t[OPEN_N], t[NAME]
    labs = [t[LABEL] for t in E14.TRADES]
    assert labs.count("TP") == 2 and labs.count("MANUAL") == 0 and labs.count("SL") == 0 and labs.count("MIX") == 0
    assert E14.UNREGISTERED_FORMS == [] and E14.FORM_WHITELIST == {"표준형"}
    assert E14.WEAK_ONLY == (E14.SAMKI,) and (E14.X9_MAIN, E14.X9_BROAD) == (0, 0)
    assert E14.DB_UPTO == "2026-10-30" and E14.BOUND_UPPER == "2026-11-04" and E14.E3_CUM_PRIOR == 2
    assert E14.FOLLOW_SRC == {} and all(t[NEW] for t in E14.TRADES)


def test_P2_denominators():
    DN = E8.denoms(E14.TRADES)
    assert (DN["tp_n"], DN["e1_n"], DN["e4_n"], DN["x2_n"], DN["om"]) == (2, 2, 2, 2, 0)
    assert [t[NAME] for t in DN["tp_new"]] == [E14.SAMKI, E14.MELCON]
    # 병기 `(약한 자리 미완결 독법)` — 삼기에너지솔루션즈 마지막 레그 제거 · X2 분모 2 → 1
    TW = [t[:E8.OPEN_N] + (True,) + t[E8.OPEN_N + 1:] if t[NAME] in E14.WEAK_ONLY else t for t in E14.TRADES]
    DW = E8.denoms(TW)
    assert (DW["e1_n"], DW["e4_n"], DW["x2_n"], DW["om"]) == (2, 2, 1, 1)
    gw = [t for t in DW["e1"] if t[NAME] == E14.SAMKI][0]
    assert x6_legs(gw, "narr") == [22.33, 18.02, 12.84]
    # 후속 0 — 신규 확장도 같은 분모
    ext = E8.denoms(E14.as_new(E14.TRADES))
    assert ext["tp_n"] == 2 and ext["e4_n"] == 2 and ext["x2_n"] == 2
    # (P) 갈래 — `~` 레그 표지 0 ⇒ (P) X2 분모 2 · om 0
    DP = E8.denoms(E14.TRADES, basis="tilde")
    assert (DP["tp_n"], DP["x2_n"], DP["om"]) == (2, 2, 0)


def test_P3_reuse_and_old_untouched():
    from run_exit_v2_post6 import x6_legs as x6
    assert E14.x6_legs is x6 and E14.denoms is E8.denoms and E14.recount is E8.recount
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_exit_v2_post4.py", "run_exit_v2_post5.py", "run_exit_v2_post6.py",
                        "run_exit_v2_post7.py", "run_exit_v2_post8.py", "run_exit_v2_post9.py", "run_exit_v2_post10.py",
                        "run_exit_v2_post11.py", "run_exit_v2_post12.py", "run_exit_v2_post13.py",
                        "RESULTS_EXIT_V2_POST10_NUMBERS.md", "RESULTS_EXIT_V2_POST11_NUMBERS.md",
                        "RESULTS_EXIT_V2_POST12_NUMBERS.md", "RESULTS_EXIT_V2_POST13_NUMBERS.md"],
                       cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def test_P4_deterministic_in_tmp(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    E14.OUT.clear()
    assert E14.main(a) == 0
    E14.OUT.clear()
    assert E14.main(b) == 0
    assert a.read_bytes() == b.read_bytes()
    if NUM.exists():           # 실제 NUMBERS 가 있으면 같은 입력 ⇒ 같은 바이트(읽기만)
        assert a.read_bytes() == NUM.read_bytes()


def test_P5_duty_lines():
    t = _txt()
    assert "**창 종료 2026-10-30 = 발행일(토) 직전 거래일(금) 봉 «포함» · `END` · 3축 · PD-1**" in t
    assert re.search(r"\*\*실행 시 `max\(date\)` = 2026-11-26 · 그 날짜 행수 2,774 — 기록만\(창 아님\)\*\*", t)
    assert "판정 축 3(`SEL-`·`EXIT-`·`S5`) · 중단 7" in t and "종결 `ANC-`" in t and "감시 모드 4회차" in t
    assert "(첫 러너 `RESULTS_SELECTION_POST14_NUMBERS.md` 신고 줄 없음 — 인용 불가)" in t
    assert "라운드 상한 250만(🔒 사장님 2026-11-01 00:0x" in t and "착수 전 누계 ≈82만" in t
    pr = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert pr[55] in t.splitlines() and pr[57] in t.splitlines()
    assert "`P12-최소n갈림`" in t and "(약한 자리 미완결 독법, " in t
    assert "`P10-기업행위봉`: 예(보수) · 봉을 읽지 않음 · 신고 줄 PD-36 인용 **0/2**" in t
    assert not re.search(r"\bGT-[A-F]\b", t) and "\r" not in t
    assert "[[PREREG_POST11]]" not in t and "[[LABELS_2026-10-08_post11]]" not in t
    assert "**조회 0회**" in t


def test_P6_structure():
    t = _txt()
    s12 = t.split("## §12.")[1].split("### §12-2")[0]
    rows = [ln for ln in s12.splitlines() if ln.startswith("| `EXIT-")]
    for axis in ("E1", "E4", "X2"):
        r = [ln for ln in rows if ln.startswith("| `EXIT-%s` | (서술) 주" % axis)]
        assert len(r) == 1 and "| 2 |" in r[0] and "최소 n 미달" in r[0] and "계수" in r[0], axis
    x2w = [ln for ln in rows if ln.startswith("| `EXIT-X2` | 병기 `(약한 자리 미완결 독법)`")]
    assert len(x2w) == 1 and "| 1 |" in x2w[0] and "최소 n 미달" in x2w[0]
    ext = [ln for ln in rows if "후속 확장" in ln]
    assert ext and all("인쇄만" in ln for ln in ext)
    assert "`EXIT-E3`" in t and "⛔ 판정 불가 유지" in t and "= 2 < 3" in t     # `I-4` 누적 경로 — 직전 확정 2 + 이번 0
    assert "「샌즈 제외」" not in t
    assert "| 32 |" in s12      # `EXIT-E2` 누적 (가) 32 · 확인 7 제외 31
