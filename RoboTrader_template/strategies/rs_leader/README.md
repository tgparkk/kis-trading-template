# rs_leader — 횡보장 RS 리더 (derived 전략, 페이퍼 관찰 전용)

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
시장이 안 좋을 때 상대적으로 강한(횡단면 RS 상위) 절대상승 종목을 매수. 횡보장에서 강건.

## 출처 / 분류
derived 전략 (Book20 아님) — 상대강도(RS) / 추세.

## 진입 (`RSLeaderRule`)
절대상승추세(`RSLeaderRule(ma_short=20, ma_long=60, abs_lb=60)`: 종가 > MA60 · MA20 > MA60 · 60일수익 > 0)를
per-stock 재확인 후 매수. **횡단면 RS 랭킹은 EOD 스크리너가 담당** (절대상승추세 통과 종목의 120일 수익률을
score로 → 정렬 + topK = RS 랭킹).

## 청산
종가 < MA20 하향이탈 (**무조건**) / sl **-8%** / tp **+15%** (추세추종이라 거의 무효, 트레일이 주청산) / max_hold **30거래일**.

## 유니버스 / regime / 사이징
- 유니버스: 거래대금 ≥ 10억 · 시총 컷 없음 (절대상승추세 통과 → 120일수익률 RS topK)
- regime: index **KOSPI** / gate **exclude_bear** (깊은약세 미입증이라 약세장 매수 차단)
- K = **10** / 종목당 **100만**

## 평판 (백테스트 / OOS)
검증 조건부 (횡보장 5/5 config 강건 +5~8% · OOS 양수 ✅ / 깊은약세 부호반전 · per-trade Sharpe 0.08~0.19 ❌).
현 백테스트는 강세장 순풍 왜곡 (2026-04/05 +8.5/+6.8%는 KOSPI +30/+28% 덕). 페이퍼 관찰 전용.

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `scripts/rs_leader/rule.py::RSLeaderRule`
