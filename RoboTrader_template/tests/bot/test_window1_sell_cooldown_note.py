"""매도 뒤 30분 재매수 금지 «불발» 기록 (10-29 창구 묶음 A ⑤ ③ · 코드 연결·제거 0).

10-22 패널(시스템): 설정 = 페이퍼 매도(engine set_sell_cooldown) · 검사 = 실전 매수
(order_execution is_sell_cooldown_active) → 서로 다른 경로라 불발. 11-05 결정 전까지 연결 금지.
여기서는 «기동 INFO 1줄» 과 «두 곳의 동작이 그대로» 만 확인한다.
"""
import asyncio
import inspect
from unittest.mock import Mock

COOLDOWN_NOTE = "[쿨다운] 매도 뒤 30분 재매수 금지는 현재 불발 상태(기록용)"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_startup_logs_cooldown_note_once():
    import bot.initializer as ini
    bot = Mock()
    bot.decision_engine.is_virtual_mode = True
    bot.decision_engine.virtual_trading.get_virtual_balance.return_value = 10_000_000
    init = ini.BotInitializer.__new__(ini.BotInitializer)
    init.bot = bot
    init.logger = Mock()
    _run(init._initialize_fund_manager())
    notes = [c.args[0] for c in init.logger.info.call_args_list if c.args and c.args[0] == COOLDOWN_NOTE]
    assert notes == [COOLDOWN_NOTE]
    bot.fund_manager.update_total_funds.assert_called_once_with(10_000_000)


def test_wiring_untouched_set_only_in_engine_check_only_in_order_execution():
    """동작 불변: 설정·검사 호출 위치는 각 1곳 그대로(연결·제거 금지)."""
    import core.trading_decision_engine as eng
    import core.trading.order_execution as oe
    eng_src = inspect.getsource(eng)
    oe_src = inspect.getsource(oe)
    assert eng_src.count("self.fund_manager.set_sell_cooldown(code, sell_reason)") == 1
    assert "self.fund_manager.is_sell_cooldown_active(" not in eng_src
    assert oe_src.count("self.fund_manager.is_sell_cooldown_active(stock_code)") == 1
    assert "self.fund_manager.set_sell_cooldown(" not in oe_src
    # 두 곳 모두 «불발 기록» 주석 블록을 단다
    for src in (eng_src, oe_src):
        assert "30분 재매수 쿨다운 불발" in src and "11-05" in src


def test_fund_manager_cooldown_semantics_unchanged():
    from core.fund_manager import FundManager
    fm = FundManager.__new__(FundManager)
    import threading
    fm._lock = threading.RLock()
    fm._sell_cooldowns = {}
    fm.sell_cooldown_minutes = 30
    fm.logger = Mock()
    assert fm.is_sell_cooldown_active("005930") is False
    fm.set_sell_cooldown("005930", "익절")
    assert fm.is_sell_cooldown_active("005930") is True
