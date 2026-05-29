"""Lynch One Up on Wall Street — Rule 집합.

규칙들 (모두 롱 전용, 일봉 해상도, 펀더멘털 단독 진입):
- rule_fast_grower         : Lynch 최애. PEG<1.0 + 고성장(20~50%) + 저부채 + 고ROE (+옵션 RSI<50)
- rule_stalwart            : 대형우량. 안정성장(10~20%) + PEG<1.5 + 품질(net_margin>0)
- rule_value_balance_sheet : 자산주 대체. pbr<1 + 저부채 + 저per (psr 100% NULL 회피)
- rule_garp_combo          : PEGY 대체. PEG<1.2 + 성장>15% + ROE>12 + 영업마진>5 (dividend_yield NULL 회피)

재무 주입:
- run 스크립트가 거래일 i에 대응하는 point-in-time `fund` dict를 사전계산해 ctx["fund"]로 전달.
- 룰은 ctx["fund"]만 읽는다(재조회 금지). fund 또는 필수 키가 None/NaN이면 RuleResult(triggered=False).
- debt_ratio / roe / operating_margin / net_margin 은 % 단위.

헬퍼:
- _rsi : Wilder RSI(14). df["close"]로 계산. 봉 부족 시 None.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# --------------------------------------------------------------------------- #
# 지표 / 유효성 헬퍼
# --------------------------------------------------------------------------- #
def _rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """Wilder RSI(period)의 마지막 값. 봉이 period+1 미만이면 None."""
    if close is None or len(close) < period + 1:
        return None
    close = close.astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    last_gain = float(avg_gain.iloc[-1])
    last_loss = float(avg_loss.iloc[-1])
    if last_loss == 0.0:
        return 100.0
    rs = last_gain / last_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _num(fund: Dict[str, Any], key: str) -> Optional[float]:
    """fund[key]를 float로. None/NaN이면 None."""
    if fund is None:
        return None
    val = fund.get(key)
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


# --------------------------------------------------------------------------- #
# 진입 룰 4종 (롱 전용, side="buy", 펀더멘털 단독 — ctx["fund"]만 읽음)
# --------------------------------------------------------------------------- #
@dataclass
class rule_fast_grower(Rule):
    """Lynch 최애 — Fast Grower.

    PEG<1.0 AND g_ni in [20,50] AND debt_ratio<80 AND roe>10
    AND net_income>0 AND prior_net_income>0
    (옵션 타이밍: RSI(14)<50 — 계산 가능할 때만 게이트, 불가하면 펀더멘털만으로 통과)
    """
    name: str = "fast_grower"
    peg_max: float = 1.0
    g_ni_min: float = 20.0
    g_ni_max: float = 50.0
    debt_ratio_max: float = 80.0
    roe_min: float = 10.0
    rsi_max: float = 50.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        fund = ctx.get("fund")
        if fund is None:
            return RuleResult(triggered=False)

        per = _num(fund, "per")
        g_ni = _num(fund, "g_ni")
        debt_ratio = _num(fund, "debt_ratio")
        roe = _num(fund, "roe")
        net_income = _num(fund, "net_income")
        prior_net_income = _num(fund, "prior_net_income")
        if None in (per, g_ni, debt_ratio, roe, net_income, prior_net_income):
            return RuleResult(triggered=False)
        if per <= 0 or net_income <= 0 or prior_net_income <= 0 or g_ni == 0:
            return RuleResult(triggered=False)

        peg = per / g_ni
        if not (peg < self.peg_max):
            return RuleResult(triggered=False)
        if not (self.g_ni_min <= g_ni <= self.g_ni_max):
            return RuleResult(triggered=False)
        if not (debt_ratio < self.debt_ratio_max):
            return RuleResult(triggered=False)
        if not (roe > self.roe_min):
            return RuleResult(triggered=False)

        # 옵션 RSI 타이밍: 계산 가능할 때만 게이트, 불가하면 통과
        rsi = _rsi(df["close"]) if df is not None and "close" in df else None
        if rsi is not None and not (rsi < self.rsi_max):
            return RuleResult(triggered=False)

        rsi_str = f"{rsi:.1f}" if rsi is not None else "n/a"
        return RuleResult(
            triggered=True, side="buy", confidence=78.0,
            reasons=[
                f"fast_grower PEG={peg:.2f} g_ni={g_ni:.1f}% per={per:.1f} "
                f"debt={debt_ratio:.0f}% roe={roe:.1f}% rsi={rsi_str}"
            ],
            metadata={"peg": peg, "g_ni": g_ni, "per": per, "roe": roe},
        )


@dataclass
class rule_stalwart(Rule):
    """대형우량 — Stalwart.

    g_ni in [10,20] AND PEG<1.5 AND roe>10 AND debt_ratio<100 AND net_margin>0
    (dividend_yield>0 원의도였으나 100% NULL → net_margin>0 품질 프록시 대체)
    """
    name: str = "stalwart"
    g_ni_min: float = 10.0
    g_ni_max: float = 20.0
    peg_max: float = 1.5
    roe_min: float = 10.0
    debt_ratio_max: float = 100.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        fund = ctx.get("fund")
        if fund is None:
            return RuleResult(triggered=False)

        per = _num(fund, "per")
        g_ni = _num(fund, "g_ni")
        roe = _num(fund, "roe")
        debt_ratio = _num(fund, "debt_ratio")
        net_margin = _num(fund, "net_margin")
        if None in (per, g_ni, roe, debt_ratio, net_margin):
            return RuleResult(triggered=False)
        if per <= 0 or g_ni == 0:
            return RuleResult(triggered=False)

        peg = per / g_ni
        if not (self.g_ni_min <= g_ni <= self.g_ni_max):
            return RuleResult(triggered=False)
        if not (peg < self.peg_max):
            return RuleResult(triggered=False)
        if not (roe > self.roe_min):
            return RuleResult(triggered=False)
        if not (debt_ratio < self.debt_ratio_max):
            return RuleResult(triggered=False)
        if not (net_margin > 0):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[
                f"stalwart PEG={peg:.2f} g_ni={g_ni:.1f}% per={per:.1f} "
                f"roe={roe:.1f}% debt={debt_ratio:.0f}% nmargin={net_margin:.1f}%"
            ],
            metadata={"peg": peg, "g_ni": g_ni, "per": per, "roe": roe},
        )


@dataclass
class rule_value_balance_sheet(Rule):
    """자산주 대체 — Value / Balance Sheet (psr 100% NULL 회피).

    pbr<1.0 AND debt_ratio<50 AND 0<per<12 AND net_income>0
    (psr<1 불가 → pbr<1 + 저per + 저부채로 자산주 발상 표현. g_ni 불필요.)
    """
    name: str = "value_balance_sheet"
    pbr_max: float = 1.0
    debt_ratio_max: float = 50.0
    per_max: float = 12.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        fund = ctx.get("fund")
        if fund is None:
            return RuleResult(triggered=False)

        pbr = _num(fund, "pbr")
        per = _num(fund, "per")
        debt_ratio = _num(fund, "debt_ratio")
        net_income = _num(fund, "net_income")
        if None in (pbr, per, debt_ratio, net_income):
            return RuleResult(triggered=False)

        if not (pbr < self.pbr_max):
            return RuleResult(triggered=False)
        if not (debt_ratio < self.debt_ratio_max):
            return RuleResult(triggered=False)
        if not (0 < per < self.per_max):
            return RuleResult(triggered=False)
        if not (net_income > 0):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=65.0,
            reasons=[
                f"value_balance_sheet pbr={pbr:.2f} per={per:.1f} "
                f"debt={debt_ratio:.0f}% ni={net_income:.0f}"
            ],
            metadata={"pbr": pbr, "per": per, "debt_ratio": debt_ratio},
        )


@dataclass
class rule_garp_combo(Rule):
    """PEGY 대체 — GARP combo (dividend_yield 100% NULL 회피).

    PEG<1.2 AND g_ni>15 AND roe>12 AND debt_ratio<120 AND operating_margin>5
    """
    name: str = "garp_combo"
    peg_max: float = 1.2
    g_ni_min: float = 15.0
    roe_min: float = 12.0
    debt_ratio_max: float = 120.0
    operating_margin_min: float = 5.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        fund = ctx.get("fund")
        if fund is None:
            return RuleResult(triggered=False)

        per = _num(fund, "per")
        g_ni = _num(fund, "g_ni")
        roe = _num(fund, "roe")
        debt_ratio = _num(fund, "debt_ratio")
        operating_margin = _num(fund, "operating_margin")
        if None in (per, g_ni, roe, debt_ratio, operating_margin):
            return RuleResult(triggered=False)
        if per <= 0 or g_ni == 0:
            return RuleResult(triggered=False)

        peg = per / g_ni
        if not (peg < self.peg_max):
            return RuleResult(triggered=False)
        if not (g_ni > self.g_ni_min):
            return RuleResult(triggered=False)
        if not (roe > self.roe_min):
            return RuleResult(triggered=False)
        if not (debt_ratio < self.debt_ratio_max):
            return RuleResult(triggered=False)
        if not (operating_margin > self.operating_margin_min):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=72.0,
            reasons=[
                f"garp_combo PEG={peg:.2f} g_ni={g_ni:.1f}% per={per:.1f} "
                f"roe={roe:.1f}% debt={debt_ratio:.0f}% omargin={operating_margin:.1f}%"
            ],
            metadata={"peg": peg, "g_ni": g_ni, "roe": roe, "operating_margin": operating_margin},
        )


ALL_RULES = [
    rule_fast_grower,
    rule_stalwart,
    rule_value_balance_sheet,
    rule_garp_combo,
]
