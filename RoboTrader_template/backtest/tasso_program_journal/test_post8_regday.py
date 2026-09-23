# -*- coding: utf-8 -*-
"""`run_regday_post8.py` 의 «가드 시험» — 분모·플래그·D-11 병기 가드가 실제로 뭔가를 «막는지» 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 가드가 통과만 내는 장식이 아닌지, **일부러 어긴 줄을 넣어
   실패가 나는지**도 본다(`test_post7_regday.py` 문형 승계 · pytest 형식).
🔑 post7 회귀는 R1 이 `test_post7_regday.main()` 을 직접 불러 pytest 에 올린다 — 그 시험의 P8(`R6.OUT is R7.OUT`)이
   post8 import 뒤에도 성립해야 한다(post8 은 `main()` 안에서만 버퍼를 잇고 되돌린다).

실행: `python -m pytest test_post8_regday.py -q -p no:cacheprovider`  (DB 접속 0건 · 라이브 트리 import 0건)

  P1  동결 상수 불변(`DB_UPTO` 09-18 · 시드 · 20,000 · 창 20 · 문턱) = post7 판과 같은 값
  P2  분모 = INTAKE §1 `exact` 4 · `none` 1 · 후속 3 = 축 밖 · 과거 표본 재계산 목록 보존
  N1  (음성) 후속·`none` 을 분모에 넣으면 «오염»된다
  P3  재진입 플래그 — exact 안 0 · 헥토 2/7 · 코데즈 7/7 ↔ PD-3 표
  P4  `P6-절단가드-A` 산술(재사용 `guard_a_fires`)
  P5  §1-4 창 규약 갈래 7 · 조합 49 · 모순 갈래 5
  P6  🆕 D-11 줄 가드 — `Q1-R2` 줄에 「지지」/「성립」이 있거나 병기가 없으면 `say()` 가 멈춘다(음성 3 · 양성 1)
  P7  재사용 증명 · `rule_txt` 는 «표시»만 바꾼다
  P8  산출물 — `Q1-R2` 가 든 모든 줄: 금지어 0 · 병기(`n_up` 중앙 + `:66` 문언) 있음
  P9  산출물 — D-6 두 값 + SSOT 줄 · D-10 꼬리표 재판정 줄 · D-3 · D-9 · 혼합 빈티지 · 라이브 · 시각 0 · 등급 0
  P10 산출물 — D-5 `(갈래 이름, n, 답)` · `P6-M1′` 판정 칸과 정밀도 의존 배선이 일치
  R1  post7 회귀 — `test_post7_regday.main()` 전건 통과
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
import test_post7_regday as T7

BASE = Path(__file__).resolve().parent
INTAKE = BASE / "INTAKE_2026-09-18_post8.md"
PD = BASE / "PREDECISION_2026-09-18_post8.md"
NUM = BASE / "RESULTS_REGDAY_POST8_NUMBERS.md"


def numbers():
    assert NUM.exists(), "RESULTS_REGDAY_POST8_NUMBERS.md 가 없다 — run_regday_post8.py 를 먼저 돌린다"
    return NUM.read_text(encoding="utf-8")


def intake_exact():
    sec = INTAKE.read_text(encoding="utf-8").split("## §1.")[1].split("## §2.")[0]
    out = []
    for ln in sec.splitlines():
        c = [x.strip() for x in ln.split("|")]
        if len(c) < 10 or not re.fullmatch(r"\d+", c[1] or ""):
            continue
        if "신규" in c[9] and "exact" in c[4]:
            m = re.search(r"[0-9][0-9A-Z]{5}", c[3])
            d = re.search(r"(\d\d)-(\d\d)", c[4])
            out.append((c[2], m.group(0), "2026-%s-%s" % (d.group(1), d.group(2))))
    return out


def test_P1_frozen_constants():
    assert R8.DB_UPTO == "2026-09-18" and R8.PUB_DATE == "2026-09-18" and R8.DB_UPTO_CUT == "2026-09-11"
    same = ("WIN", "NREP", "NULL_SEED", "BAND_UP", "UP_MULT", "M1_RATIO", "R2_RATIO", "ALPHA", "MIN_N", "MIN_PULL", "CLUSTER_MIN", "TRUNC_GUARD", "DROP_GUARD", "NUP_CITE_BAN",
            "W10_DEGRADE", "LIMIT_UP")
    for k in same:
        assert getattr(R8, k) == getattr(R7, k), k
    assert R8.NULL_SEED == 20260815 and R8.NREP == 20_000 and abs(R8.M1_RATIO - 5 / 6) < 1e-12


def test_P2_denominator():
    assert R8.POST8_EXACT == intake_exact()
    assert [n for n, _c, _d in R8.POST8_EXACT] == ["우리로", "JW신약", "액스비스", "우리기술"]
    assert R8.POST8_NONE == [("원익", "032940")]
    assert R8.POST8_FOLLOWUP == [("빛과전자", "069540"), ("로보티즈", "108490"), ("범한퓨얼셀", "382900")]
    den = {c for _n, c, _d in R8.POST8_EXACT}
    assert not den & {c for _n, c in R8.POST8_NONE + R8.POST8_FOLLOWUP}
    assert R8.POST7 == R7.POST7_EXACT and R8.POST6 == R7.POST6 and R8.POST5 == R7.POST5 and R8.POST4 == R7.POST4
    assert R8.FROZEN_CUM == (R7.FROZEN_CUM[0] + 5, R7.FROZEN_CUM[1] + 6) == (24, 28)


def test_N1_poisoned_denominator():
    poisoned = list(R8.POST8_EXACT) + [(n, c, None) for n, c in R8.POST8_NONE + R8.POST8_FOLLOWUP]
    assert len(poisoned) == 8 != 4
    assert any(d is None for _n, _c, d in poisoned)


def test_P3_flags():
    assert R8.REENTRY == {} and R8.URIRO_CODE == "046970"
    assert R8.REENTRY_APPROX == {"234340": ["2026-08-28"], "047770": ["2026-08-21", "2026-08-19"]}
    assert sum(R8.PD3_FLAG_BR["234340"].values()) == 2 and sum(R8.PD3_FLAG_BR["047770"].values()) == 7
    inc = PD.read_text(encoding="utf-8").split("## PD-3")[1].split("## PD-4")[0]
    assert "헥토 2/7 갈래" in INTAKE.read_text(encoding="utf-8") and "코데즈 7/7 갈래" in INTAKE.read_text(encoding="utf-8")
    assert "**1**(7갈래 «전부»" in inc


def test_P4_trunc_guard_reuse():
    assert R8.guard_a_fires is R7.guard_a_fires
    assert R8.guard_a_fires(0, 4) is False and R8.guard_a_fires(1, 4) is False
    assert R8.guard_a_fires(2, 4) is True and R8.guard_a_fires(1, 0) is False


def test_P5_branches():
    for nm, _code, _lab, lo, hi, days in R8.APPROX_BRANCHES:
        assert (lo, hi) == ("2026-08-21", "2026-08-31") and days == R8.AUG_END and len(days) == 7
    assert len(R8.AUG_END) ** 2 == 49 and R8.CONTRA["234340"] == set(R8.AUG_END[:5])


def test_P6_d11_line_guard_bites():
    saved_tag, n0 = R8.Q1_TAG[0], len(R8.OUT)
    try:
        R8.Q1_TAG[0] = "〔D-11 병기: 이번 회차 `REG-M4` `n_up` 중앙 **75.5** · `PREREG_Q1_V2.md:66` x〕"
        with pytest.raises(AssertionError):
            R8.say("| `Q1-R2` | ✅ 지지 | " + R8.Q1_TAG[0] + " |")          # 금지어 「지지」
        with pytest.raises(AssertionError):
            R8.say("`Q1-R2` 성립 " + R8.Q1_TAG[0])                            # 금지어 「성립」(불성립도 잡힌다)
        with pytest.raises(AssertionError):
            R8.say("`Q1-R2` 문턱 충족 — 비율 기록")                            # 병기 없음
        R8.say("`Q1-R2` 문턱 충족 — 비율 기록 " + R8.Q1_TAG[0])               # 양성 대조
        R8.say("`P6-M1′` ✅ 지지 (Q1 과 무관한 줄)")                           # Q1-R2 가 없으면 검사 대상 아님
    finally:
        del R8.OUT[n0:]
        R8.Q1_TAG[0] = saved_tag


def test_P7_reuse_and_rule_txt():
    for fn in ("block", "bucket", "fmt_pct", "gstar", "load_universe_day", "measure", "null_gstar_a",
               "null_gstar_b", "null_p", "prev_trading_day", "universe_raw_count", "verdict_and"):
        assert getattr(R8, fn) is getattr(R6, fn), fn
    assert R8.market_days is R7.market_days and R8.snapshot_tail is R7.snapshot_tail
    assert R8.rule_txt(R6.verdict_and(True, True)).startswith("✅ 두 성분 충족(기록")
    assert R8.rule_txt(R6.verdict_and(False, False)) == R6.verdict_and(False, False)
    assert R6.OUT is R7.OUT, "post8 import 가 post6 버퍼를 가로챘다(post7 시험 P8 이 깨진다)"


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
    """산문 `RESULTS_REGDAY_POST8.md` 도 같은 줄 규칙(D-11)을 지킨다 — 병기의 `n_up` 중앙은 `_NUMBERS.md` 값."""
    med = re.search(r"`n_up` 중앙값 ([\d.]+)\*\*", numbers()).group(1)
    prose = (BASE / "RESULTS_REGDAY_POST8.md").read_text(encoding="utf-8")
    q = [ln for ln in prose.splitlines() if "Q1-R2" in ln]
    assert q
    for ln in q:
        assert "지지" not in ln and "성립" not in ln, ln
        assert "`PREREG_Q1_V2.md:66`" in ln and f"**{med}**" in ln, ln


def test_P9_numbers_duties():
    t = numbers()
    assert re.search(r"표준편차 \*\*[\d.]+\(`ddof=1`\)\*\* \([\d.]+ · `ddof=0`\) — \*「SSOT = `ddof=1`\(`PREREG_POST8.md` §6\)」\*", t)
    assert "`[이름 인용 금지]` 꼬리표 =" in t and "post6 의 발동 · post7 의 미발동을 **옮기지 않았다**" in t   # D-10
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 4 / `approx` 포함 분모 6」" in t        # D-3
    assert "09-18 봉은 D+1(09-21) sweep 이후 읽음" in t and "실행 stdout 에만 인쇄" in t                        # D-9 ①③
    assert re.search(r"창 `\[\d{4}-\d\d-\d\d, \d{4}-\d\d-\d\d\]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 \d+ 봉 / "
                     r"후 \d+ 봉 · 혼합 빈티지", t)
    assert "판정 창 걸침 = 0건" in t and "지목 범위 = `M1` 과 그 승계 `P6-M1′` «만»" in t
    assert "라이브 채택 대상이 아니다" in t and "GT-" not in t
    stamps = set(re.findall(r"2026-09-2[4-9] \d\d:\d\d:\d\d", t))
    assert stamps <= {R8.MGR["run"][:19]}, stamps
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
    m1 = [r for r in rows if r.startswith("| `P6-M1′` | ⇒ 종합")][0]
    ap = [r for r in rows if r.startswith("| `P6-M1′` | `approx` 포함 조합")][0]
    assert ("⛔ 판정 불가" in m1) == ("🔴 비율 문턱이 갈린다" in ap), (m1, ap)
    assert "🔴 **아니오 — 배선 결함**" not in t


def test_R1_post7_regday_suite():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = T7.main()
    assert rc == 0, buf.getvalue()[-2000:]
    assert "✅ 전건 통과" in buf.getvalue()
