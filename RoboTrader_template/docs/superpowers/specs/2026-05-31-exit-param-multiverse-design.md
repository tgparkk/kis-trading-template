# 선별 4전략 청산 파라미터 멀티버스 최적화 — 설계서

> 작성: 2026-05-31 · 상태: 설계 승인 대기 → 구현계획(writing-plans)
> 대상: 15권 책 조사에서 선별된 라이브 페이퍼 4전략의 **청산 파라미터** 워크포워드 그리드 최적화

---

## 1. 목적

15권 조사를 거쳐 라이브 페이퍼로 채택한 4전략(`elder_ema_pullback`, `minervini_volume_dryup`,
`book_pullback_ma20`, `book_pullback_ma5`)의 **청산 파라미터**(손절·익절·최대보유·트레일링)를
멀티버스 그리드 탐색으로 최적화한다. 단, 이 프로젝트가 15권 내내 경계해 온 **과최적화(단일 BULL 거품,
다중검정 편향)**를 구조적으로 방지하는 것을 최우선 제약으로 둔다.

**한 줄 요약**: "실전 페이퍼와 같은 잣대(전략당 1천만 포트폴리오)로, 워크포워드 OOS에서, 국면최악 Sharpe와
DSR 게이트를 통과한 청산 파라미터만 채택한다. 기존값을 못 이기면 기존값을 유지한다."

---

## 2. 핵심 결정 사항 (사장님 확정)

| # | 결정 | 값 |
|---|---|---|
| 1 | 최적화 범위 | **청산 파라미터만** (진입 룰은 책 원본 그대로 고정) |
| 2 | 목적함수 | **국면최악 Sharpe** → **DSR 게이트** 2단 |
| 3 | 검증 방식 | **워크포워드(롤링)** — in-sample 최적화 / OOS 평가 분리 |
| 4 | 병렬화 | **전략 4-way 프로세스 × 내부 `n_jobs`** (16 논리코어) |
| 5 | 인프라 | **기존 `run_*` 룰 재사용** + 워크포워드/국면/DSR 래퍼 신규 |
| 6 | 자본 모델 | **포트폴리오 (전략당 1천만 공유, max_positions=5, 종목당 300만)** = 실전 페이퍼와 동일 |
| 7 | 하드웨어 | RAM 64GB → 일봉 메모리 상주 캐싱 + 코어 풀가동 |

---

## 3. 4전략 ↔ 백테스트 룰 매핑

| 라이브 전략 | 백테스트 룰 모듈 | 진입 함수 | 청산 파라미터(그리드 대상) | 기존 러너 |
|---|---|---|---|---|
| elder_ema_pullback | `strategies/books/elder_triple_screen/rules.py` | screen1/2/3 | sl·tp·max_hold·**trail_ema·trend_flip** | `run_elder_triple_screen.py` |
| minervini_volume_dryup | `strategies/books/minervini_vcp/rules.py` | `rule_volume_dryup` | sl·tp·max_hold (trail/flip 없음) | `run_minervini_vcp.py` |
| book_pullback_ma20 (강창권) | `strategies/books/haru_silijeon/rules_daily.py` | `rule_daily_ma20_pullback` | sl·tp·max_hold·**trail_ma** | `run_haru_silijeon_daily.py` |
| book_pullback_ma5 (Book15) | `strategies/books/trading_legends/rules_daily.py` | `rule_ma5_pullback` | sl·tp·max_hold·**trail_ma** | `run_trading_legends_daily.py` |

4전략 모두 진입 함수와 청산 파라미터가 코드에 명시적으로 노출돼 있어 그리드화가 가능하다.

---

## 4. 아키텍처

```
scripts/exit_param_walkforward.py        ← 신규 공통 러너 (CLI)
  ├─ 전략 어댑터 4개 (신규, 얇음)
  │    = { 진입신호 함수(rules.py 직접 호출), 청산 파라미터 그리드, 유니버스 정의, 최소봉수 }
  │      simulate_one_stock 시그니처 차이(trail_ema/trail_ma/없음)를 흡수
  ├─ 포트폴리오 시뮬레이터 (신규, 얇음)
  │    1천만·max5·종목당300만·우선순위·다음날 시가 체결
  │    진입판정 = 기존 rules.py 함수 그대로 호출 (동등성 유지)
  │    청산판정 = 기존 simulate_one_stock 청산 분기 이식 (sl→tp→mh→trail→flip 우선순위)
  ├─ 워크포워드 엔진 (신규)                ← 롤링 train/test 분할
  ├─ 국면 라벨러 (재사용)                  ← backtest/regime_analysis.classify_regime_rolling
  ├─ 목적함수 (신규)                       ← 국면최악 Sharpe → DSR 게이트
  └─ DSR (재사용)                          ← multiverse/runner/dsr.deflated_sharpe_ratio
```

### 4.1 왜 포트폴리오 시뮬레이터를 신규로 짜는가
- **사장님 결정 = 포트폴리오 모델**(실전 페이퍼와 같은 잣대). 그러나 기존 백테스트(`simulate_one_stock`)는
  **종목마다 독립 1천만 시드 → 종목간 Sharpe 평균** 방식의 per-stock 모델이라 자금·슬롯 제약이 없다.
- 기존 `multiverse/engine/portfolio_engine.py`는 자금·슬롯·우선순위·다음날 시가 체결을 갖췄지만
  **composable paramset(signal_gen/exit_rule/scorer/regime)에 강결합**돼 있어 4전략을 composable로
  재표현해야 쓸 수 있다 — 이는 기각된 "접근법 B(정체성 변형)"로의 회귀.
- 따라서 `portfolio_engine.py`의 **로직을 참고**하되 composable 결합을 떼어낸 얇은 시뮬레이터를 신규 작성한다.
  단, **진입·청산 판정 자체는 기존 `rules.py`/`simulate_one_stock`에서 그대로 가져온다.**
  신규로 짜는 부분은 오직 "여러 종목 신호를 1천만 한 통으로 어떻게 체결하느냐"는 자금관리 층이다.

### 4.2 우선순위·체결 규칙 (포트폴리오 시뮬레이터)
- **진입**: 신호일 다음 거래일 시가 체결(룩어헤드 방지). elder는 기존대로 Screen3 매수스톱(전일고가+1틱) 추적.
- **자금/슬롯 제약**: 동시보유 ≤ 5, 종목당 투자금 ≤ 300만, 현금 부족 시 진입 스킵(skipped_signals 기록).
- **신호 초과 시 우선순위**: 동일일 신규 후보가 슬롯/현금을 초과하면 거래대금 상위순으로 체결(기존 유니버스
  정렬 기준과 일치). 결정규칙은 결정론적(난수 없음)으로 고정.
- **청산**: 매 거래일 보유 종목에 sl→tp→max_hold→trail→(elder의 trend_flip) 우선순위로 판정(기존 로직 동일).

---

## 5. 워크포워드 스킴

- 데이터 기간: **2021-01-04 ~ 2026-05-29** (약 65개월)
- 롤링: **train 24개월 → test 6개월, step 6개월** → 약 **7개 OOS 폴드**
- train 24개월은 거의 모든 폴드에서 2022 BEAR 국면을 포함 → 국면최악 목적함수가 실효성을 가진다.
- 각 폴드 절차: train에서 그리드 전체 탐색 → 목적함수로 베스트 선정 → **test(미사용 OOS)에서 성과만 기록**.
- 최종 채택 판정은 **OOS 성과의 안정성** 기준(train 성과로 자랑 금지).

> 윈도우 길이(24/6/6)는 구현 시 폴드 수·표본 충분성을 보고 ±조정 가능. 단 train에 BEAR 포함은 불변 조건.

---

## 6. 청산 그리드 (전략별)

진입 룰은 고정. 그리드 크기는 DSR의 `n_trials`로 들어가므로 **의도적으로 절제**한다.
**현재 검증값을 그리드 중앙에 포함** → 최적화가 기존값을 못 이기면 "기존값 유지"가 정직한 결론이 된다.

| 전략 | stop_loss | take_profit | max_hold | trail | 조합수(약) |
|---|---|---|---|---|---|
| elder | 6 / **8** / 10% | 20 / **30** / 40% | 60 / **100** / 150 | **ema13** / off | ~54 |
| minervini | 6 / **8** / 10% | 10 / **12** / 15% | 15 / **20** / 30 | (없음) | ~27 |
| ma20(강창권) | 6 / **8** / 10% | 8 / **10** / 15% | 30 / **50** / 80 | **ma20** / off | ~54 |
| ma5(Book15) | 4 / **6** / 8% | 12 / **15** / 20% | 20 / **30** / 50 | **ma5** / off | ~54 |

(굵은 값 = 현재 검증/운용값. 정확한 범위는 구현 시 각 `rules.py`/`run_*`의 현재 파라미터를 재확인해 확정.)

---

## 7. 목적함수 파이프라인 (각 폴드 train 내부)

1. 각 청산 조합으로 **포트폴리오 백테스트**(1천만·max5·종목당300만, 유니버스 `top_volume:50`).
2. 체결된 round-trip 거래를 **진입일 국면**(BULL/BEAR/SIDEWAYS)으로 분류
   (`classify_regime_rolling`, KOSPI 20일 rolling ±2% — 기존 `regime_split_*` convention과 통일).
3. **국면최악 Sharpe = min(BULL, BEAR, SIDEWAYS Sharpe)** 로 조합 순위.
   - 특정 국면 표본이 과소하면(예: 거래 < N건) 해당 국면은 신뢰구간 경고와 함께 별도 표기.
4. 상위 후보에 **DSR 게이트**: `deflated_sharpe_ratio(sharpe, n_trials=그리드크기, n_observations,
   skew, excess_kurt)`. **DSR > 0.5**(베스트가 우연 이상일 확률 과반) 통과만 채택. 미통과 시 "그리드에서
   유의한 개선 없음 → 기존값 유지" 판정.
5. 통과 베스트 → **test(OOS)** 구간 성과 기록.

---

## 8. 병렬 실행 · RAM 64GB 활용

- **전략 4개 = 독립 프로세스 4개 동시 기동**(공유 상태 없음, DB는 SELECT 전용이라 안전). 직원 4명에 전략 1개씩 위임.
- 각 프로세스 내부 **`n_jobs`로 (조합 × 종목 × 폴드) 멀티프로세싱**. 4프로세스 × n_jobs=4 = 16 논리코어.
- **RAM 활용**:
  - **일봉 메모리 상주**: 프로세스 시작 시 유니버스 50종목 일봉을 DB에서 **1회 로드해 dict로 상주**.
    모든 그리드 조합·워크포워드 폴드가 재로드 없이 공유 → DB I/O를 폴드 루프에서 제거.
  - 메모리 압박이 없으므로 `n_jobs`를 보수적으로 깎을 필요 없음(필요 시 16까지 상향 가능).
  - 그리드 결과(폴드별 metric)는 in-memory 누적 후 종료 시 parquet flush.

---

## 9. 산출물 (`reports/exit_optimization/`)

- `{전략}_walkforward.md` — 폴드별 train 베스트 / **OOS 성과** / **파라미터 안정성**
  (폴드 간 베스트가 들쭉날쭉 = 과최적화 신호로 명시 경고).
- `{전략}_grid.parquet` — 전체 그리드 raw 결과(조합 × 폴드 × 국면 metric).
- `summary.md` — 4전략 종합 + **최종 권장 청산 파라미터**(OOS 강건한 것만) + **"기존값 대비 개선/유지" 판정표**.
- `memory/changelog-2026-05-31-exit-param-multiverse.md` — 작업 일지(프로젝트 컨벤션).

> 본 작업의 산출은 **권고안**까지다. `config/trading_config.json`/전략 `config.yaml`의 실제 파라미터
> 교체는 **별도 사장님 승인** 후 진행한다(자동 반영 금지).

---

## 10. 검증 · 동등성

- **동등성 회귀(필수)**: 신규 시뮬레이터에 `--mode per-stock` 옵션을 두어 자금제약을 끄고 돌렸을 때
  기존 헤드라인 Sharpe(elder ema_pullback A ≈ 1.22 등)를 **재현**하는지 회귀 테스트.
  재현되면 "진입/청산 로직을 정확히 이식했다"는 증거.
- **포트폴리오 시뮬레이터 단위 테스트**: 자금 소진 스킵 / 슬롯 만석 스킵 / 우선순위 체결 / 다음날 시가 체결 /
  룩어헤드 없음.
- **국면 라벨러**: 기존 `classify_regime_rolling` 그대로 재사용(기존 테스트 커버).
- **최종 채택 기준**: train 성과가 아니라 **OOS 성과 + DSR 통과**. 둘 다 만족 못하면 기존값 유지.

---

## 11. 비목표 (Out of Scope)

- 진입 룰/임계값 최적화(범위 결정 #1에서 제외).
- 4전략 간 **자금배분 비중**(30/20/25/25) 최적화 — 별도 후속 가능.
- composable 패러다임으로의 전략 포팅.
- `trading_config.json` 실파라미터 자동 교체(권고안만 산출, 반영은 별도 승인).

---

## 12. 리스크 · 주의

| 리스크 | 대응 |
|---|---|
| 청산 로직 이식 오류로 기존과 다른 결과 | `--mode per-stock` 동등성 회귀로 1.22 등 재현 확인 후에만 진행 |
| 국면별 표본 과소(특히 BEAR) → Sharpe 불안정 | 거래 수 임계 미만 국면은 경고 표기, 국면최악 판정 시 신뢰구간 병기 |
| 그리드 확대 → DSR 페널티·연산 폭증 | 그리드 절제(전략당 ~27~54조합), DSR n_trials에 실제 조합수 정직 반영 |
| 폴드 간 베스트 불안정 = 과최적화 | OOS 안정성을 1급 판정기준으로, summary에 명시 |
| 미세 개선을 유의미로 착각 | DSR>0.5 게이트 + "기존값 유지" 기본값(default to no-change) |
