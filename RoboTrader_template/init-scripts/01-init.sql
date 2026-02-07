-- =====================================================
-- RoboTrader TimescaleDB Schema Initialization
-- PostgreSQL 16 + TimescaleDB
-- =====================================================

-- TimescaleDB 확장 활성화
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =====================================================
-- 1. daily_prices (Hypertable) - 일봉 데이터
-- =====================================================
CREATE TABLE IF NOT EXISTS daily_prices (
    stock_code VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open NUMERIC(15, 2),
    high NUMERIC(15, 2),
    low NUMERIC(15, 2),
    close NUMERIC(15, 2),
    volume BIGINT,
    trading_value BIGINT,
    market_cap NUMERIC(20, 2),
    returns_1d NUMERIC(10, 6),
    returns_5d NUMERIC(10, 6),
    returns_20d NUMERIC(10, 6),
    volatility_20d NUMERIC(10, 6),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (stock_code, date)
);

-- Hypertable로 변환 (7일 청크)
SELECT create_hypertable('daily_prices', 'date',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_daily_prices_code ON daily_prices(stock_code);
CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON daily_prices(date DESC);

-- =====================================================
-- 2. minute_prices (Hypertable) - 분봉 데이터
-- =====================================================
CREATE TABLE IF NOT EXISTS minute_prices (
    stock_code VARCHAR(10) NOT NULL,
    datetime TIMESTAMPTZ NOT NULL,
    open NUMERIC(15, 2),
    high NUMERIC(15, 2),
    low NUMERIC(15, 2),
    close NUMERIC(15, 2),
    volume BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (stock_code, datetime)
);

-- Hypertable로 변환 (1일 청크)
SELECT create_hypertable('minute_prices', 'datetime',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_minute_prices_code ON minute_prices(stock_code);
CREATE INDEX IF NOT EXISTS idx_minute_prices_datetime ON minute_prices(datetime DESC);
CREATE INDEX IF NOT EXISTS idx_minute_prices_code_date ON minute_prices(stock_code, datetime DESC);

-- 압축 정책 (7일 이후 자동 압축)
ALTER TABLE minute_prices SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'stock_code'
);

SELECT add_compression_policy('minute_prices', INTERVAL '7 days', if_not_exists => TRUE);

-- 주의: 보존 정책(자동 삭제)은 의도적으로 설정하지 않음
-- 모든 데이터는 영구 보존됨

-- =====================================================
-- 3. candidate_stocks (일반 테이블) - 후보 종목
-- =====================================================
CREATE TABLE IF NOT EXISTS candidate_stocks (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(100),
    selection_date TIMESTAMPTZ NOT NULL,
    score NUMERIC(10, 4) NOT NULL,
    reasons TEXT,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_candidate_date ON candidate_stocks(selection_date DESC);
CREATE INDEX IF NOT EXISTS idx_candidate_code ON candidate_stocks(stock_code);
CREATE INDEX IF NOT EXISTS idx_candidate_status ON candidate_stocks(status);

-- =====================================================
-- 4. virtual_trading_records (일반 테이블) - 가상 매매 기록
-- =====================================================
CREATE TABLE IF NOT EXISTS virtual_trading_records (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(100),
    action VARCHAR(10) NOT NULL,  -- 'BUY' or 'SELL'
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_virtual_trading_code_date ON virtual_trading_records(stock_code, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_virtual_trading_action ON virtual_trading_records(action);
CREATE INDEX IF NOT EXISTS idx_virtual_trading_test ON virtual_trading_records(is_test);
CREATE INDEX IF NOT EXISTS idx_virtual_trading_timestamp ON virtual_trading_records(timestamp DESC);

-- 중복 매도 방지 Partial Unique Index
CREATE UNIQUE INDEX IF NOT EXISTS idx_virtual_trading_unique_sell
ON virtual_trading_records(buy_record_id)
WHERE action = 'SELL' AND buy_record_id IS NOT NULL;

-- =====================================================
-- 5. real_trading_records (일반 테이블) - 실거래 매매 기록
-- =====================================================
CREATE TABLE IF NOT EXISTS real_trading_records (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(100),
    action VARCHAR(10) NOT NULL,  -- 'BUY' or 'SELL'
    quantity INTEGER NOT NULL,
    price NUMERIC(15, 2) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    strategy VARCHAR(50),
    reason TEXT,
    profit_loss NUMERIC(15, 2) DEFAULT 0,
    profit_rate NUMERIC(10, 6) DEFAULT 0,
    buy_record_id INTEGER REFERENCES real_trading_records(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_real_trading_code_date ON real_trading_records(stock_code, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_real_trading_action ON real_trading_records(action);
CREATE INDEX IF NOT EXISTS idx_real_trading_timestamp ON real_trading_records(timestamp DESC);

-- =====================================================
-- 6. financial_data (일반 테이블) - 재무 데이터
-- =====================================================
CREATE TABLE IF NOT EXISTS financial_data (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    base_year VARCHAR(4) NOT NULL,
    base_quarter VARCHAR(2) NOT NULL,
    report_date VARCHAR(10),
    per NUMERIC(15, 4),
    pbr NUMERIC(15, 4),
    eps NUMERIC(15, 2),
    bps NUMERIC(15, 2),
    roe NUMERIC(10, 4),
    roa NUMERIC(10, 4),
    debt_ratio NUMERIC(10, 4),
    operating_margin NUMERIC(10, 4),
    sales NUMERIC(20, 2),
    net_income NUMERIC(20, 2),
    market_cap NUMERIC(20, 2),
    industry_code VARCHAR(20),
    retrieved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(stock_code, base_year, base_quarter)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_financial_data_code ON financial_data(stock_code);
CREATE INDEX IF NOT EXISTS idx_financial_data_base ON financial_data(base_year, base_quarter);

-- =====================================================
-- 7. financial_statements (일반 테이블) - ML용 재무제표 데이터
-- =====================================================
CREATE TABLE IF NOT EXISTS financial_statements (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    report_date VARCHAR(10) NOT NULL,
    fiscal_quarter VARCHAR(10),
    per NUMERIC(15, 4),
    pbr NUMERIC(15, 4),
    psr NUMERIC(15, 4),
    dividend_yield NUMERIC(10, 4),
    roe NUMERIC(10, 4),
    debt_ratio NUMERIC(10, 4),
    operating_margin NUMERIC(10, 4),
    net_margin NUMERIC(10, 4),
    revenue NUMERIC(20, 2),
    operating_profit NUMERIC(20, 2),
    net_income NUMERIC(20, 2),
    total_assets NUMERIC(20, 2),
    current_assets NUMERIC(20, 2),
    current_liabilities NUMERIC(20, 2),
    total_liabilities NUMERIC(20, 2),
    total_equity NUMERIC(20, 2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(stock_code, report_date)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_financial_statements_code_date ON financial_statements(stock_code, report_date);

-- =====================================================
-- 8. quant_factors (일반 테이블) - 팩터 점수
-- =====================================================
CREATE TABLE IF NOT EXISTS quant_factors (
    id SERIAL PRIMARY KEY,
    calc_date VARCHAR(10) NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    value_score NUMERIC(10, 4),
    momentum_score NUMERIC(10, 4),
    quality_score NUMERIC(10, 4),
    growth_score NUMERIC(10, 4),
    total_score NUMERIC(10, 4),
    factor_rank INTEGER,
    factor_details TEXT,  -- JSON 형태로 저장
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(calc_date, stock_code)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_quant_factors_date ON quant_factors(calc_date);
CREATE INDEX IF NOT EXISTS idx_quant_factors_rank ON quant_factors(calc_date, factor_rank);
CREATE INDEX IF NOT EXISTS idx_quant_factors_code ON quant_factors(stock_code);

-- =====================================================
-- 9. quant_portfolio (일반 테이블) - 상위 포트폴리오
-- =====================================================
CREATE TABLE IF NOT EXISTS quant_portfolio (
    id SERIAL PRIMARY KEY,
    calc_date VARCHAR(10) NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(100),
    rank INTEGER,
    total_score NUMERIC(10, 4),
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(calc_date, stock_code)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_quant_portfolio_date ON quant_portfolio(calc_date);
CREATE INDEX IF NOT EXISTS idx_quant_portfolio_rank ON quant_portfolio(calc_date, rank);

-- =====================================================
-- 10. stock_prices (일반 테이블) - 기존 호환용 종목 가격 데이터
-- =====================================================
CREATE TABLE IF NOT EXISTS stock_prices (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    date_time TIMESTAMPTZ NOT NULL,
    open_price NUMERIC(15, 2),
    high_price NUMERIC(15, 2),
    low_price NUMERIC(15, 2),
    close_price NUMERIC(15, 2),
    volume BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(stock_code, date_time)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_price_code_date ON stock_prices(stock_code, date_time DESC);

-- =====================================================
-- 11. trading_records (일반 테이블) - 레거시 매매 기록
-- =====================================================
CREATE TABLE IF NOT EXISTS trading_records (
    id SERIAL PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    action VARCHAR(10) NOT NULL,
    quantity INTEGER NOT NULL,
    price NUMERIC(15, 2) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    profit_loss NUMERIC(15, 2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_trading_code_date ON trading_records(stock_code, timestamp DESC);

-- =====================================================
-- 유틸리티 함수: updated_at 자동 갱신 트리거
-- =====================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 트리거 적용
CREATE TRIGGER update_daily_prices_updated_at
    BEFORE UPDATE ON daily_prices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_financial_data_updated_at
    BEFORE UPDATE ON financial_data
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_financial_statements_updated_at
    BEFORE UPDATE ON financial_statements
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_quant_factors_updated_at
    BEFORE UPDATE ON quant_factors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_quant_portfolio_updated_at
    BEFORE UPDATE ON quant_portfolio
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- 완료 메시지
-- =====================================================
DO $$
BEGIN
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'RoboTrader TimescaleDB Schema initialized successfully!';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Hypertables created:';
    RAISE NOTICE '  - daily_prices (7-day chunks)';
    RAISE NOTICE '  - minute_prices (1-day chunks, compression after 7 days, NO auto-delete)';
    RAISE NOTICE '';
    RAISE NOTICE 'Regular tables created:';
    RAISE NOTICE '  - candidate_stocks';
    RAISE NOTICE '  - virtual_trading_records';
    RAISE NOTICE '  - real_trading_records';
    RAISE NOTICE '  - financial_data';
    RAISE NOTICE '  - financial_statements';
    RAISE NOTICE '  - quant_factors';
    RAISE NOTICE '  - quant_portfolio';
    RAISE NOTICE '  - stock_prices (legacy compatibility)';
    RAISE NOTICE '  - trading_records (legacy)';
    RAISE NOTICE '=====================================================';
END $$;
