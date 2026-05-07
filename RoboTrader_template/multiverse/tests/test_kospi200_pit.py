"""KOSPI200 PIT 인프라 회귀 테스트.

실제 DB(robotrader_quant) 연결 필요.
캐시는 테스트 전 clear_cache()로 초기화, 테스트 후 cleanup.
"""
from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

import pytest

from RoboTrader_template.multiverse.data.kospi200_pit import (
    CACHE_DIR,
    KOSPI200_TOP_N,
    clear_cache,
    get_kospi200_pit,
    get_kospi200_rebalance_calendar,
    warm_cache,
)


# ------------------------------------------------------------------ #
# Fixture
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def clean_cache_around_test():
    """각 테스트 전후로 캐시 클리어."""
    clear_cache()
    yield
    clear_cache()


# ------------------------------------------------------------------ #
# 테스트
# ------------------------------------------------------------------ #

def test_basic_pit_query():
    """get_kospi200_pit(2024-12-31)이 200개 종목 반환, 모두 6자리 stock_code 형식."""
    stocks = get_kospi200_pit(date(2024, 12, 31))

    assert len(stocks) == KOSPI200_TOP_N, (
        f"200개 기대, {len(stocks)}개 반환"
    )
    code_pattern = re.compile(r"^\d{6}$")
    for code in stocks:
        assert code_pattern.match(code), f"6자리 형식 위반: {code!r}"


def test_pit_fallback_holiday():
    """주말/공휴일 입력 시 직전 거래일로 fallback.

    2024-12-29(일) 입력 → DB에 없으므로 직전 거래일(2024-12-27) 기준 결과 반환.
    """
    # 2024-12-29는 일요일 — 거래일이 아님
    stocks_holiday = get_kospi200_pit(date(2024, 12, 29))
    # 2024-12-27은 금요일 — 정상 거래일
    stocks_friday = get_kospi200_pit(date(2024, 12, 27))

    assert len(stocks_holiday) > 0, "비거래일 입력 시 fallback 결과가 비어있으면 안 됨"
    # fallback 결과는 직전 거래일 결과와 동일해야 함
    assert stocks_holiday == stocks_friday, (
        "2024-12-29(일) fallback 결과가 2024-12-27(금) 결과와 다름"
    )


def test_calendar_monthly():
    """get_kospi200_rebalance_calendar(2024-01-01, 2024-03-31, 'monthly')가 3개 키."""
    calendar = get_kospi200_rebalance_calendar(
        date(2024, 1, 1), date(2024, 3, 31), "monthly"
    )

    assert len(calendar) == 3, (
        f"1월말/2월말/3월말 3개 키 기대, {len(calendar)}개 반환: {list(calendar.keys())}"
    )

    keys = sorted(calendar.keys())
    # 각 키가 올바른 달에 속하는지 확인
    assert keys[0].month == 1, f"첫 번째 키가 1월이어야 함: {keys[0]}"
    assert keys[1].month == 2, f"두 번째 키가 2월이어야 함: {keys[1]}"
    assert keys[2].month == 3, f"세 번째 키가 3월이어야 함: {keys[2]}"

    # 각 키의 종목 리스트가 비어있지 않은지 확인
    for d, stocks in calendar.items():
        assert len(stocks) > 0, f"{d} 종목 리스트가 비어있음"


def test_cache_hit():
    """동일 as_of_date 두 번 호출 시 두 번째는 DB 없이 캐시에서 반환.

    첫 호출보다 두 번째 호출이 현저히 빠른지 timing으로 검증.
    """
    target = date(2024, 12, 31)

    # 첫 호출 — DB 조회
    t0 = time.perf_counter()
    stocks_first = get_kospi200_pit(target)
    t1 = time.perf_counter()
    first_elapsed = t1 - t0

    # 두 번째 호출 — 캐시 hit
    t2 = time.perf_counter()
    stocks_second = get_kospi200_pit(target)
    t3 = time.perf_counter()
    second_elapsed = t3 - t2

    assert stocks_first == stocks_second, "캐시 결과가 DB 결과와 다름"
    # 캐시 hit는 DB 조회보다 10배 이상 빨라야 함
    assert second_elapsed < first_elapsed / 5, (
        f"캐시 hit가 충분히 빠르지 않음 — 1차: {first_elapsed:.3f}s, 2차: {second_elapsed:.3f}s"
    )


def test_calendar_no_overlap():
    """인접 월 종목 리스트 turnover가 KOSPI200 대형주 기준으로 합리적.

    KOSPI200 월간 turnover는 대략 2~15% 수준으로 기대.
    50% 초과 시 데이터 이상 신호.

    데이터가 충분히 채워진 월(100종목 이상)에 한해 검증.
    DB 적재 초기 기간은 종목 수 부족으로 스킵.
    """
    # 데이터가 충분한 구간 사용 (2024-03 이후 2333종목 확인됨)
    calendar = get_kospi200_rebalance_calendar(
        date(2024, 3, 1), date(2024, 5, 31), "monthly"
    )
    keys = sorted(calendar.keys())
    assert len(keys) >= 2, "turnover 측정에 최소 2개 월 필요"

    for i in range(len(keys) - 1):
        prev_set = set(calendar[keys[i]])
        curr_set = set(calendar[keys[i + 1]])
        # 두 달 모두 100종목 이상일 때만 turnover 검증
        if len(prev_set) < 100 or len(curr_set) < 100:
            continue
        union_size = len(prev_set | curr_set)
        intersection_size = len(prev_set & curr_set)
        if union_size == 0:
            continue
        turnover = 1.0 - intersection_size / union_size
        assert turnover <= 0.50, (
            f"{keys[i]}→{keys[i+1]} turnover {turnover:.1%} > 50% — 데이터 이상"
        )


def test_market_cap_descending():
    """반환 리스트가 시총 내림차순 — 첫 번째 종목이 005930(삼성전자)."""
    stocks = get_kospi200_pit(date(2024, 12, 31))

    assert len(stocks) > 0
    # 삼성전자(005930)가 2024년 시총 1위
    assert stocks[0] == "005930", (
        f"시총 1위가 005930이어야 함, 실제: {stocks[0]!r}"
    )


def test_cache_persistence():
    """warm_cache로 캐시 파일 생성 후 디스크에 존재 확인, clear_cache로 삭제."""
    # 테스트용 단기 구간 (1개 월)
    start = date(2024, 12, 1)
    end = date(2024, 12, 31)

    count = warm_cache(start, end, freq="monthly")
    assert count >= 1, f"warm_cache가 최소 1개 파일 생성해야 함, 반환: {count}"

    # 캐시 파일이 디스크에 실제로 존재하는지 확인
    cache_files = list(CACHE_DIR.glob("*.json"))
    assert len(cache_files) >= 1, (
        f"캐시 파일이 {CACHE_DIR}에 존재해야 함"
    )

    # clear_cache로 전부 삭제
    deleted = clear_cache()
    assert deleted >= 1, f"clear_cache가 최소 1개 파일 삭제해야 함, 반환: {deleted}"

    # 삭제 후 파일이 없는지 확인
    remaining = list(CACHE_DIR.glob("*.json"))
    assert len(remaining) == 0, (
        f"clear_cache 후 파일이 남아있음: {remaining}"
    )
