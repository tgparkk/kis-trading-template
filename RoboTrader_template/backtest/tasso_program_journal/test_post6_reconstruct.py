# -*- coding: utf-8 -*-
"""`run_reconstruct_post6.py` 의 «가드 시험» — 계기가 규약대로 돌았는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「일치한다」만 보이면 비교자가
   항상 통과하는 장식일 수 있으므로 **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *가드가 고장난 게 아니라 너무 늦게 설치된 것* — 상수는 import 시점에 굳는다.

실행: `python test_post6_reconstruct.py`  (시스템 python · 라이브 트리 import 0건 · **DB 접속 0건**)

  P1 동결 상수 불변 (창 종료 2026-09-04 · `REC-Z5` 0.022/0.020 · 시드 20260815 · 20,000회)
  P2 `TARGETS` 구성 — 신규 **10건**이 `INTAKE_2026-09-04_post6.md` §1 과 일치하고
     **후속 2건(광전자 017900 · 삼양 0120G0)이 «없다»**(PD-2 4번) · `first_only` 3건
  P3 `SAM`(post5 보존값)이 `RESULTS_RECONSTRUCT_POST5_NUMBERS.md` 에서 **실제로 읽힌다**
     — 「재계산하지 않았다」(PD-12 (가))의 기계적 증거
  N1 대칭 — 보존값을 하나 흔든 사본에서는 P3 의 비교가 **불일치를 낸다**
  P4 측도 산술 — `iv_clip_measure` · `iv_weighted_median`(측도 절반 지점)
  P5 중앙값 관용구 — 짝수 `n` 에서 **두 가운데 값의 평균**(C-20 · `PREREG_POST6.md` §5-4)
  P6 `P6-L1'-N` 결정성 — 같은 시드로 두 번 뽑으면 같은 표본(두 번 실행 byte 동일의 핵)
  P7 산출물 필수 문구 — 라이브 채택 금지 · 창 종료 규약 · DB 최신 봉 · 시드/반복수 · C-22 확인
  P8 라이브 트리 import 0건 · `adj_factor` 산술 0건 (소스 문자열 검사)

🔴 어떤 원본 파일도 고치지 않는다. 보존값은 **메모리 사본**에서만 흔든다.
"""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import run_reconstruct_post6 as P6  # noqa: E402

BASE = Path(__file__).resolve().parent
FAIL: list[str] = []


def check(name, cond, detail=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


# ── P1. 동결 상수 ────────────────────────────────────────────────────────
print("\nP1 동결 상수 (계산 «전» 고정 — A-1 · REC-Z5 · P6-L1'-N)")
check("창 종료 END = 2026-09-04 (PD-1 · 발행 당일 봉 포함)", P6.END == "2026-09-04", P6.END)
check("REC-Z5 판정 문턱 0.022", P6.THR_MAIN == 0.022, str(P6.THR_MAIN))
check("REC-Z5 민감도 문턱 0.020", P6.THR_SENS == 0.020, str(P6.THR_SENS))
check("P6-L1'-N 시드 20260815", P6.SEED == 20260815, str(P6.SEED))
check("P6-L1'-N 반복 20,000", P6.NREP == 20000, str(P6.NREP))

# ── P2. TARGETS 구성 ─────────────────────────────────────────────────────
print("\nP2 TARGETS — INTAKE §1 신규 10건과 일치 · 후속 2건 «없음»(PD-2 4번)")
INTAKE = {  # INTAKE_2026-09-04_post6.md §1 신규 10건 (코드, 등록일, 레그, 차수, first_only)
    "한라캐스트": ("125490", "2026-08-21", [5.82, 5.72, -2.87, -2.89], 5, False),
    "헥토파이낸셜": ("234340", "2026-08-28", [22.24, 15.33, 8.27], 1, True),
    "아난티": ("025980", "2026-08-19", [10.16], 1, True),
    "아이티센글로벌": ("124500", "2026-08-20", [5.72, 0.50], 3, False),
    "현대약품": ("004310", "2026-09-01", [12.32, 2.97], 2, False),
    "원익": ("032940", "2026-08-31",
             [18.44, 16.18, 14.05, 13.09, 13.06, 9.48, 4.27], 3, False),
    "쿠콘": ("294570", "2026-08-28", [14.31, 10.74], 1, True),
    "지투파워": ("388050", "2026-08-26", [10.14, 7.36, 7.25, 5.19], 3, False),
    "우리기술투자": ("041190", "2026-08-25", [16.48, 13.80, 13.63, 10.19, 6.50], 4, False),
    "비에이치": ("090460", "2026-09-01",
                 [11.91, 10.65, 9.63, 8.36, 7.09, 6.08, 3.70], 4, False),
}
got = {t[0]: (t[1], t[2], t[3], t[4], t[7]) for t in P6.TARGETS}
check("신규 건수 10", len(P6.TARGETS) == 10, str(len(P6.TARGETS)))
check("종목 집합 일치", set(got) == set(INTAKE),
      "차분 " + str(set(got) ^ set(INTAKE)))
for nm, exp in INTAKE.items():
    check(f"{nm} 코드·등록일·레그·차수·first_only", got.get(nm) == exp, str(got.get(nm)))
check("후속 광전자(017900) 없음 — PD-2 4번",
      all(t[1] != "017900" for t in P6.TARGETS))
check("후속 삼양바이오팜(0120G0) 없음 — PD-2 4번",
      all(t[1] != "0120G0" for t in P6.TARGETS))
check("first_only 3건", sum(1 for t in P6.TARGETS if t[7]) == 3)
check("레그 합 37 (INTAKE §1 신규 10건)",
      sum(len(t[3]) for t in P6.TARGETS) == 37,
      str(sum(len(t[3]) for t in P6.TARGETS)))
check("레그>=4 건 5건 (INTAKE §2-3)",
      sum(1 for t in P6.TARGETS if len(t[3]) >= 4) == 5)
check("프리셋 전건 HDR60 (PD-8 · 변량 0)",
      all(t[5] == "HDR60" for t in P6.TARGETS))
check("라벨 = TP 9 · SL 1 (LABELS 신규 10건)",
      sorted(t[6] for t in P6.TARGETS) == ["SL"] + ["TP"] * 9)
check("재진입 2건 = 현대약품·지투파워 (PD-3)",
      sorted(t[0] for t in P6.TARGETS if t[8]) == ["지투파워", "현대약품"])

# ── P3 / N1. 보존값이 «읽힌» 값인가 (재계산 아님) ─────────────────────────
print("\nP3 SAM — post5 보존값을 RESULTS_RECONSTRUCT_POST5_NUMBERS.md 에서 실제로 읽는다")
P5NUM = (BASE / "RESULTS_RECONSTRUCT_POST5_NUMBERS.md").read_text(encoding="utf-8")


def sam_row(text):
    for line in text.splitlines():
        if line.startswith("| 삼양바이오팜 |") and "1차" in line and "HDR60" in line:
            return [c.strip() for c in line.strip("|").split("|")]
    return None


def nums(s):
    return [float(x.replace(",", "")) for x in re.findall(r"-?[\d,]+\.\d+|-?\d[\d,]*", s)]


row = sam_row(P5NUM)
check("post5 §1 삼양 행을 찾았다", row is not None)
if row:
    check("구간 개수 145", nums(row[8])[0] == P6.SAM["n_iv"], row[8])
    pr = nums(row[9])
    check("P 범위 46,903.73~59,823.31",
          (pr[0], pr[1]) == (P6.SAM["pmin"], P6.SAM["pmax"]), row[9])
    b1 = nums(row[10])
    check("b1 범위 +10.31%~+29.68%",
          (b1[0], b1[1]) == (P6.SAM["b1_lo"], P6.SAM["b1_hi"]), row[10])
    check("폭 19.37%p", nums(row[11])[0] == P6.SAM["w"], row[11])
    bar = nums(row[6])
    check("등록일 봉 [57,700, 63,500, 66,700, 58,800]",
          bar[:4] == [P6.SAM["bar_low"], P6.SAM["bar_open"],
                      P6.SAM["bar_high"], P6.SAM["bar_close"]], row[6])
check("총 측도 693.96원이 post5 §1 본문에 있다", "삼양바이오팜 693.96원" in P5NUM)
check("DD 21.59%가 post5 §7 표에 있다", "| 21.59% | 21.59% | 21.59% |" in P5NUM)
check("범위중점 b1 = 19.99% 가 §1-2 동결 문언과 같다",
      abs(P6.SAM["mid"] - 100 * (1 - (P6.SAM["pmin"] + P6.SAM["pmax"]) / 2
                                 / P6.SAM["bar_high"])) < 0.005,
      f"{P6.SAM['mid']} vs "
      f"{100*(1-(P6.SAM['pmin']+P6.SAM['pmax'])/2/P6.SAM['bar_high']):.4f}")

print("\nN1 대칭 — 보존값을 흔든 «사본»에서는 위 비교가 불일치를 낸다")
shaken = P5NUM.replace("46,903.73~59,823.31", "46,903.73~59,823.99")
row2 = sam_row(shaken)
check("흔든 사본에서 P 범위 비교가 실패한다",
      row2 is not None and nums(row2[9])[1] != P6.SAM["pmax"],
      "" if row2 is None else row2[9])
check("원본 문자열은 그대로다(사본만 흔들었다)",
      "46,903.73~59,823.31" in P5NUM and "59,823.99" not in P5NUM)

# ── P4. 측도 산술 ────────────────────────────────────────────────────────
print("\nP4 측도 산술 — iv_clip_measure · iv_weighted_median")
iv = [(0.0, 10.0), (20.0, 30.0)]
check("총 측도 20", P6.iv_measure(iv) == 20.0, str(P6.iv_measure(iv)))
check("[0,10] 과의 교집합 측도 10", P6.iv_clip_measure(iv, 0.0, 10.0) == 10.0)
check("[5,25] 과의 교집합 측도 10", P6.iv_clip_measure(iv, 5.0, 25.0) == 10.0)
check("[100,200] 과의 교집합 측도 0", P6.iv_clip_measure(iv, 100.0, 200.0) == 0.0)
check("frac_in 이 [0,1] 밖으로 안 나간다",
      0.0 <= P6.iv_clip_measure(iv, 5.0, 25.0) / P6.iv_measure(iv) <= 1.0)
check("측도가중 중앙 = 10.0 (첫 구간 끝 = 측도 절반)",
      P6.iv_weighted_median(iv) == 10.0, str(P6.iv_weighted_median(iv)))
check("측도가중 중앙 ≠ 범위중점 (15.0) — 성긴 집합에서 갈린다",
      P6.iv_weighted_median(iv) != (P6.iv_min(iv) + P6.iv_max(iv)) / 2)
check("빈 집합이면 None", P6.iv_weighted_median([]) is None)
check("단일 구간 [0,10] 의 측도가중 중앙 = 5.0",
      P6.iv_weighted_median([(0.0, 10.0)]) == 5.0)

# ── P5. 중앙값 관용구 (C-20) ─────────────────────────────────────────────
print("\nP5 중앙값 관용구 — 짝수 n 에서 두 가운데 값의 «평균» (C-20 · §5-4)")
check("med([1,2,3,4]) == 2.5", P6.med([1, 2, 3, 4]) == 2.5, str(P6.med([1, 2, 3, 4])))
check("med([1,2,3]) == 2", P6.med([1, 2, 3]) == 2)
check("상위 중앙값 관용구(sorted[len//2]=3)와 «다르다»",
      P6.med([1, 2, 3, 4]) != sorted([1, 2, 3, 4])[4 // 2])

# ── P6. 결정성 ───────────────────────────────────────────────────────────
print("\nP6 결정성 — 같은 시드로 두 번 뽑으면 같은 표본(두 번 실행 byte 동일의 핵)")
rng1, rng2 = random.Random(P6.SEED), random.Random(P6.SEED)
s1 = [rng1.randrange(24) for _ in range(P6.NREP)]
s2 = [rng2.randrange(24) for _ in range(P6.NREP)]
check("같은 시드 → 같은 20,000 표본", s1 == s2)
check("다른 시드 → 다른 표본(대칭 단언)",
      s1 != [random.Random(P6.SEED + 1).randrange(24) for _ in range(P6.NREP)])
check("표본이 창 안에만 있다", min(s1) >= 0 and max(s1) <= 23)

# ── P7. 산출물 필수 문구 ─────────────────────────────────────────────────
print("\nP7 산출물 필수 문구 — RESULTS_RECONSTRUCT_POST6_NUMBERS.md")
OUT = BASE / "RESULTS_RECONSTRUCT_POST6_NUMBERS.md"
check("산출물이 있다", OUT.exists())
if OUT.exists():
    t = OUT.read_text(encoding="utf-8")
    for phrase in (
        "라이브 채택 금지",
        "창 종료 2026-09-04 = 발행 당일 봉 «포함»",
        "DB 최신 봉 = 2026-09-04",
        "시드 **20260815**",
        "20,000회",
        "0.022%p 단일",
        "0.020%p 의무 민감도",
        "A-1 ~ A-11 전부 승계",
        "C-22 확인",
        "재계산하지 않고",
        "새 예측을 만들지 않았다",
        "총 측도",
        "폭/호가단위(칸)",
    ):
        check(f"필수 문구 「{phrase}」", phrase in t)
    check("의무 인쇄 5칸이 §1 머리에 선언돼 있다",
          "구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)" in t)
    check("모호 지점 절이 있다", "### 모호 지점" in t)
    check("중첩 굵게(**…**…**) 표기 잔재가 없다", "****" not in t)

# ── P8. 라이브 트리 격리 ─────────────────────────────────────────────────
print("\nP8 라이브 트리 import 0건 · adj_factor 산술 0건 (소스 검사)")
src = (BASE / "run_reconstruct_post6.py").read_text(encoding="utf-8")
imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
allow = {"__future__", "random", "statistics", "sys", "pathlib", "psycopg2",
         "reconstruct_prices", "run_reconstruct_post5", "run_tests"}
bad = [m for m in imports if m.split(".")[0] not in allow]
check("허용 목록 밖 import 0건", not bad, str(bad))
check("adj_factor 산술 0건", "adj_factor" not in src.replace("`adj_factor` 산술 0건", ""))
sqls = re.findall(r'"\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)', src, re.I)
check("SQL 은 SELECT 뿐", all(s.upper() == "SELECT" for s in sqls), str(set(sqls)))
check("파일 쓰기는 산출물 하나뿐",
      src.count("write_text") == 1, str(src.count("write_text")))
check("산출물 이름이 RESULTS_RECONSTRUCT_POST6_NUMBERS.md 다",
      'RESULTS_RECONSTRUCT_POST6_NUMBERS.md"' in src)

print("\n" + ("=" * 60))
if FAIL:
    print(f"FAILED {len(FAIL)}건: " + " · ".join(FAIL))
    sys.exit(1)
print("ALL PASS")
sys.exit(0)
