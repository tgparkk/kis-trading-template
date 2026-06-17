"""진입봉 PIT 기준값 산출 — box(고저 레인지) / atr / bollinger 밴드폭.

모든 계산은 df.iloc[:i+1] (bar i 이하)만 사용 = no-lookahead.

ATR 정렬 노트:
  윈도우 = df.iloc[i-n+1 : i+1]  (크기 n, 인덱스 i-n+1 ~ i)
  직전 종가는 윈도우 내 shift(1)로 계산 — 음수 인덱스 슬라이스 없음, PIT 준수.
    - 윈도우 첫 봉(k=0)은 shift(1) NaN → 자기 close로 대체 (TR = H - L).
    - 윈도우 나머지 봉(k>0)은 윈도우 내 직전 봉 종가 = PIT 준수.
  즉 True Range 계산에 사용하는 모든 가격은 bar i 이하이므로 룩어헤드 없음.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def compute_reference(
    df: pd.DataFrame,
    i: int,
    ref_type: str,
    n: int,
    bb_k: float = 2.0,
) -> Optional[dict]:
    """bar i 기준 PIT 기준값 산출.

    Args:
        df:       OHLCV DataFrame (열: high, low, close 필수).
        i:        기준봉 인덱스 (0-based).
        ref_type: "box" | "atr" | "bollinger".
        n:        룩백 기간 (윈도우 크기).
        bb_k:     볼린저 밴드 승수 (기본 2.0).

    Returns:
        ref_type별 컴포넌트 dict, 또는 워밍업 부족/퇴화 시 None.
    """
    # 워밍업 부족: 윈도우 크기 n 봉이 i+1 내에 없으면 None
    if i + 1 < n:
        return None

    win = df.iloc[i - n + 1 : i + 1]
    high = win["high"].astype(float)
    low = win["low"].astype(float)
    close = win["close"].astype(float)

    if ref_type == "box":
        box_high = float(high.max())
        box_low = float(low.min())
        return {"box_low": box_low, "box_height": box_high - box_low}

    if ref_type == "atr":
        # True Range with prior close = previous bar's close within the PIT window.
        # win = df.iloc[i-n+1 : i+1]; prev close is win["close"].shift(1).
        # First bar's prev-close falls back to its own close (TR = H-L there).
        # No negative-index slice; all rows are within [i-n+1, i] — no lookahead.
        prev_close = close.shift(1).fillna(close)
        tr = (pd.concat([
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1))
        atr = float(tr.mean())
        return {"atr": atr} if atr > 0 else None

    if ref_type == "bollinger":
        std = float(close.std(ddof=0))
        width = 2.0 * bb_k * std
        return {"bb_width": width} if width > 0 else None

    raise ValueError(f"unknown ref_type: {ref_type}")
