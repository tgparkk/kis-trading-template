# -*- coding: utf-8 -*-
"""`run_anchor_redesign.py` 의 «가드 시험» — `ANC-` 축이 동결 문언대로 닫혀 있는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「맞다」만 보이면 비교자가 항상 통과하는
   장식일 수 있으므로, **일부러 흔든 사본에서 «불일치»가 나는지**도 같이 본다.
🔑 계열 규칙: *가드를 시험하지 않으면 그것도 장식이다*(`regen_gate.py` C-19 자기문언).

실행: `python test_post7_anchor.py`  (시스템 python · 라이브 트리 import 0건 · **DB 접속 0건**)

  P1 동결 상수 불변 (`END` 09-11 · `NULL_SEED` 20260815 · `S` 100 · Holm .0167 · 게이트 40 · 최소 n 3)
  P2 표본 — post7 `exact` 6 = INTAKE §1 · 「신규 10」 = 6+2+2 (민감도 갈래) · 소급 28 = post1~6 분포
  P3 `A1` 항등 — 합성 봉에서 `Z3(A1)` 전건 False · `h_obs(A1) ≤ 1` 전건 참 ·
     **§5-1 충족 개수에 «산입되지 않는다»**  (N1 대칭: 산입하는 셈법은 다른 수를 낸다)
  P4 후보 상호 배타 · `A0` 는 채택 후보 아님 · 채택 갈래가 「정확히 1 / 2 이상 / 0」으로 닫힌다
  P5 `ANC-N4` ① 축 항등 — 발행일 휴장이면 「당일 포함」 == 「직전 봉」 (N2 대칭: 거래일이면 갈린다)
     + 소스에 「구분 불가(항등)」가 있고 **①을 대체하는 정의가 없다**
  P6 `ANC-N5` 상수 검사 — 창의 `high` 가 한 값뿐인 합성 입력에서 **절차 무효**를 낸다
  P7 새 코드 0줄 — `win_bars`·`dd_h` 가 `run_reconstruct_post6` 객체 «그 자체» ·
     `DELTA`·`pairset`·`statV`·`NULL_SEED` 가 `run_ladder_tranche` 객체 «그 자체» · 복사 SQL 엔 출처 줄
  P8 `BUY-L5` — **재개 문구가 없다**(🔒 결정 ④) · 「결정 ④로 소멸」 문구가 있다
  P9 `--mode` 가 **필수** — 인자 없이 부르면 `SystemExit(2)`
  P10 `δ`·`V`·순열 표본을 **고치지 않았다**(§4-1) · `adj_factor` 산술 0건

🔴 어떤 원본 파일도 고치지 않는다. 동결본은 **메모리 사본**에서만 흔든다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import run_anchor_redesign as ANC
import run_ladder_tranche as LAD
import run_reconstruct_post6 as R6

BASE = Path(__file__).resolve().parent
SRC = (BASE / "run_anchor_redesign.py").read_text(encoding="utf-8")

FAILS: list[str] = []


def check(tag, cond, msg):
    print(f"  {'PASS' if cond else 'FAIL'}  {tag}  {msg}")
    if not cond:
        FAILS.append(f"{tag}: {msg}")


# ═══════════════════════════════════════════════════════════════════════════
# 가짜 커서 — DB 없이 앵커 계산을 돌린다. 동결 SQL 의 «형태»에 맞춰 답한다.
# ═══════════════════════════════════════════════════════════════════════════
class FakeCursor:
    """`bars = {code: [(date, low, high, close), ...]}` (date = 'YYYY-MM-DD' 정렬)."""

    def __init__(self, bars):
        self.bars = bars
        self._rows = []

    # ── 질의 ────────────────────────────────────────────────────────────
    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        b = self.bars.get(params[0], []) if params else []
        if s.startswith("SELECT min(low), max(high)"):
            w = [r for r in b if params[1] <= r[0] <= params[2]]
            self._rows = [(min(r[1] for r in w), max(r[2] for r in w))] if w else [(None, None)]
        elif s.startswith("SELECT max(high) FROM (SELECT high"):
            w = [r for r in b if r[0] <= params[1]][-params[2]:]
            self._rows = [(max(r[2] for r in w),)] if w else [(None,)]
        elif s.startswith("SELECT date FROM (SELECT date, high"):
            w = [r for r in b if r[0] <= params[1]][-params[2]:]
            self._rows = [(max(w, key=lambda r: (r[2], r[0]))[0],)] if w else []
        elif s.startswith("SELECT high FROM daily_prices"):
            w = [r for r in b if r[0] == params[1]]
            self._rows = [(w[0][2],)] if w else []
        elif s.startswith("SELECT date, low, high, close"):
            self._rows = [(r[0], r[1], r[2], r[3]) for r in b if params[1] <= r[0] <= params[2]]
        elif s.startswith("SELECT date, low, high FROM daily_prices") and "date <= %s" in s:
            w = [r for r in b if r[0] <= params[1]][-params[2]:]
            self._rows = [(r[0], r[1], r[2]) for r in w]
        elif s.startswith("SELECT date, low, high FROM daily_prices") and "date > %s" in s:
            w = [r for r in b if r[0] > params[1]][:params[2]]
            self._rows = [(r[0], r[1], r[2]) for r in w]
        else:                                           # pragma: no cover
            raise AssertionError("가짜 커서가 모르는 SQL: " + s[:90])

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def synth(code, n=10, base=1000.0, step=10.0, close_gap=5.0):
    """단조 상승 합성 봉 — `high` 가 전부 서로 다르다(`ANC-N5` 통과용)."""
    out = []
    for i in range(n):
        d = f"2026-09-{i + 1:02d}"
        hi = base + step * i
        out.append((d, hi - 30.0, hi, hi - close_gap))
    return {code: out}


# ═══════════════════════════════════════════════════════════════════════════
def t_p1():
    print("\nP1 — 동결 상수 불변")
    check("P1-1", ANC.END == "2026-09-11", f"END = {ANC.END} (PD-1 · 발행 09-12 토 휴장 ⇒ B-1)")
    check("P1-2", ANC.PUB7 == "2026-09-12", f"PUB7 = {ANC.PUB7}")
    check("P1-3", ANC.NULL_SEED == 20260815, f"NULL_SEED = {ANC.NULL_SEED} (새 시드 0개)")
    check("P1-4", ANC.NULL_SEED is LAD.NULL_SEED or ANC.NULL_SEED == LAD.NULL_SEED,
          "시드가 `run_ladder_tranche` 값 그대로다")
    check("P1-5", ANC.S_ANCHOR == 100, f"S = {ANC.S_ANCHOR}")
    check("P1-6", ANC.S_MIN_REQUIRED == 59 and ANC.S_ANCHOR >= ANC.S_MIN_REQUIRED,
          f"S >= 20m-1 = {ANC.S_MIN_REQUIRED} (§7-1 산술)")
    check("P1-7", abs(ANC.HOLM1 - 0.05 / 3) < 1e-12 and round(ANC.HOLM1, 4) == 0.0167,
          f"Holm 1단계 = {ANC.HOLM1:.4f}")
    check("P1-8", abs(ANC.PERM_MIN_P - 1 / 101) < 1e-12,
          f"순열 최소 p = 1/101 = {ANC.PERM_MIN_P:.4f} < {ANC.HOLM1:.4f}")
    check("P1-9", ANC.PERM_MIN_P < ANC.HOLM1, "최소 p 가 Holm 문턱보다 작다(검정이 성립 가능)")
    check("P1-10", ANC.MIN_N == 3, f"최소 n = {ANC.MIN_N} (§10)")
    check("P1-11", ANC.PAIR_GATE == 40 and ANC.PAIR_GATE == LAD.PAIR_THRESHOLD,
          f"비교가능 쌍 게이트 = {ANC.PAIR_GATE} (동결값 재사용 · 새 문턱 아님)")
    check("P1-12", ANC.M_TESTS == 3, f"주 검정 m = {ANC.M_TESTS}")
    seeds = [ANC.NULL_SEED + j for j in range(ANC.S_ANCHOR)]
    check("P1-13", seeds[0] == 20260815 and seeds[-1] == 20260914,
          f"R 시드 계열 = {seeds[0]} … {seeds[-1]} (§7-3)")


def t_p2():
    print("\nP2 — 표본 (판정 분모 · 민감도 갈래 · 소급)")
    intake_exact = [("서산", "079650", "2026-09-03"), ("강동씨엔앨", "198440", "2026-09-03"),
                    ("로보티즈", "108490", "2026-09-04"), ("해치텍", "0155E0", "2026-09-07"),
                    ("빛과전자", "069540", "2026-09-08"), ("범한퓨얼셀", "382900", "2026-09-09")]
    got = [(n, c, d) for n, c, d, *_ in ANC.POST7_EXACT]
    check("P2-1", got == intake_exact, f"post7 `exact` 6건이 INTAKE §1 과 전건 일치 ({len(got)}건)")
    check("P2-2", len(ANC.POST7_EXACT) == 6 and len(ANC.POST7_EXACT) >= ANC.MIN_N,
          "판정 분모 6 >= 최소 n 3 ⇒ `ANC-P1`·`ANC-P2` 가 «열린다»(§10)")
    new10 = len(ANC.POST7_EXACT) + len(ANC.POST7_APPROX) + len(ANC.POST7_NONE)
    check("P2-3", new10 == 10, f"「신규 10」 갈래 = 6 exact + 2 approx + 2 none = {new10} (민감도)")
    check("P2-4", new10 != len(ANC.POST7_EXACT),
          "🔴 신규 10 ≠ `exact` 6 — 두 정의가 «처음 갈린다»(충돌 신고 대상 · ANC-A-2)")
    check("P2-5", len(ANC.POST7_FOLLOWUP) == 3,
          "후속 3건(한라캐스트·아난티·우리기술투자)은 등록일 축 분모 «밖»(PD-2)")
    check("P2-6", set(ANC.WIN5_TRUNC) == {"빛과전자", "범한퓨얼셀"}
          and ANC.WIN5_TRUNC["빛과전자"] == 4 and ANC.WIN5_TRUNC["범한퓨얼셀"] == 3,
          f"창5 절단 2건 = {ANC.WIN5_TRUNC} (PD-12)")
    rein = [nm for nm, _c, _d, _n, _fo, reentry, _p in ANC.POST7_EXACT if reentry]
    prior = sum(p for *_x, p in ANC.POST7_EXACT)
    check("P2-7", rein == ["빛과전자"] and prior == 0,
          f"`exact` 안 재진입 = {rein} · 판정 분모 안 `PRIOR_CYCLE_IN_WINDOW` 합 = {prior} (PD-3)")
    # 소급 28 (원장 읽기 · DB 접속 0)
    retro = ANC.retro_items()
    from collections import Counter
    dist = Counter(i["post"] for i in retro)
    check("P2-8", len(retro) == 28,
          f"소급 post1~6 `exact` = {len(retro)}건 (§8 표 = 28)")
    check("P2-9", [dist.get(k, 0) for k in (1, 2, 3, 4, 5, 6)] == [0, 2, 3, 6, 7, 10],
          f"글별 분포 = {[dist.get(k, 0) for k in (1, 2, 3, 4, 5, 6)]} (§8 = 0·2·3·6·7·10)")
    check("P2-10", all(i["post_date"] <= ANC.RETRO_LAST_POST_DATE for i in retro),
          "소급이 post6(2026-09-04)에서 끊긴다 — post7 행이 붙어도 «탐색 열»로 새 들어오지 않는다")


def t_p3():
    print("\nP3 — `A1` 항등 (§5-3) + 산입 금지 대칭")
    code = "TEST1"
    cur = FakeCursor(synth(code, n=10))
    v = ANC.anchors_for(cur, code, "2026-09-01", "2026-09-10")
    check("P3-1", v["identity_ok"] is True,
          "항등 대조 — 옮겨 적은 창이 동결 `SELECT min(low), max(high)` 와 같은 값이다")
    check("P3-2", ANC.z3(v, "A1") is False,
          f"`Z3(A1)` = False (H1 {v['H1']} == HI {v['frozen_HI']}) — 정의상 0/n")
    check("P3-3", ANC.h_obs(v, "A1") <= 1.0,
          f"`h_obs(A1)` = {ANC.h_obs(v, 'A1'):.4f} <= 1 — 정의상(max close <= max high)")
    check("P3-4", ANC.z3(v, "A0") is True,
          "대조 — `A0`(등록일 고가)는 이 상승 합성에서 붕괴한다(판별력이 있다)")
    # 항등 조항 자체
    check("P3-5", ("A1", "ANC-P1") in ANC.IDENTITY_SLOTS
          and ("A1", "ANC-P2") in ANC.IDENTITY_SLOTS,
          "`A1` 의 두 자리가 `IDENTITY_SLOTS` 에 있다")
    check("P3-6", ANC.required_count("A1") == 1,
          "⇒ `A1` 은 §5-1 에서 **`ANC-P3` 하나로만** 결정된다(충족 개수 1 필요)")
    check("P3-7", all(ANC.required_count(c) == 3 for c in ("A2", "A3")),
          "`A2`·`A3` 는 셋 다 필요하다")
    # 🔑 대칭 단언 — 「항등을 세는」 셈법은 «다른 수»를 낸다
    naive = 1 + 1 + 1          # ok1·ok2·ok3 을 전부 세면
    frozen = ANC.cond_count("A1", True, True, True)
    check("N1-1", frozen == 1 and naive == 3 and frozen != naive,
          f"대칭 — 항등을 산입하면 {naive}, 동결 규칙은 {frozen} ⇒ 비교자가 장식이 아니다")
    check("N1-2", ANC.cond_count("A2", True, True, True) == 3,
          "대칭 — 항등 자리가 «없는» 후보는 셋이 그대로 세진다")
    check("N1-3", ANC.cond_count("A1", False, False, True) == 1,
          "`A1` 은 ①②가 거짓이어도 ③만으로 충족 개수 1 (산입 금지의 귀결)")


def t_p4():
    print("\nP4 — 후보 상호 배타 · 채택 세 갈래")
    check("P4-1", ANC.CANDIDATES == ("A0", "A1", "A2", "A3"), "후보 넷")
    check("P4-2", ANC.ADOPTABLE == ("A1", "A2", "A3") and "A0" not in ANC.ADOPTABLE,
          "🔴 `A0` 는 **대조군 전용** — 채택 후보가 아니다(§3)")
    check("P4-3", len(set(ANC.ADOPTABLE)) == len(ANC.ADOPTABLE),
          "상호 배타 — 중복 후보 없음")
    for tag, pat in (("정확히 1", "len(adopted) == 1"),
                     ("2 이상", "len(adopted) >= 2"),
                     ("0", "충족 후보 0")):
        check(f"P4-4[{tag}]", pat in SRC, f"§5-2 갈래 「{tag}」 분기가 소스에 있다")
    check("P4-5", "혼합 금지" in SRC,
          "🔴 혼합 금지(「`h` 는 `A1`, `DD` 는 `A3`」 조합) 문언이 있다")
    check("P4-6", "앵커 기반 축 전면 폐기" in SRC,
          "충족 0 갈래가 「전면 폐기 상신」으로 닫혀 있다")


def t_p5():
    print("\nP5 — `ANC-N4` ① 축 항등 (발행일 휴장)")
    cal_hol = ["2026-09-09", "2026-09-10", "2026-09-11"]            # 09-12(토) 없음 = 휴장
    ident, incl, prev = ANC.publish_bar_identity(cal_hol)
    check("P5-1", ident is True and incl == "2026-09-11" == prev,
          f"휴장 ⇒ 「당일 포함」={incl} 과 「직전 봉」={prev} 이 **같은 봉** ⇒ 구분 불가(항등)")
    # 🔑 대칭 단언 — 발행일이 «거래일»이면 두 정의가 갈린다(비교자가 상수가 아니다)
    cal_biz = ["2026-09-10", "2026-09-11", "2026-09-12"]
    ident2, incl2, prev2 = ANC.publish_bar_identity(cal_biz)
    check("N2-1", ident2 is False and incl2 == "2026-09-12" and prev2 == "2026-09-11",
          f"대칭 — 발행일이 거래일이면 갈린다({incl2} ↔ {prev2})")
    check("P5-2", "구분 불가(항등)" in SRC, "산출물 문언에 「구분 불가(항등)」가 있다")
    check("P5-3", "①을 다른 정의로 «대체하지 않는다»" in SRC,
          "🔴 ①을 다른 정의로 대체하지 않는다는 문언이 있다(PD-14 1번)")
    check("P5-4", "②·③ 두 축으로만" in SRC,
          "①이 항등이면 ②·③ 두 축으로만 `ANC-N4` 를 판정한다")
    # ① 을 「대체」하는 흔적이 없는지 — 대체 정의를 쓰면 END 가 두 값이어야 한다
    ends = set(re.findall(r'^END = "(\d{4}-\d{2}-\d{2})"', SRC, re.M))
    check("P5-5", ends == {"2026-09-11"},
          f"창 종료가 «한 값»뿐이다 {sorted(ends)} — ①을 대체하는 두 번째 창이 없다")


def t_p6():
    print("\nP6 — `ANC-N5` 대조군 상수 검사")
    flat = {"FLAT": [(f"2026-09-{i+1:02d}", 900.0, 1000.0, 990.0) for i in range(6)]}
    highs = [r[2] for r in flat["FLAT"]]
    check("P6-1", len({float(h) for h in highs}) == 1,
          "합성 입력 — 창의 `high` 가 **한 값**뿐이다")
    # `random_anchor_highs` 가 어느 시드에서도 같은 값만 낸다 ⇒ 상수 ⇒ 절차 무효
    rows = [dict(name="FLAT", highs=highs)]
    drawn = {ANC.random_anchor_highs(rows, j)[0] for j in range(ANC.S_ANCHOR)}
    check("P6-2", len(drawn) == 1,
          f"`H_R` 실현값이 {len(drawn)}가지 ⇒ **상수** ⇒ `ANC-N5` **절차 무효**(`WRC-X1` 3번)")
    check("P6-3", "절차 무효" in SRC and "ANC-N5" in SRC,
          "소스에 `ANC-N5` 절차 무효 분기가 있다")
    # 🔑 대칭 — 서로 다른 high 가 있으면 상수가 아니다
    ok = [dict(name="OK", highs=[r[2] for r in synth("X", n=8)["X"]])]
    drawn2 = {ANC.random_anchor_highs(ok, j)[0] for j in range(ANC.S_ANCHOR)}
    check("N3-1", len(drawn2) > 1,
          f"대칭 — 서로 다른 `high` 가 있으면 `H_R` 실현값이 {len(drawn2)}가지(상수 아님)")
    # 결정성 — 같은 시드는 같은 값
    check("P6-4", ANC.random_anchor_highs(ok, 7) == ANC.random_anchor_highs(ok, 7),
          "같은 시드는 같은 `H_R` (결정적)")


def t_p7():
    print("\nP7 — 새 코드 0줄 (동결 코드 재사용의 «객체 동일성»)")
    check("P7-1", ANC.win_bars is R6.win_bars,
          "`win_bars` 가 `run_reconstruct_post6` 의 객체 «그 자체»(§3 `A2` 출처)")
    check("P7-2", ANC.dd_h is R6.dd_h,
          "`dd_h` 가 `run_reconstruct_post6` 의 객체 «그 자체»(§3 `A3` 출처)")
    for nm in ("pairset", "statV", "permute_null"):
        check(f"P7-3[{nm}]", getattr(ANC, nm) is getattr(LAD, nm),
              f"`{nm}` 이 `run_ladder_tranche` 의 객체 «그 자체»")
    check("P7-4", ANC.DELTA == LAD.DELTA == 1.0 and ANC.NPERM == LAD.NPERM == 200_000,
          f"`δ` = {ANC.DELTA}%p · 순열 {ANC.NPERM:,} — 동결값 그대로(§4-1 「고치지 않는다」)")
    # 옮겨 적은 SQL 에는 출처 줄이 있다
    for fn in ("frozen_lo_hi", "frozen_h_back", "frozen_h0", "window_bars"):
        body = (getattr(ANC, fn).__doc__ or "")
        check(f"P7-5[{fn}]", "출처" in body or "run_reconstruct_post6" in body,
              f"`{fn}` docstring 에 출처 줄이 있다")
    check("P7-6", "permute_null_strat" in SRC and "유일한 추가 자유도" in SRC,
          "층화 순열이 §7-2 의 «유일한 추가 자유도 1개»로 신고돼 있다")
    # 라이브 트리 import 0건
    bad = re.findall(r"^\s*(?:from|import)\s+(utils|core|api|strategies|config)\b", SRC, re.M)
    check("P7-7", not bad, f"라이브 트리 import 0건 (발견 {bad})")


def t_p8():
    print("\nP8 — `BUY-L5` (🔒 결정 ④로 소멸)")
    check("P8-1", "결정 ④로 소멸" in SRC or "결정 ④로 «자동 소멸»" in SRC,
          "「결정 ④로 소멸」 문언이 있다(PD-13 1번 · `342f6f0`)")
    resume = re.findall(r"`BUY-L5`[^\n]{0,40}재개(?!\s*조항)", SRC)
    resume = [r for r in resume if "소멸" not in r]
    check("P8-2", not resume, f"`BUY-L5` 를 «재개»한다는 문구가 없다 (발견 {resume})")
    check("P8-3", "BUY-L5" not in SRC.split("## §7")[-1].split("⇒ 🟢 **채택")[-1][:400]
          or "소멸" in SRC.split("⇒ 🟢 **채택")[-1][:400],
          "채택 갈래에서도 `BUY-L5` 는 「소멸」로만 등장한다")


def t_p9():
    print("\nP9 — `--mode` 필수 (C-23)")
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf):             # argparse 사용법 인쇄를 삼킨다
            ANC.main([])
        check("P9-1", False, "인자 없이 호출했는데 SystemExit 이 안 났다")
    except SystemExit as e:
        check("P9-1", e.code == 2, f"인자 없이 부르면 SystemExit({e.code}) (argparse required)")
    except Exception as e:                                # noqa: BLE001
        check("P9-1", False, f"예상 밖 예외: {type(e).__name__}")
    check("P9-3", "required" in buf.getvalue(),
          "argparse 가 「required」라고 말한다(가드가 도는 증거)")
    check("P9-2", 'required=True' in SRC and 'choices=("post7",)' in SRC,
          "`--mode` 가 `required=True` 이고 choices 가 닫혀 있다")


def t_p10():
    print("\nP10 — 규약 (δ·V 불변 · adj_factor · 소급 각주 · 라이브 금지)")
    check("P10-1", "adj_factor" in SRC and "곱하지 않는다" in SRC,
          "`adj_factor` 를 가격에 곱하지 않는다는 문언이 있다")
    check("P10-2", "라이브 채택 대상이 아니다" in SRC, "라이브 채택 금지 문언이 있다(`PREREG.md` §0-2)")
    check("P10-3", "소급 = 탐색 · 채택은 post7 열로만" in ANC.RETRO_FOOTNOTE,
          "§5-4 매 표 각주 문언이 상수로 박혀 있다")
    check("P10-4", SRC.count("RETRO_FOOTNOTE") >= 3,
          f"그 각주가 여러 표에 쓰인다({SRC.count('RETRO_FOOTNOTE')}회)")
    check("P10-5", "문턱을 낮춰 열지 않는다" in SRC,
          "🔴 게이트 문턱 하향 금지 조항(§10)이 있다")
    check("P10-6", "`WRC-` 판정 분모를 쓰지 않는다" in SRC,
          "§2-3 — `WRC-` 분모를 쓰지 않는다는 문언이 있다")
    # 🔴 6줄 — 소급 창 정정(글별 발행일 `END`)으로 «소급 열의 창은 글마다 짧다» 한 줄이
    #    추가됐다. 수를 «세는» 것이 목적이 아니라 **한 줄이 조용히 사라지지 않는지** 보는 것이다.
    check("P10-7", len(ANC.LIMITS) == 6, f"§13 한계 {len(ANC.LIMITS)}줄이 인쇄된다")
    check("P10-8", "창 종료 2026-09-11" in SRC or ('**{END}** = 발행일' in SRC)
          or "발행일({PUB7} 토) 휴장 ⇒ 마지막 거래일" in SRC,
          "§0 창 종료 규약 줄이 있다")
    check("P10-9", "max(date)" in SRC and "창으로 쓰지 않는다" in SRC,
          "실행 시 `max(date)` 를 «기록만» 한다(PD-1 5번)")


def main():
    print("=" * 78)
    print("test_post7_anchor — `run_anchor_redesign.py` 가드 시험 (DB 접속 0건)")
    print("=" * 78)
    for fn in (t_p1, t_p2, t_p3, t_p4, t_p5, t_p6, t_p7, t_p8, t_p9, t_p10):
        fn()
    print("\n" + "=" * 78)
    if FAILS:
        print(f"🔴 FAIL {len(FAILS)}건")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("🟢 전건 PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
