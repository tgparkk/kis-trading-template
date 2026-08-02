# -*- coding: utf-8 -*-
"""
STEP 1 — 동결 증명 + 데이터 준비
  * 처치군 날짜 661일을 코드에서 명시적으로 제외하고, 제외를 출력으로 증명한다.
  * 결과변수는 이 스크립트에서 계산하지 않는다 (가격 wide 행렬만 만든다).
"""
import os, sys, json, re, collections
import numpy as np, pandas as pd, psycopg2
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\GIT\kis-trading-template\RoboTrader_template\backtest\tasso_labels"
OUT  = os.path.join(BASE, "power")
os.makedirs(OUT, exist_ok=True)
DSN = dict(host="127.0.0.1", port=5433, dbname="kis_template",
           user="robotrader", password="1234")

# ---------------------------------------------------------------- 1. 라벨
lab = pd.read_csv(os.path.join(BASE, "labels_v5.csv"), dtype={"stock_code": str})
print("labels_v5.csv:", lab.shape, "| cols:", lab.columns.tolist())

treat = lab[(lab["regime"] == "검색기단타") & (lab["usable"] == True)].copy()
treat["post_date"] = treat["post_date"].astype(str).str[:10]
TREAT_DATES = sorted(treat["post_date"].unique())
print("\n[처치군] 행 %d · 고유종목 %d · 고유날짜 %d"
      % (len(treat), treat["stock_code"].nunique(), len(TREAT_DATES)))
print("         기간 %s ~ %s" % (TREAT_DATES[0], TREAT_DATES[-1]))

# 날짜당 처치 행수 분포 (전체)
cnt_all = treat.groupby("post_date").size()
print("[처치군] 날짜당 행수 분포(전체):", dict(sorted(collections.Counter(cnt_all).items())),
      "| 평균 %.4f" % cnt_all.mean())

# ---- C-B 커버 판정: PREREG §2.3-(c) 정규식 원본 (붙여넣기, 손으로 옮겨 적지 않음)
MA_TOK = r"(?:\d+\s*일\s*(?:이동평균선|이동평균|이평선|이평|선)|이동평균선|이평선|이평|장기\s*이평)"
RX = collections.OrderedDict([
    ("T3_ma_bounce",  re.compile(MA_TOK + r"[^,/]{0,6}?(?:반등|지지|눌림|터치)|눌림목")),
    ("T4_ma_break",   re.compile(MA_TOK + r"[^,/]{0,6}?돌파")),
    ("T2_prev_high",  re.compile(r"전일\s*고")),
    ("T1_prior_high", re.compile(r"직전\s*고|전고\b|전고점|전고\s*돌파|신고가")),
    ("T5_consec_up",  re.compile(r"연속\s*상승|연속\s*양봉")),
])
m = treat["method"].fillna("").astype(str)
cov = m.apply(lambda s: any(rx.search(s) for rx in RX.values()))
tcov = treat[cov]
cnt_cov = tcov.groupby("post_date").size()
print("\n[C-B 커버(정규식만)] 행 %d · 종목 %d · 날짜 %d | 커버율 %.2f%%"
      % (len(tcov), tcov["stock_code"].nunique(), cnt_cov.size, 100*len(tcov)/len(treat)))
print("[C-B 커버] 날짜당 행수 분포:", dict(sorted(collections.Counter(cnt_cov).items())),
      "| 평균 %.4f" % cnt_cov.mean())

for nm, rx in RX.items():
    print("   %-14s %5d" % (nm, m.apply(lambda s, r=rx: bool(r.search(s))).sum()))

# 연도별
treat["yr"] = treat["post_date"].str[:4]
print("\n[처치군] 연도별 행/날짜:")
for y, g in treat.groupby("yr"):
    print("   %s  행 %4d · 날짜 %3d" % (y, len(g), g["post_date"].nunique()))

# ---------------------------------------------------------------- 2. 거래일 캘린더
conn = psycopg2.connect(**DSN)
cal = pd.read_sql("""
    SELECT DISTINCT date FROM daily_prices
    WHERE date >= to_char(DATE '2021-01-04','YYYY-MM-DD')
      AND date <= to_char(DATE '2024-12-31','YYYY-MM-DD')
    ORDER BY date
""", conn)["date"].astype(str).tolist()
print("\n[캘린더] 2021-01-04~2024-12-31 거래일 %d" % len(cal))

SPARSE = ["2021-01-04","2021-01-05","2021-01-06","2021-01-07","2021-01-08","2021-01-11",
          "2024-03-04","2024-03-05","2024-03-06","2024-03-07","2024-03-08","2024-03-11","2024-03-12"]
print("[희소일] 사전 명시 %d일" % len(SPARSE))

calset, tset, sset = set(cal), set(TREAT_DATES), set(SPARSE)
print("[검사] 처치날짜 중 캘린더 밖:", sorted(tset - calset))
EST = sorted(calset - tset - sset)

# ---------------- 동결 증명 -------------------------------------------------
print("\n" + "="*72)
print("동결 증명 — 분산 추정 표본에서 처치 날짜를 명시적으로 제외했다")
print("="*72)
print("  캘린더 거래일           D_cal  = %d" % len(cal))
print("  처치군 사용 날짜(제외)  D_tr   = %d" % len(tset))
print("  희소일(제외)            D_sp   = %d  (그중 캘린더 내 %d, 처치일과 중복 %d)"
      % (len(SPARSE), len(sset & calset), len(sset & tset)))
print("  ⇒ 분산 추정 표본        D_est  = %d" % len(EST))
print("  검산: %d - %d - %d(중복제거) = %d"
      % (len(cal), len(tset & calset), len(sset & calset - tset), len(EST)))
print("  [PROOF] EST ∩ TREAT_DATES = %d 건  (0 이어야 함)" % len(set(EST) & tset))
print("  [PROOF] EST ∩ SPARSE      = %d 건  (0 이어야 함)" % len(set(EST) & sset))
assert len(set(EST) & tset) == 0 and len(set(EST) & sset) == 0
print("  EST 범위: %s ~ %s" % (EST[0], EST[-1]))

# EST 의 연도/월 분포 (대표성 진단용)
es = pd.Series(EST)
print("\n[EST 연도별]", dict(es.str[:4].value_counts().sort_index()))
cs = pd.Series(cal); cs_t = cs[cs.isin(tset)]
print("[캘린더 연도별]", dict(cs.str[:4].value_counts().sort_index()))
print("[처치 연도별  ]", dict(cs_t.str[:4].value_counts().sort_index()))
ym = es.str[:7].value_counts().sort_index()
print("\n[EST 월별 건수]")
for kk, vv in ym.items():
    print("   %s : %2d" % (kk, vv))

json.dump({"EST": EST, "TREAT_DATES": TREAT_DATES, "CAL": cal, "SPARSE": SPARSE},
          open(os.path.join(OUT, "date_sets.json"), "w"), ensure_ascii=False)

# n_d 분포 저장
json.dump({"full": dict(sorted(collections.Counter(cnt_all).items())),
           "cb_cov": dict(sorted(collections.Counter(cnt_cov).items())),
           "N_T": int(len(treat)), "N_T_stocks": int(treat["stock_code"].nunique()),
           "N_T_dates": int(len(TREAT_DATES)),
           "N_CB": int(len(tcov)), "N_CB_stocks": int(tcov["stock_code"].nunique()),
           "N_CB_dates": int(cnt_cov.size)},
          open(os.path.join(OUT, "nd_dist.json"), "w"), ensure_ascii=False)

# ---------------------------------------------------------------- 3. 가격 wide 행렬
print("\n[DB] daily_prices 로드 (2020-11-01 ~ 2025-04-30) ...")
px = pd.read_sql("""
    SELECT date, stock_code, open, high, low, close, trading_value
    FROM daily_prices
    WHERE date >= to_char(DATE '2020-11-01','YYYY-MM-DD')
      AND date <= to_char(DATE '2025-04-30','YYYY-MM-DD')
""", conn)
conn.close()
px["date"] = px["date"].astype(str)
print("   rows=%d  dates=%d  codes=%d" % (len(px), px["date"].nunique(), px["stock_code"].nunique()))

dates = np.array(sorted(px["date"].unique()))
codes = np.array(sorted(px["stock_code"].unique()))
di = {d: i for i, d in enumerate(dates)}
ci = {c: i for i, c in enumerate(codes)}
T, S = len(dates), len(codes)
ri = px["date"].map(di).values
cj = px["stock_code"].map(ci).values

def wide(col):
    a = np.full((T, S), np.nan, dtype=np.float64)
    a[ri, cj] = pd.to_numeric(px[col], errors="coerce").values
    return a

O, H, L, C, TV = (wide(x) for x in ["open","high","low","close","trading_value"])
np.savez_compressed(os.path.join(OUT, "px_wide.npz"),
                    dates=dates, codes=codes,
                    O=O.astype(np.float32), H=H.astype(np.float32),
                    L=L.astype(np.float32), C=C.astype(np.float32),
                    TV=TV.astype(np.float64))
print("   wide 저장 완료: (%d dates, %d codes)" % (T, S))

valid = (~np.isnan(O)) & (~np.isnan(H)) & (~np.isnan(L)) & (~np.isnan(C)) \
        & (O > 0) & (H > 0) & (L > 0) & (C > 0)
print("   OHLC 전체가드 통과 셀 %d / 관측행 %d  (결함 %d)"
      % (valid.sum(), len(px), len(px) - valid.sum()))
print("\nSTEP1 DONE")
