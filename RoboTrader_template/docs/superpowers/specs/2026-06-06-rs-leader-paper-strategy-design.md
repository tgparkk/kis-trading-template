# 횡보장 RS 리더 — 7번째 페이퍼 전략 (설계 스펙)

- 날짜: 2026-06-06
- 상태: 설계 (검토 대기) → 다음: writing-plans
- 선행: 검증 스파이크 `2026-06-06-rs-leader-bad-market-design.md` (판정 PARTIAL)

## 0. 한 줄 요약

검증에서 *강건*하게 확인된 **횡보장 RS 리더**(시장과 디커플링되어 자기 추세로 오르는 종목)를 기존 전략별 EOD 스크리너 패턴으로 **7번째 페이퍼 관찰 전략**에 등록한다. 깊은 약세장 엣지는 미입증이므로 `regime_gate=exclude_bear`로 약세장 매수를 차단하고, **paper 전용**(실계좌 아님)으로 거동만 관찰한다.

## 1. 정직한 전제 (반드시 명시)

- 검증 결과는 **조건부**: 횡보장 절대수익 5/5 config 강건(+5~8%)·OOS 양수 ✅ / 깊은약세 부호반전·미입증 ❌ / per-trade Sharpe 0.08~0.19(채택바 0.6 미달).
- 따라서 이건 **강한 전략이 아니라 격리 페이퍼 관찰 후보** — 기존 ma20/ma5가 OOS 부진에도 "페이퍼 관찰"로 유지되는 것과 동일 성격.
- **라이브 실계좌 금지.** 독립 가상자본 1천만으로 거동만 관찰. 일정 기간 관찰 후 유지/제외 재판정.

## 2. 아키텍처 (기존 전략별 EOD 스크리너 패턴 재사용)

핵심 통찰: `RuleScreenerBase.scan`이 종목별 `match` 점수를 모아 **정렬→top-K** 하므로, `match`가 추세통과 종목의 **120일 수익률을 score로 반환**하면 scan의 정렬이 곧 **횡단면 RS 랭킹**이 된다(별도 랭크 패널 불필요, 검증 로직과 정합).

```
EOD: RSLeaderScreenerAdapter.scan(date)
  → base_filter(유동성) → 종목별 match(절대상승추세 통과 시 score=120일수익률)
  → scan 정렬+topK = RS 리더 후보 → screener_snapshots 저장(owner='rs_leader')
라이브: on_tick → ctx.get_selected_stocks → RSLeaderStrategy.generate_signal
  → per-stock 절대추세 재확인 → ctx.buy (regime_gate=exclude_bear·시장방향 가드 내장)
청산: MA20 트레일링 + sl-8% + max_hold (기존 risk_management 프레임)
```

## 3. 컴포넌트

### 3.1 `strategies/rs_leader/screener.py` — `RSLeaderScreenerAdapter(RuleScreenerBase)`
- `strategy_name = "rs_leader"`, `lookback_days = 130` (MA60 + 120일 수익률 워밍업).
- `base_filter(universe)`: 거래대금 ≥10억·가격 1,000~500,000 통과만(기존 어댑터와 동형, `market_cap`/`trading_value` 사용).
- `match(df, params)`: 절대 상승추세 — `종가 > MA(ma_long)` AND `MA(ma_short) > MA(ma_long)` AND `abs_lb일 수익률 > 0`. 통과 시 `(score = rs_lb일 수익률, reason)`; 탈락 None. (정렬+topK가 RS 랭킹)
- `default_params`: `{ma_short:20, ma_long:60, abs_lb:60, rs_lb:120, max_candidates:10}`.

### 3.2 `strategies/rs_leader/strategy.py` — `RSLeaderStrategy(BaseStrategy)`
- `book_pullback_ma20/strategy.py` 와 동형 구조. `generate_signal(stock_code, df, timeframe="daily")`: 스크리너가 이미 RS 랭킹한 후보 풀에서 per-stock **절대 상승추세 재확인**(screener.match 의 추세 조건과 동일) 시 `Signal(BUY)`; 아니면 None. `holding_period="swing"`.
- `min_daily_bars` 가드: ≥ ma_long+abs_lb 충족(≈125) 필요분.
- ★재사용: 추세 판정 로직은 `scripts/rs_leader/rule.RSLeaderRule` 과 동일 정의 — 라이브/스크리너/검증 3곳 정합 유지(중복 구현 시 한 곳에 헬퍼로 추출 검토).

### 3.3 `strategies/rs_leader/config.yaml`
```yaml
strategy: {name: "RSLeaderStrategy", version: "1.0.0"}
paper_trading: true
parameters: {ma_short: 20, ma_long: 60, abs_lb: 60, rs_lb: 120, min_daily_bars: 130, max_holding_days: 30}
risk_management:
  take_profit_pct: 0.15        # 추세추종 — 고정익절 거의 무효(트레일이 주 청산)
  stop_loss_pct: 0.08
  trail_ma: 20                 # 종가 < MA20 하향이탈 시 청산 (주 청산)
  max_hold_days: 30
  max_positions: 10
  max_per_stock_amount: 3000000
target_stocks: []
```

### 3.4 `runners/_adapter_factory.py`
`build_adapter`에 `elif strategy_name == "rs_leader": from strategies.rs_leader.screener import RSLeaderScreenerAdapter; return RSLeaderScreenerAdapter(config=config, broker=broker, db_manager=db_manager)` 추가.

### 3.5 `config/trading_config.json`
`strategies[]`에 7번째 추가:
```json
{"name": "rs_leader", "enabled": true, "max_capital_pct": 0.14, "regime_index": "KOSPI", "regime_gate": "exclude_bear"}
```
- `max_capital_pct`는 실계좌 reserve 가드 레이어(paper 1천만 격리와 무관, 메모리 정책). 기존 6전략(각 0.16) 미변경. 합>1.0은 reserve 상한이라 무해.
- regime_gate=exclude_bear: 깊은약세 미입증 → BEAR 매수 차단. regime_index=KOSPI.

## 4. 데이터
- 일봉: QuantDailyReader(robotrader_quant, 조정종가) — RuleScreenerBase 기본 경로. KOSPI 게이트는 RegimeGate(기존, daily_prices KOSPI).
- 라이브 진입 평가는 `ctx.get_daily_data`(확정봉만) → 미완성 당일봉 배제(기존 SSOT).

## 5. 청산 (결정: MA20 트레일링)
- 주 청산 = 종가 < MA20 하향이탈(`trail_ma:20`). 보조 = sl −8%, max_hold 30거래일. tp는 추세추종이라 사실상 무효(고정익절 없음).
- 근거: 검증 4-bis에서 MA20 청산이 손실 중앙값 −6%→−0.7%로 축소(횡보장 양수·OOS 양수 강건 유지). per-trade Sharpe는 낮으나 페이퍼 관찰 목적엔 적합.

## 6. 테스트
- `screener.match`: 추세 통과→(score,reason) / 탈락→None / score=120일수익률 정확 / no-lookahead(df는 scan_date 이하만).
- `base_filter`: 유동성 필터 통과/탈락.
- `strategy.generate_signal`: 상승추세→BUY / 하락·짧은데이터→None.
- `build_adapter("rs_leader")`: 어댑터 인스턴스 반환.
- config 로드: StrategyLoader 가 RSLeaderStrategy 인스턴스화 + risk_management 키 인식.
- 회귀: 기존 6전략 어댑터·테스트 무영향.

## 7. 한계 (config·리포트에 명시)
- 깊은 약세장 엣지 미입증(표본 노이즈) → exclude_bear로 회피만, 능동수익 아님.
- per-trade Sharpe 낮음·아웃라이어 의존 → 페이퍼 관찰 전용.
- RS 음전환 청산 미모델(MA20 트레일로 대체).
- 라이브 평가 일봉 소스가 robotrader(sparse)일 수 있음 — 기존 전략과 동일 제약(거래량룰 없어 영향 경미).

## 8. 봇 반영
- 신 config 필드·어댑터는 **봇 재시작 시 1회 로드**. 재시작 전까지 미반영.

## 9. 비범위 (YAGNI)
- 라이브 실거래, 분봉, 인버스, 샤프너(breadth 디커플링) 필터, RS 파라미터 튜닝.
