import numpy as np
import pandas as pd
from lab.control import control_levels
from lab.sim import simulate


def _bars(rows):
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])


def test_fill_happens_at_the_level_when_low_touches_it():
    bars = _bars([["2026-01-02", 100, 101, 89, 95]] + [["2026-01-%02d" % d, 95, 96, 94, 95] for d in range(3, 25)])
    t = simulate(bars, levels=[90.0], hold_days=20)
    assert t.avg_cost == 90.0


def test_gap_down_fills_at_the_open_not_the_level():
    bars = _bars([["2026-01-02", 80, 82, 78, 81]] + [["2026-01-%02d" % d, 81, 82, 80, 81] for d in range(3, 25)])
    t = simulate(bars, levels=[90.0], hold_days=20)
    assert t.avg_cost == 80.0


def test_trade_is_marked_truncated_when_data_ends_before_hold_period():
    bars = _bars([["2026-01-02", 100, 101, 89, 95], ["2026-01-05", 95, 96, 94, 95]])
    t = simulate(bars, levels=[90.0], hold_days=20)
    assert t.truncated is True


def test_cost_is_deducted_from_the_return():
    bars = _bars([["2026-01-02", 100, 101, 89, 95]] + [["2026-01-%02d" % d, 100, 100, 100, 100] for d in range(3, 25)])
    t = simulate(bars, levels=[90.0], hold_days=20, cost=0.0021)
    gross = 100.0 / 90.0 - 1.0
    assert abs(t.ret_net - (gross - 0.0021)) < 1e-9


def test_control_levels_are_descending_and_inside_the_band():
    """대조군은 진입 '가격'만 무작위다 — 개수·순서 규약은 전략과 같아야 한다."""
    rng = np.random.default_rng(0)
    lv = control_levels(peak=5100.0, low_bound=4126.0, rng=rng, n=5)
    assert len(lv) == 5
    assert lv == sorted(lv, reverse=True)          # 1차가 최고가 — ladder 와 같은 규약
    assert all(4126.0 <= x <= 5100.0 for x in lv)


def test_control_levels_are_reproducible_for_the_same_seed():
    """재현 불가능한 대조군은 증거가 못 된다."""
    a = control_levels(5100.0, 4126.0, np.random.default_rng(42))
    b = control_levels(5100.0, 4126.0, np.random.default_rng(42))
    assert a == b


def test_partial_fill_is_reported_so_asymmetry_is_visible():
    """전략은 2개만 체결되고 대조군은 5개 다 체결되는 상황이 실제로 생긴다.

    3차를 뒤집은 절단 비대칭과 같은 클래스이므로 filled_n 을 반드시 기록한다.
    """
    bars = _bars([["2026-01-02", 100, 101, 95, 97]] + [["2026-01-%02d" % d, 97, 98, 96, 97] for d in range(3, 25)])
    t = simulate(bars, levels=[99.0, 96.0, 90.0], hold_days=20)
    assert t.filled_n == 2, t.filled_n


def test_fills_stop_at_the_validity_window():
    """유효기간 D 는 진입 창이지 보유 창이 아니다.

    제한이 없으면 보유기간 구간에서까지 체결이 일어나 청산이 창 밖으로 밀리고
    절단율이 구조적으로 부풀려진다(제한 없이 실측했을 때 54%).
    """
    bars = _bars([["2026-01-%02d" % d, 100, 101, 99, 100] for d in range(2, 10)]
                 + [["2026-01-%02d" % d, 100, 101, 80, 85] for d in range(10, 30)])
    t = simulate(bars, levels=[90.0], hold_days=5, max_fill_bars=5)
    assert t is None, "유효기간 밖 체결이 새어 들어왔다"
    t2 = simulate(bars, levels=[90.0], hold_days=5, max_fill_bars=20)
    assert t2 is not None and t2.filled_n == 1
