"""Lynch One Up on Wall Street 일봉 백테스트 (펀더멘털 단독 진입).

usage:
  python scripts/run_lynch_one_up.py --variant A --all-modes
  python scripts/run_lynch_one_up.py --variant B --mode single --rule fast_grower

데이터: daily_prices (adj_factor 적용 수정주가)
universe: financial_statements DISTINCT stock_code (~131, 전부 일봉 보유)
재무: point-in-time fund 조인 (effective_date=report_date+105d ≤ 거래일, YoY net_income 성장)
청산: Variant A (sl 12% / tp 50% / mh 120, trail 없음) 또는 B (sl 8% / tp 12% / mh 20)

⚠️ universe 교체로 이전 7권(top_volume:50)과 책간 비교성 깨짐 — 리포트에 명시할 것.
⚠️ 반드시 RoboTrader_template/ cwd 에서 실행 (상대경로 reports/...).
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.lynch_one_up.rules import ALL_RULES
from strategies.books.lynch_one_up.strategy import BOOK_META, build_strategy

LOG = logging.getLogger("lynch_one_up")

VARIANT_PARAMS = {
    "A": dict(stop_loss_pct=0.12, take_profit_pct=0.50, max_hold_bars=120, trail_ma=None),
    "B": dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20, trail_ma=None),
}

# 재무 컬럼 (financial_statements)
_FS_NUM_COLS = [
    "per", "pbr", "roe", "debt_ratio", "net_margin", "operating_margin",
    "net_income", "operating_profit", "revenue",
]

LAG_DAYS = 105       # 한국 사업보고서 공시 지연 → effective_date = report_date + 105d
PRIOR_LO_DAYS = 400  # fs_prior 후보: report_date-400d ~ report_date-330d (≈ -365d YoY)
PRIOR_HI_DAYS = 330
G_NI_CAP = 300.0     # |성장률|>300% 캡 (작은 분모 폭발 방지)


def _load_fundamentals_universe() -> List[str]:
    """financial_statements의 DISTINCT stock_code (~131, 전부 일봉 보유)."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT stock_code FROM financial_statements ORDER BY stock_code")
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _load_daily_adj(stock_codes: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """종목별 daily_prices (adj_factor 적용 수정주가) 로드."""
    # 일봉 SSOT=robotrader_quant. 펀더멘털/유니버스(financial_statements)는 robotrader 유지.
    from scripts.book_param_multiverse import _quant_daily_connection
    out: Dict[str, pd.DataFrame] = {}
    with _quant_daily_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, high, low, close, volume, adj_factor
                FROM daily_prices
                WHERE stock_code = %s
                  AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start, end))
            rows = cur.fetchall()
            if not rows or len(rows) < 30:
                continue
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "adj_factor"])
            df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
            df = df.dropna(subset=["date"])
            if len(df) < 30:
                continue
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            # quant close 는 이미 분할조정된 연속 시세 → adj_factor 곱하지 않음(곱하면 분할일 가짜 절벽).
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    return out


def _load_fundamentals_timeseries(stock_codes: List[str]) -> Dict[str, List[dict]]:
    """종목별 재무 시계열 로드.

    Returns:
        dict[code] -> report_date ASC 정렬된 row dict 리스트.
        report_date 는 date 로 파싱, 숫자 컬럼은 float (NULL 은 None 유지).
    """
    from db.connection import DatabaseConnection
    out: Dict[str, List[dict]] = {}
    cols = ", ".join(["report_date"] + _FS_NUM_COLS)
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute(f"""
                SELECT {cols}
                FROM financial_statements
                WHERE stock_code = %s
                ORDER BY report_date ASC
            """, (code,))
            rows = cur.fetchall()
            if not rows:
                continue
            parsed: List[dict] = []
            for r in rows:
                rd_raw = r[0]
                rd = pd.to_datetime(rd_raw, errors="coerce")
                if pd.isna(rd):
                    continue
                rec: dict = {"report_date": rd.date()}
                for j, col in enumerate(_FS_NUM_COLS, start=1):
                    val = r[j]
                    if val is None:
                        rec[col] = None
                    else:
                        try:
                            fv = float(val)
                            rec[col] = None if math.isnan(fv) else fv
                        except (TypeError, ValueError):
                            rec[col] = None
                parsed.append(rec)
            parsed.sort(key=lambda x: x["report_date"])
            if parsed:
                out[code] = parsed
    return out


def _find_prior(fs_rows: List[dict], curr_rd: date) -> Optional[dict]:
    """fs_curr.report_date 기준 [-400d, -330d] 창에서 -365d 에 가장 가까운 prior 행."""
    lo = curr_rd - timedelta(days=PRIOR_LO_DAYS)
    hi = curr_rd - timedelta(days=PRIOR_HI_DAYS)
    target = curr_rd - timedelta(days=365)
    best: Optional[dict] = None
    best_dist: Optional[int] = None
    for row in fs_rows:
        rd = row["report_date"]
        if lo <= rd <= hi:
            dist = abs((rd - target).days)
            if best_dist is None or dist < best_dist:
                best = row
                best_dist = dist
    return best


def _build_fund_by_idx(df: pd.DataFrame, fs_rows: List[dict]) -> List[Optional[dict]]:
    """df 각 행에 대응하는 point-in-time fund dict 리스트 (no-lookahead).

    각 거래일 D 에 대해:
      effective_date(row) = report_date + 105d
      fs_curr  = effective_date ≤ D 인 행 中 report_date 최대
      fs_prior = report_date 가 [fs_curr.rd-400d, fs_curr.rd-330d] 인 -365d 근접 행
      g_ni     = (curr.ni - prior.ni)/abs(prior.ni)*100, 가드 위반 시 None
    fs_curr 없으면 그 봉 fund=None.
    """
    n = len(df)
    if not fs_rows:
        return [None] * n

    # 사전계산: report_date ASC 이므로 effective_date 도 ASC. 포인터로 전진 스캔.
    eff = [(row["report_date"] + timedelta(days=LAG_DAYS), row) for row in fs_rows]
    eff.sort(key=lambda x: x[0])

    fund_by_idx: List[Optional[dict]] = []
    ptr = 0
    curr: Optional[dict] = None
    last_curr_rd: Optional[date] = None
    cached_fund: Optional[dict] = None

    for i in range(n):
        d = df.iloc[i]["datetime"]
        d = d.date() if hasattr(d, "date") else pd.to_datetime(d).date()

        # effective_date ≤ D 인 행들을 소비하며 가장 최신(report_date 최대) 선택
        while ptr < len(eff) and eff[ptr][0] <= d:
            cand = eff[ptr][1]
            if curr is None or cand["report_date"] >= curr["report_date"]:
                curr = cand
            ptr += 1

        if curr is None:
            fund_by_idx.append(None)
            continue

        # fs_curr 가 바뀌었을 때만 fund 재계산 (봉마다 동일 분기 반복)
        if last_curr_rd != curr["report_date"]:
            last_curr_rd = curr["report_date"]
            prior = _find_prior(fs_rows, curr["report_date"])

            curr_ni = curr.get("net_income")
            prior_ni = prior.get("net_income") if prior else None

            g_ni: Optional[float] = None
            if (
                prior_ni is not None and prior_ni > 0
                and curr_ni is not None and curr_ni > 0
            ):
                g = (curr_ni - prior_ni) / abs(prior_ni) * 100.0
                if abs(g) <= G_NI_CAP:
                    g_ni = g

            cached_fund = {
                "per": curr.get("per"),
                "pbr": curr.get("pbr"),
                "roe": curr.get("roe"),
                "debt_ratio": curr.get("debt_ratio"),
                "net_margin": curr.get("net_margin"),
                "operating_margin": curr.get("operating_margin"),
                "net_income": curr_ni,
                "prior_net_income": prior_ni if prior else None,
                "g_ni": g_ni,
            }

        fund_by_idx.append(cached_fund)

    return fund_by_idx


def simulate_one_stock(
    code: str,
    df: pd.DataFrame,
    fund_by_idx: List[Optional[dict]],
    strategy,
    stop_loss_pct: float,
    take_profit_pct: float,
    max_hold_bars: int,
    trail_ma: Optional[int],
    warmup_bars: int = 20,
    commission_rate: float = 0.00015,  # 수수료 매매 각각 (양방향)
    tax_rate: float = 0.0018,           # 거래세 매도 시
    slippage_rate: float = 0.001,       # 슬리피지 단방향
    # → 왕복 ≈ commission×2 + tax + slippage×2 = 0.41%
    initial_capital: float = 10_000_000,
) -> dict:
    """단일 종목 일봉 시뮬레이션. 신호 → 다음 봉 시가 매수 → sl/tp/mh/trail 청산."""
    from strategies.base import SignalType
    n = len(df)
    if n < warmup_bars + 2:
        return {"n_trades": 0, "trades": [], "equity_curve": [initial_capital]}

    df = df.reset_index(drop=True).copy()
    cash = initial_capital
    position: Optional[dict] = None
    trades: List[dict] = []
    equity: List[float] = []

    for i in range(warmup_bars, n - 1):
        bar_now = df.iloc[i]
        bar_next = df.iloc[i + 1]

        # 청산 체크
        if position is not None:
            entry_price = position["entry_price"]
            cur_close = float(bar_now["close"])
            ret = (cur_close - entry_price) / entry_price
            hold_bars = i - position["entry_idx"]
            exit_reason = None
            if ret <= -stop_loss_pct:
                exit_reason = "stop_loss"
            elif ret >= take_profit_pct:
                exit_reason = "take_profit"
            elif hold_bars >= max_hold_bars:
                exit_reason = "max_hold"
            elif trail_ma is not None and i >= trail_ma:
                ma = df["close"].iloc[i - trail_ma + 1:i + 1].mean()
                if cur_close < ma:
                    exit_reason = "trail_ma"
            if exit_reason is not None:
                fill = float(bar_next["open"]) * (1 - slippage_rate)
                proceeds = position["qty"] * fill
                fee = proceeds * (commission_rate + tax_rate)
                cash += proceeds - fee
                pnl = (fill - entry_price) / entry_price
                trades.append({
                    "stock_code": code, "side": "sell", "idx": i + 1,
                    "datetime": str(bar_next["datetime"]), "price": fill,
                    "qty": position["qty"], "reason": exit_reason,
                    "entry_price": entry_price, "pnl_pct": pnl,
                })
                position = None

        # 신호 평가
        if position is None:
            window = df.iloc[: i + 1]
            fund = fund_by_idx[i] if i < len(fund_by_idx) else None
            ctx_extra = {"fund": fund}
            # fund 를 ctx_extra로 BookStrategy에 전달; rule은 ctx['fund']로 읽는다.
            signal = strategy.generate_signal_with_extra_ctx(code, window, "daily", ctx_extra)
            if signal is not None and signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                fill = float(bar_next["open"]) * (1 + slippage_rate)
                qty = int((cash * 0.99) // fill)
                if qty > 0:
                    cost = qty * fill
                    fee = cost * commission_rate
                    cash -= cost + fee
                    position = {"entry_idx": i + 1, "entry_price": fill, "qty": qty}
                    trades.append({
                        "stock_code": code, "side": "buy", "idx": i + 1,
                        "datetime": str(bar_next["datetime"]), "price": fill,
                        "qty": qty, "reason": ",".join(signal.reasons or ["signal"]),
                        "entry_price": fill, "pnl_pct": 0.0,
                    })

        mtm = cash
        if position is not None:
            mtm += position["qty"] * float(bar_now["close"])
        equity.append(mtm)

    # 강제 청산
    if position is not None:
        last = df.iloc[-1]
        fill = float(last["close"]) * (1 - slippage_rate)
        proceeds = position["qty"] * fill
        fee = proceeds * (commission_rate + tax_rate)
        cash += proceeds - fee
        entry_price = position["entry_price"]
        trades.append({
            "stock_code": code, "side": "sell", "idx": n - 1,
            "datetime": str(last["datetime"]), "price": fill,
            "qty": position["qty"], "reason": "forced_close",
            "entry_price": entry_price,
            "pnl_pct": (fill - entry_price) / entry_price,
        })
        equity.append(cash)

    return {"n_trades": sum(1 for t in trades if t["side"] == "sell"), "trades": trades, "equity_curve": equity}


def _compute_metrics(initial: float, equity: List[float], trades: List[dict]) -> dict:
    if not equity:
        return dict(n_trades=0, pnl_pct=0.0, sharpe=0.0, calmar=0.0, max_dd=0.0,
                    hit_rate=0.0, avg_hold_days=0.0)
    eq = np.array(equity, dtype=float)
    pnl_pct = (eq[-1] - initial) / initial
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min()) if len(dd) else 0.0
    calmar = float(pnl_pct / max_dd) if max_dd > 1e-9 else 0.0
    sells = [t for t in trades if t["side"] == "sell"]
    wins = sum(1 for t in sells if t["pnl_pct"] > 0)
    hit = wins / len(sells) if sells else 0.0
    holds: List[int] = []
    buy_idx: Optional[int] = None
    for t in trades:
        if t["side"] == "buy":
            buy_idx = t["idx"]
        elif t["side"] == "sell" and buy_idx is not None:
            holds.append(t["idx"] - buy_idx)
            buy_idx = None
    avg_hold = float(np.mean(holds)) if holds else 0.0
    return dict(n_trades=len(sells), pnl_pct=pnl_pct, sharpe=sharpe, calmar=calmar,
                max_dd=max_dd, hit_rate=hit, avg_hold_days=avg_hold)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", required=True, choices=["A", "B"])
    p.add_argument("--mode", default=None, choices=["single", "all_AND"])
    p.add_argument("--rule", default=None)
    p.add_argument("--all-modes", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--top-n", type=int, default=50, help="(미사용 — 호환용)")
    p.add_argument("--start", default=None, help="YYYY-MM-DD (기본: daily_prices 최소 날짜)")
    p.add_argument("--end", default=None, help="YYYY-MM-DD (기본: daily_prices 최대 날짜)")
    p.add_argument("--reports-dir", default="reports/books_research/lynch_one_up")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.all_modes and args.mode is not None:
        p.error("--all-modes 와 --mode 는 동시 사용 불가")
    if not args.all_modes and args.mode is None:
        p.error("--mode 또는 --all-modes 둘 중 하나 필수")

    # 기간 자동
    if args.start is None or args.end is None:
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MIN(date), MAX(date) FROM daily_prices")
            mn, mx = cur.fetchone()
        args.start = args.start or str(mn)
        args.end = args.end or str(mx)
    LOG.info(f"period: {args.start} ~ {args.end}")

    universe = _load_fundamentals_universe()
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    data = _load_daily_adj(universe, args.start, args.end)
    LOG.info(f"loaded data for {len(data)} stocks")
    if not data:
        LOG.error("no data — aborting")
        return

    fs_ts = _load_fundamentals_timeseries(list(data.keys()))
    LOG.info(f"loaded fundamentals for {len(fs_ts)} stocks")

    # 종목별 point-in-time fund 사전계산 (한 번만)
    fund_by_idx_map: Dict[str, List[Optional[dict]]] = {}
    for code, df in data.items():
        fund_by_idx_map[code] = _build_fund_by_idx(df, fs_ts.get(code, []))

    params = VARIANT_PARAMS[args.variant]
    rule_names = [cls().name for cls in ALL_RULES]
    combos = [("single", n) for n in rule_names] + [("all_AND", None)] if args.all_modes else [(args.mode, args.rule)]

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = Path("reports/books_research/leaderboard.parquet")

    from backtest.book_backtester import append_leaderboard

    for mode, rule_name in combos:
        strategy = build_strategy(mode=mode, target_rule=rule_name)
        per_stock_pnl = []
        all_trades = []
        per_stock_metrics = []
        for code, df in data.items():
            res = simulate_one_stock(
                code=code, df=df, fund_by_idx=fund_by_idx_map[code], strategy=strategy,
                stop_loss_pct=params["stop_loss_pct"],
                take_profit_pct=params["take_profit_pct"],
                max_hold_bars=params["max_hold_bars"],
                trail_ma=params["trail_ma"],
                warmup_bars=20,
            )
            metrics = _compute_metrics(10_000_000, res["equity_curve"], res["trades"])
            per_stock_metrics.append(metrics)
            per_stock_pnl.append(metrics["pnl_pct"])
            for t in res["trades"]:
                all_trades.append(t)

        n_stocks = len(per_stock_metrics)
        agg = {
            "n_stocks": n_stocks,
            "n_trades": int(sum(m["n_trades"] for m in per_stock_metrics)),
            "pnl_pct": float(np.mean(per_stock_pnl)) if per_stock_pnl else 0.0,
            "sharpe": float(np.mean([m["sharpe"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "calmar": float(np.mean([m["calmar"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "max_dd": float(np.mean([m["max_dd"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "hit_rate": float(np.mean([m["hit_rate"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
            "avg_hold_days": float(np.mean([m["avg_hold_days"] for m in per_stock_metrics])) if per_stock_metrics else 0.0,
        }
        label = rule_name if mode == "single" else mode
        LOG.info(f"[variant={args.variant} {mode}/{label}] n_stocks={n_stocks} n_trades={agg['n_trades']} "
                 f"pnl={agg['pnl_pct']:.4%} sharpe={agg['sharpe']:.2f}")

        out_file = reports_dir / f"results_variant{args.variant}_{mode}_{label}.parquet"
        if all_trades:
            pd.DataFrame(all_trades).to_parquet(out_file, index=False)

        append_leaderboard(
            path=leaderboard_path,
            row={
                "book_id": "lynch_one_up",
                "book_name": BOOK_META["name"],
                "period": "daily_full",
                "rule_combo": label,
                "mode": mode,
                "variant": args.variant,
                "universe": f"fundamentals:{len(universe)}",
                "stop_loss_pct": params["stop_loss_pct"],
                "take_profit_pct": params["take_profit_pct"],
                "max_hold_bars": params["max_hold_bars"],
                "n_stocks": agg["n_stocks"],
                "n_trades": agg["n_trades"],
                "pnl_pct": agg["pnl_pct"],
                "sharpe": agg["sharpe"],
                "calmar": agg["calmar"],
                "max_dd_pct": agg["max_dd"],
                "hit_rate": agg["hit_rate"],
                "avg_hold_bars": agg["avg_hold_days"],
            },
        )


if __name__ == "__main__":
    main()
