"""MULTIVERSE4 공통 아티팩트 — 7전략 풀기간 연속 백테스트 → daily_returns 내보내기.

목적(사장님 지시 "안 해본 멀티버스"): 7개 페이퍼 전략의 date-indexed daily_returns 를
단일 규약 CSV 로 산출해, 지금까지 한 번도 안 해본 축 —
  ①전략간 상관·합성 포트폴리오 ②7전략 워크포워드 매트릭스 ⑤부트스트랩 CI —
을 multiverse4_portfolio_analysis.py 가 재백테스트 없이 파생하게 한다.
④거래비용 민감도는 본 스크립트의 --commission/--tax/--slippage 재실행으로 측정.

설계(walkforward_envelope.py 패턴 일반화):
  풀기간(quant 일봉 min~max) 1회 연속 백테스트 → 각 진입일이 자연히 워밍업 히스토리
  확보(naive 윈도우 분할의 워밍업 아티팩트 회피) → daily_returns 를 캘린더로 분해.

라이브 정합(전부 strategies/<name>/config.yaml 의 라이브 값, 무수정 측정 전용):
  elder    : touch_band 1.02, K20, sl8/tp30/mh100 + EMA13 trail + trend_flip (실청산)
  envelope : 책 A~I 기본값, K5, sl8/tp10/mh10 (라이브 청산=고정 sl/tp/mh → 어댑터 정확일치)
  유지윤    : breakout_prev_high(high_window=15), K5, sl10/tp10/mh10 (정확일치)
  minervini: volume_dryup(RS ctx 주입), K3, sl8/tp12/mh20 (정확일치)
  ma20     : daily_ma20_pullback, K5, sl8/tp10/mh50 + MA20 trail (실청산)
  ma5      : ma5_pullback, K5, sl3/tp15/mh30 + MA5 trail (실청산)
  rs_leader: RSLeaderRule + rs_rank(0.7, n=120) 횡단면 필터, K10, sl8/mh30 + MA20 trail
             (tp99=무효. 유니버스 top300 — 검증 스파이크 정본과 동일 스케일)

데이터: robotrader_quant SSOT (book_param_multiverse 로더 재사용, adj_factor 미적용).
비용: scripts.exit_multiverse.portfolio_sim 상수(수수료 0.015%·거래세 0.18%·슬리피지 0.10%).

usage:
  python scripts/multiverse4_returns_export.py --out reports/books_research/_mv4_returns
  python scripts/multiverse4_returns_export.py --strategies elder_ema_pullback --smoke
  python scripts/multiverse4_returns_export.py --slippage 0.003 --out D:/tmp/mv4_cost30bp
"""
from __future__ import annotations

import argparse
import contextlib
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from scripts.book_param_multiverse import (  # noqa: E402
    _build_strategy,
    _daily_minmax_dates,
    _load_book,
    _load_daily_adj,
    _load_top_volume_daily,
)
from scripts.book_portfolio_multiverse import (  # noqa: E402
    _SLTPMHAdapter,
    _load_kospi_close,
    _precompute_signals,
)
from scripts.entry_filters import apply_entry_filter  # noqa: E402
from scripts.exit_multiverse import adapters as xadapters  # noqa: E402
from scripts.exit_multiverse import signals as xsignals  # noqa: E402
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402
from scripts.rs_leader.exit_adapter import MA20TrailExitAdapter  # noqa: E402
from scripts.rs_leader.rule import RSLeaderRule  # noqa: E402

INITIAL = 10_000_000.0       # 라이브 가상매매 = 전략당 독립 1천만 (VIRTUAL_CAPITAL_PER_STRATEGY)
# ★종목당 매수금액 — 라이브 페이퍼의 실제 체결 사이징은 yaml max_per_stock_amount(300만)가
#   아니라 virtual_trading_manager.get_max_quantity 의 min(virtual_investment_amount=100만,
#   전략 budget) 이다(core/virtual_trading_manager.py:68,390). 라이브 충실 = 1_000_000.
MAX_PER_STOCK = 1_000_000.0


# ---------------------------------------------------------------------------
# 전략 스펙 — 신호생성/어댑터/청산파라미터/K/유니버스 캡슐화
# ---------------------------------------------------------------------------

@dataclass
class StrategySpec:
    name: str
    warmup: int
    K: int
    params: dict
    adapter: object
    top_n: int = 50
    # build_signals(data) -> {code: [bar_idx...]}  (no-lookahead 캐시)
    build_signals: Callable[[Dict[str, pd.DataFrame]], Dict[str, List[int]]] = field(repr=False, default=None)


def _sig_elder(data):
    from strategies.books.elder_triple_screen.rules import rule_triple_screen_ema_pullback
    # 라이브 touch_band=1.02 (config.yaml, 2026-06-02 멀티버스 검증값). 룰 기본 1.01 아님.
    strat = _build_strategy(rule_triple_screen_ema_pullback, "triple_screen_ema_pullback",
                            {"touch_band": 1.02})
    return _precompute_signals(data, strat, 70, "daily")


def _sig_envelope(data):
    _sm, rules_mod = _load_book("trading_strategy_book", "rules")
    strat = _build_strategy(getattr(rules_mod, "rule_envelope_200d_high"),
                            "envelope_200d_high", {})
    return _precompute_signals(data, strat, 42, "daily")


def _sig_dt3(data):
    _sm, rules_mod = _load_book("daytrading_3methods", "rules")
    # 라이브 high_window=15 (config.yaml, 커밋 32b42ee 멀티버스 강건값. 룰 기본 20 아님).
    strat = _build_strategy(getattr(rules_mod, "rule_breakout_prev_high"),
                            "breakout_prev_high", {"high_window": 15})
    return _precompute_signals(data, strat, 25, "daily")


def _sig_minervini(data):
    ad = xadapters.ADAPTERS["minervini_volume_dryup"]
    strat = ad.build_strategy()
    ctx_fn = ad.make_extra_ctx_fn(data)  # 횡단면 RS 백분위(12w) 주입
    return xsignals.precompute_entry_signals(data, strat, 60, ctx_fn)


def _sig_ma20(data):
    strat = xadapters.ADAPTERS["book_pullback_ma20"].build_strategy()
    return _precompute_signals(data, strat, 35, "daily")


def _sig_ma5(data):
    strat = xadapters.ADAPTERS["book_pullback_ma5"].build_strategy()
    return _precompute_signals(data, strat, 25, "daily")


def _sig_rs_leader(data):
    cache = _precompute_signals(data, RSLeaderRule(ma_short=20, ma_long=60, abs_lb=60),
                                65, "daily")
    # 횡단면 RS 상위 필터 — 검증 스파이크 정본(threshold 0.7, n=120) = 라이브 스크리너
    # topK(rs_lb=120 수익률 정렬)의 백분위 근사.
    return apply_entry_filter(data, cache, filt="rs_rank", threshold=0.7, n=120)


SPECS: Dict[str, StrategySpec] = {
    "elder_ema_pullback": StrategySpec(
        name="elder_ema_pullback", warmup=70, K=20,
        params=dict(stop_loss_pct=0.08, take_profit_pct=0.30, max_hold_bars=100,
                    trail_ema=13, trend_flip_exit=True),
        adapter=xadapters.ADAPTERS["elder_ema_pullback"],  # stop 진입 + 실청산(elder)
        build_signals=_sig_elder),
    "book_envelope_200d": StrategySpec(
        name="book_envelope_200d", warmup=42, K=5,
        params=dict(stop_loss_pct=0.08, take_profit_pct=0.10, max_hold_bars=10),
        adapter=_SLTPMHAdapter(),
        build_signals=_sig_envelope),
    "daytrading_3methods_breakout": StrategySpec(
        name="daytrading_3methods_breakout", warmup=25, K=5,
        params=dict(stop_loss_pct=0.10, take_profit_pct=0.10, max_hold_bars=10),
        adapter=_SLTPMHAdapter(),
        build_signals=_sig_dt3),
    "minervini_volume_dryup": StrategySpec(
        name="minervini_volume_dryup", warmup=60, K=3,
        params=dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20),
        adapter=xadapters.ADAPTERS["minervini_volume_dryup"],
        build_signals=_sig_minervini),
    "book_pullback_ma20": StrategySpec(
        name="book_pullback_ma20", warmup=35, K=5,
        params=dict(stop_loss_pct=0.08, take_profit_pct=0.10, max_hold_bars=50,
                    trail_ma=20),
        adapter=xadapters.ADAPTERS["book_pullback_ma20"],
        build_signals=_sig_ma20),
    "book_pullback_ma5": StrategySpec(
        name="book_pullback_ma5", warmup=25, K=5,
        params=dict(stop_loss_pct=0.03, take_profit_pct=0.15, max_hold_bars=30,
                    trail_ma=5),
        adapter=xadapters.ADAPTERS["book_pullback_ma5"],
        build_signals=_sig_ma5),
    "rs_leader": StrategySpec(
        name="rs_leader", warmup=65, K=10, top_n=300,
        params=dict(stop_loss_pct=0.08, take_profit_pct=99.0, max_hold_bars=30),
        adapter=MA20TrailExitAdapter(ma=20),
        build_signals=_sig_rs_leader),
}


# ---------------------------------------------------------------------------
# 비용 패치 (축4) — portfolio_sim 모듈 상수를 일시 교체 (라이브/타파일 무수정)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _patch_costs(commission: Optional[float] = None, tax: Optional[float] = None,
                 slippage: Optional[float] = None):
    import scripts.exit_multiverse.portfolio_sim as ps
    saved = (ps.COMMISSION_RATE, ps.TAX_RATE, ps.SLIPPAGE_RATE)
    try:
        if commission is not None:
            ps.COMMISSION_RATE = commission
        if tax is not None:
            ps.TAX_RATE = tax
        if slippage is not None:
            ps.SLIPPAGE_RATE = slippage
        yield
    finally:
        ps.COMMISSION_RATE, ps.TAX_RATE, ps.SLIPPAGE_RATE = saved


# ---------------------------------------------------------------------------
# 메트릭
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def run_one(spec: StrategySpec, data: Dict[str, pd.DataFrame],
            turnover: Dict[str, float],
            max_per_stock: float = MAX_PER_STOCK) -> dict:
    cache = spec.build_signals(data)
    n_sig = sum(len(v) for v in cache.values())
    res = run_portfolio(data=data, signal_cache=cache, adapter=spec.adapter,
                        params=spec.params, turnover=turnover,
                        initial_capital=INITIAL, max_positions=spec.K,
                        max_per_stock=max_per_stock)
    dr: pd.Series = res["daily_returns"]
    dr.index = pd.to_datetime(dr.index)
    dr = dr.sort_index()
    eq = INITIAL * (1.0 + dr).cumprod()
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    return dict(daily_returns=dr, equity=eq, n_signals=n_sig, n_trades=len(sells),
                sharpe=_sharpe(dr.to_numpy()),
                pnl=float(eq.iloc[-1] / INITIAL - 1.0) if len(eq) else 0.0,
                maxdd=_maxdd(eq.to_numpy()),
                trades=res["trades"])


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "books_research" / "_mv4_returns"))
    ap.add_argument("--strategies", nargs="*", default=list(SPECS.keys()))
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--smoke", action="store_true", help="top_n 20·rs_leader 50 으로 축소")
    ap.add_argument("--commission", type=float, default=None)
    ap.add_argument("--tax", type=float, default=None)
    ap.add_argument("--slippage", type=float, default=None)
    ap.add_argument("--max-per-stock", type=float, default=MAX_PER_STOCK,
                    help="종목당 매수금액 (라이브=100만, yaml 표기=300만)")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    mn, mx = _daily_minmax_dates()
    start = args.start or mn
    end = args.end or mx
    print(f"[period] {start} ~ {end}")

    # 유니버스/일봉은 top_n 별로 1회 로드 (50: 6전략 공유, 300: rs_leader)
    data_by_topn: Dict[int, Dict[str, pd.DataFrame]] = {}
    turnover_by_topn: Dict[int, Dict[str, float]] = {}

    def _get_data(top_n: int):
        if top_n not in data_by_topn:
            uni = _load_top_volume_daily(start, end, top_n)
            d = _load_daily_adj(uni, start, end)
            data_by_topn[top_n] = d
            turnover_by_topn[top_n] = {c: float((df["close"] * df["volume"]).sum())
                                       for c, df in d.items()}
            print(f"[load] top_n={top_n} universe={len(uni)} loaded={len(d)}")
        return data_by_topn[top_n], turnover_by_topn[top_n]

    summary_rows = []
    with _patch_costs(args.commission, args.tax, args.slippage):
        for name in args.strategies:
            spec = SPECS[name]
            top_n = spec.top_n
            if args.smoke:
                top_n = 20 if spec.top_n == 50 else 50
            data, turnover = _get_data(top_n)
            print(f"[run] {name} (K={spec.K}, top_n={top_n}, "
                  f"per_stock={args.max_per_stock:,.0f}) ...")
            r = run_one(spec, data, turnover, max_per_stock=args.max_per_stock)
            df_out = pd.DataFrame({
                "date": r["daily_returns"].index.strftime("%Y-%m-%d"),
                "daily_return": r["daily_returns"].to_numpy(),
                "equity": r["equity"].to_numpy(),
            })
            df_out.to_csv(out / f"{name}.csv", index=False)
            pd.DataFrame(r["trades"]).to_csv(out / f"{name}_trades.csv", index=False)
            print(f"[done] {name}: signals={r['n_signals']} trades={r['n_trades']} "
                  f"sharpe={r['sharpe']:.2f} pnl={r['pnl']:+.1%} maxdd={r['maxdd']:.1%}")
            summary_rows.append(dict(strategy=name, top_n=top_n, K=spec.K,
                                     n_signals=r["n_signals"], n_trades=r["n_trades"],
                                     sharpe=round(r["sharpe"], 3), pnl=round(r["pnl"], 4),
                                     maxdd=round(r["maxdd"], 4)))

    # KOSPI 벤치마크 (상관·알파용)
    kospi = _load_kospi_close(start, end)
    kospi.index = pd.to_datetime(kospi.index)
    kospi = kospi.sort_index()
    kr = kospi.pct_change().dropna()
    pd.DataFrame({"date": kr.index.strftime("%Y-%m-%d"), "daily_return": kr.to_numpy(),
                  "equity": (INITIAL * (1.0 + kr).cumprod()).to_numpy()}
                 ).to_csv(out / "KOSPI.csv", index=False)

    pd.DataFrame(summary_rows).to_csv(out / "summary.tsv", sep="\t", index=False)
    print(f"[out] {out}")


if __name__ == "__main__":
    main()
