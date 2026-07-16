"""다owner 동일종목: 매도가 실소유 전략에 귀속되는지 검증.

전략별 완전독립 포지션(2026-06-16 B안) 설계상 **같은 종목을 여러 전략이 동시
보유하는 것은 허용**된다(`core/trading/stock_state_manager.py` 슬롯 기반).
그러나 VirtualTradingManager._position_owner 가 stock_code 만으로 키잉되어
다owner 동일종목을 표현하지 못했고, 매도 시 `strategy = owner` 오버라이드가
호출자의 올바른 per-slot 전략을 stock_code 전역 맵 값으로 덮어썼다.

피해:
- DB virtual_trading_records.strategy 라벨 오염
- 잘못된 전략의 _strategy_balances 에 매도대금 입금 / _strategy_invested 차감
  / _strategy_positions 에서 미보유 종목 제거
- restore_strategy_ledger_from_records 가 오염된 strategy 컬럼으로 자본을
  재계산하므로 재기동마다 영구 오귀속 + get_max_quantity 사이징 왜곡

두 진입점 모두 결함:
- execute_virtual_buy (line 487): _position_owner[code] = strategy (last-call-wins)
- restore_strategy_ledger_from_records (line 338): 동일 (DESC 입력 → last-write-wins)
"""
import pytest
from unittest.mock import Mock, patch

from config.constants import (
    COMMISSION_RATE, SECURITIES_TAX_RATE, VIRTUAL_CAPITAL_PER_STRATEGY,
)

INITIAL = VIRTUAL_CAPITAL_PER_STRATEGY
CODE = '005930'


def _expected_cash(initial, buy_gross, sell_gross):
    """재구성 cash 식 (구현과 동일 선형식)."""
    return (
        initial
        - buy_gross * (1.0 + COMMISSION_RATE)
        + sell_gross * (1.0 - COMMISSION_RATE - SECURITIES_TAX_RATE)
    )


def _net_received(price, quantity):
    gross = price * quantity
    return gross * (1.0 - COMMISSION_RATE - SECURITIES_TAX_RATE)


def _make_vtm_capturing_db():
    """save_virtual_buy/sell 인자를 캡처하는 mock DB를 가진 VTM."""
    with patch('core.virtual_trading_manager.setup_logger'):
        from core.virtual_trading_manager import VirtualTradingManager
        vtm = VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)

    db = Mock()
    captured = {'buy': [], 'sell': []}
    counter = {'n': 0}

    def _save_buy(**kwargs):
        counter['n'] += 1
        captured['buy'].append(kwargs)
        return counter['n']

    def _save_sell(**kwargs):
        captured['sell'].append(kwargs)
        return True

    db.save_virtual_buy.side_effect = _save_buy
    db.save_virtual_sell.side_effect = _save_sell
    vtm.db_manager = db
    return vtm, captured


# ---------------------------------------------------------------------------
# (a) 복원 경로: A가 T1, B가 T2>T1 에 같은 종목 매수 → 재기동 복원(DESC) → B 매도
# ---------------------------------------------------------------------------

class TestRestoredMultiOwnerSell:
    """DB 복원 입력은 `ORDER BY b.timestamp DESC` (db/repositories/trading.py:383).

    즉 나중에 산 B가 먼저, 먼저 산 A가 마지막에 순회되어 stock_code 단일 맵에서는
    A가 last-write-wins 로 승리한다 → B의 매도가 A에 귀속되는 오염.
    """

    def _restored(self):
        vtm, captured = _make_vtm_capturing_db()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        vtm.allocate_strategy_capital("stratB", INITIAL)

        sums = {
            'stratA': {'buy_gross': 100_000.0 * 10, 'sell_gross': 0.0},
            'stratB': {'buy_gross': 120_000.0 * 5, 'sell_gross': 0.0},
        }
        # DESC 순서: 나중 매수(B, rid=20)가 먼저, 먼저 매수(A, rid=10)가 나중
        positions = [
            {'stock_code': CODE, 'strategy': 'stratB', 'quantity': 5,
             'buy_price': 120_000.0, 'buy_record_id': 20},
            {'stock_code': CODE, 'strategy': 'stratA', 'quantity': 10,
             'buy_price': 100_000.0, 'buy_record_id': 10},
        ]
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, positions)
        return vtm, captured

    def test_restore_keeps_both_owners(self):
        """복원 후 두 전략 모두 해당 종목을 보유하고 있어야 한다."""
        vtm, _ = self._restored()
        assert vtm.get_strategy_positions("stratA") == [CODE]
        assert vtm.get_strategy_positions("stratB") == [CODE]

    def test_sell_by_second_buyer_records_own_strategy(self):
        """B가 매도하면 DB 기록 strategy 는 stratB 여야 한다 (현재는 stratA 오염)."""
        vtm, captured = self._restored()

        ok = vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=130_000, quantity=5, strategy='stratB',
            reason='매도', buy_record_id=20,
        )
        assert ok is True
        assert captured['sell'][-1]['strategy'] == 'stratB'

    def test_sell_by_second_buyer_credits_own_balance(self):
        """매도대금은 stratB 에 입금되고 stratA 잔고는 불변이어야 한다."""
        vtm, _ = self._restored()
        a_before = vtm.get_strategy_balance("stratA")
        b_before = vtm.get_strategy_balance("stratB")

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=130_000, quantity=5, strategy='stratB',
            reason='매도', buy_record_id=20,
        )

        assert vtm.get_strategy_balance("stratB") == pytest.approx(
            b_before + _net_received(130_000, 5))
        assert vtm.get_strategy_balance("stratA") == pytest.approx(a_before)

    def test_sell_by_second_buyer_leaves_first_buyer_position_intact(self):
        """stratA 의 보유 종목은 제거되면 안 되고, stratB 의 것만 빠져야 한다."""
        vtm, _ = self._restored()

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=130_000, quantity=5, strategy='stratB',
            reason='매도', buy_record_id=20,
        )

        assert vtm.get_strategy_positions("stratA") == [CODE]
        assert vtm.get_strategy_positions("stratB") == []

    def test_sell_by_second_buyer_leaves_first_buyer_invested_intact(self):
        """stratA 의 invested 는 차감되면 안 된다."""
        vtm, _ = self._restored()
        a_invested_before = vtm._strategy_invested["stratA"]

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=130_000, quantity=5, strategy='stratB',
            reason='매도', buy_record_id=20,
        )

        assert vtm._strategy_invested["stratA"] == pytest.approx(a_invested_before)
        assert vtm._strategy_invested["stratB"] == pytest.approx(0.0)

    def test_first_buyer_can_still_sell_afterwards(self):
        """B 매도 후에도 A의 매도가 A에게 정상 귀속되어야 한다 (소유권 유실 없음)."""
        vtm, captured = self._restored()

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=130_000, quantity=5, strategy='stratB',
            reason='매도', buy_record_id=20,
        )
        a_before = vtm.get_strategy_balance("stratA")

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=105_000, quantity=10, strategy='stratA',
            reason='매도', buy_record_id=10,
        )

        assert captured['sell'][-1]['strategy'] == 'stratA'
        assert vtm.get_strategy_balance("stratA") == pytest.approx(
            a_before + _net_received(105_000, 10))
        assert vtm.get_strategy_positions("stratA") == []


# ---------------------------------------------------------------------------
# (b) 무재기동 동일세션: A→B 순 매수 후 A가 매도
# ---------------------------------------------------------------------------

class TestSameSessionMultiOwnerSell:
    """execute_virtual_buy(line 487) 의 last-call-wins 로 이 변형에서는
    반대편(먼저 산 A)이 피해자가 된다. 두 진입점 모두 고쳐야 한다."""

    def _bought(self):
        vtm, captured = _make_vtm_capturing_db()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        vtm.allocate_strategy_capital("stratB", INITIAL)

        rid_a = vtm.execute_virtual_buy(
            stock_code=CODE, stock_name='삼성전자',
            price=100_000, quantity=10, strategy='stratA', reason='매수',
        )
        rid_b = vtm.execute_virtual_buy(
            stock_code=CODE, stock_name='삼성전자',
            price=120_000, quantity=5, strategy='stratB', reason='매수',
        )
        assert rid_a is not None and rid_b is not None and rid_a != rid_b
        return vtm, captured, rid_a, rid_b

    def test_both_strategies_hold_after_buys(self):
        vtm, _, _, _ = self._bought()
        assert vtm.get_strategy_positions("stratA") == [CODE]
        assert vtm.get_strategy_positions("stratB") == [CODE]

    def test_sell_by_first_buyer_records_own_strategy(self):
        """A가 매도하면 DB 기록 strategy 는 stratA 여야 한다 (현재는 stratB 오염)."""
        vtm, captured, rid_a, _ = self._bought()

        ok = vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=110_000, quantity=10, strategy='stratA',
            reason='매도', buy_record_id=rid_a,
        )
        assert ok is True
        assert captured['sell'][-1]['strategy'] == 'stratA'

    def test_sell_by_first_buyer_credits_own_balance(self):
        vtm, _, rid_a, _ = self._bought()
        a_before = vtm.get_strategy_balance("stratA")
        b_before = vtm.get_strategy_balance("stratB")

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=110_000, quantity=10, strategy='stratA',
            reason='매도', buy_record_id=rid_a,
        )

        assert vtm.get_strategy_balance("stratA") == pytest.approx(
            a_before + _net_received(110_000, 10))
        assert vtm.get_strategy_balance("stratB") == pytest.approx(b_before)

    def test_sell_by_first_buyer_leaves_second_buyer_position_intact(self):
        vtm, _, rid_a, _ = self._bought()

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=110_000, quantity=10, strategy='stratA',
            reason='매도', buy_record_id=rid_a,
        )

        assert vtm.get_strategy_positions("stratA") == []
        assert vtm.get_strategy_positions("stratB") == [CODE]

    def test_sell_by_first_buyer_leaves_second_buyer_invested_intact(self):
        vtm, _, rid_a, _ = self._bought()
        b_invested_before = vtm._strategy_invested["stratB"]

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=110_000, quantity=10, strategy='stratA',
            reason='매도', buy_record_id=rid_a,
        )

        assert vtm._strategy_invested["stratB"] == pytest.approx(b_invested_before)

    def test_second_buyer_can_still_sell_afterwards(self):
        """A 매도 후에도 B의 소유권이 남아 정상 매도되어야 한다."""
        vtm, captured, rid_a, rid_b = self._bought()

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=110_000, quantity=10, strategy='stratA',
            reason='매도', buy_record_id=rid_a,
        )
        b_before = vtm.get_strategy_balance("stratB")

        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=125_000, quantity=5, strategy='stratB',
            reason='매도', buy_record_id=rid_b,
        )

        assert captured['sell'][-1]['strategy'] == 'stratB'
        assert vtm.get_strategy_balance("stratB") == pytest.approx(
            b_before + _net_received(125_000, 5))
        assert vtm.get_strategy_positions("stratB") == []

    def test_aggregate_stays_consistent_after_multi_owner_roundtrip(self):
        """집계 잔고 == Σ 전략 잔고 (다owner 라운드트립 후에도)."""
        vtm, _, rid_a, rid_b = self._bought()
        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자', price=110_000, quantity=10,
            strategy='stratA', reason='매도', buy_record_id=rid_a)
        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자', price=125_000, quantity=5,
            strategy='stratB', reason='매도', buy_record_id=rid_b)

        assert vtm.virtual_balance == pytest.approx(
            vtm.get_strategy_balance("stratA") + vtm.get_strategy_balance("stratB"))
        # 각 전략 현금 == 재구성 cash 식 (라운드트립 정합)
        assert vtm.get_strategy_balance("stratA") == pytest.approx(
            _expected_cash(INITIAL, 100_000 * 10, 110_000 * 10))
        assert vtm.get_strategy_balance("stratB") == pytest.approx(
            _expected_cash(INITIAL, 120_000 * 5, 125_000 * 5))


# ---------------------------------------------------------------------------
# 정규화 의도 보존: 호출자가 폴더키가 아닌 클래스명을 넘기는 과거 버그
# ---------------------------------------------------------------------------

class TestClassNameNormalizationPreserved:
    """line 541-544 주석의 정규화 의도(호출자가 클래스명을 넘겨도 BUY/SELL 이
    동일 폴더키로 기록)는 다owner 수정 후에도 유지되어야 한다."""

    def test_class_name_normalized_to_owning_folder_key_multi_owner(self):
        vtm, captured = _make_vtm_capturing_db()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        vtm.allocate_strategy_capital("book_pullback_ma5", INITIAL)

        vtm.execute_virtual_buy(
            stock_code=CODE, stock_name='삼성전자',
            price=100_000, quantity=10, strategy='stratA', reason='매수')
        rid_b = vtm.execute_virtual_buy(
            stock_code=CODE, stock_name='삼성전자',
            price=120_000, quantity=5, strategy='book_pullback_ma5', reason='매수')

        b_before = vtm.get_strategy_balance("book_pullback_ma5")
        a_before = vtm.get_strategy_balance("stratA")

        # 호출자가 폴더키 대신 클래스명을 넘기는 상황 (상위 경로 과거 버그)
        vtm.execute_virtual_sell(
            stock_code=CODE, stock_name='삼성전자',
            price=125_000, quantity=5, strategy='BookPullbackMa5Strategy',
            reason='매도', buy_record_id=rid_b,
        )

        # buy_record_id 로 실소유자 식별 → 폴더키로 정규화
        assert captured['sell'][-1]['strategy'] == 'book_pullback_ma5'
        assert vtm.get_strategy_balance("book_pullback_ma5") == pytest.approx(
            b_before + _net_received(125_000, 5))
        assert vtm.get_strategy_balance("stratA") == pytest.approx(a_before)
        assert vtm.get_strategy_positions("stratA") == [CODE]
