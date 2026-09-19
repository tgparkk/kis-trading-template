"""registry 가 라이브 소스와 맞는지 — AST·설정 파일 대조(DB·전략 import 없음).

라이브가 바뀌면 이 테스트가 먼저 깨진다(스펙 검증표 #1·#20).
"""
from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from backtest.concept_axes.ledger8 import registry as R

ROOT = Path(__file__).resolve().parents[4]
NEEDLES = (
    (R.G_MIN_LEN, "self.get_min_data_length()"),
    (R.G_TIMEFRAME, "timeframe != 'daily'"),
    (R.G_HELD, "stock_code in self.positions"),
    (R.G_DAILY_TRADES, "self.daily_trades >= self._max_daily_trades"),
    (R.G_MAX_POSITIONS, "len(self.positions) >= self._max_positions"),
)


def _class(folder: str) -> ast.ClassDef:
    tree = ast.parse((ROOT / "strategies" / folder / "strategy.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == R.spec(folder).cls:
            return node
    raise AssertionError(f"{folder}: 클래스 {R.spec(folder).cls} 없음")


def _method(cls: ast.ClassDef, name: str):
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _class_attr(cls: ast.ClassDef, name: str):
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def gate_order_in_source(fn) -> tuple:
    out = []
    for st in fn.body:
        if isinstance(st, ast.If):
            text = ast.unparse(st.test)
            for tok, needle in NEEDLES:
                if needle in text:
                    out.append(tok)
                    break
        elif isinstance(st, ast.Return) and st.value is not None and "self._check_buy(" in ast.unparse(st.value):
            out.append(R.G_CHECK_BUY)
    return tuple(out)


def _trading_config() -> dict:
    return json.loads((ROOT / "config" / "trading_config.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_gate_order_matches_source(folder):
    assert gate_order_in_source(_method(_class(folder), "generate_signal")) == R.spec(folder).gate_order


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_cap_log_presence(folder):
    fn = _method(_class(folder), "generate_signal")
    assert ("_log_cap_skip" in ast.unparse(fn)) == R.spec(folder).has_cap_log


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_name_exit_timeframe_and_no_on_tick_override(folder):
    cls = _class(folder)
    assert _class_attr(cls, "name") == R.spec(folder).cls          # 로거 = strategy.<name>(base.py:393)
    assert _class_attr(cls, "exit_timeframe") == "daily"            # 매도 루프 = D-1 확정봉(base.py:742-744)
    assert _method(cls, "on_tick") is None                          # 8전략 모두 BaseStrategy.on_tick


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_evaluate_entry_arity(folder):
    fn = _method(_class(folder), "evaluate_entry")
    lens = {len(n.value.elts) for n in ast.walk(fn)
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)}
    assert lens == {R.spec(folder).entry_eval_arity}


def test_registry_covers_enabled_strategies():
    enabled = {s["name"] for s in _trading_config()["strategies"] if s.get("enabled")}
    assert enabled == set(R.ALL_FOLDERS)


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_latest_regime_index_matches_trading_config(folder):
    live = {s["name"]: s.get("regime_index", "both") for s in _trading_config()["strategies"]}
    assert R.regime_index_for(folder, R.LEDGER_END)[0] == live[folder]


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_latest_k_and_mdt_match_config_yaml(folder):
    y = yaml.safe_load((ROOT / "strategies" / folder / "config.yaml").read_text(encoding="utf-8"))
    rm = y["risk_management"]
    assert R.k_for(folder, R.LEDGER_END)[0] == int(rm["max_positions"])
    assert R.mdt_for(folder, R.LEDGER_END)[0] == int(rm.get("max_daily_trades", 5))


def test_history_lookups():
    assert R.k_for("minervini_volume_dryup", date(2026, 9, 17))[0] == 3
    assert R.k_for("minervini_volume_dryup", date(2026, 9, 18))[0] == 6
    assert R.k_for("book_pullback_ma20", date(2026, 9, 17))[0] == 5
    assert R.regime_index_for("daytrading_3methods_breakout", date(2026, 9, 11))[0] == "KOSDAQ"
    assert R.regime_index_for("daytrading_3methods_breakout", date(2026, 9, 14))[0] == "auto"
    assert R.corp_action_mode_for("rs_leader", date(2026, 9, 16)) == "shadow"
    assert R.corp_action_mode_for("rs_leader", date(2026, 9, 17)) == "live"
    assert R.corp_action_mode_for("elder_ema_pullback", date(2026, 9, 17)) is None
    assert "_ontick_skip_log" not in R.state_attrs("rs_leader")
    assert "_ontick_skip_log" in R.state_attrs("book_pullback_ma20")
    assert R.LOGGER_TO_FOLDER["strategy.RSLeaderStrategy"] == "rs_leader"
    with pytest.raises(KeyError):
        R.spec("no_such_strategy")
