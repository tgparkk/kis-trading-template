# 사전등록 — 매수후보 특징 연구 (B ④ · candidate feature study)

- 상태: **v0.2 · critic 1패스 반영 · 동결 대기(2026-09-24)** · 브랜치 `research/candidate-ledger` · 기준 `585b651`(원장 PREREG 동결)
- 🔒 이 문서는 **원장 `ledger.csv` 의 결과 열(`exit_*`·`ret_pct`·`pnl_won`)을 누구든 열기 «전»에 커밋으로 동결**한다.
  🔒 표시 절(표본·결과 변수·특징·창·통계량·검정·문턱·판정 규칙·시드)은 **결과를 본 뒤 바꿀 수 없다**.
  바꿔야 하면 개봉 «전»에 `prereg_2026-09-24_candidate_feature_study_amendment_<날짜>.md` 를 따로 커밋한다.
- 작성 중 조회: 코드 grep/부분 read · DB **SELECT 는 스키마·날짜 범위·종목 수만**(§3-4 표). **수익률·청산 결과 조회 0회.**
- 동결 커밋 시점에 원장 결과를 연 사람이 있으면 이름·시각을 이 줄 아래에 적는다(없으면 「없음」).

## 0. 승계한 결정 (사장님 말 그대로)

> 「제가 자금한도를 없애자고 한건 현재 로직으로 산 다음에 나중에 추가 데이터나 수치를 조절해서 매수후보 로직 품질을 높이고 싶은 겁니다」 (2026-09-24)

> 「당분간 3전략 + 태쏘만 고도화 · 재무·뉴스 데이터로 매수후보 선정 보강」 (2026-09-11)

⇒ ① 이 연구의 출력은 **별도 「순위 층 shadow」 사전등록의 «재료»일 뿐**이다. **라이브 3전략 룰 변경 0건(~2026-10-16 · 계획서 v3)** · **배제 층 아님**.
⇒ ② 09-11 결정: 재무·뉴스 = **순위 층**(배제 아님) · 뉴스는 「정보 있나」 측정부터. 09-11 밤 단일 측정(`scratchpad/focus4_20260911/NEWS_signal_measure.md`)
   = **뉴스 순위 층 NO**(커버리지 26~34% · minervini 후보축 +1.89 vs −3.03% 인데 매수축 부호 반대 · daytrading 은 점수 높을수록 나쁨 · 사후 단일 측정).
   ⇒ **뉴스는 커버리지·방향 일치만 재고 순위 특징으로 승격하지 않는다**(§3-3).
⇒ ③ 🔒 **회의론자 조건(결과 전 고정)**: 발굴 프로그램 종결(2026-07-16) — 판별감사 191만 표본 종목선택 **OOS AUC 0.556 천장** · 비-차트 피처 전부 더해도 **+0.001** ·
   「후보(선별) 로직 추가 발굴은 권장하지 않는다」. ⇒ **이 연구의 기본 기대는 「특징이 없다」**이고,
   「특징 있음」이라고 말하려면 §5 문턱을 **확인 창에서** 넘어야 한다. 넘지 못한 특징은 전부 「없음」이다(「경향」「약한 신호」 등 중간 언어 금지).

## 1. 이 문서가 «아닌» 것

- 라이브 변경·shadow 배선이 아니다(코드 0줄 · DB 쓰기 0건). 새 코드 = §9 의 `run_features.py` 하나뿐.
- 원장(A ③-b)을 다시 정의하지 않는다 — 원장 PREREG(`backtest/concept_axes/candidate_ledger/PREREG.md`) §2~§8 을 **그대로 승계**.
- 청산 룰·밴드·사이징 연구가 아니다. 결과 변수는 원장 청산(exitsim8) 결과를 «받아쓰기»만 한다.

## 2. 표본 · 결과 변수 🔒

### 2-1. 입력 (동결된 것 · 원장 PREREG §7)
`results/ledger.csv` 30열 순서 그대로: `strategy, scan_date, stock_code, rank, score, n_passed, reason, n_bars, ref_close, market_cap, trading_value, d_volume, rs_value, excl_class, entry_date, entry_price, band_lo, band_hi, band_ok, qty, qty_basis, notional, exit_date, exit_price, exit_reason, exit_phase, hold_days, ret_pct, pnl_won, flags`
+ `results/scan_diag.csv`(`strategy, scan_date, universe_eff_date, n_universe, n_eligible, n_evaluated, n_impossible, n_no_bar_at_d, n_matched, secs`).
- 착수 조건: 🔒 **이 문서 동결 커밋이 원장 본 실행보다 «먼저»**(§9) · 원장 `summary.md`·V5 는 이 문서 동결 뒤에만 연다 · 분석 착수 = 원장 V1~V5 verifier 통과 뒤.

### 2-2. 분석 표본
| 표본 | 정의 | 역할 |
|---|---|---|
| **전수(주 분석)** | 3전략 × scan_date 2024-03-13~ **전략별 상한**(D+1 거래일 + max_hold 거래일 ≤ 2026-09-23 · ma20 50 · minervini 20 · daytrading 10 · KOSPI 달력) · `entry_price` 있음 ∧ `ret_pct` 있음 ∧ flags 에 `impossible_bar` 없음 | **판정은 여기서만** |
| 라이브 근사 | 전수 ∩ `band_ok=True` | 같은 표 인쇄만(판정 언어 금지) |
| 민감도 | ① 상한 뒤 행(`open` 평가손익 포함) ② `impossible_bar` 포함 | 인쇄만 |
- 빠진 행은 사유별(`no_open`·`no_next_day`·`상한 뒤`·`impossible_bar`) 건수를 전략×창별로 인쇄. `corp_event`·`excl_class`·`vintage_m4` 행은 **남긴다**(라이브도 안 거른다 · 창 간 비대칭 방지) — 건수만 인쇄.
- 상한 안에서도 남는 `exit_reason=open`(`max_hold_deferred` 등) 행은 표본에 두고 건수를 인쇄한다.

### 2-3. 결과 변수
| 이름 | 정의 | 역할 |
|---|---|---|
| **`ret_pct`** | 원장 열 그대로(gross · exitsim8 청산 · %) | **주 결과 — 판정 대상** |
| 적중률 | `ret_pct > 0` 비율 | 보조 · 인쇄만 |
| `r5` · `r10` | `close(entry_date + h 거래일) / entry_price − 1`, h=5·10 · 달력 = `daily_prices` `stock_code='KOSPI'` · 진입일 = 0 · close 는 원시(adj 미적용) · 해당 봉 없으면 결측 · 창 끝을 넘으면 결측 | 보조 · 인쇄만 |
- `ret_pct` 는 전략마다 tp/sl/max_hold 가 다르다 ⇒ **전략을 섞은 원값 평균은 쓰지 않는다**(§4-2 전략 고정효과).

## 3. 특징 🔒

### 3-1. 순위 특징 — Holm 가족 **N = 14**
| # | 특징 | 정의 | 출처 | PIT 보장 | 결측 |
|---|---|---|---|---|---|
| F01 | `rank` | 원장 열 | ledger | D 종가까지로 계산된 순번 | 없음 |
| F02 | `score` | 원장 열(전략마다 뜻이 다름 · 전략 안에서만 분위) | ledger | 〃 | 없음 |
| F03 | `n_passed` | 원장 열(**날짜 단위** 특징 · §4-3 순열 규칙 다름) | ledger | 〃 | 없음 |
| F04 | `rank_frac` | `rank / n_passed` | ledger | 〃 | 없음 |
| F05 | `gap` | `entry_price / ref_close − 1` | ledger | **D+1 09:00 에 알려짐** ⇒ 순위(D) 층이 아닌 **타이밍 층 특징**으로 표기 | 시가 없음 = 표본 밖 |
| F06 | `band_ok` | True vs False (**이진** · 전수에서만 · 라이브 근사 표본에선 상수라 생략) | ledger | 〃(D+1 시가) | 시가 없음 = 표본 밖 |
| F07 | `vol_ratio20` | `d_volume / mean(adj 거래량, D−20…D−1 의 20거래일)` · 거래량 = `loader.load_prices` 의 `volume × COALESCE(adj_factor,1)` | ledger + loader | D−1 까지 평균 · D 봉은 원장 값 | 앞선 봉 < 20 ⇒ 결측 |
| F08 | `market_cap` | 원장 열 | ledger | `universe_eff_date ≤ D` 행 | 없음 |
| F09 | `trading_value` | 원장 열 | ledger | 〃 | 없음 |
| F10 | `rs12w` | `strategies/minervini_volume_dryup/screener.py:97-128 build_context` 를 **3전략 전부**에 호출 · 유니버스 = 그 전략·그날 `scan_diag.n_eligible` 집합(= 그 전략 base_filter 통과 ∧ `date ≤ D` 봉 ≥1 ∧ 불가능봉 가드 통과 · 원장 PREREG §3-4 와 같은 frames 규칙 · 창 260봉) · 내부 = `compute_rs_percentile_12w`(`strategies/books/minervini_vcp/rules.py:29` · `pct_change(60)` 백분위 0~99) | loader + 어댑터 | `date ≤ D` 봉만 | NaN(60봉 미만) ⇒ 결측 · minervini 는 원장 `rs_value` 와 **100% 일치해야**(V-F1) |
| F11 | `fin_distress` | FD1(`docs/prereg_2026-09-14_fund_distress_warning.md`) §1-2 합집합 `D` **그대로**(영업적자 ∨ 적자 2년 ∨ 완전·부분잠식 50%+ ∨ 부채비율 400%+) · 비교 = `D=1` vs `D=0` | `dart_financials_asfiled` | FD1 §1-1 **그대로**: `status='000'` · `rcept_dt ≤ D−1` 인 사업연도 중 가장 최근 y 하나 · 전년 필요 시 `rcept_dt(y−1) ≤ D−1` 따로 | FD1 §1-3 **U1**: 「모름」은 제3계급 · 비교에서 빼고 **건수 따로 인쇄** |
| F12 | `fin_growth` | `g = operating_income(y) / operating_income(y−1) − 1`(연속값 · F1 §1-2 V2 형) · y 선택은 F11 과 같은 PIT | `dart_financials_asfiled`(minervini 트랙 B 배관 = `backtest/concept_axes/minervini/run.py:280` 조회) | 〃 | `operating_income(y−1) ≤ 0` ∨ 어느 해 NULL/안 보임 ⇒ 결측(사유 코드 F1 6종 그대로 인쇄) |
| F13 | `frgn5` | `Σ foreign_net_vol × close(같은 날 원시 종가) / market_cap` · KOSPI 달력 **D−5…D−1 5거래일 «전부»** 의 `foreign_flow` 행 | `foreign_flow` + `daily_prices` | T-1 이 정상(메모리 규약) ⇒ D 값 미사용 | 5일 중 하나라도 없으면 결측 · **부호 분포(>0/=0/<0) 따로 인쇄** |
| F14 | `frgn20` | F13 과 같되 D−20…D−1 20거래일 전부 | 〃 | 〃 | 20일 중 하나라도 없으면 결측 |

- 🔒 F13·F14 `source` 규칙: 같은 `(stock_code, date)` 에 행이 여럿이면 **합산 금지** · `created_at` 가장 이른 행 1개(동률이면 `source` 사전순 첫 행) · 복수 행 건수 인쇄. (관리자 실측 2026-09-24 SELECT: `source` 는 `naver` 단일 · `(stock_code,date)` 중복 0행 ⇒ 규칙은 방어용이며 현재 데이터에서는 발동하지 않는다.)
- F13·F14 는 C 결과를 **E 에서 비결측이던 종목 집합으로 제한한 표**도 인쇄(커버리지 확장 효과 분리 · 판정은 전 C).
- 🔒 F11·F12 정정공시 덮어쓰기: PK `(stock_code, bsns_year)`(`minervini/run.py:275-276`) ⇒ 정정본의 미래 `rcept_dt` 때문에 PIT 선택이 **이전 연도로 후퇴**할 수 있다. 기대 연도(scan_date 가 4-1 이후면 전년, 이전이면 전전년)보다 오래된 y 가 선택된 행 수를 전략×창별로 인쇄.

- 🔒 **N = 14 를 Holm 분모로 고정한다** — 탐색 창에서 후보가 몇 개로 줄든 분모는 14(탈락 특징 p=1 로 취급).
- 알려진 상관(인쇄만): F01~F04 는 서로 강상관 · daytrading `score` ≈ F07(`screener.py:53` 당일/평균 거래량) · minervini F10 은 TT 문턱(≥70) 으로 절단돼 분산이 작다.

### 3-2. 인쇄만 (Holm 가족 밖 · 판정 언어 금지)
| 항목 | 이유 |
|---|---|
| `investor_trend_daily` 개인·외국인·기관 5일 순매수(`*_ntby_qty`·`*_ntby_tr_pbmn`) | **데이터가 2026-07-03~2026-09-21 뿐**(실측) ⇒ 탐색 창 0일 · 확인 창 일부만. 확인 창 안에서 T3−T1 만 인쇄 |
| `read_financial_ratio`(`multiverse/data/pit_reader.py:460`) 의 `sales_growth`·`operating_income_growth` | 🔴 PIT 규약이 「`statement_ym` 월말 ≤ D−60일」(`:475-483`) — 실제 공시일 컬럼이 없다(`:527`). **연간 사업보고서 제출기한 90일 > 60일** ⇒ 12월 결산분이 최대 약 30일 앞서 보일 수 있고, 값은 `fetched_at` 시점 스냅샷(정정 반영 가능). ⇒ 주 성장 특징은 F12(`rcept_dt` 기준)로 두고 이것은 대조 인쇄만 |
| FD1 성분별 (a)~(d) 분해 | FD1 §1-2 「성분 분해는 인쇄만」 승계 |

### 3-3. 뉴스 — 「정보 있나」만 (Holm 가족 밖)
- 조인 🔒: `news_stock.news_id = news.id`(**`news.news_id` text 로 조인 금지 — 오조인**) · 종목 = `news_stock.stock_code`.
- 창: `news.published_at ∈ [D−4 거래일 00:00, D+1 00:00)` = D 포함 5거래일(09-11 측정의 「scan_date 포함」 규약 승계).
- 값: 건수 `n_news` · `overall_score` 평균. **뉴스는 2024-12-23 부터만 있다**(실측) ⇒ 탐색 창은 2024-12-23~2025-06-30 부분만.
- 보고 3가지만: ① 커버리지(`n_news ≥ 1` 비율) 전략×창 ② `ret_pct` 평균(있음 − 없음) ③ 뉴스 있는 행 안 `overall_score` T3−T1.
  「방향 일치」 = ②·③ 각각 3전략 부호 동일 ∧ 두 창 부호 동일 여부(예/아니오)만 적는다. **p 값 계산 안 함 · 순위 특징 후보로 올리지 않는다.**

### 3-4. 제외 (사유)
| 항목 | 사유 |
|---|---|
| 섹터·업종 | `stock_sector_map` 2,795행 **PIT 백데이트 결함**(모든 섹터 분석 공통) |
| 분봉 특징 | `minute_candles` = 거래대금 상위 300 만 · 2025-02-24 이후뿐(원장 §7 `minute_avail`) ⇒ 비무작위 결측 |
| KSIC 테마 | 「대장주」 KSIC 부적합 확정(재시도 금지) |

실측 스키마·범위(SELECT 1회씩): `foreign_flow(stock_code, date, foreign_net_vol, source, created_at)` 2023-02-28~2026-09-09 · 종목 수 2023=149·2024=155·2025=158·2026=627 ·
`investor_trend_daily(stock_code, date, close, prdy_vrss, {prsn,frgn,orgn}_{ntby_qty,ntby_tr_pbmn,shnu_vol,seln_vol}, source, created_at)` 2026-07-03~09-21 · 2,763종목 ·
`dart_financials_asfiled` 2019~2025 · 2,556종목 · `news` 2024-12-23~2026-09-24 · 229,942행 · `quant_financial_ratio` 200402~202603 · 2,485종목.
🔴 **F13·F14 는 2025 년까지 약 150종목만 덮는다** ⇒ 결측이 비무작위(대형주 쏠림 추정) — §7 한계 · 커버리지를 전략×창별로 인쇄.

## 4. 설계 🔒

### 4-1. 창
| 창 | scan_date | 비고 |
|---|---|---|
| **탐색 E** | 2024-03-13 ~ 2025-06-30 | 후보 특징 선정만 |
| **확인 C** | 2025-07-01 ~ 2026-09-23 | 판정 |
- ③-a 가설의 근거 73일(라이브 스냅샷 2026-06-05~09-22)은 **E 와 겹치지 않는다**(E 끝 2025-06-30). 단 **C 와는 겹친다** ⇒ §4-5 참조.
- 청산 경로는 창 경계를 넘을 수 있다(scan_date 로 창 배정 · 2025-06 말 진입 로트의 청산이 C 기간에 걸림) — 허용 · 인쇄만.

### 4-2. 통계량
- 분위: 특징별·전략별·창별로 `q = x.rank(pct=True, method='average')` · **T1: q ≤ 1/3 · T3: q > 2/3** · 동점은 한 분위에 같이(결측 제외 후).
- 전략별 효과 `Δ_s = mean(ret_pct | T3) − mean(ret_pct | T1)`(%p) · 이진(F06·F11) = `mean(1) − mean(0)`(F06 은 True−False).
- 풀링(전략 고정효과) `Δ_pool = Σ_s n_s·Δ_s / Σ_s n_s`, `n_s` = 그 전략의 그 특징 비결측 행수. 전략 간 원값 평균·분위는 섞지 않는다.
- 전략별 T1 또는 T3 가 **n < 30** 이면 그 전략의 `Δ_s` 는 「판정 불가」(풀링에서 빼고 방향 일치 표에서 「불일치」로 센다).

### 4-3. 블록 순열 검정
- 행 단위 특징(F01·F02·F04~F14): **(strategy, scan_date) 블록 안 비결측 행 전부의 T1/T2/T3 라벨**을 섞는다(그날 시장 효과 보존 · 행 1개 블록은 기여 0).
- 날짜 단위 특징(F03 `n_passed`): 블록 안이 상수라 위 방식이 퇴화 ⇒ **전략 안 날짜열의 원형 이동(circular shift)** — 날짜순 라벨열을 결과열에 대해 무작위 오프셋 k(1…T−1)만큼 돌린다 · 10,000회(서로 다른 이동은 T−1 개뿐 · 자기상관 보존).
- 반복 **10,000회** · 양측 `p = (1 + #{|Δ_perm| ≥ |Δ_obs|}) / 10,001` · 풀링 통계량 `Δ_pool` 에 대해 계산(전략별 p 는 인쇄만).
- 🔒 시드: `np.random.default_rng([20260925, w, f])` — `w` = 0(E)·1(C)·2(③-a)·3(C 에피소드 첫 행) · `f` = 특징 번호(1~14 · ③-a 는 0).

### 4-4. 판정 규칙
1. **E(탐색)** — 「후보 특징」 = `|Δ_pool,E| ≥ 1.0%p` ∧ 순열 `p_E < 0.10`. 후보 목록과 부호를 `RESULTS_explore.md` 에 적고 **C 를 열기 전에 커밋**한다.
2. **C(확인)** — 후보 특징만 `p_C` 를 구하고 **Holm(m = 14)** 보정(비후보 = p 1.0). Holm 단계는 **p 값만으로** 진행하고, 방향·「3전략 중 2」·에피소드 조건은 그 뒤 교집합으로 건다.
   「**특징 있음**」 ⟺ E 후보 ∧ Holm 보정 `p_C < 0.05`(양측) ∧ `sign(Δ_pool,C) = sign(Δ_pool,E)` ∧ **3전략 중 2 이상** `sign(Δ_s,C) = sign(Δ_pool,E)`
   ∧ **종목 에피소드 첫 행 표본**(같은 전략·종목의 연속 거래일 scan_date 묶음마다 첫 행만)에서 `sign(Δ_pool) = sign(Δ_pool,E)` ∧ 비보정 `p < 0.05`.
3. 그 외 전부 「**없음**」. E 에서 후보가 0개면 C 는 인쇄만 하고 전 특징 「없음」.
4. 보조 결과(적중률·r5·r10)·라이브 근사 표본·민감도는 판정을 바꾸지 않는다.
5. F01·F04 는 ③-a 근거 구간(2026-06-05~09-22)을 뺀 C 결과도 인쇄한다(판정은 전 C).
- 검정력(참고): C ≈ 2.3만 행 · 설계효과 5~10 가정 시 Holm 1단계 80% 검정력 최소 효과 ≈ **1.1~1.5%p** · E 문턱 1.0%p 는 그 아래 ⇒ **C 통과는 드물 것**(§0-③ 회의론자 기본 기대와 정합).

### 4-5. ③-a 가설(H-a) — 단독 사전지정 검정 (Holm 가족 밖 · m = 1)
- 내용(라이브 트리 scratchpad 탐색 · 사전등록 없음 · 미검증): **ma20 `rank` 1~10 이 11~20 보다 나쁘다**(p 0.011 · 라이브 스냅샷 73일).
- 🔒 검정 창 = **C 에서 근거 73일 구간을 뺀 2025-07-01 ~ 2026-06-04**(근거 데이터와 날짜가 겹치면 재발견이 된다).
  2026-06-05~09-23 구간과 E 창 값은 **인쇄만**.
- 🔒 결과 변수 = §2-3 **`r5`**(entry = D+1 시가 · `close(entry+5 거래일)/entry − 1` · KOSPI 달력) — 원 정의(라이브 트리 `scratchpad/candidate_rank_check_20260924/REPORT.md:52-58`)와 같다. `ret_pct`·`r10` 은 인쇄만.
- 표본 = ma20 행 중 `rank ≤ 20` ∧ 그날 `n_passed ≥ 11` ∧ `r5` 비결측(§2-2 상한·`exit_reason` 조건 미적용). `Δ_a = mean(r5 | 11~20) − mean(r5 | 1~10)` — **표본 전체 1%/99% winsorize 뒤** 계산(원값 평균도 인쇄).
- 순열 = scan_date 블록 안 라벨 섞기 10,000회 · 양측 p. 「**재현**」 ⟺ `p < 0.05` ∧ `Δ_a > 0`. 그 외 「재현 안 됨」.
- 원 방법과의 차이(원은 `005930` 행 달력 · 시가 결측 시 종가 대체 · 30% 절벽 드롭)는 결과 문서에 적는다(이 문서는 KOSPI 달력 · 대체 없음 · 드롭 없음).

### 4-6. 판정 뒤 할 수 있는 것
- 「특징 있음」 ⇒ **라이브 변경 아님** · 별도 「순위 층 shadow」 사전등록의 입력 후보(그 문서에서 새 표본·새 창으로 다시 검정).
- 전 특징 「없음」 ⇒ 발굴 프로그램 결론(AUC 0.556 천장) **재확인**으로 기록 · 같은 원장으로 특징을 바꿔 재시도하지 않는다(재시도 = 새 사전등록 + 새 표본).
- H-a 「재현」 ⇒ ma20 순위 절단 shadow 사전등록의 입력 · 「재현 안 됨」 ⇒ ③-a 를 「탐색 잡음」으로 기록.

## 5. 금지 🔒

1. 결과를 본 뒤 특징·정의·분위·창·문턱(1.0%p·0.10·0.05·n≥30)·Holm m·시드·표본 규칙을 바꾸는 것.
2. E 결과를 보고 C 의 검정 대상에 특징을 더하는 것 · C 를 E 보다 먼저 여는 것.
3. 판정 문장에 「경향」「약한 신호」「거의 유의」 등 중간 언어 · 라이브 근사/민감도 표를 판정 근거로 쓰는 것.
4. 인쇄만 항목(§3-2·§3-3)을 순위 특징으로 승격하는 것.
5. 이 연구 결과를 3전략 룰 변경 근거로 인용하는 것(~2026-10-16 룰 변경 0건).

## 6. 검증 (verifier 1패스)

- **V-F1** minervini: 재계산 `rs12w` = 원장 `rs_value` 100% 일치(불일치 행 목록 인쇄 · 1건이라도 있으면 F10 중단 보고).
- **V-F2** PIT: F11·F12 에 쓴 모든 `rcept_dt ≤ scan_date − 1` · F13·F14 에 쓴 `foreign_flow.date ≤ scan_date − 1` · F07 평균창 끝 = D−1 — 위반 0건.
- **V-F3** 표본 대수: 원장 행수 = 전수 표본 + 사유별 제외 합(전략×창).
- **V-F4** 층화 3행 손계산(시드 20260925 · 전략별 1행): F07·F10·F13 값을 DB SELECT 로 재계산.
- **V-F5** 종목 상관 점검: **종목 단위 상수 노이즈** 가짜 특징 100개(종목마다 값 1개 · 시드 `default_rng([20260927, i])`, i=1…100)를 E 에서 §4-3 순열로 검정 → `p_E < 0.10` 비율 인쇄(명목 10% · 크게 넘으면 「순열 p 낙관」 경고를 결과 문서 판정문에 병기).

## 7. 한계

1. **다중비교** — Holm(m=14)은 가족 내 FWER 만 막는다. 등록부 전체(REGISTRY) 가족 FWER 은 따로 누적된다.
2. **생존자 편향** — 원장 PREREG §8-2 승계(지금 `daily_prices` 에 남은 종목만 · 행마다 `survivor_universe`).
3. **빈티지(M4)** — 원장 §8-1 승계. `d_volume`·F07 은 현재 DB 값(라이브가 본 값과 다를 수 있다) · 2026-07-03 이전 보정 불가.
4. **gross** — 수수료·세금 0. 특징 간 비교에는 중립이나 절대 수준은 과대.
5. **표본 상관** — 같은 종목이 여러 날·여러 전략에 겹치고 보유 경로가 겹친다. 블록 순열은 «날짜 안» 교환성만 쓰므로 종목 간 계열상관은 못 다룬다 ⇒ p 가 낙관적일 수 있다(결과 문서에 명기 · 경계선 통과 특징은 이 한계를 판정문에 병기).
6. **원장 근사** — 시가 밴드·일봉 청산·on_tick 재평가 미재현(원장 §8-3·4·9).
7. **수급 커버리지** — F13·F14 는 2025 년까지 약 150종목 · 비무작위 결측.
8. **E·C 국면 차이** — 두 창의 시장 국면이 다르면 「방향 불일치」가 국면 탓일 수 있다. 판정은 바꾸지 않는다.

## 8. 비용 상한

- 방법 = SQL(SELECT 전용 · `kis_template` · port 5433) + pandas/numpy 만. 모델·학습기 0.
- 인력 = **scientist(sonnet) 1레인 + verifier 1패스**. 토큰 상한 scientist **40만** · verifier **15만** · 실행 시간 **1시간**(초과 시 중단·보고).
- 순열은 벡터화(분위 라벨 × 블록 인덱스) · 14특징 × 2창 + 에피소드 C + H-a + V-F5 가짜 100개 × 10,000회.

## 9. 산출물 · 순서

경로 `backtest/concept_axes/candidate_ledger/feature_study/`:
- `run_features.py`(유일한 새 코드) · `features.csv`(행 = 원장 행 키 + F01~F14 + 인쇄만 열) · `RESULTS_explore.md` · `RESULTS_confirm.md` · `run_meta.json`(git sha · `loader.db_fingerprint` · 시드 · 행수).
순서: ① **이 문서 동결 커밋**(원장 본 실행 «전») → ② 원장 본 실행·V1~V5 통과(원장 `summary.md`·V5 는 ① 뒤에만 연다) → ③ `features.csv` 생성·V-F1~F4 → ④ E 실행·V-F5 → `RESULTS_explore.md` 커밋 → ⑤ C·에피소드·H-a 실행 → `RESULTS_confirm.md` → ⑥ verifier.
- 라이브 트리에서 실행 금지 · 워크트리에서만.
