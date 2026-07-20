-- =====================================================================
-- dedup_minute_candles.sql  —  minute_candles 중복 봉 정리 (Part 2/3)
-- =====================================================================
-- 목적: 봉의 진짜 자연키 (stock_code, datetime) 기준 중복 행을 제거한다.
--   기존 PK 는 (stock_code, trade_date, idx) 인데 trade_date=수집일, idx=fetch
--   순번이라 같은 봉이 다른 trade_date/idx 로 재수집되면 중복 적재됐다.
--   (배경: risk-2026-07-10-minute-candles-duplicate-bars)
--
-- ★ 이 스크립트는 배포 런북의 STEP 2 다 — 반드시 Part 3(UNIQUE 인덱스 생성)
--   보다 **먼저** 실행한다. UNIQUE(stock_code,datetime) 인덱스는 중복이 남아
--   있으면 생성 자체가 실패하기 때문이다.
--
-- ★ 실행 전 필수: 수집기(collector)를 STOP 한 유지보수 창에서만 실행.
--   (loser 는 PK 로 키잉하므로 ctid 이동엔 영향받지 않지만, 실행 중이면 신규
--    봉이 끼어들어 검증 카운트가 흔들리고 정리 후 즉시 재중복될 수 있다.)
--
-- 적용 명령(사장님 권한 — kis_template DATABASE 에 접속):
--   psql -h 127.0.0.1 -p 5433 -U robotrader -d kis_template \
--        -f scripts/kis_db/dedup_minute_candles.sql
--   ⚠️ 테이블은 kis_template DB 의 public 스키마에 있다. `kis_template.` 스키마
--      접두사를 붙이지 말 것(그런 스키마는 없다 — "kis_template" 은 DB 이름).
--
-- 무손실성: 삭제 대상(loser)은 지우기 전에 minute_candles_dupes 로 전량 보존한다
--   (어느 행이 "참"인지 미판정이므로 a-priori 무손실). tie-break 은 read_minute
--   band-aid(pit_reader.py `DISTINCT ON (datetime) ORDER BY trade_date ASC, idx ASC`)
--   와 **동일 규칙** — trade_date ASC, idx ASC 로 가장 먼저 수집된 행을 keeper 로 남긴다.
--
-- 재측정된 현재 중복 규모(2026-07-20, 이 스크립트 작성 시점 kis_template read-only 실측):
--   중복 키 수 (stock_code, datetime, count>1) = 8,806
--   삭제 대상(loser) 행 수                     = 8,806
--   → 키당 정확히 1개 loser(각 dup 키가 2행). MEMORY 기록치 8,806 과 일치.
--   (스크립트는 아래에서 라이브로 재계산하므로 이 주석은 참고용. 실행 시점의
--    실제 loser 수는 STEP D 검증 SELECT 로 확인한다.)
--
-- 롤백 레시피:
--   · COMMIT 전(트랜잭션 미종료): 그냥 `ROLLBACK;` — 아무것도 바뀌지 않는다.
--   · COMMIT 후 되돌리기: 보존본에서 원복 —
--       INSERT INTO minute_candles
--         SELECT * FROM minute_candles_dupes
--         ON CONFLICT DO NOTHING;   -- (기존 PK 기준. UNIQUE 인덱스 생성 전이라면 무해)
--     그 뒤 필요시 minute_candles_dupes 를 비운다.
-- =====================================================================

BEGIN;

-- STEP A — 보존 테이블 준비(스키마 완전 복제: 컬럼/타입/기본값/제약/인덱스).
CREATE TABLE IF NOT EXISTS minute_candles_dupes (LIKE minute_candles INCLUDING ALL);

-- 안전장치: 이전 실행 잔재가 있으면 이번 이동분과 섞여 "이동==삭제" 검증이
-- 흐트러진다. 비어있음을 먼저 확인(0 이 아니면 멈추고 사람이 판단).
DO $$
DECLARE n bigint;
BEGIN
    SELECT count(*) INTO n FROM minute_candles_dupes;
    IF n <> 0 THEN
        RAISE EXCEPTION 'minute_candles_dupes 가 비어있지 않음(% 행). 이전 백업을 먼저 처리/보관 후 재실행하라.', n;
    END IF;
END $$;

-- STEP B — loser 행의 **PK (stock_code, trade_date, idx)** 를 확정.
--   ctid 가 아니라 PK 로 키잉한다 — ctid 는 autovacuum/튜플 재배치로 이동해 삭제
--   대상이 어긋날 수 있으나, 옛 PK 는 loser 행마다 UNIQUE 라 정확·안정하다.
--   keeper = 파티션(stock_code, datetime) 내 trade_date ASC, idx ASC 첫 행(rn=1).
--   loser  = 그 외(rn>1).  datetime IS NULL 행은 자연키가 없어 대상에서 제외
--            (UNIQUE(stock_code,datetime)는 NULL 을 서로 distinct 로 취급하므로
--             인덱스 생성을 막지 않는다).
CREATE TEMP TABLE _mc_losers ON COMMIT DROP AS
SELECT stock_code, trade_date, idx FROM (
    SELECT stock_code, trade_date, idx,
           row_number() OVER (
               PARTITION BY stock_code, datetime
               ORDER BY trade_date ASC, idx ASC
           ) AS rn
    FROM minute_candles
    WHERE datetime IS NOT NULL
) ranked
WHERE rn > 1;

-- STEP C — 삭제 전 전량 보존(PK 조인).
INSERT INTO minute_candles_dupes
SELECT mc.*
FROM minute_candles mc
JOIN _mc_losers l
  ON mc.stock_code = l.stock_code
 AND mc.trade_date = l.trade_date
 AND mc.idx        = l.idx;

-- STEP D — 정확히 그 loser 행만 삭제(PK 매칭).
DELETE FROM minute_candles mc
USING _mc_losers l
WHERE mc.stock_code = l.stock_code
  AND mc.trade_date = l.trade_date
  AND mc.idx        = l.idx;

-- =====================================================================
-- 검증 (COMMIT 전에 결과를 눈으로 확인할 것)
-- =====================================================================
-- (1) 보존 행수 == 삭제 대상 행수 (무손실 확인). 두 값이 같아야 한다.
SELECT
    (SELECT count(*) FROM _mc_losers)          AS losers_identified,
    (SELECT count(*) FROM minute_candles_dupes) AS backup_rows;
-- 기대: losers_identified == backup_rows (그리고 == 아래 STEP D 삭제행수).

-- (2) 정리 후 (stock_code, datetime) 기준 중복 키 수 == 0 이어야 한다.
SELECT count(*) AS remaining_dup_keys
FROM (
    SELECT 1
    FROM minute_candles
    WHERE datetime IS NOT NULL
    GROUP BY stock_code, datetime
    HAVING count(*) > 1
) d;
-- 기대: remaining_dup_keys = 0  → 이 값이 0 이어야 Part 3(UNIQUE 인덱스)가 성공한다.

-- (3) (선택) 남은 NULL-datetime 행 수 — 참고용(정리 대상 아님).
SELECT count(*) AS null_datetime_rows
FROM minute_candles WHERE datetime IS NULL;

-- =====================================================================
-- 위 (1) 두 값이 일치하고 (2) 가 0 임을 확인한 뒤에만 커밋할 것.
-- COMMIT;   -- ← 운영자가 검증 후 주석 해제하여 실행 (미확인 시 ROLLBACK;)
-- =====================================================================
