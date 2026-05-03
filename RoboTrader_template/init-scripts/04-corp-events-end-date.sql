-- corp_events: 관리종목/투자경고 해제일 추적용 end_date 컬럼 추가
-- 적용 명령: psql -h 127.0.0.1 -p 5433 -U robotrader -d robotrader -f init-scripts/04-corp-events-end-date.sql
-- end_date IS NULL → 영구 또는 미해제, end_date > as_of_date → 아직 유효
ALTER TABLE corp_events ADD COLUMN IF NOT EXISTS end_date DATE NULL;
COMMENT ON COLUMN corp_events.end_date IS '해제일(NULL이면 미해제 또는 영구). filter_universe가 end_date IS NULL OR end_date > as_of_date 기준으로 필터';
