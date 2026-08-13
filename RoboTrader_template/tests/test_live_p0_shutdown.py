"""D4(d): shutdown 이 존재하지 않는 broker.shutdown() 을 불러 후반부(PID 삭제)가 상시 스킵됐다."""
import asyncio
from unittest.mock import AsyncMock, Mock

from framework.broker import KISBroker
from bot.initializer import BotInitializer


def test_shutdown_reaches_pid_cleanup():
    bot = Mock()
    bot.telegram.shutdown = AsyncMock()
    bot.broker = Mock(spec=KISBroker)          # spec: 실브로커에 없는 메서드는 AttributeError
    bot.broker.disconnect = AsyncMock()
    bot.pid_file.exists.return_value = True
    init = BotInitializer(bot)
    init._flush_state_to_db = Mock()
    init._cancel_pending_orders = AsyncMock()
    asyncio.run(init.shutdown())
    bot.broker.disconnect.assert_awaited_once()
    bot.pid_file.unlink.assert_called_once()   # red: 현행은 AttributeError 로 미도달
