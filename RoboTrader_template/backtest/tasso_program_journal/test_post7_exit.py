# -*- coding: utf-8 -*-
"""`run_exit_v2_post7.py` 의 «가드 시험» — 계기가 규약대로 돌았는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「일치한다」만 보이면 비교자가
   항상 통과하는 장식일 수 있으므로 **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *가드가 고장난 게 아니라 너무 늦게 설치된 것* — 분모는 «정의»로 굳혀 둔다.

실행: `python test_post7_exit.py`  (시스템 python · 라이브 트리 import 0건 · **DB 접속 0건**)

  P1 동결 상수 불변 (ε 0.05 · E1 0.90 · E2 0.80 · 본전 1.0 · 창 종료 2026-09-11 · 발행 2026-09-12)
  P2 `TRADES` 구성 — 13건이 `INTAKE_2026-09-15_post7.md` §1 · `LABELS_2026-09-15_post7.md` 와 일치
  P3 🔴 **갈래별 분모** — 주 판정 `unknown` (E1 5 · E4 4 · X2 4 · 생략 3/7) ↔
     민감도 `TP` (E1 6 · E4 5 · X2 5 · 3/8) · PD-7 2번 표와 «값으로» 일치
  N1 대칭 — `unknown` 을 `TP` 로 접은 사본에서는 분모가 «실제로» 늘어난다(장식 아님)
  P4 `EXIT-X6` — 로보티즈·빛과전자는 제외 후 레그 0 ⇒ E1 분모 «밖» · 범한퓨얼셀 6→5
  P5 🆕 `EXIT-E1` 누적 **두 계열**(가)/(나) — 둘 다 산출되고, 90% 문턱을 사이에 두고
     갈리는 입력에서는 ⛔ 「누적 정의 의존」 문구가 실제로 나온다(대칭 단언 포함)
  P6 ε — 사용 0회(4글 연속) · 최소 하락 간격 0.02%p 를 실제로 검출한다
  P7 산출물 필수 문구 — **임시 디렉토리에 렌더**해 본문을 검사한다(저장소 산출물은 만들지 않는다)
  P8 라이브 트리 import 0건 · DB 접속 0건 · 파일 쓰기 1곳

🔴 어떤 원본 파일도 고치지 않는다. 라벨은 **메모리 사본**에서만 흔든다.
🔴 산출물은 **임시 디렉토리**에만 쓴다 — 저장소의 `RESULTS_*` 는 판정 레인이 만든다.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import run_exit_v2_post7 as P7  # noqa: E402

BASE = Path(__file__).resolve().parent
FAIL: list = []


def check(name, cond, detail=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


# ── P1. 동결 상수 ────────────────────────────────────────────────────────
print("\nP1 동결 상수 (계산 «전» 고정 — `PREREG_EXIT_V2.md` §2·§3 · PD-1)")
check("ε = 0.05%p", P7.EPS == 0.05, str(P7.EPS))
check("`EXIT-E1`/`X5` 문턱 0.90", P7.E1_MIN == 0.90, str(P7.E1_MIN))
check("`EXIT-E2`/`X2` 문턱 0.80", P7.E2_MIN == 0.80, str(P7.E2_MIN))
check("본전 |ret| 문턱 1.0%", P7.BE_MAX == 1.0, str(P7.BE_MAX))
check("창 종료 DB_UPTO = 2026-09-11 (PD-1 · B-1)", P7.DB_UPTO == "2026-09-11", P7.DB_UPTO)
check("발행일 PUB_DATE = 2026-09-12(토)", P7.PUB_DATE == "2026-09-12", P7.PUB_DATE)
check("상수를 post6 에서 «그대로» 가져왔다(재선언 아님)",
      "from run_exit_v2_post6 import" in
      (BASE / "run_exit_v2_post7.py").read_text(encoding="utf-8"))

# ── P2. TRADES 구성 ──────────────────────────────────────────────────────
print("\nP2 TRADES — INTAKE §1 13건(신규 10 + 후속 3) · LABELS 와 일치")
NM, LB, LG, LM, OP, TI, BE, NW, RG, PR = range(10)
INTAKE = {  # (라벨, 레그, 서술기준 미완결, breakeven_note, 신규, 프리셋)
    "한라캐스트 🔁후속": ("MIX", [11.22, 3.50, 3.43, 3.30, 2.04, -5.30], False, True, False,
                          "HDR60/표준형"),
    "아난티 🔁후속": ("MANUAL", [1.91], False, True, False, "HDR60/표준형"),
    "우리기술투자 🔁후속": ("MANUAL", [3.28, 3.25, 3.08], False, True, False, "HDR60/표준형"),
    "한전기술": ("SL", [13.61, 10.80, 7.37, 4.91, 3.34, -1.70], False, False, True, "HDR60/표준형"),
    "한전산업": ("SL", [15.55, 14.88, 12.70, 8.97, 5.78, -1.32], False, False, True, "HDR60/표준형"),
    "지투파워 🔂재진입": ("TP", [20.11, 18.58, 17.50, 15.08, 12.72], False, False, True,
                          "HDR60/표준형"),
    "서산": ("TP", [22.16, 16.09, 10.02], False, False, True, "Q2~MAX/표준형"),
    "강동씨엔앨": ("TP", [24.28, 18.33, 18.31, 12.61], False, False, True, "HDR60/표준형"),
    "로보티즈": ("TP", [9.13], True, False, True, "HDR60/표준형"),
    "해치텍": ("TP", [4.06, 0.46], False, True, True, "HDR60/표준형"),
    "빛과전자 🔂재진입": ("TP", [12.17], True, False, True, "HDR60/표준형"),
    "한국화장품제조 🔂재진입": ("unknown", [22.70, 16.81, 10.85], False, False, True,
                                "HDR60/안정형"),
    "범한퓨얼셀": ("TP", [18.89, 16.69, 14.55, 12.22, 10.8, 7.94], True, False, True,
                   "HDR60/표준형"),
}
got = {t[NM]: (t[LB], t[LG], t[OP], t[BE], t[NW], t[PR]) for t in P7.TRADES}
check("건수 13", len(P7.TRADES) == 13, str(len(P7.TRADES)))
check("종목 집합 일치", set(got) == set(INTAKE), "차분 " + str(set(got) ^ set(INTAKE)))
for nm, exp in INTAKE.items():
    check(f"{nm} 라벨·레그·완결·be_note·신규·프리셋", got.get(nm) == exp, str(got.get(nm)))
lab = {x: sum(1 for t in P7.TRADES if t[LB] == x)
       for x in ("TP", "SL", "MIX", "MANUAL", "unknown")}
check("라벨 집계 TP 7 · SL 2 · MIX 1 · MANUAL 2 · unknown 1",
      lab == {"TP": 7, "SL": 2, "MIX": 1, "MANUAL": 2, "unknown": 1}, str(lab))
check("레그 합 47 (신규 37 + 후속 10)",
      sum(len(t[LG]) for t in P7.TRADES) == 47, str(sum(len(t[LG]) for t in P7.TRADES)))
check("신규 레그 합 37", sum(len(t[LG]) for t in P7.TRADES if t[NW]) == 37)
check("「손실률」 레그 3 (한전기술·한전산업·한라캐스트)",
      sum(sum(t[LM]) for t in P7.TRADES) == 3)
check("`breakeven_note` 4건", sum(1 for t in P7.TRADES if t[BE]) == 4)
check("서술 기준 미완결 3건(로보티즈·빛과전자·범한퓨얼셀)",
      sorted(t[NM] for t in P7.TRADES if t[OP]) == ["로보티즈", "범한퓨얼셀", "빛과전자 🔂재진입"],
      str(sorted(t[NM] for t in P7.TRADES if t[OP])))
check("🔴 `~` 표지는 한전기술 «한 건»뿐 (PD-5 1번)",
      [t[NM] for t in P7.TRADES if t[TI]] == ["한전기술"],
      str([t[NM] for t in P7.TRADES if t[TI]]))
check("🔴 `~` 함정(서산 `Q2~MAX`)이 미완결로 «안» 새어 들어갔다 (PD-5 2번)",
      not [t for t in P7.TRADES if t[NM] == "서산"][0][TI]
      and not [t for t in P7.TRADES if t[NM] == "서산"][0][OP])
check("`RANGE_ONLY` 0건 (PD-18)", sum(1 for t in P7.TRADES if t[RG]) == 0)
check("한전기술의 `leg_open_ended` 는 레그 단위 표기다(-1.70)",
      P7.LEG_OPEN_ENDED == {"한전기술": -1.70}, str(P7.LEG_OPEN_ENDED))

# ── P3. 갈래별 분모 (PD-7 2번 표) ────────────────────────────────────────
print("\nP3 갈래별 분모 — PD-7 2번 표와 «값으로» 일치해야 한다")
D, DT = P7.denoms(False), P7.denoms(True)
check("주 판정 `unknown`: `TP` 분모 7", D["tp_n"] == 7, str(D["tp_n"]))
check("주 판정 `unknown`: `EXIT-E1` 분모 5", D["e1_n"] == 5, str(D["e1_n"]))
check("주 판정 `unknown`: `EXIT-E4` 분모 4", D["e4_n"] == 4, str(D["e4_n"]))
check("주 판정 `unknown`: `EXIT-X2` 주 분모 4", D["x2_n"] == 4, str(D["x2_n"]))
check("주 판정 `unknown`: 생략 편향 3/7", (D["om"], D["tp_n"]) == (3, 7),
      f"{D['om']}/{D['tp_n']}")
check("민감도 `TP`: `EXIT-E1` 분모 6", DT["e1_n"] == 6, str(DT["e1_n"]))
check("민감도 `TP`: `EXIT-E4` 분모 5", DT["e4_n"] == 5, str(DT["e4_n"]))
check("민감도 `TP`: `EXIT-X2` 분모 5", DT["x2_n"] == 5, str(DT["x2_n"]))
check("민감도 `TP`: 생략 편향 3/8", (DT["om"], DT["tp_n"]) == (3, 8),
      f"{DT['om']}/{DT['tp_n']}")
check("`EXIT-E4` 구성 = 지투파워·서산·강동씨엔앨·범한퓨얼셀",
      sorted(t[NM] for t in D["e4"]) ==
      sorted(["지투파워 🔂재진입", "서산", "강동씨엔앨", "범한퓨얼셀"]),
      str(sorted(t[NM] for t in D["e4"])))
check("`EXIT-X2` 구성 = 지투파워·서산·강동씨엔앨·해치텍",
      sorted(t[NM] for t in D["x2"]) ==
      sorted(["지투파워 🔂재진입", "서산", "강동씨엔앨", "해치텍"]),
      str(sorted(t[NM] for t in D["x2"])))
UNK = "한국화장품제조 🔂재진입"
check("🔴 `unknown` 건이 주 판정의 어느 `EXIT-` 분모에도 «없다» (PD-7 3번)",
      all(UNK not in [t[NM] for t in D[k]] for k in ("tp_new", "e1", "e4", "x2")))

print("\nN1 대칭 — `unknown` 을 `TP` 로 접으면 분모가 «실제로» 늘어난다(장식 아님)")
check("`TP` 갈래에서는 `unknown` 건이 분모에 «들어간다»",
      all(UNK in [t[NM] for t in DT[k]] for k in ("tp_new", "e1", "e4", "x2")))
check("네 분모가 전부 +1 씩 늘어난다",
      (DT["tp_n"] - D["tp_n"], DT["e1_n"] - D["e1_n"],
       DT["e4_n"] - D["e4_n"], DT["x2_n"] - D["x2_n"]) == (1, 1, 1, 1))
check("생략 편향 «분자»는 안 늘어난다(이 건은 완결이다)", DT["om"] == D["om"])
check("원본 라벨은 그대로다(사본만 흔들었다)",
      [t for t in P7.TRADES if t[NM] == UNK][0][LB] == "unknown")

# ── P4. EXIT-X6 ──────────────────────────────────────────────────────────
print("\nP4 `EXIT-X6` — 미완결 `TP` 의 마지막 레그 하나 제외 (E1·E4 한정 · §1-8)")
by = {t[NM]: t for t in P7.TRADES}
check("로보티즈 1레그 → 제외 후 0 ⇒ E1 분모 밖",
      P7.x6_legs(by["로보티즈"], "narr") == [])
check("빛과전자 1레그 → 제외 후 0 ⇒ E1 분모 밖",
      P7.x6_legs(by["빛과전자 🔂재진입"], "narr") == [])
check("범한퓨얼셀 6레그 → 제외 후 5",
      len(P7.x6_legs(by["범한퓨얼셀"], "narr")) == 5,
      str(P7.x6_legs(by["범한퓨얼셀"], "narr")))
check("완결 건은 레그가 안 깎인다(서산 3 유지)",
      P7.x6_legs(by["서산"], "narr") == [22.16, 16.09, 10.02])
check("🔴 `~` 기준 갈래에서는 `TP` 분모 안 건이 하나도 안 깎인다(`~` 는 `SL` 건에만 있다)",
      all(P7.x6_legs(t, "tilde") == list(t[LG]) for t in D["tp_new"]))
check("한전기술은 `~` 기준에서 레그가 깎인다(대칭 단언 — 기준이 살아 있다)",
      len(P7.x6_legs(by["한전기술"], "tilde")) == len(by["한전기술"][LG]) - 1)

# ── P5. EXIT-E1 누적 두 계열 (B-4) ───────────────────────────────────────
print("\nP5 🆕 `EXIT-E1` 누적 두 계열 — (가) 전 레그 / (나) `EXIT-X6` 적용 (B-4 · post7 부터 구속)")
ga = P7.e1_series(7, 7, "ga")
na = P7.e1_series(5, 5, "na")
check("(가) 누적 분모 = 4+6+9+7 = 26", ga[1] == 26, str(ga))
check("(나) 누적 분모 = 4+6+8+5 = 23", na[1] == 23, str(na))
check("두 계열의 post6 항이 «다르다»(9/9 vs 8/8) — 갈라 적는 이유",
      (P7.POST6["E1a_n"], P7.POST6["E1_n"]) == (9, 8),
      f"{P7.POST6['E1a_n']} vs {P7.POST6['E1_n']}")
check("post4·post5 항은 두 계열이 같다(그때는 `EXIT-X6` 이 없었다)",
      P7.POST4["E1_ok"] == P7.POST4["E1_n"] and P7.POST5["E1_ok"] == P7.POST5["E1_n"])
lo = P7.e1_series(0, 10, "ga")
check("대칭 단언 — 한쪽 계열만 낮추면 90% 문턱을 사이에 두고 «갈린다»",
      (lo[0] / lo[1] >= P7.E1_MIN) != (na[0] / na[1] >= P7.E1_MIN),
      f"{100*lo[0]/lo[1]:.1f}% vs {100*na[0]/na[1]:.1f}%")

# ── P6. ε ────────────────────────────────────────────────────────────────
print("\nP6 ε — 4글 연속 사용 0회 · 최소 하락 간격 0.02%p 검출")
used = [(t[NM], a, b) for t in P7.TRADES for a, b in P7.eps_pairs(t[LG])]
check("ε 에 기댄 통과 0회", used == [], str(used))
drops = sorted(a - b for t in P7.TRADES for a, b in zip(t[LG], t[LG][1:]) if a > b)
check("최소 하락 간격 = 0.02%p (강동씨엔앨 18.33 → 18.31)",
      abs(drops[0] - 0.02) < 1e-9, f"{drops[0]:.4f}")
check("ε(0.05) 은 «증가»에만 걸린다 — 하락 0.02 는 위반이 아니다",
      P7.nonincreasing([18.33, 18.31]) == [])
check("대칭 단언 — +0.06%p 증가는 «위반»으로 잡힌다",
      P7.nonincreasing([10.00, 10.06]) != [])
check("대칭 단언 — +0.04%p 증가는 ε 안이라 통과한다",
      P7.nonincreasing([10.00, 10.04]) == [])

# ── P7. 산출물 필수 문구 (임시 디렉토리 렌더) ────────────────────────────
print("\nP7 산출물 필수 문구 — 임시 디렉토리에 렌더해 검사(저장소 산출물은 만들지 않는다)")
tmp = Path(tempfile.mkdtemp(prefix="post7_exit_"))
real_base, real_out = P7.BASE, list(P7.OUT)
P7.BASE = tmp
del P7.OUT[:]
buf: list = []
_real_print = print
try:
    import builtins
    builtins.print = lambda *a, **k: buf.append(" ".join(str(x) for x in a))
    rc = P7.main()
finally:
    builtins.print = _real_print
    P7.BASE = real_base
art = tmp / "RESULTS_EXIT_V2_POST7_NUMBERS.md"
check("main() 이 0 을 돌려준다", rc == 0, str(rc))
check("임시 디렉토리에 산출물이 생겼다", art.exists())
check("🔴 저장소에는 산출물을 «안» 만들었다",
      not (BASE / "RESULTS_EXIT_V2_POST7_NUMBERS.md").exists()
      or (BASE / "RESULTS_EXIT_V2_POST7_NUMBERS.md").stat().st_size > 0)
if art.exists():
    t = art.read_text(encoding="utf-8")
    for phrase in (
        "# RESULTS_EXIT_V2_POST7_NUMBERS — 기계 생성 (수정 금지)",
        "발행일 2026-09-12(토) 휴장 ⇒ 마지막 거래일 · B-1",
        "실행 시 `max(date)`",
        "라이브 채택 대상이 아니다",
        "새 예측을 만들지 않는다",
        "`unknown`",
        "(가) 전 레그 계열",
        "(나) `EXIT-X6` 적용 계열",
        "누적 정의 의존",
        "방향 자기신고",
        "4글 연속 사용 0회",
        "Q2~MAX",
        "leg_open_ended",
        "구분 불가",
    ):
        check(f"필수 문구 「{phrase}」", phrase in t)
    check("갈래별 분모 표에 (5·4·4) 와 (6·5·5) 가 둘 다 있다",
          "| **%d** | **%d** | **%d** |" % (5, 4, 4) in t and "| 6 | 5 | 5 |" in t)
    check("`unknown` 을 `TP` 로 «선언»하지 않았다",
          "주 판정 `unknown`" in t)
    check("중첩 굵게(****) 표기 잔재가 없다", "****" not in t)
    check("표 행이 파이프로 닫혀 있다",
          all(ln.rstrip().endswith("|") for ln in t.splitlines()
              if ln.startswith("| ") and "|" in ln[2:]))
del P7.OUT[:]
P7.OUT.extend(real_out)

# ── P8. 라이브 트리 격리 ─────────────────────────────────────────────────
print("\nP8 라이브 트리 import 0건 · DB 접속 0건 · adj_factor 산술 0건 (소스 검사)")
src = (BASE / "run_exit_v2_post7.py").read_text(encoding="utf-8")
imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
allow = {"__future__", "sys", "pathlib", "run_exit_v2_post6"}
bad = [m for m in imports if m.split(".")[0] not in allow]
check("허용 목록 밖 import 0건", not bad, str(bad))
check("DB 접속 0건 (psycopg2 미사용)", "psycopg2" not in src)
check("adj_factor 산술 0건", "adj_factor" not in src)
check("파일 쓰기는 산출물 하나뿐", src.count("write_text") == 1, str(src.count("write_text")))
check("산출물 이름이 RESULTS_EXIT_V2_POST7_NUMBERS.md 다",
      'RESULTS_EXIT_V2_POST7_NUMBERS.md"' in src)
check("post6 을 `from … import` 로만 쓴다(파일을 열지 않는다)",
      re.search(r"^from run_exit_v2_post6 import", src, re.M) is not None
      and "open(" not in src)
# 🔑 새 코드 0줄 원칙의 «기계적» 증거 — 통계 핵이 post6 의 «같은 객체»여야 한다(사본 재정의 금지).
import run_exit_v2_post6 as P6  # noqa: E402
for fn in ("nonincreasing", "eps_pairs", "num", "seq", "x2_leg", "x6_legs", "ratio"):
    check(f"`{fn}` 이 post6 의 «같은 객체»다(재정의 0)",
          getattr(P7, fn) is getattr(P6, fn))
for cst in ("EPS", "E1_MIN", "E2_MIN", "BE_MAX"):
    check(f"`{cst}` 이 post6 값과 같다", getattr(P7, cst) == getattr(P6, cst))
check("post6 의 산출물 이름이 그대로다(그 파일을 건드리지 않았다는 방증)",
      'RESULTS_EXIT_V2_POST6_NUMBERS.md"' in
      (BASE / "run_exit_v2_post6.py").read_text(encoding="utf-8"))
p6 = BASE / "run_exit_v2_post6.py"
check("post6 스크립트가 여전히 자기 산출물 이름을 쓴다(건드리지 않았다는 방증)",
      'RESULTS_EXIT_V2_POST6_NUMBERS.md"' in p6.read_text(encoding="utf-8"))

print("\n" + ("=" * 60))
if FAIL:
    print(f"FAILED {len(FAIL)}건: " + " · ".join(FAIL))
    sys.exit(1)
print("ALL PASS")
sys.exit(0)
