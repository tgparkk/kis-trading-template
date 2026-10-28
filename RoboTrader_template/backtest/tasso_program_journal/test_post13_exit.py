# -*- coding: utf-8 -*-
"""`run_exit_v2_post13.py` 가드 시험 — 구조·상수·문형 검사. 🔴 실제 `RESULTS_EXIT_V2_POST13_NUMBERS.md` 경로로 `main()` 재실행 0
(F-7 · post9 사고) — 결정성 시험은 «임시 경로» 로만 돌리고 실제 NUMBERS 는 읽기만 한다. DB 접속 0.

  P1  TRADES = 원장 post13 10행/33레그와 일치(라벨·레그·「손실률」 마스크·`breakeven_note`·후속 구분·`open_ended`) · `unknown` 0 · 형 `표준형` 10/10
  P2  분모 구성 — 신규 `TP` 5 · `EXIT-E1` 5 · `EXIT-E4` 3 · `EXIT-X2` 5 · 병기 `(약한 자리 미완결 독법)` X2 2 · 후속 2 주 분모 밖 · `MANUAL` 2 · `SL` 1 분모 밖
  P3  옛 스크립트·옛 NUMBERS 작업트리 변경 0 · `EXIT-X6` 재사용 객체
  P4  (임시 경로) `main()` 결정적 — 두 번 돌려 byte 동일 · 실제 NUMBERS 와 같으면(있을 때) 일치
  P5  (NUMBERS) 의무 줄 — 감시 모드 머리 · `P12-착수상한` · 라이브 문언 · `F-6` 병기 갈래 · `P12-최소n갈림` · 🆕 `G-3` 정정 ①(E-6 표 안 병기 행 · E-9 최소 하락 간격 동률)
  P6  (NUMBERS) 구조 — `EXIT-E4` 주 갈래 계수 · 병기 인쇄만 · `EXIT-X2` 병기 갈래 · 후속 확장 인쇄만 · `EXIT-E3`/`X7` ⛔
실행: `python -m pytest test_post13_exit.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import pytest

import run_exit_v2_post8 as E8
import run_exit_v2_post13 as E13
from run_exit_v2_post6 import x6_legs, nonincreasing

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_EXIT_V2_POST13_NUMBERS.md"
LOG = "224453350897"
NAME, LABEL, LEGS, LOSSM, OPEN_N, TILDE, BE, NEW = range(8)


def _txt():
    if not NUM.exists():
        pytest.skip("RESULTS_EXIT_V2_POST13_NUMBERS.md 가 아직 없다 — 러너 실행 «뒤» 시험")
    return NUM.read_text(encoding="utf-8")


def _ledger():
    rows = [r for r in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]
    legs = [r for r in csv.DictReader((BASE / "ledger_legs.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]
    return rows, legs


def test_P1_trades_match_ledger():
    rows, legs = _ledger()
    assert len(rows) == 5 == len(E13.TRADES) and len(legs) == 19 == sum(len(t[LEGS]) for t in E13.TRADES)
    for t, r in zip(E13.TRADES, sorted(rows, key=lambda r: int(r["item_no"]))):
        ls = [l for l in legs if l["item_no"] == r["item_no"]]
        assert t[NAME].split()[0] == r["stock_name"], (t[NAME], r["stock_name"])
        assert t[LEGS] == [float(l["ret_pct"]) for l in ls], t[NAME]
        assert t[LOSSM] == [int(l["is_loss"]) for l in ls], t[NAME]
        assert r["narrative"].startswith("라벨 %s" % t[LABEL]), (t[NAME], r["narrative"][:12])
        assert (r["breakeven_exit"] == "1") == t[BE], t[NAME]
        assert (r["reg_date_precision"] == "exact" or t[NAME] in {"나인테크 🔂재진입", "삼현 🔂재진입"}) == t[NEW], t[NAME]      # 재진입 신규 none 2(나인테크·삼현)는 EXIT 축에서 신규
        assert (r["open_ended"] == "1") == t[OPEN_N], t[NAME]            # 서술 미완결 = 뷰노 1(「진행중」)
    labs = [t[LABEL] for t in E13.TRADES]
    assert labs.count("TP") == 2 and labs.count("MANUAL") == 2 and labs.count("SL") == 1 and labs.count("MIX") == 0
    assert E13.UNREGISTERED_FORMS == [] and E13.FORM_WHITELIST == {"표준형"}
    assert E13.WEAK_ONLY == ("나인테크 🔂재진입",) and (E13.X9_MAIN, E13.X9_BROAD) == (0, 2)
    assert E13.DB_UPTO == "2026-10-23" and E13.BOUND_UPPER == "2026-10-28"
    assert {t[NAME] for t in E13.TRADES if not t[NEW]} == {"뷰노 🔁후속"}


def test_P2_denominators():
    DN = E8.denoms(E13.TRADES)
    assert (DN["tp_n"], DN["e1_n"], DN["e4_n"], DN["x2_n"], DN["om"]) == (2, 2, 1, 2, 0)
    assert [t[NAME] for t in DN["tp_new"]] == ["나인테크 🔂재진입", "삼현 🔂재진입"]
    # 병기 `(약한 자리 미완결 독법)` — 세미파이브·나인테크·우리로 마지막 레그 제거 · X2 분모 5 → 2
    TW = [t[:E8.OPEN_N] + (True,) + t[E8.OPEN_N + 1:] if t[NAME] in E13.WEAK_ONLY else t for t in E13.TRADES]
    DW = E8.denoms(TW)
    assert (DW["e1_n"], DW["e4_n"], DW["x2_n"], DW["om"]) == (2, 1, 1, 1)
    gw = [t for t in DW["e1"] if t[NAME] == "나인테크 🔂재진입"][0]
    assert x6_legs(gw, "narr") == [15.3, 11.6, 10.64, 10.63, 10.23] and not nonincreasing(x6_legs(gw, "narr"))
    # 후속 2 는 주 분모 밖(음성: 후속을 신규로 바꾸면 분모가 커진다) · MANUAL·SL 은 TP 분모에 안 들어간다
    ext = E8.denoms(E13.as_new(E13.TRADES))
    assert ext["tp_n"] == 2 and ext["e4_n"] == 1 and ext["x2_n"] == 2
    # (P) 갈래 — `~` 레그 표지 = 나인테크 1 ⇒ (P) X2 분모 1 · om 1
    DP = E8.denoms(E13.TRADES, basis="tilde")
    assert (DP["tp_n"], DP["x2_n"], DP["om"]) == (2, 1, 1)


def test_P3_reuse_and_old_untouched():
    from run_exit_v2_post6 import x6_legs as x6
    assert E13.x6_legs is x6 and E13.denoms is E8.denoms and E13.recount is E8.recount
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_exit_v2_post4.py", "run_exit_v2_post5.py", "run_exit_v2_post6.py",
                        "run_exit_v2_post7.py", "run_exit_v2_post8.py", "run_exit_v2_post9.py", "run_exit_v2_post10.py",
                        "run_exit_v2_post11.py", "RESULTS_EXIT_V2_POST10_NUMBERS.md", "RESULTS_EXIT_V2_POST11_NUMBERS.md"],
                       cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def test_P4_deterministic_in_tmp(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    E13.OUT.clear()
    assert E13.main(a) == 0
    E13.OUT.clear()
    assert E13.main(b) == 0
    assert a.read_bytes() == b.read_bytes()
    if NUM.exists():           # 실제 NUMBERS 가 있으면 같은 입력 ⇒ 같은 바이트(읽기만)
        assert a.read_bytes() == NUM.read_bytes()


def test_P5_duty_lines():
    t = _txt()
    assert "**창 종료 2026-10-23 = 발행일(토) 직전 거래일(금) 봉 «포함» · `END` · 3축 · PD-1**" in t
    assert re.search(r"\*\*실행 시 `max\(date\)` = 2026-10-27 · 그 날짜 행수 2,766 — 기록만\(창 아님\)\*\*", t)
    assert "판정 축 3(`SEL-`·`EXIT-`·`S5`) · 중단 7" in t and "종결 `ANC-`" in t
    assert re.search(r"`P12-착수상한`\*\*: 상한 2026-10-28 23:59:59 · 착수 \S+ \S+ · 초과 \*\*\d+\*\* 거래일", t)
    assert "라운드 상한 220만(🔒 사장님 2026-10-25 22:5x · `G-5`) · 착수 전 누계 ≈126" in t
    pr = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert pr[55] in t.splitlines() and pr[57] in t.splitlines()
    assert "(약한 자리 미완결 독법, " in t and "`P12-최소n갈림`" in t
    assert "`P10-기업행위봉`: 예(보수) · 봉을 읽지 않음 · 신고 줄 PD-36 인용 **0/4**" in t
    assert not re.search(r"\bGT-[A-F]\b", t) and "\r" not in t
    assert "[[PREREG_POST11]]" not in t and "[[LABELS_2026-10-08_post11]]" not in t
    # 🆕 `G-3` 정정 ① — E-9: 최소 하락 간격은 «동률 전부» · E-6: 병기 행이 표 «안»
    assert re.search(r"\*\*최소 하락 간격 = \d+\.\d\d%p — .+ → .+\*\*", t)
    ls = t.splitlines()
    i = next(k for k, ln in enumerate(ls) if ln.startswith("| 후속 확장 (P) |"))
    assert ls[i + 1].startswith("| 🆕 병기 `(약한 자리 미완결 독법)`(`F-6`)") and ls[i + 2] == ""


def test_P6_structure():
    t = _txt()
    s12 = t.split("## §12.")[1].split("### §12-2")[0]
    rows = [ln for ln in s12.splitlines() if ln.startswith("| `EXIT-")]
    e4 = [ln for ln in rows if ln.startswith("| `EXIT-E4` | (서술) 주")]
    assert len(e4) == 1 and "| 1 |" in e4[0] and "최소 n 미달" in e4[0] and "계수" in e4[0]
    e4w = [ln for ln in rows if ln.startswith("| `EXIT-E4` | 병기 `(약한 자리 미완결 독법)`")]
    assert len(e4w) == 1 and "| 1 |" in e4w[0] and "최소 n 미달" in e4w[0]
    x2w = [ln for ln in rows if ln.startswith("| `EXIT-X2` | 병기 `(약한 자리 미완결 독법)`")]
    assert len(x2w) == 1 and "| 1 |" in x2w[0] and "최소 n 미달" in x2w[0]
    x2 = [ln for ln in rows if ln.startswith("| `EXIT-X2` | (서술) 주")]
    assert len(x2) == 1 and "| 2 |" in x2[0]
    ext = [ln for ln in rows if "후속 확장" in ln]
    assert ext and all("인쇄만" in ln for ln in ext)
    assert "`EXIT-E3`" in t and "⛔ 판정 불가 유지" in t
    assert "「샌즈 제외」" not in t
    assert "| 30 |" in s12      # `EXIT-E2` 누적 (가) 31 · 확인 7 제외 30
