# -*- coding: utf-8 -*-
"""`SEC-` 축 post9 판정 모드 시험 — `test_post8_sector.py` 구조 승계.

지키는 것 넷:
  ① **post8 이하 모드 불변** — `run_sector.py` 의 기존 함수 본문 md5 가 `30aed89`(post9 모드 추가 «전» · 원장 기준 커밋)
     블롭과 같고(바뀐 함수는 `run` 하나 = 분기 1개), 동결·직전 산출물(`RESULTS_SECTOR_POST8/7/6/DRYRUN_NUMBERS.md` ·
     `sector_post8/7/6/dryrun/`)이 `30aed89` 블롭과 **byte(줄끝 정규화) 동일**하다. `both` 에 post9 가 없다.
     (기존 `--mode post6/7/8` 재실행 md5 쌍 비교는 스크래치 복사본에서 «따로» 했고 보고에 적는다 — DB 를 읽으므로 이 시험 밖.)
  ② **post9 분모** — 신규 `exact` 5(섹터코드 5/5) · `approx` 0 · `none` 1(후속 우리기술) · 이중 매핑 일치.
  ③ **판정 배선 전수 검사** — §3 1행 ⛔ 열 6조건이 `SEC-P1` 에 배선 · 🆕 `P9-갈래게이트인쇄전용`(양쪽 인쇄 · 기계 검사 (나)3) ·
     의무 줄(`P9-공통독법`·`P9-행단위`·`P9-수집증거`·라이브 채택 금지 문언) · 등급 이름 0.

실행: `python -m pytest test_post9_sector.py -q -p no:cacheprovider` (DB 접속 없음 · 원장 CSV 와 산출물만 읽는다)
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

import run_sector as S
from run_ranking import POST9_CODES, approx_items, build_codes8, exact_items, load_ledger

BASE = Path(__file__).resolve().parent
NUMBERS = BASE / "RESULTS_SECTOR_POST9_NUMBERS.md"
VERDICT = BASE / "sector_post9" / "verdict.json"
BASE_REF = "30aed89"   # 🔴 원장 기준 커밋 — `run_sector.py` 에 post9 모드가 붙기 «전» 마지막 커밋


def _head_bytes(rel: str) -> bytes:
    r = subprocess.run(["git", "show", f"{BASE_REF}:./{rel}"], cwd=str(BASE), capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout


def _head_ls(dirname: str) -> list:
    r = subprocess.run(["git", "ls-tree", "--name-only", BASE_REF, f"{dirname}/"], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8")
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def _bodies(src: str) -> dict:
    t = ast.parse(src)
    return {n.name: hashlib.md5(ast.get_source_segment(src, n).encode("utf-8")).hexdigest()
            for n in t.body if isinstance(n, ast.FunctionDef)}


# ── ① post8 이하 불변 ────────────────────────────────────────────────────────
def test_existing_function_bodies_unchanged():
    old = _bodies(_head_bytes("run_sector.py").decode("utf-8"))
    new = _bodies((BASE / "run_sector.py").read_text(encoding="utf-8"))
    changed = sorted(k for k in old if old[k] != new.get(k))
    assert changed == ["run"], changed
    for k in ("main", "main_post6", "db_context", "post7_context", "main_post7", "post8_context", "main_post8",
              "v1_axis_verdicts", "load_day", "measure_case", "pools_for", "x1_run", "x1_base_for", "day_stats"):
        assert old[k] == new[k], k
    assert {"post9_context", "main_post9", "p9_read_stamp", "p9_d9_rows"} <= set(new) - set(old)
    assert not {"post9_context", "main_post9"} & set(old), "🔴 대칭 — 기준 ref 에 post9 판이 «없다»(검사력)"


def test_both_mode_excludes_post9():
    src = (BASE / "run_sector.py").read_text(encoding="utf-8")
    run_src = ast.get_source_segment(src, [n for n in ast.parse(src).body
                                           if isinstance(n, ast.FunctionDef) and n.name == "run"][0])
    assert 'if mode in ("both", "dryrun"):' in run_src and 'if mode in ("both", "post6"):' in run_src
    assert 'if mode == "post9":' in run_src and 'if mode == "post8":' in run_src
    assert not re.search(r'mode in \([^)]*"post9"', run_src)
    assert 'choices=("dryrun", "post6", "both", "post7", "post8", "post9")' in src


def test_prior_artifacts_byte_identical_to_head():
    files = ["RESULTS_SECTOR_POST8_NUMBERS.md", "RESULTS_SECTOR_POST8.md", "RESULTS_SECTOR_POST7_NUMBERS.md",
             "RESULTS_SECTOR_POST6_NUMBERS.md", "RESULTS_SECTOR_DRYRUN_NUMBERS.md", "RESULTS_SECTOR_POST7.md",
             "PREREG_SECTOR_COMOVE.md", "FREEZE_SECTOR_2026-09-03.md"]
    for d in ("sector_post8", "sector_post7", "sector_post6", "sector_dryrun"):
        tracked = _head_ls(d)
        assert tracked, d
        files += tracked
    for rel in files:
        wt = (BASE / rel).read_bytes().replace(b"\r\n", b"\n")
        assert wt == _head_bytes(rel).replace(b"\r\n", b"\n"), rel


# ── ② post9 분모 ─────────────────────────────────────────────────────────────
def _items9():
    rows = load_ledger("post6")                      # 🔴 전 행(필터 없음) — 필터는 이 축이 «따로» 건다
    codes, _ = build_codes8()
    for nm, c, _r in S.POST9_NEW:
        codes[nm] = c
    items, post_idx = exact_items(rows, codes)
    p9 = post_idx[S.POST9_LOG_NO]
    return rows, [it for it in items if it["post"] == p9], \
        [it for it in approx_items(rows, codes, post_idx) if it["post"] == p9]


def test_post9_denominator_and_dual_mapping():
    rows, ex, ap = _items9()
    assert sorted(it["name"] for it in ex) == sorted(["삼미금속", "에스투더블유", "빛샘전자", "한국첨단소재", "한컴위드"])
    assert ap == []
    none = sorted(r["stock_name"] for r in rows if r["post_log_no"] == S.POST9_LOG_NO
                  and r["reg_date_precision"] == "none")
    assert none == sorted(S.POST9_NONE_NEW + S.POST9_FOLLOWUP) == ["우리기술"]
    assert all(POST9_CODES[nm] == c for nm, c, _r in S.POST9_NEW)
    assert {nm: r for nm, _c, r in S.POST9_NEW if r} == {it["name"]: it["reg"] for it in ex}
    assert S.DB_UPTO_POST9 == "2026-09-23" and S.POST9_IDX == 9
    assert S.PD3_FLAG_P9 == {} and S.REENTRY_P9 == {}


def test_verdict_snapshot():
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    assert v["post_log_no"] == S.POST9_LOG_NO and v["window_end"] == "2026-09-23"
    assert v["denominator_exact"] == 5 and v["measurable"] == 5
    assert v["gates"]["SEC-G1"]["rate"] == 0.0 and v["gates"]["SEC-G1"]["open"] is True
    p1 = v["SEC-P1"]
    assert p1["verdict_label"] == "불성립" and p1["and_passed"] is False and p1["blocked"] is False
    assert p1["SEC-V1_split"] is True                                   # 전 갈래 읽기 = 갈림(N=5 게이트 발동 갈래 포함)
    assert p1["SEC-V1_split_P8_counts_gate_unable"] is True             # 센다 읽기(민감도)
    assert p1["SEC-V1_split_P9_gate_print_only"] is False               # 🔒 판정 읽기 — 비주 갈래 게이트 판정 불가는 세지 않는다
    assert p1["SEC-V1_gate_print_only_branches"] == ["1|N=5"]
    assert v["SEC-P2"]["prior"] == {"n_judgements": 2, "n_support": 0}
    assert v["SEC-P2"]["n_judgements"] == 3 and v["SEC-P2"]["n_support"] == 0
    assert sorted(v["same_snapshot_recompute"]) == ["post6", "post7", "post8"]


# ── ③ 판정 배선 전수 검사 ─────────────────────────────────────────────────
def test_p1_wiring_is_consistent_in_verdict_json():
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    p1, g = v["SEC-P1"], v["gates"]
    gates_ok = g["min_exact"]["open"] and g["SEC-G1"]["open"] and g["SEC-B1_fire"]["open"]
    comp = all(p1["passed"].values())
    assert p1["and_passed"] == bool(gates_ok and comp)
    assert p1["blocked_by_SEC-V1"] == bool(p1["SEC-V1_split_P9_gate_print_only"]
                                           and (p1["and_passed"] or p1["SEC-V1_any_branch_ok"]))
    assert p1["blocked_by_SEC-X1"] == bool(not p1["SEC-X1_ok"])
    assert p1["blocked"] == bool(p1["blocked_by_SEC-V1"] or p1["blocked_by_SEC-X1"])
    assert (p1["verdict"] is None) == p1["blocked"]
    if not p1["blocked"]:
        assert p1["verdict"] == bool(p1["and_passed"])
    assert p1["verdict_label"] == ("판정 불가" if p1["blocked"] else ("성립" if p1["verdict"] else "불성립"))
    assert p1["SEC-X1_ok"] == g["SEC-X1"]["open"]


def test_p1_wiring_in_source_covers_all_six_conditions():
    src = (BASE / "run_sector.py").read_text(encoding="utf-8")
    m9 = ast.get_source_segment(src, [n for n in ast.parse(src).body
                                      if isinstance(n, ast.FunctionDef) and n.name == "main_post9"][0])
    assert "gates_ok = (len(items) >= MIN_EXACT) and (g1_main < G1_THR) and b1fire" in m9
    assert "and_ok = bool(gates_ok and c_n1 and c_b1 and c_b2)" in m9
    assert "v1_split_p9, V1_COUNTED, V1_GATE_EXCL = p9_split(V1PRE[\"VD\"], NMAP, G1)" in m9   # 🆕 P9 판정 읽기
    assert "p1_blocked_v1 = bool(v1_split_p9 and (and_ok or v1_any_ok))" in m9
    assert "v1_any_ok = any(v is True for v in V1_COUNTED.values())" in m9
    assert "p1_blocked_x1 = bool(not x1_ok_pre)" in m9
    assert "p1_ok = bool(and_ok and not v1_split_p9 and x1_ok_pre)" in m9
    assert "v1_split_p8, V1_COUNTED8 = p8_split(" in m9                                     # 센다 읽기는 «병기»로만
    t = NUMBERS.read_text(encoding="utf-8")
    sec = t.split("#### 🆕 판정 배선 전수 검사", 1)[1].split("### 🔒 판정", 1)[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
    assert len(rows) == 6 and all("| ✅" in r for r in rows)


def test_p9_gate_print_only_machine_check():
    """`PREREG_POST9.md` §3 (나) 3 — (비주 갈래 ∧ n ≥ 3 ∧ 답 판정 불가 ∧ 사유 = 그 갈래 게이트) 행이 갈림 계수에 «센다» 면 위반."""
    t = NUMBERS.read_text(encoding="utf-8")
    sec = t.split("### 7-3.", 1)[1].split("#### 7-3-1.", 1)[0]
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
            for ln in sec.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
    assert rows and all(len(r) == 9 for r in rows)
    n_gate = 0
    for r in rows:
        ax, lab, n, _min, ans, g1, p8c, p9c, note = r
        nonmain = "판정 갈래" not in note and "N=3" != lab
        gate_unable = ("판정 불가" in ans) and g1.endswith("%") and float(g1[:-1]) / 100 >= S.G1_THR
        if nonmain and int(n.strip("*")) >= S.MIN_EXACT and gate_unable:
            n_gate += 1
            assert "✅ 센다" not in p9c, r                 # 판정 읽기에서는 세지 않는다
            assert p8c == "✅ 센다", r                      # 센다 읽기(양쪽 인쇄)에는 남아 있다
    assert n_gate == 1
    assert "**두 읽기가 다르다**" in t or "두 읽기가 다르다" in t
    assert "🟢 위반 아님" in t


def test_duty_lines_present_and_no_grade_names():
    t = NUMBERS.read_text(encoding="utf-8")
    for s in ("**창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**",
              "**실행 시 `max(date)` = ", "기록만(창 아님)**", "**라이브 채택 금지** — `PREREG_POST9.md` §0-1",
              "D-9 ① 쿼리 실행 시각(KST)", "D-9 ② 창 구간 `max(daily_prices.updated_at)`",
              "봉은 D+1(2026-09-28) sweep 이후 읽음", "창 구간 `min(updated_at)` =",
              "**`P9-공통독법`**", "**`P9-행단위`**", "**`P9-수집증거`**", "`P9-결측분리` 는 **post10 부터**",
              "`P8-approx의존신고`", "`P9-갈래게이트인쇄전용`", "게이트 인쇄전용", "양쪽 인쇄",
              "`missing` | 19 | 2 |", "라이브 채택 대상이 아니다"):
        assert s in t, s
    m = re.search(r"\*\*걸침 (\d+)\*\*", t)
    assert m and t.count("은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `") == int(m.group(1))
    for g in ("GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F", "충족·참고용", "낡음(재실행 금지)", "[갈래 의존]"):
        assert g not in t, g


def test_d9_first_read_matches_stamp():
    st = json.loads((BASE / "sector_post9" / "read_stamp.json").read_text(encoding="utf-8"))
    m = re.search(r"\| D-9 ① 쿼리 실행 시각\(KST\) \| \*\*([0-9: -]+)\*\*", NUMBERS.read_text(encoding="utf-8"))
    assert m and m.group(1) == st["first_read_kst"]
    assert json.loads(VERDICT.read_text(encoding="utf-8"))["d9_first_read_kst"] == st["first_read_kst"]
