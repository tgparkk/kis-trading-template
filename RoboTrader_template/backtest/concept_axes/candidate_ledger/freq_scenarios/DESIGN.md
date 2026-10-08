# 설계 — 매수 빈도 시나리오 산수 (candidate_ledger/freq_scenarios)

> 🔴 관리자 고정 · 2026-09-26 · 아래는 관리자가 준 설계문을 그대로 옮겨 적은 것이다. **결과를 본 뒤 이 문서를 바꾸지 않는다.**
> 애매한 대목은 문자 그대로 해석하고, 해석은 `RESULTS_freq.md`의 「해석 기록」 절에 남긴다.
> 🔴 관측 · 산수(관찰) · 판정 없음. 라이브 룰 변경 근거 인용 금지.

## 목적

10-17 안건(라이브 자금·K·하루 횟수 제한 제거 재검토)과 실전 전환 준비용 **비용·필요 자금 산수**. 오늘 결과(청산 진단·무작위
대조군·짝 비교: 로트당 우위 측정 불가 · 비용 0.25%p 는 확실)를 전제로 «얼마나 자주 사면 비용이 얼마인가»를 본다.

## 입력

- `candidate_ledger/results/ledger.csv`(md5 `980e58492a7ac2ed11d25526f4488dbc` · 불일치면 중단)
- 3전략: `book_pullback_ma20` · `minervini_volume_dryup` · `daytrading_3methods_breakout`
- 창 2024-03-13~2026-09-23

## 후보 집합

- L0 = `band_ok=True` ∧ `entry_price` 있음(라이브 근사).
- `exit_reason=open` 로트는 **자리는 창 끝까지 차지**하되 손익 합에서는 빼고 건수만 인쇄.

## 시나리오

- 전략마다 8개: 하루 매수 상한 N ∈ {1, 3, 5, ∞} × 동시 보유 K ∈ {현행, ∞}.
- 현행 K = ma20 10 · minervini 6 · daytrading 10(각 `strategies/*/config.yaml` `max_positions` · 09-18 발효).
- 현행 근사 = (N=5, K=현행).
- 참고판 R = L0 전부(상한·중복 거부 없음 · 로트 독립 = 원장 B1).

## 하루 처리

- entry_date 오름차순 · 같은 entry_date 안에서는 scan_date 의 `rank` 오름차순 = 라이브 순위(거래량순).
- 후보마다:
  1. 같은 전략이 그 종목을 이미 보유 중이면 건너뜀(라이브 동일 전략 중복 거부 · R 제외 전 시나리오)
  2. 그날 매수 수 < N ∧ 보유 수 < K 이면 매수.
- 🔒 자리 반환 규약 = 로트는 `[entry_date, exit_date]` 동안 자리를 차지하고 **exit_date 다음 거래일부터** 비는 것으로
  본다(보수적 · 같은 날 청산 후 재매수 없음) — `exit_phase` 로 당일 반환을 따지지 않는다.

## 자본·필요 자금

- 자본은 따로 제한하지 않는다(로트 100만원 × K 가 전략 칸막이와 같다는 09-18 사이징 결정 전제).
- 대신 **필요 자금 = 최대 동시 보유 수 × 1,000,000원** 을 인쇄.

## 지표

전략 × 시나리오 · 전체와 연도별 2024/2025/2026:

- 매수 건수(청산 완료)
- open 건수
- 거래일당 매수 수(창 거래일 617 기준)
- gross 합(`pnl_won` 합)
- 비용 합(Σ `notional` × 0.25%, 원 정수)
- net 합
- 로트당 net(원)
- 승률(`ret_pct>0`)
- 최대 동시 보유
- 필요 자금
- 비용/|gross| 비

## 🔒 쓰임새 규칙

**로트당 gross 가 시나리오마다 다른 것은 검정하지 않았고 오늘 결과상 측정 불가 크기다 ⇒ 시나리오를 로트당 gross 로
고르지 않는다.** 이 산수의 용도는 «비용 총액·필요 자금»이 빈도에 따라 어떻게 커지는지다. p·라벨 없음.
라이브 근거 아님(~10-16 룰 변경 0).

## 대조 인쇄(판정 없음)

현행 근사(5, 현행) 의 2026-08-24~2026-09-23 entry_date 구간 거래일당 매수 수 vs 라이브 실측(같은 구간
`virtual_trading_records` BUY: ma20 1.7 · minervini 1.3 · daytrading 2.0/매수일 — 관리자 제공 값 · DB 재조회
금지) — 차이는 자본·현금·장중 타이밍·밴드 근사 때문일 수 있음을 한 줄로.

## 한계

원장 한계 승계(일봉 청산 근사 · 생존자 유니버스 · 빈티지 · 시가 밴드 근사) · 비용 0.25% 는 산술(세금·호가 미끄러짐
미반영) · 한 국면.

## 테스트(합성 데이터)

자리 반환 규약(exit_date 당일엔 아직 차 있음 · 다음 거래일 빔) · 하루 상한 N 이 rank 순으로 자름 · 중복 거부 ·
비용 산술 손계산 1건 · 필요 자금 = 최대 동시 보유 × 100만.

`pytest backtest/concept_axes/candidate_ledger/tests -q` 전체 통과 + `ruff check`.

## 상한

토큰 25만 · 실행 10분.

## 최종 보고(40줄 이내)

전략별 8시나리오 + R 핵심 표(매수 수 · 거래일당 · gross · 비용 · net · 로트당 net · 필요 자금) · 대조 인쇄 ·
DESIGN.md mtime < 결과 mtime 확인 · 테스트/ruff · 해석 기록 · 파일 목록.

## 새 파일 범위(고정)

- `backtest/concept_axes/candidate_ledger/freq_scenarios/{DESIGN.md, run_freq.py, RESULTS_freq.md, freq_table.csv, run_meta.json}`
- `backtest/concept_axes/candidate_ledger/tests/test_freq_scenarios.py`
- 다른 파일 수정 금지(같은 워크트리 `docs/` 에서 다른 직원 작업 중). DB 조회 0(입력은 CSV 하나).
