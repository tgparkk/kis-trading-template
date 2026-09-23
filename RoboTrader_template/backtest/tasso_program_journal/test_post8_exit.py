# -*- coding: utf-8 -*-
"""`run_exit_v2_post8.py` 의 «가드 시험» — 계기가 동결 규약대로 돌았는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「일치한다」만 보이면 비교자가 항상 통과하는
   장식일 수 있으므로 **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *가드가 고장난 게 아니라 너무 늦게 설치된 것* — 분모는 «정의»로 굳혀 둔다.

실행: `python -m pytest test_post8_exit.py -q -p no:cacheprovider`  또는  `python test_post8_exit.py`
      (라이브 트리 import 0건 · **DB 접속 0건** · 산출물은 임시 디렉토리에 렌더해 저장소 산출물과 byte 대조)

  P1  동결 상수 — ε 0.05 · E1 0.90 · E2 0.80 · 본전 1.0 이 post6 판의 «그 값» · 최소 n(3·3·3·3·3) · 창 종료 09-18
  P2  `TRADES` 10건 = `INTAKE_2026-09-18_post8.md` §1 · `LABELS_2026-09-18_post8.md` · 원장(`ledger_trades.csv`·
      `ledger_legs.csv` b302f7f)의 레그·「손실률」·`leg_open_ended`·`manual_exit`·`breakeven_exit`·`open_ended`·라벨과 축자 일치
  P3  갈래별 분모 — (가) E1 4 · E4 3 · X2 2 · 생략 2/4 / 「우리로 제외」 3·2·1·2/3 / `~` (H) X2 1·3/4 · (P) X2 3·1/4 (PD-7 표 · PD-23)
  N1  대칭 — 라벨·신규 여부를 흔든 사본에서 분모가 «실제로» 움직인다(장식 아님)
  P4  옛 회차 재계산 — post4·5·6 = `run_exit_v2_post7.py` 동결 인용값 · post7 = post7 산출물 §9 행 축자 · 흔든 사본은 불일치
  P5  산출물 필수 문구 — D-2 세 수 · 「미등록 형: 없음」 · D-5 · D-3(대상 아님) · 라이브 금지 · B-4 두 줄 · 연결 3/3 ·
      X2 보류 · 모호 신고 2건(신규만 A/B · `~` H/P) · 등급 이름 0 · 새 라벨(「분모 의존」) 0
  P6  결정성 — 임시 디렉토리 렌더 = 저장소 `RESULTS_EXIT_V2_POST8_NUMBERS.md` byte 동일(저장소 산출물은 건드리지 않는다)
  R1  post7 회귀 — `test_post7_exit.py` 가 이 트리에서 그대로 통과(별 프로세스)
  R2  옛 판 스크립트·post7 산출물이 `154b80c` 블롭과 byte 동일(= 이 레인이 고치지 않았다) — 🔴 정정 1차(A-8):
      기준 ref = post8 산출 «이전» 마지막 커밋(`HEAD` 는 post8 WIP 커밋 뒤라 작업트리를 자기 자신과 비교한다)
  R3  소스 위생 — 허용 import · psycopg2 0 · 파일 쓰기 1곳

🔴 어떤 원본 파일도 고치지 않는다. 라벨은 **메모리 사본**에서만 흔든다.
"""
from __future__ import annotations

import builtins
import csv
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import run_exit_v2_post6 as E6
import run_exit_v2_post7 as E7
import run_exit_v2_post8 as P8

BASE = Path(__file__).resolve().parent
NUMBERS8 = BASE / "RESULTS_EXIT_V2_POST8_NUMBERS.md"
NUMBERS7 = BASE / "RESULTS_EXIT_V2_POST7_NUMBERS.md"
BASE_REF = "154b80c"   # 🔴 정정 1차(A-8·C-1) — post8 산출 «이전» 마지막 커밋
LOG8 = "224416253270"
NM, LB, LG, LM, OP, TI, BE, NW, RG, PR = range(10)
GRADE_NAMES = ["충족·참고용", "조건 미달", "낡음(재실행 금지)", "GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F"]


def _t8():
    assert NUMBERS8.exists(), "판정 실행(run_exit_v2_post8.py) 뒤에 돌린다"
    return NUMBERS8.read_text(encoding="utf-8")


# ── P1 ───────────────────────────────────────────────────────────────────
def test_P1_constants():
    assert (P8.EPS, P8.E1_MIN, P8.E2_MIN, P8.BE_MAX) == (0.05, 0.90, 0.80, 1.0)
    assert (P8.EPS, P8.E1_MIN, P8.E2_MIN, P8.BE_MAX) == (E6.EPS, E6.E1_MIN, E6.E2_MIN, E6.BE_MAX)
    for fn in ("nonincreasing", "eps_pairs", "num", "seq", "x2_leg", "x6_legs", "ratio"):
        assert getattr(P8, fn) is getattr(E6, fn), f"`{fn}` 은 post6 의 «그 객체»(재정의 0)"
    assert (P8.TP_MIN_N, P8.E4_MIN_N, P8.E2_MIN_N, P8.X2_MIN_N, P8.E3_MIN_N) == (3, 3, 3, 3, 3)
    assert (P8.DB_UPTO, P8.PUB_DATE) == ("2026-09-18", "2026-09-18")
    assert P8.UNREGISTERED_FORMS == [] and P8.FORM_WHITELIST == {"표준형"}


# ── P2 ───────────────────────────────────────────────────────────────────
def test_P2_trades_match_intake_labels_ledger():
    T = P8.TRADES
    assert len(T) == 10
    lab = {x: sum(1 for t in T if t[LB] == x) for x in ("TP", "SL", "MIX", "MANUAL", "unknown")}
    assert lab == {"TP": 6, "SL": 0, "MIX": 1, "MANUAL": 3, "unknown": 0}
    assert sum(len(t[LG]) for t in T) == 37 and sum(len(t[LG]) for t in T if t[NW]) == 30
    assert [t[NM].split()[0] for t in T if not t[NW]] == ["빛과전자", "로보티즈", "범한퓨얼셀"]
    assert [t[NM].split()[0] for t in T if t[TI]] == ["우리로"], "`~` 레그 표지는 우리로 1건(PD-5 2 함정)"
    assert [t[NM].split()[0] for t in T if t[OP]] == ["코데즈컴바인", "우리기술"], "서술 기준 미완결 2"
    assert sum(1 for t in T if t[RG]) == 0
    with open(BASE / "ledger_trades.csv", encoding="utf-8") as f:
        tr = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG8]
    with open(BASE / "ledger_legs.csv", encoding="utf-8") as f:
        lg = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG8]
    assert len(tr) == 10 and len(lg) == 37
    for k, (t, r) in enumerate(zip(T, tr), 1):
        assert int(r["item_no"]) == k and t[NM].split()[0] == r["stock_name"], (k, t[NM], r["stock_name"])
        assert r["narrative"].startswith("라벨 " + t[LB]), (t[NM], r["narrative"][:12])
        assert int(r["n_legs"]) == len(t[LG])
        assert int(r["open_ended"]) == int(t[OP]), t[NM]
        assert int(r["breakeven_exit"]) == int(t[BE]), t[NM]
        assert int(r["manual_exit"]) == int(t[LB] == "MANUAL"), t[NM]
        legs = sorted((int(x["leg_idx"]), x) for x in lg if int(x["item_no"]) == k)
        assert [float(x["ret_pct"]) for _i, x in legs] == [float(v) for v in t[LG]], t[NM]
        assert [int(x["is_loss"]) for _i, x in legs] == list(t[LM]), t[NM]
        oe = [float(x["ret_pct"]) for _i, x in legs if int(x["leg_open_ended"])]
        exp = [P8.LEG_OPEN_ENDED[t[NM]]] if t[NM] in P8.LEG_OPEN_ENDED else []
        assert oe == exp, (t[NM], oe, exp)


# ── P3 ───────────────────────────────────────────────────────────────────
def test_P3_branch_denominators():
    D = P8.denoms(P8.TRADES)
    DX = P8.denoms(P8.TRADES, excl={P8.URIRO})
    HYB = [t[:OP] + (bool(t[OP] or t[TI]),) + t[OP + 1:] for t in P8.TRADES]
    DH = P8.denoms(HYB)
    DP = P8.denoms(P8.TRADES, basis="tilde")
    assert (D["e1_n"], D["e4_n"], D["x2_n"], D["om"], D["tp_n"]) == (4, 3, 2, 2, 4), "(가) 주 — PD-7 표"
    assert (DX["e1_n"], DX["e4_n"], DX["x2_n"], DX["om"], DX["tp_n"]) == (3, 2, 1, 2, 3), "「우리로 제외」"
    assert (DH["e1_n"], DH["x2_n"], DH["om"]) == (4, 1, 3), "`~` (H) = LABELS 문언(X2 1 · 생략 3/4)"
    assert (DP["e1_n"], DP["x2_n"], DP["om"]) == (4, 3, 1), "`~` (P) 순수 문자 기준(X2 3 · 생략 1/4) — 인쇄만"
    assert sorted(t[NM].split()[0] for t in D["e4"]) == ["우리기술", "우리로", "코데즈컴바인"]
    assert sorted(t[NM].split()[0] for t in D["x2"]) == ["액스비스", "우리로"]
    assert P8.e1_ok(D["e1"]) == 4 and P8.e1_ok(D["e4"]) == 3
    assert all(not t[NW] for t in P8.TRADES if t[NM].split()[0] in ("빛과전자", "범한퓨얼셀")), \
        "후속 `TP` 2건은 「신규 건에만」으로 분모 밖"


def test_N1_symmetry_denominators_move():
    T = [list(t) for t in P8.TRADES]
    for t in T:
        if t[NM].startswith("원익"):
            t[LB] = "TP"                     # MANUAL → TP 로 흔든다(LABELS 민감도)
    D2 = P8.denoms([tuple(t) for t in T])
    assert D2["e1_n"] == 5 and D2["e4_n"] == 4, "흔든 사본에서 E1·E4 분모가 +1"
    T2 = [list(t) for t in P8.TRADES]
    for t in T2:
        if t[NM].startswith("빛과전자"):
            t[NW] = True                     # 후속 → 신규로 흔든다
    D3 = P8.denoms([tuple(t) for t in T2])
    assert D3["e1_n"] == 5 and D3["x2_n"] == 3, "후속을 신규로 읽으면 X2 가 최소 n 에 닿는다 — 「신규 건에만」 문언이 실제로 막고 있다"
    assert [t for t in P8.TRADES if t[NM].startswith("원익")][0][LB] == "MANUAL", "원본은 그대로"


# ── P4 ───────────────────────────────────────────────────────────────────
def test_P4_prior_recount_matches_frozen_quotes():
    r4, r5, r6 = (P8.recount(E.TRADES, f) for E, f in
                  ((__import__("run_exit_v2_post4"), "p4"), (__import__("run_exit_v2_post5"), "p5"), (E6, "p6")))
    q4, q5, q6 = E7.POST4, E7.POST5, E7.POST6
    assert r4["E1a"] == (q4["E1_ok"], q4["E1_n"]) and r4["E4"] == (q4["E4_ok"], q4["E4_n"]) \
        and r4["E2a"] == (q4["E2_ok"], q4["E2_n"])
    assert r5["E1a"] == (q5["E1_ok"], q5["E1_n"]) and r5["E4"] == (q5["E4_ok"], q5["E4_n"]) \
        and r5["E2a"] == (q5["E2_ok"], q5["E2_n"]) and r5["X2"] == (q5["X2_ok"], q5["X2_n"])
    assert r6["E1a"] == (q6["E1a_ok"], q6["E1a_n"]) and r6["E1n"] == (q6["E1_ok"], q6["E1_n"]) \
        and r6["E4"] == (q6["E4_ok"], q6["E4_n"]) and r6["E2a"] == (q6["E2a_ok"], q6["E2a_n"]) \
        and r6["E2b"] == (q6["E2b_ok"], q6["E2b_n"]) and r6["X2"] == (q6["X2_ok"], q6["X2_n"])
    assert r6["E3seq"] == q6["E3_SEQ"] == 1
    r7 = P8.recount(E7.TRADES, "p7")
    row7 = ("| **7번째(2026-09-12 발행) 이번** | %s | %s | %s | %s | %s | %s | %d/%d |"
            % (P8.frac(r7["E1a"]), P8.frac(r7["E1n"]), P8.frac(r7["E4"]), P8.frac(r7["E2a"]), P8.frac(r7["E2b"]),
               P8.frac(r7["X2"]), r7["X8"][0], r7["X8"][1]))
    assert row7 in NUMBERS7.read_text(encoding="utf-8").splitlines(), "post7 §9 행 축자"
    # 대칭 — 흔든 사본은 동결 인용값과 달라야 한다
    bad = [list(t) for t in E6.TRADES]
    bad[3][2] = [8.27, 15.33, 22.24]         # 헥토(post6) 시퀀스를 뒤집는다
    rb = P8.recount([tuple(t) for t in bad], "p6")
    assert rb["E1a"] != (q6["E1a_ok"], q6["E1a_n"]), "흔든 사본에서는 재계산이 동결값과 갈린다"
    # (A) 정의 — post4·post5 에서 (B) 와 다르다(모호 신고의 근거)
    assert (r4["E2bA"], r4["E2b"]) == ((2, 2), (2, 3)) and (r5["E2bA"], r5["E2b"]) == ((2, 2), (2, 3))
    assert r6["E2bA"] == r6["E2b"] and r7["E2bA"] == r7["E2b"]


# ── P5 ───────────────────────────────────────────────────────────────────
def test_P5_required_phrases():
    t = _t8()
    for needle in [
        "# RESULTS_EXIT_V2_POST8_NUMBERS — 기계 생성 (수정 금지)",
        "**창 종료 2026-09-18 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**",
        "**실행 시 `max(date)` = 2026-09-23 · 그 날짜 행수 2,764 — 기록만(창 아님)**",
        "🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1)",
        "| `EXIT-E1` **4** · `EXIT-E4` **3** · `EXIT-X2` **2** | `EXIT-E1` **4** · `EXIT-E4` **3** · `EXIT-X2` **2** "
        "(`unknown` 0 ⇒ (i) 과 같다) | **미등록 형: 없음** |",
        "`(갈래 이름, n, 답)`",
        "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 — / `approx` 포함 분모 —」",
        "- **(가) 전 레그 계열** = **30/30 = 100.0%**",
        "- **(나) `EXIT-X6` 적용 계열** = **27/27 = 100.0%**",
        "「누적 정의 의존」 **미발동**",
        "**후속 연결 지점 증가 3/3 관측**",
        "**`EXIT-X2` (가) 주 = 2/2 = 100.0%** ⇒ **⛔ 보류 — 완결 `TP` 2 < 3 · 통과로 인용 금지**",
        "⛔ 두 규칙 구분 불가",
        "**ε 은 5글 연속 사용 0회**",
        "모호 신고 — 「신규만」 갈래의 정의가 두 문서에서 다르다",
        "모호 신고 — `~` 기준의 두 읽기",
        "재계산 불일치 **0건**",
        "✅ 축자 일치",
        "「우리로 제외」",
        "EXIT-X2` 본전매도 레그 = 저자 «원» 시퀀스의 마지막",
        "새 예측을 만들지 않는다",
    ]:
        assert needle in t, needle
    for g in GRADE_NAMES:
        assert g not in t, f"등급 이름 「{g}」 이 없어야 한다(§6 단계)"
    assert "분모 의존" not in t, "post7 이 철회한 신설 라벨을 다시 만들지 않는다"
    assert "****" not in t and "%%" not in t
    assert all(ln.rstrip().endswith("|") for ln in t.splitlines() if ln.startswith("| ")), "표 행이 파이프로 닫힌다"


# ── P6 ───────────────────────────────────────────────────────────────────
def test_P6_render_is_byte_identical():
    tmp = Path(tempfile.mkdtemp(prefix="post8_exit_"))
    shutil.copy(NUMBERS7, tmp / NUMBERS7.name)          # post7 §9 행 대조 입력
    real_base, real_out, real_print = P8.BASE, list(P8.OUT), builtins.print
    try:
        P8.BASE = tmp
        del P8.OUT[:]
        builtins.print = lambda *a, **k: None
        assert P8.main() == 0
    finally:
        builtins.print = real_print
        P8.BASE = real_base
        del P8.OUT[:]
        P8.OUT.extend(real_out)
    got = (tmp / NUMBERS8.name).read_bytes()
    assert hashlib.md5(got).hexdigest() == hashlib.md5(NUMBERS8.read_bytes()).hexdigest(), \
        "저장소 산출물 = 지금 스크립트의 출력(결정적 · 손 편집 없음)"
    shutil.rmtree(tmp, ignore_errors=True)


# ── R1 · R2 · R3 ─────────────────────────────────────────────────────────
def test_R1_post7_suite_still_passes():
    r = subprocess.run([sys.executable, "-X", "utf8", "test_post7_exit.py"], cwd=BASE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "ALL PASS" in r.stdout


def _blob_md5(rel):
    out = subprocess.run(["git", "show", f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/{rel}"],
                         cwd=BASE, capture_output=True)
    assert out.returncode == 0, rel
    return hashlib.md5(out.stdout).hexdigest()


def test_R2_upstream_untouched():
    for rel in ("run_exit_v2_post4.py", "run_exit_v2_post5.py", "run_exit_v2_post6.py", "run_exit_v2_post7.py",
                "RESULTS_EXIT_V2_POST7_NUMBERS.md", "RESULTS_EXIT_V2_POST6_NUMBERS.md",
                "ledger_trades.csv", "ledger_legs.csv"):
        assert hashlib.md5((BASE / rel).read_bytes()).hexdigest() == _blob_md5(rel), f"{rel} 가 {BASE_REF} 와 다르다"
    # 🔴 대칭 — 기준 ref 에 post8 판은 «없다»(ref 가 post8 이전임을 확인 · 검사력)
    miss = subprocess.run(["git", "cat-file", "-e",
                           f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/run_exit_v2_post8.py"],
                          cwd=BASE, capture_output=True)
    assert miss.returncode != 0


def test_R3_source_hygiene():
    src = (BASE / "run_exit_v2_post8.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
    allow = {"__future__", "sys", "pathlib", "run_exit_v2_post4", "run_exit_v2_post5", "run_exit_v2_post6",
             "run_exit_v2_post7"}
    assert not [m for m in imports if m.split(".")[0] not in allow]
    assert "psycopg2" not in src and "adj_factor" not in src
    assert src.count("write_text") == 1 and 'RESULTS_EXIT_V2_POST8_NUMBERS.md"' in src
    assert "open(" not in src, "옛 판 스크립트를 파일로 열지 않는다(import 만)"


def main() -> int:
    import pytest
    return pytest.main([__file__, "-q", "-p", "no:cacheprovider"])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
