"""Greenblatt Magic Formula 일봉 백테스트 (EY+ROC 횡단면 순위 + 임계).

usage:
  python scripts/run_greenblatt_magic.py --variant A --all-modes
  python scripts/run_greenblatt_magic.py --variant B --mode single --rule magic_formula_top

데이터: daily_prices (OHLC adj_factor 적용 수정주가; market_cap 은 레벨값 → adj 미적용)
universe: financial_statements DISTINCT stock_code (전부 일봉 보유)
재무: point-in-time fund 조인 (effective_date=report_date+105d ≤ 거래일)
지표: EY=operating_profit/(market_cap+total_liabilities),
      ROC=operating_profit/(total_assets-current_liabilities)
순위: 거래일별 EY rank(desc) + ROC rank(desc) 합산 → dense ordinal magic_rank(1=best)
청산: Variant A (sl 20% / tp 99%(off) / mh 120, trail 없음) 또는 B (sl 8% / tp 12% / mh 20)

⚠️ market_cap 은 6개월 창(~124일)만 존재 → 순위/EY 신호는 그 기간 한정. 리포트에 명시할 것.
⚠️ universe 교체로 이전 책들과 책간 비교성 깨짐 — 리포트에 명시할 것.
⚠️ 반드시 RoboTrader_template/ cwd 에서 실행 (상대경로 reports/...).
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.greenblatt_magic.rules import ALL_RULES
from strategies.books.greenblatt_magic.strategy import BOOK_META, build_strategy

LOG = logging.getLogger("greenblatt_magic")

VARIANT_PARAMS = {
    "A": dict(stop_loss_pct=0.20, take_profit_pct=0.99, max_hold_bars=120, trail_ma=None),
    "B": dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20, trail_ma=None),
}

# 재무 컬럼 (financial_statements) — Magic Formula 에 필요한 것만
_FS_NUM_COLS = [
    "operating_profit", "total_assets", "total_liabilities", "current_liabilities",
]

LAG_DAYS = 105       # 한국 사업보고서 공시 지연 → effective_date = report_date + 105d
ROC_CAP = 5.0        # ROC>5.0 → 작은 분모 폭주로 간주, 부적격

# daily_prices.market_cap 은 원(won) 단위, financial_statements 컬럼은 억원 단위.
# EV 계산 전 market_cap 을 억원으로 환산해야 단위가 맞음. (원 ÷ 1e8 = 억원)
MARKET_CAP_UNIT_DIVISOR = 1e8


def _load_fundamentals_universe() -> List[str]:
    """financial_statements의 DISTINCT stock_code (전부 일봉 보유)."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT stock_code FROM financial_statements ORDER BY stock_code")
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _load_daily_adj(stock_codes: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """종목별 daily_prices 로드.

    OHLC 는 adj_factor 적용 수정주가, market_cap 은 레벨값이므로 adj 미적용(그대로).
    반환 df 컬럼: datetime, open, high, low, close, volume, market_cap.
    """
    from db.connection import DatabaseConnection
    out: Dict[str, pd.DataFrame] = {}
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, high, low, close, volume, adj_factor, market_cap
                FROM daily_prices
                WHERE stock_code = %s
                  AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start, end))
            rows = cur.fetchall()
            if not rows or len(rows) < 30:
                continue
            df = pd.DataFrame(
                rows,
                columns=["date", "open", "high", "low", "close", "volume", "adj_factor", "market_cap"],
            )
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "high", "low", "close", "volume", "adj_factor", "market_cap"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["adj_factor"] = df["adj_factor"].fillna(1.0)
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col] * df["adj_factor"]  # market_cap 은 의도적으로 미적용
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume", "market_cap"]].reset_index(drop=True)
    return out


def _load_fundamentals_timeseries(stock_codes: List[str]) -> Dict[str, List[dict]]:
    """종목별 재무 시계열 로드.

    Returns:
        dict[code] -> report_date ASC 정렬된 row dict 리스트.
        report_date 는 date 로 파싱(malformed VARCHAR 는 스킵), 숫자 컬럼은 float(NULL→None).
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


def _build_fund_by_idx(df: pd.DataFrame, fs_rows: List[dict]) -> List[Optional[dict]]:
    """df 각 행에 대응하는 point-in-time Magic fund dict 리스트 (no-lookahead).

    각 거래일 D 에 대해:
      effective_date(row) = report_date + 105d
      fs_curr = effective_date ≤ D 인 행 中 report_date 최대
      market_cap = df.iloc[i]["market_cap"]  (그날 레벨값)
      EV = market_cap + total_liabilities
      ey = operating_profit / EV
      cap_denom = total_assets - current_liabilities
      roc = operating_profit / cap_denom

    가드 위반 시 ey=None, roc=None, eligible=False:
      operating_profit<=0 / market_cap NaN or <=0 / EV<=0 / cap_denom<=0 /
      입력 중 NULL / roc>5.0
    fs_curr 없으면 그 봉 fund=None.
    """
    n = len(df)
    if not fs_rows:
        return [None] * n

    eff = [(row["report_date"] + timedelta(days=LAG_DAYS), row) for row in fs_rows]
    eff.sort(key=lambda x: x[0])

    fund_by_idx: List[Optional[dict]] = []
    ptr = 0
    curr: Optional[dict] = None

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

        op = curr.get("operating_profit")
        ta = curr.get("total_assets")
        tl = curr.get("total_liabilities")
        cl = curr.get("current_liabilities")

        mc_raw = df.iloc[i]["market_cap"]
        try:
            mc = float(mc_raw)
        except (TypeError, ValueError):
            mc = float("nan")

        ey: Optional[float] = None
        roc: Optional[float] = None
        ev: Optional[float] = None
        eligible = False

        null_input = None in (op, ta, tl, cl)
        if (
            not null_input
            and op > 0
            and not (mc is None or math.isnan(mc) or mc <= 0)
        ):
            # market_cap 은 원(won) 단위, total_liabilities 는 억원 단위 → 억원으로 환산 후 합산
            mc_eok = mc / MARKET_CAP_UNIT_DIVISOR
            ev_calc = mc_eok + tl
            cap_denom = ta - cl
            if ev_calc > 0 and cap_denom > 0:
                ey_calc = op / ev_calc
                roc_calc = op / cap_denom
                if roc_calc <= ROC_CAP:
                    ey = ey_calc
                    roc = roc_calc
                    ev = ev_calc
                    eligible = True

        fund_by_idx.append({
            "operating_profit": op,
            "market_cap": None if (mc is None or math.isnan(mc)) else mc,
            "ev": ev,
            "ey": ey,
            "roc": roc,
            "eligible": eligible,
        })

    return fund_by_idx


def _build_cross_sectional_ranks(
    data: Dict[str, pd.DataFrame],
    fund_by_idx_map: Dict[str, List[Optional[dict]]],
):
    """횡단면 순위 precompute (no-lookahead: 거래일 D 데이터만 사용).

    Returns:
        rank_by_idx_map: dict[code] -> list aligned to df rows (int magic_rank or None)
        nelig_by_idx_map: dict[code] -> list aligned to df rows (int n_eligible or 0)
        n_eligible_by_date: dict[date] -> int (로깅용)
    """
    # 1) 거래일 D 별 적격 (code, ey, roc) 수집
    elig_by_date: Dict[date, List[tuple]] = defaultdict(list)
    for code, df in data.items():
        fbi = fund_by_idx_map.get(code, [])
        for i in range(len(df)):
            fund = fbi[i] if i < len(fbi) else None
            if fund is None or not fund.get("eligible"):
                continue
            ey = fund.get("ey")
            roc = fund.get("roc")
            if ey is None or roc is None:
                continue
            d = df.iloc[i]["datetime"]
            d = d.date() if hasattr(d, "date") else pd.to_datetime(d).date()
            elig_by_date[d].append((code, ey, roc))

    # 2) 거래일별 순위 산출
    rank_by_date: Dict[date, Dict[str, int]] = {}
    nelig_by_date: Dict[date, int] = {}
    for d, items in elig_by_date.items():
        ne = len(items)
        nelig_by_date[d] = ne
        if ne == 0:
            continue
        # ey rank desc (1=best): ey 내림차순 정렬 순서
        ey_order = sorted(range(ne), key=lambda k: items[k][1], reverse=True)
        ey_rank = [0] * ne
        for pos, k in enumerate(ey_order, start=1):
            ey_rank[k] = pos
        roc_order = sorted(range(ne), key=lambda k: items[k][2], reverse=True)
        roc_rank = [0] * ne
        for pos, k in enumerate(roc_order, start=1):
            roc_rank[k] = pos
        combined = [(items[k][0], ey_rank[k] + roc_rank[k]) for k in range(ne)]
        combined.sort(key=lambda x: x[1])  # combined 오름차순 (작을수록 best)
        rank_map: Dict[str, int] = {}
        for ordinal, (code, _c) in enumerate(combined, start=1):
            rank_map[code] = ordinal  # dense ordinal (1=best)
        rank_by_date[d] = rank_map

    # 3) 종목별 bar 에 매핑
    rank_by_idx_map: Dict[str, List[Optional[int]]] = {}
    nelig_by_idx_map: Dict[str, List[int]] = {}
    for code, df in data.items():
        ranks: List[Optional[int]] = []
        neligs: List[int] = []
        for i in range(len(df)):
            d = df.iloc[i]["datetime"]
            d = d.date() if hasattr(d, "date") else pd.to_datetime(d).date()
            rmap = rank_by_date.get(d)
            ranks.append(rmap.get(code) if rmap else None)
            neligs.append(nelig_by_date.get(d, 0))
        rank_by_idx_map[code] = ranks
        nelig_by_idx_map[code] = neligs

    return rank_by_idx_map, nelig_by_idx_map, nelig_by_date


def simulate_one_stock(
    code: str,
    df: pd.DataFrame,
    fund_by_idx: List[Optional[dict]],
    rank_by_idx: List[Optional[int]],
    nelig_by_idx: List[int],
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
            mr = rank_by_idx[i] if i < len(rank_by_idx) else None
            ne = nelig_by_idx[i] if i < len(nelig_by_idx) else 0
            ctx_extra = {"fund": fund, "magic_rank": mr, "n_eligible": ne}
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
    p.add_argument("--start", default=None, help="YYYY-MM-DD (기본: daily_prices 최소 날짜)")
    p.add_argument("--end", default=None, help="YYYY-MM-DD (기본: daily_prices 최대 날짜)")
    p.add_argument("--reports-dir", default="reports/books_research/greenblatt_magic_formula")
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

    # market_cap 보유 종목 수 (universe 라벨용)
    n_with_mc = sum(1 for df in data.values() if df["market_cap"].notna().any())
    LOG.info(f"stocks with >=1 non-null market_cap: {n_with_mc}")

    fs_ts = _load_fundamentals_timeseries(list(data.keys()))
    LOG.info(f"loaded fundamentals for {len(fs_ts)} stocks")

    # 종목별 point-in-time fund 사전계산 (한 번만)
    fund_by_idx_map: Dict[str, List[Optional[dict]]] = {}
    for code, df in data.items():
        fund_by_idx_map[code] = _build_fund_by_idx(df, fs_ts.get(code, []))

    # 횡단면 순위 precompute (no-lookahead)
    rank_by_idx_map, nelig_by_idx_map, nelig_by_date = _build_cross_sectional_ranks(
        data, fund_by_idx_map
    )
    if nelig_by_date:
        ne_vals = np.array(list(nelig_by_date.values()), dtype=float)
        LOG.info(
            f"n_eligible per date: dates={len(ne_vals)} "
            f"min={int(ne_vals.min())} median={int(np.median(ne_vals))} "
            f"mean={ne_vals.mean():.1f} max={int(ne_vals.max())}"
        )
    else:
        LOG.warning("no eligible (code,date) found — magic_rank signals will be empty")

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
                code=code, df=df, fund_by_idx=fund_by_idx_map[code],
                rank_by_idx=rank_by_idx_map[code], nelig_by_idx=nelig_by_idx_map[code],
                strategy=strategy,
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
                "book_id": "greenblatt_magic",
                "book_name": BOOK_META["name"],
                "period": "daily_full_mcwindow",
                "rule_combo": label,
                "mode": mode,
                "variant": args.variant,
                "universe": f"magic:{n_with_mc}",
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
