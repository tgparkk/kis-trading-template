# 과거 재스캔 후보 원장 (`candidate_ledger`)

> **관측 원장이다 — 판정 근거로 쓰지 말 것.** 3전략(ma20·minervini·daytrading) 룰 변경 근거로 인용 금지(변경 0건 ~2026-10-16 · 계획서 v3).
> gross(수수료·세금 없음) · 생존자 유니버스(지금 `daily_prices` 에 남은 종목만) · 빈티지 보정 없음(D 봉 = 지금 DB 값, 라이브가 D+1 09:00 에 본 값과 다를 수 있다) · 장중 익절/손절 미재현(일봉 고저 근사) · 밴드 = D+1 **시가** 근사(라이브는 09:0x 실시간가). 봇 코드 0줄 변경 · DB **SELECT 만**.
> 사전등록 = [`PREREG.md`](PREREG.md)(동결 `585b651`) + [`PREREG_amendment_2026-09-24.md`](PREREG_amendment_2026-09-24.md).

## 1. 무엇인가

> 「제가 자금한도를 없애자고 한건 현재 로직으로 산 다음에 나중에 추가 데이터나 수치를 조절해서 매수후보 로직 품질을 높이고 싶은 겁니다」(사장님, 2026-09-24 · PREREG §0)

목적 = **룰이 고른 것 「전부」의 표본을 과거 재스캔으로 지금 만든다.**
라이브 스크리너 전수 저장(`df8e8fe`)은 2026-09-28 07:40 부터 발효되지만, 표본이 쌓이려면 수개월이 걸린다. 그래서 라이브 스크리너 어댑터를
**그대로** 재사용해 과거 창을 재스캔하고, 후보 로직 품질 연구(B ④ 특징 연구)에 쓸 입력 표본을 앞당겨 만든다.

## 2. 어떻게 만들었나

- 창 = **2024-03-13 ~ 2026-09-23**(617 거래일 · 시총 절벽 이후). 3전략 라이브 스크리너 어댑터를 코드 0줄 변경으로 그대로 호출하고,
  `max_candidates=None` 으로 절단 없이 통과 종목 **전부**를 원장에 남긴다.
- **배제 없음** — 우선주·외국·리츠·스팩·ETF 도 `excl_class` 열로 표시만 하고 걸러내지 않는다(라이브 유니버스 정의와 동일하게 맞추기 위함).
- 진입 = **D+1 시가**(기준가 `ref` = D 종가). 밴드는 라이브 `_entry_band` 그대로:

  | 전략 | 밴드 | down / up |
  |---|---|---|
  | ma20 | `[ref×0.92, ref×1.01]` | 0.08 / 0.01 |
  | minervini | `(−∞, ref×1.03]` | 없음 / 0.03 |
  | daytrading | `(−∞, ref×1.03]` | 없음 / 0.03 |

  🔑 **밴드 밖 행도 버리지 않는다** — `band_ok=False` 로 표시하고 청산 시뮬까지 돌려 「밴드가 없었다면」의 가상 로트 값을 남긴다.
  **라이브 근사 집계는 반드시 `band_ok=True` 로 거를 것.**
- 사이징 = **B1**(`ledger8/sizing.py` 재사용) — `qty = max(1, floor(1,000,000 / entry_price))`. 자본·K·일일 한도 없음, 로트 독립.
- 청산 = `ledger8/exitsim8.py` 일봉 시뮬(tp/sl 는 라이브 엔진 경로로 조회해 대조):

  | 전략 | tp | sl | max_hold | trail |
  |---|---|---|---|---|
  | ma20 | +10% | −8% | 50 | MA20(수익 중 종가<MA20 이면 청산) |
  | minervini | +12% | −8% | 20 | 없음 |
  | daytrading | +10% | −10% | 10 | 없음 |

  같은 봉에서 손절·익절 동시 도달 시 **손절 우선**.

## 3. 사용법

워크트리에서만 실행(라이브 트리 `D:/GIT/kis-trading-template` 에서 실행 금지).

```bash
cd <worktree>/RoboTrader_template
PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe
$PY -m backtest.concept_axes.candidate_ledger.run --pilot          # 1개월 파일럿(시간 추정)
$PY -m backtest.concept_axes.candidate_ledger.run --verify         # 본 실행 + summary 에 V1~V5
$PY -m backtest.concept_axes.candidate_ledger.run --verify-only    # 기존 결과로 V1~V5 만 재계산
```

| 옵션 | 뜻 |
|---|---|
| `--start` `--end` | 스캔 창(YYYY-MM-DD). 기본 `2024-03-13`~`2026-09-23`(PREREG §2 창 밖이면 오류) |
| `--strategies` | `ma20,minervini,daytrading`(짧은 이름) 또는 라이브 폴더명, 콤마 구분. 기본 3전략 전부 |
| `--pilot` | `--start 2024-03-13 --end 2024-03-31` 로 강제(§11 1개월 파일럿) |
| `--verify` | 스캔·시뮬 실행 뒤 `summary.md` 에 V1~V5 값 인쇄 |
| `--verify-only` | 스캔·시뮬 없이 기존 `results/` 로 V1~V5 만 재계산 |
| `--out` | 출력 폴더(기본 `results/`, `--pilot` 이면 `results/pilot/`) |

- 실행시간 실측(본 실행 · 617일 × 3전략): **1,168초**(로드 32s · 스캔 903s · 청산 228s).
- 실행 전 가드: `strategies/{3전략}/{screener,strategy,config.yaml}` + `strategies/base.py` + `strategies/_rule_screener_base.py` = **blob 11파일** 해시가 기준 커밋 `2274895` 와 다르면 중단. tp/sl/max_hold 는 라이브 엔진 경로(`resolve_live_tp_sl`)로 조회해 PREREG 표와 다르면 중단.
- 체크포인트: `results/parts/<strategy>_<YYYY-MM>.csv` + `.done`(git sha·DB 지문 기록) — 재시작 시 sha·지문이 같을 때만 이어 단다.

## 4. 출력

`results/` 아래:

- **`ledger.csv`** — 1행 = 1로트(스캔 통과 종목-일-전략). 정렬 = strategy, scan_date, rank.

  | 열 | 정의 |
  |---|---|
  | strategy, scan_date, stock_code, rank, score, n_passed, reason, n_bars | 스캔 식별·룰 통과 정보 |
  | ref_close, market_cap, trading_value, d_volume, rs_value, excl_class | 기준가·유니버스 필터값·RS(minervini) |
  | entry_date, entry_price, band_lo, band_hi, band_ok | D+1 진입 관측값(§2 밴드) |
  | qty, qty_basis, notional | B1 사이징(밴드 밖도 가상 로트) |
  | exit_date, exit_price, exit_reason, exit_phase, hold_days, ret_pct, pnl_won | exitsim8 청산 결과(gross) |
  | flags | `;` 구분 어휘(아래) |

  flags 어휘: `band_out`·`no_open`·`no_next_day`·`impossible_bar`·`vintage_m4`·`corp_event`·`minute_avail`·`survivor_universe`(상수) + exitsim8 원문(`gap_tp_open`·`sl_tp_same_bar(손절 우선)`·`bar_missing:<d>`·`max_hold_deferred(...)`·`mark_to_market` 등) + **`sim_error`**(개정 #4 · 청산 시뮬 예외 실패).
- **`scan_diag.csv`** — 날짜별 진단(행 없는 날도 1행): `strategy, scan_date, universe_eff_date, n_universe, n_eligible, n_evaluated, n_impossible, n_no_bar_at_d, n_matched, secs, n_errors`(`n_errors` = 개정 #1 추가 열).
- **`summary.md`** — 전략별 행수·진입율·exit_reason 분포·V1~V5 값.
- **`run_meta.json`** — git sha · 창 · params_hash · tp/sl/max_hold · DB 지문.

## 5. 본 실행 결과(2026-09-24 · 관측값 · verifier 1패스 APPROVE-WITH-NOTES · §5-1)

행 1개 = `results/summary.md` 그대로. 순위 구간별 수익 비교표·평균 수익률·적중률은 **여기 싣지 않는다**(PREREG §9 —
특징 연구 사전등록 `docs/prereg_2026-09-24_candidate_feature_study.md` 가 검정할 몫).

| 전략 | 행 | band_ok 비율 | no_next_day | n_passed 최소/중앙/최대 |
|---|---|---|---|---|
| book_pullback_ma20 | 24,937 | 0.736 | 24 | 2/36/126 |
| minervini_volume_dryup | 9,367 | 0.916 | 12 | 0/14/60 |
| daytrading_3methods_breakout | 18,236 | 0.831 | 36 | 1/26/117 |

exit_reason(시가 있는 로트 전부 · band_out 가상 로트 포함): ma20 = sl 13,455 · tp 9,543 · trail_ma 1,457 · open 407 · max_hold 51.
minervini = sl 5,299 · tp 3,595 · max_hold 395 · open 66. daytrading = sl 6,983 · tp 6,881 · max_hold 4,207 · open 129.

V1(스냅샷 일치율 · 재스캔 rank≤10 ∩ 라이브 rank_in_snapshot≤10, 현행 params_hash 구간 대표값): ma20 **0.982**(73일) ·
minervini **0.963**(21일, 08-25 TT on 이후) · daytrading **0.972**(62일, `high_window`=15 이후). V2~V4 불일치 **0**.

### 5-1. verifier 판정(2026-09-24 · opus · 독립 시뮬레이터로 재계산 · 원장 값 오류 0)

- V5 층화 5행 손계산 전부 일치(109610 +3,300 · 018880 −79,940 · 015360 −98,992 · 211050 +29,400 · 320000 +99,180) · 행수·달력·no_next_day 72 전부 일치 · flags 어휘 밖 토큰 0 · band_ok 전 행 재계산 불일치 0 · 손절 25,737행(갭 손절 2,186 · 손절가보다 높게 판 경우 0) · 익절 20,019행(gap_tp 1,811) · summary 표 전부 독립 재집계 일치.
- **주의 1 — max_hold 202행이 한 거래일 일찍 청산됨**(ma20 9 · minervini 67 · daytrading 126): 보유 구간에 KOSPI 달력에 없는 날(2024-12-31 · 2025-12-31 = 연말 휴장 · 2026-07-17 = 봇 로그 `현재 시장 상태: holiday`)이 끼었고, 라이브 `count_trading_days_between` 이 쓰는 정적 휴장 목록(`utils/korean_holidays.py`)에 이 날들이 없어 거래일로 센다. 라이브 코드를 그대로 재현한 결과이나 라이브 런타임은 KIS API 로 휴장일을 동기화하므로 실제 라이브와 하루 어긋날 수 있다. 원장은 고치지 않는다(관측 · 사전등록 동결) · 백로그 = 정적 휴장 목록 보강.
- **주의 2 — trail_ma 1,457행 중 205행은 진입일(k=0) 청산**(`k0_data_exit(가격=진입가 근사)` · 수익 0) — exitsim8 설계대로(D 종가가 이미 MA20 아래).
- **주의 3 — 출처**: 본 실행(15:37~15:57)은 `a51c631` 코드로 돌았고 `run_meta.git_sha` 는 그 시점 HEAD `e11fc75`(B 사전등록 커밋 · run.py 동일). 리뷰 반영(체크포인트 가드 · V1 해시별 집계 · `sim_error` · `--verify-only`)은 실행 «뒤» 수정이며 원장 값에 영향 0(sim_error 0) · `summary.md` §10 만 `--verify-only` 로 재계산됨.
- 미확인: minervini TT off 재현(V1 앞 구간 ≈0 은 간접 근거).

## 6. V1 해석 주의

- minervini 06-05~08-24 구간의 낮은 일치율(≈0)은 **재현이 틀린 게 아니라 룰이 바뀐 것** — TT 게이트 on(`86ff02d`, 2026-08-25) 이전
  스냅샷과 TT on 재스캔을 비교하기 때문이다. `summary.md` 는 params_hash 구간별로 따로 인쇄하고 현행 구간만 대표값으로 쓴다.
- daytrading 도 마찬가지: `high_window` 20→15 변경 경계가 2026-06-22/23.
- 스냅샷 없는 날 3일(2026-06-18 · 07-07 · 07-08)은 모든 전략 V1 계산에서 제외.

## 7. 다음

- 이 원장을 입력으로 **B ④ 특징 연구**(사전등록 동결 `e11fc75`)가 rank·score·n_passed 등을 검정한다 — 검정은 여기서 하지 않는다.
- 라이브 스크리너 전수 저장(`df8e8fe`, 2026-09-28 07:40 발효)이 쌓이면 이 원장(빈티지 미보정·생존자 유니버스)과 대조한다.
- 한계(PREREG §8): 빈티지 미보정 · 생존자 유니버스 · 장중 미재현 · 밴드=시가 근사 · gross · 자원 제약 없음(라이브 체결 집합과 다름) ·
  `corp_event` 플래그는 2026-07 이전 거의 안 걸림(수집 변경) · `band_ok=True` 도 on_tick 재평가 미재현이라 「체결 근사」일 뿐.

## 8. 문서 사슬

PREREG `585b651` → 개정문 [`PREREG_amendment_2026-09-24.md`](PREREG_amendment_2026-09-24.md) → 구현 `a51c631` →
특징 연구 사전등록(동결) `e11fc75`.
