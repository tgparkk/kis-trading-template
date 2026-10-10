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


# ── fix round 1 ─────────────────────────────────────────────────────────────────
import json

import pandas as pd


def _frozen_env(monkeypatch, tmp_path, md5_value=None):
    (tmp_path / "PREREG.md").write_text("x", encoding="utf-8")
    (tmp_path / "proxy_coef.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(S, "RESULTS", tmp_path)
    monkeypatch.setattr(S, "PREREG", tmp_path / "PREREG.md")
    monkeypatch.setattr(S, "PREREG_FROZEN_BLOB", "abc")
    monkeypatch.setattr(RUN, "blob", lambda p: "abc")
    monkeypatch.setattr(RUN, "clean_package", lambda: True)
    monkeypatch.setattr(S, "PROXY_COEF_MD5", RUN.md5(tmp_path / "proxy_coef.json") if md5_value is None else md5_value)


def test_effective_n1_excludes_marked_days_without_control():
    df = pd.DataFrame({"x": [1, 0, 1, 1, 0], "day": [1, 1, 2, 3, 3], "y_sl": [0.0] * 5})
    assert RUN.effective_n1(df) == 2      # day 2 has no control -> dropped
    import dataclasses
    fe_sl = dataclasses.replace(_fe(-1.0, 0.01, 0.02), n1=99)
    assert RUN.label(fe_sl, fe_sl, "cr1", fe_sl.n1, 0.3, 0.1) == "판별 보류(n₁<100)"


def test_require_frozen_needs_proxy_coef_md5(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    RUN.require_frozen()                                   # all good -> no raise
    monkeypatch.setattr(S, "PROXY_COEF_MD5", "")
    with pytest.raises(SystemExit):
        RUN.require_frozen()
    monkeypatch.setattr(S, "PROXY_COEF_MD5", "deadbeef")
    with pytest.raises(SystemExit):
        RUN.require_frozen()


def test_proxy_stage_refuses_after_freeze(monkeypatch):
    monkeypatch.setattr(S, "PREREG_FROZEN_BLOB", "abc")
    with pytest.raises(SystemExit):
        RUN.stage_proxy(None)


def _fake_build(tmp_path):
    (tmp_path / "ledger_A.csv").write_text("a\n", encoding="utf-8")
    meta = {"md5": {"ledger_A.csv": RUN.md5(tmp_path / "ledger_A.csv")}}
    (tmp_path / "build_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return RUN.build_hashes()


def test_open_refuses_tampered_build_output(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    seal = {"build_md5": _fake_build(tmp_path)}
    (tmp_path / "seal.json").write_text(json.dumps(seal), encoding="utf-8")
    (tmp_path / "ledger_A.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.stage_open(None)
    assert not (tmp_path / "open.json").exists()


def test_seal_linkage_detects_meta_change_and_accepts_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "RESULTS", tmp_path)
    seal = {"build_md5": _fake_build(tmp_path)}
    RUN.check_seal_linkage(seal)
    (tmp_path / "build_meta.json").write_text(json.dumps({"md5": {}}), encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.check_seal_linkage(seal)


@pytest.mark.parametrize("name", ["seal.json", "open.json"])
def test_build_refuses_when_seal_or_open_exists(monkeypatch, tmp_path, name):
    _frozen_env(monkeypatch, tmp_path)
    (tmp_path / name).write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.stage_build(None)
