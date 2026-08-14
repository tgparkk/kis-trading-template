"""실전 재기동 복원이 두 소유자를 하나로 뭉개지 않는지 — 2전략 대칭 회귀.

배경 (2026-08-14 실매매 전환 감사 Fix 3):
  `bot/state_restorer.py:862-882` 는 DB 보유 행을 **종목코드 단독**으로
  집계했다. 주석은 "분할매수 합산"이라 적혀 있지만 그 술어는
  「같은 전략이 두 번 샀다」와 「서로 다른 두 전략이 한 번씩 샀다」를
  구분하지 못한다. `db/repositories/trading.py:452` 의
  `ORDER BY b.timestamp DESC` 때문에 **최신 행의 전략이 이기고**, 오래된
  소유자는 통째로 버려지며 **합산 수량이 승자에게 귀속**된다.

  실전 결과: 전략 A 가 합산 크기 포지션을 받아(K 회계·사이징 오류) 전략 B 는
  아무것도 못 받는다 → B 의 청산 규칙이 영영 발동하지 않는다.

  페이퍼 경로(`_restore_holdings_from_db`)에는 이 결함이 없다 — 행마다
  `owner_strategy=owner_name` 을 넘기고 `stock_state_manager:105-125` 가
  (code, owner) 당 슬롯 1개를 허용한다. **페이퍼가 기준 동작이다.**

  🔴 계좌-DB 대사는 «종목코드 단위»(브로커 잔고는 owner 를 모른다)이므로,
  owner 별로 쪼갠 뒤에도 대사는 owner 합으로 비교해야 한다. 안 그러면
  조용한 결함이 아침 기동을 막는 LiveStartupAbort 로 바뀐다.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.broker_contract import make_account_balance, make_holding
from utils.korean_time import now_kst

KEY_A = 'rs_leader'
KEY_B = 'elder_ema_pullback'
CODE = '005930'


def _make_restorer(db_manager, strategies, broker):
    from bot.state_restorer import StateRestorer
    config = Mock()
    config.paper_trading = False
    return StateRestorer(
        trading_manager=Mock(),
        db_manager=db_manager,
        telegram_integration=Mock(),
        config=config,
        get_previous_close_callback=lambda code: 100_000.0,
        broker=broker,
        fund_manager=None,
        virtual_trading_manager=None,
        strategies=strategies,
    )


def _wire_trading_manager(restorer):
    """(code, owner) 마다 별도 슬롯 객체를 돌려준다 — 실 상태관리자와 동일 계약."""
    async def _add(**kwargs):
        return True
    restorer.trading_manager.add_selected_stock.side_effect = _add

    slots = {}

    def _get(code, strategy=None):
        key = (code, strategy or "")
        if key not in slots:
            ts = Mock()
            ts.owner_strategy_name = strategy or ""
            ts.is_stale = False
            ts.days_held = 0
            slots[key] = ts
        return slots[key]

    restorer.trading_manager.get_trading_stock.side_effect = _get
    restorer.trading_manager._change_stock_state = Mock()
    return slots


def _row(strategy, quantity, buy_price, rec_id, buy_time=None):
    return {
        'id': rec_id, 'stock_code': CODE, 'stock_name': '삼성전자',
        'quantity': quantity, 'buy_price': buy_price,
        'buy_time': buy_time if buy_time is not None else now_kst(),
        'strategy': strategy,
        'target_profit_rate': None, 'stop_loss_rate': None,
    }


def _broker(total_qty, avg_price=100_000.0):
    b = Mock()
    b.get_account_balance.return_value = make_account_balance(total_stocks=1)
    b.get_holdings.return_value = [make_holding(
        stock_code=CODE, stock_name='삼성전자',
        quantity=total_qty, avg_price=avg_price)]
    b.get_pending_orders.return_value = []
    return b


def _run_restore(rows, broker_qty, strategies):
    db = Mock()
    # ORDER BY timestamp DESC 재현 — 첫 행이 최신
    db.get_real_open_positions.return_value = pd.DataFrame(rows)
    db.get_virtual_open_positions.return_value = pd.DataFrame()

    restorer = _make_restorer(db, strategies, _broker(broker_qty))
    slots = _wire_trading_manager(restorer)
    restorer._sync_fund_manager_for_position = Mock(return_value=0.0)
    restorer._apply_stale_position_check = Mock(return_value=(0.05, 0.03))

    asyncio.run(restorer._restore_holdings_from_real_account())
    return restorer, slots


class TestTwoOwnersSameCode:
    """같은 종목을 두 전략이 나눠 보유 — 둘 다 자기 몫으로 복원된다."""

    def _strats(self):
        a = Mock(); a.name = 'RSLeaderStrategy'
        b = Mock(); b.name = 'ElderEmaPullbackStrategy'
        return a, b

    def test_both_owners_get_their_own_quantity(self):
        a, b = self._strats()
        rows = [_row(KEY_A, 5, 100_000.0, 2),   # 최신
                _row(KEY_B, 5, 100_000.0, 1)]

        _restorer, _slots = _run_restore(rows, 10, {KEY_A: a, KEY_B: b})

        a.sync_positions.assert_called_once()
        b.sync_positions.assert_called_once()
        (pos_a,) = a.sync_positions.call_args[0]
        (pos_b,) = b.sync_positions.call_args[0]
        # 대칭: A 가 5 를 받았다 AND B 도 5 를 받았다 (10/0 붕괴 금지)
        assert pos_a[CODE]['quantity'] == 5
        assert pos_b[CODE]['quantity'] == 5

    def test_owner_specific_entry_price_is_preserved(self):
        """매입가도 owner 별 원가여야 자기 손절·트레일이 맞는다."""
        a, b = self._strats()
        rows = [_row(KEY_A, 5, 120_000.0, 2),
                _row(KEY_B, 5, 80_000.0, 1)]

        _restorer, _slots = _run_restore(rows, 10, {KEY_A: a, KEY_B: b})

        (pos_a,) = a.sync_positions.call_args[0]
        (pos_b,) = b.sync_positions.call_args[0]
        assert pos_a[CODE]['entry_price'] == 120_000.0
        assert pos_b[CODE]['entry_price'] == 80_000.0

    def test_fund_sync_runs_once_per_owner(self):
        a, b = self._strats()
        rows = [_row(KEY_A, 5, 100_000.0, 2),
                _row(KEY_B, 5, 100_000.0, 1)]

        restorer, _slots = _run_restore(rows, 10, {KEY_A: a, KEY_B: b})

        owners = [c.kwargs.get('owner')
                  for c in restorer._sync_fund_manager_for_position.call_args_list]
        assert sorted(owners) == sorted([KEY_A, KEY_B])

    def test_state_transition_runs_for_both_owners(self):
        a, b = self._strats()
        rows = [_row(KEY_A, 5, 100_000.0, 2),
                _row(KEY_B, 5, 100_000.0, 1)]

        restorer, _slots = _run_restore(rows, 10, {KEY_A: a, KEY_B: b})

        owners = [c.kwargs.get('strategy')
                  for c in restorer.trading_manager._change_stock_state.call_args_list]
        assert KEY_A in owners and KEY_B in owners


class TestSameOwnerSplitBuyStillAggregates:
    """같은 전략의 진짜 분할매수는 종전대로 합산(수량 SUM·매입가 가중평균)."""

    # 2026-08-14 리뷰 R1: by_owner 의 키는 원문 라벨이 아니라 «인스턴스 기준»
    # 그룹 키가 됐다(같은 전략의 두 표기를 접기 위해). 그래서 키 튜플 대신
    # 표시 라벨(strategy)로 조회한다 — 검증 대상은 집계 결과지 키 모양이 아니다.
    # 전략을 등록해 두는 것도 그 때문이다(미등록 라벨은 전부 한 바구니다).
    def _by_owner(self, rows, strategies=None):
        a = Mock(); a.name = 'RSLeaderStrategy'
        b = Mock(); b.name = 'ElderEmaPullbackStrategy'
        db = Mock()
        db.get_real_open_positions.return_value = pd.DataFrame(rows)
        db.get_virtual_open_positions.return_value = pd.DataFrame()
        restorer = _make_restorer(
            db, strategies if strategies is not None else {KEY_A: a, KEY_B: b},
            _broker(5))
        by_owner = restorer._build_db_holdings_by_owner(pd.DataFrame(rows))
        return {info['strategy']: info for info in by_owner.values()}

    def test_split_buy_sums_quantity_and_weights_price(self):
        rows = [_row(KEY_A, 2, 15_000.0, 2),   # 최신
                _row(KEY_A, 3, 10_000.0, 1)]

        by_owner = self._by_owner(rows)

        assert list(by_owner) == [KEY_A]
        info = by_owner[KEY_A]
        assert info['quantity'] == 5
        # (2*15000 + 3*10000) / 5 = 12000
        assert info['buy_price'] == pytest.approx(12_000.0)

    def test_two_owners_are_not_merged_even_with_split_buys(self):
        """대칭: 같은 전략의 분할매수는 합치고, 다른 전략은 절대 안 합친다."""
        rows = [_row(KEY_A, 2, 15_000.0, 3),
                _row(KEY_A, 3, 10_000.0, 2),
                _row(KEY_B, 5, 20_000.0, 1)]

        by_owner = self._by_owner(rows)

        assert by_owner[KEY_A]['quantity'] == 5
        assert by_owner[KEY_B]['quantity'] == 5
        assert by_owner[KEY_B]['buy_price'] == pytest.approx(20_000.0)

    def test_single_owner_restore_is_unchanged(self):
        """단일 owner 는 종전대로 계좌 수량·평단을 쓴다(동작 불변)."""
        a = Mock(); a.name = 'RSLeaderStrategy'
        rows = [_row(KEY_A, 2, 15_000.0, 2), _row(KEY_A, 3, 10_000.0, 1)]

        db = Mock()
        db.get_real_open_positions.return_value = pd.DataFrame(rows)
        db.get_virtual_open_positions.return_value = pd.DataFrame()
        restorer = _make_restorer(db, {KEY_A: a}, _broker(5, avg_price=100_000.0))
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)
        restorer._apply_stale_position_check = Mock(return_value=(0.05, 0.03))

        asyncio.run(restorer._restore_holdings_from_real_account())

        (pos_a,) = a.sync_positions.call_args[0]
        assert pos_a[CODE]['quantity'] == 5
        assert pos_a[CODE]['entry_price'] == 100_000.0


class TestReconciliationSumsAcrossOwners:
    """대사는 종목코드 단위 — owner 합으로 비교해야 기동이 안 막힌다."""

    def _mismatches(self, rows, real_qty):
        from bot.state_restorer import StateRestorer
        db = Mock()
        db.get_real_open_positions.return_value = pd.DataFrame(rows)
        db.get_virtual_open_positions.return_value = pd.DataFrame()
        restorer = _make_restorer(db, {}, _broker(real_qty))
        real_holdings = restorer.broker.get_holdings()
        by_code = restorer._build_db_holdings_by_code(
            restorer._build_db_holdings_by_owner(db.get_real_open_positions()))
        return asyncio.run(
            restorer._detect_holdings_mismatch(real_holdings, by_code))

    def test_two_owners_summing_to_broker_qty_is_not_a_mismatch(self):
        rows = [_row(KEY_A, 5, 100_000.0, 2), _row(KEY_B, 5, 100_000.0, 1)]
        assert self._mismatches(rows, 10) == []

    def test_genuine_quantity_gap_still_reported(self):
        """대칭: 합이 안 맞으면 여전히 불일치로 잡힌다(fail-closed 유지)."""
        rows = [_row(KEY_A, 5, 100_000.0, 2), _row(KEY_B, 3, 100_000.0, 1)]
        mismatches = self._mismatches(rows, 10)
        assert len(mismatches) == 1
        assert '수량 불일치' in mismatches[0]

    def test_two_owner_restore_does_not_abort_startup(self):
        """진입점 수준: 2 owner 복원이 LiveStartupAbort 를 내지 않는다."""
        a = Mock(); a.name = 'RSLeaderStrategy'
        b = Mock(); b.name = 'ElderEmaPullbackStrategy'
        rows = [_row(KEY_A, 5, 100_000.0, 2), _row(KEY_B, 5, 100_000.0, 1)]

        db = Mock()
        db.get_real_open_positions.return_value = pd.DataFrame(rows)
        db.get_virtual_open_positions.return_value = pd.DataFrame()
        restorer = _make_restorer(db, {KEY_A: a, KEY_B: b}, _broker(10))
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)
        restorer._apply_stale_position_check = Mock(return_value=(0.05, 0.03))

        # 대사를 mock 하지 않는다 — 진짜 대사를 통과해야 한다.
        asyncio.run(restorer._restore_holdings_from_real_account())

        a.sync_positions.assert_called_once()
        b.sync_positions.assert_called_once()
