"""모멘텀 스크리너 단위 테스트"""
import pytest
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.stock_screener import MomentumScreener


class TestMomentumScreener:
    def setup_method(self):
        self.screener = MomentumScreener(min_close=1000, min_trading_amount=100_000_000)

    @patch("scripts.stock_screener.MomentumScreener._fetch_daily_closes")
    @patch("scripts.stock_screener.MomentumScreener._fetch_all_stocks")
    def test_5day_consecutive_up(self, mock_fetch_all, mock_fetch_closes):
        """5일 연속 상승 종목 감지"""
        mock_fetch_all.return_value = [
            {"code": "005930", "name": "삼성전자", "close": 72000,
             "trading_amount": 500_000_000_000, "is_rising": True},
            {"code": "000660", "name": "SK하이닉스", "close": 180000,
             "trading_amount": 300_000_000_000, "is_rising": True},
        ]

        def closes_for(code, days=7):
            if code == "005930":
                # 6일 연속 상승
                return [("d1", 60000), ("d2", 62000), ("d3", 64000),
                        ("d4", 66000), ("d5", 68000), ("d6", 70000), ("d7", 72000)]
            else:
                # 중간에 하락 있음 → 3일 연속만
                return [("d1", 170000), ("d2", 175000), ("d3", 172000),
                        ("d4", 168000), ("d5", 173000), ("d6", 176000), ("d7", 180000)]

        mock_fetch_closes.side_effect = closes_for

        results = self.screener.scan(date="20260209", consecutive_days=5)
        codes = [r["code"] for r in results]
        assert "005930" in codes
        assert "000660" not in codes

    @patch("scripts.stock_screener.MomentumScreener._fetch_all_stocks")
    def test_filter_penny_stock(self, mock_fetch_all):
        """동전주 필터링 (1단계에서 걸러짐)"""
        mock_fetch_all.return_value = [
            {"code": "999999", "name": "동전주", "close": 500,
             "trading_amount": 500_000_000, "is_rising": True},
        ]
        results = self.screener.scan(date="20260209", consecutive_days=5)
        assert len(results) == 0

    @patch("scripts.stock_screener.MomentumScreener._fetch_all_stocks")
    def test_filter_low_amount(self, mock_fetch_all):
        """거래대금 미달 필터링"""
        mock_fetch_all.return_value = [
            {"code": "005930", "name": "테스트", "close": 50000,
             "trading_amount": 50_000_000, "is_rising": True},
        ]
        results = self.screener.scan(date="20260209", consecutive_days=5)
        assert len(results) == 0

    @patch("scripts.stock_screener.MomentumScreener._fetch_all_stocks")
    def test_filter_not_rising(self, mock_fetch_all):
        """당일 하락 종목 필터링"""
        mock_fetch_all.return_value = [
            {"code": "005930", "name": "테스트", "close": 50000,
             "trading_amount": 500_000_000_000, "is_rising": False},
        ]
        results = self.screener.scan(date="20260209", consecutive_days=5)
        assert len(results) == 0

    def test_format_telegram_message(self):
        """텔레그램 메시지 포맷"""
        results = [{
            "code": "005930", "name": "삼성전자", "close": 72000,
            "volume": 1000000, "trading_amount": 320_000_000_000,
            "consecutive_up_days": 5,
        }]
        msg = self.screener.format_telegram_message(results, "20260209", 5)
        assert "삼성전자" in msg
        assert "005930" in msg
        assert "2026-02-09" in msg
        assert "1종목" in msg

    def test_format_amount(self):
        assert MomentumScreener._format_amount(320_000_000_000) == "3,200억"
        assert MomentumScreener._format_amount(1_500_000_000_000_000) == "1500.0조"
        assert MomentumScreener._format_amount(50_000_000) == "50,000,000원"

    def test_format_empty_results(self):
        msg = self.screener.format_telegram_message([], "20260209", 5)
        assert "조건에 맞는 종목이 없습니다" in msg
