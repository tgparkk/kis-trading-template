# INVENTORY — 연구 파일 참조 태깅 (tools/gen_inventory.py 생성)

| 파일 | 태그 | 참조자 |
|---|---|---|
| `backtest\__init__.py` | UNREFERENCED | - |
| `backtest\allocation_backtester.py` | TEST-ONLY | TEST:tests\allocation\test_systrader79_avgmom.py |
| `backtest\book_backtester.py` | RESEARCH | RESEARCH:scripts\book_param_multiverse.py; RESEARCH:scripts\run_books_research.py; RESEARCH:scripts\run_daytrading_3methods.py; RESEARCH:scripts\run_dino_surge.py; RESEARCH:scripts\run_elder_triple_screen.py |
| `backtest\data_completeness.py` | RESEARCH | RESEARCH:scripts\step3c_size_sector_filter.py; TEST:tests\test_data_completeness.py |
| `backtest\engine.py` | RESEARCH | RESEARCH:backtest\__init__.py; RESEARCH:backtest\multiverse.py; RESEARCH:backtest\regime_analysis.py; RESEARCH:scripts\run_intraday_tournament.py; TEST:tests\test_backtest_engine.py |
| `backtest\engine_minute.py` | RESEARCH | RESEARCH:backtest\engine.py |
| `backtest\metrics.py` | RESEARCH | RESEARCH:backtest\engine.py |
| `backtest\multiverse.py` | RESEARCH | RESEARCH:backtest\__init__.py; RESEARCH:scripts\param_optimizer.py; RESEARCH:scripts\run_buy_filter_grid.py; TEST:tests\test_multiverse.py |
| `backtest\regime_analysis.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\objective.py; RESEARCH:scripts\exit_multiverse\run.py; RESEARCH:scripts\regime_split_elder_minervini.py; TEST:tests\exit_multiverse\test_objective.py; TEST:tests\test_regime_analysis.py |
| `backtest\result.py` | RESEARCH | RESEARCH:backtest\engine.py; RESEARCH:backtest\engine_minute.py |
| `backtest\screener_universe.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\step2_universe_rebaseline.py; RESEARCH:scripts\step3_pit_rebaseline.py; RESEARCH:scripts\step3c_size_sector_filter.py; TEST:tests\test_pit_gating.py |
| `backtest\tournament_metrics.py` | RESEARCH | RESEARCH:scripts\run_intraday_tournament.py; TEST:tests\test_tournament_metrics.py |
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
| `scripts\10pct_strategy\check_no_lookahead.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p0_apply_adj_factor.py` | TEST-ONLY | TEST:tests\collectors\test_adj_factors.py |
| `scripts\10pct_strategy\p2b_signal_multiverse.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p2c_exit_grid.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_obv_swing_walkforward.py` | UNREFERENCED | - |
| `scripts\10pct_strategy\p5_stage_rerun.py` | UNREFERENCED | - |
| `scripts\__init__.py` | UNREFERENCED | - |
| `scripts\_analyze_phase2_filters.py` | UNREFERENCED | - |
| `scripts\analyze_tick_trace.py` | UNREFERENCED | - |
| `scripts\backfill_corp_events.py` | UNREFERENCED | - |
| `scripts\backfill_daily_prices_fundamental.py` | UNREFERENCED | - |
| `scripts\backfill_foreign_flow.py` | UNREFERENCED | - |
| `scripts\backfill_kospi_index.py` | UNREFERENCED | - |
| `scripts\backfill_operating_cash_flow.py` | UNREFERENCED | - |
| `scripts\backfill_vkospi.py` | TEST-ONLY | TEST:tests\test_phase5_vkospi.py |
| `scripts\book_param_multiverse.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\discovery\sizing_scenarios.py; RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\portfolio_sim_elder.py |
| `scripts\book_portfolio_multiverse.py` | RESEARCH | RESEARCH:scripts\discovery\live_strategy_signals.py; RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\strategy_gate.py; RESEARCH:scripts\walkforward_envelope.py |
| `scripts\discovery\__init__.py` | UNREFERENCED | - |
| `scripts\discovery\dynamic_risk.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\discovery\exit_adapters.py; RESEARCH:scripts\exit_multiverse\portfolio_sim.py; TEST:tests\discovery\test_dynamic_risk.py |
| `scripts\discovery\exit_adapters.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\discovery\test_dynamic_rr_exit_injection.py; TEST:tests\test_discovery.py |
| `scripts\discovery\live_strategy_signals.py` | RESEARCH | RESEARCH:scripts\dynamic_rr_multiverse.py; TEST:tests\discovery\test_live_strategy_signals.py |
| `scripts\discovery\reference_values.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\portfolio_sim.py; TEST:tests\discovery\test_reference_values.py |
| `scripts\discovery\rules.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\test_discovery.py |
| `scripts\discovery\sizing_scenarios.py` | TEST-ONLY | TEST:tests\test_discovery.py |
| `scripts\dynamic_rr_multiverse.py` | TEST-ONLY | TEST:tests\discovery\test_dynamic_rr_gate.py; TEST:tests\discovery\test_dynamic_rr_runner.py; TEST:tests\discovery\test_dynamic_rr_smoke.py |
| `scripts\entry_filters.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\multiverse3_real_exit.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\portfolio_sim_elder.py; TEST:tests\regime\test_entry_filters_no_lookahead.py |
| `scripts\etl_backfill_daily_prices.py` | TEST-ONLY | TEST:tests\collectors\test_daily_derived.py |
| `scripts\exit_multiverse\__init__.py` | UNREFERENCED | - |
| `scripts\exit_multiverse\adapters.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\run.py; RESEARCH:scripts\exit_multiverse\run_all.py; RESEARCH:scripts\multiverse3_real_exit.py; RESEARCH:scripts\multiverse4_returns_export.py; TEST:tests\exit_multiverse\test_adapters.py |
| `scripts\exit_multiverse\data_loader.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\run.py; RESEARCH:scripts\multiverse3_real_exit.py; TEST:tests\exit_multiverse\test_data_loader.py; TEST:tests\exit_multiverse\test_equivalence.py |
| `scripts\exit_multiverse\exits.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\adapters.py; TEST:tests\exit_multiverse\test_exits.py |
| `scripts\exit_multiverse\objective.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\walkforward.py; TEST:tests\exit_multiverse\test_objective.py |
| `scripts\exit_multiverse\portfolio_sim.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\discovery\sizing_scenarios.py; RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\exit_multiverse\walkforward.py; RESEARCH:scripts\multiverse3_real_exit.py |
| `scripts\exit_multiverse\report.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\run.py; TEST:tests\exit_multiverse\test_report.py |
| `scripts\exit_multiverse\run.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\run_all.py; TEST:tests\exit_multiverse\test_run_smoke.py |
| `scripts\exit_multiverse\run_all.py` | TEST-ONLY | TEST:tests\exit_multiverse\test_run_all.py |
| `scripts\exit_multiverse\signals.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\run.py; RESEARCH:scripts\multiverse3_real_exit.py; RESEARCH:scripts\multiverse4_returns_export.py; TEST:tests\exit_multiverse\test_equivalence.py; TEST:tests\exit_multiverse\test_signals.py |
| `scripts\exit_multiverse\walkforward.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\run.py; TEST:tests\exit_multiverse\test_walkforward.py |
| `scripts\feature_edge\__init__.py` | UNREFERENCED | - |
| `scripts\feature_edge\config.py` | RESEARCH | RESEARCH:scripts\feature_edge\loaders.py; RESEARCH:scripts\feature_edge\portfolio_backtest.py; RESEARCH:scripts\feature_edge\run_edge_lab.py; TEST:tests\feature_edge\test_config.py |
| `scripts\feature_edge\event_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\panel.py; TEST:tests\feature_edge\test_event_features.py |
| `scripts\feature_edge\flow_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\panel.py; TEST:tests\feature_edge\test_flow_features.py |
| `scripts\feature_edge\labelers.py` | RESEARCH | RESEARCH:scripts\feature_edge\portfolio_backtest.py; RESEARCH:scripts\feature_edge\run_edge_lab.py; TEST:tests\feature_edge\test_labelers.py |
| `scripts\feature_edge\loaders.py` | RESEARCH | RESEARCH:scripts\feature_edge\portfolio_backtest.py; RESEARCH:scripts\feature_edge\run_edge_lab.py; RESEARCH:scripts\feature_edge\timing\cost_validation.py; RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\test_loaders.py |
| `scripts\feature_edge\market_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\panel.py; TEST:tests\feature_edge\test_market_features.py |
| `scripts\feature_edge\metrics.py` | RESEARCH | RESEARCH:scripts\feature_edge\run_edge_lab.py; TEST:tests\feature_edge\test_metrics.py |
| `scripts\feature_edge\panel.py` | RESEARCH | RESEARCH:scripts\feature_edge\run_edge_lab.py; TEST:tests\feature_edge\test_panel.py |
| `scripts\feature_edge\portfolio_backtest.py` | TEST-ONLY | TEST:tests\feature_edge\test_portfolio_backtest.py |
| `scripts\feature_edge\price_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\panel.py; RESEARCH:scripts\feature_edge\portfolio_backtest.py; TEST:tests\feature_edge\test_price_features.py |
| `scripts\feature_edge\run_edge_lab.py` | TEST-ONLY | TEST:tests\feature_edge\test_run_edge_lab.py |
| `scripts\feature_edge\signals.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\cost_validation.py; RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\test_signals.py |
| `scripts\feature_edge\timing\__init__.py` | UNREFERENCED | - |
| `scripts\feature_edge\timing\buy_rules.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\cost_validation.py; RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\timing\test_buy_rules.py |
| `scripts\feature_edge\timing\config.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\cost_validation.py; RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\timing\test_config.py |
| `scripts\feature_edge\timing\cost_validation.py` | TEST-ONLY | TEST:tests\feature_edge\timing\test_cost_validation.py |
| `scripts\feature_edge\timing\intraday_features.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\buy_rules.py; RESEARCH:scripts\feature_edge\timing\sell_rules.py; TEST:tests\feature_edge\timing\test_intraday_features.py |
| `scripts\feature_edge\timing\intraday_loader.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\cost_validation.py; RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\timing\test_intraday_loader.py |
| `scripts\feature_edge\timing\run_timing_lab.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\cost_validation.py; TEST:tests\feature_edge\timing\test_run_timing_lab.py |
| `scripts\feature_edge\timing\sell_rules.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\timing\test_sell_rules.py |
| `scripts\feature_edge\timing\timing_metrics.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\timing\test_timing_metrics.py |
| `scripts\feature_edge\timing\trade_sim.py` | RESEARCH | RESEARCH:scripts\feature_edge\timing\cost_validation.py; RESEARCH:scripts\feature_edge\timing\run_timing_lab.py; TEST:tests\feature_edge\timing\test_trade_sim.py |
| `scripts\kis_db\__init__.py` | UNREFERENCED | - |
| `scripts\kis_db\create_database.py` | TEST-ONLY | TEST:tests\kis_db\test_create_database.py |
| `scripts\kis_db\schema.py` | TEST-ONLY | TEST:tests\kis_db\test_schema.py |
| `scripts\kis_db\seed_from_legacy.py` | TEST-ONLY | TEST:tests\kis_db\test_seed_from_legacy.py |
| `scripts\multiverse3_real_exit.py` | TEST-ONLY | TEST:tests\regime\test_multiverse3_real_exit.py |
| `scripts\multiverse4_portfolio_analysis.py` | RESEARCH | RESEARCH:scripts\discovery\sizing_scenarios.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\test_multiverse4.py |
| `scripts\multiverse4_returns_export.py` | RESEARCH | RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\step2_universe_rebaseline.py; RESEARCH:scripts\step3_pit_rebaseline.py; RESEARCH:scripts\step3c_size_sector_filter.py; RESEARCH:scripts\strategy_gate.py |
| `scripts\param_optimizer.py` | UNREFERENCED | - |
| `scripts\portfolio_sim_elder.py` | TEST-ONLY | TEST:tests\regime\test_portfolio_sim_elder_mkt_rs.py |
| `scripts\preflight_strategy_validate.py` | TEST-ONLY | TEST:tests\test_preflight.py |
| `scripts\regime_split_elder_minervini.py` | UNREFERENCED | - |
| `scripts\regime_split_minervini.py` | UNREFERENCED | - |
| `scripts\regime_split_weinstein.py` | UNREFERENCED | - |
| `scripts\rs_leader\__init__.py` | UNREFERENCED | - |
| `scripts\rs_leader\decompose.py` | TEST-ONLY | TEST:tests\rs_leader\test_decompose.py |
| `scripts\rs_leader\exit_adapter.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; TEST:tests\rs_leader\test_exit_adapter.py |
| `scripts\run_books_research.py` | UNREFERENCED | - |
| `scripts\run_buy_filter_grid.py` | UNREFERENCED | - |
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
| `scripts\run_screener.py` | UNREFERENCED | - |
| `scripts\run_spike_precursor_poc.py` | UNREFERENCED | - |
| `scripts\run_trading_legends_daily.py` | TEST-ONLY | TEST:tests\books\test_trading_legends_daily.py |
| `scripts\run_weinstein_stages.py` | UNREFERENCED | - |
| `scripts\signal_combo_phase1.py` | UNREFERENCED | - |
| `scripts\signal_combo_phase1_relabel.py` | UNREFERENCED | - |
| `scripts\stage1_analyze.py` | UNREFERENCED | - |
| `scripts\stage3_recommend.py` | UNREFERENCED | - |
| `scripts\step2_universe_rebaseline.py` | RESEARCH | RESEARCH:scripts\step3_pit_rebaseline.py; RESEARCH:scripts\step3c_size_sector_filter.py |
| `scripts\step3_pit_rebaseline.py` | UNREFERENCED | - |
| `scripts\step3c_size_sector_filter.py` | UNREFERENCED | - |
| `scripts\stock_screener.py` | RESEARCH | RESEARCH:scripts\run_screener.py; TEST:tests\test_stock_screener.py |
| `scripts\strategy_gate.py` | RESEARCH | RESEARCH:scripts\discovery\sizing_scenarios.py; TEST:tests\test_discovery.py |
| `scripts\walkforward_envelope.py` | UNREFERENCED | - |
