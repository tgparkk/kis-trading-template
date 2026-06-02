-- Phase 5 시그널 테이블: 외국인 순매수 + VKOSPI 일봉
-- 적용 명령 (사장님 권한):
--   psql -h 127.0.0.1 -p 5433 -U robotrader -d robotrader -f init-scripts/06-phase5-signals.sql
--
-- 설계 원칙:
--   - 두 테이블 모두 robotrader DB (메인 DB) 에 생성
--   - INSERT ON CONFLICT DO NOTHING (멱등, 재실행 무해)
--   - 자동삭제 금지 (retention policy 없음)

-- =====================================================
-- 1. foreign_flow_daily — 외국인 일별 순매수
-- =====================================================
-- PIT 보장: trade_date = T일 데이터, T+1 시초가부터 사용 가능
CREATE TABLE IF NOT EXISTS foreign_flow_daily (
    stock_code    VARCHAR(10)  NOT NULL,
    trade_date    DATE         NOT NULL,
    net_buy_vol   BIGINT,          -- 순매수거래량 (주수)
    net_buy_val   BIGINT,          -- 순매수거래대금 (원)
    created_at    TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (stock_code, trade_date)
);

COMMENT ON TABLE foreign_flow_daily IS
    '외국인 일별 순매수 데이터. pykrx get_market_net_purchases_of_equities("외국인") 백필.
     PIT: trade_date T일 → T+1 시초가 의사결정에 사용 가능.
     자동삭제 금지.';

CREATE INDEX IF NOT EXISTS idx_ffd_date
    ON foreign_flow_daily(trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_ffd_code_date
    ON foreign_flow_daily(stock_code, trade_date DESC);

-- =====================================================
-- 2. vkospi_daily — VKOSPI 일봉
-- =====================================================
-- PIT 보장: trade_date = T일 종가 → T+1 시초가부터 사용 가능
CREATE TABLE IF NOT EXISTS vkospi_daily (
    trade_date    DATE         NOT NULL PRIMARY KEY,
    open          NUMERIC(10, 4),
    high          NUMERIC(10, 4),
    low           NUMERIC(10, 4),
    close         NUMERIC(10, 4),
    volume        BIGINT,
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);

COMMENT ON TABLE vkospi_daily IS
    'VKOSPI(코스피200 변동성지수) 일봉. pykrx get_index_ohlcv("VKOSPI") 백필.
     PIT: trade_date T일 종가 → T+1 시초가 의사결정에 사용 가능.
     자동삭제 금지.';

CREATE INDEX IF NOT EXISTS idx_vkospi_date
    ON vkospi_daily(trade_date DESC);
