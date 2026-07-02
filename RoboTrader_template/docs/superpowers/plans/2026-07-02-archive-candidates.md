# ARCHIVE 후보 판정표 (2026-07-02)

> `tools/gen_archive_candidates.py` 생성. 재실행 가능(일회성 아님) — `docs/INVENTORY.md` 재생성 후 이 스크립트를 다시 돌리면 판정이 갱신된다.
>
> 판정 로직: docs/INVENTORY.md에서 태그 `UNREFERENCED` & 경로가 `scripts/`인 행만 대상 →
> ops 화이트리스트(`scripts/kis_db/*`, `backfill_*`, `preflight_*`, `seed_*`, `schema*`, `refresh_*`, `reconcile_*`) 매칭 시 KEEP →
> 나머지는 stem(확장자 뺀 파일명)을 repo 전체 `*.py`/`*.bat`/`*.ps1`에서 substring 검색(자기 자신·`__pycache__`·`archive/`·`docs/` 제외) — 1건이라도 hit면 KEEP(보수적 방향), 0-hit면 ARCHIVE.

| path | git 최종커밋일 | 판정 | 근거 |
|---|---|---|---|
| `scripts/10pct_strategy/_test_dataload.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/_v3_report_only.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/_v3_write_reports.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p0_regime_label.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p1_forward_return_matrix.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p2a_universe_filter.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p3_portfolio_walkforward.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_cmf_walkforward.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_ma_align_walkforward.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_nhb_optimization.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_obv_walkforward.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_roe_walkforward.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_stage_rerun_v2.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_tom_walkforward.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_vwap_daily_cache.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/p5_vwap_walkforward.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/_build_phase2_summary.py` | 2026-06-03 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/_check_ks11.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/_check_parquet_cols.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/_check_phase4.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/_phase1_pilot.py` | 2026-05-03 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/_run_elder_mkt_rs_sweep.py` | 2026-06-03 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/_run_phase2_filters.py` | 2026-06-03 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/_run_phase2_gaps.py` | 2026-06-03 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/analyze_anti_regime.py` | 2026-05-28 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/analyze_fade_vwap_regime.py` | 2026-05-28 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/analyze_intraday_5pct_spikes.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/analyze_morning_5pct_spikes.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/analyze_sideways_subdivision.py` | 2026-05-28 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/analyze_trend_starter_poc.py` | 2026-05-07 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/book_rebalance_multiverse.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/build_intraday_universe.py` | 2026-05-21 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/canslim_backtest.py` | 2026-05-29 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/canslim_pattern_backtest.py` | 2026-05-29 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/canslim_screener.py` | 2026-05-29 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/check_kospi_minute_source.py` | 2026-05-19 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/debug_grid_njobs2.py` | 2026-05-15 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/debug_grid_njobs8.py` | 2026-05-15 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/debug_has_adj.py` | 2026-05-07 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/debug_has_adj2.py` | 2026-05-07 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/debug_single_cell.py` | 2026-05-07 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/diag_trail_ab.py` | 2026-05-21 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/discovery/entry_sim_day.py` | 2026-06-22 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/extract_spike_precursors.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/fix_079650_fictional_fill.py` | 2026-07-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/lynch_kis_sim.py` | 2026-02-21 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/lynch_multiverse_kis.py` | 2026-02-21 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/phase1_forward_return_baseline.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/regime_split_dino_surge.py` | 2026-05-31 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/regime_split_moonbyungro.py` | 2026-05-30 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/regime_split_trading_legends.py` | 2026-05-31 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/rs_leader_validation.py` | 2026-07-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/run_raschke_daily.py` | 2026-05-29 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/run_surge_fade_minute.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/run_systrader79.py` | 2026-05-30 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/run_trend_starter_poc.py` | 2026-05-07 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/sawkami_simulation.py` | 2026-02-21 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/signal_combo_phase1_relabel_v2.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/signal_combo_phase2_exit_grid.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/signal_combo_phase3_entry_compare.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/signal_combo_phase4_swing.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/simulate_pair.py` | 2026-05-28 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/step3d_backfill_5p5yr.py` | 2026-06-28 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/sweep_anti.py` | 2026-05-28 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/sweep_fade_vwap.py` | 2026-05-28 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_fdr_foreign.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_krx_direct.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_krx_session.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_naver_foreign.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_naver_foreign2.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_naver_poc.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_pykrx.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_pykrx2.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_pykrx3.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_pykrx4.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/test_pykrx5.py` | 2026-06-02 | ARCHIVE | stem 0-hit (repo 전체 py/bat/ps1 검색, 자기 자신 제외) |
| `scripts/10pct_strategy/check_no_lookahead.py` | 2026-06-02 | KEEP | stem hit: `lib/pit_helpers.py:206` |
| `scripts/10pct_strategy/p2b_signal_multiverse.py` | 2026-06-02 | KEEP | stem hit: `scripts/10pct_strategy/p2c_exit_grid.py:7` |
| `scripts/10pct_strategy/p2c_exit_grid.py` | 2026-06-02 | KEEP | stem hit: `scripts/10pct_strategy/p3_portfolio_walkforward.py:60` |
| `scripts/10pct_strategy/p5_obv_swing_walkforward.py` | 2026-06-02 | KEEP | stem hit: `scripts/10pct_strategy/_v3_report_only.py:317` |
| `scripts/10pct_strategy/p5_stage_rerun.py` | 2026-06-02 | KEEP | stem hit: `scripts/10pct_strategy/p5_stage_rerun_v2.py:2` |
| `scripts/__init__.py` | 2026-05-07 | KEEP | stem hit: `main.py:70` |
| `scripts/_analyze_phase2_filters.py` | 2026-06-03 | KEEP | stem hit: `scripts/_build_phase2_summary.py:2` |
| `scripts/analyze_tick_trace.py` | 2026-04-12 | KEEP | stem hit: `tests/test_scripts/test_analyze_tick_trace.py:2` |
| `scripts/backfill_corp_events.py` | 2026-06-02 | KEEP | ops 화이트리스트: backfill_* |
| `scripts/backfill_daily_prices_fundamental.py` | 2026-05-29 | KEEP | ops 화이트리스트: backfill_* |
| `scripts/backfill_foreign_flow.py` | 2026-07-02 | KEEP | ops 화이트리스트: backfill_* |
| `scripts/backfill_kospi_index.py` | 2026-06-02 | KEEP | ops 화이트리스트: backfill_* |
| `scripts/backfill_operating_cash_flow.py` | 2026-05-30 | KEEP | ops 화이트리스트: backfill_* |
| `scripts/discovery/__init__.py` | 2026-06-12 | KEEP | stem hit: `main.py:70` |
| `scripts/exit_multiverse/__init__.py` | 2026-05-31 | KEEP | stem hit: `main.py:70` |
| `scripts/feature_edge/__init__.py` | 2026-06-13 | KEEP | stem hit: `main.py:70` |
| `scripts/feature_edge/timing/__init__.py` | 2026-06-13 | KEEP | stem hit: `main.py:70` |
| `scripts/kis_db/__init__.py` | 2026-06-22 | KEEP | ops 화이트리스트: scripts/kis_db/* |
| `scripts/regime_split_elder_minervini.py` | 2026-05-30 | KEEP | stem hit: `scripts/regime_split_moonbyungro.py:9` |
| `scripts/regime_split_minervini.py` | 2026-05-29 | KEEP | stem hit: `scripts/regime_split_elder_minervini.py:8` |
| `scripts/regime_split_weinstein.py` | 2026-05-29 | KEEP | stem hit: `scripts/regime_split_elder_minervini.py:9` |
| `scripts/rs_leader/__init__.py` | 2026-06-06 | KEEP | stem hit: `main.py:70` |
| `scripts/run_books_research.py` | 2026-05-28 | KEEP | stem hit: `scripts/book_param_multiverse.py:73` |
| `scripts/run_daytrading_3methods.py` | 2026-05-31 | KEEP | stem hit: `scripts/book_param_multiverse.py:12` |
| `scripts/run_elder_triple_screen.py` | 2026-05-30 | KEEP | stem hit: `scripts/portfolio_sim_elder.py:3` |
| `scripts/run_greenblatt_magic.py` | 2026-06-05 | KEEP | stem hit: `scripts/book_rebalance_multiverse.py:64` |
| `scripts/run_haru_silijeon_minute.py` | 2026-05-30 | KEEP | stem hit: `scripts/run_haru_silijeon_daily.py:3` |
| `scripts/run_lynch_one_up.py` | 2026-06-05 | KEEP | stem hit: `scripts/book_rebalance_multiverse.py:68` |
| `scripts/run_multiverse_grid.py` | 2026-05-08 | KEEP | stem hit: `multiverse/tests/test_grid_runner.py:265` |
| `scripts/run_oshaughnessy_value.py` | 2026-06-05 | KEEP | stem hit: `scripts/book_rebalance_multiverse.py:65` |
| `scripts/run_screener.py` | 2026-02-09 | KEEP | stem hit: `main.py:557` |
| `scripts/run_spike_precursor_poc.py` | 2026-05-07 | KEEP | stem hit: `multiverse/tests/test_grid_runner.py:265` |
| `scripts/run_weinstein_stages.py` | 2026-05-29 | KEEP | stem hit: `strategies/books/weinstein_stages/rules.py:4` |
| `scripts/signal_combo_phase1.py` | 2026-06-02 | KEEP | stem hit: `scripts/signal_combo_phase1_relabel.py:2` |
| `scripts/signal_combo_phase1_relabel.py` | 2026-06-02 | KEEP | stem hit: `scripts/signal_combo_phase1_relabel_v2.py:2` |
| `scripts/stage1_analyze.py` | 2026-05-13 | KEEP | stem hit: `scripts/run_bb_reversion_3stage.ps1:66` |
| `scripts/stage3_recommend.py` | 2026-05-13 | KEEP | stem hit: `scripts/run_bb_reversion_3stage.ps1:200` |
| `scripts/step3_pit_rebaseline.py` | 2026-06-25 | KEEP | stem hit: `scripts/step3c_size_sector_filter.py:11` |
| `scripts/walkforward_envelope.py` | 2026-06-07 | KEEP | stem hit: `scripts/multiverse4_returns_export.py:9` |

**ARCHIVE 76건 / KEEP 39건 / 합계 115**(scripts 계열 UNREFERENCED 전수). 참고: docs/INVENTORY.md 전체 UNREFERENCED는 이보다 많을 수 있음(multiverse/ 등 scripts/ 외 계열 포함, 이 판정 범위 밖 — 스펙 §1 불가침).
