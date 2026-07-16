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


def _owners_of(vtm, stock_code):
    """해당 종목의 소유 전략 목록.

    _position_owner 는 (종목코드, 매수기록ID) 로 키잉된다 (다owner 동일종목 지원).
    """
    return [o for (code, _), o in vtm._position_owner.items() if code == stock_code]


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
            {'stock_code': '005930', 'strategy': 'stratA', 'quantity': 10,
             'buy_price': 100_000.0, 'buy_record_id': 1},
            {'stock_code': '000660', 'strategy': 'stratB', 'quantity': 6,
             'buy_price': 110_000.0, 'buy_record_id': 2},
        ]
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, positions)

        assert vtm.get_strategy_balance("stratA") == pytest.approx(
            _expected_cash(INITIAL, 1_000_000.0, 0.0))
        assert vtm.get_strategy_balance("stratB") == pytest.approx(
            _expected_cash(INITIAL, 660_000.0, 0.0))
        assert vtm._position_owner == {
            ('005930', 1): 'stratA', ('000660', 2): 'stratB'}
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

    def test_unallocated_strategy_in_trade_sums_excluded(self):
        """[정책변경 2026-06-04] 격리 원장 모드에서 미할당(비활성) 전략은 제외.

        과거엔 trade_sums의 미할당 전략에 키를 생성(고아자금 회수)했으나,
        이 동작이 형제프로젝트/테스트 오염 전략까지 끌어들여 집계가 폭증(174.8M)했다.
        이제 allocate된 활성 전략만 재구성하고 나머지는 무시한다.
        """
        vtm = _make_vtm()
        # stratA만 할당, stratGhost는 매매기록에만 존재(비활성)
        vtm.allocate_strategy_capital("stratA", INITIAL)
        sums = {
            'stratA': {'buy_gross': 0.0, 'sell_gross': 0.0},
            'stratGhost': {'buy_gross': 2_000_000.0, 'sell_gross': 2_100_000.0},
        }
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, [])

        assert vtm.get_strategy_balance("stratGhost") is None
        assert vtm.get_strategy_balance("stratA") == pytest.approx(INITIAL)

    def test_position_for_unallocated_strategy_excluded(self):
        """[정책변경 2026-06-04] 미할당 전략의 미청산 포지션은 원장에 복원하지 않는다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL)
        positions = [{'stock_code': '000660', 'strategy': 'stratNew',
                      'quantity': 6, 'buy_price': 110_000.0}]
        vtm.restore_strategy_ledger_from_records(INITIAL, {}, positions)

        assert vtm.get_strategy_balance("stratNew") is None
        assert _owners_of(vtm, '000660') == []

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
        # buy_record_id = 런타임 mock DB가 부여한 순번(005930→1, 000660→2)
        positions = [
            {'stock_code': '005930', 'strategy': 'stratA', 'quantity': 10,
             'buy_price': 100_000.0, 'buy_record_id': 1},
            {'stock_code': '000660', 'strategy': 'stratB', 'quantity': 6,
             'buy_price': 110_000.0, 'buy_record_id': 2},
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
            {'stock_code': '005930', 'strategy': 'stratA', 'quantity': 10,
             'buy_price': 100_000.0, 'buy_record_id': 1},
            {'stock_code': '000660', 'strategy': 'stratB', 'quantity': 6,
             'buy_price': 110_000.0, 'buy_record_id': 2},
        ]
        restored.restore_strategy_ledger_from_records(INITIAL, sums, positions)

        a_before = restored.get_strategy_balance("stratA")
        b_before = restored.get_strategy_balance("stratB")

        restored.execute_virtual_sell(stock_code='005930', stock_name='삼성전자',
                                      price=110_000, quantity=10, strategy='stratA',
                                      reason='매도', buy_record_id=1)

        assert restored.get_strategy_balance("stratA") > a_before
        assert restored.get_strategy_balance("stratB") == pytest.approx(b_before)
        assert _owners_of(restored, '005930') == []


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


# ---------------------------------------------------------------------------
# DB 기록 strategy 컬럼 일관성: BUY/SELL이 동일 폴더키로 기록되어야 함
# (2026-06-01 버그: SELL이 클래스명으로 기록되어 재시작 재구성이 버킷 분리)
# ---------------------------------------------------------------------------

def _make_vtm_capturing_db():
    """save_virtual_buy/sell에 전달된 strategy 인자를 캡처하는 mock DB를 가진 VTM."""
    vtm = _make_vtm()
    db = Mock()
    captured = {'buy': [], 'sell': []}
    _counter = {'n': 0}

    def _save_buy(**kwargs):
        _counter['n'] += 1
        captured['buy'].append(kwargs.get('strategy'))
        return _counter['n']

    def _save_sell(**kwargs):
        captured['sell'].append(kwargs.get('strategy'))
        return True

    db.save_virtual_buy.side_effect = _save_buy
    db.save_virtual_sell.side_effect = _save_sell
    vtm.db_manager = db
    return vtm, captured


class TestDbStrategyColumnConsistency:
    def test_sell_persists_owner_folder_key_not_class_name(self):
        """BUY가 폴더키로 기록되면, SELL도 동일 폴더키로 기록되어야 한다.

        호출자가 strategy 인자로 클래스명을 넘겨도(상위 버그),
        _position_owner(폴더키)가 있으면 그것으로 정규화하여 DB에 기록.
        """
        vtm, captured = _make_vtm_capturing_db()
        vtm.allocate_strategy_capital("minervini_volume_dryup", 10_000_000)

        rid = vtm.execute_virtual_buy(
            stock_code='332570', stock_name='ABC',
            price=12_250, quantity=367,
            strategy='minervini_volume_dryup', reason='매수',
        )
        assert rid is not None
        assert captured['buy'][-1] == 'minervini_volume_dryup'

        # 호출자가 SELL에 클래스명을 넘기는 버그 상황 재현
        ok = vtm.execute_virtual_sell(
            stock_code='332570', stock_name='ABC',
            price=12_440, quantity=367,
            strategy='MinerviniVolumeDryupStrategy',  # 클래스명 (잘못된 입력)
            reason='매도', buy_record_id=rid,
        )
        assert ok is True
        # DB에 기록된 SELL strategy는 폴더키로 정규화돼야 함
        assert captured['sell'][-1] == 'minervini_volume_dryup'

    def test_roundtrip_reconstructs_single_bucket(self):
        """라운드트립 후 get_strategy_trade_sums 동등 그룹핑 → 현금 재구성 정확.

        DB 기록(폴더키 통일)을 trade_sums로 환원해 재시작 재구성하면
        cash = initial − buy + sell 로 한 버킷에서 복원되어야 한다.
        """
        vtm, captured = _make_vtm_capturing_db()
        vtm.allocate_strategy_capital("minervini_volume_dryup", INITIAL)

        rid = vtm.execute_virtual_buy(
            stock_code='332570', stock_name='ABC',
            price=12_250, quantity=367,
            strategy='minervini_volume_dryup', reason='매수',
        )
        vtm.execute_virtual_sell(
            stock_code='332570', stock_name='ABC',
            price=12_440, quantity=367,
            strategy='MinerviniVolumeDryupStrategy',  # 클래스명 (잘못된 입력)
            reason='매도', buy_record_id=rid,
        )
        live_balance = vtm.get_strategy_balance("minervini_volume_dryup")

        # DB에 기록된 strategy 키로 trade_sums를 구성(실DB get_strategy_trade_sums 모사)
        buy_key = captured['buy'][-1]
        sell_key = captured['sell'][-1]
        # 두 키가 같아야 한 버킷으로 합산됨 (버그면 다른 키 → 버킷 분리)
        assert buy_key == sell_key == 'minervini_volume_dryup'

        trade_sums = {
            'minervini_volume_dryup': {
                'buy_gross': 12_250 * 367,
                'sell_gross': 12_440 * 367,
            }
        }
        restored = _make_vtm()
        restored.allocate_strategy_capital("minervini_volume_dryup", INITIAL)
        restored.restore_strategy_ledger_from_records(INITIAL, trade_sums, [])

        # 재구성 현금 == 런타임 현금 (한 버킷으로 정확 복원)
        assert restored.get_strategy_balance("minervini_volume_dryup") == pytest.approx(
            live_balance
        )
        # cash = initial − buy*(1+c) + sell*(1−c−t)
        assert restored.get_strategy_balance("minervini_volume_dryup") == pytest.approx(
            _expected_cash(INITIAL, 12_250 * 367, 12_440 * 367)
        )

    def test_pending_queue_record_uses_owner_folder_key(self):
        """DB 저장 실패 시 pending 큐 레코드의 strategy도 폴더키로 정규화."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("minervini_volume_dryup", 10_000_000)
        db = Mock()
        _counter = {'n': 0}

        def _save_buy(**kwargs):
            _counter['n'] += 1
            return _counter['n']

        db.save_virtual_buy.side_effect = _save_buy
        db.save_virtual_sell.return_value = False  # 매도 DB 저장 실패 → pending 큐
        vtm.db_manager = db

        rid = vtm.execute_virtual_buy(
            stock_code='332570', stock_name='ABC',
            price=12_250, quantity=367,
            strategy='minervini_volume_dryup', reason='매수',
        )
        vtm.execute_virtual_sell(
            stock_code='332570', stock_name='ABC',
            price=12_440, quantity=367,
            strategy='MinerviniVolumeDryupStrategy',  # 클래스명 (잘못된 입력)
            reason='매도', buy_record_id=rid,
        )
        assert vtm.get_pending_sells_count() == 1
        assert vtm._pending_sell_records[0]['strategy'] == 'minervini_volume_dryup'

    def test_legacy_no_ledger_keeps_passed_strategy(self):
        """원장 미할당(레거시): _position_owner 없으면 전달된 strategy 그대로 기록."""
        vtm, captured = _make_vtm_capturing_db()
        # 할당 없음 → 단일 잔고 경로, 정규화 없음
        vtm.execute_virtual_sell(
            stock_code='005930', stock_name='삼성전자',
            price=110_000, quantity=10,
            strategy='SampleStrategy', reason='매도', buy_record_id=1,
        )
        assert captured['sell'][-1] == 'SampleStrategy'


class TestRestoreLedgerExcludesInactiveStrategies:
    """재구성 시 활성 전략(allocate된 폴더키)만 반영하고,
    매매기록·포지션에 섞인 비활성(과거/형제/테스트) 전략은 무시한다.

    2026-06-04 회귀: trade_sums 가 DB 전체 전략을 반환해 유령 전략마다
    initial(=10M)이 더해져 집계 잔고가 폭증한 버그(174.8M)에 대한 가드.
    """

    def test_inactive_strategy_in_trade_sums_ignored(self):
        """trade_sums 에 비활성 전략이 있어도 원장/집계에 포함되지 않는다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("elder_ema_pullback", INITIAL)
        sums = {
            "elder_ema_pullback": {'buy_gross': 1_000_000.0, 'sell_gross': 0.0},
            # 비활성(과거/오염) 전략들 — 무시되어야 함
            "SampleStrategy": {'buy_gross': 0.0, 'sell_gross': 50_000_000.0},
            "gate_shadow": {'buy_gross': 0.0, 'sell_gross': 30_000_000.0},
        }
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, [])

        assert vtm.get_strategy_balance("SampleStrategy") is None
        assert vtm.get_strategy_balance("gate_shadow") is None
        # 집계 = 활성 1개 전략만 (initial − buy*(1+comm))
        assert vtm.virtual_balance == pytest.approx(
            _expected_cash(INITIAL, 1_000_000.0, 0.0)
        )

    def test_inactive_open_position_owner_ignored(self):
        """비활성 전략이 소유한 미청산 포지션은 원장에 복원하지 않는다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("elder_ema_pullback", INITIAL)
        positions = [
            # 옛 SampleStrategy 잔재(152550 류) — 무시되어야 함
            {'stock_code': '152550', 'strategy': 'SampleStrategy',
             'quantity': 13851, 'buy_price': 58.0},
        ]
        vtm.restore_strategy_ledger_from_records(INITIAL, {}, positions)

        assert vtm.get_strategy_balance("SampleStrategy") is None
        assert _owners_of(vtm, '152550') == []
        assert vtm.virtual_balance == pytest.approx(INITIAL)  # 활성 전략 그대로

    def test_active_strategy_records_still_applied(self):
        """활성 전략의 기록·포지션은 정상 반영(회귀 방지)."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("minervini_volume_dryup", INITIAL)
        sums = {"minervini_volume_dryup":
                {'buy_gross': 2_000_000.0, 'sell_gross': 2_100_000.0}}
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, [])

        assert vtm.get_strategy_balance("minervini_volume_dryup") == pytest.approx(
            _expected_cash(INITIAL, 2_000_000.0, 2_100_000.0)
        )

    def test_five_active_strategies_aggregate_is_bounded(self):
        """활성 5전략 + 오염 trade_sums → 집계가 5×initial 근방(폭증 없음)."""
        vtm = _make_vtm()
        active = ["elder_ema_pullback", "minervini_volume_dryup",
                  "book_pullback_ma20", "book_pullback_ma5",
                  "daytrading_3methods_breakout"]
        for k in active:
            vtm.allocate_strategy_capital(k, INITIAL)
        sums = {
            "minervini_volume_dryup": {'buy_gross': 2_000_000.0, 'sell_gross': 2_100_000.0},
            "SampleStrategy": {'buy_gross': 0.0, 'sell_gross': 326_000_000.0},
            "리밸런싱": {'buy_gross': 0.0, 'sell_gross': 40_000_000.0},
        }
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, [])

        # 폭증(174.8M)이 아니라 5×10M 근방이어야 한다
        assert vtm.virtual_balance < 5 * INITIAL + 1_000_000
        assert vtm.virtual_balance > 5 * INITIAL - 1_000_000
        assert set(vtm._strategy_balances) == set(active)

    def test_legacy_no_allocation_keeps_trade_sums_behavior(self):
        """하위호환: allocate 없음(레거시) → 기존 동작(trade_sums로 키 구성) 유지."""
        vtm = _make_vtm()
        # 할당 없이 곧장 재구성 (레거시 단일/비격리 경로)
        sums = {"legacy_strat": {'buy_gross': 1_000_000.0, 'sell_gross': 0.0}}
        positions = [{'stock_code': '005930', 'strategy': 'legacy_strat',
                      'quantity': 10, 'buy_price': 100_000.0}]
        vtm.restore_strategy_ledger_from_records(INITIAL, sums, positions)

        assert vtm.get_strategy_balance("legacy_strat") == pytest.approx(
            _expected_cash(INITIAL, 1_000_000.0, 0.0)
        )
