"""Book19 envelope_200d_high 워크포워드 안정성 검증 (고정 config).

목적: 단일 train/test 홀드아웃(memory: train 1.20 / test 1.82)을 넘어, 채택후보 config
가 *여러 연속 윈도우*에 걸쳐 일관 양수인지(진짜 엣지) 아니면 2~3 윈도우(2021 모멘텀
+2024~26 랠리)에 집중됐는지(취약) 확인한다.

★방법(워밍업 아티팩트 회피):
  naive 윈도우 분할은 불가하다 — _load_daily_adj 가 [start,end] 만 로드하므로 6개월
  윈도우(n≈120봉)는 envelope 룰의 200봉 요구(need=202)를 못 채워 신호 0 이 된다.
  (기존 OOS test 분할 2024-07~ 도 같은 이유로 앞 ~10개월 워밍업 손상이 의심된다.)
  → 풀기간(2021~2026)을 **1회 연속 백테스트**(각 진입일이 자연히 200봉 선행 히스토리
    확보) 후, 결과 daily_returns(date-indexed) 스트림을 연속 캘린더 윈도우로 *분해*해
    윈도우별 Sharpe/PnL/MaxDD 를 계산한다. 이게 고정 config 의 통계적으로 올바른
    워크포워드다(in-sample best-of-grid 가 아니라 a priori 고정 config 의 OOS 안정성).

고정 config (memory remeasure-2026-06-05-book19-quant, OOS 채택후보):
  rule=envelope_200d_high(책 A~I 기본값), exit sl0.08/tp0.10/mh10, K=5,
  universe top_volume:50 (robotrader_quant SSOT), gate=none.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# scripts/ 를 path 에 (형제 모듈 import).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.book_portfolio_multiverse import (  # noqa: E402
    _ADAPTER,
    _precompute_signals,
    _load_kospi_close,
)
from scripts.book_param_multiverse import (  # noqa: E402
    _build_strategy,
    _daily_minmax_dates,
    _load_daily_adj,
    _load_top_volume_daily,
    _load_book,
)
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402

WARMUP = 42          # 드라이버 daily warmup (룰 자체가 내부 200봉 요구 → 자연 발사)
TOP_N = 50
K = 5
INITIAL = 10_000_000.0
MAX_PER_STOCK = 3_000_000.0
EXIT = dict(stop_loss_pct=0.08, take_profit_pct=0.10, max_hold_bars=10)


def _semiannual_windows(start: str, end: str):
    """[start,end] 를 H1(1-6월)/H2(7-12월) 반기 윈도우 경계로 분할."""
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    wins = []
    y = s.year
    while y <= e.year:
        for half, (m0, d0, m1, d1) in (
            ("H1", (1, 1, 6, 30)),
            ("H2", (7, 1, 12, 31)),
        ):
            w0 = pd.Timestamp(year=y, month=m0, day=d0)
            w1 = pd.Timestamp(year=y, month=m1, day=d1)
            if w1 < s or w0 > e:
                continue
            wins.append((f"{y}{half}", max(w0, s), min(w1, e)))
        y += 1
    return wins


def _sharpe(rets: np.ndarray) -> float:
    rets = rets[np.isfinite(rets)]
    if len(rets) <= 1 or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * math.sqrt(252))


def _maxdd(eq: np.ndarray) -> float:
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(-dd.min())


def main():
    mn, mx = _daily_minmax_dates()
    print(f"[load] full daily period: {mn} ~ {mx}")
    uni = _load_top_volume_daily(mn, mx, TOP_N)
    data = _load_daily_adj(uni, mn, mx)
    turnover = {c: float((df["close"] * df["volume"]).sum()) for c, df in data.items()}
    print(f"[load] universe={len(uni)} loaded={len(data)}")

    # 룰 로드 + 전략 빌드 (책 기본값, override 없음).
    _strat_mod, rules_mod = _load_book("trading_strategy_book", "rules")
    rule_cls = getattr(rules_mod, "rule_envelope_200d_high")
    strat = _build_strategy(rule_cls, "envelope_200d_high", {})

    cache = _precompute_signals(data, strat, WARMUP, "daily")
    n_sig = sum(len(v) for v in cache.values())
    print(f"[signals] total triggered bars: {n_sig}")

    res = run_portfolio(
        data=data, signal_cache=cache, adapter=_ADAPTER, params=EXIT,
        turnover=turnover, initial_capital=INITIAL, max_positions=K,
        max_per_stock=MAX_PER_STOCK,
    )

    dr: pd.Series = res["daily_returns"]
    dr.index = pd.to_datetime(dr.index)
    dr = dr.sort_index()
    eq_full = INITIAL * (1.0 + dr).cumprod()

    # 전체 메트릭 (sanity: memory 의 full-period 와 대조).
    full_pnl = float(eq_full.iloc[-1] / INITIAL - 1.0) if len(eq_full) else 0.0
    full_sharpe = _sharpe(dr.to_numpy())
    full_dd = _maxdd(eq_full.to_numpy())
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    print(f"[full] sharpe={full_sharpe:.3f} pnl={full_pnl:+.1%} "
          f"maxdd={full_dd:.1%} sells={len(sells)}")

    # KOSPI 윈도우 대비.
    kospi = _load_kospi_close(mn, mx)
    kospi.index = pd.to_datetime(kospi.index)
    kospi = kospi.sort_index()

    # sell 거래를 exit 날짜로 버킷팅.
    sell_dt = pd.to_datetime([t["datetime"] for t in sells])
    sell_pnl = np.array([t["pnl_pct"] for t in sells], dtype=float)

    wins = _semiannual_windows(mn, mx)
    print("\n=== WALK-FORWARD (반기 윈도우, 고정 config sl8/tp10/mh10 K5) ===")
    print(f"{'window':<8} {'sharpe':>8} {'pnl':>9} {'maxdd':>8} "
          f"{'ntr':>5} {'hit':>6} {'kospi':>9} {'alpha':>9}")
    pos_cnt = 0
    rows_out = []
    for name, w0, w1 in wins:
        m = (dr.index >= w0) & (dr.index <= w1)
        rw = dr[m]
        if len(rw) == 0:
            continue
        eqw = (1.0 + rw).cumprod()
        pnl = float(eqw.iloc[-1] - 1.0)
        sh = _sharpe(rw.to_numpy())
        dd = _maxdd(eqw.to_numpy())
        tmask = (sell_dt >= w0) & (sell_dt <= w1)
        ntr = int(tmask.sum())
        hit = float((sell_pnl[tmask] > 0).mean()) if ntr else 0.0
        kw = kospi[(kospi.index >= w0) & (kospi.index <= w1)]
        kret = float(kw.iloc[-1] / kw.iloc[0] - 1.0) if len(kw) >= 2 else float("nan")
        alpha = pnl - kret if not math.isnan(kret) else float("nan")
        if pnl > 0:
            pos_cnt += 1
        print(f"{name:<8} {sh:>8.3f} {pnl:>+9.1%} {dd:>8.1%} "
              f"{ntr:>5} {hit:>6.0%} {kret:>+9.1%} {alpha:>+9.1%}")
        rows_out.append(dict(window=name, sharpe=sh, pnl=pnl, maxdd=dd,
                             ntr=ntr, hit=hit, kospi=kret, alpha=alpha))

    n_win = len(rows_out)
    pos_alpha = sum(1 for r in rows_out if not math.isnan(r["alpha"]) and r["alpha"] > 0)
    print(f"\n[summary] positive-pnl windows: {pos_cnt}/{n_win}  "
          f"positive-alpha windows: {pos_alpha}/{n_win}")
    shs = [r["sharpe"] for r in rows_out]
    print(f"[summary] per-window sharpe: min={min(shs):.2f} "
          f"median={float(np.median(shs)):.2f} max={max(shs):.2f}")
    # 약세장(2022) 윈도우 별도 강조.
    bear = [r for r in rows_out if r["window"].startswith("2022")]
    if bear:
        print("[bear-2022] " + "  ".join(
            f"{r['window']}: sharpe={r['sharpe']:.2f} pnl={r['pnl']:+.1%} "
            f"alpha={r['alpha']:+.1%}" for r in bear))


if __name__ == "__main__":
    main()
