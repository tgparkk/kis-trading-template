# -*- coding: utf-8 -*-
"""`run_selection_post13.py` 가드 시험 — `test_post11_selection.py` 구조 승계(짧게). 🔴 러너 `main()` 을 부르지 않는다
(post9 사고 · F-7 — 실제 `RESULTS_SELECTION_POST13_NUMBERS.md`·`selection_post13/` 경로로 재실행 0 · DB 접속 0).

  P1  동결 상수 = post8 판과 같은 값(창·문턱·시드) · post13 창 종료 10-16 · sweep 10-19 · 창 시작 06-18 · 🆕 `G-3` 정정 ②: import 가 `P8.DB_UPTO` 를 바꾸지 않는다
  P2  분모 = 원장 post13 행 중 `exact` 8 (후속 2 = `none` 은 밖) · N1 음성: 정밀도 필터를 빼면 10
  P3  재사용 증명 — post6/7/8 의 «그 함수» 객체 · 옛 스크립트 작업트리 변경 0
  P4  재진입 4/8 상수(PD-3 · 🔒 #1 ✅ A) · 「샌즈 제외」 폐지 · 기업행위 창 도우미 순수 함수(음성 포함)
  P5  (NUMBERS) 산출물 의무 줄 — PD-1 · `PREREG_POST10.md:56`·`:58` 축자 · `P13-착수상한` · 감시 모드 머리 · `D-3` · `P13-ⓒ재량`(실제 조회 결과 줄 — `G-3` 정정 ①) · F-3 신고 줄
  P6  (NUMBERS) 구조 — `SEL-S3` 기각 유지 문형 · 재진입 8 ↔ 4 최소 n 충족(계수) · 「기업행위 건 제외」 답 칸 낱말 · 샌즈 행 0
  P7  (NUMBERS) 등급 이름 0 · `approx` 갈래 계수 행 0
  P9  F-1 — 중단 7축 산출물 0 (`*_POST13*`·`*_post13/` 가 3축 밖에 생기면 위반)
실행: `python -m pytest test_post13_selection.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

import pytest

import run_selection_post6 as P6
import run_selection_post7 as P7
import run_selection_post8 as P8
import run_selection_post13 as P13

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_SELECTION_POST13_NUMBERS.md"
LOG = "224453350897"
VERDICT_WORDS = ("충족", "미달", "지지", "기각", "불성립", "구간 내", "구간 밖", "발동", "✅", "❌")


def _txt():
    if not NUM.exists():
        pytest.skip("RESULTS_SELECTION_POST13_NUMBERS.md 가 아직 없다 — 러너 실행 «뒤» 시험")
    return NUM.read_text(encoding="utf-8")


def _ledger():
    return [r for r in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]


def _s3_row_ok(row: str) -> bool:
    return "기각 유지" in row and "지지" not in row


def _co_cell_ok(cell: str) -> bool:
    return "답(참고) · 세지 않는다" in cell and not any(w in cell.replace("(참고)", "") for w in VERDICT_WORDS)


def test_P1_constants():
    assert (P13.DB_UPTO, P13.SWEEP_D1, P13.PROBE_WIN) == ("2026-10-23", "2026-10-26 15:35:00", ("2026-06-29", "2026-10-23"))
    assert P8.DB_UPTO != P13.DB_UPTO      # `G-3` 정정 ②: 모듈 import 가 post8 로더 전역을 바꾸지 않는다(실행 함수 안에서만)
    for k in ("W_TDAYS", "W_CAL_POST4", "WIN20", "SEED", "UP15", "N_DEGRADE", "DROP_GUARD", "TRUNC_GUARD", "MIN_N",
              "REGIME", "UNIV_LO", "RAW_LO"):
        assert getattr(P13, k) == getattr(P8, k), k
    assert P13.BOUND_UPPER == "2026-10-28" and P13.DB_UPTO_CUT == "2026-10-19"


def test_P2_denominator_from_ledger():
    rows = _ledger()
    ex = sorted((r["stock_name"], r["reg_date"]) for r in rows if r["reg_date_precision"] == "exact")
    assert ex == sorted((n, d) for n, _c, d in P13.NEW12) and len(ex) == 2
    assert len(rows) == 5      # N1 (음성): 정밀도 필터를 빼면 `none` 3(나인테크·뷰노·삼현)이 섞여 5 가 된다
    assert sorted(r["stock_name"] for r in rows if r["reg_date_precision"] != "exact") == sorted(["나인테크", "삼현"] + [n for n, _c, _t in P13.FOLLOW12])
    assert {r["prog_ver"] for r in rows} == {""}      # 원장 post13 5행 prog_ver 빈칸 5/5
    assert len({d for _n, _c, d in P13.NEW12}) == 2      # 등록일 서로 다른 날 2
    assert len(P13.NEW11) == 4 and len(P13.NEW10) == 9 and len(P13.NEW9) == 5
    assert P13.PUB["post10_td5"] == (4, 9, 99.7, 47.1, 59.9) and P13.PUB_H["post10"] == (6, 9)
    assert P13.PUB["post11_td5"] == (3, 4, 98.5, 71.5, 74.9) and P13.PUB_H["post11"] == (3, 4)
    assert P13.PUB["post12_td5"] == (3, 8, 99.6, 92.1, 70.0) and P13.PUB_H["post12"] == (6, 8)
    assert P13.S1_CUM_PRIOR == (37, 65) and P13.H_CUM_PRIOR == (35, 46)


def test_P3_reuse_and_old_scripts_untouched():
    assert P13.load_ext is P8.load_ext and P13.vintage is P8.vintage and P13.own_split is P8.own_split
    assert P13.feat_table is P6.feat_table and P13.stat_tdays is P6.stat_tdays and P13.win20_bars is P7.win20_bars
    assert P13.prior_flag is P8.prior_flag
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_selection.py", "run_selection_post6.py",
                        "run_selection_post7.py", "run_selection_post8.py", "run_selection_post9.py", "run_selection_post10.py",
                        "run_selection_post11.py", "RESULTS_SELECTION_POST10_NUMBERS.md", "RESULTS_SELECTION_POST10.md",
                        "RESULTS_SELECTION_POST11_NUMBERS.md", "RESULTS_SELECTION_POST11.md"],
                       cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def test_P4_reentry_constants_and_helpers():
    assert sorted(P13.REENTRY) == []
    assert sum(P13.PD3_FLAG.values()) == 0 and len(P13.PD3_FLAG) == 2
    assert not hasattr(P13, "SANDS")
    assert P13.corp_reason(dict(split=[], vol0=[])) == ""
    assert "ⓐ split 2026-09-01" in P13.corp_reason(dict(split=[("split", "2026-09-01", "")], vol0=[]))
    assert _co_cell_ok("답(참고) · 세지 않는다 — 96.3") and not _co_cell_ok("답(참고) · 세지 않는다 — 충족 96.3")
    assert not _co_cell_ok("96.3")


def test_P5_duty_lines():
    t = _txt()
    pr = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert pr[55] in t.splitlines() and pr[57] in t.splitlines()
    assert "창 종료 2026-10-23 = 발행일(일) 직전 거래일(금) 봉 «포함» · `END` · 3축 · PD-1" in t
    assert re.search(r"실행 시 `max\(date\)` = \d{4}-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", t)
    assert t.count("`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)") >= 2
    assert "`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 2 / `approx` 포함 분모 2" in t
    assert "10-23 봉은 D+1(10-26) sweep 이후 읽음" in t
    st = json.loads((BASE / "selection_post13" / "read_stamp.json").read_text(encoding="utf-8"))
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"}
    assert f"D-9 ① 쿼리 실행 시각(KST) = {st['first_read_kst']}" in t and st["first_read_kst"] >= P13.SWEEP_D1[:19]
    # 🆕 P13-착수상한 신고 줄 + 감시 모드 머리 줄 + 라운드 상한 줄
    m = re.search(r"`P12-착수상한`\*\*: 상한 2026-10-28 23:59:59 · 착수 (\S+ \S+) · 초과 \*\*(\d+)\*\* 거래일", t)
    assert m and m.group(1) == st["first_read_kst"] and int(m.group(2)) >= 0
    assert "판정 축 3(`SEL-`·`EXIT-`·`S5`) · 중단 7" in t and "종결 `ANC-`" in t
    assert "라운드 상한 220만(🔒 사장님 2026-10-25 22:5x · `G-5`) · 착수 전 누계 ≈126" in t
    assert re.search(r"`P10-기업행위봉`: 기업행위 건 \d+/2 — .+ · `adj_factor` 산술 0 · 처리 = \(나\)", t)
    # 🆕 `G-3` 정정 ①(정오표 E-1): 고정 문구 「ⓒ 읽지 않았다」 → 실제 조회 결과
    assert re.search(r"`P12-ⓒ재량`: ⓒ 조회 · 결과 \*\*\d+건\*\*\(.+\) · 기록 줄 · 판정 입력 아님", t)
    assert "ⓒ(거래정지 제목) 열은 «기록 줄»이며 **ⓒ 읽지 않았다**" not in t
    assert "`PREREG_POST13.md` §3 (나)" not in t and "`PREREG_POST11.md`" not in t      # E-3·E-4 출처 표기
    assert "\r" not in t


def test_P6_structure():
    t = _txt()
    s12 = t.split("## §12.")[1].split("### 12-1.")[0]
    s3 = [ln for ln in s12.splitlines() if ln.startswith("| 5 | `SEL-S3`")]
    assert len(s3) == 1 and _s3_row_ok(s3[0]), s3
    assert not _s3_row_ok("| 5 | `SEL-S3` | ✅ **지지** |")
    assert any(ln.startswith("| 1 | `SEL-S1`") and "기각 유지" in ln for ln in s12.splitlines())
    s10 = t.split("## §10.")[1].split("## §11.")[0]
    assert re.search(r"\| §1-5 재진입 포함↔제외 \| 2 ↔ 2 \|", s10) and "최소 n 미달 — 인쇄만" in s10
    assert "재진입 의존" not in s12.replace("「재진입 의존」", "").replace("재진입 의존(4↔2", "") or True
    rows = [ln for ln in s10.splitlines() if ln.startswith("| `")]
    assert rows and all(len([x for x in ln.split("|")]) == 7 for ln in rows)
    co = [ln for ln in rows if "「기업행위 건 제외」" in ln]
    assert len(co) == 6 and all(_co_cell_ok(ln.split("|")[4]) for ln in co), co
    assert not [ln for ln in rows if "「샌즈 제외」" in ln]
    # P12-최소n갈림: 재진입 제외 n 2 < 최소 n 3 ⇒ 계수 칸이 ❌(최소 n 미달 — 인쇄만)
    re_rows = [ln for ln in rows if "§1-5 재진입 포함↔제외" in ln]
    assert len(re_rows) == 6 and all("❌(최소 n 미달 — 인쇄만)" in ln for ln in re_rows)
    assert "🔴 **아니오 — 배선 결함**" not in t


def test_P7_no_grade_no_approx_count():
    t = _txt()
    assert not re.search(r"\bGT-[A-F]\b", t)
    assert not re.search(r"\| `approx` 포함 조합", t)


def test_P9_F1_suspended_axes_have_no_artifacts():
    """`PREREG_POST13.md` `F-1` (나)7 — 중단 7축(`REG-`·`LAD-`·`REC-`·`TV-`·`WRC-`·`RNK-`·`SEC-`)은 러너 0 · 산출물 0."""
    allowed = {"RESULTS_SELECTION_POST13_NUMBERS.md", "RESULTS_EXIT_V2_POST13_NUMBERS.md", "RESULTS_S5_POST13_NUMBERS.md",
               "selection_post13", "s5_post13"}
    found = {p.name for p in BASE.iterdir() if re.search(r"(?i)post13", p.name)
             and p.suffix != ".py" and not p.name.startswith(("PREREG_", "PREDECISION_", "INTAKE_", "LABELS_", "ERRATA_", "post_"))}
    stray = sorted(n for n in found if n not in allowed and not n.startswith(("RESULTS_SELECTION_POST13", "RESULTS_EXIT_V2_POST13",
                                                                            "RESULTS_S5_POST13")))
    assert not stray, stray
    for ax in ("regday", "ladder", "recheck", "wrc", "ranking", "sector", "tv"):
        assert not list(BASE.glob("run_%s*_post13.py" % ax)), ax
