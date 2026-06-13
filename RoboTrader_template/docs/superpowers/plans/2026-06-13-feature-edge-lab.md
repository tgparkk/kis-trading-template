# Feature Edge Lab (Phase 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미사용 데이터로 만든 파생 피처가 선행수익률·전략진입 결과를 가르는지 **측정만** 하는 파이프라인(피처 패널 parquet + 엣지 리포트)을 구축한다.

**Architecture:** `scripts/feature_edge/` 신규 모듈 — 순수함수 피처 계산기(가격/시장/수급/이벤트) → 패널 어셈블러(parquet) → 라벨러(선행수익률·트리플배리어) → 전략 진입신호 생성기(기존 `build_adapter` 재사용) → 측정엔진(Spearman IC·조건부 기대값·부트스트랩·OOS·커버리지) → 리포트. 모델 학습·라이브 배선 없음.

**Tech Stack:** Python 3.9, pandas, numpy, psycopg2, pytest. 재사용: `db/quant_daily_reader.QuantDailyReader`, `runners/_adapter_factory.build_adapter`, `scripts/multiverse4_portfolio_analysis.block_bootstrap_metrics`.

**전략적 범위 결정:** 전략별 엣지 측정의 "결과 라벨"은 각 전략의 bespoke 청산이 아니라 **표준 선행수익률/트리플배리어 라벨**을 사용한다 — 전략 간 공정 비교(같은 outcome 정의) + 표본 일관성을 위해. 진입 시점만 각 전략 스크리너로 생성한다. bespoke 청산 라벨은 후속 정밀화 과제(이 플랜 범위 밖).

---

## File Structure

신규 (`scripts/feature_edge/`):
- `config.py` — 상수(유니버스 컷·기간·OOS분할·배리어·호라이즌·경로·커버리지 임계)
- `price_features.py` — 종목별 일봉 파생피처 (순수함수)
- `market_features.py` — 지수 파생 시장피처 + 횡단면 집계(breadth·dispersion)
- `flow_features.py` — foreign_flow 피처 (shift(1)·정규화·누적·streak)
- `event_features.py` — corp_events 플래그
- `panel.py` — 패널 어셈블러 → parquet
- `labelers.py` — 선행수익률 + 트리플배리어 라벨
- `signals.py` — 전략별 진입신호 생성 (`build_adapter` 재사용)
- `metrics.py` — IC·조건부기대값·커버리지·OOS·부트스트랩
- `run_edge_lab.py` — 오케스트레이터 → 리포트

테스트: `tests/feature_edge/test_{price_features,market_features,flow_features,event_features,labelers,signals,metrics,panel}.py`

산출물: `reports/discovery/feature_edge/feature_panel.parquet`, `reports/discovery/feature_edge/edge_report.md`

---

## Task 1: 모듈 스캐폴드 + config

**Files:**
- Create: `scripts/feature_edge/__init__.py` (빈 파일)
- Create: `scripts/feature_edge/config.py`
- Test: `tests/feature_edge/__init__.py` (빈 파일), `tests/feature_edge/test_config.py`

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_config.py`

```python
from scripts.feature_edge import config


def test_config_constants_present():
    assert config.UNIVERSE_MIN_TRADING_VALUE == 1_000_000_000
    assert config.PERIOD_START == "2021-01-01"
    assert config.OOS_SPLIT == "2024-06-30"
    assert config.FWD_HORIZONS == (5, 10, 20)
    # 트리플배리어: (up_pct, down_pct, horizon_bars) 세트
    assert (0.10, 0.05, 10) in config.BARRIER_SETS
    assert config.COVERAGE_MIN == 0.60
    assert config.PANEL_PATH.endswith("feature_panel.parquet")
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_config.py -v`
Expected: FAIL (ModuleNotFoundError: scripts.feature_edge.config)

- [ ] **Step 3: 구현** — `scripts/feature_edge/config.py`

```python
"""Feature Edge Lab 상수 (측정 전용 Phase 0)."""
import os

UNIVERSE_MIN_TRADING_VALUE = 1_000_000_000   # 1차 유동성 컷 (거래대금 ≥ 10억)
PERIOD_START = "2021-01-01"
PERIOD_END = "2026-06-12"
OOS_SPLIT = "2024-06-30"                       # train ≤ split < test (기존 게이트 관행)

FWD_HORIZONS = (5, 10, 20)                     # 선행수익률 호라이즌(거래일)
BARRIER_SETS = ((0.10, 0.05, 10), (0.15, 0.07, 20))  # (up, down, horizon)

COVERAGE_MIN = 0.60                            # 피처 non-null 비율 임계
KOSPI_INDEX_CODE = "0001"
KOSDAQ_INDEX_CODE = "1001"

_REPORT_DIR = os.path.join("reports", "discovery", "feature_edge")
PANEL_PATH = os.path.join(_REPORT_DIR, "feature_panel.parquet")
REPORT_PATH = os.path.join(_REPORT_DIR, "edge_report.md")
```

`scripts/feature_edge/__init__.py`, `tests/feature_edge/__init__.py` 는 빈 파일로 생성.

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/__init__.py scripts/feature_edge/config.py tests/feature_edge/__init__.py tests/feature_edge/test_config.py
git commit -m "feat(feature-edge): 모듈 스캐폴드 + config 상수"
```

---

## Task 2: 종목별 가격 파생피처

**Files:**
- Create: `scripts/feature_edge/price_features.py`
- Test: `tests/feature_edge/test_price_features.py`

설계: 입력 = 단일 종목 일봉 DataFrame(컬럼 `date,open,high,low,close,volume`, 오름차순). 출력 = 동일 길이 DataFrame, 각 행 t는 **t까지의 데이터만** 사용(룩어헤드 0). 워밍업 부족 구간은 NaN.

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_price_features.py`

```python
import numpy as np
import pandas as pd
from scripts.feature_edge.price_features import compute_price_features


def _df(closes, vols=None):
    n = len(closes)
    vols = vols or [1000] * n
    return pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": vols,
    })


def test_returns_and_ma_dist_pit():
    closes = [100, 110, 121, 133.1, 146.41, 161.05]  # +10%/일
    out = compute_price_features(_df(closes))
    # returns_5d at last row = close[-1]/close[-6]-1 (6행이면 idx5/idx0)
    assert np.isclose(out["returns_5d"].iloc[-1], 161.05 / 100 - 1, atol=1e-6)
    # MA20 이격은 20봉 미만이라 NaN
    assert np.isnan(out["ma20_dist"].iloc[-1])
    # 워밍업 전 returns_5d 는 NaN (idx<5)
    assert np.isnan(out["returns_5d"].iloc[4])


def test_volume_surge_ratio():
    closes = [100] * 25
    vols = [100] * 24 + [500]   # 마지막 봉 거래량 급증
    out = compute_price_features(_df(closes, vols))
    # 당일/직전20봉평균 = 500/100 = 5.0
    assert np.isclose(out["vol_surge"].iloc[-1], 5.0, atol=1e-6)


def test_no_lookahead_last_row_independent_of_future():
    closes = [100 + i for i in range(30)]
    full = compute_price_features(_df(closes))
    trunc = compute_price_features(_df(closes[:25]))
    # 24행까지의 피처는 미래봉 추가와 무관해야 함
    for col in ["returns_5d", "returns_20d", "ma20_dist", "vol_surge"]:
        assert np.allclose(full[col].iloc[:25].fillna(-999),
                           trunc[col].fillna(-999), atol=1e-9)
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_price_features.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현** — `scripts/feature_edge/price_features.py`

```python
"""종목별 일봉 파생피처 (PIT: 각 행은 자기 행까지만 사용)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_price_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    out = pd.DataFrame(index=df.index)
    out["date"] = df["date"].values

    out["returns_5d"] = c / c.shift(5) - 1.0
    out["returns_20d"] = c / c.shift(20) - 1.0
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    out["ma20_dist"] = c / ma20 - 1.0
    out["ma60_dist"] = c / ma60 - 1.0
    out["ma_align"] = ma20 / ma60 - 1.0                 # MA20-MA60 정렬
    out["mom_accel"] = out["returns_5d"] - out["returns_20d"] / 4.0
    out["high_proximity"] = c / c.rolling(60).max()      # 60일 신고가 근접도

    daily_ret = c.pct_change()
    out["vol_20d"] = daily_ret.rolling(20).std()
    out["vol_trend"] = daily_ret.rolling(5).std() / daily_ret.rolling(20).std()
    out["vol_surge"] = v / v.shift(1).rolling(20).mean()
    tv = c * v
    out["amihud"] = daily_ret.abs() / tv.replace(0, np.nan)
    out["tv_trend"] = tv.rolling(5).mean() / tv.rolling(20).mean()
    return out
```

> 주의: `v.shift(1).rolling(20).mean()` 은 당일 제외 직전 20봉 평균(당일 거래량을 분모에서 배제 = PIT 안전).

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_price_features.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/price_features.py tests/feature_edge/test_price_features.py
git commit -m "feat(feature-edge): 종목별 가격 파생피처 (PIT)"
```

---

## Task 3: 수급(foreign_flow) 피처

**Files:**
- Create: `scripts/feature_edge/flow_features.py`
- Test: `tests/feature_edge/test_flow_features.py`

설계: 입력 = 종목 일봉(date,volume) + foreign_flow(date, foreign_net_vol). 출력 = date 인덱스 피처. **shift(1)** 로 T-1 참조(T일 발표분은 T+1에야 사용). 정규화 = 순매수량/직전20봉 평균거래량.

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_flow_features.py`

```python
import numpy as np
import pandas as pd
from scripts.feature_edge.flow_features import compute_flow_features


def test_shift1_and_normalization():
    dates = pd.date_range("2023-03-01", periods=25, freq="D")
    daily = pd.DataFrame({"date": dates, "volume": [100.0] * 25})
    flow = pd.DataFrame({"date": dates, "foreign_net_vol": [0.0] * 24 + [50.0]})
    out = compute_flow_features(daily, flow)
    # 마지막 행은 당일(T) 수급을 못 봄(shift1) → flow_norm 은 T-1=0
    assert out["flow_norm"].iloc[-1] == 0.0
    # 24행(T)에서 본 직전값도 0 (그 전이 전부 0)
    assert out["flow_norm"].iloc[-2] == 0.0


def test_streak_counts_consecutive_net_buy():
    dates = pd.date_range("2023-03-01", periods=6, freq="D")
    daily = pd.DataFrame({"date": dates, "volume": [100.0] * 6})
    flow = pd.DataFrame({"date": dates, "foreign_net_vol": [10, 10, -5, 10, 10, 10]})
    out = compute_flow_features(daily, flow)
    # shift1 적용 후 streak: 마지막 행은 T-1까지의 연속 순매수 = (idx4,3=양수) 2
    assert out["flow_streak"].iloc[-1] == 2.0


def test_missing_flow_yields_zero_not_nan():
    dates = pd.date_range("2023-03-01", periods=10, freq="D")
    daily = pd.DataFrame({"date": dates, "volume": [100.0] * 10})
    flow = pd.DataFrame({"date": [], "foreign_net_vol": []})
    out = compute_flow_features(daily, flow)
    assert (out["flow_norm"] == 0.0).all()
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_flow_features.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현** — `scripts/feature_edge/flow_features.py`

```python
"""외국인 수급 피처 (foreign_flow). PIT: shift(1) 로 T-1 참조."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_flow_features(daily: pd.DataFrame, flow: pd.DataFrame) -> pd.DataFrame:
    d = daily[["date", "volume"]].copy()
    d["date"] = pd.to_datetime(d["date"])
    f = flow.copy()
    if len(f):
        f["date"] = pd.to_datetime(f["date"])
        f = f[["date", "foreign_net_vol"]]
    else:
        f = pd.DataFrame({"date": pd.to_datetime([]), "foreign_net_vol": []})
    m = d.merge(f, on="date", how="left")
    net = m["foreign_net_vol"].fillna(0.0).astype(float)
    net_lag = net.shift(1).fillna(0.0)                       # T-1 참조 (PIT)

    avg_vol = m["volume"].astype(float).shift(1).rolling(20).mean()
    out = pd.DataFrame(index=daily.index)
    out["date"] = m["date"].values
    out["flow_norm"] = (net_lag / avg_vol.replace(0, np.nan)).fillna(0.0)
    out["flow_cum5"] = net_lag.rolling(5).sum().fillna(0.0)
    out["flow_cum20"] = net_lag.rolling(20).sum().fillna(0.0)

    sign = (net_lag > 0).astype(int)
    # 연속 순매수 streak: 직전까지 연속 양수 개수
    grp = (sign == 0).cumsum()
    out["flow_streak"] = sign.groupby(grp).cumsum().astype(float).values
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_flow_features.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/flow_features.py tests/feature_edge/test_flow_features.py
git commit -m "feat(feature-edge): 외국인 수급 피처 (shift1 PIT)"
```

---

## Task 4: 기업이벤트(corp_events) 플래그

**Files:**
- Create: `scripts/feature_edge/event_features.py`
- Test: `tests/feature_edge/test_event_features.py`

설계: 입력 = 종목 일봉(date) + 이벤트 목록 `[(event_date, event_type), ...]`. 출력 = date 인덱스, `event_within_n`(N일내 이벤트 1/0), `days_to_event`(다음 이벤트까지 일수, 없으면 큰 값). PIT: "다음 이벤트까지"는 **이미 공시된 예정 이벤트**만 가정(증자/분할은 공시 후 예정일 존재) — 본 측정에선 단순화하여 event_date 기준 ±N 윈도우 플래그로 정의하고, 룩어헤드 경고를 리포트에 명시.

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_event_features.py`

```python
import pandas as pd
from scripts.feature_edge.event_features import compute_event_flags


def test_within_window_flag():
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    daily = pd.DataFrame({"date": dates})
    events = [(pd.Timestamp("2024-01-05"), "rights_issue")]
    out = compute_event_flags(daily, events, window=2)
    # 1/3~1/7 (±2일) 은 1, 그 밖은 0
    flags = dict(zip(out["date"], out["event_within_n"]))
    assert flags[pd.Timestamp("2024-01-03")] == 1
    assert flags[pd.Timestamp("2024-01-07")] == 1
    assert flags[pd.Timestamp("2024-01-08")] == 0
    assert flags[pd.Timestamp("2024-01-01")] == 0


def test_no_events_all_zero():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    out = compute_event_flags(pd.DataFrame({"date": dates}), [], window=3)
    assert (out["event_within_n"] == 0).all()
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_event_features.py -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/event_features.py`

```python
"""기업이벤트 플래그 (corp_events). 증자/분할/관리종목 ±window 윈도우."""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


def compute_event_flags(daily: pd.DataFrame, events: List[Tuple[pd.Timestamp, str]],
                        window: int = 3) -> pd.DataFrame:
    dates = pd.to_datetime(daily["date"]).reset_index(drop=True)
    flag = np.zeros(len(dates), dtype=int)
    ev_dates = [pd.Timestamp(e[0]) for e in events]
    for i, d in enumerate(dates):
        for ed in ev_dates:
            if abs((d - ed).days) <= window:
                flag[i] = 1
                break
    out = pd.DataFrame({"date": dates.values, "event_within_n": flag})
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_event_features.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/event_features.py tests/feature_edge/test_event_features.py
git commit -m "feat(feature-edge): 기업이벤트 플래그"
```

---

## Task 5: 시장 파생피처

**Files:**
- Create: `scripts/feature_edge/market_features.py`
- Test: `tests/feature_edge/test_market_features.py`

설계: 입력 = 지수 일봉 시계열(date, close). 출력 = date 인덱스 시장피처(추세·실현변동성 백분위). **breadth/dispersion 은 횡단면이라 패널 어셈블러(Task 6)에서 계산** — 이 모듈은 지수 단일 시계열 피처만.

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_market_features.py`

```python
import numpy as np
import pandas as pd
from scripts.feature_edge.market_features import compute_index_features


def test_index_trend_and_vol_percentile_pit():
    closes = [100 + i for i in range(300)]  # 단조상승
    idx = pd.DataFrame({"date": pd.date_range("2021-01-01", periods=300, freq="D"),
                        "close": closes})
    out = compute_index_features(idx)
    # 상승추세면 mkt_above_ma20 = 1
    assert out["mkt_above_ma20"].iloc[-1] == 1
    # 실현변동성 백분위는 0~1
    v = out["mkt_vol_pct"].iloc[-1]
    assert 0.0 <= v <= 1.0


def test_no_lookahead_index():
    closes = list(np.random.RandomState(0).randn(300).cumsum() + 100)
    idx = pd.DataFrame({"date": pd.date_range("2021-01-01", periods=300, freq="D"),
                        "close": closes})
    full = compute_index_features(idx)
    trunc = compute_index_features(idx.iloc[:250])
    assert np.allclose(full["mkt_ret20"].iloc[:250].fillna(-9),
                       trunc["mkt_ret20"].fillna(-9), atol=1e-9)
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_market_features.py -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/market_features.py`

```python
"""시장(지수) 파생피처. breadth/dispersion 은 패널 어셈블러에서 횡단면 계산."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_index_features(idx: pd.DataFrame) -> pd.DataFrame:
    c = idx["close"].astype(float)
    out = pd.DataFrame(index=idx.index)
    out["date"] = pd.to_datetime(idx["date"]).values
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    out["mkt_above_ma20"] = (c > ma20).astype(int)
    out["mkt_above_ma60"] = (c > ma60).astype(int)
    out["mkt_ret20"] = c / c.shift(20) - 1.0
    rv = c.pct_change().rolling(20).std()
    # 252일 롤링 백분위(과거만) — PIT
    out["mkt_vol_pct"] = rv.rolling(252, min_periods=60).apply(
        lambda w: (w.iloc[-1] >= w).mean(), raw=False)
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_market_features.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/market_features.py tests/feature_edge/test_market_features.py
git commit -m "feat(feature-edge): 시장 지수 파생피처 (PIT 백분위)"
```

---

## Task 6: 라벨러 (선행수익률 + 트리플배리어)

**Files:**
- Create: `scripts/feature_edge/labelers.py`
- Test: `tests/feature_edge/test_labelers.py`

설계: 입력 = 종목 일봉(date,open,high,low,close). 진입 = **T+1 시가**. 선행수익률 = `close[t+1+h]/open[t+1]-1`. 트리플배리어 = 진입가 대비 +up 선도달(=1)/−down 선도달(=0)/시간초과(=NaN 또는 마감수익 부호). 라벨은 미래봉을 쓰므로 **피처와 분리된 출력**이며, 측정 시 feature(t) ↔ label(t) 조인.

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_labelers.py`

```python
import numpy as np
import pandas as pd
from scripts.feature_edge.labelers import label_forward_returns, label_triple_barrier


def _df(o, h, l, c):
    n = len(c)
    return pd.DataFrame({"date": pd.date_range("2021-01-01", periods=n, freq="D"),
                         "open": o, "high": h, "low": l, "close": c})


def test_forward_return_entry_next_open():
    c = [100, 100, 110, 120, 130, 140]
    df = _df(o=c, h=c, l=c, c=c)
    out = label_forward_returns(df, horizons=(2,))
    # t=0: 진입 open[1]=100, exit close[1+2=3]=120 → 0.20
    assert np.isclose(out["fwd_2d"].iloc[0], 120 / 100 - 1, atol=1e-6)
    # 끝부분은 미래봉 부족 → NaN
    assert np.isnan(out["fwd_2d"].iloc[-1])


def test_triple_barrier_up_hit_first():
    # 진입 후 high 가 +10% 먼저 터치
    o = [100, 100, 100, 100, 100]
    h = [100, 100, 112, 100, 100]   # t=2 에 +12% 고가
    l = [100, 100, 100, 100, 100]
    c = [100, 100, 100, 100, 100]
    df = _df(o, h, l, c)
    out = label_triple_barrier(df, up=0.10, down=0.05, horizon=3)
    # t=0: 진입 open[1]=100, t=2 high=112 → up 선도달 → 1
    assert out["tb_up0.1_dn0.05_h3"].iloc[0] == 1


def test_triple_barrier_down_hit_first():
    o = [100, 100, 100, 100, 100]
    h = [100, 100, 100, 100, 100]
    l = [100, 94, 100, 100, 100]    # t=1 에 -6% 저가
    c = [100, 100, 100, 100, 100]
    df = _df(o, h, l, c)
    out = label_triple_barrier(df, up=0.10, down=0.05, horizon=3)
    assert out["tb_up0.1_dn0.05_h3"].iloc[0] == 0
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_labelers.py -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/labelers.py`

```python
"""결과 라벨러. 진입 = T+1 시가. (피처와 분리된 미래 outcome.)"""
from __future__ import annotations

import numpy as np
import pandas as pd


def label_forward_returns(df: pd.DataFrame, horizons=(5, 10, 20)) -> pd.DataFrame:
    o = df["open"].astype(float)
    c = df["close"].astype(float)
    entry = o.shift(-1)                       # T+1 시가
    out = pd.DataFrame(index=df.index)
    out["date"] = df["date"].values
    for h in horizons:
        exit_c = c.shift(-(1 + h))            # T+1+h 종가
        out[f"fwd_{h}d"] = exit_c / entry - 1.0
    return out


def label_triple_barrier(df: pd.DataFrame, up: float, down: float,
                         horizon: int) -> pd.DataFrame:
    o = df["open"].astype(float).values
    hi = df["high"].astype(float).values
    lo = df["low"].astype(float).values
    n = len(df)
    col = f"tb_up{up}_dn{down}_h{horizon}"
    res = np.full(n, np.nan)
    for t in range(n):
        e = t + 1
        if e >= n:
            continue
        entry = o[e]
        up_px, dn_px = entry * (1 + up), entry * (1 - down)
        label = np.nan
        end = min(e + horizon, n - 1)
        for j in range(e, end + 1):
            hit_up = hi[j] >= up_px
            hit_dn = lo[j] <= dn_px
            if hit_up and hit_dn:
                label = 0          # 같은 봉 양쪽 터치 → 보수적으로 손절 우선
                break
            if hit_up:
                label = 1
                break
            if hit_dn:
                label = 0
                break
        res[t] = label
    out = pd.DataFrame({"date": df["date"].values, col: res})
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_labelers.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/labelers.py tests/feature_edge/test_labelers.py
git commit -m "feat(feature-edge): 선행수익률+트리플배리어 라벨러 (T+1 진입)"
```

---

## Task 7: 측정 엔진 (IC·조건부기대값·커버리지·OOS·부트스트랩)

**Files:**
- Create: `scripts/feature_edge/metrics.py`
- Test: `tests/feature_edge/test_metrics.py`

설계: 패널(피처+라벨 조인된 long DataFrame, 컬럼 `date, stock_code, <features>, <labels>`)을 받아 피처별 측정값 산출.

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_metrics.py`

```python
import numpy as np
import pandas as pd
from scripts.feature_edge.metrics import (
    daily_ic, tercile_expectancy, coverage, oos_sign_consistent,
)


def _panel():
    # 피처 f 가 라벨 y 와 양의 상관(같은 값) → IC ≈ +1
    rows = []
    for d in pd.date_range("2021-01-01", periods=10, freq="D"):
        for k in range(20):
            rows.append({"date": d, "stock_code": f"S{k}", "f": float(k),
                         "y": float(k) + np.random.RandomState(k).randn() * 0.01})
    return pd.DataFrame(rows)


def test_daily_ic_positive_for_aligned_feature():
    p = _panel()
    ic = daily_ic(p, "f", "y")
    assert ic["ic_mean"] > 0.9
    assert "ic_ir" in ic


def test_tercile_expectancy_monotone():
    p = _panel()
    te = tercile_expectancy(p, "f", "y")
    # 상위 터사일 평균 y > 하위 터사일 평균 y
    assert te["top_mean"] > te["bottom_mean"]
    assert "spread" in te


def test_coverage_fraction():
    p = _panel()
    p.loc[p.index[:100], "f"] = np.nan
    cov = coverage(p, "f")
    assert 0.0 < cov < 1.0


def test_oos_sign_consistency():
    p = _panel()
    # train/test 둘다 양의 IC → 일치
    assert oos_sign_consistent(p, "f", "y", split="2021-01-05") is True
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_metrics.py -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/metrics.py`

```python
"""피처 엣지 측정. Spearman IC·터사일 기대값·커버리지·OOS·부트스트랩."""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def daily_ic(panel: pd.DataFrame, feat: str, label: str) -> Dict[str, float]:
    """일별 횡단면 Spearman IC 평균과 IR."""
    ics = []
    for _, g in panel.groupby("date"):
        sub = g[[feat, label]].dropna()
        if len(sub) >= 5:
            ic = sub[feat].rank().corr(sub[label].rank())
            if pd.notna(ic):
                ics.append(ic)
    if not ics:
        return {"ic_mean": float("nan"), "ic_ir": float("nan"), "n_days": 0}
    arr = np.array(ics)
    ir = arr.mean() / arr.std() if arr.std() > 0 else float("nan")
    return {"ic_mean": float(arr.mean()), "ic_ir": float(ir), "n_days": len(arr)}


def tercile_expectancy(panel: pd.DataFrame, feat: str, label: str) -> Dict[str, float]:
    sub = panel[[feat, label]].dropna()
    if len(sub) < 30:
        return {"top_mean": float("nan"), "bottom_mean": float("nan"), "spread": float("nan")}
    q = sub[feat].quantile([1/3, 2/3])
    bottom = sub[sub[feat] <= q.iloc[0]][label].mean()
    top = sub[sub[feat] >= q.iloc[1]][label].mean()
    return {"top_mean": float(top), "bottom_mean": float(bottom),
            "spread": float(top - bottom)}


def coverage(panel: pd.DataFrame, feat: str) -> float:
    return float(panel[feat].notna().mean())


def oos_sign_consistent(panel: pd.DataFrame, feat: str, label: str, split: str) -> bool:
    d = pd.to_datetime(panel["date"])
    train = panel[d <= split]
    test = panel[d > split]
    ic_tr = daily_ic(train, feat, label)["ic_mean"]
    ic_te = daily_ic(test, feat, label)["ic_mean"]
    if pd.isna(ic_tr) or pd.isna(ic_te):
        return False
    return (ic_tr > 0) == (ic_te > 0)


def bootstrap_ic_p05(panel: pd.DataFrame, feat: str, label: str,
                     n_iter: int = 1000, block: int = 21) -> float:
    """일별 IC 시계열에 블록 부트스트랩 → 평균 IC 분포의 p05.

    재사용: scripts.multiverse4_portfolio_analysis.block_bootstrap_metrics 와 동일한
    블록 부트스트랩 철학(여기선 IC 시계열 자체에 적용해 자급식 구현).
    """
    ics = []
    for dt, g in panel.groupby("date"):
        sub = g[[feat, label]].dropna()
        if len(sub) >= 5:
            ic = sub[feat].rank().corr(sub[label].rank())
            if pd.notna(ic):
                ics.append(ic)
    s = pd.Series(ics)
    if len(s) < block:
        return float("nan")
    rng = np.random.RandomState(42)
    means = []
    n_blocks = int(np.ceil(len(s) / block))
    for _ in range(n_iter):
        starts = rng.randint(0, len(s) - block + 1, n_blocks)
        sample = pd.concat([s.iloc[st:st + block] for st in starts])
        means.append(sample.mean())
    return float(np.percentile(means, 5))
```

> 룩어헤드 없음: 측정은 (이미 PIT인 피처) ↔ (라벨)의 정적 조인. `oos_sign_consistent` 의 split 은 §config.OOS_SPLIT.

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_metrics.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/metrics.py tests/feature_edge/test_metrics.py
git commit -m "feat(feature-edge): 측정엔진 (IC·터사일·커버리지·OOS·부트스트랩)"
```

---

## Task 8: 전략별 진입신호 생성기

**Files:**
- Create: `scripts/feature_edge/signals.py`
- Test: `tests/feature_edge/test_signals.py`

설계: 기존 `build_adapter(strategy_name)` 로 8전략 스크리너 어댑터를 얻고, 각 (stock, date)에서 어댑터의 `match(trailing_df, params)` 를 호출해 신호일을 생성. `match` 가 None 아니면 진입신호. **어댑터 재사용 = 라이브 룰과 동일.** DB 의존을 끊기 위해 일봉 공급자를 주입 가능하게 한다(테스트는 가짜 공급자).

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_signals.py`

```python
import pandas as pd
from scripts.feature_edge.signals import generate_entry_signals


class _FakeAdapter:
    strategy_name = "fake"
    lookback_days = 5

    def default_params(self):
        return {"thr": 100.0}

    def match(self, df, params):
        # 마지막 종가 > thr 이면 신호
        if float(df["close"].iloc[-1]) > params["thr"]:
            return (1.0, "above thr")
        return None


def test_generates_signal_dates():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    daily = pd.DataFrame({"date": dates, "open": [99]*6, "high":[99]*6,
                          "low":[99]*6, "close": [99, 99, 101, 99, 102, 99],
                          "volume":[1]*6})
    supplier = {"S1": daily}
    sigs = generate_entry_signals(_FakeAdapter(), ["S1"], supplier, min_bars=2)
    got = sorted(d.strftime("%Y-%m-%d") for d in sigs["date"])
    assert "2024-01-03" in got  # close=101
    assert "2024-01-05" in got  # close=102
    assert "2024-01-02" not in got
    assert (sigs["strategy"] == "fake").all()
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_signals.py -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/signals.py`

```python
"""전략별 진입신호 생성 (기존 스크리너 어댑터 재사용 = 라이브 룰 동일)."""
from __future__ import annotations

from typing import Dict, List

import pandas as pd


def generate_entry_signals(adapter, stock_codes: List[str],
                           daily_supplier: Dict[str, pd.DataFrame],
                           min_bars: int = 25) -> pd.DataFrame:
    """각 종목·각 일자에서 adapter.match(trailing) 호출 → 신호일 long DF.

    daily_supplier: {stock_code -> 오름차순 일봉 DataFrame(date,open..close,volume)}.
    반환 컬럼: date, stock_code, strategy, score.
    """
    params = adapter.default_params()
    rows = []
    for code in stock_codes:
        df = daily_supplier.get(code)
        if df is None or len(df) < min_bars:
            continue
        df = df.reset_index(drop=True)
        for i in range(min_bars - 1, len(df)):
            window = df.iloc[: i + 1]
            try:
                res = adapter.match(window, params)
            except Exception:
                res = None
            if res is not None:
                score = res[0] if isinstance(res, (tuple, list)) else float(res)
                rows.append({"date": df["date"].iloc[i], "stock_code": code,
                             "strategy": adapter.strategy_name, "score": float(score)})
    return pd.DataFrame(rows, columns=["date", "stock_code", "strategy", "score"])
```

> 라이브 어댑터 인스턴스는 `build_adapter(name)` 로 생성(Task 9 오케스트레이터). `match` 가 quant 직접조회를 하는 일부 어댑터(envelope)는 오케스트레이터에서 quant 공급자를 주입하거나 신호 생성을 스킵하고 리포트에 명시.

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_signals.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/signals.py tests/feature_edge/test_signals.py
git commit -m "feat(feature-edge): 전략별 진입신호 생성기 (어댑터 재사용)"
```

---

## Task 9: 패널 어셈블러 (parquet)

**Files:**
- Create: `scripts/feature_edge/panel.py`
- Test: `tests/feature_edge/test_panel.py`

설계: 유니버스(stock_code 리스트) + 일봉 공급자 + 지수 공급자 + 수급/이벤트 공급자를 받아 종목별 피처를 계산하고 long 패널(date, stock_code, features...)로 결합. 횡단면 집계(breadth, dispersion, 횡단면 vol 백분위, 상대강도)를 추가. DB I/O 는 별도 로더 함수로 분리(주입 가능). **테스트는 가짜 공급자로 DB 없이.**

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_panel.py`

```python
import numpy as np
import pandas as pd
from scripts.feature_edge.panel import assemble_panel


def _stock_df(seed):
    rng = np.random.RandomState(seed)
    c = (rng.randn(80).cumsum() + 200).clip(min=10)
    dates = pd.date_range("2021-01-01", periods=80, freq="D")
    return pd.DataFrame({"date": dates, "open": c, "high": c*1.01,
                         "low": c*0.99, "close": c, "volume": rng.randint(1e3,1e4,80)})


def test_assemble_panel_shape_and_relative_strength():
    codes = ["A", "B", "C"]
    daily = {k: _stock_df(i) for i, k in enumerate(codes)}
    index_df = pd.DataFrame({"date": daily["A"]["date"],
                             "close": np.linspace(300, 400, 80)})
    panel = assemble_panel(codes, daily, index_df, flow_supplier={}, event_supplier={})
    assert {"date", "stock_code", "returns_20d", "mkt_ret20",
            "rel_strength", "breadth"}.issubset(panel.columns)
    # 상대강도 = 종목 returns_20d - 지수 returns_20d (정의 검증)
    row = panel[(panel["stock_code"] == "A")].dropna(subset=["rel_strength"]).iloc[-1]
    assert np.isclose(row["rel_strength"], row["returns_20d"] - row["mkt_ret20"], atol=1e-9)


def test_breadth_is_cross_sectional_fraction():
    codes = ["A", "B", "C"]
    daily = {k: _stock_df(i) for i, k in enumerate(codes)}
    index_df = pd.DataFrame({"date": daily["A"]["date"], "close": np.ones(80)*300})
    panel = assemble_panel(codes, daily, index_df, flow_supplier={}, event_supplier={})
    b = panel.dropna(subset=["breadth"])["breadth"]
    assert ((b >= 0) & (b <= 1)).all()
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_panel.py -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/panel.py`

```python
"""피처 패널 어셈블러. 종목별 피처 + 횡단면 집계 → long DataFrame."""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from scripts.feature_edge.price_features import compute_price_features
from scripts.feature_edge.market_features import compute_index_features
from scripts.feature_edge.flow_features import compute_flow_features
from scripts.feature_edge.event_features import compute_event_flags


def assemble_panel(stock_codes: List[str],
                   daily_supplier: Dict[str, pd.DataFrame],
                   index_df: pd.DataFrame,
                   flow_supplier: Dict[str, pd.DataFrame],
                   event_supplier: Dict[str, list]) -> pd.DataFrame:
    mkt = compute_index_features(index_df)
    parts = []
    for code in stock_codes:
        df = daily_supplier.get(code)
        if df is None or len(df) < 21:
            continue
        df = df.reset_index(drop=True)
        feat = compute_price_features(df)
        flow = compute_flow_features(df, flow_supplier.get(code, pd.DataFrame(
            {"date": [], "foreign_net_vol": []})))
        ev = compute_event_flags(df, event_supplier.get(code, []))
        m = feat.merge(flow.drop(columns=["date"]).set_index(feat.index),
                       left_index=True, right_index=True)
        m = m.merge(ev.drop(columns=["date"]).set_index(feat.index),
                    left_index=True, right_index=True)
        m["stock_code"] = code
        parts.append(m)
    if not parts:
        return pd.DataFrame()
    panel = pd.concat(parts, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    # 시장피처 조인
    mkt["date"] = pd.to_datetime(mkt["date"])
    panel = panel.merge(mkt, on="date", how="left")
    panel["rel_strength"] = panel["returns_20d"] - panel["mkt_ret20"]

    # 횡단면 집계: breadth(=ma20_dist>0 비율), dispersion(returns_20d 표준편차), vol 백분위
    panel["breadth"] = panel.groupby("date")["ma20_dist"].transform(
        lambda s: (s > 0).mean())
    panel["dispersion"] = panel.groupby("date")["returns_20d"].transform("std")
    panel["vol_xs_pct"] = panel.groupby("date")["vol_20d"].rank(pct=True)
    return panel
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_panel.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/panel.py tests/feature_edge/test_panel.py
git commit -m "feat(feature-edge): 패널 어셈블러 (종목피처+횡단면 집계)"
```

---

## Task 10: DB 로더 (실데이터 공급자)

**Files:**
- Create: `scripts/feature_edge/loaders.py`
- Test: `tests/feature_edge/test_loaders.py` (DB 연결 필요 → `@pytest.mark.integration`, 기본 스킵)

설계: 실제 DB에서 공급자 dict 를 구성. `QuantDailyReader`(일봉/유니버스), `robotrader_quant.foreign_flow`, `robotrader.corp_events`, 지수 일봉. 단위테스트는 가짜를 쓰고, 통합테스트는 마커로 분리(CI 기본 스킵).

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_loaders.py`

```python
import pytest
from scripts.feature_edge import loaders


def test_loader_functions_exist():
    assert hasattr(loaders, "load_universe")
    assert hasattr(loaders, "load_daily_supplier")
    assert hasattr(loaders, "load_flow_supplier")
    assert hasattr(loaders, "load_event_supplier")
    assert hasattr(loaders, "load_index_df")


@pytest.mark.integration
def test_load_universe_returns_codes():
    codes = loaders.load_universe("2026-06-12")
    assert isinstance(codes, list) and len(codes) > 100
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_loaders.py::test_loader_functions_exist -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/loaders.py`

```python
"""실데이터 공급자 로더 (읽기전용). 단위테스트는 가짜 공급자, 여기는 통합경로."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Dict, List

import pandas as pd
import psycopg2

from db.quant_daily_reader import QuantDailyReader
from scripts.feature_edge import config


@contextmanager
def _conn(dbname: str):
    c = psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "localhost"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        dbname=dbname, user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"))
    try:
        yield c
    finally:
        c.close()


def load_universe(scan_date: str) -> List[str]:
    rows = QuantDailyReader().get_universe_snapshot(scan_date)
    return [r["stock_code"] for r in rows
            if r["trading_value"] >= config.UNIVERSE_MIN_TRADING_VALUE]


def load_daily_supplier(codes: List[str], end_date: str, days: int = 1500
                        ) -> Dict[str, pd.DataFrame]:
    r = QuantDailyReader()
    return {c: r.get_daily_prices(c, end_date=end_date, days=days) for c in codes}


def load_flow_supplier(codes: List[str]) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    with _conn("robotrader_quant") as conn:
        for c in codes:
            df = pd.read_sql(
                "SELECT date, foreign_net_vol FROM foreign_flow "
                "WHERE stock_code=%s ORDER BY date", conn, params=(c,))
            if len(df):
                out[c] = df
    return out


def load_event_supplier(codes: List[str]) -> Dict[str, list]:
    out: Dict[str, list] = {}
    with _conn("robotrader") as conn:
        cur = conn.cursor()
        for c in codes:
            cur.execute("SELECT event_date, event_type FROM corp_events "
                        "WHERE stock_code=%s", (c,))
            ev = [(pd.Timestamp(d), t) for d, t in cur.fetchall()]
            if ev:
                out[c] = ev
    return out


def load_index_df(index_code: str = None) -> pd.DataFrame:
    index_code = index_code or config.KOSPI_INDEX_CODE
    r = QuantDailyReader()
    df = r.get_daily_prices(index_code, end_date=config.PERIOD_END, days=2000)
    return df[["date", "close"]] if len(df) else pd.DataFrame(
        {"date": [], "close": []})
```

> 주의: `corp_events.event_date` 실제 컬럼명을 구현 시 `\d corp_events` 로 확인(스키마 미확정 시 `SELECT * ... LIMIT 1` 로 컬럼 파악 후 보정). 지수 코드가 daily_prices 에 종목처럼 적재됐는지 확인하고, 아니면 `market_index`/별도 소스로 보정하되 **frozen 2026-02-12 주의**(메모리), PIT 위해 daily_prices KOSPI 합성 폴백.

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_loaders.py::test_loader_functions_exist -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/loaders.py tests/feature_edge/test_loaders.py
git commit -m "feat(feature-edge): 실데이터 공급자 로더 (읽기전용)"
```

---

## Task 11: 오케스트레이터 + 리포트

**Files:**
- Create: `scripts/feature_edge/run_edge_lab.py`
- Test: `tests/feature_edge/test_run_edge_lab.py`

설계: (1) 패널 빌드 → parquet 저장, (2) 라벨 조인, (3) 전략 진입신호 생성, (4) 측정(전 패널 + 전략조건부), (5) `edge_report.md` 작성. `--stage`, `--limit`(테스트용 종목수 제한). 측정·리포트 조립 로직은 순수함수 `build_edge_table(panel_with_labels, features, labels)` 로 분리해 테스트.

- [ ] **Step 1: 실패 테스트 작성** — `tests/feature_edge/test_run_edge_lab.py`

```python
import numpy as np
import pandas as pd
from scripts.feature_edge.run_edge_lab import build_edge_table


def test_build_edge_table_ranks_features():
    rows = []
    rng = np.random.RandomState(0)
    for d in pd.date_range("2021-01-01", periods=40, freq="D"):
        for k in range(30):
            rows.append({"date": d, "stock_code": f"S{k}",
                         "good": float(k), "noise": rng.randn(),
                         "fwd_5d": float(k) * 0.001})
    panel = pd.DataFrame(rows)
    tbl = build_edge_table(panel, features=["good", "noise"], labels=["fwd_5d"])
    assert set(["feature", "label", "ic_mean", "ic_ir", "spread",
                "coverage", "bootstrap_p05", "oos_consistent"]).issubset(tbl.columns)
    good = tbl[(tbl.feature == "good") & (tbl.label == "fwd_5d")].iloc[0]
    noise = tbl[(tbl.feature == "noise") & (tbl.label == "fwd_5d")].iloc[0]
    assert good["ic_mean"] > noise["ic_mean"]
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/feature_edge/test_run_edge_lab.py -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `scripts/feature_edge/run_edge_lab.py`

```python
"""Feature Edge Lab 오케스트레이터. 패널→라벨→측정→리포트 (측정 전용)."""
from __future__ import annotations

import argparse
import os
from typing import List

import pandas as pd

from scripts.feature_edge import config
from scripts.feature_edge.metrics import (
    daily_ic, tercile_expectancy, coverage, oos_sign_consistent, bootstrap_ic_p05,
)


def build_edge_table(panel: pd.DataFrame, features: List[str],
                     labels: List[str]) -> pd.DataFrame:
    rows = []
    for label in labels:
        for feat in features:
            ic = daily_ic(panel, feat, label)
            te = tercile_expectancy(panel, feat, label)
            rows.append({
                "feature": feat, "label": label,
                "ic_mean": ic["ic_mean"], "ic_ir": ic["ic_ir"], "n_days": ic["n_days"],
                "spread": te["spread"],
                "coverage": coverage(panel, feat),
                "bootstrap_p05": bootstrap_ic_p05(panel, feat, label),
                "oos_consistent": oos_sign_consistent(panel, feat, label, config.OOS_SPLIT),
            })
    tbl = pd.DataFrame(rows)
    return tbl.sort_values(["label", "ic_mean"], ascending=[True, False]).reset_index(drop=True)


def _passes_gate(r) -> bool:
    return (pd.notna(r["bootstrap_p05"]) and r["bootstrap_p05"] > 0
            and bool(r["oos_consistent"]) and r["coverage"] >= config.COVERAGE_MIN)


def write_report(tbl: pd.DataFrame, path: str, note: str = "") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# Feature Edge Report (Phase 0 — 측정 전용)", "", note, "",
             "판정 게이트: bootstrap_p05>0 ∧ oos_consistent ∧ coverage≥%.2f" % config.COVERAGE_MIN,
             "", "## 엣지 후보 (게이트 통과)", ""]
    passed = tbl[tbl.apply(_passes_gate, axis=1)]
    lines.append(passed.to_markdown(index=False) if len(passed) else "_(통과 피처 없음)_")
    lines += ["", "## 전체 측정표", "", tbl.to_markdown(index=False),
              "", "## 다중검정 주의",
              f"- 측정 피처×라벨 조합 수: {len(tbl)} — 우연 통과 가능, p05·OOS 동시충족으로 보수화."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():  # pragma: no cover (통합 실행 경로)
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="테스트용 종목수 제한(0=전체)")
    ap.add_argument("--stage", choices=["singles", "interactions"], default="singles")
    args = ap.parse_args()

    from scripts.feature_edge import loaders, signals
    from scripts.feature_edge.panel import assemble_panel
    from scripts.feature_edge.labelers import label_forward_returns

    codes = loaders.load_universe(config.PERIOD_END)
    if args.limit:
        codes = codes[: args.limit]
    daily = loaders.load_daily_supplier(codes, config.PERIOD_END)
    index_df = loaders.load_index_df()
    flow = loaders.load_flow_supplier(codes)
    events = loaders.load_event_supplier(codes)

    panel = assemble_panel(codes, daily, index_df, flow, events)
    os.makedirs(os.path.dirname(config.PANEL_PATH), exist_ok=True)
    panel.to_parquet(config.PANEL_PATH)

    # 라벨 조인 (종목별 forward returns)
    lab_parts = []
    for c in codes:
        df = daily.get(c)
        if df is not None and len(df) > max(config.FWD_HORIZONS) + 2:
            lr = label_forward_returns(df, config.FWD_HORIZONS)
            lr["stock_code"] = c
            lab_parts.append(lr)
    labels_df = pd.concat(lab_parts, ignore_index=True)
    labels_df["date"] = pd.to_datetime(labels_df["date"])
    merged = panel.merge(labels_df, on=["date", "stock_code"], how="inner")

    feat_cols = [c for c in panel.columns if c not in ("date", "stock_code")]
    lab_cols = [f"fwd_{h}d" for h in config.FWD_HORIZONS]
    tbl = build_edge_table(merged, feat_cols, lab_cols)
    write_report(tbl, config.REPORT_PATH, note="전 패널 대상 선행수익률 IC 측정.")
    print(f"[edge-lab] 패널 {config.PANEL_PATH} / 리포트 {config.REPORT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/feature_edge/test_run_edge_lab.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/feature_edge/run_edge_lab.py tests/feature_edge/test_run_edge_lab.py
git commit -m "feat(feature-edge): 오케스트레이터 + 엣지 리포트 (게이트 판정)"
```

---

## Task 12: 통합 스모크 실행 + 전체 회귀

**Files:**
- Modify: (없음 — 실행/검증만)

- [ ] **Step 1: 단위 회귀 전체 통과 확인**

Run: `pytest tests/feature_edge/ -v`
Expected: 모든 단위테스트 PASS (통합 마커 제외)

- [ ] **Step 2: 소규모 실데이터 스모크 (종목 30개 제한)**

Run: `python -m scripts.feature_edge.run_edge_lab --limit 30`
Expected: `reports/discovery/feature_edge/feature_panel.parquet` 생성 + `edge_report.md` 생성, 예외 없이 종료. (실패 시 loaders 의 컬럼명/지수소스 보정 — Task 10 주석 참고)

- [ ] **Step 3: 리포트 sanity 확인**

`edge_report.md` 를 열어 (a) 게이트 통과 피처 표가 생성됐는지, (b) returns_20d·rel_strength 등 가격피처 IC 가 합리적 범위(|IC|<0.2)인지, (c) 커버리지가 가격피처≈1.0 / 수급피처<0.5 로 표기되는지 확인.

- [ ] **Step 4: 커밋 (산출물 제외, 코드/문서만)**

```bash
git add scripts/feature_edge/ tests/feature_edge/
git commit -m "test(feature-edge): 통합 스모크 + 전체 회귀 통과"
```

> 주의: `reports/discovery/feature_edge/*.parquet` 등 산출물은 커밋하지 않는다(`.gitignore` 확인, 필요시 추가).

---

## 후속(이 플랜 범위 밖, 측정 결과 후 결정)
- 교차항 6선 측정(`--stage interactions`): 단일 통과분 한정 곱 피처 추가 + 보수적 p05.
- 일중파생 피처(minute_candles): 계산비용 큼 → 별도 플랜.
- bespoke 청산 라벨(각 전략 실제 exit 어댑터) 정밀화.
- 결과에 따라 A(전략별 필터)/B(컴포짓 스코어)/C(시장 게이트) 중 택1 → 각각 별도 spec.

---

## Self-Review 메모
- Spec 커버리지: 패널빌더(T2~5,9)·라벨러(T6)·측정엔진(T7)·전략신호(T8)·로더(T10)·오케스트레이터/리포트(T11) = §4 컴포넌트 전부 매핑. PIT 규약(§6)은 각 피처/라벨 테스트의 no-lookahead 케이스로 검증. 반-과적합(§7) = metrics 게이트 + 리포트 다중검정 노트. VKOSPI 제외(§2)·parquet(§8) 반영.
- 미커버(의도적 후속): 교차항·일중파생·bespoke 청산·팩터/재무 피처(좁은 커버리지) — 후속 절 명시.
- 타입 일관성: 공급자 dict[str,DataFrame], 피처 함수는 date 인덱스 long, 패널 컬럼 date/stock_code 고정, metrics 는 (panel,feat,label) 시그니처 통일.
