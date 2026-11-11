"""2차 재리뷰(stage2_delta2) — G1 앞 단계 출처 관문 · G2 `run.main()` 통합(합성 · DB 0) · W4 G9·G10 값 · W5."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, timedelta

import numpy as np
import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.minute_rules import analyze as A
from backtest.concept_axes.minute_rules import data as D
from backtest.concept_axes.minute_rules import engine as E
from backtest.concept_axes.minute_rules import run as RUN

from .synth import flat
from .test_delta_guards import W_of, calc, tl
from .test_run import DT, FakeGit


# ── G1 ───────────────────────────────────────────────────────────────────
def _prior(tmp_path, monkeypatch, **over):
    monkeypatch.setattr(RUN, "REPO", tmp_path)
    md, js = tmp_path / "RESULTS_explore.md", tmp_path / "RESULTS_explore.json"
    md.write_text("x", encoding="utf-8")
    meta = tmp_path / "run_meta.json"
    meta.write_text("{}", encoding="utf-8")
    code = {"a.py": "1"}
    d = dict(spec_sha256=A.SPEC_SHA256, B=A.SPEC["B"], results_md_sha256=hashlib.sha256(b"x").hexdigest(),
             prov=dict(code_digest=A.code_digest(code), run_meta={"E": hashlib.sha256(b"{}").hexdigest()}))
    d.update(over)
    js.write_text(json.dumps(d), encoding="utf-8")
    return js, md, code, {"E": meta}


def test_g1_prior_accepts_gated_same_code(tmp_path, monkeypatch):
    js, md, code, rm = _prior(tmp_path, monkeypatch)
    A.verify_prior(js, md, FakeGit({}), code_now=code, run_meta_expect=rm)


@pytest.mark.parametrize("over,code_now", [
    (dict(prov=None), None),                                             # 함수 직접 호출 문서(출처 관문 없음)
    (dict(B=200), None),                                                  # B ≠ 10,000
    ({}, {"a.py": "2"}),                                                  # E 코드 ≠ 지금 코드
    (dict(prov=dict(code_digest="x", run_meta={"E": "0"})), None),         # run_meta 해시 불일치
])
def test_g1_prior_rejects_ungated_or_other_code(tmp_path, monkeypatch, over, code_now):
    js, md, code, rm = _prior(tmp_path, monkeypatch, **over)
    with pytest.raises(SystemExit):
        A.verify_prior(js, md, FakeGit({}), code_now=code_now or code, run_meta_expect=rm)


def test_g1_run_meta_mismatch_alone_rejected(tmp_path, monkeypatch):
    js, md, code, rm = _prior(tmp_path, monkeypatch)
    rm["E"].write_text('{"changed": 1}', encoding="utf-8")
    with pytest.raises(SystemExit):
        A.verify_prior(js, md, FakeGit({}), code_now=code, run_meta_expect=rm)


# ── G2 run.main() 통합 ───────────────────────────────────────────────────
def _cal(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


@pytest.fixture
def main_env(tmp_path, monkeypatch):
    """DB·git 없이 `run.main()` 을 돌리는 가짜 환경 — 합성 로트 3개(E 창) · 결과 폴더·비공개 폴더 = 임시."""
    cal = _cal(date(2025, 9, 1), 60)
    ledger = tmp_path / "ledger.csv"
    rows = ["strategy,scan_date,stock_code,rank,ref_close,band_lo,band_hi,band_ok,entry_date,exit_reason,flags"]
    for i, k in enumerate((5, 6, 7)):
        rows.append(f"{DT},{cal[k - 1]},{i:06d},1,10000,,10300,True,{cal[k]},sl,survivor_universe")
    ledger.write_text("\n".join(rows) + "\n", encoding="utf-8")
    meta = tmp_path / "ledger_meta.json"
    meta.write_text(json.dumps({"exit_rules": {DT: {"tp": 0.1, "sl": 0.1, "max_hold_days": 10}}}), encoding="utf-8")
    results, private = tmp_path / "repo_results", tmp_path / "private"
    monkeypatch.setattr(RUN, "LEDGER", ledger)
    monkeypatch.setattr(RUN, "LEDGER_META", meta)
    monkeypatch.setattr(RUN, "RESULTS", results)
    monkeypatch.setattr(RUN, "require_clean_tree", lambda *a, **k: None)
    monkeypatch.setattr(RUN, "git_sha", lambda: "deadbeef")

    class Conn:
        def close(self):
            pass

    monkeypatch.setattr(D, "connect", lambda: Conn())
    monkeypatch.setattr(D, "load_calendar", lambda conn, a, b: cal)
    monkeypatch.setattr(D, "load_market_of", lambda conn: {f"{i:06d}": "KOSDAQ" for i in range(3)})

    def load_daily(conn, codes, start, end, info=None):
        if info is not None:
            info.update(daily_rows=0)
        return {c: {d: X.Bar(d, 10000.0, 10000.0, 10000.0, 10000.0) for d in cal} for c in codes}

    monkeypatch.setattr(RUN, "load_daily", load_daily)
    monkeypatch.setattr(RUN, "load_corp_events", lambda conn, a, b, info=None: {})
    monkeypatch.setattr(RUN, "load_tv_rank", lambda conn, days: {})
    monkeypatch.setattr(RUN, "load_kospi", lambda conn, a, b: {})

    def load_minute_days(conn, keys, market_of, calendar=None, gap_rows=None):
        keys = sorted(keys)
        bars = np.stack([flat(10000.0).astype(np.float32) for _ in keys])
        metas = [D.DayMeta(code=c, day=d, n_rows=380, prev_day_volume=50_000.0) for c, d in keys]
        obs = np.nan_to_num(bars[:, :, E.F_VOL]) > 0
        return D.MinuteBundle(keys, bars, obs, metas, {}, {k: D.raw_checksum([]) for k in keys})

    monkeypatch.setattr(D, "load_minute_days", load_minute_days)
    monkeypatch.setattr(D, "fetch_minute_rows", lambda conn, keys: {k: [] for k in keys})
    args = ["--window", "E", "--asof", cal[-1].isoformat(), "--private-dir", str(private),
            "--gap-cache", str(tmp_path / "gap.json")]
    return args, results, private


def test_g2_main_writes_lot_csv_only_outside_repo_results(main_env):
    args, results, private = main_env
    assert RUN.main(args) == 0
    assert (private / "E" / "lots_rule.csv").exists() and (private / "E" / "fake_timing.csv").exists()
    assert (private / "E" / RUN.SEAL_README).read_text(encoding="utf-8") == RUN.SEAL_NOTE     # W1
    assert list(results.rglob("*.csv")) == []                             # 레포 results/ 에 csv 0(NB1)
    m = json.loads((results / "E" / "run_meta.json").read_text(encoding="utf-8"))
    for name in ("lots_rule.csv", "fake_timing.csv"):
        assert m["outputs"][name]["sha256"] == hashlib.sha256((private / "E" / name).read_bytes()).hexdigest()
    assert m["fakes"] == 100 and m["outputs"]["fake_timing.csv"]["rows"] == 300 and m["git_sha"] == "deadbeef"
    assert m["csv_dir"] == str(private / "E")


def test_g2_main_rejects_fakes_other_than_100(main_env):
    args, _, _ = main_env
    with pytest.raises(SystemExit):
        RUN.main(args + ["--fakes", "5"])


def test_g2_main_rejects_private_dir_inside_git_tree(main_env):
    args, _, _ = main_env
    i = args.index("--private-dir")
    bad = args[: i + 1] + [str(RUN.BASE / "results" / "priv")] + args[i + 2:]
    with pytest.raises(SystemExit):
        RUN.main(bad)


# ── W4 G9·G10 값 ─────────────────────────────────────────────────────────
def test_w4_g9_boundary_inclusive_and_g10_post_0703():
    lots = [tl(1.0 + i, fm=i, vint="False" if i in (0, 3, 5, 8) else "True") for i in range(9)]
    c = calc(W_of(lots))
    assert c.out["g9_q75"] == pytest.approx(6.0)
    assert c.out["g9_n"] == 7 and c.out["g9_est"] == pytest.approx(np.mean([1 + i for i in range(7)]))   # fm ≤ 6
    assert c.out["post0703_n"] == 4 and c.out["post0703_est"] == pytest.approx(np.mean([1, 4, 6, 9]))


# ── W5 git 판정 실패 사유 ─────────────────────────────────────────────────
def test_w5_only_not_a_repository_counts_as_outside(tmp_path):
    def run_with(rc, err):
        return lambda cmd: subprocess.CompletedProcess(cmd, rc, "", err)
    assert RUN.ensure_outside_git(tmp_path, "t", run_with(128, "fatal: not a git repository (or any…)")) == tmp_path
    with pytest.raises(SystemExit):
        RUN.ensure_outside_git(tmp_path, "t", run_with(128, "fatal: detected dubious ownership in repository"))
    with pytest.raises(SystemExit):
        RUN.ensure_outside_git(tmp_path, "t", run_with(0, ""))
