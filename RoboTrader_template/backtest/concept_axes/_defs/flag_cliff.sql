-- 🔒 제안 · 사장님 확인 전 «미동결» — 값을 보기 «전»에 서명한다
-- 권리락 «가짜 꼬리» 탐지 = flag_cliff  (데이터 주도 단일봉 절벽 탐지)
-- 정본 정의 = docs/prereg_2026-09-14_fund_distress_warning.md §3-4-b 규약 1-b
--   재현기 설계서 §8-10-b 와 FD1 §3-4-b 는 «이 파일 하나»를 인용한다 (한쪽만 고치지 않는다)
-- 🔴 이 파일은 «결과를 보기 전»에 동결돼야 하며, 꼬리 값을 본 뒤 문턱을 바꾸는 것은 FD1 §10 금지 17 이다.
--
-- 세 문턱의 근거 한 문장:
--   기계적 권리락은 «갭이 하락을 지배하고 거래량이 늘지 않는다»,
--   실제 급락은 «장중에 만들어지고 거래량이 급증한다» — 세 조건은 그 둘을 가르기 위한 것이다.
--     · close_t/close_{t-1} - 1 <= -18%   ... 1:1 무상증자(-50%)·액면분할·유상증자 권리락(-5~-20%) 을 덮되
--                                              일반 하한가(-30%) 부근 급락과 겹치는 구간은 아래 두 조건이 가른다
--     · |open_t/close_{t-1} - 1| >= 당일 총 하락의 80%   ... 하락이 «갭»에서 나왔다 (장중 형성이 아니다)
--     · volume_t <= 2.0 x mean(volume_{t-20..t-1})       ... 거래량이 «안 늘었다» (패닉 매도가 아니다)
--
-- ⚠️ volume 은 읽기 계층에서 이미 adj_factor 가 적용된다(CLAUDE.md) — 여기서 다시 곱하지 않는다.
-- ⚠️ 가격(open/close)에는 adj_factor 를 곱하지 않는다(가짜 절벽).

WITH px AS (
  SELECT stock_code, date::date AS d, open, close,
         volume * COALESCE(adj_factor, 1) AS vol_adj,
         LAG(close) OVER (PARTITION BY stock_code ORDER BY date::date) AS prev_close,
         AVG(volume * COALESCE(adj_factor, 1)) OVER (
           PARTITION BY stock_code ORDER BY date::date
           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING)                  AS vol_ma20_prior,
         COUNT(*) OVER (
           PARTITION BY stock_code ORDER BY date::date
           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING)                  AS n_prior
  FROM daily_prices
  WHERE stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')
)
SELECT stock_code, d,
       close/prev_close - 1              AS ret_close,
       open /prev_close - 1              AS gap,
       vol_adj / NULLIF(vol_ma20_prior,0) AS vol_ratio,
       TRUE                               AS flag_cliff
FROM px
WHERE prev_close IS NOT NULL AND prev_close > 0
  AND n_prior = 20                                            -- 직전 20봉이 «다» 있을 때만 판정 (그 밖은 「모른다」)
  AND close/prev_close - 1 <= -0.18                           -- (1) 절벽 크기
  AND ABS(open/prev_close - 1) >= 0.80 * ABS(close/prev_close - 1)  -- (2) 갭 성분이 하락을 지배
  AND vol_adj <= 2.0 * NULLIF(vol_ma20_prior, 0);             -- (3) 거래량 무증가

-- 🔴 동반 인쇄 의무 (FD1 §3-4-b 규약 2·3 · G12):
--   · flag_cliff 행 수를 군별(플래그/비플래그/모름)·연도별로 인쇄
--   · corp_events 조인 히트(flag_corp_action)와의 «교집합·차집합»을 인쇄
--   · 절벽 «포함» 판과 «제외» 판의 delta 를 둘 다 인쇄 (하나만 적으면 무효)
--   · n_prior < 20 이라 판정하지 못한 종목-일 수도 따로 인쇄 («없다»와 «모른다»를 가른다)
