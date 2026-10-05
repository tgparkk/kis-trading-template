from utils.exceptions import LiveStartupAbort


def test_abort_carries_reason_and_details():
    exc = LiveStartupAbort("잔고 조회 실패", "get_account_balance()={}")
    assert exc.reason == "잔고 조회 실패"
    assert "잔고 조회 실패" in str(exc) and "get_account_balance" in str(exc)


def test_abort_is_not_swallowed_by_generic_handler_contract():
    """LiveStartupAbort 는 Exception 파생 — main 최상위 except 가 잡되
    전용 분기가 먼저 잡아 exit code 2 로 구분한다(아래 main.py 수정)."""
    assert issubclass(LiveStartupAbort, Exception)


def test_abort_alert_method_exists_on_telegram_integration():
    """main.py 기동 중단 경보가 부르는 메서드가 실제로 존재해야 한다.
    (send_notification 이라는 유령 메서드를 부르다 except 에 삼켜진 전례 방지)"""
    from core.telegram_integration import TelegramIntegration
    assert callable(getattr(TelegramIntegration, 'notify_urgent_signal', None))


def _run_main_with_abort(monkeypatch, pid_file, telegram):
    """main() 을 LiveStartupAbort 를 던지는 가짜 봇으로 실행 → SystemExit 반환."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import main as main_mod

    bot = MagicMock()
    bot.pid_file = pid_file
    bot.telegram = telegram
    bot.initialize = AsyncMock(side_effect=LiveStartupAbort("잔고 조회 실패", "x"))
    monkeypatch.setattr(main_mod, "DayTradingBot", lambda: bot)
    monkeypatch.setattr("bot.env_guard.assert_correct_environment", lambda *_a, **_k: None)
    with __import__("pytest").raises(SystemExit) as ei:
        asyncio.run(main_mod.main())
    return ei.value.code


def test_abort_removes_own_pid_file_and_still_exits_2_with_alert(monkeypatch, tmp_path):
    import os
    from unittest.mock import AsyncMock, MagicMock

    pid_file = tmp_path / "robotrader_daytrading.pid"
    pid_file.write_text(str(os.getpid()))
    tg = MagicMock()
    tg.notify_urgent_signal = AsyncMock()

    code = _run_main_with_abort(monkeypatch, pid_file, tg)

    assert code == 2
    assert not pid_file.exists()
    tg.notify_urgent_signal.assert_awaited_once()
    assert "실전 기동 중단" in tg.notify_urgent_signal.await_args.args[0]


def test_abort_keeps_pid_file_of_other_process_and_exits_2(monkeypatch, tmp_path):
    import os
    from unittest.mock import AsyncMock, MagicMock

    pid_file = tmp_path / "robotrader_daytrading.pid"
    pid_file.write_text(str(os.getpid() + 1))
    tg = MagicMock()
    tg.notify_urgent_signal = AsyncMock()

    assert _run_main_with_abort(monkeypatch, pid_file, tg) == 2
    assert pid_file.exists()


def test_abort_pid_cleanup_failure_does_not_mask_exit(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock, MagicMock

    pid_file = MagicMock()
    pid_file.exists.side_effect = OSError("boom")
    tg = MagicMock()
    tg.notify_urgent_signal = AsyncMock()

    assert _run_main_with_abort(monkeypatch, pid_file, tg) == 2
