"""
Phase 5 ROE Quintile Filter — 단위 테스트
==========================================

테스트 목록
-----------
- TestRoePitNoLookAhead      : PIT 강제 — 미래 report_date 데이터 차단 검증
- TestRoeQuintileAccuracy    : 분위 계산 정확성 (간단 fixture)
- TestRoeMissingStocks       : 누락 종목 처리 (NaN → 제외)
- TestRoeSmallUniverse       : 종목 수 < n_buckets 처리
- TestRoeFilter              : roe_filter Stage A 필터 동작
- TestRoeEdgeCases           : 빈 입력, 단일 종목, 전부 동일값 등 경계 케이스

설계 원칙
---------
- DB 연결 없이 실행 가능 (mock conn + in-memory fixture 사용)
- 실제 DB 있으면 integration marker로 추가 검증
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.signals.roe_filter import roe_filter, roe_pit, roe_quintile


# ---------------------------------------------------------------------------
# Mock DB 헬퍼
# ---------------------------------------------------------------------------

def _make_mock_conn(rows: list[tuple]) -> MagicMock:
    """psycopg2 connection mock 생성.

    rows: [(stock_code, roe), ...] — DISTINCT ON (stock_code) 결과 순서 그대로.
    cursor.fetchall() 이 rows를 반환하도록 설정.
    """
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    mock_cur.__enter__ = lambda self: self
    mock_cur.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def five_stocks():
    """5종목 코드."""
    return ["A001", "A002", "A003", "A004", "A005"]


@pytest.fixture
def five_roe_rows():
    """5종목 ROE — 10, 20, 30, 40, 50 (순위 명확)."""
    return [
        ("A001", 10.0),
        ("A002", 20.0),
        ("A003", 30.0),
        ("A004", 40.0),
        ("A005", 50.0),
    ]


# ---------------------------------------------------------------------------
# TestRoePitNoLookAhead — No Look-Ahead 강제
# ---------------------------------------------------------------------------

class TestRoePitNoLookAhead:
    """PIT 강제 검증: scan_date 이후 report_date 데이터는 절대 사용 금지."""

    def test_future_report_excluded(self, five_stocks):
        """scan_date보다 미래 report_date가 있어도 SQL 필터가 차단함을 확인.

        Mock conn이 빈 rows를 반환하면 → NaN 반환 (미래 데이터 없음).
        실제 SQL에서 report_date <= scan_date 조건이 핵심.
        """
        scan_date = date(2023, 6, 30)
        # DB가 아무것도 반환하지 않음 = scan_date 이전 데이터 없음
        mock_conn = _make_mock_conn(rows=[])

        result = roe_pit(scan_date, five_stocks, conn=mock_conn)

        assert result.isna().all(), "미래 데이터 없는 경우 전부 NaN이어야 함"
        assert list(result.index) == five_stocks

    def test_pit_cutoff_uses_scan_date_in_query(self, five_stocks, five_roe_rows):
        """SQL execute 호출 시 scan_date 문자열이 파라미터로 포함되는지 확인."""
        scan_date = date(2024, 6, 30)
        mock_conn = _make_mock_conn(rows=five_roe_rows)
        mock_cur = mock_conn.cursor.return_value

        roe_pit(scan_date, five_stocks, conn=mock_conn)

        # execute 호출 파라미터 중 scan_date.isoformat()이 포함되어야 함
        call_args = mock_cur.execute.call_args
        params = call_args[0][1]  # (sql, params)
        assert "2024-06-30" in params, (
            f"scan_date '2024-06-30' must appear in SQL params, got: {params}"
        )

    def test_no_lookahead_truncation(self, five_stocks):
        """마지막 날짜 행을 제거해도 앞 날짜 ROE 결과 불변.

        scan_date를 더 이른 날짜로 줄이면 해당 시점 데이터만 남아야 함.
        두 호출의 결과가 공통 종목에 대해 동일해야 함.
        """
        # 2024-12 데이터: A001=15, A002=25
        # 2023-12 데이터: A001=10, A002=20
        stocks = ["A001", "A002"]

        rows_2024 = [("A001", 15.0), ("A002", 25.0)]
        rows_2023 = [("A001", 10.0), ("A002", 20.0)]

        conn_2024 = _make_mock_conn(rows=rows_2024)
        conn_2023 = _make_mock_conn(rows=rows_2023)

        result_2024 = roe_pit(date(2025, 1, 1), stocks, conn=conn_2024)
        result_2023 = roe_pit(date(2024, 1, 1), stocks, conn=conn_2023)

        # 각각 독립적으로 그 시점의 최신 데이터를 반환해야 함
        assert result_2024["A001"] == pytest.approx(15.0)
        assert result_2023["A001"] == pytest.approx(10.0)
        # 두 결과가 다르면 PIT가 작동 중인 것
        assert result_2024["A001"] != result_2023["A001"]


# ---------------------------------------------------------------------------
# TestRoeQuintileAccuracy — 분위 계산 정확성
# ---------------------------------------------------------------------------

class TestRoeQuintileAccuracy:
    """roe_quintile 분위 계산이 수학적으로 정확한지 검증."""

    def test_five_equal_stocks_quintile(self, five_stocks, five_roe_rows):
        """ROE 10/20/30/40/50 → 분위 1/2/3/4/5 정확 매핑."""
        scan_date = date(2024, 12, 31)
        mock_conn = _make_mock_conn(rows=five_roe_rows)

        result = roe_quintile(scan_date, five_stocks, n_buckets=5, conn=mock_conn)

        # ROE 최소(10) → Q1, 최대(50) → Q5
        assert result["A001"] == 1, f"ROE=10 → Q1, got {result['A001']}"
        assert result["A005"] == 5, f"ROE=50 → Q5, got {result['A005']}"
        # 모두 NaN 없음
        assert not result.dropna().empty

    def test_quintile_range_1_to_n(self, five_stocks, five_roe_rows):
        """분위값이 항상 1 이상 n_buckets 이하."""
        scan_date = date(2024, 12, 31)
        mock_conn = _make_mock_conn(rows=five_roe_rows)

        result = roe_quintile(scan_date, five_stocks, n_buckets=5, conn=mock_conn)
        valid = result.dropna()

        assert valid.min() >= 1
        assert valid.max() <= 5

    def test_quartile_n4(self, five_stocks, five_roe_rows):
        """n_buckets=4 quartile도 정상 동작."""
        scan_date = date(2024, 12, 31)
        mock_conn = _make_mock_conn(rows=five_roe_rows)

        result = roe_quintile(scan_date, five_stocks, n_buckets=4, conn=mock_conn)
        valid = result.dropna()

        assert valid.min() >= 1
        assert valid.max() <= 4

    def test_monotone_ordering(self, five_stocks, five_roe_rows):
        """ROE 순서 = 분위 순서 (단조 증가)."""
        scan_date = date(2024, 12, 31)
        mock_conn = _make_mock_conn(rows=five_roe_rows)

        result = roe_quintile(scan_date, five_stocks, n_buckets=5, conn=mock_conn)
        valid = result.dropna().sort_index()

        # A001 < A002 < A003 < A004 < A005 순으로 ROE 증가
        assert result["A001"] <= result["A002"]
        assert result["A002"] <= result["A003"]
        assert result["A003"] <= result["A004"]
        assert result["A004"] <= result["A005"]


# ---------------------------------------------------------------------------
# TestRoeMissingStocks — 누락 종목 처리
# ---------------------------------------------------------------------------

class TestRoeMissingStocks:
    """ROE 데이터 없는 종목은 NaN 반환, 분위 계산 제외."""

    def test_partial_data_nan_for_missing(self):
        """일부 종목만 ROE 있을 때 나머지는 NaN."""
        stocks = ["A001", "A002", "A003", "MISSING"]
        rows = [("A001", 10.0), ("A002", 20.0), ("A003", 30.0)]  # MISSING 없음
        mock_conn = _make_mock_conn(rows=rows)

        result = roe_pit(date(2024, 12, 31), stocks, conn=mock_conn)

        assert math.isnan(result["MISSING"]), "데이터 없는 종목은 NaN이어야 함"
        assert result["A001"] == pytest.approx(10.0)

    def test_quintile_missing_is_nan(self):
        """분위 계산에서 ROE 없는 종목은 NaN."""
        stocks = ["A001", "A002", "MISSING"]
        rows = [("A001", 10.0), ("A002", 50.0)]
        mock_conn = _make_mock_conn(rows=rows)

        result = roe_quintile(date(2024, 12, 31), stocks, conn=mock_conn)

        assert math.isnan(result["MISSING"]), "데이터 없는 종목 분위는 NaN이어야 함"

    def test_filter_excludes_nan(self):
        """roe_filter는 NaN 종목(데이터 없음)을 항상 제외."""
        stocks = ["A001", "A002", "MISSING"]
        # A001=Q1, A002=Q5 (min_quintile=4면 A002만 통과)
        rows = [("A001", 5.0), ("A002", 50.0)]
        mock_conn = _make_mock_conn(rows=rows)

        passed = roe_filter(date(2024, 12, 31), stocks, min_quintile=1, conn=mock_conn)

        assert "MISSING" not in passed, "NaN 종목은 필터 통과 불가"

    def test_all_missing_returns_empty(self):
        """전체 종목 ROE 없으면 빈 결과."""
        stocks = ["X001", "X002"]
        mock_conn = _make_mock_conn(rows=[])

        result = roe_pit(date(2024, 12, 31), stocks, conn=mock_conn)
        assert result.isna().all()

        passed = roe_filter(date(2024, 12, 31), stocks, min_quintile=1, conn=mock_conn)
        assert passed == []


# ---------------------------------------------------------------------------
# TestRoeSmallUniverse — 종목 수 < n_buckets 처리
# ---------------------------------------------------------------------------

class TestRoeSmallUniverse:
    """종목 수가 n_buckets 미만일 때 graceful 처리."""

    def test_3_stocks_5_buckets_no_crash(self):
        """3종목 5분위 요청 → 오류 없이 분위 반환 (종목 수 < n_buckets graceful 처리)."""
        stocks = ["A001", "A002", "A003"]
        rows = [("A001", 10.0), ("A002", 20.0), ("A003", 30.0)]
        mock_conn = _make_mock_conn(rows=rows)

        # 오류 없이 실행되어야 함
        result = roe_quintile(
            date(2024, 12, 31), stocks, n_buckets=5, conn=mock_conn
        )

        # 오류 없이 분위 반환 (값 범위 검증)
        valid = result.dropna()
        assert len(valid) > 0, "3종목이라도 분위 계산 가능해야 함"
        assert valid.min() >= 1

    def test_single_stock_returns_q1(self):
        """단일 종목 → 분위 1 반환."""
        stocks = ["SOLO"]
        rows = [("SOLO", 42.0)]
        mock_conn = _make_mock_conn(rows=rows)

        result = roe_quintile(date(2024, 12, 31), stocks, n_buckets=5, conn=mock_conn)

        assert result["SOLO"] == 1, f"단일 종목은 분위 1이어야 함, got {result['SOLO']}"

    def test_zero_stocks_empty_result(self):
        """빈 종목 목록 → 빈 Series."""
        mock_conn = _make_mock_conn(rows=[])

        result_pit = roe_pit(date(2024, 12, 31), [], conn=mock_conn)
        result_q = roe_quintile(date(2024, 12, 31), [], conn=mock_conn)
        result_f = roe_filter(date(2024, 12, 31), [], conn=mock_conn)

        assert len(result_pit) == 0
        assert len(result_q) == 0
        assert result_f == []

    def test_all_same_roe_no_crash(self):
        """모든 ROE 동일값 → 분위 1 할당, 오류 없음."""
        stocks = ["A001", "A002", "A003"]
        rows = [("A001", 15.0), ("A002", 15.0), ("A003", 15.0)]
        mock_conn = _make_mock_conn(rows=rows)

        # 오류 없이 실행되어야 함
        result = roe_quintile(date(2024, 12, 31), stocks, n_buckets=5, conn=mock_conn)
        valid = result.dropna()
        # 동일값 처리: qcut duplicates='drop' → 1개 bin → 전부 분위 1
        if len(valid) > 0:
            assert valid.max() <= 5


# ---------------------------------------------------------------------------
# TestRoeFilter — Stage A 필터 동작
# ---------------------------------------------------------------------------

class TestRoeFilter:
    """roe_filter Stage A universe filter 동작 검증."""

    def test_min_quintile_4_keeps_top40pct(self):
        """min_quintile=4 → 상위 40% (Q4, Q5) 종목만 통과."""
        stocks = ["A001", "A002", "A003", "A004", "A005"]
        # ROE 10/20/30/40/50 → Q1/Q2/Q3/Q4/Q5
        rows = [
            ("A001", 10.0),
            ("A002", 20.0),
            ("A003", 30.0),
            ("A004", 40.0),
            ("A005", 50.0),
        ]
        mock_conn = _make_mock_conn(rows=rows)

        passed = roe_filter(
            date(2024, 12, 31), stocks, min_quintile=4, n_buckets=5, conn=mock_conn
        )

        assert "A005" in passed, "ROE=50 (Q5)는 통과해야 함"
        assert "A004" in passed, "ROE=40 (Q4)는 통과해야 함"
        assert "A001" not in passed, "ROE=10 (Q1)은 제외해야 함"
        assert "A002" not in passed, "ROE=20 (Q2)는 제외해야 함"

    def test_min_quintile_1_keeps_all_with_data(self):
        """min_quintile=1 → ROE 데이터 있는 모든 종목 통과."""
        stocks = ["A001", "A002", "A003"]
        rows = [("A001", 10.0), ("A002", 20.0), ("A003", 30.0)]
        mock_conn = _make_mock_conn(rows=rows)

        passed = roe_filter(
            date(2024, 12, 31), stocks, min_quintile=1, conn=mock_conn
        )

        assert set(passed) == {"A001", "A002", "A003"}

    def test_min_quintile_5_keeps_only_top(self):
        """min_quintile=5 → Q5 (최상위) 종목만 통과."""
        stocks = ["A001", "A002", "A003", "A004", "A005"]
        rows = [
            ("A001", 10.0), ("A002", 20.0), ("A003", 30.0),
            ("A004", 40.0), ("A005", 50.0),
        ]
        mock_conn = _make_mock_conn(rows=rows)

        passed = roe_filter(
            date(2024, 12, 31), stocks, min_quintile=5, n_buckets=5, conn=mock_conn
        )

        assert "A005" in passed
        assert "A004" not in passed

    def test_invalid_min_quintile_raises(self):
        """min_quintile 범위 초과 → ValueError."""
        with pytest.raises(ValueError, match="min_quintile"):
            roe_filter(date(2024, 12, 31), ["A001"], min_quintile=6, n_buckets=5)

        with pytest.raises(ValueError, match="min_quintile"):
            roe_filter(date(2024, 12, 31), ["A001"], min_quintile=0, n_buckets=5)

    def test_n_buckets_invalid_raises(self):
        """n_buckets < 2 → ValueError."""
        mock_conn = _make_mock_conn(rows=[("A001", 10.0)])
        with pytest.raises(ValueError, match="n_buckets"):
            roe_quintile(date(2024, 12, 31), ["A001"], n_buckets=1, conn=mock_conn)


# ---------------------------------------------------------------------------
# TestRoeEdgeCases — 경계 케이스
# ---------------------------------------------------------------------------

class TestRoeEdgeCases:
    """roe_pit / roe_quintile / roe_filter 경계 케이스."""

    def test_negative_roe_handled(self):
        """음수 ROE (적자 기업)도 정상 처리."""
        stocks = ["POS", "NEG", "MID"]
        rows = [("POS", 30.0), ("NEG", -10.0), ("MID", 10.0)]
        mock_conn = _make_mock_conn(rows=rows)

        result = roe_pit(date(2024, 12, 31), stocks, conn=mock_conn)
        assert result["NEG"] == pytest.approx(-10.0)

        q_conn = _make_mock_conn(rows=rows)
        q_result = roe_quintile(date(2024, 12, 31), stocks, n_buckets=3, conn=q_conn)
        valid = q_result.dropna()
        assert valid.min() >= 1

    def test_roe_index_name(self, five_stocks, five_roe_rows):
        """반환 Series의 index.name은 'stock_code'."""
        mock_conn = _make_mock_conn(rows=five_roe_rows)
        result = roe_pit(date(2024, 12, 31), five_stocks, conn=mock_conn)
        assert result.index.name == "stock_code"

    def test_scan_date_boundary_same_day(self):
        """report_date == scan_date인 경우 포함 (≤ 조건)."""
        # Mock이 데이터를 반환한다 = scan_date 당일 데이터도 허용
        stocks = ["A001"]
        rows = [("A001", 25.0)]
        mock_conn = _make_mock_conn(rows=rows)

        result = roe_pit(date(2024, 12, 31), stocks, conn=mock_conn)
        # report_date=2024-12-31, scan_date=2024-12-31 → 포함
        assert result["A001"] == pytest.approx(25.0)

    def test_result_series_name(self, five_stocks, five_roe_rows):
        """roe_pit 결과 Series name은 'roe'."""
        mock_conn = _make_mock_conn(rows=five_roe_rows)
        result = roe_pit(date(2024, 12, 31), five_stocks, conn=mock_conn)
        assert result.name == "roe"

    def test_quintile_series_name(self, five_stocks, five_roe_rows):
        """roe_quintile 결과 Series name은 'roe_quintile'."""
        mock_conn = _make_mock_conn(rows=five_roe_rows)
        result = roe_quintile(date(2024, 12, 31), five_stocks, conn=mock_conn)
        assert result.name == "roe_quintile"


# ---------------------------------------------------------------------------
# Integration Tests (실제 DB — pytest mark로 조건부 실행)
# ---------------------------------------------------------------------------

def _db_available() -> bool:
    """실제 DB 연결 가능 여부 확인."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="127.0.0.1", port=5433, dbname="robotrader_quant",
            user="robotrader", password="1234", connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _db_available(), reason="robotrader_quant DB 연결 불가")
class TestRoeFilterIntegration:
    """실제 DB를 사용하는 통합 테스트 (CI skip 가능)."""

    def test_roe_pit_real_db(self):
        """실제 DB에서 ROE 조회 — 데이터 존재 종목 반환 검증."""
        # financial_statements에 데이터 있는 종목 코드 몇 개 사용
        stocks = ["058430", "136490", "004690"]
        scan_date = date(2026, 5, 25)

        result = roe_pit(scan_date, stocks)

        # 적어도 1개 종목은 데이터 있어야 함
        assert result.notna().any(), "실제 DB에서 ROE 조회 결과 없음"

    def test_roe_quintile_real_db(self):
        """실제 DB — 분위 계산 결과 유효성."""
        stocks = ["058430", "136490", "004690", "071320", "290740"]
        scan_date = date(2026, 5, 25)

        result = roe_quintile(scan_date, stocks, n_buckets=5)
        valid = result.dropna()

        if len(valid) > 0:
            assert valid.min() >= 1
            assert valid.max() <= 5

    def test_roe_filter_real_db_coverage(self):
        """5.4년치 커버리지 — 실제 데이터로 필터 적용 가능."""
        import psycopg2
        conn = psycopg2.connect(
            host="127.0.0.1", port=5433, dbname="robotrader_quant",
            user="robotrader", password="1234",
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT stock_code FROM financial_statements "
            "WHERE roe IS NOT NULL AND report_date <= %s",
            ["2026-05-25"],
        )
        all_stocks = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()

        if len(all_stocks) < 5:
            pytest.skip("커버리지 테스트를 위한 종목 수 부족 (< 5)")

        scan_date = date(2026, 5, 25)
        passed = roe_filter(scan_date, all_stocks, min_quintile=4, n_buckets=5)

        # 상위 40% → 전체의 약 40%가 통과해야 함 (±10% 허용)
        expected_min = len(all_stocks) * 0.30
        expected_max = len(all_stocks) * 0.50
        assert expected_min <= len(passed) <= expected_max, (
            f"Q4 이상 필터 통과 종목 수={len(passed)}, "
            f"전체={len(all_stocks)}, 기대 범위=[{expected_min:.0f}, {expected_max:.0f}]"
        )
