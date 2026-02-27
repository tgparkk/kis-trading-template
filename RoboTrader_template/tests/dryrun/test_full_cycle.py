"""
P3-2: 장 시작~마감 전체 사이클 시뮬레이션

시나리오: 09:00 장시작 → 후보선정 → 데이터수집 → 매수신호 → 주문 → 체결
→ 모니터링 → 익절/손절 → 15:20 EOD청산 → 15:30 장마감

MockMarketData로 시간별 가격 데이터 주입
각 MarketPhase 전환 검증
FundManager 자금 흐름 추적 (초기→예약→투자→회수)
"""
import sys
import unittest
from pathlib import Path
from datetime import datetime, time, timedelta
from unittest.mock import patch, MagicMock

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# psycopg2 mock (OpenSSL 환경 문제 방지)
if 'psycopg2' not in sys.modules:
    _mock_pg = MagicMock()
    _mock_pg.extensions = MagicMock()
    _mock_pg.extras = MagicMock()
    _mock_pg.IntegrityError = type('IntegrityError', (Exception,), {})
    sys.modules['psycopg2'] = _mock_pg
    sys.modules['psycopg2.extensions'] = _mock_pg.extensions
    sys.modules['psycopg2.extras'] = _mock_pg.extras

import pytz

from tests.dryrun.dryrun_broker import DryRunBroker, DryRunConfig
from config.market_hours import MarketPhase, MarketHours
from core.fund_manager import FundManager
from core.models import (
    TradingStock, StockState, Order, OrderType, OrderStatus,
    TradingConfig, Position
)

KST = pytz.timezone('Asia/Seoul')


# ============================================================================
# MockMarketData: 시간별 가격 시나리오
# ============================================================================

class MockMarketData:
    """시간별 가격 데이터 주입기"""

    def __init__(self):
        # 종목별 시간→가격 매핑
        # 삼성전자: 상승 후 하락 (익절 시나리오)
        # SK하이닉스: 하락 (손절 시나리오)
        # NAVER: 횡보 (EOD 청산 시나리오)
        self.price_timeline = {
            '005930': {  # 삼성전자: 70000 → 72100(+3%) → 71000
                time(9, 0): 70000,
                time(9, 30): 70500,
                time(10, 0): 71000,
                time(10, 30): 71500,
                time(11, 0): 72100,   # +3% → 익절 트리거
                time(13, 0): 71000,
                time(15, 0): 71000,
                time(15, 20): 71000,
            },
            '000660': {  # SK하이닉스: 150000 → 135000(-10%)
                time(9, 0): 150000,
                time(9, 30): 148000,
                time(10, 0): 145000,
                time(10, 30): 142000,
                time(11, 0): 140000,
                time(13, 0): 137000,
                time(14, 0): 135000,  # -10% → 손절 트리거
                time(15, 0): 136000,
                time(15, 20): 136000,
            },
            '035420': {  # NAVER: 횡보
                time(9, 0): 200000,
                time(9, 30): 200500,
                time(10, 0): 199500,
                time(10, 30): 200000,
                time(11, 0): 200200,
                time(13, 0): 199800,
                time(15, 0): 200000,
                time(15, 20): 200100,
            },
        }

    def get_price_at(self, stock_code: str, t: time) -> float:
        """특정 시점의 가격 반환 (가장 가까운 과거 시점)"""
        timeline = self.price_timeline.get(stock_code, {})
        if not timeline:
            return 0.0
        # t 이하인 가장 최신 시점
        candidates = [(k, v) for k, v in timeline.items() if k <= t]
        if not candidates:
            return list(timeline.values())[0]
        candidates.sort(key=lambda x: x[0])
        return candidates[-1][1]


# ============================================================================
# 테스트
# ============================================================================

class TestFullDayCycle(unittest.TestCase):
    """장 시작~마감 전체 사이클 시뮬레이션"""

    def setUp(self):
        self.broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        self.market_data = MockMarketData()
        self.fund_manager = FundManager(initial_funds=10_000_000, max_position_count=5)

    # ----------------------------------------------------------------
    # Phase 1: MarketPhase 전환 검증
    # ----------------------------------------------------------------

    def test_market_phases_through_day(self):
        """장 시작~마감 동안 MarketPhase가 올바르게 전환되는지"""
        today = datetime(2026, 2, 10)  # 화요일
        test_cases = [
            (time(7, 0), MarketPhase.PRE_MARKET),
            (time(8, 30), MarketPhase.PRE_AUCTION),
            (time(8, 59), MarketPhase.PRE_AUCTION),
            (time(9, 0), MarketPhase.OPENING_PROTECTION),
            (time(9, 4), MarketPhase.OPENING_PROTECTION),
            (time(9, 5), MarketPhase.MARKET_OPEN),
            (time(12, 0), MarketPhase.MARKET_OPEN),
            (time(15, 19), MarketPhase.MARKET_OPEN),
            (time(15, 20), MarketPhase.CLOSING_CUTOFF),
            (time(15, 29), MarketPhase.CLOSING_CUTOFF),
            (time(15, 30), MarketPhase.CLOSING_CUTOFF),  # 15:30 is within close
            (time(15, 31), MarketPhase.POST_MARKET),
        ]

        for t, expected_phase in test_cases:
            dt = KST.localize(datetime.combine(today, t))
            phase = MarketHours.get_market_phase('KRX', dt)
            self.assertEqual(phase, expected_phase,
                             f"{t} should be {expected_phase.value}, got {phase.value}")

    # ----------------------------------------------------------------
    # Phase 2: 후보 선정 → 데이터 수집 → 매수 신호
    # ----------------------------------------------------------------

    def test_candidate_selection_and_data_collection(self):
        """후보 선정 후 가격 데이터 수집"""
        candidates = ['005930', '000660', '035420']
        t = time(9, 5)

        for code in candidates:
            price = self.market_data.get_price_at(code, t)
            self.broker.set_price(code, price)
            self.assertGreater(price, 0, f"{code} 가격이 0보다 커야 함")

        # 브로커에서 가격 조회
        for code in candidates:
            p = self.broker.get_current_price(code)
            self.assertIsNotNone(p)

    # ----------------------------------------------------------------
    # Phase 3: 매수 주문 → 체결 → FundManager 자금 흐름
    # ----------------------------------------------------------------

    def test_buy_order_and_fund_flow(self):
        """매수 주문 → 체결 → 자금 예약 → 투자 확정"""
        stock_code = '005930'
        buy_price = 70000
        quantity = 10
        self.broker.set_price(stock_code, buy_price)

        # 1) 자금 예약
        amount = buy_price * quantity  # 700,000
        reserved = self.fund_manager.reserve_funds("ORD-001", amount)
        self.assertTrue(reserved)

        status = self.fund_manager.get_status()
        self.assertEqual(status['reserved_funds'], 700000)
        self.assertEqual(status['available_funds'], 10_000_000 - 700000)

        # 2) 주문 실행
        result = self.broker.place_buy_order(stock_code, quantity, buy_price)
        self.assertTrue(result['success'])

        # 3) 체결 확인 → 투자 확정 (수수료 포함)
        from config.constants import COMMISSION_RATE
        actual_amount = quantity * buy_price
        self.fund_manager.confirm_order("ORD-001", actual_amount)

        commission = actual_amount * COMMISSION_RATE
        total_cost = actual_amount + commission

        status = self.fund_manager.get_status()
        self.assertEqual(status['reserved_funds'], 0)
        self.assertAlmostEqual(status['invested_funds'], total_cost, places=0)
        self.assertAlmostEqual(status['available_funds'], 10_000_000 - total_cost, places=0)

        # 4) 보유 확인
        holdings = self.broker.get_holdings()
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]['stock_code'], stock_code)
        self.assertEqual(holdings[0]['quantity'], quantity)

    # ----------------------------------------------------------------
    # Phase 4: 모니터링 → 익절
    # ----------------------------------------------------------------

    def test_take_profit_scenario(self):
        """삼성전자: 3% 상승 시 익절"""
        stock_code = '005930'
        buy_price = 70000
        quantity = 10

        self.broker.set_price(stock_code, buy_price)
        self.broker.place_buy_order(stock_code, quantity, buy_price)

        # 가격 상승 시뮬레이션: 72100 (+3%)
        tp_price = self.market_data.get_price_at(stock_code, time(11, 0))
        self.broker.set_price(stock_code, tp_price)

        # P&L 체크
        holdings = self.broker.get_holdings()
        pnl_rate = holdings[0]['profit_loss_rate']
        self.assertGreaterEqual(pnl_rate, 0.03)  # +3% 이상

        # 익절 매도
        result = self.broker.place_sell_order(stock_code, quantity, int(tp_price))
        self.assertTrue(result['success'])

        # 포지션 청산 확인
        self.assertEqual(len(self.broker.get_holdings()), 0)

    # ----------------------------------------------------------------
    # Phase 5: 모니터링 → 손절
    # ----------------------------------------------------------------

    def test_stop_loss_scenario(self):
        """SK하이닉스: 10% 하락 시 손절"""
        stock_code = '000660'
        buy_price = 150000
        quantity = 5

        self.broker.set_price(stock_code, buy_price)
        self.broker.place_buy_order(stock_code, quantity, buy_price)

        # 가격 하락: 135000 (-10%)
        sl_price = self.market_data.get_price_at(stock_code, time(14, 0))
        self.broker.set_price(stock_code, sl_price)

        holdings = self.broker.get_holdings()
        pnl_rate = holdings[0]['profit_loss_rate']
        self.assertLessEqual(pnl_rate, -0.09)  # -10% 수준

        # 손절 매도
        result = self.broker.place_sell_order(stock_code, quantity, int(sl_price))
        self.assertTrue(result['success'])
        self.assertEqual(len(self.broker.get_holdings()), 0)

    # ----------------------------------------------------------------
    # Phase 6: EOD 청산 (15:20)
    # ----------------------------------------------------------------

    def test_eod_liquidation(self):
        """NAVER: EOD 시간(15:20)에 강제 청산"""
        stock_code = '035420'
        buy_price = 200000
        quantity = 3

        self.broker.set_price(stock_code, buy_price)
        self.broker.place_buy_order(stock_code, quantity, buy_price)

        # 15:20 가격
        eod_price = self.market_data.get_price_at(stock_code, time(15, 20))
        self.broker.set_price(stock_code, eod_price)

        # EOD 시간 확인
        dt_eod = KST.localize(datetime(2026, 2, 10, 15, 20))
        self.assertTrue(MarketHours.is_eod_liquidation_time('KRX', dt_eod))

        # EOD 청산
        result = self.broker.place_sell_order(stock_code, quantity, int(eod_price))
        self.assertTrue(result['success'])
        self.assertEqual(len(self.broker.get_holdings()), 0)

    # ----------------------------------------------------------------
    # Phase 7: 전체 사이클 통합
    # ----------------------------------------------------------------

    def test_full_day_cycle_integration(self):
        """전체 장 운영 사이클 통합 테스트"""
        fm = self.fund_manager
        broker = self.broker
        md = self.market_data

        # === 09:05 장 시작 → 후보 선정 ===
        candidates = {
            '005930': {'name': '삼성전자', 'qty': 10},
            '000660': {'name': 'SK하이닉스', 'qty': 5},
            '035420': {'name': 'NAVER', 'qty': 3},
        }

        t_open = time(9, 5)
        for code, info in candidates.items():
            price = md.get_price_at(code, t_open)
            broker.set_price(code, price)

        # === 09:05 매수 주문 ===
        order_ids = {}
        for code, info in candidates.items():
            price = broker.get_current_price(code)
            amount = price * info['qty']
            oid = f"ORD-{code}"

            ok = fm.reserve_funds(oid, amount)
            self.assertTrue(ok, f"{code} 자금 예약 실패")

            result = broker.place_buy_order(code, info['qty'], int(price))
            self.assertTrue(result['success'], f"{code} 매수 실패")

            fm.confirm_order(oid, amount)
            fm.add_position(code)
            order_ids[code] = oid

        # 3종목 보유 확인
        self.assertEqual(len(broker.get_holdings()), 3)
        status = fm.get_status()
        self.assertEqual(status['reserved_funds'], 0)
        self.assertGreater(status['invested_funds'], 0)

        initial_invested = status['invested_funds']
        initial_available = status['available_funds']

        # === 11:00 삼성전자 익절 (+3%) ===
        tp_price = md.get_price_at('005930', time(11, 0))
        broker.set_price('005930', tp_price)

        result = broker.place_sell_order('005930', 10, int(tp_price))
        self.assertTrue(result['success'])

        sell_proceeds = 10 * tp_price
        buy_cost = 10 * 70000
        fm.release_investment(buy_cost, '005930')
        fm.remove_position('005930')

        # 2종목 남음
        self.assertEqual(len(broker.get_holdings()), 2)

        # === 14:00 SK하이닉스 손절 (-10%) ===
        sl_price = md.get_price_at('000660', time(14, 0))
        broker.set_price('000660', sl_price)

        result = broker.place_sell_order('000660', 5, int(sl_price))
        self.assertTrue(result['success'])

        buy_cost_660 = 5 * 150000
        fm.release_investment(buy_cost_660, '000660')
        fm.remove_position('000660')

        self.assertEqual(len(broker.get_holdings()), 1)

        # === 15:20 NAVER EOD 청산 ===
        eod_price = md.get_price_at('035420', time(15, 20))
        broker.set_price('035420', eod_price)

        result = broker.place_sell_order('035420', 3, int(eod_price))
        self.assertTrue(result['success'])

        buy_cost_naver = 3 * 200000
        fm.release_investment(buy_cost_naver, '035420')
        fm.remove_position('035420')

        # === 15:30 장 마감 — 포지션 0 ===
        self.assertEqual(len(broker.get_holdings()), 0)
        final = fm.get_status()
        # invested_funds에 소액 수수료 잔여 가능 (각 종목 수수료 합계)
        self.assertAlmostEqual(final['invested_funds'], 0, delta=500)
        self.assertEqual(final['reserved_funds'], 0)
        self.assertEqual(final['position_count'], 0)

        # 체결 내역 확인 (매수3 + 매도3 = 6건)
        trades = broker.get_trades()
        self.assertEqual(len(trades), 6)
        buys = [t for t in trades if t['side'] == 'buy']
        sells = [t for t in trades if t['side'] == 'sell']
        self.assertEqual(len(buys), 3)
        self.assertEqual(len(sells), 3)

    # ----------------------------------------------------------------
    # Phase 8: FundManager 자금 정합성
    # ----------------------------------------------------------------

    def test_fund_manager_consistency(self):
        """자금 total = available + reserved + invested 일관성"""
        fm = self.fund_manager

        # 초기
        s = fm.get_status()
        self.assertAlmostEqual(
            s['total_funds'],
            s['available_funds'] + s['reserved_funds'] + s['invested_funds'],
            places=0
        )

        # 예약
        fm.reserve_funds("T1", 1_000_000)
        s = fm.get_status()
        self.assertAlmostEqual(
            s['total_funds'],
            s['available_funds'] + s['reserved_funds'] + s['invested_funds'],
            places=0
        )

        # 확정
        fm.confirm_order("T1", 1_000_000)
        s = fm.get_status()
        self.assertAlmostEqual(
            s['total_funds'],
            s['available_funds'] + s['reserved_funds'] + s['invested_funds'],
            places=0
        )

        # 회수 (수수료 잔여분이 invested에 남을 수 있음)
        fm.release_investment(1_000_000)
        s = fm.get_status()
        self.assertAlmostEqual(
            s['total_funds'],
            s['available_funds'] + s['reserved_funds'] + s['invested_funds'],
            places=0
        )
        # 수수료 잔여분만큼 available이 total보다 약간 적을 수 있음
        self.assertAlmostEqual(s['available_funds'], 10_000_000, delta=500)

    # ----------------------------------------------------------------
    # 매수 차단 시간대 검증
    # ----------------------------------------------------------------

    def test_buy_blocked_during_cutoff(self):
        """15:20 이후 신규 매수 차단"""
        dt = KST.localize(datetime(2026, 2, 10, 15, 21))
        self.assertTrue(MarketHours.is_new_buy_blocked('KRX', dt))

    def test_buy_allowed_during_open(self):
        """09:05~12:00 매수 허용"""
        dt = KST.localize(datetime(2026, 2, 10, 10, 0))
        self.assertFalse(MarketHours.is_new_buy_blocked('KRX', dt))


class TestMockMarketData(unittest.TestCase):
    """MockMarketData 가격 보간 테스트"""

    def setUp(self):
        self.md = MockMarketData()

    def test_exact_time_price(self):
        """정확한 시점의 가격"""
        self.assertEqual(self.md.get_price_at('005930', time(9, 0)), 70000)
        self.assertEqual(self.md.get_price_at('005930', time(11, 0)), 72100)

    def test_between_time_price(self):
        """시점 사이 가격 (가장 가까운 과거)"""
        price = self.md.get_price_at('005930', time(9, 15))
        self.assertEqual(price, 70000)  # 09:00 가격

    def test_unknown_stock(self):
        """미등록 종목"""
        self.assertEqual(self.md.get_price_at('999999', time(9, 0)), 0.0)


if __name__ == '__main__':
    unittest.main()
