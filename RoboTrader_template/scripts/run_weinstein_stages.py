"""Weinstein Stage Analysis 주봉 백테스트.

usage:
  # Variant A (책 의도 — 주봉 56주 warmup, 표본 0 가능)
  python scripts/run_weinstein_stages.py --variant A --all-modes

  # Variant B (책간 획일 — 일봉)
  python scripts/run_weinstein_stages.py --variant B --mode single --rule stage2_initial_breakout

  # Variant Light (인프라 검증 + 표본 확보)
  python scripts/run_weinstein_stages.py --variant Light --all-modes

데이터 : daily_prices (adj_factor 적용 수정주가)
universe: top_volume:50 (일평균 거래대금 상위 50)
RS      : Mansfield RS — universe 동일가중 주봉 인덱스 기반
          (KOSPI 부재 시 대체. 설계서 §1b)
청산    : Variant A  (sl 8% / tp 30% / mh 20주 / trail MA30W)
          Variant B  (sl 8% / tp 12% / mh 20일  / trail 없음)
          Variant Light (sl 8% / tp 20% / mh 10주 / trail MA10W)

※ Variant A: warmup 56주 → daily_prices 32주에선 표본 0 확실.
   인프라 동작 검증 목적으로 에러 없이 종료.
   Variant Light 결과는 인프라 검증용 only (책 평가 아님).
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.weinstein_stages.rules import (
    ALL_RULES,
    compute_ma30w_slope,
    compute_mansfield_rs,
    stage_classifier,
)
from strategies.books.weinstein_stages.strategy import BOOK_META, build_strategy
from strategies.books.weinstein_stages.weekly import resample_daily_to_weekly

LOG = logging.getLogger("weinstein_stages")

# ---------------------------------------------------------------------------
# Variant 파라미터 (설계서 §5c)
# ---------------------------------------------------------------------------
VARIANT_PARAMS = {
    # Variant A: 책 의도 — 주봉 56주 warmup, MA30W trail, tp 30%
    "A":     dict(stop_loss_pct=0.08, take_profit_pct=0.30, max_hold_bars=20,
                  trail_ma=30, weekly=True,  warmup=56, rs_n=26),
    # Variant B: 책간 획일 — 일봉 60일 warmup, trail 없음, tp 12%
    "B":     dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20,
                  trail_ma=None, weekly=False, warmup=60, rs_n=None),
    # Variant Light: 인프라 검증 — MA10W trail, tp 20%, warmup 18주
    # 결과는 인프라 검증용 only — 책 평가 아님. 추후 데이터 누적 후 재검토.
    "Light": dict(stop_loss_pct=0.08, take_profit_pct=0.20, max_hold_bars=10,
                  trail_ma=10, weekly=True,  warmup=18, rs_n=8),
}


# ---------------------------------------------------------------------------
# 데이터 로드 (run_minervini_vcp.py 패턴 재사용)
# ---------------------------------------------------------------------------

def _load_top_volume_universe(start: str, end: str, top_n: int = 50) -> List[str]:
    """daily_prices 거래대금 상위 N종목 코드 리스트."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
              AND stock_code != 'KOSPI'
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
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            # quant close 는 이미 분할조정된 연속 시세 → adj_factor 곱하지 않음(곱하면 분할일 가짜 절벽).
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    return out


def _load_kospi_daily(start: str, end: str) -> Optional[pd.DataFrame]:
    """daily_prices에서 KOSPI 지수 일봉 로드 (Phase 3a에서 적재된 데이터)."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT date, open, high, low, close, volume
            FROM daily_prices
            WHERE stock_code = 'KOSPI'
              AND date >= %s AND date <= %s
            ORDER BY date ASC
        """, (start, end))
        rows = cur.fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df["datetime"] = df["date"]
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _build_universe_close(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """{code: df} → wide close DataFrame (index=date, columns=code)."""
    series = {code: df.set_index("datetime")["close"] for code, df in data.items()}
    wide = pd.DataFrame(series)
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


def _build_universe_market_index(wide_close: pd.DataFrame) -> pd.Series:
    """universe 동일가중 일봉 종가 인덱스 시리즈.

    KOSPI 원본 대체용. 설계서 §1b.
    추후 KOSPI 데이터 충분해지면 KOSPI로 교체 검토.
    """
    return wide_close.mean(axis=1)


# ---------------------------------------------------------------------------
# 주봉 인디케이터 계산
# ---------------------------------------------------------------------------

def _build_weekly_indicators(
    weekly_df: pd.DataFrame,
    market_weekly_close: pd.Series,
    rs_n: int = 26,
) -> Dict[str, pd.Series]:
    """주봉 df로부터 MA30W, slope, Mansfield RS, Stage 시리즈 계산.

    Args:
        weekly_df         : resample_daily_to_weekly() 출력.
        market_weekly_close: universe 동일가중 주봉 종가 시리즈.
        rs_n              : Mansfield RS SMA 기간(주). Variant A=26, Light=8.

    Returns:
        dict with keys: ma30w_series, slope_series, mrs_series, stage_series.
    """
    close = weekly_df["close"].astype(float)
    close.index = range(len(close))  # 정수 index로 통일

    ma30w = close.rolling(30).mean()
    slope = compute_ma30w_slope(close, lookback=4)

    # Mansfield RS: market_weekly_close를 weekly_df datetime으로 정렬
    weekly_dates = weekly_df["datetime"].values
    mkt_aligned = market_weekly_close.reindex(
        pd.to_datetime(weekly_dates), method="nearest", tolerance=pd.Timedelta("7d")
    )
    mkt_aligned = mkt_aligned.reset_index(drop=True)
    mrs = compute_mansfield_rs(close, mkt_aligned, n=rs_n)
    mrs = mrs.reset_index(drop=True)

    stages = stage_classifier(close, ma30w, slope, mrs)

    return {
        "ma30w_series": ma30w,
        "slope_series": slope,
        "mrs_series": mrs,
        "stage_series": stages,
    }


# ---------------------------------------------------------------------------
# 시뮬레이션 (run_minervini_vcp.py simulate_one_stock 복사 + Weinstein 수정)
# ---------------------------------------------------------------------------

def simulate_one_stock(
    code: str,
    df: pd.DataFrame,
    indicators: Dict[str, pd.Series],
    strategy,
    stop_loss_pct: float,
    take_profit_pct: float,
    max_hold_bars: int,
    trail_ma: Optional[int],
    warmup_bars: int = 56,
    commission_rate: float = 0.00015,
    tax_rate: float = 0.0018,
    slippage_rate: float = 0.001,
    initial_capital: float = 10_000_000,
) -> dict:
    """단일 종목 시뮬레이션 (주봉 또는 일봉).

    신호 → 다음 봉 시가 매수 → sl/tp/mh/trail 청산.
    indicators: ma30w_series, slope_series, mrs_series, stage_series (정수 index).
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
        cur_date = bar_now["datetime"]

        # --- 청산 체크 ---
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
                ma = df["close"].iloc[i - trail_ma + 1: i + 1].mean()
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

        # --- 신호 평가 ---
        if position is None:
            window = df.iloc[: i + 1]

            # 인디케이터 슬라이스 (index i까지)
            ctx_extra = {
                k: v.iloc[: i + 1] if isinstance(v, pd.Series) else v
                for k, v in indicators.items()
            }

            signal = strategy.generate_signal_with_extra_ctx(code, window, "weekly", ctx_extra)
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

    return {
        "n_trades": sum(1 for t in trades if t["side"] == "sell"),
        "trades": trades,
        "equity_curve": equity,
    }


def _compute_metrics(initial: float, equity: List[float], trades: List[dict], weekly: bool = False) -> dict:
    """PnL/Sharpe/Calmar/MaxDD/HitRate/AvgHold 계산.

    weekly=True 시 Sharpe 연환산 인수 sqrt(52), 일봉은 sqrt(252).
    """
    if not equity:
        return dict(n_trades=0, pnl_pct=0.0, sharpe=0.0, calmar=0.0,
                    max_dd=0.0, hit_rate=0.0, avg_hold_bars=0.0)
    eq = np.array(equity, dtype=float)
    pnl_pct = (eq[-1] - initial) / initial
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    annualize = math.sqrt(52) if weekly else math.sqrt(252)
    sharpe = float(rets.mean() / rets.std() * annualize) if len(rets) > 1 and rets.std() > 0 else 0.0
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
                max_dd=max_dd, hit_rate=hit, avg_hold_bars=avg_hold)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Weinstein Stage Analysis 백테스트")
    p.add_argument("--variant", required=True, choices=["A", "B", "Light"])
    p.add_argument("--mode", default=None, choices=["single", "all_AND"])
    p.add_argument("--rule", default=None, help="mode=single 시 룰 이름")
    p.add_argument("--all-modes", action="store_true", help="모든 모드 순차 실행")
    p.add_argument("--limit", type=int, default=None, help="디버그용 universe 상한")
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--start", default=None, help="YYYY-MM-DD (기본: daily_prices 최소 날짜)")
    p.add_argument("--end", default=None, help="YYYY-MM-DD (기본: daily_prices 최대 날짜)")
    p.add_argument("--reports-dir", default="reports/books_research/weinstein_stages")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.all_modes and args.mode is not None:
        p.error("--all-modes 와 --mode 는 동시 사용 불가")
    if not args.all_modes and args.mode is None:
        p.error("--mode 또는 --all-modes 둘 중 하나 필수")

    # 기간 자동 설정
    if args.start is None or args.end is None:
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MIN(date), MAX(date) FROM daily_prices WHERE stock_code != 'KOSPI'")
            mn, mx = cur.fetchone()
        args.start = args.start or str(mn)
        args.end = args.end or str(mx)
    LOG.info(f"period: {args.start} ~ {args.end}")

    params = VARIANT_PARAMS[args.variant]
    is_weekly: bool = params["weekly"]
    warmup: int = params["warmup"]
    rs_n: int = params["rs_n"] if params["rs_n"] is not None else 26

    # universe 로드
    universe = _load_top_volume_universe(args.start, args.end, args.top_n)
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    # 일봉 데이터 로드
    data = _load_daily_adj(universe, args.start, args.end)
    LOG.info(f"loaded daily data for {len(data)} stocks")
    if not data:
        LOG.error("no data — aborting")
        return

    # universe 동일가중 시장 인덱스 (주봉)
    wide_close_daily = _build_universe_close(data)

    # KOSPI 일봉 시도 (Phase 3a 적재분)
    kospi_daily = _load_kospi_daily(args.start, args.end)
    if kospi_daily is not None:
        LOG.info(f"KOSPI 일봉 로드 성공: {len(kospi_daily)}행")
        market_daily = kospi_daily.set_index("datetime")["close"]
    else:
        LOG.info("KOSPI 데이터 없음 — universe 동일가중 인덱스로 대체 (설계서 §1b)")
        market_daily = _build_universe_market_index(wide_close_daily)

    # 주봉 시장 인덱스
    if is_weekly:
        market_df_tmp = market_daily.reset_index()
        market_df_tmp.columns = ["datetime", "close"]
        market_df_tmp["open"] = market_df_tmp["close"]
        market_df_tmp["high"] = market_df_tmp["close"]
        market_df_tmp["low"] = market_df_tmp["close"]
        market_df_tmp["volume"] = 0
        market_weekly_df = resample_daily_to_weekly(market_df_tmp)
        if len(market_weekly_df) == 0:
            LOG.error("market weekly resample 결과 없음 — aborting")
            return
        market_weekly_close = market_weekly_df.set_index("datetime")["close"]
        LOG.info(f"market weekly bars: {len(market_weekly_close)}")

    # 룰/모드 조합 목록
    rule_names = [cls().name for cls in ALL_RULES]
    if args.all_modes:
        combos = [("single", n) for n in rule_names] + [("all_AND", None)]
    else:
        combos = [(args.mode, args.rule)]

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = Path("reports/books_research/leaderboard.parquet")

    from backtest.book_backtester import append_leaderboard

    for mode, rule_name in combos:
        strategy = build_strategy(mode=mode, target_rule=rule_name)
        per_stock_metrics = []
        all_trades: List[dict] = []

        for code, daily_df in data.items():
            if is_weekly:
                # 설계서 §10b 권장: 스크립트 단에서 주봉 변환
                sim_df = resample_daily_to_weekly(daily_df)
                if len(sim_df) < warmup + 2:
                    LOG.debug(f"{code}: 주봉 {len(sim_df)}봉 < warmup {warmup}+2 — skip")
                    continue
                indicators = _build_weekly_indicators(sim_df, market_weekly_close, rs_n=rs_n)
            else:
                # Variant B: 일봉 그대로
                sim_df = daily_df.copy()
                # Mansfield RS는 일봉 universe 동일가중으로 계산
                stock_close = sim_df.set_index("datetime")["close"]
                mrs_daily = compute_mansfield_rs(stock_close, market_daily, n=rs_n)
                # 정수 index 맞춤
                mrs_reset = mrs_daily.reset_index(drop=True)
                ma30w_d = stock_close.reset_index(drop=True).rolling(30).mean()
                slope_d = compute_ma30w_slope(stock_close.reset_index(drop=True), lookback=4)
                from strategies.books.weinstein_stages.rules import stage_classifier
                stage_d = stage_classifier(
                    stock_close.reset_index(drop=True), ma30w_d, slope_d, mrs_reset
                )
                indicators = {
                    "ma30w_series": ma30w_d,
                    "slope_series": slope_d,
                    "mrs_series": mrs_reset,
                    "stage_series": stage_d,
                }

            res = simulate_one_stock(
                code=code,
                df=sim_df,
                indicators=indicators,
                strategy=strategy,
                stop_loss_pct=params["stop_loss_pct"],
                take_profit_pct=params["take_profit_pct"],
                max_hold_bars=params["max_hold_bars"],
                trail_ma=params["trail_ma"],
                warmup_bars=warmup,
                initial_capital=10_000_000,
            )
            metrics = _compute_metrics(10_000_000, res["equity_curve"], res["trades"], weekly=is_weekly)
            per_stock_metrics.append(metrics)
            all_trades.extend(res["trades"])

        if not per_stock_metrics:
            LOG.warning(f"[variant={args.variant} {mode}/{rule_name}] 처리된 종목 없음 (warmup 부족 가능) — skip")
            continue

        # 집계
        n_stocks = len(per_stock_metrics)
        agg = {
            "n_stocks": n_stocks,
            "n_trades": int(sum(m["n_trades"] for m in per_stock_metrics)),
            "pnl_pct": float(np.mean([m["pnl_pct"] for m in per_stock_metrics])),
            "sharpe": float(np.mean([m["sharpe"] for m in per_stock_metrics])),
            "calmar": float(np.mean([m["calmar"] for m in per_stock_metrics])),
            "max_dd": float(np.mean([m["max_dd"] for m in per_stock_metrics])),
            "hit_rate": float(np.mean([m["hit_rate"] for m in per_stock_metrics])),
            "avg_hold_bars": float(np.mean([m["avg_hold_bars"] for m in per_stock_metrics])),
        }
        label = rule_name if mode == "single" else mode
        unit = "주" if is_weekly else "일"
        LOG.info(
            f"[variant={args.variant} {mode}/{label}] "
            f"n_stocks={n_stocks} n_trades={agg['n_trades']} "
            f"pnl={agg['pnl_pct']:.4%} sharpe={agg['sharpe']:.2f} "
            f"avg_hold={agg['avg_hold_bars']:.1f}{unit}"
        )

        # 개별 trade 결과 저장
        out_file = reports_dir / f"results_variant{args.variant}_{mode}_{label}.parquet"
        if all_trades:
            pd.DataFrame(all_trades).to_parquet(out_file, index=False)
            LOG.info(f"trades saved: {out_file}")

        # 리더보드 append
        append_leaderboard(
            path=leaderboard_path,
            row={
                "book_id": "weinstein_stages",
                "book_name": BOOK_META["name"],
                "period": "weekly_full" if is_weekly else "daily_full",
                "rule_combo": label,
                "mode": mode,
                "variant": args.variant,
                "universe": f"top_volume:{args.top_n}",
                "stop_loss_pct": params["stop_loss_pct"],
                "take_profit_pct": params["take_profit_pct"],
                "max_hold_bars": params["max_hold_bars"],
                "weekly": is_weekly,
                "rs_n": rs_n,
                "warmup_bars": warmup,
                "n_stocks": agg["n_stocks"],
                "n_trades": agg["n_trades"],
                "pnl_pct": agg["pnl_pct"],
                "sharpe": agg["sharpe"],
                "calmar": agg["calmar"],
                "max_dd_pct": agg["max_dd"],
                "hit_rate": agg["hit_rate"],
                "avg_hold_bars": agg["avg_hold_bars"],
            },
        )

    LOG.info("done.")


if __name__ == "__main__":
    main()
