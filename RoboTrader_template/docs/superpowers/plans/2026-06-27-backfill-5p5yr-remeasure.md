# 2026-06-27 — market_cap 백필 override 로 5.5년 PIT 재측정 + 3중 비교·판정

> 측정 전용·라이브 무수정·**커밋 안 함**(워킹트리 diff 만). 영구룰: 숫자 날조 금지 —
> 아래 (C) 수치는 모두 `scripts/step3d_backfill_5p5yr.py` 실제 실행 산출(워킹트리,
> 2830s / 약 47분). 원시: `scratchpad/step3d_backfill_5p5yr.md`, `scratchpad/step3d_full.log`.
> (A)/(B) 수치는 각각 `2026-06-27-size-sector-filter-backtest.md`,
> `2026-06-27-failclosed-fix-and-2024clean-remeasure.md` 의 기존 산출 인용.
> **quant `daily_prices` 테이블은 무변형** — market_cap 보강은 in-memory override 만.

---

## 0. 한 줄 요약

quant `daily_prices.market_cap` 의 2021–23 결측(0% / 0% / 0.3%)을 **`FDR 현재주식수 ×
quant 조정종가`** 로 메모리 백필해, fail-closed 수정 코드로 **5.5년 전체(2021-01-12 ~
2026-06-26)** 를 처음으로 측정했다. 결과: ① **백필로 채움률 raw 48.5% → 99.7%**(가드
통과), ② 시총컷 없는 두 전략(envelope·rs)의 baseline 이 오염본 (A)와 **소수점까지 정확
일치**(override 가 시총컷 전략만 건드림을 입증), ③ **"시총 플로어가 성과를 개선" 결론은
백필된 5.5년에서도 무효**(대부분 null, daytrading·envelope 만 미미) — (A)에서 floor 가
좋아 보인 것은 **결측 시총컷이 2021–23 을 통째로 제외해 강세장(2024–26)만 측정한 오염
아티팩트**, ④ **2024창(B) 대비 5.5년(C) 절대 Sharpe 가 전 전략에서 급락**(강세편향 보정).

---

## 1. 백필 방법 (Phase 1)

- **공식**: `과거 시총 = FDR StockListing('KRX')['Stocks'](현재 상장주식수) × quant
  조정종가 close(scan_date 와 같은 resolved 거래일)`. quant `close` 는 이미 조정값이므로
  `adj_factor` 를 곱하지 않는다(SSOT 보존룰).
- **shares 맵**: FDR 2875 종목 → `code.zfill(6) → Stocks`. 캐시 `scratchpad/shares_map.json`.
- **override 리더**(`MarketCapOverrideReader`): `QuantDailyReader.get_universe_snapshot(date)`
  결과에서 `market_cap` 이 0/None 인 항목만 `shares[code] × close(date)` 로 메모리 보강.
  채울 수 없으면(미매칭 shares 또는 close 결측) 0 유지 → fail-closed 가 제외. close 는
  snapshot 과 동일한 `date <= scan_date` 최대 거래일에서 1회 조회·캐시.
- 이 리더를 step3c/step2 의 `load_screener_universe`·`_build_screener_unions`·
  `_CachedReader`·resolver 에 주입 → 수정된 fail-closed `base_filter` 가 보강된 시총으로
  올바로 binding. **sim/청산/비용/사이징/메트릭 = step3c `_run_pit_cached` 정본 그대로
  (multiverse4 SPECS, 월별 PIT, max_per_stock=100만)**.

### 데이터완전성 가드 (Phase 1·3 검증) — **통과**
`backtest/data_completeness.py` 가 67 scan_date(2021-01-12 .. 2026-06-26, 월별) snapshot 에서:

| | market_cap 채움률 | 판정 |
|---|---|---|
| raw(백필 전) | **48.5%** (68012/140246) | LOW (min 80%) — 2021–23 결측 지배 확인 |
| backfill(백필 후) | **99.7%** (139842/140246) | **OK** — 미매칭 0.3%(8종목·상폐 등)만 결측 |

→ 백필이 2021–23 구간을 살려 5.5년 측정을 가능케 했고, 가드가 그 완전성을 확인.

### 백필 정확도 샘플검증(실측)
2022-06-30 삼성전자 **333.24조**, SK하이닉스 **64.86조**(과제 명시 333조·65조와 일치).
2021–23 각 snapshot 매칭률 99.6~99.7%.

---

## 2. (C) 백필 5.5년 — 7전략 비교표 (실측)

| strategy | config | uni | n_sig | n_trades | sharpe | pnl | maxdd |
|---|---|---|---|---|---|---|---|
| elder_ema_pullback | baseline | 874 | 71872 | 2179 | **+0.556** | +177.02% | 61.65% |
| elder_ema_pullback | floor300 | 874 | 71872 | 2179 | +0.556 | +177.02% | 61.65% |
| elder_ema_pullback | floor500 | 874 | 71872 | 2179 | +0.556 | +177.02% | 61.65% |
| minervini_volume_dryup | baseline | 1274 | 155677 | 326 | **+0.567** | +45.11% | 17.15% |
| minervini_volume_dryup | floor300 | 1274 | 155677 | 326 | +0.567 | +45.11% | 17.15% |
| minervini_volume_dryup | floor500 | 1274 | 155677 | 326 | +0.567 | +45.11% | 17.15% |
| daytrading_3methods_breakout | baseline | 2128 | 16506 | 1082 | **+0.152** | -6.78% | 53.42% |
| daytrading_3methods_breakout | floor300 | 2128 | 16343 | 1080 | +0.159 | -5.08% | 53.25% |
| daytrading_3methods_breakout | floor500 | 2128 | 16041 | 1085 | +0.171 | -2.31% | 50.98% |
| book_envelope_200d | baseline | 2447 | 5547 | 873 | **+0.089** | -36.43% | 78.51% |
| book_envelope_200d | floor300 | 2447 | 5515 | 869 | +0.102 | -30.82% | 74.34% |
| book_envelope_200d | floor500 | 2447 | 5478 | 868 | +0.104 | -29.56% | 73.33% |
| book_pullback_ma5 | baseline | 2369 | 126255 | 2354 | **-0.078** | -34.37% | 56.41% |
| book_pullback_ma5 | floor300 | 2369 | 125093 | 2354 | -0.078 | -34.37% | 56.41% |
| book_pullback_ma5 | floor500 | 2369 | 123055 | 2350 | -0.063 | -31.85% | 55.71% |
| book_pullback_ma20 | baseline | 2369 | 52614 | 1291 | **+0.016** | -32.82% | 58.54% |
| book_pullback_ma20 | floor300 | 2369 | 52084 | 1290 | +0.025 | -31.48% | 58.54% |
| book_pullback_ma20 | floor500 | 2369 | 51164 | 1288 | +0.004 | -32.77% | 55.87% |
| rs_leader | baseline | 2447 | 278074 | 3347 | **+0.492** | +149.11% | 60.97% |
| rs_leader | floor300 | 2447 | 276031 | 3346 | +0.492 | +149.10% | 60.97% |
| rs_leader | floor500 | 2447 | 273000 | 3346 | +0.492 | +149.10% | 60.97% |

전체시장 snapshot(2026-06-26)=2486. 시총컷 전략 union 이 컨셉으로 좁혀짐(elder 35%·
minervini 51%·daytrading 86%), 시총컷 없는 전략은 넓음(envelope·rs 98%·ma 95%).

### 백필 정합성 cross-check (override 가 시총컷 전략만 건드림을 입증)
시총컷이 **없는**(거래대금만) 두 전략의 (C) baseline 이 오염본 (A) baseline 과 **소수점까지
정확 일치**:
- `book_envelope_200d` baseline: (C) +0.089 / -36.43% / 78.51% **=** (A) +0.089 / -36.43% / 78.51% ✓
- `rs_leader` baseline: (C) +0.492 / +149.11% / 60.97% **=** (A) +0.492 / +149.11% / 60.97% ✓

→ override 는 결측 `market_cap` 만 채우므로, 시총을 게이트로 쓰지 않는 전략의 유니버스·
신호·체결을 전혀 바꾸지 않는다. 백필이 의도대로 **시총컷 전략에만** 작용함을 보증.

---

## 3. 3중 비교 — (A) 오염 5.5년 vs (B) 깨끗 2024–26 vs (C) 백필 5.5년

전략별 **baseline**(필터 없음) Sharpe / pnl / maxDD. (A)는 4전략만 측정(— 표기).

| strategy | (A) 오염 5.5y<br>fail-open | (B) 깨끗 2024–26<br>fail-closed | (C) 백필 5.5y<br>fail-closed+backfill |
|---|---|---|---|
| elder_ema_pullback | +0.473 / +103.6% / 63.1% | +1.964 / +235.6% / 31.3% | **+0.556 / +177.0% / 61.6%** |
| minervini_volume_dryup | — | +1.797 / +48.0% / 6.9% | **+0.567 / +45.1% / 17.2%** |
| daytrading_3methods_breakout | +0.283 / +24.7% / 30.6% | +0.364 / +15.6% / 34.1% | **+0.152 / −6.8% / 53.4%** |
| book_envelope_200d | +0.089 / −36.4% / 78.5% | +0.702 / +34.0% / 35.1% | **+0.089 / −36.4% / 78.5%** |
| book_pullback_ma5 | — | +0.506 / +24.0% / 23.4% | **−0.078 / −34.4% / 56.4%** |
| book_pullback_ma20 | — | +0.187 / +3.8% / 36.1% | **+0.016 / −32.8% / 58.5%** |
| rs_leader | +0.492 / +149.1% / 61.0% | +1.247 / +109.2% / 25.2% | **+0.492 / +149.1% / 61.0%** |

floor300 한계효과 비교(baseline→floor300 Sharpe):

| strategy | (A) floor300 | (B) floor300 | (C) floor300 |
|---|---|---|---|
| elder | +0.473→**+1.055**(오염) | +1.964→+1.964(null) | +0.556→+0.556(null) |
| daytrading | +0.283→**−0.259**(오염) | +0.364→+0.384 | +0.152→+0.159 |
| envelope | +0.089→**+0.173**(오염) | +0.702→+0.828 | +0.089→+0.102 |
| rs | +0.492→**+0.790**(오염) | +1.247→+1.247(null) | +0.492→+0.492(null) |
| minervini | — | null | null |
| ma5 | — | null | null(floor500 만 +0.015) |
| ma20 | — | +0.187→+0.215 | +0.016→+0.025 (floor500 악화) |

---

## 4. 판정 질문 4개 — 답

### ① 각 전략의 신뢰할 5.5년 컨셉-유니버스 성과(Sharpe/pnl/MaxDD)?
= **(C) baseline 열**(fail-closed 로 컨셉 유니버스에 올바로 bind + 백필로 2021–23 살림).
- **양(+) 의미있음**: `minervini` +0.567(maxDD 17.2% — 유일 저DD), `elder` +0.556(pnl +177%
  이나 maxDD 61.6% 큼), `rs_leader` +0.492(pnl +149%, maxDD 61.0%).
- **미미/중립**: `daytrading` +0.152(pnl **−6.8%**), `book_envelope_200d` +0.089(pnl −36.4%,
  maxDD 78.5% — 5.5년 기준 부진), `book_pullback_ma20` +0.016(pnl −32.8%).
- **음(−)**: `book_pullback_ma5` **−0.078**(pnl −34.4%) — 5.5년 전체에서 손실(메모리의
  "ma5 부진" 재확인, 강세장 아티팩트 아님).
- 공통 주의: minervini 외 전 전략 maxDD 50~78% — 절대 리스크 큼(2021–22 약세 포함).

### ② "시총 플로어 개선"은 백필된 5.5년에서도 무효인가(2024창 결론 재확인)?
**그렇다 — 무효(2024창 결론 재확인).**
- **null(효과 없음) 4–5/7**: `elder`·`minervini`(자체 하한 5천억/3천억이 floor 를 완전
  포섭)·`rs_leader`·`ma5`(floor 가 거른 극소형은 애초 top-K 체결 안 됨) 는 floor300/500 이
  baseline 과 **수치 동일**(rs trades 3347→3346 수준의 무의미 차).
- **미미(weak) 2/7**: `daytrading`(+0.152→+0.171, maxDD 53.4→51.0% — 단조 개선이나 작음·
  pnl 여전히 음수권), `book_envelope_200d`(+0.089→+0.104, maxDD 78.5→73.3% — 단조이나
  pnl 여전히 −30%대). 시총컷이 없는 전략에서만 floor 가 유일 사이즈 게이트로 약하게 실효.
- **잡음**: `ma20`(floor300 소폭↑, floor500 악화).
- → 운영 함의: **일괄 시총 플로어 도입 근거는 백필 5.5년에서도 약함.** B 의 결론과 동일.

### ③ 오염 baseline(A) 대비 백필 baseline(C) 차이(=오염의 크기)?
**시총컷 전략에서 크고 방향 의존, 시총컷 없는 전략에서 0.**
- **시총컷 없음(envelope·rs)**: (A)=(C) **완전 동일**(§2 cross-check). baseline 오염 0.
- **시총컷 있음**: `elder` +0.473→+0.556(개선 — fail-open 이 5천억 미만 결측주를 누수시켜
  컨셉을 더럽혔고, fix+백필이 대형 컨셉으로 정화). `daytrading` +0.283→**+0.152**(악화 —
  fail-open 이 5천억 이상 대형주를 daytrading(중소형 컨셉)에 누수, 정화하니 부진 노출,
  pnl +24.7%→−6.8%).
- **가장 큰 오염은 baseline 이 아니라 (A)의 floor 구성**: (A) floor 는 *결측 시총* 을 컷
  기준으로 써 2021–23 전체를 제외 → **강세장(2024–26)만 측정** → elder +1.055·rs +0.790·
  envelope +0.173 처럼 부풀려짐. (C) 백필 floor 는 이 환상을 제거(§②).

### ④ 2024창(B) 대비 5.5년(C)에서 절대 Sharpe 가 떨어지는가(=강세편향 보정)?
**전 전략에서 급락 — 강한 강세편향 보정.**

| | elder | minervini | daytrading | envelope | ma5 | ma20 | rs |
|---|---|---|---|---|---|---|---|
| (B) 2024–26 | +1.964 | +1.797 | +0.364 | +0.702 | +0.506 | +0.187 | +1.247 |
| (C) 5.5년 | +0.556 | +0.567 | +0.152 | +0.089 | **−0.078** | +0.016 | +0.492 |

2024–26(2.5년)은 단일 강세국면 비중이 커 Sharpe 가 낙관 편향. 2021–22 약세(코스피 −25%
국면)를 포함한 5.5년에서 절대 Sharpe 가 1/2~1/8 로 하락, ma5 는 음수로 전환. **2024창
수치는 절대 성과 기준으로 신뢰 금지** — 5.5년(C)이 더 보수적·정직한 컨셉 성과.

---

## 5. 한계 (반드시 함께 해석)

- **현재주식수 소급 근사**: 과거 시총을 *현재* 상장주식수로 역산 → 증자·자사주 변동에서
  오차. 액면분할은 quant 조정종가가 흡수하나 발행주식수 변경(증자/감자)은 미반영. 시총
  *경계 근방* 종목의 floor 통과/제외에 ±오차 가능(단 floor 결론은 대부분 null 이라 영향 작음).
- **미매칭·생존편향**: FDR 현재 상장목록에 없는 종목(상장폐지·신규변경 8종목, 미매칭
  0.3%)은 백필 불가 → 시총 결측 유지 → fail-closed 제외. 즉 **2021–23 에 상폐된 종목은
  유니버스에서 빠짐 = 생존편향**(성과를 낙관쪽으로 약간 밀 수 있음). 본 측정은 floor 의
  *방향/생존성* 판별이 목적이라 이 편향이 결론(floor 무효)을 뒤집지 않는다.
- **PIT 월별 근사**: 라이브 일별 스크리너를 67 월별 scan_date 멤버십으로 근사(±수주).
- **maxDD 절대수준**: minervini 외 50~78% — 본 sim 은 전략별 독립 포트폴리오(max_per_stock
  100만) 기준이라 실제 8전략 합성·regime 게이트와 다름. 절대 리스크는 별도 평가 필요.
- **ex_sector(섹터) 미측정**: 현재 섹터 소급 = look-ahead 라 PIT-clean floor 구성만 측정
  (A 의 ex_sector 는 방향성 참고일 뿐, 본 백필 패스에 섞지 않음).

---

## 6. 산출물 (커밋 안 함 — 워킹트리)

신규(측정 전용, 라이브·SSOT 무수정):
- `scripts/step3d_backfill_5p5yr.py` — 백필 override 리더 + 5.5년 재측정 스크립트.
- `scratchpad/shares_map.json` — FDR 현재주식수 캐시(2875).
- `scratchpad/step3d_backfill_5p5yr.md` — 자동 raw 리포트.
- `scratchpad/step3d_full.log` — 원시 실행 로그(2830s).
- 본 문서 — 3중 비교·판정.

**quant `daily_prices` 테이블 무변형 재확인**(메모리 override 만). **커밋 안 함**.
