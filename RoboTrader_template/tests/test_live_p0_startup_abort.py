import pytest

from utils.exceptions import LiveStartupAbort


def test_abort_carries_reason_and_details():
    exc = LiveStartupAbort("잔고 조회 실패", "get_account_balance()={}")
    assert exc.reason == "잔고 조회 실패"
    assert "잔고 조회 실패" in str(exc) and "get_account_balance" in str(exc)


def test_abort_is_not_swallowed_by_generic_handler_contract():
    """LiveStartupAbort 는 Exception 파생 — main 최상위 except 가 잡되
    전용 분기가 먼저 잡아 exit code 2 로 구분한다(아래 main.py 수정)."""
    assert issubclass(LiveStartupAbort, Exception)
