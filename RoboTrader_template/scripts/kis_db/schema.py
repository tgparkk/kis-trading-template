"""kis_template DB 스키마(멱등). 레거시 스키마와 동일 컬럼/PK(드롭인) + 신규 2테이블.

usage: python -m scripts.kis_db.schema
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402

EXPECTED_TABLES = {
    # 시장데이터 (기존)
    "minute_candles", "daily_prices", "index_daily",
    "corp_events", "collection_reconciliation", "foreign_flow",
    # 운영 테이블 (Phase A — init-scripts 01/05)
    "virtual_trading_records", "real_trading_records",
    "paper_trading_state",
    "candidate_stocks", "screener_snapshots",
    # paper_strategy_equity — tools/paper_strategy_equity._ensure_table 에서
    # 승격된 DDL(Task 2, PAPER_STRATEGY_EQUITY_DDL)
    "paper_strategy_equity",
}

# paper_strategy_equity — tools/paper_strategy_equity._ensure_table 에서 승격(SSOT).
PAPER_STRATEGY_EQUITY_DDL = """
    CREATE TABLE IF NOT EXISTS paper_strategy_equity (
        trade_date date NOT NULL,
        strategy varchar(50) NOT NULL,
        source varchar(50) NOT NULL DEFAULT 'kis_template',
        cash numeric(15,2) NOT NULL,
        position_value numeric(15,2) NOT NULL,
        equity numeric(15,2) NOT NULL,
        realized_pnl_cum numeric(15,2) NOT NULL,
        n_open integer NOT NULL,
        updated_at timestamptz DEFAULT now(),
        PRIMARY KEY (trade_date, strategy, source)
    )
    """

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
    # ── 운영 테이블 (init-scripts/01-init.sql 컬럼/인덱스/제약 그대로) ──────────
    # 후보 종목
    """
    CREATE TABLE IF NOT EXISTS candidate_stocks (
        id SERIAL PRIMARY KEY,
        stock_code VARCHAR(10) NOT NULL,
        stock_name VARCHAR(100),
        selection_date TIMESTAMPTZ NOT NULL,
        score NUMERIC(10, 4) NOT NULL,
        reasons TEXT,
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_candidate_date ON candidate_stocks(selection_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_candidate_code ON candidate_stocks(stock_code)",
    "CREATE INDEX IF NOT EXISTS idx_candidate_status ON candidate_stocks(status)",
    # 가상 매매 기록 (source 컬럼 포함 — 05-vtr-source-column.sql)
    """
    CREATE TABLE IF NOT EXISTS virtual_trading_records (
        id SERIAL PRIMARY KEY,
        stock_code VARCHAR(10) NOT NULL,
        stock_name VARCHAR(100),
        action VARCHAR(10) NOT NULL,
        quantity INTEGER NOT NULL,
        price NUMERIC(15, 2) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        strategy VARCHAR(50),
        reason TEXT,
        is_test BOOLEAN DEFAULT TRUE,
        profit_loss NUMERIC(15, 2) DEFAULT 0,
        profit_rate NUMERIC(10, 6) DEFAULT 0,
        buy_record_id INTEGER REFERENCES virtual_trading_records(id),
        target_profit_rate NUMERIC(10, 6),
        stop_loss_rate NUMERIC(10, 6),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        source VARCHAR(50)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_code_date ON virtual_trading_records(stock_code, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_action ON virtual_trading_records(action)",
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_test ON virtual_trading_records(is_test)",
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_timestamp ON virtual_trading_records(timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_source ON virtual_trading_records(source)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_virtual_trading_unique_sell
    ON virtual_trading_records(buy_record_id)
    WHERE action = 'SELL' AND buy_record_id IS NOT NULL
    """,
    # 실거래 기록 base (동적 real_trading_{instance} 의 LIKE 템플릿)
    """
    CREATE TABLE IF NOT EXISTS real_trading_records (
        id SERIAL PRIMARY KEY,
        stock_code VARCHAR(10) NOT NULL,
        stock_name VARCHAR(100),
        action VARCHAR(10) NOT NULL,
        quantity INTEGER NOT NULL,
        price NUMERIC(15, 2) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        strategy VARCHAR(50),
        reason TEXT,
        profit_loss NUMERIC(15, 2) DEFAULT 0,
        profit_rate NUMERIC(10, 6) DEFAULT 0,
        buy_record_id INTEGER REFERENCES real_trading_records(id),
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_real_trading_code_date ON real_trading_records(stock_code, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_real_trading_action ON real_trading_records(action)",
    "CREATE INDEX IF NOT EXISTS idx_real_trading_timestamp ON real_trading_records(timestamp DESC)",
    # 스크리너 시점 스냅샷 (jsonb params_json/metadata)
    """
    CREATE TABLE IF NOT EXISTS screener_snapshots (
        id BIGSERIAL PRIMARY KEY,
        strategy VARCHAR(50) NOT NULL,
        scan_date DATE NOT NULL,
        params_hash VARCHAR(40) NOT NULL,
        params_json JSONB NOT NULL,
        stock_code VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100),
        rank_in_snapshot INT,
        score DOUBLE PRECISION,
        metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (strategy, scan_date, params_hash, stock_code)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_screener_snapshots_strategy_date ON screener_snapshots (strategy, scan_date)",
    "CREATE INDEX IF NOT EXISTS idx_screener_snapshots_params ON screener_snapshots (strategy, params_hash)",
    # 가상매매 EOD 잔고 이월
    """
    CREATE TABLE IF NOT EXISTS paper_trading_state (
        trade_date  DATE PRIMARY KEY,
        eod_balance NUMERIC(15, 2) NOT NULL,
        updated_at  TIMESTAMPTZ DEFAULT now()
    )
    """,
    PAPER_STRATEGY_EQUITY_DDL,
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
