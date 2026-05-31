"""워크포워드: 롤링 폴드 생성 + 폴드 평가."""
from __future__ import annotations
from typing import Dict, List
import pandas as pd

from scripts.exit_multiverse import portfolio_sim, objective


def make_folds(start: str, end: str, train_months: int = 24,
               test_months: int = 6, step_months: int = 6) -> List[dict]:
    """[{train_start, train_end, test_start, test_end}] (문자열 YYYY-MM-DD)."""
    s = pd.Timestamp(start); e = pd.Timestamp(end)
    folds = []
    cur = s
    while True:
        tr_start = cur
        tr_end = tr_start + pd.DateOffset(months=train_months)
        te_start = tr_end
        te_end = te_start + pd.DateOffset(months=test_months)
        if te_end > e + pd.DateOffset(days=1):
            if te_start < e:
                te_end = e
                folds.append({"train_start": str(tr_start.date()), "train_end": str(tr_end.date()),
                              "test_start": str(te_start.date()), "test_end": str(te_end.date())})
            break
        folds.append({"train_start": str(tr_start.date()), "train_end": str(tr_end.date()),
                      "test_start": str(te_start.date()), "test_end": str(te_end.date())})
        cur = cur + pd.DateOffset(months=step_months)
    return folds


def _slice_data(data: Dict[str, pd.DataFrame], start: str, end: str) -> Dict[str, pd.DataFrame]:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out = {}
    for code, df in data.items():
        m = (df["datetime"] >= s) & (df["datetime"] <= e)
        sub = df[m].reset_index(drop=True)
        if len(sub) > 0:
            out[code] = sub
    return out


def _reindex_signals(signal_cache_full, full_data, sliced_data) -> Dict[str, List[int]]:
    """전체기간 신호 i(=full df 인덱스)를 슬라이스 df 의 로컬 인덱스로 변환.
    날짜 기준 매핑(신호가 난 날짜가 슬라이스에 있으면 그 로컬 인덱스 사용)."""
    out = {}
    for code, sub in sliced_data.items():
        full_df = full_data[code]
        full_dates = pd.to_datetime(full_df["datetime"])
        sig_dates = set(pd.Timestamp(full_dates.iloc[i]) for i in signal_cache_full.get(code, [])
                        if i < len(full_dates))
        local = [k for k, d in enumerate(pd.to_datetime(sub["datetime"]))
                 if pd.Timestamp(d) in sig_dates]
        out[code] = local
    return out


def evaluate_fold(fold, data, signal_cache_full, adapter, grid, turnover,
                  regime_series, initial_capital, max_positions, max_per_stock,
                  min_obs=20) -> dict:
    """한 폴드: train 에서 그리드 전체 평가 → 국면최악 최고 조합 선정 → test OOS 측정."""
    n_trials = len(grid)
    results = []
    train_data = _slice_data(data, fold["train_start"], fold["train_end"])
    train_sig = _reindex_signals(signal_cache_full, data, train_data)
    for params in grid:
        res = portfolio_sim.run_portfolio(
            data=train_data, signal_cache=train_sig, adapter=adapter, params=params,
            turnover=turnover, initial_capital=initial_capital,
            max_positions=max_positions, max_per_stock=max_per_stock)
        rs = objective.regime_sharpes(res["daily_returns"], regime_series, min_obs=min_obs)
        dsr = objective.compute_dsr(res["daily_returns"], n_trials=n_trials)
        results.append({"params": params, "worst_sharpe": rs["worst"],
                        "regime": rs, "dsr": dsr, "n_trades": res["n_trades"]})
    results.sort(key=lambda r: r["worst_sharpe"], reverse=True)
    if not results:
        raise ValueError("grid must be non-empty")
    best = results[0]
    test_data = _slice_data(data, fold["test_start"], fold["test_end"])
    test_sig = _reindex_signals(signal_cache_full, data, test_data)
    oos = portfolio_sim.run_portfolio(
        data=test_data, signal_cache=test_sig, adapter=adapter, params=best["params"],
        turnover=turnover, initial_capital=initial_capital,
        max_positions=max_positions, max_per_stock=max_per_stock)
    oos_rs = objective.regime_sharpes(oos["daily_returns"], regime_series, min_obs=1)
    oos_total = (oos["equity_curve"][-1] / initial_capital - 1.0) if oos["equity_curve"] else 0.0
    return {"fold": fold, "best": best, "all_results": results,
            "oos_worst_sharpe": oos_rs["worst"], "oos_total_return": oos_total,
            "oos_n_trades": oos["n_trades"]}
