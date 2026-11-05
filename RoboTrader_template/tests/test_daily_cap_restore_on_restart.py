"""장중 재기동 하루 매수 한도 복원 (2026-11-05 창구 2회 묶음 P · D · 결함 10-16).

결함: 8전략 하루 매수 한도는 메모리 `daily_trades` 하나로만 막는데, 장중 재기동 → 장시작 콜백
`on_market_open()` 이 0 으로 둬 그날 한도가 0부터 다시 셌다(최대 5건 추가 매수 가능).
수정: `main._call_strategy_market_open()` 이 콜백 «뒤»에 전략마다
`daily_trades = max(현재, 오늘 KST 그 전략 DB BUY 수)` 로 복원한다.

🔴 함정: `strategy` 열 표기 — 페이퍼 `virtual_trading_records` = 폴더키
(`daytrading_3methods_breakout`) · 실전 인스턴스 표 `real_trading_<id>` = 클래스명
(`DayTrading3MethodsBreakoutStrategy`). 복원은 두 표기를 모두 넘겨 센다.

⚠️ 로거는 propagate=False 라 caplog 로 안 잡힌다 — Mock 로거를 꽂아 호출을 직접 본다.
실 봇 기동·실 DB 접속 없음(재기동 시뮬 = 아래 test_restart_simulation_* 의 콜백 경로).
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tests._mock_modules  # noqa: F401,E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from strategies.base import OrderInfo  # noqa: E402
from strategies.config import StrategyLoader  # noqa: E402

DT_KEY = "daytrading_3methods_breakout"
DT_CLASS = "DayTrading3MethodsBreakoutStrategy"
ROOT = Path(__file__).resolve().parent.parent


class _FakeRepo:
    """count_today_buys 만 흉내 — 표(페이퍼/실전)별 «오늘» BUY 행의 strategy 값 목록."""

    def __init__(self, virtual=(), real=(), exc=None):
        self.virtual = list(virtual)
        self.real = list(real)
        self.exc = exc
        self.calls = []

    def count_today_buys(self, strategy_names, is_virtual=True):
        self.calls.append((set(strategy_names), is_virtual))
        if self.exc is not None:
            raise self.exc
        rows = self.virtual if is_virtual else self.real
        return sum(1 for s in rows if s in set(strategy_names))


def _bot(strategies, repo, is_virtual=True):
    from main import DayTradingBot
    bot = DayTradingBot.__new__(DayTradingBot)       # 무거운 초기화 없이 콜백 경로만 시험
    bot.logger = MagicMock()
    bot.strategies = dict(strategies)
    bot.strategy = next(iter(bot.strategies.values())) if bot.strategies else None
    bot.db_manager = Mock(trading_repo=repo)
    bot.decision_engine = Mock(is_virtual_mode=is_virtual)
    return bot


def _load(name, **risk):
    st = StrategyLoader.load_strategy(name)
    if risk:
        st.config.setdefault("risk_management", {}).update(risk)
    assert st.on_init(broker=None, data_provider=None, executor=None)
    st.logger = Mock()
    return st


def _restore_lines(bot):
    return [c.args[0] for c in bot.logger.info.call_args_list
            if c.args and str(c.args[0]).startswith("[하루 한도 복원]")]


def _buy_fill(code):
    return OrderInfo(order_id="O1", stock_code=code, side="buy", quantity=1,
                     price=10000.0, filled_at=datetime(2026, 11, 5, 9, 20))


def _daily(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    flat = np.full(n, 10000.0)
    return pd.DataFrame({"datetime": idx, "open": flat, "high": flat, "low": flat,
                         "close": flat, "volume": np.full(n, 100000.0)})


# (1) 정상 07:40 기동 = 장시작 때 DB BUY 0 → 무동작 ---------------------------------

@pytest.mark.asyncio
async def test_normal_start_db_zero_is_noop(monkeypatch):
    monkeypatch.delenv("DAILY_CAP_RESTORE", raising=False)
    st = _load(DT_KEY)
    st.daily_trades = 3                                   # 전날 값 — 장시작 콜백이 0 으로 둔다
    bot = _bot({DT_KEY: st}, _FakeRepo())
    await bot._call_strategy_market_open()
    assert st.daily_trades == 0
    assert _restore_lines(bot) == []
    bot.logger.warning.assert_not_called()


# (2) 장중 재기동 · 페이퍼 표(폴더키) BUY 3 → daily_trades 3 ------------------------------

@pytest.mark.asyncio
async def test_paper_restart_restores_from_folder_key(monkeypatch):
    monkeypatch.delenv("DAILY_CAP_RESTORE", raising=False)
    st = _load(DT_KEY)
    repo = _FakeRepo(virtual=[DT_KEY] * 3 + ["rs_leader"] * 2 + [DT_CLASS])  # 다른 전략·표기 섞음
    bot = _bot({DT_KEY: st}, repo, is_virtual=True)
    await bot._call_strategy_market_open()
    assert st.daily_trades == 4                           # 폴더키 3 + 클래스명 1(둘 다 dt) · rs 제외
    names, is_virtual = repo.calls[0]
    assert {DT_KEY, DT_CLASS} <= names and is_virtual is True
    assert _restore_lines(bot) == [f"[하루 한도 복원] {DT_KEY} 오늘 BUY 4 → daily_trades 4"]


# (3) 실전 인스턴스 표(클래스명) BUY 3 → daily_trades 3 ---------------------------------

@pytest.mark.asyncio
async def test_real_restart_restores_from_class_name(monkeypatch):
    monkeypatch.delenv("DAILY_CAP_RESTORE", raising=False)
    st = _load(DT_KEY)
    repo = _FakeRepo(virtual=[DT_KEY] * 5, real=[DT_CLASS] * 3)  # 페이퍼 표는 실전에서 안 본다
    bot = _bot({DT_KEY: st}, repo, is_virtual=False)
    await bot._call_strategy_market_open()
    assert st.daily_trades == 3
    assert repo.calls[0][1] is False
    assert _restore_lines(bot) == [f"[하루 한도 복원] {DT_KEY} 오늘 BUY 3 → daily_trades 3"]


# (4) 롤백 스위치 off → 복원 생략(조회도 안 함) -----------------------------------------

@pytest.mark.parametrize("raw", ["off", "0", "false", "no", " OFF "])
@pytest.mark.asyncio
async def test_switch_off_skips_restore(monkeypatch, raw):
    monkeypatch.setenv("DAILY_CAP_RESTORE", raw)
    st = _load(DT_KEY)
    repo = _FakeRepo(virtual=[DT_KEY] * 3)
    bot = _bot({DT_KEY: st}, repo)
    await bot._call_strategy_market_open()
    assert st.daily_trades == 0
    assert repo.calls == []


def test_switch_parsing_default_on():
    from config.constants import resolve_daily_cap_restore
    assert resolve_daily_cap_restore(None) == (True, None)
    assert resolve_daily_cap_restore("  ") == (True, None)
    assert resolve_daily_cap_restore("on") == (True, None)
    assert resolve_daily_cap_restore(" Yes ") == (True, None)
    assert resolve_daily_cap_restore("No") == (False, None)
    assert resolve_daily_cap_restore("off  # 롤백") == (True, "off  # 롤백")   # 미지값 = on + 원문


@pytest.mark.asyncio
async def test_unknown_switch_value_warns_once_and_keeps_on(monkeypatch):
    """인라인 주석 등 미지값 → WARNING 1줄(repr 원값) + 기본 on 유지(복원 진행)."""
    monkeypatch.setenv("DAILY_CAP_RESTORE", "off  # 롤백")
    st = _load(DT_KEY)
    bot = _bot({DT_KEY: st}, _FakeRepo(virtual=[DT_KEY] * 2))
    await bot._call_strategy_market_open()
    assert st.daily_trades == 2
    assert bot.logger.warning.call_count == 1
    msg = bot.logger.warning.call_args.args[0]
    assert "DAILY_CAP_RESTORE" in msg and repr("off  # 롤백") in msg and "기본 on 유지" in msg


# (5) 조회 예외 → fail-open(복원 0 · WARNING 1줄 · 다른 전략은 계속) ------------------------

@pytest.mark.asyncio
async def test_query_exception_fails_open(monkeypatch):
    monkeypatch.delenv("DAILY_CAP_RESTORE", raising=False)
    a, b = _load(DT_KEY), _load("rs_leader")

    class _HalfBroken(_FakeRepo):
        def count_today_buys(self, strategy_names, is_virtual=True):
            if DT_KEY in strategy_names:
                raise RuntimeError("db down")
            return super().count_today_buys(strategy_names, is_virtual)

    bot = _bot({DT_KEY: a, "rs_leader": b}, _HalfBroken(virtual=["rs_leader"] * 2))
    await bot._call_strategy_market_open()
    assert a.daily_trades == 0                            # 현상 유지(0부터)
    assert b.daily_trades == 2                            # 다른 전략은 복원
    assert bot.logger.warning.call_count == 1
    assert "fail-open" in bot.logger.warning.call_args.args[0]


@pytest.mark.asyncio
async def test_non_int_result_fails_open(monkeypatch):
    """MagicMock 레포 등 정수가 아닌 반환은 복원하지 않는다(int(MagicMock()) == 1 함정)."""
    monkeypatch.delenv("DAILY_CAP_RESTORE", raising=False)
    st = _load(DT_KEY)
    bot = _bot({DT_KEY: st}, MagicMock())
    await bot._call_strategy_market_open()
    assert st.daily_trades == 0
    assert bot.logger.warning.call_count == 1


# (6) 10-28 M1(_pending_buy_count)과 이중 계상 없음 -------------------------------------

@pytest.mark.asyncio
async def test_restore_does_not_absorb_pending_buys(monkeypatch):
    """DB BUY = 체결분만. 복원값에 미체결은 들어가지 않고, 한도 판정에서 M1 이 따로 더한다."""
    monkeypatch.delenv("DAILY_CAP_RESTORE", raising=False)
    st = _load(DT_KEY, max_daily_trades=5, max_positions=10)
    filled = ["000001", "000002", "000003"]
    for c in filled:                                      # 재기동 복원 = 보유 3(체결분)
        st.positions[c] = {"quantity": 1, "entry_price": 10000.0, "entry_time": None}
    pending = ["338840"]                                  # 재기동 뒤 엔진이 아는 미체결 매수 1
    st.pending_buy_codes_provider = lambda: list(pending)
    st._check_buy = Mock(return_value="BUY")

    bot = _bot({DT_KEY: st}, _FakeRepo(virtual=[DT_KEY] * 3))
    await bot._call_strategy_market_open()
    assert st.daily_trades == 3                           # 3(체결) — 미체결 1 을 흡수하지 않음
    assert st._pending_buy_count() == 1
    # 3 + 1 = 4 < 5 → 새 신호 통과
    assert st.generate_signal("005930", _daily(), timeframe="daily") == "BUY"

    # 미체결이 체결되면 positions 로 옮겨 가 pending 0 · daily_trades 4 → 합 4(이중 0)
    pending.clear()
    st.on_order_filled(_buy_fill("338840"))
    assert (st.daily_trades, st._pending_buy_count()) == (4, 0)
    # 새 미체결 1 → 4 + 1 = 5 → 막힘
    pending.append("111111")
    assert st.generate_signal("005930", _daily(), timeframe="daily") is None


# 재기동 시뮬 — 페이퍼 8전략 전부(config/trading_config.json) · 폴더키 표기 --------------------

@pytest.mark.asyncio
async def test_restart_simulation_paper_all_8_strategies(monkeypatch):
    monkeypatch.delenv("DAILY_CAP_RESTORE", raising=False)
    cfg = json.loads((ROOT / "config" / "trading_config.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in cfg.get("strategies", []) if s.get("enabled", True)]
    assert len(names) == 8
    strategies = {n: _load(n) for n in names}             # 새 프로세스 = on_init 직후 0
    caps_before = {n: (s._max_daily_trades, s._max_positions) for n, s in strategies.items()}
    buys = {n: (i % 5) + 1 for i, n in enumerate(names)}  # 전략마다 오늘 체결 1~5
    rows = [n for n, k in buys.items() for _ in range(k)]
    bot = _bot(strategies, _FakeRepo(virtual=rows), is_virtual=True)
    await bot._call_strategy_market_open()
    assert {n: s.daily_trades for n, s in strategies.items()} == buys
    assert len(_restore_lines(bot)) == 8
    bot.logger.warning.assert_not_called()
    # 한도·K 숫자는 건드리지 않는다
    assert {n: (s._max_daily_trades, s._max_positions) for n, s in strategies.items()} == caps_before


@pytest.mark.asyncio
async def test_restart_simulation_real_instance_cap_reached_blocks_buy(monkeypatch):
    """실전 dt 인스턴스: 오늘 체결 5(클래스명) 뒤 재기동 → 복원 5 → 새 신호 막힘(K·한도 숫자 불변)."""
    monkeypatch.delenv("DAILY_CAP_RESTORE", raising=False)
    st = _load(DT_KEY, max_daily_trades=5, max_positions=10)
    st._check_buy = Mock(return_value="BUY")
    bot = _bot({DT_KEY: st}, _FakeRepo(real=[DT_CLASS] * 5), is_virtual=False)
    assert st.generate_signal("005930", _daily(), timeframe="daily") == "BUY"  # 복원 전 = 결함
    await bot._call_strategy_market_open()
    assert st.daily_trades == 5 and st._max_daily_trades == 5
    assert st.generate_signal("005930", _daily(), timeframe="daily") is None


# 조회 메서드 SQL — 표 선택·KST 날짜·표기 2종 전달 ---------------------------------------------

def _repo_with_cursor(real_table, count):
    from db.repositories.trading import TradingRepository
    repo = TradingRepository.__new__(TradingRepository)
    repo._real_table = real_table
    repo.logger = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = (count,)
    conn = Mock()
    conn.cursor.return_value = cursor
    cm = MagicMock()
    cm.__enter__.return_value = conn
    repo._get_connection = Mock(return_value=cm)
    return repo, cursor


@pytest.mark.parametrize("is_virtual,table", [(True, "virtual_trading_records"),
                                              (False, "real_trading_daytrading")])
def test_count_today_buys_sql(is_virtual, table):
    repo, cursor = _repo_with_cursor("real_trading_daytrading", 3)
    with patch("db.repositories.trading.now_kst", return_value=datetime(2026, 11, 5, 10, 30)):
        n = repo.count_today_buys({DT_KEY, DT_CLASS, None}, is_virtual=is_virtual)
    assert n == 3
    sql, params = cursor.execute.call_args.args
    assert f"FROM {table} " in sql
    assert "action = 'BUY'" in sql and "AT TIME ZONE 'Asia/Seoul'" in sql
    assert "strategy = ANY(%s)" in sql
    assert [DT_CLASS, DT_KEY] in [p for p in params if isinstance(p, list)]
    assert params[-1] == "2026-11-05"
    if is_virtual:
        assert "is_test = true" in sql and params[0] == "kis_template"


def test_count_today_buys_empty_names_no_query():
    repo, cursor = _repo_with_cursor("real_trading_records", 9)
    assert repo.count_today_buys([None, ""], is_virtual=True) == 0
    cursor.execute.assert_not_called()
