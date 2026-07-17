"""디노(백새봄) 『돈이 된다! 급등주 투자법』 — 일봉(daily) 백테스트.

Book 16. 눌린 우량 급등주(디노 4축 점수) → +10% 무조건 익절 회전.
haru_silijeon_daily / moonbyungro_metric 와 동일한 self-contained 러너.

usage:
  python scripts/run_dino_surge.py --variant A --all-modes
  python scripts/run_dino_surge.py --variant A --mode single --rule dino_test_pullback
  python scripts/run_dino_surge.py --variant B --mode single --rule pullback_rebound
  # 파일럿(짧은 기간·소수 종목):
  python scripts/run_dino_surge.py --variant A --mode single --rule dino_test_pullback \
      --start 2021-01-01 --end 2026-05-29 --limit 50
  # 재무 게이트 끄기(가격·기술축만):
  python scripts/run_dino_surge.py --variant A --all-modes --no-fin

데이터: daily_prices (OHLC adj_factor 적용 수정주가)
universe: top_volume:N (일평균 거래대금 상위 N) — 기존 일봉책(elder/haru)과 동일.
재무: point-in-time financial_statements 조인(effective_date=report_date+LAG_DAYS ≤ 거래일)으로
      디노 재무점수(fin_score 0~5)+좀비기업 근사 하드필터를 precompute 해 ctx["dino_fin"] 로 주입.
청산(카탈로그 §4 "+10% 무조건 익절"):
  Variant A (책 충실): sl 7% / tp 10% / mh 20 / trail_ma=5 (MA5 이탈 청산)
  Variant B (회전 단순): sl 5% / tp 10% / mh 15 / trail_ma=None
no-lookahead: rule 은 df[:i+1]만, 체결은 다음 봉 시가. 거래비용 elder/haru/문병로와 동일.

미구현/근사:
- 이자보상배율(영업이익/이자비용): financial_statements 에 이자비용 컬럼 없음 →
  debt_ratio≥DEBT_ZOMBIE AND operating_profit<=0 좀비 근사 하드필터(hard_pass=False).
- 유보율(≥1000%): 직접 컬럼 없음 → roe(이익잉여금 proxy) 양수 가점으로 근사.
- 재료(축④), 관리종목 플래그: 데이터 없음 → 생략(카탈로그 §6).

⚠️ 반드시 RoboTrader_template/ cwd 에서 실행 (상대경로 reports/...).
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.dino_surge.rules import ALL_RULES
from strategies.books.dino_surge.strategy import BOOK_META, build_strategy

LOG = logging.getLogger("dino_surge")

# 청산 파라미터 (카탈로그 §4 "+10% 무조건 익절" — A/B variant tp=0.10 고정)
VARIANT_PARAMS = {
    # A: 책 충실 — sl 7% / tp 10% / mh 20 / MA5 이탈 trail
    "A": dict(stop_loss_pct=0.07, take_profit_pct=0.10, max_hold_bars=20, trail_ma=5),
    # B: 회전 단순 — sl 5% / tp 10% / mh 15 / trail 없음
    "B": dict(stop_loss_pct=0.05, take_profit_pct=0.10, max_hold_bars=15, trail_ma=None),
    # C: 살베이지(디노 진입 + Elder식 추세청산) — 디노 +10% 고정익절·타이트손절·MA5트레일 전부 폐기.
    #    EMA13 트레일링 스톱 + 추세반전(EMA65 하향이탈=trend_flip) + 초기손절 8% + mh 100거래일,
    #    고정 익절 없음(tp=0.30 으로 사실상 추세에 맡김). exit_mode="trend" 로 분기.
    "C": dict(stop_loss_pct=0.08, take_profit_pct=0.30, max_hold_bars=100, trail_ma=None,
              exit_mode="trend", trail_ema=13, trend_ema=65),
}

# 재무 컬럼 (financial_statements) — 디노 재무점수에 필요한 것만
_FS_NUM_COLS = [
    "revenue", "operating_profit", "operating_margin", "debt_ratio", "roe",
]

LAG_DAYS = 105            # 한국 사업보고서 공시 지연 → effective_date = report_date + 105d
REV_GROWTH_MIN = 0.10    # 매출 +10%↑ (전년/직전 보고서 대비)
OPMARGIN_MIN = 10.0      # 영업이익률 ≥10% (operating_margin 은 % 단위 가정)
DEBT_HIGH = 50.0         # 부채비율 ≥50% → 감점(카탈로그 §1)
DEBT_ZOMBIE = 200.0      # 좀비 근사: 부채비율 ≥200% AND 영업적자 → hard_pass=False
DEFAULT_MIN_FIN_SCORE = 3.0  # 디노 재무점수(0~5) 컷오프 (16=만점 모순 → 보수적 근사)


def _ema(series: pd.Series, n: int) -> pd.Series:
    """지수이동평균 (adjust=False) — Elder ema_pullback 청산과 동일 사상."""
    return series.ewm(span=n, adjust=False).mean()


def _load_top_volume_universe(start: str, end: str, top_n: int = 50) -> List[str]:
    """daily_prices 의 (close*volume) 합계 상위 N종목."""
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
    """종목별 daily_prices (adj_factor 적용 수정주가) 로드. 컬럼: datetime, OHLC, volume."""
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
            # 거래정지/결손 보정 (haru/문병로와 동일)
            drop_mask = df["close"].isna() | (df["close"] <= 0)
            df = df[~drop_mask].copy()
            for col in ["open", "high", "low"]:
                fill_mask = df[col].isna() | (df[col] <= 0)
                df.loc[fill_mask, col] = df.loc[fill_mask, "close"]
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    return out


def _load_fundamentals_timeseries(stock_codes: List[str]) -> Dict[str, List[dict]]:
    """종목별 재무 시계열 로드. report_date ASC 정렬, malformed VARCHAR 스킵."""
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
                rd = pd.to_datetime(r[0], errors="coerce")
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


def _dino_fin_score(curr: dict, prev: Optional[dict], min_fin_score: float) -> dict:
    """디노 재무축(축①) 점수(0~5) + 좀비 근사 하드필터.

    카탈로그 §1 매핑:
      +1 매출 +10%↑ (prev 대비)
      +1 영업이익률 ≥10%
      +1 영업이익 흑자(>0)
      +1 ROE>0 (유보율≥1000% 근사 — 직접 컬럼 없음)
      -1 부채비율 ≥50%
    hard_pass=False: 부채비율 ≥200% AND 영업적자 (좀비기업/이자보상배율<1 근사).
    """
    revenue = curr.get("revenue")
    op = curr.get("operating_profit")
    opm = curr.get("operating_margin")
    debt = curr.get("debt_ratio")
    roe = curr.get("roe")

    score = 0.0
    # 매출 성장 +10%
    if revenue is not None and prev is not None:
        prev_rev = prev.get("revenue")
        if prev_rev is not None and prev_rev > 0 and (revenue - prev_rev) / prev_rev >= REV_GROWTH_MIN:
            score += 1.0
    # 영업이익률 ≥10%
    if opm is not None and opm >= OPMARGIN_MIN:
        score += 1.0
    # 영업이익 흑자
    if op is not None and op > 0:
        score += 1.0
    # ROE>0 (유보율 근사)
    if roe is not None and roe > 0:
        score += 1.0
    # 부채비율 ≥50% 감점
    if debt is not None and debt >= DEBT_HIGH:
        score -= 1.0

    # 좀비 근사 하드필터
    hard_pass = True
    if debt is not None and debt >= DEBT_ZOMBIE and op is not None and op <= 0:
        hard_pass = False

    return {"fin_score": score, "hard_pass": hard_pass, "min_fin_score": min_fin_score}


def _build_fin_by_idx(
    df: pd.DataFrame, fs_rows: List[dict], min_fin_score: float
) -> List[Optional[dict]]:
    """df 각 행에 대응하는 point-in-time 디노 재무 dict 리스트 (no-lookahead).

    effective_date = report_date + LAG_DAYS. 거래일 D 에 대해 effective_date ≤ D 인
    행 中 report_date 최대(curr) + 그 직전 보고서(prev, 매출성장 비교용)를 선택.
    """
    n = len(df)
    if not fs_rows:
        return [None] * n

    eff = sorted(
        [(row["report_date"] + timedelta(days=LAG_DAYS), row) for row in fs_rows],
        key=lambda x: x[0],
    )

    out: List[Optional[dict]] = []
    ptr = 0
    curr: Optional[dict] = None
    prev: Optional[dict] = None
    for i in range(n):
        d = df.iloc[i]["datetime"]
        d = d.date() if hasattr(d, "date") else pd.to_datetime(d).date()
        while ptr < len(eff) and eff[ptr][0] <= d:
            cand = eff[ptr][1]
            if curr is None or cand["report_date"] >= curr["report_date"]:
                prev = curr
                curr = cand
            ptr += 1
        if curr is None:
            out.append(None)
        else:
            out.append(_dino_fin_score(curr, prev, min_fin_score))
    return out


def simulate_one_stock(
    code: str,
    df: pd.DataFrame,
    fin_by_idx: List[Optional[dict]],
    strategy,
    stop_loss_pct: float,
    take_profit_pct: float,
    max_hold_bars: int,
    trail_ma: Optional[int],
    exit_mode: str = "fixed",
    trail_ema: int = 13,
    trend_ema: int = 65,
    warmup_bars: int = 20,
    commission_rate: float = 0.00015,
    tax_rate: float = 0.0018,
    slippage_rate: float = 0.001,
    initial_capital: float = 10_000_000,
) -> dict:
    """단일 종목 일봉 시뮬레이션. 신호 t → 다음 봉 시가 매수 → sl/tp/mh/trail_ma 청산.

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

    # variant C(추세청산) 사전계산: EMA13 트레일·EMA65 추세선 (각 i 값은 i까지 데이터만 의존 = no-lookahead).
    trend_exit = exit_mode == "trend"
    if trend_exit:
        close_s = df["close"].astype(float)
        ema_trail = _ema(close_s, trail_ema)
        ema_trend = _ema(close_s, trend_ema)
    else:
        ema_trail = ema_trend = None

    for i in range(warmup_bars, n - 1):
        bar_now = df.iloc[i]
        bar_next = df.iloc[i + 1]

        # 청산
        if position is not None:
            entry_price = position["entry_price"]
            cur_close = float(bar_now["close"])
            ret = (cur_close - entry_price) / entry_price
            hold_bars = i - position["entry_idx"]
            exit_reason = None
            if trend_exit:
                # Elder식 추세청산: 초기손절 8% → EMA13 트레일 → EMA65 하향이탈(trend_flip)
                #  → mh 100, 고정익절은 tp=0.30 으로 사실상 추세에 맡김.
                if ret <= -stop_loss_pct:
                    exit_reason = "stop_loss"
                elif ret >= take_profit_pct:
                    exit_reason = "take_profit"
                elif hold_bars >= max_hold_bars:
                    exit_reason = "max_hold"
                else:
                    e_trail = float(ema_trail.iloc[i])
                    e_trend = float(ema_trend.iloc[i])
                    e_trend_prev = float(ema_trend.iloc[i - 1]) if i >= 1 else e_trend
                    # 추세반전: EMA65 하향(기울기<0) AND 종가가 EMA65 하회
                    if pd.notna(e_trend) and e_trend < e_trend_prev and cur_close < e_trend:
                        exit_reason = "trend_flip"
                    # EMA13 트레일링 스톱: 종가가 EMA13 하회 (수익권 진입 후에만 발동 — 노이즈 청산 방지)
                    elif pd.notna(e_trail) and cur_close < e_trail and ret > 0:
                        exit_reason = "ema_trail"
            else:
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
            if exit_reason is not None and float(bar_next["open"]) <= 0:
                exit_reason = None  # 다음 봉 시가 무효 → 청산 보류
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

        # 신호 (무포지션)
        if position is None:
            window = df.iloc[: i + 1]
            fin = fin_by_idx[i] if i < len(fin_by_idx) else None
            signal = strategy.generate_signal_with_extra_ctx(code, window, "daily", {"dino_fin": fin})
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
            "entry_price": entry_price, "pnl_pct": (fill - entry_price) / entry_price,
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
    p.add_argument("--variant", required=True, choices=["A", "B", "C"])
    p.add_argument("--mode", default=None, choices=["single", "all_AND"])
    p.add_argument("--rule", default=None)
    p.add_argument("--all-modes", action="store_true")
    p.add_argument("--no-fin", action="store_true", help="재무 게이트 끄기(가격·기술축만)")
    p.add_argument("--min-fin-score", type=float, default=DEFAULT_MIN_FIN_SCORE,
                   help="디노 재무점수(0~5) 컷오프 (기본 3.0)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--start", default=None, help="YYYY-MM-DD (기본: daily_prices 최소 날짜)")
    p.add_argument("--end", default=None, help="YYYY-MM-DD (기본: daily_prices 최대 날짜)")
    p.add_argument("--reports-dir", default="reports/books_research/dino_surge")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.all_modes and args.mode is not None:
        p.error("--all-modes 와 --mode 는 동시 사용 불가")
    if not args.all_modes and args.mode is None:
        p.error("--mode 또는 --all-modes 둘 중 하나 필수")

    if args.start is None or args.end is None:
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MIN(date), MAX(date) FROM daily_prices")
            mn, mx = cur.fetchone()
        args.start = args.start or str(mn)
        args.end = args.end or str(mx)
    LOG.info(f"period: {args.start} ~ {args.end}  no_fin={args.no_fin} min_fin_score={args.min_fin_score}")

    universe = _load_top_volume_universe(args.start, args.end, args.top_n)
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    data = _load_daily_adj(universe, args.start, args.end)
    LOG.info(f"loaded data for {len(data)} stocks")
    if not data:
        LOG.error("no data — aborting")
        return

    # 재무 precompute (no-fin 이면 전부 None → 재무축 중립)
    fin_by_idx_map: Dict[str, List[Optional[dict]]] = {}
    if args.no_fin:
        for code, df in data.items():
            fin_by_idx_map[code] = [None] * len(df)
    else:
        fs_ts = _load_fundamentals_timeseries(list(data.keys()))
        LOG.info(f"loaded fundamentals for {len(fs_ts)} stocks")
        for code, df in data.items():
            fin_by_idx_map[code] = _build_fin_by_idx(df, fs_ts.get(code, []), args.min_fin_score)

    params = VARIANT_PARAMS[args.variant]
    rule_names = [cls().name for cls in ALL_RULES]
    combos = [("single", n) for n in rule_names] + [("all_AND", None)] if args.all_modes else [(args.mode, args.rule)]

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = Path("reports/books_research/leaderboard.parquet")

    from backtest.book_backtester import append_leaderboard

    fin_tag = "_nofin" if args.no_fin else ""
    for mode, rule_name in combos:
        strategy = build_strategy(mode=mode, target_rule=rule_name)
        per_stock_pnl = []
        all_trades = []
        per_stock_metrics = []
        for code, df in data.items():
            res = simulate_one_stock(
                code=code, df=df, fin_by_idx=fin_by_idx_map[code], strategy=strategy,
                stop_loss_pct=params["stop_loss_pct"],
                take_profit_pct=params["take_profit_pct"],
                max_hold_bars=params["max_hold_bars"],
                trail_ma=params["trail_ma"],
                exit_mode=params.get("exit_mode", "fixed"),
                trail_ema=params.get("trail_ema", 13),
                trend_ema=params.get("trend_ema", 65),
            )
            metrics = _compute_metrics(10_000_000, res["equity_curve"], res["trades"])
            per_stock_metrics.append(metrics)
            per_stock_pnl.append(metrics["pnl_pct"])
            all_trades.extend(res["trades"])

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
        LOG.info(f"[variant={args.variant}{fin_tag} {mode}/{label}] "
                 f"sl={params['stop_loss_pct']} tp={params['take_profit_pct']} mh={params['max_hold_bars']} "
                 f"trail_ma={params['trail_ma']} n_stocks={n_stocks} n_trades={agg['n_trades']} "
                 f"pnl={agg['pnl_pct']:.4%} sharpe={agg['sharpe']:.2f} hit={agg['hit_rate']:.2%}")

        out_file = reports_dir / f"results_variant{args.variant}{fin_tag}_{mode}_{label}.parquet"
        if all_trades:
            pd.DataFrame(all_trades).to_parquet(out_file, index=False)

        append_leaderboard(
            path=leaderboard_path,
            row={
                "book_id": "dino_surge",
                "book_name": BOOK_META["name"],
                "period": "daily_full",
                "rule_combo": label,
                "mode": mode,
                "variant": args.variant + fin_tag,
                "universe": f"top_volume:{args.top_n}",
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
