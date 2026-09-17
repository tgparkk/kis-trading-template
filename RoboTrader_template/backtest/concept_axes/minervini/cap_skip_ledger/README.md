# minervini 「자리 없어 못 산 후보」 원장 (`cap_skip_ledger`)

> **관측 원장이다 — 판정 근거로 쓰지 말 것.** 룰 변경·K 변경·전략 평가의 «근거»로 인용하지 않는다.
> 사이징·현금·장중 체결·데이터 빈티지를 무시한 **일봉 근사**이고 결과는 **% 뿐**이다(원화 환산 금지).
> 봇 코드 0줄 · DB 쓰기 0 · 라이브 로그는 읽기만. 사장님 승인 2026-09-17 밤.

## 1. 목적

`minervini_volume_dryup` 은 `generate_signal` 에서 **보유 한도 확인(strategy.py:158-160)이 매수 판단 `_check_buy`(:167) «앞»**
에 있다. 그래서 자리가 꽉 찬 날엔 «샀을 신호»가 아예 계산되지 않고, 로그에는 `[캡] … 사유=max_positions`
한 줄(종목당 하루 1줄, 2026-09-16~)만 남는다. K=3 포화로 2026-09-11~09-17 다섯 거래일 매수 0 인 동안
TT 통과 후보는 5→6→9→11 로 늘었다.

이 도구는 거래일 D 마다 그날의 후보를 다시 세우고, **라이브와 같은 코드·같은 입력**으로 «샀을 신호»를 판정한 뒤,
샀다면 어떻게 됐을지를 일봉으로 근사해 기록한다.

## 2. 사용법

워크트리에서만 돌린다(라이브 트리 `D:/GIT/kis-trading-template` 에서 실행 금지). 파이썬은 라이브 venv 인터프리터.

```bash
cd <worktree>/RoboTrader_template
PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe

# 기간 재생성 (첫 원장)
$PY -m backtest.concept_axes.minervini.cap_skip_ledger.run --start 2026-09-10 --end 2026-09-17

# 매일 EOD 에 이어 붙이기 — 최근 25거래일을 «재생성»(가상 청산이 새 봉으로 갱신된다)
$PY -m backtest.concept_axes.minervini.cap_skip_ledger.run --end 2026-09-18 --days 25
```

| 옵션 | 뜻 |
|---|---|
| `--start` / `--end` | 재생성할 거래일 범위(KOSPI 달력). `--start` 생략 시 `--end` 에서 `--days` 거래일 역산 |
| `--days` | `--start` 생략 시 재생성 거래일 수(기본 1). 최대 보유 20거래일 + 여유 → **EOD 는 25 권장** |
| `--out` | 출력 폴더(기본 이 폴더의 `results/`) |
| `--log-dir` | 라이브 로그 폴더(읽기 전용). 기본 = env `CAPLEDGER_LOG_DIR` → `<ROOT>/logs`(파일 있으면) → `D:/GIT/kis-trading-template/RoboTrader_template/logs` |
| `--no-fidelity` | 충실도 검증(최근 30거래일) 생략 |

- **멱등** — `ledger.csv` 는 «재생성한 날짜의 행만» 지우고 다시 쓴다(임시파일 → `os.replace`). 같은 입력이면 같은 바이트.
  실행 시각·git SHA 는 `run_meta.json` 에만 있다.
- **EOD 실행 시점** — 당일 `robotrader_template_*.log` 는 콘솔 캡처라 봇 가동 중엔 덜 써져 있을 수 있다. 덜 써진 날은
  `list_src` 에 `no_e6_log(default)` 가 찍힌다 → 다음 날 `--days 25` 재생성이 자동으로 메운다.
- 실행 첫 줄의 `key.ini 파일을 찾을 수 없습니다` 경고는 `config.settings` import 부수효과다(워크트리엔 key.ini 없음) — 무해, KIS API 호출 0.
- K 가 바뀌면 `classify.py` 의 `K_HISTORY` 에 (발효일, K, 근거) 한 줄을 추가한다. 이력표 최신값과 `config.yaml` 이 다르면 실행이 경고한다.

### 출력

| 파일 | 내용 |
|---|---|
| `results/ledger.csv` | 1행 = (D, 후보 종목). 컬럼 §4 |
| `results/ledger_summary.md` | 사람용 요약 — 머리에 **원장 신뢰도** · 날짜별 표 · 샀을신호 Y 미매수 목록 · 충실도 검증 · 가정·한계 |
| `results/fidelity_buys.csv` | 충실도 검증 — 최근 30거래일 실제 minervini BUY 건별 대조 |
| `results/run_meta.json` | 실행 시각 · git SHA · DB · 로그 폴더 · 경고 |

## 3. 무엇을 어떻게 재현하나 (라이브 코드 근거 · 커밋 c565256 실측)

### 3-1. 라이브가 day D 에 `generate_signal` 로 넘기는 일봉

```
BaseStrategy.on_tick                                   strategies/base.py:661-708
  → TradingContext.get_daily_data(code)                core/trading_context.py:176-199   (days=None → OHLCV_LOOKBACK_DAYS=120 달력일)
    → PriceRepository.get_daily_prices(code, 120)      db/repositories/price.py:145-180
         SELECT date,o,h,l,c, volume×COALESCE(adj_factor,1) FROM daily_prices WHERE date ≥ now_kst()−120일 ORDER BY date  (상한 없음 · 가격 무조정)
    → TradingContext._drop_unconfirmed_today_bar       core/trading_context.py:143-174   (마지막 봉 날짜 == 오늘이면 제거)
  → len < get_min_data_length()(=40) 스킵              base.py:663
  → describe_impossible_drop(data) 스킵                base.py:696
  → generate_signal(code, data, 'daily')               base.py:708 → 캡 체크(strategy.py:155-160) → _check_buy(:167)
```

⇒ **마지막 봉 = D-1 확정봉**(D 당일 부분봉은 드롭) · 길이 ≈ 80~85봉 · reader = `PriceRepository`(daily_prices) ·
거래량만 분할조정, 가격 무조정.

재현(`sources.live_daily_window`): 위 두 라이브 함수를 **그대로** 부르고, 두 모듈의 `now_kst` 만 D 09:02 KST 로 바꿔
끼운다(프로세스 안 mock · 파일 무수정). «그 시각엔 없던» D 이후 행은 먼저 잘라낸다.

### 3-2. 후보와 상태

- **후보** = `screener_snapshots`(strategy=minervini, scan_date = D 의 직전 거래일 · 달력 = `daily_prices` 'KOSPI')
  순위순 − 로그의 안전필터 `후보 제외` → 로그 `[E6] … 목표 N건` 만큼(`core/candidate_selector.py:1110-1141`).
- **상태**(우선순위 순)

| 상태 | 판정 |
|---|---|
| `bought` 실제 매수됨 | 그날 `virtual_trading_records` minervini BUY |
| `held` 이미 보유 | 09:00 에 minervini 가 보유 중(라이브는 `_check_sell` 로 간다 · strategy.py:152) |
| `no_slot` 자리 없음 | 체결 원장 시간선으로 장 전체 보유수 ≥ K(또는 체결수 ≥ max_daily_trades) · **또는** 모든 빈자리가 목록상 «앞 순위» minervini 매수로 닫힘 |
| `slot_available` 자리 있었음 | 그 밖 — 빈자리가 있었는데 안 샀다(밴드·쿨다운·타전략 보유 등 다른 사유) |

- K 는 날짜별 `K_HISTORY`(2026-06-02~ 3 · 2026-09-18~ 6). `[캡]` 로그(2026-09-16~)는 `cap_log`·`evidence` 칸에 교차 증거로만 쓴다.
- `other_holder` — 09:02 에 같은 종목을 **다른 전략**이 들고 있었으면 표시. 라이브는 전략 무관 POSITIONED 종목의 매수
  신호를 무시한다(`bot/trading_analyzer.py:126-129`) → 자리가 있어도 못 샀다.

### 3-3. 샀을 신호 (룰 복제 0)

`StrategyLoader.load_strategy('minervini_volume_dryup')` + `on_init(None,None,None)` 로 config 를 읽은 **라이브 인스턴스**의
`_check_buy(code, data)` 를 그대로 부른다(`MarketHours.is_market_open` 만 True 로 고정). 호출 전후 `positions`·
`daily_trades`·캡 로그 집합·config 를 비교해 **상태 무변경**을 확인한다(바뀌면 예외).
비율 표시는 라이브 룰 클래스 `rule_volume_dryup(ratio_max=∞)` 의 사유 문자열, 경계 근접(`near_threshold`)은 0.68/0.72 두 번 호출.

**빈티지 칸** — 라이브 스크리너 `MinerviniVolumeDryupScreenerAdapter.match()`(tt off · ratio_max ∞)로 «지금 DB» score(최근 30봉
평균 거래량)를 얻어 스냅샷 score(D 09:00 라이브 스캔)와 비교: `same`(≤1e-6) · `minor`(≤0.5%) · `changed`.
**스냅샷 동등 신호** — 재현이 `dryup_not_met` 인데 빈티지가 바뀌었으면, 스냅샷 종목은 D 09:00 에 같은 룰·같은 파라미터로 dryup 을
통과했으므로 «라이브 시점 신호 = Y»로 보고 `signal_used=Y · signal_basis=snapshot_equiv` 로 둔다(밴드는 라이브 `_entry_band`).
`signal` 칸(재현값)은 그대로 남긴다.

### 3-4. 가상 진입·청산 (`sim.py` · 가정)

- **진입**: 기준가 = 신호 `metadata.close`(D-1 종가) · 밴드 = 신호 `entry_min/max_price`(+3% 상한). D 시가가 밴드 안 → D 시가 ·
  시가가 밖이고 장중 복귀 → 밴드 경계값(시각 불명 · D 당일 고저는 청산에 안 씀) · 장중 내내 밖 → `unfillable` · D 봉 없음 → `no_bar`.
- **청산**(라이브 `position_monitor` 순서: 보유기간 → 익절 → 손절): 보유일 k(D=0)마다 봉 시작에 라이브
  `evaluate_sell_conditions(hold_days=k)` 가 참이면 그 봉 시가(`max_hold` · 20거래일) · 시가 ≥ +12% → 시가 익절 · 시가 ≤ −8% →
  시가 손절 · 장중 고저 **둘 다 닿으면 손절 우선** · 한쪽만이면 경계값 · 끝까지 안 닿으면 `open`(마지막 종가 평가).
  비교식은 라이브와 같은 수익률식 `(px−entry)/entry ≥ tp`.
- `v_dup_of` — 같은 종목의 앞선 가상 포지션이 아직 열린 날의 행. 합산할 때 빼야 한다.

## 4. `ledger.csv` 컬럼

| 묶음 | 컬럼 |
|---|---|
| 키 | `date`(D) · `scan_date`(D-1 스냅샷) · `code` · `snap_rank` · `list_pos`(라이브 E6 목록 순서) · `list_src` |
| 자리 | `K` · `n_open_0900`(체결 원장) · `restore_log_n`(07:40 복원 로그의 minervini 수 — 교차 확인) · `slot_windows` |
| 상태 | `state` · `state_ko` · `state_note` · `cap_log`(Y/N/NA) · `evidence` · `other_holder` |
| 신호 | `signal`(재현) · `signal_reason` · `dryup_ratio`(지금 DB) · `near_threshold` · `n_bars` · `last_bar` · `snap_score` · `score_now_vs_snap` · `vintage` · `signal_used` · `signal_basis` · `ref_close` · `band_max` |
| 라이브 로그 | `live_signal_log`(minervini «매수 시그널» 줄: 시각·기준가·비율) · `live_nosignal_log` · `live_notes`(진입억제·매수거절) |
| 가상 | `v_entry_status` · `v_entry_basis` · `v_entry_price` · `v_entry_vs_ref_pct` · `v_entry_note` · `v_exit_status` · `v_exit_reason` · `v_exit_date` · `v_exit_price` · `v_ret_pct` · `v_hold_days` · `v_exit_note` · `v_dup_of` |
| 실제(bought 행) | `actual_buy_time` · `actual_buy_price` · `actual_exit_date` · `actual_exit_price` · `actual_exit_reason` · `actual_ret_pct` |
| 메모 | `assumptions` · `caveats` |

## 5. 충실도 검증 (매 실행 · `--end` 기준 최근 30거래일)

실제 minervini BUY 가 있던 날마다 같은 도구를 돌려 대조한다(결과 MD §2).

1. 실제 매수 종목이 재구성한 E6 목록에 있나 · 상태가 `bought` 로 분류되나 · `_check_buy` 가 Y 인가
2. **라이브 «매수 시그널» 로그 줄 전수 대조** — 목록 안 종목의 로그 비율(소수 2자리)·기준가 vs 재현
3. **예측 매수 집합** — 09:02 빈자리만큼 목록 순서대로 [신호 Y ∧ D 시가 밴드 안 ∧ 타전략 미보유], 이후 기존 보유분 매도 때마다 1자리씩
   → 실제 매수 집합과 비교. 전략 `positions` 가 비어 K 캡이 작동하지 않은 날(보유 종목에도 매수 시그널)은 따로 센다.
4. 가상 진입가(D 시가) vs 실제 체결가 — |차| 평균·최대와 **부호 포함 평균·양수 건수·반대 사례**(진입차% = (가상 ÷ 실제 − 1)×100 · + = 가상이 비쌈) ·
   실제 종료 건의 가상 청산 사유·날짜 일치. **청산 일치 분모 = «실제 청산된» 건**이다 — 양쪽 보유 중인 건과 «실제는 보유 중·가상만 종료»인 건은
   뺀다(2026-09-17 원장: 9/13 의 13 = 16 − 073240(양쪽 보유) − 241710·006360(가상만 종료) · 두 건을 불일치로 넣으면 9/15 · 사유 12/15). 결과 MD §2-1 표 아래에 분모 내역을 찍는다.

재현률(3)이 80% 미만이거나 로그 비율 일치(2)가 90% 미만이면 MD 머리에 **[원장 신뢰도 낮음]** 과 원인을 찍는다(숨기지 않는다).

## 6. 가정·한계

- **빈티지** — D-1 이하 봉의 «값»은 지금 DB 다. D 15:3x 이후 재기록(시간외 합산 등 · `../../replayer/TRACE_M4_channel_2026-09-15.md`)과
  2026-09-14 KRX 거래시간 연장 뒤의 일봉 거래량 증가로 거래량 비율이 라이브 시점과 달라질 수 있다 → `vintage` · `near_threshold` ·
  `snapshot_equiv` 로 표시. 라이브 시그널 로그 대조는 캡 포화로 2026-09-11 이후 로그가 없어 **연장시간 이후 구간은 직접 검증되지 않았다**.
- **원장 범위 = E6 목록 한정** — 라이브 minervini `on_tick` 은 E6 목록만이 아니라 `get_selected_stocks()`(core/trading_context.py:273-298)가 돌려주는 «소유자 미지정» SELECTED 종목도 평가한다([캡] 고유 종목 2026-09-16 51 · 09-17 53 vs E6 목록 9 · 10). 목록 밖 재현 `_check_buy` Y 는 09-16 7 · 09-17 6 이고 09:02 기준 대부분 타전략 보유(매수 무시 대상)지만, 09-16 413630 은 보유자가 없어 자리가 있었다면 살 수 있던 Y 다(단 minervini 첫 [캡] 10:44:41 엔 book_pullback_ma20 이 10:39:59~10:58:49 보유). 이 기간 결론은 안 뒤집힌다 — [캡] 첫 줄 순서상 목록 종목(보유분 제외 7·8)이 목록 밖보다 먼저 평가되고, 매일 목록 안 Y 가 빈자리보다 많다. [캡] 로그 이전(~09-15)은 목록 밖 종목을 셀 수 없다.
- **장중 체결 무시** — 라이브는 첫 틱(≈09:02) 실시간가로 사고, 빈자리가 늦게 생기면 그 시각 가격에 산다. 원장은 D 시가.
  **진입가 편향의 방향**(2026-09-17 원장 · 충실도 창 08-06~09-17): 가상 진입가 − 실제 체결가 부호 포함 평균 **+1.14%**(16건 중 13건 양수) ·
  09:05 이전 첫 틱 체결 6건(09:02:43~09:03:03) **+0.72%**(5/6 양수) → **가상 진입이 실제보다 비싸게 잡히는 경향**이다(손절·익절 경계도 진입가를 따라 옮겨진다).
  반대 사례도 있다 — 006360(09-10 · 첫 틱 −0.57%) · 069540(08-25 −0.74%) · 002990(08-10 −0.10%). 최신 값은 결과 MD §2-1.
  라이브 `position_monitor` 는 주기 폴링이라 짧은 꼬리를 못 볼 수 있다(예: 241710 2026-09-10 10:15 1분봉 저가 −9.6% 에도 손절 없음)
  → **가상 손절이 실제보다 많을 수 있다.** 체결가는 경계값(갭은 시가)이지만 라이브는 넘어선 실시간가로 체결한다.
- **자리·현금 무시** — 가상 포지션끼리 자리를 다투지 않는다(같은 날 여러 건이 모두 «샀다»고 가정). 사이징·수수료·세금 없음.
- **재현 안 하는 라이브 가드** — 시장급락 게이트 · 국면 게이트 · VI · 상한가 접근 · 진입 쿨다운/사이클 한도 · 일일 손실 한도 · 수량 부족.
  → **샀을 신호 Y ≠ 살 수 있었다.**
- **구간 차** — 2026-08 초(충실도 창 앞부분)는 전략 `positions` 가 비어 K 캡이 매수를 막지 않았고, 2026-08-25 이전 매도에는 전략
  `_check_sell` 의 D-1 종가 sl/tp(1810cd2 로 제거)가 섞여 있으며, TT 게이트 on(86ff02d) 전후로 스냅샷 크기가 20 → 2~11 로 바뀌었다.
- 섹터뉴스 재정렬은 기본 shadow(순서 불변) 가정. 생존편향·adj_factor 계열 결함(병합·감자 미조정·정지 패딩)은 그대로다.

## 7. 파일

| 파일 | 역할 |
|---|---|
| `bootstrap.py` | 안전 설정 — `PGOPTIONS=default_transaction_read_only=on`(서버가 쓰기 차단) · 라이브 로그 파일 핸들러 NullHandler 선점 · `TIMESCALE_DB` = resolver |
| `sources.py` | DB SELECT — 달력·스냅샷·체결 원장(전 전략)·OHLC · 라이브 일봉 창 재현 |
| `livesignal.py` | 라이브 전략 인스턴스 로드 · on_tick 가드 → `_check_buy` · 비율/빈티지 표시 |
| `logscan.py` | 라이브 로그 읽기 — E6 목록·안전필터 제외·[캡]·매수 시그널·복원 수·진입억제 |
| `classify.py` | 순수 — K 이력·체결 원장 → 포지션 시간선·빈자리 구간·상태 |
| `sim.py` | 순수 — 가상 진입·청산 |
| `tradecal.py` | 순수 — 거래일 달력 |
| `run.py` | CLI · 원장 조립 · 예측 매수 · 충실도 · 요약 MD |
| `tests/` | 단위 테스트(DB·로그 없음) — 달력 조인 · 상태 분류 · 손절 우선 · 로그 파싱 |

```bash
$PY -m pytest backtest/concept_axes/minervini/cap_skip_ledger/tests -q -p no:cacheprovider
```
