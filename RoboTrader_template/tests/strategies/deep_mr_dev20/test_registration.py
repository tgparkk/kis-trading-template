"""deep_mr_dev20 등록 검증 — 어댑터 팩토리 + trading_config + 전략별 사이징."""
import json
from pathlib import Path

from runners._adapter_factory import build_adapter
from strategies.deep_mr_dev20.screener import DeepMrDev20ScreenerAdapter


def test_build_adapter_returns_deep_mr_dev20():
    adapter = build_adapter("deep_mr_dev20")
    assert isinstance(adapter, DeepMrDev20ScreenerAdapter)


def test_trading_config_has_deep_mr_dev20_paper():
    cfg = json.loads(Path("config/trading_config.json").read_text(encoding="utf-8"))
    entry = next(s for s in cfg["strategies"] if s["name"] == "deep_mr_dev20")
    assert entry["enabled"] is True
    # 폭락 매수는 약세장이 기회 구간(워크포워드 2022H1 -4.8% 방어 확인) → gate 없음
    assert entry["regime_gate"] == "none"
    assert entry["regime_index"] == "KOSPI"


def test_yaml_has_s2_sizing():
    import yaml
    cfg = yaml.safe_load(
        Path("strategies/deep_mr_dev20/config.yaml").read_text(encoding="utf-8"))
    # S2 사이징(자본/K=200만, 사이징 시나리오 측정 스위트스팟) — 가상매매 실체결 사이징
    assert cfg["risk_management"]["paper_investment_per_stock"] == 2_000_000
    assert cfg["risk_management"]["max_positions"] == 5
    assert cfg["parameters"]["entry_deviation_pct"] == -20.0


def test_virtual_manager_per_strategy_sizing():
    from core.virtual_trading_manager import VirtualTradingManager
    vtm = VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)
    vtm.allocate_strategy_capital("deep_mr_dev20", 10_000_000)
    vtm.allocate_strategy_capital("other_strat", 10_000_000)
    # 전략별 종목당 금액 미설정 → 기존 100만 (7전략 무영향 보장)
    assert vtm.get_max_quantity(10_000, strategy_name="other_strat") == 100
    # dev20 = S2 사이징 200만
    vtm.set_strategy_investment_amount("deep_mr_dev20", 2_000_000)
    assert vtm.get_max_quantity(10_000, strategy_name="deep_mr_dev20") == 200
    # 전략 budget 이 더 작으면 budget 이 상한
    vtm.set_strategy_investment_amount("deep_mr_dev20", 20_000_000)
    assert vtm.get_max_quantity(10_000, strategy_name="deep_mr_dev20") == 1000
