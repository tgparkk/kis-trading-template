# -*- coding: utf-8 -*-
"""`run_ranking.py --stage post10` 시험 — 기존 코드 불변(HEAD 대조 · 줄 단위) · 재실행 byte 동일 · post10 인쇄 줄 · 변이 음성."""
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_RANKING_POST10_NUMBERS.md"
REF = "8e014ca"   # post10 단계 추가 «전» run_ranking.py(인테이크 정오 1 커밋 · 원장 커밋 전)


def _snapshot_moved(stamp_dir, db_upto):
    """DB 지문이 `{stamp_dir}/read_stamp.json` 과 다르면 True — 재실행하면 산출물이 덮어써지므로 시험은 재실행하지 않는다."""
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


def _only_additions(old: str, new: str) -> bool:
    """기존 줄은 «한 글자도» 안 바뀐다 — 허용 = 순수 삽입 + `choices=` 줄 한 개 교체(`--stage` 선택지에 post10)."""
    ol, nl = old.split("\n"), new.split("\n")
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes():
        if tag == "equal" or tag == "insert":
            continue
        if tag == "replace" and i2 - i1 == 1 and "choices=" in ol[i1]:
            continue
        return False
    return True


def _head():
    return subprocess.run(["git", "-C", str(BASE), "show", f"{REF}:./run_ranking.py"], capture_output=True,
                          encoding="utf-8", check=True).stdout


def _levels_ok(t):
    line = next((ln for ln in t.split("\n") if "수준(행/글):" in ln), None)
    if line is None or "결측 n = " not in t:
        return False
    return "missing" not in line.split("(민감도")[0] and "`missing` " in line


def test_existing_code_unchanged():
    head = _head()
    new = (BASE / "run_ranking.py").read_text(encoding="utf-8")
    assert _only_additions(head, new)
    assert "# ═══ 🆕 post10 단계(덧붙임" in new and "def post10_main(a):" in new
    # post9 단계 본문(post9_main 까지)은 HEAD 와 바이트 동일
    assert head.split("\ndef main():")[0] == new.split("\ndef main():")[0]


def test_mutation_negative_unchanged_guard():
    """변이 음성 — 옛 줄 한 글자를 바꾸면 불변 검사가 실패해야 한다."""
    head = _head()
    new = (BASE / "run_ranking.py").read_text(encoding="utf-8")
    assert _only_additions(head, new)
    bad = new.replace("def p8_cross_counts(conn, windows):", "def p8_cross_counts(conn, windows, x=0):", 1)
    assert bad != new and not _only_additions(head, bad)


def test_rerun_byte_identical():
    import pytest
    if _snapshot_moved("ranking_post10", "2026-10-02"):
        pytest.skip("DB 지문 이동(다음 sweep) — byte 재현은 같은 스냅샷 안에서만 성립 · 재실행하면 산출물이 덮어써진다")
    before = hashlib.md5(NUM.read_bytes()).hexdigest()
    subprocess.run([sys.executable, "-X", "utf8", str(BASE / "run_ranking.py"), "--stage", "post10"], cwd=BASE,
                   check=True, capture_output=True)
    assert hashlib.md5(NUM.read_bytes()).hexdigest() == before


def test_p10_lines_and_verdict_words():
    t = NUM.read_text(encoding="utf-8")
    assert "⛔ **「새 정보 없음 = `REG-M4` 재진술」**" in t
    assert "창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함»" in t and "— 기록만(창 아님)" in t
    assert "라이브 채택 대상이 아니다" in t
    st = json.loads((BASE / "ranking_post10" / "read_stamp.json").read_text(encoding="utf-8"))
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"}
    assert "**" + st["first_read_kst"] + "**" in t
    assert "「2026-10-02 봉은 D+1(2026-10-06) sweep 이후 읽음」" in t and "창 구간 `max(updated_at)`" in t
    # RNK-G1 구성 예고 0/9 · 판정 분모 9
    assert "post10 신규 `exact` **9건**" in t and "구성 예고 0/9" in t
    # D-3 · P9-공통독법 · D-8 + P9-결측분리
    assert "*「`approx` 포함 시 최소 n 이 차는 축: **없음**" in t
    assert "`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음" in t
    assert _levels_ok(t) and "`1.0.43` 12/1" in t and "`missing` 19/2" in t and "*「결측 n = 19/2」*" in t
    assert "SSOT = 행(`PREREG_POST9.md` §4)" in t and "부호 갈림 검사: 통계량 정의 없음(기록만)" in t
    # P10-기업행위봉 신고 줄(k = 0 이어도) + 「기업행위 건 제외」 (이름, n, 답) · 답(참고) · 세지 않는다
    assert re.search(r"\*「`P10-기업행위봉`: 기업행위 건 \d+/9 — .+ · `adj_factor` 산술 0 · 처리 = \(나\)」\*", t)
    row = next(ln for ln in t.split("\n") if ln.startswith("| 🆕 「기업행위 건 제외」"))
    assert "답(참고) · 세지 않는다" in row
    # D-5 — 재진입 제외는 항등 아님(9 ↔ 5) · 「샌즈 제외」 인쇄만
    row_re = next(ln for ln in t.split("\n") if ln.startswith("| §1-5 재진입 제외"))
    assert "| **5** |" in row_re and "항등 아님" in row_re
    assert any(ln.startswith("| 🆕 「샌즈 제외」") and "인쇄만" in ln for ln in t.split("\n"))
    # 걸침 의무 문장 + 서산 「전부 경계 전」 + 수집증거 post10 판
    assert t.count("은 제도 경계 2026-09-14 를 걸친다") >= 8
    assert "전부 제도 경계 전" in t
    assert "addDate` 제3자 증거 = **빠진다**" in t
    # 등급 열 금지
    assert not re.search(r"^\| .*\| 등급 \|", t, re.M)


def test_mutation_negative_output_guards():
    t = NUM.read_text(encoding="utf-8")
    assert _levels_ok(t)
    assert not _levels_ok(t.replace("*「결측 n = 19/2」*", ""))
    assert not _levels_ok(re.sub(r"(수준\(행/글\): )", r"\1`missing` 19/2 · ", t, count=1))
    assert not re.search(r"\*「`P10-기업행위봉`: 기업행위 건 \d+/9", re.sub(r"\*「`P10-기업행위봉`:[^\n]*", "", t))
