# 가상매매(페이퍼) 운영 전략 — 정본 허브

> SSOT: `config/trading_config.json` `strategies[]` (이 문서는 그 스냅샷의 해설·운영 허브).
> 최종 갱신: 2026-09-17 · 상태: **8전략 활성 (`paper_trading: true`)** · 사이징 = 자본/K 균등분할(2026-06-12 발효) + 재기동마다 복리 재산정(07-29) + `max_per_stock_amount` 캡(08-27) — §0.4.
> **전략별 상세는 각 코드 폴더 README로 분산**됨 — 아래 §2 링크. 이 문서는 운영 개요(§0)·한눈표(§1)·운영 메모(§3)를 담는다.
> 🎯 **집중 3전략 / 관측 5전략**(2026-09-05 사장님 결정 · [`plan_2026-09-05_focus3_roadmap.md`](plan_2026-09-05_focus3_roadmap.md)): 집중 = `book_pullback_ma20` · `minervini_volume_dryup` · `daytrading_3methods_breakout`. 나머지 5전략(elder·envelope·ma5·rs_leader·deep_mr)은 페이퍼 그대로 돌리며 **관측만**.
> ⏰ **K 상향 예정 — 2026-09-18 07:40 재기동 발효**([`prereg_2026-09-15_focus3_K_raise.md`](prereg_2026-09-15_focus3_K_raise.md)): ma20 **5→10** · daytrading **5→10** · minervini **3→6**. **오늘(09-17) `config.yaml` 값은 5/3/5 그대로**이고 아래 §1 표도 현행값이다.
> 🛡 **rs_leader 매수 배제 가드 `live` — 2026-09-17 07:40 발효**([`prereg_2026-09-16_rsleader_exclusion_live.md`](prereg_2026-09-16_rsleader_exclusion_live.md)): 코드 기본값은 `shadow`(`config/constants.py::resolve_rs_leader_corp_action_mode` — env 미설정 시), 라이브는 `.env` `RS_LEADER_CORP_ACTION_MODE=live` 한 줄로 올렸다(코드 0줄).

## 0. 운영 개요

### 0.1 무엇을 하는가
- KIS API 기반 자동매매 프레임워크 위에서 **8개의 독립 매수 전략을 동시에 페이퍼(가상) 운영**한다.
- 목적은 단일 "최고 전략" 찾기가 아니라, **성격이 다른 전략군(추세·돌파·눌림목·평균회귀·RS)을 격리 자본으로 병렬 관찰**하여 라이브 거동을 실증하는 것. 전략끼리 자본을 나눠 쓰지 않으므로 한 전략의 부진이 다른 전략에 영향을 주지 않는다.
- `paper_trading: true` → 실제 주문은 나가지 않고, 체결을 시뮬레이션해 전략별 원장에 기록한다.

### 0.2 데이터 소스 (SSOT) — 규칙 6개만 · 상세는 [DATABASE.md](DATABASE.md)

접속 정보·표 목록·행수 스냅샷·DB 통합 경위와 2026-08-17 정정 이력은 **[`docs/DATABASE.md`](DATABASE.md)**(정본)와 [`DB통합_쉬운설명.md`](DB통합_쉬운설명.md)(경위)로 옮겼다(구판 본문 = 직전 판 `16a8106`(HEAD) · 이 파일의 마지막 변경 커밋 `af45e7c`(09-10)는 §1 표 한 줄뿐이라 **§0.2 본문은 `ae38fc8` 2026-08-17 이후 불변**). 여기엔 전략 코드가 지켜야 할 규칙만 남긴다.

1. **가격은 resolver 로만 읽는다** — `config/constants.py` `resolve_daily_source_db()`(일봉) · `resolve_minute_source_db()`(분봉) → **항상 `kis_template`**. DB명 하드코딩 금지. 이 resolver 는 **가격 전용**이며 재무는 `multiverse/data/pit_reader.py` 의 `QUANT_FINANCIAL_DB`(기본 `kis_template`)로 독립 제어한다.
2. 🔴 **롤백 스위치는 «없다»**(2026-08-17 폐지) — `KIS_DATA_SOURCE`·`QUANT_DB`·`MINUTE_DB`·`CORP_EVENTS_DB` 는 설정해도 **무시된다**. 새 env 로 되살리지 말 것.
3. ⚠️ **가격(`open/high/low/close`)에 `adj_factor` 를 곱하지 말 것** — close 는 이미 분할조정된 연속 시세다(곱하면 분할일 가짜 절벽 → 거짓 99% MaxDD).
4. 🔑 **`volume` 은 반대로 `adj_factor` 를 곱해야 맞고, 읽기 계층(`db/quant_daily_reader.py`, `volume * COALESCE(adj_factor, 1)`)이 이미 곱한다**(2026-08-15 감사) — 소비자는 그냥 쓴다(**다시 곱하면 이중조정**). 영향 룰 = `daytrading_3methods` 「당일 ≥ 직전20봉 평균×2」(분할 직후 20봉간 가짜 매수신호) · `minervini` dry-up(반대로 억제). 🔴 수정 «전» 척도로 만든 백테스트 산출물은 재검증 시 숫자가 달라진다.
5. ⚠️ **`adj_factor` NULL 행이 있다** — 2026-09-17 실측 `daily_prices` 3,209,019행 중 **411,605행**(지수 의사행 **KOSPI·KOSDAQ** 각 1,400행 = 2,800행 전부 포함 — **`KS11`·`KQ11` 각 601행(합 1,202행)은 `adj_factor` 비NULL**). 곱하지 않으므로 NaN 전파는 없지만 산술/필터에 쓸 일이 생기면 `COALESCE(adj_factor, 1)`.
6. ⚠️ **`daily_prices.date` 가 text 컬럼**이라 손상값 행이 섞일 수 있다 → coerce/dropna 필수.

- **EOD 매수후보 스크리너는 전부 일봉 SSOT(클린)로 산정.**
- **라이브 진입 평가 데이터**: `book_envelope_200d`만 200영업일이 필요해 `QuantDailyReader`(일봉 SSOT)에서 **230봉 직접 조회**(클린 · `config.yaml` `entry_lookback_bars: 230`). 나머지 7전략은 프레임워크 일봉 피드(`TIMESCALE_DB`, 200봉 미만) 사용.

### 0.3 공통 매매 경로
- **진입**: `BaseStrategy.on_tick(ctx)` → `ctx.get_daily_data`(`_drop_unconfirmed_today_bar` 적용 = 당일 미확정봉 제외, 확정봉만) → `generate_signal()` → `ctx.buy()`(서킷브레이커·VI·시장방향 가드 내장).
- **전 전략 진입 룰은 백테스트 룰을 1:1 재사용** (`strategies/books/**/rules*.py`, `strategies/rs_leader/rule.py`, `strategies/deep_mr_dev20/rule.py`를 직접 import) → **«룰 코드» 동등성** 보장.
  - 🔴 **이 문장을 「성과 동등성」으로 읽지 말 것** — 유니버스가 다르다. **§0.7 참조.**
  - ⚠️ 뒤 두 룰은 2026-07-02 Phase1 에서 `scripts/rs_leader/`·`scripts/discovery/` 로부터 **승격**됐다(라이브 엣지 -2). 옛 경로를 인용하지 말 것 — `scripts/rs_leader/rule.py` 는 **이제 존재하지 않고**(폴더엔 `decompose.py`·`exit_adapter.py`(+`__init__.py`)만 남음), `scripts/discovery/rules.py` 에는 `MeanReversionMA20Rule` **정의가 없고 `strategies.deep_mr_dev20.rule` 에서 re-export 하는 한 줄만 남아 있다**(정본은 `strategies/deep_mr_dev20/rule.py`).

### 0.7 🔴 백테스트 평판 숫자와 라이브는 «다른 모집단»이다 (2026-08-15 감사)

각 README 의 평판 숫자(`Sharpe 1.55` · `+269%` · `MaxDD 20%` 등)는 **검증 러너의 유니버스**에서 나왔다:

```python
# scripts/run_{elder_triple_screen, daytrading_3methods, minervini_vcp,
#              haru_silijeon_daily, trading_legends_daily}.py · run_books_research.py
_load_top_volume_universe(top_n=50)   # 기간 «전체» SUM(close*volume) 상위 50종목, 정적
```

라이브 스크리너는 **종목별 시총 컷 + 거래대금 하한**이라 기준 자체가 다르다. 실측(2026-06-01~08-14):

| | 라이브 매수 | `top_volume:50` 소속 | 비중 |
|---|---|---|---|
| 8전략 합계 | **646건** | **17건** | **3%** |
| 0% 인 전략 | `envelope`·`ma20`·`ma5`·`daytrading`·`deep_mr` | 0 | **0%** |

🔑🔑 ***라이브 매수의 97%가 백테스트가 본 적 없는 종목이다.*** 겹치는 3%조차 우연 기대치(7.2~10.2건)와 같은 자릿수다.

⇒ **평판 숫자를 라이브 기대치로 인용하지 말 것.** 같은 룰이라도 다른 유니버스에 적용하면 다른 전략이다.
실측·재현 → [`backtest/concept_fidelity_audit/`](../backtest/concept_fidelity_audit/RESULTS.md) §3-D ·
라이브 유니버스 재검증(3전략 진행) → [`backtest/live_universe_revalidation/PREREG.md`](../backtest/live_universe_revalidation/PREREG.md).

⚠️ 함께 확인된 것: **거동도 다르다** — 백테스트 보유 중앙 10~13거래일(≤1일 2~4%)인데 라이브는 1~2일(≤1일 43~69%).
⚠️ `top_volume:50` **자체가 룩어헤드**다(기간 전체 거래대금으로 뽑은 정적 집합) — 「정답 유니버스」가 아니다.
- **전 전략 `holding_period = "swing"`** → EOD 일괄청산을 건너뛰고 각 전략의 청산 룰(sl/tp/trail/max_hold)로만 빠진다.

### 0.4 자본·사이징 모델 (자본/K 균등분할 2026-06-12 발효 · 복리 재산정 07-29 · 종목당 캡 08-27)
- **전략별 독립 가상자본 = 1,000만원** (`VIRTUAL_CAPITAL_PER_STRATEGY`, `config/constants.py`). 8전략 × 1,000만 = **총 8,000만원** 가상.
- **종목당 매수금액 = 전략 현재자본(현금 + 포지션 원가) ÷ K(`max_positions`)**. 기동 시 `bot/initializer.py::_allocate_strategy_capital`(`main.py::_allocate_strategy_capital` 이 위임)이 `초기자본/K` 로 할당하고, 재기동마다 `core/virtual_trading_manager.py::recalculate_investment_amounts` 가 `base × (현재자본/초기자본)` 로 **복리 재산정**한다(`bot/state_restorer.py` 가 원장 복원 직후 호출). K는 yaml `risk_management.max_positions`에서 직접 읽는다. ⚠️ 그래서 §1 표의 「종목당」 열은 **초기값(1,000만/K)** 이고, 실제 금액은 그날 기동 로그 `종목당 투자금액 재산정` 줄이 정본이다.
  - 단, yaml에 `paper_investment_per_stock`이 명시되면 그 값이 K분할 기본값을 **덮어쓴다**(현재 `deep_mr_dev20`만 사용).
- **종목당 캡**: yaml `risk_management.max_per_stock_amount`(8전략 전부 선언 — 7전략 300만 · deep_mr 200만)가 `get_max_quantity` 의 `min(per_stock, 전략 잔여현금, cap)` **세 번째 항**으로 들어간다(`fe02983`, 2026-08-27 결선 — 그 전엔 선언만 있고 사이징 경로에 독자가 없었다).
- ⚠️ `max_capital_pct`(`config/trading_config.json` `strategies[]`)는 **현재 아무것도 제한하지 않는다** — `FundManager.reserve_funds` 의 전략별 상한 검사는 `strategy_max_pct_provider` 콜백이 주입돼야 도는데 `main.py` 가 `FundManager(max_daily_loss_ratio=…)` 로만 생성해 provider 가 `None` 이다. 유일한 소비자는 `strategies/config.py::StrategyLoader.load_strategies` 의 「합계 > 100% WARNING」뿐. 페이퍼 손익은 폴더키별 격리 원장으로만 집계된다.

### 0.5 두 개의 regime(국면) 레이어 (혼동 주의)
| 필드 | 의미 | 소스 |
|---|---|---|
| `regime_index` | **시장방향 급락 검사**용 지수 (장중 `ctx.buy` 가드). 값 `KOSPI` / `KOSDAQ` / `both` / `none`(면제 — `check_market_direction` 이 검사 없이 통과) / `auto` — 인식 불가 값은 WARNING 후 `both` 폴백 · `auto` 는 매수 대상 종목의 **소속 시장**으로 해석하고 결측·조회 실패면 `both`(양쪽 검사)로 떨어진다(`core/regime/market_classifier.py::resolve_regime_index`) | KIS 실시간지수 (KOSPI `0001` / KOSDAQ `1001`, `core/trading_decision_engine.py`) |
| `regime_gate` | **국면 매수차단** (BEAR/비BULL 진입 차단, EOD 1회 캐시 PIT) | `core/regime/regime_gate.py`, `daily_prices` KOSPI/KOSDAQ + `classify_daily` |

### 0.6 현금 원장이 둘이다 (설계다, 결함이 아니다 — 2026-08-14 확인)

페이퍼 매매의 "현금"을 계산하는 두 경로가 **매수 수수료를 서로 다른 시점에 인식**한다:

| 원장 | 수수료 인식 시점 | 근거 |
|---|---|---|
| `VirtualTradingManager` 전략별 `_strategy_balances`(→ `paper_strategy_equity.cash`) | **매수 시점** — 현금주의 | `core/virtual_trading_manager.py::execute_virtual_buy` (`total_cost_with_fee = total_cost + commission`을 매수 즉시 전략 잔고에서 차감) |
| `core/fund_manager.py` `available_funds` | **매도 시점**, 매도 포지션의 원가 기준 — 발생주의 | `core/fund_manager.py::confirm_order` docstring — "매수 수수료는 여기서 차감하지 않는다... 되돌리지 말 것: 매수 수수료는 «매도 시 1회» 인식이 의도된 설계다" |

- 일일 갭 크기는 `COMMISSION_RATE(=0.00015, config/constants.py) × (오늘 매도분 원가 − 오늘 매수금액)` 규모다 — 포지션이 청산되면 두 원장 모두 같은 총 수수료를 인식하게 되어 수렴한다.
- 🔴 **실계좌 예수금은 현금주의다.** `fund_manager.available`을 실계좌 잔고와 대사(reconcile)하지 말 것 — 자동 대사를 켜기 전에 어느 원장을 기준으로 삼을지 먼저 정할 것.

## 1. 활성 전략 한눈표

| # | 전략 (폴더키) | 출처 | 진입 핵심 | 청산 (sl / tp / trail / maxhold) | regime idx/gate | K | 종목당 | 유니버스 |
|---|---|---|---|---|---|---|---|---|
| 1 | [`elder_ema_pullback`](../strategies/elder_ema_pullback/README.md) | Elder 삼중창 (Var A) | EMA65 상승 + EMA13 눌림회복 + 전일고가 돌파 | -8% / +30% / EMA13 trail·EMA65 추세반전 / 100일 | KOSPI / none | 20 | 50만 | 대형(시총≥5천억)·거래대금≥50억 |
| 2 | [`book_envelope_200d`](../strategies/book_envelope_200d/README.md) | Book19 트레이딩 전략서 | 200일 신고가 + Envelope(10,10) 상단 +10% 돌파 (A~I) | -8% / +10% / 없음 / 10일 | KOSPI / none | 5 | 200만 | 거래대금≥10억 (진입평가 quant 230봉) |
| 3 | [`daytrading_3methods_breakout`](../strategies/daytrading_3methods_breakout/README.md) | 유지윤 3대 타법 (Var B) | 직전15봉 전고점 돌파 + 거래량 ≥ 직전**20**봉평균×2 + 양봉 | -10% / +10% / 없음 / 10일 | **auto**(종목 소속 시장 · 2026-09-11 `9ab3c37`, 종전 KOSDAQ) / none | 5 | 200만 | 중소형(시총<5천억)·거래량배수순 |
| 4 | [`minervini_volume_dryup`](../strategies/minervini_volume_dryup/README.md) | Minervini VCP (Var B) | dry-up(최근10봉 평균거래량 ≤ 직전30봉의 70%) **∧ Trend Template**(TT 8조건 · 2026-08-25 `86ff02d` `on`) | -8% / +12% / 없음 / 20일 | KOSPI / none | 3 | 333만 | 시총≥3천억·거래대금≥30억 |
| 5 | [`book_pullback_ma20`](../strategies/book_pullback_ma20/README.md) | 강창권 단기트레이딩 A-07 | 30일내 +25% 급등 + 20일선 눌림 지지 양봉 | -8% / +10% / MA20 trail / 50일 | KOSPI / exclude_bear | 5 | 200만 | 중소형(시총≤3조)·KOSPI+KOSDAQ |
| 6 | [`book_pullback_ma5`](../strategies/book_pullback_ma5/README.md) | 트레이딩의 전설 (Book15) | 20일내 +20% 급등 + 5일선 눌림 지지 양봉 | **-3%** / +15% / MA5 trail / 30일 | KOSPI / exclude_bear | 5 | 200만 | 중소형(시총≤3조)·KOSPI+KOSDAQ |
| 7 | [`rs_leader`](../strategies/rs_leader/README.md) | 횡보장 RS 리더 (derived, ⚠️미조정 병합 의심 종목 매수 배제 가드 — `RS_LEADER_CORP_ACTION_MODE` 코드 기본 `shadow` · 라이브 `.env` **`live`** 2026-09-17 발효) | 절대상승추세 + 횡단면 RS 랭킹(스크리너) | -8% / +15%(거의무효) / **MA20 trail(무조건)** / 30일 | KOSPI / exclude_bear | 10 | 100만 | 절대상승추세 통과 → 120일수익률 RS topK |
| 8 | [`deep_mr_dev20`](../strategies/deep_mr_dev20/README.md) | 발굴 파이프라인 배치3 | MA20 대비 -20% 폭락 + RSI(14)<30 | -7% / +12% / MA20×0.9 회복 / 7일 | KOSPI / none | 5 | 200만 | 거래대금≥100억 (top300 근사)·폭락깊이순 |

> 후보 수는 두 단계다 — **EOD 스냅샷 상한 20**(`config/constants.py` `MAX_CANDIDATES_PER_STRATEGY`, `bot/liquidation_handler.py` 가 스크리너에 넘김 · score 내림차순 topK) · **라이브 소비 10**(`config/trading_config.json` `strategy.parameters.max_candidates`, `bot/candidate_loader.py::_load_screener_candidates` → `_load_candidates_multi_strategy`). 종전 「8전략 공통 `max_candidates=10`」 표현은 소비 쪽만 맞았다. `target_stocks: []`(전부 비움)이면 EOD 스크리너 후보를 사용한다.

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

## 4. 줄번호 앵커 이동표 (2026-09-17 §0.2 축약으로 줄이 당겨졌다)

이 파일을 **줄번호로 인용하는 문서**(`backtest/concept_fidelity_audit/RESULTS.md` · `backtest/concept_axes/minervini/CONCEPT_WIRING_AUDIT.md` — 이 둘은 `backtest/` 동결 · `docs/audit_2026-08-23/` · `docs/audit_2026-08-24/` — 이 둘은 동결 아님, 다만 손대지 않았다)가 있다. 그 줄번호는 **2026-09-17 이전 판**(171줄) 기준이다:

| 인용 줄(구) | 내용 | 현재 위치 |
|---|---|---|
| :33 | daytrading 「20봉평균×2」가 분할 경계에서 왜곡 | §0.2 규칙 4 (:24) |
| :37 | `adj_factor` NULL 행 수 | §0.2 규칙 5 (:25) |
| :42 | envelope 230봉 직접 조회(클린) | §0.2 마지막 불릿 (:29) |
| :51 | 「백테스트↔라이브 동등성 보장」 — 08-17 판에서 이미 :81 로 밀려 있었다 | §0.3 두 번째 불릿 (:33) |
| :100 | §0.7 표 「0% 인 전략」 행(`audit_2026-08-24/strategy_book_envelope_200d.md:261`) | §0.7 표 (:52) |
| :115 | `paper_investment_per_stock` 이 K분할을 덮어씀 | §0.4 (:67) |
| :141~:147 | §1 한눈표 2~8행 | §1 표 (:94~:100) |
| :149 (`audit_2026-08-23/strategy_daytrading_3methods_breakout.md:26` 은 :146 으로 잘못 인용 — :146 은 위 행의 7행 rs_leader = :99) | 「공통 `max_candidates=10`」 → 스냅샷 20 · 소비 10 으로 정정 | §1 표 아래 주 (:102) |
