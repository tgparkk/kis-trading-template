# -*- coding: utf-8 -*-
"""10번째 글 등록일 축 — `Q1-R2` · `P6-M1′` · `P6-M2′` · `P6-M3′` · `REG-M4` · `REG-M5` (`P6-W10` §1-4 용도 = 해당 없음).

`run_regday_post9.py` 를 **승계**한 post10 판이다(원본은 손대지 않는다). 측정자·귀무·통계량은 `run_regday_post6/7.py`,
D-9 박제 도구(`vintage`·`mixed_line`)는 `run_selection_post8.py`, post10 상수(`NEW10`·`MGR`·`PROBE_WIN`·`SWEEP_D1`·
`read_stamp`·`LIVE_BAN`·`corp_scan`)는 `run_selection_post10.py` 에서 **import 해 그대로 재사용**한다(새 판정 로직 0줄 —
 아래 «차이» 의 갈래 계산은 같은 측정자·같은 시드를 부분 표본에 다시 부르는 것뿐이다).
post9 판 대비 «차이» = ① post10 상수(글 목록 9 · `DB_UPTO` 10-02 · 누적 기준 `FROZEN_CUM` = (32, 37)) ② §1-5 재진입 4/9 —
**항등 아님**(9 ↔ 5) ⇒ 재진입 제외 갈래를 실제로 계산해 «판정이 갈리는가»를 인쇄(`Q1-R2`·`P6-M1′`·`P6-M2′`·`P6-M3′`·`REG-M4`)하고
`P6-PRIOR_CYCLE_IN_WINDOW` 4/9 를 의무 인쇄 ③ 「첨단 제외」 자리 = 「샌즈 제외」(🔒 #1 ⓐ · 인쇄만) + 「기업행위 건 제외」
(`P10-기업행위봉` · 의무 인쇄 · 답(참고) · 세지 않는다) ④ `P9-스탬프통일`(`regday_post10/read_stamp.json`) ⑤ `[D−19, D]` 걸침 8줄 +
서산 「전부 경계 전」 줄.

준거(전부 계산 «전» 동결 · 1순위 출처): `PREREG_POST6.md` §1-5 · §1-6 · §2-2 · §3-1~3-3 · §4 #7~#12 · §5-2 ·
`PREREG_REGDAY_MEASURE.md` §4 · `PREREG_Q1_V2.md` §3 `R2`(`:66`) · `PREREG_D1_OOS.md` §4 · `PREREG_POST8.md` D-3·D-5·D-6·D-9·
D-10·D-11 · `PREREG_POST10.md`(동결 `522d6dc`) §0-1·§3 (나) · `PREDECISION_2026-10-04_post10.md` PD-1·3·12·21·23·24·27·29·35·36·43 ·
`INTAKE_2026-10-04_post10.md` §1·§5.

동결 문언 준수 사항:
  · 🔴 **판정 분모 = 신규 ∧ `exact` = 9건**(서산 · 샌즈랩 · 성호전자 · 라온시큐어 · 범한퓨얼셀 · 한켐 · HT로보틱스 · 우리로 · 뷰노) ·
    `approx` 0 · 후속 3(축 밖) · 🔒 #1 ⓐ 재등록(샌즈랩 9/29 · 한컴위드 9/23)은 등록 사건 아님.
  · 창 `[D−19, D]` = D 포함 20거래일 · `P6-절단가드-A` 0/9 예고 · 귀무 시드 20260815 · 20,000 반복(승계).
  · D-6 `n_up` sd `ddof=1` 앞 · D-11 `Q1-R2` 줄 병기·금지어 기계 검사(`say()`).
  · 산출물에 «실행 시각»은 D-9 ① 스탬프(첫 읽은 시각)만 박는다.

🔴 이 산출물은 **라이브 채택 대상이 아니다**(`PREREG_POST10.md` §0-1). 새 예측 0 · 등급 이름 0 · 라이브 트리 import 0 ·
DB SELECT 만 · `adj_factor` 산술 0 · 시드·반복 고정이라 재실행 byte 동일.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

# 🔴 새 코드 0줄 — post6·post7 판의 측정자·귀무·표 포맷을 **그대로** 재사용한다(원본 불변).
import run_regday_post6 as R6
from run_regday_post6 import (block, bucket, fmt_pct, gstar, load_universe_day,
                              measure, null_gstar_a, null_gstar_b, null_p,
                              prev_trading_day, universe_raw_count, verdict_and)
import run_regday_post7 as R7
from run_regday_post7 import guard_a_fires, market_days, snapshot_tail
from run_selection_post8 import REGIME, mixed_line, vintage
# 아래 import 는 이 프로세스 안에서 `P8.DB_UPTO` 를 10-02 로 바꾼다(파일 불변 · post8 로더용) — 이 스크립트는 그 로더를 안 쓴다.
from run_selection_post10 import (FOLLOW10, LIVE_BAN, MGR, NEW8, NEW9, NEW10, PD3_FLAG, PROBE_WIN, REENTRY, SANDS,
                                  SWEEP_D1, WINDOW_LINE, corp_reason, corp_scan, read_stamp)
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
OUT_NAME = "RESULTS_REGDAY_POST10_NUMBERS.md"
ART = BASE / "regday_post10"

DB_UPTO = "2026-10-02"       # PD-1: 창 종료 = 발행 당일(금 · 거래일) 봉 «포함» · 전 축
DB_UPTO_CUT = "2026-09-29"   # PD-27 (마) 4 대조용 절단 적재(= 최대 등록일) — 판정에 쓰지 않는다
PUB_DATE = "2026-10-02"      # 10번째 글 발행일(금요일 · 거래일)
LOAD_LO = "2026-01-01"
WIN = 20                     # [D−19, D] = D 포함 20거래일
NREP = 20_000                # 사전등록 §4-1 승계: 시드 고정 20,000 반복
NULL_SEED = 20260815
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")
BAND_UP = 0.03               # 라이브 entry_band_up_pct (REG-M5 병기용)
UP_MULT = 1.15               # n_up 정의: 고가 ≥ 전일종가 × 1.15 (승계)
M1_RATIO = 5.0 / 6.0         # P6-M1′ 비율 문턱 0.8333 (§3-1)
R2_RATIO = 0.50              # Q1-R2 문턱 (PREREG_Q1_V2.md §3 · PREREG_POST6.md §4 #7)
ALPHA = 0.05                 # 귀무 백분위 문턱
MIN_N = 3                    # 최소 n (판정 건)
MIN_PULL = 3                 # P6-M3′ 최소 n (되밀림형)
CLUSTER_MIN = 2              # P6-M2′ 전제 — 양 무리 각 ≥ 2
TRUNC_GUARD = 1.0 / 3.0      # P6-절단가드-A (§1-6 3 · REC-Y3 차용 고지)
DROP_GUARD = 0.01            # §5-2 drop_rate 가드 1%
NUP_CITE_BAN = 30            # REG-M4 재판정 문턱 (PREREG_POST6.md §4 #3 ← PREREG_D1_OOS.md §4 N2)
W10_DEGRADE = 0.50           # P6-W10 강등 문턱 (RESULTS_D1_OOS_POST5.md §9 · TV-W7 상속)
LIMIT_UP = 0.29              # 상한가 «마감» 조작정의: 종가 등락 ≥ +29% (제도 상한 +30%)

# ── 🔴 판정 분모 = 10번째 글 신규 9건 = 전부 `exact` (INTAKE §5 · PD-3 · PD-12) ──
POST10_EXACT = list(NEW10)
POST10_FOLLOWUP = list(FOLLOW10)  # 한컴위드 · 코데즈컴바인 · 빛샘전자 — 등록일 축 밖(PD-2 · `none`)
SANDS_CODE = "411080"             # 샌즈랩 · 🔒 #1 ⓐ — 「샌즈 제외」 = 인쇄만(계수 아님)
APPROX_BRANCHES: list = []        # `approx` 0 ⇒ 갈래 없음(PD-21)

# 참고 재계산(판정 대체 아님) — post9 `exact` 5 · post8 4 · post7 6 · post6 10 · post5 · post4 (같은 10-02 스냅샷)
POST9P = list(NEW9)              # post9 `exact` 5 — 같은 스냅샷 재계산(참고)
POST8 = list(NEW8)               # post8 `exact` 4 — 같은 스냅샷 재계산(참고)
POST7 = list(R7.POST7_EXACT)
POST6 = list(R7.POST6)
POST5 = list(R7.POST5)
POST4 = list(R7.POST4)
# RESULTS_REGDAY_POST9_NUMBERS.md §1 — 동결 누적 28/32 + post9 4/5 = 32/37 (대조용 · 옮겨 적은 값)
FROZEN_CUM = (32, 37)
FROZEN_P9 = (4, 5)           # post9 판정 표본 발표값(RESULTS_REGDAY_POST9_NUMBERS.md §1-1)
Q1_TEXT = "*「**판정**: R1 위반 1건이면 기각 · R2 는 비율 기록 · R3 은 구간 겹침 여부만.」*"
Q1_TAG = [""]                # D-11 병기 문자열(`REG-M4` `n_up` 중앙이 나온 뒤 채운다)


def say(s=""):
    """출력 한 줄 — 🆕 D-11 기계 검사: `Q1-R2` 가 든 줄은 「지지」·「성립」 금지 + 병기 두 가지 필수."""
    if "Q1-R2" in s:
        assert "지지" not in s and "성립" not in s, ("D-11 위반 — Q1-R2 줄에 지지/성립", s)
        assert Q1_TAG[0] and Q1_TAG[0] in s, ("D-11 위반 — Q1-R2 줄에 병기 없음", s)
    print(s)
    OUT.append(s)


def rule_txt(v):
    """`verdict_and` 결과의 «표시»만 바꾼다 — 결정규칙 충족은 «기록»이지 «선언»이 아니다(post7 A-N2 관용)."""
    return {"✅ 지지": "✅ 두 성분 충족(기록 · 선언 아님)"}.get(v, v)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


# ── DB (post7 승계 · 상단만 09-18 로 넓힌다) ────────────────────────────────
def load_prices(codes, upto=DB_UPTO):
    conn = psycopg2.connect(**DSN)
    q = ("SELECT stock_code, date, open, high, low, close, trading_value, market_cap "
         "FROM daily_prices WHERE stock_code = ANY(%s) AND date BETWEEN %s "
         "AND %s AND close > 0 ORDER BY stock_code, date")
    df = pd.read_sql(q, conn, params=(list(codes), LOAD_LO, upto))
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def main():
    prev_out = R6.OUT
    R6.OUT = OUT          # post6 의 `block()` 은 «자기 모듈의» `say` 를 쓴다 ⇒ 이 실행의 버퍼로 잇는다(원본 불변)
    try:
        return _main()
    finally:
        R6.OUT = prev_out


def _main():  # noqa: C901
    codes = sorted(set(c for _n, c, _d in POST10_EXACT + POST9P + POST8 + POST7 + POST6 + POST5 + POST4))
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    v_probe = vintage(cur, *PROBE_WIN)
    v_lane = vintage(cur, LOAD_LO, DB_UPTO)
    snap_max, snap_rows = snapshot_tail(cur)
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (DB_UPTO,))
    rows_upto = int(cur.fetchone()[0])
    fp = dict(max_date=str(snap_max), max_rows=int(snap_rows), probe=list(PROBE_WIN), probe_min_u=str(v_probe[2]),
              probe_max_u=str(v_probe[1]), probe_n=int(v_probe[3]), lane=[LOAD_LO, DB_UPTO],
              lane_min_u=str(v_lane[2]), lane_max_u=str(v_lane[1]), lane_n=int(v_lane[3]), end_rows=rows_upto)
    first_read, reused, now_kst = read_stamp(cur, ART, fp)
    note(f"[D-9 ①] 이번 실행 벽시계(DB now) = {now_kst} · 본문 ① = {first_read} "
         f"({'같은 지문 재사용' if reused else '새 지문 — 새 시각 기록'}) · vintage now = {v_probe[0]}")
    df = load_prices(codes)
    sweep = dt.datetime.fromisoformat(SWEEP_D1)
    run_after_sweep = first_read >= SWEEP_D1[:19]
    run_after_maxupd = first_read > str(v_probe[1])[:19] and first_read > str(v_lane[1])[:19]

    r10 = measure(df, POST10_EXACT)
    ok10 = [r for r in r10 if r["ok"]]
    # `P10-기업행위봉`(F-3) — 창 = `[D−19, D]` 하나(PREREG_POST10.md §3 (나) 축별 표 `REG-`·`Q1-`·`P6-M1′`). 값 산술 0 · SELECT 만.
    corp = {r["name"]: corp_scan(cur, r["code"], r["win_dates"][0], r["win_dates"][-1]) for r in ok10}
    corp_k = [r["name"] for r in ok10 if corp[r["name"]]["split"] or corp[r["name"]]["vol0"]]
    # REG-M4 `n_up` 를 «먼저» 계산한다 — D-11 병기가 `Q1-R2` 의 모든 인용 자리에 필요하다.
    uni_cache = {}
    for r in ok10:
        if r["reg"] not in uni_cache:
            uni_cache[r["reg"]] = (universe_raw_count(cur, r["reg"]), load_universe_day(cur, r["reg"]),
                                   prev_trading_day(cur, r["reg"]))

    def nup_rows(d):
        if d not in uni_cache:
            uni_cache[d] = (universe_raw_count(cur, d), load_universe_day(cur, d), prev_trading_day(cur, d))
        _raw, rowsu, _pd = uni_cache[d]
        return [x for x in rowsu
                if x[1] is not None and x[6] and float(x[1]) >= float(x[6]) * UP_MULT]

    nups = [len(nup_rows(r["reg"])) for r in ok10]
    med_nup = float(np.median(nups))
    sd1 = float(np.std(nups, ddof=1))
    sd0 = float(np.std(nups, ddof=0))
    Q1_TAG[0] = (f"〔D-11 병기: 이번 회차 `REG-M4` `n_up` 중앙 **{med_nup:.1f}** · `PREREG_Q1_V2.md:66` {Q1_TEXT}〕")
    Q1T = Q1_TAG[0]

    # ── 머리말 ──────────────────────────────────────────────────────────────
    say("# RESULTS_REGDAY_POST10_NUMBERS — 기계 생성 (수정 금지)\n")
    say(f"- 🔴 **{WINDOW_LINE}**")
    say(f"- 🔴 **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)** · "
        f"창 종료일 {DB_UPTO} 행수 **{rows_upto:,}**")
    say(f"- 🔴 **D-9 ① 쿼리 실행 시각(KST) = {first_read}**(이 지문을 이 스크립트가 «처음» 읽은 실행 · "
        "`regday_post10/read_stamp.json` · 같은 지문 재실행은 이 값을 다시 쓴다 · 🆕 `P9-스탬프통일` 발효(post10 부터 · PD-35) · 키 "
        "`first_read_kst`·`timezone`·`fingerprint`)")
    say("- 🔴 라이브 채택 금지 — `PREREG_POST10.md` §0-1 문언 그대로(`:56`·`:58`):")
    say("")
    say(LIVE_BAN[0])
    say("")
    say(LIVE_BAN[1])
    say("")
    say("10번째 글 **등록일 축** — `P6-M1′` · `P6-M2′` · `P6-M3′` · `REG-M4` · `REG-M5` "
        "+ 같은 측정자를 쓰는 비율 항목 1건(`Q1-R2` · D-11 병기 규칙 적용) · `P6-W10`(§1-4 용도) = **해당 없음**(§4) " + Q1T)
    say("준거 `PREREG_POST6.md` §1-5·§1-6·§2-2·§3-1·§3-2·§3-3·§4 #7~#12·§5-2 · `PREREG_REGDAY_MEASURE.md` §4 · "
        "`PREREG_Q1_V2.md` §3 `R2` · `PREREG_D1_OOS.md` §4 · `PREREG_POST8.md`(동결 `04cd785`) D-3·D-5·D-6·D-9·D-10·D-11 · "
        "`PREREG_POST9.md`(동결 `702f41b`) · 🆕 `PREREG_POST10.md`(동결 `522d6dc`) §3 (나) · `PREDECISION_2026-10-04_post10.md` "
        "PD-1·3·12·21·23·24·27·29·35·36·43 · `INTAKE_2026-10-04_post10.md` §1·§5 · 원장(post10 12행/34레그)")
    say("생성 `run_regday_post10.py` (`run_regday_post9.py` 승계 · 측정자 import 재사용 · 원본 불변)\n")
    say(f"- DB `kis_template.daily_prices` 설정 `DB_UPTO = {DB_UPTO}` · 이 로드의 최신 봉 **{df.date.max().date()}**")
    say(f"- 창 = `[D−19, D]` = **D 를 «포함»한 직전 {WIN}거래일** · 봉수는 전부 **등록일 포함** 셈 "
        "(§1-6 7 · `RESULTS_LADDER_TRANCHE.md` N8)")
    say(f"- 귀무 반복 **{NREP:,}** · 시드 **{NULL_SEED}** ⇒ 두 번 실행하면 **byte 동일**")
    say("- 라벨은 **축 접두**로 부른다(§0-3): `Q1-`·`P6-`·`REG-`. 접두 없는 맨 라벨은 인용이 아니다.")
    say("- 🔴 **`adj_factor` 를 곱하지도 나누지도 않았다**(프로젝트 SSOT 규약).")
    say("- 🔴 **이 문서 안에서 새 예측을 만들지 않는다** · 등급 이름을 적지 않는다(§6 단계).\n")
    say(f"> 🔴🔴 **판정 분모 = 신규 ∧ `exact` = {len(POST10_EXACT)}건**({' · '.join(n for n, _c, _d in POST10_EXACT)} · "
        "INTAKE §5 · 🔒 #1 ⓐ — 항목 내 재등록 샌즈랩 9/29 · 한컴위드 9/23 은 등록 사건 아님 · **재등록 날짜 기록**).\n"
        "> 🔴 `approx` **0건** · `none`(신규) **0건** ⇒ 정밀도 갈래 없음(PD-21) · 후속 "
        f"**{len(POST10_FOLLOWUP)}건**({' · '.join(n for n, _c, _x in POST10_FOLLOWUP)})은 **등록일 축 밖**이다(PD-2 · 「`none`」).\n"
        "> 🔴🔴 **§1-5 재진입(exact 안) = 4**(범한퓨얼셀 · 서산 · 한켐 · 우리로) ⇒ 재진입 제외 민감도 **항등 아님**(9 ↔ 5) · "
        "두 값이 판정을 가르면 「재진입 의존」(`PREREG_POST6.md` §1-5 2) · `P6-PRIOR_CYCLE_IN_WINDOW` **4/9** 의무 인쇄 · "
        "「샌즈 제외」 9 ↔ 8 은 **인쇄만**(🔒 #1 ⓐ) · 「기업행위 건 제외」는 의무 인쇄 **답(참고) · 세지 않는다**(`F-3` (나)).\n")

    say("## 0-A. 🆕 `D-9` 읽은 시각 · 빈티지 박제 · `D-3`·`D-6`·`D-8` · `P9-` 의무 줄\n")
    say("| # | 의무 | 이 실행의 재측 | 관리자 실측(옮겨 적음 · 대조) |")
    say("|---|---|---|---|")
    say(f"| ① | 쿼리 실행 시각(KST) | **{first_read}**(스탬프) · 기계 검사: **> {SWEEP_D1}(D+1 sweep) = "
        f"{'예' if run_after_sweep else '🔴 아니오'}** · **> 창 구간 `max(updated_at)` = "
        f"{'예' if run_after_maxupd else '🔴 아니오'}** | {MGR['run']} |")
    say(f"| ② | 창 구간 `max(daily_prices.updated_at)` | `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` **{v_probe[1]}** · "
        f"이 레인 적재 창 `[{LOAD_LO}, {DB_UPTO}]` **{v_lane[1]}** | {MGR['max_upd']} |")
    say(f"| ③ | 「10-02 봉은 D+1(10-06) sweep 이후 읽음」 | **10-02 봉은 D+1(10-06) sweep 이후 읽음** "
        f"(① 기계 검사 {'예' if run_after_sweep else '🔴 아니오'}) | 같음 |")
    say(f"| ④ | 창 구간 `min(updated_at)` ≥ 10-06 15:35 (기록 · 통과 조건 아님) | `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` "
        f"**{v_probe[2]} ≥ 10-06 15:35: {'예' if v_probe[2] >= sweep else '아니오'}** · 적재 창 {v_lane[2]} ≥ 10-06 15:35: "
        f"{'예' if v_lane[2] >= sweep else '아니오'} | {MGR['min_upd']} ≥ 10-06 15:35: 예 |")
    say("| ⑤ | `P8-혼합빈티지신고` | §10 (걸침 창마다 한 줄 + 「전부 경계 후/전」 추가 줄) | PD-27 (바) |")
    say(f"| 관측 보관 | 착수 조건 관측(옮겨 적음 · 2차 출처) | — | 10-06 행수 {MGR['rows_1006']:,}(×3) · 10-07 행수 "
        f"{MGR['rows_1007']:,}(×3) · 관측 {MGR['run']} · 보관 `{MGR['src']}` |")
    say("")
    say("- 🔴 `updated_at` 은 sweep 이 전 표를 일괄 갱신한 값이라 빈티지 «증거»가 아니라 **읽은 시각의 기록**이다(PD-27 (라) · "
        "`P-3` 판별력 0 — 「통과」로 인용하지 않는다) · 「정규장만」 갈래 없음.")
    n_ex, n_in = len(POST10_EXACT), len(POST10_EXACT) + len(APPROX_BRANCHES)
    say(f"- **`D-3`**: *「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 {n_ex} / `approx` 포함 분모 {n_in}」* "
        "(PD-21 구성 예고 「없음」과 일치 · `approx` 0).")
    say("- 🆕 **`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)** (`PREREG_POST9.md` §1 (나)3 · 독법 B 병기 자리 없음) — "
        "🔴 재진입 갈래(§2-3)는 `approx` 갈래가 아니다(항등 아님 · 별도 인쇄).")
    say("- **`D-6`**: `n_up` 표준편차는 **`ddof=1` 을 앞에 · `ddof=0` 을 괄호로** 인쇄한다(§6-1) — "
        "*「SSOT = `ddof=1`(`PREREG_POST8.md` §6)」* · 🔴 `REG-M4` 문턱은 **중앙값 ≥ 30** 이지 sd 가 아니다.")
    say("- **`D-8`** · 🆕 **`P9-행단위`·`P9-결측분리`: 해당 없음** — 이 레인은 `prog_ver` 를 공변량으로 쓰지 않는다(수준 목록 · "
        "결측 n 줄은 `WRC-`·`RNK-`·`SEC-` 소관 · PD-26 · PD-34).")
    say("- **`P9-WRC누적분모`·`P9-갈래게이트인쇄전용`·`P9-수집증거`**: 해당 없음(다른 레인).")
    say("")

    # ── §0. 분모·플래그 ─────────────────────────────────────────────────────
    say("## 0. 분모 · 재진입 플래그 · 창 봉수\n")
    say("| 종목 | 코드 | 등록일 | 창 시작(D−19) | 창 봉수(**D 포함**) | D **이전** 봉수 | "
        "§1-5 재진입 | 직전 사이클 등록일 | **`P6-PRIOR_CYCLE_IN_WINDOW`** | PD-3 표 | 비고 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    flags = {}
    for r in r10:
        if not r["ok"]:
            say(f"| {r['name']} | {r['code']} | {r['reg']} | — | — | — | — | — | (봉 없음) | — | — |")
            continue
        pv = REENTRY.get(r["code"], [])
        flags[r["code"]] = int(any(d in r["win_dates"] for d in pv))
        memo = ("🔀 항목 내 재등록 9/29(🔒 #1 ⓐ · 「샌즈 제외」 = 인쇄만)" if r["code"] == SANDS_CODE else "—")
        say(f"| {r['name']} | {r['code']} | {r['reg']} | {r['win_start']} | {r['nwin']} | {r['nwin'] - 1} | "
            f"{'**예**' if pv else '아니오'} | {' · '.join(pv) if pv else '—'} | **{flags[r['code']]}** | "
            f"{PD3_FLAG[r['name']]} {'🟢' if flags[r['code']] == PD3_FLAG[r['name']] else '🔴 불일치'} | {memo} |")
    n_flag = sum(flags.values())
    say("")
    say(f"⇒ 🔴🔴 **`P6-PRIOR_CYCLE_IN_WINDOW` = 1 인 건 {n_flag}/{len(ok10)}**(PD-3 「4/9」 · §1-5 3 의무 인쇄) — 판정 분모 안 "
        "§1-5 재진입이 **있다**(4건 · 재진입 제외 표본 5).")
    say("⇒ 🔴 `approx` 갈래가 없다(0) ⇒ 갈래별 플래그 표 없음 · 「재진입 제외 민감도」와 「`approx` 제외 민감도」가 겹칠 일은 없다.")
    say("🔑 §1-5 3: ***이건 「제외」가 아니다 — 「이 건은 규칙상 통과할 수 없다」는 사실을 판정과 같은 무게로 인쇄하는 "
        "장치다***(이번 글은 해당 건 4 · 판정 자체는 9건 모두 분모에 넣는다).")
    say("")

    # ── §1. 비율 측정자 관측 ────────────────────────────────────────────────
    say("## 1. 등록일 **고가** == `[D−19, D]` 최고 고가 — 관측 (측정자 공용: §1-7 비율 항목 · §2 `P6-M1′`)\n")
    rp9 = measure(df, POST9P)
    rp8 = measure(df, POST8)
    r7 = measure(df, POST7)
    r6 = measure(df, POST6)
    r5 = measure(df, POST5)
    r4 = measure(df, POST4)
    h10, n10 = block(f"1-1. 10번째 글 `exact` {len(POST10_EXACT)}건 (**판정 표본**)", r10, "10번째 글 `exact`")
    hp9, np9 = block("1-1a. 9번째 글 `exact` 5건 — 같은 스냅샷 재계산 (참고 · 판정 대체 아님)", rp9, "9번째 글(재계산)")
    hp8, np8 = block("1-1b. 8번째 글 `exact` 4건 — 같은 스냅샷 재계산 (참고 · 판정 대체 아님)", rp8, "8번째 글(재계산)")
    h7, n7 = block("1-2. 7번째 글 `exact` 6건 — 같은 스냅샷 재계산 (참고 · 판정 대체 아님)", r7, "7번째 글(재계산)")
    h6, n6 = block("1-3. 6번째 글 10건 — 같은 스냅샷 재계산 (참고 · 판정 대체 아님)", r6, "6번째 글(재계산)")
    h5, n5 = block("1-4. 5번째 글 6건 — 같은 스냅샷 재계산 (참고 · 판정 대체 아님)", r5, "5번째 글(재계산)")
    h4, n4 = block("1-5. 4번째 글 6건 — 같은 스냅샷 재계산 (참고 · 판정 대체 아님)", r4, "4번째 글(재계산)")
    past_h, past_n = hp9 + hp8 + h7 + h6 + h5 + h4, np9 + np8 + n7 + n6 + n5 + n4
    say(f"⇒ **재계산 과거 {past_n}건 = {past_h}/{past_n} = {past_h/past_n*100:.1f}%** "
        f"(post9 {hp9}/{np9} · post8 {hp8}/{np8} · post7 {h7}/{n7} · post6 {h6}/{n6} · post5 {h5}/{n5} · post4 {h4}/{n4})")
    say(f"⇒ 동결 누적(`RESULTS_REGDAY_POST9_NUMBERS.md`) **{FROZEN_CUM[0]}/{FROZEN_CUM[1]}** + 이번 {h10}/{n10} = "
        f"**{FROZEN_CUM[0] + h10}/{FROZEN_CUM[1] + n10} = {(FROZEN_CUM[0] + h10)/(FROZEN_CUM[1] + n10)*100:.1f}%**")
    same = (past_h == FROZEN_CUM[0]) and (past_n == FROZEN_CUM[1])
    say(f"⇒ 재계산 {past_n}건 = {past_h}/{past_n} · 동결값 {FROZEN_CUM[0]}/{FROZEN_CUM[1]} ⇒ "
        + ("🟢 **일치** — 스냅샷 이동(창 종료 09-23 → 10-02 · 10-06 sweep 일괄 갱신)이 과거 등록일 측정치를 바꾸지 않았다"
           if same else "🔴 **불일치 — 스냅샷 이동이 과거 값을 바꿨다(조사 대상)**")
        + f" · post9 판정 표본 발표값 {FROZEN_P9[0]}/{FROZEN_P9[1]} ↔ 재계산 {hp9}/{np9} ⇒ "
        + ("🟢 일치" if (hp9, np9) == FROZEN_P9 else "🔴 불일치"))
    say("🔴🔴 **누적 분모 규약** — 누적은 **`exact` 기준**(post7 부터) · post10 은 신규 9 = `exact` 9 라 "
        "두 기준이 같다.\n")

    miss = [r for r in r10 if r["ok"] and not r["hit"]]
    say("### 1-6. ❌ 건 — 창 최고 고가를 «어느 날»이 잡았나 (기술 · 판정 아님)\n")
    if not miss:
        say("이번 글(`exact` 판정 표본) ❌ 건 **0** — ❌ = 등록일 고가 ≠ `[D−19, D]` 최고 고가(적중 실패)이다 · 동결값과의 «불일치»가 아니다(과거 재계산 ❌ 건은 1-1b~1-5 표).\n")
    else:
        say("| 종목 | 등록일 | 등록일 고가 | 창 최고 고가 | 그 고가를 낸 날 | 비고 |")
        say("|---|---|---|---|---|---|")
        for r in miss:
            say(f"| {r['name']} | {r['reg']} | {r['high']:,.0f} | {r['win_max_high']:,.0f} | "
                f"{' · '.join(r['argmax_dates'])} | `P6-PRIOR_CYCLE_IN_WINDOW` {flags.get(r['code'], 0)} |")
        say("\n🔴 **플래그 `P6-PRIOR_CYCLE_IN_WINDOW` 는 「직전 사이클 등록일이 창 안에 있다」는 사실일 뿐, "
            "「그 날의 고가가 막았다」는 뜻이 아니다.**\n")

    say("### 1-7. 비율 항목 판정 (`PREREG_Q1_V2.md` §3 `R2` · `PREREG_POST6.md` §4 #7)\n")
    obs10 = h10 / n10
    say("| 예측 ID | 출처 파일·절 | 문언·문턱 | 최소 n | 관측 | 판정(동결 문언 = 「비율 기록」) | ⛔ 판정 불가 조건 | "
        "D-11 병기 |")
    say("|---|---|---|---|---|---|---|---|")
    say(f"| **`Q1-R2`** | `PREREG_Q1_V2.md` §3 | 등록일 `exact` 건의 **≥ 50%** | {MIN_N} | "
        f"**{h10}/{n10} = {obs10*100:.1f}%** | {'문턱(≥ 50%) 충족' if obs10 >= R2_RATIO else '문턱(≥ 50%) 미달'} — "
        f"비율 기록 | 등록일 `exact` 건 < {MIN_N} ⇒ 이번 분모 {n10} ⇒ **미발동** | {Q1T} |")
    say("")
    say(f"- 대칭/반증 쌍 = **`REG-M4`**(§6) — `Q1-R2` 가 문턱을 넘어도 `n_up` 이 크면 「어느 급등주냐」는 못 말한다 {Q1T}")
    say("- 🔴 **`REG-M4` 의 인용 금지 지목 범위 = `M1` 과 그 승계 `P6-M1′` «만»**(`PREREG_POST8.md` §11 (나)1 · D-11) — "
        f"`Q1-R2` 는 이름이 적히지 않았다 ⇒ 인용 금지는 걸리지 않고, **대신 위 병기 의무**가 걸린다 {Q1T}")
    say("- 🔑 동결 문언이 *「등록일 `exact` 건」*이라 적혀 있다 — 이번 글은 신규(9) = `exact`(9) 라 두 기준이 갈리지 않는다(PD-4 1번).\n")

    # ── §2. P6-M1′ ──────────────────────────────────────────────────────────
    say("## 2. `P6-M1′` — 비율 ∧ 귀무 (AND · `PREREG_POST6.md` §3-1)\n")
    res = {}
    for mode, label in (("move", "**이동창**(§2 문언 「창이 뽑은 날에 함께 이동」) — **주 판정**"),
                        ("fixed", "고정창(뽑은 날과 무관하게 `[D−19,D]` 최고) — **의무 민감도**")):
        rng = np.random.default_rng(NULL_SEED)
        obs, p, ratios, per = null_p(ok10, rng, mode)
        res[mode] = (obs, p)
        say(f"### 2-{'1' if mode == 'move' else '2'}. {label}\n")
        say("| 종목 | 창봉수(**D 포함**) | 그 창에서 「그날이 창 최고」인 날 비율 |")
        say("|---|---|---|")
        for r, v in zip(ok10, per):
            say(f"| {r['name']} | {r['nwin']} | {v*100:.1f}% |")
        say("")
        say(f"- 관측 비율 **{obs*100:.1f}%** · 귀무 평균 **{ratios.mean()*100:.1f}%** · "
            f"귀무 중앙 **{np.median(ratios)*100:.1f}%** · 귀무 최대 **{ratios.max()*100:.1f}%**")
        say(f"- **p = P(귀무 비율 ≥ 관측) = {p:.5f}** ({int(round(p*NREP)):,}/{NREP:,})")
        say(f"- 귀무 백분위 < {ALPHA:.0%} ⇒ **{'충족' if p < ALPHA else '미달'}**\n")
    p_move, p_fixed = res["move"][1], res["fixed"][1]
    split_null = (p_move < ALPHA) != (p_fixed < ALPHA)

    say("### 2-3. 🔂 §1-5 재진입 민감도(**항등 아님** · 9↔5) · 🔀 「샌즈 제외」·「기업행위 건 제외」(**인쇄만**)\n")
    sub_re = [r for r in ok10 if r["code"] not in REENTRY]
    sub_flag = [r for r in ok10 if flags.get(r["code"], 0) == 0]
    sub_sa = [r for r in ok10 if r["code"] != SANDS_CODE]
    sub_co = [r for r in ok10 if r["name"] not in corp_k]
    sens = {}
    CO_TAG = "🔀 「기업행위 건 제외」"
    SA_TAG = "🔀 「샌즈 제외」"
    say("| 표본 | n | 일치 | 비율 | 이동창 p | 고정창 p | 비율 ≥ 83.33% | `P6-M1′` 결정규칙 | 지위 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for tag, sub, stat in (("전 건(주 판정)", ok10, "주"),
                           ("§1-5 재진입 제외", sub_re, "**항등 아님**(9↔5 · 계수 갈래)"),
                           ("플래그=1 건만 제외(참고)", sub_flag, "재진입 제외와 **같은 집합**(플래그 1 = 재진입 4건 · 중복 계수 안 함)"),
                           (SA_TAG, sub_sa, "**인쇄만 · 판정 효과 없음**(🔒 #1 ⓐ)"),
                           (CO_TAG, sub_co, "**답(참고) · 세지 않는다**(`F-3` (나))" + (" · 항등(k=0)" if not corp_k else ""))):
        if not sub:
            say(f"| {tag} | 0 | — | — | — | — | — | (표본 없음) | {stat} |")
            continue
        hh = sum(1 for r in sub if r["hit"])
        rt = hh / len(sub)
        pm = null_p(sub, np.random.default_rng(NULL_SEED), "move")[1]
        pf = null_p(sub, np.random.default_rng(NULL_SEED), "fixed")[1]
        sens[tag] = (rt, pm, pf, len(sub), hh)
        if tag == CO_TAG:   # `F-3` (나): 답 칸 낱말 = 「답(참고) · 세지 않는다」(판정 낱말 없음)
            say(f"| {tag} | {len(sub)} | {hh} | **{rt*100:.1f}%** | {pm:.5f} | {pf:.5f} | — | 답(참고) · 세지 않는다 | {stat} |")
        else:
            say(f"| {tag} | {len(sub)} | {hh} | **{rt*100:.1f}%** | {pm:.5f} | {pf:.5f} | "
                f"{'✅' if rt >= M1_RATIO else '❌'} | {rule_txt(verdict_and(rt >= M1_RATIO, pm < ALPHA))} | {stat} |")
    v_main = verdict_and(sens["전 건(주 판정)"][0] >= M1_RATIO, p_move < ALPHA)
    v_reent = verdict_and(sens["§1-5 재진입 제외"][0] >= M1_RATIO, sens["§1-5 재진입 제외"][1] < ALPHA)
    split_reentry = v_main != v_reent
    v_sa = verdict_and(sens[SA_TAG][0] >= M1_RATIO, sens[SA_TAG][1] < ALPHA)
    say("\n⇒ §1-5 재진입 제외(n 5)로 `P6-M1′` 결정규칙 결과가 "
        + ("**🔴 갈린다 — 재진입 의존**(주 " + rule_txt(v_main) + " ↔ 제외 " + rule_txt(v_reent) + ")" if split_reentry
           else "**🟢 갈리지 않는다**(항등이 아니라 실측 같은 방향 · 주 " + rule_txt(v_main) + " = 제외 " + rule_txt(v_reent) + ")") + ".")
    say("⇒ 🔀 「샌즈 제외」 결정규칙 결과 = " + rule_txt(v_sa)
        + (" — 주 판정과 **다르다**(🟡 기록만 · 판정 효과 없음 · 🔒 #1 ⓐ)" if v_sa != v_main
           else " — 주 판정과 같다(기록 · 판정 효과 없음)"))
    say("⇒ 🔀 「기업행위 건 제외」 = **답(참고) · 세지 않는다**(`F-3` (나) · 판정 낱말 없음)" + ("" if corp_k else " · k = 0 ⇒ 주와 같은 표본(항등)") + "\n")

    say("### 2-4. `P6-절단가드-A`/`B` (§1-6 3·4 · 산술 인쇄 · PD-12)\n")
    trunc = [r for r in ok10 if r["nwin"] < WIN]
    fires = guard_a_fires(len(trunc), len(ok10))
    say(f"- 절단 건(창 봉수 **< {WIN}봉**, 등록일 포함 셈) = **{len(trunc)}건**"
        + (" — " + " · ".join(f"{r['name']} {r['nwin']}/{WIN}" for r in trunc) if trunc else "")
        + f" / 분모 `exact` {len(ok10)}건 = **{len(trunc)/len(ok10)*100:.1f}%**")
    say(f"- `P6-절단가드-A`: {len(trunc)}/{len(ok10)} = {len(trunc)/len(ok10)*100:.1f}% "
        f"{'≥' if fires else '<'} 1/3 = 33.33% ⇒ **{'⛔ 판정 불가' if fires else '미발동'}** · PD-12 예고 **0/9**(절단 0) 와 "
        + ("🟢 일치" if len(trunc) == 0 else "🔴 다르다"))
    if trunc:
        sub_t = [r for r in ok10 if r["nwin"] == WIN]
        ht = sum(1 for r in sub_t if r["hit"])
        rt = ht / len(sub_t)
        pt = null_p(sub_t, np.random.default_rng(NULL_SEED), "move")[1]
        v_tr = verdict_and(rt >= M1_RATIO, pt < ALPHA)
        split_trunc = v_tr != v_main
        say(f"- `P6-절단가드-B`: 절단 제외 {ht}/{len(sub_t)} = {rt*100:.1f}% · p={pt:.5f} ⇒ {rule_txt(v_tr)} ⇒ "
            f"**{'⛔ 판정 불가(뒤집힘)' if split_trunc else '미발동'}**")
    else:
        say("- `P6-절단가드-B`: 절단 건 **0** ⇒ 제외 표본 = 전 표본(**항등**) ⇒ **뒤집힐 여지가 없다 · 미발동**")
        split_trunc = False
    say("- 🔴 문턱 `1/3` 은 `REC-Y3`(`RESULTS_RECONSTRUCT_POST4.md`)에서 **차용**한 값이며 **절단 비율에 대해 검증된 값이 "
        "아니다**(§1-6 6 고지 승계) · 🔑 봉수 표기 규약(N8): 전부 **등록일 포함** 셈.")
    say("- ⚠️ 이름 주의: 이 가드(`P6-절단가드-A` · 창 `[D−19, D]`)는 `LAD-` 레인의 `P6-창5절단가드-A`(`D-7`)와 **다른 가드**다.")
    say("")

    approx_meas: dict = {}          # `approx` 0 ⇒ 갈래·조합 없음(D-3 (나)4 대상 없음)
    combos: list = []
    comb_ratio: list = []
    m1_flip = r2_flip = False

    say("### 2-5. `P6-M1′` 종합 판정\n")
    say("| 항목 | 문언·문턱 (출처 파일·절) | 최소 n | 관측 | 판정 |")
    say("|---|---|---|---|---|")
    say(f"| 비율 | **≥ 5/6 = {M1_RATIO*100:.2f}%** · `PREREG_POST6.md` §3-1 | {MIN_N} | "
        f"**{obs10*100:.1f}%** | {'✅ 충족' if obs10 >= M1_RATIO else '❌ 미달'} |")
    say(f"| 귀무(이동창 · 주) | 백분위 **< 5%** · `PREREG_REGDAY_MEASURE.md` §4-1 | — | "
        f"**p={p_move:.5f}** | {'✅ 충족' if p_move < ALPHA else '❌ 미달'} |")
    say(f"| 귀무(고정창 · 민감도) | 두 갈래가 갈리면 ⛔ · `PREREG_POST6.md` §3-1 | — | "
        f"**p={p_fixed:.5f}** | {'🔴 갈림' if split_null else '🟢 같음'} |")
    blocked = []
    if len(ok10) < MIN_N:
        blocked.append("① 판정 건 < 3")
    if fires:
        blocked.append("② `P6-절단가드-A`")
    if split_trunc:
        blocked.append("③ `P6-절단가드-B`")
    if split_null:
        blocked.append("④ 두 귀무 갈래가 갈림")
    rule_ok = (obs10 >= M1_RATIO) and (p_move < ALPHA)
    if blocked:
        m1_verdict = "⛔ 판정 불가 — " + " · ".join(blocked)
        say(f"\n⇒ ⛔ **판정 불가** — 발동한 조건: {' · '.join(blocked)}")
    else:
        say("\n⇒ ⛔ 판정 불가 조건 ①~④ **전부 미발동**"
            f"(① {len(ok10)} ≥ {MIN_N} · ② 절단 {len(trunc)}건 · ③ 뒤집힘 없음 · ④ 두 귀무 갈래 동일)")
        if rule_ok:
            say("⇒ 🔒 **결정규칙 «비율 ≥ 0.8333 ∧ 귀무 백분위 < 5%» 는 두 성분 모두 «충족»됐다 — 🔴 «기록»이며, "
                "아래 의존 단서를 «먼저» 읽는다.**")
        else:
            say(f"⇒ 🔒 **결정규칙 «비율 ≥ 0.8333 ∧ 귀무 백분위 < 5%»** = {rule_txt(v_main)}")
        m1_verdict = None
    deps = []
    if split_reentry:
        deps.append("재진입 의존(§1-5 2)")
    if m1_flip:
        deps.append("등록일 정밀도 의존(§4-4 `approx` 갈래에서 비율 문턱이 갈린다 · `PREREG_POST8.md` §3 (나)4)")
    if m1_verdict is None:
        if deps:
            m1_verdict = ("⛔ 판정 불가 — " + " ∧ ".join(deps) + " ⇒ 🔴 선언 없음"
                          + (" (기록: 결정규칙 두 성분 충족)" if rule_ok else f" (기록: 결정규칙 = {rule_txt(v_main)})"))
            say("")
            say("⇒ 🔴🔴 **`P6-M1′` 판정 = 「선언 없음」** — " + " ∧ ".join(f"**{d}**" for d in deps)
                + ". `PREREG_POST8.md` §3 (나)4 — *「`exact` 갈래와 `approx` 포함 갈래가 둘 다 최소 n 을 채우고 답이 갈리면 ⇒ "
                  "⛔ 판정 불가 · 새 기호를 만들지 않는다」* · post7 의 「선언 없음」 문형(`RESULTS_REGDAY_POST7.md` §2) 그대로 — "
                  "🔑 ***이 항목의 «선두 기호»는 ✅ 가 아니다.***")
        else:
            m1_verdict = ("결정규칙 충족(비율 ∧ 귀무) — 의존 단서 없음" if rule_ok else rule_txt(v_main))
            say(f"\n⇒ 의존 단서(재진입 · 등록일 정밀도) **없음** ⇒ `P6-M1′` = **{m1_verdict}**")
    say("⇒ 🔀 「샌즈 제외」·「기업행위 건 제외」 결과는 **판정에 넣지 않는다**(인쇄만 · 🔒 #1 ⓐ · `F-3` (나)).")
    say("⇒ ⚠️ 여기에 `REG-M4`(§6)가 **하나 더** 겹친다 — 발동이면 *「`M1`·`P6-M1′` 을 선정 규칙으로 인용 금지」*.")
    say("")
    say("### 2-6. 🔴 인용 시 반드시 붙일 단서 (§3-1 · 필수)\n")
    say("> ***「등록일 고가 = 최근 20거래일 최고 고가」와 「등록일이 급등일」은 같은 진술이 아니다***"
        "(`RESULTS_REGDAY_POST5.md` §5-1-②).")
    say("⇒ **`REG-M1`(및 그 승계 `P6-M1′`)은 「급등일 등록」이 아니다.** 재는 것은 «국소 신고가»다.\n")

    # ── §3. P6-M2′ ──────────────────────────────────────────────────────────
    say("## 3. `P6-M2′` — 진짜 이분성 검정 (`PREREG_POST6.md` §3-2)\n")
    say("### 3-1. 건별 `r = C/H − 1` · 무리 분류 · 경계 근접성\n")
    say("| 종목 | 등록일 | **`r = C/H − 1`** | 분류 | `−5%` 경계까지(%p) | `−1%` 경계까지(%p) | 종가 등락 | 상한가 마감? |")
    say("|---|---|---|---|---|---|---|---|")
    for r in ok10:
        b = bucket(r["r"])
        d5 = (r["r"] - (-0.05)) * 100
        d1 = (r["r"] - (-0.01)) * 100
        lim = (r["ret_c"] >= LIMIT_UP) if r["ret_c"] == r["ret_c"] else False
        say(f"| {r['name']} | {r['reg']} | **{r['r']:+.2%}** | {b} | {d5:+.2f} | {d1:+.2f} | "
            f"{fmt_pct(r['ret_c'])} | {'🔴 **예**' if lim else '아니오'} |")
    b9 = [bucket(r["r"]) for r in ok10]
    n_ceil, n_pull, n_mid = b9.count("상한가형"), b9.count("되밀림형"), b9.count("🔴 중간대")
    say(f"\n⇒ 상한가형 **{n_ceil}** · 되밀림형 **{n_pull}** · 중간대 **{n_mid}** (분모 {len(ok10)})")
    tight = min(ok10, key=lambda r: min(abs(r["r"] + 0.05), abs(r["r"] + 0.01)))
    say(f"⇒ 가장 아슬아슬한 건 = **{tight['name']}** — 두 경계 중 가까운 쪽까지 "
        f"**{min(abs(tight['r'] + 0.05), abs(tight['r'] + 0.01))*100:.2f}%p** (경계 근접성은 판정과 같은 무게 · §3-2)\n")
    say("### 3-2. 전제 판정 — **양 무리 각 ≥ 2건** (없으면 검정 자체를 안 돌린다)\n")
    prem = (n_ceil >= CLUSTER_MIN) and (n_pull >= CLUSTER_MIN)
    say(f"- 전제(`PREREG_POST6.md` §3-2): 상한가형 ≥ {CLUSTER_MIN} **그리고** 되밀림형 ≥ {CLUSTER_MIN}")
    say(f"- 관측: 상한가형 **{n_ceil}** · 되밀림형 **{n_pull}** ⇒ "
        + ("**🟢 충족 — 검정을 돌린다**" if prem else "**⛔ 미충족 — 검정을 돌리지 않는다**"))
    say("- 🔑 §3-2: ***한 무리가 1건 이하면 「무리」가 아니라 「점」이다.*** 문턱 2 의 근거는 이 정의뿐이며 **관측값과 무관**하다.\n")

    def nup_r_array(d):
        v = [float(x[3]) / float(x[1]) - 1.0 for x in nup_rows(d)
             if x[1] and float(x[1]) > 0 and x[3] is not None]
        return np.asarray(v, dtype=float)

    say("### 3-3. `G* = max_gap / (max r − min r)` · 경험적 귀무\n")
    m2_extra = ""
    if not prem:
        say(f"⛔ **이분성 판정 불가 — 한 무리만 관측(상한가형 {n_ceil}건 · 되밀림형 {n_pull}건)**")
        say("")
        say("(동결 문언 그대로다 — `PREREG_POST6.md` §3-2: *「전제(양쪽 ≥2건)를 못 채우면 ⇒ ⛔ "
            "「이분성 판정 불가 — 한 무리만 관측(`상한가형 k건 · 되밀림형 m건`)」이라고 «그대로» 적는다. "
            "✅ 로 접지 않는다.」*)")
        say(f"⇒ **`G*` 와 귀무는 계산하지 않는다**(*「없으면 검정 자체를 안 돌린다」*). 중간대는 {n_mid}건이다.\n")
        g_obs = float("nan")
        m2_verdict = "⛔ 판정 불가(전제 미충족)"
        pA = pB = float("nan")
    else:
        rs8 = [r["r"] for r in ok10]
        g_obs = gstar(rs8)
        cands_a = [nup_r_array(r["reg"]) for r in ok10]
        say(f"- 관측 `G*` = **{g_obs:.4f}** (n={len(rs8)}) · 귀무 시드 **{NULL_SEED}** · **{NREP:,}** 반복")
        say("- 🔴 **문언이 두 갈래로 읽힌다 ⇒ 양쪽 다 인쇄한다**: 읽기 A = 각 «건»을 그 건 등록일 `n_up` 집합의 한 종목으로 치환 · "
            "읽기 B = 각 «등록일»의 `n_up` 집합에서 크기 n 비복원 추출")
        nullA = null_gstar_a(cands_a, np.random.default_rng(NULL_SEED))
        pA = float((nullA >= g_obs - 1e-12).mean())
        nullB, replB = null_gstar_b(cands_a, len(rs8), np.random.default_rng(NULL_SEED))
        pB = float((nullB >= g_obs - 1e-12).mean())
        say("")
        say("| 읽기 | 귀무 표본 | 귀무 평균 `G*` | 귀무 중앙 | **p = P(귀무 ≥ 관측)** | < 5% |")
        say("|---|---|---|---|---|---|")
        say(f"| **A**(주) | {len(nullA):,} | {nullA.mean():.4f} | {np.median(nullA):.4f} | **{pA:.5f}** | "
            f"{'✅' if pA < ALPHA else '❌'} |")
        say(f"| B(병기) | {len(nullB):,} | {nullB.mean():.4f} | {np.median(nullB):.4f} | **{pB:.5f}** | "
            f"{'✅' if pB < ALPHA else '❌'} |")
        if replB:
            say(f"\n🔴 읽기 B 에서 `n_up` 집합이 n 보다 작은 등록일 {len(replB)}건(크기 {sorted(replB)}) ⇒ 복원 추출로 대체.")
        if (pA < ALPHA) != (pB < ALPHA):
            m2_verdict = "⛔ **판정 불가 · 모호** — 귀무 문언이 두 갈래로 읽히고 두 읽기가 갈린다"
        else:
            m2_verdict = "✅ 지지" if pA < ALPHA else "⛔ 불성립"
        say(f"\n⇒ 결정규칙 «`G*` 의 귀무 백분위 < 5%» ⇒ **{m2_verdict}**\n")
    say("### 3-4. 제도 효과 분리 — 상한가 «마감» 건 (§3-2 필수)\n")
    lim_rows = [r for r in ok10 if r["ret_c"] == r["ret_c"] and r["ret_c"] >= LIMIT_UP]
    say(f"- 조작정의: **종가 등락 ≥ +{LIMIT_UP:.0%}**(제도 상한 +30%). 상한가형(`r ≥ −1%`) **{n_ceil}건** 중 상한가 마감 "
        f"**{len(lim_rows)}건**" + (" — " + ", ".join(r["name"] for r in lim_rows) if lim_rows else ""))
    if prem and lim_rows:
        rest = [r["r"] for r in ok10 if not (r["ret_c"] == r["ret_c"] and r["ret_c"] >= LIMIT_UP)]
        if len(rest) >= 2:
            say(f"- 상한가 마감 건을 뺀 `G*` = **{gstar(rest):.4f}** (n={len(rest)}) ↔ 전 건 `G*` = {g_obs:.4f}")
        else:
            say(f"- 상한가 마감 건을 빼면 n={len(rest)} ⇒ `G*` 정의 불가(2건 미만) — 값 없음")
    elif not prem:
        say("- 전제 미충족으로 `G*` 자체를 계산하지 않았다 ⇒ 제외 `G*` 도 없다(건수만 인쇄).")
    say("- 🔴 `RESULTS_REGDAY_POST5.md:158`: *「***골짜기의 오른쪽 벽은 저자 행동이 아니라 시장 제도가 만든다. "
        "인과로 읽지 말 것.***」*\n")
    say("### 3-5. 옛 `REG-M2` 규칙 병기 — 죽은 가드가 «죽어 있음»을 매회 증명한다\n")
    old_ok = (n_pull >= 1) and (n_mid == 0)
    say(f"- 옛 규칙(`PREREG_REGDAY_MEASURE.md` §4-2): «되밀림형 ≥ 1 **그리고** 중간대 = 0» ⇒ 관측: 되밀림형 {n_pull} · "
        f"중간대 {n_mid} ⇒ " + ("**✅ 자동 통과**" if old_ok else "**⛔ 불성립**"))
    if old_ok and not prem:
        say("- 🔴🔴 새 전제(양 무리 각 ≥2)는 «미충족»인데 옛 규칙은 **그대로 통과**한다 — 같은 표본에서 두 규칙이 정반대를 말한다.")
    say("")

    # ── §4. 창 규약 + P6-W10 ────────────────────────────────────────────────
    say("## 4. `PREREG_POST6.md` §1-4 **창 규약** + `P6-W10`(§1-4 용도) — **해당 없음** (`approx` 0 · PD-21)\n")
    say("> 🔴 post10 신규 9건은 전부 `exact` — 「8월 말」류 `approx` 갈래가 **없다** ⇒ §4 창 규약 갈래표 · 갈래별 측정 · "
        "`P6-W10` 무작위 «창» 귀무 · `approx` 포함 조합 민감도는 **대상이 없다**(`PREREG_POST10.md` 창 규약 대상 없음 · "
        "`PREREG_POST8.md` §3 (나)4 대상 없음).")
    say("> 🔴🔴 **`TV` 축의 `P6-W10` 과 «한 수로 합치지 않는다»** — `TV` 용도의 `P6-W10` 은 `D1_OOS` 산출물 소관(B1 레인)이며, "
        "이 문서의 `P6-W10`(§1-4 용도)은 **해당 없음**이다. ***두 용도는 서로 다른 수다.***")
    ap_nup: dict = {}
    ap_meds: list = []
    m4_flip = False
    w10_all = float("nan")
    degrade_w10 = False
    say("🟢 `approx` 포함 갈래가 없으므로 「등록일 정밀도 의존」 판정 불가 경로는 **열리지 않는다**(구성상 · 판별력 0).")
    say("")

    # ── §5. P6-M3′ ──────────────────────────────────────────────────────────
    say("## 5. `P6-M3′` (반증축) — 되밀림형 종가 위치 `(C−L)/(H−L)` (`PREREG_POST6.md` §3-3)\n")
    pull10 = [r for r in ok10 if bucket(r["r"]) == "되밀림형"]
    say("| 종목 | 등록일 | 고가 | 저가 | 종가 | **`(C−L)/(H−L)`** | 개별 (< 0.5) |")
    say("|---|---|---|---|---|---|---|")
    for r in pull10:
        say(f"| {r['name']} | {r['reg']} | {r['high']:,.0f} | {r['low']:,.0f} | {r['close']:,.0f} | "
            f"**{r['pos']:.3f}** | {'✅' if r['pos'] < 0.5 else '🔴 실패'} |")
    if not pull10:
        say("| (되밀림형 0건) | — | — | — | — | — | — |")
    pos10 = sorted(r["pos"] for r in pull10)
    n_fail = sum(1 for p in pos10 if p >= 0.5)
    if len(pull10) < MIN_PULL:
        m3_verdict = f"⛔ 판정 불가(되밀림형 {len(pull10)} < {MIN_PULL})"
        say(f"\n⇒ 되밀림형 **{len(pull10)}건 < 최소 n {MIN_PULL}** ⇒ ⛔ **판정 불가**(`PREREG_POST6.md` §4 #10 ⛔ 조건 「되밀림형 < 3」)")
        say("🔑 ⛔ 는 «선언» 금지이지 «인쇄» 금지가 아니다 — 위 표의 관측값은 그대로 남긴다.")
        fail_major = (n_fail * 2 > len(pos10)) if pos10 else None
    else:
        med10 = float(np.median(pos10))
        m3_ok = med10 < 0.5
        fail_major = n_fail * 2 > len(pos10)
        say(f"\n⇒ 되밀림형 **{len(pull10)}건** · 중앙값 **{med10:.3f}** · 범위 [{min(pos10):.3f}, {max(pos10):.3f}]")
        if m3_ok:
            m3_verdict = "✅ 통과"
        elif prem:
            m3_verdict = "🔴 실패 ⇒ `P6-M2′` 지지 취소"
        else:
            m3_verdict = "🔴 실패(취소할 `P6-M2′` 지지 없음)"
        say(f"⇒ 결정규칙 «중앙값 < 0.5»(문턱 불변) ⇒ **{m3_verdict}**")
    m2_has_support = m2_verdict.startswith("✅")
    tag_state = ("발동" if (fail_major and m2_has_support) else
                 ("미발동(제한할 `P6-M2′` 지지 없음)" if not m2_has_support else "미발동(개별 실패 과반 아님)"))
    say(f"⇒ 개별 실패(`≥ 0.5`) **{n_fail}/{len(pos10)}** · 과반 여부 **{('예' if fail_major else '아니오') if pos10 else '—(되밀림형 0)'}**")
    say(f"⇒ 🆕 **`[이름 인용 금지]` 꼬리표 = {tag_state}** — 🔴 `D-10`(`PREREG_POST8.md` §10-3 · PD-28): 꼬리표는 **이번 회차 "
        "이 축의 문언**(*「개별 실패가 분모의 «과반»이면 ⇒ `P6-M2′` 지지를 「되밀림」이라는 이름으로 인용 금지」*)으로 **다시 "
        "판정**했다 — 이전 회차(post6 · post7 · post8 · post9)의 꼬리표 결과를 **옮기지 않았다**.")
    p9pull = sorted(r["pos"] for r in rp9 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p8pull = sorted(r["pos"] for r in rp8 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p7pull = sorted(r["pos"] for r in r7 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p6pull = sorted(r["pos"] for r in r6 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p5pull = sorted(r["pos"] for r in r5 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p4pull = sorted(r["pos"] for r in r4 if r["ok"] and bucket(r["r"]) == "되밀림형")
    allpos = sorted(pos10 + p9pull + p8pull + p7pull + p6pull + p5pull + p4pull)
    if allpos:
        say(f"\n(참고 · 판정 아님) 되밀림형 종가 위치 누적 **{len(allpos)}건** 중앙 **{np.median(allpos):.3f}** — "
            f"post10 {len(pos10)}건 · post9 재계산 {len(p9pull)}건 · post8 재계산 {len(p8pull)}건 · post7 재계산 {len(p7pull)}건 · post6 재계산 {len(p6pull)}건 · "
            f"post5 {len(p5pull)}건 · post4 {len(p4pull)}건")
    say("")

    # ── §6. REG-M4 ──────────────────────────────────────────────────────────
    say("## 6. `REG-M4` (대칭 단언) — `n_up` (`PREREG_REGDAY_MEASURE.md` §4-4 · 매회 재판정)\n")
    say("### 6-0. `PREREG_POST6.md` §5-2 — 유니버스 `prev_close` 결손 공개 (5열 · 등록일마다)\n")
    say("| 등록일 | `universe_mcap` | `universe_test` | `dropped` | `drop_rate` | `prev_bar_date` |")
    say("|---|---|---|---|---|---|")
    drop_flag_days = []
    ex_days = sorted(set(r["reg"] for r in ok10))
    for d in ex_days:
        raw, rowsu, pbd = uni_cache[d]
        drop = raw - len(rowsu)
        rate = drop / raw if raw else float("nan")
        if rate >= DROP_GUARD:
            drop_flag_days.append((d, rate))
        say(f"| {d} | {raw:,} | {len(rowsu):,} | {drop:,} | "
            f"{'🔴 **' + f'{rate*100:.2f}%' + '**' if rate >= DROP_GUARD else f'{rate*100:.2f}%'} | {pbd} |")
    say(f"\n- 가드(§5-2 · 숫자 1%): `drop_rate ≥ {DROP_GUARD:.0%}` 인 날은 🔴 표시하고 **그날의 `n_up` 을 다른 날과 직접 비교하지 말 것**.")
    if drop_flag_days:
        for d, rate in drop_flag_days:
            say(f"  - 🔴 **{d}** — `drop_rate` {rate*100:.2f}% ⇒ **이 날의 `n_up` 은 다른 날과 직접 비교하지 말 것**")
    else:
        say(f"  - 🟢 이번 등록일 {len(ex_days)}일 전부 `drop_rate < {DROP_GUARD:.0%}` ⇒ 가드 미발동.")
    mism = []
    for d in ex_days:
        _raw, rowsu, pbd = uni_cache[d]
        k = sum(1 for x in rowsu if str(x[7]) != str(pbd))
        if k:
            mism.append((d, k))
    say("- " + ("⚠️ 종목별 `LAG(date)` 가 시장 직전 거래일과 다른 건수: " + " · ".join(f"{d}: {k}종목" for d, k in mism)
                if mism else "🟢 종목별 `LAG(date)` 가 전부 시장 직전 거래일과 같다."))
    say("- 편향 방향(§5-2): *「빼면 더 커질 뿐 작아지지 않는다」* ⇒ **`n_up` 결론은 강건**, 다만 **순위 진술은 과대**일 수 있다.\n")
    say("### 6-1. 건별 `n_up` 과 저자 종목의 자리\n")
    say("| 종목 | 등록일 | 검정 유니버스 | **`n_up`** | 본인이 `n_up` 안에? | `n_up` 안 `거래대금/시총` 순위 | 백분위 |")
    say("|---|---|---|---|---|---|---|")
    pcts, inset_n = [], 0
    for r in ok10:
        rowsu = uni_cache[r["reg"]][1]
        up = [(x[0], float(x[4]) / float(x[5])) for x in nup_rows(r["reg"]) if x[4] is not None and x[5]]
        nup = len(up)
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
    say(f"\n⇒ **`n_up` 중앙값 {med_nup:.1f}** · 범위 **[{min(nups)}, {max(nups)}]** · 표준편차 **{sd1:.2f}(`ddof=1`)** "
        f"({sd0:.2f} · `ddof=0`) — *「SSOT = `ddof=1`(`PREREG_POST8.md` §6)」*")
    say(f"⇒ 본인이 `n_up` 집합 «안»인 건 **{inset_n}/{len(ok10)}** — 밖인 건 **{len(ok10) - inset_n}건**"
        + (f" · 안에 있는 건의 `거래대금/시총` 백분위 중앙 **{np.median(pcts):.1f}**" if pcts else ""))
    say("🔴 sd 는 문턱이 아니다 — 이 절의 판정은 **중앙값**으로만 선다(`PREREG_POST8.md` §6 (다) · `PREREG_POST6.md:802`).")
    say("")
    say("### 6-2. 「`M1`·`P6-M1′` 을 선정 규칙으로 인용 금지」 — **매회 재판정**\n")
    ban = med_nup >= NUP_CITE_BAN
    say(f"- 문턱: `n_up` 중앙 **≥ {NUP_CITE_BAN}** ⇒ 인용 금지 (`PREREG_POST6.md` §4 #3 ← `PREREG_D1_OOS.md` §4 `N2`) · "
        "`PREREG_REGDAY_MEASURE.md` §4-4 의 자기 문언은 정성적(*「매일 수십 종목」*) — **둘 다 적는다**.")
    say(f"- 관측 중앙 **{med_nup:.1f}** ⇒ **"
        + ("🔴 발동 — `M1`/`P6-M1′` 을 「선정 규칙」으로 인용 금지" if ban
           else "🟢 미발동 — 이번 글에서는 인용 금지가 걸리지 않는다")
        + "** (정성 읽기 「매일 수십 종목」으로도 "
        + ("같은 결론" if (med_nup >= 10) == ban else "🔴 다른 결론 ⇒ 판정 불가·모호") + ")")
    say("- 🆕 **지목 범위 = `M1` 과 그 승계 `P6-M1′` «만»**(`PREREG_POST8.md` §11 (나)1 · `D-11` · 동결본 예시 "
        "`PREREG_GRADE_TIERS.md:65`) — 같은 측정자를 쓰는 비율 항목(§1-7)은 **이름이 적히지 않아** 인용 금지 대상이 아니고, "
        "대신 §1-7 의 병기 의무를 진다.")
    say("- 🔑 `REG-M4` 는 **자신이 반증축**이다(§4 #11) — 여기엔 판정 낱말이 없고 «인용 금지 발동/미발동»만 있다.\n")

    # ── §7. REG-M5 ──────────────────────────────────────────────────────────
    say("## 7. `REG-M5` (기록만 · 라이브 대조) — 되밀림형 `r` 분포\n")
    r10v = sorted(r["r"] for r in pull10)
    say("| 표본 | n | 중앙 | 최소 | 최대 |")
    say("|---|---|---|---|---|")
    if r10v:
        say(f"| 10번째 글 되밀림형 | {len(r10v)} | {np.median(r10v):+.2%} | {min(r10v):+.2%} | {max(r10v):+.2%} |")
    else:
        say("| 10번째 글 되밀림형 | 0 | — | — | — |")
    pv = {}
    for lbl, rr in (("9번째 글 되밀림형(재계산)", rp9), ("8번째 글 되밀림형(재계산)", rp8), ("7번째 글 되밀림형(재계산)", r7), ("6번째 글 되밀림형(재계산)", r6),
                    ("5번째 글 되밀림형(재계산)", r5), ("4번째 글 되밀림형(재계산)", r4)):
        vv = sorted(r["r"] for r in rr if r["ok"] and bucket(r["r"]) == "되밀림형")
        pv[lbl] = vv
        if vv:
            say(f"| {lbl} | {len(vv)} | {np.median(vv):+.2%} | {min(vv):+.2%} | {max(vv):+.2%} |")
    allv = sorted(r10v + sum(pv.values(), []))
    if allv:
        say(f"| 누적 | {len(allv)} | {np.median(allv):+.2%} | {min(allv):+.2%} | {max(allv):+.2%} |")
    say(f"\n라이브 `entry_band_up_pct` = **+{BAND_UP:.0%}** (그 위로 갭업하면 매수 포기).")
    say("🔴 **예측 아님 · 판정에 쓰지 않는다.** 저자 프로그램의 «매수 체결가»는 복원되지 않았다(🔒 결정 ④ — "
        "`PREREG_BUYLADDER` 계열 종결·기록 보존).")
    say(f"🔑 전 건 `r` 분포(참고): 중앙 {np.median([r['r'] for r in ok10]):+.2%} · "
        f"[{min(r['r'] for r in ok10):+.2%}, {max(r['r'] for r in ok10):+.2%}]\n")

    # ── §8. 부수 ────────────────────────────────────────────────────────────
    say("## 8. 부수 — 창 봉수 표기 · 축 밖 건\n")
    say("| 종목 | 창 요구 | 창 실제 봉수(**D 포함**) | D **이전** 봉수 | 영향 |")
    say("|---|---|---|---|---|")
    for r in ok10:
        say(f"| {r['name']} | {WIN}봉(D 포함) | {r['nwin']} | {r['nwin'] - 1} | "
            f"{'🔴 **창이 절단됐다**' if r['nwin'] < WIN else '정상'} |")
    say(f"\n⇒ 절단 **{len(trunc)}건** — PD-12 의 「`[D−19, D]` 20/20 전건 · 절단 0」과 " + ("🟢 일치" if not trunc else "🔴 불일치") + ".")
    say("")
    say("| 등록일 축 «밖» 건 | 코드 | 사유 |")
    say("|---|---|---|")
    for nm, code, why in POST10_FOLLOWUP:
        say(f"| {nm} | {code} | 🔁 후속({why}) — `reg_date` 비움 · `none` · 그 등록 사건은 앞선 글 신규 분모에서 **이미 계상**됐다"
            "(PD-2 · 이중계상 금지) |")
    say("")
    say("⚠️ 이 레인이 쓰는 창은 `[D−19, D]` 뿐이다 — 창5 `[D, D+4]`(post7 절단 값 대체 포함)는 `LAD-`·`ANC-` 레인 소관이다.")
    say("")

    # ── §9. D-5 갈래표 ──────────────────────────────────────────────────────
    say("## 9. 🆕 `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나)2 · PD-23)\n")
    say("> 최소 n 은 동결값 그대로(판정 건 3 · 되밀림형 3 · 양 무리 각 2) · 🔴 재진입 갈래 = **항등 아님**(9↔5 · 계수 갈래) · "
        "🔀 「샌즈 제외」(🔒 #1 ⓐ)·「기업행위 건 제외」(`F-3` (나))는 **인쇄만 — 계수에 넣지 않는다** · 항등 갈래도 「항등」으로 인쇄 · "
        "`approx` 갈래 0 ⇒ `D-3` (나)4 대상 없음.\n")

    def m2_for(sub):
        bk = [bucket(r["r"]) for r in sub]
        nc_, np_ = bk.count("상한가형"), bk.count("되밀림형")
        if not (nc_ >= CLUSTER_MIN and np_ >= CLUSTER_MIN):
            return "⛔ 판정 불가(전제 미충족)", nc_, np_
        rs_ = [r["r"] for r in sub]
        g_ = gstar(rs_)
        cands_ = [nup_r_array(r["reg"]) for r in sub]
        pa_ = float((null_gstar_a(cands_, np.random.default_rng(NULL_SEED)) >= g_ - 1e-12).mean())
        pb_ = float((null_gstar_b(cands_, len(rs_), np.random.default_rng(NULL_SEED))[0] >= g_ - 1e-12).mean())
        if (pa_ < ALPHA) != (pb_ < ALPHA):
            return "⛔ 판정 불가 · 모호", nc_, np_
        return ("✅ 지지" if pa_ < ALPHA else "⛔ 불성립"), nc_, np_

    def m3_for(sub):
        ps_ = sorted(r["pos"] for r in sub if bucket(r["r"]) == "되밀림형")
        if len(ps_) < MIN_PULL:
            return f"⛔ 판정 불가(되밀림형 {len(ps_)} < {MIN_PULL})", len(ps_), (float(np.median(ps_)) if ps_ else float("nan"))
        md_ = float(np.median(ps_))
        return ("✅ 통과" if md_ < 0.5 else "🔴 실패"), len(ps_), md_

    def m4_for(sub):
        md_ = float(np.median([len(nup_rows(r["reg"])) for r in sub]))
        return ("발동" if md_ >= NUP_CITE_BAN else "미발동"), md_
    m2_main, m2_re, m2_sa, m2_co = m2_for(ok10), m2_for(sub_re), m2_for(sub_sa), m2_for(sub_co)
    m3_main, m3_re, m3_sa, m3_co = m3_for(ok10), m3_for(sub_re), m3_for(sub_sa), m3_for(sub_co)
    m4_main, m4_re, m4_sa, m4_co = m4_for(ok10), m4_for(sub_re), m4_for(sub_sa), m4_for(sub_co)
    m2_split, m4_split = m2_main[0] != m2_re[0], m4_main[0] != m4_re[0]
    # 정정 1차(verifier B-2) — `P6-M3′` 은 최소 n(되밀림형 3) 미달 갈래의 값을 「갈렸다」의 근거로 쓰지 않는다(P8-갈래계수 `PREREG_POST8.md:337-343` · `REG-` 포함)
    m3_diff = m3_main[0] != m3_re[0]
    m3_split = m3_diff and m3_main[1] >= MIN_PULL and m3_re[1] >= MIN_PULL
    m3_below = m3_diff and not m3_split
    NMIN_NOTE = "최소 n 미달 — 갈림 근거 아님(P8-갈래계수 `PREREG_POST8.md:337-343`)"
    sr = sens["§1-5 재진입 제외"]
    q1_dir = (obs10 >= R2_RATIO) != (sr[0] >= R2_RATIO)
    dep_tag = " · 🔴 **재진입 의존**(§1-5 2 · 9↔5 두 값이 판정을 가름)"
    gap_txt = lambda f: "🔴 **판정이 갈린다 — 재진입 의존**" if f else "판정 같음"   # noqa: E731
    sa, co = sens[SA_TAG], sens[CO_TAG]
    r2_main = "문턱(≥ 50%) 충족" if obs10 >= R2_RATIO else "문턱(≥ 50%) 미달"
    say("| 예측 | 갈래 이름 | n | 답 | 계수에 넣나 | D-11 병기 |")
    say("|---|---|---|---|---|---|")
    for gname, n_s, ans_s, cnt in (
            ("주(`exact`)", str(len(ok10)), f"{h10}/{n10} = {obs10*100:.1f}% · {r2_main} — 비율 기록", "✅"),
            ("§1-5 재진입 포함↔제외", f"{len(ok10)} ↔ {len(sub_re)}",
             f"{sr[4]}/{sr[3]} = {sr[0]*100:.1f}% · {'문턱(≥ 50%) 충족' if sr[0] >= R2_RATIO else '문턱(≥ 50%) 미달'} — 비율 기록 · "
             + ("🟡 문턱 방향이 다르다(기록 · 판정은 「비율 기록」이라 불변)" if q1_dir else "문턱 방향 같음"), "✅(계수 갈래)"),
            ("창 절단 포함↔제외", f"{len(ok10)} ↔ {len(ok10) - len(trunc)}", "**항등**" if not trunc else "계산(§2-4)", "✅(= 주)"),
            ("🔀 「샌즈 제외」", str(sa[3]), f"{sa[4]}/{sa[3]} = {sa[0]*100:.1f}% — 인쇄만", "❌(🔒 #1 ⓐ 인쇄만)"),
            ("🔀 「기업행위 건 제외」", str(co[3]), f"답(참고) · 세지 않는다 — {co[4]}/{co[3]} = {co[0]*100:.1f}%"
             + ("" if corp_k else " · 항등(k=0)"), "❌(계수 아님 · `F-3` (나))"),
            ("`approx` 포함 조합", "0", "갈래 없음(`approx` 0) — 해당 없음", "—")):
        say(f"| `Q1-R2` | {gname} | {n_s} | {ans_s} | {cnt} | {Q1T} |")
    m1_ans = m1_verdict
    for gname, n_s, ans_s, cnt in (
            ("주(`exact` · 이동창)", str(len(ok10)), f"비율 {obs10*100:.1f}% · p={p_move:.5f} ⇒ {rule_txt(v_main)}", "✅"),
            ("귀무 고정창(민감도)", str(len(ok10)), f"p={p_fixed:.5f} ⇒ " + ("🔴 주와 갈림 ⇒ ⛔(④)" if split_null else "주와 같음"),
             "✅(§3-1 ④)"),
            ("§1-5 재진입 포함↔제외", f"{len(ok10)} ↔ {len(sub_re)}",
             f"비율 {sr[0]*100:.1f}% · p={sr[1]:.5f}(고정창 {sr[2]:.5f}) ⇒ {rule_txt(v_reent)} — {gap_txt(split_reentry)}", "✅(계수 갈래)"),
            ("플래그=1 건만 제외", f"{len(ok10)} ↔ {len(sub_flag)}", "재진입 제외와 **같은 집합**(중복 계수 안 함 · 답 동일)", "✅(= 재진입 제외)"),
            ("창 절단 포함↔제외", f"{len(ok10)} ↔ {len(ok10) - len(trunc)}", "**항등**" if not trunc else "계산(§2-4)", "✅(= 주)"),
            ("🔀 「샌즈 제외」", str(sa[3]), f"비율 {sa[0]*100:.1f}% · p={sa[1]:.5f} ⇒ {rule_txt(v_sa)} — 인쇄만", "❌(🔒 #1 ⓐ 인쇄만)"),
            ("🔀 「기업행위 건 제외」", str(co[3]), f"답(참고) · 세지 않는다 — 비율 {co[0]*100:.1f}% · p={co[1]:.5f}"
             + ("" if corp_k else " · 항등(k=0)"), "❌(계수 아님 · `F-3` (나))"),
            ("`approx` 포함 조합 · 비율", "0", "갈래 없음(`approx` 0) — 해당 없음", "—")):
        say(f"| `P6-M1′` | {gname} | {n_s} | {ans_s} | {cnt} | — |")
    say(f"| `P6-M1′` | ⇒ 종합 | — | **{m1_ans}** | — | — |")
    say(f"| `P6-M2′` | 주(`exact`) | {len(ok10)}(상한가형 {n_ceil} · 되밀림형 {n_pull}) | {m2_verdict} | ✅ | — |")
    if prem:
        say(f"| `P6-M2′` | 귀무 읽기 A / B | {len(ok10)} | p = {pA:.5f} / {pB:.5f} ⇒ "
            + ("🔴 갈림 ⇒ 판정 불가·모호" if (pA < ALPHA) != (pB < ALPHA) else "같음") + " | ✅ | — |")
    else:
        say("| `P6-M2′` | 귀무 읽기 A / B | — | 전제 미충족 ⇒ 계산 안 함 | — | — |")
    say(f"| `P6-M2′` | §1-5 재진입 포함↔제외 | {len(ok10)} ↔ {len(sub_re)} | 상한가형 {m2_re[1]} · 되밀림형 {m2_re[2]} ⇒ {m2_re[0]} — "
        f"{gap_txt(m2_split)} | ✅(계수 갈래) | — |")
    say(f"| `P6-M2′` | 🔀 「샌즈 제외」 | {sa[3]} | 상한가형 {m2_sa[1]} · 되밀림형 {m2_sa[2]} ⇒ {m2_sa[0]} — 인쇄만 | ❌(🔒 #1 ⓐ 인쇄만) | — |")
    say(f"| `P6-M2′` | 🔀 「기업행위 건 제외」 | {co[3]} | 답(참고) · 세지 않는다 — 상한가형 {m2_co[1]} · 되밀림형 {m2_co[2]}"
        + ("" if corp_k else " · 항등(k=0)") + " | ❌(계수 아님 · `F-3` (나)) | — |")
    say(f"| `P6-M3′` | 주(`exact` 되밀림형) | {len(pull10)} | {m3_verdict} · 꼬리표 {tag_state} | ✅ | — |")
    say(f"| `P6-M3′` | §1-5 재진입 포함↔제외 | {len(ok10)} ↔ {len(sub_re)} | 되밀림형 {m3_re[1]}건 ⇒ {m3_re[0]} — {NMIN_NOTE if m3_below else gap_txt(m3_split)} | "
        "✅(계수 갈래) | — |")
    say(f"| `P6-M3′` | 🔀 「샌즈 제외」 | {sa[3]} | 되밀림형 {m3_sa[1]}건 ⇒ {m3_sa[0]} — 인쇄만 | ❌(🔒 #1 ⓐ 인쇄만) | — |")
    say(f"| `P6-M3′` | 🔀 「기업행위 건 제외」 | {co[3]} | 답(참고) · 세지 않는다 — 되밀림형 {m3_co[1]}건 · 중앙 "
        + ("—" if m3_co[2] != m3_co[2] else f"{m3_co[2]:.3f}") + ("" if corp_k else " · 항등(k=0)") + " | ❌(계수 아님 · `F-3` (나)) | — |")
    say(f"| `REG-M4` | 주(`exact`) | {len(ok10)} | 중앙 {med_nup:.1f} ⇒ {'발동' if ban else '미발동'} | ✅ | — |")
    say(f"| `REG-M4` | §1-5 재진입 포함↔제외 | {len(ok10)} ↔ {len(sub_re)} | 중앙 {m4_re[1]:.1f} ⇒ {m4_re[0]} — {gap_txt(m4_split)} | "
        "✅(계수 갈래) | — |")
    say(f"| `REG-M4` | 🔀 「샌즈 제외」 | {sa[3]} | 중앙 {m4_sa[1]:.1f} — 인쇄만 | ❌(🔒 #1 ⓐ 인쇄만) | — |")
    say(f"| `REG-M4` | 🔀 「기업행위 건 제외」 | {co[3]} | 답(참고) · 세지 않는다 — 중앙 {m4_co[1]:.1f}"
        + ("" if corp_k else " · 항등(k=0)") + " | ❌(계수 아님 · `F-3` (나)) | — |")
    say("| `REG-M4` | `approx` 포함 조합 | 0 | 갈래 없음(`approx` 0) — 해당 없음 | — | — |")
    say("")
    dep_list = [n_ for n_, f_ in (("`P6-M1′`", split_reentry), ("`P6-M2′`", m2_split),
                                  ("`P6-M3′`", m3_split), ("`REG-M4`", m4_split)) if f_]
    say("⇒ **계수 결과**: " + ("`P6-M3′` 은 최소 n(되밀림형 3)을 채운 갈래 = 주 갈래 1개(재진입 제외 갈래는 되밀림형 "
                              f"{m3_re[1]} < 3 · 갈림 근거 아님) · " if m3_below else "")
        + "«판정» 답이 갈린 예측 = **"
        + (" · ".join(dep_list) if dep_list else "없음") + "**"
        + (f" · #7 비율 항목은 「비율 기록」이라 판정이 없고 문턱 방향만 {'다르다' if q1_dir else '같다'}(기록)") + ".")
    say("")

    # ── §10. D-9 혼합 빈티지 + 09-29 절단 대조 ──────────────────────────────
    say("## 10. 🆕 `D-9` · `P8-혼합빈티지신고` + 10-02 봉 영향 대조 (PD-27 (마) 4 · (바))\n")
    say("> 이 레인의 판정 창 = `[D−19, D]`(`PREREG_POST8.md:546` 「`REC-`/`REG-` = `[D−19, D]`」) · 적재 창 = "
        f"`[{LOAD_LO}, {DB_UPTO}]`. **걸치는 창마다 한 줄.**\n")
    say("| 건 | 창 시작 | 창 끝 | 경계 전 봉 | 경계 후 봉 | 걸침? | INTAKE §5 예고 |")
    say("|---|---|---|---|---|---|---|")
    cross, before_lines = [], []
    for r in ok10:
        nb = sum(1 for d in r["win_dates"] if d < REGIME)
        na = sum(1 for d in r["win_dates"] if d >= REGIME)
        cr = nb > 0 and na > 0
        if cr:
            cross.append(mixed_line(r["win_dates"][0], r["win_dates"][-1], nb, na) + f" ({r['name']} `[D−19, D]`)")
        elif na == 0:
            before_lines.append(f"창 `[{r['win_dates'][0]}, {r['win_dates'][-1]}]` 은 전부 제도 경계 전(전 {nb} / 후 0) ({r['name']} `[D−19, D]`)")
        say(f"| {r['name']} | {r['win_dates'][0]} | {r['win_dates'][-1]} | {nb} | {na} | "
            f"{'🔴 걸침' if cr else ('🟡 전부 전' if na == 0 else '안 걸침')} | {'전부 경계 전' if r['name'] == '서산' else '걸침'} |")
    ld = market_days(cur, LOAD_LO, DB_UPTO)
    lb, la = sum(1 for d in ld if d < REGIME), sum(1 for d in ld if d >= REGIME)
    say(f"| 적재 창(시장 달력) | {ld[0]} | {ld[-1]} | {lb} | {la} | {'🔴 걸침' if lb and la else '안 걸침'} | — |")
    if lb and la:
        cross.append(mixed_line(ld[0], ld[-1], lb, la) + " (적재 창)")
    say("")
    say("**의무 문장**(`PREREG_POST8.md` §9 (나)3 · 걸침 칸마다):\n")
    for ln in cross:
        say(f"- {ln}")
    if not cross:
        say("- (걸침 창 없음)")
    n_cj = len(cross) - (1 if lb and la else 0)
    say("")
    say("**추가 줄**(「전부 경계 전」 · PD-27 (바) 재량):\n")
    for ln in before_lines or ["(해당 창 없음)"]:
        say(f"- {ln}")
    say("")
    x19_ok = n_cj == 8 and len(before_lines) == 1 and "서산" in before_lines[0]
    say(f"⇒ **판정 창 걸침 = {n_cj}건** — INTAKE §5 예고(걸침 8줄 + 서산 「전부 경계 전」 줄)와 "
        + ("🟢 **일치**(건수 · 서산 전부 전)" if x19_ok else "🔴 **불일치 — 조사 대상(값 불변 인쇄)**") + ".")
    say(f"⇒ 등록일 봉 자체가 제도 경계 «후»인 건 = **{sum(1 for r in ok10 if r['reg'] >= REGIME)}/{len(ok10)}**(기록만 · 판정에 안 씀).")
    say("")
    say("### 10-1. 🆕 `P10-기업행위봉`(`F-3` · `PREREG_POST10.md` §3 (나)) — 창 = `[D−19, D]`\n")
    say("| 종목 | 창 | ⓐ `split` 행 | ⓑ `volume = 0` 봉 | 기록 줄 — 창 안 `corp_events` 전 행 | ⓒ(기록 줄) 거래정지 제목 |")
    say("|---|---|---|---|---|---|")
    for r in ok10:
        sc = corp[r["name"]]
        say(f"| {r['name']} | `[{r['win_dates'][0]}, {r['win_dates'][-1]}]` | {len(sc['split'])} | {len(sc['vol0'])} | "
            + (" · ".join(f"{t} {d}" for t, d, _x in sc["allrows"]) or "—") + " | "
            + (" · ".join(f"{d} {t}" for d, t in sc["halt"]) or "0") + " |")
    say("")
    say(f"- 🔴 **`P10-기업행위봉`: 기업행위 건 {len(corp_k)}/{len(ok10)} — "
        + ("; ".join(f"{nm}: {corp_reason(corp[nm])}" for nm in corp_k) if corp_k else "ⓐ 0 · ⓑ 0(건별 사유 없음)")
        + " · `adj_factor` 산술 0 · 처리 = (나)**")
    say("- 인테이크 예고(PD-36): ⓐ **0/9** — 이번 측정 ⓐ " + str(sum(1 for r in ok10 if corp[r["name"]]["split"])) + "/9 · ⓑ 는 «레인 · 착수 뒤» 집계"
        "(`F-3` (나)6 · 이 줄이 그 집계) · 「기업행위 건 제외」 갈래 값 = §2-3 · §9(답(참고) · 세지 않는다 · 판정 불변).")
    say("- 🔴 **이 스크립트는 거래정지 구간 봉의 패딩 여부를 «판별하지 않는다»** — 가격·거래량을 조정하지 않는다(규칙 불변).")
    say("")
    df_cut = load_prices(codes, DB_UPTO_CUT)
    r10c = measure(df_cut, POST10_EXACT)
    keys_cmp = ("hit", "nwin", "high", "low", "close", "r", "ret_c")
    same_cut = all(all(a[k] == b[k] for k in keys_cmp) for a, b in zip(ok10, [x for x in r10c if x["ok"]]))
    say(f"⇒ **10-02 봉 영향 대조**(PD-27 (마) 4): 가격을 **{DB_UPTO_CUT}** 까지만 적재해 같은 측정자를 다시 쟀다 — `exact` "
        f"{len(ok10)}건의 일치·봉수·OHLC·`r`·등락 ⇒ "
        + ("**🟢 전부 동일 — 09-30 이후 봉은 이 레인의 판정값에 들어가지 않는다**" if same_cut
           else "**🔴 다르다 — 조사 대상(값 불변 인쇄)**") + " · `n_up` 은 등록일(≤ 09-29) 단면이라 영향 경로가 없다.")
    say("🔴 **방향 추론은 실측으로 인용하지 않는다**(`PREREG_POST8.md` §9 (마)) · 「정규장만」 갈래 없음.")
    say("")

    # ── §11. 판정 요약 · 배선 점검 · 의무 체크리스트 ───────────────────────
    say("## 11. 판정 요약 — `PREREG_POST6.md` §4 #7~#12 형식 (등급 열 없음)\n")
    say("| # | 항목 | 문턱 (출처 파일) | 최소 n | 관측 | **판정** | 대칭/반증 쌍 · ⛔ 조건 |")
    say("|---|---|---|---|---|---|---|")
    r2_cell = (f"{r2_main} — **비율 기록**(동결 문언 `:66`)"
               + (" · 🔴 `approx` 갈래에서 갈림 ⇒ ⛔ 판정 불가(`D-3` (나)4)" if r2_flip else ""))
    say(f"| 7 | `Q1-R2` | ≥ 50% · `PREREG_Q1_V2.md` §3 | {MIN_N} | {h10}/{n10} = {obs10*100:.1f}% | {r2_cell} | "
        f"`REG-M4` · `exact` < 3 ⇒ 미발동 · {Q1T} |")
    say(f"| 8 | `P6-M1′` | ≥ 0.8333 ∧ < 5% · `PREREG_REGDAY_MEASURE.md` §4-1 + `PREREG_POST6.md` §3-1 | {MIN_N} | "
        f"비율 {obs10*100:.1f}% · p={p_move:.5f}(고정창 {p_fixed:.5f}) | **{m1_verdict}** | "
        f"`REG-M4`({'발동 ⇒ 선정 규칙 인용 금지' if ban else '미발동'}) · 절단 {len(trunc)}/{len(ok10)} |")
    c9 = f"**{m2_verdict}**" + (dep_tag if m2_split else "")
    c10 = f"**{m3_verdict}** · 꼬리표 {tag_state}" + (dep_tag if m3_split else "")
    c11 = f"**{'🔴 발동 — `M1`·`P6-M1′` 인용 금지' if ban else '🟢 미발동'}**" + (dep_tag if m4_split else "")
    say(f"| 9 | `P6-M2′` | 귀무 백분위 < 5% · `PREREG_POST6.md` §3-2 | 양 무리 각 ≥ 2 | 상한가형 {n_ceil} · 되밀림형 {n_pull} · "
        f"중간대 {n_mid}" + (f" · `G*` {g_obs:.4f} · p(A) {pA:.5f}" if prem else "") + f" | {c9} | `P6-M3′` |")
    say(f"| 10 | `P6-M3′` | < 0.5 · `PREREG_REGDAY_MEASURE.md` §4-3 | 되밀림형 3 | 되밀림형 {len(pull10)}건"
        + (f" · 중앙 {np.median(pos10):.3f}" if pos10 else "") + f" | {c10} | "
        "개별 실패 과반 → 이름 인용 금지(D-10 재판정) |")
    say(f"| 11 | `REG-M4` | ≥ 30 ⇒ 인용 금지 · `PREREG_D1_OOS.md` §4 `N2` | — | 중앙 {med_nup:.1f} · [{min(nups)}, {max(nups)}] · "
        f"sd {sd1:.2f}(`ddof=1`) ({sd0:.2f} · `ddof=0`) | {c11} | "
        "자신이 반증축 · 지목 = `M1`·`P6-M1′` 만(D-11) |")
    say(f"| 12 | `REG-M5` | 없음 · `PREREG_REGDAY_MEASURE.md` §4-5 | — | 되밀림형 `r` "
        + (f"중앙 {np.median(r10v):+.2%}" if r10v else "0건") + " ↔ 라이브 밴드 +3% | (판정 없음 · 기록만) | 판정 금지 조항 |")
    say("| — | `P6-W10`(§1-4 용도) | ≥ 50% ⇒ 강등 · `PREREG_D1_OOS.md` §4(`TV-W7` 상속) | — | 해당 없음(`approx` 0) | "
        "**해당 없음** | `TV` 용도와 한 수로 합치지 않는다(B1 레인 소관) |")
    say("")
    say("### 11-1. 🔴 배선 점검 — 발화한 가드가 판정 칸에 «실제로» 걸렸는가 (post7 교훈 ①)\n")
    say("| 가드 | 상태 | 걸려야 하는 판정 칸 | 칸에 반영됐나 |")
    say("|---|---|---|---|")
    wires = [
        ("`REG-M4`(n_up 중앙 ≥ 30)", "발동" if ban else "미발동", "#8 `P6-M1′` 인용 금지 단서", True),
        ("`P6-절단가드-A`", "발동" if fires else "미발동", "#7·#8", (not fires) or m1_verdict.startswith("⛔")),
        ("`P6-절단가드-B`", "발동" if split_trunc else "미발동(항등)", "#8", (not split_trunc) or m1_verdict.startswith("⛔")),
        ("귀무 두 갈래(④)", "갈림" if split_null else "같음", "#8", (not split_null) or m1_verdict.startswith("⛔")),
        ("`D-3` (나)4 정밀도 의존 — `P6-M1′`", "발동" if m1_flip else "미발동", "#8",
         m1_verdict.startswith("⛔") == (m1_flip or bool(blocked) or split_reentry)),
        ("`D-3` (나)4 정밀도 의존 — #7 비율 항목", "발동" if r2_flip else "미발동", "#7", ("⛔" in r2_cell) == r2_flip),
        ("`P6-M2′` 전제", "충족" if prem else "미충족", "#9", prem or m2_verdict.startswith("⛔")),
        ("`P6-M3′` 최소 n", "충족" if len(pull10) >= MIN_PULL else "미달", "#10",
         (len(pull10) >= MIN_PULL) or m3_verdict.startswith("⛔")),
        ("`drop_rate ≥ 1%`", "발동" if drop_flag_days else "미발동", "§6-0 비교 금지 문구", True),
        ("§1-5 재진입 의존(9↔5)", "발동 — " + " · ".join(dep_list) if dep_list
         else "미발동(두 값이 판정을 가르지 않음" + (" · `P6-M3′` 재진입 제외 갈래는 최소 n 미달 — 갈림 근거 아님" if m3_below else "") + ")", "#8~#11",
         ((not split_reentry) or "재진입 의존" in m1_verdict) and ("재진입 의존" in c9) == m2_split
         and ("재진입 의존" in c10) == m3_split and ("재진입 의존" in c11) == m4_split),
        ("「샌즈 제외」·「기업행위 건 제외」", "인쇄만", "없음(판정 효과 없음)", True),
    ]
    for g, s_, tgt, okw in wires:
        say(f"| {g} | {s_} | {tgt} | {'🟢 예' if okw else '🔴 **아니오 — 배선 결함**'} |")
    assert all(w[3] for w in wires), "배선 결함"
    say("")
    say("### 11-2. `PREREG_POST8.md` 인쇄 의무 체크리스트 (이 산출물)\n")
    say("| 의무 | 이 레인 해당 | 자리 |")
    say("|---|---|---|")
    say("| `D-3`(`P8-approx의존신고`) | **해당** | §0-A |")
    say("| `D-5`(`(갈래 이름, n, 답)`) | **해당** | §9 |")
    say("| `D-6`(REG 레인 두 값 병기 + SSOT 줄) | **해당** | §6-1 · §11 |")
    say("| `D-9`(①~⑤) | **해당** | §0-A · §10 |")
    say("| `D-10`(`P6-M3′` 꼬리표 재판정) | **해당** | §5 |")
    say("| `D-11`(#7 비율 항목 인용 병기 · 같은 줄 판정 낱말 금지) | **해당** — `say()` 가 줄마다 기계 검사 | 전편 |")
    say("| `D-1`·`D-2`·`D-4`·`D-7`·`D-8` | 해당 없음(다른 레인 · 공변량 미사용) | — |")
    say("| `P9-공통독법` | **해당**(대상 없음 신고) | §0-A |")
    say("| `P9-행단위`·`P9-결측분리` | **해당 없음** 신고 | §0-A |")
    say("| `P9-스탬프통일`(`regday_post10/read_stamp.json`) | **해당** | 머리말 · §0-A |")
    say("| `P6-PRIOR_CYCLE_IN_WINDOW` 4/9 의무 인쇄 | **해당** | §0 |")
    say("| `P9-WRC누적분모`·`P9-갈래게이트인쇄전용`·`P9-수집증거` | 해당 없음(다른 레인) | §0-A |")
    say("| 🆕 `F-3` `P10-기업행위봉` 신고 줄 · 「기업행위 건 제외」 갈래 · PD-27 (바) 걸침 | **해당** | §2-3 · §9 · §10 · §10-1 |")
    say("| 라이브 채택 금지(§0-1 문언 축자) | **해당** | 머리말 |")
    say("")
    say(f"🔴 **{WINDOW_LINE}** · **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)**.")
    say("🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST10.md` §0-1).")

    conn.close()
    (BASE / OUT_NAME).write_bytes(("\n".join(OUT) + "\n").encode("utf-8"))
    note(f"[written] {OUT_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
