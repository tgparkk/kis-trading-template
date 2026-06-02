# Phase 5 — 카테고리 1: 차트 패턴

> 작성일: 2026-05-25 | 조사자: document-specialist (Claude)
> 출처 우선순위: 책 3권(00_kyobo_books.md) → Bulkowski Encyclopedia → VT Markets/TradingMetrics → Investopedia/한국 자료

---

총 27개 컨셉 (책 3권 11개 + 외부 16개)

- 책 3권: 00_kyobo_books.md 참조 (강창권·이시이 카츠토시·앤드루 아지즈)
- 외부: Bulkowski thepatternsite.com, VT Markets 2025 Chart Patterns Guide, TradingMetrics Island Reversal Docs, Investopedia

---

## 컨셉 카탈로그

---

### 1. 헤드앤숄더 (Head and Shoulders — 하락 반전)

- **정의**: 세 개의 연속 봉우리 중 가운데(머리)가 가장 높고, 양쪽 어깨가 유사한 높이. 넥라인(두 어깨 사이 저점 연결선) 하향 돌파 + 거래량 증가 시 진입. 목표가 = 머리 높이만큼 넥라인에서 하락.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) · Bulkowski thepatternsite.com (성공률 89%)
- **카테고리 태그**: Stage C (청산/숏 진입)
- **버킷**: mid (10~30일)
- **한국 시장 적용 사례**: 코스피 대형주 고점권에서 자주 관찰. 넥라인 = 지지→저항 전환 확인 필수.
- **PIT-safe 가능성**: 가능 — 넥라인 돌파는 당일 종가 확정 후 익일 진입으로 구현 가능.
- **필요 데이터**: 일봉 고가/저가/종가, 거래량
- **예상 difficulty**: 중간 (넥라인 기울기 판단 로직 필요)

---

### 2. 역 헤드앤숄더 (Inverse Head and Shoulders — 상승 반전)

- **정의**: 세 개의 골짜기 중 가운데(머리)가 가장 낮음. 넥라인 상향 돌파 + 거래량 급증 시 매수. 목표가 = 머리 깊이만큼 넥라인 위.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) (성공률 89%)
- **카테고리 태그**: Stage A (진입 신호)
- **버킷**: mid (10~30일)
- **한국 시장 적용 사례**: 급락 후 바닥 다지기 구간에서 발생. 넥라인 돌파 시 거래량 동반 여부가 신뢰도 핵심.
- **PIT-safe 가능성**: 가능 — 넥라인 돌파 당일 종가 기준 익일 진입.
- **필요 데이터**: 일봉 고가/저가/종가, 거래량
- **예상 difficulty**: 중간

---

### 3. 이중 바닥 (Double Bottom — W 패턴)

- **정의**: 두 개의 유사한 저점(3~5% 이내) 형성 후 중간 저항선 상향 돌파. 거래량 확인 필수. 목표가 = 저점~저항선 높이만큼 추가 상승.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) (성공률 88% in bull market) · Bulkowski — Adam&Adam, Adam&Eve, Eve&Adam, Eve&Eve 4변형 분류
- **카테고리 태그**: Stage A (반전 진입)
- **버킷**: swing~mid (3~20일)
- **한국 시장 적용 사례**: 코스닥 급락 이후 지지 확인 패턴으로 빈번. 두 번째 저점 거래량 감소 + 돌파 시 급증이 신뢰도 높음.
- **PIT-safe 가능성**: 가능 — 저항선 돌파 종가 확정 후 진입.
- **필요 데이터**: 일봉 고가/저가/종가, 거래량
- **예상 difficulty**: 쉬움

---

### 4. 이중 천장 (Double Top — M 패턴)

- **정의**: 두 개의 유사한 고점(3~5% 이내) 형성 후 중간 지지선 하향 이탈. 목표가 = 고점~지지선 높이만큼 하락.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) (성공률 73~88%)
- **카테고리 태그**: Stage C (청산 신호)
- **버킷**: mid (10~30일)
- **한국 시장 적용 사례**: 저항선 재시험 실패 후 거래량 감소하면 신뢰도 상승.
- **PIT-safe 가능성**: 가능 — 지지선 이탈 종가 확정 후 익일 청산.
- **필요 데이터**: 일봉 고가/저가/종가, 거래량
- **예상 difficulty**: 쉬움

---

### 5. 삼중 바닥 (Triple Bottom)

- **정의**: 세 개의 유사한 저점 형성 + 저항선 돌파. 이중 바닥보다 신뢰도 높으나 출현 빈도 낮음. Bulkowski: "busted" 버전(돌파 실패) 포함 분류.
- **출처**: [Bulkowski thepatternsite.com](https://thepatternsite.com/chartpatterns.html)
- **카테고리 태그**: Stage A
- **버킷**: mid~position (20~60일)
- **한국 시장 적용 사례**: 장기 횡보 종목에서 발생. 세 번째 저점 거래량 급감이 핵심 조건.
- **PIT-safe 가능성**: 가능
- **필요 데이터**: 일봉 고가/저가/종가, 거래량
- **예상 difficulty**: 중간 (세 저점 인식 알고리즘 필요)

---

### 6. 삼중 천장 (Triple Top)

- **정의**: 세 개의 유사한 고점 형성 + 지지선 이탈. 하락 반전 신호. 이중 천장보다 강한 신호.
- **출처**: [Bulkowski thepatternsite.com](https://thepatternsite.com/chartpatterns.html)
- **카테고리 태그**: Stage C
- **버킷**: mid~position (20~60일)
- **한국 시장 적용 사례**: 저항대 3회 돌파 실패 후 매물대 확정. 청산 시그널.
- **PIT-safe 가능성**: 가능
- **필요 데이터**: 일봉 고가/저가/종가, 거래량
- **예상 difficulty**: 중간

---

### 7. 컵앤핸들 (Cup and Handle)

- **정의**: 둥근 바닥(U자형, 7~65주) + 소규모 하락 조정(핸들, 15~50% 되돌림) + 핸들 저항선 돌파 매수. 성공률 95%(Bulkowski), 평균 상승폭 54%.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) · Bulkowski (성공률 80~95%)
- **카테고리 태그**: Stage A
- **버킷**: position (30~65일, 핸들만 보면 swing 가능)
- **한국 시장 적용 사례**: 중소형 성장주에서 나타남. 핸들 구간 거래량 감소 필수 조건.
- **PIT-safe 가능성**: 가능 — 핸들 고점 돌파 당일 종가 기준 진입.
- **필요 데이터**: 일봉 고가/저가/종가, 거래량 (최소 7주 데이터)
- **예상 difficulty**: 어려움 (둥근 바닥 인식 + 핸들 정의 알고리즘)

---

### 8. 강세 깃발형 (Bull Flag)

- **정의**: 급등(깃대) 후 좁은 하향 평행 채널(깃발) 형성 → 거래량 감소 후 상향 돌파 + 거래량 급증 시 매수. 목표가 = 깃대 높이만큼 추가 상승. 성공률 91.51%.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) · 책 3 (앤드루 아지즈, 전략2) — [교보 3권 참조](https://product.kyobobook.co.kr/detail/S000001777389)
- **카테고리 태그**: Stage B (추세 지속 진입)
- **버킷**: swing (1~5일)
- **한국 시장 적용 사례**: 테마주 급등 후 눌림목 패턴과 동일. 깃대 거래량이 깃발 거래량의 3배 이상이어야 신뢰도 높음.
- **PIT-safe 가능성**: 가능 — 채널 상단 돌파 봉 종가 기준.
- **필요 데이터**: 분봉 또는 일봉, 거래량
- **예상 difficulty**: 쉬움

---

### 9. 약세 깃발형 (Bear Flag)

- **정의**: 급락(깃대) 후 좁은 상향 평행 채널 형성 → 채널 하단 이탈 시 추가 하락 진입. 성공률 ~80%.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/)
- **카테고리 태그**: Stage C
- **버킷**: swing (1~5일)
- **한국 시장 적용 사례**: 급락 후 데드캣 반등 구간에서 출현. 공매도 제한으로 직접 숏 어렵고 청산 신호로 활용.
- **PIT-safe 가능성**: 가능 — 이탈 종가 확정 후 익일 처리.
- **필요 데이터**: 분봉 또는 일봉, 거래량
- **예상 difficulty**: 쉬움

---

### 10. 페넌트 (Pennant)

- **정의**: 급등/급락(깃대) 후 수렴하는 삼각형 패턴(거래량 감소) → 방향 돌파 시 추세 지속. 성공률 80~85%.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) · Bulkowski (상승 페넌트 성공률 80%, 하락 46%)
- **카테고리 태그**: Stage B
- **버킷**: swing (2~7일)
- **한국 시장 적용 사례**: 급등 이후 단기 수렴. 깃발과 유사하나 채널이 아닌 삼각 수렴.
- **PIT-safe 가능성**: 가능
- **필요 데이터**: 분봉 또는 일봉, 거래량
- **예상 difficulty**: 중간 (수렴 삼각형 실시간 인식)

---

### 11. 상승 쐐기 / 하락 쐐기 (Rising Wedge / Falling Wedge)

- **정의**: 상승 쐐기 — 지지선과 저항선이 모두 우상향하나 저항이 더 가파름 → 하향 이탈 시 하락 신호 (성공률 64%). 하락 쐐기 — 두 선 모두 우하향, 지지가 더 가파름 → 상향 돌파 시 상승 신호 (성공률 64%).
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/)
- **카테고리 태그**: Stage A (하락 쐐기 돌파) / Stage C (상승 쐐기 이탈)
- **버킷**: mid (10~30일)
- **한국 시장 적용 사례**: 상승 쐐기는 오르는 종목의 매도 경고 신호로 유용.
- **PIT-safe 가능성**: 가능 — 이탈/돌파 종가 확정 후 익일 진입.
- **필요 데이터**: 일봉 고가/저가/종가
- **예상 difficulty**: 중간 (두 추세선 동시 추적)

---

### 12. 대칭 삼각형 (Symmetrical Triangle)

- **정의**: 낮아지는 고점 + 높아지는 저점으로 수렴. 추세 방향으로 돌파 시 추세 지속. 성공률 76%(추세 방향 돌파 기준). 거래량 30일 평균 대비 50% 이상 증가 확인 필수.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) · Bulkowski
- **카테고리 태그**: Stage A 또는 Stage C (돌파 방향에 따라)
- **버킷**: mid (10~30일)
- **한국 시장 적용 사례**: 주요 이벤트(실적·공시) 전 수렴 구간에서 자주 발생.
- **PIT-safe 가능성**: 가능
- **필요 데이터**: 일봉 고가/저가, 거래량
- **예상 difficulty**: 중간

---

### 13. 상승 삼각형 (Ascending Triangle)

- **정의**: 수평 저항선 + 우상향 지지선. 저항선 상향 돌파 + 거래량 급증 시 매수. 성공률 75%.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) · Bulkowski
- **카테고리 태그**: Stage A
- **버킷**: mid (10~30일)
- **한국 시장 적용 사례**: 저항선 재시험 횟수가 많을수록(3회 이상) 돌파 시 폭발력 증가.
- **PIT-safe 가능성**: 가능
- **필요 데이터**: 일봉 고가/저가/종가, 거래량
- **예상 difficulty**: 중간

---

### 14. 하강 삼각형 (Descending Triangle)

- **정의**: 수평 지지선 + 우하향 저항선. 지지선 하향 이탈 시 하락 추가. 성공률 75%.
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) · Bulkowski
- **카테고리 태그**: Stage C
- **버킷**: mid (10~30일)
- **한국 시장 적용 사례**: 지지선 붕괴 후 급락 가속. 공매도보다 보유 포지션 청산 신호로 사용.
- **PIT-safe 가능성**: 가능
- **필요 데이터**: 일봉 고가/저가/종가
- **예상 difficulty**: 중간

---

### 15. 직사각형 박스 돌파 (Rectangle Breakout)

- **정의**: 수평 지지선과 수평 저항선 사이 횡보 → 어느 방향이든 거래량 동반 돌파 시 추세 시작. 성공률 65~70%. 이시이 카츠토시 책 Rule 63~65 "횡보 후 돌파".
- **출처**: [VT Markets Chart Patterns 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/) · 책 2 (이시이 카츠토시) — [교보 2권 참조](https://product.kyobobook.co.kr/detail/S000001014275)
- **카테고리 태그**: Stage A 또는 Stage C
- **버킷**: swing~mid (3~20일)
- **한국 시장 적용 사례**: 눌림목 후 수렴 횡보 구간에서 빈번. 박스 높이를 목표가로 사용.
- **PIT-safe 가능성**: 가능 — 돌파 종가 확정 후 익일 진입.
- **필요 데이터**: 일봉 고가/저가/종가, 거래량
- **예상 difficulty**: 쉬움

---

### 16. 망치형 캔들 (Hammer)

- **정의**: 하락 추세 중 아래꼬리가 몸통의 2배 이상, 위꼬리 없음(또는 미미), 작은 양봉 몸통. 저점 지지 확인 반등 신호. 이시이 카츠토시 책 Rule 60~62 "아래꼬리 양봉".
- **출처**: Investopedia (https://www.investopedia.com/terms/h/hammer.asp) · 책 2 (이시이 카츠토시) · 책 3 (앤드루 아지즈, 반전매매 전략3~4)
- **카테고리 태그**: Stage A
- **버킷**: swing (1~3일)
- **한국 시장 적용 사례**: 장중 급락 후 회복 캔들. 지지선 부근에서 발생 시 신뢰도 급상승.
- **PIT-safe 가능성**: 가능 — 당일 종가 확정 후 익일 진입.
- **필요 데이터**: 일봉 시가/고가/저가/종가
- **예상 difficulty**: 쉬움

---

### 17. 도지 (Doji)

- **정의**: 시가=종가(또는 매우 근접). 시장 방향 미결정 신호. 상승 추세에서 도지 출현 → 하락 반전 경고. 하락 추세에서 도지 + 다음봉 양봉 확인 → 반전 매수.
- **출처**: Investopedia (https://www.investopedia.com/terms/d/doji.asp) · 책 3 (앤드루 아지즈, "불확실 캔들 집중" 6장) — [교보 3권 참조](https://product.kyobobook.co.kr/detail/S000001777389)
- **카테고리 태그**: Stage A 또는 Stage C (추세에 따라 다름)
- **버킷**: swing (1~2일)
- **한국 시장 적용 사례**: 단독 도지보다 다음 봉 방향 확인 후 진입(2봉 패턴)이 한국 시장에서 안정적.
- **PIT-safe 가능성**: 가능 (2봉 확인 필요)
- **필요 데이터**: 일봉 시가/고가/저가/종가
- **예상 difficulty**: 쉬움

---

### 18. 장대양봉 마루보주 (Marubozu)

- **정의**: 위아래 꼬리 없는 장대양봉 — 시가=저가, 종가=고가. 강한 매수세 신호. 이시이 카츠토시 책 Rule 51~53.
- **출처**: 책 2 (이시이 카츠토시) — [교보 2권 참조](https://product.kyobobook.co.kr/detail/S000001014275)
- **카테고리 태그**: Stage B
- **버킷**: swing (1~3일)
- **한국 시장 적용 사례**: 급등 첫날 장대양봉 출현 후 익일 추가 상승 편승 패턴과 연결.
- **PIT-safe 가능성**: 가능 — 당일 종가 확정 후 적용.
- **필요 데이터**: 일봉 시가/고가/저가/종가, 거래량
- **예상 difficulty**: 쉬움

---

### 19. 불리시 엔걸핑 (Bullish Engulfing)

- **정의**: 하락 추세에서 소형 음봉 다음 날 더 큰 양봉이 전날 몸통을 완전히 감싸는 패턴. 강한 반전 신호. 거래량 동반 시 신뢰도 상승.
- **출처**: Investopedia (https://www.investopedia.com/terms/b/bullishengulfingpattern.asp) · Groww Candlestick Patterns Guide (https://groww.in/blog/candlestick-patterns)
- **카테고리 태그**: Stage A
- **버킷**: swing (1~3일)
- **한국 시장 적용 사례**: 지지선 근방 엔걸핑 + 거래량 급증이 가장 강한 매수 신호 조합.
- **PIT-safe 가능성**: 가능 — 2봉 확정 후 익일 진입.
- **필요 데이터**: 일봉 시가/고가/저가/종가, 거래량
- **예상 difficulty**: 쉬움

---

### 20. 모닝스타 (Morning Star)

- **정의**: 3봉 패턴. 1봉: 장대음봉. 2봉: 갭다운 후 작은 몸통(도지 또는 스피닝탑). 3봉: 장대양봉이 1봉 몸통의 50% 이상 회복. 강한 상승 반전.
- **출처**: Investopedia (https://www.investopedia.com/terms/m/morningstar.asp) · Groww Candlestick Patterns (https://groww.in/blog/candlestick-patterns)
- **카테고리 태그**: Stage A
- **버킷**: swing (3일 패턴)
- **한국 시장 적용 사례**: 코스닥 저점 확인 패턴으로 유효. 2봉의 갭다운이 한국 시장에서는 작을 수 있으므로 몸통 크기로 보완 판단.
- **PIT-safe 가능성**: 가능 — 3봉 종가 확정 후 익일 진입.
- **필요 데이터**: 일봉 시가/고가/저가/종가
- **예상 difficulty**: 중간 (3봉 패턴 인식 + 50% 회복 조건)

---

### 21. 이브닝스타 (Evening Star)

- **정의**: 모닝스타 반대. 1봉: 장대양봉. 2봉: 갭업 후 작은 몸통. 3봉: 장대음봉이 1봉 몸통의 50% 이상 잠식. 강한 하락 반전.
- **출처**: Investopedia (https://www.investopedia.com/terms/e/eveningstar.asp)
- **카테고리 태그**: Stage C
- **버킷**: swing (3일 패턴)
- **한국 시장 적용 사례**: 고점권 청산 신호. 2봉에서 상한가 부근 거래 후 3봉 급락 시 전형적 패턴.
- **PIT-safe 가능성**: 가능 — 3봉 종가 확정 후 청산.
- **필요 데이터**: 일봉 시가/고가/저가/종가
- **예상 difficulty**: 중간

---

### 22. 쓰리 화이트 솔저스 (Three White Soldiers)

- **정의**: 연속 3개 장대양봉, 각 봉이 전봉 몸통 내에서 시가 시작, 각 봉 신고가 마감. 강한 다중봉 상승 반전. 단, 거래량 급증 동반 필수.
- **출처**: [TradingSim Three White Soldiers](https://www.tradingsim.com/blog/three-white-soldiers) · [ChartMill](https://www.chartmill.com/documentation/technical-analysis/candlestick-patterns/446-three-white-soldiers)
- **카테고리 태그**: Stage A
- **버킷**: swing (3~5일)
- **한국 시장 적용 사례**: 급락 이후 3일 연속 양봉 회복 시 중기 추세 전환 신호. 한국 시장 상한가(+30%) 제도로 인해 3봉 모두 상한가면 별도 "점상한가 연속" 패턴으로 분류.
- **PIT-safe 가능성**: 가능 — 3봉 확정 후 진입.
- **필요 데이터**: 일봉 시가/고가/저가/종가, 거래량
- **예상 difficulty**: 쉬움

---

### 23. 브레이크어웨이 갭 (Breakaway Gap)

- **정의**: 장기 횡보/패턴 완성 후 상당한 갭 발생. 새로운 추세 시작 신호. 갭 구간이 지지(상향 갭) 또는 저항(하향 갭)으로 전환. 갭 채움 없이 추세 지속.
- **출처**: Investopedia (https://www.investopedia.com/terms/b/breakawaygap.asp) · TradingMetrics Gap Patterns
- **카테고리 태그**: Stage A (상향 갭) / Stage C (하향 갭)
- **버킷**: swing~mid (1~10일)
- **한국 시장 적용 사례**: 공시·실적 서프라이즈 당일 갭 발생이 전형적. 갭 구간이 이후 지지선 역할.
- **PIT-safe 가능성**: 가능 — 갭 당일 종가 확정 후 적용.
- **필요 데이터**: 일봉 시가/전일종가, 거래량
- **예상 difficulty**: 쉬움

---

### 24. 익스호스천 갭 (Exhaustion Gap)

- **정의**: 추세 말단에서 최후의 갭 발생. 이후 추세 소진 → 반전. 브레이크어웨이 갭과 형태 유사하나 추세 끝에 위치. 갭 채움(gap fill) 발생 시 신호 확정.
- **출처**: Investopedia (https://www.investopedia.com/terms/e/exhaustiongap.asp) · TradingMetrics
- **카테고리 태그**: Stage C (상승 추세 말단)
- **버킷**: swing (1~5일)
- **한국 시장 적용 사례**: 과열 급등 종목 마지막 갭상승 → 익일 갭 채움 발생 시 고점 확인. 매도 기준으로 활용.
- **PIT-safe 가능성**: 부분 — 갭 발생 당일에는 추세 끝인지 중간인지 불명확. 익일 갭 채움 확인 후 적용 권장.
- **필요 데이터**: 일봉 시가/전일종가, 이전 추세 방향
- **예상 difficulty**: 어려움 (브레이크어웨이와 구분 어려움)

---

### 25. 아일랜드 리버설 (Island Reversal)

- **정의**: 추세 방향으로 갭 발생(첫 번째 갭) → 소규모 가격 군집(섬) 형성 → 반대 방향 갭(두 번째 갭) 발생으로 섬이 고립. 강력한 반전 신호. 두 번째 갭 돌파 + 거래량 스파이크 필수.
- **출처**: [TradingMetrics Island Reversal](https://docs.tradingmetrics.com/en/technical-analysis/trading-patterns/gap-patterns/island-reversal)
- **카테고리 태그**: Stage C (상단 아일랜드) / Stage A (하단 아일랜드)
- **버킷**: swing~mid (3~15일)
- **한국 시장 적용 사례**: 테마주 과열 후 하락 갭 발생 시 하단 아일랜드 형성. 드물지만 신뢰도 매우 높음.
- **PIT-safe 가능성**: 가능 — 두 번째 갭 확정(다음날 시가) 기준 진입.
- **필요 데이터**: 일봉 시가/전일종가, 거래량
- **예상 difficulty**: 어려움 (두 갭의 대칭성 인식)

---

### 26. 일봉/주봉 정배열 (Golden MA Alignment)

- **정의**: 이동평균선이 단기→장기 순서로 위에서 아래 배열. 일봉 기준: 5일 > 10일 > 20일 > 60일 > 120일. 모든 선이 우상향. 추세 강세 확인 신호.
- **출처**: [한국투자교육원](https://www.kcie.or.kr/mobile/guide/2/13/web_view?series_idx=&content_idx=1317) · 책 1 (강창권, 2장 이동평균선) — [교보 1권 참조](https://product.kyobobook.co.kr/detail/S000217567051)
- **카테고리 태그**: Stage B (추세 확인)
- **버킷**: swing~mid (3~20일)
- **한국 시장 적용 사례**: 한국 투자자들이 가장 많이 쓰는 필터. 5·20·60일선 정배열이 실전 최소 조건.
- **PIT-safe 가능성**: 가능 — 종가 기준 이평선 계산.
- **필요 데이터**: 일봉 종가 (최소 120일)
- **예상 difficulty**: 쉬움

---

### 27. ABCD 패턴

- **정의**: A(상승 시작) → B(1차 고점) → C(눌림, A보다 높은 저점) → D(신고가). C 지점 안착 확인 후 C 근처 매수. 손절: C 이탈. 청산: D 도달 시 절반 청산 후 잔량 손절 이동.
- **출처**: 책 3 (앤드루 아지즈, 전략1) — [교보 3권 참조](https://product.kyobobook.co.kr/detail/S000001777389)
- **카테고리 태그**: Stage A (C 눌림 진입)
- **버킷**: swing (1~5일)
- **한국 시장 적용 사례**: 장중 분봉에서도 유효. C 지점이 전일 종가 이상이면 신뢰도 높음.
- **PIT-safe 가능성**: 가능 — C 지점 확인 후 진입.
- **필요 데이터**: 분봉 또는 일봉 고가/저가/종가
- **예상 difficulty**: 중간

---

## 종합 평가

### 즉시 코드화 우선순위 Top 5

1. **일봉 정배열** (컨셉 26) — 데이터 요건 단순(일봉 종가만), 계산 명확, 기존 MA 인프라 재사용. 모든 전략의 사전 필터로 즉시 적용 가능.
2. **이중 바닥 (Double Bottom)** (컨셉 3) — 2개 저점 + 저항선 돌파 로직. 성공률 88%. 코스닥 급락 후 반등 포착에 실전 적합.
3. **강세 깃발형 (Bull Flag)** (컨셉 8) — 기존 ORB·Bull Flag 전략 인프라 존재. 성공률 91.5%. 분봉/일봉 모두 적용 가능.
4. **망치형 캔들 (Hammer)** (컨셉 16) — OHLC 4개 데이터만으로 즉시 계산. 지지선 필터와 조합 시 실전 정밀도 향상.
5. **불리시 엔걸핑** (컨셉 19) — 2봉 패턴, 코드 단순, 거래량 필터와 결합 시 신뢰도 높음.

### PIT 위험 컨셉

- **익스호스천 갭** (컨셉 24): 당일에는 추세 중간 갭인지 소진 갭인지 판단 불가. 반드시 익일 갭 채움 확인 후 사용. Look-ahead 위험 있음 — 반드시 D+1 확인 강제.
- **모닝스타 / 이브닝스타** (컨셉 20, 21): 2봉째 갭 조건이 한국 시장에서 불명확할 경우 임의 완화 금지. 조건 완화 시 false positive 증가.
- **아일랜드 리버설** (컨셉 25): 두 번째 갭이 확정된 시점(당일 시가)에만 진입. 갭 예측 기반 선진입 금지.

### 향후 확장 메모

- 컨티뉴에이션 갭(Runaway/Measuring Gap): 추세 중반 갭. 이번 범위에 포함 안 됨. 향후 추가 조사 권장.
- V 패턴 / W 패턴: 이중 바닥/천장의 빠른 버전. 분봉 스캘핑에 유용. 별도 컨셉으로 분리 가능.
- 한국 특수 패턴 확장: 점상한가 연속 2일, 하한가 탈출, 상한가 눌림목은 00_kyobo_books.md에 포함되어 있으나 이 파일에서는 차트 구조 패턴에 집중하여 제외. Phase 5 후속 파일로 분리 권장.

---

## 참고 자료

- [Bulkowski Pattern Index — thepatternsite.com](https://thepatternsite.com/chartpatterns.html)
- [Bulkowski Visual Index of Chart Patterns](https://thepatternsite.com/visualcpindex.html)
- [VT Markets Chart Patterns Cheat Sheet 2025](https://www.vtmarkets.com/discover/chart-patterns-cheat-sheet-2025-stock-trading-patterns-guide/)
- [TradingMetrics Island Reversal Gap Pattern](https://docs.tradingmetrics.com/en/technical-analysis/trading-patterns/gap-patterns/island-reversal)
- [Groww — 38 Candlestick Patterns](https://groww.in/blog/candlestick-patterns)
- [TradingSim Three White Soldiers](https://www.tradingsim.com/blog/three-white-soldiers)
- [ChartMill Three White Soldiers](https://www.chartmill.com/documentation/technical-analysis/candlestick-patterns/446-three-white-soldiers)
- [한국금융투자자보호재단 — 차트 기초](https://www.kcie.or.kr/mobile/guide/2/13/web_view?series_idx=&content_idx=1317)
- 책 1: 강창권 "주식투자 단기 트레이딩의 정석" — https://product.kyobobook.co.kr/detail/S000217567051
- 책 2: 이시이 카츠토시 "주식 데이트레이딩의 신 100법칙" — https://product.kyobobook.co.kr/detail/S000001014275
- 책 3: 앤드루 아지즈 "도박꾼이 아니라 트레이더가 되어라" — https://product.kyobobook.co.kr/detail/S000001777389
