# -*- coding: utf-8 -*-
"""`run_s5_post11.py` 가드 시험 — 구조·상수·문형 검사. 🔴 러너 `main()` 을 부르지 않는다(F-7 · post9 사고 — 실제
`RESULTS_S5_POST11_NUMBERS.md`·`s5_post11/` 경로로 재실행 0 · DB 접속 0).

  P1  상수 = 원장 post11 (exact 4 · none 5 · prog_ver 1.0.44) · 가드 `assert_ledger_matches` 통과 + 음성
  P2  `P11-S5재진입` 기계 검사 — `assert_tail` 양성·음성(라벨 갈림 ↔ 꼬리표 · 「⛔ 판정 불가(갈림)」 금지)
  P3  `P10-S5기호` — `assert_symbol` 양성·음성
  P4  (NUMBERS) 판정 칸 구조 — 선두 기호 = 주 갈래 매핑 · 꼬리표 유무 = 제외 라벨 ≠ 주 라벨 · 제외 갈래 `(라벨, 건수, 값)`
  P5  (NUMBERS) 의무 줄 — 감시 모드 머리 · `P11-착수상한` · `max(rcept_dt)` · 단서 각주 2·2′ · 라이브 문언 · 등급 이름 0
실행: `python -m pytest test_post11_s5.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import run_s5_post8 as S8
import run_s5_post11 as S11

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_S5_POST11_NUMBERS.md"


def _txt():
    if not NUM.exists():
        pytest.skip("RESULTS_S5_POST11_NUMBERS.md 가 아직 없다 — 러너 실행 «뒤» 시험")
    return NUM.read_text(encoding="utf-8")


def test_P1_constants_and_ledger_guard():
    assert (S11.POST_LOG, S11.POST_DATE, S11.DB_UPTO, S11.PIT_CUTOFF) == ("224435494393", "2026-10-08", "2026-10-08", "2026-10-08")
    assert S11.DPLUS1_SWEEP == "2026-10-12 15:35" and S11.WIN_START == "2026-06-19" and S11.BOUND_UPPER == "2026-10-14"
    assert [n for n, _c, _d in S11.EXACT4] == ["한국첨단소재", "광전자", "삼현", "쓰리빌리언"]
    assert S11.REENTRY == {"한국첨단소재", "광전자"} and S11.APPROX == [] and len(S11.FOLLOWUP5) == 5
    assert S11.MIN_JUDGEABLE == 3 and S11.BAND_PP == 10 and S11.TAIL == "[재진입 제외 이탈]"
    rows = S11.ledger_rows()
    assert len(rows) == 9 and S11.assert_ledger_matches(rows)
    bad = [dict(r) for r in rows]                       # 음성: 등록일 한 칸을 바꾸면 가드가 걸린다
    [r for r in bad if r["stock_name"] == "한국첨단소재"][0]["reg_date"] = "2026-09-24"
    with pytest.raises(AssertionError):
        S11.assert_ledger_matches(bad)
    # 옛 판 불변
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_s5_post7.py", "run_s5_post8.py", "run_s5_post9.py",
                        "run_s5_post10.py", "RESULTS_S5_POST10_NUMBERS.md"], cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def _cell_lines(cell):
    return ["<!-- S5-VERDICT-BEGIN -->", "| §1-5 재진입 포함 ↔ 제외 | 4 ↔ 2 | **(S5-성립)** ↔ **(S5-보류)** — 제외 갈래 `(라벨, 건수, 값)` = x |",
            "- ⇒ **최종: %s**" % cell, "<!-- S5-VERDICT-END -->"]


def test_P2_tail_guard():
    ok = _cell_lines("✅ (S5-성립) [재진입 제외 이탈]")
    assert S11.assert_tail(ok, True)
    assert S11.assert_tail(_cell_lines("✅ (S5-성립)"), False)                  # 같으면 꼬리표 없음
    with pytest.raises(AssertionError):
        S11.assert_tail(_cell_lines("✅ (S5-성립)"), True)                       # 갈렸는데 꼬리표 없음
    with pytest.raises(AssertionError):
        S11.assert_tail(ok, False)                                             # 같은데 꼬리표 있음
    with pytest.raises(AssertionError):
        S11.assert_tail(_cell_lines("⛔ 판정 불가(갈림)"), False) if False else S11.assert_tail(
            _cell_lines("⛔ 판정 불가(갈림) [재진입 제외 이탈]"), True)               # 옛 문형 금지
    with pytest.raises(AssertionError):
        S11.assert_tail([ok[0], ok[2], ok[3]], True)                           # 제외 갈래 병기 줄 없음
    assert S11.assert_tail(_cell_lines("판정 미개방 — 순서 증거 미비"), True)     # 미개방은 면제


def test_P3_symbol_guard():
    assert S11.assert_symbol(_cell_lines("✅ (S5-성립) [재진입 제외 이탈]"))
    assert S11.assert_symbol(_cell_lines("❌ (S5-이탈)"))
    with pytest.raises(AssertionError):
        S11.assert_symbol(_cell_lines("❌ (S5-성립)"))                           # 라벨 ↔ 기호 어긋남
    with pytest.raises(AssertionError):
        S11.assert_symbol(_cell_lines("(S5-성립)"))                              # 기호 없음


def test_P4_verdict_cell_structure():
    t = _txt()
    cell = [ln for ln in t.splitlines() if ln.startswith("- ⇒ **최종: ")]
    assert len(cell) == 1
    c = cell[0][len("- ⇒ **최종: "):].split("**")[0].strip()
    assert S11.SPLIT_WORD not in c
    body = t.split("<!-- S5-VERDICT-BEGIN -->")[1].split("<!-- S5-VERDICT-END -->")[0]
    main_lab = re.search(r"- `exact` 갈래\(주\) 답 = \*\*(\([^)]+\)|판정 불가·모호)\*\*", body).group(1)
    row = [ln for ln in body.splitlines() if ln.startswith("| §1-5 재진입 포함 ↔ 제외")][0]
    labs = re.search(r"\*\*(\(S5-[^)]+\)|판정 불가·모호)\*\* ↔ \*\*(\(S5-[^)]+\)|판정 불가·모호)\*\*", row)
    assert labs and labs.group(1) == main_lab and "(라벨, 건수, 값)" in row
    assert (S11.TAIL in c) == (labs.group(2) != labs.group(1))
    if c[0] in "✅❌⛔":
        assert c[0] == S11.SYMBOL[main_lab]
    assert t.count("<!-- S5-VERDICT-BEGIN -->") == 1 and t.count("<!-- S5-VERDICT-END -->") == 1
    S8.assert_labels_only_in_verdict(t.splitlines())


def test_P5_duty_lines():
    t = _txt()
    assert S11.WINDOW_LINE in t and re.search(r"실행 시 `max\(date\)` = 2026-10-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", t)
    assert "판정 축 3(`SEL-`·`EXIT-`·`S5`) · 중단 7" in t and "종결 `ANC-`" in t
    assert re.search(r"`P11-착수상한`\*\*: 상한 2026-10-14 23:59:59 · 착수 \S+ \S+ · 초과 \*\*\d+\*\* 거래일", t)
    assert "라운드 상한 100 → 120(10-08 22:3x) → 170만(10-16 19:5x 🔒) · 착수 전 누계 ≈92" in t
    assert "max(rcept_dt)" in t and S11.FOOT_OK in t and S11.FOOT_OUT in t
    pr = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert S11.LIVE_BAN in t and pr[55].replace("> ", "", 1).strip() == S11.LIVE_BAN.strip() or S11.LIVE_BAN in t
    st = json.loads((BASE / "s5_post11" / "read_stamp.json").read_text(encoding="utf-8"))
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"} and f"**{st['first_read_kst']}**" in t
    assert "`P11-S5재진입`" in t and "`P11-최소n갈림`" in t
    body = t.replace(S11.FOOT_OUT, "")
    assert not re.search(r"\bGT-[A-F]\b", body) and "\r" not in t
    assert "| 기업행위 건 제외(`F-3` · **답(참고) · 세지 않는다**)" in t
