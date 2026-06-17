# 동적 손익비 멀티버스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 8개 활성 전략에 박스권/ATR/볼린저폭 기준값으로 손익비를 동적 산출하고, 고정 손익비 대비 OOS 강건하게 우월한 조합이 있는지 측정 전용으로 검증한다.

**Architecture:** 기존 발굴 파이프라인(`exit_multiverse/portfolio_sim.run_portfolio` + `discovery/exit_adapters` + `strategy_gate` 게이트) 위에 per-trade 동적 손익비 레이어를 얹는다. 진입은 불변, 청산 sl/tp만 진입 시점에 종목별로 산출해 `position`에 기록. 동적 미설정 시 기존 고정 동작과 바이트동일(베이스라인 보존).

**Tech Stack:** Python 3.8+, pandas, pytest, psycopg2 (quant DB), 기존 `scripts/discovery/*` · `scripts/exit_multiverse/portfolio_sim.py` · `scripts/strategy_gate.py`.

**참조 spec:** `docs/superpowers/specs/2026-06-17-dynamic-risk-reward-multiverse-design.md`

---

## 파일 구조

```
신규:  scripts/discovery/reference_values.py     — compute_reference() (box/atr/bollinger PIT)
신규:  scripts/discovery/dynamic_risk.py          — resolve_risk(), eff_sl(), eff_tp() + 클램프 상수
신규:  scripts/discovery/live_strategy_signals.py — 8 라이브 전략 generate_signal → build_signals 어댑터
신규:  scripts/dynamic_rr_multiverse.py           — 오케스트레이터 (그리드·베이스라인·게이트·출력)
수정:  scripts/discovery/exit_adapters.py          — 3 어댑터가 eff_sl/eff_tp 사용
수정:  scripts/book_portfolio_multiverse.py        — _SLTPMHAdapter 가 eff_sl/eff_tp 사용
수정:  scripts/exit_multiverse/portfolio_sim.py    — run_portfolio 옵션 dynamic 주입
신규 테스트:
       tests/discovery/test_reference_values.py
       tests/discovery/test_dynamic_risk.py
       tests/discovery/test_dynamic_rr_exit_injection.py
       tests/discovery/test_live_strategy_signals.py
       tests/discovery/test_dynamic_rr_smoke.py
```

**불변식**: No-lookahead(`df.iloc[:i+1]`만), quant `daily_prices` SSOT(adj_factor 곱 금지), 비용 내장.

---

## Task 1: 라이브 전략 진입신호 어댑터 + 가용성 점검 (★최대 리스크 우선 해소)

**Files:**
- Create: `scripts/discovery/live_strategy_signals.py`
- Test: `tests/discovery/test_live_strategy_signals.py`

동적 청산은 진입 불변·sl/tp만 변경이라, 8전략 진입신호를 백테스트에서 재현해야 한다. 기존 `_precompute_signals(data, rule_obj, warmup, "daily")`(book_portfolio_multiverse.py:266)는 `rule_obj.generate_signal(code, df, tf)`를 호출한다. 라이브 전략 클래스도 동일 시그니처의 `generate_signal`을 가지므로 그대로 래핑한다.

- [ ] **Step 1: 라이브 전략 로더 헬퍼 작성**

```python
# scripts/discovery/live_strategy_signals.py
"""8 라이브 전략의 generate_signal 을 백테스트 build_signals 로 래핑."""
from __future__ import annotations
from typing import Dict, List
import pandas as pd
from strategies.config import StrategyLoader

# (folder_name, warmup_bars) — warmup 은 각 전략 min_len 보수값
LIVE_STRATEGIES = {
    "elder_ema_pullback": 70,
    "minervini_volume_dryup": 60,
    "deep_mr_dev20": 30,
    "daytrading_3methods_breakout": 25,
    "rs_leader": 65,
    "book_envelope_200d": 205,
    "book_pullback_ma20": 30,
    "book_pullback_ma5": 15,
}

def load_strategy(folder: str):
    """StrategyLoader 로 전략 인스턴스 1개 로드 (config.yaml 기반)."""
    return StrategyLoader.load_from_folder(folder)

def build_signals_for(folder: str, data: Dict[str, pd.DataFrame], warmup: int) -> Dict[str, List[int]]:
    """각 종목 df 에 대해 generate_signal 이 BUY 를 낸 bar index 목록 반환 (PIT)."""
    from strategies.base import SignalType
    strat = load_strategy(folder)
    out: Dict[str, List[int]] = {}
    for code, df in data.items():
        df = df.reset_index(drop=True)
        idxs: List[int] = []
        for i in range(warmup, len(df) - 1):
            sig = strat.generate_signal(code, df.iloc[: i + 1], "daily")
            if sig is not None and sig.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                idxs.append(i)
        out[code] = idxs
    return out
```

> **주의:** `StrategyLoader.load_from_folder` 의 실제 API 명은 Step 2 에서 검증한다. 다르면(예: `StrategyLoader(folder).load()`) 이 헬퍼만 수정.

- [ ] **Step 2: StrategyLoader API 확인**

Run: `python -c "from strategies.config import StrategyLoader; print([m for m in dir(StrategyLoader) if not m.startswith('__')])"`
Expected: 로더 메서드 목록 출력. `load_from_folder` 가 없으면 실제 로드 메서드명으로 Step 1 의 `load_strategy` 교체.

- [ ] **Step 3: 가용성 점검 테스트 작성 (실패 예상)**

```python
# tests/discovery/test_live_strategy_signals.py
import pandas as pd
import numpy as np
import pytest
from scripts.discovery.live_strategy_signals import LIVE_STRATEGIES, build_signals_for, load_strategy

def _synthetic_df(n=260):
    # 상승추세 + 눌림 합성 (대부분 전략이 최소 1신호 내도록)
    base = np.linspace(10000, 15000, n)
    noise = np.sin(np.linspace(0, 20, n)) * 400
    close = base + noise
    df = pd.DataFrame({
        "datetime": pd.date_range("2023-01-01", periods=n, freq="D").astype(str),
        "open": close * 0.99, "high": close * 1.02,
        "low": close * 0.98, "close": close,
        "volume": np.linspace(1e6, 3e6, n).astype(int),
    })
    return df

def test_all_live_strategies_loadable():
    for folder in LIVE_STRATEGIES:
        strat = load_strategy(folder)
        assert hasattr(strat, "generate_signal")

def test_build_signals_runs_for_each_strategy():
    data = {"TEST": _synthetic_df()}
    for folder, warmup in LIVE_STRATEGIES.items():
        sigs = build_signals_for(folder, data, warmup)
        assert "TEST" in sigs
        assert isinstance(sigs["TEST"], list)
```

- [ ] **Step 4: 실행해서 실패 확인**

Run: `python -m pytest tests/discovery/test_live_strategy_signals.py -v`
Expected: import/로드 단계에서 FAIL (모듈/메서드 미존재).

- [ ] **Step 5: 실패 해소까지 헬퍼 수정 후 통과**

Run: `python -m pytest tests/discovery/test_live_strategy_signals.py -v`
Expected: PASS (2 tests). 일부 전략이 합성데이터로 신호 0건이어도 `list` 반환이면 통과 — 신호 빈도는 Step 6 에서 실데이터로 확인.

- [ ] **Step 6: 실데이터 가용성 probe 스크립트 (1회성, 결과 기록)**

```python
# scripts/discovery/live_strategy_signals.py  (말미에 __main__ 추가)
if __name__ == "__main__":
    # 실 quant 유니버스로 8전략 신호 빈도 점검 — v1 포함 가능 전략 확정용
    from scripts.book_portfolio_multiverse import _load_universe_data  # 유니버스 로더 (Step 6a 확인)
    data = _load_universe_data(top_n=100)  # 실제 함수명/시그니처는 6a 에서 확인
    for folder, warmup in LIVE_STRATEGIES.items():
        sigs = build_signals_for(folder, data, warmup)
        total = sum(len(v) for v in sigs.values())
        names = sum(1 for v in sigs.values() if v)
        print(f"{folder:32} 신호 {total:5}건 / {names:3}종목")
```

- [ ] **Step 6a: 유니버스 로더 함수명 확인**

Run: `python -c "import scripts.book_portfolio_multiverse as m; print([f for f in dir(m) if 'load' in f.lower() or 'univ' in f.lower()])"`
Expected: 유니버스/데이터 로더 함수 목록. probe 의 `_load_universe_data` 를 실제 함수로 교체.

- [ ] **Step 7: probe 실행 — v1 포함 전략 확정**

Run: `python scripts/discovery/live_strategy_signals.py`
Expected: 8전략 신호 빈도 출력. **신호 < 30건 전략은 v1 제외 후보** — 결과를 `reports/discovery/dynamic_rr/_signal_probe.txt` 에 저장하고 SUMMARY 에 명시.

- [ ] **Step 8: Commit**

```bash
git add scripts/discovery/live_strategy_signals.py tests/discovery/test_live_strategy_signals.py
git commit -m "feat(dynamic-rr): 라이브 8전략 진입신호 백테스트 어댑터 + 가용성 probe"
```

---

## Task 2: ReferenceValueProvider (compute_reference)

**Files:**
- Create: `scripts/discovery/reference_values.py`
- Test: `tests/discovery/test_reference_values.py`

- [ ] **Step 1: PIT 정확성 테스트 작성 (실패 예상)**

```python
# tests/discovery/test_reference_values.py
import numpy as np
import pandas as pd
import pytest
from scripts.discovery.reference_values import compute_reference

def _df():
    # i=0..9, close/high/low 명시 — 박스 계산 검증용
    high = [10,11,12,11,10, 13,12,11,12,13]
    low  = [ 9, 9,10, 9, 8, 10,10, 9,10,11]
    close= [ 9,10,11,10, 9, 12,11,10,11,12]
    return pd.DataFrame({
        "datetime": pd.date_range("2023-01-01", periods=10, freq="D").astype(str),
        "open": close, "high": high, "low": low, "close": close,
        "volume": [1000]*10})

def test_box_uses_only_past_bars():
    df = _df()
    # i=4, n=5 → high[0:5]=max 12, low[0:5]=min 8 → box_height=4, box_low=8
    ref = compute_reference(df, 4, "box", n=5)
    assert ref["box_low"] == 8.0
    assert ref["box_height"] == 4.0

def test_box_no_lookahead_changes_with_i():
    df = _df()
    # i=9, n=5 → high[5:10]=13, low[5:10]=9 → height 4, low 9
    ref = compute_reference(df, 9, "box", n=5)
    assert ref["box_low"] == 9.0
    assert ref["box_height"] == 4.0

def test_atr_positive_and_pit():
    df = _df()
    ref = compute_reference(df, 9, "atr", n=5)
    assert ref["atr"] > 0

def test_bollinger_width_positive():
    df = _df()
    ref = compute_reference(df, 9, "bollinger", n=5, bb_k=2.0)
    assert ref["bb_width"] > 0

def test_insufficient_warmup_returns_none():
    df = _df()
    assert compute_reference(df, 2, "box", n=5) is None  # i+1 < n
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `python -m pytest tests/discovery/test_reference_values.py -v`
Expected: FAIL (module 미존재).

- [ ] **Step 3: compute_reference 구현**

```python
# scripts/discovery/reference_values.py
"""진입봉 PIT 기준값 산출 — box(고저 레인지) / atr / bollinger 밴드폭.
모든 계산은 df.iloc[:i+1] (bar i 이하)만 사용 = no-lookahead."""
from __future__ import annotations
from typing import Optional
import pandas as pd

def compute_reference(df: pd.DataFrame, i: int, ref_type: str, n: int, bb_k: float = 2.0) -> Optional[dict]:
    if i + 1 < n:
        return None
    win = df.iloc[i - n + 1 : i + 1]
    high = win["high"].astype(float)
    low = win["low"].astype(float)
    close = win["close"].astype(float)
    if ref_type == "box":
        box_high = float(high.max()); box_low = float(low.min())
        return {"box_low": box_low, "box_height": box_high - box_low}
    if ref_type == "atr":
        prev_close = df["close"].astype(float).iloc[i - n : i]  # n개 이전 종가
        h = high.values; l = low.values
        pc = prev_close.values if len(prev_close) == n else close.shift(1).fillna(close).values
        tr = [max(h[k] - l[k], abs(h[k] - pc[k]), abs(l[k] - pc[k])) for k in range(n)]
        atr = float(pd.Series(tr).mean())
        return {"atr": atr} if atr > 0 else None
    if ref_type == "bollinger":
        std = float(close.std(ddof=0))
        width = 2.0 * bb_k * std
        return {"bb_width": width} if width > 0 else None
    raise ValueError(f"unknown ref_type: {ref_type}")
```

- [ ] **Step 4: 실행해서 통과 확인**

Run: `python -m pytest tests/discovery/test_reference_values.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/discovery/reference_values.py tests/discovery/test_reference_values.py
git commit -m "feat(dynamic-rr): compute_reference (box/atr/bollinger PIT 기준값)"
```

---

## Task 3: DynamicRiskResolver (resolve_risk + eff_sl/eff_tp)

**Files:**
- Create: `scripts/discovery/dynamic_risk.py`
- Test: `tests/discovery/test_dynamic_risk.py`

- [ ] **Step 1: 클램프·RR·fallback 테스트 작성 (실패 예상)**

```python
# tests/discovery/test_dynamic_risk.py
import pytest
from scripts.discovery.dynamic_risk import resolve_risk, eff_sl, eff_tp, SL_FLOOR, SL_CAP, TP_CAP

def test_atr_rr_preserved():
    # atr=200, entry=10000, sl_mult=1.0 → sl=2% → 하한 3% 클램프, tp=rr*sl
    sl, tp, clamped = resolve_risk("atr", {"atr": 200}, 10000, sl_mult=2.0, rr=2.0)
    # sl=2*200/10000=4% (하한 위), tp=2*4%=8%
    assert abs(sl - 0.04) < 1e-9
    assert abs(tp - 0.08) < 1e-9
    assert clamped is False

def test_sl_floor_applied():
    sl, tp, clamped = resolve_risk("atr", {"atr": 100}, 10000, sl_mult=1.0, rr=2.0)
    # raw sl=1% < 3% → floor
    assert sl == SL_FLOOR

def test_sl_cap_applied():
    sl, tp, clamped = resolve_risk("atr", {"atr": 2000}, 10000, sl_mult=1.0, rr=1.0)
    # raw sl=20% > 15% → cap
    assert sl == SL_CAP

def test_tp_cap_clamps_and_flags():
    # sl=15%(cap), rr=3 → tp=45% > 30% → clamp to 30%, clamped=True
    sl, tp, clamped = resolve_risk("atr", {"atr": 2000}, 10000, sl_mult=1.0, rr=3.0)
    assert tp == TP_CAP
    assert clamped is True

def test_box_structural():
    # box_low=9000, box_height=1000, entry=10000, buffer=0 → sl=(10000-9000)/10000=10%, tp=1000*2/10000=20%
    sl, tp, clamped = resolve_risk("box", {"box_low": 9000, "box_height": 1000}, 10000, sl_mult=1.0, rr=2.0, buffer=0.0)
    assert abs(sl - 0.10) < 1e-9
    assert abs(tp - 0.20) < 1e-9

def test_none_ref_returns_none():
    assert resolve_risk("atr", None, 10000, 1.0, 2.0) is None

def test_eff_sl_fallback_to_params():
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12}
    assert eff_sl({}, params) == 0.08          # position 에 sl_pct 없음 → params
    assert eff_tp({}, params) == 0.12
    assert eff_sl({"sl_pct": 0.05}, params) == 0.05  # position 우선
    assert eff_tp({"tp_pct": 0.20}, params) == 0.20
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `python -m pytest tests/discovery/test_dynamic_risk.py -v`
Expected: FAIL (module 미존재).

- [ ] **Step 3: dynamic_risk 구현**

```python
# scripts/discovery/dynamic_risk.py
"""per-trade 동적 손익비 산출 + 청산 어댑터용 effective sl/tp 헬퍼.
import 의존 없음(leaf 모듈) — exit_adapters / _SLTPMHAdapter 양쪽이 안전하게 import."""
from __future__ import annotations
from typing import Optional, Tuple

SL_FLOOR = 0.03   # 손절 하한 (라이브 옵션 D-A)
SL_CAP = 0.15     # 손절 상한
TP_CAP = 0.30     # 익절 상한 (elder 30% 보존)

def resolve_risk(ref_type: str, ref: Optional[dict], entry_price: float,
                 sl_mult: float, rr: float, buffer: float = 0.0
                 ) -> Optional[Tuple[float, float, bool]]:
    """returns (sl_pct, tp_pct, tp_clamped) 또는 None(기준값 부재 → 호출자 fallback)."""
    if ref is None or entry_price <= 0:
        return None
    if ref_type == "box":
        sl_level = ref["box_low"] * (1.0 - buffer)
        sl_pct = (entry_price - sl_level) / entry_price
        tp_pct = ref["box_height"] * rr / entry_price
    elif ref_type == "atr":
        sl_pct = sl_mult * ref["atr"] / entry_price
        tp_pct = rr * sl_pct
    elif ref_type == "bollinger":
        sl_pct = sl_mult * ref["bb_width"] / entry_price
        tp_pct = rr * sl_pct
    else:
        raise ValueError(f"unknown ref_type: {ref_type}")
    # SL 클램프
    sl_pct = max(SL_FLOOR, min(SL_CAP, sl_pct))
    # TP 하한 = SL (RR>=1 보장)
    tp_pct = max(tp_pct, sl_pct)
    # TP 상한 클램프 + 플래그
    clamped = False
    if tp_pct > TP_CAP:
        tp_pct = TP_CAP
        clamped = True
    return (sl_pct, tp_pct, clamped)

def eff_sl(position: dict, params: dict) -> float:
    v = position.get("sl_pct")
    return v if v is not None else params["stop_loss_pct"]

def eff_tp(position: dict, params: dict) -> float:
    v = position.get("tp_pct")
    return v if v is not None else params["take_profit_pct"]
```

- [ ] **Step 4: 실행해서 통과 확인**

Run: `python -m pytest tests/discovery/test_dynamic_risk.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/discovery/dynamic_risk.py tests/discovery/test_dynamic_risk.py
git commit -m "feat(dynamic-rr): resolve_risk 클램프/RR + eff_sl/eff_tp fallback 헬퍼"
```

---

## Task 4: 청산 어댑터에 eff_sl/eff_tp 배선 (베이스라인 바이트동일 보존)

**Files:**
- Modify: `scripts/discovery/exit_adapters.py` (3 어댑터의 sl/tp 읽기)
- Modify: `scripts/book_portfolio_multiverse.py:113-127` (`_SLTPMHAdapter`)
- Test: `tests/discovery/test_dynamic_rr_exit_injection.py`

- [ ] **Step 1: 바이트동일 + position 우선 테스트 작성 (실패 예상)**

```python
# tests/discovery/test_dynamic_rr_exit_injection.py
import pandas as pd
from scripts.discovery.exit_adapters import MAReversionExitAdapter
from scripts.book_portfolio_multiverse import _SLTPMHAdapter

def _df():
    close = [10000, 10100, 9000, 9500, 10000]  # idx2 에서 -10% 하락
    return pd.DataFrame({"datetime": range(5), "open": close, "high": close,
                         "low": close, "close": close, "volume": [1]*5})

def test_sltpmh_baseline_unchanged_when_no_position_override():
    df = _df()
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 100}
    pos = {"entry_idx": 1, "entry_price": 10000, "qty": 1}  # sl_pct 없음
    # idx2 close=9000 → ret -10% <= -8% → stop_loss (기존 고정과 동일)
    assert _SLTPMHAdapter.exit_reason(df, 2, pos, params) == "stop_loss"

def test_sltpmh_position_override_takes_precedence():
    df = _df()
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 100}
    pos = {"entry_idx": 1, "entry_price": 10000, "qty": 1, "sl_pct": 0.15, "tp_pct": 0.30}
    # sl 15% 이므로 -10% 는 손절 아님 → None (max_hold 도 아님)
    assert _SLTPMHAdapter.exit_reason(df, 2, pos, params) is None
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `python -m pytest tests/discovery/test_dynamic_rr_exit_injection.py -v`
Expected: 2번째 테스트 FAIL (현재 params 만 읽어 -10%를 손절 처리).

- [ ] **Step 3: `_SLTPMHAdapter` 수정**

`scripts/book_portfolio_multiverse.py` 상단 import 에 추가:
```python
from scripts.discovery.dynamic_risk import eff_sl, eff_tp
```
`_SLTPMHAdapter.exit_reason` (113-127) 의 비교를 교체:
```python
    @staticmethod
    def exit_reason(df, i, position, params) -> Optional[str]:
        entry_price = position["entry_price"]
        cur_close = float(df.iloc[i]["close"])
        ret = (cur_close - entry_price) / entry_price
        hold_bars = i - position["entry_idx"]
        if ret <= -eff_sl(position, params):
            return "stop_loss"
        if ret >= eff_tp(position, params):
            return "take_profit"
        if hold_bars >= params["max_hold_bars"]:
            return "max_hold"
        return None
```

- [ ] **Step 4: `exit_adapters.py` 3 어댑터 수정**

상단 import 추가: `from scripts.discovery.dynamic_risk import eff_sl, eff_tp`
각 어댑터(`CloseAboveMAExitAdapter`, `MAReversionExitAdapter`, `BBReversionExitAdapter`)의 다음 두 줄을 교체:
```python
        if ret <= -params["stop_loss_pct"]:    →    if ret <= -eff_sl(position, params):
        if ret >= params["take_profit_pct"]:   →    if ret >= eff_tp(position, params):
```

- [ ] **Step 5: 실행해서 통과 확인**

Run: `python -m pytest tests/discovery/test_dynamic_rr_exit_injection.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: 기존 discovery/exit 회귀 확인**

Run: `python -m pytest tests/discovery tests/exit_multiverse -q`
Expected: 기존 통과 테스트 green 유지 (신규 실패 0).

- [ ] **Step 7: Commit**

```bash
git add scripts/discovery/exit_adapters.py scripts/book_portfolio_multiverse.py tests/discovery/test_dynamic_rr_exit_injection.py
git commit -m "feat(dynamic-rr): 청산 어댑터 eff_sl/eff_tp 배선 (베이스라인 바이트동일 보존)"
```

---

## Task 5: run_portfolio 옵션 동적 주입

**Files:**
- Modify: `scripts/exit_multiverse/portfolio_sim.py` (run_portfolio 진입부 ~line 173)
- Test: `tests/discovery/test_dynamic_rr_smoke.py` (Step 1-2 만, 나머지는 Task 6)

진입 시점(체결 bar i+1, 신호 bar i)에서 기준값 산출 → resolve → `positions[code]` 에 `sl_pct`/`tp_pct` 기록. 동적 미설정(`dyn=None`)이면 기존과 동일.

- [ ] **Step 1: 동적 주입 스모크 테스트 작성 (실패 예상)**

```python
# tests/discovery/test_dynamic_rr_smoke.py
import pandas as pd, numpy as np
from scripts.exit_multiverse.portfolio_sim import run_portfolio
from scripts.book_portfolio_multiverse import _SLTPMHAdapter

def _data():
    close = np.array([10000,10100,10200,9000,9500,10000,10100,10200,10300,10400], float)
    df = pd.DataFrame({"datetime": range(10), "open": close, "high": close*1.01,
                       "low": close*0.99, "close": close, "volume": [1]*10})
    return {"AAA": df}

def test_dynamic_resolver_records_per_trade_sltp():
    data = _data()
    signals = {"AAA": [1]}  # bar1 진입신호 → bar2 체결
    params = {"stop_loss_pct": 0.99, "take_profit_pct": 0.99, "max_hold_bars": 99}
    dyn = {"ref_type": "box", "n": 2, "sl_mult": 1.0, "rr": 2.0, "buffer": 0.0, "bb_k": 2.0}
    res = run_portfolio(data, signals, _SLTPMHAdapter(), params,
                        max_positions=5, dyn=dyn)
    # 동적 sl/tp 가 기록·적용되어 bar3 -10% 급락에서 손절 발생(고정 99%면 청산 안 됨)
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    assert any(t["reason"] == "stop_loss" for t in sells)
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `python -m pytest tests/discovery/test_dynamic_rr_smoke.py::test_dynamic_resolver_records_per_trade_sltp -v`
Expected: FAIL (`run_portfolio() got unexpected keyword 'dyn'`).

- [ ] **Step 3: run_portfolio 에 dyn 파라미터 추가**

`scripts/exit_multiverse/portfolio_sim.py` 상단 import:
```python
from scripts.discovery.reference_values import compute_reference
from scripts.discovery.dynamic_risk import resolve_risk
```
`def run_portfolio(...)` 시그니처에 `dyn: dict = None` 추가 (기본 None = 기존 동작).
진입 직후 `positions[code] = {"entry_idx": i + 1, "entry_price": fill, "qty": qty, ...}` (line ~173) 바로 다음에 삽입:
```python
            if dyn is not None:
                ref = compute_reference(df, i, dyn["ref_type"], dyn["n"], dyn.get("bb_k", 2.0))
                resolved = resolve_risk(dyn["ref_type"], ref, fill,
                                        dyn.get("sl_mult", 1.0), dyn["rr"], dyn.get("buffer", 0.0))
                if resolved is not None:
                    sl_pct, tp_pct, clamped = resolved
                    positions[code]["sl_pct"] = sl_pct
                    positions[code]["tp_pct"] = tp_pct
                    positions[code]["tp_clamped"] = clamped
                # resolved None(기준값 부재) → sl_pct 미기록 → eff_sl fallback(고정 params)
```
> `df` 는 진입 루프에서 `data[code]` 로 접근 가능해야 함. 루프 변수명이 다르면(예: `df = data[code]`) 그대로 사용. Step 4 에서 실패 시 변수명 확인.

- [ ] **Step 4: 실행해서 통과 확인**

Run: `python -m pytest tests/discovery/test_dynamic_rr_smoke.py::test_dynamic_resolver_records_per_trade_sltp -v`
Expected: PASS.

- [ ] **Step 5: 기존 run_portfolio 회귀 확인 (dyn=None 경로 불변)**

Run: `python -m pytest tests/exit_multiverse -q`
Expected: 기존 통과 green 유지.

- [ ] **Step 6: Commit**

```bash
git add scripts/exit_multiverse/portfolio_sim.py tests/discovery/test_dynamic_rr_smoke.py
git commit -m "feat(dynamic-rr): run_portfolio 옵션 dyn 주입 (진입시 per-trade sl/tp 기록)"
```

---

## Task 6: 오케스트레이터 — 그리드·베이스라인·출력

**Files:**
- Create: `scripts/dynamic_rr_multiverse.py`
- Test: `tests/discovery/test_dynamic_rr_smoke.py` (자기참조 스모크 추가)

- [ ] **Step 1: fixed셀 자기참조 ΔSharpe==0 스모크 테스트 추가 (실패 예상)**

```python
# tests/discovery/test_dynamic_rr_smoke.py (추가)
from scripts.dynamic_rr_multiverse import run_strategy_grid, GRID

def test_fixed_cell_matches_baseline_self_reference():
    # ref_type=fixed 셀의 metrics 는 베이스라인과 동일 → ΔSharpe==0
    data = _data()
    signals = {"AAA": [1]}
    base_params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 20}
    rows = run_strategy_grid("test_strat", data, signals, base_params,
                             grid=[{"ref_type": "fixed"}])
    assert len(rows) == 1
    assert abs(rows[0]["delta_sharpe"]) < 1e-9
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `python -m pytest tests/discovery/test_dynamic_rr_smoke.py::test_fixed_cell_matches_baseline_self_reference -v`
Expected: FAIL (module 미존재).

- [ ] **Step 3: 오케스트레이터 구현**

```python
# scripts/dynamic_rr_multiverse.py
"""동적 손익비 멀티버스 오케스트레이터 (측정 전용).
전략별: 베이스라인(고정) + 동적 그리드 셀 → run_portfolio → metrics → ΔSharpe."""
from __future__ import annotations
from typing import Dict, List
import pandas as pd
from scripts.exit_multiverse.portfolio_sim import run_portfolio
from scripts.book_portfolio_multiverse import _SLTPMHAdapter
from scripts.book_param_multiverse import _daily_metrics  # equity/trades → metrics

# 그리드 축 (spec 3.2) — 거친 격자
def build_grid() -> List[dict]:
    cells = [{"ref_type": "fixed"}]
    for ref in ("box", "atr", "bollinger"):
        for n in (10, 20):
            for sl_mult in (1.0, 1.5, 2.0):
                for rr in (1.0, 1.5, 2.0, 3.0):
                    cells.append({"ref_type": ref, "n": n, "sl_mult": sl_mult,
                                  "rr": rr, "buffer": 0.0, "bb_k": 2.0})
    return cells

GRID = build_grid()

def _metrics_for(data, signals, base_params, dyn, max_positions=5) -> dict:
    res = run_portfolio(data, signals, _SLTPMHAdapter(), base_params,
                        max_positions=max_positions, dyn=dyn)
    eq = res.get("equity_curve") or [10_000_000]
    m = _daily_metrics(10_000_000, eq, res["trades"])
    m["n_trades"] = sum(1 for t in res["trades"] if t["side"] == "sell")
    m["clamp_frac"] = (sum(1 for t in res["trades"]
                           if t.get("side") == "buy" and False)  # buy 엔 clamp 정보 없음
                       )
    return m

def run_strategy_grid(name, data, signals, base_params, grid=None) -> List[dict]:
    grid = grid if grid is not None else GRID
    base_m = _metrics_for(data, signals, base_params, dyn=None)
    base_sharpe = base_m.get("sharpe", 0.0)
    rows = []
    for cell in grid:
        dyn = None if cell["ref_type"] == "fixed" else cell
        m = _metrics_for(data, signals, base_params, dyn=dyn)
        rows.append({"strategy": name, **cell,
                     "sharpe": m.get("sharpe", 0.0),
                     "cagr": m.get("cagr", 0.0),
                     "mdd": m.get("mdd", 0.0),
                     "n_trades": m.get("n_trades", 0),
                     "delta_sharpe": m.get("sharpe", 0.0) - base_sharpe})
    return rows
```
> `_daily_metrics` 의 반환 키(`sharpe`/`cagr`/`mdd`)는 Step 4 에서 확인 후 맞춤. clamp_frac 정확 집계는 Task 7 에서 trades 의 per-sell clamp 전파와 함께 구현(여기선 placeholder 0 제거하고 Task 7 에서 보강).

- [ ] **Step 4: `_daily_metrics` 반환 키 확인 후 맞춤**

Run: `python -c "import inspect, scripts.book_param_multiverse as m; print(inspect.getsource(m._daily_metrics))" | head -40`
Expected: 반환 dict 키 확인 → `run_strategy_grid` 의 `m.get("sharpe"/"cagr"/"mdd")` 를 실제 키명으로 교체. clamp_frac placeholder 라인 삭제.

- [ ] **Step 5: 실행해서 통과 확인**

Run: `python -m pytest tests/discovery/test_dynamic_rr_smoke.py -v`
Expected: PASS (전체 3 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/dynamic_rr_multiverse.py tests/discovery/test_dynamic_rr_smoke.py
git commit -m "feat(dynamic-rr): 오케스트레이터 그리드+베이스라인 (fixed셀 자기참조 0 검증)"
```

---

## Task 7: OOS 강건성 게이트 + 클램프 추적

**Files:**
- Modify: `scripts/dynamic_rr_multiverse.py` (게이트·train/test·부트스트랩·clamp_frac)
- Modify: `scripts/exit_multiverse/portfolio_sim.py` (sell trade 에 tp_clamped 전파)
- Test: `tests/discovery/test_dynamic_rr_gate.py`

- [ ] **Step 1: 게이트 판정 테스트 작성 (실패 예상)**

```python
# tests/discovery/test_dynamic_rr_gate.py
from scripts.dynamic_rr_multiverse import evaluate_dynamic_gates

def test_winner_requires_both_windows_positive():
    cell = {"delta_sharpe_train": 0.3, "sharpe_train": 0.5,
            "delta_sharpe_test": 0.2, "sharpe_test": 0.4,
            "boot_dsharpe_p05": 0.05, "delta_sharpe_cost": 0.1,
            "n_trades": 50, "clamp_frac": 0.05}
    ok, _ = evaluate_dynamic_gates(cell)
    assert ok is True

def test_test_window_negative_fails():
    cell = {"delta_sharpe_train": 0.3, "sharpe_train": 0.5,
            "delta_sharpe_test": -0.1, "sharpe_test": 0.4,
            "boot_dsharpe_p05": 0.05, "delta_sharpe_cost": 0.1,
            "n_trades": 50, "clamp_frac": 0.05}
    ok, reason = evaluate_dynamic_gates(cell)
    assert ok is False and "test" in reason.lower()

def test_high_clamp_frac_excluded():
    cell = {"delta_sharpe_train": 0.3, "sharpe_train": 0.5,
            "delta_sharpe_test": 0.2, "sharpe_test": 0.4,
            "boot_dsharpe_p05": 0.05, "delta_sharpe_cost": 0.1,
            "n_trades": 50, "clamp_frac": 0.30}
    ok, reason = evaluate_dynamic_gates(cell)
    assert ok is False and "clamp" in reason.lower()

def test_few_trades_fails():
    cell = {"delta_sharpe_train": 0.3, "sharpe_train": 0.5,
            "delta_sharpe_test": 0.2, "sharpe_test": 0.4,
            "boot_dsharpe_p05": 0.05, "delta_sharpe_cost": 0.1,
            "n_trades": 10, "clamp_frac": 0.05}
    ok, reason = evaluate_dynamic_gates(cell)
    assert ok is False and "trade" in reason.lower()
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `python -m pytest tests/discovery/test_dynamic_rr_gate.py -v`
Expected: FAIL (`evaluate_dynamic_gates` 미존재).

- [ ] **Step 3: evaluate_dynamic_gates 구현**

```python
# scripts/dynamic_rr_multiverse.py (추가)
MIN_TRADES = 30
MAX_CLAMP_FRAC = 0.20

def evaluate_dynamic_gates(cell: dict):
    """4관문: OOS(train&test ΔSharpe>0 & Sharpe>0) + 부트스트랩 p05>0 + 비용후 ΔSharpe>0
    + 거래수>=MIN_TRADES, 그리고 clamp_frac<=MAX_CLAMP_FRAC."""
    if cell["n_trades"] < MIN_TRADES:
        return False, f"few_trades({cell['n_trades']}<{MIN_TRADES})"
    if cell["clamp_frac"] > MAX_CLAMP_FRAC:
        return False, f"clamp_frac_high({cell['clamp_frac']:.2f})"
    if not (cell["delta_sharpe_train"] > 0 and cell["sharpe_train"] > 0):
        return False, "train_window_not_positive"
    if not (cell["delta_sharpe_test"] > 0 and cell["sharpe_test"] > 0):
        return False, "test_window_not_positive"
    if cell["boot_dsharpe_p05"] <= 0:
        return False, "bootstrap_p05<=0"
    if cell["delta_sharpe_cost"] <= 0:
        return False, "cost_stress_negative"
    return True, "PASS"
```

- [ ] **Step 4: 실행해서 통과 확인**

Run: `python -m pytest tests/discovery/test_dynamic_rr_gate.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: clamp_frac 정확 집계 — sell trade 에 tp_clamped 전파**

`portfolio_sim.py` 청산 trade dict(line ~92)에 `"tp_clamped": pos.get("tp_clamped", False)` 추가. `_metrics_for` 에서:
```python
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    m["n_trades"] = len(sells)
    m["clamp_frac"] = (sum(1 for t in sells if t.get("tp_clamped")) / len(sells)) if sells else 0.0
```

- [ ] **Step 6: train/test 분리 + 부트스트랩 + 비용스트레스 배선**

`run_strategy_grid` 를 확장: 각 셀을 train(2021~2024.6)/test(2024.7~2026.5) 구간으로 각각 `run_portfolio` 실행해 `sharpe_train/test`, `delta_sharpe_train/test` 계산. 부트스트랩·비용스트레스는 `strategy_gate` 의 기존 헬퍼 재사용:
```python
from scripts.strategy_gate import sharpe as _sharpe
# 부트스트랩: 거래 pnl 블록 리샘플 → ΔSharpe 분포 p05
# 비용스트레스: base_params 의 slippage 를 +0.003 한 재실행 ΔSharpe
```
> 기존 `strategy_gate` 의 부트스트랩/비용 함수 정확 명칭은 `python -c "import scripts.strategy_gate as g; print([f for f in dir(g) if 'boot' in f or 'cost' in f])"` 로 확인 후 호출.

- [ ] **Step 7: 회귀 + 게이트 테스트 통과 확인**

Run: `python -m pytest tests/discovery -q`
Expected: PASS, 기존 green 유지.

- [ ] **Step 8: Commit**

```bash
git add scripts/dynamic_rr_multiverse.py scripts/exit_multiverse/portfolio_sim.py tests/discovery/test_dynamic_rr_gate.py
git commit -m "feat(dynamic-rr): OOS 강건성 게이트 + clamp_frac 추적/제외"
```

---

## Task 8: 전체 실행 + SUMMARY + verifier

**Files:**
- Modify: `scripts/dynamic_rr_multiverse.py` (`__main__`: 8전략 실행·출력)
- Create: `reports/discovery/dynamic_rr/` (출력)

- [ ] **Step 1: 실행 엔트리 작성**

```python
# scripts/dynamic_rr_multiverse.py (__main__)
if __name__ == "__main__":
    import os
    from scripts.discovery.live_strategy_signals import LIVE_STRATEGIES, build_signals_for
    from scripts.book_portfolio_multiverse import _load_universe_data  # Task1 6a 확인된 실명
    os.makedirs("reports/discovery/dynamic_rr", exist_ok=True)
    data = _load_universe_data(top_n=300)
    summary_rows = []
    for folder, warmup in LIVE_STRATEGIES.items():
        signals = build_signals_for(folder, data, warmup)
        if sum(len(v) for v in signals.values()) < 30:
            print(f"SKIP {folder}: 신호<30 (v1 제외)"); continue
        # base_params 는 전략 config.yaml 의 risk 값 로드
        base_params = _load_base_params(folder)  # Step 2
        rows = run_strategy_grid(folder, data, signals, base_params)
        for r in rows:
            r["gate_pass"], r["gate_reason"] = evaluate_dynamic_gates(r) if "delta_sharpe_test" in r else (False, "no_oos")
        pd.DataFrame(rows).to_csv(f"reports/discovery/dynamic_rr/{folder}_grid.tsv", sep="\t", index=False)
        winners = [r for r in rows if r.get("gate_pass")]
        summary_rows.append({"strategy": folder, "winners": len(winners),
                             "best": max((r["delta_sharpe"] for r in rows), default=0.0)})
    pd.DataFrame(summary_rows).to_csv("reports/discovery/dynamic_rr/_summary.tsv", sep="\t", index=False)
    print("DONE — reports/discovery/dynamic_rr/")
```

- [ ] **Step 2: `_load_base_params` 구현 (config.yaml risk 로드)**

```python
def _load_base_params(folder: str) -> dict:
    import yaml
    with open(f"strategies/{folder}/config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    r = cfg.get("risk", {})
    return {"stop_loss_pct": float(r["stop_loss_pct"]),
            "take_profit_pct": float(r["take_profit_pct"]),
            "max_hold_bars": int(r.get("max_hold_days", r.get("max_holding_days", 20)))}
```

- [ ] **Step 3: 전체 실행**

Run: `python scripts/dynamic_rr_multiverse.py`
Expected: `reports/discovery/dynamic_rr/<strategy>_grid.tsv` (전략별) + `_summary.tsv` 생성. 콘솔에 SKIP/DONE 로그.

- [ ] **Step 4: SUMMARY 문서 작성**

`reports/discovery/dynamic_rr/_DYNAMIC_RR_SUMMARY.md` 작성: 전략별 승자 셀(ref_type/lookback/sl_mult/RR), train/test ΔSharpe, 거래수, 게이트 통과/탈락 사유. **train만 좋고 test 음수인 셀은 "false positive" 명시**. 제외된 전략(신호<30)·clamp 제외 셀 명시.

- [ ] **Step 5: verifier 대조**

Run: oh-my-claudecode:verifier 에이전트 또는 수동으로 SUMMARY 수치를 `_grid.tsv` 와 대조 (체리피킹·미보고 cap 없음 확인).

- [ ] **Step 6: 전체 회귀**

Run: `python -m pytest tests/discovery tests/exit_multiverse -q`
Expected: green 유지.

- [ ] **Step 7: Commit**

```bash
git add scripts/dynamic_rr_multiverse.py reports/discovery/dynamic_rr/
git commit -m "feat(dynamic-rr): 8전략 멀티버스 전체 실행 + SUMMARY (측정 전용)"
```

---

## Self-Review 체크 (작성자 수행 완료)

- **Spec 커버리지**: §2 아키텍처→T4·T5, §3 기준값/그리드→T2·T3·T6, §4 게이트/베이스라인→T6·T7, §5 테스트→각 T, §6 파일→파일구조, §7 리스크(진입신호)→T1. ✅
- **Placeholder**: 각 스텝에 실제 코드/명령 포함. 외부 의존 API명(StrategyLoader, _load_universe_data, _daily_metrics 키, strategy_gate 부트스트랩 함수)은 **"확인 스텝"으로 명시**(T1S2/S6a, T6S4, T7S6) — 추정 금지·실행으로 확정.
- **타입 일관성**: `dyn` dict 키(ref_type/n/sl_mult/rr/buffer/bb_k), `resolve_risk` 반환 `(sl_pct,tp_pct,clamped)`, `eff_sl/eff_tp(position,params)`, cell dict 키(delta_sharpe_train/test 등) 전 태스크 일관. ✅
- **Spec 정밀화 1건**: spec "셀 무효"(RR×SL>TP상한)를 per-trade 클램프 + cell clamp_frac>20% 제외로 운영화(silent cap 금지). T3·T7 반영.
