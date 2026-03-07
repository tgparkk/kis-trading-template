# 퀀트 전략: 동적 손익비 관리

> 퀀트 팩터 전략에서 종목 품질에 따라 익절/손절률을 동적으로 조정하는 메커니즘을 설명합니다.
> 이 문서는 **퀀트 전략 구현의 참고 문서**이며, kis-template 프레임워크 공통 기능이 아닙니다.

---

## 1. 동적 조정 개요

### ⚙️ 매일 동적 조정 (09:05 리밸런싱)

**핵심 개념**: 종목의 **품질과 기대수익에 따라 차등 관리**

```
고품질 종목 (S등급)
→ 높은 기대수익
→ 높은 익절률 (20%)
→ 낮은 손절률 (8%)
→ 큰 수익 기회, 작은 손실 허용

저품질 종목 (B등급)
→ 낮은 기대수익
→ 낮은 익절률 (15%)
→ 높은 손절률 (10%)
→ 작은 수익도 확보, 손실 빠르게 차단
```

매일 09:05 리밸런싱 시, 퀀트 스크리닝 결과(08:55 계산)를 기반으로 각 종목의 복합 점수를 계산하고, 등급에 따라 익절/손절률을 차등 설정합니다. 이미 보유 중인 유지 종목도 새 점수로 목표값이 갱신됩니다.

---

## 2. 계산 프로세스

### Step 1: DB에서 데이터 읽기

09:05 리밸런싱 시 다음 데이터를 DB에서 조회:

```python
# 1) 퀀트 포트폴리오 조회
portfolio = db_manager.get_quant_portfolio(
    calc_date="20251228",  # 오늘 08:55 스크리닝 결과
    limit=30
)

# 결과:
[
    {
        'stock_code': '005930',
        'stock_name': '삼성전자',
        'rank': 1,
        'total_score': 85.2,  # ⭐ 종합 점수
        ...
    },
    ...
]

# 2) 팩터 점수 조회
factor_scores = db_manager.get_factor_scores(
    calc_date="20251228",
    stock_code="005930"
)

# 결과:
{
    'value_score': 75.3,
    'momentum_score': 92.1,    # ⭐ Momentum 점수
    'quality_score': 88.6,
    'growth_score': 79.4,
    'total_score': 85.2,
    'factor_rank': 1
}
```

**코드 위치**:
- `db/database_manager.py` - `get_quant_portfolio()`
- `db/database_manager.py` - `get_factor_scores()`

---

### Step 2: API 호출 (현재가 조회)

리밸런싱 시 매수 주문을 위해 현재가를 조회:

```python
from api.kis_market_api import get_current_price

# 현재가 API 조회
current_price_info = get_current_price("005930")

# 결과:
{
    'current_price': 70000,
    'change_rate': 1.5,
    'volume': 12345678,
    ...
}
```

**용도**:
- 매수 주문 시 현재가 기준으로 주문
- 목표 익절가/손절가 계산에는 사용 안 함 (비율로 관리)

---

### Step 3: 복합 점수 계산

종목별로 3가지 지표를 결합한 복합 점수 계산:

```python
# 1. 순위 점수 (1위=100점, 50위=0점)
rank_score = (51 - rank) / 50 * 100
# 예: rank=1 → rank_score=100
#     rank=25 → rank_score=52
#     rank=50 → rank_score=2

# 2. 종합 점수 정규화 (0-100 범위)
score_normalized = max(0, min(100, total_score))
# 예: total_score=85.2 → score_normalized=85.2

# 3. Momentum 점수 정규화 (0-100 범위)
momentum_normalized = max(0, min(100, momentum_score))
# 예: momentum_score=92.1 → momentum_normalized=92.1

# 4. 가중 평균 (기본값: 순위 40%, 점수 30%, Momentum 30%)
composite_score = (
    rank_score * 0.40 +
    score_normalized * 0.30 +
    momentum_normalized * 0.30
)

# 예시 계산:
# rank=1, total_score=85.2, momentum_score=92.1
# composite_score = 100*0.4 + 85.2*0.3 + 92.1*0.3
#                 = 40 + 25.56 + 27.63
#                 = 93.19 → S등급
```

**코드 위치**: `core/quant/target_profit_loss_calculator.py`

---

### Step 4: 등급별 목표 설정

복합 점수에 따라 차등 목표 설정:

```python
if composite_score >= 80:
    return 0.20, 0.08  # S등급: 익절 20%, 손절 8%
elif composite_score >= 65:
    return 0.17, 0.09  # A등급: 익절 17%, 손절 9%
elif composite_score >= 50:
    return 0.15, 0.10  # B등급: 익절 15%, 손절 10%
elif composite_score >= 35:
    return 0.13, 0.10  # C등급: 익절 13%, 손절 10%
else:
    return 0.12, 0.10  # D등급: 익절 12%, 손절 10%
```

**코드 위치**: `core/quant/target_profit_loss_calculator.py`

---

### Step 5: DB 저장 및 메모리 설정

계산된 목표값을 DB와 메모리에 저장:

```python
# 1) 매수 주문 실행 (virtual_trading_records에 저장)
db_manager.save_virtual_buy(
    stock_code="005930",
    stock_name="삼성전자",
    quantity=100,
    price=70000,
    target_profit_rate=0.20,  # ⭐ S등급
    stop_loss_rate=0.08,      # ⭐ S등급
    strategy="Quant Rebalancing",
    reason="S등급 (복합점수 93.2점)"
)

# 2) 메모리 객체에도 설정
trading_stock.target_profit_rate = 0.20
trading_stock.stop_loss_rate = 0.08
```

**코드 위치**:
- `core/helpers/rebalancing_executor.py`
- `db/database_manager.py`

---

## 3. 등급별 목표 설정

| 등급 | 복합점수 | 익절률 | 손절률 | 특징 |
|------|---------|--------|--------|------|
| **S** | 80+ | 20% | 8% | 최고 품질, 큰 수익 추구 |
| **A** | 65-80 | 17% | 9% | 고품질, 적극적 관리 |
| **B** | 50-65 | 15% | 10% | 중간 품질, 균형 관리 |
| **C** | 35-50 | 13% | 10% | 보수적 관리 |
| **D** | 35 미만 | 12% | 10% | 최소 기대, 빠른 손절 |

**설계 의도**:
- 높은 점수 → 높은 익절, 낮은 손절 (리스크 감수)
- 낮은 점수 → 낮은 익절, 높은 손절 (보수적)

---

## 4. 실제 계산 예시

### 📌 종목 A (삼성전자, 1위)

```
DB 읽기:
- rank: 1
- total_score: 85.2
- momentum_score: 92.1

복합 점수 계산:
- rank_score: 100 (1위 → 100점)
- composite_score: 100*0.4 + 85.2*0.3 + 92.1*0.3 = 93.19

등급: S등급 (93.19 ≥ 80)

목표 설정:
- target_profit_rate: 0.20 (20%)
- stop_loss_rate: 0.08 (8%)

매수 실행:
- 현재가: 70,000원
- 수량: 100주
- 익절가: 84,000원 (70,000 * 1.20)
- 손절가: 64,400원 (70,000 * 0.92)

DB 저장:
- virtual_trading_records 테이블에 기록
- target_profit_rate, stop_loss_rate 포함
```

### 📌 종목 B (중소형주, 25위)

```
DB 읽기:
- rank: 25
- total_score: 55.8
- momentum_score: 48.2

복합 점수 계산:
- rank_score: 52 (25위 → 52점)
- composite_score: 52*0.4 + 55.8*0.3 + 48.2*0.3 = 51.96

등급: B등급 (50 ≤ 51.96 < 65)

목표 설정:
- target_profit_rate: 0.15 (15%)
- stop_loss_rate: 0.10 (10%)

매수 실행:
- 현재가: 50,000원
- 수량: 80주
- 익절가: 57,500원 (50,000 * 1.15)
- 손절가: 45,000원 (50,000 * 0.90)
```

---

## 5. 유지 종목 목표 갱신

리밸런싱 시 **계속 보유하는 종목**도 새 점수로 익절/손절률을 갱신합니다.

### 🔁 keep_list_updater 동작

```python
# core/helpers/keep_list_updater.py

for keep_item in keep_list:
    # 새 점수로 목표 재계산
    new_target_profit_rate, new_stop_loss_rate = calculator.calculate(
        rank=keep_item['new_rank'],
        total_score=keep_item['new_total_score'],
        momentum_score=keep_item['new_momentum_score']
    )

    # 메모리 업데이트
    trading_stock.target_profit_rate = new_target_profit_rate
    trading_stock.stop_loss_rate = new_stop_loss_rate

    # DB 업데이트 (매수 기록 갱신)
    db_manager.update_virtual_buy_targets(
        buy_record_id=keep_item['buy_record_id'],
        target_profit_rate=new_target_profit_rate,
        stop_loss_rate=new_stop_loss_rate
    )
```

**갱신 예시**:
```
어제: 10위 (A등급, 익절 17%, 손절 9%)
오늘: 5위 (S등급, 익절 20%, 손절 8%)
→ 목표율 갱신! (더 높은 익절, 더 낮은 손절)
```

**코드 위치**: `core/helpers/keep_list_updater.py`

---

## 6. 데이터 흐름 요약

```
[DB 읽기]
quant_portfolio → rank, total_score
quant_factor_scores → momentum_score
    ↓
[API 호출]
get_current_price() → 현재가 (매수 주문용)
    ↓
[계산]
복합 점수 = rank*0.4 + total_score*0.3 + momentum*0.3
    ↓
[등급 분류]
S(80+), A(65-80), B(50-65), C(35-50), D(<35)
    ↓
[목표 설정]
등급별 차등 익절률/손절률
    ↓
[저장]
DB: virtual_trading_records (target_profit_rate, stop_loss_rate)
메모리: TradingStock 객체
    ↓
[모니터링]
1분마다 현재가 조회 → 목표가 도달 체크 → 매도
```

### 🎯 핵심 요약

1. **매일 09:05** 리밸런싱 시 동적 조정
2. **DB 데이터**: 순위, 종합 점수, Momentum 점수
3. **API 데이터**: 현재가 (매수 주문용)
4. **복합 점수**: 3가지 지표를 가중 평균 (40% + 30% + 30%)
5. **5단계 등급**: S/A/B/C/D (차등 관리)
6. **DB 저장**: 익절/손절률을 virtual_trading_records에 기록
7. **재시작 복원**: DB에서 목표율 읽어서 모니터링 재개

---

**마지막 업데이트**: 2026-03-07
