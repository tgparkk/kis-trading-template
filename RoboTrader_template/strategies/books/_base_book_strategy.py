"""책 백테스트 공통 베이스.

각 책의 매매 규칙(Rule)을 리스트로 받아 단일/AND/OR 조합으로 Signal을 생성한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

import pandas as pd

from strategies.base import BaseStrategy, Signal, SignalType

VALID_MODES = ("single", "all_AND", "top_K_OR")


@dataclass
class RuleResult:
    """규칙 평가 결과."""
    triggered: bool
    side: Literal["buy", "sell"] = "buy"
    confidence: float = 70.0
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Rule(ABC):
    """개별 매매 규칙. 책마다 N개를 정의한다."""

    name: str = "unnamed"

    @abstractmethod
    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        """t 시점 데이터(df 마지막 행 기준)로 신호 평가. t+1 이후 접근 금지."""
        raise NotImplementedError


class BookStrategy(BaseStrategy):
    """책 전략 공통 베이스. 모든 책 strategy는 이걸 상속해서 rules 리스트만 주입한다."""

    name = "BookStrategy"
    version = "1.0.0"
    holding_period = "intraday"  # 책별로 override

    def __init__(
        self,
        rules: List[Rule],
        mode: str = "single",
        target_rule: Optional[str] = None,
        or_members: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(config or {})
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
        if mode == "single" and target_rule is None:
            raise ValueError("mode='single' requires target_rule name")
        if mode == "top_K_OR" and not or_members:
            raise ValueError("mode='top_K_OR' requires or_members list")

        self.rules = rules
        self.mode = mode
        self.target_rule = target_rule
        self.or_members = or_members or []
        self._rule_map = {r.name: r for r in rules}
        if len(self._rule_map) != len(rules):
            seen: list = []
            dups: list = []
            for r in rules:
                if r.name in seen:
                    dups.append(r.name)
                else:
                    seen.append(r.name)
            raise ValueError(f"Duplicate rule names detected: {sorted(set(dups))}")

    def generate_signal(
        self, stock_code: str, data: pd.DataFrame, timeframe: str = "daily"
    ) -> Optional[Signal]:
        if data is None or len(data) == 0:
            return None
        ctx = {"stock_code": stock_code, "timeframe": timeframe}

        if self.mode == "single":
            rule = self._rule_map.get(self.target_rule)
            if rule is None:
                return None
            res = rule.evaluate(data, ctx)
            return self._to_signal(stock_code, res, res.reasons if res.triggered else [])

        if self.mode == "all_AND":
            if not self.rules:
                return None
            results = [(r.name, r.evaluate(data, ctx)) for r in self.rules]
            if all(res.triggered for _, res in results):
                merged_reasons = [r for _, res in results for r in res.reasons]
                return self._to_signal(stock_code, results[0][1], merged_reasons)
            return None

        if self.mode == "top_K_OR":
            for name in self.or_members:
                rule = self._rule_map.get(name)
                if rule is None:
                    continue
                res = rule.evaluate(data, ctx)
                if res.triggered:
                    return self._to_signal(stock_code, res, [name])
            return None

        return None

    def generate_signal_with_extra_ctx(
        self, stock_code: str, data: pd.DataFrame, timeframe: str, extra: Dict[str, Any]
    ) -> Optional[Signal]:
        """generate_signal과 같지만 ctx에 extra dict를 머지해서 rule에 전달."""
        if data is None or len(data) == 0:
            return None
        ctx = {"stock_code": stock_code, "timeframe": timeframe, **extra}

        if self.mode == "single":
            rule = self._rule_map.get(self.target_rule)
            if rule is None:
                return None
            res = rule.evaluate(data, ctx)
            return self._to_signal(stock_code, res, res.reasons if res.triggered else [])

        if self.mode == "all_AND":
            if not self.rules:
                return None
            results = [(r.name, r.evaluate(data, ctx)) for r in self.rules]
            if all(res.triggered for _, res in results):
                merged_reasons = [r for _, res in results for r in res.reasons]
                return self._to_signal(stock_code, results[0][1], merged_reasons)
            return None

        if self.mode == "top_K_OR":
            for name in self.or_members:
                rule = self._rule_map.get(name)
                if rule is None:
                    continue
                res = rule.evaluate(data, ctx)
                if res.triggered:
                    return self._to_signal(stock_code, res, [name])
            return None
        return None

    @staticmethod
    def _to_signal(stock_code: str, res: RuleResult, reasons: List[str]) -> Optional[Signal]:
        if not res.triggered:
            return None
        if res.side not in ("buy", "sell"):
            raise ValueError(f"RuleResult.side must be 'buy' or 'sell', got {res.side!r}")
        sig_type = SignalType.BUY if res.side == "buy" else SignalType.SELL
        return Signal(
            signal_type=sig_type,
            stock_code=stock_code,
            confidence=res.confidence,
            reasons=reasons,
            metadata=res.metadata,
        )
