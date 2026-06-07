# 횡보장 RS 리더 — 7번째 페이퍼 전략 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 검증에서 횡보장 강건으로 확인된 RS 리더를 기존 전략별 EOD 스크리너 패턴으로 7번째 **페이퍼 관찰** 전략에 등록한다(라이브 실계좌 아님).

**Architecture:** EOD 스크리너(`RuleScreenerBase`)가 절대상승추세 통과 종목을 120일수익률 score로 매기고 scan 정렬+topK로 횡단면 RS 랭킹 → screener_snapshots. 라이브는 `RSLeaderStrategy.generate_signal`이 선정 풀에서 per-stock 절대추세 재확인 후 매수. 청산은 MA20 트레일(검증 4-bis와 동일, 무조건 이탈)+sl+max_hold. 진입 추세로직은 기머지된 `scripts/rs_leader/rule.RSLeaderRule` 단일 소스 재사용(DRY).

**Tech Stack:** Python 3.8+, pandas, pytest. 스펙: `docs/superpowers/specs/2026-06-06-rs-leader-paper-strategy-design.md`. 패턴 참조: `strategies/book_pullback_ma20/{screener,strategy}.py`.

---

## 재사용/참조 (수정 금지)
- `scripts/rs_leader/rule.py::RSLeaderRule(ma_short=20, ma_long=60, abs_lb=60).generate_signal(code, df, "daily")` → 절대상승추세면 `Signal(BUY)`, 아니면 None. (pandas + strategies.base 만 의존 → 라이브 import 안전)
- `strategies/_rule_screener_base.py::RuleScreenerBase` (scan/base_filter/match 인터페이스, `_load_universe`/`_load_daily`는 QuantDailyReader 사용. df 컬럼: date,open,high,low,close,volume).
- `strategies/base.py::BaseStrategy, Signal, SignalType, OrderInfo`.
- 패턴 원본: `strategies/book_pullback_ma20/strategy.py` (evaluate_entry/evaluate_sell_conditions/on_tick 라이프사이클).
- 등록 지점: `runners/_adapter_factory.py::build_adapter`, `config/trading_config.json` `strategies[]`.

## 파일 구조
- Create: `strategies/rs_leader/__init__.py`
- Create: `strategies/rs_leader/screener.py` — `RSLeaderScreenerAdapter`
- Create: `strategies/rs_leader/strategy.py` — `RSLeaderStrategy`
- Create: `strategies/rs_leader/config.yaml`
- Modify: `runners/_adapter_factory.py` (elif rs_leader)
- Modify: `config/trading_config.json` (7번째 strategies[] 항목)
- Create: `tests/strategies/rs_leader/__init__.py`, `tests/strategies/rs_leader/test_screener.py`, `tests/strategies/rs_leader/test_strategy.py`, `tests/strategies/rs_leader/test_registration.py`

---

## Task 1: 스크리너 어댑터 `RSLeaderScreenerAdapter`

**Files:**
- Create: `strategies/rs_leader/__init__.py`
- Create: `strategies/rs_leader/screener.py`
- Create: `tests/strategies/rs_leader/__init__.py`
- Test: `tests/strategies/rs_leader/test_screener.py`

- [ ] **Step 1: 브랜치 생성**

Run:
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && git checkout -b feat/rs-leader-paper-strategy
```
Expected: `Switched to a new branch 'feat/rs-leader-paper-strategy'`

- [ ] **Step 2: 실패 테스트 작성**

`strategies/rs_leader/__init__.py`:
```python
```
`tests/strategies/rs_leader/__init__.py`:
```python
```
`tests/strategies/rs_leader/test_screener.py`:
```python
import numpy as np
import pandas as pd

from strategies.rs_leader.screener import RSLeaderScreenerAdapter


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_match_uptrend_returns_score_and_reason():
    closes = list(np.linspace(100, 200, 130))  # 단조상승: 추세통과
    adapter = RSLeaderScreenerAdapter()
    res = adapter.match(_df(closes), adapter.default_params())
    assert res is not None
    score, reason = res
    # score = 120일 수익률 = close[-1]/close[-121]-1 > 0
    assert score > 0 and isinstance(reason, str) and reason


def test_match_downtrend_returns_none():
    closes = list(np.linspace(200, 100, 130))
    adapter = RSLeaderScreenerAdapter()
    assert adapter.match(_df(closes), adapter.default_params()) is None


def test_match_too_short_returns_none():
    closes = list(np.linspace(100, 110, 40))
    adapter = RSLeaderScreenerAdapter()
    assert adapter.match(_df(closes), adapter.default_params()) is None


def test_base_filter_liquidity():
    adapter = RSLeaderScreenerAdapter()
    uni = [
        {"code": "A", "market_cap": 5e11, "trading_value": 2e9},   # 통과
        {"code": "B", "market_cap": 5e11, "trading_value": 5e8},   # 거래대금 미달
    ]
    out = adapter.base_filter(uni)
    assert [u["code"] for u in out] == ["A"]
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/strategies/rs_leader/test_screener.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategies.rs_leader.screener'`

- [ ] **Step 4: 구현 작성**

`strategies/rs_leader/screener.py`:
```python
"""횡보장 RS 리더 전략 EOD 스크리너 어댑터.

match 가 절대상승추세 통과 종목의 120일 수익률을 score 로 반환 → RuleScreenerBase.scan
의 정렬+topK 가 곧 횡단면 RS 랭킹(별도 패널 불요). 진입 추세 판정은 검증에서 쓴
scripts.rs_leader.rule.RSLeaderRule 단일 소스를 재사용(DRY).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from scripts.rs_leader.rule import RSLeaderRule


class RSLeaderScreenerAdapter(RuleScreenerBase):
    strategy_name = "rs_leader"
    lookback_days = 130  # MA60 + 120일 수익률 워밍업

    def default_params(self) -> Dict[str, Any]:
        return {
            "ma_short": 20, "ma_long": 60, "abs_lb": 60, "rs_lb": 120,
            "min_trading_value": 1_000_000_000,
            "min_price": 1_000, "max_price": 500_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        out = []
        for u in universe:
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        rs_lb = int(params.get("rs_lb", 120))
        rule = RSLeaderRule(
            ma_short=int(params.get("ma_short", 20)),
            ma_long=int(params.get("ma_long", 60)),
            abs_lb=int(params.get("abs_lb", 60)),
        )
        # 가격대 가드(절대상승추세는 RSLeaderRule이 판정)
        close = df["close"].astype(float)
        last = float(close.iloc[-1])
        if last < params.get("min_price", 1_000) or last > params.get("max_price", 500_000):
            return None
        sig = rule.generate_signal("_", df, "daily")
        if sig is None:
            return None
        if len(close) <= rs_lb:
            return None
        rs_ret = last / float(close.iloc[-1 - rs_lb]) - 1.0
        reason = f"RS리더: 절대상승추세 + {rs_lb}일수익률 {rs_ret * 100:+.1f}%"
        return (float(rs_ret), reason)  # score=RS수익률 → scan 정렬+topK = RS랭킹
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/strategies/rs_leader/test_screener.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add strategies/rs_leader/__init__.py strategies/rs_leader/screener.py tests/strategies/rs_leader/
git commit -m "feat(rs_leader): EOD screener adapter (abs-trend + cross-sectional RS via topK)"
```

---

## Task 2: 전략 `RSLeaderStrategy` + config.yaml

**Files:**
- Create: `strategies/rs_leader/strategy.py`
- Create: `strategies/rs_leader/config.yaml`
- Test: `tests/strategies/rs_leader/test_strategy.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/strategies/rs_leader/test_strategy.py`:
```python
import numpy as np
import pandas as pd

from strategies.rs_leader.strategy import RSLeaderStrategy


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_evaluate_entry_uptrend_true():
    closes = list(np.linspace(100, 200, 130))
    ok, reasons = RSLeaderStrategy.evaluate_entry(_df(closes), min_daily_bars=130)
    assert ok is True and reasons


def test_evaluate_entry_downtrend_false():
    closes = list(np.linspace(200, 100, 130))
    ok, reasons = RSLeaderStrategy.evaluate_entry(_df(closes), min_daily_bars=130)
    assert ok is False


def test_sell_stop_loss():
    closes = [100] * 25 + [90]
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=100.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should and code == "stop_loss"


def test_sell_ma20_break_unconditional():
    # 상승 후 MA20 아래로 마감 → ma_break (수익여부 무관, 검증 4-bis 정합)
    closes = list(range(100, 130)) + [110]
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=110.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should and code == "ma_break"


def test_sell_hold_when_above_ma():
    closes = list(range(100, 140))
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=130.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/strategies/rs_leader/test_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategies.rs_leader.strategy'`

- [ ] **Step 3: config.yaml 작성**

`strategies/rs_leader/config.yaml`:
```yaml
# =============================================================================
# RS Leader Strategy — 횡보장 RS 리더 (페이퍼 관찰 전용)
# 검증: docs/superpowers/specs/2026-06-06-rs-leader-bad-market-design.md (PARTIAL)
#   횡보장 절대수익 강건, 깊은약세 미입증·저Sharpe → 격리 페이퍼 관찰.
# 진입: 절대상승추세(종가>MA60·MA20>MA60·60일수익>0) + 스크리너 횡단면 RS 상위.
# 청산: MA20 하향이탈(무조건) / sl -8% / max_hold 30거래일.
# =============================================================================
strategy:
  name: "RSLeaderStrategy"
  version: "1.0.0"
paper_trading: true
parameters:
  ma_short: 20
  ma_long: 60
  abs_lb: 60
  rs_lb: 120
  min_daily_bars: 130
  max_holding_days: 30
risk_management:
  take_profit_pct: 0.15       # 추세추종 — 고정익절 거의 무효(트레일이 주 청산)
  stop_loss_pct: 0.08
  trail_ma: 20                # 종가 < MA20 하향이탈 시 청산 (무조건)
  max_hold_days: 30
  max_positions: 10
  max_daily_trades: 5
  max_per_stock_amount: 3000000
target_stocks: []
```

- [ ] **Step 4: strategy.py 작성**

`strategies/rs_leader/strategy.py`:
```python
"""RS Leader Strategy — 횡보장 RS 리더 (페이퍼 관찰 전용).

진입: 절대상승추세(scripts.rs_leader.rule.RSLeaderRule 단일 소스 재사용) — 횡단면 RS
랭킹은 EOD 스크리너가 담당하고, 이 전략은 선정 풀에서 per-stock 추세 재확인 후 매수.
청산: MA20 하향이탈(무조건, 검증 4-bis 정합) / sl -8% / max_hold 30거래일.
holding_period="swing" → EOD 일괄청산 건너뜀. paper_trading=True.
"""
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between
from ..base import BaseStrategy, OrderInfo, Signal, SignalType
from scripts.rs_leader.rule import RSLeaderRule


class RSLeaderStrategy(BaseStrategy):
    name: str = "RSLeaderStrategy"
    version: str = "1.0.0"
    description: str = "횡보장 RS 리더 — 절대상승추세+횡단면RS (sl8/trail_ma20/max30, paper)"
    author: str = "Template"
    holding_period: str = "swing"
    accepts_volume_fallback: bool = True

    def get_min_data_length(self) -> int:
        params = self.config.get("parameters", {})
        return int(params.get("min_daily_bars", 130))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._min_daily_bars = int(params.get("min_daily_bars", 130))
        self._ma_short = int(params.get("ma_short", 20))
        self._ma_long = int(params.get("ma_long", 60))
        self._abs_lb = int(params.get("abs_lb", 60))

        risk = self.config.get("risk_management", {})
        self._take_profit_pct = float(risk.get("take_profit_pct", 0.15))
        self._stop_loss_pct = float(risk.get("stop_loss_pct", 0.08))
        self._max_hold_days = int(risk.get("max_hold_days", 30))
        self._trail_ma = risk.get("trail_ma", 20)
        self._trail_ma = int(self._trail_ma) if self._trail_ma is not None else None
        self._max_positions = int(risk.get("max_positions", 10))
        self._max_daily_trades = int(risk.get("max_daily_trades", 5))
        self._max_per_stock_amount = float(risk.get("max_per_stock_amount", 3_000_000))

        self.max_holding_days = int(
            params.get("max_holding_days", risk.get("max_hold_days", 30))
        )
        self._paper_trading = self.config.get("paper_trading", True)

        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0
        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(RS리더, sl={self._stop_loss_pct:.0%}/trail_ma={self._trail_ma}/"
            f"max_hold={self._max_hold_days}거래일)"
        )
        if self._paper_trading:
            self.logger.info("⚠️ Paper Trading 모드 활성화")
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0
        if self.positions:
            self.logger.info(f"장 시작 — 보유 {len(self.positions)}개: {list(self.positions.keys())}")
        else:
            self.logger.info("장 시작 — 보유 종목 없음")

    def generate_signal(self, stock_code: str, data: pd.DataFrame,
                        timeframe: str = "daily") -> Optional[Signal]:
        if data is None or len(data) < self.get_min_data_length():
            return None
        if stock_code in self.positions:
            return self._check_sell(stock_code, data)
        if self.daily_trades >= self._max_daily_trades:
            return None
        if len(self.positions) >= self._max_positions:
            return None
        if timeframe != "daily":
            return None
        return self._check_buy(stock_code, data)

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {
                "quantity": order.quantity, "entry_price": order.price,
                "entry_time": order.filled_at,
            }
            self.logger.info(f"📥 매수 체결: {order.stock_code} @ {order.price:,.0f} x {order.quantity}주")
        elif order.stock_code in self.positions:
            pos = self.positions.pop(order.stock_code)
            pnl_pct = (order.price - pos["entry_price"]) / pos["entry_price"] * 100
            prefix = "[PAPER] " if self._paper_trading else ""
            self.logger.info(f"📤 {prefix}매도 체결: {order.stock_code} @ {order.price:,.0f} ({pnl_pct:+.1f}%)")

    def on_market_close(self) -> None:
        self.logger.info(f"장 마감 — 거래 {self.daily_trades}건, 보유 {len(self.positions)}종목")

    # --- 순수 판단 함수 ---
    @staticmethod
    def evaluate_entry(df: pd.DataFrame, min_daily_bars: int = 130,
                       ma_short: int = 20, ma_long: int = 60, abs_lb: int = 60
                       ) -> Tuple[bool, List[str]]:
        """절대상승추세 진입 — RSLeaderRule 단일 소스 재사용."""
        if df is None or len(df) < min_daily_bars:
            return False, []
        rule = RSLeaderRule(ma_short=ma_short, ma_long=ma_long, abs_lb=abs_lb)
        sig = rule.generate_signal("_", df, "daily")
        if sig is None:
            return False, []
        return True, ["절대상승추세(종가>MA60·MA20>MA60·60일수익>0)"]

    @staticmethod
    def evaluate_sell_conditions(df: pd.DataFrame, entry_price: float, hold_days: int,
                                 stop_loss_pct: float = 0.08, take_profit_pct: float = 0.15,
                                 max_hold_days: int = 30, trail_ma: Optional[int] = 20
                                 ) -> Tuple[bool, List[str], str]:
        """청산 우선순위(검증 4-bis MA20TrailExitAdapter 정합):
        stop_loss → take_profit → ma_break(무조건) → max_hold."""
        close = df["close"].astype(float)
        cur_close = float(close.iloc[-1])
        ret = (cur_close - entry_price) / entry_price
        if ret <= -stop_loss_pct:
            return True, [f"손절 ({ret*100:+.1f}%)"], "stop_loss"
        if ret >= take_profit_pct:
            return True, [f"익절 ({ret*100:+.1f}%)"], "take_profit"
        if trail_ma is not None and len(close) >= trail_ma:
            ma_val = float(close.iloc[-trail_ma:].mean())
            if cur_close < ma_val:
                return True, [f"MA{trail_ma} 이탈 (종가 {cur_close:.0f} < MA {ma_val:.0f})"], "ma_break"
        if hold_days >= max_hold_days:
            return True, [f"최대 보유일 초과 ({hold_days}거래일)"], "max_hold"
        return False, [], ""

    # --- 내부 헬퍼 ---
    def _check_buy(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        if not MarketHours.is_market_open("KRX"):
            return None
        triggered, reasons = self.evaluate_entry(
            data, min_daily_bars=self._min_daily_bars,
            ma_short=self._ma_short, ma_long=self._ma_long, abs_lb=self._abs_lb)
        if not triggered:
            return None
        current_price = float(data["close"].astype(float).iloc[-1])
        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)
        recommended_qty = max(1, int(self._max_per_stock_amount // current_price))
        metadata = {"close": current_price, "recommended_qty": recommended_qty}
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {current_price:,.0f} "
                f"(추천 {recommended_qty}주) | " + " | ".join(reasons))
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60.0,
                      target_price=target, stop_loss=stop, reasons=reasons, metadata=metadata)

    def _check_sell(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        entry_time = pos.get("entry_time")
        hold_days = max(0, count_trading_days_between(entry_time, now_kst()) - 1) if entry_time else 0
        should_sell, reasons, exit_reason = self.evaluate_sell_conditions(
            df=data, entry_price=entry_price, hold_days=hold_days,
            stop_loss_pct=self._stop_loss_pct, take_profit_pct=self._take_profit_pct,
            max_hold_days=self._max_hold_days, trail_ma=self._trail_ma)
        if not should_sell:
            return None
        current_price = float(data["close"].astype(float).iloc[-1])
        pnl_pct = (current_price - entry_price) / entry_price * 100
        metadata = {"entry_price": entry_price, "pnl_pct": pnl_pct,
                    "hold_days": hold_days, "exit_reason": exit_reason}
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매도 시그널: {stock_code} @ {current_price:,.0f} "
                f"({exit_reason}) | " + " | ".join(reasons))
        return Signal(signal_type=SignalType.SELL, stock_code=stock_code,
                      confidence=min(95.0, 60.0 + len(reasons) * 15),
                      reasons=reasons, metadata=metadata)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/strategies/rs_leader/test_strategy.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: 커밋**

```bash
git add strategies/rs_leader/strategy.py strategies/rs_leader/config.yaml tests/strategies/rs_leader/test_strategy.py
git commit -m "feat(rs_leader): RSLeaderStrategy (entry reuse RSLeaderRule, MA20-trail exit)"
```

---

## Task 3: 등록 — _adapter_factory + trading_config.json

**Files:**
- Modify: `runners/_adapter_factory.py`
- Modify: `config/trading_config.json`
- Test: `tests/strategies/rs_leader/test_registration.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/strategies/rs_leader/test_registration.py`:
```python
import json
from pathlib import Path

from runners._adapter_factory import build_adapter
from strategies.rs_leader.screener import RSLeaderScreenerAdapter


def test_build_adapter_returns_rs_leader():
    adapter = build_adapter("rs_leader")
    assert isinstance(adapter, RSLeaderScreenerAdapter)


def test_trading_config_has_rs_leader_paper():
    cfg = json.loads(Path("config/trading_config.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in cfg["strategies"]]
    assert "rs_leader" in names
    entry = next(s for s in cfg["strategies"] if s["name"] == "rs_leader")
    assert entry["enabled"] is True
    assert entry["regime_gate"] == "exclude_bear"
    assert entry["regime_index"] == "KOSPI"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/strategies/rs_leader/test_registration.py -v`
Expected: FAIL — build_adapter returns None (unknown 전략) / config에 rs_leader 없음.

- [ ] **Step 3: `_adapter_factory.py` 수정**

`runners/_adapter_factory.py` 의 `book_envelope_200d` elif 블록 바로 다음에 추가:
```python
        elif strategy_name == "rs_leader":
            from strategies.rs_leader.screener import RSLeaderScreenerAdapter
            return RSLeaderScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
```

- [ ] **Step 4: `config/trading_config.json` 수정**

`strategies` 배열의 마지막 항목(`book_pullback_ma5`) 뒤에 추가(직전 항목 끝 `}` 뒤 콤마 추가):
```json
    {
      "name": "rs_leader",
      "enabled": true,
      "max_capital_pct": 0.14,
      "regime_index": "KOSPI",
      "regime_gate": "exclude_bear"
    }
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/strategies/rs_leader/test_registration.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: 커밋**

```bash
git add runners/_adapter_factory.py config/trading_config.json tests/strategies/rs_leader/test_registration.py
git commit -m "feat(rs_leader): register screener adapter + 7th paper strategy in trading_config"
```

---

## Task 4: 통합 검증 (StrategyLoader 로드 + 회귀)

**Files:** (코드 변경 없음 — 검증 전용)

- [ ] **Step 1: rs_leader 전 테스트 + StrategyLoader 로드 확인**

Run:
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/strategies/rs_leader/ -v
```
Expected: 11 passed (screener 4 + strategy 5 + registration 2).

- [ ] **Step 2: StrategyLoader 가 RSLeaderStrategy 인스턴스화하는지 스모크**

Run:
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python -c "
from strategies.config import StrategyLoader
s = StrategyLoader().load_strategy('rs_leader')
print('LOADED', type(s).__name__)
assert type(s).__name__ == 'RSLeaderStrategy'
"
```
Expected: `LOADED RSLeaderStrategy`. (StrategyLoader API가 다르면 `strategies/config.py` 의 실제 로드 메서드명을 확인해 맞춘다 — 폴더명 `rs_leader` → `RSLeaderStrategy` 자동탐색.)

- [ ] **Step 3: 회귀 — 기존 전략 어댑터/로더 무영향**

Run:
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python -c "
from runners._adapter_factory import build_adapter
for n in ['elder_ema_pullback','minervini_volume_dryup','book_pullback_ma20','book_pullback_ma5','daytrading_3methods_breakout','book_envelope_200d','rs_leader']:
    a = build_adapter(n); assert a is not None, n
print('ALL 7 adapters OK')
"
```
Expected: `ALL 7 adapters OK`.

- [ ] **Step 4: 커밋 (검증 로그용 — 변경 없으면 생략)**

변경 파일 없으면 커밋 생략. 있으면:
```bash
git add -A && git commit -m "test(rs_leader): integration verification (loader + 7 adapters)"
```

---

## 봇 반영
신 config 필드·어댑터는 **봇 재시작 시 1회 로드**. 재시작 전까지 미반영(라이브 무영향). 페이퍼 독립자본 1천만은 main.py `_allocate_strategy_capital`이 활성 전략 폴더키마다 자동 할당.

## 자기검토 메모
- 스펙 §3.1 스크리너→Task1, §3.2/3.3 전략·config→Task2, §3.4/3.5 등록→Task3, §6 테스트→Task1~4, §8 봇반영→상기.
- DRY: 진입 추세로직 `RSLeaderRule` 단일 소스(검증·스크리너·전략 공유). 청산은 검증 4-bis(MA20 무조건 이탈)와 동일 우선순위로 strategy에 복제(라이브 프레임 정합).
- 한계(스펙 §7): 깊은약세 미입증→exclude_bear 회피, 저Sharpe·관찰용, RS음전환 미모델 — config/리포트에 명시됨.
- ★Task2 step4 `count_trading_days_between`/`MarketHours` 시그니처는 book_pullback_ma20 와 동일 사용 — 그 파일에서 import 경로 확인됨.
