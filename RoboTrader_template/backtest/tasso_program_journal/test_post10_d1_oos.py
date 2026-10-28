# -*- coding: utf-8 -*-
"""`run_d1_oos_post10.py` 가드 시험 — post9 판(`test_post9_d1_oos.py`) 구조 승계 · 짧게. (TV = 「0건 · 미룸」)

  P1  문형 승계 — `ITEMS`·`PRIOR`·`CLASSES` 가 post7/post8 판의 «그 객체»다 · 원본 불변(기준 `8e014ca`)
  P2  13항목 상태 — post9 연속 +1(`TV-W1`~`W3` 6글 · 나머지 5글) · 전부 미룸
  P3  grep 실측 — 원문(작업트리 또는 보관본)에서 「거래대금」 0 · 「배」 0 · 「시총」 0 · (음성) 수치 붙이면 잡힌다
  P4  산출물 — 13행 전부 ⛔ 미룬다 · 인쇄 의무 · 라이브 문언 = `PREREG_POST10.md:56` · stamp ↔ ① 줄 · 재실행 byte 동일
🔴 옛 회차 시험·러너는 실행하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import run_d1_oos_post7 as D7
import run_d1_oos_post8 as D8
import run_d1_oos_post9 as D9
import run_d1_oos_post10 as D10

BASE = Path(__file__).resolve().parent
NUM = BASE / D10.OUT_NAME
STAMP = BASE / D10.STAMP_DIR / "read_stamp.json"
RAW = [BASE / "post_224429747319.txt", Path("D:/archive/tasso-program-journal-20261004/post_224429747319.txt")]
BASE_REF = "8e014ca"


def test_P1_inherited_objects_and_originals_untouched():
    assert D10.CLASSES is D8.CLASSES and D10.AUX_ZERO is D8.AUX_ZERO and len(D7.ITEMS) == 13
    src = (BASE / "run_d1_oos_post10.py").read_text(encoding="utf-8")
    assert "for lbl, hyp, thr, minn, pair, block in D7.ITEMS:" in src and "D7.PRIOR" in src and "D9.status9()" in src
    for f in ("run_d1_oos_post7.py", "run_d1_oos_post8.py", "run_d1_oos_post9.py", "RESULTS_D1_OOS_POST9_NUMBERS.md",
              "RESULTS_D1_OOS_POST9.md", "test_post9_d1_oos.py"):
        r = subprocess.run(["git", "diff", "--quiet", BASE_REF, "--", f], cwd=str(BASE))
        assert r.returncode == 0, f
    assert subprocess.run(["git", "cat-file", "-e", f"{BASE_REF}:./{D10.OUT_NAME}"], cwd=str(BASE),
                          capture_output=True).returncode != 0, "대칭 — 기준 ref 에 post10 산출물 없음"


def test_P2_status_plus_one():
    st = D10.status10()
    assert [s[0] for s in st] == [s[0] for s in D9.status9()] and len(st) == 13
    streak = {s[0]: s[5] for s in st}
    assert streak["`TV-W1`"] == streak["`TV-W2`"] == streak["`TV-W3`"] == 6 == D10.DEFER_STREAK
    assert all(v == 5 for k, v in streak.items() if k not in ("`TV-W1`", "`TV-W2`", "`TV-W3`"))
    assert all(s[4] == "미룸" and s[3].endswith(" · 9 미룸") for s in st)
    assert D10.ZERO_STREAK == 5
    assert D10.status10() != D9.status9()                          # 대칭 — post9 표와 다르다(연속이 늘었다)


def _raw():
    for p in RAW:
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def test_P3_grep_counts_and_negative():
    t = _raw()
    assert t is not None, "원문(작업트리·보관본) 둘 다 없다"
    for w, n in D10.GREP_WORDS:
        assert t.count(w) == n == 0, (w, t.count(w))
    assert not re.search(r"\d+(\.\d+)?\s*배", t)
    lines = t.splitlines()
    lines[37] = lines[37] + " 거래대금/시총 0.5배"
    assert re.search(r"\d+(\.\d+)?\s*배", "\n".join(lines)), "수치 진술 검출기가 죽어 있다(음성 대조)"
    assert "거래대금" not in t and "거래대금" in (t + " 거래대금")    # 대칭 — 검출기가 낱말에 반응한다


@pytest.mark.skipif(not NUM.exists(), reason="산출물 아직 없음")
def test_P4_numbers_duties_and_stamp():
    t = NUM.read_text(encoding="utf-8")
    L = t.splitlines()
    assert D10.assert_duties(L)
    line56 = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()[55]
    assert line56 == "> " + D10.LIVE_BAN and line56 in L
    sec = t.split("## §2.")[1].split("### §2-1.")[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| `") or ln.startswith("| P6")]
    assert len(rows) == 13 and all("⛔ **미룬다**" in r and "`(주, 0, 미룸)`" in r for r in rows)
    assert "**TV: 0건 · 미룸**" in t
    assert "**`TV-W1`·`TV-W2` 미룸 = 6글 연속**" in t and "**종목 단위 자가보고 0건 = 5글 연속**" in t
    st = json.loads(STAMP.read_text(encoding="utf-8"))
    assert set(st) == {"fingerprint", "first_read_kst", "timezone"}
    m = re.search(r"^\| `D-9` ① 쿼리 실행 시각\(KST\) \| \*\*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\*\*", t, re.M)
    assert m and m.group(1) == st["first_read_kst"]
    assert "GT-" not in t and "\r" not in t
    bad = [x.replace("0건 · 미룸", "") for x in L]
    with pytest.raises(AssertionError):                            # 대칭 — 「0건 · 미룸」 줄이 없으면 가드가 문다
        D10.assert_duties(bad)


def _db_ok():
    try:
        import psycopg2
        from run_tests import DSN
        psycopg2.connect(connect_timeout=5, **DSN).close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not (_db_ok() and NUM.exists() and STAMP.exists()), reason="DB 없음 또는 산출물 없음")
def test_P4_rerun_byte_identical_when_same_fingerprint(tmp_path):
    import psycopg2
    from run_tests import DSN
    conn = psycopg2.connect(**DSN)
    try:
        _f, _n, _r, fp = D10.read_stamp(conn.cursor(), base=tmp_path)
    finally:
        conn.close()
    if fp != json.loads(STAMP.read_text(encoding="utf-8"))["fingerprint"]:
        pytest.skip("DB 지문 이동 — byte 재현은 같은 스냅샷 안에서만 성립")
    before = hashlib.md5(NUM.read_bytes()).hexdigest(), hashlib.md5(STAMP.read_bytes()).hexdigest()
    r = subprocess.run([sys.executable, "-X", "utf8", "run_d1_oos_post10.py"], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    assert before == (hashlib.md5(NUM.read_bytes()).hexdigest(), hashlib.md5(STAMP.read_bytes()).hexdigest())
