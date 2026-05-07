"""spike_label 단위 테스트."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from RoboTrader_template.multiverse.labels.spike_label import (
    is_spike_d,
    label_dataframe,
)


# ──────────────────────────────────────────────────────────────────────────────
# is_spike_d
# ──────────────────────────────────────────────────────────────────────────────

class TestIsSpikeD:
    def test_exactly_five_percent_is_true(self):
        """D-1 close=10000, D high=10500 → 정확히 +5% → True."""
        assert is_spike_d(10_000.0, 10_500.0, threshold=0.05) is True

    def test_one_below_five_percent_is_false(self):
        """D-1 close=10000, D high=10499 → +4.99% → False."""
        assert is_spike_d(10_000.0, 10_499.0, threshold=0.05) is False

    def test_above_threshold_is_true(self):
        assert is_spike_d(10_000.0, 11_000.0, threshold=0.05) is True

    def test_default_threshold_is_five_percent(self):
        """threshold 인자 생략 → 기본값 0.05."""
        assert is_spike_d(10_000.0, 10_500.0) is True
        assert is_spike_d(10_000.0, 10_499.0) is False

    def test_custom_threshold(self):
        """threshold=0.10 → 10% 이상."""
        assert is_spike_d(10_000.0, 11_000.0, threshold=0.10) is True
        assert is_spike_d(10_000.0, 10_999.0, threshold=0.10) is False

    def test_equal_to_close_is_false(self):
        """D high == D-1 close → 0% 상승 → False."""
        assert is_spike_d(10_000.0, 10_000.0, threshold=0.05) is False

    def test_negative_return_is_false(self):
        """하락한 경우 → False."""
        assert is_spike_d(10_000.0, 9_000.0, threshold=0.05) is False

    def test_zero_threshold_requires_gte_close(self):
        """threshold=0 → high >= close이면 True."""
        assert is_spike_d(10_000.0, 10_000.0, threshold=0.0) is True
        assert is_spike_d(10_000.0, 9_999.0, threshold=0.0) is False

    def test_float_precision(self):
        """부동소수점 경계값: 정확히 5% 경계."""
        close = 10_000.0
        high = close * 1.05
        # 수학적으로 정확히 경계 → True
        assert is_spike_d(close, high, threshold=0.05) is True


# ──────────────────────────────────────────────────────────────────────────────
# label_dataframe
# ──────────────────────────────────────────────────────────────────────────────

class TestLabelDataframe:
    def _make_df(self, close_list: list, high_list: list) -> pd.DataFrame:
        """close / high 컬럼만 있는 DataFrame."""
        assert len(close_list) == len(high_list)
        return pd.DataFrame({"close": close_list, "high": high_list})

    def test_last_row_is_nan(self):
        """마지막 행은 항상 NaN."""
        df = self._make_df([10_000, 10_100, 10_200], [10_500, 10_600, 10_700])
        labels = label_dataframe(df)
        assert math.isnan(labels.iloc[-1]), "마지막 행은 NaN이어야 함"

    def test_known_positive(self):
        """close=10000 → next high=10500 (exactly +5%) → True."""
        df = self._make_df([10_000, 10_100], [10_200, 10_500])
        labels = label_dataframe(df)
        assert labels.iloc[0] is True or labels.iloc[0] == True

    def test_known_negative(self):
        """close=10000 → next high=10499 (+4.99%) → False."""
        df = self._make_df([10_000, 10_100], [10_200, 10_499])
        labels = label_dataframe(df)
        assert labels.iloc[0] is False or labels.iloc[0] == False

    def test_positive_negative_count(self):
        """알려진 시퀀스로 양성/음성 카운트 검증.

        5행 DataFrame:
          행 0: close=10000, 다음 high=10500 → True  (+5.0%)
          행 1: close=10000, 다음 high=10499 → False (+4.99%)
          행 2: close=10000, 다음 high=11000 → True  (+10%)
          행 3: close=10000, 다음 high=9000  → False (-10%)
          행 4: (마지막) → NaN

        close 컬럼은 라벨 계산에서 i번째 행의 close를 사용.
        high 컬럼은 i+1번째 행의 high를 사용.

        즉:
          labels[0] = high[1] >= close[0] * 1.05 = 10499 >= 10500 → False
          labels[1] = high[2] >= close[1] * 1.05 = 11000 >= 10500 → True
          labels[2] = high[3] >= close[2] * 1.05 = 9000 >= 10500  → False
          labels[3] = high[4] >= close[3] * 1.05 = NaN high 없음  → 마지막-1
          labels[4] = NaN

        실제 5행 테스트:
        close = [10000, 10000, 10000, 10000, 10000]
        high  = [999,   10499, 11000,  9000,  10500]

        labels[0] = high[1]=10499 >= close[0]*1.05=10500 → False
        labels[1] = high[2]=11000 >= close[1]*1.05=10500 → True
        labels[2] = high[3]=9000  >= close[2]*1.05=10500 → False
        labels[3] = high[4]=10500 >= close[3]*1.05=10500 → True
        labels[4] = NaN
        → 양성 2, 음성 2, NaN 1
        """
        close = [10_000.0] * 5
        high  = [999.0, 10_499.0, 11_000.0, 9_000.0, 10_500.0]
        df = self._make_df(close, high)
        labels = label_dataframe(df)

        assert len(labels) == 5
        assert math.isnan(labels.iloc[-1])

        non_nan = [v for v in labels.iloc[:-1] if not (isinstance(v, float) and math.isnan(v))]
        positives = sum(1 for v in non_nan if v is True or v == True)
        negatives = sum(1 for v in non_nan if v is False or v == False)

        assert positives == 2, f"양성 2개 기대, 실제={positives}"
        assert negatives == 2, f"음성 2개 기대, 실제={negatives}"

    def test_length_equals_input(self):
        """반환 Series 길이 == 입력 DataFrame 길이."""
        n = 10
        df = self._make_df([10_000.0] * n, [10_500.0] * n)
        labels = label_dataframe(df)
        assert len(labels) == n

    def test_index_preserved(self):
        """반환 Series 인덱스가 입력 DataFrame 인덱스와 동일."""
        df = self._make_df([10_000.0, 10_100.0, 10_200.0], [10_500.0, 10_600.0, 10_700.0])
        df.index = [10, 20, 30]
        labels = label_dataframe(df)
        assert list(labels.index) == [10, 20, 30]

    def test_single_row_all_nan(self):
        """1행 → 라벨 1개 모두 NaN."""
        df = self._make_df([10_000.0], [10_500.0])
        labels = label_dataframe(df)
        assert len(labels) == 1
        assert math.isnan(labels.iloc[0])

    def test_custom_threshold(self):
        """threshold=0.10 → 10% 이상만 양성."""
        close = [10_000.0, 10_000.0]
        high_values = [10_999.0, 11_000.0]  # [+9.99%, +10%]
        df = self._make_df(close, high_values)
        labels = label_dataframe(df, threshold=0.10)
        # labels[0] = high[1]=11000 >= close[0]*1.10=11000 → True
        assert labels.iloc[0] is True or labels.iloc[0] == True
        assert math.isnan(labels.iloc[1])

    def test_below_custom_threshold(self):
        """threshold=0.10, high < 10% → False."""
        close = [10_000.0, 10_000.0]
        high_values = [10_100.0, 10_999.0]
        df = self._make_df(close, high_values)
        labels = label_dataframe(df, threshold=0.10)
        # labels[0] = high[1]=10999 >= close[0]*1.10=11000 → False
        assert labels.iloc[0] is False or labels.iloc[0] == False
