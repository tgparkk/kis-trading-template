"""책 전략 파라미터 멀티버스 드라이버 (재사용 가능).

진입 룰 파라미터(dataclass 필드) + 청산 파라미터(sl/tp/mh)를 **동시에** 그리드 스윕한다.
임의의 책 전략의 단일 룰에 대해, 데이터를 한 번만 로드(in-process)하고 모든 조합을
강건한 목적함수로 랭킹한다. 분봉(minute)·일봉(daily) 두 트랙 모두 지원.

설계:
- 데이터는 (기간·유니버스)당 한 번만 로드하여 모든 조합에서 재사용한다 (이게 in-process 의 핵심).
- 진입 룰은 ALL_RULES 에서 .name 으로 찾고, dataclass 필드를 **overrides 로 주입해 인스턴스화한다.
- mode="single" 의 BookStrategy(rules=[그 룰]) 로 단일 룰만 평가.
- 분봉: 기간별 BookBacktester.run_universe (no-lookahead 가드 내장).
- 일봉: 전체기간 simulate_one_stock (no-lookahead 가드 내장, run_daytrading_3methods 와 동일 로직 복제).

목적함수(강건):
- 분봉(다기간): pos_periods(pnl>0 기간 수) desc → mean_sharpe desc → mean_pnl desc.
  단 1개 기간에서만 양수면 [OVERFIT] 플래그.
- 일봉: sharpe desc → pnl desc. --start/--end 국면창 주면 per-regime 도 보고.

출력:
- <out>/multiverse_<book>_<rule>.tsv (전 조합, 정렬됨)
- top-K 표 + best vs baseline(룰 기본 필드값 + grid 내 baseline sl/tp/mh) 콘솔 출력.
- reports/books_research/leaderboard.parquet 에는 절대 쓰지 않는다 (--out temp dir 만 사용).

grid JSON 포맷 (caller 가 임의 book/rule 구동용):
  {"<rule_field>": [v1, v2, ...], ..., "sl": [...], "tp": [...], "mh": [...]}
  - rule_field 키는 룰 dataclass 필드명 (예: aziz rule_abcd 의 "lookback",
    daytrading rule_breakout_prev_high 의 "high_window"/"vol_lookback"/"vol_mult").
  - sl/tp/mh 는 청산 파라미터 (stop_loss_pct / take_profit_pct / max_hold_bars).

usage (분봉):
  python scripts/book_param_multiverse.py --book aziz_day_trade --rule abcd \
    --granularity minute --periods 2025-10 \
    --grid '{"lookback":[10,15,20],"sl":[0.03,0.05],"tp":[0.05,0.10],"mh":[120]}' \
    --universe top_volume:50 --limit 20 --out D:\\tmp\\multiverse\\smoke_aziz

usage (일봉):
  python scripts/book_param_multiverse.py --book daytrading_3methods --rule breakout_prev_high \
    --granularity daily \
    --grid '{"high_window":[15,20,30],"vol_mult":[1.5,2.0],"sl":[0.10],"tp":[0.10],"mh":[10]}' \
    --universe top_volume:50 --limit 20 --out D:\\tmp\\multiverse\\smoke_dt3
"""

from __future__ import annotations

import argparse
import importlib
import itertools
import json
import logging
import math
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows 콘솔(cp949)에서 비-ASCII 출력 안전화
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

LOG = logging.getLogger("book_param_multiverse")

# 분봉 기간 (run_books_research 와 동일)
MINUTE_PERIODS = {
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-04": ("2026-04-01", "2026-04-30"),
    "2026-05": ("2026-05-01", "2026-05-27"),
}

EXIT_KEYS = ("sl", "tp", "mh")


# ===========================================================================
# 데이터 로더 (run 스크립트의 최소 로더 복제 — 기존 스크립트는 수정하지 않음)
# ===========================================================================

def _load_book(book_id: str, rules_module: str = "rules"):
    # strategy 모듈: strategy.py 우선, 없으면 strategy_daily.py fallback
    try:
        strat_mod = importlib.import_module(f"strategies.books.{book_id}.strategy")
    except ModuleNotFoundError:
        strat_mod = importlib.import_module(f"strategies.books.{book_id}.strategy_daily")
    rules_mod = importlib.import_module(f"strategies.books.{book_id}.{rules_module}")
    if not hasattr(rules_mod, "ALL_RULES"):
        raise AttributeError(f"strategies.books.{book_id}.{rules_module} 에 ALL_RULES 가 없습니다")
    return strat_mod, rules_mod


def _resolve_rule_cls(rules_mod, rule_name: str):
    """ALL_RULES 에서 .name == rule_name (또는 rule_<name>) 인 dataclass 를 찾는다."""
    for cls in rules_mod.ALL_RULES:
        inst = cls()
        if inst.name == rule_name:
            return cls
    # 클래스명(rule_abcd) 입력 허용 → .name 환원
    stripped = rule_name[len("rule_"):] if rule_name.startswith("rule_") else rule_name
    for cls in rules_mod.ALL_RULES:
        if cls().name == stripped:
            return cls
    valid = [cls().name for cls in rules_mod.ALL_RULES]
    raise ValueError(f"rule {rule_name!r} 없음. 사용가능: {valid}")


# --- minute 로더 (run_books_research.py 복제) ---

def _load_top_volume_minute(period_start: str, period_end: str, top_n: int) -> List[str]:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        q = """
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM minute_candles
            WHERE datetime >= %s AND datetime < %s::date + INTERVAL '1 day'
            GROUP BY stock_code
            ORDER BY turnover DESC, stock_code ASC
            LIMIT %s
        """
        df = pd.read_sql(q, conn, params=(period_start, period_end, top_n))
    return df["stock_code"].tolist()


def _load_minute_data(stock_codes: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    from db.connection import DatabaseConnection
    out: Dict[str, pd.DataFrame] = {}
    with DatabaseConnection.get_connection() as conn:
        for code in stock_codes:
            q = """
                SELECT datetime, open, high, low, close, volume
                FROM minute_candles
                WHERE stock_code = %s
                  AND datetime >= %s
                  AND datetime < %s::date + INTERVAL '1 day'
                ORDER BY datetime ASC
            """
            df = pd.read_sql(q, conn, params=(code, start_date, end_date))
            if not df.empty:
                out[code] = df
    return out


# --- daily 로더 (run_daytrading_3methods.py 복제) ---

def _load_top_volume_daily(start: str, end: str, top_n: int) -> List[str]:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
            GROUP BY stock_code
            ORDER BY turnover DESC, stock_code ASC
            LIMIT %s
        """, (start, end, top_n))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _load_daily_adj(stock_codes: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    from db.connection import DatabaseConnection
    out: Dict[str, pd.DataFrame] = {}
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, high, low, close, volume, adj_factor
                FROM daily_prices
                WHERE stock_code = %s AND date >= %s AND date <= %s
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
            drop_mask = df["close"].isna() | (df["close"] <= 0)
            df = df[~drop_mask].copy()
            for col in ["open", "high", "low"]:
                fill_mask = df[col].isna() | (df[col] <= 0)
                df.loc[fill_mask, col] = df.loc[fill_mask, "close"]
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    return out


def _daily_minmax_dates() -> Tuple[str, str]:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT MIN(date), MAX(date) FROM daily_prices")
        mn, mx = cur.fetchone()
    return str(mn), str(mx)


# ===========================================================================
# 일봉 시뮬레이터 (run_daytrading_3methods.py 복제 — no-lookahead 동일)
# ===========================================================================

def _simulate_daily(
    code: str, df: pd.DataFrame, strategy,
    stop_loss_pct: float, take_profit_pct: float, max_hold_bars: int,
    warmup_bars: int = 42, commission_rate: float = 0.00015,
    tax_rate: float = 0.0018, slippage_rate: float = 0.001,
    initial_capital: float = 10_000_000,
) -> dict:
    from strategies.base import SignalType
    n = len(df)
    if n < warmup_bars + 2:
        return {"trades": [], "equity_curve": [initial_capital]}
    df = df.reset_index(drop=True).copy()
    cash = initial_capital
    position: Optional[dict] = None
    trades: List[dict] = []
    equity: List[float] = []

    for i in range(warmup_bars, n - 1):
        bar_now = df.iloc[i]
        bar_next = df.iloc[i + 1]
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
            if exit_reason is not None and float(bar_next["open"]) <= 0:
                exit_reason = None
            if exit_reason is not None:
                fill = float(bar_next["open"]) * (1 - slippage_rate)
                proceeds = position["qty"] * fill
                fee = proceeds * (commission_rate + tax_rate)
                cash += proceeds - fee
                pnl = (fill - entry_price) / entry_price
                trades.append({"side": "sell", "idx": i + 1, "pnl_pct": pnl})
                position = None
        if position is None:
            window = df.iloc[: i + 1]
            signal = strategy.generate_signal(code, window, "daily")
            if signal is not None and signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                raw_next_open = float(bar_next["open"])
                fill = raw_next_open * (1 + slippage_rate)
                qty = int((cash * 0.99) // fill) if fill > 0 else 0
                if qty > 0:
                    cost = qty * fill
                    fee = cost * commission_rate
                    cash -= cost + fee
                    position = {"entry_idx": i + 1, "entry_price": fill, "qty": qty}
                    trades.append({"side": "buy", "idx": i + 1, "pnl_pct": 0.0})
        mtm = cash
        if position is not None:
            mtm += position["qty"] * float(bar_now["close"])
        equity.append(mtm)

    if position is not None and float(df.iloc[-1]["close"]) > 0:
        last = df.iloc[-1]
        fill = float(last["close"]) * (1 - slippage_rate)
        proceeds = position["qty"] * fill
        fee = proceeds * (commission_rate + tax_rate)
        cash += proceeds - fee
        entry_price = position["entry_price"]
        trades.append({"side": "sell", "idx": n - 1, "pnl_pct": (fill - entry_price) / entry_price})
        equity.append(cash)
    return {"trades": trades, "equity_curve": equity}


def _daily_metrics(initial: float, equity: List[float], trades: List[dict]) -> dict:
    if not equity:
        return dict(n_trades=0, pnl=0.0, sharpe=0.0, calmar=0.0, max_dd=0.0, hit=0.0)
    eq = np.array(equity, dtype=float)
    pnl = (eq[-1] - initial) / initial
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min()) if len(dd) else 0.0
    calmar = float(pnl / max_dd) if max_dd > 1e-9 else 0.0
    sells = [t for t in trades if t["side"] == "sell"]
    wins = sum(1 for t in sells if t["pnl_pct"] > 0)
    hit = wins / len(sells) if sells else 0.0
    return dict(n_trades=len(sells), pnl=pnl, sharpe=sharpe, calmar=calmar, max_dd=max_dd, hit=hit)


# ===========================================================================
# 조합 빌드 / 평가
# ===========================================================================

def _split_grid(grid: Dict[str, List], rule_cls) -> Tuple[Dict[str, List], Dict[str, List]]:
    """grid 를 rule-field 그리드와 exit(sl/tp/mh) 그리드로 분리. 알려지지 않은 키는 에러."""
    rule_field_names = {f.name for f in dataclass_fields(rule_cls)}
    rule_grid: Dict[str, List] = {}
    exit_grid: Dict[str, List] = {}
    for k, v in grid.items():
        if k in EXIT_KEYS:
            exit_grid[k] = list(v)
        elif k in rule_field_names:
            rule_grid[k] = list(v)
        else:
            raise ValueError(
                f"grid 키 {k!r} 는 룰 필드도 exit({EXIT_KEYS})도 아님. "
                f"룰 필드: {sorted(rule_field_names - {'name'})}"
            )
    exit_grid.setdefault("sl", [0.02])
    exit_grid.setdefault("tp", [0.03])
    exit_grid.setdefault("mh", [60])
    return rule_grid, exit_grid


def _cartesian(grid: Dict[str, List]) -> List[Dict[str, Any]]:
    if not grid:
        return [{}]
    keys = list(grid.keys())
    return [dict(zip(keys, vals)) for vals in itertools.product(*[grid[k] for k in keys])]


def _build_strategy(rule_cls, rule_name: str, rule_overrides: Dict[str, Any]):
    from strategies.books._base_book_strategy import BookStrategy
    rule = rule_cls(**rule_overrides)
    return BookStrategy(rules=[rule], mode="single", target_rule=rule_name)


def _eval_minute_combo(strategy, sl, tp, mh, data: Dict[str, pd.DataFrame]) -> dict:
    from backtest.book_backtester import BookBacktester
    bt = BookBacktester(
        strategy=strategy, initial_capital=10_000_000, warmup_bars=20,
        stop_loss_pct=sl, take_profit_pct=tp, max_hold_bars=mh,
    )
    agg = bt.run_universe(data)
    return dict(n_trades=agg.n_trades, pnl=agg.pnl_pct, sharpe=agg.sharpe,
                calmar=agg.calmar, hit=agg.hit_rate, max_dd=agg.max_dd_pct)


def _eval_daily_combo(strategy, sl, tp, mh, data: Dict[str, pd.DataFrame]) -> dict:
    pnls, sharpes, calmars, hits, dds, ntr = [], [], [], [], [], 0
    for code, df in data.items():
        res = _simulate_daily(code, df, strategy, sl, tp, mh)
        m = _daily_metrics(10_000_000, res["equity_curve"], res["trades"])
        pnls.append(m["pnl"]); sharpes.append(m["sharpe"]); calmars.append(m["calmar"])
        hits.append(m["hit"]); dds.append(m["max_dd"]); ntr += m["n_trades"]
    if not pnls:
        return dict(n_trades=0, pnl=0.0, sharpe=0.0, calmar=0.0, hit=0.0, max_dd=0.0)
    return dict(n_trades=ntr, pnl=float(np.mean(pnls)), sharpe=float(np.mean(sharpes)),
                calmar=float(np.mean(calmars)), hit=float(np.mean(hits)), max_dd=float(np.mean(dds)))


# ===========================================================================
# 포맷 헬퍼
# ===========================================================================

def _combo_label(rule_over: Dict[str, Any], sl, tp, mh) -> str:
    parts = [f"{k}={v}" for k, v in sorted(rule_over.items())]
    parts += [f"sl={sl}", f"tp={tp}", f"mh={mh}"]
    return " ".join(parts)


def _rule_defaults(rule_cls) -> Dict[str, Any]:
    inst = rule_cls()
    return {f.name: getattr(inst, f.name) for f in dataclass_fields(rule_cls) if f.name != "name"}


# ===========================================================================
# main
# ===========================================================================

def main():
    p = argparse.ArgumentParser(description="책 전략 진입+청산 파라미터 멀티버스 드라이버")
    p.add_argument("--book", required=True)
    p.add_argument("--rules-module", default="rules", dest="rules_module",
                   help="룰 모듈명 (기본 'rules'; daily 룰은 'rules_daily' 등)")
    p.add_argument("--rule", required=True, help="단일 룰 .name (또는 rule_<name>)")
    p.add_argument("--universe", default="top_volume:50")
    p.add_argument("--granularity", default="auto", choices=["minute", "daily", "auto"])
    p.add_argument("--periods", default="2025-10,2026-04,2026-05",
                   help="분봉 전용 쉼표 구분 (daily 는 무시)")
    p.add_argument("--start", default=None, help="daily 기간 시작 (기본 daily_prices 최소)")
    p.add_argument("--end", default=None, help="daily 기간 끝 (기본 daily_prices 최대)")
    p.add_argument("--grid", required=True, help='JSON: {"<rule_field>":[...],"sl":[...],"tp":[...],"mh":[...]}')
    p.add_argument("--out", default=None)
    p.add_argument("--limit", type=int, default=None, help="유니버스 N개 제한 (속도)")
    p.add_argument("--top-k", type=int, default=15)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not args.universe.startswith("top_volume:"):
        p.error("--universe 는 top_volume:N 형식만 지원")
    top_n = int(args.universe.split(":", 1)[1])

    strat_mod, rules_mod = _load_book(args.book, args.rules_module)
    rule_cls = _resolve_rule_cls(rules_mod, args.rule)
    rule_name = rule_cls().name

    granularity = args.granularity
    if granularity == "auto":
        granularity = getattr(strat_mod, "BOOK_META", {}).get("data_granularity", "minute")
    LOG.info(f"book={args.book} rule={rule_name} granularity={granularity} universe=top_volume:{top_n}")

    grid = json.loads(args.grid)
    rule_grid, exit_grid = _split_grid(grid, rule_cls)
    rule_combos = _cartesian(rule_grid)
    exit_combos = _cartesian(exit_grid)
    total = len(rule_combos) * len(exit_combos)
    LOG.info(f"grid: rule_combos={len(rule_combos)} exit_combos={len(exit_combos)} total={total}")

    out_dir = Path(args.out) if args.out else Path(r"D:\tmp\multiverse") / f"{args.book}_{rule_name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[dict] = []

    if granularity == "minute":
        periods = [x.strip() for x in args.periods.split(",") if x.strip()]
        for pr in periods:
            if pr not in MINUTE_PERIODS:
                p.error(f"분봉 기간 {pr!r} 미정의. 사용가능: {list(MINUTE_PERIODS)}")
        # 기간별 데이터 1회 로드
        period_data: Dict[str, Dict[str, pd.DataFrame]] = {}
        for pr in periods:
            start, end = MINUTE_PERIODS[pr]
            uni = _load_top_volume_minute(start, end, top_n)
            if args.limit:
                uni = uni[: args.limit]
            data = _load_minute_data(uni, start, end)
            period_data[pr] = data
            LOG.info(f"period={pr} universe={len(uni)} loaded_data={len(data)}")

        for ro in rule_combos:
            for eo in exit_combos:
                sl, tp, mh = eo["sl"], eo["tp"], eo["mh"]
                strat = _build_strategy(rule_cls, rule_name, ro)
                per_period = {}
                for pr in periods:
                    per_period[pr] = _eval_minute_combo(strat, sl, tp, mh, period_data[pr])
                pnls = [per_period[pr]["pnl"] for pr in periods]
                shs = [per_period[pr]["sharpe"] for pr in periods]
                ntr = sum(per_period[pr]["n_trades"] for pr in periods)
                pos_periods = sum(1 for x in pnls if x > 0)
                mean_sharpe = float(np.mean(shs)) if shs else 0.0
                mean_pnl = float(np.mean(pnls)) if pnls else 0.0
                overfit = (pos_periods == 1 and len(periods) > 1)
                row = {**{f"r_{k}": v for k, v in ro.items()}, "sl": sl, "tp": tp, "mh": mh,
                       "n_trades": ntr, "pos_periods": pos_periods, "n_periods": len(periods),
                       "mean_sharpe": mean_sharpe, "mean_pnl": mean_pnl, "overfit": overfit,
                       "_rule_over": ro}
                for pr in periods:
                    row[f"pnl_{pr}"] = per_period[pr]["pnl"]
                rows.append(row)
        rows.sort(key=lambda r: (-r["pos_periods"], -r["mean_sharpe"], -r["mean_pnl"]))
        sort_desc = "pos_periods desc, mean_sharpe desc, mean_pnl desc"
        regimes = None
    else:  # daily
        if args.start is None or args.end is None:
            mn, mx = _daily_minmax_dates()
            start = args.start or mn
            end = args.end or mx
        else:
            start, end = args.start, args.end
        LOG.info(f"daily period: {start} ~ {end}")
        uni = _load_top_volume_daily(start, end, top_n)
        if args.limit:
            uni = uni[: args.limit]
        data = _load_daily_adj(uni, start, end)
        LOG.info(f"universe={len(uni)} loaded_data={len(data)}")
        regimes = (args.start is not None and args.end is not None)

        for ro in rule_combos:
            for eo in exit_combos:
                sl, tp, mh = eo["sl"], eo["tp"], eo["mh"]
                strat = _build_strategy(rule_cls, rule_name, ro)
                m = _eval_daily_combo(strat, sl, tp, mh, data)
                row = {**{f"r_{k}": v for k, v in ro.items()}, "sl": sl, "tp": tp, "mh": mh,
                       "n_trades": m["n_trades"], "pnl": m["pnl"], "sharpe": m["sharpe"],
                       "calmar": m["calmar"], "hit": m["hit"], "max_dd": m["max_dd"],
                       "_rule_over": ro}
                rows.append(row)
        rows.sort(key=lambda r: (-r["sharpe"], -r["pnl"]))
        sort_desc = "sharpe desc, pnl desc"

    # --- TSV 저장 (내부 키 _rule_over 제외) ---
    tsv_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    tsv_path = out_dir / f"multiverse_{args.book}_{rule_name}.tsv"
    pd.DataFrame(tsv_rows).to_csv(tsv_path, sep="\t", index=False)

    # --- top-K 콘솔 출력 ---
    print(f"\n=== MULTIVERSE {args.book} / {rule_name} ({granularity}) - sorted by {sort_desc} ===")
    print(f"total combos: {len(rows)}  |  tsv: {tsv_path}")
    topk = rows[: args.top_k]
    if granularity == "minute":
        print(f"{'rank':>4} {'combo':<48} {'ntr':>5} {'pos/N':>6} {'mSharpe':>8} {'mPnl':>8}  flag")
        for i, r in enumerate(topk, 1):
            label = _combo_label(r["_rule_over"], r["sl"], r["tp"], r["mh"])
            flag = "[OVERFIT]" if r["overfit"] else ""
            print(f"{i:>4} {label:<48} {r['n_trades']:>5} "
                  f"{r['pos_periods']}/{r['n_periods']:>3} {r['mean_sharpe']:>8.3f} "
                  f"{r['mean_pnl']:>8.4f}  {flag}")
    else:
        print(f"{'rank':>4} {'combo':<48} {'ntr':>5} {'sharpe':>8} {'pnl':>9} {'calmar':>7} {'hit':>6} {'maxdd':>7}")
        for i, r in enumerate(topk, 1):
            label = _combo_label(r["_rule_over"], r["sl"], r["tp"], r["mh"])
            print(f"{i:>4} {label:<48} {r['n_trades']:>5} {r['sharpe']:>8.3f} "
                  f"{r['pnl']:>9.4f} {r['calmar']:>7.2f} {r['hit']:>6.2%} {r['max_dd']:>7.2%}")

    # --- best vs baseline ---
    defaults = _rule_defaults(rule_cls)
    # baseline rule overrides = grid 내 룰 필드는 기본값으로 고정
    baseline_rule_over = {k: defaults[k] for k in rule_grid.keys()}
    # baseline exit = grid 의 첫 값
    bl_sl = exit_grid["sl"][0]; bl_tp = exit_grid["tp"][0]; bl_mh = exit_grid["mh"][0]

    def _match(r):
        if r["_rule_over"] != baseline_rule_over:
            return False
        return r["sl"] == bl_sl and r["tp"] == bl_tp and r["mh"] == bl_mh

    baseline = next((r for r in rows if _match(r)), None)
    best = rows[0] if rows else None
    print("\n--- BEST vs BASELINE ---")
    if best is not None:
        print(f"BEST    : {_combo_label(best['_rule_over'], best['sl'], best['tp'], best['mh'])}")
        if granularity == "minute":
            print(f"          pos={best['pos_periods']}/{best['n_periods']} "
                  f"mSharpe={best['mean_sharpe']:.3f} mPnl={best['mean_pnl']:.4f} "
                  f"{'[OVERFIT]' if best['overfit'] else ''}")
        else:
            print(f"          sharpe={best['sharpe']:.3f} pnl={best['pnl']:.4f} "
                  f"calmar={best['calmar']:.2f} hit={best['hit']:.2%}")
    if baseline is not None:
        bl_label = _combo_label(baseline["_rule_over"], baseline["sl"], baseline["tp"], baseline["mh"])
        print(f"BASELINE: {bl_label}")
        if granularity == "minute":
            print(f"          pos={baseline['pos_periods']}/{baseline['n_periods']} "
                  f"mSharpe={baseline['mean_sharpe']:.3f} mPnl={baseline['mean_pnl']:.4f}")
        else:
            print(f"          sharpe={baseline['sharpe']:.3f} pnl={baseline['pnl']:.4f} "
                  f"calmar={baseline['calmar']:.2f} hit={baseline['hit']:.2%}")
    else:
        print("BASELINE: (rule defaults + first exit) 가 grid 에 없어 비교 생략")

    if granularity == "daily" and regimes:
        print(f"\n(regime window: {start} ~ {end} - results above are limited to this regime)")


if __name__ == "__main__":
    main()
