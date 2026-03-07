# Lynch Strategy — 피터 린치 PEG 기반 가치+성장 전략

## 개요

| 항목 | 내용 |
|------|------|
| 클래스 | `LynchStrategy` |
| 버전 | 1.0.0 |
| 설명 | 피터 린치 PEG 기반 가치+성장 전략 |
| 추가 모듈 | `screener.py` (후보 스크리닝), `db_manager.py` (전용 DB) |

## 매수 조건 (모두 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | PEG <= 0.3 | PER / 영업이익성장률(%) |
| 2 | 영업이익 YoY >= 70% | 전년 대비 영업이익 성장률 |
| 3 | 부채비율 <= 200% | 재무 안정성 필터 |
| 4 | ROE >= 5% | 자기자본이익률 하한 |
| 5 | RSI(14) < 35 | 과매도 구간 진입 |
| 6 | PER > 0, 영업이익 > 0 | 적자 기업 제외 |

## 매도 조건 (1개 이상 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | 익절 | 수익률 +50% 도달 |
| 2 | 손절 | 수익률 -15% 도달 |
| 3 | 최대 보유 | 120거래일 초과 |

## 파일 구조

```
strategies/lynch/
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
  peg_max: 0.3                # PEG 상한
  op_income_growth_min: 70.0  # 영업이익 성장률 (%)
  debt_ratio_max: 200.0       # 부채비율 상한 (%)
  roe_min: 5.0                # ROE 하한 (%)
  rsi_period: 14
  rsi_oversold: 35

risk_management:
  max_positions: 5
  take_profit_pct: 0.50       # 익절 50%
  stop_loss_pct: 0.15         # 손절 15%
  max_hold_days: 120          # 최대 보유일
  max_daily_trades: 5
  max_daily_loss_pct: 5.0     # 일일 최대 손실 제한
  max_per_stock_amount: 3000000  # 종목당 최대 투자금액
```

## 특징

- **재무 데이터 기반**: KIS Financial API를 통해 PEG/ROE/부채비율 등 재무지표 활용
- **DB 매매 기록**: `LynchDBManager`가 전용 테이블에 매매 이력 관리
- **장시작 시 후보 스크리닝**: `LynchCandidateSelector`가 재무 조건 기반으로 후보 선별
- **일일 손실 제한**: 누적 실현손실 5% 초과 시 매수 중단
- **정적 메서드 분리**: `evaluate_buy_conditions` / `evaluate_sell_conditions`가 `@staticmethod`로 분리되어 테스트 용이
