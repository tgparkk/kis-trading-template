# CODE MAP — 운영 vs 연구 경계 (에이전트 라우팅)

> 목적: 에이전트가 "운영 동작"을 찾을 때 연구/일회성 코드에 오도되지 않도록.
> 최종 검증: 2026-07-02 (Phase 1 승격 완료 + Phase 2 `backtest/` 연구 분류 확정). 드리프트 의심 시 하단 검증 명령 재실행.

## 디렉토리 분류
- **운영(production, 라이브 매매 경로)**: `core/` `bot/` `framework/` `api/`
  `strategies/` `collectors/` `db/` `runners/` `signals/` `lib/` `utils/` `tools/`
  - `tools/` = EOD 운영 도구(일일 리포트·equity 스냅샷). 라이브 봇이 import하는 비(非)전략 운영 코드.
- **연구/일회성(research, 라이브 아님)**: `scripts/` `multiverse/` `books/` `council/` `backtest/`
  → 운영 동작을 여기서 추론하지 말 것. 파일별 태깅은 [INVENTORY.md](INVENTORY.md) 참조.
  - `backtest/` 확정 근거(2026-07-02): 유일한 라이브 참조였던 `make_screener_snapshot_provider`
    팩토리가 `core/screener_snapshot_provider.py`로 승격되어 라이브 의존 0건 확정(Phase2).
    남은 `runners.param_optimizer`·`runners.run_buy_filter_grid` 참조는 연구 CLI 러너였고
    같은 날 `scripts/`로 이동, INVENTORY LIVE-DEP 0건 재확인.
- **runners/**: 운영 디렉토리이나 실제 라이브 의존은 `_adapter_factory.py`
  (← `bot/candidate_loader.py:252` 지연 import) · `screener_snapshot_collector.py`
  (← `bot/liquidation_handler.py:432` 지연 import) 2개뿐. `param_optimizer.py`·
  `run_buy_filter_grid.py`는 연구 그리드 러너로 오분류돼 있었던 것을 2026-07-02
  `scripts/`로 강등(Task 4).
- **archive/**: 무참조 확정 연구코드 보관소(2026-07-02 76건 이동, 판정근거
  `docs/superpowers/plans/2026-07-02-archive-candidates.md`). 검색 대상 아님, 복원은 git mv 역방향.

## ✅ 라이브 → 연구 의존 엣지: **0건** (2026-07-02 Phase 1 승격 완료)

과거 9엣지(정적 8 + 동적 1)는 전부 운영 위치로 승격됨. 연구 스크립트는 필요 시 운영 코드를
**역방향 import**(연구→운영, 허용)한다. 승격 이력:

| 과거 엣지 (라이브 파일 → 연구 대상) | 새 위치 |
|---|---|
| `collectors/daily_adj.py:8` → 동적 import `scripts.10pct_strategy.p0_apply_adj_factor` | `collectors/adj_factors.py` (compute_adj_factors, importlib 제거) |
| `bot/system_monitor.py` → `scripts.daily_trading_summary` | `tools/daily_trading_summary.py` |
| `bot/system_monitor.py` → `scripts.paper_strategy_equity` | `tools/paper_strategy_equity.py` |
| `collectors/daily_derived.py` → `scripts.etl_backfill_daily_prices.SQL_UPDATE_RETURNS` | `collectors/daily_derived.py` (상수 내장) |
| `collectors/foreign_flow_collector.py` → `scripts.backfill_foreign_flow.fetch_foreign_naver` | `collectors/foreign_flow_fetcher.py` |
| `strategies/rs_leader/{strategy,screener}.py` → `scripts.rs_leader.rule.RSLeaderRule` | `strategies/rs_leader/rule.py` |
| `strategies/deep_mr_dev20/{strategy,screener}.py` → `scripts.discovery.rules.MeanReversionMA20Rule` | `strategies/deep_mr_dev20/rule.py` (rules.py는 re-export 유지) |
| `core/candidate_selector.py:885` → `backtest.engine.make_screener_snapshot_provider` (지연 import) | `core/screener_snapshot_provider.py` (verbatim 승격, `backtest/engine.py`는 re-export만 유지, Phase2) |

## .bat 엔트리포인트
- `매일_분석_실행.bat:23` → `python tools\daily_trading_summary.py` (Phase1에서 경로 동반수정)
- `장마감_자동분석.bat` → **비활성** (호출 대상 `scripts/auto_analysis.py`가 저장소에 부재, 2026-07-02 REM 처리)

## 검증 명령 (드리프트 점검)
```bash
grep -rn "from scripts\|import scripts\|from multiverse\|import multiverse\|from backtest\|import backtest" bot/ collectors/ strategies/ core/ framework/ api/ db/ runners/ signals/ lib/ utils/ tools/ --include="*.py" | grep -v test
grep -rn "import_module\|__import__" bot/ collectors/ core/ framework/ api/ db/ runners/ signals/ tools/ --include="*.py" | grep -v gen_inventory
# (gen_inventory.py는 동적 import '탐지기'라 문자열 매치가 자기 소스에 걸림 — 오탐 제외)
grep -rn "scripts" *.bat
```
Expected: 첫 두 명령 **0건**(라이브 엣지 재발=FAIL), .bat은 REM 처리된 행만.
인벤토리 재생성: `venv\Scripts\python tools/gen_inventory.py > docs/INVENTORY.md` (LIVE-DEP=0 유지 확인).

관련 설계: `docs/superpowers/specs/2026-06-30-research-production-separation-design.md` · 계획: `docs/superpowers/plans/2026-07-02-research-production-separation-phase1.md`
