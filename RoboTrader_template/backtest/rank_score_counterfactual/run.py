# -*- coding: utf-8 -*-
"""랭킹 함수 반사실 — 사전등록 `PREREG.md`(동결) 실행부. **1단계 게이트 전용.**

🔴 이 파일은 지금 «1단계»(PREREG §6)만 구현한다. 유일한 실행 모드는 `--stage1` 이고
**PnL·수익률을 계산하지 않는다** — `BookBacktester` 를 import 하지도 부르지도 않으므로
거래당 수익률이 메모리에 들어올 경로 자체가 없다. 2단계(§4·§5)는 별도 지시로 구현한다.
***그래서 §6-5 의 「거래 수」는 «진입 트리거 수»(= arm 이 그날 고른 종목-일 수)로 센다.***
실현 거래 수는 청산 판정을 필요로 하고, 청산 판정은 수익률 계산이다 → 2단계 몫.

Arm 4개는 «랭킹 함수 하나»만 다르다 (PREREG §2):

    V = mean(volume,        최근 w)      (현행)
    T = mean(close*volume,  최근 w)      🔑 갈림점
    R = 적격 풀에서 무작위 10종목, 시드 0..19
    P = close 마지막값 내림차순          🔴 반증축

룰 평가는 (code, date) 캐시를 **1회** 만들어 전 arm 이 공유하고, **같은 창에서**
V·T·P 세 점수를 함께 계산한다 — arm 간 차이를 랭킹 함수로만 고립시키는 장치다
(`universe_lookahead_ladder` §2 승계).

🔑 척도 (PREREG 척도 고지 = `ac69084` 이후):
`daily_prices.close` 는 이미 분할조정 연속시세이고 `volume` 은 **원본 저장**이라,
라이브 읽기계층(`db/quant_daily_reader.py::_SELECT_OHLCV`)이 `volume * adj_factor` 로
단위를 맞춘다. 이 스크립트는 성능 때문에 raw SQL 로 읽으므로 **그 보정을 로더에서
«한 번만» 재현**한다(`vol_adj`). 그 뒤로는 `close × vol_adj` 를 그대로 쓰고
`adj_factor` 를 **다시 곱하지 않는다**(PREREG §8-6 이중조정 금지).

라이브 코드는 «읽기»만 한다(스크리너 어댑터 import). DB 는 SELECT 만.
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import yaml

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

from strategies.book_pullback_ma5.screener import BookPullbackMa5ScreenerAdapter        # noqa: E402
from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter      # noqa: E402
from strategies.minervini_volume_dryup.screener import (                                # noqa: E402
    MinerviniVolumeDryupScreenerAdapter,
)

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234",
           dbname="kis_template")

# 🔑 종목코드 술어 — 신형 코드는 «중간»이 영문일 수 있다(`0001A0`).
#    `^[0-9]{6}$` 로 하면 54종목을 놓친다. 의사티커(KOSPI/KOSDAQ/KS11/KQ11)는
#    첫 글자가 숫자가 아니라 이 술어에 이미 안 걸리지만, 명시적으로도 배제한다.
STOCK_ONLY = ("stock_code ~ '^[0-9][0-9A-Z]{5}$' "
              "AND stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')")

W0, W1 = "2021-01-01", "2026-05-31"   # PREREG §3 — W-long 하나만. 라이브 페이퍼 구간 제외.
MAX_CANDIDATES = 10                    # PREREG §2 고정
N_SEEDS = 20                           # PREREG §2 — R 시드 0..19
N_DECILES = 10                         # PREREG §6-4

# 전략 정의. `w`(점수 창)·`lookback`(match 에 넘기는 창)·`warmup`(룰 최소봉)은
# 전부 라이브 코드에서 온 값이다 — 아래 `verify_strategy_params()` 가 대조·인쇄한다.
STRATS = {
    "book_pullback_ma5": dict(
        screener=BookPullbackMa5ScreenerAdapter, w=5,
        lookback=60,    # BookPullbackMa5ScreenerAdapter.lookback_days
        warmup=25,      # config.yaml parameters.min_daily_bars (룰 최소 22봉 + 여유)
        exp_sl=0.03, exp_tp=0.15, exp_mh=30, role="판정 대상",
    ),
    "book_pullback_ma20": dict(
        screener=BookPullbackMa20ScreenerAdapter, w=20,
        lookback=90, warmup=35,
        exp_sl=0.08, exp_tp=0.10, exp_mh=50, role="판정 대상",
    ),
    "minervini_volume_dryup": dict(
        screener=MinerviniVolumeDryupScreenerAdapter, w=30,   # = base_window
        lookback=90, warmup=40,
        exp_sl=0.08, exp_tp=0.12, exp_mh=20, role="차등 예측 대조군",
    ),
}

# DB 지문 — 이 스크립트가 «실제로 읽는» 슬라이스만 (`regen_gate.py` 형식 승계).
FINGERPRINT_SQL = {
    f"daily_prices[{W0}..{W1}] (stock-only)":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}'",
    f"daily_prices[{W0}..{W1}] market_cap>0":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}' AND market_cap > 0",
    f"daily_prices[{W0}..{W1}] adj_factor<>1":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}' "
        f"AND COALESCE(adj_factor,1) <> 1",
    "daily_prices (전체)":
        "SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices",
    "daily_prices[전체] 의사티커":
        "SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        "WHERE stock_code IN ('KOSPI','KOSDAQ','KS11','KQ11')",
}

OUT: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


# ────────────────────────────────────────────────────────────────────────────
# 0. 설정 대조 — 청산 파라미터는 config.yaml 이 정본
# ────────────────────────────────────────────────────────────────────────────
def verify_strategy_params() -> list[str]:
    """각 전략 `config.yaml` 의 sl/tp/max_hold 를 읽어 지시서 기대값과 대조한 표(행)를 만든다.

    🔴 config 가 정본이다 — 어긋나면 그 사실을 표에 인쇄한다.
    (1단계는 청산을 «쓰지 않지만», 2단계가 쓸 값이 무엇인지 여기서 못박아 인쇄한다.)
    """
    rows = []
    for name, cfg in STRATS.items():
        y = yaml.safe_load((ROOT / "strategies" / name / "config.yaml").read_text(encoding="utf-8"))
        rm = (y or {}).get("risk_management", {}) or {}
        sl, tp, mh = rm.get("stop_loss_pct"), rm.get("take_profit_pct"), rm.get("max_hold_days")
        cfg["sl"], cfg["tp"], cfg["mh"] = sl, tp, mh
        ok = (sl == cfg["exp_sl"] and tp == cfg["exp_tp"] and mh == cfg["exp_mh"])
        rows.append(f"| `{name}` | {sl} / {tp} / {mh} | "
                    f"{cfg['exp_sl']} / {cfg['exp_tp']} / {cfg['exp_mh']} | "
                    f"{'✅ 일치' if ok else '🔴 **불일치 — config 를 정본으로 씀**'} |")
    return rows


# ────────────────────────────────────────────────────────────────────────────
# 1. DB 읽기 (SELECT 전용)
# ────────────────────────────────────────────────────────────────────────────
def db_fingerprint(conn) -> dict:
    out = {}
    with conn.cursor() as cur:
        for k, q in FINGERPRINT_SQL.items():
            cur.execute(q)
            r = cur.fetchone()
            out[k] = [int(r[0] or 0), int(r[1] or 0), str(r[2])]
    return out


def load_prices(conn) -> pd.DataFrame:
    """창 구간 일봉. `vol_adj = volume * COALESCE(adj_factor,1)` 을 **여기서 한 번만** 만든다.

    이것이 라이브 읽기계층(`QuantDailyReader._SELECT_OHLCV`)과 동일한 척도다.
    이후 어떤 계산에서도 `adj_factor` 를 다시 곱하지 않는다(PREREG §8-6).
    OHLC 결측/비양수 보정은 `universe_lookahead_ladder/run.py` 와 동일하다.
    """
    df = pd.read_sql(f"""
        SELECT stock_code, date, open, high, low, close,
               (volume * COALESCE(adj_factor, 1))::double precision AS vol_adj
        FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}'
        ORDER BY stock_code, date
    """, conn)
    for c in ("open", "high", "low", "close", "vol_adj"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[~(df["close"].isna() | (df["close"] <= 0) | df["datetime"].isna())].copy()
    for c in ("open", "high", "low"):
        m = df[c].isna() | (df[c] <= 0)
        df.loc[m, c] = df.loc[m, "close"]
    df["vol_adj"] = df["vol_adj"].fillna(0).clip(lower=0)
    # 룰이 보는 컬럼명은 `volume` 이다 — 조정된 값을 그 이름으로 넘긴다.
    df["volume"] = df["vol_adj"]
    return df.dropna(subset=["open", "high", "low", "close"])


def load_universe(conn) -> tuple[dict, dict]:
    """`{date: {code: (market_cap, trading_value)}}` 와 결측 통계.

    `trading_value` 는 읽기계층과 동일하게 **`close × (volume × adj_factor)`** 로 직접 만든다
    (저장된 `trading_value` 컬럼은 «조정 close × 원본 volume» 이라 분할 이전 구간이
    과소평가돼 있다 — `quant_daily_reader.py:81-87` 주석과 같은 이유).
    """
    u = pd.read_sql(f"""
        SELECT date, stock_code, market_cap,
               (close * (volume * COALESCE(adj_factor,1)))::double precision AS tv
        FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}'
    """, conn)
    u["market_cap"] = pd.to_numeric(u["market_cap"], errors="coerce")
    u["tv"] = pd.to_numeric(u["tv"], errors="coerce").fillna(0.0)
    stats = dict(
        rows=int(len(u)),
        mcap_missing=int((u["market_cap"].isna() | (u["market_cap"] <= 0)).sum()),
        days_all=int(u["date"].nunique()),
        days_with_mcap=int(u.loc[u["market_cap"] > 0, "date"].nunique()),
    )
    uni: dict = defaultdict(dict)
    for d, code, mc, tv in zip(u["date"].to_numpy(), u["stock_code"].to_numpy(),
                               u["market_cap"].to_numpy(), u["tv"].to_numpy()):
        uni[d][code] = (float(mc) if mc == mc else 0.0, float(tv))
    return dict(uni), stats


def eligible_by_date(uni: dict, screener) -> dict:
    """전략 `base_filter` 를 날짜별로 그대로 통과시킨다 (PREREG §2 — base_filter 전체 고정)."""
    out = {}
    for d, m in uni.items():
        recs = [{"code": c, "name": c, "market_cap": mc, "trading_value": tv}
                for c, (mc, tv) in m.items()]
        out[d] = {r["code"] for r in screener.base_filter(recs)}
    return out


# ────────────────────────────────────────────────────────────────────────────
# 2. 룰 평가 캐시 — 전 arm 공유 (PREREG §2 핵심 장치)
# ────────────────────────────────────────────────────────────────────────────
def build_cache(px: pd.DataFrame, elig: dict, screener, cfg: dict) -> tuple[dict, dict]:
    """`{code: {date: (score_V, score_T, score_P)}}` 와 진행 통계.

    적격(`base_filter` 통과)인 (code, date) 에서만 룰을 평가한다 — 평가 결과와 세 점수를
    **같은 창에서** 만들므로 arm 간 차이는 「어느 점수로 정렬했나」 하나뿐이다.
    """
    params = screener.default_params()
    lb, wm, w = cfg["lookback"], cfg["warmup"], cfg["w"]
    trig: dict = defaultdict(dict)
    n_eval = n_fire = 0
    codes_done = 0
    total_codes = px["stock_code"].nunique()
    t0 = time.perf_counter()
    for code, g in px.groupby("stock_code", sort=False):
        codes_done += 1
        if codes_done % 400 == 0:
            print(f"      ...{codes_done}/{total_codes} 종목 · 평가 {n_eval:,} · "
                  f"발화 {n_fire:,} · {time.perf_counter()-t0:.0f}s", flush=True)
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        closes = g["close"].to_numpy(dtype=float)
        vols = g["volume"].to_numpy(dtype=float)
        n = len(g)
        for i in range(wm, n):
            d = dates[i]
            if code not in elig.get(d, ()):
                continue
            v = screener.match(g.iloc[max(0, i + 1 - lb):i + 1], params)
            n_eval += 1
            if v is None:
                continue
            n_fire += 1
            a = max(0, i + 1 - w)
            cw, vw = closes[a:i + 1], vols[a:i + 1]
            trig[code][d] = (float(vw.mean()), float((cw * vw).mean()), float(closes[i]))
    return dict(trig), dict(n_eval=n_eval, n_fire=n_fire, secs=time.perf_counter() - t0)


# ────────────────────────────────────────────────────────────────────────────
# 3. Arm 선택 — 랭킹 함수 하나만 다르다
# ────────────────────────────────────────────────────────────────────────────
def build_pools(trig: dict, elig: dict) -> dict:
    """`{date: [(code, sV, sT, sP), ...]}` — 그날 base_filter 통과 ∧ 룰 발화한 «적격 풀».

    코드 오름차순으로 고정한다. 라이브는 동점을 DB 행 순서로 깨지만 그건 재현 불가능한
    순서이므로, 여기서는 «코드 오름차순 + 안정정렬»로 결정적으로 깬다.
    """
    pools: dict = defaultdict(list)
    for code, dd in trig.items():
        for d, (sv, st, sp) in dd.items():
            if code in elig.get(d, ()):
                pools[d].append((code, sv, st, sp))
    return {d: sorted(v) for d, v in pools.items()}


def select_deterministic(pools: dict, idx: int) -> dict:
    """`idx` 번째 점수 내림차순 top-`MAX_CANDIDATES`. idx 1=V, 2=T, 3=P."""
    return {d: [c for c, *_ in sorted(v, key=lambda t: t[idx], reverse=True)[:MAX_CANDIDATES]]
            for d, v in pools.items()}


def select_random(pools: dict, seed: int) -> dict:
    """R arm — V·T·P 와 «같은 풀»에서 매일 무작위 `MAX_CANDIDATES` 종목 (비복원)."""
    rng = np.random.RandomState(seed)
    out = {}
    for d in sorted(pools):
        codes = [c for c, *_ in pools[d]]
        k = min(MAX_CANDIDATES, len(codes))
        out[d] = list(rng.choice(codes, size=k, replace=False)) if k else []
    return out


# ────────────────────────────────────────────────────────────────────────────
# 4. 게이트 산출 (PREREG §6) — 해석 없음, 순수 산출
# ────────────────────────────────────────────────────────────────────────────
def daily_overlap(a: dict, b: dict) -> tuple[float, int]:
    """(일별 평균 겹침 종목 수, 겹친 날 수). 양쪽 다 비어있지 않은 날만 센다."""
    vals = []
    for d, av in a.items():
        bv = b.get(d)
        if not av or not bv:
            continue
        vals.append(len(set(av) & set(bv)))
    return (float(np.mean(vals)) if vals else float("nan")), len(vals)


def uniq(sel: dict) -> set:
    out = set()
    for v in sel.values():
        out |= set(v)
    return out


def profile(sel: dict, uni: dict) -> dict:
    """선택 (code, date) 의 중앙 주가·중앙 시총·중앙 거래대금·선택수·고유 종목수.

    주가·시총·거래대금은 «선택된 그 날»의 값이다(주가 = 그날 종가 = 라이브 `prev_close`).
    """
    px_, mc_, tv_ = [], [], []
    n = 0
    for d, codes in sel.items():
        m = uni.get(d, {})
        for c in codes:
            n += 1
            if c in m:
                mc_.append(m[c][0])
                tv_.append(m[c][1])
    return dict(n=n, uniq=len(uniq(sel)),
                med_mcap=float(np.median(mc_)) if mc_ else float("nan"),
                med_tv=float(np.median(tv_)) if tv_ else float("nan"))


def profile_price(sel: dict, pools: dict) -> float:
    """중앙 주가 — 풀에 실린 `sP`(그날 종가)를 그대로 쓴다."""
    vals = []
    for d, codes in sel.items():
        m = {c: sp for c, _, _, sp in pools.get(d, [])}
        vals += [m[c] for c in codes if c in m]
    return float(np.median(vals)) if vals else float("nan")


def decile_hist(sel: dict, pools: dict, uni: dict) -> np.ndarray:
    """선택 종목의 «그날 적격 풀 안에서의 거래대금 10분위» 히스토그램(1=하위 … 10=상위).

    기준 모집단은 «그날 적격 풀»(= base_filter 통과 ∧ 룰 발화) 이다 — arm 이 실제로
    고르는 모집단과 같은 집합이라야 분위 비교가 뜻을 갖는다.
    """
    h = np.zeros(N_DECILES, dtype=float)
    for d, codes in sel.items():
        pool = pools.get(d) or []
        if len(pool) < 2:
            continue
        m = uni.get(d, {})
        tvs = np.array([m.get(c, (0.0, 0.0))[1] for c, *_ in pool], dtype=float)
        order = tvs.argsort(kind="stable")
        rank = np.empty(len(tvs), dtype=float)
        rank[order] = np.arange(len(tvs), dtype=float)
        dec = np.minimum((rank / len(tvs) * N_DECILES).astype(int), N_DECILES - 1)
        pos = {c: k for k, (c, *_) in enumerate(pool)}
        for c in codes:
            if c in pos:
                h[dec[pos[c]]] += 1
    return h


def ks_distance(h1: np.ndarray, h2: np.ndarray) -> float:
    if h1.sum() <= 0 or h2.sum() <= 0:
        return float("nan")
    c1, c2 = np.cumsum(h1 / h1.sum()), np.cumsum(h2 / h2.sum())
    return float(np.max(np.abs(c1 - c2)))


def changed_stock_days(selV: dict, selT: dict) -> list[tuple[str, str, str]]:
    """V→T 로 «선택이 바뀐 종목-일». (date, code, 'dropped'|'added') 목록."""
    out = []
    for d in set(selV) | set(selT):
        v, t = set(selV.get(d, [])), set(selT.get(d, []))
        out += [(d, c, "dropped") for c in sorted(v - t)]
        out += [(d, c, "added") for c in sorted(t - v)]
    return out


# ────────────────────────────────────────────────────────────────────────────
# 5. main
# ────────────────────────────────────────────────────────────────────────────
def stage1() -> int:
    conn = psycopg2.connect(**DSN)
    say("# 랭킹 함수 반사실 — 1단계 게이트 (PREREG §6, PnL 미조회)")
    say("")
    say("사전등록: [`PREREG.md`](PREREG.md)(동결). 창 = **W-long 2021-01-01 ~ 2026-05-31** 하나.")
    say("")
    say("🔴 이 문서는 PREREG **§6(1단계 게이트)까지만** 다룬다. "
        "**해석·「좋다/나쁘다」 판단은 없다** — 순수 산출이다. "
        "결과 계산(§4·§5, PnL 필요)은 2단계다.")
    say("")
    say("🔑 이 실행은 `BookBacktester` 를 **import 하지도 호출하지도 않는다** — "
        "거래당 수익률이 메모리에 들어올 경로 자체가 없다. "
        "그래서 §6-5 의 「거래 수」는 **«진입 트리거 수»**(arm 이 그날 고른 종목-일 수)로 센다.")
    say("")

    # ── 0. 청산 파라미터 대조 ───────────────────────────────────────────────
    say("## 0. `config.yaml` 에서 읽은 청산 파라미터 (하드코딩 아님)")
    say("")
    say("🔴 1단계는 청산을 «쓰지 않는다». 2단계가 쓸 값을 여기서 못박아 인쇄한다.")
    say("")
    say("| 전략 | config (sl/tp/max_hold) | 지시서 기대값 | 일치 |")
    say("|---|---|---|---|")
    for r in verify_strategy_params():
        say(r)
    say("")

    # ── DB 지문 ─────────────────────────────────────────────────────────────
    fp = db_fingerprint(conn)
    say("## 0b. DB 지문 (`regen_gate.py` 형식 승계 · 5슬라이스)")
    say("")
    say("| 슬라이스 | 행 수 | 종목 수 | max(date) |")
    say("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        say(f"| `{k}` | {a:,} | {b:,} | {c} |")
    say("")

    # ── 데이터 적재 ─────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    px = load_prices(conn)
    uni, ustats = load_universe(conn)
    conn.close()
    dates_all = sorted(uni)
    print(f"[load] 일봉 {len(px):,}행 / {px.stock_code.nunique():,}종목 · "
          f"{time.perf_counter()-t0:.0f}s", flush=True)

    say("## 1. 표본 · 창 · 워밍업")
    say("")
    say(f"- 일봉 **{len(px):,}행** / **{px.stock_code.nunique():,}종목** / "
        f"거래일 **{len(dates_all):,}일** (창 {W0}~{W1})")
    say(f"- 창 «이전» 히스토리: **0행** — `daily_prices` 의 최소일이 "
        f"**{px['date'].min()}** 이라 창 시작보다 이르지 않다. "
        f"⇒ 워밍업(ma5 25봉 · ma20 35봉 · minervini 40봉)은 **창 «안»에서 소진**된다.")
    say(f"- 종목코드 술어 `^[0-9][0-9A-Z]{{5}}$` · 의사티커 KOSPI/KOSDAQ/KS11/KQ11 명시 배제.")
    say("")

    # ── 6. market_cap 결측률 (PREREG §6-6 / §7-4) ──────────────────────────
    say("## 2. 🔴 `market_cap` 결측률 (PREREG §6-6 · §7-4)")
    say("")
    miss = ustats["mcap_missing"] / ustats["rows"] * 100 if ustats["rows"] else float("nan")
    say(f"- 창 안 전체 행 **{ustats['rows']:,}** 중 `market_cap` 결측(NULL 또는 ≤0) "
        f"**{ustats['mcap_missing']:,}** = **{miss:.1f}%**")
    say(f"- `market_cap` 이 하나라도 있는 거래일 **{ustats['days_with_mcap']:,}** / "
        f"전체 거래일 **{ustats['days_all']:,}**")
    say("")
    say("연도-월별 `market_cap>0` 종목 수(그날 몇 종목이 시총을 갖는가):")
    say("")
    say("| 연-월 | 거래일 | 최소 | 최대 | 평균 |")
    say("|---|---|---|---|---|")
    bym: dict = defaultdict(list)
    for d in dates_all:
        bym[d[:7]].append(sum(1 for mc, _ in uni[d].values() if mc > 0))
    for m in sorted(bym):
        v = bym[m]
        say(f"| {m} | {len(v)} | {min(v):,} | {max(v):,} | {int(np.mean(v)):,} |")
    say("")
    say("🔴 세 전략의 `base_filter` 는 시총 결측을 **fail-closed 로 제외**한다"
        "(`strategies/_rule_screener_base.py::_passes_market_cap`). "
        "⇒ **시총이 없는 날은 적격 풀이 비고, 어떤 arm 도 아무것도 고르지 않는다.**")
    say("")

    # ── 전략별 처리 ─────────────────────────────────────────────────────────
    all_changed: dict = {}
    notes: dict = {}
    for name, cfg in STRATS.items():
        scr = cfg["screener"]()
        say(f"---")
        say("")
        say(f"## `{name}` — {cfg['role']} (w={cfg['w']})")
        say("")
        print(f"\n[{name}] 시작", flush=True)

        elig = eligible_by_date(uni, scr)
        n_elig_days = sum(1 for d in dates_all if elig.get(d))
        elig_sizes = [len(elig[d]) for d in dates_all if elig.get(d)]
        say(f"- 적격일(base_filter 통과 종목이 1개 이상인 날) **{n_elig_days:,}** / "
            f"{len(dates_all):,}일 · 적격 풀 크기 중앙 "
            f"**{int(np.median(elig_sizes)) if elig_sizes else 0:,}** "
            f"(최소 {min(elig_sizes) if elig_sizes else 0:,} · "
            f"최대 {max(elig_sizes) if elig_sizes else 0:,})")
        print(f"  적격일 {n_elig_days} · 룰 평가 시작", flush=True)

        trig, tstats = build_cache(px, elig, scr, cfg)
        say(f"- 룰 평가 **{tstats['n_eval']:,}회** / 발화 **{tstats['n_fire']:,}건** / "
            f"발화 종목 **{len(trig):,}** · {tstats['secs']:.0f}s")

        pools = build_pools(trig, elig)
        pool_days = sorted(d for d in pools if pools[d])
        psz = [len(pools[d]) for d in pool_days]
        say(f"- **적격 풀**(base_filter 통과 ∧ 룰 발화) 이 비지 않은 날 **{len(pool_days):,}** · "
            f"풀 크기 중앙 **{int(np.median(psz)) if psz else 0}** "
            f"(최소 {min(psz) if psz else 0} · 최대 {max(psz) if psz else 0})")
        n_saturated = sum(1 for d in pool_days if len(pools[d]) <= MAX_CANDIDATES)
        say(f"- 🔴 풀 크기 ≤ `max_candidates`(={MAX_CANDIDATES}) 인 날 **{n_saturated:,}** / "
            f"{len(pool_days):,} — ***그런 날은 네 arm 이 «같은 집합»을 고른다*** "
            f"(랭킹 함수가 아무것도 가르지 않는다).")
        say("")

        selV = select_deterministic(pools, 1)
        selT = select_deterministic(pools, 2)
        selP = select_deterministic(pools, 3)
        selR = [select_random(pools, s) for s in range(N_SEEDS)]
        print(f"  선택 완료 (V/T/P + R×{N_SEEDS})", flush=True)

        # ── §6-1 겹침 행렬 ──────────────────────────────────────────────────
        say(f"### {name} — §6-1 arm 간 선택 종목 겹침")
        say("")
        say(f"일별 평균 겹침 종목 수(최대 {MAX_CANDIDATES}). R 은 시드 {N_SEEDS}개의 평균이다.")
        say("")
        det = {"V": selV, "T": selT, "P": selP}
        say("| | V | T | R | P |")
        say("|---|---|---|---|---|")
        for a in ("V", "T", "P"):
            row = [f"| **{a}** "]
            for b in ("V", "T"):
                m, _ = daily_overlap(det[a], det[b])
                row.append(f"| {m:.2f} ")
            rs = [daily_overlap(det[a], r)[0] for r in selR]
            row.append(f"| {np.nanmean(rs):.2f} ")
            m, _ = daily_overlap(det[a], det["P"])
            row.append(f"| {m:.2f} |")
            say("".join(row))
        rr = [daily_overlap(selR[i], selR[j])[0]
              for i in range(N_SEEDS) for j in range(i + 1, N_SEEDS)]
        say(f"| **R** | {np.nanmean([daily_overlap(r, selV)[0] for r in selR]):.2f} "
            f"| {np.nanmean([daily_overlap(r, selT)[0] for r in selR]):.2f} "
            f"| {np.nanmean(rr):.2f} "
            f"| {np.nanmean([daily_overlap(r, selP)[0] for r in selR]):.2f} |")
        say("")
        uV, uT, uP = uniq(selV), uniq(selT), uniq(selP)
        uR = [uniq(r) for r in selR]
        say("전 기간 고유 종목 수 · 교집합:")
        say("")
        say("| | 고유 종목 | ∩V | ∩T | ∩P |")
        say("|---|---|---|---|---|")
        for lab, s in (("V", uV), ("T", uT), ("P", uP)):
            say(f"| **{lab}** | {len(s):,} | {len(s & uV):,} | {len(s & uT):,} | {len(s & uP):,} |")
        say(f"| **R**(시드평균) | {np.mean([len(s) for s in uR]):.0f} | "
            f"{np.mean([len(s & uV) for s in uR]):.0f} | "
            f"{np.mean([len(s & uT) for s in uR]):.0f} | "
            f"{np.mean([len(s & uP) for s in uR]):.0f} |")
        say(f"| **R**(20시드 합집합) | {len(set().union(*uR)) if uR else 0:,} | | | |")
        say("")

        # ── §6-2 arm 별 프로필 ──────────────────────────────────────────────
        say(f"### {name} — §6-2 arm 별 중앙 주가 · 시총 · 거래대금 · 종목 수")
        say("")
        say("| Arm | 선택 종목-일 | 고유 종목 | 중앙 주가(원) | 중앙 시총(억) | 중앙 거래대금(억) |")
        say("|---|---|---|---|---|---|")
        for lab, s in (("V (현행)", selV), ("T (거래대금)", selT), ("P (주가)", selP)):
            p = profile(s, uni)
            say(f"| **{lab}** | {p['n']:,} | {p['uniq']:,} | {profile_price(s, pools):,.0f} | "
                f"{p['med_mcap']/1e8:,.0f} | {p['med_tv']/1e8:,.1f} |")
        rp = [profile(r, uni) for r in selR]
        rprice = [profile_price(r, pools) for r in selR]
        say(f"| **R (무작위, 20시드 평균)** | {np.mean([p['n'] for p in rp]):,.0f} | "
            f"{np.mean([p['uniq'] for p in rp]):,.0f} | {np.nanmean(rprice):,.0f} | "
            f"{np.nanmean([p['med_mcap'] for p in rp])/1e8:,.0f} | "
            f"{np.nanmean([p['med_tv'] for p in rp])/1e8:,.1f} |")
        say("")

        # ── §6-3 쏠림 (시점 축) ─────────────────────────────────────────────
        ch = changed_stock_days(selV, selT)
        all_changed[name] = ch
        notes[name] = dict(
            elig_days=n_elig_days, pool_days=len(pool_days), saturated=n_saturated,
            first_change=min((d for d, _, _ in ch), default="—"),
            last_change=max((d for d, _, _ in ch), default="—"),
            first_sel=min((d for d, v in selV.items() if v), default="—"),
        )
        say(f"### {name} — §6-3 🔴 쏠림 점검 (시점 축) — V→T 로 선택이 바뀐 종목-일")
        say("")
        say(f"바뀐 종목-일 **{len(ch):,}건** "
            f"(V 에서 빠짐 {sum(1 for _,_,k in ch if k=='dropped'):,} · "
            f"T 에서 들어옴 {sum(1 for _,_,k in ch if k=='added'):,})")
        say("")
        if ch:
            yr = Counter(d[:4] for d, _, _ in ch)
            say("| 연도 | 바뀐 종목-일 | 비중 |")
            say("|---|---|---|")
            for y in sorted(yr):
                say(f"| {y} | {yr[y]:,} | {yr[y]/len(ch)*100:.1f}% |")
            top_y, top_n = max(yr.items(), key=lambda kv: kv[1])
            say("")
            if top_n / len(ch) > 0.50:
                say(f"🔴 **{top_y} 가 변화의 {top_n/len(ch)*100:.1f}% (>50%) — "
                    f"「국면 특이 → 판별 보류」.** 2단계에서 PnL 은 조회하되 "
                    f"결론에 «단일 국면 의존»을 명시한다 (PREREG §6-3).")
            else:
                say(f"✅ 최대 연도({top_y}) 비중 **{top_n/len(ch)*100:.1f}% ≤ 50%** — "
                    f"연도 쏠림 문턱 통과.")
            say("")
            mo = Counter(d[:7] for d, _, _ in ch)
            say("<details><summary>월별 분포</summary>")
            say("")
            say("| 연-월 | 바뀐 종목-일 | 비중 |")
            say("|---|---|---|")
            for m in sorted(mo):
                say(f"| {m} | {mo[m]:,} | {mo[m]/len(ch)*100:.1f}% |")
            say("")
            say("</details>")
        else:
            say("🔴 바뀐 종목-일이 **0건** — V 와 T 가 «완전히 같은» 집합을 골랐다.")
        say("")

        # ── §6-4 거래대금 10분위 · KS ───────────────────────────────────────
        hV, hT = decile_hist(selV, pools, uni), decile_hist(selT, pools, uni)
        say(f"### {name} — §6-4 V·T 선택 집합의 일별 거래대금 10분위 분포 · KS 거리")
        say("")
        say("기준 모집단 = **그날 적격 풀**(base_filter 통과 ∧ 룰 발화). 1=하위 10% … 10=상위 10%.")
        say("")
        say("| 10분위 | " + " | ".join(str(i + 1) for i in range(N_DECILES)) + " |")
        say("|---|" + "---|" * N_DECILES)
        for lab, h in (("V", hV), ("T", hT)):
            tot = h.sum() or 1
            say(f"| **{lab}** | " + " | ".join(f"{x/tot*100:.1f}%" for x in h) + " |")
        say("")
        say(f"**KS 거리(V vs T) = {ks_distance(hV, hT):.3f}**")
        say("")
        say("🔑 PREREG §6-4: **KS > 0.20 은 예상된다**(그게 이 실험의 취지다). "
            "여기서는 «자동 판별불가»로 쓰지 않고 **크기만 기록**한다 — "
            "축이 «의도적으로» 유동성을 바꾸기 때문이다.")
        say("")

        # ── §6-5 거래 수 대칭성 ─────────────────────────────────────────────
        say(f"### {name} — §6-5 arm 별 진입 트리거 수 (거래 수 대칭성)")
        say("")
        counts = {"V": sum(len(v) for v in selV.values()),
                  "T": sum(len(v) for v in selT.values()),
                  "P": sum(len(v) for v in selP.values())}
        rc = [sum(len(v) for v in r.values()) for r in selR]
        say("| Arm | 진입 트리거 수 |")
        say("|---|---|")
        for k, v in counts.items():
            say(f"| **{k}** | {v:,} |")
        say(f"| **R** (20시드) | 평균 {np.mean(rc):,.0f} · 최소 {min(rc):,} · 최대 {max(rc):,} |")
        allc = list(counts.values()) + [float(np.mean(rc))]
        lo, hi = min(allc), max(allc)
        say("")
        if lo > 0 and hi / lo >= 2.0:
            say(f"🔴 **arm 간 트리거 수가 {hi/lo:.2f}배 벌어졌다(≥2배)** — "
                f"비교가 「같은 전략의 두 버전」이 아니라 「다른 빈도의 두 전략」이 된다. "
                f"2단계 판정문에 병기할 것 (PREREG §6-5).")
        else:
            say(f"✅ arm 간 트리거 수 최대/최소 = **{hi/lo:.2f}배 (<2배)** — 대칭성 통과.")
        say("")
        say(f"🔑 PREREG §7-7 표본 문턱(전략별 거래 수 < 200 → 「표본 부족 → 판별 보류」): "
            f"현재 트리거 수 기준 **{'🔴 미달' if min(counts.values()) < 200 else '✅ 충족'}** "
            f"(V {counts['V']:,} · T {counts['T']:,} · P {counts['P']:,}). "
            f"⚠️ 실현 거래 수는 이보다 «적다» — 종목당 단일 포지션이 겹치는 트리거를 삼킨다. "
            f"확정은 2단계 몫이다.")
        say("")

    # ── §6-3 전략별 구성비 (판정엔 안 씀) ──────────────────────────────────
    say("---")
    say("")
    say("## 3. §6-3 전략별 구성비 — V→T 변화의 전략별 분포 (🔴 판정에는 쓰지 않는다)")
    say("")
    say("전략별로 «따로» 판정하므로 이 표는 판정에 들어가지 않는다. "
        "나중에 전략을 합치려는 사람이 그 위험을 볼 수 있게 남긴다 (PREREG §6-3).")
    say("")
    tot = sum(len(v) for v in all_changed.values())
    say("| 전략 | 바뀐 종목-일 | 비중 |")
    say("|---|---|---|")
    for k, v in all_changed.items():
        say(f"| `{k}` | {len(v):,} | {len(v)/tot*100 if tot else float('nan'):.1f}% |")
    say(f"| **합계** | **{tot:,}** | 100.0% |")
    say("")

    say("## 4. 등록 외 조합 (PREREG §8-2 · §9)")
    say("")
    say("**계산한 적 없다.** arm 은 V·T·R·P 넷뿐이고 창 길이 스윕·가중 혼합 score·"
        "거래대금 로그 변환은 이 스크립트에 구현되어 있지 않다.")
    say("")

    # ── 실행 중 관찰 (사전등록 이행 관련, 해석 아님) ────────────────────────
    say("## 5. 🔴 실행 중 관찰한 것 (사전등록 이행 관련 · 해석 아님)")
    say("")
    say("`stop_vol_fit_gate/GATE.md` 의 같은 이름 절을 승계한다 — "
        "**결과 해석이 아니라 「사전등록을 어떻게 이행했는가」의 기록**이다.")
    say("")
    say("### 5-1. 🔴 창이 사전등록대로 실현되지 않았다 (§3 vs 실측)")
    say("")
    say("| 전략 | 적격일 / 1,325 | 풀 비지 않은 날 | 풀 ≤10 인 날 | 첫 선택일 | 첫 V→T 변화일 | 마지막 |")
    say("|---|---|---|---|---|---|---|")
    for k, v in notes.items():
        say(f"| `{k}` | {v['elig_days']:,} | {v['pool_days']:,} | {v['saturated']:,} | "
            f"{v['first_sel']} | {v['first_change']} | {v['last_change']} |")
    say("")
    say("PREREG §3 은 창을 **2021-01-01~2026-05-31(5.4년)** 로 동결했다. 그런데 §2 표대로 "
        "`market_cap` 이 **2023-04-25 부터만** 존재하고 **2024-03 중순까지 하루 8종목뿐**이며, "
        "세 전략의 `base_filter` 는 시총 결측을 fail-closed 로 제외한다. "
        "⇒ ***창의 앞부분에서는 적격 풀이 비어 어떤 arm 도 아무것도 고르지 않는다.***")
    say("")
    say("🔴 **따라서 §6-3 의 「연도별 비중」 분모에는 2021·2022·2023 이 «한 건도» 들어 있지 않다.** "
        "「최대 연도 ≤50% ⇒ 쏠림 통과」는 **2024~2026 만으로 이루어진 분모 위에서 계산된 값**이다. "
        "이 사실 없이 그 ✅ 를 인용하면 안 된다.")
    say("")
    say("### 5-2. 🔴 §6-5 「거래 수 대칭성」은 1단계에서 구조적으로 항상 통과한다")
    say("")
    say("네 arm 은 모두 그날 적격 풀에서 `min(max_candidates, |풀|)` 개를 고르므로 "
        "**진입 트리거 수가 정의상 완전히 같다**(실측 전부 1.00배). "
        "⇒ ***이 절의 ✅ 는 「검사를 통과했다」가 아니라 「이 단계에서는 검사가 성립하지 않는다」는 뜻이다.*** "
        "PREREG §6-5 가 의도한 비대칭은 **실현 거래 수**에서만 나타날 수 있고, 그건 청산 판정 "
        "= 수익률 계산을 요구하므로 **2단계 몫**이다.")
    say("")
    say("### 5-3. 척도 — `volume × adj_factor` 를 로더에서 «한 번» 적용했다")
    say("")
    say("PREREG 척도 고지는 *「`volume` 은 읽기계층에서 조정된다」* 를 전제한다. "
        "이 스크립트는 성능 때문에 raw SQL 로 읽으므로 그 보정을 "
        "`load_prices()`·`load_universe()` 에서 재현했다 — "
        "`db/quant_daily_reader.py::_SELECT_OHLCV` 와 **같은 식**(`volume * COALESCE(adj_factor,1)`)이다. "
        "이 보정이 «없으면» `ac69084` **이전** 척도가 되어 척도 고지를 어긴다. "
        "적용은 로더 1회뿐이고 이후 어디에서도 `adj_factor` 를 다시 곱하지 않는다(§8-6).")
    say("")
    say("### 5-4. 승계 원본과 달라진 지점 · 재현하지 «않은» 라이브 동작")
    say("")
    say("| 항목 | 이 실행 | 비고 |")
    say("|---|---|---|")
    say("| 종목코드 술어 | `^[0-9][0-9A-Z]{5}$` (2,788종목) | "
        "승계 원본 `universe_lookahead_ladder` 는 `^[0-9]{5}[0-9A-Z]$` (2,734종목). "
        "신형 코드(`0001A0` 등) 54종목이 더 든다 |")
    say("| 불가능봉 가드 | **적용 안 함** | "
        "라이브 `scan()` 에는 있으나(`_rule_screener_base.py:96`) 승계 원본에는 없고 "
        "PREREG §2 고정 목록에도 없다. 전 arm 에 동일하게 걸리지만 "
        "**풀에서 한 종목이 빠지면 11번째가 들어오므로 arm 마다 대체 종목이 다르다** — 완전 중립은 아니다 |")
    say("| 동점 처리 | 코드 오름차순 + 안정정렬 | "
        "라이브는 DB 행 순서라 재현 불가능하다. 동점이 흔한 **arm P**(같은 종가)에서만 실질 영향 |")
    say("| 유니버스 스냅샷 폴백 | **재현 안 함** | "
        "라이브 `get_universe_snapshot` 은 `date <= scan_date` 중 최신 «완전 퀀트일»로 폴백한다. "
        "여기서는 그날 행만 쓴다(승계 원본과 동일). 2024-03 이후는 매일 완전 적재라 무영향 |")
    say("| 워밍업 | **창 «안»에서 소진** | "
        "PREREG §3 은 *「창 이전 히스토리로 채운다」* 지만 `daily_prices` 최소일이 "
        "**2021-01-04** 라 창 이전 행이 **0**이다. 위 5-1 때문에 실질 영향은 없다 |")
    say("")
    say("### 5-5. 어떤 컬럼만 SELECT 했는가 — PnL 미조회 보장")
    say("")
    say("- `daily_prices`: `stock_code` · `date` · `open` · `high` · `low` · `close` · "
        "`volume` · `adj_factor` · `market_cap` — 이상 **9개 컬럼만**.")
    say("- `virtual_trading_records` 등 **매매 원장 테이블은 어느 것도 조회하지 않았다.** "
        "`BookBacktester` 는 import 조차 하지 않는다 ⇒ 거래당 수익률이 산출된 적이 없다.")
    say("")

    (BASE / "GATE.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] GATE.md", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage1", action="store_true",
                    help="PREREG §6 1단계 게이트만 산출한다 (PnL 미조회). 현재 유일한 모드.")
    a = ap.parse_args()
    if not a.stage1:
        print("이 스크립트는 지금 `--stage1` 만 구현되어 있다 "
              "(PREREG §6 = PnL 을 보기 «전»에 확정하는 1단계 게이트).\n"
              "2단계(§4·§5, 거래당 수익률)는 별도 지시로 구현한다.", flush=True)
        return 2
    return stage1()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
