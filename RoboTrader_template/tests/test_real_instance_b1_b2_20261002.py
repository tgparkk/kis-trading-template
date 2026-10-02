"""실전 daytrading 인스턴스 결함 B-1(후보 출처)·B-2(익절선) 수정 — 회귀 고정 (2026-10-02).

사전등록: `docs/prereg_2026-10-02_real_daytrading_b1_b2_fix.md` §④ 판정 기준 (i)~(iv).

원칙: **페이퍼 8전략(INSTANCE_ID "default" · paper_trading true) 동작 0 변경.**
KIS·네트워크·DB 에 닿지 않는다 — 전부 페이크/모의 객체.
"""
import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401,E402

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import yaml  # noqa: E402

from core.candidate_selector import CandidateSelector, CandidateStock  # noqa: E402
from core.models import StockState, TradingStock  # noqa: E402
from config.constants import (  # noqa: E402
    DEFAULT_STOP_LOSS_RATE, DEFAULT_TARGET_PROFIT_RATE,
    REAL_INSTANCE_SNAPSHOT_POLL_SEC, REAL_INSTANCE_SNAPSHOT_WAIT_MAX_SEC,
    STALE_DEFAULT_STOP_LOSS, STALE_DEFAULT_TARGET_PROFIT,
)
from utils.korean_time import KST  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DT_KEY = "daytrading_3methods_breakout"
DT_CONFIG = yaml.safe_load(
    (PROJECT_ROOT / "strategies" / DT_KEY / "config.yaml").read_text(encoding="utf-8"))
PAPER_8 = [
    "elder_ema_pullback", "book_envelope_200d", DT_KEY, "minervini_volume_dryup",
    "book_pullback_ma20", "book_pullback_ma5", "rs_leader", "deep_mr_dev20",
]


def _cand(code, owner=DT_KEY):
    return CandidateStock(code=code, name=code, market="KRX", score=50.0,
                          reason=f"screener_snapshot({owner})", prev_close=0.0)


def _set_instance(monkeypatch, instance_id):
    import config.settings as settings
    monkeypatch.setattr(settings, "INSTANCE_ID", instance_id, raising=False)


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    import bot.candidate_loader as cl
    monkeypatch.setattr(cl, "time", types.SimpleNamespace(monotonic=c.monotonic))
    return c


class _FakeTM:
    """add_selected_stock 호출을 기록하는 최소 TradingStockManager 대역."""

    def __init__(self):
        self.calls = []
        self._reg = {}

    async def add_selected_stock(self, stock_code, stock_name, selection_reason="",
                                 prev_close=0.0, owner_strategy=""):
        self.calls.append({"stock_code": stock_code, "owner_strategy": owner_strategy})
        ts = MagicMock()
        ts.strategy_name = None
        self._reg[(stock_code, owner_strategy)] = ts
        return True

    def get_trading_stock(self, stock_code, strategy=None):
        return self._reg.get((stock_code, strategy or ""))


class _FakeSelector:
    """실전 경로가 부르는 것(has_prev_day_snapshot·_fetch)과 부르면 안 되는 것(폴백·JSON·다중)을 기록."""

    def __init__(self, ready):
        self._ready = {k: list(v) for k, v in ready.items()}
        self.ready_calls = []
        self.fetch_calls = []
        self.load_from_screener = MagicMock(return_value=[_cand("999999")])
        self.select_daily_candidates = AsyncMock(return_value=[_cand("888888")])
        self.select_candidates_per_strategy = MagicMock(return_value={})

    def has_prev_day_snapshot(self, name):
        self.ready_calls.append(name)
        seq = self._ready[name]
        v = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(v, Exception):
            raise v
        return v

    def _fetch_candidates_for_strategy(self, name, max_candidates, sector_rerank=True):
        self.fetch_calls.append((name, max_candidates, sector_rerank))
        return [_cand("111111", name), _cand("222222", name)]


def _bot(strategy_keys, selector):
    bot = MagicMock()
    bot._candidates_loaded = False
    bot._candidate_load_retries = 0
    bot.liquidation_handler = None
    bot.config.strategy = {"parameters": {"max_candidates": 10}}
    bot.strategies = {k: MagicMock(name=k) for k in strategy_keys}
    bot.strategy = next(iter(bot.strategies.values())) if bot.strategies else None
    bot.candidate_selector = selector
    bot.db_manager = MagicMock()
    bot.trading_manager = _FakeTM()
    bot.telegram = MagicMock()
    bot.telegram.notify_error = AsyncMock()
    bot.telegram.notify_system_status = AsyncMock()
    return bot


def _loader(bot):
    from bot.candidate_loader import CandidateLoader
    loader = CandidateLoader(bot)
    loader.logger = MagicMock()
    return loader


def _msgs(m):
    return [c.args[0] if c.args else "" for c in m.call_args_list]


def _assert_no_fallback(bot, sel):
    sel.load_from_screener.assert_not_called()
    sel.select_daily_candidates.assert_not_called()
    sel.select_candidates_per_strategy.assert_not_called()
    bot.db_manager.candidate_repo.save_candidate_stocks.assert_not_called()
    assert not {c["stock_code"] for c in bot.trading_manager.calls} & {"999999", "888888"}


# =============================================================================
# (i) B-1 — 실전 인스턴스: 스냅샷 경로 · 대기·재시도 · fail-closed
# =============================================================================
class TestB1RealInstanceSnapshotPath:

    @pytest.mark.asyncio
    async def test_single_strategy_reads_snapshot_path_immediately(self, monkeypatch, clock):
        _set_instance(monkeypatch, "daytrading")
        sel = _FakeSelector({DT_KEY: [True]})
        bot = _bot([DT_KEY], sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()

        assert sel.fetch_calls == [(DT_KEY, 10, False)], "페이퍼와 같은 함수·목표 10·재정렬 생략이어야 한다"
        assert [c["owner_strategy"] for c in bot.trading_manager.calls] == [DT_KEY, DT_KEY]
        assert bot._candidates_loaded is True
        assert loader.snapshot_wait_pending is False
        _assert_no_fallback(bot, sel)
        bot.telegram.notify_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_snapshot_appears_late_then_registers(self, monkeypatch, clock):
        _set_instance(monkeypatch, "daytrading")
        sel = _FakeSelector({DT_KEY: [False, True]})
        bot = _bot([DT_KEY], sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()
        # 첫 시도 없음 → 대기. 장시작 콜백 1회를 위해 loaded 는 이미 True.
        assert bot._candidates_loaded is True
        assert loader.snapshot_wait_pending is True
        assert bot.trading_manager.calls == []
        assert len([m for m in _msgs(loader.logger.warning) if "[B1-실전]" in m]) == 1

        clock.t += REAL_INSTANCE_SNAPSHOT_POLL_SEC / 2       # 간격 전 — 조회하지 않는다
        await loader.poll_snapshot_wait()
        assert sel.ready_calls == [DT_KEY]

        clock.t += REAL_INSTANCE_SNAPSHOT_POLL_SEC          # 간격 지남 — 재확인 → 생김
        await loader.poll_snapshot_wait()
        assert sel.ready_calls == [DT_KEY, DT_KEY]
        assert sel.fetch_calls == [(DT_KEY, 10, False)]
        assert len(bot.trading_manager.calls) == 2
        assert loader.snapshot_wait_pending is False
        _assert_no_fallback(bot, sel)
        bot.telegram.notify_error.assert_not_called()
        # 대기 경고는 한 번만
        assert len([m for m in _msgs(loader.logger.warning) if "[B1-실전]" in m]) == 1

    @pytest.mark.asyncio
    async def test_snapshot_never_appears_fail_closed(self, monkeypatch, clock):
        _set_instance(monkeypatch, "daytrading")
        sel = _FakeSelector({DT_KEY: [False]})
        bot = _bot([DT_KEY], sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()
        polls = 1
        while loader.snapshot_wait_pending:
            clock.t += REAL_INSTANCE_SNAPSHOT_POLL_SEC
            await loader.poll_snapshot_wait()
            polls += 1
            assert polls < 1000, "상한에서 멈추지 않는다"
        # 상한 = 15분 / 10초 간격 → 첫 시도 + 90회 재확인
        assert polls == REAL_INSTANCE_SNAPSHOT_WAIT_MAX_SEC // REAL_INSTANCE_SNAPSHOT_POLL_SEC + 1

        assert bot.trading_manager.calls == [], "fail-closed — 후보 0"
        _assert_no_fallback(bot, sel)
        errors = [m for m in _msgs(loader.logger.error) if "[B1-실전]" in m]
        assert len(errors) == 1 and "fail-closed" in errors[0]
        bot.telegram.notify_error.assert_awaited_once()

        # 상한 뒤에는 더 조회하지 않는다(그날 끝)
        n = len(sel.ready_calls)
        clock.t += 3600
        await loader.poll_snapshot_wait()
        assert len(sel.ready_calls) == n

    @pytest.mark.asyncio
    async def test_poll_never_raises_and_retries_after_check_error(self, monkeypatch, clock):
        _set_instance(monkeypatch, "daytrading")
        sel = _FakeSelector({DT_KEY: [RuntimeError("db down"), True]})
        bot = _bot([DT_KEY], sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()          # 예외 → 대기
        assert loader.snapshot_wait_pending is True
        clock.t += REAL_INSTANCE_SNAPSHOT_POLL_SEC
        await loader.poll_snapshot_wait()                 # 재시도 → 성공
        assert loader.snapshot_wait_pending is False
        assert len(bot.trading_manager.calls) == 2

    @pytest.mark.asyncio
    async def test_fetch_error_is_fail_closed_without_raise(self, monkeypatch, clock):
        _set_instance(monkeypatch, "daytrading")
        sel = _FakeSelector({DT_KEY: [True]})
        sel._fetch_candidates_for_strategy = MagicMock(side_effect=RuntimeError("boom"))
        bot = _bot([DT_KEY], sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()
        assert bot.trading_manager.calls == []
        assert loader.snapshot_wait_pending is False
        _assert_no_fallback(bot, sel)

    @pytest.mark.asyncio
    async def test_two_strategy_instance_also_snapshot_path_per_strategy(self, monkeypatch, clock):
        """「전략 수와 무관」 — 2전략 인스턴스도 다중 경로(폴백 포함)가 아니라 전략별 대기."""
        _set_instance(monkeypatch, "rs_leader")
        sel = _FakeSelector({"rs_leader": [True], DT_KEY: [False, True]})
        bot = _bot(["rs_leader", DT_KEY], sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()
        assert {c["owner_strategy"] for c in bot.trading_manager.calls} == {"rs_leader"}
        assert loader.snapshot_wait_pending is True
        clock.t += REAL_INSTANCE_SNAPSHOT_POLL_SEC
        await loader.poll_snapshot_wait()
        assert {c["owner_strategy"] for c in bot.trading_manager.calls} == {"rs_leader", DT_KEY}
        assert loader.snapshot_wait_pending is False
        _assert_no_fallback(bot, sel)

    @pytest.mark.asyncio
    async def test_no_strategies_instance_is_fail_closed(self, monkeypatch, clock):
        _set_instance(monkeypatch, "daytrading")
        sel = _FakeSelector({})
        bot = _bot([], sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()
        assert bot.trading_manager.calls == []
        assert loader.snapshot_wait_pending is False
        _assert_no_fallback(bot, sel)
        bot.telegram.notify_error.assert_awaited_once()


class TestB1CandidateSelectorPieces:
    """실전이 부르는 셀렉터 조각 — 재정렬 생략 · D-1 동일 · 페이퍼 호출형 불변."""

    def _selector(self):
        sel = CandidateSelector.__new__(CandidateSelector)
        sel.logger = MagicMock()
        sel.db_manager = MagicMock()
        sel._filter_unsafe_stocks = MagicMock(side_effect=lambda pool, limit: pool[:limit])
        sel._apply_sector_news_rerank = MagicMock(side_effect=lambda name, codes, d: (list(codes), {}))
        return sel

    def _provider_factory(self, codes, seen):
        def factory(strategy_name):
            def provider(strategy, scan_date):
                seen.append((strategy, scan_date))
                return list(codes)
            return provider
        return factory

    def test_sector_rerank_false_skips_rerank_same_result_as_shadow(self):
        codes = [f"{i:06d}" for i in range(1, 26)]
        seen = []
        with patch("core.screener_snapshot_provider.make_screener_snapshot_provider",
                   self._provider_factory(codes, seen)):
            paper_sel = self._selector()
            paper = paper_sel._fetch_candidates_for_strategy(DT_KEY, 10)
            inst_sel = self._selector()
            inst = inst_sel._fetch_candidates_for_strategy(DT_KEY, 10, sector_rerank=False)

        paper_sel._apply_sector_news_rerank.assert_called_once()   # 페이퍼(기본값) = 종전대로 재정렬 호출
        inst_sel._apply_sector_news_rerank.assert_not_called()     # 실전 = 재정렬(=로그 UPSERT) 0
        assert [c.code for c in inst] == [c.code for c in paper] == codes[:10]
        assert [c.reason for c in inst] == [c.reason for c in paper]

    def test_has_prev_day_snapshot_uses_same_d1_as_fetch(self):
        seen = []
        with patch("core.screener_snapshot_provider.make_screener_snapshot_provider",
                   self._provider_factory(["000001"], seen)):
            sel = self._selector()
            assert sel.has_prev_day_snapshot(DT_KEY) is True
            sel._fetch_candidates_for_strategy(DT_KEY, 10)
        assert len(seen) == 2 and seen[0] == seen[1], f"D-1 이 갈렸다: {seen}"

        with patch("core.screener_snapshot_provider.make_screener_snapshot_provider",
                   self._provider_factory([], [])):
            assert self._selector().has_prev_day_snapshot(DT_KEY) is False

    def test_paper_select_per_strategy_call_shape_unchanged(self):
        """(ii) 페이퍼 다중 경로가 `_fetch_candidates_for_strategy` 를 «인자 2개» 로 부른다(새 kwarg 미전달)."""
        sel = CandidateSelector.__new__(CandidateSelector)
        sel.logger = MagicMock()
        sel._fetch_candidates_for_strategy = MagicMock(return_value=[])
        strategies = {k: MagicMock() for k in PAPER_8}
        sel.select_candidates_per_strategy(strategies, max_per_strategy=10)
        assert sel._fetch_candidates_for_strategy.call_args_list == [call(k, 10) for k in PAPER_8]


# =============================================================================
# (ii) 페이퍼(default) — 종전 경로 그대로
# =============================================================================
class TestB1PaperUnchanged:

    @pytest.mark.asyncio
    async def test_paper_8_strategies_same_multi_path(self, monkeypatch, clock):
        _set_instance(monkeypatch, "default")
        sel = MagicMock()
        sel.select_candidates_per_strategy.return_value = {k: [_cand(f"{i:06d}", k)] for i, k in enumerate(PAPER_8)}
        bot = _bot(PAPER_8, sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()

        sel.select_candidates_per_strategy.assert_called_once_with(bot.strategies, max_per_strategy=10)
        sel.has_prev_day_snapshot.assert_not_called()
        sel._fetch_candidates_for_strategy.assert_not_called()
        sel.select_daily_candidates.assert_not_called()
        assert loader.snapshot_wait_pending is False
        assert len(bot.trading_manager.calls) == 8
        assert not [m for m in _msgs(loader.logger.error) if "[B1-실전]" in m]

    @pytest.mark.asyncio
    async def test_paper_single_strategy_same_json_path(self, monkeypatch, clock):
        _set_instance(monkeypatch, "default")
        sel = MagicMock()
        sel.load_from_screener.return_value = [_cand("005930")]
        bot = _bot([DT_KEY], sel)
        loader = _loader(bot)

        await loader._load_screener_candidates()

        sel.load_from_screener.assert_called_once_with(max_candidates=10)
        sel.has_prev_day_snapshot.assert_not_called()
        assert loader.snapshot_wait_pending is False
        assert [c["owner_strategy"] for c in bot.trading_manager.calls] == [DT_KEY]


# =============================================================================
# 메인 루프 — 대기 중에도 보유 감시 · 장시작 콜백 1회 · 페이퍼는 poll 0
# =============================================================================
@pytest.fixture
def real_bot():
    with patch('main.KISBroker') as mock_broker_cls, \
         patch('main.DatabaseManager') as mock_db_cls, \
         patch('main.TelegramIntegration'), \
         patch('main.check_duplicate_process'), \
         patch('main.load_config') as mock_load_config, \
         patch('main.StrategyLoader') as mock_loader:
        mock_load_config.return_value = MagicMock(
            rebalancing_mode=False,
            strategy={'name': 'sample', 'enabled': False, 'parameters': {'max_candidates': 10}},
            paper_trading=True,
        )
        mock_db_cls.return_value.db_path = ':memory:'
        mock_broker_cls.return_value.connect = AsyncMock(return_value=True)
        mock_loader.load_strategy.side_effect = FileNotFoundError("test")
        from main import DayTradingBot
        bot = DayTradingBot()
        bot.decision_engine.check_market_direction = MagicMock(return_value=(False, ""))
        yield bot


async def _run_loop(bot, n_iter):
    async def stop_after(seconds):
        stop_after.n += 1
        if stop_after.n >= n_iter:
            bot.is_running = False
    stop_after.n = 0
    bot.is_running = True
    with patch('main.is_market_open', return_value=True), \
         patch('asyncio.sleep', side_effect=stop_after), \
         patch.object(bot, '_check_eod_liquidation', new=AsyncMock()):
        await bot._main_trading_loop()


class TestB1MainLoop:

    @pytest.mark.asyncio
    async def test_instance_wait_does_not_block_and_market_open_once(self, real_bot, monkeypatch, clock):
        _set_instance(monkeypatch, "daytrading")
        bot = real_bot
        strat = MagicMock()
        strat.on_tick = AsyncMock()
        bot.strategies = {DT_KEY: strat}
        bot.ctx_for_strategy = MagicMock()
        bot.candidate_selector = _FakeSelector({DT_KEY: [False]})
        bot.data_collector.collect_once = AsyncMock()
        bot.order_manager.check_pending_orders_once = AsyncMock()
        bot.trading_manager.check_positions_once = AsyncMock()
        market_open = AsyncMock()
        polls = []
        orig_poll = bot.candidate_loader.poll_snapshot_wait

        async def spy_poll():
            polls.append(clock.t)
            clock.t += 3                                   # 루프 1회 ≈ 3초
            await orig_poll()

        with patch.object(bot, '_call_strategy_market_open', new=market_open), \
             patch.object(bot.candidate_loader, 'poll_snapshot_wait', new=spy_poll):
            await _run_loop(bot, 6)

        assert market_open.await_count == 1, "장시작 콜백은 대기 중에도 1회"
        assert bot.trading_manager.check_positions_once.await_count == 6, "대기 중에도 매 반복 보유 감시"
        # 1번째 반복 = 로드 안에서 1회 · 2번째 반복부터 main 루프 elif 가 매 반복 1회
        assert len(polls) == 6, polls
        assert bot.candidate_loader.snapshot_wait_pending is True

    @pytest.mark.asyncio
    async def test_paper_loop_never_polls(self, real_bot, monkeypatch):
        _set_instance(monkeypatch, "default")
        bot = real_bot
        bot._candidates_loaded = True
        bot.data_collector.collect_once = AsyncMock()
        bot.order_manager.check_pending_orders_once = AsyncMock()
        bot.trading_manager.check_positions_once = AsyncMock()
        poll = AsyncMock()
        with patch.object(bot.candidate_loader, 'poll_snapshot_wait', new=poll):
            await _run_loop(bot, 4)
        poll.assert_not_called()
        assert bot.trading_manager.check_positions_once.await_count == 4


# =============================================================================
# (iii) B-2 — 실전 매수·실전 복원 tp/sl = 소유 전략 config
# =============================================================================
def _dt_strategy():
    return SimpleNamespace(name="DayTrading3MethodsBreakoutStrategy", config=DT_CONFIG)


def _ts(code="123456", owner=DT_KEY):
    return TradingStock(stock_code=code, stock_name=code, state=StockState.SELECTED,
                        selected_time=datetime(2026, 10, 19, 9, 0, tzinfo=KST),
                        owner_strategy_name=owner)


def _real_engine(strategies_by_key, strategy=None):
    import logging
    from core.trading_decision_engine import TradingDecisionEngine
    from core.trading_stock_manager import TradingStockManager
    om = MagicMock()
    om.place_buy_order = AsyncMock(return_value="ORD-1")
    om.set_trading_manager = MagicMock()
    tm = TradingStockManager(intraday_manager=MagicMock(), data_collector=MagicMock(), order_manager=om)
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.trading_manager = tm
    engine.logger = logging.getLogger("test.b2")
    engine.strategies_by_key = strategies_by_key
    engine.strategy = strategy
    return engine, tm


class TestB2RealBuy:

    def test_resolver_pct_first_then_ratio(self):
        from core.trading_decision_engine import resolve_strategy_tp_sl
        assert resolve_strategy_tp_sl(_dt_strategy()) == (0.10, 0.10)
        both = SimpleNamespace(config={"risk_management": {
            "take_profit_pct": 0.12, "take_profit_ratio": 0.5, "stop_loss_ratio": 0.07}})
        assert resolve_strategy_tp_sl(both) == (0.12, 0.07)
        assert resolve_strategy_tp_sl(SimpleNamespace(config={})) == (None, None)
        assert resolve_strategy_tp_sl(MagicMock()) == (None, None)
        assert resolve_strategy_tp_sl(None) == (None, None)

    @pytest.mark.asyncio
    async def test_real_buy_sets_daytrading_config_tp_sl(self):
        engine, tm = _real_engine({DT_KEY: _dt_strategy()})
        ts = _ts()
        tm._register_stock(ts)
        assert (ts.target_profit_rate, ts.stop_loss_rate) == (DEFAULT_TARGET_PROFIT_RATE, DEFAULT_STOP_LOSS_RATE)

        ok = await engine.execute_real_buy(ts, "test", buy_price=4280.0, quantity=10)

        assert ok is True
        assert (ts.target_profit_rate, ts.stop_loss_rate) == (0.10, 0.10)
        assert ts.state == StockState.BUY_PENDING

    @pytest.mark.asyncio
    async def test_real_buy_class_name_owner_also_resolves(self):
        engine, tm = _real_engine({DT_KEY: _dt_strategy()})
        ts = _ts(owner="DayTrading3MethodsBreakoutStrategy")
        tm._register_stock(ts)
        assert await engine.execute_real_buy(ts, "test", buy_price=4280.0, quantity=10) is True
        assert (ts.target_profit_rate, ts.stop_loss_rate) == (0.10, 0.10)

    @pytest.mark.asyncio
    async def test_real_buy_unresolved_owner_keeps_defaults_and_still_buys(self):
        """다전략에서 owner 미해석 → 추측하지 않는다(종전 값) · 매수는 막지 않는다."""
        engine, tm = _real_engine({DT_KEY: _dt_strategy(), "rs_leader": SimpleNamespace(
            name="RSLeaderStrategy", config={"risk_management": {"take_profit_pct": 0.15, "stop_loss_pct": 0.08}})})
        ts = _ts(owner="ghost")
        tm._register_stock(ts)
        assert await engine.execute_real_buy(ts, "test", buy_price=4280.0, quantity=10) is True
        assert (ts.target_profit_rate, ts.stop_loss_rate) == (DEFAULT_TARGET_PROFIT_RATE, DEFAULT_STOP_LOSS_RATE)


RESTORE_NOW = datetime(2026, 10, 19, 10, 0, tzinfo=KST)
BUY_TIME_9D = pd.Timestamp("2026-10-06 09:00:10")   # 10-19 기준 9거래일(≥ STALE_DEFAULT_APPLY_DAYS 7 · < 30)


def _restorer(strategies, paper_trading, db_manager, broker=None):
    from bot.state_restorer import StateRestorer
    config = MagicMock()
    config.paper_trading = paper_trading
    tm = MagicMock()
    tm.add_selected_stock = AsyncMock(return_value=True)
    slots = {}
    tm.get_trading_stock = MagicMock(side_effect=lambda code, strategy=None: slots.setdefault(
        code, TradingStock(stock_code=code, stock_name=code, state=StockState.SELECTED,
                           selected_time=RESTORE_NOW)))
    tm._change_stock_state = MagicMock()
    r = StateRestorer(trading_manager=tm, db_manager=db_manager, telegram_integration=AsyncMock(),
                      config=config, get_previous_close_callback=lambda code: 4300.0,
                      broker=broker, fund_manager=None, virtual_trading_manager=None,
                      strategies=strategies)
    r.is_paper_trading = paper_trading
    return r, slots


def _real_broker(code="123456", qty=10, avg=4280.0):
    from tests.broker_contract import make_account_balance, make_holding
    broker = MagicMock()
    broker.get_pending_orders = MagicMock(return_value=[])
    broker.get_account_balance.return_value = make_account_balance(total_stocks=1)
    broker.get_holdings.return_value = [make_holding(stock_code=code, stock_name=code,
                                                     quantity=qty, avg_price=avg)]
    return broker


def _real_rows(code="123456", qty=10, owner=DT_KEY):
    # 실원장 스키마 그대로 — tp/sl 컬럼 «없음»(db/repositories/trading.py get_real_open_positions)
    return pd.DataFrame([{"id": 1, "stock_code": code, "stock_name": code, "quantity": qty,
                          "buy_price": 4280.0, "buy_time": BUY_TIME_9D, "strategy": owner,
                          "buy_reason": "체결"}])


class TestB2RealRestore:

    async def _restore(self, strategies):
        db = MagicMock()
        db.get_real_open_positions.return_value = _real_rows()
        r, slots = _restorer(strategies, False, db, broker=_real_broker())
        r._detect_holdings_mismatch = AsyncMock(return_value=[])
        with patch("bot.state_restorer.now_kst", return_value=RESTORE_NOW), \
             patch("bot.state_restorer.DatabaseConnection"):
            await r._restore_holdings_from_real_account()
        return slots["123456"]

    @pytest.mark.asyncio
    async def test_real_restore_uses_strategy_tp_sl_and_no_stale_tightening(self):
        ts = await self._restore({DT_KEY: _dt_strategy()})
        assert ts.days_held >= 7, "전제: 7거래일+ 보유(조임 조건에 걸리는 나이)"
        assert (ts.target_profit_rate, ts.stop_loss_rate) == (0.10, 0.10), "±5% 로 조여지면 안 된다"

    @pytest.mark.asyncio
    async def test_control_unresolvable_config_still_defaults_then_tightened(self):
        """대조: config 를 못 찾는 소유 전략은 종전 그대로(기본값 → 7거래일+ ±5%) — 이 테스트가 조임을 «볼 수 있다»."""
        strat = MagicMock()
        strat.name = "DayTrading3MethodsBreakoutStrategy"
        ts = await self._restore({DT_KEY: strat})
        assert (ts.target_profit_rate, ts.stop_loss_rate) == (STALE_DEFAULT_TARGET_PROFIT, STALE_DEFAULT_STOP_LOSS)


# =============================================================================
# (iv) 페이퍼 — 가상 매수·가상 복원 종전 그대로 (새 헬퍼 호출 0)
# =============================================================================
class TestB2PaperUnchanged:

    @pytest.mark.asyncio
    async def test_virtual_buy_unchanged_and_new_helpers_untouched(self):
        import core.trading_decision_engine as tde
        from core.trading_decision_engine import TradingDecisionEngine
        engine = TradingDecisionEngine(config=None)            # config None → 가상 모드
        assert engine.is_virtual_mode is True
        strat = MagicMock()
        strat.name = "DayTrading3MethodsBreakoutStrategy"
        strat.config = DT_CONFIG
        engine.set_strategies({DT_KEY: strat})
        engine.virtual_trading.execute_virtual_buy = MagicMock(return_value=101)
        ts = _ts()
        with patch.object(tde, "resolve_strategy_tp_sl", wraps=tde.resolve_strategy_tp_sl) as spy, \
             patch.object(engine, "_apply_owner_tp_sl_for_real_buy") as real_apply:
            ok = await engine.execute_virtual_buy(ts, None, "r", buy_price=4280.0, quantity=10,
                                                  strategy_name=DT_KEY)
        assert ok is True
        assert (ts.target_profit_rate, ts.stop_loss_rate) == (0.10, 0.10)
        kwargs = engine.virtual_trading.execute_virtual_buy.call_args.kwargs
        assert (kwargs["target_profit_rate"], kwargs["stop_loss_rate"]) == (0.10, 0.10)
        spy.assert_not_called()
        real_apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_virtual_restore_unchanged_even_with_strategy_config(self):
        """가상 복원은 B-2 를 타지 않는다 — NULL 행은 종전대로 기본값 → 7거래일+ ±5%, 기록값 행은 그 값."""
        db = MagicMock()
        db.get_virtual_open_positions.return_value = pd.DataFrame([
            {"id": 11, "stock_code": "111111", "stock_name": "a", "quantity": 10, "buy_price": 4280.0,
             "buy_time": BUY_TIME_9D, "strategy": DT_KEY, "target_profit_rate": None, "stop_loss_rate": None},
            {"id": 12, "stock_code": "222222", "stock_name": "b", "quantity": 10, "buy_price": 4280.0,
             "buy_time": BUY_TIME_9D, "strategy": DT_KEY, "target_profit_rate": 0.10, "stop_loss_rate": 0.10},
        ])
        r, slots = _restorer({DT_KEY: _dt_strategy()}, True, db)
        with patch("bot.state_restorer.now_kst", return_value=RESTORE_NOW), \
             patch("bot.state_restorer.resolve_strategy_tp_sl") as spy:
            await r._restore_holdings_from_db()
        spy.assert_not_called()
        assert (slots["111111"].target_profit_rate, slots["111111"].stop_loss_rate) == (
            STALE_DEFAULT_TARGET_PROFIT, STALE_DEFAULT_STOP_LOSS)
        assert (slots["222222"].target_profit_rate, slots["222222"].stop_loss_rate) == (0.10, 0.10)
