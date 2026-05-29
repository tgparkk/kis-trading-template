# Changelog 2026-05-29 — Greenblatt Magic Formula (Book 9)

> 책 연구 시리즈 Book 9. depth-first 6단계 완주(같은 세션, 끝까지 자동 진행).
> 두 번째 펀더멘털 책. 첫 **횡단면 순위** 전략.

## 핵심 결과 (per-trade — 집계는 0거래 희석)
- **베스트: magic_formula_top (순위 상위 20)**
  - Variant B: 197거래 승률 61.4% 평균 +4.88%/거래 — **펀더멘털 2책 최고 표본·성과** (>Lynch +2.84%)
  - Variant A: 38거래 승률 84.2% 평균 +32.29% — 단 forced_close 31/38 (BULL buy&hold 과대, 신뢰 낮음)
- **순위 작동 vs 절대 임계값 전멸**: threshold(EY>0.10 AND ROC>0.25)·high_roc_value(ROC>0.40) 0거래 — ROC max 0.247로 Greenblatt 미국 기준(ROC>25%) 한국 대형주 도달불가. → **"Magic Formula 본질 = 상대 순위"** 입증
- all_AND 0거래

## 🐛 단위 버그 발견·수정 (중요)
- `market_cap`은 **원 단위**(현대차 102.4조=1.024e14), `financial_statements`는 **억원 단위**(영업이익 97,725억) → 1e8배 불일치
- EV=market_cap+total_liabilities에서 market_cap이 압도 → EY=op/EV≈0 (전 7,965 bars EY=0.0000) → 순위가 사실상 ROC 단독
- 수정: `MARKET_CAP_UNIT_DIVISOR=1e8`로 market_cap을 억원 환산 후 EV 계산. 수정 후 EY p50=5.2% p90=11.7% max=19.4% 정상화
- 수정 후 magic_formula_top 재실행 (A +9.61→+10.04%, B +7.79→+8.07% per-stock mean)

## 구현 (executor 직원, opus + 수정 1회)
- 신규 4파일: strategies/books/greenblatt_magic/{__init__,rules,strategy}.py + scripts/run_greenblatt_magic.py
- EBIT=operating_profit, EV=market_cap/1e8+total_liabilities, ROC=operating_profit/(total_assets−current_liabilities)
- 룰 3종: magic_formula_top(순위)/magic_formula_threshold/high_roc_value
- **횡단면 순위 precompute**: 일자별 적격종목 EY·ROC 순위 합산→상위 N. ctx에 magic_rank+n_eligible 주입(Minervini RS식) + Lynch PIT fund 조인(105일 lag)
- 일자별 적격 universe 평균 66종목(min 26, 전 124일 ≥20). ROC>5.0 캡
- Variant A(sl0.20/tp0.99off/mh120) B(sl0.08/tp0.12/mh20). warmup 20

## 데이터 제약 (라이브 조회)
- **market_cap 2025-07-31~2026-02-02만(~124일, 6개월) + 79/131종목** → 순위 변형 6개월 단일 국면. 이전 8권과 기간·universe 단절
- EV 상향편향(현금 컬럼 없음 → EY 과소), 연간 데이터, 영업권 ROC 분모 포함(하향), 금융/유틸 제외 불가(섹터 컬럼 없음)

## 검증
- pytest tests/books/: 47 passed (회귀 없음)
- leaderboard 124→132행 (greenblatt 8행, magic_formula_top 2개만 거래), 결과 parquet

## 산출물
- 조사 research.md / 설계 docs/superpowers/specs/2026-05-29-greenblatt-magic-design.md / 리포트 report.md / index.md 갱신

## 다음 책
- **Book 10 (최종)** = osullivan_what_works (James O'Shaughnessy — What Works on Wall Street). 대규모 팩터 순위(Value Composite/Trending Value). Greenblatt 횡단면 순위 인프라 재사용. ⚠️ psr·dividend_yield 100% NULL → 가용 팩터(per/pbr/momentum) 한정.
