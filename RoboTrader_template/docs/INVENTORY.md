# INVENTORY — 연구 파일 참조 태깅 (tools/gen_inventory.py 생성)

> **수동 확인 사항 (AST 워커 한계)**
> - **동적 import 미포착**: `scripts/book_rebalance_multiverse.py:428`, `scripts/book_param_multiverse.py:90-93`는 리터럴이 아닌 동적 경로로 모듈을 로드해 AST 리터럴 포착 한계에 걸림 — 아래 태그와 무관하게 수동으로 라이브 의존 여부 확인 필요.
> - **`UNREFERENCED` ≠ 죽은 코드 확정**: `.bat`/CLI 직접 실행 스크립트나 `__main__` 진입점 파일은 다른 `.py`에서 import되지 않으므로 이 워커에는 `UNREFERENCED`로 잡히지만 실제로는 사용 중일 수 있음 — 후속 죽은코드 정리 계획에서 파일별로 개별 판정할 것.

| 파일 | 태그 | 참조자 |
|---|---|---|
| `multiverse\__init__.py` | UNREFERENCED | - |
| `multiverse\composable\__init__.py` | UNREFERENCED | - |
| `multiverse\composable\_normalize.py` | UNREFERENCED | - |
| `multiverse\composable\exit_rule.py` | UNREFERENCED | - |
| `multiverse\composable\features\__init__.py` | UNREFERENCED | - |
| `multiverse\composable\features\spike_features.py` | UNREFERENCED | - |
| `multiverse\composable\holding_cap.py` | UNREFERENCED | - |
| `multiverse\composable\paramset.py` | UNREFERENCED | - |
| `multiverse\composable\personas\__init__.py` | UNREFERENCED | - |
| `multiverse\composable\personas\_grid.py` | UNREFERENCED | - |
| `multiverse\composable\personas\intraday.py` | UNREFERENCED | - |
| `multiverse\composable\personas\long_term.py` | UNREFERENCED | - |
| `multiverse\composable\personas\quant.py` | UNREFERENCED | - |
| `multiverse\composable\personas\spike_precursor.py` | UNREFERENCED | - |
| `multiverse\composable\personas\spike_precursor_inverse.py` | UNREFERENCED | - |
| `multiverse\composable\personas\swing.py` | UNREFERENCED | - |
| `multiverse\composable\personas\trend_starter.py` | UNREFERENCED | - |
| `multiverse\composable\rebalancer.py` | UNREFERENCED | - |
| `multiverse\composable\regime.py` | UNREFERENCED | - |
| `multiverse\composable\scorer.py` | UNREFERENCED | - |
| `multiverse\composable\signal_gen.py` | UNREFERENCED | - |
| `multiverse\composable\sizer.py` | UNREFERENCED | - |
| `multiverse\composable\strategy.py` | UNREFERENCED | - |
| `multiverse\composable\universe.py` | UNREFERENCED | - |
| `multiverse\data\__init__.py` | UNREFERENCED | - |
| `multiverse\data\corp_events.py` | UNREFERENCED | - |
| `multiverse\data\kospi200_pit.py` | UNREFERENCED | - |
| `multiverse\data\pit_reader.py` | UNREFERENCED | - |
| `multiverse\data\quality.py` | UNREFERENCED | - |
| `multiverse\engine\__init__.py` | UNREFERENCED | - |
| `multiverse\engine\pit_engine.py` | UNREFERENCED | - |
| `multiverse\engine\portfolio_engine.py` | UNREFERENCED | - |
| `multiverse\labels\__init__.py` | UNREFERENCED | - |
| `multiverse\labels\spike_label.py` | UNREFERENCED | - |
| `multiverse\metrics\__init__.py` | UNREFERENCED | - |
| `multiverse\metrics\calculator.py` | UNREFERENCED | - |
| `multiverse\persistence\__init__.py` | UNREFERENCED | - |
| `multiverse\persistence\paramset_store.py` | UNREFERENCED | - |
| `multiverse\persistence\parquet_writer.py` | UNREFERENCED | - |
| `multiverse\persistence\position_store.py` | UNREFERENCED | - |
| `multiverse\persistence\state_restorer.py` | UNREFERENCED | - |
| `multiverse\runner\__init__.py` | UNREFERENCED | - |
| `multiverse\runner\dsr.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\objective.py |
| `multiverse\runner\grid_runner.py` | UNREFERENCED | - |
| `multiverse\runner\report.py` | UNREFERENCED | - |
| `multiverse\runner\smoke.py` | UNREFERENCED | - |
| `multiverse\tests\__init__.py` | UNREFERENCED | - |
| `multiverse\tests\conftest.py` | UNREFERENCED | - |
| `multiverse\tests\test_composable.py` | UNREFERENCED | - |
| `multiverse\tests\test_corp_events.py` | UNREFERENCED | - |
| `multiverse\tests\test_data_coverage.py` | UNREFERENCED | - |
| `multiverse\tests\test_data_quality.py` | UNREFERENCED | - |
| `multiverse\tests\test_dsr.py` | UNREFERENCED | - |
| `multiverse\tests\test_grid_expansion.py` | UNREFERENCED | - |
| `multiverse\tests\test_grid_runner.py` | UNREFERENCED | - |
| `multiverse\tests\test_kospi200_pit.py` | UNREFERENCED | - |
| `multiverse\tests\test_metrics.py` | UNREFERENCED | - |
| `multiverse\tests\test_paramset_store.py` | UNREFERENCED | - |
| `multiverse\tests\test_personas.py` | UNREFERENCED | - |
| `multiverse\tests\test_pit_engine.py` | UNREFERENCED | - |
| `multiverse\tests\test_pit_guard.py` | UNREFERENCED | - |
| `multiverse\tests\test_portfolio_engine.py` | UNREFERENCED | - |
| `multiverse\tests\test_portfolio_metrics.py` | UNREFERENCED | - |
| `multiverse\tests\test_position_store.py` | UNREFERENCED | - |
| `multiverse\tests\test_smoke.py` | UNREFERENCED | - |
| `multiverse\tests\test_spike_features.py` | UNREFERENCED | - |
| `multiverse\tests\test_spike_label.py` | UNREFERENCED | - |
| `multiverse\tests\test_state_restorer.py` | UNREFERENCED | - |
| `multiverse\tests\test_trend_starter_exit.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\_test_dataload.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\_v3_report_only.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\_v3_write_reports.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\check_no_lookahead.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p0_apply_adj_factor.py` | TEST-ONLY | TEST:tests\collectors\test_adj_factors.py |
| `scripts\10pct_strategy\p0_regime_label.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p1_forward_return_matrix.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p2a_universe_filter.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p2b_signal_multiverse.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p2c_exit_grid.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p3_portfolio_walkforward.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_cmf_walkforward.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_ma_align_walkforward.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_nhb_optimization.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_obv_swing_walkforward.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_obv_walkforward.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_roe_walkforward.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_stage_rerun.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_stage_rerun_v2.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_tom_walkforward.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_vwap_daily_cache.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_vwap_walkforward.py` | UNREFERENCED | - |
| `scripts\__init__.py` | UNREFERENCED | - |
| `scripts\_analyze_phase2_filters.py` | UNREFERENCED | - |
| `scripts\_build_phase2_summary.py` | UNREFERENCED | - |
| `scripts\_check_ks11.py` | UNREFERENCED | - |
| `scripts\_check_parquet_cols.py` | UNREFERENCED | - |
| `scripts\_check_phase4.py` | UNREFERENCED | - |
| `scripts\_phase1_pilot.py` | UNREFERENCED | - |
| `scripts\_run_elder_mkt_rs_sweep.py` | UNREFERENCED | - |
| `scripts\_run_phase2_filters.py` | UNREFERENCED | - |
| `scripts\_run_phase2_gaps.py` | UNREFERENCED | - |
| `scripts\analyze_anti_regime.py` | UNREFERENCED | - |
| `scripts\analyze_fade_vwap_regime.py` | UNREFERENCED | - |
| `scripts\analyze_intraday_5pct_spikes.py` | UNREFERENCED | - |
| `scripts\analyze_morning_5pct_spikes.py` | UNREFERENCED | - |
| `scripts\analyze_sideways_subdivision.py` | UNREFERENCED | - |
| `scripts\analyze_tick_trace.py` | UNREFERENCED | - |
| `scripts\analyze_trend_starter_poc.py` | UNREFERENCED | - |
| `scripts\backfill_corp_events.py` | UNREFERENCED | - |
| `scripts\backfill_daily_prices_fundamental.py` | UNREFERENCED | - |
| `scripts\backfill_foreign_flow.py` | UNREFERENCED | - |
| `scripts\backfill_kospi_index.py` | UNREFERENCED | - |
| `scripts\backfill_operating_cash_flow.py` | UNREFERENCED | - |
| `scripts\backfill_vkospi.py` | TEST-ONLY | TEST:tests\test_phase5_vkospi.py |
| `scripts\book_param_multiverse.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\discovery\sizing_scenarios.py; RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\portfolio_sim_elder.py |
| `scripts\book_portfolio_multiverse.py` | RESEARCH | RESEARCH:scripts\discovery\live_strategy_signals.py; RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\rs_leader_validation.py; RESEARCH:scripts\strategy_gate.py |
| `scripts\book_rebalance_multiverse.py` | UNREFERENCED | - |
| `scripts\build_intraday_universe.py` | UNREFERENCED | - |
| `scripts\canslim_backtest.py` | UNREFERENCED | - |
| `scripts\canslim_pattern_backtest.py` | UNREFERENCED | - |
| `scripts\canslim_screener.py` | UNREFERENCED | - |
| `scripts\check_kospi_minute_source.py` | UNREFERENCED | - |
| `scripts\debug_grid_njobs2.py` | UNREFERENCED | - |
| `scripts\debug_grid_njobs8.py` | UNREFERENCED | - |
| `scripts\debug_has_adj.py` | UNREFERENCED | - |
| `scripts\debug_has_adj2.py` | UNREFERENCED | - |
| `scripts\debug_single_cell.py` | UNREFERENCED | - |
| `scripts\diag_trail_ab.py` | UNREFERENCED | - |
| `scripts\discovery\__init__.py` | UNREFERENCED | - |
| `scripts\discovery\dynamic_risk.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\discovery\exit_adapters.py; RESEARCH:scripts\exit_multiverse\portfolio_sim.py; TEST:tests\discovery\test_dynamic_risk.py |
| `scripts\discovery\entry_sim_day.py` | UNREFERENCED | - |
| `scripts\discovery\exit_adapters.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\discovery\test_dynamic_rr_exit_injection.py; TEST:tests\test_discovery.py |
| `scripts\discovery\live_strategy_signals.py` | RESEARCH | RESEARCH:scripts\discovery\entry_sim_day.py; RESEARCH:scripts\dynamic_rr_multiverse.py; TEST:tests\discovery\test_live_strategy_signals.py |
| `scripts\discovery\reference_values.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\portfolio_sim.py; TEST:tests\discovery\test_reference_values.py |
| `scripts\discovery\rules.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\test_discovery.py |
| `scripts\discovery\sizing_scenarios.py` | TEST-ONLY | TEST:tests\test_discovery.py |
| `scripts\dynamic_rr_multiverse.py` | TEST-ONLY | TEST:tests\discovery\test_dynamic_rr_gate.py; TEST:tests\discovery\test_dynamic_rr_runner.py; TEST:tests\discovery\test_dynamic_rr_smoke.py |
| `scripts\entry_filters.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\multiverse3_real_exit.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\portfolio_sim_elder.py; RESEARCH:scripts\rs_leader_validation.py |
| `scripts\etl_backfill_daily_prices.py` | TEST-ONLY | TEST:tests\collectors\test_daily_derived.py |
| `scripts\exit_multiverse\__init__.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\adapters.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\data_loader.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\exits.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\objective.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\portfolio_sim.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\discovery\sizing_scenarios.py; RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\multiverse3_real_exit.py; RESEARCH:scripts\multiverse4_returns_export.py |
| `scripts\exit_multiverse\report.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\run.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\run_all.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\signals.py` | TEST-ONLY | TEST:tests\regime\test_multiverse3_real_exit.py |
| `scripts\exit_multiverse\walkforward.py` | UNREFERENCED | - |
| `scripts\extract_spike_precursors.py` | UNREFERENCED | - |
| `scripts\feature_edge\__init__.py` | UNREFERENCED | - |
| `scripts\feature_edge\config.py` | UNREFERENCED | - |
| `scripts\feature_edge\event_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\panel.py; TEST:tests\feature_edge\test_event_features.py |
| `scripts\feature_edge\flow_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\panel.py; TEST:tests\feature_edge\test_flow_features.py |
| `scripts\feature_edge\labelers.py` | RESEARCH | RESEARCH:scripts\feature_edge\portfolio_backtest.py; RESEARCH:scripts\feature_edge\run_edge_lab.py; TEST:tests\feature_edge\test_labelers.py |
| `scripts\feature_edge\loaders.py` | UNREFERENCED | - |
| `scripts\feature_edge\market_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\panel.py; TEST:tests\feature_edge\test_market_features.py |
| `scripts\feature_edge\metrics.py` | RESEARCH | RESEARCH:scripts\feature_edge\run_edge_lab.py; TEST:tests\feature_edge\test_metrics.py |
| `scripts\feature_edge\panel.py` | RESEARCH | RESEARCH:scripts\feature_edge\run_edge_lab.py; TEST:tests\feature_edge\test_panel.py |
| `scripts\feature_edge\portfolio_backtest.py` | TEST-ONLY | TEST:tests\feature_edge\test_portfolio_backtest.py |
| `scripts\feature_edge\price_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\panel.py; RESEARCH:scripts\feature_edge\portfolio_backtest.py; TEST:tests\feature_edge\test_price_features.py |
| `scripts\feature_edge\run_edge_lab.py` | TEST-ONLY | TEST:tests\feature_edge\test_run_edge_lab.py |
| `scripts\feature_edge\signals.py` | TEST-ONLY | TEST:tests\feature_edge\test_signals.py |
| `scripts\feature_edge\timing\__init__.py` | UNREFERENCED | - |
| `scripts\feature_edge\timing\buy_rules.py` | TEST-ONLY | TEST:tests\feature_edge\timing\test_buy_rules.py |
| `scripts\feature_edge\timing\config.py` | UNREFERENCED | - |
| `scripts\feature_edge\timing\cost_validation.py` | TEST-ONLY | TEST:tests\feature_edge\timing\test_cost_validation.py |
| `scripts\feature_edge\timing\intraday_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\buy_rules.py; RESEARCH:scripts\feature_edge\timing\sell_rules.py; TEST:tests\feature_edge\timing\test_intraday_features.py |
| `scripts\feature_edge\timing\intraday_loader.py` | UNREFERENCED | - |
| `scripts\feature_edge\timing\run_timing_lab.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\cost_validation.py; TEST:tests\feature_edge\timing\test_run_timing_lab.py |
| `scripts\feature_edge\timing\sell_rules.py` | TEST-ONLY | TEST:tests\feature_edge\timing\test_sell_rules.py |
| `scripts\feature_edge\timing\timing_metrics.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\timing\test_timing_metrics.py |
| `scripts\feature_edge\timing\trade_sim.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\cost_validation.py; RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\timing\test_trade_sim.py |
| `scripts\fix_079650_fictional_fill.py` | UNREFERENCED | - |
| `scripts\kis_db\__init__.py` | UNREFERENCED | - |
| `scripts\kis_db\create_database.py` | TEST-ONLY | TEST:tests\kis_db\test_create_database.py |
| `scripts\kis_db\schema.py` | TEST-ONLY | TEST:tests\kis_db\test_schema.py |
| `scripts\kis_db\seed_from_legacy.py` | TEST-ONLY | TEST:tests\kis_db\test_seed_from_legacy.py |
| `scripts\lynch_kis_sim.py` | UNREFERENCED | - |
| `scripts\lynch_multiverse_kis.py` | UNREFERENCED | - |
| `scripts\multiverse3_real_exit.py` | TEST-ONLY | TEST:tests\regime\test_multiverse3_real_exit.py |
| `scripts\multiverse4_portfolio_analysis.py` | RESEARCH | RESEARCH:scripts\discovery\sizing_scenarios.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\test_multiverse4.py |
| `scripts\multiverse4_returns_export.py` | RESEARCH | RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\step2_universe_rebaseline.py; RESEARCH:scripts\step3_pit_rebaseline.py; RESEARCH:scripts\step3c_size_sector_filter.py; RESEARCH:scripts\step3d_backfill_5p5yr.py |
| `scripts\phase1_forward_return_baseline.py` | UNREFERENCED | - |
| `scripts\portfolio_sim_elder.py` | RESEARCH | RESEARCH:scripts\_run_elder_mkt_rs_sweep.py; TEST:tests\regime\test_portfolio_sim_elder_mkt_rs.py |
| `scripts\preflight_strategy_validate.py` | TEST-ONLY | TEST:tests\test_preflight.py |
| `scripts\regime_split_dino_surge.py` | UNREFERENCED | - |
| `scripts\regime_split_elder_minervini.py` | UNREFERENCED | - |
| `scripts\regime_split_minervini.py` | UNREFERENCED | - |
| `scripts\regime_split_moonbyungro.py` | UNREFERENCED | - |
| `scripts\regime_split_trading_legends.py` | UNREFERENCED | - |
| `scripts\regime_split_weinstein.py` | UNREFERENCED | - |
| `scripts\rs_leader\__init__.py` | UNREFERENCED | - |
| `scripts\rs_leader\decompose.py` | RESEARCH | RESEARCH:scripts\rs_leader_validation.py; TEST:tests\rs_leader\test_decompose.py |
| `scripts\rs_leader\exit_adapter.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\rs_leader_validation.py; TEST:tests\rs_leader\test_exit_adapter.py |
| `scripts\rs_leader_validation.py` | UNREFERENCED | - |
| `scripts\run_books_research.py` | UNREFERENCED | - |
| `scripts\run_daytrading_3methods.py` | UNREFERENCED | - |
| `scripts\run_dino_surge.py` | TEST-ONLY | TEST:tests\books\test_dino_surge_daily.py |
| `scripts\run_elder_triple_screen.py` | UNREFERENCED | - |
| `scripts\run_greenblatt_magic.py` | UNREFERENCED | - |
| `scripts\run_haru_silijeon_daily.py` | TEST-ONLY | TEST:tests\books\test_haru_silijeon_daily.py |
| `scripts\run_haru_silijeon_minute.py` | UNREFERENCED | - |
| `scripts\run_hongyongchan.py` | TEST-ONLY | TEST:tests\books\test_hongyongchan_rules.py |
| `scripts\run_intraday_tournament.py` | TEST-ONLY | TEST:tests\test_intraday_universe.py |
| `scripts\run_lynch_one_up.py` | UNREFERENCED | - |
| `scripts\run_minervini_vcp.py` | TEST-ONLY | TEST:tests\exit_multiverse\test_equivalence.py |
| `scripts\run_moonbyungro_metric.py` | TEST-ONLY | TEST:tests\books\test_moonbyungro_rules.py |
| `scripts\run_multiverse_grid.py` | UNREFERENCED | - |
| `scripts\run_oshaughnessy_value.py` | UNREFERENCED | - |
| `scripts\run_raschke_daily.py` | UNREFERENCED | - |
| `scripts\run_screener.py` | UNREFERENCED | - |
| `scripts\run_spike_precursor_poc.py` | UNREFERENCED | - |
| `scripts\run_surge_fade_minute.py` | UNREFERENCED | - |
| `scripts\run_systrader79.py` | UNREFERENCED | - |
| `scripts\run_trading_legends_daily.py` | TEST-ONLY | TEST:tests\books\test_trading_legends_daily.py |
| `scripts\run_trend_starter_poc.py` | UNREFERENCED | - |
| `scripts\run_weinstein_stages.py` | UNREFERENCED | - |
| `scripts\sawkami_simulation.py` | UNREFERENCED | - |
| `scripts\signal_combo_phase1.py` | UNREFERENCED | - |
| `scripts\signal_combo_phase1_relabel.py` | UNREFERENCED | - |
| `scripts\signal_combo_phase1_relabel_v2.py` | UNREFERENCED | - |
| `scripts\signal_combo_phase2_exit_grid.py` | UNREFERENCED | - |
| `scripts\signal_combo_phase3_entry_compare.py` | UNREFERENCED | - |
| `scripts\signal_combo_phase4_swing.py` | UNREFERENCED | - |
| `scripts\simulate_pair.py` | UNREFERENCED | - |
| `scripts\stage1_analyze.py` | UNREFERENCED | - |
| `scripts\stage3_recommend.py` | UNREFERENCED | - |
| `scripts\step2_universe_rebaseline.py` | RESEARCH | RESEARCH:scripts\step3_pit_rebaseline.py; RESEARCH:scripts\step3c_size_sector_filter.py; RESEARCH:scripts\step3d_backfill_5p5yr.py |
| `scripts\step3_pit_rebaseline.py` | UNREFERENCED | - |
| `scripts\step3c_size_sector_filter.py` | RESEARCH | RESEARCH:scripts\step3d_backfill_5p5yr.py |
| `scripts\step3d_backfill_5p5yr.py` | UNREFERENCED | - |
| `scripts\stock_screener.py` | RESEARCH | RESEARCH:scripts\run_screener.py; TEST:tests\test_stock_screener.py |
| `scripts\strategy_gate.py` | RESEARCH | RESEARCH:scripts\discovery\sizing_scenarios.py; TEST:tests\test_discovery.py |
| `scripts\sweep_anti.py` | UNREFERENCED | - |
| `scripts\sweep_fade_vwap.py` | UNREFERENCED | - |
| `scripts\test_fdr_foreign.py` | UNREFERENCED | - |
| `scripts\test_krx_direct.py` | UNREFERENCED | - |
| `scripts\test_krx_session.py` | UNREFERENCED | - |
| `scripts\test_naver_foreign.py` | UNREFERENCED | - |
| `scripts\test_naver_foreign2.py` | UNREFERENCED | - |
| `scripts\test_naver_poc.py` | UNREFERENCED | - |
| `scripts\test_pykrx.py` | UNREFERENCED | - |
| `scripts\test_pykrx2.py` | UNREFERENCED | - |
| `scripts\test_pykrx3.py` | UNREFERENCED | - |
| `scripts\test_pykrx4.py` | UNREFERENCED | - |
| `scripts\test_pykrx5.py` | UNREFERENCED | - |
| `scripts\walkforward_envelope.py` | UNREFERENCED | - |
