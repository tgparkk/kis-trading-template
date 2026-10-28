# -*- coding: utf-8 -*-
"""`run_regday_post10.py` 의 «가드 시험» — `test_post9_regday.py` 구조 승계. 분모·D-11 병기 가드·P9-/F-3 인쇄 줄을 본다.

🔑 계열 규칙: 단독 단언은 판별력이 없다 → 대칭 단언(일부러 어긴 줄을 넣어 실패가 나는지도 본다).
실행: `python -m pytest test_post10_regday.py -q -p no:cacheprovider`  (DB 접속 0건 · 라이브 트리 import 0건)
🔴 옛 회차 시험(`test_post7_regday` 등)은 호출하지 않는다 — 옛 러너 재실행은 커밋된 옛 NUMBERS 를 덮어쓴다(09-30 사고).

  P1  동결 상수 = post7 판과 같은 값 · post10 `DB_UPTO` 10-02 · 절단 대조 09-29
  P2  분모 = 10번째 글 `exact` 9(INTAKE·원장 대조) · 후속 3 = 축 밖 · 누적 (32, 37)
  N1  (음성) 후속을 분모에 넣으면 «오염»된다
  P3  `approx` 0 · 재진입 4(항등 아님 · PD-3) · 샌즈 코드
  P4  `P6-절단가드-A` 산술(재사용)
  P6  D-11 줄 가드(음성 3 · 양성 1)
  P7  재사용 증명 · post6 버퍼 불가로채기 · 옛 스크립트 작업트리 변경 0
  P8  산출물·산문 — `Q1-R2` 가 든 모든 줄: 금지어 0 · 병기
  P9  산출물 — D-3·D-6·D-9·D-10·`P9-` 인쇄 줄·F-3 신고 줄·4/9·걸침 8+서산 전부 전·라이브 문구·창 문구·등급 0
  P10 산출물 — D-5 삼항 · 「기업행위 건 제외」 답 칸 낱말 · 배선
"""
from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import pytest

import run_regday_post6 as R6
import run_regday_post7 as R7
import run_regday_post10 as R10
import run_selection_post8 as P8
import run_selection_post10 as S10

BASE = Path(__file__).resolve().parent
INTAKE = BASE / "INTAKE_2026-10-04_post10.md"
NUM = BASE / "RESULTS_REGDAY_POST10_NUMBERS.md"
PROSE = BASE / "RESULTS_REGDAY_POST10.md"
LOG = "224429747319"
VERDICT_WORDS = ("충족", "미달", "지지", "불성립", "통과", "실패", "발동", "✅", "❌")


def numbers():
    assert NUM.exists(), "RESULTS_REGDAY_POST10_NUMBERS.md 가 없다 — run_regday_post10.py 를 먼저 돌린다"
    return NUM.read_text(encoding="utf-8")


def _co_cell_ok(cell: str) -> bool:
    """「기업행위 건 제외」 답 칸 가드 — 낱말 + 판정 낱말 없음(`F-3` (나))."""
    return "답(참고) · 세지 않는다" in cell and not any(w in cell.replace("(참고)", "") for w in VERDICT_WORDS)


def test_P1_frozen_constants():
    assert R10.DB_UPTO == "2026-10-02" and R10.PUB_DATE == "2026-10-02" and R10.DB_UPTO_CUT == "2026-09-29"
    same = ("WIN", "NREP", "NULL_SEED", "BAND_UP", "UP_MULT", "M1_RATIO", "R2_RATIO", "ALPHA", "MIN_N", "MIN_PULL",
            "CLUSTER_MIN", "TRUNC_GUARD", "DROP_GUARD", "NUP_CITE_BAN", "W10_DEGRADE", "LIMIT_UP")
    for k in same:
        assert getattr(R10, k) == getattr(R7, k), k
    assert R10.NULL_SEED == 20260815 and R10.NREP == 20_000 and abs(R10.M1_RATIO - 5 / 6) < 1e-12
    assert P8.DB_UPTO == "2026-10-02"


def test_P2_denominator():
    assert R10.POST10_EXACT == S10.NEW10 == [
        ("서산", "079650", "2026-09-09"), ("샌즈랩", "411080", "2026-09-14"), ("성호전자", "043260", "2026-09-14"),
        ("라온시큐어", "042510", "2026-09-15"), ("범한퓨얼셀", "382900", "2026-09-16"), ("한켐", "457370", "2026-09-16"),
        ("HT로보틱스", "396300", "2026-09-18"), ("우리로", "046970", "2026-09-18"), ("뷰노", "338220", "2026-09-29")]
    intake = INTAKE.read_text(encoding="utf-8")
    for nm, code, _d in R10.POST10_EXACT:
        assert nm in intake and code in intake, nm
    rows = [r for r in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")) if r["post_log_no"] == LOG]
    assert sorted(r["stock_name"] for r in rows if r["reg_date_precision"] == "exact") == sorted(n for n, _c, _d in R10.POST10_EXACT)
    assert R10.POST9P == S10.NEW9 and len(R10.POST9P) == 5
    assert R10.POST8 == [(n, c, d) for n, c, d, _t in P8.EXACT8]
    assert [n for n, _c, _d in R10.POST8] == ["우리로", "JW신약", "액스비스", "우리기술"]
    assert sorted(n for n, _c, _x in R10.POST10_FOLLOWUP) == sorted(r["stock_name"] for r in rows if r["reg_date_precision"] != "exact")
    den = {c for _n, c, _d in R10.POST10_EXACT}
    assert not den & {c for _n, c, _x in R10.POST10_FOLLOWUP}
    assert R10.POST7 == R7.POST7_EXACT and R10.POST6 == R7.POST6 and R10.POST5 == R7.POST5 and R10.POST4 == R7.POST4
    assert R10.FROZEN_CUM == (32, 37) and R10.FROZEN_P9 == (4, 5)      # post9 보고 §1: 28/32 + 4/5


def test_N1_poisoned_denominator():
    poisoned = list(R10.POST10_EXACT) + [(n, c, None) for n, c, _x in R10.POST10_FOLLOWUP]
    assert len(poisoned) == 12 != 9
    assert any(d is None for _n, _c, d in poisoned)


def test_P3_no_approx_reentry_four():
    assert R10.APPROX_BRANCHES == [] and R10.SANDS_CODE == "411080" and R10.REENTRY is S10.REENTRY
    assert sorted(R10.REENTRY) == ["046970", "079650", "382900", "457370"]
    assert sum(S10.PD3_FLAG.values()) == 4 and S10.PD3_FLAG["샌즈랩"] == 0     # 재진입은 항등이 아니다(9↔5)
    assert len([c for _n, c, _d in R10.POST10_EXACT if c not in R10.REENTRY]) == 5


def test_P4_trunc_guard_reuse():
    assert R10.guard_a_fires is R7.guard_a_fires
    assert R10.guard_a_fires(0, 9) is False and R10.guard_a_fires(2, 9) is False
    assert R10.guard_a_fires(3, 9) is True and R10.guard_a_fires(1, 0) is False


def test_P6_d11_line_guard_bites():
    saved_tag, n0 = R10.Q1_TAG[0], len(R10.OUT)
    try:
        R10.Q1_TAG[0] = "〔D-11 병기: 이번 회차 `REG-M4` `n_up` 중앙 **64.0** · `PREREG_Q1_V2.md:66` x〕"
        with pytest.raises(AssertionError):
            R10.say("| `Q1-R2` | ✅ 지지 | " + R10.Q1_TAG[0] + " |")
        with pytest.raises(AssertionError):
            R10.say("`Q1-R2` 성립 " + R10.Q1_TAG[0])
        with pytest.raises(AssertionError):
            R10.say("`Q1-R2` 문턱 충족 — 비율 기록")
        R10.say("`Q1-R2` 문턱 충족 — 비율 기록 " + R10.Q1_TAG[0])
        R10.say("`P6-M1′` ✅ 지지 (Q1 과 무관한 줄)")
    finally:
        del R10.OUT[n0:]
        R10.Q1_TAG[0] = saved_tag


def test_P7_reuse_and_old_untouched():
    for fn in ("block", "bucket", "fmt_pct", "gstar", "load_universe_day", "measure", "null_gstar_a",
               "null_gstar_b", "null_p", "prev_trading_day", "universe_raw_count", "verdict_and"):
        assert getattr(R10, fn) is getattr(R6, fn), fn
    assert R10.market_days is R7.market_days and R10.snapshot_tail is R7.snapshot_tail
    assert R10.corp_scan is S10.corp_scan and R10.read_stamp is S10.read_stamp
    assert R10.rule_txt(R6.verdict_and(True, True)).startswith("✅ 두 성분 충족(기록")
    assert R6.OUT is R7.OUT, "post10 import 가 post6 버퍼를 가로챘다"
    r = subprocess.run(["git", "status", "--porcelain", "--", "run_regday_post6.py", "run_regday_post7.py", "run_regday_post8.py",
                        "run_regday_post9.py", "RESULTS_REGDAY_POST9_NUMBERS.md", "RESULTS_REGDAY_POST9.md"],
                       cwd=BASE, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def test_P8_numbers_q1_lines():
    t = numbers()
    med = re.search(r"`n_up` 중앙값 ([\d.]+)\*\*", t).group(1)
    q = [ln for ln in t.splitlines() if "Q1-R2" in ln]
    assert len(q) >= 8
    for ln in q:
        assert "지지" not in ln and "성립" not in ln, ln
        assert "`PREREG_Q1_V2.md:66`" in ln and "R2 는 비율 기록" in ln, ln
        assert f"`n_up` 중앙 **{med}**" in ln, ln


def test_P8b_prose_q1_lines():
    assert PROSE.exists(), "RESULTS_REGDAY_POST10.md 가 없다"
    med = re.search(r"`n_up` 중앙값 ([\d.]+)\*\*", numbers()).group(1)
    q = [ln for ln in PROSE.read_text(encoding="utf-8").splitlines() if "Q1-R2" in ln]
    assert q
    for ln in q:
        assert "지지" not in ln and "성립" not in ln, ln
        assert "`PREREG_Q1_V2.md:66`" in ln and f"**{med}**" in ln, ln


def test_P9_numbers_duties():
    t = numbers()
    assert re.search(r"표준편차 \*\*[\d.]+\(`ddof=1`\)\*\* \([\d.]+ · `ddof=0`\) — \*「SSOT = `ddof=1`\(`PREREG_POST8.md` §6\)」\*", t)
    assert "`[이름 인용 금지]` 꼬리표 =" in t and "이전 회차(post6 · post7 · post8 · post9)의 꼬리표 결과를 **옮기지 않았다**" in t   # D-10
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 9 / `approx` 포함 분모 9」" in t              # D-3
    assert "10-02 봉은 D+1(10-06) sweep 이후 읽음" in t and "`regday_post10/read_stamp.json`" in t                   # D-9 ①③
    assert "`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)" in t                                        # P9-공통독법
    assert "`P9-행단위`·`P9-결측분리`: 해당 없음" in t and "`P9-스탬프통일` 발효" in t
    assert "## 4. `PREREG_POST6.md` §1-4 **창 규약** + `P6-W10`(§1-4 용도) — **해당 없음**" in t
    assert "***두 용도는 서로 다른 수다.***" in t and "한 수로 합치지 않는다" in t
    assert R10.WINDOW_LINE in t and R10.LIVE_BAN[0] in t and R10.LIVE_BAN[1] in t
    # F-3 신고 줄(k = 0 이어도) · 재등록 날짜 · 4/9
    assert re.search(r"`P10-기업행위봉`: 기업행위 건 \d+/9 — .+ · `adj_factor` 산술 0 · 처리 = \(나\)", t)
    assert "`P6-PRIOR_CYCLE_IN_WINDOW` = 1 인 건 4/9" in t
    assert "재등록 날짜 기록" in t and "재등록 샌즈랩 9/29 · 한컴위드 9/23" in t
    # D-9 걸침: 판정 창 8 + 적재 창 1 · 서산 「전부 경계 전」 1줄
    assert len(re.findall(r"창 `\[\d{4}-\d\d-\d\d, \d{4}-\d\d-\d\d\]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 \d+ 봉 / "
                          r"후 \d+ 봉 · 혼합 빈티지", t)) == 9
    assert len(re.findall(r"은 전부 제도 경계 전\(전 \d+ / 후 0\) \(서산 `\[D−19, D\]`\)", t)) == 1
    assert "판정 창 걸침 = 8건" in t and "🟢 **일치**(건수 · 서산 전부 전)" in t
    assert "라이브 채택 대상이 아니다" in t and "GT-" not in t
    m = re.search(r"D-9 ① 쿼리 실행 시각\(KST\) = (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", t)
    assert m and m.group(1) >= R10.SWEEP_D1[:19], m
    assert "\r" not in t


def test_P10_branch_triples_and_wiring():
    t = numbers()
    sec = t.split("## 9.")[1].split("## 10.")[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| `")]
    for lbl in ("`Q1-R2`", "`P6-M1′`", "`P6-M2′`", "`P6-M3′`", "`REG-M4`"):
        mine = [r for r in rows if r.startswith("| " + lbl + " |")]
        assert mine, lbl
        for r in mine:
            c = [x.strip() for x in r.split("|")]
            assert len(c) == 8 and c[2] and c[3] and c[4], (lbl, r)
    assert any("`approx` 포함 조합" in r and "해당 없음" in r for r in rows)
    # 재진입 갈래는 항등이 아니다(9 ↔ 5) — 「항등」 한 낱말로 끝나는 재진입 행이 없다
    re_rows = [r for r in rows if "§1-5 재진입 포함↔제외" in r]
    assert len(re_rows) == 5 and all("9 ↔ 5" in r for r in re_rows)
    assert not any(r.split("|")[4].strip() == "**항등**" for r in re_rows)
    # 「기업행위 건 제외」 답 칸 = 낱말 + 판정 낱말 없음 · 음성: 판정 낱말이 섞이면 실패
    co = [r for r in rows if "「기업행위 건 제외」" in r]
    assert len(co) == 5 and all(_co_cell_ok(r.split("|")[4]) for r in co), co
    assert _co_cell_ok("답(참고) · 세지 않는다 — 비율 55.6%") and not _co_cell_ok("답(참고) · 세지 않는다 — 문턱 충족")
    sa = [r for r in rows if "「샌즈 제외」" in r]
    assert len(sa) == 5 and all("인쇄만" in r for r in sa), sa
    assert "🔴 **아니오 — 배선 결함**" not in t
