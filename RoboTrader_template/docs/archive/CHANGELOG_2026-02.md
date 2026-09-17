> **DEPRECATED 2026-09-17 — 보관용.** 이 변경 이력은 **2026-02-11(커밋 `549fad2`)에서 동결**됐다. 마지막 항목 `[0.9.0] 2026-02-10` 이후 약 1,180 커밋이 기록되지 않았고, 태그는 2개(`pre-quant-removal` 02-08 · `v0.9.0-pre-test` 03-02), 루트 `pyproject.toml` 의 version 은 0.9.0 고정.
> 이후 이력 = `git log`(레포) + 세션 changelog(`changelog-YYYY-MM-DD-*.md` · 레포 밖 Claude Code 프로젝트 메모리).
> 아래 수치는 2026-02 당시 값 — 「Test count 1014」는 현재 `tests/` 372 파일·`def test_` 5,012(정적 집계)와 다르고, 예제 전략(momentum·mean_reversion·volume_breakout)은 `strategies/` 에 코드(strategy.py·config.yaml)가 남아 있지만 `config/trading_config.json` `strategies[]` 에 없어 로드되지 않는 비활성(`main.py` `_load_strategies` 는 그 목록만 로드)이며, 라이브는 그 목록의 8전략이다.
> 원문은 아래 그대로.

# Changelog

All notable changes to this project will be documented in this file.

## [0.9.0] - 2026-02-10

### Added
- **Type hints**: ~130 functions across 38 files with full return type annotations
- **Screener optimization**: ETF pre-filter + ThreadPoolExecutor parallel fetching (~5-10x speedup)
- **Logging standardization**: All `print` statements converted to `logger` calls (main.py, settings.py, post_market_data_saver.py)
- **README**: Updated setup instructions (key.ini, trading_config.json)

### Fixed
- `test_stock_screener.py`: Missing `change_rate` field in mock data
- `test_main_loop.py`: Missing `_load_screener_candidates` mock
- `test_circuit_breaker.py`: sys.modules mock pollution issue
- `api/__init__.py`: Added missing circuit_breaker import

## [0.8.0] - 2026-02-09

### Added
- **Dry-run simulation** (P3): `DryRunBroker` with virtual execution, partial fills, random rejection
- **Full cycle simulation**: 19 tests covering market open → close with price injection
- **Abnormal scenario simulation**: 18 tests (circuit breaker, partial fill, order rejection, timeout, VI)
- **Report generator** (`core/report_generator.py`): Daily markdown + Telegram reports with FIFO PnL

### Added (Strategy Templates - P1)
- 3 example strategies: momentum, mean_reversion, volume_breakout
- `docs/STRATEGY_GUIDE.md`: Step-by-step guide for new strategy development
- StrategyLoader dynamic loading for all 4 strategies
- 45 strategy tests (interface compliance + logic + loader)

### Added (Stability - P0)
- **Circuit Breaker integration**: VI/halt → order blocking (buy blocked on VI, sell allowed)
- **Thread safety**: `threading.Lock` on `CircuitBreakerState`
- **Holiday integration**: `MarketHours` methods check `korean_holidays`
- **confirm_order fix**: Excess fill amount deducted from available_funds
- **4 stability scenarios**: Network resilience, order safety, market boundary, position safety
- **Main loop error isolation**: 5 stages with independent try/except
- **state_restorer edge cases**: 26 tests covering partial failure, NULL fields, DB fallback

### Fixed
- `round_to_tick`: Banker's rounding → `math.floor(x/tick + 0.5) * tick`
- `test_executor`: price_rounding tick=100 assertion corrected
- `test_database`: psycopg2 mock isolation
- `test_daily_data_failure`: encoding, asyncio, API signature fixes
- OrderStatus.FAILED enum added
- 23 dead imports removed

## [0.7.0] - 2026-02-08

### Added
- **KISBroker integration** (Steps 1-3): Unified broker abstraction
- **main.py refactor**: 24% code reduction, single sequential loop (3s interval)
- **Screener → strategy pipeline**: `CandidateSelector.load_from_screener()` with ETF filter
- **Documentation**: ARCHITECTURE.md, TRADING_FLOW.md, CONFIGURATION.md
- 36 initial tests (main_loop, state_restorer, trading_flow)

---

Test count: **1014 passed**, 2 skipped, 0 failed
