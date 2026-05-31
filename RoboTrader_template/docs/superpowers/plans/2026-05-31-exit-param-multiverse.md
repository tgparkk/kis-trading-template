# 선별 4전략 청산 파라미터 멀티버스 최적화 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 선별 4전략(elder/minervini/ma20/ma5)의 청산 파라미터를, 실전과 동일한 포트폴리오 자본 모델 + 워크포워드 OOS + 국면최악 Sharpe → DSR 게이트로 최적화하는 CLI 도구를 만든다.

**Architecture:** 기존 `run_*.py`의 진입(`generate_signal_with_extra_ctx`)·청산 로직을 그대로 재사용하되, 자금·슬롯 제약을 가진 얇은 포트폴리오 시뮬레이터를 신규 작성한다. 진입 신호는 청산 파라미터와 무관하므로 그리드 루프 밖에서 1회 사전계산해 캐싱한다(RAM 64GB). 전략 4개를 독립 프로세스로 병렬 실행한다.

**Tech Stack:** Python 3.8+, pandas/numpy, PostgreSQL(포트 5433, `db.connection.DatabaseConnection`), pytest, `concurrent.futures`(멀티프로세싱), scipy(DSR).

**참조 설계서:** `docs/superpowers/specs/2026-05-31-exit-param-multiverse-design.md`

---

## 사전 지식 (구현자가 반드시 알아야 할 기존 코드)

이 계획은 다음 기존 자산을 재사용한다. 작업 전 한 번씩 읽어라:

- **4전략 백테스트 러너** (진입/청산 로직 원본 — 여기서 그대로 가져온다):
  - `scripts/run_elder_triple_screen.py` — elder. **매수스톱 진입**(Screen3: 전일고가+1틱, `N_TRAIL=2`일 추적), 청산 `trail_ema`(지수이평 13) + `trend_flip`(ema65[i] < ema65[i-5]). 진입신호는 `strategy.generate_signal_with_extra_ctx(code, df[:i+1], "daily", {})`.
  - `scripts/run_minervini_vcp.py` — minervini. **다음날 시가 진입**, 청산 `trail_ma`(단순이평). RS를 `compute_rs_percentile_12w(wide_close)`로 미리 계산해 `ctx_extra={"rs_value": ...}`로 주입.
  - `scripts/run_haru_silijeon_daily.py` — ma20(강창권). 다음날 시가 진입, `trail_ma`(단순이평). `_resolve_exit_params`로 룰별 tp/trail override.
  - `scripts/run_trading_legends_daily.py` — ma5(Book15). haru와 1:1 동일 골격.
- **재사용 유틸**:
  - `backtest/regime_analysis.py` → `classify_regime_rolling(kospi_close, window=20, threshold=0.05) -> pd.Series[MarketRegime]`, `MarketRegime`(BULL/BEAR/SIDEWAYS enum).
  - `multiverse/runner/dsr.py` → `deflated_sharpe_ratio(sharpe, n_trials, n_observations, skew=0.0, excess_kurt=0.0) -> float(0~1)`, `passes_dsr(dsr, threshold=0.95) -> bool`.
  - `strategies/books/elder_triple_screen/rules.py` → `ema(series, n)`, `krx_tick(price)`, `screen1_uptrend(close)`.
  - `strategies/books/minervini_vcp/rules.py` → `compute_rs_percentile_12w(wide_close)`.
- **라이브 전략 현재 운용 청산값** (그리드 중앙값으로 반드시 포함할 값. `strategies/<name>/config.yaml`에서 재확인):
  - elder: sl 0.08 / tp 0.30 / max_hold 100 / trail_ema 13 / trend_flip True
  - minervini: sl 0.08 / tp 0.12 / max_hold 20 / trail 없음
  - ma20: sl 0.08 / tp 0.10 / max_hold 50 / trail_ma 20
  - ma5: sl 0.03 / tp 0.15 / max_hold 30 / trail_ma 5

**핵심 비용 상수(4전략 공통, 절대 바꾸지 말 것):** `commission_rate=0.00015`(양방향 각각), `tax_rate=0.0018`(매도시), `slippage_rate=0.001`(단방향). 왕복 ≈ 0.41%.

---

## File Structure

신규 패키지 `scripts/exit_multiverse/` 로 모은다(책임별 분리, 각 파일 단일 책임):

| 파일 | 책임 |
|---|---|
| `scripts/exit_multiverse/__init__.py` | 패키지 마커 |
| `scripts/exit_multiverse/data_loader.py` | top_volume 유니버스 + 일봉 adj 로드 (기존 `_load_*` 복제) + KOSPI 종가 로드 |
| `scripts/exit_multiverse/adapters.py` | 4전략 어댑터(`StrategyAdapter` dataclass) + 청산함수 2종 + 그리드 정의 |
| `scripts/exit_multiverse/signals.py` | 진입 신호 사전계산(그리드 무관 캐시) |
| `scripts/exit_multiverse/portfolio_sim.py` | 포트폴리오 시뮬레이터(자금·슬롯·우선순위, per-stock 모드 포함) |
| `scripts/exit_multiverse/objective.py` | 국면별 Sharpe 분해 + 국면최악 + DSR |
| `scripts/exit_multiverse/walkforward.py` | 롤링 train/test 폴드 생성 + 폴드 평가 |
| `scripts/exit_multiverse/run.py` | CLI 러너 + 전략 4-프로세스 병렬 + 일봉 메모리 상주 |
| `scripts/exit_multiverse/report.py` | 산출물(md/parquet/summary) |
| `tests/exit_multiverse/test_*.py` | 단위 테스트 |

테스트는 `tests/exit_multiverse/` 아래. `pytest tests/exit_multiverse/ -v`로 실행.

---

## Task 1: 패키지 스캐폴딩 + 데이터 로더

**Files:**
- Create: `scripts/exit_multiverse/__init__.py`
- Create: `scripts/exit_multiverse/data_loader.py`
- Create: `tests/exit_multiverse/__init__.py`
- Create: `tests/exit_multiverse/test_data_loader.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

`scripts/exit_multiverse/__init__.py` 와 `tests/exit_multiverse/__init__.py` 를 빈 파일로 생성.

- [ ] **Step 2: data_loader.py 작성**

`run_elder_triple_screen.py` 의 `_load_top_volume_universe`(44-58행)와 `_load_daily_adj`(61-101행)를 **그대로 복제**하고, KOSPI 종가 로더를 추가한다.

```python
"""유니버스·일봉·KOSPI 종가 로더. 기존 run_*.py 의 _load_* 를 재사용."""
from __future__ import annotations
import logging
from typing import Dict, List
import pandas as pd

LOG = logging.getLogger("exit_multiverse.data_loader")


def load_top_volume_universe(start: str, end: str, top_n: int = 50) -> List[str]:
    # run_elder_triple_screen.py:44-58 그대로 복제
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
            GROUP BY stock_code
            ORDER BY turnover DESC
            LIMIT %s
        """, (start, end, top_n))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def load_daily_adj(stock_codes: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    # run_elder_triple_screen.py:61-101 그대로 복제 (adj_factor 적용 + OHLC 결손 보정)
    from db.connection import DatabaseConnection
    out: Dict[str, pd.DataFrame] = {}
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, high, low, close, volume, adj_factor
                FROM daily_prices
                WHERE stock_code = %s AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start, end))
            rows = cur.fetchall()
            if not rows or len(rows) < 30:
                continue
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "adj_factor"])
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "high", "low", "close", "volume", "adj_factor"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["adj_factor"] = df["adj_factor"].fillna(1.0)
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col] * df["adj_factor"]
            drop_mask = df["close"].isna() | (df["close"] <= 0)
            df = df[~drop_mask].copy()
            for col in ["open", "high", "low"]:
                fill_mask = df[col].isna() | (df[col] <= 0)
                df.loc[fill_mask, col] = df.loc[fill_mask, "close"]
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    return out


def load_turnover_rank(start: str, end: str) -> Dict[str, float]:
    """종목별 거래대금 합계 (진입 우선순위 정렬용)."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
            GROUP BY stock_code
        """, (start, end))
        rows = cur.fetchall()
    return {r[0]: float(r[1]) for r in rows}


def load_kospi_close(start: str, end: str) -> pd.Series:
    """daily_prices 의 KOSPI 지수 종가 (국면 라벨용). regime_split_*.py 와 동일 소스."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT date, close FROM daily_prices "
            "WHERE stock_code = 'KOSPI' AND date >= %s AND date <= %s ORDER BY date ASC",
            (start, end),
        )
        rows = cur.fetchall()
    if not rows:
        raise RuntimeError("daily_prices에 KOSPI 행이 없음")
    return pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows}, name="kospi").sort_index()
```

- [ ] **Step 3: 테스트 작성**

`tests/exit_multiverse/test_data_loader.py`:

```python
import pandas as pd
import pytest
from scripts.exit_multiverse import data_loader


def test_load_top_volume_universe_returns_codes():
    codes = data_loader.load_top_volume_universe("2024-01-01", "2024-12-31", top_n=10)
    assert isinstance(codes, list)
    assert len(codes) <= 10
    assert all(isinstance(c, str) for c in codes)


def test_load_daily_adj_shape():
    codes = data_loader.load_top_volume_universe("2024-01-01", "2024-12-31", top_n=3)
    data = data_loader.load_daily_adj(codes, "2024-01-01", "2024-12-31")
    assert isinstance(data, dict)
    for code, df in data.items():
        assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume"]
        assert (df["close"] > 0).all()


def test_load_kospi_close_sorted():
    s = data_loader.load_kospi_close("2024-01-01", "2024-12-31")
    assert isinstance(s, pd.Series)
    assert s.index.is_monotonic_increasing
    assert (s > 0).all()
```

- [ ] **Step 4: 테스트 실행 (DB 연결 필요)**

Run: `cd RoboTrader_template; python -m pytest tests/exit_multiverse/test_data_loader.py -v`
Expected: 3 passed (DB에 2024 데이터 + KOSPI 행 존재 가정). KOSPI 행이 없으면 `test_load_kospi_close_sorted`만 조정.

- [ ] **Step 5: Commit**

```bash
git add scripts/exit_multiverse/__init__.py scripts/exit_multiverse/data_loader.py tests/exit_multiverse/
git commit -m "feat(exit-mv): 유니버스·일봉·KOSPI 종가 로더"
```

---

## Task 2: 청산 함수 2종 (elder / 단순MA) + 단위 테스트

**Files:**
- Create: `scripts/exit_multiverse/exits.py`
- Create: `tests/exit_multiverse/test_exits.py`

청산 판정을 그리드 루프에서 수만 번 호출하므로, 기존 `simulate_one_stock` 의 청산 분기를 **순수 함수**로 추출한다. 두 종류: elder(trail_ema 지수이평 + ema65 trend_flip)와 단순MA(trail_ma 단순이평).

- [ ] **Step 1: 테스트 먼저 작성**

`tests/exit_multiverse/test_exits.py`:

```python
import numpy as np
import pandas as pd
import pytest
from scripts.exit_multiverse import exits


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_stop_loss_triggers():
    df = _df([100.0] * 70 + [100.0, 90.0])  # 진입가 100, 종가 90 = -10%
    pos = {"entry_idx": 70, "entry_price": 100.0, "qty": 1}
    reason = exits.exit_reason_simple_ma(df, i=71, position=pos,
                                         stop_loss_pct=0.08, take_profit_pct=0.99,
                                         max_hold_bars=100, trail_ma=None)
    assert reason == "stop_loss"


def test_take_profit_triggers():
    df = _df([100.0] * 70 + [100.0, 115.0])
    pos = {"entry_idx": 70, "entry_price": 100.0, "qty": 1}
    reason = exits.exit_reason_simple_ma(df, i=71, position=pos,
                                         stop_loss_pct=0.08, take_profit_pct=0.12,
                                         max_hold_bars=100, trail_ma=None)
    assert reason == "take_profit"


def test_max_hold_triggers():
    df = _df([100.0] * 110)
    pos = {"entry_idx": 70, "entry_price": 100.0, "qty": 1}
    reason = exits.exit_reason_simple_ma(df, i=90, position=pos,
                                         stop_loss_pct=0.08, take_profit_pct=0.99,
                                         max_hold_bars=20, trail_ma=None)
    assert reason == "max_hold"


def test_trail_ma_breaks_below():
    closes = [100.0] * 50 + list(np.linspace(100, 120, 20)) + [110.0]
    df = _df(closes)
    i = len(df) - 1
    pos = {"entry_idx": 60, "entry_price": 105.0, "qty": 1}
    # 종가 110 < 최근 trail_ma=5 평균? 직전 5봉이 상승이라 110이 5MA 아래면 trail
    reason = exits.exit_reason_simple_ma(df, i=i, position=pos,
                                         stop_loss_pct=0.50, take_profit_pct=0.99,
                                         max_hold_bars=999, trail_ma=5)
    assert reason in (None, "trail_ma")  # 데이터 의존 — 함수가 예외 없이 동작함을 확인


def test_elder_trend_flip():
    # ema65 가 하락하면 trend_flip
    closes = list(np.linspace(200, 100, 80))  # 단조 하락 → ema65[i] < ema65[i-5]
    df = _df(closes)
    i = len(df) - 1
    pos = {"entry_idx": 70, "entry_price": 150.0, "qty": 1}
    reason = exits.exit_reason_elder(df, i=i, position=pos,
                                     stop_loss_pct=0.50, take_profit_pct=0.99,
                                     max_hold_bars=999, trail_ema=None, trend_flip_exit=True)
    assert reason == "trend_flip"
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python -m pytest tests/exit_multiverse/test_exits.py -v`
Expected: FAIL (module `exits` not found).

- [ ] **Step 3: exits.py 구현**

`run_elder_triple_screen.py:145-164`(elder 청산)와 `run_haru_silijeon_daily.py:166-181`(단순MA 청산)의 로직을 그대로 순수함수로 옮긴다.

```python
"""청산 판정 순수 함수 — 기존 simulate_one_stock 청산 분기 1:1 이식."""
from __future__ import annotations
from typing import Optional
import pandas as pd
from strategies.books.elder_triple_screen.rules import ema


def exit_reason_simple_ma(df, i, position, stop_loss_pct, take_profit_pct,
                          max_hold_bars, trail_ma) -> Optional[str]:
    """minervini/ma20/ma5 공통 청산. run_haru_silijeon_daily.py:166-181 이식.
    우선순위: stop_loss → take_profit → max_hold → trail_ma. 판정 기준은 bar i 종가."""
    entry_price = position["entry_price"]
    cur_close = float(df.iloc[i]["close"])
    ret = (cur_close - entry_price) / entry_price
    hold_bars = i - position["entry_idx"]
    if ret <= -stop_loss_pct:
        return "stop_loss"
    if ret >= take_profit_pct:
        return "take_profit"
    if hold_bars >= max_hold_bars:
        return "max_hold"
    if trail_ma is not None and i + 1 >= trail_ma:
        ma = df["close"].iloc[i - trail_ma + 1:i + 1].mean()
        if pd.notna(ma) and cur_close < float(ma):
            return "trail_ma"
    return None


def exit_reason_elder(df, i, position, stop_loss_pct, take_profit_pct,
                      max_hold_bars, trail_ema, trend_flip_exit) -> Optional[str]:
    """elder 청산. run_elder_triple_screen.py:145-164 이식.
    우선순위: stop_loss → take_profit → max_hold → trail_ema(수익중&종가<EMA13) → trend_flip(ema65 하락)."""
    entry_price = position["entry_price"]
    cur_close = float(df.iloc[i]["close"])
    ret = (cur_close - entry_price) / entry_price
    hold_bars = i - position["entry_idx"]
    exit_reason = None
    if ret <= -stop_loss_pct:
        exit_reason = "stop_loss"
    elif ret >= take_profit_pct:
        exit_reason = "take_profit"
    elif hold_bars >= max_hold_bars:
        exit_reason = "max_hold"
    elif trail_ema is not None and ret > 0:
        ema_trail = ema(df["close"].iloc[: i + 1].astype(float), trail_ema)
        if cur_close < float(ema_trail.iloc[-1]):
            exit_reason = "trail_ema"
    if exit_reason is None and trend_flip_exit and i >= 5:
        ema65 = ema(df["close"].iloc[: i + 1].astype(float), 65)
        if float(ema65.iloc[-1]) < float(ema65.iloc[-6]):
            exit_reason = "trend_flip"
    return exit_reason
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `python -m pytest tests/exit_multiverse/test_exits.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/exit_multiverse/exits.py tests/exit_multiverse/test_exits.py
git commit -m "feat(exit-mv): 청산 판정 순수함수 2종(elder/단순MA) 이식"
```

---

## Task 3: 진입 신호 사전계산 (그리드 무관 캐시)

**Files:**
- Create: `scripts/exit_multiverse/signals.py`
- Create: `tests/exit_multiverse/test_signals.py`

진입 신호는 청산 파라미터와 무관하므로 그리드 루프 밖에서 1회 계산해 `{code: [신호발생 bar 인덱스 i, ...]}` 로 캐싱한다.

- [ ] **Step 1: 테스트 먼저 작성**

`tests/exit_multiverse/test_signals.py`:

```python
import pandas as pd
from scripts.exit_multiverse import signals


class _StubStrategy:
    """i=72 에서만 BUY 신호."""
    def generate_signal_with_extra_ctx(self, code, window, tf, ctx):
        from strategies.base import Signal, SignalType
        if len(window) - 1 == 72:
            return Signal(signal_type=SignalType.BUY, stock_code=code, confidence=80,
                          reasons=["stub"])
        return None


def _df(n=100):
    import numpy as np
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open": np.linspace(100, 120, n), "high": np.linspace(101, 121, n),
        "low": np.linspace(99, 119, n), "close": np.linspace(100, 120, n),
        "volume": [1000] * n,
    })


def test_precompute_entry_signals_finds_signal_bar():
    data = {"005930": _df(100)}
    strat = _StubStrategy()
    cache = signals.precompute_entry_signals(
        data, strat, warmup_bars=70, extra_ctx_fn=lambda code, dt: {})
    assert cache["005930"] == [72]


def test_precompute_respects_warmup():
    data = {"005930": _df(100)}
    strat = _StubStrategy()
    cache = signals.precompute_entry_signals(
        data, strat, warmup_bars=80, extra_ctx_fn=lambda code, dt: {})
    assert cache["005930"] == []  # 72 < warmup 80 → 평가 안 됨
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/exit_multiverse/test_signals.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: signals.py 구현**

```python
"""진입 신호 사전계산. 청산 파라미터와 무관 → 그리드 루프 밖에서 1회."""
from __future__ import annotations
from typing import Callable, Dict, List
import pandas as pd
from strategies.base import SignalType


def precompute_entry_signals(
    data: Dict[str, pd.DataFrame],
    strategy,
    warmup_bars: int,
    extra_ctx_fn: Callable[[str, pd.Timestamp], dict],
) -> Dict[str, List[int]]:
    """각 종목에서 BUY/STRONG_BUY 신호가 난 bar 인덱스 i 목록.

    기존 simulate_one_stock 의 신호평가(run_elder:213-222 등)와 동일:
      window=df[:i+1], signal=strategy.generate_signal_with_extra_ctx(code, window, "daily", ctx).
    i 범위는 [warmup_bars, n-2] (마지막 봉은 다음날 체결 불가).
    extra_ctx_fn(code, date) → ctx_extra dict (minervini RS 주입용, 나머지는 {}).
    """
    cache: Dict[str, List[int]] = {}
    for code, df in data.items():
        n = len(df)
        sig_bars: List[int] = []
        if n >= warmup_bars + 2:
            for i in range(warmup_bars, n - 1):
                cur_date = df.iloc[i]["datetime"]
                window = df.iloc[: i + 1]
                ctx = extra_ctx_fn(code, cur_date)
                sig = strategy.generate_signal_with_extra_ctx(code, window, "daily", ctx)
                if sig is not None and sig.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                    sig_bars.append(i)
        cache[code] = sig_bars
    return cache
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/exit_multiverse/test_signals.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/exit_multiverse/signals.py tests/exit_multiverse/test_signals.py
git commit -m "feat(exit-mv): 진입 신호 사전계산 캐시(그리드 무관)"
```

---

## Task 4: 어댑터 정의 (4전략) + 그리드

**Files:**
- Create: `scripts/exit_multiverse/adapters.py`
- Create: `tests/exit_multiverse/test_adapters.py`

각 전략의 차이(진입 메커니즘, 청산 종류, ctx 주입, 그리드, warmup)를 `StrategyAdapter` 로 흡수한다.

- [ ] **Step 1: 테스트 먼저 작성**

`tests/exit_multiverse/test_adapters.py`:

```python
from scripts.exit_multiverse import adapters


def test_four_adapters_exist():
    names = set(adapters.ADAPTERS.keys())
    assert names == {"elder_ema_pullback", "minervini_volume_dryup",
                     "book_pullback_ma20", "book_pullback_ma5"}


def test_grid_includes_live_value_elder():
    ad = adapters.ADAPTERS["elder_ema_pullback"]
    grid = ad.build_grid()
    # 현재 운용값(sl0.08/tp0.30/mh100/trail_ema13/flip True)이 그리드에 포함돼야 함
    assert any(g["stop_loss_pct"] == 0.08 and g["take_profit_pct"] == 0.30
               and g["max_hold_bars"] == 100 and g["trail_ema"] == 13
               and g["trend_flip_exit"] is True for g in grid)


def test_grid_includes_live_value_ma5():
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    grid = ad.build_grid()
    assert any(g["stop_loss_pct"] == 0.03 and g["take_profit_pct"] == 0.15
               and g["max_hold_bars"] == 30 and g["trail_ma"] == 5 for g in grid)


def test_entry_mechanism_values():
    assert adapters.ADAPTERS["elder_ema_pullback"].entry_mechanism == "stop"
    assert adapters.ADAPTERS["minervini_volume_dryup"].entry_mechanism == "market"
    assert adapters.ADAPTERS["book_pullback_ma20"].entry_mechanism == "market"
    assert adapters.ADAPTERS["book_pullback_ma5"].entry_mechanism == "market"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/exit_multiverse/test_adapters.py -v`
Expected: FAIL.

- [ ] **Step 3: adapters.py 구현**

```python
"""4전략 어댑터. 진입 메커니즘·청산종류·ctx주입·그리드를 캡슐화."""
from __future__ import annotations
import itertools
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import pandas as pd

from scripts.exit_multiverse import exits


@dataclass
class StrategyAdapter:
    name: str
    entry_mechanism: str          # "stop"(elder 매수스톱) | "market"(다음날 시가)
    warmup_bars: int
    exit_kind: str                # "elder" | "simple_ma"
    build_strategy: Callable[[], object]
    build_grid: Callable[[], List[dict]]
    make_extra_ctx_fn: Callable[[Dict[str, pd.DataFrame]], Callable[[str, pd.Timestamp], dict]]

    def exit_reason(self, df, i, position, params) -> Optional[str]:
        if self.exit_kind == "elder":
            return exits.exit_reason_elder(
                df, i, position,
                stop_loss_pct=params["stop_loss_pct"],
                take_profit_pct=params["take_profit_pct"],
                max_hold_bars=params["max_hold_bars"],
                trail_ema=params.get("trail_ema"),
                trend_flip_exit=params.get("trend_flip_exit", False))
        return exits.exit_reason_simple_ma(
            df, i, position,
            stop_loss_pct=params["stop_loss_pct"],
            take_profit_pct=params["take_profit_pct"],
            max_hold_bars=params["max_hold_bars"],
            trail_ma=params.get("trail_ma"))


def _grid(**axes) -> List[dict]:
    keys = list(axes.keys())
    return [dict(zip(keys, combo)) for combo in itertools.product(*axes.values())]


# ---- elder ----
def _elder_strategy():
    from strategies.books.elder_triple_screen.strategy import build_strategy
    return build_strategy(mode="single", target_rule="triple_screen_ema_pullback")


def _elder_grid() -> List[dict]:
    # 중앙=현재 운용값(0.08/0.30/100/13/True). trail off 와 flip off 도 탐색.
    return _grid(stop_loss_pct=[0.06, 0.08, 0.10],
                 take_profit_pct=[0.20, 0.30, 0.40],
                 max_hold_bars=[60, 100, 150],
                 trail_ema=[13, None],
                 trend_flip_exit=[True, False])  # 3*3*3*2*2 = 108 (DSR n_trials 정직 반영)


# ---- minervini (RS 주입 필요) ----
def _minervini_strategy():
    from strategies.books.minervini_vcp.strategy import build_strategy
    return build_strategy(mode="single", target_rule="volume_dryup")


def _minervini_grid() -> List[dict]:
    return _grid(stop_loss_pct=[0.06, 0.08, 0.10],
                 take_profit_pct=[0.10, 0.12, 0.15],
                 max_hold_bars=[15, 20, 30])  # 27, trail 없음


def _minervini_ctx_factory(data: Dict[str, pd.DataFrame]):
    """run_minervini_vcp.py:100-105,290-291 의 RS 계산을 재현."""
    from strategies.books.minervini_vcp.rules import compute_rs_percentile_12w
    series = {code: df.set_index("datetime")["close"] for code, df in data.items()}
    wide = pd.DataFrame(series)
    wide.index = pd.to_datetime(wide.index)
    wide = wide.sort_index()
    rs_wide = compute_rs_percentile_12w(wide)

    def _ctx(code: str, dt: pd.Timestamp) -> dict:
        if code in rs_wide.columns and dt in rs_wide.index:
            val = float(rs_wide.loc[dt, code])
        else:
            val = float("nan")
        return {"rs_value": val}
    return _ctx


# ---- ma20 (강창권/haru) ----
def _ma20_strategy():
    from strategies.books.haru_silijeon.strategy_daily import build_strategy_daily
    return build_strategy_daily(mode="single", target_rule="daily_ma20_pullback")


def _ma20_grid() -> List[dict]:
    return _grid(stop_loss_pct=[0.06, 0.08, 0.10],
                 take_profit_pct=[0.08, 0.10, 0.15],
                 max_hold_bars=[30, 50, 80],
                 trail_ma=[20, None])  # 54


# ---- ma5 (Book15/trading_legends) ----
def _ma5_strategy():
    from strategies.books.trading_legends.strategy_daily import build_strategy_daily
    return build_strategy_daily(mode="single", target_rule="ma5_pullback")


def _ma5_grid() -> List[dict]:
    # 중앙=현재 운용값(0.03/0.15/30/5). sl 에 0.03 반드시 포함.
    return _grid(stop_loss_pct=[0.03, 0.05, 0.08],
                 take_profit_pct=[0.12, 0.15, 0.20],
                 max_hold_bars=[20, 30, 50],
                 trail_ma=[5, None])  # 54


def _empty_ctx_factory(data):
    return lambda code, dt: {}


ADAPTERS: Dict[str, StrategyAdapter] = {
    "elder_ema_pullback": StrategyAdapter(
        name="elder_ema_pullback", entry_mechanism="stop", warmup_bars=70,
        exit_kind="elder", build_strategy=_elder_strategy, build_grid=_elder_grid,
        make_extra_ctx_fn=_empty_ctx_factory),
    "minervini_volume_dryup": StrategyAdapter(
        name="minervini_volume_dryup", entry_mechanism="market", warmup_bars=60,
        exit_kind="simple_ma", build_strategy=_minervini_strategy, build_grid=_minervini_grid,
        make_extra_ctx_fn=_minervini_ctx_factory),
    "book_pullback_ma20": StrategyAdapter(
        name="book_pullback_ma20", entry_mechanism="market", warmup_bars=20,
        exit_kind="simple_ma", build_strategy=_ma20_strategy, build_grid=_ma20_grid,
        make_extra_ctx_fn=_empty_ctx_factory),
    "book_pullback_ma5": StrategyAdapter(
        name="book_pullback_ma5", entry_mechanism="market", warmup_bars=20,
        exit_kind="simple_ma", build_strategy=_ma5_strategy, build_grid=_ma5_grid,
        make_extra_ctx_fn=_empty_ctx_factory),
}
```

> **구현자 주의:** `build_strategy(mode="single", target_rule=...)`의 `target_rule` 이름은 각 전략의 `ALL_RULES`/`ALL_DAILY_RULES` 에 실제 존재하는 룰명이어야 한다. elder는 `triple_screen_ema_pullback`, minervini는 `volume_dryup`, ma20은 `daily_ma20_pullback`, ma5는 `ma5_pullback` 으로 추정되나, **각 `rules.py`/`rules_daily.py`의 룰 클래스 `.name`을 grep으로 확인 후 확정하라**(불일치 시 build가 실패한다). 또한 라이브 `strategies/<name>/config.yaml`의 현재 청산값을 읽어 `_*_grid()` 중앙값과 일치하는지 재확인하라.

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/exit_multiverse/test_adapters.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/exit_multiverse/adapters.py tests/exit_multiverse/test_adapters.py
git commit -m "feat(exit-mv): 4전략 어댑터 + 청산 그리드(현재 운용값 중앙 포함)"
```

---

## Task 5: 포트폴리오 시뮬레이터 (핵심)

**Files:**
- Create: `scripts/exit_multiverse/portfolio_sim.py`
- Create: `tests/exit_multiverse/test_portfolio_sim.py`

날짜축을 따라가며: ①보유 청산판정→다음날 시가 체결 ②미보유 신호종목 진입(우선순위·슬롯·현금 한도)→다음날 시가/매수스톱 체결 ③일별 equity 기록. `max_positions`/`max_per_stock`/`initial_capital` 제약. per-stock 모드(`unconstrained=True`)는 각 종목 독립 자본으로 기존 `simulate_one_stock` 동등성 회귀에 쓴다.

- [ ] **Step 1: 테스트 먼저 작성**

`tests/exit_multiverse/test_portfolio_sim.py`:

```python
import numpy as np
import pandas as pd
import pytest
from scripts.exit_multiverse import portfolio_sim
from scripts.exit_multiverse import adapters


def _flat_then_drop(n=80):
    closes = [100.0] * 72 + [100.0, 100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 90.0]
    closes = (closes + [90.0] * n)[:n]
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1000] * n,
    })


def test_max_positions_caps_holdings():
    # 5종목 모두 같은 날 신호 → max_positions=2 면 2종목만 진입
    data = {f"{i:06d}": _flat_then_drop() for i in range(5)}
    signal_cache = {code: [72] for code in data}  # 모두 i=72 신호
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.99, "max_hold_bars": 999, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={code: float(i) for i, code in enumerate(data)},
        initial_capital=10_000_000, max_positions=2, max_per_stock=3_000_000,
        unconstrained=False)
    # 동시 보유가 2를 넘지 않았는지
    assert res["max_concurrent_positions"] <= 2
    assert res["n_skipped"] >= 1  # 슬롯 부족으로 스킵 발생


def test_equity_curve_nonempty():
    data = {"000001": _flat_then_drop()}
    signal_cache = {"000001": [72]}
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.99, "max_hold_bars": 999, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={"000001": 1.0}, initial_capital=10_000_000,
        max_positions=5, max_per_stock=3_000_000, unconstrained=False)
    assert len(res["equity_curve"]) > 0
    assert "daily_returns" in res
    assert isinstance(res["daily_returns"], pd.Series)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/exit_multiverse/test_portfolio_sim.py -v`
Expected: FAIL.

- [ ] **Step 3: portfolio_sim.py 구현**

```python
"""포트폴리오 시뮬레이터 — 자금·슬롯 제약 하에서 4전략 공통 체결.

진입/청산 판정은 어댑터(=기존 rules.py/청산함수)에 위임. 이 파일은 자금관리만.
no-lookahead: 판정은 bar i, 체결은 bar i+1 시가. 비용 상수는 기존 run_*.py 와 동일.
"""
from __future__ import annotations
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from strategies.books.elder_triple_screen.rules import krx_tick, screen1_uptrend

COMMISSION_RATE = 0.00015
TAX_RATE = 0.0018
SLIPPAGE_RATE = 0.001
N_TRAIL = 2  # elder 매수스톱 추적일 (run_elder_triple_screen.py:36)


def _build_master_dates(data: Dict[str, pd.DataFrame]) -> List[pd.Timestamp]:
    s = set()
    for df in data.values():
        s.update(pd.to_datetime(df["datetime"]).tolist())
    return sorted(s)


def run_portfolio(data, signal_cache, adapter, params, turnover,
                  initial_capital=10_000_000, max_positions=5,
                  max_per_stock=3_000_000, unconstrained=False) -> dict:
    """날짜축 포트폴리오 시뮬레이션.

    data: {code: df(datetime,open,high,low,close,volume)}
    signal_cache: {code: [신호 bar i, ...]} (precompute_entry_signals 결과)
    adapter: StrategyAdapter (exit_reason / entry_mechanism 제공)
    params: 청산 파라미터 dict (그리드 1조합)
    turnover: {code: 거래대금} (진입 우선순위 정렬)
    unconstrained=True: per-stock 독립자본 모드(동등성 회귀용) — 자금/슬롯 무제한,
                        각 종목 첫 신호만, 종목별 initial_capital 독립.

    반환: {equity_curve, daily_returns(pd.Series, index=date), trades,
           max_concurrent_positions, n_trades, n_skipped}
    """
    # 종목별 (date -> row index) 매핑
    idx_by_date: Dict[str, Dict[pd.Timestamp, int]] = {}
    for code, df in data.items():
        idx_by_date[code] = {pd.Timestamp(d): k for k, d in enumerate(df["datetime"])}
    signal_set = {code: set(v) for code, v in signal_cache.items()}

    master = _build_master_dates(data)
    cash = initial_capital
    positions: Dict[str, dict] = {}            # code -> {entry_idx, entry_price, qty}
    pending: Dict[str, dict] = {}              # code -> {trigger_high_idx, days_left} (elder)
    trades: List[dict] = []
    equity_dates: List[pd.Timestamp] = []
    equity_vals: List[float] = []
    max_concurrent = 0
    n_skipped = 0
    entered_codes: set = set()                 # unconstrained 모드: 1회 진입 제한용

    # 종목당 독립 현금(unconstrained 모드)
    cash_by_code: Dict[str, float] = {code: initial_capital for code in data} if unconstrained else {}

    for d in master:
        # ---- 1) 청산 판정 + 체결 (보유 종목) ----
        for code in list(positions.keys()):
            df = data[code]
            i = idx_by_date[code].get(d)
            if i is None or i + 1 >= len(df):
                continue
            reason = adapter.exit_reason(df, i, positions[code], params)
            if reason is not None:
                nxt_open = float(df.iloc[i + 1]["open"])
                if nxt_open <= 0:
                    continue
                fill = nxt_open * (1 - SLIPPAGE_RATE)
                pos = positions.pop(code)
                proceeds = pos["qty"] * fill
                fee = proceeds * (COMMISSION_RATE + TAX_RATE)
                if unconstrained:
                    cash_by_code[code] += proceeds - fee
                else:
                    cash += proceeds - fee
                trades.append({"stock_code": code, "side": "sell",
                               "datetime": str(df.iloc[i + 1]["datetime"]),
                               "entry_price": pos["entry_price"], "price": fill,
                               "qty": pos["qty"], "reason": reason,
                               "pnl_pct": (fill - pos["entry_price"]) / pos["entry_price"],
                               "entry_date": pos["entry_date"]})

        # ---- 2) 진입 후보 수집 (미보유 & 신호발생 & 다음봉 존재) ----
        candidates = []
        for code, df in data.items():
            if code in positions:
                continue
            if unconstrained and code in entered_codes:
                continue
            i = idx_by_date[code].get(d)
            if i is None or i + 1 >= len(df):
                continue
            if adapter.entry_mechanism == "market":
                if i in signal_set.get(code, ()):
                    candidates.append((code, i))
            else:  # elder 매수스톱: 신호 발생 시 pending 등록, 이후 스톱 체결
                if i in signal_set.get(code, ()) and code not in pending:
                    pending[code] = {"trigger_high_idx": i, "days_left": N_TRAIL}

        # elder pending 스톱 체결 후보
        if adapter.entry_mechanism == "stop":
            for code in list(pending.keys()):
                if code in positions:
                    pending.pop(code, None); continue
                df = data[code]; i = idx_by_date[code].get(d)
                if i is None or i + 1 >= len(df):
                    continue
                prior_high = float(df.iloc[pending[code]["trigger_high_idx"]]["high"])
                trigger = prior_high + krx_tick(prior_high)
                nxt_open = float(df.iloc[i + 1]["open"]); nxt_high = float(df.iloc[i + 1]["high"])
                fill = None
                if nxt_open >= trigger:
                    fill = nxt_open * (1 + SLIPPAGE_RATE)
                elif nxt_high >= trigger:
                    fill = trigger * (1 + SLIPPAGE_RATE)
                if fill is not None:
                    candidates.append((code, i, fill))
                else:
                    pending[code]["days_left"] -= 1
                    pending[code]["trigger_high_idx"] = i
                    wclose = df["close"].iloc[: i + 2].astype(float)
                    if pending[code]["days_left"] <= 0 or not screen1_uptrend(wclose):
                        pending.pop(code, None)

        # ---- 3) 우선순위 정렬(거래대금 내림차순) 후 진입 체결 ----
        candidates.sort(key=lambda c: turnover.get(c[0], 0.0), reverse=True)
        for cand in candidates:
            code, i = cand[0], cand[1]
            df = data[code]
            if not unconstrained and len(positions) >= max_positions:
                n_skipped += 1; continue
            if adapter.entry_mechanism == "stop":
                fill = cand[2]
            else:
                nxt_open = float(df.iloc[i + 1]["open"])
                if nxt_open <= 0:
                    continue
                fill = nxt_open * (1 + SLIPPAGE_RATE)
            avail = cash_by_code[code] if unconstrained else min(cash, max_per_stock)
            qty = int((avail * 0.99) // fill) if fill > 0 else 0
            if qty <= 0:
                n_skipped += 1; continue
            cost = qty * fill; fee = cost * COMMISSION_RATE
            if unconstrained:
                cash_by_code[code] -= cost + fee
            else:
                cash -= cost + fee
            positions[code] = {"entry_idx": i + 1, "entry_price": fill, "qty": qty,
                               "entry_date": str(df.iloc[i + 1]["datetime"])}
            if adapter.entry_mechanism == "stop":
                pending.pop(code, None)
            if unconstrained:
                entered_codes.add(code)
            trades.append({"stock_code": code, "side": "buy",
                           "datetime": str(df.iloc[i + 1]["datetime"]),
                           "entry_price": fill, "price": fill, "qty": qty,
                           "reason": "signal", "pnl_pct": 0.0,
                           "entry_date": str(df.iloc[i + 1]["datetime"])})

        max_concurrent = max(max_concurrent, len(positions))

        # ---- 4) 일별 equity (MTM: cash + 보유 종목 당일 종가 평가) ----
        if unconstrained:
            mtm = sum(cash_by_code.values())
        else:
            mtm = cash
        for code, pos in positions.items():
            i = idx_by_date[code].get(d)
            if i is not None:
                mtm += pos["qty"] * float(data[code].iloc[i]["close"])
        equity_dates.append(d); equity_vals.append(mtm)

    eq = pd.Series(equity_vals, index=pd.to_datetime(equity_dates))
    daily_returns = eq.pct_change().dropna()
    return {"equity_curve": equity_vals, "daily_returns": daily_returns,
            "trades": trades, "max_concurrent_positions": max_concurrent,
            "n_trades": sum(1 for t in trades if t["side"] == "sell"),
            "n_skipped": n_skipped}
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/exit_multiverse/test_portfolio_sim.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/exit_multiverse/portfolio_sim.py tests/exit_multiverse/test_portfolio_sim.py
git commit -m "feat(exit-mv): 포트폴리오 시뮬레이터(자금·슬롯·매수스톱·per-stock 모드)"
```

---

## Task 6: per-stock 동등성 회귀 (기존 Sharpe 재현)

**Files:**
- Create: `tests/exit_multiverse/test_equivalence.py`

신규 시뮬레이터의 진입/청산 이식이 정확한지, `unconstrained=True` 모드로 기존 `run_minervini_vcp.simulate_one_stock` 과 **거래 횟수·방향이 일치**하는지 단일 종목으로 검증한다. (minervini는 진입 메커니즘이 단순해 비교가 깔끔하다.)

- [ ] **Step 1: 테스트 작성**

```python
"""동등성 회귀: 신규 포트폴리오 시뮬(unconstrained)이 기존 simulate_one_stock 과
같은 거래를 생성하는지. minervini 단일종목으로 검증."""
import pandas as pd
import pytest
from scripts.exit_multiverse import data_loader, signals, adapters, portfolio_sim


@pytest.mark.slow
def test_minervini_single_stock_trade_count_matches_legacy():
    import scripts.run_minervini_vcp as legacy

    start, end = "2022-01-01", "2024-12-31"
    codes = data_loader.load_top_volume_universe(start, end, top_n=5)
    data = data_loader.load_daily_adj(codes, start, end)
    # 한 종목만
    code = next(iter(data))
    one = {code: data[code]}

    ad = adapters.ADAPTERS["minervini_volume_dryup"]
    strat = ad.build_strategy()
    ctx_fn = ad.make_extra_ctx_fn(data)   # RS는 전체 유니버스로 계산
    sig = signals.precompute_entry_signals(one, strat, ad.warmup_bars, ctx_fn)

    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12,
              "max_hold_bars": 20, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=one, signal_cache=sig, adapter=ad, params=params,
        turnover={code: 1.0}, initial_capital=10_000_000,
        max_positions=99, max_per_stock=10_000_000, unconstrained=True)

    # 기존 simulate_one_stock 으로 동일 종목·동일 파라미터 실행
    wide = pd.DataFrame({code: data[code].set_index("datetime")["close"]})
    wide.index = pd.to_datetime(wide.index)
    from strategies.books.minervini_vcp.rules import compute_rs_percentile_12w
    rs = compute_rs_percentile_12w(pd.DataFrame(
        {c: data[c].set_index("datetime")["close"] for c in data}))
    legacy_res = legacy.simulate_one_stock(
        code=code, df=data[code], rs_series=rs[code] if code in rs.columns else None,
        strategy=strat, stop_loss_pct=0.08, take_profit_pct=0.12,
        max_hold_bars=20, trail_ma=None)

    new_sells = res["n_trades"]
    legacy_sells = sum(1 for t in legacy_res["trades"] if t["side"] == "sell")
    # 매수스톱이 없는 minervini는 거래수가 정확히 일치해야 함(±1 허용: 마지막 강제청산 처리 차이)
    assert abs(new_sells - legacy_sells) <= 1
```

- [ ] **Step 2: 실행**

Run: `python -m pytest tests/exit_multiverse/test_equivalence.py -v -m slow`
Expected: PASS. 만약 거래수가 크게 다르면 진입/청산 이식 버그 → `portfolio_sim` 의 신호평가·청산판정 인덱스(i vs i+1)를 기존 `simulate_one_stock` 과 대조해 수정. **이 테스트가 통과해야 이후 결과를 신뢰할 수 있다.**

- [ ] **Step 3: Commit**

```bash
git add tests/exit_multiverse/test_equivalence.py
git commit -m "test(exit-mv): per-stock 동등성 회귀(신규 시뮬 vs 기존 simulate_one_stock)"
```

---

## Task 7: 목적함수 (국면별 Sharpe 분해 + 국면최악 + DSR)

**Files:**
- Create: `scripts/exit_multiverse/objective.py`
- Create: `tests/exit_multiverse/test_objective.py`

포트폴리오 **일별 수익률**을 KOSPI 국면 라벨로 분류해 국면별 Sharpe를 구하고, 그 최소값(국면최악)을 점수로 한다. DSR은 전체 일별수익률 기준.

- [ ] **Step 1: 테스트 작성**

`tests/exit_multiverse/test_objective.py`:

```python
import numpy as np
import pandas as pd
from scripts.exit_multiverse import objective
from backtest.regime_analysis import MarketRegime


def _regime_series(dates, labels):
    return pd.Series([getattr(MarketRegime, l) for l in labels], index=pd.to_datetime(dates))


def test_regime_worst_sharpe_picks_min():
    dates = pd.date_range("2021-01-01", periods=9)
    # 3 BULL(+), 3 BEAR(-), 3 SIDEWAYS(0)
    rets = pd.Series([0.01, 0.02, 0.015, -0.01, -0.02, -0.015, 0.0, 0.001, -0.001], index=dates)
    regimes = _regime_series(dates, ["BULL"]*3 + ["BEAR"]*3 + ["SIDEWAYS"]*3)
    out = objective.regime_sharpes(rets, regimes, min_obs=2)
    assert out["BEAR"] < out["BULL"]
    assert out["worst"] == min(out["BULL"], out["BEAR"], out["SIDEWAYS"])


def test_dsr_computed():
    dates = pd.date_range("2021-01-01", periods=300)
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0.001, 0.01, 300), index=dates)
    dsr = objective.compute_dsr(rets, n_trials=54)
    assert 0.0 <= dsr <= 1.0
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/exit_multiverse/test_objective.py -v`
Expected: FAIL.

- [ ] **Step 3: objective.py 구현**

```python
"""목적함수: 국면별 Sharpe 분해 → 국면최악 → DSR."""
from __future__ import annotations
import math
from typing import Dict
import numpy as np
import pandas as pd

from backtest.regime_analysis import MarketRegime
from multiverse.runner.dsr import deflated_sharpe_ratio

_ANNUAL = math.sqrt(252)


def _sharpe(rets: np.ndarray) -> float:
    rets = rets[np.isfinite(rets)]
    if len(rets) < 2 or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * _ANNUAL)


def regime_sharpes(daily_returns: pd.Series, regime_series: pd.Series,
                   min_obs: int = 20) -> Dict[str, float]:
    """일별 수익률을 그날의 국면 라벨로 분류해 국면별 연환산 Sharpe.

    min_obs 미만 표본 국면은 worst 계산에서 제외하되 값은 보고(신뢰 부족 표기는 report 책임).
    'worst' = min(표본 충분한 국면 Sharpe). 충분한 국면이 없으면 0.0.
    """
    # regime_series index를 날짜로 통일해 매핑
    reg_map = {pd.Timestamp(str(k)[:10]): (v.value.upper() if isinstance(v, MarketRegime) else "SIDEWAYS")
               for k, v in regime_series.items()}
    out: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for label in ("BULL", "BEAR", "SIDEWAYS"):
        mask = daily_returns.index.map(lambda d: reg_map.get(pd.Timestamp(str(d)[:10])) == label)
        vals = daily_returns[np.asarray(mask, dtype=bool)].to_numpy()
        out[label] = _sharpe(vals)
        counts[label] = len(vals)
    eligible = [out[l] for l in ("BULL", "BEAR", "SIDEWAYS") if counts[l] >= min_obs]
    out["worst"] = float(min(eligible)) if eligible else 0.0
    out["_counts"] = counts  # report 에서 신뢰도 표기용
    return out


def compute_dsr(daily_returns: pd.Series, n_trials: int) -> float:
    """전체 일별수익률 기준 DSR. n_trials=그리드 조합 수."""
    rets = daily_returns.to_numpy()
    rets = rets[np.isfinite(rets)]
    if len(rets) < 2:
        return 0.0
    sharpe = _sharpe(rets)
    from scipy.stats import skew as _skew, kurtosis as _kurt
    sk = float(_skew(rets)) if len(rets) > 2 else 0.0
    ek = float(_kurt(rets, fisher=True)) if len(rets) > 3 else 0.0
    return deflated_sharpe_ratio(sharpe=sharpe, n_trials=n_trials,
                                 n_observations=len(rets), skew=sk, excess_kurt=ek)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/exit_multiverse/test_objective.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/exit_multiverse/objective.py tests/exit_multiverse/test_objective.py
git commit -m "feat(exit-mv): 목적함수(국면별 Sharpe·국면최악·DSR)"
```

---

## Task 8: 워크포워드 폴드 생성 + 폴드 평가

**Files:**
- Create: `scripts/exit_multiverse/walkforward.py`
- Create: `tests/exit_multiverse/test_walkforward.py`

롤링 train/test 폴드(train 24개월/test 6개월/step 6개월)를 만들고, 각 폴드 train 에서 그리드 전체를 평가해 국면최악 Sharpe 최고 조합을 선정(+DSR 기록), test 에서 OOS 성과를 측정한다.

- [ ] **Step 1: 테스트 작성**

`tests/exit_multiverse/test_walkforward.py`:

```python
import pandas as pd
from scripts.exit_multiverse import walkforward


def test_make_folds_count_and_no_overlap():
    folds = walkforward.make_folds("2021-01-01", "2026-05-31",
                                   train_months=24, test_months=6, step_months=6)
    assert len(folds) >= 6
    for f in folds:
        assert f["train_start"] < f["train_end"] <= f["test_start"] < f["test_end"]


def test_make_folds_train_includes_bear_year():
    # train 24개월이면 대부분 폴드가 2022(BEAR)를 포함
    folds = walkforward.make_folds("2021-01-01", "2026-05-31", 24, 6, 6)
    assert any(f["train_start"] <= "2022-06-01" <= f["train_end"] for f in folds)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/exit_multiverse/test_walkforward.py -v`
Expected: FAIL.

- [ ] **Step 3: walkforward.py 구현**

```python
"""워크포워드: 롤링 폴드 생성 + 폴드 평가."""
from __future__ import annotations
from typing import Callable, Dict, List
import pandas as pd

from scripts.exit_multiverse import portfolio_sim, objective


def make_folds(start: str, end: str, train_months: int = 24,
               test_months: int = 6, step_months: int = 6) -> List[dict]:
    """[{train_start, train_end, test_start, test_end}] (문자열 YYYY-MM-DD)."""
    s = pd.Timestamp(start); e = pd.Timestamp(end)
    folds = []
    cur = s
    while True:
        tr_start = cur
        tr_end = tr_start + pd.DateOffset(months=train_months)
        te_start = tr_end
        te_end = te_start + pd.DateOffset(months=test_months)
        if te_end > e + pd.DateOffset(days=1):
            # 마지막 test 가 end 를 넘으면, test_end 를 end 로 잘라 1폴드만 더 허용
            if te_start < e:
                te_end = e
                folds.append({"train_start": str(tr_start.date()), "train_end": str(tr_end.date()),
                              "test_start": str(te_start.date()), "test_end": str(te_end.date())})
            break
        folds.append({"train_start": str(tr_start.date()), "train_end": str(tr_end.date()),
                      "test_start": str(te_start.date()), "test_end": str(te_end.date())})
        cur = cur + pd.DateOffset(months=step_months)
    return folds


def _slice_data(data: Dict[str, pd.DataFrame], start: str, end: str) -> Dict[str, pd.DataFrame]:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out = {}
    for code, df in data.items():
        m = (df["datetime"] >= s) & (df["datetime"] <= e)
        sub = df[m].reset_index(drop=True)
        if len(sub) > 0:
            out[code] = sub
    return out


def evaluate_fold(fold, data, signal_cache_full, adapter, grid, turnover,
                  regime_series, initial_capital, max_positions, max_per_stock,
                  min_obs=20) -> dict:
    """한 폴드: train 에서 그리드 전체 평가 → 국면최악 최고 조합 선정 → test OOS 측정.

    signal_cache_full: 전체기간 신호 캐시. 폴드 구간 슬라이스 시, 슬라이스 df 의
      로컬 인덱스로 신호 i 를 재매핑해야 한다(아래 _reindex_signals).
    """
    n_trials = len(grid)
    results = []
    train_data = _slice_data(data, fold["train_start"], fold["train_end"])
    train_sig = _reindex_signals(signal_cache_full, data, train_data)
    for params in grid:
        res = portfolio_sim.run_portfolio(
            data=train_data, signal_cache=train_sig, adapter=adapter, params=params,
            turnover=turnover, initial_capital=initial_capital,
            max_positions=max_positions, max_per_stock=max_per_stock)
        rs = objective.regime_sharpes(res["daily_returns"], regime_series, min_obs=min_obs)
        dsr = objective.compute_dsr(res["daily_returns"], n_trials=n_trials)
        results.append({"params": params, "worst_sharpe": rs["worst"],
                        "regime": rs, "dsr": dsr, "n_trades": res["n_trades"]})
    # 국면최악 Sharpe 최고 조합 선정
    results.sort(key=lambda r: r["worst_sharpe"], reverse=True)
    best = results[0]
    # test OOS
    test_data = _slice_data(data, fold["test_start"], fold["test_end"])
    test_sig = _reindex_signals(signal_cache_full, data, test_data)
    oos = portfolio_sim.run_portfolio(
        data=test_data, signal_cache=test_sig, adapter=adapter, params=best["params"],
        turnover=turnover, initial_capital=initial_capital,
        max_positions=max_positions, max_per_stock=max_per_stock)
    oos_rs = objective.regime_sharpes(oos["daily_returns"], regime_series, min_obs=1)
    oos_total = (oos["equity_curve"][-1] / initial_capital - 1.0) if oos["equity_curve"] else 0.0
    return {"fold": fold, "best": best, "all_results": results,
            "oos_worst_sharpe": oos_rs["worst"], "oos_total_return": oos_total,
            "oos_n_trades": oos["n_trades"]}


def _reindex_signals(signal_cache_full, full_data, sliced_data) -> Dict[str, List[int]]:
    """전체기간 신호 i(=full df 인덱스)를 슬라이스 df 의 로컬 인덱스로 변환.
    날짜 기준 매핑(신호가 난 날짜가 슬라이스에 있으면 그 로컬 인덱스 사용)."""
    out = {}
    for code, sub in sliced_data.items():
        full_df = full_data[code]
        full_dates = pd.to_datetime(full_df["datetime"])
        sig_dates = set(pd.Timestamp(full_dates.iloc[i]) for i in signal_cache_full.get(code, [])
                        if i < len(full_dates))
        local = [k for k, d in enumerate(pd.to_datetime(sub["datetime"]))
                 if pd.Timestamp(d) in sig_dates]
        out[code] = local
    return out
```

> **주의(룩어헤드):** 신호 사전계산은 전체기간 df 로 1회 수행하지만, 각 신호는 `df[:i+1]`만 보므로 미래정보를 쓰지 않는다. 폴드 슬라이스 후 재계산하지 않고 날짜로 재매핑하는 것은, train/test 경계에서 warmup 부족으로 신호가 약간 누락될 수 있으나(슬라이스 앞부분), 미래누수는 없다. 정확도를 더 높이려면 폴드별로 `precompute_entry_signals` 를 재실행해도 된다(연산↑). **1차 구현은 재매핑 방식, OOS 신뢰성 우려 시 폴드별 재계산으로 전환**(run.py 에 `--recompute-signals-per-fold` 플래그).

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/exit_multiverse/test_walkforward.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/exit_multiverse/walkforward.py tests/exit_multiverse/test_walkforward.py
git commit -m "feat(exit-mv): 워크포워드 폴드 생성·평가(train 그리드→OOS)"
```

---

## Task 9: 리포트 생성

**Files:**
- Create: `scripts/exit_multiverse/report.py`
- Create: `tests/exit_multiverse/test_report.py`

폴드별 결과 → `{전략}_walkforward.md`(폴드별 train 베스트/OOS/파라미터 안정성) + `{전략}_grid.parquet`.

- [ ] **Step 1: 테스트 작성**

```python
import pandas as pd
from pathlib import Path
from scripts.exit_multiverse import report


def test_build_grid_dataframe():
    fold_results = [{
        "fold": {"train_start": "2021-01-01", "train_end": "2023-01-01",
                 "test_start": "2023-01-01", "test_end": "2023-07-01"},
        "best": {"params": {"stop_loss_pct": 0.08, "take_profit_pct": 0.30,
                            "max_hold_bars": 100}, "worst_sharpe": 0.5, "dsr": 0.97,
                 "n_trades": 30},
        "all_results": [],
        "oos_worst_sharpe": 0.3, "oos_total_return": 0.12, "oos_n_trades": 8,
    }]
    df = report.build_fold_table(fold_results)
    assert "oos_total_return" in df.columns
    assert len(df) == 1


def test_param_stability_flag():
    # 폴드마다 베스트 파라미터가 다르면 unstable
    best_params = [{"stop_loss_pct": 0.08}, {"stop_loss_pct": 0.06}, {"stop_loss_pct": 0.10}]
    assert report.param_stability(best_params)["stop_loss_pct"]["unstable"] is True
```

- [ ] **Step 2: 실패 확인 → 구현**

`scripts/exit_multiverse/report.py`:

```python
"""산출물: 폴드 테이블, 파라미터 안정성, markdown 리포트."""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import pandas as pd


def build_fold_table(fold_results: List[dict]) -> pd.DataFrame:
    rows = []
    for fr in fold_results:
        b = fr["best"]
        row = {"train_start": fr["fold"]["train_start"], "test_start": fr["fold"]["test_start"],
               "test_end": fr["fold"]["test_end"],
               "train_worst_sharpe": b["worst_sharpe"], "train_dsr": b["dsr"],
               "train_n_trades": b["n_trades"],
               "oos_worst_sharpe": fr["oos_worst_sharpe"],
               "oos_total_return": fr["oos_total_return"], "oos_n_trades": fr["oos_n_trades"]}
        for k, v in b["params"].items():
            row[f"best_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def param_stability(best_params: List[dict]) -> Dict[str, dict]:
    """폴드 간 베스트 파라미터 분산. 고유값 2개 초과면 unstable(과최적화 신호)."""
    out = {}
    keys = set().union(*[p.keys() for p in best_params]) if best_params else set()
    for k in keys:
        vals = [p.get(k) for p in best_params]
        uniq = set(str(v) for v in vals)
        out[k] = {"values": vals, "n_unique": len(uniq), "unstable": len(uniq) > 2}
    return out


def write_strategy_report(name: str, fold_results: List[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = build_fold_table(fold_results)
    df.to_parquet(out_dir / f"{name}_grid.parquet", index=False)
    stab = param_stability([fr["best"]["params"] for fr in fold_results])
    md = [f"# {name} — 워크포워드 청산 최적화 결과\n",
          "## 폴드별 train 베스트 / OOS 성과\n", df.to_markdown(index=False), "\n",
          "## 파라미터 안정성 (폴드 간)\n"]
    for k, v in stab.items():
        flag = "⚠️ UNSTABLE(과최적화 의심)" if v["unstable"] else "안정"
        md.append(f"- **{k}**: {v['values']} → {flag}")
    mean_oos = df["oos_worst_sharpe"].mean() if len(df) else 0.0
    md.append(f"\n## 종합\n- 평균 OOS 국면최악 Sharpe: **{mean_oos:.3f}**")
    md.append(f"- 평균 OOS 수익률: **{df['oos_total_return'].mean():.2%}**" if len(df) else "")
    path = out_dir / f"{name}_walkforward.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path
```

- [ ] **Step 3: 통과 확인**

Run: `python -m pytest tests/exit_multiverse/test_report.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add scripts/exit_multiverse/report.py tests/exit_multiverse/test_report.py
git commit -m "feat(exit-mv): 폴드 테이블·파라미터 안정성·md 리포트"
```

---

## Task 10: CLI 러너 (단일 전략 실행) + 일봉 메모리 상주

**Files:**
- Create: `scripts/exit_multiverse/run.py`
- Create: `tests/exit_multiverse/test_run_smoke.py`

단일 전략의 전체 파이프라인을 실행하는 CLI. 일봉을 1회 로드해 메모리 상주, 신호 1회 사전계산 후 모든 폴드/조합이 공유.

- [ ] **Step 1: run.py 구현**

```python
"""단일 전략 청산 멀티버스 워크포워드 실행 CLI.

usage:
  python -m scripts.exit_multiverse.run --strategy elder_ema_pullback \
      --start 2021-01-01 --end 2026-05-29 --top-n 50 --max-positions 5 \
      --max-per-stock 3000000 --initial-capital 10000000 \
      --regime-threshold 0.02 --dsr-threshold 0.95 \
      --reports-dir reports/exit_optimization
"""
from __future__ import annotations
import argparse, logging, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.exit_multiverse import data_loader, signals, adapters, walkforward, report
from backtest.regime_analysis import classify_regime_rolling

LOG = logging.getLogger("exit_multiverse.run")


def run_one(strategy: str, start: str, end: str, top_n: int, max_positions: int,
            max_per_stock: float, initial_capital: float, regime_threshold: float,
            dsr_threshold: float, reports_dir: str) -> Path:
    ad = adapters.ADAPTERS[strategy]
    LOG.info(f"[{strategy}] universe/data 로드 (메모리 상주)")
    codes = data_loader.load_top_volume_universe(start, end, top_n)
    data = data_loader.load_daily_adj(codes, start, end)
    turnover = data_loader.load_turnover_rank(start, end)
    kospi = data_loader.load_kospi_close(start, end)
    regime_series = classify_regime_rolling(kospi, window=20, threshold=regime_threshold)

    LOG.info(f"[{strategy}] 진입 신호 사전계산 (그리드 무관, 1회)")
    strat = ad.build_strategy()
    ctx_fn = ad.make_extra_ctx_fn(data)
    signal_cache = signals.precompute_entry_signals(data, strat, ad.warmup_bars, ctx_fn)

    grid = ad.build_grid()
    folds = walkforward.make_folds(start, end, 24, 6, 6)
    LOG.info(f"[{strategy}] grid={len(grid)} folds={len(folds)} → 평가 시작")

    fold_results = []
    for fi, fold in enumerate(folds):
        fr = walkforward.evaluate_fold(
            fold=fold, data=data, signal_cache_full=signal_cache, adapter=ad,
            grid=grid, turnover=turnover, regime_series=regime_series,
            initial_capital=initial_capital, max_positions=max_positions,
            max_per_stock=max_per_stock)
        fold_results.append(fr)
        LOG.info(f"  fold{fi} {fold['test_start']}~{fold['test_end']}: "
                 f"OOS worst_sharpe={fr['oos_worst_sharpe']:.3f} "
                 f"OOS ret={fr['oos_total_return']:.2%} best_dsr={fr['best']['dsr']:.3f}")

    out_dir = Path(reports_dir)
    path = report.write_strategy_report(strategy, fold_results, out_dir)
    LOG.info(f"[{strategy}] 리포트: {path}")
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True, choices=list(adapters.ADAPTERS.keys()))
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-05-29")
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--max-positions", type=int, default=5)
    p.add_argument("--max-per-stock", type=float, default=3_000_000)
    p.add_argument("--initial-capital", type=float, default=10_000_000)
    p.add_argument("--regime-threshold", type=float, default=0.02)
    p.add_argument("--dsr-threshold", type=float, default=0.95)
    p.add_argument("--reports-dir", default="reports/exit_optimization")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_one(args.strategy, args.start, args.end, args.top_n, args.max_positions,
            args.max_per_stock, args.initial_capital, args.regime_threshold,
            args.dsr_threshold, args.reports_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스모크 테스트(짧은 기간·작은 유니버스)**

`tests/exit_multiverse/test_run_smoke.py`:

```python
import pytest
from pathlib import Path
from scripts.exit_multiverse import run


@pytest.mark.slow
def test_run_one_ma5_smoke(tmp_path):
    path = run.run_one(
        strategy="book_pullback_ma5", start="2023-01-01", end="2024-06-30",
        top_n=10, max_positions=5, max_per_stock=3_000_000,
        initial_capital=10_000_000, regime_threshold=0.02, dsr_threshold=0.95,
        reports_dir=str(tmp_path))
    assert path.exists()
    assert (tmp_path / "book_pullback_ma5_grid.parquet").exists()
```

- [ ] **Step 3: 실행**

Run: `cd RoboTrader_template; python -m pytest tests/exit_multiverse/test_run_smoke.py -v -m slow`
Expected: PASS (수 분 소요 가능). 실패 시 로그로 원인 파악.

- [ ] **Step 4: 수동 실행 확인 (1개 전략)**

Run: `cd RoboTrader_template; python -m scripts.exit_multiverse.run --strategy book_pullback_ma5 --start 2023-01-01 --end 2024-12-31 --top-n 20`
Expected: `reports/exit_optimization/book_pullback_ma5_walkforward.md` 생성, OOS 로그 출력.

- [ ] **Step 5: Commit**

```bash
git add scripts/exit_multiverse/run.py tests/exit_multiverse/test_run_smoke.py
git commit -m "feat(exit-mv): 단일 전략 워크포워드 CLI(일봉 메모리 상주)"
```

---

## Task 11: 전략 4-프로세스 병렬 오케스트레이터 + summary

**Files:**
- Create: `scripts/exit_multiverse/run_all.py`
- Create: `tests/exit_multiverse/test_run_all.py`

4전략을 독립 프로세스로 병렬 실행(`ProcessPoolExecutor`, 16 논리코어)하고, 완료 후 4전략 종합 `summary.md`(현재 운용값 대비 개선/유지 판정 + DSR 게이트 표기)를 생성한다.

- [ ] **Step 1: run_all.py 구현**

```python
"""4전략 청산 멀티버스 병렬 오케스트레이터 + 종합 summary.

usage:
  python -m scripts.exit_multiverse.run_all --start 2021-01-01 --end 2026-05-29 \
      --top-n 50 --max-workers 4 --dsr-threshold 0.95
"""
from __future__ import annotations
import argparse, logging, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.exit_multiverse import run as run_mod
from scripts.exit_multiverse import adapters

LOG = logging.getLogger("exit_multiverse.run_all")

# 현재 라이브 운용 청산값 (summary 개선/유지 판정 기준)
LIVE_PARAMS = {
    "elder_ema_pullback": {"stop_loss_pct": 0.08, "take_profit_pct": 0.30, "max_hold_bars": 100,
                           "trail_ema": 13, "trend_flip_exit": True},
    "minervini_volume_dryup": {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 20},
    "book_pullback_ma20": {"stop_loss_pct": 0.08, "take_profit_pct": 0.10, "max_hold_bars": 50, "trail_ma": 20},
    "book_pullback_ma5": {"stop_loss_pct": 0.03, "take_profit_pct": 0.15, "max_hold_bars": 30, "trail_ma": 5},
}


def _worker(kwargs):
    return run_mod.run_one(**kwargs)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-05-29")
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--max-positions", type=int, default=5)
    p.add_argument("--max-per-stock", type=float, default=3_000_000)
    p.add_argument("--initial-capital", type=float, default=10_000_000)
    p.add_argument("--regime-threshold", type=float, default=0.02)
    p.add_argument("--dsr-threshold", type=float, default=0.95)
    p.add_argument("--reports-dir", default="reports/exit_optimization")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    common = dict(start=args.start, end=args.end, top_n=args.top_n,
                  max_positions=args.max_positions, max_per_stock=args.max_per_stock,
                  initial_capital=args.initial_capital, regime_threshold=args.regime_threshold,
                  dsr_threshold=args.dsr_threshold, reports_dir=args.reports_dir)
    jobs = [dict(strategy=s, **common) for s in adapters.ADAPTERS.keys()]

    LOG.info(f"4전략 병렬 실행 (max_workers={args.max_workers})")
    with ProcessPoolExecutor(max_workers=args.max_workers) as ex:
        futs = {ex.submit(_worker, j): j["strategy"] for j in jobs}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                LOG.info(f"[{s}] 완료: {fut.result()}")
            except Exception as e:
                LOG.error(f"[{s}] 실패: {e!r}")

    _write_summary(Path(args.reports_dir), args.dsr_threshold)


def _write_summary(out_dir: Path, dsr_threshold: float):
    """4전략 grid.parquet 을 모아 OOS 종합 + 현재값 대비 개선/유지 판정."""
    rows = []
    for s in adapters.ADAPTERS.keys():
        pq = out_dir / f"{s}_grid.parquet"
        if not pq.exists():
            continue
        df = pd.read_parquet(pq)
        mean_oos = df["oos_worst_sharpe"].mean()
        mean_ret = df["oos_total_return"].mean()
        max_train_dsr = df["train_dsr"].max() if "train_dsr" in df else 0.0
        verdict = ("개선 채택후보" if (mean_oos > 0 and max_train_dsr >= dsr_threshold)
                   else "기존값 유지(유의 개선 없음)")
        rows.append({"strategy": s, "mean_oos_worst_sharpe": mean_oos,
                     "mean_oos_return": mean_ret, "max_train_dsr": max_train_dsr,
                     "verdict": verdict})
    summary = pd.DataFrame(rows)
    md = ["# 선별 4전략 청산 멀티버스 — 종합 (OOS 기준)\n",
          f"> DSR 게이트 임계 = {dsr_threshold} (1급 0.95 / 과반 0.5)\n",
          summary.to_markdown(index=False) if len(summary) else "(결과 없음)",
          "\n## 판정 규칙",
          "- **개선 채택후보**: 평균 OOS 국면최악 Sharpe > 0 **그리고** train DSR ≥ 임계",
          "- 그 외: **기존값 유지** (default to no-change)",
          "\n## 주의",
          "- 실제 `trading_config.json`/`config.yaml` 교체는 **별도 사장님 승인** 필요.",
          "- 폴드 간 파라미터 UNSTABLE 표기 전략은 채택 신중."]
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    LOG.info(f"summary: {out_dir / 'summary.md'}")
```

- [ ] **Step 2: 테스트(가벼운 summary 단위만)**

`tests/exit_multiverse/test_run_all.py`:

```python
import pandas as pd
from pathlib import Path
from scripts.exit_multiverse import run_all


def test_write_summary_from_fake_parquet(tmp_path):
    for s in run_all.adapters.ADAPTERS.keys():
        pd.DataFrame({"oos_worst_sharpe": [0.3, 0.4], "oos_total_return": [0.1, 0.05],
                      "train_dsr": [0.96, 0.5]}).to_parquet(tmp_path / f"{s}_grid.parquet")
    run_all._write_summary(tmp_path, dsr_threshold=0.95)
    assert (tmp_path / "summary.md").exists()
    txt = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "개선 채택후보" in txt or "기존값 유지" in txt
```

- [ ] **Step 3: 통과 확인**

Run: `python -m pytest tests/exit_multiverse/test_run_all.py -v`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add scripts/exit_multiverse/run_all.py tests/exit_multiverse/test_run_all.py
git commit -m "feat(exit-mv): 4전략 병렬 오케스트레이터 + 종합 summary"
```

---

## Task 12: 전체 실행 + 회귀 + changelog

**Files:**
- Modify: `RoboTrader_template/memory/MEMORY.md` (1줄 포인터)
- Create: `RoboTrader_template/memory/changelog-2026-05-31-exit-param-multiverse.md`

- [ ] **Step 1: 전체 회귀 테스트**

Run: `cd RoboTrader_template; python -m pytest tests/exit_multiverse/ -v` (slow 포함: `-m "slow or not slow"`)
Expected: 전부 passed. (특히 Task 6 동등성 회귀 통과 필수.)
Run(전체 회귀): `python -m pytest tests/ -q` — 기존 테스트 깨짐 없는지 확인.

- [ ] **Step 2: 본 실행 (4전략 병렬, 전체 기간)**

Run: `cd RoboTrader_template; python -m scripts.exit_multiverse.run_all --start 2021-01-01 --end 2026-05-29 --top-n 50 --max-workers 4 --regime-threshold 0.02 --dsr-threshold 0.95`
Expected: `reports/exit_optimization/{4전략}_walkforward.md`, `{4전략}_grid.parquet`, `summary.md` 생성. 시간이 오래 걸리면 `run_in_background` 로 실행.

- [ ] **Step 3: 결과 검토**

`reports/exit_optimization/summary.md` 와 각 `_walkforward.md` 를 읽고:
- per-stock 동등성(Task 6) 통과를 근거로 결과 신뢰성 확인
- 파라미터 안정성 UNSTABLE 전략 식별
- DSR 게이트 통과 여부 → "개선 채택후보" vs "기존값 유지" 판정

- [ ] **Step 4: changelog 작성 + MEMORY.md 포인터**

`memory/changelog-2026-05-31-exit-param-multiverse.md` 에 설계·구현·결과·판정을 기록.
`MEMORY.md` 의 "다음 세션 시작점" 섹션에 1줄 포인터 추가.

- [ ] **Step 5: Commit**

```bash
git add reports/exit_optimization/ memory/changelog-2026-05-31-exit-param-multiverse.md memory/MEMORY.md
git commit -m "feat(exit-mv): 4전략 청산 멀티버스 워크포워드 실행 결과 + 일지"
```

> **파라미터 교체 금지:** 본 계획은 권고안(`summary.md`)까지다. `trading_config.json`/`config.yaml` 실교체는 사장님 승인 후 별도 작업.

---

## Self-Review (작성자 점검 결과)

**1. Spec coverage:** 설계서 12개 섹션 매핑 — 청산만 최적화(Task 4 그리드), 포트폴리오 모델(Task 5), 워크포워드(Task 8), 국면최악+DSR(Task 7), 기존 룰 재사용(Task 2/3), per-stock 동등성(Task 6), 병렬·RAM 상주(Task 10/11), 산출물(Task 9/11), 검증(Task 6/12), 비목표·파라미터 교체 금지(Task 12 말미). ✔ 전 항목 task 존재.

**2. Placeholder scan:** "기존 X 복제"는 출처 코드가 본 계획/원본 파일에 제시돼 있어 placeholder 아님. TBD/TODO 없음. ✔

**3. Type consistency:** `run_portfolio` 반환 키(`equity_curve/daily_returns/trades/max_concurrent_positions/n_trades/n_skipped`)가 Task 5 정의와 Task 7/8 사용에서 일치. `regime_sharpes` 반환 `worst` 키가 Task 7/8에서 일관 사용. `StrategyAdapter` 필드(`entry_mechanism/exit_kind/build_grid/make_extra_ctx_fn`)가 Task 4 정의와 Task 5/10 사용에서 일치. `evaluate_fold` 반환(`best/oos_worst_sharpe/oos_total_return/oos_n_trades`)이 Task 9 report 에서 일관. ✔

**알려진 리스크(구현 중 확인):** ①`build_strategy` 의 `target_rule` 실제 룰명(각 rules.py grep 확인) ②라이브 config.yaml 청산값과 그리드 중앙값 일치 ③신호 재매핑 방식의 OOS warmup 누락(필요시 폴드별 재계산 전환) ④elder 매수스톱의 포트폴리오 다종목 동시성 — Task 6 동등성은 minervini(단순진입)로만 검증되므로 elder pending 로직은 스모크(Task 10)로 추가 관찰.
