# -*- coding: utf-8 -*-
"""`run_regday_post9.py` 의 «가드 시험» — post8 판(`test_post8_regday.py`) 구조 승계. 분모·D-11 병기 가드·P9- 인쇄 줄을 본다.

🔑 계열 규칙: 단독 단언은 판별력이 없다 → 대칭 단언(일부러 어긴 줄을 넣어 실패가 나는지도 본다).
실행: `python -m pytest test_post9_regday.py -q -p no:cacheprovider`  (DB 접속 0건 · 라이브 트리 import 0건)

  P1  동결 상수 = post7 판과 같은 값 · post9 `DB_UPTO` 09-23 · 절단 대조 09-15
  P2  분모 = 9번째 글 `exact` 5(INTAKE 본문 대조) · 후속 1 = 축 밖 · 누적 (28, 32) = post8 누적 + 4/4
  N1  (음성) 후속을 분모에 넣으면 «오염»된다
  P3  `approx` 0 · 재진입 0 · 첨단 코드
  P4  `P6-절단가드-A` 산술(재사용)
  P6  D-11 줄 가드(음성 3 · 양성 1)
  P7  재사용 증명 · post6 버퍼 불가로채기
  P8  산출물·산문 — `Q1-R2` 가 든 모든 줄: 금지어 0 · 병기
  P9  산출물 — D-3·D-6·D-9·D-10·`P9-` 인쇄 줄·PD-31·걸침 3건·라이브 문구·창 문구·등급 0
  P10 산출물 — D-5 삼항 · 배선
  R1  post7 회귀
"""
from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import run_regday_post6 as R6
import run_regday_post7 as R7
import run_regday_post8 as R8
import run_regday_post9 as R9
import run_selection_post9 as S9
import test_post7_regday as T7

BASE = Path(__file__).resolve().parent
INTAKE = BASE / "INTAKE_2026-09-24_post9.md"
NUM = BASE / "RESULTS_REGDAY_POST9_NUMBERS.md"
PROSE = BASE / "RESULTS_REGDAY_POST9.md"


def numbers():
    assert NUM.exists(), "RESULTS_REGDAY_POST9_NUMBERS.md 가 없다 — run_regday_post9.py 를 먼저 돌린다"
    return NUM.read_text(encoding="utf-8")


def test_P1_frozen_constants():
    assert R9.DB_UPTO == "2026-09-23" and R9.PUB_DATE == "2026-09-23" and R9.DB_UPTO_CUT == "2026-09-15"
    same = ("WIN", "NREP", "NULL_SEED", "BAND_UP", "UP_MULT", "M1_RATIO", "R2_RATIO", "ALPHA", "MIN_N", "MIN_PULL",
            "CLUSTER_MIN", "TRUNC_GUARD", "DROP_GUARD", "NUP_CITE_BAN", "W10_DEGRADE", "LIMIT_UP")
    for k in same:
        assert getattr(R9, k) == getattr(R7, k), k
    assert R9.NULL_SEED == 20260815 and R9.NREP == 20_000 and abs(R9.M1_RATIO - 5 / 6) < 1e-12


def test_P2_denominator():
    assert R9.POST9_EXACT == S9.NEW9 == [("삼미금속", "012210", "2026-09-04"), ("에스투더블유", "488280", "2026-09-10"),
                                         ("빛샘전자", "072950", "2026-09-14"), ("한국첨단소재", "062970", "2026-09-15"),
                                         ("한컴위드", "054920", "2026-09-15")]
    intake = INTAKE.read_text(encoding="utf-8")
    for nm, code, _d in R9.POST9_EXACT:
        assert nm in intake and code in intake, nm
    assert R9.POST8 == R8.POST8_EXACT
    assert [n for n, _c, _d in R9.POST8] == ["우리로", "JW신약", "액스비스", "우리기술"]
    assert R9.POST9_FOLLOWUP == [("우리기술", "032820", "post8 #10 · 09-09 재명시")]
    den = {c for _n, c, _d in R9.POST9_EXACT}
    assert not den & {c for _n, c, _x in R9.POST9_FOLLOWUP}
    assert R9.POST7 == R7.POST7_EXACT and R9.POST6 == R7.POST6 and R9.POST5 == R7.POST5 and R9.POST4 == R7.POST4
    assert R9.FROZEN_CUM == (R8.FROZEN_CUM[0] + 4, R8.FROZEN_CUM[1] + 4) == (28, 32)
    assert R9.FROZEN_P8 == (4, 4)


def test_N1_poisoned_denominator():
    poisoned = list(R9.POST9_EXACT) + [(n, c, None) for n, c, _x in R9.POST9_FOLLOWUP]
    assert len(poisoned) == 6 != 5
    assert any(d is None for _n, _c, d in poisoned)


def test_P3_no_approx_no_reentry():
    assert R9.APPROX_BRANCHES == [] and R9.REENTRY == {} and R9.CHEOM_CODE == "062970"
    assert S9.PD3_FLAG == {nm: 0 for nm, _c, _d in R9.POST9_EXACT}
    assert R9.PD27_X19 == {"빛샘전자": (19, 1), "한국첨단소재": (18, 2), "한컴위드": (18, 2)}


def test_P4_trunc_guard_reuse():
    assert R9.guard_a_fires is R7.guard_a_fires
    assert R9.guard_a_fires(0, 5) is False and R9.guard_a_fires(1, 5) is False
    assert R9.guard_a_fires(2, 5) is True and R9.guard_a_fires(1, 0) is False


def test_P6_d11_line_guard_bites():
    saved_tag, n0 = R9.Q1_TAG[0], len(R9.OUT)
    try:
        R9.Q1_TAG[0] = "〔D-11 병기: 이번 회차 `REG-M4` `n_up` 중앙 **64.0** · `PREREG_Q1_V2.md:66` x〕"
        with pytest.raises(AssertionError):
            R9.say("| `Q1-R2` | ✅ 지지 | " + R9.Q1_TAG[0] + " |")
        with pytest.raises(AssertionError):
            R9.say("`Q1-R2` 성립 " + R9.Q1_TAG[0])
        with pytest.raises(AssertionError):
            R9.say("`Q1-R2` 문턱 충족 — 비율 기록")
        R9.say("`Q1-R2` 문턱 충족 — 비율 기록 " + R9.Q1_TAG[0])
        R9.say("`P6-M1′` ✅ 지지 (Q1 과 무관한 줄)")
    finally:
        del R9.OUT[n0:]
        R9.Q1_TAG[0] = saved_tag


def test_P7_reuse():
    for fn in ("block", "bucket", "fmt_pct", "gstar", "load_universe_day", "measure", "null_gstar_a",
               "null_gstar_b", "null_p", "prev_trading_day", "universe_raw_count", "verdict_and"):
        assert getattr(R9, fn) is getattr(R6, fn), fn
    assert R9.market_days is R7.market_days and R9.snapshot_tail is R7.snapshot_tail
    assert R9.rule_txt(R6.verdict_and(True, True)).startswith("✅ 두 성분 충족(기록")
    assert R6.OUT is R7.OUT, "post9 import 가 post6 버퍼를 가로챘다(post7 시험 P8 이 깨진다)"


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
    assert PROSE.exists(), "RESULTS_REGDAY_POST9.md 가 없다"
    med = re.search(r"`n_up` 중앙값 ([\d.]+)\*\*", numbers()).group(1)
    q = [ln for ln in PROSE.read_text(encoding="utf-8").splitlines() if "Q1-R2" in ln]
    assert q
    for ln in q:
        assert "지지" not in ln and "성립" not in ln, ln
        assert "`PREREG_Q1_V2.md:66`" in ln and f"**{med}**" in ln, ln


def test_P9_numbers_duties():
    t = numbers()
    assert re.search(r"표준편차 \*\*[\d.]+\(`ddof=1`\)\*\* \([\d.]+ · `ddof=0`\) — \*「SSOT = `ddof=1`\(`PREREG_POST8.md` §6\)」\*", t)
    assert "`[이름 인용 금지]` 꼬리표 =" in t and "이전 회차(post6 · post7 · post8)의 꼬리표 결과를 **옮기지 않았다**" in t   # D-10
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 5 / `approx` 포함 분모 5」" in t              # D-3
    assert "09-23 봉은 D+1(09-28) sweep 이후 읽음" in t and "`regday_post9/read_stamp.json`" in t                   # D-9 ①③
    assert "`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)" in t                                        # P9-공통독법
    assert "`P9-행단위`: 해당 없음" in t and "`P9-결측분리` 는 post10 부터(미적용)" in t
    assert "`P9-스탬프통일` 적용 아님 — post10 부터" in t
    assert "## 4. `PREREG_POST6.md` §1-4 **창 규약** + `P6-W10`(§1-4 용도) — **해당 없음**" in t             # 창 규약·W10 해당 없음
    assert "***두 용도는 서로 다른 수다.***" in t and "한 수로 합치지 않는다" in t
    assert R9.WINDOW_LINE in t and R9.LIVE_BAN[0] in t and R9.LIVE_BAN[1] in t
    assert R9.CHEOM_LINE in t and "판정 창 걸침 = 3건" in t and "🟢 **일치**(건수·전/후 봉수 전부)" in t   # PD-31 · PD-27 (바)
    assert len(re.findall(r"창 `\[\d{4}-\d\d-\d\d, \d{4}-\d\d-\d\d\]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 \d+ 봉 / "
                          r"후 \d+ 봉 · 혼합 빈티지", t)) == 4                                               # 판정 창 3 + 적재 창 1
    assert "라이브 채택 대상이 아니다" in t and "GT-" not in t
    m = re.search(r"D-9 ① 쿼리 실행 시각\(KST\) = (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", t)
    assert m and m.group(1) >= R9.SWEEP_D1[:19], m
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
    assert "🔴 **아니오 — 배선 결함**" not in t


def test_R1_post7_regday_suite():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = T7.main()
    assert rc == 0, buf.getvalue()[-2000:]
    assert "✅ 전건 통과" in buf.getvalue()
