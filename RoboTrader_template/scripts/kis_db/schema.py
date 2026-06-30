"""kis_template DB 스키마(멱등). 레거시 스키마와 동일 컬럼/PK(드롭인) + 신규 2테이블.

usage: python -m scripts.kis_db.schema
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402

EXPECTED_TABLES = {
    "minute_candles", "daily_prices", "index_daily",
    "corp_events", "collection_reconciliation", "foreign_flow",
}

DDL_STATEMENTS = [
    # 분봉 (robotrader.minute_candles 동일)
    """
    CREATE TABLE IF NOT EXISTS minute_candles (
        stock_code VARCHAR NOT NULL,
        trade_date VARCHAR NOT NULL,
        idx INTEGER NOT NULL,
        date VARCHAR,
        time VARCHAR,
        close DOUBLE PRECISION,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        volume DOUBLE PRECISION,
        amount DOUBLE PRECISION,
        datetime TIMESTAMP,
        PRIMARY KEY (stock_code, trade_date, idx)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_minute_candles_code_date ON minute_candles(stock_code, trade_date)",
    # 일봉 (robotrader_quant.daily_prices 동일 — date 는 TEXT)
    """
    CREATE TABLE IF NOT EXISTS daily_prices (
        stock_code VARCHAR NOT NULL,
        date TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume BIGINT,
        trading_value BIGINT,
        market_cap DOUBLE PRECISION,
        returns_1d DOUBLE PRECISION,
        returns_5d DOUBLE PRECISION,
        returns_20d DOUBLE PRECISION,
        volatility_20d DOUBLE PRECISION,
        adj_factor DOUBLE PRECISION,
        created_at TIMESTAMP DEFAULT now(),
        updated_at TIMESTAMP DEFAULT now(),
        PRIMARY KEY (stock_code, date)
    )
    """,
    # 지수 일봉 (신규 — KOSPI/KOSDAQ)
    """
    CREATE TABLE IF NOT EXISTS index_daily (
        index_code VARCHAR NOT NULL,
        date TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume DOUBLE PRECISION,
        created_at TIMESTAMP DEFAULT now(),
        PRIMARY KEY (index_code, date)
    )
    """,
    # corp_events (robotrader.corp_events 동일)
    """
    CREATE TABLE IF NOT EXISTS corp_events (
        stock_code TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_date DATE NOT NULL,
        end_date DATE,
        meta JSONB,
        PRIMARY KEY (stock_code, event_type, event_date)
    )
    """,
    # 외국인 순매매량 (robotrader_quant.foreign_flow 동일 — 네이버 금융 소스)
    """
    CREATE TABLE IF NOT EXISTS foreign_flow (
        stock_code VARCHAR NOT NULL,
        date DATE NOT NULL,
        foreign_net_vol BIGINT,
        source VARCHAR DEFAULT 'naver',
        created_at TIMESTAMP DEFAULT now(),
        PRIMARY KEY (stock_code, date)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_foreign_flow_date ON foreign_flow(date)",
    # 교차 DB 비교 결과 (신규)
    """
    CREATE TABLE IF NOT EXISTS collection_reconciliation (
        trade_date TEXT NOT NULL,
        dataset VARCHAR NOT NULL,
        real_rows INTEGER,
        new_rows INTEGER,
        overlap INTEGER,
        value_match_rate DOUBLE PRECISION,
        coverage DOUBLE PRECISION,
        verdict VARCHAR,
        created_at TIMESTAMP DEFAULT now(),
        PRIMARY KEY (trade_date, dataset)
    )
    """,
]


def create_all(conn) -> None:
    with conn.cursor() as cur:
        for ddl in DDL_STATEMENTS:
            cur.execute(ddl)
    conn.commit()


if __name__ == "__main__":
    with KisDbConnection.get_connection() as conn:
        create_all(conn)
    print(f"스키마 생성 완료: {sorted(EXPECTED_TABLES)}")
