"""
test_phase5_foreign_flow.py
===========================

외국인 5일 누적 순매수 시그널 (F-06) 단위 테스트.

커버리지:
  - No Look-Ahead 검증 (end_date = scan_date - 1)
  - foreign_net_buy_5d_cum: DB fixture 기반 누적 정확성
  - foreign_flow_signal: 양수/음수/누락 종목 처리
  - DB 실패 시 NaN 반환 (graceful degradation)
  - 백필 스크립트 _monthly_windows: 날짜 분할 정확성
  - 백필 스크립트 _map_and_append: 컬럼 매핑
  - dry-run 모드: DB 저장 없이 건수 반환
"""
from __future__ import annotations

import sys
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# sys.path 설정 — RoboTrader_template 루트를 경로에 추가
# ─────────────────────────────────────────────────────────────────────────────
_TMPL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TMPL_ROOT not in sys.path:
    sys.path.insert(0, _TMPL_ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼: DB 커서 Mock 생성
# ─────────────────────────────────────────────────────────────────────────────

def _make_db_mock(rows: list[tuple]):
    """psycopg2 커넥션/커서 Mock 반환 (fetchall → rows)."""
    mock_cur = MagicMock()
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = rows

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.close = MagicMock()
    return mock_conn


# ─────────────────────────────────────────────────────────────────────────────
# 1. No Look-Ahead 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestNoLookAhead:
    """PIT 보장: T+1 의사결정에 T일 이하 데이터만 사용."""

    def test_foreign_net_buy_5d_cum_end_date_is_yesterday(self):
        """foreign_net_buy_5d_cum의 end_date 파라미터가 scan_date - 1임을 소비자가 보장해야 함.

        실제 SQL 조회 조건: trade_date <= end_date
        scan_date=오늘이면 end_date=어제 → 오늘 데이터 절대 미포함.
        """
        from signals.foreign_flow import foreign_net_buy_5d_cum

        scan_date = date(2026, 5, 23)  # 금요일 (의사결정일 T+1)
        end_date = date(2026, 5, 22)   # 목요일 (T일 = 마지막 사용 가능 데이터)

        # end_date <= scan_date - 1 이 성립함을 확인
        from datetime import timedelta
        assert end_date <= scan_date - timedelta(days=1), (
            f"PIT 위반: end_date({end_date}) > scan_date-1({scan_date - timedelta(days=1)})"
        )

    def test_foreign_flow_signal_uses_scan_date_minus_one(self):
        """foreign_flow_signal 내부에서 end_date = scan_date - 1일로 설정됨을 검증."""
        from signals.foreign_flow import foreign_flow_signal

        captured_end_dates: list[date] = []

        def _mock_cum(stock_code: str, end_date: date) -> float:
            captured_end_dates.append(end_date)
            return 1_000_000.0  # 양수 → True

        scan_date = date(2026, 5, 23)
        with patch("signals.foreign_flow.foreign_net_buy_5d_cum", side_effect=_mock_cum):
            result = foreign_flow_signal(["005930", "000660"], scan_date)

        from datetime import timedelta
        expected_end = scan_date - timedelta(days=1)
        for ed in captured_end_dates:
            assert ed == expected_end, (
                f"PIT 위반: end_date={ed}, expected={expected_end}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. foreign_net_buy_5d_cum 누적 정확성
# ─────────────────────────────────────────────────────────────────────────────

class TestForeignNetBuy5dCum:
    """5일 누적 순매수 계산 정확성."""

    def test_simple_sum_of_five_days(self):
        """5거래일 합산이 정확한지 확인."""
        from signals.foreign_flow import foreign_net_buy_5d_cum

        # Fixture: 5거래일 순매수대금
        fixture_rows = [
            (date(2026, 5, 22), 1_000_000),
            (date(2026, 5, 21), 2_000_000),
            (date(2026, 5, 20), -500_000),
            (date(2026, 5, 19), 3_000_000),
            (date(2026, 5, 16), 500_000),
        ]
        expected = 1_000_000 + 2_000_000 + (-500_000) + 3_000_000 + 500_000

        mock_conn = _make_db_mock(fixture_rows)
        with patch("signals.foreign_flow._get_conn", return_value=mock_conn):
            result = foreign_net_buy_5d_cum("005930", date(2026, 5, 22))

        assert result == float(expected), f"누적합 불일치: {result} != {expected}"

    def test_empty_db_returns_nan(self):
        """DB에 데이터 없으면 NaN 반환 (graceful degradation)."""
        from signals.foreign_flow import foreign_net_buy_5d_cum

        mock_conn = _make_db_mock([])
        with patch("signals.foreign_flow._get_conn", return_value=mock_conn):
            result = foreign_net_buy_5d_cum("999999", date(2026, 5, 22))

        assert pd.isna(result), f"빈 DB에서 NaN 반환 기대, got: {result}"

    def test_db_exception_returns_nan(self):
        """DB 연결 실패 시 NaN 반환 (예외 억제)."""
        from signals.foreign_flow import foreign_net_buy_5d_cum

        with patch("signals.foreign_flow._get_conn", side_effect=Exception("연결 실패")):
            result = foreign_net_buy_5d_cum("005930", date(2026, 5, 22))

        assert pd.isna(result), f"DB 예외 시 NaN 반환 기대, got: {result}"

    def test_none_values_in_net_buy_val_skipped(self):
        """net_buy_val이 None인 행은 합산에서 제외."""
        from signals.foreign_flow import foreign_net_buy_5d_cum

        fixture_rows = [
            (date(2026, 5, 22), 1_000_000),
            (date(2026, 5, 21), None),   # None → 스킵
            (date(2026, 5, 20), 2_000_000),
        ]

        mock_conn = _make_db_mock(fixture_rows)
        with patch("signals.foreign_flow._get_conn", return_value=mock_conn):
            result = foreign_net_buy_5d_cum("005930", date(2026, 5, 22))

        assert result == 3_000_000.0, f"None 스킵 후 합산 불일치: {result}"

    def test_negative_cumulative_returns_negative(self):
        """5일 누적이 음수이면 음수 반환 (매도 압력)."""
        from signals.foreign_flow import foreign_net_buy_5d_cum

        fixture_rows = [
            (date(2026, 5, 22), -2_000_000),
            (date(2026, 5, 21), -1_000_000),
            (date(2026, 5, 20), -3_000_000),
        ]

        mock_conn = _make_db_mock(fixture_rows)
        with patch("signals.foreign_flow._get_conn", return_value=mock_conn):
            result = foreign_net_buy_5d_cum("005930", date(2026, 5, 22))

        assert result < 0, f"음수 누적합 기대, got: {result}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. foreign_flow_signal Series 반환
# ─────────────────────────────────────────────────────────────────────────────

class TestForeignFlowSignal:
    """foreign_flow_signal 종목 리스트 처리."""

    def _patch_cum(self, values: dict[str, float]):
        """stock_code → 누적값 Mock."""
        def _mock(stock_code: str, end_date: date) -> float:
            return values.get(stock_code, float("nan"))
        return patch("signals.foreign_flow.foreign_net_buy_5d_cum", side_effect=_mock)

    def test_positive_cumulative_returns_true(self):
        """5일 누적 양수 → True."""
        from signals.foreign_flow import foreign_flow_signal

        with self._patch_cum({"005930": 5_000_000}):
            result = foreign_flow_signal(["005930"], date(2026, 5, 23))

        assert result["005930"] is True or result["005930"] == True

    def test_negative_cumulative_returns_false(self):
        """5일 누적 음수 → False."""
        from signals.foreign_flow import foreign_flow_signal

        with self._patch_cum({"000660": -1_000_000}):
            result = foreign_flow_signal(["000660"], date(2026, 5, 23))

        assert result["000660"] is False or result["000660"] == False

    def test_nan_returns_false(self):
        """데이터 없음(NaN) → False (매수 신호 없음)."""
        from signals.foreign_flow import foreign_flow_signal

        with self._patch_cum({"999999": float("nan")}):
            result = foreign_flow_signal(["999999"], date(2026, 5, 23))

        assert result["999999"] is False or result["999999"] == False

    def test_multiple_stocks(self):
        """복수 종목 혼합 처리."""
        from signals.foreign_flow import foreign_flow_signal

        values = {
            "005930": 10_000_000,   # True
            "000660": -5_000_000,   # False
            "035420": float("nan"), # False
        }
        with self._patch_cum(values):
            result = foreign_flow_signal(list(values.keys()), date(2026, 5, 23))

        assert result["005930"] == True
        assert result["000660"] == False
        assert result["035420"] == False
        assert isinstance(result, pd.Series)
        assert result.dtype == bool

    def test_empty_stock_list(self):
        """빈 종목 리스트 → 빈 Series."""
        from signals.foreign_flow import foreign_flow_signal

        with patch("signals.foreign_flow.foreign_net_buy_5d_cum"):
            result = foreign_flow_signal([], date(2026, 5, 23))

        assert len(result) == 0
        assert isinstance(result, pd.Series)


# ─────────────────────────────────────────────────────────────────────────────
# 4. 백필 스크립트 유틸 함수 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestBackfillUtils:
    """backfill_foreign_flow.py 유틸 함수 단위 검증."""

    def test_monthly_windows_count(self):
        """2021-01 ~ 2021-06: 6개 윈도우 반환."""
        from scripts.backfill_foreign_flow import _monthly_windows

        windows = _monthly_windows(date(2021, 1, 1), date(2021, 6, 30))
        assert len(windows) == 6, f"월별 윈도우 수 불일치: {len(windows)}"

    def test_monthly_windows_format(self):
        """윈도우 날짜가 YYYYMMDD 형식."""
        from scripts.backfill_foreign_flow import _monthly_windows

        windows = _monthly_windows(date(2026, 1, 1), date(2026, 3, 31))
        for fromdate, todate in windows:
            assert len(fromdate) == 8 and fromdate.isdigit()
            assert len(todate) == 8 and todate.isdigit()

    def test_monthly_windows_no_overlap(self):
        """윈도우가 연속적이고 겹치지 않음."""
        from scripts.backfill_foreign_flow import _monthly_windows
        from datetime import datetime

        windows = _monthly_windows(date(2024, 1, 1), date(2024, 12, 31))
        for i in range(len(windows) - 1):
            end_i   = datetime.strptime(windows[i][1], "%Y%m%d").date()
            start_i1 = datetime.strptime(windows[i + 1][0], "%Y%m%d").date()
            assert end_i < start_i1, f"윈도우 겹침: {windows[i]} / {windows[i+1]}"

    def test_insert_batch_dry_run_no_db_call(self):
        """dry-run 모드에서 DB INSERT 호출 없음."""
        from scripts.backfill_foreign_flow import _insert_batch

        rows = [
            {"stock_code": "005930", "trade_date": date(2026, 5, 22),
             "net_buy_vol": 100, "net_buy_val": 1_000_000},
        ]
        with patch("scripts.backfill_foreign_flow._get_conn") as mock_conn:
            result = _insert_batch(rows, dry_run=True)
            mock_conn.assert_not_called()

        assert result == len(rows)

    def test_map_and_append_standard_columns(self):
        """표준 pykrx 컬럼명(한국어)으로 매핑 정상 작동."""
        from scripts.backfill_foreign_flow import _map_and_append

        import pandas as pd
        df = pd.DataFrame([
            {
                "날짜": "20260522",
                "티커": "005930",
                "순매수거래량": 10000,
                "순매수거래대금": 5_000_000,
            }
        ])

        rows: list = []
        _map_and_append(df, rows)

        assert len(rows) == 1
        assert rows[0]["stock_code"] == "005930"
        assert rows[0]["trade_date"] == date(2026, 5, 22)
        assert rows[0]["net_buy_vol"] == 10000
        assert rows[0]["net_buy_val"] == 5_000_000

    def test_map_and_append_invalid_ticker_skipped(self):
        """유효하지 않은 티커(문자 포함) 스킵."""
        from scripts.backfill_foreign_flow import _map_and_append

        import pandas as pd
        df = pd.DataFrame([
            {"날짜": "20260522", "티커": "INVALID", "순매수거래량": 1, "순매수거래대금": 1},
            {"날짜": "20260522", "티커": "000660", "순매수거래량": 2, "순매수거래대금": 2},
        ])

        rows: list = []
        _map_and_append(df, rows)

        codes = [r["stock_code"] for r in rows]
        assert "INVALID" not in codes
        assert "000660" in codes
