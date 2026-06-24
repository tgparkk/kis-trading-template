# book_pullback_ma20 — 강창권 『단기 트레이딩의 정석』 A-07

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
급등 후 20일선까지 눌린 종목의 지지 반등을 노리는 눌림목.

## 출처 / 분류
강창권 『단기 트레이딩의 정석』 A-07 — 눌림목.

## 진입 (`rule_daily_ma20_pullback`)
1. 직전30일 내 **+25%** 급등 이력
2. 종가 ≥ MA20 × (1 − below_tol) (지지 유효)
3. 마지막 봉 저가가 20일선 ±touch_tol 터치
4. 마지막 봉 양봉

## 청산
sl **-8%** / tp **+10%** (책 명시 유일 익절) / 수익 중 종가 < MA20 trailing / max_hold **50거래일**.

## 유니버스 / regime / 사이징
- 유니버스: 중소형 (시총 ≤ 3조) · KOSPI + KOSDAQ 모두 (눌림목은 시장 무관)
- regime: index **KOSPI** / gate **exclude_bear** (눌림목은 게이트 진짜 수혜 — MaxDD 대폭↓)
- K = **5** / 종목당 **200만**

## 평판 (백테스트 / OOS)
Sharpe **0.44** / **+16%**. OOS 부진(-21~97%)이나 격리자본 페이퍼 관찰로 라이브 검증 유지.

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `strategies/books/haru_silijeon/rules_daily.py::rule_daily_ma20_pullback`
