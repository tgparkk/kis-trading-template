# -*- coding: utf-8 -*-
"""`run_wrc_post10.py` 시험 — 구성 스냅샷 · 재실행 byte 동일 · post10 인쇄 줄 존재 · 변이 음성(post9 판 구조 승계 · 자기 축만)."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_WRC_POST10_NUMBERS.md"


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


def _levels_ok(t):
    """`P9-결측분리` 기계 검사 — 수준 목록(괄호 «밖»)에 `missing` 없음 · 결측 n 줄 있음."""
    line = next((ln for ln in t.split("\n") if "수준(행/글):" in ln), None)
    if line is None or "결측 n = " not in t:
        return False
    outside = line.split("(민감도")[0]
    return "missing" not in outside and "`missing` " in line


def test_rerun_byte_identical():
    import pytest
    if _snapshot_moved("wrc_post10", "2026-10-02"):
        pytest.skip("DB 지문 이동(다음 sweep) — byte 재현은 같은 스냅샷 안에서만 성립 · 재실행하면 산출물이 덮어써진다")
    before = _md5(NUM)
    subprocess.run([sys.executable, "-X", "utf8", str(BASE / "run_wrc_post10.py")], cwd=BASE, check=True,
                   capture_output=True)
    assert _md5(NUM) == before


def test_composition_snapshot():
    """구성 예고(PD-22): 단독 3 · 누적 8 · 판정 분모 8 — `WRC-G1` 은 post6~9 의 4/5 가 이미 있어 누적 분자 ≥ 4 ⇒ 어느 쪽이든 발동."""
    g = json.loads((BASE / "wrc_post10" / "gate.json").read_text(encoding="utf-8"))
    cum = g["cumulative"]
    assert cum["n"] == 8 and cum["fire"] is True
    assert g["one_post"]["n"] == 3 and g["solo_post10"] == 3
    names = sorted(c["name"] for c in g["cases"] if c["post"] == "post10")
    assert names == ["HT로보틱스", "라온시큐어", "샌즈랩"]
    t = NUM.read_text(encoding="utf-8")
    assert "⛔ **판정 불가(`WRC-G1` 발동)**" in t
    assert "단독 **3** · 누적 **8** · 판정 분모 **8**" in t and "🟢 일치" in t


def test_p10_lines_present():
    t = NUM.read_text(encoding="utf-8")
    assert "창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · `END` · 전 축(`WRC-` 포함) · PD-1" in t
    assert re.search(r"실행 시 `max\(date\)` = \d{4}-\d{2}-\d{2} · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", t)
    assert "라이브 채택 대상이 아니다" in t
    # D-9 ① = read_stamp.json 의 first_read_kst (P9-스탬프통일) · ② · ③
    st = json.loads((BASE / "wrc_post10" / "read_stamp.json").read_text(encoding="utf-8"))
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"}
    assert "**" + st["first_read_kst"] + "**" in t
    assert "「2026-10-02 봉은 D+1(2026-10-06) sweep 이후 읽음」" in t and "창 구간 `max(daily_prices.updated_at)`" in t
    # D-3 · P9-공통독법
    assert "*「`approx` 포함 시 최소 n 이 차는 축: 없음」*" in t
    assert "`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음" in t
    # D-8 + P9-결측분리 (수준 «밖» missing 금지 · 결측 n)
    assert _levels_ok(t)
    assert "`1.0.43` 12/1" in t and "`missing` 19/2" in t and "*「결측 n = 19/2」*" in t
    assert "SSOT = 행(`PREREG_POST9.md` §4)" in t and "부호 갈림 검사: 통계량 정의 없음(기록만)" in t
    # P10-기업행위봉 신고 줄(k = 0 이어도) + 「기업행위 건 제외」 답 칸 낱말
    assert re.search(r"\*「`P10-기업행위봉`: 기업행위 건 \d+/8 — .+ · `adj_factor` 산술 0 · 처리 = \(나\)」\*", t)
    row = next(ln for ln in t.split("\n") if ln.startswith("| 「기업행위 건 제외」"))
    assert "답(참고) · 세지 않는다" in row
    # D-5 갈래 — 샌즈 제외(구조차단) · post8 우리로 제외 · 재진입 제외 · 각각 (이름, n, 답)
    for lab in ("「샌즈 제외」", "「post8 우리로 제외」", "재진입 제외", "미완결"):
        assert any(ln.startswith("| ") and lab in ln for ln in t.split("\n")), lab
    # D-9 걸침 의무 문장 집계(예고 1 · 1 · 8) · 서산 「전부 경계 전」
    assert "`REC-` `[D, END]` 걸침 1" in t and "`LAD-` 창5 `[D, D+4]` 걸침 1" in t and "`REG-`/`REC-` `[D−19, D]` 걸침 8" in t
    assert "전부 제도 경계 전" in t
    # P9-수집증거(post10 판) — addDate 제3자 증거 «빠진다»
    assert "addDate` 제3자 증거 = **빠진다**" in t and "순서 · md5" in t
    # 등급 열 금지(§6 은 이 단계가 아니다)
    assert not re.search(r"^\| .*\| 등급 \|", t, re.M)


def test_mutation_negative():
    """변이 음성 — 기계 검사 함수가 «깨진» 산출물을 실제로 잡는지."""
    t = NUM.read_text(encoding="utf-8")
    assert _levels_ok(t)
    bad1 = t.replace("*「결측 n = 19/2」*", "")
    assert not _levels_ok(bad1)
    bad2 = re.sub(r"(수준\(행/글\): )", r"\1`missing` 19/2 · ", t, count=1)
    assert not _levels_ok(bad2)
    bad3 = re.sub(r"\*「`P10-기업행위봉`:[^\n]*\n", "", t)
    assert not re.search(r"\*「`P10-기업행위봉`: 기업행위 건 \d+/8", bad3)


def test_no_adj_factor_arithmetic():
    src = (BASE / "run_wrc_post10.py").read_text(encoding="utf-8")
    assert "adj_factor" not in "".join(re.findall(r'"SELECT[^"]*"', src))
