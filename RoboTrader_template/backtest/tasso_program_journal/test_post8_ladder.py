# -*- coding: utf-8 -*-
"""`run_ladder_tranche_post8.py` 의 «가드 시험» — 누적 재계산이 동결 규약·옛 값을 흔들지 않았는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「일치한다」만 보이면 비교자가 항상 통과하는
   장식일 수 있으므로 **일부러 흔든 사본에서 불일치가 나는지**도 본다.
🔑 계열 규칙: *가드를 시험하지 않으면 그것도 장식이다* — 읽은 시각 박제(`prior_stamp`)는 지문이 움직이면
   «반드시» 새 시각을 박아야 한다(재사용이 새지 않는지).

실행: `python -m pytest test_post8_ladder.py -q -p no:cacheprovider`  또는  `python test_post8_ladder.py`
      (라이브 트리 import 0건 · **DB 접속 0건** — 산출물 `RESULTS_LADDER_TRANCHE_POST8_NUMBERS.md` 를 읽기만 한다)

  P1  동결 상수 불변 (δ 1.0 · 시드 20260815 · 순열 200,000 · 게이트 40 · END 09-18 · 발행 09-18 · 경계 09-14)
  P2  `ITEMS` 구성 — 앞 28건 = post7 판 · 앞 22건 = post6 판 · 앞 12건 = 동결 생성기 · post8 4건 = INTAKE `exact` 4 ·
      원장(`ledger_trades.csv` b302f7f)의 `reg_date`·`fill_n` 과 일치 · 등록일 축 밖 4건·`approx` 2건 부재
  N1  대칭 — 메모리 사본 한 칸을 흔들면 P2 비교가 정확히 그 칸을 잡는다
  P3  상류 무수정·재사용 — 통계 핵·가드·`build_rows`·누적 목록이 «그 객체» · import 만으로 `LAD.OUT` 결속을 안 흔든다
  P4  `P6-창5절단가드-A` 산술 — 0/7·0/4 미발동 · post7 2/6(참고 전건) 발동 · 1/3 등호
  P5  읽은 시각 박제 — 같은 지문이면 이전 ① 을 잇고, 지문이 한 글자라도 다르면 None(새 시각) · 파일 없으면 None
  P6  post7 「절단 시점 값」 인용이 동결본 축자와 일치(빛과전자 4봉 20.33 · 범한퓨얼셀 3봉 6.42 · 지투파워 3갈래)
  P7  산출물 필수 문구(D-9 ①~⑤ · D-7 두 산술·분모 갈래·1회차 · D-1 세 수·누적 줄 · D-5 · D-3 · 라이브 금지 · 계열 재현)
  P8  산출물 수치 정합 — 「누적 비교가능 쌍」 줄 = §2 창5 행 · 혼합 빈티지 8줄 = PD-27 (바) · 등급 이름 0
  R1  post7 회귀 — `test_post7_ladder.py --require-artifact` 가 이 트리에서 그대로 통과(별 프로세스)
  R2  상류 파일·post7 산출물이 `154b80c` 블롭과 byte 동일(= 이 레인이 고치지 않았다) — 🔴 정정 1차(A-8·C-1):
      기준 ref = post8 산출 «이전» 마지막 커밋 `154b80c`(`HEAD` 는 post8 WIP 커밋 뒤라 작업트리를 자기 자신과 비교한다)

🔴 어떤 원본 파일도 고치지 않는다. 동결본은 메모리 사본에서만 흔든다.
"""
from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import run_ladder_tranche as LAD
import run_ladder_tranche_post6 as P6
import run_ladder_tranche_post7 as P7
import run_ladder_tranche_post8 as P8

BASE = Path(__file__).resolve().parent
NUMBERS7 = BASE / "RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md"
NUMBERS8 = BASE / "RESULTS_LADDER_TRANCHE_POST8_NUMBERS.md"
BASE_REF = "154b80c"   # 🔴 정정 1차 — post8 산출 «이전» 마지막 커밋
LOG8 = "224416253270"

# `INTAKE_2026-09-18_post8.md` §1 — 신규 7건 중 `exact` 4건 (종목, 코드, 등록일, 차수 N)
INTAKE_EXACT4 = [
    ("우리로", "046970", "2026-09-11", 1),
    ("JW신약", "067290", "2026-09-01", 1),
    ("액스비스", "0011A0", "2026-09-11", 1),
    ("우리기술", "032820", "2026-09-09", 1),
]
OUT_OF_AXIS = ["원익", "빛과전자", "로보티즈", "범한퓨얼셀"]     # none 1 + 후속 3
APPROX2 = ["헥토파이낸셜", "코데즈컴바인"]
# PD-27 (바) — `LAD-` 창5 걸침 칸 (종목, 시작, 끝, 전, 후)
CROSS8 = [("우리로", "2026-09-11", "2026-09-17", 1, 4), ("액스비스", "2026-09-11", "2026-09-17", 1, 4),
          ("우리기술", "2026-09-09", "2026-09-15", 3, 2), ("빛과전자", "2026-09-08", "2026-09-14", 4, 1),
          ("범한퓨얼셀", "2026-09-09", "2026-09-15", 3, 2), ("지투파워", "2026-09-08", "2026-09-14", 4, 1),
          ("지투파워", "2026-09-09", "2026-09-15", 3, 2), ("지투파워", "2026-09-10", "2026-09-16", 2, 3)]
GRADE_NAMES = ["충족·참고용", "조건 미달", "낡음(재실행 금지)", "GT-A", "GT-B", "GT-C", "GT-D", "GT-E", "GT-F"]


def _t8():
    assert NUMBERS8.exists(), f"{NUMBERS8.name} 이 없다 — 판정 실행(run_ladder_tranche_post8.py) 뒤에 돌린다"
    return NUMBERS8.read_text(encoding="utf-8")


# ── P1 ───────────────────────────────────────────────────────────────────
def test_P1_frozen_constants():
    assert (P8.DELTA, P8.NULL_SEED, P8.NPERM, P8.PAIR_THRESHOLD) == (1.0, 20260815, 200_000, 40)
    assert (P8.DELTA, P8.NULL_SEED, P8.NPERM, P8.PAIR_THRESHOLD) == \
        (LAD.DELTA, LAD.NULL_SEED, LAD.NPERM, LAD.PAIR_THRESHOLD), "동결 생성기와 같은 값(재정의 0)"
    assert (P8.END, P8.PUB8, P8.END7, P8.BOUNDARY) == ("2026-09-18", "2026-09-18", "2026-09-11", "2026-09-14")
    assert P8.PUB8 == P8.END, "발행일 = 거래일 = 창 종료(post6 과 같은 갈래 · post7 과 다른 갈래)"
    assert P8.TRUNC5_MIN_BARS == P6.TRUNC5_MIN_BARS == 5
    assert (P8.GUARD_A_NUM, P8.GUARD_A_DEN) == (1, 3)
    assert (P8.N_NEW_POST8, P8.N_EXACT_POST8) == (7, 4), "가드-A 분모 = 이번 글 신규 7 · 주 표본 = exact 4"
    assert (P8.LAD_P2_LO, P8.LAD_P2_HI) == (15.0, 35.0)


# ── P2 ───────────────────────────────────────────────────────────────────
def test_P2_items_composition():
    assert len(P8.ITEMS) == 32
    assert list(P8.ITEMS[:28]) == list(P7.ITEMS), "앞 28건 = post7 판 그대로"
    assert list(P8.ITEMS[:22]) == list(P6.ITEMS), "앞 22건 = post6 판 그대로(3단 승계)"
    assert list(P8.ITEMS[:12]) == list(LAD.ITEMS), "앞 12건 = 동결 생성기 그대로"
    got = [(it[0], it[1], it[2], it[3]) for it in P8.ITEMS[28:]]
    assert got == INTAKE_EXACT4
    assert all(it[3] == 1 for it in P8.ITEMS[28:]), "🔴 exact 4건 전부 N = 1(PD-13)"
    assert all(it[5] == P8.PUB8 and it[4] == "post8" and it[6] is False for it in P8.ITEMS[28:])
    names8 = [it[0] for it in P8.ITEMS[28:]]
    assert not set(names8) & set(OUT_OF_AXIS), "등록일 축 밖 4건이 주 표본에 없다"
    assert not set(names8) & set(APPROX2), "approx 2건도 주 표본에 없다(§7-1 갈래)"
    assert [n for n, *_ in P8.OUT_OF_REGDAY_AXIS] == OUT_OF_AXIS
    assert [a[0] for a in P8.APPROX_BRANCHES] == APPROX2 and [a[2] for a in P8.APPROX_BRANCHES] == [1, 2]
    assert [it[0] for it in P8.ITEMS if it[6]] == ["코데즈컴바인", "한켐", "현대약품", "지투파워", "빛과전자"], \
        "B-7 2번째 사이클 5건 — post8 은 exact 안 0"
    assert len(P8.FIRST_ONLY_POST8_NEW) == 6 and P8.FIRST_ONLY_POST8_EXACT == names8


def test_P2b_items_match_ledger():
    """원장(b302f7f) post8 행과 대조 — 게이트가 안 보는 칸(등록일·정밀도·fill_n)이 스크립트와 같은가."""
    with open(BASE / "ledger_trades.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["post_log_no"] == LOG8]
    assert len(rows) == 10
    exact = [(r["stock_name"], r["reg_date"], int(r["fill_n"])) for r in rows if r["reg_date_precision"] == "exact"]
    assert exact == [(n, d, N) for n, _c, d, N in INTAKE_EXACT4]
    prec = sorted(r["reg_date_precision"] for r in rows)
    assert prec == sorted(["exact"] * 4 + ["approx"] * 2 + ["none"] * 4)
    appr = {r["stock_name"]: int(r["fill_n"]) for r in rows if r["reg_date_precision"] == "approx"}
    assert appr == {"헥토파이낸셜": 1, "코데즈컴바인": 2}


def test_N1_symmetry_shaken_copy():
    shaken = [list(t) for t in P8.ITEMS[:28]]
    shaken[26][3] = 9                       # post7 빛과전자의 N 을 흔든다
    caught = [i for i, (a, b) in enumerate(zip(shaken, P7.ITEMS)) if tuple(a) != tuple(b)]
    assert caught == [26]
    got = [[t[0], t[1], t[2], t[3]] for t in P8.ITEMS[28:]]
    got[2][1] = "001100"                    # 액스비스 코드를 흔든다
    assert sum(1 for a, b in zip(got, INTAKE_EXACT4) if tuple(a) != b) == 1


# ── P3 ───────────────────────────────────────────────────────────────────
def test_P3_reuse_same_objects():
    for nm in ("pairset", "statV", "permute_null", "run_axis"):
        assert getattr(P8, nm) is getattr(LAD, nm), nm
    for nm in ("guard_a_fires", "verdict_t1", "median"):
        assert getattr(P8, nm) is getattr(P6, nm), nm
    assert P8.build_rows is P7.build_rows and P8.ITEMS_CUM28 is P7.ITEMS
    assert P8.ITEMS[:28] is not P7.ITEMS, "새 리스트(상류 리스트를 제자리에서 변형하지 않는다)"


def test_P3b_import_does_not_rebind_output_buffer():
    """`LAD.OUT` 재지정은 `main()` 안에서만 — import 만으로는 post7 판 결속(`LAD.OUT is P7.OUT`)이 유지된다."""
    assert LAD.OUT is P7.OUT
    src = (BASE / "run_ladder_tranche_post8.py").read_text(encoding="utf-8")
    top = [ln for ln in src.splitlines() if ln.startswith("LAD.OUT")]
    assert top == [], "모듈 최상위에 `LAD.OUT = …` 가 없다"
    assert "    LAD.OUT = OUT" in src


# ── P4 ───────────────────────────────────────────────────────────────────
def test_P4_guard_a_arithmetic():
    assert P8.guard_a_fires(0, 7) is False and P8.guard_a_fires(0, 4) is False, "주 0/7 · exact 0/4 — 미발동"
    assert P8.guard_a_fires(2, 6) is True, "post7 exact 2/6 = 33.3% — 문턱 «도달»(참고 전건 · 계수 안 함)"
    assert P8.guard_a_fires(1, 3) is True and P8.guard_a_fires(2, 7) is False and P8.guard_a_fires(3, 7) is True


# ── P5 ───────────────────────────────────────────────────────────────────
def test_P5_prior_stamp_reuse_and_symmetry():
    fp = "| ② 창 구간 `max(daily_prices.updated_at)` | 지문 A |"
    body = ("# x\n| ① 쿼리 실행 시각(KST) | **2026-09-24 00:00:01** — 설명 |\n" + fp + "\n")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "N.md"
        assert P8.prior_stamp(p, fp) is None, "파일이 없으면 새 시각"
        p.write_text(body, encoding="utf-8")
        assert P8.prior_stamp(p, fp) == "2026-09-24 00:00:01", "같은 지문 ⇒ 이전 ① 을 잇는다"
        assert P8.prior_stamp(p, fp.replace("A", "B")) is None, "🔴 지문 한 글자 차이 ⇒ 반드시 새 시각(재사용이 새지 않는다)"
        p.write_text(body.replace("**2026-09-24 00:00:01**", "2026-09-24"), encoding="utf-8")
        assert P8.prior_stamp(p, fp) is None, "① 형식이 깨지면 잇지 않는다"
    assert P8.STAMP_RE.search(_t8()), "실제 산출물의 ① 줄이 재사용 정규식에 걸린다(다음 재실행이 잇는다)"


# ── P6 ───────────────────────────────────────────────────────────────────
def test_P6_post7_truncation_quotes_match_frozen():
    t7 = NUMBERS7.read_text(encoding="utf-8")
    for nm, ref in P8.POST7_TRUNC_ASOF.items():
        assert f"{nm}({ref['d0']} 등록 · 창5 **{ref['n5_asof']}봉** / 규정 5봉 · DD5 = **{ref['dd5_asof']:.2f}%**)" in t7
    for d0, (n5, v) in P8.POST7_G2_ASOF.items():
        assert re.search(rf"^\| {d0} \| [\d,]+ \| {n5} \| [\d,]+ \| \*\*{v:.2f}%\*\*", t7, re.M), d0
    assert "DD5 = **99.99%**" not in t7, "대칭: 없는 값은 안 잡힌다(비교가 장식이 아니다)"
    assert P8.PD27_CROSS5_G2 == {"2026-09-08": (4, 1), "2026-09-09": (3, 2), "2026-09-10": (2, 3)}


# ── P7 ───────────────────────────────────────────────────────────────────
def test_P7_required_phrases():
    t = _t8()
    for needle in [
        "# RESULTS_LADDER_TRANCHE_POST8_NUMBERS — 기계 생성 (수정 금지)",
        "**창 종료 2026-09-18 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**",
        "— 기록만(창 아님)**",
        "🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1)",
        "| ① 쿼리 실행 시각(KST) |",
        "| ② 창 구간 `max(daily_prices.updated_at)` |",
        "「09-18 봉은 D+1(09-21) sweep 이후 읽음」",
        "≥ 09-21 15:35: 예」**(기록 · 통과 조건 아님",
        "「정규장만」 갈래 | **열지 않음**",
        "`adj_factor` 산술 **0건**",
        "**0/7 = 0.0%**", "**0/4 = 0.0%**",
        "**분모 갈래: 갈리지 않음**",
        "**post8 = 1회차 · `exact` 갈래 «미도달»**",
        "「참고 전건」",
        "| ① 그 글 «단독»(post8 주 표본 4건끼리) | **0** |",
        "그 글 열 비교가능 쌍 0(구성 · exact 4건 전부 N=1)",
        "`(갈래 이름, n, 답)`",
        "「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 4 / `approx` 포함 분모 6」",
        "🔴 **`D-3` (나)4 검사**(`PREREG_POST8.md:250`",       # 🆕 정정 1차 A-B2
        "주 갈래와 같은 쪽 **49/49** ⇒ **갈리지 않는다 — 주 판정 불변**",
        "「우리로 제외」 — **인쇄만 · 판정 효과 없음**",
        "왼쪽 열은 인용이다",
        "대체 전/후 `V`·`p` — 의무 인쇄",
        "`LAD-T1` 영구 취소",
        "분모 정의 = 「DB 있는 신규 건」 = 7건",
        "합치지 않는다",
        "새 예측을 만들지 않았다",
    ]:
        assert needle in t, needle
    rep = [ln for ln in t.splitlines()
           if re.match(r"^\| post[4-7]", ln) and "| ✅ 재현 | `RESULTS_LADDER_TRANCHE" in ln]
    assert len(rep) == 4, "post4~post7 계열 재계산 4행이 전부 인쇄값을 재현"
    assert "🔴 불일치" not in t, "재현 불일치 표시가 한 줄도 없다"


# ── P8 ───────────────────────────────────────────────────────────────────
def test_P8_numbers_consistency():
    t = _t8()
    m = re.search(r"^\*\*누적 비교가능 쌍 = (\d+)\*\*$", t, re.M)
    assert m, "찾기 쉬운 한 줄 「누적 비교가능 쌍 = <수>」"
    row = re.search(r"^\| \*\*창5 `\[D,D\+4\]` \(주\)\*\* \| (\d+) \| (\d+) \|", t, re.M)
    assert row and int(m.group(1)) == int(row.group(2)), "D-1 ② = §2 주 판정 창5 비교가능 쌍"
    assert int(m.group(1)) >= P8.PAIR_THRESHOLD
    three = re.search(r"^\| ③ 게이트 판정에 쓴 수\(= ②\) \| \*\*(\d+)\*\*", t, re.M)
    assert three and three.group(1) == m.group(1), "③ = ②"
    lines = re.findall(r"창 `\[(\S+), (\S+)\]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 (\d+) 봉 / 후 (\d+) 봉 · 혼합 빈티지", t)
    got = sorted((a, b, int(c), int(d)) for a, b, c, d in lines)
    exp = sorted((s, e, b, a) for _n, s, e, b, a in CROSS8)
    assert got == exp, "혼합 빈티지 신고 8줄 = PD-27 (바) 표"
    assert "PD-27 (바) 표(창5 걸침 3건 + 대체 창 5)와 **일치 ✅**" in t
    for g in GRADE_NAMES:
        assert g not in t, f"등급 이름 「{g}」 이 없어야 한다(§6 단계)"
    assert "****" not in t
    assert all(ln.rstrip().endswith("|") for ln in t.splitlines() if ln.startswith("| ")), "표 행이 파이프로 닫힌다"


# ── R1 · R2 ──────────────────────────────────────────────────────────────
def test_R1_post7_suite_still_passes():
    r = subprocess.run([sys.executable, "-X", "utf8", "test_post7_ladder.py", "--require-artifact"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "✅ 전건 통과" in r.stdout


def _blob_md5(rel):
    out = subprocess.run(["git", "show", f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/{rel}"],
                         cwd=BASE, capture_output=True)
    assert out.returncode == 0, rel
    return hashlib.md5(out.stdout).hexdigest()


def test_R2_upstream_untouched():
    for rel in ("run_ladder_tranche.py", "run_ladder_tranche_post6.py", "run_ladder_tranche_post7.py",
                "RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md", "RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md",
                "run_tests.py"):
        wt = hashlib.md5((BASE / rel).read_bytes()).hexdigest()
        assert wt == _blob_md5(rel), f"{rel} 가 {BASE_REF} 와 다르다 — 이 레인은 고치지 않는다"
    # 🔴 대칭 — 같은 ref 에 post8 스크립트는 «없다»(ref 가 post8 이전임을 확인 · 검사력)
    miss = subprocess.run(["git", "cat-file", "-e",
                           f"{BASE_REF}:RoboTrader_template/backtest/tasso_program_journal/run_ladder_tranche_post8.py"],
                          cwd=BASE, capture_output=True)
    assert miss.returncode != 0


def test_R3_source_hygiene():
    src = (BASE / "run_ladder_tranche_post8.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
    allow = {"__future__", "re", "statistics", "sys", "collections", "math", "pathlib", "psycopg2", "run_tests",
             "run_ladder_tranche", "run_ladder_tranche_post6", "run_ladder_tranche_post7"}
    assert not [m for m in imports if m.split(".")[0] not in allow]
    assert not re.search("adj_" r"factor\s*[\*/]|[\*/]\s*adj_" r"factor|execute\([^)]*adj_" r"factor", src), "adj_factor 산술·조회 0"
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b\s", src), "DB 쓰기 0"
    assert src.count("write_text") == 1 and "RESULTS_LADDER_TRANCHE_POST8_NUMBERS.md" in src


def main() -> int:
    import pytest
    return pytest.main([__file__, "-q", "-p", "no:cacheprovider"])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
