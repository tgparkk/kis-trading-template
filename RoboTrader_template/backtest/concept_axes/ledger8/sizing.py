"""두 사이징 arm — 순수 함수(DB·로그·전략 인스턴스 없음).

🔴 arm B 는 「자본 분모가 없는 세계」다. 총자산·누적수익률·자본 대비 %를 계산하지 말 것.
   이 모듈은 «수량»과 «명목금액»만 돌려준다.

arm A — 라이브 `VirtualTradingManager.get_max_quantity`(core/virtual_trading_manager.py:591-620) 재현
────────────────────────────────────────────────────────────────────────────────────────────
    per_stock  = 그날 07:40 복리 재산정 값 = 기준값 × (현금 + 원가) / 초기자본
                 (recalculate_investment_amounts :300-361 · 로그 `종목당 투자금액 재산정: <전략> A원 → B원`)
                 기준값 = 자본/K(allocate_strategy_capital :250-254) · yaml `paper_investment_per_stock` 이
                 있으면 그 값(deep_mr_dev20 · bot/initializer.py:489-494 · set_strategy_investment_amount :261-276)
    max_amount = min(per_stock, 잔고)            (:608)
    cap        = yaml `max_per_stock_amount` 가 max_amount 보다 작으면 그 값 (:611-617)
    qty        = int(max_amount / price)         (:618) ⇒ price > max_amount 면 0주 → 「수량부족」
                 (core/trading_decision_engine.py:429-430)
    🔑 잔고는 재현하지 않는다(전략 잔고 시간선 = paper_strategy_equity 리플레이 영역) ⇒ arm A 수량은 «상한»이다.
       실측: 09-18 ma20 per_stock 864,374 · 09-17 minervini 3,337,630(상한 3,000,000 에 걸림) — 검증표 #12.

arm B — 사장님 규칙(스펙 §0 · 2026-09-18 확정)
─────────────────────────────────────────────
    qty = max(1, floor(1_000_000 / price))   — 자본 한도·K·일일 체결 한도·종목당 상한 전부 없음.
    예: 204,000원 → 4주(816,000원) · 1,078,000원 → 1주(1,078,000원). 고가주는 명목이 100만원을 넘는다(규칙의 성질).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Optional

ARM_B_PER_STOCK = 1_000_000   # 🔒 사장님 규칙의 기준 금액 — 결과를 보고 바꾸지 말 것

BASIS_AMOUNT = "amount"        # floor(1,000,000/주가) ≥ 1
BASIS_ONE_SHARE = "one_share"  # 주가 > 1,000,000 → 1주 강제
BASIS_NONE = "n/a"


@dataclass(frozen=True)
class Qty:
    qty: int
    basis: str
    notional: float                 # qty × price (원)
    per_stock: Optional[float] = None
    note: str = ""

    @property
    def blocked(self) -> bool:
        return self.qty <= 0


def arm_a_qty(price: Optional[float], per_stock: Optional[float], cap: Optional[float] = None,
              per_stock_src: str = "") -> Qty:
    """라이브 수량 상한(잔고 항 제외). `price > min(per_stock, cap)` 이면 0주."""
    if price is None or price <= 0 or per_stock is None or per_stock <= 0:
        return Qty(0, BASIS_NONE, 0.0, per_stock, "가격/per_stock 없음")
    max_amount = float(per_stock)
    notes = [f"per_stock {max_amount:,.0f}원" + (f"({per_stock_src})" if per_stock_src else "")]
    if cap is not None and 0 < float(cap) < max_amount:
        max_amount = float(cap)
        notes.append(f"종목당 상한 {max_amount:,.0f}원 적용")
    qty = int(max_amount / float(price))
    if qty <= 0:
        notes.append(f"주가 {float(price):,.0f} > 한도 {max_amount:,.0f} ⇒ 0주(수량부족 거절)")
        return Qty(0, BASIS_NONE, 0.0, float(per_stock), " · ".join(notes))
    return Qty(qty, BASIS_AMOUNT, qty * float(price), float(per_stock), " · ".join(notes))


def arm_b_qty(price: Optional[float], per_stock: int = ARM_B_PER_STOCK) -> Qty:
    """사장님 규칙 — `qty = max(1, floor(per_stock / price))`. 자원 제약 없음."""
    if price is None or price <= 0:
        return Qty(0, BASIS_NONE, 0.0, float(per_stock), "가격 없음")
    raw = floor(float(per_stock) / float(price))
    if raw >= 1:
        return Qty(int(raw), BASIS_AMOUNT, int(raw) * float(price), float(per_stock))
    return Qty(1, BASIS_ONE_SHARE, float(price), float(per_stock),
               f"주가 {float(price):,.0f} > {per_stock:,.0f} ⇒ 1주(명목 = 기준의 {float(price) / per_stock:.2f}배)")
