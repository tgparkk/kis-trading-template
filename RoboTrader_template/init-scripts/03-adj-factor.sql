-- Phase 1: daily_prices에 adj_factor 컬럼 추가
-- 적용 명령(사장님 권한):
--   psql -h 127.0.0.1 -p 5433 -U robotrader -d robotrader -f init-scripts/03-adj-factor.sql
--
-- adj_factor: 수정주가 배수 (액면분할/유상증자/배당락 보정)
--   DEFAULT 1.0 = 분할/권리 없음 (기존 행 소급 적용)
--   PIT reader가 as_of_date 시점 기준 과거 시계열 일괄 보정에 사용

ALTER TABLE daily_prices
    ADD COLUMN IF NOT EXISTS adj_factor NUMERIC DEFAULT 1.0;

-- 기존 NULL 행 보정 (ADD COLUMN 후 NULL이 들어간 경우 대비)
UPDATE daily_prices
SET adj_factor = 1.0
WHERE adj_factor IS NULL;

-- NOT NULL 제약 추가 (DEFAULT 1.0 보장 후)
ALTER TABLE daily_prices
    ALTER COLUMN adj_factor SET NOT NULL,
    ALTER COLUMN adj_factor SET DEFAULT 1.0;

COMMENT ON COLUMN daily_prices.adj_factor IS
    '수정주가 배수 — 액면분할/유상증자/배당락 반영. PIT reader가 과거 OHLCV 보정에 사용. DEFAULT 1.0';

-- ============================================================
-- robotrader_quant DB 접근 권한 부여
-- 적용 명령(postgres 슈퍼유저):
--   psql -h 127.0.0.1 -p 5433 -U postgres -d robotrader_quant -f init-scripts/03-adj-factor.sql
-- ============================================================
-- 아래 두 줄은 robotrader_quant DB에 연결된 상태에서만 유효합니다.
-- psql로 직접 적용 시: \c robotrader_quant 후 아래 GRANT 실행
-- GRANT SELECT ON quant_financial_ratio TO robotrader;
-- GRANT SELECT ON quant_balance_sheet    TO robotrader;
-- GRANT SELECT ON quant_income_statement TO robotrader;
