# Book 11 문병로 Phase 0 — 영업현금흐름(OCF) 백필 (2026-05-30)

## 배경
Book 11 "문병로 메트릭 스튜디오"(한국 첫 저자책)는 사장님 결정으로 5팩터 완전체(PBR·PER·PSR·POR·**PCR**) 진행. PCR(주가/영업현금흐름)을 위해 `financial_statements`에 영업활동현금흐름 컬럼이 필요했으나 DB에 전무 → Phase 0로 백필.

## 조사 결론
- **소스 = DART 유일**: KIS 재무 API는 현금흐름표 미지원(손익/대차/비율만). DART `fnlttSinglAcntAll.json`(sj_div='CF')만 가능.
- DART 키는 이미 `RoboTrader_template/.env`의 `OPENDART_API_KEY`에 확보돼 있었음(`backfill_corp_events.py`가 사용 중). RoboTrader_quant엔 KIS 키만 있고 DART 코드 없음(재사용 불가).

## 작업
1. **스키마**: `financial_statements.operating_cash_flow NUMERIC(20,2)` 추가. `init-scripts/01-init.sql` 반영. (비파괴 ADD COLUMN)
2. **스크립트 신규**: `scripts/backfill_operating_cash_flow.py`
   - corp_code 매핑(corpCode.xml) → DART fnlttSinglAcntAll CFS(연결) 우선·OFS(별도) fallback
   - 영업현금흐름 추출: account_id `ifrs-full_CashFlowsFromUsedInOperatingActivities` 우선, account_nm '영업활동' 부분일치 fallback
   - **단위 /1e8**(DART 원 → 억원, revenue 컬럼 정합) — 과거 책 1e8 단위버그 회피
   - 멱등: `operating_cash_flow IS NULL` 행만 UPDATE. status 013(부재) graceful skip. throttle 0.3초.
3. **실행 이슈**: 서브에이전트가 백그라운드 잡을 유지 못해 1차 46/131종목에서 중단 → **하니스 레벨 run_in_background로 재실행**(--years 2015~2025, 2015 이전은 DART 원천 부재라 호출 낭비 제외)하여 완주.

## 결과
- **131/131 종목**, 1,287행 채움. DART 가용기간(2015~2025) 충전율 **92.4%**(1,287/1,393).
- 연도별 86%(2015)→99%(2023~2025). 부호: 양 1,087·음 200(15.5% OCF 적자기업).
- 범위 -23.5조 ~ +53.4조원, 중앙값 520억. **단위 억원 확정**(SK하이닉스 2024 OCF 29.8조 실제 일치).

## 미수집 (PCR→4팩터 fallback 대상)
- **2014 이하 1,285행 영구 NULL**(DART XBRL 2015 시작 한계).
- 2015+ 잔여 106행(초기연도 미상장·CF 미제출, 산발적). 삼성전자 005930은 universe에 행 자체 없음(대상 외).

## 다음 = Phase 1
5팩터 코드화: `strategies/books/moonbyungro_metric/` + `scripts/run_moonbyungro_metric.py`(O'Shaughnessy 복제·확장), PCR=(market_cap/1e8)/ocf, ocf>0 가드+캡 → 다년(2021~2026) 다국면 백테스트.

상세 리포트: [reports/books_research/moonbyungro_metric/phase0_ocf_backfill.md](../reports/books_research/moonbyungro_metric/phase0_ocf_backfill.md)

## 미커밋
스키마 ALTER·신규 스크립트·init-sql 수정·리포트 — git 커밋은 사장님 승인 대기.
