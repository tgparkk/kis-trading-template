-- ✅ 결정됨 2026-09-15(사장님 · 권고안 채택) — 동결은 critic 재확인(D-16~D-18) 후
--   근거 = memory/decision-2026-09-15-flag-cliff-and-baseline-beta.md 1 — 값을 보기 «전»에 서명했다
-- 권리락 «가짜 꼬리» 탐지 = flag_cliff  (데이터 주도 단일봉 절벽 탐지)
-- 정본 정의 = docs/prereg_2026-09-14_fund_distress_warning.md §3-4-b 규약 1-b (v0.6 · D-20 ✅ 결정됨)
--   재현기 설계서 §8-10-b 와 FD1 §3-4-b 는 «이 파일 하나»를 인용한다 (한쪽만 고치지 않는다)
-- 🔴 이 SQL 골격은 «결정 시점(2026-09-15)까지 꼬리 값을 보지 않고» 정했다. 꼬리 값을 본 뒤 문턱을 바꾸는 것은 FD1 §10 금지 17 이다.
--
-- 세 문턱의 근거 한 문장:
--   기계적 권리락은 «갭이 하락을 지배하고 거래량이 늘지 않는다»,
--   실제 급락은 «장중에 만들어지고 거래량이 급증한다» — 세 조건은 그 둘을 가르기 위한 것이다.
--     · close_t/close_{t-1} - 1 <= -18%   ... 1:1 무상증자(-50%)·액면분할·유상증자 권리락(-5~-20%) 을 덮되
--                                              일반 하한가(-30%) 부근 급락과 겹치는 구간은 아래 두 조건이 가른다
--     · open_t/close_{t-1} - 1 <= 0.80 x (close_t/close_{t-1} - 1)
--                                         ... 하락이 «갭»에서 나왔다 (장중 형성이 아니다 · 양변 음수)
--     · volume_t <= 2.0 x mean(volume_{t-20..t-1})       ... 거래량이 «안 늘었다» (패닉 매도가 아니다)
--
-- ✅ 결정됨 2026-09-15(사장님 · ② 세 조건 + 부호 정정 승인 · 문턱 불변)  (critic 재확인 C2 MAJOR)
--   구안 `ABS(open/prev-1) >= 0.80 * ABS(close/prev-1)` 은 «상방» 갭도 통과시켰다 —
--   시가 +15% 로 갭업했다가 종가 -18% 로 밀린 날이 |0.15| >= 0.8*|0.18| = 0.144 로 성립한다.
--   그건 산문 「당일 하락의 80% 이상이 «갭»에서 나왔다」와 «반대» 방향(장중 형성)이다.
--   ⇒ 조건 (1) 이 이미 close/prev-1 <= -0.18 < 0 을 보장하므로 «부호 있는» 부등식으로 고친다.
--     양변이 음수이고, 문턱값 0.80 과 -18%·2.0x 는 «한 글자도» 바뀌지 않았다.
--
-- 🔒 2026-09-15 volume 조정 정정 · 이 파일에 한함  (critic 재확인 C8)
--   CLAUDE.md 의 「volume 은 읽기 계층에서 이미 adj_factor 가 적용된다」는 resolver 경유 읽기의 말이다.
--   이 SQL 은 «원시 daily_prices 직접 조회»라 읽기 계층 «밖»이다 ⇒ 여기서는 volume 에
--   COALESCE(adj_factor,1) 을 «곱한다». (이중조정이 아니라 미조정을 메우는 것이다.)
-- ⚠️ 가격(open/close)에는 adj_factor 를 곱하지 않는다(가짜 절벽).
--
-- 🔒 2026-09-15 adj 불변 가드 신설  (critic 재확인 C1 CRITICAL · 새 문턱이 아니다)
--   「adj_factor 는 종목당 단일 값이라 날짜별 조정이 불가능하다」는 전제가 실측으로 «반증»됐다 —
--   daily_prices 비-1 다치 종목 116 · 판정 창(2025-01-01~2026-05-31) |Δadj|>0.001 계단 49건(48종목) ·
--   001080 은 2026-03-09 에 adj 10 -> 1 · 011090·014990·226340 은 «행별» 값(각각 411·1,055·401 고유값).
--   ⇒ 창 안에서 adj 가 «변한» 종목-일은 「없다」가 아니라 「모른다」로 빼고 그 건수를 인쇄한다
--     (n_prior < 20 과 «같은» 처리 · 판정 문턱을 바꾸는 조항이 아니다).
--   🔑 PostgreSQL 은 COUNT(DISTINCT ...) OVER 를 지원하지 않는다 ⇒ 규약과 «같은 뜻»인
--     MIN(COALESCE(adj_factor,1)) OVER w21 = MAX(COALESCE(adj_factor,1)) OVER w21 로 쓴다
--     (창 = ROWS BETWEEN 20 PRECEDING AND CURRENT ROW = 거래량 20봉 창 + 당일).

WITH px AS (
  SELECT stock_code, date::date AS d, open, close,
         volume * COALESCE(adj_factor, 1)                    AS vol_adj,
         LAG(close) OVER w                                   AS prev_close,
         AVG(volume * COALESCE(adj_factor, 1)) OVER w20      AS vol_ma20_prior,
         COUNT(*) OVER w20                                   AS n_prior,
         MIN(COALESCE(adj_factor, 1)) OVER w21               AS adj_min_21,
         MAX(COALESCE(adj_factor, 1)) OVER w21               AS adj_max_21
  FROM daily_prices
  WHERE stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')
  WINDOW w   AS (PARTITION BY stock_code ORDER BY date::date),
         w20 AS (PARTITION BY stock_code ORDER BY date::date
                 ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING),
         w21 AS (PARTITION BY stock_code ORDER BY date::date
                 ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
)
SELECT stock_code, d,
       close/prev_close - 1              AS ret_close,
       open /prev_close - 1              AS gap,
       vol_adj / NULLIF(vol_ma20_prior,0) AS vol_ratio,
       TRUE                               AS flag_cliff
FROM px
WHERE prev_close IS NOT NULL AND prev_close > 0
  AND n_prior = 20                                            -- 직전 20봉이 «다» 있을 때만 판정 (그 밖은 「모른다」)
  AND adj_min_21 = adj_max_21                                 -- 창 안 adj 불변일 때만 판정 (그 밖은 「모른다」 · C1)
  AND close/prev_close - 1 <= -0.18                           -- (1) 절벽 크기
  AND open /prev_close - 1 <= 0.80 * (close/prev_close - 1)   -- (2) 갭 성분이 하락을 지배 (🔒 부호 정정 · 양변 음수)
  AND vol_adj <= 2.0 * NULLIF(vol_ma20_prior, 0);             -- (3) 거래량 무증가

-- 🔴 동반 인쇄 의무 (FD1 §3-4-b 규약 2·3 · G12):
--   · flag_cliff 행 수를 군별(플래그/비플래그/모름)·연도별로 인쇄
--   · corp_events 조인 히트(flag_corp_action)와의 «교집합·차집합»을 인쇄
--   · 절벽 «포함» 판과 «제외» 판의 delta 를 둘 다 인쇄 (하나만 적으면 무효)
--   · n_prior < 20 이라 판정하지 못한 종목-일 수도 따로 인쇄 («없다»와 «모른다»를 가른다)
--   · 🆕 adj_min_21 <> adj_max_21 («창 안 adj 계단») 이라 판정하지 못한 종목-일 수도 따로 인쇄
--        — 같은 자리에 FD1 §3-0-b 유동성 컷·G13 이 요구하는 「adj 계단 종목-일 수」를 적는다
