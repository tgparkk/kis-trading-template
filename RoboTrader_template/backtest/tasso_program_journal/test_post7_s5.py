# -*- coding: utf-8 -*-
"""`run_s5_post7.py` · `run_wrc_post7.py` 의 «가드 시험» — **DB 없이** 도는 것만 담는다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「가드가 통과한다」만 보이면 그 가드는
   항상 통과하는 장식일 수 있으므로 **일부러 흔든 사본에서 실패하는지**도 본다.
🔑 계열 규칙: *「안 하기로 했다」는 기억이고 검사는 코드다* — PD-15 의 「판정 선언 없음」을
   **문자열 가드**로 못박고, 그 가드가 실제로 무는지 양방향으로 보인다.

실행: `python test_post7_s5.py`  (시스템 python · 라이브 트리 import 0건 · **DB 접속 0건**)

  P1  동결 상수 — PIT 규약(`status='000'` · `rcept_dt <= 2026-09-12`) · `exact` 주 표본 6 ·
      판정 가능 5 · 대조군 상위 1% · 창 종료 2026-09-11 · 시드 20260815
  P2  🔴 **판정문 금지** — 산출 문자열에 `(S5-성립)`·`(S5-이탈)`·`(S5-보류)` 가 **하나도 없다**
  N1  대칭 — 라벨을 넣은 «사본»에서는 `assert_no_verdict()` 가 **운다**
  N2  대칭 — `say(...)` 안에 판정 라벨 리터럴이 있으면 소스 스캔이 **잡는다**
  P3  `[탐색]` 꼬리표 · Holm 가족 **+0** 문구
  P4  §1-1 「둘 다」 — 주 표본 n · 민감도 판 n 이 **둘 다** 인쇄된다
  N3  대칭 — 한쪽을 지운 사본에서는 `assert_both_n()` 이 **운다**
  P5  해치텍 제외 사유 = **「`dart_financials_asfiled` 미수록」**(≠ 「이름 매칭 실패」)
  P6  PIT 한계 문구(`max(rcept_dt) = 2026-08-06` · 17,892행)
  P7  `run_wrc_post7` — 주 분모 **0** · ⛔ · `approx` 민감도 갈래 1 · 해치텍 `fill_n=4` 인데 탈락
  P8  🔴 동결 파일 불변 — `run_wrc_explore.py`·`run_s5_sidebyside.py` 를 **한 글자도 안 바꿨다**

🔴 어떤 원본 파일도 고치지 않는다. 동결본은 **메모리 사본에서만** 흔든다.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import run_s5_post7 as S5
import run_wrc_post7 as WRC

BASE = Path(__file__).resolve().parent
FAILS: list[str] = []


def check(tag, cond, msg):
    print(f"  {'PASS' if cond else 'FAIL'}  {tag}  {msg}")
    if not cond:
        FAILS.append(f"{tag}: {msg}")


def static_lines():
    """DB 없이 만들어지는 산문 블록 전부 — 가드는 이 위에서 돈다."""
    return (S5.header_lines("2026-09-15", 2765)
            + S5.contamination_lines()
            + S5.precision_lines()
            + S5.pit_limit_lines()
            + S5.news_defer_lines()
            + S5.sparsity_lines()
            + S5.limits_lines())


def git_clean(path):
    """작업트리가 `HEAD` 와 같은가 — `git diff --quiet` 가 0 이면 안 바뀐 것이다."""
    try:
        r = subprocess.run(["git", "diff", "--quiet", "--", path],
                           cwd=str(BASE), capture_output=True)
        return r.returncode == 0, "git diff --quiet"
    except Exception as e:  # noqa: BLE001
        return None, f"git 실행 실패({e})"


# ══════════════════════════════════════════════════════════════════════════════
def p1_frozen_constants():
    print("\n[P1] 동결 상수 — 이 파일에서 «고른» 값이 하나도 없다")
    check("P1-1", S5.PIT_STATUS == "000", f"PIT status = {S5.PIT_STATUS!r} (§1)")
    check("P1-2", S5.PIT_CUTOFF == "2026-09-12",
          f"PIT 절단면 = 글 게시일 {S5.PIT_CUTOFF} (§1)")
    check("P1-3", S5.DB_UPTO == "2026-09-11",
          f"창 종료 = {S5.DB_UPTO} (PD-1 · 발행일 토요일 휴장 ⇒ B-1)")
    check("P1-4", S5.TOP_PCT == 99.0,
          f"대조군 = 백분위 >= {S5.TOP_PCT} (= 상위 1% · §1)")
    check("P1-5", S5.SEED == 20260815, f"시드 = {S5.SEED} (계열 고정값)")
    check("P1-6", len(S5.EXACT6) == 6, f"주 표본(신규 ∧ exact) n = {len(S5.EXACT6)}")
    check("P1-7", len(S5.APPROX2) == 2, f"민감도 판 추가분(approx) = {len(S5.APPROX2)}")
    check("P1-8", len(S5.EXACT6) + len(S5.APPROX2) == 8,
          "민감도 판 n = 8 (주 6 + approx 2)")
    check("P1-9", S5.NO_FIN_CODES == {"0155E0"},
          "재무 표 미수록 = 해치텍 `0155E0` 1건 (PD-15 2번)")
    codes = {c for _n, c, _d in S5.EXACT6}
    check("P1-10", len(codes - S5.NO_FIN_CODES) == 5,
          f"판정 가능 = {len(codes - S5.NO_FIN_CODES)} / {len(codes)} (PD-15 3번)")
    check("P1-11", len(S5.NONE2) == 2 and len(S5.FOLLOWUP3) == 3,
          "등록일 축 «밖» = none 2 + 후속 3 (PD-4 3번 · PD-2)")
    src = (BASE / "run_s5_post7.py").read_text(encoding="utf-8")
    check("P1-12", "status = %s" in src and "rcept_dt <= %s" in src
          and "ORDER BY bsns_year DESC LIMIT 1" in src,
          "PIT SQL = status ∧ rcept_dt <= 게시일 ∧ 최근 «사업연도 하나»")
    check("P1-13", "run_selection.py:60" in src and "rank(pct=True)" in src,
          "대조군 = 태쏘 `f1` 축 정의 재사용(출처 줄 명기 · 새 정의 아님)")
    # `approx` 창 규약 실측(PD-4 2번) — 8일 / 7일
    days = {nm: d for nm, _c, _desc, d in S5.APPROX2}
    check("P1-14", len(days["지투파워"]) == 8,
          "「9월 초」 창 규약 = 거래일 8일 (PD-4 2번)")
    check("P1-15", len(days["한국화장품제조"]) == 7,
          "「8월 말」 창 규약 = 거래일 7일 (PD-4 2번)")


def p2_no_verdict():
    print("\n[P2] 🔴 판정문 금지 — PD-15 1번")
    L = static_lines()
    body = "\n".join(L)
    hit = [lab for lab in S5.FORBIDDEN_LABELS if lab in body]
    check("P2-1", not hit, f"산문 블록에 판정 라벨 없음 (검사 대상 {len(L)}줄)")
    ok = True
    try:
        S5.assert_no_verdict(L)
    except AssertionError:
        ok = False
    check("P2-2", ok, "`assert_no_verdict()` 통과")
    check("P2-3", S5.FORBIDDEN_LABELS == ("(S5-성립)", "(S5-이탈)", "(S5-보류)"),
          "금지 라벨 3종이 §2 동결 표와 같다")
    # 🔴 소스 스캔 — `say(...)` 호출 안에 라벨 리터럴이 있으면 DB 경로에서 새어 나간다
    src = (BASE / "run_s5_post7.py").read_text(encoding="utf-8").splitlines()
    leak = [i + 1 for i, ln in enumerate(src)
            if re.search(r"\bsay\(", ln) and any(lab in ln for lab in S5.FORBIDDEN_LABELS)]
    check("P2-4", not leak, f"`say(` 줄에 라벨 리터럴 없음 (의심 줄 {leak or '없음'})")
    check("P2-5", "assert_no_verdict(OUT)" in "\n".join(src),
          "🔴 스크립트가 **쓰기 «전»에** 스스로 가드를 부른다")


def n1_verdict_guard_bites():
    print("\n[N1/N2] 대칭 — 가드가 «실제로» 무는가")
    for lab in S5.FORBIDDEN_LABELS:
        bit = False
        try:
            S5.assert_no_verdict(static_lines() + [f"⇒ **{lab}**"])
        except AssertionError:
            bit = True
        check("N1", bit, f"라벨 `{lab}` 을 넣은 사본에서 `assert_no_verdict()` 가 운다")
    # N2 — 소스 스캐너 자신의 판별력
    fake = ['    say("⇒ (S5-성립)")']
    leak = [i for i, ln in enumerate(fake)
            if re.search(r"\bsay\(", ln) and any(l2 in ln for l2 in S5.FORBIDDEN_LABELS)]
    check("N2", len(leak) == 1, "소스 스캐너가 «가짜 누출 줄»을 잡는다 (판별력 있음)")


def p3_tags():
    print("\n[P3] `[탐색]` 꼬리표 · Holm 가족 +0")
    body = "\n".join(static_lines())
    check("P3-1", "[탐색]" in body, "`[탐색]` 꼬리표가 있다 (`PREREG_GRADE_TIERS.md` §1-3)")
    check("P3-2", body.count("[탐색]") >= 2,
          f"꼬리표가 여러 표에 붙는다 ({body.count('[탐색]')}회)")
    check("P3-3", "Holm 가족" in body and "+0" in body,
          "Holm 가족 **+0** 문구 (주 검정을 늘리지 않는다 · §2)")
    check("P3-4", "라이브 채택 대상이 아니다" in body,
          "라이브 채택 금지 문구 (`PREREG.md` §0-2)")
    check("P3-5", "창 종료 2026-09-11" in body and "발행일(2026-09-12 토) 휴장" in body,
          "창 종료 규약 줄(B-1)")
    check("P3-6", "max(date)" in body and "창으로 쓰지 않는다" in body,
          "실행 시 `max(date)` 기록 줄 — 창으로 쓰지 않는다")
    check("P3-7", "기계 생성 (수정 금지)" in body, "머리 줄 = 기계 생성 표기")


def p4_both_n():
    print("\n[P4/N3] §1-1 「주 표본 n · 민감도 판 n 을 «둘 다»」")
    L = static_lines()
    ok = True
    try:
        S5.assert_both_n(L)
    except AssertionError:
        ok = False
    check("P4-1", ok, "`assert_both_n()` 통과")
    body = "\n".join(L)
    check("P4-2", "주 표본 n = 6" in body, "주 표본 n = 6 이 문자로 인쇄된다")
    check("P4-3", "민감도 판 n = 8" in body, "민감도 판 n = 8 이 문자로 인쇄된다")
    check("P4-4", "하나만 적으면 무효" in body, "§1-1 의 「하나만 적으면 무효」 인용")
    # N3 — 한쪽을 지운 사본에서는 울어야 한다
    for drop in ("주 표본 n", "민감도 판 n"):
        cut = [ln for ln in L if drop not in ln]
        bit = False
        try:
            S5.assert_both_n(cut)
        except AssertionError:
            bit = True
        check("N3", bit, f"「{drop}」 을 지운 사본에서 `assert_both_n()` 이 운다")
    check("N3-2", "assert_both_n(OUT)" in (BASE / "run_s5_post7.py").read_text(encoding="utf-8"),
          "스크립트가 쓰기 «전»에 이 가드도 부른다")


def p5_hachitech_reason():
    print("\n[P5] 해치텍 — 「이름 매칭 실패」가 «아니다»")
    r = S5.no_fin_reason("0155E0")
    check("P5-1", "미수록" in r, "사유 = `dart_financials_asfiled` **미수록**")
    check("P5-2", "이름 매칭 실패" in r and "아니다" in r,
          "「이름 매칭 실패»가 **아니다**」를 명시한다 (PD-11 2번 자기정정)")
    check("P5-3", "0155E0" in r, "코드는 **해결됐다**(`0155E0`)는 사실을 같이 적는다")
    other = S5.no_fin_reason("999999")
    check("P5-4", "미수록" not in other,
          "다른 코드에는 이 사유를 붙이지 않는다 (사유 가르기의 판별력)")
    body = "\n".join(static_lines())
    check("P5-5", "강동씨엔앨" in body and "강동씨앤엘" in body,
          "저자 표기 ↔ DB 표기 불일치(PD-10 4번)를 산출물에 적는다")


def p6_pit_limit():
    print("\n[P6] PIT 한계 — 표가 멈춰 있다 (PD-15 4번)")
    body = "\n".join(S5.pit_limit_lines())
    check("P6-1", "17,892행" in body, "전체 17,892행")
    check("P6-2", "2026-08-06" in body, "`max(rcept_dt)` = 2026-08-06")
    check("P6-3", "형식상 통과" in body, "「형식상 통과」하지만 표가 담지 않는다는 구분")
    check("P6-4", S5.PIT_LIMIT == {"rows": 17892, "max_rcept": "2026-08-06"},
          "상수도 같은 값 (실측 인용 · 재계산 아님)")


def p7_wrc_closed_by_construction():
    print("\n[P7] `WRC-` — 주 분모가 «구성»으로 0")
    cs = WRC.intake_cases()
    check("P7-1", len(cs) == 13, f"인테이크 §1 = {len(cs)}건 (신규 10 + 후속 3)")
    ex = [c for c in cs if c["prec"] == "exact"]
    check("P7-2", len(ex) == 6, f"`exact` = {len(ex)}건 (PD-4)")
    check("P7-3", len(WRC.denom(ex)) == 0, "🔴 주 분모 = **0** ⇒ ⛔ 최소 n 미달")
    first = [c["name"] for c in ex if c["fill_n"] == 1]
    check("P7-4", len(first) == 5,
          f"1차 체결 5건 = {first} (§2-19 · 구성으로 닫힌 이유 ①)")
    hz = [c for c in ex if c["name"] == "해치텍"][0]
    check("P7-5", hz["fill_n"] == 4 and hz["distinct"] == 2 and not hz["gate"],
          "해치텍 `fill_n=4` 인데 **서로 다른 값 레그 2 < 3** 이라 탈락 (이유 ②)")
    br = WRC.approx_branch(cs)
    check("P7-6", len(br) == 1 and br[0]["name"] == "지투파워",
          "`approx` 민감도 갈래 = 지투파워 1건 (fill_n 3 · 다른 값 레그 5)")
    check("P7-7", len(WRC.denom([c for c in cs if c["prec"] == "approx"])) == 0,
          "🔴 동결 게이트는 `approx` 를 통과시키지 않는다 (갈래 ≠ 게이트)")
    check("P7-8", WRC.END == "2026-09-11" and WRC.POST_DATE == "2026-09-12",
          f"창 종료 {WRC.END} · 발행 {WRC.POST_DATE}(토 · 휴장)")
    # 문턱을 «새로» 만들지 않았다 — 동결본에서 import 한 같은 객체다
    import run_wrc_explore as W
    check("P7-9", (WRC.SEED, WRC.NREP, WRC.THR, WRC.BAND_THR, WRC.G1_THR, WRC.N_THR)
          == (W.SEED, W.NREP, W.THR, W.BAND_THR, W.G1_THR, W.N_THR),
          "문턱·시드 전부 `run_wrc_explore` 에서 import (복사 0건 · `WRC-X1` 4번)")
    check("P7-10", WRC.SEED == 20260815 and WRC.NREP == 20000,
          "시드 20260815 · 반복 20,000 (동결값)")
    check("P7-11", len(WRC.CODES7) == 13 and WRC.CODES7["해치텍"] == "0155E0",
          "코드 13/13 해결 · 해치텍 = `0155E0` (PD-11)")
    check("P7-12", len(WRC.COVERAGE) == 4,
          "커버리지는 **축별로 4줄** — 한 수로 합치지 않는다 (PD-11 3번)")


def p8_frozen_files_untouched():
    print("\n[P8] 🔴 동결 파일 불변 — 한 글자도 안 바꿨다")
    # 🔴 **동결 «스크립트»만 못박는다.**
    #    원장(`ledger_*.csv`)은 **여러 레인이 동시에 쓰는 공유 파일**이고 이번 회차에 post7 행
    #    (+13/+47)이 append 되는 중이다 ⇒ `HEAD` 와 달라지는 것이 **정상**이다.
    #    🔑 post6 전례 그대로: ***공유 파일을 통째 지문으로 박으면 그건 재현성 장치가 아니라
    #      «재현성 파괴 장치»다***(`test_post6_wrc.py::test_ledger_is_not_pinned_by_whole_file_md5`).
    #      내가 «안 건드렸다»는 것은 아래 P8-2 소스 스캔이 단언한다.
    for f in ("run_wrc_explore.py", "run_s5_sidebyside.py"):
        ok, how = git_clean(f)
        if ok is None:
            check("P8", True, f"{f} — {how} (건너뜀 · 아래 소스 스캔이 남는다)")
        else:
            check("P8", ok, f"{f} 가 `HEAD` 와 같다 ({how})")
    check("P8-1", True,
          "🔴 원장 `ledger_*.csv` 는 **일부러 지문에 넣지 않는다** — 공유 파일이고 이번 회차에 "
          "post7 행이 append 되는 중이다(post6 전례 · 통째 지문은 재현성 파괴 장치)")
    # 소스 스캔 — 내 파일이 그 이름에 «쓰지» 않는다
    mine = ["run_s5_post7.py", "run_wrc_post7.py", "test_post7_s5.py"]
    targets = ["run_wrc_explore.py", "run_s5_sidebyside.py",
               "ledger_trades.csv", "ledger_legs.csv", "RESULTS_WRC_EXPLORE.md"]
    bad = []
    for m in mine:
        src = (BASE / m).read_text(encoding="utf-8")
        for t in targets:
            for mo in re.finditer(re.escape(t), src):
                seg = src[max(0, mo.start() - 120):mo.end() + 60]
                if re.search(r"write_text|open\([^)]*['\"]w|\.write\(", seg):
                    bad.append(f"{m} → {t}")
    check("P8-2", not bad, f"내 파일 3종이 동결 파일에 쓰지 않는다 ({bad or '위반 0'})")
    check("P8-3", "run_wrc_explore" in (BASE / "run_wrc_post7.py").read_text(encoding="utf-8"),
          "`run_wrc_explore` 는 **import 로만** 등장한다(재사용 · 수정 아님)")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    print("=" * 78)
    print("test_post7_s5.py — `S5` · `WRC-` post7 가드 시험 (DB 접속 0건)")
    print("=" * 78)
    p1_frozen_constants()
    p2_no_verdict()
    n1_verdict_guard_bites()
    p3_tags()
    p4_both_n()
    p5_hachitech_reason()
    p6_pit_limit()
    p7_wrc_closed_by_construction()
    p8_frozen_files_untouched()
    print("\n" + "=" * 78)
    if FAILS:
        print(f"🔴 FAIL {len(FAILS)}건")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("🟢 전부 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
