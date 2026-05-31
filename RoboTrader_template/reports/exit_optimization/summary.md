# 선별 4전략 청산 멀티버스 — 종합 (OOS 기준)

> DSR 게이트 임계 = 0.95 (1급 0.95 / 과반 0.5)

| strategy               |   mean_oos_worst_sharpe |   mean_oos_return |   max_train_dsr | verdict                     |
|:-----------------------|------------------------:|------------------:|----------------:|:----------------------------|
| elder_ema_pullback     |                -4.15922 |         0.0136844 |    0            | 기존값 유지(유의 개선 없음) |
| minervini_volume_dryup |                -2.76875 |         0.0494115 |    8.96927e-153 | 기존값 유지(유의 개선 없음) |
| book_pullback_ma20     |                -4.17287 |         0.116273  |    0            | 기존값 유지(유의 개선 없음) |
| book_pullback_ma5      |                -5.04176 |        -0.12103   |    0            | 기존값 유지(유의 개선 없음) |

## 판정 규칙
- **개선 채택후보**: 평균 OOS 국면최악 Sharpe > 0 **그리고** train DSR ≥ 임계
- 그 외: **기존값 유지** (default to no-change)

## 주의
- 실제 trading_config.json/config.yaml 교체는 **별도 사장님 승인** 필요.
- 폴드 간 파라미터 UNSTABLE 표기 전략은 채택 신중.