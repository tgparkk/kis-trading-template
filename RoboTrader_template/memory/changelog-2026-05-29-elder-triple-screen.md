# Changelog 2026-05-29 — Elder Triple Screen (Book 7)

> 트레이딩 책 연구 시리즈 Book 7. depth-first 원칙(한 권 깊게 → 다음 책) 준수.
> 조사 → 설계 → 코드 → 백테스트 → 리포트/인덱스 6단계 완주(사장님 "끝까지 자동 진행" 승인).

## 결정 사항 (사장님 승인)
- Screen 1(장기 추세) = **일봉 65일 EMA proxy** (정통 26주 EMA는 224일 데이터에 비현실적, ~159일만 사용가능)
- 끝까지 자동 진행 (Phase별 결재 없음)

## 핵심 결과
- **최고 룰: triple_screen_ema_pullback (Variant A)** — 134거래, **PnL +23.76%, Sharpe 1.22, Calmar 2.64, hit 56.4%**
- **7권 통틀어 일봉 최고 PnL** (Minervini volume_dryup +20.27% 상회, Sharpe는 Minervini 1.41 > Elder 1.22)
- **역설적 발견**: 가장 단순한 셋업(EMA65 상승 + EMA13 터치 반등)이 정통 다지표 Triple Screen(Force Index +6%, Elder-Ray +8.7%, Sharpe 0.2~0.5)을 압도 — Minervini 단순 volume_dryup > trend_template와 동일 패턴

## 구현 (executor 직원, opus)
- 신규 4파일 (기존 파일 무수정):
  - `strategies/books/elder_triple_screen/{__init__.py, rules.py, strategy.py}`
  - `scripts/run_elder_triple_screen.py`
- 지표 헬퍼 8종: ema, macd_hist, force_index, bull_power, bear_power, stochastic, impulse_color, krx_tick (모두 `ewm(adjust=False)`)
- 룰 4종: triple_screen_force_index(72) / stochastic(68) / elder_ray(66) / ema_pullback(60)
- Screen 1 공통 proxy: `ema65.iloc[-1] > ema65.iloc[-6]` (5일 기울기)
- Screen 3 매수스톱(Approx A, 2일 trailing): 전일 고가+krx_tick 돌파 시 체결, no-lookahead
- Variant A: sl8/tp30/EMA13 trail+ema65 반전/mh100 · B: sl8/tp12/no trail/mh20
- **지수 불필요**(종목 자기완결) — Weinstein Mansfield RS 의존성 제거 → 구현 부담 최소

## 트러블슈팅
- **상대경로 저장 버그**: run 스크립트가 `reports/...` 상대경로 사용 → repo 루트에서 실행 시 `RoboTrader_template/` 누락된 위치에 저장됨. Minervini/Weinstein은 `RoboTrader_template/`에서 실행되는 관례. → 잘못 생성 파일 정리 후 올바른 cwd에서 재실행. 스크립트는 형제 책과 동일 패턴 유지(미수정).

## 데이터 관찰
- daily_prices 범위가 2021-01-04~2026-05-29(1,325일)로 확장됐으나, top_volume:50 종목 커버리지는 평균 ~142봉으로 얕고 불균등(13~100봉 다수) → 표본 희소 경고 강화

## 검증
- pytest tests/books/ : **47 passed** (회귀 없음)
- leaderboard.parquet: 104→114행 (Elder 10행 추가), 결과 parquet 8개

## 산출물
- 조사: `reports/books_research/elder_triple_screen/research.md`
- 설계: `docs/superpowers/specs/2026-05-29-elder-triple-screen-design.md`
- 리포트: `reports/books_research/elder_triple_screen/report.md`
- 인덱스: `reports/books_research/index.md` 갱신 (진행상태/Elder섹션/책별베스트/다음책)

## 한계
- 단일 BULL 구간 편향(평균 ~142봉 상승), 표본 희소, 적응판(일봉 proxy ≠ 원전 주봉), Screen 3 일봉 근사
- 다지표 confluence·all_AND 부진 → walk-forward·하락장 검증 후 CANDIDATE_ALPHAS 등록 검토

## 다음 책
- **Book 8** = `lynch_one_up` (Peter Lynch — 월가의 영웅). 펀더멘털 6카테고리 + PEG. 기존 운영 `strategies/lynch/`와 연구판 구분 필요.
