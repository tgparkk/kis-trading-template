# 시장 국면(Market Regime) 판별 방법 — 전문가 조사·권고

> 작성: 2026-06-02 · 범위: KOSPI/KOSDAQ 일봉 · 목적: 책 전략 백테스트의 국면 분해 + "국면 게이트" 진입 필터
> **★절대조건: No Look-Ahead** — T 시점 국면은 T 이전(≤T) 데이터로만 결정.

---

## 0. 핵심 결론 (TL;DR)

1. 우리 현재 방법(KOSPI 60일 수익률 ±5% + 20일 변동성 백분위)은 **PIT-safe하지만 단일지표·임계값 임의성·전환지연·횡보과다**의 약점이 있다.
2. **추천 채택안 = "추세필터(이평) + 변동성/시장폭 보조"의 3요소 스코어**. 구체: **KOSPI 종가 vs MA120 + MA120 기울기(20일)** 로 BULL/BEAR/SIDEWAYS 1차 판정, **20일 실현변동성 252일 trailing 백분위**로 vol 라벨, **daily_prices % above MA120(시장폭)** 으로 확정도(confirmation) 보강.
3. **주의: DB의 `market_regime` 테이블 `peak_trough` method는 look-ahead가 내장된 사후 dating(LT/Pagan-Sossounov 류)이므로 라이브 게이트·PIT 백테스트에 절대 사용 금지.** 국면 *서술/사후 라벨링*에만 사용. (생성 스크립트가 레포에 없음 = 외부 산출물.)
4. 멀티버스에서 국면정의 자체를 스윕할 후보: `ma_window∈{60,120,200}`, `slope_lookback∈{10,20,40}`, `breadth_window∈{50,120,200}`, `breadth_thresh∈{0.45,0.5,0.55}`, `vol_pct_hi∈{0.6,0.67,0.75}`, `confirm_days∈{0,3,5}`(라벨 확정 지연 — *사후 평활이 아닌 forward-only 디바운스만*).

---

## 1. 실무/학계 국면 판별 방법 카탈로그

| 방법 | 입력데이터 | 규칙(요지) | 장점 | 단점 | Look-Ahead 위험 |
|---|---|---|---|---|---|
| **이평선 추세필터** (200/120일 MA) | 지수 종가 | close>MA → bull, close<MA → bear, 빈번 교차 → sideways | 단순·견고·실무 표준(SPY 200MA) | 휩쏘(횡보서 잦은 전환), 추세 후행 | **낮음** (MA는 trailing) |
| **MA 기울기/다중MA 정렬** | 지수 종가 | MA120 기울기>0 & 가격>MA → bull; 골든/데드크로스 | 방향성 명확, 정렬은 강추세 포착 | 전환 지연, 파라미터 다수 | **낮음** |
| **시계열 모멘텀(N개월 수익률 부호)** | 지수 종가 | 12개월(or 60·120일) 누적수익 부호 | 학계 검증多(TSMOM), 우리 현재 방법 | 임계값·룩백 임의, 횡보 과다 | **낮음** (rolling) |
| **듀얼 모멘텀** | 지수+안전자산 | 절대(>무위험)+상대(>대체자산) | risk-on/off 명료 | 자산쌍 필요(우린 금리 미보유) | **낮음** |
| **변동성 레짐**(실현변동성/VIX·VKOSPI) | 종가(or 옵션 IV) | 20일 RV 백분위 高 → 위험회피 | 위기 조기 포착, 사이징에 직결 | 방향성 없음(고변동≠하락), 보조용 | **낮음** (trailing 백분위 시) |
| **시장폭 Breadth**(% above MA, A/D, 신고저) | 전종목 OHLCV | %above MA200>50% → bull 확정 | 내부동력 포착, 천장/바닥 다이버전스 | 유니버스 정의 민감, 데이터 무거움 | **낮음** (당일 단면 trailing MA) |
| **ADX / 채널폭**(추세 vs 박스) | 지수 OHLC | ADX<20 → 무추세(sideways), >25 → 추세 | trending↔ranging 직접 분류 | 방향(상/하) 별도 필요 | **낮음** |
| **HMM / Markov-Switching** | 수익률(±변동성) | 잠재상태 K개 추정, 상태확률 | 확률적·다변량·체제전환 부드러움 | 상태 라벨 불안정, 재학습 필수, 과적합 | **중~높음** — *Viterbi 전체구간 평활·고정모수는 누설*. 반드시 rolling refit(예: 63일마다, 10일 purge) |
| **변화점 탐지**(CUSUM/Bai-Perron) | 수익률/변동성 | 통계적 break 검출 | 구조변화 엄밀 | 사후성 강함, 실시간 지연 | **높음** (양방향 정보) |
| **Peak-Trough dating**(Lunde-Timmermann, Pagan-Sossounov) | 지수 종가 | 누적 ±20%/15% 필터로 고점·저점 확정 | bull/bear 사후 라벨 표준(학계) | **전환점은 수 관측 후에야 확정 = 미래가격 사용** | **★매우 높음** — 라이브/PIT 백테스트 사용 불가, 서술용만 |
| **복합 스코어카드**(추세+변동성+폭 가중합) | 위 조합 | 신호별 점수 합산 → risk-on/off | 단일지표 잡음 완화, 견고 | 가중치 튜닝, 해석 복잡 | 구성요소가 PIT면 **낮음** |

### 출처(웹조사 2026-06-02)
- 200MA + ADX + VIX 실무 스택, 추세장=추세추종/횡보=평균회귀 적합: [tradewink](https://www.tradewink.com/glossary/market-regime-detection), [QuantMonitor](https://quantmonitor.net/how-to-identify-market-regimes-and-filter-strategies-by-trend-and-volatility/), [LuxAlgo](https://www.luxalgo.com/blog/market-regimes-explained-build-winning-trading-strategies/), [KJ Trading/Kevin Davey](https://kjtradingsystems.medium.com/bull-and-bear-regime-trading-how-to-algo-trade-with-trends-and-not-get-run-over-by-them-b1c39bf2dec)
- HMM rolling refit(63일·10일 purge·walk-forward 100 folds)로 look-ahead 제거 — 2026 MDPI Electronics: [MDPI](https://www.mdpi.com/2079-9292/15/6/1334), [QuestDB](https://questdb.com/glossary/market-regime-detection-using-hidden-markov-models/), [QuantStart](https://www.quantstart.com/articles/hidden-markov-models-for-regime-detection-using-r/)
- Lunde-Timmermann(λ₁=20%, λ₂=15%) / Pagan-Sossounov dating은 **전환점이 미래 관측 후 확정 → 실시간 백테스트 불가**: [Lunde-Timmermann WP (U.Toronto)](https://www.economics.utoronto.ca/public/workingPapers/tecipa-369.pdf), [ScienceDirect rule-based](https://www.sciencedirect.com/science/article/abs/pii/S0275531921002245), [CRAN bbdetection](https://cran.r-project.org/web/packages/bbdetection/bbdetection.pdf)

---

## 2. No-Look-Ahead 구현 포인트 (공통)

1. **Rolling only**: 모든 통계(평균·표준편차·백분위·MA)는 `≤T` 윈도우로만. `pct_change(N)`는 OK(close[T]/close[T-N]).
2. **표준화/백분위는 trailing**: z-score·백분위는 `rolling(win, min_periods=...)`의 마지막 값만 사용. 전체기간 `rank(pct=True)`·`StandardScaler.fit(전체)` 금지.
3. **라벨 확정 지연 = forward-only 디바운스만 허용**: "N일 연속 같은 신호일 때만 전환"은 OK(과거만 사용). **사후 평활(centered smoothing, 양방향 필터, peak-trough 재라벨)은 금지** — 미래 정보 누설.
4. **HMM/ML**: 반드시 rolling/expanding refit + purge gap. Viterbi 경로를 전체구간에 한 번 적합 후 라벨링하면 미래 누설.
5. **의사결정 타이밍**: T일 종가 확정(15:30 KST) → T+1 시초가 의사결정. 우리 `vkospi_at`/`get_daily_data._drop_unconfirmed_today_bar` 패턴과 동일하게 "미완성 당일봉 제외".
6. **인덱스 데이터 일관성**: `market_index`는 2026-02-12에서 멈춤(frozen). 라이브 PIT은 `daily_prices`의 `stock_code='KOSPI'`(2026-06-02까지)를 SSOT로 써야 함 — regime_split_elder_minervini.py가 이미 이 소스 사용.

---

## 3. 한국시장 특수성

- **KOSPI·KOSDAQ 디커플링**: 코스닥(성장·중소형·개인 비중)은 코스피보다 변동·낙폭 큼(예: 2024-08-05 KOSPI −8.77% vs KOSDAQ −11.30%; 2022-01 코스닥 −18%). → **전략 유니버스에 맞춰 인덱스 선택**(대형주풀=KOSPI, 중소형/급등주=KOSDAQ 또는 둘의 worst-of).
- **외국인 수급 지배**: 한미 금리역전·환율 급등 시 외국인 이탈이 하락 트리거. 외국인 순매수는 강한 국면 보조지표지만 **현재 미보유**(조달 과제, 아래 §6). `scripts/backfill_foreign_flow.py`가 존재하나 적재 여부 미확인.
- **장기 박스권**: 한국지수는 추세장보다 박스권이 길다 → SIDEWAYS 비중이 구조적으로 높음. 60일±5%는 이를 더 부풀림. ADX/채널 또는 폭 확정으로 "약추세 BULL/BEAR"를 살려야 함.
- **이벤트 리스크 빈발**: 계엄·관세 등 정책 충격이 잦아 변동성 레짐(VKOSPI)이 한국에서 특히 유용. VKOSPI 신호 모듈(`signals/vkospi.py`)이 PIT-safe하게 이미 구현됨.

---

## 4. 현재 방법(60일 수익률 ±5%) 평가

`classify_regime_rolling(kospi_close, window=20|60, threshold=0.02|0.05)` + `compute_vol_class`(20일 RV의 252일 백분위, ≥0.67=HIGH).

**강점**: PIT-safe(rolling), 구현 단순, 이미 검증 파이프라인에 통합.

**약점**
1. **임계값 임의성**: ±5%(또는 backtest용 ±2%)와 60일(또는 20일) 윈도우가 검증 없이 고정. window/threshold가 스크립트마다 불일치(p0=60d/±5%, regime_split=20d/±2%) → **국면 라벨 비일관**.
2. **단일지표(종가 모멘텀)**: 추세 방향만 보고 추세 *강도*·시장 *내부동력*(폭)·변동성을 분리 안 함. 같은 +6%라도 폭넓은 상승 vs 소수 대형주 견인을 구분 못 함.
3. **횡보 과다 / 전환 지연**: ±5% 데드존이 넓어 약추세를 전부 SIDEWAYS로 흡수. 60일 누적은 전환점에서 후행(천장에서 한참 뒤 BEAR 인지).
4. **휩쏘**: 임계 부근에서 BULL↔SIDEWAYS 잦은 깜빡임(디바운스 없음).

---

## 5. ★권고 — 우리 데이터로 당장 구현 가능한 PIT 국면 판별

### 채택 추천안: **TREND-PRIMARY 3요소 합성 (MA추세 + 변동성 + 시장폭 확정)**

모두 보유 데이터(`daily_prices` KOSPI 종가 + 전종목 OHLCV)로 PIT 계산 가능. 금리/외국인 불필요.

**구성**
1. **추세(방향) — 1차 판정** (KOSPI 종가, `stock_code='KOSPI'` in daily_prices):
   - `ma = SMA(close, 120)`, `slope = ma[T]/ma[T-20] - 1` (20일 기울기)
   - `dist = close[T]/ma[T] - 1`
   - **BULL**: `close>ma` AND `slope>0` (가격이 상승추세선 위 + 추세선 자체 상승)
   - **BEAR**: `close<ma` AND `slope<0`
   - **SIDEWAYS**: 그 외(가격·기울기 불일치 = 전환·박스)
2. **변동성 라벨** (보조, 직교): `vol20 = std(logret,20)*√252`, `vol_pct = trailing252 백분위`. HIGH_VOL if `vol_pct≥0.67` else LOW_VOL. (현행 `compute_vol_class` 그대로 재사용 — PIT 검증됨.)
3. **시장폭 확정(confirmation)** (`daily_prices` 비지수 종목 단면):
   - 각 일자 `breadth = (종목별 close > SMA(close,120)인 종목 비율)`
   - **BULL 확정**: 1차 BULL AND `breadth≥0.55`; **BEAR 확정**: 1차 BEAR AND `breadth≤0.45`; 폭이 어긋나면 한 단계 완화(→SIDEWAYS) = 거짓 추세 방지.
   - **caveat**: 우리 `daily_prices` 비지수 유니버스는 ~123~323종목의 *큐레이션 풀*(전체 KSE 아님). breadth는 "이 풀 기준" 상대지표로 해석. 그래도 추세 방향 확정에는 충분히 유효(절대값보다 변화).
4. **forward-only 디바운스**: 새 라벨이 `confirm_days=3`일 연속 유지될 때만 전환(휩쏘 억제). 과거만 사용 → PIT 안전.

**최종 라벨**: `{BULL,BEAR,SIDEWAYS} × {HIGH_VOL,LOW_VOL}` = 6구간 (기존 스키마·6구간 분석과 호환).

**왜 이 안인가**: ①실무 표준(가격 vs 장기MA)을 코어로 두되 ②MA 기울기로 "MA 위인데 하락중" 같은 모호함 제거 ③시장폭으로 소수종목 착시(특히 한국 대형주 쏠림) 차단 ④변동성은 직교 축으로 분리 — 단일 종가 모멘텀의 4대 약점을 정조준. 모두 trailing이라 PIT-safe, HMM 같은 재학습·불안정 라벨 리스크 없음.

### 대안 2안 (간단·견고, 폭 미사용): **MA200 + 모멘텀 부호**
- `BULL`: close>SMA200 AND ret_120d>0 / `BEAR`: close<SMA200 AND ret_120d<0 / 그 외 SIDEWAYS. + 동일 vol 라벨.
- 추천안의 경량판. breadth 계산이 부담스러운 백테스트 루프에서 빠르게 쓸 때.

### 멀티버스 스윕 파라미터 (국면정의 자체를 탐색)
| 파라미터 | 후보 | 의미 |
|---|---|---|
| `ma_window` | 60, 120, 200 | 추세 기준 길이 |
| `slope_lookback` | 10, 20, 40 | MA 기울기 측정 구간 |
| `breadth_window` | 50, 120, 200 | %above MA 기준 |
| `breadth_bull_thr` / `breadth_bear_thr` | 0.55/0.45, 0.50/0.50, 0.60/0.40 | 폭 확정 임계 |
| `vol_pct_hi` | 0.60, 0.67, 0.75 | HIGH_VOL 컷 |
| `confirm_days` | 0, 3, 5 | forward-only 디바운스(평활 아님) |
| `index` | KOSPI, KOSDAQ, worst-of | 유니버스 정합 |

> 스윕 시 **목적함수는 라벨 자체가 아니라 "국면별 전략 OOS 성과 분리도"** 로 평가. 그리고 라벨 정의는 in-sample 최적화 후 **OOS·다국면(특히 BEAR 포함)에서 재확인** — 단일국면 과적합은 이미 멀티버스에서 반복 확인된 함정(MEMORY 교훈).

---

## 6. 구현 스케치

```python
# regime_pit.py (신규 제안) — 전부 PIT-safe, daily_prices SSOT
import numpy as np, pandas as pd

def classify_regime_trend(kospi_close: pd.Series, ma_window=120, slope_lb=20) -> pd.Series:
    ma = kospi_close.rolling(ma_window, min_periods=ma_window).mean()
    slope = ma / ma.shift(slope_lb) - 1.0
    above = kospi_close > ma
    out = pd.Series("SIDEWAYS", index=kospi_close.index)
    out[(above) & (slope > 0)] = "BULL"
    out[(~above) & (slope < 0)] = "BEAR"
    return out  # 모두 ≤T 데이터

def breadth_above_ma(daily_prices_pivot: pd.DataFrame, win=120) -> pd.Series:
    # pivot: index=date, columns=stock_code, values=close (비지수 종목만)
    ma = daily_prices_pivot.rolling(win, min_periods=win).mean()
    above = (daily_prices_pivot > ma)
    return above.sum(axis=1) / above.count(axis=1)  # 결측 제외 비율

def confirm_debounce(label: pd.Series, days=3) -> pd.Series:
    # 새 라벨이 days일 연속일 때만 전환 — forward-only(과거만)
    out = label.copy(); cur = label.iloc[0]; run = 0; prev = cur
    vals = label.values; res = []
    for v in vals:
        if v == prev: run += 1
        else: run = 1; prev = v
        if run >= days: cur = v
        res.append(cur)
    return pd.Series(res, index=label.index)

def vol_class(kospi_close, win=20, rank_win=252, hi=0.67):
    lr = np.log(kospi_close/kospi_close.shift(1))
    vol = lr.rolling(win).std()*np.sqrt(252)
    pct = vol.rolling(rank_win, min_periods=60).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1])
    return np.where(pct>=hi, "HIGH_VOL", "LOW_VOL")
```

**통합 지점**
- 기존 `backtest/regime_analysis.classify_regime_rolling`을 대체하지 말고 `classify_regime_trend`를 **추가**(하위호환). `scripts/regime_split_*.py`가 라벨 소스를 옵션으로 선택하게.
- 인덱스 소스는 `daily_prices` `stock_code='KOSPI'`(라이브, 2026-06까지) — `market_index`(frozen)·`market_regime.peak_trough`(look-ahead) 사용 금지.
- 6구간 라벨은 `market_regime` 테이블에 `method='trend_breadth'`로 저장 가능(기존 스키마 그대로, ON CONFLICT DO NOTHING).

---

## 7. 조달 과제 (현재 미보유, 선택적 보강)
- **외국인 순매수/수급**: KIS 투자자별 매매동향 또는 KRX. `scripts/backfill_foreign_flow.py` 적재 상태 확인 후 BULL/BEAR 확정 보조축으로 추가 가능.
- **금리/환율(원달러, 한미 스프레드)**: 거시 risk-on/off 게이트용. 한국 특수성상 환율 급등=외국인 이탈 선행. ECOS/yfinance로 조달.
- 둘 다 **없어도 추천안은 완결** — 우선순위 낮음.
