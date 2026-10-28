"""KRX 주식 호가가격단위 — 2023-01-25 개편 표 고정 (2026-10-09 · fix/real-flow-7).

출처: 한국거래소 「호가가격단위(Tick Size)」 안내
regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T3.jsp (2026-10-09 확인) —
2,000원 미만 1 · 2,000~5,000 미만 5 · 5,000~20,000 미만 10 · 20,000~50,000 미만 50 ·
50,000~200,000 미만 100 · 200,000~500,000 미만 500 · 500,000 이상 1,000 (유가증권·코스닥 통일).

같은 표가 두 곳에 있다(`utils/price_utils._get_tick_size` = 실전 주문가·페이퍼 가상 체결가 ·
`framework/utils.get_tick_size` = 주문 직전 호가 검증 `validate_tick`). 하나로 모으는 것은 범위 밖 —
여기서는 «두 표가 같다»를 고정한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from framework.utils import get_tick_size, round_to_tick as fw_round, validate_tick  # noqa: E402
from utils.price_utils import _get_tick_size, round_to_tick as pu_round  # noqa: E402

BOUNDARIES = [
    (1, 1), (999, 1), (1_000, 1), (1_999, 1),
    (2_000, 5), (4_999, 5),
    (5_000, 10), (19_999, 10),
    (20_000, 50), (49_999, 50),
    (50_000, 100), (199_999, 100),
    (200_000, 500), (499_999, 500),
    (500_000, 1_000), (2_000_000, 1_000),
]


@pytest.mark.parametrize("price,tick", BOUNDARIES)
def test_boundaries_price_utils(price, tick):
    assert _get_tick_size(price) == tick


@pytest.mark.parametrize("price,tick", BOUNDARIES)
def test_boundaries_framework(price, tick):
    assert get_tick_size(price) == tick


def _sweep():
    ps = set()
    for lo, hi, step in [(1, 3_000, 1), (3_000, 25_000, 7), (25_000, 250_000, 53),
                         (250_000, 1_200_000, 499)]:
        ps.update(range(lo, hi, step))
    for b, _ in BOUNDARIES:
        ps.update({b - 1, b, b + 1})
    ps.discard(0)
    return sorted(ps)


def test_two_tables_are_identical_and_rounding_agrees():
    """두 함수가 같은 표 — 정수·소수 가격 전부에서 단위와 반올림 결과가 같다."""
    for p in _sweep():
        for x in (p, p + 0.4, p + 0.5, p - 0.5):
            assert get_tick_size(x) == _get_tick_size(x), x
            assert fw_round(x) == int(pu_round(x)), x


def test_rounded_price_always_passes_order_tick_validation():
    """주문가 반올림(price_utils) 결과는 주문 직전 검증(framework validate_tick)을 늘 통과한다 —
    구간 경계(2,000·5,000·20,000·50,000·200,000·500,000)가 다음 구간 단위의 배수라 경계 넘김도 안전."""
    for p in _sweep():
        for x in (p, p + 0.49, p + 0.5):
            r = int(pu_round(x))
            assert validate_tick(r), (x, r)


def test_order_api_round_and_validate_follow_new_table():
    from api.kis_order_api import _round_to_krx_tick, _validate_tick_size
    assert _round_to_krx_tick(1_234) == 1_234             # 개편 전 1,235(5원)
    assert _round_to_krx_tick(12_345) == 12_350           # 10원 반올림 (개편 전 12,350 = 50원 · 우연 일치)
    assert _round_to_krx_tick(12_334) == 12_330           # 개편 전 12,350
    assert _round_to_krx_tick(123_456) == 123_500         # 100원 반올림 (개편 전 123,500 = 500원)
    assert _round_to_krx_tick(123_420) == 123_400         # 개편 전 123,500
    assert _validate_tick_size(1_234) is True             # 개편 전 False → 호가 보정으로 1,235 에 주문됐다
    assert _validate_tick_size(12_330) is True
    assert _validate_tick_size(123_400) is True
    assert _validate_tick_size(2_001) is False
    assert _validate_tick_size(20_010) is False
    assert _validate_tick_size(200_100) is False
