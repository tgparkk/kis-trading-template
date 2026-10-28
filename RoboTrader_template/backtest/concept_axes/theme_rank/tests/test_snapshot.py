from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

from backtest.concept_axes.theme_rank import snapshot as SN

M = {1: frozenset({"000001", "000002", "000003"}), 2: frozenset({"000001", "000004"}), 3: frozenset({"000005"})}
SNAP = SN.Snapshot(date(2026, 10, 8), {1: "큰테마", 2: "작은테마", 3: "외톨이"}, M)


def test_norm_code_pads_and_strips():
    assert SN.norm_code(5930) == "005930"
    assert SN.norm_code(" 5930 ") == "005930"
    assert SN.norm_code("005930") == "005930"


def test_invert_maps_code_to_themes():
    inv = SN.invert(M)
    assert inv["000001"] == frozenset({1, 2})
    assert inv["000005"] == frozenset({3})


def test_pick_snap_date_latest_on_or_before():
    av = [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 8)]
    assert SN.pick_snap_date(av, date(2026, 10, 7)) == date(2026, 10, 6)
    assert SN.pick_snap_date(av, date(2026, 10, 8)) == date(2026, 10, 8)
    assert SN.pick_snap_date(av, date(2026, 10, 4)) is None


def test_theme_columns_prefers_most_shared_then_smaller_theme():
    cols = SN.theme_columns(["000001", "000002", "000004"], SNAP)
    # 000001: 테마1 공유 {000002}=1 · 테마2 공유 {000004}=1 → 동점 → 작은 테마(2 · 크기 2)
    assert cols["000001"] == {"theme": "작은테마", "size": 2, "shared": 1}
    assert cols["000002"] == {"theme": "큰테마", "size": 3, "shared": 1}


def test_theme_columns_zero_shared_falls_back_to_smallest_theme_and_unthemed_is_dash():
    cols = SN.theme_columns(["5", "999999"], SNAP)          # "5" → "000005"
    assert cols["000005"] == {"theme": "외톨이", "size": 1, "shared": 0}
    assert cols["999999"] == {"theme": "-", "size": None, "shared": 0}


class _Cur:
    def __init__(self):
        self._sql = ""
        self.calls = []

    def execute(self, sql, args=None):
        self._sql = sql
        self.calls.append((sql, args))

    def fetchall(self):
        if "FROM theme_daily WHERE" in self._sql:
            return [(1, "큰테마")]
        if "FROM theme_member_daily" in self._sql:
            return [(1, "5930"), (1, "000660")]
        return [(date(2026, 10, 5),), (date(2026, 10, 8),)]


class _Conn:
    def __init__(self):
        self.c = _Cur()

    def cursor(self):
        return self.c


def test_load_snapshot_normalizes_codes_and_dates_list():
    s = SN.load_snapshot(_Conn(), date(2026, 10, 8))
    assert s.members[1] == frozenset({"005930", "000660"})
    assert s.theme_name == {1: "큰테마"}
    assert SN.load_snap_dates(_Conn()) == [date(2026, 10, 5), date(2026, 10, 8)]


def test_load_snapshot_run_id_filters_both_tables():
    plain, pinned = _Conn(), _Conn()
    SN.load_snapshot(plain, date(2026, 10, 8))
    SN.load_snapshot(pinned, date(2026, 10, 8), 4)
    assert [a for _, a in plain.c.calls] == [(date(2026, 10, 8),)] * 2
    assert all("run_id" not in s for s, _ in plain.c.calls)
    assert [a for _, a in pinned.c.calls] == [(date(2026, 10, 8), 4)] * 2
    assert all(s.endswith("WHERE snap_date = %s AND run_id = %s") for s, _ in pinned.c.calls)


def test_snapshot_module_loads_standalone_by_path():
    """EOD 스크립트는 다른 워크트리 sys.path 에서 이 파일 하나만 경로로 읽는다 — 패키지 import 없이 돌아야 한다."""
    path = Path(SN.__file__)
    spec = importlib.util.spec_from_file_location("theme_snapshot_standalone", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["theme_snapshot_standalone"] = mod
    spec.loader.exec_module(mod)
    assert mod.theme_columns(["000004"], mod.Snapshot(date(2026, 10, 8), {2: "작은테마"},
                                                      {2: frozenset({"000001", "000004"})}))["000004"]["size"] == 2
