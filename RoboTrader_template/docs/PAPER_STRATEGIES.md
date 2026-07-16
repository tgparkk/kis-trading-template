# 가상매매(페이퍼) 운영 전략 — 정본 허브

> SSOT: `config/trading_config.json` `strategies[]` (이 문서는 그 스냅샷의 해설·운영 허브).
> 최종 갱신: 2026-06-24 · 상태: **8전략 활성 (`paper_trading: true`)** · 사이징 = A안 균등 K분할(2026-06-12 발효).
> **전략별 상세는 각 코드 폴더 README로 분산**됨 — 아래 §2 링크. 이 문서는 운영 개요(§0)·한눈표(§1)·운영 메모(§3)를 담는다.

## 0. 운영 개요

### 0.1 무엇을 하는가
- KIS API 기반 자동매매 프레임워크 위에서 **8개의 독립 매수 전략을 동시에 페이퍼(가상) 운영**한다.
- 목적은 단일 "최고 전략" 찾기가 아니라, **성격이 다른 전략군(추세·돌파·눌림목·평균회귀·RS)을 격리 자본으로 병렬 관찰**하여 라이브 거동을 실증하는 것. 전략끼리 자본을 나눠 쓰지 않으므로 한 전략의 부진이 다른 전략에 영향을 주지 않는다.
- `paper_trading: true` → 실제 주문은 나가지 않고, 체결을 시뮬레이션해 전략별 원장에 기록한다.

### 0.2 데이터 소스 (SSOT) — 라이브·연구 공통 `kis_template` (2026-07-16 통일)

**가격 데이터는 단일 진입점(resolver)을 통해서만 읽는다.** `config/constants.py`:
- `resolve_daily_source_db()` → **일봉** DB명 (기본 `kis_template`)
- `resolve_minute_source_db()` → **분봉** DB명 (기본 `kis_template`)
- 롤백 스위치는 **`KIS_DATA_SOURCE=legacy`** 하나뿐(일봉↔분봉이 서로 다른 세대로 갈라지지 않게 공유).

| 데이터 | SSOT | 비고 |
|---|---|---|
| **일봉** | `kis_template.daily_prices` | 2,606종목 · 2021-01-04~ · 2,823,971행 · market_cap 완비 |
| **분봉** | `kis_template.minute_candles` | 1,445종목 · 20250224~ · 55,941,645행 |
| **KOSPI/KOSDAQ 지수 라인** | `kis_template.daily_prices` (`stock_code='KOSPI'`) | 2021-01-04~ 전구간 1,357행 |
| **재무** | `robotrader_quant.*` ⚠️**의도된 예외** | 아래 참조 |

- ⚠️ `adj_factor`를 **곱하지 말 것** — close는 이미 분할조정된 연속 시세다(곱하면 분할일 가짜 절벽 → 거짓 99% MaxDD).
  실측: 035720 2021-04-14 close=112,000 `adj_factor`=5 → 곱하면 560,000 → 분할일 **-78.5% 가짜 폭락**.
- ⚠️ kis_template은 `adj_factor` **NULL 행 44,923개**(KOSPI 지수행 1,357개 전부 포함). 곱하지 않으므로 NaN 전파는 없지만,
  산술/필터에 쓸 일이 생기면 `COALESCE(adj_factor, 1)`.
- ⚠️ `daily_prices.date`가 text 컬럼이라 손상값 행이 섞임 → coerce/dropna 필수.
- **EOD 매수후보 스크리너는 전부 일봉 SSOT(클린)로 산정.**
- **라이브 진입 평가 데이터**:
  - `book_envelope_200d`만 200영업일이 필요해 `QuantDailyReader`(일봉 SSOT)에서 **230봉 직접 조회**(클린).
  - 나머지 7전략은 프레임워크 일봉 피드(`TIMESCALE_DB`, ~85봉) 사용 → 거래량 룰에 미세한 품질 영향(파국 아님).

**왜 통일했나**: 형제 봇(rt·rt_quant) 중단으로 레거시 `robotrader`/`robotrader_quant`는 **2026-07-10 동결**됐고,
`kis_template`이 양쪽의 상위집합(종목·기간·행수 모두 ≥)이며 유일하게 갱신된다. 라이브는 `.env`(`KIS_DATA_SOURCE=new`)로
이미 kis_template을 봤지만, **`.env`는 gitignore 대상이라 연구 프로세스(clean checkout·워크트리·CI)엔 없어** 코드 기본값
(`legacy`)으로 떨어져 **연구만 동결된 죽은 DB를 읽고 있었다**. → 기본값을 `new`로 뒤집어 env 없이 실행돼도 올바른 소스를 쓴다.

**⚠️ 재무는 `robotrader_quant` 유지 — 의도된 예외(오류 아님)**
`financial_statements`(4,350) · `quant_balance_sheet`/`quant_financial_ratio`/`quant_income_statement`(각 45,473)는
**robotrader_quant에만 존재**하고 kis_template엔 **테이블 자체가 없다**(kis의 `financial_data`/`quant_factors`/`quant_portfolio`는
컷오버 때 만든 빈 껍데기 0행). 해당 경로(`lib/signals/roe_filter.py`, `multiverse/data/pit_reader.read_financial_ratio`)는
가격 resolver를 태우면 안 된다. 재무까지 옮기려면 kis_template에 테이블·적재 파이프라인이 먼저 필요하다(별건).

### 0.3 공통 매매 경로
- **진입**: `BaseStrategy.on_tick(ctx)` → `ctx.get_daily_data`(`_drop_unconfirmed_today_bar` 적용 = 당일 미확정봉 제외, 확정봉만) → `generate_signal()` → `ctx.buy()`(서킷브레이커·VI·시장방향 가드 내장).
- **전 전략 진입 룰은 백테스트 룰을 1:1 재사용** (`strategies/books/**/rules*.py`, `scripts/rs_leader/rule.py`, `scripts/discovery/rules.py`를 직접 import) → 백테스트↔라이브 동등성 보장.
- **전 전략 `holding_period = "swing"`** → EOD 일괄청산을 건너뛰고 각 전략의 청산 룰(sl/tp/trail/max_hold)로만 빠진다.

### 0.4 자본·사이징 모델 (A안 균등 K분할, 2026-06-12 발효)
- **전략별 독립 가상자본 = 1,000만원** (`VIRTUAL_CAPITAL_PER_STRATEGY`, `config/constants.py`). 8전략 × 1,000만 = **총 8,000만원** 가상.
- **종목당 매수금액 = 가상자본 ÷ K(`max_positions`) 균등분할** (`main.py::_allocate_strategy_capital`). K는 yaml `risk_management.max_positions`에서 직접 읽는다.
  - 단, yaml에 `paper_investment_per_stock`이 명시되면 그 값이 K분할 기본값을 **덮어쓴다**(현재 `deep_mr_dev20`만 사용).
- ⚠️ `max_capital_pct`는 **별개 레이어**(`FundManager` 실계좌 reserve 비율)로, 가상매매의 전략별 1,000만 격리·종목당 금액과는 **무관**하다. 페이퍼 손익은 폴더키별 격리 원장으로만 집계된다.

### 0.5 두 개의 regime(국면) 레이어 (혼동 주의)
| 필드 | 의미 | 소스 |
|---|---|---|
| `regime_index` | **시장방향 급락 검사**용 지수 (장중 `ctx.buy` 가드) | KIS 실시간지수 (KOSPI 0001 / KOSDAQ 1001) |
| `regime_gate` | **국면 매수차단** (BEAR/비BULL 진입 차단, EOD 1회 캐시 PIT) | `core/regime/regime_gate.py`, `daily_prices` KOSPI/KOSDAQ + `classify_daily` |

## 1. 활성 전략 한눈표

| # | 전략 (폴더키) | 출처 | 진입 핵심 | 청산 (sl / tp / trail / maxhold) | regime idx/gate | K | 종목당 | 유니버스 |
|---|---|---|---|---|---|---|---|---|
| 1 | [`elder_ema_pullback`](../strategies/elder_ema_pullback/README.md) | Elder 삼중창 (Var A) | EMA65 상승 + EMA13 눌림회복 + 전일고가 돌파 | -8% / +30% / EMA13 trail·EMA65 추세반전 / 100일 | KOSPI / none | 20 | 50만 | 대형(시총≥5천억)·거래대금≥50억 |
| 2 | [`book_envelope_200d`](../strategies/book_envelope_200d/README.md) | Book19 트레이딩 전략서 | 200일 신고가 + Envelope(10,10) 상단 +10% 돌파 (A~I) | -8% / +10% / 없음 / 10일 | KOSPI / none | 5 | 200만 | 거래대금≥10억 (진입평가 quant 230봉) |
| 3 | [`daytrading_3methods_breakout`](../strategies/daytrading_3methods_breakout/README.md) | 유지윤 3대 타법 (Var B) | 직전15봉 전고점 돌파 + 거래량×2 + 양봉 | -10% / +10% / 없음 / 10일 | KOSDAQ / none | 5 | 200만 | 중소형(시총<5천억)·거래량배수순 |
| 4 | [`minervini_volume_dryup`](../strategies/minervini_volume_dryup/README.md) | Minervini VCP (Var B) | 최근10봉 평균거래량 ≤ 직전30봉의 70% (dry-up) | -8% / +12% / 없음 / 20일 | KOSPI / none | 3 | 333만 | 시총≥3천억·거래대금≥30억 |
| 5 | [`book_pullback_ma20`](../strategies/book_pullback_ma20/README.md) | 강창권 단기트레이딩 A-07 | 30일내 +25% 급등 + 20일선 눌림 지지 양봉 | -8% / +10% / MA20 trail / 50일 | KOSPI / exclude_bear | 5 | 200만 | 중소형(시총≤3조)·KOSPI+KOSDAQ |
| 6 | [`book_pullback_ma5`](../strategies/book_pullback_ma5/README.md) | 트레이딩의 전설 (Book15) | 20일내 +20% 급등 + 5일선 눌림 지지 양봉 | **-3%** / +15% / MA5 trail / 30일 | KOSPI / exclude_bear | 5 | 200만 | 중소형(시총≤3조)·KOSPI+KOSDAQ |
| 7 | [`rs_leader`](../strategies/rs_leader/README.md) | 횡보장 RS 리더 (derived) | 절대상승추세 + 횡단면 RS 랭킹(스크리너) | -8% / +15%(거의무효) / **MA20 trail(무조건)** / 30일 | KOSPI / exclude_bear | 10 | 100만 | 절대상승추세 통과 → 120일수익률 RS topK |
| 8 | [`deep_mr_dev20`](../strategies/deep_mr_dev20/README.md) | 발굴 파이프라인 배치3 | MA20 대비 -20% 폭락 + RSI(14)<30 | -7% / +12% / MA20×0.9 회복 / 7일 | KOSPI / none | 5 | 200만 | 거래대금≥100억 (top300 근사)·폭락깊이순 |

> 스크리너는 8전략 공통으로 `max_candidates=10`을 score 내림차순 정렬해 topK 후보를 만든다. `target_stocks: []`(전부 비움)이면 EOD 스크리너 후보를 사용한다.

## 2. 전략별 상세 (코드 옆 README)

각 전략의 의도·진입/청산 룰·평판 상세는 코드 폴더의 README로 이동했습니다 (코드와 같이 보기 위함).

| # | 전략 | 상세 문서 |
|---|---|---|
| 1 | Elder 삼중창 (Var A) | [`strategies/elder_ema_pullback/README.md`](../strategies/elder_ema_pullback/README.md) |
| 2 | Book19 트레이딩 전략서 | [`strategies/book_envelope_200d/README.md`](../strategies/book_envelope_200d/README.md) |
| 3 | 유지윤 데이트레이딩 3대 타법 | [`strategies/daytrading_3methods_breakout/README.md`](../strategies/daytrading_3methods_breakout/README.md) |
| 4 | Minervini VCP | [`strategies/minervini_volume_dryup/README.md`](../strategies/minervini_volume_dryup/README.md) |
| 5 | 강창권 단기트레이딩 A-07 | [`strategies/book_pullback_ma20/README.md`](../strategies/book_pullback_ma20/README.md) |
| 6 | 트레이딩의 전설 (Book15) | [`strategies/book_pullback_ma5/README.md`](../strategies/book_pullback_ma5/README.md) |
| 7 | 횡보장 RS 리더 (derived) | [`strategies/rs_leader/README.md`](../strategies/rs_leader/README.md) |
| 8 | 발굴 파이프라인 배치3 | [`strategies/deep_mr_dev20/README.md`](../strategies/deep_mr_dev20/README.md) |

## 3. 운영 메모 / 잔여

- **봇 재시작 시 반영**: config 변경(전략 추가·사이징·gate)은 1회 로드라 봇 재시작 시 발효된다. deep_mr_dev20 등록 + A안 균등 K분할 사이징은 2026-06-12 적용분.
- **정식 leaderboard.parquet 등재**: envelope·rs_leader·deep_mr 등 신규/관찰 전략은 **페이퍼 실적 누적 후** 판정(지시). 현 백테스트 수치는 강세장 순풍·in-sample 편향이 섞여 라이브 실증이 필요.
- **성격 분포**: 추세(elder=강·minervini=평범) / 돌파(envelope=비강세장 alpha·유지윤=약함) / 눌림목(ma20·ma5=게이트 수혜·OOS 부진) / RS(rs_leader=횡보장 관찰) / 평균회귀(deep_mr=폭락 저격). 강세장을 이기는 게 목적이 아닌 전략이 다수 — 격리자본이라 상호 무영향.
- **데이터 버그 주의**: `daily_prices.date`가 text라 손상값 행 존재(coerce/dropna 필수). adj_factor는 quant close가 이미 조정됐으므로 **곱하지 말 것**(분할일 가짜절벽 → 거짓 99% MaxDD).
