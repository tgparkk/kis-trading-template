# Minervini VCP (Book 5/10) — 단권 깊이 조사 설계서

> 작성일: 2026-05-29
> 책: Mark Minervini — *Trade Like a Stock Market Wizard* (한역: 초수익 성장주 투자)
> Book ID: `minervini_vcp`
> 전체 인덱스: [reports/books_research/index.md](../../../RoboTrader_template/reports/books_research/index.md)
> 직전 책: O'Neil CANSLIM (Phase A+B) — 표본 7건 한계 인식

---

## 1. 작업 원칙

- **한 권 깊이 + 기록 후 다음 책** (사장님 지시, 2026-05-29).
  병렬 진행 금지. Minervini 완전 종료(Phase 5 커밋) 후에야 Weinstein 탐색 시작.
- 조사 → 기록 → 코드화 → 백테스트 → 리포트 → 커밋 순서 고정.
- 책간 비교는 `reports/books_research/index.md` 통합 인덱스에서만 갱신.

## 2. 작업 단계 (Phase 0~5)

| Phase | 산출물 | 핵심 |
|---|---|---|
| 0 조사 | (workspace) | 책 원본 + 웹·세미나·인터뷰 + Trend Template 교차검증 |
| 1 기록 | `reports/books_research/minervini_vcp/research.md` | 셋업 카탈로그·SEPA·VCP·RS·청산·발화차이 |
| 2 코드화 | `strategies/books/minervini_vcp/rules.py`, `strategy.py`, `screener.py(필요시)` | `_base_book_strategy` 재사용 |
| 3 백테스트 | `reports/books_research/minervini_vcp/backtest_*.parquet` | daily_prices 실측 224일 + RS 자체 계산. universe `top_volume:50`. 청산 Variant A/B 이중 |
| 4 리포트 | `reports/books_research/minervini_vcp/report.md` + `index.md` 갱신 | 5번 행 갱신, 5권 비교 섹션, CANDIDATE_ALPHAS 자격 검토 |
| 5 changelog | `memory/changelog-2026-05-29-minervini.md` + 단계별 커밋 | 종료 후 Weinstein 탐색 시작 |

## 3. 조사 범위 (Phase 0)

### 3.1 책 원본
- *Trade Like a Stock Market Wizard* (2013) — 전체 SEPA 챕터.
- *Think & Trade Like a Champion* (2017) — 리스크 관리·R-multiple 보강.

### 3.2 웹 보조
- IBD/MarketSmith의 RS Rating 정의·계산식.
- Minervini.com 블로그·인터뷰 발화.
- 1997 / 2021 US Investing Championship 우승 시점 포지셔닝 보고.

### 3.3 교차검증 대상
- **SEPA Trend Template 8조건** — 책 본문 vs 외부 인터뷰 차이 점검.
- **VCP 정량 기준** — 진폭 수축 비율(15% → 10% → 5% 식) 책-블로그 일관성.
- **R-multiple 청산** — 책 발화(7~8%)와 실제 우승 시 운용(2~3% 사용 보고) 차이.

### 3.4 산출물 형식 (research.md 골격)
```
1. 핵심 개념
2. SEPA Trend Template (8조건 정량 정의 + 책-외부 차이)
3. VCP Pattern (단계·진폭·거래량·피벗)
4. RS 자체 계산 (IBD 식 + 단순 대체)
5. 청산 룰 (Variant A/B)
6. 셋업 카탈로그 (10개+, 코드화 가능 여부 표시)
7. 한국 시장 적용 시 주의점
8. 참고 자료
```

## 4. 핵심 규칙 정의

### 4.1 SEPA Trend Template (스크리너, 8조건)
1. Price > 150 MA, Price > 200 MA
2. 150 MA > 200 MA
3. 200 MA가 최소 1개월(20거래일)+ 상승 추세
4. 50 MA > 150 MA > 200 MA
5. Price > 50 MA
6. 52주 신고가 −25% 이내
7. 52주 신저가 +30% 이상
8. RS Rating ≥ 70 (희망 80+)

### 4.2 VCP Pattern (엔트리)
- 베이스 길이: 7주~수개월
- 수축 단계: 2~6단계, 각 단계 진폭이 직전의 50% 이내로 좁아짐
- 거래량 dry-up: 수축 단계 일평균 거래량 < 베이스 시작 시점 20일 평균
- 피벗 포인트: 베이스 내부 최고점 (base resistance level — buy stop 대상)
- 돌파 트리거: 피벗 + 종가 돌파 + RVOL ≥ 1.5x

### 4.3 RS 자체 계산
- **방식 1 (IBD 근사)**: 가중 수익률 = 0.40×R(12W) + 0.20×R(26W) + 0.20×R(39W) + 0.20×R(52W). 전 universe 백분위 → 0~99.
- **방식 2 (단순)**: 12주 수익률 universe 백분위.
- 1차 구현은 방식 2 (단순 12주 백분위). 데이터 확장 시 방식 1(IBD 근사)로 업그레이드. 사유: 워밍업 봉 절감 (RS 52주 260일 → 12주 60일) — section 5.1 정책과 일치.

## 5. 백테스트 명세 (Phase 3)

### 5.1 데이터
- 테이블: `daily_prices` (실측 224거래일, 2025-07-01 ~ 2026-05-29)
- universe: `top_volume:50` (일평균 거래대금 상위 50) — 분봉 책들과 동일 정책
- 워밍업:
  - 1차(엄격): 200 MA + RS 52주(=260일) → 워밍업 260거래일, 데이터 224일 < 260 → 검증 불가
  - 2차(완화): 200 MA + RS 12주(=60일) → 워밍업 220거래일 (rule_trend_template 가드), 데이터 224일 → 검증 가능 ~4일 (trend_template 한정)
  - 3차(rule별 최소): simulate_one_stock 의 warmup_bars=60 (RS 12주만). vcp_breakout/tight_closes/volume_dryup 은 진입 가능. trend_template 은 220 guard로 데이터 218일 종목 영구 False.
- 기본 정책: 3차(rule별 최소) 채택. RS는 방식 2(단순 12주). 표본 부족 시 O'Neil처럼 미등록 가능성 수용.
- daily_prices 실측: 2025-07-01 ~ 2026-05-29 = 224일. spec 초기 가정 "~318일"은 오류 — 실측 반영.

### 5.2 청산 Variant (이중 비교)

| Variant | sl | tp | 트레일링 | mh | 출처 |
|---|---|---|---|---|---|
| A (책 의도) | 7~8% | 2~3R (소급 20~24%) | 50 MA 이탈 | 35거래일 | Minervini 발화 |
| B (책간 획일) | 8% | 12% | 없음 | 20거래일 | 분봉 책 sl3/tp5/mh120 일봉 환산 |

각 룰 단독 + 통합 비교 모두 산출.

### 5.3 평가지표
- 1급: PnL, Sharpe
- 2급: Calmar, MaxDD, Sortino, Hit Rate, n_trades, avg_hold_days
- 추가: 국면별 분해 (BULL/BEAR/SIDEWAYS, KOSPI 기준)

### 5.4 품질 게이트 (기존과 동일)
- ✅ no-lookahead (t+1 데이터 접근 금지)
- ✅ 거래비용 왕복 0.21% (매수+매도+세금)
- ✅ 슬리피지 0.10% 단방향
- ✅ adj_factor 반영 (corp_events 백필 완료)

## 6. 코드화 명세 (Phase 2)

### 6.1 파일 구성
```
strategies/books/minervini_vcp/
├── __init__.py
├── rules.py           # SEPA 8조건 + VCP 패턴 + RS 자체 계산 함수
├── strategy.py        # MinerviniVCPStrategy (BookStrategy 상속)
└── screener.py        # SEPA 통과 후보 필터 (선택, 일봉 전용)
```

### 6.2 인터페이스
- BookStrategy 베이스 재사용 — `_base_book_strategy.py`
- CLI: `python scripts/run_books_research.py --book minervini_vcp --period {YYYY-MM} --all-modes`
- 청산 변종 옵션: `--exit-variant A|B|both`

### 6.3 규칙 단독·통합 모드
- **single**: 각 규칙 단독 (SEPA only / VCP only / SEPA+VCP)
- **all_AND**: SEPA + VCP + 피벗 돌파 + RVOL ≥ 1.5 모두 충족

## 7. 결과물 (Phase 4)

### 7.1 report.md 구조
```
1. 요약 (베스트 룰·기간·청산 Variant)
2. 풀런 결과 표 (Variant A / Variant B 분리)
3. 국면별 분해
4. 5권 비교 (아지즈·Bellafiore·Raschke·O'Neil·Minervini)
5. CANDIDATE_ALPHAS 자격 검토 (표본·Sharpe·Calmar 기준)
6. 한계와 후속 검증 항목
```

### 7.2 인덱스 갱신
- `index.md` 진행 상태 표 5번 행 → ✅ 완료
- Best PnL · Variant 표기
- 5권 비교 섹션 추가

### 7.3 CANDIDATE_ALPHAS 자격
- 표본 ≥ 30 트레이드, Sharpe 양, Calmar ≥ 1.0 시 등록.
- O'Neil(표본 7건) 미등록 사례 — 동일 기준 적용.

## 8. 일정·산출 가정
- Phase 0~1: 1~2 세션
- Phase 2: 1 세션
- Phase 3: 1 세션
- Phase 4~5: 1 세션
- 총 4~5 세션 (~1주 페이스)

## 9. 다음 단계 (외부)
- Minervini Phase 5 커밋 종료 → Weinstein Stage Analysis(주봉) 디자인 착수.
- 추세 3권 종료 후 가치 3권(Lynch/Greenblatt/O'Shaughnessy) 또는 CANSLIM 표본 확대 재검증 중 사장님 결재.

---

## 부록 — 결정 로그 (2026-05-29 사장님 결재)

| 결정 | 선택 |
|---|---|
| 다음 그룹 | 추세 3권 (Minervini → Weinstein → Elder) |
| 진행 방식 | 순차 (1권씩 완료 후 다음) |
| 백테스트 기간 | daily_prices 전체 단일 긴 구간 + RS 자체 계산 (실측 224일) |
| 작업 흐름 | 한 권 깊이 + 기록 후 다음 책 (병렬 금지) |
| 조사 깊이 | 책 + 웹 + 세미나/인터뷰 + Trend Template 정량 교차검증 |
| 청산룰 | Variant A(Minervini 본인) + Variant B(책간 획일) 이중 비교 |
