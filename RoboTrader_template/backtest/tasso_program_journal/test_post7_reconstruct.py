# -*- coding: utf-8 -*-
"""`run_reconstruct_post7.py` 의 «가드 시험» — 계기가 규약대로 돌았는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「일치한다」만 보이면 비교자가
   항상 통과하는 장식일 수 있으므로 **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *가드가 고장난 게 아니라 너무 늦게 설치된 것* — 상수·분모는 import 시점에 굳는다.

실행: `python test_post7_reconstruct.py`  (시스템 python · 라이브 트리 import 0건 · **DB 접속 0건**)

  P1 동결 상수 불변 (창 종료 2026-09-11 · 발행 2026-09-12 · `REC-Z5` 0.022/0.020 · 시드 20260815)
  P2 `TARGETS` 구성 — 신규 **10건**이 `INTAKE_2026-09-15_post7.md` §1 과 일치하고
     **후속 3건(한라캐스트 125490 · 아난티 025980 · 우리기술투자 041190)이 «없다»**(PD-2 4번)
  P3 🔴 **PD-4 분모** — `exact` 6 / `approx` 2 / `none` 2 · `first_only` `exact` 5
  P4 🔴 **`REC-Y1` 최소 n 미달** — `exact` 레그>=4 가 **2 < 3** ⇒ ⛔ ·
     `approx` 포함 갈래 3 은 «민감도 문자열»로만 등장하고 판정 문구가 없다
  N1 대칭 — `approx` 를 분모에 넣은 «사본»에서는 최소 n 이 실제로 충족된다(가드가 살아 있다)
  P5 🔒 **`REC-Z4` 는 판정하지 않는다** — 조건 충족 3건만 관측 인쇄 ·
     소스에 「즉시 L 판정」류 귀결 문구가 **없다** · 결정 ④ 종결 목록 11개
  P6 `ANANTI`(post6 보존값)가 `RESULTS_RECONSTRUCT_POST6_NUMBERS.md` 에서 **실제로 읽힌다**
     — 「재계산하지 않았다」(PD-12 (가) 문형)의 기계적 증거 · N2 흔든 사본에서 불일치
  P7 `approx` 창 규약 갈래 — 「9월 초」 8거래일 · 「8월 말」 7거래일 (PD-4 2번 실측값)
  P8 소스 필수 문구 · 라이브 트리 import 0건 · SQL 은 SELECT 뿐 · 파일 쓰기 1곳

🔴 어떤 원본 파일도 고치지 않는다. 보존값은 **메모리 사본**에서만 흔든다.
🔴 **`run_reconstruct_post7.py` 를 실행하지 않는다**(DB 가 필요하고, 판정은 관리자 지시로 돈다).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import run_reconstruct_post5 as P5M  # noqa: E402
import run_reconstruct_post6 as P6M  # noqa: E402
import run_reconstruct_post7 as P7  # noqa: E402

BASE = Path(__file__).resolve().parent
FAIL: list = []


def check(name, cond, detail=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


NM, CODE, D0, PREC, LEGS, TR, PRESET, LABEL, FO, REENT = range(10)

# ── P1. 동결 상수 ────────────────────────────────────────────────────────
print("\nP1 동결 상수 (계산 «전» 고정 — A-1 · REC-Z5 · 시드)")
check("창 종료 END = 2026-09-11 (PD-1 · B-1 · 발행일 휴장)", P7.END == "2026-09-11", P7.END)
check("발행일 PUB_DATE = 2026-09-12(토)", P7.PUB_DATE == "2026-09-12", P7.PUB_DATE)
check("REC-Z5 판정 문턱 0.022", P7.THR_MAIN == 0.022, str(P7.THR_MAIN))
check("REC-Z5 민감도 문턱 0.020", P7.THR_SENS == 0.020, str(P7.THR_SENS))
check("계열 고정 시드 20260815 (값을 지우지 않았다)", P7.SEED == 20260815, str(P7.SEED))
check("NREP 20,000 (값을 지우지 않았다)", P7.NREP == 20000, str(P7.NREP))
check("post6 과 «같은 시드»다(새 시드를 만들지 않았다)", P7.SEED == P6M.SEED)
check("🔴 창 종료가 post6 에서 «전진»했다(09-04 → 09-11)", P7.END != P6M.END,
      f"{P6M.END} → {P7.END}")

# ── P2. TARGETS 구성 ─────────────────────────────────────────────────────
print("\nP2 TARGETS — INTAKE §1 신규 10건과 일치 · 후속 3건 «없음»(PD-2 4번)")
INTAKE = {  # (코드, 등록일, 정밀도, 레그, 차수, 프리셋, 라벨, first_only, 재진입)
    "한전기술": ("052690", None, "none",
                 [13.61, 10.80, 7.37, 4.91, 3.34, -1.70], 4, "HDR60", "SL", False, False),
    "한전산업": ("130660", None, "none",
                 [15.55, 14.88, 12.70, 8.97, 5.78, -1.32], 5, "HDR60", "SL", False, False),
    "지투파워": ("388050", None, "approx",
                 [20.11, 18.58, 17.50, 15.08, 12.72], 3, "HDR60", "TP", False, True),
    "서산": ("079650", "2026-09-03", "exact",
             [22.16, 16.09, 10.02], 1, "Q2~MAX", "TP", True, False),
    "강동씨엔앨": ("198440", "2026-09-03", "exact",
                   [24.28, 18.33, 18.31, 12.61], 1, "HDR60", "TP", True, False),
    "로보티즈": ("108490", "2026-09-04", "exact", [9.13], 1, "HDR60", "TP", True, False),
    "해치텍": ("0155E0", "2026-09-07", "exact", [4.06, 0.46], 4, "HDR60", "TP", False, False),
    "빛과전자": ("069540", "2026-09-08", "exact", [12.17], 1, "HDR60", "TP", True, True),
    "한국화장품제조": ("003350", None, "approx",
                       [22.70, 16.81, 10.85], 1, "HDR60", "unknown", True, True),
    "범한퓨얼셀": ("382900", "2026-09-09", "exact",
                   [18.89, 16.69, 14.55, 12.22, 10.8, 7.94], 1, "HDR60", "TP", True, False),
}
got = {t[NM]: tuple(t[1:]) for t in P7.TARGETS}
check("신규 건수 10", len(P7.TARGETS) == 10, str(len(P7.TARGETS)))
check("종목 집합 일치", set(got) == set(INTAKE), "차분 " + str(set(got) ^ set(INTAKE)))
for nm, exp in INTAKE.items():
    check(f"{nm} 코드·등록일·정밀도·레그·차수·프리셋·라벨·fo·재진입",
          got.get(nm) == exp, str(got.get(nm)))
for nm, code in (("한라캐스트", "125490"), ("아난티", "025980"), ("우리기술투자", "041190")):
    check(f"후속 {nm}({code}) 없음 — PD-2 4번",
          all(t[CODE] != code for t in P7.TARGETS))
check("레그 합 37 (INTAKE §1 신규 10건)",
      sum(len(t[LEGS]) for t in P7.TARGETS) == 37,
      str(sum(len(t[LEGS]) for t in P7.TARGETS)))
check("🔴 해치텍 코드가 `0155E0` 다 (PD-11 2번 자기정정)",
      got["해치텍"][0] == "0155E0", got["해치텍"][0])
check("🔴 서산 프리셋이 `Q2~MAX` 다 (HDR60 아님 · A-4 분모 밖)",
      got["서산"][5] == "Q2~MAX", got["서산"][5])
check("프리셋 HDR60 은 9건 (서산만 다르다 · PD-9)",
      sum(1 for t in P7.TARGETS if t[PRESET] == "HDR60") == 9)

# ── P3. PD-4 분모 ────────────────────────────────────────────────────────
print("\nP3 PD-4 분모 — `exact` 6 / `approx` 2 / `none` 2 (이 계열에서 «처음» 갈린다)")
ex = [t for t in P7.TARGETS if t[PREC] == "exact"]
ap = [t for t in P7.TARGETS if t[PREC] == "approx"]
nn = [t for t in P7.TARGETS if t[PREC] == "none"]
check("`exact` 6건", len(ex) == 6, str([t[NM] for t in ex]))
check("`approx` 2건 = 지투파워·한국화장품제조",
      sorted(t[NM] for t in ap) == ["지투파워", "한국화장품제조"], str([t[NM] for t in ap]))
check("`none` 2건 = 한전기술·한전산업",
      sorted(t[NM] for t in nn) == ["한전기술", "한전산업"], str([t[NM] for t in nn]))
check("신규 10 ≠ `exact` 6 — 이번 글에서 처음 갈린다(PD-4 1번 충돌 신고)",
      len(P7.TARGETS) != len(ex))
check("`first_only` ∧ `exact` = 5건",
      sum(1 for t in ex if t[FO]) == 5, str([t[NM] for t in ex if t[FO]]))
check("재진입 ∧ `exact` = 빛과전자 1건 (판정 분모 안 플래그 0 · INTAKE §2-10)",
      [t[NM] for t in ex if t[REENT]] == ["빛과전자"], str([t[NM] for t in ex if t[REENT]]))
check("재진입 3건 중 2건이 `approx` (민감도가 겹친다 · PD-3 마지막 줄)",
      sum(1 for t in ap if t[REENT]) == 2)

# ── P4 / N1. REC-Y1 최소 n ───────────────────────────────────────────────
print("\nP4 `REC-Y1` — `exact` 레그>=4 가 2 < 3 ⇒ ⛔ 최소 n 미달 (§4 #38)")
y1_exact = [t[NM] for t in ex if len(t[LEGS]) >= 4]
y1_approx = [t[NM] for t in ap if len(t[LEGS]) >= 4]
check("`exact` 레그>=4 = 강동씨엔앨·범한퓨얼셀 2건",
      sorted(y1_exact) == ["강동씨엔앨", "범한퓨얼셀"], str(y1_exact))
check("2 < 3 ⇒ 최소 n 미달", len(y1_exact) < 3)
check("`approx` 레그>=4 = 지투파워 1건", y1_approx == ["지투파워"], str(y1_approx))

print("\nN1 대칭 — `approx` 를 분모에 넣은 «사본»에서는 최소 n 이 실제로 충족된다")
check("`approx` 포함 갈래는 3 ⇒ 최소 n 충족(가드가 장식이 아니다)",
      len(y1_exact) + len(y1_approx) == 3)
check("원본 분모는 그대로 `exact` 다(사본만 흔들었다)",
      len([t for t in P7.TARGETS if t[PREC] == "exact" and len(t[LEGS]) >= 4]) == 2)

# ── P5. REC-Z4 는 판정하지 않는다 (결정 ④) ───────────────────────────────
print("\nP5 🔒 `REC-Z4` — 조건 충족 건수만 관측 인쇄 · 판정 없음 (결정 ④ · `342f6f0`)")
z4 = [t[NM] for t in ex if t[FO] and len(set(t[LEGS])) >= 3]
check("`REC-Z4` 조건 충족 `exact` 3건 = 서산·강동씨엔앨·범한퓨얼셀",
      sorted(z4) == ["강동씨엔앨", "범한퓨얼셀", "서산"], str(z4))
check("로보티즈·빛과전자는 서로 다른 값 레그 1 ⇒ 조건 미충족",
      all(len(set(dict((t[NM], t[LEGS]) for t in ex)[n])) == 1
          for n in ("로보티즈", "빛과전자")))
SRC = (BASE / "run_reconstruct_post7.py").read_text(encoding="utf-8")
check("🔴 소스에 「즉시 L 판정」 귀결 문구가 «없다»", "즉시 L 판정" not in SRC)
check("🔴 소스에 「즉시 판정한다」 문구가 «없다»", "즉시 판정한다" not in SRC)
check("「관측 인쇄만」 문구가 있다", "관측 인쇄만" in SRC)
check("결정 ④ 종결 목록이 11개다(`P6-L1'`~`BUY-L5`)",
      len(P7.CLOSED_BY_DECISION4) == 11, str(len(P7.CLOSED_BY_DECISION4)))
for lab in ("`P6-L1'`", "`P6-L2'`", "`P6-L3'`", "`P6-L-누적`", "`P6-L-대칭`", "`BUY-L5`"):
    check(f"{lab} 이 종결 목록에 있다", lab in P7.CLOSED_BY_DECISION4)
check("종결된 축의 귀무를 «돌리지 않는다»(random 미import)", "import random" not in SRC)
check("대칭 — post6 은 그 귀무를 실제로 돌렸다(장식 비교가 아니다)",
      "import random" in (BASE / "run_reconstruct_post6.py").read_text(encoding="utf-8"))

# ── P6 / N2. 보존값이 «읽힌» 값인가 (재계산 아님) ────────────────────────
print("\nP6 ANANTI — post6 보존값을 RESULTS_RECONSTRUCT_POST6_NUMBERS.md 에서 실제로 읽는다")
P6NUM = (BASE / "RESULTS_RECONSTRUCT_POST6_NUMBERS.md").read_text(encoding="utf-8")


def row_of(text, head):
    for line in text.splitlines():
        if line.startswith(head):
            return [c.strip() for c in line.strip("|").split("|")]
    return None


def nums(s):
    return [float(x.replace(",", "")) for x in re.findall(r"-?[\d,]+\.\d+|-?\d[\d,]*", s)]


row = row_of(P6NUM, "| 아난티 | 1차 | TP | 2026-08-19 |")
check("post6 §1 아난티 행을 찾았다", row is not None)
if row:
    check("구간 개수 156", nums(row[7])[0] == P7.ANANTI["n_iv"], row[7])
    pr = nums(row[8])
    check("P 범위 4,311.71~5,492.26",
          (pr[0], pr[1]) == (P7.ANANTI["pmin"], P7.ANANTI["pmax"]), row[8])
    check("총 측도 68.34", nums(row[9])[0] == P7.ANANTI["measure"], row[9])
    b1 = nums(row[10])
    check("b1 범위 +4.32%~+24.88%",
          (b1[0], b1[1]) == (P7.ANANTI["b1_lo"], P7.ANANTI["b1_hi"]), row[10])
    check("폭 20.57%p", nums(row[11])[0] == P7.ANANTI["w"], row[11])
    bar = nums(row[5])
    check("등록일 봉 [4,750, 4,880, 5,740, 5,350]",
          bar[:4] == [P7.ANANTI["bar_low"], P7.ANANTI["bar_open"],
                      P7.ANANTI["bar_high"], P7.ANANTI["bar_close"]], row[5])
check("frac_in 0.5582 가 post6 §10 표에 있다", "**0.5582**" in P6NUM)
check("DD 17.25% 가 post6 §15 표에 있다", "| 17.25% | 17.25% | 17.25% |" in P6NUM)
check("보존값의 창 종료가 post6 의 것(2026-09-04)이라고 적혀 있다",
      P7.ANANTI["end"] == "2026-09-04", P7.ANANTI["end"])

print("\nN2 대칭 — 보존값을 흔든 «사본»에서는 위 비교가 불일치를 낸다")
shaken = P6NUM.replace("4,311.71~5,492.26", "4,311.71~5,492.99")
row2 = row_of(shaken, "| 아난티 | 1차 | TP | 2026-08-19 |")
check("흔든 사본에서 P 범위 비교가 실패한다",
      row2 is not None and nums(row2[8])[1] != P7.ANANTI["pmax"],
      "" if row2 is None else row2[8])
check("원본 문자열은 그대로다(사본만 흔들었다)",
      "4,311.71~5,492.26" in P6NUM and "5,492.99" not in P6NUM)

# ── P7. approx 창 규약 갈래 ──────────────────────────────────────────────
print("\nP7 `approx` 창 규약 갈래 — PD-4 2번 달력 실측값")
check("「9월 초」 = 8 거래일", len(P7.APPROX_BRANCHES["지투파워"]) == 8,
      str(len(P7.APPROX_BRANCHES["지투파워"])))
check("「8월 말」 = 7 거래일", len(P7.APPROX_BRANCHES["한국화장품제조"]) == 7,
      str(len(P7.APPROX_BRANCHES["한국화장품제조"])))
check("「9월 초」 범위가 09-01~09-10 이다",
      P7.APPROX_BRANCHES["지투파워"][0] == "2026-09-01"
      and P7.APPROX_BRANCHES["지투파워"][-1] == "2026-09-10")
check("「8월 말」 범위가 08-21~08-31 이다",
      P7.APPROX_BRANCHES["한국화장품제조"][0] == "2026-08-21"
      and P7.APPROX_BRANCHES["한국화장품제조"][-1] == "2026-08-31")
check("주말(토·일)이 갈래에 없다 — 거래일만",
      all(d not in ("2026-09-05", "2026-09-06", "2026-08-22", "2026-08-23",
                    "2026-08-29", "2026-08-30")
          for v in P7.APPROX_BRANCHES.values() for d in v))
check("창5 절단 2건 = 빛과전자 4봉 · 범한퓨얼셀 3봉 (PD-12)",
      P7.WIN5_TRUNC == {"빛과전자": 4, "범한퓨얼셀": 3}, str(P7.WIN5_TRUNC))
check("소수 1자리 한계 대상 = 범한퓨얼셀 10.8 (PD-10 3번)",
      P7.DECIMAL_LIMIT == {"범한퓨얼셀": 10.8}, str(P7.DECIMAL_LIMIT))

# ── P8. 소스 필수 문구 · 라이브 트리 격리 ────────────────────────────────
print("\nP8 소스 필수 문구 · import 0건 · SELECT 뿐 · 파일 쓰기 1곳")
for phrase in (
    "# RESULTS_RECONSTRUCT_POST7_NUMBERS — 기계 생성 (수정 금지)",
    "휴장 ⇒ 마지막 거래일 · B-1",
    "실행 시 `max(date)`",
    "그 날짜 행수",
    "라이브 채택 대상이 아니다",
    "새 예측을 만들지 않았다",
    "A-1 ~ A-11 전부 승계",
    "재계산하지 않았다",
    "기록 보존",
    "결정 ④",
    "%p 단일",
    "구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)",
    "모호 지점",
    "방향 자기신고",
    "최소 n 미달",
    "등록일 축 «밖»",
):
    check(f"필수 문구 「{phrase}」", phrase in SRC)
imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", SRC, re.M)
allow = {"__future__", "sys", "pathlib", "psycopg2",
         "reconstruct_prices", "run_reconstruct_post5", "run_reconstruct_post6", "run_tests"}
bad = [m for m in imports if m.split(".")[0] not in allow]
check("허용 목록 밖 import 0건", not bad, str(bad))
check("adj_factor 산술 0건", "adj_factor" not in SRC.replace("`adj_factor` 산술 0건", ""))
sqls = re.findall(r'"\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)', SRC, re.I)
check("SQL 은 SELECT 뿐", all(s.upper() == "SELECT" for s in sqls), str(set(sqls)))
check("파일 쓰기는 산출물 하나뿐", SRC.count("write_text") == 1, str(SRC.count("write_text")))
check("산출물 이름이 RESULTS_RECONSTRUCT_POST7_NUMBERS.md 다",
      'RESULTS_RECONSTRUCT_POST7_NUMBERS.md"' in SRC)
# 🔑 새 코드 0줄 원칙의 «기계적» 증거 — 통계 핵이 post5·post6 의 «같은 객체»여야 한다.
for fn in ("bars", "feasible_exact", "feasible_pointwise", "iv_max", "iv_measure",
           "iv_min", "min_residual", "sigma20"):
    check(f"`{fn}` 이 post5 의 «같은 객체»다(재정의 0)",
          getattr(P7, fn) is getattr(P5M, fn))
for fn in ("dd_h", "fmt_pct", "med", "win_bars"):
    check(f"`{fn}` 이 post6 의 «같은 객체»다(재정의 0)",
          getattr(P7, fn) is getattr(P6M, fn))
check("post6 의 산출물 이름이 그대로다(그 파일을 건드리지 않았다는 방증)",
      'RESULTS_RECONSTRUCT_POST6_NUMBERS.md"' in
      (BASE / "run_reconstruct_post6.py").read_text(encoding="utf-8"))

print("\n" + ("=" * 60))
if FAIL:
    print(f"FAILED {len(FAIL)}건: " + " · ".join(FAIL))
    sys.exit(1)
print("ALL PASS")
sys.exit(0)
