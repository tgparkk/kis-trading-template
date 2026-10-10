"""최종 리뷰 I5 (봉인 고정) + 동결 전 수정 묶음 — 백필 보고 가드 · 진입 불가 집단별 수 · 블라인드 안전 봉인 인쇄."""
import json
from datetime import date

import pandas as pd
import pytest

from backtest.concept_axes.dt_dart_filter import run as RUN
from backtest.concept_axes.dt_dart_filter import settings as S
from backtest.concept_axes.dt_dart_filter import surv as SV
from backtest.concept_axes.dt_dart_filter.tests.test_run import _fake_build, _frozen_env, _seal_files


# ── I5 · seal ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["seal.json", "open.started", "open.json"])
def test_seal_refuses_rerun(monkeypatch, tmp_path, name):
    _frozen_env(monkeypatch, tmp_path)
    (tmp_path / name).write_text('{"keep": 1}', encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.stage_seal(None)                     # conn 을 쓰기 전에 거부해야 한다
    assert (tmp_path / name).read_text(encoding="utf-8") == '{"keep": 1}'


def test_sealed_report_md5_line_roundtrip(tmp_path):
    _seal_files(tmp_path, {"a": 1})
    RUN.check_sealed_report(tmp_path / "sealed_report.md", tmp_path / "seal.json")
    (tmp_path / "seal.json").write_text(json.dumps({"a": 2}), encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.check_sealed_report(tmp_path / "sealed_report.md", tmp_path / "seal.json")


def test_sealed_report_without_or_with_two_md5_lines_refused(tmp_path):
    (tmp_path / "seal.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sealed_report.md").write_text("# 봉인\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.check_sealed_report(tmp_path / "sealed_report.md", tmp_path / "seal.json")
    h = RUN.md5(tmp_path / "seal.json")
    (tmp_path / "sealed_report.md").write_text(RUN.seal_md5_line(h) + "\n" + RUN.seal_md5_line(h) + "\n",
                                               encoding="utf-8")
    with pytest.raises(SystemExit):
        RUN.check_sealed_report(tmp_path / "sealed_report.md", tmp_path / "seal.json")
    with pytest.raises(SystemExit):
        RUN.check_sealed_report(tmp_path / "missing.md", tmp_path / "seal.json")


# ── I5 · open ────────────────────────────────────────────────────────────────────
def test_open_refuses_seal_json_not_matching_report(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    _seal_files(tmp_path, {"build_md5": _fake_build(tmp_path)}, report_md5="0" * 32)
    with pytest.raises(SystemExit, match="seal.json"):
        RUN.stage_open(None)
    assert not (tmp_path / "open.started").exists()


def test_open_refuses_when_started_marker_exists(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    _seal_files(tmp_path, {"build_md5": _fake_build(tmp_path)})
    (tmp_path / "open.started").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="open.started"):
        RUN.stage_open(None)


def test_open_writes_started_marker_before_any_computation(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    monkeypatch.setattr(RUN, "_check_build", lambda conn: {})
    _seal_files(tmp_path, {"build_md5": _fake_build(tmp_path)})

    def boom(conn):
        assert (tmp_path / "open.started").exists()          # 계산 전 표식이 이미 있어야 한다
        raise RuntimeError("stop")
    monkeypatch.setattr(RUN, "_load_env", boom)
    with pytest.raises(RuntimeError):
        RUN.stage_open(None)
    marker = json.loads((tmp_path / "open.started").read_text(encoding="utf-8"))
    assert marker["seal_md5"] == RUN.md5(tmp_path / "seal.json")
    with pytest.raises(SystemExit):                          # 중간에 죽어도 두 번째 개봉은 거부
        RUN.stage_open(None)


# ── 백필 보고 ↔ settings 가드(build) ─────────────────────────────────────────────
def _chk(**kw):
    base = dict(complete=True, window=[S.FILING_START.isoformat(), S.SCAN_END.isoformat()], types=["A", "B", "I"])
    base.update(kw)
    return base


def test_check_backfill_report_matches_settings():
    RUN.check_backfill_report(_chk())
    RUN.check_backfill_report(_chk(types=["I", "A", "B"]))
    for bad in (_chk(complete=False), _chk(window=["2021-01-01", "2023-12-31"]), _chk(types=["A", "B"]),
                _chk(window=None), {k: v for k, v in _chk().items() if k != "types"}):
        with pytest.raises(SystemExit):
            RUN.check_backfill_report(bad)


def test_build_refuses_backfill_report_window_mismatch(monkeypatch, tmp_path):
    _frozen_env(monkeypatch, tmp_path)
    monkeypatch.setattr(RUN, "committed_unchanged", lambda p: True)
    (tmp_path / "backfill_check.json").write_text(json.dumps(_chk(window=["2021-01-01", "2024-03-11"])),
                                                  encoding="utf-8")
    with pytest.raises(SystemExit, match="백필"):
        RUN.stage_build(None)


# ── 진입 불가 집단별 수(open 보조) · 대리 소형 비율(seal) ─────────────────────────
def _led():
    rows = [  # code, scan_date, status, p_L
        ("1", date(2021, 3, 2), "filled", 0.2), ("2", date(2021, 3, 2), "halt_entry", 0.3),
        ("3", date(2021, 3, 2), "halt_entry", 0.1), ("4", date(2022, 5, 2), "filled", 0.7),
        ("5", date(2022, 5, 2), "halt_entry", 0.8), ("6", date(2022, 5, 2), "no_fill", 0.1),
        ("7", date(2023, 1, 3), "filled", float("nan")), ("8", date(2023, 1, 3), "filled", 0.4),
    ]
    return pd.DataFrame(rows, columns=["stock_code", "scan_date", "status", "p_L"])


def test_halt_entry_counts_by_arm_small_proxy_only():
    marks = {("2", date(2021, 3, 2)), ("1", date(2021, 3, 2)), ("5", date(2022, 5, 2))}
    out = RUN.halt_entry_counts(_led(), marks)
    assert out == {"표식": {"halt_entry": 1, "n": 2}, "대조": {"halt_entry": 1, "n": 2}}


def test_pl_small_share_by_year():
    out = RUN.pl_small_share_by_year(_led())
    assert out[2021] == {"n": 3, "n_nan": 0, "share_small": 1.0}
    assert out[2022] == {"n": 3, "n_nan": 0, "share_small": pytest.approx(1 / 3)}
    assert out[2023] == {"n": 1, "n_nan": 1, "share_small": 1.0}


def test_seal_report_lines_label_raw_counts_and_print_blind_safe_extras():
    gate = dict(rej_cr1=0.1, rej_2w=0.09, tool="cr1", reason="ok", n_valid=400, n_valid_2w=400, n_valid_min=380,
                sd_null=1.2, mean_se_cr1=1.1, rej_lo_cr1=0.05, rej_lo_2w=0.06, why_cr1="ok", why_2w="ok",
                mean_fake_n1=110.5, n_fake=400, n_skipped=3)
    seal = dict(n1=110, n1_raw=130, n1_raw_by_year={2021: 50, 2022: 80}, n0_raw=5000, n0=4100, sd_ctrl_sl=8.0,
                sd_ctrl_tp=8.1, gate=gate, mde_null=2.9, mde_se=2.7,
                pl_small_share_by_year={2021: {"n": 10, "n_nan": 0, "share_small": 0.7}}, final_verdict=None, reseal=None,
                surv={"surv_i": 0.01, "n_i": 300, "surv_ii": 0.005, "n_ii": 2000,
                      "breakdown_i": {c: 1 for c in SV.CLASSES}, "breakdown_ii": {c: 2 for c in SV.CLASSES}})
    txt = "\n".join(RUN.seal_report_lines(seal))
    assert "원시" in txt and "n₁ 원시 연도별" in txt and "대조 원시 5,000" in txt
    assert "p_L<0.5 비율" in txt and "2021 0.700" in txt
    assert "하측(p1<0.05) CR1 0.050 · 2원 0.060" in txt and "가짜 평균 n₁ 110.5" in txt and "유효 400/400(문턱 380)" in txt
    assert "코넥스 제외" in txt
