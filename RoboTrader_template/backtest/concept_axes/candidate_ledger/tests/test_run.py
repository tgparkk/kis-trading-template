"""PREREG §3~§7 단위 테스트 — 합성 데이터 · DB 없음."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.candidate_ledger import run as R
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.replayer import scan as SC


def _frame(code: str, n: int, end: str, drop_at: int = None) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=n)
    close = np.full(n, 10_000.0)
    if drop_at is not None:                       # 음수 인덱스 = 끝에서부터(−50% 불가능봉)
        close[drop_at:] = 5_000.0
    return pd.DataFrame({"stock_code": code, "date": dates, "open": close, "high": close, "low": close,
                         "close": close, "volume": 1_000.0})


def _book(*frames: pd.DataFrame) -> R.Book:
    px = pd.concat(frames, ignore_index=True)
    return R.build_book(px)


# ── §4 밴드 ────────────────────────────────────────────────────────────────
def test_band_ma20_inclusive():
    lo, hi = R.entry_band(10_000.0, 0.08, 0.01)
    assert lo == pytest.approx(9_200.0) and hi == pytest.approx(10_100.0)
    assert R.band_ok(lo, lo, hi) and R.band_ok(hi, lo, hi)            # 경계 포함
    assert not R.band_ok(lo - 0.01, lo, hi) and not R.band_ok(hi + 0.01, lo, hi)


def test_band_open_lower_side():
    lo, hi = R.entry_band(10_000.0, None, 0.03)
    assert lo is None and hi == pytest.approx(10_300.0)
    assert R.band_ok(1.0, lo, hi) and not R.band_ok(10_301.0, lo, hi)


# ── §3-6 절단 없음 ────────────────────────────────────────────────────────
def test_rank_no_truncation_and_ties():
    ms = [dict(stock_code=f"{i:06d}", score=float(i % 3)) for i in range(25)]
    out = R.rank_day(ms)
    assert len(out) == 25 and all(r["n_passed"] == 25 for r in out)
    assert [r["rank"] for r in out] == list(range(1, 26))
    top = [r for r in out if r["score"] == 2.0]
    assert [r["stock_code"] for r in top] == sorted(r["stock_code"] for r in top)   # 동점 = 코드 오름차순
    with pytest.raises(TypeError):                                                     # §3-6 금지 경로
        SC.rank_and_truncate([(m["stock_code"], m["score"]) for m in ms], None, True)


# ── §3-4·§3-5 minervini 2패스 · sanity_window ─────────────────────────────
class _StubAdapter:
    def __init__(self):
        self.frames = None
        self.calls = []

    def build_context(self, frames, scan_date):
        self.frames = sorted(frames)
        return {c: {"rs_value": 50.0 + i} for i, c in enumerate(sorted(frames))}

    def match(self, win, params, ctx):
        self.calls.append((win["stock_code"].iloc[0], dict(ctx)))
        if win["stock_code"].iloc[0] == "ERR001":
            raise ValueError("boom")
        return float(win["volume"].iloc[-1]), "ok"


def _two_pass_book():
    D = "2024-03-15"
    return D, _book(
        _frame("A00001", 300, D),                        # D 봉 있음
        _frame("B00001", 300, "2024-03-14"),             # D 봉 없음 → RS 컨텍스트엔 포함 · 행 없음
        _frame("C00001", 300, D, drop_at=-10),           # 최근 90봉 안 불가능봉 → 제외
        _frame("E00001", 300, D, drop_at=-150),          # 90봉 밖(260 창 안) 불가능봉 → sanity 90 이면 통과
        _frame("ERR001", 300, D),                        # match 예외 → 격리
    )


def test_minervini_two_pass_frames_and_rows():
    D, book = _two_pass_book()
    ad = _StubAdapter()
    elig = set(book) | {"Z99999"}                        # 데이터 없는 적격 종목
    rows, dg = R.scan_two_pass(ad, {}, book, elig, pd.Timestamp(D), 260, 90)
    assert ad.frames == ["A00001", "B00001", "E00001", "ERR001"]
    assert sorted(r["stock_code"] for r in rows) == ["A00001", "E00001"]
    assert all(r["rs_value"] is not None for r in rows)
    assert dict(ad.calls)["A00001"] == {"rs_value": 50.0}
    assert dg["n_impossible"] == 1 and dg["n_errors"] == 1 and dg["n_evaluated"] == 3
    assert dg["n_matched"] == 2 and dg["n_no_bar_at_d"] == len(elig) - 1 - 3
    assert all(r["n_bars"] == 260 for r in rows)


def test_sanity_window_none_guards_whole_window():
    D, book = _two_pass_book()
    ad = _StubAdapter()
    rows, dg = R.scan_two_pass(ad, {}, book, set(book), pd.Timestamp(D), 260, None)
    assert "E00001" not in ad.frames and dg["n_impossible"] == 2


# ── §5 qty 항등 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("price,qty,basis", [(204_000.0, 4, "amount"), (1_000_000.0, 1, "amount"),
                                             (1_078_000.0, 1, "one_share"), (333.0, 3003, "amount")])
def test_qty_identity(price, qty, basis):
    q = R.Z.arm_b_qty(price)
    assert (q.qty, q.basis) == (qty, basis)
    assert abs(q.qty * price - q.notional) <= 1


# ── §6 window_fn 룩어헤드 금지 ────────────────────────────────────────────
def test_window_fn_excludes_same_day_bar():
    book = _book(_frame("A00001", 200, "2024-03-15"))
    fn = R.make_window_fn(book)
    day = date(2024, 3, 15)
    data, _ = fn("A00001", day)
    assert data["date"].max() == pd.Timestamp("2024-03-14")
    assert data["date"].min() >= pd.Timestamp(day - timedelta(days=120))
    assert list(data.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert fn("NOPE00", day) == (None, {})


# ── 청산 경로 절단이 결과를 바꾸지 않는다 ─────────────────────────────────
def test_build_path_truncation_is_exact():
    cal = [date(2024, 1, 1) + timedelta(days=i) for i in range(40)]
    bars = {d: X.Bar(d, 100.0, 101.0, 99.0, 100.0) for d in cal if d != cal[5] and d != cal[10]}
    rules = X.ExitRules(tp=0.5, sl=0.5, max_hold_days=10)
    pos = X.Pos("A00001", cal[0], None, 100.0, 1, X.BASIS_D_OPEN)
    full = [(k, d, bars.get(d)) for k, d in enumerate(cal)]
    cut = R.build_path(cal, {d: i for i, d in enumerate(cal)}, bars, cal[0], 10)
    assert len(cut) == 12                                       # k=10 결측 → k=11 까지
    a = X.simulate_lot(pos, rules, full, lambda p, d: None)
    b = X.simulate_lot(pos, rules, cut, lambda p, d: None)
    assert (a.reason, a.exit_date, a.price, a.hold_days, a.flags) == (b.reason, b.exit_date, b.price,
                                                                        b.hold_days, b.flags)


# ── lot_row — 밴드 밖도 가상 로트 · no_next_day ───────────────────────────
def _env(book, cal):
    return R.Env(cal=cal, book=book, uni={}, excl={"A00001": "pref"}, imp_dates={}, corp_dates={},
                 bad_open=set(), minute_fn=lambda pairs: set())


def test_lot_row_band_out_is_simulated_and_no_next_day():
    f = _frame("A00001", 60, "2024-03-29")
    f.loc[f.index[-1], ["open", "high", "low", "close"]] = [11_000.0, 11_000.0, 11_000.0, 11_000.0]
    book = _book(f)
    cal = [pd.Timestamp(d).date() for d in f["date"]]
    env = _env(book, cal)
    strat = SimpleNamespace(_entry_band_down_pct=0.08, _entry_band_up_pct=0.01)
    rules = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=50)
    m = dict(stock_code="A00001", scan_date=pd.Timestamp(cal[-2]), score=1.0, reason="r", n_bars=60, rank=1,
             n_passed=1)
    row, err = R.lot_row(env, "book_pullback_ma20", m, strat, rules, lambda p, d: None, None, set())
    assert not err and list(row) == R.LEDGER_COLS
    assert row["band_ok"] == "False" and row["flags"].split(";")[0] == "band_out"
    assert row["qty"] == "90" and row["exit_reason"] == "open" and row["excl_class"] == "pref"
    assert "survivor_universe" in row["flags"] and "vintage_m4" in row["flags"]
    m2 = dict(m, scan_date=pd.Timestamp(cal[-1]))
    row2, _ = R.lot_row(env, "book_pullback_ma20", m2, strat, rules, lambda p, d: None, None, set())
    assert row2["flags"].startswith("no_next_day") and row2["qty"] == "" and row2["entry_date"] == ""


# ── 가드 ──────────────────────────────────────────────────────────────────
def test_guard_blobs_mismatch_stops():
    def fake(*args):
        return "aaa" if args[0] == "rev-parse" else ("bbb" if "base.py" in args[-1] else "aaa")
    with pytest.raises(SystemExit):
        R.guard_blobs(git=fake)
    assert len(R.guard_blobs(git=lambda *a: "same")) == len(R.GUARD_FILES)


def test_guard_rules_mismatch_stops():
    R.guard_rules("minervini_volume_dryup", X.ExitRules(0.12, 0.08, 20))
    with pytest.raises(SystemExit):
        R.guard_rules("minervini_volume_dryup", X.ExitRules(0.10, 0.08, 20))
    with pytest.raises(SystemExit):
        R.guard_rules("book_pullback_ma20", X.ExitRules(0.10, 0.08, 50),
                      SimpleNamespace(_entry_band_down_pct=None, _entry_band_up_pct=0.01))


# ── 체크포인트 이어 달리기 ────────────────────────────────────────────────
def test_checkpoint_resume(tmp_path):
    rows = [{k: "x" for k in R.LEDGER_COLS}]
    diag = [{k: "1" for k in R.DIAG_COLS}]
    days = [pd.Timestamp("2024-03-13"), pd.Timestamp("2024-03-29")]
    assert R.load_done_part(tmp_path, "s", "2024-03", "sha1", "fp1", days) is None
    R.save_part(tmp_path, "s", "2024-03", rows, diag,
                dict(git_sha="sha1", db_fingerprint="fp1", n_days=2, window=R.part_window(days)))
    got = R.load_done_part(tmp_path, "s", "2024-03", "sha1", "fp1", days)
    assert got[0] == rows and got[1] == diag
    for args in (("sha2", "fp1", days), ("sha1", "fp2", days), ("sha1", "fp1", days[:1]),
                 ("sha1", "fp1", [days[0], pd.Timestamp("2024-03-28")])):
        with pytest.raises(SystemExit):
            R.load_done_part(tmp_path, "s", "2024-03", *args)


# ── 창 끝 = D (D 이후 봉이 있어도) ─────────────────────────────────────────
class _LastDateAdapter:
    def __init__(self):
        self.last = []

    def base_filter(self, universe):
        return universe

    def build_context(self, frames, scan_date):
        self.last += [f["date"].iloc[-1] for f in frames.values()]
        return {}

    def match(self, win, params, ctx=None):
        self.last.append(win["date"].iloc[-1])
        return 1.0, "ok"


def test_scan_window_ends_at_d_despite_future_bars():
    D = pd.Timestamp("2024-03-15")
    px = pd.concat([_frame("A00001", 300, "2024-04-30"), _frame("B00001", 300, "2024-04-30")],
                   ignore_index=True)
    ad = _LastDateAdapter()
    rows, _ = R.scan_two_pass(ad, {}, R.build_book(px), {"A00001", "B00001"}, D, 260, 90)
    assert len(rows) == 2 and set(ad.last) == {D}
    ad2 = _LastDateAdapter()
    ms, _, _ = SC.scan_strategy(px, {D: {"A00001", "B00001"}}, ad2, {}, 90, scan_dates=[D], progress_every=0)
    assert len(ms) == 2 and set(ad2.last) == {D}


def test_window_fn_excludes_same_day_with_future_bars():
    fn = R.make_window_fn(_book(_frame("A00001", 200, "2024-04-30")))
    data, _ = fn("A00001", date(2024, 3, 15))
    assert data["date"].max() == pd.Timestamp("2024-03-14")


# ── --verify-only ──────────────────────────────────────────────────────────
def test_verify_only_rewrites_only_verify_section(tmp_path):
    base = {k: "" for k in R.LEDGER_COLS}
    rows = [dict(base, strategy="book_pullback_ma20", scan_date="2024-03-13", stock_code="000001", rank="1",
                 n_passed="1", entry_date="2024-03-14", entry_price="1000", band_lo="920", band_hi="1010",
                 band_ok="True", qty="1000", notional="1000000", exit_date="2024-03-15", exit_price="1100",
                 exit_reason="tp", hold_days="1", pnl_won="100000", flags="vintage_m4;survivor_universe")]
    diag = [dict({k: "0" for k in R.DIAG_COLS}, strategy="book_pullback_ma20", scan_date="2024-03-13",
                 n_matched="1")]
    R.write_csv(tmp_path / "ledger.csv", R.LEDGER_COLS, rows)
    R.write_csv(tmp_path / "scan_diag.csv", R.DIAG_COLS, diag)
    (tmp_path / "run_meta.json").write_text('{"strategies": ["book_pullback_ma20"]}', encoding="utf-8")
    (tmp_path / "summary.md").write_text("# head\n\n## 전략별\nkeep\n\n## §10 검증 (old)\nSTALE\n",
                                         encoding="utf-8")
    assert R.verify_only(tmp_path, conn_factory=lambda: pytest.fail("V1 창 밖인데 DB 접속")) == 0
    out = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert out.startswith("# head") and "keep" in out and "STALE" not in out
    assert "Σn_passed 1 · Σn_matched 1 · 불일치 날짜 0" in out and "band_ok 재계산 불일치 0" in out
