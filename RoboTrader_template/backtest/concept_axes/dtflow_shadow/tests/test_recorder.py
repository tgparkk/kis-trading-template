import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from backtest.concept_axes.dtflow_shadow import candidates as C
from backtest.concept_axes.dtflow_shadow import kis as K
from backtest.concept_axes.dtflow_shadow import store as ST

RT = Path(__file__).resolve().parents[4]


def load_runner():
    spec = importlib.util.spec_from_file_location("dtflow_runner", RT / "scripts" / "dtflow_shadow_recorder.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeKis:
    def __init__(self, expire=False):
        self.calls, self.expire = 0, expire

    def get(self, kind, params):
        self.calls += 1
        if self.expire:
            raise K.TokenUnavailable("x")
        return {"rt_cd": "0", "output": [], "output2": []}, "2026-10-12T07:52:01"


def _ctx(R, now, kis=None, complete=True, uni_date="2026-10-08"):
    store = ST.MemoryStore()
    alerts = []
    ctx = R.Ctx(T=date(2026, 10, 12), now_fn=lambda: now, store=store, inputs_cur=None,
                kis_factory=lambda: kis or FakeKis(), code_sha="sha", archive=None, log=lambda *a: None,
                alerts=alerts, k=None, dry_run=True)
    R._prev_day = lambda cur, T: date(2026, 10, 8)
    R._d_complete = lambda cur, D: (complete and uni_date == "2026-10-08",
                                    {"d_rows": 2700, "dprev_rows": 2700, "universe_date": uni_date})
    R._compute = lambda cur, D: [C.Cand("000001", 2.5, 1), C.Cand("000002", 2.1, 2)]
    R._cal = lambda cur, D: [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 7), D]
    R._scan_days_desc = lambda cur, D: [D]
    return ctx


def test_record_ok_writes_trial_rows():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    assert R.run_record(ctx) == "ok"
    assert len(ctx.store.cands("trial", date(2026, 10, 8))) == 2
    assert ctx.store.runs("trial")[0]["n_calls"] == 8


def test_record_refuses_after_0838():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 8, 39))
    assert R.run_record(ctx) == "missed_host" and ctx.alerts


def test_record_universe_stale():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52), uni_date="2026-10-07")
    assert R.run_record(ctx) == "universe_stale" and not ctx.store.cands("trial", date(2026, 10, 8))


def test_record_missed_token_no_rows():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52), kis=FakeKis(expire=True))
    assert R.run_record(ctx) == "missed_token" and not ctx.store.cands("trial", date(2026, 10, 8))


@pytest.mark.parametrize("exc", [PermissionError("locked"), UnicodeDecodeError("utf-8", b"x", 0, 1, "bad"),
                                 FileNotFoundError("gone")])
def test_record_token_read_os_errors_are_missed_token(exc):
    R = load_runner()

    def boom():
        raise exc
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    ctx.kis_factory = boom
    assert R.run_record(ctx) == "missed_token" and not ctx.store.cands("trial", date(2026, 10, 8))
    assert ctx.alerts


def test_record_late_marks_rows():
    R = load_runner()
    times = iter([datetime(2026, 10, 12, 8, 37), datetime(2026, 10, 12, 8, 41)] + [datetime(2026, 10, 12, 8, 41)] * 50)
    ctx = _ctx(R, None)
    ctx.now_fn = lambda: next(times)
    assert R.run_record(ctx) == "late"
    assert all(r["late"] for r in ctx.store.cands("trial", date(2026, 10, 8)))


def test_snapshot_check_records_match():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    R.run_record(ctx)
    ctx.now_fn = lambda: datetime(2026, 10, 12, 9, 5)
    R._load_snapshot = lambda cur, D: [("000001", 1, 2.5), ("000002", 2, 2.1)]
    assert R.run_snapshot(ctx) == "ok"
    snap = [r for r in ctx.store.runs("trial") if r["run_kind"] == "snapshot_check"][0]
    assert snap["snapshot_match"] is True


def test_record_vintage2_refetches_prev_day():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    prevD = date(2026, 10, 7)
    prev = {c: None for c in ST.CAND_COLS}
    prev.update(rule_v="v1", scan_date=prevD, stock_code="000009", rank=1, score=2.0, code_sha="x", late=False,
                row_sha="r")
    run = {c: None for c in ST.RUN_COLS}
    run.update(rule_v="v1", scan_date=prevD, run_kind="record", run_at="2026-10-08T07:52:00", status="ok", code_sha="x")
    ctx.store.write_day("trial", [prev], [], run)
    R._scan_days_desc = lambda cur, D: [D, prevD]
    assert R.run_record(ctx) == "ok"
    raws = ctx.store.t["dtflow_shadow.trial_raw"]
    assert sum(1 for r in raws if r["vintage"] == 2 and r["scan_date"] == prevD) == 4
    assert sum(1 for r in raws if r["vintage"] == 1) == 8          # 오늘 기록은 그대로


def test_cli_rejects_dev_flags_without_dry_run():
    R = load_runner()
    with pytest.raises(SystemExit):
        R.main(["--record", "--date", "2026-10-12"])
