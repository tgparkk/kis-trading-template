"""CANSLIM Phase B — 평평한 베이스 + 컵핸들 단순화 패턴 인식 후 일봉 백테스트.

평평한 베이스: 직전 N일 (예: 25일) 가격 범위 <= 15%, 50일 MA 위, 다음 봉 베이스 고점 돌파
컵핸들 단순화: 직전 60일 내 V/U 형성 + 핸들 (좁은 박스) -> 돌파

진입: 패턴 충족 다음 봉 시가
청산: -7% / +20% / 40일 max_hold (CANSLIM 기본)

"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = logging.getLogger("canslim_phase_b")


def _detect_flat_base(df: pd.DataFrame, target_idx: int, base_days: int = 25,
                      max_range_pct: float = 0.15) -> bool:
    """평평한 베이스 + 다음 봉 베이스 고점 돌파 검출.

    조건:
    - base_days 동안 고가~저가 범위 <= max_range_pct
    - 베이스 하단이 50일 MA 아래로 5% 이상 내려가지 않음
    - target_idx 봉 종가가 베이스 고점 돌파 (0.1% 마진)
    """
    if target_idx < base_days + 50:
        return False
    base = df.iloc[target_idx - base_days:target_idx]
    base_high = float(base['high'].max())
    base_low = float(base['low'].min())
    if base_high <= 0:
        return False
    range_pct = (base_high - base_low) / base_high
    if range_pct > max_range_pct:
        return False
    # 50일 MA 위 확인
    ma50 = float(df['close'].iloc[target_idx - 50:target_idx].mean())
    if base_low < ma50 * 0.95:  # 베이스가 50일 MA 아래로 너무 깊지 않게
        return False
    # target_idx 봉 종가가 베이스 고점 돌파
    if target_idx >= len(df):
        return False
    last_close = float(df['close'].iloc[target_idx])
    return last_close > base_high * 1.001  # 0.1% 마진


def _detect_cup_handle(df: pd.DataFrame, target_idx: int, cup_days: int = 60,
                       handle_days: int = 10, cup_depth_max: float = 0.33,
                       handle_depth_max: float = 0.15) -> bool:
    """컵핸들 단순화 — V/U 형성 + 좁은 핸들 + 돌파.

    조건:
    - cup: 앞쪽 cup_days - handle_days 구간에서 U/V 형성
    - cup 깊이 10%~33% (너무 얕거나 너무 깊으면 제외)
    - 컵 시작/끝 가격 차이 20% 이내 (U 형태)
    - handle: 뒤쪽 handle_days 구간에서 좁은 범위 + 컵 상단 85% 이상
    - target_idx 봉 종가가 핸들 고점 돌파
    """
    if target_idx < cup_days + 10:
        return False
    cup = df.iloc[target_idx - cup_days:target_idx - handle_days]
    handle = df.iloc[target_idx - handle_days:target_idx]
    if len(cup) < int(cup_days * 0.8) or len(handle) < int(handle_days * 0.5):
        return False
    cup_start = float(cup['close'].iloc[0])
    cup_end = float(cup['close'].iloc[-1])
    cup_low = float(cup['low'].min())
    cup_high = float(cup['high'].max())
    if cup_high <= 0 or cup_start <= 0:
        return False
    # 컵 깊이 검증
    cup_depth = (cup_high - cup_low) / cup_high
    if cup_depth > cup_depth_max or cup_depth < 0.10:
        return False
    # 컵 시작/끝이 유사한 수준 (U/V 양쪽 끝 비슷)
    if abs(cup_start - cup_end) / cup_start > 0.20:
        return False
    # 핸들 — 좁은 범위 + 컵 우상단
    handle_high = float(handle['high'].max())
    handle_low = float(handle['low'].min())
    if handle_high <= 0:
        return False
    handle_depth = (handle_high - handle_low) / handle_high
    if handle_depth > handle_depth_max:
        return False
    if handle_low < cup_high * 0.85:  # 핸들이 컵 상단 절반 아래로 떨어지지 않음
        return False
    # target_idx 봉 종가가 핸들 고점 돌파
    if target_idx >= len(df):
        return False
    last_close = float(df['close'].iloc[target_idx])
    return last_close > handle_high * 1.001


def _load_prices(stock_codes: list, start: str, end: str) -> dict:
    """종목별 daily_prices 로드 (adj_factor 적용). start/end는 YYYY-MM-DD."""
    from db.connection import DatabaseConnection

    # 패턴 인식에 충분한 이력 확보를 위해 start보다 120일 전부터 로드
    start_dt = pd.Timestamp(start) - pd.Timedelta(days=180)
    start_load = start_dt.strftime("%Y-%m-%d")

    prices = {}
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, high, low, close, adj_factor
                FROM daily_prices
                WHERE stock_code = %s
                  AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start_load, end))
            rows = cur.fetchall()
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'adj_factor'])
            df['date'] = pd.to_datetime(df['date'])
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['adj_factor'] = pd.to_numeric(df['adj_factor'], errors='coerce').fillna(1.0)
            # adj_factor 적용
            for col in ['open', 'high', 'low', 'close']:
                df[f'{col}_adj'] = df[col] * df['adj_factor']
            df = df.dropna(subset=['open_adj', 'close_adj', 'high_adj', 'low_adj'])
            if len(df) < 70:
                LOG.debug(f"{code}: 이력 부족 ({len(df)}행) — 스킵")
                continue
            prices[code] = df.reset_index(drop=True)
    return prices


def _simulate_trades(screener: pd.DataFrame, prices: dict,
                     stop_loss: float, take_profit: float,
                     max_hold_days: int,
                     base_days: int, max_range_pct: float,
                     cup_days: int, cup_depth_max: float) -> pd.DataFrame:
    """스크리너 신호 날짜 기준 패턴 검출 -> 다음 봉 시가 진입 -> 청산 시뮬레이션."""
    trades = []

    for code in sorted(screener['stock_code'].unique()):
        if code not in prices:
            LOG.debug(f"{code}: 가격 데이터 없음 — 스킵")
            continue

        df_price = prices[code]
        # adj_factor 적용된 컬럼으로 작업용 df 구성
        df_work = df_price[['date', 'open_adj', 'high_adj', 'low_adj', 'close_adj']].copy()
        df_work.columns = ['date', 'open', 'high', 'low', 'close']

        code_signals = screener[screener['stock_code'] == code].sort_values('date')
        screener_dates = set(code_signals['date'])

        in_position = False
        for i in range(len(df_work)):
            if in_position:
                continue
            row_date = df_work['date'].iloc[i]
            if row_date not in screener_dates:
                continue

            flat_base = _detect_flat_base(df_work, i,
                                          base_days=base_days,
                                          max_range_pct=max_range_pct)
            cup_handle = _detect_cup_handle(df_work, i,
                                            cup_days=cup_days,
                                            cup_depth_max=cup_depth_max)
            if not (flat_base or cup_handle):
                continue

            # 진입: 다음 봉 시가
            if i + 1 >= len(df_work):
                continue
            entry_open = float(df_work['open'].iloc[i + 1])
            entry_date = df_work['date'].iloc[i + 1]
            if pd.isna(entry_open) or entry_open <= 0:
                continue

            stop_price = entry_open * (1 - stop_loss)
            target_price = entry_open * (1 + take_profit)

            exit_reason = None
            exit_price = entry_open
            exit_date = entry_date
            hold_bars_actual = 0

            for hold in range(1, max_hold_days + 1):
                bar_idx = i + 1 + hold
                if bar_idx >= len(df_work):
                    # 데이터 끝 강제청산
                    exit_price = float(df_work['close'].iloc[-1])
                    exit_date = df_work['date'].iloc[-1]
                    exit_reason = "end_of_data"
                    hold_bars_actual = hold
                    break
                bar_close = float(df_work['close'].iloc[bar_idx])
                if pd.isna(bar_close):
                    continue
                if bar_close <= stop_price:
                    exit_reason = "stop_loss"
                    exit_price = bar_close
                    exit_date = df_work['date'].iloc[bar_idx]
                    hold_bars_actual = hold
                    break
                if bar_close >= target_price:
                    exit_reason = "take_profit"
                    exit_price = bar_close
                    exit_date = df_work['date'].iloc[bar_idx]
                    hold_bars_actual = hold
                    break
                if hold == max_hold_days:
                    exit_reason = "max_hold"
                    exit_price = bar_close
                    exit_date = df_work['date'].iloc[bar_idx]
                    hold_bars_actual = hold

            if exit_reason is None:
                continue

            pnl_pct = (exit_price - entry_open) / entry_open
            hold_days_cal = (exit_date - entry_date).days

            sig_row = code_signals[code_signals['date'] == row_date].iloc[0]
            trades.append({
                'stock_code': code,
                'signal_date': row_date,
                'entry_date': entry_date,
                'entry_price': entry_open,
                'exit_date': exit_date,
                'exit_price': exit_price,
                'pnl_pct': pnl_pct,
                'hold_days': hold_days_cal,
                'hold_bars': hold_bars_actual,
                'reason': exit_reason,
                'pattern': 'flat_base' if flat_base else 'cup_handle',
                'momentum_score': sig_row.get('momentum_score', np.nan),
                'ni_yoy': sig_row.get('ni_yoy', np.nan),
                'roe': sig_row.get('roe', np.nan),
            })
            in_position = True  # 종목당 첫 신호 1거래로 제한

    return pd.DataFrame(trades)


def print_summary(df: pd.DataFrame, args) -> None:
    print()
    print("=" * 55)
    print("  CANSLIM Phase B - 패턴 인식 백테스트 결과")
    print("=" * 55)
    print(f"스크리너: {args.screener}")
    print(f"기간: {args.start} ~ {args.end}")
    print(f"손절: -{args.stop_loss*100:.0f}% / 익절: +{args.take_profit*100:.0f}% / 최대보유: {args.max_hold_days}일")
    print(f"평평한베이스 파라미터: base_days={args.base_days}, max_range_pct={args.max_range_pct:.0%}")
    print(f"컵핸들 파라미터: cup_days={args.cup_days}, cup_depth_max={args.cup_depth_max:.0%}")
    print()

    if len(df) == 0:
        print("거래 없음 — 패턴 조건 미충족")
        return

    n = len(df)
    wins = (df['pnl_pct'] > 0).sum()
    win_rate = wins / n
    avg_pnl = df['pnl_pct'].mean()
    median_pnl = df['pnl_pct'].median()
    total_pnl = df['pnl_pct'].sum()
    avg_hold = df['hold_days'].mean()

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
    print("패턴별 거래:")
    print(df['pattern'].value_counts().to_string())
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
    display_cols = ['stock_code', 'pattern', 'entry_date', 'exit_date',
                    'hold_days', 'pnl_pct', 'reason']
    print(df[display_cols].sort_values('entry_date').to_string(index=False))


def main():
    p = argparse.ArgumentParser(description="CANSLIM Phase B 패턴 백테스트")
    p.add_argument("--screener",
                   default="reports/books_research/oneil_canslim/screener_daily.parquet")
    p.add_argument("--start", default="2025-01-01")
    p.add_argument("--end", default="2026-05-28")
    p.add_argument("--stop-loss", type=float, default=0.07)
    p.add_argument("--take-profit", type=float, default=0.20)
    p.add_argument("--max-hold-days", type=int, default=40)
    # 평평한 베이스 파라미터
    p.add_argument("--base-days", type=int, default=25)
    p.add_argument("--max-range-pct", type=float, default=0.15)
    # 컵핸들 파라미터
    p.add_argument("--cup-days", type=int, default=60)
    p.add_argument("--cup-depth-max", type=float, default=0.33)
    p.add_argument("--out",
                   default="reports/books_research/oneil_canslim/canslim_phase_b_trades.parquet")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    screener = pd.read_parquet(args.screener)
    screener['date'] = pd.to_datetime(screener['date'])
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

    if len(prices) == 0:
        print("가격 데이터 없음")
        return

    LOG.info("패턴 검출 + 백테스트 시뮬레이션 실행 중")
    df_trades = _simulate_trades(
        screener, prices,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit,
        max_hold_days=args.max_hold_days,
        base_days=args.base_days,
        max_range_pct=args.max_range_pct,
        cup_days=args.cup_days,
        cup_depth_max=args.cup_depth_max,
    )

    print_summary(df_trades, args)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_trades.to_parquet(out_path, index=False)
    LOG.info(f"저장 완료: {out_path}")

    if len(df_trades) <= 3:
        LOG.warning(
            f"거래수 {len(df_trades)} <= 3. "
            "완화된 스크리너(screener_daily_relaxed.parquet)나 "
            "--max-range-pct 0.20 --cup-depth-max 0.40 으로 재실행 권장"
        )


if __name__ == "__main__":
    main()
