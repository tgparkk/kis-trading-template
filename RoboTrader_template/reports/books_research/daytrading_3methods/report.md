# Book 17 — 유지윤 『하루 만에 수익 내는 데이트레이딩 3대 타법』 리포트

> ※ 번호 정리(2026-05-31): 병렬 세션의 dino_surge(급등주 투자법)가 Book 16으로 확정되어, 본서는 **Book 17**로 재번호. 두 책은 같은 날 병렬 진행됨.

> 2026-05-31 · 캡처(HQ 314p)→OCR→전략분석→코드화(TDD)→백테스트→페이퍼 전략화 완주.
> book_id `daytrading_3methods` · 저자 유지윤 · 북오션 2021 · ISBN 978-89-6799-583-6.

## 1. 책 정체
한국 **세력주/급등주 분봉 데이트레이딩** 실전서. 이론보다 **실명 종목 사례 차트 해설**(12+종목) 중심. 골격은 일관되게 **일봉으로 종목 선정 → 분봉 거래량 폭증 봉에서 진입 → 당일 청산**, 제1원칙 "거래량 없으면 무의미".

3대 타법(목차·뒤표지 확정):
1. **바닥 타법**(Ch2, p.28~118) — 폭락·동전주의 세력 방어(연속 밑꼬리)·매집(갭상승 단봉) 후 반등 초입. 패턴 3×3(상승3+지지3), 2지지(상한가 후 2조정).
2. **지지 타법**(Ch3, p.119~201) — 급등 후 지지 캔들 ~10개(2주)·윗꼬리 2지지·거래량 점감 후 2차 시세. **TP +15/17/19%, SL −10%**.
3. **돌파 타법**(Ch4, p.202~311) — 전고점/매물대 거래량 동반 돌파(장대양봉 +22%·신고가). TP 10~20%·상한가.

## 2. 코드화 (일봉 환원, book_backtester 트랙)
`strategies/books/daytrading_3methods/rules.py` — 4룰(TDD 25 tests, 회귀 books 218 passed):

| 룰 | 타법 | 진입 요지 |
|---|---|---|
| `rule_support_10candle` | 지지 | +25% 급등 이력 → 10캔들 지지(고점 −10% 이내) + 거래량 점감 → 거래량 폭증 양봉 |
| `rule_floor_3x3` | 바닥 | 상승 3봉(+5%↑) + 지지 3봉(횡보) → 양봉 돌파 + 거래량 |
| `rule_floor_2support` | 바닥 | 강한 양봉(+20%) 후 2회 지지 유지 → 양봉 재개 |
| `rule_breakout_prev_high` | 돌파 | 20봉 전고점 거래량(2배) 동반 돌파 + 양봉 |

청산 variant: **A** sl10/tp15/mh20(지지 기본), **B** sl10/tp10/mh10(돌파 빠른 익절).
품질 게이트: no-lookahead(현재봉 제외 슬라이스, 코드리뷰 검증 CLEAN) · 왕복 비용 ~0.21% · 슬리피지 0.10% · adj_factor.

## 3. 백테스트 결과 (full-period 2021-01-04 ~ 2026-05-29, top_volume:50)

| 룰 | Variant | 거래 | PnL % | Sharpe | Hit |
|---|---|---|---|---|---|
| **breakout_prev_high** ⭐ | B | 706 | **+5.90** | **0.17** | 46.7% |
| support_10candle | B | 78 | +3.42 | 0.08 | 29.6% |
| support_10candle | A | 76 | +3.37 | -0.00 | 22.5% |
| floor_3x3 | B | 92 | +2.69 | -0.04 | 32.8% |
| breakout_prev_high | A | 637 | +1.81 | -0.02 | 38.7% |
| floor_3x3 | A | 90 | -0.21 | -0.12 | 27.5% |
| floor_2support | A/B | 3 | ~0 | -0.01 | (표본부족) |
| all_AND | A/B | 0 | — | — | — |

(book-local 원천: `results_variant{A,B}_single_*.parquet` 8파일.)

## 4. 핵심 발견 & 결론
- **베스트 = breakout_prev_high(돌파 타법) variant B**: 706거래 +5.90%·Sharpe 0.17·hit 46.7%. 표본 충분·양(+)이나 **Sharpe 0.17 = 약함**.
- **빠른 익절(variant B, tp10/mh10) > 느린(A, tp15/mh20)** — 전 룰 공통. 한국 단타 빠른 회전 유리(강창권·trading_legends와 동일 경향).
- **floor_2support 대형주풀 미발화(3T)**: 책의 상한가 후 2지지는 **마이크로캡 급등주 패턴**이라 top_volume:50(대형주)에선 거의 안 잡힘 → 유니버스 불일치.
- **all_AND 0거래**: 4룰 상호 배타(바닥/지지/돌파는 동시 성립 불가).
- **결론: CANDIDATE 부적격**(Sharpe < 0.2). 17권째 동일 패턴 — **기술적 추세추종(Elder 1.22·Minervini 1.41)만 생존**, 급등주 분봉 단타 계열은 일봉 환원해도 Sharpe 0.1대.
- **신규 알파 아님 확인**: breakout_prev_high ≈ 기존 trading_legends new_high_breakout, support_10candle ≈ ma_pullback 계열의 변형. 책의 "10캔들 지지+거래량 점감" 추가 필터가 단순 돌파 대비 **엣지를 주지 못함**(support B Sharpe 0.08 < breakout B 0.17).

## 5. 가상매매(페이퍼) 환경
- 베스트 룰 **breakout_prev_high(variant B)**를 라이브 페이퍼 전략 `strategies/daytrading_3methods_breakout/`로 코드화(진입은 백테스트 rules.py 직접 재사용 = 1:1 동등). sl10/tp10/mh10, holding_period=swing.
- `config/trading_config.json`에 5번째 전략으로 등록(enabled, 격리자금 1천만·max_capital_pct 0.20). 기존 검증 4전략(elder/minervini/ma20/ma5) **불변**.
- ⚠️ **탐색·관찰용**: Sharpe 0.17로 검증 4전략 대비 약함. 며칠 페이퍼 관찰 후 유지/제외 판단 권고(실자금 승격 부적격).

## 6. 후속/잔여
- 차기 검토: **마이크로캡/급등주 유니버스**(top_volume 대형주풀 대신 급등주 풀)에서 재백테스트 시 floor_2support·support_10candle 발화·성과 재평가.
- 코드리뷰 MEDIUM(테스트 격리 2건: floor_3x3 돌파 경계, floor_2support k==0 커버리지; floor_2support 연속지지 충실도) — 결론 불변, 테스트 하드닝 TODO.
- 격리 보류: `index.md`·`leaderboard.parquet`·`MEMORY.md` 갱신은 병렬 세션 종료 후. git 커밋은 사장님 승인.

상세 판독: `raw_notes/notes_*.md`(8파일) · 룰 증류: `strategy_catalog.md` · 서사: `reading_notes.md`.
