# Book 15 『트레이딩의 전설』 판독·코드화·백테스트 (2026-05-30)

> 키움증권 채널K 엮음, 『트레이딩의 전설』(넥스트씨, 2025-09-30), 키움영웅전 실전투자대회 수상자 9인 인터뷰집.
> 상세 카탈로그·결과: `reports/books_research/trading_legends/report.md`

## 1. 판독 (전자책 캡처 140장 → 직원 7명 분담)
- 원자료 `D:\tmp\tl_001~140.png`(휘발성 tmp). 직원 7명이 20장씩 분담 판독(1명 소켓에러 → 재투입 복구) → `raw_notes/notes_*.md` 7개.
- **9인 전원 확정**(판권면 tl_137): 불개미·신정재·청사진·방배동선수·만쥬·바른다른·캐리·월억언제해보나·뭐라도되겠지.
- **성격**: 시스템 전략서 아닌 인터뷰집. **9인 중 8인이 분봉/호가창 스캘퍼** → 4권(아지즈·Bellafiore·Raschke·강창권 분봉) 전멸 선례와 동일 영역. 코드화 가치는 일봉 오버나이트/돌파/눌림 클러스터에 집중.

## 2. 코드화 (그룹A 일봉 6룰, executor opus)
- 신규 `strategies/books/trading_legends/`: `rules_daily.py`(6룰)·`strategy_daily.py`·`__init__.py`.
  6룰 = close_momentum_breakout(종가매매) · limit_up_follow(상따) · new_high_breakout(전고점돌파) · prev_limitup_pullback(전날상한가눌림) · ma5_pullback(눌림목) · bottom_first_bull(바닥권첫양봉).
- `scripts/run_trading_legends_daily.py`: variant A(sl8/tp off/mh100/trail)·B(sl8/tp12/mh20)·**O(오버나이트 sl5/tp off/mh1)** + RULE_SL_OVERRIDE(limit_up_follow=0.03) + RULE_TRAIL_MA(6룰).
- `scripts/regime_split_trading_legends.py`(moonbyungro 패턴 복제, regime_label_5y 캐시 재사용).
- `tests/books/test_trading_legends_daily.py` **22 passed**.

## 3. 백테스트 결과 (2021~2026, top_volume:100, 99종목)
| 룰 | var | 거래 | PnL% | Sharpe | Calmar | 승률 | MaxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| 종가매매 | O | 1456 | **−3.95** | −0.15 | 0.18 | 40.6 | 25.0 |
| 상따 | O | 139 | +3.44 | 0.05 | 1.25 | 21.1 | **7.46** |
| 전고점돌파 | A | 607 | +3.56 | 0.06 | 0.53 | 31.0 | 26.0 |
| 전날상한가눌림 | A | 37 | +1.24 | −0.06 | 0.03 | 9.5 | 3.8 |
| 눌림목 | A | 3844 | +0.25 | 0.12 | 0.36 | 36.9 | 38.1 |
| **눌림목** | **B** | 2520 | **+33.66** | **0.63** | 1.57 | 49.1 | 37.3 |
| 바닥권첫양봉 | A | 791 | −0.20 | −0.03 | 0.08 | 24.9 | 13.5 |

국면: BULL 39.3/BEAR 29.3/SIDEWAYS 31.4%. entry-BEAR 양수 = 전고점돌파 A(+1.21)·눌림목 B(+1.15)·바닥권 A(+0.81), 단 exit는 BULL 의존.

## 4. 결론 — CANDIDATE 부적격 (15권째 동일 라인)
1. **책 시그니처(종가매매)는 백테스트 실패** −3.95%. "장 막판 강세→익일 갭" 가설 일봉 해상도 불성립 → 이 책 고유 기여 ≈ 0.
2. **유일 강세(눌림목 B +33.66%/Sharpe 0.63)는 신규 알파 아님** — Book14 강창권 ma5_10(+46%) 재확인. "눌림목=한국 일봉 최강 단일패턴" 교차 재확인이나 BULL 청산 집중 의존(BEAR exit −4.19%).
3. **상따는 저DD 니치**(MaxDD 7.46% 최저, calmar 1.25) but Sharpe 0.05·139거래 통계력 부족. 무레버리지 기준(원문 미수 3.3배 미반영). 상한가 종목이 대형주 유니버스에 희소.
4. **Elder A 약세장 방어(BEAR +3.01%) 도달 룰 없음.** 기술적 추세추종(Elder/Minervini)만 Sharpe 0.6대 생존 = 15권째 재확인.
- 분봉 그룹B(만쥬·바른다른·월억·캐리 호가창)는 전멸 선례로 코드화 생략(카탈로그 기록만).

## 5. 부수 작업 — 책 후보 백로그 (인터넷서점 병렬 조사)
- 사장님 지시로 직원 4명 병렬 발굴(교보/예스24/알라딘): `reports/books_research/candidate_backlog.md` + 카테고리 4파일. 49권(기존 15권 제외).
- 우선순위 '상': **터틀의 방식(돈키언 돌파, 일봉 코드화 최상)** · 박병창 매매의 기술 · **거인의 포트폴리오(allocation 트랙 확장)** · 듀얼모멘텀 · 유지윤 50패턴 · 김단테 절대수익. 신규 팩터: 사경인 S-RIM, 강환국 GP/A.
- depth-first 원칙 유지(발굴만 병렬, 깊이 조사는 순차).

## 6. 미커밋 / 다음
- 미커밋: trading_legends 코드/스크립트/테스트, regime_split_trading_legends.py, report.md, raw_notes, candidate_backlog*, changelog, index/MEMORY — git 커밋 사장님 승인 대기.
- 다음 깊이 조사 1순위(사장님 점지 대기): 터틀의 방식 또는 거인의 포트폴리오.
