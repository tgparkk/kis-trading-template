# -*- coding: utf-8 -*-
"""검증 레인 보조 검사 (읽기 전용 · DB SELECT 만): F12b 동률 · snap_n 늦은 행 · 지수 시가 이상 · §3 17/75 다른 seed · §6 반전"""
import os, sys, io
import numpy as np, pandas as pd, psycopg2
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="kis_template", user="robotrader", password="1234")
conn.set_session(readonly=True)


def q(sql, p=None):
    cur = conn.cursor(); cur.execute(sql, p)
    return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])


C = pd.read_csv(os.path.join(HERE, "lots_features.csv"), dtype={"stock_code": str}, encoding="utf-8-sig")

# 1) F12 직전 SELL 동률(같은 timestamp 의 다른 전략 SELL 2건 이상)
T = q("""select b.id buy_id, b.stock_code, b.strategy, x.timestamp, count(*) n, string_agg(x.strategy, ',') strats
         from virtual_trading_records b join virtual_trading_records x on x.stock_code=b.stock_code and x.is_test and x.action='SELL'
              and x.timestamp<b.timestamp
         where b.is_test and b.action='BUY'
         group by 1,2,3,4 having count(*)>1""")
T = T[T.buy_id.isin(C.buy_id)]
last = q("""select b.id buy_id, max(x.timestamp) mx from virtual_trading_records b join virtual_trading_records x
            on x.stock_code=b.stock_code and x.is_test and x.action='SELL' and x.timestamp<b.timestamp
            where b.is_test and b.action='BUY' group by 1""")
T = T.merge(last, on="buy_id")
T = T[T.timestamp == T.mx]
print("[F12 동률] 직전 SELL 가 같은 시각 여러 건인 청산 로트:")
print(T.merge(C[["buy_id", "rebuy", "rebuy_same", "y_loss"]], on="buy_id").to_string())

# 2) snap_n 분모에 매수 뒤 생성 행이 섞인 로트
S = q("""select l.buy_id, l.ts, ss.created_at, ss.stock_code
         from (select unnest(%s::int[]) buy_id, unnest(%s::text[]) strategy, unnest(%s::date[]) d1, unnest(%s::timestamptz[]) ts) l
         join screener_snapshots ss on ss.strategy=l.strategy and ss.scan_date=l.d1 where ss.created_at>=l.ts""",
      (C.buy_id.tolist(), C.strategy.tolist(), C.d1_date.tolist(),
       [pd.Timestamp(x).tz_localize("Asia/Seoul").isoformat() for x in C.buy_ts]))
print(f"[snap_n] 매수 뒤 생성 스냅샷 행 {len(S)} · 로트 {S.buy_id.nunique()}")
if len(S):
    b = S.buy_id.iloc[0]
    print("   ", C.loc[C.buy_id == b, ["buy_id", "strategy", "stock_code", "buy_ts", "d1_date", "snap_rank", "snap_n", "snap_created"]].to_string(index=False))
    print("    늦은 행 created_at 범위", S.created_at.min(), "~", S.created_at.max(), "· 행", len(S))

# 3) 지수 시가 이상(open=close 또는 open<=0)
I = q("select stock_code, date, open, close from daily_prices where stock_code in ('KOSPI','KOSDAQ') and (open is null or open<=0 or open=close)")
print("[지수 시가 이상]", I.values.tolist(), "· 해당 매수일 로트", int(C.buy_date.isin(I.date).sum()))

# 4) §3 «날 뺀» 구간 0 안 걸침 개수 — 독립 범주화 + 다른 seed
d = C.copy()
def qlab(v): return "없음" if pd.isna(v) else f"Q{int(v)}"
def cut(x, e, labs): return "없음" if pd.isna(x) else labs[int(np.searchsorted(e, x, side="left"))]
cats = {
    "F1": d.strat, "F2": d.snap_rank.map(lambda r: "없음" if pd.isna(r) else "1" if r <= 1 else "2-3" if r <= 3 else "4-6" if r <= 6 else "7+"),
    "F3": d.q_mcap.map(qlab), "F4a": d.q_r1d.map(qlab), "F4b": d.q_r5d.map(qlab), "F4c": d.q_r20d.map(qlab), "F5": d.q_vol20.map(qlab),
    "F6": d.gap_pct.map(lambda x: cut(x, [-3, -1, 1, 3], list("abcde"))), "F7": d.px_vs_d1_pct.map(lambda x: cut(x, [-5, -2, 0, 2], list("abcde"))),
    "F8": d.buy_hm.map(lambda h: "a" if h < "09:10" else "b" if h < "10:00" else "c" if h < "12:00" else "d"),
    "F9": d.idx_gap_pct.map(lambda x: cut(x, [-1.5, -0.5, 0.5, 1.5], list("abcde"))), "F10": d.q_tval.map(qlab), "F11": d.market,
    "F12a": d.rebuy_prior, "F12b": d.rebuy_same.where(d.rebuy_same != "없음", "XX"), "F13": d.cohold_other.astype(str),
    "F14": d.seq_day.clip(upper=5).astype(int).astype(str)}
rng = np.random.default_rng(99)
ud = np.array(sorted(d.buy_date.unique()))
pos = {k: np.where(d.buy_date.values == k)[0] for k in ud}
boots = [np.concatenate([pos[k] for k in rng.choice(ud, len(ud))]) for _ in range(1000)]
ldm = d.loss_dm.values; edm = d.excess_dm.values
n_big = n_keep = 0; kept = []
for f, s in cats.items():
    s = s.values
    for c in pd.unique(s):
        if f == "F12b" and c == "XX":
            continue
        m = s == c
        if m.sum() < 30:
            continue
        n_big += 1
        L, E = [], []
        for ix in boots:
            mm = m[ix]
            if mm.any():
                L.append(ldm[ix][mm].mean()); E.append(edm[ix][mm].mean())
        l = np.percentile(L, [2.5, 97.5]); e = np.percentile(E, [2.5, 97.5])
        if l[0] > 0 or l[1] < 0 or e[0] > 0 or e[1] < 0:
            n_keep += 1; kept.append(f"{f}:{c}")
print(f"[§3 다른 seed] n≥30 범주 {n_big} · 0 안 걸침 {n_keep}: {kept}")

# 5) §6 반전 · §1 날짜별
lose = d[d.profit_loss < 0]; win = d[d.profit_loss > 0]
for nm, m in [("F14 5+", d.seq_day >= 5), ("deep_mr", d.strat == "deep_mr"), ("ma5", d.strat == "ma5")]:
    print(f"[§6] {nm}: 패 {int(m[lose.index].sum())}/{len(lose)} · 승 {int(m[win.index].sum())}/{len(win)} · 0원 {int(m[d.profit_loss == 0].sum())}")
print("[§1] 10-13·10-15·10-30 매수 로트", [(d.buy_date == x).sum() for x in ["2026-10-13", "2026-10-15", "2026-10-30"]])
