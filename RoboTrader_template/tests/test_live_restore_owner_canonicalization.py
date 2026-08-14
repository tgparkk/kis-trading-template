"""복원 owner 라벨을 «전략 인스턴스» 기준으로 접는지 — 2표기/2전략 대칭 회귀.

배경 (2026-08-14 리뷰 R1 — Fix 3 가 만든 회귀):
  `_build_db_holdings_by_owner` 는 (종목코드, **원문 라벨**) 로 키를 잡았다.
  같은 전략이 두 표기로 기록되면(폴더키 'rs_leader' / 클래스명
  'RSLeaderStrategy') 한 전략이 «2 owner» 로 보여 수량이 쪼개진다. 그런데
  `_resolve_owner_strategy` 는 두 표기를 **같은 인스턴스**로 해석하고
  `BaseStrategy.sync_positions` 는 `dict.update()` 라서, 두 번째 주입이 첫
  번째를 덮어쓴다 → 계좌는 10주인데 전략은 5주만 보유한 줄 알고 그 5주에
  맞춰 청산을 건다.

  표기가 실제로 갈린다: `bot/candidate_loader.py:100` 은 **단일전략 모드**에서
  `self._bot.strategy.name`(클래스명)으로, `:186` 은 **다중전략 모드**에서
  폴더키로 등록한다(`:68` 이 스위치). 1↔2 전략 구성 변경을 거친 종목은 두
  표기의 행을 둘 다 갖는다 ⇒ **전략이 1개일 때도 터진다.**

  수정 전 동작(종목코드 단독 집계)은 이 입력에서 «옳았다»(슬롯 1개, 계좌
  수량 10). 그래서 이건 순수 회귀다.

리뷰 R5(권고):
  레그별 수량은 검사되지 않아 0/음수 레그가 `set_position` 과 POSITIONED 까지
  도달했다. 대사는 «합»만 보므로 `10+0`·`15+(-5)` 가 통과한다.
"""
import asyncio
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.broker_contract import make_account_balance, make_holding
from core.models import StockState
from utils.exceptions import LiveStartupAbort
from utils.korean_time import now_kst

KEY_A, CLS_A = 'rs_leader', 'RSLeaderStrategy'
KEY_B, CLS_B = 'elder_ema_pullback', 'ElderEmaPullbackStrategy'
CODE = '005930'


def _strats():
    a = Mock(); a.name = CLS_A
    b = Mock(); b.name = CLS_B
    return a, b


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


def _row(strategy, quantity, buy_price, rec_id):
    return {
        'id': rec_id, 'stock_code': CODE, 'stock_name': '삼성전자',
        'quantity': quantity, 'buy_price': buy_price, 'buy_time': now_kst(),
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


def _prepared(rows, broker_qty, strategies, avg_price=100_000.0):
    db = Mock()
    db.get_real_open_positions.return_value = pd.DataFrame(rows)
    db.get_virtual_open_positions.return_value = pd.DataFrame()
    restorer = _make_restorer(db, strategies, _broker(broker_qty, avg_price))
    _wire_trading_manager(restorer)
    restorer._sync_fund_manager_for_position = Mock(return_value=0.0)
    restorer._apply_stale_position_check = Mock(return_value=(0.05, 0.03))
    return restorer


def _legs(restorer, rows):
    by_owner = restorer._build_db_holdings_by_owner(pd.DataFrame(rows))
    return restorer._build_restore_legs(restorer.broker.get_holdings(), by_owner)


# ---------------------------------------------------------------------------
# 1. 같은 전략의 두 표기는 하나로 접힌다 / 다른 전략은 절대 안 접힌다
# ---------------------------------------------------------------------------

class TestSameStrategyTwoNotationsCollapse:
    def test_two_notations_of_one_strategy_produce_one_leg(self):
        a, _b = _strats()
        rows = [_row(KEY_A, 5, 69_000.0, 2), _row(CLS_A, 5, 71_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        legs = _legs(restorer, rows)

        assert len(legs) == 1, f"같은 전략이 2 owner 로 쪼개졌다: {legs}"
        # 단일 owner 로 접혔으므로 수정 전과 동일하게 계좌 수량·평단을 쓴다
        assert legs[0]['quantity'] == 10
        assert legs[0]['buy_price'] == 100_000.0

    def test_two_notations_strategy_sees_full_broker_quantity(self):
        """진입점: sync_positions 덮어쓰기로 절반만 보유한 줄 알면 안 된다."""
        a, _b = _strats()
        rows = [_row(KEY_A, 5, 69_000.0, 2), _row(CLS_A, 5, 71_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        asyncio.run(restorer._restore_holdings_from_real_account())

        a.sync_positions.assert_called_once()
        (pos,) = a.sync_positions.call_args[0]
        assert pos[CODE]['quantity'] == 10

    def test_two_distinct_strategies_still_split(self):
        """대칭: 인스턴스가 다르면 접지 않는다(Fix 3 의 본래 목적 유지)."""
        a, b = _strats()
        rows = [_row(KEY_A, 5, 100_000.0, 2), _row(KEY_B, 5, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a, KEY_B: b})

        asyncio.run(restorer._restore_holdings_from_real_account())

        (pos_a,) = a.sync_positions.call_args[0]
        (pos_b,) = b.sync_positions.call_args[0]
        assert pos_a[CODE]['quantity'] == 5
        assert pos_b[CODE]['quantity'] == 5

    def test_mixed_notations_across_two_strategies(self):
        """A 는 두 표기, B 는 한 표기 → 2 레그(A 7 / B 3), 대칭."""
        a, b = _strats()
        rows = [_row(CLS_A, 4, 100_000.0, 3), _row(KEY_A, 3, 100_000.0, 2),
                _row(KEY_B, 3, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a, KEY_B: b})

        asyncio.run(restorer._restore_holdings_from_real_account())

        (pos_a,) = a.sync_positions.call_args[0]
        (pos_b,) = b.sync_positions.call_args[0]
        assert pos_a[CODE]['quantity'] == 7
        assert pos_b[CODE]['quantity'] == 3

    def test_single_notation_is_unchanged(self):
        """회귀: 현행 데이터(라벨 1종)는 종전과 완전히 동일."""
        a, _b = _strats()
        rows = [_row(KEY_A, 10, 90_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        legs = _legs(restorer, rows)

        assert len(legs) == 1
        assert legs[0]['owner'] == KEY_A
        assert legs[0]['quantity'] == 10
        assert legs[0]['buy_price'] == 100_000.0


# ---------------------------------------------------------------------------
# 2. 미해석 owner — 한 바구니로 접고 «시끄럽게» 알린다
# ---------------------------------------------------------------------------

class TestUnresolvableOwners:
    def test_two_unresolvable_labels_collapse_into_one_leg(self):
        a, _b = _strats()
        rows = [_row('unknown', 4, 100_000.0, 2),
                _row('macd_cross', 6, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        legs = _legs(restorer, rows)

        assert len(legs) == 1
        assert legs[0]['quantity'] == 10

    def test_blank_and_unresolvable_share_the_same_bucket(self):
        a, _b = _strats()
        rows = [_row('', 4, 100_000.0, 2), _row('unknown', 6, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        assert len(_legs(restorer, rows)) == 1

    def test_resolvable_and_unresolvable_split_and_owner_keeps_its_share(self):
        """대칭: 살아있는 전략은 정확히 자기 몫만, 고아 몫은 남에게 안 준다.

        (빌더 수준 검증. 진입점은 아래처럼 고아를 만나면 기동을 중단한다.)
        """
        a, _b = _strats()
        rows = [_row(KEY_A, 7, 100_000.0, 2), _row('unknown', 3, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        legs = _legs(restorer, rows)

        assert len(legs) == 2
        by_owner = {leg['owner']: leg['quantity'] for leg in legs}
        assert by_owner[KEY_A] == 7
        assert by_owner['unknown'] == 3

    def test_orphan_leg_aborts_startup(self):
        """🔴 사장님 결정(2026-08-14): 고아 레그는 fail-closed = 기동 중단.

        미해석 라벨은 실전 도입기에 거의 항상 «설정 실수»(폴더명 오타·전략
        비활성화·표기 드리프트)다. 아무 전략도 소유하지 않는 실포지션을 안고
        하루를 굴리느니 멈추고 사람이 본다.
        """
        a, _b = _strats()
        rows = [_row(KEY_A, 7, 100_000.0, 2), _row('unknown', 3, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        with pytest.raises(LiveStartupAbort):
            asyncio.run(restorer._restore_holdings_from_real_account())

    def test_all_unresolvable_aborts_startup(self):
        """전량이 고아여도(=단일 레그) 마찬가지로 중단한다."""
        a, _b = _strats()
        rows = [_row('unknown', 10, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        with pytest.raises(LiveStartupAbort):
            asyncio.run(restorer._restore_holdings_from_real_account())

    def test_orphan_report_names_the_code_and_label(self, monkeypatch):
        """중단 사유는 진단 가능해야 한다 — 종목·라벨이 본문에 남는다."""
        import bot.state_restorer as sr
        a, _b = _strats()
        fake_logger = Mock()
        monkeypatch.setattr(sr, 'logger', fake_logger)
        rows = [_row(KEY_A, 7, 100_000.0, 2), _row('unknown', 3, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        orphans = restorer._detect_orphan_legs(_legs(restorer, rows))

        assert len(orphans) == 1
        assert CODE in orphans[0] and 'unknown' in orphans[0]
        assert fake_logger.error.called, "고아 레그가 ERROR 없이 지나갔다"

    def test_resolvable_only_logs_no_orphan_error(self, monkeypatch):
        """대칭: 정상 입력에서는 고아 ERROR 가 나오지 않는다(경보 마비 방지)."""
        import bot.state_restorer as sr
        a, b = _strats()
        fake_logger = Mock()
        monkeypatch.setattr(sr, 'logger', fake_logger)
        rows = [_row(KEY_A, 7, 100_000.0, 2), _row(KEY_B, 3, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a, KEY_B: b})

        assert restorer._detect_orphan_legs(_legs(restorer, rows)) == []
        assert not fake_logger.error.called

    def test_blank_strategy_column_on_a_db_row_aborts(self):
        """대칭 ①: DB 행이 있는데 strategy 컬럼이 비면 그건 진짜 고아다."""
        a, _b = _strats()
        rows = [_row('', 10, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        with pytest.raises(LiveStartupAbort):
            asyncio.run(restorer._restore_holdings_from_real_account())

    def test_leg_without_a_db_row_is_reconciliations_business(self):
        """대칭 ②: DB 행이 «아예 없는» 레그는 소유권이 아니라 대사의 소관이다.

        「실계좌에만 존재」는 _detect_holdings_mismatch 가 이미 fail-closed 로
        죽인다(프로덕션 도달 불가). 여기서 또 abort 하면 같은 입력에 중복
        차단이 생기고, 대사를 mock 한 기존 테스트들이 진단 불가로 죽는다.
        """
        a, _b = _strats()
        restorer = _prepared([], 10, {KEY_A: a})

        legs = restorer._build_restore_legs(restorer.broker.get_holdings(), {})

        assert len(legs) == 1 and legs[0]['owner'] == ""
        assert restorer._detect_orphan_legs(legs) == []

    def test_clean_input_does_not_abort(self):
        """🔴 대칭 단언 — 여기가 제일 중요하다.

        fail-closed 를 넣을 때 진짜 위험은 「아무도 진단 못 하는 기동 차단」이
        되는 것이다. 정상 입력이 **중단 없이 끝까지 복원되는지** 를 같이 고정해야
        고아 차단이 과잉으로 번지지 않는다.
        """
        a, b = _strats()
        rows = [_row(KEY_A, 7, 100_000.0, 2), _row(KEY_B, 3, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a, KEY_B: b})

        asyncio.run(restorer._restore_holdings_from_real_account())  # no raise

        a.sync_positions.assert_called_once()
        b.sync_positions.assert_called_once()

    def test_class_name_notation_is_not_treated_as_orphan(self):
        """대칭: 폴더키가 아니라 클래스명으로 적힌 라벨도 «해석된다» = 고아 아님.

        2단 해석(폴더키→클래스명)이 죽으면 정상 계좌가 통째로 기동 차단된다.
        """
        a, _b = _strats()
        rows = [_row(CLS_A, 10, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a})

        asyncio.run(restorer._restore_holdings_from_real_account())  # no raise

        a.sync_positions.assert_called_once()


# ---------------------------------------------------------------------------
# 3. 레그 수량 이상 — 대사는 «합»만 보므로 레그를 따로 본다 (리뷰 R5)
# ---------------------------------------------------------------------------

class TestLegQuantityAnomaly:
    def test_zero_quantity_leg_aborts_startup(self):
        a, b = _strats()
        rows = [_row(KEY_A, 10, 100_000.0, 2), _row(KEY_B, 0, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a, KEY_B: b})

        with pytest.raises(LiveStartupAbort):
            asyncio.run(restorer._restore_holdings_from_real_account())

    def test_negative_quantity_leg_aborts_startup(self):
        """합(15-5=10)이 계좌와 맞아 대사를 통과하던 입력."""
        a, b = _strats()
        rows = [_row(KEY_A, 15, 100_000.0, 2), _row(KEY_B, -5, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a, KEY_B: b})

        with pytest.raises(LiveStartupAbort):
            asyncio.run(restorer._restore_holdings_from_real_account())

    def test_healthy_legs_do_not_abort(self):
        """대칭: 정상 수량은 종전대로 통과한다(과잉 차단 금지)."""
        a, b = _strats()
        rows = [_row(KEY_A, 5, 100_000.0, 2), _row(KEY_B, 5, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a, KEY_B: b})

        asyncio.run(restorer._restore_holdings_from_real_account())

        a.sync_positions.assert_called_once()
        b.sync_positions.assert_called_once()

    def test_leg_builder_never_emits_nonpositive_leg(self):
        """방어선 2중화: 대사를 건너뛰고 빌더를 직접 불러도 0/음수는 안 나온다."""
        a, b = _strats()
        rows = [_row(KEY_A, 10, 100_000.0, 2), _row(KEY_B, 0, 100_000.0, 1)]
        restorer = _prepared(rows, 10, {KEY_A: a, KEY_B: b})

        legs = _legs(restorer, rows)

        assert all(leg['quantity'] > 0 for leg in legs)
        assert len(legs) == 1


# ---------------------------------------------------------------------------
# 4. 병합 상호작용 — 2 레그 전개 × 좁혀진 복원 경고 억제 (main 981d3cb)
# ---------------------------------------------------------------------------

class TestTwoLegExpansionUnderNarrowedSuppression:
    """`981d3cb` 은 복원 경고 억제를 «SELECTED → POSITIONED» 한 쌍으로 좁혔다.

    Fix 3 의 2 레그 전개는 같은 종목에 슬롯을 «두 개» 만들고 각각을 전이시키므로,
    억제 범위가 좁아진 뒤에도 두 레그 모두 그 쌍 안에 머무는지 확인해야 한다.
    (직전 리뷰의 증명은 넓은 형태 `ab383d0` 기준이었다.)

    로거는 `propagate=False` 라 caplog 로 안 잡힌다 — 진짜 로거에 핸들러를 붙여
    «방출 자체» 를 관측한다(test_restore_transition_warning 과 동일 관례).
    """

    ABNORMAL = "[비정상 상태전이]"

    class _Recorder(logging.Handler):
        def __init__(self):
            super().__init__(level=logging.DEBUG)
            self.records = []

        def emit(self, record):
            self.records.append(record)

    def _real_chain_restorer(self, rows, broker_qty, strategies):
        from core.trading_stock_manager import TradingStockManager
        db = Mock()
        db.get_real_open_positions.return_value = pd.DataFrame(rows)
        db.get_virtual_open_positions.return_value = pd.DataFrame()

        # intraday_manager.add_selected_stock 은 await 되므로 AsyncMock 이어야
        # 한다. 맨 Mock 이면 등록이 조용히 실패해(「0/2개 복원 완료」) 전이가
        # 아예 일어나지 않고, 「경고 0줄」이 통과해 버린다 — 아래 상태 단언이
        # 그 죽은 테스트를 잡는다.
        intraday = Mock()
        intraday.add_selected_stock = AsyncMock(return_value=True)
        tm = TradingStockManager(
            intraday_manager=intraday, data_collector=Mock(), order_manager=Mock())
        restorer = _make_restorer(db, strategies, _broker(broker_qty))
        restorer.trading_manager = tm
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)
        restorer._apply_stale_position_check = Mock(return_value=(0.05, 0.03))
        return restorer, tm

    def _run(self, rows, broker_qty, strategies):
        restorer, tm = self._real_chain_restorer(rows, broker_qty, strategies)
        sm = tm._state_manager
        rec = self._Recorder()
        sm.logger.addHandler(rec)
        try:
            asyncio.run(restorer._restore_holdings_from_real_account())
        finally:
            sm.logger.removeHandler(rec)
        msgs = [r.getMessage() for r in rec.records if self.ABNORMAL in r.getMessage()]
        return sm, msgs

    def test_two_leg_restore_emits_no_abnormal_transition_warning(self):
        a, b = _strats()
        rows = [_row(KEY_A, 5, 100_000.0, 2), _row(KEY_B, 5, 100_000.0, 1)]

        sm, abnormal = self._run(rows, 10, {KEY_A: a, KEY_B: b})

        assert abnormal == [], f"2 레그 전개가 경고를 남겼다: {abnormal}"
        # 그리고 전이가 «사라진» 게 아니라 실제로 두 슬롯 다 POSITIONED 여야 한다
        states = [ts.state for ts in sm._find_by_code(CODE)]
        assert len(states) == 2
        assert all(s == StockState.POSITIONED for s in states)

    def test_single_leg_restore_still_silent(self):
        """대칭: 1 레그(종전 형상)도 여전히 조용하다."""
        a, _b = _strats()
        rows = [_row(KEY_A, 10, 100_000.0, 1)]

        sm, abnormal = self._run(rows, 10, {KEY_A: a})

        assert abnormal == []
        states = [ts.state for ts in sm._find_by_code(CODE)]
        assert states == [StockState.POSITIONED]
