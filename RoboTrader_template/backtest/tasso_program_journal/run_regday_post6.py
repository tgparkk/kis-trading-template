# -*- coding: utf-8 -*-
"""6번째 글 등록일 축 — `Q1-R2` · `P6-M1′` · `P6-M2′` · `P6-M3′` · `REG-M4` · `REG-M5`.

`run_regday_post5.py` 를 **승계**한 post6 판이다(원본은 손대지 않는다).

준거(전부 계산 «전» 동결):
  · `PREREG_POST6.md` §0-3(접두 표기) · §1-5(재진입) · §1-6(절단가드 A/B · 봉수 표기)
    · §2-2 · §3-1(`P6-M1′`) · §3-2(`P6-M2′`) · §3-3(`P6-M3′`) · §4 #7~#12 · §5-2(5열·drop_rate)
  · `PREREG_REGDAY_MEASURE.md` §4 · `PREREG_Q1_V2.md` §3 `R2`
  · `PREDECISION_2026-09-04_post6.md` PD-1(창 종료 = 발행 당일 봉 포함) · PD-2(후속 2건 분모 밖)
    · PD-3(재진입 2건 · `P6-PRIOR_CYCLE_IN_WINDOW`) · PD-9(절단 0)
  · `INTAKE_2026-09-04_post6.md` §1(신규 10건) · §5

동결 문언 준수 사항:
  · 창 `[D−19, D]` = **D 를 «포함»한 직전 20거래일** — 봉수는 반드시 「등록일 포함/직전」을 명시(§1-6 7)
  · 귀무 **시드 20260815 · 20,000 반복**(승계) · 이동창이 주(主) · 고정창은 **의무 민감도**
  · `P6-M1′` 결정규칙 = **비율 ≥ 0.8333 ∧ 귀무 백분위 < 5%** (AND) · 갈리면 🟡 부분 충족(인용 금지)
  · `P6-M2′` 전제 = **양 무리 각 ≥ 2건** — 못 채우면 **검정을 안 돌리고** 문언 그대로 ⛔ 를 적는다
  · `P6-M3′` 판정은 **중앙값 < 0.5** · 개별 실패가 **과반**이면 「되밀림」이라는 «이름» 인용 금지
  · `REG-M4` 는 **매회 재판정**(상수가 아니다) · `REG-M5` 는 **기록만**(판정 금지)

🔴 이 산출물은 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).
🔴 결과 문서 안에서 **새 예측을 만들지 않는다**(`RESULTS_REGDAY_POST5.md` §10 처리 승계).
라이브 트리 import 0건. DB 는 SELECT 만. 시드·반복 고정이라 **두 번 실행하면 byte 동일**이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DB_UPTO = "2026-09-04"       # PD-1: 발행일 = 거래일 = DB 최대일 · 창 종료 = 발행 당일 봉 «포함»
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
MIN_N = 3                    # 최소 n (신규 건)
MIN_PULL = 3                 # P6-M3′ 최소 n (되밀림형)
CLUSTER_MIN = 2              # P6-M2′ 전제 — 양 무리 각 ≥ 2 (PREREG_POST6.md §3-2 신규 문턱)
TRUNC_GUARD = 1.0 / 3.0      # P6-절단가드-A (§1-6 3 · REC-Y3 차용 고지)
DROP_GUARD = 0.01            # §5-2 drop_rate 가드 1% (PREREG_POST6.md §5-2 신규 문턱)
NUP_CITE_BAN = 30            # REG-M4 재판정 문턱 (PREREG_POST6.md §4 #3 ← PREREG_D1_OOS.md §4 N2)
LIMIT_UP = 0.29              # 상한가 «마감» 조작정의: 종가 등락 ≥ +29% (제도 상한 +30%)

# ── 분모 = 6번째 글 «신규» 10건 (INTAKE §1) ──────────────────────────────────
# 🔴 후속 2건(광전자 017900 · 삼양바이오팜 0120G0)은 PD-2 2번대로 등록일 축 분모에서 «제외»한다
#    (이중계상 금지 — 그 등록 사건은 post5 신규 분모에서 이미 계상됐다).
POST6_NEW = [
    ("한라캐스트",       "125490", "2026-08-21"),
    ("헥토파이낸셜",     "234340", "2026-08-28"),
    ("아난티",           "025980", "2026-08-19"),
    ("아이티센글로벌",   "124500", "2026-08-20"),
    ("현대약품",         "004310", "2026-09-01"),
    ("원익",             "032940", "2026-08-31"),
    ("쿠콘",             "294570", "2026-08-28"),
    ("지투파워",         "388050", "2026-08-26"),
    ("우리기술투자",     "041190", "2026-08-25"),
    ("비에이치",         "090460", "2026-09-01"),
]
# 재진입(2번째 사이클) — PD-3. 직전 사이클 등록일(없으면 None = 저자 미명시).
REENTRY = {"388050": "2026-08-13",   # 지투파워 — post4 #4
           "004310": None}           # 현대약품 — 07-31 글 #12 · 등록일 미명시(none)
PD3_FLAG = {"388050": 1, "004310": 0}   # PD-3 표가 «계산 전»에 못박은 값 — 대조용

# 참고 재계산(판정 대체 아님) — post5·post4 신규 건
POST5 = [
    ("혜인",             "003010", "2026-08-11"),
    ("한국화장품제조",   "003350", "2026-08-12"),
    ("코데즈컴바인",     "047770", "2026-08-21"),
    ("한켐",             "457370", "2026-08-20"),
    ("삼양바이오팜",     "0120G0", "2026-08-21"),
    ("광전자",           "017900", "2026-08-05"),
]
POST4 = [
    ("이노테크",         "469610", "2026-08-13"),
    ("한켐",             "457370", "2026-08-12"),
    ("금호건설",         "002990", "2026-08-12"),
    ("지투파워",         "388050", "2026-08-13"),
    ("PS일렉트로닉스",   "332570", "2026-08-13"),
    ("코데즈컴바인",     "047770", "2026-08-19"),
]
FROZEN_CUM = (11, 12)        # RESULTS_REGDAY_POST5 계열 누적(post4 6/6 + post5 5/6) — 대조용


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


# ── DB ───────────────────────────────────────────────────────────────────────
def load_prices(codes):
    conn = psycopg2.connect(**DSN)
    q = ("SELECT stock_code, date, open, high, low, close, trading_value, market_cap "
         "FROM daily_prices WHERE stock_code = ANY(%s) AND date BETWEEN '2026-01-01' "
         f"AND '{DB_UPTO}' AND close > 0 ORDER BY stock_code, date")
    df = pd.read_sql(q, conn, params=(list(codes),))
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def universe_raw_count(cur, d):
    """그날 `market_cap>0` 인 종목 수 (prev_close 필터 «전») = §5-2 `universe_mcap`."""
    cur.execute(
        "SELECT count(*) FROM daily_prices WHERE date=%s AND close > 0 "
        "AND market_cap IS NOT NULL AND market_cap > 0 AND NOT (stock_code = ANY(%s))",
        (d, list(PSEUDO)))
    return int(cur.fetchone()[0])


def prev_trading_day(cur, d):
    """시장 전체의 직전 거래일 = §5-2 `prev_bar_date`."""
    cur.execute("SELECT max(date) FROM daily_prices WHERE date < %s AND close > 0", (d,))
    v = cur.fetchone()[0]
    return v if v else "—"


def load_universe_day(cur, d):
    """등록일 유니버스 (그날 + 직전 거래일 종가). 의사티커 제외 · market_cap>0.

    🔑 `daily_prices.date` 는 **text** 컬럼이다(ISO 'YYYY-MM-DD') — 날짜 산술을 SQL 에서 하면
       `text >= timestamp` 로 죽는다. 하한을 파이썬에서 문자열로 만들어 넘긴다
       (`RESULTS_REGDAY_POST5.md` §7-5).
    """
    lo = (pd.Timestamp(d) - pd.Timedelta(days=20)).date().isoformat()
    cur.execute(
        "WITH u AS (SELECT stock_code, date, high, low, close, trading_value, market_cap, "
        "  LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close, "
        "  LAG(date)  OVER (PARTITION BY stock_code ORDER BY date) AS prev_date "
        "  FROM daily_prices WHERE date BETWEEN %s AND %s AND close > 0) "
        "SELECT stock_code, high, low, close, trading_value, market_cap, prev_close, prev_date "
        "FROM u WHERE date = %s AND market_cap IS NOT NULL AND market_cap > 0 "
        "AND prev_close IS NOT NULL AND prev_close > 0 AND NOT (stock_code = ANY(%s))",
        (lo, d, d, list(PSEUDO)))
    return cur.fetchall()


# ── 측정 ─────────────────────────────────────────────────────────────────────
def per_stock(df, code):
    m = df[df.stock_code == code].reset_index(drop=True)
    h = m.high.to_numpy(dtype=float)
    # is20h[i] = high[i] 가 «i 를 포함한 직전 20거래일» 최고 고가와 같다 (이동창)
    roll = pd.Series(h).rolling(WIN, min_periods=1).max().to_numpy()
    m = m.assign(is20h=(h >= roll - EPS))
    return m


def measure(df, items):
    """각 건의 등록일 측정자. 창 봉수는 **등록일 D 를 포함**한 셈이다(§1-6 7 · N8)."""
    rows = []
    for nm, code, reg in items:
        m = per_stock(df, code)
        D = pd.Timestamp(reg)
        idx = m.index[m.date == D]
        if len(idx) == 0:
            rows.append(dict(name=nm, code=code, reg=reg, ok=False))
            continue
        i = int(idx[0])
        w0 = max(0, i - WIN + 1)
        win = m.iloc[w0:i + 1]
        o, h, l, c = (float(m.open[i]), float(m.high[i]),
                      float(m.low[i]), float(m.close[i]))
        prev_c = float(m.close[i - 1]) if i >= 1 else float("nan")
        rows.append(dict(
            name=nm, code=code, reg=reg, ok=True, i=i, nwin=len(win),
            win_start=str(win.date.iloc[0].date()),
            high=h, low=l, close=c, open=o, prev_close=prev_c,
            win_max_high=float(win.high.max()),
            hit=bool(h >= float(win.high.max()) - EPS),
            r=c / h - 1.0,
            pos=(c - l) / (h - l) if h > l else float("nan"),
            ret_c=c / prev_c - 1.0 if prev_c == prev_c else float("nan"),
            ret_h=h / prev_c - 1.0 if prev_c == prev_c else float("nan"),
            win_dates=[str(x.date()) for x in win.date],
            argmax_dates=[str(d.date()) for d, hv in zip(win.date, win.high)
                          if float(hv) >= float(win.high.max()) - EPS],
            win_is20h=win.is20h.to_numpy().copy(),
            win_high=win.high.to_numpy(dtype=float).copy(),
        ))
    return rows


def null_p(rows, rng, mode):
    """`P6-M1′` 귀무: 각 건마다 창 안 무작위 날을 뽑아 같은 판정. mode='move'|'fixed'."""
    obs = float(np.mean([r["hit"] for r in rows]))
    per = []
    for r in rows:
        if mode == "move":
            per.append(r["win_is20h"].astype(float))
        else:
            mx = r["win_high"].max()
            per.append((r["win_high"] >= mx - EPS).astype(float))
    ratios = np.zeros(NREP)
    for k in range(NREP):
        acc = 0.0
        for v in per:
            acc += v[rng.integers(len(v))]
        ratios[k] = acc / len(per)
    p = float((ratios >= obs - 1e-12).mean())
    return obs, p, ratios, [float(v.mean()) for v in per]


def bucket(r):
    """동결 대역 그대로: 상한가형 `r ≥ −1%` · 되밀림형 `r ≤ −5%` · 그 외 중간대."""
    return "상한가형" if r >= -0.01 else ("되밀림형" if r <= -0.05 else "🔴 중간대")


def gstar(vals):
    """`G* = max_gap / (max r − min r)`. 범위 0(전 건 동일값)이면 **간극이 없다** ⇒ 0.0."""
    v = np.sort(np.asarray(vals, dtype=float))
    if len(v) < 2:
        return float("nan")
    rg = float(v[-1] - v[0])
    if rg <= 0:
        return 0.0
    return float(np.max(np.diff(v)) / rg)


def gstar_rows(M):
    """(rep, n) 행렬의 행별 `G*` — 벡터화."""
    M = np.sort(M, axis=1)
    rg = M[:, -1] - M[:, 0]
    gp = np.diff(M, axis=1).max(axis=1)
    return np.where(rg > 0, gp / np.where(rg > 0, rg, 1.0), 0.0)


def null_gstar_a(cands, rng):
    """읽기 A — 각 «건»을 그 건의 등록일 `n_up` 집합에서 뽑은 한 종목으로 «치환»(날짜 정합·크기 n)."""
    cols = [c[rng.integers(0, len(c), NREP)] for c in cands]
    return gstar_rows(np.stack(cols, axis=1))


def null_gstar_b(cands, n, rng):
    """읽기 B — 각 «등록일»의 `n_up` 집합에서 크기 `n` 을 뽑아(비복원) `G*`. 날짜별 분포를 합친다."""
    outs, repl = [], []
    for c in cands:
        m = len(c)
        if m >= n:
            idx = np.argsort(rng.random((NREP, m)), axis=1)[:, :n]
            M = c[idx]
        else:  # 집합이 n 보다 작으면 비복원 추출이 불가능하다 ⇒ 복원 추출로 대체하고 그 사실을 인쇄
            repl.append(m)
            M = c[rng.integers(0, m, (NREP, n))]
        outs.append(gstar_rows(M))
    return np.concatenate(outs), repl


def fmt_pct(x):
    return "—" if x != x else f"{x:+.2%}"


def verdict_and(ratio_ok, p_ok):
    if ratio_ok and p_ok:
        return "✅ 지지"
    if ratio_ok or p_ok:
        return "🟡 부분 충족 — **지지로 인용 금지**"
    return "⛔ 불성립"


def block(title, rows, tag):
    say(f"### {title}\n")
    say("| 종목 | 등록일 | 창봉수(**D 포함**) | 등록일 고가 | 창 최고 고가 | **일치** | "
        "`r=C/H−1` | `(C−L)/(H−L)` | 종가 등락 | 고가 등락 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if not r["ok"]:
            say(f"| {r['name']} | {r['reg']} | — | — | — | (봉 없음) | — | — | — | — |")
            continue
        say(f"| {r['name']} | {r['reg']} | {r['nwin']} | {r['high']:,.0f} | "
            f"{r['win_max_high']:,.0f} | {'✅' if r['hit'] else '❌'} | "
            f"{r['r']:+.2%} | {r['pos']:.3f} | {fmt_pct(r['ret_c'])} | {fmt_pct(r['ret_h'])} |")
    hits = sum(1 for r in rows if r["ok"] and r["hit"])
    n = sum(1 for r in rows if r["ok"])
    say(f"\n⇒ **{tag} 일치 {hits}/{n} = {hits/n*100:.1f}%**\n")
    return hits, n


def main():  # noqa: C901
    codes = sorted({c for _n, c, _d in POST6_NEW + POST5 + POST4})
    df = load_prices(codes)

    # ── 머리말 ──────────────────────────────────────────────────────────────
    say("# RESULTS_REGDAY_POST6_NUMBERS — 기계 생성 (수정 금지)\n")
    say("6번째 글 **등록일 축** — `Q1-R2` · `P6-M1′` · `P6-M2′` · `P6-M3′` · `REG-M4` · `REG-M5`")
    say("준거 `PREREG_POST6.md` §2-2·§3-1·§3-2·§3-3·§4 #7~#12·§5-2 · "
        "`PREREG_REGDAY_MEASURE.md` §4 · `PREREG_Q1_V2.md` §3 `R2` · "
        "`PREDECISION_2026-09-04_post6.md` PD-1·PD-2·PD-3·PD-9 · `INTAKE_2026-09-04_post6.md` §1·§5")
    say("생성 `run_regday_post6.py` (스크립트 stdout 그대로 · `run_regday_post5.py` 승계 · 원본 불변)\n")
    say(f"- DB `kis_template.daily_prices` 스냅샷 최신 **{df.date.max().date()}** "
        f"(설정 `DB_UPTO = {DB_UPTO}`)")
    say("- **창 종료 2026-09-04 = 발행 당일 봉 «포함»**(PD-1) — 이 레인이 쓰는 창은 `[D−19, D]` 뿐이다")
    say(f"- 창 = `[D−19, D]` = **D 를 «포함»한 직전 {WIN}거래일** · 봉수는 전부 **등록일 포함** 셈 "
        "(§1-6 7 · `RESULTS_LADDER_TRANCHE.md` N8)")
    say(f"- 귀무 반복 **{NREP:,}** · 시드 **{NULL_SEED}** ⇒ 두 번 실행하면 **byte 동일**")
    say("- 라벨은 **축 접두**로 부른다(§0-3): `Q1-`·`P6-`·`REG-`. 접두 없는 맨 라벨은 인용이 아니다.")
    say("- 🔴 **이 산출물은 라이브 채택 대상이 아니다**(`PREREG.md` §0-2).")
    say("- 🔴 **이 문서 안에서 새 예측을 만들지 않는다**(`RESULTS_REGDAY_POST5.md` §10 처리 승계).\n")
    say("> 🔴 **분모 = 6번째 글 «신규» 10건.** 후속 2건(광전자 · 삼양바이오팜)은 **PD-2 2번**대로 "
        "등록일 축 분모에서 제외한다(이중계상 금지 — 값을 보고 뺀 것이 아니라 «정의»로 빠진다).\n"
        "> 🟢 신규 10건 전부 등록일 `exact` · 본문 안 모순 0 ⇒ **대안 날짜 계산 없음**.\n"
        "> 🟢 코드 10/10 DB 존재 ⇒ post5 레메디형 결손 0.\n")

    # ── §0. 분모·플래그 ─────────────────────────────────────────────────────
    say("## 0. 분모 · 재진입 플래그 · 창 봉수\n")
    r6 = measure(df, POST6_NEW)
    say("| 종목 | 코드 | 등록일 | 창 시작(D−19) | 창 봉수(**D 포함**) | D **이전** 봉수 | "
        "재진입 | 직전 사이클 등록일 | **`P6-PRIOR_CYCLE_IN_WINDOW`** |")
    say("|---|---|---|---|---|---|---|---|---|")
    flags, flag_mismatch = {}, []
    for r in r6:
        if not r["ok"]:
            say(f"| {r['name']} | {r['code']} | {r['reg']} | — | — | — | — | — | (봉 없음) |")
            continue
        if r["code"] in REENTRY:
            pr = REENTRY[r["code"]]
            if pr is None:
                fl, prev_s = 0, "🔴 저자 미명시(`none`)"
            else:
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
    say(f"\n⇒ **`P6-PRIOR_CYCLE_IN_WINDOW` = 1 인 건 {n_flag}건** (§1-5 3 의무 인쇄) · "
        f"재진입 건 자체는 **{len(REENTRY)}건**(지투파워 · 현대약품)")
    say("🔑 §1-5 3: ***이건 「제외」가 아니다 — 「이 건은 규칙상 통과할 수 없다」는 사실을 "
        "판정과 같은 무게로 인쇄하는 장치다.***")
    if flag_mismatch:
        for nm, want, got in flag_mismatch:
            say(f"🔴 **PD-3 표와 불일치**: {nm} — 문서 {want} ↔ 계산 {got}")
    else:
        say("🟢 PD-3 표(지투파워 1 · 현대약품 0)와 **계산값이 일치**한다.")
    say("🔴 현대약품은 직전 사이클 등록일이 **저자 미명시**라 플래그가 «구성상» 0 이다 — "
        "「창 안에 없었다」가 아니라 **「잴 수 없다」**. 병기 의무(PD-3).\n")

    # ── §1. Q1-R2 / P6-M1′ 관측 ────────────────────────────────────────────
    say("## 1. `Q1-R2` · `P6-M1′` 관측 — 등록일 **고가** == `[D−19, D]` 최고 고가\n")
    r5 = measure(df, POST5)
    r4 = measure(df, POST4)
    h6, n6 = block("1-1. 6번째 글 신규 10건 (**판정 표본**)", r6, "6번째 글 신규")
    h5, n5 = block("1-2. 5번째 글 6건 — 09-04 스냅샷 재계산 (참고 · 판정 대체 아님)", r5, "5번째 글(재계산)")
    h4, n4 = block("1-3. 4번째 글 6건 — 09-04 스냅샷 재계산 (참고 · 판정 대체 아님)", r4, "4번째 글(재계산)")
    say(f"⇒ **누적 {n6 + n5 + n4}건 = {h6 + h5 + h4}/{n6 + n5 + n4} = "
        f"{(h6 + h5 + h4)/(n6 + n5 + n4)*100:.1f}%**")
    say(f"⇒ 동결 누적(`PREREG_POST6.md` §2-2) **{FROZEN_CUM[0]}/{FROZEN_CUM[1]}** + 이번 {h6}/{n6} = "
        f"**{FROZEN_CUM[0] + h6}/{FROZEN_CUM[1] + n6} = "
        f"{(FROZEN_CUM[0] + h6)/(FROZEN_CUM[1] + n6)*100:.1f}%**")
    same = (h5 + h4 == FROZEN_CUM[0]) and (n5 + n4 == FROZEN_CUM[1])
    say(f"⇒ 재계산 과거 12건 = {h5 + h4}/{n5 + n4} · 동결값 {FROZEN_CUM[0]}/{FROZEN_CUM[1]} ⇒ "
        f"{'🟢 **일치** — 스냅샷 이동(08-28 → 09-04)이 과거 등록일 측정치를 바꾸지 않았다' if same else '🔴 **불일치 — 스냅샷 이동이 과거 값을 바꿨다(조사 대상)**'}\n")

    miss = [r for r in r6 if r["ok"] and not r["hit"]]
    say("### 1-4. ❌ 건 — 창 최고 고가를 «어느 날»이 잡았나 (기술 · 판정 아님)\n")
    if not miss:
        say("불일치 건 **0**.\n")
    else:
        say("| 종목 | 등록일 | 등록일 고가 | 창 최고 고가 | 그 고가를 낸 날 | "
            "직전 사이클 등록일과 같은 날? |")
        say("|---|---|---|---|---|---|")
        for r in miss:
            pr = REENTRY.get(r["code"])
            same_s = ("—(재진입 아님)" if r["code"] not in REENTRY else
                      ("🔴 저자 미명시" if pr is None else
                       ("✅ 같다" if pr in r["argmax_dates"] else
                        f"❌ **아니다** — 직전 사이클 등록일 {pr}")))
            say(f"| {r['name']} | {r['reg']} | {r['high']:,.0f} | {r['win_max_high']:,.0f} | "
                f"{' · '.join(r['argmax_dates'])} | {same_s} |")
        say("\n🔴 post5 코데즈컴바인의 기전(*「재진입 건은 구조적으로 «자기 첫 사이클의 고가»에 막힌다」* "
            "`RESULTS_REGDAY_POST5.md` §7-1)이 이번에도 «같은 모양»인지는 이 표로만 말한다 — "
            "**플래그 `P6-PRIOR_CYCLE_IN_WINDOW = 1` 은 「직전 사이클 등록일이 창 안에 있다」는 사실일 뿐, "
            "「그 날의 고가가 막았다」는 뜻이 아니다.**\n")

    say("### 1-5. `Q1-R2` 판정\n")
    obs6 = h6 / n6
    say("| 예측 | 출처 파일·절 | 문언·문턱 | 최소 n | 관측 | 판정 | ⛔ 판정 불가 조건 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| **`Q1-R2`** | `PREREG_Q1_V2.md` §3 | 등록일 `exact` 건의 **≥ 50%** | {MIN_N} | "
        f"**{h6}/{n6} = {obs6*100:.1f}%** | {'✅ 지지' if obs6 >= R2_RATIO else '⛔ 불성립'} | "
        f"등록일 미명시 제외 후 < {MIN_N} ⇒ 이번 분모 {n6} ⇒ **미발동** |")
    say(f"\n- 🔴 대칭/반증 쌍 = **`REG-M4`**(§5) — `Q1-R2` 가 지지돼도 `n_up` 이 크면 "
        "「어느 급등주냐」는 못 말한다.\n")

    # ── §2. P6-M1′ ──────────────────────────────────────────────────────────
    say("## 2. `P6-M1′` — 비율 ∧ 귀무 (AND · `PREREG_POST6.md` §3-1)\n")
    ok6 = [r for r in r6 if r["ok"]]
    res = {}
    for mode, label in (("move", "**이동창**(§2 문언 「창이 뽑은 날에 함께 이동」) — **주 판정**"),
                        ("fixed", "고정창(뽑은 날과 무관하게 `[D−19,D]` 최고) — **의무 민감도**")):
        rng = np.random.default_rng(NULL_SEED)
        obs, p, ratios, per = null_p(ok6, rng, mode)
        res[mode] = (obs, p)
        say(f"### 2-{'1' if mode == 'move' else '2'}. {label}\n")
        say("| 종목 | 창봉수(**D 포함**) | 그 창에서 「그날이 창 최고」인 날 비율 |")
        say("|---|---|---|")
        for r, v in zip(ok6, per):
            say(f"| {r['name']} | {r['nwin']} | {v*100:.1f}% |")
        say()
        say(f"- 관측 비율 **{obs*100:.1f}%** · 귀무 평균 **{ratios.mean()*100:.1f}%** · "
            f"귀무 중앙 **{np.median(ratios)*100:.1f}%** · 귀무 최대 **{ratios.max()*100:.1f}%**")
        say(f"- **p = P(귀무 비율 ≥ 관측) = {p:.5f}** ({int(round(p*NREP)):,}/{NREP:,})")
        say(f"- 귀무 백분위 < {ALPHA:.0%} ⇒ **{'충족' if p < ALPHA else '미달'}**\n")

    p_move, p_fixed = res["move"][1], res["fixed"][1]
    split_null = (p_move < ALPHA) != (p_fixed < ALPHA)
    say("### 2-3. 재진입 제외 민감도 (§1-5 2 · 의무)\n")
    sub_all = [r for r in ok6 if r["code"] not in REENTRY]
    sub_flag = [r for r in ok6 if flags.get(r["code"], 0) == 0]
    sens = {}
    say("| 표본 | n | 일치 | 비율 | 이동창 p | 고정창 p | 비율 ≥ 83.33% | `P6-M1′` |")
    say("|---|---|---|---|---|---|---|---|")
    for tag, sub in (("전 건(주 판정)", ok6),
                     ("재진입 2건 제외", sub_all),
                     ("플래그=1 건만 제외(참고)", sub_flag)):
        hh = sum(1 for r in sub if r["hit"])
        rt = hh / len(sub)
        pm = null_p(sub, np.random.default_rng(NULL_SEED), "move")[1]
        pf = null_p(sub, np.random.default_rng(NULL_SEED), "fixed")[1]
        sens[tag] = (rt, pm, pf)
        say(f"| {tag} | {len(sub)} | {hh} | **{rt*100:.1f}%** | {pm:.5f} | {pf:.5f} | "
            f"{'✅' if rt >= M1_RATIO else '❌'} | {verdict_and(rt >= M1_RATIO, pm < ALPHA)} |")
    v_main = verdict_and(sens["전 건(주 판정)"][0] >= M1_RATIO, p_move < ALPHA)
    v_reent = verdict_and(sens["재진입 2건 제외"][0] >= M1_RATIO, sens["재진입 2건 제외"][1] < ALPHA)
    split_reentry = v_main != v_reent
    say(f"\n⇒ 재진입 제외로 판정이 **{'🔴 갈린다 ⇒ 「재진입 의존」 — 어느 쪽도 지지로 선언하지 않는다' if split_reentry else '🟢 갈리지 않는다'}**\n")

    say("### 2-4. `P6-절단가드-A`/`B` (§1-6 3·4 · 산술 인쇄)\n")
    trunc = [r for r in ok6 if r["nwin"] < WIN]
    say(f"- 절단 건(창 봉수 **< {WIN}봉**, 등록일 포함 셈) = **{len(trunc)}건** / 분모 {len(ok6)}건 "
        f"= **{len(trunc)/len(ok6)*100:.1f}%**")
    say(f"- `P6-절단가드-A`: {len(trunc)}/{len(ok6)} = {len(trunc)/len(ok6)*100:.1f}% "
        f"{'≥' if len(trunc)/len(ok6) >= TRUNC_GUARD else '<'} 1/3 = 33.33% ⇒ "
        f"**{'⛔ 판정 불가' if len(trunc)/len(ok6) >= TRUNC_GUARD else '미발동'}**")
    if trunc:
        sub_t = [r for r in ok6 if r["nwin"] == WIN]
        ht = sum(1 for r in sub_t if r["hit"])
        rt = ht / len(sub_t)
        pt = null_p(sub_t, np.random.default_rng(NULL_SEED), "move")[1]
        v_tr = verdict_and(rt >= M1_RATIO, pt < ALPHA)
        say(f"- `P6-절단가드-B`: 절단 제외 {ht}/{len(sub_t)} = {rt*100:.1f}% · p={pt:.5f} ⇒ {v_tr} · "
            f"주 판정 {v_main} ⇒ **{'⛔ 판정 불가(뒤집힘)' if v_tr != v_main else '미발동'}**")
        split_trunc = v_tr != v_main
    else:
        say(f"- `P6-절단가드-B`: 절단 건이 **0** 이므로 제외 표본 = 전 표본 "
            f"({len(ok6)}건 · {sum(1 for r in ok6 if r['hit'])}/{len(ok6)} = "
            f"{sum(1 for r in ok6 if r['hit'])/len(ok6)*100:.1f}%) ⇒ **뒤집힐 여지가 없다 · 미발동**")
        split_trunc = False
    say("- 🔴 문턱 `1/3` 은 `REC-Y3`(`RESULTS_RECONSTRUCT_POST4.md`)에서 **차용**한 값이며 "
        "**절단 비율에 대해 검증된 값이 아니다**(§1-6 6 고지 승계).")
    say("- 🟢 PD-9 예고(신규 10건 전부 20/20)와 **계산이 일치**한다." if not trunc
        else "- 🔴 PD-9 예고(전 건 20/20)와 다르다 — 절단 건이 나왔다.")
    say("")

    say("### 2-5. `P6-M1′` 종합 판정\n")
    say("| 항목 | 문언·문턱 (출처 파일·절) | 최소 n | 관측 | 판정 |")
    say("|---|---|---|---|---|")
    say(f"| 비율 | **≥ 5/6 = {M1_RATIO*100:.2f}%** · `PREREG_POST6.md` §3-1 | {MIN_N} | "
        f"**{obs6*100:.1f}%** | {'✅ 충족' if obs6 >= M1_RATIO else '❌ 미달'} |")
    say(f"| 귀무(이동창 · 주) | 백분위 **< 5%** · `PREREG_REGDAY_MEASURE.md` §4-1 | — | "
        f"**p={p_move:.5f}** | {'✅ 충족' if p_move < ALPHA else '❌ 미달'} |")
    say(f"| 귀무(고정창 · 민감도) | 두 갈래가 갈리면 ⛔ · `PREREG_POST6.md` §3-1 | — | "
        f"**p={p_fixed:.5f}** | {'🔴 갈림' if split_null else '🟢 같음'} |")
    blocked = []
    if len(ok6) < MIN_N:
        blocked.append("① 신규 건 < 3")
    if trunc and len(trunc) / len(ok6) >= TRUNC_GUARD:
        blocked.append("② `P6-절단가드-A`")
    if split_trunc:
        blocked.append("③ `P6-절단가드-B`")
    if split_null:
        blocked.append("④ 두 귀무 갈래가 갈림")
    if blocked:
        say(f"\n⇒ ⛔ **판정 불가** — 발동한 조건: {' · '.join(blocked)}")
    else:
        say(f"\n⇒ 결정규칙 «비율 ≥ 0.8333 **∧** 귀무 백분위 < 5%» ⇒ **{v_main}**")
        say("⇒ ⛔ 판정 불가 조건 ①~④ **전부 미발동**"
            f"(① {len(ok6)} ≥ {MIN_N} · ② 절단 {len(trunc)}건 · ③ 뒤집힘 없음 · ④ 두 갈래 동일)")
    if split_reentry:
        say("⇒ 🔴 **재진입 의존** — §1-5 2 대로 어느 쪽도 지지로 선언하지 않는다.")
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
    for r in ok6:
        b = bucket(r["r"])
        d5 = (r["r"] - (-0.05)) * 100
        d1 = (r["r"] - (-0.01)) * 100
        lim = (r["ret_c"] >= LIMIT_UP) if r["ret_c"] == r["ret_c"] else False
        say(f"| {r['name']} | {r['reg']} | **{r['r']:+.2%}** | {b} | {d5:+.2f} | {d1:+.2f} | "
            f"{fmt_pct(r['ret_c'])} | {'🔴 **예**' if lim else '아니오'} |")
    b6 = [bucket(r["r"]) for r in ok6]
    n_ceil, n_pull, n_mid = b6.count("상한가형"), b6.count("되밀림형"), b6.count("🔴 중간대")
    say(f"\n⇒ 상한가형 **{n_ceil}** · 되밀림형 **{n_pull}** · 중간대 **{n_mid}** (분모 {len(ok6)})")
    say("🔑 경계 근접성은 **판정과 같은 무게로** 적는다(§3-2) — post5 광전자는 **0.74%p** 짜리였다"
        "(*「60원짜리 결론이다」*). 위 표의 두 열이 그 자리다.")
    tight = min(ok6, key=lambda r: min(abs(r["r"] + 0.05), abs(r["r"] + 0.01)))
    say(f"⇒ 가장 아슬아슬한 건 = **{tight['name']}** — 두 경계 중 가까운 쪽까지 "
        f"**{min(abs(tight['r'] + 0.05), abs(tight['r'] + 0.01))*100:.2f}%p**\n")

    say("### 3-2. 전제 판정 — **양 무리 각 ≥ 2건** (없으면 검정 자체를 안 돌린다)\n")
    prem = (n_ceil >= CLUSTER_MIN) and (n_pull >= CLUSTER_MIN)
    say(f"- 전제(`PREREG_POST6.md` §3-2 · **이 문서에서 처음 선언한 문턱**): 상한가형 ≥ {CLUSTER_MIN} "
        f"**그리고** 되밀림형 ≥ {CLUSTER_MIN}")
    say(f"- 관측: 상한가형 **{n_ceil}** · 되밀림형 **{n_pull}** ⇒ "
        f"**{'🟢 충족 — 검정을 돌린다' if prem else '⛔ 미충족 — 검정을 돌리지 않는다'}**")
    say(f"- 최소 n(신규 건) {MIN_N} ⇒ 분모 {len(ok6)} ⇒ 충족")
    say("- 🔑 §3-2: ***한 무리가 1건 이하면 「무리」가 아니라 「점」이다.*** "
        "문턱 2 의 근거는 이 정의뿐이며 **관측값과 무관**하다.\n")

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    uni_cache = {}
    for r in ok6:
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
        rs6 = [r["r"] for r in ok6]
        g_obs = gstar(rs6)
        cands_a = [nup_r_array(r["reg"]) for r in ok6]
        empty = [r["name"] for r, c in zip(ok6, cands_a) if len(c) == 0]
        say(f"- 관측 `G*` = **{g_obs:.4f}** (n={len(rs6)})")
        say("- 귀무(§3-2 문언): *「각 건의 등록일에 대해 **그날 `n_up` 집합**에서 «같은 크기 `n`»을 "
            "무작위 추출해 같은 `G*` 를 계산」* · 시드 "
            f"**{NULL_SEED}** · **{NREP:,}** 반복")
        if empty:
            say(f"- 🔴 `n_up` 집합이 빈 등록일 건: {', '.join(empty)} ⇒ 귀무 계산 불가")
        say("- 🔴 **문언이 두 갈래로 읽힌다 ⇒ 양쪽 다 인쇄한다**(값 보고 고르지 않는다):")
        say("  - **읽기 A** = 각 «건»을 그 건의 등록일 `n_up` 집합에서 뽑은 한 종목으로 치환"
            "(날짜 구성 보존 · 크기 n)")
        say("  - **읽기 B** = 각 «등록일»의 `n_up` 집합에서 크기 n 을 비복원 추출"
            "(날짜별 분포를 합침)")
        rngA = np.random.default_rng(NULL_SEED)
        nullA = null_gstar_a(cands_a, rngA)
        pA = float((nullA >= g_obs - 1e-12).mean())
        rngB = np.random.default_rng(NULL_SEED)
        nullB, replB = null_gstar_b(cands_a, len(rs6), rngB)
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
    lim_rows = [r for r in ok6 if r["ret_c"] == r["ret_c"] and r["ret_c"] >= LIMIT_UP]
    say(f"- 조작정의: **종가 등락 ≥ +{LIMIT_UP:.0%}**(제도 상한 +30%). "
        f"상한가형(`r ≥ −1%`) **{n_ceil}건** 중 상한가 마감 **{len(lim_rows)}건**"
        f"{' — ' + ', '.join(r['name'] for r in lim_rows) if lim_rows else ''}")
    if prem:
        rest = [r["r"] for r in ok6 if not (r["ret_c"] == r["ret_c"] and r["ret_c"] >= LIMIT_UP)]
        if len(rest) >= 2 and lim_rows:
            g_rest = gstar(rest)
            say(f"- 상한가 마감 건을 뺀 `G*` = **{g_rest:.4f}** (n={len(rest)}) "
                f"↔ 전 건 `G*` = {g_obs:.4f}")
            cands_rest = [nup_r_array(r["reg"]) for r in ok6
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
        "제도가 만든다. 인과로 읽지 말 것.***」* — 원 사전등록 조항은 "
        "`PREREG_REGDAY_MEASURE.md` §5(*「상한가형 3건은 `C = H` 가 «제도상 자동»」*)이며 "
        "**둘은 다른 문서다**(§3-2 요구대로 구분해 적는다).\n")

    say("### 3-5. 옛 `REG-M2` 규칙 병기 — 죽은 가드가 «죽어 있음»을 매회 증명한다\n")
    old_ok = (n_pull >= 1) and (n_mid == 0)
    say(f"- 옛 규칙(`PREREG_REGDAY_MEASURE.md` §4-2): «되밀림형 ≥ 1 **그리고** 중간대 = 0»")
    say(f"- 관측: 되밀림형 {n_pull} · 중간대 {n_mid} ⇒ **{'✅ 자동 통과' if old_ok else '⛔ 불성립'}**")
    say(f"- 🔑 `RESULTS_REGDAY_POST5.md` §3-1: *「***M2 의 결정규칙은 「이분성」을 검정하지 못한다. "
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

    # ── §4. P6-M3′ ──────────────────────────────────────────────────────────
    say("## 4. `P6-M3′` (반증축) — 되밀림형 종가 위치 `(C−L)/(H−L)` (`PREREG_POST6.md` §3-3)\n")
    pull6 = [r for r in ok6 if bucket(r["r"]) == "되밀림형"]
    say("| 종목 | 등록일 | 고가 | 저가 | 종가 | **`(C−L)/(H−L)`** | 개별 (< 0.5) |")
    say("|---|---|---|---|---|---|---|")
    for r in pull6:
        say(f"| {r['name']} | {r['reg']} | {r['high']:,.0f} | {r['low']:,.0f} | {r['close']:,.0f} | "
            f"**{r['pos']:.3f}** | {'✅' if r['pos'] < 0.5 else '🔴 실패'} |")
    pos6 = sorted(r["pos"] for r in pull6)
    if len(pull6) < MIN_PULL:
        say(f"\n⇒ 되밀림형 **{len(pull6)}건 < 최소 n {MIN_PULL}** ⇒ ⛔ **판정 불가**"
            "(`PREREG_POST6.md` §4 #10 ⛔ 조건 「되밀림형 < 3」)")
        med6 = float("nan")
        m3_ok = None
        fail_major = None
    else:
        med6 = float(np.median(pos6))
        m3_ok = med6 < 0.5
        n_fail = sum(1 for p in pos6 if p >= 0.5)
        fail_major = n_fail * 2 > len(pos6)
        say(f"\n⇒ 되밀림형 **{len(pull6)}건** · 중앙값 **{med6:.3f}** · "
            f"범위 [{min(pos6):.3f}, {max(pos6):.3f}]")
        if m3_ok:
            say("⇒ 결정규칙 «중앙값 < 0.5»(문턱 불변) ⇒ **✅ 통과**")
        elif prem:
            say("⇒ 결정규칙 «중앙값 < 0.5»(문턱 불변) ⇒ **🔴 실패 ⇒ `P6-M2′` 지지 취소**")
        else:
            say("⇒ 결정규칙 «중앙값 < 0.5»(문턱 불변) ⇒ **🔴 실패** — 다만 `P6-M2′` 는 이미 "
                "«판정 불가»(전제 미충족)라 **취소할 지지가 없다**. 반증축이 «단독으로» 실패한 셈이다.")
        say(f"⇒ 개별 실패(`≥ 0.5`) **{n_fail}/{len(pos6)}** ⇒ 과반 여부 "
            f"**{'🔴 과반 — 「되밀림」이라는 «이름»으로 인용 금지' if fail_major else '과반 아님(인용 제한 미발동)'}**")
        say(f"- 🔴 「과반」은 `PREREG_POST6.md` §3-3 에서 **처음 선언한 문턱**이다"
            "(이름의 정의에서 나온 값 · 관측값과 무관). post5 는 3/6 = 정확히 절반이라 "
            "**과반이 아니었다**(미발동).")
        say("- 🔑 인용 제한은 **지지 취소가 아니다**(§3-3 문언 그대로).")
    p5pull = sorted(r["pos"] for r in r5 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p4pull = sorted(r["pos"] for r in r4 if r["ok"] and bucket(r["r"]) == "되밀림형")
    allpos = sorted(pos6 + p5pull + p4pull)
    if allpos:
        say(f"\n(참고 · 판정 아님) 되밀림형 종가 위치 누적 **{len(allpos)}건** 중앙 "
            f"**{np.median(allpos):.3f}** — post6 {len(pos6)}건 · post5 재계산 {len(p5pull)}건 · "
            f"post4 재계산 {len(p4pull)}건")
    say("")

    # ── §5. REG-M4 ──────────────────────────────────────────────────────────
    say("## 5. `REG-M4` (대칭 단언) — `n_up` (`PREREG_REGDAY_MEASURE.md` §4-4 · 매회 재판정)\n")
    say("### 5-0. `PREREG_POST6.md` §5-2 — 유니버스 `prev_close` 결손 공개 (5열 · 등록일마다)\n")
    say("| 등록일 | `universe_mcap` | `universe_test` | `dropped` | `drop_rate` | `prev_bar_date` |")
    say("|---|---|---|---|---|---|")
    drop_flag_days = []
    for d in sorted(uni_cache):
        raw, rowsu, pbd = uni_cache[d]
        drop = raw - len(rowsu)
        rate = drop / raw if raw else float("nan")
        if rate >= DROP_GUARD:
            drop_flag_days.append((d, rate))
        # 🔴 표시는 **가드(`drop_rate ≥ 1%`)에만** 붙인다 — 0 아닌 탈락 자체는 붉게 칠하지 않는다
        # (§5-2 가드가 재는 것은 «건수»가 아니라 «비율»이다).
        say(f"| {d} | {raw:,} | {len(rowsu):,} | {drop:,} | "
            f"{'🔴 **' + f'{rate*100:.2f}%' + '**' if rate >= DROP_GUARD else f'{rate*100:.2f}%'} | "
            f"{pbd} |")
    say(f"\n- 가드(§5-2 · **이 문서에서 처음 선언한 숫자 1%**): `drop_rate ≥ {DROP_GUARD:.0%}` 인 날은 "
        "🔴 표시하고 **그날의 `n_up` 을 다른 날과 직접 비교하지 말 것**.")
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

    say("### 5-1. 건별 `n_up` 과 저자 종목의 자리\n")
    say("| 종목 | 등록일 | 검정 유니버스 | **`n_up`** | 본인이 `n_up` 안에? | "
        "`n_up` 안 `거래대금/시총` 순위 | 백분위 |")
    say("|---|---|---|---|---|---|---|")
    nups, pcts, inset_n = [], [], 0
    for r in ok6:
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
            pct = (nup - rk) / (nup - 1) * 100 if nup > 1 else 100.0
            pcts.append(pct)
            rk_s, pct_s, in_s = f"**{rk} / {nup}**", f"{pct:.1f}", "✅"
        else:
            rk_s, pct_s, in_s = "—", "—", "🔴 **아니다**"
        say(f"| {r['name']} | {r['reg']} | {len(rowsu):,} | **{nup}** | {in_s} | {rk_s} | {pct_s} |")
    conn.close()
    med_nup = float(np.median(nups))
    say(f"\n⇒ **`n_up` 중앙값 {med_nup:.1f}** · 범위 **[{min(nups)}, {max(nups)}]** · "
        f"표준편차 {np.std(nups, ddof=0):.1f}**(모표준편차 · `ddof=0`)**")
    say(f"⇒ 본인이 `n_up` 집합 «안»인 건 **{inset_n}/{len(ok6)}** — "
        f"밖인 건 **{len(ok6) - inset_n}건**"
        + (f" · 안에 있는 건의 `거래대금/시총` 백분위 중앙 **{np.median(pcts):.1f}**" if pcts else ""))
    say("")
    say("### 5-2. 「`P6-M1′` 을 선정 규칙으로 인용 금지」 — **매회 재판정**\n")
    ban = med_nup >= NUP_CITE_BAN
    say(f"- 문턱: `n_up` 중앙 **≥ {NUP_CITE_BAN}** ⇒ 인용 금지 "
        f"(`PREREG_POST6.md` §4 #3 ← `PREREG_D1_OOS.md` §4 `N2`). "
        f"`PREREG_REGDAY_MEASURE.md` §4-4 의 자기 문언은 정성적이다(*「매일 수십 종목」*) — **둘 다 적는다**.")
    say(f"- 관측 중앙 **{med_nup:.1f}** ⇒ **{'🔴 발동 — `M1`/`P6-M1′` 을 「선정 규칙」으로 인용 금지' if ban else '🟢 미발동 — 이번 글에서는 인용 금지가 걸리지 않는다'}**"
        f" (정성 읽기 「매일 수십 종목」으로도 {'같은 결론' if (med_nup >= 10) == ban else '🔴 다른 결론 ⇒ 판정 불가·모호'})")
    say("- 🔑 §2-2: ***`REG-M4` 는 상수가 아니다*** — `n_up` 이 작아지는 날이 오면 다시 볼 수 있으므로 "
        "**매회 다시 낸다**.")
    say("- 🔴 대칭: `REG-M4` 는 **자신이 반증축**이다(§4 #11). 그래서 여기엔 「지지」가 없고 "
        "«인용 금지 발동/미발동»만 있다.\n")

    # ── §6. REG-M5 ──────────────────────────────────────────────────────────
    say("## 6. `REG-M5` (기록만 · 라이브 대조) — 되밀림형 `r` 분포\n")
    r6v = sorted(r["r"] for r in pull6)
    say("| 표본 | n | 중앙 | 최소 | 최대 |")
    say("|---|---|---|---|---|")
    if r6v:
        say(f"| 6번째 글 되밀림형 | {len(r6v)} | {np.median(r6v):+.2%} | {min(r6v):+.2%} | "
            f"{max(r6v):+.2%} |")
    else:
        say("| 6번째 글 되밀림형 | 0 | — | — | — |")
    p5v = sorted(r["r"] for r in r5 if r["ok"] and bucket(r["r"]) == "되밀림형")
    p4v = sorted(r["r"] for r in r4 if r["ok"] and bucket(r["r"]) == "되밀림형")
    if p5v:
        say(f"| 5번째 글 되밀림형(재계산) | {len(p5v)} | {np.median(p5v):+.2%} | {min(p5v):+.2%} | "
            f"{max(p5v):+.2%} |")
    if p4v:
        say(f"| 4번째 글 되밀림형(재계산) | {len(p4v)} | {np.median(p4v):+.2%} | {min(p4v):+.2%} | "
            f"{max(p4v):+.2%} |")
    allv = sorted(r6v + p5v + p4v)
    if allv:
        say(f"| 누적 | {len(allv)} | {np.median(allv):+.2%} | {min(allv):+.2%} | {max(allv):+.2%} |")
    say(f"\n라이브 `entry_band_up_pct` = **+{BAND_UP:.0%}** (그 위로 갭업하면 매수 포기).")
    if r6v:
        say(f"저자 되밀림형 등록일 종가는 그날 고가 대비 **{np.median(r6v):+.2%}**(중앙) 자리다.")
    say("🔴 **예측 아님 · 판정에 쓰지 않는다.** 저자 프로그램의 «매수 체결가»는 아직 복원 안 됐다"
        "(`PREREG_BUYLADDER.md` `L1`·`L2` 판정 불가).")
    say("🔑 전 건 `r` 분포(참고 · 되밀림형 한정 아님): "
        f"중앙 {np.median([r['r'] for r in ok6]):+.2%} · "
        f"[{min(r['r'] for r in ok6):+.2%}, {max(r['r'] for r in ok6):+.2%}]\n")

    # ── §7. 부수 ────────────────────────────────────────────────────────────
    say("## 7. 부수 — 창 절단 · 봉수 표기 규약\n")
    say("🔑 **아래 「창 봉수」는 «등록일 D 를 포함한» 셈이다** — 20봉 = 등록일 + 그 앞 19봉 "
        "(§1-6 7 · `RESULTS_LADDER_TRANCHE.md` N8).\n")
    say("| 종목 | 창 요구 | 창 실제 봉수(**D 포함**) | D **이전** 봉수 | 영향 |")
    say("|---|---|---|---|---|")
    for r in ok6:
        note = "🔴 **창이 절단됐다** — `[D−19,D]` 가 아니라 상장/수집 이후 전 구간" \
            if r["nwin"] < WIN else "정상"
        say(f"| {r['name']} | {WIN}봉(D 포함) | {r['nwin']} | {r['nwin'] - 1} | {note} |")
    say(f"\n⇒ 절단 **{len(trunc)}건** — PD-9 의 「신규 10건 전부 20/20」과 "
        f"{'🟢 일치' if not trunc else '🔴 불일치'}.")
    say("⚠️ 우리기술투자(041190)는 **04-01~08-04 구간에 결손**이 있으나(191종목 계열) "
        "`[D−19, D]` = `[2026-07-28, 2026-08-25]` 창은 봉이 다 있다 — 60봉 특징(`f9`)은 다른 레인(`SEL-`) 소관이다.")
    say("⚠️ 이 레인이 쓰는 창은 `[D−19, D]` 뿐이다 — **PD-11 의 창5 `[D, D+4]` 절단**(현대약품·비에이치)은 "
        "`LAD-` 레인 소관이며 **이 산출물의 값에 영향이 없다**.\n")

    (BASE / "RESULTS_REGDAY_POST6_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
