# -*- coding: utf-8 -*-
"""`PREREG_SELECTION.md` §7 + `PREREG_POST6.md` §2-1 실행 — 8번째 글 (out-of-sample, 5회차).

`run_selection_post7.py` 를 **승계**한다(원본은 손대지 않는다). 특징 정의·백분위 통계량은
`run_selection.py` 의 `build_features` 를, 창 통계량·`s1_row`·`aggs`·`feat_table`·`fmt`·`med` 는
`run_selection_post6.py` 를, 유니버스 조회(`load_universe_day`·`universe_raw_count`)·`win20_bars`·
`pct`·`snapshot_tail` 은 `run_selection_post7.py` 를 **import 해 그대로 재사용**한다(새 코드 0줄 원칙).
새로 적은 것은 ① post8 상수 ② `DB_UPTO` 가 박힌 로더 3개(post7 판은 09-11 이 박혀 있어 못 쓴다 —
post7 이 post6 로더를 다시 적은 것과 같은 이유) ③ `PREREG_POST8.md` 인쇄 의무(D-3·D-5·D-6·D-9) 뿐이다.

동결 준거(값을 보기 «전»에 고정 · 1순위 출처):
  · `PREREG_SELECTION.md` §7          — `SEL-S1`~`SEL-S4` 문언·문턱 · 「3건 미만이면 미룬다」(`:111`)
  · `PREREG_POST6.md` §2-1            — `SEL-S1` 기각 유지(부활 경로 없음) · `P6-S1h`(단조 완화 축)
                                        · `P6-S1h-N`(`n_up` 중앙 >= 30 ⇒ 인용 금지 강등)
  · `PREREG_POST6.md` §4 #1~#6·#11 · §1-4(창 규약) · §1-5(재진입) · §1-6(절단 가드)
                                        · §5-1(C-17 `f9` NaN 보존) · §5-2(C-18 유니버스 5열 · 1% 가드)
  · `PREREG_POST8.md`(동결 `04cd785` · 머지 `729f28b`) — 🆕 첫 구속 회차:
        §0-1(라이브 아님) · §0-5-1(가분성) · §3 `D-3`(`P8-approx의존신고`) · §5 `D-5`(`P8-갈래계수`)
        · §6 `D-6`(`ddof=1` SSOT) · §8 `D-8` · §9 `D-9`(`P8-빈티지` · `P8-혼합빈티지신고`)
  · `PREDECISION_2026-09-18_post8.md` — PD-1(창 종료 **2026-09-18** · 발행 당일 봉 포함) · PD-2(후속 3 축 밖)
        · PD-3(재진입 · 항목 내 2 사이클 · 🔒 #1-(ii) 「우리로 제외」 인쇄만) · PD-4(정밀도 · 🔒 #2 원익 `none`)
        · PD-11(코드 · 커버리지) · PD-12(창 봉수 · C-17 대상 0 예고) · PD-21 · PD-23 · PD-24 · PD-27 (마)(바)
  · `INTAKE_2026-09-18_post8.md` §1 · §5(판정 대상 목록 · ⚠️ 공통 의무)

🔴 이번 회차에 갈리는 것(구성 · 값 아님):
   · 판정 분모 = 신규 ∧ `exact` = **4**(우리로 · JW신약 · 액스비스 · 우리기술) · `approx` 2(헥토 · 코데즈
     「8월말」 = 창 규약 08-21~08-31 거래일 7일) = 의무 민감도 · `none` 1(원익) + 후속 3 = 등록일 축 밖.
   · §1-5 재진입(등록 자체가 같은 종목의 두 번째 사이클) = exact 안 **0** ⇒ 재진입 민감도 **항등**(명시 인쇄).
   · 우리로 = 한 항목 안 두 사이클(측정 등록 09-11 = 사이클 1 · `P6-PRIOR_CYCLE_IN_WINDOW` 0) ⇒ 포함 ·
     「우리로 제외」 4 ↔ 3 은 **인쇄만 · 판정 효과 없음**(🔒 #1-(ii)).
   · 창 절단 0 ⇒ 절단 민감도 **항등**(명시 인쇄).
🔴 DB 스냅샷이 post7(09-11 창 · 09-15 실행)과 다르다(09-23 sweep 이 전 표 `updated_at` 을 다시 썼다).
   post4~post7 표본도 **같은 스냅샷에서 재계산**해 나란히 인쇄한다. 직전 문서 숫자를 옮겨 비교하지 않는다.
🔴 산출물(`_NUMBERS.md`)에 «실행 시각»을 박지 않는다(post7 관용 · `RESULTS_REGDAY_POST7.md:8`) —
   D-9 ① 쿼리 실행 시각은 **stdout 에만** 찍고 산문 §0 이 옮겨 적는다. 산출물에는 그 시각에 대한
   **결정적 기계 검사 결과**(실행 시각 > D+1 sweep · > 창 구간 `max(updated_at)`)만 남긴다 ⇒ 재실행 byte 동일.
🔴 값 보고 규칙을 바꾸지 않는다. 문언이 모호하면 **양쪽을 인쇄하고 「판정 불가·모호」**로 적는다.
🔴 이 스크립트는 결과 문서 안에서 새 예측을 만들지 않는다(`PREREG_POST6.md` §7-B #11).
🔴 등급(`PREREG_GRADE_TIERS.md`) 이름은 한 개도 적지 않는다(§6 단계 · PD-16 · PD-28).

라이브 트리 import 0건 (pandas / numpy / psycopg2 + 같은 폴더 모듈). DB 는 SELECT 만.
`adj_factor` 를 곱하지도 나누지도 않는다. 라이브 채택 대상이 아니다.
"""
from __future__ import annotations

import datetime as dt
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

import run_selection
from run_selection import FEATS, PSEUDO, build_features
# 🔴 새 코드 0줄 — post6·post7 판의 통계량·표 포맷·조회를 **그대로** 재사용한다(원본 불변).
import run_selection_post6 as P6
from run_selection_post6 import (aggs, feat_table, fmt, med, s1_row, stat_cal,  # noqa: F401
                                 stat_tdays)
import run_selection_post7 as P7
from run_selection_post7 import (load_universe_day, pct, snapshot_tail,
                                 universe_raw_count, win20_bars)
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
OUT_NAME = "RESULTS_SELECTION_POST8_NUMBERS.md"

POST8_LOG_NO = "224416253270"   # INTAKE 머리 · PD-11
POST8_POST_DATE = "2026-09-18"  # 발행 2026-09-18(금) 17:25:39 KST — 거래일
PROG_VER = "1.0.42"             # PD-8 (이 레인은 공변량으로 쓰지 않는다 · D-8 해당 없음)
DB_UPTO = "2026-09-18"          # PD-1: 창 종료 = 발행 당일 봉 «포함» · 전 축(WRC- 포함)
DB_UPTO_CUT = "2026-09-11"      # PD-27 (마) 4 대조용 절단 적재(09-18 봉 영향 확인) — 판정에 쓰지 않는다
UNIV_LO = "2026-04-01"          # 유니버스 창 하한(post4~7 승계)
RAW_LO = "2026-01-01"
W_TDAYS = 5                     # 동결 문언 [D-4, D] = 거래일 5일 (판정 창)
W_CAL_POST4 = 10                # post4 구현 (달력 10일 · 대조 창)
WIN20 = 20                      # `P6-절단가드-A` 의 창 [D-19, D] = D 포함 20거래일
SEED = 20260815                 # 계열 고정 시드 (`run_selection.RNG`)
UP15 = 1.15                     # `n_up` 정의: 등록일 고가 >= 전일 종가 x 1.15
N_DEGRADE = 30                  # `P6-S1h-N` 강등 문턱 (`PREREG_D1_OOS.md` §4 N2 인용)
DROP_GUARD = 0.01               # §5-2 `drop_rate` 가드 1%
TRUNC_GUARD = 1.0 / 3.0         # `P6-절단가드-A` 문턱 (§1-6 3 · `REC-Y3` 차용 고지)
MIN_N = 3                       # 계열 최소 n (`PREREG_SELECTION.md:111` · `PREREG_POST6.md` §4)
REGIME = "2026-09-14"           # KRX 연장 제도 경계(`PREREG_POST8.md` §9)
SWEEP_D1 = "2026-09-21 15:35:00"  # 09-18 봉의 D+1 sweep (PD-27 (마) 2)
PROBE_WIN = ("2026-07-24", "2026-09-18")  # PD-27 (다) 창 시작 07-24 ~ 창 종료
# 관리자 착수 조건 실측(공통 지시문 §3 · 보관 `probes_precalc_0924/`) — 옮겨 적은 사실(대조용 · 계산값 아님)
MGR = dict(run="2026-09-24 00:07:44 KST", rows_0918=2764,
           max_upd="2026-09-23 15:46:25.855518", min_upd="2026-09-23 15:45:10.623955",
           max_date="2026-09-23", rows_max=2764)

# ── 8번째 글 신규 7건 (INTAKE_2026-09-18_post8 §1 표 그대로 · 원장 `b302f7f`) ─────────────
#    (종목, 코드, 등록일, 정밀도, 표시)
#    🔁 후속 3건(빛과전자 post7#11 · 로보티즈 post7#9 · 범한퓨얼셀 post7#13)은 **등록일 축 밖**(PD-2 2번).
NEW8 = [
    ("우리로", "046970", "2026-09-11", "exact", "항목 내 2 사이클(측정 등록 = 사이클 1)"),
    ("원익", "032940", None, "none", "재진입(2번째 · 직전 post6 #8 08-31)"),
    ("JW신약", "067290", "2026-09-01", "exact", ""),
    ("헥토파이낸셜", "234340", None, "approx", "재진입(2번째 · 직전 post6 #4 08-28)"),
    ("액스비스", "0011A0", "2026-09-11", "exact", ""),
    ("코데즈컴바인", "047770", None, "approx", "재진입(3번째 사이클 · 직전 post5 #3 08-21)"),
    ("우리기술", "032820", "2026-09-09", "exact", ""),
]
FOLLOW8 = [("빛과전자", "069540", "post7 #11 · 09-08 재명시"),
           ("로보티즈", "108490", "post7 #9 · 09-04 재명시"),
           ("범한퓨얼셀", "382900", "post7 #13 · 09-09 재명시")]
EXACT8 = [(nm, c, d, tag) for nm, c, d, p, tag in NEW8 if p == "exact"]
APPROX8 = [(nm, c, tag) for nm, c, d, p, tag in NEW8 if p == "approx"]
NONE8 = [nm for nm, c, d, p, tag in NEW8 if p == "none"]
URIRO = "우리로"                 # 🔒 #1-(ii): 「우리로 제외」 = 인쇄만 · 판정 효과 없음
REENTRY_EXACT: set = set()      # §1-5 재진입(등록 자체가 두 번째 사이클) — exact 안 **0** (PD-3 · INTAKE §5)

# `PREREG_POST6.md` §1-4 창 규약 — 「8월말」 = 「8월 말」 = 08-21~08-31 의 모든 거래일 7일(PD-4 2번 · 달력 실측).
AUG_END = ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
           "2026-08-27", "2026-08-28", "2026-08-31"]
APPROX_BRANCHES = {
    "헥토파이낸셜": ("「8월 말」(원문 「8월말」)", "2026-08-21", "2026-08-31", AUG_END),
    "코데즈컴바인": ("「8월 말」(원문 「8월말」)", "2026-08-21", "2026-08-31", AUG_END),
}
# PD-3 — 헥토 「한번 더」 ∧ 「8월 말」: 직전 등록 08-28 보다 이른 5갈래는 저자 문장과 논리 모순(표시만 · 창을 좁히지 않는다).
CONTRA = {"헥토파이낸셜": {"2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27"}}
# PD-3 — 직전 사이클 등록일(원장 실측) · `P6-PRIOR_CYCLE_IN_WINDOW` 갈래별 값(PD-3 표가 «계산 전»에 못박은 값 — 대조용)
PREV_CYCLE = {"헥토파이낸셜": ["2026-08-28"], "코데즈컴바인": ["2026-08-21", "2026-08-19"]}
PD3_FLAG_BR = {"헥토파이낸셜": {d: (1 if d in ("2026-08-28", "2026-08-31") else 0) for d in AUG_END},
               "코데즈컴바인": {d: 1 for d in AUG_END}}
PD3_FLAG_EXACT = {"우리로": 0, "JW신약": 0, "액스비스": 0, "우리기술": 0}

# 과거 신규 건 — 같은 09-24 스냅샷 재계산용 (각 판 `NEW*` 와 같은 표 · post7 은 `exact` 6)
NEW7 = [("서산", "079650", "2026-09-03"), ("강동씨엔앨", "198440", "2026-09-03"),
        ("로보티즈", "108490", "2026-09-04"), ("해치텍", "0155E0", "2026-09-07"),
        ("빛과전자", "069540", "2026-09-08"), ("범한퓨얼셀", "382900", "2026-09-09")]
NEW6 = list(P7.NEW6)
NEW5 = list(P7.NEW5)
NEW4 = list(P7.NEW4)

# 직전 문서가 **발표한** 집계 (문서에서 옮겨 적은 상수 · 재계산 아님 · 대조용).
PUB = {  # (S1 hits, S1 n, S2, S3, S4)
    "post4_cal10": (3, 6, 99.7, 48.0, 64.2),    # RESULTS_SELECTION_POST4_NUMBERS.md (08-21)
    "post4_td5": (3, 6, 99.7, 47.5, 64.2),      # RESULTS_SELECTION_POST5.md §4-1 (08-28)
    "post5_td5": (2, 6, 99.5, 47.9, 66.1),      # RESULTS_SELECTION_POST5.md §0 (08-28)
    "post6_td5": (7, 10, 99.7, 47.6, 78.9),     # RESULTS_SELECTION_POST6_NUMBERS.md §5 (09-04)
    "post7_td5": (4, 6, 99.6, 47.0, 64.5),      # RESULTS_SELECTION_POST7_NUMBERS.md §2·§5 (09-15 실행 · 09-11 창)
}
PUB_33 = ("6/7 = 85.7%", "99.4", "48.3", "61.6")       # 1~3번째 글 33건 열 (🔴 또 다른 창)
PUB_H = {"post4": (6, 6), "post5": (4, 6), "post6": (8, 10), "post7": (5, 6)}   # 고가 변량(post4·5 = 소급 탐색)
S1_CUM_PRIOR = (22, 35)          # RESULTS_SELECTION_POST7_NUMBERS.md §2-1 (33건 열 6/7 포함 · 승계 셈법)
H_CUM_PRIOR = (13, 16)           # `P6-S1h` 판정 누적 = post6 8/10 + post7 5/6 (post4·5 소급은 넣지 않는다)
NUP_SERIES = [("post5", "87", "[47, 93]", "—"), ("post6", "65.5", "[47, 86]", "12.36"),
              ("post7", "59.0", "[55, 74]", "7.09")]     # 각 판 발표값 · sd 는 ddof=1(INTAKE_2026-09-15_post7.md:318)
STOCK_INFO_SNAP = ("2,115행", "2026-02-10 10:33:05")  # PD-11 옮겨 적은 존재 사실


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호 · post7 관용)."""
    print(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


# ── 로더 (post7 승계 · 상단만 09-18 로 넓힌다 — post7 판은 상수 09-11 이 박혀 있다) ─────
def load_ext(upto=DB_UPTO):
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, high, low, close, trading_value, market_cap "
        f"FROM daily_prices WHERE date BETWEEN '{UNIV_LO}' AND '{upto}' "
        "AND market_cap IS NOT NULL AND market_cap > 0 AND close > 0", conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def load_raw_close():
    """S1·`P6-S1h` 용 원시 종가·고가 (market_cap 필터 없이)."""
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, high, close FROM daily_prices "
        f"WHERE date BETWEEN '{RAW_LO}' AND '{DB_UPTO}' AND close > 0", conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def market_days(cur):
    """시장 거래일 달력 (의사티커 제외 · 봉이 하나라도 있는 날)."""
    cur.execute(
        "SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s "
        "AND NOT (stock_code = ANY(%s)) ORDER BY date",
        (RAW_LO, DB_UPTO, list(PSEUDO)))
    return [r[0] for r in cur.fetchall()]


def vintage(cur, lo, hi):
    """D-9 ①②④ — (쿼리 시각[세션 KST · naive], 창 구간 max(updated_at), min(updated_at), 행수)."""
    cur.execute("SELECT now()::timestamp, max(updated_at), min(updated_at), count(*) "
                "FROM daily_prices WHERE date BETWEEN %s AND %s", (lo, hi))
    return cur.fetchone()


def own_split(raw, code, d, n):
    """그 종목 봉으로 센 창(끝 = D · D 포함 n 봉)의 (시작, 끝, 경계 전 봉수, 경계 후 봉수)."""
    m = raw[(raw.stock_code == code) & (raw.date <= pd.Timestamp(d))].tail(n)
    if m.empty:
        return None
    b = pd.Timestamp(REGIME)
    return (str(m.date.min().date()), str(m.date.max().date()),
            int((m.date < b).sum()), int((m.date >= b).sum()))


def prior_flag(raw, code, d, prevs):
    """`P6-PRIOR_CYCLE_IN_WINDOW` — 그 종목 봉 `[D-19, D]` 안에 직전 사이클 등록일이 있으면 1."""
    m = raw[(raw.stock_code == code) & (raw.date <= pd.Timestamp(d))].tail(WIN20)
    ds = set(str(x.date()) for x in m.date)
    return int(any(p in ds for p in prevs))


def mixed_line(lo, hi, nb, na):
    """`P8-혼합빈티지신고` 의무 문장(`PREREG_POST8.md` §9 (나)3 형식 그대로)."""
    return (f"창 `[{lo}, {hi}]` 은 제도 경계 2026-09-14 를 걸친다 — "
            f"경계 전 {nb} 봉 / 후 {na} 봉 · 혼합 빈티지")


def main():
    prev_out = P6.OUT
    P6.OUT = OUT          # `feat_table` 은 post6 모듈의 `say` 로 쓴다 ⇒ 버퍼를 이 실행으로 잇는다(원본 불변)
    try:
        return _main()
    finally:
        P6.OUT = prev_out


def _main():  # noqa: C901
    t0 = time.time()

    src = (BASE / "run_selection.py").read_text(encoding="utf-8")
    c17_line = next((i + 1 for i, ln in enumerate(src.splitlines())
                     if "where(prev_max.notna())" in ln), None)
    c17_ok = c17_line is not None
    c17_src = src.splitlines()[c17_line - 1].strip() if c17_ok else "(없음)"

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    # D-9 ①②④ — 가격을 읽기 «직전»에 읽은 시각·창 구간 갱신 시각을 박는다.
    v_probe = vintage(cur, *PROBE_WIN)
    v_lane = vintage(cur, RAW_LO, DB_UPTO)
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (DB_UPTO,))
    rows_upto = int(cur.fetchone()[0])
    snap_max, snap_rows = snapshot_tail(cur)
    note(f"[D-9 ①] 쿼리 실행 시각(KST · DB now()) = {v_probe[0]}")

    df = build_features(load_ext())
    raw = load_raw_close()
    mdays = market_days(cur)

    sweep = dt.datetime.fromisoformat(SWEEP_D1)
    run_after_sweep = v_probe[0] > sweep
    run_after_maxupd = v_probe[0] > v_probe[1] and v_lane[0] > v_lane[1]
    min_ok = v_probe[2] >= sweep
    min_ok_lane = v_lane[2] >= sweep

    say("# RESULTS_SELECTION_POST8_NUMBERS — 기계 생성 (수정 금지)\n")
    say("사전등록 `PREREG_SELECTION.md` §7(`9e53825`, 8/15 동결) + `PREREG_POST6.md` §2-1·§4 #1~#6·#11 + "
        "🆕 `PREREG_POST8.md`(동결 `04cd785` · 첫 구속 회차) · 생성 `run_selection_post8.py` "
        "(`run_selection_post7.py` 승계 · 원본 불변)")
    say("계산 «전» 동결 = [`PREDECISION_2026-09-18_post8.md`](PREDECISION_2026-09-18_post8.md) · "
        "[`INTAKE_2026-09-18_post8.md`](INTAKE_2026-09-18_post8.md) · "
        "[`LABELS_2026-09-18_post8.md`](LABELS_2026-09-18_post8.md) · 원장 `b302f7f`(post8 10행/37레그)")
    say("")
    say("## §0. 실행 환경 · 동결 규약 (값을 보기 «전»에 고정)\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| DB | `kis_template.daily_prices` — **SELECT 만** |")
    say(f"| 유니버스 창 | {UNIV_LO} ~ **{DB_UPTO}** (`market_cap > 0` ∧ `close > 0` ∧ 의사티커 제외) |")
    say(f"| 유니버스 | **{df.stock_code.nunique():,}종목** · **{df.date.nunique()}거래일** "
        f"· 최신 봉 **{df.date.max().date()}** |")
    say(f"| 🔴 창 종료 | **창 종료 {DB_UPTO} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
        "전 축(`WRC-` 포함) · PD-1** |")
    say(f"| 🔴 실행 시 스냅샷(기록만) | **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 {snap_rows:,} — "
        f"기록만(창 아님)** (PD-1 8번) · 창 종료일 {DB_UPTO} 행수 **{rows_upto:,}** |")
    say(f"| 판정 창 | 동결 문언 `[D-4, D]` = **거래일 {W_TDAYS}일** (`PREREG_SELECTION.md` §2) |")
    say(f"| 대조 창 | post4 구현 `달력 {W_CAL_POST4}일` — **판정에 쓰지 않는다** |")
    say(f"| 🔴 판정 분모 | **신규 ∧ `exact` = {len(EXACT8)}건** ({' · '.join(r[0] for r in EXACT8)} · PD-4 1번 · "
        "`RNK-D5` · `PREREG_ANCHOR_REDESIGN.md` §2-3 · `PREREG_S5_FUND_NEWS_OOS.md` §1-1) |")
    say(f"| 민감도 분모 | `approx` **{len(APPROX8)}건**({' · '.join(r[0] for r in APPROX8)} · 갈래별 인쇄 · §5-3) · "
        f"「신규 {len(NEW8)}」 갈래 병기(측정 가능 {len(EXACT8) + len(APPROX8)} = `exact` {len(EXACT8)} + "
        f"`approx` {len(APPROX8)} · `none` 은 등록일이 없어 잴 수 없다) |")
    say(f"| 축 밖 | `none` **{len(NONE8)}건**({' · '.join(NONE8)} · 🔒 #2) + 후속 **{len(FOLLOW8)}건**"
        f"({' · '.join(r[0] for r in FOLLOW8)} — PD-2) |")
    say(f"| 시드 | **{SEED}** (`run_selection.RNG` 계열 고정값) |")
    say(f"| NREP | **{run_selection.NREP:,}** = `run_selection.py` 상수 그대로 — "
        "🔴 **이 스크립트는 귀무를 «돌리지 않는다»**(post5~post7 승계) |")
    say(f"| C-17 반영 | {'✅' if c17_ok else '🔴 **미반영 ⇒ 산출물 무효**'} "
        f"`run_selection.py:{c17_line}` — `{c17_src}` |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) |")
    say("")
    say("### 0-1. 🆕 `D-9` 읽은 시각 · 빈티지 박제 (`PREREG_POST8.md` §9 (나)1·2 · PD-27 (마)(바))\n")
    say("| # | 의무 | 이 실행의 재측 | 관리자 실측(옮겨 적음 · 대조) |")
    say("|---|---|---|---|")
    say("| ① | 쿼리 실행 시각(KST) | 🔴 **실행 stdout 에만 인쇄**(post7 관용 「산출물에 시각을 박지 않는다」 "
        "`RESULTS_REGDAY_POST7.md:8` · 바이트 결정론 보호) · 정본 실행 값은 산문 `RESULTS_SELECTION_POST8.md` §0 "
        f"· 기계 검사: **실행 시각 > {SWEEP_D1}(D+1 sweep) = {'예' if run_after_sweep else '🔴 아니오'}** · "
        f"**실행 시각 > 창 구간 `max(updated_at)` = {'예' if run_after_maxupd else '🔴 아니오'}** | "
        f"{MGR['run']} |")
    say(f"| ② | 창 구간 `max(daily_prices.updated_at)` | `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` **{v_probe[1]}** · "
        f"이 레인 적재 창 `[{RAW_LO}, {DB_UPTO}]` **{v_lane[1]}** | {MGR['max_upd']} |")
    say("| ③ | 「09-18 봉은 D+1(09-21) sweep 이후 읽음」 | **09-18 봉은 D+1(09-21) sweep 이후 읽음** "
        f"(① 기계 검사 {'예' if run_after_sweep else '🔴 아니오'}) | 같음 |")
    say(f"| ④ | 창 구간 `min(updated_at)` ≥ 09-21 15:35 (기록 · 통과 조건 아님) | "
        f"`[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` **{v_probe[2]} ≥ 09-21 15:35: {'예' if min_ok else '아니오'}** · "
        f"적재 창 {v_lane[2]} ≥ 09-21 15:35: {'예' if min_ok_lane else '아니오'} | "
        f"{MGR['min_upd']} ≥ 09-21 15:35: 예 |")
    say("| ⑤ | `P8-혼합빈티지신고` | §11 (걸침 창마다 한 줄) | PD-27 (바) |")
    say("")
    say("- 🔴 **`updated_at` 은 sweep 이 전 표를 일괄 갱신한 값**이라 빈티지 «증거»가 아니라 **읽은 시각의 기록**이다"
        "(PD-27 (라) · `P-3` 판별력 0 — 「통과」로 인용하지 않는다). 빈티지 정의 = `P8-빈티지`"
        "(D+1 15:35 재기록을 이미 지난 `daily_prices.high/low` · 시간외분이 들어간 채 — `PREREG_POST8.md` §9 (나)1).")
    say("- 🔴 **「정규장만」 갈래는 열지 않는다**(`PREREG_POST8.md` §9 (나)4) · `adj_factor` 산술 **0**(§9 (나)5).")
    say(f"- 창 구간 행수: `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` **{v_probe[3]:,}** · 적재 창 **{v_lane[3]:,}**.")
    say("")
    say("### 0-2. 🆕 `D-3` · `D-6` · `D-8` 의무 줄\n")
    n_ex, n_in = len(EXACT8), len(EXACT8) + len(APPROX8)
    opened = [lbl for lbl in ("SEL-S1", "P6-S1h", "SEL-S2", "SEL-S3", "SEL-S4", "P6-S1h-N")
              if n_in >= MIN_N > n_ex]
    say(f"- **`D-3`**: *「`approx` 포함 시 최소 n 이 차는 축: {'없음' if not opened else ' · '.join(opened)} · "
        f"`exact` 분모 {n_ex} / `approx` 포함 분모 {n_in}」* (`PREREG_POST8.md` §3 (나)3 · PD-21 구성 예고 「없음」과 "
        f"{'일치' if not opened else '🔴 불일치'}) — `exact` {n_ex} ≥ 최소 n {MIN_N} 이라 `approx` 없이도 연다 · "
        "`approx` 포함값은 **의무 민감도 · 판정 언어 없음**(§3 (나)2).")
    say("- **`D-6`**: 이 산출물의 `n_up` 표준편차는 **`ddof=1`(표본)** 이다(`PREREG_POST8.md` §6 SSOT) · "
        "문턱은 **중앙값 ≥ 30** 이지 sd 가 아니다(`PREREG_POST6.md:794`).")
    say(f"- **`D-8`**: 이 레인은 `prog_ver` 를 **공변량으로 쓰지 않는다**(수준 목록 의무 대상 밖 · PD-26) · "
        f"post8 `prog_ver` = `{PROG_VER}`(10행) — 🔴 `missing` 건도 분모에서 빼지 않는다(§8 (나)4).")
    say("")
    say("🔴 **NREP 차이 고지**(§0 의무): `run_selection.py` 는 §3 귀무(창 길이 보존 무작위 종목)에 "
        f"`NREP = {run_selection.NREP:,}` 를 쓴다. **post5~post7 판도 이 스크립트도 귀무를 돌리지 않는다** "
        "— `PREREG_SELECTION.md` §7 예측이 *「중앙값이 문턱을 넘느냐」* 형태라 귀무를 요구하지 않기 "
        "때문이다. ⇒ ***이 문서에 「p 값」은 없다. 「p 값이 있다」고 인용하지 말 것.***")
    say("🔴 **값 보고 규칙을 바꾸지 않는다.** 문언이 모호하면 **양쪽을 인쇄하고 「판정 불가·모호」**로 "
        "적는다. 이 문서 안에서 **새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11). "
        "등급(`PREREG_GRADE_TIERS.md`) 이름은 **적지 않는다**(§6 단계 · PD-16).")
    say("🔴 **`adj_factor` 를 곱하지도 나누지도 않았다**(프로젝트 SSOT 규약 · 원주가 그대로).")
    if not c17_ok:
        say("🔴🔴 **C-17 미반영 — `PREREG_POST6.md` §1-6 8번에 따라 `SEL-S3` 판정은 무효다.**")
    say("")

    # ── §1. 표본 ────────────────────────────────────────────────────────────
    say(f"## §1. 표본 — 8번째 글 **신규 {len(NEW8)}건** 중 **판정 분모 `exact` {len(EXACT8)}건** "
        "(후속 3건은 등록일 축 분모 «밖» · PD-2 2번)\n")
    say(f"| # | 종목 | 코드 | 등록일 | **정밀도** | `[D-19, D]` 봉수(등록일 «포함») | "
        f"창 `[D-4, D]` 봉수 | 표시 | **창 안 DB 행수**(`date <= {DB_UPTO}`) | DB 최초일 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    win20 = {}
    for i, (nm, code, reg, prec, tag) in enumerate(NEW8, 1):
        cur.execute("SELECT count(*) FILTER (WHERE date <= %s), min(date) "
                    "FROM daily_prices WHERE stock_code=%s", (DB_UPTO, code))
        n_all, mn = cur.fetchone()
        if reg:
            nb20, wlen = win20_bars(cur, mdays, code, reg)
            win20[nm] = (nb20, wlen)
            _st, nb5 = stat_tdays(df, code, pd.Timestamp(reg), W_TDAYS)
            nb20_s, nb5_s, reg_s = f"**{nb20}/{wlen}**", str(nb5), reg
        else:
            br = APPROX_BRANCHES.get(nm)
            reg_s = f"{br[0]} (갈래 {len(br[3])})" if br else "🔴 **미명시**(`none` · 🔒 #2)"
            nb20_s = nb5_s = "— (§5-3 갈래별)" if br else "—"
        prec_s = {"exact": "`exact`", "approx": "🟡 `approx`", "none": "🔴 `none`"}[prec]
        emo = "🔀" if nm == URIRO else "🔂"
        say(f"| {i} | {nm} | {code} | {reg_s} | {prec_s} | {nb20_s} | {nb5_s} | "
            f"{emo + ' **' + tag + '**' if tag else '—'} | {n_all} | {mn} |")
    say("")
    say(f"🔁 **후속 {len(FOLLOW8)}건**(" + " · ".join(f"{nm} `{c}` {t}" for nm, c, t in FOLLOW8)
        + ")은 **등록일 축 분모에서 제외**한다 — PD-2 2번: *「이중계상 금지(그 등록 사건은 post7 신규 분모에서 "
          "이미 계상)」* · 값을 보고 뺀 것이 아니라 **«정의»로 빠진다**.")
    say(f"🔴 **`none` {len(NONE8)}건**({' · '.join(NONE8)})은 등록일이 **미기재**다(PD-4 · 🔒 #2 = `none` · "
        "약한 결정) ⇒ 등록일 축 밖. 대안 독법(`exact` 09-03)은 **갈래로 계산하지 않는다**(PD-4).")
    say("🔂 **§1-5 재진입(등록 자체가 같은 종목의 두 번째 사이클)** = 헥토파이낸셜 · 코데즈컴바인(둘 다 `approx`) + "
        "원익(`none`) ⇒ **판정 분모(`exact`) 안 §1-5 재진입 = 0**(§8 · 재진입 민감도 **항등**).")
    say(f"🔀 **{URIRO}** = 한 항목 안 **두 사이클**(post5 한켐 A-9 이후 두 번째 · 측정 등록 09-11 = 사이클 1 · "
        "`P6-PRIOR_CYCLE_IN_WINDOW` 0) ⇒ **포함** · 「우리로 제외」 4 ↔ 3 은 **인쇄만 · 판정 효과 없음**"
        "(🔒 #1-(ii) · PD-3 ③ (ii)).")
    say("")
    say("### 1-1. 🔴 커버리지 — 축별로 «다른 수»다 (PD-11 · 의무 산술 인쇄)\n")
    say("| 축 | 필요한 자료 | 측정 가능 | 측정 불가 | 비율 | 문턱 1/3 |")
    say("|---|---|---|---|---|---|")
    say(f"| **이 레인**(`SEL-`) | `daily_prices` | **{len(EXACT8)}/{len(EXACT8)}** | 0 | 0.0% | 미발동 |")
    say("| (참고) `SEC-` | `stock_industry` 섹터코드 | 3/4 | 1(액스비스) | 25.0% | 미발동 |")
    say("| (참고) `S5` | `dart_financials_asfiled` PIT | 3/4 | 1(액스비스) | 25.0% | — |")
    say("| (참고) `WRC-` | `fill_n >= 2` ∧ 서로 다른 값 레그 >= 3 | 0/4 | — | — | 단독 0 · 누적으로 판정 |")
    say("")
    say("🔴 **액스비스(`0011A0`)는 `stock_info`·`stock_industry` 에 «없지만» 이 레인은 막히지 않는다** — "
        "`market_cap` 을 **`daily_prices` 에서** 읽기 때문이다(`run_selection_post6.py:120-122` 승계 · PD-11). "
        f"`stock_info` = {STOCK_INFO_SNAP[0]} · `max(updated_at)` **{STOCK_INFO_SNAP[1]}**(옮겨 적은 존재 사실 · "
        "이 스크립트는 `stock_info` 를 읽지 않는다). 🔴 우리기술 `032820` ≠ 우리기술투자 `041190`(PD-11).")
    say("")

    # ── §2. SEL-S1 ──────────────────────────────────────────────────────────
    n8 = len(EXACT8)
    say("## §2. `SEL-S1` — 등록일 **종가** 전일대비 >= +15% (동결 문언 · 🔴 기각 «유지»)\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 종가 | **종가 등락** | 문턱 충족 | 표시 |")
    say("|---|---|---|---|---|---|---|")
    s1_hits, s1_rows = 0, []
    for nm, code, reg, tag in EXACT8:
        r = s1_row(raw, code, reg)
        s1_rows.append((nm, reg, r, tag))
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | (데이터 없음) | {tag or '—'} |")
            continue
        ok = r["ret_c"] >= 0.15
        s1_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['close']:,.0f} | "
            f"**{pct(r['ret_c'])}** | {'✅' if ok else '❌'} | {'🔀' if nm == URIRO else '—'} |")
    s1_pass = s1_hits * 2 >= n8
    say(f"\n⇒ **이번 판정 분모 = {s1_hits}/{n8} = {s1_hits/n8*100:.1f}%** · 문턱 **>= 절반**"
        f"(= {-(-n8//2)}/{n8}) ⇒ 표본 자체로는 **{'문턱 위' if s1_pass else '문턱 아래'}**")
    say("")
    say("🔴 **판정 = ❌ 「기각 유지」.** `PREREG_POST6.md` §2-1 이 값을 보기 «전»에 못박았다 — "
        "*「6번째 글에서도 «같은 문턱(+15% 종가, >= 절반)»으로 계속 잰다. **부활 경로는 없다.**」* "
        "⇒ **문턱을 낮추지도, 이번 표본으로 기각을 무르지도 않는다.**")
    if s1_pass:
        say("🟡 **문언 모호 지점(인쇄 의무)**: 이번 표본이 문턱 «위»인데 동결 문언은 「부활 경로 없음」이다. "
            "***이 문서는 그 둘을 «양쪽 다» 인쇄하고 새 결정을 만들지 않는다***.")
    else:
        say("🟢 이번 표본은 문턱 아래다 — 동결 문언(「기각 유지」)과 표본이 같은 방향이라 모호 지점이 없다.")
    say("")

    def s1_count(items):
        rr = [s1_row(raw, c, d) for _n, c, d in items]
        return (sum(1 for r in rr if r and r["ret_c"] >= 0.15), sum(1 for r in rr if r),
                sum(1 for r in rr if r and r["ret_h"] >= 0.15))
    rc4, rc5, rc6, rc7 = s1_count(NEW4), s1_count(NEW5), s1_count(NEW6), s1_count(NEW7)
    say("### 2-1. `SEL-S1` 누적 — 발표값(승계 셈법) + 🆕 같은 스냅샷 재계산 나란히\n")
    say("| 글 | S1 발표값 | S1 **09-24 스냅샷 재계산** | 일치? | 분모 규약 |")
    say("|---|---|---|---|---|")
    say(f"| 1~3번째(33건 중 등록일 특정 7건) | {PUB_33[0]} | —(재계산 대상 아님 · 창·표본 구성이 다르다) | — | "
        "🔴 또 다른 창 |")
    for lbl, key, rc, nn in (("4번째 6건", "post4_cal10", rc4, 6), ("5번째 6건", "post5_td5", rc5, 6),
                             ("6번째 10건", "post6_td5", rc6, 10), ("7번째 `exact` 6건", "post7_td5", rc7, 6)):
        ph = PUB[key][0]
        say(f"| {lbl} | {ph}/{nn} = {ph/nn*100:.1f}% | {rc[0]}/{rc[1]} = {rc[0]/max(rc[1], 1)*100:.1f}% | "
            f"{'✅' if (rc[0], rc[1]) == (ph, nn) else '🔴 **다름**'} | 신규 = `exact`"
            + (" (post7 은 신규 10 ≠ `exact` 6)" if key == "post7_td5" else "") + " |")
    say(f"| **8번째 `exact` {n8}건** | — | **{s1_hits}/{n8} = {s1_hits/n8*100:.1f}%** | — | "
        f"🔴 **신규 {len(NEW8)} ≠ `exact` {n8}**(2회 연속 갈림 · PD-4) |")
    cum_h, cum_n = S1_CUM_PRIOR[0] + s1_hits, S1_CUM_PRIOR[1] + n8
    rh = 6 + rc4[0] + rc5[0] + rc6[0] + rc7[0] + s1_hits
    rn = 7 + rc4[1] + rc5[1] + rc6[1] + rc7[1] + n8
    say(f"| **누적**(승계 셈법 = 발표값 {S1_CUM_PRIOR[0]}/{S1_CUM_PRIOR[1]} + 이번) | "
        f"**{cum_h}/{cum_n} = {cum_h/cum_n*100:.1f}%** | 재계산 셈법(33건 열 6/7 + 재계산 4글 + 이번) = "
        f"**{rh}/{rn} = {rh/rn*100:.1f}%** | — | — |")
    say("")
    say("⚠️ **S1 은 창을 안 쓴다**(등락률) ⇒ 글 사이 S1 은 창 정의와 무관하게 비교 가능하다. "
        "🔴 그래도 **표본이 매번 통째로 바뀌므로 「같은 검정의 반복」이 아니다.**")
    say(f"🔴🔴 **누적 분모 규약** — 위 누적은 **`exact` 기준**이고, 「신규 {len(NEW8)}」 기준 갈래는 §5-3 에 병기한다. "
        "***두 수를 한 칸에 합치지 않는다.***")
    say("")

    # ── §3. P6-S1h ──────────────────────────────────────────────────────────
    say("## §3. `P6-S1h` — 등록일 **고가** 전일대비 >= +15% (`PREREG_POST6.md` §2-1 · §4 #2)\n")
    say("> 🔴 **단조 완화 축이다 — 통과는 증거가 아니다.** `high >= close` 는 항등적으로 참이므로 "
        "`SEL-S1` 통과 ⟹ `P6-S1h` 통과이고, 분모도 같다 ⇒ "
        "***`P6-S1h` 비율 >= `SEL-S1` 비율이 «구성상» 항상 성립***한다.\n")
    say("> 🔑 **증거는 오직 두 방향뿐이다** — ① 비율 < 1/2 이면 **불성립**(⛔ 경로) "
        "② `P6-S1h-N` 이 **안 발동**(`n_up` 중앙 < 30)해야 「그날 드문 종목을 골랐다」가 성립한다(§7).\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 고가 | **고가 등락** | 문턱 충족 | 표시 |")
    say("|---|---|---|---|---|---|---|")
    h_hits = 0
    for nm, reg, r, tag in s1_rows:
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | (데이터 없음) | {tag or '—'} |")
            continue
        ok = r["ret_h"] >= 0.15
        h_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['high']:,.0f} | "
            f"**{pct(r['ret_h'])}** | {'✅' if ok else '❌'} | {'🔀' if nm == URIRO else '—'} |")
    h_pass = h_hits * 2 >= n8
    say(f"\n⇒ **`P6-S1h` = {h_hits}/{n8} = {h_hits/n8*100:.1f}%** · 문턱 **>= 1/2** · 최소 n = {MIN_N} "
        f"(`exact` {n8} >= {MIN_N} ⇒ 판정한다) ⇒ "
        + ("**🟡 문턱 충족 — 단, 단조 완화 축이라 «증거 아님»**" if h_pass
           else "**❌ 불성립(⛔ 경로 발동 — 완화 축에서도 떨어졌다)**"))
    say("")
    say("### 3-1. 🔬 발표값 · 같은 스냅샷 재계산 — **post4·post5 는 탐색적 표기 전용(누적 분모에 넣지 않는다)**\n")
    say("| 글 | 고가 +15% 발표값 | **09-24 스냅샷 재계산** | 일치? | 지위 |")
    say("|---|---|---|---|---|")
    for lbl, key, rc, st in (("4번째 6건", "post4", rc4, "소급 · 탐색"), ("5번째 6건", "post5", rc5, "소급 · 탐색"),
                             ("6번째 10건", "post6", rc6, "판정"), ("7번째 `exact` 6건", "post7", rc7, "판정")):
        ph = PUB_H[key]
        say(f"| {lbl} | {ph[0]}/{ph[1]} = {ph[0]/ph[1]*100:.1f}% | {rc[2]}/{rc[1]} = "
            f"{rc[2]/max(rc[1], 1)*100:.1f}% | {'✅' if (rc[2], rc[1]) == ph else '🔴 **다름**'} | {st} |")
    say(f"| **8번째 `exact` {n8}건 — 판정 대상** | — | **{h_hits}/{n8} = {h_hits/n8*100:.1f}%** | — | 판정 |")
    hc_h, hc_n = H_CUM_PRIOR[0] + h_hits, H_CUM_PRIOR[1] + n8
    say(f"| **판정 누적**(post6~ · 발표값 {H_CUM_PRIOR[0]}/{H_CUM_PRIOR[1]} + 이번) | — | "
        f"**{hc_h}/{hc_n} = {hc_h/hc_n*100:.1f}%** | — | 🔴 누적은 **기록**(누적 문턱 없음) |")
    say("")
    say("🔴 **소급 2행은 판정에 쓰지 않는다** · **`P6-S1h` 의 누적은 6번째 글부터 시작한다.**")
    say("🔴 **`SEL-S1` 의 기각을 무르지 않는다** — `P6-S1h` 통과를 *「S1 이 측정자만 틀렸던 것」*으로 "
        "읽지 않는다(`PREREG_POST6.md` §2-1 ①이 금지한 독법).")
    say("")

    # ── §4. 특징 백분위 ─────────────────────────────────────────────────────
    say("## §4. 특징 9개 백분위 (창 안 일별 백분위의 «최댓값»)\n")
    rows8_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg, _ in EXACT8]
    rows8_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg, _ in EXACT8]
    rows7_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW7]
    rows6_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW6]
    rows5_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW5]
    rows4_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW4]
    rows4_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg in NEW4]
    feat_table(f"4-1. 8번째 글 `exact` {n8}건 — **판정 창**(거래일 {W_TDAYS}일)", rows8_t)
    feat_table(f"4-2. 8번째 글 `exact` {n8}건 — 대조 창(post4 구현 · 달력 {W_CAL_POST4}일)", rows8_c)
    feat_table(f"4-3. 7번째 글 `exact` 6건 — 판정 창(거래일 {W_TDAYS}일) · **09-24 스냅샷 재계산**", rows7_t)
    feat_table(f"4-4. 6번째 글 10건 — 판정 창(거래일 {W_TDAYS}일) · **09-24 스냅샷 재계산**", rows6_t)
    feat_table(f"4-5. 5번째 글 6건 — 판정 창(거래일 {W_TDAYS}일) · **09-24 스냅샷 재계산**", rows5_t)
    feat_table(f"4-6. 4번째 글 6건 — 판정 창(거래일 {W_TDAYS}일) · **09-24 스냅샷 재계산**", rows4_t)
    feat_table(f"4-7. 4번째 글 6건 — 대조 창(달력 {W_CAL_POST4}일) · **09-24 스냅샷 재계산**", rows4_c)

    # ── §5. S2·S3·S4 판정 ───────────────────────────────────────────────────
    a8t, a8c = aggs(rows8_t), aggs(rows8_c)
    a7t, a6t, a5t, a4t, a4c = aggs(rows7_t), aggs(rows6_t), aggs(rows5_t), aggs(rows4_t), aggs(rows4_c)
    s2, s3, s4, s3_n, s3_nan = a8t
    say(f"## §5. `SEL-S2`·`SEL-S3`·`SEL-S4` 판정 (판정 창 = 거래일 {W_TDAYS}일 · 분모 = `exact` {n8})\n")
    say(f"| 예측 | 문언(동결) | 문턱 (출처) | 최소 n | **이번(`exact` {n8}건)** | 판정 | ⛔ 판정 불가 조건 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| **`SEL-S2`** | `거래대금/시총` 백분위 중앙 | >= 95 (값만 기록) · `PREREG_SELECTION.md` §7 "
        f"| {MIN_N} | **{fmt(s2)}** | {'✅ 충족' if s2 is not None and s2 >= 95 else '🟡 미달'} | "
        f"판정 건 < 3 (이번 {n8} ⇒ 미발동) |")
    say(f"| **`SEL-S3`** | `60일 최고종가 갱신` 백분위 중앙 | **< 90** (핵심·위반 시 기각) · "
        f"`PREREG_SELECTION.md` §7 | {MIN_N} | **{fmt(s3)}** (분모 {s3_n}/{n8} · NaN {s3_nan}) | "
        f"{'✅ 지지' if s3 is not None and s3 < 90 else '❌ 기각'} | 판정 건 < 3 · "
        f"**§5-1(C-17) 수정 전이면 무효** ⇒ {'반영 ✅' if c17_ok else '🔴 미반영'} |")
    say(f"| **`SEL-S4`** | `시가총액` 백분위 중앙 | 40~80 (값만 기록) · `PREREG_SELECTION.md` §7 | {MIN_N} | "
        f"**{fmt(s4)}** | {'✅ 구간 내' if s4 is not None and 40 <= s4 <= 80 else '🟡 구간 밖'} | "
        f"판정 건 < 3 (이번 {n8} ⇒ 미발동) |")
    say("")
    same_dir = (a8c[0] is not None and s2 is not None
                and (a8c[0] >= 95) == (s2 >= 95) and (a8c[1] < 90) == (s3 < 90)
                and (40 <= a8c[2] <= 80) == (40 <= s4 <= 80))
    say(f"대조 창(달력 {W_CAL_POST4}일) 값: S2 **{fmt(a8c[0])}** · S3 **{fmt(a8c[1])}** · "
        f"S4 **{fmt(a8c[2])}** — 판정 창과 "
        f"{'**같은 방향**' if same_dir else '🔴 **다른 방향 ⇒ 창 의존**'}. "
        "🔴 **판정은 동결 문언(거래일 5일)으로 선다.**")
    say("")
    say("### 5-1. 누적 — 🔴 **열마다 창·분모 규약·스냅샷이 다르다. 「5연속 재현」이라고 쓰지 않는다.**\n")
    say("| 예측 | 1~3번째(33건)<br>🔴 또 다른 창 | 4번째 발표<br>달력10 · 08-21 | 4번째 재계산<br>거래일5 · **09-24** | "
        "5번째 발표<br>거래일5 · 08-28 | 5번째 재계산<br>거래일5 · **09-24** | 6번째 발표<br>거래일5 · 09-04 | "
        "6번째 재계산<br>거래일5 · **09-24** | 7번째 발표<br>거래일5 · 09-15 · `exact` 6 | 7번째 재계산<br>거래일5 · **09-24** | "
        f"**8번째**<br>거래일5 · **09-24** · `exact` {n8} |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    for k, lbl in ((2, "S2"), (3, "S3"), (4, "S4")):
        j = k - 2
        say(f"| {lbl} | {PUB_33[k - 1]} | {PUB['post4_cal10'][k]:.1f} | {fmt(a4t[j])} | "
            f"{PUB['post5_td5'][k]:.1f} | {fmt(a5t[j])} | {PUB['post6_td5'][k]:.1f} | {fmt(a6t[j])} | "
            f"{PUB['post7_td5'][k]:.1f} | {fmt(a7t[j])} | **{fmt(a8t[j])}** |")
    say("")
    say("⚠️ **「33건」 열은 잣대가 또 다르다** — `run_selection.py` 의 **달력 6일** + 최대 15거래일. "
        "*「방향 참고로만 쓴다」*(`RESULTS_SELECTION_POST5.md` §0).")
    say("⚠️ **`PREREG_POST6.md` §2-1 이 금지한 표현**: *「N연속 재현」이라고 쓰지 않는다*. "
        "***표본이 매번 통째로 바뀌고 스냅샷·측정 장치(C-17)도 움직였으며, 분모 규약(신규 → `exact`)도 2회 연속 "
        "갈렸고, 이번엔 창이 제도 경계(09-14)를 넘는 첫 회차다.***")
    say("")
    say("### 5-2. 🔴 재계산 대조 — 원 발표값 ↔ 이번 09-24 재계산\n")
    say("| 표본 | 창 | 예측 | 원 발표값 | 09-24 재계산 | 차 | 일치? | 비고 |")
    say("|---|---|---|---|---|---|---|---|")
    for tag, pubkey, agg, cw in (("4번째 글", "post4_td5", a4t, f"거래일{W_TDAYS}"),
                                 ("4번째 글", "post4_cal10", a4c, f"달력{W_CAL_POST4}"),
                                 ("5번째 글", "post5_td5", a5t, f"거래일{W_TDAYS}"),
                                 ("6번째 글", "post6_td5", a6t, f"거래일{W_TDAYS}"),
                                 ("7번째 글", "post7_td5", a7t, f"거래일{W_TDAYS}")):
        for k, lbl in ((2, "S2"), (3, "S3"), (4, "S4")):
            pub = PUB[pubkey][k]
            now = agg[k - 2]
            d = None if now is None or now != now else now - pub
            hit = d is not None and abs(d) < 0.05
            mark = "✅ 일치" if hit else "🔴 **다름**"
            extra = "—"
            if lbl == "S3" and not hit:
                extra = (f"🔴 `f9` NaN **{agg[4]}건**이 분모에서 빠졌다(§5-1 5번)"
                         if agg[4] > 0 else
                         "🔴 **C-17 효과가 «아니다»** — `f9` NaN **0건**. "
                         "남는 설명은 «스냅샷/개별 백분위 이동»뿐이다")
            say(f"| {tag} | {cw} | {lbl} | {pub:.1f} | {fmt(now)} | "
                f"{'—' if d is None else f'{d:+.1f}'} | {mark} | {extra} |")
    say("")
    say(f"S3 분모(NaN 제외 후): 4번째 거래일{W_TDAYS} **{a4t[3]}/6**(NaN {a4t[4]}) · "
        f"4번째 달력{W_CAL_POST4} **{a4c[3]}/6**(NaN {a4c[4]}) · "
        f"5번째 **{a5t[3]}/6**(NaN {a5t[4]}) · 6번째 **{a6t[3]}/10**(NaN {a6t[4]}) · "
        f"7번째 **{a7t[3]}/6**(NaN {a7t[4]})")
    say("")
    say("🔴 **과거 산출물을 다시 재지 않는다**(`PREREG_POST6.md` §5-1 5번): 값이 달라져도 "
        "**post4~post7 판정은 그대로 둔다.** 위 표는 「나란히 인쇄」 의무를 이행한 것이며 "
        "***과거 판정의 교체가 아니다.***")
    say("")

    # ── 유니버스 n_up (§7 · §5-3 공용) ───────────────────────────────────────
    ucache = {}

    def nup_of(d):
        if d not in ucache:
            ucache[d] = (universe_raw_count(cur, d), load_universe_day(cur, d))
        raw_n, rowsu = ucache[d]
        up = [(sc, float(tv) / float(mc)) for sc, hi, _cl, tv, mc, pc_, _pdt in rowsu
              if hi is not None and pc_ and float(hi) >= float(pc_) * UP15
              and tv is not None and mc]
        return raw_n, rowsu, up

    # ── §5-3. approx 갈래 ────────────────────────────────────────────────────
    say(f"### 5-3. 🟡 `approx` {len(APPROX8)}건 — **갈래별 인쇄**(의무 민감도 · PD-4 2번 · `PREREG_POST6.md` §1-4)\n")
    say("> 🔴 **값을 보고 한 갈래를 고르지 않는다.** 창 규약이 지시하는 «모든 거래일»을 갈래로 두고 "
        "전부 인쇄한 뒤, 조합 전체에서 판정이 갈리는지만 본다. 🔴 **`approx` 포함값에는 판정 언어를 붙이지 않는다**"
        "(`PREREG_POST8.md` §3 (나)2).\n")
    approx_stats = {}
    for nm, code, _tag in APPROX8:
        label, lo, hi, days = APPROX_BRANCHES[nm]
        cal = [d for d in mdays if lo <= d <= hi]
        say(f"**{nm}** (`{code}`) — {label} = `[{lo}, {hi}]` · 동결 문서 갈래 **{len(days)}일** · "
            f"DB 거래일 달력 실측 **{len(cal)}일** ⇒ "
            + ("🟢 일치 (「창 규약 적용」)"
               if cal == days else f"🔴 **불일치** — DB: {cal} (고치지 않고 그대로 적는다)"))
        say("")
        say("| 갈래 `D` | `[D-19, D]` 봉수 | 창 `[D-4, D]` 봉수 | 종가 등락 | 고가 등락 | "
            "`f1` | `f9` | `f7` | `n_up` | `P6-PRIOR_CYCLE_IN_WINDOW`(계산 · PD-3 표) | 표시 |")
        say("|---|---|---|---|---|---|---|---|---|---|---|")
        per = []
        for d in days:
            nb20, wlen = win20_bars(cur, mdays, code, d)
            st, nb5 = stat_tdays(df, code, pd.Timestamp(d), W_TDAYS)
            r = s1_row(raw, code, d)
            _rn, _ru, up = nup_of(d)
            fl = prior_flag(raw, code, d, PREV_CYCLE[nm])
            per.append((d, st, nb5, r, len(up), fl))
            f1s = "—" if not st else fmt(st["f1_tv_mcap"])
            f9s = "—" if not st else fmt(st["f9_newhigh"])
            f7s = "—" if not st else fmt(st["f7_mcap"])
            want = PD3_FLAG_BR[nm][d]
            mark = ("🔴 **모순 갈래**(「한번 더」 ∧ 직전 등록 08-28 보다 이름 · PD-3)"
                    if d in CONTRA.get(nm, ()) else "—")
            say(f"| {d} | {nb20}/{wlen} | {nb5} | "
                f"{'—' if r is None else pct(r['ret_c'])} | "
                f"{'—' if r is None else pct(r['ret_h'])} | {f1s} | {f9s} | {f7s} | {len(up)} | "
                f"**{fl}** · {want} {'🟢' if fl == want else '🔴 불일치'} | {mark} |")
        say("")
        approx_stats[nm] = (code, per)

    keys = list(approx_stats)
    branch_lists = [approx_stats[k][1] for k in keys]
    nup_ex = [len(nup_of(reg)[2]) for _nm, _code, reg, _t in EXACT8]
    n_med_main = float(np.median(nup_ex))
    say(f"#### 5-3-1. 조합 전체에서 판정이 갈리는가 (`exact` {n8} + `approx` {len(APPROX8)} = "
        f"{n8 + len(APPROX8)}건 = 「신규 {len(NEW8)}」 중 측정 가능 전부 · 전 갈래 조합)\n")
    combo = []
    for cmb in itertools.product(*branch_lists):
        rows = list(rows8_t) + [(k, approx_stats[k][0], c[0], c[1], c[2]) for k, c in zip(keys, cmb)]
        a = aggs(rows)
        s1c = (s1_hits + sum(1 for c in cmb if c[3] and c[3]["ret_c"] >= 0.15)) / (n8 + len(cmb))
        hc = (h_hits + sum(1 for c in cmb if c[3] and c[3]["ret_h"] >= 0.15)) / (n8 + len(cmb))
        nmed = float(np.median(nup_ex + [c[4] for c in cmb]))
        combo.append((a, s1c, hc, nmed))
    n_comb = len(combo)
    say(f"- 갈래 조합 수 = {' x '.join(str(len(b)) for b in branch_lists)} = **{n_comb}**")
    say("")
    say(f"| 예측 | 문턱 | 주 판정(`exact` {n8}) | 조합 최소 | 조합 최대 | 판정이 갈리는가 |")
    say("|---|---|---|---|---|---|")
    flips_ap = {}
    specs = [
        ("`SEL-S1`", ">= 1/2", s1_hits / n8, [c[1] for c in combo], lambda v: v >= 0.5, True),
        ("`P6-S1h`", ">= 1/2", h_hits / n8, [c[2] for c in combo], lambda v: v >= 0.5, True),
        ("`SEL-S2`", ">= 95", s2, [c[0][0] for c in combo], lambda v: v >= 95, False),
        ("`SEL-S3`", "< 90", s3, [c[0][1] for c in combo], lambda v: v < 90, False),
        ("`SEL-S4`", "40~80", s4, [c[0][2] for c in combo], lambda v: 40 <= v <= 80, False),
        ("`P6-S1h-N` `n_up` 중앙", f">= {N_DEGRADE} ⇒ 강등", n_med_main, [c[3] for c in combo],
         lambda v: v >= N_DEGRADE, False),
    ]
    s1_sample_flip = False
    for lbl, thr_s, main_v, vals, test, is_ratio in specs:
        vals = [v for v in vals if v is not None and v == v]
        if not vals or main_v is None or main_v != main_v:
            say(f"| {lbl} | {thr_s} | {fmt(main_v)} | — | — | (계산 불가) |")
            flips_ap[lbl] = None
            continue
        verdicts = set(test(v) for v in vals)
        flip = (len(verdicts) > 1) or (test(main_v) not in verdicts)
        f = (lambda v: f"{v*100:.1f}%") if is_ratio else fmt
        if lbl == "`SEL-S1`":
            # 🔴 `SEL-S1` 의 «판정»은 표본과 무관하게 「기각 유지」다(`PREREG_POST6.md` §2-1 · 부활 경로 없음).
            #    갈래가 바꾸는 것은 «표본 수준»(문턱 위/아래)뿐이다 ⇒ 판정 칸 불변 · 두 독법 병기(§5-3-2).
            s1_sample_flip = flip
            flips_ap[lbl] = False
            say(f"| {lbl} | {thr_s} | {f(main_v)} | {f(min(vals))} | {f(max(vals))} | "
                + ("🟡 **표본 수준만 갈린다**(판정 「기각 유지」는 갈래 무관)" if flip else "🟢 같다") + " |")
            continue
        flips_ap[lbl] = flip
        say(f"| {lbl} | {thr_s} | {f(main_v)} | {f(min(vals))} | {f(max(vals))} | "
            f"{'🔴 **갈린다**' if flip else '🟢 같다'} |")
    say("")
    fl_list = [k for k, v in flips_ap.items() if v]
    if fl_list:
        say(f"🔴🔴 **`approx` 갈래에서 판정이 갈린 항목 {len(fl_list)}건**: " + " · ".join(fl_list)
            + " ⇒ ***「등록일 정밀도 의존」 ⇒ ⛔ 판정 불가***(`PREREG_POST8.md` §3 (나)4 — `exact` 갈래와 `approx` 포함 "
              "갈래가 둘 다 최소 n 을 채우고 답이 갈리면 · 새 기호를 만들지 않는다).")
    else:
        say("🟢 **판정이 갈린 항목 0건** ⇒ `PREREG_POST8.md` §3 (나)4(등록일 정밀도 의존 ⇒ ⛔) **미발동**. "
            "⚠️ 단 이건 「`approx` 가 정확하다」가 아니라 **「집계가 안 뒤집힌다」**일 뿐이다.")
    say("🔴 **`approx` 건은 주 판정 분모에 넣지 않는다**(PD-4 1번) — 위 표는 **민감도**이고, "
        "***여기서 열린 값을 판정으로 승격하지 않는다.*** 🔴 헥토 **모순 갈래 5개**는 표시만 했고 **창을 좁히지 "
        "않았다**(PD-3).")
    say("🔴 **`P6-W10`(무작위 «창» 귀무)은 이 레인이 아니라 `run_regday_post8.py` 가 인쇄한다** — "
        "§1-4 창 규약 용도이며 **`TV` 축의 `P6-W10` 미룸과 한 수로 합치지 않는다**(PD-6 · PD-4 2번).")
    if s1_sample_flip:
        say("")
        say("##### 5-3-2. 🟡 `SEL-S1` — 표본 수준 갈림의 두 독법 (문언 모호 · 양쪽 인쇄 · 새 결정 없음)\n")
        say(f"- 관측: 주 판정 표본(`exact` {n8}) **{s1_hits}/{n8} = {s1_hits/n8*100:.1f}%**(문턱 >= 1/2 «위» · "
            f"경계에 정확히 붙음) ↔ `approx` 포함 {n_comb} 조합 **전부 문턱 «아래»**"
            f"([{min(c[1] for c in combo)*100:.1f}%, {max(c[1] for c in combo)*100:.1f}%]).")
        say("- **독법 A(이 산출물의 판정 칸)**: `PREREG_POST8.md` §3 (나)4 의 「답」 = **판정**이다. `SEL-S1` 의 판정은 "
            "`PREREG_POST6.md` §2-1 이 값과 무관하게 「기각 유지 · 부활 경로 없음」으로 동결했으므로 **두 갈래의 답이 같다** "
            "⇒ (나)4 **비발동** · 판정 칸 = ❌ 기각 유지.")
        say("- **독법 B(병기)**: 「답」 = **표본 수준의 문턱 비교**로 읽으면 두 갈래가 갈린다 ⇒ (나)4 ⇒ ⛔ 판정 불가.")
        say("- 🔑 **두 독법 모두 「부활」은 없다** — A 는 기각 유지, B 는 판정 불가다. §2 의 「문언 모호 지점」"
            "(표본은 문턱 위 ↔ 동결 판정은 기각 유지)은 **`exact` 갈래에서만** 서고 `approx` 포함 갈래에서는 사라진다. "
            "🔴 ***어느 독법을 SSOT 로 할지는 사전등록 사안이다 — 여기서 고르지 않고 둘 다 적는다.***")
    say("")

    # ── §6. f9 원값·NaN ─────────────────────────────────────────────────────
    say("## §6. 🔴 `f9_newhigh` 원값·NaN — C-17 (`PREREG_POST6.md` §4 #5 「`f9` 원값 1 건수 의무 인쇄」)\n")
    say("| 종목 | 창 봉수 | `f9` 원값(창 최대) | 갱신일 | 등록일 당일도 갱신? | `f9` 백분위 | "
        "로드창 선행 봉수 | 상태 |")
    say("|---|---|---|---|---|---|---|---|")
    n_raw1 = n_nan = 0
    nan_names, priors = [], {}
    for nm, code, reg, st, nb in rows8_t:
        m = df[(df.stock_code == code) & (df.date <= pd.Timestamp(reg))].tail(W_TDAYS)
        raw_v = m["f9_newhigh"].max() if not m.empty else None
        n_prior = int(((df.stock_code == code) & (df.date < pd.Timestamp(reg))).sum())
        priors[nm] = n_prior
        is_nan = raw_v is None or raw_v != raw_v
        n_nan += int(is_nan)
        if is_nan:
            nan_names.append(nm)
        raw_s = "🔴 **NaN**" if is_nan else f"{raw_v:.0f}"
        n_raw1 += int((not is_nan) and raw_v == 1.0)
        days = [str(d.date()) for d, v in zip(m.date, m.f9_newhigh) if v == 1.0]
        onD = "✅" if (len(m) and m.f9_newhigh.iloc[-1] == 1.0) else "—"
        pv = None if st is None else st["f9_newhigh"]
        pct_s = "🔴 **NaN**" if (pv is None or pv != pv) else f"{pv:.1f}"
        note_s = "🔴 **C-17 규약으로 `SEL-S3` 분모에서 빠진다**" if is_nan else "—"
        say(f"| {nm} | {nb} | {raw_s} | {'·'.join(days) if days else '—'} | {onD} | {pct_s} | "
            f"{n_prior} | {note_s} |")
    say(f"\n⇒ **`f9` 원값 = 1 인 건 {n_raw1}/{n8}** (4번째 0/6 · 5번째 2/6 · 6번째 2/10 · 7번째 0/6 — 발표값) · "
        f"**NaN(계산 불가) {n_nan}/{n8}**{' — ' + ' · '.join(nan_names) if nan_names else ''}")
    say(f"⇒ **`SEL-S3` 중앙값 분모 = {s3_n}/{n8}** "
        + ("(NaN 건이 없어 전 건이 들어갔다)" if s3_nan == 0 else f"(NaN {s3_nan}건이 빠졌다)"))
    say("")
    say("### 6-1. 🔴 C-17 대상 **0 예고**(PD-12) 확인 — 로드창 직전 봉 · 액스비스 신규 수집 종목\n")
    cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code='0011A0' "
                "AND date BETWEEN '2026-04-01' AND '2026-08-04'")
    ax_have = int(cur.fetchone()[0])
    cur.execute("SELECT count(DISTINCT date) FROM daily_prices WHERE date BETWEEN '2026-04-01' "
                "AND '2026-08-04' AND NOT (stock_code = ANY(%s))", (list(PSEUDO),))
    ax_days = int(cur.fetchone()[0])
    cur.execute("SELECT min(date) FROM daily_prices WHERE stock_code='0011A0'")
    ax_first = cur.fetchone()[0]
    rawp, mcnull, mcfirst = {}, {}, {}
    for nm, code, reg, _t in EXACT8:
        cur.execute("SELECT count(*), count(*) FILTER (WHERE market_cap IS NULL OR market_cap <= 0), "
                    "min(date) FILTER (WHERE market_cap > 0) FROM daily_prices "
                    "WHERE stock_code=%s AND date >= %s AND date < %s", (code, UNIV_LO, reg))
        rawp[nm], mcnull[nm], mcfirst[nm] = cur.fetchone()
    min_raw = min(rawp.values())
    min_prior = min(priors.values())
    say("| 항목 | 값 | PD-12 예고 |")
    say("|---|---|---|")
    say(f"| 로드창(04-01~) 안 등록일 «직전» **DB 원시 행**(PD-12 의 셈 · `p8_win.sql` `load_prior`) — 최소 | **{min_raw}** "
        f"({' · '.join(f'{k} {v}' for k, v in rawp.items())}) | 전건 **≥ 96** ⇒ **대상 0 예고** |")
    say(f"| 🔴 같은 구간 **특징 계산 행**(`market_cap > 0` ∧ `close > 0` — `run_selection.build_features` 가 실제로 쓰는 행) "
        f"— 최소 | **{min_prior}** ({' · '.join(f'{k} {v}' for k, v in priors.items())}) | (예고 없음 — PD-12 는 원시 행을 셌다) |")
    say(f"| 🔴 `market_cap` NULL/0 행 · 첫 `market_cap > 0` 일 | "
        + " · ".join(f"{k} {mcnull[k]}행 · {mcfirst[k]}" for k in rawp) + " | (예고 없음) |")
    say(f"| 액스비스 `0011A0` 2026-04-01 ~ 08-04 봉 | **{ax_have}/{ax_days}** · DB 첫 봉 **{ax_first}** | "
        "**77/85** · 첫 봉 04-13 |")
    say("| `f9_newhigh` NaN(`exact`) | **" + (f"{n_nan}건" if n_nan else "0건") + "** | **0** |")
    say("")
    pd12_ok = (n_nan == 0) and (min_raw >= 96) and ax_have == 77 and ax_days == 85
    say("- " + ("🟢 PD-12 예고(*「로드창 안 직전 봉이 전 건 ≥ 96 ⇒ 대상 0 예고 · 액스비스 04-01~08-04 = 77/85」*)와 "
                "**원시 행 기준으로 계산이 일치**한다 ⇒ C-17 NaN 규약 대상 **0** · `SEL-S3` 분모 = "
                f"{s3_n}/{n8}." if pd12_ok else
                "🔴 PD-12 예고와 **다르다** — 그 사실을 그대로 적고 규약을 고치지 않는다."))
    thin = [k for k, v in priors.items() if v < 60]
    if thin:
        say(f"- 🔴🔴 **새 관측(계산 전 예고 밖 · 기록)**: 특징 계산 행은 원시 행보다 적다 — `market_cap` 이 초기 구간에 "
            f"NULL 이라 로더가 그 행을 버린다. **{' · '.join(f'{k}({priors[k]}행)' for k in thin)}** — 등록일 직전 특징 행이 **60 미만**이라 "
            "`f5`·`f6`·`f9`(60행 rolling · `min_periods=20`)가 **짧은 계열로 계산됐다**. "
            "🔴 C-17 은 이것을 잡지 않는다(NaN 이 아니다) — 「부분 결손」 한계의 실례다. "
            "🔴 **규약을 고치지 않는다**(`PREREG_POST6.md` §5-1 은 NaN 보존만 요구한다) · `SEL-S3` 중앙값은 가운데 두 값의 "
            "평균이라 이 판정에서 계산값을 그대로 쓴다(값 불변 인쇄).")
    say("- 🔴 **한계(인쇄 의무)**: C-17 은 「완전 결측」만 잡고 「부분 결손」은 못 잡는다. "
        "선행 봉이 `min_periods=20` 을 넘으면 `f9` 는 계산되며, ***그 「60봉」은 달력 60거래일이 아니라 "
        "「DB 에 남아 있는 60행(그중 `market_cap > 0` 인 행)」이다.*** 액스비스는 DB 첫 봉이 04-13 이다"
        "(🔴 DB 첫 봉 = 상장일 아님 · PD-11).")
    say("")

    # ── §7. P6-S1h-N + §5-2 유니버스 5열 ────────────────────────────────────
    say("## §7. `P6-S1h-N` (희소성 대칭 단언) + §5-2 유니버스 5열\n")
    say("> 문턱 **`n_up` 중앙 >= 30 ⇒ `P6-S1h` 는 「선정 규칙」으로 인용 금지(판별력 없음으로 강등)** "
        "— 출처 `PREREG_D1_OOS.md` §4 **N2**. ⛔ 판정 불가 조건 = `n_up` 계산 불가일(§5-2 결손).\n")
    say("| 종목 | 등록일 | `universe_mcap` | `universe_test` | `dropped` | `drop_rate` | "
        "`prev_bar_date` | **`n_up`** | 본인이 `n_up` 안에? | `n_up` 안 `f1` 순위 | 백분위 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    nups, drops, ranks = [], [], []
    for nm, code, reg, tag in EXACT8:
        raw_n, rowsu, up = nup_of(reg)
        kept = len(rowsu)
        drop = raw_n - kept
        rate = drop / raw_n if raw_n else float("nan")
        pds = sorted(set(str(r[6]) for r in rowsu if r[6] is not None))
        j = mdays.index(reg) if reg in mdays else None
        mkt_prev = mdays[j - 1] if j else "—"
        pd_s = pds[0] if len(pds) == 1 else f"{min(pds)}~{max(pds)} ({len(pds)}종)"
        if len(pds) > 1:
            pd_s += f" · 시장 직전 거래일 **{mkt_prev}**"
        nup = len(up)
        nups.append((nm, reg, nup, tag))
        drops.append((nm, reg, raw_n, kept, drop, rate, pd_s, mkt_prev))
        up_sorted = sorted(up, key=lambda x: (-x[1], x[0]))
        inset = [k for k, (sc, _v) in enumerate(up_sorted) if sc == code]
        if inset:
            rk = inset[0] + 1
            pctv = (nup - rk) / (nup - 1) * 100 if nup > 1 else 100.0
            rk_s, pct_s, in_s = f"**{rk} / {nup}**", f"{pctv:.1f}", "✅"
            ranks.append((nm, rk, nup, pctv))
        else:
            rk_s, pct_s, in_s = "—", "—", "🔴 **아니다**"
            ranks.append((nm, None, nup, None))
        say(f"| {nm} | {reg} | {raw_n:,} | {kept:,} | "
            f"{'**' + format(drop, ',') + '**' if drop else '0'} | "
            f"{'🔴 **' + f'{rate*100:.2f}%' + '**' if rate >= DROP_GUARD else f'{rate*100:.2f}%'} | "
            f"{pd_s} | **{nup}** | {in_s} | {rk_s} | {pct_s} |")
    say("")
    bad_days = sorted(set((d[1], d[5]) for d in drops if d[5] >= DROP_GUARD))
    if bad_days:
        say(f"🔴 **`drop_rate >= {DROP_GUARD*100:.0f}%` 인 등록일 {len(bad_days)}건**: "
            + " · ".join(f"{d} ({r*100:.2f}%)" for d, r in bad_days)
            + " ⇒ ***그날의 `n_up` 을 다른 날과 «직접 비교하지 말 것»***(`PREREG_POST6.md` §5-2 가드).")
    else:
        say(f"🟢 **`drop_rate >= {DROP_GUARD*100:.0f}%` 인 등록일 0건** "
            f"(최대 {max(d[5] for d in drops)*100:.2f}%) ⇒ §5-2 가드 **미발동**.")
    say("🔴 **편향 방향**(§5-2 의무): `prev_close` 가 없어 빠진 종목은 「급등 아님」이 아니라 "
        "**검정에서 빠진다** — *「빼면 더 커질 뿐 작아지지 않는다」* ⇒ "
        "**`n_up` 결론은 강건하고, 「순위」 진술은 과대**일 수 있다.")
    say("")
    nv = [x[2] for x in nups]
    n_med = float(np.median(nv))
    assert n_med == n_med_main, ("n_up 중앙 배선 불일치", n_med, n_med_main)
    n_sd = float(np.std(nv, ddof=1)) if len(nv) > 1 else float("nan")
    degrade = n_med >= N_DEGRADE
    say("### 7-1. `P6-S1h-N` 판정\n")
    say("| 통계량 | 값 |")
    say("|---|---|")
    say(f"| `n_up` 중앙값 | **{n_med:.1f}** |")
    say(f"| `n_up` 범위 | **[{min(nv)}, {max(nv)}]** |")
    say(f"| `n_up` 표준편차(표본 · `ddof=1` · `PREREG_POST8.md` §6 SSOT) | **{n_sd:.2f}** |")
    say(f"| 문턱 | **>= {N_DEGRADE} ⇒ 인용 금지 강등** (`PREREG_D1_OOS.md` §4 N2) — 🔴 sd 는 문턱이 아니다 |")
    say("| **판정** | **" + ("🔴 발동 — `P6-S1h` 를 「선정 규칙」으로 «인용 금지»(판별력 없음으로 강등)"
                            if degrade else "🟢 미발동 — 희소성 단언이 살아 있다") + "** |")
    say("")
    say("계열 실측 대조(각 판 발표값 · sd 는 `ddof=1`): "
        + " · ".join(f"{p} **중앙 {m} · 범위 {r} · sd {s}**" for p, m, r, s in NUP_SERIES)
        + f" ⇒ 이번 중앙 **{n_med:.1f}** · sd **{n_sd:.2f}**.")
    say("")
    say("### 7-2. 저자 종목의 `n_up` 안 위치 (의무 인쇄 · `PREREG_POST6.md` §2-1)\n")
    say("| 종목 | `n_up` 안 순위 | `n_up` | 백분위 |")
    say("|---|---|---|---|")
    for nm, rk, nup, pctv in ranks:
        say(f"| {nm} | {'**' + str(rk) + '위**' if rk else '🔴 집합 밖'} | {nup} | "
            f"{'—' if pctv is None else f'{pctv:.1f}'} |")
    top1 = [nm for nm, rk, _n, _p in ranks if rk == 1]
    outset = [nm for nm, rk, _n, _p in ranks if rk is None]
    say("")
    say(f"⇒ **1위인 건 {len(top1)}/{n8}**{(' — ' + ' · '.join(top1)) if top1 else ''} · "
        f"**`n_up` 집합 «밖»인 건 {len(outset)}/{n8}**"
        f"{(' — ' + ' · '.join(outset)) if outset else ''}")
    if len(top1) < n8:
        say("🔴 **저자 종목이 1위가 아닌 건이 있다** ⇒ ***「어느 급등주냐」는 여전히 미해결*** "
            "(`PREREG_POST6.md` §2-1 의무 문구).")
    say("")
    say("### 7-3. 죽은 가드 실측 점검 (`PREREG_POST6.md` §7-B #10)\n")
    n_regdays = len(set(r[2] for r in EXACT8))
    say(f"`P6-S1h-N` 이 **상수를 재는가**: `n_up` 이 **{len(set(nv))}개의 서로 다른 값**을 가진다 "
        f"(범위 [{min(nv)}, {max(nv)}] · 표준편차 `ddof=1` {n_sd:.2f}) ⇒ "
        + ("**🟢 상수가 아니다 — 가드는 살아 있다(장식이 아니다)**" if len(set(nv)) > 1
           else "**🔴 상수다 — 죽은 가드 후보**")
        + f" · 🔑 `exact` {n8}건의 등록일은 **{n_regdays}일**뿐이다(같은 날 등록 건은 같은 `n_up`).")
    say("")

    # ── §8. 재진입 · 「우리로 제외」 ────────────────────────────────────────
    say("## §8. 🔂 §1-5 재진입 민감도 (**항등 명시**) + 🔀 「우리로 제외」(**인쇄만**) (`PREREG_POST6.md` §1-5 · PD-3)\n")
    flags_ex = {nm: prior_flag(raw, c, d, []) for nm, c, d, _t in EXACT8}
    say("> 🔴🔴 **판정 분모 안 §1-5 재진입 = 0** — `exact` 4건 중 «등록 자체가 같은 종목의 두 번째 사이클»인 건이 없다. "
        "⇒ **재진입 제외 표본 = 주 판정 표본(항등)** · 「재진입 의존」은 **구성상 생길 수 없다**(판별력 0 · 그 사실을 적는다).\n")
    say("> 🔴 **우리로는 §1-5 재진입이 «아니다»** — 한 항목 안 두 사이클이지만 측정하는 등록(09-11)은 **사이클 1** 이라 "
        "「자기 직전 사이클의 등록일」이 존재하지 않는다(`P6-PRIOR_CYCLE_IN_WINDOW` = 0 · PD-3). "
        "⚠️ 이 플래그와 `WRC-R5` 의 `구조차단`(항목 내 2 사이클 표시 · 우리로 1)은 **다른 플래그**다 — 한 칸에 섞지 않는다.\n")
    say("| 종목 | 정밀도 | 이번 등록일 | 직전 사이클 등록일 | **`P6-PRIOR_CYCLE_IN_WINDOW`**(계산 · PD-3 표) | "
        "판정 분모 안인가 |")
    say("|---|---|---|---|---|---|")
    for nm, _c, d, _t in EXACT8:
        prev_s = "없음(사이클 1 · 항목 내 사이클 2 는 날짜 없음)" if nm == URIRO else "없음"
        say(f"| {nm} | `exact` | {d} | {prev_s} | **{flags_ex[nm]}** · {PD3_FLAG_EXACT[nm]} "
            f"{'🟢' if flags_ex[nm] == PD3_FLAG_EXACT[nm] else '🔴 불일치'} | ✅ 예 |")
    for nm, _c, _t in APPROX8:
        per = approx_stats[nm][1]
        ones = [p[0] for p in per if p[5] == 1]
        say(f"| {nm} | 🟡 `approx` | {APPROX_BRANCHES[nm][0]} | {' · '.join(PREV_CYCLE[nm])} | "
            f"갈래별 **{len(ones)}/{len(per)} 갈래 = 1**({' · '.join(ones) if ones else '—'}) | "
            "🔴 아니다(민감도 갈래) |")
    say("| 원익 | 🔴 `none` | 미기재(🔒 #2) | 2026-08-31 | **계산 안 함**(등록일 축 밖) | 🔴 아니다 |")
    n_flag_in = sum(flags_ex.values())
    say(f"\n⇒ **판정 분모(`exact` {n8}) 안 플래그 합 = {n_flag_in}** · "
        "**글 전체 플래그 = 헥토 2/7 갈래 · 코데즈 7/7 갈래(둘 다 `approx`)** — 두 수를 한 칸에 합치지 않는다.")
    say("🔑 §1-5 3: ***이건 「제외」가 아니라 「이 건은 규칙상 통과할 수 없다」는 사실을 "
        "판정과 같은 무게로 인쇄하는 장치다.***")
    say("")
    keep = [r for r in rows8_t if r[0] != URIRO]
    ak = aggs(keep)
    s1_keep = sum(1 for nm, _reg, r, _t in s1_rows if nm != URIRO and r and r["ret_c"] >= 0.15)
    h_keep = sum(1 for nm, _reg, r, _t in s1_rows if nm != URIRO and r and r["ret_h"] >= 0.15)
    nk = len(keep)
    nups_keep = [x[2] for x in nups if x[0] != URIRO]
    med_keep = float(np.median(nups_keep))
    say(f"| 항목 | 문턱 | **`exact` {n8}건**(주 판정) | **§1-5 재진입 제외**(민감도) | "
        f"🔀 **「우리로 제외」 {nk}건**(인쇄만 · 판정 효과 없음 · 🔒 #1-(ii)) | 「우리로 제외」가 문턱 반대편인가(기록) |")
    say("|---|---|---|---|---|---|")
    rows_sens = [
        ("`SEL-S1`(종가 +15%)", ">= 1/2", f"{s1_hits}/{n8} = {s1_hits/n8*100:.1f}%",
         f"{s1_keep}/{nk} = {s1_keep/nk*100:.1f}%", (s1_hits * 2 >= n8) != (s1_keep * 2 >= nk)),
        ("`P6-S1h`(고가 +15%)", ">= 1/2", f"{h_hits}/{n8} = {h_hits/n8*100:.1f}%",
         f"{h_keep}/{nk} = {h_keep/nk*100:.1f}%", (h_hits * 2 >= n8) != (h_keep * 2 >= nk)),
        ("`SEL-S2`", ">= 95", fmt(s2), fmt(ak[0]), (s2 >= 95) != (ak[0] >= 95)),
        ("`SEL-S3`", "< 90", fmt(s3), fmt(ak[1]), (s3 < 90) != (ak[1] < 90)),
        ("`SEL-S4`", "40~80", fmt(s4), fmt(ak[2]), (40 <= s4 <= 80) != (40 <= ak[2] <= 80)),
        ("`P6-S1h-N` `n_up` 중앙", f">= {N_DEGRADE} ⇒ 강등", f"{n_med:.1f}", f"{med_keep:.1f}",
         (n_med >= N_DEGRADE) != (med_keep >= N_DEGRADE)),
    ]
    uriro_other = []
    for lbl, thr, a, b, other in rows_sens:
        if other:
            uriro_other.append(lbl)
        say(f"| {lbl} | {thr} | {a} | **항등**(= 주 판정 · 제외할 건 0) | {b} | "
            f"{'🟡 예(기록만 — 판정 효과 없음)' if other else '아니오'} |")
    say("")
    say("🟢 **§1-5 재진입 민감도 = 항등** ⇒ 「재진입 의존」 없음(구성상). "
        "🔀 **「우리로 제외」는 인쇄만이다** — PD-3 ③ (ii) · 🔒 #1-(ii): 이 축들의 재진입은 «등록 자체가 두 번째 사이클»이고 "
        "§1-5 논거(*「재진입 건은 구조적으로 자기 첫 사이클의 고가에 막힌다」* `PREREG_POST6.md:277`)는 측정 등록이 첫 사이클인 "
        "우리로에 서지 않는다 ⇒ **`재진입 의존`·`P8-갈래계수` 효과 없음**"
        + (f" · 🟡 문턱 반대편 기록 {len(uriro_other)}건: " + " · ".join(uriro_other) + " (판정 불변)"
           if uriro_other else "")
        + ".")
    say("")

    # ── §9. 절단 가드 ───────────────────────────────────────────────────────
    say("## §9. `P6-절단가드-A`/`B` (`PREREG_POST6.md` §1-6 · PD-12)\n")
    trunc = [(nm, v) for nm, v in win20.items() if v[0] < WIN20]
    frac = len(trunc) / n8
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 분모 | **`exact` {n8}건**(판정 분모) |")
    say(f"| 분자 = 창 `[D-19, D]` 봉수 **< {WIN20}** 인 건 | **{len(trunc)}**"
        f"{' — ' + ' · '.join(f'{nm} {v[0]}/{v[1]}' for nm, v in trunc) if trunc else ''} |")
    say(f"| 비율 | **{len(trunc)}/{n8} = {frac*100:.1f}%** |")
    say("| 문턱 | **>= 1/3 (33.3%) ⇒ ⛔ 판정 불가** |")
    say(f"| **`P6-절단가드-A`** | **{'🔴 발동 ⇒ ⛔ 판정 불가' if frac >= TRUNC_GUARD else '🟢 미발동'}** |")
    say("")
    say("🟢 PD-12 예고(*「`P6-절단가드-A` 분자 **0/4**」*)와 **" + ("계산이 일치" if len(trunc) == 0 else "🔴 다르다")
        + "**한다.")
    say("")
    say("### 9-1. 절단 제외 민감도 (§1-6 2번) — **항등 명시**\n")
    if trunc:
        say("🔴 절단 건이 있다 — 이 판본은 절단 0 을 전제로 쓰였으므로 **여기서 멈추고 그 사실을 적는다**(값 불변).")
    else:
        say(f"- 절단 건 **0** ⇒ 절단 제외 표본 = 전 표본 **{n8}건 = 항등** ⇒ `P6-절단가드-B`(절단 제외 민감도가 판정을 "
            "뒤집으면 ⛔) = **🟢 미발동 — 뒤집힐 여지가 없다(구성상)**.")
    say("⚠️ **문턱 `1/3` 의 출처 = `REC-Y3` 에서 «차용»**(`RESULTS_RECONSTRUCT_POST4.md:119-121`) — "
        "***절단 비율에 대해 검증된 값이 아니다***(§1-6 6번 차용 고지 승계).")
    say("🔑 **봉수 표기 규약**(N8 승계): 창 봉수는 전부 **「등록일 «포함»」** 기준이다 — 20봉 = 등록일 + 직전 19봉.")
    say("")

    # ── §10. D-5 갈래 계수표 ─────────────────────────────────────────────────
    say("## §10. 🆕 `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나)2 · PD-23)\n")
    say("> 규칙: 최소 n(동결값 그대로 = **3**)을 채운 갈래만 「답」으로 센다 · 🔀 「우리로 제외」는 **인쇄만 — 계수에 "
        "넣지 않는다**(🔒 #1-(ii)) · 항등 갈래도 「항등」으로 인쇄 · `approx` 포함 갈래가 `exact` 와 갈리면 `D-3` (나)4 가 "
        "이긴다(⛔ 판정 불가 · PD-23 확인 사항 ㄷ).\n")
    say("| 예측 | 갈래 이름 | n | 답 | 계수에 넣나 |")
    say("|---|---|---|---|---|")
    ans = {
        "`SEL-S1`": ("기각 유지(표본 %d/%d = %.1f%% · %s)" % (s1_hits, n8, s1_hits / n8 * 100,
                                                             "문턱 위" if s1_pass else "문턱 아래"),
                     "%d/%d = %.1f%%" % (s1_keep, nk, s1_keep / nk * 100)),
        "`P6-S1h`": (("문턱 충족(단조 완화 축 · 증거 아님)" if h_pass else "불성립") + " %d/%d" % (h_hits, n8),
                     "%d/%d = %.1f%%" % (h_keep, nk, h_keep / nk * 100)),
        "`SEL-S2`": (("충족" if s2 >= 95 else "미달") + " " + fmt(s2), fmt(ak[0])),
        "`SEL-S3`": (("지지" if s3 < 90 else "기각") + " " + fmt(s3) + f"(분모 {s3_n}/{n8})", fmt(ak[1])),
        "`SEL-S4`": (("구간 내" if 40 <= s4 <= 80 else "구간 밖") + " " + fmt(s4), fmt(ak[2])),
        "`P6-S1h-N`": (("발동" if degrade else "미발동") + f" 중앙 {n_med:.1f}", f"중앙 {med_keep:.1f}"),
    }
    apmap = {"`SEL-S1`": "`SEL-S1`", "`P6-S1h`": "`P6-S1h`", "`SEL-S2`": "`SEL-S2`", "`SEL-S3`": "`SEL-S3`",
             "`SEL-S4`": "`SEL-S4`", "`P6-S1h-N`": "`P6-S1h-N` `n_up` 중앙"}
    cal_dir = {"`SEL-S2`": fmt(a8c[0]), "`SEL-S3`": fmt(a8c[1]), "`SEL-S4`": fmt(a8c[2])}
    counted_div = {}
    for lbl, (main_a, keep_a) in ans.items():
        fa = flips_ap.get(apmap[lbl])
        say(f"| {lbl} | 주 판정(`exact`) | {n8} | **{main_a}** | ✅ |")
        say(f"| {lbl} | §1-5 재진입 포함↔제외 | {n8} ↔ {n8} | **항등**(exact 안 §1-5 재진입 0) | ✅(= 주) |")
        say(f"| {lbl} | 창 절단 포함↔제외 | {n8} ↔ {n8} | **항등**(절단 0) | ✅(= 주) |")
        say(f"| {lbl} | 🔀 「우리로 제외」 | {nk} | {keep_a} — 인쇄만 | ❌(🔒 #1-(ii)) |")
        if lbl == "`SEL-S1`" and s1_sample_flip:
            ap_ans = ("판정 「기각 유지」는 같다(독법 A) · 🟡 **표본 수준은 갈린다**(전 조합 문턱 아래 · "
                      "독법 B 면 ⛔ — §5-3-2)(판정 언어 없음)")
        elif fa is None:
            ap_ans = "— (계산 불가)"
        else:
            ap_ans = "🔴 **주 판정과 갈린다**(판정 언어 없음)" if fa else "주 판정과 같은 쪽(판정 언어 없음)"
        say(f"| {lbl} | `approx` 포함 조합(「신규 {len(NEW8)}」 측정 가능 전부 · {n_comb} 조합) | {n8 + len(APPROX8)} | "
            f"{ap_ans} | ✅(`D-3` (나)4 검사용) |")
        if lbl in cal_dir:
            say(f"| {lbl} | 대조 창(달력 10일 · 판정에 안 씀) | {n8} | {cal_dir[lbl]} — "
                f"{'같은 방향' if same_dir else '다른 방향'} | ❌(판정 창 아님) |")
        counted_div[lbl] = bool(fa)
    say("")
    say("⇒ **계수 결과**: 최소 n 을 채운 갈래(주 · `approx` 포함)가 «판정» 답이 갈린 예측 = "
        + (" · ".join(k for k, v in counted_div.items() if v) if any(counted_div.values()) else "**없음**")
        + (" · 🟡 `SEL-S1` 은 **표본 수준만** 갈린다(판정 불변 · 두 독법 §5-3-2)" if s1_sample_flip else "")
        + " · 항등 갈래 2종(§1-5 재진입 · 절단)은 주 판정과 같은 표본이라 갈릴 수 없다.")
    say("")

    # ── §11. D-9 혼합 빈티지 신고 + 09-11 절단 대조 ─────────────────────────
    say("## §11. 🆕 `D-9` · `P8-혼합빈티지신고` + 09-18 봉 영향 대조 (PD-27 (마) 4 · (바))\n")
    say("> 이 레인의 창 = 판정 창 `[D-4, D]` · 절단 가드 창 `[D-19, D]`(PD-27 (바) 「`REG-`/`REC-` `[D-19, D]`」 열과 같은 "
        "창) · 유니버스 적재 창 `[2026-04-01, 2026-09-18]`. 🔴 셋 다 본다 — **걸치는 창마다 한 줄**.\n")
    say("| 건 | 창 | 시작 | 끝 | 경계 전 봉 | 경계 후 봉 | 걸침? |")
    say("|---|---|---|---|---|---|---|")
    cross_lines = []
    win_items = [(nm, c, d) for nm, c, d, _t in EXACT8]
    for nm, c, _t in APPROX8:
        for d in APPROX_BRANCHES[nm][3]:
            win_items.append((f"{nm}(갈래 {d})", c, d))
    for nm, c, d in win_items:
        for wlab, n in (("`[D-4, D]`", W_TDAYS), ("`[D-19, D]`", WIN20)):
            s = own_split(raw, c, d, n)
            if s is None:
                continue
            crossed = s[2] > 0 and s[3] > 0
            if crossed:
                cross_lines.append(mixed_line(s[0], s[1], s[2], s[3]))
            say(f"| {nm} | {wlab} | {s[0]} | {s[1]} | {s[2]} | {s[3]} | {'🔴 걸침' if crossed else '안 걸침'} |")
    ud = [d for d in mdays if UNIV_LO <= d <= DB_UPTO]
    ub = sum(1 for d in ud if d < REGIME)
    ua = sum(1 for d in ud if d >= REGIME)
    say(f"| 유니버스(시장 달력) | 적재 창 | {ud[0]} | {ud[-1]} | {ub} | {ua} | "
        f"{'🔴 걸침' if ub and ua else '안 걸침'} |")
    if ub and ua:
        cross_lines.append(mixed_line(ud[0], ud[-1], ub, ua))
    say("")
    say("**의무 문장**(`PREREG_POST8.md` §9 (나)3 · 걸침 칸마다):")
    say("")
    if cross_lines:
        for ln in cross_lines:
            say(f"- {ln}")
    else:
        say("- (걸침 창 없음)")
    say("")
    n_cross_judge = len(cross_lines) - (1 if ub and ua else 0)
    say(f"⇒ **판정 창(`[D-4, D]`·`[D-19, D]`) 걸침 = {n_cross_judge}건** — PD-27 (바) 의 `[D-19, D]` 열 「전건 안 걸침」과 "
        + ("🟢 일치" if n_cross_judge == 0 else "🔴 불일치") + " · **걸치는 것은 유니버스 적재 창뿐**이다.")
    say("")
    # 09-18 봉이 판정값에 들어가는가 — 절단 적재(09-11)와 대조 (PD-27 (마) 4 「SEL- 은 계산 레인이 확인」)
    df_cut = build_features(load_ext(DB_UPTO_CUT))
    r8_cut = [(nm, c, reg) + stat_tdays(df_cut, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg, _ in EXACT8]
    a_cut = aggs(r8_cut)
    maxdiff = 0.0
    for (_n1, _c1, _r1, st1, _b1), (_n2, _c2, _r2, st2, _b2) in zip(rows8_t, r8_cut):
        for f in FEATS:
            v1, v2 = st1[f], st2[f]
            if (v1 != v1) and (v2 != v2):
                continue
            maxdiff = max(maxdiff, abs(v1 - v2) if (v1 == v1 and v2 == v2) else float("inf"))
    ap_cut_same = True
    for nm, c, _t in APPROX8:
        for d, st, _nb5, _r, _nu, _fl in approx_stats[nm][1]:
            st2, _nb = stat_tdays(df_cut, c, pd.Timestamp(d), W_TDAYS)
            for f in FEATS:
                v1, v2 = st[f], st2[f]
                if (v1 != v1) and (v2 != v2):
                    continue
                if not (v1 == v1 and v2 == v2) or abs(v1 - v2) > 0:
                    ap_cut_same = False
    same_cut = (a_cut[:3] == a8t[:3]) and maxdiff == 0.0 and ap_cut_same
    n_ap_br = sum(len(APPROX_BRANCHES[nm][3]) for nm, _c, _t in APPROX8)
    say(f"**09-18 봉 영향 대조**(PD-27 (마) 4 — *「`SEL-` 은 유니버스를 `DB_UPTO` 까지 적재하므로 영향 여부는 계산 레인이 "
        f"확인」*): 유니버스를 **{DB_UPTO_CUT}** 까지만 적재해 같은 통계량을 다시 쟀다 — `exact` {n8}건 특징 백분위 최대 "
        f"절대차 **{maxdiff:.4f}** · S2/S3/S4 = {fmt(a_cut[0])} / {fmt(a_cut[1])} / {fmt(a_cut[2])} ↔ 주 {fmt(s2)} / "
        f"{fmt(s3)} / {fmt(s4)} · `approx` {n_ap_br}갈래 {'동일' if ap_cut_same else '🔴 다름'} ⇒ "
        + ("**🟢 동일 — 09-14 이후 봉은 이 레인의 판정값에 들어가지 않는다**(특징은 과거만 보는 rolling · 백분위는 그날 단면)"
           if same_cut else "**🔴 다르다 — 09-14 이후 봉이 판정값을 움직인다(조사 대상 · 값 불변 인쇄)**") + ".")
    say("🔴 그래도 **한 스냅샷에서 한 번에** 돌렸다(PD-27 (마) 4 · 보수적 · 판정에 무해). "
        "🔴 **방향 추론(「`H` 를 높이고 `L` 을 낮춘다」)은 실측으로 인용하지 않는다**(`PREREG_POST8.md` §9 (마)).")
    say("🔴 **한계 절 문장**(`P-4`·`P-5` · 관리자 실측 옮김): `overtime_daily` 09-14 이후 `ovtm_vol > 0` **0** · "
        "09-22·23 행 없음 ⇒ 시간외분을 뺄 수 없다 · 15:30 분봉 09-16~09-23 = 0·0·1·0·1·0 ⇒ 정규장 상한 구성 불가 ⇒ "
        "**「정규장만」 갈래 없음**.")
    say("")

    # ── §12. 판정 요약 ──────────────────────────────────────────────────────
    say("## §12. 판정 요약 — `PREREG_POST6.md` §4 #1~#6·#11 형식 (등급 열 없음)\n")
    prec_dep = {k: bool(flips_ap.get(apmap[k])) for k in ans}
    say(f"| # | 항목 | 문턱 (출처 파일) | 최소 n | 값(`exact` {n8}) | **판정** | 대칭/반증 쌍 | "
        "⛔ 경로 · 민감도 |")
    say("|---|---|---|---|---|---|---|---|")
    say(f"| 1 | `SEL-S1` | >= 1/2 · `PREREG_SELECTION.md` §7 | {MIN_N} | "
        f"{s1_hits}/{n8} = {s1_hits/n8*100:.1f}% | "
        "❌ **기각 유지**(`PREREG_POST6.md` §2-1 · 부활 경로 없음) | `SEL-S3` | "
        f"판정 건 < 3(미발동) · 재진입 제외 **항등** · 절단 제외 **항등** · 「우리로 제외」 {s1_keep}/{nk}(인쇄만)"
        + (" · 🟡 `approx` 포함 조합은 표본 수준 문턱 아래(두 독법 §5-3-2 · 부활 없음)" if s1_sample_flip else "")
        + " |")
    verdict_cell = {}
    v2_ = ("🟡 **문턱 충족 — 단조 완화 축이라 «증거 아님»**" if h_pass else "❌ **불성립**")
    if prec_dep["`P6-S1h`"]:
        v2_ = "⛔ **판정 불가 — 등록일 정밀도 의존**(`PREREG_POST8.md` §3 (나)4) · 기록: " + v2_
    if degrade and h_pass:
        v2_ += " ⇒ #3 발동으로 **인용 금지 강등**"
    verdict_cell["`P6-S1h`"] = v2_
    say(f"| 2 | `P6-S1h` | >= 1/2 · `PREREG_SELECTION.md` §7(상속) | {MIN_N} | "
        f"{h_hits}/{n8} = {h_hits/n8*100:.1f}% | {v2_} | `P6-S1h-N`(`n_up` 중앙 >= 30 → 강등) | "
        f"🔴 **통과는 증거 아님** · 재진입·절단 제외 **항등** · 「우리로 제외」 {h_keep}/{nk}(인쇄만) |")
    v3_ = ("🔴 **발동 ⇒ `P6-S1h` 인용 금지(강등)**" if degrade else "🟢 **미발동**")
    if prec_dep["`P6-S1h-N`"]:
        v3_ = "⛔ **판정 불가 — 등록일 정밀도 의존** · 기록: " + v3_
    verdict_cell["`P6-S1h-N`"] = v3_
    say(f"| 3 | `P6-S1h-N` | >= {N_DEGRADE} → 인용 금지 · `PREREG_D1_OOS.md` §4 | — | "
        f"중앙 {n_med:.1f} · 범위 [{min(nv)}, {max(nv)}] · sd(`ddof=1`) {n_sd:.2f} | {v3_} | 자신이 반증축 | "
        f"`drop_rate >= 1%` {len(bad_days)}일 · 「우리로 제외」 중앙 {med_keep:.1f}(인쇄만) |")
    for num, lbl, thr, val, ok_s, pair, extra in (
            (4, "`SEL-S2`", ">= 95 · `PREREG_SELECTION.md` §7", fmt(s2),
             "✅ **충족**" if s2 >= 95 else "🟡 **미달**", "`SEL-S4`", ""),
            (5, "`SEL-S3`", "**< 90** · `PREREG_SELECTION.md` §7", f"{fmt(s3)} (분모 {s3_n}/{n8})",
             "✅ **지지**" if s3 < 90 else "❌ **기각**", f"`f9` 원값 1 건수 = **{n_raw1}/{n8}**(인쇄 완료)",
             f"§5-1 수정 전이면 무효 ⇒ {'반영 ✅' if c17_ok else '🔴 미반영'} · "),
            (6, "`SEL-S4`", "40~80 · `PREREG_SELECTION.md` §7", fmt(s4),
             "✅ **구간 내**" if 40 <= s4 <= 80 else "🟡 **구간 밖**", "`SEL-S2`", "")):
        if prec_dep[lbl]:
            ok_s = "⛔ **판정 불가 — 등록일 정밀도 의존**(`PREREG_POST8.md` §3 (나)4) · 기록: " + ok_s
        verdict_cell[lbl] = ok_s
        vals = [c[0][num - 4] for c in combo if c[0][num - 4] is not None]
        say(f"| {num} | {lbl} | {thr} | {MIN_N} | {val} | {ok_s} | {pair} | {extra}재진입·절단 제외 **항등** · "
            f"「우리로 제외」 {fmt(ak[num - 4])}(인쇄만) · `approx` 조합 [{fmt(min(vals)) if vals else '—'}, "
            f"{fmt(max(vals)) if vals else '—'}](판정 언어 없음) |")
    say(f"| 11 | `REG-M4` | 기록 · `PREREG_REGDAY_MEASURE.md` §4-4 | — | "
        f"`n_up` 중앙 {n_med:.1f} · 범위 [{min(nv)}, {max(nv)}] | 🟡 **기록만**(대칭 단언 · 판정 아님) | "
        "자신이 반증축 | §5-2 결손일 — 이 표의 `n_up` 은 `P6-S1h-N` 과 **같은 계산**이다 |")
    say("")
    say("### 12-1. 🔴 배선 점검 — 발화한 가드가 판정 칸에 «실제로» 걸렸는가 (post7 교훈 ①)\n")
    say("| 가드 | 상태 | 걸려야 하는 판정 칸 | 칸에 반영됐나 |")
    say("|---|---|---|---|")
    # 발동한 항목의 판정 칸은 «⛔ 판정 불가» 로 시작해야 하고, 미발동 항목은 그 말이 없어야 한다(양방향).
    wired_prec = all(verdict_cell[k].startswith("⛔ **판정 불가 — 등록일 정밀도 의존")
                     == prec_dep[k] for k in verdict_cell)
    wires = [
        ("`P6-S1h-N`(n_up 중앙 ≥ 30)", "발동" if degrade else "미발동", "#2 `P6-S1h`",
         (not degrade) or (not h_pass) or ("인용 금지 강등" in v2_)),
        ("`P6-절단가드-A`", "발동" if frac >= TRUNC_GUARD else "미발동", "#1~#6", frac < TRUNC_GUARD),
        ("`P6-절단가드-B`", "미발동(항등)" if not trunc else "확인 필요", "#1~#6", not trunc),
        ("`drop_rate ≥ 1%`", "발동" if bad_days else "미발동", "#3 비교 금지 문구", True),
        ("C-17 반영", "반영" if c17_ok else "미반영", "#5 `SEL-S3`", c17_ok),
        ("`D-3` (나)4 정밀도 의존", "발동: " + (" · ".join(k for k, v in prec_dep.items() if v) or "없음"),
         "발동 항목의 판정 칸(⛔ 선두)", wired_prec),
        ("§1-5 재진입 의존", "구성상 불가(항등)", "#1~#6", True),
        ("「우리로 제외」", "인쇄만(🔒 #1-(ii))", "없음(판정 효과 없음)", True),
    ]
    for g, s_, tgt, okw in wires:
        say(f"| {g} | {s_} | {tgt} | {'🟢 예' if okw else '🔴 **아니오 — 배선 결함**'} |")
    assert all(w[3] for w in wires), "배선 결함"
    say("")
    say("🔴 **이 문서에서 처음 정한 문턱에 걸렸는가**(`PREREG_POST6.md` §9): "
        f"`drop_rate >= 1%` 가드 = **{'발동' if bad_days else '미발동'}** ⇒ "
        + ("🔴 **「이 문서에서 처음 정한 문턱에 걸렸다」고 적는다.**" if bad_days
           else "🟢 판정을 가르지 않았다."))
    say("")

    # ── §13. D-의무 체크리스트 ──────────────────────────────────────────────
    say("## §13. `PREREG_POST8.md` 인쇄 의무 체크리스트 (이 산출물 · 가분성 §0-5-1)\n")
    say("| 의무 | 이 레인 해당 | 자리 |")
    say("|---|---|---|")
    say("| `D-1`(`ANC-P3` 세 수) | 해당 없음(`ANC-`·`LAD-` 레인) | — |")
    say("| `D-2`(`EXIT-` 세 수) | 해당 없음 | — |")
    say("| `D-3`(`P8-approx의존신고`) | **해당** | §0-2 |")
    say("| `D-4`(`WRC-` 단독 열) | 해당 없음 | — |")
    say("| `D-5`(`P8-갈래계수` 세 쪽) | **해당** | §10 |")
    say("| `D-6`(`ddof=1` 표기) | **해당** | §7-1 · §0-2 |")
    say("| `D-7`(창5 가드 두 산술) | 해당 없음(`LAD-`) · 🔴 이 레인의 `P6-절단가드-A` 는 **다른 가드** | §9 |")
    say("| `D-8`(`prog_ver` 수준 목록) | 해당 없음(공변량 미사용) | §0-2 |")
    say("| `D-9`(①~⑤) | **해당** | §0-1 · §11 |")
    say("| `D-10`(등급 열 형식) | 해당 없음(§6 단계 · 이 문서에 등급 없음) | — |")
    say("| `D-11`(`Q1-R2` 병기) | 해당 없음(이 레인은 `Q1-R2` 를 인용하지 않는다) | — |")
    say("| 공통(라이브 아님 · 과거 표본 같은 스냅샷 재계산 · 새 예측 0) | **해당** | §0 · §2-1 · §3-1 · §4 · §5-1 · §5-2 |")
    say("")
    say("🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1). "
        "🔴 **`adj_factor` 를 곱하지도 나누지도 않았다**(프로젝트 SSOT 규약 · 원주가 그대로).")
    say(f"🔴 **창 종료 {DB_UPTO} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1** · "
        f"**실행 시 `max(date)` = {snap_max} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)**.")

    conn.close()
    (BASE / OUT_NAME).write_bytes(("\n".join(OUT) + "\n").encode("utf-8"))
    note("")
    note(f"[written] {OUT_NAME} · 런타임 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
