# Weinstein Stage Analysis — 백테스트 설계서 (Phase 2)

> Book: Stan Weinstein — *Secrets for Profiting in Bull and Bear Markets* (McGraw-Hill, 1988)
> 조사 노트: [reports/books_research/weinstein_stages/research.md](../../../reports/books_research/weinstein_stages/research.md)
> 작성일: 2026-05-29
> 사장님 결정: **주봉 인프라 신규 구축 후 진행** (daily_prices 224일 → 주봉 ~32주, MA30 검증 한계 명시한 채 책 의도 그대로 구현)

---

## 0. 메타

| 항목 | 값 |
|---|---|
| Book ID | `weinstein_stages` |
| 기반 책 | Weinstein (1988) — Stage Analysis (4 Stage / 30W MA / Mansfield RS) |
| 데이터 단위 | **주봉(weekly)** 기본 + 일봉 보조 (일봉 데이터에서 자체 집계) |
| 데이터 한계 | daily_prices 2025-07-01 ~ 2026-05-29 = 224 거래일 → 주봉 약 32주. MA30(주) 검증 표본 ≤ 2주 (사실상 단발성), MA10(주)는 약 22주 검증 가능 |
| 국면 | 단일 BULL 구간 편향 (Minervini와 동일 한계) |
| 사장님 결정 인용 | 2026-05-29: "주봉 인프라 신규 구축 후 진행" |

---

## 1. 데이터 인프라

### 1a. 주봉 집계 헬퍼 (신규 구현)

**위치**: `RoboTrader_template/strategies/books/weinstein_stages/weekly.py` (책 전용 모듈로 격리. 다른 책에서 재사용 시 `strategies/books/_weekly_utils.py`로 승격하되 Phase 2에선 책 내부에 둠)

```python
# strategies/books/weinstein_stages/weekly.py
import pandas as pd

def resample_daily_to_weekly(
    daily_df: pd.DataFrame,
    min_days_per_week: int = 3,
) -> pd.DataFrame:
    """
    Input columns: datetime(or date), open, high, low, close, volume
                   (run_minervini_vcp._load_daily_adj 출력과 동일 스키마)
    Output: weekly_df with same columns + 'n_days' (해당 주의 거래일 수)

    규칙:
      - 주 마감: ISO 주(월~일) 기준 'W-FRI' (한국 영업일 기준 그 주의 마지막 거래일)
      - open  = 그 주 첫 거래일 open
      - high  = max(high)
      - low   = min(low)
      - close = 그 주 마지막 거래일 close
      - volume = sum(volume)
      - n_days = 그 주에 데이터가 있는 거래일 수
      - n_days < min_days_per_week 인 주는 dropna (공휴일 다발 주 제외)
      - datetime = 그 주의 마지막 거래일 datetime (W-FRI resample의 right label이 아닌 실제 마지막 거래일)
    """
```

**확정 사항** (research.md 부록 미결 1)
- 주 마감 기준: **`W-FRI`** (월~금 한국 영업일, 마지막 거래일이 금요일이 아니어도 그 주의 마지막 거래일로 라벨)
- 공휴일 처리: pandas resample에 한국 공휴일 캘린더 명시 사용하지 않음 — 단순 그루핑 후 빈 주는 자동 제외
- 거래일 < 3일 주: dropna (반쪽짜리 표본 배제). 임계값 3은 추후 데이터 누적 후 재검토

### 1b. 시장 지수 (Mansfield RS용)

**현실 확인 결과** (2026-05-29 SELECT 실행):
- daily_prices에 KOSPI(KS11/^KS11/0001/KOSPI) / KODEX200(069500) / TIGER200(102110) / KODEX코스닥150(229200) / 226490 / 069660 등 **단 하나도 존재하지 않음** (rows=0)
- → KOSPI 지수 적재 + 인프라 추가 작업은 Phase 2 본 plan 범위를 벗어남

**권장안 (확정)**: **universe 동일가중 인덱스 (Mansfield RS 변형 + universe 백분위 병행)**
- 사유:
  1. daily_prices에 지수 부재 → 외부 데이터 로드 작업이 새 Phase로 분리되어야 함
  2. Minervini `compute_rs_percentile_12w`이 이미 universe 백분위 방식으로 운영 중 — 일관성 유지
  3. universe top_volume:50은 대형주 중심이라 KOSPI 프록시로 합리적 (대형주 동일가중 ≈ 시총가중 KOSPI 와 상관 0.85+ 추정)
- 구현:
  - `_build_universe_market_index(wide_close)` → universe 일봉 종가의 횡단면 평균 → 일봉 시리즈 → 주봉 resample → market_weekly_close
  - Mansfield RS 식 그대로 적용 (다만 index 자리에 universe 평균이 들어감)

**기각된 대안**:
- (a) KOSPI 지수 적재: 데이터 적재 작업이 별도 Phase로 분리되어야 해서 Phase 2~3 범위 초과
- (c) Minervini RS 백분위 (12주) 그대로: research.md에서 "Mansfield RS 원본 구현"을 명시 권장했으므로 Mansfield 식 자체는 유지하되 지수만 universe로 대체. 단, **백분위 RS도 보조 신호로 함께 계산**해 두 방식 비교 분석 가능하게 함

### 1c. 데이터 로드 재사용 / 신규

| 기능 | 재사용 vs 신규 | 위치 |
|---|---|---|
| `_load_top_volume_universe(start, end, top_n)` | **재사용** | `scripts/run_minervini_vcp.py` 참조 — Weinstein script로 복사 또는 import |
| `_load_daily_adj(codes, start, end)` (adj_factor 적용) | **재사용** | 동상 |
| `_build_universe_close(data)` (wide DataFrame) | **재사용** | 동상 |
| `resample_daily_to_weekly(daily_df)` | **신규** | `strategies/books/weinstein_stages/weekly.py` |
| `_build_universe_market_index(wide_close)` (universe 동일가중) | **신규** | `scripts/run_weinstein_stages.py` 내부 또는 weekly.py |
| `compute_mansfield_rs(stock_weekly, market_weekly, n)` | **신규** | `strategies/books/weinstein_stages/rules.py` |
| `compute_rs_percentile_12w` (보조) | **재사용** | `strategies/books/minervini_vcp/rules.py` 에서 import |

---

## 2. 룰 함수 명세 (rules.py)

**위치**: `RoboTrader_template/strategies/books/weinstein_stages/rules.py`

모든 룰은 **주봉 DataFrame**을 입력으로 받는다. `BookStrategy.generate_signal_with_extra_ctx`에 일봉이 들어오므로, strategy.py가 일봉→주봉 변환 후 룰에 전달하는 패턴을 사용한다 (3장 참조).

### 2a. 보조 헬퍼

#### `compute_ma30w_slope(weekly_close: pd.Series, lookback: int = 4) -> float`
- 정의: `(MA30(t) - MA30(t - lookback)) / MA30(t - lookback)`
- 단위: 비율 (예: 0.005 = +0.5%/4주)
- 출처: research.md §3 — axlfi.com 인용
- **확정**(research.md 부록 미결 1): 임계값 ±0.001 (0.1%/4주)
  - `slope > +0.001` → 상승
  - `|slope| ≤ 0.001` → 평탄
  - `slope < -0.001` → 하락
- 추후 재검토: 데이터 누적 후 임계값 grid search 가능

#### `compute_mansfield_rs(stock_weekly_close: pd.Series, market_weekly_close: pd.Series, n: int = 26) -> pd.Series`
- 식 (research.md §4 stageanalysis.net 원본):
  ```
  RP(t)  = (stock(t) / market(t)) * 100
  MRS(t) = (RP(t) / SMA(RP, n) - 1) * 100
  ```
- **확정**(research.md 부록 미결 3): `n = 26` (주봉)
  - 원본은 52주. 데이터 32주 → 52 사용 불가. n=26으로 축소하면 26주 warmup 후 ~6주 검증 가능. 비현실적이지만 책 의도 보존
  - 사장님 결정 "주봉 인프라 신규 구축" 명시 사항 반영
  - 추후 재검토: 데이터 1년+ 누적 후 n=52로 복귀

#### `stage_classifier(price: float, ma30w: float, ma30w_slope_pct: float, mansfield_rs: float) -> Literal[1,2,3,4]`
- 분류 표 (research.md §2):

| Stage | 가격 vs MA30W | MA30W 기울기 | Mansfield RS |
|---|---|---|---|
| 1 (Basing) | 혼재 (price ≈ ma30w ±5%) | 평탄 (`|slope|≤0.001`) | < 0 또는 0 근처 |
| 2 (Advancing) | price > ma30w | slope > +0.001 | ≥ 0 |
| 3 (Top) | 혼재 (price ≈ ma30w ±5%) | 평탄 (`|slope|≤0.001`) | 하락 전환 (slope_rs < 0) |
| 4 (Declining) | price < ma30w | slope < -0.001 | < 0 |

- Stage 1과 3 구분: 직전 4주 stage 이력으로 판단. 직전이 Stage 4였으면 1, Stage 2였으면 3
- Stage 2와 4는 가격·기울기로 단일 결정
- 우선순위(애매한 경우): (1) MA30W 기울기 → (2) 가격 위치 → (3) Mansfield RS

### 2b. 핵심 룰 3개 (Phase 2 코드화 대상)

#### `rule_stage2_initial_breakout`
- **의미**: Stage 1 → Stage 2 전환 돌파 (research.md §5.A)
- **반환**: `RuleResult(triggered, side="buy", confidence=72.0, ...)`

| 조건 | 정량식 | 출처 |
|---|---|---|
| 1. Stage 전환 | 직전 주 stage == 1 AND 현재 주 stage == 2 | research.md §5.A |
| 2. 가격 > MA30W | `weekly_close[-1] > ma30w[-1]` | 책 본문 |
| 3. 박스 저항선 돌파 | `weekly_close[-1] > rolling_max(weekly_close, 16).iloc[-2]` | **확정**(미결 4): 박스 기간 = 16주 (research.md §5.A "150일 = 약 30주"는 일봉 표현. 주봉으로 16주는 ≈ 80일, Stage 1 베이스 평균 길이의 보수적 추정) |
| 4. 거래량 돌파 | `weekly_volume[-1] > rolling_mean(weekly_volume, 4).iloc[-2] * 1.5` | **확정**(미결 6): 배수 = 1.5 (research.md 후보 1.5~2.0 중 보수적 1.5 채택. 표본 부족 시 통과율을 확보) |
| 5. Mansfield RS ≥ 0 | `mansfield_rs[-1] >= 0` | research.md §4 |

- **t-1 종가 기준**: 위 모든 비교는 `weekly_close.iloc[-1]` (당주 종가) 기준. 진입은 다음 주 시가 (백테스트에서 `bar_next['open']`)
- **No-lookahead 보장**: 박스 저항선·평균 거래량은 `iloc[-2]` (당주 제외 직전까지) 기준 → 당주 자체가 돌파한 봉이므로 비교 시점이 맞음

#### `rule_stage2_continuation_pullback`
- **의미**: Stage 2 진행 중 MA30W 5% 이내 되돌림 후 회복 (research.md §5.B)

| 조건 | 정량식 |
|---|---|
| 1. 현재 Stage 2 | `stage_classifier(...)[-1] == 2` AND 직전 4주 모두 Stage 2 |
| 2. MA30W 5% 이내 되돌림 | `min((weekly_close[-4:] - ma30w[-4:]) / ma30w[-4:]) < 0.05` (지난 4주 중 한 번이라도 MA30W 5% 이내 접근) **확정**(미결 5): 범위 = 5% |
| 3. 회복 (재돌파) | `weekly_close[-1] > max(weekly_high[-5:-1])` (지난 4주 swing high 재돌파) |
| 4. 회복 시 거래량 | `weekly_volume[-1] > rolling_mean(weekly_volume, 4).iloc[-2] * 1.0` (기준치 이상 — pullback 룰은 1.5배 강제 아님) |
| 5. Mansfield RS ≥ 0 | `mansfield_rs[-1] >= 0` |

- **confidence**: 68.0 (initial_breakout 72보다 약간 낮음 — 재진입 셋업의 통계적 신뢰도 보수 추정)

#### `rule_ma30w_bounce`
- **의미**: Stage 2 중 MA30W 단순 반등 — research.md 셋업 #6 (pullback의 단순화 버전, swing high 조건 완화)

| 조건 | 정량식 |
|---|---|
| 1. 현재 Stage 2 | `stage_classifier(...)[-1] == 2` |
| 2. MA30W 터치 후 양봉 회복 | `weekly_low[-1] <= ma30w[-1] * 1.03` AND `weekly_close[-1] > weekly_open[-1]` (당주 저점이 MA30W 3% 이내까지 내려갔다가 양봉 마감) |
| 3. Mansfield RS ≥ 0 | `mansfield_rs[-1] >= 0` |

- **confidence**: 60.0 (가장 느슨한 셋업)
- pullback과 차이: swing high 재돌파 조건 없음, MA 접근만으로 진입

### 2c. ALL_RULES 정의

```python
ALL_RULES = [
    rule_stage2_initial_breakout,
    rule_stage2_continuation_pullback,
    rule_ma30w_bounce,
]
```

`build_strategy(mode, target_rule, or_members)` 시그니처는 Minervini와 동일.

### 2d. research.md 미결 7개 항목 — 본 설계서 확정 현황

| # | 항목 | 본 설계서 확정값 | 위치 |
|---|---|---|---|
| 1 | MA30W 기울기 임계값 | ±0.001 (0.1%/4주) | §2a |
| 2 | Mansfield RS 대체지수 | universe 동일가중 인덱스 | §1b |
| 3 | Mansfield RS n 파라미터 | 26 (주봉) | §2a |
| 4 | Stage 1 박스 저항선 기간 | 16주 | §2b rule_stage2_initial_breakout |
| 5 | Continuation pullback 범위 | 5% (MA30W 이내) | §2b rule_stage2_continuation_pullback |
| 6 | 돌파 거래량 배수 | 1.5배 (4주 평균 대비) | §2b rule_stage2_initial_breakout |
| 7 | warmup 전략 | Variant A: 56주 / Light: 18주 — Variant Light 신규 추가 | §3, §4 |

**확정 7/7 (100%)**. 모든 임시 확정값에 "추후 데이터 누적 후 재검토" 코멘트를 코드 주석으로 부착할 것 (Phase 3 executor 지시사항).

---

## 3. 청산 룰

### Variant A (책 의도 — Stage 추세 추종)

| 항목 | 값 | 근거 |
|---|---|---|
| sl | 0.08 | Weinstein(1988) "stop just below the breakout level", research.md §6 |
| tp | 0.30 | 장기 추세 추종 (Weinstein은 명시적 tp 없음 → Stage 3 진입까지 보유 의도 해석) |
| trail | 주 종가 < MA30W 시 청산 | Weinstein "raise stops to just below the 30-week MA" |
| mh | 20주 (≈ 100거래일) | research.md §6 |
| 데이터 단위 | 주봉 | — |

### Variant B (책간 획일 — 일봉)

| 항목 | 값 | 근거 |
|---|---|---|
| sl | 0.08 | Minervini와 통일 |
| tp | 0.12 | 동상 |
| trail | 없음 | — |
| mh | 20거래일 | — |
| 데이터 단위 | 일봉 | — |

### Variant Light (데이터 한계 대응 — 신규)

| 항목 | 값 | 근거 |
|---|---|---|
| sl | 0.08 | — |
| tp | 0.20 | A와 B의 중간 |
| trail | 주 종가 < MA10W 시 청산 | Weinstein의 MA30W 의도를 짧은 MA로 근사 |
| mh | 10주 (≈ 50거래일) | — |
| 데이터 단위 | 주봉 | — |

**Variant Light 도입 사유**:
- Variant A는 warmup 30주 + Mansfield RS 26주 = 56주 필요 → 데이터 32주에선 검증 불가
- Variant Light는 MA10(주) + RS 8주로 축소해 warmup 18주 → 약 14주 검증 가능
- "Weinstein 의도 완전 구현 불가 시 표본 확보용"이며, **본 Variant 결과는 책 평가가 아닌 인프라 동작 검증용**임을 리포트에 명시

### 3a. trail_ma_weekly 청산 로직 (구현 주의)

Minervini `simulate_one_stock`의 `trail_ma`는 일봉 N봉 SMA. Weinstein은 **주봉 MA30(W) 이탈**이 트리거.
구현 방법:
- 옵션 (a) 주봉 시뮬레이션 (권장): 일봉 데이터를 주봉으로 변환 후 주봉 단위로 시뮬. `trail_ma=30` 의미가 자연스럽게 30주.
- 옵션 (b) 일봉 시뮬에 주봉 MA를 매핑: 매 일봉에 그 주의 MA30W를 broadcast → 종가 < MA30W 체크. 구현 복잡, 청산 타이밍 일봉 단위로 빨라짐.

**확정**: 옵션 (a) — 주봉 시뮬을 기본으로 한다. Variant B만 일봉 시뮬.

---

## 4. 백테스트 시뮬레이션 파이프라인

### 4a. 공통 파라미터 (Minervini와 일관)

| 항목 | 값 |
|---|---|
| universe | `top_volume:50` |
| 기간 | 3개: 2025-10 / 2026-04 / 2026-05 (Minervini index와 동일) — 단 주봉 셋업은 단일 full-period(2025-07-01 ~ 2026-05-29) 권장 |
| 슬리피지 | 0.001 (단방향 0.1%) |
| 수수료 | 0.00015 (매매 양방향) |
| 거래세 | 0.0018 (매도) |
| 왕복 비용 | ≈ 0.41% |
| no-lookahead | 모든 룰은 t 주 종가 기준 평가 → 진입은 t+1 주 시가 |
| initial_capital | 10_000_000 |

### 4b. warmup_bars (확정 — 미결 7)

- Variant A (주봉): **56주** (MA30(주) 30 + Mansfield RS n=26)
- Variant Light (주봉): **18주** (MA10(주) 10 + RS n=8)
- Variant B (일봉): **60일** (Minervini와 동일)

데이터 224일 / 32주 기준:
- Variant A: warmup 56주 → 검증 가능 ~ -24주 → **표본 0 (확실)**. 사장님 결정대로 진행하되 리포트에 명시 경고.
- Variant Light: warmup 18주 → 검증 가능 ~14주. 표본 1~10건 예상.
- Variant B: warmup 60일 → 검증 가능 ~164일. 표본 충분.

### 4c. `simulate_one_stock` 재사용 분석

| Minervini 구현 부분 | Weinstein 재사용 여부 |
|---|---|
| 신호 발생 후 다음 봉 시가 매수 | **재사용 가능** |
| sl/tp/mh 청산 | **재사용 가능** (변수만 변경) |
| `trail_ma`로 N봉 SMA 이탈 청산 | **재사용 가능** — 단 주봉 입력 시 N=30 → MA30W 자동 |
| 수수료/세금/슬리피지 | **재사용 가능** |
| 강제 마지막 봉 청산 | **재사용 가능** |
| RS 전달 (`ctx_extra={"rs_value": rs}`) | **재사용 가능** — rs_value를 Mansfield RS로 교체 |

**결론**: `simulate_one_stock` 함수 자체는 Weinstein용 script에 **그대로 복사**해 사용. 차이점은:
1. `df`를 주봉 DataFrame으로 전달 (Variant A/Light)
2. `rs_series`를 universe 백분위가 아닌 **Mansfield RS 시리즈**로 전달
3. `warmup_bars`를 56/18/60으로 분기

→ 함수 시그니처 변경 없음. 호출부만 바꿈.

### 4d. 일봉 ↔ 주봉 인덱싱 매핑

- 주봉 시뮬: `df = resample_daily_to_weekly(daily_df)` 후 주봉 인덱스로 시뮬레이션
- 매수가: `weekly_df.iloc[i+1]['open']` → 의미상 "다음 주 첫 거래일 시가" — 실제 일봉의 그 다음 주 월요일 시가에 해당
- 청산가: 동일 룰. 다음 주 시가 청산
- 한계: 주중 sl/tp 트리거가 주봉 종가 기준이라 실제보다 청산이 늦어질 수 있음 — 알려진 한계로 §8에 명시

---

## 5. CLI / 실행

### 5a. 스크립트 신규

**위치**: `RoboTrader_template/scripts/run_weinstein_stages.py`

Minervini의 `run_minervini_vcp.py`를 템플릿으로 복사 후 수정:

```bash
# Variant A (책 의도 — 주봉 56주 warmup, 표본 0 가능)
python scripts/run_weinstein_stages.py --variant A --all-modes

# Variant B (책간 획일 — 일봉)
python scripts/run_weinstein_stages.py --variant B --mode single --rule stage2_initial_breakout

# Variant Light (인프라 검증 + 표본 확보)
python scripts/run_weinstein_stages.py --variant Light --all-modes
```

CLI 옵션:
- `--variant {A, B, Light}` (Minervini는 A/B 2종 → Light 추가)
- `--mode {single, all_AND}` (Minervini와 동일)
- `--rule <name>` (single 모드용)
- `--all-modes` (Minervini와 동일)
- `--limit N` (디버그용)
- `--top-n N` (default=50)
- `--start, --end` (default: daily_prices full range)
- `--reports-dir` (default: `reports/books_research/weinstein_stages`)

### 5b. CLI 옵션 변경 영향 (executor 주의 사항)

- `book_backtester.py` (분봉 기반) **사용 안 함**. Minervini와 동일하게 별도 스크립트.
- `scripts/run_books_research.py` 수정 **불필요**. (분봉 책용으로 유지)

### 5c. VARIANT_PARAMS 추가

```python
VARIANT_PARAMS = {
    "A":     dict(stop_loss_pct=0.08, take_profit_pct=0.30, max_hold_bars=20, trail_ma=30, weekly=True,  warmup=56, rs_n=26),
    "B":     dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20, trail_ma=None, weekly=False, warmup=60, rs_n=None),
    "Light": dict(stop_loss_pct=0.08, take_profit_pct=0.20, max_hold_bars=10, trail_ma=10, weekly=True,  warmup=18, rs_n=8),
}
```

---

## 6. 평가지표 / 출력

### 6a. 지표

- **1급**: PnL, Sharpe (Minervini와 동일)
- **2급**: Calmar, MaxDD, Sortino, Hit Rate, n_trades, avg_hold_bars (주봉이면 주, 일봉이면 일), sells_by_reason
- **Sharpe 연환산**: 주봉이면 `sqrt(52)`, 일봉이면 `sqrt(252)` — Minervini는 일봉 `sqrt(252)`만 사용 중. Weinstein 주봉용 헬퍼 추가 필요

### 6b. 국면 분해 (BULL/BEAR/SIDEWAYS)

- Minervini의 `regime_split_minervini.py` 패턴 그대로 복사 → `scripts/regime_split_weinstein.py`
- 20일 수익률 ±2% 임계 (Minervini와 통일)
- 단일 BULL 구간 편향 한계 명시 (§8)

### 6c. 출력 Parquet

**개별 trade 결과**: `reports/books_research/weinstein_stages/results_variant{A,B,Light}_{single,all_AND}_{rule_name}.parquet`

**리더보드 append**: `reports/books_research/leaderboard.parquet` (책간 공통 — Minervini와 동일 파일에 append)
- 컬럼 `book_id = "weinstein_stages"`로 구분
- 추가 컬럼: `variant`, `weekly` (bool), `rs_n`, `warmup_bars`

**regime breakdown**: `reports/books_research/weinstein_stages/regime_breakdown.parquet`

---

## 7. 가설 / 검증 항목

본 백테스트가 답해야 할 가설:

| # | 가설 | 검증 방식 |
|---|---|---|
| H1 | Mansfield RS ≥ 0 + Stage 2 Initial Breakout 셋업은 단순 MA30W 돌파 단일조건보다 PnL이 높다 | `rule_stage2_initial_breakout` (RS 조건 포함) vs `rule_ma30w_bounce` (RS 조건 포함) Sharpe·PnL 비교 |
| H2 | Stage 2 Continuation Pullback은 Initial Breakout보다 Hit Rate가 높으나 PnL은 낮다 (보수적 셋업 특성) | 두 룰 Hit Rate·PnL 비교 |
| H3 | 주봉 기반(Variant A) 전략은 일봉 기반(Variant B)보다 avg_hold가 길고 매매 수가 적다 | n_trades, avg_hold_bars 비교 (주↔일 단위 환산 후) |
| H4 | universe 동일가중 인덱스 기반 Mansfield RS는 universe 백분위 RS와 동일 종목 진입 결과 ≥ 70% 일치 | rule_stage2_initial_breakout 진입 시점에 두 RS 모두 계산 후 일치율 측정 (보조 분석) |

H1, H2, H3는 결과 리포트에서 Yes/No로 답할 수 있어야 한다. H4는 보조 분석으로 Phase 4 리포트에 부록 추가.

---

## 8. 알려진 한계

| # | 한계 | 영향 |
|---|---|---|
| L1 | 데이터 224일 / 주봉 32주 → Variant A warmup 56주 불가 | Variant A 표본 0건 거의 확실. 리포트에서 "인프라 검증용"으로 위치 |
| L2 | 단일 BULL 구간 편향 (KOSPI 2025-07~2026-05 전체 상승) | BEAR/SIDEWAYS 표본 부족. 국면 분해 결과의 통계적 의미 제한 |
| L3 | Stage 분류기가 정성 표현을 정량화한 근사 | 책 원본은 chart pattern 시각 판단. 본 구현은 규칙 기반 근사 |
| L4 | universe top_volume:50 → 대형주 편향 | Weinstein 책은 중소형주 Stage 2 진입 사례도 다수. universe 다변화는 향후 검토 |
| L5 | universe 동일가중 Mansfield RS는 KOSPI 원본과 다름 | RS 절대값 비교는 무의미. zero line 신호로만 사용 |
| L6 | 주봉 시뮬은 주중 sl/tp 트리거가 늦음 | 실제보다 sl/tp 청산 시점이 평균 2~3일 뒤로 밀림. 보수적 추정값 |
| L7 | 한국 공매도 제약 → Stage 4 셋업 전면 제외 | 책 전체 의도의 50%만 검증. matrix balanced 못함 |

---

## 9. Phase 3 (코드화) 작업 분해

executor에게 전달할 작업 리스트. **예상 LOC**은 Minervini 동등 파일 기준 ±20%.

| # | 작업 | 위치 | 예상 LOC | 의존성 |
|---|---|---|---|---|
| T1 | `weekly.py` — `resample_daily_to_weekly` | `strategies/books/weinstein_stages/weekly.py` | 40 | pandas |
| T2 | `rules.py` — 헬퍼 3개 (`compute_ma30w_slope`, `compute_mansfield_rs`, `stage_classifier`) | `strategies/books/weinstein_stages/rules.py` | 80 | T1, Minervini `compute_rs_percentile_12w` import |
| T3 | `rules.py` — 룰 3개 (`rule_stage2_initial_breakout`, `rule_stage2_continuation_pullback`, `rule_ma30w_bounce`) | 동상 | 200 | T2 |
| T4 | `rules.py` — `ALL_RULES` 상수 | 동상 | 5 | T3 |
| T5 | `strategy.py` — `WeinsteinStagesStrategy` + `build_strategy(mode, target_rule, or_members)` + 일봉→주봉 변환 wrapper | `strategies/books/weinstein_stages/strategy.py` | 80 | T1, T4. **주의**: BookStrategy의 `generate_signal`은 일봉 df를 받는 가정 → Weinstein은 wrapper에서 weekly로 변환 후 룰에 전달 |
| T6 | `__init__.py` | `strategies/books/weinstein_stages/__init__.py` | 10 | — |
| T7 | `scripts/run_weinstein_stages.py` — CLI + simulate_one_stock 복사 + Mansfield RS series 빌드 + `VARIANT_PARAMS = {A, B, Light}` | `scripts/run_weinstein_stages.py` | 350 | T5, Minervini `run_minervini_vcp.py` 패턴 |
| T8 | `scripts/regime_split_weinstein.py` — Minervini regime split 복사 + 출력 경로 변경 | `scripts/regime_split_weinstein.py` | 180 | T7 (선택) |
| T9 | `tests/books/test_weinstein_rules.py` — 룰 단위 테스트 (룰별 trigger/non-trigger 케이스 + Stage classifier 4 분기 + resample weekly 정합성) | `tests/books/test_weinstein_rules.py` | 250 | T1~T5 |
| T10 | 책 인덱스 갱신 (`docs/books/index.md`이 있으면) — Phase 5에서 처리 | `docs/books/index.md` | 5 | 백테스트 결과 |

**총 예상 LOC**: ≈ 1,200 (테스트 250 포함). Minervini 동등(rules 192 + strategy 35 + run script 356 + regime 180 + tests ≈ 200 = ~1,000)보다 약간 큼 — 주봉 변환 + Variant Light 추가분.

### 9a. executor 주의사항

- **모든 임시 확정값에 코드 주석으로 "추후 데이터 누적 후 재검토" 명시** (research.md 미결 7개 모두)
- Minervini 코드 패턴을 최대한 따라 import path / 명명 / decorator 일관성 유지
- t-1 종가 기준 룰 평가, t+1 시가 진입 원칙은 절대 위반 금지
- Variant A 표본 0인 경우 스크립트가 에러 없이 종료해야 함 (`if not data: return`)

---

## 10. 보고 / 사장님 결재 필요 항목

### 10a. Phase 2 → 3 사이 사장님 결재 항목

| # | 항목 | 옵션 | 본 설계서 권장 |
|---|---|---|---|
| Q1 | Variant Light 백테스트 결과를 "책 평가"로 인용할지 "인프라 검증용"으로만 명시할지 | (a) 책 평가 포함 / (b) 인프라 검증용 only | **(b)** 인프라 검증용으로만. Variant A 표본 0이지만 책 의도 완전 구현. Variant B로 책 의도 일부 평가 |
| Q2 | 단일 full-period(224일) vs Minervini와 동일 3개 기간 분해 | (a) full-period only / (b) 3개 기간 모두 / (c) 둘 다 | **(c)** 일관성 유지 위해 둘 다 산출. Variant A는 full-period에서만 의미 있음 |
| Q3 | regime_split (BULL/BEAR/SIDEWAYS 분해) 실행 여부 | (a) 실행 / (b) 생략 | **(a)** 실행. 단일 BULL 한계 명시할 수 있음 |
| Q4 | universe 동일가중 인덱스로 KOSPI를 갈음하는 것에 대한 확인 | (a) 동의 / (b) KOSPI 별도 적재 작업 추가 | **(a)** 동의 (Q4는 Phase 3 시작 전 사장님 확인만 받으면 됨) |

### 10b. Executor 사전 경고: 가장 막힐 가능성 큰 작업 1개

**T5 (`strategy.py` — 일봉→주봉 변환 wrapper)**

이유:
- `BookStrategy.generate_signal_with_extra_ctx(stock_code, data, timeframe, extra)` 시그니처는 일봉을 가정
- Weinstein은 **룰 평가 시점에 주봉이 필요** → wrapper가 매 호출마다 일봉→주봉 변환을 해야 함 (느림)
- 더 효율적: 시뮬레이션 시작 시점에 1회 주봉 변환 후 룰에 직접 주봉 전달. 하지만 이건 `simulate_one_stock` 내부 구조 변경 필요
- 최적 해결: `scripts/run_weinstein_stages.py`의 `simulate_one_stock`을 호출하기 전에 **df를 미리 주봉으로 변환**해서 넘긴다 (Variant A/Light). Variant B는 일봉 그대로
- 즉 일봉 변환 wrapper는 strategy.py에 두지 말고, script 진입 직전에 변환. strategy는 "받은 df가 이미 주봉/일봉 형태"라고 가정
- 단점: `BookStrategy` 베이스의 `timeframe` 인자가 "daily"로 고정돼 있으나 의미상 "weekly" — 일단 "daily" 그대로 사용하되 metadata에 `"granularity": "weekly"` 추가

**Executor에게 명시할 가이드**: T5 작성 전 본 §10b 전문 참조. wrapper 패턴 대신 "사전 변환 + 룰 입력은 주봉으로 가정" 패턴 사용.

---

## 부록 A. 파일 트리 (Phase 3 종료 시점 예상)

```
RoboTrader_template/
├── strategies/books/
│   ├── _base_book_strategy.py        (변경 없음)
│   ├── minervini_vcp/                 (변경 없음)
│   └── weinstein_stages/              ← 신규
│       ├── __init__.py
│       ├── weekly.py                  (T1)
│       ├── rules.py                   (T2, T3, T4)
│       └── strategy.py                (T5)
├── scripts/
│   ├── run_minervini_vcp.py           (변경 없음 — 참조용)
│   ├── regime_split_minervini.py      (변경 없음 — 참조용)
│   ├── run_weinstein_stages.py        ← 신규 (T7)
│   └── regime_split_weinstein.py      ← 신규 (T8)
├── tests/books/
│   └── test_weinstein_rules.py        ← 신규 (T9)
├── docs/superpowers/specs/
│   └── 2026-05-29-weinstein-stages-design.md    ← 본 문서
└── reports/books_research/
    ├── leaderboard.parquet            (책간 공통 — append)
    └── weinstein_stages/              ← 신규 디렉토리 (Phase 4에서 결과 저장)
        ├── results_variantA_*.parquet
        ├── results_variantB_*.parquet
        ├── results_variantLight_*.parquet
        └── regime_breakdown.parquet
```

---

**작성 완료**: 2026-05-29
**다음 단계**: 사장님 §10a Q1~Q4 결재 → Phase 3 코드화 (T1~T9, 예상 ~1,200 LOC)
