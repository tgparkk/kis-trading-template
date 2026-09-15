"""Circuit Breaker 로 매도가 «스킵»된 사실은 DEBUG 가 아니라 WARNING 이다.

결함(2026-09-15 결정 패널 §F-5 ④ · §D-7 확인): `position_monitor.py:421` 이
CB 활성 중 매도 시도를 통째로 건너뛰면서 `logger.debug` 로 남긴다. 운영 로그는
INFO 이상만 파일에 남으므로 **보유 종목의 손절이 막힌 사건이 로그에서 사라진다**
— 「조용함」이 정상과 구분되지 않는 전형적 거짓 음성.

이 파일이 단언하는 것:
  ① CB 활성 중 매도 스킵이 WARNING 으로 나온다
  ② 반환 동작은 그대로(스킵 후 즉시 return — 매도 시도 0회)
  ③ CB 가 없으면 이 경고가 «안» 뜬다

⚠️ `utils/logger.py:106` 이 `propagate = False` 라 caplog 가 루트로는 못 잡는다.
   caplog 핸들러를 모듈 로거에 직접 붙여 레벨을 실측한다.
"""
import logging
from unittest.mock import AsyncMock, Mock

import pytest

from core.trading import position_monitor as pm
from utils.korean_time import now_kst

MODULE_LOGGER = "core.trading.position_monitor"


@pytest.fixture
def capture(caplog):
    """모듈 로거(propagate=False)에 caplog 핸들러를 직접 연결한다."""
    logger = logging.getLogger(MODULE_LOGGER)
    prev_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(prev_level)


def _monitor():
    m = pm.PositionMonitor(Mock(), Mock(), Mock(), Mock())
    # setup_logger 가 생성 시점에 레벨을 LOG_LEVEL(기본 INFO)로 되돌린다.
    # DEBUG 로 낮춰야 「승격 전 = DEBUG」와 「승격 후 = WARNING」을 같은
    # 조건에서 구분해 볼 수 있다(운영은 INFO 이상만 파일에 남는다).
    logging.getLogger(MODULE_LOGGER).setLevel(logging.DEBUG)
    return m


def _stock(code="005930"):
    s = Mock()
    s.stock_code = code
    s.last_sell_timeout_time = None
    return s


@pytest.mark.asyncio
async def test_circuit_breaker_skip_is_warning(capture):
    m = _monitor()
    m._sell_fail_times["005930"] = now_kst()  # 방금 발동 → 쿨다운 중
    m._get_sell_price = AsyncMock()

    await m._execute_sell(_stock(), 10000.0, "손절")

    hits = [
        r for r in capture.records
        if "Circuit Breaker" in r.getMessage() and "매도 스킵" in r.getMessage()
    ]
    assert len(hits) == 1, [r.getMessage() for r in capture.records]
    assert hits[0].levelno == logging.WARNING
    assert hits[0].levelname == "WARNING"


@pytest.mark.asyncio
async def test_circuit_breaker_skip_still_returns_immediately(capture):
    """경고 승격이 동작을 바꾸지 않는다 — 매도 시도는 여전히 0회."""
    m = _monitor()
    m._sell_fail_times["005930"] = now_kst()
    m._get_sell_price = AsyncMock()

    result = await m._execute_sell(_stock(), 10000.0, "손절")

    assert result is None
    m._get_sell_price.assert_not_called()


@pytest.mark.asyncio
async def test_no_warning_when_circuit_breaker_inactive(capture):
    m = _monitor()
    m._get_sell_price = AsyncMock(return_value=None)

    await m._execute_sell(_stock(), 10000.0, "손절")

    assert not [
        r for r in capture.records
        if "Circuit Breaker" in r.getMessage() and "매도 스킵" in r.getMessage()
    ]
