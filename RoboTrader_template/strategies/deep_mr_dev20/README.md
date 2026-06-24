# deep_mr_dev20 — MA20 -20% 폭락 평균회귀 (발굴 파이프라인 배치3 졸업)

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
-20% 깊은 폭락 + 과매도 종목을 매수해 MA20 회복까지 반등을 먹는 평균회귀. 자체 발굴 파이프라인 22변형 중
유일하게 품질 전관문(G2~G5)을 통과한 8번째 전략.

## 출처 / 분류
발굴 파이프라인 배치3 졸업 — 평균회귀 (폭락 저격).

## 진입 (`MeanReversionMA20Rule`, 백테스트 단일소스)
1. (종가 − MA20) / MA20 ≤ **-20%** (깊은 폭락)
2. RSI(14) < **30** (과매도)

## 청산 (`MAReversionExitAdapter`, 우선순위 1:1)
sl **-7%** → tp **+12%** → MA20 × 0.9 회복 → max_hold **7거래일**.

## 유니버스 / regime / 사이징
- 유니버스: 거래대금 ≥ 100억 (top300 근사 — top500+ 확장 시 엣지 소멸 확인) · 폭락 깊이(|이탈|)순. 거래량 폴백 비허용(희소조건 전략).
- regime: index **KOSPI** / gate **none**
- K = **5** / 종목당 **200만** — yaml `paper_investment_per_stock: 2,000,000` 명시 (S2 시나리오 = 자본/K 스위트스팟, CAGR +14.2% / Sharpe 0.79 / P(DD≥30%) = 11%)

## 평판 (백테스트 / OOS)
**+51.8%** / Sharpe **0.73** / MaxDD **16.2%** / 거래당 그로스 +1.81% / 월 6.0회.
부트스트랩 Sharpe p05 +0.22 · 워크포워드 8/11(최악 -4.8%) · 섭동(-16~-24%) 전부 양수 · OOS train 0.93/test 0.30.
⚠️ 성격 = 승률 49% · 중앙값 -0.33% · 우꼬리 의존(+17~49%)의 "자주 조금 잃고 가끔 크게 먹는" 희소 저격형.

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `scripts/discovery/rules.py::MeanReversionMA20Rule`
