> 생성 2026-09-17 · 기준 커밋 `16a8106` · Python 3.9.13 · 결과 436행(LIVE-DEP 1 · RESEARCH 58 · TEST-ONLY 45 · UNREFERENCED 332). 아래 표는 `tools/gen_inventory.py` 출력 그대로이며 이 머리말 3줄만 수기.
> 재생성(🔴 **워크트리에서** — 라이브 트리 금지): `cd RoboTrader_template && PYTHONUTF8=1 python -B tools/gen_inventory.py > ../_inventory_tmp.md && sed -i 's/\r$//' ../_inventory_tmp.md && { head -4 docs/INVENTORY.md; cat ../_inventory_tmp.md; } > ../_inventory_new.md && mv ../_inventory_new.md docs/INVENTORY.md` — 워크트리엔 `venv/` 가 없으므로(`.gitignore` `venv/` · 미추적) `venv/Scripts/python` 이 아니라 **시스템 Python 3.9.13**(도구는 표준 라이브러리 `ast`·`os` 만 사용 · 2026-09-17 워크트리 실측 본문 diff 0) 또는 라이브 트리 venv 인터프리터의 절대경로를 쓰되 cwd 는 워크트리. 🔴 `> docs/INVENTORY.md` 로 바로 리다이렉트하지 말 것(cp949 콘솔에서 `—` 인코딩 실패 시 쉘이 파일을 먼저 0바이트로 비운다). `PYTHONUTF8=1` 필수. 🔴 Windows Python 은 리다이렉트 시 CRLF 로 쓴다(2026-09-17 실측) — `sed` 로 LF 통일(HEAD 는 LF) · 머리말 3줄+빈 줄은 수기라 `head -4` 로 되붙인다(빠뜨리면 사라짐).
> 도구 주의: `gen_inventory.py` 의 PROD_DIRS 는 `lib/` 를 운영으로 센다(CLAUDE.md·docs/CODE_MAP.md 는 2026-07-10 부터 연구 분류). 도구는 코드라 이번 문서 정리에서 손대지 않음 — `lib/` 가 연구 파일을 import 하면 LIVE-DEP 로 «과대» 표기될 수 있다(2026-09-17 현재 해당 없음).

# INVENTORY — 연구 파일 참조 태깅 (tools/gen_inventory.py 생성)

| 파일 | 태그 | 참조자 |
|---|---|---|
| `backtest\__init__.py` | UNREFERENCED | - |
| `backtest\allocation_backtester.py` | TEST-ONLY | TEST:tests\allocation\test_systrader79_avgmom.py |
| `backtest\book_backtester.py` | RESEARCH | RESEARCH:backtest\concept_axes\ma5\run.py; RESEARCH:backtest\concept_axes\ma5_exit\run.py; RESEARCH:backtest\concept_axes\minervini\run.py; RESEARCH:backtest\live_universe_revalidation\run.py; RESEARCH:backtest\rank_score_counterfactual\run.py |
| `backtest\concept_axes\ma5\run.py` | UNREFERENCED | - |
| `backtest\concept_axes\ma5_exit\run.py` | UNREFERENCED | - |
| `backtest\concept_axes\minervini\run.py` | TEST-ONLY | TEST:tests\test_concept_axes_breakout.py; TEST:tests\test_concept_axes_doc1_pin.py |
| `backtest\concept_axes\minervini\tt_counterfactual\run_ledger.py` | UNREFERENCED | - |
| `backtest\concept_axes\minervini\verify_live_wiring.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\__init__.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\flags.py` | RESEARCH | RESEARCH:backtest\concept_axes\replayer\ledger.py; RESEARCH:backtest\concept_axes\replayer\run.py; RESEARCH:backtest\concept_axes\replayer\tests\test_flag_cliff_sql_parity.py; RESEARCH:backtest\concept_axes\replayer\tests\test_flags.py; RESEARCH:backtest\concept_axes\replayer\tests\test_integration_one_day.py |
| `backtest\concept_axes\replayer\gate.py` | RESEARCH | RESEARCH:backtest\concept_axes\replayer\run.py; RESEARCH:backtest\concept_axes\replayer\tests\test_gate.py; RESEARCH:backtest\concept_axes\replayer\tests\test_integration_one_day.py |
| `backtest\concept_axes\replayer\ledger.py` | RESEARCH | RESEARCH:backtest\concept_axes\replayer\run.py; RESEARCH:backtest\concept_axes\replayer\tests\test_integration_one_day.py |
| `backtest\concept_axes\replayer\loader.py` | RESEARCH | RESEARCH:backtest\concept_axes\replayer\flags.py; RESEARCH:backtest\concept_axes\replayer\run.py; RESEARCH:backtest\concept_axes\replayer\scan.py; RESEARCH:backtest\concept_axes\replayer\tests\conftest.py; RESEARCH:backtest\concept_axes\replayer\tests\test_flag_cliff_sql_parity.py |
| `backtest\concept_axes\replayer\run.py` | RESEARCH | RESEARCH:backtest\concept_axes\replayer\tests\test_integration_one_day.py |
| `backtest\concept_axes\replayer\scan.py` | RESEARCH | RESEARCH:backtest\concept_axes\replayer\ledger.py; RESEARCH:backtest\concept_axes\replayer\run.py; RESEARCH:backtest\concept_axes\replayer\tests\test_integration_one_day.py; RESEARCH:backtest\concept_axes\replayer\tests\test_scan.py |
| `backtest\concept_axes\replayer\tests\__init__.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\tests\conftest.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\tests\test_flag_cliff_sql_parity.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\tests\test_flags.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\tests\test_gate.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\tests\test_integration_one_day.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\tests\test_loader.py` | UNREFERENCED | - |
| `backtest\concept_axes\replayer\tests\test_scan.py` | UNREFERENCED | - |
| `backtest\concept_fidelity_audit\backtest_vs_live.py` | UNREFERENCED | - |
| `backtest\concept_fidelity_audit\behavior.py` | UNREFERENCED | - |
| `backtest\concept_fidelity_audit\universe_gap.py` | UNREFERENCED | - |
| `backtest\crash_gate_counterfactual\extract_blocks.py` | UNREFERENCED | - |
| `backtest\crash_gate_counterfactual\run_counterfactual.py` | UNREFERENCED | - |
| `backtest\data_completeness.py` | RESEARCH | RESEARCH:scripts\step3c_size_sector_filter.py; TEST:tests\test_data_completeness.py |
| `backtest\engine.py` | RESEARCH | RESEARCH:backtest\__init__.py; RESEARCH:backtest\multiverse.py; RESEARCH:backtest\regime_analysis.py; RESEARCH:scripts\run_intraday_tournament.py; TEST:tests\test_backtest_engine.py |
| `backtest\engine_minute.py` | RESEARCH | RESEARCH:backtest\engine.py |
| `backtest\entry_quality_audit\run.py` | UNREFERENCED | - |
| `backtest\live_universe_revalidation\run.py` | UNREFERENCED | - |
| `backtest\metrics.py` | RESEARCH | RESEARCH:backtest\engine.py |
| `backtest\multiverse.py` | RESEARCH | RESEARCH:backtest\__init__.py; RESEARCH:scripts\param_optimizer.py; RESEARCH:scripts\run_buy_filter_grid.py; TEST:tests\test_multiverse.py |
| `backtest\pnl_decomposition\decompose.py` | UNREFERENCED | - |
| `backtest\rank_score_counterfactual\run.py` | UNREFERENCED | - |
| `backtest\regime_analysis.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\objective.py; RESEARCH:scripts\exit_multiverse\run.py; RESEARCH:scripts\regime_split_elder_minervini.py; TEST:tests\exit_multiverse\test_objective.py; TEST:tests\test_regime_analysis.py |
| `backtest\result.py` | RESEARCH | RESEARCH:backtest\engine.py; RESEARCH:backtest\engine_minute.py |
| `backtest\screener_universe.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\step2_universe_rebaseline.py; RESEARCH:scripts\step3_pit_rebaseline.py; RESEARCH:scripts\step3c_size_sector_filter.py; TEST:tests\test_pit_gating.py |
| `backtest\stop_path_minute\run_path.py` | UNREFERENCED | - |
| `backtest\stop_vol_fit_gate\run_gate.py` | UNREFERENCED | - |
| `backtest\stop_vol_fit_gate\run_results.py` | UNREFERENCED | - |
| `backtest\stoploss_counterfactual\run_stoploss.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\__init__.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\bands.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\calibrate.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\calibrate_run.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\control.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\control5.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\data.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\report5.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\run.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\run5.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\run6.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\run7.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\segments.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\sim.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\lab\stats.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\measure_peak_lag.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\rescore_local_rebound.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\rescore_surge_metric.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\smoke_run5.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\smoke_run6.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\smoke_run7.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_bands.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_calibrate.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_control5.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_data.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_labels.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_run6.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_run7.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_run_smoke.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_segments.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_sim.py` | UNREFERENCED | - |
| `backtest\tasso_entry_timing\tests\test_stats.py` | UNREFERENCED | - |
| `backtest\tasso_labels\band_discreteness.py` | UNREFERENCED | - |
| `backtest\tasso_labels\frozen_constants.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\aggregate_survivorship.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\analyze_posts.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\batch_cat2829.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\build_claims_cat2829.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\build_img_claims.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\build_journal_ledger.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\build_labels_v4.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\build_labels_v5.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\calc_table.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\calibrate_naver_index.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\cat2829_common.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\check_categories.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\claims_schema.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\classify_unmapped_v4.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\codename_census.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\decode_account_holding.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\diagnose_unmapped_prose.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\download_account_images_full.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\download_images_28_29.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\extract_anchor_text.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\extract_calc_images.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\extract_timing.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\fetch_all_calc.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\finalize_unmapped_v4.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\finalize_v3.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\harvest_bodies.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\harvest_cat28_29.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\harvest_cat28_29_full.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\harvest_early_journals.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\harvest_fallback.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\harvest_list.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\img_index_build.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\img_probe_sample.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\parse_bodies.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\parse_posts.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\parse_prose.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\parse_titles.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\probe_unmapped_v4.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\rebuild_labels_v3.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\reextract_cat2829.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\regime_markers.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\resolve_codes.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\resolve_codes_prose.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\resolve_codes_v4.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\s6_two_track.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\scan_rest.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\test_c_rate_by_year.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\universe_2015_feasibility.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_anchor_text.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_cat2829.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_coverage.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_img_claims.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_preset.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_prose_v5.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_rationale.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_recall.py` | UNREFERENCED | - |
| `backtest\tasso_labels\harvest\verify_recall_v4.py` | UNREFERENCED | - |
| `backtest\tasso_labels\power\step1_freeze_and_data.py` | UNREFERENCED | - |
| `backtest\tasso_labels\power\step2_power.py` | UNREFERENCED | - |
| `backtest\tasso_labels\power\step3_mde.py` | UNREFERENCED | - |
| `backtest\tasso_labels\power\step4_sensitivity.py` | UNREFERENCED | - |
| `backtest\tasso_labels\power\step5_summary.py` | UNREFERENCED | - |
| `backtest\tasso_labels\tests\test_cat2829_pipeline.py` | UNREFERENCED | - |
| `backtest\tasso_labels\tests\test_frozen_constants.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\backfill_fill_n.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\fetch_post.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\filter_curve.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\filter_selectivity.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\probe_minute_api.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\reconstruct_prices.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\regen_gate.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_anchor_redesign.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_conditional.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_conditional_wide.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_d1_oos.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_d1_oos_post5.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_d1_oos_post6.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_d1_oos_post7.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_exit_v2_post4.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_exit_v2_post5.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_exit_v2_post6.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_exit_v2_post7.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_flow_norm.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_gapfill.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_hdr.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_intraday_pick.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_ladder_tranche.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_ladder_tranche_post6.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_ladder_tranche_post7.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_leg_structure.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_minute_entry.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_minute_selltiming.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_q1_v2.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_ranking.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_reconstruct_post4.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_reconstruct_post4_exact.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_reconstruct_post5.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_reconstruct_post6.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_reconstruct_post7.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_regday_post5.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_regday_post6.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_regday_post7.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_s5_post7.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_s5_sidebyside.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_sector.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_selection.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_selection_flow.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_selection_post4.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_selection_post5.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_selection_post6.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_selection_post7.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_selection_robust.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_selltiming.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_tests.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_wrc_explore.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_wrc_post6.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\run_wrc_post7.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\solve_common_band.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post6_ladder.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post6_ledger.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post6_ranking.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post6_reconstruct.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post6_sector.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post6_wrc.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_anchor.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_exit.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_ladder.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_ledger.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_ranking.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_reconstruct.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_regday.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_s5.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\test_post7_selection.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\tests\test_post6_exit.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\tests\test_post6_regday.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\tests\test_regen_gate_args.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\tests\test_s5_fixes.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\universe_gap.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\verify_ledger.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\verify_ledger_post5.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\verify_ledger_post6.py` | UNREFERENCED | - |
| `backtest\tasso_program_journal\verify_ledger_post7.py` | UNREFERENCED | - |
| `backtest\tournament_metrics.py` | RESEARCH | RESEARCH:scripts\run_intraday_tournament.py; TEST:tests\test_tournament_metrics.py |
| `backtest\universe_lookahead_ladder\run.py` | UNREFERENCED | - |
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
| `multiverse\data\corp_events.py` | TEST-ONLY | TEST:tests\test_research_data_source.py |
| `multiverse\data\kospi200_pit.py` | UNREFERENCED | - |
| `multiverse\data\pit_reader.py` | TEST-ONLY | TEST:tests\test_research_data_source.py |
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
| `scripts\backfill_daily_for_codes.py` | UNREFERENCED | - |
| `scripts\backfill_daily_prices_fundamental.py` | UNREFERENCED | - |
| `scripts\backfill_foreign_flow.py` | UNREFERENCED | - |
| `scripts\backfill_kospi_index.py` | UNREFERENCED | - |
| `scripts\backfill_minute_for_codes.py` | UNREFERENCED | - |
| `scripts\backfill_operating_cash_flow.py` | UNREFERENCED | - |
| `scripts\backfill_vkospi.py` | TEST-ONLY | TEST:tests\test_phase5_vkospi.py |
| `scripts\book_param_multiverse.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\discovery\sizing_scenarios.py; RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\portfolio_sim_elder.py |
| `scripts\book_portfolio_multiverse.py` | RESEARCH | RESEARCH:scripts\discovery\live_strategy_signals.py; RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\strategy_gate.py; RESEARCH:scripts\walkforward_envelope.py |
| `scripts\dart_industry_c1_collect.py` | UNREFERENCED | - |
| `scripts\dart_industry_c2_load.py` | UNREFERENCED | - |
| `scripts\dart_industry_c3_report.py` | UNREFERENCED | - |
| `scripts\dart_mcap_a1_corpcode_map.py` | UNREFERENCED | - |
| `scripts\dart_mcap_a2_decompose.py` | UNREFERENCED | - |
| `scripts\dart_mcap_a2_validate.py` | UNREFERENCED | - |
| `scripts\dart_mcap_a2_variants.py` | UNREFERENCED | - |
| `scripts\dart_mcap_a3_stlm_gating.py` | UNREFERENCED | - |
| `scripts\dart_mcap_b1_collect.py` | UNREFERENCED | - |
| `scripts\dart_mcap_b2_compute.py` | UNREFERENCED | - |
| `scripts\dart_mcap_b3_split_guard.py` | UNREFERENCED | - |
| `scripts\dart_mcap_b4_load.py` | UNREFERENCED | - |
| `scripts\dart_mcap_common.py` | UNREFERENCED | - |
| `scripts\discovery\__init__.py` | UNREFERENCED | - |
| `scripts\discovery\dynamic_risk.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\discovery\exit_adapters.py; RESEARCH:scripts\exit_multiverse\portfolio_sim.py; TEST:tests\discovery\test_dynamic_risk.py |
| `scripts\discovery\exit_adapters.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\discovery\test_dynamic_rr_exit_injection.py; TEST:tests\test_discovery.py |
| `scripts\discovery\intraday_rebound\__init__.py` | UNREFERENCED | - |
| `scripts\discovery\intraday_rebound\asym_grid.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_asym_grid.py |
| `scripts\discovery\intraday_rebound\db.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_db_config.py |
| `scripts\discovery\intraday_rebound\features.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_features.py; TEST:tests\discovery\intraday_rebound\test_outcome_probe.py |
| `scripts\discovery\intraday_rebound\first_touch.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_first_touch.py |
| `scripts\discovery\intraday_rebound\labeler.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_labeler.py |
| `scripts\discovery\intraday_rebound\outcome_probe.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_outcome_probe.py |
| `scripts\discovery\intraday_rebound\ranking.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_ranking.py |
| `scripts\discovery\intraday_rebound\reproduce.py` | UNREFERENCED | - |
| `scripts\discovery\intraday_rebound\resample.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_resample.py |
| `scripts\discovery\intraday_rebound\shape_compare.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_shape_compare.py; TEST:tests\discovery\intraday_rebound\test_volume_probe.py |
| `scripts\discovery\intraday_rebound\shape_events.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_shape_events.py; TEST:tests\discovery\intraday_rebound\test_shape_samples.py; TEST:tests\discovery\intraday_rebound\test_volume_probe.py |
| `scripts\discovery\intraday_rebound\shape_samples.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_shape_samples.py |
| `scripts\discovery\intraday_rebound\stability_scan.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_stability_scan.py |
| `scripts\discovery\intraday_rebound\universe.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_universe.py |
| `scripts\discovery\intraday_rebound\volume_probe.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_volume_probe.py |
| `scripts\discovery\intraday_rebound\walkforward.py` | TEST-ONLY | TEST:tests\discovery\intraday_rebound\test_walkforward.py |
| `scripts\discovery\live_strategy_signals.py` | RESEARCH | RESEARCH:scripts\dynamic_rr_multiverse.py; TEST:tests\discovery\test_live_strategy_signals.py |
| `scripts\discovery\reference_values.py` | RESEARCH | RESEARCH:scripts\exit_multiverse\portfolio_sim.py; TEST:tests\discovery\test_reference_values.py |
| `scripts\discovery\rules.py` | RESEARCH | RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\test_discovery.py |
| `scripts\discovery\sizing_scenarios.py` | TEST-ONLY | TEST:tests\test_discovery.py |
| `scripts\dynamic_rr_multiverse.py` | TEST-ONLY | TEST:tests\discovery\test_dynamic_rr_gate.py; TEST:tests\discovery\test_dynamic_rr_runner.py; TEST:tests\discovery\test_dynamic_rr_smoke.py |
| `scripts\entry_filters.py` | RESEARCH | RESEARCH:scripts\book_portfolio_multiverse.py; RESEARCH:scripts\multiverse3_real_exit.py; RESEARCH:scripts\multiverse4_returns_export.py; RESEARCH:scripts\portfolio_sim_elder.py; TEST:tests\regime\test_entry_filters_no_lookahead.py |
| `scripts\etl_backfill_daily_prices.py` | TEST-ONLY | TEST:tests\collectors\test_daily_derived.py |
| `scripts\eval_sector_news_shadow.py` | UNREFERENCED | - |
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
| `scripts\kis_db\migrate_operational_data.py` | TEST-ONLY | TEST:tests\kis_db\test_migrate_operational_data.py |
| `scripts\kis_db\report_equivalence.py` | TEST-ONLY | TEST:tests\kis_db\test_report_equivalence.py |
| `scripts\kis_db\schema.py` | LIVE-DEP | PROD:tools\paper_strategy_equity.py; RESEARCH:scripts\kis_db\migrate_operational_data.py; TEST:tests\kis_db\test_schema.py |
| `scripts\kis_db\seed_from_legacy.py` | TEST-ONLY | TEST:tests\kis_db\test_seed_from_legacy.py |
| `scripts\kis_db\smoke_state_restore.py` | TEST-ONLY | TEST:tests\kis_db\test_smoke_state_restore.py |
| `scripts\multiverse3_real_exit.py` | TEST-ONLY | TEST:tests\regime\test_multiverse3_real_exit.py |
| `scripts\multiverse4_portfolio_analysis.py` | RESEARCH | RESEARCH:scripts\discovery\sizing_scenarios.py; RESEARCH:scripts\strategy_gate.py; TEST:tests\test_multiverse4.py |
| `scripts\multiverse4_returns_export.py` | RESEARCH | RESEARCH:scripts\dynamic_rr_multiverse.py; RESEARCH:scripts\step2_universe_rebaseline.py; RESEARCH:scripts\step3_pit_rebaseline.py; RESEARCH:scripts\step3c_size_sector_filter.py; RESEARCH:scripts\strategy_gate.py |
| `scripts\param_optimizer.py` | UNREFERENCED | - |
| `scripts\portfolio_sim_elder.py` | TEST-ONLY | TEST:tests\regime\test_portfolio_sim_elder_mkt_rs.py |
| `scripts\preflight_strategy_validate.py` | TEST-ONLY | TEST:tests\test_preflight.py |
| `scripts\prereg_20260903_w1_snapshot.py` | UNREFERENCED | - |
| `scripts\probe_position_entries.py` | UNREFERENCED | - |
| `scripts\regime_split_elder_minervini.py` | UNREFERENCED | - |
| `scripts\regime_split_minervini.py` | UNREFERENCED | - |
| `scripts\regime_split_weinstein.py` | UNREFERENCED | - |
| `scripts\repair_corp_action_prices.py` | TEST-ONLY | TEST:tests\test_repair_cli.py |
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
