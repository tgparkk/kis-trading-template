from runners.screener_snapshot_collector import resolve_active_strategies


def test_resolve_from_config_strategies():
    config = type("C", (), {})()
    config.strategies = [
        {"name": "elder_ema_pullback", "enabled": True},
        {"name": "minervini_volume_dryup", "enabled": True},
        {"name": "disabled_one", "enabled": False},
    ]
    out = resolve_active_strategies(config)
    assert out == ["elder_ema_pullback", "minervini_volume_dryup"]


def test_resolve_fallback_to_all_when_no_config():
    out = resolve_active_strategies(None)
    assert isinstance(out, list) and len(out) > 0
