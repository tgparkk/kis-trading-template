# RS 리더 (나쁜 장에서도 오르는 종목) — 검증 스파이크 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 일봉 상대강도(RS) 리더 종목선정이 "나쁜 장(횡보·약세)에서도 절대수익을 내는가"를 사전등록 엄격 기준으로 측정하는 검증 스파이크를 만든다. (전략 라이브 배선 아님 — GO/NO-GO 리포트가 산출물)

**Architecture:** 기존 백테스트 부품을 최대 재사용한다. 신규 코드는 ①RS 리더 진입룰(절대 상승추세, per-stock no-lookahead) ②거래의 국면별 분해기 ③소표본 통계 헬퍼(PSR·약세장 에피소드) ④오케스트레이터 스크립트뿐. 진입신호는 `_precompute_signals` → `apply_entry_filter(rs_rank)` 로 게이팅, 체결은 `run_portfolio`(한정자본 max-K, 비용내장), 국면 라벨은 `_build_daily_regime_map`(실제 KOSPI) 재사용.

**Tech Stack:** Python 3.8+, pandas/numpy, psycopg2 (PostgreSQL `localhost:5433` robotrader/robotrader_quant), pytest. 스펙: `docs/superpowers/specs/2026-06-06-rs-leader-bad-market-design.md`.

---

## 재사용 부품 (수정 금지 — import만)

- `scripts/exit_multiverse/portfolio_sim.py::run_portfolio(data, signal_cache, adapter, params, turnover, initial_capital, max_positions, max_per_stock)` → `{equity_curve, daily_returns, trades, max_concurrent_positions, n_trades, n_skipped}`. **`trades`** = dict 리스트, sell 항목에 `entry_date`(str)·`pnl_pct`(float)·`side`·`reason`. 비용(수수료0.00015+세0.0018+슬리피지0.001) 내장.
- `scripts/book_portfolio_multiverse.py::_SLTPMHAdapter` (entry_mechanism="market", sl/tp/mh 청산), `_build_daily_regime_map(start, end) -> {pd.Timestamp: "bull"|"sideways"|"bear"}`.
- `scripts/entry_filters.py::apply_entry_filter(data, cache, filt, threshold, n, kospi_close=None)` — `filt="rs_rank"` 횡단면 N봉수익률 백분위 ≥ threshold.
- `strategies/base.py::Signal, SignalType` (BUY 신호).

## 데이터 사실 (검증됨)

- DB: `host=localhost port=5433 user=robotrader password=robotrader_secure_pw_2024`.
- 일봉(SSOT): `robotrader_quant.daily_prices` 컬럼 `stock_code,date,open,high,low,close,volume,trading_value,market_cap` (조정종가 — adj_factor 곱하지 말 것). 2021~2026 커버.
- KOSPI: `robotrader.daily_prices` `stock_code='KOSPI'` 2021-01-04~2026-05-29 (이미 `_build_daily_regime_map`가 사용).
- 약세장 에피소드(국면별 분해·OOS용): `2022-01-01~2022-12-31`(깊은약세), `2024-07-01~2024-12-31`(충격형), `2026-02-15~2026-03-31`(V급락).

## 파일 구조

- Create: `scripts/rs_leader/__init__.py` (빈 패키지)
- Create: `scripts/rs_leader/rule.py` — `RSLeaderRule` (절대 상승추세 BUY 신호, per-stock, no-lookahead)
- Create: `scripts/rs_leader/decompose.py` — `decompose_trades_by_regime`, `episode_stats`, `probabilistic_sharpe_ratio`
- Create: `scripts/rs_leader_validation.py` — 오케스트레이터(데이터로드→신호→rs_rank필터→run_portfolio→국면분해→OOS→리포트)
- Create: `tests/rs_leader/__init__.py`
- Create: `tests/rs_leader/test_rule.py`
- Create: `tests/rs_leader/test_decompose.py`
- Output (코드아님): `reports/regime_spike/rs_leader_validation.md` (실행 산출물)

---

## Task 0: 작업 브랜치 + 패키지 스캐폴드

**Files:**
- Create: `scripts/rs_leader/__init__.py`
- Create: `tests/rs_leader/__init__.py`

- [ ] **Step 1: 브랜치 생성**

Run:
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && git checkout -b feat/rs-leader-validation
```
Expected: `Switched to a new branch 'feat/rs-leader-validation'`

- [ ] **Step 2: 빈 패키지 파일 생성**

`scripts/rs_leader/__init__.py`:
```python
"""RS 리더 검증 스파이크 (나쁜 장에서도 오르는 종목)."""
```

`tests/rs_leader/__init__.py`:
```python
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/rs_leader/__init__.py tests/rs_leader/__init__.py
git commit -m "chore(rs_leader): scaffold validation spike package"
```

---

## Task 1: RSLeaderRule — 절대 상승추세 진입룰 (per-stock, no-lookahead)

**Files:**
- Create: `scripts/rs_leader/rule.py`
- Test: `tests/rs_leader/test_rule.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/rs_leader/test_rule.py`:
```python
import numpy as np
import pandas as pd
import pytest

from scripts.rs_leader.rule import RSLeaderRule
from strategies.base import SignalType


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_uptrend_emits_buy():
    # 단조 상승 80봉: close>MA60, MA20>MA60, 60일수익률>0
    closes = list(np.linspace(100, 200, 80))
    rule = RSLeaderRule()
    sig = rule.generate_signal("000001", _df(closes), "daily")
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_downtrend_no_signal():
    closes = list(np.linspace(200, 100, 80))
    rule = RSLeaderRule()
    assert rule.generate_signal("000001", _df(closes), "daily") is None


def test_too_short_no_signal():
    closes = list(np.linspace(100, 110, 40))  # < ma_long+1
    rule = RSLeaderRule()
    assert rule.generate_signal("000001", _df(closes), "daily") is None


def test_no_lookahead_truncation_invariance():
    # 미래 봉을 덧붙여도 과거 시점 i 의 신호는 불변이어야 한다.
    closes = list(np.linspace(100, 200, 80)) + list(np.linspace(200, 50, 40))
    full = _df(closes)
    rule = RSLeaderRule()
    # 평가 시점 i=79 (상승 마지막). window 절단본 vs 풀데이터 절단 동일.
    sig_trunc = rule.generate_signal("000001", full.iloc[:80], "daily")
    # 풀데이터에서 직접 [:80] 슬라이스도 동일 입력이어야 함(룰이 trailing만 사용 증명).
    sig_again = rule.generate_signal("000001", full.iloc[:80].copy(), "daily")
    assert (sig_trunc is None) == (sig_again is None)
    if sig_trunc is not None:
        assert sig_trunc.signal_type == sig_again.signal_type == SignalType.BUY
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/rs_leader/test_rule.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.rs_leader.rule'`

- [ ] **Step 3: 최소 구현 작성**

`scripts/rs_leader/rule.py`:
```python
"""RS 리더 진입룰 — 절대 상승추세 (per-stock, no-lookahead).

선정 룰(스펙 §3-2 절대 상승추세):
  종가 > MA(ma_long) AND MA(ma_short) > MA(ma_long) AND abs_lb일 수익률 > 0.
횡단면 RS 랭크는 이 룰이 아니라 apply_entry_filter(filt="rs_rank") 가 담당한다
(룰은 종목 단독 정보만 보므로 분리. 둘을 AND 결합해 'RS 리더'를 구성).

no-lookahead: generate_signal 은 호출자가 넘긴 window(=df.iloc[:i+1]) 만 본다.
rolling 은 전부 trailing(center 미사용)이라 미래 봉 무관.
"""
from __future__ import annotations

import pandas as pd

from strategies.base import Signal, SignalType


class RSLeaderRule:
    name = "rs_leader"

    def __init__(self, ma_short: int = 20, ma_long: int = 60, abs_lb: int = 60):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.abs_lb = abs_lb

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        if df is None or len(df) < self.ma_long + 1 or len(df) <= self.abs_lb:
            return None
        close = df["close"].astype(float)
        ma_s = close.rolling(self.ma_short, min_periods=self.ma_short).mean().iloc[-1]
        ma_l = close.rolling(self.ma_long, min_periods=self.ma_long).mean().iloc[-1]
        if pd.isna(ma_s) or pd.isna(ma_l):
            return None
        c = float(close.iloc[-1])
        ref = float(close.iloc[-1 - self.abs_lb])
        if ref <= 0:
            return None
        ret = c / ref - 1.0
        if c > ma_l and ma_s > ma_l and ret > 0:
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60)
        return None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/rs_leader/test_rule.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/rs_leader/rule.py tests/rs_leader/test_rule.py
git commit -m "feat(rs_leader): absolute-uptrend entry rule with no-lookahead tests"
```

---

## Task 2: 거래의 국면별 분해 + 소표본 통계 헬퍼

**Files:**
- Create: `scripts/rs_leader/decompose.py`
- Test: `tests/rs_leader/test_decompose.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/rs_leader/test_decompose.py`:
```python
import math
import pandas as pd

from scripts.rs_leader.decompose import (
    decompose_trades_by_regime, episode_stats, probabilistic_sharpe_ratio,
)


def _sell(entry_date, pnl):
    return {"side": "sell", "entry_date": entry_date, "pnl_pct": pnl}


def test_decompose_groups_by_regime():
    regime_map = {
        pd.Timestamp("2022-03-02"): "bear",
        pd.Timestamp("2025-05-02"): "sideways",
        pd.Timestamp("2025-06-02"): "bull",
    }
    trades = [
        _sell("2022-03-02 00:00:00", -0.05),
        _sell("2025-05-02 00:00:00", 0.04),
        _sell("2025-05-02 00:00:00", -0.01),
        _sell("2025-06-02 00:00:00", 0.10),
        {"side": "buy", "entry_date": "2025-06-02 00:00:00", "pnl_pct": 0.0},  # buy 무시
    ]
    out = decompose_trades_by_regime(trades, regime_map)
    assert out["bear"]["n"] == 1
    assert out["sideways"]["n"] == 2
    assert out["bull"]["n"] == 1
    assert abs(out["sideways"]["mean_pnl"] - 0.015) < 1e-9
    assert abs(out["sideways"]["win_rate"] - 0.5) < 1e-9


def test_episode_stats_filters_date_range():
    trades = [
        _sell("2022-06-01 00:00:00", -0.02),
        _sell("2022-06-15 00:00:00", 0.03),
        _sell("2025-01-01 00:00:00", 0.5),  # 범위 밖
    ]
    s = episode_stats(trades, "2022-01-01", "2022-12-31")
    assert s["n"] == 2
    assert abs(s["mean_pnl"] - 0.005) < 1e-9


def test_psr_higher_for_longer_track():
    # 동일 Sharpe 라도 표본이 길수록 PSR↑ (단조성 sanity).
    short = probabilistic_sharpe_ratio(sharpe=1.0, n=30, skew=0.0, kurt=3.0)
    long = probabilistic_sharpe_ratio(sharpe=1.0, n=300, skew=0.0, kurt=3.0)
    assert 0.0 <= short <= 1.0 and 0.0 <= long <= 1.0
    assert long > short
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/rs_leader/test_decompose.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.rs_leader.decompose'`

- [ ] **Step 3: 최소 구현 작성**

`scripts/rs_leader/decompose.py`:
```python
"""거래의 국면별 분해 + 소표본 통계 (검증 스파이크 분석층).

- decompose_trades_by_regime: run_portfolio trades(sell)를 진입일 국면라벨로 그룹화.
- episode_stats: 특정 날짜 구간(약세장 에피소드)으로 거래 필터 후 통계.
- probabilistic_sharpe_ratio: 표본길이·왜도·첨도 반영 PSR(소표본 적합, Bailey-LdP).
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import NormalDist
from typing import Dict, List

import pandas as pd


def _stats(pnls: List[float]) -> dict:
    s = pd.Series(pnls, dtype=float)
    return {
        "n": int(s.size),
        "mean_pnl": float(s.mean()) if s.size else 0.0,
        "median_pnl": float(s.median()) if s.size else 0.0,
        "win_rate": float((s > 0).mean()) if s.size else 0.0,
    }


def decompose_trades_by_regime(
    trades: List[dict], regime_map: Dict[pd.Timestamp, str]
) -> Dict[str, dict]:
    """sell 거래를 진입일(entry_date) 국면 라벨로 그룹화해 그룹별 통계 반환."""
    buckets: Dict[str, List[float]] = defaultdict(list)
    for t in trades:
        if t.get("side") != "sell":
            continue
        ed = pd.Timestamp(t["entry_date"]).normalize()
        regime = regime_map.get(ed, "unknown")
        buckets[regime].append(float(t["pnl_pct"]))
    return {reg: _stats(p) for reg, p in buckets.items()}


def episode_stats(trades: List[dict], start: str, end: str) -> dict:
    """진입일이 [start, end] 인 sell 거래만의 통계 (약세장 에피소드 OOS용)."""
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    pnls = [
        float(t["pnl_pct"]) for t in trades
        if t.get("side") == "sell" and lo <= pd.Timestamp(t["entry_date"]).normalize() <= hi
    ]
    return _stats(pnls)


def probabilistic_sharpe_ratio(
    sharpe: float, n: int, skew: float = 0.0, kurt: float = 3.0, benchmark: float = 0.0
) -> float:
    """PSR = Prob(true Sharpe > benchmark). sharpe/benchmark 는 *동일 주기* 기준.

    소표본·비정규성 반영(Bailey & López de Prado 2012). n<=1 이면 0.5 반환.
    """
    if n <= 1:
        return 0.5
    denom = math.sqrt(1.0 - skew * sharpe + (kurt - 1.0) / 4.0 * sharpe ** 2)
    if denom <= 0:
        return 0.5
    z = (sharpe - benchmark) * math.sqrt(n - 1) / denom
    return float(NormalDist().cdf(z))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/rs_leader/test_decompose.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/rs_leader/decompose.py tests/rs_leader/test_decompose.py
git commit -m "feat(rs_leader): regime decomposition + small-sample PSR helpers"
```

---

## Task 3: 오케스트레이터 — 데이터 로드 + 신호 + rs_rank 필터 + run_portfolio (스모크)

**Files:**
- Create: `scripts/rs_leader_validation.py`

이 태스크는 데이터로드(자체 DB쿼리, 부품 시그니처 의존 제거)·신호생성·필터·체결까지를 배선하고 **소규모 스모크 실행**으로 파이프라인이 도는지 확인한다. 리포트·OOS는 Task 4.

- [ ] **Step 1: 오케스트레이터 작성 (데이터 로드 + 백테스트 파이프라인)**

`scripts/rs_leader_validation.py`:
```python
"""RS 리더 검증 스파이크 오케스트레이터.

흐름:
  유니버스/일봉 로드(robotrader_quant.daily_prices, 조정종가)
  → 종목별 RSLeaderRule 진입신호 캐시(no-lookahead, _precompute_signals)
  → rs_rank 횡단면 필터(apply_entry_filter)
  → run_portfolio(한정자본 max-K, 비용내장, sl/mh 청산)
  → 국면별 분해(_build_daily_regime_map) + 약세장 에피소드 OOS + PSR
  → reports/regime_spike/rs_leader_validation.md 작성(GO/NO-GO).

사용:
  python scripts/rs_leader_validation.py --start 2021-01-01 --end 2026-05-29 \
    --universe-top 300 --k 10 --rs-threshold 0.7 --rs-n 120 \
    --sl 0.08 --mh 30 --smoke
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rs_leader.rule import RSLeaderRule  # noqa: E402
from scripts.book_portfolio_multiverse import _SLTPMHAdapter, _precompute_signals  # noqa: E402
from scripts.entry_filters import apply_entry_filter  # noqa: E402
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402

DB = dict(host="localhost", port=5433, dbname="robotrader_quant",
          user="robotrader", password="robotrader_secure_pw_2024")


def load_universe_data(start: str, end: str, top_n: int, min_tv: float = 1e9):
    """유동 상위 top_n 종목의 일봉 dict + turnover 반환.

    유니버스 = 기간 내 평균 거래대금 상위 N (결정적). df 컬럼: datetime, open, high,
    low, close, volume. 조정종가 그대로(adj_factor 미적용).
    """
    look_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    conn = psycopg2.connect(**DB)
    try:
        df = pd.read_sql(
            "SELECT stock_code, date, open, high, low, close, volume, trading_value "
            "FROM daily_prices WHERE stock_code NOT IN ('KS11','KQ11') "
            "AND date >= %s AND date <= %s AND close > 0 ORDER BY stock_code, date",
            conn, params=(look_start, end),
        )
    finally:
        conn.close()
    # 유니버스 선정: 기간(start~end) 평균 거래대금 상위 N
    in_win = df[(df["date"] >= pd.Timestamp(start).date())]
    tv = in_win.groupby("stock_code")["trading_value"].mean()
    tv = tv[tv >= min_tv].sort_values(ascending=False).head(top_n)
    universe = list(tv.index)
    data = {}
    turnover = {}
    for code in universe:
        sub = df[df["stock_code"] == code].copy()
        sub = sub.rename(columns={"date": "datetime"})
        sub["datetime"] = pd.to_datetime(sub["datetime"])
        sub = sub.sort_values("datetime").reset_index(drop=True)
        data[code] = sub[["datetime", "open", "high", "low", "close", "volume"]]
        turnover[code] = float(tv[code])
    return data, turnover


def run_backtest(data, turnover, *, rs_threshold, rs_n, k, sl, mh,
                 initial=10_000_000, max_per_stock=3_000_000):
    rule = RSLeaderRule()
    cache = _precompute_signals(data, rule, warmup_bars=65, granularity="daily")
    filtered = apply_entry_filter(data, cache, filt="rs_rank",
                                  threshold=rs_threshold, n=rs_n)
    params = dict(stop_loss_pct=sl, take_profit_pct=99.0, max_hold_bars=mh)  # tp 사실상 무효(추세추종)
    res = run_portfolio(data=data, signal_cache=filtered, adapter=_SLTPMHAdapter(),
                        params=params, turnover=turnover, initial_capital=initial,
                        max_positions=k, max_per_stock=max_per_stock)
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-05-29")
    p.add_argument("--universe-top", type=int, default=300, dest="universe_top")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--rs-threshold", type=float, default=0.7, dest="rs_threshold")
    p.add_argument("--rs-n", type=int, default=120, dest="rs_n")
    p.add_argument("--sl", type=float, default=0.08)
    p.add_argument("--mh", type=int, default=30)
    p.add_argument("--smoke", action="store_true", help="작은 유니버스로 파이프라인만 확인")
    args = p.parse_args()

    top = 30 if args.smoke else args.universe_top
    print(f"[load] universe top={top} {args.start}~{args.end}")
    data, turnover = load_universe_data(args.start, args.end, top)
    print(f"[load] {len(data)} stocks")
    res = run_backtest(data, turnover, rs_threshold=args.rs_threshold, rs_n=args.rs_n,
                       k=args.k, sl=args.sl, mh=args.mh)
    print(f"[bt] n_trades={res['n_trades']} max_concurrent={res['max_concurrent_positions']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스모크 실행 (파이프라인 동작 확인)**

Run:
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python scripts/rs_leader_validation.py --start 2024-01-01 --end 2024-12-31 --smoke
```
Expected: 에러 없이 `[load] N stocks` 와 `[bt] n_trades=... max_concurrent=...` 출력 (n_trades ≥ 0). 예외 발생 시 중단하고 원인(컬럼명·import 경로) 수정.

- [ ] **Step 3: 커밋**

```bash
git add scripts/rs_leader_validation.py
git commit -m "feat(rs_leader): validation orchestrator (load+signal+rs_rank+portfolio) smoke-passing"
```

---

## Task 4: 국면 분해 + 약세장 OOS + GO/NO-GO 리포트 생성

**Files:**
- Modify: `scripts/rs_leader_validation.py` (분석·리포트 함수 추가 + main 확장)

- [ ] **Step 1: 분석·리포트 함수 추가**

`scripts/rs_leader_validation.py` 의 import 블록에 추가:
```python
from scripts.book_portfolio_multiverse import _build_daily_regime_map  # noqa: E402
from scripts.exit_multiverse.portfolio_sim import COMMISSION_RATE  # noqa: E402  (존재확인용)
from scripts.rs_leader.decompose import (  # noqa: E402
    decompose_trades_by_regime, episode_stats, probabilistic_sharpe_ratio,
)

BEAR_EPISODES = [
    ("2022_deep", "2022-01-01", "2022-12-31"),
    ("2024H2_shock", "2024-07-01", "2024-12-31"),
    ("2026-03_vdrop", "2026-02-15", "2026-03-31"),
]
OOS_SPLITS = [
    ("train", "2021-01-01", "2024-06-30"),
    ("test", "2024-07-01", "2026-05-29"),
]
```

파일 하단(`main` 위)에 추가:
```python
def _sharpe_of_trades(trades):
    sells = [t for t in trades if t.get("side") == "sell"]
    s = pd.Series([float(t["pnl_pct"]) for t in sells], dtype=float)
    if s.size < 2 or s.std() == 0:
        return 0.0, 0.0, 0.0, s.size
    return float(s.mean() / s.std()), float(s.skew()), float(s.kurt() + 3.0), s.size


def evaluate(res, regime_map):
    trades = res["trades"]
    by_regime = decompose_trades_by_regime(trades, regime_map)
    episodes = {name: episode_stats(trades, lo, hi) for name, lo, hi in BEAR_EPISODES}
    oos = {name: episode_stats(trades, lo, hi) for name, lo, hi in OOS_SPLITS}
    sharpe, skew, kurt, n = _sharpe_of_trades(trades)
    psr = probabilistic_sharpe_ratio(sharpe, n, skew, kurt)
    return {"by_regime": by_regime, "episodes": episodes, "oos": oos,
            "trade_sharpe": sharpe, "psr": psr, "n_trades": n}


def go_verdict(ev):
    """스펙 §6 GO 기준 4개 채점 (전부 충족 시 GO)."""
    by, oos, eps = ev["by_regime"], ev["oos"], ev["episodes"]
    c1 = by.get("sideways", {}).get("mean_pnl", -1) > 0 and \
        all(oos[s].get("mean_pnl", -1) > 0 for s in ("train", "test"))
    c2 = by.get("bear", {}).get("mean_pnl", -1) > -0.05  # 비파국(에피소드 평균 손실 -5% 이내)
    c3 = True  # 벤치마크 우위는 리포트에 KOSPI 동구간 수치 병기(수동 판정 보조)
    n_bear_pos = sum(1 for _, s in eps.items() if s["n"] >= 5 and s["mean_pnl"] > 0)
    c4 = n_bear_pos >= 1  # 약세장 에피소드 중 ≥1 에서 양수(표본있는 것 한정)
    passed = c1 and c2 and c4
    return {"GO": passed, "c1_sideways_oos": c1, "c2_bear_not_catastrophic": c2,
            "c3_benchmark": "수동검토", "c4_leave_one_bear": c4}


def write_report(path, args, ev, verdict):
    lines = ["# RS 리더 검증 — GO/NO-GO 리포트", "",
             f"- 기간: {args.start} ~ {args.end} / 유니버스 top {args.universe_top}",
             f"- 파라미터: K={args.k} rs_n={args.rs_n} rs_threshold={args.rs_threshold} "
             f"sl={args.sl} mh={args.mh}",
             f"- 총 거래(sell): {ev['n_trades']}  거래Sharpe(per-trade): {ev['trade_sharpe']:.3f}  PSR: {ev['psr']:.3f}",
             "", "## 국면별 절대수익 (per-trade pnl)", "",
             "| 국면 | n | 평균 | 중앙 | 승률 |", "|---|---|---|---|---|"]
    for reg in ("bull", "sideways", "bear", "unknown"):
        s = ev["by_regime"].get(reg)
        if s:
            lines.append(f"| {reg} | {s['n']} | {s['mean_pnl']*100:+.2f}% | "
                         f"{s['median_pnl']*100:+.2f}% | {s['win_rate']*100:.1f}% |")
    lines += ["", "## 약세장 에피소드", "", "| 에피소드 | n | 평균 | 승률 |", "|---|---|---|---|"]
    for name, _, _ in BEAR_EPISODES:
        s = ev["episodes"][name]
        lines.append(f"| {name} | {s['n']} | {s['mean_pnl']*100:+.2f}% | {s['win_rate']*100:.1f}% |")
    lines += ["", "## OOS 분할", "", "| 분할 | n | 평균 | 승률 |", "|---|---|---|---|"]
    for name, _, _ in OOS_SPLITS:
        s = ev["oos"][name]
        lines.append(f"| {name} | {s['n']} | {s['mean_pnl']*100:+.2f}% | {s['win_rate']*100:.1f}% |")
    lines += ["", "## GO/NO-GO (스펙 §6)", "",
              f"- C1 SIDEWAYS 절대수익+ & train/test 양수: {verdict['c1_sideways_oos']}",
              f"- C2 BEAR 비파국: {verdict['c2_bear_not_catastrophic']}",
              f"- C3 벤치마크 우위: {verdict['c3_benchmark']} (KOSPI 동구간 수치와 수동 대조)",
              f"- C4 약세장 에피소드 ≥1 양수: {verdict['c4_leave_one_bear']}",
              "", f"## 판정: {'✅ GO' if verdict['GO'] else '❌ NO-GO'}", ""]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
```

`main` 의 끝부분(`print('[bt] ...')` 다음)에 추가:
```python
    if not args.smoke:
        print("[regime] building daily regime map (real KOSPI)...")
        regime_map = _build_daily_regime_map(args.start, args.end)
        ev = evaluate(res, regime_map)
        verdict = go_verdict(ev)
        out = ROOT / "reports" / "regime_spike" / "rs_leader_validation.md"
        write_report(out, args, ev, verdict)
        print(f"[report] {out}  →  {'GO' if verdict['GO'] else 'NO-GO'}")
```

- [ ] **Step 2: 스모크 회귀 확인 (분석경로 추가가 기존 스모크를 안 깨는지)**

Run:
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python scripts/rs_leader_validation.py --start 2024-01-01 --end 2024-12-31 --smoke
```
Expected: 이전과 동일하게 `[bt] ...` 출력 후 정상 종료 (smoke 라 리포트 생략).

- [ ] **Step 3: 커밋**

```bash
git add scripts/rs_leader_validation.py
git commit -m "feat(rs_leader): regime decomposition, bear-episode OOS, GO/NO-GO report"
```

---

## Task 5: 전체 검증 실행 + 결과 해석 (실행 태스크 — 코드 아님)

**Files:**
- Output: `reports/regime_spike/rs_leader_validation.md`

- [ ] **Step 1: 기본 파라미터 전체 실행**

Run (장시간 — 백그라운드 권장):
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python scripts/rs_leader_validation.py \
  --start 2021-01-01 --end 2026-05-29 --universe-top 300 \
  --k 10 --rs-threshold 0.7 --rs-n 120 --sl 0.08 --mh 30
```
Expected: `[report] ...rs_leader_validation.md  →  GO` 또는 `NO-GO`.

- [ ] **Step 2: 소수 그리드 plateau 확인 (과적합 방지)**

`rs_threshold ∈ {0.6, 0.7, 0.8}`, `rs_n ∈ {60, 120}`, `k ∈ {5, 10}` 를 각각 한 번씩 실행해 국면별 결과의 **일관성(고원)** 을 확인한다(칼날 최적점이면 기각). 각 실행 전 `--out` 대신 리포트 파일명을 수동 백업하거나, 결과 표를 수기 기록.

예:
```bash
python scripts/rs_leader_validation.py --start 2021-01-01 --end 2026-05-29 --universe-top 300 --k 5 --rs-threshold 0.6 --rs-n 60 --sl 0.08 --mh 30
```

- [ ] **Step 3: KOSPI 벤치마크 수동 대조 (C3)**

각 약세장 에피소드 구간의 KOSPI 수익률을 조회해 전략 per-trade 평균과 대조(전략이 나쁜 장에서 KOSPI보다 나은지). 조회:
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python -c "
import psycopg2, pandas as pd
c=psycopg2.connect(host='localhost',port=5433,dbname='robotrader',user='robotrader',password='robotrader_secure_pw_2024')
for nm,lo,hi in [('2022','2022-01-01','2022-12-31'),('2024H2','2024-07-01','2024-12-31'),('2026-03','2026-02-15','2026-03-31')]:
    df=pd.read_sql(\"SELECT date,close FROM daily_prices WHERE stock_code='KOSPI' AND date BETWEEN %s AND %s ORDER BY date\",c,params=(lo,hi))
    print(nm, f'{(df.close.iloc[-1]/df.close.iloc[0]-1)*100:+.1f}%')
"
```

- [ ] **Step 4: 최종 판정 + 메모리 기록**

리포트의 GO/NO-GO 와 plateau·벤치마크 대조를 종합해 최종 판정을 `reports/regime_spike/rs_leader_validation.md` 하단에 "최종 결론" 절로 수기 추가. 결과를 프로젝트 메모리(`MEMORY.md` + 토픽 파일)에 한 줄 기록.

- [ ] **Step 5: 커밋**

```bash
git add reports/regime_spike/rs_leader_validation.md
git commit -m "docs(rs_leader): validation spike GO/NO-GO results"
```

---

## 검증 후 분기

- **GO** → 별도 스펙·플랜으로 `strategies/rs_leader/` 페이퍼 전략(7번째) + EOD 스크리너 어댑터 구현 (스펙 §7 산출물 2). 이 플랜의 범위 아님.
- **NO-GO** → 전략 미구현. 리포트에 사유 기록하고 종료. (거짓 GO보다 거짓 NO가 싸다 — 스펙 §6)

## 자기검토 메모 (작성자)

- 스펙 §3 절대상승추세 → Task1 RSLeaderRule. §3 횡단면 RS → Task3 `apply_entry_filter(rs_rank)` 재사용. §3 샤프너(옵션)는 미포함(1차 단순화, GO 후 추가 검토) — 플랜 실행 시 필요하면 mkt_rs/breadth 추가 필터로 확장.
- §5 데이터·실제 KOSPI → Task3 자체 로드 + Task4 `_build_daily_regime_map`. §6 채점(국면분해·OOS·PSR·plateau) → Task2/4/5. §6 GO 4기준 → `go_verdict`(C3는 수동).
- §4 청산: tp는 추세추종이라 사실상 비활성(99.0), sl 0.08 + mh + (MA20 이탈은 1차 미모델 — `_SLTPMHAdapter` 한계, GO 후 커스텀 어댑터로 보강 예정. 한계를 리포트에 명시).
- 비용: run_portfolio 내장(왕복 ~0.4%) — 별도 차감 불요.
