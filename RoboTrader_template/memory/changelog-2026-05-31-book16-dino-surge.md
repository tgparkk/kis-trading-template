# Book 16 — 디노(백새봄) 『돈이 된다! 급등주 투자법』 완주 (2026-05-31)

> 책조사 16권째. 멀티버스 조사 세션과 **격리 운용**(신규 파일만 생성, DB SELECT만, git 커밋은 사장님 승인 대기 — 멀티버스 WIP 휩쓸림 방지).

## 개요
- **책**: 디노(백새봄), 진서원(2022-04-20). 네이버 월재연(월급쟁이 재테크 연구) 카페 베스트셀러.
- **전략**: 낚싯대 매매법 = 급등 후 눌린 우량주를 디노테스트로 선별 → 10~20종목 분산 → **+10% 무조건 익절**. 시그니처 *"수익률보다 회전율"*.
- **성격**: Book 14/15(분봉 스캘핑 전멸)과 달리 **일봉 추세추종+눌림 매수** → 검증 가치 있는 후보로 판단해 코드화 진행.
- **book_id**: `dino_surge`.

## 워크플로우 (재사용 자산)
1. **교보 이북 실물 판독**: 화면 자동캡처 PowerShell(`CopyFromScreen`) → 2페이지 펼침 영역(x150-1550, y150-1330) 117 스프레드 캡처. 페이지넘김 = **다음화살표 클릭(1610,752)**(이 뷰어는 마우스휠 무효), MD5 3중복 끝감지, 되감기 180클릭으로 표지부터 보장. **PS5.1 BOM 이슈로 한글 리터럴 깨짐 → 유니코드 코드포인트(`[char]0xAE09`)로 우회.**
2. **분담 판독**: 직원 6인이 spread 범위 나눠 동시 Read 판독 → `raw_notes/notes_*.md` 6개(원문 기준, 추정 금지). 1인 실패 재투입.
3. **종합**: `strategy_catalog.md`(코드화 사양 4축 점수·청산·필터).
4. **코드화**(executor opus): `strategies/books/dino_surge/`(rules.py 2 variant + strategy.py) + `scripts/run_dino_surge.py`(self-contained 일봉 러너) + `tests/books/test_dino_surge_daily.py`(27 통과, 회귀 188 통과).
5. **백테스트**(executor opus): 다년 2021~2026 + 국면 분해(`scripts/regime_split_dino_surge.py` 신규) → `report.md`.

## 전략 사양 (판독 원문)
- **디노 테스트 4축**(~16점): ①재무(매출+10%·영익률≥10%·흑자·유보율≥1000%·부채↓) ②가격(고점대비 −20~−40% 눌림 가점/저점대비 과열 감점) ③기술(OBV 우상향+RSI·투자심리 ≤30~40 침체반등) ④재료
- **하드필터**: 이자보상배율<1 제외(좀비), 관리종목 제외
- **청산**: +10% 무조건 익절 / 손절 −5~7% 또는 MA5 이탈 / 하락장 +5%로 하향 / 환율1200·네마녀의날 매도
- **포지션**: 10~20종목 분산, 현금 10%, 무레버리지, 월1회 스캔

## 백테스트 결과 (전체기간 top_volume:50, 2021-01-04~2026-05-29)
| variant | rule | 거래 | PnL | Sharpe | Calmar | Hit |
|---|---|---|---|---|---|---|
| **B**(sl5/tp10/mh15) | **pullback_rebound** ⭐ | 55 | **+3.12%** | **0.078** | 0.87 | 27.8% |
| A_nofin(sl7/tp10/mh20/MA5트레일) | dino_test_pullback | 135 | +0.58% | 0.025 | 0.21 | 31.4% |
| A(재무게이트) | dino_test_pullback | 8 | +0.10% | −0.00 | — | 2.3% |

top100 강건성: variant B Sharpe 0.078→0.092 유지(소표본 우연 아님), variant A는 음전환.

## 핵심 결론
- **CANDIDATE 부적격** — Sharpe 0.078~0.092 = **펀더멘털 붕괴군**(문병로·홍용찬 ~0.1). 추세추종 생존군(Elder 0.68/Minervini 0.64)과 0.6 vs 0.08 격차. **16권째 "한국 일봉은 추세추종만 생존" 재확인.**
- **약세장 진입 방어는 Elder급(부분 발견)**: variant B **entry-BEAR +3.59%(n=39) > Elder +3.01%**. "고점대비 −20~−40% 눌림 + RSI 저점반등" 가격축 진입이 약세장 저가매수로 유효. 단 exit-BEAR +0.65%(자기완결 방어 아님), SIDEWAYS 약함. **재무게이트 끄면 더 좋음 = 디노 재무점수 무관, 가격눌림 일반 효과.**
- **책 시그니처 2개 모두 부분 반박**: ① 디노 재무테스트 알파 무첨가(컷오프 풀수록 표본만↑ Sharpe 0.01~0.03 정체) ② "+10% 무조건 익절" 회전 미작동(청산 31%만 +10% 도달, 손절이 상쇄; A의 MA5 trail은 90% 트레일청산으로 회전철학 자멸).
- **표본 부족**: 베스트도 55거래(연 1~17), 50종목 중 23종목만 거래 = 자본활용률 극저 → 헤드라인 Sharpe 저하 직접 원인.

## 데이터 한계/근사
이자보상배율(이자비용 컬럼 부재→debt≥200%+영업적자 좀비근사), 유보율(ROE>0 근사), 재료(생략), 봉차트 13패턴(바닥반전군만), 관리종목(top_volume 간접회피), 디노점수 컷오프 16=만점 모순(min_fin_score 1~3 스윕 보완).

## 산출물 (전부 신규 파일, git 커밋 사장님 승인 대기)
- `reports/books_research/dino_surge/`: raw_notes 6개 + strategy_catalog.md + report.md + regime_split.md + results_*.parquet 8개
- `strategies/books/dino_surge/`: rules.py, strategy.py, __init__.py
- `scripts/run_dino_surge.py`, `scripts/regime_split_dino_surge.py`
- `tests/books/test_dino_surge_daily.py` (27 통과, 회귀 188 통과)
- `reports/books_research/leaderboard.parquet` rows 229~237 append
- index.md Book16 행·결과섹션 추가
- 캡처 원본: `D:\tmp\book16_capture\pages\spread_*.png` (117장, 임시)

## 보호 파일 미수정 확인
멀티버스 세션 WIP(`tests/exit_multiverse/*`, `scripts/backfill_corp_events.py`, `strategies/books/elder_triple_screen/rules.py`)는 손대지 않음. git 커밋/푸시 없음.

## 살베이지 실험 (variant C: 디노진입 + Elder식 추세청산) — 2026-05-31, "건질 게 있나" 확정 실험
사장님 질문("정말 건질 게 없나")에 답하기 위해, 유일한 부품(눌림 진입의 약세장 방어 +3.59%)을 청산만 바꿔 살릴 수 있는지 검증.
- **결과: 살아남지 못함(더 나빠짐).** variant C(디노 눌림진입 + EMA13트레일/EMA65 trend_flip/초기손절8%/mh100, +10%고정익절 폐기): 헤드라인 Sharpe **−0.02**(B 0.078보다도 추락), **entry-BEAR +3.59%→+0.03% 소멸**, 보유 14.2일→**1.7일**.
- **실패 메커니즘(결정적)**: 디노 눌림 진입은 **역추세 저가매수**(진입 시 EMA65 거의 항상 하향·종가<EMA65) → 다음 봉에 trend_flip 즉시 발동(53/56=95%, 평균 +0.04%), 반등 전개 전 잘림. **추세청산은 추세진입 전제라 역추세 진입과 구조적 양립 불가.**
- **함의**: dino B의 +10%/시간기반(mh15) 청산이 오히려 bear-entry 엣지(+3.59%)를 이미 거뒀음. 헤드라인 Sharpe 저하의 진범은 청산이 아니라 **신호 희소성**(5년 55거래·50종목중 23만 거래 = 자본활용률 극저). 청산을 더 만져도 희소성 천장은 안 바뀜(추가 청산 튜닝 = 데이터마이닝).
- pytest 32 passed(기존27+C 5). 변경: `scripts/run_dino_surge.py`(variant C), `regime_split_dino_surge.py`, `test_dino_surge_daily.py`, `report.md §9`.

## 최종 — 건질 것의 정확한 범위
- **전략으로는 No**(부적격 불변). **부품으로는 딱 하나**: "고점대비 −20~−40% 눌림 + RSI 저점반등" = **약세장 진입타이밍 신호**(entry-BEAR +3.59% Elder급). 단 ①디노 고유 아님(눌림 일반효과) ②희소해서 단독 전략 불가 → **이미 다른 신호가 충분한 포트폴리오/복합의 약세장 진입 필터 component로만** 가치. 단독 候補 부적격.
- 디노 책 2대 시그니처(재무테스트·+10%회전)는 둘 다 무효. **책 고유 기여 ≈ 0**(15권째와 동일 운명, 회전형은 종가매매처럼 일봉 불성립).

## 후속
- 약세장 진입 필터 component는 candidate_backlog의 향후 복합/포트폴리오 작업 시 재활용 후보로 메모(전략 아님).
- 다음 깊이조사 = 터틀의 방식(사장님 점지) 또는 거인의 포트폴리오.
