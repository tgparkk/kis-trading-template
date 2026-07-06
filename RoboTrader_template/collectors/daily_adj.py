# collectors/daily_adj.py
"""adj_factor 갱신 — corp_events 분할이벤트 기반(새 DB). compute_adj_factors 재사용."""
import psycopg2.extras

from collectors.adj_factors import compute_adj_factors


def load_split_events(conn) -> dict:
    """새 DB corp_events 에서 split_factor 보유 split 이벤트 로드(조정 시점=권리락일).

    조정 시점은 event_date(PK, DART 공시일)가 아니라 실제 권리락일이다 —
    split_factor_infer 가 meta.effective_date 에 기록한 갭 발생일을 우선 사용하고
    (COALESCE), 레거시 pykrx 백필 105건처럼 effective_date 가 없는 행은 event_date
    (이미 ex-date로 적재됨)를 그대로 쓴다.

    동일 (stock_code, 권리락일)에 대해 중복 행(예: 공시일-PK 행 + 과거 코드가 PK를
    이동시켜 만든 ex-date-PK 행)이 존재하면 이중조정(factor 제곱)을 막기 위해
    (stock_code, 권리락일) 당 1건만 채택한다(2026-07-06 code review, R2).
    """
    from collections import defaultdict
    events = defaultdict(list)
    seen = set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_code, "
            "COALESCE((meta->>'effective_date')::date, event_date) AS eff_date, "
            "(meta->>'split_factor')::float "
            "FROM corp_events "
            "WHERE event_type = 'split' AND meta->>'split_factor' IS NOT NULL "
            "ORDER BY stock_code, eff_date"
        )
        for stock_code, eff_date, sf in cur.fetchall():
            key = (stock_code, eff_date)
            if key in seen:
                continue
            seen.add(key)
            events[stock_code].append((eff_date, float(sf)))
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
    """{stock: {date: factor}} → [(factor, stock, date)] 전 종목·전 날짜(1.0 포함).

    이벤트가 있는 종목(adj_map 키)만 대상 — 그 종목들의 모든 날짜에 "현재 이벤트
    기준으로 계산된" adj_factor 를 완전히 다시 쓴다(1.0 도 포함). 잘못된 스탬프가
    나중에 정정되면(이벤트 삭제·factor·effective_date 수정) 그 구간이 자동으로 1.0
    으로 원복되도록 자가치유(self-healing)한다 — != 1.0 만 쓰던 예전 필터는 정정을
    반영하지 못했다(2026-07-06 code review, R4). 이벤트가 아예 없는 종목은 adj_map 에
    들어오지 않으므로 여기서도 손대지 않는다.
    """
    rows = []
    for sc, date_adj in adj_map.items():
        for ds, af in date_adj.items():
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
