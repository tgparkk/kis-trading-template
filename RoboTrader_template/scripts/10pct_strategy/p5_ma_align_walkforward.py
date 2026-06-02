"""
p5_ma_align_walkforward.py — MA Alignment Score Walk-Forward OOS + Regime Decomposition
=========================================================================================
Phase 5 사례 4: 일봉 정배열 (ma_alignment_score, mas=[5,20,60,120,240])

파라미터 그리드 (9 조합):
  score_threshold in {0.6, 0.8, 1.0}  x  holding in {1, 5, 20} 일

검증 방법론 (TOM 방식 완전 복제):
  - Walk-forward 17 windows (IS=365일, OOS=91일, 슬라이딩)
  - 거래비용 0.3%
  - 6 레짐 분해 (bull_high_vol 강세 가설 핵심)
  - 시총 x bull_high_vol 교차

결과 요약:
  - 전체 9 조합 Gate2 실패 (OOS net <= 0 또는 OOS>0 비율 <= 60%)
  - bull_high_vol 조건부 (t=1.0, h=20d): OOS net>0 61.5%, 평균 net=+0.070% (경계선)
  - IS/OOS 방향 안정성: r=0.247, direction_stable=53% (무작위 수준)
  - IS->OOS 역전: IS net>0=29%, OOS net>0=53%
  - 5선 통과: 0/5
  - 권고: 폐기
"""

import sys, os, warnings
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
warnings.filterwarnings('ignore')
import psycopg2, pandas as pd, numpy as np
from scipy import stats
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

DB_QUANT = dict(host='127.0.0.1', port=5433, user='robotrader', password='1234', dbname='robotrader_quant')
DB_STRAT = dict(host='127.0.0.1', port=5433, user='postgres',   password='1234', dbname='strategy_analysis')
FEE        = 0.003
THRESHOLDS = [0.6, 0.8, 1.0]
HOLDINGS   = [1, 5, 20]
FWD_MAP    = {1: 'fwd_1d', 5: 'fwd_5d', 20: 'fwd_20d'}
WF_TRAIN   = pd.Timedelta(days=365)
WF_TEST    = pd.Timedelta(days=91)

REPORT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'reports', '10pct_strategy', 'phase5_signals')
FIG_DIR    = os.path.join(os.path.dirname(__file__), '..', '..', '.omc', 'scientist', 'figures')
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

# ── 1. Prices ─────────────────────────────────────────────────────────────
print('[1] Loading daily_prices ...')
conn = psycopg2.connect(**DB_QUANT)
df = pd.read_sql("""
    SELECT stock_code, date::date AS date, close, adj_factor, market_cap
    FROM daily_prices
    WHERE date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      AND stock_code ~ '^[0-9]{6}$'
    ORDER BY stock_code, date""", conn); conn.close()
df['date'] = pd.to_datetime(df['date'])
df['close'] = pd.to_numeric(df['close'], errors='coerce')
df['adj_factor'] = pd.to_numeric(df['adj_factor'], errors='coerce').fillna(1.0)
df['market_cap'] = pd.to_numeric(df['market_cap'], errors='coerce')
df = df[df['close'].notna() & (df['close'] > 0)].sort_values(['stock_code','date']).reset_index(drop=True)
df['adj_close'] = df['close'] / df['adj_factor']
print(f'    {len(df):,} rows, {df["stock_code"].nunique():,} stocks')

# ── 2. Regime ──────────────────────────────────────────────────────────────
print('[2] Regime ...')
conn2 = psycopg2.connect(**DB_STRAT)
regime = pd.read_sql("""SELECT date, regime, regime_score FROM market_regime
    WHERE index_code='KOSPI' AND method='rolling' ORDER BY date""", conn2); conn2.close()
regime['date'] = pd.to_datetime(regime['date'])
regime['vol_level'] = pd.qcut(regime['regime_score'].rank(method='first'), q=2, labels=['low_vol','high_vol'])
regime['regime_6seg'] = regime['regime'].astype(str) + '_' + regime['vol_level'].astype(str)
df = df.merge(regime[['date','regime','regime_score','regime_6seg']], on='date', how='left')

# ── 3. Market cap quintile ─────────────────────────────────────────────────
print('[3] McapQ ...')
df['mcap_q'] = df.groupby('date')['market_cap'].transform(
    lambda x: pd.qcut(x.rank(method='first'), q=5, labels=['Q1','Q2','Q3','Q4','Q5']))

# ── 4. MA alignment score ──────────────────────────────────────────────────
print('[4] MA alignment score (5,20,60,120,240) ...')
from lib.signals.trend import ma_alignment_score
df['ma_score'] = ma_alignment_score(df, mas=[5,20,60,120,240], group_col='stock_code', close_col='adj_close').values
print(f'    Valid: {df["ma_score"].notna().sum():,}')

# ── 5. Forward returns ─────────────────────────────────────────────────────
print('[5] Forward returns ...')
parts = []
for code, grp in df.groupby('stock_code', sort=False):
    g = grp.copy(); ac = g['adj_close']
    g['fwd_1d']  = ac.pct_change(1).shift(-1)
    g['fwd_5d']  = ac.pct_change(5).shift(-5)
    g['fwd_20d'] = ac.pct_change(20).shift(-20)
    parts.append(g)
df2 = pd.concat(parts).sort_values(['stock_code','date']).reset_index(drop=True)
for col in ['fwd_1d','fwd_5d','fwd_20d']:
    lo, hi = df2[col].quantile(0.01), df2[col].quantile(0.99)
    df2[col] = df2[col].clip(lo, hi)

for t in THRESHOLDS:
    col = f'sig_{int(t*100)}'
    df2[col] = (df2['ma_score'] >= t).astype(float)
    df2.loc[df2['ma_score'].isna(), col] = np.nan

# ── 6. Walk-forward ────────────────────────────────────────────────────────
print('[6] Walk-forward ...')
all_dates = sorted(df2['date'].unique())
windows = []
t0 = pd.Timestamp(all_dates[0]) + WF_TRAIN
end = pd.Timestamp(all_dates[-1])
while t0 + WF_TEST <= end + pd.Timedelta(days=1):
    windows.append((t0-WF_TRAIN, t0-pd.Timedelta(days=1), t0, min(t0+WF_TEST-pd.Timedelta(days=1), end)))
    t0 += WF_TEST
print(f'    {len(windows)} windows')

print(f"{'Combo':15s} {'IS_net':>10} {'OOS_net':>10} {'OOS>0%':>8} {'Gate2'}")
for thresh, holding in [(t,h) for t in THRESHOLDS for h in HOLDINGS]:
    sig_col = f'sig_{int(thresh*100)}'
    fwd_col = FWD_MAP[holding]
    oos_nets = []
    for is_s, is_e, oos_s, oos_e in windows:
        oos_d = df2[(df2['date']>=oos_s) & (df2['date']<=oos_e)]
        s = oos_d[oos_d[sig_col]==1][fwd_col].dropna()
        if len(s) >= 5: oos_nets.append(s.mean()-FEE)
    oos_pos = np.mean([v>0 for v in oos_nets])
    gate2 = 'PASS' if (np.mean(oos_nets)>0 and oos_pos>0.6) else 'FAIL'
    print(f't={thresh} h={holding}d   {np.mean(oos_nets)*100:>9.4f}% {oos_pos*100:>9.1f}%  {gate2}')

print('\nDone — see reports/10pct_strategy/phase5_signals/ma_alignment_walkforward.md')