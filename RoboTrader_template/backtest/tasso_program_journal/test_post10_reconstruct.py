# -*- coding: utf-8 -*-
"""`run_reconstruct_post10.py` 가드 시험 — post9 판(`test_post9_reconstruct.py`) 구조 승계 · 짧게.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* · *가드를 시험하지 않으면 그것도 장식이다*.

실행: `python -m pytest test_post10_reconstruct.py -q -p no:cacheprovider`
      (라이브 트리 import 0건 · DB SELECT 뿐 — 재실행 출력은 **임시 폴더**에만 쓴다 · DB 불가 또는 지문 이동이면 skip)
🔴 옛 회차 시험(`test_post8_*`·`test_post9_*`)과 옛 러너는 실행하지 않는다(sweep 뒤 재실행이 옛 NUMBERS 를 덮어쓴다 — 09-30 사고).

  P1 동결 상수(창 종료 10-02 = 발행 당일 · logNo · 제도 경계 · D+1 sweep · REC-Z5 · 시드 = post8 값)
  P2 `TARGETS` = `INTAKE_2026-10-04_post10.md` §1 신규 9건 · 레그 = 원장 post10 행 · 후속 3 = TARGETS 밖(대칭: 흔든 사본 불일치)
  P3 분모 — exact 9 · approx 0 · first_only 5 · 다차수 4 · 재진입 4(항등 아님) · 레그≥4 4(「샌즈 제외」 3 · 재진입 제외 4) · Z4 관행 2
  P4 승계 — 판정 함수·통계 핵 = post8/post5/post6 «같은 객체» · 새 함수 = 선언 목록
  P5 D-9 ① 도장 — `read_stamp.json` 키 3개(`first_read_kst`·`timezone`·`fingerprint`) · `query_stamp.json` 금지
  P6 소스 위생 — import 허용 목록 · SELECT 뿐 · `adj_factor` 산술 0 · 쓰기 2곳 · HDR-D1 계산 0(`a_hdr` import 0)
  P7 산출물 인쇄 의무 — 머리 3줄 · D-9 ①~④ · 걸침/전부후/전부전 · D-3 · P9-공통독법 · D-5 44행 · F-3 신고 줄 · F-5 종결 줄 · 감시 줄 · 등급 이름 0
  P8 판정값 스냅샷(이 회차 값 — 바뀌면 재검수 대상)
  P9 재실행 byte 동일(임시 폴더) · P10 원장 게이트가 문다 · R2 post4~9 파일 무변경(기준 `8e014ca`)
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import run_reconstruct_post5 as P5M
import run_reconstruct_post6 as P6M
import run_reconstruct_post8 as P8
import run_reconstruct_post9 as P9
import run_reconstruct_post10 as P10

BASE = Path(__file__).resolve().parent
SRC = (BASE / "run_reconstruct_post10.py").read_text(encoding="utf-8")
NUMBERS = BASE / P10.OUT_NAME
BASE_REF = "8e014ca"   # 원장·산출물 «이전» 커밋 — HEAD 비교는 검사력 0
NM, CODE, D0, PREC, LEGS, TR, PRESET, LABEL, FO, REENT = range(10)

INTAKE = {  # INTAKE_2026-10-04_post10.md §1 · 테스트 쪽 독립 사본 (코드, 등록일, 정밀도, 레그, 차수, 프리셋, 라벨, fo, 재진입)
    "라온시큐어": ("042510", "2026-09-15", "exact", [12.78, 9.52, 6.40, 2.33, 0.32, -0.49], 4, "HDR60", "MIX", False, False),
    "범한퓨얼셀": ("382900", "2026-09-16", "exact", [7.79, 0.38], 1, "HDR60", "TP", True, True),
    "서산": ("079650", "2026-09-09", "exact", [3.01, 0.38], 5, "QRT", "TP", False, True),
    "샌즈랩": ("411080", "2026-09-14", "exact", [5.24, 4.88, 0.29, -0.02], 3, "HDR60", "MIX", False, False),
    "성호전자": ("043260", "2026-09-14", "exact", [26.39, 17.92, 13.71, 9.28], 1, "HDR60", "TP", True, False),
    "HT로보틱스": ("396300", "2026-09-18", "exact", [16.93, 12.36, 7.65, 7.63, 7.62], 3, "HDR60", "TP", False, False),
    "한켐": ("457370", "2026-09-16", "exact", [10.37], 1, "HDR60", "TP", True, True),
    "뷰노": ("338220", "2026-09-29", "exact", [15.63, 2.18], 1, "HDR60", "TP", True, False),
    "우리로": ("046970", "2026-09-18", "exact", [19.47, 15.44, 11.58], 1, "HDR60", "TP", True, True),
}


def test_P1_frozen_constants():
    assert P10.END == P10.DB_UPTO == P10.POST10_POST_DATE == "2026-10-02"
    assert P10.POST10_LOG_NO == "224429747319" and P10.PROG_VER is None
    assert P10.BOUNDARY == "2026-09-14" and P10.WIN_START == "2026-08-12" and P10.SWEEP_D1 == "2026-10-06 15:35:00"
    assert (P10.THR_MAIN, P10.THR_SENS, P10.SEED, P10.NREP) == (P8.THR_MAIN, P8.THR_SENS, P8.SEED, P8.NREP)
    assert P10.CLOSED_BY_DECISION4 is P8.CLOSED_BY_DECISION4
    assert P10.END != P9.END                                      # 🔴 대칭 — 창이 post9 에서 전진했다
    assert P10.STAMP == BASE / "reconstruct_post10" / "read_stamp.json"


def test_P2_targets_match_intake_and_ledger():
    got = {t[NM]: tuple(t[1:]) for t in P10.TARGETS}
    assert got == INTAKE and len(P10.TARGETS) == 9
    rows = [r for r in csv.DictReader(open(BASE / "ledger_legs.csv", encoding="utf-8"))
            if r["post_log_no"] == P10.POST10_LOG_NO]
    assert len(rows) == 34
    for nm in INTAKE:
        led = [float(r["ret_pct"]) for r in sorted((r for r in rows if r["stock_name"] == nm),
                                                   key=lambda r: int(r["leg_idx"]))]
        assert led == INTAKE[nm][3], nm
    for nm, _code, _why, _lp, lc in P10.FOLLOWUPS:
        led = [float(r["ret_pct"]) for r in sorted((r for r in rows if r["stock_name"] == nm),
                                                   key=lambda r: int(r["leg_idx"]))]
        assert led == lc, nm
    assert {f[0] for f in P10.FOLLOWUPS} == {"한컴위드", "코데즈컴바인", "빛샘전자"}
    assert not {f[1] for f in P10.FOLLOWUPS} & {t[CODE] for t in P10.TARGETS}   # 후속 = 등록일 축 밖(PD-2 2)
    shaken = list(INTAKE["라온시큐어"][3])
    shaken[-1] = -0.48
    assert shaken != [float(r["ret_pct"]) for r in rows if r["stock_name"] == "라온시큐어"]   # 대칭 — 흔든 사본은 불일치
    tr = {r["stock_name"]: r for r in csv.DictReader(open(BASE / "ledger_trades.csv", encoding="utf-8"))
          if r["post_log_no"] == P10.POST10_LOG_NO}
    for nm, exp in INTAKE.items():
        assert tr[nm]["reg_date"] == exp[1] and tr[nm]["reg_date_precision"] == "exact"
        assert (tr[nm]["fill_level"] == "first_only") == exp[7] and int(tr[nm]["fill_n"]) == exp[4]
    for nm, *_ in P10.FOLLOWUPS:
        assert tr[nm]["reg_date"] == "" and tr[nm]["reg_date_precision"] == "none"


def test_P3_denominators():
    T = P10.TARGETS
    assert [t[NM] for t in T if t[PREC] != "exact"] == []
    assert sorted(t[NM] for t in T if t[FO]) == sorted(["범한퓨얼셀", "성호전자", "한켐", "뷰노", "우리로"])
    assert sorted(t[NM] for t in T if t[TR] >= 2) == sorted(["라온시큐어", "서산", "샌즈랩", "HT로보틱스"])
    assert sorted(t[NM] for t in T if t[REENT]) == sorted(["범한퓨얼셀", "서산", "한켐", "우리로"])
    y1 = [t[NM] for t in T if len(t[LEGS]) >= 4]
    assert sorted(y1) == sorted(["라온시큐어", "샌즈랩", "성호전자", "HT로보틱스"]) and len(y1) >= 3   # 열림 예고
    assert len([n for n in y1 if n != "샌즈랩"]) == 3                                              # 「샌즈 제외」 3
    assert len([t for t in T if not t[REENT] and len(t[LEGS]) >= 4]) == 4                        # 재진입 제외 4
    assert not P8.d3_hit(3, len(y1), len(y1)) and P8.d3_hit(3, 2, 3)                             # 대칭 — 가드는 살아 있다
    assert sorted(t[NM] for t in T if t[FO] and len(set(t[LEGS])) >= 3) == sorted(["성호전자", "우리로"])
    assert [t[NM] for t in T if t[FO] and len(t[LEGS]) == 3] == ["우리로"]
    assert sum(1 for t in T if t[REENT]) == 4 and len(T) - 4 == 5                                  # 재진입 갈래 9 ↔ 5(항등 아님)


def test_P4_inherited_objects():
    for fn in ("core", "win_stats", "d19_start", "d3_hit", "gc_status", "re_dep_status", "raw_key",
               "a_y1", "a_y2", "a_y3", "a_y4", "a_z1", "a_z2", "a_z3", "a_z4", "a_q1r3", "a_r1", "pct"):
        assert getattr(P10, fn) is getattr(P8, fn), fn
    for fn in ("feasible_pointwise", "iv_max", "iv_measure", "iv_min", "min_residual", "sigma20"):
        assert getattr(P10, fn) is getattr(P5M, fn), fn
    for fn in ("dd_h", "fmt_pct", "med", "win_bars"):
        assert getattr(P10, fn) is getattr(P6M, fn), fn
    defs = re.findall(r"^def (\w+)", SRC, re.M)
    assert defs == ["say", "note", "win5_count", "win_line", "read_stamp_resolve", "ledger_gate", "ledger_match",
                    "corp_scan", "main"]
    assert P10.win5_count is not P8.win5_count                     # 🔴 이탈 자기신고 대상(창 종료 인자 사본)
    assert "a_hdr" not in SRC.replace("`a_hdr`", "")               # 🔴 `HDR-D1` 계산 0 — 함수를 부르지 않는다


def test_P5_stamp_file():
    disk = json.loads(P10.STAMP.read_text(encoding="utf-8"))
    assert set(disk) == {"fingerprint", "first_read_kst", "timezone"}      # 키 통일(PD-35) · `runs_kst` 누적 없음
    assert disk["fingerprint"]["win"] == "2026-08-12~2026-10-02"
    assert disk["first_read_kst"] in NUMBERS.read_text(encoding="utf-8")   # 같은 문자열 인쇄
    assert not (BASE / "reconstruct_post10" / "query_stamp.json").exists()  # 옛 키·옛 파일명 금지
    # 대칭 — 같은 지문이면 재사용 · 다르면 새 시각
    same, ch1 = P10.read_stamp_resolve(disk, disk["fingerprint"], "X", "tz")
    assert not ch1 and same["first_read_kst"] == disk["first_read_kst"]
    diff, ch2 = P10.read_stamp_resolve(disk, dict(disk["fingerprint"], n=-1), "X", "tz")
    assert ch2 and diff["first_read_kst"] == "X"


def test_P6_source_hygiene():
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", SRC, re.M)
    allow = {"__future__", "csv", "json", "subprocess", "sys", "pathlib", "psycopg2", "reconstruct_prices", "run_tests",
             "run_reconstruct_post4", "run_reconstruct_post5", "run_reconstruct_post6", "run_reconstruct_post7",
             "run_reconstruct_post8", "run_reconstruct_post9"}
    assert not [m for m in imports if m.split(".")[0] not in allow]
    assert not re.search("adj_" r"factor\s*[*/]|[*/]\s*adj_" r"factor", SRC)
    sqls = re.findall(r'"\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|SHOW)\b', SRC, re.I)
    assert sqls and all(s.upper() in ("SELECT", "SHOW") for s in sqls)
    assert SRC.count("write_text") == 2 and "STAMP.write_text" in SRC and "(BASE / OUT_NAME).write_text" in SRC
    assert 'subprocess.run(["git", "diff", "--quiet"' in SRC        # 읽기 전용 git 조회만
    assert not re.search(r'"git",\s*"(add|commit|stash|checkout|reset)', SRC)


@pytest.fixture(scope="module")
def numbers():
    if not NUMBERS.exists():
        pytest.fail("RESULTS_RECONSTRUCT_POST10_NUMBERS.md 가 없다 — 스크립트를 먼저 돌려야 한다")
    return NUMBERS.read_text(encoding="utf-8")


def test_P7_print_obligations(numbers):
    t = numbers
    head = t.splitlines()[:6]
    assert t.startswith("# RESULTS_RECONSTRUCT_POST10_NUMBERS — 기계 생성 (수정 금지)")
    assert any("창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1"
               in ln for ln in head)
    assert any(re.search(r"실행 시 `max\(date\)` = 2026-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", ln)
               for ln in head)
    assert any("이 검정의 산출물은 **기록**이지 전략 후보가 아니다" in ln and "PREREG_POST10.md" in ln for ln in head)
    assert re.search(r"\| D-9 ① 쿼리 실행 시각\(KST\) \| \*\*2026-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\+09:00\*\* \(`timezone` = Asia/Seoul", t)
    assert "D-9 ② 창 구간 `max(daily_prices.updated_at)`" in t
    assert "**10-02 봉은 D+1(10-06) sweep 이후 읽음**" in t
    assert re.search(r"창 구간 `min\(updated_at\)` = 2026-\S+ \S+ ≥ 2026-10-06 15:35: (예|아니오)", t)
    cross = re.findall(r"^- .+: \*「창 `\[\S+, \S+\]` 은 제도 경계 2026-09-14 를 걸친다 — "
                       r"경계 전 `\d+` 봉 / 후 `\d+` 봉 · 혼합 빈티지」\*$", t, re.M)
    assert len(cross) == 9                                        # `[D−19, D]` 8 + `[D, END]` 1(서산) — 브리프 A-1
    assert sum(1 for c in cross if c.startswith("- 서산 `[D, END]`")) == 1
    assert len(re.findall(r"^- .+: \*「창 `\[\S+, \S+\]` 은 전부 제도 경계 후\(전 0 / 후 \d+\)」\*$", t, re.M)) == 8
    assert "`[D−19, D]` 걸침 8줄 (" in t and "「전부 경계 전」 1줄 (서산)" in t   # `D-9` 추가 줄 — 서산 전부 경계 전
    assert t.count("`[D−19, D]`(POST8 :546)") == 9 and t.count("`[D, END]`(ANC §2-1)") == 9
    assert "**「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 4 / `approx` 포함 분모 4」**" in t
    assert "**`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)**" in t
    d5 = re.findall(r"^\| `(?:REC-[YZ]\d|Q1-R3|P6-R1')`[^|]* \| [^|]*\(#\d+[^|]*\) \| [^|]+ \| \d+ \| ", t, re.M)
    assert len(d5) == 11 * 4                                      # 11 항목 × (주 · 재진입 · 샌즈 · 절단)
    assert not re.search(r"^\| `HDR-D1`", t, re.M)                # 🔴 종결 — 갈래 표에 없다
    assert re.search(r"`P10-기업행위봉`: 기업행위 건 \d+/9 — .+ · `adj_factor` 산술 0 · 처리 = \(나\)", t)   # F-3 신고 줄(k=0 이어도)
    assert t.count("답(참고) · 세지 않는다") >= 11                  # 「기업행위 건 제외」 값 의무 인쇄
    assert "해당 없음 — 🔒 종결(2026-10-01 폐기 접수 · `PREREG_ANCHOR_REDESIGN.md:253` · 기록 보존) — 핵심 수: 계산 0회" in t
    assert "귀결 대상 종결(`F-5`)" in t and "`REC-Z3` 제도 경계 분리 조항 없음" in t
    assert "**감시 줄**" in t and "`P6-PRIOR_CYCLE_IN_WINDOW` = **4/9**" in t
    assert not re.search(r"GT-[A-F]|충족·참고용|조건 미달|낡음\(재실행 금지\)", t)   # 등급 이름 0(§6 단계)
    assert "「정규장만」 갈래는 열지 않는다" in t and "`adj_factor` 산술 **0**" in t
    sec12 = t.split("## §12.")[1].split("## §13.")[0]
    assert not re.search(r"\d\.\d{3}", sec12) and "중점 중앙값 **" not in sec12   # §12 에 계산값 0


def test_P8_verdict_snapshot(numbers):
    t = numbers
    for s in ("해 0개(정확법 · `exact` 9건): **4/9 = 44.4%** (라온시큐어, 샌즈랩, 성호전자, HT로보틱스)",
              "⇒ **`REC-Y1` = 판정 불가 — 대상 전건 해 0개(폭 미정의 4/4)**",
              "🆕 **`REC-Y1` 열림 예고 검증**: 레그≥4 exact **4**(예고 4) · 「샌즈 제외」 **3**(예고 3) · 재진입 제외 **4**(예고 4",
              "- ⇒ **`REC-Y2` = 구분 대상 있음(우리로)**",
              "- ⇒ **net 으로 설명 안 됨 — gross 4/9 · net 4/9**",
              "`Δr_min` < `res` 인 건 **1/9 = 11.1%** · 문턱 **>= 1/3 = 33.3%** ⇒ **⛔ 불성립**",
              "**`REC-Z3` = 5/9 = 55.6%**",
              "두 문턱에서 분류가 갈리는 건: **0건**",
              "`REC-Z4` 조건 충족(관측)**: 계수 관행(post8 PD-13 · `first_only` ∧ 서로 다른 값 레그 ≥3) **2건** (성호전자, 우리로)",
              "`full` 1 < 2 ⇒ ⛔ **판정 안 함 · 관측만.**",
              "🔴 **「갈렸다」 항목: 0개**",
              "🔴 **§1-5 「재진입 의존」 항목: 0개**",
              "`P10-기업행위봉`: 기업행위 건 0/9"):
        assert s in t, s
    assert "**`REC-Z3` = 4/9" not in t                              # 대칭 — 스냅샷 검사가 값에 반응한다


def test_P9_rerun_byte_identical(tmp_path):
    """임시 폴더로 출력·stamp 를 돌려 같은 바이트가 나오는지 본다(저장소 파일은 건드리지 않는다)."""
    try:
        import psycopg2
        from run_tests import DSN
        psycopg2.connect(**DSN).close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DB 접속 불가 — {e}")
    st = tmp_path / "read_stamp.json"
    shutil.copy(P10.STAMP, st)
    before = st.read_bytes()
    saved = (P10.BASE, P10.STAMP)
    P10.BASE, P10.STAMP = tmp_path, st
    P10.OUT.clear()
    try:
        assert P10.main() == 0
    finally:
        P10.BASE, P10.STAMP = saved
        P10.OUT.clear()
    if st.read_bytes() != before:
        pytest.skip("DB 지문 이동(다음 sweep) — byte 비교 불가(규칙 귀결 · 결함 아님)")
    assert (tmp_path / NUMBERS.name).read_bytes() == NUMBERS.read_bytes()


def test_P10_ledger_gate_bites(tmp_path, monkeypatch):
    """원장 게이트 — 실제 저장소는 통과 · 행을 뺀 사본은 거부(대칭)."""
    gate, why = P10.ledger_gate()
    assert gate is not None and why is None and len(gate["trades"]) == 12 and len(gate["legs"]) == 34
    assert P10.ledger_match(gate) == []
    bad = dict(gate, legs=[r for r in gate["legs"] if not (r["stock_name"] == "뷰노" and r["leg_idx"] == "2")])
    assert P10.ledger_match(bad) == ["뷰노"]
    monkeypatch.setattr(P10, "LEDGER_BASE", tmp_path)
    shutil.copy(BASE / "ledger_legs.csv", tmp_path / "ledger_legs.csv")
    (tmp_path / "ledger_trades.csv").write_text("post_log_no\n", encoding="utf-8")
    g2, why2 = P10.ledger_gate()
    assert g2 is None and "12" in why2                             # 원장 행이 없으면 거부 → 러너는 「원장 대기」


def test_R2_prior_files_untouched():
    paths = ["run_reconstruct_post4.py", "run_reconstruct_post4_exact.py", "run_reconstruct_post5.py",
             "run_reconstruct_post6.py", "run_reconstruct_post7.py", "run_reconstruct_post8.py",
             "run_reconstruct_post9.py", "reconstruct_prices.py",
             "RESULTS_RECONSTRUCT_POST8_NUMBERS.md", "RESULTS_RECONSTRUCT_POST9_NUMBERS.md", "RESULTS_RECONSTRUCT_POST9.md",
             "reconstruct_post9/query_stamp.json", "test_post9_reconstruct.py", "test_post8_reconstruct.py"]
    r = subprocess.run(["git", "diff", "--quiet", BASE_REF, "--"] + paths, cwd=str(BASE))
    assert r.returncode == 0                                       # 작업트리 = 8e014ca
    r2 = subprocess.run(["git", "cat-file", "-e", f"{BASE_REF}:./run_reconstruct_post10.py"], cwd=str(BASE),
                        capture_output=True)
    assert r2.returncode != 0                                      # 대칭 — 기준 ref 엔 post10 판이 없다(검사력)
