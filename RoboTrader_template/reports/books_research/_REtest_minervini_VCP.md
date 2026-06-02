# Minervini VCP 핵심 재구현 — 재검증 (RETEST)

> 감사 지적: 채택룰(`volume_dryup`)은 책 시그니처 VCP 가 아니라 거래량 dry-up 보조신호
> 단독이었고, VCP 핵심(연속 변동성 수축 + 피벗 돌파 + RVOL)은 미구현/조잡 proxy 였다.
> 본 재검증은 책 §3 사양대로 **이산적 수축파동(contraction leg)** 을 직접 검출하는
> `rule_vcp_contraction_breakout` 을 신규 구현하고 백테스트한 결과다.
>
> 데이터: daily_prices(adj 수정주가) · universe top_volume:50 · 2021-01-01~2026-05-29
> 포트폴리오 모델: initial 1천만 / max_per_stock 300만 / K∈{5,10} / sl·tp·mh 그리드
> 신규 룰 기존 `rule_vcp_breakout`(전·후반 진폭 proxy)·`volume_dryup`(채택룰) 보존.

## 1. 신규 룰 `rule_vcp_contraction_breakout`

책 §3 VCP 사양을 직접 검증 (기존 proxy 와 달리 이산 수축 leg 검출):

- **연속 수축파동 검출**: base_lookback(기본 60거래일) 구간에서 swing high→다음 swing low 로
  이산 contraction leg 시퀀스 추출 (`_find_swing_pivots` + `_find_contraction_legs`).
- **단계적 낙폭 축소**: 각 leg 낙폭(%) ≤ 직전 leg × `contraction_shrink_ratio`.
- **contraction별 거래량 감소(dry-up 시퀀스)**: 각 leg 평균거래량 ≤ 직전 × `volume_shrink_ratio`.
- **피벗 돌파**: 종가 > 마지막 수축 leg 고점(피벗) × (1+`pivot_buffer`).
- **RVOL**: 돌파봉 거래량 ≥ base 평균 × `rvol_mult`.
- **수축 횟수**: `min_contractions`(2)~`max_contractions`(4).
- no-lookahead: `df.iloc[:t+1]` 만 사용 (테스트 9번 window-invariance 로 검증).

튜닝 가능 dataclass 필드: `base_lookback, swing_span, min_contractions, max_contractions,
contraction_shrink_ratio, volume_shrink_ratio, pivot_buffer, rvol_mult, max_last_depth`.

자체 테스트 `tests/strategies/books/test_minervini_vcp_breakout.py`: **10 passed**
(정상 VCP triggered, 수축 미축소·거래량 미감소·RVOL 미달·피벗 미돌파·데이터부족 시 False,
필드 존재, ALL_RULES 합류+기존 보존, no-lookahead, run_single 거래 발생).

## 2. 거래 빈도 — VCP 엄격도가 거래량을 결정 (★핵심 발견)

top_volume:50 전구간 raw 신호 수 (포트폴리오 K 미적용, 종목내 전봉 평가):

| contraction_shrink_ratio | volume_shrink 1.0 | volume_shrink 1.3 |
|---|---|---|
| **0.7** (진짜 엄격 VCP, 각 leg ≤70%) | **1** | **1** |
| 0.85 | 15 | 38 |
| 1.0 (비확대만 요구) | 45 | 97 |

→ **책 사양에 충실할수록(shrink≤0.7) 신호가 5년 50종목에서 1건으로 붕괴** — 과거
`rule_vcp_breakout` 2거래 붕괴가 그대로 재발. 대형주(top_volume:50)는 연속·단계축소
수축파동이 거의 형성되지 않음. shrink=0.85~1.0 으로 완화해야 통계 가능 표본(15~97).

## 3. 전구간 백테스트 (포트폴리오, K·sl·tp·mh 그리드)

### 3-1. 진짜 엄격 VCP (shrink=0.7) — n=1, 통계 무의미
full 144조합 그리드 top 은 전부 shrink=0.7 의 **단일거래(n=1)** Sharpe 0.78/PnL+7.9%
= 1승 행운 artifact. 채택 불가.

### 3-2. 표본 확보 구간 (shrink∈{0.85, 1.0}) — 64조합 best
| 순위 | 조합 | ntr | Sharpe | PnL | Calmar | Hit | MaxDD |
|---|---|---|---|---|---|---|---|
| best | shrink=1.0 vshrink=1.0 rvol=1.5 sl8/tp20/mh20 K5 | 22 | **0.107** | **−0.08%** | −0.00 | 36.4% | 32.0% |
| 3 | shrink=1.0 vshrink=1.0 rvol=1.3 sl8/tp20/mh20 K5 | 24 | 0.071 | −4.5% | −0.14 | 33.3% | 32.2% |
| baseline | shrink=0.85 vshrink=1.0 rvol=1.5 sl8/tp12/mh20 K5 | (9T) | −0.706 | −12.0% | −0.96 | 22.2% | — |

→ 표본 충분(22~24T) 구간에서 **best Sharpe 0.107·PnL≈0·MaxDD 32%** = 사실상 무알파/손실.
hit 27~36%(돌파 실패 잦음), MaxDD 32~41% 로 위험만 큼.

## 4. 국면별 (shrink=0.85, vshrink=1.3, rvol=1.3, sl8/tp20/mh35, K5)

| Regime | 기간 | ntr | Sharpe | PnL | Hit | MaxDD |
|---|---|---|---|---|---|---|
| BULL | 2025-06~2026-05 | 2 | −0.089 | −1.1% | 50% | 5.5% |
| SIDEWAYS | 2023~2024 | 7 | 0.061 | +0.4% | 42.9% | 8.95% |
| BEAR | 2022 | 5 | 0.614 | +7.1% | 60% | 6.0% |

→ 표본 전부 2~7거래(국면당 통계 부족). BEAR 만 양수(+7.1%)나 5거래라 참고 수준.
국면 분해도 거래 빈도 붕괴 문제를 재확인.

## 5. 기존 dryup 단독 대비 + vcp_breakout(구) 대비

| 룰 | ntr(전구간) | best Sharpe | best PnL | 비고 |
|---|---|---|---|---|
| **volume_dryup (채택룰, B)** | 153 | **1.41** | **+20.27%** | report.md 기준 |
| rule_vcp_breakout (구, proxy) | 5 | −0.054 | −24.98% | 전부 음수 |
| **rule_vcp_contraction_breakout (신, 책핵심)** | 1~24 | 0.107(표본확보) / 0.78(n=1) | ≈0% / 손실 | 무알파 |

→ **VCP 핵심을 책대로 구현해도 top_volume:50 에서 무알파(악화)**. 채택룰 volume_dryup
(Sharpe 1.41) 대비 압도적 열위. 구 proxy(전부 음수)보다는 표본 확보 시 소폭 개선이나
여전히 Sharpe 0.1대·PnL≈0.

## 6. 결론 (1줄)

**책 시그니처 VCP(연속 수축+피벗돌파+RVOL)를 §3 사양대로 구현했으나, 엄격히 적용하면
top_volume:50 에서 5년 1거래로 붕괴(과거 2거래 붕괴 재발)하고 완화해도 22~24거래에 best
Sharpe 0.107·PnL≈0·MaxDD 32% 무알파 — VCP 핵심은 대형주 일봉에서 작동하지 않으며 채택룰
volume_dryup(Sharpe 1.41/+20%)이 여전히 유일 알파.** (VCP 패턴은 중소형 급등주 풀이 더
적합할 가능성 — 후속 surge 유니버스 검증 여지.)
