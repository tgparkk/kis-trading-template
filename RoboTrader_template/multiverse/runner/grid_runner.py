"""ParamSet 그리드 발사 — plain / oos_split / walkforward 3 모드."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
import time
from typing import Callable, Literal

from RoboTrader_template.multiverse.composable import ParamSet, ComposableStrategy
from RoboTrader_template.multiverse.engine.portfolio_engine import (
    run_portfolio_backtest,
    PortfolioBacktestResult,
)
from RoboTrader_template.multiverse.metrics import compute_metrics, Metrics
from RoboTrader_template.multiverse.runner.dsr import deflated_sharpe_ratio, passes_dsr
from RoboTrader_template.multiverse.persistence import (
    flush_results_to_parquet,
    write_cell_result,
)


# 데이터과학자 보강: WF 윈도우 최소 요건
MIN_IS_DAYS = 252
MIN_OOS_DAYS = 63
MIN_WF_WINDOWS = 6


Mode = Literal["plain", "oos_split", "walkforward"]


@dataclass
class GridRunConfig:
    mode: Mode
    start_date: date
    end_date: date
    initial_capital: float
    candidate_symbols: list
    output_dir: Path
    n_jobs: int = 4
    # oos_split 전용
    is_ratio: float = 0.7
    # walkforward 전용
    is_window_days: int = 252
    oos_window_days: int = 63
    n_windows: int = 6
    # DSR 통과 임계
    dsr_threshold: float = 0.95
    # 1급 정렬 키 (기본 calmar)
    primary_metric: str = "calmar"


@dataclass
class GridRunResult:
    config: GridRunConfig
    n_cells_evaluated: int
    n_cells_passed_dsr: int
    parquet_path: Path
    rows: list  # 모든 셀 결과 누적


def run_grid(
    *,
    config: GridRunConfig,
    paramsets: list,
    strategy_factory: Callable,
) -> GridRunResult:
    """ParamSet 그리드를 모드에 맞춰 발사.

    모드별 동작:
      - plain: 각 ParamSet에 대해 start~end 단일 백테스트
      - oos_split: 각 ParamSet에 대해 IS(0~is_ratio) + OOS(is_ratio~end). 두 윈도우 모두 측정.
      - walkforward: rolling 윈도우 n_windows개 (IS=is_window_days, OOS=oos_window_days, step=oos_window_days)

    WF 가드: is_window_days<252 또는 oos_window_days<63 또는 n_windows<6 → ValueError

    그리드 차원 병렬 (ThreadPoolExecutor n_jobs).
    각 셀 결과 → compute_metrics → DSR 계산 → Parquet row 누적 → 최종 flush.
    """
    if config.mode == "walkforward":
        if config.is_window_days < MIN_IS_DAYS:
            raise ValueError(
                f"walkforward IS 윈도우는 ≥{MIN_IS_DAYS}거래일 필요 (현재 {config.is_window_days})"
            )
        if config.oos_window_days < MIN_OOS_DAYS:
            raise ValueError(
                f"walkforward OOS 윈도우는 ≥{MIN_OOS_DAYS}거래일 필요 (현재 {config.oos_window_days})"
            )
        if config.n_windows < MIN_WF_WINDOWS:
            raise ValueError(
                f"walkforward 윈도우 개수는 ≥{MIN_WF_WINDOWS} 필요 (현재 {config.n_windows})"
            )

    rows: list = []

    # 셀 작업 단위: (paramset, window_idx, ws, we) 튜플
    cell_tasks = list(_expand_cells(config, paramsets))
    n_total_trials = len(cell_tasks)

    def _run_one_cell(task) -> dict:
        paramset, window_idx, ws, we = task
        strategy = strategy_factory(paramset)
        t0 = time.monotonic()
        result: PortfolioBacktestResult = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=config.candidate_symbols,
            start_date=ws,
            end_date=we,
            initial_capital=config.initial_capital,
        )
        runtime = time.monotonic() - t0
        metrics: Metrics = compute_metrics(
            result.daily_equity, result.trades, config.initial_capital
        )
        # DSR — n_trials = 그리드 전체 셀 수
        n_obs = len(result.daily_equity)
        dsr = deflated_sharpe_ratio(
            sharpe=metrics.sharpe,
            n_trials=n_total_trials,
            n_observations=n_obs,
            skew=metrics.return_skew,
            excess_kurt=metrics.return_kurt,
        )
        return write_cell_result(
            output_dir=config.output_dir,
            paramset_id=paramset.paramset_id(),
            config_hash=paramset.config_hash(),
            mode=config.mode,
            window_idx=window_idx,
            start_date=ws,
            end_date=we,
            metrics=asdict(metrics) | {"dsr": dsr, "passes_dsr": passes_dsr(dsr, config.dsr_threshold)},
            runtime_seconds=runtime,
            extra={"final_equity": result.final_equity},
        )

    # 병렬 실행
    if config.n_jobs <= 1:
        for task in cell_tasks:
            rows.append(_run_one_cell(task))
    else:
        with ThreadPoolExecutor(max_workers=config.n_jobs) as pool:
            futures = [pool.submit(_run_one_cell, t) for t in cell_tasks]
            for f in as_completed(futures):
                rows.append(f.result())

    parquet_path = flush_results_to_parquet(
        config.output_dir, rows, config.mode
    )

    return GridRunResult(
        config=config,
        n_cells_evaluated=len(rows),
        n_cells_passed_dsr=sum(1 for r in rows if r.get("m_passes_dsr")),
        parquet_path=parquet_path,
        rows=rows,
    )


def _expand_cells(config: GridRunConfig, paramsets: list) -> list:
    """모드별로 (paramset, window_idx, start, end) 튜플 생성."""
    if config.mode == "plain":
        return [(p, 0, config.start_date, config.end_date) for p in paramsets]

    if config.mode == "oos_split":
        # IS 윈도우 + OOS 윈도우 — 캘린더일로 계산
        total = (config.end_date - config.start_date).days
        is_end = config.start_date + timedelta(days=int(total * config.is_ratio))
        cells = []
        for p in paramsets:
            cells.append((p, 0, config.start_date, is_end))   # IS
            cells.append((p, 1, is_end, config.end_date))     # OOS
        return cells

    if config.mode == "walkforward":
        # rolling 윈도우 n_windows개
        cells = []
        for p in paramsets:
            for i in range(config.n_windows):
                # offset = i * oos_window_days (캘린더일 단순화)
                offset_days = i * config.oos_window_days
                ws = config.start_date + timedelta(days=offset_days)
                we = ws + timedelta(days=config.is_window_days + config.oos_window_days)
                if we > config.end_date:
                    we = config.end_date
                cells.append((p, i, ws, we))
        return cells

    raise ValueError(f"unknown mode: {config.mode}")


def filter_passed_dsr(rows: list) -> list:
    """DSR 통과 셀만."""
    return [r for r in rows if r.get("m_passes_dsr")]


def sort_by_primary_metric(rows: list, metric: str = "calmar") -> list:
    """1급 지표로 내림차순 정렬. DSR 미통과 셀은 정렬 후순위로 자동 푸시."""
    key = f"m_{metric}"
    return sorted(
        rows,
        key=lambda r: (r.get("m_passes_dsr", False), r.get(key, 0.0)),
        reverse=True,
    )
