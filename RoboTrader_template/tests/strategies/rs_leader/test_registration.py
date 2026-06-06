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
