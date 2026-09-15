# -*- coding: utf-8 -*-
"""7번째 글 등록일 축 — `Q1-R2` · `P6-M1′` · `P6-M2′` · `P6-M3′` · `REG-M4` · `REG-M5`.

`run_regday_post6.py` 를 **승계**한 post7 판이다(원본은 손대지 않는다).
측정자·귀무·통계량(`per_stock`·`measure`·`null_p`·`bucket`·`gstar`·`null_gstar_a`·`null_gstar_b`·
`verdict_and`·`block`·`fmt_pct`)은 **import 해 그대로 재사용**한다(새 코드 0줄 원칙).

준거(전부 계산 «전» 동결):
  · `PREREG_POST6.md` §0-3(접두 표기) · §1-4(「N월 초/말」 창 규약) · §1-5(재진입)
    · §1-6(절단가드 A/B · 봉수 표기) · §2-2 · §3-1(`P6-M1′`) · §3-2(`P6-M2′`) · §3-3(`P6-M3′`)
    · §4 #7~#12 · §5-2(5열·drop_rate)
  · `PREREG_REGDAY_MEASURE.md` §4 · `PREREG_Q1_V2.md` §3 `R2` · `PREREG_D1_OOS.md` §4(`P6-W10` 상속)
  · `PREDECISION_2026-09-15_post7.md` PD-1(창 종료 = **2026-09-11**) · PD-2(후속 3건 분모 밖)
    · PD-3(재진입 3건 · 플래그) · PD-4(등록일 정밀도 · 창 규약 «첫 발동» · `P6-W10` 의무 인쇄)
    · PD-6(`TV` 축 `P6-W10` 은 «미룸» — 한 수로 합치지 않는다) · PD-11 · PD-12(절단 1건)
  · `INTAKE_2026-09-15_post7.md` §1(신규 10건) · §5

동결 문언 준수 사항:
  · 🔴 **판정 분모 = 신규 ∧ `reg_date_precision = exact` = 6건**(PD-4 1번) — 이 계열 최초로
    「신규」와 「`exact`」가 갈렸다. `approx` 2 는 **갈래별 의무 민감도**, `none` 2 + 후속 3 은 축 밖.
  · 창 `[D−19, D]` = **D 를 «포함»한 직전 20거래일** — 봉수는 반드시 「등록일 포함/직전」을 명시(§1-6 7)
  · 귀무 **시드 20260815 · 20,000 반복**(승계) · 이동창이 주(主) · 고정창은 **의무 민감도**
  · `P6-M1′` 결정규칙 = **비율 ≥ 0.8333 ∧ 귀무 백분위 < 5%** (AND) · 갈리면 🟡 부분 충족(인용 금지)
  · `P6-M2′` 전제 = **양 무리 각 ≥ 2건** — 못 채우면 **검정을 안 돌리고** 문언 그대로 ⛔ 를 적는다
  · `P6-M3′` 판정은 **중앙값 < 0.5** · 되밀림형 < 3 이면 ⛔ · 개별 실패가 **과반**이면 이름 인용 금지
  · `REG-M4` 는 **매회 재판정**(상수가 아니다) · `REG-M5` 는 **기록만**(판정 금지)
  · 🆕 **`P6-W10`(무작위 «창» 귀무)은 §1-4 창 규약 용도로 «의무 인쇄»**(PD-4 2번) —
    🔴 `TV` 축의 `P6-W10` 은 자가보고 0건이라 «미룬다»(PD-6). ***두 용도를 한 수로 합치지 않는다.***

🔴 이 산출물은 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).
🔴 결과 문서 안에서 **새 예측을 만들지 않는다**(`RESULTS_REGDAY_POST5.md` §10 처리 승계).
라이브 트리 import 0건. DB 는 SELECT 만. `adj_factor` 산술 0건.
시드·반복 고정이라 **두 번 실행하면 byte 동일**이다.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

# 🔴 새 코드 0줄 — post6 판의 측정자·귀무·표 포맷을 **그대로** 재사용한다(원본 불변).
#    출처: run_regday_post6.py:157(per_stock) :165(measure) :203(null_p) :226(bucket)
#          :231(gstar) :241(gstar_rows) :248(null_gstar_a) :253(null_gstar_b)
#          :266(fmt_pct) :270(verdict_and) :278(block)
#          :124(universe_raw_count) :133(prev_trading_day) :140(load_universe_day)
import run_regday_post6 as R6
from run_regday_post6 import (block, bucket, fmt_pct, gstar, load_universe_day,
                              measure, null_gstar_a, null_gstar_b, null_p,
                              prev_trading_day, universe_raw_count, verdict_and)
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DB_UPTO = "2026-09-11"       # PD-1: 발행일 09-12(토) 휴장 ⇒ 마지막 거래일. 창 종료 = 09-11.
PUB_DATE = "2026-09-12"      # 7번째 글 발행일(토요일 = 휴장)
WIN = 20                     # [D−19, D] = D 포함 20거래일
NREP = 20_000                # 사전등록 §4-1 승계: 시드 고정 20,000 반복
NULL_SEED = 20260815
EPS = 1e-6
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")
BAND_UP = 0.03               # 라이브 entry_band_up_pct (REG-M5 병기용)
UP_MULT = 1.15               # n_up 정의: 고가 ≥ 전일종가 × 1.15 (승계)
M1_RATIO = 5.0 / 6.0         # P6-M1′ 비율 문턱 0.8333 (§3-1)
R2_RATIO = 0.50              # Q1-R2 문턱 (PREREG_Q1_V2.md §3)
ALPHA = 0.05                 # 귀무 백분위 문턱
MIN_N = 3                    # 최소 n (판정 건)
MIN_PULL = 3                 # P6-M3′ 최소 n (되밀림형)
CLUSTER_MIN = 2              # P6-M2′ 전제 — 양 무리 각 ≥ 2
TRUNC_GUARD = 1.0 / 3.0      # P6-절단가드-A (§1-6 3 · REC-Y3 차용 고지)
DROP_GUARD = 0.01            # §5-2 drop_rate 가드 1%
NUP_CITE_BAN = 30            # REG-M4 재판정 문턱 (PREREG_POST6.md §4 #3 ← PREREG_D1_OOS.md §4 N2)
W10_DEGRADE = 0.50           # 🆕 P6-W10 강등 문턱 (RESULTS_D1_OOS_POST5.md §9 · TV-W7 상속)
LIMIT_UP = 0.29              # 상한가 «마감» 조작정의: 종가 등락 ≥ +29% (제도 상한 +30%)

# ── 🔴 판정 분모 = 7번째 글 «신규» 10건 중 `reg_date_precision = exact` **6건** (PD-4 1번) ──
#    후속 3건(한라캐스트·아난티·우리기술투자)은 PD-2 2번대로 등록일 축 분모에서 «제외»한다
#    (이중계상 금지 — 그 등록 사건은 post6 신규 분모에서 이미 계상됐다).
#    `none` 2건(한전기술·한전산업)은 **등록일 문장 자체가 없어** 축 밖이다(PD-4).
POST7_EXACT = [
    ("서산", "079650", "2026-09-03"),
    ("강동씨엔앨", "198440", "2026-09-03"),
    ("로보티즈", "108490", "2026-09-04"),
    ("해치텍", "0155E0", "2026-09-07"),
    ("빛과전자", "069540", "2026-09-08"),
    ("범한퓨얼셀", "382900", "2026-09-09"),
]
POST7_NONE = [("한전기술", "052690"), ("한전산업", "130660")]
POST7_FOLLOWUP = [("한라캐스트", "125490"), ("아난티", "025980"), ("우리기술투자", "041190")]

# 🆕 `PREREG_POST6.md` §1-4 창 규약 «첫 발동» (PD-4 2번 · 달력 실측을 옮겨 적은 값).
#    (종목, 코드, 저자 표기, 창 하한, 창 상한, 갈래 거래일 목록)
APPROX_BRANCHES = [
    ("지투파워", "388050", "「9월 초」", "2026-09-01", "2026-09-10",
     ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
      "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"]),
    ("한국화장품제조", "003350", "「8월 말」", "2026-08-21", "2026-08-31",
     ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
      "2026-08-27", "2026-08-28", "2026-08-31"]),
]

# PD-3 — 재진입 3건. 직전 «사이클의 등록일».
#    🔴 판정 분모(`exact` 6) 안의 재진입은 **빛과전자 1건**뿐이고 그 건의 플래그는 **0**
#      (직전 등록일 08-05 < 창 시작 08-11 ⇒ 구성상 0) ⇒ **판정 분모 안 플래그 = 0**.
#    🔴 글 전체 플래그 **2건**(지투파워·한국화장품제조)은 **둘 다 `approx` 갈래**다.
REENTRY = {"069540": "2026-08-05"}                   # 판정 분모 안 (빛과전자)
REENTRY_APPROX = {"388050": "2026-08-26", "003350": "2026-08-12"}
PD3_FLAG = {"069540": 0, "388050": 1, "003350": 1}   # PD-3 표가 «계산 전»에 못박은 값 — 대조용

# 참고 재계산(판정 대체 아님) — post6·post5·post4 신규 건
POST6 = [
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
POST5 = [
    ("혜인", "003010", "2026-08-11"),
    ("한국화장품제조", "003350", "2026-08-12"),
    ("코데즈컴바인", "047770", "2026-08-21"),
    ("한켐", "457370", "2026-08-20"),
    ("삼양바이오팜", "0120G0", "2026-08-21"),
    ("광전자", "017900", "2026-08-05"),
]
POST4 = [
    ("이노테크", "469610", "2026-08-13"),
    ("한켐", "457370", "2026-08-12"),
    ("금호건설", "002990", "2026-08-12"),
    ("지투파워", "388050", "2026-08-13"),
    ("PS일렉트로닉스", "332570", "2026-08-13"),
    ("코데즈컴바인", "047770", "2026-08-19"),
]
# RESULTS_REGDAY_POST6_NUMBERS.md:85 — post4 6/6 + post5 5/6 + post6 8/10 = 19/22 (대조용)
FROZEN_CUM = (19, 22)


def say(s=""):
    print(s)
    OUT.append(s)


# 🔴 post6 의 `block()` 은 «자기 모듈의» `say` 를 쓴다 ⇒ 그 버퍼를 이 실행의 버퍼로 잇는다
#    (`run_ladder_tranche_post6.py:74` 의 `LAD.OUT = OUT` 전례 그대로 · 원본 파일 불변).
R6.OUT = OUT

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


# ── DB (post6 승계 · 상단만 09-11 로 넓힌다) ────────────────────────────────
def load_prices(codes):
    conn = psycopg2.connect(**DSN)
    q = ("SELECT stock_code, date, open, high, low, close, trading_value, market_cap "
         "FROM daily_prices WHERE stock_code = ANY(%s) AND date BETWEEN '2026-01-01' "
         f"AND '{DB_UPTO}' AND close > 0 ORDER BY stock_code, date")
    df = pd.read_sql(q, conn, params=(list(codes),))
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def snapshot_tail(cur):
    """PD-1 5번 표기 의무 — 실행 시 `max(date)` 와 그 날짜 행수(창으로 쓰지 «않는다»)."""
    cur.execute("SELECT max(date) FROM daily_prices")
    mx = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (mx,))
    return str(mx), int(cur.fetchone()[0])


def market_days(cur, lo, hi):
    cur.execute(
        "SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s "
        "AND NOT (stock_code = ANY(%s)) ORDER BY date", (lo, hi, list(PSEUDO)))
    return [r[0] for r in cur.fetchall()]


def guard_a_fires(num, den):
    """`P6-절단가드-A` — 문턱은 **등호 포함**(≥ 1/3 · §1-6 5번)."""
    return den > 0 and num / den >= TRUNC_GUARD


def main():  # noqa: C901
    codes = sorted(set([c for _n, c, _d in POST7_EXACT + POST6 + POST5 + POST4]
                       + [c for _n, c, *_r in APPROX_BRANCHES]))
    df = load_prices(codes)

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    snap_max, snap_rows = snapshot_tail(cur)

    # ── 머리말 ──────────────────────────────────────────────────────────────
    say("# RESULTS_REGDAY_POST7_NUMBERS — 기계 생성 (수정 금지)\n")
    say("7번째 글 **등록일 축** — `Q1-R2` · `P6-M1′` · `P6-M2′` · `P6-M3′` · `REG-M4` · `REG-M5` "
        "· 🆕 `P6-W10`(§1-4 창 규약 용도)")
    say("준거 `PREREG_POST6.md` §1-4·§2-2·§3-1·§3-2·§3-3·§4 #7~#12·§5-2 · "
        "`PREREG_REGDAY_MEASURE.md` §4 · `PREREG_Q1_V2.md` §3 `R2` · `PREREG_D1_OOS.md` §4 · "
        "`PREDECISION_2026-09-15_post7.md` PD-1·PD-2·PD-3·PD-4·PD-6·PD-11·PD-12 · "
        "`INTAKE_2026-09-15_post7.md` §1·§5")
    say("생성 `run_regday_post7.py` (`run_regday_post6.py` 승계 · 측정자 import 재사용 · 원본 불변)\n")
    say(f"- DB `kis_template.daily_prices` 설정 `DB_UPTO = {DB_UPTO}` · "
        f"이 로드의 최신 봉 **{df.date.max().date()}**")
    say(f"- 🔴 **창 종료 {DB_UPTO} = 발행일({PUB_DATE} 토) 휴장 ⇒ 마지막 거래일 · "
        "B-1(전 축 · `WRC-` 포함)**(PD-1)")
    say(f"- 🔴 **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 = {snap_rows:,}** — "
        "PD-1 5번 표기 의무. ***창으로 쓰지 않는다.***")
    say(f"- 창 = `[D−19, D]` = **D 를 «포함»한 직전 {WIN}거래일** · 봉수는 전부 **등록일 포함** 셈 "
        "(§1-6 7 · `RESULTS_LADDER_TRANCHE.md` N8)")
    say(f"- 귀무 반복 **{NREP:,}** · 시드 **{NULL_SEED}** ⇒ 두 번 실행하면 **byte 동일**")
    say("- 라벨은 **축 접두**로 부른다(§0-3): `Q1-`·`P6-`·`REG-`. 접두 없는 맨 라벨은 인용이 아니다.")
    say("- 🔴 **이 산출물은 라이브 채택 대상이 아니다**(`PREREG.md` §0-2).")
    say("- 🔴 **`adj_factor` 를 곱하지도 나누지도 않았다**(프로젝트 SSOT 규약).")
    say("- 🔴 **이 문서 안에서 새 예측을 만들지 않는다**(`RESULTS_REGDAY_POST5.md` §10 처리 승계).\n")
    say(f"> 🔴🔴 **판정 분모 = 신규 ∧ `exact` = {len(POST7_EXACT)}건**(PD-4 1번). "
        f"이 계열 최초로 **신규 10 != `exact` {len(POST7_EXACT)}** 로 갈렸다 — "
        "`RNK-D5` · `PREREG_ANCHOR_REDESIGN.md` §2-3 · `PREREG_S5_FUND_NEWS_OOS.md` §1-1 "
        "세 동결본이 **같은 규칙**(*「판정 분모 = `exact` 만 · `approx` 는 의무 민감도」*)을 "
        "이미 동결해 두었다.\n"
        f"> 🔴 `approx` **2건**(지투파워 · 한국화장품제조)은 **§4 갈래별 민감도**이고, "
        f"`none` **{len(POST7_NONE)}건**(한전기술 · 한전산업) + 후속 **{len(POST7_FOLLOWUP)}건**"
        "(한라캐스트 · 아난티 · 우리기술투자)은 **등록일 축 밖**이다(PD-2 · PD-4).\n"
        "> 🟢 코드 13/13 DB 존재(PD-11) ⇒ post5 레메디형 결손 0. "
        "🔴 단 해치텍(`0155E0`)은 **신규 상장**이라 창이 절단된다(PD-12 · §2-4).\n")

    # ── §0. 분모·플래그 ─────────────────────────────────────────────────────
    say("## 0. 분모 · 재진입 플래그 · 창 봉수\n")
    r7 = measure(df, POST7_EXACT)
    say("| 종목 | 코드 | 등록일 | 창 시작(D−19) | 창 봉수(**D 포함**) | D **이전** 봉수 | "
        "재진입 | 직전 사이클 등록일 | **`P6-PRIOR_CYCLE_IN_WINDOW`** |")
    say("|---|---|---|---|---|---|---|---|---|")
    flags, flag_mismatch = {}, []
    for r in r7:
        if not r["ok"]:
            say(f"| {r['name']} | {r['code']} | {r['reg']} | — | — | — | — | — | (봉 없음) |")
            continue
        if r["code"] in REENTRY:
            pr = REENTRY[r["code"]]
            fl, prev_s = (1 if pr in r["win_dates"] else 0), pr
        else:
            fl, prev_s = 0, "—"
        flags[r["code"]] = fl
        if r["code"] in PD3_FLAG and PD3_FLAG[r["code"]] != fl:
            flag_mismatch.append((r["name"], PD3_FLAG[r["code"]], fl))
        say(f"| {r['name']} | {r['code']} | {r['reg']} | {r['win_start']} | {r['nwin']} | "
            f"{r['nwin'] - 1} | {'🔂 **예**' if r['code'] in REENTRY else '아니오'} | {prev_s} | "
            f"**{fl}** |")
    n_flag = sum(flags.values())
    say("")
    say(f"⇒ 🔴🔴 **판정 분모 안 `P6-PRIOR_CYCLE_IN_WINDOW` = 1 인 건 {n_flag}건** "
        "(§1-5 3 의무 인쇄) — 판정 분모 안 재진입은 **빛과전자 1건**뿐이고 그 건의 플래그가 "
        f"**{PD3_FLAG['069540']}** 이다(직전 등록일 {REENTRY['069540']} < 창 시작 ⇒ **구성상 0**).")
    say(f"⇒ 🔴 **글 전체 플래그 = {PD3_FLAG['388050'] + PD3_FLAG['003350']}건** "
        "(지투파워 · 한국화장품제조) — ***둘 다 `approx` 갈래라 판정 분모 «안에 없다»***"
        "(INTAKE §2-10). **두 수를 한 칸에 합치지 않는다.**")
    say("🔑 §1-5 3: ***이건 「제외」가 아니다 — 「이 건은 규칙상 통과할 수 없다」는 사실을 "
        "판정과 같은 무게로 인쇄하는 장치다.***")
    if flag_mismatch:
        for nm, want, got in flag_mismatch:
            say(f"🔴 **PD-3 표와 불일치**: {nm} — 문서 {want} ↔ 계산 {got}")
    else:
        say(f"🟢 PD-3 표(빛과전자 {PD3_FLAG['069540']})와 **계산값이 일치**한다.")
    say("🔴 **재진입 3건 중 2건이 `approx`** 라 「재진입 제외 민감도」와 「`approx` 제외 민감도」가 "
        "겹친다(PD-3 말미) ⇒ ***두 민감도를 «따로» 인쇄하고 합치지 않는다***(§2-3 · §4).")
    say("")

    # ── §1. Q1-R2 / P6-M1′ 관측 ────────────────────────────────────────────
    say("## 1. `Q1-R2` · `P6-M1′` 관측 — 등록일 **고가** == `[D−19, D]` 최고 고가\n")
    r6 = measure(df, POST6)
    r5 = measure(df, POST5)
    r4 = measure(df, POST4)
    h7, n7 = block(f"1-1. 7번째 글 `exact` {len(POST7_EXACT)}건 (**판정 표본**)", r7, "7번째 글 `exact`")
    h6, n6 = block(f"1-2. 6번째 글 10건 — {DB_UPTO} 스냅샷 재계산 (참고 · 판정 대체 아님)",
                   r6, "6번째 글(재계산)")
    h5, n5 = block(f"1-3. 5번째 글 6건 — {DB_UPTO} 스냅샷 재계산 (참고 · 판정 대체 아님)",
                   r5, "5번째 글(재계산)")
    h4, n4 = block(f"1-4. 4번째 글 6건 — {DB_UPTO} 스냅샷 재계산 (참고 · 판정 대체 아님)",
                   r4, "4번째 글(재계산)")
    say(f"⇒ **재계산 과거 {n6 + n5 + n4}건 = {h6 + h5 + h4}/{n6 + n5 + n4} = "
        f"{(h6 + h5 + h4)/(n6 + n5 + n4)*100:.1f}%**")
    say(f"⇒ 동결 누적(`RESULTS_REGDAY_POST6_NUMBERS.md`) **{FROZEN_CUM[0]}/{FROZEN_CUM[1]}** + "
        f"이번 {h7}/{n7} = **{FROZEN_CUM[0] + h7}/{FROZEN_CUM[1] + n7} = "
        f"{(FROZEN_CUM[0] + h7)/(FROZEN_CUM[1] + n7)*100:.1f}%**")
    same = (h6 + h5 + h4 == FROZEN_CUM[0]) and (n6 + n5 + n4 == FROZEN_CUM[1])
    say(f"⇒ 재계산 {n6 + n5 + n4}건 = {h6 + h5 + h4}/{n6 + n5 + n4} · "
        f"동결값 {FROZEN_CUM[0]}/{FROZEN_CUM[1]} ⇒ "
        + ("🟢 **일치** — 스냅샷 이동(09-04 → 09-11)이 과거 등록일 측정치를 바꾸지 않았다"
           if same else "🔴 **불일치 — 스냅샷 이동이 과거 값을 바꿨다(조사 대상)**"))
    say("🔴🔴 **누적 분모 규약이 이 글에서 갈린다** — post4~6 은 「신규 = `exact`」라 두 정의가 같은 "
        f"수였다. post7 은 신규 10 != `exact` {n7} 이다. ***위 누적은 `exact` 기준이며, "
        "「신규 10」 기준으로 다시 세지 않는다*** (동결 문언이 지시한 쪽이 `exact` 다 — PD-4 1번).\n")

    miss = [r for r in r7 if r["ok"] and not r["hit"]]
    say("### 1-5. ❌ 건 — 창 최고 고가를 «어느 날»이 잡았나 (기술 · 판정 아님)\n")
    if not miss:
        say("불일치 건 **0**.\n")
    else:
        say("| 종목 | 등록일 | 등록일 고가 | 창 최고 고가 | 그 고가를 낸 날 | "
            "직전 사이클 등록일과 같은 날? |")
        say("|---|---|---|---|---|---|")
        for r in miss:
            pr = REENTRY.get(r["code"])
            same_s = ("—(재진입 아님)" if r["code"] not in REENTRY else
                      ("✅ 같다" if pr in r["argmax_dates"] else
                       f"❌ **아니다** — 직전 사이클 등록일 {pr}"))
            say(f"| {r['name']} | {r['reg']} | {r['high']:,.0f} | {r['win_max_high']:,.0f} | "
                f"{' · '.join(r['argmax_dates'])} | {same_s} |")
        say("\n🔴 post5 코데즈컴바인의 기전(*「재진입 건은 구조적으로 «자기 첫 사이클의 고가»에 막힌다」* "
            "`RESULTS_REGDAY_POST5.md` §7-1)이 이번에도 «같은 모양»인지는 이 표로만 말한다 — "
            "**플래그 `P6-PRIOR_CYCLE_IN_WINDOW = 1` 은 「직전 사이클 등록일이 창 안에 있다」는 "
            "사실일 뿐, 「그 날의 고가가 막았다」는 뜻이 아니다.**\n")

    say("### 1-6. `Q1-R2` 판정\n")
    obs7 = h7 / n7
    say("| 예측 | 출처 파일·절 | 문언·문턱 | 최소 n | 관측 | 판정 | ⛔ 판정 불가 조건 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| **`Q1-R2`** | `PREREG_Q1_V2.md` §3 | 등록일 `exact` 건의 **≥ 50%** | {MIN_N} | "
        f"**{h7}/{n7} = {obs7*100:.1f}%** | {'✅ 지지' if obs7 >= R2_RATIO else '⛔ 불성립'} | "
        f"등록일 `exact` 건 < {MIN_N} ⇒ 이번 분모 {n7} ⇒ **미발동** |")
    say(f"\n- 🔴 대칭/반증 쌍 = **`REG-M4`**(§5) — `Q1-R2` 가 지지돼도 `n_up` 이 크면 "
        "「어느 급등주냐」는 못 말한다.")
    say("- 🔑 동결 문언이 *「등록일 `exact` 건」*이라 적혀 있다 — **이번 글에서 그 문언이 "
        "「신규」와 처음 갈렸고, 문언이 지시한 `exact` 를 쓴다**(PD-4 1번).\n")

    # ── §2. P6-M1′ ──────────────────────────────────────────────────────────
    say("## 2. `P6-M1′` — 비율 ∧ 귀무 (AND · `PREREG_POST6.md` §3-1)\n")
    ok7 = [r for r in r7 if r["ok"]]
    res = {}
    for mode, label in (("move", "**이동창**(§2 문언 「창이 뽑은 날에 함께 이동」) — **주 판정**"),
                        ("fixed", "고정창(뽑은 날과 무관하게 `[D−19,D]` 최고) — **의무 민감도**")):
        rng = np.random.default_rng(NULL_SEED)
        obs, p, ratios, per = null_p(ok7, rng, mode)
        res[mode] = (obs, p)
        say(f"### 2-{'1' if mode == 'move' else '2'}. {label}\n")
        say("| 종목 | 창봉수(**D 포함**) | 그 창에서 「그날이 창 최고」인 날 비율 |")
        say("|---|---|---|")
        for r, v in zip(ok7, per):
            say(f"| {r['name']} | {r['nwin']} | {v*100:.1f}% |")
        say("")
        say(f"- 관측 비율 **{obs*100:.1f}%** · 귀무 평균 **{ratios.mean()*100:.1f}%** · "
            f"귀무 중앙 **{np.median(ratios)*100:.1f}%** · 귀무 최대 **{ratios.max()*100:.1f}%**")
        say(f"- **p = P(귀무 비율 ≥ 관측) = {p:.5f}** ({int(round(p*NREP)):,}/{NREP:,})")
        say(f"- 귀무 백분위 < {ALPHA:.0%} ⇒ **{'충족' if p < ALPHA else '미달'}**\n")

    p_move, p_fixed = res["move"][1], res["fixed"][1]
    split_null = (p_move < ALPHA) != (p_fixed < ALPHA)

    say("### 2-3. 재진입 제외 민감도 (§1-5 2 · 의무 · 🔴 `approx` 민감도와 «따로» 인쇄)\n")
    sub_all = [r for r in ok7 if r["code"] not in REENTRY]
    sub_flag = [r for r in ok7 if flags.get(r["code"], 0) == 0]
    sens = {}
    say("| 표본 | n | 일치 | 비율 | 이동창 p | 고정창 p | 비율 ≥ 83.33% | `P6-M1′` |")
    say("|---|---|---|---|---|---|---|---|")
    for tag, sub in (("전 건(주 판정)", ok7),
                     ("재진입 1건 제외(빛과전자)", sub_all),
                     ("플래그=1 건만 제외(참고)", sub_flag)):
        if not sub:
            say(f"| {tag} | 0 | — | — | — | — | — | (표본 없음) |")
            continue
        hh = sum(1 for r in sub if r["hit"])
        rt = hh / len(sub)
        pm = null_p(sub, np.random.default_rng(NULL_SEED), "move")[1]
        pf = null_p(sub, np.random.default_rng(NULL_SEED), "fixed")[1]
        sens[tag] = (rt, pm, pf)
        say(f"| {tag} | {len(sub)} | {hh} | **{rt*100:.1f}%** | {pm:.5f} | {pf:.5f} | "
            f"{'✅' if rt >= M1_RATIO else '❌'} | {verdict_and(rt >= M1_RATIO, pm < ALPHA)} |")
    v_main = verdict_and(sens["전 건(주 판정)"][0] >= M1_RATIO, p_move < ALPHA)
    v_reent = verdict_and(sens["재진입 1건 제외(빛과전자)"][0] >= M1_RATIO,
                          sens["재진입 1건 제외(빛과전자)"][1] < ALPHA)
    split_reentry = v_main != v_reent
    say(f"\n⇒ 재진입 제외로 판정이 **"
        + ("🔴 갈린다 ⇒ 「재진입 의존」 — 어느 쪽도 지지로 선언하지 않는다" if split_reentry
           else "🟢 갈리지 않는다") + "**")
    say(f"🔑 **「플래그=1 건만 제외」 갈래는 이번에 «전 건»과 같다** — 판정 분모 안 플래그가 "
        f"**{n_flag}** 이기 때문이다(구성상 항등 = 판별력 0). 그 사실을 그대로 적는다.\n")

    say("### 2-4. `P6-절단가드-A`/`B` (§1-6 3·4 · 산술 인쇄 · PD-12)\n")
    trunc = [r for r in ok7 if r["nwin"] < WIN]
    fires = guard_a_fires(len(trunc), len(ok7))
    say(f"- 절단 건(창 봉수 **< {WIN}봉**, 등록일 포함 셈) = **{len(trunc)}건**"
        + (" — " + " · ".join(f"{r['name']} {r['nwin']}/{WIN}" for r in trunc) if trunc else "")
        + f" / 분모 `exact` {len(ok7)}건 = **{len(trunc)/len(ok7)*100:.1f}%**")
    say(f"- `P6-절단가드-A`: {len(trunc)}/{len(ok7)} = {len(trunc)/len(ok7)*100:.1f}% "
        f"{'≥' if fires else '<'} 1/3 = 33.33% ⇒ **{'⛔ 판정 불가' if fires else '미발동'}**")
    say("- 🟢 PD-12 예고(*「분자 = **1**(해치텍 10/20 · 첫 봉 08-25 = 상장일) · 나머지 5건 20/20 ⇒ "
        "1/6 ≈ 16.7% < 1/3 ⇒ 미발동」*)와 **"
        + ("계산이 일치" if len(trunc) == 1 else "🔴 다르다") + "**한다.")
    say("- 🔴 **방향 자기신고**(PD-12 · §1-6 2번): *「창이 짧으면 「창 최고」가 되기 쉽다 ⇒ "
        "**`Q1-R2`·`P6-M1′` 관측에 «유리한» 방향**」* ⇒ **절단 제외 민감도는 «필수»**이며, "
        "***값을 보고 빼지 않는다(§1-6 1번).***")
    if trunc:
        sub_t = [r for r in ok7 if r["nwin"] == WIN]
        ht = sum(1 for r in sub_t if r["hit"])
        rt = ht / len(sub_t)
        pt = null_p(sub_t, np.random.default_rng(NULL_SEED), "move")[1]
        v_tr = verdict_and(rt >= M1_RATIO, pt < ALPHA)
        r2_tr = ht / len(sub_t)
        say(f"- `P6-절단가드-B`: 절단 제외 {ht}/{len(sub_t)} = {rt*100:.1f}% · p={pt:.5f} ⇒ {v_tr} · "
            f"주 판정 {v_main} ⇒ **{'⛔ 판정 불가(뒤집힘)' if v_tr != v_main else '미발동'}**")
        say(f"- (대칭) `Q1-R2` 절단 제외 = {ht}/{len(sub_t)} = {r2_tr*100:.1f}% ⇒ "
            f"{'✅ 지지' if r2_tr >= R2_RATIO else '⛔ 불성립'} · 주 판정 "
            f"{'✅ 지지' if obs7 >= R2_RATIO else '⛔ 불성립'} ⇒ "
            f"**{'🔴 갈린다' if (r2_tr >= R2_RATIO) != (obs7 >= R2_RATIO) else '🟢 같다'}**")
        split_trunc = v_tr != v_main
    else:
        say(f"- `P6-절단가드-B`: 절단 건이 **0** 이므로 제외 표본 = 전 표본 ⇒ "
            "**뒤집힐 여지가 없다 · 미발동**")
        split_trunc = False
    say("- 🔴 문턱 `1/3` 은 `REC-Y3`(`RESULTS_RECONSTRUCT_POST4.md`)에서 **차용**한 값이며 "
        "**절단 비율에 대해 검증된 값이 아니다**(§1-6 6 고지 승계).")
    say("- 🔑 **봉수 표기 규약**(§1-6 7 · N8): 해치텍 = **등록일 포함 10봉 = 등록일 직전 9봉**.")
    say("")

    say("### 2-5. `P6-M1′` 종합 판정\n")
    say("| 항목 | 문언·문턱 (출처 파일·절) | 최소 n | 관측 | 판정 |")
    say("|---|---|---|---|---|")
    say(f"| 비율 | **≥ 5/6 = {M1_RATIO*100:.2f}%** · `PREREG_POST6.md` §3-1 | {MIN_N} | "
        f"**{obs7*100:.1f}%** | {'✅ 충족' if obs7 >= M1_RATIO else '❌ 미달'} |")
    say(f"| 귀무(이동창 · 주) | 백분위 **< 5%** · `PREREG_REGDAY_MEASURE.md` §4-1 | — | "
        f"**p={p_move:.5f}** | {'✅ 충족' if p_move < ALPHA else '❌ 미달'} |")
    say(f"| 귀무(고정창 · 민감도) | 두 갈래가 갈리면 ⛔ · `PREREG_POST6.md` §3-1 | — | "
        f"**p={p_fixed:.5f}** | {'🔴 갈림' if split_null else '🟢 같음'} |")
    # 🔴 §2-5 의 «선언»은 두 의존(재진입 · 등록일 정밀도)을 «둘 다» 보고 내려야 한다.
    #    정밀도 민감도의 «인쇄»는 §4-4 지만 계산은 부수효과가 없으므로 여기서 미리 한다 —
    #    같은 `measure`·같은 갈래를 쓰고, §4-4 가 다시 계산한 값과 **일치를 단언**한다.
    _pre_meas = {nm: measure(df, [(nm, code, d) for d in days])
                 for nm, code, _lab, _lo, _hi, days in APPROX_BRANCHES}
    _pre_combos = list(itertools.product(*[[r for r in _pre_meas[nm] if r["ok"]]
                                           for nm, *_x in APPROX_BRANCHES]))
    _pre_m1 = [sum(1 for r in list(ok7) + list(c) if r["hit"]) / (len(ok7) + len(c))
               for c in _pre_combos]
    prec_dep = bool(_pre_m1) and (
        len({v >= M1_RATIO for v in _pre_m1}) > 1
        or ((obs7 >= M1_RATIO) not in {v >= M1_RATIO for v in _pre_m1}))

    blocked = []
    if len(ok7) < MIN_N:
        blocked.append("① 판정 건 < 3")
    if fires:
        blocked.append("② `P6-절단가드-A`")
    if split_trunc:
        blocked.append("③ `P6-절단가드-B`")
    if split_null:
        blocked.append("④ 두 귀무 갈래가 갈림")
    if blocked:
        say(f"\n⇒ ⛔ **판정 불가** — 발동한 조건: {' · '.join(blocked)}")
    else:
        say(f"\n⇒ 🔒 **결정규칙 «비율 ≥ 0.8333 ∧ 귀무 백분위 < 5%» 자체는 충족됐다 "
            f"— {v_main}**(🔴 **«기록»이고 «선언»이 아니다** — 아래 의존 단서를 «먼저» 읽는다).")
        say("⇒ ⛔ 판정 불가 조건 ①~④ **전부 미발동**"
            f"(① {len(ok7)} ≥ {MIN_N} · ② 절단 {len(trunc)}건 · ③ 뒤집힘 없음 · ④ 두 갈래 동일)")
    _deps = []
    if split_reentry:
        _deps.append("**재진입 의존**(§1-5 2 · 이 절의 민감도 표)")
    if prec_dep:
        _deps.append("**등록일 정밀도 의존**(§4-4 `approx` 갈래에서 판정이 갈린다)")
    if _deps:
        say("")
        say("⇒ 🔴🔴 **`P6-M1′` 판정 = 「선언 없음」** — "
            + " ∧ ".join(_deps)
            + ". 동결 `PREREG_POST6.md` §1-5 2(`:283-284`)가 *「두 값이 **판정을 가르면** ⇒ "
              "🔴 「재진입 의존」으로 적고 **어느 쪽도 지지로 선언하지 않는다**」*고 못박는다. "
              "🔑 ***그러므로 이 항목의 «선두 기호»는 ✅ 가 아니다*** — "
              "결정규칙 충족은 위 줄에 «기록»으로만 남는다.")
        say("🔴 **인용 금지 문장**: *「`P6-M1′` 이 지지됐다」* · *「등록일 고가 = 20일 최고가가 "
            "확인됐다」*. ⚠️ 여기에 `REG-M4` 발동(§6)이 **하나 더** 겹친다 — 세 단서를 "
            "**같이** 달지 않으면 인용하지 않는다.")
    say("")
    say("### 2-6. 🔴 인용 시 반드시 붙일 단서 (§3-1 · 필수)\n")
    say("> ***「등록일 고가 = 최근 20거래일 최고 고가」와 「등록일이 급등일」은 같은 진술이 아니다***"
        "(`RESULTS_REGDAY_POST5.md` §5-1-②).")
    say("⇒ **`REG-M1`(및 그 승계 `P6-M1′`)은 「급등일 등록」이 아니다.** 재는 것은 «국소 신고가»다 — "
        "post5 한켐은 고가 등락 **+4.61%** 로도 통과했다. 아래 §5 의 「본인이 `n_up` 안에?」 열로 "
        "이번 글에서도 매회 확인한다.\n")

    # ── §3. P6-M2′ ──────────────────────────────────────────────────────────
    say("## 3. `P6-M2′` — 진짜 이분성 검정 (`PREREG_POST6.md` §3-2)\n")
    say("### 3-1. 건별 `r = C/H − 1` · 무리 분류 · 경계 근접성\n")
    say("| 종목 | 등록일 | **`r = C/H − 1`** | 분류 | `−5%` 경계까지(%p) | `−1%` 경계까지(%p) | "
        "종가 등락 | 상한가 마감? |")
    say("|---|---|---|---|---|---|---|---|")
    for r in ok7:
        b = bucket(r["r"])
        d5 = (r["r"] - (-0.05)) * 100
        d1 = (r["r"] - (-0.01)) * 100
        lim = (r["ret_c"] >= LIMIT_UP) if r["ret_c"] == r["ret_c"] else False
        say(f"| {r['name']} | {r['reg']} | **{r['r']:+.2%}** | {b} | {d5:+.2f} | {d1:+.2f} | "
            f"{fmt_pct(r['ret_c'])} | {'🔴 **예**' if lim else '아니오'} |")
    b7 = [bucket(r["r"]) for r in ok7]
    n_ceil, n_pull, n_mid = b7.count("상한가형"), b7.count("되밀림형"), b7.count("🔴 중간대")
    say(f"\n⇒ 상한가형 **{n_ceil}** · 되밀림형 **{n_pull}** · 중간대 **{n_mid}** (분모 {len(ok7)})")
    say("🔑 경계 근접성은 **판정과 같은 무게로** 적는다(§3-2) — post5 광전자는 **0.74%p** 짜리였다"
        "(*「60원짜리 결론이다」*). 위 표의 두 열이 그 자리다.")
    tight = min(ok7, key=lambda r: min(abs(r["r"] + 0.05), abs(r["r"] + 0.01)))
    say(f"⇒ 가장 아슬아슬한 건 = **{tight['name']}** — 두 경계 중 가까운 쪽까지 "
        f"**{min(abs(tight['r'] + 0.05), abs(tight['r'] + 0.01))*100:.2f}%p**\n")

    say("### 3-2. 전제 판정 — **양 무리 각 ≥ 2건** (없으면 검정 자체를 안 돌린다)\n")
    prem = (n_ceil >= CLUSTER_MIN) and (n_pull >= CLUSTER_MIN)
    say(f"- 전제(`PREREG_POST6.md` §3-2): 상한가형 ≥ {CLUSTER_MIN} **그리고** "
        f"되밀림형 ≥ {CLUSTER_MIN}")
    say(f"- 관측: 상한가형 **{n_ceil}** · 되밀림형 **{n_pull}** ⇒ "
        + ("**🟢 충족 — 검정을 돌린다**" if prem else "**⛔ 미충족 — 검정을 돌리지 않는다**"))
    say(f"- 최소 n(판정 건) {MIN_N} ⇒ 분모 {len(ok7)} ⇒ "
        + ("충족" if len(ok7) >= MIN_N else "🔴 미달"))
    say("- 🔑 §3-2: ***한 무리가 1건 이하면 「무리」가 아니라 「점」이다.*** "
        "문턱 2 의 근거는 이 정의뿐이며 **관측값과 무관**하다.\n")

    uni_cache = {}
    for r in ok7:
        if r["reg"] not in uni_cache:
            uni_cache[r["reg"]] = (universe_raw_count(cur, r["reg"]),
                                   load_universe_day(cur, r["reg"]),
                                   prev_trading_day(cur, r["reg"]))

    def nup_rows(d):
        _raw, rowsu, _pd = uni_cache[d]
        return [x for x in rowsu
                if x[1] is not None and x[6] and float(x[1]) >= float(x[6]) * UP_MULT]

    def nup_r_array(d):
        """그날 `n_up` 집합의 `r = C/H − 1` (고가 > 0 인 종목만)."""
        v = [float(x[3]) / float(x[1]) - 1.0 for x in nup_rows(d)
             if x[1] and float(x[1]) > 0 and x[3] is not None]
        return np.asarray(v, dtype=float)

    say("### 3-3. `G* = max_gap / (max r − min r)` · 경험적 귀무\n")
    if not prem:
        say(f"⛔ **이분성 판정 불가 — 한 무리만 관측(상한가형 {n_ceil}건 · 되밀림형 {n_pull}건)**")
        say("")
        say("(동결 문언 그대로다 — `PREREG_POST6.md` §3-2: *「전제(양쪽 ≥2건)를 못 채우면 ⇒ ⛔ "
            "「이분성 판정 불가 — 한 무리만 관측(`상한가형 k건 · 되밀림형 m건`)」이라고 «그대로» 적는다. "
            "✅ 로 접지 않는다.」*)")
        say(f"⇒ **`G*` 와 귀무는 계산하지 않는다**(*「없으면 검정 자체를 안 돌린다」*). "
            f"중간대는 {n_mid}건이다.")
        say("🔑 ***이게 `REG-M2` 의 결함을 고치는 핵심이다*** — 단봉 표본을 ✅ 로 접지 않는 것.\n")
        g_obs = float("nan")
        m2_verdict = "⛔ 판정 불가(전제 미충족)"
    else:
        rs7 = [r["r"] for r in ok7]
        g_obs = gstar(rs7)
        cands_a = [nup_r_array(r["reg"]) for r in ok7]
        empty = [r["name"] for r, c in zip(ok7, cands_a) if len(c) == 0]
        say(f"- 관측 `G*` = **{g_obs:.4f}** (n={len(rs7)})")
        say("- 귀무(§3-2 문언): *「각 건의 등록일에 대해 **그날 `n_up` 집합**에서 «같은 크기 `n`»을 "
            f"무작위 추출해 같은 `G*` 를 계산」* · 시드 **{NULL_SEED}** · **{NREP:,}** 반복")
        if empty:
            say(f"- 🔴 `n_up` 집합이 빈 등록일 건: {', '.join(empty)} ⇒ 귀무 계산 불가")
        say("- 🔴 **문언이 두 갈래로 읽힌다 ⇒ 양쪽 다 인쇄한다**(값 보고 고르지 않는다):")
        say("  - **읽기 A** = 각 «건»을 그 건의 등록일 `n_up` 집합에서 뽑은 한 종목으로 치환")
        say("  - **읽기 B** = 각 «등록일»의 `n_up` 집합에서 크기 n 을 비복원 추출")
        rngA = np.random.default_rng(NULL_SEED)
        nullA = null_gstar_a(cands_a, rngA)
        pA = float((nullA >= g_obs - 1e-12).mean())
        rngB = np.random.default_rng(NULL_SEED)
        nullB, replB = null_gstar_b(cands_a, len(rs7), rngB)
        pB = float((nullB >= g_obs - 1e-12).mean())
        say("")
        say("| 읽기 | 귀무 표본 | 귀무 평균 `G*` | 귀무 중앙 | **p = P(귀무 ≥ 관측)** | < 5% |")
        say("|---|---|---|---|---|---|")
        say(f"| **A**(주) | {len(nullA):,} | {nullA.mean():.4f} | {np.median(nullA):.4f} | "
            f"**{pA:.5f}** | {'✅' if pA < ALPHA else '❌'} |")
        say(f"| B(병기) | {len(nullB):,} | {nullB.mean():.4f} | {np.median(nullB):.4f} | "
            f"**{pB:.5f}** | {'✅' if pB < ALPHA else '❌'} |")
        if replB:
            say(f"\n🔴 읽기 B 에서 `n_up` 집합이 n 보다 작은 등록일 {len(replB)}건 "
                f"(크기 {sorted(replB)}) ⇒ 그 날만 **복원 추출**로 대체했다(그 사실을 그대로 적는다).")
        split_g = (pA < ALPHA) != (pB < ALPHA)
        if split_g:
            m2_verdict = "⛔ **판정 불가 · 모호** — 귀무 문언이 두 갈래로 읽히고 두 읽기가 갈린다"
        else:
            m2_verdict = "✅ 지지" if pA < ALPHA else "⛔ 불성립"
        say(f"\n⇒ 결정규칙 «`G*` 의 귀무 백분위 < 5%» ⇒ **{m2_verdict}**")
        say("⇒ ⛔ 경로(대칭): 백분위 ≥ 5% 면 불성립 · 전제 미충족이면 판정 불가 · "
            "두 읽기가 갈리면 판정 불가·모호\n")

    say("### 3-4. 제도 효과 분리 — 상한가 «마감» 건 (§3-2 필수)\n")
    lim_rows = [r for r in ok7 if r["ret_c"] == r["ret_c"] and r["ret_c"] >= LIMIT_UP]
    say(f"- 조작정의: **종가 등락 ≥ +{LIMIT_UP:.0%}**(제도 상한 +30%). "
        f"상한가형(`r ≥ −1%`) **{n_ceil}건** 중 상한가 마감 **{len(lim_rows)}건**"
        + (" — " + ", ".join(r["name"] for r in lim_rows) if lim_rows else ""))
    if prem:
        rest = [r["r"] for r in ok7 if not (r["ret_c"] == r["ret_c"] and r["ret_c"] >= LIMIT_UP)]
        if len(rest) >= 2 and lim_rows:
            g_rest = gstar(rest)
            say(f"- 상한가 마감 건을 뺀 `G*` = **{g_rest:.4f}** (n={len(rest)}) "
                f"↔ 전 건 `G*` = {g_obs:.4f}")
            cands_rest = [nup_r_array(r["reg"]) for r in ok7
                          if not (r["ret_c"] == r["ret_c"] and r["ret_c"] >= LIMIT_UP)]
            rngR = np.random.default_rng(NULL_SEED)
            nullR = null_gstar_a(cands_rest, rngR)
            pR = float((nullR >= g_rest - 1e-12).mean())
            say(f"- (참고 · 민감도) 크기만 맞춘 읽기 A 귀무: **p={pR:.5f}** — "
                "🔴 동결 문언은 「`G*` 를 인쇄」까지만 요구한다. 귀무 후보 풀은 그대로 두고 "
                "**크기만** 맞췄다(문언에 없는 부분이라 그대로 적는다).")
        elif lim_rows:
            say(f"- 상한가 마감 건을 빼면 n={len(rest)} ⇒ `G*` 정의 불가(2건 미만) — 값 없음")
        else:
            say("- 상한가 마감 건이 **0** 이므로 뺄 것이 없다 ⇒ 제외 `G*` = 전 건 `G*` 와 동일")
    else:
        say("- 전제 미충족으로 `G*` 자체를 계산하지 않았다 ⇒ 제외 `G*` 도 없다(건수만 인쇄).")
    say("- 🔴 `RESULTS_REGDAY_POST5.md:158`: *「***골짜기의 오른쪽 벽은 저자 행동이 아니라 시장 "
        "제도가 만든다. 인과로 읽지 말 것.***」*\n")

    say("### 3-5. 옛 `REG-M2` 규칙 병기 — 죽은 가드가 «죽어 있음»을 매회 증명한다\n")
    old_ok = (n_pull >= 1) and (n_mid == 0)
    say("- 옛 규칙(`PREREG_REGDAY_MEASURE.md` §4-2): «되밀림형 ≥ 1 **그리고** 중간대 = 0»")
    say(f"- 관측: 되밀림형 {n_pull} · 중간대 {n_mid} ⇒ "
        + ("**✅ 자동 통과**" if old_ok else "**⛔ 불성립**"))
    say("- 🔑 `RESULTS_REGDAY_POST5.md` §3-1: *「***M2 의 결정규칙은 「이분성」을 검정하지 못한다. "
        "「중간대가 비어 있음」만 검정한다.***」*")
    if old_ok and not prem:
        say("- 🔴🔴 **이번 글이 그 증명이다** — 새 전제(양 무리 각 ≥2)는 «미충족»인데 "
            "옛 규칙은 **그대로 통과**한다. 같은 표본에서 두 규칙이 정반대를 말한다.")
    elif old_ok and prem:
        say("- 이번 글에서는 두 규칙이 같은 방향이다(옛 규칙 통과 · 새 전제 충족) — "
            "그래도 옛 규칙이 «검정하지 못한다»는 사실은 변하지 않는다.")
    else:
        say("- 이번 글에서는 옛 규칙이 통과하지 못했다(중간대에 건이 들어왔다).")
    say("")

    # ── §4. 🆕 창 규약 첫 발동 + P6-W10 ─────────────────────────────────────
    say("## 4. 🆕 `PREREG_POST6.md` §1-4 **창 규약 «첫 발동»** + `P6-W10` 귀무 (PD-4 2번 · 의무)\n")
    say("> 🔴🔴 **`TV` 축의 `P6-W10` 과 «한 수로 합치지 않는다».** `TV` 자가보고는 이번 글에 "
        "**0건**이라 `TV-W1`~`W9`·`P6-W10`·`TV-N1`~`N3` 는 전부 ⛔ **「미룬다」**"
        "(PD-6 · `run_d1_oos_post7.py`). 아래는 **§1-4 창 규약 용도**의 `P6-W10` 이며, "
        "***두 용도는 서로 다른 수다.***\n")
    say("> 🔴 **`approx` 2건은 판정 분모에 «들어가지 않는다»**(PD-4 1번). 이 절은 **의무 민감도**이고, "
        "***여기서 열린 값을 판정으로 승격하지 않는다.***\n")
    say("### 4-1. 창 규약 적용 — 갈래 확인\n")
    say("| 종목 | 코드 | 저자 표기 | 창 | 동결 문서 갈래 | DB 거래일 달력 실측 | 일치 |")
    say("|---|---|---|---|---|---|---|")
    branch_ok = True
    for nm, code, label, lo, hi, days in APPROX_BRANCHES:
        cal = market_days(cur, lo, hi)
        ok = (cal == days)
        branch_ok = branch_ok and ok
        say(f"| {nm} | {code} | {label} | `[{lo}, {hi}]` | **{len(days)}일** | "
            f"**{len(cal)}일** | {'🟢 일치' if ok else '🔴 **불일치** — DB: ' + ' · '.join(cal)} |")
    say("")
    say("⇒ **「창 규약 적용」** — 「9월 초」 = 09-01~09-10 의 «모든 거래일», "
        "「8월 말」 = 08-21~08-31 의 «모든 거래일»(PD-4 2번 · 달력 실측). "
        + ("🟢 동결 문서와 DB 달력이 일치한다."
           if branch_ok else "🔴 어긋난 곳이 있다 — 그대로 인쇄하고 «고치지 않는다»."))
    say("")
    say("### 4-2. 갈래별 측정 (`Q1-R2`·`P6-M1′` 측정자 그대로)\n")
    approx_meas = {}
    for nm, code, label, lo, hi, days in APPROX_BRANCHES:
        rows = measure(df, [(nm, code, d) for d in days])
        approx_meas[nm] = rows
        say(f"**{nm}** (`{code}`) — {label} · 갈래 {len(days)}일\n")
        say("| 갈래 `D` | 창봉수(**D 포함**) | 등록일 고가 | 창 최고 고가 | **일치** | "
            "`r=C/H−1` | `(C−L)/(H−L)` | 종가 등락 |")
        say("|---|---|---|---|---|---|---|---|")
        for r in rows:
            if not r["ok"]:
                say(f"| {r['reg']} | — | — | — | (봉 없음) | — | — | — |")
                continue
            say(f"| {r['reg']} | {r['nwin']} | {r['high']:,.0f} | {r['win_max_high']:,.0f} | "
                f"{'✅' if r['hit'] else '❌'} | {r['r']:+.2%} | {r['pos']:.3f} | "
                f"{fmt_pct(r['ret_c'])} |")
        okr = [r for r in rows if r["ok"]]
        hh = sum(1 for r in okr if r["hit"])
        say(f"\n⇒ 갈래 적중 **{hh}/{len(okr)} = {hh/len(okr)*100:.1f}%**\n")

    say("### 4-3. `P6-W10` — 무작위 «창» 귀무 (§1-4 용도 · **의무 인쇄**)\n")
    say("> 문턱 **귀무 적중률 ≥ 50% → 강등**(`RESULTS_D1_OOS_POST5.md` §9 — `TV-W7` 상속 · "
        "`PREREG_D1_OOS.md` §4). 🔑 ***「창 규약이 지시한 아무 날이나 골라도 같은 답이 나온다」면 "
        "그 측정자는 등록일을 재는 것이 아니다.***\n")
    say("| 종목 | 창 갈래 수 | 갈래 적중 | **귀무 적중률**(전수) | ≥ 50% ⇒ 강등 |")
    say("|---|---|---|---|---|")
    w10_rates = []
    for nm, code, label, lo, hi, days in APPROX_BRANCHES:
        okr = [r for r in approx_meas[nm] if r["ok"]]
        hh = sum(1 for r in okr if r["hit"])
        rate = hh / len(okr) if okr else float("nan")
        w10_rates.append(rate)
        say(f"| {nm} | {len(okr)} | {hh} | **{rate*100:.1f}%** | "
            f"{'🔴 **예**' if rate >= W10_DEGRADE else '🟢 아니오'} |")
    say("")
    # 전수(조합) 귀무 — 갈래 집합이 작아 «표본이 아니라 전수»로 센다(시드 불필요·결정적).
    combos = list(itertools.product(*[[r for r in approx_meas[nm] if r["ok"]]
                                      for nm, *_x in APPROX_BRANCHES]))
    combo_hit = [sum(1 for r in c if r["hit"]) / len(c) for c in combos]
    w10_all = float(np.mean(combo_hit)) if combo_hit else float("nan")
    degrade_w10 = w10_all >= W10_DEGRADE
    say(f"- **조합 전수 귀무**: 갈래 조합 "
        f"{' x '.join(str(len([r for r in approx_meas[nm] if r['ok']])) for nm, *_x in APPROX_BRANCHES)}"
        f" = **{len(combos)}** · 조합 평균 적중률 **{w10_all*100:.1f}%** · "
        f"범위 [{min(combo_hit)*100:.1f}%, {max(combo_hit)*100:.1f}%]")
    say(f"- **`P6-W10` 판정** = **"
        + ("🔴 발동 — 귀무 적중률 ≥ 50% ⇒ 창 규약 갈래로는 등록일을 «가리지 못한다»(강등)"
           if degrade_w10 else "🟢 미발동 — 창 규약 갈래가 답을 가른다") + "**")
    say(f"- 🔑 **전수를 셌으므로 시드가 필요 없다**(갈래 집합이 작다). 계열 시드 **{NULL_SEED}** 는 "
        "§2·§3 귀무에만 쓰였다 — 여기서 새 시드를 만들지 않았다.")
    say("- 🔴 **이 수를 `TV` 축 `P6-W10` 과 합치지 않는다**(PD-6 · 두 용도).")
    say("")
    say("### 4-4. `approx` 포함 갈래가 주 판정을 뒤집는가 (민감도 · 승격 금지)\n")
    say(f"| 예측 | 문턱 | 주 판정(`exact` {len(ok7)}) | `approx` 포함 조합 최소 | 조합 최대 | "
        "판정이 갈리는가 |")
    say("|---|---|---|---|---|---|")
    r2_vals, m1_vals = [], []
    for c in combos:
        allr = list(ok7) + list(c)
        hh = sum(1 for r in allr if r["hit"])
        r2_vals.append(hh / len(allr))
        m1_vals.append(hh / len(allr))
    r2_flip = len(set(v >= R2_RATIO for v in r2_vals)) > 1 or \
        ((obs7 >= R2_RATIO) not in set(v >= R2_RATIO for v in r2_vals))
    m1_flip = len(set(v >= M1_RATIO for v in m1_vals)) > 1 or \
        ((obs7 >= M1_RATIO) not in set(v >= M1_RATIO for v in m1_vals))
    # 🔒 §2-5 가 «앞에서» 쓴 값과 같아야 한다 — 다르면 배선 결함이다.
    assert bool(m1_flip) == bool(prec_dep), ("등록일 정밀도 의존 배선 불일치", m1_flip, prec_dep)
    say(f"| `Q1-R2` | ≥ 50% | {obs7*100:.1f}% | {min(r2_vals)*100:.1f}% | {max(r2_vals)*100:.1f}% | "
        f"{'🔴 **갈린다**' if r2_flip else '🟢 같다'} |")
    say(f"| `P6-M1′` 비율 | ≥ 83.33% | {obs7*100:.1f}% | {min(m1_vals)*100:.1f}% | "
        f"{max(m1_vals)*100:.1f}% | {'🔴 **갈린다**' if m1_flip else '🟢 같다'} |")
    say("")
    if r2_flip or m1_flip:
        say("🔴🔴 **`approx` 갈래에서 판정이 갈린다** ⇒ ***「등록일 정밀도 의존」으로 적고 어느 쪽도 "
            "«지지»로 선언하지 않는다*** — 단 **주 판정은 동결 문언이 지시한 `exact` 로 선다**"
            "(PD-4 1번 · 갈린다는 사실을 숨기지 않는다).")
    else:
        say("🟢 **갈리지 않는다** ⇒ 「등록일 정밀도 의존」 없음. "
            "⚠️ 단 이건 「`approx` 가 정확하다」가 아니라 **「집계가 안 뒤집힌다」**일 뿐이다.")
    say("🔴 **재진입 민감도(§2-3)와 이 `approx` 민감도를 «합치지 않는다»** — 재진입 3건 중 2건이 "
        "`approx` 라 두 민감도가 겹치기 때문이다(PD-3 말미 · 따로 인쇄 의무).")
    say("")

    # ── §5. P6-M3′ ──────────────────────────────────────────────────────────
    say("## 5. `P6-M3′` (반증축) — 되밀림형 종가 위치 `(C−L)/(H−L)` (`PREREG_POST6.md` §3-3)\n")
    pull7 = [r for r in ok7 if bucket(r["r"]) == "되밀림형"]
    say("| 종목 | 등록일 | 고가 | 저가 | 종가 | **`(C−L)/(H−L)`** | 개별 (< 0.5) |")
    say("|---|---|---|---|---|---|---|")
    for r in pull7:
        say(f"| {r['name']} | {r['reg']} | {r['high']:,.0f} | {r['low']:,.0f} | {r['close']:,.0f} | "
            f"**{r['pos']:.3f}** | {'✅' if r['pos'] < 0.5 else '🔴 실패'} |")
    pos7 = sorted(r["pos"] for r in pull7)
    if len(pull7) < MIN_PULL:
        say(f"\n⇒ 되밀림형 **{len(pull7)}건 < 최소 n {MIN_PULL}** ⇒ ⛔ **판정 불가** "
            "(`PREREG_POST6.md` §4 #10 ⛔ 조건 「되밀림형 < 3」 · INTAKE §5 2행)")
        say("🔑 ⛔ 는 «선언» 금지이지 «인쇄» 금지가 아니다 — 위 표의 관측값은 그대로 남긴다.")
        med7 = float("nan")
        fail_major = None
    else:
        med7 = float(np.median(pos7))
        m3_ok = med7 < 0.5
        n_fail = sum(1 for p in pos7 if p >= 0.5)
        fail_major = n_fail * 2 > len(pos7)
        say(f"\n⇒ 되밀림형 **{len(pull7)}건** · 중앙값 **{med7:.3f}** · "
            f"범위 [{min(pos7):.3f}, {max(pos7):.3f}]")
        if m3_ok:
            say("⇒ 결정규칙 «중앙값 < 0.5»(문턱 불변) ⇒ **✅ 통과**")
        elif prem:
            say("⇒ 결정규칙 «중앙값 < 0.5»(문턱 불변) ⇒ **🔴 실패 ⇒ `P6-M2′` 지지 취소**")
        else:
            say("⇒ 결정규칙 «중앙값 < 0.5»(문턱 불변) ⇒ **🔴 실패** — 다만 `P6-M2′` 는 이미 "
                "«판정 불가»(전제 미충족)라 **취소할 지지가 없다**. 반증축이 «단독으로» 실패한 셈이다.")
        say(f"⇒ 개별 실패(`≥ 0.5`) **{n_fail}/{len(pos7)}** ⇒ 과반 여부 **"
            + ("🔴 과반 — 「되밀림」이라는 «이름»으로 인용 금지" if fail_major
               else "과반 아님(인용 제한 미발동)") + "**")
        say("- 🔑 인용 제한은 **지지 취소가 아니다**(§3-3 문언 그대로).")
    p6pull = sorted(r["pos"] for r in r6 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p5pull = sorted(r["pos"] for r in r5 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p4pull = sorted(r["pos"] for r in r4 if r["ok"] and bucket(r["r"]) == "되밀림형")
    allpos = sorted(pos7 + p6pull + p5pull + p4pull)
    if allpos:
        say(f"\n(참고 · 판정 아님) 되밀림형 종가 위치 누적 **{len(allpos)}건** 중앙 "
            f"**{np.median(allpos):.3f}** — post7 {len(pos7)}건 · post6 재계산 {len(p6pull)}건 · "
            f"post5 {len(p5pull)}건 · post4 {len(p4pull)}건")
    say("")

    # ── §6. REG-M4 ──────────────────────────────────────────────────────────
    say("## 6. `REG-M4` (대칭 단언) — `n_up` (`PREREG_REGDAY_MEASURE.md` §4-4 · 매회 재판정)\n")
    say("### 6-0. `PREREG_POST6.md` §5-2 — 유니버스 `prev_close` 결손 공개 (5열 · 등록일마다)\n")
    say("| 등록일 | `universe_mcap` | `universe_test` | `dropped` | `drop_rate` | `prev_bar_date` |")
    say("|---|---|---|---|---|---|")
    drop_flag_days = []
    for d in sorted(uni_cache):
        raw, rowsu, pbd = uni_cache[d]
        drop = raw - len(rowsu)
        rate = drop / raw if raw else float("nan")
        if rate >= DROP_GUARD:
            drop_flag_days.append((d, rate))
        say(f"| {d} | {raw:,} | {len(rowsu):,} | {drop:,} | "
            f"{'🔴 **' + f'{rate*100:.2f}%' + '**' if rate >= DROP_GUARD else f'{rate*100:.2f}%'} | "
            f"{pbd} |")
    say(f"\n- 가드(§5-2 · 숫자 1%): `drop_rate ≥ {DROP_GUARD:.0%}` 인 날은 🔴 표시하고 "
        "**그날의 `n_up` 을 다른 날과 직접 비교하지 말 것**.")
    if drop_flag_days:
        for d, rate in drop_flag_days:
            say(f"  - 🔴 **{d}** — `drop_rate` {rate*100:.2f}% ⇒ "
                "**이 날의 `n_up` 은 다른 날과 직접 비교하지 말 것**")
    else:
        say(f"  - 🟢 이번 등록일 {len(uni_cache)}일 전부 `drop_rate < {DROP_GUARD:.0%}` ⇒ 가드 미발동 "
            "(post5 는 08-05 가 6.91% 였다).")
    mism = []
    for d in sorted(uni_cache):
        _raw, rowsu, pbd = uni_cache[d]
        k = sum(1 for x in rowsu if str(x[7]) != str(pbd))
        if k:
            mism.append((d, pbd, k))
    if mism:
        say("- ⚠️ `prev_bar_date` 는 **시장 전체의 직전 거래일**이다. 종목별 `LAG(date)` 가 그와 다른 건수: "
            + " · ".join(f"{d}: {k}종목" for d, _p, k in mism)
            + " ⇒ 그 종목들은 **더 먼 과거 봉**을 전일종가로 쓴다(결손 계열).")
    else:
        say("- 🟢 종목별 `LAG(date)` 가 전부 시장 직전 거래일과 같다.")
    say("- 편향 방향(§5-2 · `RESULTS_REGDAY_POST5.md` §5-0): *「빼면 더 커질 뿐 작아지지 않는다」* ⇒ "
        "**`n_up` 결론은 강건**, 다만 **순위 진술은 과대**일 수 있다.\n")

    say("### 6-1. 건별 `n_up` 과 저자 종목의 자리\n")
    say("| 종목 | 등록일 | 검정 유니버스 | **`n_up`** | 본인이 `n_up` 안에? | "
        "`n_up` 안 `거래대금/시총` 순위 | 백분위 |")
    say("|---|---|---|---|---|---|---|")
    nups, pcts, inset_n = [], [], 0
    for r in ok7:
        rowsu = uni_cache[r["reg"]][1]
        up = [(x[0], float(x[4]) / float(x[5])) for x in nup_rows(r["reg"])
              if x[4] is not None and x[5]]
        nup = len(up)
        nups.append(nup)
        up_sorted = sorted(up, key=lambda t: -t[1])
        hit_i = [k for k, (sc, _v) in enumerate(up_sorted) if sc == r["code"]]
        if hit_i:
            inset_n += 1
            rk = hit_i[0] + 1
            pctv = (nup - rk) / (nup - 1) * 100 if nup > 1 else 100.0
            pcts.append(pctv)
            rk_s, pct_s, in_s = f"**{rk} / {nup}**", f"{pctv:.1f}", "✅"
        else:
            rk_s, pct_s, in_s = "—", "—", "🔴 **아니다**"
        say(f"| {r['name']} | {r['reg']} | {len(rowsu):,} | **{nup}** | {in_s} | {rk_s} | {pct_s} |")
    med_nup = float(np.median(nups))
    say(f"\n⇒ **`n_up` 중앙값 {med_nup:.1f}** · 범위 **[{min(nups)}, {max(nups)}]** · "
        f"표준편차 {np.std(nups, ddof=0):.1f}**(모표준편차 · `ddof=0`)**")
    say(f"⇒ 본인이 `n_up` 집합 «안»인 건 **{inset_n}/{len(ok7)}** — "
        f"밖인 건 **{len(ok7) - inset_n}건**"
        + (f" · 안에 있는 건의 `거래대금/시총` 백분위 중앙 **{np.median(pcts):.1f}**" if pcts else ""))
    say("")
    say("### 6-2. 「`P6-M1′` 을 선정 규칙으로 인용 금지」 — **매회 재판정**\n")
    ban = med_nup >= NUP_CITE_BAN
    say(f"- 문턱: `n_up` 중앙 **≥ {NUP_CITE_BAN}** ⇒ 인용 금지 "
        f"(`PREREG_POST6.md` §4 #3 ← `PREREG_D1_OOS.md` §4 `N2`). "
        "`PREREG_REGDAY_MEASURE.md` §4-4 의 자기 문언은 정성적이다(*「매일 수십 종목」*) — "
        "**둘 다 적는다**.")
    say(f"- 관측 중앙 **{med_nup:.1f}** ⇒ **"
        + ("🔴 발동 — `M1`/`P6-M1′` 을 「선정 규칙」으로 인용 금지" if ban
           else "🟢 미발동 — 이번 글에서는 인용 금지가 걸리지 않는다")
        + "** (정성 읽기 「매일 수십 종목」으로도 "
        + ("같은 결론" if (med_nup >= 10) == ban else "🔴 다른 결론 ⇒ 판정 불가·모호") + ")")
    say("- 🔑 §2-2: ***`REG-M4` 는 상수가 아니다*** — `n_up` 이 작아지는 날이 오면 다시 볼 수 있으므로 "
        "**매회 다시 낸다**.")
    say("- 🔴 대칭: `REG-M4` 는 **자신이 반증축**이다(§4 #11). 그래서 여기엔 「지지」가 없고 "
        "«인용 금지 발동/미발동»만 있다.\n")

    # ── §7. REG-M5 ──────────────────────────────────────────────────────────
    say("## 7. `REG-M5` (기록만 · 라이브 대조) — 되밀림형 `r` 분포\n")
    r7v = sorted(r["r"] for r in pull7)
    say("| 표본 | n | 중앙 | 최소 | 최대 |")
    say("|---|---|---|---|---|")
    if r7v:
        say(f"| 7번째 글 되밀림형 | {len(r7v)} | {np.median(r7v):+.2%} | {min(r7v):+.2%} | "
            f"{max(r7v):+.2%} |")
    else:
        say("| 7번째 글 되밀림형 | 0 | — | — | — |")
    p6v = sorted(r["r"] for r in r6 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p5v = sorted(r["r"] for r in r5 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p4v = sorted(r["r"] for r in r4 if r["ok"] and bucket(r["r"]) == "되밀림형")
    for lbl, vv in (("6번째 글 되밀림형(재계산)", p6v), ("5번째 글 되밀림형(재계산)", p5v),
                    ("4번째 글 되밀림형(재계산)", p4v)):
        if vv:
            say(f"| {lbl} | {len(vv)} | {np.median(vv):+.2%} | {min(vv):+.2%} | {max(vv):+.2%} |")
    allv = sorted(r7v + p6v + p5v + p4v)
    if allv:
        say(f"| 누적 | {len(allv)} | {np.median(allv):+.2%} | {min(allv):+.2%} | {max(allv):+.2%} |")
    say(f"\n라이브 `entry_band_up_pct` = **+{BAND_UP:.0%}** (그 위로 갭업하면 매수 포기).")
    if r7v:
        say(f"저자 되밀림형 등록일 종가는 그날 고가 대비 **{np.median(r7v):+.2%}**(중앙) 자리다.")
    say("🔴 **예측 아님 · 판정에 쓰지 않는다.** 저자 프로그램의 «매수 체결가»는 복원되지 않았다 "
        "(🔒 결정 ④로 `PREREG_BUYLADDER` 계열은 **종결·기록 보존** — PD-13 1번).")
    say("🔑 전 건 `r` 분포(참고 · 되밀림형 한정 아님): "
        f"중앙 {np.median([r['r'] for r in ok7]):+.2%} · "
        f"[{min(r['r'] for r in ok7):+.2%}, {max(r['r'] for r in ok7):+.2%}]\n")

    # ── §8. 부수 ────────────────────────────────────────────────────────────
    say("## 8. 부수 — 창 절단 · 봉수 표기 규약 · 축 밖 건\n")
    say("🔑 **아래 「창 봉수」는 «등록일 D 를 포함한» 셈이다** — 20봉 = 등록일 + 그 앞 19봉 "
        "(§1-6 7 · `RESULTS_LADDER_TRANCHE.md` N8).\n")
    say("| 종목 | 창 요구 | 창 실제 봉수(**D 포함**) | D **이전** 봉수 | 영향 |")
    say("|---|---|---|---|---|")
    for r in ok7:
        nt = ("🔴 **창이 절단됐다** — `[D−19,D]` 가 아니라 상장/수집 이후 전 구간"
              if r["nwin"] < WIN else "정상")
        say(f"| {r['name']} | {WIN}봉(D 포함) | {r['nwin']} | {r['nwin'] - 1} | {nt} |")
    say(f"\n⇒ 절단 **{len(trunc)}건** — PD-12 의 「해치텍 10/20 · 나머지 5건 20/20」과 "
        + ("🟢 일치" if len(trunc) == 1 else "🔴 불일치") + ".")
    say("")
    say("### 8-1. 등록일 축 «밖» 건 (기록 · 분모 아님)\n")
    say("| 종목 | 코드 | 사유 |")
    say("|---|---|---|")
    for nm, code in POST7_NONE:
        say(f"| {nm} | {code} | 🔴 `none` — **등록일 문장이 없다**(PD-4). "
            "「8월 26일」은 급등 사유일이고 등록 문장과 **다른 줄**이라 승격하지 않는다 |")
    for nm, code in POST7_FOLLOWUP:
        say(f"| {nm} | {code} | 🔁 후속 — 그 등록 사건은 post6 신규 분모에서 **이미 계상**됐다"
            "(PD-2 2번 · 이중계상 금지 · 값을 보고 뺀 것이 아니라 «정의»로 빠진다) |")
    say("")
    say("⚠️ 이 레인이 쓰는 창은 `[D−19, D]` 뿐이다 — **PD-12 의 창5 `[D, D+4]` 절단**"
        "(빛과전자 4봉 · 범한퓨얼셀 3봉)은 `LAD-`·`ANC-` 레인 소관이며 "
        "**이 산출물의 값에 영향이 없다**.")
    say("⚠️ 해치텍(`0155E0`)의 60봉 특징(`f9`) NaN 처리는 `SEL-` 레인 소관이다"
        "(`run_selection_post7.py` §6-1 · C-17).")
    say("")
    say(f"🔴 **창 종료 {DB_UPTO} = 발행일({PUB_DATE} 토) 휴장 ⇒ 마지막 거래일 · B-1(전 축 · "
        f"`WRC-` 포함)** · **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 = {snap_rows:,}**"
        "(기록 의무 · 창으로 쓰지 않는다 · PD-1 5번).")
    say("🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).")

    conn.close()
    (BASE / "RESULTS_REGDAY_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
