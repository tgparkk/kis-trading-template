# Intraday Timing Lab (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 분봉 기반 매수/매도 타이밍 룰을 3전략 신호에 조건부로 적용해, baseline(D+1 시가 진입 + 일봉 청산) 대비 트레이드 결과 개선 여부를 측정만 하는 파이프라인을 구축한다.

**Architecture:** `scripts/feature_edge/timing/` 신규 — 순수함수 분봉 피처(VWAP·오프닝레인지·갭) → 매수/매도 타이밍 룰 → 트레이드 시뮬레이터(baseline vs 대안, gross/net) → 델타 측정(부트스트랩·기간내 OOS) → 리포트. Phase 0의 `signals.py`(진입신호)·`loaders.py`(일봉)·exit 어댑터 인터페이스를 재사용. 모델학습·라이브배선 없음.

**Tech Stack:** Python 3.9, pandas, numpy, psycopg2, pytest. 분봉 = `robotrader.minute_candles`(1분봉, 컬럼 open/high/low/close/volume/amount/time/trade_date).

**핵심 계약(태스크 간 일관):**
- 분봉 df: 컬럼 `time, open, high, low, close, volume, amount`, datetime 오름차순. 1분봉 = 1행/분.
- `EntryFill = namedtuple("EntryFill", ["price", "bar_idx", "reason"])`; 매수룰 `rule(intraday, baseline_open, params) -> Optional[EntryFill]` (None=스킵).
- `IntradayExit = namedtuple("IntradayExit", ["price", "bar_idx", "reason"])`; 매도룰 `rule(intraday, entry_price, params) -> Optional[IntradayExit]` (None=당일 장중청산 없음).
- 일봉 청산 어댑터 인터페이스(기존 `scripts/discovery/exit_adapters.py` 동일): `exit_reason(daily_df, i, position, params) -> Optional[str]`. position=`{"entry_price","entry_idx"}`.
- `Trade = namedtuple("Trade", ["filled","entry_price","exit_price","ret_gross","ret_net","hold_days","mfe","mae","exit_reason"])`.

---

## File Structure
신규 `scripts/feature_edge/timing/`:
- `config.py` — 상수
- `intraday_features.py` — vwap·opening_range·gap (순수·PIT)
- `buy_rules.py` — 매수 타이밍 5룰
- `sell_rules.py` — 매도 타이밍 5룰
- `trade_sim.py` — FixedExitAdapter + simulate_trade
- `timing_metrics.py` — 델타·부트스트랩·기간내 OOS
- `intraday_loader.py` — minute_candles 로더(실DB)
- `run_timing_lab.py` — 오케스트레이터 + 리포트

테스트: `tests/feature_edge/timing/test_*.py`. 산출물: `reports/discovery/timing_lab/{trades.parquet,timing_report.md}`.

---

## Task 1: 스캐폴드 + config

**Files:**
- Create: `scripts/feature_edge/timing/__init__.py` (빈), `scripts/feature_edge/timing/config.py`
- Test: `tests/feature_edge/timing/__init__.py` (빈), `tests/feature_edge/timing/test_config.py`

- [ ] **Step 1: 실패 테스트** — `tests/feature_edge/timing/test_config.py`
```python
from scripts.feature_edge.timing import config


def test_constants():
    assert config.INTRADAY_START == "2025-02-24"
    assert config.INTRADAY_END == "2026-06-12"
    assert config.OOS_SPLIT == "2026-01-01"
    assert config.SLIPPAGE_PER_SIDE == 0.001
    assert config.OPENING_RANGE_MIN == 30
    assert config.TIMING_STRATEGIES == (
        "daytrading_3methods_breakout", "deep_mr_dev20", "book_envelope_200d")
    assert config.TRADES_PATH.endswith("trades.parquet")
    assert config.REPORT_PATH.endswith("timing_report.md")
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/feature_edge/timing/test_config.py -v` → FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현** — `scripts/feature_edge/timing/config.py`
```python
"""Intraday Timing Lab 상수 (측정 전용 Phase 1)."""
import os

INTRADAY_START = "2025-02-24"      # minute_candles 커버 시작
INTRADAY_END = "2026-06-12"
OOS_SPLIT = "2026-01-01"           # 기간내 OOS: train < split ≤ test
SLIPPAGE_PER_SIDE = 0.001          # net 계산용 편도 슬리피지 가정(0.10%)
OPENING_RANGE_MIN = 30             # 오프닝레인지 분
GAP_SKIP_PCT = 0.05                # 갭업 스킵 임계
INTRADAY_TRAIL_PCT = 0.03          # 장중 트레일 이탈
TIME_EXIT = "1430"                 # 시각청산 (HHMM)
MOM_LOSS_MIN = 30                  # 모멘텀소실 lookback 분
ATR_STOP_K = 2.0                   # ATR 손절 배수

TIMING_STRATEGIES = (
    "daytrading_3methods_breakout", "deep_mr_dev20", "book_envelope_200d")

_REPORT_DIR = os.path.join("reports", "discovery", "timing_lab")
TRADES_PATH = os.path.join(_REPORT_DIR, "trades.parquet")
REPORT_PATH = os.path.join(_REPORT_DIR, "timing_report.md")
```
빈 파일 `scripts/feature_edge/timing/__init__.py`, `tests/feature_edge/timing/__init__.py` 생성.

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/feature_edge/timing/test_config.py -v` → PASS

- [ ] **Step 5: 커밋**
```bash
git add scripts/feature_edge/timing/__init__.py scripts/feature_edge/timing/config.py tests/feature_edge/timing/__init__.py tests/feature_edge/timing/test_config.py
git commit -m "feat(timing): 스캐폴드 + config"
```

---

## Task 2: 분봉 피처 (VWAP·오프닝레인지·갭)

**Files:** Create `scripts/feature_edge/timing/intraday_features.py`; Test `tests/feature_edge/timing/test_intraday_features.py`

- [ ] **Step 1: 실패 테스트**
```python
import numpy as np
import pandas as pd
from scripts.feature_edge.timing.intraday_features import vwap, opening_range, gap_pct


def _intra(o, h, l, c, v, a):
    n = len(c)
    return pd.DataFrame({"time": [f"{900+i:04d}" for i in range(n)],
                         "open": o, "high": h, "low": l, "close": c,
                         "volume": v, "amount": a})


def test_vwap_cumulative_pit():
    # amount=가격*거래량 가정: VWAP[t] = Σamount/Σvolume (t까지 누적)
    df = _intra([10]*3,[10]*3,[10]*3,[10,20,30],[1,1,1],[10,20,30])
    w = vwap(df)
    assert np.isclose(w.iloc[0], 10.0)
    assert np.isclose(w.iloc[1], (10+20)/2)
    assert np.isclose(w.iloc[2], (10+20+30)/3)


def test_opening_range_first_n_bars():
    df = _intra(o=[5]*5, h=[5,7,6,9,4], l=[5,3,2,5,1], c=[5]*5, v=[1]*5, a=[5]*5)
    hi, lo = opening_range(df, n=3)
    assert hi == 7  # max high of first 3 bars
    assert lo == 2  # min low of first 3 bars


def test_gap_pct():
    assert np.isclose(gap_pct(d1_open=110.0, prev_close=100.0), 0.10)
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/timing/intraday_features.py`
```python
"""분봉 파생피처 (PIT: 각 봉은 그 봉까지의 누적/창만 사용)."""
from __future__ import annotations

import pandas as pd


def vwap(intraday: pd.DataFrame) -> pd.Series:
    """누적 VWAP = Σamount / Σvolume (각 봉 t까지). amount=거래대금."""
    cum_amt = intraday["amount"].astype(float).cumsum()
    cum_vol = intraday["volume"].astype(float).cumsum().replace(0, pd.NA)
    return (cum_amt / cum_vol).astype(float)


def opening_range(intraday: pd.DataFrame, n: int):
    """첫 n봉(=n분)의 (고가, 저가)."""
    head = intraday.iloc[:n]
    return float(head["high"].astype(float).max()), float(head["low"].astype(float).min())


def gap_pct(d1_open: float, prev_close: float) -> float:
    """D+1 시가 갭 = d1_open/prev_close - 1."""
    if prev_close <= 0:
        return 0.0
    return d1_open / prev_close - 1.0
```

- [ ] **Step 4: 통과 확인** → PASS (3 tests)

- [ ] **Step 5: 커밋**
```bash
git add scripts/feature_edge/timing/intraday_features.py tests/feature_edge/timing/test_intraday_features.py
git commit -m "feat(timing): 분봉 피처 VWAP·오프닝레인지·갭 (PIT)"
```

---

## Task 3: 매수 타이밍 룰 5종

**Files:** Create `scripts/feature_edge/timing/buy_rules.py`; Test `tests/feature_edge/timing/test_buy_rules.py`

- [ ] **Step 1: 실패 테스트**
```python
import numpy as np
import pandas as pd
from scripts.feature_edge.timing.buy_rules import (
    vwap_entry, gap_skip, opening_range_breakout, pullback_to_vwap, first30_strength)


def _intra(o, h, l, c, v=None, a=None):
    n = len(c)
    v = v or [1]*n
    a = a or [o[i]*v[i] for i in range(n)]
    return pd.DataFrame({"time": [f"{900+i:04d}" for i in range(n)],
                         "open": o, "high": h, "low": l, "close": c,
                         "volume": v, "amount": a})


def test_vwap_entry_returns_first_vwap_price():
    df = _intra([10,10,10],[10,10,10],[10,10,10],[10,10,10])
    fill = vwap_entry(df, baseline_open=10.0, params={})
    assert fill is not None and np.isclose(fill.price, 10.0)


def test_gap_skip_blocks_when_gap_exceeds():
    df = _intra([11]*3,[11]*3,[11]*3,[11]*3)
    # prev_close 주입 via params
    assert gap_skip(df, baseline_open=11.0, params={"prev_close": 10.0, "gap_skip_pct": 0.05}) is None
    assert gap_skip(df, baseline_open=10.2, params={"prev_close": 10.0, "gap_skip_pct": 0.05}) is not None


def test_opening_range_breakout_enters_on_break():
    # 첫 3봉 고가 12, 4번째 봉 high 13 → 돌파
    df = _intra(o=[10,10,10,10,10], h=[11,12,11,13,10], l=[9]*5, c=[10]*5)
    fill = opening_range_breakout(df, baseline_open=10.0, params={"or_min": 3})
    assert fill is not None and fill.price >= 12


def test_opening_range_breakout_skips_if_no_break():
    df = _intra(o=[10]*5, h=[11,12,11,11,10], l=[9]*5, c=[10]*5)
    assert opening_range_breakout(df, baseline_open=10.0, params={"or_min": 3}) is None


def test_first30_strength_skip_when_weak():
    # 첫 30분(여기선 첫 3봉) 종가<시가 → 스킵
    df = _intra(o=[10,10,10,10], h=[10]*4, l=[9]*4, c=[9,9,9,9])
    assert first30_strength(df, baseline_open=10.0, params={"or_min": 3}) is None
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/timing/buy_rules.py`
```python
"""매수 타이밍 룰. rule(intraday, baseline_open, params) -> EntryFill|None (None=스킵)."""
from __future__ import annotations

from collections import namedtuple
from typing import Optional

import pandas as pd

from scripts.feature_edge.timing.intraday_features import vwap, opening_range, gap_pct

EntryFill = namedtuple("EntryFill", ["price", "bar_idx", "reason"])


def vwap_entry(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    if intraday is None or len(intraday) == 0:
        return None
    w = vwap(intraday)
    return EntryFill(price=float(w.iloc[0]), bar_idx=0, reason="vwap_entry")


def gap_skip(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    g = gap_pct(baseline_open, params.get("prev_close", baseline_open))
    if g > params.get("gap_skip_pct", 0.05):
        return None
    return EntryFill(price=float(baseline_open), bar_idx=0, reason="gap_ok")


def opening_range_breakout(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    if intraday is None or len(intraday) == 0:
        return None
    n = params.get("or_min", 30)
    hi, _ = opening_range(intraday, n)
    after = intraday.iloc[n:]
    for idx, row in after.iterrows():
        if float(row["high"]) >= hi:
            return EntryFill(price=float(hi), bar_idx=int(idx), reason="or_breakout")
    return None


def pullback_to_vwap(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    if intraday is None or len(intraday) == 0:
        return None
    w = vwap(intraday)
    for i in range(len(intraday)):
        if float(intraday["low"].iloc[i]) <= float(w.iloc[i]):
            return EntryFill(price=float(w.iloc[i]), bar_idx=i, reason="pullback_vwap")
    return None


def first30_strength(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    if intraday is None or len(intraday) == 0:
        return None
    n = params.get("or_min", 30)
    head = intraday.iloc[:n]
    if float(head["close"].iloc[-1]) > float(head["open"].iloc[0]):
        # 강세 확인 후 n봉째 종가에 진입
        return EntryFill(price=float(head["close"].iloc[-1]), bar_idx=min(n, len(intraday)) - 1,
                         reason="first30_strong")
    return None
```

- [ ] **Step 4: 통과 확인** → PASS (5 tests)

- [ ] **Step 5: 커밋**
```bash
git add scripts/feature_edge/timing/buy_rules.py tests/feature_edge/timing/test_buy_rules.py
git commit -m "feat(timing): 매수 타이밍 룰 5종"
```

---

## Task 4: 매도 타이밍 룰 5종

**Files:** Create `scripts/feature_edge/timing/sell_rules.py`; Test `tests/feature_edge/timing/test_sell_rules.py`

- [ ] **Step 1: 실패 테스트**
```python
import pandas as pd
from scripts.feature_edge.timing.sell_rules import (
    vwap_break_exit, intraday_trail, time_exit, intraday_momentum_loss)


def _intra(c, h=None, l=None, v=None, a=None, times=None):
    n = len(c)
    h = h or c; l = l or c; v = v or [1]*n; a = a or [c[i]*v[i] for i in range(n)]
    times = times or [f"{900+i:04d}" for i in range(n)]
    return pd.DataFrame({"time": times, "open": c, "high": h, "low": l,
                         "close": c, "volume": v, "amount": a})


def test_vwap_break_exits_when_close_below_vwap():
    # 가격이 오르다 마지막에 vwap 아래로 — close < vwap 시 청산
    df = _intra(c=[10, 12, 8])
    x = vwap_break_exit(df, entry_price=10.0, params={})
    assert x is not None and x.reason == "vwap_break"


def test_intraday_trail_exits_on_drawdown_from_high():
    # 당일 고가 12 후 -3% 이탈(<=11.64)
    df = _intra(c=[10, 12, 11.5], h=[10, 12, 12])
    x = intraday_trail(df, entry_price=10.0, params={"trail_pct": 0.03})
    assert x is not None and x.reason == "intraday_trail"


def test_time_exit_triggers_at_or_after_time():
    df = _intra(c=[10, 11, 12], times=["1300", "1430", "1500"])
    x = time_exit(df, entry_price=10.0, params={"time_exit": "1430"})
    assert x is not None and x.bar_idx == 1


def test_momentum_loss_exits_on_negative_lookback():
    df = _intra(c=[10, 11, 10.5])  # 직전 1봉 수익률 음전환
    x = intraday_momentum_loss(df, entry_price=10.0, params={"mom_min": 1})
    assert x is not None and x.reason == "mom_loss"
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/timing/sell_rules.py`
```python
"""매도 타이밍 룰. rule(intraday, entry_price, params) -> IntradayExit|None.

각 룰은 당일 분봉에서 가장 먼저 트리거되는 봉의 청산을 반환(없으면 None).
PIT: 봉 t 판정은 t까지의 정보만 사용.
"""
from __future__ import annotations

from collections import namedtuple
from typing import Optional

import pandas as pd

from scripts.feature_edge.timing.intraday_features import vwap

IntradayExit = namedtuple("IntradayExit", ["price", "bar_idx", "reason"])


def vwap_break_exit(intraday: pd.DataFrame, entry_price: float, params: dict) -> Optional[IntradayExit]:
    w = vwap(intraday)
    for i in range(len(intraday)):
        if float(intraday["close"].iloc[i]) < float(w.iloc[i]):
            return IntradayExit(price=float(intraday["close"].iloc[i]), bar_idx=i, reason="vwap_break")
    return None


def intraday_trail(intraday: pd.DataFrame, entry_price: float, params: dict) -> Optional[IntradayExit]:
    k = params.get("trail_pct", 0.03)
    run_high = float("-inf")
    for i in range(len(intraday)):
        run_high = max(run_high, float(intraday["high"].iloc[i]))
        if float(intraday["low"].iloc[i]) <= run_high * (1 - k):
            return IntradayExit(price=float(run_high * (1 - k)), bar_idx=i, reason="intraday_trail")
    return None


def time_exit(intraday: pd.DataFrame, entry_price: float, params: dict) -> Optional[IntradayExit]:
    cutoff = params.get("time_exit", "1430")
    for i in range(len(intraday)):
        if str(intraday["time"].iloc[i]) >= cutoff:
            return IntradayExit(price=float(intraday["close"].iloc[i]), bar_idx=i, reason="time_exit")
    return None


def intraday_momentum_loss(intraday: pd.DataFrame, entry_price: float, params: dict) -> Optional[IntradayExit]:
    n = params.get("mom_min", 30)
    c = intraday["close"].astype(float).reset_index(drop=True)
    for i in range(n, len(c)):
        if c.iloc[i] < c.iloc[i - n]:
            return IntradayExit(price=float(c.iloc[i]), bar_idx=i, reason="mom_loss")
    return None
```
> `atr_scaled_stop` 은 일봉 ATR 의존이라 trade_sim 의 일봉 청산 어댑터(Task 5)에서 다룬다(분봉 룰 아님).

- [ ] **Step 4: 통과 확인** → PASS (4 tests)

- [ ] **Step 5: 커밋**
```bash
git add scripts/feature_edge/timing/sell_rules.py tests/feature_edge/timing/test_sell_rules.py
git commit -m "feat(timing): 매도 타이밍 룰 4종 (분봉)"
```

---

## Task 5: 트레이드 시뮬레이터 + FixedExitAdapter

**Files:** Create `scripts/feature_edge/timing/trade_sim.py`; Test `tests/feature_edge/timing/test_trade_sim.py`

- [ ] **Step 1: 실패 테스트**
```python
import numpy as np
import pandas as pd
from scripts.feature_edge.timing.trade_sim import FixedExitAdapter, simulate_trade


def _daily(closes):
    n = len(closes)
    return pd.DataFrame({"date": [f"2025-03-{i+1:02d}" for i in range(n)],
                         "open": closes, "high": [c*1.0 for c in closes],
                         "low": closes, "close": closes})


def test_fixed_exit_take_profit():
    adapter = FixedExitAdapter()
    params = {"stop_loss_pct": 0.10, "take_profit_pct": 0.10, "max_hold_bars": 10}
    daily = _daily([100, 100, 115])  # +15% at idx2 → tp
    pos = {"entry_price": 100.0, "entry_idx": 1}
    assert adapter.exit_reason(daily, 2, pos, params) == "take_profit"


def test_baseline_trade_no_intraday_rules():
    daily = _daily([100, 100, 90])  # entry idx1=100, idx2 close 90 → -10% sl
    params = {"stop_loss_pct": 0.10, "take_profit_pct": 0.10, "max_hold_bars": 10}
    tr = simulate_trade(signal_idx=0, daily=daily, intraday_by_date={},
                        exit_adapter=FixedExitAdapter(), exit_params=params,
                        buy_rule=None, sell_rule=None, buy_params={}, sell_params={},
                        slippage=0.0)
    assert tr.filled is True
    assert np.isclose(tr.entry_price, 100.0)
    assert tr.exit_reason == "stop_loss"
    assert np.isclose(tr.ret_gross, -0.10, atol=1e-6)


def test_net_applies_slippage_both_sides():
    daily = _daily([100, 100, 110])
    params = {"stop_loss_pct": 0.10, "take_profit_pct": 0.10, "max_hold_bars": 10}
    tr = simulate_trade(0, daily, {}, FixedExitAdapter(), params,
                        None, None, {}, {}, slippage=0.01)
    # net = 110*(0.99) / (100*1.01) - 1 < gross
    assert tr.ret_net < tr.ret_gross


def test_buy_skip_yields_unfilled():
    daily = _daily([100, 100, 110])
    params = {"stop_loss_pct": 0.10, "take_profit_pct": 0.10, "max_hold_bars": 10}

    def always_skip(intra, base_open, p):
        return None
    tr = simulate_trade(0, daily, {}, FixedExitAdapter(), params,
                        buy_rule=always_skip, sell_rule=None, buy_params={}, sell_params={},
                        slippage=0.0)
    assert tr.filled is False
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/timing/trade_sim.py`
```python
"""트레이드 시뮬레이터: baseline(D+1 시가+일봉청산) vs 분봉 타이밍 오버레이. gross/net."""
from __future__ import annotations

from collections import namedtuple
from typing import Callable, Optional

import pandas as pd

Trade = namedtuple("Trade", ["filled", "entry_price", "exit_price", "ret_gross",
                             "ret_net", "hold_days", "mfe", "mae", "exit_reason"])

_UNFILLED = Trade(False, float("nan"), float("nan"), float("nan"), float("nan"),
                  0, float("nan"), float("nan"), "skip")


class FixedExitAdapter:
    """고정 청산: sl → tp → max_hold (종가 기준). 돌파/돌파류 baseline."""
    def exit_reason(self, daily: pd.DataFrame, i: int, position: dict, params: dict) -> Optional[str]:
        entry = position["entry_price"]
        ret = float(daily["close"].iloc[i]) / entry - 1.0
        if ret <= -params["stop_loss_pct"]:
            return "stop_loss"
        if ret >= params["take_profit_pct"]:
            return "take_profit"
        if i - position["entry_idx"] >= params["max_hold_bars"]:
            return "max_hold"
        return None


def simulate_trade(signal_idx: int, daily: pd.DataFrame, intraday_by_date: dict,
                   exit_adapter, exit_params: dict,
                   buy_rule: Optional[Callable], sell_rule: Optional[Callable],
                   buy_params: dict, sell_params: dict, slippage: float) -> Trade:
    e = signal_idx + 1
    if e >= len(daily):
        return _UNFILLED
    d1 = daily.iloc[e]
    baseline_open = float(d1["open"])
    intra_d1 = intraday_by_date.get(d1["date"])

    if buy_rule is not None:
        bp = dict(buy_params); bp.setdefault("prev_close", float(daily["close"].iloc[signal_idx]))
        fill = buy_rule(intra_d1, baseline_open, bp)
        if fill is None:
            return _UNFILLED
        entry_price = float(fill.price)
    else:
        entry_price = baseline_open

    position = {"entry_price": entry_price, "entry_idx": e}
    exit_price, reason, hold = None, None, 0
    last = min(e + exit_params["max_hold_bars"], len(daily) - 1)
    mfe, mae = float("-inf"), float("inf")
    for i in range(e, last + 1):
        day = daily.iloc[i]
        mfe = max(mfe, float(day["high"]) / entry_price - 1.0)
        mae = min(mae, float(day["low"]) / entry_price - 1.0)
        intra = intraday_by_date.get(day["date"])
        if sell_rule is not None and intra is not None:
            xi = sell_rule(intra, entry_price, sell_params)
            if xi is not None:
                exit_price, reason, hold = float(xi.price), xi.reason, i - e
                break
        r = exit_adapter.exit_reason(daily, i, position, exit_params)
        if r is not None:
            exit_price, reason, hold = float(day["close"]), r, i - e
            break
    if exit_price is None:
        exit_price, reason, hold = float(daily["close"].iloc[last]), "max_hold", last - e

    ret_gross = exit_price / entry_price - 1.0
    ret_net = (exit_price * (1 - slippage)) / (entry_price * (1 + slippage)) - 1.0
    return Trade(True, entry_price, exit_price, ret_gross, ret_net, hold, mfe, mae, reason)
```

- [ ] **Step 4: 통과 확인** → PASS (4 tests)

- [ ] **Step 5: 커밋**
```bash
git add scripts/feature_edge/timing/trade_sim.py tests/feature_edge/timing/test_trade_sim.py
git commit -m "feat(timing): 트레이드 시뮬레이터 + FixedExitAdapter (gross/net)"
```

---

## Task 6: 타이밍 측정 (델타·부트스트랩·기간내 OOS)

**Files:** Create `scripts/feature_edge/timing/timing_metrics.py`; Test `tests/feature_edge/timing/test_timing_metrics.py`

- [ ] **Step 1: 실패 테스트**
```python
import numpy as np
import pandas as pd
from scripts.feature_edge.timing.timing_metrics import (
    summarize_trades, delta_vs_baseline, bootstrap_delta_p05)


def _trades(rets, dates=None):
    n = len(rets)
    dates = dates or pd.date_range("2025-03-01", periods=n, freq="D")
    return pd.DataFrame({"date": dates, "ret_net": rets, "ret_gross": rets})


def test_summarize_trades_basic():
    s = summarize_trades(_trades([0.1, -0.05, 0.2, -0.1]), col="ret_net")
    assert np.isclose(s["mean"], 0.0375, atol=1e-6)
    assert np.isclose(s["hit_rate"], 0.5)
    assert s["n"] == 4


def test_delta_positive_when_alt_better():
    base = _trades([0.0, 0.0, 0.0, 0.0])
    alt = _trades([0.05, 0.05, 0.05, 0.05])
    d = delta_vs_baseline(alt, base, col="ret_net")
    assert d["delta_mean"] > 0


def test_bootstrap_delta_p05_returns_float():
    rng = np.random.RandomState(0)
    alt = _trades(list(rng.randn(60) * 0.02 + 0.01))
    base = _trades(list(rng.randn(60) * 0.02))
    p05 = bootstrap_delta_p05(alt, base, col="ret_net", n_iter=200)
    assert isinstance(p05, float)
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/timing/timing_metrics.py`
```python
"""타이밍 측정: 트레이드 요약·baseline 델타·부트스트랩 p05·기간내 OOS."""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def summarize_trades(trades: pd.DataFrame, col: str = "ret_net") -> Dict[str, float]:
    r = trades[col].dropna()
    if len(r) == 0:
        return {"n": 0, "mean": float("nan"), "hit_rate": float("nan"), "sharpe": float("nan")}
    sharpe = r.mean() / r.std() if r.std() > 0 else float("nan")
    return {"n": int(len(r)), "mean": float(r.mean()),
            "hit_rate": float((r > 0).mean()), "sharpe": float(sharpe)}


def delta_vs_baseline(alt: pd.DataFrame, base: pd.DataFrame, col: str = "ret_net") -> Dict[str, float]:
    a, b = summarize_trades(alt, col), summarize_trades(base, col)
    return {"delta_mean": a["mean"] - b["mean"],
            "delta_hit": a["hit_rate"] - b["hit_rate"],
            "alt_n": a["n"], "base_n": b["n"], "alt_mean": a["mean"], "base_mean": b["mean"]}


def bootstrap_delta_p05(alt: pd.DataFrame, base: pd.DataFrame, col: str = "ret_net",
                        n_iter: int = 1000) -> float:
    """alt 평균 − base 평균 의 부트스트랩 분포 p05 (>0이면 개선 견고)."""
    a = alt[col].dropna().to_numpy()
    b = base[col].dropna().to_numpy()
    if len(a) < 10 or len(b) < 10:
        return float("nan")
    rng = np.random.RandomState(42)
    deltas = []
    for _ in range(n_iter):
        sa = rng.choice(a, len(a), replace=True)
        sb = rng.choice(b, len(b), replace=True)
        deltas.append(sa.mean() - sb.mean())
    return float(np.percentile(deltas, 5))


def oos_delta_signs(alt: pd.DataFrame, base: pd.DataFrame, split: str, col: str = "ret_net") -> Dict[str, float]:
    """기간내 OOS: split 기준 train/test 각 델타 평균 부호."""
    da = pd.to_datetime(alt["date"]); db = pd.to_datetime(base["date"])
    tr = delta_vs_baseline(alt[da < split], base[db < split], col)["delta_mean"]
    te = delta_vs_baseline(alt[da >= split], base[db >= split], col)["delta_mean"]
    return {"train_delta": tr, "test_delta": te,
            "consistent": bool(pd.notna(tr) and pd.notna(te) and (tr > 0) == (te > 0))}
```

- [ ] **Step 4: 통과 확인** → PASS (3 tests)

- [ ] **Step 5: 커밋**
```bash
git add scripts/feature_edge/timing/timing_metrics.py tests/feature_edge/timing/test_timing_metrics.py
git commit -m "feat(timing): 타이밍 측정 (델타·부트스트랩·기간내 OOS)"
```

---

## Task 7: 분봉 로더 (실DB)

**Files:** Create `scripts/feature_edge/timing/intraday_loader.py`; Test `tests/feature_edge/timing/test_intraday_loader.py`

VERIFIED DB FACTS: `robotrader.minute_candles` 컬럼 `stock_code, trade_date(YYYYMMDD str), time, open, high, low, close, volume, amount, datetime`. 접속 localhost:5433 robotrader/1234.

- [ ] **Step 1: 실패 테스트**
```python
import pytest
from scripts.feature_edge.timing import intraday_loader as L


def test_functions_exist():
    assert hasattr(L, "load_intraday_by_date")
    assert hasattr(L, "covered_stock_dates")


@pytest.mark.integration
def test_load_intraday_real():
    # 005930 의 한 거래일 분봉이 비어있지 않은지(커버 구간)
    m = L.load_intraday_by_date("005930", "2026-06-12")
    assert m is None or "close" in m.columns
```

- [ ] **Step 2: 실패 확인** (`test_functions_exist`) → FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/timing/intraday_loader.py`
```python
"""minute_candles 로더 (읽기전용)."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Dict, Optional

import pandas as pd
import psycopg2


@contextmanager
def _conn():
    c = psycopg2.connect(host=os.getenv("TIMESCALE_HOST", "localhost"),
                         port=int(os.getenv("TIMESCALE_PORT", 5433)),
                         dbname="robotrader", user=os.getenv("TIMESCALE_USER", "robotrader"),
                         password=os.getenv("TIMESCALE_PASSWORD", "1234"))
    try:
        yield c
    finally:
        c.close()


def _norm(date: str) -> str:
    return date.replace("-", "") if "-" in date else date


def load_intraday_by_date(stock_code: str, trade_date: str) -> Optional[pd.DataFrame]:
    td = _norm(trade_date)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT time, open, high, low, close, volume, amount FROM minute_candles "
                    "WHERE stock_code=%s AND trade_date=%s ORDER BY datetime", (stock_code, td))
        rows = cur.fetchall()
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume", "amount"])


def load_intraday_supplier(stock_code: str) -> Dict[str, pd.DataFrame]:
    """{ 'YYYY-MM-DD' -> 분봉df } 전체. trade_sim 의 intraday_by_date 로 사용."""
    with _conn() as conn:
        df = pd.read_sql(
            "SELECT trade_date, time, open, high, low, close, volume, amount "
            "FROM minute_candles WHERE stock_code=%s ORDER BY datetime", conn, params=(stock_code,))
    out: Dict[str, pd.DataFrame] = {}
    if len(df) == 0:
        return out
    for td, g in df.groupby("trade_date"):
        iso = f"{td[:4]}-{td[4:6]}-{td[6:8]}"
        out[iso] = g.drop(columns=["trade_date"]).reset_index(drop=True)
    return out


def covered_stock_dates() -> Dict[str, int]:
    """{ stock_code -> 분봉 보유 거래일수 } (커버 종목 식별용)."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT stock_code, count(distinct trade_date) FROM minute_candles GROUP BY stock_code")
        return {str(s): int(n) for s, n in cur.fetchall()}
```

- [ ] **Step 4: 통과 확인** (`test_functions_exist`) → PASS

- [ ] **Step 4b: 실DB 스모크**
```bash
python -c "from scripts.feature_edge.timing import intraday_loader as L; m=L.load_intraday_by_date('005930','2026-06-12'); print('bars', 0 if m is None else len(m)); print('cov stocks', len(L.covered_stock_dates()))"
```
Expected: bars > 100, cov stocks > 1000. (0이면 trade_date 정규화/컬럼 점검 후 보정.)

- [ ] **Step 5: 커밋**
```bash
git add scripts/feature_edge/timing/intraday_loader.py tests/feature_edge/timing/test_intraday_loader.py
git commit -m "feat(timing): 분봉 로더 (minute_candles, 읽기전용)"
```

---

## Task 8: 오케스트레이터 + 리포트

**Files:** Create `scripts/feature_edge/timing/run_timing_lab.py`; Test `tests/feature_edge/timing/test_run_timing_lab.py`

설계: (1) 3전략 신호 생성(`signals.py`+`build_adapter`, 일봉=loaders), (2) 분봉 커버 종목·기간으로 제한, (3) 각 신호에 baseline + 각 룰 trade_sim, (4) 룰별 델타·부트스트랩·OOS 측정 → 리포트. 측정·리포트 조립은 순수함수 `build_timing_table(rule_trades, baseline_trades)` 로 분리 테스트. main()은 통합경로(pragma no cover).

- [ ] **Step 1: 실패 테스트**
```python
import numpy as np
import pandas as pd
from scripts.feature_edge.timing.run_timing_lab import build_timing_table


def test_build_timing_table_ranks_rules():
    base = pd.DataFrame({"date": pd.date_range("2025-03-01", periods=40),
                         "ret_net": [0.0]*40, "ret_gross": [0.0]*40})
    good = pd.DataFrame({"date": pd.date_range("2025-03-01", periods=40),
                         "ret_net": [0.03]*40, "ret_gross": [0.03]*40})
    tbl = build_timing_table({"good_rule": good}, base, split="2025-03-20")
    row = tbl[tbl.rule == "good_rule"].iloc[0]
    assert set(["rule", "alt_n", "delta_mean_net", "bootstrap_p05_net",
                "oos_consistent", "base_mean_net"]).issubset(tbl.columns)
    assert row["delta_mean_net"] > 0
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/timing/run_timing_lab.py`
```python
"""Intraday Timing Lab 오케스트레이터 (측정 전용)."""
from __future__ import annotations

import argparse
import os
from typing import Dict

import pandas as pd

from scripts.feature_edge.timing import config
from scripts.feature_edge.timing.timing_metrics import (
    delta_vs_baseline, bootstrap_delta_p05, oos_delta_signs, summarize_trades)


def build_timing_table(rule_trades: Dict[str, pd.DataFrame], baseline: pd.DataFrame,
                       split: str = None) -> pd.DataFrame:
    split = split or config.OOS_SPLIT
    rows = []
    for rule, alt in rule_trades.items():
        dn = delta_vs_baseline(alt, baseline, "ret_net")
        dg = delta_vs_baseline(alt, baseline, "ret_gross")
        oos = oos_delta_signs(alt, baseline, split, "ret_net")
        rows.append({
            "rule": rule, "alt_n": dn["alt_n"], "base_n": dn["base_n"],
            "base_mean_net": dn["base_mean"], "alt_mean_net": dn["alt_mean"],
            "delta_mean_net": dn["delta_mean"], "delta_mean_gross": dg["delta_mean"],
            "delta_hit_net": dn["delta_hit"],
            "bootstrap_p05_net": bootstrap_delta_p05(alt, baseline, "ret_net"),
            "oos_consistent": oos["consistent"],
        })
    return pd.DataFrame(rows).sort_values("delta_mean_net", ascending=False).reset_index(drop=True)


def write_report(per_strategy: Dict[str, pd.DataFrame], path: str, note: str = "") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# Intraday Timing Report (Phase 1 — 측정 전용)", "", note,
             "", "⚠️ 단일국면(2025-02~2026-06 강세/횡보) — 탐색적, 국면강건 주장 불가.",
             "판정(참고): delta_mean_net>0 ∧ bootstrap_p05_net>0 ∧ oos_consistent.", ""]
    for strat, tbl in per_strategy.items():
        lines += [f"## {strat}", "", tbl.to_markdown(index=False), ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():  # pragma: no cover (통합 실행 경로)
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="전략별 신호 종목수 제한(0=전체)")
    args = ap.parse_args()

    from runners._adapter_factory import build_adapter
    from scripts.feature_edge import loaders, signals
    from scripts.feature_edge.timing import intraday_loader, buy_rules, sell_rules
    from scripts.feature_edge.timing.trade_sim import FixedExitAdapter, simulate_trade

    cov = intraday_loader.covered_stock_dates()
    cov_codes = [c for c, n in cov.items() if n >= 20]   # 분봉 보유 거래일 ≥20
    universe = loaders.load_universe(config.INTRADAY_END)
    codes = [c for c in universe if c in set(cov_codes)]
    if args.limit:
        codes = codes[: args.limit]
    daily_sup = loaders.load_daily_supplier(codes, config.INTRADAY_END)

    BUY = {"baseline": None, "vwap_entry": buy_rules.vwap_entry, "gap_skip": buy_rules.gap_skip,
           "or_breakout": buy_rules.opening_range_breakout, "pullback_vwap": buy_rules.pullback_to_vwap,
           "first30": buy_rules.first30_strength}
    SELL = {"vwap_break": sell_rules.vwap_break_exit, "intraday_trail": sell_rules.intraday_trail,
            "time_exit": sell_rules.time_exit, "mom_loss": sell_rules.intraday_momentum_loss}
    buy_params = {"gap_skip_pct": config.GAP_SKIP_PCT, "or_min": config.OPENING_RANGE_MIN}
    sell_params = {"trail_pct": config.INTRADAY_TRAIL_PCT, "time_exit": config.TIME_EXIT,
                   "mom_min": config.MOM_LOSS_MIN}

    per_strategy = {}
    for strat in config.TIMING_STRATEGIES:
        adapter = build_adapter(strat)
        exit_params = _exit_params_for(strat)   # 아래 헬퍼
        sigs = signals.generate_entry_signals(adapter, codes, daily_sup)
        intr_cache = {c: intraday_loader.load_intraday_supplier(c) for c in sigs["stock_code"].unique()}
        rule_trades = {}
        baseline_trades = []
        # baseline + 각 단일 매수룰(매도=baseline) + 각 단일 매도룰(매수=baseline)
        for _, s in sigs.iterrows():
            d = daily_sup.get(s["stock_code"])
            if d is None:
                continue
            idx = d.index[d["date"] == pd.Timestamp(s["date"])]
            if len(idx) == 0:
                continue
            si = int(idx[0]); intr = intr_cache.get(s["stock_code"], {})
            tr = simulate_trade(si, d, intr, FixedExitAdapter(), exit_params,
                                None, None, buy_params, sell_params, config.SLIPPAGE_PER_SIDE)
            if tr.filled:
                baseline_trades.append({"date": s["date"], "ret_net": tr.ret_net, "ret_gross": tr.ret_gross})
        baseline = pd.DataFrame(baseline_trades)
        # 단일 매수룰
        for name, brule in BUY.items():
            if name == "baseline":
                continue
            rows = _run_rule(sigs, daily_sup, intr_cache, exit_params, brule, None,
                             buy_params, sell_params)
            rule_trades[f"buy:{name}"] = rows
        for name, srule in SELL.items():
            rows = _run_rule(sigs, daily_sup, intr_cache, exit_params, None, srule,
                             buy_params, sell_params)
            rule_trades[f"sell:{name}"] = rows
        per_strategy[strat] = build_timing_table(rule_trades, baseline)

    write_report(per_strategy, config.REPORT_PATH, note="3전략 분봉 타이밍 단일룰 측정.")
    print(f"[timing-lab] 리포트 {config.REPORT_PATH}")


def _exit_params_for(strat: str) -> dict:
    import yaml
    with open(os.path.join("strategies", strat, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    rm = cfg.get("risk_management", {})
    return {"stop_loss_pct": float(rm.get("stop_loss_pct", 0.08)),
            "take_profit_pct": float(rm.get("take_profit_pct", 0.10)),
            "max_hold_bars": int(rm.get("max_hold_days", 10))}


def _run_rule(sigs, daily_sup, intr_cache, exit_params, brule, srule, buy_params, sell_params):
    from scripts.feature_edge.timing.trade_sim import FixedExitAdapter, simulate_trade
    rows = []
    for _, s in sigs.iterrows():
        d = daily_sup.get(s["stock_code"])
        if d is None:
            continue
        idx = d.index[d["date"] == pd.Timestamp(s["date"])]
        if len(idx) == 0:
            continue
        si = int(idx[0]); intr = intr_cache.get(s["stock_code"], {})
        tr = simulate_trade(si, d, intr, FixedExitAdapter(), exit_params,
                            brule, srule, buy_params, sell_params, config.SLIPPAGE_PER_SIDE)
        if tr.filled:
            rows.append({"date": s["date"], "ret_net": tr.ret_net, "ret_gross": tr.ret_gross})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인** (`test_build_timing_table_ranks_rules`) → PASS

- [ ] **Step 5: 커밋**
```bash
git add scripts/feature_edge/timing/run_timing_lab.py tests/feature_edge/timing/test_run_timing_lab.py
git commit -m "feat(timing): 오케스트레이터 + 타이밍 리포트"
```

---

## Task 9: 통합 스모크 + 회귀

- [ ] **Step 1: 단위 회귀** — `python -m pytest tests/feature_edge/timing/ -v` → 전부 PASS (통합 마커 제외)

- [ ] **Step 2: 소규모 실데이터 스모크** — `python -m scripts.feature_edge.timing.run_timing_lab --limit 40` → `reports/discovery/timing_lab/timing_report.md` 생성, 예외 없이 종료.

- [ ] **Step 3: 리포트 sanity** — 3전략 섹션 존재, 각 룰의 alt_n(표본수)·delta_mean_net·bootstrap_p05_net·oos_consistent 표기. baseline 대비 음/양 델타가 합리적 범위(|delta|<0.1)인지, 표본수가 0이 아닌지 확인. deep_mr 등 표본 적으면 리포트에 그대로 노출(묵시 절단 없음).

- [ ] **Step 4: 커밋 (코드/문서만, 산출물 제외)**
```bash
git add scripts/feature_edge/timing/ tests/feature_edge/timing/
git commit -m "test(timing): 통합 스모크 + 회귀"
```
> `reports/discovery/timing_lab/*` 산출물은 커밋 제외.

---

## 후속 (범위 밖)
- 매수×매도 조합(단일 통과분 한정), 슬리피지 민감도(0.05/0.10/0.20%), atr_scaled_stop 일봉 변형, deep_mr 하한가 체결불가 정밀 모델, 결과에 따른 라이브 반영 결정.

## Self-Review 메모
- Spec 커버리지: intraday_features(T2)·buy_rules(T3)·sell_rules(T4)·trade_sim+baseline(T5)·metrics(T6)·loader(T7)·orchestrator/report(T8)·스모크(T9) = §4 컴포넌트 전부 매핑. gross/net(T5·T6), 부트스트랩·기간내 OOS(T6), 단일국면 caveat(리포트 T8), 표본 병기(T8·T9), PIT(각 피처/룰 테스트). 3전략 스코프(config·T8).
- 타입 일관성: EntryFill/IntradayExit/Trade namedtuple, 룰 시그니처 `(intraday, base_open/entry_price, params)`, exit_adapter `exit_reason(daily,i,position,params)`, intraday_by_date={isoDate:df} — 태스크 간 동일.
- 미커버(후속): 매수×매도 조합·슬리피지 민감도·atr_scaled_stop·하한가 모델.
