"""
P3-4: 성과 리포트 자동 생성 테스트
"""
import sys
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if 'psycopg2' not in sys.modules:
    _mock_pg = MagicMock()
    _mock_pg.extensions = MagicMock()
    _mock_pg.extras = MagicMock()
    _mock_pg.IntegrityError = type('IntegrityError', (Exception,), {})
    sys.modules['psycopg2'] = _mock_pg
    sys.modules['psycopg2.extensions'] = _mock_pg.extensions
    sys.modules['psycopg2.extras'] = _mock_pg.extras

from core.report_generator import generate_daily_report, generate_telegram_report, _calc_pnl_stats


class TestReportGenerator(unittest.TestCase):

    def _sample_trades(self):
        return [
            {'order_id': 'O1', 'stock_code': '005930', 'side': 'buy',
             'quantity': 10, 'price': 70000, 'amount': 700000,
             'timestamp': datetime(2026, 2, 10, 9, 5)},
            {'order_id': 'O2', 'stock_code': '005930', 'side': 'sell',
             'quantity': 10, 'price': 72100, 'amount': 721000,
             'timestamp': datetime(2026, 2, 10, 11, 0)},
            {'order_id': 'O3', 'stock_code': '000660', 'side': 'buy',
             'quantity': 5, 'price': 150000, 'amount': 750000,
             'timestamp': datetime(2026, 2, 10, 9, 10)},
            {'order_id': 'O4', 'stock_code': '000660', 'side': 'sell',
             'quantity': 5, 'price': 135000, 'amount': 675000,
             'timestamp': datetime(2026, 2, 10, 14, 0)},
        ]

    def _sample_positions(self):
        return [
            {'stock_code': '035420', 'stock_name': 'NAVER', 'quantity': 3,
             'avg_price': 200000, 'current_price': 200100,
             'profit_loss': 300, 'profit_loss_rate': 0.0005},
        ]

    def _sample_fund_status(self):
        return {
            'total_funds': 10_000_000,
            'available_funds': 8_400_000,
            'reserved_funds': 0,
            'invested_funds': 600_300,
            'utilization_rate': 0.06,
            'position_count': 1,
        }

    def test_generate_daily_report_contains_sections(self):
        """리포트에 필수 섹션 포함"""
        report = generate_daily_report(
            self._sample_trades(), self._sample_positions(),
            self._sample_fund_status(), datetime(2026, 2, 10)
        )
        self.assertIn('일일 매매 리포트', report)
        self.assertIn('매매 요약', report)
        self.assertIn('손익 현황', report)
        self.assertIn('매매 내역', report)
        self.assertIn('보유종목 현황', report)
        self.assertIn('자금 현황', report)

    def test_trade_count(self):
        """거래 건수 표시"""
        report = generate_daily_report(
            self._sample_trades(), [], self._sample_fund_status()
        )
        self.assertIn('4건', report)
        self.assertIn('매수 2', report)
        self.assertIn('매도 2', report)

    def test_pnl_stats(self):
        """손익 통계 계산"""
        stats = _calc_pnl_stats(self._sample_trades())
        # 삼성: (72100-70000)*10 = +21000
        # SK: (135000-150000)*5 = -75000
        self.assertAlmostEqual(stats['realized_pnl'], 21000 - 75000)
        self.assertEqual(stats['wins'], 1)
        self.assertEqual(stats['losses'], 1)
        self.assertAlmostEqual(stats['win_rate'], 50.0)

    def test_empty_trades(self):
        """거래 없는 경우"""
        report = generate_daily_report([], [], self._sample_fund_status())
        self.assertIn('0건', report)
        self.assertIn('보유종목 없음', report)

    def test_positions_display(self):
        """보유종목 표시"""
        report = generate_daily_report(
            [], self._sample_positions(), self._sample_fund_status()
        )
        self.assertIn('NAVER', report)
        self.assertIn('035420', report)
        self.assertIn('200,000', report)

    def test_fund_status_display(self):
        """자금 현황 표시"""
        report = generate_daily_report(
            [], [], self._sample_fund_status()
        )
        self.assertIn('10,000,000', report)
        self.assertIn('8,400,000', report)

    def test_telegram_report(self):
        """텔레그램 리포트 생성"""
        report = generate_telegram_report(
            self._sample_trades(), self._sample_positions(),
            self._sample_fund_status(), datetime(2026, 2, 10)
        )
        self.assertIn('02/10', report)
        self.assertIn('거래 4건', report)
        self.assertIn('실현손익', report)
        self.assertIn('승률', report)
        # 텔레그램 4096자 제한
        self.assertLessEqual(len(report), 4096)

    def test_telegram_report_short(self):
        """텔레그램 리포트가 충분히 짧은지"""
        report = generate_telegram_report(
            self._sample_trades(), self._sample_positions(),
            self._sample_fund_status()
        )
        self.assertLess(len(report), 500)

    def test_no_positions_in_telegram(self):
        """보유종목 없을 때 텔레그램 리포트"""
        report = generate_telegram_report(
            self._sample_trades(), [], self._sample_fund_status()
        )
        self.assertNotIn('보유', report)  # 보유 종목 라인 미포함


class TestPnlStatsEdgeCases(unittest.TestCase):

    def test_only_buys(self):
        """매수만 있는 경우"""
        trades = [
            {'stock_code': '005930', 'side': 'buy', 'quantity': 10, 'price': 70000},
        ]
        stats = _calc_pnl_stats(trades)
        self.assertEqual(stats['realized_pnl'], 0)
        self.assertEqual(stats['win_rate'], 0)

    def test_multiple_sells_one_buy(self):
        """1회 매수, 2회 분할 매도"""
        trades = [
            {'stock_code': '005930', 'side': 'buy', 'quantity': 100, 'price': 70000},
            {'stock_code': '005930', 'side': 'sell', 'quantity': 50, 'price': 72000},
            {'stock_code': '005930', 'side': 'sell', 'quantity': 50, 'price': 68000},
        ]
        stats = _calc_pnl_stats(trades)
        # (72000-70000)*50 + (68000-70000)*50 = 100000 - 100000 = 0
        self.assertAlmostEqual(stats['realized_pnl'], 0)

    def test_fifo_matching(self):
        """FIFO 매칭 검증"""
        trades = [
            {'stock_code': '005930', 'side': 'buy', 'quantity': 10, 'price': 70000},
            {'stock_code': '005930', 'side': 'buy', 'quantity': 10, 'price': 72000},
            {'stock_code': '005930', 'side': 'sell', 'quantity': 15, 'price': 73000},
        ]
        stats = _calc_pnl_stats(trades)
        # FIFO: 10@70000 → (73000-70000)*10=30000, 5@72000 → (73000-72000)*5=5000
        self.assertAlmostEqual(stats['realized_pnl'], 35000)


if __name__ == '__main__':
    unittest.main()
