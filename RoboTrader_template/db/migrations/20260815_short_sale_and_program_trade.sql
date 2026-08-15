-- 공매도 일별추이 + 종목별 프로그램매매 일별 (KIS TR FHPST04830000 / FHPPG04650201)
--
-- 왜: 태쏘 후보선정 역추론의 특징 9개(f1~f9)가 전부 가격·거래대금·변동성이고 **수급 축이
--     통째로 빠져 있었다**. 「18종목/일 → 1~2 선별」의 미설명 구간을 메울 후보 축이다.
--
-- 원문 필드는 `raw` JSONB 에 통째로 보존한다 — 컬럼을 골라 뽑는 순간 나중에 필요해진 필드가
-- 사라지고, 그때는 롤링 창이 지나 복구가 안 된다(재무 `dart_financials_asfiled` 에서 이미
-- 겪은 형태: 계정행 280만 중 DB엔 7컬럼만 남아 있었다).

CREATE TABLE IF NOT EXISTS short_sale_daily (
    stock_code           VARCHAR   NOT NULL,
    date                 DATE      NOT NULL,
    close                NUMERIC,
    open                 NUMERIC,
    high                 NUMERIC,
    low                  NUMERIC,
    avg_price            NUMERIC,          -- avrg_prc (공매도 평균가)
    acml_vol             BIGINT,           -- 누적 거래량
    ssts_cntg_qty        BIGINT,           -- 공매도 «체결수량»
    ssts_vol_rlim        NUMERIC,          -- 공매도 거래량 비중 (%)
    acml_ssts_cntg_qty   BIGINT,           -- 누적 공매도 수량
    ssts_tr_pbmn         BIGINT,           -- 공매도 거래대금
    ssts_tr_pbmn_rlim    NUMERIC,          -- 공매도 거래대금 비중 (%)
    raw                  JSONB,            -- KIS 원문 21필드 전체
    source               VARCHAR   DEFAULT 'kis_FHPST04830000',
    created_at           TIMESTAMP DEFAULT now(),
    PRIMARY KEY (stock_code, date)
);
CREATE INDEX IF NOT EXISTS ix_short_sale_daily_date ON short_sale_daily (date);

CREATE TABLE IF NOT EXISTS program_trade_daily (
    stock_code           VARCHAR   NOT NULL,
    date                 DATE      NOT NULL,
    close                NUMERIC,
    acml_vol             BIGINT,
    acml_tr_pbmn         BIGINT,
    seln_vol             BIGINT,           -- whol_smtn_seln_vol   프로그램 매도 수량
    shnu_vol             BIGINT,           -- whol_smtn_shnu_vol   프로그램 매수 수량
    ntby_qty             BIGINT,           -- whol_smtn_ntby_qty   프로그램 «순매수» 수량
    seln_tr_pbmn         BIGINT,
    shnu_tr_pbmn         BIGINT,
    ntby_tr_pbmn         BIGINT,           -- whol_smtn_ntby_tr_pbmn
    raw                  JSONB,            -- KIS 원문 15필드 전체
    source               VARCHAR   DEFAULT 'kis_FHPPG04650201',
    created_at           TIMESTAMP DEFAULT now(),
    PRIMARY KEY (stock_code, date)
);
CREATE INDEX IF NOT EXISTS ix_program_trade_daily_date ON program_trade_daily (date);
