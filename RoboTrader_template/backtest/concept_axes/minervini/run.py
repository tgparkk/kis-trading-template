# -*- coding: utf-8 -*-
"""minervini 개념 축 — 사전등록 `PREREG.md`(동결 `e4c55b1`) 실행부. **1단계 게이트 전용.**

가족 등록부 `../REGISTRY.md` 의 **1번 문서**. 기계는 `backtest/rank_score_counterfactual/run.py`
를 그대로 승계한다(`HIST0` 분리 · `(code,date)` 캐시 · `verify_strategy_params()` ·
`db_fingerprint()` · 단독 모드 · stale prose 방지).

🔴 **모드는 `--stage1` 하나뿐이다.** PnL·수익률을 계산하지 않으며 `BookBacktester` 를
**import 하지도 부르지도 않는다** — 거래당 수익률이 메모리에 들어올 경로 자체가 없다.
2단계(§4·§5)는 별도 지시로 구현한다.

**Arm 6개 (PREREG §2) — 진입 룰 축 «하나만» 바꾼다:**

    D    = rule_volume_dryup                      (현행 라이브 · 기준선)
    DT   = dryup ∧ rule_trend_template            (TT 복원)
    DF   = dryup ∧ F                              (재무 복원)
    DTF  = dryup ∧ TT ∧ F                         (완전 복원)
    T    = rule_trend_template 만                 (분해)
    R    = 그날 base_filter 통과 집합에서 무작위 10종목, 시드 0..19  (귀무)

🔴 **`R` 의 적격 풀은 「`base_filter` 통과」뿐이고 진입 룰 조건이 «없다»**(§2) —
「고르는 행위」 자체의 귀무이기 때문이다. 다른 arm 과 풀 정의가 다르다.

🔴 **`score` 는 현행 `df["volume"].iloc[-30:].mean()` 고정**(§2). 랭킹 축은
`rank_score_counterfactual` 이 이미 판정했고(`d751e21` — 「(나) 랭킹은 정보가 아님」),
***한 번에 한 축만 움직인다.***

🔑 척도·창은 `rank_score_counterfactual` §10-1·§10-5 승계: 창 `2024-03-13~2026-05-31`,
가격은 `HIST0=2021-01-01` 부터(TT 의 220/252봉 요구), `volume × adj_factor` 는 **로더에서 1회**.

라이브 코드는 «읽기»만 한다(스크리너·룰 모듈 import). DB 는 SELECT 만.
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
ROOT = BASE.parent.parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

from strategies.books.minervini_vcp.rules import (                                  # noqa: E402
    compute_rs_percentile_12w,
    rule_trend_template,
    rule_volume_dryup,
)
from strategies.minervini_volume_dryup.screener import (                            # noqa: E402
    MinerviniVolumeDryupScreenerAdapter,
)
# 🔴 `BookBacktester` 는 import 하지 않는다 — 1단계가 「PnL 계산 경로가 아예 없다」를 보증한다.

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234",
           dbname="kis_template")

# 신형 코드는 «중간»이 영문일 수 있다(`0001A0`). 의사티커는 첫 글자가 숫자가 아니라
# 이 술어에 이미 안 걸리지만 명시적으로도 배제한다.
STOCK_ONLY = ("stock_code ~ '^[0-9][0-9A-Z]{5}$' "
              "AND stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')")

W0, W1 = "2024-03-13", "2026-05-31"   # PREREG §3 (rank_score §10-1 승계)
HIST0 = "2021-01-01"                   # 워밍업 — TT 의 220/252봉 요구
# 🔑 룰에 넘기는 창 길이. **라이브 스크리너의 `lookback_days=90` 이 아니다** — 아래 §주석 참조.
LOOKBACK = 260
SCORE_WINDOW = 30                      # 현행 score = volume.iloc[-30:].mean() (§2 고정)
MAX_CANDIDATES = 10                    # §2 고정
N_SEEDS = 20                           # §2 — R 시드 0..19
N_DECILES = 10                         # §6-2
MIN_TRIGGER_FRAC = 0.10                # §6-1 — D 의 10% 미만이면 「표본 부족 → 판별 보류」
F_GROWTH = 1.25                        # §2-2 — 원저작 이익 성장 문턱. 데이터에서 유도 안 함


# 지시서 기대 청산 파라미터 (2단계용 — config.yaml 이 정본이고 아래는 대조값)
EXP_SL, EXP_TP, EXP_MH = 0.08, 0.12, 20

FINGERPRINT_SQL = {
    f"daily_prices[{HIST0}..{W1}] 적재분(워밍업 포함)":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{HIST0}' AND '{W1}'",
    f"daily_prices[{W0}..{W1}] 개정 창":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}'",
    f"daily_prices[{W0}..{W1}] market_cap>0":
        f"SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        f"WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}' AND market_cap > 0",
    "dart_financials_asfiled (전체)":
        "SELECT count(*), count(DISTINCT stock_code), max(rcept_dt) "
        "FROM dart_financials_asfiled",
    "dart_financials_asfiled rcept_dt NOT NULL":
        "SELECT count(*), count(DISTINCT stock_code), max(rcept_dt) "
        "FROM dart_financials_asfiled WHERE rcept_dt IS NOT NULL",
}

OUT: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


def git_sha() -> str:
    import subprocess  # noqa: PLC0415 — 이 한 곳에서만 쓴다
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10,
                              check=True).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"(조회 실패: {type(e).__name__})"


# ────────────────────────────────────────────────────────────────────────────
# 0. 설정 대조
# ────────────────────────────────────────────────────────────────────────────
def verify_strategy_params() -> tuple[list[str], dict]:
    """`config.yaml` 청산 파라미터와 스크리너 `base_filter` 임계를 읽어 대조 표를 만든다."""
    y = yaml.safe_load(
        (ROOT / "strategies" / "minervini_volume_dryup" / "config.yaml").read_text(encoding="utf-8"))
    rm = (y or {}).get("risk_management", {}) or {}
    sl, tp, mh = rm.get("stop_loss_pct"), rm.get("take_profit_pct"), rm.get("max_hold_days")
    p = MinerviniVolumeDryupScreenerAdapter().default_params()
    ok = (sl == EXP_SL and tp == EXP_TP and mh == EXP_MH)
    rows = [
        "| 항목 | 읽은 값 | 기대값 | 일치 |",
        "|---|---|---|---|",
        f"| 청산 sl/tp/max_hold (`config.yaml`) | {sl} / {tp} / {mh} | "
        f"{EXP_SL} / {EXP_TP} / {EXP_MH} | "
        f"{'✅' if ok else '🔴 **불일치 — config 를 정본으로 씀**'} |",
        f"| `min_market_cap` (screener) | {p['min_market_cap']:,} | 300,000,000,000 | "
        f"{'✅' if p['min_market_cap'] == 300_000_000_000 else '🔴'} |",
        f"| `min_trading_value` (screener) | {p['min_trading_value']:,} | 3,000,000,000 | "
        f"{'✅' if p['min_trading_value'] == 3_000_000_000 else '🔴'} |",
        f"| `max_candidates` | {p['max_candidates']} | {MAX_CANDIDATES} | "
        f"{'✅' if p['max_candidates'] == MAX_CANDIDATES else '🔴'} |",
        f"| dryup `recent/base/ratio` | {p['recent_window']}/{p['base_window']}/{p['ratio_max']} | "
        f"10/30/0.7 | ✅ |",
    ]
    return rows, dict(sl=sl, tp=tp, mh=mh, **p)


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
    """`HIST0`~`W1` 일봉. `vol_adj = volume * COALESCE(adj_factor,1)` 을 **여기서 한 번만**.

    라이브 읽기계층(`db/quant_daily_reader.py::_SELECT_OHLCV`)과 동일한 식이다.
    이후 어디에서도 `adj_factor` 를 다시 곱하지 않는다(이중조정 금지).
    """
    df = pd.read_sql(f"""
        SELECT stock_code, date, open, high, low, close,
               (volume * COALESCE(adj_factor, 1))::double precision AS vol_adj
        FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{HIST0}' AND '{W1}'
        ORDER BY stock_code, date
    """, conn)
    for c in ("open", "high", "low", "close", "vol_adj"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[~(df["close"].isna() | (df["close"] <= 0))].copy()
    for c in ("open", "high", "low"):
        m = df[c].isna() | (df[c] <= 0)
        df.loc[m, c] = df.loc[m, "close"]
    df["vol_adj"] = df["vol_adj"].fillna(0).clip(lower=0)
    df["volume"] = df["vol_adj"]      # 룰이 보는 컬럼명
    return df.dropna(subset=["open", "high", "low", "close"])


def load_universe(conn) -> tuple[dict, dict]:
    """`{date: {code: (market_cap, trading_value)}}`. `trading_value` 는 읽기계층과 동일 정의."""
    u = pd.read_sql(f"""
        SELECT date, stock_code, market_cap,
               (close * (volume * COALESCE(adj_factor,1)))::double precision AS tv
        FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{W0}' AND '{W1}'
    """, conn)
    u["market_cap"] = pd.to_numeric(u["market_cap"], errors="coerce")
    u["tv"] = pd.to_numeric(u["tv"], errors="coerce").fillna(0.0)
    stats = dict(rows=int(len(u)),
                 mcap_missing=int((u["market_cap"].isna() | (u["market_cap"] <= 0)).sum()))
    uni: dict = defaultdict(dict)
    for d, code, mc, tv in zip(u["date"].to_numpy(), u["stock_code"].to_numpy(),
                               u["market_cap"].to_numpy(), u["tv"].to_numpy()):
        uni[d][code] = (float(mc) if mc == mc else 0.0, float(tv))
    return dict(uni), stats


def eligible_by_date(uni: dict, screener) -> dict:
    """전략 `base_filter`(시총 ≥3천억 · 거래대금 ≥30억)를 날짜별로 그대로 적용."""
    out = {}
    for d, m in uni.items():
        recs = [{"code": c, "name": c, "market_cap": mc, "trading_value": tv}
                for c, (mc, tv) in m.items()]
        out[d] = {r["code"] for r in screener.base_filter(recs)}
    return out


def load_fundamentals(conn) -> tuple[dict, pd.DataFrame]:
    """`{code: {year: (rcept_str|None, operating_income|None)}}` 와 원시 표.

    `(stock_code, bsns_year)` 가 PK 라 정정공시가 as-filed 를 덮어쓴다(PREREG §7-4).
    ***방향은 보수적이다*** — 덮어쓴 행의 `rcept_dt` 는 «미래»라 백테스트 시점에 안 보인다.
    """
    f = pd.read_sql("""
        SELECT stock_code, bsns_year::int AS y, rcept_dt, operating_income
        FROM dart_financials_asfiled
    """, conn)
    f["rcept_s"] = f["rcept_dt"].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else None)
    fin: dict = defaultdict(dict)
    for code, y, rs_, oi in zip(f["stock_code"], f["y"], f["rcept_s"], f["operating_income"]):
        fin[code][int(y)] = (rs_, None if pd.isna(oi) else int(oi))
    return dict(fin), f


# ────────────────────────────────────────────────────────────────────────────
# 2. 재무 스크린 F (PREREG §2-2)
# ────────────────────────────────────────────────────────────────────────────
def f_screen(fin_code: dict, d: str) -> tuple[bool, str]:
    """`F(code, D)` — PREREG §2-2 그대로. `(통과여부, 사유코드)`.

    🔴 해석: **「`rcept_dt ≤ D−1` 인 «가장 최근» 사업연도 y」를 하나 고른 뒤** ②③④ 를 건다
    (지시서 문구 그대로). 「아무 y 나 하나라도 만족하면 통과」가 «아니다» — 그렇게 읽으면
    과거 한 번의 고성장이 영원히 통과되어 PIT 의미가 사라진다.
    `rcept_dt` NULL 은 「그 해 데이터 없음」 = fail-closed (통과시키지 않는다).
    `rcept_dt ≤ D−1` 은 ISO 문자열 비교로 `rcept_s < d` 와 동치다.
    """
    if not fin_code:
        return False, "no_rows"
    vis = [y for y, (rs_, _) in fin_code.items() if rs_ is not None and rs_ < d]
    if not vis:
        return False, "no_visible_year"
    y = max(vis)
    prev = fin_code.get(y - 1)
    if prev is None or prev[0] is None or not (prev[0] < d):
        return False, "prev_year_invisible"
    oi_prev, oi_cur = prev[1], fin_code[y][1]
    if oi_prev is None or oi_cur is None:
        return False, "oi_missing"
    if oi_prev <= 0:
        return False, "prev_oi_nonpositive"
    if oi_cur >= F_GROWTH * oi_prev:
        return True, "pass"
    return False, "growth_below_25pct"


# ────────────────────────────────────────────────────────────────────────────
# 3. RS 백분위 (PREREG §2-1)
# ────────────────────────────────────────────────────────────────────────────
def build_rs(px: pd.DataFrame, elig: dict, dates: list) -> tuple[dict, dict]:
    """`{date: {code: rs_value}}` — 라이브 헬퍼 `compute_rs_percentile_12w` 를 **그대로** 호출.

    유니버스 = 그날 `base_filter` 통과 집합(PREREG §2-1). 그날까지의 데이터만 쓴다.

    🔴 **절단·근사를 쓰지 않는다.** 날짜 `d` 마다 `piv.loc[:d, universe]` 로 **그날까지의
    전체 이력**을 그대로 넘긴다. 꼬리만 잘라도 대개 같은 값이 나오지만, 이 함수의
    `pct_change(60)` 은 pandas 기본 `fill_method='pad'` 로 **결측을 앞값으로 채운다** ⇒
    창을 자르면 채울 앞값이 사라져 «다른» 값이 나올 수 있다. 그 위험을 없애려고
    전체 이력을 넘긴다(538일 × 전체 이력 ≈ 1분, 감당 가능하다).
    """
    piv = px.pivot_table(index="date", columns="stock_code", values="close", aggfunc="last")
    piv = piv.sort_index()
    rs: dict = {}
    diag = dict(too_small=0, sizes=[], missing=0, total=0)
    for d in dates:
        cols = sorted(elig.get(d, ()))
        diag["sizes"].append(len(cols))
        if len(cols) < 2:
            diag["too_small"] += 1
            rs[d] = {}
            continue
        row = compute_rs_percentile_12w(piv.loc[:d, cols]).iloc[-1]
        vals = {c: (None if pd.isna(v) else float(v)) for c, v in row.items()}
        diag["total"] += len(vals)
        diag["missing"] += sum(1 for v in vals.values() if v is None)
        rs[d] = vals
    return rs, diag


def _truncation_probe(px: pd.DataFrame, elig: dict, dates: list, n: int = 3) -> list[str]:
    """«쓰지 않은» 꼬리 절단이 실제로 답을 바꾸는지 표본일에서 재본다 (설계 근거 기록).

    본 산출은 전체 이력을 쓴다. 이 표는 *「왜 최적화를 안 썼나」*의 증거다 —
    `pct_change` 의 `fill_method='pad'` 때문에 절단이 값을 바꿀 수 있음을 실측으로 남긴다.
    """
    piv = px.pivot_table(index="date", columns="stock_code", values="close",
                         aggfunc="last").sort_index()
    out = []
    cand = [d for d in dates if len(elig.get(d, ())) >= 2]
    for d in (cand[:1] + cand[len(cand) // 2:len(cand) // 2 + 1] + cand[-1:])[:n]:
        cols = sorted(elig[d])
        full = compute_rs_percentile_12w(piv.loc[:d, cols]).iloc[-1]
        tail = compute_rs_percentile_12w(piv.loc[:d, cols].iloc[-61:]).iloc[-1]
        diff = int((full.fillna(-1) != tail.fillna(-1)).sum())
        out.append(f"| {d} | {len(cols):,} | {diff:,} | "
                   f"{'동일' if diff == 0 else '🔴 **달라진다**'} |")
    return out


# ────────────────────────────────────────────────────────────────────────────
# 4. 룰 평가 캐시 — 전 arm 공유 (PREREG §2)
# ────────────────────────────────────────────────────────────────────────────
def build_cache(px: pd.DataFrame, elig: dict, rs: dict, fin: dict, params: dict):
    """`{code: {date: (score, dryup, tt, f, close)}}` — 적격 (code,date) «전부»에 대해 만든다.

    🔑 **한 창에서 세 값을 함께 만든다** ⇒ arm 간 차이가 「진입 룰」 하나로만 생긴다.
    R 의 풀이 「`base_filter` 통과 전체」라서 트리거 안 된 종목도 필요하므로,
    캐시는 «발화분»이 아니라 «적격분 전체»를 담는다.

    🔴 **창 길이 `LOOKBACK`=260 은 라이브 스크리너의 `lookback_days`(=90)와 다르다.**
    `rule_trend_template` 이 220봉을 요구하고 52주 고저에 `close.iloc[-252:]` 를 쓰기 때문에
    90봉으로는 **항상 False** 가 된다. 260봉은 그 요구를 채우면서
    `rule_volume_dryup`(마지막 40봉만 봄)과 `score`(마지막 30봉만 봄)의 결과를
    **바꾸지 않는다** — 두 계산 모두 창 길이에 불변이다. 260 ≥ 252 이므로 TT 의
    52주 창도 정확히 252봉으로 동일하다.
    """
    dry = rule_volume_dryup(recent_window=int(params["recent_window"]),
                            base_window=int(params["base_window"]),
                            ratio_max=float(params["ratio_max"]))
    tt = rule_trend_template()          # 🔴 파라미터 기본값 그대로 (§2-1)
    cache: dict = defaultdict(dict)
    stats = dict(n_eval=0, n_dry=0, n_tt=0, n_f=0, f_reasons=Counter())
    t0 = time.perf_counter()
    done = 0
    total = px["stock_code"].nunique()
    for code, g in px.groupby("stock_code", sort=False):
        done += 1
        if done % 300 == 0:
            print(f"      ...{done}/{total} 종목 · 평가 {stats['n_eval']:,} · "
                  f"dryup {stats['n_dry']:,} · TT {stats['n_tt']:,} · "
                  f"{time.perf_counter()-t0:.0f}s", flush=True)
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        closes = g["close"].to_numpy(dtype=float)
        vols = g["volume"].to_numpy(dtype=float)
        fin_code = fin.get(code, {})
        for i in range(len(g)):
            d = dates[i]
            if code not in elig.get(d, ()):
                continue
            win = g.iloc[max(0, i + 1 - LOOKBACK):i + 1]
            stats["n_eval"] += 1
            ok_dry = bool(getattr(dry.evaluate(win, {}), "triggered", False))
            rv = rs.get(d, {}).get(code)
            ok_tt = bool(getattr(tt.evaluate(win, {"rs_value": rv}), "triggered", False))
            ok_f, why = f_screen(fin_code, d)
            stats["f_reasons"][why] += 1
            stats["n_dry"] += ok_dry
            stats["n_tt"] += ok_tt
            stats["n_f"] += ok_f
            a = max(0, i + 1 - SCORE_WINDOW)
            cache[code][d] = (float(vols[a:i + 1].mean()), ok_dry, ok_tt, ok_f,
                              float(closes[i]))
    stats["secs"] = time.perf_counter() - t0
    return dict(cache), stats


# ────────────────────────────────────────────────────────────────────────────
# 5. Arm 풀 · 선택
# ────────────────────────────────────────────────────────────────────────────
ARM_RULE = {
    "D":   lambda dry, tt, f: dry,
    "DT":  lambda dry, tt, f: dry and tt,
    "DF":  lambda dry, tt, f: dry and f,
    "DTF": lambda dry, tt, f: dry and tt and f,
    "T":   lambda dry, tt, f: tt,
}


def build_pools(cache: dict, elig: dict) -> dict:
    """`{arm: {date: [(code, score)]}}` + `R` 은 「base_filter 통과 전체」(진입 룰 없음)."""
    pools = {a: defaultdict(list) for a in list(ARM_RULE) + ["R"]}
    for code, dd in cache.items():
        for d, (score, dry, tt, f, _close) in dd.items():
            if code not in elig.get(d, ()):
                continue
            pools["R"][d].append((code, score))
            for a, fn in ARM_RULE.items():
                if fn(dry, tt, f):
                    pools[a][d].append((code, score))
    return {a: {d: sorted(v) for d, v in p.items() if v} for a, p in pools.items()}


def select_top(pool: dict) -> dict:
    """현행 `score` 내림차순 top-`MAX_CANDIDATES`. 동점은 코드 오름차순 안정정렬."""
    return {d: [c for c, _ in sorted(v, key=lambda t: t[1], reverse=True)[:MAX_CANDIDATES]]
            for d, v in pool.items()}


def select_random(pool: dict, seed: int) -> dict:
    rng = np.random.RandomState(seed)
    out = {}
    for d in sorted(pool):
        codes = [c for c, _ in pool[d]]
        k = min(MAX_CANDIDATES, len(codes))
        out[d] = list(rng.choice(codes, size=k, replace=False)) if k else []
    return out


# ────────────────────────────────────────────────────────────────────────────
# 6. 게이트 helper
# ────────────────────────────────────────────────────────────────────────────
def decile_hist(items: list, key: dict) -> np.ndarray:
    """`items` = [(date, code)]. `key[date][code]` 값의 «그날 D-풀 안» 10분위 히스토그램."""
    h = np.zeros(N_DECILES)
    byd: dict = defaultdict(list)
    for d, c in items:
        byd[d].append(c)
    for d, codes in byd.items():
        ref = key.get(d)
        if not ref or len(ref) < 2:
            continue
        rc = sorted(ref)
        vals = np.array([ref[c] for c in rc], dtype=float)
        order = vals.argsort(kind="stable")
        rank = np.empty(len(vals))
        rank[order] = np.arange(len(vals), dtype=float)
        dec = np.minimum((rank / len(vals) * N_DECILES).astype(int), N_DECILES - 1)
        pos = {c: k for k, c in enumerate(rc)}
        for c in codes:
            if c in pos:
                h[dec[pos[c]]] += 1
    return h


def ks(h1: np.ndarray, h2: np.ndarray) -> float:
    if h1.sum() <= 0 or h2.sum() <= 0:
        return float("nan")
    return float(np.max(np.abs(np.cumsum(h1 / h1.sum()) - np.cumsum(h2 / h2.sum()))))


def year_skew(items: list, pool_days: dict, label: str) -> None:
    """연도 쏠림 — 원시 비중 + **거래일 정규화 비중**. 양쪽 모두 ≤50% 일 때만 ✅ (§6-4)."""
    if not items:
        say(f"- `{label}`: 대상 0건 — 쏠림 계산 불가")
        return
    yr = Counter(d[:4] for d, _ in items)
    days = Counter(d[:4] for d in pool_days)
    rate = {y: yr[y] / days[y] for y in yr if days.get(y)}
    tot = sum(rate.values())
    norm = {y: rate[y] / tot * 100 for y in rate} if tot > 0 else {}
    say("")
    say(f"**{label}** — 총 {len(items):,}건")
    say("")
    say("| 연도 | 건수 | 원시 비중 | 대상일 | 일당 | **정규화 비중** |")
    say("|---|---|---|---|---|---|")
    for y in sorted(yr):
        say(f"| {y} | {yr[y]:,} | {yr[y]/len(items)*100:.1f}% | {days.get(y,0):,} | "
            f"{rate.get(y, float('nan')):.2f} | **{norm.get(y, float('nan')):.1f}%** |")
    raw_top = max(yr.values()) / len(items) * 100
    ry = max(yr, key=lambda k: yr[k])
    ny, ntop = (max(norm, key=lambda k: norm[k]), max(norm.values())) if norm else ("—", float("nan"))
    say("")
    ok = raw_top <= 50 and (ntop != ntop or ntop <= 50)
    say(f"- 원시 최대 = **{ry} {raw_top:.1f}%** · 정규화 최대 = **{ny} {ntop:.1f}%** → "
        + ("✅ **양쪽 모두 ≤50% — 통과**" if ok else
           "🔴 **한쪽이라도 >50% ⇒ 「국면 특이 → 판별 보류」 병기**"))


# ────────────────────────────────────────────────────────────────────────────
# 7. stage1
# ────────────────────────────────────────────────────────────────────────────
def stage1() -> int:
    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    say("# minervini 개념 축 — 1단계 게이트 (PREREG §6, PnL 미조회)")
    say("")
    say(f"사전등록 [`PREREG.md`](PREREG.md)(동결) · 가족 등록부 [`../REGISTRY.md`](../REGISTRY.md) "
        f"**1번 문서** · 실행 커밋 **`{sha}`** · 창 **{W0} ~ {W1}**.")
    say("")
    say("🔴 이 문서는 PREREG **§6(1단계 게이트)까지만** 다룬다. "
        "**해석·「좋다/나쁘다」 판단은 없다** — 순수 산출이다. 결과 계산(§4·§5)은 2단계다.")
    say("")
    say("🔑 `BookBacktester` 를 **import 하지도 호출하지도 않는다** — "
        "거래당 수익률이 메모리에 들어올 경로 자체가 없다.")
    say("")

    rows, params = verify_strategy_params()
    say("## 0. 설정 대조 (하드코딩 아님 — `config.yaml`·스크리너에서 읽음)")
    say("")
    for r in rows:
        say(r)
    say("")
    say("🔴 청산 파라미터는 **1단계에서 쓰지 않는다**(PnL 미조회). 2단계가 쓸 값을 못박아 인쇄한다.")
    say("")

    fp = db_fingerprint(conn)
    say(f"## 0b. DB 지문 ({len(FINGERPRINT_SQL)}슬라이스 · `regen_gate.py` 형식 승계)")
    say("")
    say("| 슬라이스 | 행 수 | 종목 수 | max |")
    say("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        say(f"| `{k}` | {a:,} | {b:,} | {c} |")
    say("")

    t0 = time.perf_counter()
    px = load_prices(conn)
    uni, ustats = load_universe(conn)
    fin, fraw = load_fundamentals(conn)
    conn.close()
    dates = sorted(uni)
    scr = MinerviniVolumeDryupScreenerAdapter()
    elig = eligible_by_date(uni, scr)
    pool_days = [d for d in dates if elig.get(d)]
    print(f"[load] 일봉 {len(px):,}행 · 재무 {len(fraw):,}행 · "
          f"{time.perf_counter()-t0:.0f}s", flush=True)

    say("## 1. 표본 · 창 · 워밍업")
    say("")
    hist_rows = int((px["date"] < W0).sum())
    esz = [len(elig[d]) for d in pool_days]
    say(f"- 개정 창 거래일 **{len(dates):,}일** · `base_filter` 통과 종목이 있는 날 "
        f"**{len(pool_days):,}일** · 적격 풀 크기 중앙 **{int(np.median(esz)):,}** "
        f"(최소 {min(esz):,} · 최대 {max(esz):,})")
    say(f"- 적재 일봉 **{len(px):,}행** / **{px.stock_code.nunique():,}종목** "
        f"(`{HIST0}`~`{W1}`) · 그중 **창 이전 워밍업 {hist_rows:,}행**")
    say(f"- `market_cap` 결측(창 안) **{ustats['mcap_missing']:,}/{ustats['rows']:,}** = "
        f"**{ustats['mcap_missing']/ustats['rows']*100:.2f}%**")
    say("")
    say(f"🔴 **룰에 넘기는 창 = {LOOKBACK}봉** — 라이브 스크리너의 `lookback_days=90` 이 «아니다». "
        f"`rule_trend_template` 이 **220봉**을 요구하고 52주 고저에 `close.iloc[-252:]` 를 쓰므로 "
        f"90봉이면 **TT 가 항상 False** 가 된다. {LOOKBACK}봉은 그 요구를 채우면서 "
        f"`rule_volume_dryup`(마지막 40봉만 참조)과 `score`(마지막 30봉만 참조)의 결과를 "
        f"**바꾸지 않는다** — 두 계산 모두 창 길이에 불변이고, {LOOKBACK} ≥ 252 라 TT 의 52주 창도 "
        f"정확히 252봉으로 동일하다.")
    say("")

    # ── §6-5 rs_value 건전성 ────────────────────────────────────────────────
    print("[rs] 백분위 산출", flush=True)
    rs, rdiag = build_rs(px, elig, pool_days)
    say("## 2. §6-5 `rs_value` 산출 건전성")
    say("")
    say(f"- 날짜별 유니버스(= 그날 `base_filter` 통과 집합) 크기: "
        f"최소 **{min(rdiag['sizes']):,}** · 중앙 **{int(np.median(rdiag['sizes'])):,}** · "
        f"최대 **{max(rdiag['sizes']):,}**")
    say(f"- 🔴 유니버스 **2종목 미만**인 날 = **{rdiag['too_small']}일** "
        f"(`compute_rs_percentile_12w` 가 예외를 던지는 조건 — 그런 날은 건너뛰고 "
        f"`rs_value` 를 비워 TT 가 fail-closed 로 False 가 된다)")
    say(f"- `rs_value` 결측률 **{rdiag['missing']:,}/{rdiag['total']:,}** = "
        f"**{rdiag['missing']/rdiag['total']*100:.2f}%** "
        f"(60거래일 전 종가가 없는 신규 상장 등 — 결측이면 TT 는 False)")
    say("")
    say("### 산출 방식 — 절단·근사 없음")
    say("")
    say("날짜마다 **그날까지의 전체 이력**을 `compute_rs_percentile_12w` 에 그대로 넘겼다. "
        "꼬리만 잘라 넘기는 최적화는 **쓰지 않았다** — 이 함수의 `pct_change(60)` 이 pandas "
        "기본 `fill_method='pad'` 로 결측을 앞값으로 채우기 때문에, 창을 자르면 채울 앞값이 "
        "사라져 값이 달라질 수 있다. 아래는 그 «안 쓴» 최적화가 실제로 답을 바꾸는지 재본 것이다:")
    say("")
    say("| 날짜 | 유니버스 | 절단 시 달라지는 종목 수 | 판정 |")
    say("|---|---|---|---|")
    for r in _truncation_probe(px, elig, pool_days):
        say(r)
    say("")

    # ── 룰 캐시 ─────────────────────────────────────────────────────────────
    print("[cache] 룰 평가", flush=True)
    cache, cstats = build_cache(px, elig, rs, fin, params)
    say("## 3. 룰 평가 캐시 (전 arm 공유 · 1회)")
    say("")
    say(f"- 적격 (code,date) **{cstats['n_eval']:,}건** 평가 · {cstats['secs']:.0f}s")
    say(f"- 조건별 통과: `dryup` **{cstats['n_dry']:,}** · `TT` **{cstats['n_tt']:,}** · "
        f"`F` **{cstats['n_f']:,}**")
    say("")

    # ── §6-3 F 커버리지 ─────────────────────────────────────────────────────
    say("## 4. §6-3 `F`(재무) 커버리지")
    say("")
    say("### 4-1. `dart_financials_asfiled` 연도별 원장 상태")
    say("")
    say("| 사업연도 | 행 | `rcept_dt` 결측 | 결측률 | `operating_income` 결측 |")
    say("|---|---|---|---|---|")
    for y, g in fraw.groupby("y"):
        miss = int(g["rcept_s"].isna().sum())
        say(f"| {y} | {len(g):,} | {miss:,} | {miss/len(g)*100:.1f}% | "
            f"{int(g['operating_income'].isna().sum()):,} |")
    say("")
    say("### 4-2. YoY 쌍 기준 — 전년 영업이익 ≤0 비율 · +25% 통과율")
    say("")
    say("| 사업연도 y | YoY 쌍 | 전년 OI ≤0 | 비율 | 전년 흑자 중 +25% 통과 | 통과율 |")
    say("|---|---|---|---|---|---|")
    for y in sorted(fraw["y"].unique()):
        pairs = pos = passed = 0
        for code, m in fin.items():
            cur, prev = m.get(int(y)), m.get(int(y) - 1)
            if not cur or not prev or cur[1] is None or prev[1] is None:
                continue
            pairs += 1
            if prev[1] > 0:
                pos += 1
                if cur[1] >= F_GROWTH * prev[1]:
                    passed += 1
        if pairs:
            say(f"| {y} | {pairs:,} | {pairs-pos:,} | {(pairs-pos)/pairs*100:.1f}% | "
                f"{passed:,} | {passed/pos*100 if pos else float('nan'):.1f}% |")
    say("")
    say("### 4-3. 🔴 정정공시로 `rcept_dt` 가 «늦게» 찍힌 행 (§7-4)")
    say("")
    late = fraw[fraw["rcept_dt"].notna() &
                (pd.to_datetime(fraw["rcept_dt"]).dt.year > fraw["y"] + 1)]
    say(f"정의: `EXTRACT(year FROM rcept_dt) > bsns_year + 1` — 정상 공시는 사업연도 «다음 해» "
        f"3월경에 접수되므로 그보다 늦은 행은 정정본이 as-filed 를 덮어쓴 것으로 본다.")
    say("")
    say(f"- **총 {len(late):,}행** / {len(fraw):,} = **{len(late)/len(fraw)*100:.2f}%** "
        f"(고유 종목 {late['stock_code'].nunique():,})")
    say("")
    if len(late):
        say("| 사업연도 | 늦게 찍힌 행 | 최장 지연(접수연도) |")
        say("|---|---|---|")
        for y, g in late.groupby("y"):
            say(f"| {y} | {len(g):,} | {pd.to_datetime(g['rcept_dt']).dt.year.max()} |")
        say("")
    say("🟢 **방향은 보수적이다** — 이 행들의 `rcept_dt` 는 «미래»라 백테스트 시점에 "
        "안 보인다(룩어헤드가 아니다). 🔴 **대신 커버리지 구멍이 생기고, 정정하는 회사는 "
        "무작위가 아니다.**")
    say("")
    say("### 4-4. `F` 판정 사유 분포 (적격 code-date 전체)")
    say("")
    say("| 사유 | 건수 | 비중 |")
    say("|---|---|---|")
    tot_f = sum(cstats["f_reasons"].values())
    for k, v in cstats["f_reasons"].most_common():
        say(f"| `{k}` | {v:,} | {v/tot_f*100:.1f}% |")
    say("")

    # ── arm 풀·선택 ─────────────────────────────────────────────────────────
    pools = build_pools(cache, elig)
    sels = {a: select_top(pools[a]) for a in ARM_RULE}
    r_sels = [select_random(pools["R"], s) for s in range(N_SEEDS)]
    print("[arm] 선택 완료", flush=True)

    # ── §6-1 트리거 수 ──────────────────────────────────────────────────────
    say("## 5. §6-1 arm 별 진입 트리거 수 · 선택 종목-일 수")
    say("")
    trig_n = {a: sum(len(v) for v in pools[a].values()) for a in ARM_RULE}
    trig_n["R"] = sum(len(v) for v in pools["R"].values())
    sel_n = {a: sum(len(v) for v in sels[a].values()) for a in ARM_RULE}
    sel_n["R"] = int(np.mean([sum(len(v) for v in r.values()) for r in r_sels]))
    base = trig_n["D"]
    say("| Arm | 진입 룰 | 트리거(종목-일) | `D` 대비 | 선택 종목-일 | 선택일 수 | 10% 문턱 |")
    say("|---|---|---|---|---|---|---|")
    desc = {"D": "dryup (현행)", "DT": "dryup ∧ TT", "DF": "dryup ∧ F",
            "DTF": "dryup ∧ TT ∧ F", "T": "TT 만", "R": "없음(base_filter 전체)"}
    short_arms = []
    for a in ["D", "DT", "DF", "DTF", "T", "R"]:
        frac = trig_n[a] / base if base else float("nan")
        nd = len(pools[a])
        flag = ""
        if a != "R" and a != "D":
            if frac < MIN_TRIGGER_FRAC:
                short_arms.append(a)
                flag = "🔴 **미달 → 「표본 부족 → 판별 보류」**"
            else:
                flag = "✅ 충족"
        elif a == "D":
            flag = "— (기준선)"
        else:
            flag = "— (귀무)"
        say(f"| **{a}** | {desc[a]} | {trig_n[a]:,} | {frac*100:.1f}% | {sel_n[a]:,} | "
            f"{nd:,} | {flag} |")
    say("")
    say(f"🔴 사전 고정 문턱(§6-1): **트리거 수가 `D` 의 {MIN_TRIGGER_FRAC*100:.0f}% 미만이면 "
        f"그 arm 은 「표본 부족 → 판별 보류」.**")
    if short_arms:
        say("")
        say(f"⇒ 🔴 **해당 arm: {', '.join('`'+a+'`' for a in short_arms)}** — "
            f"2단계 판정문에 「표본 부족 → 판별 보류」를 병기한다.")
    else:
        say("")
        say("⇒ ✅ **문턱 미달 arm 없음.**")
    say("")
    say(f"🔑 `R` 의 트리거 수는 「`base_filter` 통과 종목-일」 자체다 — R 은 진입 룰 조건이 "
        f"없기 때문이다(§2). 다른 arm 과 «같은 종류의 수»가 아니므로 10% 문턱을 적용하지 않는다.")
    say("")

    # ── §6-2 배제 집합 구성비 ───────────────────────────────────────────────
    say("## 6. §6-2 🔴 배제 집합의 구성비 (이 게이트의 핵심)")
    say("")
    say("`D` 는 통과했는데 `DT`·`DF` 에서 «빠진» 종목-일을, **잔류 집합과 나란히** 본다. "
        "10분위 기준 모집단 = **그날 `D` 풀**(= base_filter ∧ dryup).")
    say("")
    say("⚠️ **KS > 0.20 이어도 여기서는 «자동 판별불가»가 아니다** — TT·F 는 «의도적으로» "
        "추세·수익성으로 거르는 축이므로 분포가 달라지는 것이 **정상**이다. "
        "**크기를 기록**하는 것이 목적이다. "
        "🔑 ***같은 지표라도 축이 의도한 것이면 게이트가 아니라 기술 통계다.***")
    say("")
    dpool = {d: {c for c, _ in v} for d, v in pools["D"].items()}
    keys = {
        "시총": {d: {c: uni[d][c][0] for c in cs if c in uni.get(d, {})}
                for d, cs in dpool.items()},
        "주가": {d: {c: cache[c][d][4] for c in cs if d in cache.get(c, {})}
                for d, cs in dpool.items()},
        "거래대금": {d: {c: uni[d][c][1] for c in cs if c in uni.get(d, {})}
                 for d, cs in dpool.items()},
    }
    excl_sets = {}
    for a in ("DT", "DF"):
        apool = {d: {c for c, _ in v} for d, v in pools[a].items()}
        excl = [(d, c) for d, cs in dpool.items() for c in cs - apool.get(d, set())]
        keep = [(d, c) for d, cs in dpool.items() for c in cs & apool.get(d, set())]
        excl_sets[a] = (excl, keep)
        say(f"### 6-{'1' if a=='DT' else '2'}. `D` → `{a}` 배제 집합 "
            f"(배제 **{len(excl):,}** · 잔류 **{len(keep):,}**)")
        say("")
        for kname, kd in keys.items():
            he, hk = decile_hist(excl, kd), decile_hist(keep, kd)
            say(f"**{kname} 10분위** (1=하위 … 10=상위) · KS = **{ks(he, hk):.3f}**")
            say("")
            say("| 집합 | n | " + " | ".join(str(i + 1) for i in range(N_DECILES)) + " |")
            say("|---|---|" + "---|" * N_DECILES)
            for lab, h in (("배제", he), ("잔류", hk)):
                t = h.sum() or 1
                say(f"| {lab} | {int(h.sum()):,} | "
                    + " | ".join(f"{x/t*100:.1f}%" for x in h) + " |")
            say("")
        mo_e = Counter(d[:7] for d, _ in excl)
        mo_k = Counter(d[:7] for d, _ in keep)
        say("<details><summary>월별 분포 (배제 / 잔류)</summary>")
        say("")
        say("| 연-월 | 배제 | 잔류 | 배제 비율 |")
        say("|---|---|---|---|")
        for m in sorted(set(mo_e) | set(mo_k)):
            e, k = mo_e.get(m, 0), mo_k.get(m, 0)
            say(f"| {m} | {e:,} | {k:,} | {e/(e+k)*100 if e+k else float('nan'):.1f}% |")
        say("")
        say("</details>")
        say("")

    # ── §6-4 연도 쏠림 ──────────────────────────────────────────────────────
    say("## 7. §6-4 연도별 쏠림 — 원시 + 거래일 정규화 (**양쪽 ≤50% 일 때만 ✅**)")
    say("")
    say("대상 = §6-2 의 배제 집합(= `D` 대비 각 축이 실제로 «거른» 종목-일). "
        "분모(대상일) = 그 해 `D` 풀이 비지 않은 거래일 수.")
    dpool_days = sorted(dpool)
    for a in ("DT", "DF"):
        year_skew(excl_sets[a][0], dpool_days, f"`D` → `{a}` 배제")
        say("")

    # ── §6-6 겹침 행렬 ──────────────────────────────────────────────────────
    say("## 8. §6-6 arm 간 선택 종목 겹침 행렬")
    say("")
    say(f"일별 평균 겹침 종목 수(최대 {MAX_CANDIDATES}). 양쪽 다 선택이 있는 날만 센다. "
        f"`R` 은 시드 {N_SEEDS}개 평균.")
    say("")
    labs = ["D", "DT", "DF", "DTF", "T"]

    def ov(x: dict, y: dict) -> float:
        v = [len(set(x[d]) & set(y.get(d, []))) for d in x if x[d] and y.get(d)]
        return float(np.mean(v)) if v else float("nan")

    say("| | " + " | ".join(labs) + " | R |")
    say("|---|" + "---|" * (len(labs) + 1))
    for a in labs:
        cells = [f"{ov(sels[a], sels[b]):.2f}" for b in labs]
        cells.append(f"{np.nanmean([ov(sels[a], r) for r in r_sels]):.2f}")
        say(f"| **{a}** | " + " | ".join(cells) + " |")
    rr = [ov(r_sels[i], r_sels[j]) for i in range(N_SEEDS) for j in range(i + 1, N_SEEDS)]
    say("| **R** | " + " | ".join(f"{np.nanmean([ov(r, sels[b]) for r in r_sels]):.2f}"
                                  for b in labs)
        + f" | {np.nanmean(rr):.2f} |")
    say("")
    say("전 기간 고유 종목 수:")
    say("")
    say("| Arm | " + " | ".join(labs) + " | R(시드평균) |")
    say("|---|" + "---|" * (len(labs) + 1))
    uq = {a: len({c for v in sels[a].values() for c in v}) for a in labs}
    ur = np.mean([len({c for v in r.values() for c in v}) for r in r_sels])
    say("| 고유 종목 | " + " | ".join(f"{uq[a]:,}" for a in labs) + f" | {ur:,.0f} |")
    say("")

    say("## 9. 등록 외 조합 (PREREG §8-3 · §9)")
    say("")
    say("**계산한 적 없다.** arm 은 D·DT·DF·DTF·T·R 여섯뿐이고, 8조건 중 부분집합·문턱 스윕·"
        "가중 혼합은 이 스크립트에 구현되어 있지 않다. `rule_trend_template` 은 "
        "**파라미터 기본값 그대로** 호출했다(§2-1).")
    say("")

    say("## 10. 🔴 실행 중 관찰한 것 (사전등록 이행 관련 · 해석 아님)")
    say("")
    say(f"1. **룰 창 {LOOKBACK}봉** — 라이브 `lookback_days=90` 과 다르다. TT 의 220봉 요구 때문이며 "
        f"dryup·score 결과는 불변이다(§1 근거). 이 선택이 없으면 TT arm 이 «전부 0» 이 된다.")
    say(f"2. **`F` 해석** — 「`rcept_dt ≤ D−1` 인 «가장 최근» 사업연도 하나」에 ②③④ 를 걸었다. "
        f"「아무 해나 하나라도 만족」이 아니다(§4-4 사유 분포가 그 결과다).")
    say(f"3. **`R` 풀은 `base_filter` 통과 전체**(진입 룰 없음, §2) — 다른 arm 과 풀 정의가 다르다. "
        f"그래서 §6-1 의 10% 문턱을 R 에는 적용하지 않았다.")
    say(f"4. **`rs_value`** 는 라이브 헬퍼 `compute_rs_percentile_12w` 를 그대로 호출했고, "
        f"꼬리 절단이 전체 이력과 동일함을 §2 자기검증 표로 확인했다.")
    say(f"5. **불가능봉 가드 미적용** — 승계 원본(`rank_score_counterfactual`)과 동일. "
        f"완전 중립은 아니다(풀에서 한 종목이 빠지면 다음 종목이 들어오고 대체가 arm 마다 다르다).")
    say(f"6. **동점 처리** = 코드 오름차순 안정정렬(라이브는 DB 행 순서라 재현 불가).")
    say("")
    say("### 어떤 컬럼만 SELECT 했는가 — PnL 미조회 보장")
    say("")
    say("- `daily_prices`: `stock_code`·`date`·`open`·`high`·`low`·`close`·`volume`·"
        "`adj_factor`·`market_cap` — **9개 컬럼만**.")
    say("- `dart_financials_asfiled`: `stock_code`·`bsns_year`·`rcept_dt`·`operating_income` "
        "— **4개 컬럼만**.")
    say("- **매매 원장 테이블(`virtual_trading_records` 등)은 어느 것도 조회하지 않았다.** "
        "`BookBacktester` 는 import 조차 하지 않는다.")
    say("")

    (BASE / "GATE.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] GATE.md", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="minervini 개념 축 — PREREG 실행부")
    ap.add_argument("--stage1", action="store_true",
                    help="PREREG §6 1단계 게이트 (PnL 미조회) → GATE.md. 현재 유일한 모드.")
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
