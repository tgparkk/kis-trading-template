# -*- coding: utf-8 -*-
"""`run_reconstruct_post9.py` 가드 시험 — post8 판(`test_post8_reconstruct.py`) 구조 승계 · 짧게.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* · *가드를 시험하지 않으면 그것도 장식이다*.

실행: `python -m pytest test_post9_reconstruct.py -q -p no:cacheprovider`
      (라이브 트리 import 0건 · P9 만 DB SELECT — 출력은 **임시 폴더**에만 쓴다 · DB 불가 또는 지문 이동이면 skip)

  P1 동결 상수(창 종료 09-23 = 발행 당일 · logNo · 원장 커밋 · 제도 경계 · D+1 sweep · REC-Z5 · 시드 = post8 값)
  P2 `TARGETS` = `INTAKE_2026-09-24_post9.md` §1 신규 5건 · 레그 = 원장 post9 행 · 후속 우리기술 = TARGETS 밖(대칭: 흔든 사본 불일치)
  P3 분모 — exact 5 · approx 0 · first_only 3 · 다차수 2 · 재진입 0 · 레그≥4 2(< 3) · Z4 관행 2 / 「정확히 3레그」 0
  P4 승계 — 판정 함수·통계 핵 = post8/post5/post6 «같은 객체» · 새 함수 = `win5_count` 하나(+ 인쇄 보조)
  P5 D-9 ① 도장 — stamp 파일 = 최초 시각 1개(`runs_kst` 없음) · 경로 = `reconstruct_post9/query_stamp.json`
  P6 소스 위생 — import 허용 목록 · SELECT 뿐 · `adj_factor` 산술 0 · 쓰기 2곳
  P7 산출물 인쇄 의무 — 머리 3줄(창 종료 · max(date) · 라이브 채택 금지 §0-1) · D-9 ①~④ · 걸침 5줄 · 전부 후 3줄 ·
     D-3 한 줄 · `P9-공통독법` 신고 줄 · D-5 36행 · 확인 5 신고 줄 · 감시 줄 · 등급 이름 0
  P8 판정값 스냅샷(이 회차 값 — 바뀌면 재검수 대상)
  P9 재실행 byte 동일(임시 폴더 · DB SELECT) · R1 post8 가드 시험 통과 · R2 post4~8 파일 무변경(기준 `30aed89`)
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import run_reconstruct_post5 as P5M
import run_reconstruct_post6 as P6M
import run_reconstruct_post8 as P8
import run_reconstruct_post9 as P9

BASE = Path(__file__).resolve().parent
SRC = (BASE / "run_reconstruct_post9.py").read_text(encoding="utf-8")
NUMBERS = BASE / "RESULTS_RECONSTRUCT_POST9_NUMBERS.md"
BASE_REF = "30aed89"   # 원장 기준 커밋(post9 산출 «이전») — HEAD 비교는 검사력 0
NM, CODE, D0, PREC, LEGS, TR, PRESET, LABEL, FO, REENT = range(10)

INTAKE = {  # INTAKE_2026-09-24_post9.md §1 · 테스트 쪽 독립 사본 (코드, 등록일, 정밀도, 레그, 차수, 프리셋, 라벨, fo, 재진입)
    "삼미금속": ("012210", "2026-09-04", "exact", [22.09, 17.76, 13.45, 9.23], 1, "HDR60", "TP", True, False),
    "에스투더블유": ("488280", "2026-09-10", "exact", [15.08, 10.64], 1, "HDR60", "TP", True, False),
    "빛샘전자": ("072950", "2026-09-14", "exact", [23.08, 21.05, 18.64, 16.46, 14.20, 12.26, 10.08],
             1, "HDR60", "TP", True, False),
    "한국첨단소재": ("062970", "2026-09-15", "exact", [3.80, 3.79, 3.79], 4, "HDR60", "TP", False, False),
    "한컴위드": ("054920", "2026-09-15", "exact", [7.55, 7.52], 2, "HDR60", "TP", False, False),
}


def test_P1_frozen_constants():
    assert P9.END == P9.DB_UPTO == P9.POST9_POST_DATE == "2026-09-23"
    assert P9.POST9_LOG_NO == "224421214462" and P9.LEDGER_COMMIT == "30aed89" and P9.PROG_VER is None
    assert P9.BOUNDARY == "2026-09-14" and P9.WIN_START == "2026-08-07" and P9.SWEEP_D1 == "2026-09-28 15:35:00"
    assert (P9.THR_MAIN, P9.THR_SENS, P9.SEED, P9.NREP) == (P8.THR_MAIN, P8.THR_SENS, P8.SEED, P8.NREP)
    assert P9.CLOSED_BY_DECISION4 is P8.CLOSED_BY_DECISION4
    assert P9.END != P8.END                                       # 🔴 대칭 — 창이 post8 에서 전진했다


def test_P2_targets_match_intake_and_ledger():
    got = {t[NM]: tuple(t[1:]) for t in P9.TARGETS}
    assert got == INTAKE
    rows = [r for r in csv.DictReader(open(BASE / "ledger_legs.csv", encoding="utf-8"))
            if r["post_log_no"] == P9.POST9_LOG_NO]
    assert len(rows) == 23
    for nm in list(INTAKE) + ["우리기술"]:
        led = [float(r["ret_pct"]) for r in sorted((r for r in rows if r["stock_name"] == nm),
                                                   key=lambda r: int(r["leg_idx"]))]
        exp = INTAKE[nm][3] if nm in INTAKE else P9.FOLLOWUPS[0][4]
        assert led == exp, nm
    assert all(t[CODE] != "032820" for t in P9.TARGETS)           # 후속 = 등록일 축 밖(PD-2 2)
    assert P9.FOLLOWUPS[0][3] == dict((t[NM], t[LEGS]) for t in P8.TARGETS)["우리기술"]
    assert [3.80, 3.79, 3.80] != INTAKE["한국첨단소재"][3]           # 대칭 — 흔든 사본은 불일치
    tr = {r["stock_name"]: r for r in csv.DictReader(open(BASE / "ledger_trades.csv", encoding="utf-8"))
          if r["post_log_no"] == P9.POST9_LOG_NO}
    for nm, exp in INTAKE.items():
        assert tr[nm]["reg_date"] == exp[1] and tr[nm]["reg_date_precision"] == "exact"
        assert (tr[nm]["fill_level"] == "first_only") == exp[7] and int(tr[nm]["fill_n"]) == exp[4]
    assert tr["우리기술"]["reg_date"] == "" and tr["우리기술"]["reg_date_precision"] == "none"


def test_P3_denominators():
    T = P9.TARGETS
    assert [t[NM] for t in T if t[PREC] != "exact"] == []
    assert sorted(t[NM] for t in T if t[FO]) == sorted(["삼미금속", "에스투더블유", "빛샘전자"])
    assert sorted(t[NM] for t in T if t[TR] >= 2) == sorted(["한국첨단소재", "한컴위드"])
    assert not any(t[REENT] for t in T)
    y1 = [t[NM] for t in T if len(t[LEGS]) >= 4]
    assert sorted(y1) == sorted(["삼미금속", "빛샘전자"]) and len(y1) < 3   # REC-Y1 최소 n 미달
    assert not P8.d3_hit(3, len(y1), len(y1)) and P8.d3_hit(3, 2, 3)       # 대칭 — 가드는 살아 있다
    assert sorted(t[NM] for t in T if t[FO] and len(set(t[LEGS])) >= 3) == sorted(["삼미금속", "빛샘전자"])
    assert [t[NM] for t in T if t[FO] and len(t[LEGS]) == 3] == []


def test_P4_inherited_objects():
    for fn in ("core", "win_stats", "d19_start", "stamp_resolve", "d3_hit", "gc_status", "re_dep_status", "raw_key",
               "a_y1", "a_y2", "a_y3", "a_y4", "a_z1", "a_z2", "a_z3", "a_z4", "a_q1r3", "a_hdr", "a_r1", "pct"):
        assert getattr(P9, fn) is getattr(P8, fn), fn
    for fn in ("feasible_pointwise", "iv_max", "iv_measure", "iv_min", "min_residual", "sigma20"):
        assert getattr(P9, fn) is getattr(P5M, fn), fn
    for fn in ("dd_h", "fmt_pct", "med", "win_bars"):
        assert getattr(P9, fn) is getattr(P6M, fn), fn
    defs = re.findall(r"^def (\w+)", SRC, re.M)
    assert defs == ["say", "note", "win5_count", "win_line", "main"]
    assert P9.win5_count is not P8.win5_count                      # 🔴 이탈 자기신고 대상(창 종료 인자 사본)


def test_P5_stamp_file():
    assert P9.STAMP == BASE / "reconstruct_post9" / "query_stamp.json"
    disk = json.loads(P9.STAMP.read_text(encoding="utf-8"))
    assert set(disk) == {"fingerprint", "first_query_kst"}          # runs_kst 누적 없음(post8 정정 1차 교훈)
    assert disk["fingerprint"]["win"] == "2026-08-07~2026-09-23"
    assert disk["first_query_kst"] in NUMBERS.read_text(encoding="utf-8")   # 같은 문자열 인쇄


def test_P6_source_hygiene():
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", SRC, re.M)
    allow = {"__future__", "json", "sys", "pathlib", "psycopg2", "reconstruct_prices", "run_tests",
             "run_reconstruct_post4", "run_reconstruct_post5", "run_reconstruct_post6", "run_reconstruct_post7",
             "run_reconstruct_post8"}
    assert not [m for m in imports if m.split(".")[0] not in allow]
    assert not re.search("adj_" r"factor\s*[*/]|[*/]\s*adj_" r"factor", SRC)
    sqls = re.findall(r'"\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b', SRC, re.I)
    assert sqls and all(s.upper() == "SELECT" for s in sqls)
    assert SRC.count("write_text") == 2 and "STAMP.write_text" in SRC


@pytest.fixture(scope="module")
def numbers():
    if not NUMBERS.exists():
        pytest.fail("RESULTS_RECONSTRUCT_POST9_NUMBERS.md 가 없다 — 스크립트를 먼저 돌려야 한다")
    return NUMBERS.read_text(encoding="utf-8")


def test_P7_print_obligations(numbers):
    t = numbers
    head = t.splitlines()[:6]
    assert t.startswith("# RESULTS_RECONSTRUCT_POST9_NUMBERS — 기계 생성 (수정 금지)")
    assert any("창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1"
               in ln for ln in head)
    assert any(re.search(r"실행 시 `max\(date\)` = 2026-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", ln)
               for ln in head)
    assert any("이 검정의 산출물은 **기록**이지 전략 후보가 아니다" in ln and "PREREG_POST9.md` §0-1" in ln for ln in head)
    assert re.search(r"\| D-9 ① 쿼리 실행 시각\(KST\) \| \*\*2026-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\+09:00\*\*", t)
    assert "D-9 ② 창 구간 `max(daily_prices.updated_at)`" in t
    assert "**09-23 봉은 D+1(09-28) sweep 이후 읽음**" in t
    assert re.search(r"창 구간 `min\(updated_at\)` = 2026-\S+ \S+ ≥ 2026-09-28 15:35: (예|아니오)", t)
    cross = re.findall(r"^- .+: \*「창 `\[\S+, \S+\]` 은 제도 경계 2026-09-14 를 걸친다 — "
                       r"경계 전 `\d+` 봉 / 후 `\d+` 봉 · 혼합 빈티지」\*$", t, re.M)
    assert len(cross) == 5                                        # [D, END] 2 + [D−19, D] 3 (PD-27 (바))
    assert len(re.findall(r"^- .+: \*「창 `\[\S+, \S+\]` 은 전부 제도 경계 후\(전 0 / 후 \d+\)」\*$", t, re.M)) == 3
    assert t.count("`[D−19, D]`(POST8 :546)") == 5 and t.count("`[D, END]`(ANC §2-1)") == 5
    assert "**「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 2 / `approx` 포함 분모 2」**" in t
    assert "**`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)**" in t
    d5 = re.findall(r"^\| `(?:REC-[YZ]\d|Q1-R3|HDR-D1|P6-R1')`[^|]* \| [^|]*\(#\d+[^|]*\) \| [^|]+ \| \d+ \| ", t, re.M)
    assert len(d5) == 12 * 3                                      # 12 항목 × (주 · 재진입 항등 · 절단 항등)
    assert P9.CORP_NOTE in t and "**감시 줄**" in t
    assert not re.search(r"GT-[A-F]|충족·참고용|조건 미달|낡음\(재실행 금지\)", t)   # 등급 이름 0(§6 단계)
    assert "「정규장만」 갈래는 열지 않는다" in t and "`adj_factor` 산술 **0**" in t


def test_P8_verdict_snapshot(numbers):
    t = numbers
    for s in ("⇒ **`REC-Y1` = 최소 n 미달(2 < 3)**",
              "- ⇒ **`REC-Y2` = 구분 대상 있음(빛샘전자)**",
              "해 0개(정확법 · `exact` 5건): **3/5 = 60.0%** (삼미금속, 한국첨단소재, 한컴위드)",
              "- ⇒ **net 으로 설명 안 됨 — gross 3/5 · net 3/5**",
              "`Δr_min` < `res` 인 건 **2/5 = 40.0%** · 문턱 **>= 1/3 = 33.3%** ⇒ **✅ 성립**",
              "**`REC-Z3` = 5/5 = 100.0%**",
              "두 문턱에서 분류가 갈리는 건: **0건**",
              "`first_only` **측정 가능 2 < 3**",
              "🔴🔴 **`HDR-D1` 무효**",
              "`full` 1 < 2 ⇒ ⛔ **판정 안 함 · 관측만.**",
              "🔴 **「갈렸다」 항목: 0개**",
              "🔴 **§1-5 「재진입 의존」 항목: 0개**"):
        assert s in t, s
    assert "**`REC-Z3` = 4/5" not in t                               # 대칭 — 스냅샷 검사가 값에 반응한다


def test_P9_rerun_byte_identical(tmp_path):
    """임시 폴더로 출력·stamp 를 돌려 같은 바이트가 나오는지 본다(저장소 파일은 건드리지 않는다)."""
    try:
        import psycopg2
        from run_tests import DSN
        psycopg2.connect(**DSN).close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DB 접속 불가 — {e}")
    st = tmp_path / "query_stamp.json"
    shutil.copy(P9.STAMP, st)
    before = st.read_bytes()
    saved = (P9.BASE, P9.STAMP)
    P9.BASE, P9.STAMP = tmp_path, st
    P9.OUT.clear()
    try:
        assert P9.main() == 0
    finally:
        P9.BASE, P9.STAMP = saved
        P9.OUT.clear()
    if st.read_bytes() != before:
        pytest.skip("DB 지문 이동(다음 sweep) — byte 비교 불가(규칙 귀결 · 결함 아님)")
    assert (tmp_path / NUMBERS.name).read_bytes() == NUMBERS.read_bytes()


def test_R1_post8_guard_suite_still_passes():
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "test_post8_reconstruct.py", "-q",
                        "-p", "no:cacheprovider"], cwd=str(BASE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0 and " passed" in r.stdout, r.stdout[-2000:]


def test_R2_prior_files_untouched():
    paths = ["run_reconstruct_post4.py", "run_reconstruct_post4_exact.py", "run_reconstruct_post5.py",
             "run_reconstruct_post6.py", "run_reconstruct_post7.py", "run_reconstruct_post8.py", "reconstruct_prices.py",
             "RESULTS_RECONSTRUCT_POST7_NUMBERS.md", "RESULTS_RECONSTRUCT_POST8_NUMBERS.md", "RESULTS_RECONSTRUCT_POST8.md",
             "reconstruct_post8/query_stamp.json", "test_post8_reconstruct.py", "test_post7_reconstruct.py"]
    r = subprocess.run(["git", "diff", "--quiet", BASE_REF, "--"] + paths, cwd=str(BASE))
    assert r.returncode == 0                                       # 작업트리 = 30aed89
    r2 = subprocess.run(["git", "cat-file", "-e", f"{BASE_REF}:./run_reconstruct_post9.py"], cwd=str(BASE),
                        capture_output=True)
    assert r2.returncode != 0                                      # 대칭 — 기준 ref 엔 post9 판이 없다(검사력)
