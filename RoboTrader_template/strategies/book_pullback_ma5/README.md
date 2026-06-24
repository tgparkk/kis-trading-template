# book_pullback_ma5 — 『트레이딩의 전설』(Book15) ma5_pullback

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
급등 후 5일선까지의 짧은 눌림을 타이트 손절로 잡는 단기 트레이더형 눌림목.

## 출처 / 분류
『트레이딩의 전설』(Book15) ma5_pullback — 눌림목 (단기).

## 진입 (`rule_ma5_pullback`)
1. 최근20일 내 **+20%** 급등 이력
2. 마지막 봉 저가가 5일선 ±touch_tol 터치
3. 종가 ≥ MA5 × (1 − below_tol)
4. 마지막 봉 양봉

## 청산
**sl -3%** (타이트, 단기 트레이더 손절) / tp **+15%** / 수익 중 종가 < MA5 trailing / max_hold **30거래일**.

## 유니버스 / regime / 사이징
- 유니버스: 중소형 (시총 ≤ 3조) · KOSPI + KOSDAQ
- regime: index **KOSPI** / gate **exclude_bear** (진짜 수혜)
- K = **5** / 종목당 **200만**

## 평판 (백테스트 / OOS)
Sharpe **0.63**이나 **BULL 청산 의존 리스크** (OOS -87% 장기 전소). 페이퍼 관찰로 유지.

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `strategies/books/trading_legends/rules_daily.py::rule_ma5_pullback`
