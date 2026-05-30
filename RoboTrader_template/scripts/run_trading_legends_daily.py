"""『트레이딩의 전설』(키움영웅전 9인 트레이더) — 일봉(daily) 백테스트.

일봉 단위로 정량화한 6종 기법을 daily_prices 로 검증.
run_haru_silijeon_daily.py 패턴과 1:1 동일(시뮬·메트릭·leaderboard append 공유).

usage:
  python scripts/run_trading_legends_daily.py --variant A --all-modes
  python scripts/run_trading_legends_daily.py --variant O --mode single --rule limit_up_follow
  python scripts/run_trading_legends_daily.py --variant O --mode single --rule close_momentum_breakout
  # 파일럿(짧은 기간·단일룰):
  python scripts/run_trading_legends_daily.py --variant O --mode single \
      --rule limit_up_follow --start 2024-01-01 --end 2024-12-31 --limit 30

데이터: daily_prices (OHLC adj_factor 적용 수정주가)
universe: top_volume:50 (일평균 거래대금 상위 50)  — 기존 일봉책(haru/elder)과 동일
청산 variant:
  Variant A (스윙 표준): sl 8% / tp off(99%) / mh 100 / trail_ma=룰별 기본
  Variant B (단기 회전): sl 8% / tp 12% / mh 20 / trail_ma=None
  Variant O (오버나이트): sl 5% / tp off(99%) / mh 1 / trail_ma=None
  ※ limit_up_follow(상따)는 책 명시 -3% 타이트 손절 → variant 무관 sl=0.03 강제 override.
  오버나이트 성격 룰(close_momentum_breakout, limit_up_follow)은 variant O 권장이나 A/B/O 모두 실행 가능.
no-lookahead: rule 은 df[:i+1]만, 체결은 다음 봉 시가. 거래비용 haru/elder/문병로와 동일.

⚠️ 반드시 RoboTrader_template/ cwd 에서 실행 (상대경로 reports/...).
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.trading_legends.rules_daily import ALL_DAILY_RULES
from strategies.books.trading_legends.strategy_daily import BOOK_META_DAILY, build_strategy_daily

LOG = logging.getLogger("trading_legends_daily")

VARIANT_PARAMS = {
    # A: 스윙 표준 — tp off(추세 보유), trail_ma 룰별, mh 100
    "A": dict(stop_loss_pct=0.08, take_profit_pct=0.99, max_hold_bars=100, use_trail=True),
    # B: 단기 회전 — tp 12% 고정, trail 없음, mh 20
    "B": dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20, use_trail=False),
    # O: 오버나이트 — sl 5%, tp off, mh 1(익일 청산), trail 없음
    "O": dict(stop_loss_pct=0.05, take_profit_pct=0.99, max_hold_bars=1, use_trail=False),
}

# 상따(limit_up_follow) 책 명시 -3% 타이트 손절 — variant 무관 강제 override
RULE_SL_OVERRIDE = {
    "limit_up_follow": 0.03,
}

# 룰별 기본 trail MA(일봉 이평선 이탈 시 매도). variant A use_trail=True 일 때만 적용.
# all_AND 모드는 진입 이평이 혼재되므로 보수적으로 20일선 사용.
RULE_TRAIL_MA = {
    "close_momentum_breakout": 5,
    "new_high_breakout": 20,
    "prev_limitup_pullback": 10,
    "ma5_pullback": 5,
    "bottom_first_bull": 20,
    "limit_up_follow": 5,
}
DEFAULT_TRAIL_MA = 20


def _load_top_volume_universe(start: str, end: str, top_n: int = 50) -> List[str]:
    """daily_prices의 (close*volume) 합계 상위 N종목."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
            GROUP BY stock_code
            ORDER BY turnover DESC
            LIMIT %s
        """, (start, end, top_n))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _load_daily_adj(stock_codes: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """종목별 daily_prices (adj_factor 적용 수정주가) 로드."""
    from db.connection import DatabaseConnection
    out: Dict[str, pd.DataFrame] = {}
    with DatabaseConnection.get_connection() as conn:
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
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "high", "low", "close", "volume", "adj_factor"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["adj_factor"] = df["adj_factor"].fillna(1.0)
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col] * df["adj_factor"]
            # 거래정지일 등 OHLC 결손 보정: close 유효 행은 open/high/low(<=0 or NaN)를 close로 채움.
            # close 자체가 0 이하/NaN인 완전 결손 행은 체결 불가 → 드롭.
            n_before = len(df)
            drop_mask = df["close"].isna() | (df["close"] <= 0)
            n_dropped = int(drop_mask.sum())
            df = df[~drop_mask].copy()
            n_filled = 0
            for col in ["open", "high", "low"]:
                fill_mask = df[col].isna() | (df[col] <= 0)
                n_filled += int(fill_mask.sum())
                df.loc[fill_mask, col] = df.loc[fill_mask, "close"]
            if n_dropped or n_filled:
                LOG.info(f"[{code}] OHLC 보정: {n_filled}행 채움 / {n_dropped}행 드롭 (총 {n_before}행)")
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    return out


def simulate_one_stock(
    code: str,
    df: pd.DataFrame,
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
    """단일 종목 일봉 시뮬레이션. 신호 t → 다음 봉 시가 매수 → sl/tp/mh/trail_ma 청산.

    trail_ma 가 정수면 '종가 < N일 이평선' 시 청산(책 공통 '이평선 이탈 시 매도').
    no-lookahead: rule 은 df[:i+1]만, 체결 판정은 각 bar OHLC만.
    """
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
            elif trail_ma is not None and i + 1 >= trail_ma:
                ma = df["close"].iloc[i - trail_ma + 1:i + 1].mean()
                if pd.notna(ma) and cur_close < float(ma):
                    exit_reason = "trail_ma"
            if exit_reason is not None:
                raw_next_open = float(bar_next["open"])
                if raw_next_open <= 0:  # 다음 봉 시가 무효 → 청산 보류
                    exit_reason = None
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

        # 신호 평가 (무포지션일 때)
        if position is None:
            window = df.iloc[: i + 1]
            signal = strategy.generate_signal_with_extra_ctx(code, window, "daily", {})
            if signal is not None and signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                raw_next_open = float(bar_next["open"])
                fill = raw_next_open * (1 + slippage_rate)
                qty = int((cash * 0.99) // fill) if fill > 0 else 0
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
    if position is not None and float(df.iloc[-1]["close"]) > 0:
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


def _resolve_exit_params(variant: str, mode: str, rule_name: Optional[str]):
    """variant + 룰별 override 로 (sl, tp, mh, trail_ma) 확정."""
    params = VARIANT_PARAMS[variant]
    sl = params["stop_loss_pct"]
    tp = params["take_profit_pct"]
    mh = params["max_hold_bars"]
    # 상따 -3% 손절 override (single 모드에서 해당 룰일 때)
    if mode == "single" and rule_name in RULE_SL_OVERRIDE:
        sl = RULE_SL_OVERRIDE[rule_name]
    # trail MA
    trail = None
    if params["use_trail"]:
        if mode == "single" and rule_name in RULE_TRAIL_MA:
            trail = RULE_TRAIL_MA[rule_name]
        else:
            trail = DEFAULT_TRAIL_MA
    return sl, tp, mh, trail


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", required=True, choices=["A", "B", "O"])
    p.add_argument("--mode", default=None, choices=["single", "all_AND"])
    p.add_argument("--rule", default=None)
    p.add_argument("--all-modes", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--start", default=None, help="YYYY-MM-DD (기본: daily_prices 최소 날짜)")
    p.add_argument("--end", default=None, help="YYYY-MM-DD (기본: daily_prices 최대 날짜)")
    p.add_argument("--reports-dir", default="reports/books_research/trading_legends")
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

    universe = _load_top_volume_universe(args.start, args.end, args.top_n)
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    data = _load_daily_adj(universe, args.start, args.end)
    LOG.info(f"loaded data for {len(data)} stocks")
    if not data:
        LOG.error("no data — aborting")
        return

    rule_names = [cls().name for cls in ALL_DAILY_RULES]
    combos = [("single", n) for n in rule_names] + [("all_AND", None)] if args.all_modes else [(args.mode, args.rule)]

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = Path("reports/books_research/leaderboard.parquet")

    from backtest.book_backtester import append_leaderboard

    for mode, rule_name in combos:
        strategy = build_strategy_daily(mode=mode, target_rule=rule_name)
        sl, tp, mh, trail = _resolve_exit_params(args.variant, mode, rule_name)
        per_stock_pnl = []
        all_trades = []
        per_stock_metrics = []
        for code, df in data.items():
            res = simulate_one_stock(
                code=code, df=df, strategy=strategy,
                stop_loss_pct=sl, take_profit_pct=tp,
                max_hold_bars=mh, trail_ma=trail,
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
        LOG.info(f"[variant={args.variant} {mode}/{label}] sl={sl} tp={tp} mh={mh} trail_ma={trail} "
                 f"n_stocks={n_stocks} n_trades={agg['n_trades']} "
                 f"pnl={agg['pnl_pct']:.4%} sharpe={agg['sharpe']:.2f} hit={agg['hit_rate']:.2%}")

        out_file = reports_dir / f"results_variant{args.variant}_{mode}_{label}.parquet"
        if all_trades:
            pd.DataFrame(all_trades).to_parquet(out_file, index=False)

        append_leaderboard(
            path=leaderboard_path,
            row={
                "book_id": "trading_legends_daily",
                "book_name": BOOK_META_DAILY["name"],
                "period": "daily_full",
                "rule_combo": label,
                "mode": mode,
                "variant": args.variant,
                "universe": f"top_volume:{args.top_n}",
                "stop_loss_pct": sl,
                "take_profit_pct": tp,
                "max_hold_bars": mh,
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
