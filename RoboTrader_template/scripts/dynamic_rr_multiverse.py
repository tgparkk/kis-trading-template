"""동적 손익비 멀티버스 오케스트레이터 (측정 전용).

전략별: 베이스라인(고정) + 동적 그리드 셀 → run_portfolio → metrics → ΔSharpe.
Task 7: OOS 강건성 게이트 (train/test 분할 ΔSharpe + 부트스트랩 ΔSharpe p05 +
비용스트레스 ΔSharpe) — 동적 셀은 베이스라인을 강건히 이겨야만 "승리".
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.exit_multiverse.portfolio_sim import run_portfolio
from scripts.book_portfolio_multiverse import _SLTPMHAdapter
from scripts.book_param_multiverse import _daily_metrics
# strategy_gate 와 동일 비용패치 컨텍스트 재사용 (run_portfolio 에 slippage 파라미터가
# 없으므로 모듈 상수를 일시 교체하는 방식 — 라이브/타파일 무수정).
from scripts.multiverse4_returns_export import _patch_costs
from scripts.exit_multiverse.portfolio_sim import SLIPPAGE_RATE as _BASE_SLIPPAGE

_INITIAL = 10_000_000

# OOS 강건성 게이트 임계 (strategy_gate G4/G5 철학과 정합).
MIN_TRADES = 30
MAX_CLAMP_FRAC = 0.20
_OOS_CUTOFF = "2024-06-30"   # train ≤ cutoff < test
_COST_STRESS_SLIPPAGE_ADD = 0.003   # 비용스트레스: 슬리피지 +30bp
_BOOT_SEED = 12345
_BOOT_ITERS = 500
_BOOT_BLOCK = 21


def evaluate_dynamic_gates(cell: dict) -> Tuple[bool, str]:
    """4관문: 거래수>=MIN_TRADES & clamp_frac<=MAX_CLAMP_FRAC,
    OOS(train&test ΔSharpe>0 & Sharpe>0), 부트스트랩 ΔSharpe p05>0, 비용스트레스 ΔSharpe>0."""
    if cell["n_trades"] < MIN_TRADES:
        return False, f"few_trades({cell['n_trades']}<{MIN_TRADES})"
    if cell["clamp_frac"] > MAX_CLAMP_FRAC:
        return False, f"clamp_frac_high({cell['clamp_frac']:.2f})"
    if not (cell["delta_sharpe_train"] > 0 and cell["sharpe_train"] > 0):
        return False, "train_window_not_positive"
    if not (cell["delta_sharpe_test"] > 0 and cell["sharpe_test"] > 0):
        return False, "test_window_not_positive"
    if not (cell["boot_dsharpe_p05"] > 0):
        return False, "bootstrap_p05<=0"
    if cell["delta_sharpe_cost"] <= 0:
        return False, "cost_stress_negative"
    return True, "PASS"


def build_grid() -> List[dict]:
    """베이스라인 포함 전체 그리드 셀 목록을 반환한다."""
    cells: List[dict] = [{"ref_type": "fixed"}]
    for ref in ("box", "atr", "bollinger"):
        for n in (10, 20):
            for sl_mult in (1.0, 1.5, 2.0):
                for rr in (1.0, 1.5, 2.0, 3.0):
                    cells.append(
                        {"ref_type": ref, "n": n, "sl_mult": sl_mult,
                         "rr": rr, "buffer": 0.0, "bb_k": 2.0}
                    )
    return cells


GRID = build_grid()


def _make_turnover(signals: Dict[str, list]) -> Dict[str, float]:
    """signals 딕셔너리의 종목코드로 uniform turnover 맵을 만든다."""
    return {code: 1.0 for code in signals}


def _run(
    data: Dict[str, pd.DataFrame],
    signals: Dict[str, list],
    base_params: dict,
    dyn: Optional[dict],
    max_positions: int = 5,
) -> dict:
    """run_portfolio 1회 실행 결과(raw)를 반환한다."""
    turnover = _make_turnover(signals)
    return run_portfolio(
        data, signals, _SLTPMHAdapter(), base_params, turnover,
        max_positions=max_positions, dyn=dyn,
    )


def _metrics_from_result(res: dict) -> dict:
    """run_portfolio 결과 dict → _daily_metrics + n_trades/clamp_frac."""
    equity = res["equity_curve"]  # confirmed key
    m = _daily_metrics(_INITIAL, equity, res["trades"])
    sells = [t for t in res["trades"] if t.get("side") == "sell"]
    m["n_trades"] = len(sells)
    m["clamp_frac"] = (
        sum(1 for t in sells if t.get("tp_clamped")) / len(sells)
        if sells else 0.0
    )
    return m


def _metrics_for(
    data: Dict[str, pd.DataFrame],
    signals: Dict[str, list],
    base_params: dict,
    dyn: Optional[dict],
    max_positions: int = 5,
) -> dict:
    """run_portfolio 실행 후 _daily_metrics 로 지표를 계산한다."""
    return _metrics_from_result(_run(data, signals, base_params, dyn, max_positions))


def _split_data_by_date(
    data: Dict[str, pd.DataFrame],
    signals: Dict[str, list],
    cutoff: str = _OOS_CUTOFF,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, list],
           Dict[str, pd.DataFrame], Dict[str, list]]:
    """각 종목 df 를 cutoff 기준 train(≤cutoff)/test(>cutoff) 로 분할하고
    신호 바 인덱스를 윈도우-로컬 위치로 리매핑한다.

    리매핑 규약: 원본 정수 인덱스 i 의 datetime 이 윈도우 마스크에 들면, 그 종목의
    윈도우-로컬 df(reset_index drop) 에서의 위치(=마스크 내 누적 순번)로 매핑한다.
    윈도우 df 는 datetime 순서를 보존하므로 i → (윈도우 내 i 이하 마스크 개수 - 1).
    윈도우 밖 신호는 버린다. 윈도우에 신호/바가 부족한 셀은 거래수 게이트에서
    자연 탈락(크래시 없음).
    """
    cut = pd.Timestamp(cutoff)
    train_d: Dict[str, pd.DataFrame] = {}
    train_s: Dict[str, list] = {}
    test_d: Dict[str, pd.DataFrame] = {}
    test_s: Dict[str, list] = {}
    for code, df in data.items():
        dt = pd.to_datetime(df["datetime"])
        train_mask = (dt <= cut).to_numpy()
        test_mask = (dt > cut).to_numpy()
        # 원본 인덱스 → 윈도우-로컬 위치 매핑 (마스크 누적합 - 1)
        train_pos = np.cumsum(train_mask) - 1
        test_pos = np.cumsum(test_mask) - 1
        sub_train = df[train_mask].reset_index(drop=True)
        sub_test = df[test_mask].reset_index(drop=True)
        sig = signals.get(code, [])
        tr_sig = sorted({int(train_pos[i]) for i in sig
                         if 0 <= i < len(train_mask) and train_mask[i]})
        te_sig = sorted({int(test_pos[i]) for i in sig
                         if 0 <= i < len(test_mask) and test_mask[i]})
        if len(sub_train):
            train_d[code] = sub_train
            train_s[code] = tr_sig
        if len(sub_test):
            test_d[code] = sub_test
            test_s[code] = te_sig
    return train_d, train_s, test_d, test_s


def _window_delta_sharpe(
    data: Dict[str, pd.DataFrame],
    signals: Dict[str, list],
    base_params: dict,
    dyn: Optional[dict],
    max_positions: int,
) -> Tuple[float, float]:
    """윈도우 내에서 베이스라인 + 셀을 각각 돌려 (cell_sharpe, delta_sharpe) 반환.

    데이터/신호가 비면 (0.0, 0.0) — 거래수 게이트에서 탈락하도록 graceful.
    """
    if not data:
        return 0.0, 0.0
    base_m = _metrics_for(data, signals, base_params, dyn=None,
                          max_positions=max_positions)
    base_s = float(base_m.get("sharpe", 0.0))
    if dyn is None:
        # fixed 셀: 자기참조 → ΔSharpe 정확히 0 (동일 런)
        return base_s, 0.0
    cell_m = _metrics_for(data, signals, base_params, dyn=dyn,
                          max_positions=max_positions)
    cell_s = float(cell_m.get("sharpe", 0.0))
    return cell_s, cell_s - base_s


def _trade_pnls(res: dict) -> np.ndarray:
    """매도(청산) 거래의 pnl_pct 배열 (체결 순서 보존)."""
    return np.array([float(t["pnl_pct"]) for t in res["trades"]
                     if t.get("side") == "sell"], dtype=float)


def _sharpe_of_pnls(pnls: np.ndarray) -> float:
    """거래당 pnl 시퀀스의 (무연율화) Sharpe = mean/std. 표본<2 또는 std=0 → 0."""
    pnls = pnls[np.isfinite(pnls)]
    if len(pnls) <= 1 or pnls.std() == 0:
        return 0.0
    return float(pnls.mean() / pnls.std())


def _bootstrap_dsharpe_p05(
    cell_pnls: np.ndarray,
    base_pnls: np.ndarray,
    n_iter: int = _BOOT_ITERS,
    block: int = _BOOT_BLOCK,
    seed: int = _BOOT_SEED,
) -> float:
    """셀·베이스라인 거래당 pnl 시퀀스를 각각 이동블록 부트스트랩(B회) 재표집하여
    ΔSharpe(=cell_sharpe − base_sharpe) 분포의 5분위를 반환한다.

    재현성을 위해 np.random.default_rng(seed) 고정. 표본이 block*2 미만이면
    단순 i.i.d. 복원추출로 폴백(여전히 seed 고정). 한쪽이라도 비면 nan.
    """
    if len(cell_pnls) == 0 or len(base_pnls) == 0:
        return float("nan")
    rng = np.random.default_rng(seed)

    def _resample(x: np.ndarray) -> np.ndarray:
        n = len(x)
        if n < block * 2:
            idx = rng.integers(0, n, size=n)
            return x[idx]
        n_blocks = int(np.ceil(n / block))
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        return np.concatenate([x[s:s + block] for s in starts])[:n]

    diffs = np.empty(n_iter)
    for it in range(n_iter):
        diffs[it] = _sharpe_of_pnls(_resample(cell_pnls)) - _sharpe_of_pnls(_resample(base_pnls))
    return float(np.percentile(diffs, 5))


def _cost_stress_delta_sharpe(
    data: Dict[str, pd.DataFrame],
    signals: Dict[str, list],
    base_params: dict,
    dyn: dict,
    max_positions: int,
) -> float:
    """슬리피지 +30bp 비용스트레스 하에서 ΔSharpe(=cell − baseline) 재계산.

    run_portfolio 에 slippage 파라미터가 없으므로 _patch_costs 컨텍스트로 모듈
    상수 SLIPPAGE_RATE 를 (기존+0.003) 으로 일시 교체한다(strategy_gate G4_cost 와
    동일 방식). 동일 컨텍스트 안에서 base/cell 을 모두 돌려 동일 비용을 보장.
    """
    stressed = _BASE_SLIPPAGE + _COST_STRESS_SLIPPAGE_ADD
    with _patch_costs(slippage=stressed):
        base_s = float(_metrics_for(data, signals, base_params, dyn=None,
                                    max_positions=max_positions).get("sharpe", 0.0))
        cell_s = float(_metrics_for(data, signals, base_params, dyn=dyn,
                                    max_positions=max_positions).get("sharpe", 0.0))
    return cell_s - base_s


def run_strategy_grid(
    name: str,
    data: Dict[str, pd.DataFrame],
    signals: Dict[str, list],
    base_params: dict,
    grid: Optional[List[dict]] = None,
    max_positions: int = 5,
    boot_iters: int = _BOOT_ITERS,
) -> List[dict]:
    """전략 하나에 대해 그리드 전체를 돌려 ΔSharpe + OOS 강건성 행 목록을 반환한다.

    각 행은 풀기간 지표(sharpe/pnl/calmar/max_dd/delta_sharpe) 외에
    train/test 윈도우 ΔSharpe, 부트스트랩 ΔSharpe p05, 비용스트레스 ΔSharpe,
    그리고 evaluate_dynamic_gates 의 (gate_pass, gate_reason) 을 포함한다.

    Parameters
    ----------
    name:         전략 이름 (행에 기록됨)
    data:         종목코드 → OHLCV DataFrame
    signals:      종목코드 → 진입 바 인덱스 리스트
    base_params:  고정 sl/tp/mh 파라미터 (베이스라인)
    grid:         그리드 셀 목록; None 이면 GRID 전체 사용
    max_positions: 동시 최대 포지션 수
    boot_iters:   부트스트랩 반복수 (테스트에선 축소)
    """
    grid = grid if grid is not None else GRID

    # 풀기간 베이스라인 (재사용)
    base_res = _run(data, signals, base_params, dyn=None, max_positions=max_positions)
    base_sharpe = float(_metrics_from_result(base_res).get("sharpe", 0.0))
    base_pnls = _trade_pnls(base_res)

    # train/test 윈도우 1회 분할 (그리드 전체 공유)
    tr_d, tr_s, te_d, te_s = _split_data_by_date(data, signals)

    rows: List[dict] = []
    for cell in grid:
        dyn = None if cell.get("ref_type") == "fixed" else cell
        res = _run(data, signals, base_params, dyn=dyn, max_positions=max_positions)
        m = _metrics_from_result(res)
        cell_sharpe = float(m.get("sharpe", 0.0))

        # 윈도우별 베이스라인+셀 재실행 → 윈도우 ΔSharpe
        s_tr, d_tr = _window_delta_sharpe(tr_d, tr_s, base_params, dyn, max_positions)
        s_te, d_te = _window_delta_sharpe(te_d, te_s, base_params, dyn, max_positions)

        if dyn is None:
            # fixed 셀: 모든 ΔSharpe 정확히 0, 비용스트레스도 0 (자기참조)
            boot_p05 = 0.0
            d_cost = 0.0
        else:
            boot_p05 = _bootstrap_dsharpe_p05(_trade_pnls(res), base_pnls,
                                              n_iter=boot_iters)
            d_cost = _cost_stress_delta_sharpe(data, signals, base_params, dyn,
                                               max_positions)

        row = {
            "strategy": name,
            **cell,
            "sharpe": cell_sharpe,
            "calmar": float(m.get("calmar", 0.0)),
            "max_dd": float(m.get("max_dd", 0.0)),
            "pnl": float(m.get("pnl", 0.0)),
            "n_trades": int(m.get("n_trades", 0)),
            "clamp_frac": float(m.get("clamp_frac", 0.0)),
            "delta_sharpe": cell_sharpe - base_sharpe,
            "sharpe_train": s_tr,
            "delta_sharpe_train": d_tr,
            "sharpe_test": s_te,
            "delta_sharpe_test": d_te,
            "boot_dsharpe_p05": boot_p05,
            "delta_sharpe_cost": d_cost,
        }
        gate_pass, gate_reason = evaluate_dynamic_gates(row)
        row["gate_pass"] = gate_pass
        row["gate_reason"] = gate_reason
        rows.append(row)
    return rows
