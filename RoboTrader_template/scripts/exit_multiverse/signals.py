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
