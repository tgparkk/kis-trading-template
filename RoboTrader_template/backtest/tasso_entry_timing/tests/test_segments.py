import pandas as pd
from lab.segments import find_segments


def _frame(rows):
    return pd.DataFrame(rows, columns=["stock_code", "date", "open", "high", "low", "close", "volume"])


_RALLY = [
    ["A", "2026-01-02", 100, 105, 95, 100, 1000],
    ["A", "2026-01-05", 100, 104, 90, 96, 1000],   # 최저 90
    ["A", "2026-01-06", 96, 150, 96, 148, 9000],   # 급등봉 (시가 96, 직전봉 종가 96)
    ["A", "2026-01-07", 148, 200, 145, 195, 5000], # 최고 200 — 오늘이 창 최고
]


def test_low_variant_uses_the_lowest_low_as_start():
    segs = find_segments(_frame(_RALLY), variant="low", lookback=3, min_gain=0.30)
    assert len(segs) == 1
    assert segs[0].start_px == 90
    assert segs[0].peak_px == 200


def test_surge_open_variant_starts_at_the_surge_bar_open():
    segs = find_segments(_frame(_RALLY), variant="surge_open", lookback=3, min_gain=0.30)
    assert segs[0].start_px == 96


def test_prev_close_variant_starts_at_the_bar_before_the_surge():
    segs = find_segments(_frame(_RALLY), variant="prev_close", lookback=3, min_gain=0.30)
    assert segs[0].start_px == 96


def test_segment_is_dropped_when_gain_below_activation():
    df = _frame([
        ["A", "2026-01-02", 100, 105, 95, 100, 1000],
        ["A", "2026-01-05", 100, 110, 99, 108, 3000],
        ["A", "2026-01-06", 108, 112, 107, 110, 3000],
    ])
    assert find_segments(df, variant="low", lookback=2, min_gain=0.30) == []


def test_no_segment_emitted_on_a_day_that_is_not_a_window_high():
    """구간은 '새 고점을 찍은 날'에만 발생한다 — 하락 중에는 안 생긴다."""
    rows = _RALLY + [["A", "2026-01-08", 195, 196, 180, 182, 4000]]
    segs = find_segments(_frame(rows), variant="low", lookback=3, min_gain=0.30)
    assert all(s.peak_date != "2026-01-08" for s in segs)


def test_many_segments_across_a_long_history():
    """종목당 1건만 나오면 5.6년 백테스트 표본이 붕괴한다."""
    rows = []
    for cycle in range(5):
        base = 100 + cycle
        rows += [
            ["A", f"2026-{cycle+1:02d}-02", base, base + 5, base - 5, base, 1000],
            ["A", f"2026-{cycle+1:02d}-05", base, base + 4, base - 10, base - 4, 1000],
            ["A", f"2026-{cycle+1:02d}-06", base - 4, base + 50, base - 4, base + 48, 9000],
            ["A", f"2026-{cycle+1:02d}-07", base + 48, base + 100, base + 45, base + 95, 5000],
        ]
    segs = find_segments(_frame(rows), variant="low", lookback=3, min_gain=0.30)
    assert len(segs) >= 4, len(segs)
