"""페이퍼 보유 복원 — 일봉 조회가 실패해도 DB 보유는 항상 런타임에 올린다 (2026-11-19 결함).

사실: 07:40 기동 때 KIS `OPSQ0008` 로 보유 6종목의 일봉 조회가 실패 →
`collect_daily_data_only` 가 selected_stocks 에서 지우고 False → `add_selected_stock` False →
`_restore_holdings_from_db` 가 그 보유를 건너뜀(`보유 종목 29/35개 복원 완료`). 6종목이 종일
손절·익절·보유기간 감시 밖, 「보유 중 무시」 가드가 못 봐서 028300 중복 매수, 관문이 실전을 끔.

고정하는 것:
  1. 실제 사슬(StateRestorer → TradingStockManager → OrderExecution → IntradayStockManager →
     IntradayDataCollector)에서 일봉이 None 이어도 전 종목 POSITIONED · `N/M` 이 M/M ·
     「일봉 미확보」 별도 줄 · 관문 정규식 형식 불변.
  2. 짧은 재시도 1회로 붙으면 정상 등록(미확보 줄 없음).
  3. 일봉 없는 슬롯도 현재가 기반 손절·익절·보유기간 백스톱을 받는다.
  4. 「보유 중 무시」 가드가 폴백 슬롯을 본다(같은 전략 중복 매수 차단).
  5. 전략 일봉 청산은 DB 일봉이 없으면 보류, 들어오면 정상 경로로 돌아온다.

KIS·DB 에 닿지 않는다 — 브로커는 페이크, 일봉 DB 저장은 모의.
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
from utils.korean_time import now_kst  # noqa: E402

GATE_RE = re.compile(r"보유 종목 (\d+)/(\d+)개 복원 완료")
OWNER = "book_pullback_ma20"


def _daily_df(n=103):
    closes = np.full(n, 10_000.0)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": np.full(n, 100_000.0),
    })


def _holding(code, qty, price, buy_time, row_id, tp=0.10, sl=0.08, owner=OWNER):
    return {
        "id": row_id, "stock_code": code, "stock_name": code, "quantity": qty,
        "buy_price": price, "buy_time": buy_time, "strategy": owner,
        "target_profit_rate": tp, "stop_loss_rate": sl,
    }


def _build(holdings, ohlcv, strategy):
    """실체 TradingStockManager + IntradayStockManager(리밸런싱 모드) + StateRestorer(페이퍼).

    ohlcv: broker.get_ohlcv_data 의 side_effect(code, period, count) — None 이면 조회 실패.
    """
    from bot.state_restorer import StateRestorer
    from core.intraday_stock_manager import IntradayStockManager
    from core.trading_stock_manager import TradingStockManager

    broker = Mock()
    broker.get_ohlcv_data = Mock(side_effect=ohlcv)
    intraday = IntradayStockManager(broker, SimpleNamespace(rebalancing_mode=True))
    intraday.data_collector._save_daily_to_db = AsyncMock(return_value=True)  # DB 쓰기 0
    data_collector = MagicMock()
    data_collector.get_stock.return_value = None
    tsm = TradingStockManager(intraday, data_collector, MagicMock(), None)

    db = Mock()
    db.get_virtual_open_positions.return_value = pd.DataFrame(holdings)
    config = Mock()
    config.paper_trading = True
    r = StateRestorer(
        trading_manager=tsm, db_manager=db, telegram_integration=None, config=config,
        get_previous_close_callback=lambda code: 10_000.0, broker=broker, fund_manager=None,
        virtual_trading_manager=None, strategies={OWNER: strategy},
    )
    return r, tsm, intraday, data_collector, broker


async def _restore(r):
    with patch("bot.state_restorer.PAPER_RESTORE_RETRY_SEC", 0), \
         patch("bot.state_restorer.logger") as log:
        await r._restore_holdings_from_db()
    infos = [str(c.args[0]) for c in log.info.call_args_list if c.args]
    warns = [str(c.args[0]) for c in log.warning.call_args_list if c.args]
    return infos, warns


def _fail_for(*bad_codes):
    def _ohlcv(code, period, count):
        return None if code in bad_codes else _daily_df()
    return _ohlcv


def _strategy_stub(max_holding_days=None):
    return SimpleNamespace(name="BookPullbackMa20Strategy", max_holding_days=max_holding_days,
                           sync_positions=Mock())


class TestPaperRestoreKeepsPositionsWhenDailyFails:

    @pytest.mark.asyncio
    async def test_all_db_holdings_positioned_and_gate_line_is_m_of_m(self):
        bt = now_kst() - timedelta(days=3)
        holdings = [
            _holding("417010", 104, 6_210.0, bt, 3501),
            _holding("062040", 10, 20_000.0, bt, 3502),
            _holding("028300", 5, 40_000.0, bt, 3603),
        ]
        strat = _strategy_stub()
        r, tsm, intraday, data_collector, broker = _build(holdings, _fail_for("062040", "028300"), strat)

        infos, warns = await _restore(r)

        for h in holdings:
            slot = tsm.get_trading_stock(h["stock_code"], strategy=OWNER)
            assert slot is not None and slot.state == StockState.POSITIONED, h["stock_code"]
            assert slot.position.quantity == h["quantity"]
            assert slot.position.avg_price == pytest.approx(h["buy_price"])
            assert slot.stop_loss_rate == pytest.approx(0.08)
            assert slot.target_profit_rate == pytest.approx(0.10)
            assert slot.owner_strategy is strat
            assert slot._virtual_buy_record_id == h["id"]
        # 관문 줄 = 형식 불변 · N == M
        gate = [line for line in infos if GATE_RE.search(line)]
        assert len(gate) == 1 and GATE_RE.search(gate[0]).groups() == ("3", "3")
        # 일봉 미확보는 별도 줄 — 관문 정규식에 걸리지 않는다
        (missing,) = [w for w in warns if "일봉 미확보" in w]
        assert "일봉 미확보 2종목" in missing and "062040" in missing and "028300" in missing
        assert "417010" not in missing
        assert not GATE_RE.search(missing) and "보유 종목 없음" not in missing
        # 짧은 재시도 1회(실패 종목만 2번 조회) · 성공 종목은 1번
        calls = [c.args[0] for c in broker.get_ohlcv_data.call_args_list]
        assert calls.count("062040") == 2 and calls.count("028300") == 2 and calls.count("417010") == 1
        # 정상 종목만 장중 관리 등록 · 폴백 종목도 현재가 수집 목록엔 올라간다
        assert set(intraday.selected_stocks) == {"417010"}
        added = {c.args[0] for c in data_collector.add_candidate_stock.call_args_list}
        assert added == {"417010", "062040", "028300"}
        # 전략 포지션 주입에도 전 종목
        (positions,) = strat.sync_positions.call_args[0]
        assert set(positions) == {"417010", "062040", "028300"}

    @pytest.mark.asyncio
    async def test_retry_succeeds_registers_normally_without_missing_line(self):
        bt = now_kst() - timedelta(days=3)
        seen = []

        def _ohlcv(code, period, count):
            seen.append(code)
            return None if seen.count(code) == 1 else _daily_df()   # 첫 조회만 실패

        r, tsm, intraday, _, broker = _build(
            [_holding("062040", 10, 20_000.0, bt, 3502)], _ohlcv, _strategy_stub())

        infos, warns = await _restore(r)

        assert tsm.get_trading_stock("062040", strategy=OWNER).state == StockState.POSITIONED
        assert "062040" in intraday.selected_stocks
        assert broker.get_ohlcv_data.call_count == 2
        assert not [w for w in warns if "일봉 미확보" in w]
        assert any(GATE_RE.search(line) and "1/1" in line for line in infos)

    @pytest.mark.asyncio
    async def test_degraded_slot_gets_price_stop_loss_take_profit_and_max_hold(self):
        bt = now_kst() - timedelta(days=3)
        r, tsm, intraday, _, _ = _build(
            [_holding("062040", 10, 20_000.0, bt, 3502)], _fail_for("062040"), _strategy_stub())
        await _restore(r)
        slot = tsm.get_trading_stock("062040", strategy=OWNER)

        pm = tsm._position_monitor
        pm.set_decision_engine(Mock())
        pm._execute_sell = AsyncMock()
        fixed = now_kst().replace(hour=10, minute=30, second=0, microsecond=0)
        with patch("core.trading.position_monitor.now_kst", return_value=fixed):
            intraday.get_current_price_for_sell = Mock(return_value={"current_price": 18_000.0})  # −10%
            await pm._check_positioned_stocks_for_sell()
            assert pm._execute_sell.await_count == 1
            assert pm._execute_sell.call_args.args[0] is slot
            assert "손절" in pm._execute_sell.call_args.args[2]

            pm._execute_sell.reset_mock()
            intraday.get_current_price_for_sell = Mock(return_value={"current_price": 22_500.0})  # +12.5%
            await pm._check_positioned_stocks_for_sell()
            assert pm._execute_sell.await_count == 1 and "익절" in pm._execute_sell.call_args.args[2]
        intraday.get_current_price_for_sell.assert_called_with("062040")

    @pytest.mark.asyncio
    async def test_degraded_slot_gets_max_hold_backstop(self):
        bt = now_kst() - timedelta(days=30)
        r, tsm, intraday, _, _ = _build(
            [_holding("062040", 10, 20_000.0, bt, 3502)], _fail_for("062040"),
            _strategy_stub(max_holding_days=5))
        await _restore(r)
        slot = tsm.get_trading_stock("062040", strategy=OWNER)
        assert slot.days_held >= 5

        pm = tsm._position_monitor
        pm.set_decision_engine(Mock())
        pm._execute_sell = AsyncMock()
        fixed = now_kst().replace(hour=10, minute=30, second=0, microsecond=0)
        with patch("core.trading.position_monitor.now_kst", return_value=fixed):
            intraday.get_current_price_for_sell = Mock(return_value={"current_price": 20_100.0})  # 손익 무관
            await pm._check_positioned_stocks_for_sell()
        assert pm._execute_sell.await_count == 1
        assert "보유기간" in pm._execute_sell.call_args.args[2]

    @pytest.mark.asyncio
    async def test_same_strategy_buy_guard_sees_degraded_slot(self):
        """ⓑ 「보유 중 무시」 가드(trading_analyzer)가 폴백 슬롯을 본다 → 같은 전략 중복 매수 없음."""
        from bot.trading_analyzer import TradingAnalyzer

        bt = now_kst() - timedelta(days=3)
        strat = _strategy_stub()
        r, tsm, _, _, _ = _build([_holding("028300", 5, 40_000.0, bt, 3603)], _fail_for("028300"), strat)
        await _restore(r)

        bot = MagicMock()
        bot.trading_manager = tsm
        bot.strategies = {OWNER: strat}
        analyzer = TradingAnalyzer(bot)
        analyzer.logger = Mock()
        candidate = Mock(stock_code="028300", stock_name="028300")

        result = await analyzer.analyze_buy_decision(candidate, available_funds=1_000_000, strategy_name=OWNER)

        assert not result
        assert any("보유 중인 종목 매수 신호 무시" in str(c.args[0])
                   for c in analyzer.logger.info.call_args_list)
        bot.db_manager.price_repo.get_daily_prices.assert_not_called()   # 가드에서 멈춤


class TestDailyExitDeferredUntilDataArrives:

    @pytest.mark.asyncio
    async def test_trail_ma_exit_waits_for_daily_then_fires(self, monkeypatch):
        """전략 일봉 청산(MA20 trailing)은 DB 일봉이 없으면 보류(매도 0 · 예외 0), 들어오면 정상 발화."""
        import strategies.book_pullback_ma20.strategy as mod
        from strategies.book_pullback_ma20.strategy import BookPullbackMa20Strategy

        now = now_kst().replace(hour=10, minute=0, second=0, microsecond=0)
        monkeypatch.setattr(mod, "now_kst", lambda: now)
        strat = BookPullbackMa20Strategy({"paper_trading": True})
        strat.on_init(None, None, None)
        strat.logger = Mock()

        r, tsm, _, _, _ = _build(
            [_holding("062040", 10, 10_000.0, now - timedelta(days=3), 3502)], _fail_for("062040"), strat)
        await _restore(r)
        assert r.apply_pending_strategy_positions() == 1
        assert strat.positions["062040"]["entry_price"] == pytest.approx(10_000.0)

        daily = {"df": None}

        async def _get_daily(code, days=None):
            return daily["df"]

        ctx = MagicMock()
        ctx.tracer = None
        ctx.get_selected_stocks.return_value = []
        ctx.get_positions.side_effect = lambda: tsm.get_stocks_by_state(StockState.POSITIONED)
        ctx.get_daily_data = _get_daily
        ctx.sell = AsyncMock()

        await strat.on_tick(ctx)                     # 일봉 없음 → 판단 보류
        ctx.sell.assert_not_awaited()

        closes = np.r_[np.full(40, 11_000.0), [10_500.0]]   # MA20≈11,000 > 종가 · 진입가 대비 +5%
        daily["df"] = pd.DataFrame({
            "datetime": pd.date_range("2026-09-01", periods=len(closes), freq="D"),
            "open": closes, "high": closes, "low": closes, "close": closes,
            "volume": np.full(len(closes), 100_000.0),
        })
        await strat.on_tick(ctx)                     # 일봉 도착 → 정상 경로
        ctx.sell.assert_awaited_once()
        assert ctx.sell.call_args.args[0] == "062040"
