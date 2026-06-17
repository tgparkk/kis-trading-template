"""진입봉 PIT 기준값 산출 — box(고저 레인지) / atr / bollinger 밴드폭.

모든 계산은 df.iloc[:i+1] (bar i 이하)만 사용 = no-lookahead.

ATR 정렬 노트:
  윈도우 = df.iloc[i-n+1 : i+1]  (크기 n, 인덱스 i-n+1 ~ i)
  윈도우의 k번째 봉(k=0..n-1)의 직전 종가 = df["close"].iloc[i-n+k]
    - k=0: df["close"].iloc[i-n]  → 윈도우 시작 직전봉 (항상 i-n ≤ i, PIT 준수)
    - k>0: 윈도우 내 직전봉 (PIT 준수)
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
        # 직전 종가 정렬: 윈도우 k번째 봉의 prev_close = df["close"].iloc[i-n+k]
        # k=0 → df["close"].iloc[i-n] (윈도우 시작 직전, PIT 준수)
        h = high.values
        l = low.values
        prev_closes = df["close"].astype(float).iloc[i - n : i].values  # 길이 n
        tr = [
            max(h[k] - l[k], abs(h[k] - prev_closes[k]), abs(l[k] - prev_closes[k]))
            for k in range(n)
        ]
        atr = float(sum(tr) / n)
        return {"atr": atr} if atr > 0 else None

    if ref_type == "bollinger":
        std = float(close.std(ddof=0))
        width = 2.0 * bb_k * std
        return {"bb_width": width} if width > 0 else None

    raise ValueError(f"unknown ref_type: {ref_type}")
