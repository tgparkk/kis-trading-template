# -*- coding: utf-8 -*-
"""`run_selection_post9.py` 가드 시험 — `test_post8_selection.py` 구조 승계(짧게).

  P1  동결 상수 = post8 판과 같은 값(창·문턱·시드) · post9 창 종료 09-23 · sweep 09-28
  P2  분모 = 원장 `30aed89` post9 행 중 `exact` 5 (후속 우리기술 `none` 은 밖) · N1 음성: 정밀도 필터를 빼면 6
  P3  재사용 증명 — post6/7/8 의 «그 함수» 객체(재정의 0) · post8 이하 스크립트 작업트리 변경 0
  P4  산출물 의무 줄 — PD-1 두 줄 · `PREREG_POST9.md:39`·`:41` 축자 · `P9-공통독법` 「답 = 판정」 · `P9-행단위` · D-3 · D-9 ① = 스탬프
  P5  판정값 스냅샷(이 회차 값 · 회귀 감지용)
  P6  등급 이름 0 · `approx` 갈래 계수 행 0
  P7  재실행 byte 동일(DB SELECT · 같은 지문 ⇒ 같은 스탬프)
실행: `python -m pytest test_post9_selection.py -q -p no:cacheprovider`
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
import run_selection_post9 as P9

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_SELECTION_POST9_NUMBERS.md"
LOG = "224421214462"


def _txt():
    return NUM.read_text(encoding="utf-8")


def test_P1_constants():
    assert (P9.DB_UPTO, P9.SWEEP_D1, P9.PROBE_WIN) == ("2026-09-23", "2026-09-28 15:35:00", ("2026-08-07", "2026-09-23"))
    for k in ("W_TDAYS", "W_CAL_POST4", "WIN20", "SEED", "UP15", "N_DEGRADE", "DROP_GUARD", "TRUNC_GUARD", "MIN_N",
              "REGIME", "UNIV_LO", "RAW_LO"):
        assert getattr(P9, k) == getattr(P8, k), k
    assert P8.DB_UPTO == "2026-09-23"   # 이 프로세스 안에서만 바꾼 전역(파일 불변은 P3)


def test_P2_denominator_from_ledger():
    rows = [r for r in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]
    ex = sorted((r["stock_name"], r["reg_date"]) for r in rows if r["reg_date_precision"] == "exact")
    assert ex == sorted((n, d) for n, _c, d in P9.NEW9) and len(ex) == 5
    # N1 (음성): 정밀도 필터를 빼면 후속 우리기술(`none`)이 섞여 6 이 된다 — 필터가 장식이 아니다
    assert len(rows) == 6 and [r["stock_name"] for r in rows if r["reg_date_precision"] != "exact"] == ["우리기술"]
    assert [n for n, _c, _t in P9.FOLLOW9] == ["우리기술"]


def test_P3_reuse_and_old_scripts_untouched():
    assert P9.load_ext is P8.load_ext and P9.vintage is P8.vintage and P9.own_split is P8.own_split
    assert P9.feat_table is P6.feat_table and P9.stat_tdays is P6.stat_tdays and P9.win20_bars is P7.win20_bars
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_selection.py", "run_selection_post6.py",
                        "run_selection_post7.py", "run_selection_post8.py", "RESULTS_SELECTION_POST8_NUMBERS.md",
                        "RESULTS_SELECTION_POST8.md"], cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def test_P4_duty_lines():
    t = _txt()
    pr = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").splitlines()
    assert pr[38] in t.splitlines() and pr[40] in t.splitlines()
    assert "창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1" in t
    assert re.search(r"실행 시 `max\(date\)` = \d{4}-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", t)
    assert t.count("`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)") >= 2
    assert "`P9-행단위`: 해당 없음" in t
    assert "`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 5 / `approx` 포함 분모 5" in t
    st = json.loads((BASE / "selection_post9" / "read_stamp.json").read_text(encoding="utf-8"))
    assert f"D-9 ① 쿼리 실행 시각(KST) = {st['first_read_kst']}" in t and "PD-31 신고 줄" in t


def test_P5_verdict_snapshot():
    t = _txt()
    for s in ("| 1 | `SEL-S1` | >= 1/2 · `PREREG_SELECTION.md` §7 | 3 | 3/5 = 60.0% | ❌ **기각 유지**",
              "| 2 | `P6-S1h` | >= 1/2 · `PREREG_SELECTION.md` §7(상속) | 3 | 3/5 = 60.0% | 🟡 **문턱 충족",
              "중앙 64.0 · 범위 [58, 69] · sd(`ddof=1`) 3.94 | 🔴 **발동",
              "| 4 | `SEL-S2` | >= 95 · `PREREG_SELECTION.md` §7 | 3 | 99.5 | ✅ **충족**",
              "| 5 | `SEL-S3` | **< 90** · `PREREG_SELECTION.md` §7 | 3 | 96.3 (분모 5/5) | ❌ **기각**",
              "| 6 | `SEL-S4` | 40~80 · `PREREG_SELECTION.md` §7 | 3 | 56.9 | ✅ **구간 내**",
              "PD-12 예고와 **계산이 일치**", "PD-27 (바) `[D−19, D]` 열(빛샘 19/1 · 첨단 18/2 · 한컴 18/2)과 🟢 일치"):
        assert s in t, s
    assert "🔴 **아니오 — 배선 결함**" not in t


def test_P6_no_grade_no_approx_count():
    t = _txt()
    assert not re.search(r"\bGT-[A-F]\b", t)
    assert not re.search(r"\| `approx` 포함 조합", t)


def _snapshot_moved():
    """DB 지문(`run_selection_post9::_main` 과 같은 키)이 `selection_post9/read_stamp.json` 과 다르면 True — 그때 재실행은 산출물을 덮어쓴다."""
    import psycopg2
    fp = json.loads((BASE / "selection_post9" / "read_stamp.json").read_text(encoding="utf-8"))["fingerprint"]
    conn = psycopg2.connect(**P9.DSN)
    try:
        cur = conn.cursor()
        v_probe = P9.vintage(cur, *P9.PROBE_WIN)
        v_lane = P9.vintage(cur, P9.RAW_LO, P9.DB_UPTO)
        cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (P9.DB_UPTO,))
        rows_upto = int(cur.fetchone()[0])
        snap_max, snap_rows = P9.snapshot_tail(cur)
    finally:
        conn.close()
    cur_fp = dict(max_date=str(snap_max), max_rows=int(snap_rows), probe=list(P9.PROBE_WIN),
                  probe_min_u=str(v_probe[2]), probe_max_u=str(v_probe[1]), probe_n=int(v_probe[3]),
                  lane=[P9.RAW_LO, P9.DB_UPTO], lane_min_u=str(v_lane[2]), lane_max_u=str(v_lane[1]),
                  lane_n=int(v_lane[3]), end_rows=rows_upto)
    return cur_fp != fp


def test_P7_rerun_byte_identical():
    import pytest
    if _snapshot_moved():
        pytest.skip("DB 지문 이동(다음 sweep) — byte 재현은 같은 스냅샷 안에서만 성립 · 재실행하면 산출물이 덮어써진다")
    before = hashlib.md5(NUM.read_bytes()).hexdigest()
    P9.OUT.clear()
    assert P9.main() == 0
    assert hashlib.md5(NUM.read_bytes()).hexdigest() == before
