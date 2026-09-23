# -*- coding: utf-8 -*-
"""`run_selection_post8.py` 의 «가드 시험» — 분모 규약·인쇄 의무가 실제로 뭔가를 «막는지» 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「`exact` 가 4다」만 보이면 그 필터가 장식일 수 있으므로
   **일부러 흔든 사본에서 불일치가 나는지**도 본다(`test_post7_selection.py` 문형 승계).
🔑 post7 판은 `main()` 만 있어 pytest 가 0건을 모았다 — 이 파일은 `test_*` 함수로 쓰고, post7 회귀는 R1 이
   `test_post7_selection.main()` 을 직접 불러 pytest 에 올린다(`test_post8_ledger.py` R1 문형).

실행: `python -m pytest test_post8_selection.py -q -p no:cacheprovider`  (DB 접속 0건 · 라이브 트리 import 0건)
      — 산출물 검사(P8~P10)는 `RESULTS_SELECTION_POST8_NUMBERS.md` 를 «읽기만» 한다.

  P1  동결 상수 불변(`DB_UPTO` 09-18 · 시드 · 창 5/10/20 · 문턱) = post7 판과 같은 값
  P2  분모 구성 = INTAKE §1 축자(신규 7 · `exact` 4 · `approx` 2 · `none` 1 · 후속 3 제외) + 원장 `b302f7f` 대조
  N1  (음성) 정밀도 필터를 무력화하면 분모가 «오염»된다
  P3  재진입 플래그(판정 분모 안 0 · 헥토 2/7 · 코데즈 7/7) ↔ PD-3 표 · N2 흔들면 그 1칸만 잡힌다
  P4  `P6-절단가드-A` 산술(0/4 미발동 · 2/4 발동 · 등호 포함)
  P5  C-17 NaN 규약 존재 · PD-12 예고 문장(≥ 96 · 77/85)
  P6  §1-4 창 규약 갈래 7 · 조합 49 · 헥토 모순 갈래 5
  P7  재사용 증명(post6·post7 의 «그 함수» — 재정의 0)
  P8  산출물 의무 줄 — D-3 · D-6 · D-9 ①~⑤ · 라이브 문구 · PD-1 두 줄
  P9  D-5 — 예측마다 `(갈래 이름, n, 답)` 행 · 「우리로 제외」 = 인쇄만 · 항등 명시
  P10 산출물에 실행 «시각»이 없다(바이트 결정론) · 등급(`GT-`) 0
  R1  post7 회귀 — `test_post7_selection.main()` 전건 통과
"""
from __future__ import annotations

import csv
import io
import re
from contextlib import redirect_stdout
from pathlib import Path

import run_selection
import run_selection_post6 as P6
import run_selection_post7 as P7
import run_selection_post8 as P8
import test_post7_selection as T7

BASE = Path(__file__).resolve().parent
INTAKE = BASE / "INTAKE_2026-09-18_post8.md"
PD = BASE / "PREDECISION_2026-09-18_post8.md"
NUM = BASE / "RESULTS_SELECTION_POST8_NUMBERS.md"
LOG = "224416253270"


def intake_rows():
    """INTAKE §1 표 10행 → (번호, 종목, 코드, 정밀도|'follow', 신규/후속)."""
    out = []
    sec = INTAKE.read_text(encoding="utf-8").split("## §1.")[1].split("## §2.")[0]
    for ln in sec.splitlines():
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


def numbers():
    assert NUM.exists(), "RESULTS_SELECTION_POST8_NUMBERS.md 가 없다 — run_selection_post8.py 를 먼저 돌린다"
    return NUM.read_text(encoding="utf-8")


# ---- P1 ----------------------------------------------------------------------
def test_P1_frozen_constants():
    assert P8.DB_UPTO == "2026-09-18" and P8.POST8_POST_DATE == "2026-09-18"
    assert P8.POST8_LOG_NO == LOG and P8.PROG_VER == "1.0.42"
    assert (P8.W_TDAYS, P8.W_CAL_POST4, P8.WIN20) == (5, 10, 20)
    assert (P8.W_TDAYS, P8.WIN20, P8.UP15, P8.N_DEGRADE, P8.DROP_GUARD, P8.SEED) == \
        (P7.W_TDAYS, P7.WIN20, P7.UP15, P7.N_DEGRADE, P7.DROP_GUARD, P7.SEED)
    assert abs(P8.TRUNC_GUARD - 1.0 / 3.0) < 1e-12 and P8.MIN_N == 3
    assert P8.UNIV_LO == "2026-04-01" and P8.REGIME == "2026-09-14"
    assert P8.SWEEP_D1 == "2026-09-21 15:35:00" and P8.PROBE_WIN == ("2026-07-24", "2026-09-18")
    assert P8.DB_UPTO_CUT == "2026-09-11" and P8.DB_UPTO_CUT < P8.REGIME < P8.DB_UPTO


# ---- P2 / N1 -----------------------------------------------------------------
def test_P2_denominator_matches_intake():
    rows = intake_rows()
    assert len(rows) == 10 and [r[0] for r in rows] == list(range(1, 11))
    want_new = [(nm, code, prec) for _i, nm, code, prec, kind in rows if kind == "신규"]
    got_new = [(nm, code, prec) for nm, code, _d, prec, _t in P8.NEW8]
    assert got_new == want_new, (got_new, want_new)
    assert [r[0] for r in P8.EXACT8] == ["우리로", "JW신약", "액스비스", "우리기술"]
    assert [r[1] for r in P8.EXACT8] == ["046970", "067290", "0011A0", "032820"]
    assert [r[2] for r in P8.EXACT8] == ["2026-09-11", "2026-09-01", "2026-09-11", "2026-09-09"]
    assert [r[0] for r in P8.APPROX8] == ["헥토파이낸셜", "코데즈컴바인"] and P8.NONE8 == ["원익"]
    follow = [nm for _i, nm, _c, _p, kind in rows if kind == "후속"]
    assert follow == [f[0] for f in P8.FOLLOW8] == ["빛과전자", "로보티즈", "범한퓨얼셀"]
    assert all(nm not in [r[0] for r in P8.NEW8] for nm in follow), "후속이 신규 분모에 들어갔다"
    assert "032820" != "041190" and "우리기술투자" not in [r[0] for r in P8.NEW8]   # PD-11 유사명


def test_P2b_ledger_b302f7f():
    tr = [t for t in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8"))
          if t["post_log_no"] == LOG]
    assert len(tr) == 10
    by = {t["stock_name"]: t for t in tr}
    for nm, _c, d, prec, _t in P8.NEW8:
        assert by[nm]["reg_date_precision"] == prec, nm
        assert by[nm]["reg_date"] == (d or ""), nm
    for nm, _c, _t in P8.FOLLOW8:
        assert by[nm]["reg_date_precision"] == "none" and by[nm]["reg_date"] == "" and "CONTINUATION" in by[nm]["narrative"]
    assert by["액스비스"]["narrative"].count("0011A0") >= 1


def test_N1_precision_filter_bites():
    poisoned = [(nm, c, d, t) for nm, c, d, p, t in P8.NEW8]          # 정밀도 무시
    assert len(poisoned) == 7 != len(P8.EXACT8) == 4
    assert any(d is None for _n, _c, d, _t in poisoned)               # none/approx 가 섞이면 등록일이 없다


# ---- P3 / N2 -----------------------------------------------------------------
def test_P3_reentry_flags():
    assert P8.REENTRY_EXACT == set() and set(P8.PD3_FLAG_EXACT.values()) == {0}
    h = P8.PD3_FLAG_BR["헥토파이낸셜"]
    k = P8.PD3_FLAG_BR["코데즈컴바인"]
    assert sum(h.values()) == 2 and [d for d, v in h.items() if v] == ["2026-08-28", "2026-08-31"]
    assert sum(k.values()) == 7
    assert P8.PREV_CYCLE == {"헥토파이낸셜": ["2026-08-28"], "코데즈컴바인": ["2026-08-21", "2026-08-19"]}
    seg = PD.read_text(encoding="utf-8").split("## PD-3")[1].split("## PD-4")[0]
    assert "D ∈ {08-28, 08-31} ⇒ **1**" in seg and "7갈래 «전부»" in seg
    assert "`P6-PRIOR_CYCLE_IN_WINDOW`(우리로) = 0" in seg


def test_N2_flag_shake_caught():
    shaken = dict(P8.PD3_FLAG_BR["헥토파이낸셜"])
    shaken["2026-08-27"] = 1
    caught = [d for d in shaken if shaken[d] != P8.PD3_FLAG_BR["헥토파이낸셜"][d]]
    assert caught == ["2026-08-27"] and sum(shaken.values()) == 3


# ---- P4 ----------------------------------------------------------------------
def test_P4_trunc_guard_arith():
    fires = (lambda num, den: den > 0 and num / den >= P8.TRUNC_GUARD)
    assert fires(0, 4) is False and fires(1, 4) is False
    assert fires(2, 4) is True and fires(1, 3) is True and fires(2, 6) is True


# ---- P5 ----------------------------------------------------------------------
def test_P5_c17_and_pd12():
    src = (BASE / "run_selection.py").read_text(encoding="utf-8")
    assert sum(1 for ln in src.splitlines() if "where(prev_max.notna())" in ln) == 1
    pd12 = PD.read_text(encoding="utf-8").split("## PD-12")[1].split("## PD-13")[0]
    assert "≥ 96" in pd12 and "77/85" in pd12 and "대상 0 예고" in pd12
    assert "0/4" in pd12


# ---- P6 ----------------------------------------------------------------------
def test_P6_window_rule_branches():
    for nm in ("헥토파이낸셜", "코데즈컴바인"):
        lab, lo, hi, days = P8.APPROX_BRANCHES[nm]
        assert (lo, hi) == ("2026-08-21", "2026-08-31") and len(days) == 7
        assert days == ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27",
                        "2026-08-28", "2026-08-31"]
    assert len(P8.APPROX_BRANCHES["헥토파이낸셜"][3]) * len(P8.APPROX_BRANCHES["코데즈컴바인"][3]) == 49
    assert P8.CONTRA["헥토파이낸셜"] == set(P8.AUG_END[:5])
    pd4 = PD.read_text(encoding="utf-8").split("## PD-4")[1].split("## PD-5")[0]
    assert "08-21·24·25·26·27·28·31" in pd4


# ---- P7 ----------------------------------------------------------------------
def test_P7_reuse_no_redefinition():
    for fn in ("stat_tdays", "stat_cal", "med", "s1_row", "feat_table", "aggs", "fmt"):
        assert getattr(P8, fn) is getattr(P6, fn), fn
    for fn in ("load_universe_day", "universe_raw_count", "win20_bars", "pct", "snapshot_tail"):
        assert getattr(P8, fn) is getattr(P7, fn), fn
    assert P8.build_features is run_selection.build_features and P8.FEATS == run_selection.FEATS
    assert P8.NEW6 == P7.NEW6 and P8.NEW5 == P7.NEW5 and P8.NEW4 == P7.NEW4
    assert P6.OUT is not P8.OUT, "import 만으로 post6 버퍼를 가로채면 안 된다(main 안에서만 잇는다)"


# ---- P8 ~ P10 (산출물) --------------------------------------------------------
def test_P8_numbers_duty_lines():
    t = numbers()
    assert "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 4 / `approx` 포함 분모 6」" in t   # D-3
    assert "`ddof=1`" in t and "sd 는 문턱이 아니다" in t                                          # D-6
    assert "09-18 봉은 D+1(09-21) sweep 이후 읽음" in t                                            # D-9 ③
    assert re.search(r"\| ① \| 쿼리 실행 시각\(KST\) \|.*실행 stdout 에만 인쇄.*D\+1 sweep\) = 예", t)  # D-9 ①
    assert re.search(r"\| ② \| 창 구간 `max\(daily_prices\.updated_at\)` \| `\[2026-07-24, 2026-09-18\]` \*\*2026-\d\d-\d\d", t)
    assert re.search(r"≥ 09-21 15:35: (예|아니오)\*\*", t)                                           # D-9 ④
    lines = re.findall(r"창 `\[\d{4}-\d\d-\d\d, \d{4}-\d\d-\d\d\]` 은 제도 경계 2026-09-14 를 걸친다 — "
                       r"경계 전 \d+ 봉 / 후 \d+ 봉 · 혼합 빈티지", t)                                    # D-9 ⑤
    assert len(lines) >= 1
    assert "라이브 채택 대상이 아니다" in t
    assert "창 종료 2026-09-18 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1" in t
    assert re.search(r"실행 시 `max\(date\)` = \d{4}-\d\d-\d\d · 그 날짜 행수 [\d,]+ — 기록만\(창 아님\)", t)
    assert "C-17 반영 | ✅" in t


def test_P9_branch_triples():
    t = numbers()
    sec = t.split("## §10.")[1].split("## §11.")[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| `")]
    for lbl in ("`SEL-S1`", "`P6-S1h`", "`SEL-S2`", "`SEL-S3`", "`SEL-S4`", "`P6-S1h-N`"):
        mine = [r for r in rows if r.startswith("| " + lbl + " |")]
        assert len(mine) >= 5, lbl
        for r in mine:
            c = [x.strip() for x in r.split("|")]
            assert len(c) == 7 and c[2] and c[3] and c[4], (lbl, r)      # (갈래 이름, n, 답) 세 쪽
        assert any("항등" in r and "재진입" in r for r in mine), lbl
        assert any("항등" in r and "절단" in r for r in mine), lbl
        assert any("「우리로 제외」" in r and "인쇄만" in r and "❌" in r for r in mine), lbl
        assert any("`approx` 포함 조합" in r for r in mine), lbl


def test_P10_no_timestamp_no_grade():
    t = numbers()
    # 박혀도 되는 시각은 «옮겨 적은» 관리자 착수 실측(상수) 하나뿐이다 — 이 실행의 now() 는 stdout 에만 간다.
    stamps = set(re.findall(r"2026-09-2[4-9] \d\d:\d\d:\d\d", t))
    assert stamps <= {P8.MGR["run"][:19]}, ("실행 시각이 산출물에 박혔다(바이트 결정론 위반)", stamps)
    assert "GT-" not in t
    assert "\r" not in t and t.endswith("\n")


# ---- R1 ----------------------------------------------------------------------
def test_R1_post7_selection_suite():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = T7.main()
    assert rc == 0, buf.getvalue()[-2000:]
    assert "✅ 전건 통과" in buf.getvalue()
