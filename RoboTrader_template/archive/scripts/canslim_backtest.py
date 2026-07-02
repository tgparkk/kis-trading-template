"""CANSLIM 스크리너 결과를 다음 봉 시가 매수, -7%/+20%/40일 청산.

입력: screener_daily.parquet (date, stock_code, momentum_score, ...)
가격: daily_prices (adj_factor 반영된 수정주가 사용)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = logging.getLogger("canslim_backtest")


def _load_prices(stock_codes: list, start: str, end: str) -> dict:
    """종목별 daily_prices 로드. start/end는 YYYY-MM-DD."""
    from db.connection import DatabaseConnection
    prices = {}
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, close, adj_factor
                FROM daily_prices
                WHERE stock_code = %s
                  AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start, end))
            rows = cur.fetchall()
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'adj_factor'])
            df['date'] = pd.to_datetime(df['date'])
            df['open'] = pd.to_numeric(df['open'], errors='coerce')
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['adj_factor'] = pd.to_numeric(df['adj_factor'], errors='coerce').fillna(1.0)
            # adj_factor 적용
            df['open_adj'] = df['open'] * df['adj_factor']
            df['close_adj'] = df['close'] * df['adj_factor']
            df = df.dropna(subset=['open_adj', 'close_adj'])
            if len(df) < 5:
                continue
            prices[code] = df.set_index('date')
    return prices


def simulate_trades(screener: pd.DataFrame, prices: dict,
                    stop_loss: float, take_profit: float,
                    max_hold_days: int) -> pd.DataFrame:
    """스크리너 신호 → 다음 봉 시가 매수 → 청산 시뮬레이션."""
    trades = []

    # 종목별로 처리 (신호 중복 시 보유 중이면 건너뜀)
    for code in sorted(screener['stock_code'].unique()):
        if code not in prices:
            LOG.debug(f"{code}: daily_prices 없음 — 스킵")
            continue

        df_price = prices[code]
        code_signals = screener[screener['stock_code'] == code].sort_values('date')

        in_position = False
        for _, sig_row in code_signals.iterrows():
            if in_position:
                continue
            signal_date = sig_row['date']

            # 다음 거래일 (signal_date 이후 첫 봉)
            future_dates = df_price.index[df_price.index > signal_date]
            if len(future_dates) == 0:
                continue
            entry_date = future_dates[0]
            entry_bar = df_price.loc[entry_date]
            entry_price = entry_bar['open_adj']
            if pd.isna(entry_price) or entry_price <= 0:
                continue

            stop_price = entry_price * (1 - stop_loss)
            target_price = entry_price * (1 + take_profit)

            # 이후 봉들 순회
            hold_bars = df_price[df_price.index > entry_date]
            exit_date = None
            exit_price = None
            exit_reason = None

            for hold_i, (bar_date, bar) in enumerate(hold_bars.iterrows(), start=1):
                close = bar['close_adj']
                if pd.isna(close):
                    continue
                if close <= stop_price:
                    exit_reason = "stop_loss"
                elif close >= target_price:
                    exit_reason = "take_profit"
                elif hold_i >= max_hold_days:
                    exit_reason = "max_hold"

                if exit_reason:
                    exit_date = bar_date
                    exit_price = close
                    break

            if exit_date is None:
                # 데이터 끝까지 보유 — 강제청산
                last_date = hold_bars.index[-1] if len(hold_bars) > 0 else entry_date
                last_close = hold_bars.iloc[-1]['close_adj'] if len(hold_bars) > 0 else entry_price
                exit_date = last_date
                exit_price = last_close
                exit_reason = "end_of_data"

            pnl_pct = (exit_price - entry_price) / entry_price
            hold_days = (exit_date - entry_date).days

            trades.append({
                'stock_code': code,
                'entry_date': entry_date,
                'entry_price': entry_price,
                'exit_date': exit_date,
                'exit_price': exit_price,
                'pnl_pct': pnl_pct,
                'hold_days': hold_days,
                'reason': exit_reason,
                'momentum_score': sig_row.get('momentum_score', np.nan),
                'ni_yoy': sig_row.get('ni_yoy', np.nan),
                'roe': sig_row.get('roe', np.nan),
            })
            in_position = True  # 이 종목은 한 번 거래 완료로 간주

    return pd.DataFrame(trades)


def print_summary(df: pd.DataFrame, args) -> None:
    print()
    print("=" * 50)
    print("  CANSLIM Phase A 백테스트 결과")
    print("=" * 50)
    print(f"스크리너: {args.screener}")
    print(f"기간: {args.start} ~ {args.end}")
    print(f"손절: -{args.stop_loss*100:.0f}% / 익절: +{args.take_profit*100:.0f}% / 최대보유: {args.max_hold_days}일")
    print()

    if len(df) == 0:
        print("거래 없음")
        return

    n = len(df)
    wins = (df['pnl_pct'] > 0).sum()
    win_rate = wins / n
    avg_pnl = df['pnl_pct'].mean()
    median_pnl = df['pnl_pct'].median()
    total_pnl = df['pnl_pct'].sum()
    avg_hold = df['hold_days'].mean()

    # 수익/손실 분리
    win_avg = df.loc[df['pnl_pct'] > 0, 'pnl_pct'].mean() if wins > 0 else 0.0
    loss_avg = df.loc[df['pnl_pct'] <= 0, 'pnl_pct'].mean() if (n - wins) > 0 else 0.0
    payoff = abs(win_avg / loss_avg) if loss_avg != 0 else float('inf')

    print(f"총 거래: {n}")
    print(f"승률: {win_rate:.1%} ({wins}/{n})")
    print(f"평균 PnL/거래: {avg_pnl:.2%}")
    print(f"중간값 PnL: {median_pnl:.2%}")
    print(f"누적 PnL: {total_pnl:.2%} (단순 합산)")
    print(f"평균 보유일: {avg_hold:.1f}일")
    print(f"평균 수익/거래 (승): {win_avg:.2%}")
    print(f"평균 손실/거래 (패): {loss_avg:.2%}")
    print(f"수익:손실 비율: {payoff:.2f}")
    print()
    print("청산 사유 분포:")
    print(df['reason'].value_counts().to_string())
    print()
    print("종목별 결과:")
    stock_summary = (df.groupby('stock_code')
                       .agg(trades=('pnl_pct', 'count'),
                            avg_pnl=('pnl_pct', 'mean'),
                            total_pnl=('pnl_pct', 'sum'))
                       .sort_values('avg_pnl', ascending=False))
    print(stock_summary.to_string())
    print()
    print("개별 거래 내역:")
    display_cols = ['stock_code', 'entry_date', 'exit_date', 'hold_days', 'pnl_pct', 'reason']
    print(df[display_cols].sort_values('entry_date').to_string(index=False))


def main():
    p = argparse.ArgumentParser(description="CANSLIM 백테스트")
    p.add_argument("--screener",
                   default="reports/books_research/oneil_canslim/screener_daily.parquet")
    p.add_argument("--start", default="2025-07-01")
    p.add_argument("--end", default="2026-05-28")
    p.add_argument("--stop-loss", type=float, default=0.07)
    p.add_argument("--take-profit", type=float, default=0.20)
    p.add_argument("--max-hold-days", type=int, default=40)
    p.add_argument("--out",
                   default="reports/books_research/oneil_canslim/canslim_phase_a_trades.parquet")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    screener = pd.read_parquet(args.screener)
    screener['date'] = pd.to_datetime(screener['date'])
    # 백테스트 기간 내 신호만 필터
    screener = screener[
        (screener['date'] >= args.start) &
        (screener['date'] <= args.end)
    ].copy()
    LOG.info(f"스크리너 신호: {len(screener)} entries, "
             f"{screener['stock_code'].nunique()} 종목, "
             f"기간 {screener['date'].min().date() if len(screener) > 0 else 'N/A'} ~ "
             f"{screener['date'].max().date() if len(screener) > 0 else 'N/A'}")

    if len(screener) == 0:
        print("기간 내 스크리너 신호 없음")
        return

    stock_codes = sorted(screener['stock_code'].unique().tolist())
    LOG.info(f"일봉 가격 로드 중 ({len(stock_codes)} 종목)")
    prices = _load_prices(stock_codes, args.start, args.end)
    LOG.info(f"가격 로드 완료: {len(prices)} 종목")

    LOG.info("백테스트 시뮬레이션 실행 중")
    df_trades = simulate_trades(screener, prices,
                                args.stop_loss, args.take_profit,
                                args.max_hold_days)

    print_summary(df_trades, args)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_trades.to_parquet(out_path, index=False)
    LOG.info(f"저장 완료: {out_path}")


if __name__ == "__main__":
    main()
