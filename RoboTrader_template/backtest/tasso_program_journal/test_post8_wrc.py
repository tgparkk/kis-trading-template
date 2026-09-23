# -*- coding: utf-8 -*-
"""`WRC-` 축 post8 판정 회차의 **가드 테스트** — DB 없이 도는 것만 담는다.

post7 판에는 `test_post7_wrc.py` 가 «없었다»(post6 판 `test_post6_wrc.py` 규약을 승계한다). 지키는 것:
  1. **상수** — `CODES8` ↔ `INTAKE_2026-09-18_post8.md` §1 표 축자 · 창 종료 `2026-09-18`(PD-1).
  2. **분모 정의** — 원장 재측정 = 인테이크 «계산 전» 구성 · post8 «단독» 0(`fill_n = 1` 구성) ·
     누적 = post6 5(인테이크 post6 예측과 같은 이름) + post7 0 + post8 0.
  3. **`PREREG_POST8.md` 의무 줄** — `D-4` 세 수 «같은 행» · `D-3` 신고 줄 · `D-5` 갈래표 · `D-8` 수준 목록 ·
     `D-9` ①~⑤ · 라이브 채택 금지 · 등급 이름 0.
  4. **post7 이하 회귀** — `run_wrc_post7.py`·`run_wrc_post6.py`·`run_wrc_explore.py` 와 그 산출물이 `154b80c`(post8 이전) 블롭과
     **내용 동일**(이 회차가 한 글자도 안 바꿨다).

🔴 DB 접속·라이브 import 0건. `python -m pytest test_post8_wrc.py -q -p no:cacheprovider` 로 돈다.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import run_wrc_explore as W
import run_wrc_post6 as P6
import run_wrc_post7 as P7
import run_wrc_post8 as P8

BASE = Path(__file__).resolve().parent
INTAKE = "INTAKE_2026-09-18_post8.md"
NUMBERS = BASE / "RESULTS_WRC_POST8_NUMBERS.md"
BASE_REF = "154b80c"   # 🔴 정정 1차(C-1) — post8 산출 «이전» 마지막 커밋(HEAD 는 post8 WIP 뒤라 검사력 0)
CODE_RE = re.compile(r"[0-9][0-9A-Z]{5}")


def _numbers() -> str:
    return NUMBERS.read_text(encoding="utf-8")


def _cases():
    tr, legs = W.read_ledger()
    return W.build_cases(tr, legs)


def _intake_table() -> dict:
    out = {}
    for ln in (BASE / INTAKE).read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in ln.split("|")]
        if len(c) >= 5 and c[1].isdigit():
            m = CODE_RE.search(c[3] or "")
            if m:
                out[c[2]] = m.group(0)
    return out


def _head_blob(rel: str) -> bytes:
    r = subprocess.run(["git", "show", f"{BASE_REF}:./{rel}"], cwd=str(BASE), capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout


# ── 1. 상수 ──────────────────────────────────────────────────────────────────
def test_codes_match_intake_table_verbatim():
    tbl = _intake_table()
    assert len(P8.CODES8) == 10
    assert {k: tbl.get(k) for k in P8.CODES8} == P8.CODES8
    assert P8.CODES8["액스비스"] == "0011A0" and P8.CODES8["우리기술"] == "032820"


def test_window_constants_are_pd1():
    assert P8.POST8_LOG == "224416253270"
    assert P8.POST8_DATE == "2026-09-18" and P8.DB_UPTO == "2026-09-18"
    assert P8.WINDOW_END["post6"] == "2026-09-04" and P8.WINDOW_END["post7"] == "2026-09-11"
    assert P8.WINDOW_END["post4"] == P8.WINDOW_END["post5"] == "2026-09-02"   # FREEZE_WRC §2
    assert len(P8.APPROX_DAYS) == 7 and P8.APPROX_DAYS[0] == "2026-08-21" and P8.APPROX_DAYS[-1] == "2026-08-31"


def test_thresholds_are_imported_not_redefined():
    assert (P8.BAND_THR, P8.G1_THR, P8.N_THR, P8.SEED, P8.NREP, P8.THR) == \
           (W.BAND_THR, W.G1_THR, W.N_THR, W.SEED, W.NREP, W.THR)


# ── 2. 분모 ──────────────────────────────────────────────────────────────────
def test_ledger_matches_intake_rows():
    p8 = [c for c in _cases() if c["log_no"] == P8.POST8_LOG]
    got = sorted((c["name"], c["prec"], c["fill_n"], c["distinct"]) for c in p8)
    want = sorted((nm, prec, fn, len(set(lg))) for nm, prec, fn, lg in P8.INTAKE_ROWS8)
    assert got == want and len(p8) == 10


def test_solo_denominator_is_zero_by_fill_n():
    p8 = [c for c in _cases() if c["log_no"] == P8.POST8_LOG]
    exact = [c for c in p8 if c["prec"] == "exact"]
    assert sorted(c["name"] for c in exact) == sorted(["우리로", "JW신약", "액스비스", "우리기술"])
    assert all(c["fill_n"] == 1 for c in exact)
    assert not [c for c in p8 if c["gate"]]
    # 🔴 우리로가 빠지는 사유는 `fill_n = 1` 이다 — 서로 다른 값 레그는 7 로 조건을 채운다
    ur = next(c for c in p8 if c["name"] == "우리로")
    assert ur["distinct"] == 7 and ur["fill_n"] == 1


def test_approx_branch_is_codez_only():
    p8 = [c for c in _cases() if c["log_no"] == P8.POST8_LOG]
    assert [c["name"] for c in P7.approx_branch(p8)] == ["코데즈컴바인"]


def test_cumulative_denominator_is_post6_five():
    cases = _cases()
    g6 = sorted(c["name"] for c in cases if c["gate"] and c["log_no"] == P8.POST6_LOG)
    g7 = [c for c in cases if c["gate"] and c["log_no"] == P8.POST7_LOG]
    assert g6 == sorted(P6.INTAKE_DENOM_PRED) and len(g6) == 5
    assert g7 == []


def test_gate_json_recompute_matches_frozen():
    g = json.loads((BASE / "wrc_post8" / "gate.json").read_text(encoding="utf-8"))
    assert g["solo_post8"] == 0
    assert (g["cumulative"]["n"], g["cumulative"]["db_absent"], g["cumulative"]["empty"]) == (5, 0, 4)
    assert g["cumulative"]["fire"] is True
    ex = [c for c in g["cases"] if c["post"] in ("post4", "post5")]
    assert len(ex) == 10
    assert sum(c["a0_gross"] in ("db_absent", "empty") for c in ex) == 6       # FREEZE_WRC §4 6/10
    assert [d["D"] for d in g["approx_codez"]] == P8.APPROX_DAYS
    assert g["approx_days_db"] == P8.APPROX_DAYS


# ── 3. 의무 줄 ───────────────────────────────────────────────────────────────
def test_d4_three_numbers_on_the_same_row():
    rows = [ln for ln in _numbers().splitlines() if ln.startswith("| post8 | **0** |")]
    assert len(rows) == 1
    r = rows[0]
    assert "**5**(post6 5 + post7 0 + post8 0)" in r and "| **5** |" in r
    assert "`WRC-G1` 발동" in r and "「최소 n 미달」이 «아니다»" in r


def test_d3_d5_d8_d9_lines_present():
    t = _numbers()
    assert "`approx` 포함 시 최소 n 이 차는 축: **없음**" in t
    assert "`exact` 분모 **5**(누적 · 단독 0) / `approx` 포함 분모 **6**" in t
    assert "| 갈래 | 지위 | **n** | 최소 n(3) | `WRC-G1` | **답** | 비고 |" in t
    assert "| `1.0.42` | 10 | 1 |" in t and "| `missing` | 13 | 1 |" in t
    for s in ("D-9 ① 쿼리 실행 시각(KST)", "D-9 ② 창 구간 `max(daily_prices.updated_at)`",
              "봉은 D+1(2026-09-21) sweep 이후 읽음", "창 구간 `min(updated_at)` =", "혼합 빈티지」"):
        assert s in t, s
    assert "라이브 채택 대상이 아니다" in t


def test_d9_first_read_matches_stamp():
    st = json.loads((BASE / "wrc_post8" / "read_stamp.json").read_text(encoding="utf-8"))
    m = re.search(r"\| D-9 ① 쿼리 실행 시각\(KST\) \| \*\*([0-9: -]+)\*\*", _numbers())
    assert m and m.group(1) == st["first_read_kst"]


def test_mixed_vintage_lines_cover_pd27_table():
    t = _numbers()
    n = t.count("은 제도 경계 2026-09-14 를 걸친다")
    assert n == len(P8.PD27_CROSS) + len(P8.APPROX_DAYS)
    assert "`[2026-09-11, 2026-09-18]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `1` 봉 / 후 `5` 봉" in t


def test_no_grade_names_and_verdicts_carry_reason():
    t = _numbers()
    for g in ("GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F", "충족·참고용", "낡음(재실행 금지)", "[갈래 의존]"):
        assert g not in t, g
    verdict_rows = [ln for ln in t.splitlines() if re.match(r"\| `WRC-(P1|N1|N2|O1|V1)` \|", ln)]
    assert len(verdict_rows) == 5 and all("(`WRC-G1` 발동)" in r for r in verdict_rows)


def test_no_adj_factor_in_sql():
    src = (BASE / "run_wrc_post8.py").read_text(encoding="utf-8")
    sql = re.findall(r'"(SELECT[^"]*)"', src)
    assert sql and not any("adj_factor" in q for q in sql)


# ── 4. post7 이하 회귀 ───────────────────────────────────────────────────────
def test_post7_and_earlier_untouched_vs_head():
    for rel in ("run_wrc_post7.py", "run_wrc_post6.py", "run_wrc_explore.py",
                "RESULTS_WRC_POST7_NUMBERS.md", "RESULTS_WRC_POST6_NUMBERS.md", "RESULTS_WRC_EXPLORE.md",
                "RESULTS_WRC_POST7.md", "PREREG_WEIGHTED_RECON.md", "FREEZE_WRC_2026-09-02.md"):
        wt = (BASE / rel).read_bytes().replace(b"\r\n", b"\n")
        assert wt == _head_blob(rel).replace(b"\r\n", b"\n"), f"{rel} 가 {BASE_REF} 와 다르다"
    # 🔴 대칭 — 기준 ref 에 post8 판은 «없다»(ref 가 post8 이전임을 확인 · 검사력)
    r = subprocess.run(["git", "cat-file", "-e", f"{BASE_REF}:./run_wrc_post8.py"], cwd=str(BASE), capture_output=True)
    assert r.returncode != 0
