# daytrading_3methods_breakout — 유지윤 데이트레이딩 3대 타법 (Variant B)

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
거래량 동반 전고점 돌파를 빠르게 먹고 빠지는 돌파 타법. 약한 Sharpe라 탐색·관찰용.

## 출처 / 분류
유지윤 『데이트레이딩 3대 타법』 (Variant B) — 돌파.

## 진입 (`rule_breakout_prev_high`, high_window=15)
종가 ≥ 직전15봉 전고점 + 당일거래량 ≥ 15봉평균 × 2.0 + 양봉.

## 청산
sl **-10%** / tp **+10%** / max_hold **10거래일** / trailing 없음 (돌파 타법 = 고정 손익절).

## 유니버스 / regime / 사이징
- 유니버스: 중소형 (시총 < 5천억) · 거래량 배수순
- regime: index **KOSDAQ** / gate **none** (일봉 게이트는 분봉 성격이라 부적합)
- K = **5** / 종목당 **200만**

## 평판 (백테스트)
706T / **+5.90%** / Sharpe **0.17** / hit 46.7% — 약함. 탐색·관찰 목적으로 유지.

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `strategies/books/daytrading_3methods/rules.py::rule_breakout_prev_high`
