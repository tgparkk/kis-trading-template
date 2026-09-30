# -*- coding: utf-8 -*-
"""`run_d1_oos_post9.py` 가드 시험 — post8 판(`test_post8_d1_oos.py`) 구조 승계 · 짧게.

  P1  문형 승계 — `ITEMS`·`PRIOR`·`STATUS`·허용오차가 post7/post8 판의 «그 객체»다 · 원본 불변
  P2  13항목 상태 — post8 연속 +1(`TV-W1`~`W3` 5글 · 나머지 4글) · 전부 미룸
  P3  grep 실측 — 원문(작업트리 또는 보관본)에서 「거래대금」 1(:38) · 「배」 0 · 「시총」 0 · (음성) 수치 붙이면 잡힌다
  P4  산출물 — 13행 전부 ⛔ 미룬다 · 인쇄 의무 · 라이브 문언 = `PREREG_POST9.md:39` · stamp ↔ ① 줄 · 재실행 byte 동일
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

BASE = Path(__file__).resolve().parent
NUM = BASE / D9.OUT_NAME
STAMP = BASE / D9.STAMP_DIR / "read_stamp.json"
RAW = [BASE / "post_224421214462.txt", Path("D:/archive/tasso-program-journal-20260923/post_224421214462.txt")]
BASE_REF = "30aed89"


def test_P1_inherited_objects_and_originals_untouched():
    assert D9.CLASSES is D8.CLASSES and D9.AUX_ZERO is D8.AUX_ZERO and len(D7.ITEMS) == 13
    src = (BASE / "run_d1_oos_post9.py").read_text(encoding="utf-8")
    assert "for lbl, hyp, thr, minn, pair, block in D7.ITEMS:" in src and "D7.PRIOR" in src and "D8.STATUS" in src
    for f in ("run_d1_oos_post8.py", "run_d1_oos_post7.py", "RESULTS_D1_OOS_POST8_NUMBERS.md", "RESULTS_D1_OOS_POST8.md"):
        r = subprocess.run(["git", "diff", "--quiet", BASE_REF, "--", f], cwd=str(BASE))
        assert r.returncode == 0, f


def test_P2_status_plus_one():
    st = D9.status9()
    assert [s[0] for s in st] == [s[0] for s in D8.STATUS] and len(st) == 13
    streak = {s[0]: s[5] for s in st}
    assert streak["`TV-W1`"] == streak["`TV-W2`"] == streak["`TV-W3`"] == 5 == D9.DEFER_STREAK
    assert all(v == 4 for k, v in streak.items() if k not in ("`TV-W1`", "`TV-W2`", "`TV-W3`"))
    assert all(s[4] == "미룸" and s[3].endswith(" · 8 미룸") for s in st)
    assert D9.ZERO_STREAK == 4


def _raw():
    for p in RAW:
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def test_P3_grep_counts_and_negative():
    t = _raw()
    assert t is not None, "원문(작업트리·보관본) 둘 다 없다"
    for w, n in D9.GREP_WORDS:
        assert t.count(w) == n, (w, t.count(w))
    lines = t.splitlines()
    for ln, frag, _k in D9.GREP_LINES:
        assert frag in lines[ln - 1], ln
    assert not re.search(r"\d+(\.\d+)?\s*배", t)
    lines[37] = lines[37] + " 거래대금/시총 0.5배"
    assert re.search(r"\d+(\.\d+)?\s*배", "\n".join(lines)), "수치 진술 검출기가 죽어 있다(음성 대조)"


@pytest.mark.skipif(not NUM.exists(), reason="산출물 아직 없음")
def test_P4_numbers_duties_and_stamp():
    t = NUM.read_text(encoding="utf-8")
    L = t.splitlines()
    assert D9.assert_duties(L)
    line39 = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").splitlines()[38]
    assert line39 == "> " + D9.LIVE_BAN and line39 in L
    sec = t.split("## §2.")[1].split("### §2-1.")[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| `") or ln.startswith("| P6")]
    assert len(rows) == 13 and all("⛔ **미룬다**" in r and "`(주, 0, 미룸)`" in r for r in rows)
    assert "해치텍" not in sec and "액스비스" not in sec, "이전 글 종목 문구가 남았다"
    assert "**`TV-W1`·`TV-W2` 미룸 = 5글 연속**" in t and "**종목 단위 자가보고 0건 = 4글 연속**" in t
    st = json.loads(STAMP.read_text(encoding="utf-8"))
    m = re.search(r"^\| `D-9` ① 쿼리 실행 시각\(KST\) \| \*\*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\*\*", t, re.M)
    assert m and m.group(1) == st["first_read_kst"]
    assert "GT-" not in t and "\r" not in t


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
        _f, _n, _r, fp = D9.read_stamp(conn.cursor(), base=tmp_path)
    finally:
        conn.close()
    if fp != json.loads(STAMP.read_text(encoding="utf-8"))["fingerprint"]:
        pytest.skip("DB 지문 이동 — byte 재현은 같은 스냅샷 안에서만 성립")
    before = hashlib.md5(NUM.read_bytes()).hexdigest(), hashlib.md5(STAMP.read_bytes()).hexdigest()
    r = subprocess.run([sys.executable, "-X", "utf8", "run_d1_oos_post9.py"], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    assert before == (hashlib.md5(NUM.read_bytes()).hexdigest(), hashlib.md5(STAMP.read_bytes()).hexdigest())
