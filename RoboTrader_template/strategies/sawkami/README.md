# Sawkami Strategy — 사와카미 투신 스타일 가치투자

## 개요

실적 성장 + 저평가 + 과매도 종목을 매수하는 가치투자 전략입니다. 재무 데이터(KIS Financial API) 기반으로 후보를 스크리닝하고, 기술적 지표로 진입 타이밍을 잡습니다.

- **클래스**: `SawkamiStrategy`
- **버전**: 1.0.0

### 매수 조건 (5개 모두 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | 영업이익 성장 | 영업이익 YoY 성장률 >= 30% |
| 2 | 52주 고점 대비 하락 | 52주 고점 대비 -20% 이상 하락 |
| 3 | 저PBR | PBR < 1.5 (현재가/BPS) |
| 4 | 거래량 급증 | 거래량 >= 20일 평균의 1.5배 |
| 5 | RSI 과매도 | RSI(14) < 30 |

### 매도 조건 (1개 이상 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | 익절 | 수익률 +15% 도달 |
| 2 | 손절 | 수익률 -15% 도달 |
| 3 | 보유 기한 초과 | 최대 보유일 40일 초과 |

## 파일 구조

```
strategies/sawkami/
├── config.yaml    # 전략 파라미터 + DB 설정
├── strategy.py    # 전략 로직 구현
├── screener.py    # 후보 종목 스크리닝
├── db_manager.py  # 전용 매매 기록 DB
└── README.md      # 이 파일
```

## 설정 (config.yaml)

주요 설정값을 `config.yaml`에서 조정할 수 있습니다:

```yaml
parameters:
  op_income_growth_min: 30.0  # 영업이익 성장률 (%)
  high52w_drop_pct: -20.0     # 52주 고점 대비 하락률
  high52w_period: 252         # 52주 = 252거래일
  pbr_max: 1.5                # PBR 상한
  volume_ratio_min: 1.5       # 거래량 배수
  volume_ma_period: 20
  rsi_period: 14
  rsi_oversold: 30

risk_management:
  max_positions: 10
  take_profit_pct: 0.15       # 익절 15%
  stop_loss_pct: 0.15         # 손절 15%
  max_hold_days: 40           # 최대 보유일
  max_daily_trades: 5
  max_daily_loss_pct: 5.0     # 일일 최대 손실 제한
  max_per_stock_amount: 5000000  # 종목당 최대 투자금액
```

## 특징

- **재무 데이터 기반**: KIS Financial API로 영업이익/PBR 등 조회
- **후보 스크리닝**: 장시작 시 `SawkamiCandidateSelector`가 조건 충족 종목 필터링
- **전용 DB**: `SawkamiDBManager`로 매매 기록 관리, 보유 포지션 자동 복원
- **일일 손실 제한**: 누적 실현손실 5% 초과 시 매수 중단
