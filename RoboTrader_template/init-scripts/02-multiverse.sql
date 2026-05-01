-- multiverse Phase 0 스키마: composable_paramset / composable_position / corp_events
-- 적용 명령(사장님 권한): psql -h 127.0.0.1 -p 5433 -U robotrader -d robotrader -f init-scripts/02-multiverse.sql

-- ============================================================
-- 1. composable_paramset
--    Composable 전략의 84변수 ParamSet 직렬화 저장.
--    config_hash로 코드/config 버전 불일치 감지 지원.
-- ============================================================
CREATE TABLE IF NOT EXISTS composable_paramset (
    paramset_id   TEXT        PRIMARY KEY,
    json_blob     JSONB       NOT NULL,
    config_hash   TEXT        NOT NULL,
    code_version  TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_composable_paramset_config_hash
    ON composable_paramset(config_hash);

-- ============================================================
-- 2. composable_position
--    라이브 봇 재시작 시 포지션 상태 복원용.
--    entry_signal_json: 진입 시 충족된 시그널 스냅샷.
--    pending_scale_qty: 분할매수 잔여 수량.
-- ============================================================
CREATE TABLE IF NOT EXISTS composable_position (
    symbol              TEXT        NOT NULL,
    paramset_id         TEXT        NOT NULL
        REFERENCES composable_paramset(paramset_id) ON DELETE RESTRICT,
    entry_price         NUMERIC     NOT NULL,
    atr_at_entry        NUMERIC,
    lock_step           INTEGER     NOT NULL DEFAULT 0,
    held_days           INTEGER     NOT NULL DEFAULT 0,
    entry_signal_json   JSONB,
    pending_scale_qty   NUMERIC     NOT NULL DEFAULT 0,
    last_updated        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, paramset_id)
);

-- ============================================================
-- 3. corp_events
--    한국 시장 특수 이벤트: 액면분할/관리종목/거래정지 등.
--    PIT reader가 as_of_date 기준 Universe 필터에 활용.
-- ============================================================
CREATE TABLE IF NOT EXISTS corp_events (
    stock_code  TEXT  NOT NULL,
    event_type  TEXT  NOT NULL
        CHECK (event_type IN (
            'split',
            'rights_issue',
            'bonus_issue',
            'dividend_ex',
            'administrative',
            'caution',
            'warning',
            'halt'
        )),
    event_date  DATE  NOT NULL,
    meta        JSONB,
    PRIMARY KEY (stock_code, event_type, event_date)
);

CREATE INDEX IF NOT EXISTS idx_corp_events_event_date
    ON corp_events(event_date);

CREATE INDEX IF NOT EXISTS idx_corp_events_stock_date
    ON corp_events(stock_code, event_date);
