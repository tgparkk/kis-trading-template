"""KISBroker 실계약 fixture — 모든 브로커 mock 의 유일한 출처.

2026-08-14 P0 스펙: 결함 4건 전부 「mock 이 실브로커에 없는 키(positions,
account_balance)를 발명」해 테스트가 green 인 채 숨었다. 이 모듈의 키 집합은
test_live_broker_contract.py 가 실브로커 반환과 동일함을 고정한다.
손으로 브로커 dict 를 만들지 말 것.
"""
from typing import Dict, List

# framework/broker.py get_account_balance() 반환 dict 의 전체 키 (:280-290)
ACCOUNT_BALANCE_KEYS = frozenset({
    'total_balance', 'available_cash', 'invested_amount',
    'total_profit_loss', 'total_profit_loss_rate', 'deposit_total',
    'next_day_amount', 'total_stocks', 'inquiry_time',
})

# api/kis_market_api.py get_account_balance()['stocks'] 항목 키 (:711-720)
# = KISBroker.get_holdings() 항목 키 (get_existing_holdings 가 그대로 반환)
HOLDING_ITEM_KEYS = frozenset({
    'stock_code', 'stock_name', 'quantity', 'avg_price',
    'current_price', 'eval_amount', 'profit_loss', 'profit_loss_rate',
})


def make_account_balance(**overrides) -> Dict:
    """생성: 실계약 계좌잔고 dict 기본값 + 재정의.

    실계약 키 집합을 벗어나려면 KeyError 를 낸다. 모든 후속 테스트는
    이 factory 만 쓸 것 — 손으로 dict 리터럴을 만들면 키가 漂流한다.
    """
    base = {
        'total_balance': 5_000_000,
        'available_cash': 4_000_000,
        'invested_amount': 1_000_000,
        'total_profit_loss': 0,
        'total_profit_loss_rate': 0.0,
        'deposit_total': 4_000_000,
        'next_day_amount': 4_000_000,
        'total_stocks': 0,
        'inquiry_time': '2026-08-14 08:00:00',
    }
    unknown = set(overrides) - ACCOUNT_BALANCE_KEYS
    if unknown:
        raise KeyError(f"실계약에 없는 키: {unknown}")
    base.update(overrides)
    return base


def make_holding(**overrides) -> Dict:
    """생성: 실계약 보유항목 dict 기본값 + 재정의.

    실계약 키 집합을 벗어나려면 KeyError 를 낸다. 모든 후속 테스트는
    이 factory 만 쓸 것 — 손으로 dict 리터럴을 만들면 키가 漂流한다.
    """
    base = {
        'stock_code': '005930', 'stock_name': '삼성전자',
        'quantity': 10, 'avg_price': 100_000.0,
        'current_price': 101_000.0, 'eval_amount': 1_010_000,
        'profit_loss': 10_000, 'profit_loss_rate': 1.0,
    }
    unknown = set(overrides) - HOLDING_ITEM_KEYS
    if unknown:
        raise KeyError(f"실계약에 없는 키: {unknown}")
    base.update(overrides)
    return base
