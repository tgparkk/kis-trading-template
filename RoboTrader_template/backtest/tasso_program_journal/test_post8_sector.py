# -*- coding: utf-8 -*-
"""`SEC-` 축 post8 판정 모드 시험 — `test_post6_sector.py` 규약 승계(post7 판 시험은 «없었다»).

지키는 것 셋:
  ① **post7 이하 모드 불변** — `run_sector.py` 의 기존 함수 본문 md5 가 `HEAD` 블롭과 같고(바뀐 함수는 `run`
     하나 = 분기 1개), 동결·직전 산출물(`RESULTS_SECTOR_POST7/POST6/DRYRUN_NUMBERS.md` · `sector_post7/` ·
     `sector_post6/` · `sector_dryrun/`)이 `HEAD` 블롭과 **byte(줄끝 정규화) 동일**하다. `both` 에 post8 이 없다.
  ② **post8 분모** — 신규 `exact` 4(섹터코드 3/4 · 액스비스 미수록) · `approx` 2(날짜 없음) · `none` 4 ·
     이중 매핑(`run_ranking.POST8_CODES` ↔ `POST8_NEW`) 일치.
  ③ **판정 배선 전수 검사** — §3 1행 ⛔ 열 6조건이 `SEC-P1` 에 배선됐다(`verdict.json` 논리 일관 ·
     소스의 배선 식 · 산출물의 6행 표) · 🆕 `P8-갈래계수` · 의무 줄(`D-3`·`D-5`·`D-8`·`D-9`) · 등급 이름 0.

실행: `python -m pytest test_post8_sector.py -q -p no:cacheprovider` (DB 접속 없음 · 원장 CSV 와 산출물만 읽는다)
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

import run_sector as S
from run_ranking import POST8_CODES, approx_items, build_codes8, exact_items, load_ledger

BASE = Path(__file__).resolve().parent
NUMBERS = BASE / "RESULTS_SECTOR_POST8_NUMBERS.md"
VERDICT = BASE / "sector_post8" / "verdict.json"


def _head_bytes(rel: str) -> bytes:
    r = subprocess.run(["git", "show", f"HEAD:./{rel}"], cwd=str(BASE), capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout


def _head_ls(dirname: str) -> list:
    r = subprocess.run(["git", "ls-tree", "--name-only", "HEAD", f"{dirname}/"], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8")
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def _bodies(src: str) -> dict:
    t = ast.parse(src)
    return {n.name: hashlib.md5(ast.get_source_segment(src, n).encode("utf-8")).hexdigest()
            for n in t.body if isinstance(n, ast.FunctionDef)}


# ── ① post7 이하 불변 ────────────────────────────────────────────────────────
def test_existing_function_bodies_unchanged():
    old = _bodies(_head_bytes("run_sector.py").decode("utf-8"))
    new = _bodies((BASE / "run_sector.py").read_text(encoding="utf-8"))
    changed = sorted(k for k in old if old[k] != new.get(k))
    assert changed == ["run"], changed
    for k in ("main", "main_post6", "db_context", "post7_context", "main_post7", "v1_axis_verdicts",
              "load_day", "measure_case", "pools_for", "x1_run", "x1_base_for", "day_stats"):
        assert old[k] == new[k], k
    assert {"post8_context", "main_post8"} <= set(new) - set(old)


def test_both_mode_excludes_post8():
    src = (BASE / "run_sector.py").read_text(encoding="utf-8")
    run_src = ast.get_source_segment(src, [n for n in ast.parse(src).body
                                           if isinstance(n, ast.FunctionDef) and n.name == "run"][0])
    assert 'if mode in ("both", "dryrun"):' in run_src and 'if mode in ("both", "post6"):' in run_src
    assert 'if mode == "post8":' in run_src
    assert not re.search(r'mode in \([^)]*"post8"', run_src)
    assert 'choices=("dryrun", "post6", "both", "post7", "post8")' in src


def test_prior_artifacts_byte_identical_to_head():
    files = ["RESULTS_SECTOR_POST7_NUMBERS.md", "RESULTS_SECTOR_POST6_NUMBERS.md",
             "RESULTS_SECTOR_DRYRUN_NUMBERS.md", "RESULTS_SECTOR_POST7.md", "PREREG_SECTOR_COMOVE.md",
             "FREEZE_SECTOR_2026-09-03.md"]
    for d in ("sector_post7", "sector_post6", "sector_dryrun"):
        tracked = _head_ls(d)
        assert tracked, d
        files += tracked
    for rel in files:
        wt = (BASE / rel).read_bytes().replace(b"\r\n", b"\n")
        assert wt == _head_bytes(rel).replace(b"\r\n", b"\n"), rel


# ── ② post8 분모 ─────────────────────────────────────────────────────────────
def _items8():
    rows = load_ledger("post6")                      # 🔴 전 행(필터 없음) — 필터는 이 축이 «따로» 건다
    codes, _ = build_codes8()
    for nm, c, _r in S.POST8_NEW:
        codes[nm] = c
    items, post_idx = exact_items(rows, codes)
    p8 = post_idx[S.POST8_LOG_NO]
    return rows, [it for it in items if it["post"] == p8], \
        [it for it in approx_items(rows, codes, post_idx) if it["post"] == p8]


def test_post8_denominator_and_dual_mapping():
    rows, ex, ap = _items8()
    assert sorted(it["name"] for it in ex) == sorted(["우리로", "JW신약", "액스비스", "우리기술"])
    assert sorted(it["name"] for it in ap) == ["코데즈컴바인", "헥토파이낸셜"] and all(not it["reg"] for it in ap)
    none = sorted(r["stock_name"] for r in rows if r["post_log_no"] == S.POST8_LOG_NO
                  and r["reg_date_precision"] == "none")
    assert none == sorted(S.POST8_NONE_NEW + S.POST8_FOLLOWUP)
    assert all(POST8_CODES[nm] == c for nm, c, _r in S.POST8_NEW)
    assert {nm: r for nm, _c, r in S.POST8_NEW if r} == {it["name"]: it["reg"] for it in ex}
    assert S.POST8_TWO_CYCLE_CODE == POST8_CODES["우리로"]
    assert S.DB_UPTO_POST8 == "2026-09-18" and S.POST8_IDX == 8


def test_verdict_denominator_and_g1():
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    assert v["post_log_no"] == S.POST8_LOG_NO and v["window_end"] == "2026-09-18"
    assert v["denominator_exact"] == 4 and v["measurable"] == 3
    assert abs(v["gates"]["SEC-G1"]["rate"] - 0.25) < 1e-12 and v["gates"]["SEC-G1"]["open"] is True


# ── ③ 판정 배선 전수 검사 ─────────────────────────────────────────────────
def test_p1_wiring_is_consistent_in_verdict_json():
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    p1, g = v["SEC-P1"], v["gates"]
    gates_ok = g["min_exact"]["open"] and g["SEC-G1"]["open"] and g["SEC-B1_fire"]["open"]
    comp = all(p1["passed"].values())
    assert p1["and_passed"] == bool(gates_ok and comp)
    assert p1["blocked_by_SEC-V1"] == bool(p1["and_passed"] and p1["SEC-V1_split_P8"])
    assert p1["blocked_by_SEC-X1"] == bool(p1["and_passed"] and not p1["SEC-X1_ok"])
    assert p1["blocked"] == bool(p1["blocked_by_SEC-V1"] or p1["blocked_by_SEC-X1"])
    assert (p1["verdict"] is None) == p1["blocked"]
    if not p1["blocked"]:
        assert p1["verdict"] == bool(p1["and_passed"])
    assert p1["verdict_label"] == ("판정 불가" if p1["blocked"] else ("성립" if p1["verdict"] else "불성립"))
    assert p1["SEC-X1_ok"] == g["SEC-X1"]["open"]


def test_p1_wiring_in_source_covers_all_six_conditions():
    src = (BASE / "run_sector.py").read_text(encoding="utf-8")
    m8 = ast.get_source_segment(src, [n for n in ast.parse(src).body
                                      if isinstance(n, ast.FunctionDef) and n.name == "main_post8"][0])
    assert "gates_ok = (len(items) >= MIN_EXACT) and (g1_main < G1_THR) and b1fire" in m8
    assert "and_ok = bool(gates_ok and c_n1 and c_b1 and c_b2)" in m8
    assert "p1_blocked_v1 = bool(and_ok and v1_split_p8)" in m8
    assert "p1_blocked_x1 = bool(and_ok and not x1_ok_pre)" in m8
    assert "p1_ok = bool(and_ok and not v1_split_p8 and x1_ok_pre)" in m8
    assert 'assert x1_ok == x1_ok_pre' in m8                    # 사전 계산한 X1 ↔ §6 인쇄값 일치
    t = NUMBERS.read_text(encoding="utf-8")
    sec = t.split("#### 🆕 판정 배선 전수 검사", 1)[1].split("### 🔒 판정", 1)[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
    assert len(rows) == 6 and all("| ✅" in r for r in rows)


def test_duty_lines_present_and_no_grade_names():
    t = NUMBERS.read_text(encoding="utf-8")
    for s in ("D-9 ① 쿼리 실행 시각(KST)", "D-9 ② 창 구간 `max(daily_prices.updated_at)`",
              "봉은 D+1(2026-09-21) sweep 이후 읽음", "창 구간 `min(updated_at)` =",
              "`approx` 포함 시 최소 n 이 차는 축: **없음**", "| `1.0.42` | 10 | 1 |",
              "`P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)`", "「우리로 제외」", "라이브 채택 대상이 아니다",
              "창 종료 `2026-09-18` = 발행 당일", "액스비스(`0011A0`)만 `stock_industry` 미수록"):
        assert s in t, s
    assert t.count("은 제도 경계 2026-09-14 를 걸친다") == len(__import__("run_ranking").POST8_PD27_CROSS)
    for g in ("GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F", "충족·참고용", "낡음(재실행 금지)", "[갈래 의존]"):
        assert g not in t, g


def test_d9_first_read_matches_stamp():
    st = json.loads((BASE / "sector_post8" / "read_stamp.json").read_text(encoding="utf-8"))
    m = re.search(r"\| D-9 ① 쿼리 실행 시각\(KST\) \| \*\*([0-9: -]+)\*\*", NUMBERS.read_text(encoding="utf-8"))
    assert m and m.group(1) == st["first_read_kst"]
    assert json.loads(VERDICT.read_text(encoding="utf-8"))["d9_first_read_kst"] == st["first_read_kst"]
