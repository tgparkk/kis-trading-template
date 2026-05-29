# Changelog 2026-05-29 — Lynch One Up on Wall Street (Book 8)

> 트레이딩 책 연구 시리즈 Book 8. depth-first 6단계 완주(사장님 "끝까지 자동 진행" 승인).
> Elder(Book 7)에 이어 같은 세션 진행. 첫 **펀더멘털 단독** 책.

## 결정 사항 (사장님 승인)
- universe = **재무 보유 종목**(fundamentals:131, per 보유 79) — top_volume:50 ∩ 재무 = 10종목이라 사용 불가
- 끝까지 자동 진행

## 데이터 실태 (직원 라이브 DB 조회 — 설계 좌우)
- financial_statements 2,678행 / **131종목**. report_date 91% 12월 → **사실상 연간**(fiscal_quarter 공란)
- **psr·dividend_yield 100% NULL** → 자산주(psr)·PEGY(배당) 룰 불가 → 대체 룰
- per 46%·roe 45%·pbr/debt_ratio 39% NULL. net_income/operating_profit ≈0% NULL → 성장률은 raw NI로 계산
- top_volume:50 ∩ 재무 = **10종목**, per 보유 79, ≥120봉 46. 종목당 평균 ~124봉(6개월)
- net_income ≤0 가 18% → PEG 불안정

## 핵심 결과 (per-trade — 집계 PnL은 0거래 종목 희석으로 무의미)
- **표본 견고 유일 룰: value_balance_sheet** (저PBR<1.0+저PER<12+저부채<50%)
  - Variant B: 114거래 승률 52.6% 평균 +2.84%/거래
  - Variant A: 34거래 승률 50% 평균 +11.51%/거래 (forced_close 15건 견인)
- fast_grower 3~6T·stalwart 1~3T·garp_combo 10~32T — 표본 부족/무의미. all_AND 0거래
- **3회 연속 "단순 우위" 패턴**: 단순 가치 스크린 > 복잡 GARP/고성장 (Minervini·Elder와 동일)
- **결론: 데이터 제약으로 inconclusive. CANDIDATE_ALPHAS 부적격**

## 구현 (executor 직원, opus)
- 신규 4파일: strategies/books/lynch_one_up/{__init__,rules,strategy}.py + scripts/run_lynch_one_up.py
- 룰 4종: fast_grower(78)/stalwart(70)/value_balance_sheet(65)/garp_combo(72)
- **point-in-time 재무 조인**: effective_date=report_date+105일(한국 사업보고서 90일+버퍼) ≤ 거래일. YoY net_income 성장(prior 365일±). 가드: NI≤0 제외, |g_ni|>300 캡, per≤0 제외
- ctx["fund"] 주입(Minervini rs_value 방식). Variant A(sl12/tp50/mh120) B(sl8/tp12/mh20). warmup 20
- 운영 strategies/lynch/(PEG 단일룰)와 별도 — 혼동 금지

## 트러블슈팅
- executor 스모크가 leaderboard에 부분행(fundamentals:20, fast_grower만 131) 잔류 → 클린 재실행 전 lynch 행 제거 후 A/B all-modes 재실행
- Elder 교훈대로 RoboTrader_template/ cwd에서 실행

## 검증
- pytest tests/books/: 47 passed (회귀 없음)
- leaderboard 114→124행 (lynch 10행), 결과 parquet 8개

## 산출물
- 조사 research.md / 설계 docs/superpowers/specs/2026-05-29-lynch-one-up-design.md / 리포트 report.md / index.md 갱신

## 한계
- universe 비교성 단절(fundamentals:131 vs top_volume:50), 연간 데이터, 극소 N, NULL 다수, 짧은 이력, 생존편향, BULL 편향
- Lynch 13속성·정성 스토리·내부자/자사주 미반영(데이터 부재)

## 다음 책
- **Book 9** = greenblatt_magic_formula (Joel Greenblatt — Magic Formula). EBIT/EV + ROC 2지표 순위합산. Lynch 재무 PIT 파이프라인 재사용. EBIT/EV 컬럼(시총·부채) 가용성 사전 점검 필요.
