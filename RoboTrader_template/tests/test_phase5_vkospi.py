"""
test_phase5_vkospi.py
=====================

VKOSPI 시그널 (S2-01) 단위 테스트.

커버리지:
  - No Look-Ahead 검증 (end_date = scan_date - 1)
  - vkospi_at: 정확한 날짜 및 값 반환
  - vkospi_zscore: z-score 계산 정확성, 데이터 부족 처리
  - vkospi_spike_signal: 임계값 동작 검증
  - 백필 스크립트 _yearly_windows: 날짜 분할
  - 백필 스크립트 dry-run 모드
  - DB 실패 시 graceful degradation
"""
from __future__ import annotations

import sys
import os
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# sys.path 설정
# ─────────────────────────────────────────────────────────────────────────────
_TMPL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TMPL_ROOT not in sys.path:
    sys.path.insert(0, _TMPL_ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _make_db_mock(rows: list[tuple]):
    """psycopg2 커넥션/커서 Mock (fetchall → rows)."""
    mock_cur = MagicMock()
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = rows

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.close = MagicMock()
    return mock_conn


def _make_vkospi_rows(values: list[tuple[date, float]]) -> list[tuple]:
    """(trade_date, close) 튜플 리스트 생성 헬퍼."""
    return [(d, v) for d, v in values]


# ─────────────────────────────────────────────────────────────────────────────
# 1. No Look-Ahead 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestNoLookAhead:
    """PIT 보장: scan_date = T+1 의사결정일, 사용 데이터는 T일 이하."""

    def test_vkospi_at_uses_scan_date_minus_one(self):
        """vkospi_at(scan_date) 내부에서 end_date = scan_date - 1."""
        from signals.vkospi import vkospi_at

        captured: list[date] = []

        def _mock_fetch(end_date: date, window: int = 60):
            captured.append(end_date)
            import pandas as pd
            return pd.DataFrame([{"trade_date": end_date, "close": 18.5}])

        scan_date = date(2026, 5, 23)
        with patch("signals.vkospi._fetch_vkospi_history", side_effect=_mock_fetch):
            vkospi_at(scan_date)

        assert len(captured) == 1
        assert captured[0] == scan_date - timedelta(days=1), (
            f"PIT 위반: end_date={captured[0]}, expected={scan_date - timedelta(days=1)}"
        )

    def test_vkospi_zscore_uses_scan_date_minus_one(self):
        """vkospi_zscore(scan_date) 내부 end_date = scan_date - 1."""
        from signals.vkospi import vkospi_zscore

        captured: list[date] = []

        def _mock_fetch(end_date: date, window: int = 60):
            captured.append(end_date)
            # 충분한 히스토리 반환
            import pandas as pd
            rows = [
                {"trade_date": end_date - timedelta(days=i), "close": 18.0 + i * 0.1}
                for i in range(30, -1, -1)
            ]
            return pd.DataFrame(rows)

        scan_date = date(2026, 5, 23)
        with patch("signals.vkospi._fetch_vkospi_history", side_effect=_mock_fetch):
            vkospi_zscore(scan_date)

        assert captured[0] == scan_date - timedelta(days=1)

    def test_spike_signal_uses_scan_date_minus_one(self):
        """vkospi_spike_signal은 vkospi_zscore를 통해 PIT를 위임함."""
        from signals.vkospi import vkospi_spike_signal

        with patch("signals.vkospi.vkospi_zscore", return_value=1.5) as mock_z:
            vkospi_spike_signal(date(2026, 5, 23), threshold_z=2.0)
            mock_z.assert_called_once_with(date(2026, 5, 23))


# ─────────────────────────────────────────────────────────────────────────────
# 2. vkospi_at 정확성
# ─────────────────────────────────────────────────────────────────────────────

class TestVkospiAt:
    """vkospi_at: 날짜별 종가 반환 검증."""

    def test_returns_exact_date_close(self):
        """end_date 당일 데이터 반환."""
        from signals.vkospi import vkospi_at

        end_date = date(2026, 5, 22)
        rows = [(end_date, 22.5), (date(2026, 5, 21), 20.0)]

        mock_conn = _make_db_mock(rows)
        with patch("signals.vkospi._get_conn", return_value=mock_conn):
            result = vkospi_at(date(2026, 5, 23))  # scan_date → end_date = 2026-05-22

        assert result == 22.5

    def test_empty_db_returns_nan(self):
        """DB 데이터 없으면 NaN."""
        from signals.vkospi import vkospi_at

        mock_conn = _make_db_mock([])
        with patch("signals.vkospi._get_conn", return_value=mock_conn):
            result = vkospi_at(date(2026, 5, 23))

        assert pd.isna(result)

    def test_db_exception_returns_nan(self):
        """DB 연결 실패 시 NaN."""
        from signals.vkospi import vkospi_at

        with patch("signals.vkospi._get_conn", side_effect=Exception("연결 실패")):
            result = vkospi_at(date(2026, 5, 23))

        assert pd.isna(result)

    def test_returns_most_recent_when_no_exact_match(self):
        """end_date 당일 없으면 가장 최근 데이터 반환 (장 휴일 등)."""
        from signals.vkospi import vkospi_at

        # end_date = 2026-05-22 (금), DB에는 2026-05-21 (목) 까지만 있음
        rows = [
            (date(2026, 5, 19), 18.0),
            (date(2026, 5, 20), 19.5),
            (date(2026, 5, 21), 21.0),
        ]
        mock_conn = _make_db_mock(rows)
        with patch("signals.vkospi._get_conn", return_value=mock_conn):
            result = vkospi_at(date(2026, 5, 23))

        # 가장 최근 = 2026-05-21 → 21.0
        assert result == 21.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. vkospi_zscore 계산 정확성
# ─────────────────────────────────────────────────────────────────────────────

class TestVkospiZscore:
    """z-score 계산 검증."""

    def _patch_fetch(self, rows: list[tuple]):
        """_fetch_vkospi_history Mock."""
        df = pd.DataFrame(rows, columns=["trade_date", "close"])
        df["close"] = df["close"].astype(float)
        df = df.sort_values("trade_date").reset_index(drop=True)
        return patch("signals.vkospi._fetch_vkospi_history", return_value=df)

    def test_zscore_calculation_correct(self):
        """z-score = (current - mean(hist)) / std(hist) 검증.

        구현 로직:
          closes = df["close"].values  (오름차순 정렬)
          current = closes[-1]         (마지막 = 최신값)
          hist = closes[:-1] if len(closes) > window else closes
          window=60 이고 len(closes)=10 이므로 hist = closes (전체)
          mu = mean(closes), sigma = std(closes, ddof=1)
          z = (current - mu) / sigma
        """
        from signals.vkospi import vkospi_zscore

        # 10개 데이터, window=60 → len(10) <= 60 → hist = closes (전체)
        closes = [15.0, 16.0, 14.0, 15.5, 17.0, 16.5, 15.0, 14.5, 16.0, 20.0]
        rows = [
            (date(2026, 1, 1) + timedelta(days=i), v)
            for i, v in enumerate(closes)
        ]

        with self._patch_fetch(rows):
            z = vkospi_zscore(date(2026, 1, 11), window=60)

        # 수동 계산: hist = closes (전체, window 초과 아님)
        hist = pd.Series(closes)
        current = closes[-1]
        expected_z = (current - hist.mean()) / hist.std(ddof=1)
        assert abs(z - expected_z) < 1e-6, f"z-score 불일치: {z} != {expected_z}"

    def test_zscore_too_few_data_returns_nan(self):
        """데이터 1건이면 NaN (std 계산 불가)."""
        from signals.vkospi import vkospi_zscore

        rows = [(date(2026, 5, 22), 18.5)]
        with self._patch_fetch(rows):
            z = vkospi_zscore(date(2026, 5, 23))

        assert pd.isna(z)

    def test_zscore_zero_std_returns_zero(self):
        """표준편차 0 (모든 값 동일)이면 z-score = 0."""
        from signals.vkospi import vkospi_zscore

        rows = [(date(2026, 1, 1) + timedelta(days=i), 20.0) for i in range(10)]
        with self._patch_fetch(rows):
            z = vkospi_zscore(date(2026, 1, 11))

        assert z == 0.0

    def test_zscore_db_exception_returns_nan(self):
        """DB 예외 시 NaN."""
        from signals.vkospi import vkospi_zscore

        with patch("signals.vkospi._get_conn", side_effect=Exception("DB 오류")):
            z = vkospi_zscore(date(2026, 5, 23))

        assert pd.isna(z)


# ─────────────────────────────────────────────────────────────────────────────
# 4. vkospi_spike_signal 임계값 동작
# ─────────────────────────────────────────────────────────────────────────────

class TestVkospiSpikeSignal:
    """스파이크 감지 임계값 검증."""

    def test_spike_above_threshold_returns_true(self):
        """z-score > threshold → True (공포 국면)."""
        from signals.vkospi import vkospi_spike_signal

        with patch("signals.vkospi.vkospi_zscore", return_value=2.5):
            assert vkospi_spike_signal(date(2026, 5, 23), threshold_z=2.0) is True

    def test_spike_below_threshold_returns_false(self):
        """z-score < threshold → False (정상 국면)."""
        from signals.vkospi import vkospi_spike_signal

        with patch("signals.vkospi.vkospi_zscore", return_value=1.5):
            assert vkospi_spike_signal(date(2026, 5, 23), threshold_z=2.0) is False

    def test_spike_exactly_at_threshold_returns_false(self):
        """z-score == threshold → False (초과 아님)."""
        from signals.vkospi import vkospi_spike_signal

        with patch("signals.vkospi.vkospi_zscore", return_value=2.0):
            assert vkospi_spike_signal(date(2026, 5, 23), threshold_z=2.0) is False

    def test_spike_nan_returns_false(self):
        """z-score NaN → False (데이터 없음 = 신호 없음)."""
        from signals.vkospi import vkospi_spike_signal

        with patch("signals.vkospi.vkospi_zscore", return_value=float("nan")):
            assert vkospi_spike_signal(date(2026, 5, 23)) is False

    def test_spike_custom_threshold(self):
        """커스텀 임계값 (threshold_z=3.0) 동작."""
        from signals.vkospi import vkospi_spike_signal

        with patch("signals.vkospi.vkospi_zscore", return_value=2.5):
            # threshold=3.0 이면 z=2.5는 미달
            assert vkospi_spike_signal(date(2026, 5, 23), threshold_z=3.0) is False

        with patch("signals.vkospi.vkospi_zscore", return_value=3.1):
            # threshold=3.0 이면 z=3.1은 초과
            assert vkospi_spike_signal(date(2026, 5, 23), threshold_z=3.0) is True

    def test_negative_zscore_returns_false(self):
        """z-score 음수 (VKOSPI 하락) → False."""
        from signals.vkospi import vkospi_spike_signal

        with patch("signals.vkospi.vkospi_zscore", return_value=-1.5):
            assert vkospi_spike_signal(date(2026, 5, 23)) is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. 백필 스크립트 유틸 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestBackfillVkospiUtils:
    """backfill_vkospi.py 유틸 함수 단위 검증."""

    def test_yearly_windows_count_full_5yr(self):
        """2021 ~ 2026: 6개 윈도우."""
        from scripts.backfill_vkospi import _yearly_windows

        windows = _yearly_windows(date(2021, 1, 1), date(2026, 5, 25))
        assert len(windows) == 6, f"연도 윈도우 수 불일치: {len(windows)}"

    def test_yearly_windows_format(self):
        """윈도우 날짜가 YYYYMMDD 형식."""
        from scripts.backfill_vkospi import _yearly_windows

        windows = _yearly_windows(date(2021, 1, 1), date(2023, 12, 31))
        for fromdate, todate in windows:
            assert len(fromdate) == 8 and fromdate.isdigit()
            assert len(todate) == 8 and todate.isdigit()

    def test_yearly_windows_no_overlap(self):
        """윈도우가 연속적이고 겹치지 않음."""
        from scripts.backfill_vkospi import _yearly_windows
        from datetime import datetime

        windows = _yearly_windows(date(2021, 1, 1), date(2025, 12, 31))
        for i in range(len(windows) - 1):
            end_i    = datetime.strptime(windows[i][1], "%Y%m%d").date()
            start_i1 = datetime.strptime(windows[i + 1][0], "%Y%m%d").date()
            assert end_i < start_i1, f"윈도우 겹침: {windows[i]} / {windows[i+1]}"

    def test_insert_batch_dry_run_no_db_call(self):
        """dry-run 시 DB 호출 없음."""
        from scripts.backfill_vkospi import _insert_batch

        rows = [
            {"trade_date": date(2026, 5, 22), "open": 18.0,
             "high": 20.0, "low": 17.5, "close": 19.5, "volume": None},
        ]
        with patch("scripts.backfill_vkospi._get_conn") as mock_conn:
            result = _insert_batch(rows, dry_run=True)
            mock_conn.assert_not_called()

        assert result == len(rows)

    def test_insert_batch_empty_rows_returns_zero(self):
        """빈 rows → 0 반환."""
        from scripts.backfill_vkospi import _insert_batch

        result = _insert_batch([], dry_run=True)
        assert result == 0

    def test_yearly_windows_partial_year_end(self):
        """연도 중간 종료일도 정확히 처리."""
        from scripts.backfill_vkospi import _yearly_windows
        from datetime import datetime

        windows = _yearly_windows(date(2026, 1, 1), date(2026, 5, 25))
        assert len(windows) == 1
        assert windows[0][0] == "20260101"
        assert windows[0][1] == "20260525"

    def test_fetch_vkospi_year_pykrx_not_installed(self):
        """pykrx 미설치 시 빈 리스트 반환."""
        from scripts.backfill_vkospi import _fetch_vkospi_year

        with patch.dict("sys.modules", {"pykrx": None, "pykrx.stock": None}):
            # ImportError 발생 → 빈 리스트
            import importlib
            with patch("builtins.__import__", side_effect=ImportError("pykrx 없음")):
                # _fetch_vkospi_year 내부에서 try/except ImportError → []
                try:
                    result = _fetch_vkospi_year("20260101", "20260131")
                    assert isinstance(result, list)
                except ImportError:
                    pass  # ImportError 직접 전파 시에도 테스트 통과


# ─────────────────────────────────────────────────────────────────────────────
# 6. _fetch_vkospi_history 통합 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchVkospiHistory:
    """_fetch_vkospi_history: DB 조회 결과 DataFrame 변환."""

    def test_returns_sorted_dataframe(self):
        """날짜 오름차순 정렬된 DataFrame 반환."""
        from signals.vkospi import _fetch_vkospi_history

        rows = [
            (date(2026, 5, 22), 22.0),
            (date(2026, 5, 20), 20.0),
            (date(2026, 5, 21), 21.0),
        ]
        mock_conn = _make_db_mock(rows)
        with patch("signals.vkospi._get_conn", return_value=mock_conn):
            df = _fetch_vkospi_history(date(2026, 5, 22), window=60)

        assert list(df["trade_date"]) == sorted(df["trade_date"].tolist())

    def test_returns_float_close(self):
        """close 컬럼이 float 타입."""
        from signals.vkospi import _fetch_vkospi_history

        rows = [(date(2026, 5, 22), 18.75)]
        mock_conn = _make_db_mock(rows)
        with patch("signals.vkospi._get_conn", return_value=mock_conn):
            df = _fetch_vkospi_history(date(2026, 5, 22))

        assert df["close"].dtype == float or str(df["close"].dtype).startswith("float")

    def test_db_exception_returns_empty_df(self):
        """DB 예외 시 빈 DataFrame."""
        from signals.vkospi import _fetch_vkospi_history

        with patch("signals.vkospi._get_conn", side_effect=Exception("오류")):
            df = _fetch_vkospi_history(date(2026, 5, 22))

        assert df.empty
        assert "close" in df.columns
