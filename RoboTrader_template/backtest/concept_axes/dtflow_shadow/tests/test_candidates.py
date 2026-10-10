import numpy as np
import pandas as pd

from backtest.concept_axes.dtflow_shadow import candidates as C


def _df(closes, highs=None, vols=None, opens=None):
    n = len(closes)
    return pd.DataFrame({"date": pd.date_range("2026-08-01", periods=n), "open": opens or [c * 0.99 for c in closes],
                         "high": highs or closes, "low": closes, "close": closes, "volume": vols or [1000.0] * n})


def test_sql_keeps_adj_factor_on_one_line():
    for sql in (C.UNIVERSE_SQL, C.DAILY_SQL):
        assert any("volume * COALESCE(adj_factor, 1)" in line for line in sql.splitlines())


def test_base_filter_live_rules():
    rows = [("1", 4.9e11, 2e9), ("2", 5e11, 2e9), ("3", 0.0, 2e9), ("4", 1e11, 9.9e8)]
    assert [r[0] for r in C.base_filter(rows)] == ["1"]


def test_match_breakout_volume_bullish():
    closes = [100.0] * 30 + [110.0]
    vols = [1000.0] * 30 + [2500.0]
    s = C.match(_df(closes, vols=vols))
    assert s is not None and abs(s - 2.5) < 1e-12


def test_match_rejects_short_window_no_volume_or_bearish():
    assert C.match(_df([100.0] * 16)) is None
    assert C.match(_df([100.0] * 30 + [110.0], vols=[1000.0] * 30 + [1500.0])) is None
    closes = [100.0] * 30 + [110.0]
    assert C.match(_df(closes, vols=[1000.0] * 30 + [2500.0], opens=[99.0] * 30 + [111.0])) is None


def test_impossible_drop():
    assert C.impossible(_df([100.0, 60.0, 61.0]))
    assert not C.impossible(_df([100.0, 70.0, 71.0]))


def test_rank_stable_desc():
    r = C.rank([("a", 2.0), ("b", 3.0), ("c", 2.0)])
    assert [(x.stock_code, x.rank) for x in r] == [("b", 1), ("a", 2), ("c", 3)]


def test_compare_exact_and_mismatch():
    mine = C.rank([("a", 3.0), ("b", 2.0)])
    assert C.compare(mine, [("a", 1, 3.0), ("b", 2, 2.0)])["match"]
    m = C.compare(mine, [("a", 1, 3.0)])
    assert not m["match"] and m["only_mine"] == ["b"]
    assert not C.compare(mine, [("a", 1, 3.0), ("b", 2, 2.1)])["match"]


# --- Fix round 1: d_complete / prev_trading_day / compute / load_snapshot 가짜 커서 테스트 ---
from datetime import date as _date, timedelta as _td


class FakeCur:
    """SQL 본문으로 응답을 고른다. kospi=직전 거래일(KOSPI 행), counts={iso날짜: 시총 행수},
    universe=유니버스 날짜, daily={종목: 일봉 행(DESC)}, uni=유니버스 행, snap=스냅샷 행."""

    def __init__(self, kospi=None, counts=None, universe=None, daily=None, uni=None, snap=None):
        self.kospi, self.counts, self.universe = kospi, counts or {}, universe
        self.daily, self.uni, self.snap = daily or {}, uni or [], snap or []
        self.calls = []
        self._res = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "stock_code = 'KOSPI'" in sql:
            self._res = [(self.kospi,)]
        elif sql == C.UNIVERSE_DATE_SQL:
            self._res = [(self.universe,)]
        elif sql == C.UNIVERSE_SQL:
            self._res = self.uni
        elif sql == C.DAILY_SQL:
            self._res = self.daily.get(params[0], [])
        elif sql == C.SNAPSHOT_SQL:
            self._res = self.snap
        elif sql.startswith("SELECT count(*) FROM daily_prices WHERE date = %s"):
            self._res = [(self.counts.get(params[0], 0),)]
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._res[0]

    def fetchall(self):
        return self._res


D = _date(2026, 10, 12)
DP = _date(2026, 10, 8)


def _counts(n_d, n_p):
    return {D.isoformat(): n_d, DP.isoformat(): n_p}


def test_d_complete_ratio():
    ok, info = C.d_complete(FakeCur(kospi=DP.isoformat(), counts=_counts(980, 1000), universe=D.isoformat()), D)
    assert ok is True
    assert info == {"d_rows": 980, "dprev_rows": 1000, "universe_date": D.isoformat()}
    ok, info = C.d_complete(FakeCur(kospi=DP.isoformat(), counts=_counts(979, 1000), universe=D.isoformat()), D)
    assert ok is False
    assert info["d_rows"] == 979 and info["dprev_rows"] == 1000


def test_d_complete_prev_day_missing_no_exception():
    ok, info = C.d_complete(FakeCur(kospi=None, counts=_counts(1000, 1000), universe=D.isoformat()), D)
    assert ok is False
    assert info["dprev_rows"] == 0 and info["d_rows"] == 1000


def test_d_complete_stale_universe_not_ok():
    cur = FakeCur(kospi=DP.isoformat(), counts=_counts(1000, 1000), universe=DP.isoformat())
    ok, info = C.d_complete(cur, D)
    assert ok is False
    assert info["universe_date"] == DP.isoformat()


def test_d_complete_holiday_zero_rows_not_ok():
    ok, info = C.d_complete(FakeCur(kospi=DP.isoformat(), counts=_counts(0, 1000), universe=DP.isoformat()), D)
    assert ok is False
    assert info["d_rows"] == 0


def test_prev_trading_day_strictly_before_T():
    # 금요일 휴장 뒤 월요일 T: SQL 은 `date < T` 로 직전 거래일(목) 을 고른다
    cur = FakeCur(kospi="2026-10-08")
    T = _date(2026, 10, 12)
    assert C.prev_trading_day(cur, T) == _date(2026, 10, 8)
    sql, params = cur.calls[0]
    assert "date < %s" in sql and params == ("2026-10-12",)
    assert C.prev_trading_day(FakeCur(kospi=None), T) is None


def test_load_snapshot_params_and_shape():
    cur = FakeCur(snap=[("000001", 1, 2.5), ("000002", 2, None)])
    out = C.load_snapshot(cur, D)
    assert out[0] == ("000001", 1, 2.5)
    assert out[1][0] == "000002" and out[1][1] == 2 and out[1][2] != out[1][2]  # NaN
    assert cur.calls[0][1] == (C.S.FOLDER, D, C.S.PARAMS_HASH)


def test_compute_breakout_one_candidate():
    # 31봉: 직전 30봉 종가·고가 100·거래량 1000, 마지막 봉 양봉 돌파(110·고가110·거래량 2500)
    n = 31
    dates = [_date(2026, 8, 1) + _td(days=i) for i in range(n)]
    asc = [(d, 99.0, 100.0, 99.0, 100.0, 1000.0) for d in dates[:-1]]
    asc.append((dates[-1], 105.0, 110.0, 105.0, 110.0, 2500.0))
    desc = list(reversed(asc))
    uni = [("000001", 1e11, 2e9)]
    cur = FakeCur(universe=D.isoformat(), uni=uni, daily={"000001": desc})
    out = C.compute(cur, dates[-1])
    assert [(c.stock_code, c.rank) for c in out] == [("000001", 1)]
    assert abs(out[0].score - 2.5) < 1e-9
