import pytest
from lab.bands import WEIGHTS
from lab.calibrate import best_subset_avg, score_grade2


def test_subset_averages_include_the_danal_observed_prices():
    """다날 실제 매입가 4,404.36 = 1·2차 가중평균, 4,297.96 = 1~4차 가중평균."""
    levels = [4452.0, 4371.0, 4289.0, 4208.0, 4126.0]
    avgs = best_subset_avg(levels, WEIGHTS)
    assert any(abs(a - 4404.36) < 5 for a in avgs), avgs
    assert any(abs(a - 4297.96) < 5 for a in avgs), avgs


def test_score_uses_subset_average_not_single_level():
    """단일 레벨 최근접으로 채점하면 정답 규칙을 탈락시킨다."""
    levels = [4452.0, 4371.0, 4289.0, 4208.0, 4126.0]
    fills = [{"buy": 4404.36}]
    assert score_grade2(levels, fills) == pytest.approx(0.0, abs=2e-3)
