"""분할이벤트 → adj_factor 계산 (scripts/10pct_strategy/p0_apply_adj_factor.py 에서 승격).

승격 사유: collectors/daily_adj.py 가 라이브 EOD 경로에서 사용하는데, 원 위치가
숫자 시작 디렉토리(10pct_strategy)라 importlib 동적 import 를 강제 — 정적 분석 불가
지뢰였음 (2026-07-02 Phase1, 동작 무변경).
"""
import math
from datetime import date


def compute_adj_factors(events: dict, stock_dates: dict) -> dict:
    """
    For each (stock, date T):
      adj_factor(T) = product(sf for (ed, sf) in events[stock] if ed > T)

    Returns: {stock_code: {date_str: adj_factor}}
    """
    result = {}
    for stock_code, ev_list in events.items():
        if stock_code not in stock_dates:
            continue
        dates = stock_dates[stock_code]
        stock_result = {}
        for date_str in dates:
            try:
                t = date.fromisoformat(date_str)
            except ValueError:
                stock_result[date_str] = 1.0
                continue
            future_factors = [sf for (ed, sf) in ev_list if ed > t]
            stock_result[date_str] = math.prod(future_factors) if future_factors else 1.0
        result[stock_code] = stock_result
    return result
