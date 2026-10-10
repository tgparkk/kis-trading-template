import importlib.util
import sys
import types
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from backtest.concept_axes.dtflow_shadow import candidates as C
from backtest.concept_axes.dtflow_shadow import kis as K
from backtest.concept_axes.dtflow_shadow import store as ST

RT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _no_real_paths(monkeypatch, tmp_path):
    """안전망 — 어떤 테스트도 실제 홈·key.ini·토큰·아카이브를 건드리지 않는다."""
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_TOKEN", str(tmp_path / "no_token.json"))
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_ARCHIVE", str(tmp_path / "archive"))


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
    R._prev_day = lambda T: date(2026, 10, 8)
    R._d_complete = lambda cur, D, dprev: (complete and uni_date == "2026-10-08",
                                           {"d_rows": 2700, "dprev_rows": 2700, "universe_date": uni_date})
    R._compute = lambda cur, D: [C.Cand("000001", 2.5, 1), C.Cand("000002", 2.1, 2)]
    R._cal = lambda D: [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 7), D]
    R._scan_days_desc = lambda D: [D]
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
    R._scan_days_desc = lambda D: [D, prevD]
    assert R.run_record(ctx) == "ok"
    raws = ctx.store.t["dtflow_shadow.trial_raw"]
    assert sum(1 for r in raws if r["vintage"] == 2 and r["scan_date"] == prevD) == 4
    assert sum(1 for r in raws if r["vintage"] == 1) == 8          # 오늘 기록은 그대로


def test_cli_rejects_dev_flags_without_dry_run():
    R = load_runner()
    with pytest.raises(SystemExit):
        R.main(["--record", "--date", "2026-10-12"])


# ---- fix round 1 ----
import requests  # noqa: E402


class _BadKis:
    def __init__(self, exc=None, fail_all=False, fail_first=False):
        self.exc, self.fail_all, self.fail_first, self.calls = exc, fail_all, fail_first, 0

    def get(self, kind, params):
        self.calls += 1
        if self.exc is not None and self.calls == 3:
            raise self.exc
        bad = self.fail_all or (self.fail_first and self.calls == 1)
        return {"rt_cd": "1" if bad else "0", "msg_cd": "X", "output": [], "output2": []}, "2026-10-12T07:52:01"


def _err_rows(ctx):
    return [r for r in ctx.store.runs("trial") if r["status"] == "error"]


def test_network_error_is_error_not_missed_token():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52), kis=_BadKis(exc=requests.ConnectionError("secret-host")))
    assert R.run_record(ctx) == "error"
    rows = _err_rows(ctx)
    assert len(rows) == 1 and rows[0]["error_text"] == "ConnectionError"
    assert not ctx.store.cands("trial", date(2026, 10, 8)) and ctx.alerts


def test_d_none_persists_error_row():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    R._prev_day = lambda T: None
    assert R.run_record(ctx) == "error"
    assert len(_err_rows(ctx)) == 1 and ctx.alerts


def test_unexpected_exception_persists_error_row_and_propagates():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))

    def boom(cur, D):
        raise ValueError("bad data")
    R._compute = boom
    with pytest.raises(ValueError):
        R.run_record(ctx)
    rows = _err_rows(ctx)
    assert len(rows) == 1 and rows[0]["error_text"] == "ValueError"


def test_error_row_write_failure_does_not_mask_original():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    R._compute = lambda cur, D: (_ for _ in ()).throw(ValueError("orig"))

    def bad_write(phase, run):
        raise RuntimeError("db down")
    ctx.store.write_run = bad_write
    with pytest.raises(ValueError):
        R.run_record(ctx)


def test_all_calls_failed_is_error_no_rows():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52), kis=_BadKis(fail_all=True))
    assert R.run_record(ctx) == "error"
    assert not ctx.store.cands("trial", date(2026, 10, 8))
    assert _err_rows(ctx)[0]["error_text"] == "AllCallsFailed"


def test_one_failed_call_still_ok():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52), kis=_BadKis(fail_first=True))
    assert R.run_record(ctx) == "ok"
    assert ctx.store.runs("trial")[0]["n_fail"] == 1


def test_snapshot_before_0903_writes_nothing():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    R.run_record(ctx)
    n = len(ctx.store.runs("trial"))
    ctx.now_fn = lambda: datetime(2026, 10, 12, 9, 2)
    assert R.run_snapshot(ctx) == "too_early"
    assert len(ctx.store.runs("trial")) == n
    ctx.now_fn = lambda: datetime(2026, 10, 12, 9, 3)
    R._load_snapshot = lambda cur, D: [("000001", 1, 2.5), ("000002", 2, 2.1)]
    assert R.run_snapshot(ctx) == "ok"


def test_now_requires_dry_run():
    R = load_runner()
    with pytest.raises(SystemExit):
        R.main(["--record", "--now", "08:00"])


def _frozen_fake(R, monkeypatch, calls):
    def fake(repo, path=None):
        calls.append(path)
        return types.SimpleNamespace(code_sha="abcdef0123456789", credit_lag_k=None)
    monkeypatch.setattr(R.G, "write_frozen", fake)


def test_freeze_refused_when_sealed_row_exists(monkeypatch):
    R = load_runner()
    calls = []
    _frozen_fake(R, monkeypatch, calls)
    st = ST.MemoryStore()
    run = {c: None for c in ST.RUN_COLS}
    run.update(rule_v="v1", scan_date=date(2026, 10, 8), run_kind="record", run_at="2026-10-12T07:52:00",
               status="missed_token", code_sha="x")
    st.write_run("sealed", run)
    assert R.run_freeze(lambda: st) == 2 and calls == []


def test_freeze_proceeds_when_sealed_empty_or_tables_missing(monkeypatch):
    R = load_runner()
    calls = []
    _frozen_fake(R, monkeypatch, calls)
    assert R.run_freeze(lambda: ST.MemoryStore()) == 0

    class NoTable(Exception):
        pgcode = "42P01"

    class Missing:
        def runs(self, phase):
            raise NoTable("relation does not exist")
    assert R.run_freeze(lambda: Missing()) == 0 and len(calls) == 2


def test_freeze_other_db_error_propagates(monkeypatch):
    R = load_runner()
    _frozen_fake(R, monkeypatch, [])

    def down():
        raise ConnectionError("down")
    with pytest.raises(ConnectionError):
        R.run_freeze(down)


# ---- final fix: C1 · I1 · I3 · I4 · I6 · M1 · M4 ----
from backtest.concept_axes.dtflow_shadow import settings as S  # noqa: E402
from backtest.concept_axes.dtflow_shadow.lock import LockBusy  # noqa: E402

D8 = date(2026, 10, 8)
PAST = [D8 - timedelta(days=i) for i in range(1, 13)]          # 끝난 스캔일(합성 · 내림차순)


def _seed_trial_day(store, d, lag=3, n=2, match=True):
    cands = []
    for i in range(n):
        r = {c: None for c in ST.CAND_COLS}
        r.update(rule_v="v1", scan_date=d, stock_code=f"00009{i}", rank=i + 1, score=2.0, code_sha="x", late=False,
                 credit_lag=lag)
        r["row_sha"] = ST.row_sha(r, ST.CAND_COLS)
        cands.append(r)
    rec = {c: None for c in ST.RUN_COLS}
    rec.update(rule_v="v1", scan_date=d, run_kind="record", run_at=f"{d}T07:52:00", status="ok", code_sha="x",
               avail_investor=0.99, avail_program=0.99, avail_short=0.99)
    store.write_day("trial", cands, [], rec)
    snap = {c: None for c in ST.RUN_COLS}
    snap.update(rule_v="v1", scan_date=d, run_kind="snapshot_check", run_at=f"{d}T09:05:00", status="ok",
                code_sha="x", snapshot_match=match)
    store.write_run("trial", snap)


@pytest.mark.parametrize("n_done, phase", [(10, "sealed"), (9, "trial")])
def test_record_seals_after_ten_completed_trial_days(n_done, phase):
    """C1: 오늘 기록하는 D 가 아니라 «끝난» 10거래일로 판정 → 10일 통과면 그날 아침 기록이 봉인 표로."""
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    ctx.k = 3
    R._scan_days_desc = lambda D: [D] + PAST
    for d in PAST[:n_done]:
        _seed_trial_day(ctx.store, d)
    assert R.run_record(ctx) == "ok"
    other = "trial" if phase == "sealed" else "sealed"
    assert len(ctx.store.cands(phase, D8)) == 2 and not ctx.store.cands(other, D8)
    assert [r["scan_date"] for r in ctx.store.runs(phase) if r["run_kind"] == "record"].count(D8) == 1


def test_choose_k_uses_only_days_with_ok_trial_record():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    out = []
    ctx.log = out.append
    R._scan_days_desc = lambda D: [D] + PAST                    # D(오늘 아직 기록 전)·PAST[3:] 는 기록 없음
    for d in PAST[:3]:
        _seed_trial_day(ctx.store, d, lag=3)
    R.run_choose_k(ctx)
    row = [ln for ln in out if str(ln).startswith("k=3 ")][0]
    assert "최소 일 가용률 1.000" in row


def test_prev_day_and_cal_come_from_korean_calendar():
    """I1: D·cal = utils.korean_holidays 달력(KOSPI 의사티커 적재 상태와 무관) · 12-31 휴장."""
    R = load_runner()
    assert R._prev_day(date(2026, 10, 12)) == D8                 # 10-09 한글날 · 주말 건너뜀
    assert R._prev_day(date(2027, 1, 4)) == date(2026, 12, 30)   # 01-01 공휴일 · 12-31 KRX 휴장
    cal = R._cal(D8)
    assert cal[-1] == D8 and len(cal) == R.CAL_DAYS and cal == sorted(cal)
    assert date(2026, 10, 9) not in cal and date(2026, 9, 25) not in cal
    assert all(d.weekday() < 5 for d in cal)
    assert R._scan_days_desc(D8) == sorted(cal, reverse=True)


def test_runner_and_candidates_never_use_kospi_pseudo_ticker():
    src = (RT / "scripts" / "dtflow_shadow_recorder.py").read_text(encoding="utf-8")
    assert "'KOSPI'" not in src and "'KOSPI'" not in Path(C.__file__).read_text(encoding="utf-8")


def test_record_passes_calendar_dprev_to_d_complete():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    R._scan_days_desc = lambda D: [D] + PAST
    seen = []
    R._d_complete = lambda cur, D, dprev: (seen.append((D, dprev)) or True,
                                           {"d_rows": 1, "dprev_rows": 1, "universe_date": D.isoformat()})
    assert R.run_record(ctx) == "ok" and seen == [(D8, PAST[0])]


@pytest.mark.parametrize("phase, status", [("trial", "error"), ("trial", "ok"), ("sealed", "missed_token"),
                                           ("sealed", "late")])
def test_record_refuses_scan_date_already_recorded(phase, status):
    """I1: 그 scan_date 에 record run 행(단계·상태 무관)이 있으면 아무것도 쓰지 않고 경보."""
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    run = {c: None for c in ST.RUN_COLS}
    run.update(rule_v="v1", scan_date=D8, run_kind="record", run_at="2026-10-12T07:52:00", status=status, code_sha="x")
    ctx.store.write_run(phase, run)
    before = {k: [dict(r) for r in v] for k, v in ctx.store.t.items()}
    assert R.run_record(ctx) == "already_recorded"
    assert ctx.store.t == before and any("already_recorded" in a for a in ctx.alerts)


def test_record_other_day_record_does_not_block():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    _seed_trial_day(ctx.store, PAST[0])
    assert R.run_record(ctx) == "ok"


# ---- M1: run_snapshot ----
def test_snapshot_phase_follows_sealed_runs_not_sealed_cands():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 9, 5))
    run = {c: None for c in ST.RUN_COLS}
    run.update(rule_v="v1", scan_date=PAST[0], run_kind="record", run_at="2026-10-08T07:52:00", status="ok", code_sha="x")
    ctx.store.write_run("sealed", run)                           # 이미 봉인 중 · 오늘 D 는 놓친 날
    assert R.run_snapshot(ctx) == "no_record"
    assert [r["status"] for r in ctx.store.runs("sealed") if r["run_kind"] == "snapshot_check"] == ["no_record"]
    assert not ctx.store.runs("trial")


def test_snapshot_missing_is_no_snapshot():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    R.run_record(ctx)
    ctx.now_fn = lambda: datetime(2026, 10, 12, 9, 5)
    R._load_snapshot = lambda cur, D: []
    assert R.run_snapshot(ctx) == "no_snapshot"
    snap = [r for r in ctx.store.runs("trial") if r["run_kind"] == "snapshot_check"]
    assert len(snap) == 1 and snap[0]["status"] == "no_snapshot" and snap[0]["snapshot_match"] is None
    assert any("no_snapshot" in a for a in ctx.alerts)


def test_snapshot_exception_persists_error_row():
    R = load_runner()
    ctx = _ctx(R, datetime(2026, 10, 12, 7, 52))
    R.run_record(ctx)
    ctx.now_fn = lambda: datetime(2026, 10, 12, 9, 5)

    def boom(cur, D):
        raise ValueError("db says SECRET")
    R._load_snapshot = boom
    with pytest.raises(ValueError):
        R.run_snapshot(ctx)
    err = [r for r in ctx.store.runs("trial") if r["run_kind"] == "snapshot_check"]
    assert len(err) == 1 and err[0]["status"] == "error" and err[0]["error_text"] == "ValueError"
    assert err[0]["scan_date"] == D8


# ---- main: I3 · I4 · I6 · M4 ----
def _sent(monkeypatch, R):
    sent = []
    monkeypatch.setattr(R.AL, "send", lambda text, dry_run=False, **kw: sent.append((text, dry_run)) or True)
    return sent


def _log_text():
    d = S.log_dir()
    return "".join(p.read_text(encoding="utf-8") for p in sorted(d.glob("recorder_*.log"))) if d.exists() else ""


def test_main_guard_refusal_alerts_logs_exit2(monkeypatch, capsys):
    R = load_runner()
    sent = _sent(monkeypatch, R)
    assert R.main(["--record"]) == 2                              # 임시 홈에 frozen.json 없음
    assert sent and "guard_refused" in sent[0][0] and "frozen_missing" in sent[0][0]
    assert "guard_refused" in _log_text() and "frozen_missing" in _log_text()


def test_main_guard_unexpected_exception_alerts_logs_exit2(monkeypatch, capsys):
    R = load_runner()
    sent = _sent(monkeypatch, R)

    def bad(*a, **k):
        raise ValueError("pw=SECRET-123")
    monkeypatch.setattr(R.G, "load_frozen", bad)
    assert R.main(["--record"]) == 2
    out = capsys.readouterr()
    assert sent and "ValueError" in sent[0][0] and "SECRET" not in sent[0][0]
    assert "ValueError" in _log_text() and "SECRET" not in _log_text()
    assert "SECRET" not in out.out + out.err


def test_freeze_with_dry_run_is_rejected(monkeypatch):
    R = load_runner()
    called = []
    monkeypatch.setattr(R, "run_freeze", lambda *a, **k: called.append(1) or 0)
    with pytest.raises(SystemExit) as ei:
        R.main(["--freeze", "--dry-run"])
    assert ei.value.code == 2 and not called


def _dry_main_env(monkeypatch, R, store=None):
    def no(*a, **k):
        raise AssertionError("dry-run 이 실 토큰·key.ini·KIS 를 건드렸다")
    monkeypatch.setattr(R.K, "read_token", no)
    monkeypatch.setattr(R.K, "read_kis_conf", no)
    monkeypatch.setattr(R.K, "Client", no)
    monkeypatch.setattr(R.ST, "connect_writer", no)
    monkeypatch.setattr(R, "_open_inputs", lambda: object())
    st = store if store is not None else ST.MemoryStore()
    monkeypatch.setattr(R, "_open_store", lambda dry_run: st if dry_run else no())
    R._d_complete = lambda cur, D, dprev: (True, {"d_rows": 1, "dprev_rows": 1, "universe_date": D.isoformat()})
    R._compute = lambda cur, D: [C.Cand("000001", 2.5, 1), C.Cand("000002", 2.1, 2)]
    return st


DRY = ["--record", "--dry-run", "--no-guard", "--date", "2026-10-12", "--now", "07:52"]


def test_dry_run_uses_kis_stub_no_token_no_kis(monkeypatch, capsys, tmp_path):
    R = load_runner()
    sent = _sent(monkeypatch, R)
    st = _dry_main_env(monkeypatch, R)
    assert R.main(DRY + ["--home", str(tmp_path / "dryhome")]) == 0
    assert "status=ok" in capsys.readouterr().out
    run = [r for r in st.runs("trial") if r["run_kind"] == "record"][0]
    assert run["scan_date"] == D8 and run["n_calls"] == 8 and run["n_fail"] == 0
    assert all(r["msg_cd"] == "DRYRUN" for r in st.t["dtflow_shadow.trial_raw"])
    assert all(d for _, d in sent)                                # 경보도 dry-run(전송 0)


def test_open_store_dry_run_is_memory():
    R = load_runner()
    assert isinstance(R._open_store(True), ST.MemoryStore)


def test_main_already_recorded_exit2(monkeypatch, tmp_path):
    R = load_runner()
    _sent(monkeypatch, R)
    st = ST.MemoryStore()
    run = {c: None for c in ST.RUN_COLS}
    run.update(rule_v="v1", scan_date=D8, run_kind="record", run_at="2026-10-12T07:52:00", status="error", code_sha="x")
    st.write_run("trial", run)
    _dry_main_env(monkeypatch, R, st)
    assert R.main(DRY + ["--home", str(tmp_path / "dryhome")]) == 2
    assert len(st.runs("trial")) == 1


def test_main_lockbusy_logged_exit3(monkeypatch, tmp_path):
    R = load_runner()
    _sent(monkeypatch, R)
    _dry_main_env(monkeypatch, R)

    def busy(self):
        raise LockBusy("held")
    monkeypatch.setattr(R.RunnerLock, "acquire", busy)
    home = tmp_path / "dryhome"
    assert R.main(DRY + ["--home", str(home)]) == 3
    logs = list((home / "logs").glob("recorder_*.log"))
    assert len(logs) == 1 and "LockBusy" in logs[0].read_text(encoding="utf-8")


def test_main_exception_exit_logged_type_only_one_alert(monkeypatch, capsys, tmp_path):
    R = load_runner()
    sent = _sent(monkeypatch, R)
    _dry_main_env(monkeypatch, R)

    def boom():
        raise RuntimeError("password=SECRET-xyz")
    monkeypatch.setattr(R, "_open_inputs", boom)
    home = tmp_path / "dryhome"
    assert R.main(DRY + ["--home", str(home)]) == 1
    out = capsys.readouterr()
    text = (home / "logs").glob("recorder_*.log").__next__().read_text(encoding="utf-8")
    assert "RuntimeError" in text and "SECRET" not in text
    assert "SECRET" not in out.out + out.err
    assert len(sent) == 1 and "RuntimeError" in sent[0][0] and "SECRET" not in sent[0][0]


def test_main_record_exception_sends_one_alert(monkeypatch, tmp_path):
    R = load_runner()
    sent = _sent(monkeypatch, R)
    _dry_main_env(monkeypatch, R)
    R._compute = lambda cur, D: (_ for _ in ()).throw(ValueError("x"))
    assert R.main(DRY + ["--home", str(tmp_path / "dryhome")]) == 1
    assert len(sent) == 1 and "status=error" in sent[0][0] and "ValueError" in sent[0][0]


def test_freeze_guard_refusal_prints_reason_not_message(monkeypatch, capsys):
    R = load_runner()

    def refuse(repo, path=None):
        raise R.G.GuardError("git status 실패: C:/secret/path", "git_failed")
    monkeypatch.setattr(R.G, "write_frozen", refuse)
    assert R.run_freeze(lambda: ST.MemoryStore()) == 2
    out = capsys.readouterr().out
    assert "git_failed" in out and "secret" not in out
