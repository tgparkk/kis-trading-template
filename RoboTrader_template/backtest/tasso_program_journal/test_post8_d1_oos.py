# -*- coding: utf-8 -*-
"""`run_d1_oos_post8.py` 의 «가드 시험» — 0건 ⇒ 13항목 미룸이 규칙을 넓히지 않고 인쇄되는지 본다.

post7 판에는 이 레인의 시험 파일이 없었다(`test_post7_*.py` 목록 실측) — 승계할 시험이 없어 **새로** 쓴다(작은 범위).

실행: `python -m pytest test_post8_d1_oos.py -q -p no:cacheprovider`  (DB 접속 0건 · 라이브 트리 import 0건)

  P1  문형 승계 — 판정표(`ITEMS` 13행)·누적(`PRIOR`)·허용오차·N2 문턱이 post7 판의 «그 객체»다
  P2  13항목 누적 미룸 상태 표 — 라벨이 `ITEMS` 와 같은 13개 · `TV-W1`~`W3` 4글 · 나머지 3글 · W1·W2 연속 = 4
  P3  grep 실측 — 원문(작업트리 또는 보관본)에서 「거래대금」 2(:56 · :64) · 「배」 0 · 「시총」 0
  N1  (음성) 「거래대금」 산문 줄에 「0.5배」를 붙이면 수치 진술 후보가 생긴다 ⇒ 0건 판정은 «수치 부재»에 기대고 있다
  P4  산출물 — 「0건 · 미룸」 · 13행 전부 ⛔ 미룬다 · D-3 · D-9 ①~⑤ · 라이브 · 시각 0 · 등급 0
"""
from __future__ import annotations

import re
from pathlib import Path

import run_d1_oos_post7 as D7
import run_d1_oos_post8 as D8

BASE = Path(__file__).resolve().parent
NUM = BASE / "RESULTS_D1_OOS_POST8_NUMBERS.md"
RAW = [BASE / "post_224416253270.txt", Path("D:/archive/tasso-program-journal-20260918/post_224416253270.txt")]


def test_P1_inherited_objects():
    assert D8.TOL == D7.TOL == 0.20 and D8.N2_DEGRADE == D7.N2_DEGRADE == 30 and D8.SEED == D7.SEED
    assert len(D7.ITEMS) == 13 and D7.PRIOR_TOTAL == (12, 6)
    src = (BASE / "run_d1_oos_post8.py").read_text(encoding="utf-8")
    assert "for lbl, hyp, thr, minn, pair, block in D7.ITEMS:" in src and "D7.PRIOR" in src
    assert D8.DB_UPTO == "2026-09-18"


def test_P2_status_table():
    labels_items = [it[0] for it in D7.ITEMS]
    labels_status = [s[0].split("(")[0].strip() for s in D8.STATUS]
    assert sorted(labels_status) == sorted(labels_items) and len(D8.STATUS) == 13
    streak = {s[0].split("(")[0].strip(): s[5] for s in D8.STATUS}
    assert streak["`TV-W1`"] == streak["`TV-W2`"] == streak["`TV-W3`"] == 4 == D8.DEFER_STREAK
    assert all(v == 3 for k, v in streak.items() if k not in ("`TV-W1`", "`TV-W2`", "`TV-W3`"))
    assert all(s[4] == "미룸" for s in D8.STATUS)


def _raw_text():
    for p in RAW:
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def test_P3_grep_counts():
    t = _raw_text()
    assert t is not None, "원문(작업트리·보관본) 둘 다 없다"
    for w, n in D8.GREP_WORDS:
        assert t.count(w) == n, (w, t.count(w))
    lines = t.splitlines()
    for ln, frag, _k in D8.GREP_LINES:
        assert "거래대금" in lines[ln - 1], ln
    assert not re.search(r"\d+(\.\d+)?\s*배", t), "「N배」 수치 진술이 원문에 있다 — 0건 판정 재검토"


def test_N1_numeric_claim_would_be_caught():
    t = _raw_text()
    lines = t.splitlines()
    lines[55] = lines[55] + " 거래대금/시총 0.5배"
    assert re.search(r"\d+(\.\d+)?\s*배", "\n".join(lines)), "수치 진술 검출기가 죽어 있다"


def test_P4_numbers_duties():
    assert NUM.exists(), "RESULTS_D1_OOS_POST8_NUMBERS.md 가 없다 — run_d1_oos_post8.py 를 먼저 돌린다"
    t = NUM.read_text(encoding="utf-8")
    assert "「**0건 · 미룸**」" in t
    sec = t.split("## §2.")[1].split("### §2-1.")[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| `") or ln.startswith("| P6")]
    assert len(rows) == 13 and all("⛔ **미룬다**" in r and "`(주, 0, 미룸)`" in r for r in rows)
    assert "해치텍" not in sec, "post7 종목 문구가 post8 판정표에 남았다"
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 0 / `approx` 포함 분모 0」" in t
    assert "09-18 봉은 D+1(09-21) sweep 이후 읽음" in t and "실행 stdout 에만 인쇄" in t
    assert "걸침 창 없음" in t and "4글 연속" in t and "라이브 채택 대상이 아니다" in t
    stamps = set(re.findall(r"2026-09-2[4-9] \d\d:\d\d:\d\d", t))
    assert stamps <= {D8.MGR["run"][:19]}, stamps
    assert "GT-" not in t and "\r" not in t
