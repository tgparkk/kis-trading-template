# 책 2: Mike Bellafiore — One Good Trade / The PlayBook

> 카테고리: 인트라데이 (분봉, prop trading)  
> 데이터 입도: 분봉 (minute_candles)  
> 조사 완료: 2026-05-28  
> 코드화·백테스트: 진행 예정  
> 조사 원본: [strategies/books/bellafiore_playbook/RULES_RESEARCH.md](../strategies/books/bellafiore_playbook/RULES_RESEARCH.md)

## 1. 책 요약

Mike Bellafiore는 뉴욕 prop trading firm **SMB Capital** 공동창업자. *One Good Trade*(2010) + *The PlayBook*(2013) 두 권.

핵심 차별점 (vs 아지즈):
- 단순 패턴이 아닌 **다섯 의사결정 레이어** 복합: Big Picture · Intraday Fundamentals · Technicals · Tape Reading · Intuition
- **Stocks In Play** 명확 정량화: RVOL ≥ 2 (In Play), ≥ 3 (고신뢰), ≥ 5 (강력) — 아지즈보다 임계값 명시적
- 트레이더 개인의 강점에 맞는 셋업 4~5개를 발굴·정밀화 (vs 범용 신호)
- Reasons2Sell 프레임워크: 추세 이탈 / 저항 도달 / 비정상 매도 / 뉴스 변화

## 2. 10개 셋업 (조사 결과)

| # | 셋업 | 한국 코드화 난이도 | 비고 |
|---|---|---|---|
| 1 | Opening Drive | ❌ 어려움 (Level2 의존) | 09:00~09:15 단기 모멘텀, 테이프 핵심 |
| 2 | **Second Day Play** | ✅ 가능 | D-1 ±5% 극단 마감 + D+1 통합 후 레벨 재접근 |
| 3 | **Bull/Bear Flag** | ✅ 가능 | 폴+플래그 패턴, R:R 3:1, In Play 종목만 |
| 4 | Pullback Trade | ⚠️ 부분 가능 | 30~60% 되돌림, 추세선 의존, 재량 큰 편 |
| 5 | **Range Trade** | ✅ 가능 | 명확 지지·저항, 오후 세션, 가짜 돌파 후 재진입 |
| 6 | **Fade Trade (VWAP 평균회귀)** | ✅ 가능 | VWAP ±2% 이격 + RSI(2)>90 |
| 7 | **Opening Consolidation Breakout** | ✅ 가능 | 갭 + 통합 + 브레이크아웃 |
| 8 | Intraday Relative Strength | ⚠️ 부분 가능 | KOSPI 대비 종목 RS, 섹터 비교 필요 |
| 9 | Trade2Hold | ❌ 어려움 | 재량적 추세선, 테이프 흡수 판단 |
| 10 | **Catalyst Gap Trade** | ✅ 가능 | 갭 ±3% + RVOL≥3 + VWAP 유지 + 9/21 EMA |

**우선 코드화 대상 (6개)**: Second Day Play, Bull/Bear Flag, Range Trade, Fade Trade, Opening Consolidation Breakout, Catalyst Gap Trade

## 3. 아지즈와의 차이점

| 항목 | Bellafiore | Aziz |
|---|---|---|
| In Play 기준 | RVOL ≥ 2/3/5 임계값 명시 | Float + 갭% + 스캐너 |
| 촉매 의존 | 매우 강조 (촉매 없으면 회피) | 강조하지만 기술적 갭도 OK |
| 종목 특성 | 대형·중형주 (뉴욕 prop firm) | 소형·저가주 + 중형 |
| 신호 정량성 | 일부 명시 (RVOL, RSI(2)) | 더 패턴 중심 (ABCD 등) |
| 핵심 도구 | Level 2 호가창 + Tape Reading | 차트 패턴 + VWAP/EMA |

## 4. 한국 시장 적용 노트

- **Level 2 호가창**: KIS API 10단계 호가 가능. 미국식 tape speed는 어렵지만 호가창 불균형 정도 측정 가능
- **RVOL 자체 계산**: `현재까지 누적 거래량 / (평균일거래량 × 경과시간비율)` — daily_prices에서 평균거래량 + minute_candles에서 누적
- **시간대**: 미국 09:30~16:00 → 한국 09:00~15:30. Opening Drive 09:00~09:15
- **공매도 제약**: 일부 short 셋업(Fade short, Trend short) 한국 개인 적용 어려움 — long-only 백테스트로 전환

## 5. 다음 단계

1. **규칙맵 README 작성**: 6개 코드화 대상에 대해 정확한 진입·청산 수치 + 한국 임계값 매핑
2. **시그널 함수 코드화**: `strategies/books/bellafiore_playbook/rules.py` (6개 함수)
3. **단위 테스트**: `tests/strategies/books/bellafiore_playbook/test_rules.py`
4. **백테스트**: 기존 인프라(BookBacktester + CLI) 그대로 사용. universe 전종목 또는 top_volume:50, 3기간
5. **통합 문서 업데이트**: 결과 추가, 책 의도 복원 (RVOL 필터 등) 시도

진행 시 약 1~2시간 예상.

## 6. 산출물 (현재까지)

| 종류 | 경로 |
|---|---|
| 조사 원본 | `strategies/books/bellafiore_playbook/RULES_RESEARCH.md` (10셋업 상세, 18 출처) |
| 코드 | 진행 예정 |
| 백테스트 결과 | 진행 예정 |
