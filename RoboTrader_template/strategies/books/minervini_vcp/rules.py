"""Minervini VCP — Rule 집합.

규칙들:
- rule_trend_template: SEPA Trend Template 8조건
- rule_vcp_breakout: VCP 베이스 + 피벗 돌파
- rule_tight_closes: 3주 변동폭 ≤ 1.5%
- rule_volume_dryup: 거래량 dry-up + tightness

헬퍼:
- compute_rs_percentile_12w: universe 12주 수익률 백분위
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


def compute_rs_percentile_12w(universe_close: pd.DataFrame) -> pd.DataFrame:
    """universe 종목 12주(60거래일) 수익률을 0~99 백분위로 변환.

    Args:
        universe_close: index=date, columns=stock_code, values=close.
    Returns:
        같은 shape의 DataFrame. 각 행은 해당 날짜의 RS 백분위 (0~99).
    """
    ret_12w = universe_close.pct_change(60)
    rank = ret_12w.rank(axis=1, pct=True, na_option="keep")
    return (rank * 99).round().astype("Int64")
