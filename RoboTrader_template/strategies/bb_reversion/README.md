# BB Reversion Strategy — 볼린저밴드 하단 매수, 중심선 매도

## 개요

| 항목 | 내용 |
|------|------|
| 클래스 | `BBReversionStrategy` |
| 버전 | 1.0.0 |
| 설명 | 볼린저밴드 하단 매수, 중심선 매도 — 횡보장(ADX<20) 특화 |
| 대상 | 저변동성 섹터 (은행, 보험, 유틸리티, 식품, 통신, 배당주) |

### 매수 조건 (모두 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | BB 하단 터치 | 현재가 ≤ BB 하단 (20일, 2시그마) |
| 2 | RSI 과매도 | RSI(14) < 40 |
| 3 | 횡보 확인 | ADX(14) < 20 |
| 4 | 거래량 증가 | 거래량 ≥ 20일 평균의 1.2배 |

### 매도 조건 (1개 이상 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | BB 중심선 도달 | SMA(20) 도달 (주요 목표) |
| 2 | 익절 | 수익률 +5% |
| 3 | 손절 | 수익률 -3% |
| 4 | 보유 기간 초과 | 최대 15일 |
| 5 | 추세 전환 | ADX > 30 시 즉시 매도 |

## 파일 구조

```
strategies/bb_reversion/
├── config.yaml    # 전략 파라미터 + 스크리닝 설정
├── strategy.py    # 전략 로직 구현
├── screener.py    # 섹터 종목 스크리닝
└── README.md      # 이 파일
```

## 설정 (config.yaml)

주요 설정값을 `config.yaml`에서 조정할 수 있습니다:

```yaml
parameters:
  bb_period: 20
  bb_std: 2.0
  rsi_period: 14
  rsi_oversold: 40
  adx_period: 14
  adx_max: 20          # 횡보 판단 기준
  adx_exit: 30         # 추세 전환 매도
  volume_ratio_min: 1.2
  volume_ma_period: 20

risk_management:
  stop_loss_pct: 0.03       # 손절 3%
  take_profit_pct: 0.05     # 익절 5%
  max_holding_days: 15
  max_positions: 5
  max_daily_trades: 10

screening:
  target_sectors: [bank, insurance, utility, food, telecom, dividend]
```

## 특징

- `evaluate_buy_conditions` / `evaluate_sell_conditions`가 `@staticmethod`로 분리되어 시뮬레이션에서도 동일 로직 사용 가능
- `screener.py`를 통해 대상 섹터 종목을 자동 스크리닝
