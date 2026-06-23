# collectors/daily_adj.py
"""adj_factor 갱신 — corp_events 분할이벤트 기반(새 DB). compute_adj_factors 재사용."""
import importlib

import psycopg2.extras

# p0_apply_adj_factor 는 패키지 경로에 숫자 시작 디렉토리(10pct_strategy)라 importlib 사용
_p0 = importlib.import_module("scripts.10pct_strategy.p0_apply_adj_factor")
compute_adj_factors = _p0.compute_adj_factors


def load_split_events(conn) -> dict:
    """새 DB corp_events 에서 split_factor 보유 분할이벤트 로드."""
    from collections import defaultdict
    events = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_code, event_date, (meta->>'split_factor')::float "
            "FROM corp_events "
            "WHERE event_type = 'split' AND meta->>'split_factor' IS NOT NULL "
            "ORDER BY stock_code, event_date"
        )
        for stock_code, event_date, sf in cur.fetchall():
            events[stock_code].append((event_date, float(sf)))
    return dict(events)


def load_stock_dates(conn, stock_codes) -> dict:
    """대상 종목들의 daily_prices 날짜 목록."""
    if not stock_codes:
        return {}
    out = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_code, date FROM daily_prices WHERE stock_code = ANY(%s) ORDER BY date",
            (list(stock_codes),),
        )
        for sc, d in cur.fetchall():
            out.setdefault(sc, []).append(d)
    return out


def _adj_update_rows(adj_map: dict):
    """{stock: {date: factor}} → [(factor, stock, date)] (factor != 1.0 만)."""
    rows = []
    for sc, date_adj in adj_map.items():
        for ds, af in date_adj.items():
            if abs(af - 1.0) > 1e-9:
                rows.append((af, sc, ds))
    return rows


def update_adj_factors(conn) -> int:
    events = load_split_events(conn)
    if not events:
        return 0
    stock_dates = load_stock_dates(conn, list(events.keys()))
    adj_map = compute_adj_factors(events, stock_dates)
    rows = _adj_update_rows(adj_map)
    if not rows:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            "UPDATE daily_prices SET adj_factor = %s, updated_at = now() "
            "WHERE stock_code = %s AND date = %s",
            rows, page_size=1000,
        )
    conn.commit()
    return len(rows)
