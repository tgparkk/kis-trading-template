# -*- coding: utf-8 -*-
"""`PREREG_SELECTION.md` §7 + `PREREG_POST6.md` §2-1 실행 — 7번째 글 (out-of-sample, 4회차).

`run_selection_post6.py` 를 **승계**한다(원본은 손대지 않는다). 특징 정의·백분위 통계량은
`run_selection.py` 의 `build_features` 를 **그대로** 재사용하고, 창 통계량·`s1_row`·`aggs`·
`feat_table`·`fmt`·`med` 는 `run_selection_post6.py` 에서 **import 해 재사용**한다(새 코드 0줄 원칙).

동결 준거(값을 보기 «전»에 고정):
  · `PREREG_SELECTION.md` §7          — `SEL-S1`~`SEL-S4` 문언·문턱
  · `PREREG_POST6.md` §2-1            — `SEL-S1` 기각 유지(부활 경로 없음) · `P6-S1h`(단조 완화 축)
                                        · `P6-S1h-N`(희소성 대칭 단언 · `n_up` 중앙 >= 30 ⇒ 인용 금지 강등)
  · `PREREG_POST6.md` §4 #1~#6·#11    — 문턱·최소 n·대칭 쌍·⛔ 판정 불가 조건
  · `PREREG_POST6.md` §5-1 (C-17)     — `f9_newhigh` NaN 보존 (`run_selection.py` 반영 확인 필수)
  · `PREREG_POST6.md` §5-2 (C-18)     — 유니버스 5열 공개 + `drop_rate >= 1%` 🔴 가드
  · `PREREG_POST6.md` §1-5 (C-5)      — 재진입 건: 분모 포함 + **제외 민감도 의무 인쇄**
  · `PREREG_POST6.md` §1-6 (C-6)      — 절단 가드 `P6-절단가드-A`(창 `[D-19, D]` 봉수 < 20)
  · `PREDECISION_2026-09-15_post7.md` — PD-1(창 종료 = **2026-09-11**) · PD-2(후속 3건 분모 밖)
                                        · PD-3(재진입 3건 · 플래그) · PD-4(등록일 정밀도 · 판정 분모)
                                        · PD-11(코드 해결 · 커버리지) · PD-12(창 봉수 · C-17 NaN 1건)
  · `INTAKE_2026-09-15_post7.md` §1·§5 — 종목·코드·등록일(표 그대로) · 판정 대상 목록

🔴🔴 **이 글에서 «등록일 정밀도»가 처음 갈린다**(PD-4). 신규 10 != `exact` 6.
   **판정 분모 = 신규 ∧ `reg_date_precision = exact` = 6건**(`RNK-D5` · `ANC` §2-3 · `S5` §1-1
   세 동결본이 같은 규칙을 이미 동결했다) · `approx` 2 는 **의무 민감도**(갈래별 인쇄) ·
   `none` 2 + 후속 3 = 5건은 **등록일 축 밖**.

🔴 DB 스냅샷이 post6(최신 09-04)과 다르다. post4·post5·post6 표본도 **같은 09-11 스냅샷에서
   재계산**해 나란히 인쇄한다. 직전 문서 숫자를 그대로 옮겨 비교하지 않는다.
🔴 값 보고 규칙을 바꾸지 않는다. 문언이 모호하면 **양쪽을 인쇄하고 「판정 불가·모호」**로 적는다.
🔴 이 스크립트는 **결과 문서 안에서 새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11).

라이브 트리 import 0건 (pandas / numpy / psycopg2 + 같은 폴더 모듈). DB 는 SELECT 만.
`adj_factor` 를 곱하지도 나누지도 않는다.
"""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

import run_selection
from run_selection import FEATS, PSEUDO, build_features
# 🔴 새 코드 0줄 — post6 판의 통계량·표 포맷을 **그대로** 재사용한다(원본 불변).
#    출처: run_selection_post6.py:180(stat_tdays) :188(stat_cal) :196(med) :204(s1_row)
#          :215(feat_table) :231(aggs) :240(fmt)
from run_selection_post6 import (aggs, feat_table, fmt, med, s1_row, stat_cal,
                                 stat_tdays)
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DB_UPTO = "2026-09-11"          # PD-1: 발행일 09-12(토) 휴장 ⇒ 마지막 거래일. 창 종료 = 09-11.
PUB_DATE = "2026-09-12"         # 7번째 글 발행일(토요일 = 휴장)
W_TDAYS = 5                     # 동결 문언 [D-4, D] = 거래일 5일 (판정 창)
W_CAL_POST4 = 10                # post4 구현 (달력 10일 · 대조 창)
WIN20 = 20                      # `P6-절단가드-A` 의 창 [D-19, D] = D 포함 20거래일
SEED = 20260815                 # 계열 고정 시드 (`run_selection.RNG`)
UP15 = 1.15                     # `n_up` 정의: 등록일 고가 >= 전일 종가 x 1.15
N_DEGRADE = 30                  # `P6-S1h-N` 강등 문턱 (`PREREG_D1_OOS.md` §4 N2 인용)
DROP_GUARD = 0.01               # §5-2 `drop_rate` 가드 1%
TRUNC_GUARD = 1.0 / 3.0         # `P6-절단가드-A` 문턱 (§1-6 3 · `REC-Y3` 차용 고지)

# ── 7번째 글 신규 10건 (INTAKE_2026-09-15_post7 §1 표 그대로) ────────────────
#    (종목, 코드, 등록일, 정밀도, 재진입 태그)
#    🔁 후속 3건(한라캐스트 post6#3 · 아난티 post6#5 · 우리기술투자 post6#11)은
#       **등록일 축 분모 밖**(PD-2 2번) ⇒ 이 목록에 «없다».
NEW7 = [
    ("한전기술", "052690", None, "none", ""),
    ("한전산업", "130660", None, "none", ""),
    ("지투파워", "388050", None, "approx", "재진입(3번째 사이클)"),
    ("서산", "079650", "2026-09-03", "exact", ""),
    ("강동씨엔앨", "198440", "2026-09-03", "exact", ""),
    ("로보티즈", "108490", "2026-09-04", "exact", ""),
    ("해치텍", "0155E0", "2026-09-07", "exact", ""),
    ("빛과전자", "069540", "2026-09-08", "exact", "재진입(2번째)"),
    ("한국화장품제조", "003350", None, "approx", "재진입(2번째)"),
    ("범한퓨얼셀", "382900", "2026-09-09", "exact", ""),
]
# 판정 분모 = 신규 ∧ `exact` = 6건 (PD-4 1번)
EXACT7 = [(nm, c, d, tag) for nm, c, d, p, tag in NEW7 if p == "exact"]
APPROX7 = [(nm, c, tag) for nm, c, d, p, tag in NEW7 if p == "approx"]
NONE7 = [nm for nm, c, d, p, tag in NEW7 if p == "none"]

# `PREREG_POST6.md` §1-4 창 규약 «첫 발동» (PD-4 2번 · 달력 실측을 옮겨 적은 값).
#    「9월 초」 = 09-01~09-10 의 거래일 8일 · 「8월 말」 = 08-21~08-31 의 거래일 7일.
#    🔴 실행 시 `daily_prices` 거래일 달력과 대조해 어긋나면 그 사실을 인쇄한다(고치지 않는다).
APPROX_BRANCHES = {
    "지투파워": ("「9월 초」", "2026-09-01", "2026-09-10",
                 ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
                  "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"]),
    "한국화장품제조": ("「8월 말」", "2026-08-21", "2026-08-31",
                       ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
                        "2026-08-27", "2026-08-28", "2026-08-31"]),
}

# PD-3 — 재진입 3건. 🔴 그중 **판정 분모(`exact` 6) 안에 있는 것은 빛과전자 1건뿐**이고
#    그 건의 `P6-PRIOR_CYCLE_IN_WINDOW` = **0**(직전 등록일 08-05 < 창 시작 08-11) =>
#    **판정 분모 안 플래그 = 0**. 글 전체 플래그 2건은 둘 다 `approx` 갈래다.
REENTRY_ALL = {"지투파워", "한국화장품제조", "빛과전자"}
REENTRY_EXACT = {"빛과전자"}
PD3_FLAG = {"지투파워": 1, "한국화장품제조": 1, "빛과전자": 0}
PD3_PREV = {"지투파워": "2026-08-26", "한국화장품제조": "2026-08-12", "빛과전자": "2026-08-05"}

# 6번째 글 신규 10건 (`run_selection_post6.NEW6` 와 같은 표) — 같은 스냅샷 재계산용.
NEW6 = [
    ("한라캐스트", "125490", "2026-08-21"),
    ("헥토파이낸셜", "234340", "2026-08-28"),
    ("아난티", "025980", "2026-08-19"),
    ("아이티센글로벌", "124500", "2026-08-20"),
    ("현대약품", "004310", "2026-09-01"),
    ("원익", "032940", "2026-08-31"),
    ("쿠콘", "294570", "2026-08-28"),
    ("지투파워", "388050", "2026-08-26"),
    ("우리기술투자", "041190", "2026-08-25"),
    ("비에이치", "090460", "2026-09-01"),
]
NEW5 = [
    ("혜인", "003010", "2026-08-11"),
    ("한국화장품제조", "003350", "2026-08-12"),
    ("코데즈컴바인", "047770", "2026-08-21"),
    ("한켐", "457370", "2026-08-20"),
    ("삼양바이오팜", "0120G0", "2026-08-21"),
    ("광전자", "017900", "2026-08-05"),
]
NEW4 = [
    ("이노테크", "469610", "2026-08-13"),
    ("한켐", "457370", "2026-08-12"),
    ("금호건설", "002990", "2026-08-12"),
    ("지투파워", "388050", "2026-08-13"),
    ("PS일렉트로닉스", "332570", "2026-08-13"),
    ("코데즈컴바인", "047770", "2026-08-19"),
]

# 직전 문서가 **발표한** 집계 (문서에서 옮겨 적은 상수 · 재계산 아님 · 대조용).
PUB = {
    # (S1 hits, S1 n, S2, S3, S4)
    "post4_cal10": (3, 6, 99.7, 48.0, 64.2),    # RESULTS_SELECTION_POST4_NUMBERS.md (08-21)
    "post4_td5": (3, 6, 99.7, 47.5, 64.2),      # RESULTS_SELECTION_POST5.md §4-1 (08-28)
    "post5_td5": (2, 6, 99.5, 47.9, 66.1),      # RESULTS_SELECTION_POST5.md §0 (08-28)
    "post6_td5": (7, 10, 99.7, 47.6, 78.9),     # RESULTS_SELECTION_POST6_NUMBERS.md §5 (09-04)
}
PUB_33 = ("6/7 = 85.7%", "99.4", "48.3", "61.6")       # 1~3번째 글 33건 열 (🔴 또 다른 창)
PUB_H = {"post4": (6, 6), "post5": (4, 6), "post6": (8, 10)}   # 고가 변량 소급값(탐색 표기 전용)
S1_CUM_PRIOR = (18, 29)                                # RESULTS_SELECTION_POST6_NUMBERS.md §2-1
# PD-11 — 명부 스냅샷이 낡았다는 «존재 사실»(계산값 아님 · 옮겨 적는다).
STOCK_INFO_SNAP = ("2,115행", "2026-02-10 10:33:05")


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


# ── 로더 (post6 승계 · 상단만 09-11 로 넓힌다) ───────────────────────────────
def load_ext():
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, high, low, close, trading_value, market_cap "
        f"FROM daily_prices WHERE date BETWEEN '2026-04-01' AND '{DB_UPTO}' "
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
        f"WHERE date BETWEEN '2026-01-01' AND '{DB_UPTO}' AND close > 0", conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def market_days(cur):
    """시장 거래일 달력 (의사티커 제외 · 봉이 하나라도 있는 날)."""
    cur.execute(
        "SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s "
        "AND NOT (stock_code = ANY(%s)) ORDER BY date",
        ("2026-01-01", DB_UPTO, list(PSEUDO)))
    return [r[0] for r in cur.fetchall()]


def snapshot_tail(cur):
    """PD-1 5번 표기 의무 — 실행 시 `max(date)` 와 그 날짜 행수(창으로 쓰지 «않는다»)."""
    cur.execute("SELECT max(date) FROM daily_prices")
    mx = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (mx,))
    return str(mx), int(cur.fetchone()[0])


def universe_raw_count(cur, d):
    """그날 `market_cap>0` 인 종목 수 (prev_close 필터 «전») — §5-2 `universe_mcap`."""
    cur.execute(
        "SELECT count(*) FROM daily_prices WHERE date=%s AND close > 0 "
        "AND market_cap IS NOT NULL AND market_cap > 0 AND NOT (stock_code = ANY(%s))",
        (d, list(PSEUDO)))
    return int(cur.fetchone()[0])


def load_universe_day(cur, d):
    """등록일 유니버스 (그날 + 직전 «자기» 봉의 종가·날짜). `run_selection_post6` 승계.

    🔑 `daily_prices.date` 는 **text** 컬럼이다(ISO 'YYYY-MM-DD') — 날짜 산술을 SQL 에서 하면
       `text >= timestamp` 로 죽는다. 하한을 파이썬에서 문자열로 만들어 넘긴다.
    """
    lo = (pd.Timestamp(d) - pd.Timedelta(days=20)).date().isoformat()
    cur.execute(
        "WITH u AS (SELECT stock_code, date, high, close, trading_value, market_cap, "
        "  LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close, "
        "  LAG(date)  OVER (PARTITION BY stock_code ORDER BY date) AS prev_date "
        "  FROM daily_prices WHERE date BETWEEN %s AND %s AND close > 0) "
        "SELECT stock_code, high, close, trading_value, market_cap, prev_close, prev_date FROM u "
        "WHERE date = %s AND market_cap IS NOT NULL AND market_cap > 0 "
        "AND prev_close IS NOT NULL AND prev_close > 0 AND NOT (stock_code = ANY(%s)) "
        "ORDER BY stock_code",
        (lo, d, d, list(PSEUDO)))
    return cur.fetchall()


def win20_bars(cur, mdays, code, reg):
    """창 `[D-19, D]` 의 (그 종목 봉수, 창 길이) — 봉수는 **등록일 «포함»** 셈(§1-6 7 · N8)."""
    if reg not in mdays:
        return 0, 0
    j = mdays.index(reg)
    wdays = mdays[max(0, j - WIN20 + 1): j + 1]
    cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code=%s AND date = ANY(%s)",
                (code, wdays))
    return int(cur.fetchone()[0]), len(wdays)


def pct(v):
    return "—" if v is None else "%+.2f%%" % (v * 100)


def main():  # noqa: C901
    t0 = time.time()

    src = (BASE / "run_selection.py").read_text(encoding="utf-8")
    c17_line = next((i + 1 for i, ln in enumerate(src.splitlines())
                     if "where(prev_max.notna())" in ln), None)
    c17_ok = c17_line is not None
    c17_src = src.splitlines()[c17_line - 1].strip() if c17_ok else "(없음)"

    say("# RESULTS_SELECTION_POST7_NUMBERS — 기계 생성 (수정 금지)\n")
    say("사전등록 `PREREG_SELECTION.md` §7(`9e53825`, 8/15 동결) + "
        "`PREREG_POST6.md` §2-1·§4 #1~#6·#11 · 생성 `run_selection_post7.py` "
        "(`run_selection_post6.py` 승계 · 원본 불변)")
    say("계산 «전» 동결 = [`PREDECISION_2026-09-15_post7.md`](PREDECISION_2026-09-15_post7.md) · "
        "[`INTAKE_2026-09-15_post7.md`](INTAKE_2026-09-15_post7.md) · "
        "[`LABELS_2026-09-15_post7.md`](LABELS_2026-09-15_post7.md)")
    say("")
    say("## §0. 실행 환경 · 동결 규약 (값을 보기 «전»에 고정)\n")

    df = build_features(load_ext())
    raw = load_raw_close()

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    mdays = market_days(cur)
    snap_max, snap_rows = snapshot_tail(cur)

    say("| 항목 | 값 |")
    say("|---|---|")
    say("| DB | `kis_template.daily_prices` — **SELECT 만** |")
    say(f"| 유니버스 창 | 2026-04-01 ~ **{DB_UPTO}** (`market_cap > 0` ∧ `close > 0` ∧ 의사티커 제외) |")
    say(f"| 유니버스 | **{df.stock_code.nunique():,}종목** · **{df.date.nunique()}거래일** "
        f"· 최신 봉 **{df.date.max().date()}** |")
    say(f"| 🔴 창 종료 | **창 종료 {DB_UPTO} = 발행일({PUB_DATE} 토) 휴장 ⇒ 마지막 거래일 · "
        "B-1(전 축 · `WRC-` 포함)** (PD-1) |")
    say(f"| 🔴 실행 시 스냅샷(기록만) | **실행 시 `max(date)` = {snap_max} · "
        f"그 날짜 행수 = {snap_rows:,}** — PD-1 5번 표기 의무. ***창으로 쓰지 않는다.*** |")
    say(f"| 판정 창 | 동결 문언 `[D-4, D]` = **거래일 {W_TDAYS}일** (`PREREG_SELECTION.md` §2) |")
    say(f"| 대조 창 | post4 구현 `달력 {W_CAL_POST4}일` — **판정에 쓰지 않는다** |")
    say(f"| 🔴 판정 분모 | **신규 ∧ `exact` = {len(EXACT7)}건** (PD-4 1번 · `RNK-D5` · "
        "`PREREG_ANCHOR_REDESIGN.md` §2-3 · `PREREG_S5_FUND_NEWS_OOS.md` §1-1) |")
    say(f"| 민감도 분모 | `approx` **{len(APPROX7)}건**(갈래별 인쇄 · §5-3) · "
        f"「신규 {len(NEW7)}」 갈래 병기 |")
    say(f"| 축 밖 | `none` **{len(NONE7)}건**({' · '.join(NONE7)}) + 후속 **3건**"
        "(한라캐스트 · 아난티 · 우리기술투자 — PD-2) |")
    say(f"| 시드 | **{SEED}** (`run_selection.RNG` 계열 고정값) |")
    say(f"| NREP | **{run_selection.NREP:,}** = `run_selection.py` 상수 그대로 — "
        "🔴 **이 스크립트는 귀무를 «돌리지 않는다»**(post5·post6 승계) |")
    say(f"| C-17 반영 | {'✅' if c17_ok else '🔴 **미반영 ⇒ 산출물 무효**'} "
        f"`run_selection.py:{c17_line}` — `{c17_src}` |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다** (`PREREG.md` §0-2) |")
    say("")
    say("🔴 **NREP 차이 고지**(§0 의무): `run_selection.py` 는 §3 귀무(창 길이 보존 무작위 종목)에 "
        f"`NREP = {run_selection.NREP:,}` 를 쓴다. **post5·post6 판도 이 스크립트도 귀무를 돌리지 않는다** "
        "— `PREREG_SELECTION.md` §7 예측이 *「중앙값이 문턱을 넘느냐」* 형태라 귀무를 요구하지 않기 "
        "때문이다. ⇒ ***이 문서에 「p 값」은 없다. 「p 값이 있다」고 인용하지 말 것.***")
    say("🔴 **값 보고 규칙을 바꾸지 않는다.** 문언이 모호하면 **양쪽을 인쇄하고 「판정 불가·모호」**로 "
        "적는다. 이 문서 안에서 **새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11).")
    say("🔴 **`adj_factor` 를 곱하지도 나누지도 않았다**(프로젝트 SSOT 규약 · 원주가 그대로).")
    if not c17_ok:
        say("🔴🔴 **C-17 미반영 — `PREREG_POST6.md` §1-6 8번에 따라 `SEL-S3` 판정은 무효다.**")
    say("")

    # ── §1. 표본 ────────────────────────────────────────────────────────────
    say(f"## §1. 표본 — 7번째 글 **신규 {len(NEW7)}건** 중 **판정 분모 `exact` {len(EXACT7)}건** "
        "(후속 3건은 등록일 축 분모 «밖» · PD-2 2번)\n")
    say("| # | 종목 | 코드 | 등록일 | **정밀도** | `[D-19, D]` 봉수(등록일 «포함») | "
        "창 `[D-4, D]` 봉수 | 재진입 | DB 행수 | DB 최초일 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    win20 = {}
    for i, (nm, code, reg, prec, tag) in enumerate(NEW7, 1):
        cur.execute("SELECT count(*), min(date) FROM daily_prices WHERE stock_code=%s", (code,))
        n_all, mn = cur.fetchone()
        if reg:
            nb20, wlen = win20_bars(cur, mdays, code, reg)
            win20[nm] = (nb20, wlen)
            _st, nb5 = stat_tdays(df, code, pd.Timestamp(reg), W_TDAYS)
            nb20_s, nb5_s, reg_s = f"**{nb20}/{wlen}**", str(nb5), reg
        else:
            br = APPROX_BRANCHES.get(nm)
            reg_s = f"{br[0]} (갈래 {len(br[3])})" if br else "🔴 **미명시**"
            nb20_s = nb5_s = "— (§5-3 갈래별)" if br else "—"
        prec_s = {"exact": "`exact`", "approx": "🟡 `approx`", "none": "🔴 `none`"}[prec]
        say(f"| {i} | {nm} | {code} | {reg_s} | {prec_s} | {nb20_s} | {nb5_s} | "
            f"{'🔂 **' + tag + '**' if tag else '—'} | {n_all} | {mn} |")
    say("")
    say("🔁 **후속 3건**(한라캐스트 `125490` post6 #3 · 아난티 `025980` post6 #5 · "
        "우리기술투자 `041190` post6 #11)은 **등록일 축 분모에서 제외**한다 — PD-2 2번: "
        "*「그 등록 사건은 post6 신규 분모에서 이미 계상됐다. 값을 보고 뺀 것이 아니라 «정의»로 빠진다」*.")
    say(f"🔴 **`none` {len(NONE7)}건**({' · '.join(NONE7)})은 **등록일 문장 자체가 없다**(PD-4) ⇒ "
        "등록일 축 밖. 「8월 26일」은 **급등 사유일**이고 등록 문장과 다른 줄이라 **승격하지 않는다**.")
    say("🔂 **재진입 3건**(지투파워 3번째 사이클 · 한국화장품제조 · 빛과전자 — PD-3): "
        "**분모에 넣는다**(`PREREG_POST6.md` §1-5 1번) + **제외 민감도 의무 인쇄**(§8).")
    say("")
    say("### 1-1. 🔴 커버리지 — 축별로 «다른 수»다 (PD-11 3번 · 의무 산술 인쇄)\n")
    say("| 축 | 필요한 자료 | 측정 가능 | 측정 불가 | 비율 | 문턱 1/3 |")
    say("|---|---|---|---|---|---|")
    say(f"| **이 레인**(`SEL-`) | `daily_prices` | **{len(EXACT7)}/{len(EXACT7)}** | 0 | 0.0% | 미발동 |")
    say("| (참고) `SEC-` | `stock_industry` 섹터코드 | 5/6 | 1(해치텍) | 16.7% | 미발동 |")
    say("| (참고) `S5` | `dart_financials_asfiled` PIT | 5/6 | 1(해치텍) | 16.7% | 판정 안 함(PD-15) |")
    say("| (참고) `WRC-` | `fill_n >= 2` ∧ 서로 다른 값 레그 >= 3 | 0/6 | — | — | 최소 n 미달 ⇒ ⛔ |")
    say("")
    say("🔴 **서산·해치텍은 `stock_info` 에 «없지만» 이 레인은 막히지 않는다** — `market_cap` 을 "
        "**`daily_prices` 에서** 읽기 때문이다(`run_selection_post6.py:120-122` 승계 · PD-11 1번). "
        f"결손은 두 종목의 문제가 아니라 **명부 스냅샷의 문제**다: `stock_info` = {STOCK_INFO_SNAP[0]} · "
        f"`max(updated_at)` **{STOCK_INFO_SNAP[1]}**(옮겨 적은 존재 사실 · 이 스크립트는 `stock_info` 를 "
        "읽지 않는다).")
    say("")

    # ── §2. SEL-S1 ──────────────────────────────────────────────────────────
    say("## §2. `SEL-S1` — 등록일 **종가** 전일대비 >= +15% (동결 문언 · 🔴 기각 «유지»)\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 종가 | **종가 등락** | 문턱 충족 | 재진입 |")
    say("|---|---|---|---|---|---|---|")
    s1_hits, s1_rows = 0, []
    for nm, code, reg, tag in EXACT7:
        r = s1_row(raw, code, reg)
        s1_rows.append((nm, reg, r, tag))
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | (데이터 없음) | {tag or '—'} |")
            continue
        ok = r["ret_c"] >= 0.15
        s1_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['close']:,.0f} | "
            f"**{pct(r['ret_c'])}** | {'✅' if ok else '❌'} | {'🔂' if tag else '—'} |")
    n7 = len(EXACT7)
    s1_pass = s1_hits * 2 >= n7
    say(f"\n⇒ **이번 판정 분모 = {s1_hits}/{n7} = {s1_hits/n7*100:.1f}%** · 문턱 **>= 절반**"
        f"(= {-(-n7//2)}/{n7}) ⇒ 표본 자체로는 **{'문턱 위' if s1_pass else '문턱 아래'}**")
    say("")
    say("🔴 **판정 = ❌ 「기각 유지」.** `PREREG_POST6.md` §2-1 이 값을 보기 «전»에 못박았다 — "
        "*「6번째 글에서도 «같은 문턱(+15% 종가, >= 절반)»으로 계속 잰다. **부활 경로는 없다.**」* "
        "⇒ **문턱을 낮추지도, 이번 표본으로 기각을 무르지도 않는다.**")
    if s1_pass:
        say("🟡 **문언 모호 지점(인쇄 의무)**: 이번 표본이 문턱 «위»인데 동결 문언은 「부활 경로 없음」이다. "
            "***이 문서는 그 둘을 «양쪽 다» 인쇄하고 새 결정을 만들지 않는다***.")
    else:
        say("🟢 이번 표본도 문턱 아래다 — 동결 문언(「기각 유지」)과 표본이 같은 방향이라 모호 지점이 없다.")
    say("")
    say("### 2-1. `SEL-S1` 누적 (`RESULTS_SELECTION_POST6_NUMBERS.md` §2-1 승계)\n")
    say("| 글 | S1(종가) | 분모 규약 |")
    say("|---|---|---|")
    say(f"| 1~3번째(33건 중 등록일 특정 7건) | {PUB_33[0]} | 🔴 또 다른 창 |")
    say(f"| 4번째 6건 | {PUB['post4_cal10'][0]}/6 = {PUB['post4_cal10'][0]/6*100:.1f}% | 신규 = `exact` |")
    say(f"| 5번째 6건 | {PUB['post5_td5'][0]}/6 = {PUB['post5_td5'][0]/6*100:.1f}% | 신규 = `exact` |")
    say(f"| 6번째 10건 | {PUB['post6_td5'][0]}/10 = {PUB['post6_td5'][0]/10*100:.1f}% | 신규 = `exact` |")
    say(f"| **7번째 {n7}건** | **{s1_hits}/{n7} = {s1_hits/n7*100:.1f}%** | "
        f"🔴 **신규 {len(NEW7)} != `exact` {n7}** — 이 계열 최초로 갈렸다(PD-4) |")
    cum_h, cum_n = S1_CUM_PRIOR[0] + s1_hits, S1_CUM_PRIOR[1] + n7
    say(f"| **누적** | **{cum_h}/{cum_n} = {cum_h/cum_n*100:.1f}%** | — |")
    say("")
    say("⚠️ **S1 은 창을 안 쓴다**(등락률) ⇒ 글 사이 S1 은 창 정의와 무관하게 비교 가능하다. "
        "🔴 그래도 **표본이 매번 통째로 바뀌므로 「같은 검정의 반복」이 아니다.**")
    say("🔴🔴 **누적 분모 규약이 이 글에서 갈린다** — post4~6 은 「신규 = `exact`」라 두 정의가 같은 "
        f"수였다. post7 은 신규 {len(NEW7)} != `exact` {n7} 이다. 위 누적은 **`exact` 기준**이고, "
        f"「신규 {len(NEW7)}」 기준 갈래는 §5-3 에 병기한다. ***두 수를 한 칸에 합치지 않는다.***")
    say("")

    # ── §3. P6-S1h ──────────────────────────────────────────────────────────
    say("## §3. `P6-S1h` — 등록일 **고가** 전일대비 >= +15% (`PREREG_POST6.md` §2-1 · §4 #2)\n")
    say("> 🔴 **단조 완화 축이다 — 통과는 증거가 아니다.** `high >= close` 는 항등적으로 참이므로 "
        "`SEL-S1` 통과 ⟹ `P6-S1h` 통과이고, 분모도 같다 ⇒ "
        "***`P6-S1h` 비율 >= `SEL-S1` 비율이 «구성상» 항상 성립***한다.\n")
    say("> 🔑 **증거는 오직 두 방향뿐이다** — ① 비율 < 1/2 이면 **불성립**(⛔ 경로) "
        "② `P6-S1h-N` 이 **안 발동**(`n_up` 중앙 < 30)해야 「그날 드문 종목을 골랐다」가 성립한다(§7).\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 고가 | **고가 등락** | 문턱 충족 | 재진입 |")
    say("|---|---|---|---|---|---|---|")
    h_hits = 0
    for nm, reg, r, tag in s1_rows:
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | (데이터 없음) | {tag or '—'} |")
            continue
        ok = r["ret_h"] >= 0.15
        h_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['high']:,.0f} | "
            f"**{pct(r['ret_h'])}** | {'✅' if ok else '❌'} | {'🔂' if tag else '—'} |")
    h_pass = h_hits * 2 >= n7
    say(f"\n⇒ **`P6-S1h` = {h_hits}/{n7} = {h_hits/n7*100:.1f}%** · 문턱 **>= 1/2** · 최소 n = 3 "
        f"(`exact` {n7} >= 3 ⇒ 판정한다) ⇒ "
        + ("**🟡 문턱 충족 — 단, 단조 완화 축이라 «증거 아님»**" if h_pass
           else "**❌ 불성립(⛔ 경로 발동 — 완화 축에서도 떨어졌다)**"))
    say("")
    say("### 3-1. 🔬 소급값 — **탐색적 표기 전용 · 누적 분모에 넣지 않는다** (`PREREG_POST6.md` §2-1 ③)\n")
    say("| 글 | 고가 +15% |")
    say("|---|---|")
    say(f"| 4번째 6건(소급) | {PUB_H['post4'][0]}/6 = {PUB_H['post4'][0]/6*100:.1f}% |")
    say(f"| 5번째 6건(소급) | {PUB_H['post5'][0]}/6 = {PUB_H['post5'][0]/6*100:.1f}% |")
    say(f"| 6번째 10건(판정) | {PUB_H['post6'][0]}/10 = {PUB_H['post6'][0]/10*100:.1f}% |")
    say(f"| **7번째 {n7}건 — 판정 대상** | **{h_hits}/{n7} = {h_hits/n7*100:.1f}%** |")
    say("")
    say("🔴 **소급 2행은 판정에 쓰지 않는다** · **`P6-S1h` 의 누적은 6번째 글부터 시작한다.**")
    say("🔴 **`SEL-S1` 의 기각을 무르지 않는다** — `P6-S1h` 통과를 *「S1 이 측정자만 틀렸던 것」*으로 "
        "읽지 않는다(`PREREG_POST6.md` §2-1 ①이 금지한 독법).")
    say("")

    # ── §4. 특징 백분위 ─────────────────────────────────────────────────────
    say("## §4. 특징 9개 백분위 (창 안 일별 백분위의 «최댓값»)\n")
    rows7_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS)
               for nm, c, reg, _ in EXACT7]
    rows7_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4)
               for nm, c, reg, _ in EXACT7]
    rows6_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW6]
    rows5_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW5]
    rows4_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW4]
    rows4_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg in NEW4]

    feat_table(f"4-1. 7번째 글 `exact` {n7}건 — **판정 창**(거래일 {W_TDAYS}일)", rows7_t)
    feat_table(f"4-2. 7번째 글 `exact` {n7}건 — 대조 창(post4 구현 · 달력 {W_CAL_POST4}일)", rows7_c)
    feat_table(f"4-3. 6번째 글 10건 — 판정 창(거래일 {W_TDAYS}일) · **{DB_UPTO} 스냅샷 재계산**", rows6_t)
    feat_table(f"4-4. 5번째 글 6건 — 판정 창(거래일 {W_TDAYS}일) · **{DB_UPTO} 스냅샷 재계산**", rows5_t)
    feat_table(f"4-5. 4번째 글 6건 — 판정 창(거래일 {W_TDAYS}일) · **{DB_UPTO} 스냅샷 재계산**", rows4_t)
    feat_table(f"4-6. 4번째 글 6건 — 대조 창(달력 {W_CAL_POST4}일) · **{DB_UPTO} 스냅샷 재계산**", rows4_c)

    # ── §5. S2·S3·S4 판정 ───────────────────────────────────────────────────
    a7t = aggs(rows7_t)
    a7c = aggs(rows7_c)
    a6t = aggs(rows6_t)
    a5t = aggs(rows5_t)
    a4t = aggs(rows4_t)
    a4c = aggs(rows4_c)

    s2, s3, s4, s3_n, s3_nan = a7t
    say(f"## §5. `SEL-S2`·`SEL-S3`·`SEL-S4` 판정 (판정 창 = 거래일 {W_TDAYS}일 · 분모 = `exact` {n7})\n")
    say(f"| 예측 | 문언(동결) | 문턱 (출처) | 최소 n | **이번(`exact` {n7}건)** | 판정 | ⛔ 판정 불가 조건 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| **`SEL-S2`** | `거래대금/시총` 백분위 중앙 | >= 95 (값만 기록) · `PREREG_SELECTION.md` §7 "
        f"| 3 | **{fmt(s2)}** | {'✅ 충족' if s2 is not None and s2 >= 95 else '🟡 미달'} | "
        f"판정 건 < 3 (이번 {n7} ⇒ 미발동) |")
    say(f"| **`SEL-S3`** | `60일 최고종가 갱신` 백분위 중앙 | **< 90** (핵심·위반 시 기각) · "
        f"`PREREG_SELECTION.md` §7 | 3 | **{fmt(s3)}** (분모 {s3_n}/{n7} · NaN {s3_nan}) | "
        f"{'✅ 지지' if s3 is not None and s3 < 90 else '❌ 기각'} | 판정 건 < 3 · "
        f"**§5-1(C-17) 수정 전이면 무효** ⇒ {'반영 ✅' if c17_ok else '🔴 미반영'} |")
    say(f"| **`SEL-S4`** | `시가총액` 백분위 중앙 | 40~80 (값만 기록) · `PREREG_SELECTION.md` §7 | 3 | "
        f"**{fmt(s4)}** | {'✅ 구간 내' if s4 is not None and 40 <= s4 <= 80 else '🟡 구간 밖'} | "
        f"판정 건 < 3 (이번 {n7} ⇒ 미발동) |")
    say("")
    same_dir = (a7c[0] is not None and s2 is not None
                and (a7c[0] >= 95) == (s2 >= 95) and (a7c[1] < 90) == (s3 < 90)
                and (40 <= a7c[2] <= 80) == (40 <= s4 <= 80))
    say(f"대조 창(달력 {W_CAL_POST4}일) 값: S2 **{fmt(a7c[0])}** · S3 **{fmt(a7c[1])}** · "
        f"S4 **{fmt(a7c[2])}** — 판정 창과 "
        f"{'**같은 방향**' if same_dir else '🔴 **다른 방향 ⇒ 창 의존**'}. "
        "🔴 **판정은 동결 문언(거래일 5일)으로 선다.**")
    say("")
    say("### 5-1. 누적 — 🔴 **열마다 창·분모 규약이 다르다. 「4연속 재현」이라고 쓰지 않는다.**\n")
    say("| 예측 | 1~3번째(33건)<br>🔴 또 다른 창 | 4번째 발표<br>달력10 · 08-21 | "
        "4번째 재계산<br>거래일5 · **09-11** | 5번째 발표<br>거래일5 · 08-28 | "
        "5번째 재계산<br>거래일5 · **09-11** | 6번째 발표<br>거래일5 · 09-04 | "
        "6번째 재계산<br>거래일5 · **09-11** | **7번째**<br>거래일5 · **09-11** · `exact` 6 |")
    say("|---|---|---|---|---|---|---|---|---|")
    say(f"| S2 | {PUB_33[1]} | {PUB['post4_cal10'][2]:.1f} | {fmt(a4t[0])} | "
        f"{PUB['post5_td5'][2]:.1f} | {fmt(a5t[0])} | {PUB['post6_td5'][2]:.1f} | {fmt(a6t[0])} | "
        f"**{fmt(s2)}** |")
    say(f"| S3 | {PUB_33[2]} | {PUB['post4_cal10'][3]:.1f} | {fmt(a4t[1])} | "
        f"{PUB['post5_td5'][3]:.1f} | {fmt(a5t[1])} | {PUB['post6_td5'][3]:.1f} | {fmt(a6t[1])} | "
        f"**{fmt(s3)}** |")
    say(f"| S4 | {PUB_33[3]} | {PUB['post4_cal10'][4]:.1f} | {fmt(a4t[2])} | "
        f"{PUB['post5_td5'][4]:.1f} | {fmt(a5t[2])} | {PUB['post6_td5'][4]:.1f} | {fmt(a6t[2])} | "
        f"**{fmt(s4)}** |")
    say("")
    say("⚠️ **「33건」 열은 잣대가 또 다르다** — `run_selection.py` 의 **달력 6일** + 최대 15거래일. "
        "*「방향 참고로만 쓴다」*(`RESULTS_SELECTION_POST5.md` §0).")
    say("⚠️ **`PREREG_POST6.md` §2-1 이 금지한 표현**: *「N연속 재현」이라고 쓰지 않는다*. "
        "***표본이 매번 통째로 바뀌고 스냅샷·측정 장치(C-17)도 움직였으며, "
        "이번에는 «분모 규약»(신규 → `exact`)까지 갈렸다.***")
    say("")
    say("### 5-2. 🔴 재계산 대조 — 직전 발표값과 이번 스냅샷이 갈리는가\n")
    say(f"| 표본 | 창 | 예측 | 직전 발표값 | {DB_UPTO} 재계산 | 차 | 일치? | 비고 |")
    say("|---|---|---|---|---|---|---|---|")
    for tag, pubkey, agg, cw in (("4번째 글", "post4_td5", a4t, f"거래일{W_TDAYS}"),
                                 ("4번째 글", "post4_cal10", a4c, f"달력{W_CAL_POST4}"),
                                 ("5번째 글", "post5_td5", a5t, f"거래일{W_TDAYS}"),
                                 ("6번째 글", "post6_td5", a6t, f"거래일{W_TDAYS}")):
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
        f"5번째 **{a5t[3]}/6**(NaN {a5t[4]}) · 6번째 **{a6t[3]}/10**(NaN {a6t[4]})")
    say("")
    say("🔴 **과거 산출물을 다시 재지 않는다**(`PREREG_POST6.md` §5-1 5번): 값이 달라져도 "
        "**post4~post6 판정은 그대로 둔다.** 위 표는 「나란히 인쇄」 의무를 이행한 것이며 "
        "***과거 판정의 교체가 아니다.***")
    say("")

    # ── §5-3. approx 갈래 (창 규약 첫 발동 · 의무 민감도) ────────────────────
    say("### 5-3. 🟡 `approx` 2건 — **갈래별 인쇄**(의무 민감도 · PD-4 2번 · `PREREG_POST6.md` §1-4)\n")
    say("> 🔴 **값을 보고 한 갈래를 고르지 않는다.** 창 규약이 지시하는 «모든 거래일»을 갈래로 두고 "
        "전부 인쇄한 뒤, 조합 전체에서 판정이 갈리는지만 본다.\n")
    approx_stats = {}
    for nm, code, tag in APPROX7:
        label, lo, hi, days = APPROX_BRANCHES[nm]
        cal = [d for d in mdays if lo <= d <= hi]
        say(f"**{nm}** (`{code}`) — {label} = `[{lo}, {hi}]` · 동결 문서 갈래 **{len(days)}일** · "
            f"DB 거래일 달력 실측 **{len(cal)}일** ⇒ "
            + ("🟢 일치 (「창 규약 적용」)"
               if cal == days else f"🔴 **불일치** — DB: {cal} (고치지 않고 그대로 적는다)"))
        say("")
        say("| 갈래 `D` | `[D-19, D]` 봉수 | 창 `[D-4, D]` 봉수 | 종가 등락 | 고가 등락 | "
            "`f1` | `f9` | `f7` |")
        say("|---|---|---|---|---|---|---|---|")
        per = []
        for d in days:
            nb20, wlen = win20_bars(cur, mdays, code, d)
            st, nb5 = stat_tdays(df, code, pd.Timestamp(d), W_TDAYS)
            r = s1_row(raw, code, d)
            per.append((d, st, nb5))
            f1s = "—" if not st else fmt(st["f1_tv_mcap"])
            f9s = "—" if not st else fmt(st["f9_newhigh"])
            f7s = "—" if not st else fmt(st["f7_mcap"])
            say(f"| {d} | {nb20}/{wlen} | {nb5} | "
                f"{'—' if r is None else pct(r['ret_c'])} | "
                f"{'—' if r is None else pct(r['ret_h'])} | {f1s} | {f9s} | {f7s} |")
        say("")
        approx_stats[nm] = (code, per)

    say(f"#### 5-3-1. 조합 전체에서 판정이 갈리는가 (`exact` {n7} + `approx` {len(APPROX7)} = "
        f"{n7 + len(APPROX7)}건 · 전 갈래 조합)\n")
    keys = list(approx_stats)
    branch_lists = [approx_stats[k][1] for k in keys]
    combo_aggs = []
    for combo in itertools.product(*branch_lists):
        rows = list(rows7_t) + [(k, approx_stats[k][0], c[0], c[1], c[2])
                                for k, c in zip(keys, combo)]
        combo_aggs.append(aggs(rows))
    n_comb = len(combo_aggs)
    s2v = [a[0] for a in combo_aggs if a[0] is not None and a[0] == a[0]]
    s3v = [a[1] for a in combo_aggs if a[1] is not None and a[1] == a[1]]
    s4v = [a[2] for a in combo_aggs if a[2] is not None and a[2] == a[2]]
    say(f"- 갈래 조합 수 = {' x '.join(str(len(b)) for b in branch_lists)} = **{n_comb}**")
    say("")
    say(f"| 예측 | 문턱 | 주 판정(`exact` {n7}) | 조합 최소 | 조합 최대 | 판정이 갈리는가 |")
    say("|---|---|---|---|---|---|")
    flips_ap = []
    for lbl, thr_s, main_v, vals, test in (
            ("`SEL-S2`", ">= 95", s2, s2v, lambda v: v >= 95),
            ("`SEL-S3`", "< 90", s3, s3v, lambda v: v < 90),
            ("`SEL-S4`", "40~80", s4, s4v, lambda v: 40 <= v <= 80)):
        if not vals or main_v is None or main_v != main_v:
            say(f"| {lbl} | {thr_s} | {fmt(main_v)} | — | — | (계산 불가) |")
            continue
        verdicts = set(test(v) for v in vals)
        flip = (len(verdicts) > 1) or (test(main_v) not in verdicts)
        if flip:
            flips_ap.append(lbl)
        say(f"| {lbl} | {thr_s} | {fmt(main_v)} | {fmt(min(vals))} | {fmt(max(vals))} | "
            f"{'🔴 **갈린다**' if flip else '🟢 같다'} |")
    say("")
    if flips_ap:
        say(f"🔴🔴 **`approx` 갈래에서 판정이 갈린 항목 {len(flips_ap)}건**: " + " · ".join(flips_ap)
            + " ⇒ ***「등록일 정밀도 의존」으로 적고 어느 쪽도 «지지»로 선언하지 않는다*** "
              "(`RNK-D5`·`ANC` §2-3·`S5` §1-1 의 「주 표본은 `exact`」 규약 + "
              "`PREREG_POST6.md` §1-5 2번 민감도 문형).")
    else:
        say("🟢 **어느 항목도 갈리지 않는다** ⇒ 「등록일 정밀도 의존」 없음. "
            "⚠️ 단 이건 「`approx` 가 정확하다」가 아니라 **「집계가 안 뒤집힌다」**일 뿐이다.")
    say("🔴 **`approx` 건은 주 판정 분모에 넣지 않는다**(PD-4 1번) — 위 표는 **민감도**이고, "
        "***여기서 열린 값을 판정으로 승격하지 않는다.***")
    say("🔴 **`P6-W10`(무작위 «창» 귀무)은 이 레인이 아니라 `run_regday_post7.py` 가 인쇄한다** — "
        "§1-4 창 규약 용도이며 **`TV` 축의 `P6-W10` 미룸과 한 수로 합치지 않는다**(PD-6 · PD-4 2번).")
    say("")

    # ── §6. f9 원값·NaN ─────────────────────────────────────────────────────
    say("## §6. 🔴 `f9_newhigh` 원값·NaN — C-17 (`PREREG_POST6.md` §4 #5 「`f9` 원값 1 건수 의무 인쇄」)\n")
    say("| 종목 | 창 봉수 | `f9` 원값(창 최대) | 갱신일 | 등록일 당일도 갱신? | `f9` 백분위 | "
        "로드창 선행 봉수 | 상태 |")
    say("|---|---|---|---|---|---|---|---|")
    n_raw1 = n_nan = 0
    nan_names = []
    for nm, code, reg, st, nb in rows7_t:
        m = df[(df.stock_code == code) & (df.date <= pd.Timestamp(reg))].tail(W_TDAYS)
        raw_v = m["f9_newhigh"].max() if not m.empty else None
        n_prior = int(((df.stock_code == code) & (df.date < pd.Timestamp(reg))).sum())
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
    say(f"\n⇒ **`f9` 원값 = 1 인 건 {n_raw1}/{n7}** (4번째 0/6 · 5번째 2/6 · 6번째 2/10) · "
        f"**NaN(계산 불가) {n_nan}/{n7}**{' — ' + ' · '.join(nan_names) if nan_names else ''}")
    say(f"⇒ **`SEL-S3` 중앙값 분모 = {s3_n}/{n7}** "
        + ("(NaN 건이 없어 전 건이 들어갔다)" if s3_nan == 0 else f"(NaN {s3_nan}건이 빠졌다)"))
    say("")
    say("### 6-1. 🔴 해치텍 `0155E0` — **C-17 NaN 규약 대상 1건**(PD-12 · 신규 상장)\n")
    cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code='0155E0' "
                "AND date BETWEEN '2026-04-01' AND '2026-08-04'")
    ht_have = int(cur.fetchone()[0])
    cur.execute("SELECT count(DISTINCT date) FROM daily_prices WHERE date BETWEEN '2026-04-01' "
                "AND '2026-08-04' AND NOT (stock_code = ANY(%s))", (list(PSEUDO),))
    ht_days = int(cur.fetchone()[0])
    ht_nb20, ht_win = win20.get("해치텍", (0, 0))
    ht_prior = int(((df.stock_code == "0155E0") & (df.date < pd.Timestamp("2026-09-07"))).sum())
    ht_nan = "해치텍" in nan_names
    say("| 항목 | 값 | PD-12 예고 |")
    say("|---|---|---|")
    say(f"| 60봉 특징용 2026-04-01 ~ 08-04 봉 | **{ht_have}/{ht_days}** | 🔴 **0봉**(상장 전) |")
    say(f"| 창 `[D-19, D]` 봉수 (등록일 09-07 «포함») | **{ht_nb20}/{ht_win}** | 🔴 **10/20 = 절단** |")
    say(f"| 로드창(04-01~) 안 등록일 «직전» 봉수 | **{ht_prior}** (60봉 rolling `min_periods=20`) | — |")
    say("| `f9_newhigh` | **"
        + ("NaN ⇒ `SEL-S3` 분모 탈락" if ht_nan else "값 있음 ⇒ `SEL-S3` 분모에 «남는다»")
        + "** | C-17 NaN 규약 대상 **1건** |")
    say("")
    say("- 나머지 5건의 04-01~08-04 구간은 **85/85** 로 예고돼 있다(PD-12) — 실측은 §4 표와 "
        "위 로드창 봉수로 확인한다.")
    if ht_nan:
        say(f"- 🟢 PD-12 예고(*「해치텍은 0봉 ⇒ **C-17 NaN 규약 대상 1건** · `SEL-S3` 분모에서 빠질 수 "
            f"있다」*)와 **계산이 일치**한다 ⇒ `SEL-S3` 분모 = {s3_n}/{n7}.")
    else:
        say("- 🔴 PD-12 예고와 **다르다** — 해치텍의 `f9` 가 NaN 이 아니다. "
            "***그 사실을 그대로 적고 규약을 고치지 않는다.***")
    say("- 🔴 **한계(인쇄 의무)**: C-17 은 「완전 결측」만 잡고 「부분 결손」은 못 잡는다. "
        "선행 봉이 `min_periods=20` 을 넘으면 `f9` 는 계산되며, ***그 「60봉」은 달력 60거래일이 아니라 "
        "「DB 에 남아 있는 60행」이다.***")
    say("")

    # ── §7. P6-S1h-N + §5-2 유니버스 5열 ────────────────────────────────────
    say("## §7. `P6-S1h-N` (희소성 대칭 단언) + §5-2 유니버스 5열\n")
    say("> 문턱 **`n_up` 중앙 >= 30 ⇒ `P6-S1h` 는 「선정 규칙」으로 인용 금지(판별력 없음으로 강등)** "
        "— 출처 `PREREG_D1_OOS.md` §4 **N2**. ⛔ 판정 불가 조건 = `n_up` 계산 불가일(§5-2 결손).\n")
    say("| 종목 | 등록일 | `universe_mcap` | `universe_test` | `dropped` | `drop_rate` | "
        "`prev_bar_date` | **`n_up`** | 본인이 `n_up` 안에? | `n_up` 안 `f1` 순위 | 백분위 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    nups, drops, ranks = [], [], []
    ucache = {}
    for nm, code, reg, tag in EXACT7:
        if reg not in ucache:
            ucache[reg] = (universe_raw_count(cur, reg), load_universe_day(cur, reg))
        raw_n, rowsu = ucache[reg]
        kept = len(rowsu)
        drop = raw_n - kept
        rate = drop / raw_n if raw_n else float("nan")
        pds = sorted(set(str(r[6]) for r in rowsu if r[6] is not None))
        j = mdays.index(reg) if reg in mdays else None
        mkt_prev = mdays[j - 1] if j else "—"
        pd_s = pds[0] if len(pds) == 1 else f"{min(pds)}~{max(pds)} ({len(pds)}종)"
        if len(pds) > 1:
            pd_s += f" · 시장 직전 거래일 **{mkt_prev}**"
        up = [(sc, float(tv) / float(mc)) for sc, hi, cl, tv, mc, pc_, _pdt in rowsu
              if hi is not None and pc_ and float(hi) >= float(pc_) * UP15
              and tv is not None and mc]
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
    n_sd = float(np.std(nv, ddof=1)) if len(nv) > 1 else float("nan")
    degrade = n_med >= N_DEGRADE
    say("### 7-1. `P6-S1h-N` 판정\n")
    say("| 통계량 | 값 |")
    say("|---|---|")
    say(f"| `n_up` 중앙값 | **{n_med:.1f}** |")
    say(f"| `n_up` 범위 | **[{min(nv)}, {max(nv)}]** |")
    say(f"| `n_up` 표준편차(표본 · ddof=1) | **{n_sd:.2f}** |")
    say(f"| 문턱 | **>= {N_DEGRADE} ⇒ 인용 금지 강등** (`PREREG_D1_OOS.md` §4 N2) |")
    say("| **판정** | **" + ("🔴 발동 — `P6-S1h` 를 「선정 규칙」으로 «인용 금지»(판별력 없음으로 강등)"
                            if degrade else "🟢 미발동 — 희소성 단언이 살아 있다") + "** |")
    say("")
    say("계열 실측 대조: post5 **중앙 87 · 범위 47~93** · post6 **중앙 65.5 · 범위 [47, 86]** "
        f"⇒ 이번 중앙 **{n_med:.1f}**.")
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
    say(f"⇒ **1위인 건 {len(top1)}/{n7}**{(' — ' + ' · '.join(top1)) if top1 else ''} · "
        f"**`n_up` 집합 «밖»인 건 {len(outset)}/{n7}**"
        f"{(' — ' + ' · '.join(outset)) if outset else ''}")
    if len(top1) < n7:
        say("🔴 **저자 종목이 1위가 아닌 건이 있다** ⇒ ***「어느 급등주냐」는 여전히 미해결*** "
            "(`PREREG_POST6.md` §2-1 의무 문구).")
    say("")
    say("### 7-3. 죽은 가드 실측 점검 (`PREREG_POST6.md` §7-B #10)\n")
    say(f"`P6-S1h-N` 이 **상수를 재는가**: `n_up` 이 **{len(set(nv))}개의 서로 다른 값**을 가진다 "
        f"(범위 [{min(nv)}, {max(nv)}] · 표준편차 {n_sd:.2f}) ⇒ "
        + ("**🟢 상수가 아니다 — 가드는 살아 있다(장식이 아니다)**" if len(set(nv)) > 1
           else "**🔴 상수다 — 죽은 가드 후보**"))
    say("")

    # ── §8. 재진입 제외 민감도 ──────────────────────────────────────────────
    say("## §8. 🔂 재진입 제외 민감도 (**의무 인쇄** · `PREREG_POST6.md` §1-5 2번 · PD-3)\n")
    say("> 🔴🔴 **판정 분모 안 플래그 = 0.** `exact` 6 안의 재진입은 **빛과전자 1건**뿐이고 그 건의 "
        f"`P6-PRIOR_CYCLE_IN_WINDOW` = **{PD3_FLAG['빛과전자']}** "
        f"(직전 등록일 {PD3_PREV['빛과전자']} < 창 시작 2026-08-11 ⇒ **구성상 0**).\n")
    say("> 🔴 **글 전체 플래그 2건**(지투파워 · 한국화장품제조)은 **둘 다 `approx` 갈래**다(INTAKE §2-10) "
        "— ***판정 분모 안에 없다.*** 두 수를 한 칸에 합치지 않는다.\n")
    say("| 종목 | 정밀도 | 이번 등록일 | 직전 사이클 등록일 | **`P6-PRIOR_CYCLE_IN_WINDOW`** | "
        "판정 분모 안인가 |")
    say("|---|---|---|---|---|---|")
    for nm in ("지투파워", "한국화장품제조", "빛과전자"):
        prec = next(p for n2, c, d, p, t in NEW7 if n2 == nm)
        d0 = next(d for n2, c, d, p, t in NEW7 if n2 == nm)
        say(f"| {nm} | {'`exact`' if prec == 'exact' else '🟡 `approx`'} | "
            f"{d0 or APPROX_BRANCHES[nm][0]} | {PD3_PREV[nm]} | **{PD3_FLAG[nm]}** | "
            f"{'✅ 예' if prec == 'exact' else '🔴 아니다(민감도 갈래)'} |")
    say(f"\n⇒ **판정 분모(`exact` {n7}) 안 플래그 합 = "
        f"{sum(PD3_FLAG[n2] for n2 in REENTRY_EXACT)}** · "
        f"**글 전체 플래그 합 = {sum(PD3_FLAG.values())}**(둘 다 `approx`).")
    say("🔑 §1-5 3: ***이건 「제외」가 아니라 「이 건은 규칙상 통과할 수 없다」는 사실을 "
        "판정과 같은 무게로 인쇄하는 장치다.***")
    say("")
    keep = [r for r in rows7_t if r[0] not in REENTRY_EXACT]
    ak = aggs(keep)
    s1_keep = sum(1 for nm, _reg, r, _t in s1_rows
                  if nm not in REENTRY_EXACT and r and r["ret_c"] >= 0.15)
    h_keep = sum(1 for nm, _reg, r, _t in s1_rows
                 if nm not in REENTRY_EXACT and r and r["ret_h"] >= 0.15)
    nk = len(keep)
    nups_keep = [x[2] for x in nups if x[0] not in REENTRY_EXACT]
    med_keep = float(np.median(nups_keep))
    say(f"| 항목 | 문턱 | **`exact` {n7}건**(주 판정) | **재진입 제외 {nk}건**(민감도) | "
        "판정이 갈리는가 |")
    say("|---|---|---|---|---|")
    rows_sens = [
        ("`SEL-S1`(종가 +15%)", ">= 1/2",
         f"{s1_hits}/{n7} = {s1_hits/n7*100:.1f}%", f"{s1_keep}/{nk} = {s1_keep/nk*100:.1f}%",
         (s1_hits * 2 >= n7) != (s1_keep * 2 >= nk)),
        ("`P6-S1h`(고가 +15%)", ">= 1/2",
         f"{h_hits}/{n7} = {h_hits/n7*100:.1f}%", f"{h_keep}/{nk} = {h_keep/nk*100:.1f}%",
         (h_hits * 2 >= n7) != (h_keep * 2 >= nk)),
        ("`SEL-S2`", ">= 95", fmt(s2), fmt(ak[0]), (s2 >= 95) != (ak[0] >= 95)),
        ("`SEL-S3`", "< 90", fmt(s3), fmt(ak[1]), (s3 < 90) != (ak[1] < 90)),
        ("`SEL-S4`", "40~80", fmt(s4), fmt(ak[2]), (40 <= s4 <= 80) != (40 <= ak[2] <= 80)),
        ("`P6-S1h-N` `n_up` 중앙", f">= {N_DEGRADE} ⇒ 강등", f"{n_med:.1f}", f"{med_keep:.1f}",
         (n_med >= N_DEGRADE) != (med_keep >= N_DEGRADE)),
    ]
    flipped = []
    for lbl, thr, a, b, flip in rows_sens:
        if flip:
            flipped.append(lbl)
        say(f"| {lbl} | {thr} | {a} | {b} | {'🔴 **갈린다**' if flip else '🟢 같다'} |")
    say("")
    if flipped:
        say(f"🔴🔴 **판정이 갈린 항목 {len(flipped)}건**: " + " · ".join(flipped)
            + " ⇒ ***「재진입 의존」으로 적고 어느 쪽도 «지지»로 선언하지 않는다***"
              "(`PREREG_POST6.md` §1-5 2번 문언 그대로).")
    else:
        say("🟢 **어느 항목도 갈리지 않는다** ⇒ 「재진입 의존」 없음. "
            "⚠️ 단 이건 「재진입 건이 같다」가 아니라 **「집계가 안 뒤집힌다」**일 뿐이다.")
    say("")

    # ── §9. 절단 가드 ───────────────────────────────────────────────────────
    say("## §9. `P6-절단가드-A`/`B` (`PREREG_POST6.md` §1-6 · PD-12)\n")
    trunc = [(nm, v) for nm, v in win20.items() if v[0] < WIN20]
    frac = len(trunc) / n7
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 분모 | **`exact` {n7}건**(판정 분모) |")
    say(f"| 분자 = 창 `[D-19, D]` 봉수 **< {WIN20}** 인 건 | **{len(trunc)}**"
        f"{' — ' + ' · '.join(f'{nm} {v[0]}/{v[1]}' for nm, v in trunc) if trunc else ''} |")
    say(f"| 비율 | **{len(trunc)}/{n7} = {frac*100:.1f}%** |")
    say("| 문턱 | **>= 1/3 (33.3%) ⇒ ⛔ 판정 불가** |")
    say(f"| **`P6-절단가드-A`** | **{'🔴 발동 ⇒ ⛔ 판정 불가' if frac >= TRUNC_GUARD else '🟢 미발동'}** |")
    say("")
    say("🟢 PD-12 예고(*「분자 = **1**(해치텍 10/20) · 나머지 5건 20/20 ⇒ 1/6 = 16.7% < 1/3 ⇒ "
        "미발동」*)와 **" + ("계산이 일치" if len(trunc) == 1 else "🔴 다르다") + "**한다.")
    say("")
    say("### 9-1. 절단 제외 민감도 (**필수** · §1-6 2번)\n")
    say("> 🔴 **방향 자기신고**(PD-12 · §1-6 2번): *「창이 짧으면 「창 최고」가 되기 쉽다 ⇒ "
        "**관측에 «유리한» 방향**」*. 해치텍의 짧은 창은 우리 쪽에 유리하므로 "
        "***제외 민감도를 반드시 나란히 인쇄한다. 값을 보고 빼지 않는다(§1-6 1번).***\n")
    trunc_names = set(nm for nm, _v in trunc)
    keep_t = [r for r in rows7_t if r[0] not in trunc_names]
    at = aggs(keep_t) if keep_t else (None, None, None, 0, 0)
    s1_kt = sum(1 for nm, _reg, r, _t in s1_rows
                if nm not in trunc_names and r and r["ret_c"] >= 0.15)
    h_kt = sum(1 for nm, _reg, r, _t in s1_rows
               if nm not in trunc_names and r and r["ret_h"] >= 0.15)
    nkt = max(len(keep_t), 1)
    say(f"| 항목 | 문턱 | **전 건 {n7}**(주 판정) | **절단 제외 {len(keep_t)}**(민감도) | "
        "판정이 갈리는가 |")
    say("|---|---|---|---|---|")
    flips_t = []
    rows_tr = [
        ("`SEL-S1`", ">= 1/2", f"{s1_hits}/{n7}", f"{s1_kt}/{len(keep_t)}",
         (s1_hits * 2 >= n7) != (s1_kt * 2 >= nkt)),
        ("`P6-S1h`", ">= 1/2", f"{h_hits}/{n7}", f"{h_kt}/{len(keep_t)}",
         (h_hits * 2 >= n7) != (h_kt * 2 >= nkt)),
        ("`SEL-S2`", ">= 95", fmt(s2), fmt(at[0]),
         at[0] is not None and (s2 >= 95) != (at[0] >= 95)),
        ("`SEL-S3`", "< 90", fmt(s3), fmt(at[1]),
         at[1] is not None and (s3 < 90) != (at[1] < 90)),
        ("`SEL-S4`", "40~80", fmt(s4), fmt(at[2]),
         at[2] is not None and (40 <= s4 <= 80) != (40 <= at[2] <= 80)),
    ]
    for lbl, thr, a, b, flip in rows_tr:
        if flip:
            flips_t.append(lbl)
        say(f"| {lbl} | {thr} | {a} | {b} | {'🔴 **갈린다**' if flip else '🟢 같다'} |")
    say("")
    say("**`P6-절단가드-B`**(절단 제외 민감도가 판정을 뒤집으면 ⛔) = **"
        + (f"🔴 발동 — 뒤집힌 항목 {len(flips_t)}건: " + " · ".join(flips_t) if flips_t
           else "🟢 미발동 — 뒤집힌 항목 0건") + "**")
    say("")
    say("⚠️ **문턱 `1/3` 의 출처 = `REC-Y3` 에서 «차용»**(`RESULTS_RECONSTRUCT_POST4.md:119-121`) — "
        "***절단 비율에 대해 검증된 값이 아니다***(§1-6 6번 차용 고지 승계).")
    say("🔑 **봉수 표기 규약**(N8 승계): 창 봉수는 전부 **「등록일 «포함»」** 기준이다 — "
        "해치텍 **10봉 = 등록일 포함 10봉 = 직전 9봉**(PD-12).")
    say("")

    # ── §10. 판정 요약 ──────────────────────────────────────────────────────
    say("## §10. 판정 요약 — `PREREG_POST6.md` §4 #1~#6·#11 형식\n")
    say(f"| # | 항목 | 문턱 (출처 파일) | 최소 n | 값(`exact` {n7}) | **판정** | 대칭/반증 쌍 | "
        "⛔ 경로 · 민감도 |")
    say("|---|---|---|---|---|---|---|---|")
    say(f"| 1 | `SEL-S1` | >= 1/2 · `PREREG_SELECTION.md` §7 | 3 | "
        f"{s1_hits}/{n7} = {s1_hits/n7*100:.1f}% | "
        "❌ **기각 유지**(`PREREG_POST6.md` §2-1 · 부활 경로 없음) | `SEL-S3` | "
        f"판정 건 < 3(미발동) · 재진입 제외 {s1_keep}/{nk} · 절단 제외 {s1_kt}/{len(keep_t)} |")
    say(f"| 2 | `P6-S1h` | >= 1/2 · `PREREG_SELECTION.md` §7(상속) | 3 | "
        f"{h_hits}/{n7} = {h_hits/n7*100:.1f}% | "
        + ("🟡 **문턱 충족 — 단조 완화 축이라 «증거 아님»**" if h_pass else "❌ **불성립**")
        + " | `P6-S1h-N`(`n_up` 중앙 >= 30 → 강등) | "
        f"🔴 **통과는 증거 아님** · 재진입 제외 {h_keep}/{nk} · 절단 제외 {h_kt}/{len(keep_t)} |")
    say(f"| 3 | `P6-S1h-N` | >= {N_DEGRADE} → 인용 금지 · `PREREG_D1_OOS.md` §4 | — | "
        f"중앙 {n_med:.1f} · 범위 [{min(nv)}, {max(nv)}] · sd {n_sd:.2f} | "
        + ("🔴 **발동 ⇒ `P6-S1h` 인용 금지(강등)**" if degrade else "🟢 **미발동**")
        + " | 자신이 반증축 | "
        f"`drop_rate >= 1%` {len(bad_days)}일 · 재진입 제외 중앙 {med_keep:.1f} |")
    say(f"| 4 | `SEL-S2` | >= 95 · `PREREG_SELECTION.md` §7 | 3 | {fmt(s2)} | "
        + ("✅ **충족**" if s2 >= 95 else "🟡 **미달**")
        + f" | `SEL-S4` | 재진입 제외 {fmt(ak[0])} · 절단 제외 {fmt(at[0])} · "
          f"`approx` 조합 [{fmt(min(s2v)) if s2v else '—'}, {fmt(max(s2v)) if s2v else '—'}] |")
    say(f"| 5 | `SEL-S3` | **< 90** · `PREREG_SELECTION.md` §7 | 3 | {fmt(s3)} (분모 {s3_n}/{n7}) | "
        + ("✅ **지지**" if s3 < 90 else "❌ **기각**")
        + f" | `f9` 원값 1 건수 = **{n_raw1}/{n7}**(인쇄 완료) | "
          f"§5-1 수정 전이면 무효 ⇒ {'반영 ✅' if c17_ok else '🔴 미반영'} · "
          f"재진입 제외 {fmt(ak[1])} · 절단 제외 {fmt(at[1])} · "
          f"`approx` 조합 [{fmt(min(s3v)) if s3v else '—'}, {fmt(max(s3v)) if s3v else '—'}] |")
    say(f"| 6 | `SEL-S4` | 40~80 · `PREREG_SELECTION.md` §7 | 3 | {fmt(s4)} | "
        + ("✅ **구간 내**" if 40 <= s4 <= 80 else "🟡 **구간 밖**")
        + f" | `SEL-S2` | 재진입 제외 {fmt(ak[2])} · 절단 제외 {fmt(at[2])} · "
          f"`approx` 조합 [{fmt(min(s4v)) if s4v else '—'}, {fmt(max(s4v)) if s4v else '—'}] |")
    say(f"| 11 | `REG-M4` | 기록 · `PREREG_REGDAY_MEASURE.md` §4-4 | — | "
        f"`n_up` 중앙 {n_med:.1f} · 범위 [{min(nv)}, {max(nv)}] | 🟡 **기록만**(대칭 단언 · 판정 아님) | "
        "자신이 반증축 | §5-2 결손일 — 이 표의 `n_up` 은 `P6-S1h-N` 과 **같은 계산**이다 |")
    say("")
    say("🔴 **이 문서에서 처음 정한 문턱에 걸렸는가**(`PREREG_POST6.md` §9): "
        f"`drop_rate >= 1%` 가드 = **{'발동' if bad_days else '미발동'}** ⇒ "
        + ("🔴 **「이 문서에서 처음 정한 문턱에 걸렸다」고 적는다.**" if bad_days
           else "🟢 판정을 가르지 않았다."))
    say("")
    say("🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2). "
        "🔴 **`adj_factor` 를 곱하지도 나누지도 않았다**(프로젝트 SSOT 규약 · 원주가 그대로).")
    say(f"🔴 **창 종료 {DB_UPTO} = 발행일({PUB_DATE} 토) 휴장 ⇒ 마지막 거래일 · B-1(전 축 · "
        f"`WRC-` 포함)** · **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 = {snap_rows:,}**"
        "(기록 의무 · 창으로 쓰지 않는다 · PD-1 5번).")

    conn.close()
    (BASE / "RESULTS_SELECTION_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    note("")
    note(f"[written] RESULTS_SELECTION_POST7_NUMBERS.md · 런타임 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
