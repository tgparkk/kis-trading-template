#!/usr/bin/env python3
"""
Lynch PEG 전략 멀티버스 — kis-template evaluate 함수 직접 사용
=============================================================
strategy.py의 evaluate_buy/sell_conditions를 그대로 호출하여
시뮬과 실전의 로직 일치를 보장합니다.
"""

import sys
import os
import time
import numpy as np
import pandas as pd
import psycopg2
from collections import defaultdict
from itertools import product
from dataclasses import dataclass
from typing import List, Dict, Tuple, Any

# kis-template의 strategies를 import하기 위한 경로 설정
TEMPLATE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TEMPLATE_ROOT)

from strategies.lynch.strategy import LynchStrategy

DB = dict(host='172.23.208.1', port=5433, dbname='strategy_analysis', user='postgres', password='postgres')
START, END = '2022-01-01', '2026-02-10'
INITIAL_CAPITAL = 15_000_000
MAX_POSITIONS = 5
PER_STOCK = INITIAL_CAPITAL / MAX_POSITIONS
SLIPPAGE = 0.003
COMMISSION = 0.00015


def calculate_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def load_all_data():
    """DB에서 모든 데이터 한 번에 로드"""
    conn = psycopg2.connect(**DB)

    # 영업이익 YoY
    financials = pd.read_sql("""
        SELECT stock_code, year, amount as op_income
        FROM financial_data WHERE account_name = '영업이익'
    """, conn)

    # yearly_fundamentals
    fundamentals = pd.read_sql("""
        SELECT stock_code, year, per, pbr, roe, debt_ratio
        FROM yearly_fundamentals
    """, conn)

    # 전체 거래일
    all_dates_df = pd.read_sql(
        f"SELECT DISTINCT trade_date FROM daily_candles WHERE trade_date >= '{START}' AND trade_date <= '{END}' ORDER BY trade_date",
        conn
    )
    all_dates = all_dates_df['trade_date'].values.astype('datetime64[D]')

    # 영업이익 YoY 계산
    fin_pivot = financials.pivot_table(index='stock_code', columns='year', values='op_income')
    op_growth_map = {}  # (code, year) -> growth%
    for code in fin_pivot.index:
        for yr in fin_pivot.columns:
            prev_yr = yr - 1
            if prev_yr in fin_pivot.columns:
                curr = fin_pivot.loc[code, yr]
                prev = fin_pivot.loc[code, prev_yr]
                if pd.notna(curr) and pd.notna(prev) and prev > 0:
                    op_growth_map[(code, yr)] = ((curr - prev) / prev) * 100

    # fundamentals를 딕셔너리로
    fund_map = {}  # (code, year) -> {per, debt_ratio, roe}
    for _, row in fundamentals.iterrows():
        key = (row['stock_code'], int(row['year']))
        fund_map[key] = {
            'per': float(row['per']) if pd.notna(row['per']) else 0.0,
            'debt_ratio': float(row['debt_ratio']) if pd.notna(row['debt_ratio']) else 999.0,
            'roe': float(row['roe']) if pd.notna(row['roe']) else 0.0,
        }

    # 통합 재무 딕셔너리: (code, trading_year) -> fundamentals + op_growth
    # trading_year의 재무 = year-1의 데이터
    combined_fund = {}
    all_codes = set()
    for trading_yr in range(2022, 2027):
        fiscal_yr = trading_yr - 1
        for code in set(c for (c, y) in fund_map.keys() if y == fiscal_yr):
            fund = fund_map.get((code, fiscal_yr), {})
            growth = op_growth_map.get((code, fiscal_yr))
            if growth is not None and fund.get('per', 0) > 0:
                combined_fund[(code, trading_yr)] = {
                    'per': fund['per'],
                    'op_income_growth': growth,
                    'debt_ratio': fund['debt_ratio'],
                    'roe': fund['roe'],
                }
                all_codes.add(code)

    # 해당 종목들의 candles만 로드
    valid_codes = list(all_codes)
    if not valid_codes:
        conn.close()
        return None, None, None, None

    placeholders = ','.join(['%s'] * len(valid_codes))
    candles = pd.read_sql(f"""
        SELECT stock_code, trade_date, open_price, high_price, low_price, close_price, volume
        FROM daily_candles WHERE stock_code IN ({placeholders})
        ORDER BY stock_code, trade_date
    """, conn, params=valid_codes)
    conn.close()

    candles['trade_date'] = pd.to_datetime(candles['trade_date']).values.astype('datetime64[D]')

    # 종목별 DataFrame + RSI 미리 계산 (여러 period)
    stock_data = {}
    rsi_cache = {}  # (code, period) -> {date: rsi_val}

    for code in valid_codes:
        df = candles[candles['stock_code'] == code].copy()
        df = df.set_index('trade_date').sort_index()
        df = df[~df.index.duplicated(keep='first')]
        stock_data[code] = df

        for period in [14, 21, 28]:
            if len(df) > period + 2:
                rsi = calculate_rsi_series(df['close_price'], period)
                rsi_dict = {}
                for d, v in rsi.items():
                    rsi_dict[np.datetime64(pd.Timestamp(d), 'D')] = float(v) if pd.notna(v) else 100.0
                rsi_cache[(code, period)] = rsi_dict

    print(f"데이터 로드 완료: {len(valid_codes)}종목, {len(all_dates)}거래일, {len(combined_fund)}개 재무조합")
    return all_dates, combined_fund, stock_data, rsi_cache


def precompute_signals(all_dates, combined_fund, stock_data, rsi_cache):
    """
    모든 후보를 DataFrame으로 사전 계산하여 벡터 필터링 가능하게 함.
    evaluate_buy_conditions의 로직을 검증 후 동일하게 벡터화.
    """
    print("시그널 후보 사전 계산 중...", flush=True)
    rows = []

    for di, current_date in enumerate(all_dates):
        trading_year = int(str(current_date)[:4])
        for code, sd in stock_data.items():
            if current_date not in sd.index:
                continue
            fund = combined_fund.get((code, trading_year))
            if fund is None:
                continue
            price = float(sd.loc[current_date, 'close_price'])
            if price <= 0:
                continue
            rd = rsi_cache.get((code, 14))
            rsi_val = rd.get(current_date, 100.0) if rd else 100.0

            per = fund.get('per', 0.0)
            op_growth = fund.get('op_income_growth', 0.0)
            debt_ratio = fund.get('debt_ratio', 999.0)
            roe = fund.get('roe', 0.0)

            # 적자 제외 (per <= 0 or op_growth <= 0)
            if per <= 0 or op_growth <= 0:
                continue

            peg = per / op_growth

            rows.append((di, code, price, peg, op_growth, debt_ratio, roe, rsi_val))

    cdf = pd.DataFrame(rows, columns=['di', 'code', 'price', 'peg', 'op_growth', 'debt_ratio', 'roe', 'rsi'])
    print(f"후보: {len(cdf)}개 (적자 제외 후)", flush=True)
    return cdf


def build_signal_index(cdf, peg_max, op_growth_min, debt_ratio_max, roe_min, rsi_oversold):
    """벡터 필터링 — evaluate_buy_conditions과 동일 로직"""
    mask = (
        (cdf['peg'] <= peg_max) &
        (cdf['op_growth'] >= op_growth_min) &
        (cdf['debt_ratio'] <= debt_ratio_max) &
        (cdf['roe'] >= roe_min) &
        (cdf['rsi'] < rsi_oversold)
    )
    filtered = cdf[mask]
    sig_by_di = defaultdict(list)
    for di, code, price in zip(filtered['di'].values, filtered['code'].values, filtered['price'].values):
        sig_by_di[int(di)].append((code, float(price)))
    return sig_by_di


def build_price_lookup(stock_data):
    """price_lookup을 한번만 구축 — 키를 datetime64[D]로 통일"""
    price_lookup = {}
    for code, sd in stock_data.items():
        pl = {}
        for d, row in sd.iterrows():
            pl[np.datetime64(pd.Timestamp(d), 'D')] = float(row['close_price'])
        price_lookup[code] = pl
    return price_lookup


def simulate_fast(sig_by_di, all_dates, price_lookup, tp_pct, sl_pct, max_hold_days):
    """빠른 포트폴리오 시뮬레이션 — 시그널 인덱스 기반"""
    cash = float(INITIAL_CAPITAL)
    positions = {}
    trades = []
    equity_arr = np.full(len(all_dates), float(INITIAL_CAPITAL))

    for di, current_date in enumerate(all_dates):
        # Equity
        eq = cash
        for code, pos in positions.items():
            p = price_lookup.get(code, {}).get(current_date, pos['entry_price'])
            eq += p * pos['quantity']
        equity_arr[di] = eq

        # 매도 체크
        codes_to_sell = []
        for code, pos in positions.items():
            p = price_lookup.get(code, {}).get(current_date)
            if p is None:
                continue
            hold_days = int((current_date - pos['entry_date']) / np.timedelta64(1, 'D'))

            should_sell, _ = LynchStrategy.evaluate_sell_conditions(
                current_price=p, entry_price=pos['entry_price'],
                hold_days=hold_days,
                take_profit_pct=tp_pct, stop_loss_pct=sl_pct,
                max_hold_days=max_hold_days,
            )
            if should_sell:
                sell_price = p * (1 - SLIPPAGE) * (1 - COMMISSION)
                pnl = sell_price * pos['quantity'] - pos['cost']
                trades.append(pnl)
                cash += sell_price * pos['quantity']
                codes_to_sell.append(code)

        for code in codes_to_sell:
            del positions[code]

        # 매수 체크
        if len(positions) < MAX_POSITIONS and di in sig_by_di:
            held = set(positions.keys())
            for code, price in sig_by_di[di]:
                if len(positions) >= MAX_POSITIONS:
                    break
                if code in held:
                    continue
                buy_price = price * (1 + SLIPPAGE) * (1 + COMMISSION)
                invest = min(PER_STOCK, cash * 0.95)
                qty = int(invest / buy_price)
                if qty <= 0:
                    continue
                cost = buy_price * qty
                if cost > cash:
                    continue
                cash -= cost
                positions[code] = {
                    'entry_price': price * (1 + SLIPPAGE),
                    'entry_date': current_date,
                    'quantity': qty,
                    'cost': cost,
                }
                held.add(code)

    # 미청산 강제 매도
    last_date = all_dates[-1]
    for code, pos in positions.items():
        p = price_lookup.get(code, {}).get(last_date, pos['entry_price'])
        sell_price = p * (1 - SLIPPAGE) * (1 - COMMISSION)
        pnl = sell_price * pos['quantity'] - pos['cost']
        trades.append(pnl)

    return calc_metrics(trades, equity_arr, all_dates)


def calc_metrics(trades, equity, dates):
    n = len(trades)
    if n == 0:
        return None

    first_nonzero = np.argmax(equity > 0)
    eq = equity[first_nonzero:]
    if len(eq) < 2 or eq[0] <= 0:
        return None

    years = (dates[-1] - dates[first_nonzero]).astype('timedelta64[D]').astype(int) / 365.25
    if years <= 0:
        return None

    cagr = ((eq[-1] / eq[0]) ** (1/years) - 1) * 100
    peak = np.maximum.accumulate(eq)
    mdd = ((eq - peak) / peak).min() * 100
    daily_ret = np.diff(eq) / eq[:-1]
    std = daily_ret.std()
    sharpe = (daily_ret.mean() / std * np.sqrt(252)) if std > 0 else 0
    wins = sum(1 for t in trades if t > 0)
    wr = wins / n * 100
    final = eq[-1]

    return {
        'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe,
        'n_trades': n, 'win_rate': wr, 'final_equity': final,
    }


def main():
    t0 = time.time()
    print("데이터 로딩...", flush=True)
    all_dates, combined_fund, stock_data, rsi_cache = load_all_data()
    if all_dates is None:
        print("데이터 없음!")
        return

    # ============================================================
    # STEP 1: 진입조건 멀티버스 (Exit 고정: TP50/SL15/120일)
    # ============================================================
    print("\n" + "="*60)
    print("STEP 1: 진입조건 멀티버스")
    print("="*60, flush=True)

    peg_list = [0.3, 0.5, 0.7, 1.0, 1.5]
    op_growth_list = [20, 30, 50, 70]
    rsi_period_list = [14]
    rsi_upper_list = [25, 30, 35, 40, 50, 60]
    debt_list = [100, 150, 200, 9999]
    roe_list = [0, 5, 10, 15]

    total = len(peg_list) * len(op_growth_list) * len(rsi_upper_list) * len(debt_list) * len(roe_list)
    print(f"총 {total} 조합", flush=True)

    # 시그널 후보 사전 계산
    candidates = precompute_signals(all_dates, combined_fund, stock_data, rsi_cache)
    price_lookup = build_price_lookup(stock_data)

    results_1 = []
    count = 0
    for peg, opg, rsi_u, debt, roe in product(peg_list, op_growth_list, rsi_upper_list, debt_list, roe_list):
        count += 1
        if count % 100 == 0:
            print(f"  {count}/{total}...", flush=True)

        sig_idx = build_signal_index(candidates, peg, opg, debt, roe, rsi_u)
        m = simulate_fast(sig_idx, all_dates, price_lookup, 0.50, 0.15, 120)
        if m and m['n_trades'] >= 20:
            results_1.append({
                'peg': peg, 'op_growth': opg, 'rsi_upper': rsi_u,
                'debt': debt, 'roe': roe, **m
            })

    results_1.sort(key=lambda x: x['sharpe'], reverse=True)
    print(f"\n유효 조합: {len(results_1)}", flush=True)

    print(f"\nTop 20 진입조건 (Sharpe):")
    print(f"{'#':>3} {'PEG':>5} {'OPG':>5} {'RSI':>5} {'Debt':>6} {'ROE':>5} {'CAGR':>7} {'MDD':>7} {'Sharpe':>7} {'N':>5} {'WR':>6} {'Final':>12}")
    for i, r in enumerate(results_1[:20]):
        d = f"{r['debt']}" if r['debt'] < 9000 else "None"
        print(f"{i+1:>3} {r['peg']:>5.1f} {r['op_growth']:>5.0f} {r['rsi_upper']:>5.0f} {d:>6} {r['roe']:>5.0f} {r['cagr']:>6.1f}% {r['mdd']:>6.1f}% {r['sharpe']:>7.2f} {r['n_trades']:>5} {r['win_rate']:>5.1f}% {r['final_equity']:>11,.0f}")

    # ============================================================
    # STEP 2: Top 20 × Exit 멀티버스
    # ============================================================
    print("\n" + "="*60)
    print("STEP 2: Exit 멀티버스")
    print("="*60, flush=True)

    tp_list = [0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
    sl_list = [0.05, 0.07, 0.10, 0.15, 0.20]
    hold_list = [30, 40, 60, 90, 120]

    top20 = results_1[:20]
    total_2 = len(top20) * len(tp_list) * len(sl_list) * len(hold_list)
    print(f"총 {total_2} 조합", flush=True)

    results_2 = []
    count = 0
    # Top 20의 시그널 인덱스 캐시
    entry_sig_cache = {}
    for entry in top20:
        key = (entry['peg'], entry['op_growth'], entry['rsi_upper'], entry['debt'], entry['roe'])
        entry_sig_cache[key] = build_signal_index(candidates, entry['peg'], entry['op_growth'], entry['debt'], entry['roe'], entry['rsi_upper'])

    for entry in top20:
        key = (entry['peg'], entry['op_growth'], entry['rsi_upper'], entry['debt'], entry['roe'])
        sig_idx = entry_sig_cache[key]
        for tp, sl, hd in product(tp_list, sl_list, hold_list):
            count += 1
            if count % 500 == 0:
                print(f"  {count}/{total_2}...", flush=True)

            m = simulate_fast(sig_idx, all_dates, price_lookup, tp, sl, hd)
            if m and m['n_trades'] >= 20:
                results_2.append({
                    'peg': entry['peg'], 'op_growth': entry['op_growth'],
                    'rsi_upper': entry['rsi_upper'], 'debt': entry['debt'],
                    'roe': entry['roe'],
                    'tp': tp, 'sl': sl, 'hold': hd, **m
                })

    results_2.sort(key=lambda x: x['sharpe'], reverse=True)
    print(f"\n유효 조합: {len(results_2)}", flush=True)

    print(f"\nTop 20 전체 파라미터 (Sharpe):")
    print(f"{'#':>3} {'PEG':>5} {'OPG':>4} {'RSI':>4} {'Debt':>5} {'ROE':>4} {'TP':>5} {'SL':>5} {'Hold':>5} {'CAGR':>7} {'MDD':>7} {'Sharpe':>7} {'N':>5} {'WR':>6} {'Final':>12}")
    for i, r in enumerate(results_2[:20]):
        d = f"{r['debt']}" if r['debt'] < 9000 else "N"
        print(f"{i+1:>3} {r['peg']:>5.1f} {r['op_growth']:>4.0f} {r['rsi_upper']:>4.0f} {d:>5} {r['roe']:>4.0f} {r['tp']*100:>4.0f}% {r['sl']*100:>4.0f}% {r['hold']:>5} {r['cagr']:>6.1f}% {r['mdd']:>6.1f}% {r['sharpe']:>7.2f} {r['n_trades']:>5} {r['win_rate']:>5.1f}% {r['final_equity']:>11,.0f}")

    # Top 5 (안정형: MDD > -20%)
    stable = [r for r in results_2 if r['mdd'] > -20 and r['n_trades'] >= 30]
    stable.sort(key=lambda x: x['sharpe'], reverse=True)

    print("\n" + "="*60)
    print("🛡️ 안정형 Top 5 (MDD > -20%, 거래수 ≥ 30)")
    print("="*60)
    for i, r in enumerate(stable[:5]):
        d = f"{r['debt']}%" if r['debt'] < 9000 else "제한없음"
        print(f"\n#{i+1}: PEG≤{r['peg']}, 영이익≥{r['op_growth']:.0f}%, RSI<{r['rsi_upper']:.0f}, 부채≤{d}, ROE≥{r['roe']:.0f}%")
        print(f"    Exit: TP{r['tp']*100:.0f}%/SL{r['sl']*100:.0f}%/Hold{r['hold']}일")
        print(f"    CAGR={r['cagr']:.1f}%, MDD={r['mdd']:.1f}%, Sharpe={r['sharpe']:.2f}, N={r['n_trades']}, WR={r['win_rate']:.1f}%, 최종={r['final_equity']:,.0f}원")

    # Top 5 (공격형: Sharpe 최고)
    aggressive = [r for r in results_2 if r['n_trades'] >= 30][:5]

    print("\n" + "="*60)
    print("🚀 공격형 Top 5 (Sharpe 최고, 거래수 ≥ 30)")
    print("="*60)
    for i, r in enumerate(aggressive):
        d = f"{r['debt']}%" if r['debt'] < 9000 else "제한없음"
        print(f"\n#{i+1}: PEG≤{r['peg']}, 영이익≥{r['op_growth']:.0f}%, RSI<{r['rsi_upper']:.0f}, 부채≤{d}, ROE≥{r['roe']:.0f}%")
        print(f"    Exit: TP{r['tp']*100:.0f}%/SL{r['sl']*100:.0f}%/Hold{r['hold']}일")
        print(f"    CAGR={r['cagr']:.1f}%, MDD={r['mdd']:.1f}%, Sharpe={r['sharpe']:.2f}, N={r['n_trades']}, WR={r['win_rate']:.1f}%, 최종={r['final_equity']:,.0f}원")

    elapsed = time.time() - t0
    print(f"\n총 소요: {elapsed:.1f}초", flush=True)

    # 결과 저장
    best_stable = stable[0] if stable else None
    best_aggr = aggressive[0] if aggressive else None
    save_results(results_1[:20], results_2[:20], stable[:5], aggressive[:5], best_stable, best_aggr)


def save_results(top20_entry, top20_full, top5_stable, top5_aggr, best_s, best_a):
    lines = [
        "# 피터 린치 멀티버스 v3 — kis-template 코드 기반",
        f"분석일: 2026-02-14",
        f"**evaluate_buy/sell_conditions() 직접 호출** — 시뮬=실전 동일 로직",
        "",
    ]

    lines.append("## Step 1: Top 20 진입조건 (Exit 고정: TP50/SL15/120일)")
    lines.append("| # | PEG | 영이익 | RSI | 부채 | ROE | CAGR | MDD | Sharpe | 거래 | 승률 |")
    lines.append("|---|-----|--------|-----|------|-----|------|-----|--------|------|------|")
    for i, r in enumerate(top20_entry):
        d = f"{r['debt']}%" if r['debt'] < 9000 else "-"
        lines.append(f"| {i+1} | {r['peg']} | {r['op_growth']:.0f}% | {r['rsi_upper']:.0f} | {d} | {r['roe']:.0f}% | {r['cagr']:.1f}% | {r['mdd']:.1f}% | {r['sharpe']:.2f} | {r['n_trades']} | {r['win_rate']:.1f}% |")

    lines.append("")
    lines.append("## Step 2: Top 20 전체 파라미터")
    lines.append("| # | PEG | OPG | RSI | Debt | ROE | TP | SL | Hold | CAGR | MDD | Sharpe | N | WR |")
    lines.append("|---|-----|-----|-----|------|-----|----|----|------|------|-----|--------|---|-----|")
    for i, r in enumerate(top20_full):
        d = f"{r['debt']}" if r['debt'] < 9000 else "-"
        lines.append(f"| {i+1} | {r['peg']} | {r['op_growth']:.0f} | {r['rsi_upper']:.0f} | {d} | {r['roe']:.0f} | {r['tp']*100:.0f}% | {r['sl']*100:.0f}% | {r['hold']} | {r['cagr']:.1f}% | {r['mdd']:.1f}% | {r['sharpe']:.2f} | {r['n_trades']} | {r['win_rate']:.1f}% |")

    lines.append("")
    lines.append("## 🛡️ 안정형 Top 5 (MDD > -20%)")
    for i, r in enumerate(top5_stable):
        d = f"{r['debt']}%" if r['debt'] < 9000 else "제한없음"
        lines.append(f"\n### #{i+1}")
        lines.append(f"- 진입: PEG≤{r['peg']}, 영이익≥{r['op_growth']:.0f}%, RSI<{r['rsi_upper']:.0f}, 부채≤{d}, ROE≥{r['roe']:.0f}%")
        lines.append(f"- 매도: TP {r['tp']*100:.0f}%, SL {r['sl']*100:.0f}%, Hold {r['hold']}일")
        lines.append(f"- **CAGR {r['cagr']:.1f}%, MDD {r['mdd']:.1f}%, Sharpe {r['sharpe']:.2f}**, 거래 {r['n_trades']}건, 승률 {r['win_rate']:.1f}%")

    lines.append("")
    lines.append("## 🚀 공격형 Top 5 (Sharpe 최고)")
    for i, r in enumerate(top5_aggr):
        d = f"{r['debt']}%" if r['debt'] < 9000 else "제한없음"
        lines.append(f"\n### #{i+1}")
        lines.append(f"- 진입: PEG≤{r['peg']}, 영이익≥{r['op_growth']:.0f}%, RSI<{r['rsi_upper']:.0f}, 부채≤{d}, ROE≥{r['roe']:.0f}%")
        lines.append(f"- 매도: TP {r['tp']*100:.0f}%, SL {r['sl']*100:.0f}%, Hold {r['hold']}일")
        lines.append(f"- **CAGR {r['cagr']:.1f}%, MDD {r['mdd']:.1f}%, Sharpe {r['sharpe']:.2f}**, 거래 {r['n_trades']}건, 승률 {r['win_rate']:.1f}%")

    with open('/home/qwer/.openclaw/workspace/memory/analysis-lynch-multiverse-v3.md', 'w') as f:
        f.write('\n'.join(lines))
    print("\n결과 저장: memory/analysis-lynch-multiverse-v3.md")


if __name__ == '__main__':
    main()
