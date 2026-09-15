-- NW2 §2-2 / §2-2-b 사건 건수 재현기 (수익률 0회 · 건수만)
-- 정본 분류 = backtest/concept_axes/_defs/dart_cls.sql (새 정규식 금지)
-- 최초 실행 2026-09-15 · 리뷰 #9 대응 (critic 비재현 원인 규명)
--
-- 🔑🔑 두 가지를 «반드시» 고정해야 값이 재현된다 (둘 중 하나라도 풀면 값이 흔들린다):
--   (1) 중복제거 LAG 의 정렬을 «결정적»으로 — ORDER BY published_at, id
--       같은 (stock_code, published_at) 동시각 타이가 D6 창 안에만 218그룹/482행 있다.
--       ORDER BY published_at 만 쓰면 타이 순서가 실행마다 달라져 (a) 가 518 ↔ 520 ↔ 522 로 흔들린다.
--       ⇒ critic 의 520/457/352 는 «다른 값»이 아니라 «타이 정렬이 안 묶인 같은 쿼리»다.
--   (2) 거래일 달력을 2026-09-14 지문(rn = 1,397)으로 «고정»
--       달력이 하루 자라면 +20/+60 컷오프가 2026-08-14/06-18 → 2026-08-18/06-19 로 밀린다.
--
-- 실행: psql -d "postgresql://robotrader:1234@127.0.0.1:5433/kis_template" -f 이 파일

\set ON_ERROR_STOP on

\i backtest/concept_axes/_defs/dart_cls.sql

-- 거래일 달력 (의사티커 KOSPI · 2026-09-14 지문으로 고정)
CREATE TEMP VIEW cal AS
SELECT d, row_number() OVER (ORDER BY d) rn
FROM (SELECT DISTINCT date::date d FROM daily_prices
      WHERE stock_code='KOSPI' AND date::date <= DATE '2026-09-14') t;

\echo '=== 0) 달력 지문 (기대: max_rn = 1397 · max_d = 2026-09-14) ==='
SELECT max(rn) AS max_rn, max(d) AS max_d FROM cal;

\echo '=== 1) D6 소분류 x 종목연결 여부 — 원시행 (리뷰 #8: 801 = 761 연결 + 40 미연결) ==='
SELECT CASE WHEN title ~ '발행결정' THEN 'a_발행결정'
            WHEN title ~ '전환청구권행사|신주인수권행사' THEN 'b_행사'
            WHEN title ~ '전환가액|신주인수권행사가액|교환가액' THEN 'c_리픽싱'
            ELSE 'd_기타' END AS sub,
       count(*) FILTER (WHERE stock_code IS NOT NULL) AS linked,
       count(*) FILTER (WHERE stock_code IS NULL)     AS unlinked,
       count(*)                                        AS total
FROM dart_cls
WHERE dtype='D6_CB_BW_EB'
  AND published_at::date BETWEEN DATE '2026-01-01' AND DATE '2026-09-14'
GROUP BY 1 ORDER BY 1;

\echo '=== 2) §2-3 / §2-2 dtype 별 건수·완전창 n (중복제거 후 · pd 컷오프) ==='
WITH raw AS (
  SELECT stock_code, dtype, id, published_at, published_at::date AS ed,
         LAG(published_at::date) OVER (PARTITION BY stock_code,dtype ORDER BY published_at, id) AS prev_ed
  FROM dart_cls
  WHERE stock_code IS NOT NULL
    AND published_at::date BETWEEN DATE '2026-01-01' AND DATE '2026-09-14')
SELECT dtype,
       count(*)                                              AS n_all,
       count(*) FILTER (WHERE ed <= DATE '2026-08-14')       AS n_w20,
       count(*) FILTER (WHERE ed <= DATE '2026-06-18')       AS n_w60
FROM raw WHERE prev_ed IS NULL OR ed-prev_ed > 5
GROUP BY dtype ORDER BY dtype;

\echo '=== 3) §2-2-b (a) — (code, D6) 중복제거 후 발행결정만 · pd 컷오프  [기대 518 / 455 / 352] ==='
WITH raw AS (
  SELECT stock_code, dtype, title, id, published_at, published_at::date AS ed,
         LAG(published_at::date) OVER (PARTITION BY stock_code,dtype ORDER BY published_at, id) AS prev_ed
  FROM dart_cls
  WHERE stock_code IS NOT NULL AND dtype='D6_CB_BW_EB'
    AND published_at::date BETWEEN DATE '2026-01-01' AND DATE '2026-09-14')
SELECT count(*) AS n_all,
       count(*) FILTER (WHERE ed <= DATE '2026-08-14') AS n_w20,
       count(*) FILTER (WHERE ed <= DATE '2026-06-18') AS n_w60
FROM raw WHERE (prev_ed IS NULL OR ed-prev_ed > 5) AND title ~ '발행결정';

\echo '=== 4) §2-2-b (b) — (code, 발행결정) 소분류 단위 중복제거 · pd 컷오프  [기대 558 / 492 / 384] ==='
WITH raw AS (
  SELECT stock_code, title, id, published_at, published_at::date AS ed,
         LAG(published_at::date) OVER (PARTITION BY stock_code ORDER BY published_at, id) AS prev_ed
  FROM dart_cls
  WHERE stock_code IS NOT NULL AND dtype='D6_CB_BW_EB' AND title ~ '발행결정'
    AND published_at::date BETWEEN DATE '2026-01-01' AND DATE '2026-09-14')
SELECT count(*) AS n_all,
       count(*) FILTER (WHERE ed <= DATE '2026-08-14') AS n_w20,
       count(*) FILTER (WHERE ed <= DATE '2026-06-18') AS n_w60
FROM raw WHERE prev_ed IS NULL OR ed-prev_ed > 5;

\echo '=== 5) (a)/(b) 를 τ0 컷오프로 다시 잰 판  [기대 (a) 518/453/350 · (b) 558/490/382] ==='
WITH raw AS (
  SELECT stock_code, dtype, title, id, published_at, published_at::date AS ed,
         (published_at::time >= TIME '15:20') AS ah,
         LAG(published_at::date) OVER (PARTITION BY stock_code,dtype ORDER BY published_at, id) AS prev_ed
  FROM dart_cls
  WHERE stock_code IS NOT NULL AND dtype='D6_CB_BW_EB'
    AND published_at::date BETWEEN DATE '2026-01-01' AND DATE '2026-09-14'),
ded AS (SELECT * FROM raw WHERE (prev_ed IS NULL OR ed-prev_ed > 5) AND title ~ '발행결정'),
ev0 AS (SELECT e.*, (SELECT min(c.rn) FROM cal c
                     WHERE c.d > e.ed OR (c.d = e.ed AND NOT e.ah)) AS rn0 FROM ded e)
SELECT 'a_tau0' AS k, count(*) AS n_all,
       count(*) FILTER (WHERE (SELECT max(rn) FROM cal) - rn0 >= 20) AS n_w20,
       count(*) FILTER (WHERE (SELECT max(rn) FROM cal) - rn0 >= 60) AS n_w60
FROM ev0;

WITH raw AS (
  SELECT stock_code, title, id, published_at, published_at::date AS ed,
         (published_at::time >= TIME '15:20') AS ah,
         LAG(published_at::date) OVER (PARTITION BY stock_code ORDER BY published_at, id) AS prev_ed
  FROM dart_cls
  WHERE stock_code IS NOT NULL AND dtype='D6_CB_BW_EB' AND title ~ '발행결정'
    AND published_at::date BETWEEN DATE '2026-01-01' AND DATE '2026-09-14'),
ded AS (SELECT * FROM raw WHERE prev_ed IS NULL OR ed-prev_ed > 5),
ev0 AS (SELECT e.*, (SELECT min(c.rn) FROM cal c
                     WHERE c.d > e.ed OR (c.d = e.ed AND NOT e.ah)) AS rn0 FROM ded e)
SELECT 'b_tau0' AS k, count(*) AS n_all,
       count(*) FILTER (WHERE (SELECT max(rn) FROM cal) - rn0 >= 20) AS n_w20,
       count(*) FILTER (WHERE (SELECT max(rn) FROM cal) - rn0 >= 60) AS n_w60
FROM ev0;

\echo '=== 6) 타이 규모 — 왜 정렬을 묶어야 하는지의 증거 (D6 창 안) ==='
SELECT count(*) AS tie_groups, sum(c) AS tie_rows FROM (
  SELECT stock_code, published_at, count(*) c FROM dart_cls
  WHERE stock_code IS NOT NULL AND dtype='D6_CB_BW_EB'
    AND published_at::date BETWEEN DATE '2026-01-01' AND DATE '2026-09-14'
  GROUP BY 1,2 HAVING count(*)>1) t;

\echo '=== 7) §2-2 주 표 — τ0 축 완전창 n (v0.4: 주 표의 컷오프 축) ==='
WITH raw AS (
  SELECT stock_code, dtype, id, published_at, published_at::date AS ed,
         (published_at::time >= TIME '15:20') AS ah,
         LAG(published_at::date) OVER (PARTITION BY stock_code,dtype ORDER BY published_at, id) AS prev_ed
  FROM dart_cls
  WHERE stock_code IS NOT NULL
    AND published_at::date BETWEEN DATE '2026-01-01' AND DATE '2026-09-14'),
ded AS (SELECT * FROM raw WHERE prev_ed IS NULL OR ed-prev_ed > 5),
ev0 AS (SELECT e.*, (SELECT min(c.rn) FROM cal c
                     WHERE c.d > e.ed OR (c.d = e.ed AND NOT e.ah)) AS rn0 FROM ded e)
SELECT dtype, count(*) AS n_all,
  count(*) FILTER (WHERE (SELECT max(rn) FROM cal) - rn0 >= 20) AS n_w20_tau0,
  count(*) FILTER (WHERE (SELECT max(rn) FROM cal) - rn0 >= 60) AS n_w60_tau0
FROM ev0
WHERE dtype IN ('D3_유상증자','D5_감자_주식병합','D6_CB_BW_EB','E1_실적잠정')
GROUP BY dtype ORDER BY dtype;
