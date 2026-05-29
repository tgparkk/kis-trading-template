# Changelog 2026-05-29 — O'Shaughnessy What Works on Wall Street (Book 10, 최종)

> 책 연구 시리즈 **최종 10권**. depth-first 6단계 완주(같은 세션, 끝까지 자동).
> 세 번째 펀더멘털 책 + 다팩터 횡단면 순위. **10권 시리즈 완료.**

## 핵심 결과 (per-trade)
- **베스트: low_psr (단일 저PSR)** — Variant B 200거래 승률 54.5% 평균 +4.63%/거래 (집계 +6.67%, A +8.26%)
- value_composite(182T, +3.85%) / trending_value(138T, +3.89%) / all_AND(74T, +1.6%)
- **단일 저PSR이 4팩터 복합·Trending Value 압도** → O'Shaughnessy "PSR=가치 팩터의 왕" 한국 확인
- Trending Value(플래그십) 부진: 6개월 모멘텀 불가(16종목)→3개월 + 단일 BULL이라 모멘텀 틸트 무력

## 구현 (executor 직원, opus)
- 신규 4파일: strategies/books/oshaughnessy_value/{__init__,rules,strategy}.py + scripts/run_oshaughnessy_value.py
- **PSR 재구성**: psr 컬럼 100% NULL이나 revenue ~100% → PSR=(market_cap/1e8)/revenue
- VC1식 4팩터 복합(PSR+PE+PB+EV/EBIT 백분위 평균) + Trending Value(저평가40%→3개월 모멘텀) + low_psr 단일
- Greenblatt `_build_cross_sectional_ranks` 확장 → vc_rank/tv_rank/psr_rank/n_eligible ctx 주입
- 룰 3종: value_composite(75)/trending_value(78)/low_psr(70). Variant A(sl0.20/tp0.99/mh120) B(sl0.08/tp0.12/mh20)

## 데이터 제약
- **진짜 VC2/VC3 불가**: 주주수익률(dividend_yield 100% NULL)·P/CF·EBITDA 부재 → 4판 헤드라인 손실. VC1식만
- **6개월 모멘텀 불가**: ≥140봉 16종목만 → 3개월(63봉) 사용 (책 스펙 이탈)
- universe=factor:79(market_cap 6개월 창), EV 상향편향, 연간 데이터, 금융/유틸 제외 불가

## 검증
- pytest tests/books/: 47 passed. leaderboard 132→140행(osullivan 8행). PSR median 0.44(정상)

## 🏁 10권 시리즈 완료 — 5대 교훈
1. **"단순/단일/상대 > 복잡/다지표/절대" (5책 연속)**: Minervini/Elder/Lynch/Greenblatt/O'Shaughnessy
2. 일봉 추세/가치가 분봉 인트라데이보다 한국 적합
3. 최고: Elder ema_pullback(+23.76%)·Minervini volume_dryup(+20.27%), Sharpe 1.2~1.4
4. 펀더멘털 3책 inconclusive(연간·6개월창·NULL·생존편향), 단 저PSR·Magic 순위 양 엣지
5. 전 책 BULL 편향 → walk-forward·약세장 검증이 CANDIDATE 전제

## CANDIDATE 우선순위 (walk-forward 후)
1. Elder ema_pullback 2. Minervini volume_dryup (3. 펀더멘털 순위는 market_cap 백필 후)

## 산출물
- 조사 research.md / 설계 docs/superpowers/specs/2026-05-29-oshaughnessy-design.md / 리포트 report.md
- index.md에 10권 통합 요약 추가
