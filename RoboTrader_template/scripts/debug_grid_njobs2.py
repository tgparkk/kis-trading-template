"""grid_runner 병렬화 stall 진단 — 5셀 × 1년 × n_jobs=2.

어제 PoC 144셀 × n_jobs=8 가동 시 셀 0개 완료(stall) 재현 시도.
단일 셀(n_jobs=1)은 9분 9초에 정상 완료됨이 5/9 진단으로 확인됨.
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

out = Path("D:/GIT/kis-trading-template/RoboTrader_template/output/debug_5cells_njobs2")
out.mkdir(parents=True, exist_ok=True)

config = GridRunConfig(
    mode="plain",
    start_date=date(2024, 1, 2),
    end_date=date(2024, 12, 31),
    initial_capital=10_000_000,
    candidate_symbols=universe,
    output_dir=out,
    n_jobs=2,  # 핵심: 병렬 활성화
    universe_filter="kospi200_pit",
)

def factory(ps):
    return build_quant_strategy(ps, candidate_symbols=universe)

t0 = time.monotonic()
print(f"=== run_grid 시작 (5셀 × 1년 × n_jobs=2) — 정상이면 약 22~30분 예상 ===")
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
