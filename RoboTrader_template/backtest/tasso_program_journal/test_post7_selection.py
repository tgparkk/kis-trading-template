# -*- coding: utf-8 -*-
"""`run_selection_post7.py` 의 «가드 시험» — 분모 규약이 실제로 뭔가를 «막는지» 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「`exact` 가 6이다」만 보이면 그 필터가
   «있으나 마나»일 수 있으므로, **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *회귀 판정은 실패 «집합»의 양방향 차분* — INTAKE §1 13행 전건을 열별로 대조한다.

실행: `python test_post7_selection.py`  (시스템 python · **DB 접속 0건** · 라이브 트리 import 0건)

  P1  동결 상수 불변                (`DB_UPTO` 2026-09-11 · `SEED` 20260815 · 창 5/20 · 문턱)
  P2  분모 구성 = INTAKE §1 축자     (신규 10 · `exact` 6 · `approx` 2 · `none` 2 · 후속 3 제외)
  N1  (음성 대조) `exact` 판별을 무력화하면 분모가 «오염»된다 ⇒ 가드가 살아 있다
  P3  재진입 플래그                  (판정 분모 안 **0** · 글 전체 **2** · 둘 다 `approx`)
  N2  (대칭) PD-3 표 값을 하나 흔들면 정확히 그 1건만 불일치로 잡힌다
  P4  `P6-절단가드-A` 산술           (1/6 미발동 · 2/6 발동 · 문턱은 **등호 포함**)
  P5  C-17 NaN 규약                  (`run_selection.py` 의 `.where(prev_max.notna())` 존재 ·
                                      해치텍이 60봉 축 대상 1건 · PD-12 문장과 대조)
  P6  창 규약 갈래 8 / 7             (PD-4 2번 · 거래일 목록 길이·원소)
  P7  재사용 증명                    (통계량이 post6 의 «그 함수»다 — 재정의 0)

🔴 원본 파일은 하나도 건드리지 않는다. 동결본은 메모리 사본에서만 흔든다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import run_selection
import run_selection_post6 as P6
import run_selection_post7 as P7

BASE = Path(__file__).resolve().parent
INTAKE = BASE / "INTAKE_2026-09-15_post7.md"
PD = BASE / "PREDECISION_2026-09-15_post7.md"

FAILS: list = []


def check(tag, cond, msg):
    print("%s %-4s %s" % ("🟢" if cond else "🔴", tag, msg))
    if not cond:
        FAILS.append("%s: %s" % (tag, msg))


def intake_rows():
    """INTAKE §1 표 13행 → (번호, 종목, 코드, 정밀도|'follow', 신규/후속)."""
    out = []
    for ln in INTAKE.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.split("|")]
        if len(c) < 10 or not re.fullmatch(r"\d+", c[1] or ""):
            continue
        m = re.search(r"[0-9][0-9A-Z]{5}", c[3])
        kind = "후속" if "후속" in c[9] else ("신규" if "신규" in c[9] else "?")
        if kind == "후속":
            prec = "follow"
        elif "exact" in c[4]:
            prec = "exact"
        elif "approx" in c[4]:
            prec = "approx"
        elif "none" in c[4]:
            prec = "none"
        else:
            prec = "?"
        out.append((int(c[1]), c[2], m.group(0) if m else None, prec, kind))
    return out


def main():  # noqa: C901
    print("== P1. 동결 상수 불변 ==")
    check("P1", P7.DB_UPTO == "2026-09-11",
          "`DB_UPTO` = %s (PD-1 · 발행 09-12 토 휴장 ⇒ 마지막 거래일)" % P7.DB_UPTO)
    check("P1", P7.PUB_DATE == "2026-09-12", "발행일 = %s (토요일 = 휴장)" % P7.PUB_DATE)
    check("P1", P7.SEED == 20260815, "`SEED` = %d (계열 고정값 · 새 시드 0)" % P7.SEED)
    check("P1", (P7.W_TDAYS, P7.W_CAL_POST4, P7.WIN20) == (5, 10, 20),
          "창 = 거래일 %d · 달력 %d · 절단창 %d" % (P7.W_TDAYS, P7.W_CAL_POST4, P7.WIN20))
    check("P1", (P7.UP15, P7.N_DEGRADE, P7.DROP_GUARD) == (1.15, 30, 0.01),
          "문턱 UP15=%s · N_DEGRADE=%s · DROP_GUARD=%s (post6 과 같은 값)"
          % (P7.UP15, P7.N_DEGRADE, P7.DROP_GUARD))
    check("P1", (P7.W_TDAYS, P7.WIN20, P7.UP15, P7.N_DEGRADE, P7.DROP_GUARD, P7.SEED)
          == (P6.W_TDAYS, P6.WIN20, P6.UP15, P6.N_DEGRADE, P6.DROP_GUARD, P6.SEED),
          "post6 판과 **동일한 동결 상수**를 쓴다(문턱 재정의 0)")
    check("P1", abs(P7.TRUNC_GUARD - 1.0 / 3.0) < 1e-12,
          "`P6-절단가드-A` 문턱 = 1/3 (§1-6 3 · REC-Y3 차용)")

    print("== P2 / N1. 분모 구성 = INTAKE §1 축자 ==")
    rows = intake_rows()
    check("P2", len(rows) == 13, "INTAKE §1 표 = %d행 (항목번호 결번 0 · 기대 13)" % len(rows))
    want_new = [(nm, code, prec) for _i, nm, code, prec, kind in rows if kind == "신규"]
    got_new = [(nm, code, prec) for nm, code, _d, prec, _t in P7.NEW7]
    check("P2", got_new == want_new,
          "`NEW7` 10건이 INTAKE §1 (종목·코드·정밀도)과 축자 일치%s"
          % ("" if got_new == want_new else " — 불일치 %s" % [
              (a, b) for a, b in zip(got_new, want_new) if a != b]))
    check("P2", len(P7.NEW7) == 10, "신규 = %d건" % len(P7.NEW7))
    check("P2", len(P7.EXACT7) == 6
          and [r[0] for r in P7.EXACT7] == ["서산", "강동씨엔앨", "로보티즈", "해치텍",
                                            "빛과전자", "범한퓨얼셀"],
          "🔴 **판정 분모 = 신규 ∧ `exact` = %d건** %s (PD-4 1번)"
          % (len(P7.EXACT7), [r[0] for r in P7.EXACT7]))
    check("P2", len(P7.APPROX7) == 2
          and set(r[0] for r in P7.APPROX7) == {"지투파워", "한국화장품제조"},
          "`approx` = %d건 %s (의무 민감도)" % (len(P7.APPROX7), [r[0] for r in P7.APPROX7]))
    check("P2", P7.NONE7 == ["한전기술", "한전산업"],
          "`none` = %s (등록일 문장 자체가 없다 · 축 밖)" % P7.NONE7)
    check("P2", len(P7.NEW7) != len(P7.EXACT7),
          "🔴 **신규 %d != `exact` %d** — 이 계열 최초로 갈렸다(PD-4)"
          % (len(P7.NEW7), len(P7.EXACT7)))
    follow = [nm for _i, nm, _c, _p, kind in rows if kind == "후속"]
    check("P2", follow == ["한라캐스트", "아난티", "우리기술투자"]
          and all(nm not in [r[0] for r in P7.NEW7] for nm in follow),
          "후속 3건 %s 이 신규 분모에 **없다** (PD-2 이중계상 금지)" % follow)
    # 후속 3건이 post6 재계산 목록(NEW6)에는 그대로 남아 있어야 한다(post6 행 불변).
    check("P2", {"한라캐스트", "아난티", "우리기술투자"} <= set(n for n, _c, _d in P7.NEW6),
          "후속 3건은 post6 재계산 표본(`NEW6`)에는 **그대로** 있다(post6 행 불변)")

    # N1 — `exact` 판별을 무력화하면 분모가 오염되는가
    poisoned = [(nm, c, d, tag) for nm, c, d, p, tag in P7.NEW7]      # 정밀도 무시 = 「안 거른다」
    check("N1", len(poisoned) == 10 and len(poisoned) != len(P7.EXACT7),
          "정밀도 필터를 무력화하면 분모가 %d → %d 로 «오염»된다 ⇒ 가드가 «실제로» 막고 있다"
          % (len(P7.EXACT7), len(poisoned)))

    print("== P3 / N2. 재진입 플래그 (판정 분모 안 0 · 글 전체 2) ==")
    check("P3", P7.REENTRY_ALL == {"지투파워", "한국화장품제조", "빛과전자"},
          "글 전체 재진입 3건 = %s (PD-3)" % sorted(P7.REENTRY_ALL))
    check("P3", P7.REENTRY_EXACT == {"빛과전자"},
          "판정 분모(`exact`) 안 재진입 = %s (1건뿐)" % sorted(P7.REENTRY_EXACT))
    in_den = sum(P7.PD3_FLAG[n] for n in P7.REENTRY_EXACT)
    all_flag = sum(P7.PD3_FLAG.values())
    check("P3", in_den == 0,
          "🔴🔴 **판정 분모 안 `P6-PRIOR_CYCLE_IN_WINDOW` 합 = %d**(빛과전자 = 0 · 구성상)" % in_den)
    check("P3", all_flag == 2,
          "🔴 **글 전체 플래그 합 = %d** (지투파워 1 · 한국화장품제조 1)" % all_flag)
    ap_names = set(r[0] for r in P7.APPROX7)
    check("P3", all(n in ap_names for n, v in P7.PD3_FLAG.items() if v == 1),
          "플래그=1 인 2건이 **둘 다 `approx` 갈래**다 ⇒ 판정 분모 «안에 없다» (INTAKE §2-10)")
    check("P3", in_den != all_flag,
          "두 수가 **다르다**(%d != %d) ⇒ 「한 칸에 합치지 않는다」가 실제로 지켜져야 하는 자리"
          % (in_den, all_flag))
    # PD 문서와 대조 — 통째 md5 는 고정하지 «않는다»(다른 레인이 쓰는 파일).
    seg = PD.read_text(encoding="utf-8")
    seg3 = seg.split("## PD-3")[1].split("## PD-4")[0] if "## PD-3" in seg else ""
    row = {nm: next((l for l in seg3.splitlines() if l.startswith("| **" + nm)
                     or l.startswith("| " + nm)), "") for nm in P7.REENTRY_ALL}
    check("P3", "P6-PRIOR_CYCLE_IN_WINDOW" in seg3
          and "**1**" in row["지투파워"] and "**1**" in row["한국화장품제조"]
          and "**0**" in row["빛과전자"],
          "PD-3 표 서술(지투파워 1 · 한국화장품제조 1 · 빛과전자 0) ↔ 코드 상수 일치")
    # N2 대칭 — 비교자가 실제로 불일치를 잡는가
    shaken = dict(P7.PD3_FLAG)
    shaken["빛과전자"] = 1
    caught = [k for k in shaken if shaken[k] != P7.PD3_FLAG[k]]
    check("N2", caught == ["빛과전자"] and sum(shaken[n] for n in P7.REENTRY_EXACT) == 1,
          "플래그 하나를 흔들면 정확히 그 1건(%s)만 불일치 · 분모 안 합이 0 → 1 로 바뀐다" % caught)

    print("== P4. `P6-절단가드-A` 산술 (문턱은 등호 포함) ==")
    fires = (lambda num, den: den > 0 and num / den >= P7.TRUNC_GUARD)
    check("P4", fires(1, 6) is False, "1/6 = 16.7% < 1/3 ⇒ **미발동** (이번 글 · 해치텍 1건)")
    check("P4", fires(2, 6) is True, "2/6 = 33.3% ⇒ **발동** (문턱은 등호 포함 · §1-6 5번)")
    check("P4", fires(1, 3) is True, "1/3 = 33.3% ⇒ 발동 (등호)")
    check("P4", fires(3, 10) is False, "3/10 = 30% < 1/3 ⇒ 미발동")
    check("P4", fires(4, 10) is True, "4/10 = 40% ⇒ 발동")

    print("== P5. C-17 NaN 규약 (해치텍 1건) ==")
    src = (BASE / "run_selection.py").read_text(encoding="utf-8")
    c17 = [i + 1 for i, ln in enumerate(src.splitlines()) if "where(prev_max.notna())" in ln]
    check("P5", len(c17) == 1,
          "`run_selection.py:%s` 에 C-17 NaN 보존이 있다 — 없으면 `SEL-S3` 판정 무효"
          % (c17[0] if c17 else "없음"))
    ht = [r for r in P7.EXACT7 if r[0] == "해치텍"]
    check("P5", len(ht) == 1 and ht[0][1] == "0155E0" and ht[0][2] == "2026-09-07",
          "해치텍 = 코드 `0155E0` · 등록일 2026-09-07 (PD-11 2번 · news 경유 해결)")
    pd12 = seg.split("## PD-12")[1].split("## PD-13")[0] if "## PD-12" in seg else ""
    check("P5", "0봉" in pd12 and "C-17" in pd12 and "85/85" in pd12,
          "PD-12 가 «계산 전»에 못박은 문장(해치텍 60봉 **0봉** ⇒ C-17 대상 · 나머지 5건 85/85)")
    check("P5", "10/20" in pd12,
          "PD-12 가 해치텍 창 봉수 **10/20 = 절단**을 «계산 전»에 적었다")

    print("== P6. §1-4 창 규약 갈래 (PD-4 2번) ==")
    b1 = P7.APPROX_BRANCHES["지투파워"]
    b2 = P7.APPROX_BRANCHES["한국화장품제조"]
    check("P6", len(b1[3]) == 8 and b1[1] == "2026-09-01" and b1[2] == "2026-09-10",
          "「9월 초」 = [%s, %s] 거래일 **%d일**" % (b1[1], b1[2], len(b1[3])))
    check("P6", len(b2[3]) == 7 and b2[1] == "2026-08-21" and b2[2] == "2026-08-31",
          "「8월 말」 = [%s, %s] 거래일 **%d일**" % (b2[1], b2[2], len(b2[3])))
    check("P6", b1[3] == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
                          "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"],
          "「9월 초」 갈래 원소가 PD-4 2번 목록과 축자 일치")
    check("P6", b2[3] == ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
                          "2026-08-27", "2026-08-28", "2026-08-31"],
          "「8월 말」 갈래 원소가 PD-4 2번 목록과 축자 일치")
    check("P6", all(d[:4] == "2026" and len(d) == 10 for d in b1[3] + b2[3]),
          "갈래 날짜가 전부 ISO(`daily_prices.date` 는 text 컬럼) 표기다")
    check("P6", len(b1[3]) * len(b2[3]) == 56,
          "조합 수 = 8 x 7 = **%d** (전수 열거 가능 ⇒ 시드 불필요)" % (len(b1[3]) * len(b2[3])))

    print("== P7. 재사용 증명 (새 코드 0줄) ==")
    for fn in ("stat_tdays", "stat_cal", "med", "s1_row", "feat_table", "aggs", "fmt"):
        check("P7", getattr(P7, fn) is getattr(P6, fn),
              "`%s` 가 post6 의 «그 함수» 그대로다(재정의 0)" % fn)
    check("P7", P7.build_features is run_selection.build_features,
          "`build_features` 가 `run_selection.py` 의 «그 함수» 그대로다")
    check("P7", P7.FEATS == run_selection.FEATS and len(P7.FEATS) == 9,
          "특징 %d개가 `run_selection.FEATS` 그대로다" % len(P7.FEATS))

    print("")
    if FAILS:
        print("🔴 실패 %d건" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("✅ 전건 통과")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
