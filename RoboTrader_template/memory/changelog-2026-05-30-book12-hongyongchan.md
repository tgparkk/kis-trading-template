# Book 12 홍용찬 『실전 퀀트투자』 — 조사+코드화+백테스트 (2026-05-30)

## 조사 정정
홍용찬은 정통 가치투자가 아니라 **계량/시스템 퀀트 저자**(V차트는 최준철 등 타 저자). 대표작 『실전 퀀트투자』(2017). 시그니처 = 소형주(시총 하위 20%) + 4선 저밸류(PER+PBR+PCR+PSR) + 성장/마진/부채 게이트, 20종목, 분기 리밸런싱. 설계서: docs/superpowers/specs/2026-05-30-hongyongchan-design.md

## 사장님 방침
- **배당 전략 제외** — dividend_yield 백필/룰 미구현. 코어(4선+소형주20%+게이트)만.

## 코드화 (문병로 85% 재활용)
- 신규 `strategies/books/hongyongchan/{__init__,rules,strategy}.py` — 룰 3종(value4_low/small_value4/hong_combo) + HongYongchanStrategy.
- 신규 `scripts/run_hongyongchan.py` — 문병로 복제. POR 제거(4선), 소형주 40%→**20%**, hong_rank(소형주∩흑자∩성장YoY∩마진/ROE/부채, **skip-missing** 정책), --quarterly 옵션, variant Q/K/B. universe 131 동일.
- 신규 테스트 26개 → **pytest tests/books/ 95 passed**(기존 69+신규 26, 회귀 0).

## 백테스트 (2021~2026, 131종목, 5종 실행 전부 exit 0)
> n_eligible(4선) median 55, hong_gate median 7/date. PSR 0.43/PCR 5.29 정상.

### variant K (문병로와 직접 비교)
| 룰 | 거래 | PnL | Sharpe | 승률 |
|---|---|---|---|---|
| **value4_low**(4선) ⭐ | 213 | **+12.87%** | **0.11** | 42.7% |
| small_value4(소형주20%) | 129 | +12.53% | 0.06 | 41.1% |
| hong_combo(게이트) | 88 | +8.93% | 0.05 | 39.8% |
| value4_low Q(분기) | 469 | +10.18% | 0.09 | 48.0% |

## 핵심 발견 (문병로 5팩터와 A/B)
1. **4선 ≈ 5팩터** — value4_low(+12.87%/Sh0.11) ≈ 문병로 value_composite_kr(+13.68%/0.09). 밸류 팩터 4개나 5개나 한국 다년에서 동급.
2. **성장/마진 게이트가 알파를 못 더한다(오히려 깎음)** — hong_combo(+8.93%) < 순수 4선(+12.87%). 홍용찬 책 핵심 주장(밸류+성장+퀄리티 게이트 결합) **부분 반박**. "단순>복잡" 패턴 재확인(Minervini/Elder/Lynch/문병로 이어 6번째).
3. **소형주 20% > 40%** — 홍 small_value4(+12.53%) > 문 small_value 40%(+6.99%). 강한 소형주 틸트가 유효.
4. 분기 리밸런싱(Q_q +4.19%) << 상시(Q +10.18%). K(장기)>Q(중기)>B(단기).
5. **Sharpe 0.01~0.11 붕괴 — 펀더멘털 5책째 동일 결론.** CANDIDATE 부적격. 기술적 추세추종(Elder0.68/Minervini0.64)만 다년 생존.

## 산출물
- reports/books_research/hongyongchan/report.md + results_*.parquet 20개. index.md Book12 섹션·진행표 갱신. leaderboard.parquet 기록.

## 미커밋 (사장님 승인 대기)
전략 패키지·run 스크립트·테스트·리포트·index — git 커밋 미실행.
