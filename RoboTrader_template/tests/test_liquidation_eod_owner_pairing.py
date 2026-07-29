"""EOD 청산 실패 추적의 (종목코드, owner) 쌍 키잉 검증

배경 (2026-07-29 독립 감사):
    `LiquidationHandler._eod_failed_stocks` 가 stock_code 문자열 집합이라
    두 전략이 같은 종목의 EOD 청산에 동시 실패하면 **한 항목으로 병합**되고,
    `_force_complete_failed_stocks()` 가 owner 없이 슬롯을 조회해
    **남의 슬롯 원가를 남의 소유자에게서 회수**한다.

    동일 결함 클래스: `f4c3683`(_position_owner) · `0eb4a5e`(보유종목 레지스트리).

이 파일의 1·2번 테스트는 수정 이전 코드에서 반드시 실패해야 한다(판별력).
"""

import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from bot.liquidation_handler import EOD_LIQUIDATION_MAX_RETRIES, LiquidationHandler
from core.models import Position, StockState, TradingStock

MA5 = "book_pullback_ma5"
MA20 = "book_pullback_ma20"
CODE = "037230"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stock(code=CODE, owner="", avg_price=50000.0, qty=10, name="테스트종목"):
    stock = TradingStock(
        stock_code=code,
        stock_name=name,
        state=StockState.POSITIONED,
        selected_time=datetime.datetime.now(),
    )
    stock.position = Position(stock_code=code, quantity=qty, avg_price=avg_price)
    stock.owner_strategy_name = owner
    stock.is_selling = False
    return stock


def _make_bot(stocks, virtual_sell=None):
    """StockStateManager._find_by_code 와 동일한 매칭 규약을 흉내낸 bot mock.

    strategy 미지정 시 삽입순 첫 슬롯을 반환한다 = 결함이 드러나는 지점.
    """
    bot = Mock()

    bot.trading_manager.get_stocks_by_state.return_value = stocks

    def _get_trading_stock(stock_code, strategy=None):
        matches = [s for s in stocks if s.stock_code == stock_code]
        if strategy is not None:
            matches = [s for s in matches if s.owner_strategy_name == strategy]
        return matches[0] if matches else None

    bot.trading_manager.get_trading_stock.side_effect = _get_trading_stock
    bot.trading_manager.move_to_sell_candidate.return_value = True
    bot.trading_manager.execute_sell_order = AsyncMock()
    bot.trading_manager._change_stock_state = Mock()

    bot.decision_engine.is_virtual_mode = True
    if virtual_sell is None:
        bot.decision_engine.execute_virtual_sell = AsyncMock(return_value=False)
    else:
        bot.decision_engine.execute_virtual_sell = AsyncMock(side_effect=virtual_sell)

    strategy = Mock()
    strategy.should_liquidate_eod.return_value = True
    bot.decision_engine.strategy = strategy

    bot.intraday_manager.get_combined_chart_data.return_value = None
    bot.broker.get_current_price.return_value = 51000

    bot.fund_manager.release_investment = Mock()
    bot.fund_manager.remove_position = Mock()
    bot.fund_manager.adjust_pnl = Mock()

    bot.telegram = None
    return bot


async def _run_eod(handler):
    with patch('bot.liquidation_handler.MarketHours') as mock_mh:
        mock_mh.get_market_hours.return_value = {
            'eod_liquidation_hour': 15,
            'eod_liquidation_minute': 20,
        }
        await handler.execute_end_of_day_liquidation()


def _entries(handler):
    """내부 표현을 (code, owner) 쌍 집합으로 정규화해 비교 가능하게 만든다.

    ⚠️ owner 는 **3값을 그대로 보존**한다 — named(문자열) / 무기명("") / 미상(None).
    `owner or None` 로 뭉개면 "" 소실 결함(2026-07-29 리뷰 HIGH)을 테스트가
    못 잡는다. 레거시 문자열 단독 항목만 (code, None) 으로 승격한다.

    프로덕션 헬퍼에 의존하지 않는다 — 수정을 되돌린 코드에서도 이 테스트가
    '결함' 때문에 실패해야지 'AttributeError' 로 실패하면 판별력이 없다.
    """
    out = set()
    for e in handler._eod_failed_stocks:
        if isinstance(e, tuple):
            out.add((e[0], e[1]))
        else:
            out.add((e, None))
    return out


# ---------------------------------------------------------------------------
# 1. 핵심 — 다중 소유 종목의 실패 항목이 병합되지 않는다
# ---------------------------------------------------------------------------

class TestFailedEntriesNotMerged:

    @pytest.mark.asyncio
    async def test_two_owners_both_fail_produce_two_entries(self):
        """같은 종목을 2전략이 보유하고 둘 다 청산 실패 → 항목 2개가 각각 남는다"""
        s_ma5 = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        s_ma20 = _make_stock(owner=MA20, avg_price=60000.0, qty=20)
        bot = _make_bot([s_ma5, s_ma20])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)

        assert _entries(handler) == {(CODE, MA5), (CODE, MA20)}
        assert len(handler._eod_failed_stocks) == 2

    @pytest.mark.asyncio
    async def test_two_owners_both_fail_survive_retry_round(self):
        """재시도에서도 둘 다 실패하면 두 항목이 그대로 유지된다(병합 금지)"""
        s_ma5 = _make_stock(owner=MA5)
        s_ma20 = _make_stock(owner=MA20)
        bot = _make_bot([s_ma5, s_ma20])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        result = await handler.retry_failed_eod_liquidation()

        assert result is False
        assert _entries(handler) == {(CODE, MA5), (CODE, MA20)}


# ---------------------------------------------------------------------------
# 2. 핵심 — 강제완료가 각 소유자의 실제 원가를 각자에게서 회수한다
# ---------------------------------------------------------------------------

class TestForceCompleteUsesOwnCost:

    @pytest.mark.asyncio
    async def test_each_owner_released_with_its_own_cost(self):
        """ma5=50000*10, ma20=60000*20 — 각자 자기 원가로 각자 owner 에게서 회수"""
        s_ma5 = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        s_ma20 = _make_stock(owner=MA20, avg_price=60000.0, qty=20)
        bot = _make_bot([s_ma5, s_ma20])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        await handler._force_complete_failed_stocks()

        released = {
            (c.kwargs['owner'], c.args[0])
            for c in bot.fund_manager.release_investment.call_args_list
        }
        assert released == {(MA5, 500000.0), (MA20, 1200000.0)}

        removed = {tuple(c.args) for c in bot.fund_manager.remove_position.call_args_list}
        assert removed == {(CODE, MA5), (CODE, MA20)}

    @pytest.mark.asyncio
    async def test_each_owner_state_changed_with_its_own_owner(self):
        """상태 전환도 각 소유자별로 1회씩, 자기 owner 로 전달된다"""
        s_ma5 = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        s_ma20 = _make_stock(owner=MA20, avg_price=60000.0, qty=20)
        bot = _make_bot([s_ma5, s_ma20])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        await handler._force_complete_failed_stocks()

        strategies = {
            c.kwargs['strategy'] for c in bot.trading_manager._change_stock_state.call_args_list
        }
        assert strategies == {MA5, MA20}
        assert bot.trading_manager._change_stock_state.call_count == 2

    @pytest.mark.asyncio
    async def test_force_complete_clears_all_pairs(self):
        """강제완료 후 두 항목 모두 비워진다"""
        bot = _make_bot([_make_stock(owner=MA5), _make_stock(owner=MA20)])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        await handler._force_complete_failed_stocks()

        assert len(handler._eod_failed_stocks) == 0


# ---------------------------------------------------------------------------
# 3. 재시도 루프가 올바른 슬롯을 집는다
# ---------------------------------------------------------------------------

class TestRetryPicksCorrectSlot:

    @pytest.mark.asyncio
    async def test_retry_targets_failing_owner_slot_not_first_slot(self):
        """ma5 는 성공·ma20 만 실패 → 재시도는 ma20 슬롯을 대상으로 한다"""
        s_ma5 = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        s_ma20 = _make_stock(owner=MA20, avg_price=60000.0, qty=20)

        async def _sell(trading_stock, price, reason):
            return trading_stock.owner_strategy_name != MA20

        bot = _make_bot([s_ma5, s_ma20], virtual_sell=_sell)
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        assert _entries(handler) == {(CODE, MA20)}

        bot.decision_engine.execute_virtual_sell.reset_mock()
        await handler.retry_failed_eod_liquidation()

        targets = [c.args[0] for c in bot.decision_engine.execute_virtual_sell.call_args_list]
        assert len(targets) == 1
        assert targets[0] is s_ma20

    @pytest.mark.asyncio
    async def test_retry_drops_entry_when_owner_slot_already_liquidated(self):
        """owner 슬롯이 사라졌으면(이미 청산) 남의 슬롯을 잡지 않고 항목을 정리한다"""
        s_ma5 = _make_stock(owner=MA5)
        s_ma20 = _make_stock(owner=MA20)
        bot = _make_bot([s_ma5, s_ma20])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        # ma20 슬롯만 실제로 청산되어 사라진 상황
        bot.trading_manager.get_stocks_by_state.return_value = [s_ma5]
        bot.decision_engine.execute_virtual_sell = AsyncMock(return_value=True)

        await handler.retry_failed_eod_liquidation()

        targets = [c.args[0] for c in bot.decision_engine.execute_virtual_sell.call_args_list]
        assert targets == [s_ma5]
        assert len(handler._eod_failed_stocks) == 0


# ---------------------------------------------------------------------------
# 4. owner=None 레거시 엔트리 폴백 + WARNING
# ---------------------------------------------------------------------------

class TestLegacyOwnerlessEntryFallback:

    @pytest.mark.asyncio
    async def test_bare_string_entry_still_force_completes(self):
        """레거시 문자열 단독 항목도 강제완료가 동작한다(코드 단독 조회 폴백)"""
        stock = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        bot = _make_bot([stock])
        handler = LiquidationHandler(bot)
        handler._eod_failed_stocks = {CODE}  # 구버전 표현

        await handler._force_complete_failed_stocks()

        bot.fund_manager.release_investment.assert_called_once_with(
            500000.0, stock_code=CODE, owner=MA5
        )

    @pytest.mark.asyncio
    async def test_bare_string_entry_logs_warning(self):
        """무기명 폴백은 조용히 넘어가지 않고 WARNING 을 남긴다"""
        bot = _make_bot([_make_stock(owner=MA5)])
        handler = LiquidationHandler(bot)
        handler._eod_failed_stocks = {CODE}

        with patch.object(handler.logger, 'warning') as mock_warn:
            await handler._force_complete_failed_stocks()

        messages = [str(c) for c in mock_warn.call_args_list]
        assert any('[EOD소유미상]' in m for m in messages), messages

    @pytest.mark.asyncio
    async def test_explicit_none_owner_pair_logs_warning(self):
        """(code, None) 쌍도 동일하게 폴백 + WARNING"""
        bot = _make_bot([_make_stock(owner=MA5)])
        handler = LiquidationHandler(bot)
        handler._eod_failed_stocks = {(CODE, None)}

        with patch.object(handler.logger, 'warning') as mock_warn:
            await handler._force_complete_failed_stocks()

        messages = [str(c) for c in mock_warn.call_args_list]
        assert any('[EOD소유미상]' in m for m in messages), messages

    @pytest.mark.asyncio
    async def test_retry_with_legacy_entry_warns_and_falls_back(self):
        """재시도 경로의 무기명 폴백도 WARNING 을 남기고 첫 슬롯으로 진행한다"""
        stock = _make_stock(owner=MA5)
        bot = _make_bot([stock])
        bot.decision_engine.execute_virtual_sell = AsyncMock(return_value=True)
        handler = LiquidationHandler(bot)
        handler._eod_failed_stocks = {CODE}

        with patch.object(handler.logger, 'warning') as mock_warn:
            result = await handler.retry_failed_eod_liquidation()

        assert result is True
        messages = [str(c) for c in mock_warn.call_args_list]
        assert any('[EOD소유미상]' in m for m in messages), messages
        targets = [c.args[0] for c in bot.decision_engine.execute_virtual_sell.call_args_list]
        assert targets == [stock]

    @pytest.mark.asyncio
    async def test_unnamed_slot_preserves_empty_owner_not_none(self):
        """무기명 슬롯("")은 ""로 보존된다 — None(미상)으로 뭉개지 않는다.

        "" 는 버릴 정보가 아니라 `_find_by_code(code, "")` 로 **무기명 슬롯만**
        정확 매칭되는 가장 정밀한 키다. None 으로 뭉개면 필터가 해제되어
        남의 슬롯이 후보에 들어온다.
        """
        bot = _make_bot([_make_stock(owner="")])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)

        assert _entries(handler) == {(CODE, "")}

    @pytest.mark.asyncio
    async def test_unnamed_entry_does_not_take_unknown_owner_fallback(self):
        """무기명("")은 정확 매칭되므로 [EOD소유미상] 폴백 경로를 타지 않는다"""
        bot = _make_bot([_make_stock(owner="")])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        with patch.object(handler.logger, 'warning') as mock_warn:
            await handler._force_complete_failed_stocks()

        messages = [str(c) for c in mock_warn.call_args_list]
        assert not any('[EOD소유미상]' in m for m in messages), messages


# ---------------------------------------------------------------------------
# 4-b. [HIGH] 무기명("") owner 가 뭉개지면 건강한 named 포지션이 파괴된다
# ---------------------------------------------------------------------------

class TestUnnamedOwnerDoesNotHijackNamedSlot:
    """2026-07-29 독립 리뷰 HIGH 재현.

    `_slot_owner` 가 `or None` 로 ""를 None 으로 뭉개면:
      실패항목 (CODE,"") → (CODE,None) → 소유미상 폴백 → 삽입순 첫 슬롯(=named)
      → **정상 매도된 named 의 원가를 회수하고 그 포지션을 파괴**하며,
        진짜 실패한 무기명 포지션은 손도 안 댄 채 남는다.
    """

    @pytest.mark.asyncio
    async def test_unnamed_failure_does_not_destroy_named_position(self):
        s_named = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        s_anon = _make_stock(owner="", avg_price=60000.0, qty=20)

        async def _sell(trading_stock, price, reason):
            # named 는 정상 매도 성공, 무기명만 청산 실패
            return trading_stock.owner_strategy_name != ""

        bot = _make_bot([s_named, s_anon], virtual_sell=_sell)
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        assert _entries(handler) == {(CODE, "")}

        await handler._force_complete_failed_stocks()

        # 회수는 진짜 실패한 무기명 쪽 원가(60000*20)만
        bot.fund_manager.release_investment.assert_called_once_with(
            1200000.0, stock_code=CODE, owner=""
        )
        bot.fund_manager.remove_position.assert_called_once_with(CODE, "")

        # 정상 매도된 named 포지션은 파괴되지 않아야 한다
        assert s_named.position is not None
        assert s_named.position.quantity == 10
        # 무기명 쪽은 강제완료되어 클리어
        assert s_anon.position is None

    @pytest.mark.asyncio
    async def test_unnamed_and_named_both_fail_stay_separate(self):
        """무기명과 named 가 동시 실패해도 두 항목이 각각 남는다"""
        s_named = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        s_anon = _make_stock(owner="", avg_price=60000.0, qty=20)
        bot = _make_bot([s_named, s_anon])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)

        assert _entries(handler) == {(CODE, MA5), (CODE, "")}

        await handler._force_complete_failed_stocks()
        released = {
            (c.kwargs['owner'], c.args[0])
            for c in bot.fund_manager.release_investment.call_args_list
        }
        assert released == {(MA5, 500000.0), ("", 1200000.0)}

    @pytest.mark.asyncio
    async def test_retry_matches_unnamed_slot_not_named_slot(self):
        """재시도도 무기명 항목에 대해 무기명 슬롯을 집는다"""
        s_named = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        s_anon = _make_stock(owner="", avg_price=60000.0, qty=20)

        async def _sell(trading_stock, price, reason):
            return trading_stock.owner_strategy_name != ""

        bot = _make_bot([s_named, s_anon], virtual_sell=_sell)
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        bot.decision_engine.execute_virtual_sell.reset_mock()
        await handler.retry_failed_eod_liquidation()

        targets = [c.args[0] for c in bot.decision_engine.execute_virtual_sell.call_args_list]
        assert targets == [s_anon]


# ---------------------------------------------------------------------------
# 4-c. [MEDIUM] fail-closed — owner 슬롯 부재 시 남의 슬롯을 건드리지 않는다
# ---------------------------------------------------------------------------

class TestForceCompleteFailsClosed:
    """owner 지정 조회가 비면 **아무것도 하지 않는다**.

    구 코드는 코드 단독 조회라 남의 슬롯을 잡아 release/remove/state 3콜을
    날리고 그 포지션을 파괴했다. 자금 회수를 건너뛰는 쪽이 안전하다:
    `invested_funds` 는 영속되지 않고 강제완료는 DB 부작용이 0이라
    다음 기동 재구성 결과가 동일하다(2026-07-29 리뷰 실측).
    """

    @pytest.mark.asyncio
    async def test_skips_when_named_owner_slot_absent_but_other_owner_present(self):
        other = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        bot = _make_bot([other])
        handler = LiquidationHandler(bot)
        # MA20 소유분의 실패 항목인데 MA20 슬롯은 이미 사라진 상태
        handler._eod_failed_stocks = {(CODE, MA20)}

        await handler._force_complete_failed_stocks()

        bot.fund_manager.release_investment.assert_not_called()
        bot.fund_manager.remove_position.assert_not_called()
        bot.trading_manager._change_stock_state.assert_not_called()

        # 남의(MA5) 포지션은 온전해야 한다
        assert other.position is not None
        assert other.position.quantity == 10
        assert len(handler._eod_failed_stocks) == 0

    @pytest.mark.asyncio
    async def test_skips_when_unnamed_owner_slot_absent_but_named_present(self):
        """무기명 항목인데 무기명 슬롯이 없으면 named 를 대신 잡지 않는다"""
        named = _make_stock(owner=MA5, avg_price=50000.0, qty=10)
        bot = _make_bot([named])
        handler = LiquidationHandler(bot)
        handler._eod_failed_stocks = {(CODE, "")}

        await handler._force_complete_failed_stocks()

        bot.fund_manager.release_investment.assert_not_called()
        assert named.position is not None


# ---------------------------------------------------------------------------
# 5. 단일 소유 회귀 — 기존 동작 불변
# ---------------------------------------------------------------------------

class TestSingleOwnerRegression:

    @pytest.mark.asyncio
    async def test_single_owner_failure_tracked_once(self):
        bot = _make_bot([_make_stock(owner=MA5)])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)

        assert _entries(handler) == {(CODE, MA5)}
        assert handler.has_failed_eod_stocks() is True

    @pytest.mark.asyncio
    async def test_single_owner_success_tracks_nothing(self):
        bot = _make_bot([_make_stock(owner=MA5)], virtual_sell=None)
        bot.decision_engine.execute_virtual_sell = AsyncMock(return_value=True)
        handler = LiquidationHandler(bot)

        await _run_eod(handler)

        assert len(handler._eod_failed_stocks) == 0
        assert handler.has_failed_eod_stocks() is False

    @pytest.mark.asyncio
    async def test_single_owner_retry_then_force_complete(self):
        """단일 소유: 한도 초과 시 강제완료가 그 소유자로 1회 회수"""
        bot = _make_bot([_make_stock(owner=MA5, avg_price=50000.0, qty=10)])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        handler._eod_retry_count = EOD_LIQUIDATION_MAX_RETRIES
        result = await handler.retry_failed_eod_liquidation()

        assert result is False
        bot.fund_manager.release_investment.assert_called_once_with(
            500000.0, stock_code=CODE, owner=MA5
        )
        bot.fund_manager.remove_position.assert_called_once_with(CODE, MA5)
        assert len(handler._eod_failed_stocks) == 0

    @pytest.mark.asyncio
    async def test_reset_eod_state_clears_pairs(self):
        bot = _make_bot([_make_stock(owner=MA5), _make_stock(owner=MA20)])
        handler = LiquidationHandler(bot)

        await _run_eod(handler)
        handler.reset_eod_state()

        assert len(handler._eod_failed_stocks) == 0
        assert handler._eod_retry_count == 0

    @pytest.mark.asyncio
    async def test_real_mode_move_failure_tracks_pair(self):
        """실매매 경로의 실패 항목도 쌍으로 기록된다"""
        s_ma5 = _make_stock(owner=MA5)
        s_ma20 = _make_stock(owner=MA20)
        bot = _make_bot([s_ma5, s_ma20])
        bot.decision_engine.is_virtual_mode = False
        bot.trading_manager.move_to_sell_candidate.return_value = False
        handler = LiquidationHandler(bot)

        await _run_eod(handler)

        assert _entries(handler) == {(CODE, MA5), (CODE, MA20)}

    @pytest.mark.asyncio
    async def test_individual_exception_tracks_pair(self):
        """개별 예외 경로도 owner 를 잃지 않는다"""
        s_ma5 = _make_stock(owner=MA5)
        s_ma20 = _make_stock(owner=MA20)

        async def _boom(trading_stock, price, reason):
            raise RuntimeError("네트워크 오류")

        bot = _make_bot([s_ma5, s_ma20], virtual_sell=_boom)
        handler = LiquidationHandler(bot)

        await _run_eod(handler)

        assert _entries(handler) == {(CODE, MA5), (CODE, MA20)}
