# -*- coding: utf-8 -*-
"""`run_selection_post10.py` 가드 시험 — `test_post9_selection.py` 구조 승계(짧게). DB 접속은 P7(지문 비교)뿐.

  P1  동결 상수 = post8 판과 같은 값(창·문턱·시드) · post10 창 종료 10-02 · sweep 10-06 · 창 시작 08-12
  P2  분모 = 원장 post10 행 중 `exact` 9 (후속 3 = `none` 은 밖) · N1 음성: 정밀도 필터를 빼면 12
  P3  재사용 증명 — post6/7/8 의 «그 함수» 객체(재정의 0) · 옛 스크립트 작업트리 변경 0
  P4  재진입 4/9 상수(PD-3) · 「샌즈 제외」 상수 · 기업행위 창 도우미 순수 함수(음성 포함)
  P5  산출물 의무 줄 — PD-1 두 줄 · `PREREG_POST10.md:56`·`:58` 축자 · `P9-공통독법` · D-3 · D-9 ① = 스탬프 · F-3 신고 줄
  P6  산출물 구조 — `SEL-S3` 기각 유지 문형(음성: 「지지」 행이면 실패) · 재진입 항등 아님 · 걸침 줄 · 「기업행위 건 제외」 답 칸 낱말
  P7  등급 이름 0 · `approx` 갈래 계수 행 0
  P8  재실행 byte 동일(DB SELECT · 같은 지문 ⇒ 같은 스탬프)
실행: `python -m pytest test_post10_selection.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

import run_selection_post6 as P6
import run_selection_post7 as P7
import run_selection_post8 as P8
import run_selection_post10 as P10

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_SELECTION_POST10_NUMBERS.md"
LOG = "224429747319"
VERDICT_WORDS = ("충족", "미달", "지지", "기각", "불성립", "구간 내", "구간 밖", "발동", "✅", "❌")


def _txt():
    assert NUM.exists(), "RESULTS_SELECTION_POST10_NUMBERS.md 가 없다 — run_selection_post10.py 를 먼저 돌린다"
    return NUM.read_text(encoding="utf-8")


def _ledger():
    return [r for r in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]


def _s3_row_ok(row: str) -> bool:
    """`SEL-S3` 판정 칸 가드 — 기각 유지 문형이고 「지지」가 없다(`PREREG_POST10.md` §3 (나)7)."""
    return "기각 유지" in row and "지지" not in row


def _co_cell_ok(cell: str) -> bool:
    """「기업행위 건 제외」 답 칸 가드 — 낱말 「답(참고) · 세지 않는다」 + 판정 낱말 없음(`F-3` (나))."""
    return "답(참고) · 세지 않는다" in cell and not any(w in cell.replace("(참고)", "") for w in VERDICT_WORDS)


def test_P1_constants():
    assert (P10.DB_UPTO, P10.SWEEP_D1, P10.PROBE_WIN) == ("2026-10-02", "2026-10-06 15:35:00", ("2026-08-12", "2026-10-02"))
    for k in ("W_TDAYS", "W_CAL_POST4", "WIN20", "SEED", "UP15", "N_DEGRADE", "DROP_GUARD", "TRUNC_GUARD", "MIN_N",
              "REGIME", "UNIV_LO", "RAW_LO"):
        assert getattr(P10, k) == getattr(P8, k), k
    assert P8.DB_UPTO == "2026-10-02"   # 이 프로세스 안에서만 바꾼 전역(파일 불변은 P3)


def test_P2_denominator_from_ledger():
    rows = _ledger()
    ex = sorted((r["stock_name"], r["reg_date"]) for r in rows if r["reg_date_precision"] == "exact")
    assert ex == sorted((n, d) for n, _c, d in P10.NEW10) and len(ex) == 9
    # N1 (음성): 정밀도 필터를 빼면 후속 3(`none`)이 섞여 12 가 된다 — 필터가 장식이 아니다
    assert len(rows) == 12
    assert sorted(r["stock_name"] for r in rows if r["reg_date_precision"] != "exact") == sorted(n for n, _c, _t in P10.FOLLOW10)
    assert len({d for _n, _c, d in P10.NEW10}) == 6      # 등록일 서로 다른 날 6(INTAKE §5)
    assert P10.NEW9 == [("삼미금속", "012210", "2026-09-04"), ("에스투더블유", "488280", "2026-09-10"),
                        ("빛샘전자", "072950", "2026-09-14"), ("한국첨단소재", "062970", "2026-09-15"),
                        ("한컴위드", "054920", "2026-09-15")]


def test_P3_reuse_and_old_scripts_untouched():
    assert P10.load_ext is P8.load_ext and P10.vintage is P8.vintage and P10.own_split is P8.own_split
    assert P10.feat_table is P6.feat_table and P10.stat_tdays is P6.stat_tdays and P10.win20_bars is P7.win20_bars
    assert P10.prior_flag is P8.prior_flag
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_selection.py", "run_selection_post6.py",
                        "run_selection_post7.py", "run_selection_post8.py", "run_selection_post9.py",
                        "RESULTS_SELECTION_POST9_NUMBERS.md", "RESULTS_SELECTION_POST9.md"], cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def test_P4_reentry_constants_and_helpers():
    assert sorted(P10.REENTRY) == ["046970", "079650", "382900", "457370"]      # 우리로·서산·범한·한켐
    assert sum(P10.PD3_FLAG.values()) == 4 and len(P10.PD3_FLAG) == 9
    assert P10.SANDS == "샌즈랩" and [nm for nm, c, _d in P10.NEW10 if c == "411080"] == ["샌즈랩"]
    # 순수 함수(음성 포함) — 사유 문자열
    assert P10.corp_reason(dict(split=[], vol0=[])) == ""
    assert "ⓐ split 2026-09-01" in P10.corp_reason(dict(split=[("split", "2026-09-01", "")], vol0=[]))
    assert "ⓑ `volume = 0` 2봉(2026-09-01~2026-09-02)" in P10.corp_reason(dict(split=[], vol0=["2026-09-01", "2026-09-02"]))
    # 가드 음성: 「기업행위 건 제외」 답 칸에 판정 낱말이 들어가면 실패
    assert _co_cell_ok("답(참고) · 세지 않는다 — 96.3") and not _co_cell_ok("답(참고) · 세지 않는다 — 충족 96.3")
    assert not _co_cell_ok("96.3")


def test_P5_duty_lines():
    t = _txt()
    pr = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
    assert pr[55] in t.splitlines() and pr[57] in t.splitlines()
    assert "창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · `END` · 전 축(`WRC-` 포함) · PD-1" in t
    assert re.search(r"실행 시 `max\(date\)` = \d{4}-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", t)
    assert t.count("`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)") >= 2
    assert "`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 9 / `approx` 포함 분모 9" in t
    assert "`P9-행단위`·`P9-결측분리`: 해당 없음" in t and "10-02 봉은 D+1(10-06) sweep 이후 읽음" in t
    st = json.loads((BASE / "selection_post10" / "read_stamp.json").read_text(encoding="utf-8"))
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"}
    assert f"D-9 ① 쿼리 실행 시각(KST) = {st['first_read_kst']}" in t and st["first_read_kst"] >= P10.SWEEP_D1[:19]
    # F-3 신고 줄(k = 0 이어도) + 재등록 날짜 기록
    assert re.search(r"`P10-기업행위봉`: 기업행위 건 \d+/9 — .+ · `adj_factor` 산술 0 · 처리 = \(나\)", t)
    assert "재등록(샌즈랩 9/29 · 한컴위드 9/23) 날짜 기록" in t
    assert "\r" not in t


def test_P6_structure():
    t = _txt()
    s12 = t.split("## §12.")[1].split("### 12-1.")[0]
    s3 = [ln for ln in s12.splitlines() if ln.startswith("| 5 | `SEL-S3`")]
    assert len(s3) == 1 and _s3_row_ok(s3[0]), s3
    assert not _s3_row_ok("| 5 | `SEL-S3` | ✅ **지지** |") and not _s3_row_ok("| 5 | `SEL-S3` | ❌ **기각** |")   # 음성
    assert any(ln.startswith("| 1 | `SEL-S1`") and "기각 유지" in ln for ln in s12.splitlines())
    # 재진입 갈래 = 항등 아님(9 ↔ 5) · P6-PRIOR_CYCLE_IN_WINDOW 4/9
    assert "**`P6-PRIOR_CYCLE_IN_WINDOW` = 1 인 건 4/9**" in t or "= 1 인 건 4/9" in t
    s10 = t.split("## §10.")[1].split("## §11.")[0]
    assert re.search(r"\| §1-5 재진입 포함↔제외 \| 9 ↔ 5 \|", s10) and "| **항등**(재진입 0)" not in s10
    # D-5 세 쪽: 모든 데이터 행이 (갈래, n, 답, 계수) 네 칸 + 「기업행위 건 제외」 답 칸 가드
    rows = [ln for ln in s10.splitlines() if ln.startswith("| `")]
    assert rows and all(len([x for x in ln.split("|")]) == 7 for ln in rows)
    co = [ln for ln in rows if "「기업행위 건 제외」" in ln]
    assert len(co) == 6 and all(_co_cell_ok(ln.split("|")[4]) for ln in co), co
    sa = [ln for ln in rows if "「샌즈 제외」" in ln]
    assert len(sa) == 6 and all("인쇄만" in ln and "❌" in ln for ln in sa)
    # D-9: 판정 창 걸침 8 + 적재 창 1 · 서산 전부 경계 전 1줄
    assert len(re.findall(r"창 `\[\d{4}-\d\d-\d\d, \d{4}-\d\d-\d\d\]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 \d+ 봉 / "
                          r"후 \d+ 봉 · 혼합 빈티지 \(", t)) >= 8
    assert len(re.findall(r"은 전부 제도 경계 전\(전 \d+ / 후 0\) \(서산 ", t)) >= 1
    assert "🔴 **아니오 — 배선 결함**" not in t


def test_P7_no_grade_no_approx_count():
    t = _txt()
    assert not re.search(r"\bGT-[A-F]\b", t)
    assert not re.search(r"\| `approx` 포함 조합", t)


def _snapshot_moved():
    """DB 지문(`run_selection_post10::_main` 과 같은 키)이 `selection_post10/read_stamp.json` 과 다르면 True — 그때 재실행은 산출물을 덮어쓴다."""
    import psycopg2
    fp = json.loads((BASE / "selection_post10" / "read_stamp.json").read_text(encoding="utf-8"))["fingerprint"]
    conn = psycopg2.connect(**P10.DSN)
    try:
        cur = conn.cursor()
        v_probe = P10.vintage(cur, *P10.PROBE_WIN)
        v_lane = P10.vintage(cur, P10.RAW_LO, P10.DB_UPTO)
        cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (P10.DB_UPTO,))
        rows_upto = int(cur.fetchone()[0])
        snap_max, snap_rows = P10.snapshot_tail(cur)
    finally:
        conn.close()
    cur_fp = dict(max_date=str(snap_max), max_rows=int(snap_rows), probe=list(P10.PROBE_WIN),
                  probe_min_u=str(v_probe[2]), probe_max_u=str(v_probe[1]), probe_n=int(v_probe[3]),
                  lane=[P10.RAW_LO, P10.DB_UPTO], lane_min_u=str(v_lane[2]), lane_max_u=str(v_lane[1]),
                  lane_n=int(v_lane[3]), end_rows=rows_upto)
    return cur_fp != fp


def test_P8_rerun_byte_identical():
    import pytest
    if _snapshot_moved():
        pytest.skip("DB 지문 이동(다음 sweep) — byte 재현은 같은 스냅샷 안에서만 성립 · 재실행하면 산출물이 덮어써진다")
    before = hashlib.md5(NUM.read_bytes()).hexdigest()
    P10.OUT.clear()
    assert P10.main() == 0
    assert hashlib.md5(NUM.read_bytes()).hexdigest() == before
