-- 섹터 뉴스 재정렬 기록 (스펙 B §3.3, 2026-09-06 승인)
--
-- 왜 필요한가: 09:00 후보 로드 때 섹터 뉴스 점수로 «움직였을» 순위를 매일 기록한다.
--   shadow 기간(≥20거래일)의 이 표가 live 전환 판단(§8)의 원천이다.
-- SSOT 는 db/repositories/sector_news.py::RERANK_LOG_DDL (ensure_table 이 기동 시 실행). 이 파일은 기록용.
-- reason: 'ok' | 'no_score_rows' | 'stale' | 'fn_missing' | 'table_missing' | 'excluded_strategy' | 'error:<종류>'
--         ok 가 아니면 new_rank = orig_rank · sector_score NULL 로 «그래도 행을 쓴다».

CREATE TABLE IF NOT EXISTS sector_news_rerank_log (
    trade_date    date        NOT NULL,
    strategy      text        NOT NULL,
    stock_code    varchar(20) NOT NULL,
    sector_key    text,                   -- NULL = 섹터 미상
    sector_score  double precision,       -- sector_news_score.score_signed 원값
    orig_rank     integer     NOT NULL,   -- screener_snapshots 순위 (1-based)
    new_rank      integer     NOT NULL,   -- 재정렬 후 순위 (shadow 에서도 «됐을» 순위)
    applied       boolean     NOT NULL,   -- live 에서 실제 적용됐으면 true
    mode          text        NOT NULL,   -- 'shadow' | 'live'
    reason        text        NOT NULL,
    score_asof    timestamp,              -- 읽은 sector_news_score.computed_at (max)
    created_at    timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, strategy, stock_code)
);
