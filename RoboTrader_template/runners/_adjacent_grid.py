# RoboTrader_template/runners/_adjacent_grid.py
"""
Stage 1 → Stage 2 인접 격자 생성기.

build_adjacent_grid(top_df, original_grid, max_cells, sample_n) → (grid, info)
- 각 축에서 top_df 통과셀의 값 분포 → min*0.8 ~ max*1.2 범위 sample_n점 균등 샘플
- 분산이 0인 축(통과셀이 단일값) 자동 freeze → 1점만 사용
- 데카르트 곱 cell_count > max_cells면 freeze 추가하며 축소 시도
- 그래도 초과시 ValueError (사장님 결재 트리거)
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd


def _sample_axis(values: List[Any], sample_n: int) -> List[float]:
    """축의 통과셀 값 → min*0.8 ~ max*1.2 범위 sample_n점 균등 샘플."""
    if not values:
        raise ValueError("axis has empty values")
    vmin, vmax = min(values), max(values)
    lo = vmin * 0.8 if vmin > 0 else vmin * 1.2  # 음수 보호
    hi = vmax * 1.2 if vmax > 0 else vmax * 0.8
    if math.isclose(lo, hi):
        return [float(lo)]
    return list(np.linspace(lo, hi, sample_n))


def build_adjacent_grid(
    top_df: pd.DataFrame,
    original_grid: Dict[str, List[Any]],
    max_cells: int,
    sample_n: int = 4,
) -> Tuple[Dict[str, List[Any]], Dict[str, Any]]:
    """Stage 1 통과셀에서 Stage 2 인접 격자 생성."""
    if top_df.empty:
        raise ValueError("top_df is empty — Stage 1 produced 0 passing cells")

    axes = list(original_grid.keys())
    new_grid: Dict[str, List[Any]] = {}
    frozen: List[str] = []

    for axis in axes:
        if axis not in top_df.columns:
            new_grid[axis] = original_grid[axis][:1]
            frozen.append(axis)
            continue
        col = top_df[axis].dropna().tolist()
        if not col:
            new_grid[axis] = original_grid[axis][:1]
            frozen.append(axis)
            continue
        unique_vals = list(set(col))
        if len(unique_vals) <= 1:
            new_grid[axis] = [unique_vals[0]] if unique_vals else original_grid[axis][:1]
            frozen.append(axis)
        else:
            new_grid[axis] = _sample_axis(unique_vals, sample_n)

    # max_cells 초과 시 분산 작은 축부터 freeze
    while True:
        cells = 1
        for v in new_grid.values():
            cells *= len(v)
        if cells <= max_cells:
            break
        # 가장 다양도 낮은 비freeze 축 선택 (값 수 적은 것)
        candidates = [(a, len(new_grid[a])) for a in axes if a not in frozen and len(new_grid[a]) > 1]
        if not candidates:
            raise ValueError(
                f"cell_count={cells} > max_cells={max_cells} after all freezable axes frozen. "
                "Reduce Top N seed or increase max_cells."
            )
        candidates.sort(key=lambda x: x[1])
        target = candidates[0][0]
        new_grid[target] = new_grid[target][:1]
        frozen.append(target)

    final_cells = 1
    for v in new_grid.values():
        final_cells *= len(v)

    info = {
        "cell_count": final_cells,
        "frozen_axes": frozen,
        "sample_n": sample_n,
    }
    return new_grid, info


def export_grid_yaml(grid: Dict[str, List[Any]], path: str) -> None:
    """Stage 2 multiverse_grid override yaml로 저장 (param_optimizer가 일반 grid처럼 읽음)."""
    import yaml
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(grid, f, allow_unicode=True, sort_keys=False)
