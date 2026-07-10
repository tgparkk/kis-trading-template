import numpy as np
import pytest

from scripts.discovery.multiframe_chart_cnn.label3d import label3d


def test_tp_hit_intrabar_realizes_exactly_at_tp():
    entry = 100.0
    # 1봉째 고가가 +3% 넘게 찍히지만 시가는 갭 아님 → 정확히 tp 에 실현
    fwd_open = np.array([100.1, 100.2])
    fwd_high = np.array([103.5, 104.0])
    fwd_low = np.array([99.9, 100.0])
    fwd_close = np.array([103.0, 103.5])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.03, sl=0.03)
    assert outcome == "tp"
    assert ret == pytest.approx(0.03)


def test_gap_up_through_tp_realizes_at_open():
    entry = 100.0
    # 시가가 이미 +5% 갭업 → tp 를 시가에 실현(정확히 3% 아님, 5%)
    fwd_open = np.array([105.0])
    fwd_high = np.array([106.0])
    fwd_low = np.array([104.0])
    fwd_close = np.array([105.5])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.03, sl=0.03)
    assert outcome == "tp"
    assert ret == pytest.approx(0.05)


def test_gap_down_through_sl_realizes_at_open():
    entry = 100.0
    fwd_open = np.array([94.0])   # -6% 갭다운
    fwd_high = np.array([95.0])
    fwd_low = np.array([93.0])
    fwd_close = np.array([94.5])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.05, sl=0.03)
    assert outcome == "sl"
    assert ret == pytest.approx(-0.06)


def test_intrabar_both_barriers_sl_wins():
    entry = 100.0
    fwd_open = np.array([100.0])
    fwd_high = np.array([104.0])   # +4% 고가
    fwd_low = np.array([96.0])     # -4% 저가 (같은 봉)
    fwd_close = np.array([100.0])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.03, sl=0.03)
    assert outcome == "sl"
    assert ret == pytest.approx(-0.03)


def test_timeout_realizes_at_last_close():
    entry = 100.0
    fwd_open = np.array([100.0, 100.5, 101.0])
    fwd_high = np.array([101.0, 101.5, 102.0])
    fwd_low = np.array([99.0, 99.5, 100.0])
    fwd_close = np.array([100.5, 101.0, 101.5])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.05, sl=0.05)
    assert outcome == "timeout"
    assert ret == pytest.approx(101.5 / 100.0 - 1.0)


def test_first_touch_ordering_sl_before_tp():
    entry = 100.0
    # 1봉 SL, 2봉 TP → 먼저 온 SL 이 결과
    fwd_open = np.array([100.0, 100.0])
    fwd_high = np.array([101.0, 105.0])
    fwd_low = np.array([96.0, 100.0])
    fwd_close = np.array([97.0, 104.0])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.03, sl=0.03)
    assert outcome == "sl"
