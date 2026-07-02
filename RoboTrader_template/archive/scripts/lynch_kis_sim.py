#!/usr/bin/env python3
"""
Lynch KIS Simulation — 피터 린치 PEG 전략 백테스트
==================================================

strategy.py의 evaluate_buy/sell_conditions()를 직접 호출.
최적화: 재무 필터 먼저 적용 → 통과 종목만 candles 로드.
"""

import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple
from dataclasses import dataclass
from collections import defaultdict

sys.path.insert(0, '/mnt/d/GIT/kis-trading-template/RoboTrader_template')
from strategies.lynch.strategy import LynchStrategy

# ============================================================================
# Config
# ============================================================================
DB_CONFIG = dict(
    host="172.23.208.1", port=5433, dbname="strategy_analysis",
    user="postgres", password="postgres",
)

INITIAL_CAPITAL = 15_000_000
MAX_POSITIONS = 5
PER_STOCK_AMOUNT = 3_000_000
SLIPPAGE = 0.003
COMMISSION = 0.00015

PEG_MAX = 0.3
OP_GROWTH_MIN = 70.0
DEBT_RATIO_MAX = 200.0
ROE_MIN = 5.0
RSI_PERIOD = 14
RSI_OVERSOLD = 35.0
TAKE_PROFIT_PCT = 0.50
STOP_LOSS_PCT = 0.15
MAX_HOLD_DAYS = 120


@dataclass
class Trade:
    stock_code: str
    entry_price: float
    entry_date: object
    exit_price: float
    exit_date: object
    quantity: int
    pnl: float
    pnl_pct: float
    hold_days: int
    exit_reason: str


def calculate_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi[avg_loss.abs() < 1e-10] = 100.0
    return rsi


def run_simulation():
    import psycopg2

    conn = psycopg2.connect(**DB_CONFIG)

    # Step 1: 재무 데이터 로드 (작음)
    print("재무 데이터 로딩...")
    financials = pd.read_sql("""
        SELECT stock_code, year, account_name, amount
        FROM financial_data WHERE account_name = '영업이익'
        ORDER BY stock_code, year
    """, conn)

    fundamentals_df = pd.read_sql("""
        SELECT stock_code, year, per, pbr, roe, debt_ratio
        FROM yearly_fundamentals ORDER BY stock_code, year
    """, conn)

    # Build fundamental map
    fund_map: Dict[Tuple[str, int], Dict] = {}
    for _, row in fundamentals_df.iterrows():
        key = (row['stock_code'], int(row['year']))
        fund_map[key] = {
            'per': float(row['per']) if pd.notna(row['per']) else 0.0,
            'roe': float(row['roe']) if pd.notna(row['roe']) else 0.0,
            'debt_ratio': float(row['debt_ratio']) if pd.notna(row['debt_ratio']) else 999.0,
        }

    op_income = {}
    for _, row in financials.iterrows():
        op_income[(row['stock_code'], int(row['year']))] = float(row['amount']) if pd.notna(row['amount']) else 0.0

    for (code, year), amt in op_income.items():
        prev_amt = op_income.get((code, year - 1))
        if prev_amt and prev_amt > 0 and amt > 0:
            growth = (amt - prev_amt) / prev_amt * 100
        else:
            growth = 0.0
        key = (code, year)
        if key not in fund_map:
            fund_map[key] = {'per': 0.0, 'roe': 0.0, 'debt_ratio': 999.0}
        fund_map[key]['op_income_growth'] = growth

    # Step 2: 재무 조건 통과 종목 필터
    valid_fund_keys = set()
    for (code, year), f in fund_map.items():
        if 'op_income_growth' not in f:
            continue
        per = f['per']
        op_g = f['op_income_growth']
        if per <= 0 or op_g <= 0:
            continue
        if per / op_g > PEG_MAX:
            continue
        if op_g < OP_GROWTH_MIN:
            continue
        if f['debt_ratio'] > DEBT_RATIO_MAX:
            continue
        if f['roe'] < ROE_MIN:
            continue
        valid_fund_keys.add((code, year))

    valid_codes = list(set(code for code, year in valid_fund_keys))
    print(f"재무 조건 통과: {len(valid_fund_keys)}개 (code,year) 쌍, {len(valid_codes)}개 종목")

    if not valid_codes:
        print("재무 조건 통과 종목 없음. 종료.")
        conn.close()
        return

    # Step 3: 통과 종목 + 전체 거래일용 candles 로드
    # 전체 거래일 목록 먼저 구하기
    print("거래일 로딩...")
    all_dates_df = pd.read_sql("SELECT DISTINCT trade_date FROM daily_candles ORDER BY trade_date", conn)
    all_dates = all_dates_df['trade_date'].values.astype('datetime64[D]')

    # 통과 종목 candles만 로드
    placeholders = ','.join(['%s'] * len(valid_codes))
    print(f"통과 종목 {len(valid_codes)}개의 캔들 로딩...")
    candles = pd.read_sql(f"""
        SELECT stock_code, trade_date, open_price, high_price, low_price, close_price, volume
        FROM daily_candles
        WHERE stock_code IN ({placeholders})
        ORDER BY stock_code, trade_date
    """, conn, params=valid_codes)

    conn.close()
    print(f"candles 로드: {len(candles):,}행")

    candles['trade_date'] = pd.to_datetime(candles['trade_date']).values.astype('datetime64[D]')

    # Step 4: RSI 계산 + 매수 시그널 수집
    print("매수 시그널 사전 계산 중...")
    buy_signals = []

    for code in valid_codes:
        df = candles[candles['stock_code'] == code].copy()
        if len(df) < RSI_PERIOD + 2:
            continue
        df = df.set_index('trade_date').sort_index()
        df = df[~df.index.duplicated(keep='first')]

        rsi = calculate_rsi_series(df['close_price'], RSI_PERIOD)

        for date_val, rsi_val in rsi.items():
            if pd.isna(rsi_val) or rsi_val >= RSI_OVERSOLD:
                continue

            year = int(str(date_val)[:4])
            fund_key = (code, year - 1)
            if fund_key not in valid_fund_keys:
                continue

            fund = fund_map[fund_key]
            price = float(df.loc[date_val, 'close_price'])
            if price <= 0:
                continue

            buy_signals.append((date_val, code, price, fund))

    print(f"매수 시그널: {len(buy_signals)}개")

    signal_by_date = defaultdict(list)
    for date_val, code, price, fund in buy_signals:
        # Normalize to numpy datetime64[D] to match all_dates
        d = np.datetime64(pd.Timestamp(date_val), 'D')
        signal_by_date[d].append((code, price, fund))

    # Stock price lookup
    stock_data = {}
    for code in valid_codes:
        df = candles[candles['stock_code'] == code].copy()
        df['trade_date'] = df['trade_date'].values.astype('datetime64[D]')
        df = df.set_index('trade_date').sort_index()
        df = df[~df.index.duplicated(keep='first')]
        stock_data[code] = df

    # Step 5: 시뮬레이션
    print("시뮬레이션 실행 중...")

    cash = float(INITIAL_CAPITAL)
    positions: Dict[str, dict] = {}
    trades: List[Trade] = []
    equity_curve = []

    for current_date in all_dates:
        portfolio_value = cash
        for code, pos in positions.items():
            if code in stock_data and current_date in stock_data[code].index:
                price = float(stock_data[code].loc[current_date, 'close_price'])
            else:
                price = pos['entry_price']
            portfolio_value += price * pos['quantity']
        equity_curve.append((current_date, portfolio_value))

        # Sell check
        codes_to_sell = []
        for code, pos in positions.items():
            if code not in stock_data or current_date not in stock_data[code].index:
                continue
            current_price = float(stock_data[code].loc[current_date, 'close_price'])
            hold_days = int((current_date - pos['entry_date']) / np.timedelta64(1, 'D'))

            should_sell, reasons = LynchStrategy.evaluate_sell_conditions(
                current_price=current_price,
                entry_price=pos['entry_price'],
                hold_days=hold_days,
                take_profit_pct=TAKE_PROFIT_PCT,
                stop_loss_pct=STOP_LOSS_PCT,
                max_hold_days=MAX_HOLD_DAYS,
            )

            if should_sell:
                sell_price = current_price * (1 - SLIPPAGE)
                proceeds = sell_price * pos['quantity'] * (1 - COMMISSION)
                pnl = proceeds - pos['cost']
                pnl_pct = (sell_price - pos['entry_price']) / pos['entry_price'] * 100
                trades.append(Trade(
                    stock_code=code, entry_price=pos['entry_price'],
                    entry_date=pos['entry_date'], exit_price=sell_price,
                    exit_date=current_date, quantity=pos['quantity'],
                    pnl=pnl, pnl_pct=pnl_pct, hold_days=hold_days,
                    exit_reason=reasons[0] if reasons else "UNKNOWN",
                ))
                cash += proceeds
                codes_to_sell.append(code)

        for code in codes_to_sell:
            del positions[code]

        # Buy check
        if len(positions) < MAX_POSITIONS and current_date in signal_by_date:
            for code, sig_price, fund in signal_by_date[current_date]:
                if len(positions) >= MAX_POSITIONS:
                    break
                if code in positions:
                    continue
                if cash < PER_STOCK_AMOUNT * 0.3:
                    break

                should_buy, reasons = LynchStrategy.evaluate_buy_conditions(
                    current_price=sig_price,
                    rsi_value=RSI_OVERSOLD - 1,
                    fundamentals=fund,
                    peg_max=PEG_MAX,
                    op_growth_min=OP_GROWTH_MIN,
                    debt_ratio_max=DEBT_RATIO_MAX,
                    roe_min=ROE_MIN,
                    rsi_oversold=RSI_OVERSOLD,
                )

                if not should_buy:
                    continue

                buy_price = sig_price * (1 + SLIPPAGE)
                invest_amount = min(PER_STOCK_AMOUNT, cash * 0.95)
                quantity = int(invest_amount / buy_price)
                if quantity <= 0:
                    continue
                cost = buy_price * quantity * (1 + COMMISSION)
                if cost > cash:
                    quantity = int(cash / (buy_price * (1 + COMMISSION)))
                    if quantity <= 0:
                        continue
                    cost = buy_price * quantity * (1 + COMMISSION)

                cash -= cost
                positions[code] = {
                    'entry_price': buy_price,
                    'entry_date': current_date,
                    'quantity': quantity,
                    'cost': cost,
                }

    # Force close
    last_date = all_dates[-1]
    for code, pos in list(positions.items()):
        if code in stock_data and last_date in stock_data[code].index:
            price = float(stock_data[code].loc[last_date, 'close_price'])
        else:
            price = pos['entry_price']
        sell_price = price * (1 - SLIPPAGE)
        proceeds = sell_price * pos['quantity'] * (1 - COMMISSION)
        pnl = proceeds - pos['cost']
        pnl_pct = (sell_price - pos['entry_price']) / pos['entry_price'] * 100
        hold_days = int((last_date - pos['entry_date']) / np.timedelta64(1, 'D'))
        trades.append(Trade(
            stock_code=code, entry_price=pos['entry_price'],
            entry_date=pos['entry_date'], exit_price=sell_price,
            exit_date=last_date, quantity=pos['quantity'],
            pnl=pnl, pnl_pct=pnl_pct, hold_days=hold_days,
            exit_reason="FORCE_CLOSE",
        ))
        cash += proceeds
    positions.clear()

    # ====================================================================
    # 성과 분석
    # ====================================================================
    equity = pd.DataFrame(equity_curve, columns=['date', 'equity'])
    equity['date'] = pd.to_datetime(equity['date'])
    equity = equity.set_index('date')

    final_equity = float(equity['equity'].iloc[-1])
    start_date = equity.index[0]
    end_date = equity.index[-1]
    years = (end_date - start_date) / np.timedelta64(365, 'D')

    cagr = (final_equity / INITIAL_CAPITAL) ** (1 / years) - 1 if years > 0 else 0
    peak = equity['equity'].cummax()
    drawdown = (equity['equity'] - peak) / peak
    mdd = float(drawdown.min()) * 100

    daily_returns = equity['equity'].pct_change().dropna()
    sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 and daily_returns.std() > 0 else 0.0

    total_trades = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0

    equity_monthly = equity.resample('M').last()
    monthly_returns = equity_monthly['equity'].pct_change().dropna()
    avg_monthly_return = monthly_returns.mean() * 100 if len(monthly_returns) > 0 else 0

    yearly_perf = []
    equity['year'] = pd.to_datetime(equity.index.astype(str)).year
    for yr, grp in equity.groupby('year'):
        yr_start = float(grp['equity'].iloc[0])
        yr_end = float(grp['equity'].iloc[-1])
        yr_ret = (yr_end / yr_start - 1) * 100
        yr_trades = [t for t in trades if str(t.entry_date)[:4] == str(yr)]
        yr_wins = [t for t in yr_trades if t.pnl > 0]
        yearly_perf.append({
            'year': yr, 'return_pct': yr_ret, 'trades': len(yr_trades),
            'win_rate': len(yr_wins) / len(yr_trades) * 100 if yr_trades else 0,
            'start_equity': yr_start, 'end_equity': yr_end,
        })

    sorted_trades = sorted(trades, key=lambda t: t.pnl, reverse=True)
    top5_profit = sorted_trades[:5]
    top5_loss = sorted_trades[-5:]

    # ====================================================================
    # 출력
    # ====================================================================
    print("\n" + "=" * 70)
    print("📊 Lynch PEG 전략 시뮬레이션 결과")
    print("=" * 70)
    print(f"기간: {start_date} ~ {end_date} ({years:.1f}년)")
    print(f"초기자산: {INITIAL_CAPITAL:>15,.0f}원")
    print(f"최종자산: {final_equity:>15,.0f}원")
    print(f"CAGR:     {cagr * 100:>14.2f}%")
    print(f"MDD:      {mdd:>14.2f}%")
    print(f"Sharpe:   {sharpe:>14.3f}")
    print(f"총 거래:  {total_trades:>14}건")
    print(f"승률:     {win_rate:>14.1f}%")
    print(f"월평균 수익률: {avg_monthly_return:>9.2f}%")

    print(f"\n📅 연도별 성과:")
    print(f"{'연도':>6} {'수익률':>10} {'거래수':>8} {'승률':>8} {'시작자산':>15} {'종료자산':>15}")
    for yp in yearly_perf:
        print(f"{yp['year']:>6} {yp['return_pct']:>9.2f}% {yp['trades']:>8} {yp['win_rate']:>7.1f}% "
              f"{yp['start_equity']:>15,.0f} {yp['end_equity']:>15,.0f}")

    print(f"\n🏆 Top 5 수익 거래:")
    for t in top5_profit:
        print(f"  {t.stock_code} | {t.entry_date} → {t.exit_date} | {t.pnl_pct:+.1f}% | {t.exit_reason}")

    print(f"\n💀 Top 5 손실 거래:")
    for t in top5_loss:
        print(f"  {t.stock_code} | {t.entry_date} → {t.exit_date} | {t.pnl_pct:+.1f}% | {t.exit_reason}")

    # Save report
    report = f"""# Lynch PEG 전략 시뮬레이션 결과

## 파라미터
- PEG ≤ {PEG_MAX}, 영업이익 YoY ≥ {OP_GROWTH_MIN}%, 부채비율 ≤ {DEBT_RATIO_MAX}%, ROE ≥ {ROE_MIN}%, RSI < {RSI_OVERSOLD}
- TP: +{TAKE_PROFIT_PCT*100:.0f}%, SL: -{STOP_LOSS_PCT*100:.0f}%, Timeout: {MAX_HOLD_DAYS}거래일
- 초기자산: {INITIAL_CAPITAL:,.0f}원, {MAX_POSITIONS}종목, 종목당 {PER_STOCK_AMOUNT:,.0f}원
- 슬리피지: {SLIPPAGE*100:.1f}%, 수수료: {COMMISSION*100:.3f}%

## 전체 성과
| 지표 | 값 |
|------|-----|
| 기간 | {start_date} ~ {end_date} ({years:.1f}년) |
| 최종자산 | {final_equity:,.0f}원 |
| CAGR | {cagr*100:.2f}% |
| MDD | {mdd:.2f}% |
| Sharpe | {sharpe:.3f} |
| 총 거래 | {total_trades}건 |
| 승률 | {win_rate:.1f}% |
| 월평균 수익률 | {avg_monthly_return:.2f}% |

## 연도별 성과
| 연도 | 수익률 | 거래수 | 승률 | 시작자산 | 종료자산 |
|------|--------|--------|------|----------|----------|
"""
    for yp in yearly_perf:
        report += f"| {yp['year']} | {yp['return_pct']:.2f}% | {yp['trades']} | {yp['win_rate']:.1f}% | {yp['start_equity']:,.0f} | {yp['end_equity']:,.0f} |\n"

    report += "\n## Top 5 수익 거래\n"
    for t in top5_profit:
        report += f"- {t.stock_code}: {t.entry_date} → {t.exit_date} | {t.pnl_pct:+.1f}% | {t.exit_reason}\n"

    report += "\n## Top 5 손실 거래\n"
    for t in top5_loss:
        report += f"- {t.stock_code}: {t.entry_date} → {t.exit_date} | {t.pnl_pct:+.1f}% | {t.exit_reason}\n"

    report += f"\n---\n생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

    output_path = '/home/qwer/.openclaw/workspace/memory/analysis-lynch-kis-sim.md'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n📄 결과 저장: {output_path}")


if __name__ == "__main__":
    run_simulation()
