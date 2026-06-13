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
