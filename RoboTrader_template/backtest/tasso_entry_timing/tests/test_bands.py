import pytest
from lab.bands import WEIGHTS, exogenous_quantiles, ladder, pit_quantiles


def test_ladder_reproduces_the_samsung_screen():
    """화면 실측 5레벨. 부호가 뒤집히면 여기서 죽는다."""
    got = ladder(peak=380_000, q1=0.353, q3=0.560, c=0.8)
    expected = [238_165, 222_395, 206_625, 190_855, 175_085]
    for g, e in zip(got, expected):
        assert abs(g - e) < 300, (got, expected)


def test_first_level_is_the_highest_price_and_last_gets_the_most_weight():
    """사다리 방향 + 하방가중. 총 체결금액은 뒤집혀도 비슷해서 합계로는 안 잡힌다."""
    lv = ladder(peak=380_000, q1=0.353, q3=0.560, c=0.8)
    assert lv[0] > lv[-1]
    assert WEIGHTS[-1] > WEIGHTS[0]
    assert abs(sum(WEIGHTS) - 1.0) < 1e-9


def test_ladder_is_evenly_spaced():
    lv = ladder(peak=5_100, q1=0.119, q3=0.199, c=0.8)
    gaps = [lv[i] - lv[i + 1] for i in range(4)]
    assert max(gaps) - min(gaps) < 1e-6


def test_pit_returns_none_when_bucket_sample_is_too_small():
    history = [(0.4, 0.3)] * 5          # (gain, drawdown) 5건뿐
    assert pit_quantiles(history, gain=0.4, min_n=30) is None


def test_pit_uses_only_the_matching_gain_bucket():
    history = [(0.4, 0.10)] * 40 + [(5.0, 0.50)] * 40
    q1, q3 = pit_quantiles(history, gain=0.4, min_n=30)
    assert q1 == pytest.approx(0.10, abs=1e-6)
    assert q3 == pytest.approx(0.10, abs=1e-6)


def test_exogenous_interpolation_matches_the_two_observed_points():
    _, _ = exogenous_quantiles(0.298)
    c_danal = sum(exogenous_quantiles(0.298)) / 2
    c_samsung = sum(exogenous_quantiles(6.143)) / 2
    assert c_danal == pytest.approx(0.1590, abs=1e-3)
    assert c_samsung == pytest.approx(0.4565, abs=1e-3)
