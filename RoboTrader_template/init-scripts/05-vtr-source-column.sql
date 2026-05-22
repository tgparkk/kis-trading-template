-- virtual_trading_records: 출처(프로젝트) 구분용 source 컬럼 추가
-- 적용 명령(사장님 권한):
--   psql -h 127.0.0.1 -p 5433 -U robotrader -d robotrader -f init-scripts/05-vtr-source-column.sql
--
-- 배경: robotrader DB의 virtual_trading_records 테이블을 두 프로젝트가 공유함
--   - kis-trading-template (이 프로젝트) → source='kis_template'
--   - D:/GIT/RoboTrader (형제 프로젝트, macd_cross_alt 등) → source='robotrader'
--   출처 구분 컬럼이 없어 손익 집계가 상호 오염됨 → source 컬럼으로 분리.
--
-- 주의: nullable + DEFAULT NULL 유지 (NOT NULL 금지).
--   RoboTrader의 기존 INSERT(컬럼 미지정)가 깨지면 안 됨.

-- 1단계: 컬럼 추가 (nullable, DEFAULT NULL)
ALTER TABLE virtual_trading_records
    ADD COLUMN IF NOT EXISTS source VARCHAR(50);

COMMENT ON COLUMN virtual_trading_records.source IS
    '레코드 출처 프로젝트 구분. ''kis_template''=kis-trading-template, ''robotrader''=RoboTrader 형제 프로젝트. NULL=분류 불가/미태깅. nullable 유지(타 프로젝트 INSERT 호환).';

-- source 기준 필터 조회 가속용 인덱스
CREATE INDEX IF NOT EXISTS idx_virtual_trading_source
    ON virtual_trading_records(source);

-- 2단계: 기존 레코드 backfill (1회성 UPDATE, 멱등 — 재실행 무해)
--   블랙리스트 방식: RoboTrader 형제 프로젝트 전략만 'robotrader'로 태깅하고,
--   나머지 전부(분류 불가 포함)는 'kis_template'로 태깅한다.
--   화이트리스트 방식이면 미등록 kis-template 전략(gate_shadow / 눌림목캔들패턴 /
--   퀀트리밸런싱 / Manual cleanup 등)이 NULL로 남는 누락이 발생하므로 블랙리스트로 정정.
--   2026-05-22 실제 DB 적용 결과: source NULL 0건 (772 kis_template / 5 robotrader,
--   robotrader는 macd_cross_alt 전략).
--
-- 실제 strategy 값을 먼저 확인하려면:
--   SELECT DISTINCT strategy FROM virtual_trading_records;
-- robotrader 출처로 분류해야 할 전략이 추가되면 아래 IN 목록에 더한다.

-- RoboTrader 형제 프로젝트 전략 → 'robotrader' (블랙리스트)
UPDATE virtual_trading_records
SET source = 'robotrader'
WHERE strategy IN (
      'macd_cross_alt'
  )
  AND (source IS DISTINCT FROM 'robotrader');

-- 그 외 전부 → 'kis_template' (분류 불가/미태깅 포함)
UPDATE virtual_trading_records
SET source = 'kis_template'
WHERE strategy IS DISTINCT FROM 'macd_cross_alt'
  AND (source IS DISTINCT FROM 'kis_template');

-- 결과: source NULL 0건. 재실행 시 IS DISTINCT FROM 가드로 0건 업데이트(멱등).

-- 3단계: strategy 표기 통일 backfill (1회성 UPDATE, 2026-05-22 적용 완료)
--   kis-template은 전략 컬럼을 클래스명으로 통일. 옛 설정명 'sample' → 'SampleStrategy'.
--   lynch / bb_reversion 전략 레코드는 테이블에 없으므로 별도 통일 불필요.
--   macd_cross_alt(robotrader) 등 타 출처 레코드는 절대 변경 금지.
-- 영향 행 수: 49건 (SELL 49, BUY 0 — 이미 'SampleStrategy' 사용 중이었음)
UPDATE virtual_trading_records
SET strategy = 'SampleStrategy'
WHERE strategy = 'sample'
  AND source = 'kis_template';
-- 이미 적용됨 (2026-05-22). 재실행 시 0건 업데이트로 무해함.
