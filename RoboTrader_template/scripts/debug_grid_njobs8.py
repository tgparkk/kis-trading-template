"""grid_runner 병렬화 stall 진단 — 5셀 × 1년 × n_jobs=8.

patch #1 검증: portfolio_engine.py:256-268 _get_portfolio_trading_dates() 호출을
backtest_session() 밖으로 이동 (commit befd296) 후 n_jobs=8 stall 재현 여부 확인.

어제(5/8) PoC 144셀 × n_jobs=8: 셀 0개 완료 (stall, 3시간 19분)
오늘(5/9) 14:00경 진단: n_jobs=2 5셀 33분 45초 정상
결론: stall은 n_jobs >= 4~8 임계값에서만 발생
"""
from __future__ import annotations
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PKG_ROOT = _PROJECT_ROOT / "RoboTrader_template"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PKG_ROOT))

# UTF-8 stdout (cp949 em-dash 문제 회피)
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

import logging
import time
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

from RoboTrader_template.multiverse.composable.personas._grid import expand_grid_quant
from RoboTrader_template.multiverse.composable.personas import build_quant_strategy
from RoboTrader_template.multiverse.runner.grid_runner import GridRunConfig, run_grid
from RoboTrader_template.multiverse.data.kospi200_pit import get_kospi200_pit

paramsets = expand_grid_quant()[:5]
print(f"paramsets: {len(paramsets)}")
print(f"hashes: {[ps.config_hash() for ps in paramsets]}")

universe = get_kospi200_pit(date(2024, 1, 2))
print(f"universe: {len(universe)} 종목")

out = Path("D:/GIT/kis-trading-template/RoboTrader_template/output/debug_5cells_njobs8")
out.mkdir(parents=True, exist_ok=True)

config = GridRunConfig(
    mode="plain",
    start_date=date(2024, 1, 2),
    end_date=date(2024, 12, 31),
    initial_capital=10_000_000,
    candidate_symbols=universe,
    output_dir=out,
    n_jobs=8,  # 핵심: patch #1 효과 검증 — 어제 stall 임계값
    universe_filter="kospi200_pit",
)

def factory(ps):
    return build_quant_strategy(ps, candidate_symbols=universe)

t0 = time.monotonic()
print(f"=== run_grid 시작 (5셀 × 1년 × n_jobs=8) — patch #1 효과 검증 ===")
print(f"=== 정상 예상: 약 9~10분 (단일 셀 시간, 5셀 동시 처리) ===")
print(f"=== stall 판정: 15분 후 셀 완료 0개이면 patch #1 미효과 ===")
result = run_grid(config=config, paramsets=paramsets, strategy_factory=factory)
elapsed = time.monotonic() - t0

print(f"=== 완료: {elapsed:.1f}초 ({elapsed/60:.1f}분) ===")
print(f"평가 셀: {result.n_cells_evaluated} / 5 = {result.n_cells_evaluated/5*100:.1f}%")
print(f"DSR 통과: {result.n_cells_passed_dsr}")
print(f"parquet: {result.parquet_path}")

# 셀당 평균
if result.n_cells_evaluated > 0:
    avg = elapsed / result.n_cells_evaluated
    print(f"셀당 평균: {avg:.1f}초")
else:
    print(f"셀 완료 0개 — STALL 재현 (patch #1 효과 없음)")
