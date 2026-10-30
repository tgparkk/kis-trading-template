# -*- coding: utf-8 -*-
"""검증 레인 독립 재현 (읽기 전용 · DB SELECT 만 · 레인 코드 import 0)
실행: venv python -X utf8 -I vf_reproduce.py   (DB = kis_template · resolver 와 같은 값)
결과 변수·핵심 범주는 SQL 로 다시 만들고, 레인 csv 는 «비교»와 일부 연속 특징(F3·F4a·F6·F7·F9 값)에만 쓴다.
"""
import os, sys, io
import numpy as np, pandas as pd, psycopg2
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
PSEUDO = ('KOSPI', 'KOSDAQ', 'KOSPI200', 'KRX100', 'KOSDAQ150', 'KTOP30')
conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="kis_template", user="robotrader", password="1234")
conn.set_session(readonly=True)


def q(sql, p=None):
    cur = conn.cursor(); cur.execute(sql, p)
    return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])


# ---- 1. 로트(SQL 로 직접) + 당일 순번 + 재매수 ----
L = q("""
with cal as (select date::date d, row_number() over (order by date) i from daily_prices where stock_code='KOSPI'),
b as (select id, stock_code, strategy, price::float8 price, quantity, timestamp ts,
             (timestamp at time zone 'Asia/Seoul')::date bd,
             row_number() over (partition by strategy, (timestamp at time zone 'Asia/Seoul')::date order by timestamp, id) seq
      from virtual_trading_records where is_test and action='BUY'),
s as (select id, buy_record_id, price::float8 sprice, timestamp ts, reason, profit_loss::float8 pl,
             (timestamp at time zone 'Asia/Seoul')::date sd from virtual_trading_records where is_test and action='SELL')
select s.id sell_id, b.id buy_id, b.strategy, b.stock_code, b.ts bts, s.ts sts, b.bd, s.sd, b.price, b.quantity, s.pl,
       s.reason, b.seq, cb.i bi, cs.i si, (select d from cal where i=cb.i-1) d1,
       exists(select 1 from virtual_trading_records x join cal cx on cx.d=(x.timestamp at time zone 'Asia/Seoul')::date
              where x.is_test and x.action='SELL' and x.stock_code=b.stock_code and x.timestamp<b.ts and cb.i-cx.i between 0 and 5) rebuy,
       (select x.strategy from virtual_trading_records x join cal cx on cx.d=(x.timestamp at time zone 'Asia/Seoul')::date
              where x.is_test and x.action='SELL' and x.stock_code=b.stock_code and x.timestamp<b.ts and cb.i-cx.i between 0 and 5
              order by x.timestamp desc limit 1) rebuy_strat
from s join b on b.id=s.buy_record_id join cal cb on cb.d=b.bd join cal cs on cs.d=s.sd
""")
L["y_loss"] = (L.pl < 0).astype(int)
L["y_stop"] = L.reason.fillna("").str.startswith("손절").astype(int)
L["gross"] = L.pl / (L.price * L.quantity) * 100
nb = q("select count(*) n from virtual_trading_records where is_test and action='BUY'").n[0]
print(f"[1] 로트 {len(L)} · 승 {(L.pl > 0).sum()} · 패 {(L.pl < 0).sum()} · 0원 {(L.pl == 0).sum()} · BUY {nb} → 미청산 {nb - len(L)}")
print(f"[2] 손절 {L.y_stop.sum()} ({L.y_stop.mean() * 100:.1f}%) · 패배율 {L.y_loss.mean() * 100:.1f}%")
pdays = L.groupby("bd").size()
print(f"[3] 매수일 {pdays.size} · 최대 {pdays.max()} ({pdays.idxmax()}) · 당일 왕복 {(L.bi == L.si).sum()}")

# ---- 2. 시장 중앙값(SQL percentile_cont · eq_median.py 규칙) ----
pairs = L[["bd", "sd"]].drop_duplicates()
bs = [str(x) for x in pairs.bd]
ss_ = [str(x) for x in pairs.sd]
M = q("""
with p as (select unnest(%s::text[]) b, unnest(%s::text[]) s)
select p.b, p.s,
  case when p.b=p.s then
    (select percentile_cont(0.5) within group (order by returns_1d) from daily_prices
      where date=p.b and volume>0 and returns_1d is not null and stock_code not in %s)
  else
    (select percentile_cont(0.5) within group (order by t.close/x.close-1) from daily_prices x join daily_prices t
       on t.stock_code=x.stock_code and t.date=p.s and t.volume>0
      where x.date=p.b and x.volume>0 and x.close>0 and x.stock_code not in %s)
  end med
from p""", (bs, ss_, PSEUDO, PSEUDO))
M["key"] = M.b + "|" + M.s
L["key"] = L.bd.astype(str) + "|" + L.sd.astype(str)
L["med"] = L.key.map(dict(zip(M.key, M.med.astype(float)))) * 100
L["exc"] = L.gross - L.med
print(f"[4] 평균 gross {L.gross.mean():+.3f}% · 평균 초과 {L.exc.mean():+.3f}%p · 중앙 초과 {L.exc.median():+.2f} · 시장 중앙값 평균 {L.med.mean():+.2f}")

# ---- 3. 급락일(KOSPI close/전일 close) ----
K = q("select date, close from daily_prices where stock_code='KOSPI' order by date")
K["r"] = (K.close / K.close.shift(1) - 1) * 100
kr = dict(zip(K.date, K.r))
L["kr"] = L.bd.astype(str).map(kr)
dn = L.kr <= -3
up = L.kr >= 3
print(f"[5] |KOSPI|≥3% 매수일 로트 {(dn | up).sum()} (≤−3: {dn.sum()}·{L[dn].bd.nunique()}일·패배율 {L[dn].y_loss.mean() * 100:.1f}% / ≥+3: {up.sum()}·{L[up].bd.nunique()}일)")

# ---- 4. 범주 ----
SH = {"book_pullback_ma5": "ma5", "rs_leader": "rs", "daytrading_3methods_breakout": "dt", "book_pullback_ma20": "ma20",
      "elder_ema_pullback": "elder", "book_envelope_200d": "env", "minervini_volume_dryup": "minervini", "deep_mr_dev20": "deep_mr"}
L["strat"] = L.strategy.map(SH)
L["dm_exc"] = L.exc - L.groupby("bd").exc.transform("mean")
L["dm_loss"] = L.y_loss - L.groupby("bd").y_loss.transform("mean")
L["hm"] = pd.to_datetime(L.bts).dt.tz_convert("Asia/Seoul").dt.strftime("%H:%M:%S")


def show(name, m):
    g = L[m]
    print(f"    {name}: n={len(g)} 패배율 {g.y_loss.mean() * 100:.1f}% 손절 {g.y_stop.mean() * 100:.1f}% 평균 초과 {g.exc.mean():+.2f} "
          f"날뺀 패배 {g.dm_loss.mean() * 100:+.1f}%p 날뺀 초과 {g.dm_exc.mean():+.2f}")


print("[6~8] 범주")
show("F14 5번째+", L.seq >= 5)
for st in ["ma5", "rs", "dt", "ma20", "elder", "env", "minervini", "deep_mr"]:
    show(f"F1 {st}", L.strat == st)
show("F8 09:00~09:10", L.hm < "09:10")
show("F8 09:10~10:00", (L.hm >= "09:10") & (L.hm < "10:00"))
show("F8 10:00~12:00", (L.hm >= "10:00") & (L.hm < "12:00"))
show("재매수", L.rebuy)
show("F12b 같은 전략", L.rebuy & (L.rebuy_strat == L.strategy))
show("F12b 다른 전략", L.rebuy & (L.rebuy_strat != L.strategy))
r2e = 1 - L.dm_exc.var(ddof=0) / L.exc.var(ddof=0)
r2l = 1 - L.dm_loss.var(ddof=0) / L.y_loss.var(ddof=0)
print(f"[9] 매수일 분산 몫 초과 {r2e * 100:.1f}% · 패배 {r2l * 100:.1f}%")

# ---- 5. 스냅샷 순위(scan_date=D-1) · 지수갭 ----
S = q("""select l.buy_id, min(ss.rank_in_snapshot) rk, max(ss.created_at) cmax, min(ss.created_at) cmin
         from (select unnest(%s::int[]) buy_id, unnest(%s::text[]) strategy, unnest(%s::text[]) code, unnest(%s::date[]) d1) l
         join screener_snapshots ss on ss.strategy=l.strategy and ss.stock_code=l.code and ss.scan_date=l.d1
         group by l.buy_id""", (L.buy_id.tolist(), L.strategy.tolist(), L.stock_code.tolist(), [str(x) for x in L.d1]))
SN = q("""select l.buy_id, max(ss.created_at) nmax
         from (select unnest(%s::int[]) buy_id, unnest(%s::text[]) strategy, unnest(%s::date[]) d1) l
         join screener_snapshots ss on ss.strategy=l.strategy and ss.scan_date=l.d1 group by l.buy_id""",
       (L.buy_id.tolist(), L.strategy.tolist(), [str(x) for x in L.d1]))
L = L.merge(S, on="buy_id", how="left").merge(SN, on="buy_id", how="left")
print(f"[10] 순위 있는 로트 {L.rk.notna().sum()} · 그 종목 스냅샷 행 created_at ≥ 매수 시각 {(L.cmax >= L.bts).sum()} · "
      f"그 전략·날 스냅샷 전체(snap_n 분모) 중 created_at ≥ 매수 시각 있는 로트 {(L.nmax >= L.bts).sum()}")
gapmin = (L.bts - L.nmax).dt.total_seconds()
print(f"     (매수 시각 − 그 전략·날 스냅샷 마지막 created_at) 최소 {gapmin.min():.1f}초 · 중앙 {gapmin.median():.0f}초")
SI = q("select stock_code, market from stock_info")
L = L.merge(SI, on="stock_code", how="left")
print(f"     지수갭 있는 로트(market∈KOSPI/KOSDAQ) {L.market.isin(['KOSPI', 'KOSDAQ']).sum()}")

# ---- 6. 레인 csv 와 행 단위 대조 ----
C = pd.read_csv(os.path.join(HERE, "lots_features.csv"), dtype={"stock_code": str}, encoding="utf-8-sig")
J = L.merge(C, on="buy_id", suffixes=("", "_lane"))
print(f"[대조] 맞춘 행 {len(J)} · |초과 차| 최대 {np.abs(J.exc - J.excess_pct).max():.2e} · seq 불일치 {(J.seq != J.seq_day).sum()} · "
      f"rebuy 불일치 {(J.rebuy.astype(int) != J.rebuy_lane).sum()} · y_loss 불일치 {(J.y_loss != J.y_loss_lane).sum()} · "
      f"y_stop 불일치 {(J.y_stop != J.y_stop_lane).sum()} · rank 불일치 {((J.rk != J.snap_rank) & J.rk.notna()).sum()}")

# ---- 7. 부트스트랩: 날짜 블록 vs 로트 단위 (독립 구현 · seed 다름) ----
rng = np.random.default_rng(7)
days = L.bd.values
ud = np.unique(days)
pos = {d: np.where(days == d)[0] for d in ud}


def ci(mask, v, block, B=1000):
    out = []
    for _ in range(B):
        ix = np.concatenate([pos[d] for d in rng.choice(ud, len(ud))]) if block else rng.integers(0, len(L), len(L))
        m = mask[ix]
        if m.any():
            out.append(v[ix][m].mean())
    return np.percentile(out, [2.5, 97.5])


for name, m in [("F1 dt", (L.strat == "dt").values), ("F8 09:00~09:10", (L.hm < "09:10").values),
                ("F12b 같은 전략", (L.rebuy & (L.rebuy_strat == L.strategy)).values)]:
    a = ci(m, L.dm_loss.values * 100, True)
    b = ci(m, L.dm_loss.values * 100, False)
    print(f"[부트] {name} 날뺀 패배율 95%: 날짜 블록 [{a[0]:+.1f}, {a[1]:+.1f}] · 로트 단위 [{b[0]:+.1f}, {b[1]:+.1f}]")

# ---- 8. 선형확률모형 부호 ----
C2 = C.set_index("buy_id").loc[L.buy_id]


def cut(x, e):
    return np.where(np.isnan(x), -1, np.searchsorted(e, x, side="left"))


cols = {"절편": np.ones(len(L))}
for st in ["rs", "dt", "ma20", "elder", "env", "minervini", "deep_mr"]:
    cols[f"F1={st}"] = (L.strat == st).astype(float).values
for qn, nm_ in [("q_mcap", "F3"), ("q_r1d", "F4a")]:
    for k in [1, 2, 4, 5]:
        cols[f"{nm_}=Q{k}"] = (C2[qn].values == k).astype(float)
g6 = cut(C2.gap_pct.values, [-3, -1, 1, 3])
g7 = cut(C2.px_vs_d1_pct.values, [-5, -2, 0, 2])
for k in [0, 1, 3, 4]:
    cols[f"F6={k}"] = (g6 == k).astype(float)
for k in [0, 1, 3, 4]:
    cols[f"F7={k}"] = (g7 == k).astype(float)
cols["F8=09:00~09:10"] = (L.hm < "09:10").astype(float).values
cols["F8=10~12"] = ((L.hm >= "10:00") & (L.hm < "12:00")).astype(float).values
cols["F8=12~"] = (L.hm >= "12:00").astype(float).values
ig = C2.idx_gap_pct.values
cols["F9"] = np.nan_to_num(ig)
cols["F9 없음"] = np.isnan(ig).astype(float)
cols["재매수"] = L.rebuy.astype(float).values
nm = list(cols)
X = np.column_stack([cols[k] for k in nm])
y = L.y_loss.values.astype(float)
beta = np.linalg.lstsq(X, y, rcond=None)[0]
bb = []
for _ in range(1000):
    ix = np.concatenate([pos[d] for d in rng.choice(ud, len(ud))])
    bb.append(np.linalg.lstsq(X[ix], y[ix], rcond=None)[0])
lo, hi = np.percentile(np.array(bb), [2.5, 97.5], axis=0)
print("[LPM] 0 안 걸침:", [f"{k} {b:+.3f} [{l:+.3f},{h:+.3f}]" for k, b, l, h in zip(nm, beta, lo, hi) if not (l <= 0 <= h)])
for k in ["F1=dt", "F1=ma20", "F8=09:00~09:10", "재매수", "F1=minervini"]:
    i = nm.index(k)
    print(f"      {k} {beta[i]:+.3f} [{lo[i]:+.3f}, {hi[i]:+.3f}]")

# ---- 9. 누출 보조 검사 ----
print(f"[누출] 매수 시각 최소 {L.hm.min()} · d1 < 매수일 전부 {(pd.to_datetime(L.d1) < pd.to_datetime(L.bd)).all()}")
big = C[(C.px_vs_d1_pct.abs() > 25) | (C.gap_pct.abs() > 25)]
print(f"[누출] |괴리|·|갭| >25% 로트 {len(big)}:", big[["stock_code", "buy_date", "gap_pct", "px_vs_d1_pct"]].round(1).values.tolist()[:10])
AF = q("""select l.code, l.bd, count(*) n from (select unnest(%s::text[]) code, unnest(%s::text[]) d1, unnest(%s::text[]) bd) l
          join daily_prices dp on dp.stock_code=l.code and dp.date between l.d1 and l.bd and coalesce(dp.adj_factor,1)<>1
          group by 1,2""", (L.stock_code.tolist(), [str(x) for x in L.d1], [str(x) for x in L.bd]))
print(f"[누출] D-1~매수일 adj_factor≠1 행이 있는 로트 {len(AF)}")
