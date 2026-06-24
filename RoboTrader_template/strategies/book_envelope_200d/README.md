# book_envelope_200d — Book19 트레이딩 전략서

> 활성 페이퍼 전략. 운영 허브 → [docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md) · 추가 가이드 → [docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md)
> 임계값의 SSOT는 `config.yaml` + 진입/청산 룰 코드입니다. 이 문서는 *해설*이며, 숫자가 어긋나면 코드가 정본.

## 한 줄
200일 신고가를 막 돌파하는 강세 모멘텀을 추격. OOS 홀드아웃에서 cross-period 강건이 확인된 유일 신규 엣지.

## 출처 / 분류
Book19 『트레이딩 전략서』 HTS 조건검색식 A~I verbatim — 돌파 모멘텀.

## 진입 (`rule_envelope_200d_high`, 책 A~I verbatim)
200일 종가신고가 + Envelope(MA10)×1.10 상단 돌파 + 양봉 + 거래량 전일대비↑ + 종가 > 이등분선 +
5일 평균거래대금 ≥ 50억 + 갭상승/직전급등 제외 + 당일 시초대비 +3%.

## 청산
sl **-8%** / tp **+10%** / max_hold **10거래일** / trailing 없음.

## 데이터 특이 ★
200일 신고가는 200영업일이 필요 → 라이브 robotrader 피드(~85봉)로는 부족 → **진입평가용 일봉을
`QuantDailyReader`(quant SSOT)에서 230봉 직접조회**(클린). 청산은 현재가·보유일만 필요해 프레임워크 일봉 사용.

## 유니버스 / regime / 사이징
- 유니버스: 거래대금 ≥ 10억 (진입평가 quant 230봉)
- regime: index **KOSPI** / gate **none**
- K = **5** / 종목당 **200만**

## 평판 (백테스트 / OOS)
OOS train **1.20** / test **1.82**. 워크포워드 = 조건부 통과 (엣지는 랠리 이전부터 일관·양수 8/11이나
alpha가 비강세장 한정, 메가불장 -85% 하회, 깊은약세 2022H1 -4.33). 페이퍼 관찰에 적합.

## 코드
- 전략: `strategy.py` · 설정: `config.yaml` · EOD 스크리너: `screener.py`
- 진입 룰(SSOT): `strategies/books/trading_strategy_book/rules.py::rule_envelope_200d_high`
