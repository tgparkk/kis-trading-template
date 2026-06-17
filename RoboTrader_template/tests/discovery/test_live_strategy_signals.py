"""TDD 테스트: 라이브 8전략 진입신호 백테스트 어댑터.

scripts/discovery/live_strategy_signals.py 의 두 공개 API 검증:
  - load_strategy(folder) : StrategyLoader 를 통해 전략 인스턴스 반환
  - build_signals_for(folder, data, warmup) : Dict[str, List[int]] 반환 (PIT)
"""
from __future__ import annotations

import math
from typing import Dict, List

import numpy as np
import pandas as pd
import pytest

# ──────────────────────────────────────────────────────────────────
# 합성 데이터 빌더
# ──────────────────────────────────────────────────────────────────

def _make_synthetic_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """일봉 합성 DataFrame: datetime(str), open, high, low, close, volume.

    상승추세 + 사인 잡음 → Elder/Minervini/rs_leader 등 추세추종 전략이
    충분히 긴 warmup 이후 신호를 낼 수 있는 데이터.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-04", periods=n, freq="B")
    trend = np.linspace(10000, 20000, n)
    noise = rng.normal(0, 200, n)
    sine = 500 * np.sin(np.linspace(0, 8 * math.pi, n))
    close = trend + noise + sine
    close = np.maximum(close, 1000.0)
    high = close * (1 + rng.uniform(0.001, 0.015, n))
    low = close * (1 - rng.uniform(0.001, 0.015, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(100_000, 5_000_000, n).astype(float)
    df = pd.DataFrame({
        "datetime": dates.strftime("%Y-%m-%d"),
        "open": open_.round(0),
        "high": high.round(0),
        "low": low.round(0),
        "close": close.round(0),
        "volume": volume,
    })
    return df


# ──────────────────────────────────────────────────────────────────
# 픽스처
# ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def synthetic_data() -> Dict[str, pd.DataFrame]:
    """단일 합성 종목 데이터 dict."""
    return {"000001": _make_synthetic_df(n=300)}


# ──────────────────────────────────────────────────────────────────
# 테스트 1: LIVE_STRATEGIES 상수 — 8개 폴더명 + warmup 정의 확인
# ──────────────────────────────────────────────────────────────────

def test_live_strategies_constant_has_eight_entries():
    from scripts.discovery.live_strategy_signals import LIVE_STRATEGIES
    assert len(LIVE_STRATEGIES) == 8
    expected_folders = {
        "elder_ema_pullback",
        "minervini_volume_dryup",
        "deep_mr_dev20",
        "daytrading_3methods_breakout",
        "rs_leader",
        "book_envelope_200d",
        "book_pullback_ma20",
        "book_pullback_ma5",
    }
    assert set(LIVE_STRATEGIES.keys()) == expected_folders
    for folder, warmup in LIVE_STRATEGIES.items():
        assert isinstance(warmup, int) and warmup > 0, (
            f"{folder} warmup must be positive int, got {warmup}"
        )


# ──────────────────────────────────────────────────────────────────
# 테스트 2: load_strategy — 8전략 전부 로드 가능하고 generate_signal 보유
# ──────────────────────────────────────────────────────────────────

def test_all_live_strategies_loadable():
    from scripts.discovery.live_strategy_signals import LIVE_STRATEGIES, load_strategy
    errors: List[str] = []
    for folder in LIVE_STRATEGIES:
        try:
            strat = load_strategy(folder)
            assert hasattr(strat, "generate_signal"), (
                f"{folder} has no generate_signal"
            )
        except Exception as exc:
            errors.append(f"{folder}: {exc}")
    assert not errors, "일부 전략 로드 실패:\n" + "\n".join(errors)


# ──────────────────────────────────────────────────────────────────
# 테스트 3: build_signals_for — 구조/타입 검증 (신호 수 0 허용)
# ──────────────────────────────────────────────────────────────────

def test_build_signals_runs_for_each_strategy(synthetic_data):
    from scripts.discovery.live_strategy_signals import LIVE_STRATEGIES, build_signals_for
    for folder, warmup in LIVE_STRATEGIES.items():
        result = build_signals_for(folder, synthetic_data, warmup)
        # 반환 타입: Dict[str, List[int]]
        assert isinstance(result, dict), f"{folder}: result must be dict"
        for code, bars in result.items():
            assert isinstance(code, str), f"{folder}: key must be str"
            assert isinstance(bars, list), f"{folder}: value must be list"
            for b in bars:
                assert isinstance(b, int), f"{folder}: bar index must be int, got {type(b)}"
            # 신호가 있으면 warmup 이상이어야 함 (PIT 가드)
            if bars:
                assert min(bars) >= warmup, (
                    f"{folder}: signal bar {min(bars)} < warmup {warmup}"
                )


# ──────────────────────────────────────────────────────────────────
# 테스트 4: PIT(미래참조 금지) — 신호바 인덱스가 len(df)-1 미만
# ──────────────────────────────────────────────────────────────────

def test_build_signals_no_lookahead(synthetic_data):
    """신호 인덱스는 마지막 bar(n-1)에 발생할 수 없다 — 다음봉 체결 불가."""
    from scripts.discovery.live_strategy_signals import LIVE_STRATEGIES, build_signals_for
    code = list(synthetic_data.keys())[0]
    n = len(synthetic_data[code])
    for folder, warmup in LIVE_STRATEGIES.items():
        result = build_signals_for(folder, synthetic_data, warmup)
        bars = result.get(code, [])
        assert n - 1 not in bars, (
            f"{folder}: 마지막 bar {n-1} 에 신호 — lookahead 위반"
        )
