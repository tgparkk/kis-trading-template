# tests/test_pit_gating.py
"""PIT(point-in-time) 게이팅 순수함수 테스트.

신호캐시 {code: [bar_idx...]} 를 진입봉 날짜 기준으로 eligible_resolver 로 거르는
``pit_gate_signal_cache`` 와, 월별 scan_date 스냅샷 멤버십으로 PIT 판정하는
``make_scan_eligible_resolver`` 를 DB 없이(가짜 resolver/reader 주입) 단언한다.
"""
import pandas as pd

from backtest.screener_universe import (
    make_scan_eligible_resolver,
    pit_gate_signal_cache,
)


def _df(dates):
    """datetime 컬럼만 있으면 충분(게이팅은 iloc[bar_idx]['datetime'] 만 본다)."""
    return pd.DataFrame({
        "datetime": pd.to_datetime(dates),
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
    })


# ---------------------------------------------------------------------------
# pit_gate_signal_cache
# ---------------------------------------------------------------------------

def test_all_eligible_cache_unchanged():
    """모든 (code, bar) 가 eligible → 캐시 불변."""
    data = {
        "A": _df(["2021-01-04", "2021-01-05", "2021-01-06"]),
        "B": _df(["2021-01-04", "2021-01-05", "2021-01-06"]),
    }
    cache = {"A": [0, 2], "B": [1]}
    gated = pit_gate_signal_cache(cache, data, lambda code, d: True)
    assert gated == {"A": [0, 2], "B": [1]}


def test_partial_ineligible_removes_only_those_bars():
    """일부 (code, date) ineligible → 해당 bar 만 제거, 나머지 보존."""
    data = {
        "A": _df(["2021-01-04", "2021-01-05", "2021-01-06"]),
        "B": _df(["2021-01-04", "2021-01-05", "2021-01-06"]),
    }
    cache = {"A": [0, 1, 2], "B": [0, 2]}

    # B 의 2021-01-04(bar 0) 만 ineligible, 나머지 전부 eligible
    def resolver(code, d):
        ts = pd.Timestamp(d)
        if code == "B" and ts == pd.Timestamp("2021-01-04"):
            return False
        return True

    gated = pit_gate_signal_cache(cache, data, resolver)
    assert gated["A"] == [0, 1, 2]
    assert gated["B"] == [2]            # bar 0(01-04) 제거, bar 2(01-06) 보존


def test_empty_cache_and_empty_eligible():
    """빈 캐시 → 빈 결과. 전부 ineligible → 모든 종목 빈 리스트. 예외 없음."""
    assert pit_gate_signal_cache({}, {}, lambda c, d: True) == {}

    data = {"A": _df(["2021-01-04", "2021-01-05"])}
    cache = {"A": [0, 1]}
    gated = pit_gate_signal_cache(cache, data, lambda c, d: False)
    assert gated == {"A": []}


def test_bar_without_data_is_dropped_safely():
    """캐시에 종목이 있지만 data 에 없으면 그 종목은 안전히 빈 리스트(예외 없음)."""
    data = {"A": _df(["2021-01-04", "2021-01-05"])}
    cache = {"A": [0], "GHOST": [0, 1]}
    gated = pit_gate_signal_cache(cache, data, lambda c, d: True)
    assert gated["A"] == [0]
    assert gated["GHOST"] == []


# ---------------------------------------------------------------------------
# make_scan_eligible_resolver — 가장 최근 scan_date <= d 폴백
# ---------------------------------------------------------------------------

class _FakeReader:
    """get_universe_snapshot(scan_date) 만 제공. 날짜별 스냅샷을 dict 로 주입."""

    def __init__(self, snapshots):
        self._snapshots = snapshots          # {scan_date_str: [snapshot dict...]}
        self.calls = []

    def get_universe_snapshot(self, scan_date):
        key = scan_date if isinstance(scan_date, str) else scan_date.strftime("%Y-%m-%d")
        self.calls.append(key)
        return list(self._snapshots.get(key, []))


def _snap(*codes):
    # 전부 base_filter 통과하도록 소형+거래대금 충족으로 구성.
    return [
        {"stock_code": c, "market_cap": 3e11, "trading_value": 2e9} for c in codes
    ]


def test_resolver_uses_membership_of_exact_scan_date():
    """진입일이 scan_date 와 정확히 일치하면 그 날 통과집합으로 판정."""
    reader = _FakeReader({
        "2021-01-31": _snap("A", "B"),
        "2021-02-28": _snap("B", "C"),
    })
    resolver = make_scan_eligible_resolver(
        "daytrading_3methods_breakout", ["2021-01-31", "2021-02-28"], reader=reader
    )
    assert resolver("A", "2021-01-31") is True
    assert resolver("C", "2021-01-31") is False     # C 는 1월 집합에 없음
    assert resolver("C", "2021-02-28") is True


def test_resolver_most_recent_scan_date_fallback():
    """진입일이 scan_date 사이면 *직전* scan_date 집합으로 PIT 판정."""
    reader = _FakeReader({
        "2021-01-31": _snap("A", "B"),
        "2021-02-28": _snap("C"),
    })
    resolver = make_scan_eligible_resolver(
        "daytrading_3methods_breakout", ["2021-01-31", "2021-02-28"], reader=reader
    )
    # 2021-02-10 은 01-31 과 02-28 사이 → 직전(01-31) 집합 사용
    assert resolver("A", "2021-02-10") is True       # 01-31 집합에 있음
    assert resolver("C", "2021-02-10") is False      # C 는 02-28부터 → 02-10엔 미적격
    # 02-28 이후는 02-28 집합
    assert resolver("C", "2021-03-15") is True
    assert resolver("A", "2021-03-15") is False


def test_resolver_before_first_scan_date_is_ineligible():
    """첫 scan_date 이전 진입일 → 적용할 통과집합 없음 → 미적격."""
    reader = _FakeReader({"2021-01-31": _snap("A")})
    resolver = make_scan_eligible_resolver(
        "daytrading_3methods_breakout", ["2021-01-31"], reader=reader
    )
    assert resolver("A", "2020-12-15") is False


def test_resolver_caches_snapshot_per_date():
    """같은 scan_date 를 여러 번 조회해도 reader 는 날짜당 1회만 호출(캐시)."""
    reader = _FakeReader({"2021-01-31": _snap("A", "B")})
    resolver = make_scan_eligible_resolver(
        "daytrading_3methods_breakout", ["2021-01-31"], reader=reader
    )
    resolver("A", "2021-02-01")
    resolver("B", "2021-02-02")
    resolver("A", "2021-03-01")
    assert reader.calls.count("2021-01-31") == 1
