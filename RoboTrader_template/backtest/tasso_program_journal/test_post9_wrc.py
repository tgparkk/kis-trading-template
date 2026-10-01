# -*- coding: utf-8 -*-
"""`run_wrc_post9.py` 시험 — 판정값 스냅샷 · 재실행 byte 동일 · PREREG_POST9 인쇄 줄 존재 (post8 판 구조 승계 · 짧게)."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_WRC_POST9_NUMBERS.md"


def _snapshot_moved(stamp_dir, db_upto):
    """DB 지문이 `{stamp_dir}/read_stamp.json` 과 다르면 True — 재실행하면 산출물이 새 스냅샷으로 «덮어써지므로» 시험은 재실행하지 않는다."""
    import psycopg2
    from run_tests import DSN
    fp = json.loads((BASE / stamp_dir / "read_stamp.json").read_text(encoding="utf-8"))["fingerprint"]
    conn = psycopg2.connect(**DSN)
    try:
        cur = conn.cursor()
        cur.execute("SELECT max(date) FROM daily_prices")
        mx = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (mx,))
        mx_rows = int(cur.fetchone()[0])
        cur.execute("SELECT count(*), max(updated_at) FROM daily_prices WHERE date = %s", (db_upto,))
        end_rows, end_max = cur.fetchone()
    finally:
        conn.close()
    cur_fp = (str(mx), mx_rows, int(end_rows), str(end_max))
    return cur_fp != (fp["max_date"], fp["max_rows"], fp["end_rows"], fp["end_max_u"])


def _md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def test_rerun_byte_identical():
    import pytest
    if _snapshot_moved("wrc_post9", "2026-09-23"):
        pytest.skip("DB 지문 이동(다음 sweep) — byte 재현은 같은 스냅샷 안에서만 성립 · 재실행하면 산출물이 덮어써진다")
    before = _md5(NUM)
    subprocess.run([sys.executable, "-X", "utf8", str(BASE / "run_wrc_post9.py")], cwd=BASE, check=True,
                   capture_output=True)
    assert _md5(NUM) == before


def test_verdict_snapshot():
    g = json.loads((BASE / "wrc_post9" / "gate.json").read_text(encoding="utf-8"))
    cum = g["cumulative"]
    assert (cum["n"], cum["db_absent"] + cum["empty"], cum["fire"]) == (5, 4, True)
    assert g["one_post"]["n"] == 0 and g["solo_post9"] == 0
    t = NUM.read_text(encoding="utf-8")
    assert "⛔ **판정 불가(`WRC-G1` 발동)**" in t
    assert "🟢 **갈리지 않는다**" in t


def test_p9_lines_present():
    t = NUM.read_text(encoding="utf-8")
    assert "창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1" in t
    assert re.search(r"실행 시 `max\(date\)` = \d{4}-\d{2}-\d{2} · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", t)
    live = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").split("\n")[38]
    assert "> " + live in t                              # §0-1 문언 축자
    # P9-WRC누적분모 — 누적·한 글 두 행 + 갈림 줄 · 판정 칸 사유는 누적만
    assert "| `WRC-G1` | 🔒 **누적**" in t and "| `WRC-G1` | 한 글(" in t
    assert "`P9-WRC누적분모` 갈림: 누적 4/5 = 80.0% 발동 ↔ 한 글 분모 0 · 판정 = 누적" in t
    g1_row = next(ln for ln in t.split("\n") if ln.startswith("| `WRC-G1` | (커버리지)"))
    assert "누적 4/5" in g1_row and "한 글" not in g1_row
    assert "`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음" in t
    assert "수준(행/글): " in t and "`missing`: 19/2" in t and "SSOT = 행(`PREREG_POST9.md` §4)" in t
    assert "부호 갈림 검사: 통계량 정의 없음(기록만)" in t
    assert "`git merge-base --is-ancestor 88afe62 58833f0` = **참**" in t
    assert "(나)3 기계 검사 세 조건 전부 참" in t


def test_no_adj_factor_arithmetic():
    src = (BASE / "run_wrc_post9.py").read_text(encoding="utf-8")
    assert "adj_factor" not in "".join(re.findall(r'"SELECT[^"]*"', src))
