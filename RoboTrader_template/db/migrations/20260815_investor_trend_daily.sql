-- 종목별 일자별 투자자 매매동향 (KIS TR FHKST01010900)
--
-- 왜 필요한가: 기존 수급 테이블 `foreign_flow` 는 **627 종목**뿐이고 외국인 «수량» 한 컬럼이다.
--   태쏘 매매일지 역추론에서 후보 선정 축에 수급이 통째로 빠져 있었는데(f1~f9 전부 가격·거래대금·
--   변동성), 소형주 커버리지가 없어 유니버스 백분위를 못 냈다.
--
-- ⚠️ 공급 TR 이 **최근 30 거래일**만 준다. 조회 시작일 파라미터가 없어 그보다 과거는 복구 불가다.
--    ⇒ 이 테이블은 «놓치면 영영 못 채우는» 종류다. 적재를 거르지 말 것.
--
-- 단위: `*_qty`/`*_vol` = 주 · `*_tr_pbmn` = **백만원** (KIS 원문 그대로 보존)
-- 날짜 규약: `foreign_flow` 와 맞춰 DATE 타입. (`daily_prices.date` 는 text 'YYYY-MM-DD',
--            `minute_candles.date` 는 text 'YYYYMMDD' — 조인 시 형변환 필요)

CREATE TABLE IF NOT EXISTS investor_trend_daily (
    stock_code          VARCHAR   NOT NULL,
    date                DATE      NOT NULL,
    close               BIGINT,              -- stck_clpr
    prdy_vrss           BIGINT,              -- 전일 대비

    prsn_ntby_qty       BIGINT,              -- 개인 순매수 수량
    frgn_ntby_qty       BIGINT,              -- 외국인 순매수 수량
    orgn_ntby_qty       BIGINT,              -- 기관계 순매수 수량
    prsn_ntby_tr_pbmn   BIGINT,              -- 개인 순매수 금액(백만원)
    frgn_ntby_tr_pbmn   BIGINT,
    orgn_ntby_tr_pbmn   BIGINT,

    prsn_shnu_vol       BIGINT,              -- 개인 매수 수량
    frgn_shnu_vol       BIGINT,
    orgn_shnu_vol       BIGINT,
    prsn_seln_vol       BIGINT,              -- 개인 매도 수량
    frgn_seln_vol       BIGINT,
    orgn_seln_vol       BIGINT,

    source              VARCHAR   DEFAULT 'kis_FHKST01010900',
    created_at          TIMESTAMP DEFAULT now(),
    PRIMARY KEY (stock_code, date)
);

CREATE INDEX IF NOT EXISTS ix_investor_trend_daily_date ON investor_trend_daily (date);
