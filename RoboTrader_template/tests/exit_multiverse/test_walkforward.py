import pandas as pd
from scripts.exit_multiverse import walkforward


def test_make_folds_count_and_no_overlap():
    folds = walkforward.make_folds("2021-01-01", "2026-05-31",
                                   train_months=24, test_months=6, step_months=6)
    assert len(folds) >= 6
    for f in folds:
        assert f["train_start"] < f["train_end"] <= f["test_start"] < f["test_end"]


def test_make_folds_train_includes_bear_year():
    folds = walkforward.make_folds("2021-01-01", "2026-05-31", 24, 6, 6)
    assert any(f["train_start"] <= "2022-06-01" <= f["train_end"] for f in folds)
