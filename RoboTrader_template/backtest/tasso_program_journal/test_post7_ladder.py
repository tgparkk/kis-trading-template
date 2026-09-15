# -*- coding: utf-8 -*-
"""`run_ladder_tranche_post7.py` 의 «가드 시험» — 누적 재계산이 기존 값을 흔들지 않았는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「일치한다」만 보이면 비교자가
   항상 통과하는 장식일 수 있으므로 **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *회귀 판정은 실패 «집합»의 양방향 차분* — 누적 22건 전건을 대조한다.

실행: `python test_post7_ladder.py`  (시스템 python · 라이브 트리 import 0건 · **DB 접속 0건**)
      `python test_post7_ladder.py --require-artifact`   ← 판정 실행 «뒤» 관리자가 쓴다

  P1 동결 상수 불변 (`delta` 1.0 · 시드 20260815 · 순열 200,000 · 게이트 40 · `END` 2026-09-11)
  P2 `ITEMS` 구성 — 앞 22건이 `run_ladder_tranche_post6.ITEMS` 와 «완전히 같다»
     + post7 주 표본 6건이 INTAKE §1 의 `exact` 6건과 일치 + 등록일 축 밖 5건이 들어오지 않았다
  P3 상류 모듈 **무수정** — post6·post4/5 목록과 통계 핵이 import 로만 온다(재정의 0)
  N1 대칭 — 메모리 사본에서 한 칸을 흔들면 P2 의 비교가 **불일치를 낸다**
  P4 통계 핵(`pairset`·`statV`) — 완전 정렬이면 `V`=0 · 완전 역정렬이면 `V`=comp
  P5 `P6-창5절단가드-A` 산술 — 2/10 미발동 · **2/6 발동**(등호 포함) · 3/10 미발동 · 1/3·4/10 발동
  P6 PD-12 4번 «대체» 재료 — post6 동결본의 「절단 시점 값」을 **인용대로** 들고 있다
     (24.00 / 14.00 · 4봉) + post6 `ITEMS` 행이 그대로다(= 옛 파일을 안 고쳤다)
  P7 `verdict_t1` 분기 — 게이트 미달 「보류」 · p<0.05 「지지후보」 · p>=0.05 「불성립」
  P8 산출물 필수 문구 (🟡 산출물이 아직 없으면 **PENDING** — `--require-artifact` 로 강제)
  P9 (곁다리) `run_d1_oos_post7.py` — DB 조회 0회 계약(`psycopg2` 미import) · 13항목 · 미룸 3회차

🔴 어떤 원본 파일도 고치지 않는다. 동결본은 메모리 사본에서만 흔든다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import run_ladder_tranche as LAD
import run_ladder_tranche_post6 as P6
import run_ladder_tranche_post7 as P7

BASE = Path(__file__).resolve().parent
NUMBERS6 = BASE / "RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md"
NUMBERS7 = BASE / "RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md"

REQUIRE_ARTIFACT = "--require-artifact" in sys.argv

# `INTAKE_2026-09-15_post7.md` §1 — 신규 10건 중 `exact` 6건 (종목, 코드, 등록일, 차수 N)
INTAKE_EXACT6 = [
    ("서산", "079650", "2026-09-03", 1),
    ("강동씨엔앨", "198440", "2026-09-03", 1),
    ("로보티즈", "108490", "2026-09-04", 1),
    ("해치텍", "0155E0", "2026-09-07", 4),
    ("빛과전자", "069540", "2026-09-08", 1),
    ("범한퓨얼셀", "382900", "2026-09-09", 1),
]
# `INTAKE` §2-12 — 신규 10건 전체 차수 분포 1:6 · 3:1 · 4:2 · 5:1
INTAKE_NEW10_NS = [1, 1, 1, 1, 1, 1, 3, 4, 4, 5]
# PD-2 / PD-4 3번 — 등록일 축 «밖» 5건 (후속 3 + `none` 2)
OUT_OF_AXIS = ["한전기술", "한전산업", "한라캐스트", "아난티", "우리기술투자"]
# PD-4 — `approx` 2건도 주 표본에 없다(§7-1 갈래 민감도)
APPROX2 = ["지투파워", "한국화장품제조"]

FAILS: list[str] = []
PENDING: list[str] = []


def check(tag, cond, msg):
    print(f"  {'PASS' if cond else 'FAIL'}  {tag}  {msg}")
    if not cond:
        FAILS.append(f"{tag}: {msg}")


def pending(tag, msg):
    print(f"  PEND  {tag}  {msg}")
    PENDING.append(f"{tag}: {msg}")


def main():  # noqa: C901
    print("== P1. 동결 상수 불변 ==")
    check("P1", P7.DELTA == 1.0, f"delta = {P7.DELTA}")
    check("P1", P7.NULL_SEED == 20260815, f"NULL_SEED = {P7.NULL_SEED}")
    check("P1", P7.NPERM == 200_000, f"NPERM = {P7.NPERM:,}")
    check("P1", P7.PAIR_THRESHOLD == 40, f"게이트 = {P7.PAIR_THRESHOLD}")
    check("P1", (P7.DELTA, P7.NULL_SEED, P7.NPERM, P7.PAIR_THRESHOLD)
          == (LAD.DELTA, LAD.NULL_SEED, LAD.NPERM, LAD.PAIR_THRESHOLD),
          "동결 생성기와 같은 값을 쓴다(재정의 0)")
    check("P1", P7.END == "2026-09-11", f"END = {P7.END} (PD-1 · 창 종료)")
    check("P1", P7.PUB7 == "2026-09-12",
          f"발행일 = {P7.PUB7} (**토요일 = 휴장** ⇒ 창A 는 END 에서 끝난다 · B-1)")
    check("P1", P7.PUB7 > P7.END,
          "🔴 발행일 > 창 종료 — post6(발행일 = 거래일 = 창 종료)과 «구조가 다른» 회차다")
    check("P1", P7.TRUNC5_MIN_BARS == P6.TRUNC5_MIN_BARS == 5, "창5 = 5봉 (동결)")
    check("P1", (P7.GUARD_A_NUM, P7.GUARD_A_DEN) == (1, 3), "가드-A 문턱 = 1/3 (차용 고지 승계)")
    check("P1", (P7.N_NEW_POST7, P7.N_EXACT_POST7) == (10, 6),
          "🔴 가드-A 분모 10(이번 글 신규) ≠ 주 표본 6(`exact`) — 이 계열 최초로 갈린다(PD-4)")
    check("P1", (P7.LAD_P2_LO, P7.LAD_P2_HI) == (15.0, 35.0), "`LAD-P2` 구간 15~35% (동결)")

    print("== P2. ITEMS 구성 ==")
    check("P2", len(P7.ITEMS) == 28, f"누적 표본 {len(P7.ITEMS)}건 (22 + 6)")
    check("P2", list(P7.ITEMS[:22]) == list(P6.ITEMS),
          "앞 22건이 post6 판의 ITEMS 와 완전히 같다(한 글자도 안 고쳤다)")
    check("P2", list(P7.ITEMS[:12]) == list(LAD.ITEMS),
          "앞 12건이 동결 생성기의 ITEMS 와도 완전히 같다(2단 승계 확인)")
    got = [(it[0], it[1], it[2], it[3]) for it in P7.ITEMS[22:]]
    check("P2", got == INTAKE_EXACT6, "post7 주 표본 6건이 INTAKE §1 `exact`(종목·코드·등록일·차수)와 일치")
    check("P2", sorted(it[3] for it in P7.ITEMS[22:]) == [1, 1, 1, 1, 1, 4],
          "post7 주 표본 차수 다중집합 = [1,1,1,1,1,4]")
    new7_names = [it[0] for it in P7.ITEMS[22:]]
    check("P2", all(n not in new7_names for n in OUT_OF_AXIS),
          f"등록일 축 밖 5건({', '.join(OUT_OF_AXIS)})이 주 표본에 없다 (PD-2 · PD-4 3번)")
    check("P2", all(n not in new7_names for n in APPROX2),
          f"`approx` 2건({', '.join(APPROX2)})도 주 표본에 없다 — §7-1 갈래 민감도 (PD-4 1번)")
    check("P2", [n for n, *_ in P7.OUT_OF_REGDAY_AXIS] == OUT_OF_AXIS,
          "등록일 축 밖 표가 5건 그대로 있다(사유를 라벨과 분리해 적는 자리)")
    check("P2", sorted(INTAKE_NEW10_NS) == [1, 1, 1, 1, 1, 1, 3, 4, 4, 5]
          and INTAKE_NEW10_NS.count(1) == 6,
          "INTAKE §2-12 신규 10건 분포 = 1:6 · 3:1 · 4:2 · 5:1 (post6 보다 1차에 몰려 있다)")
    seconds = [it[0] for it in P7.ITEMS if it[6]]
    check("P2", seconds == ["코데즈컴바인", "한켐", "현대약품", "지투파워", "빛과전자"],
          f"2번째 사이클 플래그 = {seconds} (B-7 + PD-3 · 주 표본 안은 빛과전자 1건)")
    check("P2", P7.PRIOR_CYCLE_FLAG_POST7 == {"지투파워": 1, "한국화장품제조": 1, "빛과전자": 0},
          "`P6-PRIOR_CYCLE_IN_WINDOW` = PD-3 표 그대로")
    check("P2", P7.PRIOR_CYCLE_IN_MAIN == ["빛과전자"]
          and P7.PRIOR_CYCLE_FLAG_POST7["빛과전자"] == 0,
          "🔴 주 표본 안 재진입은 1건이고 그 플래그가 **0** ⇒ 판정 분모 안 플래그 = 0 (INTAKE §5 머리말)")
    check("P2", len(P7.FIRST_ONLY_POST7_NEW) == 6 and len(P7.FIRST_ONLY_POST7_EXACT) == 5,
          "`first_only` 신규 6 · 그중 `exact` 5 (PD-13 · post6 3건의 두 배)")

    print("== N1. 대칭 — 비교자가 실제로 불일치를 잡는가 ==")
    shaken = [list(t) for t in P7.ITEMS[:22]]
    shaken[0][3] = 99                      # post4 이노테크의 차수 N 을 흔든다
    caught = [i for i, (a, b) in enumerate(zip(shaken, P6.ITEMS)) if tuple(a) != tuple(b)]
    check("N1", caught == [0],
          "누적 22건 중 한 칸(이노테크 N)을 흔들면 정확히 그 1건만 불일치로 잡힌다")
    shaken2 = [list(t) for t in P7.ITEMS[22:]]
    shaken2[3][1] = "015500"               # 해치텍 코드를 흔든다
    got2 = [(t[0], t[1], t[2], t[3]) for t in shaken2]
    check("N1", got2 != INTAKE_EXACT6 and sum(
        1 for a, b in zip(got2, INTAKE_EXACT6) if a != b) == 1,
          "post7 6건 중 코드 하나(해치텍 `0155E0`)를 흔들면 정확히 1건이 INTAKE 와 갈린다")

    print("== P3. 상류 모듈 무수정 (import 재사용) ==")
    for nm in ("pairset", "statV", "permute_null", "run_axis"):
        check("P3", getattr(P7, nm) is getattr(LAD, nm),
              f"`{nm}` 이 `run_ladder_tranche` 의 «그 객체»다(복사·재정의 아님)")
    for nm in ("guard_a_fires", "verdict_t1", "median"):
        check("P3", getattr(P7, nm) is getattr(P6, nm),
              f"`{nm}` 이 `run_ladder_tranche_post6` 의 «그 객체»다(복사·재정의 아님)")
    check("P3", P7.ITEMS[:22] is not P6.ITEMS and list(P7.ITEMS[:22]) == list(P6.ITEMS),
          "누적 목록은 «새 리스트»지만 내용은 동일 — 상류 리스트를 제자리에서 변형하지 않았다")
    check("P3", LAD.OUT is P7.OUT,
          "🔴 `LAD.OUT` 이 post7 버퍼에 묶여 있다(post6 import «뒤»에 재지정 — 표 행이 샐 자리 없음)")
    check("P3", P7.ITEMS_CUM22 is P6.ITEMS, "누적 22건을 post6 에서 **import 로** 가져왔다")

    print("== P4. 통계 핵 (pairset · statV) ==")
    # `V` = 「낙폭이 큰 쪽의 차수가 더 «작은»」 쌍 수 = 사다리 «위반» 수(§4-4).
    ns = [1, 2, 3, 4]
    ps, dropped = P7.pairset([10.0, 20.0, 30.0, 40.0], P7.DELTA)
    V, comp = P7.statV(ns, ps)
    check("P4", (V, comp, dropped) == (0, 6, 0),
          f"완전 사다리(차수↑ ⇒ 낙폭↑) ⇒ 위반 V={V} · comp={comp} · 버린 쌍={dropped}")
    V2, comp2 = P7.statV(ns, P7.pairset([40.0, 30.0, 20.0, 10.0], P7.DELTA)[0])
    check("P4", (V2, comp2) == (6, 6), f"완전 역정렬 ⇒ 위반 V={V2}/{comp2} (대칭 단언)")
    ps3, dropped3 = P7.pairset([20.0, 20.5, 30.0], P7.DELTA)
    check("P4", dropped3 == 1 and len(ps3) == 2,
          f"|차이| <= delta(1.0%p) 인 쌍 1개를 버린다 (버린 쌍={dropped3})")

    print("== P5. P6-창5절단가드-A 산술 ==")
    check("P5", P7.guard_a_fires(2, 10) is False,
          "2/10 = 20% < 1/3 ⇒ **미발동** (이번 글 주 분모 = 신규 10 · PD-12 3번)")
    check("P5", P7.guard_a_fires(2, 6) is True,
          "🔴 2/6 = 33.3% ⇒ **발동 조건에 «닿는다»** (`exact` 갈래 · 등호 포함 · 숨기지 않는다)")
    check("P5", P7.guard_a_fires(3, 10) is False,
          "3/10 = 30% ⇒ 미발동 — `approx` 갈래(지투파워) 포함해도 **불변** (PD-12 5번)")
    check("P5", P7.guard_a_fires(1, 3) is True, "1/3 = 33.3% ⇒ 발동 (문턱은 등호 포함 · §1-6 5번)")
    check("P5", P7.guard_a_fires(4, 10) is True, "4/10 = 40% ⇒ 발동")
    check("P5", P7.guard_a_fires(1, 6) is False,
          "1/6 = 16.7% ⇒ 미발동 — `P6-절단가드-A`(해치텍 10/20 · §1-2)와 같은 산술")

    print("== P6. PD-12 4번 «대체» 재료 — 인용이 동결본과 일치하는가 ==")
    check("P6", set(P7.POST6_TRUNC_ASOF) == {"현대약품", "비에이치"},
          "대체 대상 = post6 절단 2건(현대약품·비에이치)")
    check("P6", all(v["n5_asof"] == 4 for v in P7.POST6_TRUNC_ASOF.values()),
          "절단 시점 창5 봉수 = 4봉 (규정 5봉 미달)")
    if NUMBERS6.exists():
        t6 = NUMBERS6.read_text(encoding="utf-8")
        m = re.search(r"\*\*절단 건수 = 2\*\*", t6)
        check("P6", m is not None, "post6 동결본에 「**절단 건수 = 2**」 가 있다")
        for nm, ref in P7.POST6_TRUNC_ASOF.items():
            needle = f"{nm}({ref['d0']} 등록 · 창5 **{ref['n5_asof']}봉**"
            check("P6", needle in t6, f"동결본 §1-1 에 `{needle}…` 가 있다")
            check("P6", f"DD5 = **{ref['dd5_asof']:.2f}%**" in t6,
                  f"{nm} 절단 시점 DD5 = {ref['dd5_asof']:.2f}% 가 동결본 값과 일치(인용 · 재계산 아님)")
        # N1 대칭 — 틀린 값을 넣으면 위 비교가 잡아야 한다
        check("N1", "DD5 = **99.99%**" not in t6,
              "대칭: 없는 값(99.99%)은 동결본에서 안 잡힌다 ⇒ 위 비교가 장식이 아니다")
    else:
        pending("P6", f"{NUMBERS6.name} 이 없다 — 인용 대조를 못 했다")
    p6_rows = {it[0]: it for it in P7.ITEMS[:22]}
    check("P6", "창5 절단" in p6_rows["현대약품"][7] and "창5 절단" in p6_rows["비에이치"][7],
          "🔴 post6 행의 비고가 「창5 절단」 **그대로**다 — 옛 파일을 고치지 않았다는 증거"
          "(대체는 산출물 안에서만 인쇄한다)")

    print("== P7. verdict_t1 (LAD-T1 결정규칙 §5-2) ==")
    check("P7", P7.verdict_t1(dict(comp=39, p=0.01)) == "보류", "비교가능 39 < 40 ⇒ 보류")
    check("P7", P7.verdict_t1(dict(comp=41, p=0.0499)) == "지지후보", "40 이상 ∧ p<0.05 ⇒ 지지후보")
    check("P7", P7.verdict_t1(dict(comp=161, p=0.4914)) == "불성립", "40 이상 ∧ p>=0.05 ⇒ 불성립")
    check("P7", P7.verdict_t1(dict(comp=161, p=0.05)) == "불성립", "p = 0.05 는 지지가 아니다(등호)")

    print("== P8. 산출물 필수 문구 ==")
    if NUMBERS7.exists():
        t = NUMBERS7.read_text(encoding="utf-8")
        for tag, needle in [
            ("머리말", "# RESULTS_LADDER_TRANCHE_POST7_NUMBERS — 기계 생성 (수정 금지)"),
            ("창 종료 규약", "창 종료 2026-09-11 = 발행일(2026-09-12 토) 휴장 ⇒ 마지막 거래일"),
            ("실행 시 max(date)", "실행 시 `max(date)`"),
            ("라이브 채택 금지", "라이브 채택 대상이 아니다"),
            ("절단 건수", "**절단 건수 = 2**"),
            ("가드-A 주 분모", "**2/10 = 20.0%**"),
            ("가드-A exact 갈래", "**2/6 = 33.3%**"),
            ("PD-12 4번 대체", "§1-1b"),
            ("대체 인용 고지", "왼쪽 열은 인용이다 — 재계산하지 않았다"),
            ("md5 불변", "한 byte 도 고치지 않았다"),
            ("누적 쌍 재계산", "post6 누적 **161**"),
            ("T3 부호 감시", "부호 감시"),
            ("LAD-T1 영구 취소", "`LAD-T1` 영구 취소"),
            ("LAD-P2 하한 관찰", "**15.62%**"),
            ("LAD-P1 분모 정의", "분모 정의 = 「DB 있는 신규 건」"),
            ("approx 갈래 민감도", "§7-1"),
            ("두 민감도 분리", "합치지 않는다"),
            # 🔴 **선재 결함 정정** — 바늘이 산출물 축자와 달랐다(`는` 한 글자 + 겹화살괄호).
            #    산출물은 *「라벨을 이유로 빠지지 «않는다»」* 라고 쓴다(`run_ladder_tranche_post7.py:274`).
            #    🔑 바늘이 틀리면 이 검사는 «항상 실패»해서 아무도 안 보게 된다 — 문구를 고친 게 아니라 «바늘»을 고쳤다.
            ("B-2 carve-out 고지", "라벨을 이유로 빠지지 «않는다»"),
        ]:
            check("P8", needle in t, f"{tag} — `{needle}`")
        check("P8", t.count("| **1** |") >= 2 and "빛과전자" in t and "범한퓨얼셀" in t,
              "`P6-WIN5_TRUNC` = 1 인 행이 2건(빛과전자·범한퓨얼셀)")
    elif REQUIRE_ARTIFACT:
        check("P8", False, f"{NUMBERS7.name} 이 없다 — `--require-artifact` 인데 판정을 안 돌렸다")
    else:
        pending("P8", f"{NUMBERS7.name} 미생성 — **판정 실행 «뒤» `--require-artifact` 로 재실행 의무**")

    print("== P9. (곁다리) run_d1_oos_post7.py — DB 조회 0회 계약 ==")
    before = "psycopg2" in sys.modules
    import run_d1_oos_post7 as D7
    check("P9", D7.DB_UPTO == "2026-09-11" and D7.PUB7 == "2026-09-12",
          f"창 종료 {D7.DB_UPTO} · 발행일 {D7.PUB7} (옮겨 적은 값 · 조회하지 않는다)")
    check("P9", len(D7.ITEMS) == 13, f"판정 대상 라벨 {len(D7.ITEMS)}개 전부 ⛔ 미룸 (PD-6)")
    check("P9", sum(n for *_x, n in D7.CLASSES) == 0 and all(n == 0 for _w, n in D7.GREP_WORDS),
          "부류 A~F 전부 0 · grep 낱말(거래대금·배·시총) 전부 0 — 「완전 부재」")
    check("P9", D7.DEFER_STREAK == 3, "`TV-W1`·`W2` 누적 미룸 = 3글 연속(5·6·7번째)")
    check("P9", D7.PRIOR_TOTAL == (12, 6), "누적 재현 12건 중 6 — post5 이후 불변(재계산 0)")
    check("P9", not hasattr(D7, "psycopg2") and ("psycopg2" in sys.modules) == before,
          "🔴 모듈이 `psycopg2` 를 import 하지 않는다 — DB 조회 0회 계약")

    print()
    if PENDING:
        print(f"🟡 PENDING {len(PENDING)}건 (산출물 미생성 — 판정 실행 뒤 재실행)")
        for p in PENDING:
            print(f"  - {p}")
    if FAILS:
        print(f"🔴 실패 {len(FAILS)}건")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("✅ 전건 통과" + (" (PENDING 제외)" if PENDING else ""))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
