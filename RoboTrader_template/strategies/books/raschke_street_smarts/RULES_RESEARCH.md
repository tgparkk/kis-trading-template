# Linda Raschke - Street Smarts: 매매 셋업 조사

> 조사일: 2026-05-28
> 출처: 하단 URL 목록

## 요약

"Street Smarts: High Probability Short-Term Trading Strategies" (Laurence A. Connors & Linda Bradford Raschke, 1995/1996, ISBN 0-9650461-0-9)는 미국 선물·주식 시장에서 검증된 단기 트레이딩 패턴 플레이북. 핵심 철학은 "컨텍스트와 가격 행동"이 지표·복잡한 공식보다 우선 — 거짓 돌파 후 반전, 추세 말미 소진, 변동성 압축 후 폭발적 방향성. 대부분 셋업은 일봉 또는 일봉+분봉 혼합 기반, 보유 기간 당일~수 거래일. Raschke는 2010년대 이후 웨비나에서 "Holy Grail은 여전히 유효"라고 언급.

## 셋업 목록 (10개)

### 셋업 1: Turtle Soup (일봉)
- 20일 신저점 돌파 후 다음 봉에서 이전 저점 위 5~10틱에 매수 스탑. 당일 GFD
- 거짓 돌파를 역이용 (터틀 추종자들의 진입을 페이드)
- 손절: 당일 저점 1~수센트 아래. 익절: 2~6봉 트레일링

### 셋업 2: Turtle Soup Plus One (일봉)
- D+0에 20일 신저점 + 종가가 이전 저점 이하 → D+1에 이전 저점 위 매수 스탑
- 종가 확인으로 신뢰도 강화

### 셋업 3: 80-20 (일봉+분봉)
- 전일이 대형봉. 시가는 일일 범위 상위 20%, 종가는 하위 20% (또는 반대) 봉
- 당일 전일 저점 -5~15틱까지 하락 후 반전 → 전일 저점에 매수 스탑
- 당일 데이 트레이드, overnight 금지

### 셋업 4: Momentum Pinball (일봉+분봉)
- 전일 3기간 RSI of 1기간 ROC < 30 → 롱 시그널, > 70 → 숏 시그널
- 당일 첫 1시간봉 고점/저점 돌파 진입
- 손절: 첫 1시간봉 극단. 보유: 당일~익일 시가

### 셋업 5: Holy Grail (분봉+일봉) ⭐ Raschke 직접 추천 — 여전히 유효
- 14기간 ADX > 30 및 상승 중 + 20기간 MA까지 풀백 (첫 번째 풀백만)
- 풀백봉 고점 위에 매수 스탑
- 손절: 신규 스윙 저점. 익절: 트레일링 스탑

### 셋업 6: The Anti (분봉/일봉)
- 임펄스 무브 후 Stochastic(%K 7, %D 10) 훅 패턴
- 20기간 EMA 추세 필터 + %D 방향 진행 중 %K 훅 → 봉 극단에 진입
- 2~4봉 내 청산

### 셋업 7: ADX Gapper (일봉)
- ADX(12) > 30 + +DI(28) > -DI(28) (추세 강세)
- 갭 역방향 오픈 (롱: 전일 저점 아래 갭다운) → 전일 저점에 매수 스탑
- 당일 데이 트레이드

### 셋업 8: 2-Period ROC (일봉)
- 2일 ROC가 음→양 전환 (롱) 또는 양→음 (숏)
- 종가 매수, 익일 청산
- Taylor Trading Technique 연계

### 셋업 9: NR4 + Historic Volatility (일봉)
- 오늘 범위가 직전 3봉 중 최소 (NR4)
- 6일 실현변동성 / 100일 실현변동성 < 0.5
- NR4 봉 고점 위 / 저점 아래 양방향 브레이크아웃 스탑
- 구조적으로 견고 (변동성 사이클 원리)

### 셋업 10: Gimmee Bar (분봉/일봉)
- 볼린저밴드 횡보장 + 밴드 하단 터치 후 반전 양봉 → 매수
- 목표: 반대편 밴드. 일부 출처는 Joe Ross 기원, Raschke 채용

(상세 진입·손절·익절·한계는 위 요약 참조; 전체 18 출처 URL 하단)

---

## 한국 시장 적용 시 주의점

### 데이터 입도
- 일봉 전용: Turtle Soup, Turtle Soup Plus One, 80-20, 2-Period ROC — `daily_prices` 사용 (기존 분봉 백테스터 미지원, 별도 일봉 엔진 필요)
- 분봉 코드화 가능: Holy Grail, Anti, Gimmee Bar, Momentum Pinball, NR4 변형 — 분봉 인디케이터 직접 계산

### 거래 시간 차이
- Momentum Pinball "첫 1시간봉" = 한국 09:00~10:00

### 공매도 제약
- 한국 일반 개인투자자 공매도 제한. 숏 셋업 (Turtle Soup 숏, 80-20 숏, ADX Gapper 숏) 인버스 ETF (KODEX 200 인버스) 한정

### 미세구조
- 책 1995년 미국 선물·주식 기준. "틱" 조건은 한국 호가단위로 변환 또는 ATR × 0.1 권장
- Raschke 본인이 Turtle Soup, 80-20은 알고리즘 시장에서 엣지 약화 가능성 언급. Holy Grail, NR4 + HV은 견고 가능성

## 출처 URL 목록

1. https://pdfcoffee.com/80-20x27s-from-street-smarts-high-probability-short-term-trading-strategiesraschke--pdf-free.html
2. https://www.mql5.com/en/articles/2717 — Turtle Soup
3. https://www.mql5.com/en/articles/2825 — Momentum Pinball
4. https://www.mql5.com/en/articles/2785 — 80-20
5. https://www.tradingsetupsreview.com/the-holy-grail-trading-setup/
6. https://tradersmastermind.com/linda-raschke-trading-strategy/
7. https://www.gate.com/news/detail/18612681 — Holy Grail ADX EMA
8. https://www.tradingsetupsreview.com/gimmee-bar/
9. https://georgepruitt.com/connors-raschke-momentum-pinball/
10. https://www.newtraderu.com/2020/08/15/turtle-soup-trading-strategy/
11. http://technical.traders.com/tradersonline/display.asp?art=2794 — ADX Gapper
12. http://technical.traders.com/tradersonline/display.asp?art=3728 — 2-Period ROC
13. https://www.cryptodatadownload.com/blog/posts/inside-contraction-historical-volatility-strategy/ — NR4+HV
14. https://www.stockmaniacs.net/3-10-oscillator-trend-reversal-patterns/ — Anti 3/10
15. https://www.litefinance.org/blog/for-beginners/anti-a-fresh-look-at-indicators/ — Anti
16. https://www.turtletrader.com/trader-raschke/ — Raschke 배경
17. https://store.traders.com/-v14-c08-histori-pdf.html — Traders 매거진 V.14:8 NR4/HV
18. http://street-smarts-tradestation.blogspot.com/2008/03/street-smarts-high-probability-short.html

## 코드화 우선순위 (한국 분봉 기준)

| # | 셋업 | 데이터 | 우선순위 | 비고 |
|---|---|---|---|---|
| 1 | Holy Grail | 분봉 | ⭐⭐⭐ | Raschke 본인 추천, 여전히 유효 |
| 2 | Anti | 분봉 | ⭐⭐ | 스토캐스틱 훅 |
| 3 | Gimmee Bar | 분봉 | ⭐⭐ | 볼린저밴드 횡보 |
| 4 | NR4 변형 | 분봉 | ⭐⭐ | 변동성 사이클 |
| 5 | Momentum Pinball 변형 | 분봉 | ⭐ | 첫 1시간 돌파 |
| 6 | Turtle Soup | 일봉 | ⭐ | 일봉 백테스터 필요 |
| 7 | Turtle Soup Plus One | 일봉 | ⭐ | 일봉 |
| 8 | 80-20 | 일봉+분봉 | ⭐ | 일봉 신호 |
| 9 | ADX Gapper | 일봉 | ⭐ | 일봉 |
| 10 | 2-Period ROC | 일봉 | ⭐ | 일봉 |

분봉 코드화 5개 우선. 일봉 5개는 후속.
