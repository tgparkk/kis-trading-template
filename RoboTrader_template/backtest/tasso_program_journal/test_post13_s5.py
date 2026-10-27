# -*- coding: utf-8 -*-
"""`run_s5_post13.py` 가드 시험 — 구조·상수·문형 검사. 🔴 러너 `main()` 을 부르지 않는다(F-7 · post9 사고 — 실제
`RESULTS_S5_POST13_NUMBERS.md`·`s5_post13/` 경로로 재실행 0 · DB 접속 0).

  P1  상수 = 원장 post13 (exact 8 · none 2 · prog_ver 1.0.45) · 🆕 PIT 절단일 10-16 ≠ 글 게시일 10-17 · 정오표 E-7 `:58` 줄 상수 · 가드 `assert_ledger_matches` 통과 + 음성
  P2  `P12-S5재진입` 기계 검사 — `assert_tail` 양성·음성(라벨 갈림 ↔ 꼬리표 · 「⛔ 판정 불가(갈림)」 금지)
  P3  `P10-S5기호` — `assert_symbol` 양성·음성
  P4  (NUMBERS) 판정 칸 구조 — 선두 기호 = 주 갈래 매핑 · 꼬리표 유무 = 제외 라벨 ≠ 주 라벨 · 제외 갈래 `(라벨, 건수, 값)`
  P5  (NUMBERS) 의무 줄 — 감시 모드 머리 · `P12-착수상한` · 🆕 `G-3` 정정 ①(E-7 `:58` 축자 줄 · E-8 「PIT 행 0개」 단위 · E-3·E-4 출처) · `max(rcept_dt)` · 단서 각주 2·2′ · 라이브 문언 · 등급 이름 0
실행: `python -m pytest test_post13_s5.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import run_s5_post8 as S8
import run_s5_post13 as S13

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_S5_POST13_NUMBERS.md"


def _txt():
    if not NUM.exists():
        pytest.skip("RESULTS_S5_POST13_NUMBERS.md 가 아직 없다 — 러너 실행 «뒤» 시험")
    return NUM.read_text(encoding="utf-8")


def test_P1_constants_and_ledger_guard():
    assert (S13.POST_LOG, S13.POST_DATE, S13.DB_UPTO, S13.PIT_CUTOFF) == ("224453350897", "2026-10-25", "2026-10-23", "2026-10-23")
    assert S13.DPLUS1_SWEEP == "2026-10-26 15:35" and S13.WIN_START == "2026-06-29" and S13.BOUND_UPPER == "2026-10-28"
    assert [n for n, _c, _d in S13.EXACT8] == ["코리아써키트", "에코앤드림"]
    assert S13.REENTRY == set() and S13.APPROX == [] and len(S13.FOLLOWUP2) == 3
    assert S13.LIVE_58.startswith("⇒ `PREREG_POST8.md:26`")          # 정오표 E-7 — `PREREG_POST10.md:58` 축자 줄
    assert S13.MIN_JUDGEABLE == 3 and S13.BAND_PP == 10 and S13.TAIL == "[재진입 제외 이탈]"
    rows = S13.ledger_rows()
    assert len(rows) == 5 and S13.assert_ledger_matches(rows)
    bad = [dict(r) for r in rows]                       # 음성: 등록일 한 칸을 바꾸면 가드가 걸린다
    [r for r in bad if r["stock_name"] == "에코앤드림"][0]["reg_date"] = "2026-10-02"
    with pytest.raises(AssertionError):
        S13.assert_ledger_matches(bad)
    # 옛 판 불변
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_s5_post7.py", "run_s5_post8.py", "run_s5_post9.py",
                        "run_s5_post10.py", "run_s5_post11.py", "RESULTS_S5_POST10_NUMBERS.md", "RESULTS_S5_POST11_NUMBERS.md"], cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def _cell_lines(cell):
    return ["<!-- S5-VERDICT-BEGIN -->", "| §1-5 재진입 포함 ↔ 제외 | 4 ↔ 2 | **(S5-성립)** ↔ **(S5-보류)** — 제외 갈래 `(라벨, 건수, 값)` = x |",
            "- ⇒ **최종: %s**" % cell, "<!-- S5-VERDICT-END -->"]


def test_P2_tail_guard():
    ok = _cell_lines("✅ (S5-성립) [재진입 제외 이탈]")
    assert S13.assert_tail(ok, True)
    assert S13.assert_tail(_cell_lines("✅ (S5-성립)"), False)                  # 같으면 꼬리표 없음
    with pytest.raises(AssertionError):
        S13.assert_tail(_cell_lines("✅ (S5-성립)"), True)                       # 갈렸는데 꼬리표 없음
    with pytest.raises(AssertionError):
        S13.assert_tail(ok, False)                                             # 같은데 꼬리표 있음
    with pytest.raises(AssertionError):
        S13.assert_tail(_cell_lines("⛔ 판정 불가(갈림)"), False) if False else S13.assert_tail(
            _cell_lines("⛔ 판정 불가(갈림) [재진입 제외 이탈]"), True)               # 옛 문형 금지
    with pytest.raises(AssertionError):
        S13.assert_tail([ok[0], ok[2], ok[3]], True)                           # 제외 갈래 병기 줄 없음
    assert S13.assert_tail(_cell_lines("판정 미개방 — 순서 증거 미비"), True)     # 미개방은 면제


def test_P3_symbol_guard():
    assert S13.assert_symbol(_cell_lines("✅ (S5-성립) [재진입 제외 이탈]"))
    assert S13.assert_symbol(_cell_lines("❌ (S5-이탈)"))
    with pytest.raises(AssertionError):
        S13.assert_symbol(_cell_lines("❌ (S5-성립)"))                           # 라벨 ↔ 기호 어긋남
    with pytest.raises(AssertionError):
        S13.assert_symbol(_cell_lines("(S5-성립)"))                              # 기호 없음


def test_P4_verdict_cell_structure():
    t = _txt()
    cell = [ln for ln in t.splitlines() if ln.startswith("- ⇒ **최종: ")]
    assert len(cell) == 1
    c = cell[0][len("- ⇒ **최종: "):].split("**")[0].strip()
    assert S13.SPLIT_WORD not in c
    body = t.split("<!-- S5-VERDICT-BEGIN -->")[1].split("<!-- S5-VERDICT-END -->")[0]
    main_lab = re.search(r"- `exact` 갈래\(주\) 답 = \*\*(\([^)]+\)|판정 불가·모호)\*\*", body).group(1)
    row = [ln for ln in body.splitlines() if ln.startswith("| §1-5 재진입 포함 ↔ 제외")][0]
    labs = re.search(r"\*\*(\(S5-[^)]+\)|판정 불가·모호)\*\* ↔ \*\*(\(S5-[^)]+\)|판정 불가·모호)\*\*", row)
    assert labs and labs.group(1) == main_lab and "(라벨, 건수, 값)" in row
    assert (S13.TAIL in c) == (labs.group(2) != labs.group(1))
    if c[0] in "✅❌⛔":
        assert c[0] == S13.SYMBOL[main_lab]
    assert t.count("<!-- S5-VERDICT-BEGIN -->") == 1 and t.count("<!-- S5-VERDICT-END -->") == 1
    S8.assert_labels_only_in_verdict(t.splitlines())


def test_P5_duty_lines():
    t = _txt()
    assert S13.WINDOW_LINE in t and re.search(r"실행 시 `max\(date\)` = 2026-10-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", t)
    assert "판정 축 3(`SEL-`·`EXIT-`·`S5`) · 중단 7" in t and "종결 `ANC-`" in t
    assert re.search(r"`P12-착수상한`\*\*: 상한 2026-10-28 23:59:59 · 착수 \S+ \S+ · 초과 \*\*\d+\*\* 거래일", t)
    assert "라운드 상한 220만(🔒 사장님 2026-10-25 22:5x · `G-5`) · 착수 전 누계 ≈126" in t
    assert "max(rcept_dt)" in t and S13.FOOT_OK in t and S13.FOOT_OUT in t
    pr = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert S13.LIVE_BAN in t and pr[55].replace("> ", "", 1).strip() == S13.LIVE_BAN.strip() or S13.LIVE_BAN in t
    st = json.loads((BASE / "s5_post13" / "read_stamp.json").read_text(encoding="utf-8"))
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"} and f"**{st['first_read_kst']}**" in t
    assert "`P12-S5재진입`" in t and "`P12-최소n갈림`" in t
    # 🆕 `G-3` 정정 ① — E-7: `PREREG_POST10.md:58` 축자 줄이 산출물에 있다 · E-8: 「PIT 행 0개」 단위 명시 · E-3·E-4: 출처 표기
    assert pr[57] in t.splitlines() and S13.LIVE_58 == pr[57]
    assert re.search(r"① PIT 행 0개 고유 종목 \d+ · ② 행은 있는데 `operating_income` NULL 고유 종목 \d+", t) and "종목-일 단위로는 Σ(상위 1% − 측정 가능) = **" in t
    assert "`PREREG_POST10.md` `F-3`" in t and "`P11-" not in t
    body = t.replace(S13.FOOT_OUT, "")
    assert not re.search(r"\bGT-[A-F]\b", body) and "\r" not in t
    assert "| 기업행위 건 제외(`PREREG_POST10.md` `F-3` · **답(참고) · 세지 않는다**)" in t
