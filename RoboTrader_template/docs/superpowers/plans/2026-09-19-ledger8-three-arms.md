# ledger8 세 arm 원장 (A 라이브 · B1 로트 독립 · B2 평단 합산) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-09-10~09-18(7거래일) 8전략의 라이브 E6 후보를 «자금한도 없는 세계» 두 벌(B1 로트 독립 · B2 평단 합산)과 라이브(A_actual · A_sim)로 나란히 재현하고, 라이브가 각 (날짜, 전략, 종목)을 어느 단계에서 멈췄는지 로그 증거로 분류하는 읽기 전용 관측 원장을 만든다.

**Architecture:** 매수 신호는 라이브 전략 인스턴스의 `_check_buy` 를 그대로 부르고(`livesignal8`) 라이브 로그 `[on_tick] 매수신호` 와 먼저 대조한다(신호 충실도 게이트 → B 계산 전). 청산은 8전략 공통 1벌이다 — 익절·손절 비율은 엔진 `execute_virtual_buy` 를 캡처 스텁으로 호출해 얻고(`sellprobe8`), 데이터 청산은 전략 사본에 포지션을 주입해 `generate_signal(…, 'daily')` → `_check_sell` 을 D+k 시각으로 부른다. 봉 단위 순서 엔진(`exitsim8`)과 로트 엔진(`arms`)은 순수 함수라 DB 없이 테스트한다.

**Tech Stack:** Python 3.9.13(라이브 venv) · pandas · psycopg2(SELECT 전용, `PGOPTIONS=default_transaction_read_only=on`) · pytest(DB 없는 단위 테스트) · 재사용 `backtest/concept_axes/minervini/cap_skip_ledger/{bootstrap,sources,sim,tradecal,classify}.py`(수정 금지).

**Spec:** `RoboTrader_template/docs/superpowers/specs/2026-09-19-ledger8-three-arms-design.md` — §0 확정 규칙 · 초안 검증표 20항 · 설계 3-1~3-8 · §4 구현 순서·위험 · 「결정 — 세부 적용안」(D1~D4 · 창 · 스키마 · 규약). 이 계획은 그 문서를 근거로 논증한다. 실행자는 둘 다 읽는다.

## Global Constraints

- 작업 트리 = 워크트리 `D:/tmp/kis-wt-ledger8`(브랜치 `research/ledger-8strategies`). 🔴 라이브 트리 `D:/GIT/kis-trading-template` 에서 테스트·실행 금지(읽기·로그 읽기만).
- 파이썬 = `D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe`(3.9.13 — `X | Y` 타입·`match` 금지, 모든 모듈 첫 줄 `from __future__ import annotations`), cwd = `D:/tmp/kis-wt-ledger8/RoboTrader_template`. 아래에서 `$PY` 는 이 경로다.
- 테스트: `$PY -m pytest backtest/concept_axes/ledger8/tests -q -p no:cacheprovider` (DB·로그 파일 없이 돈다).
- 라이브 코드 0줄 — `core/`·`strategies/`·`bot/`·`api/`·`db/`·`config/` 수정 금지. `backtest/concept_axes/minervini/cap_skip_ledger/` 수정 금지(minervini 원장이 쓰고 있음).
- DB 쓰기 0 · DB명 하드코딩 금지 — `cap_skip_ledger.bootstrap` 을 먼저 import 한다(resolver → `TIMESCALE_DB`, `PGOPTIONS=-c default_transaction_read_only=on`). DB `kis_template` @127.0.0.1:5433 user robotrader(SELECT 만).
- 라이브 로그(읽기 전용) `D:/GIT/kis-trading-template/RoboTrader_template/logs/robotrader_template_YYYYMMDD_*.log`(콘솔 캡처 · `trading_*.log` 의 상위집합).
- 창 = **2026-09-10 ~ 2026-09-18 = 7거래일**(로그 파일 7개). 청산 추적은 DB 최신 일봉까지(실행 시점 기준 · 실현/미청산 분리).
- 사장님 규칙(스펙 §0): 자금한도 해제(전략 자본 1,000만원 칸막이 · 잔고부족 거절 · K · 하루 매매횟수 · 종목당 상한 전부 제거) · 후보 통과 종목은 전부 산다 · `qty = max(1, floor(1_000_000 / 주가))` · B1 서로 다른 계좌(로트 독립) · B2 한 계좌(평단 합산) · A = 라이브 그대로 · 진입·청산 룰(`_check_buy`/`_check_sell`)은 세 arm 모두 그대로.
- 적용안(스펙 「결정」 절): D1 B 후보 = 라이브 E6 상위 10(본) · 스냅샷 11~20위는 `tier=ext` 별도 칸 / D2 전략 간 동일종목 차단 해제 · `other_holder_live` 플래그 / D3 시장급락 게이트 유지 / D4 B2 보유기한은 첫 매수부터 · 손절·익절·trail 은 합산 평단 · `hold_clock_reset_diff` 플래그.
- 추가 결정(스펙 「추가 결정」 표 · 2026-09-19): **D3′ 급락 게이트 = «풀린 뒤 산다»** — 09:02 에 막혀 있으면 그 시각엔 안 사고, 게이트가 풀린 뒤 첫 분봉 가격이 매수 밴드 안이면 그 가격에 산다(`minute_candles` · 키 `trade_date` · SELECT 만) · 끝까지 밴드 밖이면 미체결 · 해제 시각은 로그 시장방향성 시간선(실측 09-11 09:23:09 · 09-14 11:02:06) · «하루 종일 막았으면» 결과를 민감도로 함께 · 진입일 청산은 진입 시각 이후 고저만 / **D5 속도 조절 규칙 = «빼되 표시»** — 진입억제(60초·사이클 3건)·25분 매수 쿨다운·VI·일일손실한도는 B 미적용(사장님 규칙 «후보 통과 종목은 전부 산다»), 라이브였다면 막혔을 건은 규칙별 플래그로 건수·성과 별도 집계 / 브랜치 커밋 허용(push·main 머지는 별도 승인).
- 기록 스키마: 행은 `(날짜, 전략, 종목, 단계, 결과)` + `n_evals/first_ts/last_ts` 로 접는다 · 단계 = 후보/신호/캡/현금/체결(+기타 게이트) · B1 플래그 `is_repeat_while_open · open_lot_seq · days_since_open_lot` / B2 `n_adds · avg_price_path · final_avg_price`.
- 🔴 총자산·누적수익률·자본 대비 % 산출 금지(B 는 자본 분모 없음) — 건별 %, 원 단위 정수 금액, 명목 가중 수익률(Σ손익÷Σ명목)만. 보고용 금액은 원 단위 정수 · % 는 소수 2자리.
- 모든 산출물 머리에 「관측 원장이다 — 판정 근거로 쓰지 말 것」. 파일 쓰기는 임시파일 → `os.replace`(멱등 · 같은 입력이면 같은 바이트, 실행 시각·SHA 는 `run_meta.json` 에만).
- 커밋: 이 브랜치에만 · push·머지 금지 · 메시지 `type(ledger8): 한국어 요약` + 빈 줄 + `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` · 메시지는 히어독(`git commit -F - <<'MSG'`) · `git add` 는 경로 명시(와일드카드·`-A` 금지).
- 🔒 충실도 기준값(`SIG_AGREE_MIN=0.90` · `EXIT_REASON_MIN=0.70` · `FID_MIN_N=5`)은 결과를 보고 바꾸지 않는다. 미달은 숨기지 않고 표에 `LOW` 로 적는다. 신호 일치는 Y·N 방향을 나눠 판정한다. «평가 가능» 규칙은 v3 로 고정하고 v1·v2 결과를 민감도로 늘 함께 싣는다(변경 이력은 「계획 검증 실행」 절).

---

## 설계 판단 (스펙 대비 — 근거와 함께)

1. **arm A = `A_actual` + `A_sim` + «멈춘 단계» 분류 — 권고안 그대로 채택.** 라이브 자금 게이트 시간선(잔고 G2 · 복리 per_stock · 쿨다운)을 재현하지 않는다. 대신 (날짜, 전략, 종목)마다 `stages.classify_a` 가 로그 계기 줄 → 체결 원장 시간선 → 재구성 순서로 증거를 찾아 `fill / cash / gate(other_holder·market_gate·daily_loss·band·throttle·other) / unexplained / cap / held / signal` 중 하나로 적고, 증거 종류를 `basis` 칸(`log`·`timeline`·`vtr`·`recon`·`replay`)에 남긴다. A vs B 비교는 `A_sim` 대 `B1`(같은 진입·청산 시뮬)로만 한다(minervini 원장 가상 진입가 편향 +1.14% — 스펙 §4-5).
2. **신호는 «로그 우선»이다.** 라이브가 그날 그 종목을 `_check_buy` 까지 평가했다고 볼 수 있으면(`[on_tick] 매수신호` 줄이 있거나, on_tick 이 돌았고 «평가 가능»했는데 줄이 없으면) 로그 판정(Y/N)을 쓰고, 아니면 재현(`_check_buy` 지금 DB)을 쓴다(`signal_basis = log|replay`). 근거: 로그 판정은 그 시점 DB 로 계산된 값이라 빈티지(D-1 거래량이 라이브 스캔 뒤 재기록 — 09-14 거래시간 연장 «전»에도 있었다: 09-10 115440 +0.4% · 09-11 006880 +0.5% · 연장 뒤 폭 확대, 최대 +24.3% 051160 09-18)를 타지 않는다. 대안(재현만 사용)은 day·min 의 빈티지 뒤집힘을 그대로 B 에 싣는다 — 기각.
   - **한계(critic 교차검수 🔴1)**: 판정 가능 행은 거의 전부 «로그 Y» 라 검증되는 것은 Y 방향뿐이다. 「라이브 N 인데 재현 Y」(N 방향) 표본은 elder 11 외 0 이고, B1 로트의 절반이 재현 신호다(검증 실행 159/312 = 51% — day 71% · min 81% · ma20 69% · «B1 중 A 캡»·«B1 중 A 이미 보유» 묶음은 100% 재현). 그래서 신호 표는 방향별(Y·N)로 나누고, 보고서는 전략별·A 단계별 재현 비중과 거래량 룰(day·min) 재현 행의 룰 여유·«빈티지 취약» 표시를 싣는다(관측 빈티지 폭은 데이터에서 잰다 · 방향: 재기록은 거래량 증가 ⇒ day 재현은 Y 쪽, min 재현은 N 쪽으로 기움). 재현 행을 보정하지는 않는다.
   - **«평가 가능» 규칙(= 로그로 N 을 말할 수 있다)은 `fidelity8.slot_verdict` 한 곳의 순수 함수**다. v3(채택) = `cap_skip_ledger/classify.py::classify_candidate`(:176-205 — 09:00 보유면 held, 장 전체 빈자리 없음 «또는 모든 빈자리가 목록상 앞 순위 매수로 닫힘»이면 no_slot) + «빈자리 구간 안에서 그 전략 on_tick 이 한 번이라도 끝났으면(`[on_tick] 매수검토` 시각) no_slot 이 아니다» + 그날 `[캡]` 줄 없음. 근거는 코드다 — on_tick 은 한 번 돌 때 목록 전부를 평가한다(strategies/base.py:660-734). 변경 이력(v1 → v2 → v3)과 각 규칙의 수치는 「계획 검증 실행」 절에 숨기지 않고 적고, 보고서 §1-2 에 세 규칙을 나란히 싣는다.
3. **매도 탐침은 `_check_sell` 직접 호출이 아니라 `generate_signal(code, data, timeframe='daily')` 를 부른다.** 라이브 매도 루프(strategies/base.py:739-749)가 그렇게 부르고, 보유 종목이면 8전략 모두 `min_len`(P1·P2)·`timeframe`(P1) 게이트를 지난 뒤 보유 분기에서 `_check_sell` 로 간다(P3 는 보유 분기가 첫 줄). 직접 호출하면 `min_len` 가드(예: elder 70봉)를 건너뛰어 라이브에 없는 청산을 만든다. 스펙 3-2 의 「`_check_sell(...)` 그대로 호출」보다 한 단계 바깥이며 결과는 같은 코드 경로다.
4. **익절·손절 비율은 하드코딩하지 않고 라이브 엔진 경로로 얻는다.** `TradingDecisionEngine.execute_virtual_buy`(core/trading_decision_engine.py:499-714)를 `virtual_trading` 자리에 인자만 받아 적는 스텁을 끼워 호출한다. 라이브 호출부(bot/trading_analyzer.py:275-281)는 `target_profit_rate/stop_loss_rate` 를 넘기지 않으므로 3순위(전략 config `take_profit_pct/stop_loss_pct`, :589-607) → 손절 하한 3%(:655-658)가 그대로 돈다. 2026-09-19 드라이런(DB 없음) 결과: elder 0.30/0.08 · envelope 0.10/0.08 · day 0.10/0.10 · min 0.12/0.08 · ma20 0.10/0.08 · ma5 0.15/0.03 · rs 0.15/0.08 · deep 0.12/0.07 — 스펙 3-2 표와 일치. 체결 원장 `virtual_trading_records.target_profit_rate/stop_loss_rate` 와 건별 대조한다(과제 6).
5. **하루 청산 순서(일봉 근사)** = `position_monitor` 보유기간(`days_held=k ≥ strategy.max_holding_days`, position_monitor.py:251-285) → 갭 익절(시가, :314-323) → 데이터 청산(시가, on_tick 매도 루프) → 갭 손절(시가 · 라이브는 09:05 이후 가격 → 플래그, :219-224·:326) → 장중 고저 터치(동시면 손절 우선 · `sim.simulate_exit` 봉 1개 호출로 재사용). 보유기간은 `position_monitor` 규칙으로 판정한다 — 전략 `_check_sell` 의 `count_trading_days_between(entry, now)-1` 은 진입 시각보다 이른 시각에 평가하면 하루 늦게 세지만(시각 의존) `position_monitor` 가 07:40 복원 `days_held=k`(bot/state_restorer.py:388-392)로 09:00 에 먼저 판다.
6. **진입일(k=0)에도 데이터 청산 탐침을 한 번 돌린다.** 라이브는 매수 직후 같은 날 on_tick 매도 루프가 D-1 확정봉으로 `_check_sell` 을 부른다. 체결되면 가격 = 진입가 근사 + `k0_data_exit` 플래그.
7. **B 진입은 D 09:02 한 번**(`sim.simulate_entry` — D 시가 · 밴드 복귀 · 불가). 진입억제(쿨다운 60초 · 사이클 15초당 3건, config/constants.py:410-418 · core/trading_context.py:484-515)·25분 매수 쿨다운(bot/trading_analyzer.py:132-136 · core/models.py:196)·VI(trading_context.py:424-426)·일일손실한도(:428-436)는 B 에 적용하지 않는다 — 근거는 사장님 규칙 «매수 후보를 통과한 종목은 자본과 무관하게 전부 산다»(스펙 §0-2 · 「추가 결정」 D5)다. 이 규칙들이 «시각만 늦춘다»고 보지 않는다 — A 가 멈춘 단계가 진입억제인 후보가 ma5 18 · rs 17 · elder 1 이다. 그래서 **라이브였다면 막혔을 B 로트를 규칙별로 표시**한다(`Fill.d5`: `throttle` = 그날 그 (전략, 종목)에 `[진입억제]` 줄 · `buy_cooldown` = 같은 전략이 같은 종목을 진입 25분 안에 샀다(체결 원장 재구성) · `daily_loss` = `매수 차단: 일일 손실 한도 초과` 줄 · VI 는 DEBUG 로그라 관측 불가). 상한가 +25% 는 플래그만(스펙 3-3).
8. **금액 값(종목당 상한·deep_mr `paper_investment_per_stock`·복리 per_stock)은 registry 에 복제하지 않는다.** 라이브 인스턴스(`strategy._max_per_stock_amount`)·config·로그(`종목당 투자금액 재산정`)에서 실행 때 읽는다 — 검증표 #12~#14 의 「registry 에 추가」를 대체(복제본이 어긋날 위험 제거). registry 에는 이력이 필요한 값(K · max_daily_trades · regime_index · rs 모드)만 둔다.
9. **매 실행은 창 전체 재계산**(날짜별 병합 없음 — 청산이 최신 봉에 따라 바뀌므로). 스펙 §4 「진입 집합 동결 후 청산만 재추적」은 `fills_b.csv` + `--reuse-fills` 로 제공한다.
10. **시장급락 = D3′ «풀린 뒤 산다».** 발동일은 09-14 만이 아니라 09-11 도다(로그 `매수 판단 스킵: 시장급락` 09-11 196줄 · 09-14 713줄, 둘 다 `종목=` 칸 없음 — 3필드 줄은 09-16 발효). 09:02 판정은 로그 `[시장방향성필터] 관측 지수=… 판정=` 시간선(전략별 `regime_index` 이력 · daytrading `auto` 는 `resolve_regime_index(count=False)`)으로 하고, 막혀 있으면 같은 시간선의 해제 시각(막힌 지수가 모두 `허용` 이 된 첫 시각) 뒤 분봉(`PriceRepository.get_minute_prices` — db/repositories/price.py:188-229)을 `exitsim8.lift_entry` 가 차례로 `sim.simulate_entry` 에 넣어 첫 체결을 찾는다(해제 시각이 든 분봉은 해제 전 가격이 섞여 제외). 진입일 청산은 진입 «이후» 분봉만 모은 봉(`Pos.touch_bar`)으로 판정한다. 민감도 두 줄: «하루 종일 막았으면»(해제 뒤 체결 제외) · «게이트가 없었다면»(09:02 체결 · `B1_nogate`). ⚠️ `minute_candles` 는 그날 선정 종목 위주 ~300종목/일이라 차단 행의 약 절반은 분봉이 없다(`no_minute_data` → 본 집계에서 «안 산 것» · 건수 공개). 코드 없는 게이트 줄은 직전 `[on_tick] 매수신호: CODE(` 에 귀속한다 — 봇은 전략을 하나씩 `await` 한다(main.py:465-493). 귀속 검증: 로그 `가상매수:` 줄의 귀속 결과를 체결 원장 BUY 와 날짜·전략별로 대조한다(과제 4).
11. **청산 충실도 창은 2026-08-26 부터**(1810cd2 「전략 고유 sl/tp 제거」 2026-08-25 21:19 커밋 → 다음 기동 발효). 그 전 매도에는 D-1 종가 sl/tp 가 섞여 있다. 실제 매수 ≤09:05 는 진입일 고저를 쓰고(`D_open` 취급), 그 뒤 매수는 진입일 고저를 쓰지 않는다(`actual`).
12. **상태 무변경 검사** 대상 = `positions · daily_trades · _cap_skip_logged · _cap_skip_log_date · config · _ontick_skip_log`, 예외 = rs_leader 의 `_ontick_skip_log`(`_check_buy` 안 `_should_log_ontick`, rs_leader/strategy.py:182·189). envelope 의 `_entry_df_cache`·`_quant` 는 캐시라 대상 밖(명시).
13. **B1 vs B2 합계의 성질** — 미청산 로트끼리는 같은 마지막 종가로 평가되므로 Σ(종가−매입가)×수량 = (종가−평단)×총수량 으로 합이 같아진다. B1·B2 차이는 «청산이 갈린» 계좌에서만 생긴다(보고서 §3 문구에 적는다).
14. **같은 날 시간선은 B1·B2 가 같다**(critic 🟡1) — 청산에 `phase`(09:00 시가 단계 = 보유기간·갭 익절 · 09:02 뒤 = 데이터 청산·손절·터치)를 달고, B1 «열린 로트 위 재신호»는 09:00 시가 단계에서 청산된 로트를 열림으로 세지 않는다(B2 는 그 시각에 계좌를 닫고 09:02 체결로 새 계좌를 연다). D3′ 해제 뒤 진입이면 그날 청산은 전부 진입 «전»이다. 남는 B1 재신호 ≠ B2 추가매수 차이는 로트별 손절과 평단 손절이 갈린 경우뿐이다(검증 실행 rs_leader 23 vs 22 — 351320: 로트 4,100 은 09-17 손절 · 평단 4,149 계좌는 09-16 손절).

## 계획 검증 실행 (2026-09-19 · 작성자 크로스체크 — 워크트리·저장소 무변경)

이 계획의 코드 블록을 스크래치 사본(`git archive HEAD` 로 뽑은 트리 · 워크트리 밖)에 과제 순서대로 붙여 넣고 돌렸다. DB 는 SELECT 만, 라이브 로그는 읽기만. 두 차례 했다 — 1차(최초 계획) · 2차(critic 교차검수 REQUEST_CHANGES + 사장님 추가 결정 D3′·D5 반영 뒤). 아래 과제의 「참고값」은 2차 수치다(DB·로그가 그 뒤 바뀌면 달라질 수 있다).

**2차 결과**
- 단위 테스트 11파일 **140 passed**(DB 없음 · 3초 · 1차 127 + 새 13: 방향별 신호 표 · `slot_verdict` 반례 3 · 빈티지 방향 · 거래량 룰 여유 · 청산 phase · `lift_entry` 2 · 해제 뒤 진입일 · 시가 단계 청산 재신호 2 · 해제 뒤 추가매수).
- `run`(1일) 3초 × 2(09-18 · 09-14) · `run`(7거래일) 7초 · 두 번 실행한 CSV·summary.md 해시 **동일(멱등)** · `[경고]` **0**.
- 로그 귀속: 시장급락 09-11 196줄 · 09-14 713줄 **전부 귀속(미귀속 0)** · `보유 중인 종목 매수 신호 무시` 09-17 2 · 09-18 125줄 · `가상매수:` 귀속 = 체결 원장 BUY(불일치 0).
- 익절·손절 엔진 경로 = 체결 원장 BUY **194/194 일치**(08-26~09-18).
- 신호 충실도(v3 · 방향별): Y 방향 전 그룹 100%(elder 42/42 · env 6/6 · day 21/21 · min 9/9 · ma20 19/19 · ma5 58/58 · rs shadow 31/31 · live 15/15) · **N 방향은 elder 11/11 뿐 — 나머지 7그룹 표본 0 ⇒ «N 방향 판정 불가»**. envelope 판정 가능 6행은 전부 실제 체결(bought) — 자명한 Y/Y. daytrading 이유 문자열 0/21 = 빈티지(관측 D-1 거래량 재기록 21쌍 +0.17%~+24.33%).
- 재현 신호 비중(B1 로트): 159/312 = 51%(elder 28% · env 0% · day 71% · min 81% · ma20 69% · ma5 15% · rs 34%) · «B1 중 A 캡»·«B1 중 A 이미 보유» 묶음은 전부 100% 재현. 빈티지 취약 재현 행 1(minervini).
- 재구성 모순(no_slot 인데 로그 매수신호): v2 **21건**(ma5 12 · rs 9) → v3 **0건**.
- 청산 충실도: 판정 불가 1(minervini n=4) 외 전부 ok(사유 일치 88.89~100%).
- D3′: 급락 차단 main 행 86 → 해제 뒤 체결 **27** · 분봉 없음 44 · 끝까지 밴드 밖 15. B1 로트 312 = 1차의 285 + 해제 뒤 27. 민감도: 하루 종일 막았으면 285 · 게이트 없었다면(09:02) 70.
- D5(B1 로트 중 라이브였다면 막혔을 것): 진입억제 78 · 25분 쿨다운 6 · 일일손실한도 0 · VI 관측 불가.
- B1 재신호 vs B2 추가매수: elder 9/9 · min 29/29 · ma20 9/9 · ma5 6/6 · rs 23/22(351320 — 로트 손절과 평단 손절이 갈림 · 결함 아님) · 나머지 0/0.

**«평가 가능» 규칙 변경 이력 — 숨기지 않는다**

| 판 | 규칙 | 무엇을 보고 바꿨나 | 신호 표(판정 가능 · Y · N) |
|---|---|---|---|
| v1(최초 계획) | 09:02 한 시점 — 그 시각 미보유 ∧ 빈자리 구간 안 ∧ `[캡]` 줄 없음 | — | day 38행 · Y 100% · **N 0/17(LOW)** · min 12행 · N 0/3 · ma5 62행 · N 0/4 |
| v2(1차 검증 뒤) | `classify_candidate`(minervini 원장 규칙 · 앞 순위 매수로 빈자리 소진 포함) | 1차 실행의 day 55%·min 75% LOW 를 보고 원인(첫 틱 안에서 앞 순위 매수가 자리를 채움)을 찾아 바꿨다 — **결과를 보고 바꾼 변경**이다(critic 🔴2 지적 · 🔒 정신 위배) | day 21행 · Y 100% · N 표본 0 · min 9 · ma5 58 |
| v3(2차 · 채택) | v2 + «빈자리 구간 안에서 그 전략 on_tick 이 끝났으면 no_slot 아님»(critic 이 준 구조 결함 수정 · 근거 = on_tick 은 한 번에 목록 전부를 평가, base.py:660-734) | critic 반례 21행(ma5 12 · rs 9: v2 no_slot 인데 빈자리 구간 안에 `[on_tick] 매수신호` — 예 ma5 09-11 006910 빈자리 09:00:00~09:28:07 · 첫 신호 09:03:37) | v2 와 같은 판정 가능 수(반례 21행은 이미 로그 Y) · 재구성 모순 21 → 0 |

- 결론을 바꾸는 방향으로 고른 규칙이 아니라는 증거는 표 자체다 — v3 는 판정 가능 수를 늘리지도 줄이지도 않았고(N 방향 표본 0 그대로), v1 의 day N 0/17 은 «앞 순위 매수가 첫 on_tick 안에서 자리를 채워 라이브가 평가하지 못한 행»이다(v3 도 그 구간 안 on_tick 완료가 없음을 확인). 🔒 이 뒤로 규칙을 바꾸지 않는다 — 세 규칙은 보고서 §1-2 에 늘 나란히 싣는다.
- 1차 실행의 그 밖 수치(127 passed · 7일 7초 · 멱등 · 귀속 · 194/194 · 청산 충실도)는 2차와 같다.

## 파일 구조

모두 `RoboTrader_template/backtest/concept_axes/ledger8/` 아래(기존 5파일은 미커밋 초안).

| 파일 | 책임 | 과제 |
|---|---|---|
| `__init__.py` | 패키지 표지(기존 · 그대로) | 1 |
| `registry.py` | 8전략 명세(게이트 순서·K·max_daily_trades·regime_index 이력·rs 모드·상태 검사 대상) — 순수 데이터 | 1 (전면 교체) |
| `sizing.py` | arm A 수량 상한(복리 per_stock·종목당 상한) · arm B 수량 — 순수 | 1 (전면 교체) |
| `logscan8.py` | 라이브 로그 1회 순회 → 전략별 E6·매수신호·게이트(귀속)·체결·캡·시장방향성 시간선 — 순수(파일 읽기만) | 2 (전면 교체) |
| `fidelity8.py` | 신호(방향별)·«평가 가능» 규칙(`slot_verdict` v1·v2·v3)·빈티지 표시·청산·익절손절·진입가 충실도 — 순수 | 3 신설 · 6 추가 |
| `livesignal8.py` | 라이브 `_check_buy` 호출(패치·가드·상태 검사) · 강제 밴드 · 거래량 룰 여유(`volume_margin`) | 3 신설 |
| `sources8.py` | SELECT(스냅샷·체결 원장+수량·일봉 창 캐시·분봉) — 재사용 래퍼 | 4 (전면 교체) · 9 추가 |
| `context8.py` | 실행 문맥(DB·달력·체결·인스턴스·캐시·시간선 질의) | 4 신설 · 6·9 추가 |
| `run.py` | CLI — `--stage signal|exit|all` · CSV · 요약 | 4 신설 · 6·9·10 확장 |
| `exitsim8.py` | 봉 단위 청산 순서 엔진(청산 phase) · D3′ 해제 뒤 진입(`lift_entry`) — 순수(탐침 주입) | 5 신설 |
| `sellprobe8.py` | 라이브 익절·손절 비율(엔진 경로) · 데이터 청산 탐침(전략 사본) | 6 신설 |
| `stages.py` | arm A «멈춘 단계» 분류 + 접힌 단계 행 — 순수 | 7 신설 |
| `arms.py` | A_actual · A_sim · B1 · B2 로트/계좌 엔진 — 순수 | 8 신설 |
| `report.py` | `summary.md` (5개 질문 · 방향별 충실도 · 규칙 민감도 · 재현 비중·빈티지 · D3′·D5 부록) — 순수 | 10 신설 |
| `README.md` | 사용법·재현 근거·가정·한계 | 11 신설 |
| `tests/` | `conftest.py` · `test_registry_gate_order.py` · `test_sizing.py` · `test_logscan8.py` · `test_fidelity8.py` · `test_livesignal8.py` · `test_exitsim8.py` · `test_sellprobe8.py` · `test_stages.py` · `test_arms.py` · `test_report.py` | 과제별 |
| `results/` | 실행 산출물(CSV·MD·JSON) — CSV 는 `.gitignore:154` 예외로 추적됨 | 9·10·11 |

## 과제 목록

| # | 과제 | 스펙 §4 | 예상 줄 수(코드+테스트) |
|---|---|---|---|
| 1 | registry · sizing 교체 + 게이트 순서 AST 대조 | ① (#8·9·12·13·14·20) | 306 + 165 |
| 2 | logscan8 교체 — `[on_tick] 매수신호` 기준 · 게이트 귀속 · on_tick 완료 시각 · 시장방향성 | ① (#3·4·16·17·18) | 437 + 158 |
| 3 | fidelity8(신호 · 방향별 · `slot_verdict` · 빈티지) + livesignal8(+거래량 룰 여유) | ② | 370 + 190 |
| 4 | sources8 · context8 · run `--stage signal` + **신호 충실도 게이트(실데이터 · 규칙 민감도)** | ② | 430 |
| 5 | exitsim8 — 봉 단위 청산 순서 엔진 · 청산 phase · D3′ `lift_entry` | ③ · D3′ | 228 + 130 |
| 6 | sellprobe8 + 청산·익절손절 충실도 + run `--stage exit` + **청산 충실도 게이트(실데이터)** | ③ | 280 + 150 |
| 7 | stages — arm A 멈춘 단계(+일일손실한도) | ④ | 139 + 71 |
| 8 | arms — A_actual · A_sim · B1 · B2(청산 phase 시간선 · 해제 뒤 추가매수) | ④ | 309 + 136 |
| 9 | run 전체(원장·체결·arm·CSV · D3′ · D5) + 1일 스모크 2회 | ⑤ | 400 |
| 10 | report + 7일 전체 실행 | ⑥ | 336 + 53 |
| 11 | README + 최종 검증 | ⑦ | 180 |

---

### Task 1: registry · sizing 교체 + 게이트 순서 AST 대조

**Files:**
- Modify(전면 교체): `backtest/concept_axes/ledger8/registry.py`
- Modify(전면 교체): `backtest/concept_axes/ledger8/sizing.py`
- Create: `backtest/concept_axes/ledger8/tests/__init__.py`(빈 파일), `backtest/concept_axes/ledger8/tests/conftest.py`
- Test: `backtest/concept_axes/ledger8/tests/test_registry_gate_order.py`, `backtest/concept_axes/ledger8/tests/test_sizing.py`

**Interfaces:**
- Consumes: 없음(라이브 소스 파일을 텍스트로만 읽는다).
- Produces:
  - `registry.StrategySpec(folder, cls, gate_order, has_cap_log, ref_key, frame, entry_eval_arity, k_history, mdt_history, regime_history, note)` · `.logger_name` · `.pattern`
  - `registry.SPECS`, `BY_FOLDER: Dict[str, StrategySpec]`, `ALL_FOLDERS: Tuple[str, ...]`, `LOGGER_TO_FOLDER: Dict[str, str]`
  - `registry.spec(folder) -> StrategySpec` · `k_for(folder, d) -> Tuple[int, str]` · `mdt_for(folder, d) -> Tuple[int, str]` · `regime_index_for(folder, d) -> Tuple[str, str]` · `corp_action_mode_for(folder, d) -> Optional[str]` · `state_attrs(folder) -> Tuple[str, ...]`
  - 상수 `G_MIN_LEN G_TIMEFRAME G_HELD G_DAILY_TRADES G_MAX_POSITIONS G_CHECK_BUY` · `P1 P2 P3` · `FRAME_ONTICK FRAME_QUANT` · `TIER_MAIN="main" TIER_EXT="ext" TIER_OFFLIST="offlist"` · `RS_LEADER_LIVE_SINCE=date(2026,9,17)` · `CAP_LOG_SINCE=date(2026,9,16)` · `VIRTUAL_CAPITAL_PER_STRATEGY=10_000_000` · `LEDGER_START=date(2026,9,10)` · `LEDGER_END=date(2026,9,18)` · `EXIT_FID_SINCE=date(2026,8,26)` · `STATE_CHECKED` · `STATE_EXEMPT`
  - `sizing.Qty(qty, basis, notional, per_stock, note)` · `.blocked` · `sizing.arm_a_qty(price, per_stock, cap=None, per_stock_src="") -> Qty` · `sizing.arm_b_qty(price, per_stock=ARM_B_PER_STOCK) -> Qty` · 상수 `ARM_B_PER_STOCK=1_000_000 BASIS_AMOUNT="amount" BASIS_ONE_SHARE="one_share" BASIS_NONE="n/a"`

- [ ] **Step 1: 사전 확인 — 창 안 설정 변경이 K 뿐인지(⚠️ 미확인 해소)**

Run(워크트리 cwd):
```bash
git show bc7df66 --stat -- 'strategies/*/config.yaml'
git show bc7df66 -- 'strategies/*/config.yaml' | grep -E '^[+-] ' | grep -v max_positions
git log --format='%h %ci %s' --since=2026-09-01 -G'max_per_stock_amount|paper_investment_per_stock|take_profit_pct|stop_loss_pct|max_hold_days|entry_band|trail_|min_daily_bars' -- 'strategies/*/config.yaml'
```
Expected: 첫 줄은 ma20·daytrading·minervini `config.yaml` 3개. 둘째 줄 출력 0줄(바뀐 줄이 `max_positions` 뿐). 셋째 줄은 `bc7df66` 한 줄(주석 문자열 매칭) 또는 0줄. 다른 커밋이 나오면 멈추고 관리자에게 보고(그 값의 이력을 registry 에 넣어야 한다).

- [ ] **Step 2: 테스트 뼈대와 실패하는 테스트 작성**

`backtest/concept_axes/ledger8/tests/__init__.py`: 빈 파일.

`backtest/concept_axes/ledger8/tests/conftest.py`:
```python
"""ledger8 단위 테스트 — DB·라이브 로그 없음. 워크트리에서만 돌린다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]   # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

`backtest/concept_axes/ledger8/tests/test_registry_gate_order.py`:
```python
"""registry 가 라이브 소스와 맞는지 — AST·설정 파일 대조(DB·전략 import 없음).

라이브가 바뀌면 이 테스트가 먼저 깨진다(스펙 검증표 #1·#20).
"""
from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from backtest.concept_axes.ledger8 import registry as R

ROOT = Path(__file__).resolve().parents[4]
NEEDLES = (
    (R.G_MIN_LEN, "self.get_min_data_length()"),
    (R.G_TIMEFRAME, "timeframe != 'daily'"),
    (R.G_HELD, "stock_code in self.positions"),
    (R.G_DAILY_TRADES, "self.daily_trades >= self._max_daily_trades"),
    (R.G_MAX_POSITIONS, "len(self.positions) >= self._max_positions"),
)


def _class(folder: str) -> ast.ClassDef:
    tree = ast.parse((ROOT / "strategies" / folder / "strategy.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == R.spec(folder).cls:
            return node
    raise AssertionError(f"{folder}: 클래스 {R.spec(folder).cls} 없음")


def _method(cls: ast.ClassDef, name: str):
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _class_attr(cls: ast.ClassDef, name: str):
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def gate_order_in_source(fn) -> tuple:
    out = []
    for st in fn.body:
        if isinstance(st, ast.If):
            text = ast.unparse(st.test)
            for tok, needle in NEEDLES:
                if needle in text:
                    out.append(tok)
                    break
        elif isinstance(st, ast.Return) and st.value is not None and "self._check_buy(" in ast.unparse(st.value):
            out.append(R.G_CHECK_BUY)
    return tuple(out)


def _trading_config() -> dict:
    return json.loads((ROOT / "config" / "trading_config.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_gate_order_matches_source(folder):
    assert gate_order_in_source(_method(_class(folder), "generate_signal")) == R.spec(folder).gate_order


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_cap_log_presence(folder):
    fn = _method(_class(folder), "generate_signal")
    assert ("_log_cap_skip" in ast.unparse(fn)) == R.spec(folder).has_cap_log


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_name_exit_timeframe_and_no_on_tick_override(folder):
    cls = _class(folder)
    assert _class_attr(cls, "name") == R.spec(folder).cls          # 로거 = strategy.<name>(base.py:393)
    assert _class_attr(cls, "exit_timeframe") == "daily"            # 매도 루프 = D-1 확정봉(base.py:742-744)
    assert _method(cls, "on_tick") is None                          # 8전략 모두 BaseStrategy.on_tick


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_evaluate_entry_arity(folder):
    fn = _method(_class(folder), "evaluate_entry")
    lens = {len(n.value.elts) for n in ast.walk(fn)
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)}
    assert lens == {R.spec(folder).entry_eval_arity}


def test_registry_covers_enabled_strategies():
    enabled = {s["name"] for s in _trading_config()["strategies"] if s.get("enabled")}
    assert enabled == set(R.ALL_FOLDERS)


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_latest_regime_index_matches_trading_config(folder):
    live = {s["name"]: s.get("regime_index", "both") for s in _trading_config()["strategies"]}
    assert R.regime_index_for(folder, R.LEDGER_END)[0] == live[folder]


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_latest_k_and_mdt_match_config_yaml(folder):
    y = yaml.safe_load((ROOT / "strategies" / folder / "config.yaml").read_text(encoding="utf-8"))
    rm = y["risk_management"]
    assert R.k_for(folder, R.LEDGER_END)[0] == int(rm["max_positions"])
    assert R.mdt_for(folder, R.LEDGER_END)[0] == int(rm.get("max_daily_trades", 5))


def test_history_lookups():
    assert R.k_for("minervini_volume_dryup", date(2026, 9, 17))[0] == 3
    assert R.k_for("minervini_volume_dryup", date(2026, 9, 18))[0] == 6
    assert R.k_for("book_pullback_ma20", date(2026, 9, 17))[0] == 5
    assert R.regime_index_for("daytrading_3methods_breakout", date(2026, 9, 11))[0] == "KOSDAQ"
    assert R.regime_index_for("daytrading_3methods_breakout", date(2026, 9, 14))[0] == "auto"
    assert R.corp_action_mode_for("rs_leader", date(2026, 9, 16)) == "shadow"
    assert R.corp_action_mode_for("rs_leader", date(2026, 9, 17)) == "live"
    assert R.corp_action_mode_for("elder_ema_pullback", date(2026, 9, 17)) is None
    assert "_ontick_skip_log" not in R.state_attrs("rs_leader")
    assert "_ontick_skip_log" in R.state_attrs("book_pullback_ma20")
    assert R.LOGGER_TO_FOLDER["strategy.RSLeaderStrategy"] == "rs_leader"
    with pytest.raises(KeyError):
        R.spec("no_such_strategy")
```

`backtest/concept_axes/ledger8/tests/test_sizing.py`:
```python
"""사이징 두 arm — 사장님 규칙 예시 · 복리 per_stock · 종목당 상한 · 0주."""
from __future__ import annotations

from backtest.concept_axes.ledger8 import sizing as Z


def test_arm_b_examples_from_rule():
    q = Z.arm_b_qty(204_000)
    assert (q.qty, q.basis, q.notional) == (4, Z.BASIS_AMOUNT, 816_000.0)
    q = Z.arm_b_qty(1_078_000)
    assert (q.qty, q.basis, q.notional) == (1, Z.BASIS_ONE_SHARE, 1_078_000.0)


def test_arm_b_boundary_and_missing():
    assert (Z.arm_b_qty(1_000_000).qty, Z.arm_b_qty(1_000_000).basis) == (1, Z.BASIS_AMOUNT)
    assert Z.arm_b_qty(999_999).qty == 1
    assert Z.arm_b_qty(None).blocked and Z.arm_b_qty(0).blocked


def test_arm_a_compounded_per_stock():
    q = Z.arm_a_qty(10_000, 864_374, cap=3_000_000, per_stock_src="log")
    assert q.qty == 86 and q.per_stock == 864_374


def test_arm_a_cap_binds():
    q = Z.arm_a_qty(10_000, 3_337_630, cap=3_000_000)
    assert q.qty == 300 and "상한" in q.note


def test_arm_a_zero_when_price_above_limit():
    q = Z.arm_a_qty(1_097_000, 864_374, cap=3_000_000)
    assert q.blocked and q.qty == 0 and "수량부족" in q.note


def test_arm_a_missing_inputs():
    assert Z.arm_a_qty(None, 1_000_000).blocked
    assert Z.arm_a_qty(10_000, None).blocked
```

- [ ] **Step 3: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_registry_gate_order.py backtest/concept_axes/ledger8/tests/test_sizing.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module ... has no attribute 'LEDGER_END'`(registry) · `TypeError: arm_a_qty() ...`(sizing 시그니처가 초안과 다름).

- [ ] **Step 4: `registry.py` 전면 교체**

```python
"""8전략 명세 — 라이브 소스에서 실측한 값만 적는다(순수 데이터 · import 부수효과 0).

🔴 여기 적힌 것은 «라이브가 실제로 하는 일»이다. 코드와 어긋나면 코드가 맞다.
   `tests/test_registry_gate_order.py` 가 8전략 `strategy.py` 를 AST 로 읽어 게이트 순서 · `_log_cap_skip`
   유무 · 클래스 `name` · `exit_timeframe` · `evaluate_entry` 반환 길이 · `on_tick` 미재정의를 대조하고,
   `config/trading_config.json`·각 `config.yaml` 과 최신 K·max_daily_trades·regime_index 를 대조한다.

게이트 순서 3패턴 (2026-09-19 실측 · 커밋 14a9b7a)
────────────────────────────────────────────────
`BaseStrategy.on_tick` 매수 루프(strategies/base.py:660-734)는 8전략 공통이다:

    data 없음/len < get_min_data_length()  → 스킵      (base.py:662-687)
    describe_impossible_drop(data)         → 스킵      (base.py:693-707)
    generate_signal(code, data, 'daily')               (base.py:708)
    BUY 면 `[on_tick] 매수신호: CODE(…)` 한 줄 → ctx.buy (base.py:720-734)

| 패턴 | generate_signal 안 순서 | 전략 |
|---|---|---|
| **P1** | `min_len` → `timeframe` → 보유(매도분기) → `daily_trades` → `max_positions` → `_check_buy` | ma20 · ma5 · elder · rs_leader · deep_mr |
| **P2** | `min_len` → 보유(매도분기) → `daily_trades` → `max_positions` → `timeframe` → `_check_buy` | daytrading · minervini |
| **P3** | (`min_len` **없음**) → 보유(매도분기) → `daily_trades` → `max_positions` → `timeframe` → `_check_buy` | envelope |

🔑 매수·매도 경로와 이 원장 (검증표 #2~#4 정정)
   - 매수 루프는 언제나 `timeframe='daily'` ⇒ `timeframe` 게이트는 매수에서 발화하지 않는다.
   - 매도는 두 경로다. ① `on_tick` 매도 루프(base.py:739-761)가 `exit_timeframe`(8전략 전부 'daily')으로
     `generate_signal` → 보유 분기 → `_check_sell` — 틱마다 **D-1 확정봉**. ② `position_monitor`
     (core/trading/position_monitor.py:359-361)는 `timeframe='intraday'` 인데 P1 은 게이트에서 None,
     P2·P3 의 `evaluate_sell_conditions` 는 보유기간만 본다 ⇒ **매도 재현은 8전략 공통 1벌**(exitsim8).
   - `[캡] … 사유=timeframe` 은 ② 경로(P1 의 ma20)에서만 찍힌다 — 매수 차단이 아니다.
   - 매도 루프는 «다른 전략» 보유 종목까지 돈다(core/trading_context.py:300-307). 자기 보유가 아니면 매수
     분기로 떨어져 🧾·`[캡]` 줄이 찍히고 BUY 는 버려진다(base.py:750) ⇒ **신호 기준 줄은 매수 루프 전용
     `[on_tick] 매수신호: CODE(`**(base.py:723-726)이고 `[캡]` 은 E6 목록과 교집합으로만 읽는다.
   - **P3(envelope)만 진짜로 다르다**: `min_len` 가드가 없고(on_tick 게이트는 `min_gate_bars`=5,
     strategy.py:57-63), `_check_buy` 가 인자 `data` 를 안 쓰고 `_fetch_entry_history` 로 QuantDailyReader 에서
     `entry_lookback_bars`=230봉(config.yaml:35)을 다시 읽는다(strategy.py:225-266). `_entry_df_cache`·`_quant` 는
     캐시라 상태 무변경 검사 대상이 아니다.

`_log_cap_skip` 계기는 3전략(ma20 · daytrading · minervini)에만 있다 ⇒ 나머지 5전략의 `[캡]` 칸은 언제나 NA.
「[캡] 줄이 없다」를 「막히지 않았다」로 읽지 말 것.

`max_daily_trades` 는 «일일 체결»(매수+매도) 한도다 — 8전략 `on_order_filled` 첫 줄이 매수·매도 모두
`daily_trades += 1`(예: book_pullback_ma20/strategy.py:151)이고 매도도 통보된다(core/trading_decision_engine.py:935).

금액 값(`max_per_stock_amount` · deep_mr `paper_investment_per_stock` · 복리 per_stock)은 여기 적지 않는다 —
라이브 인스턴스·config·로그(`종목당 투자금액 재산정`)에서 실행 때 읽는다(복제본이 어긋날 위험 제거).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, Sequence, Tuple

# 게이트 토큰 — 테스트가 소스에서 찾아내는 표지와 같은 이름
G_MIN_LEN = "min_len"
G_TIMEFRAME = "timeframe"
G_HELD = "held"
G_DAILY_TRADES = "daily_trades"
G_MAX_POSITIONS = "max_positions"
G_CHECK_BUY = "check_buy"

P1 = (G_MIN_LEN, G_TIMEFRAME, G_HELD, G_DAILY_TRADES, G_MAX_POSITIONS, G_CHECK_BUY)
P2 = (G_MIN_LEN, G_HELD, G_DAILY_TRADES, G_MAX_POSITIONS, G_TIMEFRAME, G_CHECK_BUY)
P3 = (G_HELD, G_DAILY_TRADES, G_MAX_POSITIONS, G_TIMEFRAME, G_CHECK_BUY)
PATTERN_NAME = {P1: "P1", P2: "P2", P3: "P3"}

FRAME_ONTICK = "ontick_daily"      # on_tick 이 넘긴 일봉(PriceRepository · 120 달력일 · ~80~85봉)
FRAME_QUANT = "quant_entry_hist"   # envelope `_check_buy` 가 스스로 읽는 프레임(QuantDailyReader 230봉)

TIER_MAIN = "main"        # 라이브 E6 상위 T(목표 10) — D1 본 결과
TIER_EXT = "ext"          # 스냅샷 T+1~20위 — 라이브가 후보로 본 적 없음(안전필터 미검사) · 별도 칸
TIER_OFFLIST = "offlist"  # 실제 매수인데 그날 E6 목록 밖(소유자 미지정 SELECTED) — A 에만 있다

Hist = Tuple[Tuple[date, Any, str], ...]


@dataclass(frozen=True)
class StrategySpec:
    folder: str                 # 폴더키 = trading_config.json strategies[].name = vtr.strategy
    cls: str                    # 클래스 `name` → 로거 이름 `strategy.<cls>`
    gate_order: Tuple[str, ...]
    has_cap_log: bool           # generate_signal 에 _log_cap_skip 호출부가 있나
    ref_key: str                # Signal.metadata 의 기준가 키
    frame: str
    entry_eval_arity: int       # evaluate_entry 반환 튜플 길이(강제 밴드 패치용)
    k_history: Hist
    mdt_history: Hist
    regime_history: Hist        # trading_config.json regime_index(급락게이트 지수축)
    note: str = ""

    @property
    def logger_name(self) -> str:
        return f"strategy.{self.cls}"

    @property
    def pattern(self) -> str:
        return PATTERN_NAME.get(self.gate_order, "?")


_MDT5: Hist = ((date(2026, 6, 1), 5, "8전략 공통 max_daily_trades=5(일일 «체결») · 변경 이력 없음"),)
_KOSPI: Hist = ((date(2026, 6, 2), "KOSPI",
                 "trading_config.json regime_index · 창 안 변경 없음(git log -G regime_index)"),)

SPECS: Tuple[StrategySpec, ...] = (
    StrategySpec(
        folder="elder_ema_pullback", cls="ElderEmaPullbackStrategy",
        gate_order=P1, has_cap_log=False, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 2), 5, "초기값(도입 커밋 4d0e941 · 32b42ee 표기 무해 — 검증표 #8)"),
                   (date(2026, 6, 4), 20, "689792a K 5→20(2026-06-03 커밋 · 다음 기동 발효)")),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="min_daily_bars=70 · 진입 기준 = 매수스톱(D-1 고가 + 1틱) · 밴드 [스톱, 스톱×1.02]",
    ),
    StrategySpec(
        folder="book_envelope_200d", cls="BookEnvelope200dStrategy",
        gate_order=P3, has_cap_log=False, ref_key="ref_close", frame=FRAME_QUANT, entry_eval_arity=3,
        k_history=((date(2026, 6, 5), 5, "16114b5/ad4cc12 신설"),),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="🔴 스냅샷이 창 안 1~2행(09-09~09-15 스캔) 뒤 0행 ⇒ 신호 판정 표본이 작고, 판정 가능 행이 "
             "실제 체결(bought)뿐이면 자명한 Y/Y 다(보고서가 표에서 문장을 만든다). 자체 프레임이 «지금 DB» 라 빈티지 위험.",
    ),
    StrategySpec(
        folder="daytrading_3methods_breakout", cls="DayTrading3MethodsBreakoutStrategy",
        gate_order=P2, has_cap_log=True, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 2), 5, "초기값(근거 주석 없음)"),
                   (date(2026, 9, 18), 10, "bc7df66/c565256 K 5→10 · docs/prereg_2026-09-15_focus3_K_raise.md")),
        mdt_history=_MDT5,
        regime_history=((date(2026, 6, 2), "KOSDAQ", "044a20e 전략별 지수 도입"),
                        (date(2026, 9, 14), "auto", "a57a607 KOSDAQ→auto(09-11 18:50 커밋 · 09-14 07:40 발효)")),
        note="거래량 룰 — 빈티지 위험. `[on_tick] 매수신호` 이유 문자열의 vol=a/b 로 건별 대조 가능",
    ),
    StrategySpec(
        folder="minervini_volume_dryup", cls="MinerviniVolumeDryupStrategy",
        gate_order=P2, has_cap_log=True, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 2), 3, "821fb80 Minervini K=3 집중"),
                   (date(2026, 9, 18), 6, "bc7df66/c565256 K 3→6 · docs/prereg_2026-09-15_focus3_K_raise.md")),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="cap_skip_ledger(48b2fe1)가 이 전략만 다루던 원장의 원본",
    ),
    StrategySpec(
        folder="book_pullback_ma20", cls="BookPullbackMa20Strategy",
        gate_order=P1, has_cap_log=True, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 5), 5, "초기값(근거 주석 없음)"),
                   (date(2026, 9, 18), 10, "bc7df66/c565256 K 5→10 · docs/prereg_2026-09-15_focus3_K_raise.md")),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="P1 인데 _log_cap_skip 이 있다 ⇒ [캡] 사유=timeframe 줄은 position_monitor 분봉 경로(매수 차단 아님)",
    ),
    StrategySpec(
        folder="book_pullback_ma5", cls="BookPullbackMa5Strategy",
        gate_order=P1, has_cap_log=False, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=3,
        k_history=((date(2026, 6, 5), 5, "초기값(근거 주석 없음)"),),
        mdt_history=_MDT5, regime_history=_KOSPI,
    ),
    StrategySpec(
        folder="rs_leader", cls="RSLeaderStrategy",
        gate_order=P1, has_cap_log=False, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=2,
        k_history=((date(2026, 6, 6), 10, "7fd20d4 신설"),),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="🔴 _check_buy 첫머리 corp_action 배제(모드 = config.constants.RS_LEADER_CORP_ACTION_MODE · "
             "2026-09-17 07:40 부터 live, 가드 코드 자체는 9811d42 · 09-10 23:49 머지 ⇒ 09-10 은 가드 없음 = shadow 와 동치). "
             "_should_log_ontick 이 _ontick_skip_log 를 바꾸므로 상태 무변경 검사에서 제외. 신호가 매일 반복될 수 있다.",
    ),
    StrategySpec(
        folder="deep_mr_dev20", cls="DeepMrDev20Strategy",
        gate_order=P1, has_cap_log=False, ref_key="close", frame=FRAME_ONTICK, entry_eval_arity=2,
        k_history=((date(2026, 6, 12), 5, "938ceeb 신설"),),
        mdt_history=_MDT5, regime_history=_KOSPI,
        note="창 안 스냅샷 0건(매일 `[E6] deep_mr_dev20: screener_snapshots 0건`) ⇒ 후보 0",
    ),
)

BY_FOLDER: Dict[str, StrategySpec] = {s.folder: s for s in SPECS}
ALL_FOLDERS: Tuple[str, ...] = tuple(s.folder for s in SPECS)
LOGGER_TO_FOLDER: Dict[str, str] = {s.logger_name: s.folder for s in SPECS}

RS_LEADER_LIVE_SINCE = date(2026, 9, 17)   # docs/prereg_2026-09-16_rsleader_exclusion_live.md · 로그 09-17 07:40:26 mode=live
CAP_LOG_SINCE = date(2026, 9, 16)          # [캡] 계기 e597c33(머지 36fe61c) · 09-16 07:40
VIRTUAL_CAPITAL_PER_STRATEGY = 10_000_000  # config/constants.py:181
LEDGER_START = date(2026, 9, 10)
LEDGER_END = date(2026, 9, 18)             # 7거래일(검증표 #19)
EXIT_FID_SINCE = date(2026, 8, 26)         # 1810cd2(2026-08-25 21:19) 전략 고유 sl/tp 제거 → 다음 기동부터

# 상태 무변경 검사(livesignal8) — 호출 전후 deepcopy 비교
STATE_CHECKED: Tuple[str, ...] = ("positions", "daily_trades", "_cap_skip_logged", "_cap_skip_log_date",
                                  "config", "_ontick_skip_log")
STATE_EXEMPT: Dict[str, Tuple[str, ...]] = {"rs_leader": ("_ontick_skip_log",)}


def spec(folder: str) -> StrategySpec:
    try:
        return BY_FOLDER[folder]
    except KeyError:
        raise KeyError(f"등록되지 않은 전략 폴더키: {folder!r} (등록: {', '.join(ALL_FOLDERS)})")


def _at(history: Sequence[Tuple[date, Any, str]], d: date, what: str) -> Tuple[Any, str]:
    best: Optional[Tuple[Any, str]] = None
    for eff, v, why in sorted(history, key=lambda h: h[0]):
        if eff <= d:
            best = (v, why)
    if best is None:
        raise ValueError(f"{what} 이력에 {d} 이전 항목이 없다")
    return best


def k_for(folder: str, d: date) -> Tuple[int, str]:
    """날짜 d 에 유효한 (K=max_positions, 근거)."""
    v, why = _at(spec(folder).k_history, d, f"{folder} K")
    return int(v), why


def mdt_for(folder: str, d: date) -> Tuple[int, str]:
    """날짜 d 에 유효한 (max_daily_trades — 일일 «체결», 근거)."""
    v, why = _at(spec(folder).mdt_history, d, f"{folder} max_daily_trades")
    return int(v), why


def regime_index_for(folder: str, d: date) -> Tuple[str, str]:
    """날짜 d 에 그 전략이 급락게이트에 넘긴 설정값(`KOSPI`·`KOSDAQ`·`auto`·`both`·`none`)."""
    v, why = _at(spec(folder).regime_history, d, f"{folder} regime_index")
    return str(v), why


def corp_action_mode_for(folder: str, d: date) -> Optional[str]:
    """그날 라이브가 쓰던 `RS_LEADER_CORP_ACTION_MODE`. rs_leader 가 아니면 None."""
    if folder != "rs_leader":
        return None
    return "live" if d >= RS_LEADER_LIVE_SINCE else "shadow"


def state_attrs(folder: str) -> Tuple[str, ...]:
    exempt = STATE_EXEMPT.get(folder, ())
    return tuple(a for a in STATE_CHECKED if a not in exempt)
```

- [ ] **Step 5: `sizing.py` 전면 교체**

```python
"""두 사이징 arm — 순수 함수(DB·로그·전략 인스턴스 없음).

🔴 arm B 는 「자본 분모가 없는 세계」다. 총자산·누적수익률·자본 대비 %를 계산하지 말 것.
   이 모듈은 «수량»과 «명목금액»만 돌려준다.

arm A — 라이브 `VirtualTradingManager.get_max_quantity`(core/virtual_trading_manager.py:591-620) 재현
────────────────────────────────────────────────────────────────────────────────────────────
    per_stock  = 그날 07:40 복리 재산정 값 = 기준값 × (현금 + 원가) / 초기자본
                 (recalculate_investment_amounts :300-361 · 로그 `종목당 투자금액 재산정: <전략> A원 → B원`)
                 기준값 = 자본/K(allocate_strategy_capital :250-254) · yaml `paper_investment_per_stock` 이
                 있으면 그 값(deep_mr_dev20 · bot/initializer.py:489-494 · set_strategy_investment_amount :261-276)
    max_amount = min(per_stock, 잔고)            (:608)
    cap        = yaml `max_per_stock_amount` 가 max_amount 보다 작으면 그 값 (:611-617)
    qty        = int(max_amount / price)         (:618) ⇒ price > max_amount 면 0주 → 「수량부족」
                 (core/trading_decision_engine.py:429-430)
    🔑 잔고는 재현하지 않는다(전략 잔고 시간선 = paper_strategy_equity 리플레이 영역) ⇒ arm A 수량은 «상한»이다.
       실측: 09-18 ma20 per_stock 864,374 · 09-17 minervini 3,337,630(상한 3,000,000 에 걸림) — 검증표 #12.

arm B — 사장님 규칙(스펙 §0 · 2026-09-18 확정)
─────────────────────────────────────────────
    qty = max(1, floor(1_000_000 / price))   — 자본 한도·K·일일 체결 한도·종목당 상한 전부 없음.
    예: 204,000원 → 4주(816,000원) · 1,078,000원 → 1주(1,078,000원). 고가주는 명목이 100만원을 넘는다(규칙의 성질).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Optional

ARM_B_PER_STOCK = 1_000_000   # 🔒 사장님 규칙의 기준 금액 — 결과를 보고 바꾸지 말 것

BASIS_AMOUNT = "amount"        # floor(1,000,000/주가) ≥ 1
BASIS_ONE_SHARE = "one_share"  # 주가 > 1,000,000 → 1주 강제
BASIS_NONE = "n/a"


@dataclass(frozen=True)
class Qty:
    qty: int
    basis: str
    notional: float                 # qty × price (원)
    per_stock: Optional[float] = None
    note: str = ""

    @property
    def blocked(self) -> bool:
        return self.qty <= 0


def arm_a_qty(price: Optional[float], per_stock: Optional[float], cap: Optional[float] = None,
              per_stock_src: str = "") -> Qty:
    """라이브 수량 상한(잔고 항 제외). `price > min(per_stock, cap)` 이면 0주."""
    if price is None or price <= 0 or per_stock is None or per_stock <= 0:
        return Qty(0, BASIS_NONE, 0.0, per_stock, "가격/per_stock 없음")
    max_amount = float(per_stock)
    notes = [f"per_stock {max_amount:,.0f}원" + (f"({per_stock_src})" if per_stock_src else "")]
    if cap is not None and 0 < float(cap) < max_amount:
        max_amount = float(cap)
        notes.append(f"종목당 상한 {max_amount:,.0f}원 적용")
    qty = int(max_amount / float(price))
    if qty <= 0:
        notes.append(f"주가 {float(price):,.0f} > 한도 {max_amount:,.0f} ⇒ 0주(수량부족 거절)")
        return Qty(0, BASIS_NONE, 0.0, float(per_stock), " · ".join(notes))
    return Qty(qty, BASIS_AMOUNT, qty * float(price), float(per_stock), " · ".join(notes))


def arm_b_qty(price: Optional[float], per_stock: int = ARM_B_PER_STOCK) -> Qty:
    """사장님 규칙 — `qty = max(1, floor(per_stock / price))`. 자원 제약 없음."""
    if price is None or price <= 0:
        return Qty(0, BASIS_NONE, 0.0, float(per_stock), "가격 없음")
    raw = floor(float(per_stock) / float(price))
    if raw >= 1:
        return Qty(int(raw), BASIS_AMOUNT, int(raw) * float(price), float(per_stock))
    return Qty(1, BASIS_ONE_SHARE, float(price), float(per_stock),
               f"주가 {float(price):,.0f} > {per_stock:,.0f} ⇒ 1주(명목 = 기준의 {float(price) / per_stock:.2f}배)")
```

- [ ] **Step 6: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_registry_gate_order.py backtest/concept_axes/ledger8/tests/test_sizing.py -q -p no:cacheprovider`
Expected: PASS(약 50 passed — 파라미터 8×6 + 단건). 게이트 순서 테스트가 실패하면 registry 가 아니라 라이브가 바뀐 것이다 — 고치지 말고 멈춰서 관리자에게 보고.

- [ ] **Step 7: 교차 확인(스펙 항목 충족 체크리스트)**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| 검증표 #1 게이트 3패턴 | `test_gate_order_matches_source` | [ ] |
| #2 매도 1벌 · #3 [캡]∩E6 · #4 신호 기준 줄 | registry 독스트링(구현은 과제 2·5) | [ ] |
| #5 envelope 230봉(210 아님) | registry 독스트링 | [ ] |
| #6 [캡] 3전략 | `test_cap_log_presence` | [ ] |
| #8 K 이력 · #9 일일 «체결» | `k_history`·`mdt_history` · `test_latest_k_and_mdt_match_config_yaml` | [ ] |
| #10 rs 모드 날짜 | `corp_action_mode_for` · `test_history_lookups` | [ ] |
| #12~#14 복리 per_stock·deep_mr·종목당 상한 | `sizing.arm_a_qty`(값은 과제 9 에서 로그·인스턴스로 주입) | [ ] |
| #19 7거래일 | `LEDGER_START/END` | [ ] |
| #20 게이트 순서 테스트 파일 신설 | `tests/test_registry_gate_order.py` | [ ] |
| §0 규칙 3 `max(1, floor(1e6/주가))` | `arm_b_qty` · `test_arm_b_examples_from_rule` | [ ] |

- [ ] **Step 8: Commit**

```bash
git add backtest/concept_axes/ledger8/__init__.py backtest/concept_axes/ledger8/registry.py backtest/concept_axes/ledger8/sizing.py backtest/concept_axes/ledger8/tests/__init__.py backtest/concept_axes/ledger8/tests/conftest.py backtest/concept_axes/ledger8/tests/test_registry_gate_order.py backtest/concept_axes/ledger8/tests/test_sizing.py docs/superpowers/specs/2026-09-19-ledger8-three-arms-design.md docs/superpowers/plans/2026-09-19-ledger8-three-arms.md
git commit -F - <<'MSG'
feat(ledger8): 8전략 명세·사이징 교체 + 게이트 순서 AST 대조 테스트

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```


---

### Task 2: logscan8 교체 — 신호 기준 줄 · 게이트 귀속 · 시장방향성 시간선

**Files:**
- Modify(전면 교체): `backtest/concept_axes/ledger8/logscan8.py`
- Test: `backtest/concept_axes/ledger8/tests/test_logscan8.py`

**Interfaces:**
- Consumes: 없음(순수 · 파일 읽기만). `registry.LOGGER_TO_FOLDER` 는 호출자가 넘긴다.
- Produces:
  - `Fold(n, first, last, detail)` · `.hit(hhmmss, **detail)`
  - `StratDay(e6, e6_zero, excluded, sector_mode, buysig, receipt, cap, nosignal, gates, fills, ontick_times, restore_n, per_stock)` · `.ontick_runs -> int` · `.cap_blocking(code) -> Dict[str, Fold]` · `.gates_for(code) -> Dict[str, Fold]`
  - `DayLog(d, files, by_strategy, owner_counts, rs_mode, market_dir, unattributed)` · `.found` · `.get(folder) -> StratDay` · `.index_state(index, hhmmss) -> str` · `.first_verdict_after(index, hhmmss, verdict) -> str`
  - `GateHit(gate, code, owner, detail)` · `parse_gate(msg) -> Optional[GateHit]` · `attribute(g, pending, last_owner) -> Tuple[Optional[str], Optional[str]]` · `reject_gate(text) -> str`
  - `scan_day(log_dir: Path, d: date, folders: Sequence[str], logger_to_folder: Dict[str, str]) -> DayLog`
  - `CandList(main, ext, target, src)` · `live_candidate_list(snapshot_codes, sd, default_target=10) -> CandList`
  - 게이트 상수 `G_CRASH="market_crash" G_REGIME="regime_gate" G_HELD_ANY="held_any" G_OWNED="owned_other" G_BUYSTOP="buy_stop" G_LIMITUP="limit_up" G_THROTTLE="throttle" G_BAND_ABOVE="band_above" G_BAND_BELOW="band_below" G_QTY="qty_short" G_BALANCE="balance_short" G_NO_PRICE="no_price" G_UNFILLED="unfilled" G_REJECT_OTHER="reject_other" G_DAILY_LOSS="daily_loss" G_FILL="fill"`

- [ ] **Step 1: 실패하는 테스트 작성 — 실제 로그 줄 픽스처**

아래 줄들은 2026-09-14·09-15·09-18 라이브 로그에서 그대로 옮기고 날짜 머리만 `2026-09-14` 로 맞췄다(표시 `[합성]` 은 창 안 표본이 없어 코드 문자열로 만든 줄). `backtest/concept_axes/ledger8/tests/test_logscan8.py`:
```python
"""logscan8 — 실제 줄 픽스처(DB 없음): 매도 루프 🧾 제외 · `종목=` 없는 시장급락 줄 귀속 · 보유 중 무시 줄 ·
[캡]∩E6 · 체결 줄 귀속 · 시장방향성 시간선."""
from __future__ import annotations

from datetime import date

from backtest.concept_axes.ledger8 import logscan8 as L
from backtest.concept_axes.ledger8 import registry as R

D = date(2026, 9, 14)

LOG = """\
2026-09-14 07:40:25 | strategy.RSLeaderStrategy | INFO | [rs-corp-action] mode=shadow (startup)
2026-09-14 07:40:28 | bot.state_restorer | INFO | [진단] 런타임 포지션 엔트리 46건 / 고유 46종목 / 소유자별 {'rs_leader': 10, 'minervini_volume_dryup': 3} (DB 기준선)
2026-09-14 07:40:28 | core.virtual_trading_manager | INFO | 종목당 투자금액 재산정: book_pullback_ma20 1,000,000원 → 864,374원 (자본 8,643,742/10,000,000 = 0.8644, 기준 1,000,000원)
2026-09-14 09:00:48 | core.candidate_selector | INFO | [섹터뉴스] rs_leader mode=shadow reason=ok 이동 10종목(↑7 ↓3) 점수 as-of 09:00 섹터매핑 20/20
2026-09-14 09:00:50 | core.candidate_selector | INFO | 후보 제외: 006490(006490) — 관리종목
2026-09-14 09:00:51 | core.candidate_selector | INFO | [E6] rs_leader: screener_snapshots 10건 확보 (스냅샷 20건, 목표 10건, D-1=2026-09-11)
2026-09-14 09:00:51 | core.candidate_selector | INFO | [E6] rs_leader: 후보 10종목
2026-09-14 09:00:51 | core.candidate_selector | INFO | [E6] deep_mr_dev20: screener_snapshots 0건 (D-1=2026-09-11) — 조건에 맞는 종목 없음, 금일 미진입
2026-09-14 09:00:51 | core.candidate_selector | INFO | [E6] deep_mr_dev20: 후보 0종목
2026-09-14 09:01:42 | core.trading_decision_engine | INFO | [시장방향성필터] 관측 지수=KOSPI 코드=0001 등락률=-3.45% 임계값=-2.5% 판정=차단
2026-09-14 09:02:20 | core.trading_decision_engine | INFO | [시장방향성필터] 관측 지수=KOSDAQ 코드=1001 등락률=-2.44% 임계값=-3.0% 판정=허용
2026-09-14 09:04:48 | strategy.RSLeaderStrategy | INFO | 🧾 [PAPER] 매수 시그널: 060570 @ 5,040 (추천 595주) | 절대상승추세(종가>MA20·종가>MA60·MA20>MA60·60일수익>0)
2026-09-14 09:04:48 | strategy.RSLeaderStrategy | INFO | [on_tick] 매수신호: 060570(BUY, 신뢰도 60.0, 이유: 절대상승추세(종가>MA20·종가>MA60·MA20>MA60·60일수익>0))
2026-09-14 09:04:48 | trading_context | INFO | 매수 판단 스킵: 시장급락 (KOSPI -3.36% (임계값: -2.5%))
2026-09-14 09:04:50 | strategy.RSLeaderStrategy | INFO | 🧾 [PAPER] 매수 시그널: 111111 @ 1,000 (추천 3000주) | 절대상승추세(종가>MA20·종가>MA60·MA20>MA60·60일수익>0)
2026-09-14 09:04:51 | strategy.RSLeaderStrategy | INFO | [on_tick] 매수검토 10종목(스킵 0), 신호 1건 | 매도검토 44종목, 신호 0건
2026-09-14 09:05:10 | trading_context | INFO | 매수 판단 스킵: 시장급락 (KOSPI -3.36% (임계값: -2.5%))
2026-09-14 09:09:22 | strategy.MinerviniVolumeDryupStrategy | INFO | 🧾 [PAPER] 매수 시그널: 317400 @ 10,000 (추천 300주) | volume_dryup recent/base=0.64 ≤ 0.70
2026-09-14 09:09:22 | strategy.MinerviniVolumeDryupStrategy | INFO | [on_tick] 매수신호: 317400(BUY, 신뢰도 58.0, 이유: volume_dryup recent/base=0.64 ≤ 0.70)
2026-09-14 09:09:22 | core.trading_decision_engine | INFO | [시장방향성필터] 관측 지수=KOSPI 코드=0001 등락률=-2.17% 임계값=-2.5% 판정=허용
2026-09-14 09:09:22 | bot.trading_analyzer | INFO | 보유 중인 종목 매수 신호 무시: 317400(317400)
2026-09-14 09:09:30 | strategy.MinerviniVolumeDryupStrategy | INFO | [on_tick] 매수검토 6종목(스킵 0), 신호 1건 | 매도검토 45종목, 신호 0건
2026-09-14 09:10:13 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수신호: 209640(BUY, 신뢰도 68.0, 이유: breakout_prev_high close=3820.00 prior20_high=3245.00 vol=6496084/72684)
2026-09-14 09:10:13 | core.trading_decision_engine | INFO | 가상매수: 209640 177주 @3,695 (익절:10.0% 손절:10.0%)
2026-09-14 09:10:13 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수신호: 072990(BUY, 신뢰도 68.0, 이유: breakout_prev_high close=3210.00 prior20_high=3150.00 vol=1233796/16707)
2026-09-14 09:10:13 | trading_context | INFO | [진입억제] 072990 매수 스킵 — 쿨다운 59초 남음 (마지막 진입 0초 전)
2026-09-14 09:10:14 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수검토 10종목(스킵 0), 신호 2건 | 매도검토 45종목, 신호 0건
2026-09-14 09:18:37 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수신호: 072990(BUY, 신뢰도 68.0, 이유: breakout_prev_high close=3210.00 prior20_high=3150.00 vol=1233796/16707)
2026-09-14 09:18:37 | bot.trading_analyzer | INFO | [매수거절] 072990 수량부족
2026-09-14 09:18:38 | strategy.DayTrading3MethodsBreakoutStrategy | INFO | [on_tick] 매수검토 10종목(스킵 0), 신호 1건 | 매도검토 46종목, 신호 0건
2026-09-14 09:20:19 | strategy.BookPullbackMa5Strategy | INFO | [on_tick] 매수신호: 162300(BUY, 신뢰도 68.0, 이유: ma5_pullback ma5=2731.00 low=2770.00 close=2860.00)
2026-09-14 09:20:19 | core.virtual_trading_manager | WARNING | ⚠️ 전략 가상 잔고 부족 [book_pullback_ma5]: 1,543,108원 < 1,543,131원
2026-09-14 09:20:19 | bot.trading_analyzer | WARNING | 162300 가상 매수 미체결 — 예약 취소 (유령 체결 방지)
2026-09-14 09:20:20 | strategy.BookPullbackMa5Strategy | INFO | [on_tick] 매수검토 10종목(스킵 0), 신호 1건 | 매도검토 46종목, 신호 0건
2026-09-14 09:30:00 | trading_context | INFO | 매수 판단 스킵: 시장급락 (KOSPI -3.10% (임계값: -2.5%)) 종목=005930 전략=book_pullback_ma20 해석지수=KOSPI
2026-09-14 09:31:00 | strategy.BookPullbackMa20Strategy | INFO | [캡] book_pullback_ma20 317400 평가 스킵 사유=timeframe 보유=6/10 일일매수=1/5
2026-09-14 09:31:01 | strategy.BookPullbackMa20Strategy | INFO | [캡] book_pullback_ma20 232140 평가 스킵 사유=max_positions 보유=5/5 일일매수=0/5
2026-09-14 09:40:00 | strategy.ElderEmaPullbackStrategy | INFO | [on_tick] 매수신호: 000810(BUY, 신뢰도 60.0, 이유: triple_screen_ema_pullback low=1<=ema13*1.02 close=2>ema13=1)
2026-09-14 09:40:00 | trading_context | INFO | 매수스톱 미도달 스킵: 000810 (현재가 660,000 < 매수스톱 683,000)
2026-09-14 09:41:00 | strategy.ElderEmaPullbackStrategy | INFO | [on_tick] 매수신호: 012450(BUY, 신뢰도 60.0, 이유: triple_screen_ema_pullback low=1<=ema13*1.02 close=2>ema13=1)
2026-09-14 09:41:00 | trading_context | INFO | 매수 차단: 상한가 접근 (현재가 13,000 / 전일종가 10,000 = +30.0%)
2026-09-14 09:42:00 | strategy.ElderEmaPullbackStrategy | INFO | [on_tick] 매수신호: 005380(BUY, 신뢰도 60.0, 이유: triple_screen_ema_pullback low=1<=ema13*1.02 close=2>ema13=1)
2026-09-14 09:42:00 | trading_context | WARNING | 매수 차단: 일일 손실 한도 초과 (누적손실 1,000,000원 / 한도 10.0%)
"""


def _dir(tmp_path, text=LOG):
    (tmp_path / "robotrader_template_20260914_074007.log").write_text(text, encoding="utf-8")
    return tmp_path


def _scan(tmp_path):
    return L.scan_day(_dir(tmp_path), D, R.ALL_FOLDERS, R.LOGGER_TO_FOLDER)


def test_startup_lines(tmp_path):
    dl = _scan(tmp_path)
    assert dl.found and dl.rs_mode == "shadow"
    assert dl.get("rs_leader").restore_n == 10 and dl.get("book_pullback_ma5").restore_n == 0
    assert dl.get("book_pullback_ma20").per_stock["new"] == 864_374


def test_candidate_block(tmp_path):
    rs = _scan(tmp_path).get("rs_leader")
    assert rs.e6 == dict(secured=10, snapshot=20, target=10, d1="2026-09-11", time="09:00:51")
    assert rs.excluded == ["006490"] and rs.sector_mode == "shadow"
    deep = _scan(tmp_path).get("deep_mr_dev20")
    assert deep.e6_zero and deep.e6["target"] == 0


def test_buy_signal_excludes_sell_loop_receipts(tmp_path):
    rs = _scan(tmp_path).get("rs_leader")
    assert set(rs.buysig) == {"060570"}                    # 매도 루프 🧾(111111)은 신호가 아니다
    assert set(rs.receipt) == {"060570", "111111"}          # 🧾 는 기준가 대조용으로만 모은다
    assert rs.buysig["060570"].detail["reasons"].startswith("절대상승추세(")
    assert rs.receipt["060570"].detail["ref"] == 5040.0 and rs.ontick_runs == 1
    assert rs.ontick_times == ["09:04:51"]                  # on_tick 1회 «완료» 시각(빈자리 구간 판정용)


def test_codeless_crash_line_goes_to_preceding_signal(tmp_path):
    dl = _scan(tmp_path)
    assert dl.get("rs_leader").gates_for("060570") == {L.G_CRASH: dl.get("rs_leader").gates[("060570", L.G_CRASH)]}
    assert dl.unattributed.get(L.G_CRASH) == 1               # 매수검토 줄 뒤(09:05:10)의 줄은 귀속 불가
    three_field = dl.get("book_pullback_ma20").gates[("005930", L.G_CRASH)]
    assert three_field.n == 1                                 # 09-16~ 3필드 줄은 줄 안의 전략·종목으로


def test_held_any_throttle_qty_balance_buystop_limitup(tmp_path):
    dl = _scan(tmp_path)
    assert ("317400", L.G_HELD_ANY) in dl.get("minervini_volume_dryup").gates
    day = dl.get("daytrading_3methods_breakout")
    assert ("072990", L.G_THROTTLE) in day.gates and ("072990", L.G_QTY) in day.gates
    assert day.buysig["072990"].n == 2 and day.buysig["072990"].first == "09:10:13"
    ma5 = dl.get("book_pullback_ma5")
    assert ("162300", L.G_BALANCE) in ma5.gates and ("162300", L.G_UNFILLED) in ma5.gates
    elder = dl.get("elder_ema_pullback")
    assert ("000810", L.G_BUYSTOP) in elder.gates and ("012450", L.G_LIMITUP) in elder.gates
    assert ("005380", L.G_DAILY_LOSS) in elder.gates          # [합성] 종목 칸 없는 WARNING → 직전 매수신호


def test_fill_line_attributed_with_tp_sl(tmp_path):
    f = _scan(tmp_path).get("daytrading_3methods_breakout").fills["209640"]
    assert f.detail == dict(qty=177, price=3695.0, tp_pct=10.0, sl_pct=10.0)


def test_cap_blocking_drops_timeframe(tmp_path):
    ma20 = _scan(tmp_path).get("book_pullback_ma20")
    assert ma20.cap_blocking("317400") == {}
    assert set(ma20.cap_blocking("232140")) == {"max_positions"}


def test_market_direction_series(tmp_path):
    dl = _scan(tmp_path)
    assert dl.index_state("KOSPI", "09:02:00") == "차단"
    assert dl.index_state("KOSPI", "09:00:30") == "차단"     # 첫 관측 전이면 그날 첫 관측
    assert dl.index_state("KOSDAQ", "09:02:00") == "허용"
    assert dl.first_verdict_after("KOSPI", "09:02:00", "허용") == "09:09:22"
    assert dl.index_state("NONE", "09:02:00") == ""


def test_parse_gate_crash_forms():
    old = L.parse_gate("매수 판단 스킵: 시장급락 (KOSPI -3.45% (임계값: -2.5%))")
    new = L.parse_gate("매수 판단 스킵: 시장급락 (KOSPI -3.1% (임계값: -2.5%)) 종목=005930 전략=rs_leader 해석지수=KOSPI")
    assert (old.gate, old.code, old.owner) == (L.G_CRASH, None, None)
    assert (new.gate, new.code, new.owner) == (L.G_CRASH, "005930", "rs_leader")


def test_reject_gate_mapping():
    assert L.reject_gate("수량부족") == L.G_QTY
    assert L.reject_gate("진입가 밴드 이탈 — 스킵 (현재가 1 > 상한 0)") == L.G_BAND_ABOVE
    assert L.reject_gate("진입가 밴드 하회 — 스킵 (현재가 0 < 하한 1)") == L.G_BAND_BELOW
    assert L.reject_gate("현재가 미확보 — 진입 보류") == L.G_NO_PRICE
    assert L.reject_gate("데이터부족") == L.G_REJECT_OTHER


def test_live_candidate_list_main_ext(tmp_path):
    rs = _scan(tmp_path).get("rs_leader")
    snap = ["006490"] + [f"{i:06d}" for i in range(1, 20)]
    cl = L.live_candidate_list(snap, rs)
    assert cl.main == [f"{i:06d}" for i in range(1, 11)] and cl.ext == [f"{i:06d}" for i in range(11, 20)]
    assert cl.src == "log" and cl.target == 10


def test_missing_file(tmp_path):
    dl = L.scan_day(tmp_path, D, R.ALL_FOLDERS, R.LOGGER_TO_FOLDER)
    assert not dl.found and dl.get("rs_leader").e6 is None
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_logscan8.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: ... 'StratDay' object has no attribute 'buysig'` 등(초안에는 신호 기준 줄·게이트 귀속이 없다).

- [ ] **Step 3: `logscan8.py` 전면 교체**

```python
"""라이브 로그 읽기(읽기 전용 · 8전략 동시) — `robotrader_template_YYYYMMDD_*.log`.

콘솔 캡처 파일은 `trading_*.log` 의 **상위집합**이다. 파일 한 번 순회로 8전략 것을 전부 모은다.
봇은 전략을 «하나씩» 돈다(main.py:465-493 라운드로빈 · `await strat.on_tick(ctx)`) ⇒ 한 전략의
`[on_tick] 매수신호: CODE(` 줄(strategies/base.py:723-726) 바로 뒤의 매수 실행 경로 줄은 그 (전략, 종목)의 것이다.

뽑는 계기 (2026-09-19 로그·코드 실측)
────────────────────────────────────
| 키 | 원본 줄 | 생산자 |
|---|---|---|
| `e6`·`e6_zero` | `[E6] <전략>: screener_snapshots N건 확보 (…)` · `… 0건 (D-1=…)` | core/candidate_selector.py:1098-1101·1137-1140 |
| `excluded` | `후보 제외: CODE(NAME) — 사유` — 다음 E6 확보 줄의 전략 몫 | candidate_selector 안전필터 |
| `sector_mode` | `[섹터뉴스] <전략> mode=shadow …` (shadow 면 순서 불변) | candidate_selector 재정렬 |
| `buysig` 🔑 | `[on_tick] 매수신호: CODE(BUY, 신뢰도 x, 이유: …)` — **매수 루프 전용 = 신호 기준** | base.py:723-726 |
| `ontick_times` | `[on_tick] 매수검토 N종목(스킵 k), 신호 m건 | …` 시각 — 그 전략 on_tick 1회 «완료»(빈자리 구간 판정) | base.py:763-766 |
| `receipt` | `🧾 [PAPER] 매수 시그널: CODE @ REF (…추천 Q주) | 사유` — 매도 루프 줄 섞임 ⇒ 기준가 대조용 | 각 전략 `_check_buy` |
| `cap` | `[캡] <전략> CODE 평가 스킵 사유=R 보유=n/K 일일매수=d/M` — `timeframe` 은 매수 차단 아님 | base.py:576-605 |
| `nosignal` | `[신호없음] CODE: …` | base.py on_tick · rs_leader corp_action |
| `gates` | 아래 매수 실행 경로 줄 — 직전 `[on_tick] 매수신호` 의 (전략, 종목)에 귀속 | trading_context · trading_analyzer · decision_engine · VTM |
| `fills` | `가상매수: CODE Q주 @P (익절:x% 손절:y%)` | core/trading_decision_engine.py:698-701 |
| `per_stock` | `종목당 투자금액 재산정: <전략> A원 → B원 (자본 …, 기준 …원)` | core/virtual_trading_manager.py:300-361 |
| `restore_n` | `[진단] 런타임 포지션 엔트리 … 소유자별 {…}` | bot/state_restorer.py |
| `market_dir` | `[시장방향성필터] 관측 지수=X … 판정=차단|허용` — 급락게이트 시간선 | core/trading_decision_engine.py:210-218 |
| `rs_mode` | `[rs-corp-action] mode=… (startup)` | strategies/rs_leader/strategy.py:85 |

매수 실행 경로 게이트 (core/trading_context.py:313-539 → bot/trading_analyzer.py:103-186 → 엔진 → VTM)
| 게이트 | 줄 | 종목 칸 |
|---|---|---|
| market_crash | `매수 판단 스킵: 시장급락 (…)` (+ `종목= 전략= 해석지수=` 는 2026-09-16~) | 09-15 이전 없음 → 직전 매수신호에 귀속 |
| regime_gate | `매수 판단 스킵: 국면게이트 (…)` | 없음 |
| owned_other | `매수 거부: CODE는 이미 OWNER 소유 …` | 있음 |
| buy_stop | `매수스톱 미도달 스킵: CODE (…)` | 있음 |
| limit_up | `매수 차단: 상한가 접근 (…)` | 없음 |
| daily_loss | `매수 차단: 일일 손실 한도 초과 (…)` (WARNING · core/trading_context.py:428-436) | 없음 |
| throttle | `[진입억제] CODE 매수 스킵 — 쿨다운|이번 사이클 …` | 있음 |
| held_any | `보유 중인 종목 매수 신호 무시: CODE(NAME)` — 어느 전략이든 보유 | 있음 |
| band_above·band_below·qty_short·no_price·reject_other | `[매수거절] CODE 사유` | 있음 |
| balance_short | VTM `전략 가상 잔고 부족 [전략]` | 없음(전략만) |
| unfilled | `CODE 가상 매수 미체결 — 예약 취소` | 있음 |

🔴 주의
1. 불가능봉(`strategies/_rule_screener_base.py:180`)·rs `— 후보 제외 (mode=live)`(rs_leader/screener.py:151) 줄은 콜론형
   `후보 제외:` 가 아니다. 스크리너 훅이 D 09:00 에 scan_date=D-1 스냅샷을 쓰면서 이미 뺀 종목이라 E6 목록을 다시
   줄일 필요가 없다(검증표 #17 — 이유 정정).
2. 귀속 못 한 게이트 줄은 버리지 않고 `DayLog.unattributed` 에 센다.
3. 봇 가동 중엔 콘솔 캡처가 블록 버퍼링돼 당일 파일이 덜 써져 있을 수 있다.
4. 창 안 0건이라 실측 표본이 없는 줄(`국면게이트`·`매수 거부`·`상한가 접근`·`이번 사이클`·`일일 손실 한도`)은 코드 문자열로 정규식을 적었다.
5. VI 매수 보류(`{code} 매수 스킵: VI 발동 중` · trading_context.py:424-426)와 25분 매수 쿨다운(trading_analyzer.py:132-136)은 DEBUG 라 로그 파일에 없다.

접기 — 행 단위는 «평가 1회»가 아니라 `(날짜, 전략, 종목, 계기)` 이고 `n`·`first`·`last` 로 접는다.
"""
from __future__ import annotations

import ast
import glob
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TS = r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \| (\S+) \| (\w+) \| "
RE_LINE = re.compile(_TS + r"(.*)$")

# ── 후보 블록 ──
RE_E6_BOUNDARY = re.compile(r"\[E6\] (\S+): 후보 \d+종목")
RE_E6_OK = re.compile(r"\[E6\] (\S+): screener_snapshots (\d+)건 확보 "
                      r"\(스냅샷 (\d+)건, 목표 (\d+)건, D-1=(\d{4}-\d{2}-\d{2})\)")
RE_E6_ZERO = re.compile(r"\[E6\] (\S+): screener_snapshots 0건 \(D-1=(\d{4}-\d{2}-\d{2})\)")
RE_EXCLUDED = re.compile(r"후보 제외: (\w{6})\(")
RE_SECTOR = re.compile(r"\[섹터뉴스\] (\S+) mode=(\w+)")
# ── 기동 ──
RE_RESTORE = re.compile(r"\[진단\] 런타임 포지션 엔트리 .*?소유자별 (\{.*?\})")
RE_RECALC = re.compile(r"종목당 투자금액 재산정: (\S+) ([\d,]+)원 → ([\d,]+)원 "
                       r"\(자본 ([\d,]+)/([\d,]+) = ([\d.]+), 기준 ([\d,]+)원\)")
RE_RS_MODE = re.compile(r"\[rs-corp-action\] mode=(\w+) \(startup\)")
RE_MKT_DIR = re.compile(r"\[시장방향성필터\] 관측 지수=(\w+) 코드=\w+ 등락률=([+-]?[\d.]+)% "
                        r"임계값=([+-]?[\d.]+)% 판정=(\S+)")
# ── 전략 로거(strategy.<Cls>) ──
RE_BUYSIG = re.compile(r"\[on_tick\] 매수신호: (\w{6})\((\w+), 신뢰도 ([\d.]+), 이유: (.*)\)$")
RE_ONTICK_SUMMARY = re.compile(r"\[on_tick\] 매수검토 (\d+)종목\(스킵 (\d+)\), 신호 (\d+)건")
# 두 형식:  "… @ 12,345 (추천 8주)"  ·  "… @ 12,345 (매수스톱 12,900, 추천 7주)"
RE_RECEIPT = re.compile(r"매수 시그널: (\w{6}) @ ([\d,]+) \(.*?추천 (\d+)주\)(?: \| (.*))?$")
RE_CAP = re.compile(r"\[캡\] (\S+) (\w{6}) 평가 스킵 사유=(\w+) 보유=(\d+)/(\d+) 일일매수=(\d+)/(\d+)")
RE_NOSIG = re.compile(r"\[신호없음\] (\w{6}): (.*)$")
# ── 매수 실행 경로 ──
RE_CRASH = re.compile(r"매수 판단 스킵: 시장급락 \((.*)\)(?: 종목=(\w{6}) 전략=(\S+) 해석지수=(\S+))?$")
RE_HELD_ANY = re.compile(r"보유 중인 종목 매수 신호 무시: (\w{6})\(")
RE_OWNED = re.compile(r"매수 거부: (\w{6})는 이미 (\S+) 소유")
RE_BUYSTOP = re.compile(r"매수스톱 미도달 스킵: (\w{6}) ")
RE_LIMITUP = re.compile(r"매수 차단: 상한가 접근")
RE_DAILY_LOSS = re.compile(r"매수 차단: 일일 손실 한도 초과")
RE_THROTTLE = re.compile(r"\[진입억제\] (\w{6}) 매수 스킵 — (?:쿨다운|이번 사이클)")
RE_REJECT = re.compile(r"\[매수거절\] (\w{6}) (.*)$")
RE_BAL_SHORT = re.compile(r"전략 가상 잔고 부족 \[(\S+)\]")
RE_UNFILLED = re.compile(r"(\w{6}) 가상 매수 미체결")
RE_FILL = re.compile(r"가상매수: (\w{6}) (\d+)주 @([\d,]+) \(익절:([\d.]+)% 손절:([\d.]+)%\)")

G_CRASH = "market_crash"
G_REGIME = "regime_gate"
G_HELD_ANY = "held_any"
G_OWNED = "owned_other"
G_BUYSTOP = "buy_stop"
G_LIMITUP = "limit_up"
G_THROTTLE = "throttle"
G_BAND_ABOVE = "band_above"
G_BAND_BELOW = "band_below"
G_QTY = "qty_short"
G_BALANCE = "balance_short"
G_NO_PRICE = "no_price"
G_UNFILLED = "unfilled"
G_REJECT_OTHER = "reject_other"
G_DAILY_LOSS = "daily_loss"
G_FILL = "fill"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


@dataclass
class Fold:
    """(전략, 종목, 계기) 하나에 대한 접힌 관측."""
    n: int = 0
    first: str = ""
    last: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def hit(self, hhmmss: str, **detail: Any) -> None:
        self.n += 1
        if not self.first:
            self.first = hhmmss
            self.detail.update(detail)     # 첫 줄의 값을 대표로 둔다
        self.last = hhmmss


@dataclass
class StratDay:
    """한 전략의 하루치 로그 관측."""
    e6: Optional[Dict[str, Any]] = None
    e6_zero: bool = False
    excluded: List[str] = field(default_factory=list)
    sector_mode: str = ""
    buysig: Dict[str, Fold] = field(default_factory=dict)
    receipt: Dict[str, Fold] = field(default_factory=dict)
    cap: Dict[Tuple[str, str], Fold] = field(default_factory=dict)
    nosignal: Dict[str, Fold] = field(default_factory=dict)
    gates: Dict[Tuple[str, str], Fold] = field(default_factory=dict)
    fills: Dict[str, Fold] = field(default_factory=dict)
    ontick_times: List[str] = field(default_factory=list)   # `[on_tick] 매수검토` 줄 시각 = on_tick 1회 «완료»
    restore_n: Optional[int] = None
    per_stock: Optional[Dict[str, Any]] = None

    @property
    def ontick_runs(self) -> int:
        return len(self.ontick_times)

    def cap_blocking(self, code: str) -> Dict[str, Fold]:
        """«매수 차단» `[캡]` 사유만 — `timeframe` 은 position_monitor 분봉 경로라 뺀다."""
        return {r: f for (c, r), f in self.cap.items() if c == code and r != "timeframe"}

    def gates_for(self, code: str) -> Dict[str, Fold]:
        return {g: f for (c, g), f in self.gates.items() if c == code}


@dataclass
class DayLog:
    d: date
    files: List[str] = field(default_factory=list)
    by_strategy: Dict[str, StratDay] = field(default_factory=lambda: OrderedDict())
    owner_counts: Dict[str, int] = field(default_factory=dict)
    rs_mode: str = ""
    market_dir: List[Tuple[str, str, str]] = field(default_factory=list)   # (hhmmss, 지수, 판정)
    unattributed: Dict[str, int] = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return bool(self.files)

    def get(self, folder: str) -> StratDay:
        return self.by_strategy.setdefault(folder, StratDay())

    def index_state(self, index: str, hhmmss: str) -> str:
        """그 시각 `index` 급락게이트 판정 — 그 시각 이전 마지막 관측, 없으면 그날 첫 관측. 관측 0 이면 ''."""
        obs = [(t, v) for t, i, v in self.market_dir if i == index]
        if not obs:
            return ""
        before = [v for t, v in obs if t <= hhmmss]
        return before[-1] if before else obs[0][1]

    def first_verdict_after(self, index: str, hhmmss: str, verdict: str) -> str:
        for t, i, v in self.market_dir:
            if i == index and t > hhmmss and v == verdict:
                return t
        return ""


@dataclass
class GateHit:
    gate: str
    code: Optional[str] = None
    owner: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)


def reject_gate(text: str) -> str:
    """`[매수거절] CODE 사유` 의 사유 → 게이트(엔진 문자열 core/trading_decision_engine.py:356-430)."""
    t = text.strip()
    if t.startswith("수량부족"):
        return G_QTY
    if "밴드 이탈" in t:
        return G_BAND_ABOVE
    if "밴드 하회" in t:
        return G_BAND_BELOW
    if "시장급락" in t:
        return G_CRASH
    if "현재가 미확보" in t:
        return G_NO_PRICE
    return G_REJECT_OTHER


def parse_gate(msg: str) -> Optional[GateHit]:
    """매수 실행 경로 줄이면 GateHit, 아니면 None."""
    if "매수 판단 스킵: 시장급락" in msg:
        mc = RE_CRASH.search(msg)
        return GateHit(G_CRASH, mc.group(2) if mc else None, mc.group(3) if mc else None)
    if "매수 판단 스킵: 국면게이트" in msg:
        return GateHit(G_REGIME)
    for rx, gate in ((RE_HELD_ANY, G_HELD_ANY), (RE_OWNED, G_OWNED), (RE_BUYSTOP, G_BUYSTOP),
                     (RE_THROTTLE, G_THROTTLE), (RE_UNFILLED, G_UNFILLED)):
        mm = rx.search(msg)
        if mm:
            return GateHit(gate, mm.group(1))
    if RE_LIMITUP.search(msg):
        return GateHit(G_LIMITUP)
    if RE_DAILY_LOSS.search(msg):
        return GateHit(G_DAILY_LOSS)
    mr = RE_REJECT.search(msg)
    if mr:
        return GateHit(reject_gate(mr.group(2)), mr.group(1))
    mb = RE_BAL_SHORT.search(msg)
    if mb:
        return GateHit(G_BALANCE, None, mb.group(1))
    mf = RE_FILL.search(msg)
    if mf:
        return GateHit(G_FILL, mf.group(1), None, dict(qty=int(mf.group(2)), price=_num(mf.group(3)),
                                                      tp_pct=float(mf.group(4)), sl_pct=float(mf.group(5))))
    return None


def attribute(g: GateHit, pending: Optional[Tuple[str, str]],
              last_owner: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """(전략, 종목). 3필드 줄은 줄 안 값 · 종목 없는 줄은 직전 매수신호 · 종목 있는 줄은 직전 매수신호가
    같은 종목이면 그 전략, 아니면 그 종목의 마지막 매수신호 전략."""
    if g.code is not None and g.owner is not None:
        return g.owner, g.code
    if g.code is None:
        if pending is None:
            return None, None
        if g.owner is not None and g.owner != pending[0]:
            return None, None
        return pending
    if pending is not None and pending[1] == g.code:
        return pending[0], g.code
    return last_owner.get(g.code), g.code


def _scan_candidate_block(out: DayLog, known: set, msg: str, t: str, pending_excl: List[str]) -> bool:
    if "[E6]" in msg:
        if RE_E6_BOUNDARY.search(msg):
            pending_excl.clear()
            return True
        mo = RE_E6_OK.search(msg)
        if mo and mo.group(1) in known:
            sd = out.get(mo.group(1))
            if sd.e6 is None:
                sd.e6 = dict(secured=int(mo.group(2)), snapshot=int(mo.group(3)), target=int(mo.group(4)),
                             d1=mo.group(5), time=t)
                sd.excluded = list(pending_excl)
            return True
        mz = RE_E6_ZERO.search(msg)
        if mz and mz.group(1) in known:
            sd = out.get(mz.group(1))
            sd.e6_zero = True
            if sd.e6 is None:
                sd.e6 = dict(secured=0, snapshot=0, target=0, d1=mz.group(2), time=t)
                sd.excluded = list(pending_excl)
        return True
    if "후보 제외:" in msg:
        mx = RE_EXCLUDED.search(msg)
        if mx:
            pending_excl.append(mx.group(1))
        return True
    if "[섹터뉴스]" in msg:
        ms = RE_SECTOR.search(msg)
        if ms and ms.group(1) in known and not out.get(ms.group(1)).sector_mode:
            out.get(ms.group(1)).sector_mode = ms.group(2)
        return True
    return False


def _scan_startup(out: DayLog, known: set, msg: str, t: str) -> bool:
    if "런타임 포지션 엔트리" in msg:
        mr = RE_RESTORE.search(msg)
        if mr and not out.owner_counts:
            try:
                owners = ast.literal_eval(mr.group(1))
                out.owner_counts = {str(k): int(v) for k, v in owners.items()}
                for f_ in known:
                    out.get(f_).restore_n = out.owner_counts.get(f_, 0)
            except (ValueError, SyntaxError):
                pass
        return True
    if "종목당 투자금액 재산정" in msg:
        mr = RE_RECALC.search(msg)
        if mr and mr.group(1) in known:
            out.get(mr.group(1)).per_stock = dict(
                old=_num(mr.group(2)), new=_num(mr.group(3)), capital=_num(mr.group(4)),
                initial=_num(mr.group(5)), ratio=float(mr.group(6)), base=_num(mr.group(7)), time=t)
        return True
    if "[rs-corp-action] mode=" in msg:
        mm = RE_RS_MODE.search(msg)
        if mm and not out.rs_mode:
            out.rs_mode = mm.group(1)
        return True
    if "[시장방향성필터] 관측 지수" in msg:
        md = RE_MKT_DIR.search(msg)
        if md:
            out.market_dir.append((t, md.group(1), md.group(4)))
        return True
    return False


def _scan_strategy_line(sd: StratDay, folder: str, msg: str, t: str,
                        pending: Optional[Tuple[str, str]], last_owner: Dict[str, str]
                        ) -> Optional[Tuple[str, str]]:
    """전략 로거 줄 하나를 반영하고 새 pending 을 돌려준다."""
    if "[on_tick] 매수신호" in msg:
        mb = RE_BUYSIG.search(msg)
        if mb:
            code = mb.group(1)
            sd.buysig.setdefault(code, Fold()).hit(t, signal_type=mb.group(2), confidence=float(mb.group(3)),
                                                   reasons=mb.group(4))
            last_owner[code] = folder
            return (folder, code)
        return pending
    if "[on_tick] 매수검토" in msg:
        if RE_ONTICK_SUMMARY.search(msg):
            sd.ontick_times.append(t)
        return None
    if "매수 시그널:" in msg:
        ms = RE_RECEIPT.search(msg)
        if ms:
            sd.receipt.setdefault(ms.group(1), Fold()).hit(t, ref=_num(ms.group(2)), qty=int(ms.group(3)),
                                                           reasons=(ms.group(4) or "")[:200])
    elif "[캡]" in msg:
        mc = RE_CAP.search(msg)
        if mc and mc.group(1) == folder:
            sd.cap.setdefault((mc.group(2), mc.group(3)), Fold()).hit(
                t, held=int(mc.group(4)), k=int(mc.group(5)), daily=int(mc.group(6)), mdt=int(mc.group(7)))
    elif "[신호없음]" in msg:
        mn = RE_NOSIG.search(msg)
        if mn:
            sd.nosignal.setdefault(mn.group(1), Fold()).hit(t, msg=mn.group(2)[:120])
    return pending


def scan_day(log_dir: Path, d: date, folders: Sequence[str], logger_to_folder: Dict[str, str]) -> DayLog:
    """하루치 로그를 한 번 순회해 전 전략 관측을 모은다."""
    out = DayLog(d)
    for f in folders:
        out.get(f)
    paths = sorted(glob.glob(str(Path(log_dir) / f"robotrader_template_{d:%Y%m%d}_*.log")))
    out.files = [Path(p).name for p in paths]
    known = set(folders)
    day_prefix = f"{d:%Y-%m-%d}"
    for p in paths:
        pending_excl: List[str] = []
        pending: Optional[Tuple[str, str]] = None
        last_owner: Dict[str, str] = {}
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.startswith(day_prefix):
                    continue
                m = RE_LINE.match(line.rstrip("\n"))
                if not m:
                    continue
                _, t, logger, _lvl, msg = m.groups()
                if _scan_candidate_block(out, known, msg, t, pending_excl):
                    continue
                if _scan_startup(out, known, msg, t):
                    continue
                folder = logger_to_folder.get(logger)
                if folder in known:
                    pending = _scan_strategy_line(out.get(folder), folder, msg, t, pending, last_owner)
                    continue
                g = parse_gate(msg)
                if g is None:
                    continue
                owner, code = attribute(g, pending, last_owner)
                if owner in known and code:
                    sd = out.get(owner)
                    if g.gate == G_FILL:
                        sd.fills.setdefault(code, Fold()).hit(t, **g.detail)
                    else:
                        sd.gates.setdefault((code, g.gate), Fold()).hit(t, text=msg[:120])
                else:
                    out.unattributed[g.gate] = out.unattributed.get(g.gate, 0) + 1
    return out


@dataclass
class CandList:
    main: List[str]
    ext: List[str]
    target: int
    src: str


def live_candidate_list(snapshot_codes: Sequence[str], sd: StratDay, default_target: int = 10) -> CandList:
    """라이브 E6 목록 재구성 = 스냅샷 순위순 − 안전필터 제외 → 앞에서 «목표» 개수
    (core/candidate_selector.py:1104-1141). 안전필터는 «지연»이다(limit=max_candidates) — 목표만큼 모이면
    멈추므로 제외 줄은 main 구간에서만 나온다 ⇒ ext(나머지 = 스냅샷 T+1~20위)는 안전필터 미검사.
    """
    if sd.e6 is not None:
        target, src = int(sd.e6["target"]), "log"
    else:
        target, src = default_target, "no_e6_log(default)"
    excl = set(sd.excluded)
    kept = [c for c in snapshot_codes if c not in excl]
    main, ext = kept[:target], kept[target:]
    if sd.e6 is not None and len(main) != sd.e6["secured"]:
        src += f"·count_mismatch(recon {len(main)} vs log {sd.e6['secured']})"
    if sd.sector_mode and sd.sector_mode != "shadow":
        src += f"·sector_mode={sd.sector_mode}(순서 재정렬 가능)"
    return CandList(main, ext, target, src)
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_logscan8.py -q -p no:cacheprovider`
Expected: PASS(13 passed).

- [ ] **Step 5: 실제 로그로 건수 대조(읽기 전용 · 라이브 로그 폴더)**

Run:
```bash
$PY - <<'PY'
from datetime import date
from pathlib import Path
from backtest.concept_axes.ledger8 import logscan8 as L, registry as R
LOG = Path("D:/GIT/kis-trading-template/RoboTrader_template/logs")
for d in [date(2026, 9, x) for x in (10, 11, 14, 15, 16, 17, 18)]:
    dl = L.scan_day(LOG, d, R.ALL_FOLDERS, R.LOGGER_TO_FOLDER)
    crash = sum(f.n for sd in dl.by_strategy.values() for (c, g), f in sd.gates.items() if g == L.G_CRASH)
    held = sum(f.n for sd in dl.by_strategy.values() for (c, g), f in sd.gates.items() if g == L.G_HELD_ANY)
    print(d, "files", len(dl.files), "crash귀속", crash, "unattr", dl.unattributed, "held_any", held,
          "buysig", {f[:6]: len(sd.buysig) for f, sd in dl.by_strategy.items()})
PY
```
Expected: 7일 모두 `files 1`. `crash귀속 + unattr[market_crash]` = 09-11 196 · 09-14 713(`grep -c "매수 판단 스킵: 시장급락"` 과 같아야 함). 09-18 `held_any` = 125. `unattr` 가 크면(귀속률 < 90%) 멈추고 원인 줄을 5개 보고. 참고값(계획 검증 실행): 7일 모두 `unattr {}` · crash 09-11 196 · 09-14 713 · held_any 09-17 2 · 09-18 125.

- [ ] **Step 6: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| #3 `[캡]` ∩ E6 · `timeframe` 제외 | `cap_blocking` · `test_cap_blocking_drops_timeframe` | [ ] |
| #4 신호 기준 줄 = `[on_tick] 매수신호: CODE(` · 🧾 는 보조 | `buysig`/`receipt` · `test_buy_signal_excludes_sell_loop_receipts` | [ ] |
| #16① 09-14 `종목=` 없는 시장급락 줄 | `attribute`(pending) · `test_codeless_crash_line_goes_to_preceding_signal` · Step 5 건수 | [ ] |
| #16② `보유 중인 종목 매수 신호 무시` | `G_HELD_ANY` · 테스트 · Step 5(09-18 125) | [ ] |
| #16③ 거절 줄 귀속을 🧾 가 아닌 매수신호로 | `attribute` · pending 은 `[on_tick] 매수신호`에서만 설정 | [ ] |
| #17 불가능봉·rs 제외 줄 비포착(이유 정정) | 독스트링 주의 1 · `RE_EXCLUDED` 콜론형 | [ ] |
| #18 섹터뉴스 모드 매일 파싱 | `sector_mode` · `live_candidate_list` src 표기 | [ ] |
| #12 per_stock 로그 파싱 | `per_stock` · `test_startup_lines` | [ ] |
| D3 시장급락 시간선 | `market_dir`·`index_state` · `test_market_direction_series` | [ ] |
| D1 main/ext | `CandList` · `test_live_candidate_list_main_ext` | [ ] |

- [ ] **Step 7: Commit**

```bash
git add backtest/concept_axes/ledger8/logscan8.py backtest/concept_axes/ledger8/tests/test_logscan8.py
git commit -F - <<'MSG'
feat(ledger8): 로그 스캐너 교체 — [on_tick] 매수신호 기준·게이트 귀속·시장방향성 시간선

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```


---

### Task 3: fidelity8(신호) + livesignal8 — 라이브 `_check_buy` 그대로

**Files:**
- Create: `backtest/concept_axes/ledger8/fidelity8.py`
- Create: `backtest/concept_axes/ledger8/livesignal8.py`
- Test: `backtest/concept_axes/ledger8/tests/test_fidelity8.py`, `backtest/concept_axes/ledger8/tests/test_livesignal8.py`

**Interfaces:**
- Consumes: `registry.spec · corp_action_mode_for · state_attrs · ALL_FOLDERS`(과제 1). 재사용 `cap_skip_ledger.sources._as_of` · `cap_skip_ledger.classify.{slot_windows_detail, classify_candidate, open_at, fmt_windows, Trade, STATE_*}`(순수). 라이브 룰 클래스 `rule_breakout_prev_high`·`rule_volume_dryup`(기본 문턱만 읽음).
- Produces:
  - `fidelity8.SIG_AGREE_MIN=0.90 EXIT_REASON_MIN=0.70 FID_MIN_N=5` · `LOG_Y LOG_N LOG_NA` · `OUT_AGREE_Y OUT_AGREE_N OUT_REPLAY_ONLY OUT_LOG_ONLY OUT_NA`
  - `fidelity8.signal_log_state(buysig_seen: bool, ontick_ran: bool, evaluable: bool) -> str`
  - `fidelity8.decide_signal(replay: str, log: str) -> Tuple[str, str]`
  - `fidelity8.signal_outcome(replay: str, log: str) -> str`
  - `fidelity8.signal_table(rows, outcome_key="outcome") -> List[Dict[str, Any]]` (행 키: `strategy, mode, <outcome_key>, slot_state, reasons_equal, ref_equal` · 결과 키: `group n evaluable agree_Y agree_N replay_only log_only bought y_n y_rate n_n n_rate rate verdict verdict_note reasons_eq ref_eq`)
  - `fidelity8.SlotVerdict(state, state_v2, eval_v1, note)` · `fidelity8.slot_verdict(trades, d, k, mdt, code, list_order, ontick_times, first_tick=time(9,2)) -> SlotVerdict` · `EVALUABLE_STATES`
  - `fidelity8.day_volume_vintage(live_reasons, replay_reasons) -> Optional[float]` · `fidelity8.vintage_fragile(bias, signal, ratio, threshold, vmax) -> str`
  - `livesignal8.SignalEval8(folder, code, d, signal, reason, reasons_str, n_bars, last_bar, ref, band_min, band_max, confidence, detail)`
  - `livesignal8.load8(folder) -> BaseStrategy` · `state_snapshot(strategy, folder) -> tuple` · `live_buy_patches(strategy, folder, d)`(context manager)
  - `livesignal8.evaluate8(strategy, folder, code, d, data) -> SignalEval8`
  - `livesignal8.forced_band(strategy, folder, code, d, data) -> Optional[Tuple[Optional[float], Optional[float], Optional[float]]]` — (기준가, 밴드 하한, 밴드 상한)
  - `livesignal8.volume_margin(folder, data, ev) -> Optional[Tuple[float, float]]` — (비율, 문턱) · 상수 `DAY MIN VOLUME_RULE_BIAS`

- [ ] **Step 1: 전제 재확인 — envelope 자체 프레임 조회 경계(계획 작성 시 확인됨)**

Run: `grep -n "def get_daily_prices" -A 30 db/quant_daily_reader.py`
Expected: `db/quant_daily_reader.py:161-184` — `WHERE stock_code = %s AND date <= %s ORDER BY date DESC LIMIT %s`(end_date 포함 · `days` = 봉 수) · psycopg2(libpq ⇒ `PGOPTIONS` 읽기 전용 적용). `_fetch_entry_history`(book_envelope_200d/strategy.py:231-249)가 `now_kst().date()` 를 `end_date` 로 넘기고 그날 봉을 지우므로, 모듈 `now_kst` 를 D 09:02 로 패치하면 «D-1 까지 230봉»이다. 코드가 이와 다르면 멈추고 보고.

- [ ] **Step 2: 실패하는 테스트 작성**

`backtest/concept_axes/ledger8/tests/test_fidelity8.py`:
```python
"""fidelity8 — 신호 판정·방향별 집계·«평가 가능» 규칙(v1·v2·v3 · 반례)·빈티지 취약 표시(순수)."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backtest.concept_axes.ledger8 import fidelity8 as F
from backtest.concept_axes.minervini.cap_skip_ledger.classify import (STATE_BOUGHT, STATE_HELD, STATE_NO_SLOT,
                                                                      STATE_SLOT, Trade)


def test_signal_log_state():
    assert F.signal_log_state(True, False, False) == F.LOG_Y        # 줄이 있으면 무조건 Y
    assert F.signal_log_state(False, True, True) == F.LOG_N         # on_tick 돌았고 평가 가능했는데 줄 없음
    assert F.signal_log_state(False, True, False) == F.LOG_NA       # 보유·캡 — _check_buy 까지 못 갔을 수 있다
    assert F.signal_log_state(False, False, True) == F.LOG_NA       # 그날 on_tick 흔적 없음


def test_decide_signal_prefers_log():
    assert F.decide_signal("N", "Y") == ("Y", "log")
    assert F.decide_signal("Y", "N") == ("N", "log")
    assert F.decide_signal("Y", "NA") == ("Y", "replay")


def test_signal_outcome():
    assert F.signal_outcome("Y", "Y") == F.OUT_AGREE_Y
    assert F.signal_outcome("N", "N") == F.OUT_AGREE_N
    assert F.signal_outcome("Y", "N") == F.OUT_REPLAY_ONLY
    assert F.signal_outcome("N", "Y") == F.OUT_LOG_ONLY
    assert F.signal_outcome("Y", "NA") == F.OUT_NA


def _row(strategy, outcome, mode="", reasons_equal="", ref_equal="", slot_state=STATE_SLOT):
    return dict(strategy=strategy, mode=mode, outcome=outcome, reasons_equal=reasons_equal, ref_equal=ref_equal,
                slot_state=slot_state)


def test_signal_table_splits_directions():
    rows = ([_row("book_pullback_ma20", F.OUT_AGREE_Y, reasons_equal="Y", ref_equal="Y")] * 9
            + [_row("book_pullback_ma20", F.OUT_LOG_ONLY)]
            + [_row("daytrading_3methods_breakout", F.OUT_AGREE_N)] * 5
            + [_row("daytrading_3methods_breakout", F.OUT_REPLAY_ONLY)] * 2
            + [_row("book_envelope_200d", F.OUT_AGREE_Y, slot_state=STATE_BOUGHT)] * 6
            + [_row("rs_leader", F.OUT_NA, mode="live")] * 3)
    t = {g["group"]: g for g in F.signal_table(rows)}
    ma20 = t["book_pullback_ma20"]
    assert (ma20["y_n"], ma20["y_rate"], ma20["n_n"], ma20["n_rate"]) == (10, 0.9, 0, None)
    assert ma20["verdict"] == "ok" and "N 방향 판정 불가" in ma20["verdict_note"] and ma20["reasons_eq"] == 9
    day = t["daytrading_3methods_breakout"]
    assert day["n_rate"] == pytest.approx(5 / 7) and day["verdict"] == "LOW"            # N 방향 71% < 90%
    env = t["book_envelope_200d"]
    assert env["bought"] == 6 and env["evaluable"] == 6 and env["verdict"] == "ok"     # 전부 bought = 자명한 Y/Y
    assert t["rs_leader[live]"]["evaluable"] == 0 and t["rs_leader[live]"]["verdict"] == "판정 불가"


def test_signal_table_other_outcome_key():
    rows = [dict(strategy="a", mode="", outcome=F.OUT_NA, outcome_v1=F.OUT_AGREE_N, slot_state=STATE_SLOT)] * 5
    assert F.signal_table(rows)[0]["evaluable"] == 0
    assert F.signal_table(rows, outcome_key="outcome_v1")[0]["agree_N"] == 5


# ── «평가 가능» 규칙 — 반례: ma5 09-11 006910 형(빈자리 09:00:00~09:28:07 · 첫 신호 09:03:37) ──
D = date(2026, 9, 11)
UPPER = Trade(buy_id=1, code="A00001", buy_ts=datetime(2026, 9, 11, 9, 28, 7), buy_price=100.0)   # 앞 순위가 마지막 자리를 채움
ORDER = ["A00001", "006910"]


def test_slot_verdict_v3_reopens_when_on_tick_finished_inside_free_window():
    v = F.slot_verdict([UPPER], D, 1, 5, "006910", ORDER, ["09:03:37", "09:30:00"])
    assert v.state_v2 == STATE_NO_SLOT            # v2: 모든 빈자리가 앞 순위 매수로 닫힘
    assert v.state == STATE_SLOT                  # v3: 빈자리 동안 on_tick 이 끝났다 → 평가됐다
    assert v.eval_v1 is True and "09:03:37" in v.note


def test_slot_verdict_v3_keeps_no_slot_without_on_tick_in_window():
    v = F.slot_verdict([UPPER], D, 1, 5, "006910", ORDER, ["09:28:30", "09:30:00"])   # 소진 뒤에야 끝남
    assert v.state_v2 == STATE_NO_SLOT and v.state == STATE_NO_SLOT


def test_slot_verdict_never_free_and_held():
    old = Trade(buy_id=2, code="000002", buy_ts=datetime(2026, 9, 10, 9, 5), buy_price=10.0)   # 전날부터 K=1 채움
    v = F.slot_verdict([old], D, 1, 5, "006910", ["006910"], ["09:03:00"])
    assert v.state == STATE_NO_SLOT and v.eval_v1 is False
    mine = Trade(buy_id=3, code="006910", buy_ts=datetime(2026, 9, 10, 9, 5), buy_price=10.0)
    assert F.slot_verdict([mine], D, 5, 5, "006910", ["006910"], ["09:03:00"]).state == STATE_HELD


def test_day_volume_vintage_and_fragile_direction():
    assert F.day_volume_vintage("breakout vol=100/10", "breakout vol=124/10") == pytest.approx(0.24)
    assert F.day_volume_vintage("", "vol=1/1") is None
    # daytrading(bias Y): 재현 Y 비율 2.2 · 문턱 2.0 · vmax 24.3% → 라이브 최소 1.77 < 2.0 → 취약
    assert F.vintage_fragile("Y", "Y", 2.2, 2.0, 0.243) == "Y"
    assert F.vintage_fragile("Y", "Y", 3.0, 2.0, 0.243) == "N"
    assert F.vintage_fragile("Y", "N", 1.5, 2.0, 0.243) == "N"      # 재기록은 N 을 Y 로 만들지 못한다
    # minervini(bias N): 재현 N 비율 0.80 · 문턱 0.70 → 라이브 최소 0.644 ≤ 0.70 → 취약
    assert F.vintage_fragile("N", "N", 0.80, 0.70, 0.243) == "Y"
    assert F.vintage_fragile("N", "Y", 0.60, 0.70, 0.243) == "N"
    assert F.vintage_fragile(None, "Y", 2.2, 2.0, 0.243) == "" and F.vintage_fragile("Y", "Y", None, 2.0, 0.2) == ""
```

`backtest/concept_axes/ledger8/tests/test_livesignal8.py`:
```python
"""livesignal8 — 라이브 인스턴스 로드 · on_tick 가드 · 상태 무변경(rs 예외) · 라이브 밴드(합성 프레임 · DB 없음)."""
from __future__ import annotations

from datetime import date, datetime
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.ledger8 import livesignal8 as LS8
from backtest.concept_axes.ledger8 import registry as R

D = date(2026, 9, 17)


def _frame(n: int = 90, last_close: float = 118.0) -> pd.DataFrame:
    days = pd.bdate_range(end="2026-09-16", periods=n)
    close = np.linspace(100.0, 130.0, n)
    close[-1] = last_close
    return pd.DataFrame({"date": days, "open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": np.full(n, 1e5)})


def _forced(folder: str):
    if R.spec(folder).entry_eval_arity == 3:
        return staticmethod(lambda *a, **k: (True, ["forced"], {}))
    return staticmethod(lambda *a, **k: (True, ["forced"]))


@pytest.fixture(scope="module")
def strategies():
    return {f: LS8.load8(f) for f in R.ALL_FOLDERS}


def test_load8_all(strategies):
    assert set(strategies) == set(R.ALL_FOLDERS)
    assert all(s.positions == {} and s.daily_trades == 0 for s in strategies.values())


def test_on_tick_guards(strategies):
    s = strategies["book_pullback_ma20"]
    assert LS8.evaluate8(s, "book_pullback_ma20", "000001", D, None).reason == "no_daily_data"
    ev = LS8.evaluate8(s, "book_pullback_ma20", "000001", D, _frame(n=10))
    assert ev.signal == "N" and ev.reason.startswith("insufficient_data(10<")


@pytest.mark.parametrize("folder", [f for f in R.ALL_FOLDERS if f != "book_envelope_200d"])
def test_yes_path_returns_live_band(strategies, folder):
    s, df = strategies[folder], _frame()
    with mock.patch.object(type(s), "evaluate_entry", _forced(folder)):
        ev = LS8.evaluate8(s, folder, "000001", D, df)
    assert ev.signal == "Y" and ev.reasons_str == "forced"
    ref = float(df["close"].iloc[-1])
    assert ev.ref == pytest.approx(ref)
    if folder == "elder_ema_pullback":
        from strategies.books.elder_triple_screen.rules import krx_tick
        hi = float(df["high"].iloc[-1])
        stop = hi + krx_tick(hi)
        assert ev.band_min == pytest.approx(stop) and ev.band_max == pytest.approx(stop * (1 + s._entry_band_up_pct))
    else:
        assert (ev.band_min, ev.band_max) == s._entry_band(ref, down_pct=s._entry_band_down_pct,
                                                           up_pct=s._entry_band_up_pct)


def test_envelope_reads_own_frame_and_clears_cache(strategies):
    s = strategies["book_envelope_200d"]
    with mock.patch.object(s, "_fetch_entry_history", return_value=_frame(n=240)) as fetch, \
            mock.patch.object(type(s), "evaluate_entry", _forced("book_envelope_200d")):
        ev = LS8.evaluate8(s, "book_envelope_200d", "000001", D, _frame(n=8))   # on_tick 게이트는 min_gate_bars=5
    assert fetch.called and ev.signal == "Y" and s._entry_df_cache == {}


def test_state_change_raises_except_rs_leader_skip_log(strategies):
    def mutate(self, code, data):
        self._ontick_skip_log[(code, "probe")] = datetime(2026, 9, 17, 9, 2)
        return None
    for folder, raises in (("rs_leader", False), ("book_pullback_ma20", True)):
        s = strategies[folder]
        with mock.patch.object(type(s), "_check_buy", mutate):
            if raises:
                with pytest.raises(RuntimeError):
                    LS8.evaluate8(s, folder, "000001", D, _frame())
            else:
                assert LS8.evaluate8(s, folder, "000001", D, _frame()).signal == "N"
        s._ontick_skip_log.clear()


def test_positions_change_raises_even_for_rs_leader(strategies):
    def mutate(self, code, data):
        self.positions[code] = {}
        return None
    s = strategies["rs_leader"]
    with mock.patch.object(type(s), "_check_buy", mutate), pytest.raises(RuntimeError):
        LS8.evaluate8(s, "rs_leader", "000001", D, _frame())
    s.positions.clear()


def test_patches_restore(strategies):
    import config.constants as CC
    from config.market_hours import MarketHours
    before_mode, before_fn = CC.RS_LEADER_CORP_ACTION_MODE, MarketHours.is_market_open
    with LS8.live_buy_patches(strategies["rs_leader"], "rs_leader", date(2026, 9, 17)):
        assert CC.RS_LEADER_CORP_ACTION_MODE == "live" and MarketHours.is_market_open("KRX") is True
    with LS8.live_buy_patches(strategies["rs_leader"], "rs_leader", date(2026, 9, 16)):
        assert CC.RS_LEADER_CORP_ACTION_MODE == "shadow"
    assert CC.RS_LEADER_CORP_ACTION_MODE == before_mode and MarketHours.is_market_open == before_fn


def test_forced_band_is_live_band(strategies):
    folder = "book_pullback_ma5"
    s = strategies[folder]
    ref, lo, hi = LS8.forced_band(s, folder, "000001", D, _frame())
    assert (lo, hi) == s._entry_band(ref, down_pct=s._entry_band_down_pct, up_pct=s._entry_band_up_pct)
    assert s.positions == {}


def test_volume_margin_uses_live_rule_thresholds():
    from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
    from strategies.books.minervini_vcp.rules import rule_volume_dryup
    ev = LS8.SignalEval8(LS8.DAY, "000001", D, "Y", "x", reasons_str="breakout_prev_high close=1 prior20_high=1 vol=300/100")
    assert LS8.volume_margin(LS8.DAY, None, ev) == (3.0, float(rule_breakout_prev_high.vol_mult))
    df = _frame(n=40)
    df["volume"] = [100.0] * 30 + [60.0] * 10                   # recent10 / base30 = 0.60
    ratio, thr = LS8.volume_margin(LS8.MIN, df, LS8.SignalEval8(LS8.MIN, "000001", D, "N", "rule_not_met"))
    assert ratio == pytest.approx(0.60) and thr == float(rule_volume_dryup.ratio_max)
    assert LS8.volume_margin("rs_leader", df, ev) is None
```

- [ ] **Step 3: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_fidelity8.py backtest/concept_axes/ledger8/tests/test_livesignal8.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'fidelity8'` / `'livesignal8'`.

- [ ] **Step 4: `fidelity8.py` 작성(신호 부분)**

```python
"""충실도 — 순수 판정·집계(DB 없음). 라이브 계기와 재현을 대조해 «원장을 얼마나 믿을지»를 수치로 낸다.

🔒 기준값은 결과를 보고 바꾸지 않는다. 미달은 숨기지 않고 표에 LOW 로 적는다.
   신호 충실도는 B 계산 «전에» 본다(스펙 §4-2) — run `--stage signal`.
🔑 신호 일치는 방향을 나눠 본다. 판정 가능 행은 대부분 «로그 Y» 라 Y 방향만 검증되기 쉽다 — 「라이브 N 인데
   재현 Y」 오류율(N 방향)은 로그 N 표본이 있어야 잰다. 표본이 모자라면 «판정 불가»로 남긴다(critic 2026-09-19).
🔑 «평가 가능»(= 로그로 N 을 말할 수 있다) 규칙은 `slot_verdict` 한 곳에 순수 함수로 둔다. 변경 이력(v1→v2→v3)은
   계획서 「계획 검증 실행」 절에 있고, 세 규칙의 결과를 모두 보고서에 싣는다(채택 = v3).
"""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import classify as C

SIG_AGREE_MIN = 0.90      # 전략별 신호 일치율(방향별 · 평가 가능 행) 기준
EXIT_REASON_MIN = 0.70    # 전략별 청산 사유 일치율(실제 청산된 건) 기준
FID_MIN_N = 5             # 분모가 이보다 작으면 «판정 불가»

LOG_Y, LOG_N, LOG_NA = "Y", "N", "NA"
OUT_AGREE_Y = "agree_Y"
OUT_AGREE_N = "agree_N"
OUT_REPLAY_ONLY = "replay_only"
OUT_LOG_ONLY = "log_only"
OUT_NA = "na"
EVALUABLE_STATES = (C.STATE_SLOT, C.STATE_BOUGHT)


def signal_log_state(buysig_seen: bool, ontick_ran: bool, evaluable: bool) -> str:
    """라이브 로그가 말하는 그날 신호.

    Y  = 그날 `[on_tick] 매수신호: CODE(` 가 한 줄이라도 있다(무스로틀 — strategies/base.py:720-726).
    N  = 그 전략 on_tick 이 그날 돌았고 평가 가능(`slot_verdict`)했는데 줄이 없다.
    NA = 그 밖 — 보유·캡이라 `_check_buy` 까지 안 갔을 수 있거나 로그가 없다.
    """
    if buysig_seen:
        return LOG_Y
    if ontick_ran and evaluable:
        return LOG_N
    return LOG_NA


def decide_signal(replay: str, log: str) -> Tuple[str, str]:
    """(사용 신호, 근거). 라이브 로그가 판정 가능하면 로그(그 시점 DB), 아니면 재현(지금 DB)."""
    if log in (LOG_Y, LOG_N):
        return log, "log"
    return replay, "replay"


def signal_outcome(replay: str, log: str) -> str:
    if log == LOG_NA:
        return OUT_NA
    if replay == "Y" and log == LOG_Y:
        return OUT_AGREE_Y
    if replay == "N" and log == LOG_N:
        return OUT_AGREE_N
    return OUT_REPLAY_ONLY if replay == "Y" else OUT_LOG_ONLY


# ── «평가 가능» 규칙 (v1 · v2 · v3 — 채택 v3) ──────────────────────────────────
@dataclass
class SlotVerdict:
    state: str        # v3(채택) — classify.STATE_BOUGHT/HELD/NO_SLOT/SLOT
    state_v2: str     # v2 = cap_skip_ledger classify_candidate 그대로(민감도)
    eval_v1: bool     # v1 = 09:02 한 시점: 그 시각 미보유 ∧ 빈자리 구간 안(민감도)
    note: str


def slot_verdict(trades: Sequence[C.Trade], d: date, k: int, mdt: int, code: str, list_order: Sequence[str],
                 ontick_times: Sequence[str], first_tick: time = time(9, 2, 0)) -> SlotVerdict:
    """그날 라이브가 이 종목을 `_check_buy` 까지 평가할 수 있었나(체결 원장 시간선 · 순수).

    v2 = `classify.classify_candidate`(cap_skip_ledger/classify.py:176-205): bought > held(09:00 보유) >
         no_slot(장 전체 빈자리 없음 «또는 모든 빈자리가 목록상 앞 순위 매수로 닫힘») > slot_available.
    v3 = v2 의 no_slot 중 «빈자리 구간 안에서 그 전략 on_tick 이 한 번이라도 끝났다»(`[on_tick] 매수검토` 시각
         t, 구간 시작 ≤ t < 구간 끝=소진 매수 시각)면 slot_available — on_tick 은 한 번 돌 때 목록 전부를 평가하고
         그 한 번이 빈자리 동안 끝났으면 이 종목도 자리 있는 상태로 평가됐다. 소진 매수를 낸 on_tick 의 요약 줄은
         소진 시각 «뒤»라 스스로 제외된다. (반례: ma5 09-11 006910 — 빈자리 09:00:00~09:28:07 · 첫 신호 09:03:37)
    v1 = 09:02 한 시점 규칙(최초안) — 첫 틱 안에서 앞 순위 매수가 자리를 채우는 경우를 못 본다.
    """
    n0, windows = C.slot_windows_detail(trades, d, k, mdt)
    state_v2, note = C.classify_candidate(code, d, trades, windows, list_order=list_order)
    t1 = datetime.combine(d, first_tick)
    held_t1 = any(x.code == code for x in C.open_at(trades, t1))
    eval_v1 = (not held_t1) and any(w[0] <= first_tick < w[1] for w in windows)
    state = state_v2
    if state_v2 == C.STATE_NO_SLOT:
        hits = sorted(t for t in ontick_times for w in windows
                      if w[0].strftime("%H:%M:%S") <= t < w[1].strftime("%H:%M:%S"))
        if hits:
            state = C.STATE_SLOT
            note += f" · 빈자리 구간 안 on_tick 완료 {hits[0]}(v3: 평가 가능)"
    return SlotVerdict(state, state_v2, eval_v1,
                       f"{note} · K={k} 09:00보유={n0} 빈자리={C.fmt_windows(windows) or '(없음)'}")


# ── 빈티지(거래량 재기록) ─────────────────────────────────────────────────────
_VOL_RE = re.compile(r"vol=(\d+)/(\d+)")


def day_volume_vintage(live_reasons: Optional[str], replay_reasons: Optional[str]) -> Optional[float]:
    """daytrading 사유 `vol=a/b` 의 a(D-1 거래량) — (재현 a ÷ 라이브 a − 1). 라이브 스캔 뒤 재기록된 폭."""
    a = _VOL_RE.search(live_reasons or "")
    b = _VOL_RE.search(replay_reasons or "")
    if not a or not b or float(a.group(1)) <= 0:
        return None
    return float(b.group(1)) / float(a.group(1)) - 1.0


def vintage_fragile(bias: Optional[str], signal: str, ratio: Optional[float], threshold: Optional[float],
                    vmax: Optional[float]) -> str:
    """재현 신호가 «관측 빈티지 폭» 안에서 뒤집힐 수 있었나. 반환 'Y' 취약 · 'N' 안전 · '' 재료 없음.

    재기록은 거래량을 «늘린다»(관측). 그래서 방향이 정해져 있다.
      bias='Y'(daytrading: 비율 ≥ 문턱이 Y) — 재현 Y 이고 비율/(1+vmax) < 문턱 ⇒ 라이브는 N 이었을 수 있다.
      bias='N'(minervini: 비율 ≤ 문턱이 Y) — 재현 N 이고 비율/(1+vmax) ≤ 문턱 ⇒ 라이브는 Y 였을 수 있다.
    반대쪽(day 재현 N · min 재현 Y)은 재기록이 일어나도 뒤집히지 않는다 → 'N'.
    ⚠️ vmax 를 비율 전체에 거는 것은 상한(보수적)이다 — minervini 는 D-1 봉 하나가 recent 10봉 평균에 1/10 로만 든다.
    """
    if not bias or ratio is None or threshold is None or vmax is None:
        return ""
    live_min = ratio / (1.0 + max(vmax, 0.0))
    if bias == "Y" and signal == "Y":
        return "Y" if live_min < threshold else "N"
    if bias == "N" and signal == "N":
        return "Y" if live_min <= threshold else "N"
    return "N"


def _group(row: Dict[str, Any]) -> str:
    mode = row.get("mode") or ""
    return f"{row['strategy']}[{mode}]" if mode else str(row["strategy"])


def signal_table(rows: Sequence[Dict[str, Any]], outcome_key: str = "outcome") -> List[Dict[str, Any]]:
    """전략별(rs_leader 는 모드별) 신호 일치 — 방향을 나눈다.

    Y 방향 = 로그 Y 행 중 재현도 Y = agree_Y / (agree_Y + log_only)
    N 방향 = 로그 N 행 중 재현도 N = agree_N / (agree_N + replay_only) — 「라이브 N 인데 재현 Y」 오류율의 거울
    판정: 분모 ≥ FID_MIN_N 인 방향만 기준과 비교 · 하나라도 미달 LOW · 둘 다 표본 부족이면 «판정 불가».
    `bought` = 판정 가능 행 중 실제 체결(자명한 Y/Y) 수. `outcome_key` 로 민감도 규칙(v1·v2)의 결과도 같은 표로 낸다.
    """
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        key = _group(r)
        g = groups.setdefault(key, dict(group=key, n=0, evaluable=0, agree_Y=0, agree_N=0, replay_only=0,
                                        log_only=0, bought=0, reasons_eq=0, ref_eq=0))
        g["n"] += 1
        o = r[outcome_key]
        if o == OUT_NA:
            continue
        g["evaluable"] += 1
        g[o] += 1
        g["bought"] += int(r.get("slot_state") == C.STATE_BOUGHT)
        if o == OUT_AGREE_Y:
            g["reasons_eq"] += int(r.get("reasons_equal") == "Y")
            g["ref_eq"] += int(r.get("ref_equal") == "Y")
    out: List[Dict[str, Any]] = []
    for g in groups.values():
        g["y_n"] = g["agree_Y"] + g["log_only"]
        g["n_n"] = g["agree_N"] + g["replay_only"]
        g["y_rate"] = g["agree_Y"] / g["y_n"] if g["y_n"] else None
        g["n_rate"] = g["agree_N"] / g["n_n"] if g["n_n"] else None
        g["rate"] = (g["agree_Y"] + g["agree_N"]) / g["evaluable"] if g["evaluable"] else None
        dirs = (("Y", g["y_n"], g["y_rate"]), ("N", g["n_n"], g["n_rate"]))
        judged = [(nm, r_) for nm, n_, r_ in dirs if n_ >= FID_MIN_N]
        g["verdict_note"] = " · ".join(f"{nm} 방향 판정 불가(n={n_}<{FID_MIN_N})" for nm, n_, _ in dirs
                                       if n_ < FID_MIN_N)
        if not judged:
            g["verdict"] = "판정 불가"
        elif any(r_ < SIG_AGREE_MIN for _, r_ in judged):
            g["verdict"] = "LOW"
        else:
            g["verdict"] = "ok"
        out.append(g)
    return out
```

- [ ] **Step 5: `livesignal8.py` 작성**

```python
"""«샀을 신호» 판정 — 8전략 라이브 인스턴스의 `_check_buy` 를 그대로 부른다(룰 복제 0).

라이브 `BaseStrategy.on_tick` 매수 루프(strategies/base.py:660-708) 순서:
  ① data 없음 / len < get_min_data_length() → 스킵        (:662-687)
  ② describe_impossible_drop(data) → 스킵                   (:693-707)
  ③ generate_signal 의 보유·일일체결·K 게이트 — 여기서는 «건너뛴다»(보유와 무관하게 룰만 본다 · 스펙 3-1).
     그 게이트는 stages.py 가 로그·체결 원장으로 따로 분류한다.
  ④ _check_buy(code, data)
하루 1회면 충분하다 — 창은 오늘 봉을 뺀 확정봉(core/trading_context.py:143-199)이고 8전략 `_check_buy` 는
`data` 의 마지막 확정봉(D-1)만 쓴다(스펙 3-6: 여러 틱을 하루 1회로 접는 것은 근사가 아니라 정확).

패치(프로세스 안 mock · 파일 무수정)
  - `config.market_hours.MarketHours.is_market_open` → True. 8전략 모두 같은 클래스를 import 한다.
  - rs_leader: `config.constants.RS_LEADER_CORP_ACTION_MODE` 를 그날 모드로(corp_action_guard.py:56-57 가 호출 시점에 읽는다).
  - envelope: 모듈 `now_kst` 를 D 09:02 로(`_fetch_entry_history` 캐시 키·end_date · strategy.py:231-249),
    호출 전후 `_entry_df_cache` 를 비운다.
상태 무변경 — registry.state_attrs(folder) 를 호출 전후 deepcopy 비교, 다르면 RuntimeError.
"""
from __future__ import annotations

import copy
import importlib
import re
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterator, Optional, Tuple
from unittest import mock

import pandas as pd

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저
from backtest.concept_axes.minervini.cap_skip_ledger import sources as _S

import config.constants as _CC                              # noqa: E402
from config.market_hours import MarketHours                 # noqa: E402
from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high   # noqa: E402
from strategies.books.minervini_vcp.rules import rule_volume_dryup               # noqa: E402
from strategies.config import StrategyLoader                # noqa: E402
from utils.data_sanity import describe_impossible_drop      # noqa: E402

from . import registry as R

ENVELOPE = "book_envelope_200d"
DAY = "daytrading_3methods_breakout"
MIN = "minervini_volume_dryup"
# 거래량 재기록(증가)이 재현 신호를 어느 쪽으로 기울이나 — day: 비율 ≥ 문턱이 Y ⇒ Y 쪽 · min: 비율 ≤ 문턱이 Y ⇒ N 쪽
VOLUME_RULE_BIAS = {DAY: "Y", MIN: "N"}
_VOL_RE = re.compile(r"vol=(\d+)/(\d+)")
_RATIO_RE = re.compile(r"recent/base=([0-9.]+)")


@dataclass
class SignalEval8:
    folder: str
    code: str
    d: date
    signal: str                          # Y | N
    reason: str                          # Y: 룰 사유 · N: no_daily_data | insufficient_data(n<m) | impossible_bar(…) | rule_not_met
    reasons_str: str = ""                # ', '.join(signal.reasons) — 라이브 `[on_tick] 매수신호 … 이유:` 와 같은 표기(base.py:722)
    n_bars: int = 0
    last_bar: str = ""
    ref: Optional[float] = None          # metadata[registry.ref_key]
    band_min: Optional[float] = None
    band_max: Optional[float] = None
    confidence: Optional[float] = None
    detail: Dict[str, Any] = field(default_factory=dict)


def load8(folder: str):
    """라이브와 같은 로더(StrategyLoader)로 config.yaml 을 읽어 인스턴스를 만든다. 브로커·API 없음."""
    s = StrategyLoader.load_strategy(folder)
    if not s.on_init(None, None, None):
        raise RuntimeError(f"{folder} on_init 실패")
    return s


def _module(strategy):
    return importlib.import_module(type(strategy).__module__)


def state_snapshot(strategy, folder: str) -> tuple:
    return tuple(copy.deepcopy(getattr(strategy, a, None)) for a in R.state_attrs(folder))


@contextmanager
def live_buy_patches(strategy, folder: str, d: date) -> Iterator[None]:
    mode = R.corp_action_mode_for(folder, d)
    with ExitStack() as st:
        st.enter_context(mock.patch.object(MarketHours, "is_market_open", return_value=True))
        if mode is not None:
            st.enter_context(mock.patch.object(_CC, "RS_LEADER_CORP_ACTION_MODE", mode))
            st.enter_context(mock.patch.object(_CC, "RS_LEADER_CORP_ACTION_MODE_INVALID", None))
        if folder == ENVELOPE:
            st.enter_context(mock.patch.object(_module(strategy), "now_kst", return_value=_S._as_of(d)))
            strategy._entry_df_cache.clear()
        try:
            yield
        finally:
            if folder == ENVELOPE:
                strategy._entry_df_cache.clear()


def _guard(folder: str, code: str, d: date, data: Optional[pd.DataFrame], min_len: int) -> Optional[SignalEval8]:
    if data is None or data.empty:
        return SignalEval8(folder, code, d, "N", "no_daily_data")
    n = len(data)
    last = str(pd.to_datetime(data["date"].iloc[-1]).date())
    if n < min_len:
        return SignalEval8(folder, code, d, "N", f"insufficient_data({n}<{min_len})", n_bars=n, last_bar=last)
    bad = describe_impossible_drop(data)
    if bad:
        return SignalEval8(folder, code, d, "N", f"impossible_bar({bad})", n_bars=n, last_bar=last)
    return None


def _call_check_buy(strategy, folder: str, code: str, d: date, data: pd.DataFrame):
    before = state_snapshot(strategy, folder)
    quant: Optional[pd.DataFrame] = None
    with live_buy_patches(strategy, folder, d):
        sig = strategy._check_buy(code, data)
        if folder == ENVELOPE:
            quant = strategy._entry_df_cache.get((code, d))
    if state_snapshot(strategy, folder) != before:
        raise RuntimeError(f"_check_buy 가 전략 상태를 바꿨다 — {folder} {code} {d}")
    return sig, quant


def evaluate8(strategy, folder: str, code: str, d: date, data: Optional[pd.DataFrame]) -> SignalEval8:
    early = _guard(folder, code, d, data, strategy.get_min_data_length())
    if early is not None:
        return early
    n, last = len(data), str(pd.to_datetime(data["date"].iloc[-1]).date())
    sig, quant = _call_check_buy(strategy, folder, code, d, data)
    detail: Dict[str, Any] = {}
    if quant is not None and not quant.empty:
        detail.update(quant_n=len(quant), quant_last=str(pd.to_datetime(quant["date"].iloc[-1]).date()))
    if sig is None:
        return SignalEval8(folder, code, d, "N", "rule_not_met", n_bars=n, last_bar=last, detail=detail)
    meta = dict(getattr(sig, "metadata", {}) or {})
    ref = meta.get(R.spec(folder).ref_key)
    reasons = list(sig.reasons or [])
    detail.update(signal_type=sig.signal_type.name, buy_stop_price=meta.get("buy_stop_price"))
    return SignalEval8(
        folder, code, d, "Y", "; ".join(reasons) or "buy", ", ".join(reasons) if reasons else "-", n, last,
        ref=float(ref) if ref is not None else None,
        band_min=getattr(sig, "entry_min_price", None), band_max=getattr(sig, "entry_max_price", None),
        confidence=float(sig.confidence), detail=detail)


def forced_band(strategy, folder: str, code: str, d: date, data: Optional[pd.DataFrame]
                ) -> Optional[Tuple[Optional[float], Optional[float], Optional[float]]]:
    """룰을 참으로 강제하고 라이브 `_check_buy` 를 불러 (기준가, 밴드) 만 얻는다 — 밴드·매수스톱 공식 복제 0.

    쓰는 곳: 라이브 로그는 Y 인데 재현이 N(빈티지)인 행, A_sim 의 실제 매수 중 재현 N 인 행.
    `evaluate_entry` 반환 길이 = registry.entry_eval_arity(테스트가 AST 로 대조). rs_leader live 배제면 None.
    """
    if data is None or data.empty:
        return None
    if R.spec(folder).entry_eval_arity == 3:
        fake = staticmethod(lambda *a, **k: (True, ["forced_band"], {}))
    else:
        fake = staticmethod(lambda *a, **k: (True, ["forced_band"]))
    with mock.patch.object(type(strategy), "evaluate_entry", fake):
        sig, _ = _call_check_buy(strategy, folder, code, d, data)
    if sig is None:
        return None
    ref = (sig.metadata or {}).get(R.spec(folder).ref_key)
    return (float(ref) if ref is not None else None,
            getattr(sig, "entry_min_price", None), getattr(sig, "entry_max_price", None))


def volume_margin(folder: str, data: Optional[pd.DataFrame], ev: SignalEval8) -> Optional[Tuple[float, float]]:
    """거래량 룰 전략의 (비율, 문턱) — 라이브 룰 클래스의 기본 문턱을 쓴다(공식 복제 0). 해당 없으면 None.

    day: `_check_buy` 사유 `vol=a/b`(룰이 Y 일 때만 사유가 있다) · 문턱 = rule_breakout_prev_high.vol_mult
         (strategies/books/daytrading_3methods/rules.py:280 · 비교 :293)
    min: rule_volume_dryup(ratio_max=∞) 사유 `recent/base=x` · 문턱 = rule_volume_dryup.ratio_max
         (strategies/books/minervini_vcp/rules.py:319 · 비교 :330)
    """
    if folder == DAY:
        m = _VOL_RE.search(ev.reasons_str or "")
        if not m or float(m.group(2)) <= 0:
            return None
        return float(m.group(1)) / float(m.group(2)), float(rule_breakout_prev_high.vol_mult)
    if folder == MIN:
        if data is None or data.empty:
            return None
        res = rule_volume_dryup(ratio_max=float("inf")).evaluate(data, {})
        m = _RATIO_RE.search(" ".join(getattr(res, "reasons", None) or []))
        return (float(m.group(1)), float(rule_volume_dryup.ratio_max)) if m else None
    return None
```

- [ ] **Step 6: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_fidelity8.py backtest/concept_axes/ledger8/tests/test_livesignal8.py -q -p no:cacheprovider`
Expected: PASS. 첫 줄의 `key.ini 파일을 찾을 수 없습니다` 경고는 `config.settings` import 부수효과(워크트리엔 key.ini 없음) — 무해, KIS API 호출 0.

- [ ] **Step 7: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| 3-1 `StrategyLoader.load_strategy` + `on_init(None,None,None)` 8전략 | `load8` · `test_load8_all`(스펙의 「추측」 해소) | [ ] |
| 3-1 `MarketHours.is_market_open` 1회 패치 | `live_buy_patches` · `test_patches_restore` | [ ] |
| 3-1 `generate_signal` 거치지 않고 `_check_buy` 직접 | `_call_check_buy` | [ ] |
| envelope `now_kst` 패치 + 캐시 비움 | `live_buy_patches` · `test_envelope_reads_own_frame_and_clears_cache` | [ ] |
| rs_leader 날짜별 모드 패치 · `_ontick_skip_log` 예외 | `live_buy_patches` · `test_state_change_raises_except_rs_leader_skip_log` | [ ] |
| elder 밴드 = [매수스톱, ×1.02] · ref_key(env=ref_close) | `test_yes_path_returns_live_band` | [ ] |
| 신호 충실도 판정 규칙(로그 우선 · 방향별 Y·N · 판정 불가 · LOW) | `fidelity8.signal_table` · `test_signal_table_splits_directions` | [ ] |
| critic 🔴2 «평가 가능» 규칙 = 순수 함수 · 반례(빈자리 안 on_tick) · v1·v2 민감도 | `fidelity8.slot_verdict` · `test_slot_verdict_*` | [ ] |
| critic 🔴1③ 거래량 룰 여유 · 빈티지 방향(day→Y · min→N) | `livesignal8.volume_margin` · `fidelity8.vintage_fragile` · 테스트 | [ ] |

- [ ] **Step 8: Commit**

```bash
git add backtest/concept_axes/ledger8/fidelity8.py backtest/concept_axes/ledger8/livesignal8.py backtest/concept_axes/ledger8/tests/test_fidelity8.py backtest/concept_axes/ledger8/tests/test_livesignal8.py
git commit -F - <<'MSG'
feat(ledger8): 라이브 _check_buy 재현(8전략)과 신호 충실도 판정

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 4: sources8 · context8 · run `--stage signal` + 신호 충실도 게이트(실데이터)

**Files:**
- Modify(전면 교체): `backtest/concept_axes/ledger8/sources8.py`
- Create: `backtest/concept_axes/ledger8/context8.py`
- Create: `backtest/concept_axes/ledger8/run.py`
- 산출(추적 안 함 — 과제 10 전체 실행 때 커밋): `backtest/concept_axes/ledger8/results/fidelity_signal.csv`, `offlist_signals.csv`, `run_meta.json`

**Interfaces:**
- Consumes: `logscan8.scan_day · live_candidate_list · CandList · StratDay`(과제 2) · `livesignal8.load8 · evaluate8`(과제 3) · `fidelity8.signal_log_state · decide_signal · signal_outcome · signal_table`(과제 3) · `registry.*`(과제 1) · 재사용 `cap_skip_ledger.{bootstrap, sources, classify, tradecal, sim.Bar}`.
- Produces:
  - `sources8.connect · load_calendar · load_bars · FIRST_TICK · KST · as_of(d) -> datetime · aware(ts) -> datetime · load_snapshot(conn, strategy, scan_date) -> List[Dict] · snapshot_strategies(conn, start, end) -> Dict[str, int] · load_trades8(conn, until) -> Dict[str, List[Tuple]] · WindowCache.get(code, d) -> Tuple[Optional[DataFrame], Dict]`
    - `load_trades8` 행 = `(id, code, action, price, ts_kst, reason, buy_record_id, quantity, target_profit_rate, stop_loss_rate)` — 앞 7칸은 `classify.build_trades` 입력과 같다.
  - `context8.TradeExtra(qty, tp_rate, sl_rate)` · `context8.Ctx8` 필드 `conn calendar log_dir strategies trades extras windows bars logs snaps` · 메서드 `open(log_dir) -> Ctx8(classmethod) · close() · log_for(d) · bars_for(code) · snapshot(folder, scan_date) · candidates(folder, d) -> Tuple[CandList, Optional[date], Dict[str, Optional[int]]] · path(code, d) -> List[Tuple[int, date, Optional[Bar]]] · first_tick(d) -> datetime · slot_state(folder, code, d, list_order) -> fidelity8.SlotVerdict · others_at(folder, code, t) -> List[str] · buys_on(folder, d) -> List[Trade] · last_close(code) -> Optional[Tuple[date, float]]`
    - `slot_state` = `fidelity8.slot_verdict`(과제 3) 에 체결 원장·K 이력·그 전략 on_tick 완료 시각(`StratDay.ontick_times`)을 넘긴 것
  - `run.evaluate_candidates(ctx, days) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], Dict[str, Any]]` — (후보 행, 목록 밖 신호, 관측 빈티지 `{n, vmin, vmax}`) · 후보 행 dict 키: `d folder code tier list_pos snap_rank list_src scan_date sector_mode held no_slot slot_state slot_state_v2 eval_v1 slot_note ev buysig receipt signal_log signal_log_v1 signal_log_v2 signal_used signal_basis vol_ratio vol_threshold vintage_fragile reasons_equal ref_equal`
  - `run.signal_fidelity_rows(cands) -> List[Dict[str, str]]` · `run._print_signal_tables(sig_rows, vintage)` · `run.fill_attribution_check(ctx, days) -> List[str]` · `run.SIG_COLS · OFF_COLS` · `run._fmt · _pct · _won_str · _atomic_write_csv · _atomic_write_text · _git_sha · _resolve_log_dir · _meta · main(argv)`

- [ ] **Step 1: `sources8.py` 전면 교체**

```python
"""DB 읽기(SELECT 전용) — 8전략판.

순수 SELECT·달력·OHLC·일봉 창 재현은 `cap_skip_ledger.sources` 가 이미 전략 무관이라 그대로 재사용한다
(그 파일은 minervini 원장이 쓰고 있어 수정하지 않는다). 새로 두는 것은 넷:
  1. `load_snapshot(conn, strategy, scan_date)` — 원본은 모듈 상수 `STRATEGY` 를 썼다(sources.py:35 · :64-70).
  2. `snapshot_strategies(conn, start, end)` — 창 안 스냅샷 보유 전략(run_meta 점검용).
  3. `load_trades8(conn, until)` — 원본 체결 원장(sources.py:73-87)에 수량·익절률·손절률 칸을 더한 판.
  4. `WindowCache` — `(code, D)` → 라이브 일봉 창. 8전략·매도 탐침이 같은 창을 공유한다.
envelope 의 자체 프레임은 여기서 읽지 않는다 — livesignal8 이 라이브 `_check_buy` 를 그대로 부른다.
🔴 DB 쓰기 0 — `bootstrap` 이 `PGOPTIONS=default_transaction_read_only=on` 으로 서버에서 막는다.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저
from backtest.concept_axes.minervini.cap_skip_ledger import sources as _S
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar  # noqa: F401  (재노출)

connect = _S.connect
load_calendar = _S.load_calendar
load_bars = _S.load_bars
FIRST_TICK = _S.FIRST_TICK      # 실측 첫 on_tick 평가 시각 ≈ 09:02
KST = _S._KST
as_of = _S._as_of               # date → D 09:02 KST(aware)
_fetch = _S._fetch


def aware(ts: datetime) -> datetime:
    """DB 의 `AT TIME ZONE 'Asia/Seoul'` naive 시각 → as_of 와 같은 tz(전략 hold_days 계산의 aware 비교용)."""
    if KST is not None and ts.tzinfo is None:
        return ts.replace(tzinfo=KST)
    return ts


def load_snapshot(conn, strategy: str, scan_date: date) -> List[Dict]:
    """`screener_snapshots` 한 전략·한 스캔일(순위순)."""
    rows = _fetch(conn, "SELECT stock_code, rank_in_snapshot, score, params_hash, "
                        "(created_at AT TIME ZONE 'Asia/Seoul') FROM screener_snapshots "
                        "WHERE strategy = %s AND scan_date = %s ORDER BY rank_in_snapshot, stock_code",
                  (strategy, scan_date.isoformat()))
    return [dict(code=str(c), rank=int(r) if r is not None else None, score=s, params_hash=h, created_at=ca)
            for c, r, s, h, ca in rows]


def snapshot_strategies(conn, start: date, end: date) -> Dict[str, int]:
    rows = _fetch(conn, "SELECT strategy, count(*) FROM screener_snapshots "
                        "WHERE scan_date BETWEEN %s AND %s GROUP BY strategy",
                  (start.isoformat(), end.isoformat()))
    return {str(s): int(n) for s, n in rows}


def load_trades8(conn, until: date) -> Dict[str, List[Tuple]]:
    """페이퍼 체결 전부(전 전략 · until 포함) → {strategy: [(id, code, action, price, ts_kst, reason,
    buy_record_id, quantity, target_profit_rate, stop_loss_rate)]}. `is_test=true` 가 정상이라 거르지 않는다."""
    rows = _fetch(conn, "SELECT COALESCE(strategy, ''), id, stock_code, action, price::float8, "
                        "(timestamp AT TIME ZONE 'Asia/Seoul'), reason, buy_record_id, quantity, "
                        "target_profit_rate::float8, stop_loss_rate::float8 "
                        "FROM virtual_trading_records "
                        "WHERE (timestamp AT TIME ZONE 'Asia/Seoul')::date <= %s ORDER BY timestamp, id",
                  (until.isoformat(),))
    out: Dict[str, List[Tuple]] = {}
    for strat, *rest in rows:
        out.setdefault(str(strat), []).append(tuple(rest))
    return out


class WindowCache:
    """`(code, D)` → 라이브가 D 첫 틱에 넘겼을 일봉 창(마지막 봉 = D-1). `cap_skip_ledger.sources.live_daily_window`."""

    def __init__(self, repo=None):
        self._repo = repo if repo is not None else _S._price_mod.PriceRepository()
        self._cache: Dict[Tuple[str, date], Tuple[Optional[pd.DataFrame], Dict]] = {}

    def get(self, code: str, d: date) -> Tuple[Optional[pd.DataFrame], Dict]:
        key = (code, d)
        if key not in self._cache:
            self._cache[key] = _S.live_daily_window(code, d, repo=self._repo)
        return self._cache[key]

    def __len__(self) -> int:
        return len(self._cache)
```

- [ ] **Step 2: `context8.py` 작성**

```python
"""실행 문맥 — DB(SELECT 전용)·달력·체결 원장·라이브 인스턴스·캐시와 시간선 질의.

🔴 DB 쓰기 0 — `bootstrap` 이 먼저 import 되어 PGOPTIONS=default_transaction_read_only=on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저
from backtest.concept_axes.minervini.cap_skip_ledger import classify as C
from backtest.concept_axes.minervini.cap_skip_ledger import tradecal as T
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

from . import fidelity8 as F
from . import livesignal8 as LS8
from . import logscan8 as L8
from . import registry as R
from . import sources8 as SRC8

CAL_START = date(2026, 6, 1)   # 달력·OHLC 읽기 시작(청산 충실도 창 08-26 보다 앞)


@dataclass
class TradeExtra:
    qty: int
    tp_rate: Optional[float]
    sl_rate: Optional[float]


@dataclass
class Ctx8:
    conn: Any
    calendar: List[date]
    log_dir: Path
    strategies: Dict[str, Any]
    trades: Dict[str, List[C.Trade]]
    extras: Dict[int, TradeExtra]
    windows: SRC8.WindowCache
    bars: Dict[str, Dict[date, Bar]] = field(default_factory=dict)
    logs: Dict[date, L8.DayLog] = field(default_factory=dict)
    snaps: Dict[Tuple[str, date], List[Dict]] = field(default_factory=dict)

    @classmethod
    def open(cls, log_dir: Path) -> "Ctx8":
        conn = SRC8.connect()
        cal = SRC8.load_calendar(conn, CAL_START, date.today() + timedelta(days=1))
        strategies = {f: LS8.load8(f) for f in R.ALL_FOLDERS}
        raw = SRC8.load_trades8(conn, date.today())
        trades = {k: C.build_trades([r[:7] for r in v]) for k, v in raw.items()}
        extras = {int(r[0]): TradeExtra(int(r[7] or 0), r[8], r[9]) for v in raw.values() for r in v}
        return cls(conn, cal, Path(log_dir), strategies, trades, extras, SRC8.WindowCache())

    def close(self) -> None:
        self.conn.close()

    def log_for(self, d: date) -> L8.DayLog:
        if d not in self.logs:
            self.logs[d] = L8.scan_day(self.log_dir, d, R.ALL_FOLDERS, R.LOGGER_TO_FOLDER)
        return self.logs[d]

    def bars_for(self, code: str) -> Dict[date, Bar]:
        if code not in self.bars:
            self.bars[code] = SRC8.load_bars(self.conn, code, CAL_START)
        return self.bars[code]

    def snapshot(self, folder: str, scan_date: date) -> List[Dict]:
        key = (folder, scan_date)
        if key not in self.snaps:
            self.snaps[key] = SRC8.load_snapshot(self.conn, folder, scan_date)
        return self.snaps[key]

    def candidates(self, folder: str, d: date) -> Tuple[L8.CandList, Optional[date], Dict[str, Optional[int]]]:
        """(라이브 E6 목록 main/ext, 스캔일 D-1, 스냅샷 순위)."""
        scan = T.prev_trading_day(self.calendar, d)
        snap = self.snapshot(folder, scan) if scan else []
        dl = self.log_for(d)
        sd = dl.get(folder)
        cl = L8.live_candidate_list([r["code"] for r in snap], sd)
        if sd.e6 is not None and scan and sd.e6["d1"] != scan.isoformat():
            cl.src += f"·D-1_mismatch(log {sd.e6['d1']})"
        if not dl.found:
            cl.src += "·no_log_file"
        return cl, scan, {r["code"]: r["rank"] for r in snap}

    def path(self, code: str, d: date) -> List[Tuple[int, date, Optional[Bar]]]:
        """진입일 D(k=0)부터 달력(=DB KOSPI 최신 봉) 끝까지 [(k, 날짜, 봉|None)]."""
        bars = self.bars_for(code)
        days = [d] + T.days_after(self.calendar, d)
        return [(i, dd, bars.get(dd)) for i, dd in enumerate(days)]

    def first_tick(self, d: date) -> datetime:
        return datetime.combine(d, SRC8.FIRST_TICK)

    def slot_state(self, folder: str, code: str, d: date, list_order: List[str]) -> F.SlotVerdict:
        """그날 라이브가 이 종목을 `_check_buy` 까지 평가할 수 있었나 — 규칙은 `fidelity8.slot_verdict`(순수 ·
        v3 채택 · v1·v2 는 민감도). 이 메서드는 체결 원장·K 이력·그 전략 on_tick 완료 시각만 넘긴다."""
        k, _ = R.k_for(folder, d)
        mdt, _ = R.mdt_for(folder, d)
        return F.slot_verdict(self.trades.get(folder, []), d, k, mdt, code, list_order,
                              self.log_for(d).get(folder).ontick_times, SRC8.FIRST_TICK)

    def others_at(self, folder: str, code: str, t: datetime) -> List[str]:
        return C.other_holders(self.trades, code, t, exclude=folder)

    def buys_on(self, folder: str, d: date) -> List[C.Trade]:
        return [x for x in self.trades.get(folder, []) if x.buy_ts.date() == d]

    def last_close(self, code: str) -> Optional[Tuple[date, float]]:
        bars = self.bars_for(code)
        if not bars:
            return None
        d = max(bars)
        return d, float(bars[d].close)
```

- [ ] **Step 3: `run.py` 작성(신호 단계만)**

```python
"""ledger8 — 8전략 세 arm(A 라이브 · B1 로트 독립 · B2 평단 합산) 관측 원장 CLI.

    cd <worktree>/RoboTrader_template
    PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe
    $PY -m backtest.concept_axes.ledger8.run --stage signal       # ② 신호 충실도(B 계산 «전에» 본다)

🔴 DB 쓰기 0 · 라이브 코드 0줄 · 관측 원장이다 — 판정 근거로 쓰지 말 것.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap
from backtest.concept_axes.minervini.cap_skip_ledger import classify as C
from backtest.concept_axes.minervini.cap_skip_ledger import tradecal as T

from . import fidelity8 as F
from . import livesignal8 as LS8
from . import registry as R
from .context8 import Ctx8

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "results"
BANNER = "관측 원장이다 — 판정 근거로 쓰지 말 것."


# ── 서식·I/O ─────────────────────────────────────────────────────────────
def _fmt(x: Any, nd: int = 4) -> str:
    if x is None:
        return ""
    if isinstance(x, bool):
        return "Y" if x else "N"
    if isinstance(x, float):
        return f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return str(x)


def _pct(x: Optional[float]) -> str:
    return "" if x is None else f"{x:+.2f}"


def _won_str(x: Optional[float]) -> str:
    return "" if x is None else str(int(round(x)))


def _yn(cond: Optional[bool]) -> str:
    return "" if cond is None else ("Y" if cond else "N")


def _atomic_write_csv(path: Path, cols: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols), extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(HERE),
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _resolve_log_dir(arg: Optional[str]) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("LEDGER8_LOG_DIR")
    if env:
        return Path(env)
    local = bootstrap.ROOT / "logs"
    if list(local.glob("robotrader_template_*.log")):
        return local
    return bootstrap.LIVE_LOG_DIR_DEFAULT


def _meta(days: Sequence[date], log_dir: Path, stage: str, warnings: Sequence[str]) -> Dict[str, Any]:
    return dict(banner=BANNER, run_ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), git_sha=_git_sha(),
                db=bootstrap.DB_NAME, log_dir=str(log_dir), stage=stage,
                window=f"{days[0]}~{days[-1]}", n_days=len(days), warnings=list(warnings))


# ── ② 신호 ────────────────────────────────────────────────────────────────
SIG_COLS = ["date", "strategy", "mode", "code", "list_pos", "slot_state", "slot_state_v2", "eval_v1",
            "signal_replay", "replay_reason", "signal_log", "signal_log_v1", "signal_log_v2", "n_evals", "first_ts",
            "last_ts", "outcome", "outcome_v1", "outcome_v2", "no_slot_but_log_y", "no_slot_but_log_y_v2",
            "reasons_equal", "ref_equal", "receipt_ref", "replay_ref", "signal_basis", "vol_ratio", "vol_threshold",
            "rule_margin_pct", "vintage_fragile"]
OFF_COLS = ["date", "strategy", "n_offlist", "codes"]


def evaluate_candidates(ctx: Ctx8, days: Sequence[date]
                        ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], Dict[str, Any]]:
    """(후보 행, E6 목록 밖 `[on_tick] 매수신호` 집계, 관측 빈티지). 후보 = D1 main + ext.

    «평가 가능» = `fidelity8.slot_verdict` v3(채택) ∧ 그날 `[캡]` 줄(3전략·09-16~) 없음. v1·v2 결과도 행에 남긴다(민감도).
    """
    cands: List[Dict[str, Any]] = []
    offlist: List[Dict[str, str]] = []
    for d in days:
        dl = ctx.log_for(d)
        for folder in R.ALL_FOLDERS:
            sd = dl.get(folder)
            cl, scan, ranks = ctx.candidates(folder, d)
            order = cl.main + cl.ext
            strat = ctx.strategies[folder]
            ran = sd.ontick_runs > 0
            off = sorted(set(sd.buysig) - set(cl.main))
            if off:
                offlist.append(dict(date=d.isoformat(), strategy=folder, n_offlist=str(len(off)), codes=",".join(off)))
            for tier, codes in ((R.TIER_MAIN, cl.main), (R.TIER_EXT, cl.ext)):
                for pos_, code in enumerate(codes, start=1):
                    data, _ = ctx.windows.get(code, d)
                    ev = LS8.evaluate8(strat, folder, code, d, data)
                    sv = ctx.slot_state(folder, code, d, order)
                    capblk = bool(sd.cap_blocking(code))
                    bs = sd.buysig.get(code) if tier == R.TIER_MAIN else None
                    rc = sd.receipt.get(code) if tier == R.TIER_MAIN else None
                    if tier == R.TIER_MAIN:
                        slog = F.signal_log_state(bs is not None, ran, sv.state in F.EVALUABLE_STATES and not capblk)
                        slog_v2 = F.signal_log_state(bs is not None, ran,
                                                     sv.state_v2 in F.EVALUABLE_STATES and not capblk)
                        slog_v1 = F.signal_log_state(bs is not None, ran, sv.eval_v1 and not capblk)
                    else:
                        slog = slog_v2 = slog_v1 = F.LOG_NA
                    used, basis = F.decide_signal(ev.signal, slog)
                    vm = LS8.volume_margin(folder, data, ev)
                    cands.append(dict(
                        d=d, folder=folder, code=code, tier=tier,
                        list_pos=pos_ if tier == R.TIER_MAIN else len(cl.main) + pos_,
                        snap_rank=ranks.get(code), list_src=cl.src, scan_date=scan, sector_mode=sd.sector_mode,
                        held=(sv.state == C.STATE_HELD), no_slot=(sv.state == C.STATE_NO_SLOT), slot_state=sv.state,
                        slot_state_v2=sv.state_v2, eval_v1=sv.eval_v1, slot_note=sv.note, ev=ev, buysig=bs,
                        receipt=rc, signal_log=slog, signal_log_v1=slog_v1, signal_log_v2=slog_v2,
                        signal_used=used, signal_basis=basis,
                        vol_ratio=vm[0] if vm else None, vol_threshold=vm[1] if vm else None,
                        reasons_equal=(_yn(bs.detail.get("reasons") == ev.reasons_str)
                                       if (bs is not None and ev.signal == "Y") else ""),
                        ref_equal=(_yn(abs(float(rc.detail["ref"]) - ev.ref) < 0.5)
                                   if (rc is not None and ev.ref is not None) else "")))
    # 관측 빈티지 — day 의 라이브 사유 `vol=a/b` 와 재현 사유를 맞대 D-1 거래량 재기록 폭을 잰다(데이터로 · 하드코딩 없음)
    pairs = [F.day_volume_vintage(c["buysig"].detail.get("reasons"), c["ev"].reasons_str) for c in cands
             if c["folder"] == LS8.DAY and c["buysig"] is not None and c["ev"].signal == "Y"]
    pairs = [x for x in pairs if x is not None]
    vintage = dict(n=len(pairs), vmin=min(pairs) if pairs else None, vmax=max(pairs) if pairs else None)
    for c in cands:
        bias = LS8.VOLUME_RULE_BIAS.get(c["folder"])
        c["vintage_fragile"] = (F.vintage_fragile(bias, c["ev"].signal, c["vol_ratio"], c["vol_threshold"],
                                                  vintage["vmax"]) if c["signal_basis"] == "replay" else "")
    return cands, offlist, vintage


def signal_fidelity_rows(cands: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for c in cands:
        if c["tier"] != R.TIER_MAIN:
            continue
        ev, bs, rc = c["ev"], c["buysig"], c["receipt"]
        margin = ((c["vol_ratio"] / c["vol_threshold"] - 1) * 100
                  if c["vol_ratio"] is not None and c["vol_threshold"] else None)
        rows.append(OrderedDict(
            date=c["d"].isoformat(), strategy=c["folder"], mode=R.corp_action_mode_for(c["folder"], c["d"]) or "",
            code=c["code"], list_pos=str(c["list_pos"]), slot_state=c["slot_state"],
            slot_state_v2=c["slot_state_v2"], eval_v1=_fmt(c["eval_v1"]), signal_replay=ev.signal,
            replay_reason=ev.reason[:60], signal_log=c["signal_log"], signal_log_v1=c["signal_log_v1"],
            signal_log_v2=c["signal_log_v2"], n_evals=str(bs.n) if bs else "", first_ts=bs.first if bs else "",
            last_ts=bs.last if bs else "", outcome=F.signal_outcome(ev.signal, c["signal_log"]),
            outcome_v1=F.signal_outcome(ev.signal, c["signal_log_v1"]),
            outcome_v2=F.signal_outcome(ev.signal, c["signal_log_v2"]),
            no_slot_but_log_y=_yn(c["slot_state"] == C.STATE_NO_SLOT and bs is not None),
            no_slot_but_log_y_v2=_yn(c["slot_state_v2"] == C.STATE_NO_SLOT and bs is not None),
            reasons_equal=c["reasons_equal"], ref_equal=c["ref_equal"],
            receipt_ref=_fmt(rc.detail.get("ref")) if rc else "", replay_ref=_fmt(ev.ref),
            signal_basis=c["signal_basis"], vol_ratio=_fmt(c["vol_ratio"]), vol_threshold=_fmt(c["vol_threshold"]),
            rule_margin_pct=_pct(margin), vintage_fragile=c["vintage_fragile"]))
    return rows


def fill_attribution_check(ctx: Ctx8, days: Sequence[date]) -> List[str]:
    """로그 `가상매수:` 줄의 전략 귀속(logscan8.attribute) ↔ 체결 원장 BUY — 귀속 규칙의 실데이터 검증."""
    out: List[str] = []
    for d in days:
        dl = ctx.log_for(d)
        if not dl.found:
            out.append(f"{d}: 로그 파일 없음")
            continue
        for folder in R.ALL_FOLDERS:
            log_codes = set(dl.get(folder).fills)
            vtr_codes = {t.code for t in ctx.buys_on(folder, d)}
            if log_codes != vtr_codes:
                out.append(f"{d} {folder}: 로그 가상매수 귀속 {sorted(log_codes)} ≠ 체결 원장 {sorted(vtr_codes)}")
    return out


def _print_signal_tables(sig_rows: Sequence[Dict[str, str]], vintage: Dict[str, Any]) -> None:
    """B 계산 «전에» 보는 표 — 방향별 일치 · 규칙 민감도(v1·v2·v3) · 재구성 모순 · 재현 비중."""
    def r_(x: Optional[float]) -> str:
        return "-" if x is None else f"{x * 100:.2f}%"
    print("\n== 신호 충실도 — 채택 규칙 v3 (E6 main ∩ `[on_tick] 매수신호`) · B 계산 전에 본다")
    print("group | 판정가능 | Y방향 둘다Y/로그Y | N방향 둘다N/로그N | 그중 bought | verdict | note")
    for g in F.signal_table(sig_rows):
        print(f"{g['group']} | {g['evaluable']} | {g['agree_Y']}/{g['y_n']} ({r_(g['y_rate'])}) | "
              f"{g['agree_N']}/{g['n_n']} ({r_(g['n_rate'])}) | {g['bought']} | {g['verdict']} | {g['verdict_note']}")
    print("\n== «평가 가능» 규칙 민감도 — v1 09:02 한 시점 · v2 classify_candidate · v3 v2+빈자리 구간 on_tick(채택)")
    t = {k: {g["group"]: g for g in F.signal_table(sig_rows, outcome_key=k)}
         for k in ("outcome_v1", "outcome_v2", "outcome")}
    for grp in t["outcome"]:
        cells = " | ".join(f"{k[-2:] if k != 'outcome' else 'v3'} {t[k][grp]['evaluable']}건 "
                           f"Y {r_(t[k][grp]['y_rate'])} N {r_(t[k][grp]['n_rate'])} {t[k][grp]['verdict']}"
                           for k in ("outcome_v1", "outcome_v2", "outcome"))
        print(f"{grp} | {cells}")
    n_v2 = sum(1 for r in sig_rows if r["no_slot_but_log_y_v2"] == "Y")
    n_v3 = sum(1 for r in sig_rows if r["no_slot_but_log_y"] == "Y")
    print(f"\n재구성 모순(no_slot 인데 로그 매수신호 있음): v2 {n_v2}건 → v3 {n_v3}건")
    rep = sum(1 for r in sig_rows if r["signal_basis"] == "replay")
    frag = sum(1 for r in sig_rows if r["vintage_fragile"] == "Y")
    print(f"main 후보 행 중 재현 신호 {rep}/{len(sig_rows)} · 빈티지 취약 {frag} · 관측 빈티지(day D-1 거래량) "
          f"n={vintage['n']} 범위 {r_(vintage['vmin'])}~{r_(vintage['vmax'])}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ledger8 — 8전략 세 arm 관측 원장")
    ap.add_argument("--start", default=R.LEDGER_START.isoformat())
    ap.add_argument("--end", default=R.LEDGER_END.isoformat())
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--log-dir", default=None, help="라이브 로그 폴더(읽기 전용)")
    ap.add_argument("--stage", choices=("signal",), default="signal")
    a = ap.parse_args(argv)
    out = Path(a.out)
    log_dir = _resolve_log_dir(a.log_dir)
    ctx = Ctx8.open(log_dir)
    try:
        days = T.days_in_range(ctx.calendar, date.fromisoformat(a.start), date.fromisoformat(a.end))
        if not days:
            print(f"거래일 없음: {a.start} ~ {a.end}")
            return 2
        print(f"로그 {log_dir} · 창 {days[0]}~{days[-1]} ({len(days)}거래일) · DB {bootstrap.DB_NAME}")
        warnings = fill_attribution_check(ctx, days)
        cands, offlist, vintage = evaluate_candidates(ctx, days)
        sig_rows = signal_fidelity_rows(cands)
        _atomic_write_csv(out / "fidelity_signal.csv", SIG_COLS, sig_rows)
        _atomic_write_csv(out / "offlist_signals.csv", OFF_COLS, offlist)
        _print_signal_tables(sig_rows, vintage)
        for w in warnings:
            print(f"[경고] {w}")
        meta = _meta(days, log_dir, a.stage, warnings)
        meta["vintage"] = vintage
        _atomic_write_text(out / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 기존 테스트 전부 통과 확인(회귀)**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests -q -p no:cacheprovider`
Expected: PASS(과제 1~3 테스트 전부). `run.py`·`context8.py`·`sources8.py` 는 DB 경계라 단위 테스트 대신 Step 5 실데이터 실행으로 검증한다.

- [ ] **Step 5: 신호 충실도 게이트 — 7거래일 실데이터(DB 읽기 전용)**

Run: `$PY -m backtest.concept_axes.ledger8.run --stage signal`
Expected:
- 첫 줄 `로그 D:\GIT\kis-trading-template\RoboTrader_template\logs · 창 2026-09-10~2026-09-18 (7거래일) · DB kis_template`.
- `[경고] … 로그 가상매수 귀속 … ≠ 체결 원장 …` 줄이 **0개**(과제 2 귀속 규칙의 실데이터 검증). 1개라도 나오면 그 날짜 로그에서 해당 종목 줄 앞뒤 5줄을 보고 멈춘다.
- 신호 충실도 표 8그룹(rs_leader 는 `[shadow]`·`[live]` 로 갈림 · deep_mr 은 후보 0이라 표에 없다) — 방향별 `둘다Y/로그Y` · `둘다N/로그N` · `그중 bought`. 그 아래 «평가 가능» 규칙 민감도(v1·v2·v3) 표 · `재구성 모순 v2 N건 → v3 M건` · `재현 신호 k/n · 빈티지 취약 · 관측 빈티지 범위` 줄.
- 참고값(계획 검증 실행 2차 · 판정 가능 · Y/로그Y · N/로그N · bought): elder 53 · 42/42 · 11/11 · 11 · envelope 6 · 6/6 · 0/0 · 6 · day 21 · 21/21 · 0/0 · 13(이유 문자열 일치 0/21 = 빈티지) · min 9 · 9/9 · 0/0 · 2 · ma20 19 · 19/19 · 0/0 · 7 · ma5 58 · 58/58 · 0/0 · 18 · rs[shadow] 31 · 31/31 · 0/0 · 14 · rs[live] 15 · 15/15 · 0/0 · 5 — 판정 전부 `ok`, elder 외 7그룹 비고 `N 방향 판정 불가(n=0<5)`. 민감도: v1 에서 day `N 0/17 LOW` · min N 0/3 · ma5 N 0/4 → v2·v3 에서 그 행들은 no_slot(판정 불가). 재구성 모순 v2 21 → v3 0. 재현 신호 194/406 · 빈티지 취약 1 · 관측 빈티지 21쌍 0.17%~24.33%.
- `results/fidelity_signal.csv` · `offlist_signals.csv` · `run_meta.json` 생성. 콘솔에 rs_leader `WARNING … [신호없음] … 진입 제외 «안 함»(mode=shadow)` 줄이 섞여 나온다 — 라이브 `_check_buy` 가 찍는 WARNING(부트스트랩은 INFO 이하만 끈다) · 라이브 로그 파일로는 안 간다(NullHandler) · 무해.

- [ ] **Step 6: 게이트 판정 — 멈출지 결정**

`verdict == "LOW"`(채택 v3 · 어느 방향이든) 인 그룹이 있으면 **과제 5 이후로 진행하지 말고** 관리자에게 표 전체 + 그 그룹의 `replay_only`/`log_only` 행 10개(`fidelity_signal.csv` 에서 `outcome` 으로 거름)를 보고한다. 관리자 결정: (a) 계속 — 그 전략 B 결과에 `[신호 충실도 낮음]` 을 붙인다(과제 10 보고서가 자동으로 붙임) (b) 원인 조사. `N 방향 판정 불가` 는 멈출 사유가 아니다 — 보고서 §0 이 «이 그룹의 재현 신호는 Y 쪽 오류를 잴 수 없다»로 자동 표기하고, §1-3 이 재현 비중을 함께 싣는다. 🔒 v1·v2 민감도 결과를 보고 규칙을 다시 바꾸지 말 것. 🔒 기준값(0.90)이나 규칙을 바꿔서 통과시키지 말 것.

- [ ] **Step 7: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| §4-2 E6 상위10 ∩ `[on_tick] 매수신호` 대조 · 전략별 일치율 표 · B 계산 «전에» | `--stage signal` · `_print_signal_table` · Step 5·6 | [ ] |
| #7 기준가 대조(env=ref_close · 🧾 는 보조) | `ref_equal`(receipt vs replay) | [ ] |
| 3-1 day 의 `vol=a/b` 대조 | `reasons_equal`(라이브 이유 문자열 = 재현 이유 문자열) | [ ] |
| 3-4 E6 목록 밖 `[on_tick] 매수신호` 건수 | `offlist_signals.csv` | [ ] |
| #18 폴더키 스냅샷 · D-1 불일치 표기 | `Ctx8.candidates` src | [ ] |
| envelope 판정 불가 · rs_leader 모드별 | `signal_table` 그룹 · Step 5 | [ ] |
| 귀속 규칙 실데이터 검증(#16③) | `fill_attribution_check` 경고 0 | [ ] |

- [ ] **Step 8: Commit(코드만 — 결과 파일은 과제 10 에서)**

```bash
git add backtest/concept_axes/ledger8/sources8.py backtest/concept_axes/ledger8/context8.py backtest/concept_axes/ledger8/run.py
git commit -F - <<'MSG'
feat(ledger8): 실행 문맥·체결 원장(수량 포함)·신호 충실도 단계 CLI

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```


---

### Task 5: exitsim8 — 봉 단위 청산 순서 엔진(순수)

**Files:**
- Create: `backtest/concept_axes/ledger8/exitsim8.py`
- Test: `backtest/concept_axes/ledger8/tests/test_exitsim8.py`

**Interfaces:**
- Consumes: 재사용 `cap_skip_ledger.sim.{Bar, simulate_exit, EXIT_TP, EXIT_SL, EXIT_MAX_HOLD, EXIT_OPEN}`(sim.py:28-35·87-153).
- Produces:
  - `ExitRules(tp: float, sl: float, max_hold_days: int, source: str = "")`(frozen)
  - `Pos(code, entry_date, entry_time, entry_price, qty, entry_basis, touch_bar=None)` — B2 는 `entry_price` = 합산 평단, `entry_time` = 첫 매수(또는 시계 리셋 시 마지막 추가매수) 시각 · `touch_bar` = D3′ 진입 뒤 분봉만 모은 봉
  - `ExitOut(status, reason, exit_date, price, ret_pct, hold_days, flags, phase)` · `.closed` — `phase` ∈ `PHASE_OPEN(09:00 보유기간·갭 익절) · PHASE_AFTER(09:02~) · PHASE_ENTRY(진입일)`
  - `LiftEntry(status, price, time, basis, touch_bar)` · `lift_entry(d, minutes: Sequence[Tuple[str, Bar]], lift_hhmmss, band_min, band_max) -> LiftEntry` — D3′ · 상태 `LIFT_FILLED LIFT_UNFILLABLE LIFT_NO_MINUTE LIFT_NOT_LIFTED`
  - `Probe = Callable[[Pos, date], Optional[str]]` — (포지션, 평가일 D+k) → 데이터 청산 사유 코드 또는 None
  - `PathT = Sequence[Tuple[int, date, Optional[Bar]]]`
  - `open_phase(pos, rules, k, bar, pending_max_hold=False) -> Optional[ExitOut]`
  - `after_open(pos, rules, k, day, bar, probe, touches=True) -> Optional[ExitOut]`
  - `entry_day(pos, rules, bar, probe) -> Optional[ExitOut]`
  - `simulate_lot(pos, rules, path, probe) -> ExitOut`
  - `mark_to_market(pos, last) -> ExitOut` (last = `(k, day, Bar)` 또는 None)
  - 상수 `BASIS_D_OPEN="D_open" BASIS_BAND="band_touch" BASIS_ACTUAL="actual" BASIS_LIFT="after_lift"` · `PHASE_OPEN PHASE_AFTER PHASE_ENTRY` · `FLAG_LIFT_ADD` · `EXIT_TP EXIT_SL EXIT_MAX_HOLD EXIT_OPEN` · 플래그 `FLAG_GAP_TP FLAG_SL_GAP_0905 FLAG_SL_TP_BOTH FLAG_K0_DATA FLAG_BAR_MISSING FLAG_MAXHOLD_DEFERRED FLAG_NO_D_TOUCH FLAG_TOUCH_SKIPPED_ADD FLAG_MTM`

- [ ] **Step 1: 실패하는 테스트 작성**

`backtest/concept_axes/ledger8/tests/test_exitsim8.py`:
```python
"""exitsim8 — 하루 청산 순서(보유기간 → 갭 익절 → 데이터 청산 → 갭 손절 → 터치) · 평단 이동 · 09:05 플래그."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

R10 = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=5, source="test")
DAYS = [date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15),
        date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]
FLAT = (100.0, 101.0, 99.0, 100.0)


def _pos(price: float = 100.0, basis: str = X.BASIS_D_OPEN) -> X.Pos:
    return X.Pos("000001", DAYS[0], datetime(2026, 9, 10, 9, 2), price, 10, basis)


def _path(*ohlc):
    return [(i, DAYS[i], None if b is None else Bar(DAYS[i], *b)) for i, b in enumerate(ohlc)]


def _no_probe(pos, day):
    return None


def _probe_on(hit_day, reason="trail_ma"):
    return lambda pos, day: reason if day == hit_day else None


def test_open_position_marks_to_last_close():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, FLAT, FLAT), _no_probe)
    assert ex.status == "open" and ex.reason == X.EXIT_OPEN and ex.exit_date == DAYS[2]
    assert ex.ret_pct == 0.0 and ex.hold_days == 2 and X.FLAG_MTM in ex.flags


def test_data_exit_sells_at_that_day_open():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, FLAT, (103.0, 104.0, 102.0, 103.0)), _probe_on(DAYS[2]))
    assert (ex.reason, ex.exit_date, ex.price, ex.hold_days) == ("trail_ma", DAYS[2], 103.0, 2)


def test_gap_tp_beats_data_exit():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, (111.0, 112.0, 110.0, 111.0)), _probe_on(DAYS[1]))
    assert ex.reason == X.EXIT_TP and ex.price == 111.0 and X.FLAG_GAP_TP in ex.flags


def test_max_hold_comes_first_at_open():
    path = _path(FLAT, FLAT, FLAT, FLAT, FLAT, (120.0, 121.0, 119.0, 120.0))   # k=5 시가 +20%
    ex = X.simulate_lot(_pos(), R10, path, _no_probe)
    assert ex.reason == X.EXIT_MAX_HOLD and ex.hold_days == 5 and ex.price == 120.0


def test_gap_down_sl_flags_0905():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, (90.0, 91.0, 89.0, 90.0)), _no_probe)
    assert ex.reason == X.EXIT_SL and ex.price == 90.0 and X.FLAG_SL_GAP_0905 in ex.flags


def test_same_bar_touch_prefers_sl():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, (100.0, 111.0, 91.0, 100.0)), _no_probe)
    assert ex.reason == X.EXIT_SL and ex.price == pytest.approx(92.0) and X.FLAG_SL_TP_BOTH in ex.flags


def test_average_price_moves_the_stop():
    path = _path(FLAT, (96.0, 97.0, 91.0, 95.0))
    assert X.simulate_lot(_pos(100.0), R10, path, _no_probe).reason == X.EXIT_SL   # 100×0.92=92 ≥ 91
    assert X.simulate_lot(_pos(98.0), R10, path, _no_probe).status == "open"        # 98×0.92=90.16 < 91


def test_d_open_entry_day_uses_day_touches():
    ex = X.simulate_lot(_pos(), R10, _path((100.0, 101.0, 91.0, 95.0)), _no_probe)
    assert ex.reason == X.EXIT_SL and ex.hold_days == 0


def test_band_touch_skips_entry_day_touches_but_probes():
    path = _path((100.0, 112.0, 90.0, 100.0), FLAT)
    ex = X.simulate_lot(_pos(basis=X.BASIS_BAND), R10, path, _no_probe)
    assert ex.status == "open" and X.FLAG_NO_D_TOUCH in ex.flags
    ex2 = X.simulate_lot(_pos(basis=X.BASIS_BAND), R10, path, _probe_on(DAYS[0]))
    assert (ex2.reason, ex2.hold_days, ex2.price) == ("trail_ma", 0, 100.0) and X.FLAG_K0_DATA in ex2.flags


def test_missing_bar_defers_max_hold():
    rules = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=2)
    ex = X.simulate_lot(_pos(), rules, _path(FLAT, FLAT, None, (101.0, 102.0, 100.0, 101.0)), _no_probe)
    assert ex.reason == X.EXIT_MAX_HOLD and ex.exit_date == DAYS[3] and X.FLAG_MAXHOLD_DEFERRED in ex.flags


def test_after_open_can_skip_touches():
    bar = Bar(DAYS[1], 100.0, 100.5, 85.0, 90.0)
    assert X.after_open(_pos(), R10, 1, DAYS[1], bar, _no_probe, touches=False) is None
    assert X.after_open(_pos(), R10, 1, DAYS[1], bar, _no_probe, touches=True).reason == X.EXIT_SL


def test_exit_phase_labels():
    assert X.simulate_lot(_pos(), R10, _path(FLAT, (111.0, 112.0, 110.0, 111.0)), _no_probe).phase == X.PHASE_OPEN
    assert X.simulate_lot(_pos(), R10, _path(FLAT, (90.0, 91.0, 89.0, 90.0)), _no_probe).phase == X.PHASE_AFTER
    assert X.simulate_lot(_pos(), R10, _path((100.0, 101.0, 91.0, 95.0)), _no_probe).phase == X.PHASE_ENTRY


def _mins(*rows):
    return [(t, Bar(DAYS[0], float(o), float(h), float(lo), float(c))) for t, o, h, lo, c in rows]


def test_lift_entry_first_in_band_minute_after_lift():
    mins = _mins(("09:23:00", 100, 100, 99, 100), ("09:24:00", 105, 105, 102, 104),
                 ("09:25:00", 103, 104, 101, 102), ("09:26:00", 101, 102, 95, 96))
    le = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0)
    # 09:23 봉은 해제 전 · 09:24 시가 105 > 상한 103 이나 저가 102 ≤ 103 → 경계 103 · 터치 봉은 다음 분봉(09:25)부터
    assert (le.status, le.price, le.time, le.basis) == (X.LIFT_FILLED, 103.0, "09:24:00", "minute_band_touch")
    tb = le.touch_bar
    assert (tb.open, tb.high, tb.low, tb.close) == (103.0, 104.0, 95.0, 96.0)


def test_lift_entry_statuses():
    above = _mins(("09:30:00", 110, 111, 109, 110))
    assert X.lift_entry(DAYS[0], above, "09:23:09", None, 103.0).status == X.LIFT_UNFILLABLE
    assert X.lift_entry(DAYS[0], [], "09:23:09", None, 103.0).status == X.LIFT_NO_MINUTE
    assert X.lift_entry(DAYS[0], above, "", None, 103.0).status == X.LIFT_NOT_LIFTED


def test_after_lift_entry_day_uses_post_entry_bar_only():
    tb = Bar(DAYS[0], 100.0, 101.0, 91.0, 95.0)          # 진입 뒤 저가 91 → 손절
    day_bar = (98.0, 101.0, 80.0, 95.0)                    # 일봉 저가 80 은 진입 «전» 일 수 있다 — 쓰면 안 된다
    pos = X.Pos("000001", DAYS[0], datetime(2026, 9, 10, 9, 24), 100.0, 10, X.BASIS_LIFT, touch_bar=tb)
    ex = X.simulate_lot(pos, R10, _path(day_bar), _no_probe)
    assert (ex.reason, ex.hold_days, ex.phase) == (X.EXIT_SL, 0, X.PHASE_ENTRY) and ex.price == pytest.approx(92.0)
    pos2 = X.Pos("000001", DAYS[0], datetime(2026, 9, 10, 9, 24), 100.0, 10, X.BASIS_LIFT)
    assert X.simulate_lot(pos2, R10, _path(day_bar), _no_probe).status == "open"
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_exitsim8.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'exitsim8'`.

- [ ] **Step 3: `exitsim8.py` 작성**

```python
"""청산 재현 — 순수(DB·전략 인스턴스 없음 · 데이터 청산은 주입된 탐침). 8전략 공통 1벌(스펙 검증표 #2).

라이브 하루의 청산 순서 (2026-09-19 코드 실측)
  07:40 복원  days_held = k — count_trading_days_between(매수시각, 07:40)(bot/state_restorer.py:388-392)
  09:00~      position_monitor 매 반복(core/trading/position_monitor.py:200-335)
                ① 보유기간  days_held ≥ strategy.max_holding_days → 현재가 매도        (:251-285)
                ② 익절      (현재가 − 평단)/평단 ≥ target_profit_rate                   (:314-323)
                ③ 손절      09:05 이후만(:219-224 · :326) · (현재가 − 평단)/평단 ≤ −stop_loss_rate (:327-335)
  09:0x       on_tick 매도 루프 → generate_signal(D-1 확정봉, 'daily') → 보유 분기 → _check_sell (strategies/base.py:739-761)
  ⇒ 일봉 근사: [보유기간 → 갭 익절](시가 · phase=open0900) → [데이터 청산](시가) → [갭 손절](시가 · 라이브는 09:05 이후
     가격 → 플래그) → 장중 고저 터치(동시면 손절 우선) — 뒤의 셋은 phase=after0902.
  평단 = position.avg_price(:215) ⇒ B2 는 합산 평단을 `Pos.entry_price` 로 넣는다.
갭 손절·장중 터치·동시 터치 손절 우선은 `cap_skip_ledger/sim.py::simulate_exit`(:87-153)를 봉 1개씩 불러 그대로 쓴다.
진입일(k=0): 탐침 1회(라이브는 매수 직후 같은 날 on_tick 매도 루프가 D-1 확정봉으로 `_check_sell`) → 진입 «이후» 고저만
  터치 판정 — basis=D_open 은 D 일봉 전체 · after_lift(D3′)는 진입 분봉 뒤 분봉만 모은 봉(`Pos.touch_bar`) ·
  band_touch·actual(시각 불명)은 진입일 고저를 쓰지 않는다.
D3′(급락 게이트 = 풀린 뒤 산다): `lift_entry` 가 해제 시각 뒤 분봉을 차례로 `sim.simulate_entry` 에 넣어 첫 체결을 찾는다.
🔴 일봉으로 안 되는 것 — 갭다운 손절 체결가(라이브 09:05 가격) · 폴링이 놓친 짧은 꼬리 · 같은 날 청산 후 재진입 — 플래그로만.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import sim as S
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

BASIS_D_OPEN = "D_open"
BASIS_BAND = "band_touch"
BASIS_ACTUAL = "actual"
BASIS_LIFT = "after_lift"

PHASE_OPEN = "open0900"        # 09:00 — position_monitor 보유기간·갭 익절(09:02 진입 «전»)
PHASE_AFTER = "after0902"      # 09:02~ — 데이터 청산·갭 손절·장중 터치
PHASE_ENTRY = "entry_day"      # 진입 당일

EXIT_TP = S.EXIT_TP
EXIT_SL = S.EXIT_SL
EXIT_MAX_HOLD = S.EXIT_MAX_HOLD
EXIT_OPEN = S.EXIT_OPEN

FLAG_GAP_TP = "gap_tp_open"
FLAG_SL_GAP_0905 = "sl_gap_open(라이브는 09:05 이후 가격)"
FLAG_SL_TP_BOTH = "sl_tp_same_bar(손절 우선)"
FLAG_K0_DATA = "k0_data_exit(가격=진입가 근사)"
FLAG_BAR_MISSING = "bar_missing"
FLAG_MAXHOLD_DEFERRED = "max_hold_deferred(결측 다음 봉 시가)"
FLAG_NO_D_TOUCH = "entry_day_touch_skipped(진입 시각 불명)"
FLAG_TOUCH_SKIPPED_ADD = "add_day_touch_skipped(band_touch 추가매수)"
FLAG_LIFT_ADD = "add_after_lift(그날 청산 판정은 기존 평단으로 먼저)"
FLAG_MTM = "mark_to_market(마지막 종가)"

LIFT_FILLED = "filled"
LIFT_UNFILLABLE = "unfillable"
LIFT_NO_MINUTE = "no_minute_data"
LIFT_NOT_LIFTED = "not_lifted"


@dataclass(frozen=True)
class ExitRules:
    tp: float
    sl: float
    max_hold_days: int
    source: str = ""


@dataclass
class Pos:
    code: str
    entry_date: date
    entry_time: datetime
    entry_price: float
    qty: int
    entry_basis: str
    touch_bar: Optional[Bar] = None      # after_lift — 진입 뒤 분봉만 모은 D 봉(진입일 터치용)


@dataclass
class ExitOut:
    status: str                      # closed | open
    reason: str                      # tp | sl | max_hold | <데이터 청산 exit_reason> | open
    exit_date: Optional[date]
    price: Optional[float]
    ret_pct: Optional[float]
    hold_days: Optional[int]
    flags: List[str] = field(default_factory=list)
    phase: str = ""

    @property
    def closed(self) -> bool:
        return self.status == "closed"


Probe = Callable[[Pos, date], Optional[str]]
PathT = Sequence[Tuple[int, date, Optional[Bar]]]
MinuteBar = Tuple[str, Bar]          # (분봉 시작 HH:MM:SS, OHLC)


def _never(_k: int) -> bool:
    return False


def _rate(entry: float, px: float) -> float:
    return (float(px) - float(entry)) / float(entry)


def _closed(reason: str, d: date, px: float, pos: Pos, k: int, flags: List[str], phase: str) -> ExitOut:
    return ExitOut("closed", reason, d, float(px), _rate(pos.entry_price, px) * 100.0, k, list(flags), phase)


def _from_sim(ex: S.Exit, k: int, phase: str) -> Optional[ExitOut]:
    if ex.status != "closed":
        return None
    flags: List[str] = []
    if "갭 손절(시가)" in ex.notes:
        flags.append(FLAG_SL_GAP_0905)
    if "갭 익절(시가)" in ex.notes:
        flags.append(FLAG_GAP_TP)
    if any("모두 닿음" in n for n in ex.notes):
        flags.append(FLAG_SL_TP_BOTH)
    return ExitOut("closed", ex.reason, ex.exit_date, ex.price, ex.ret_pct, k, flags, phase)


def open_phase(pos: Pos, rules: ExitRules, k: int, bar: Bar, pending_max_hold: bool = False) -> Optional[ExitOut]:
    """09:00 — position_monitor 보유기간 → 익절(시가). 손절은 09:05 전이라 여기서 안 본다."""
    if pending_max_hold or k >= rules.max_hold_days:
        return _closed(EXIT_MAX_HOLD, bar.d, bar.open, pos, k,
                       [FLAG_MAXHOLD_DEFERRED] if pending_max_hold else [], PHASE_OPEN)
    if _rate(pos.entry_price, bar.open) >= rules.tp:
        return _closed(EXIT_TP, bar.d, bar.open, pos, k, [FLAG_GAP_TP], PHASE_OPEN)
    return None


def after_open(pos: Pos, rules: ExitRules, k: int, day: date, bar: Bar, probe: Probe,
               touches: bool = True) -> Optional[ExitOut]:
    """09:0x 데이터 청산(시가) → (touches 면) 갭 손절·장중 터치(sim.simulate_exit 봉 1개)."""
    r = probe(pos, day)
    if r:
        return _closed(r, day, bar.open, pos, k, [], PHASE_AFTER)
    if not touches:
        return None
    return _from_sim(S.simulate_exit(pos.entry_price, BASIS_BAND, None, [(k, bar)], rules.sl, rules.tp, _never),
                     k, PHASE_AFTER)


def entry_day(pos: Pos, rules: ExitRules, bar: Optional[Bar], probe: Probe) -> Optional[ExitOut]:
    """k=0 — 진입 당일. 터치는 진입 «이후» 고저만(D_open = D 봉 · after_lift = touch_bar · 그 밖 = 안 봄)."""
    if bar is None:
        return None
    r = probe(pos, pos.entry_date)
    if r:
        return _closed(r, pos.entry_date, pos.entry_price, pos, 0, [FLAG_K0_DATA], PHASE_ENTRY)
    touch = bar if pos.entry_basis == BASIS_D_OPEN else pos.touch_bar
    if touch is None:
        return None
    return _from_sim(S.simulate_exit(pos.entry_price, BASIS_D_OPEN, touch, [], rules.sl, rules.tp, _never),
                     0, PHASE_ENTRY)


def mark_to_market(pos: Pos, last: Optional[Tuple[int, date, Bar]], flags: Sequence[str] = ()) -> ExitOut:
    if last is None:
        return ExitOut("open", EXIT_OPEN, None, None, None, None, list(flags) + ["no_bar"])
    k, day, bar = last
    return ExitOut("open", EXIT_OPEN, day, float(bar.close), _rate(pos.entry_price, bar.close) * 100.0, k,
                   list(flags) + [FLAG_MTM])


def simulate_lot(pos: Pos, rules: ExitRules, path: PathT, probe: Probe) -> ExitOut:
    """로트 1개(B1 · A_sim · 청산 충실도) — path[0] 은 진입일(k=0)."""
    if not path:
        return ExitOut("open", EXIT_OPEN, None, None, None, None, ["no_path"])
    _, d0, bar0 = path[0]
    touch_ok = pos.entry_basis == BASIS_D_OPEN or pos.touch_bar is not None
    flags: List[str] = [] if touch_ok else [FLAG_NO_D_TOUCH]
    ex = entry_day(pos, rules, bar0, probe)
    if ex is not None:
        ex.flags = flags + ex.flags
        return ex
    last: Optional[Tuple[int, date, Bar]] = (0, d0, bar0) if bar0 is not None else None
    pending = False
    for k, day, bar in list(path)[1:]:
        if bar is None:
            flags.append(f"{FLAG_BAR_MISSING}:{day}")
            if k >= rules.max_hold_days:
                pending = True
            continue
        ex = open_phase(pos, rules, k, bar, pending) or after_open(pos, rules, k, day, bar, probe)
        if ex is not None:
            ex.flags = flags + ex.flags
            return ex
        last = (k, day, bar)
    return mark_to_market(pos, last, flags)


@dataclass
class LiftEntry:
    status: str                          # filled | unfillable | no_minute_data | not_lifted
    price: Optional[float] = None
    time: str = ""                       # 체결로 본 분봉의 시작 시각 HH:MM:SS
    basis: str = ""                      # minute_open | minute_band_touch
    touch_bar: Optional[Bar] = None      # 진입 «이후» 분봉만 모은 D 봉(시가 = 진입가)


def lift_entry(d: date, minutes: Sequence[MinuteBar], lift_hhmmss: str, band_min: Optional[float],
               band_max: Optional[float]) -> LiftEntry:
    """D3′ — 급락 게이트가 풀린 뒤 첫 매수 밴드 안 가격(스펙 「추가 결정」).

    분봉 시작 시각 ≥ 해제 시각인 봉만 본다(해제 시각이 든 분봉엔 해제 전 가격이 섞인다). 각 분봉을
    `sim.simulate_entry` 에 그대로 넣는다 — 시가가 밴드 안이면 그 시가(basis=minute_open), 시가 밖·봉 안 복귀면
    밴드 경계값(minute_band_touch · 그 분 안 시각 불명). 끝까지 없으면 unfillable. 진입일 터치용 봉은
    minute_open 이면 그 분봉부터, band_touch 면 «다음» 분봉부터 모은다(진입 시각 이후만).
    """
    if not lift_hhmmss:
        return LiftEntry(LIFT_NOT_LIFTED)
    if not minutes:
        return LiftEntry(LIFT_NO_MINUTE)
    after = [(t, b) for t, b in minutes if t >= lift_hhmmss]
    for i, (t, b) in enumerate(after):
        ent = S.simulate_entry(b, band_min, band_max)
        if ent.status != S.ENTRY_FILLED:
            continue
        rest = after[i:] if ent.basis == BASIS_D_OPEN else after[i + 1:]
        touch = (Bar(d, float(ent.price), max(x.high for _, x in rest), min(x.low for _, x in rest),
                     float(rest[-1][1].close)) if rest else None)
        return LiftEntry(LIFT_FILLED, float(ent.price), t,
                         "minute_open" if ent.basis == BASIS_D_OPEN else "minute_band_touch", touch)
    return LiftEntry(LIFT_UNFILLABLE)
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_exitsim8.py -q -p no:cacheprovider`
Expected: PASS(15 passed).

- [ ] **Step 5: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| 3-2 매도 공통 1벌 · 파라미터 매핑 0 | `ExitRules`(tp/sl/max_hold 는 과제 6 이 라이브 경로로 채움) · 데이터 청산은 `Probe` | [ ] |
| 3-2 평균매입가 대비 판정 · B2 평단 | `Pos.entry_price` · `test_average_price_moves_the_stop` | [ ] |
| 3-2 09:00~09:05 손절 보류 플래그 | `FLAG_SL_GAP_0905` · `test_gap_down_sl_flags_0905` | [ ] |
| 3-2 고가·저가 동시 터치 = 손절 우선(sim.py 재사용) | `_from_sim`(sim.simulate_exit 호출) · `test_same_bar_touch_prefers_sl` | [ ] |
| 3-2 데이터 청산 = D+k-1 확정봉으로 D+k 첫 틱 | `after_open`(탐침에 D+k 전달 · 창 마지막 봉은 D+k-1) · `test_data_exit_sells_at_that_day_open` | [ ] |
| 3-2 보유기간 = `days_held=k` 같은 날 발동 | `open_phase` · `test_max_hold_comes_first_at_open` | [ ] |
| 3-2 같은 날 순서(익절 → 데이터 → 손절) | `open_phase` → `after_open` · `test_gap_tp_beats_data_exit` | [ ] |
| 3-3 밴드 터치 체결은 D 고저를 청산에 안 씀 | `entry_day` · `test_band_touch_skips_entry_day_touches_but_probes` | [ ] |
| 3-8 `test_exitsim8`(전날 봉 trail · 평단 이동 · 09:05) | 위 테스트 | [ ] |
| D3′ 해제 뒤 첫 밴드 안 분봉 · 진입일은 진입 이후 고저만 | `lift_entry` · `entry_day`(touch_bar) · `test_lift_entry_*` · `test_after_lift_entry_day_uses_post_entry_bar_only` | [ ] |
| critic 🟡1 청산 단계(09:00 시가 vs 09:02 뒤) 구분 | `ExitOut.phase` · `test_exit_phase_labels` | [ ] |

- [ ] **Step 6: Commit**

```bash
git add backtest/concept_axes/ledger8/exitsim8.py backtest/concept_axes/ledger8/tests/test_exitsim8.py
git commit -F - <<'MSG'
feat(ledger8): 청산 순서 엔진 — 보유기간·갭 익절·데이터 청산·09:05 손절 플래그·손절 우선

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 6: sellprobe8 + 청산·익절손절 충실도 + run `--stage exit` + 청산 충실도 게이트(실데이터)

**Files:**
- Create: `backtest/concept_axes/ledger8/sellprobe8.py`
- Modify: `backtest/concept_axes/ledger8/fidelity8.py`(청산 부분 추가 — 파일 끝에 덧붙임)
- Modify: `backtest/concept_axes/ledger8/context8.py`(필드 2개 + `attach_exit_probes`)
- Modify: `backtest/concept_axes/ledger8/run.py`(import · 청산 충실도 함수 · `main` 교체)
- Test: `backtest/concept_axes/ledger8/tests/test_sellprobe8.py`, `backtest/concept_axes/ledger8/tests/test_fidelity8.py`(추가)

**Interfaces:**
- Consumes: `exitsim8.ExitRules · Pos · simulate_lot · BASIS_D_OPEN · BASIS_ACTUAL`(과제 5) · `Ctx8`(과제 4) · `sources8.as_of · aware`(과제 4) · 라이브 `core.trading_decision_engine.TradingDecisionEngine`(:39-56 생성자 · :90 `set_strategies` · :499 `execute_virtual_buy`) · `core.models.TradingStock(stock_code, stock_name, state, selected_time)`·`StockState` · `strategies.base.SignalType`.
- Produces:
  - `sellprobe8.resolve_live_tp_sl(folder, strategy) -> ExitRules`
  - `sellprobe8.SellProbe(folder, strategy, window_fn)` · `__call__(pos, day) -> Optional[str]` · `.calls`
  - `fidelity8.actual_reason(text) -> str` · `exit_outcome(actual_reason, actual_date, sim_reason, sim_date) -> str` · `exit_table(rows) -> List[Dict]` · `rates_equal(a, b) -> bool` · `tp_sl_table(rows) -> List[Dict]` · `entry_diff_stats(rows) -> List[Dict]`
  - `Ctx8.rules: Dict[str, ExitRules]` · `Ctx8.probes: Dict[str, SellProbe]` · `Ctx8.attach_exit_probes() -> None`
  - `run.exit_fidelity_rows(ctx, since, until) -> List[Dict[str, str]]` · `run.EXIT_COLS` · `run.EARLY_FILL`

- [ ] **Step 1: 실패하는 테스트 작성**

`backtest/concept_axes/ledger8/tests/test_sellprobe8.py`:
```python
"""sellprobe8 — 라이브 엔진 경로 tp/sl · 매도 탐침(generate_signal → _check_sell) — 합성 프레임 · DB 없음."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import livesignal8 as LS8
from backtest.concept_axes.ledger8 import registry as R
from backtest.concept_axes.ledger8 import sellprobe8 as SP
from backtest.concept_axes.ledger8 import sources8 as SRC8


@pytest.fixture(scope="module")
def strategies():
    return {f: LS8.load8(f) for f in R.ALL_FOLDERS}


def _rising(n: int = 90, last: float = 118.0) -> pd.DataFrame:
    days = pd.bdate_range(end="2026-09-16", periods=n)
    close = np.linspace(100.0, 130.0, n)
    close[-1] = last
    return pd.DataFrame({"date": days, "open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": np.full(n, 1e5)})


def _crash(n: int = 90) -> pd.DataFrame:
    days = pd.bdate_range(end="2026-09-09", periods=n)
    close = np.full(n, 100.0)
    close[-1] = 60.0
    return pd.DataFrame({"date": days, "open": close, "high": close, "low": close, "close": close,
                         "volume": np.full(n, 1e5)})


def _pos(entry: float, day: date = date(2026, 9, 10)) -> X.Pos:
    return X.Pos("000001", day, SRC8.aware(datetime.combine(day, SRC8.FIRST_TICK)), entry, 10, X.BASIS_D_OPEN)


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_tp_sl_from_engine_path_matches_config(strategies, folder):
    s = strategies[folder]
    rules = SP.resolve_live_tp_sl(folder, s)
    rm = s.config["risk_management"]
    assert rules.tp == pytest.approx(float(rm["take_profit_pct"]))
    assert rules.sl == pytest.approx(max(float(rm["stop_loss_pct"]), 0.03))    # 손절 하한 3% (engine :655-658)
    assert rules.max_hold_days == int(s.max_holding_days)
    assert s.positions == {} and s.daily_trades == 0                            # on_order_filled 는 사본에만


def test_probe_trail_exit_and_no_exit_when_losing(strategies):
    probe = SP.SellProbe("book_pullback_ma20", strategies["book_pullback_ma20"], lambda code, d: (_rising(), {}))
    assert probe(_pos(110.0), date(2026, 9, 17)) == "trail_ma"      # 수익 중 · 종가 < MA20
    assert probe(_pos(125.0), date(2026, 9, 17)) is None             # 손실 중 → trail 없음
    assert probe.inst.positions == {} and strategies["book_pullback_ma20"].positions == {}


def test_probe_respects_min_len_guard_like_live_sell_loop(strategies):
    probe = SP.SellProbe("elder_ema_pullback", strategies["elder_ema_pullback"], lambda code, d: (_rising(n=50), {}))
    assert probe(_pos(110.0), date(2026, 9, 17)) is None              # generate_signal 의 min_len(70) 가드


def test_probe_max_hold_counts_trading_days_by_patched_clock(strategies):
    s = strategies["deep_mr_dev20"]
    probe = SP.SellProbe("deep_mr_dev20", s, lambda code, d: (_crash(), {}))
    pos = _pos(100.0, date(2026, 9, 1))
    assert probe(pos, date(2026, 9, 9)) is None                        # hold 6 < 7
    assert probe(pos, date(2026, 9, 10)) == "max_hold"                 # hold 7 ≥ 7


def test_probe_no_data_returns_none(strategies):
    probe = SP.SellProbe("rs_leader", strategies["rs_leader"], lambda code, d: (None, {}))
    assert probe(_pos(100.0), date(2026, 9, 17)) is None and probe.calls == 0
```

`backtest/concept_axes/ledger8/tests/test_fidelity8.py` 끝에 추가:
```python
# ── 청산·익절손절·진입가 ────────────────────────────────────────────────────
def test_actual_reason_mapping():
    assert F.actual_reason("목표 익절 도달 (10.12% >= 10.00%)") == "tp"
    assert F.actual_reason("손절 실행 (-8.10% <= -8.00%)") == "sl"
    assert F.actual_reason("보유기간 10일 초과 (한도: 10일)") == "max_hold"
    assert F.actual_reason("최대 보유일 초과 (10거래일)") == "max_hold"
    assert F.actual_reason("EMA13 trailing 이탈 (종가 1 < EMA13 2)") == "trail_ema"
    assert F.actual_reason("EMA65 추세반전 청산") == "trend_flip"
    assert F.actual_reason("MA20 trailing 이탈 (종가 1 < MA20 2)") == "trail_ma"
    assert F.actual_reason("MA20×0.9 회복 (종가 1 ≥ 2)") == "ma_recovery"
    assert F.actual_reason("MA20 이탈 (종가 1 < MA 2)") == "ma_break"
    assert F.actual_reason("장기보유 종목 우선 청산: 수익률 1.00% (보유 31일)") == "stale"
    assert F.actual_reason("알 수 없는 사유") == "other:알 수 없는 사유"


def test_exit_outcome():
    d1, d2 = date(2026, 9, 11), date(2026, 9, 14)
    assert F.exit_outcome("tp", d1, "tp", d1) == "Y"
    assert F.exit_outcome("tp", d1, "tp", d2) == "reason_only"
    assert F.exit_outcome("sl", d1, "tp", d1) == "N"
    assert F.exit_outcome("sl", d1, "open", None) == "actual_only_closed"
    assert F.exit_outcome("open", None, "sl", d1) == "sim_only_closed"
    assert F.exit_outcome("open", None, "open", None) == "both_open"


def test_exit_table_denominator_is_actual_closed():
    rows = ([dict(strategy="rs_leader", outcome="Y", actual_reason="ma_break", same_day_actual="N")] * 6
            + [dict(strategy="rs_leader", outcome="actual_only_closed", actual_reason="sl", same_day_actual="Y")] * 2
            + [dict(strategy="rs_leader", outcome="both_open", actual_reason="open", same_day_actual="")] * 3)
    t = F.exit_table(rows)[0]
    assert (t["closed"], t["Y"], t["same_day"]) == (8, 6, 2)
    assert t["reason_rate"] == 0.75 and t["verdict"] == "ok"


def test_tp_sl_table_and_entry_diff_stats():
    rows = [dict(strategy="book_pullback_ma5", tp_sl_match="Y")] * 3 + [dict(strategy="book_pullback_ma5", tp_sl_match="N")]
    t = F.tp_sl_table(rows)[0]
    assert (t["n"], t["match"]) == (4, 3)
    e = {g["strategy"]: g for g in F.entry_diff_stats([
        dict(strategy="a", entry_diff_pct="+1.00", first_tick="Y"),
        dict(strategy="a", entry_diff_pct="-0.50", first_tick="N"),
        dict(strategy="a", entry_diff_pct="", first_tick="N")])}
    assert e["a"]["n"] == 2 and e["a"]["positive"] == 1 and e["a"]["signed_mean"] == pytest.approx(0.25)
    assert e["a"]["signed_mean_first"] == pytest.approx(1.0) and e["(전체)"]["n"] == 2
```
(머리 import — `date` · `pytest` · `F` — 는 과제 3 판에 이미 있다.)

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_sellprobe8.py backtest/concept_axes/ledger8/tests/test_fidelity8.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'sellprobe8'` · `AttributeError: module ... fidelity8 has no attribute 'actual_reason'`.

- [ ] **Step 3: `sellprobe8.py` 작성**

```python
"""라이브 청산 규칙을 «라이브 코드로» 얻는다 — 익절·손절 비율(엔진 경로) + 데이터 청산(전략 매도 분기).

1. `resolve_live_tp_sl` — `TradingDecisionEngine.execute_virtual_buy`(core/trading_decision_engine.py:499-714)를
   그대로 부르되 `virtual_trading` 자리에 인자만 받아 적는 스텁을 끼운다(DB 0 · 기록 0).
   라이브 호출부(bot/trading_analyzer.py:275-281)처럼 tp/sl 인자를 넘기지 않으므로 3순위(전략 config
   `take_profit_pct`/`stop_loss_pct`, :589-607) → 4순위 기본값(:611-634) → 손절 하한 3%(:655-658)가 그대로 돈다.
   `on_order_filled` 통보(:703-710)는 전략 «사본»에만 간다.
2. `SellProbe` — 라이브 `on_tick` 매도 루프(strategies/base.py:739-761) 한 번을 재현한다.
   보유 종목 → generate_signal(code, D+k 일봉 창(마지막 봉 D+k−1), 'daily') → (min_len · timeframe 게이트) →
   보유 분기 → `_check_sell`. 전략 모듈의 `now_kst` 를 D+k 09:02 로 바꿔 끼워 보유일 계산식 두 벌
   (`count_trading_days_between(...)-1` · `_trading_days_elapsed`)을 코드 그대로 쓴다.
"""
from __future__ import annotations

import asyncio
import copy
import importlib
from datetime import date, datetime
from typing import Any, Callable, Dict, Optional, Tuple
from unittest import mock

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

from core.models import StockState, TradingStock                  # noqa: E402
from core.trading_decision_engine import TradingDecisionEngine    # noqa: E402
from strategies.base import SignalType                            # noqa: E402

from . import sources8 as SRC8
from .exitsim8 import ExitRules, Pos

WindowFn = Callable[[str, date], Tuple[Any, Dict]]


class _CaptureVTM:
    """`VirtualTradingManager.execute_virtual_buy` 자리 — 인자만 받아 적고 기록 ID 1 을 돌려준다(DB 0)."""

    def __init__(self) -> None:
        self.kwargs: Dict[str, Any] = {}

    def execute_virtual_buy(self, **kwargs: Any) -> int:
        self.kwargs = dict(kwargs)
        return 1


def resolve_live_tp_sl(folder: str, strategy) -> ExitRules:
    eng = TradingDecisionEngine()
    cap = _CaptureVTM()
    eng.virtual_trading = cap
    eng.set_strategies({folder: copy.deepcopy(strategy)})
    ts = TradingStock(stock_code="000000", stock_name="ledger8-probe", state=StockState.SELECTED,
                      selected_time=datetime(2026, 1, 1))
    ok = asyncio.run(eng.execute_virtual_buy(ts, None, "ledger8 tp/sl probe", buy_price=10_000.0, quantity=1,
                                             strategy_name=folder))
    if not ok or "target_profit_rate" not in cap.kwargs:
        raise RuntimeError(f"{folder}: 엔진 경로로 tp/sl 을 못 얻었다")
    tp, sl = float(cap.kwargs["target_profit_rate"]), float(cap.kwargs["stop_loss_rate"])
    if (tp, sl) != (float(ts.target_profit_rate), float(ts.stop_loss_rate)):
        raise RuntimeError(f"{folder}: VTM 인자와 trading_stock 값이 다르다 ({tp},{sl}) vs "
                           f"({ts.target_profit_rate},{ts.stop_loss_rate})")
    rm = (getattr(strategy, "config", None) or {}).get("risk_management", {})
    src = ("config(take_profit_pct/stop_loss_pct)"
           if rm.get("take_profit_pct") is not None and rm.get("stop_loss_pct") is not None
           else "⚠️ 기본값·비율키 경로 — 엔진 config 미주입")
    return ExitRules(tp=tp, sl=sl, max_hold_days=int(strategy.max_holding_days), source=src)


class SellProbe:
    """(포지션, 평가일 D+k) → 데이터 청산 사유 코드(`metadata['exit_reason']`) 또는 None."""

    def __init__(self, folder: str, strategy, window_fn: WindowFn):
        if getattr(strategy, "_quant", None) is not None:
            raise RuntimeError("SellProbe 는 _check_buy 호출 «전»에 만들어야 한다(envelope DB 리더 deepcopy 방지)")
        self.folder = folder
        self.inst = copy.deepcopy(strategy)
        self.inst.positions = {}
        self.inst.daily_trades = 0
        self.mod = importlib.import_module(type(strategy).__module__)
        self.window_fn = window_fn
        self.calls = 0

    def __call__(self, pos: Pos, day: date) -> Optional[str]:
        data, _diag = self.window_fn(pos.code, day)
        if data is None or len(data) == 0:          # base.py:748 과 같은 조건
            return None
        self.inst.positions = {pos.code: {"quantity": int(pos.qty), "entry_price": float(pos.entry_price),
                                          "entry_time": pos.entry_time}}
        try:
            with mock.patch.object(self.mod, "now_kst", return_value=SRC8.as_of(day)):
                sig = self.inst.generate_signal(pos.code, data, timeframe="daily")
        finally:
            self.inst.positions = {}
        self.calls += 1
        if sig is None or sig.signal_type not in (SignalType.SELL, SignalType.STRONG_SELL):
            return None
        return str((sig.metadata or {}).get("exit_reason") or "strategy_sell")
```

- [ ] **Step 4: `fidelity8.py` 끝에 청산 부분 덧붙이기**

파일 머리 import(`re` · `date` · `Optional`)는 과제 3 판에 이미 있다. 파일 끝에 추가:
```python
# ── ③ 청산 · 익절손절 · 진입가 ─────────────────────────────────────────────
# 실제 매도 사유(vtr.reason) → 시뮬 사유 코드. position_monitor 문자열(:282·:317-320·:330-333·:229-244)과
# 전략 매도 신호 사유(', '.join(signal.reasons) — 각 전략 evaluate_sell_conditions)를 앞머리로 가른다.
_ACTUAL_RULES = (
    (re.compile(r"^목표 익절 도달"), "tp"),
    (re.compile(r"^손절 실행"), "sl"),
    (re.compile(r"^보유기간 \d+일 초과"), "max_hold"),
    (re.compile(r"^최대 보유일 초과"), "max_hold"),
    (re.compile(r"^EMA\d+ trailing 이탈"), "trail_ema"),
    (re.compile(r"^EMA\d+ 추세반전"), "trend_flip"),
    (re.compile(r"^MA\d+ trailing 이탈"), "trail_ma"),
    (re.compile(r"^MA\d+×[\d.]+ 회복"), "ma_recovery"),
    (re.compile(r"^MA\d+ 이탈"), "ma_break"),
    (re.compile(r"^장기보유 종목"), "stale"),
)


def actual_reason(text: Optional[str]) -> str:
    t = (text or "").strip()
    for rx, code in _ACTUAL_RULES:
        if rx.match(t):
            return code
    return f"other:{t[:20]}"


def exit_outcome(actual: str, actual_date: Optional[date], sim: str, sim_date: Optional[date]) -> str:
    if actual == "open" and sim == "open":
        return "both_open"
    if actual == "open":
        return "sim_only_closed"
    if sim == "open":
        return "actual_only_closed"
    if actual == sim:
        return "Y" if actual_date == sim_date else "reason_only"
    return "N"


def exit_table(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """전략별 청산 일치. 분모 = «실제 청산된» 건(actual_reason != open) — 시뮬만 열려 있으면 불일치로 센다."""
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        g = groups.setdefault(r["strategy"], dict(strategy=r["strategy"], n=0, closed=0, Y=0, reason_only=0, N=0,
                                                  actual_only_closed=0, sim_only_closed=0, both_open=0, same_day=0))
        g["n"] += 1
        g[r["outcome"]] += 1
        if r["actual_reason"] != "open":
            g["closed"] += 1
            g["same_day"] += int(r.get("same_day_actual") == "Y")
    out: List[Dict[str, Any]] = []
    for g in groups.values():
        c = g["closed"]
        g["reason_rate"] = (g["Y"] + g["reason_only"]) / c if c else None
        g["full_rate"] = g["Y"] / c if c else None
        if c < FID_MIN_N:
            g["verdict"] = f"판정 불가(n={c}<{FID_MIN_N})"
        else:
            g["verdict"] = "ok" if g["reason_rate"] >= EXIT_REASON_MIN else "LOW"
        out.append(g)
    return out


def rates_equal(a: Optional[float], b: Optional[float]) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < 1e-9


def tp_sl_table(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """전략별 — 체결 원장 BUY 의 target_profit_rate/stop_loss_rate 와 엔진 경로 값 일치 건수."""
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        if r.get("tp_sl_match") not in ("Y", "N"):
            continue
        g = groups.setdefault(r["strategy"], dict(strategy=r["strategy"], n=0, match=0))
        g["n"] += 1
        g["match"] += int(r["tp_sl_match"] == "Y")
    return list(groups.values())


def entry_diff_stats(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """진입차% = (가상 진입가 ÷ 실제 체결가 − 1)×100 · + 면 가상이 비싸다. 전략별 + (전체)."""
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for r in rows:
        if not r.get("entry_diff_pct"):
            continue
        x = float(r["entry_diff_pct"])
        for key in (r["strategy"], "(전체)"):
            g = groups.setdefault(key, dict(strategy=key, n=0, s=0.0, a=0.0, positive=0, n_first=0, s_first=0.0))
            g["n"] += 1
            g["s"] += x
            g["a"] += abs(x)
            g["positive"] += int(x > 0)
            if r.get("first_tick") == "Y":
                g["n_first"] += 1
                g["s_first"] += x
    return [dict(strategy=g["strategy"], n=g["n"], signed_mean=g["s"] / g["n"], abs_mean=g["a"] / g["n"],
                 positive=g["positive"], n_first=g["n_first"],
                 signed_mean_first=(g["s_first"] / g["n_first"] if g["n_first"] else None))
            for g in groups.values()]
```

- [ ] **Step 5: `context8.py` 수정 — 청산 규칙·탐침 부착**

import 줄 `from . import sources8 as SRC8` 아래에 추가:
```python
from . import sellprobe8 as SP
```
`Ctx8` 필드 `snaps` 아래에 추가:
```python
    rules: Dict[str, Any] = field(default_factory=dict)     # folder → exitsim8.ExitRules
    probes: Dict[str, Any] = field(default_factory=dict)    # folder → sellprobe8.SellProbe
```
`close()` 바로 위에 메서드 추가:
```python
    def attach_exit_probes(self) -> None:
        """라이브 청산 규칙(엔진 경로 tp/sl · 전략 매도 분기 탐침). 🔴 `_check_buy` 호출 «전»에 부른다
        (envelope 인스턴스가 QuantDailyReader 를 품기 전에 사본을 뜬다)."""
        for f in R.ALL_FOLDERS:
            self.rules[f] = SP.resolve_live_tp_sl(f, self.strategies[f])
            self.probes[f] = SP.SellProbe(f, self.strategies[f], self.windows.get)
```

- [ ] **Step 6: `run.py` 수정 — 청산 충실도 단계**

import 블록에 추가(`from . import fidelity8 as F` 위아래 알파벳 순):
```python
from datetime import date, datetime, time
from . import exitsim8 as X
from . import sources8 as SRC8
```
(기존 `from datetime import date, datetime` 줄은 위 줄로 교체.)

`_print_signal_tables` 아래에 추가:
```python
# ── ③ 청산 · 익절손절 ──────────────────────────────────────────────────────
EARLY_FILL = time(9, 5, 0)     # 실제 매수 ≤ 09:05 면 진입일 고저를 쓴다(D_open 취급)
EXIT_COLS = ["buy_id", "strategy", "code", "buy_date", "buy_time", "buy_price", "entry_basis", "actual_reason",
             "actual_exit_date", "actual_ret_pct", "sim_reason", "sim_exit_date", "sim_ret_pct", "sim_hold_days",
             "sim_flags", "outcome", "same_day_actual", "tp_db", "sl_db", "tp_live", "sl_live", "tp_sl_match"]


def exit_fidelity_rows(ctx: Ctx8, since: date, until: date) -> List[Dict[str, str]]:
    """실제 매수(since~until)를 «실제 진입가·시각»으로 청산 시뮬에 통과 → 실제 청산과 사유·날짜 대조."""
    rows: List[Dict[str, str]] = []
    for folder in R.ALL_FOLDERS:
        rules, probe = ctx.rules[folder], ctx.probes[folder]
        for t in ctx.trades.get(folder, []):
            d = t.buy_ts.date()
            if not (since <= d <= until):
                continue
            extra = ctx.extras.get(t.buy_id)
            basis = X.BASIS_D_OPEN if t.buy_ts.time() <= EARLY_FILL else X.BASIS_ACTUAL
            pos = X.Pos(t.code, d, SRC8.aware(t.buy_ts), float(t.buy_price), extra.qty if extra else 1, basis)
            sim = X.simulate_lot(pos, rules, ctx.path(t.code, d), probe)
            ar = F.actual_reason(t.sell_reason) if t.sell_ts is not None else "open"
            ad = t.sell_ts.date() if t.sell_ts is not None else None
            tp_db = extra.tp_rate if extra else None
            sl_db = extra.sl_rate if extra else None
            match = (_yn(F.rates_equal(tp_db, rules.tp) and F.rates_equal(sl_db, rules.sl))
                     if tp_db is not None and sl_db is not None else "")
            rows.append(OrderedDict(
                buy_id=str(t.buy_id), strategy=folder, code=t.code, buy_date=d.isoformat(),
                buy_time=f"{t.buy_ts:%H:%M:%S}", buy_price=_fmt(t.buy_price), entry_basis=basis,
                actual_reason=ar, actual_exit_date=ad.isoformat() if ad else "",
                actual_ret_pct=_pct((t.sell_price / t.buy_price - 1) * 100) if t.sell_ts is not None else "",
                sim_reason=sim.reason, sim_exit_date=sim.exit_date.isoformat() if sim.exit_date else "",
                sim_ret_pct=_pct(sim.ret_pct), sim_hold_days=_fmt(sim.hold_days), sim_flags=" · ".join(sim.flags),
                outcome=F.exit_outcome(ar, ad, sim.reason, sim.exit_date if sim.closed else None),
                same_day_actual=_yn(ad == d) if ad else "", tp_db=_fmt(tp_db), sl_db=_fmt(sl_db),
                tp_live=_fmt(rules.tp), sl_live=_fmt(rules.sl), tp_sl_match=match))
    return rows


def _print_exit_tables(exit_rows: Sequence[Dict[str, str]]) -> None:
    print("\n== 청산 충실도 (실제 매수 → 실제 진입가로 시뮬 · 분모 = 실제 청산된 건)")
    print("strategy | n | closed | Y | reason_only | N | actual_only_closed | same_day | reason_rate | verdict")
    for g in F.exit_table(exit_rows):
        rate = "-" if g["reason_rate"] is None else f"{g['reason_rate'] * 100:.2f}%"
        print(f"{g['strategy']} | {g['n']} | {g['closed']} | {g['Y']} | {g['reason_only']} | {g['N']} | "
              f"{g['actual_only_closed']} | {g['same_day']} | {rate} | {g['verdict']}")
    print("\n== 익절·손절 비율 (엔진 경로 vs 체결 원장 BUY)")
    for g in F.tp_sl_table(exit_rows):
        print(f"{g['strategy']} | {g['match']}/{g['n']}")
```

`main()` 을 통째로 아래로 교체:
```python
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ledger8 — 8전략 세 arm 관측 원장")
    ap.add_argument("--start", default=R.LEDGER_START.isoformat())
    ap.add_argument("--end", default=R.LEDGER_END.isoformat())
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--log-dir", default=None, help="라이브 로그 폴더(읽기 전용)")
    ap.add_argument("--stage", choices=("signal", "exit"), default="exit")
    ap.add_argument("--exit-fid-since", default=R.EXIT_FID_SINCE.isoformat())
    a = ap.parse_args(argv)
    out = Path(a.out)
    log_dir = _resolve_log_dir(a.log_dir)
    ctx = Ctx8.open(log_dir)
    try:
        ctx.attach_exit_probes()          # 🔴 _check_buy 보다 먼저(envelope 사본)
        days = T.days_in_range(ctx.calendar, date.fromisoformat(a.start), date.fromisoformat(a.end))
        if not days:
            print(f"거래일 없음: {a.start} ~ {a.end}")
            return 2
        print(f"로그 {log_dir} · 창 {days[0]}~{days[-1]} ({len(days)}거래일) · DB {bootstrap.DB_NAME}")
        warnings = fill_attribution_check(ctx, days)
        cands, offlist, vintage = evaluate_candidates(ctx, days)
        sig_rows = signal_fidelity_rows(cands)
        _atomic_write_csv(out / "fidelity_signal.csv", SIG_COLS, sig_rows)
        _atomic_write_csv(out / "offlist_signals.csv", OFF_COLS, offlist)
        _print_signal_tables(sig_rows, vintage)
        if a.stage == "exit":
            exit_rows = exit_fidelity_rows(ctx, date.fromisoformat(a.exit_fid_since), days[-1])
            _atomic_write_csv(out / "fidelity_exit.csv", EXIT_COLS, exit_rows)
            _print_exit_tables(exit_rows)
        for w in warnings:
            print(f"[경고] {w}")
        meta = _meta(days, log_dir, a.stage, warnings)
        meta["vintage"] = vintage
        _atomic_write_text(out / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        ctx.close()
```

- [ ] **Step 7: 통과 확인(전체 회귀)**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests -q -p no:cacheprovider`
Expected: PASS(과제 1~6 전부).

- [ ] **Step 8: 청산 충실도 게이트 — 실데이터(DB 읽기 전용)**

Run: `$PY -m backtest.concept_axes.ledger8.run --stage exit`
Expected:
- 신호 표(과제 4 와 같은 값) 다음에 청산 표 7전략(deep_mr 은 창 안 체결 없음). 표본 규모 참고(2026-09-19 DB SELECT): 08-26~09-18 실제 매수 194건 · 청산 147건(envelope 13 · ma20 12 · ma5 48 · day 20 · elder 9 · min 4 · rs 41).
- 익절·손절 표는 전 전략 `n/n` 일치가 기대값(과제 설계 판단 4 드라이런 값). 불일치가 1건이라도 있으면 `fidelity_exit.csv` 에서 그 행의 `tp_db/sl_db` 를 보고 멈춘다(K 상향 전후 config 변경이 있었다는 뜻).
- 참고값(계획 검증 실행 · 실제 청산/Y/사유만/N/실제만 청산/사유 일치율): elder 9/7/1/1/0/88.89% · envelope 13/11/1/1/0/92.31% · day 20/15/5/0/0/100% · min 4/3/1/0/0/판정 불가 · ma20 12/11/0/0/1/91.67% · ma5 48/29/18/1/0/97.92% · rs 41/33/8/0/0/100% · 익절·손절 194/194.
- `results/fidelity_exit.csv` 생성.

- [ ] **Step 9: 게이트 판정 — 멈출지 결정**

`verdict == "LOW"` 전략이 있으면 과제 7 이후로 가지 말고 관리자에게 표 + 그 전략 `outcome ∈ {N, actual_only_closed}` 행 전부를 보고한다. 알려진 구조적 차이(스펙 3-2): 폴링이 놓친 짧은 꼬리(→ 시뮬 손절이 실제보다 많음) · 갭다운 손절 체결가(09:05) · 같은 날 청산. 관리자 결정: (a) 계속(보고서가 해당 전략에 `[청산 충실도 낮음]` 을 붙임) (b) `minute_candles` 보강(v2 · 이 계획 범위 밖). 🔒 기준값·순서 규칙을 결과에 맞춰 바꾸지 말 것.

- [ ] **Step 10: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| 3-2 매도 탐침(deepcopy · positions 주입 · now_kst D+k 09:02) | `SellProbe` · `test_probe_*` | [ ] |
| 손절·익절 비율 = 라이브가 매수 시점에 정하는 경로(engine :589-607·:655-658·:696-697) · 하드코딩 0 | `resolve_live_tp_sl` · `test_tp_sl_from_engine_path_matches_config` · Step 8 원장 대조 | [ ] |
| 보유일 계산식 두 벌 코드 그대로 | 탐침이 전략 `_check_sell` 을 그대로 호출 · `test_probe_max_hold_counts_trading_days_by_patched_clock` | [ ] |
| §4-3 실제 청산된 A 건과 사유·날짜 대조 | `exit_fidelity_rows` · `exit_table`(분모 = 실제 청산) · Step 8·9 | [ ] |
| 설계 판단 3(min_len 가드 포함) | `test_probe_respects_min_len_guard_like_live_sell_loop` | [ ] |
| 설계 판단 11(청산 충실도 창 08-26~) | `--exit-fid-since` 기본값 `R.EXIT_FID_SINCE` | [ ] |

- [ ] **Step 11: Commit**

```bash
git add backtest/concept_axes/ledger8/sellprobe8.py backtest/concept_axes/ledger8/fidelity8.py backtest/concept_axes/ledger8/context8.py backtest/concept_axes/ledger8/run.py backtest/concept_axes/ledger8/tests/test_sellprobe8.py backtest/concept_axes/ledger8/tests/test_fidelity8.py
git commit -F - <<'MSG'
feat(ledger8): 라이브 엔진 경로 익절·손절 비율과 매도 탐침 + 청산 충실도 단계

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```


---

### Task 7: stages — arm A «멈춘 단계» 분류(순수)

**Files:**
- Create: `backtest/concept_axes/ledger8/stages.py`
- Test: `backtest/concept_axes/ledger8/tests/test_stages.py`

**Interfaces:**
- Consumes: `logscan8.Fold` · 게이트 상수 `G_*`(과제 2) · 재사용 `cap_skip_ledger.classify.Trade`.
- Produces:
  - 상수 `STAGE_CANDIDATE STAGE_SIGNAL STAGE_HELD STAGE_CAP STAGE_GATE STAGE_CASH STAGE_UNEXPLAINED STAGE_FILL` · `GATE_KIND: Dict[str, str]` · `GATE_DEPTH: Tuple[str, ...]` · `FUNNEL_COLS`
  - `AFacts(d, folder, code, held_live, no_slot_live, slot_note, cap_log, buysig, gates, filled, signal_log, signal_replay, a_qty_upper=None)`
  - `AStop(stage, result, basis, detail)`
  - `deepest_gate(gates) -> Optional[str]` · `classify_a(f: AFacts) -> AStop` · `funnel_rows(f: AFacts) -> List[Dict[str, str]]`

- [ ] **Step 1: 실패하는 테스트 작성**

`backtest/concept_axes/ledger8/tests/test_stages.py`:
```python
"""stages — arm A «멈춘 단계» 분류 · 접힌 단계 행(순수)."""
from __future__ import annotations

from datetime import date, datetime

from backtest.concept_axes.ledger8 import logscan8 as L8
from backtest.concept_axes.ledger8 import stages as ST
from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade

D = date(2026, 9, 18)


def _fold(*times: str) -> L8.Fold:
    f = L8.Fold()
    for t in times:
        f.hit(t)
    return f


def _facts(**kw) -> ST.AFacts:
    base = dict(d=D, folder="daytrading_3methods_breakout", code="072990", held_live=False, no_slot_live=False,
                slot_note="K=10 09:00보유=5 빈자리=09:00:00-15:30:00", cap_log={}, buysig=None, gates={},
                filled=None, signal_log="NA", signal_replay="N", a_qty_upper=None)
    base.update(kw)
    return ST.AFacts(**base)


def test_fill_wins():
    t = Trade(buy_id=1, code="209640", buy_ts=datetime(2026, 9, 18, 9, 2, 13), buy_price=3695.0)
    a = ST.classify_a(_facts(code="209640", filled=t, buysig=_fold("09:02:13")))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_FILL, "Y", "vtr")


def test_deepest_gate_decides_cash_over_band_and_throttle():
    gates = {L8.G_THROTTLE: _fold("09:02:13"), L8.G_BAND_ABOVE: _fold("09:05:00"),
             L8.G_QTY: _fold("09:08:37", "09:30:00")}
    a = ST.classify_a(_facts(buysig=_fold("09:02:13", "09:08:37"), gates=gates, signal_log="Y"))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_CASH, L8.G_QTY, "log")
    assert "qty_short×2" in a.detail and "throttle×1" in a.detail


def test_other_holder_gate():
    a = ST.classify_a(_facts(buysig=_fold("09:09:22"), gates={L8.G_HELD_ANY: _fold("09:09:22")}, signal_log="Y"))
    assert (a.stage, a.result) == (ST.STAGE_GATE, "other_holder")


def test_signal_without_trace_is_unexplained_or_recon_cash():
    assert ST.classify_a(_facts(buysig=_fold("09:11:00"), signal_log="Y")).stage == ST.STAGE_UNEXPLAINED
    a = ST.classify_a(_facts(buysig=_fold("09:11:00"), signal_log="Y", a_qty_upper=0))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_CASH, "qty_zero_recon", "recon")


def test_held_then_cap_then_signal():
    assert ST.classify_a(_facts(held_live=True, no_slot_live=True)).stage == ST.STAGE_HELD
    a = ST.classify_a(_facts(cap_log={"max_positions": _fold("09:02:52")}, no_slot_live=True))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_CAP, "max_positions", "log")
    a = ST.classify_a(_facts(no_slot_live=True))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_CAP, "no_slot", "timeline")
    assert ST.classify_a(_facts(signal_log="N")).basis == "log"
    a = ST.classify_a(_facts(signal_log="NA", signal_replay="Y"))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_SIGNAL, "Y", "replay")


def test_funnel_rows_fold_n_first_last():
    gates = {L8.G_QTY: _fold("09:08:37", "09:30:00")}
    rows = ST.funnel_rows(_facts(buysig=_fold("09:02:13", "09:08:37", "09:30:00"), gates=gates, signal_log="Y"))
    assert [(r["stage"], r["result"]) for r in rows] == [
        (ST.STAGE_CANDIDATE, "Y"), (ST.STAGE_SIGNAL, "Y"), (ST.STAGE_CASH, L8.G_QTY)]
    sig = rows[1]
    assert (sig["n"], sig["first_ts"], sig["last_ts"], sig["basis"]) == ("3", "09:02:13", "09:30:00", "log")
    assert all(set(r) == set(ST.FUNNEL_COLS) for r in rows)
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_stages.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'stages'`.

- [ ] **Step 3: `stages.py` 작성**

```python
"""arm A 단계 분류 — 순수(DB·로그 파일 없음). (날짜, 전략, 종목)이 라이브에서 «어디서 멈췄나».

단계(스펙 「결정」 절 스키마 — 후보/신호/캡/현금/체결 + 기타 게이트):
  fill         실제 체결(virtual_trading_records BUY)
  cash         `[매수거절] 수량부족` · VTM `전략 가상 잔고 부족` — 또는 계기 줄이 없고 재구성 수량 0(recon)
  gate         매수신호 뒤 실행 경로에서 막힘 — other_holder · market_gate · daily_loss · band · throttle · other
  unexplained  매수신호는 있는데 막힌 계기 줄이 없다(DEBUG 게이트 — 25분 매수 쿨다운·종목정보 없음·VI · 로그 버퍼)
  cap          `[캡]` max_positions/daily_trades(3전략 · 09-16~) 또는 체결 원장 시간선상 빈자리 없음(앞 순위 매수로 소진 포함 · classify.classify_candidate)
  held         09:00 에 이 전략이 이미 보유(classify.classify_candidate) → generate_signal 이 매도 분기로 간다
  signal       룰 미충족(로그 N) 또는 판단 근거 없음(재현값 표기)
증거 `basis`: log(계기 줄) · timeline(체결 원장 재구성) · vtr · recon(수량 재구성) · replay(재현).
하루 동안 여러 게이트를 만나면 «라이브 실행 경로에서 가장 깊이 간 곳»을 대표로 두고 전부 `detail` 에 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade

from . import logscan8 as L8

STAGE_CANDIDATE = "candidate"
STAGE_SIGNAL = "signal"
STAGE_HELD = "held"
STAGE_CAP = "cap"
STAGE_GATE = "gate"
STAGE_CASH = "cash"
STAGE_UNEXPLAINED = "unexplained"
STAGE_FILL = "fill"

GATE_KIND: Dict[str, str] = {
    L8.G_QTY: STAGE_CASH, L8.G_BALANCE: STAGE_CASH,
    L8.G_HELD_ANY: "other_holder", L8.G_OWNED: "other_holder",
    L8.G_CRASH: "market_gate", L8.G_REGIME: "market_gate",
    L8.G_BUYSTOP: "band", L8.G_BAND_ABOVE: "band", L8.G_BAND_BELOW: "band", L8.G_LIMITUP: "band",
    L8.G_THROTTLE: "throttle",
    L8.G_DAILY_LOSS: "daily_loss",
    L8.G_REJECT_OTHER: "other", L8.G_NO_PRICE: "other", L8.G_UNFILLED: "other",
}
# 라이브 실행 경로 순서: core/trading_context.py:351(급락) · :366(국면) · :381-396(소유) · :428-436(일일손실) · :438-453(매수스톱) ·
# :466-482(상한가) · :484-515(진입억제) → bot/trading_analyzer.py:127-130(보유 중 무시 · 127 조회 · 128-130 판정) → 엔진 :356-430
# (데이터부족·현재가·밴드 하회·밴드 이탈·수량부족) → VTM 잔고(execute_virtual_buy) → 미체결
GATE_DEPTH: Tuple[str, ...] = (
    L8.G_CRASH, L8.G_REGIME, L8.G_OWNED, L8.G_DAILY_LOSS, L8.G_BUYSTOP, L8.G_LIMITUP, L8.G_THROTTLE, L8.G_HELD_ANY,
    L8.G_REJECT_OTHER, L8.G_NO_PRICE, L8.G_BAND_BELOW, L8.G_BAND_ABOVE, L8.G_QTY, L8.G_BALANCE, L8.G_UNFILLED)

FUNNEL_COLS = ["date", "strategy", "code", "stage", "result", "n", "first_ts", "last_ts", "basis"]


@dataclass
class AFacts:
    d: date
    folder: str
    code: str
    held_live: bool
    no_slot_live: bool
    slot_note: str
    cap_log: Dict[str, L8.Fold]          # StratDay.cap_blocking(code) — timeframe 제외
    buysig: Optional[L8.Fold]
    gates: Dict[str, L8.Fold]            # StratDay.gates_for(code)
    filled: Optional[Trade]
    signal_log: str                      # Y | N | NA
    signal_replay: str                   # Y | N
    a_qty_upper: Optional[int] = None    # sizing.arm_a_qty(기준가, per_stock, cap).qty — 잔고 항 제외 상한


@dataclass
class AStop:
    stage: str
    result: str
    basis: str
    detail: str


def deepest_gate(gates: Dict[str, L8.Fold]) -> Optional[str]:
    seen = [g for g in GATE_DEPTH if g in gates]
    return seen[-1] if seen else None


def _fold_txt(name: str, f: L8.Fold) -> str:
    return f"{name}×{f.n}({f.first}~{f.last})"


def classify_a(f: AFacts) -> AStop:
    if f.filled is not None:
        return AStop(STAGE_FILL, "Y", "vtr", f"{f.filled.buy_ts:%H:%M:%S} @{f.filled.buy_price:g}")
    if f.buysig is not None:
        g = deepest_gate(f.gates)
        detail = " ".join(_fold_txt(k, v) for k, v in sorted(f.gates.items()))
        if g is not None:
            kind = GATE_KIND[g]
            return AStop(STAGE_CASH, g, "log", detail) if kind == STAGE_CASH else AStop(STAGE_GATE, kind, "log", detail)
        if f.a_qty_upper == 0:
            return AStop(STAGE_CASH, "qty_zero_recon", "recon",
                         "계기 줄 없음 · 재구성 수량 0(복리 per_stock·종목당 상한 기준 — 잔고 미반영 상한)")
        return AStop(STAGE_UNEXPLAINED, "signal_Y_no_trace", "log",
                     "DEBUG 게이트(25분 매수 쿨다운·종목정보 없음·VI) 또는 로그 버퍼 — 계기 줄 없음")
    if f.held_live:
        return AStop(STAGE_HELD, "Y", "timeline", "09:00 이 전략 보유 → generate_signal 매도 분기")
    if f.cap_log:
        return AStop(STAGE_CAP, "+".join(sorted(f.cap_log)), "log",
                     " ".join(_fold_txt(k, v) for k, v in sorted(f.cap_log.items())))
    if f.no_slot_live:
        return AStop(STAGE_CAP, "no_slot", "timeline", f.slot_note)
    if f.signal_log == "N":
        return AStop(STAGE_SIGNAL, "N", "log", "on_tick 평가 · [on_tick] 매수신호 없음")
    return AStop(STAGE_SIGNAL, f.signal_replay, "replay", "라이브 평가 여부 불명 — 재현 신호")


def _row(f: AFacts, stage: str, result: str, n: str, first: str, last: str, basis: str) -> Dict[str, str]:
    return dict(date=f.d.isoformat(), strategy=f.folder, code=f.code, stage=stage, result=result,
                n=n, first_ts=first, last_ts=last, basis=basis)


def funnel_rows(f: AFacts) -> List[Dict[str, str]]:
    """(날짜, 전략, 종목, 단계, 결과) + n_evals/first_ts/last_ts 로 접힌 행(스펙 결정 절 스키마)."""
    rows = [_row(f, STAGE_CANDIDATE, "Y", "1", "", "", "e6")]
    if f.buysig is not None:
        rows.append(_row(f, STAGE_SIGNAL, "Y", str(f.buysig.n), f.buysig.first, f.buysig.last, "log"))
    elif f.signal_log == "N":
        rows.append(_row(f, STAGE_SIGNAL, "N", "", "", "", "log"))
    else:
        rows.append(_row(f, STAGE_SIGNAL, f"replay:{f.signal_replay}", "", "", "", "replay"))
    if f.held_live:
        rows.append(_row(f, STAGE_HELD, "Y", "", "", "", "timeline"))
    for r, fold in sorted(f.cap_log.items()):
        rows.append(_row(f, STAGE_CAP, r, str(fold.n), fold.first, fold.last, "log"))
    if f.no_slot_live and not f.cap_log:
        rows.append(_row(f, STAGE_CAP, "no_slot", "", "", "", "timeline"))
    for g in (x for x in GATE_DEPTH if x in f.gates):
        fold = f.gates[g]
        stage = STAGE_CASH if GATE_KIND[g] == STAGE_CASH else STAGE_GATE
        rows.append(_row(f, stage, g, str(fold.n), fold.first, fold.last, "log"))
    if f.filled is not None:
        ts = f"{f.filled.buy_ts:%H:%M:%S}"
        rows.append(_row(f, STAGE_FILL, "Y", "1", ts, ts, "vtr"))
    return rows
```

- [ ] **Step 4: 통과 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_stages.py -q -p no:cacheprovider`
Expected: PASS(6 passed).

- [ ] **Step 5: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| 기록 스키마 단계 = 후보/신호/캡/현금/체결 · (날짜,전략,종목,단계,결과)+n/first/last | `funnel_rows` · `FUNNEL_COLS` · `test_funnel_rows_fold_n_first_last` | [ ] |
| 과제 지시 «어느 단계에서 멈췄나(+ 타전략보유·급락·밴드·수량부족)» · 로그 증거 + 없으면 재구성·플래그 | `classify_a` · `basis` | [ ] |
| arm A 분류에 추가할 게이트(스펙 §1 끝: 급락 · 국면 · 쿨다운 · 상한가 · 타전략 보유 + 일일손실한도) | `GATE_KIND` · `GATE_DEPTH` | [ ] |
| #9 일일 «체결» · #3 [캡]∩E6 | `cap_log`(timeframe 제외 · 후보 행에서만) · `no_slot_live`(체결 원장 시간선 = 매수+매도 체결 수) | [ ] |

- [ ] **Step 6: Commit**

```bash
git add backtest/concept_axes/ledger8/stages.py backtest/concept_axes/ledger8/tests/test_stages.py
git commit -F - <<'MSG'
feat(ledger8): arm A 멈춘 단계 분류 — 로그 계기·체결 원장 시간선·재구성 근거 표기

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 8: arms — A_actual · A_sim · B1(로트 독립) · B2(평단 합산)

**Files:**
- Create: `backtest/concept_axes/ledger8/arms.py`
- Test: `backtest/concept_axes/ledger8/tests/test_arms.py`

**Interfaces:**
- Consumes: `exitsim8.{Pos, ExitRules, ExitOut, PathT, Probe, Bar, simulate_lot, entry_day, open_phase, after_open, mark_to_market, BASIS_D_OPEN, BASIS_LIFT, PHASE_OPEN, EXIT_OPEN, FLAG_BAR_MISSING, FLAG_NO_D_TOUCH, FLAG_TOUCH_SKIPPED_ADD, FLAG_LIFT_ADD}`(과제 5) · `registry.TIER_MAIN`(과제 1) · 재사용 `tradecal.days_in_range` · `classify.Trade`.
- Produces:
  - `Fill(folder, code, d, price, basis, qty, qty_basis, tier="main", signal_basis="", crash_blocked=False, other_holder_live="", buy_id=None, entry_time=None, touch_bar=None, lift_time="", d5="")`(frozen)
  - `Lot(lot_id, fill, exit, is_repeat_while_open=False, open_lot_seq=1, days_since_open_lot=None)` · `.notional_won` · `.pnl_won`
  - `Account(acct_id, folder, code, fills, qty, avg_price, avg_path, exit=None, flags=[], hold_clock_reset_diff="", avg_flip="")` · `.first_date` · `.n_adds` · `.notional_won` · `.pnl_won` · `.add(fill)`
  - `ActualRow(trade, folder, qty, exit_status, exit_reason, exit_date, exit_price)` · `.notional_won` · `.pnl_won` · `.ret_pct`
  - `run_lots(fills, rules, path_fn, probe_for, cal, time_fn, prefix) -> List[Lot]`
  - `run_accounts(fills, rules, path_fn, probe_for, time_fn, clock=CLOCK_FIRST) -> List[Account]`
  - `mark_clock_diff(first, reset) -> None` · `mark_avg_flip(accounts, b1_lots) -> None`
  - `a_actual(trades_by_folder, qty_of, days, last_close, reason_code) -> List[ActualRow]`
  - 상수 `CLOCK_FIRST="first" CLOCK_LAST_ADD="last_add"` · 타입 `PathFn = Callable[[str, date], PathT]` · `ProbeFor = Callable[[str], Probe]` · `TimeFn = Callable[[date], datetime]`

- [ ] **Step 1: 실패하는 테스트 작성**

`backtest/concept_axes/ledger8/tests/test_arms.py`:
```python
"""arms — B1 로트 독립 · B2 평단 합산(추가매수 · 새 계좌 · 시계 리셋 · band_touch 추가) · 원 정수 · A_actual."""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from backtest.concept_axes.ledger8 import arms as A
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import fidelity8 as F
from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

FOLDER = "book_pullback_ma20"
DAYS = [date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15),
        date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]
RULES = {FOLDER: X.ExitRules(tp=0.10, sl=0.08, max_hold_days=50)}


def _bar(i, o, h, lo, c):
    return Bar(DAYS[i], float(o), float(h), float(lo), float(c))


def _path_fn(bars):
    def fn(code, d):
        i0 = DAYS.index(d)
        return [(k, dd, bars.get(dd)) for k, dd in enumerate(DAYS[i0:])]
    return fn


def _time(d):
    return datetime.combine(d, time(9, 2))


def _no_probe(folder):
    return lambda pos, day: None


def _fill(i, price, qty=10, basis=X.BASIS_D_OPEN):
    return A.Fill(FOLDER, "000001", DAYS[i], float(price), basis, qty, "amount")


# 첫 로트(100)는 3일째 손절(100×0.92=92 ≥ 저가 89), 합산 평단 96.5 는 버틴다(96.5×0.92=88.78 < 89)
BARS = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 93, 94, 92.5, 93), DAYS[2]: _bar(2, 94, 95, 89, 90)}


def test_b1_lots_are_independent():
    first, second = A.run_lots([_fill(0, 100), _fill(1, 93)], RULES, _path_fn(BARS), _no_probe, DAYS, _time, "B1")
    assert first.exit.reason == X.EXIT_SL and first.exit.exit_date == DAYS[2]
    assert second.exit.status == "open"                                   # 93×0.92=85.56 < 89
    assert (second.is_repeat_while_open, second.open_lot_seq, second.days_since_open_lot) == (True, 2, 1)
    assert (first.is_repeat_while_open, first.open_lot_seq, first.days_since_open_lot) == (False, 1, None)
    assert first.pnl_won == -80 and first.notional_won == 1000


def test_b2_averages_and_holds_where_b1_first_lot_stopped():
    fills = [_fill(0, 100), _fill(1, 93)]
    accts = A.run_accounts(fills, RULES, _path_fn(BARS), _no_probe, _time)
    assert len(accts) == 1
    a = accts[0]
    assert a.n_adds == 1 and a.qty == 20 and a.avg_price == pytest.approx(96.5)
    assert a.avg_path == [100.0, pytest.approx(96.5)]
    assert a.exit.status == "open"
    A.mark_avg_flip(accts, A.run_lots(fills, RULES, _path_fn(BARS), _no_probe, DAYS, _time, "B1"))
    assert a.avg_flip == "reason:sl→open"


def test_b2_new_account_after_full_exit_same_day():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 111, 112, 110, 111)}
    accts = A.run_accounts([_fill(0, 100), _fill(1, 111)], RULES, _path_fn(bars), _no_probe, _time)
    assert len(accts) == 2
    assert (accts[0].exit.reason, accts[0].exit.exit_date, accts[0].n_adds) == (X.EXIT_TP, DAYS[1], 0)
    assert accts[1].first_date == DAYS[1] and accts[1].avg_price == 111.0


def test_hold_clock_reset_changes_max_hold_day():
    flat = {d: Bar(d, 100.0, 101.0, 99.0, 100.0) for d in DAYS}
    rules = {FOLDER: X.ExitRules(tp=0.10, sl=0.08, max_hold_days=2)}
    fills = [_fill(0, 100), _fill(1, 100)]
    first = A.run_accounts(fills, rules, _path_fn(flat), _no_probe, _time, A.CLOCK_FIRST)
    reset = A.run_accounts(fills, rules, _path_fn(flat), _no_probe, _time, A.CLOCK_LAST_ADD)
    assert first[0].exit.exit_date == DAYS[2] and reset[0].exit.exit_date == DAYS[3]
    A.mark_clock_diff(first, reset)
    assert first[0].hold_clock_reset_diff == f"diff:max_hold@{DAYS[3]}"


def test_band_touch_add_skips_that_day_touches():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 95, 96, 85, 90)}
    accts = A.run_accounts([_fill(0, 100), _fill(1, 96, basis=X.BASIS_BAND)], RULES, _path_fn(bars), _no_probe, _time)
    assert accts[0].exit.status == "open"
    assert any(fl.startswith(X.FLAG_TOUCH_SKIPPED_ADD) for fl in accts[0].flags)


def test_a_actual_rows():
    closed = Trade(buy_id=1, code="000001", buy_ts=datetime(2026, 9, 10, 9, 3), buy_price=100.0,
                   sell_ts=datetime(2026, 9, 11, 9, 1), sell_price=110.0, sell_reason="목표 익절 도달 (10.00% >= 10.00%)")
    held = Trade(buy_id=2, code="000002", buy_ts=datetime(2026, 9, 11, 9, 4), buy_price=50.0)
    old = Trade(buy_id=3, code="000003", buy_ts=datetime(2026, 9, 1, 9, 4), buy_price=10.0)
    rows = A.a_actual({FOLDER: [closed, held, old]}, lambda i: {1: 10, 2: 20, 3: 5}[i], DAYS,
                      lambda code: (DAYS[-1], 55.0), F.actual_reason)
    assert [r.trade.buy_id for r in rows] == [1, 2]
    assert (rows[0].exit_status, rows[0].exit_reason, rows[0].pnl_won, rows[0].notional_won) == ("closed", "tp", 100, 1000)
    assert (rows[1].exit_status, rows[1].exit_price, rows[1].pnl_won) == ("open", 55.0, 100)
    assert rows[1].ret_pct == pytest.approx(10.0)


def test_open_phase_exit_is_not_open_for_same_day_signal():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 111, 112, 110, 111)}   # 1일째 09:00 갭 익절
    fills = [_fill(0, 100), _fill(1, 111)]
    lots = A.run_lots(fills, RULES, _path_fn(bars), _no_probe, DAYS, _time, "B1")
    assert lots[0].exit.phase == X.PHASE_OPEN and lots[1].is_repeat_while_open is False
    accts = A.run_accounts(fills, RULES, _path_fn(bars), _no_probe, _time)
    assert sum(lot.is_repeat_while_open for lot in lots) == sum(a.n_adds for a in accts) == 0


def test_after_phase_exit_same_day_counts_as_open_like_b2_add():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 100, 101, 99, 100)}
    probe = lambda folder: (lambda pos, day: "trail_ma" if day == DAYS[1] else None)   # noqa: E731  1일째 09:02 데이터 청산
    fills = [_fill(0, 100), _fill(1, 100)]
    lots = A.run_lots(fills, RULES, _path_fn(bars), probe, DAYS, _time, "B1")
    accts = A.run_accounts(fills, RULES, _path_fn(bars), probe, _time)
    assert lots[1].is_repeat_while_open is True and len(accts) == 1 and accts[0].n_adds == 1


def test_lift_fill_uses_post_entry_bar_and_same_day_exit_comes_first():
    tb = Bar(DAYS[1], 100.0, 101.0, 91.0, 95.0)             # 해제 뒤 분봉만 모은 봉 — 저가 91
    lift = A.Fill(FOLDER, "000001", DAYS[1], 100.0, X.BASIS_LIFT, 10, "amount",
                  entry_time=datetime(2026, 9, 11, 9, 24), touch_bar=tb, lift_time="09:24:00")
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 100, 101, 80, 95)}
    probe = lambda folder: (lambda pos, day: "trail_ma" if (day == DAYS[1] and pos.entry_date == DAYS[0]) else None)  # noqa: E731
    fills = [_fill(0, 100), lift]
    lots = A.run_lots(fills, RULES, _path_fn(bars), probe, DAYS, _time, "B1")
    assert lots[0].exit.reason == "trail_ma" and lots[1].is_repeat_while_open is False
    assert (lots[1].exit.reason, lots[1].exit.hold_days) == (X.EXIT_SL, 0)      # 일봉 저가 80 이 아니라 진입 뒤 91
    accts = A.run_accounts(fills, RULES, _path_fn(bars), probe, _time)
    assert len(accts) == 2 and accts[1].fills[0].basis == X.BASIS_LIFT
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_arms.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'arms'`.

- [ ] **Step 3: `arms.py` 작성**

```python
"""세 arm 로트 엔진 — 순수(DB·전략 인스턴스 없음 · 청산은 주입된 탐침).

| arm | 무엇 | 로트 |
|---|---|---|
| A_actual | virtual_trading_records 실제 체결(진실값 · gross) | 실제 매수 1건 = 1 |
| A_sim | A_actual 매수를 B 와 «같은» 진입·청산 시뮬에 통과 — A vs B 비교는 시뮬 대 시뮬로만(스펙 §4-5) | 실제 매수 1건 = 1 |
| B1 | 서로 다른 계좌 — 같은 종목을 또 사면 별도 로트, 로트마다 자기 매입가로 손절·익절 | 체결 1건 = 1 |
| B2 | 한 계좌 — 또 사면 평단 합산, 합산 평단으로 손절·익절·trail · 보유기한은 첫 매수부터(D4-a) | (전략, 종목) 연속 보유 = 1 |

🔴 총자산·누적수익률·자본 대비 % 금지 — 건별 %, 원(정수), 명목 가중 수익률(Σ손익/Σ명목)만.
🔑 B2 는 B1 을 걸러서 못 만든다(평단이 바뀌면 손절·익절 시점 자체가 바뀐다) — 신호(Fill)는 공유, 시뮬은 두 벌.
🔑 같은 날 시간선은 B1·B2 가 같다 — 09:00 시가 단계(보유기간·갭 익절) 청산은 09:02 진입 «전», 데이터 청산·손절·
   터치는 «후»(B2 는 추가매수 뒤 판정 · B1 은 그 로트를 «열림»으로 센다). D3′ 해제 뒤 진입은 그날 청산을 전부 «전»으로 본다.
B2 하루 순서: 09:00 open_phase(기존 평단) → 09:02 추가매수(평단 갱신) → after_open(새 평단 · band_touch 추가면 그날 터치 생략).
            해제 뒤 추가매수(D3′)는 after_open(기존 평단) 먼저 → 살아 있으면 추가(그날 터치는 이미 봤다).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import tradecal as T
from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade

from . import exitsim8 as X
from . import registry as R

CLOCK_FIRST = "first"          # D4-a(적용) — 보유기한은 첫 매수부터
CLOCK_LAST_ADD = "last_add"    # D4-b(반대편 기록) — 추가매수마다 시계 리셋(라이브 on_order_filled 덮어쓰기와 같은 효과)

PathFn = Callable[[str, date], X.PathT]
ProbeFor = Callable[[str], X.Probe]
TimeFn = Callable[[date], datetime]


def _won(x: float) -> int:
    return int(round(x))


@dataclass(frozen=True)
class Fill:
    folder: str
    code: str
    d: date
    price: float
    basis: str                          # D_open | band_touch | after_lift
    qty: int
    qty_basis: str                      # amount | one_share | actual
    tier: str = R.TIER_MAIN
    signal_basis: str = ""
    crash_blocked: bool = False
    other_holder_live: str = ""
    buy_id: Optional[int] = None        # A_sim — 원 체결 id
    entry_time: Optional[datetime] = None
    touch_bar: Optional[X.Bar] = None   # after_lift — 진입 뒤 분봉만 모은 봉
    lift_time: str = ""                 # after_lift — 체결 분봉 시각
    d5: str = ""                        # D5 — 라이브였다면 막혔을 속도 조절 규칙(쉼표 목록)


@dataclass
class Lot:
    lot_id: str
    fill: Fill
    exit: X.ExitOut
    is_repeat_while_open: bool = False
    open_lot_seq: int = 1
    days_since_open_lot: Optional[int] = None

    @property
    def notional_won(self) -> int:
        return _won(self.fill.price * self.fill.qty)

    @property
    def pnl_won(self) -> Optional[int]:
        return None if self.exit.price is None else _won((self.exit.price - self.fill.price) * self.fill.qty)


def _pos(f: Fill, t: datetime) -> X.Pos:
    return X.Pos(f.code, f.d, t, float(f.price), int(f.qty), f.basis, touch_bar=f.touch_bar)


def _open_on(lot: Lot, d: date, after_lift: bool = False) -> bool:
    """날짜 d 의 새 진입 시각에 이 로트가 아직 열려 있었나 — B2 계좌와 같은 시간선."""
    e = lot.exit
    if not e.closed:
        return True
    if e.exit_date is None or e.exit_date < d:
        return False
    if e.exit_date > d:
        return True
    if after_lift:
        return False
    return e.phase != X.PHASE_OPEN


def run_lots(fills: Sequence[Fill], rules: Dict[str, X.ExitRules], path_fn: PathFn, probe_for: ProbeFor,
             cal: Sequence[date], time_fn: TimeFn, prefix: str) -> List[Lot]:
    """체결 1건 = 로트 1개(B1 · A_sim · 부록). 같은 (전략, 종목)에 열린 로트가 있으면 반복 플래그."""
    lots: List[Lot] = []
    by_key: Dict[Tuple[str, str], List[Lot]] = {}
    for i, f in enumerate(sorted(fills, key=lambda x: (x.d, x.folder, x.code, x.buy_id or 0))):
        ex = X.simulate_lot(_pos(f, f.entry_time or time_fn(f.d)), rules[f.folder], path_fn(f.code, f.d),
                            probe_for(f.folder))
        prev = [lot for lot in by_key.get((f.folder, f.code), []) if _open_on(lot, f.d, f.basis == X.BASIS_LIFT)]
        since = (len(T.days_in_range(cal, min(lot.fill.d for lot in prev), f.d)) - 1) if prev else None
        lot = Lot(f"{prefix}-{i:04d}", f, ex, bool(prev), len(prev) + 1, since)
        by_key.setdefault((f.folder, f.code), []).append(lot)
        lots.append(lot)
    return lots


@dataclass
class Account:
    acct_id: str
    folder: str
    code: str
    fills: List[Fill]
    qty: int
    avg_price: float
    avg_path: List[float]
    exit: Optional[X.ExitOut] = None
    flags: List[str] = field(default_factory=list)
    hold_clock_reset_diff: str = ""
    avg_flip: str = ""

    @property
    def first_date(self) -> date:
        return self.fills[0].d

    @property
    def n_adds(self) -> int:
        return len(self.fills) - 1

    @property
    def notional_won(self) -> int:
        return _won(sum(f.price * f.qty for f in self.fills))

    @property
    def pnl_won(self) -> Optional[int]:
        if self.exit is None or self.exit.price is None:
            return None
        return _won((self.exit.price - self.avg_price) * self.qty)

    def add(self, f: Fill) -> None:
        self.avg_price = (self.avg_price * self.qty + f.price * f.qty) / (self.qty + f.qty)
        self.qty += f.qty
        self.fills.append(f)
        self.avg_path.append(self.avg_price)


def _simulate_account(fl: Sequence[Fill], i: int, rules: X.ExitRules, path_fn: PathFn, probe: X.Probe,
                      time_fn: TimeFn, clock: str, acct_id: str) -> Tuple[Account, int]:
    f0 = fl[i]
    i += 1
    acct = Account(acct_id, f0.folder, f0.code, [f0], int(f0.qty), float(f0.price), [float(f0.price)])
    clock_d, clock_t, k0 = f0.d, (f0.entry_time or time_fn(f0.d)), 0

    def pos(basis: str, touch: Optional[X.Bar] = None) -> X.Pos:
        return X.Pos(f0.code, clock_d, clock_t, acct.avg_price, acct.qty, basis, touch_bar=touch)

    path = list(path_fn(f0.code, f0.d))
    if not path:
        acct.exit = X.ExitOut("open", X.EXIT_OPEN, None, None, None, None, ["no_path"])
        return acct, i
    ex = X.entry_day(pos(f0.basis, f0.touch_bar), rules, path[0][2], probe)
    if ex is not None:
        acct.exit = ex
        return acct, i
    if f0.basis != X.BASIS_D_OPEN and f0.touch_bar is None:
        acct.flags.append(X.FLAG_NO_D_TOUCH)
    last: Optional[Tuple[int, date, X.Bar]] = (0, path[0][1], path[0][2]) if path[0][2] is not None else None
    pending = False
    for k, day, bar in path[1:]:
        kk = k - k0
        if bar is None:
            acct.flags.append(f"{X.FLAG_BAR_MISSING}:{day}")
            if kk >= rules.max_hold_days:
                pending = True
            continue
        ex = X.open_phase(pos(X.BASIS_D_OPEN), rules, kk, bar, pending)
        if ex is not None:                      # 같은 날 신호는 바깥 루프에서 새 계좌가 된다
            acct.exit = ex
            return acct, i
        add = fl[i] if (i < len(fl) and fl[i].d == day) else None
        if add is not None and add.basis == X.BASIS_LIFT:
            ex = X.after_open(pos(X.BASIS_D_OPEN), rules, kk, day, bar, probe)     # 해제 전(기존 평단) 판정 먼저
            if ex is not None:
                acct.exit = ex
                return acct, i                                                   # 해제 뒤 체결은 새 계좌
            i += 1
            acct.add(add)
            acct.flags.append(f"{X.FLAG_LIFT_ADD}:{day}")
            if clock == CLOCK_LAST_ADD:
                clock_d, clock_t, k0, kk = day, (add.entry_time or time_fn(day)), k, 0
            last = (kk, day, bar)
            continue
        touches = True
        if add is not None:
            i += 1
            acct.add(add)
            if clock == CLOCK_LAST_ADD:
                clock_d, clock_t, k0, kk = day, (add.entry_time or time_fn(day)), k, 0
            if add.basis != X.BASIS_D_OPEN:
                touches = False
                acct.flags.append(f"{X.FLAG_TOUCH_SKIPPED_ADD}:{day}")
        ex = X.after_open(pos(X.BASIS_D_OPEN), rules, kk, day, bar, probe, touches=touches)
        if ex is not None:
            acct.exit = ex
            return acct, i
        last = (kk, day, bar)
    acct.exit = X.mark_to_market(pos(X.BASIS_D_OPEN), last, [])
    return acct, i


def run_accounts(fills: Sequence[Fill], rules: Dict[str, X.ExitRules], path_fn: PathFn, probe_for: ProbeFor,
                 time_fn: TimeFn, clock: str = CLOCK_FIRST) -> List[Account]:
    """(전략, 종목)별 한 계좌. 전량 청산 뒤 신호가 오면 새 계좌."""
    by_key: Dict[Tuple[str, str], List[Fill]] = {}
    for f in fills:
        by_key.setdefault((f.folder, f.code), []).append(f)
    tag = "B2r" if clock == CLOCK_LAST_ADD else "B2"
    out: List[Account] = []
    for key in sorted(by_key):
        fl = sorted(by_key[key], key=lambda x: x.d)
        i = 0
        while i < len(fl):
            acct, i = _simulate_account(fl, i, rules[key[0]], path_fn, probe_for(key[0]), time_fn, clock,
                                        f"{tag}-{len(out):04d}")
            out.append(acct)
    return out


def mark_clock_diff(first: Sequence[Account], reset: Sequence[Account]) -> None:
    """D4 반대편 기록 — 추가매수마다 시계를 리셋했으면 청산(사유·날짜)이 달라졌을 계좌."""
    by_start = {(a.folder, a.code, a.first_date): a for a in reset}
    for a in first:
        if a.n_adds == 0:
            a.hold_clock_reset_diff = "n/a(추가매수 없음)"
            continue
        b = by_start.get((a.folder, a.code, a.first_date))
        if b is None or a.exit is None or b.exit is None:
            a.hold_clock_reset_diff = "account_split_differs"
            continue
        same = (a.exit.reason, a.exit.exit_date) == (b.exit.reason, b.exit.exit_date)
        a.hold_clock_reset_diff = "same" if same else f"diff:{b.exit.reason}@{b.exit.exit_date}"


def mark_avg_flip(accounts: Sequence[Account], b1_lots: Sequence[Lot]) -> None:
    """평단 이동 효과 — 같은 첫 체결의 B1 로트와 B2 계좌의 청산 비교(same · date_only · reason:a→b)."""
    first_lot = {(lot.fill.folder, lot.fill.code, lot.fill.d): lot for lot in b1_lots}
    for a in accounts:
        if a.n_adds == 0:
            a.avg_flip = "n/a(추가매수 없음)"
            continue
        lot = first_lot.get((a.folder, a.code, a.first_date))
        if lot is None or a.exit is None:
            a.avg_flip = "no_b1_lot"
            continue
        r1, d1, r2, d2 = lot.exit.reason, lot.exit.exit_date, a.exit.reason, a.exit.exit_date
        if (r1, d1) == (r2, d2):
            a.avg_flip = "same"
        elif r1 == r2:
            a.avg_flip = "date_only"
        else:
            a.avg_flip = f"reason:{r1}→{r2}"


@dataclass
class ActualRow:
    trade: Trade
    folder: str
    qty: int
    exit_status: str                   # closed | open
    exit_reason: str                   # fidelity8.actual_reason 코드 | open
    exit_date: Optional[date]
    exit_price: Optional[float]        # 실제 매도가 | 마지막 종가(평가)

    @property
    def notional_won(self) -> int:
        return _won(self.trade.buy_price * self.qty)

    @property
    def pnl_won(self) -> Optional[int]:
        return None if self.exit_price is None else _won((self.exit_price - self.trade.buy_price) * self.qty)

    @property
    def ret_pct(self) -> Optional[float]:
        return None if self.exit_price is None else (self.exit_price / self.trade.buy_price - 1) * 100.0


def a_actual(trades_by_folder: Dict[str, Sequence[Trade]], qty_of: Callable[[int], int], days: Sequence[date],
             last_close: Callable[[str], Optional[Tuple[date, float]]],
             reason_code: Callable[[str], str]) -> List[ActualRow]:
    """창 안 실제 매수(전 전략). 미청산은 마지막 종가 평가(gross · 수수료·세금 없음)."""
    dayset = set(days)
    out: List[ActualRow] = []
    for folder in sorted(trades_by_folder):
        for t in trades_by_folder[folder]:
            if t.buy_ts.date() not in dayset:
                continue
            q = int(qty_of(t.buy_id))
            if t.sell_ts is not None:
                out.append(ActualRow(t, folder, q, "closed", reason_code(t.sell_reason), t.sell_ts.date(),
                                     float(t.sell_price)))
            else:
                lc = last_close(t.code)
                out.append(ActualRow(t, folder, q, "open", "open", lc[0] if lc else None, lc[1] if lc else None))
    return out
```

- [ ] **Step 4: 통과 확인(전체 회귀)**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests -q -p no:cacheprovider`
Expected: PASS(과제 1~8 전부).

- [ ] **Step 5: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| §0-4 B1 로트 독립(자기 매입가) · B2 평단 합산 · 신호 공유·시뮬 두 벌 | `run_lots` · `run_accounts` · `test_b1_lots_are_independent` · `test_b2_averages_*` | [ ] |
| 3-6 B1 `is_repeat_while_open · open_lot_seq · days_since_open_lot` | `Lot` · `run_lots` | [ ] |
| 3-6 B2 `n_adds · avg_price_path` · 전량 청산 뒤 새 계좌 | `Account` · `test_b2_new_account_after_full_exit_same_day` | [ ] |
| D4 적용(첫 매수부터) + `hold_clock_reset_diff` | `CLOCK_FIRST/LAST_ADD` · `mark_clock_diff` · `test_hold_clock_reset_changes_max_hold_day` | [ ] |
| 보고서 Q3 평단 이동으로 뒤집힌 건수 | `mark_avg_flip` | [ ] |
| A = A_actual + A_sim | `a_actual` · `run_lots(…, prefix="AS")`(과제 9 에서 호출) | [ ] |
| 총자산·누적수익률 금지 · 원 정수 | `notional_won`·`pnl_won`(int) · 자본 분모 없음 | [ ] |
| 3-8 `test_arms`(B1 로트 독립 · B2 n_adds · 청산 뒤 새 계좌) | 위 테스트 | [ ] |
| critic 🟡1 09:00 시가 단계 청산 로트는 «열림» 아님(B1 재신호 = B2 추가매수 시간선) | `_open_on` · `test_open_phase_exit_is_not_open_for_same_day_signal` · `test_after_phase_exit_same_day_counts_as_open_like_b2_add` | [ ] |
| D3′ 해제 뒤 진입 — 그날 청산이 먼저 · 진입일 터치는 진입 뒤 분봉만 | `_open_on(after_lift)` · `_simulate_account` · `test_lift_fill_uses_post_entry_bar_and_same_day_exit_comes_first` | [ ] |

- [ ] **Step 6: Commit**

```bash
git add backtest/concept_axes/ledger8/arms.py backtest/concept_axes/ledger8/tests/test_arms.py
git commit -F - <<'MSG'
feat(ledger8): 세 arm 로트 엔진 — A_actual·A_sim·B1 로트 독립·B2 평단 합산·시계 리셋 대조

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```


---

### Task 9: run 전체 — 원장·체결·세 arm·CSV(D3′ 해제 뒤 진입 · D5 표시) + 1일 스모크 2회

**Files:**
- Modify: `backtest/concept_axes/ledger8/sources8.py`(함수 1개 추가 — `minute_bars`)
- Modify: `backtest/concept_axes/ledger8/context8.py`(필드 1개 + 메서드 1개 — 분봉 캐시)
- Modify: `backtest/concept_axes/ledger8/run.py`(import · 원장·arm 조립 함수 · `main` 교체)
- 산출(스모크는 워크트리 밖 `D:/tmp/ledger8_smoke_0918/` · `D:/tmp/ledger8_smoke_0914/` — 커밋 안 함)

**Interfaces:**
- Consumes: 과제 1~8 전부 — `evaluate_candidates`·`exit_fidelity_rows`·`EARLY_FILL`(run) · `stages.AFacts/classify_a/funnel_rows/FUNNEL_COLS` · `arms.Fill/Lot/Account/ActualRow/run_lots/run_accounts/mark_clock_diff/mark_avg_flip/a_actual/CLOCK_*` · `exitsim8.lift_entry/LIFT_FILLED/BASIS_LIFT/Bar` · `sizing.arm_a_qty/arm_b_qty` · `livesignal8.forced_band/evaluate8` · `logscan8.G_THROTTLE/G_DAILY_LOSS/StratDay` · `Ctx8.rules/probes/path/last_close/buys_on/others_at/first_tick/log_for/bars_for/windows` · 재사용 `sim.simulate_entry/ENTRY_FILLED` · 라이브 `config.constants.PRICE_LIMIT_GUARD_RATE`(config/constants.py:219) · `core.models.TradingStock.buy_cooldown_minutes`(core/models.py:196 · 기본값 25 · core·bot·main 어디서도 덮지 않음) · `core.regime.market_classifier.resolve_regime_index(configured, stock_code, market_lookup=None, strategy_name=None, count=True)`(:157-194 — `count=False` 로 부른다) · `db.repositories.price.PriceRepository.get_minute_prices(stock_code, trade_date)`(db/repositories/price.py:188-229 · `minute_candles` · `trade_date` 키 · SELECT 만).
- Produces:
  - `sources8.minute_bars(code, d) -> List[Tuple[str, Bar]]` · `Ctx8.minutes` · `Ctx8.minute_bars(code, d)`
  - `run.per_stock_for(sd, strategy, folder, d) -> Tuple[float, str]` · `run.crash_state(ctx, folder, code, d) -> Tuple[bool, str]` · `run.d5_flags(ctx, sd, folder, code, entry_naive) -> List[str]` · 상수 `COOLDOWN_MIN · D5_THROTTLE · D5_COOLDOWN · D5_DAILY_LOSS`
  - `run.attach_rows(ctx, cands, reuse=None) -> Tuple[List[Dict[str, str]], List[Fill], List[Fill], List[Dict[str, str]]]` — (원장 행, B 체결, D3 «게이트 없었다면» 09:02 체결, 접힌 단계 행)
  - `run.a_sim_fills(ctx, days, in_list) -> Tuple[List[Fill], List[Dict[str, str]], List[str]]` — (체결, 진입 대조 행, 경고)
  - `run.lot_rows(lots, arm) · acct_rows(accts) · actual_rows(rows, in_list) · fill_rows(fills) · read_fills(path)`
  - `run.build_arms(ctx, days, cands, reuse=None) -> Dict[str, Any]` — 키 `ledger funnel fills lots accounts a_sim a_sim_entry a_actual warnings repeat_vs_adds`
  - `run.OUT_FILES` · 열 목록 `LEDGER_COLS FILL_COLS LOT_COLS ACCT_COLS ACTUAL_COLS ASIM_ENTRY_COLS`
  - CLI `--stage all`(기본) · `--reuse-fills PATH`
  - lots 의 `arm` 값: `B1`(본 · D3′ 해제 뒤 체결 포함) · `B1_nogate`(D3 반대편 — 게이트 없었다면 09:02 체결) · `B1_ext`(D1 11~20위)

- [ ] **Step 1: 분봉 읽기 — `sources8.py` · `context8.py`**

`sources8.py` 의 `class WindowCache:` 바로 위에 추가:
```python
_MINUTE_REPO = None


def minute_bars(code: str, d: date) -> List[Tuple[str, Bar]]:
    """D3′ 용 하루 분봉 — 라이브 `PriceRepository.get_minute_prices`(db/repositories/price.py:188-229 · `minute_candles`
    · 키 `trade_date` · SELECT 만)를 그대로 부른다 → [(분봉 시작 HH:MM:SS, Bar)]. 그날이 아닌 행(팬텀 세션)은 버린다.
    ⚠️ `minute_candles` 는 그날 선정 종목 위주로 ~300종목/일만 있다 — 없으면 [] (D3′ 상태 `no_minute_data`)."""
    global _MINUTE_REPO
    if _MINUTE_REPO is None:
        _MINUTE_REPO = _S._price_mod.PriceRepository()
    df = _MINUTE_REPO.get_minute_prices(code, d.strftime("%Y%m%d"))
    if df is None or df.empty:
        return []
    out: List[Tuple[str, Bar]] = []
    for ts, o, h, lo, c in zip(pd.to_datetime(df["datetime"]), df["open"], df["high"], df["low"], df["close"]):
        if ts.date() != d or any(pd.isna(x) for x in (o, h, lo, c)):
            continue
        out.append((ts.strftime("%H:%M:%S"), Bar(d, float(o), float(h), float(lo), float(c))))
    return out
```
`context8.py` 의 `probes` 필드 아래에 추가:
```python
    minutes: Dict[Tuple[str, date], List[Tuple[str, Bar]]] = field(default_factory=dict)
```
`attach_exit_probes` 위에 메서드 추가:
```python
    def minute_bars(self, code: str, d: date) -> List[Tuple[str, Bar]]:
        key = (code, d)
        if key not in self.minutes:
            self.minutes[key] = SRC8.minute_bars(code, d)
        return self.minutes[key]
```

- [ ] **Step 2: import 추가(`run.py`)**

`from datetime import date, datetime, time` 줄을 `from datetime import date, datetime, time, timedelta` 로 바꾸고, 맨 위 `import csv` 앞에 `import dataclasses` 를 넣는다. `from backtest.concept_axes.minervini.cap_skip_ledger import tradecal as T` 아래에:
```python
from backtest.concept_axes.minervini.cap_skip_ledger import sim as S
from config.constants import PRICE_LIMIT_GUARD_RATE                  # noqa: E402  (bootstrap 뒤)
from core.models import TradingStock                                 # noqa: E402
from core.regime.market_classifier import resolve_regime_index       # noqa: E402
```
`from . import exitsim8 as X` 위에 `from . import arms as A` 를, `from . import livesignal8 as LS8` 아래에 `from . import logscan8 as L8` 를, `from . import registry as R` 아래에 `from . import sizing as Z` 를(과제 6 의 `from . import sources8 as SRC8` 는 그대로), `from . import sizing as Z` 아래에 `from . import stages as ST` 를 넣는다.

- [ ] **Step 3: 원장·arm 조립 함수 추가(`_print_exit_tables` 아래)**

```python
# ── ④⑤ 원장 · 세 arm ─────────────────────────────────────────────────────
LEDGER_COLS = [
    "date", "strategy", "code", "tier", "list_pos", "snap_rank", "list_src", "scan_date", "sector_mode",
    "K", "held_live", "no_slot_live", "slot_state", "slot_state_v2", "eval_v1", "slot_note", "other_holder_live",
    "signal_replay", "replay_reason", "n_bars", "last_bar", "signal_log", "n_evals", "first_ts", "last_ts",
    "reasons_equal", "signal_used", "signal_basis", "vol_ratio", "vol_threshold", "rule_margin_pct",
    "vintage_fragile", "ref", "band_min", "band_max", "band_basis",
    "a_stop_stage", "a_stop_result", "a_stop_basis", "a_stop_detail", "a_per_stock", "a_per_stock_src",
    "a_qty_upper", "a_buy_time", "a_buy_price",
    "b_entry_status", "b_entry_basis", "b_entry_price", "b_entry_vs_ref_pct", "b_entry_note",
    "b_qty", "b_qty_basis", "b_notional_won", "crash_blocked", "crash_lifted_at", "lift_status", "lift_time",
    "lift_price", "limitup_possible", "d5_flags", "b1_lot_id", "b2_acct_id", "caveats",
]
FILL_COLS = ["date", "strategy", "code", "tier", "price", "basis", "qty", "qty_basis", "signal_basis",
             "crash_blocked", "other_holder_live", "entry_time", "lift_time", "touch_open", "touch_high", "touch_low",
             "touch_close", "d5"]
LOT_COLS = ["arm", "lot_id", "tier", "strategy", "code", "entry_date", "entry_basis", "entry_price", "qty",
            "qty_basis", "notional_won", "signal_basis", "crash_blocked", "lift_time", "d5_flags", "other_holder_live",
            "buy_id", "is_repeat_while_open", "open_lot_seq", "days_since_open_lot", "exit_status", "exit_reason",
            "exit_phase", "exit_date", "exit_price", "ret_pct", "hold_days", "pnl_won", "flags"]
ACCT_COLS = ["acct_id", "strategy", "code", "first_date", "n_fills", "n_adds", "fill_dates", "avg_price_path",
             "final_avg_price", "qty", "notional_won", "exit_status", "exit_reason", "exit_date", "exit_price",
             "ret_pct", "hold_days", "pnl_won", "hold_clock_reset_diff", "avg_flip", "flags"]
ACTUAL_COLS = ["buy_id", "strategy", "code", "buy_date", "buy_time", "buy_price", "qty", "notional_won", "in_list",
               "exit_status", "exit_reason", "exit_date", "exit_price", "ret_pct", "pnl_won"]
ASIM_ENTRY_COLS = ["buy_id", "strategy", "code", "date", "in_list", "band_basis", "sim_entry_status",
                   "sim_entry_basis", "sim_entry_price", "actual_buy_time", "actual_buy_price", "entry_diff_pct",
                   "first_tick"]
OUT_FILES = (("ledger8.csv", "ledger", LEDGER_COLS), ("funnel.csv", "funnel", ST.FUNNEL_COLS),
             ("fills_b.csv", "fills", FILL_COLS), ("lots_b1.csv", "lots", LOT_COLS),
             ("accounts_b2.csv", "accounts", ACCT_COLS), ("a_sim.csv", "a_sim", LOT_COLS),
             ("a_sim_entry.csv", "a_sim_entry", ASIM_ENTRY_COLS), ("a_actual.csv", "a_actual", ACTUAL_COLS))

FillKey = Tuple[date, str, str, str]      # (날짜, 전략, 종목, tier)

# D5 — 속도 조절 규칙은 B 에 적용하지 않는다(사장님 규칙 «후보 통과 종목은 전부 산다»). 라이브였다면 막혔을 건만 표시.
COOLDOWN_MIN = next(f.default for f in dataclasses.fields(TradingStock) if f.name == "buy_cooldown_minutes")
D5_THROTTLE = "throttle"          # [진입억제] 60초 쿨다운·사이클 3건(로그 · core/trading_context.py:484-515)
D5_COOLDOWN = "buy_cooldown"      # 25분 매수 쿨다운(체결 원장 재구성 · bot/trading_analyzer.py:132-136 · DEBUG 라 로그 없음)
D5_DAILY_LOSS = "daily_loss"      # 일일손실한도(로그 · core/trading_context.py:428-436)
# VI 매수 보류(trading_context.py:424-426)는 DEBUG 로그라 관측 불가 — 표시하지 않고 한계로 적는다.


def per_stock_for(sd: L8.StratDay, strategy, folder: str, d: date) -> Tuple[float, str]:
    """arm A 종목당 금액 — 로그 복리 재산정(검증표 #12) → config paper_investment_per_stock(#13) → 자본/K."""
    if sd.per_stock:
        return float(sd.per_stock["new"]), "log(종목당 투자금액 재산정)"
    rm = (getattr(strategy, "config", None) or {}).get("risk_management", {})
    if rm.get("paper_investment_per_stock"):
        return float(rm["paper_investment_per_stock"]), "config(paper_investment_per_stock · 복리 미반영)"
    k, _ = R.k_for(folder, d)
    return R.VIRTUAL_CAPITAL_PER_STRATEGY / k, "fallback(자본/K · 복리 미반영)"


def crash_state(ctx: Ctx8, folder: str, code: str, d: date) -> Tuple[bool, str]:
    """D3 — 급락게이트 «유지». B 진입 시각(09:02) 그 지수의 로그 판정이 `차단` 이면 막힘 + 풀린 첫 시각(D3′ 에 쓴다)."""
    cfg, _ = R.regime_index_for(folder, d)
    idx = resolve_regime_index(cfg, code, strategy_name=None, count=False)
    if idx == "none":
        return False, ""
    names = ("KOSPI", "KOSDAQ") if idx == "both" else (idx,)
    dl = ctx.log_for(d)
    t = SRC8.FIRST_TICK.strftime("%H:%M:%S")
    blocked = [n for n in names if dl.index_state(n, t) == "차단"]
    if not blocked:
        return False, ""
    lifts = [dl.first_verdict_after(n, t, "허용") for n in blocked]
    return True, (max(lifts) if all(lifts) else "")


def d5_flags(ctx: Ctx8, sd: L8.StratDay, folder: str, code: str, entry_naive: datetime) -> List[str]:
    """D5 — 라이브였다면 이 B 진입을 막았을 속도 조절 규칙. 관측 가능한 것만(로그 줄 · 체결 원장)."""
    g = sd.gates_for(code)
    out: List[str] = []
    if L8.G_THROTTLE in g:
        out.append(D5_THROTTLE)
    if L8.G_DAILY_LOSS in g:
        out.append(D5_DAILY_LOSS)
    if any(t.code == code and timedelta(0) <= entry_naive - t.buy_ts < timedelta(minutes=COOLDOWN_MIN)
           for t in ctx.buys_on(folder, entry_naive.date())):
        out.append(D5_COOLDOWN)
    return out


def attach_rows(ctx: Ctx8, cands: Sequence[Dict[str, Any]], reuse: Optional[Dict[FillKey, A.Fill]] = None
                ) -> Tuple[List[Dict[str, str]], List[A.Fill], List[A.Fill], List[Dict[str, str]]]:
    """후보 행 → (원장 행, B 체결, D3 «게이트 없었다면» 09:02 체결(민감도), 접힌 단계 행). A 단계는 main 만.

    B 진입 = D 09:02 한 번(설계 판단 7). 그 시각 급락 게이트가 막고 있으면 D3′ — 게이트가 풀린 뒤 첫 밴드 안 분봉
    가격(`exitsim8.lift_entry`)에 산다. 속도 조절 규칙(D5)은 적용하지 않고 라이브였다면 막혔을 규칙만 `d5` 에 적는다.
    """
    ledger: List[Dict[str, str]] = []
    fills: List[A.Fill] = []
    nogate: List[A.Fill] = []
    funnel: List[Dict[str, str]] = []
    for c in cands:
        d, folder, code, tier, ev = c["d"], c["folder"], c["code"], c["tier"], c["ev"]
        strat = ctx.strategies[folder]
        sd = ctx.log_for(d).get(folder)
        others = ctx.others_at(folder, code, ctx.first_tick(d))
        bs = c["buysig"]
        caveats: List[str] = []
        margin = ((c["vol_ratio"] / c["vol_threshold"] - 1) * 100
                  if c["vol_ratio"] is not None and c["vol_threshold"] else None)
        row: Dict[str, str] = OrderedDict((k, "") for k in LEDGER_COLS)
        row.update(date=d.isoformat(), strategy=folder, code=code, tier=tier, list_pos=str(c["list_pos"]),
                   snap_rank=_fmt(c["snap_rank"]), list_src=c["list_src"], scan_date=_fmt(c["scan_date"]),
                   sector_mode=c["sector_mode"], K=str(R.k_for(folder, d)[0]), held_live=_fmt(c["held"]),
                   no_slot_live=_fmt(c["no_slot"]), slot_state=c["slot_state"], slot_state_v2=c["slot_state_v2"],
                   eval_v1=_fmt(c["eval_v1"]), slot_note=c["slot_note"], other_holder_live=",".join(others),
                   signal_replay=ev.signal, replay_reason=ev.reason[:80], n_bars=str(ev.n_bars),
                   last_bar=ev.last_bar, signal_log=c["signal_log"], reasons_equal=c["reasons_equal"],
                   signal_used=c["signal_used"], signal_basis=c["signal_basis"], vol_ratio=_fmt(c["vol_ratio"]),
                   vol_threshold=_fmt(c["vol_threshold"]), rule_margin_pct=_pct(margin),
                   vintage_fragile=c["vintage_fragile"])
        if bs is not None:
            row.update(n_evals=str(bs.n), first_ts=bs.first, last_ts=bs.last)
        band: Optional[Tuple[Optional[float], Optional[float], Optional[float]]] = None
        if c["signal_used"] == "Y":
            if ev.signal == "Y":
                band, row["band_basis"] = (ev.ref, ev.band_min, ev.band_max), "replay"
            else:
                data, _ = ctx.windows.get(code, d)
                band, row["band_basis"] = LS8.forced_band(strat, folder, code, d, data), "forced(로그 Y·재현 N)"
                if band is None:
                    caveats.append("밴드 산출 불가 — 강제 _check_buy 도 None(rs_leader live 배제·데이터 없음)")
        if band is not None:
            row.update(ref=_fmt(band[0]), band_min=_fmt(band[1], 2), band_max=_fmt(band[2], 2))
        if tier == R.TIER_MAIN:
            buys = [t for t in ctx.buys_on(folder, d) if t.code == code]
            per_stock, ps_src = per_stock_for(sd, strat, folder, d)
            ref_px = band[0] if band is not None else ev.ref
            qa = Z.arm_a_qty(ref_px, per_stock, getattr(strat, "_max_per_stock_amount", None), ps_src)
            facts = ST.AFacts(d, folder, code, c["held"], c["no_slot"], c["slot_note"], sd.cap_blocking(code), bs,
                              sd.gates_for(code), buys[0] if buys else None, c["signal_log"], ev.signal,
                              qa.qty if ref_px else None)
            stop = ST.classify_a(facts)
            funnel.extend(ST.funnel_rows(facts))
            row.update(a_stop_stage=stop.stage, a_stop_result=stop.result, a_stop_basis=stop.basis,
                       a_stop_detail=stop.detail[:200], a_per_stock=_won_str(per_stock), a_per_stock_src=ps_src,
                       a_qty_upper=str(qa.qty) if ref_px else "")
            if buys:
                row.update(a_buy_time=f"{buys[0].buy_ts:%H:%M:%S}", a_buy_price=_fmt(buys[0].buy_price))
        fill: Optional[A.Fill] = None
        if reuse is not None:
            fill = reuse.get((d, folder, code, tier))
            if fill is not None:
                row.update(b_entry_status=S.ENTRY_FILLED, b_entry_note="reuse-fills")
        elif band is not None:
            ent = S.simulate_entry(ctx.bars_for(code).get(d), band[1], band[2])
            row.update(b_entry_status=ent.status, b_entry_basis=ent.basis, b_entry_note=ent.note)
            if ent.price is not None and band[0]:
                row["b_entry_vs_ref_pct"] = _pct((ent.price / band[0] - 1) * 100)
            common = dict(tier=tier, signal_basis=c["signal_basis"], other_holder_live=",".join(others))
            crash, lifted = crash_state(ctx, folder, code, d)
            if not crash:
                if ent.status == S.ENTRY_FILLED:
                    q = Z.arm_b_qty(ent.price)
                    fill = A.Fill(folder, code, d, float(ent.price), ent.basis, q.qty, q.basis, **common)
            else:
                row.update(crash_blocked="Y", crash_lifted_at=lifted)
                if ent.status == S.ENTRY_FILLED:           # D3 반대편 — 게이트가 없었다면 09:02 에 샀다(민감도)
                    q0 = Z.arm_b_qty(ent.price)
                    nogate.append(A.Fill(folder, code, d, float(ent.price), ent.basis, q0.qty, q0.basis,
                                         crash_blocked=True, **common))
                le = X.lift_entry(d, ctx.minute_bars(code, d), lifted, band[1], band[2])
                row.update(lift_status=le.status, lift_time=le.time, lift_price=_fmt(le.price),
                           b_entry_status=f"crash→{le.status}")
                if le.status == X.LIFT_FILLED:
                    q = Z.arm_b_qty(le.price)
                    fill = A.Fill(folder, code, d, float(le.price), X.BASIS_LIFT, q.qty, q.basis, crash_blocked=True,
                                  entry_time=SRC8.aware(datetime.combine(d, time.fromisoformat(le.time))),
                                  touch_bar=le.touch_bar, lift_time=le.time, **common)
        if fill is not None:
            if reuse is None:
                t_naive = (datetime.combine(d, time.fromisoformat(fill.lift_time)) if fill.lift_time
                           else ctx.first_tick(d))
                fill = dataclasses.replace(fill, d5=",".join(d5_flags(ctx, sd, folder, code, t_naive)))
            fills.append(fill)
            row.update(b_entry_basis=fill.basis, b_entry_price=_fmt(fill.price), b_qty=str(fill.qty),
                       b_qty_basis=fill.qty_basis, b_notional_won=_won_str(fill.price * fill.qty),
                       crash_blocked=_fmt(fill.crash_blocked), d5_flags=fill.d5)
            if band is not None and band[0] and fill.price >= band[0] * (1 + PRICE_LIMIT_GUARD_RATE):
                row["limitup_possible"] = "Y"          # 상한가 +25% 게이트(trading_context.py:466-482) — 플래그만
        row["caveats"] = " | ".join(caveats)
        ledger.append(row)
    return ledger, fills, nogate, funnel


def a_sim_fills(ctx: Ctx8, days: Sequence[date], in_list: Dict[Tuple[date, str], List[str]]
                ) -> Tuple[List[A.Fill], List[Dict[str, str]], List[str]]:
    """실제 매수 → B 와 같은 진입 시뮬(D 시가 · 밴드 복귀). 밴드 = 재현 Y 면 그 밴드, 아니면 강제 밴드. 수량 = 실제.
    체결 원장에 수량이 없으면 수량 0 으로 두되 «경고»로 남긴다(조용히 넣지 않는다)."""
    fills: List[A.Fill] = []
    rows: List[Dict[str, str]] = []
    warns: List[str] = []
    dayset = set(days)
    for folder in R.ALL_FOLDERS:
        strat = ctx.strategies[folder]
        for t in ctx.trades.get(folder, []):
            d = t.buy_ts.date()
            if d not in dayset:
                continue
            data, _ = ctx.windows.get(t.code, d)
            ev = LS8.evaluate8(strat, folder, t.code, d, data)
            if ev.signal == "Y":
                band, basis = (ev.ref, ev.band_min, ev.band_max), "replay"
            else:
                band, basis = LS8.forced_band(strat, folder, t.code, d, data), "forced"
            if band is None:
                band, basis = (None, None, None), "none(밴드 없음 → D 시가)"
            ent = S.simulate_entry(ctx.bars_for(t.code).get(d), band[1], band[2])
            listed = t.code in in_list.get((d, folder), [])
            extra = ctx.extras.get(t.buy_id)
            if extra is None:
                warns.append(f"A_sim {folder} {t.code} {d} buy_id={t.buy_id}: 체결 원장 수량 없음 → 수량 0(손익 0)")
            rows.append(OrderedDict(
                buy_id=str(t.buy_id), strategy=folder, code=t.code, date=d.isoformat(), in_list=_yn(listed),
                band_basis=basis, sim_entry_status=ent.status, sim_entry_basis=ent.basis,
                sim_entry_price=_fmt(ent.price), actual_buy_time=f"{t.buy_ts:%H:%M:%S}",
                actual_buy_price=_fmt(t.buy_price),
                entry_diff_pct=_pct((ent.price / t.buy_price - 1) * 100) if ent.price else "",
                first_tick=_yn(t.buy_ts.time() <= EARLY_FILL)))
            if ent.status == S.ENTRY_FILLED:
                fills.append(A.Fill(folder, t.code, d, float(ent.price), ent.basis, extra.qty if extra else 0,
                                    "actual", tier=R.TIER_MAIN if listed else R.TIER_OFFLIST, signal_basis=basis,
                                    buy_id=t.buy_id))
    return fills, rows, warns


def lot_rows(lots: Sequence[A.Lot], arm: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for lot in lots:
        f, e = lot.fill, lot.exit
        out.append(OrderedDict(
            arm=arm, lot_id=lot.lot_id, tier=f.tier, strategy=f.folder, code=f.code, entry_date=f.d.isoformat(),
            entry_basis=f.basis, entry_price=_fmt(f.price), qty=str(f.qty), qty_basis=f.qty_basis,
            notional_won=str(lot.notional_won), signal_basis=f.signal_basis, crash_blocked=_fmt(f.crash_blocked),
            lift_time=f.lift_time, d5_flags=f.d5, other_holder_live=f.other_holder_live, buy_id=_fmt(f.buy_id),
            is_repeat_while_open=_fmt(lot.is_repeat_while_open), open_lot_seq=str(lot.open_lot_seq),
            days_since_open_lot=_fmt(lot.days_since_open_lot), exit_status=e.status, exit_reason=e.reason,
            exit_phase=e.phase, exit_date=e.exit_date.isoformat() if e.exit_date else "",
            exit_price=_fmt(e.price, 2), ret_pct=_pct(e.ret_pct), hold_days=_fmt(e.hold_days),
            pnl_won=_fmt(lot.pnl_won), flags=" · ".join(e.flags)))
    return out


def acct_rows(accts: Sequence[A.Account]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for a in accts:
        e = a.exit
        out.append(OrderedDict(
            acct_id=a.acct_id, strategy=a.folder, code=a.code, first_date=a.first_date.isoformat(),
            n_fills=str(len(a.fills)), n_adds=str(a.n_adds), fill_dates=",".join(f.d.isoformat() for f in a.fills),
            avg_price_path="→".join(_fmt(p, 2) for p in a.avg_path), final_avg_price=_fmt(a.avg_price, 2),
            qty=str(a.qty), notional_won=str(a.notional_won), exit_status=e.status, exit_reason=e.reason,
            exit_date=e.exit_date.isoformat() if e.exit_date else "", exit_price=_fmt(e.price, 2),
            ret_pct=_pct(e.ret_pct), hold_days=_fmt(e.hold_days), pnl_won=_fmt(a.pnl_won),
            hold_clock_reset_diff=a.hold_clock_reset_diff, avg_flip=a.avg_flip, flags=" · ".join(a.flags + e.flags)))
    return out


def actual_rows(rows: Sequence[A.ActualRow], in_list: Dict[Tuple[date, str], List[str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for r in rows:
        t, d = r.trade, r.trade.buy_ts.date()
        out.append(OrderedDict(
            buy_id=str(t.buy_id), strategy=r.folder, code=t.code, buy_date=d.isoformat(),
            buy_time=f"{t.buy_ts:%H:%M:%S}", buy_price=_fmt(t.buy_price), qty=str(r.qty),
            notional_won=str(r.notional_won), in_list=_yn(t.code in in_list.get((d, r.folder), [])),
            exit_status=r.exit_status, exit_reason=r.exit_reason,
            exit_date=r.exit_date.isoformat() if r.exit_date else "", exit_price=_fmt(r.exit_price, 2),
            ret_pct=_pct(r.ret_pct), pnl_won=_fmt(r.pnl_won)))
    return out


def fill_rows(fills: Sequence[A.Fill]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for f in fills:
        tb = f.touch_bar
        out.append(OrderedDict(
            date=f.d.isoformat(), strategy=f.folder, code=f.code, tier=f.tier, price=repr(f.price), basis=f.basis,
            qty=str(f.qty), qty_basis=f.qty_basis, signal_basis=f.signal_basis, crash_blocked=_fmt(f.crash_blocked),
            other_holder_live=f.other_holder_live, entry_time=f.entry_time.isoformat() if f.entry_time else "",
            lift_time=f.lift_time, touch_open=repr(tb.open) if tb else "", touch_high=repr(tb.high) if tb else "",
            touch_low=repr(tb.low) if tb else "", touch_close=repr(tb.close) if tb else "", d5=f.d5))
    return out


def read_fills(path: Path) -> Dict[FillKey, A.Fill]:
    """`fills_b.csv`(진입 집합 동결본) → 키별 Fill. 스펙 §4 「진입 집합 동결 후 청산만 재추적」."""
    out: Dict[FillKey, A.Fill] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            d = date.fromisoformat(r["date"])
            tb = (X.Bar(d, float(r["touch_open"]), float(r["touch_high"]), float(r["touch_low"]),
                        float(r["touch_close"])) if r["touch_open"] else None)
            out[(d, r["strategy"], r["code"], r["tier"])] = A.Fill(
                r["strategy"], r["code"], d, float(r["price"]), r["basis"], int(r["qty"]), r["qty_basis"],
                tier=r["tier"], signal_basis=r["signal_basis"], crash_blocked=(r["crash_blocked"] == "Y"),
                other_holder_live=r["other_holder_live"],
                entry_time=datetime.fromisoformat(r["entry_time"]) if r["entry_time"] else None,
                touch_bar=tb, lift_time=r["lift_time"], d5=r["d5"])
    return out


def build_arms(ctx: Ctx8, days: Sequence[date], cands: Sequence[Dict[str, Any]],
               reuse: Optional[Dict[FillKey, A.Fill]] = None) -> Dict[str, Any]:
    ledger, fills, nogate, funnel = attach_rows(ctx, cands, reuse)
    in_list: Dict[Tuple[date, str], List[str]] = {}
    for c in cands:
        if c["tier"] == R.TIER_MAIN:
            in_list.setdefault((c["d"], c["folder"]), []).append(c["code"])
    probe_for = ctx.probes.__getitem__
    main_f = [f for f in fills if f.tier == R.TIER_MAIN]               # D3′: 해제 뒤 체결 포함
    b1 = A.run_lots(main_f, ctx.rules, ctx.path, probe_for, ctx.calendar, SRC8.as_of, "B1")
    b1g = A.run_lots([f for f in nogate if f.tier == R.TIER_MAIN],        # D3 반대편 — 게이트 없었다면(09:02)
                     ctx.rules, ctx.path, probe_for, ctx.calendar, SRC8.as_of, "B1G")
    b1x = A.run_lots([f for f in fills if f.tier == R.TIER_EXT],           # D1: 11~20위 별도 칸
                     ctx.rules, ctx.path, probe_for, ctx.calendar, SRC8.as_of, "B1X")
    b2 = A.run_accounts(main_f, ctx.rules, ctx.path, probe_for, SRC8.as_of, A.CLOCK_FIRST)
    b2r = A.run_accounts(main_f, ctx.rules, ctx.path, probe_for, SRC8.as_of, A.CLOCK_LAST_ADD)
    A.mark_clock_diff(b2, b2r)
    A.mark_avg_flip(b2, b1)
    af, asim_entry, warns = a_sim_fills(ctx, days, in_list)
    asim = A.run_lots(af, ctx.rules, ctx.path, probe_for, ctx.calendar, SRC8.as_of, "AS")
    aact = A.a_actual(ctx.trades, lambda i: ctx.extras[i].qty if i in ctx.extras else 0, days, ctx.last_close,
                      F.actual_reason)
    lot_id = {(lot.fill.d, lot.fill.folder, lot.fill.code, lot.fill.tier): lot.lot_id for lot in b1 + b1x}
    acct_id = {(f.d, f.folder, f.code): a.acct_id for a in b2 for f in a.fills}
    for r in ledger:
        d = date.fromisoformat(r["date"])
        r["b1_lot_id"] = lot_id.get((d, r["strategy"], r["code"], r["tier"]), "")
        if r["tier"] == R.TIER_MAIN:
            r["b2_acct_id"] = acct_id.get((d, r["strategy"], r["code"]), "")
    # B1 «열린 로트 위 재신호» 와 B2 «추가매수» 는 같은 시간선이라 대부분 같다. 남는 차이는 로트별 청산 vs 평단 청산이
    # 갈린 경우뿐이다(결함 아님) — 전략별로 적어 둔다.
    repeat_vs_adds = {f: dict(b1_repeat=sum(1 for x in b1 if x.fill.folder == f and x.is_repeat_while_open),
                              b2_adds=sum(a.n_adds for a in b2 if a.folder == f)) for f in R.ALL_FOLDERS}
    return dict(ledger=ledger, funnel=funnel, fills=fill_rows(fills),
                lots=lot_rows(b1, "B1") + lot_rows(b1g, "B1_nogate") + lot_rows(b1x, "B1_ext"),
                accounts=acct_rows(b2), a_sim=lot_rows(asim, "A_sim"), a_sim_entry=asim_entry,
                a_actual=actual_rows(aact, in_list), warnings=warns, repeat_vs_adds=repeat_vs_adds)


def _print_counts(res: Dict[str, Any]) -> None:
    print("\n== 규모 (전략별)")
    print("strategy | 후보(main) | 사용신호Y | B체결(main) | 그중 해제 뒤 | B1로트 | B2계좌 | B1 재신호/B2 추가 | A실제매수")
    for f in R.ALL_FOLDERS:
        led = [r for r in res["ledger"] if r["strategy"] == f and r["tier"] == R.TIER_MAIN]
        ra = res["repeat_vs_adds"][f]
        print(f"{f} | {len(led)} | {sum(1 for r in led if r['signal_used'] == 'Y')} | "
              f"{sum(1 for r in led if r['b_entry_price'])} | "
              f"{sum(1 for r in led if r['b_entry_basis'] == X.BASIS_LIFT)} | "
              f"{sum(1 for r in res['lots'] if r['strategy'] == f and r['arm'] == 'B1')} | "
              f"{sum(1 for r in res['accounts'] if r['strategy'] == f)} | {ra['b1_repeat']}/{ra['b2_adds']} | "
              f"{sum(1 for r in res['a_actual'] if r['strategy'] == f)}")
    crash = [r for r in res["ledger"] if r["crash_blocked"] == "Y" and r["tier"] == R.TIER_MAIN]
    st: Dict[str, int] = {}
    for r in crash:
        st[r["lift_status"] or "(밴드 없음)"] = st.get(r["lift_status"] or "(밴드 없음)", 0) + 1
    print(f"D3′ 급락 차단 main 행 {len(crash)} → " + " · ".join(f"{k} {v}" for k, v in sorted(st.items())))
```

- [ ] **Step 4: `main()` 을 통째로 교체**

```python
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ledger8 — 8전략 세 arm 관측 원장")
    ap.add_argument("--start", default=R.LEDGER_START.isoformat())
    ap.add_argument("--end", default=R.LEDGER_END.isoformat())
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--log-dir", default=None, help="라이브 로그 폴더(읽기 전용)")
    ap.add_argument("--stage", choices=("signal", "exit", "all"), default="all")
    ap.add_argument("--exit-fid-since", default=R.EXIT_FID_SINCE.isoformat())
    ap.add_argument("--reuse-fills", default=None, help="진입 집합 동결 파일(fills_b.csv) — 청산만 재추적")
    a = ap.parse_args(argv)
    out = Path(a.out)
    log_dir = _resolve_log_dir(a.log_dir)
    reuse = read_fills(Path(a.reuse_fills)) if a.reuse_fills else None
    ctx = Ctx8.open(log_dir)
    try:
        ctx.attach_exit_probes()          # 🔴 _check_buy 보다 먼저(envelope 사본)
        days = T.days_in_range(ctx.calendar, date.fromisoformat(a.start), date.fromisoformat(a.end))
        if not days:
            print(f"거래일 없음: {a.start} ~ {a.end}")
            return 2
        print(f"로그 {log_dir} · 창 {days[0]}~{days[-1]} ({len(days)}거래일) · DB {bootstrap.DB_NAME}")
        warnings = fill_attribution_check(ctx, days)
        cands, offlist, vintage = evaluate_candidates(ctx, days)
        sig_rows = signal_fidelity_rows(cands)
        _atomic_write_csv(out / "fidelity_signal.csv", SIG_COLS, sig_rows)
        _atomic_write_csv(out / "offlist_signals.csv", OFF_COLS, offlist)
        _print_signal_tables(sig_rows, vintage)
        exit_rows: List[Dict[str, str]] = []
        if a.stage in ("exit", "all"):
            exit_rows = exit_fidelity_rows(ctx, date.fromisoformat(a.exit_fid_since), days[-1])
            _atomic_write_csv(out / "fidelity_exit.csv", EXIT_COLS, exit_rows)
            _print_exit_tables(exit_rows)
        res: Dict[str, Any] = {}
        if a.stage == "all":
            res = build_arms(ctx, days, cands, reuse)
            for name, key, cols in OUT_FILES:
                _atomic_write_csv(out / name, cols, res[key])
            _print_counts(res)
            warnings.extend(res["warnings"])
        for w in warnings:
            print(f"[경고] {w}")
        meta = _meta(days, log_dir, a.stage, warnings)
        meta["vintage"] = vintage
        meta["last_bar"] = ctx.calendar[-1].isoformat() if ctx.calendar else ""
        meta["reuse_fills"] = a.reuse_fills or ""
        meta["repeat_vs_adds"] = res.get("repeat_vs_adds", {})
        _atomic_write_text(out / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        ctx.close()
```

- [ ] **Step 5: 회귀 테스트**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests -q -p no:cacheprovider`
Expected: PASS(과제 1~8 전부 — run.py·sources8·context8 변경은 DB 경계라 Step 7~8 실행으로 검증).

- [ ] **Step 6: 전제 재확인 — `auto` 지수 해석 · 분봉 경로**

Run:
```bash
$PY - <<'PY'
import backtest.concept_axes.minervini.cap_skip_ledger.bootstrap  # noqa: F401
from datetime import date
from core.regime.market_classifier import resolve_regime_index
from backtest.concept_axes.ledger8 import sources8 as SRC8
print(resolve_regime_index("auto", "005930", strategy_name=None, count=False),
      resolve_regime_index("auto", "209640", strategy_name=None, count=False),
      resolve_regime_index("KOSPI", "209640", strategy_name=None, count=False))
m = SRC8.minute_bars("005930", date(2026, 9, 11))
print(len(m), m[0][0], m[-1][0])
PY
```
Expected: `KOSPI KOSDAQ KOSPI`(계획 검증 실행에서 확인) · 분봉 약 380개 · 첫 `09:00:00`. `auto` 가 `both both KOSPI` 면 `stock_market` 매핑을 못 읽은 것(core/regime/market_classifier.py:99-119) — 멈추고 보고. 매핑은 «지금» 값이라 PIT 가 아니다(README 한계).

- [ ] **Step 7: 1일 스모크 2회(09-18 평일 · 09-14 급락일 · 워크트리 밖 출력)**

Run:
```bash
$PY -m backtest.concept_axes.ledger8.run --start 2026-09-18 --end 2026-09-18 --out D:/tmp/ledger8_smoke_0918
$PY -m backtest.concept_axes.ledger8.run --start 2026-09-14 --end 2026-09-14 --out D:/tmp/ledger8_smoke_0914
```
Expected: 둘 다 종료코드 0 · `Traceback` 없음 · `[경고]` 0줄 · 각 폴더에 CSV 11개 + `run_meta.json`(과제 10 전엔 `summary.md` 없음). 09-14 는 `D3′ 급락 차단 main 행 … → filled · no_minute_data · unfillable` 줄이 나온다(09-18 은 0). 실행 시간 기록. 참고값(계획 검증 실행 2차): 각 3초 · 09-14 `D3′ 급락 차단 main 행 44 → filled 12 · no_minute_data 22 · unfillable 10` · 09-18 `… 0`.

- [ ] **Step 8: 스모크 산출물 정합 검사**

Run:
```bash
$PY - <<'PY'
import csv
from pathlib import Path
for O in (Path("D:/tmp/ledger8_smoke_0918"), Path("D:/tmp/ledger8_smoke_0914")):
    rd = lambda n: list(csv.DictReader((O / n).open(encoding="utf-8")))
    led, lots, accts, act, fills = rd("ledger8.csv"), rd("lots_b1.csv"), rd("accounts_b2.csv"), rd("a_actual.csv"), rd("fills_b.csv")
    main = [r for r in led if r["tier"] == "main"]
    b1 = [r for r in lots if r["arm"] == "B1"]
    print(O.name, "후보 main", len(main), "ext", len(led) - len(main))
    print("  B1 로트", len(b1), "= main 체결", sum(1 for r in main if r["b_entry_price"]),
          "· 그중 해제 뒤", sum(1 for r in b1 if r["entry_basis"] == "after_lift"))
    print("  B2 계좌", len(accts), "≤ B1", len(accts) <= len(b1), "· B1_nogate", sum(1 for r in lots if r["arm"] == "B1_nogate"))
    print("  A 실제 매수", len(act), "· fill 단계", sum(1 for r in main if r["a_stop_stage"] == "fill"))
    print("  D5", {k: sum(1 for r in b1 if k in r["d5_flags"].split(",")) for k in ("throttle", "buy_cooldown", "daily_loss")})
    print("  qty_basis", {b: sum(1 for r in fills if r["qty_basis"] == b) for b in sorted({r["qty_basis"] for r in fills})})
    assert all("." not in r["pnl_won"] for r in b1 if r["pnl_won"])
    assert all(r["lift_time"] for r in b1 if r["entry_basis"] == "after_lift")
PY
```
Expected: 「B1 로트 = main 체결」 두 수가 같다 · `B2 계좌 ≤ B1 True` · 09-18 `A 실제 매수` = 체결 원장 BUY 11건 · `fill 단계` ≤ A 실제 매수(차이 = E6 목록 밖 매수) · 09-14 `해제 뒤` ≥ 1 · 09-18 `해제 뒤` = 0 · `pnl_won` 에 소수점 없음. 하나라도 어긋나면 멈추고 해당 행을 보고. 참고값(계획 검증 실행 2차): 09-18 — main 60 · ext 52 · B1 52 = 52 · 해제 뒤 0 · B2 52 · B1_nogate 0 · A 11 · fill 11 · D5 throttle 37 · qty_basis amount 91 · one_share 1 / 09-14 — main 56 · ext 48 · B1 21 = 21 · 해제 뒤 12 · B2 21 · B1_nogate 35 · A 6 · fill 6 · D5 throttle 1 · buy_cooldown 1.

- [ ] **Step 9: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| §4-4 arms — A_actual·A_sim·B1·B2 · D1~D4 플래그 전부 | `build_arms` · `attach_rows`(`tier` · `other_holder_live` · `crash_blocked`·`crash_lifted_at`) · `mark_clock_diff` | [ ] |
| §4-5 run CLI + 결과 파일 | `main` · `OUT_FILES` · Step 7 | [ ] |
| D1 본 = E6 상위 10 · 11~20위 `tier=ext` 별도 | `evaluate_candidates` · `B1_ext` | [ ] |
| D2 전략 간 차단 해제 + `other_holder_live` | `attach_rows`(B 는 보유 무시) | [ ] |
| **D3′ 풀린 뒤 산다**(분봉 · 해제 시각 · 진입일 규칙 일관) · 하루 종일 막힘 민감도 · 게이트 없음 민감도 | `crash_state` → `lift_entry` · `Fill.touch_bar` · `B1_nogate` · 보고서 §6(과제 10) | [ ] |
| **D5 빼되 표시**(진입억제·25분 쿨다운·일일손실 — VI 는 관측 불가) | `d5_flags` · `Fill.d5` · `lots_b1.csv d5_flags` | [ ] |
| critic 🟡4 A_sim 수량 없음 → 경고 | `a_sim_fills` warns → `[경고]` · `run_meta.warnings` | [ ] |
| critic 🟡1 B1 재신호 vs B2 추가매수 대조 | `repeat_vs_adds` · `_print_counts` | [ ] |
| 3-3 진입 = `sim.simulate_entry` 세 밴드 유형 · 상한가 +25% 플래그 | `attach_rows` · `limitup_possible` | [ ] |
| 3-4 소유자 미지정 SELECTED 는 B 에서 제외 · A 에는 `offlist` | `TIER_OFFLIST`(A_sim) · B 는 E6 main/ext 만 | [ ] |
| #12 per_stock 로그 · #13 deep_mr · #14 종목당 상한 | `per_stock_for` · `arm_a_qty(..., _max_per_stock_amount)` | [ ] |
| 스펙 위험 「1주 분기 실질 0건일 수 있음」 확인 | Step 8 `qty_basis` 분포 | [ ] |
| 진입 집합 동결 · 청산만 재추적(해제 뒤 체결 포함) | `fills_b.csv`(entry_time · touch_* 칸) · `--reuse-fills` | [ ] |

- [ ] **Step 10: Commit**

```bash
git add backtest/concept_axes/ledger8/sources8.py backtest/concept_axes/ledger8/context8.py backtest/concept_axes/ledger8/run.py
git commit -F - <<'MSG'
feat(ledger8): 원장·세 arm 조립 — D3′ 해제 뒤 진입(분봉)·D5 속도 조절 표시·D1~D4 플래그·진입 집합 동결

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```


---

### Task 10: report — summary.md(5개 질문 · 충실도 · 부록) + 7일 전체 실행

**Files:**
- Create: `backtest/concept_axes/ledger8/report.py`
- Modify: `backtest/concept_axes/ledger8/run.py`(import 1줄 · `main` 교체)
- Test: `backtest/concept_axes/ledger8/tests/test_report.py`
- 산출(커밋): `backtest/concept_axes/ledger8/results/` 13개 파일

**Interfaces:**
- Consumes: `fidelity8.signal_table(rows, outcome_key) · exit_table · tp_sl_table · entry_diff_stats · FID_MIN_N`(과제 3·6) · `run` 의 `SIG_COLS` 행 · `EXIT_COLS` 행 · `build_arms` 산출 dict 행(과제 9 열 이름 그대로) · `run_meta.vintage` · `registry.ALL_FOLDERS · TIER_MAIN`.
- Produces:
  - `report.BANNER · A_GROUPS · RESOURCE_GROUPS · PERF_HDR · D5_LABELS · RULES · LIMITS`
  - `report.won(x) -> str` · `pct(x) -> str` · `ratio(x) -> str` · `md_table(header, rows) -> str` · `perf(rows) -> Dict` · `perf_cells(p) -> List[str]` · `replay_share(rows) -> str` · `a_group(ledger_row) -> str`
  - `report.render(meta, sig_rows, exit_rows, entry_rows, ledger, lots, accounts, a_sim, a_actual, offlist) -> str` — 표는 안에서 `fidelity8` 로 만든다(문장도 표에서 생성)

- [ ] **Step 1: 실패하는 테스트 작성**

`backtest/concept_axes/ledger8/tests/test_report.py`:
```python
"""report — 실현/평가 분리 성과 · 원 정수 · 방향별 신호 표 · 표에서 만든 문장 · 절 구성 · 결정적 출력(DB 없음)."""
from __future__ import annotations

import pytest

from backtest.concept_axes.ledger8 import report as RP


def _lot(strategy, lot_id, status, ret, pnl, notional, arm="B1", code="000001", seq="1", repeat="N", other="",
         basis="replay", entry_basis="D_open", d5=""):
    return dict(arm=arm, lot_id=lot_id, tier="main", strategy=strategy, code=code, exit_status=status, ret_pct=ret,
                pnl_won=pnl, notional_won=notional, open_lot_seq=seq, is_repeat_while_open=repeat,
                other_holder_live=other, qty_basis="amount", crash_blocked="N", signal_basis=basis,
                entry_basis=entry_basis, d5_flags=d5)


def _sig(strategy, outcome, slot_state="slot_available", mode="", ov1=None, ov2=None, contra="N", contra_v2="N"):
    return dict(strategy=strategy, mode=mode, outcome=outcome, outcome_v1=ov1 or outcome, outcome_v2=ov2 or outcome,
                slot_state=slot_state, reasons_equal="Y", ref_equal="Y", no_slot_but_log_y=contra,
                no_slot_but_log_y_v2=contra_v2, signal_basis="log", vintage_fragile="", rule_margin_pct="")


def test_perf_splits_realized_and_open():
    p = RP.perf([_lot("rs_leader", "B1-0000", "closed", "+10.00", "100000", "1000000"),
                 _lot("rs_leader", "B1-0001", "open", "-5.00", "-50000", "1000000")])
    assert (p["n"], p["n_closed"], p["n_open"], p["win"]) == (2, 1, 1, 1)
    assert (p["pnl_closed"], p["pnl_open"]) == (100000, -50000)
    assert p["nw"] == pytest.approx(2.5)
    assert RP.won(1234567) == "1,234,567" and RP.pct(2.5) == "+2.50%" and RP.ratio(0.9) == "90.00%"
    assert RP.replay_share([_lot("a", "x", "open", "", "", "1"), _lot("a", "y", "open", "", "", "1", basis="log")]) == "1/2 (50%)"


def test_render_sections_flags_generated_sentences_and_determinism():
    meta = dict(db="kis_template", window="2026-09-10~2026-09-18", n_days=7, last_bar="2026-09-18",
                log_dir="L", warnings=[], vintage=dict(n=3, vmin=0.004, vmax=0.243))
    sig = ([_sig("book_envelope_200d", "agree_Y", slot_state="bought")] * 6
           + [_sig("daytrading_3methods_breakout", "agree_N")] * 5
           + [_sig("daytrading_3methods_breakout", "replay_only", ov2="na", contra_v2="Y")] * 3)
    ledger = [dict(strategy="daytrading_3methods_breakout", tier="main", signal_used="Y", a_stop_stage="cash",
                   a_stop_result="qty_short", b1_lot_id="B1-0000", crash_blocked="N", lift_status="")]
    lots = [_lot("daytrading_3methods_breakout", "B1-0000", "closed", "+10.00", "100000", "1000000", d5="throttle")]
    accts = [dict(strategy="daytrading_3methods_breakout", exit_status="closed", ret_pct="+10.00", pnl_won="100000",
                  notional_won="1000000", n_adds="0", avg_flip="n/a(추가매수 없음)",
                  hold_clock_reset_diff="n/a(추가매수 없음)")]
    md = RP.render(meta, sig, [], [], ledger, lots, accts, [], [], [])
    assert "판정 근거로 쓰지 말 것" in md
    assert "daytrading_3methods_breakout [신호 충실도 낮음]" in md                 # N 방향 5/8 < 90%
    assert "`book_envelope_200d` 판정 가능 6행이 전부 실제 체결(bought)" in md      # 표에서 만든 문장
    assert "v2 3건" in md and "v3 0건" in md                                       # 재구성 모순 v2 → v3
    for h in ("## 0.", "## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 8."):
        assert h in md
    assert "자본 대비" not in md and "100,000" in md and "D5 라이브였다면 진입억제" in md
    assert md == RP.render(meta, sig, [], [], ledger, lots, accts, [], [], [])   # 실행 시각 없음 → 멱등
```

- [ ] **Step 2: 실패 확인**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests/test_report.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'report'`.

- [ ] **Step 3: `report.py` 작성**

```python
"""summary.md — 사람용 요약(순수 · CSV 모양 dict 행만 받는다 · DB 없음).

답할 것(스펙 「결정」 절):
  ① A vs B1 — 자원 제약(캡·현금)이 잘라낸 표본 규모 + 그 종목 성과(시뮬 대 시뮬: A_sim vs B1 · A_actual 병기)
  ② B1 vs B2 — 합산 여부만으로 결과 차이 ⇒ 차이 큰 전략 = 중복 처리를 따로 정할 전략
  ③ 평단 이동으로 손절/익절이 뒤집힌 건수(+ D4 반대편: 보유기한 시계 리셋)
  ④ 전략별 중복 신호 통계(rs_leader 로트 분포)
  ⑤ 충실도(신호 Y·N 방향 · 규칙 민감도 · 재현 비중·빈티지 · 청산 · 진입가 · 익절손절) — envelope·rs_leader 필수
🔴 총자산·누적수익률·자본 분모 % 를 쓰지 않는다 · 금액 = 원 단위 정수 · % = 소수 2자리 · 실현/평가 분리.
🔑 실행 시각·git SHA 는 넣지 않는다(run_meta.json) — 같은 입력이면 같은 바이트. 문장은 표에서 만든다(고정 문구 금지).
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from . import fidelity8 as F
from . import registry as R

BANNER = ("> **관측 원장이다 — 판정 근거로 쓰지 말 것.** 일봉 근사 · gross(수수료·세금 없음) · "
          "B 는 자본 분모가 없는 세계라 합계는 «원»과 «명목 가중 %»(Σ손익÷Σ명목)로만 적는다.")
A_GROUPS = (("fill", "A 체결"), ("held", "A 이미 보유"), ("cap", "A 캡(K·일일 체결)"),
            ("cash", "A 현금(수량부족·잔고)"), ("gate:other_holder", "A 타전략 보유"),
            ("gate:market_gate", "A 시장급락"), ("gate:daily_loss", "A 일일손실한도"),
            ("gate:band", "A 밴드·매수스톱"), ("gate:throttle", "A 진입억제"), ("gate:other", "A 기타 게이트"),
            ("unexplained", "A 계기 없음"), ("signal", "A 신호 없음·불명"))
RESOURCE_GROUPS = ("cap", "cash")
PERF_HDR = ["건수", "청산/보유", "청산 승", "청산 평균%", "실현 손익(원)", "평가 손익(원)", "명목가중%"]
D5_LABELS = (("throttle", "진입억제(60초·사이클 3건) — 로그"), ("buy_cooldown", "25분 매수 쿨다운 — 체결 원장 재구성"),
             ("daily_loss", "일일손실한도 — 로그"))
LS8_DAY = "daytrading_3methods_breakout"   # livesignal8.DAY 와 같은 값 — report 는 라이브 모듈을 import 하지 않는다
LS8_MIN = "minervini_volume_dryup"         # livesignal8.MIN
RULES = (("outcome_v1", "v1 09:02 한 시점"), ("outcome_v2", "v2 classify_candidate"),
         ("outcome", "v3 v2+빈자리 구간 on_tick(채택)"))
LIMITS = [
    "B 진입 = D 09:02 한 번(D 시가 · 시가가 밴드 밖이고 장중 복귀면 경계값 · 장중 내내 밖이면 불가). 라이브는 첫 틱 이후 "
    "실시간가다. 사장님 규칙 «후보 통과 종목은 전부 산다»에 따라 진입억제(60초·사이클 3건)·25분 매수 쿨다운·VI·"
    "일일손실한도는 B 에 적용하지 않고, 라이브였다면 막혔을 건만 §6 D5 표로 따로 센다(VI 는 DEBUG 로그라 관측 불가).",
    "D3′ 급락 게이트 = «풀린 뒤 산다»: 09:02 에 막혀 있으면 로그 `[시장방향성필터]` 시간선의 해제 시각 뒤 첫 밴드 안 분봉 "
    "가격(`minute_candles`)에 산다. 분봉이 없는 종목(`no_minute_data`)은 본 집계에서 «안 산 것»으로 남고 §6 에 건수를 적는다. "
    "daytrading `auto`(09-14~)의 종목 시장은 «지금» stock_market 매핑(PIT 아님).",
    "청산 = 일봉 근사: 보유기간·갭 익절·데이터 청산은 시가, 갭 손절은 시가(라이브는 09:05 이후 가격 — "
    "sl_gap_open 플래그), 장중 고저 동시 터치는 손절 우선. 폴링이 놓친 짧은 꼬리 때문에 시뮬 손절이 실제보다 많을 수 있다.",
    "신호 = 라이브 로그 우선(그 시점 DB) · 로그로 판정 못 하는 행(보유·캡)은 재현(지금 DB). 재현 행은 D-1 거래량이 라이브 "
    "스캔 뒤 재기록된 빈티지를 탄다 — 재기록은 09-14 거래시간 연장 «전»에도 있었고(예 09-10 115440 +0.4% · 09-11 006880 "
    "+0.5%) 연장 뒤 폭이 커졌다(최대 +24.3% · 051160 09-18). 거래량 룰 전략(day·min)의 재현 행은 룰 여유와 «빈티지 취약» "
    "표시를 §1-3 에 싣는다(보정은 하지 않는다).",
    "«평가 가능»(로그로 N 을 말할 수 있다) 규칙은 v1→v2→v3 로 바뀌었다(계획서 「계획 검증 실행」). 세 규칙의 결과를 §1-2 에 모두 싣는다.",
    "envelope 자체 프레임(QuantDailyReader 230봉)은 «지금 DB» 라 빈티지 위험. 창 안 스냅샷은 09-09~09-15 스캔 1~2행 뒤 0행.",
    "rs_leader corp_action 모드는 날짜별(09-17~ live). 09-10 은 가드 코드 자체가 없었다(9811d42 · 09-10 23:49 머지) — shadow 와 동치.",
    "arm A 는 라이브 자금 게이트 시간선(잔고·복리·쿨다운)을 재현하지 않는다. 멈춘 단계는 로그 계기 줄 → 체결 원장 시간선 → "
    "재구성(a_qty_upper = 잔고 미반영 상한) 순으로 분류하고 근거를 a_stop_basis 에 적었다.",
    "관측 기간이 짧다(마지막 봉 = 머리말 last_bar) — 대부분 로트가 미청산(평가)이다. 진입 집합은 fills_b.csv 로 동결해 두고 "
    "`--reuse-fills` 로 청산만 재추적할 것.",
    "gross — 수수료·세금 없음. 라이브 실현손익 보고 기준(net · fund_manager)과 다르다.",
    "생존편향·adj_factor 계열 결함(병합·감자 미조정·정지 패딩)은 그대로다.",
]


def _i(s: Optional[str]) -> int:
    return int(s) if s not in (None, "") else 0


def _f(s: Optional[str]) -> Optional[float]:
    return float(s) if s not in (None, "") else None


def won(x: int) -> str:
    return f"{int(x):,d}"


def pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:+.2f}%"


def ratio(x: Optional[float]) -> str:
    return "-" if x is None else f"{x * 100:.2f}%"


def md_table(header: Sequence[Any], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(str(h) for h in header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |")
    return "\n".join(out)


def perf(rows: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    closed = [r for r in rows if r["exit_status"] == "closed"]
    rets = [x for x in (_f(r["ret_pct"]) for r in closed) if x is not None]
    notional = sum(_i(r["notional_won"]) for r in rows)
    pnl_c = sum(_i(r["pnl_won"]) for r in closed)
    pnl_o = sum(_i(r["pnl_won"]) for r in rows if r["exit_status"] != "closed")
    return dict(n=len(rows), n_closed=len(closed), n_open=len(rows) - len(closed), win=sum(1 for x in rets if x > 0),
                mean_closed=(sum(rets) / len(rets) if rets else None), pnl_closed=pnl_c, pnl_open=pnl_o,
                nw=((pnl_c + pnl_o) / notional * 100.0 if notional else None))


def perf_cells(p: Dict[str, Any]) -> List[str]:
    return [str(p["n"]), f"{p['n_closed']}/{p['n_open']}", f"{p['win']}/{p['n_closed']}", pct(p["mean_closed"]),
            won(p["pnl_closed"]), won(p["pnl_open"]), pct(p["nw"])]


def replay_share(rows: Sequence[Dict[str, str]]) -> str:
    n = len(rows)
    k = sum(1 for r in rows if r.get("signal_basis") == "replay")
    return f"{k}/{n} ({k / n * 100:.0f}%)" if n else "-"


def a_group(row: Dict[str, str]) -> str:
    st = row.get("a_stop_stage", "")
    return f"gate:{row.get('a_stop_result', '')}" if st == "gate" else st


def _low_flags(sig_table: Sequence[Dict[str, Any]], exit_table: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    low: Dict[str, str] = {}
    for g in sig_table:
        if g["verdict"] == "LOW":
            key = str(g["group"]).split("[")[0]
            if "[신호 충실도 낮음]" not in low.get(key, ""):
                low[key] = low.get(key, "") + "[신호 충실도 낮음]"
    for g in exit_table:
        if g["verdict"] == "LOW":
            low[g["strategy"]] = low.get(g["strategy"], "") + "[청산 충실도 낮음]"
    return low


def render(meta: Dict[str, Any], sig_rows: Sequence[Dict[str, str]], exit_rows: Sequence[Dict[str, str]],
           entry_rows: Sequence[Dict[str, str]], ledger: Sequence[Dict[str, str]], lots: Sequence[Dict[str, str]],
           accounts: Sequence[Dict[str, str]], a_sim: Sequence[Dict[str, str]], a_actual: Sequence[Dict[str, str]],
           offlist: Sequence[Dict[str, str]]) -> str:
    sig_table = F.signal_table(sig_rows)
    exit_table = F.exit_table(exit_rows)
    low = _low_flags(sig_table, exit_table)

    def name(f: str) -> str:
        return f"{f} {low[f]}" if f in low else f

    b1 = [r for r in lots if r["arm"] == "B1"]
    grp = {r["b1_lot_id"]: a_group(r) for r in ledger if r.get("b1_lot_id")}
    L: List[str] = ["# ledger8 — 8전략 세 arm 관측 원장 요약", "", BANNER,
                    f"> 창 {meta['window']}({meta['n_days']}거래일) · 청산 추적 = DB 최신 봉 {meta.get('last_bar', '')} · "
                    f"DB {meta['db']} · 로그 {meta['log_dir']} · 실행 시각·git SHA 는 run_meta.json", ""]

    L += ["## 0. 원장 신뢰도", ""]
    L.append(f"- 충실도 LOW: {', '.join(f'{k} {v}' for k, v in low.items()) or '없음'} — "
             "LOW 전략의 수치는 그 표기와 함께만 인용할 것(기준값은 결과를 보고 바꾸지 않았다).")
    for g in sig_table:
        if g["evaluable"] and g["bought"] == g["evaluable"]:
            L.append(f"- `{g['group']}` 판정 가능 {g['evaluable']}행이 전부 실제 체결(bought)이다 — 자명한 Y/Y 라 "
                     "신호 재현력의 증거로는 약하다.")
    thin_n = [g["group"] for g in sig_table if g["n_n"] < F.FID_MIN_N]
    if thin_n:
        L.append(f"- N 방향(라이브 N 인데 재현 Y 오류율) 표본 부족 {len(thin_n)}그룹: {', '.join(thin_n)} — "
                 "이 그룹의 재현 신호는 Y 쪽 오류를 잴 수 없다(§1-3 재현 비중과 함께 읽을 것).")
    for w in meta.get("warnings", []):
        L.append(f"- [경고] {w}")
    L.append("")

    L += ["## 1. 충실도 (⑤)", "", "### 1-1. 신호 — 채택 규칙 v3 · 방향별(Y = 로그 Y 중 재현 Y · N = 로그 N 중 재현 N)", ""]
    L.append(md_table(["전략[모드]", "행", "판정가능", "Y 방향 일치", "N 방향 일치", "그중 bought", "이유 문자열 일치",
                       "기준가 일치", "판정", "비고"],
                      [[g["group"], g["n"], g["evaluable"], f"{g['agree_Y']}/{g['y_n']} {ratio(g['y_rate'])}",
                        f"{g['agree_N']}/{g['n_n']} {ratio(g['n_rate'])}", g["bought"],
                        f"{g['reasons_eq']}/{g['agree_Y']}", f"{g['ref_eq']}/{g['agree_Y']}", g["verdict"],
                        g["verdict_note"] or "-"] for g in sig_table]))
    L += ["", "### 1-2. «평가 가능» 규칙 민감도 · 재구성 모순", ""]
    tabs = {k: {g["group"]: g for g in F.signal_table(sig_rows, outcome_key=k)} for k, _ in RULES}
    rows_ = []
    for g in sig_table:
        cells = []
        for k, _ in RULES:
            x = tabs[k].get(g["group"])
            cells.append("-" if x is None else f"{x['evaluable']}행 · Y {ratio(x['y_rate'])} · N {ratio(x['n_rate'])} · "
                                                f"{x['verdict']}")
        rows_.append([g["group"]] + cells)
    L.append(md_table(["전략[모드]"] + [lbl for _, lbl in RULES], rows_))
    cv2 = Counter(r["strategy"] for r in sig_rows if r.get("no_slot_but_log_y_v2") == "Y")
    cv3 = Counter(r["strategy"] for r in sig_rows if r.get("no_slot_but_log_y") == "Y")
    L += ["", "- 재구성 모순 = 체결 원장 시간선은 no_slot 인데 라이브 로그엔 `[on_tick] 매수신호` 가 있다(재구성 규칙의 충실도): "
          f"v2 {sum(cv2.values())}건({' · '.join(f'{k} {v}' for k, v in sorted(cv2.items())) or '-'}) → "
          f"v3 {sum(cv3.values())}건({' · '.join(f'{k} {v}' for k, v in sorted(cv3.items())) or '-'}).", ""]
    L += ["### 1-3. 재현 신호 비중 · 거래량 룰 빈티지", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        sr = [r for r in sig_rows if r["strategy"] == f]
        mine = [r for r in b1 if r["strategy"] == f]
        if not sr and not mine:
            continue
        used_y = [r for r in ledger if r["strategy"] == f and r["tier"] == R.TIER_MAIN and r.get("signal_used") == "Y"]
        frag = sum(1 for r in sr if r.get("vintage_fragile") == "Y")
        withm = sum(1 for r in sr if r.get("signal_basis") == "replay" and r.get("rule_margin_pct"))
        rows_.append([name(f), len(sr), replay_share(used_y), replay_share(mine),
                      f"{withm}/{frag}" if f in (LS8_DAY, LS8_MIN) else "-"])
    L.append(md_table(["전략", "main 후보 행", "사용 신호 Y 중 재현", "B1 로트 중 재현", "재현 행 룰 여유 계산/빈티지 취약"],
                      rows_))
    v = meta.get("vintage") or {}
    L += ["", f"- 관측 빈티지(daytrading D-1 거래량 · 라이브 사유 vs 재현 사유 {v.get('n', 0)}쌍): "
          f"{ratio(v.get('vmin'))} ~ {ratio(v.get('vmax'))}. 재기록은 거래량을 «늘린다» ⇒ daytrading(비율 ≥ 문턱이 Y) 재현은 "
          "Y 쪽으로, minervini(비율 ≤ 문턱이 Y) 재현은 N 쪽으로 기운다. «빈티지 취약» = 관측 최대 폭 안에서 뒤집힐 수 있는 재현 행.",
          ""]
    L += ["### 1-4. 청산 — 실제 매수를 실제 진입가로 시뮬 (분모 = 실제 청산된 건)", ""]
    L.append(md_table(["전략", "실제 매수", "실제 청산", "사유·날짜 일치", "사유만", "불일치", "실제만 청산", "당일 청산",
                       "사유 일치율", "판정"],
                      [[g["strategy"], g["n"], g["closed"], g["Y"], g["reason_only"], g["N"], g["actual_only_closed"],
                        g["same_day"], ratio(g["reason_rate"]), g["verdict"]] for g in exit_table]) if exit_table else "(없음)")
    tpsl = F.tp_sl_table(exit_rows)
    L += ["", "### 1-5. 익절·손절 비율 — 엔진 경로 vs 체결 원장 BUY", ""]
    L.append(md_table(["전략", "일치/건수"], [[g["strategy"], f"{g['match']}/{g['n']}"] for g in tpsl]) if tpsl else "(없음)")
    es = F.entry_diff_stats(entry_rows)
    L += ["", "### 1-6. 진입가 — (A_sim 진입가 ÷ 실제 체결가 − 1)×100 · + 면 시뮬이 비싸다", ""]
    L.append(md_table(["전략", "건수", "부호 포함 평균", "|차| 평균", "양수", "첫 틱(≤09:05) 건수", "첫 틱 부호 평균"],
                      [[g["strategy"], g["n"], pct(g["signed_mean"]), pct(g["abs_mean"]).replace("+", ""),
                        f"{g['positive']}/{g['n']}", g["n_first"], pct(g["signed_mean_first"])] for g in es])
             if es else "(없음)")
    off = Counter()
    for r in offlist:
        off[r["strategy"]] += _i(r["n_offlist"])
    L += ["", "- E6 목록 밖 `[on_tick] 매수신호`(소유자 미지정 SELECTED — B 에서 제외, 스펙 3-4): "
          + (" · ".join(f"{k} {v}" for k, v in sorted(off.items())) or "없음"), ""]

    L += ["## 2. A vs B1 — 자원 제약이 잘라낸 표본과 그 성과 (①)", ""]
    size_rows, perf_rows = [], []
    for f in R.ALL_FOLDERS:
        led = [r for r in ledger if r["strategy"] == f and r["tier"] == R.TIER_MAIN]
        mine = [r for r in b1 if r["strategy"] == f]
        if not led and not mine:
            continue
        res_lots = [r for r in mine if grp.get(r["lot_id"]) in RESOURCE_GROUPS]
        size_rows.append([name(f), len(led), sum(1 for r in led if r.get("signal_used") == "Y"), len(mine),
                          sum(1 for r in a_sim if r["strategy"] == f), len(res_lots)])
        perf_rows.append([name(f), "A_actual(실제 · 진실값)"]
                         + perf_cells(perf([r for r in a_actual if r["strategy"] == f])) + ["-"])
        asf = [r for r in a_sim if r["strategy"] == f]
        perf_rows.append([name(f), "A_sim(실제 매수 · 같은 시뮬)"] + perf_cells(perf(asf)) + [replay_share(asf)])
        perf_rows.append([name(f), "B1 전체"] + perf_cells(perf(mine)) + [replay_share(mine)])
        for key, label in A_GROUPS:
            g = [r for r in mine if grp.get(r["lot_id"]) == key]
            if g:
                perf_rows.append([name(f), f"B1 중 {label}"] + perf_cells(perf(g)) + [replay_share(g)])
    L.append(md_table(["전략", "후보 행(main)", "사용 신호 Y", "B1 로트", "A_sim 로트", "B1 중 A 가 자원 제약(캡·현금)으로 못 산 것"],
                      size_rows))
    L += ["", md_table(["전략", "묶음"] + PERF_HDR + ["재현 신호 비중"], perf_rows),
          "", "- A 와 B 는 «A_sim 대 B1»(같은 진입·청산 시뮬)으로만 비교한다. A_actual 은 참고(진실값 · 체결가·시각이 다르다).",
          "- «재현 신호 비중»이 높은 묶음(특히 «A 캡»·«A 이미 보유»)은 라이브가 그 종목을 평가하지 않아 신호가 전부 재현이다 — "
          "§1-1 N 방향 표본과 §1-3 빈티지를 함께 볼 것.", ""]

    L += ["## 3. B1 vs B2 — 합산 여부만으로 달라진 것 (②)", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        m1 = [r for r in b1 if r["strategy"] == f]
        m2 = [r for r in accounts if r["strategy"] == f]
        if not m1:
            continue
        p1, p2 = perf(m1), perf(m2)
        t1, t2 = p1["pnl_closed"] + p1["pnl_open"], p2["pnl_closed"] + p2["pnl_open"]
        rows_.append((abs(t2 - t1), [name(f), p1["n"], p2["n"], sum(_i(r["n_adds"]) for r in m2), won(t1), won(t2),
                                     won(t2 - t1), pct(p1["nw"]), pct(p2["nw"])]))
    rows_.sort(key=lambda x: -x[0])
    L.append(md_table(["전략", "B1 로트", "B2 계좌", "B2 추가매수", "B1 손익(원·실현+평가)", "B2 손익(원·실현+평가)",
                       "차(B2−B1)", "B1 명목가중%", "B2 명목가중%"], [r for _, r in rows_]) if rows_ else "(없음)")
    L += ["", "- 차이가 큰 전략부터 — 중복 매수 처리를 따로 정해야 할 후보. 부호보다 크기를 본다. 미청산 로트끼리는 같은 "
          "마지막 종가로 평가돼 합이 같아지므로(Σ(종가−매입가)×수량 = (종가−평단)×총수량) 차이는 청산이 갈린 계좌에서만 생긴다.", ""]

    L += ["## 4. 평단 이동으로 뒤집힌 청산 (③)", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        m2 = [r for r in accounts if r["strategy"] == f and _i(r["n_adds"]) > 0]
        if not m2:
            continue
        c = Counter("reason" if r["avg_flip"].startswith("reason:") else r["avg_flip"] for r in m2)
        slp = sum(1 for r in m2 if r["avg_flip"].startswith("reason:")
                  and ({"sl", "tp"} & set(r["avg_flip"][len("reason:"):].split("→"))))
        clk = sum(1 for r in m2 if r["hold_clock_reset_diff"].startswith("diff:"))
        rows_.append([name(f), len(m2), c.get("same", 0), c.get("date_only", 0), c.get("reason", 0), slp, clk])
    L.append(md_table(["전략", "추가매수 있는 계좌", "B1 첫 로트와 같음", "날짜만 다름", "사유 다름", "그중 손절·익절이 뒤집힘",
                       "시계 리셋 시 청산 달라짐(D4-b)"], rows_) if rows_ else "(추가매수 계좌 없음)")
    L.append("")

    L += ["## 5. 전략별 중복 신호 (④)", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        m1 = [r for r in b1 if r["strategy"] == f]
        if not m1:
            continue
        per_code = Counter(r["code"] for r in m1)
        dist = Counter(min(v, 4) for v in per_code.values())
        rows_.append([name(f), len(m1), len(per_code), sum(1 for r in m1 if r["is_repeat_while_open"] == "Y"),
                      sum(_i(r["n_adds"]) for r in accounts if r["strategy"] == f),
                      max(_i(r["open_lot_seq"]) for r in m1), dist.get(1, 0), dist.get(2, 0), dist.get(3, 0),
                      dist.get(4, 0)])
    L.append(md_table(["전략", "B1 로트", "종목 수", "열린 로트 위 재신호", "B2 추가매수(대조)", "최대 동시 로트",
                       "종목당 1로트", "2", "3", "4+"], rows_) if rows_ else "(없음)")
    L += ["", "- «열린 로트 위 재신호»와 «B2 추가매수»는 같은 시간선(09:00 시가 단계 청산은 진입 전)이라 대부분 같다. 남는 차이는 "
          "로트별 청산과 평단 청산이 갈린 계좌다. rs_leader 는 신호가 매일 반복될 수 있어 로트가 불어난다(스펙 §4 위험).", ""]

    L += ["## 6. 부록 — D1 11~20위 · D3′ 급락 · D2 타전략 보유 · D5 속도 조절 · 수량 근거", ""]
    ext = [r for r in lots if r["arm"] == "B1_ext"]
    nogate = [r for r in lots if r["arm"] == "B1_nogate"]
    lifted = [r for r in b1 if r["entry_basis"] == "after_lift"]
    allday = [r for r in b1 if r["entry_basis"] != "after_lift"]
    oh = [r for r in b1 if r.get("other_holder_live")]
    crash_rows = [r for r in ledger if r.get("crash_blocked") == "Y" and r["tier"] == R.TIER_MAIN]
    st = Counter(r.get("lift_status") or "(밴드 없음)" for r in crash_rows)
    L.append(f"- D3′ 급락 차단 main 행 {len(crash_rows)}: " + (" · ".join(f"{k} {v}" for k, v in sorted(st.items())) or "없음")
             + " (filled = 해제 뒤 체결 · no_minute_data = 분봉 없음 → 본 집계에서 안 산 것)")
    L.append("")
    rows_ = [["D1 스냅샷 11~20위(tier=ext · 본 집계 밖)"] + perf_cells(perf(ext)),
             ["D3′ 해제 뒤 체결(본 집계 안)"] + perf_cells(perf(lifted)),
             ["D3′ 민감도 — 하루 종일 막았으면(B1 에서 해제 뒤 체결 제외)"] + perf_cells(perf(allday)),
             ["D3 반대편 — 게이트가 없었다면 09:02(B1_nogate · 본 집계 밖)"] + perf_cells(perf(nogate)),
             ["D2 라이브였다면 타전략 보유로 막혔을 B1 로트(other_holder_live · 본 집계 안)"] + perf_cells(perf(oh))]
    for k, label in D5_LABELS:
        g = [r for r in b1 if k in (r.get("d5_flags") or "").split(",")]
        rows_.append([f"D5 라이브였다면 {label} 에 막혔을 B1 로트(본 집계 안)"] + perf_cells(perf(g)))
    L.append(md_table(["묶음"] + PERF_HDR, rows_))
    qb = Counter(r["qty_basis"] for r in b1)
    L += ["", "- D5: VI 매수 보류는 DEBUG 로그라 관측 불가 — 표에 없다. 진입억제 표시는 라이브가 그 종목에 매수신호를 낸 날만 "
          "관측된다(라이브가 평가하지 않은 B 로트는 표시 불가).",
          "- B1 수량 근거: " + (" · ".join(f"{k} {v}" for k, v in sorted(qb.items())) or "없음")
          + " (one_share = 주가 > 1,000,000원 → 1주)", ""]

    L += ["## 7. arm A — 후보가 라이브에서 멈춘 단계", ""]
    rows_ = []
    for f in R.ALL_FOLDERS:
        led = [r for r in ledger if r["strategy"] == f and r["tier"] == R.TIER_MAIN]
        if not led:
            continue
        c = Counter(a_group(r) for r in led)
        rows_.append([name(f), len(led)] + [c.get(k, 0) for k, _ in A_GROUPS])
    L.append(md_table(["전략", "후보 행"] + [lbl for _, lbl in A_GROUPS], rows_) if rows_ else "(없음)")
    L += ["", "- 근거(`a_stop_basis`)는 ledger8.csv — log(계기 줄) · timeline(체결 원장 재구성) · vtr · recon · replay.", ""]

    L += ["## 8. 가정·한계", ""]
    L += [f"- {x}" for x in LIMITS]
    L.append("")
    return "\n".join(L)
```

- [ ] **Step 4: `run.py` 수정 — summary.md 생성**

import 블록 `from . import registry as R` 아래에 `from . import report as RP` 추가. `main()` 의 `res: Dict[str, Any] = {}` 줄부터 끝(`ctx.close()`)까지를 아래로 교체(앞부분은 과제 9 그대로):
```python
        res: Dict[str, Any] = {}
        if a.stage == "all":
            res = build_arms(ctx, days, cands, reuse)
            for name, key, cols in OUT_FILES:
                _atomic_write_csv(out / name, cols, res[key])
            _print_counts(res)
            warnings.extend(res["warnings"])
        for w in warnings:
            print(f"[경고] {w}")
        meta = _meta(days, log_dir, a.stage, warnings)
        meta["vintage"] = vintage
        meta["last_bar"] = ctx.calendar[-1].isoformat() if ctx.calendar else ""
        meta["reuse_fills"] = a.reuse_fills or ""
        meta["repeat_vs_adds"] = res.get("repeat_vs_adds", {})
        if a.stage == "all":
            md = RP.render(meta, sig_rows, exit_rows, res["a_sim_entry"], res["ledger"], res["lots"],
                           res["accounts"], res["a_sim"], res["a_actual"], offlist)
            _atomic_write_text(out / "summary.md", md)
        _atomic_write_text(out / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        ctx.close()
```

- [ ] **Step 5: 통과 확인(전체 회귀)**

Run: `$PY -m pytest backtest/concept_axes/ledger8/tests -q -p no:cacheprovider`
Expected: PASS(과제 1~10 전부).

- [ ] **Step 6: 7거래일 전체 실행(기본 창 · results/)**

Run: `$PY -m backtest.concept_axes.ledger8.run`
Expected: 종료코드 0 · `[경고]` 0줄 · 신호·청산 표가 과제 4·6 과 같은 값 · 규모 표 8행 · `backtest/concept_axes/ledger8/results/` 에 13개(`fidelity_signal.csv fidelity_exit.csv offlist_signals.csv ledger8.csv funnel.csv fills_b.csv lots_b1.csv accounts_b2.csv a_sim.csv a_sim_entry.csv a_actual.csv summary.md run_meta.json`). `a_actual.csv` 행 수 = 창 안 실제 매수 76(2026-09-19 DB SELECT: envelope 6 · ma20 7 · ma5 18 · day 13 · elder 11 · min 2 · rs 19). 참고값(계획 검증 실행 2차 · 약 7초) 규모 표 = 후보(main)/사용신호Y/B체결/그중 해제 뒤/B1로트/B2계좌/B1 재신호·B2 추가/A실제: elder 70/58/29/0/29/20/9·9/11 · envelope 6/6/5/1/5/5/0·0/6 · day 70/70/69/0/69/69/0·0/13 · min 50/49/47/9/47/18/29·29/2 · ma20 70/70/54/7/54/45/9·9/7 · ma5 70/70/52/4/52/46/6·6/18 · rs 70/70/56/6/56/34/23·22/19 · deep 0 — B1 312(1차 285 + D3′ 해제 뒤 27) · B2 237. `D3′ 급락 차단 main 행 86 → filled 27 · no_minute_data 44 · unfillable 15`. §6: B1_nogate 70 · B1_ext 251 · D5 진입억제 78 · 25분 쿨다운 6 · 일일손실 0 · one_share 3.

- [ ] **Step 7: 멱등 확인**

Run:
```bash
cd backtest/concept_axes/ledger8/results && sha256sum *.csv summary.md > D:/tmp/ledger8_h1.txt && cd - >/dev/null
$PY -m backtest.concept_axes.ledger8.run
cd backtest/concept_axes/ledger8/results && sha256sum *.csv summary.md | diff D:/tmp/ledger8_h1.txt - && echo IDEMPOTENT; cd - >/dev/null
```
Expected: `IDEMPOTENT`(두 실행 사이 DB 가 바뀌지 않았다면). 다르면 어떤 파일의 어떤 행이 다른지 `diff` 로 찾아 보고(정렬 불안정·dict 순서 의존이 원인일 가능성).

- [ ] **Step 8: 보고서 읽기 점검**

`results/summary.md` 를 열어 확인: §0 LOW 표기가 과제 4·6 게이트 결과와 같다 · §0 의 «전부 bought» · «N 방향 표본 부족» 문장이 §1-1 표 수치와 맞는다(고정 문구 없음) · §1-2 에 v1·v2·v3 세 열과 재구성 모순 v2→v3 건수 · §1-3 에 전략별 재현 비중·빈티지 범위 · rs_leader 가 `[shadow]`/`[live]` 두 줄 · §6 에 D3′(해제 뒤 체결 · 하루 종일 막힘 · 게이트 없음)과 D5 세 줄 · 금액 칸에 소수점 없음 · «총자산»·«누적수익률»·«자본 대비» 문구 없음(`grep -nE "총자산|누적수익률|자본 대비" results/summary.md` 0줄).

- [ ] **Step 9: 교차 확인**

| 스펙 항목 | 충족 위치 | 확인 |
|---|---|---|
| §4-6 보고서 5개 질문 | `render` §2(①) · §3(②) · §4(③) · §5(④) · §1(⑤) | [ ] |
| 실현/미청산 분리 | `perf`(실현 손익·평가 손익 칸) | [ ] |
| envelope 표기(표에서 생성 — 전부 bought 면 «자명한 Y/Y») · rs_leader 모드별·로트 분포 | §0·§1-1 · §5 | [ ] |
| critic 🔴1 방향별 신호 표 · 재현 비중(전략별·A 단계별) · 빈티지 방향·취약 표시 | §1-1 · §1-3 · §2 «재현 신호 비중» 칸 | [ ] |
| critic 🔴2 규칙 민감도(v1·v2·v3) · 재구성 모순 건수 | §1-2 | [ ] |
| D3′ 해제 뒤 체결 · 하루 종일 막힘 · 게이트 없음 / D5 규칙별 플래그 건수·성과 | §6 | [ ] |
| critic 🟡1 B1 재신호 vs B2 추가매수 대조 | §5 «B2 추가매수(대조)» 칸 | [ ] |
| A vs B 는 시뮬 대 시뮬로만 | §2 표(A_sim vs B1) · 문구 | [ ] |
| D1 ext · D2 other_holder_live 별도 집계 | §6 | [ ] |
| 총자산·누적수익률 금지 · 원 정수 · % 2자리 | `won`·`pct` · Step 8 grep | [ ] |
| 멱등(os.replace · 같은 입력 같은 바이트) | Step 7 | [ ] |
| 1주 분기 실질 건수 확인(스펙 위험) | §6 수량 근거 | [ ] |

- [ ] **Step 10: Commit(코드 + 첫 원장)**

```bash
git add backtest/concept_axes/ledger8/report.py backtest/concept_axes/ledger8/run.py backtest/concept_axes/ledger8/tests/test_report.py backtest/concept_axes/ledger8/results/fidelity_signal.csv backtest/concept_axes/ledger8/results/fidelity_exit.csv backtest/concept_axes/ledger8/results/offlist_signals.csv backtest/concept_axes/ledger8/results/ledger8.csv backtest/concept_axes/ledger8/results/funnel.csv backtest/concept_axes/ledger8/results/fills_b.csv backtest/concept_axes/ledger8/results/lots_b1.csv backtest/concept_axes/ledger8/results/accounts_b2.csv backtest/concept_axes/ledger8/results/a_sim.csv backtest/concept_axes/ledger8/results/a_sim_entry.csv backtest/concept_axes/ledger8/results/a_actual.csv backtest/concept_axes/ledger8/results/summary.md backtest/concept_axes/ledger8/results/run_meta.json
git diff --cached --name-only
git commit -F - <<'MSG'
feat(ledger8): 요약 보고서(5개 질문·방향별 충실도·규칙 민감도·D3′·D5) + 09-10~09-18 첫 원장

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```
`git diff --cached --name-only` 가 16줄(코드 3 + 결과 13)인지 확인한 뒤 커밋한다(`.gitignore:139-154` 의 `*.csv` 예외 — 재사용 규칙: 스테이징 목록으로 확인).

---

### Task 11: README + 최종 검증

**Files:**
- Create: `backtest/concept_axes/ledger8/README.md`

**Interfaces:**
- Consumes: 과제 1~10 전부(문서화만).
- Produces: `README.md`(사용법 · 재현 근거 · 출력 · 충실도 · 가정·한계 · 파일 표).

- [ ] **Step 1: `README.md` 작성**

````markdown
# 8전략 세 arm 관측 원장 (`ledger8`)

> **관측 원장이다 — 판정 근거로 쓰지 말 것.** 룰 변경·K 변경·자금한도 해제(본안 재검토 2026-10-17)의 «근거»로 인용하지 않는다.
> 일봉 근사 · gross(수수료·세금 없음) · B 는 자본 분모가 없다(총자산·누적수익률 없음). 봇 코드 0줄 · DB 쓰기 0 · 라이브 로그 읽기만.
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
| `--reuse-fills` | B 진입 집합을 이 파일로 고정(신호 재평가 결과와 무관하게 같은 진입) |
| `--out` · `--log-dir` | 출력 폴더(기본 `results/`) · 라이브 로그 폴더(기본 env `LEDGER8_LOG_DIR` → `<ROOT>/logs` → 라이브 로그) |

- 매 실행은 창 전체를 다시 계산한다(청산이 최신 봉에 따라 바뀜). 같은 입력이면 CSV·`summary.md` 는 같은 바이트이고 실행 시각·git SHA 는 `run_meta.json` 에만 있다.
- 첫 줄의 `key.ini 파일을 찾을 수 없습니다` 경고는 `config.settings` import 부수효과(워크트리엔 key.ini 없음) — 무해, KIS API 호출 0.
- 콘솔에 섞이는 `strategy.RSLeaderStrategy | WARNING | [신호없음] … 진입 제외 «안 함»(mode=shadow)` 줄은 라이브 `_check_buy` 가 찍는 WARNING 이다(부트스트랩은 INFO 이하만 끈다) — 라이브 로그 파일로는 가지 않는다(NullHandler) · 무해.
- K·max_daily_trades·regime_index·rs 모드가 바뀌면 `registry.py` 이력표에 (발효일, 값, 근거) 한 줄을 넣는다 — `tests/test_registry_gate_order.py` 가 최신값을 config 와 대조한다.

## 3. 무엇을 어떻게 재현하나 (라이브 코드 근거 · 커밋 14a9b7a)

- **후보**: `screener_snapshots`(scan_date = D 직전 거래일) 순위순 − 로그 `후보 제외:` → 로그 `[E6] … 목표 N건` 만큼(core/candidate_selector.py:1104-1141).
- **신호**: 라이브 인스턴스(`StrategyLoader.load_strategy` + `on_init(None,None,None)`)의 `_check_buy` 를 그대로 부른다. on_tick 가드(데이터 길이 · 불가능봉)는
  base.py:660-707 그대로, 보유·일일체결·K 게이트는 건너뛴다. 패치 = `MarketHours.is_market_open`(True) · rs_leader 모드(날짜별) · envelope `now_kst`(D 09:02)+캐시 비움.
  상태 무변경 검사(rs_leader `_ontick_skip_log` 예외). 사용 신호는 **로그 우선** — `[on_tick] 매수신호: CODE(`(매수 루프 전용 줄)가 있으면 Y,
  on_tick 이 돌았고 «평가 가능»(`fidelity8.slot_verdict` v3 — 체결 원장 시간선 + 빈자리 구간 안 on_tick 완료 + `[캡]` 줄 없음)했는데 없으면 N, 그 밖은 재현.
  신호 일치는 Y·N 방향을 나눠 본다(검증 실행: N 방향 표본은 elder 11 뿐). 재현 행은 day·min 룰 여유와 «빈티지 취약»(관측 재기록 폭 안에서 뒤집힐 수 있음)을 표시한다.
- **진입(B·A_sim)**: D 09:02 한 번 — D 시가가 밴드 안이면 시가, 밖이고 장중 복귀면 경계값, 장중 내내 밖이면 불가(`cap_skip_ledger/sim.py`).
  그 시각 급락 게이트가 막고 있으면 **D3′ 풀린 뒤 산다** — 로그 시장방향성 시간선의 해제 시각 뒤 첫 밴드 안 분봉(`minute_candles`) 가격(분봉 없으면 `no_minute_data` · 본 집계에서 안 산 것).
  **D5** — 진입억제·25분 매수 쿨다운·VI·일일손실한도는 B 미적용(«후보 통과 종목은 전부 산다»), 라이브였다면 막혔을 로트만 `d5_flags` 로 표시(VI 관측 불가).
- **청산(8전략 공통 1벌)**: 익절·손절 비율 = 라이브 엔진 `execute_virtual_buy` 경로(config `take_profit_pct/stop_loss_pct` → 손절 하한 3%)를
  캡처 스텁으로 호출해 얻는다. 데이터 청산 = 전략 사본에 포지션(평단·첫 매수 시각)을 넣고 `now_kst` 를 D+k 09:02 로 바꿔
  `generate_signal(code, D+k 일봉 창, 'daily')` → `_check_sell`. 하루 순서 = 보유기간(position_monitor `days_held=k`) → 갭 익절 →
  데이터 청산 → 갭 손절(라이브는 09:05 이후 — 플래그) → 장중 고저 터치(동시면 손절 우선).
- **arm A 멈춘 단계**: fill · cash(수량부족·잔고) · gate(타전략 보유 · 시장급락 · 일일손실한도 · 밴드·매수스톱 · 진입억제 · 기타) · unexplained · cap · held · signal.
  근거 = 로그 계기 줄(`[on_tick] 매수신호` 뒤 실행 경로 줄을 그 (전략, 종목)에 귀속 — 봇은 전략을 하나씩 돈다) → 체결 원장 시간선 → 재구성.

## 4. 출력 (`results/`)

| 파일 | 내용 |
|---|---|
| `summary.md` | 사람용 요약 — 신뢰도 · 충실도 · ① A vs B1 · ② B1 vs B2 · ③ 평단 뒤집힘 · ④ 중복 신호 · 부록 · A 멈춘 단계 · 가정·한계 |
| `ledger8.csv` | 1행 = (날짜, 전략, 종목, tier) — 후보·«평가 가능»(v3·v2·v1)·신호(재현/로그/사용)·룰 여유·빈티지·밴드·A 단계·B 진입·D1~D5 플래그(해제 뒤 진입 포함)·로트/계좌 id |
| `funnel.csv` | (날짜, 전략, 종목, 단계, 결과) + n/first_ts/last_ts/basis — 접힌 단계 행 |
| `fills_b.csv` | B 진입 집합(동결용) |
| `lots_b1.csv` | B1 로트(`arm` = B1 · B1_nogate · B1_ext) — `is_repeat_while_open · open_lot_seq · days_since_open_lot · exit_phase · lift_time · d5_flags` |
| `accounts_b2.csv` | B2 계좌 — `n_adds · avg_price_path · final_avg_price · hold_clock_reset_diff · avg_flip` |
| `a_actual.csv` · `a_sim.csv` · `a_sim_entry.csv` | 실제 체결 · 같은 시뮬 로트 · 시뮬 진입가 vs 실제 체결가 |
| `fidelity_signal.csv` · `fidelity_exit.csv` · `offlist_signals.csv` | 신호(v1·v2·v3 결과 · 재구성 모순 · 룰 여유)·청산·익절손절 충실도 · E6 목록 밖 매수신호 |
| `run_meta.json` | 실행 시각 · git SHA · DB · 로그 폴더 · 창 · 최신 봉 · 관측 빈티지 · B1 재신호 vs B2 추가매수 · 경고 |

## 5. 충실도 기준 (🔒 결과를 보고 바꾸지 않는다)

- 신호: 전략별(rs_leader 는 모드별) · 방향별(Y = 로그 Y 중 재현 Y · N = 로그 N 중 재현 N) 일치율 ≥ 90% · 방향 분모 < 5 면 그 방향 «판정 불가» · 두 방향 다 모자라면 «판정 불가». 판정 가능 행이 전부 실제 체결(bought)이면 보고서가 «자명한 Y/Y» 라고 적는다(표에서 생성).
- «평가 가능» 규칙: v3 고정(`fidelity8.slot_verdict`) · v1(09:02 한 시점)·v2(classify_candidate) 결과를 늘 함께 싣는다 — 변경 이력은 계획서 「계획 검증 실행」.
- 청산: 전략별 실제 청산된 건의 사유 일치율 ≥ 70% · 분모 < 5 면 «판정 불가».
- 익절·손절: 엔진 경로 값 = 체결 원장 BUY 의 `target_profit_rate/stop_loss_rate`.
- 미달 전략은 `summary.md` 에서 `[신호 충실도 낮음]` · `[청산 충실도 낮음]` 을 달고 나온다.

## 6. 가정·한계

`summary.md` §8 과 같다(`report.LIMITS`). 핵심: B 진입은 D 09:02 한 번(D5 규칙 미적용 · 막혔을 건 표시 · VI 관측 불가) · 급락일은 D3′ 해제 뒤 분봉 진입(분봉 없는 종목 ~절반은 안 산 것) ·
청산은 일봉 근사(시뮬 손절이 실제보다 많을 수 있음) · 신호 N 방향 오류율은 elder 외 잴 수 없음 · 재현 신호는 «지금 DB» 빈티지(재기록은 09-14 연장 전에도 있었음 · day 는 Y 쪽 · min 은 N 쪽으로 기움) ·
daytrading `auto` 는 «지금» 시장 매핑 · 관측 기간이 짧아 대부분 미청산 → `--reuse-fills` 로 재추적 · gross · 생존편향·adj_factor 계열 결함 그대로.

## 7. 파일

| 파일 | 역할 |
|---|---|
| `registry.py` | 8전략 명세(게이트 순서·K·max_daily_trades·regime_index 이력·rs 모드·상태 검사) |
| `sizing.py` | arm A 수량 상한 · arm B 수량 |
| `logscan8.py` | 라이브 로그 1회 순회 · 게이트 귀속 · 시장방향성 시간선 |
| `livesignal8.py` | 라이브 `_check_buy` 재현 · 강제 밴드 |
| `sellprobe8.py` | 엔진 경로 익절·손절 비율 · 매도 탐침 |
| `exitsim8.py` | 봉 단위 청산 순서 엔진(순수) |
| `stages.py` | arm A 멈춘 단계(순수) |
| `arms.py` | A_actual · A_sim · B1 · B2 엔진(순수) |
| `fidelity8.py` | 충실도 판정·집계 · «평가 가능» 규칙 `slot_verdict` · 빈티지 표시(순수) |
| `sources8.py` · `context8.py` | DB SELECT · 실행 문맥 |
| `run.py` · `report.py` | CLI · 요약 MD |
| 재사용(수정 금지) | `../minervini/cap_skip_ledger/{bootstrap,sources,sim,tradecal,classify}.py` |
````

- [ ] **Step 2: 최종 검증 — 라이브 코드·재사용 원본 무변경**

Run:
```bash
git diff --stat main...HEAD -- core strategies bot api db config
git diff --stat main...HEAD -- backtest/concept_axes/minervini
git status --short
```
Expected: 앞 두 줄 출력 0줄(라이브 코드 0줄 · cap_skip_ledger 무변경). `git status --short` 는 README 1개만.

- [ ] **Step 3: 최종 검증 — 자리표시·건너뛴 테스트 없음 · 전체 테스트**

Run:
```bash
grep -rnE "TODO|FIXME|XXX|pytest\.skip|mark\.skip|xfail|\.only\(" backtest/concept_axes/ledger8 --include=*.py
$PY -m pytest backtest/concept_axes/ledger8/tests -q -p no:cacheprovider
$PY -m pytest backtest/concept_axes/minervini/cap_skip_ledger/tests -q -p no:cacheprovider
```
Expected: grep 0줄 · ledger8 전부 PASS · cap_skip_ledger 테스트 전부 PASS(재사용 원본 회귀 없음).

- [ ] **Step 4: 교차 확인(스펙 §4-7 + 계획 전체)**

| 항목 | 확인 |
|---|---|
| README 가 사용법·재현 근거·출력·충실도 기준·가정·한계·파일을 담는다 | [ ] |
| 스펙 규약: 라이브 코드 0줄 · DB 쓰기 0 · 총자산·누적수익률 없음 · 「관측 원장」 문구 · 멱등 · push·머지 없음 | [ ] |
| 과제 4·6 게이트 결과(LOW 여부)가 관리자에게 보고됐다 | [ ] |

- [ ] **Step 5: Commit**

```bash
git add backtest/concept_axes/ledger8/README.md
git diff --cached --name-only
git commit -F - <<'MSG'
docs(ledger8): README — 세 arm 정의·사용법·재현 근거·출력·충실도 기준·한계

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git log --format='%h %an <%ae> %s' -12
```
Expected: 마지막 줄 목록의 저자가 전부 `tgparkk <sttgpark@gmail.com>`. push·머지하지 않는다.

---

## Self-Review (계획 작성자 점검 · 2026-09-19)

**1. 스펙 대비 누락 점검**

| 스펙 항목 | 과제 |
|---|---|
| §0-1~3 자금한도 해제 · 전부 산다 · `max(1, floor(1e6/주가))` | 1(`arm_b_qty`) · 9(`attach_rows` — B 는 보유·캡·현금 무시) |
| §0-4 B1/B2 두 세계 · 신호 공유 시뮬 두 벌 | 8 · 9 |
| §0-5 A = 라이브 그대로 · 룰 그대로 | 3(`_check_buy` 그대로) · 6(`_check_sell` 경로 그대로) · 7 · 8(A_actual·A_sim) |
| §0-6 라이브 무변경 · 원장 먼저 | 전 과제 규약 · 11 Step 2 |
| 검증표 #1 · #20 게이트 순서 테스트 | 1 |
| #2 매도 1벌 | 5 · 6 |
| #3 [캡]∩E6 · #4 신호 기준 줄 · #16①②③ | 2 · 4(귀속 실데이터 검증) |
| #5 envelope 230봉 · 자체 프레임 | 1(문서) · 3(`now_kst` 패치·캐시) |
| #6 [캡] 3전략 · #11 CAP_LOG_SINCE | 1 · 7(`cap_log`) |
| #7 ref_key · elder 매수스톱 | 1 · 3(테스트) |
| #8 K 이력 · #9 일일 «체결» | 1 · 3(`slot_verdict` = 체결 원장 시간선 · 체결 수 한도) |
| #10 rs 모드 날짜 | 1 · 3 |
| #12 복리 per_stock · #13 deep_mr · #14 종목당 상한 | 1(sizing) · 2(로그 파싱) · 9(`per_stock_for`) |
| #15 G2·G3 + 추가 게이트(급락·국면·쿨다운·상한가·타전략·일일손실) | 2(`parse_gate`) · 7(`GATE_KIND`/`GATE_DEPTH`) |
| #17 불가능봉·rs 제외 줄 주석 정정 | 2 |
| #18 폴더키 · 섹터뉴스 모드 매일 | 2 · 4 |
| #19 7거래일 | 1 |
| 3-1 livesignal8 공통·전략별 특이사항 | 3 |
| 3-2 매도 탐침 · 손절·익절 경로 · 09:05 · 손절 우선 · 같은 날 순서 | 5 · 6 |
| 3-3 진입 세 밴드 · 상한가 +25% 플래그 | 9 |
| 3-4 소유자 미지정 SELECTED 제외 · 목록 밖 매수신호 칸 | 4(`offlist_signals.csv`) · 9(`TIER_OFFLIST`) |
| 3-5 D2 | 9 |
| 3-6 중복 신호 플래그(B1·B2) · n_evals 는 로그 측에만 | 7(`funnel`) · 8 |
| 3-7 replayer 와 병행(합치지 않음) | 범위 밖 — 이 계획은 replayer 코드를 쓰지 않는다. 빈티지는 «보정»하지 않고 드러낸다: 로그로 판정 가능한 행은 로그 신호(그 시점 DB)를 쓰고, 재현 행은 전략별·A 단계별 비중(§1-3·§2)과 day·min 룰 여유·«빈티지 취약» 표시(관측 재기록 폭 · 방향)로 공개한다(설계 판단 2) |
| 3-8 파일 구성·테스트 목록 | 1·2·3·5·6·7·8·10(테스트 파일 11개 · 140개) |
| §4 순서 ①~⑦ · 신호 충실도 B 전 · 청산 충실도 | 과제 1~11 순서 · 4 Step 6 · 6 Step 9 게이트 |
| §4 위험: 로그 오염 · envelope · rs · 빈티지 · 짧은 기간 · 09-14 급락 · 1주 분기 | 2 · 4 · 6 · 9(`qty_basis`) · 10(§0·§6·§8) · `--reuse-fills` |
| 결정 D1~D4 · 창 · 스키마 · 보고서 5개 질문 · 규약 | 9 · 10 · Global Constraints |
| 추가 결정 D3′ 풀린 뒤 산다(분봉 · 해제 시각 · 진입일 규칙 · 하루 종일 민감도) | 2(시장방향성 시간선) · 5(`lift_entry` · `touch_bar`) · 8(해제 뒤 추가매수) · 9(`attach_rows` · `B1_nogate`) · 10(§6) |
| 추가 결정 D5 빼되 표시(규칙별 플래그 · 건수·성과) · 설계 판단 7 근거 교체 | 2(`G_DAILY_LOSS`) · 9(`d5_flags`) · 10(§6) · 설계 판단 7 |
| critic 🔴1 Y 방향만 검증 → 방향별 표 · 재현 비중 · 룰 여유·빈티지 방향 | 3(`signal_table` · `volume_margin` · `vintage_fragile`) · 4(표) · 10(§0·§1-1·§1-3·§2) |
| critic 🔴2 «평가 가능» 규칙 — v3 · 순수 함수+반례 테스트 · 모순 건수 · v1 민감도 · 변경 이력 공개 | 2(`ontick_times`) · 3(`slot_verdict` · 테스트 3) · 4(민감도·모순 출력) · 10(§1-2) · 「계획 검증 실행」 |
| critic 🟡1 시가 단계 청산 로트 | 5(`ExitOut.phase`) · 8(`_open_on` · 테스트 2) · 9(`repeat_vs_adds`) · 10(§5) |
| critic 🟡2 envelope 고정 문구 → 표에서 생성 | 1(registry note) · 10(§0 문장 생성) · 11(README §5) |
| critic 🟡3 빈티지 문구(연장 전에도 재기록) | 설계 판단 2 · `report.LIMITS` · README §6 |
| critic 🟡4 A_sim 수량 없음 → 경고 | 9(`a_sim_fills` warns) |
| critic 🟡5 trading_analyzer 인용 줄 | 재확인 결과 127-130 이 맞다(127 POSITIONED 조회 · 128-130 판정·로그·return · 132-136 은 25분 쿨다운) — 7(`GATE_DEPTH` 주석)에 풀어 적음 |

**2. 자리표시 점검** — 「TBD/TODO/나중에/적절히」 없음. 모든 코드 단계에 실제 코드, 모든 실행 단계에 명령·기대 결과. 확인이 필요한 사실은 아래 「⚠️ 미확인」으로 모았고 각 항목에 해소 단계를 지정했다.

**3. 이름·타입 일관성** — `ExitRules/Pos/ExitOut/Probe/PathT/LiftEntry/lift_entry/PHASE_*`(과제 5)를 6·8·9 가 같은 이름으로 쓴다. `F.SlotVerdict/slot_verdict/vintage_fragile/day_volume_vintage`(3) = `Ctx8.slot_state`·`evaluate_candidates`(4). `Fill.touch_bar/lift_time/d5`(8) = `attach_rows`·`fill_rows`·`read_fills`(9). `Fill` 키 `(d, folder, code, tier)`(9 `FillKey`) = `fill_rows`/`read_fills` 열. `StratDay.cap_blocking/gates_for`(2) = `AFacts.cap_log/gates`(7). `F.signal_log_state/decide_signal/signal_outcome/signal_table`(3) = run(4). `F.actual_reason/exit_outcome/exit_table/tp_sl_table/entry_diff_stats`(6) = run(6·10)·arms 테스트(8). `Ctx8.rules/probes`(6) = `build_arms`(9). `run.EARLY_FILL`(6) = `a_sim_fills`(9).

## ⚠️ 미확인 (계획 작성 시점에 코드·데이터로 닫지 못한 것)

1. **신호 N 방향(「라이브 N 인데 재현 Y」) 오류율** — 로그 N 표본이 elder 11 외 0 이라 7그룹은 잴 수 없다. B1 로트의 51%(day 71% · min 81% · ma20 69%)가 재현 신호이고 «A 캡»·«A 이미 보유» 묶음은 100% 재현이다. 창을 넓히거나 라이브에 «평가했는데 N» 계기 줄이 생기기 전에는 닫히지 않는다 — 보고서 §0·§1-3 이 표시한다.
2. **D3′ 분봉 공백** — `minute_candles` 는 ~300종목/일이라 급락 차단 main 행 86 중 44(51%)가 분봉 없음 → 본 집계에서 «안 산 것». 이 44행이 실제로 해제 뒤 밴드 안에 들어왔는지는 모른다(민감도: «게이트 없었다면» 70 로트 · «하루 종일 막았으면» 285 로트를 함께 싣는다).
3. 전략 `self.positions` 가 체결 원장 시간선과 같다는 전제(held·no_slot 재구성) — 직접 검증 불가 → `basis=timeline` 표기. 재구성 모순(no_slot ∧ 로그 매수신호)이 v3 에서 0 인 것이 간접 증거.
4. 창 안 0건이라 실측 표본이 없는 로그 줄(`국면게이트` · `매수 거부:` · `매수 차단: 상한가 접근` · `[진입억제] … 이번 사이클` · `일일 손실 한도 초과`) — 코드 문자열(core/trading_context.py:370·391-395·433-436·479-481·497-501)로 정규식을 적었다.
5. D5 의 VI 매수 보류(DEBUG 로그)는 관측 불가 — 표시하지 않는다. 진입억제 표시는 라이브가 그 종목에 매수신호를 낸 날만 관측된다.
6. 충실도 기준값(`SIG_AGREE_MIN=0.90 · EXIT_REASON_MIN=0.70 · FID_MIN_N=5`)은 minervini 원장(90%·80%)을 참고한 관리자 수준 선택이다 — 결과를 보고 바꾸지 않는다.

**계획 검증 실행으로 해소된 것**(2026-09-19): QuantDailyReader 경계(`date <= end_date · LIMIT 봉 수` · psycopg2 — db/quant_daily_reader.py:161-184) · `auto` 지수 해석(005930→KOSPI · 209640→KOSDAQ) · `bc7df66` 은 `max_positions` 3줄만 변경 · 게이트 귀속 실데이터(미귀속 0 · `가상매수:` 귀속 = 체결 원장) · 실행 시간(1일 3초 · 7일 7초) · 합성 테스트 날짜 휴장 없음(140 passed) · `zoneinfo` 가용(`Asia/Seoul`) · 8전략 `on_init(None,None,None)` 성공(스펙 3-1 의 «추측» 해소) · `minute_candles` 스키마(`trade_date` YYYYMMDD 문자열 · PK stock_code+trade_date+idx) · `TradingStock.buy_cooldown_minutes`=25 를 덮는 코드 없음.
