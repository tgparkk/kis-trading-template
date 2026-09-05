# -*- coding: utf-8 -*-
"""`run_ladder_tranche_post6.py` 의 «가드 시험» — 누적 재계산이 기존 값을 흔들지 않았는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「일치한다」만 보이면 비교자가
   항상 통과하는 장식일 수 있으므로 **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *회귀 판정은 실패 «집합»의 양방향 차분* — 12건 전건을 열별로 대조한다.

실행: `python test_post6_ladder.py`  (시스템 python · 라이브 트리 import 0건 · **DB 접속 0건**)

  P1 동결 상수 불변 (`delta` 1.0 · 시드 20260815 · 순열 200,000 · 게이트 40)
  P2 `ITEMS` 구성 — 앞 12건이 `run_ladder_tranche.ITEMS` 와 «완전히 같다» + 신규 10건이 INTAKE §1 과 일치
  P3 산출물 대조 — 기존 12건의 `DD3`·`DD5`·`DD_A`·`E`·`sigma20` 이 동결본
     `RESULTS_LADDER_TRANCHE.md` §2 와 **전건 일치**(= 기존 계산 경로 불변의 증거)
  N1 대칭 — 동결본 값 하나를 흔든 사본에서는 P3 의 비교가 **불일치를 낸다**
  P4 통계 핵(`pairset`·`statV`) — 완전 정렬이면 `V`=0 · 완전 역정렬이면 `V`=comp
  P5 `P6-창5절단가드-A` 산술 — 2/10 미발동 · 1/3·3/9·4/10 발동(문턱은 등호 포함)
  P6 `verdict_t1` — 게이트 미달이면 「보류」 · `p`<0.05 면 「지지후보」 · 아니면 「불성립」
  P7 산출물 필수 문구 — DB 최신 봉·창 종료 규약·라이브 채택 금지·절단 플래그 2건

🔴 어떤 원본 파일도 고치지 않는다. 동결본은 메모리 사본에서만 흔든다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import run_ladder_tranche as LAD
import run_ladder_tranche_post6 as P6

BASE = Path(__file__).resolve().parent
FROZEN = BASE / "RESULTS_LADDER_TRANCHE.md"
NUMBERS = BASE / "RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md"

# `INTAKE_2026-09-04_post6.md` §1 — 신규 10건 (종목, 코드, 등록일, 차수 N)
INTAKE_NEW10 = [
    ("한라캐스트", "125490", "2026-08-21", 5),
    ("헥토파이낸셜", "234340", "2026-08-28", 1),
    ("아난티", "025980", "2026-08-19", 1),
    ("아이티센글로벌", "124500", "2026-08-20", 3),
    ("현대약품", "004310", "2026-09-01", 2),
    ("원익", "032940", "2026-08-31", 3),
    ("쿠콘", "294570", "2026-08-28", 1),
    ("지투파워", "388050", "2026-08-26", 3),
    ("우리기술투자", "041190", "2026-08-25", 4),
    ("비에이치", "090460", "2026-09-01", 4),
]
FOLLOWUP_EXCLUDED = ["광전자", "삼양바이오팜"]   # PD-2 — 후속 2건은 신규 분모 밖

FAILS: list[str] = []


def check(tag, cond, msg):
    print(f"  {'PASS' if cond else 'FAIL'}  {tag}  {msg}")
    if not cond:
        FAILS.append(f"{tag}: {msg}")


def table_rows(text, first_col_is_index=True):
    """마크다운 표에서 `| 1 | 종목 | ... |` 꼴 행만 셀 리스트로 돌려준다."""
    out = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 12 or not first_col_is_index:
            continue
        if re.fullmatch(r"\d+", cells[1] or ""):
            out.append(cells)
    return out


def legacy_map(text):
    """(종목, 글) -> (DD3, DD5, DD_A, E, sigma20) — 두 산출물 형식 모두에서 같은 열을 뽑는다."""
    m = {}
    for cells in table_rows(text):
        pcts = re.findall(r"(\d+\.\d+)%", " | ".join(cells))
        if len(pcts) != 3:
            continue
        key = (cells[2], cells[3])
        m[key] = (pcts[0], pcts[1], pcts[2], cells[10], cells[11])
    return m


def main():
    print("== P1. 동결 상수 불변 ==")
    check("P1", P6.DELTA == 1.0, f"delta = {P6.DELTA}")
    check("P1", P6.NULL_SEED == 20260815, f"NULL_SEED = {P6.NULL_SEED}")
    check("P1", P6.NPERM == 200_000, f"NPERM = {P6.NPERM:,}")
    check("P1", P6.PAIR_THRESHOLD == 40, f"게이트 = {P6.PAIR_THRESHOLD}")
    check("P1", (P6.DELTA, P6.NULL_SEED, P6.NPERM, P6.PAIR_THRESHOLD)
          == (LAD.DELTA, LAD.NULL_SEED, LAD.NPERM, LAD.PAIR_THRESHOLD),
          "동결 생성기와 같은 값을 쓴다(재정의 0)")
    check("P1", P6.END == "2026-09-04" and P6.PUB6 == "2026-09-04",
          f"END = {P6.END} · 발행일 = {P6.PUB6} (PD-1 · 발행 당일 봉 포함)")

    print("== P2. ITEMS 구성 ==")
    check("P2", len(P6.ITEMS) == 22, f"누적 표본 {len(P6.ITEMS)}건 (12 + 10)")
    check("P2", list(P6.ITEMS[:12]) == list(LAD.ITEMS),
          "앞 12건이 동결 생성기의 ITEMS 와 완전히 같다(한 글자도 안 고쳤다)")
    got = [(it[0], it[1], it[2], it[3]) for it in P6.ITEMS[12:]]
    check("P2", got == INTAKE_NEW10, "신규 10건이 INTAKE §1(종목·코드·등록일·차수)과 일치")
    check("P2", sorted(it[3] for it in P6.ITEMS[12:]) == [1, 1, 1, 2, 3, 3, 3, 4, 4, 5],
          "신규 차수 다중집합 = INTAKE §2-4 분포 1:3 · 2:1 · 3:3 · 4:2 · 5:1")
    new_names = [it[0] for it in P6.ITEMS[12:]]
    check("P2", all(n not in new_names for n in FOLLOWUP_EXCLUDED),
          f"후속 2건({', '.join(FOLLOWUP_EXCLUDED)})이 신규 분모에 없다 (PD-2 이중계상 금지)")
    seconds = [it[0] for it in P6.ITEMS if it[6]]
    check("P2", seconds == ["코데즈컴바인", "한켐", "현대약품", "지투파워"],
          f"2번째 사이클 플래그 = {seconds} (B-7 + PD-3)")

    print("== P3 / N1. 기존 12건 값 불변 (동결본 §2 대조) ==")
    if not NUMBERS.exists():
        check("P3", False, f"{NUMBERS.name} 이 없다 — 먼저 run_ladder_tranche_post6.py 를 실행할 것")
    else:
        frozen = legacy_map(FROZEN.read_text(encoding="utf-8"))
        mine = legacy_map(NUMBERS.read_text(encoding="utf-8"))
        keys = [k for k in mine if k[1] in ("post4", "post5")]
        check("P3", len(keys) == 12, f"산출물의 기존 행 {len(keys)}건")
        diffs = [f"{k[0]}({k[1]}) {frozen.get(k)} != {mine[k]}" for k in keys
                 if frozen.get(k) != mine[k]]
        check("P3", not diffs, "DD3·DD5·DD_A·E·sigma20 전건 일치"
              + ("" if not diffs else " — 불일치: " + " / ".join(diffs)))
        # N1 대칭 — 비교자가 실제로 불일치를 잡는지
        shaken = dict(frozen)
        k0 = keys[0]
        v = list(shaken[k0])
        v[1] = "99.99"
        shaken[k0] = tuple(v)
        caught = [k for k in keys if shaken.get(k) != mine[k]]
        check("N1", len(caught) == 1 and caught[0] == k0,
              f"동결본 DD5 하나를 99.99 로 흔들면 정확히 그 1건({k0[0]})만 불일치로 잡힌다")

    print("== P4. 통계 핵 (pairset · statV) ==")
    # `V` = 「낙폭이 큰 쪽의 차수가 더 «작은»」 쌍 수 = 사다리 «위반» 수(§4-4).
    # ⇒ 「완전 사다리」 = 차수가 클수록 낙폭도 크다 ⇒ V = 0.
    ns = [1, 2, 3, 4]
    ps, dropped = P6.pairset([10.0, 20.0, 30.0, 40.0], P6.DELTA)
    V, comp = P6.statV(ns, ps)
    check("P4", (V, comp, dropped) == (0, 6, 0),
          f"완전 사다리(차수↑ ⇒ 낙폭↑) ⇒ 위반 V={V} · comp={comp} · 버린 쌍={dropped}")
    V2, comp2 = P6.statV(ns, P6.pairset([40.0, 30.0, 20.0, 10.0], P6.DELTA)[0])
    check("P4", (V2, comp2) == (6, 6), f"완전 역정렬 ⇒ 위반 V={V2}/{comp2} (대칭 단언)")
    ps3, dropped3 = P6.pairset([20.0, 20.5, 30.0], P6.DELTA)
    check("P4", dropped3 == 1 and len(ps3) == 2,
          f"|차이| <= delta(1.0%p) 인 쌍 1개를 버린다 (버린 쌍={dropped3})")

    print("== P5. P6-창5절단가드-A 산술 ==")
    check("P5", P6.guard_a_fires(2, 10) is False, "2/10 = 20% < 1/3 ⇒ 미발동 (이번 글)")
    check("P5", P6.guard_a_fires(1, 3) is True, "1/3 = 33.3% ⇒ 발동 (문턱은 등호 포함 · §1-6 5번)")
    check("P5", P6.guard_a_fires(3, 9) is True, "3/9 ⇒ 발동")
    check("P5", P6.guard_a_fires(4, 10) is True, "4/10 = 40% ⇒ 발동")

    print("== P6. verdict_t1 (LAD-T1 결정규칙 §5-2) ==")
    check("P6", P6.verdict_t1(dict(comp=39, p=0.01)) == "보류", "비교가능 39 < 40 ⇒ 보류")
    check("P6", P6.verdict_t1(dict(comp=41, p=0.0499)) == "지지후보", "40 이상 ∧ p<0.05 ⇒ 지지후보")
    check("P6", P6.verdict_t1(dict(comp=161, p=0.4914)) == "불성립", "40 이상 ∧ p>=0.05 ⇒ 불성립")
    check("P6", P6.verdict_t1(dict(comp=161, p=0.05)) == "불성립", "p = 0.05 는 지지가 아니다(등호)")

    print("== P7. 산출물 필수 문구 ==")
    if NUMBERS.exists():
        t = NUMBERS.read_text(encoding="utf-8")
        for tag, needle in [
            ("DB 최신 봉", "**DB 최신 봉 = `2026-09-04`**"),
            ("창 종료 규약", "발행 당일 봉 «포함»"),
            ("라이브 채택 금지", "라이브 채택 대상이 아니다"),
            ("절단 건수", "**절단 건수 = 2**"),
            ("가드-A 산술", "**2/10 = 20.0%**"),
            ("누적 쌍 재계산", "post5 누적 **41**"),
            ("T3 부호 감시", "부호 감시"),
            ("LAD-P1 분모 정의", "분모 정의 = 「DB 있는 신규 건」"),
        ]:
            check("P7", needle in t, f"{tag} — `{needle}`")
        check("P7", t.count("**1**") >= 2 and "현대약품" in t and "비에이치" in t,
              "P6-WIN5_TRUNC = 1 인 행이 2건(현대약품·비에이치)")

    print()
    if FAILS:
        print(f"🔴 실패 {len(FAILS)}건")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("✅ 전건 통과")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
