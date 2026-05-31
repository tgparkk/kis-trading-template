from scripts.exit_multiverse import adapters


def test_four_adapters_exist():
    names = set(adapters.ADAPTERS.keys())
    assert names == {"elder_ema_pullback", "minervini_volume_dryup",
                     "book_pullback_ma20", "book_pullback_ma5"}


def test_grid_includes_live_value_elder():
    ad = adapters.ADAPTERS["elder_ema_pullback"]
    grid = ad.build_grid()
    assert any(g["stop_loss_pct"] == 0.08 and g["take_profit_pct"] == 0.30
               and g["max_hold_bars"] == 100 and g["trail_ema"] == 13
               and g["trend_flip_exit"] is True for g in grid)


def test_grid_includes_live_value_ma5():
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    grid = ad.build_grid()
    assert any(g["stop_loss_pct"] == 0.03 and g["take_profit_pct"] == 0.15
               and g["max_hold_bars"] == 30 and g["trail_ma"] == 5 for g in grid)


def test_entry_mechanism_values():
    assert adapters.ADAPTERS["elder_ema_pullback"].entry_mechanism == "stop"
    assert adapters.ADAPTERS["minervini_volume_dryup"].entry_mechanism == "market"
    assert adapters.ADAPTERS["book_pullback_ma20"].entry_mechanism == "market"
    assert adapters.ADAPTERS["book_pullback_ma5"].entry_mechanism == "market"
