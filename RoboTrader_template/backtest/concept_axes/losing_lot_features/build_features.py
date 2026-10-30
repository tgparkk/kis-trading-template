# -*- coding: utf-8 -*-
"""패배 로트의 특징 — 특징 표 만들기 (읽기 전용 연구 · DB SELECT 만 · KIS API 0)

DB → lots_features.csv (청산 로트 1행 = SELL 1건 ↔ BUY(buy_record_id) 1건)
🔴 모든 특징은 진입 BUY timestamp(KST) 이전에 존재한 값만: D-1 일봉 · 당일 시가(매수 ≥09:00) ·
   매수 전 SELL/BUY 기록 · scan_date=D-1 스냅샷. 당일 종가·당일 returns_1d·매도 뒤 가격은 특징 아님
   (결과 변수 ③ 초과 수익의 «시장 중앙값»에만 씀).
실행: (RoboTrader_template 에서) PYTHONPATH=$PWD:$PWD/.. python -X utf8 backtest/concept_axes/losing_lot_features/build_features.py
"""
import os
import time

import numpy as np
import pandas as pd
import psycopg2

try:
    from config.constants import resolve_daily_source_db
    DBNAME = resolve_daily_source_db()
except Exception:  # resolver 와 같은 값
    DBNAME = "kis_template"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lots_features.csv")
LOG = os.path.join(HERE, "run_log.txt")
PSEUDO = ("KOSPI", "KOSDAQ", "KOSPI200", "KRX100", "KOSDAQ150", "KTOP30")
SHORT = {"book_pullback_ma5": "ma5", "rs_leader": "rs", "daytrading_3methods_breakout": "dt",
         "book_pullback_ma20": "ma20", "elder_ema_pullback": "elder", "book_envelope_200d": "env",
         "minervini_volume_dryup": "minervini", "deep_mr_dev20": "deep_mr"}

T0 = time.time()
log_lines = []


def log(s):
    print(s)
    log_lines.append(s)


def reason_cat(r):
    r = r or ""
    if r.startswith("손절"):
        return "손절"
    if r.startswith("목표 익절") or r.startswith("익절"):
        return "익절"
    if r.startswith("MA20 이탈") or r.startswith("MA20×"):
        return "MA 이탈"
    if "trailing" in r or r.startswith("트레일링") or r.startswith("EMA13"):
        return "trailing"
    if r.startswith("EMA"):
        return "EMA"
    if r.startswith("보유기간") or r.startswith("장기보유"):
        return "기간"
    return "기타"


def prior_cat(rc):
    return {"손절": "손절", "익절": "익절"}.get(rc, "이탈·기타")


conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname=DBNAME, user="robotrader", password="1234")
conn.set_session(readonly=True)


def q(sql, p=None):
    cur = conn.cursor()
    cur.execute(sql, p)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


# ---------- 1. 기록 ----------
vtr = q("""select id, stock_code, action, quantity, price::float8 as price,
                  (timestamp at time zone 'Asia/Seoul') as ts, strategy, reason,
                  profit_loss::float8 as profit_loss, buy_record_id
           from virtual_trading_records where is_test""")
vtr["ts"] = pd.to_datetime(vtr.ts)
buys = vtr[vtr.action == "BUY"].copy()
sells = vtr[vtr.action == "SELL"].copy()
sells["rcat"] = sells.reason.map(reason_cat)
log(f"vtr is_test: BUY {len(buys)} · SELL {len(sells)} · SELL rid 있음 {int(sells.buy_record_id.notna().sum())}")

lots = sells.merge(buys, left_on="buy_record_id", right_on="id", suffixes=("_s", "_b"), how="inner")
assert len(lots) == len(sells), "SELL↔BUY 1:1 실패"
assert (lots.stock_code_s == lots.stock_code_b).all() and (lots.strategy_s == lots.strategy_b).all()
assert (lots.ts_s >= lots.ts_b).all(), "매도 시각 < 매수 시각"
log(f"같은 초 왕복(매도 시각 = 매수 시각) 로트 {int((lots.ts_s == lots.ts_b).sum())} · 그 손익 합 {lots.loc[lots.ts_s == lots.ts_b, 'profit_loss_s'].sum():.0f}")
lots = pd.DataFrame({
    "sell_id": lots.id_s, "buy_id": lots.id_b, "strategy": lots.strategy_b,
    "strat": lots.strategy_b.map(SHORT).fillna(lots.strategy_b), "stock_code": lots.stock_code_b,
    "buy_ts": lots.ts_b, "buy_price": lots.price_b, "qty": lots.quantity_b,
    "sell_ts": lots.ts_s, "sell_price": lots.price_s, "sell_reason": lots.reason_s,
    "sell_cat": lots.rcat, "profit_loss": lots.profit_loss_s,
})
lots["buy_date"] = lots.buy_ts.dt.strftime("%Y-%m-%d")
lots["sell_date"] = lots.sell_ts.dt.strftime("%Y-%m-%d")
lots["gross_pct"] = lots.profit_loss / (lots.buy_price * lots.qty) * 100
lots["hold_hours"] = (lots.sell_ts - lots.buy_ts).dt.total_seconds() / 3600
lots["y_loss"] = (lots.profit_loss < 0).astype(int)
lots["y_stop"] = lots.sell_reason.fillna("").str.startswith("손절").astype(int)

# ---------- 2. 일봉 ----------
dp = q("""select stock_code, date, open, close, volume, trading_value, market_cap,
                 returns_1d, returns_5d, returns_20d, volatility_20d
          from daily_prices where date >= '2026-04-20' and date <= '2026-10-30'""")
for c in ["open", "close", "trading_value", "market_cap", "returns_1d", "returns_5d", "returns_20d",
          "volatility_20d", "volume"]:
    dp[c] = pd.to_numeric(dp[c], errors="coerce").astype(float)
cal = sorted(dp.loc[dp.stock_code == "KOSPI", "date"].unique())
tidx = {d: i for i, d in enumerate(cal)}
prev_day = {cal[i]: cal[i - 1] for i in range(1, len(cal))}
assert all(d in tidx for d in lots.buy_date) and all(d in tidx for d in lots.sell_date), "달력 밖 날짜"
lots["d1_date"] = lots.buy_date.map(prev_day)
lots["hold_tdays"] = lots.sell_date.map(tidx) - lots.buy_date.map(tidx)

idx = dp[dp.stock_code.isin(["KOSPI", "KOSDAQ"])].set_index(["stock_code", "date"])
eq = dp[~dp.stock_code.isin(PSEUDO)].copy()
# 분위(전 종목 · 그날 기준 · Q1 = 낮음) — returns/vol/거래대금 = volume>0 종목 · 시총 = market_cap>0 종목
live = eq[eq.volume > 0].copy()
for col, qn in [("returns_1d", "q_r1d"), ("returns_5d", "q_r5d"), ("returns_20d", "q_r20d"),
                ("volatility_20d", "q_vol20"), ("trading_value", "q_tval")]:
    pct = live.groupby("date")[col].rank(pct=True)
    live[qn] = np.ceil(pct * 5).clip(1, 5)
mc = eq[eq.market_cap > 0].copy()
mc["q_mcap"] = np.ceil(mc.groupby("date").market_cap.rank(pct=True) * 5).clip(1, 5)
d1 = eq.set_index(["stock_code", "date"])[["close", "returns_1d", "returns_5d", "returns_20d",
                                            "volatility_20d", "trading_value", "market_cap", "volume"]]
d1q = live.set_index(["stock_code", "date"])[["q_r1d", "q_r5d", "q_r20d", "q_vol20", "q_tval"]]
d1m = mc.set_index(["stock_code", "date"])[["q_mcap"]]
key1 = pd.MultiIndex.from_arrays([lots.stock_code, lots.d1_date])
f = d1.reindex(key1).reset_index(drop=True)
lots["d1_close"] = f.close.values
lots["d1_volume"] = f.volume.values
for c in ["returns_1d", "returns_5d", "returns_20d", "volatility_20d"]:
    lots[f"d1_{c}"] = (f[c] * 100).values
lots["d1_trading_value"] = f.trading_value.values
lots["d1_market_cap"] = f.market_cap.values
fq = d1q.reindex(key1).reset_index(drop=True)
for c in fq.columns:
    lots[c] = fq[c].values
lots["q_mcap"] = d1m.reindex(key1).reset_index(drop=True).q_mcap.values
d0 = eq.set_index(["stock_code", "date"])[["open"]].reindex(
    pd.MultiIndex.from_arrays([lots.stock_code, lots.buy_date]))
lots["d0_open"] = d0.open.values
lots["gap_pct"] = (lots.d0_open / lots.d1_close - 1) * 100
lots["px_vs_d1_pct"] = (lots.buy_price / lots.d1_close - 1) * 100

# ---------- 3. 시장(stock_info) · 지수 갭 ----------
si = q("select stock_code, market, sector from stock_info")
si_n_sector = int(si.sector.notna().sum())
lots = lots.merge(si, on="stock_code", how="left")
lots["market"] = lots.market.fillna("없음")
log(f"stock_info: 종목 {len(si)} · sector 값 있음 {si_n_sector} → F11 섹터 = 전부 없음(시장만 사용)")


def idx_gap(row):
    m = row.market if row.market in ("KOSPI", "KOSDAQ") else None
    if m is None:
        return np.nan
    try:
        o = idx.loc[(m, row.buy_date), "open"]
        c = idx.loc[(m, row.d1_date), "close"]
    except KeyError:
        return np.nan
    return (o / c - 1) * 100 if c and o else np.nan


lots["idx_gap_pct"] = lots.apply(idx_gap, axis=1)
kospi_close = idx.loc["KOSPI", "close"].sort_index()
kospi_ret = (kospi_close / kospi_close.shift(1) - 1) * 100
lots["kospi_d0_ret_pct"] = lots.buy_date.map(kospi_ret)  # 🔴 결과 해석용(급락일 표식) · 특징 아님

# ---------- 4. 스크리너 순위(scan_date = D-1) ----------
ss = q("""select strategy, scan_date::text as scan_date, stock_code, rank_in_snapshot,
                 (created_at at time zone 'Asia/Seoul') as snap_created
          from screener_snapshots""")
ss["snap_created"] = pd.to_datetime(ss.snap_created)
ssn = ss.groupby(["strategy", "scan_date"]).stock_code.count().rename("snap_n").reset_index()
ss1 = ss.groupby(["strategy", "scan_date", "stock_code"]).agg(snap_rank=("rank_in_snapshot", "min"),
                                                               snap_created=("snap_created", "min")).reset_index()
lots = lots.merge(ss1, left_on=["strategy", "d1_date", "stock_code"],
                  right_on=["strategy", "scan_date", "stock_code"], how="left").drop(columns=["scan_date"])
lots = lots.merge(ssn, left_on=["strategy", "d1_date"], right_on=["strategy", "scan_date"],
                  how="left").drop(columns=["scan_date"])
lots["snap_rank_pct"] = lots.snap_rank / lots.snap_n

# ---------- 5. 재매수 · 동시 보유 · 당일 순번 ----------
sells_all = sells[["stock_code", "ts", "strategy", "rcat"]].copy()
sells_all["date"] = sells_all.ts.dt.strftime("%Y-%m-%d")
sell_by_lot = sells.set_index("buy_record_id").ts
buys_all = buys[["id", "stock_code", "ts", "strategy"]].copy()
buys_all["sell_ts"] = buys_all.id.map(sell_by_lot)  # NaT = 미청산
buys_all["date"] = buys_all.ts.dt.strftime("%Y-%m-%d")
buys_all = buys_all.sort_values(["ts", "id"])
buys_all["seq_day"] = buys_all.groupby(["strategy", "date"]).cumcount() + 1  # 같은 시각 = id 순
lots["seq_day"] = lots.buy_id.map(buys_all.set_index("id").seq_day)


def in_window(bi, d):
    return 0 <= bi - tidx.get(d, -999) <= 5


sg = {k: v.sort_values("ts") for k, v in sells_all.groupby("stock_code")}
bg = {k: v for k, v in buys_all.groupby("stock_code")}
rb_flag, rb_prior, rb_same, rb_tdiff, rb_prior_ts, co_hold = [], [], [], [], [], []
for r in lots.itertuples():
    bi = tidx[r.buy_date]
    s = sg.get(r.stock_code)
    hit = None
    if s is not None:
        cand = s[s.ts < r.buy_ts]
        cand = cand[cand.date.map(lambda d: in_window(bi, d))]
        if len(cand):
            hit = cand.iloc[-1]
    rb_flag.append(int(hit is not None))
    rb_prior.append(prior_cat(hit.rcat) if hit is not None else "없음")
    rb_same.append(("같은" if hit.strategy == r.strategy else "다른") if hit is not None else "없음")
    rb_tdiff.append(bi - tidx[hit.date] if hit is not None else np.nan)
    rb_prior_ts.append(hit.ts if hit is not None else pd.NaT)
    b = bg[r.stock_code]
    oth = b[(b.strategy != r.strategy) & (b.ts < r.buy_ts) & (b.sell_ts.isna() | (b.sell_ts > r.buy_ts))]
    co_hold.append(int(len(oth) > 0))
lots["rebuy"] = rb_flag
lots["rebuy_prior"] = rb_prior
lots["rebuy_same"] = rb_same
lots["rebuy_tdiff"] = rb_tdiff
lots["rebuy_prior_ts"] = pd.to_datetime(pd.Series(rb_prior_ts))
lots["cohold_other"] = co_hold

# 교차 확인: 보고서 10-30 6장 누적 표 10-23~10-30 매수 재매수 36/98(BUY 전체 · 미청산 포함)
chk = buys_all[(buys_all.date >= "2026-10-23") & (buys_all.date <= "2026-10-30")]
n_rb = 0
for r in chk.itertuples():
    s = sg.get(r.stock_code)
    if s is None:
        continue
    bi = tidx[r.date]
    c = s[s.ts < r.ts]
    if c.date.map(lambda d: in_window(bi, d)).any():
        n_rb += 1
log(f"재매수 정의 교차 확인(BUY 10-23~10-30 · 미청산 포함): {n_rb}/{len(chk)} (보고서 10-30 6장 = 36/98)")

# ---------- 6. 시각 · 요일 ----------
lots["buy_hm"] = lots.buy_ts.dt.strftime("%H:%M:%S")
lots["weekday"] = lots.buy_ts.dt.dayofweek
lots["month"] = lots.buy_ts.dt.month

# ---------- 7. 결과 ③ 초과 수익(시장 중앙값 = 결과 쪽에만 사용) ----------
close_p = eq.pivot(index="date", columns="stock_code", values="close")
vol_p = eq.pivot(index="date", columns="stock_code", values="volume")
r1_p = eq.pivot(index="date", columns="stock_code", values="returns_1d")
med_cache = {}
for b, s in set(zip(lots.buy_date, lots.sell_date)):
    if b == s:
        ok = vol_p.loc[b] > 0
        med_cache[(b, s)] = float(np.median(r1_p.loc[b][ok].dropna())) * 100
    else:
        ok = (vol_p.loc[b] > 0) & (vol_p.loc[s] > 0) & (close_p.loc[b] > 0)
        rr = (close_p.loc[s][ok] / close_p.loc[b][ok] - 1).dropna()
        med_cache[(b, s)] = float(np.median(rr)) * 100
lots["mkt_med_pct"] = [med_cache[(b, s)] for b, s in zip(lots.buy_date, lots.sell_date)]
lots["excess_pct"] = lots.gross_pct - lots.mkt_med_pct
lots["excess_dm"] = lots.excess_pct - lots.groupby("buy_date").excess_pct.transform("mean")
lots["loss_dm"] = lots.y_loss - lots.groupby("buy_date").y_loss.transform("mean")

# ---------- 8. 누출 자가검사 ----------
leak = {}
leak["D-1 일봉(분위 포함) 날짜 < 매수일"] = bool((lots.d1_date < lots.buy_date).all())
leak["당일 시가(F6·F9) 쓰는 로트 매수 시각 ≥ 09:00:00 KST"] = bool((lots.buy_hm >= "09:00:00").all())
leak["스냅샷 scan_date(=D-1) < 매수일"] = bool((lots.d1_date < lots.buy_date).all())
m = lots.snap_created.notna()
n_snap_late = int((lots.loc[m, "snap_created"] >= lots.loc[m, "buy_ts"]).sum())
leak[f"스냅샷 created_at < 매수 시각(순위 있는 로트 {int(m.sum())})"] = n_snap_late == 0
mr = lots.rebuy == 1
leak["F12 직전 SELL 시각 < 매수 시각"] = bool((lots.loc[mr, "rebuy_prior_ts"] < lots.loc[mr, "buy_ts"]).all())
leak["F13 다른 전략 BUY 시각 < 매수 시각(코드 조건)"] = True
leak["F14 순번 = 같은 날 같은 전략 앞선 BUY 수 + 1(시각순)"] = True
FEATURE_COLS = ["strat", "snap_rank", "snap_n", "snap_rank_pct", "q_mcap", "d1_market_cap", "d1_returns_1d",
                "d1_returns_5d", "d1_returns_20d", "q_r1d", "q_r5d", "q_r20d", "d1_volatility_20d", "q_vol20",
                "gap_pct", "px_vs_d1_pct", "buy_hm", "idx_gap_pct", "d1_trading_value", "q_tval", "market",
                "sector", "rebuy", "rebuy_prior", "rebuy_same", "cohold_other", "seq_day", "weekday", "month"]
forbidden = {"mkt_med_pct", "excess_pct", "kospi_d0_ret_pct", "sell_price", "gross_pct", "excess_dm", "loss_dm"}
leak["특징 열에 결과·당일 종가 파생 열 없음"] = not (set(FEATURE_COLS) & forbidden)
for k, v in leak.items():
    log(f"[누출 검사] {k}: {'PASS' if v else 'FAIL'}")
log(f"  스냅샷 created_at ≥ 매수 시각 로트 수 = {n_snap_late}")

lots = lots.sort_values(["buy_ts", "buy_id"]).reset_index(drop=True)
lots.drop(columns=["rebuy_prior_ts"]).to_csv(OUT, index=False, encoding="utf-8-sig")
log(f"lots_features.csv 행 {len(lots)} · 열 {lots.shape[1] - 1} · 매수일 {lots.buy_date.nunique()} · "
    f"D-1 일봉 결측 {int(lots.d1_close.isna().sum())} · d0 시가 결측 {int(lots.d0_open.isna().sum())} · "
    f"순위 있음 {int(lots.snap_rank.notna().sum())} · 지수갭 결측 {int(lots.idx_gap_pct.isna().sum())} · "
    f"시총분위 결측 {int(lots.q_mcap.isna().sum())}")
ok_all = all(leak.values())
log(f"build rc={0 if ok_all else 1} · {time.time() - T0:.1f}초")
with open(LOG, "w", encoding="utf-8") as fh:
    fh.write("# build_features.py\n" + "\n".join(log_lines) + "\n")
assert ok_all, "누출 검사 실패"
