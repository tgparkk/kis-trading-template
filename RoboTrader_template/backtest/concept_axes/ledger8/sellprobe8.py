"""라이브 청산 규칙을 «라이브 코드로» 얻는다 — 익절·손절 비율(엔진 경로) + 데이터 청산(전략 매도 분기).

1. `resolve_live_tp_sl` — `TradingDecisionEngine.execute_virtual_buy`(core/trading_decision_engine.py:499-714)를
   그대로 부르되 `virtual_trading` 자리에 인자만 받아 적는 스텁을 끼운다(DB 0 · 기록 0).
   라이브 호출부(bot/trading_analyzer.py:275-281)처럼 tp/sl 인자를 넘기지 않으므로 3순위(전략 config
   `take_profit_pct`/`stop_loss_pct`, :589-607) → 4순위 기본값(:611-634) → 손절 하한 3%(:655-658)가 그대로 돈다.
   `on_order_filled` 통보(:703-710)는 전략 «사본»에만 간다.
2. `SellProbe` — 라이브 `on_tick` 매도 루프(strategies/base.py:739-761) 한 번을 재현한다.
   보유 종목 → generate_signal(code, D+k 일봉 창(마지막 봉 D+k−1), 'daily') → (min_len · timeframe 게이트) →
   보유 분기 → `_check_sell`. 전략 모듈의 `now_kst` 를 D+k 09:02 로 바꿔 끼워 보유일 계산식 두 벌
   (`count_trading_days_between(...)-1` · `_trading_days_elapsed`)을 코드 그대로 쓴다.
"""
from __future__ import annotations

import asyncio
import copy
import importlib
from datetime import date, datetime
from typing import Any, Callable, Dict, Optional, Tuple
from unittest import mock

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

from core.models import StockState, TradingStock                  # noqa: E402
from core.trading_decision_engine import TradingDecisionEngine    # noqa: E402
from strategies.base import SignalType                            # noqa: E402

from . import sources8 as SRC8
from .exitsim8 import ExitRules, Pos

WindowFn = Callable[[str, date], Tuple[Any, Dict]]


class _CaptureVTM:
    """`VirtualTradingManager.execute_virtual_buy` 자리 — 인자만 받아 적고 기록 ID 1 을 돌려준다(DB 0)."""

    def __init__(self) -> None:
        self.kwargs: Dict[str, Any] = {}

    def execute_virtual_buy(self, **kwargs: Any) -> int:
        self.kwargs = dict(kwargs)
        return 1


def resolve_live_tp_sl(folder: str, strategy) -> ExitRules:
    eng = TradingDecisionEngine()
    cap = _CaptureVTM()
    eng.virtual_trading = cap
    eng.set_strategies({folder: copy.deepcopy(strategy)})
    ts = TradingStock(stock_code="000000", stock_name="ledger8-probe", state=StockState.SELECTED,
                      selected_time=datetime(2026, 1, 1))
    ok = asyncio.run(eng.execute_virtual_buy(ts, None, "ledger8 tp/sl probe", buy_price=10_000.0, quantity=1,
                                             strategy_name=folder))
    if not ok or "target_profit_rate" not in cap.kwargs:
        raise RuntimeError(f"{folder}: 엔진 경로로 tp/sl 을 못 얻었다")
    tp, sl = float(cap.kwargs["target_profit_rate"]), float(cap.kwargs["stop_loss_rate"])
    if (tp, sl) != (float(ts.target_profit_rate), float(ts.stop_loss_rate)):
        raise RuntimeError(f"{folder}: VTM 인자와 trading_stock 값이 다르다 ({tp},{sl}) vs "
                           f"({ts.target_profit_rate},{ts.stop_loss_rate})")
    rm = (getattr(strategy, "config", None) or {}).get("risk_management", {})
    src = ("config(take_profit_pct/stop_loss_pct)"
           if rm.get("take_profit_pct") is not None and rm.get("stop_loss_pct") is not None
           else "⚠️ 기본값·비율키 경로 — 엔진 config 미주입")
    return ExitRules(tp=tp, sl=sl, max_hold_days=int(strategy.max_holding_days), source=src)


class SellProbe:
    """(포지션, 평가일 D+k) → 데이터 청산 사유 코드(`metadata['exit_reason']`) 또는 None."""

    def __init__(self, folder: str, strategy, window_fn: WindowFn):
        if getattr(strategy, "_quant", None) is not None:
            raise RuntimeError("SellProbe 는 _check_buy 호출 «전»에 만들어야 한다(envelope DB 리더 deepcopy 방지)")
        self.folder = folder
        self.inst = copy.deepcopy(strategy)
        self.inst.positions = {}
        self.inst.daily_trades = 0
        self.mod = importlib.import_module(type(strategy).__module__)
        self.window_fn = window_fn
        self.calls = 0

    def __call__(self, pos: Pos, day: date) -> Optional[str]:
        data, _diag = self.window_fn(pos.code, day)
        if data is None or len(data) == 0:          # base.py:748 과 같은 조건
            return None
        self.inst.positions = {pos.code: {"quantity": int(pos.qty), "entry_price": float(pos.entry_price),
                                          "entry_time": pos.entry_time}}
        try:
            with mock.patch.object(self.mod, "now_kst", return_value=SRC8.as_of(day)):
                sig = self.inst.generate_signal(pos.code, data, timeframe="daily")
        finally:
            self.inst.positions = {}
        self.calls += 1
        if sig is None or sig.signal_type not in (SignalType.SELL, SignalType.STRONG_SELL):
            return None
        return str((sig.metadata or {}).get("exit_reason") or "strategy_sell")
