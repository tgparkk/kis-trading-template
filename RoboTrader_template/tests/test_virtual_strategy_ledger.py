"""
전략별 가상매매 자금 격리(원장) 테스트.

각 전략이 독립된 가상 초기자본을 갖고:
- 매수는 그 전략의 잔여 한도 내로 제한된다.
- 매도는 종목 소유 전략(_position_owner)의 잔고로 복구된다.
- 집계 잔고(virtual_balance)는 전략 잔고 합계와 항상 일치한다.

하위호환: 아무 전략도 할당하지 않으면 기존 단일 virtual_balance 동작 그대로.
"""
import pytest
from unittest.mock import Mock, patch


def _make_vtm():
    """패치된 VirtualTradingManager 인스턴스 (paper 모드, DB 없음)."""
    with patch('core.virtual_trading_manager.setup_logger'):
        from core.virtual_trading_manager import VirtualTradingManager
        return VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)


def _make_vtm_with_db():
    """save_virtual_buy/sell이 성공을 반환하는 mock DB를 가진 VTM."""
    vtm = _make_vtm()
    db = Mock()
    # 매수 시 호출마다 증가하는 record id 부여
    _counter = {'n': 0}

    def _save_buy(**kwargs):
        _counter['n'] += 1
        return _counter['n']

    db.save_virtual_buy.side_effect = _save_buy
    db.save_virtual_sell.return_value = True
    vtm.db_manager = db
    return vtm


# ---------------------------------------------------------------------------
# 할당 및 집계 동기화
# ---------------------------------------------------------------------------

class TestAllocateAndAggregate:
    def test_allocate_sets_strategy_balance(self):
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("elder_ema_pullback", 10_000_000)
        assert vtm.get_strategy_balance("elder_ema_pullback") == 10_000_000

    def test_aggregate_equals_sum_of_strategies(self):
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("elder_ema_pullback", 10_000_000)
        vtm.allocate_strategy_capital("minervini", 10_000_000)
        assert vtm.virtual_balance == 20_000_000
        assert vtm.get_virtual_balance() == 20_000_000

    def test_unknown_strategy_balance_is_none(self):
        vtm = _make_vtm()
        assert vtm.get_strategy_balance("nope") is None


# ---------------------------------------------------------------------------
# 매수: 전략별 차감 격리
# ---------------------------------------------------------------------------

class TestBuyIsolation:
    def test_buy_deducts_only_owning_strategy(self):
        vtm = _make_vtm_with_db()
        vtm.allocate_strategy_capital("stratA", 10_000_000)
        vtm.allocate_strategy_capital("stratB", 10_000_000)

        rid = vtm.execute_virtual_buy(
            stock_code='005930', stock_name='삼성전자',
            price=100_000, quantity=10,
            strategy='stratA', reason='매수',
        )
        assert rid is not None

        # A만 차감 (cost = 100000*10 + 수수료)
        assert vtm.get_strategy_balance("stratA") < 10_000_000
        assert vtm.get_strategy_balance("stratB") == 10_000_000
        # 집계도 차감분만큼 줄어듦
        assert vtm.virtual_balance == (
            vtm.get_strategy_balance("stratA") + vtm.get_strategy_balance("stratB")
        )

    def test_position_owner_recorded(self):
        vtm = _make_vtm_with_db()
        vtm.allocate_strategy_capital("stratA", 10_000_000)
        vtm.execute_virtual_buy(
            stock_code='005930', stock_name='삼성전자',
            price=100_000, quantity=10,
            strategy='stratA', reason='매수',
        )
        assert vtm.get_strategy_positions("stratA") == ['005930']

    def test_buy_rejected_when_strategy_balance_insufficient(self):
        vtm = _make_vtm_with_db()
        vtm.allocate_strategy_capital("stratA", 500_000)  # 50만원만 할당
        # 1주 100만원 → 전략 한도 초과 → 거부
        rid = vtm.execute_virtual_buy(
            stock_code='005930', stock_name='삼성전자',
            price=1_000_000, quantity=1,
            strategy='stratA', reason='매수',
        )
        assert rid is None
        # 잔고 불변
        assert vtm.get_strategy_balance("stratA") == 500_000


# ---------------------------------------------------------------------------
# 매도: 소유 전략 복구
# ---------------------------------------------------------------------------

class TestSellRestoresOwner:
    def test_sell_restores_owning_strategy_only(self):
        vtm = _make_vtm_with_db()
        vtm.allocate_strategy_capital("stratA", 10_000_000)
        vtm.allocate_strategy_capital("stratB", 10_000_000)

        rid = vtm.execute_virtual_buy(
            stock_code='005930', stock_name='삼성전자',
            price=100_000, quantity=10,
            strategy='stratA', reason='매수',
        )
        after_buy_a = vtm.get_strategy_balance("stratA")
        assert after_buy_a < 10_000_000

        ok = vtm.execute_virtual_sell(
            stock_code='005930', stock_name='삼성전자',
            price=110_000, quantity=10,
            strategy='stratA', reason='매도', buy_record_id=rid,
        )
        assert ok is True

        # A 잔고가 복구되어 매수 직후보다 증가 (이익 매도)
        assert vtm.get_strategy_balance("stratA") > after_buy_a
        # B는 불변
        assert vtm.get_strategy_balance("stratB") == 10_000_000
        # 소유권/포지션 정리됨
        assert vtm.get_strategy_positions("stratA") == []
        # 집계 = 합계
        assert vtm.virtual_balance == (
            vtm.get_strategy_balance("stratA") + vtm.get_strategy_balance("stratB")
        )


# ---------------------------------------------------------------------------
# 하위호환: 할당 없으면 단일 virtual_balance 경로
# ---------------------------------------------------------------------------

class TestLegacyNoAllocation:
    def test_buy_uses_single_balance_when_no_allocation(self):
        vtm = _make_vtm_with_db()
        # 할당 전혀 없음 → 기존 단일 잔고 10,000,000
        assert vtm.virtual_balance == 10_000_000
        before = vtm.virtual_balance

        rid = vtm.execute_virtual_buy(
            stock_code='005930', stock_name='삼성전자',
            price=100_000, quantity=10,
            strategy='SampleStrategy', reason='매수',
        )
        assert rid is not None
        # 단일 잔고에서 차감
        assert vtm.virtual_balance < before
        # 전략 원장은 비어있음
        assert vtm.get_strategy_balance("SampleStrategy") is None

    def test_get_max_quantity_legacy_uses_virtual_balance(self):
        vtm = _make_vtm()
        # 할당 없음 → min(virtual_investment_amount=1,000,000, virtual_balance=10,000,000)/price
        qty = vtm.get_max_quantity(100_000)
        assert qty == 10  # 1,000,000 / 100,000

    def test_get_max_quantity_with_strategy_uses_strategy_balance(self):
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", 300_000)  # 30만원만
        # min(virtual_investment_amount=1,000,000, strategy_balance=300,000)/price
        qty = vtm.get_max_quantity(100_000, strategy_name="stratA")
        assert qty == 3  # 300,000 / 100,000


# ---------------------------------------------------------------------------
# 재시작 영속화: 매매기록에서 전략 원장 재구성
# ---------------------------------------------------------------------------

from config.constants import (
    COMMISSION_RATE, SECURITIES_TAX_RATE, VIRTUAL_CAPITAL_PER_STRATEGY,
)

INITIAL = VIRTUAL_CAPITAL_PER_STRATEGY


def _expected_cash(initial, buy_gross, sell_gross):
    """재구성 cash 식 (테스트 기준값) — 구현과 동일 선형식."""
    return (
        initial
        - buy_gross * (1.0 + COMMISSION_RATE)
        + sell_gross * (1.0 - COMMISSION_RATE - SECURITIES_TAX_RATE)
    )


class TestRestoreLedgerFromRecords:
    def test_buy_only_cash(self):
        """매수만 있는 전략: cash = initial − buy_gross*(1+commission)"""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        sums = {'stratA': {'buy_gross': 1_000_000.0, 'sell_gross': 0.0}}
        positions = [{'stock_code': '005930', 'strategy': 'stratA',
                      'quantity': 10, 'buy_price': 100_000.0}]
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, positions)

        assert vtm.get_strategy_balance("stratA") == pytest.approx(
            _expected_cash(INITIAL, 1_000_000.0, 0.0)
        )

    def test_buy_and_sell_cash(self):
        """매수+매도: cash 식에 sell_gross 순수익 반영"""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        sums = {'stratA': {'buy_gross': 1_000_000.0, 'sell_gross': 1_100_000.0}}
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, [])

        assert vtm.get_strategy_balance("stratA") == pytest.approx(
            _expected_cash(INITIAL, 1_000_000.0, 1_100_000.0)
        )

    def test_two_stocks_two_strategies(self):
        """2종목/2전략: 각 전략 독립 재구성 + position owner 복원"""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        vtm.allocate_strategy_capital("stratB", INITIAL)
        sums = {
            'stratA': {'buy_gross': 1_000_000.0, 'sell_gross': 0.0},
            'stratB': {'buy_gross': 660_000.0, 'sell_gross': 0.0},
        }
        positions = [
            {'stock_code': '005930', 'strategy': 'stratA', 'quantity': 10, 'buy_price': 100_000.0},
            {'stock_code': '000660', 'strategy': 'stratB', 'quantity': 6, 'buy_price': 110_000.0},
        ]
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, positions)

        assert vtm.get_strategy_balance("stratA") == pytest.approx(
            _expected_cash(INITIAL, 1_000_000.0, 0.0))
        assert vtm.get_strategy_balance("stratB") == pytest.approx(
            _expected_cash(INITIAL, 660_000.0, 0.0))
        assert vtm._position_owner == {'005930': 'stratA', '000660': 'stratB'}
        assert vtm.get_strategy_positions("stratA") == ['005930']
        assert vtm.get_strategy_positions("stratB") == ['000660']

    def test_invested_restored_from_positions(self):
        """invested = Σ qty*buy_price*(1+commission)"""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        sums = {'stratA': {'buy_gross': 1_000_000.0, 'sell_gross': 0.0}}
        positions = [{'stock_code': '005930', 'strategy': 'stratA',
                      'quantity': 10, 'buy_price': 100_000.0}]
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, positions)

        assert vtm._strategy_invested["stratA"] == pytest.approx(
            10 * 100_000.0 * (1.0 + COMMISSION_RATE)
        )

    def test_aggregate_equals_sum_of_cash(self):
        """집계 virtual_balance == Σ 전략 cash"""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        vtm.allocate_strategy_capital("stratB", INITIAL)
        sums = {
            'stratA': {'buy_gross': 1_000_000.0, 'sell_gross': 0.0},
            'stratB': {'buy_gross': 500_000.0, 'sell_gross': 0.0},
        }
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, [])

        assert vtm.virtual_balance == pytest.approx(
            vtm.get_strategy_balance("stratA") + vtm.get_strategy_balance("stratB")
        )

    def test_no_double_deduction_for_buy(self):
        """매수비용은 cash 식에서 한 번만 차감 — position 루프는 cash 재차감 안 함.

        positions 유무에 따라 cash가 달라지면 안 된다 (이중차감 검증).
        """
        sums = {'stratA': {'buy_gross': 1_000_000.0, 'sell_gross': 0.0}}

        vtm_with_pos = _make_vtm()
        vtm_with_pos.allocate_strategy_capital("stratA", INITIAL)
        vtm_with_pos.restore_strategy_ledger_from_records(
            INITIAL, sums,
            [{'stock_code': '005930', 'strategy': 'stratA',
              'quantity': 10, 'buy_price': 100_000.0}],
        )

        vtm_no_pos = _make_vtm()
        vtm_no_pos.allocate_strategy_capital("stratA", INITIAL)
        vtm_no_pos.restore_strategy_ledger_from_records(INITIAL, sums, [])

        assert vtm_with_pos.get_strategy_balance("stratA") == pytest.approx(
            vtm_no_pos.get_strategy_balance("stratA")
        )

    def test_first_run_empty_inputs_keeps_initial(self):
        """첫 실행(기록·포지션 없음): cash = initial 그대로."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        vtm.restore_strategy_ledger_from_records(INITIAL, {}, [])
        assert vtm.get_strategy_balance("stratA") == pytest.approx(INITIAL)

    def test_deleted_strategy_key_created(self):
        """삭제된 전략(할당 없으나 trade_sums에 존재): 원장에 키 생성(고아자금 회수)."""
        vtm = _make_vtm()
        # stratA만 할당, stratGhost는 매매기록에만 존재
        vtm.allocate_strategy_capital("stratA", INITIAL)
        sums = {
            'stratA': {'buy_gross': 0.0, 'sell_gross': 0.0},
            'stratGhost': {'buy_gross': 2_000_000.0, 'sell_gross': 2_100_000.0},
        }
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, [])

        assert vtm.get_strategy_balance("stratGhost") is not None
        assert vtm.get_strategy_balance("stratGhost") == pytest.approx(
            _expected_cash(INITIAL, 2_000_000.0, 2_100_000.0)
        )

    def test_position_for_unallocated_strategy_creates_key(self):
        """미할당 전략의 미청산 포지션도 원장 키 생성 + owner 복원."""
        vtm = _make_vtm()
        # 아무 할당 없음, trade_sums에도 없음 → positions만으로 원장 활성화 불가하므로
        # 하나라도 활성 상태로 만들기 위해 기존 할당 하나 둠
        vtm.allocate_strategy_capital("stratA", INITIAL)
        positions = [{'stock_code': '000660', 'strategy': 'stratNew',
                      'quantity': 6, 'buy_price': 110_000.0}]
        vtm.restore_strategy_ledger_from_records(INITIAL, {}, positions)

        assert vtm.get_strategy_balance("stratNew") == pytest.approx(INITIAL)
        assert vtm._position_owner['000660'] == 'stratNew'

    def test_legacy_noop_when_inactive(self):
        """하위호환: 원장 미활성 + 빈 입력 → no-op (단일 잔고 불변)."""
        vtm = _make_vtm()  # 할당 전혀 없음
        before = vtm.virtual_balance
        vtm.restore_strategy_ledger_from_records(INITIAL, {}, [])
        assert vtm.virtual_balance == before
        assert vtm._strategy_balances == {}


class TestRestartParity:
    """재시작 전(런타임 원장) == 재시작 후(재구성) 동일성 검증."""

    def test_reconstruction_matches_runtime_ledger(self):
        # 1) 런타임: A로 005930 매수, B로 000660 매수
        live = _make_vtm_with_db()
        live.allocate_strategy_capital("stratA", INITIAL)
        live.allocate_strategy_capital("stratB", INITIAL)
        live.execute_virtual_buy(stock_code='005930', stock_name='삼성전자',
                                 price=100_000, quantity=10, strategy='stratA', reason='매수')
        live.execute_virtual_buy(stock_code='000660', stock_name='하이닉스',
                                 price=110_000, quantity=6, strategy='stratB', reason='매수')

        # 2) 재시작: 새 VTM + 할당 + 재구성
        restored = _make_vtm()
        restored.allocate_strategy_capital("stratA", INITIAL)
        restored.allocate_strategy_capital("stratB", INITIAL)
        sums = {
            'stratA': {'buy_gross': 100_000 * 10, 'sell_gross': 0.0},
            'stratB': {'buy_gross': 110_000 * 6, 'sell_gross': 0.0},
        }
        positions = [
            {'stock_code': '005930', 'strategy': 'stratA', 'quantity': 10, 'buy_price': 100_000.0},
            {'stock_code': '000660', 'strategy': 'stratB', 'quantity': 6, 'buy_price': 110_000.0},
        ]
        restored.restore_strategy_ledger_from_records(INITIAL, sums, positions)

        # 3) 재구성값 == 런타임값
        assert restored.get_strategy_balance("stratA") == pytest.approx(
            live.get_strategy_balance("stratA"))
        assert restored.get_strategy_balance("stratB") == pytest.approx(
            live.get_strategy_balance("stratB"))
        assert restored.virtual_balance == pytest.approx(live.virtual_balance)
        assert restored._position_owner == live._position_owner

    def test_sell_after_restore_credits_owner_only(self):
        """재구성 후 매도 → owner 전략만 증가, 타전략 불변."""
        restored = _make_vtm_with_db()
        restored.allocate_strategy_capital("stratA", INITIAL)
        restored.allocate_strategy_capital("stratB", INITIAL)
        sums = {
            'stratA': {'buy_gross': 100_000 * 10, 'sell_gross': 0.0},
            'stratB': {'buy_gross': 110_000 * 6, 'sell_gross': 0.0},
        }
        positions = [
            {'stock_code': '005930', 'strategy': 'stratA', 'quantity': 10, 'buy_price': 100_000.0},
            {'stock_code': '000660', 'strategy': 'stratB', 'quantity': 6, 'buy_price': 110_000.0},
        ]
        restored.restore_strategy_ledger_from_records(INITIAL, sums, positions)

        a_before = restored.get_strategy_balance("stratA")
        b_before = restored.get_strategy_balance("stratB")

        restored.execute_virtual_sell(stock_code='005930', stock_name='삼성전자',
                                      price=110_000, quantity=10, strategy='stratA',
                                      reason='매도', buy_record_id=1)

        assert restored.get_strategy_balance("stratA") > a_before
        assert restored.get_strategy_balance("stratB") == pytest.approx(b_before)
        assert '005930' not in restored._position_owner


class TestSellOwnerFallback:
    """매도 시 _position_owner miss 폴백: strategy 인자가 폴더키면 귀속."""

    def test_fallback_credits_matching_strategy(self):
        vtm = _make_vtm_with_db()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        # _position_owner 비어 있음 (재구성 전 매도 등) but strategy='stratA' 직매칭
        before = vtm.get_strategy_balance("stratA")
        vtm.execute_virtual_sell(stock_code='005930', stock_name='삼성전자',
                                 price=110_000, quantity=10, strategy='stratA',
                                 reason='매도', buy_record_id=1)
        # 전략 잔고에 매도수익 반영 (단일 잔고로 새지 않음)
        assert vtm.get_strategy_balance("stratA") > before

    def test_unknown_strategy_falls_to_single_balance(self):
        """전달 strategy가 원장에 없으면 단일 잔고 경로 (레거시)."""
        vtm = _make_vtm_with_db()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        a_before = vtm.get_strategy_balance("stratA")
        agg_before = vtm.virtual_balance
        vtm.execute_virtual_sell(stock_code='999999', stock_name='미지',
                                 price=110_000, quantity=10, strategy='ghost',
                                 reason='매도', buy_record_id=1)
        # stratA 불변 (귀속 안 됨)
        assert vtm.get_strategy_balance("stratA") == pytest.approx(a_before)
        # 단일 잔고(update_virtual_balance)로 증가
        assert vtm.virtual_balance > agg_before
