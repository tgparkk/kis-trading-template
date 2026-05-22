# 2026-05-22 D-1 Stocks-in-Play universe 구현 + 스모크 검증

## 한줄 요약

룩어헤드 제거 후 "변동성 상위 N" universe가 무엣지로 확인됨에 따라(changelog-2026-05-21 §7), universe를 D-1 기준 RVOL+모멘텀 하드 게이트(Stocks-in-Play 프록시)로 재설계·구현·검증. SIP universe는 dynamic 대비 소폭 우월하나(orb -0.54%/일 vs -0.67%/일) ORB는 여전히 손실 — RVOL+모멘텀만으론 흑자 전환 불가, spec §7의 "D-1만으론 부족" 시나리오 확인.

## 1. 설계

- 설계서: [spec-2026-05-22-sip-universe.md](spec-2026-05-22-sip-universe.md) (brainstorming 산출, 사장님 승인)
- A안 채택: 거래일 X의 universe = D-1 기준 하드 게이트 모두 통과 → RVOL 상위 N
  - RVOL ≥ 2.0× (D-1 거래량 / 직전 20거래일 평균)
  - |전일 등락| ≥ 3%
  - 거래대금 ≥ 100억, 주가 ≥ 3,000
  - top_n = 30
- 데이터 한정: D-1 이전만 (갭·촉매 미사용 — 데이터 부재). 촉매 프록시 = RVOL 급증.

## 2. 구현 (commit d1a6f0c)

- `utils/intraday_universe.py`:
  - `load_daily_aggregates()` — minute_candles 전기간 일별 집계(volume/amount/close), `_daily_agg.parquet` 캐시
  - `build_stocks_in_play_universe()` — 순수함수, `trade_date <= asof` 필터로 룩어헤드 구조적 차단
  - 기존 `build_universe_for_date`(변동성)는 대조군으로 보존
- `scripts/run_intraday_tournament.py`: `_make_stocks_in_play_provider` + `--universe sip` + CLI `--sip-rvol-min`/`--sip-return-min`/`--sip-top-n`
- TDD: 실패 테스트 먼저 → 단위테스트 35 passed (게이트/top_n/이력/룩어헤드 차단)
- executor 에이전트가 API 529로 최종 보고 누락 → 관리자가 코드·테스트·스모크 직접 검증

## 3. 스모크 검증 (orb, 2026-04-01~05-15, ~30거래일)

| universe | 평균 일수익률 | 승률 | 최선 시나리오 | 거래수 |
|---|---|---|---|---|
| dynamic (전일 변동성) | -0.67% | 32.6% | -0.42% | 295~466 |
| **sip (RVOL+모멘텀)** | **-0.54%** | 31.1% | **-0.19%** | 157~215 |

- SIP 스모크 4시나리오 상세: SL3/TP6 -0.19%·승33% / SL3/TP2 -0.46%·승36% / SL2/TP2 -0.71%·승33% / SL2/TP6 -0.79%·승21%. 합격 0/4.
- end-to-end 정상 작동 확인 (universe 빌드·수치 현실적·에러 0).

## 4. 결론

- **SIP universe 구현은 검증 완료** — 작동 정상, 룩어헤드 없음.
- SIP는 dynamic보다 우월(더 선별적 → 거래 절반, 손실 ~0.13%/일 축소)하나 **ORB를 흑자로 못 돌림**.
- spec §7 예고대로: RVOL+모멘텀만으론 엣지의 일부만 재현. 갭·촉매가 빠진 한계가 그대로 드러남.
- 분봉 SIP 1차 iteration 종료. 추가 진전은 갭(2차 iteration) 또는 촉매 데이터 확보 필요 — 별도 결재 의안.

## 5. 다음

사장님 지시에 따라 일봉 `multiverse/` 패키지로 전환 (5/3 이후 휴면, handoff-2026-05-03 기준 §4 결정 대기).

## 관련 문서
- [changelog-2026-05-21-trail-bug-orb-revival.md](changelog-2026-05-21-trail-bug-orb-revival.md) — 룩어헤드 발견·수정
- [spec-2026-05-22-sip-universe.md](spec-2026-05-22-sip-universe.md) — SIP 설계서
- [research-2026-05-20-daytrading-deep-dive.md](research-2026-05-20-daytrading-deep-dive.md) — Stocks-in-Play 근거
