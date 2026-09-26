-- 연구 ② LLM 전 종목 채점 shadow — 부록 C 🔒 (Q10 승인 뒤 postgres 로 1회 실행)
-- 실행: psql -h 127.0.0.1 -p 5433 -U postgres -d kis_template -f ddl.sql
--       (비밀번호는 실행 중 \prompt 로 받는다 = config/key.ini [LLM_SHADOW] db_password 값 · 문서·git 에 쓰지 않음)
-- 규약: 템플릿 db/repositories/sector_news.py:12 · IF NOT EXISTS · retention 없음 · DROP 없음.
-- 🔒 봉인 열: shadow.output_json · batch.raw_result · rep.* · search.output_json — robotrader 는 집계 뷰만 읽는다(Q10).
\set ON_ERROR_STOP on
\if :{?llm_shadow_pw}
\else
\prompt 'llm_shadow_writer password (key.ini [LLM_SHADOW] db_password): ' llm_shadow_pw
\endif

SELECT 'CREATE ROLE llm_shadow_writer LOGIN PASSWORD ' || quote_literal(:'llm_shadow_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_shadow_writer') \gexec

CREATE SCHEMA IF NOT EXISTS llm_shadow AUTHORIZATION llm_shadow_writer;
REVOKE ALL ON SCHEMA llm_shadow FROM PUBLIC;

-- 쓰기 역할이 읽는 공개 표(§3 입력 · SELECT 만)
GRANT CONNECT ON DATABASE kis_template TO llm_shadow_writer;
GRANT USAGE ON SCHEMA public TO llm_shadow_writer;
GRANT SELECT ON public.daily_prices, public.news, public.news_stock, public.dart_disclosures,
                public.kis_financial_ratio, public.stock_info, public.stock_market, public.screener_snapshots
      TO llm_shadow_writer;

SET ROLE llm_shadow_writer;   -- 표·뷰 소유 = llm_shadow_writer

-- 그날 계획 요약(§5-3 · 순환·늦은 편입·성수기 재계산용 · 모델 출력 없음)
CREATE TABLE IF NOT EXISTS llm_shadow.day_plan (
    family            text        NOT NULL,
    scan_date         date        NOT NULL,
    t_date            date        NOT NULL,
    family_day_idx    integer     NOT NULL,
    u_codes           text[]      NOT NULL,
    u_sha256          text        NOT NULL,
    peak_day          boolean     NOT NULL,
    n_u               integer, n_a_today integer, n_a_carried integer, n_b_due integer,
    n_sel_a           integer, n_sel_b integer, n_skipped_cap integer, n_dropped_carry integer,
    n_a_disc_no_title integer, n_batches integer,
    cand_snapshot     boolean,
    code_sha          text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (family, scan_date)
);

-- 호출 «전» 계획(§5-3)
CREATE TABLE IF NOT EXISTS llm_shadow.plan (
    family          text        NOT NULL,
    scan_date       date        NOT NULL,
    stock_code      varchar(20) NOT NULL,
    trigger         char(1)     NOT NULL,
    slice           smallint    NOT NULL,
    gap_td          integer,
    carried         boolean     NOT NULL,
    cand_strategies text[],
    planned         text        NOT NULL,          -- call | skipped_cap | dropped_carry
    batch_id        text,
    batch_pos       smallint,
    input_text      text,
    input_sha256    text,
    block_sha256    text,
    u_sha256        text        NOT NULL,
    code_sha        text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (family, scan_date, stock_code)
);

-- 본표(§4 · 채점 = status ok)
CREATE TABLE IF NOT EXISTS llm_shadow.shadow (
    family          text        NOT NULL,
    scan_date       date        NOT NULL,
    stock_code      varchar(20) NOT NULL,
    trigger         char(1)     NOT NULL,
    slice           smallint,
    gap_td          integer,
    carried         boolean     NOT NULL,
    cand_strategies text[],
    status          text        NOT NULL,
    batch_id        text,
    batch_pos       smallint,
    attempt         smallint,
    input_text      text,
    input_sha256    text,
    block_sha256    text,
    output_json     jsonb,                          -- 🔒 봉인
    model           text,
    cli_version     text,
    exe_sha256      text,
    code_sha        text,
    argv_sha256     text,
    prompt_version  text,
    prompt_sha256   text,
    latency_ms      integer,
    cost_usd        numeric,
    error_text      varchar(300),
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (family, scan_date, stock_code)
);

-- 호출 1회 = 1행(§4 · §5-4 · §5-5)
CREATE TABLE IF NOT EXISTS llm_shadow.batch (
    family              text        NOT NULL,
    scan_date           date        NOT NULL,
    batch_id            text        NOT NULL,
    kind                text        NOT NULL,      -- primary | retry | repeat | overload_retry | search | search_retry
    n_items             smallint,
    stdin_sha256        text,
    argv_sha256         text,
    status              text        NOT NULL,
    is_error            boolean,
    api_error_status    integer,
    error_text          varchar(300),
    limit_error         boolean,
    overload            boolean,
    raw_result          text,                       -- 🔒 봉인
    model               text,
    model_usage_keys    text[],
    cli_version         text,
    exe_sha256          text,
    code_sha            text,
    prompt_version      text,
    prompt_sha256       text,
    latency_ms          integer,
    cost_usd            numeric,
    web_search_requests integer,
    web_fetch_requests  integer,
    permission_denials  integer,
    cell_status         jsonb,                      -- 종목별 status(검증기 값 · 모델 출력 아님)
    n_ok                smallint,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (family, scan_date, batch_id)
);

-- 반복(§5-6) 🔒 봉인 표
CREATE TABLE IF NOT EXISTS llm_shadow.rep (
    family          text        NOT NULL,
    scan_date       date        NOT NULL,
    stock_code      varchar(20) NOT NULL,
    batch_id        text        NOT NULL,
    batch_pos       smallint,
    status          text        NOT NULL,
    input_text      text,
    input_sha256    text,
    block_sha256    text,
    output_json     jsonb,
    model           text,
    cli_version     text,
    exe_sha256      text,
    code_sha        text,
    argv_sha256     text,
    prompt_version  text,
    prompt_sha256   text,
    latency_ms      integer,
    cost_usd        numeric,
    error_text      varchar(300),
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (family, scan_date, stock_code)
);

-- 검색 팔(§5-9) 🔒 봉인 표(허용 = v_search_daily)
CREATE TABLE IF NOT EXISTS llm_shadow.search (
    family              text        NOT NULL,
    scan_date           date        NOT NULL,
    stock_code          varchar(20) NOT NULL,
    main_family         text,
    sample_order        smallint,
    attempt             smallint,
    status              text        NOT NULL,
    input_text          text,
    input_sha256        text,
    block_sha256        text,
    output_json         jsonb,
    n_sources           integer,
    n_excluded          integer,
    web_search_requests integer,
    web_fetch_requests  integer,
    permission_denials  integer,
    helper_models       text,                       -- modelUsage 중 가족 모델 아닌 키(콤마 조인 · 개정 3)
    model               text,
    cli_version         text,
    exe_sha256          text,
    code_sha            text,
    argv_sha256         text,
    prompt_version      text,
    prompt_sha256       text,
    latency_ms          integer,
    cost_usd            numeric,
    error_text          varchar(300),
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (family, scan_date, stock_code)
);

-- 검색 팔 (ㄱ)(ㄷ) 일일 집계(허용 · §5-9 · §13-1)
CREATE TABLE IF NOT EXISTS llm_shadow.search_daily_agg (
    family              text        NOT NULL,
    scan_date           date        NOT NULL,
    judged_on           date        NOT NULL,
    n_rows              integer, n_ok integer,
    n_sources_le_d      integer, n_disc_sources integer, n_press_sources integer,
    n_missing_disc      integer, n_missing_press integer, n_db_unlinked integer,
    n_excluded_after_d  integer, n_rule_violation integer,
    code_sha            text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (family, scan_date)
);

-- 부록 C 뷰 3개(그대로)
CREATE OR REPLACE VIEW llm_shadow.v_daily_counts AS
  SELECT family, scan_date, trigger, status, carried, count(*) AS n, avg(latency_ms) AS latency_ms
  FROM llm_shadow.shadow GROUP BY 1,2,3,4,5;                         -- 점수·태그·입력·출력 열 없음
CREATE OR REPLACE VIEW llm_shadow.v_batch_health AS
  SELECT family, scan_date, kind, count(*) AS calls, sum((is_error)::int) AS errors,
         count(*) FILTER (WHERE api_error_status IN (429, 529)) AS overload, sum(cost_usd) AS cost_usd
  FROM llm_shadow.batch GROUP BY 1,2,3;
CREATE OR REPLACE VIEW llm_shadow.v_search_daily AS                -- (ㄱ)(ㄷ) 만 · (ㄴ) 는 개봉-1 스크립트가 계산
  SELECT scan_date, n_sources_le_d, n_missing_disc, n_missing_press, n_db_unlinked, n_excluded_after_d, n_rule_violation
  FROM llm_shadow.search_daily_agg;

RESET ROLE;

REVOKE ALL ON ALL TABLES IN SCHEMA llm_shadow FROM PUBLIC;
GRANT USAGE ON SCHEMA llm_shadow TO robotrader;
GRANT SELECT ON llm_shadow.v_daily_counts, llm_shadow.v_batch_health, llm_shadow.v_search_daily TO robotrader;

-- 개정(2026-09-26 amendment prereg_..._amendment_2026-09-26.md 개정 3) — 이 DDL 은 이미 1회 실행됐다.
-- 관리자는 아래 ALTER 블록만 다시 실행할 것(postgres 로 접속 · IF NOT EXISTS 로 멱등 · CREATE TABLE 은 재실행 불필요).
ALTER TABLE llm_shadow.search ADD COLUMN IF NOT EXISTS helper_models text;
