"""30분 상태 알림 Markdown 파싱 실패 수정 (10-29 창구 묶음 A ⑩).

원인: 템플릿 `시장: {market_status}` 에 `market_open` 같은 밑줄 값이 들어가 레거시 Markdown
엔티티 파싱 실패 → send_message 가 ERROR 후 `_escape_markdown` 재전송(도착은 함 · 하루 ~15회).
수정: market_status 값만 이스케이프. 재전송 폴백 자체는 그대로 둔다.
"""
import asyncio
import re
from unittest.mock import AsyncMock, patch

import pytest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _notifier():
    from utils.telegram.telegram_notifier import TelegramNotifier
    with patch("utils.telegram.telegram_notifier.Bot"), \
         patch("utils.telegram.telegram_notifier.HTTPXRequest"):
        n = TelegramNotifier("dummy", "1")
    n.bot.send_message = AsyncMock(return_value=True)
    return n


RAW_UNDERSCORE = re.compile(r"(?<!\\)_")


@pytest.mark.parametrize("status", ["market_open", "pre_market", "after_market", "closed"])
def test_status_message_has_no_raw_underscore_and_no_fallback(status):
    n = _notifier()
    with patch.object(n, "_escape_markdown", wraps=n._escape_markdown) as esc:
        _run(n.send_system_status(market_status=status, pending_orders=0, completed_orders=3))
    n.bot.send_message.assert_awaited_once()  # 첫 전송 1회 — 재전송 없음
    text = n.bot.send_message.await_args.kwargs["text"]
    assert not RAW_UNDERSCORE.search(text), text
    assert n.bot.send_message.await_args.kwargs["parse_mode"] == "Markdown"
    esc.assert_not_called()  # 폴백(전체 이스케이프) 경로 미호출
    assert "*시스템 상태*" in text  # 굵게 표시는 그대로


def test_status_value_escaped_once():
    n = _notifier()
    _run(n.send_system_status(market_status="market_open", pending_orders=1, completed_orders=2))
    text = n.bot.send_message.await_args.kwargs["text"]
    assert "시장: market\\_open\n" in text
    assert "미체결: 1건" in text and "완료: 2건" in text


def test_other_templates_unchanged():
    """다른 알림은 손대지 않는다(범위 밖)."""
    n = _notifier()
    _run(n.send_error_alert(module="a_b", error="x"))
    text = n.bot.send_message.await_args.kwargs["text"]
    assert "모듈: a_b" in text
