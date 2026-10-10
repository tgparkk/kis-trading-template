-- 실행(사장님 확인 뒤 1회 · Task 10): psql -h 127.0.0.1 -p 5433 -U postgres -d kis_template -f ddl.sql
-- 비밀번호는 실행 중 \prompt 로 받는다 = config/key.ini [DTFLOW_SHADOW] db_password 값.
-- 규약: retention 없음 · DROP 없음 · IF NOT EXISTS 없음(이미 있으면 멈춘다).
\set ON_ERROR_STOP on
\if :{?dtflow_pw}
\else
\prompt 'dtflow_shadow_writer password (key.ini [DTFLOW_SHADOW] db_password): ' dtflow_pw
\endif
CREATE ROLE dtflow_shadow_writer LOGIN PASSWORD :'dtflow_pw';
CREATE SCHEMA dtflow_shadow AUTHORIZATION dtflow_shadow_writer;
REVOKE ALL ON SCHEMA dtflow_shadow FROM PUBLIC;
GRANT CONNECT ON DATABASE kis_template TO dtflow_shadow_writer;
GRANT USAGE ON SCHEMA public TO dtflow_shadow_writer;
GRANT SELECT ON public.daily_prices, public.stock_info, public.screener_snapshots TO dtflow_shadow_writer;
SET ROLE dtflow_shadow_writer;
CREATE TABLE dtflow_shadow.trial_candidates (rule_v text, scan_date date, stock_code text, rank int, score double precision,
  run_at timestamptz, f1_orgn double precision, f2_prog double precision, f3_short double precision, f4_credit double precision,
  credit_deal_date text, credit_lag int, has_investor boolean, has_program boolean, has_short boolean, has_credit boolean,
  x_frgn double precision, x_prsn double precision, x_orgn5 double precision, x_loan_gvrt double precision,
  x_ssts_amt_rlim double precision, acml_tr_pbmn double precision, late boolean, code_sha text NOT NULL, row_sha text NOT NULL,
  PRIMARY KEY (rule_v, scan_date, stock_code));
CREATE TABLE dtflow_shadow.trial_raw (rule_v text, scan_date date, stock_code text, kind text, vintage smallint,
  fetched_at text, rt_cd text, msg_cd text, body jsonb, body_sha256 text NOT NULL,
  PRIMARY KEY (rule_v, scan_date, stock_code, kind, vintage));
CREATE TABLE dtflow_shadow.trial_run (rule_v text, scan_date date, run_kind text, run_at timestamptz, status text NOT NULL,
  n_cands int, n_calls int, n_fail int, avail_investor double precision, avail_program double precision,
  avail_short double precision, avail_credit double precision, snapshot_match boolean, snapshot_n int, mine_n int,
  max_score_diff double precision, universe_date text, d_rows int, dprev_rows int, rows_sha256 text, duration_ms int,
  code_sha text NOT NULL, error_text text, PRIMARY KEY (rule_v, scan_date, run_kind, run_at));
CREATE TABLE dtflow_shadow.candidates (LIKE dtflow_shadow.trial_candidates INCLUDING ALL);
CREATE TABLE dtflow_shadow.raw (LIKE dtflow_shadow.trial_raw INCLUDING ALL);
CREATE TABLE dtflow_shadow.run (LIKE dtflow_shadow.trial_run INCLUDING ALL);
RESET ROLE;
GRANT USAGE ON SCHEMA dtflow_shadow TO robotrader;
GRANT SELECT ON ALL TABLES IN SCHEMA dtflow_shadow TO robotrader;
