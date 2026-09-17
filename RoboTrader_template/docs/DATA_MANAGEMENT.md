# 데이터 관리 — 언제 무엇이 DB 에 들어오고, 재기동 때 무엇을 읽는가

> 기준일 **2026-09-17** · 코드 `main`@`16a8106`. 이전 판(2026-03-22)은 SQLite 구문·`core/ml_data_collector.py`·08:30 재무 수집·1분 모니터링 등 **존재하지 않는 경로**를 설명하고 있어 전면 교체했다.
> 표·컬럼·접속은 [DATABASE.md](DATABASE.md) · 매매 흐름 전체는 [TRADING_FLOW.md](TRADING_FLOW.md).

---

## 1. 하루 시간표 (DB 쓰기 기준 · 페이퍼 봇 `INSTANCE_ID='default'`)

| 시각 | 무엇 | 코드 | 쓰는 표 |
|---|---|---|---|
| 07:40 기동 | 상태 복원(§4) | `bot/initializer.py` → `bot/state_restorer.py` | (읽기) |
| 장전 루프 | 전략 `get_target_stocks` 등록 → **regime 지수 갱신**(KOSPI/KOSDAQ → `daily_prices` 의사티커, 하루 1회·성공 시 래치) → 브리핑 | `bot/system_monitor._handle_premarket_tasks` → `core/regime/index_refresh.refresh_regime_indices` | `daily_prices` |
| 후보 로드 직전 | 스크리너 스냅샷 훅(`SCREENER_SNAPSHOT_ENABLED=true` 일 때 · 하루 1회 · `scan_date`=직전 거래일) → 후보 저장 | `bot/candidate_loader.py` → `bot/liquidation_handler.run_screener_snapshot_hook` → `runners/screener_snapshot_collector.run_once` · `candidate_repo.save_candidate_stocks` | `screener_snapshots` · `candidate_stocks` · `sector_news_rerank_log`(`core/candidate_selector._apply_sector_news_rerank`) |
| 장중 · 종목 선정 시 | **W1** 일봉 150봉 UPSERT(원주가 · 과거 행은 «빈 칸만», 당일 행만 덮어씀 — `W1_PAST_ROWS_INSERT_ONLY=True`) | `core/intraday_stock_manager.add_selected_stock` → `core/intraday/data_collector._save_daily_to_db` → `db/repositories/price.save_daily_prices_batch` | `daily_prices` |
| 장중 · 체결 즉시 | BUY/SELL 기록(`source='kis_template'` · P/L 은 gross 계산) | `core/virtual_trading_manager` → `db/repositories/trading.save_virtual_buy/sell` (실전은 `core/orders/order_db_handler` · `core/trading/order_completion_handler` → `save_real_buy/sell` → `real_trading_<instance>`) | `virtual_trading_records` / `real_trading_*` |
| 장중 · 분봉 | **DB 쓰기 0** — 분봉은 `IntradayStockManager` 메모리에만 있다(`core/data_collector.RealTimeDataCollector` 는 인메모리). 3초 주기 포지션 감시도 메모리 현재가 | — | — |
| 15:00 EOD 청산 훅 | 페이퍼 현금 잔고 저장(현금만) | `bot/liquidation_handler` → `virtual_trading_manager.save_paper_trading_state` | `paper_trading_state` |
| **15:35+ 후장 블록** | §2 | `bot/system_monitor._handle_postmarket_tasks` | 아래 · `paper_trading_state`(§2 5·8단계 재저장) |

휴장일(`is_holiday`)엔 15:35 블록 전체 스킵. 실전 인스턴스(`INSTANCE_ID≠default`)는 자금 정합성 검증만 하고 **생성 작업은 전부 페이퍼 봇에 위임**(같은 행 이중 UPSERT·분봉 이중 재적재 방지).

## 2. 15:35 후장 블록 — 실행 순서 (`bot/system_monitor._handle_postmarket_tasks`)

1. `_verify_eod_fund_integrity` — 자금 등식 검사(DB 쓰기 0)
2. `tools.daily_trading_summary.print_today_trading_summary` — 일일 매매 리포트(로그 · gross 라벨)
3. `_log_regime_index_resolution` — 급락게이트 지수 해석 집계(로그)
4. `_verify_screener_snapshot` — 오늘 스냅샷 존재 검증(로그)
5. `_run_equity_snapshot` **1차** → `tools/paper_strategy_equity.run_daily_equity_snapshot` → `paper_strategy_equity`(이 시점 보유평가는 전일 종가 · 스냅샷 직전 `_resave_paper_trading_state` → `paper_trading_state` 재저장 · 8단계 재실행 때도)
6. `_run_regime_index_refresh` — KOSPI/KOSDAQ 일봉 → `daily_prices`(멱등 UPSERT)
7. `_run_data_collection` → **`collectors/eod_collection.run_data_collection(trade_date)`** — §3 (수 분, `to_thread`)
8. `_run_equity_snapshot` **재실행** — 당일 종가로 보유평가 덮어쓰기(전구간 UPSERT 멱등 · `paper_trading_state` 재저장 포함)
9. `_log_eod_benchmark` — 벤치마크 한 줄(맨 끝 · `bot/eod_benchmark.py`)

각 단계는 try/except 로 격리된다 — 한 단계 실패가 다음을 막지 않는다.

## 3. EOD 수집 체인 `collectors/eod_collection.run_data_collection` (kis_template 단일 · 단계별 예외 격리 `_safe`)

| # | 키 | 함수 | 하는 일 | 표 |
|---|---|---|---|---|
| 1 | `daily` | `daily_collector.collect_daily` | 유니버스 = `stock_market ∪ daily_prices`(`SQL_STOCK_ONLY`) · 종목당 최근 7봉 KIS fetch → `daily_writer.upsert_daily_rows` → `daily_derived.update_returns_volatility` → `split_factor_infer.infer_and_stamp_split_factors`(corp_events.meta 에 배수·권리락일 스탬프) → `daily_adj.update_adj_factors` → `corp_action_watch.scan_and_queue`(미조정 이력 «탐지만») | `daily_prices` · `corp_events.meta` |
| 2 | `minute` | `minute_collector.collect_minute` | 거래대금 top300(`minute_universe`) 당일 분봉 → `minute_writer.replace_minute_day`(DELETE+INSERT) | `minute_candles` |
| 3 | `index` | `index_collector.collect_index` | KIS 업종 일봉(FDR 폴백) → `index_writer`(날짜 기준 신선도 판정) | `index_daily` |
| 4 | `stock_market` | `stock_market_collector.collect_stock_market` | FDR 상장목록 → 시장 라벨(성공 시에만 `market_classifier.reset_cache`) | `stock_market` |
| 5 | `foreign_flow` | `foreign_flow_collector.collect_foreign_flow` | 네이버 외국인 순매매량 · `rows==0` 은 ERROR 승격 | `foreign_flow` |
| 6 | `corp_events` | `corp_events_collector.collect_corp_events` | OpenDART `list.json` 최근 7일 · `ON CONFLICT DO NOTHING` | `corp_events` |
| 7·8 | `financials` · `financials_reconcile` | `financial_collector.collect_financials` / `reconcile_financials` | DART as-filed 원장(키=접수건) + KIS 분기비율(교차검증용) — 쓰기는 `financial_writer.py` 한 곳 | `dart_financial_*` · `kis_financial_ratio` · `collection_reconciliation` |
| 9·10 | `sector` · `sector_reconcile` | `sector_collector.collect_sector` / `reconcile_sector` | KSIC 명부(SCD2)·업종 일별 성적표·이름표 — 쓰기는 `sector_writer.py` 한 곳 | `stock_sector_map` · `sector_daily_stats` · `ksic_code_name` · `sector_ksic_nodata` |
| 11~15 | `investor_trend` · `program_trade` · `short_sale` · `credit_balance` · `overtime` | `investor_trend_collector` · `market_flow_collector` | KIS 수급 축. 공급 TR 이 **최근 30거래일 롤링**이라 놓치면 영구 결손 → EOD 편입. 각 수집기가 **신선도 가드**(마지막 적재가 오래됐을 때만 실행)를 걸어 보통 `{"skipped": …}` 가 **정상** | `investor_trend_daily` · `program_trade_daily` · `short_sale_daily` · `credit_balance_daily` · `overtime_daily` |
| — | `reconcile` | (항상 `{}`) | 레거시 교차비교는 2026-08-17 폐지. 키만 로그 계약 때문에 유지 | — |

로그 한 줄 「EOD 데이터 수집 완료: 일봉 … 분봉 … 지수 …」에 모든 키가 찍힌다. 시장매핑·수급·외국인 실패는 ERROR 로 승격된다(조용한 결손 방지).

## 4. 재기동 복원 (`bot/initializer.py` → `StateRestorer.restore_todays_candidates`)

1. `_restore_candidates(today)` — `candidate_stocks` 의 **오늘** 행 → `TradingStockManager` 등록.
2. 보유 복원 — 모드별 소스가 다르다:
   - 페이퍼(`paper_trading=true`): `_restore_holdings_from_db` → `db_manager.get_virtual_open_positions()` = `vtr` 에서 `BUY ∧ is_test=true ∧ source='kis_template' ∧ NOT EXISTS SELL`.
   - 실전: `_restore_holdings_from_real_account`(계좌 잔고 대조) + `get_real_open_positions()` = `real_trading_<instance>` 의 **잔량 술어**(`BUY.qty − ΣSELL.qty > 0`, 부분매도 대응).
3. 행마다 `target_profit_rate`/`stop_loss_rate` 복원 — NULL·NaN 이면 `DEFAULT_TARGET_PROFIT_RATE`/`DEFAULT_STOP_LOSS_RATE`, 장기보유는 `_apply_stale_position_check` 가 덮어쓴다. owner 전략(`strategy` 컬럼)별로 `self.positions` 에 주입 · 상태 `POSITIONED`.
4. 보유 0건이어도 `_reconstruct_strategy_ledger([])` 는 반드시 돈다 — 안 돌면 누적손익이 원장에서 사라진다(코드 주석).
5. 현금은 `paper_trading_state` 최근 `eod_balance` 이월 + `get_strategy_trade_sums`(전 이력 gross 합)로 전략별 재구성(`core/virtual_trading_manager`).

로그 「N/N 복원」이 포지션 SSOT 다.

## 5. adj_factor · 기업행위 — 어디서 계산되나

- 규약: **`adj_close = raw_close / adj_factor`** · `daily_prices.close` 는 이미 조정본, `volume` 은 원본(읽을 때 `× COALESCE(adj_factor,1)`). `collectors/adj_factors.compute_adj_factors` 는 «권리락일 이후» 이벤트 계수의 곱만 하고, 방향(분할 `f=10` / 병합 `f=1/10`)은 호출자 `daily_adj.load_split_events` 가 `corp_events.meta.direction` 으로 정한다.
- 조정 시점 = `COALESCE(meta.effective_date, event_date)` — `event_date`(DART 공시일, PK)는 절대 바꾸지 않고, `split_factor_infer` 가 공시일 +90일 구간의 «첫 clean 갭»을 `meta.effective_date` 로 스탬프한다.
- 7봉 창 «밖»의 과거 OHLC 를 다시 쓰는 라이브 코드는 없다 — EOD `daily_writer.upsert_daily_rows` 는 종목당 최근 7봉(`daily_collector.collect_one(lookback_days=7)`)의 OHLCV 를 매일 `ON CONFLICT DO UPDATE` 로 덮어쓰고, 장중 W1 은 당일 행만 덮어쓴다(과거 행은 `DO NOTHING`). 기업행위 매매정지는 7봉보다 길어 창이 정지 구간을 못 넘는다(`corp_action_watch.py` docstring). 미조정 이력은 `corp_action_watch` 가 **목록만** 적재하고, 보정은 `scripts/repair_corp_action_prices.py`(+`db/adj_backup.py` 백업 필수)로 사람이 돌린다.

## 6. 예전 문서에 있었지만 «없는» 것

`SQLite`/`INSERT OR IGNORE` · `core/ml_data_collector.py` · `core/helpers/state_restoration_helper.py` · `save_virtual_sell(profit_loss=…)` 파라미터(P/L 은 내부 계산) · `is_test = 1`(boolean) · `financial_statements` 08:30 수집(writer 0 · 2026-03 스냅샷) · `quant_factor_scores`/08:55 퀀트 스크리닝 실행자 · 1분 모니터링(실제 3초 · `core/trading/position_monitor.py` `monitor_interval = 3`) · `core/post_market_data_saver` 의 일봉 DB 저장(2026-09-03 제거 · 분봉 텍스트 덤프만 남음).
