# 사전등록 — D-1 게이트 관측 번들: 로그·shadow 전용 4건 ③④⑤⑥ (2026-09-24)

> 상태: **발효 대기** · 발효 **2026-09-28(월) 07:40 재기동**
> 번들 = 이 문서(③④⑤⑥) + 전수 저장 사전등록 `docs/prereg_2026-09-24_screener_fullpass_snapshot.md`(브랜치 `feat/screener-fullpass-snapshot` 커밋 `28727e0` 동결 · 발효 2026-09-28 07:40)
> 분류: 계기(로그 전용) 3건 ③④⑥ + shadow 계기 1건 ⑤ · 매수·매도 거동 **바이트 동일** · DB 쓰기 **0** · 룰·사이징 코드 **0줄** · 대조군 5전략 `strategy.py` **0줄**
> 브랜치 `feat/gate-observability-bundle`(워크트리 `D:/tmp/kis-wt-gate-obs` ← `main` `cb2acfc`) · 이 문서 작성 시점 코드 변경 0줄
> 근거: 09-21 EOD 보고서 `docs/reports/2026-09/report_2026-09-21_장마감.md` §13 D-1(:778) · §2-2(:71-82) · §2-3(:84-97) · §8(:501-613)

---

## §0 전제 · 동결 조항

- **0-1 사장님 결정 원문(2026-09-24)**: 「**로그·shadow만 ②③④⑤⑥ + 전수 저장**」 → 「**②는 10-05 판정 뒤로**」 · 「**⑤ shadow 계기 = 집중 3전략만**」 · ⑥ 대상 = `수량부족` 만 · ③ 으로 인한 기존 테스트 기대 문자열 3곳 변경 = 승인(§4-1 에 사전등록).
  ⇒ **이 번들 = ③④⑤⑥.** ② 는 §8(10-05 K 판정 뒤 별도 사전등록) · ① `daily_trades`→`daily_buys` 는 2026-10-17 재검토(§8).
- **0-2 3전략 룰 동결(2026-09-05)**: ma20·minervini·daytrading 진입·청산 룰은 **2026-10-16 까지 변경 0건**. 본 번들은 `evaluate_entry`·`_check_buy`·`_check_sell`·`get_max_quantity` 본문을 한 줄도 바꾸지 않는다.
- **0-3 계기 조항**: `docs/plan_2026-09-05_focus3_roadmap_amendment_2026-09-15.md:16` 원문 — 「**계기(로그 전용) 변경은 예산 밖이지만 별도 커밋·별도 승인이다.**」 ⇒ 이 문서가 그 별도 승인 요청서다. 선례 `36fe61c`(09-16 `_log_cap_skip`) · `6d155fd`(09-19 요약줄 「자리·일일」 칸).
- **0-4 ⑤ 는 09-18 패널이 기각한 Q2-ⓒ 가 «아니다»**: ⓒ = 「`_check_buy` 를 먼저 돌리고 캡을 나중에」(순서 변경 · `PANEL_quant.md:27` · `PANEL_dev.md:272`). ⑤ 는 캡 판정이 먼저 · `return None` 그대로 · 캡 분기 «안»에서 순수 함수만 추가 호출이다. 게이트 순서 통일(ⓑ)도 하지 않는다(`PANEL_dev.md:43`·`:271`).
  🔑 **패널 반론 병기**: 「ⓒ 는 불필요하다 — 같은 정보를 라이브 0줄로 만드는 도구가 이미 머지됐다(`48b2fe1`)」(`PANEL_dev.md:13`). **⑤ 의 실제 값은 오프라인 재현이 못 주는 «그날 봇이 본 데이터 그대로의 판정»이다** — 재현기는 «지금 DB» 를 읽어 거래량 재기록(빈티지)에 룰이 갈린다(`ledger8/registry.py:129` 「거래량 룰 — 빈티지 위험」 · `livesignal8.py:48` `VOLUME_RULE_BIAS`).
- **0-5 발효 중인 K 상향 사전등록과의 관계**: `docs/prereg_2026-09-15_focus3_K_raise.md` 는 「**나머지 5전략은 손대지 않는다 = 대조군.**」(:104) · 「**나머지 5전략 0줄.**」(:347)을 걸고, P5(5전략 매수 패턴 변화 = 0 · :364 · 위반 시 즉시 롤백 :490)를 **09-18~10-05 창**(:549)에서 잰다.
  - ② 를 뺐으므로 대조군 5전략(elder·rs_leader·ma5·envelope·deep_mr)의 `strategy.py` 는 이 번들에서도 **0줄**이다. 09-18 패널도 ⓐ(5전략 `_log_cap_skip`)를 「대조군 5전략의 `generate_signal` 을 P5 감시 중에 건드린다」며 **창 밖(10-16 이후)** 으로 돌렸다(`PANEL_dev.md:270`) — ② 연기의 근거다.
  - ③④⑥ 는 **공유 코드만** 바꾸고(`strategies/base.py` · `core/trading_decision_engine.py` · `bot/trading_analyzer.py`) 바뀌는 것은 **로그 문자열뿐**이다. 🔴 **선언**: ④·⑥ 의 `[매수거절]` 문구와 ③ 의 on_tick 호출 래핑은 **대조군 포함 8전략 전부**의 코드 경로·로그에 나타난다(예: elder 의 `수량부족·단가초과`).
  - **09-28 07:40 을 P5 창 안의 «기지 사건»으로 사전등록한다.** P5 는 체결·포화율 SQL 로 재므로(:364 「같은 SQL」) 로그 문구는 측정값에 들어가지 않는다. 09-28 이후 P5 가 깨져도 **§4-1 I1~I4 불변 테스트가 통과했다면 이 번들 탓으로 돌리지 않는다**; 실패했다면 이 번들이 1순위 용의자다.

> 🔎 **쉬운 설명 — 용어 셋**
> - **P1/P2(게이트 순서)**: 「살까?」 전에 거치는 칸막이 순서. P1(ma20)은 「분봉이면 그만」을 먼저, P2(minervini·daytrading)는 「보유 중이면 팔지부터」를 먼저 본다. **이번에 안 바꾼다.**
> - **루프밖**: 봇의 9초 순환 중 「살 후보 훑기(매수루프)」·「보유종목 훑기(매도루프)」 «밖»의 호출. 예: 손절·익절 감시가 ma20 보유종목을 분봉으로 물을 때 찍히는 `[캡] 사유=timeframe` — **매수를 막은 게 아니다.**
> - **스로틀**: 같은 종목·같은 거절은 10분에 한 줄만 적는 장치. 예: minervini 가 088350 을 45초마다 사려다 현금 398원이라 거절돼도 로그엔 10분에 1줄 → ⑥ 이 「외 13회」로 빠진 횟수를 붙인다.

## §1 목적 — 계기별로 무엇에 답하나

| # | 답하는 질문 | 지금 못 답하는 이유 |
|---|---|---|
| ③ | `[캡]` 한 줄이 **진짜 막힌 매수 후보**인가 **남의 보유종목 스캔**인가 | 09-21 ma20 44줄 중 38줄 = 매도루프(7배 과대) · 틱 산술로만 분해 |
| ④ | `수량부족` = **지갑이 비었다**인가 **한 주가 종목당 예산보다 비싸다**인가 | 한 문자열(09-21 508 대 6) · 처방이 정반대 |
| ⑤ | 캡에 막힌 후보가 **룰상 신호였나** | 캡이 걸리면 `_check_buy` 미도달 ⇒ 증거가 원리적으로 없다(09-21 보고서 §2-2) |
| ⑥ | `수량부족` 이 **실제 몇 번** 났나 | 10분 스로틀 — 09-21 로그 514줄 대 실제 ≈1,023회 |

**전수 저장과의 관계**: 전수 저장은 «EOD 스크리너 통과 종목 전체»(후보 풀의 분모)를, ⑤ 는 «그중 장중 후보가 캡에 막혔을 때 룰이 참이었나»(막힘의 비용)를 남긴다. 합치면 **통과 → 후보 → 캡 차단(③) → 룰 참/거짓(⑤) → 자금 거절(④⑥) → 체결**이 로그·DB 로 이어진다. ① 재검토(10-17)의 1차 증거 = ⑤ 의 `캡사유=daily_trades 룰=참` 건수.

## §2 변경 내용 (파일:줄은 `cb2acfc` 기준)

### ③ `[캡]` 경로 태그 (매수루프 / 매도루프 / 루프밖)

- `strategies/base.py:385-387` 옆에 `self._eval_path = None` + ⑤ 상태 2개(`_cap_shadow_logged` · `_cap_shadow_log_date`).
- `:708`(매수루프 `generate_signal`)을 `self._eval_path = "매수루프"` → `try:` 호출 `finally: self._eval_path = None` 으로 감싼다. `:749`(매도루프)도 `"매도루프"` 로 동일. `generate_signal` 은 동기 함수 ⇒ set~reset 사이에 `await` 가 없어 다른 코루틴·`wait_for` 취소(`main.py:486-493`)가 끼어들 수 없다(메인 루프도 순차 `main.py:457-489`).
- `_log_cap_skip`(`:576-605` · 억제 `:587-595`): `path = getattr(self, "_eval_path", None) or "루프밖"` · 억제 키 `(code, reason)` → `(code, reason, path)` · **줄 «끝»에** ` 경로={path}`.
- 형식: `[캡] {folder} {code} 평가 스킵 사유={reason} 보유={n}/{K} 일일매수={d}/{D} 경로={매수루프|매도루프|루프밖}`
- 끝에 붙이는 이유: 기존 파서 `ledger8/logscan8.py:87` · `minervini/cap_skip_ledger/logscan.py:32-33` 가 `…일일매수=(\d+)/(\d+)` 까지를 비앵커 `search`(`:384`·`:94`)로 읽는다 ⇒ 호환. `[캡]` 은 계기가 있는 3전략에서만 찍힌다(② 연기).

### ④ `수량부족` 사유 라벨 — 문자열만, 제어 흐름 0

- `core/trading_decision_engine.py:429-430` `if qty <= 0:` 분기 **안에서만** VTM 신규 읽기 전용 메서드 `describe_zero_quantity(price, strategy_name) -> str` 을 불러 접미를 붙인다. 인자는 엔진이 이미 만든 `ledger_key`(`:419-420`). 가상모드(`:417-423`)만 — 실전 경로(`:424-427`) 문자열 불변.
- 메서드는 G1 `get_max_quantity`(`core/virtual_trading_manager.py:591-621`)와 **같은 항을 같은 규칙으로 읽기만** 한다: budget(`:602-605`) · per_stock(`:606-607`) · cap 은 G1 과 똑같이 `cap is not None and 0 < cap` 일 때만(`:611-612`) ⇒ `eff = min(per_stock, cap)` (cap 무효면 `per_stock`).
- 라벨 3종(현금 = `budget < price` · 단가 = `eff < price`): 현금만 → `수량부족·현금부족` · 단가만 → `수량부족·단가초과` · 둘 다 → `수량부족·현금부족+단가초과` · 둘 다 아님/예외/비문자열 → 접미 `""`(= 현행 `수량부족`).
- 형식(두 금액 모두 인쇄): `[매수거절] {code} 수량부족·현금부족 (전략잔여 {budget:,.0f}원 · 종목당 {eff:,.0f}원 · 1주 {price:,.0f}원)` — 다른 두 라벨도 괄호 안 같은 세 값.
- 호환: 접두 `수량부족` 유지 → `ledger8/logscan8.py:231` `startswith("수량부족")` 그대로 G_QTY · grep `수량부족` 총계 불변. G2 하드거절(`virtual_trading_manager.py:656-661`)은 G1 이 먼저 qty=0 을 만들어 **사실상 도달 불가**(09-21 §8-4) — 불변.

### ⑤ shadow 게이지 — 캡에 막힌 후보의 진입 룰을 «평가만» 해 로그 (집중 3전략만)

- `strategies/base.py` `_log_cap_skip` 뒤(`:605` 다음)에 `_log_cap_shadow(stock_code, reason, evaluate)` 신설. **`_eval_path == "매수루프"` 일 때만** · (code, reason) **거래일당 1회**(표지를 평가 «전»에 찍어 반복 비용 0) · `evaluate()` 반환의 `[0]`(참/거짓)·`[1]`(reasons)만 읽는다 · 전 구간 try/except.
- 형식: `[shadow] {folder} {code} 캡사유={daily_trades|max_positions} 룰={참|거짓|오류} 보유={n}/{K} 일일매수={d}/{D}` (+ 참이면 ` | {reasons}`). `[shadow]` 태그는 09-21~23 로그에 0회(충돌 없음).
- 삽입(`_log_cap_skip` 줄 바로 뒤 · `return None` 앞) — `evaluate` 인자는 그 전략 `_check_buy` 와 **동일**:

| 전략 | daily_trades | max_positions | `evaluate` (= `_check_buy` 호출부) |
|---|---|---|---|
| book_pullback_ma20 | `:142` 뒤 | `:145` 뒤 | `lambda: self.evaluate_entry(data, min_daily_bars=self._min_daily_bars)` (`:260-262`) |
| minervini_volume_dryup | `:156` 뒤 | `:159` 뒤 | 같은 인자 (`:287-289`) |
| daytrading_3methods_breakout | `:133` 뒤 | `:136` 뒤 | `+ high_window=self._high_window` (`:259-261`) |

- `timeframe` 분기엔 넣지 않는다(매수루프는 항상 `'daily'` · `base.py:708`). `cash` 는 룰이 이미 평가·신호된 뒤라 불필요 — ④·⑥ 담당. 대조군 5전략 0줄(§0-5).
- 비용: `evaluate_entry` 는 staticmethod 순수 함수 · on_tick 이 이미 받은 `data`(`base.py:662`) 재사용 · DB/API 0 · 전략당 하루 ≤ 후보 10 × 사유 2 = 20회. 30초 타임아웃(`main.py:424`) 대비 무시 가능(09-21~23 타임아웃 0/0/0).
- `self.positions`·`daily_trades`·`ctx.buy` 무접촉 · **Signal 을 만들지 않는다** ⇒ 🧾·`[on_tick] 매수신호` 줄 0 → ledger8 신호 파서 오염 0.

### ⑥ `수량부족` 스로틀 요약 「… 외 N회」

- `bot/trading_analyzer.py:82` 옆 `self._reject_suppressed: Dict[Tuple[str, str], int] = {}`.
- `:174-178`: `_should_log_reject` 를 결정당 **정확히 1회** 호출해 결과를 변수로 받고, 억제됐고 키(`reject_throttle_key` `:43-56`) head 가 `수량부족` 으로 시작하면 +1 · INFO 통과 때 pop 해 N>0 이면 줄 끝에 ` 외 {N}회`. 창(`REJECT_LOG_INTERVAL` `:23`)·억제 판정·DEBUG 줄 불변 · 다른 사유 불변.
- 의미(사장님 표현): 「**직전 10분간 같은 거절 N회 더**」(정확히는 같은 키의 직전 INFO 이후 억제 횟수). 예 `[매수거절] 088350 수량부족·현금부족 (전략잔여 398원 · 종목당 1,668,815원 · 1주 5,650원) 외 13회`. 새 줄 0.
- 한계: 그날 **마지막 창의 억제분은 찍히지 않는다**(키당 ≤ 1창). 정확 총계는 `전달 매수신호 사용` − 체결 − 타 거절로 복원 가능(§6).

## §3 불변 조건 (하나라도 깨지면 머지 불가)

- **I1 반환값**: 8전략 `generate_signal` 반환이 모든 게이트 상태에서 동일.
- **I2 상태**: `positions`·`daily_trades`·`_max_positions`·`_max_daily_trades` 호출 전후 deepcopy 동일 · `data` 프레임 불변.
- **I3 게이트 순서**: `ledger8/registry.py:19-21` P1/P2/P3 그대로 — `test_gate_order_matches_source`·`test_cap_log_presence` **무수정** 통과.
- **I4 주문**: `ctx.buy`/`ctx.sell` 호출 순서·인자 동일 · 엔진 `qty`·`buy_info` 동일(④ 는 qty≤0 분기의 문자열만).
- **I5 DB**: 새 쓰기·스키마·조회 0. **I6 예외**: 새 코드 전부 try/except. **I7 대조군**: 5전략 `strategy.py`·`config.yaml` diff 0.

## §4 검증 계획

**4-1 단위 테스트**(🔴 pytest 는 워크트리에서만 · 라이브 트리 금지)
- ③ 🔒 **사전등록된 기대값 변경 3곳**: `tests/strategies/test_cap_skip_log.py:77-80`·`:92-95`·`:108-111` 에 ` 경로=루프밖` 추가(×3전략). 신규: 가짜 ctx on_tick 으로 매수루프/매도루프 태그 · on_tick 뒤 `_eval_path is None` · `generate_signal` 예외 뒤에도 None 복구.
- ④ **격자 테스트**: budget·per_stock·cap(None·0·음수·양수)·price 격자에서 `get_max_quantity == 0` ⇔ 라벨 비어 있지 않음 · 3라벨 각각 · 메서드 예외/Mock 반환 시 정확히 `"{code} 수량부족"` · 실전 경로 불변 · `reject_throttle_key` 키 분리 · `logscan8.reject_gate` = G_QTY.
- ⑤ 캡 상태 반환 None · I2 · 매도루프·루프밖 shadow 0줄 · 하루 1회 · 🔑 **동치**: 같은 `data` 로 캡을 풀었을 때 `_check_buy` 가 BUY ⇔ shadow `룰=참`(3전략 × 참/거짓 픽스처) · evaluate 예외 → `룰=오류` 한 줄 · 예외 전파 0.
- ⑥ `_reject_now` 이음매로 창 안 3회 + 창 뒤 1회 → 두 번째 INFO 에 ` 외 2회` · 타 사유 접미 0 · `tests/bot/test_buy_rejection_visibility.py` **무수정** 통과.

**4-2 회귀** — 루트 `pyproject.toml:10` `testpaths = ["RoboTrader_template/tests"]` 는 연구 테스트를 안 돈다 ⇒ 경로를 명시한다(워크트리 루트에서):
`python -m pytest -m "not db" RoboTrader_template/tests RoboTrader_template/backtest/concept_axes/ledger8/tests RoboTrader_template/backtest/concept_axes/minervini/cap_skip_ledger/tests`
1. **편집 «전»** 무수정 `cb2acfc` 로 1회 → 새 기준선 B0(기존 `D:/tmp/ontick_baseline_5958b66.txt` = 5 failed · 8 수집오류는 `cb2acfc` 이전).
2. 브랜치로 같은 명령 → 실패 «집합»을 **B0 · 5958b66 기준선 둘 다와 양방향 차분**. 신규 실패 0 · 사라진 실패는 사유 기록 · 기대값 변경은 4-1 ③ 뿐.
3. 09-28 전 **최종 1회**: 이 브랜치 + `feat/screener-fullpass-snapshot` 을 합친 임시 워크트리에서 같은 명령 → B0 대비 차분.

**4-3 09-28 EOD 점검표**(로그 = 상위집합 `robotrader_template_20260928_*.log`)

| # | 확인 | 방법 | 기대 |
|---|---|---|---|
| E1 | ③ 발효 | `grep -c '\[캡\]'` vs `grep -c '\[캡\].*경로='` | 차 0 |
| E2 | ③ 한 방향 | 3전략 각각: 요약줄 포화 틱 >0 ⇒ `[캡] {folder} … 경로=매수루프` >0 | 성립(예외 §10-2) |
| E3 | ③ 분해 | `경로=매수루프` / `매도루프` / `루프밖` 줄 수(전략·사유별) | 루프밖 = ma20 `timeframe` 뿐 · 매수루프 ≈ §6-1 |
| E4 | ④ | `grep -cE '\[매수거절\] [0-9A-Z]{6} 수량부족( 외 [0-9]+회)?$'` | 0 · 3라벨 합 = `수량부족` 총계 |
| E5 | ⑤ | `[shadow]` 줄 수 = `[캡] … 사유∈{daily_trades,max_positions} … 경로=매수루프` 줄 수 | **정확히 같음** · `룰=오류` 0 |
| E6 | ⑥ | Σ(1+N) over `수량부족` 줄 vs 억제 복원식(§6-3) | 차 ≥ 0 이고 마지막 창 꼬리뿐 |
| E7 | 일관성 점검 | `가상매수:`/`가상매도:` 줄 수 vs VTR BUY/SELL 행 | 일치(기준 §6-4) |
| E8 | 비용 | `grep -c 'on_tick 타임아웃'` | 0 |

## §5 위험 · 새 줄 예산

- **새 줄 예산(일)**: `[shadow]` **상한 60**(3전략 × 후보 10 × 사유 2 · 09-21~23 추정 6~7 / 21~23 / 21~24) · ③ 로 늘 수 있는 `[캡]` 줄(같은 (종목, 사유)가 매수·매도 루프 둘 다 = 후보이면서 남의 보유) **상한 60** · ④ 라벨 줄 = 기존 `수량부족` 줄(195~514 · 새 줄 아님 · 키 분리로 (종목, 창)당 +1 가능) · ⑥ `외 N회` ⊂ ④ 줄(새 줄 0) ⇒ **새 줄 상한 120/일**. (이전 초안의 ≈240 은 ② 포함분 — 폐기.)
- **on_tick 타임아웃**: shadow 는 (code, reason) 첫 조우 1회 · 메모리 데이터 · I/O 0. ③ 은 속성 대입 2회/호출.
- **스로틀 상호작용**: ④ 가 키를 라벨별로 나눠 같은 종목이 라벨을 오가면 창당 최대 라벨 수만큼 줄 · ⑥ 카운터는 키별이라 합산 정확 · `utils/rate_limited_logger.py` 는 WARNING/ERROR 만 제한 ⇒ INFO `[매수거절]` 무영향.
- **해석 위험**: shadow `룰=참` ≠ 「샀을 것」 — 밴드(`trading_decision_engine.py:407-416`)·현금(G1)·쿨다운·타전략 보유 필터 이전의 «신호 수준» 반사실. 보고서에서 「놓친 매수」로 쓰지 말 것.

## §6 09-21~23 기준선 (로그 직접 파싱 + DB SELECT · 재현 = `docs/prereg_2026-09-24_gate_observability_bundle_baseline.py` · 2026-09-24 실행 출력은 그 docstring 끝 · 전 항목 일치)

**6-1 `[캡]`(계기 있는 3전략)** — 줄 = 고유 종목(하루 1회 억제). 매수루프 추정 = 그 종목이 그날 그 전략 매수루프 줄(`[신호없음] … generate_signal None`·`[on_tick] 매수신호`)에 나옴.

| 날짜 | ma20 daily_trades | ma20 max_positions | ma20 timeframe | daytrading daily_trades | daytrading max_positions | 합 |
|---|---|---|---|---|---|---:|
| 09-21 | 44 (매수 6 / 매도 38) | 0 | 10 (루프밖) | 0 | 0 | 54 |
| 09-22 | 49 (7 / 42) | 51 (7 / 44) | 10 | 53 (7 / 46) | 0 | 163 |
| 09-23 | 0 | 55 (5 / 50) | 10 | 52 (7 / 45) | 59 (9 / 50) | 176 |

minervini 0/0/0. 09-21 ma20 6/38 은 보고서 §8-2 틱 산술과 일치.

**6-2 참고 — ② 연기분(대조군 포화 · 요약줄 파싱)**: ma5 포화 틱 65/66 · 58/61 · 59/61, rs_leader 66/66 · 60/61 · 58/61(매수루프 막힌 고유 ma5 9 · 13 · 15 / rs_leader 5 · 4 · 6) · elder·envelope·deep_mr 0. 이 막힘은 ② 가 없는 동안 계속 `[캡]` 0줄이다.

**6-3 `수량부족`** — 라벨은 §2-④ 규칙 그대로 재계산(budget = 전일 `paper_strategy_equity.cash` + 당일 VTR 체결 누적 · 수수료 0.015%·거래세 0.18% · price = 🧾 신호가 · eff = min(per_stock, cap 3,000,000)).

| 날짜 | 줄 / 고유 | 전략별 줄 | 현금부족 | 단가초과 | 현금+단가 | 억제(추정) | 실제 ≈ |
|---|---|---|---|---|---:|---:|---:|
| 09-21 | 514 / 26 | daytrading 330 · minervini 167 · ma20 11 · elder 6 | 508 / 25 | 6 / 1 (elder 039030) | 0 | 509 | 1,023 |
| 09-22 | 214 / 8 | minervini 213 · elder 1 | 213 / 7 | 1 / 1 (elder 039030) | 0 | 215 | 429 |
| 09-23 | 195 / 7 | minervini 186 · elder 9 | 186 / 6 | 9 / 1 (elder 128940) | 0 | 180 | 375 |

- 단가초과 = elder 종목당 435,786 / 434,914원 대 039030 484,000 · 128940 502,000원 · elder 현금 3.6~4.5백만원 ≫ 1주 ⇒ 현금 조건 거짓. cap 은 3일 전 구간 비바인딩.
- 억제 = `전달 매수신호 사용` − 로그 거절 − 체결: 09-21 1,105−553−8 = 544(수량부족 509) · 09-23 452−224−17 = 211(180) · 09-22 는 산식 체결 16 대 DB 18 ⇒ ±2.

**6-4 기타**: 총 줄 11,534 / 12,172 / 9,004 · `[on_tick]` 요약 528 / 492 / 489 · `[매수거절]` 553 / 228 / 224 · on_tick 타임아웃 0 / 0 / 0 · `가상매수:`/`가상매도:` 8/12 · 18/16 · 17/9 = VTR BUY/SELL 8/12 · 18/16 · 17/9.

## §7 롤백

- 항목별 커밋 4개(③④⑤⑥) + 문서 1 → 개별 `git revert` 가능 · 발효는 다음 07:40 재기동 · DB·설정 롤백 없음 · 커밋·revert·push 는 사장님 확인 후.
- **트리거(새 줄 종류만 센다 — 총 줄 수는 9,004~12,172 로 흔들려 쓰지 않는다)**: `[shadow]` > 120/일(상한 60 의 2배) · ③ 으로 2줄이 된 (종목, 사유) 쌍 > 120 · `수량부족·*` 줄 > 1,028(3일 최대 514 의 2배) · **I1 불변 테스트 실패 1건** · **⑤ 원인 on_tick 타임아웃 ≥ 1**(타임아웃 줄 직전 같은 전략 `[shadow]` 줄) · E7 불일치 → 원인 규명 전까지 해당 항목 revert.
- 의존: ⑤ 는 ③(`_eval_path`)에 의존 ⇒ ③ revert 시 ⑤ 동반. ⑥ 은 ④ 와 독립.

## §8 이 문서가 안 하는 것

- **② 5전략 `_log_cap_skip` 배선** — 「②는 10-05 판정 뒤로」 · **10-05 K 판정 뒤 별도 사전등록**(대조군 0줄 유지 · §0-5).
- **① `daily_trades` → `daily_buys` 분리**(라이브 거동 변경) — 2026-10-17 재검토.
- 게이트 순서 통일·재배열(ⓑ) · `_check_buy` 선행 후 캡 적용(ⓒ) — 09-18 패널 기각(§0-4).
- 사이징 변경 일체(K · per_stock · cap · `max_daily_trades` 값 불변) · 후보 종목 분봉 수집.
- 매도루프 `[캡]` 줄 억제(태그만) · 매도루프가 남의 보유종목에 BUY 를 만들고 버리는 경로(`base.py:750`) 수정 · G2 코드 정리 · 1차/2차 스냅샷 문구(D-5) · 새 DB 테이블 · ⑥ 의 `수량부족` 외 사유 확장.

## §9 출처

- 결정: 09-21 보고서 §13 D-1 `:778` · §2-2 `:71-82` · §2-3 `:84-97` · §8-2 `:537-556` · §8-4 `:602-613` · 개정문 `:16` · K 상향 `prereg_2026-09-15_focus3_K_raise.md:104·347·364·490·549` · 09-18 패널 부록 A.
- 코드: `strategies/base.py:383-387·576-605·660-734·739-761` · 3전략 `strategy.py` 위 표 · `core/trading_decision_engine.py:407-430` · `core/virtual_trading_manager.py:591-621·656-661` · `bot/trading_analyzer.py:23·43-56·82-101·174-178` · `core/trading_context.py:185-197` · `main.py:424·486-493`.
- 연구: `backtest/concept_axes/ledger8/registry.py:19-21·29·129·145` · `logscan8.py:87·125-137·231·384` · `stages.py:128-129` · `livesignal8.py:48·90` · `minervini/cap_skip_ledger/logscan.py:32-33·94-97`.
- 테스트: `tests/strategies/test_cap_skip_log.py:69-111` · `tests/bot/test_buy_rejection_visibility.py:206-262` · 설정 `pyproject.toml:10-14`.
- 로그: `logs/robotrader_template_2026092{1,2,3}_*.log`(읽기만) · DB `virtual_trading_records`·`paper_strategy_equity`(SELECT).

## §10 구현 체크리스트 (critic 사소 9건 · 구현 단계에서 처리)

1. **E4 정규식** `\[매수거절\] [0-9A-Z]{6} 수량부족( 외 [0-9]+회)?$` — 라벨 없는 `수량부족` 줄 = 0 기대.
2. **E2 는 한 방향만** — 예외: 후보가 이미 보유(매도 분기) · `base.py:663-707` 스킵(데이터 없음·부족·불가능봉) · 요약줄은 틱 «끝» 값이라 같은 틱 매도로 포화가 바뀐 경우. **E3**: `경로=루프밖` 인데 사유≠timeframe = 포지션 불일치 → 조사.
3. **⑤ 테스트**: `MarketHours.is_market_open` 패치(ma20 `:257` · minervini `:284` · daytrading `:256` · 선례 `livesignal8.py:90`) · `[0]`/`[1]` 읽기와 `| {reasons}` 인쇄 일치(본문 반영) · shadow 줄 `보유=n/K 일일매수=d/D`(본문 반영) · 하루 1회로 충분 = `get_daily_data` 가 당일 미확정봉을 뺀다(`core/trading_context.py:185-197`) ⇒ 하루 내내 D-1 확정봉.
4. **④**: `ledger_key`(엔진 fallback `:419-420`) 전달 · 금액 `{…:,.0f}` · Mock VTM 대비 `isinstance(suffix, str)` 가드(아니면 `""`) · 문구 「G2 사실상 도달 불가」.
5. **③**: 같은 (종목, 사유)가 이제 2줄(매수·매도 루프) 가능 → `ledger8/stages.py:128-129` 의 `Fold.n`·`last`(`logscan8.py:125-137`) 증가 선언 · `cap_skip_ledger/logscan.py:95` 는 첫 줄만 보관(매도루프 줄일 수 있음) · `ledger8/registry.py:29`·`:145` 의 「`사유=timeframe` = position_monitor 경로」 문구를 `경로=루프밖` 기준으로 갱신.
6. **⑥**: `_should_log_reject` 는 결정당 정확히 1회(`bot/trading_analyzer.py:95-100` 가 `_reject_log_times` 를 갱신 — 두 번 부르면 스스로 억제) · 의미 = 「직전 10분간 같은 거절 N회 더」 · 창 상수 `REJECT_LOG_INTERVAL` = `:23`.
7. **롤백 경로**: 워크트리에서 revert → 장 마감 뒤 머지(라이브 트리 장중 브랜치 전환 금지) · ③ 커밋이 ⑤ 상태 속성 2개를 함께 들고 간다(⑤ 만 revert 해도 무해) · E7 은 「일관성 점검」(기준 8/12 · 18/16 · 17/9).
8. **증거 보관(결정)**: 세션 scratchpad 의 `gateobs/baseline.py`·`qty_labels.py` + DB 내보내기 2건(VTR · `paper_strategy_equity`)을 한 파일로 합쳐 **`docs/prereg_2026-09-24_gate_observability_bundle_baseline.py`**(이 문서 옆 · SELECT 전용 · 라이브 import 0 · `test_*` 아님 ⇒ 수집 0)로 뒀다 — ✅ 2026-09-24 실행 출력이 §6 과 일치(docstring 에 박제). 패널 원문은 `scratchpad/`(`RoboTrader_template/.gitignore:267`)라 인용 줄을 부록 A 에 박제.
9. **⑤ vs ⓒ**: 패널 반론(`PANEL_dev.md:13`)과 ⑤ 의 실제 값(그날 봇이 본 데이터 그대로 · 거래량 빈티지)을 §0-4 에 병기(반영) · 쉬운 설명 상자 §1 앞(반영).

## 부록 A. 09-18 패널 발췌 (원문 `RoboTrader_template/scratchpad/eod_20260918/` · gitignore)

- `PANEL_dev.md:13` — 「4. **Q2-ⓒ 는 「계기 변경」이 아니라 「거동 변경」이다.** … 그리고 **ⓒ 는 불필요하다** — 같은 정보를 라이브 0줄로 만드는 도구가 09-17 에 이미 머지됐다(`48b2fe1`).」
- `PANEL_dev.md:270` — 「**ⓐ 5전략에 `_log_cap_skip` 추가** | 🟡 **창 밖(10-16 이후)으로** | 비용은 15줄로 싸지만, 대조군 5전략의 `generate_signal` 을 P5 감시 중에 건드린다.」
- `PANEL_dev.md:271` — 「**ⓑ 게이트 순서 통일** | 🔴 **하지 않는다** | §0 — 양방향 모두 청산 룰 변경. 2026-06-09·06-12 whipsaw 회귀 위험. 하려면 별도 사전등록」
- `PANEL_dev.md:272` — 「**ⓒ `_check_buy` 선행** | 🔴 **하지 않는다. 그리고 불필요하다**」 · `PANEL_quant.md:27` — 「(2) 조항을 ⓒ 에 쓰면 안 된다. 계산 순서를 바꾸는 순간 로그 전용이 아니다.」
