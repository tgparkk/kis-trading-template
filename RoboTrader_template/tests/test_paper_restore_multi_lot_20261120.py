"""페이퍼 보유 복원 — 같은 전략·같은 종목의 열린 매수 로트 2개가 둘 다 감시된다 (2026-11-20 결함).

사실: 028300 `deep_mr_dev20` 에 열린 BUY 2행 — rid 3603(40주 @28,400 · 11-18) · rid 3633(17주 @26,850 ·
11-19). 11-20 07:40 복원이 `ORDER BY timestamp DESC` 순으로 돌며 3633 을 슬롯에 올린 뒤 3603 이 같은 슬롯을
덮어썼다(`[비정상 상태전이] positioned → positioned`). 17주 로트는 손절·익절·보유기간 감시 밖이었고, 40주
로트가 팔리면 런타임에 028300 이 없어 같은 전략이 또 살 수 있었다.

고정하는 것(설계 B · 로트별 순차 감시):
  1. 복원: 슬롯(종목×전략 1개)엔 가장 먼저 산 로트(3603)가 감시 로트로 올라가고, 나머지(3633)는 그 슬롯의
     대기 로트로 쌓인다. `positioned → positioned` 경고 0 · 관문 줄 `N/M` 은 M/M(두 로트 다 셈) · 자금 장부와
     전략 원장엔 두 로트 다 · 전략 포지션 주입은 감시 로트 · 별도 WARNING 줄(관문 정규식 불일치).
  2. 감시 로트가 손절되면 재기동 없이 곧바로 대기 로트가 그 로트의 진입가·손절/익절률·보유일로 올라온다 →
     그 로트도 자기 손절선으로 팔린다. SELL 은 로트마다 1행(자기 buy_record_id · 자기 수량).
  3. 승계 직후에도 「보유 중 무시」 가드가 슬롯을 본다(같은 전략 중복 매수 없음).

KIS·DB 에 닿지 않는다 — 브로커·DB 는 페이크.
"""
import re
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401,E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from core.models import StockState  # noqa: E402
from utils.korean_holidays import count_trading_days_between  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402

GATE_RE = re.compile(r"보유 종목 (\d+)/(\d+)개 복원 완료|보유 종목 없음")
OWNER = "deep_mr_dev20"
CODE = "028300"


def _daily_df(n=103):
    closes = np.full(n, 30_000.0)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": np.full(n, 100_000.0),
    })


def _holding(code, qty, price, buy_time, row_id, tp=0.12, sl=0.07, owner=OWNER):
    return {
        "id": row_id, "stock_code": code, "stock_name": code, "quantity": qty,
        "buy_price": price, "buy_time": buy_time, "strategy": owner,
        "target_profit_rate": tp, "stop_loss_rate": sl,
    }


def _rows():
    """get_virtual_open_positions 와 같은 순서(timestamp DESC) — 나중 로트가 먼저 온다."""
    now = now_kst()
    bt_new = now - timedelta(days=1)   # 3633 · 11-19 에 해당
    bt_old = now - timedelta(days=5)   # 3603 · 11-18 에 해당
    rows = [
        _holding(CODE, 17, 26_850.0, bt_new, 3633),
        _holding("417010", 104, 6_210.0, now - timedelta(days=3), 3501),
        _holding(CODE, 40, 28_400.0, bt_old, 3603),
    ]
    return rows, bt_old, bt_new


def _strategy():
    from strategies.deep_mr_dev20.strategy import DeepMrDev20Strategy
    strat = DeepMrDev20Strategy({"paper_trading": True})
    strat.on_init(None, None, None)
    strat.logger = Mock()
    return strat


def _build(holdings, strategy, fund_manager, vtm=None, strategies=None):
    """실체 TradingStockManager + IntradayStockManager(리밸런싱 모드) + StateRestorer(페이퍼)."""
    from bot.state_restorer import StateRestorer
    from core.intraday_stock_manager import IntradayStockManager
    from core.trading_stock_manager import TradingStockManager

    broker = Mock()
    broker.get_ohlcv_data = Mock(side_effect=lambda code, period, count: _daily_df())
    intraday = IntradayStockManager(broker, SimpleNamespace(rebalancing_mode=True))
    intraday.data_collector._save_daily_to_db = AsyncMock(return_value=True)  # DB 쓰기 0
    data_collector = MagicMock()
    data_collector.get_stock.return_value = None
    tsm = TradingStockManager(intraday, data_collector, MagicMock(), None)
    tsm._state_manager.logger = Mock()   # [비정상 상태전이] 경고 포착

    db = Mock()
    db.get_virtual_open_positions.return_value = pd.DataFrame(holdings)
    db.get_strategy_trade_sums.return_value = {}
    config = Mock()
    config.paper_trading = True
    r = StateRestorer(
        trading_manager=tsm, db_manager=db, telegram_integration=None, config=config,
        get_previous_close_callback=lambda code: 30_000.0, broker=broker, fund_manager=fund_manager,
        virtual_trading_manager=vtm,
        strategies=strategies if strategies is not None else {OWNER: strategy},
    )
    return r, tsm, intraday


async def _restore(r):
    with patch("bot.state_restorer.logger") as log:
        await r._restore_holdings_from_db()
    infos = [str(c.args[0]) for c in log.info.call_args_list if c.args]
    warns = [str(c.args[0]) for c in log.warning.call_args_list if c.args]
    errors = [str(c.args[0]) for c in log.error.call_args_list if c.args]
    return infos, warns, errors


def _abnormal(tsm):
    return [str(c.args[0]) for c in tsm._state_manager.logger.warning.call_args_list
            if c.args and "비정상 상태전이" in str(c.args[0])]


def _ledger_vtm():
    vtm = Mock()
    vtm._strategy_balances = {OWNER: 10_000_000.0}
    vtm.get_virtual_balance.return_value = 10_000_000.0
    return vtm


def _engine(tsm, fm, strat):
    """가상모드 실엔진 — VTM 은 실체(원장 미사용 = 레거시 단일 잔고) · DB 는 페이크."""
    from core.trading_decision_engine import TradingDecisionEngine
    engine = TradingDecisionEngine(trading_manager=tsm, config=None)   # config None → 가상모드
    engine.set_fund_manager(fm)
    engine.set_strategies({OWNER: strat})
    db = Mock()
    db.save_virtual_sell = Mock(return_value=True)
    engine.virtual_trading.db_manager = db
    engine.db_manager = None
    return engine, db


class TestRestoreQueuesSecondLotOnSameSlot:

    @pytest.mark.asyncio
    async def test_oldest_lot_is_watched_and_newer_lot_waits_on_the_same_slot(self):
        from core.fund_manager import FundManager

        rows, bt_old, bt_new = _rows()
        strat = _strategy()
        fm = FundManager(initial_funds=50_000_000)
        vtm = _ledger_vtm()
        r, tsm, _ = _build(rows, strat, fm, vtm=vtm)

        infos, warns, errors = await _restore(r)

        slot = tsm.get_trading_stock(CODE, strategy=OWNER)
        assert slot is not None and slot.state == StockState.POSITIONED
        # 감시 로트 = 가장 먼저 산 로트(3603) — 덮어쓰기가 아니라 «선택»
        assert slot.position.quantity == 40
        assert slot.position.avg_price == pytest.approx(28_400.0)
        assert slot._virtual_buy_record_id == 3603
        assert slot.days_held == count_trading_days_between(
            bt_old.replace(tzinfo=None), now_kst().replace(tzinfo=None))
        # 대기 로트 = 3633 — 자기 진입가·수량·손절/익절률·보유일을 가진 채
        (lot,) = slot._queued_restored_lots
        assert lot["buy_record_id"] == 3633 and lot["quantity"] == 17
        assert lot["buy_price"] == pytest.approx(26_850.0)
        assert lot["stop_loss_rate"] == pytest.approx(0.07) and lot["target_profit_rate"] == pytest.approx(0.12)
        assert lot["days_held"] == count_trading_days_between(
            bt_new.replace(tzinfo=None), now_kst().replace(tzinfo=None))
        assert lot["days_held"] < slot.days_held
        # 같은 슬롯에 복원이 두 번 내려앉지 않는다
        assert _abnormal(tsm) == []
        # 관문 줄 = 형식 불변 · 두 로트 다 셈(M/M)
        (gate,) = [line for line in infos if GATE_RE.search(line)]
        assert GATE_RE.search(gate).groups() == ("3", "3")
        # 별도 WARNING 줄 — 두 로트가 보이고 관문 정규식엔 안 걸린다
        (multi,) = [w for w in warns if "열린 매수 로트" in w]
        assert CODE in multi and "3603" in multi and "3633" in multi
        assert not GATE_RE.search(multi)
        assert "손절가가 감시 로트" not in multi     # 대기 로트 손절가 24,970 < 감시 로트 26,412
        assert not [e for e in errors if "복원 불가" in e]
        # 자금 장부엔 두 로트 금액 다 · 엔트리는 (종목, 전략) 단위
        assert fm.invested_funds == pytest.approx(40 * 28_400 + 17 * 26_850 + 104 * 6_210)
        assert fm._position_entries == {(CODE, OWNER), ("417010", OWNER)}
        # 전략 원장 재구성엔 두 로트(각자 buy_record_id)
        open_positions = vtm.restore_strategy_ledger_from_records.call_args.args[2]
        assert sorted(p["buy_record_id"] for p in open_positions if p["stock_code"] == CODE) == [3603, 3633]
        # 전략 포지션 주입 = 감시 로트
        assert r.apply_pending_strategy_positions() == 1
        assert strat.positions[CODE]["entry_price"] == pytest.approx(28_400.0)
        assert strat.positions[CODE]["quantity"] == 40


class TestWatchedLotExitPromotesNextLot:

    @pytest.mark.asyncio
    async def test_stop_loss_on_watched_lot_promotes_waiting_lot_which_then_stops_on_its_own_line(self):
        from bot.trading_analyzer import TradingAnalyzer
        from core.fund_manager import FundManager

        rows, _, bt_new = _rows()
        strat = _strategy()
        fm = FundManager(initial_funds=50_000_000)
        r, tsm, intraday = _build(rows, strat, fm)
        await _restore(r)
        r.apply_pending_strategy_positions()
        slot = tsm.get_trading_stock(CODE, strategy=OWNER)

        engine, db = _engine(tsm, fm, strat)
        pm = tsm._position_monitor
        pm.set_decision_engine(engine)
        tsm.set_paper_trading(True)
        prices = {CODE: 26_300.0, "417010": 6_210.0}
        intraday.get_current_price_for_sell = Mock(side_effect=lambda c: {"current_price": prices[c]})
        fixed = now_kst().replace(hour=10, minute=30, second=0, microsecond=0)

        # ① 26,300 = 3603 기준 −7.39%(손절) · 3633 기준 −2.05%(아님) → 3603 만 팔린다
        with patch("core.trading.position_monitor.now_kst", return_value=fixed):
            await pm._check_positioned_stocks_for_sell()

        (first,) = db.save_virtual_sell.call_args_list
        assert first.kwargs["buy_record_id"] == 3603 and first.kwargs["quantity"] == 40
        # 재기동 없이 곧바로 3633 이 같은 슬롯에 올라온다 — 자기 진입가·손절/익절률·보유일
        assert slot.state == StockState.POSITIONED
        assert slot.position.quantity == 17
        assert slot.position.avg_price == pytest.approx(26_850.0)
        assert slot._virtual_buy_record_id == 3633 and slot._virtual_quantity == 17
        assert slot.stop_loss_rate == pytest.approx(0.07) and slot.target_profit_rate == pytest.approx(0.12)
        assert slot.days_held == count_trading_days_between(
            bt_new.replace(tzinfo=None), now_kst().replace(tzinfo=None))
        assert slot._queued_restored_lots == []
        assert slot.is_selling is False
        assert _abnormal(tsm) == []
        # 자금 장부: 3603 만 회수 · 엔트리는 남는다
        assert fm.invested_funds == pytest.approx(17 * 26_850 + 104 * 6_210)
        assert (CODE, OWNER) in fm._position_entries
        # 전략 포지션 = 3633 (3603 매도 통보로 빠진 뒤 다시 들어옴)
        assert strat.positions[CODE]["entry_price"] == pytest.approx(26_850.0)
        assert strat.positions[CODE]["quantity"] == 17

        # 승계 직후 「보유 중 무시」 가드가 슬롯을 본다 → 같은 전략 중복 매수 없음
        bot = MagicMock()
        bot.trading_manager = tsm
        bot.strategies = {OWNER: strat}
        analyzer = TradingAnalyzer(bot)
        analyzer.logger = Mock()
        candidate = Mock(stock_code=CODE, stock_name=CODE)
        assert not await analyzer.analyze_buy_decision(candidate, available_funds=1_000_000, strategy_name=OWNER)
        assert any("보유 중인 종목 매수 신호 무시" in str(c.args[0]) for c in analyzer.logger.info.call_args_list)

        # ② 24,900 = 3633 기준 −7.26%(자기 손절선) → 3633 이 팔린다 · SELL 은 로트마다 1행
        prices[CODE] = 24_900.0
        with patch("core.trading.position_monitor.now_kst", return_value=fixed):
            await pm._check_positioned_stocks_for_sell()

        assert [(c.kwargs["buy_record_id"], c.kwargs["quantity"]) for c in db.save_virtual_sell.call_args_list] \
            == [(3603, 40), (3633, 17)]
        assert slot.state == StockState.COMPLETED and slot.position is None
        assert fm.invested_funds == pytest.approx(104 * 6_210)
        assert (CODE, OWNER) not in fm._position_entries
        assert CODE not in strat.positions
        assert _abnormal(tsm) == []

    @pytest.mark.asyncio
    async def test_waiting_lot_is_not_sold_by_the_watched_lots_signal(self):
        """대기 로트는 감시 로트의 청산 사유로 같이 팔리지 않는다 — 승계 뒤 자기 기준으로만 판단."""
        from core.fund_manager import FundManager

        rows, _, _ = _rows()
        strat = _strategy()
        fm = FundManager(initial_funds=50_000_000)
        r, tsm, intraday = _build(rows, strat, fm)
        await _restore(r)
        slot = tsm.get_trading_stock(CODE, strategy=OWNER)

        engine, db = _engine(tsm, fm, strat)
        pm = tsm._position_monitor
        pm.set_decision_engine(engine)
        tsm.set_paper_trading(True)
        prices = {CODE: 26_300.0, "417010": 6_210.0}
        intraday.get_current_price_for_sell = Mock(side_effect=lambda c: {"current_price": prices[c]})
        fixed = now_kst().replace(hour=10, minute=30, second=0, microsecond=0)

        with patch("core.trading.position_monitor.now_kst", return_value=fixed):
            await pm._check_positioned_stocks_for_sell()   # 3603 손절 → 3633 승계
            await pm._check_positioned_stocks_for_sell()   # 같은 가격 = 3633 기준 −2.05% → 안 팔림

        assert [c.kwargs["buy_record_id"] for c in db.save_virtual_sell.call_args_list] == [3603]
        assert slot.state == StockState.POSITIONED and slot._virtual_buy_record_id == 3633


async def _restored(rows, strategies=None):
    """복원까지 끝낸 (restorer, tsm, slot, strat, fm, warns) — 전략 포지션 재주입 포함."""
    from core.fund_manager import FundManager
    strat = _strategy()
    fm = FundManager(initial_funds=50_000_000)
    r, tsm, _ = _build(rows, strat, fm, strategies=strategies)
    _, warns, _ = await _restore(r)
    r.apply_pending_strategy_positions()
    return r, tsm, tsm.get_trading_stock(CODE, strategy=OWNER), strat, fm, warns


class TestReviewFollowUps:
    """리뷰(2026-11-20) 후속 — 교차 보유 · 매도 실패 · 승계 실패 되돌림 · 비활성 owner · 로트 3개."""

    @pytest.mark.asyncio
    async def test_other_strategy_same_code_is_not_grouped(self):
        """ⓐ 다른 전략·같은 종목(교차 보유)은 묶지 않는다 — 전략마다 자기 슬롯 · 대기 로트 없음."""
        other = "book_pullback_ma20"
        now = now_kst()
        rows = [
            _holding(CODE, 17, 26_850.0, now - timedelta(days=1), 3633, owner=other),
            _holding(CODE, 40, 28_400.0, now - timedelta(days=5), 3603),
        ]
        other_strat = SimpleNamespace(name="BookPullbackMa20Strategy", max_holding_days=None,
                                      sync_positions=Mock())
        from core.fund_manager import FundManager
        strat = _strategy()
        fm = FundManager(initial_funds=50_000_000)
        r, tsm, _ = _build(rows, strat, fm, strategies={OWNER: strat, other: other_strat})
        infos, warns, _ = await _restore(r)

        mine = tsm.get_trading_stock(CODE, strategy=OWNER)
        theirs = tsm.get_trading_stock(CODE, strategy=other)
        assert mine is not theirs
        assert (mine._virtual_buy_record_id, mine.position.quantity, mine.state) == (3603, 40, StockState.POSITIONED)
        assert (theirs._virtual_buy_record_id, theirs.position.quantity, theirs.state) == (3633, 17, StockState.POSITIONED)
        assert mine._queued_restored_lots == [] and theirs._queued_restored_lots == []
        assert not [w for w in warns if "열린 매수 로트" in w]
        (gate,) = [line for line in infos if GATE_RE.search(line)]
        assert GATE_RE.search(gate).groups() == ("2", "2")
        assert _abnormal(tsm) == []
        assert fm._position_entries == {(CODE, OWNER), (CODE, other)}

    @pytest.mark.asyncio
    async def test_failed_sell_does_not_promote(self):
        """ⓑ 매도 실패(VTM False) → 승계 없음 · 감시 로트·대기 로트 그대로."""
        rows, _, _ = _rows()
        r, tsm, slot, strat, fm, _ = await _restored(rows)
        engine, db = _engine(tsm, fm, strat)
        engine.virtual_trading.execute_virtual_sell = Mock(return_value=False)

        ok = await engine.execute_virtual_sell(slot, 26_300.0, "손절")

        assert ok is False
        assert (slot._virtual_buy_record_id, slot.position.quantity) == (3603, 40)
        assert [lot["buy_record_id"] for lot in slot._queued_restored_lots] == [3633]
        assert strat.positions[CODE]["entry_price"] == pytest.approx(28_400.0)
        db.save_virtual_sell.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("break_at", ["mid_promotion", "bad_lot_value"])
    async def test_promotion_failure_reverts_to_post_sell_state(self, break_at):
        """ⓒ 승계 중 예외 → 슬롯 = «매도 직후» 상태(COMPLETED · 포지션/매수정보 없음 · 엔트리·전략 포지션
        없음) · 매도는 True · 남은 로트는 SELL 이 없어 DB 열린 로트 → 다음 기동 복원이 다시 올린다."""
        rows, _, _ = _rows()
        r, tsm, slot, strat, fm, _ = await _restored(rows)
        engine, db = _engine(tsm, fm, strat)
        engine.logger = Mock()
        if break_at == "mid_promotion":     # 상태 전이 «뒤» 에서 터짐
            fm.add_position = Mock(side_effect=RuntimeError("boom"))
        else:                               # 값 변환에서 터짐(상태 변경 «전»)
            slot._queued_restored_lots[0]["quantity"] = "x"

        ok = await engine.execute_virtual_sell(slot, 26_300.0, "손절")

        assert ok is True
        assert slot.state == StockState.COMPLETED
        assert slot.position is None and slot._virtual_buy_record_id is None and not slot.has_virtual_position()
        assert slot._queued_restored_lots == []
        assert (CODE, OWNER) not in fm._position_entries
        assert CODE not in strat.positions
        assert _abnormal(tsm) == []
        (err,) = [str(c.args[0]) for c in engine.logger.error.call_args_list if "대기 로트 승계 실패" in str(c.args[0])]
        assert "state=completed" in err and "포지션 없음" in err and "3633" in err
        # DB 기준: SELL 은 3603 하나 → 3633 은 열린 로트로 남아 다음 기동 복원 대상
        sold = {c.kwargs["buy_record_id"] for c in db.save_virtual_sell.call_args_list}
        assert sold == {3603}
        _, tsm2, slot2, _, _, _ = await _restored([row for row in rows if row["id"] not in sold])
        assert slot2.state == StockState.POSITIONED and slot2._virtual_buy_record_id == 3633
        assert slot2._queued_restored_lots == []

    @pytest.mark.asyncio
    async def test_promotion_call_error_still_returns_recorded_sell_as_true(self):
        """L2 — 승계 호출 자체가 터져도 이미 기록된 매도는 True(재시도가 다른 로트를 팔지 않게)."""
        rows, _, _ = _rows()
        r, tsm, slot, strat, fm, _ = await _restored(rows)
        engine, db = _engine(tsm, fm, strat)
        engine._promote_queued_restored_lot = Mock(side_effect=RuntimeError("boom"))

        assert await engine.execute_virtual_sell(slot, 26_300.0, "손절") is True
        assert [c.kwargs["buy_record_id"] for c in db.save_virtual_sell.call_args_list] == [3603]

    @pytest.mark.asyncio
    async def test_inactive_owner_does_not_pollute_default_strategy(self):
        """ⓓ owner 가 비활성(전략 맵에 없음)이면 승계는 하되 기본 전략 positions 에 주입하지 않는다."""
        from core.fund_manager import FundManager
        rows, _, _ = _rows()
        fm = FundManager(initial_funds=50_000_000)
        r, tsm, _ = _build(rows, None, fm, strategies={})
        await _restore(r)
        slot = tsm.get_trading_stock(CODE, strategy=OWNER)
        assert slot.owner_strategy is None

        from core.trading_decision_engine import TradingDecisionEngine
        engine = TradingDecisionEngine(trading_manager=tsm, config=None)
        engine.set_fund_manager(fm)
        default = Mock()
        default.positions = {}
        engine.set_strategy(default)
        engine.virtual_trading.db_manager = Mock(save_virtual_sell=Mock(return_value=True))

        assert await engine.execute_virtual_sell(slot, 26_300.0, "손절") is True

        assert slot.state == StockState.POSITIONED and slot._virtual_buy_record_id == 3633
        default.sync_positions.assert_not_called()
        assert default.positions == {}

    @pytest.mark.asyncio
    async def test_three_lots_promote_in_buy_order_and_note_higher_stop(self):
        """ⓔ 로트 3개 — 먼저 산 순서로 감시·승계 · SELL 은 로트마다 1행. 나중 로트 손절가가 더 높으면
        복원 WARNING 줄에 그 사실만 덧붙인다(감시 로트 선택은 그대로)."""
        now = now_kst()
        rows = [   # timestamp DESC
            _holding(CODE, 10, 30_000.0, now - timedelta(hours=1), 3650),
            _holding(CODE, 17, 26_850.0, now - timedelta(days=1), 3633),
            _holding(CODE, 40, 28_400.0, now - timedelta(days=5), 3603),
        ]
        r, tsm, slot, strat, fm, warns = await _restored(rows)
        assert slot._virtual_buy_record_id == 3603
        assert [lot["buy_record_id"] for lot in slot._queued_restored_lots] == [3633, 3650]
        (multi,) = [w for w in warns if "열린 매수 로트" in w]
        assert "열린 매수 로트 3개" in multi
        assert "손절가가 감시 로트(26,412원)보다 높은 대기 로트 ['rid 3650 27,900원']" in multi
        assert fm.invested_funds == pytest.approx(40 * 28_400 + 17 * 26_850 + 10 * 30_000)

        engine, db = _engine(tsm, fm, strat)
        await engine.execute_virtual_sell(slot, 26_300.0, "손절")
        assert (slot._virtual_buy_record_id, slot.position.quantity) == (3633, 17)
        assert strat.positions[CODE]["entry_price"] == pytest.approx(26_850.0)
        await engine.execute_virtual_sell(slot, 24_900.0, "손절")
        assert (slot._virtual_buy_record_id, slot.position.quantity) == (3650, 10)
        assert slot.state == StockState.POSITIONED and slot._queued_restored_lots == []
        assert strat.positions[CODE]["entry_price"] == pytest.approx(30_000.0)
        await engine.execute_virtual_sell(slot, 27_800.0, "손절")

        assert [(c.kwargs["buy_record_id"], c.kwargs["quantity"]) for c in db.save_virtual_sell.call_args_list] \
            == [(3603, 40), (3633, 17), (3650, 10)]
        assert slot.state == StockState.COMPLETED and slot.position is None
        assert (CODE, OWNER) not in fm._position_entries and CODE not in strat.positions
        assert fm.invested_funds == pytest.approx(0.0)
        assert _abnormal(tsm) == []


def test_trading_stock_has_empty_queue_by_default():
    """대기 로트는 페이퍼 DB 복원만 채운다 — 새 슬롯(실전 포함)은 빈 목록, 슬롯끼리 공유하지 않는다."""
    from core.models import TradingStock
    a = TradingStock(stock_code="005930", stock_name="삼성전자", state=StockState.SELECTED,
                     selected_time=now_kst())
    b = TradingStock(stock_code="000660", stock_name="SK하이닉스", state=StockState.SELECTED,
                     selected_time=now_kst())
    assert a._queued_restored_lots == [] and b._queued_restored_lots == []
    a._queued_restored_lots.append({"buy_record_id": 1})
    assert b._queued_restored_lots == []
