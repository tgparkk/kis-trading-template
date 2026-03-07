# Mean Reversion Strategy — MA20 평균회귀

## 개요

MA20 대비 과도한 이탈 시 매수하고, 평균 복귀 시 매도하는 전략입니다.

- **클래스**: `MeanReversionStrategy`
- **버전**: 1.0.0

### 매수 조건 (모두 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | MA 이탈 | 현재가가 MA20 대비 -10% 이상 이탈 |
| 2 | RSI 과매도 (선택) | RSI(14) < 30 (과매도 확인 필터) |

### 매도 조건 (1개 이상 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | MA 복귀 | 이탈 거리의 90% 이상 회복 |
| 2 | 익절 | +12% 도달 |
| 3 | 손절 | -7% 도달 |

## 파일 구조

```
strategies/mean_reversion/
├── config.yaml    # 전략 파라미터 설정
├── strategy.py    # 전략 로직 구현
└── README.md      # 이 파일
```

## 설정 (config.yaml)

주요 설정값을 `config.yaml`에서 조정할 수 있습니다:

```yaml
parameters:
  ma_period: 20              # 이동평균 기간
  entry_deviation_pct: -10.0 # MA 대비 이탈률 (%)
  exit_recovery_ratio: 0.9   # MA 복귀 비율 (0~1)
  use_rsi_filter: true       # RSI 필터 사용 여부
  rsi_period: 14
  rsi_oversold: 30

risk_management:
  stop_loss_pct: 0.07        # 손절 7%
  take_profit_pct: 0.12      # 익절 12%
  max_daily_trades: 5
```
