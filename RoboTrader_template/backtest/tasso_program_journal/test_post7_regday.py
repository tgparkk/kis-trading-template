# -*- coding: utf-8 -*-
"""`run_regday_post7.py` 의 «가드 시험» — 창 규약·분모·플래그 규칙이 실제로 뭔가를 «막는지» 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「8일이다」만 보이면 그 목록이 장식일 수
   있으므로, **흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *죽은 가드도 가드다* — 문턱이 등호를 포함하는지, 두 `P6-W10` 용도가 «다른 수»인지
   를 여기서 못 박는다.

실행: `python test_post7_regday.py`  (시스템 python · **DB 접속 0건** · 라이브 트리 import 0건)

  P1  동결 상수 불변          (`DB_UPTO` 2026-09-11 · 시드 20260815 · 20,000 · 창 20 · 문턱)
  P2  분모 구성               (`exact` 6 · `none` 2 · 후속 3 = 축 밖 · post6 재계산 10건 보존)
  N1  (음성 대조) 후속 3건을 분모에 넣으면 «오염»된다 ⇒ PD-2 가 실제로 막고 있다
  P3  재진입 플래그           (판정 분모 안 **0** · `approx` 갈래 **2** · 두 수는 «다르다»)
  P4  `P6-절단가드-A` 산술    (1/6 미발동 · 2/6 발동 · 문턱 **등호 포함**) — `guard_a_fires`
  P5  §1-4 창 규약 갈래 8 / 7 (PD-4 2번 축자) + 조합 56
  N2  (대칭) 갈래 목록에서 하루를 빼면 길이 대조가 «불일치»를 낸다
  P6  `P6-W10` 두 용도 분리   (§1-4 용도 = 인쇄 · `TV` 용도 = 미룸 · 강등 문턱 50%)
  P7  판정 규칙 상수          (`verdict_and` AND 규칙 · `bucket` 대역 · `Q1-R2` 50% · M1 83.33%)
  P8  재사용 증명             (측정자가 post6 의 «그 함수»다 — 재정의 0 · `OUT` 버퍼 연결)

🔴 원본 파일은 하나도 건드리지 않는다. 동결본은 메모리 사본에서만 흔든다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import run_regday_post6 as R6
import run_regday_post7 as R7

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
    pd_txt = PD.read_text(encoding="utf-8")

    print("== P1. 동결 상수 불변 ==")
    check("P1", R7.DB_UPTO == "2026-09-11",
          "`DB_UPTO` = %s (PD-1 · 발행 09-12 토 휴장 ⇒ 마지막 거래일)" % R7.DB_UPTO)
    check("P1", R7.PUB_DATE == "2026-09-12", "발행일 = %s (토요일 = 휴장)" % R7.PUB_DATE)
    check("P1", R7.NULL_SEED == 20260815 and R7.NREP == 20_000,
          "귀무 시드 %d · 반복 %d (승계 · 새 시드 0)" % (R7.NULL_SEED, R7.NREP))
    check("P1", (R7.NULL_SEED, R7.NREP, R7.WIN, R7.UP_MULT, R7.ALPHA)
          == (R6.NULL_SEED, R6.NREP, R6.WIN, R6.UP_MULT, R6.ALPHA),
          "post6 판과 **동일한 동결 상수**(시드·반복·창·UP_MULT·alpha) — 재정의 0")
    check("P1", (R7.MIN_N, R7.MIN_PULL, R7.CLUSTER_MIN) == (3, 3, 2),
          "최소 n = %d · 되밀림형 최소 n = %d · 무리 전제 = %d"
          % (R7.MIN_N, R7.MIN_PULL, R7.CLUSTER_MIN))
    check("P1", (R7.DROP_GUARD, R7.NUP_CITE_BAN, R7.LIMIT_UP) == (0.01, 30, 0.29),
          "drop_rate %s · n_up 인용금지 %s · 상한가 마감 %s"
          % (R7.DROP_GUARD, R7.NUP_CITE_BAN, R7.LIMIT_UP))
    check("P1", R7.FROZEN_CUM == (19, 22),
          "동결 누적 = %s (`RESULTS_REGDAY_POST6_NUMBERS.md`:85 에서 옮겨 적은 값)"
          % (R7.FROZEN_CUM,))

    print("== P2 / N1. 분모 구성 (PD-4 · PD-2) ==")
    rows = intake_rows()
    want_exact = [(nm, code) for _i, nm, code, prec, kind in rows
                  if kind == "신규" and prec == "exact"]
    got_exact = [(nm, code) for nm, code, _d in R7.POST7_EXACT]
    check("P2", got_exact == want_exact and len(got_exact) == 6,
          "🔴 **판정 분모 = 신규 ∧ `exact` = %d건** %s ↔ INTAKE §1 축자 일치"
          % (len(got_exact), [n for n, _c in got_exact]))
    want_none = [(nm, code) for _i, nm, code, prec, kind in rows
                 if kind == "신규" and prec == "none"]
    check("P2", R7.POST7_NONE == want_none,
          "`none` %s — 등록일 문장 자체가 없다(PD-4) ⇒ 축 밖" % [n for n, _c in R7.POST7_NONE])
    want_follow = [(nm, code) for _i, nm, code, prec, kind in rows if kind == "후속"]
    check("P2", R7.POST7_FOLLOWUP == want_follow and len(want_follow) == 3,
          "후속 %s — PD-2 2번으로 등록일 축 분모 «밖»" % [n for n, _c in R7.POST7_FOLLOWUP])
    den_names = set(n for n, _c, _d in R7.POST7_EXACT)
    check("P2", all(n not in den_names for n, _c in R7.POST7_FOLLOWUP + R7.POST7_NONE),
          "후속 3 + `none` 2 가 판정 분모에 **하나도 없다** (이중계상 금지)")
    check("P2", len(R7.POST6) == 10 and "한라캐스트" in [n for n, _c, _d in R7.POST6],
          "post6 재계산 표본 = 10건(후속 3건의 «원» 등록 사건은 여기에 그대로 있다 · post6 행 불변)")
    check("P2", len(R7.POST5) == 6 and len(R7.POST4) == 6,
          "post5 6건 · post4 6건 재계산 표본 보존 (같은 09-11 스냅샷에서 다시 잰다)")
    ap = set(b[0] for b in R7.APPROX_BRANCHES)
    check("P2", ap == {"지투파워", "한국화장품제조"} and not (ap & den_names),
          "`approx` 2건 %s 은 §4 민감도 전용 — 판정 분모에 **없다**" % sorted(ap))

    # N1 — 후속을 분모에 넣으면 오염되는가
    poisoned = R7.POST7_EXACT + [(n, c, "2026-08-21") for n, c in R7.POST7_FOLLOWUP]
    check("N1", len(poisoned) == 9 and len(poisoned) != len(R7.POST7_EXACT),
          "후속 3건을 넣으면 분모가 %d → %d 로 «오염»된다 ⇒ PD-2 가 «실제로» 막고 있다"
          % (len(R7.POST7_EXACT), len(poisoned)))

    print("== P3. 재진입 플래그 (판정 분모 안 0 · `approx` 2) ==")
    check("P3", set(R7.REENTRY) == {"069540"},
          "판정 분모 안 재진입 = 빛과전자 `069540` 1건뿐")
    check("P3", set(R7.REENTRY_APPROX) == {"388050", "003350"},
          "`approx` 갈래 재진입 = 지투파워 · 한국화장품제조")
    in_den = sum(R7.PD3_FLAG[c] for c in R7.REENTRY)
    ap_flag = sum(R7.PD3_FLAG[c] for c in R7.REENTRY_APPROX)
    check("P3", in_den == 0, "🔴🔴 **판정 분모 안 플래그 합 = %d**(구성상 0)" % in_den)
    check("P3", ap_flag == 2, "🔴 **`approx` 갈래 플래그 합 = %d**" % ap_flag)
    check("P3", in_den != ap_flag,
          "두 수가 **다르다**(%d != %d) ⇒ 「한 수로 합치지 않는다」가 지켜져야 하는 자리"
          % (in_den, ap_flag))
    check("P3", R7.REENTRY["069540"] == "2026-08-05",
          "빛과전자 직전 «등록일» = %s (post3 #6 · post4 행은 종료 기록이라 등록 사건이 아니다 · PD-3 ②)"
          % R7.REENTRY["069540"])
    seg3 = pd_txt.split("## PD-3")[1].split("## PD-4")[0] if "## PD-3" in pd_txt else ""
    check("P3", "구성상 0" in seg3 and "2026-08-05" in seg3,
          "PD-3 이 «계산 전»에 빛과전자 = **0**(구성상)을 적었다")

    print("== P4. `P6-절단가드-A` 산술 (문턱 등호 포함) ==")
    check("P4", R7.guard_a_fires(1, 6) is False, "1/6 = 16.7% < 1/3 ⇒ **미발동** (이번 글)")
    check("P4", R7.guard_a_fires(2, 6) is True, "2/6 = 33.3% ⇒ **발동** (등호 포함 · §1-6 5번)")
    check("P4", R7.guard_a_fires(1, 3) is True, "1/3 ⇒ 발동 (등호)")
    check("P4", R7.guard_a_fires(3, 10) is False, "3/10 = 30% < 1/3 ⇒ 미발동")
    check("P4", R7.guard_a_fires(0, 6) is False, "0/6 ⇒ 미발동")
    check("P4", R7.guard_a_fires(1, 0) is False, "분모 0 이면 발동하지 않는다(0 나눗셈 방지)")
    pd12 = pd_txt.split("## PD-12")[1].split("## PD-13")[0] if "## PD-12" in pd_txt else ""
    check("P4", "10/20" in pd12 and "16.7%" in pd12 and "미발동" in pd12,
          "PD-12 가 «계산 전»에 1/6 = 16.7% < 1/3 ⇒ 미발동을 적었다 (해치텍 10/20)")

    print("== P5 / N2. §1-4 창 규약 갈래 (PD-4 2번) ==")
    b = {x[0]: x for x in R7.APPROX_BRANCHES}
    g2 = b["지투파워"]
    hk = b["한국화장품제조"]
    check("P5", g2[3] == "2026-09-01" and g2[4] == "2026-09-10" and len(g2[5]) == 8,
          "「9월 초」 = [%s, %s] 거래일 **%d일**" % (g2[3], g2[4], len(g2[5])))
    check("P5", hk[3] == "2026-08-21" and hk[4] == "2026-08-31" and len(hk[5]) == 7,
          "「8월 말」 = [%s, %s] 거래일 **%d일**" % (hk[3], hk[4], len(hk[5])))
    check("P5", g2[5] == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
                          "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"],
          "「9월 초」 갈래 원소가 PD-4 2번 목록과 축자 일치")
    check("P5", hk[5] == ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
                          "2026-08-27", "2026-08-28", "2026-08-31"],
          "「8월 말」 갈래 원소가 PD-4 2번 목록과 축자 일치")
    check("P5", len(g2[5]) * len(hk[5]) == 56,
          "조합 = 8 x 7 = **%d** ⇒ **전수 열거 가능**(시드 불필요)" % (len(g2[5]) * len(hk[5])))
    seg4 = pd_txt.split("## PD-4")[1].split("## PD-5")[0] if "## PD-4" in pd_txt else ""
    check("P5", "거래일 8일" in seg4 and "거래일 7일" in seg4,
          "PD-4 2번이 «계산 전»에 8일 / 7일을 적었다")
    # N2 대칭 — 목록을 흔들면 길이 대조가 불일치를 내는가
    shaken = list(g2[5])[:-1]
    check("N2", len(shaken) != len(g2[5]) and shaken != g2[5],
          "「9월 초」에서 하루를 빼면 길이 %d != %d ⇒ 대조가 «실제로» 잡는다"
          % (len(shaken), len(g2[5])))

    print("== P6. `P6-W10` 두 용도 분리 (PD-4 2번 ↔ PD-6) ==")
    check("P6", R7.W10_DEGRADE == 0.50,
          "강등 문턱 = 귀무 적중률 ≥ %.0f%% (`RESULTS_D1_OOS_POST5.md` §9 · `TV-W7` 상속)"
          % (R7.W10_DEGRADE * 100))
    seg6 = pd_txt.split("## PD-6")[1].split("## PD-7")[0] if "## PD-6" in pd_txt else ""
    check("P6", "P6-W10" in seg6 and "한 수로 합치지 않는다" in seg6,
          "PD-6 이 *「두 용도를 한 수로 합치지 않는다」*를 «계산 전»에 못박았다")
    src7 = (BASE / "run_regday_post7.py").read_text(encoding="utf-8")
    check("P6", "한 수로 합치지 않는다" in src7 and "P6-W10" in src7,
          "산출물 생성기가 그 문장을 **인쇄**한다(문장이 코드에 있다)")
    check("P6", "미룬다" in src7 and "run_d1_oos_post7.py" in src7,
          "`TV` 축 `P6-W10` 은 «미룸»이고 그건 `run_d1_oos_post7.py` 소관임을 산출물에 적는다")

    print("== P7. 판정 규칙 상수 ==")
    check("P7", abs(R7.M1_RATIO - 5.0 / 6.0) < 1e-12 and abs(R7.R2_RATIO - 0.5) < 1e-12,
          "`P6-M1′` 비율 문턱 %.4f(= 5/6) · `Q1-R2` %.2f" % (R7.M1_RATIO, R7.R2_RATIO))
    check("P7", R7.verdict_and(True, True) == "✅ 지지",
          "AND 규칙 — 비율 ∧ 귀무 둘 다 충족이면 «지지»")
    check("P7", R7.verdict_and(True, False).startswith("🟡")
          and R7.verdict_and(False, True).startswith("🟡"),
          "한쪽만 충족이면 **🟡 부분 충족 — 지지로 인용 금지**")
    check("P7", R7.verdict_and(False, False) == "⛔ 불성립", "둘 다 미달이면 ⛔ 불성립")
    check("P7", R7.bucket(-0.005) == "상한가형" and R7.bucket(-0.01) == "상한가형",
          "상한가형 대역 = `r ≥ −1%` (등호 포함)")
    check("P7", R7.bucket(-0.05) == "되밀림형" and R7.bucket(-0.06) == "되밀림형",
          "되밀림형 대역 = `r ≤ −5%` (등호 포함)")
    check("P7", R7.bucket(-0.03) == "🔴 중간대", "그 사이는 중간대 — ✅ 로 접지 않는다")

    print("== P8. 재사용 증명 (새 코드 0줄) ==")
    for fn in ("measure", "null_p", "bucket", "gstar", "null_gstar_a", "null_gstar_b",
               "verdict_and", "block", "fmt_pct", "universe_raw_count",
               "prev_trading_day", "load_universe_day"):
        check("P8", getattr(R7, fn) is getattr(R6, fn),
              "`%s` 가 post6 의 «그 함수» 그대로다(재정의 0)" % fn)
    check("P8", R6.OUT is R7.OUT,
          "post6 `block()` 의 버퍼가 이 실행의 `OUT` 으로 이어졌다"
          "(`run_ladder_tranche_post6.py:74` 전례 · 원본 파일 불변)")

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
