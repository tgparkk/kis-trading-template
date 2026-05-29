"""통합 단일 계좌 포트폴리오 시뮬레이터 (책 베스트 룰).

기존 scripts/run_elder_triple_screen.py / run_minervini_vcp.py 는 종목당 100만원
"독립 계좌"를 굴려 종목별 수익률을 단순평균(book_backtester.run_universe)한다.
그래서 자본효율(투자시간 비중)을 거의 반영 못한 "룰 엣지" 측정치였다.

이 스크립트는 **단일 계좌**로 top_volume:50 universe 전체를 매일 순회하며
최대 동시보유 K종목·종목당 균등비중으로 운용하는 실계좌 시뮬을 수행한다.

룰/청산 로직은 기존 elder/minervini 스크립트의 simulate_one_stock 과 정확히 동일하게 복제:
- Elder variant A: Screen 3 매수스톱(전일 고가+1틱, 최대 N_TRAIL=2일 추적) +
  sl 8% / tp 30% / max_hold 100 / EMA13 trail(수익중) / ema65 추세반전 청산.
- Minervini variant B (volume_dryup): 신호 → 다음봉 시가 매수 + sl 8% / tp 12% / mh 20.

체결: no-lookahead — 신호/청산판정은 t봉(df[:i+1])까지만, 체결은 t+1봉 OHLC.
거래비용: 수수료 0.015%×2 + 거래세 0.18%(매도) + 슬리피지 0.10%×2 ≈ 왕복 0.41%.

usage:
  python scripts/portfolio_sim_elder.py                       # Elder A, K=5/10/20 + KOSPI
  python scripts/portfolio_sim_elder.py --with-minervini      # + Minervini B, K=10
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

from strategies.base import SignalType
from strategies.books.elder_triple_screen.rules import ema, krx_tick, screen1_uptrend
from strategies.books.elder_triple_screen.strategy import build_strategy as build_elder
from strategies.books.minervini_vcp.strategy import build_strategy as build_minervini

LOG = logging.getLogger("portfolio_sim")

# 거래비용 (기존 book_backtester / run_* 스크립트 상수 재사용)
COMMISSION_RATE = 0.00015   # 매수·매도 각각
TAX_RATE = 0.0018           # 매도 시 거래세
SLIPPAGE_RATE = 0.001       # 단방향 슬리피지
#   → 왕복 ≈ commission×2 + tax + slippage×2 = 0.41%

N_TRAIL = 2                 # Elder Screen 3 매수스톱 추적 최대 일수
WARMUP_BARS = 70            # Elder 룰 요구 (len>=70). Minervini volume_dryup은 40이면 충분하나 통일.
INITIAL_CAPITAL = 10_000_000

ELDER_A_PARAMS = dict(stop_loss_pct=0.08, take_profit_pct=0.30, max_hold_bars=100,
                      trail_ema=13, trend_flip_exit=True)
MINERVINI_B_PARAMS = dict(stop_loss_pct=0.08, take_profit_pct=0.12, max_hold_bars=20)


# --------------------------------------------------------------------------- #
# 데이터 로딩 (run_elder_triple_screen._load_daily_adj 와 동일 로직)
# --------------------------------------------------------------------------- #
def _load_top_volume_universe(start: str, end: str, top_n: int = 50) -> List[str]:
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


def _load_kospi(start: str, end: str) -> pd.DataFrame:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT date, close FROM daily_prices
            WHERE stock_code = 'KOSPI' AND date >= %s AND date <= %s
            ORDER BY date ASC
        """, (start, end))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df[df["close"] > 0].dropna().reset_index(drop=True)
    return df


# --------------------------------------------------------------------------- #
# 종목별 정렬: 모든 종목 df를 공통 거래일 인덱스(union)에 맞춰 row dict 리스트로.
# 각 종목은 자기 데이터가 시작되기 전 날짜에는 등장하지 않음(None).
# --------------------------------------------------------------------------- #
def _build_calendar(data: Dict[str, pd.DataFrame]) -> List[pd.Timestamp]:
    all_dates = set()
    for df in data.values():
        all_dates.update(df["datetime"].tolist())
    return sorted(all_dates)


# --------------------------------------------------------------------------- #
# Elder variant A 청산 판정 (run_elder_triple_screen 와 동일)
#   df_close: 종목 종가 시리즈(0..i), entry_price, hold_bars(=i-entry_idx)
#   반환: exit_reason 또는 None
# --------------------------------------------------------------------------- #
def _elder_exit_reason(df_local: pd.DataFrame, i: int, entry_price: float, entry_idx: int,
                       p: dict) -> Optional[str]:
    cur_close = float(df_local["close"].iloc[i])
    ret = (cur_close - entry_price) / entry_price
    hold_bars = i - entry_idx
    if ret <= -p["stop_loss_pct"]:
        return "stop_loss"
    if ret >= p["take_profit_pct"]:
        return "take_profit"
    if hold_bars >= p["max_hold_bars"]:
        return "max_hold"
    if p["trail_ema"] is not None and ret > 0:
        ema_trail = ema(df_local["close"].iloc[: i + 1].astype(float), p["trail_ema"])
        if cur_close < float(ema_trail.iloc[-1]):
            return "trail_ema"
    if p["trend_flip_exit"] and i >= 5:
        ema65 = ema(df_local["close"].iloc[: i + 1].astype(float), 65)
        if float(ema65.iloc[-1]) < float(ema65.iloc[-6]):
            return "trend_flip"
    return None


def _minervini_exit_reason(df_local: pd.DataFrame, i: int, entry_price: float, entry_idx: int,
                           p: dict) -> Optional[str]:
    cur_close = float(df_local["close"].iloc[i])
    ret = (cur_close - entry_price) / entry_price
    hold_bars = i - entry_idx
    if ret <= -p["stop_loss_pct"]:
        return "stop_loss"
    if ret >= p["take_profit_pct"]:
        return "take_profit"
    if hold_bars >= p["max_hold_bars"]:
        return "max_hold"
    return None


# --------------------------------------------------------------------------- #
# 통합 포트폴리오 시뮬레이션
# --------------------------------------------------------------------------- #
def simulate_portfolio(
    data: Dict[str, pd.DataFrame],
    calendar: List[pd.Timestamp],
    strategy,
    exit_reason_fn,
    exit_params: dict,
    max_positions: int,
    use_buy_stop: bool,
    rs_wide: Optional[pd.DataFrame] = None,
    initial_capital: float = INITIAL_CAPITAL,
) -> dict:
    """단일 계좌 포트폴리오 시뮬.

    매 거래일 d (calendar[t]):
      1) 각 종목 df의 로컬 인덱스 i = (d 위치). i<WARMUP 또는 데이터 없으면 스킵.
      2) 보유 포지션: t봉 종가로 청산조건 판정 → 만족 시 t+1봉(다음 거래일) 시가 체결 예약.
      3) 신규 진입: t봉 신호 평가 → t+1봉 체결(Elder는 매수스톱 추적, Minervini는 단순 시가).
      4) 슬롯(가용 = max_positions - 현재보유)만큼만 신규 진입. 신호 많으면 종목코드순 선택(명시적 자의 가정).
      5) equity = 현금 + Σ(보유수량 × t봉 종가).  ← mark-to-market

    체결가는 항상 "다음 거래일" 봉으로 계산하므로 no-lookahead 유지.
    동시 다종목 체결은 그날 시가 기준 가용현금을 균등분할(남은 슬롯 수로 나눔).
    """
    # 각 종목별 날짜→로컬 인덱스 매핑 + numpy 캐시
    idx_map: Dict[str, Dict[pd.Timestamp, int]] = {}
    for code, df in data.items():
        idx_map[code] = {d: i for i, d in enumerate(df["datetime"])}

    cash = initial_capital
    positions: Dict[str, dict] = {}   # code -> {entry_idx, entry_price, qty}
    pending_buy: Dict[str, dict] = {}  # code -> Elder 매수스톱 대기 {trigger_high_idx, days_left, reasons}
    # 다음 거래일 실행 예약: 청산 코드 집합 / 신규진입 후보 (Minervini 단순 시가용)
    trades: List[dict] = []
    equity_curve: List[float] = []
    equity_dates: List[pd.Timestamp] = []
    invested_ratio_series: List[float] = []
    n_holdings_series: List[int] = []

    n_days = len(calendar)
    # t 일에 결정(신호/청산판정) → t+1 일 시가 체결. 마지막 날은 체결 불가하므로 n_days-1 까지 결정.
    for t in range(n_days - 1):
        d = calendar[t]
        d_next = calendar[t + 1]

        # ---- (A) 청산: 보유 종목 중 t봉에서 청산조건 만족 → d_next 시가 체결 ----
        for code in list(positions.keys()):
            df = data[code]
            i = idx_map[code].get(d)
            if i is None:
                continue  # 그 종목은 d일 거래 없음(정지 등) → 판정 보류
            j = idx_map[code].get(d_next)
            if j is None:
                continue  # 다음 거래일 체결 봉 없음 → 보류
            pos = positions[code]
            reason = exit_reason_fn(df, i, pos["entry_price"], pos["entry_idx"], exit_params)
            if reason is not None:
                fill = float(df["open"].iloc[j]) * (1 - SLIPPAGE_RATE)
                proceeds = pos["qty"] * fill
                fee = proceeds * (COMMISSION_RATE + TAX_RATE)
                cash += proceeds - fee
                pnl = (fill - pos["entry_price"]) / pos["entry_price"]
                trades.append({
                    "stock_code": code, "side": "sell", "datetime": str(d_next),
                    "price": fill, "qty": pos["qty"], "reason": reason,
                    "entry_price": pos["entry_price"], "pnl_pct": pnl,
                })
                del positions[code]

        # ---- (B) Elder 매수스톱 대기 처리 (d_next OHLC로 체결 판정) ----
        if use_buy_stop:
            for code in list(pending_buy.keys()):
                if code in positions:
                    del pending_buy[code]
                    continue
                df = data[code]
                j = idx_map[code].get(d_next)
                if j is None:
                    continue  # 다음 거래일 봉 없음 → 보류(추적일 미차감)
                pend = pending_buy[code]
                trig_idx = pend["trigger_high_idx"]
                prior_high = float(df["high"].iloc[trig_idx])
                trigger = prior_high + krx_tick(prior_high)
                nxt_open = float(df["open"].iloc[j])
                nxt_high = float(df["high"].iloc[j])
                fill = None
                if nxt_open >= trigger:
                    fill = nxt_open * (1 + SLIPPAGE_RATE)
                elif nxt_high >= trigger:
                    fill = trigger * (1 + SLIPPAGE_RATE)
                if fill is not None:
                    # 슬롯·현금 가드는 (C)에서 신규진입과 함께 일괄 처리 위해 후보로만 표시
                    pend["_fill"] = fill
                    pend["_fill_idx"] = j
                else:
                    pend["days_left"] -= 1
                    pend["trigger_high_idx"] = j
                    window_close = df["close"].iloc[: j + 1].astype(float)
                    if pend["days_left"] <= 0 or not screen1_uptrend(window_close):
                        del pending_buy[code]

        # ---- (C) 신규 진입 후보 수집 (t봉 신호) ----
        # Elder: 신규 pending 등록(다음날부터 매수스톱 추적). 이미 보유/대기 중이면 스킵.
        # Minervini: 신호 → d_next 시가 매수 후보.
        buy_candidates: List[dict] = []  # {code, fill, fill_idx}  (즉시 체결형)
        if use_buy_stop:
            # 이미 _fill이 잡힌 대기 종목들을 체결 후보로
            for code, pend in pending_buy.items():
                if "_fill" in pend and code not in positions:
                    buy_candidates.append({"code": code, "fill": pend["_fill"],
                                           "fill_idx": pend["_fill_idx"],
                                           "reasons": pend.get("reasons")})
        # 신호 평가 → Elder는 신규 pending 등록, Minervini는 즉시 후보
        for code, df in data.items():
            if code in positions:
                continue
            if use_buy_stop and code in pending_buy:
                continue
            i = idx_map[code].get(d)
            if i is None or i < WARMUP_BARS:
                continue
            j = idx_map[code].get(d_next)
            if j is None:
                continue
            window = df.iloc[: i + 1]
            if rs_wide is not None:
                rs_val = float(rs_wide.loc[d, code]) if (d in rs_wide.index and code in rs_wide.columns
                                                         and pd.notna(rs_wide.loc[d, code])) else np.nan
                signal = strategy.generate_signal_with_extra_ctx(code, window, "daily", {"rs_value": rs_val})
            else:
                signal = strategy.generate_signal_with_extra_ctx(code, window, "daily", {})
            if signal is None or signal.signal_type not in (SignalType.BUY, SignalType.STRONG_BUY):
                continue
            if use_buy_stop:
                pending_buy[code] = {"trigger_high_idx": i, "days_left": N_TRAIL,
                                     "reasons": signal.reasons}
            else:
                fill = float(df["open"].iloc[j]) * (1 + SLIPPAGE_RATE)
                buy_candidates.append({"code": code, "fill": fill, "fill_idx": j,
                                       "reasons": signal.reasons})

        # ---- (D) 슬롯 배정 + 체결 (균등비중) ----
        # 자의 가정: 신호가 슬롯보다 많으면 종목코드 오름차순으로 선택.
        buy_candidates.sort(key=lambda c: c["code"])
        free_slots = max_positions - len(positions)
        if free_slots > 0 and buy_candidates and cash > 0:
            selected = buy_candidates[:free_slots]
            # 종목당 균등비중 = 가용현금 / 남은 슬롯(=min(free_slots, 후보수))
            per_slot_cash = (cash * 0.99) / max(free_slots, 1)
            for cand in selected:
                code = cand["code"]
                fill = cand["fill"]
                qty = int(per_slot_cash // fill)
                if qty <= 0:
                    continue
                cost = qty * fill
                fee = cost * COMMISSION_RATE
                if cost + fee > cash:
                    qty = int((cash * 0.999) // (fill * (1 + COMMISSION_RATE)))
                    if qty <= 0:
                        continue
                    cost = qty * fill
                    fee = cost * COMMISSION_RATE
                cash -= cost + fee
                positions[code] = {"entry_idx": cand["fill_idx"], "entry_price": fill, "qty": qty}
                trades.append({
                    "stock_code": code, "side": "buy", "datetime": str(d_next),
                    "price": fill, "qty": qty,
                    "reason": ",".join(cand.get("reasons") or ["signal"]),
                    "entry_price": fill, "pnl_pct": 0.0,
                })
                if use_buy_stop and code in pending_buy:
                    del pending_buy[code]
        # 체결 안 된 매수스톱 _fill 후보는 다음 루프서 재평가되지 않도록 정리
        if use_buy_stop:
            for code in list(pending_buy.keys()):
                if "_fill" in pending_buy[code] and code not in positions:
                    # 슬롯 부족으로 미체결 → 대기 취소(자의 가정: 매수스톱은 1회성)
                    del pending_buy[code]

        # ---- (E) mark-to-market equity (d_next 봉이 아닌 "체결 후 + 현재 d 종가" 평가) ----
        # 체결은 d_next 시가에 일어났으므로, equity 측정 기준일을 d_next 종가로 두면 lookahead.
        # 일관성을 위해 equity는 "체결 반영 후, d_next 시가 기준 보유 평가"로 기록.
        mtm = cash
        invested = 0.0
        for code, pos in positions.items():
            j = idx_map[code].get(d_next)
            if j is not None:
                px = float(data[code]["open"].iloc[j])
            else:
                # d_next에 봉 없으면 마지막 알려진 종가
                i_last = idx_map[code].get(d)
                px = float(data[code]["close"].iloc[i_last]) if i_last is not None else pos["entry_price"]
            val = pos["qty"] * px
            mtm += val
            invested += val
        equity_curve.append(mtm)
        equity_dates.append(d_next)
        invested_ratio_series.append(invested / mtm if mtm > 0 else 0.0)
        n_holdings_series.append(len(positions))

    # ---- 마지막 날 강제 청산 (calendar[-1] 종가) ----
    last_d = calendar[-1]
    for code in list(positions.keys()):
        df = data[code]
        i = idx_map[code].get(last_d)
        if i is None:
            i = len(df) - 1  # 마지막 알려진 봉
        pos = positions[code]
        fill = float(df["close"].iloc[i]) * (1 - SLIPPAGE_RATE)
        proceeds = pos["qty"] * fill
        fee = proceeds * (COMMISSION_RATE + TAX_RATE)
        cash += proceeds - fee
        trades.append({
            "stock_code": code, "side": "sell", "datetime": str(last_d),
            "price": fill, "qty": pos["qty"], "reason": "forced_close",
            "entry_price": pos["entry_price"],
            "pnl_pct": (fill - pos["entry_price"]) / pos["entry_price"],
        })
        del positions[code]
    equity_curve.append(cash)
    equity_dates.append(last_d)
    invested_ratio_series.append(0.0)
    n_holdings_series.append(0)

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "equity_dates": equity_dates,
        "invested_ratio": invested_ratio_series,
        "n_holdings": n_holdings_series,
    }


# --------------------------------------------------------------------------- #
# 메트릭
# --------------------------------------------------------------------------- #
def _years_between(d0: pd.Timestamp, d1: pd.Timestamp) -> float:
    return (pd.Timestamp(d1) - pd.Timestamp(d0)).days / 365.25


def compute_portfolio_metrics(res: dict, initial: float) -> dict:
    eq = np.array(res["equity_curve"], dtype=float)
    dates = res["equity_dates"]
    final = eq[-1]
    total_ret = (final - initial) / initial
    years = _years_between(dates[0], dates[-1])
    cagr = (final / initial) ** (1 / years) - 1 if years > 0 and final > 0 else 0.0
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) > 1 and rets.std() > 0:
        sharpe = float(rets.mean() / rets.std() * math.sqrt(252))
    else:
        sharpe = 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min()) if len(dd) else 0.0
    calmar = float(cagr / max_dd) if max_dd > 1e-9 else 0.0
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    wins = sum(1 for t in sells if t["pnl_pct"] > 0)
    hit = wins / len(sells) if sells else 0.0
    avg_invested = float(np.mean(res["invested_ratio"])) if res["invested_ratio"] else 0.0
    avg_holdings = float(np.mean(res["n_holdings"])) if res["n_holdings"] else 0.0
    return dict(
        total_ret=total_ret, cagr=cagr, sharpe=sharpe, max_dd=max_dd, calmar=calmar,
        hit_rate=hit, n_trades=len(sells), avg_invested_ratio=avg_invested,
        avg_holdings=avg_holdings, final_equity=final, years=years,
    )


def compute_kospi_metrics(kospi: pd.DataFrame, initial: float = INITIAL_CAPITAL) -> dict:
    close = kospi["close"].astype(float).values
    dates = kospi["date"].tolist()
    eq = close / close[0] * initial
    total_ret = (eq[-1] - initial) / initial
    years = _years_between(dates[0], dates[-1])
    cagr = (eq[-1] / initial) ** (1 / years) - 1 if years > 0 else 0.0
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min())
    calmar = float(cagr / max_dd) if max_dd > 1e-9 else 0.0
    return dict(total_ret=total_ret, cagr=cagr, sharpe=sharpe, max_dd=max_dd,
                calmar=calmar, years=years, daily_rets=rets, dates=dates[1:])


def compute_alpha_beta(port_eq: np.ndarray, port_dates: List[pd.Timestamp],
                       kospi: pd.DataFrame) -> dict:
    """포트폴리오 일간수익률을 KOSPI 일간수익률에 회귀 → beta, alpha(연율), 정보비율."""
    pser = pd.Series(port_eq, index=pd.to_datetime(port_dates)).sort_index()
    pser = pser[~pser.index.duplicated(keep="last")]
    pret = pser.pct_change().dropna()
    kser = pd.Series(kospi["close"].astype(float).values, index=pd.to_datetime(kospi["date"]))
    kret = kser.pct_change().dropna()
    joined = pd.concat([pret.rename("p"), kret.rename("k")], axis=1).dropna()
    if len(joined) < 30:
        return dict(beta=float("nan"), alpha_ann=float("nan"), info_ratio=float("nan"), n=len(joined))
    cov = np.cov(joined["p"], joined["k"])
    beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else float("nan")
    alpha_daily = float(joined["p"].mean() - beta * joined["k"].mean())
    alpha_ann = alpha_daily * 252
    active = joined["p"] - joined["k"]
    info_ratio = float(active.mean() / active.std() * math.sqrt(252)) if active.std() > 0 else float("nan")
    return dict(beta=beta, alpha_ann=alpha_ann, info_ratio=info_ratio, n=len(joined))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--ks", type=int, nargs="+", default=[5, 10, 20])
    p.add_argument("--with-minervini", action="store_true")
    p.add_argument("--reports-dir", default="reports/10pct_strategy")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.start is None or args.end is None:
        from db.connection import DatabaseConnection
        with DatabaseConnection.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MIN(date), MAX(date) FROM daily_prices WHERE stock_code != 'KOSPI'")
            mn, mx = cur.fetchone()
        args.start = args.start or str(mn)
        args.end = args.end or str(mx)
    LOG.info(f"period: {args.start} ~ {args.end}")

    universe = _load_top_volume_universe(args.start, args.end, args.top_n)
    LOG.info(f"universe size: {len(universe)}")
    data = _load_daily_adj(universe, args.start, args.end)
    LOG.info(f"loaded data for {len(data)} stocks")
    if not data:
        LOG.error("no data — aborting")
        return
    calendar = _build_calendar(data)
    LOG.info(f"calendar trading days: {len(calendar)} ({calendar[0].date()} ~ {calendar[-1].date()})")

    kospi = _load_kospi(args.start, args.end)
    LOG.info(f"KOSPI days: {len(kospi)}")
    kospi_m = compute_kospi_metrics(kospi)

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    equity_frames = {}

    # ---- Elder A 통합 (K=5/10/20) ----
    elder_strategy = build_elder(mode="single", target_rule="triple_screen_ema_pullback")
    for K in args.ks:
        LOG.info(f"=== Elder ema_pullback A | K={K} ===")
        res = simulate_portfolio(
            data=data, calendar=calendar, strategy=elder_strategy,
            exit_reason_fn=_elder_exit_reason, exit_params=ELDER_A_PARAMS,
            max_positions=K, use_buy_stop=True,
        )
        m = compute_portfolio_metrics(res, INITIAL_CAPITAL)
        ab = compute_alpha_beta(np.array(res["equity_curve"]), res["equity_dates"], kospi)
        m["alpha_vs_kospi"] = m["cagr"] - kospi_m["cagr"]
        m.update({"beta": ab["beta"], "alpha_ann": ab["alpha_ann"], "info_ratio": ab["info_ratio"]})
        m.update({"strategy": "elder_ema_pullback_A", "K": K})
        rows.append(m)
        equity_frames[f"elder_A_K{K}"] = pd.DataFrame({
            "date": res["equity_dates"], "equity": res["equity_curve"],
            "invested_ratio": res["invested_ratio"], "n_holdings": res["n_holdings"],
        })
        pd.DataFrame(res["trades"]).to_parquet(reports_dir / f"portfolio_elder_A_K{K}_trades.parquet", index=False)
        LOG.info(f"  total={m['total_ret']:.2%} CAGR={m['cagr']:.2%} Sharpe={m['sharpe']:.2f} "
                 f"MaxDD={m['max_dd']:.2%} invested={m['avg_invested_ratio']:.1%} trades={m['n_trades']}")

    # ---- Minervini B (volume_dryup), K=10 ----
    if args.with_minervini:
        LOG.info("=== Minervini volume_dryup B | K=10 ===")
        mv_strategy = build_minervini(mode="single", target_rule="volume_dryup")
        res = simulate_portfolio(
            data=data, calendar=calendar, strategy=mv_strategy,
            exit_reason_fn=_minervini_exit_reason, exit_params=MINERVINI_B_PARAMS,
            max_positions=10, use_buy_stop=False, rs_wide=None,
        )
        m = compute_portfolio_metrics(res, INITIAL_CAPITAL)
        ab = compute_alpha_beta(np.array(res["equity_curve"]), res["equity_dates"], kospi)
        m["alpha_vs_kospi"] = m["cagr"] - kospi_m["cagr"]
        m.update({"beta": ab["beta"], "alpha_ann": ab["alpha_ann"], "info_ratio": ab["info_ratio"]})
        m.update({"strategy": "minervini_volume_dryup_B", "K": 10})
        rows.append(m)
        equity_frames["minervini_B_K10"] = pd.DataFrame({
            "date": res["equity_dates"], "equity": res["equity_curve"],
            "invested_ratio": res["invested_ratio"], "n_holdings": res["n_holdings"],
        })
        pd.DataFrame(res["trades"]).to_parquet(reports_dir / "portfolio_minervini_B_K10_trades.parquet", index=False)
        LOG.info(f"  total={m['total_ret']:.2%} CAGR={m['cagr']:.2%} Sharpe={m['sharpe']:.2f} "
                 f"MaxDD={m['max_dd']:.2%} invested={m['avg_invested_ratio']:.1%} trades={m['n_trades']}")

    # ---- 결과 저장 ----
    summary = pd.DataFrame(rows)
    summary_path = reports_dir / "portfolio_sim_summary.parquet"
    summary.to_parquet(summary_path, index=False)
    for name, frame in equity_frames.items():
        frame.to_parquet(reports_dir / f"portfolio_equity_{name}.parquet", index=False)

    # KOSPI 행
    kospi_row = dict(strategy="KOSPI_buy_hold", K=np.nan, total_ret=kospi_m["total_ret"],
                     cagr=kospi_m["cagr"], sharpe=kospi_m["sharpe"], max_dd=kospi_m["max_dd"],
                     calmar=kospi_m["calmar"])

    # ---- 콘솔 리포트 ----
    print("\n" + "=" * 100)
    print("통합 포트폴리오 시뮬레이션 결과 (단일 계좌, initial=10,000,000원)")
    print(f"기간: {calendar[0].date()} ~ {calendar[-1].date()}  ({kospi_m['years']:.2f}년)  universe=top_volume:{args.top_n}")
    print("=" * 100)
    hdr = (f"{'strategy':<26}{'K':>4}{'total':>10}{'CAGR':>9}{'Sharpe':>8}"
           f"{'MaxDD':>9}{'Calmar':>8}{'invested':>10}{'avgHold':>9}{'trades':>8}{'alpha':>9}")
    print(hdr)
    print("-" * 100)
    for r in rows:
        print(f"{r['strategy']:<26}{int(r['K']):>4}{r['total_ret']:>9.1%} {r['cagr']:>8.2%} "
              f"{r['sharpe']:>7.2f} {r['max_dd']:>8.1%} {r['calmar']:>7.2f} "
              f"{r['avg_invested_ratio']:>9.1%} {r['avg_holdings']:>8.1f} {r['n_trades']:>7d} "
              f"{r['alpha_vs_kospi']:>8.2%}")
    print(f"{kospi_row['strategy']:<26}{'--':>4}{kospi_row['total_ret']:>9.1%} {kospi_row['cagr']:>8.2%} "
          f"{kospi_row['sharpe']:>7.2f} {kospi_row['max_dd']:>8.1%} {kospi_row['calmar']:>7.2f} "
          f"{'--':>9} {'--':>8} {'--':>7} {'--':>8}")
    print("-" * 100)
    print("\n[알파/베타 상세 (KOSPI 회귀)]")
    for r in rows:
        print(f"  {r['strategy']} K={int(r['K'])}: beta={r.get('beta', float('nan')):.2f} "
              f"alpha_ann={r.get('alpha_ann', float('nan')):.2%} info_ratio={r.get('info_ratio', float('nan')):.2f}")
    print(f"\nsummary parquet: {summary_path}")
    print("=" * 100)


if __name__ == "__main__":
    main()
