# -*- coding: utf-8 -*-
"""`S5` 재무·뉴스 OOS — **8번째 글** · 🟢 **이 계열 «첫 판정» 회차**(라벨 선언 있음).

동결 준거(1순위 · 값 보기 «전»에 전부 다시 읽었다):
  · `PREREG_S5_FUND_NEWS_OOS.md` v0.3 — §1(예측 한 줄 · PIT · 대조군 · 최소 n 3) · §1-1(정밀도:
    `exact` 주 · `approx` 민감도 인쇄만 · `after` 제외) · §2(판정문 3라벨 · Holm +0) · §3(승계) · §4
    (🔴 본문 0바이트 변경 — 이 스크립트는 그 파일을 읽지도 쓰지도 않는다)
  · `FREEZE_S5_2026-09-16.md`(커밋 `96beddc`) — §1 동결 대상 · §3 순서 증거 네 줄 · §6 라벨 선언
  · `PREREG_POST8.md` §12(`D-12`) · §3(`D-3`) · §5(`D-5`) · §9(`D-9`) · §0-5-1(가분성)
  · `PREDECISION_2026-09-18_post8.md` PD-1 · PD-4 · PD-11 · **PD-15** · PD-21 · PD-23 · PD-27 · **PD-30**
  · `INTAKE_2026-09-18_post8.md` §1 · §5 「S5」 행 · `LABELS_2026-09-18_post8.md`
  · 원장 커밋 `b302f7f`(post8 10행 · 37레그) — 원장엔 종목코드 열이 없다 ⇒ 코드는 INTAKE §1 표가 유일 출처
승계(원본 불변 · import 재사용): `run_s5_post7.py` — `pit_row`·`pit_miss_kind`·`control_top1`·
  `loss_rate`·`news_hits`·`assert_both_n`·`sparsity_lines`·`news_defer_lines`·`CONTAM`·상수.
  🔴 `run_s5_post7.pit_row` 는 모듈 전역 `PIT_CUTOFF` 를 읽는다 ⇒ 이 스크립트는 **메모리 안에서만**
  `pit_cutoff()` 문맥으로 절단면을 바꿨다가 되돌린다(파일은 한 바이트도 안 바꾼다 ·
  `run_selection_post7.py` 의 `P6.OUT = OUT` 관용과 같은 부류).

이번 회차의 갈림(계산 «전»에 적는다 · 값 아님):
  S5-R8-1 **판정 분모 = 신규 ∧ `exact` = 4**(우리로 · JW신약 · 액스비스 · 우리기술) · 판정 가능 예고
      **3**(액스비스 `0011A0` = `dart_financials_asfiled` 0행 · «표 미수록» · 이름 매칭 실패 «아님») ·
      민감도 판 **6**(판정 가능 예고 5 · 헥토파이낸셜·코데즈컴바인 = `approx` 「8월말」 7갈래).
  S5-R8-2 **PIT** = `status='000'` ∧ `rcept_dt <= 2026-09-18`(글 게시일) · 가장 최근 사업연도 «하나».
      ⚠️ 표는 `max(rcept_dt)` 2026-08-06 에서 멈춰 있다(PD-15) — 「형식상 통과」 한계를 박는다.
  S5-R8-3 **「우리로 제외」 3 ↔ 2 = 인쇄만**(🔒 #1-(ii) · 판정 효과 없음) · §1-5 재진입 = **항등**
      (exact 열 §1-5 재진입 0) · `none` 1(원익) + 후속 3 = 등록일 축 밖.
  S5-R8-4 🔴 **대조군 «합치기» 셈법이 동결 문언에 없다**(`RESULTS_S5_POST7.md` §10 이 「이 문서 밖의
      결정」으로 남겼고, 그 뒤 어느 동결본도 정하지 않았다). 다음 규칙을 둔다(🔴 「값 보기 «전» 고정」은 **자기보고**다 —
      증거 없음: 이 파일 수정 시각 01:04:28 > 첫 실행 00:47:07 · 네 셈법이 같은 답이라 이 주장이 판정을 떠받치지 않는다):
      셈법 네 개를 **전부** 인쇄한다 — (가) 종목-일 pooled × 전 `exact` 날짜(= post7 구현 승계 · 주 열) ·
      (나) 날짜별 비율 평균 × 전 `exact` 날짜 · (다) pooled × «판정 가능» 건의 날짜만 ·
      (라) 날짜별 평균 × «판정 가능» 건의 날짜만. **네 셈법의 라벨이 모두 같으면 그 라벨**,
      하나라도 다르면 **「판정 불가·모호」**(공통 지시 §4-11 · 새 문턱·새 라벨 0개).
  S5-R8-5 `approx` 민감도(§1-1 「두 값을 «둘 다»」) = 판정 가능 5 기준 차이 «범위»(갈래 7×7 조합) ·
      🔴 판정 언어 금지 · 라벨 문자열을 그 절에 쓰지 않는다(가드가 문다).
  S5-R8-8 🆕 정정 1차(verifier A B1) — **`D-3` (나)4 검사**(`PREREG_POST8.md:250` *「`exact` 갈래와 `approx` 포함
      갈래가 둘 다 최소 n 을 채우고 답이 갈리면 ⇒ ⛔ 판정 불가」*). 초판은 이 검사를 하지 않고 `exact` 라벨을 최종으로
      적었다. `approx` 포함 판정 가능 5 ≥ 3 · `exact` 판정 가능 3 ≥ 3 ⇒ 두 갈래 모두 최소 n 충족 ⇒ 셈법 네 개마다
      `approx` 포함 49조합의 `±10%p` 안/밖을 `exact` 갈래와 대조하고, 한 셈법이라도 «반대쪽» 조합이 있으면 갈린다.
      🔴 SEL·REG 와 같은 축 공통 규칙이다(REG `P6-M1′` 「선언 없음」과 같은 조항) — `PREREG_S5_FUND_NEWS_OOS.md:24`
      「판정 언어 금지」는 (나)2 와 같은 말이고 (나)4 를 막지 않는다. `approx` 행에는 라벨을 붙이지 않는다(원시값만).
  S5-R8-6 post7 표본은 **같은 2026-09-24 스냅샷에서 재계산**해 나란히 인쇄 · post7 행은 `—`
      (판정 없음이었음 · 소급 재판정 금지 `FREEZE_S5_2026-09-16.md` §6 · `PREREG_POST8.md` §12 (라)).
      🔴 post7+post8 합산은 만들지 않는다(판정 분모 = post8 신규 · PD-15 · 소급 금지).
  S5-R8-7 🔴 **D-9 ① 시각 줄** — 분 단위 실행 시각은 **stdout 전용**(post7 `note()` 관용 · 바이트 결정론).
      산출물에는 **실행일 + 빈티지 구간**(창 구간 `max(updated_at)` ≤ 읽은 시각 < 다음 sweep)을 박는다.
      🔴 재량 · 충돌 신고 대상(보고서) — `PREREG_POST8.md:544-545` ↔ `FREEZE_WRC_2026-09-02.md` §2
      「커밋(실행)마다 바뀌는 값을 산출물에 적으면 그 산출물은 자기 자신을 재현할 수 없게 된다」.

🔴 등급 이름은 한 개도 적지 않는다(§6 단계 · PD-16 · PD-28) — 가드가 문다.
🔴 라이브 채택 대상이 아니다(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1).
🔴 라이브 트리 import 0건 · DB `SELECT` 만 · `adj_factor` 산술 0건 · 난수 0회(결정적) · 새 정의 0개.
🔴 이 스크립트가 만드는 산출물은 `RESULTS_S5_POST8_NUMBERS.md` «하나»다 — 산문 `RESULTS_S5_POST8.md`
   는 사람이 쓴다(post7 규약 · `MANUAL_DOCS` 자리).
"""
from __future__ import annotations

import csv
import itertools
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path

import psycopg2

import run_s5_post7 as S7
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
KST = timezone(timedelta(hours=9))

# ── 이번 회차 상수 (INTAKE §1·§5 · PD-1 · PD-4 · PD-11 · PD-15 — 여기서 고르지 않는다) ─────
POST_LOG = "224416253270"
POST_DATE = "2026-09-18"        # 글 게시일(금 · 거래일) — PIT 절단면
DB_UPTO = "2026-09-18"          # PD-1 · 창 종료 = 발행 당일 봉 «포함» · 전 축
PIT_CUTOFF = POST_DATE          # §1 PIT `rcept_dt <= 글 게시일`
PIT_STATUS = S7.PIT_STATUS      # "000" (동결값 승계)
TOP_PCT = S7.TOP_PCT            # 99.0 = 상위 1% (동결값 승계)
NEWS_BACK = S7.NEWS_BACK        # 4 (탐색 인쇄 전용)
SEED = S7.SEED                  # 20260815 — 이 레인은 난수를 쓰지 않는다
MIN_JUDGEABLE = 3               # §1 *「신규 «판정 가능» 건이 3건 미만이면 판정을 미루고」*
BAND_PP = 10                    # §2 `abs(선정 − 대조군) ≤ 10%p`
PROG_VER = "1.0.42"
VINTAGE_BOUNDARY = "2026-09-14"     # KRX 연장 제도 발효일(`PREREG_POST8.md` §9)
DPLUS1_SWEEP = "2026-09-21 15:35"   # 09-18 봉의 D+1 sweep(PD-27 (마) 2)
WIN_START = "2026-07-24"            # 관리자 착수 프로브 창 시작(PD-27 (다))
# 다음 sweep 표기용 휴장일(읽기 전용 참조 · import 아님): `utils/korean_holidays.py:69-71`
#   — 2026-09-24 추석 전날 · 09-25 추석 · (09-26 토) · 09-28 은 거래일(같은 파일 :72-75 주석)
HOLIDAYS_NEAR = {"2026-09-24", "2026-09-25", "2026-09-26"}

LABEL_OK, LABEL_OUT, LABEL_HOLD = "(S5-성립)", "(S5-이탈)", "(S5-보류)"
LABELS = (LABEL_OK, LABEL_OUT, LABEL_HOLD)
AMBIG = "판정 불가·모호"
# 🔴 등급 이름 — 이 산출물에 나오면 안 되는 문자열(§6 단계 · PD-16 · PD-28)
FORBIDDEN_GRADE = ("충족·참고용", "조건 미달", "낡음(재실행 금지)")
GRADE_CODE_RE = re.compile(r"GT-[A-F]")
VERDICT_BEGIN = "<!-- S5-VERDICT-BEGIN -->"
VERDICT_END = "<!-- S5-VERDICT-END -->"

# ── 표본 (`INTAKE_2026-09-18_post8.md` §1 표 «그대로» · 항목 순서) ──────────────
EXACT4 = [
    ("우리로", "046970", "2026-09-11"),          # 항목 내 2 사이클 · 사이클 1 등록일(PD-3)
    ("JW신약", "067290", "2026-09-01"),
    ("액스비스", "0011A0", "2026-09-11"),        # news 경유 코드 해결(PD-11)
    ("우리기술", "032820", "2026-09-09"),        # ≠ 우리기술투자 041190(PD-11)
]
URIRO = "우리로"
_AUG_END = ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
            "2026-08-27", "2026-08-28", "2026-08-31"]
APPROX2 = [
    ("헥토파이낸셜", "234340", "「8월말」 = 08-21~08-31 의 거래일 7일", list(_AUG_END)),
    ("코데즈컴바인", "047770", "「8월말」 = 08-21~08-31 의 거래일 7일", list(_AUG_END)),
]
NONE1 = [("원익", "032940")]                       # 🔒 #2 · PD-4
FOLLOWUP3 = [("빛과전자", "069540"), ("로보티즈", "108490"), ("범한퓨얼셀", "382900")]  # PD-2
NO_FIN_CODES = {"0011A0"}                           # PD-15 · PD-11 — 표 미수록
PD11_RECORD = dict(rows=17892, max_rcept="2026-08-06")   # PD-11 기록(대조용 · 재계산 값이 주)


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호 · post7 관용)."""
    print(s)


def pp(fr):
    """Fraction(%) → 소수 1자리 문자열."""
    return "—" if fr is None else f"{float(fr):.1f}%"


def ppd(fr):
    return "—" if fr is None else f"{float(fr):+.1f}%p"


@contextmanager
def pit_cutoff(c):
    """`run_s5_post7.pit_row` 의 절단면을 «메모리 안에서만» 바꿨다가 되돌린다(파일 불변)."""
    old = S7.PIT_CUTOFF
    S7.PIT_CUTOFF = c
    try:
        yield
    finally:
        S7.PIT_CUTOFF = old


# ══════════════════════════════════════════════════════════════════════════════
# 판정 규칙 — §2 동결 문언 그대로 (새 문턱 0)
# ══════════════════════════════════════════════════════════════════════════════
def s5_label(sel_loss, sel_ok, ctrl_pct):
    """§2 — `(S5-보류)` 신규 판정 가능 < 3 · `(S5-성립)` `abs(차) ≤ 10%p` · `(S5-이탈)` `> 10%p`.

    🔴 경계 비교는 `Fraction` 으로 한다(부동소수 반올림이 10.0%p 경계를 흔들지 않게)."""
    if sel_ok < MIN_JUDGEABLE:
        return LABEL_HOLD
    if ctrl_pct is None:
        return None
    diff = Fraction(100 * sel_loss, sel_ok) - ctrl_pct
    return LABEL_OK if abs(diff) <= BAND_PP else LABEL_OUT


def final_label(labels):
    """S5-R8-4 — 네 셈법의 라벨이 전부 같으면 그 라벨, 하나라도 다르면 「판정 불가·모호」."""
    got = {x for x in labels}
    if None in got or len(got) != 1:
        return AMBIG
    return got.pop()


def ctrl_rate(entries, pooled):
    """대조군 비율(%) — `entries` = [(lo, ok), …] · pooled = 종목-일 합 · 아니면 날짜별 평균."""
    use = [(lo, ok) for lo, ok in entries if ok]
    if not use:
        return None
    if pooled:
        return Fraction(100 * sum(lo for lo, _ in use), sum(ok for _, ok in use))
    return sum((Fraction(100 * lo, ok) for lo, ok in use), Fraction(0)) / len(use)


# ══════════════════════════════════════════════════════════════════════════════
# 가드 — 쓰기 «전»에 스스로 문다
# ══════════════════════════════════════════════════════════════════════════════
def assert_labels_only_in_verdict(lines):
    """🔴 라벨 문자열은 «판정 절» 안에서만 — `approx`·post7·뉴스 절에 새면 판정 언어 금지 위반."""
    inside, bad = False, []
    for i, ln in enumerate(lines):
        if VERDICT_BEGIN in ln:
            inside = True
            continue
        if VERDICT_END in ln:
            inside = False
            continue
        if not inside and any(lab in ln for lab in LABELS):
            bad.append(i + 1)
    if bad:
        raise AssertionError("🔴 판정 절 밖에 S5 라벨이 있다(판정 언어 금지 위반): 줄 %s" % bad)
    return True


def assert_no_grade_names(lines):
    body = "\n".join(lines)
    hit = [g for g in FORBIDDEN_GRADE if g in body] + GRADE_CODE_RE.findall(body)
    if hit:
        raise AssertionError("🔴 등급 이름이 산출물에 들어갔다(§6 단계 · PD-16): %s" % hit)
    return True


REQUIRED_MARKERS = (
    "D-9 ①", "D-9 ②", "D-9 ③", "D-9 ④", "D-9 ⑤",
    "`approx` 포함 시 최소 n 이 차는 축:",
    "D-5 갈래",
    "주 표본 n", "민감도 판 n",
    "라이브 채택 대상이 아니다",
    "창 종료 2026-09-18 = 발행 당일(금 · 거래일) 봉 «포함»",
    "실행 시 `max(date)`",
    "Holm 가족",
    "max(rcept_dt)",
)


def assert_duties(lines):
    """🔴 공통 인쇄 의무(`PREREG_POST8.md` 가분성 §0-5-1) — 빠지면 그 축 무효 ⇒ 쓰지 않는다."""
    body = "\n".join(lines)
    miss = [m for m in REQUIRED_MARKERS if m not in body]
    if miss:
        raise AssertionError("🔴 인쇄 의무 누락: %s" % miss)
    return True


def ledger_rows(path=None):
    p = Path(path) if path else BASE / "ledger_trades.csv"
    with p.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r["post_log_no"] == POST_LOG]


def assert_ledger_matches(rows):
    """🔴 상수가 원장(`b302f7f`)과 같은가 — 이름·등록일·정밀도·프로그램 버전."""
    ex = [(r["stock_name"], r["reg_date"]) for r in rows if r["reg_date_precision"] == "exact"]
    ap = sorted(r["stock_name"] for r in rows if r["reg_date_precision"] == "approx")
    no = sorted(r["stock_name"] for r in rows if r["reg_date_precision"] == "none")
    want_no = sorted([n for n, _ in NONE1] + [n for n, _ in FOLLOWUP3])
    errs = []
    if sorted(ex) != sorted((n, d) for n, _c, d in EXACT4):
        errs.append(f"exact {ex}")
    if ap != sorted(n for n, *_ in APPROX2):
        errs.append(f"approx {ap}")
    if no != want_no:
        errs.append(f"none {no}")
    if len(rows) != 10 or {r["prog_ver"] for r in rows} != {PROG_VER}:
        errs.append(f"rows {len(rows)} · prog_ver {sorted({r['prog_ver'] for r in rows})}")
    if {r["post_date"] for r in rows} != {POST_DATE}:
        errs.append("post_date")
    if errs:
        raise AssertionError("🔴 상수 ↔ 원장 불일치: " + " · ".join(errs))
    return True


# ══════════════════════════════════════════════════════════════════════════════
# 산문 블록 — DB 없이 만들어지는 부분(시험이 직접 문다)
# ══════════════════════════════════════════════════════════════════════════════
def header_lines(run_day, max_date, max_rows, vint):
    """`vint` = dict(win_max, win_min, read_max, read_min, next_sweep, dplus1_ok)."""
    L = []
    L.append("# RESULTS_S5_POST8_NUMBERS — 기계 생성 (수정 금지)\n")
    L.append("생성 `run_s5_post8.py` · 사전등록 [`PREREG_S5_FUND_NEWS_OOS.md`](PREREG_S5_FUND_NEWS_OOS.md) v0.3 "
             "(본문 0바이트 · 동결 선언 [`FREEZE_S5_2026-09-16.md`](FREEZE_S5_2026-09-16.md) `96beddc`) · "
             "[`PREREG_POST8.md`](PREREG_POST8.md) §12(`D-12`) · "
             "인테이크 [`INTAKE_2026-09-18_post8.md`](INTAKE_2026-09-18_post8.md) §1·§5 · "
             "결정 [`PREDECISION_2026-09-18_post8.md`](PREDECISION_2026-09-18_post8.md) **PD-15 · PD-30** · "
             "원장 `b302f7f`(post8 10행 · 37레그) · 승계 `run_s5_post7.py`(import · 원본 불변)")
    L.append("")
    L.append("## §0. 실행 환경 · 동결 규약\n")
    L.append("| 항목 | 값 |")
    L.append("|---|---|")
    L.append("| 🔴 창 종료 | **창 종료 2026-09-18 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
             "전 축(`WRC-` 포함) · PD-1** |")
    L.append(f"| 🔴 실행 시 `max(date)` | **{max_date}** · 그 날짜 행수 **{max_rows:,}** — "
             "기록만(창 아님 · PD-1 8번) |")
    L.append(f"| 🔴 D-9 ① 쿼리 실행 시각(KST) | 실행일 **{run_day}** · 읽은 시각은 "
             f"**[창 구간 `max(updated_at)` {vint['win_max']}, 다음 sweep {vint['next_sweep']})** 안 — "
             "🔴 분 단위 시각은 stdout 전용(바이트 결정론 · post7 `note()` 관용 · S5-R8-7 재량) |")
    L.append(f"| 🔴 D-9 ② 창 구간 `max(daily_prices.updated_at)` | **{vint['win_max']}** "
             f"(창 구간 `[{WIN_START}, {DB_UPTO}]` · 관리자 착수 프로브와 같은 구간) · "
             f"이 축이 «실제로 읽은» 날짜 집합의 `max(updated_at)` = **{vint['read_max']}** |")
    L.append("| 🔴 D-9 ③ | **09-18 봉은 D+1(09-21) sweep 이후 읽음** |")
    L.append(f"| 🔴 D-9 ④ | 창 구간 `min(updated_at)` = **{vint['win_min']}** ≥ {DPLUS1_SWEEP}: "
             f"**{'예' if vint['dplus1_ok'] else '아니오'}** (기록 · 통과 조건 아님 · `updated_at` 은 "
             "sweep 마다 일괄 갱신 값이라 빈티지 «증거»가 아니다 — PD-27 (라)) |")
    L.append(f"| 🔴 D-9 ⑤ 혼합 빈티지 | **걸침 창 0** — 이 축의 `daily_prices` 읽기는 «날짜 한 개» 단위"
             f"(등록일 `D` · `approx` 갈래일)이고 그 날짜 전부 {VINTAGE_BOUNDARY} «전»이다 "
             f"(읽은 날짜 최대 = **{vint['read_date_max']}**) ⇒ `P8-혼합빈티지신고` 문장 대상 없음 "
             "(PD-27 (바) 표에 `S5` 행 없음) · 「정규장만」 갈래 열지 않음 · `adj_factor` 산술 0 |")
    L.append(f"| PIT 규약 | `dart_financials_asfiled` · `status = '{PIT_STATUS}'` ∧ "
             f"`rcept_dt <= {PIT_CUTOFF}`(글 게시일) · **가장 최근 사업연도 «하나»만** · "
             "🔴 실패해도 다른 해를 찾지 않는다(§1) |")
    L.append(f"| 대조군 | 같은 날 유니버스 `trading_value / market_cap` 백분위 **상위 1%**"
             f"(= `pct >= {TOP_PCT:.1f}`) — 태쏘 `f1` 축과 **같은 정의**"
             "(`run_selection.py:60` · `:82-83` · `run_s5_post7.control_top1` 그대로) |")
    L.append("| 판정 라벨 | 🟢 **선언 있음** — `FREEZE_S5_2026-09-16.md` §6(`96beddc` · fetch «앞» · PD-0) · "
             "`PREREG_S5_FUND_NEWS_OOS.md:34-36` 세 라벨 · 🟢 **이 계열 «첫 판정» 회차**(PD-15) |")
    L.append(f"| 최소 n | 신규 «판정 가능» 건 **{MIN_JUDGEABLE}** 미만이면 미룬다(§1 `:15` · §2 `:36`) |")
    L.append(f"| 시드 | **{SEED}** (계열 고정값) — 🔴 이 레인은 **난수를 쓰지 않는다**(결정적) |")
    L.append("| Holm 가족 | 🔴 **+0** — 주 검정 수를 늘리지 않는다(§2 `:37` · FREEZE §6) |")
    L.append("| 등급 | 🔴 이 산출물은 등급 이름을 **한 개도 적지 않는다**(§6 단계 · PD-16 · PD-28) |")
    L.append("| 라이브 | 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) |")
    L.append("")
    L.append("🔴 **post7 은 소급 재판정하지 않는다** — post7 의 `S5` 행은 `—`(판정 없음이었음) 그대로다"
             "(`FREEZE_S5_2026-09-16.md` §6 · `PREREG_POST8.md` §12 (라)). §7 의 post7 재계산은 **값만**이다.")
    L.append("🔴 **검정력이 없다**(§2 `:38`) — 라벨이 무엇이든 ***「재무를 본다/안 본다」의 증거가 아니다***"
             "(FREEZE §6 · 「성립」 라벨이 나와도 「재무를 안 본다」의 증거가 아니다).")
    L.append("")
    return L


def contamination_lines():
    C = S7.CONTAM
    L = []
    L.append("## §0-1. 오염 고지 — **나는 이미 봤다** (§0 승계 · 재계산 아님 · 동결 문언 옮김)\n")
    L.append("| 이미 본 값 | 수 |")
    L.append("|---|---|")
    L.append(f"| 사전등록 시점 원장 | **{C['ledger_trades']}건 / {C['ledger_legs']}레그 / "
             f"고유 {C['uniq_codes']}종목 / {C['posts']}글** |")
    L.append(f"| 영업적자(2026-09-14 패널) | **{C['seen_loss']}** (대조 유니버스 {C['seen_univ']}) |")
    L.append(f"| 뉴스 보유(등록일 창) | **{C['seen_news']}** vs 같은 날 유니버스 기준선 "
             f"**{C['seen_news_base']}** |")
    L.append(f"| 이름→코드 매칭 **상한** | **{C['name_match']}** — 미매칭 8종목은 「모른다」로 남는다 |")
    L.append("")
    L.append("⇒ 예측은 **post7 이후 «새» 신규 건에만** 걸려 있다(§0). 🔴 ***이름 매핑은 「비슷한 이름」에서 "
             "조용히 틀린다*** — 이 글에도 **「우리기술」(`032820`) ↔ 「우리기술투자」(`041190` · post6·post7 "
             "종목)** · **「원익」 LIKE 7종목**(정확히 「원익」은 `032940` 하나)이 있다(PD-11). "
             "코드는 인테이크 §1 표를 유일 출처로 쓴다.")
    L.append("")
    return L


def precision_lines(n_judge_main=None, n_judge_sens=None):
    """§1-1 — 정밀도 분포 + **주 표본 n · 민감도 판 n «둘 다»**(하나만 적으면 무효)."""
    n_main = len(EXACT4)
    n_sens = len(EXACT4) + len(APPROX2)
    jm = "—" if n_judge_main is None else str(n_judge_main)
    js = "—" if n_judge_sens is None else str(n_judge_sens)
    L = []
    L.append("## §1. `reg_date` 정밀도 분포 · 표본 n\n")
    L.append("| 정밀도 | 건 | 처리(§1-1 동결) |")
    L.append("|---|---|---|")
    L.append(f"| **`exact`** | **{len(EXACT4)}** | 🟢 **주 표본** — 판정은 이 건으로만 |")
    L.append(f"| `approx` | {len(APPROX2)} | ⚪ **민감도 인쇄만** · 🔴 판정 언어 금지 |")
    L.append(f"| `none`(신규) | {len(NONE1)} | 등록일 축 **밖**(PD-4 · 🔒 #2 원익) |")
    L.append(f"| `none`(후속) | {len(FOLLOWUP3)} | 등록일 축 **밖**(PD-2 · 이중계상 금지) |")
    L.append("| `after` | 0 | 🔴 제외(§1-1) — 이번 글엔 없다 |")
    L.append("")
    L.append(f"- **주 표본 n = {n_main}** (신규 ∧ `exact`) · 그중 **판정 가능 {jm}**")
    L.append(f"- **민감도 판 n = {n_sens}** (주 표본 + `approx` {len(APPROX2)}) · 그중 판정 가능 {js}")
    L.append("- 🔴 §1-1 *「주 표본 n · 민감도 판 n 을 «둘 다» — **하나만 적으면 무효**」* ⇒ 두 줄은 **같이** "
             "인쇄된다(`run_s5_post7.assert_both_n()` 이 쓰기 «전»에 검사한다).")
    L.append(f"- 🔴 **§1-5 재진입(등록 자체가 두 번째 사이클) = exact 열 0 ⇒ 재진입 민감도 «항등»**(4 ↔ 4). "
             f"「{URIRO} 제외」 4 ↔ 3 은 **인쇄만 · 판정 효과 없음**(🔒 #1-(ii) · PD-3 · PD-23).")
    L.append("")
    return L


def no_fin_reason(code):
    """🔴 「측정 불가」 사유를 문자로 가른다 — 액스비스는 해치텍(post7)과 사유가 «다르다»."""
    if code in NO_FIN_CODES:
        return ("🔴 **`dart_financials_asfiled` «미수록»(0행)** — «이름 매칭 실패»가 **아니다**"
                "(코드 `%s` 는 news 경유로 **해결됐다** · PD-11). 🔴 사유를 «08-06 정지»로 적지 않는다 — "
                "`news` 에 2026-03-18 자 「[액스비스] 사업보고서 (2025.12)」 제목이 있어(PD-11) 접수 시점이 "
                "정지일 «앞»일 수 있다 ⇒ **표의 수집 범위 문제**이고, 이 스크립트는 그 원인을 가르지 않는다"
                % code)
    return "측정 불가(사유는 위 표)"


def d3_line(n_exact, n_incl, j_exact, j_incl):
    """🆕 `P8-approx의존신고`(`PREREG_POST8.md` §3 (나) 3) — 한 줄 · 없으면 무효."""
    opens = "S5" if (j_incl >= MIN_JUDGEABLE > j_exact) else "없음"
    return (f"- 🔴 **D-3** — *「`approx` 포함 시 최소 n 이 차는 축: **{opens}** · `exact` 분모 "
            f"**{n_exact}**(판정 가능 {j_exact}) / `approx` 포함 분모 **{n_incl}**(판정 가능 {j_incl})」* "
            "(PD-21 구성 예고 = 「없음」 · 최소 n 은 «판정 가능» 건 기준 `:15`)")


def limits_lines(sel_in_ctrl=None):
    L = []
    L.append("## §11. 한계 (승계 · 미리 적는다)\n")
    L.append("- 🔴 **검정력이 없다** — §2 동결 문언: `n=37 · p0=0.30` 에서 `z = −0.39 · p ≈ 0.35` · 뉴스 축 "
             "**MDE 24.6%p**. ***애초에 기각도 지지도 못 한다*** — 이번 판정 가능 건은 그보다 훨씬 작다.")
    L.append(f"- 🔴 **판정 가능 건이 최소 n 경계({MIN_JUDGEABLE})에 붙어 있다** — 한 건이 선정 비율을 "
             "33%p 씩 옮긴다. 「비율」과 함께 **건별 원표**(§3)를 읽을 것.")
    L.append("- 🔴 **이름→코드 매칭 상한 83.0%** — 틀린 매핑은 플래그 «값»으로 전파된다(§0).")
    L.append("- 🔴 **액스비스의 「측정 불가」는 「적자 아님」이 아니다** — 분자·분모 어디에도 넣지 않는다.")
    L.append("- 🔴 **PIT 표가 멈춰 있다**(§2) — 「PIT 를 지켰다」와 「최신 공시를 봤다」는 다른 말이다.")
    L.append("- 🔴 **대조군 합치기 셈법이 동결 문언에 없다**(S5-R8-4) — 네 셈법을 전부 인쇄했고 "
             "하나로 고르지 않았다. 정본 셈법은 **다음 사전등록 재료**다(값을 본 뒤라 이 회차엔 소급 금지). "
             "🔴 「규칙은 값 보기 «전» 고정」은 **자기보고**다(증거 없음).")
    if sel_in_ctrl is not None:
        k, lo_x, ok_x, d_x = sel_in_ctrl
        L.append(f"- 🔴 **선정 건이 자기 날짜 대조군 안에 있다** — 그 날짜에 등록된 선정 `exact` 코드가 그날 상위 1% 에 든 "
                 f"날짜 줄 **{k}/{len(EXACT4)}**(대조군 = 선정 포함) ⇒ 차이가 **0 쪽으로 당겨진다**(보수 방향 — 「같다」 쪽으로 기운다). "
                 f"자기 날짜 선정 코드를 뺀 (가) 대조군 = {lo_x}/{ok_x} = {pp(Fraction(100 * lo_x, ok_x) if ok_x else None)} · "
                 f"차이 {ppd(d_x)} ⇒ `±10%p` {'안' if (d_x is not None and abs(d_x) <= BAND_PP) else '밖'}"
                 "(`exact` 갈래의 안/밖 불변 · 인쇄만).")
    L.append("- 🔴 **`adj_factor` 를 가격에 곱하지도 나누지도 않는다**(프로젝트 SSOT · 이 축은 가격을 쓰지 않는다).")
    L.append("- 🔴 이 분석은 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) — "
             "***라벨이 무엇이든 라이브 채택 금지는 그대로다***(§3).")
    L.append("")
    return L


def duty_misc_lines():
    L = []
    L.append("## §10. 그 밖의 `PREREG_POST8.md` 의무 — 이 축에 해당하는가\n")
    L.append("| 의무 | 이 축 |")
    L.append("|---|---|")
    L.append("| `D-1`(ANC·LAD 누적 세 수) · `D-2`(EXIT) · `D-4`(WRC) · `D-7`(LAD) · `D-11`(REG·Q1) | "
             "해당 없음 — 이 축의 항목이 아니다 |")
    L.append("| `D-6` `ddof` | 해당 없음 — 이 산출물은 `n_up` 표준편차를 인쇄하지 않는다 "
             "(SSOT = `ddof=1` · `PREREG_POST8.md` §6) |")
    L.append(f"| `D-8` `prog_ver` 수준 | 해당 없음 — 이 산출물은 `prog_ver` 를 **공변량으로 쓰지 않는다**"
             f"(PD-26 · INTAKE §5 ⚠️) · post8 10행 = `{PROG_VER}`(원장 대조 가드 통과) |")
    L.append("| `D-10` 등급 열 형식 | §6 단계(이 산출물 밖) |")
    L.append("| `D-12` `S5` 동결 절차 | 🟢 이행 완료(`96beddc` · PD-30) — 순서 증거 ④ 는 보고서·산문 참조"
             "(이 스크립트는 git 을 실행하지 않는다) |")
    L.append("")
    return L


# ══════════════════════════════════════════════════════════════════════════════
# 측정 보조 (DB)
# ══════════════════════════════════════════════════════════════════════════════
def vintage(cur, read_dates):
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices "
                "WHERE date >= %s AND date <= %s", (WIN_START, DB_UPTO))
    wmin, wmax = cur.fetchone()
    rd = sorted(set(read_dates))
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices WHERE date = ANY(%s)", (rd,))
    rmin, rmax = cur.fetchone()
    nxt = next_sweep(cur)
    return dict(win_min=str(wmin), win_max=str(wmax), read_min=str(rmin), read_max=str(rmax),
                read_date_max=max(rd), next_sweep=nxt,
                dplus1_ok=bool(wmin is not None and str(wmin) >= DPLUS1_SWEEP))


def next_sweep(cur):
    """다음 sweep 예정 = `max(date)` 다음 거래일 15:35 — 🔴 표기용(`HOLIDAYS_NEAR` 밖 임시 휴장은 모른다)."""
    cur.execute("SELECT max(date) FROM daily_prices")
    d = datetime.strptime(str(cur.fetchone()[0]), "%Y-%m-%d")
    d += timedelta(days=1)
    while d.weekday() >= 5 or d.strftime("%Y-%m-%d") in HOLIDAYS_NEAR:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d") + " 15:35 예정"


def fin_counts(cur, code, cutoff):
    cur.execute("SELECT count(*), count(*) FILTER (WHERE status = %s AND rcept_dt IS NOT NULL "
                "AND rcept_dt <= %s) FROM dart_financials_asfiled WHERE stock_code = %s",
                (PIT_STATUS, cutoff, code))
    a, b = cur.fetchone()
    return int(a), int(b)


class CtrlCache:
    """날짜별 대조군(상위 1%) 측정 캐시 — `control_top1` + `loss_rate` 는 동결 함수 그대로."""

    def __init__(self, cur):
        self.cur = cur
        self.memo = {}
        self.miss = {"no_row": set(), "null_value": set(), "unknown": set()}

    def get(self, d):
        if d not in self.memo:
            top, n_univ = S7.control_top1(self.cur, d)
            lo, ok, unk, kinds = S7.loss_rate(self.cur, top)
            for c in unk:
                self.miss[kinds.get(c) or "unknown"].add(c)
            self.memo[d] = dict(top=len(top), n_univ=n_univ, lo=lo, ok=ok, codes=list(top))
        return self.memo[d]


def select_cases(cur, cases):
    """건별 PIT — `(name, code, d, r)` · `r = run_s5_post7.pit_row` 결과(또는 None)."""
    out = []
    for nm, code, d in cases:
        out.append((nm, code, d, S7.pit_row(cur, code)))
    return out


# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:      # noqa: C901
    t0 = time.time()
    run_dt = datetime.now(KST)
    # 🔴 착수 조건(PD-27 (마) 1·2) — 달력: 09-18 봉의 D+1 sweep(09-21 15:35) «뒤»에만 돈다.
    if run_dt.strftime("%Y-%m-%d %H:%M") < DPLUS1_SWEEP:
        raise SystemExit("🔴 착수 조건 미충족 — 09-18 봉은 아직 D 빈티지다(PD-27 (마)). 계산하지 않는다.")
    lrows = ledger_rows()
    assert_ledger_matches(lrows)

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    cur.execute("SELECT max(date) FROM daily_prices")
    max_date = str(cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (max_date,))
    max_rows = int(cur.fetchone()[0])

    read_dates = [d for *_x, d in EXACT4] + [d for *_x, ds in APPROX2 for d in ds] \
        + [d for *_x, d in S7.EXACT6]
    vint = vintage(cur, read_dates)

    with pit_cutoff(PIT_CUTOFF):
        sel = select_cases(cur, EXACT4)
        apx = [(nm, code, desc, days, S7.pit_row(cur, code)) for nm, code, desc, days in APPROX2]
        fin_detail = {code: fin_counts(cur, code, PIT_CUTOFF) for _n, code, _d in EXACT4}
        fin_detail.update({code: fin_counts(cur, code, PIT_CUTOFF) for _n, code, *_x in APPROX2})
        cc = CtrlCache(cur)
        ctrl_main = [cc.get(d) for _n, _c, d in EXACT4]
        apx_ctrl = {code: [cc.get(d) for d in days] for _n, code, _desc, days, _r in apx}
        miss8 = {k: sorted(v) for k, v in cc.miss.items()}
        # 🆕 정정 1차(A-2) — 선정 코드가 자기 날짜 대조군(상위 1%)에 들어 있나 · 빼면 (가) 대조군이 어떻게 되나(인쇄만)
        #    「자기 날짜」 = 그 날짜에 등록된 선정 코드(09-11 = 우리로·액스비스) — 다른 날 등록된 선정 코드는 그 날의 정상 대조군이다.
        x_lo = x_ok = x_k = 0
        for (_n0, _c0, d_row), c in zip(EXACT4, ctrl_main):
            own = {cc_ for _n, cc_, dd in EXACT4 if dd == d_row}
            keep = [t for t in c["codes"] if t not in own]
            x_k += int(len(keep) != len(c["codes"]))
            lo_, ok_, _unk, _kinds = S7.loss_rate(cur, keep)
            x_lo += lo_
            x_ok += ok_
    with pit_cutoff(S7.POST_DATE):          # post7 재계산 — post7 의 PIT 절단면(09-12)
        sel7 = select_cases(cur, S7.EXACT6)
        cc7 = CtrlCache(cur)
        ctrl7 = [cc7.get(d) for _n, _c, d in S7.EXACT6]
    news8 = [(nm, code, d, S7.news_hits(cur, code, d)) for nm, code, d in EXACT4]
    cur.execute("SELECT count(*), max(rcept_dt), max(created_at) FROM dart_financials_asfiled")
    fin_rows, fin_max_rcept, fin_max_created = cur.fetchone()

    judge = [(nm, code, d, r) for nm, code, d, r in sel if r is not None]
    unk = [(nm, code) for nm, code, _d, r in sel if r is None]
    s_loss, s_ok = sum(1 for *_x, r in judge if r[2] < 0), len(judge)
    apx_judge = [x for x in apx if x[4] is not None]
    j_sens = s_ok + len(apx_judge)

    # ═══ §0 ~ §2 ═══════════════════════════════════════════════════════════
    for ln in header_lines(run_dt.strftime("%Y-%m-%d"), max_date, max_rows, vint):
        say(ln)
    for ln in contamination_lines():
        say(ln)
    for ln in precision_lines(s_ok, j_sens):
        say(ln)
    say("## §2. 🔴 PIT 한계 — 표가 **멈춰 있다** (PD-15 · 재측정)\n")
    say(f"- `dart_financials_asfiled` 전체 **{fin_rows:,}행** · **`max(rcept_dt)` = {fin_max_rcept}** · "
        f"`max(created_at)` = {fin_max_created} (이 실행에서 다시 읽음)")
    same = (fin_rows == PD11_RECORD["rows"] and str(fin_max_rcept) == PD11_RECORD["max_rcept"])
    say(f"- PD-11 기록({PD11_RECORD['rows']:,}행 · {PD11_RECORD['max_rcept']})과 같은가: "
        f"**{'예' if same else '아니오'}**")
    say(f"- ⇒ *「`rcept_dt <= {PIT_CUTOFF}`(글 게시일)」* 조건은 **형식상 통과**하지만 ***표 자체가 "
        f"{fin_max_rcept} 이후 접수분을 담지 않는다.*** 이 축의 「최근 사업연도」는 **표가 가진 최근 연도**다.")
    say("")

    # ═══ §3 선정 건 ═════════════════════════════════════════════════════════
    say("## §3. 선정 건 — 주 표본 `exact` 4 건별 PIT\n")
    say("| 종목 | 코드 | 등록일 | 표 전체 행 | PIT 통과 행 | 사업연도 | `rcept_dt` | `operating_income`(원) | 영업적자? |")
    say("|---|---|---|---|---|---|---|---|---|")
    for nm, code, d, r in sel:
        a, b = fin_detail[code]
        if r is None:
            say(f"| {nm} | `{code}` | {d} | {a} | {b} | — | — | — | 🔴 **측정 불가** |")
            continue
        say(f"| {nm} | `{code}` | {d} | {a} | {b} | {r[0]} | {r[1]} | {r[2]:,} | "
            f"{'🔴 **예**' if r[2] < 0 else '아니오'} |")
    say("")
    say(f"- **판정 가능 {s_ok} / {len(EXACT4)}** · 측정 불가 **{len(unk)}**"
        + (f" ({', '.join(n for n, _ in unk)})" if unk else ""))
    say(f"- **선정 건 영업적자 비율 = {s_loss}/{s_ok} = {pp(Fraction(100 * s_loss, s_ok) if s_ok else None)}**")
    for nm, code in unk:
        say(f"- {nm}(`{code}`) — {no_fin_reason(code)}")
    say("- 🔴 **측정 불가 건은 분자에도 분모에도 넣지 않는다** — 「모른다」를 「적자 아님」으로 접으면 그 건이 "
        "조용히 통과한다.")
    say("")

    # ═══ §4 대조군 ═════════════════════════════════════════════════════════
    say("## §4. 대조군 — 같은 날 `거래대금/시총` 상위 1%\n")
    say("| 건 | 등록일 | 그날 유니버스 | 상위 1% 종목 수 | 측정 가능 | 영업적자 | 적자 비율 | 선정 건 판정 가능? |")
    say("|---|---|---|---|---|---|---|---|")
    for (nm, _code, d, r), c in zip(sel, ctrl_main):
        say(f"| {nm} | {d} | {c['n_univ']:,} | {c['top']} | {c['ok']} | {c['lo']} | "
            f"{pp(Fraction(100 * c['lo'], c['ok']) if c['ok'] else None)} | "
            f"{'예' if r is not None else '🔴 아니오(측정 불가)'} |")
    say("")
    say(f"- 🔴🔴 **대조군의 「측정 불가」는 «두 종류»다**(post7 개선 1 승계) — ① PIT 행 0개 "
        f"{len(miss8['no_row'])}종목" + (f"(`{'`·`'.join(miss8['no_row'])}`)" if miss8['no_row'] else "")
        + f" · ② 행은 있는데 `operating_income` NULL {len(miss8['null_value'])}종목"
        + (f"(`{'`·`'.join(miss8['null_value'])}`)" if miss8['null_value'] else "")
        + (f" · 분류 불명 {len(miss8['unknown'])}" if miss8['unknown'] else "")
        + ". 🔴 둘 다 분자에도 분모에도 넣지 않는다(선정 건과 같은 잣대).")
    say("- 🔴 **같은 날짜가 두 줄**(09-11 = 우리로·액스비스)인 것은 그날 등록 건이 2건이기 때문이다(post7 "
        "09-03 두 줄과 같은 구성).")
    say("")

    # ═══ §5 판정 ═══════════════════════════════════════════════════════════
    say(VERDICT_BEGIN)
    say("## §5. 🟢 판정 — `S5` 첫 판정 (라벨 = `FREEZE_S5_2026-09-16.md` §6 선언 · `PREREG_S5_FUND_NEWS_OOS.md:34-36`)\n")
    say("> **S5**: *post7 이후 새 글의 «신규» 건의 **영업적자 비율**은, 그날 「거래대금/시총 상위 1%」 대조군의 "
        "적자 비율과 **±10%p 안에서 같다**.* (`PREREG_S5_FUND_NEWS_OOS.md:12` 원문)")
    say("")
    s_pct = Fraction(100 * s_loss, s_ok) if s_ok else None
    all_e = [(c["lo"], c["ok"]) for c in ctrl_main]
    jud_e = [(c["lo"], c["ok"]) for (_n, _c, _d, r), c in zip(sel, ctrl_main) if r is not None]
    variants = [
        ("(가) pooled 종목-일 × 전 `exact` 날짜 — post7 구현 승계(주 열)", all_e, True),
        ("(나) 날짜별 비율 평균 × 전 `exact` 날짜", all_e, False),
        ("(다) pooled 종목-일 × «판정 가능» 건의 날짜만", jud_e, True),
        ("(라) 날짜별 비율 평균 × «판정 가능» 건의 날짜만", jud_e, False),
    ]
    say("| 대조군 셈법(S5-R8-4) | 날짜 줄 수 | 대조군 적자 비율 | 선정 적자 비율 | 차이(선정 − 대조군) | "
        "`abs ≤ 10%p`? | 라벨 |")
    say("|---|---|---|---|---|---|---|")
    labs = []
    for name, ents, pooled in variants:
        cr = ctrl_rate(ents, pooled)
        lab = s5_label(s_loss, s_ok, cr)
        labs.append(lab)
        diff = None if (cr is None or s_pct is None) else s_pct - cr
        inb = "—" if diff is None else ("예" if abs(diff) <= BAND_PP else "아니오")
        pool_txt = (f"{sum(lo for lo, ok in ents if ok)}/{sum(ok for _lo, ok in ents if ok)} = {pp(cr)}"
                    if pooled else pp(cr))
        say(f"| {name} | {len(ents)} | {pool_txt} | {s_loss}/{s_ok} = {pp(s_pct)} | {ppd(diff)} | {inb} | "
            f"**{lab or '—'}** |")
    fin = final_label(labs)
    say("")
    say(f"- 판정 가능 **{s_ok}** ≥ {MIN_JUDGEABLE} ⇒ `(S5-보류)` 조건 " + ("**불성립**" if s_ok >= MIN_JUDGEABLE
                                                                        else "**성립**"))
    say(f"- 🔴 **규칙(S5-R8-4)**: 네 셈법의 라벨이 모두 같으면 그 라벨 · 하나라도 다르면 「{AMBIG}」 — "
        "🔴 「값 보기 «전» 고정」은 **자기보고**다(증거 없음 · 네 셈법이 같은 답이라 이 주장이 판정을 떠받치지 않는다).")
    say(f"- `exact` 갈래(주) 답 = **{fin}**" + ("" if fin != AMBIG else " — 셈법이 판정을 가른다(동결 문언이 셈법을 정하지 않았다)"))
    # ── 🆕 정정 1차(verifier A B1) — `D-3` (나)4 검사(S5-R8-8) · 셈법 네 개 × `approx` 포함 49조합 ──
    sens_loss4 = s_loss + sum(1 for x in apx_judge if x[4][2] < 0)
    sens_pct4 = Fraction(100 * sens_loss4, j_sens) if j_sens else None
    exact_in = {}
    for name, ents, pooled in variants:
        cr = ctrl_rate(ents, pooled)
        exact_in[name] = None if (cr is None or s_pct is None) else abs(s_pct - cr) <= BAND_PP
    n4_rows, split_any = [], False
    for (name, ents, pooled), base_e in zip(variants, (all_e, all_e, jud_e, jud_e)):
        ds = []
        for pick in itertools.product(*[apx_ctrl[x[1]] for x in apx_judge]):
            cr = ctrl_rate(base_e + [(c["lo"], c["ok"]) for c in pick], pooled)
            if cr is not None and sens_pct4 is not None:
                ds.append(sens_pct4 - cr)
        n_in = sum(1 for x in ds if abs(x) <= BAND_PP)
        opp = (n_in if exact_in[name] is False else len(ds) - n_in) if exact_in[name] is not None else 0
        split = bool(ds) and opp > 0
        split_any = split_any or split
        n4_rows.append((name, len(base_e) + len(apx_judge), ds, n_in, split))
    both_ok = s_ok >= MIN_JUDGEABLE and j_sens >= MIN_JUDGEABLE
    fin_final = (f"⛔ 판정 불가 — 등록일 정밀도 의존(D-3 (나)4 `PREREG_POST8.md:250`) · 기록: exact {fin}"
                 if (both_ok and split_any) else fin)
    say("")
    say(f"**🔴 `D-3` (나)4 검사**(`PREREG_POST8.md:250` · S5-R8-8) — 두 갈래 최소 n: `exact` 판정 가능 **{s_ok}** · "
        f"`approx` 포함 판정 가능 **{j_sens}** (최소 n {MIN_JUDGEABLE}) ⇒ **{'둘 다 충족' if both_ok else '한쪽 미달 — 검사 대상 아님'}** · "
        f"`approx` 포함 선정 적자 비율 = {sens_loss4}/{j_sens} = {pp(sens_pct4)}\n")
    say("| 대조군 셈법 | 날짜 줄 수(주 + `approx` 1개씩) | `approx` 포함 49조합 차이 범위 | `±10%p` 안 조합 | `exact` 갈래 | 갈리나 |")
    say("|---|---|---|---|---|---|")
    for (name, nrow, ds, n_in, split) in n4_rows:
        rng = f"{ppd(min(ds))} ~ {ppd(max(ds))}" if ds else "—"
        ex = "—" if exact_in[name] is None else ("`±10%p` 안" if exact_in[name] else "`±10%p` 밖")
        say(f"| {name.split(' — ')[0]} | {nrow} | {rng} | {n_in}/{len(ds)} | {ex} | "
            f"{'🔴 **갈린다**(반대쪽 조합 있음)' if split else '같은 쪽'} |")
    say("")
    say("- 🔴 **축 공통 규칙** — SEL·REG 와 같은 조항이다(같은 회차 REG `P6-M1′` 「선언 없음」 · "
        "`RESULTS_REGDAY_POST8_NUMBERS.md` §2) · `PREREG_S5_FUND_NEWS_OOS.md:24` 「판정 언어 금지」는 (나)2 와 같은 말이고 "
        "(나)4 를 막지 않는다 · RNK-D5(`PREREG_RANKING.md:371-373`) 「두 값이 판정을 가르면 ⇒ ⛔」와 같은 방향. "
        "🔴 초판(정정 전)은 이 검사를 하지 않고 `exact` 라벨을 최종으로 적었다 — 동결 문언이 지시하는 판정문으로 고친다.")
    say(f"- ⇒ **최종: {fin_final}**" + ("" if fin_final != AMBIG else " — 셈법이 판정을 가른다(동결 문언이 셈법을 정하지 않았다)"))
    say("- 🔴 Holm 가족 **+0** · 🔴 이 라벨은 **검정이 아니다**(§2 `:35` *「「저자가 재무를 본다」의 «관측»이지 "
        "검정이 아니다」* · `:38` 검정력 없음).")
    say("")

    # D-5 갈래 표
    say("### 5-1. 🔴 D-5 갈래 — `(갈래 이름, n, 답)` 세 쪽 (`PREREG_POST8.md` §5 (나) 2 · PD-23)\n")
    say("| 갈래 | n(표본 · 판정 가능) | 답 |")
    say("|---|---|---|")
    say(f"| 주 갈래 — 신규 ∧ `exact` · 우리로 포함 | {len(EXACT4)} · {s_ok} | **{fin}**(기록 · 최종은 위 (나)4 검사) |")
    s_no = [(nm, code, d, r) for nm, code, d, r in sel if nm != URIRO]
    s_no_ok = [x for x in s_no if x[3] is not None]
    s_no_loss = sum(1 for *_x, r in s_no_ok if r[2] < 0)
    c_no = [(c["lo"], c["ok"]) for (nm, _c, _d, _r), c in zip(sel, ctrl_main) if nm != URIRO]
    cr_no = ctrl_rate(c_no, True)
    say(f"| 「{URIRO} 제외」(🔒 #1-(ii) · **인쇄만 · 판정 효과 없음**) | {len(s_no)} · {len(s_no_ok)} | "
        f"판정 가능 {len(s_no_ok)} < {MIN_JUDGEABLE} ⇒ 답 없음(최소 n 미달) · 값만: 선정 "
        f"{s_no_loss}/{len(s_no_ok)} = {pp(Fraction(100 * s_no_loss, len(s_no_ok)) if s_no_ok else None)} · "
        f"대조군(가) {pp(cr_no)} |")
    say(f"| §1-5 재진입 포함 ↔ 제외 | {len(EXACT4)} ↔ {len(EXACT4)} | **항등** — exact 열 §1-5 재진입 0 "
        "(우리로 = 항목 내 2 사이클 · 측정 등록 = 첫 사이클 · `P6-PRIOR_CYCLE_IN_WINDOW` 0) |")
    say(f"| `approx` 포함(민감도 판 · 49조합) | {len(EXACT4) + len(APPROX2)} · {j_sens} | "
        "`±10%p` 안 조합 " + " · ".join(f"{nm.split(' ')[0]} {n_in}/{len(ds)}" for nm, _r, ds, n_in, _s in n4_rows)
        + " — `exact` 갈래(네 셈법 전부 `±10%p` 밖)와 "
        + ("🔴 **갈린다** ⇒ `D-3` (나)4" if split_any else "같은 쪽")
        + "(판정 언어 없음 · §1-1) · 값은 §6 |")
    say("| 대조군 셈법 (가)·(나)·(다)·(라) | 위 표 | 위 표의 라벨 열 그대로 |")
    say("| 창 절단 포함 ↔ 제외 | — | **항등** — 이 축은 창을 쓰지 않는다(날짜 한 개 단위) |")
    say("")
    say(d3_line(len(EXACT4), len(EXACT4) + len(APPROX2), s_ok, j_sens))
    say("")
    say(VERDICT_END)
    say("")

    # ═══ §6 approx 민감도 ═══════════════════════════════════════════════════
    say("## §6. `approx` 2건 — **민감도 인쇄만** · 🔴 판정 언어 금지(§1-1)\n")
    say("| 종목 | 코드 | 창 서술 | 갈래 수 | 표 전체 행 | PIT 통과 행 | 사업연도 | 영업적자? | 대조군 적자 비율(갈래 범위) |")
    say("|---|---|---|---|---|---|---|---|---|")
    for nm, code, desc, days, r in apx:
        rates = [Fraction(100 * c["lo"], c["ok"]) for c in apx_ctrl[code] if c["ok"]]
        rng = f"{pp(min(rates))}~{pp(max(rates))}" if rates else "—"
        a, b = fin_detail[code]
        neg = "🔴 측정 불가" if r is None else ("🔴 **예**" if r[2] < 0 else "아니오")
        say(f"| {nm} | `{code}` | {desc} | {len(days)} | {a} | {b} | {r[0] if r else '—'} | {neg} | {rng} |")
    say("")
    # 민감도 판 «두 값» — 판정 가능 5 · 대조군 = 주 날짜 4줄 + 갈래 1개씩(7×7 조합)
    sens_loss = s_loss + sum(1 for x in apx_judge if x[4][2] < 0)
    combos = []
    for pick in itertools.product(*[apx_ctrl[x[1]] for x in apx_judge]):
        ents = all_e + [(c["lo"], c["ok"]) for c in pick]
        cr = ctrl_rate(ents, True)
        if cr is not None and j_sens:
            combos.append(Fraction(100 * sens_loss, j_sens) - cr)
    say(f"- **민감도 판(주 표본 + `approx`) 선정 적자 비율 = {sens_loss}/{j_sens} = "
        f"{pp(Fraction(100 * sens_loss, j_sens) if j_sens else None)}** · 대조군 = (가) 셈법 × 주 날짜 "
        f"{len(all_e)}줄 + `approx` 건마다 갈래 1개(조합 **{len(combos)}**개)")
    if combos:
        say(f"- 차이(선정 − 대조군) **범위 = {ppd(min(combos))} ~ {ppd(max(combos))}** · "
            f"`±{BAND_PP}%p` 안 조합 {sum(1 for x in combos if abs(x) <= BAND_PP)}/{len(combos)}")
    say("- 🔴 §1-1 *「`approx` … **판정 언어 금지**」* ⇒ 위 값에 라벨을 붙이지 않는다 · 갈래별 값을 한 수로 "
        "합치지 않는다(범위로만). 🔴 단 두 갈래가 모두 최소 n 을 채우고 `±10%p` 안/밖이 갈리면 `D-3` (나)4 가 "
        "판정을 닫는다(§5 (나)4 검사 · 정정 1차 — 초판의 「판정에 쓰지 않는다」는 (나)4 를 빠뜨린 문장이었다).")
    say("- ⚠️ 헥토 「한번 더」 ∧ 「8월말」 — 직전 등록 08-28 보다 이른 **5갈래(08-21~08-27)는 저자 문장과 논리적 "
        "모순 갈래**다(PD-3 · 창 규약은 좁히지 않는다 · 표시만).")
    say("")

    # ═══ §7 post7 재계산 ═══════════════════════════════════════════════════
    judge7 = [x for x in sel7 if x[3] is not None]
    l7 = sum(1 for *_x, r in judge7 if r[2] < 0)
    e7 = [(c["lo"], c["ok"]) for c in ctrl7]
    cr7 = ctrl_rate(e7, True)
    s7p = Fraction(100 * l7, len(judge7)) if judge7 else None
    say("## §7. post7 표본 — **같은 2026-09-24 스냅샷에서 재계산** · 값만 (post7 행 = `—` · 판정 없음이었음)\n")
    say(f"- PIT 절단면 = post7 게시일 **{S7.POST_DATE}** · 표본 = `run_s5_post7.EXACT6`(주 표본 {len(S7.EXACT6)})")
    say("")
    say("| 종목 | 코드 | 등록일 | 사업연도 | `rcept_dt` | `operating_income`(원) | 영업적자? |")
    say("|---|---|---|---|---|---|---|")
    for nm, code, d, r in sel7:
        if r is None:
            say(f"| {nm} | `{code}` | {d} | — | — | — | 🔴 측정 불가 |")
        else:
            say(f"| {nm} | `{code}` | {d} | {r[0]} | {r[1]} | {r[2]:,} | {'🔴 예' if r[2] < 0 else '아니오'} |")
    say("")
    say("| 글 | 주 표본 n · 판정 가능 | 선정 적자 비율 | 대조군 (가) pooled | 차이 | 라벨 |")
    say("|---|---|---|---|---|---|")
    say(f"| post7(재계산) | {len(S7.EXACT6)} · {len(judge7)} | {l7}/{len(judge7)} = {pp(s7p)} | "
        f"{sum(lo for lo, ok in e7 if ok)}/{sum(ok for _l, ok in e7 if ok)} = {pp(cr7)} | "
        f"{ppd(None if (s7p is None or cr7 is None) else s7p - cr7)} | **—**(판정 없음 · 소급 금지) |")
    say(f"| post8 | {len(EXACT4)} · {s_ok} | {s_loss}/{s_ok} = {pp(s_pct)} | {pp(ctrl_rate(all_e, True))} | "
        f"{ppd(None if s_pct is None or ctrl_rate(all_e, True) is None else s_pct - ctrl_rate(all_e, True))} | "
        "§5 참조 |")
    say("")
    say("- 🔴 **post7+post8 합산은 만들지 않는다** — 판정 분모는 post8 신규 건이고(PD-15), 합산은 post7 을 "
        "판정에 끌어들이는 소급이다(`FREEZE_S5_2026-09-16.md` §6).")
    say("")

    # ═══ §8 뉴스 [탐색] ═══════════════════════════════════════════════════════
    for ln in S7.news_defer_lines():
        say(ln.replace("## §5.", "## §8."))
    say(f"| 종목 | 코드 | 등록일 | 창 `[D−{NEWS_BACK}, D]` 뉴스 건수 |")
    say("|---|---|---|---|")
    for nm, code, d, k in news8:
        say(f"| {nm} | `{code}` | {d} | {k} |")
    say("")
    say("- 🔬 **탐색 표기 · 판정 아님 · τ 라벨 없음**(§3) · 요약통계 없음.")
    say("")

    for ln in S7.sparsity_lines():
        say(ln.replace("## §6.", "## §9."))
    for ln in duty_misc_lines():
        say(ln)
    _xs = None if not (x_ok and s_ok) else Fraction(100 * s_loss, s_ok) - Fraction(100 * x_lo, x_ok)
    for ln in limits_lines((x_k, x_lo, x_ok, _xs)):
        say(ln)

    # ── 🔴 쓰기 «전» 자기 가드 ────────────────────────────────────────────────
    S7.assert_both_n(OUT)
    assert_labels_only_in_verdict(OUT)
    assert_no_grade_names(OUT)
    assert_duties(OUT)

    (BASE / "RESULTS_S5_POST8_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    note("")
    note(f"[D-9 ①] 쿼리 실행 시각(KST) = {run_dt.strftime('%Y-%m-%d %H:%M:%S')} · "
         f"창 구간 max(updated_at) = {vint['win_max']} · min = {vint['win_min']}")
    note("[guard] assert_both_n ✅ · assert_labels_only_in_verdict ✅ · assert_no_grade_names ✅ · "
         "assert_duties ✅ · assert_ledger_matches ✅")
    note(f"[written] RESULTS_S5_POST8_NUMBERS.md · 런타임 {time.time() - t0:.3f}s")
    note("🔴 산문 `RESULTS_S5_POST8.md` 는 «사람이» 쓴다 — 이 스크립트는 만들지 않는다.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
