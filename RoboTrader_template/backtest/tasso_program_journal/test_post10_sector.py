# -*- coding: utf-8 -*-
"""`SEC-` 축 post10 판정 모드 시험 — `test_post9_sector.py` 구조 승계(자기 축만).

지키는 것 다섯:
  ① **post9 이하 모드 불변** — `run_sector.py` 의 기존 함수 본문 md5 가 `0cc2e5e`(post10 모드 추가 «전» · 원장 append 커밋)
     블롭과 같고(바뀐 함수는 `run` 하나 = 분기 1개), 동결·직전 산출물(`RESULTS_SECTOR_POST9/8/7/6/DRYRUN_NUMBERS.md` ·
     `sector_post9/8/7/6/dryrun/`)이 `0cc2e5e` 블롭과 **byte(줄끝 정규화) 동일**하다. `both` 에 post10 이 없다.
  ② **post10 분모** — 신규 `exact` 9(섹터코드 9/9) · `approx` 0 · `none` 3(후속) · 이중 매핑 일치 · 재진입 4/9(항등 아님).
  ③ **판정 배선 전수 검사** — §3 1행 ⛔ 열 6조건이 `SEC-P1` 에 배선 · `P9-갈래게이트인쇄전용`(양쪽 인쇄) ·
     🆕 `P10-갈래게이트자리` 신고 줄 k ↔ 갈래 표 · 의무 줄 · 등급 이름 0.
  ④ **post10 신규 의무** — `P9-결측분리`(수준 목록에 `missing` 없음 · 결측 n 줄) · `P9-스탬프통일`(`read_stamp.json`) ·
     `P10-기업행위봉`(신고 줄 + 「기업행위 건 제외」 갈래 «답(참고) · 세지 않는다») · 「샌즈 제외」 인쇄만 · 걸침 8줄 + 서산 전부 경계 전.
  ⑤ **변이 음성** — 검사가 «잡는지»를 입력을 일부러 깨서 확인한다(검사력).

실행: `python -m pytest test_post10_sector.py -q -p no:cacheprovider` (DB 접속 없음 · 원장 CSV 와 산출물만 읽는다)
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
NUMBERS = BASE / "RESULTS_SECTOR_POST10_NUMBERS.md"
VERDICT = BASE / "sector_post10" / "verdict.json"
BASE_REF = "0cc2e5e"   # 🔴 원장 append 커밋 — `run_sector.py` 에 post10 모드가 붙기 «전» 마지막 커밋(run_sector.py 는 8e014ca 와 같다)


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


def _main10_src() -> str:
    src = (BASE / "run_sector.py").read_text(encoding="utf-8")
    return ast.get_source_segment(src, [n for n in ast.parse(src).body
                                        if isinstance(n, ast.FunctionDef) and n.name == "main_post10"][0])


# ── ① post9 이하 불변 ────────────────────────────────────────────────────────
def test_existing_function_bodies_unchanged():
    old = _bodies(_head_bytes("run_sector.py").decode("utf-8"))
    new = _bodies((BASE / "run_sector.py").read_text(encoding="utf-8"))
    changed = sorted(k for k in old if old[k] != new.get(k))
    assert changed == ["run"], changed
    for k in ("main", "main_post6", "db_context", "post7_context", "main_post7", "post8_context", "main_post8",
              "post9_context", "main_post9", "p9_read_stamp", "p9_d9_rows",
              "v1_axis_verdicts", "load_day", "measure_case", "pools_for", "x1_run", "x1_base_for", "day_stats"):
        assert old[k] == new[k], k
    added = {"post10_context", "main_post10", "p10_read_stamp", "p10_d9_rows", "p10_level_lines", "p10_collect_lines",
             "p10_cross_windows", "p10_ca_scan"}
    assert added <= set(new) - set(old)
    assert not {"post10_context", "main_post10"} & set(old), "🔴 대칭 — 기준 ref 에 post10 판이 «없다»(검사력)"


def test_both_mode_excludes_post10():
    src = (BASE / "run_sector.py").read_text(encoding="utf-8")
    run_src = ast.get_source_segment(src, [n for n in ast.parse(src).body
                                           if isinstance(n, ast.FunctionDef) and n.name == "run"][0])
    assert 'if mode in ("both", "dryrun"):' in run_src and 'if mode in ("both", "post6"):' in run_src
    assert 'if mode == "post10":' in run_src and 'if mode == "post9":' in run_src
    assert not re.search(r'mode in \([^)]*"post10"', run_src)
    assert 'choices=("dryrun", "post6", "both", "post7", "post8", "post9", "post10")' in src


def test_prior_artifacts_byte_identical_to_head():
    files = ["RESULTS_SECTOR_POST9_NUMBERS.md", "RESULTS_SECTOR_POST9.md", "RESULTS_SECTOR_POST8_NUMBERS.md",
             "RESULTS_SECTOR_POST8.md", "RESULTS_SECTOR_POST7_NUMBERS.md", "RESULTS_SECTOR_POST6_NUMBERS.md",
             "RESULTS_SECTOR_DRYRUN_NUMBERS.md", "RESULTS_SECTOR_POST7.md",
             "PREREG_SECTOR_COMOVE.md", "FREEZE_SECTOR_2026-09-03.md"]
    for d in ("sector_post9", "sector_post8", "sector_post7", "sector_post6", "sector_dryrun"):
        tracked = _head_ls(d)
        assert tracked, d
        files += tracked
    for rel in files:
        wt = (BASE / rel).read_bytes().replace(b"\r\n", b"\n")
        assert wt == _head_bytes(rel).replace(b"\r\n", b"\n"), rel


def test_no_anc_artifacts_and_no_lane_overreach():
    """`F-5` (ㄱ) — ANC 앵커 산출물을 «만들지 않았다»."""
    assert not list(BASE.glob("RESULTS_ANCHOR_POST10*")) and not (BASE / "anchor_post10").exists()


# ── ② post10 분모 ────────────────────────────────────────────────────────────
def _items10():
    rows = load_ledger("post6")                      # 🔴 전 행(필터 없음) — 필터는 이 축이 «따로» 건다
    codes, _ = build_codes8()
    codes.update(POST9_CODES)
    for nm, c, _r in S.POST10_NEW:
        codes[nm] = c
    items, post_idx = exact_items(rows, codes)
    p10 = post_idx[S.POST10_LOG_NO]
    return rows, [it for it in items if it["post"] == p10], \
        [it for it in approx_items(rows, codes, post_idx) if it["post"] == p10]


def test_post10_denominator_and_dual_mapping():
    rows, ex, ap = _items10()
    want = ["라온시큐어", "범한퓨얼셀", "서산", "샌즈랩", "성호전자", "HT로보틱스", "한켐", "뷰노", "우리로"]
    assert sorted(it["name"] for it in ex) == sorted(want)
    assert ap == []
    none = sorted(r["stock_name"] for r in rows if r["post_log_no"] == S.POST10_LOG_NO
                  and r["reg_date_precision"] == "none")
    assert none == sorted(S.POST10_NONE_NEW + S.POST10_FOLLOWUP) == sorted(["한컴위드", "코데즈컴바인", "빛샘전자"])
    assert {nm: r for nm, _c, r in S.POST10_NEW if r} == {it["name"]: it["reg"] for it in ex}
    assert len({c for _n, c, _r in S.POST10_NEW}) == 12
    assert S.DB_UPTO_POST10 == "2026-10-02" and S.POST10_IDX == 10
    # 🔂 PD-3 — 재진입 4/9(항등 아님) · 항목 내 2 사이클 = 샌즈랩
    assert set(S.PD3_FLAG_P10) == {it["code"] for it in ex if it["name"] in ("범한퓨얼셀", "서산", "한켐", "우리로")}
    assert sum(S.PD3_FLAG_P10.values()) == 4 and len(ex) - 4 == 5
    assert S.POST10_TWO_CYCLE_CODE == [it["code"] for it in ex if it["name"] == "샌즈랩"][0]
    assert S.SEC_P2_PRIOR_P10 == {"n_judgements": 3, "n_support": 0}


def test_post10_log_in_committed_ledger():
    rows = _head_bytes("ledger_trades.csv").decode("utf-8").splitlines()
    assert sum(1 for ln in rows if ln.startswith(S.POST10_LOG_NO + ",")) == 12


# ── ③ 판정 배선 전수 검사 ─────────────────────────────────────────────────
def test_verdict_snapshot():
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    assert v["post_log_no"] == S.POST10_LOG_NO and v["window_end"] == "2026-10-02"
    assert v["denominator_exact"] == 9
    assert v["SEC-P2"]["prior"] == {"n_judgements": 3, "n_support": 0}
    assert sorted(v["same_snapshot_recompute"]) == ["post6", "post7", "post8"]
    assert v["two_cycle_exclusion"]["print_only"] is True and v["two_cycle_exclusion"]["code"] == "411080"
    assert v["reentry_sensitivity"]["P6_PRIOR_CYCLE_IN_WINDOW_in_denominator"] == S.PD3_FLAG_P10
    assert v["gates"]["SEC-G1"]["rate"] is not None and v["P10_corp_action"]["n"] == 9


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
    m10 = _main10_src()
    assert "gates_ok = (len(items) >= MIN_EXACT) and (g1_main < G1_THR) and b1fire" in m10
    assert "and_ok = bool(gates_ok and c_n1 and c_b1 and c_b2)" in m10
    assert "v1_split_p9, V1_COUNTED, V1_GATE_EXCL = p9_split(V1PRE[\"VD\"], NMAP, G1)" in m10
    assert "p1_blocked_v1 = bool(v1_split_p9 and (and_ok or v1_any_ok))" in m10
    assert "v1_any_ok = any(v is True for v in V1_COUNTED.values())" in m10
    assert "p1_blocked_x1 = bool(not x1_ok_pre)" in m10
    assert "p1_ok = bool(and_ok and not v1_split_p9 and x1_ok_pre)" in m10
    assert "v1_split_p8, V1_COUNTED8 = p8_split(" in m10
    t = NUMBERS.read_text(encoding="utf-8")
    sec = t.split("#### 🆕 판정 배선 전수 검사", 1)[1].split("### 🔒 판정", 1)[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
    assert len(rows) == 6 and all("| ✅" in r for r in rows)


def _gate_rows(t: str):
    sec = t.split("### 7-3.", 1)[1].split("#### 7-3-1.", 1)[0]
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
            for ln in sec.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
    assert rows and all(len(r) == 9 for r in rows)
    return sec, rows


def _count_gate_slots(rows) -> list:
    out = []
    for r in rows:
        ax, lab, n, _min, ans, g1, p8c, p9c, note = r
        nonmain = "판정 갈래" not in note
        gate_unable = ("판정 불가" in ans) and g1.endswith("%") and float(g1[:-1]) / 100 >= S.G1_THR
        if nonmain and int(n.strip("*")) >= S.MIN_EXACT and gate_unable:
            out.append(f"{ax}|{lab}")
    return out


def test_p9_gate_print_only_and_p10_slot_line_match_table():
    """`PREREG_POST9.md` §3 (나) 3 + `PREREG_POST10.md` §2 (나) 3·4 — 신고 줄 k 가 갈래 표에서 센 수와 같다."""
    t = NUMBERS.read_text(encoding="utf-8")
    sec, rows = _gate_rows(t)
    slots = _count_gate_slots(rows)
    for r in rows:
        if f"{r[0]}|{r[1]}" in slots:
            assert "✅ 센다" not in r[7], r                 # 판정 읽기에서는 세지 않는다
            assert r[6] == "✅ 센다", r                      # 센다 읽기(양쪽 인쇄)에는 남아 있다
    m = re.search(r"\*「`P10-갈래게이트자리`: 적용 자리 (\d+)\((.*?)\) · 판정 이동 (0|있음)」\*", sec)
    assert m, "🔴 신고 줄 없음 — 그 산출물 무효(가분성)"
    assert int(m.group(1)) == len(slots), (m.group(1), slots)
    if slots:
        assert sorted(x.strip() for x in m.group(2).split(" · ")) == sorted(slots)
    assert "🟢 위반 아님" in t and "🟢 일치" in sec


def test_p10_slot_check_has_teeth_mutation():
    """⑤ 변이 음성 — 표에서 «세지 않는다» 행을 하나 더 만들면(k 불일치) 검사가 잡는다."""
    sec, rows = _gate_rows(NUMBERS.read_text(encoding="utf-8"))
    slots = _count_gate_slots(rows)
    forged = [list(r) for r in rows]
    victim = next(r for r in forged if f"{r[0]}|{r[1]}" not in slots)
    victim[4], victim[5], victim[2] = "**판정 불가**", "50.0%", "**9**"
    victim[7] = "✅ 센다"
    assert len(_count_gate_slots(forged)) == len(slots) + 1       # 신고 줄 k(=len(slots)) 와 어긋난다


def test_gate_slot_source_extends_to_axes_3_and_4():
    m10 = _main10_src()
    assert '(ax == 3 and lab != "글 단위 중앙") or (ax == 4 and lab != "`exact` 만")' in m10
    assert "return g1map[(MAIN_N, MAIN_M)]" in m10


# ── ④ post10 신규 의무 ────────────────────────────────────────────────────
def test_duty_lines_present_and_no_grade_names():
    t = NUMBERS.read_text(encoding="utf-8")
    for s in ("**창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · `END` · 전 축(`WRC-` 포함) · PD-1**",
              "**실행 시 `max(date)` = ", "기록만(창 아님)**", "**라이브 채택 금지** — `PREREG_POST9.md` §0-1",
              "D-9 ① 쿼리 실행 시각(KST)", "D-9 ② 창 구간 `max(daily_prices.updated_at)`",
              "봉은 D+1(2026-10-06) sweep 이후 읽음", "창 구간 `min(updated_at)` =",
              "**`P9-공통독법`**", "**`P9-행단위`·`P9-결측분리`**", "**`P9-수집증거`**",
              "`P8-approx의존신고`", "`P9-갈래게이트인쇄전용`", "게이트 인쇄전용", "양쪽 인쇄",
              "`P10-갈래게이트자리`: 적용 자리", "`P10-기업행위봉`: 기업행위 건", "`adj_factor` 산술 0", "처리 = (나)",
              "답(참고) · 세지 않는다", "「샌즈 제외」", "라이브 채택 대상이 아니다",
              "approx` 포함 시 최소 n 이 차는 축: **없음**"):
        assert s in t, s
    for g in ("GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F", "충족·참고용", "낡음(재실행 금지)", "[갈래 의존]"):
        assert g not in t, g
    assert "ANC §2-1" not in t


def test_missing_split_levels_and_stamp():
    """`P9-결측분리` — 수준 목록(괄호 «밖»)에 `missing` 이 없고 결측 n 줄이 있다 · `P9-스탬프통일` — read_stamp.json."""
    t = NUMBERS.read_text(encoding="utf-8")
    m = re.search(r"\*「수준\(행/글\): (.*?) · SSOT = 행\(`PREREG_POST9.md` §4\) \(민감도 · `missing` 을 수준으로 둔 목록: (.*?)\)」\*", t)
    assert m, "수준 목록 줄 없음"
    outside, inside = m.group(1), m.group(2)
    assert "missing" not in outside and "missing" in inside
    assert "`1.0.43` 12/1" in outside and "`1.0.30` 23/1" in outside
    assert "*「결측 n = 19/2」*" in t and "부호 갈림 검사: 통계량 정의 없음(기록만)" in t
    levels_table = t.split("### 9-1.", 1)[1].split("### 9-2.", 1)[0]
    assert "| `missing` |" not in levels_table
    st = json.loads((BASE / "sector_post10" / "read_stamp.json").read_text(encoding="utf-8"))
    assert {"first_read_kst", "timezone", "fingerprint"} <= set(st)
    mm = re.search(r"\| D-9 ① 쿼리 실행 시각\(KST\) \| \*\*([0-9: -]+)\*\*", t)
    assert mm and mm.group(1) == st["first_read_kst"]
    assert json.loads(VERDICT.read_text(encoding="utf-8"))["d9_first_read_kst"] == st["first_read_kst"]
    assert not (BASE / "sector_post10" / "query_stamp.json").exists()


def test_missing_split_check_has_teeth_mutation():
    """⑤ 변이 음성 — `missing` 을 수준 목록(괄호 밖)에 넣은 줄은 검사 정규식이 «잡는다»."""
    bad = "*「수준(행/글): `1.0.30` 23/1 · `missing` 19/2 · SSOT = 행(`PREREG_POST9.md` §4) (민감도 · `missing` 을 수준으로 둔 목록: 위 8수준 + `missing` 19/2)」*"
    m = re.search(r"\*「수준\(행/글\): (.*?) · SSOT = 행\(`PREREG_POST9.md` §4\) \(민감도 · `missing` 을 수준으로 둔 목록: (.*?)\)」\*", bad)
    assert m and "missing" in m.group(1)                       # 위반 — 검사(`missing` not in outside)가 실패하게 만든다
    lines = S.p10_level_lines([{"prog_ver": "", "post_log_no": "x"}, {"prog_ver": "1.0.1", "post_log_no": "y"}])
    assert "`1.0.1` 1/1" in lines[0] and "결측 n = 1/1" in lines[1]


def test_corp_action_lines():
    t = NUMBERS.read_text(encoding="utf-8")
    m = re.search(r"\*「`P10-기업행위봉`: 기업행위 건 (\d+)/9 — (.*?) · `adj_factor` 산술 0 · 처리 = \(나\)」\*", t)
    assert m, "🔴 신고 줄 없음 — 그 산출물 무효"
    k = int(m.group(1))
    sec = t.split("### 7-4.", 1)[1].split("#### 7-4-1.", 1)[0]
    flagged = [ln for ln in sec.splitlines() if ln.startswith("| ") and ln.rstrip().endswith("| 🔴 예 |")]
    assert len(flagged) == k
    ca_row = next(ln for ln in sec.splitlines() if ln.startswith("| 「기업행위 건 제외」"))
    assert "답(참고) · 세지 않는다" in ca_row
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    assert v["P10_corp_action"]["k"] == k and v["P10_corp_action"]["answer_word"] == "답(참고) · 세지 않는다"
    # 계수에 «센다» 로 들어가 있지 않다 — `7-3` 갈래 표에 이 이름이 없다
    assert "기업행위" not in t.split("### 7-3.", 1)[1].split("#### 7-3-1.", 1)[0].split("| # | 갈래")[1].split("- 🆕")[0]


def test_reentry_not_identity_and_sands_print_only():
    t = NUMBERS.read_text(encoding="utf-8")
    sec72 = t.split("### 7-2.", 1)[1].split("### 7-4.", 1)[0]
    assert "항등이 아니다" in sec72 and "4/9" in sec72
    rows = [ln for ln in sec72.splitlines() if ln.startswith("| 제외(민감도)")]
    assert rows and rows[0].split("|")[2].strip() == "5"
    sec731 = t.split("#### 7-3-1.", 1)[1].split("### 7-2.", 1)[0]
    assert "인쇄만" in sec731 and "「샌즈 제외」" in sec731
    row = next(ln for ln in sec731.splitlines() if ln.startswith("| 「샌즈 제외」"))
    assert row.split("|")[2].strip() == "8" and "인쇄만" in row
    assert "| 「샌즈 제외」 |" in t.split("#### 7-4-1.", 1)[1] and "**인쇄만**" in t.split("#### 7-4-1.", 1)[1]


def test_cross_window_lines():
    """걸침 8줄 + 서산 `[D−19, D]` 「전부 경계 전」 줄 · `[D, END]` 걸침 1 · 창5 걸침 1(서산) — PD-27 (바) 표."""
    t = NUMBERS.read_text(encoding="utf-8")
    sec = t.split("### 10-2.", 1)[1].split("### 10-3.", 1)[0]
    cross = [ln for ln in sec.splitlines() if "은 제도 경계 2026-09-14 를 걸친다" in ln]
    assert len(cross) == 10, len(cross)                       # 1(`[D, END]`) + 1(창5) + 8(`[D−19, D]`)
    assert sum("`REG-`/`REC-` `[D−19, D]`" in ln for ln in cross) == 8
    assert sum("`REC-` `[D, END]`" in ln for ln in cross) == 1 and sum("`LAD-` 창5" in ln for ln in cross) == 1
    assert any("전부 제도 경계 전(전 20 / 후 0)" in ln and "서산" in ln and "`[D−19, D]`" not in ln.split("(")[0]
               or ("전부 제도 경계 전" in ln and "서산" in ln) for ln in sec.splitlines())
    assert "걸침 10" in sec and "전부 경계 후 16" in sec and "전부 경계 전 1" in sec
    m = re.search(r"\*\*걸침 (\d+)\*\*", sec)
    assert m and int(m.group(1)) == len(cross)


def test_sec_p2_cumulative_rows():
    """`SEC-P2` 누계 — post9 행은 옮겨 적은 «성립 0 / 판정 3» · post10 행은 그 위에 이어진다(post8 행은 판정 2)."""
    t = NUMBERS.read_text(encoding="utf-8")
    assert "| post8 (옮겨 적은 값) | **불성립** | 성립 0 / 판정 2 |" in t
    assert "| post9 (옮겨 적은 값) | **불성립** | 성립 0 / 판정 3 |" in t
    v = json.loads(VERDICT.read_text(encoding="utf-8"))["SEC-P2"]
    assert v["prior"] == {"n_judgements": 3, "n_support": 0}
    assert v["n_judgements"] == 3 + (0 if json.loads(VERDICT.read_text(encoding="utf-8"))["SEC-P1"]["blocked"] else 1)
