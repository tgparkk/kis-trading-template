# 8전략 세 arm 관측 원장 (`ledger8`)

> **관측 원장이다 — 판정 근거로 쓰지 말 것.** 룰 변경·K 변경·자금한도 해제(본안 재검토 2026-10-17)의 «근거»로 인용하지 않는다.
> 일봉 근사 · gross(수수료·세금 없음) · B 는 자본 분모가 없는 세계다 — 전체 잔고 합계·기간 수익률 지표는 만들지 않는다(원 단위 손익 · 명목가중 %만). 봇 코드 0줄 · DB 쓰기 0 · 라이브 로그 읽기만.
> 설계 = `docs/superpowers/specs/2026-09-19-ledger8-three-arms-design.md` · 계획 = `docs/superpowers/plans/2026-09-19-ledger8-three-arms.md`.

## 1. 무엇을 비교하나

| arm | 뜻 |
|---|---|
| **A_actual** | 라이브가 실제로 한 일(`virtual_trading_records` 체결 · 진실값) |
| **A_sim** | A_actual 매수를 B 와 «같은» 진입·청산 시뮬에 통과시킨 것 — A vs B 는 이것과 B1 으로만 비교 |
| **B1** | 사장님 규칙 · 서로 다른 계좌 — 같은 종목을 또 사면 별도 로트, 로트마다 자기 매입가로 손절·익절 |
| **B2** | 사장님 규칙 · 한 계좌 — 또 사면 평단 합산, 합산 평단으로 손절·익절·trail · 보유기한은 첫 매수부터 |

사장님 규칙(2026-09-18): 자금한도(전략 자본 칸막이 · 잔고 거절 · K · 일일 체결 한도 · 종목당 상한) 전부 해제 · 후보를 통과한
종목은 전부 산다 · `qty = max(1, floor(1_000_000 / 주가))`. 적용안: D1 후보 = 라이브 E6 상위 10(11~20위는 `tier=ext` 별도) ·
D2 전략 간 동일종목 차단 해제(`other_holder_live` 표시) · D3 시장급락 게이트 유지(`crash_blocked` 별도) · D4 B2 보유기한은 첫 매수부터
(`hold_clock_reset_diff` = 시계 리셋이었다면 달라졌을 건).

## 2. 사용법 (워크트리에서만 — 라이브 트리 `D:/GIT/kis-trading-template` 에서 실행 금지)

```bash
cd <worktree>/RoboTrader_template
PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe
$PY -m backtest.concept_axes.ledger8.run --stage signal     # ② 신호 충실도만(B 계산 전에 본다)
$PY -m backtest.concept_axes.ledger8.run --stage exit       # ③ 청산·익절손절 충실도까지
$PY -m backtest.concept_axes.ledger8.run                    # 전부 — 기본 창 2026-09-10~09-18
$PY -m backtest.concept_axes.ledger8.run --reuse-fills backtest/concept_axes/ledger8/results/fills_b.csv   # 진입 동결 · 청산만 재추적
$PY -m pytest backtest/concept_axes/ledger8/tests -q -p no:cacheprovider
```

| 옵션 | 뜻 |
|---|---|
| `--start` `--end` | 거래일 범위(KOSPI 달력). 기본 2026-09-10 ~ 2026-09-18(7거래일) |
| `--stage` | `signal` · `exit` · `all`(기본) |
| `--exit-fid-since` | 청산 충실도 대상 실제 매수 시작일(기본 2026-08-26 — 1810cd2 전략 고유 sl/tp 제거 다음 기동) |
| `--reuse-fills` | B 진입 집합을 이 파일로 고정(신호 재평가 결과와 무관하게 같은 진입) — main·ext·`tier=lift_ub` 전부 복원하지만 `B1_nogate` 는 다시 만들지 않는다(원 설계 · `fills_b.csv` 에 nogate 행이 없다). 이 모드에서 원장은 얇다(lift_status 등 빠짐) — 청산 재추적 용도로만 쓸 것 |
| `--out` · `--log-dir` | 출력 폴더(기본 `results/`) · 라이브 로그 폴더(기본 env `LEDGER8_LOG_DIR` → `<ROOT>/logs` → 라이브 로그) |

- 매 실행은 창 전체를 다시 계산한다(청산이 최신 봉에 따라 바뀜). 같은 입력이면 CSV·`summary.md` 는 같은 바이트이고 실행 시각·git SHA 는 `run_meta.json` 에만 있다(실측: 같은 코드로 4회 재실행 — CSV·summary.md 바이트 동일, `run_meta.json` 의 `run_ts`·`git_sha` 만 다름).
- 첫 줄의 `key.ini 파일을 찾을 수 없습니다` 경고는 `config.settings` import 부수효과(워크트리엔 key.ini 없음) — 무해, KIS API 호출 0.
- 콘솔에 섞이는 `strategy.RSLeaderStrategy | WARNING | [신호없음] … 진입 제외 «안 함»(mode=shadow)` 줄은 라이브 `_check_buy` 가 찍는 WARNING 이다(부트스트랩은 INFO 이하만 끈다) — 라이브 로그 파일로는 가지 않는다(NullHandler) · 무해.
- K·max_daily_trades·regime_index·rs 모드가 바뀌면 `registry.py` 이력표에 (발효일, 값, 근거) 한 줄을 넣는다 — `tests/test_registry_gate_order.py` 가 최신값을 config 와 대조한다.

## 3. 무엇을 어떻게 재현하나 (라이브 코드 근거 · 브랜치 시작 커밋 14a9b7a — 라이브 코드 자체는 이후 무변경)

- **후보**: `screener_snapshots`(scan_date = D 직전 거래일) 순위순 − 로그 `후보 제외:` → 로그 `[E6] … 목표 N건` 만큼(core/candidate_selector.py:1104-1141).
- **신호**: 라이브 인스턴스(`StrategyLoader.load_strategy` + `on_init(None,None,None)`)의 `_check_buy` 를 그대로 부른다. on_tick 가드(데이터 길이 · 불가능봉)는
  base.py:660-707 그대로, 보유·일일체결·K 게이트는 건너뛴다. 패치 = `MarketHours.is_market_open`(True) · rs_leader 모드(날짜별) · envelope `now_kst`(D 09:02)+캐시 비움.
  상태 무변경 검사(rs_leader `_ontick_skip_log` 예외). 사용 신호는 **로그 우선** — `[on_tick] 매수신호: CODE(`(매수 루프 전용 줄)가 있으면 Y,
  on_tick 이 돌았고 «평가 가능»(`fidelity8.slot_verdict` v3 — 체결 원장 시간선 + 빈자리 구간 안 on_tick 완료 + `[캡]` 줄 없음)했는데 없으면 N, 그 밖은 재현.
  신호 일치는 Y·N 방향을 나눠 본다(검증 실행: N 방향 표본은 elder 11 뿐). 재현 행은 day·min 룰 여유와 «빈티지 취약»(관측 재기록 폭 안에서 뒤집힐 수 있음)을 표시한다.
- **진입(B·A_sim)**: D 09:02 한 번 — D 시가가 밴드 안이면 시가, 밖이고 장중 복귀면 경계값, 장중 내내 밖이면 불가(`cap_skip_ledger/sim.py`).
  그 시각 급락 게이트가 막고 있으면 **D3′ 게이트가 «열린» 구간 안에서만 산다**(재차단 구간 제외 — 라이브와 같게) — 로그 시장방향성 시간선의 열린 구간 안 첫 밴드 안 분봉(`minute_candles`) 가격.
  분봉이 아예 없는 행은 «안 산 것」이 아니라 **«모른다»**(§6.5 A3) — 다만 그 행에서 라이브가 실제로 산 것이 확인되면(§6.9 `live_fill`) 그 체결로 진입한다.
  **D5** — 진입억제·25분 매수 쿨다운·VI·일일손실한도는 B 미적용(«후보 통과 종목은 전부 산다»), 라이브였다면 막혔을 로트만 `d5_flags` 로 표시(VI 관측 불가 · 쿨다운은 대부분 관측 불가 — §6.7).
- **청산(8전략 공통 1벌)**: 익절·손절 비율 = 라이브 엔진 `execute_virtual_buy` 경로(config `take_profit_pct/stop_loss_pct` → 손절 하한 3%)를
  캡처 스텁으로 호출해 얻는다. 데이터 청산 = 전략 사본에 포지션(평단·첫 매수 시각)을 넣고 `now_kst` 를 D+k 09:02 로 바꿔
  `generate_signal(code, D+k 일봉 창, 'daily')` → `_check_sell`. 하루 순서 = 보유기간(position_monitor `days_held=k`) → 갭 익절 →
  데이터 청산 → 갭 손절(라이브는 09:05 이후 — 플래그) → 장중 고저 터치(동시면 손절 우선).
- **arm A 멈춘 단계**: fill · cash(수량부족·잔고) · gate(타전략 보유 · 시장급락 · 일일손실한도 · 밴드·매수스톱 · 진입억제 · 기타) · unexplained · cap · held · signal.
  근거 = 로그 계기 줄(`[on_tick] 매수신호` 뒤 실행 경로 줄을 그 (전략, 종목)에 귀속 — 봇은 전략을 하나씩 돈다) → 체결 원장 시간선 → 재구성.

## 4. 출력 (`results/`)

| 파일 | 내용 |
|---|---|
| `summary.md` | 사람용 요약 — 신뢰도 · 충실도 · ① A vs B1 · ② B1 vs B2 · ③ 평단 뒤집힘 · ④ 중복 신호 · 부록(시나리오·D3′/A3·D2·D5·수량 근거) · A 멈춘 단계 · 가정·한계 |
| `ledger8.csv` | 1행 = (날짜, 전략, 종목, tier) — 후보·«평가 가능»(v3·v2·v1)·신호(재현/로그/사용)·룰 여유·빈티지·밴드·A 단계·B 진입(`gate_open`·`lift_window`·`lift_reblocked`·`lift_unknown`·`ub_status`/`ub_price` 포함)·D1~D5 플래그(해제 뒤 진입 포함)·로트/계좌 id |
| `funnel.csv` | (날짜, 전략, 종목, 단계, 결과) + n/first_ts/last_ts/basis — 접힌 단계 행 |
| `fills_b.csv` | B 진입 집합(동결용) — `tier` ∈ `main`\|`ext`\|`lift_ub`(A3 상한 전용) |
| `lots_b1.csv` | B1 로트. `arm` ∈ `B1`(본 집계 · main tier 만) \| `B1_nogate`(게이트 없었다면) \| `B1_ext`(D1 11~20위) \| `B1_ub`(A3 상한 실행 — **main 로트를 다시 포함**하므로 B1 과 더하지 않는다). 열 = `is_repeat_while_open · open_lot_seq · days_since_open_lot · exit_phase · lift_time · d5_flags` |
| `accounts_b2.csv` | B2 계좌(본 집계). 열 = `n_adds · fill_tiers · avg_price_path · final_avg_price · hold_clock_reset_diff · avg_flip` |
| `accounts_b2_ub.csv` | B2 A3 상한 계좌(id 접두 `B2U-`) — `FLAG_ADD_UNKNOWN`(추가매수 불명)이 나오는 유일한 파일 |
| `a_actual.csv` · `a_sim.csv` · `a_sim_entry.csv` | 실제 체결 · 같은 시뮬 로트 · 시뮬 진입가 vs 실제 체결가 |
| `fidelity_signal.csv` · `fidelity_exit.csv` · `offlist_signals.csv` | 신호(v1·v2·v3 결과 · 재구성 모순 · 룰 여유)·청산·익절손절 충실도 · E6 목록 밖 매수신호 |
| `run_meta.json` | `banner` · 실행 시각(`run_ts`) · git SHA(`git_sha`) · DB · 로그 폴더 · 창 · 최신 봉 · 관측 빈티지(`vintage`) · B1 재신호 vs B2 추가매수(`repeat_vs_adds`) · 경고(`warnings`) |

CSV 는 어느 파일도 머리에 배너 문장을 두지 않는다(기계 판독용 — 첫 줄에 문장을 넣으면 파서가 깨진다). 배너는 `summary.md` 3번째 줄과
`run_meta.json` 의 `banner` 필드, 그리고 이 README 에 있다.

## 5. 충실도 기준 (🔒 결과를 보고 바꾸지 않는다)

- 신호: 전략별(rs_leader 는 모드별) · 방향별(Y = 로그 Y 중 재현 Y · N = 로그 N 중 재현 N) 일치율 ≥ 90% · 방향 분모 < 5 면 그 방향 «판정 불가»(수치가 아니라 `N 0/3 판정 불가` 처럼 표본 수를 보여 인쇄) · 두 방향 다 모자라면 «판정 불가». 판정 가능 행이 전부 실제 체결(bought)이면 보고서가 «자명한 Y/Y» 라고 적는다(표에서 생성).
- «평가 가능» 규칙: v3 고정(`fidelity8.slot_verdict`) · v1(09:02 한 시점)·v2(classify_candidate) 결과를 늘 함께 싣는다 — 변경 이력은 계획서 「계획 검증 실행」.
- 청산: 전략별 실제 청산된 건의 사유 일치율 ≥ 70% · 분모 < 5 면 «판정 불가».
- 익절·손절: 엔진 경로 값 = 체결 원장 BUY 의 `target_profit_rate/stop_loss_rate`.
- 미달 전략은 `summary.md` 에서 `[신호 충실도 낮음]` · `[청산 충실도 낮음]` 을 달고 나온다. 현재 창(7일)에서는 어느 전략도 미달이 아니다(v1 규칙에서만 daytrading 이 LOW — §1-2 채택은 v3).

## 6. 계획 대비 달라진 점 (2026-09-19 구현 중 결정)

이 README 의 초안(§1-5, 옛 계획서 코드 블록)은 구현 전에 쓰였다. 실제 코드는 critic 2차 검수의 「구현 중 반영」 5항목(A1~A5,
`.superpowers/sdd/2026-09-19-ledger8-three-arms/amendments.md`)과 리뷰에서 나온 몇 가지 수정을 계획서 위에 더 넣었다. 계획서 파일
자체는 고치지 않았다(critic ruling) — 차이는 여기와 각 과제 보고서에 있다.

1. **A2 — «평가 가능»(v3) 시작 경계.** `[on_tick] 매수검토` 요약 줄은 on_tick 이 **끝날 때** 찍힌다(base.py:763-766). 빈자리가 그
   on_tick 도중에 열렸다면(매도 루프가 자리를 비움) 매수 루프는 빈자리가 열리기 **전**에 돌았는데도 요약 줄은 구간 안에 들어가 버린다.
   고친 규칙: 같은 전략의 **직전** 요약 시각이 구간 시작 **이후**일 때만 「구간 안에서 on_tick 이 돌았다」로 인정한다(on_tick 전체가
   구간 안에서 돈 경우만). 하루 첫 요약 줄의 prev 하한은 **09:00:00**(장 시작 — `main.py:433` 이 `is_market_open` 전엔 루프를
   건너뛰고 on_tick 은 순차라 09:00 전 시작이 불가능하다).
2. **lift 시각 정규화.** `minute_candles` 는 `HHMMSS`(DB), 로그 시장방향성 줄은 `HH:MM:SS` 를 쓴다. 두 형식이 섞이면 게이트 해제 전
   체결·오판 미체결이 조용히 생길 수 있어, `exitsim8.lift_entry` 가 두 형식을 정규화해서 비교한다(형식 불명은 `ValueError`).
3. **D3′ 진입 = 게이트 «열린» 구간 안에서만(재차단 반영).** 초안은 «첫 해제 시각 이후 첫 밴드 안 분봉」만 봤는데, 09-14 는 13:11 에
   다시 막히고 09-11 은 하루 22회 전환한다 — 라이브라면 재차단 구간에선 안 샀을 것이다. `logscan8.DayLog.open_windows`(모든 열린
   구간)와 `exitsim8.lift_entry(..., windows=...)`(구간 안 첫 바만 진입 후보)로 고쳤다. 재차단 구간에서만 밴드 안이었던 행은
   `lift_reblocked=Y`(다음 열린 구간에서 체결 또는 끝까지 미체결)로 표시한다. 전체 창 영향 = main `after_lift` 27→26, ext 26→24(정확히
   3+3행 이동: 09-11 ma5 079650 09:47→10:00 · 09-11 minervini/rs_leader 098120 09:35→09:36 · 09-14 ma20 443670·ma5 446540·elder
   005830 은 unfillable 로 전환). 진입 뒤 청산 판정에 쓰는 터치 분봉은 재차단 여부와 무관하게 전부 쓴다(청산은 게이트 대상이 아니다).
4. **A3 — 분봉 없는 급락 해제 행 = 「모른다」, 「안 산 것」이 아니다.** `minute_candles` 는 하루 ~300종목만 있어(선정 종목 위주 —
   무작위 결측이 아니다), 막힌 main 86행 중 44행은 애초에 분봉이 없다. 이 행들은 `lift_unknown=Y` 로 본 집계(하한)에서 빼고,
   D 일봉 상한 민감도를 나란히 싣는다: `tier=lift_ub`(`fills_b.csv`) 로 별도 실행해 `lots_b1.csv arm=B1_ub`(main 재포함 · 더하지
   말 것)와 `accounts_b2_ub.csv`(id `B2U-`)에 담는다. 상한 가격 규칙 — D 일봉 [저가, 고가]가 밴드와 겹치면 체결, 가격은 D 종가가
   밴드 안이면 종가, 아니면 가까운 밴드 경계값, 진입일 터치(`touch_bar`)는 쓰지 않음(`FLAG_NO_D_TOUCH`); 겹치지 않으면 상한도
   미체결. 상한 체결 날 같은 (전략, 종목) B2 계좌가 이미 열려 있으면 `FLAG_ADD_UNKNOWN`(추가매수 불명 — 상한 파일에만 존재).
   현재 창: main 44 unknown 중 상한 filled 28 · unfillable 8, B1 상한−하한 = **−114,324원**(28개 `lift_ub` 로트 몫), B2
   `FLAG_ADD_UNKNOWN` **10**.
5. **`live_fill` — 「아는 것은 안다」.** A3 의 44 unknown 행 중 **8행**은 실제로 라이브가 그 종목을 게이트 해제 뒤에 샀다(분봉이
   없을 뿐 매수 자체는 사실 · A_actual 로 확인). 이 8행은 «모른다» 로 두지 않고 그 라이브 체결 시각·가격(`basis=live_fill`)으로
   본 집계(main)에 넣는다 — 진입 뒤 분봉이 없어 진입일 고저(`touch_bar`)는 못 보므로 `FLAG_NO_D_TOUCH`. 상한 쪽에는 넣지 않는다
   (이미 아는 값이라 상한 민감도 대상이 아니다). 이 보정 뒤 **라이브 실제 매수 76건 전부가 B1 본 집계에 있다**(`live_fill` 8건
   포함, 이전엔 68건만 — 8건이 A3 unknown 으로 빠져 있었다). `ledger8.csv` 의 `lift_status` 는 그대로 `no_minute_data` 를 유지하되
   (사실이 그렇다), 실제로 어떻게 처리됐는지는 `b_entry_basis=live_fill` 과 `caveats`(`분봉 없음 — 라이브 실제 체결(HH:MM:SS
   @ price)로 진입(live_fill · 모른다·상한에서 뺐다)`)로 알 수 있다.
6. **A1 — D5 플래그(진입억제·25분 쿨다운).**
   - **진입억제(`throttle`)**: 초안은 그날 그 종목에 `[진입억제]` 줄이 있으면 전부 «막힘»으로 셌는데, 그중 26건은 A 멈춘 단계가
     `fill`(라이브가 실제로 샀다)이었다 — 그건 «막힘」이 아니라 «지연」이다. 리포트(§6-3)는 세 갈래로 나눠 보인다: 최종 차단(A
     멈춘 단계 = 진입억제, **28**건) / 지연 뒤 라이브가 실제로 삼(A=fill, **22**건 — `throttle_delay`) / 진입억제를 지나 다른
     단계에서 멈춤(**30**건 — 현금 19·밴드 7·타전략 보유 4). 같은 사실의 표시 문제라 별도 사장님 결정 없이 controller ruling 으로
     처리했다.
   - **25분 매수 쿨다운(`buy_cooldown`)**: critic 초안의 전제(«쿨다운은 전략을 가리지 않는다»)가 라이브 코드와 어긋났다.
     확인한 사실 — 쿨다운은 `(종목, 소유 전략)` 슬롯 객체 단위다(`core/models.py:195-196,284-296` · `core/trading/
     stock_state_manager.py:60-66,95-106` · `core/trading_context.py:88-109,376` · `bot/trading_analyzer.py:127-136,305`).
     다른 전략의 매수는 자기 객체의 시계만 돌리므로, 코드-전용 폴백(≥2 슬롯, `[모호조회]` WARNING 이 유일한 흔적)을 거치지 않는 한
     이 전략의 객체엔 닿지 않는다. 창 안에서 초안 규칙이 잡은 6건은 **전부 그 후보 자신의 라이브 매수**(진짜 교차-전략 사례가
     아님)였다 — 그래서 **`D5_COOLDOWN`(`"buy_cooldown"`) 상수는 삭제**하고 `D5_COOLDOWN_UNKNOWN`(«관측 불가»)만 남았다. 이번
     창의 교차-전략 쿨다운은 **0건**(관측 가능한 사례가 없다). §6-3 «25분 매수 쿨다운」행은 항상 0건 · «관측 불가» 라벨로만 나온다.
7. **A4/A5 — 보고서 표기.**
   - A4: B2 에서 D3′ 해제 뒤 추가매수가 있는 날은 기존 평단으로 하루 전체를 먼저 판정하고 추가매수 뒤에는 터치를 보지 않는다(B1 은
     같은 날 진입 이후 분봉을 전부 본다) — 이 비대칭이 B1 vs B2 차이에 섞일 수 있어, `FLAG_LIFT_ADD` 계좌(창 6건)의 몫을 §3 에
     별도 열(해제 뒤 추가매수 계좌 · 그 계좌 몫 차 · 나머지 차)로 분리했다.
   - A5: §0 에 v1/v2/v3 로 LOW 판정이 갈리는 그룹을 표에서 생성한 문장으로 적는다(예: v1 규칙에서는 daytrading 이 LOW). §1-2 의 N
     방향 표본이 `FID_MIN_N`(5) 미만이면 `N 0/3 판정 불가` 처럼 표본 수를 보여 «판정 불가»로 찍는다(예전엔 `N 0.00% · ok` 로
     찍혀 오해를 줬다).
8. **CSV 는 배너 줄이 없다.** 전역 제약의 「모든 산출물 머리에 배너」 취지는 지켰지만, 배너는 `summary.md` 머리·`run_meta.json`·
   이 README 에만 있다 — CSV 는 기계 판독용이라 첫 줄에 문장을 넣으면 파서가 깨진다(controller ruling).
9. **결과 커밋은 2개(과제 9·10 각각 코드→결과).** 코드 커밋과 결과 커밋을 분리해서, `run_meta.json` 의 `git_sha` 가 그 결과를
   만든 정확한 코드 커밋을 가리키게 했다(한 커밋으로 묶으면 dirty 코드 상태에서 결과가 나온 것처럼 SHA 가 부모 커밋을 가리킨다).

## 7. 가정·한계

`summary.md` §8 과 같다(`report.LIMITS`). 핵심: B 진입은 D 09:02 한 번(D5 규칙 미적용 · 막혔을 건 표시 · VI 관측 불가) · 급락일은
게이트 «열린」 구간 안 첫 밴드 안 분봉 진입(재차단 구간 제외 · 분봉 없는 행은 «모른다» — 하한은 제외·상한은 일봉으로 별도 · 라이브가
실제로 샀으면 `live_fill`) · 청산은 일봉 근사(시뮬 손절이 실제보다 많을 수 있음) · 신호 N 방향 오류율은 elder 외 잴 수 없음 ·
재현 신호는 «지금 DB» 빈티지(재기록은 09-14 연장 전에도 있었음 · day 는 Y 쪽 · min 은 N 쪽으로 기움) · daytrading `auto` 는 «지금»
시장 매핑 · 관측 기간이 짧아 대부분 미청산 → `--reuse-fills` 로 재추적 · gross · 생존편향·adj_factor 계열 결함 그대로.

## 8. 파일

| 파일 | 역할 |
|---|---|
| `registry.py` | 8전략 명세(게이트 순서·K·max_daily_trades·regime_index 이력·rs 모드·상태 검사) |
| `sizing.py` | arm A 수량 상한 · arm B 수량 |
| `logscan8.py` | 라이브 로그 1회 순회 · 게이트 귀속 · 시장방향성 시간선(`open_windows` 포함) · `[모호조회]` 파싱(`DayLog.ambiguous`) |
| `livesignal8.py` | 라이브 `_check_buy` 재현 · 강제 밴드 |
| `sellprobe8.py` | 엔진 경로 익절·손절 비율 · 매도 탐침 |
| `exitsim8.py` | 봉 단위 청산 순서 엔진(순수) · D3′ `lift_entry`(게이트 열린 구간·상한·`live_fill` 지원) |
| `stages.py` | arm A 멈춘 단계(순수) |
| `arms.py` | A_actual · A_sim · B1 · B2 엔진(순수) |
| `fidelity8.py` | 충실도 판정·집계 · «평가 가능» 규칙 `slot_verdict`(v3 시작 경계 포함) · 빈티지 표시(순수) |
| `sources8.py` · `context8.py` | DB SELECT · 실행 문맥 |
| `run.py` · `report.py` | CLI · 요약 MD(`report.py` 는 브리프의 ~340줄에서 시나리오 분리·D5 세 갈래·A3/A4/A5 표시를 더해 524줄) |
| 재사용(수정 금지) | `../minervini/cap_skip_ledger/{bootstrap,sources,sim,tradecal,classify}.py` |
