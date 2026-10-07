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

    import pytest

    import main as main_mod

    bot = MagicMock()
    bot.pid_file = pid_file
    bot.telegram = telegram
    bot.initialize = AsyncMock(side_effect=LiveStartupAbort("잔고 조회 실패", "x"))
    monkeypatch.setattr(main_mod, "DayTradingBot", lambda: bot)
    monkeypatch.setattr("bot.env_guard.assert_correct_environment", lambda *_a, **_k: None)
    with pytest.raises(SystemExit) as ei:
        asyncio.run(main_mod.main())
    return ei.value.code


def test_abort_removes_own_pid_file_and_still_exits_2_with_alert(monkeypatch, tmp_path, caplog):
    import os
    from unittest.mock import AsyncMock, MagicMock

    pid_file = tmp_path / "robotrader_daytrading.pid"
    pid_file.write_text(str(os.getpid()))
    tg = MagicMock()
    tg.notify_urgent_signal = AsyncMock()

    import logging

    with caplog.at_level(logging.INFO):
        code = _run_main_with_abort(monkeypatch, pid_file, tg)

    assert code == 2
    assert not pid_file.exists()
    crit = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    expected = f"🚨 실전 기동 중단: {LiveStartupAbort('잔고 조회 실패', 'x')}"
    assert [r.getMessage() for r in crit] == [expected]
    assert any("기동 중단: PID 파일 정리 완료" in r.getMessage() for r in caplog.records)
    assert not any("PID 파일 삭제 완료" in r.getMessage() for r in caplog.records)
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


def test_abort_pid_cleanup_failure_does_not_mask_exit(monkeypatch, tmp_path, caplog):
    from unittest.mock import AsyncMock, MagicMock

    pid_file = MagicMock()
    pid_file.exists.side_effect = OSError("boom")
    tg = MagicMock()
    tg.notify_urgent_signal = AsyncMock()

    assert _run_main_with_abort(monkeypatch, pid_file, tg) == 2
    assert any("PID 파일 정리 실패(기동 중단)" in r.getMessage() for r in caplog.records)
    tg.notify_urgent_signal.assert_awaited_once()


def _run_main_with_init_false(monkeypatch, pid_file):
    """main() 을 initialize()=False 인 가짜 봇으로 실행 → SystemExit code 반환."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    import main as main_mod

    bot = MagicMock()
    bot.pid_file = pid_file
    bot.initialize = AsyncMock(return_value=False)
    monkeypatch.setattr(main_mod, "DayTradingBot", lambda: bot)
    monkeypatch.setattr("bot.env_guard.assert_correct_environment", lambda *_a, **_k: None)
    with pytest.raises(SystemExit) as ei:
        asyncio.run(main_mod.main())
    return ei.value.code


def test_init_false_removes_own_pid_file_and_exits_1(monkeypatch, tmp_path):
    import os

    pid_file = tmp_path / "robotrader.pid"
    pid_file.write_text(str(os.getpid()))

    assert _run_main_with_init_false(monkeypatch, pid_file) == 1
    assert not pid_file.exists()


def test_init_false_keeps_pid_file_of_other_process(monkeypatch, tmp_path):
    import os

    pid_file = tmp_path / "robotrader.pid"
    pid_file.write_text(str(os.getpid() + 1))

    assert _run_main_with_init_false(monkeypatch, pid_file) == 1
    assert pid_file.exists()


def test_init_false_pid_cleanup_failure_does_not_mask_exit(monkeypatch, tmp_path, caplog):
    from unittest.mock import MagicMock

    pid_file = MagicMock()
    pid_file.exists.side_effect = OSError("boom")

    assert _run_main_with_init_false(monkeypatch, pid_file) == 1
    assert any("PID 파일 정리 실패(초기화 실패)" in r.getMessage() for r in caplog.records)


def _run_main_script_with_crash(monkeypatch, tmp_path, pid_text):
    """`python main.py` 의 최상위 except Exception 경로 — asyncio.run 이 터지는 상태로 __main__ 실행."""
    import asyncio
    import runpy
    from pathlib import Path

    import pytest

    from config.settings import INSTANCE_ID
    from main import pid_file_name

    def _boom(_coro):
        _coro.close()
        raise RuntimeError("crash")

    monkeypatch.chdir(tmp_path)
    pid_file = Path(pid_file_name(INSTANCE_ID))
    if pid_text is not None:
        pid_file.write_text(pid_text)
    monkeypatch.setattr(asyncio, "run", _boom)
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    with pytest.raises(SystemExit) as ei:
        runpy.run_path(str(main_path), run_name="__main__")
    return ei.value.code, tmp_path / pid_file


def test_toplevel_crash_removes_own_pid_file_and_exits_1(monkeypatch, tmp_path):
    import os

    code, pid_file = _run_main_script_with_crash(monkeypatch, tmp_path, str(os.getpid()))
    assert code == 1
    assert not pid_file.exists()


def test_toplevel_crash_keeps_pid_file_of_other_process(monkeypatch, tmp_path):
    import os

    code, pid_file = _run_main_script_with_crash(monkeypatch, tmp_path, str(os.getpid() + 1))
    assert code == 1
    assert pid_file.exists()


def test_toplevel_crash_pid_cleanup_failure_does_not_mask_exit(monkeypatch, tmp_path, caplog):
    import os
    from pathlib import Path

    def _fail(*_a, **_k):
        raise OSError("boom")

    monkeypatch.setattr(Path, "read_text", _fail)
    code, pid_file = _run_main_script_with_crash(monkeypatch, tmp_path, str(os.getpid()))
    assert code == 1
    assert pid_file.exists()
    assert any("PID 파일 정리 실패(시스템 오류)" in r.getMessage() for r in caplog.records)
