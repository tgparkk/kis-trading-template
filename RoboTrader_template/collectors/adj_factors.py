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
      adj_factor(T) = product(f for (ed, f) in events[stock] if ed > T)

    규약(2026-08-03 확정): **adj_close(T) = raw_close(T) / adj_factor(T)**

    따라서 events 가 넘기는 f 는 이미 *방향이 반영된* 계수여야 한다:
      - 정방향 분할 10:1  → f = 10    (분할 전 raw 156,500 / 10 = 15,650 = 현재 스케일)
      - 액면병합  1:10    → f = 1/10  (병합 전 raw   3,995 / 0.1 = 39,950 = 현재 스케일)

    이전에는 호출측이 corp_events.meta.split_factor 를 그대로 넘겼는데, 그 값은
    병합에도 >1 이라(실측: 011930 1:10 병합 sf=10.0 == 058430 10:1 분할 sf=10.0)
    병합 종목의 과거 가격이 정반대 방향으로 sf**2 만큼 틀어졌다. 방향 해석은
    corp_events.meta.direction 을 아는 호출측(collectors.daily_adj.load_split_events)
    책임이며, 이 함수는 넘겨받은 계수를 곱하기만 한다.

    ⚠️ daily_prices.close 는 (정상 경로에서는) 이미 조정된 연속 시세이므로 소비자가
    이 값을 close 에 적용해선 안 된다 — CLAUDE.md 「adj_factor 를 곱하지 말 것」 참조.
    adj_factor 는 원시 시세를 다룰 때만 쓰는 PIT 메타데이터다.

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
