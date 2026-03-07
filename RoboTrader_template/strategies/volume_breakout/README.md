# Volume Breakout Strategy — 거래량 폭증 돌파 매매

## 개요

거래량 10배 폭증 + 양봉 발생 시 돌파 매매를 실행하는 전략입니다.

- **클래스**: `VolumeBreakoutStrategy`
- **버전**: 1.0.0

### 매수 조건 (모두 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | 거래량 폭증 | 당일 거래량 >= 20일 평균의 10배 |
| 2 | 양봉 | 종가 > 시가 |
| 3 | 봉 크기 | 시가 대비 종가 상승률 >= 1.0% |

### 매도 조건 (1개 이상 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | 익절 | 수익률 +10% 도달 |
| 2 | 손절 | 수익률 -5% 도달 |
| 3 | 보유기간 초과 | 5일 초과 보유 |
| 4 | 거래량 급감 | 전일 대비 거래량 50% 이하 |

## 파일 구조

```
strategies/volume_breakout/
├── config.yaml    # 전략 파라미터 설정
├── strategy.py    # 전략 로직 구현
└── README.md      # 이 파일
```

## 설정 (config.yaml)

주요 설정값을 `config.yaml`에서 조정할 수 있습니다:

```yaml
parameters:
  volume_avg_period: 20        # 평균 거래량 기간
  volume_multiplier: 10.0      # 거래량 폭증 배수
  require_bullish_candle: true  # 양봉 조건
  min_candle_body_pct: 1.0     # 최소 봉 크기 (%)
  max_holding_days: 5

risk_management:
  max_position_size: 0.08      # 보수적 (변동성 큰 종목)
  stop_loss_pct: 0.05          # 손절 5%
  take_profit_pct: 0.10        # 익절 10%
  max_daily_trades: 3
```

## 주의사항

- 거래량 폭증 종목은 변동성이 크므로 `max_position_size`를 0.08(8%)로 보수적 설정
- `BaseStrategy`의 추상 메서드 5개를 **모두** 구현해야 합니다
- 클래스 이름은 반드시 `Strategy`로 끝나야 로더가 인식합니다
- `config.yaml`과 `strategy.py`가 모두 있어야 유효한 전략으로 인식됩니다
