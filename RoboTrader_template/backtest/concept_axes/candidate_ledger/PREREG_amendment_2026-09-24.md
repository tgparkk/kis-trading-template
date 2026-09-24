# PREREG 개정문 — 2026-09-24 (결과 개봉 «전» · 구현·파일럿 단계에서 드러난 사소 4건)

- 대상: `PREREG.md`(동결 커밋 `585b651`) · 개정 시점 = `run.py` 구현 + 2024-03 파일럿(13거래일 · `results/pilot/`) 뒤 · **본 실행 결과 개봉 전** · 파일럿 `summary.md` 의 수익·사유 분포는 관리자가 보지 않았다(행수·실행시간·V2~V4 불일치 0 만 확인).
- 성격: 열·룰·창·문턱을 바꾸지 않는다. 진단 열 1개 추가 · 진단 시간 열의 의미 명시 · 청산 창 길이의 라이브 정합 명시.

| # | PREREG 절 | 원문 | 개정 | 사유 |
|---|---|---|---|---|
| 1 | §7 `scan_diag.csv` | strategy, scan_date, universe_eff_date, n_universe, n_eligible, n_evaluated, n_impossible, n_no_bar_at_d, n_matched, secs | 끝에 **`n_errors`**(종목-일 단위로 격리한 예외 수) 추가 | 예외 격리 카운트를 넣을 자리가 동결 열에 없었다. 판정·V2 에 안 쓰는 진단 열 |
| 2 | §7 `scan_diag.secs` | (정의 없음) | ma20·daytrading 은 `scan_strategy` 를 월 단위로 한 번에 부르므로 **그 달 스캔 시간 ÷ 날짜 수(평균)** · minervini(2패스 · 날짜별 호출)는 날짜별 실측 | 재현기 `scan_strategy` 의 호출 단위가 월이라 날짜별 실측이 없다. 비용 보고용 |
| 3 | §6 `window_fn` | 「`px` 중 `date < day` 인 최근 N봉」(N 미정) | N = 라이브 `live_daily_window` 와 동일하게 **D 이전 120 달력일**(`config/constants.py:67 OHLCV_LOOKBACK_DAYS`) | 라이브 on_tick 의 일봉 창과 같은 길이 · 「당일 봉 포함 금지」는 그대로 |
| 4 | §7 flags 어휘 | `band_out`·`no_open`·`no_next_day`·`impossible_bar`·`vintage_m4`·`corp_event`·`minute_avail`·`survivor_universe` + exitsim8 원문 | **`sim_error`** 추가 — 시가가 있는 로트의 청산 시뮬(`simulate_lot`)이 예외로 실패한 행(청산 열 빈칸 · `scan_diag.n_errors` 에도 계수) | 진단 플래그 · 판정·열·룰 불변. 예외 행을 「미청산」과 구분하기 위함 |

- 불변 확인(파일럿 · 관리자 확인 범위): blob 해시 11파일 = `2274895` 일치 · tp/sl/max_hold·밴드·lookback = PREREG 표 일치 · V2·V3·V4 불일치 0 · 오류 0.
- 이 개정문은 `run.py` 와 같은 커밋으로 동결한다. 이후 개정은 새 파일(`PREREG_amendment_<날짜>.md`).
