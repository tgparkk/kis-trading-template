from main import should_use_volume_fallback


def test_no_fallback_when_some_strategy_has_candidates():
    assert should_use_volume_fallback({"elder_ema_pullback": ["005930"], "book_pullback_ma5": []}) is False


def test_fallback_only_when_all_empty():
    assert should_use_volume_fallback({"elder_ema_pullback": [], "book_pullback_ma5": []}) is True


def test_fallback_when_empty_dict():
    assert should_use_volume_fallback({}) is True
