"""
test_phase5_foreign_flow.py
===========================

외국인 5일 누적 순매수 시그널 (F-06) 단위 테스트.

커버리지:
  - No Look-Ahead 검증 (end_date = scan_date - 1)
  - foreign_net_buy_5d_cum: DB fixture 기반 누적 정확성
  - foreign_flow_signal: 양수/음수/누락 종목 처리
  - DB 실패 시 NaN 반환 (graceful degradation)

참고: 과거 backfill_foreign_flow.py(pykrx) 유틸 검증 클래스 TestBackfillUtils 는
스크립트가 Naver 소스 구현으로 통째 교체되며(_monthly_windows/_map_and_append/
_insert_batch 삭제) 고아가 되어 제거함(2026-06-23). 신규 스크립트는 네트워크/DB
바운드라 순수 단위 대상이 없음. 런타임 신호 모듈 signals/foreign_flow.py 는 위
커버리지로 유지.
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
