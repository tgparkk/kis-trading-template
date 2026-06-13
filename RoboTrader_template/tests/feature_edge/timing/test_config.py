from scripts.feature_edge.timing import config


def test_constants():
    assert config.INTRADAY_START == "2025-02-24"
    assert config.INTRADAY_END == "2026-06-12"
    assert config.OOS_SPLIT == "2026-01-01"
    assert config.SLIPPAGE_PER_SIDE == 0.001
    assert config.OPENING_RANGE_MIN == 30
    assert config.TIMING_STRATEGIES == (
        "daytrading_3methods_breakout", "deep_mr_dev20", "book_envelope_200d")
    assert config.TRADES_PATH.endswith("trades.parquet")
    assert config.REPORT_PATH.endswith("timing_report.md")
