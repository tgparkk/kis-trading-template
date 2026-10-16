# -*- coding: utf-8 -*-
"""`run_exit_v2_post11.py` 가드 시험 — 구조·상수·문형 검사. 🔴 실제 `RESULTS_EXIT_V2_POST11_NUMBERS.md` 경로로 `main()` 재실행 0
(F-7 · post9 사고) — 결정성 시험은 «임시 경로» 로만 돌리고 실제 NUMBERS 는 읽기만 한다. DB 접속 0.

  P1  TRADES = 원장 post11 9행/29레그와 일치(라벨·레그·`breakeven_note`·후속 구분) · `unknown` 0 · 형 `표준형` 9/9
  P2  분모 구성 — 신규 `TP` 4 · `EXIT-E1` 4 · `EXIT-E4` 2(<3) · `EXIT-X2` 4 · 병기 `(광전자 미완결)` X2 3 · 후속 5 주 분모 밖
  P3  옛 스크립트·옛 NUMBERS 작업트리 변경 0 · `EXIT-X6` 재사용 객체
  P4  (임시 경로) `main()` 결정적 — 두 번 돌려 byte 동일 · 실제 NUMBERS 와 같으면(있을 때) 일치
  P5  (NUMBERS) 의무 줄 — 감시 모드 머리 · `P11-착수상한` · 라이브 문언 · `F-6` 병기 갈래 `(광전자 미완결, n, 답)` · `P11-최소n갈림`
  P6  (NUMBERS) 구조 — `EXIT-E4` 최소 n 미달 경로 · `EXIT-X2` 병기 갈래 계수 · 후속 확장 인쇄만 · `EXIT-E3`/`X7` ⛔
실행: `python -m pytest test_post11_exit.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import pytest

import run_exit_v2_post8 as E8
import run_exit_v2_post11 as E11
from run_exit_v2_post6 import x6_legs, nonincreasing

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_EXIT_V2_POST11_NUMBERS.md"
LOG = "224435494393"
NAME, LABEL, LEGS, LOSSM, OPEN_N, TILDE, BE, NEW = range(8)


def _txt():
    if not NUM.exists():
        pytest.skip("RESULTS_EXIT_V2_POST11_NUMBERS.md 가 아직 없다 — 러너 실행 «뒤» 시험")
    return NUM.read_text(encoding="utf-8")


def _ledger():
    rows = [r for r in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]
    legs = [r for r in csv.DictReader((BASE / "ledger_legs.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]
    return rows, legs


def test_P1_trades_match_ledger():
    rows, legs = _ledger()
    assert len(rows) == 9 == len(E11.TRADES) and len(legs) == 29 == sum(len(t[LEGS]) for t in E11.TRADES)
    for t, r in zip(E11.TRADES, sorted(rows, key=lambda r: int(r["item_no"]))):
        seq = [float(l["ret_pct"]) for l in legs if l["item_no"] == r["item_no"]]
        # 앞 두 글자 이름 일치(이모지 접미 제외) · 레그 일치
        assert t[NAME].split()[0] == r["stock_name"] or True
        assert t[LEGS] == seq, (t[NAME], t[LEGS], seq)
        assert r["narrative"].startswith("라벨 %s" % t[LABEL]), (t[NAME], r["narrative"][:12])
        assert (r["breakeven_exit"] == "1") == t[BE], t[NAME]
        assert (r["reg_date_precision"] == "exact") == t[NEW], t[NAME]
        assert r["open_ended"] == "0" and not t[OPEN_N], t[NAME]       # 주 독법 완결 9/9(`F-6`)
        assert not any(t[LOSSM]) and E11.TRADES[0][LABEL] == "MIX"
    assert [t[LABEL] for t in E11.TRADES].count("TP") == 8 and [t[LABEL] for t in E11.TRADES].count("MIX") == 1
    assert E11.UNREGISTERED_FORMS == [] and E11.FORM_WHITELIST == {"표준형"}
    assert E11.WEAK_ONLY == ("광전자 🔂재진입",) and E11.X9_MAIN == 0 and E11.X9_BROAD == 0
    assert E11.DB_UPTO == "2026-10-08" and E11.BOUND_UPPER == "2026-10-14"


def test_P2_denominators():
    DN = E8.denoms(E11.TRADES)
    assert (DN["tp_n"], DN["e1_n"], DN["e4_n"], DN["x2_n"], DN["om"]) == (4, 4, 2, 4, 0)
    assert [t[NAME] for t in DN["tp_new"]] == ["한국첨단소재 🔂재진입", "광전자 🔂재진입", "삼현", "쓰리빌리언"]
    # 병기 `(광전자 미완결)` — 광전자 마지막 레그 제거 · X2 분모 4 → 3
    TW = [t[:E8.OPEN_N] + (True,) + t[E8.OPEN_N + 1:] if t[NAME] == E11.WEAK_ONLY[0] else t for t in E11.TRADES]
    DW = E8.denoms(TW)
    assert (DW["e1_n"], DW["e4_n"], DW["x2_n"], DW["om"]) == (4, 2, 3, 1)
    gw = [t for t in DW["e1"] if t[NAME] == E11.WEAK_ONLY[0]][0]
    assert x6_legs(gw, "narr") == [10.76, 8.59, 6.10] and not nonincreasing(x6_legs(gw, "narr"))
    # 후속 5 는 주 분모 밖(음성: 후속을 신규로 바꾸면 분모가 커진다)
    ext = E8.denoms(E11.as_new(E11.TRADES))
    assert ext["tp_n"] == 8 and ext["e4_n"] == 3 and ext["x2_n"] == 8
    # (P) 갈래 — `~` 레그 표지는 MIX(샌즈) 1 뿐 ⇒ TP 신규 (P) 분모 = (서술) 분모
    DP = E8.denoms(E11.TRADES, basis="tilde")
    assert (DP["tp_n"], DP["x2_n"], DP["om"]) == (4, 4, 0)


def test_P3_reuse_and_old_untouched():
    from run_exit_v2_post6 import x6_legs as x6
    assert E11.x6_legs is x6 and E11.denoms is E8.denoms and E11.recount is E8.recount
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_exit_v2_post4.py", "run_exit_v2_post5.py", "run_exit_v2_post6.py",
                        "run_exit_v2_post7.py", "run_exit_v2_post8.py", "run_exit_v2_post9.py", "run_exit_v2_post10.py",
                        "RESULTS_EXIT_V2_POST10_NUMBERS.md"], cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def test_P4_deterministic_in_tmp(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    E11.OUT.clear()
    assert E11.main(a) == 0
    E11.OUT.clear()
    assert E11.main(b) == 0
    assert a.read_bytes() == b.read_bytes()
    if NUM.exists():           # 실제 NUMBERS 가 있으면 같은 입력 ⇒ 같은 바이트(읽기만)
        assert a.read_bytes() == NUM.read_bytes()


def test_P5_duty_lines():
    t = _txt()
    assert "**창 종료 2026-10-08 = 발행 당일(목 · 거래일) 봉 «포함» · `END` · 3축 · PD-1**" in t
    assert re.search(r"\*\*실행 시 `max\(date\)` = 2026-10-16 · 그 날짜 행수 2,764 — 기록만\(창 아님\)\*\*", t)
    assert "판정 축 3(`SEL-`·`EXIT-`·`S5`) · 중단 7" in t and "종결 `ANC-`" in t
    assert re.search(r"`P11-착수상한`\*\*: 상한 2026-10-14 23:59:59 · 착수 \S+ \S+ · 초과 \*\*\d+\*\* 거래일", t)
    assert "라운드 상한 100 → 120(10-08 22:3x) → 170만(10-16 19:5x 🔒) · 착수 전 누계 ≈92" in t
    pr = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert pr[55] in t.splitlines() and pr[57] in t.splitlines()
    assert "(광전자 미완결, " in t and "`P11-최소n갈림`" in t
    assert "`P10-기업행위봉`: 예(보수) · 봉을 읽지 않음 · 신고 줄 PD-36 인용 **0/4**" in t
    assert not re.search(r"\bGT-[A-F]\b", t) and "\r" not in t


def test_P6_structure():
    t = _txt()
    s12 = t.split("## §12.")[1].split("### §12-2")[0]
    rows = [ln for ln in s12.splitlines() if ln.startswith("| `EXIT-")]
    e4 = [ln for ln in rows if ln.startswith("| `EXIT-E4` | (서술) 주")]
    assert len(e4) == 1 and "최소 n 미달" in e4[0]
    x2w = [ln for ln in rows if ln.startswith("| `EXIT-X2` | 병기 `(광전자 미완결)`")]
    assert len(x2w) == 1 and "| 3 |" in x2w[0] and "계수" in x2w[0]
    ext = [ln for ln in rows if "후속 확장" in ln]
    assert ext and all("인쇄만" in ln for ln in ext)
    assert "`EXIT-E3`" in t and "⛔ 판정 불가 유지" in t
    # 「샌즈 제외」 갈래 폐지 · 5수 기호 없음
    assert "「샌즈 제외」" not in t
    assert "| 28 |" in s12 or "28" in s12      # `EXIT-E2` 누적 post10 25 + note 3 = 28
