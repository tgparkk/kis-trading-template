import pytest

from backtest.concept_axes.dt_dart_filter import run as RUN
from backtest.concept_axes.dt_dart_filter import settings as S
from backtest.concept_axes.dt_dart_filter.stats import FE


def _fe(beta, p1, p2):
    return FE(beta, 1.0, 1.0, p1, p2, p1, p2, 500, 120, 300, 200, 40)


def test_label_present_requires_both_rules_threshold_and_survivorship():
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.03, 0.06), "cr1", 120, 0.3, 0.1) == "있음(−)"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.20, 0.40), "cr1", 120, 0.3, 0.1) == "판별 보류"
    assert RUN.label(_fe(-0.3, 0.01, 0.02), _fe(-0.3, 0.01, 0.02), "cr1", 120, 0.3, 0.1) == "판별 보류"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-0.9, 0.01, 0.02), "cr1", 120, 0.05, 0.1) == "판별 보류"


def test_label_reverse_tool_fail_and_small_n():
    assert RUN.label(_fe(1.2, 0.99, 0.01), _fe(1.2, 0.99, 0.01), "cr1", 120, 0.3, 0.1) == "역방향"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-1.0, 0.01, 0.02), "fail", 120, 0.3, 0.1) == "판정 불가(도구)"
    assert RUN.label(_fe(-1.0, 0.01, 0.02), _fe(-1.0, 0.01, 0.02), "cr1", 99, 0.3, 0.1) == "판별 보류(n₁<100)"


def test_require_frozen_refuses_when_blob_empty(monkeypatch):
    monkeypatch.setattr(S, "PREREG_FROZEN_BLOB", "")
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_open_refuses_without_frozen(monkeypatch):
    monkeypatch.setattr(S, "PREREG_FROZEN_BLOB", "")
    with pytest.raises(SystemExit):
        RUN.main(["--stage", "open"])
