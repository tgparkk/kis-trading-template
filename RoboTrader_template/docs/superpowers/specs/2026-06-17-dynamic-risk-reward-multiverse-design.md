# 동적 손익비 멀티버스 — 설계 (Spec)

- **날짜**: 2026-06-17
- **상태**: 설계 승인됨 (구현 plan 대기)
- **목적**: 전략별 기준값(박스권/변동성)으로 손익비(risk-reward ratio)를 동적으로 산출하고, 고정 손익비 대비 강건하게 우월한 조합이 있는지 **측정 전용**으로 검증한다.
- **스코프 결정** (브레인스토밍 합의):
  - 1차 목적 = **측정 전용 연구** (라이브 배선은 승자 확정 후 별도 결정)
  - 기준값 = **메뉴를 멀티버스로 비교** (box / atr / bollinger vs 고정 baseline)
  - 대상 = **활성 8전략 전체**
  - 합격 = **OOS 강건성 게이트** (strategy_gate 재사용)

---

## 1. 배경 & 문제

현재 8개 활성 전략은 모두 **고정 손익비**를 쓴다. 각 `config.yaml`의 `risk` 블록 값을 init 시점에 상수로 읽어 청산에 그대로 사용한다(ATR·변동성·국면 기반 일일 재산정 없음).

| 전략 | SL | TP | max_hold | 트레일 |
|---|---|---|---|---|
| elder_ema_pullback | 8% | 30% | 100 | EMA13 |
| minervini_volume_dryup | 8% | 12% | 20 | 없음 |
| deep_mr_dev20 | 7% | 12% | 7 | MA회복 |
| daytrading_3methods_breakout | 10% | 10% | 10 | 없음 |
| rs_leader | 8% | 15% | 30 | MA20 이탈 |
| book_envelope_200d | 8% | 10% | 10 | 없음 |
| book_pullback_ma20 | 8% | 10% | 50 | MA20 |
| book_pullback_ma5 | 3% | 15% | 30 | MA5 |

**가설**: 종목별 구조(박스권 폭)·변동성에 손익비를 맞추면, 고정 손익비보다 위험조정수익이 개선될 수 있다. 단, 이 프로젝트의 반복된 교훈은 **"임계값 튜닝 = 과적합"**이므로, 인샘플 베스트가 아니라 **OOS 강건성**으로만 승자를 판정한다.

---

## 2. 아키텍처

기존 발굴 파이프라인(`strategy_gate` + `discovery/exit_adapters` + `book_param_multiverse.run_portfolio`) 위에 **per-trade 동적 손익비 레이어**를 얹는다. 진입 로직은 불변, **청산의 sl/tp만 진입 시점에 종목별로 산출**한다.

```
[8전략 진입신호]  →  [ReferenceValueProvider: 진입봉 PIT 기준값]
                          ↓
                   [DynamicRiskResolver: 기준값 × 배수 → per-trade (sl_pct, tp_pct)]
                          ↓ position["sl_pct"/"tp_pct"]
                   [run_portfolio + exit adapter (position 우선 → 없으면 고정 params)]
                          ↓ trades / equity
                   [metrics → OOS 강건성 게이트 → 고정 베이스라인 대비 ΔSharpe]
                          ↓
                   [reports/discovery/dynamic_rr/*.tsv + _DYNAMIC_RR_SUMMARY.md]
```

### 2.1 신규 유닛 (단일 책임·독립 테스트 가능)

| 유닛 | 입력 | 출력 | 책임 |
|---|---|---|---|
| `ReferenceValueProvider` | `df[:i+1]`, ref_type, lookback_n | `ref` 스칼라 | 진입봉에서 박스권높이/ATR/볼린저폭을 **PIT로 계산** (룩어헤드 0). ref_type별 분기 |
| `DynamicRiskResolver` | `ref`, entry_price, sl_mult, RR, floors | `(sl_pct, tp_pct)` 또는 INVALID | 기준값×배수 → per-trade % 변환, 클램프, RR 보존 |
| `dynamic_rr_multiverse.py` | 전략·그리드 | tsv/md | 오케스트레이터: 전략별 그리드 실행·베이스라인 대비·게이트 적용·출력 |

### 2.2 기존 코드 변경 (최소·하위호환)

- `exit_adapters.py` + `run_portfolio`/`_simulate_daily`: 청산이 `params["stop_loss_pct"]`를 직접 읽던 것을 헬퍼 `_eff_sl(position, params)` = `position.get("sl_pct", params["stop_loss_pct"])` (tp도 동일)로 교체.
  - **position에 sl_pct 없으면 = 기존 고정 동작 바이트동일** → 베이스라인 보존 → ΔSharpe 비교 유효.
- 진입부 `position = {...}`: 동적 resolver가 설정됐을 때만 `position["sl_pct"/"tp_pct"]` 기록.

### 2.3 핵심 불변식

- **No-lookahead**: 기준값은 `df.iloc[:i+1]`(진입판정봉 ≤ i, 체결 i+1 시가)만 사용.
- **데이터 SSOT**: quant `daily_prices`, **adj_factor 곱 금지** (메모리 정책).
- **비용반영**: 기존 commission(0.00015)·tax(0.0018)·slippage(0.001) 내장 + 게이트 cost_slippage 0.003 스트레스.

---

## 3. 기준값 정의 & 멀티버스 그리드

손익비를 직접 모수화: **SL은 기준값에서 산출 → TP = RR × SL**. (독립 sl/tp 2축보다 그리드가 작아 과적합 감소, "손익비" 의도와 직결.)

### 3.1 기준값 타입 (ref_type) — 전부 진입봉 i PIT

**1. `box` (박스권 구조레벨) — 1순위**
```
box_high   = max(high[i-N+1 : i+1])
box_low    = min(low[i-N+1 : i+1])
box_height = box_high - box_low
SL_level   = box_low × (1 - buffer)         → sl_pct = (entry - SL_level)/entry   (지지 아래)
TP         = entry + box_height × RR         → tp_pct = box_height × RR / entry   (측정된 움직임)
```
v1의 "박스"는 **N일 고저 레인지**로 근사 (횡보 consolidation 패턴 감지는 v2, YAGNI).

**2. `atr` (변동성 배수)**
```
atr_n  = ATR(N) at i
sl_pct = sl_mult × atr_n / entry,    tp_pct = RR × sl_pct
```

**3. `bollinger` (밴드폭 변동성)**
```
bb_width = 2 × k × std(close[N]) at i      (k=2 기본)
sl_pct   = sl_mult × bb_width / entry,    tp_pct = RR × sl_pct
```

**4. `fixed` (베이스라인)** = 각 전략의 현재 라이브 sl/tp/max_hold 그대로.

> **★RR 의미 차이 (의도적·명시)**: `box`는 구조 기반이라 **RR = 측정된 움직임 배수**(tp = box_height×RR, SL은 box_low 구조레벨에서 독립 산출). `atr`/`bollinger`는 **RR = 손익비**(tp_pct = RR×sl_pct). 즉 box에서 RR은 손익비와 직결되지 않는다. 셀 간 비교를 위해 **실현 손익비 = tp_pct/sl_pct 를 파생 컬럼으로 항상 출력**한다. (대안: box도 tp=RR×sl 통일 — 측정 후 v2 검토.)

### 3.2 그리드 축 (의도적 거친 격자 — 과적합 방지)

| 축 | 값 | 비고 |
|---|---|---|
| ref_type | fixed / box / atr / bollinger | 비교 기준 |
| lookback_n | 10, 20 | 박스·변동성 창 |
| sl_mult | 1.0, 1.5, 2.0 | 기준값→SL 스케일 (box buffer 0 / 0.5%) |
| **RR (손익비)** | 1.0, 1.5, 2.0, 3.0 | tp = RR × sl |
| max_hold | **전략 현재값 고정** | 손익비 효과만 격리 (스윕 안 함) |

→ 전략당 ≈ 3 ref × 2 lookback × 3 sl_mult × 4 RR = **72셀 + 베이스라인**, × 8전략 ≈ **580런**.

### 3.3 Resolver 클램프 (라이브 정합·이상치 가드)

| 클램프 | 값 | 근거 |
|---|---|---|
| SL 하한 | 3% | 라이브 옵션 D-A (손절 하한 −3%) |
| SL 상한 | 15% | 현재 라이브 최대 SL=daytrading 10%에 헤드룸 |
| TP 하한 | = SL | RR ≥ 1 보장 |
| TP 상한 | 30% | 현재 라이브 최대 TP=elder 30% 보존 |

- **실현 tp_pct 가 TP 상한(30%) 초과 시 → 해당 그리드 셀 INVALID 처리** (TP 클립 아님 — RR/측정움직임을 정확히 보존, 측정 깨끗). box·atr·bollinger 공통 적용.
- 기준값 NaN/0폭(워밍업 부족·횡보) → 그 거래는 **고정값 fallback** + fallback 카운트 로깅.

---

## 4. 평가 · 게이트 · 베이스라인 대비

### 4.1 비교 구조 (전략별)
```
베이스라인 = 현재 라이브 고정 sl/tp/max_hold  →  run_portfolio  →  metrics_base
각 동적 셀 = ref×lookback×sl_mult×RR          →  run_portfolio  →  metrics_cell
비교 = ΔSharpe = Sharpe(cell) − Sharpe(base),  ΔCAGR,  ΔMDD,  Δ승률
```

### 4.2 합격 게이트 (OOS 강건성 — strategy_gate 로직 재사용·각색)

| 게이트 | 조건 | 출처 |
|---|---|---|
| **OOS 홀드아웃** | train(2021~2024.6) **AND** test(2024.7~2026.5) **둘 다** ΔSharpe>0 + 절대 Sharpe>0 | 메모리 train/test 분할 |
| **부트스트랩** | 거래 pnl 블록 부트스트랩, ΔSharpe p05 > 0 | strategy_gate G4 |
| **비용반영** | 비용 내장 + cost_slippage 0.003 스트레스 후에도 ΔSharpe>0 | G6 |
| **거래 충분성** | 동적 셀 거래수 ≥ 30 — 소표본 우연 배제 | G2 |

→ **승자 = 4관문 전부 통과한 셀.** 평균적으로 몇 셀만 살아남아도 그게 진짜 엣지.

### 4.3 안전장치 (과적합 가드 — 메모리 교훈 반영)

- **In-sample 체리피킹 금지**: 전체 그리드를 출력하되, **train만 좋고 test 음수인 셀은 "false positive" 라벨**.
- **베이스라인 바이트동일 보존**: ref_type=fixed 셀은 position에 sl_pct 미기록 → 기존 고정 청산과 동일 → **fixed 셀 ΔSharpe == 0 자기참조 스모크 테스트**로 검증.
- **per-strategy 결론**: 전략마다 "동적 손익비가 고정을 강건하게 이겼는가? 이겼다면 어느 ref_type/RR?" 표. 한 개도 못 이기면 그것도 정당한 결과(고정이 이미 충분).

### 4.4 산출물

- `reports/discovery/dynamic_rr/<strategy>_grid.tsv` — 전 셀 metrics + 게이트 통과여부
- `reports/discovery/_DYNAMIC_RR_SUMMARY.md` — 전략별 승자/판정 (verifier가 TSV 대조)

---

## 5. 테스트 전략 (TDD)

| 대상 | 핵심 테스트 |
|---|---|
| `ReferenceValueProvider` | box/atr/bollinger **PIT 정확성**(i값이 ≤i 봉만 사용), 고정 픽스처 수치, 워밍업부족·0폭 NaN 처리 |
| `DynamicRiskResolver` | 클램프(SL 3~15%, TP≤30%), RR×SL>30% → 셀 INVALID, RR 보존 |
| 어댑터 변경 | position 우선 분기 / **fallback 바이트동일**(베이스라인 보존 — 최우선) |
| 오케스트레이터 | **fixed셀 ΔSharpe==0 자기참조 스모크**, 그리드 열거, 게이트 배선 |
| 회귀 | 기존 discovery/gate 테스트 green 유지 |

---

## 6. 구현 단위 (파일 분해)

```
신규:  scripts/discovery/reference_values.py     (ReferenceValueProvider + box/atr/bollinger)
신규:  scripts/discovery/dynamic_risk.py          (DynamicRiskResolver)
신규:  scripts/dynamic_rr_multiverse.py           (오케스트레이터: 전략별 그리드·베이스라인·게이트·출력)
수정:  scripts/discovery/exit_adapters.py          (_eff_sl/_eff_tp 헬퍼)
수정:  scripts/book_param_multiverse.py            (run_portfolio/_simulate_daily: 진입시 동적 sl/tp 주입)
재사용: strategy_gate(evaluate_gates·bootstrap·sharpe), _daily_metrics
신규:  tests/discovery/test_reference_values.py
신규:  tests/discovery/test_dynamic_risk.py
신규:  tests/discovery/test_dynamic_rr_exit_injection.py
신규:  tests/discovery/test_dynamic_rr_smoke.py
```

---

## 7. 리스크 (착수 전 인지)

1. **★최대 리스크 — 8전략 진입신호 소싱**: 동적 청산은 진입 불변·sl/tp만 변경이라, **8전략 각각의 진입 신호를 백테스트에서 재현**해야 한다. deep_mr 등 일부는 discovery rule_fn 보유, 나머지는 `strategy.generate_signal` 경로 필요.
   → **구현 1번 태스크 = 8전략 진입신호 어댑터 가용성 점검**. 재현 불가 전략은 v1에서 제외하고 SUMMARY에 명시.
2. **청산 충실도**: 동적 레이어가 기존 청산 의미를 훼손하면 안 됨 → 바이트동일 베이스라인 테스트로 방어.
3. **박스 정의 단순화**: v1은 "N일 고저 레인지" 근사. 횡보 패턴 감지는 v2.
4. **연산량**: ~580런 × 풀기간 — 전략별 병렬 권장.

---

## 8. 범위 밖 (YAGNI)

- 라이브 배선 (Signal/BaseStrategy 동적 sl/tp) — 측정 후 별도 결정
- 분봉 동적 손익비
- 횡보박스 consolidation 패턴 감지
- max_hold 동적화
