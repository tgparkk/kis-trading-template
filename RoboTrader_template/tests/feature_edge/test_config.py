from scripts.feature_edge import config


def test_config_constants_present():
    assert config.UNIVERSE_MIN_TRADING_VALUE == 1_000_000_000
    assert config.PERIOD_START == "2021-01-01"
    assert config.OOS_SPLIT == "2024-06-30"
    assert config.FWD_HORIZONS == (5, 10, 20)
    # 트리플배리어: (up_pct, down_pct, horizon_bars) 세트
    assert (0.10, 0.05, 10) in config.BARRIER_SETS
    assert config.COVERAGE_MIN == 0.60
    assert config.PANEL_PATH.endswith("feature_panel.parquet")
