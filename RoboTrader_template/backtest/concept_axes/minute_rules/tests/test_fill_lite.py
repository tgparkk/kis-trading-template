"""fill_lite(E1-lite) — 체결 시각 → 분 행 · 모델가 a·b · 오차 부호 · 호가표 시대(10-19) · 시각대 나눔(합성 자료만)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from backtest.concept_axes.minute_rules import engine as E
from backtest.concept_axes.minute_rules import fill_lite as F

from .synth import flat, put

KST = timezone(timedelta(hours=9))


def test_minute_index_from_fill_time_and_tz():
    assert F.minute_idx(datetime(2026, 10, 20, 9, 0, 59, tzinfo=KST)) == 0
    assert F.minute_idx(datetime(2026, 10, 20, 9, 5, 0, tzinfo=KST)) == 5
    assert F.minute_idx(datetime(2026, 10, 20, 0, 5, 0, tzinfo=timezone.utc)) == 5          # UTC 00:05 = KST 09:05
    assert F.minute_idx(datetime(2026, 10, 20, 9, 5, 0)) == 5                                # naive = KST
    assert F.minute_idx(datetime(2026, 10, 20, 15, 20, 0, tzinfo=KST)) is None
    assert F.minute_idx(datetime(2026, 10, 20, 8, 59, 59, tzinfo=KST)) is None


def test_buckets_and_tick_era_cut():
    assert [F.bucket_of(i) for i in (0, 4, 5, 9, 10, 379)] == ["0900_0905"] * 2 + ["0905_0910"] * 2 + ["0910_"] * 2
    assert F.tick_era(datetime(2026, 10, 16).date()) == "pre1019"
    assert F.tick_era(datetime(2026, 10, 19).date()) == "post1019"


def test_reproduce_models_errors_and_range():
    b = flat(10000.0)
    put(b, 7, 10000, 10100, 9900, 10055)                   # 09:07 종가 10,055 → 반올림 10,060(호가 10)
    put(b, 8, 10200, 10200, 10200, 10200)
    r = F.reproduce(F.Fill("paper", "000001", datetime(2026, 10, 20, 9, 7, 31, tzinfo=KST), 10050.0), b)
    assert r["excl"] == "" and r["minute_idx"] == 7 and r["bucket"] == "0905_0910" and r["tick_era"] == "post1019"
    assert r["close_raw"] == 10055 and r["px_a"] == 10060 and r["px_b"] == 10200
    assert r["err_a"] == pytest.approx((10060 / 10050 - 1) * 100) and r["err_b"] > 0 and r["in_range"]
    far = F.Fill("real", "000001", datetime(2026, 10, 20, 9, 7, tzinfo=KST), 12000.0)
    assert F.reproduce(far, b)["in_range"] is False


def test_reproduce_exclusions():
    t = datetime(2026, 10, 20, 9, 30, tzinfo=KST)
    assert F.reproduce(F.Fill("paper", "x", t, 1.0), None)["excl"] == "no_minute_data"
    assert F.reproduce(F.Fill("paper", "x", t.replace(hour=15, minute=25), 1.0), flat())["excl"] == "off_session"
    nb = np.full((E.N_SLOTS, E.N_FIELDS), np.nan)
    assert F.reproduce(F.Fill("paper", "x", t, 1.0), nb)["excl"] == "no_price_at_minute"
    last = F.reproduce(F.Fill("paper", "x", t.replace(hour=15, minute=19), 10000.0), flat())
    assert last["px_b"] is None and last["err_b"] is None                 # 15:19 → 다음 분 없음


def test_summarize_groups_by_source_era_bucket():
    b = flat(10000.0)
    fills = [F.Fill("paper", "a", datetime(2026, 10, 16, 9, 2, tzinfo=KST), 10000.0),
             F.Fill("paper", "a", datetime(2026, 10, 16, 9, 3, tzinfo=KST), 9900.0),
             F.Fill("paper", "a", datetime(2026, 10, 20, 9, 30, tzinfo=KST), 10100.0),
             F.Fill("real", "a", datetime(2026, 10, 20, 9, 1, tzinfo=KST), 10000.0)]
    g = {x["strategy"]: x for x in F.summarize([F.reproduce(f, b) for f in fills])}
    assert set(g) == {"paper|pre1019|0900_0905", "paper|post1019|0910_", "real|post1019|0900_0905", "(전체)"}
    assert g["paper|pre1019|0900_0905"]["n"] == 2 and g["paper|pre1019|0900_0905"]["positive"] == 1
    assert g["(전체)"]["n"] == 4


def test_private_output_outside_repo(monkeypatch, tmp_path):
    monkeypatch.delenv(F.PRIVATE_ENV, raising=False)
    assert F.private_out() == F.PRIVATE_DEFAULT / "fill_lite.csv"
    monkeypatch.setenv(F.PRIVATE_ENV, str(tmp_path))
    assert F.private_out() == tmp_path / "fill_lite.csv"
    from pathlib import Path
    with pytest.raises(SystemExit):
        F.private_out(str(Path(F.__file__).resolve().parent / "results" / "fill_lite.csv"))
