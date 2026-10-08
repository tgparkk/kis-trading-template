"""run.main() 합성 스모크(R14) — DB·git·실제 결과 없이 끝까지 돌아 RESULTS.md 를 쓰는지만 본다(판정 값은 보지 않는다)."""
from __future__ import annotations

import json
import subprocess

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.candidate_ledger import run as CL
from backtest.concept_axes.theme_rank import build_arena as BA
from backtest.concept_axes.theme_rank import build_signals as BS
from backtest.concept_axes.theme_rank import run as RN
from backtest.concept_axes.theme_rank import signal as SG
from backtest.concept_axes.theme_rank import snapshot as SN

CODES = [f"{i:06d}" for i in range(1, 25)]
MEMBERS = {t: frozenset(CODES[3 * (t - 1):3 * (t - 1) + 6]) for t in range(1, 8)}     # 겹치는 테마 7개


class _Conn:
    def close(self):
        pass


def _setup(tmp_path, monkeypatch):
    rng = np.random.default_rng(7)
    days = [d.date() for d in pd.bdate_range("2025-06-02", periods=40)]              # 창 E·C 모두 걸친다
    ds = [d.isoformat() for d in days]
    excess = {d: {c: float(rng.normal(0.0, 0.05)) for c in CODES} for d in days}
    states = {d: SG.day_state(e) for d, e in excess.items()}
    keys, arena = [], []
    for i in range(32):
        for r, c in enumerate(sorted(rng.choice(CODES, 8, replace=False)), 1):
            keys.append((days[i], str(c)))
            arena.append(dict(scan_date=ds[i], stock_code=str(c), rank=r, fill="open", entry_date=ds[i + 1],
                              exit_date=ds[i + 3], exit_reason="tp" if r % 2 else "time",
                              ret_net=float(rng.normal(0.0, 3.0))))
    inp = BS.Inputs(states=states, excess=excess, raw_r=excess, themes_of=SN.invert(MEMBERS), members=MEMBERS,
                    themes_of_full=SN.invert(MEMBERS), members_full=MEMBERS,
                    day_codes={d: frozenset(c for k, c in keys if k == d) for d in days},
                    streak_of=BS.streak_table(sorted(MEMBERS), MEMBERS, states, days))
    sig = pd.DataFrame(BS.compute_rows(keys, inp), columns=BS.SIG_COLS)
    files = {"arena.csv": tmp_path / "arena.csv", "signals.csv": tmp_path / "signals.csv",
             "calib.json": tmp_path / "calib.json"}
    pd.DataFrame(arena).reindex(columns=BA.ARENA_COLS, fill_value="").to_csv(
        files["arena.csv"], index=False, lineterminator="\n")
    sig.to_csv(files["signals.csv"], index=False, lineterminator="\n")
    BA.write_lf(files["calib.json"], json.dumps({"mode": "hac", "lag": 11, "n_cut": 547,
                                                 "arena_md5": BA.md5(files["arena.csv"])}))
    BA.write_lf(tmp_path / "signals_meta.json", json.dumps({"n_cut": 547}))
    ledger = tmp_path / "ledger.csv"
    pd.DataFrame({"scan_date": ds}).to_csv(ledger, index=False, lineterminator="\n")

    git = {"status": "", "rev-parse": "0123456789abcdef0123456789abcdef01234567\n"}
    monkeypatch.setattr(RN, "guard", lambda *a, **k: None)
    monkeypatch.setattr(RN, "_git", lambda *a: subprocess.CompletedProcess(a, 0, git[a[0]], ""))
    monkeypatch.setattr(RN, "N_CUT", 547)
    monkeypatch.setattr(RN, "N_PLACEBO", 3)
    monkeypatch.setattr(RN, "FILES", files)
    monkeypatch.setattr(RN, "PREREG", tmp_path / "PREREG.md")
    monkeypatch.setattr(BA, "OUT", tmp_path)
    monkeypatch.setattr(BA, "LEDGER_CSV", ledger)
    monkeypatch.setattr(BA, "LEDGER_MD5", BA.md5(ledger))
    monkeypatch.setattr(CL, "_connect", lambda: _Conn())
    monkeypatch.setattr(SN, "load_snapshot", lambda conn, d, run_id=None: SN.Snapshot(
        d, {t: f"합성테마{t}" for t in MEMBERS}, MEMBERS))
    monkeypatch.setattr(BS, "load_day_states", lambda conn: (states, excess, excess, days))
    return files


def test_main_writes_results(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert RN.main() == 0
    text = (tmp_path / "RESULTS.md").read_bytes().decode("utf-8")
    assert "## 판정:" in text and "dirty=no" in text and "\r" not in text


def test_main_refuses_when_db_s_differs_from_frozen_signals(tmp_path, monkeypatch):
    files = _setup(tmp_path, monkeypatch)
    sig = pd.read_csv(files["signals.csv"], dtype={"stock_code": str, "scan_date": str})
    sig.loc[0, "s"] = float(sig.loc[0, "s"]) + 1e-9
    sig.to_csv(files["signals.csv"], index=False, lineterminator="\n")
    with pytest.raises(SystemExit, match="DB 상태가 동결 신호와 다르다"):
        RN.main()
    assert not (tmp_path / "RESULTS.md").exists()


def test_main_refuses_when_calib_arena_md5_stale(tmp_path, monkeypatch):
    files = _setup(tmp_path, monkeypatch)
    BA.write_lf(files["calib.json"], json.dumps({"mode": "hac", "lag": 11, "n_cut": 547, "arena_md5": "0" * 32}))
    with pytest.raises(SystemExit, match="arena_md5"):
        RN.main()
