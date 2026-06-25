# 2026-06-25 Task 5(D): 라이브 청산 손익률 vs 백테스트 정합 조사

**작성일**: 2026-06-25  
**조사범위**: 8전략 전수, 코드 정적 분석 + DB 실측(virtual_trading_records, source=kis_template, 2026-06-01~)  
**상태**: 확정 / 추정 구분 명시

---

## 1. 8전략 Signal.target_price / stop_loss 식 + config% + 분기 방향 표

| 전략 | target_price 식 | stop_loss 식 | 코드 위치 | config tp% | config sl% | 갭업 시 tp 분기 | 갭업 시 sl 분기 |
|------|----------------|--------------|-----------|-----------|-----------|----------------|----------------|
| elder_ema_pullback | `current_price * (1 + 0.30)` | `current_price * (1 - 0.08)` | strategy.py:341-342 | 30% | 8% | 갭업 시 tp% 낮아짐(양수 유지) | 갭업 시 sl% 좁아짐 |
| book_envelope_200d | `ref_close * (1 + 0.10)` | `ref_close * (1 - 0.08)` | strategy.py:268-269 | 10% | 8% | 갭업 시 tp 음수 가능(ref_close < fill) | 갭업 시 sl% 급격히 좁아짐 |
| daytrading_3methods_breakout | `current_price * (1 + 0.10)` | `current_price * (1 - 0.10)` | strategy.py:268-269 | 10% | 10% | 갭업 시 tp% 낮아짐 | 갭업 시 sl% 좁아짐 |
| minervini_volume_dryup | `current_price * (1 + 0.12)` | `current_price * (1 - 0.08)` | strategy.py:285-286 | 12% | 8% | 갭업 시 tp% 낮아짐 | 갭업 시 sl% 좁아짐 |
| book_pullback_ma20 | `current_price * (1 + 0.10)` | `current_price * (1 - 0.08)` | strategy.py:269-270 | 10% | 8% | 갭업 시 tp% 낮아짐 | 갭업 시 sl% 좁아짐 |
| book_pullback_ma5 | `current_price * (1 + 0.15)` | `current_price * (1 - 0.03)` | strategy.py:269-270 | 15% | 3% | 갭업 시 tp% 낮아짐 | 갭업 시 sl% 좁아짐 |
| rs_leader | `current_price * (1 + 0.15)` | `current_price * (1 - 0.08)` | strategy.py:162-163 | 15% | 8% | 갭업 시 tp% 낮아짐 | 갭업 시 sl% 좁아짐 |
| deep_mr_dev20 | `current_price * (1 + 0.12)` | `current_price * (1 - 0.07)` | strategy.py:171-172 | 12% | 7% | 갭업 시 tp% 낮아짐 | 갭업 시 sl% 좁아짐 |

### 핵심 발견 — current_price vs ref_close 분기

**7전략(elder / daytrading / minervini / ma20 / ma5 / rs_leader / deep_mr)**:  
Signal.target_price = `current_price * (1 + tp_pct)`, 즉 **일봉 확정 종가(generate_signal 평가 시점)**를 기준으로 설정.  
→ 이 current_price가 라이브 체결가(buy_price)와 같으면 2순위와 3순위 결과가 일치하므로 분기 없음.  
→ 라이브 틱이 달라지면(갭업/갭다운) 2순위 역산 tp/sl이 config%와 미세하게 다름.

**book_envelope_200d (1전략만 예외)**:  
Signal.target_price = `ref_close * (1 + 0.10)`, **ref_close = quant 일봉 직전 확정 종가** (별도 DB 조회, strategy.py:267).  
→ ref_close와 라이브 체결가(fill_price)가 다르면 역산 tp가 config 10%에서 크게 벗어남.  
→ 갭업 체결(fill > ref_close)이면 tp 음수 가능. 실제 2026-06-12 089970에서 tp=-1.88% 발생 확인(DB).

### 분기가 생기는 정확한 경로

```
generate_signal() 호출 시점:
  current_price = data["close"].iloc[-1]  ← 일봉 확정 종가 (generate_signal이 평가하는 데이터)

라이브 체결 시점(수 분~수 시간 후):
  buy_price = _get_live_price()  ← 실시간 현재가

2순위 역산:
  tp_2nd = (signal.target_price - buy_price) / buy_price
         = (current_price*(1+config_tp) - buy_price) / buy_price
         = config_tp + (current_price - buy_price)/buy_price
         = config_tp + gap_factor  ← gap_factor = (ref_close - fill) / fill

결론: 2순위 tp = config_tp + gap_factor
      2순위 sl = config_sl - gap_factor (부호 반대)
```

즉 **갭업이면 tp 감소·sl 좁아짐, 갭다운이면 tp 증가·sl 넓어짐**. 방향은 동일.

---

## 2. Signal 절대가의 청산 외 다른 용도

### 조사 결과 (확정)

| 용도 | 파일 | 라인 | 설명 |
|------|------|------|------|
| 익절률 역산(2순위) | `core/trading_decision_engine.py` | 542-545 | `_tp = (signal.target_price - buy_price) / buy_price` |
| 손절률 역산(2순위) | `core/trading_decision_engine.py` | 546-547 | `stop_loss_rate = (buy_price - signal.stop_loss) / buy_price` |
| 진입 지정가 밴드 검증 | `core/trading_decision_engine.py` | 373-380 | `entry_min_price` / `entry_max_price` 사용 — **target_price/stop_loss 미사용** |
| 진입 지정가 밴드 검증(2) | `core/trading_context.py` | 389-404 | `entry_min_price` 돌파 게이트 — **target_price/stop_loss 미사용** |
| DB 저장(tp/sl rate) | `core/orders/order_executor.py` | 571-579 | rate 값이 저장됨, Signal 절대가 자체는 저장 안 됨 |
| 주문 가격(order price) | `core/trading_decision_engine.py` | 364-396 | `round_to_tick(current_price)` 사용 — **Signal 절대가 미사용** |

**Signal.target_price / stop_loss(절대가)는 오직 하나의 경로: `trading_decision_engine.py:542-547` 역산(2순위)에서만 사용된다.**  
진입 주문 가격, 진입 지정가 밴드(entry_min/max), DB 저장 모두 이 절대가를 직접 소비하지 않는다.  
→ **2순위 제거는 Signal.target_price/stop_loss 절대가의 유일한 사용처를 제거하는 것과 동치**.

---

## 3. 실측 갭 진입·괴리 정량

### 분석 방법
- 기준: `virtual_trading_records` WHERE action='BUY' AND source='kis_template' AND timestamp >= '2026-06-01'
- n=239건 (8전략 합산)
- gap_pct = fill_price / implied_ref_close − 1  
  (implied_ref_close = fill_price × (1+tp_rate) / (1+config_tp): Signal이 config% 기준이면 gap_pct=0)

### 전략별 2순위 채택 비율 및 갭 분포

| 전략 | n | 2순위 채택 | config 일치 | tp<0 | avg_gap% | min_gap% | max_gap% | 갭업>2% | 갭다운>2% |
|------|---|-----------|------------|------|----------|---------|---------|--------|---------|
| book_envelope_200d | 24 | 24(100%) | 0 | **1** | −2.02 | **−17.67** | +12.10 | 3 | 12 |
| book_pullback_ma20 | 29 | 29(100%) | 0 | 0 | −0.74 | −5.02 | +9.33 | 2 | 6 |
| book_pullback_ma5 | 37 | 34(92%) | 3 | 0 | −1.78 | −10.91 | +2.47 | 1 | 12 |
| daytrading_3methods_breakout | 29 | 25(86%) | 4 | 0 | −2.88 | **−23.24** | +5.22 | 2 | 12 |
| deep_mr_dev20 | 19 | 17(89%) | 2 | 0 | −2.08 | −6.94 | +5.39 | 2 | 10 |
| elder_ema_pullback | 33 | 33(100%) | 0 | 0 | −0.30 | −4.97 | +9.26 | 5 | 9 |
| minervini_volume_dryup | 31 | 31(100%) | 0 | 0 | −0.52 | −13.49 | +9.36 | 7 | 11 |
| rs_leader | 37 | 35(95%) | 2 | 0 | −1.58 | −13.58 | +8.59 | 7 | 14 |

### 주요 수치 해석

1. **2순위 채택률 86~100%**: 거의 모든 진입에서 Signal 절대가가 tp/sl 결정에 사용되고 있음. config값과 정확히 일치하는 경우는 8전략 합산 239건 중 18건(7.5%)에 불과.

2. **평균 gap_pct 음수(-0.30% ~ -2.88%)**: 갭다운(fill_price < ref_close) 진입이 갭업보다 많음. 갭다운 시 tp는 config%보다 높아지고 sl은 config%보다 좁아짐 → 손절이 더 타이트해지는 방향.

3. **book_envelope_200d 최대 편차**: daytrading −23.24%, envelope −17.67%는 각각 config% 대비 tp 편차가 13.24%p, 7.67%p에 달함. 이는 체결가가 ref_close 대비 크게 달랐음을 의미.

4. **tp 음수 1건 확인**: 089970 (2026-06-12), book_envelope_200d, fill_price=95,400, ref_close≒85,100, gap=+12.1%. 갭업 12%로 체결 → tp=-1.88%. Band-aid(양수만 채택) 덕분에 3순위(config 10%)로 낙하하지 않고 **2순위 sl만 잘못 역산된 채 저장됨**(sl=17.93% — config 8% 대비 9.93%p 더 넓음).

---

## 4. STOP_LOSS_FLOOR 3% binding 실측

### binding 발생 건수 (book_pullback_ma5 제외 — config sl=3%와 동치)

| 전략 | binding 건수 / 전체 | config sl% | 원인 |
|------|---------------------|-----------|------|
| book_envelope_200d | 2 / 24 | 8% | 갭업 체결 → Signal 역산 sl < 3% → FLOOR 적용 |
| daytrading_3methods_breakout | 3 / 29 | 10% | 갭업 체결 → Signal 역산 sl < 3% → FLOOR 적용 |
| deep_mr_dev20 | 5 / 19 | 7% | 갭업 체결 → Signal 역산 sl < 3% → FLOOR 적용 |
| minervini_volume_dryup | 1 / 31 | 8% | 갭업 체결 → Signal 역산 sl < 3% → FLOOR 적용 |
| rs_leader | 5 / 37 | 8% | 갭업 체결 → Signal 역산 sl < 3% → FLOOR 적용 |
| elder_ema_pullback | 0 / 33 | 8% | sl 8% 범위 내에서 gap이 흡수됨 (config sl 크므로 floor에 안 닿음) |
| book_pullback_ma20 | 0 / 29 | 8% | 동일 이유 |

**전체 binding 건수: 16건 / 154건(ma5 제외) = 10.4%**

binding 전형 패턴: 갭업이 클수록 Signal 역산 sl = (fill - stop_signal) / fill 에서 분자가 줄어 sl이 작아짐 → 3% 미만 → FLOOR 적용. binding된 건의 tp는 모두 높음(19~43%) — 갭업이 Signal tp 도달을 어렵게 만들면서 동시에 sl을 위험하게 좁히는 이중 왜곡.

---

## 5. 결정 권고

### 옵션 α: 2순위 제거 → config% 기준(진입가 기준 고정%) 우선 = 백테스트 완전 정합

**변경 위치**: `core/trading_decision_engine.py:542-547`  
제거 대상:
```python
# [2순위] Signal의 target_price / stop_loss (절대가 → 비율 변환) — 이 블록 전체 제거
if target_profit_rate is None and signal and signal.target_price and buy_price > 0:
    _tp = (signal.target_price - buy_price) / buy_price
    if _tp > 0:
        target_profit_rate = _tp
if stop_loss_rate is None and signal and signal.stop_loss and buy_price > 0:
    stop_loss_rate = (buy_price - signal.stop_loss) / buy_price
```

**효과**:
- tp/sl이 항상 진입가(buy_price) 기준 config%로 결정됨 = 백테스트 `entry_price × (1±rate)` 정합
- tp 음수 완전 소멸
- FLOOR 3% binding 빈도 대폭 감소 (config sl >= 3%인 한 발생 안 함. book_pullback_ma5만 config sl=3%=FLOOR 동치)
- 갭업/갭다운 여부에 무관하게 동일 비율 적용
- Signal.target_price/stop_loss 절대가는 현재 이 경로 외 사용처 없음 → 제거 후 side-effect 없음

**회귀 범위**: 낮음. 이미 tp=음수 방어 코드(band-aid)가 있는 상태에서, 2순위 전체를 제거하는 것이므로:
- `test_decision_engine.py`의 Signal target_price/stop_loss 2순위 관련 테스트 케이스 수정 필요 (있는 경우)
- 영향 전략: 8전략 전부 (tp/sl 결정이 바뀜)

**리스크**: 일부 전략이 tp/sl 역할로 Signal 절대가를 활용하는 설계 의도가 있었다면 기능 소실. 그러나 코드 분석 결과 8전략 모두 `current_price × (1±%)` 또는 `ref_close × (1±%)`를 쓰므로, Signal 절대가가 config%보다 더 정확한 목표가를 담는 경우는 없음. → 제거가 안전.

---

### 옵션 β: 2순위 유지 + 왜곡 가드 강화

**현황**: 이미 tp < 0이면 None 유지(band-aid)로 tp 음수는 차단. 미해결은 sl 역산 왜곡.

**추가 가드 안**:
```python
# sl 역산 후 config sl보다 너무 좁으면(예: config sl의 50% 미만) config sl로 대체
if stop_loss_rate is not None and self.strategy:
    cfg_sl = ...  # config sl 조회
    if cfg_sl and stop_loss_rate < cfg_sl * 0.5:
        stop_loss_rate = cfg_sl  # config sl로 교체
```

**회귀 범위**: 낮음(추가 로직만). 그러나 왜곡이 완전히 제거되지 않음 — gap이 작을 때는 미세 편차가 계속 발생하며 백테스트 정합은 여전히 달성 안 됨. STOP_LOSS_FLOOR 3%는 현 코드에서 이미 일부 방어 중.

---

### 권고 결론

**옵션 α 권고**: 2순위 완전 제거.

근거:
1. Signal.target_price/stop_loss 절대가는 진입 주문 가격, 지정가 밴드, DB 저장에 사용되지 않는다(확정). 2순위가 유일한 사용처이므로 제거 side-effect가 없다.
2. 8전략 모두 target_price/stop_loss를 `price × (1±config%)` 형태로 설정한다(확정). 이는 config%와 같은 정보를 절대가로 포장한 것일 뿐이다. 2순위 역산 결과가 config%와 항상 같아야 하지만, 체결 시점의 가격 이동으로 매번 달라진다.
3. DB 실측 239건 중 92.5%가 2순위 채택 → Signal 절대가가 tp/sl 결정의 사실상 주경로가 되어 있음. 그 결과 갭 편차가 상시 발생.
4. 백테스트는 진입가 기준 고정%이므로, 라이브도 진입가 기준 고정%(optionα = 3순위 직행)가 정합.

**재현 테스트 설계**:
- `test_decision_engine.py`에 "Signal.target_price/stop_loss 설정 시 3순위(config%)로 처리되는지" 케이스 추가
- mock buy_price = ref_close * 1.05 (갭업 5%) 시나리오에서 tp = config_tp, sl = config_sl 검증
- FLOOR 3% binding 케이스: config_sl=0.02 → FLOOR=0.03 으로 clamp 검증

---

## 6. 잔여 불확실성

| 항목 | 확정/추정 | 내용 |
|------|---------|------|
| 7전략 current_price 기준 | **확정** | 코드에서 직접 확인(data["close"].iloc[-1]) |
| book_envelope_200d ref_close 기준 | **확정** | strategy.py:267 `ref_close = float(df["close"].astype(float).iloc[-1])` with df=quant 일봉 |
| 2순위 유일 사용처 | **확정** | grep 전수조사, target_price/stop_loss 절대가 사용 위치 1곳만 |
| DB gap 통계 | **확정** | virtual_trading_records 239건 실측 |
| FLOOR binding 16건 | **확정** | sl_rate=0.03 정확히 일치하는 건 카운트 |
| tp 음수 1건(089970) | **확정** | DB에서 직접 확인(-0.018763) |
| 옵션α 후 테스트 케이스 수정 필요 여부 | **추정** | test_decision_engine.py를 직접 분석하지 않음. 2순위 관련 테스트 존재 시 수정 필요 |
| 실전(real trading) 경로에서의 동일 적용 여부 | **확정** | trading_decision_engine.py:442-447에서 동일 virtual_buy 호출 경로 확인. 가상/실전 동일 코드 경유 |

---

*파일: `docs/superpowers/plans/2026-06-25-D-signal-rate-findings.md`*