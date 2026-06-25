# 같은날 청산 인과추적 findings
> 작성: 2026-06-25 | 추적 대상: envelope(book_envelope_200d) · daytrading(daytrading_3methods_breakout)

---

## 1. 같은날 BUY→SELL 전체 레코드 (DB 직접 추출)

| 날짜 | 종목 | 전략 | 매수시각 | 매도시각 | 매수가 | 매도가 | 수익률 | 로그 확인 사유 |
|------|------|------|----------|----------|--------|--------|--------|---------------|
| 2026-06-10 | 069960 | envelope | 09:05:11 | 11:54:45 | 162,500 | 170,400 | +4.86% | **공통 트레일링 스톱** |
| 2026-06-10 | 000430 | daytrading | 09:01:20 | 13:25:36 | 5,990 | 5,400 | -9.85% | **손절 실행** (stop_loss_rate=9.85%) |
| 2026-06-11 | 006220 | daytrading | 09:01:22 | 09:06:49 | 13,150 | 13,500 | +2.66% | **공통 트레일링 스톱** |
| 2026-06-11 | 002630 | daytrading | 09:07:47 | 09:41:40 | 815 | 872 | +6.99% | **공통 트레일링 스톱** |
| 2026-06-11 | 004170 | envelope | 09:20:04 | 10:58:56 | 677,000 | 701,000 | +3.55% | **공통 트레일링 스톱** |
| 2026-06-12 | 085620 | envelope | 09:05:16 | 09:06:53 | 28,150 | 26,650 | -5.33% | **손절 실행** (stop_loss_rate=4.08%) |
| 2026-06-12 | 089970 | envelope | 09:09:26 | 09:09:36 | 95,400 | 96,200 | +0.84% | **목표 익절 도달** (target_profit_rate=-1.88%) |
| 2026-06-12 | 222800 | envelope | 09:01:20 | 10:18:19 | 140,000 | 128,700 | -8.07% | **전략 매도신호** (손절 -8.1%) |
| 2026-06-15 | 011280 | daytrading | 09:08:17 | 11:46:37 | 2,035 | 2,085 | +2.46% | **공통 트레일링 스톱** (추정, 로그 미확인) |
| 2026-06-15 | 093370 | envelope | 09:04:17 | 09:09:22 | 19,850 | 20,250 | +2.02% | **공통 트레일링 스톱** |
| 2026-06-15 | 140860 | envelope | 09:11:33 | 09:22:05 | 279,500 | 271,000 | -3.04% | **손절 실행** (stop_loss_rate=3.0%, 하한 적용) |
| 2026-06-15 | 403870 | envelope | 09:01:04 | 09:53:43 | 69,700 | 77,000 | +10.47% | **전략 매도신호** (익절 +10.0% — 정상 tp) |
| 2026-06-16 | 330860 | envelope | 09:04:57 | 09:44:46 | 58,700 | 54,000 | -8.01% | **전략 매도신호** (손절 -8.0% — 정상 sl) |
| 2026-06-24 | 034940 | daytrading | 09:01:53 | 13:35:15 | 856 | 1,000 | +16.82% | 정상 tp 도달 |
| 2026-06-24 | 067290 | daytrading | 09:09:07 | 14:12:58 | 2,800 | 2,715 | -3.04% | 정상 sl 도달 |
| 2026-06-24 | — | — | — | — | — | — | — | (나머지 14950·045520 등은 익일 매도) |

---

## 2. 확정 코드경로별 분류

### 경로 A: 공통 트레일링 스톱 (비정상 — 수정 완료)

**발생 사례**: 069960, 006220, 002630, 004170, 093370 (af40db9 이전 발생)

**코드 경로 (구버전, af40db9 이전)**:
`core/trading/position_monitor.py` `_analyze_sell_for_stock()`:
```
# 구버전: strategy_for_sell 존재 여부 무관하게 무조건 트레일링 체크
self._check_trailing_stop(trading_stock, current_price, buy_price, profit_rate)
if trading_stock.trailing_stop_activated:
    if current_price <= trailing_stop_price:
        → _execute_sell()  # 전략 tp/sl 도달 전에 선점
```

**root cause**: 우선순위 `stale > max_holding > trailing > tp > sl` 구조에서 trailing이 tp/sl보다 앞에 위치했고, `strategy_for_sell is None` 가드가 없었음.

**수정**: `af40db9` (2026-06-24) — `if strategy_for_sell is None:` 가드 추가로 전략-소유 포지션에는 공통 트레일링 미적용. 현재 코드에서 이 경로는 차단됨.

---

### 경로 B: 음수 target_profit_rate → 매수 직후 즉시 익절 (비정상 — 현존 버그)

**발생 사례**: 089970 (2026-06-12 09:09:26 매수 → 09:09:36 10초 후 청산, +0.84%)

**로그 직접 증거**:
```
09:09:26 | 가상매수: 089970 10주 @95,400 (익절:-1.9% 손절:17.9%)
09:09:36 | 089970 익절 신호: 목표 익절 도달 (0.84% >= -1.88%)
```

**생성 경로** (`core/trading_decision_engine.py` L537-538):
```python
# [2순위] Signal의 target_price → 비율 변환
if target_profit_rate is None and signal and signal.target_price and buy_price > 0:
    target_profit_rate = (signal.target_price - buy_price) / buy_price
```

`BookEnvelope200dStrategy._check_buy()` (L268-269):
```python
ref_close = float(df["close"].astype(float).iloc[-1])  # 전일 확정 종가 기준
target = ref_close * (1 + self._take_profit_pct)        # 전일종가 × 1.10
```

**수치 재현**:
- 전일 확정 종가(ref_close) = 85,100원
- signal.target_price = 85,100 × 1.10 = 93,610원
- 실제 체결가(buy_price) = 95,400원 (갭업 체결)
- target_profit_rate = (93,610 - 95,400) / 95,400 = **-1.88%** (음수)
- 결과: `profit_rate 0.84% >= target_profit_rate -1.88%` → 매수 즉시 참

**check 코드** (`position_monitor.py` L307-308):
```python
if hasattr(trading_stock, 'target_profit_rate') and trading_stock.target_profit_rate:
    if profit_rate >= trading_stock.target_profit_rate:
        → _execute_sell()
```

`trading_stock.target_profit_rate` 조건은 `bool(-1.88%)` = True (0이 아니므로), 따라서 음수 target_profit_rate도 체크에 진입함.

**현존 여부**: 현재 코드에서 수정되지 않음. 갭업 체결 시마다 재현 가능.

---

### 경로 C: 정상 tp/sl 체결 (허용 — 옵션3 기준)

**사례**: 403870(+10.47%, 전략 매도신호 tp), 330860(-8.0%, 전략 매도신호 sl), 222800(-8.1%, 전략 매도신호 sl), 034940(+16.82%), 067290(-3.04%)

이들은 `position_monitor.py` L307-315 (tp 체크) 또는 L329-357 (전략 generate_signal SELL) 경로를 통해 실제 설정된 tp/sl 임계에 도달한 정상 청산임. 옵션3 기준 제거 대상이 아님.

---

### 경로 D: 손절률 heuristic 적용 → 타이트 손절 (경계 사례)

**사례**: 085620 (손절 -5.33% <= -4.08%), 140860 (손절 -3.04% <= -3.00%)

140860은 손절 하한 3.0% 강제 적용(`STOP_LOSS_FLOOR=0.03`) 결과 손절률이 3.0%로 narrowed되어 조기 청산됨. 이는 의도된 정책(2026-05-14 결정)이므로 제거 대상이 아님. 단, 손절률이 전략 설계 sl(8%)보다 훨씬 좁게 산정된 근본 원인(signal.stop_loss가 ref_close 기준이므로 갭업 체결시 heuristic 오류 발생)은 경로 B와 동일 구조.

---

## 3. 가설별 증거 요약

### 가설 P1: is_stale 오분류 → 조기 청산
- **증거 없음**: 로그에서 "장기보유 종목 우선 청산" 문자열 발견 0건
- **down-rank**: 당일 매수 종목에 days_held≥STALE_POSITION_DAYS(30)는 수학적으로 불가. 기각.

### 가설 P2: owner_strategy=None → 공통 트레일링 선점
- **확정 (구버전)**: 069960, 006220, 002630, 004170, 093370 — 로그에서 "트레일링 스톱 매도" 직접 확인
- **단, af40db9 이후 차단됨**: 현 코드에서 `if strategy_for_sell is None:` 가드로 전략-소유 포지션은 트레일링 비적용
- **현재 활성 여부**: 아니오 (2026-06-24 수정 완료)

### 가설 P3: 정상 tp/sl 경로 (옵션3 허용)
- **확정 (정상)**: 403870, 330860, 222800 등 — 실제 tp/sl 임계 도달
- **제거 불필요**

### 가설 P_NEW: 음수 target_profit_rate → 즉시 익절 트리거
- **확정 (현존 버그)**: 089970 — 로그에서 "익절:-1.9%", "목표 익절 도달 (0.84% >= -1.88%)" 직접 확인
- **현재 활성**: 예. 갭업 체결 시(체결가 > signal.target_price) 재현 가능

---

## 4. 현재 상태 요약

| 경로 | 설명 | 현재 상태 | 제거 대상 |
|------|------|-----------|-----------|
| A (트레일링) | 전략-소유 포지션에 공통 트레일링 선점 | af40db9에서 수정 완료 | 완료 |
| B (음수 tp) | 갭업 체결 시 target_profit_rate 음수화 → 즉시 청산 | **현존, 미수정** | **YES** |
| C (정상 tp/sl) | 전략 설계 tp/sl 도달 | 정상 | NO |
| D (타이트 sl) | STOP_LOSS_FLOOR 또는 signal.stop_loss 기준 타이트 | 의도된 정책 | NO |

---

## 5. 옵션3 기준 최소 수정 권고

### 수정 대상: 경로 B (음수 target_profit_rate)

**파일**: `core/trading_decision_engine.py`

**문제 위치** (L537-538):
```python
if target_profit_rate is None and signal and signal.target_price and buy_price > 0:
    target_profit_rate = (signal.target_price - buy_price) / buy_price
    # ← buy_price > signal.target_price 시 음수 생성, 무방어
```

**권고 수정**:
```python
if target_profit_rate is None and signal and signal.target_price and buy_price > 0:
    _tp = (signal.target_price - buy_price) / buy_price
    if _tp > 0:  # 갭업 체결로 target_price < buy_price인 경우 무시, 전략 config/default로 fallback
        target_profit_rate = _tp
    # 음수(갭업 체결)는 None으로 유지 → 3순위(전략 config)·4순위(default 15%)로 낙하
```

**파일**: `core/trading/position_monitor.py`

**보조 방어** (L307-308) — 음수 tp가 어떤 경로로든 들어오는 경우 방어:
```python
# 현재:
if hasattr(trading_stock, 'target_profit_rate') and trading_stock.target_profit_rate:

# 권고:
if hasattr(trading_stock, 'target_profit_rate') and trading_stock.target_profit_rate \
        and trading_stock.target_profit_rate > 0:
```

### 재현 테스트 설계

```python
# test_framework_negative_tp_rate.py
# 시나리오: signal.target_price = 93,610, buy_price = 95,400 (갭업)
# 기대: target_profit_rate는 음수가 되지 않고 전략 config tp 또는 DEFAULT로 낙하
def test_negative_target_price_gaps_up_does_not_set_negative_tp():
    signal = Signal(target_price=93_610, stop_loss=87_900, ...)
    buy_price = 95_400
    # execute_virtual_buy 경로에서 target_profit_rate > 0 보장 검증
    assert trading_stock.target_profit_rate > 0
    
# 시나리오: 음수 tp가 TradingStock에 있어도 position_monitor가 매도 스킵
def test_position_monitor_skips_sell_when_tp_negative():
    trading_stock.target_profit_rate = -0.019
    # _analyze_sell_for_stock 호출 시 익절 체크에서 매도 안 됨
    assert not sell_triggered
```

---

## 6. 잔여 불확실성

1. **011280 (2026-06-15, daytrading +2.46%)**: 로그 grep에서 트레일링 확인 못함. 트레일링(af40db9 이전)으로 추정하나 로그 직접 확인 필요. 해당 날짜 로그에서 `011280 트레일링` 검색 권고.

2. **경로 B 재발 빈도**: 갭업 체결(signal.target_price < 체결가) 빈도에 의존. 스크리너가 전일 종가 기준 target_price를 계산하고 실제 시가가 갭업되면 항상 재현됨. 특히 장 시작 직후 5분(gap-up 빈발 시간대)에 집중.

3. **경로 D(signal.stop_loss 기준 타이트 손절)**의 정책 적정성: 갭업 체결 시 signal.stop_loss도 ref_close 기준이므로 stop_loss_rate 역시 실제보다 넓게 산정됨(반대 방향). 이는 옵션3 제거 대상은 아니나 백테스트 정합 이슈로 별도 추적 권고.

---

## 7. 핵심 결론

**같은날 비정상 청산의 실제 원인은 두 가지였다:**

1. **경로 A (과거, 수정 완료)**: `af40db9` 이전, `position_monitor` 트레일링 체크에 `strategy_for_sell is None` 가드 부재 → 전략-소유 포지션에도 공통 트레일링(+5%/-3%) 선점. 2026-06-10~2026-06-15의 트레일링 사례 5건 해당. **현재 코드에서 해결됨.**

2. **경로 B (현존, 미수정)**: `execute_virtual_buy`에서 `signal.target_price`(전일종가 기준)를 실제 체결가(갭업)로 나누어 target_profit_rate가 음수로 산정됨 → `position_monitor` L307 체크가 `profit_rate >= 음수`를 즉시 만족 → 매수 10초 후 청산. 089970(2026-06-12) 확정, 갭업 체결 시 재현 가능한 현존 버그. **최소 수정 필요.**

**P1(is_stale), 기타 경로는 증거 없음으로 기각.**
