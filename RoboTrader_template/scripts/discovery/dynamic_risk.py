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
    sl_pct = max(SL_FLOOR, min(SL_CAP, sl_pct))   # SL 클램프
    tp_pct = max(tp_pct, sl_pct)                  # TP 하한 = SL (RR>=1)
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
