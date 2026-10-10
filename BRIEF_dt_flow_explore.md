# BRIEF — daytrading 후보 × 수급 5종 «탐색» 1회 (2026-10-10 · 관리자)

## 왜
사장님 질문: 「뉴스·퀀트(수급) 데이터로 무엇을 살지 실제로 좋아지나 — 기다리지 말고 과거 데이터로 먼저 볼 수 없나」.
🔒 사장님 10-10 결정: **«3개월 탐색 1회»** — 참고·우선순위용 · 매수 규칙 안 바꿈 · 09-24 「같은 원장 새 특징 탐색 금지」 **이 건 한정 면제** · 「모른다」가 나올 가능성 큼을 알고 승인.

## 실측 사실(관리자 10-10 SELECT · 다시 확인만)
- 수급 표가 전 종목을 덮는 건 **2026-07-03~** 뿐: `investor_trend_daily`·`program_trade_daily`·`short_sale_daily` 07-03~10-06 · `credit_balance_daily` 2026-07~ ≈2,640종목(그 전 2~36종목 → 쓰지 말 것).
- `foreign_flow` = 2026-03까지 ≈150종목 고정 목록 → **쓰지 말 것**. 외국인은 `investor_trend_daily.frgn_ntby_tr_pbmn`(전 종목 · 07-03~)으로.
- 후보 원장 = `RoboTrader_template/backtest/concept_axes/candidate_ledger/results/ledger.csv`(main 추적 · daytrading `daytrading_3methods_breakout` 2024-03-13~**2026-09-23**). band_ok daytrading: 07월 158 · 08월 436 · 09월 322.
- 공유 표 수집 시차: 5일 몰아 수집(STALE_DAYS) · 7월분은 08-15 소급 · 값은 «D 의 최종값». B 스펙(main `docs/superpowers/specs/2026-10-10-daytrading-filter-layer-design.md` §4-3 · 56줄)은 07:52 에 KIS 로 D 값을 직접 받으므로, 이 탐색은 «07:52 에 받는 D 값 ≈ 표의 D 최종값» 가정 → 결과 문서 첫머리에 가정으로 적을 것.

## 설계(이대로 · 바꿀 땐 보고서에 이유 한 줄)
- **표본**: ledger.csv 의 daytrading 행 · scan_date **2026-07-03 ~ 2026-09-23** · `band_ok=True` · **에피소드 첫 행**(정의는 `candidate_ledger/feature_study/run_features.py` 것 그대로 재사용 — 수정 금지 · 필요하면 함수 복사) · 후보 < 10 인 날 제외(B 규칙) · 그 특징 커버리지 < 80% 인 날은 그 특징에서 제외 · 결측 행은 그 특징에서 제외. 10월 이후는 청산이 아직 안 끝나 제외(원장 끝 09-23).
- **D** = scan_date(신호일 · 매수는 D+1).
- **특징(B §4-3 과 같은 정의·같은 방향 · 꼬리 20%)**:
  ① 기관 = `investor.orgn_ntby_tr_pbmn`×1e6 ÷ `program.acml_tr_pbmn` (D) · 하위 20%
  ② 프로그램 = `program.ntby_tr_pbmn` ÷ `program.acml_tr_pbmn` (D) · 하위 20%
  ③ 공매도 = `short.ssts_vol_rlim` (D) · 상위 20%
  ④ 신용잔고율 = `credit.loan_rmnd_rate` @ D−k 거래일 · **k=3 과 k=4 둘 다 인쇄**(고르지 말 것) · 상위 20%
  탐색 열(인쇄만): 외국인 = `investor.frgn_ntby_tr_pbmn`×1e6 ÷ `acml_tr_pbmn` 하위 20% · `credit.loan_gvrt` 상위 20%.
  🔴 단위 확인 먼저: investor 금액 = 백만원 · program/short = 원(B 스펙 56줄) — 실제 값 몇 행으로 비율이 −1~+1 범위인지 확인하고 보고.
- **결과 변수**: 주 = 원장 `ret_pct`(원장의 청산 흉내 · sl/tp/max_hold) · 보조 = D+1 시가→종가(`daily_prices` · 🔴 `adj_factor` 곱하지 말 것 · 원가격 그대로). 원장 ret_pct 가 B §3-4 매매 흉내와 다르다는 점 한 줄 명시.
- **통계(판정 아님 · 크기 그림)**:
  - Δ = 날짜 안에서 (꼬리 평균 − 나머지 평균) → 날짜별 n 가중 평균(날짜 고정효과 · «엣지 = 시장 베타» 대응).
  - 95% 구간 = 날짜 묶음 부트스트랩 2,000회.
  - 잡음 띠 = 가짜 특징 400개(날짜 안 무작위 순위) Δ 분포 → 관측 Δ 가 몇 백분위인지.
  - 월별(07·08·09) Δ 부호.
  - 특징마다 n(행·날) · 결측률 · 예상 MDE(≈2.8×SE).
- **라벨은 둘 중 하나만**: 「눈에 띔」(잡음 띠 바깥 2.5% ∧ 월 3개 부호 같음 ∧ 두 결과 변수 부호 같음) / 「모름」. 🔴 「있음」「효과 확인」「유의」 같은 말 금지(09-24: 도구 교정 전 「있음」 보고 금지 · 순열 p 3배 낙관 전례). p 값은 인쇄해도 되지만 «참고 · 낙관 쪽» 표시.

## 지켜야 할 것
- DB = **SELECT 만** · KIS 호출 0 · 봇 코드 0줄 · 뉴스 표(`news*`·`sector_news*`) 조회 금지(NW1 봉인) · `dtflow_shadow` 스키마 조회 금지.
- 동결 코드 수정 금지: `candidate_ledger/*`(run.py·feature_study·tool_calibration) · A `dt_dart_filter` · B `dt_flow_shadow` — 필요하면 **복사**.
- 라이브 트리(`D:/GIT/kis-trading-template`)에서 실행·테스트 금지. 작업은 이 워크트리 `D:/tmp/kis-wt-dt-flow-explore` 에서만.
- **git commit·push 금지**(사장님 확인 뒤 관리자가 함) — 파일만 만들어 둘 것.
- DB 접속: host 127.0.0.1 · port 5433 · db `kis_template` · user robotrader / pw 1234 (또는 레포의 resolver).
- 토큰 절약: 파일은 필요한 줄만 읽기(grep) · 보고는 짧게.

## 산출물
- `RoboTrader_template/backtest/concept_axes/dt_flow_explore/explore.py`(한 파일 · 실행 1줄 · 난수 시드 고정)
- `…/dt_flow_explore/RESULTS_2026-10-10.md`(≤120줄): 첫머리 = 가정·면제·«탐색 · 매수 규칙 안 바꿈 · B(동결 40e1355) 규칙·k 바꾸지 않음» · 표 1개(특징 × [n행·n날 · 결측률 · Δ 주 · 95%구간 · 잡음 백분위 · 월별 부호 · Δ 보조 · MDE · 라벨]) · 단위 확인 결과 · 한계.
- `…/dt_flow_explore/rows.csv`(표본 행 + 특징값 · 재계산용) · `run_meta.json`(시드·행수·쿼리 시각·git HEAD).
- 최소 시험: 날짜 안 꼬리 Δ 계산을 손으로 만든 작은 표 2개로 확인하는 테스트 1파일(`tests/` 아래 · 이 워크트리에서만 실행).
