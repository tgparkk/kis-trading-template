"""D1: 실전 총자금 = min(real_total_funds_cap, 실계좌 total_balance). 무언 폴백 금지."""
import asyncio
from unittest.mock import Mock

import pytest

from tests.broker_contract import make_account_balance
from utils.exceptions import LiveStartupAbort
from bot.initializer import BotInitializer


def _init_with(cap, balance_return):
    bot = Mock()
    bot.config.real_total_funds_cap = cap
    # 실제 페이퍼/실전 분기 조건은 `bot.decision_engine.is_virtual_mode` 다
    # (bot/initializer.py:661) — `bot.config.paper_trading` 가 아니다. brief 원문은
    # 후자를 세팅하지만 그건 프로덕션 코드가 읽지 않는 속성이라 분기가 안 갈린다.
    bot.decision_engine.is_virtual_mode = False
    bot.broker.get_account_balance.return_value = balance_return
    init = BotInitializer(bot)
    return bot, init


def _run(init):
    asyncio.run(init._initialize_fund_manager())


class TestRealFundInit:
    def test_uses_total_balance_key_not_invented_account_balance(self):
        """red 재현: 현행은 없는 키 account_balance 를 읽어 상수 1천만원."""
        bot, init = _init_with(cap=100_000_000,
                               balance_return=make_account_balance(total_balance=5_000_000))
        _run(init)
        bot.fund_manager.update_total_funds.assert_called_once_with(5_000_000.0)

    def test_cap_wins_when_smaller(self):
        bot, init = _init_with(cap=3_000_000,
                               balance_return=make_account_balance(total_balance=5_000_000))
        _run(init)
        bot.fund_manager.update_total_funds.assert_called_once_with(3_000_000.0)

    @pytest.mark.parametrize("bad_balance", [{}, make_account_balance(total_balance=0)])
    def test_query_failure_or_zero_aborts(self, bad_balance):
        """red 재현: 현행은 조용히 1천만원 폴백."""
        bot, init = _init_with(cap=3_000_000, balance_return=bad_balance)
        with pytest.raises(LiveStartupAbort):
            _run(init)
        bot.fund_manager.update_total_funds.assert_not_called()

    @pytest.mark.parametrize("bad_cap", [None, 0, -1])
    def test_missing_cap_aborts(self, bad_cap):
        bot, init = _init_with(cap=bad_cap,
                               balance_return=make_account_balance(total_balance=5_000_000))
        with pytest.raises(LiveStartupAbort):
            _run(init)

    def test_non_numeric_cap_aborts(self):
        """리뷰 Important: 생 ValueError 로 죽으면 main 의 텔레그램 경보를 건너뛴다."""
        bot, init = _init_with(cap="abc",
                               balance_return=make_account_balance(total_balance=5_000_000))
        with pytest.raises(LiveStartupAbort):
            _run(init)
        bot.fund_manager.update_total_funds.assert_not_called()

    def test_non_numeric_balance_aborts(self):
        """리뷰 Important: fixture 의 키 가드는 값 타입을 안 막는다 — override 로 문자열 주입."""
        bot, init = _init_with(cap=3_000_000,
                               balance_return=make_account_balance(total_balance="N/A"))
        with pytest.raises(LiveStartupAbort):
            _run(init)
        bot.fund_manager.update_total_funds.assert_not_called()


def test_paper_mode_unchanged():
    """라이브 불변: 페이퍼 분기는 이 Task 가 건드리지 않는다."""
    bot = Mock()
    bot.decision_engine.is_virtual_mode = True
    # bot = Mock() 이라 미설정 속성은 전부 자식 Mock — virtual_trading 도 기본값이
    # None 이 아니라 Mock 이 되어 `get_virtual_balance() <= 0` 비교가 TypeError 로
    # 깨진다(실코드가 아니라 mock 배선 문제). None 으로 명시해 실코드의 else 경로를 태운다.
    bot.decision_engine.virtual_trading = None
    init = BotInitializer(bot)
    asyncio.run(init._initialize_fund_manager())
    bot.broker.get_account_balance.assert_not_called()
