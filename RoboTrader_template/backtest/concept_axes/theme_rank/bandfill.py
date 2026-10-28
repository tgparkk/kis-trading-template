"""라이브 +3% 밴드 체결의 일봉 재현(스펙 §5-1) + 밴드 터치 로트의 청산 재시뮬.

시가 ≤ 상한 → 시가 체결(원장 결과 그대로) · 시가 > 상한 ∧ 저가 ≤ 상한 → 상한가 체결(재시뮬) · 그 밖 미체결.
daytrading 은 하한이 없다(`entry_band_down_pct` None) — 하한은 보지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

FILL_OPEN, FILL_BAND, FILL_NONE, FILL_NO_BAR = "open", "band_touch", "none", "no_bar"


@dataclass(frozen=True)
class Fill:
    status: str
    price: Optional[float]


def band_fill(open_: Optional[float], low: Optional[float], hi: Optional[float]) -> Fill:
    if open_ is None or not open_ > 0:
        return Fill(FILL_NO_BAR, None)
    if hi is None or open_ <= hi:
        return Fill(FILL_OPEN, float(open_))
    if low is not None and low <= hi:
        return Fill(FILL_BAND, float(hi))
    return Fill(FILL_NONE, None)


def resim_band_touch(code: str, d1: date, price: float, env: Any, rules: Any, probe: Any) -> Any:
    """상한가에 산 것으로 보고 원장과 같은 청산기(`exitsim8.simulate_lot`)로 다시 돈다.

    체결 시각을 모르므로 진입일 터치 청산은 보지 않는다(ledger8 A3 상한 민감도 규칙 · `BASIS_UPPER` · touch_bar=None).
    """
    from backtest.concept_axes.candidate_ledger import run as CL
    from backtest.concept_axes.ledger8 import exitsim8 as X
    from backtest.concept_axes.ledger8 import sizing as Z
    from backtest.concept_axes.ledger8 import sources8 as SRC8
    q = Z.arm_b_qty(price)
    pos = X.Pos(code, d1, SRC8.aware(datetime.combine(d1, CL.ENTRY_TIME)), float(price), q.qty, X.BASIS_UPPER)
    path = CL.build_path(env.cal, env.cal_idx, env.bars(code), d1, rules.max_hold_days)
    return X.simulate_lot(pos, rules, path, probe)


def filled(arena: pd.DataFrame) -> pd.DataFrame:
    """판정에 쓰는 행 = 체결(시가·밴드 터치) ∧ 순수익 있음."""
    a = arena[arena["fill"].isin([FILL_OPEN, FILL_BAND])].copy()
    a["ret_net"] = pd.to_numeric(a["ret_net"], errors="coerce")
    return a[a["ret_net"].notna()].reset_index(drop=True)
