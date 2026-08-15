-- 신용잔고 일별추이 + 시간외 단일가 일별 (KIS TR FHPST04760000 / FHPST02320000)
--
-- 왜: 태쏘 후보선정 「18종목/일 → 1~2」의 미설명 구간을 메울 축을 계속 넓힌다.
--   - **신용잔고**: 융자·대주 잔고와 «공여율». 개인 레버리지가 몰린 종목을 가른다.
--   - **시간외**: 급등주는 정규장이 끝난 뒤에도 움직인다. 정규장 종가만 보면 안 보이는 축.
--
-- ⚠️ 둘 다 공급 TR 이 **최근 30 거래일 롤링**이다 — 조회 시작일 파라미터가 없어
--    놓친 날은 **영구 결손**이다. EOD 파이프라인 편입이 필수다.
--
-- 원문은 `raw` JSONB 에 통째로 보존한다(컬럼을 골라 뽑으면 나중에 필요해진 필드가 사라지고
-- 그때는 창이 지나 복구가 안 된다 — `dart_financials_asfiled` 에서 겪은 형태).

CREATE TABLE IF NOT EXISTS credit_balance_daily (
    stock_code        VARCHAR   NOT NULL,
    date              DATE      NOT NULL,   -- KIS 원문은 `deal_date`
    close             NUMERIC,
    acml_vol          BIGINT,
    loan_new_stcn     BIGINT,               -- 융자 신규 수량
    loan_rdmp_stcn    BIGINT,               -- 융자 상환 수량
    loan_rmnd_stcn    BIGINT,               -- 융자 «잔고» 수량
    loan_rmnd_amt     BIGINT,               -- 융자 잔고 금액
    loan_rmnd_rate    NUMERIC,              -- 융자 잔고 비율
    loan_gvrt         NUMERIC,              -- 융자 «공여율»
    stln_new_stcn     BIGINT,               -- 대주 신규
    stln_rdmp_stcn    BIGINT,
    stln_rmnd_stcn    BIGINT,               -- 대주 잔고 수량
    stln_rmnd_amt     BIGINT,
    stln_rmnd_rate    NUMERIC,
    stln_gvrt         NUMERIC,
    raw               JSONB,
    source            VARCHAR   DEFAULT 'kis_FHPST04760000',
    created_at        TIMESTAMP DEFAULT now(),
    PRIMARY KEY (stock_code, date)
);
CREATE INDEX IF NOT EXISTS ix_credit_balance_daily_date ON credit_balance_daily (date);

CREATE TABLE IF NOT EXISTS overtime_daily (
    stock_code        VARCHAR   NOT NULL,
    date              DATE      NOT NULL,
    ovtm_close        NUMERIC,              -- 시간외 단일가
    ovtm_vol          BIGINT,               -- 시간외 거래량
    ovtm_tr_pbmn      BIGINT,               -- 시간외 거래대금
    ovtm_ctrt         NUMERIC,              -- 시간외 등락률
    reg_close         NUMERIC,              -- 정규장 종가 (대조용)
    raw               JSONB,
    source            VARCHAR   DEFAULT 'kis_FHPST02320000',
    created_at        TIMESTAMP DEFAULT now(),
    PRIMARY KEY (stock_code, date)
);
CREATE INDEX IF NOT EXISTS ix_overtime_daily_date ON overtime_daily (date);
