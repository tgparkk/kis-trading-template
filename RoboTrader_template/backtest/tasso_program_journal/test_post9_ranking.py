# -*- coding: utf-8 -*-
"""`run_ranking.py --stage post9` 시험 — 기존 단계 함수 본문 불변(HEAD 대조) · 판정값 스냅샷 · 재실행 byte 동일 · P9 줄."""
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_RANKING_POST9_NUMBERS.md"
REF = "30aed89"   # 원장 기준 커밋 = post9 모드 추가 «전» run_ranking.py


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


def _defs(src):
    tree = ast.parse(src)
    return {n.name: ast.get_source_segment(src, n) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.Assign)) and getattr(n, "name", None)}


def test_existing_stage_functions_unchanged():
    head = subprocess.run(["git", "-C", str(BASE), "show", f"{REF}:./run_ranking.py"], capture_output=True,
                          encoding="utf-8", check=True).stdout
    new = (BASE / "run_ranking.py").read_text(encoding="utf-8")
    old_defs, new_defs = _defs(head), _defs(new)
    for name, body in old_defs.items():
        if name == "main":
            continue
        assert new_defs.get(name) == body, name
    # main: HEAD 본문의 줄은 전부 그대로 남는다(post9 분기·choices 만 덧붙임)
    old_main = [ln for ln in old_defs["main"].split("\n") if "choices=" not in ln]
    new_main = new_defs["main"].split("\n")
    assert all(ln in new_main for ln in old_main)
    assert new.split("\n# ═══ 🆕 post9 단계")[0] == head.split("\ndef main():")[0]   # 앞부분 바이트 동일


def test_rerun_byte_identical():
    import pytest
    if _snapshot_moved("ranking_post9", "2026-09-23"):
        pytest.skip("DB 지문 이동(다음 sweep) — byte 재현은 같은 스냅샷 안에서만 성립 · 재실행하면 산출물이 덮어써진다")
    before = hashlib.md5(NUM.read_bytes()).hexdigest()
    subprocess.run([sys.executable, "-X", "utf8", str(BASE / "run_ranking.py"), "--stage", "post9"], cwd=BASE,
                   check=True, capture_output=True)
    assert hashlib.md5(NUM.read_bytes()).hexdigest() == before


def test_verdict_snapshot_and_p9_lines():
    t = NUM.read_text(encoding="utf-8")
    assert "`p` **0.00000** · `m` **14.0**" in t
    assert "⛔ **「새 정보 없음 = `REG-M4` 재진술」**" in t
    assert "**판정 비율(선택 규칙)** = **0.0%**" in t
    assert "🟢 **갈리지 않는다** ⇒ `RNK-V1` 미발동" in t
    assert "관측 감시 `RNK-N2`(문턱 30)" in t and "문턱까지 **16.0**" in t
    assert "창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함»" in t and "— 기록만(창 아님)" in t
    live = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").split("\n")[38]
    assert "> " + live in t
    assert "`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음" in t
    assert "SSOT = 행(`PREREG_POST9.md` §4)" in t and "부호 갈림 검사: 통계량 정의 없음(기록만)" in t
    assert "`git merge-base --is-ancestor 8d28e14 58833f0` = **참**" in t
