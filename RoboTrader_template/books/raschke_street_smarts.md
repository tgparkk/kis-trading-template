# 책 3: Linda Raschke — Street Smarts: High Probability Short-Term Trading Strategies

> 카테고리: 단기 트레이딩 (인트라데이 + 스윙 혼합)  
> 데이터 입도: 일봉 + 분봉 혼합  
> 조사 완료: 2026-05-28  
> 코드화·백테스트: 진행 예정  
> 조사 원본: [strategies/books/raschke_street_smarts/RULES_RESEARCH.md](../strategies/books/raschke_street_smarts/RULES_RESEARCH.md)

## 1. 책 요약

Linda Bradford Raschke + Laurence Connors 공저(1995/1996). 미국 선물·주식 단기 트레이딩 셋업 플레이북.

특징 (vs 아지즈/Bellafiore):
- **일봉 기반 셋업 다수** — 분봉 인트라데이만 다룬 두 책과 차별
- **인디케이터 명확** — ADX, Stochastic, RSI, EMA, 볼린저밴드 정확한 파라미터
- **거짓 돌파 페이드** + **변동성 사이클** + **추세 풀백** 세 축
- Raschke 본인이 "Holy Grail은 2010년대에도 여전히 유효" 언급

## 2. 10개 셋업

### 한국 분봉 코드화 가능 (5개) — 우선 진행

| # | 셋업 | 진입 조건 요약 | 데이터 |
|---|---|---|---|
| 1 | **Holy Grail** ⭐ | ADX(14)>30 + 20EMA 첫 풀백 + 풀백봉 고가 돌파 | 분봉 또는 일봉 |
| 2 | Anti | %K(7)/%D(10) 스토캐스틱 훅 + 20EMA 필터 + 임펄스 후 | 분봉 |
| 3 | Gimmee Bar | 볼린저밴드 횡보 + 밴드 하단 터치 + 반전 양봉 | 분봉 |
| 4 | NR4 변형 | 직전 3봉 최소 범위 + 변동성 압축 | 분봉 (변형) |
| 5 | Momentum Pinball | 전일 RSI(3) of ROC(1) < 30 + 첫 1시간봉 돌파 | 분봉 + 일봉 |

### 한국 일봉 전용 (5개) — 후속

| # | 셋업 | 데이터 |
|---|---|---|
| 6 | Turtle Soup | 일봉 |
| 7 | Turtle Soup Plus One | 일봉 |
| 8 | 80-20 | 일봉+분봉 |
| 9 | ADX Gapper | 일봉 |
| 10 | 2-Period ROC | 일봉 |

## 3. 아지즈·Bellafiore와의 비교

| 항목 | 아지즈 | Bellafiore | Raschke |
|---|---|---|---|
| 데이터 입도 | 분봉만 | 분봉만 | **일봉 + 분봉 혼합** |
| 인디케이터 | 패턴 중심 | RVOL·RSI(2) | **ADX·Stoch·EMA·BB 정확** |
| 셋업 방향성 | 모멘텀 추격 | 평균회귀 + 모멘텀 | **변동성 압축 + 풀백 + 페이드** |
| 한국 적용 난이도 | 분봉만 → 쉬움 | 분봉만 → 쉬움 | 일봉 5개 분리 진행 필요 |

## 4. 진행 계획

### Phase 1 — 분봉 코드화 (현재)
- Holy Grail / Anti / Gimmee Bar / NR4 변형 / Momentum Pinball 변형
- 기존 BookBacktester 활용. 1~2시간 소요
- 풀런 → 리포트

### Phase 2 — 일봉 백테스터 (후속)
- 기존 `backtest/engine.py` 일봉 엔진 활용 또는 BookBacktester 일봉 데이터 적용
- Turtle Soup / 80-20 / ADX Gapper / 2-Period ROC / Turtle Soup +1
- 일봉 데이터 다이렉트 사용

## 5. 산출물 (현재까지)

| 종류 | 경로 |
|---|---|
| 조사 원본 | `strategies/books/raschke_street_smarts/RULES_RESEARCH.md` (10셋업, 18 출처) |
| 코드 | Phase 1 진행 예정 |
| 백테스트 결과 | Phase 1 풀런 후 |
