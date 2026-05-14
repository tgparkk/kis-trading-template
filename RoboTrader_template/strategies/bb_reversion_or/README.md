# BB Reversion Strategy — OR-relaxed (BB ∧ (RSI ∨ VOL) ∧ ADX)

> **실험 전략**: `bb_reversion`의 4-AND 진입 조건이 신호를 과도하게 억제함을
> Stage 1 그리드 탐색(평균 0.5건/종목/년)으로 확인 후, OR 완화 변형을 격리 실험.
> **라이브 봇에 영향 없음** — `bb_reversion/` 파일은 일절 수정하지 않음.

## 개요

| 항목 | 내용 |
|------|------|
| 클래스 | `BBReversionORStrategy` |
| 버전 | 1.0.0-or |
| 설명 | BB ∧ (RSI ∨ VOL) ∧ ADX — 진입 조건 OR 완화 실험 변형 |
| 기반 | `bb_reversion/BBReversionStrategy` (매도 로직 동일) |
| 대상 | 저변동성 섹터 (은행, 보험, 유틸리티, 식품, 통신, 배당주) |

## 원본 vs OR 변형 비교

| 원본 `bb_reversion` (4-AND) | 이 전략 `bb_reversion_or` (OR 완화) |
|----------------------------|-------------------------------------|
| BB ∧ RSI ∧ ADX ∧ VOL       | BB ∧ **(RSI ∨ VOL)** ∧ ADX          |

### 매수 조건

| # | 조건 | 필수/선택 |
|---|------|---------|
| 1 | BB 하단 터치 — 현재가 ≤ BB 하단 (20일, 2시그마) | **필수** |
| 2 | RSI(14) < 과매도 임계값 **OR** 거래량 ≥ 평균의 배수 | **하나 이상** |
| 3 | 횡보 확인 — ADX(14) < adx_max | **필수** |

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
