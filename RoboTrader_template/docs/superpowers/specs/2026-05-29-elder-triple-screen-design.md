# Elder Triple Screen — 백테스트 설계서 (Book 7)

> 조사 노트: [reports/books_research/elder_triple_screen/research.md](../../../reports/books_research/elder_triple_screen/research.md)
> 작성: 2026-05-29
> 결정사항(사장님 승인): Screen 1 = **일봉 65일 EMA proxy** / 끝까지 자동 진행

---

## 0. 설계 원칙

1. **일봉 단일 해상도** — Screen 1(추세)을 주봉이 아닌 일봉 65일 EMA(=13주×5)로 근사 → 224일 데이터에서 ~159일 사용가능. Minervini 일봉 파이프라인 재사용(`run_minervini_vcp.py` 구조), 주봉 resample 불필요.
2. **종목 자기완결** — 지수 불필요. ctx 주입 불필요(Minervini의 rs_value조차 불필요). 모든 지표를 rule이 `df` 윈도에서 직접 계산.
3. **롱 전용** — 한국 공매도 제약 → 숏 셋업 제외.
4. **no-lookahead** — rule은 `df`(t까지)만 사용. 진입은 t+1, Screen 3 체결도 t+1 OHLC만으로 판정.
5. **거래비용** — Minervini와 동일(commission 0.015%×2, tax 0.18%, slippage 0.1%×2 ≈ 왕복 0.41%).

---

## 1. 지표 헬퍼 (rules.py 모듈 함수)

> 모두 `ewm(span=N, adjust=False)` 사용 (Elder/차팅 일치). 입력은 `df`의 시리즈.

```
ema(series, n)              = series.ewm(span=n, adjust=False).mean()
macd_hist(close,12,26,9)    = (ema12-ema26) - ema((ema12-ema26),9)
force_index(close,vol,n)    = ema((close - close.shift(1)) * vol, n)     # raw 후 EMA(n)
bull_power(high,close,13)   = high - ema(close,13)
bear_power(low,close,13)    = low  - ema(close,13)
stochastic(high,low,close,n=14,k=3,d=3):
    ll=low.rolling(n).min(); hh=high.rolling(n).max()
    k_raw=100*(close-ll)/(hh-ll).replace(0,nan)
    %K=k_raw.rolling(k).mean(); %D=%K.rolling(d).mean()
impulse_color(close,13,12,26,9):
    ema_up = ema13[t]>ema13[t-1]; hist_up = hist[t]>hist[t-1]
    green = ema_up & hist_up; red = (~ema_up)&(~hist_up); blue = 그 외
krx_tick(price): KRX 호가단위 (2023 개정)
    <2,000→1 / <5,000→5 / <20,000→10 / <50,000→50 /
    <200,000→100 / <500,000→500 / ≥500,000→1,000
```

---

## 2. Screen 1 공통 추세 proxy (확정)

```
ema65 = ema(close, 65)
screen1_uptrend(t) = ema65.iloc[-1] > ema65.iloc[-6]      # 5일(1주) 기울기 > 0
```

- 사장님 승인값. warmup 65봉. 임계값(단순 부호)은 추후 데이터 누적 후 재검토.

---

## 3. 진입 룰 4종 (확정 파라미터)

> 모든 룰: 최소봉 = warmup(MACD ~35, ema65 65 등) 충족 시에만 평가. side="buy".
> Screen 3(매수스톱)은 run 스크립트가 처리 → rule은 Screen 1+2 신호만 판정.

### rule_triple_screen_force_index (Setup A, confidence 72)
정통 Triple Screen.
1. `screen1_uptrend` (ema65 상승)
2. 일봉 **MACD-Hist(12,26,9) 상승**: `hist[-1] > hist[-2]`
3. 일봉 **Force Index(2일 EMA) < 0**: `fi2.iloc[-1] < 0`
- min_bars = 70

### rule_triple_screen_stochastic (Setup B, confidence 68)
주봉 EMA 상승 + 일봉 Stochastic 과매도.
1. `screen1_uptrend`
2. **Stochastic(14,3,3) %K < 30** AND **%K[-1] > %D[-1]** (상향 전환)
- min_bars = 70

### rule_triple_screen_elder_ray (Setup C, confidence 66)
Impulse 비적색 + Elder-Ray Bear Power 상승.
1. `screen1_uptrend`
2. 일봉 **Impulse NOT red** (red = ema13 하락 AND hist 하락; green/blue 허가)
3. 일봉 **Bear Power < 0 AND Bear Power[-1] > Bear Power[-2]** (음수이나 상승)
4. 일봉 **ema13 상승** (`ema13[-1] > ema13[-2]`)
- min_bars = 70

### rule_triple_screen_ema_pullback (Setup D, confidence 60)
단순화 EMA 눌림 반등 — 표본 최대·견고성 베이스라인.
1. `screen1_uptrend`
2. 일봉 **`low[-1] <= ema13[-1]*1.01` AND `close[-1] > ema13[-1]`** (EMA13 터치 후 회복)
- min_bars = 70

```
ALL_RULES = [rule_triple_screen_force_index, rule_triple_screen_stochastic,
             rule_triple_screen_elder_ray, rule_triple_screen_ema_pullback]
```

---

## 4. Screen 3 진입 (run 스크립트 — Approx A 매수스톱)

신호가 t에 발생하면 t+1에서:
```
trigger = high[t] + krx_tick(high[t])
if open[t+1] >= trigger:        fill = open[t+1] * (1+slippage)   # 갭상승 체결
elif high[t+1] >= trigger:      fill = trigger   * (1+slippage)   # 장중 스톱 발동
else:                           미체결 → 그 다음날 재시도(최대 N_TRAIL=2일, 매일 trigger 갱신)
                                N_TRAIL 초과 또는 screen1 추세 반전 시 신호 취소
```
- no-lookahead: t+1 OHLC만으로 t+1 체결 판정. trailing 재시도도 각 날 OHLC만 사용.
- 4개 셋업 모두 동일 적용(Setup D 포함 — 일관성). 이로써 D는 책 의도(open 진입)보다 보수적이나 Screen 3 충실.

---

## 5. 청산 Variant (확정)

| Variant | sl | tp | trail | mh | 비고 |
|---------|-----|-----|-------|-----|------|
| **A** (책 의도) | 0.08 | 0.30 | **EMA13 이탈** (수익 후 `close < ema13`) + **추세 반전**(ema65 기울기 하향) | 100 | Elder 추세추종 |
| **B** (획일) | 0.08 | 0.12 | 없음 | 20 | 책간 비교 |

- Variant A trail은 Minervini의 SMA `trail_ma`와 달리 **EMA13** + ema65 반전 OR 조건. Elder simulate에서 구현.
- 2%/6% 자금관리는 포지션 사이징 룰이므로 본 백테스트(종목별 단일 포지션, 자본 99% 투입)에서는 제외(연구 노트 §5 명시). 향후 PositionSizer 연동 시 검토.

---

## 6. 코드 산출물

```
strategies/books/elder_triple_screen/
├── __init__.py
├── rules.py      # 지표 헬퍼 6종 + krx_tick + 룰 4종 + ALL_RULES
└── strategy.py   # ElderTripleScreenStrategy(BookStrategy) + BOOK_META + build_strategy
scripts/run_elder_triple_screen.py   # Minervini run 복제 + Screen3 매수스톱 + EMA13 trail
```

- **strategy.py**: `holding_period="swing"`. BOOK_META id="elder_triple_screen", category="multi_timeframe_trend".
- **run 스크립트**: `_load_top_volume_universe`, `_load_daily_adj`는 Minervini와 동일(복제). `compute_rs_percentile_12w`/rs_series 제거(불필요). `simulate_one_stock`에 Screen3 매수스톱 + EMA13 trail + ema65 반전 exit 추가. `--variant A|B`, `--mode|--all-modes`, `--rule`, `--top-n`, `--start/--end`. leaderboard book_id="elder_triple_screen".

---

## 7. 백테스트 실행 계획

```
python scripts/run_elder_triple_screen.py --variant A --all-modes
python scripts/run_elder_triple_screen.py --variant B --all-modes
```
- 기간: daily_prices 전체(2025-07-01 ~ 2026-05-29). universe top_volume:50.
- 산출: `reports/books_research/elder_triple_screen/results_variant{A,B}_single_{rule}.parquet` + leaderboard 행 추가.

---

## 8. 검증 (Phase 4 후)

- pytest 회귀: `tests/books/` (기존 통과 유지). 신규 Elder rule 단위 테스트는 시간 허용 시 추가.
- no-lookahead 수동 점검: Screen3 체결이 t+1 OHLC만 참조하는지.
- 결과 표본 수 기록. BULL 편향 경고 리포트 전면 표기.

---

## 9. 한계 (리포트 반영)

- 단일 BULL 구간(224일) → 롱 전용 추세추종 과대평가 위험. 하락장 방어 미검증.
- 표본 희소(confluence 시스템). Sharpe/Calmar 신뢰구간 넓음 → directional 해석.
- 파라미터가 Elder 원전과 다른 적응판(일봉 proxy, 13주 EMA 등) — "an adaptation" 라벨.
