# -*- coding: utf-8 -*-
"""패배 로트의 특징 — lots_features.csv → 표 → RESULTS.md (기술 통계만 · 판정 언어 없음)

실행: (RoboTrader_template 에서) python -X utf8 backtest/concept_axes/losing_lot_features/analyze.py
DB 접속 없음(csv 만 읽음). 부트스트랩 = 매수일 블록 1,000회 · seed 20261030.
"""
import os
import time

import numpy as np
import pandas as pd

T0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "lots_features.csv")
RES = os.path.join(HERE, "RESULTS.md")
LOG = os.path.join(HERE, "run_log.txt")
B = 1000
SEED = 20261030
SMALL = 30

d = pd.read_csv(CSV, dtype={"stock_code": str}, encoding="utf-8-sig")
N = len(d)
STRAT_ORDER = d.strat.value_counts().index.tolist()


def b5(x, edges, labels):
    if pd.isna(x):
        return "없음"
    for e, lab in zip(edges, labels):
        if x <= e:
            return lab
    return labels[-1]


# ---------- 범주 만들기 ----------
GAPL = ["≤−3", "−3~−1", "−1~+1", "+1~+3", ">+3"]
PXL = ["≤−5", "−5~−2", "−2~0", "0~+2", ">+2"]
IGL = ["≤−1.5", "−1.5~−0.5", "−0.5~+0.5", "+0.5~+1.5", ">+1.5"]
TL = ["09:00~09:10", "09:10~10:00", "10:00~12:00", "12:00~15:30"]
qlab = lambda v: "없음" if pd.isna(v) else f"Q{int(v)}"
d["F1"] = d.strat
d["F2"] = d.snap_rank.map(lambda r: b5(r, [1, 3, 6], ["1위", "2~3위", "4~6위", "7위+"]))
d["F3"] = d.q_mcap.map(qlab)
d["F4a"] = d.q_r1d.map(qlab)
d["F4b"] = d.q_r5d.map(qlab)
d["F4c"] = d.q_r20d.map(qlab)
d["F5"] = d.q_vol20.map(qlab)
d["F6"] = d.gap_pct.map(lambda x: b5(x, [-3, -1, 1, 3], GAPL))
d["F7"] = d.px_vs_d1_pct.map(lambda x: b5(x, [-5, -2, 0, 2], PXL))
d["F8"] = d.buy_hm.map(lambda h: TL[0] if h < "09:10" else TL[1] if h < "10:00" else TL[2] if h < "12:00" else TL[3])
d["F9"] = d.idx_gap_pct.map(lambda x: b5(x, [-1.5, -0.5, 0.5, 1.5], IGL))
d["F10"] = d.q_tval.map(qlab)
d["F11"] = d.market
d["F12a"] = d.rebuy_prior.map(lambda v: "재매수 아님" if v == "없음" else f"직전 {v}")
d["F12b"] = d.rebuy_same.map(lambda v: "재매수 아님" if v == "없음" else f"{v} 전략")
d["F13"] = d.cohold_other.map({0: "없음", 1: "다른 전략 보유 중"})
d["F14"] = d.seq_day.map(lambda s: "5번째+" if s >= 5 else f"{int(s)}번째")
d["F15a"] = d.weekday.map(dict(enumerate("월화수목금")))
d["F15b"] = d.month.map(lambda m: f"{int(m)}월")
d["period"] = np.where(d.buy_date < "2026-09-18", "~09-17", "09-18~")

FEATS = [("F1", "전략", STRAT_ORDER), ("F2", "후보 순위(D-1 스냅샷)", ["1위", "2~3위", "4~6위", "7위+", "없음"]),
         ("F3", "시총 5분위(D-1 · Q5 대형)", ["Q1", "Q2", "Q3", "Q4", "Q5"]),
         ("F4a", "전일 등락 1d 5분위", ["Q1", "Q2", "Q3", "Q4", "Q5"]),
         ("F4b", "5d 등락 5분위", ["Q1", "Q2", "Q3", "Q4", "Q5"]),
         ("F4c", "20d 등락 5분위", ["Q1", "Q2", "Q3", "Q4", "Q5"]),
         ("F5", "20일 변동성 5분위", ["Q1", "Q2", "Q3", "Q4", "Q5"]),
         ("F6", "당일 시가 갭 %", GAPL), ("F7", "매수가 vs D-1 종가 %", PXL), ("F8", "진입 시각", TL),
         ("F9", "지수 시가 갭 %(종목 시장)", IGL + ["없음"]),
         ("F10", "거래대금 5분위(D-1)", ["Q1", "Q2", "Q3", "Q4", "Q5"]),
         ("F11", "시장(stock_info)", ["KOSPI", "KOSDAQ", "없음"]),
         ("F12a", "재매수(5거래일 · 직전 종류)", ["재매수 아님", "직전 익절", "직전 손절", "직전 이탈·기타"]),
         ("F12b", "재매수(같은/다른 전략)", ["같은 전략", "다른 전략"]),
         ("F13", "다른 전략 동시 보유", ["없음", "다른 전략 보유 중"]),
         ("F14", "그날 그 전략 몇 번째 매수", ["1번째", "2번째", "3번째", "4번째", "5번째+"]),
         ("F15a", "요일", list("월화수목금")), ("F15b", "월", ["6월", "7월", "8월", "9월", "10월"])]

base_loss = d.y_loss.mean() * 100
base_stop = d.y_stop.mean() * 100
base_exc = d.excess_pct.mean()


def stats(g):
    return dict(n=len(g), loss=g.y_loss.mean() * 100, stop=g.y_stop.mean() * 100, gm=g.gross_pct.mean(),
                gmed=g.gross_pct.median(), em=g.excess_pct.mean(), emed=g.excess_pct.median(),
                edm=g.excess_dm.mean(), ldm=g.loss_dm.mean() * 100)


# ---------- 매수일 블록 부트스트랩 ----------
rng = np.random.default_rng(SEED)
dates = np.array(sorted(d.buy_date.unique()))
rows_by_date = {k: v.values for k, v in d.groupby("buy_date").groups.items()}
boot_idx = []
for _ in range(B):
    pick = rng.choice(dates, size=len(dates), replace=True)
    boot_idx.append(np.concatenate([rows_by_date[x] for x in pick]))

# 범주별 날 뺀 값(ldm·edm)의 부트스트랩 구간
ldm_v = d.loss_dm.values * 100
edm_v = d.excess_dm.values
cat_ci = {}
for code, _, cats in FEATS:
    col = d[code].values
    for c in cats:
        mask = col == c
        if mask.sum() == 0:
            continue
        ls, es = [], []
        for ix in boot_idx:
            m = mask[ix]
            if m.sum() == 0:
                continue
            ls.append(ldm_v[ix][m].mean())
            es.append(edm_v[ix][m].mean())
        cat_ci[(code, c)] = (np.percentile(ls, [2.5, 97.5]), np.percentile(es, [2.5, 97.5]))

# ---------- §2 1차원 표 ----------
one_rows = []
L2 = ["| 특징 | 범주 | n | 패배율 | 손절률 | 평균 gross | 중앙 gross | 평균 초과 | 중앙 초과 | 날 뺀 초과 | 날 뺀 패배율 |",
      "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
s = stats(d)
L2.append(f"| 전체 | — | {s['n']} | {s['loss']:.1f}% | {s['stop']:.1f}% | {s['gm']:+.2f} | {s['gmed']:+.2f} | "
          f"{s['em']:+.2f} | {s['emed']:+.2f} | 0 | 0 |")
for code, name, cats in FEATS:
    first = True
    for c in cats:
        g = d[d[code] == c]
        if len(g) == 0:
            continue
        s = stats(g)
        one_rows.append(dict(code=code, name=name, cat=c, **s))
        tag = "†" if s["n"] < SMALL else ""
        lab = f"{code} {name}" if first else ""
        first = False
        L2.append(f"| {lab} | {c}{tag} | {s['n']} | {s['loss']:.1f}% | {s['stop']:.1f}% | {s['gm']:+.2f} | "
                  f"{s['gmed']:+.2f} | {s['em']:+.2f} | {s['emed']:+.2f} | {s['edm']:+.2f} | {s['ldm']:+.1f}%p |")
one = pd.DataFrame(one_rows)
one["dloss"] = one.loss - base_loss
one["dexc"] = one.em - base_exc

# F2 K 상향 전후
f2p = []
for p in ["~09-17", "09-18~"]:
    sub = d[d.period == p]
    parts = []
    for c in ["1위", "2~3위", "4~6위", "7위+", "없음"]:
        g = sub[sub.F2 == c]
        if len(g):
            parts.append(f"{c} {g.y_loss.mean() * 100:.0f}%({len(g)})")
    f2p.append(f"{p}(n={len(sub)}): " + " · ".join(parts))

# ---------- §1 표본 ----------
nw = int((d.profit_loss > 0).sum())
nl = int((d.profit_loss < 0).sum())
nz = int((d.profit_loss == 0).sum())
nstop = int(d.y_stop.sum())
cat_cnt = d.sell_cat.value_counts()
per_day = d.groupby("buy_date").size()
kret = d.groupby("buy_date").kospi_d0_ret_pct.first()
crash = kret[kret.abs() >= 3].sort_index()
crash_lots = int(d.buy_date.isin(crash.index).sum())
down = kret[kret <= -3].sort_index()
up = kret[kret >= 3].sort_index()
down_lots = int(d.buy_date.isin(down.index).sum())
up_lots = int(d.buy_date.isin(up.index).sum())
top5 = per_day.sort_values(ascending=False).head(5)
r2_exc = 1 - d.excess_dm.var(ddof=0) / d.excess_pct.var(ddof=0)
r2_loss = 1 - d.loss_dm.var(ddof=0) / d.y_loss.var(ddof=0)

# ---------- §4 전략 × 특징 ----------
X2 = [("F3", ["Q1", "Q2", "Q3", "Q4", "Q5"]), ("F6", GAPL), ("F7", PXL), ("F8", TL),
      ("F12a", ["재매수 아님", "직전 익절", "직전 손절", "직전 이탈·기타"])]
L4 = ["| 특징 | 범주 | " + " | ".join(STRAT_ORDER) + " |", "|---|---|" + "--:|" * len(STRAT_ORDER)]
for code, cats in X2:
    first = True
    for c in cats:
        cells = []
        for st in STRAT_ORDER:
            g = d[(d[code] == c) & (d.strat == st)]
            if len(g) == 0:
                cells.append("·")
            else:
                tag = "†" if len(g) < SMALL else ""
                cells.append(f"{g.y_loss.mean() * 100:.0f}·{g.excess_pct.mean():+.1f}({len(g)}){tag}")
        L4.append(f"| {code if first else ''} | {c} | " + " | ".join(cells) + " |")
        first = False

# ---------- §5 선형확률모형(OLS) + 블록 부트스트랩 ----------
def dummies(col, base, cats):
    return {f"{col}={c}": (d[col] == c).astype(float).values for c in cats if c != base}


Xd = {"절편": np.ones(N)}
Xd.update(dummies("F1", "ma5", STRAT_ORDER))
Xd.update(dummies("F3", "Q3", ["Q1", "Q2", "Q3", "Q4", "Q5"]))
Xd.update(dummies("F4a", "Q3", ["Q1", "Q2", "Q3", "Q4", "Q5"]))
Xd.update(dummies("F6", "−1~+1", GAPL))
Xd.update(dummies("F7", "−2~0", PXL))
Xd.update(dummies("F8", "09:10~10:00", TL))
Xd["F9 지수갭(%p 당)"] = d.idx_gap_pct.fillna(0).values
Xd["F9 지수갭 없음"] = d.idx_gap_pct.isna().astype(float).values
Xd["F12 재매수"] = d.rebuy.astype(float).values
names = list(Xd)
X = np.column_stack([Xd[k] for k in names])
y = d.y_loss.values.astype(float)
beta = np.linalg.lstsq(X, y, rcond=None)[0]
bb = np.array([np.linalg.lstsq(X[ix], y[ix], rcond=None)[0] for ix in boot_idx])
lo, hi = np.percentile(bb, [2.5, 97.5], axis=0)
ncol = X.sum(axis=0)
L5 = ["| 변수 | 계수 [95%] | n(=1) | 변수 | 계수 [95%] | n(=1) |", "|---|---|--:|---|---|--:|"]
cells = []
for k, b_, l_, h_, n_ in zip(names, beta, lo, hi, ncol):
    star = "" if l_ <= 0 <= h_ else " ◆"
    nn = "—" if k in ("절편", "F9 지수갭(%p 당)") else str(int(n_))
    cells.append(f"{k} | {b_:+.3f} [{l_:+.3f}, {h_:+.3f}]{star} | {nn}")
for i in range(0, len(cells), 2):
    L5.append("| " + cells[i] + " | " + (cells[i + 1] if i + 1 < len(cells) else "| |") + " |")
n_excl0 = sum(1 for k, l_, h_ in zip(names, lo, hi) if k != "절편" and not (l_ <= 0 <= h_))

# ---------- §3 날 효과 분리: 원 차이 vs 날 뺀 차이 ----------
big = one[(one.n >= SMALL) & (~one.code.isin(["F15a", "F15b"]))].copy()  # 요일·월 = 매수일 안 상수 → 날 뺀 값 0
big["ldm_lo"] = [cat_ci[(r.code, r.cat)][0][0] for r in big.itertuples()]
big["ldm_hi"] = [cat_ci[(r.code, r.cat)][0][1] for r in big.itertuples()]
big["edm_lo"] = [cat_ci[(r.code, r.cat)][1][0] for r in big.itertuples()]
big["edm_hi"] = [cat_ci[(r.code, r.cat)][1][1] for r in big.itertuples()]
big["keep"] = (big.ldm_lo > 0) | (big.ldm_hi < 0) | (big.edm_lo > 0) | (big.edm_hi < 0)
top_loss = big.sort_values("dloss", ascending=False).head(3)
low_loss = big.sort_values("dloss").head(3)
kept = big[big.keep].copy()
kept["absd"] = kept.ldm.abs()
kept = kept.sort_values("absd", ascending=False)


def fmt_row3(r):
    return (f"| {r.code} {r.cat} | {int(r.n)} | {r.loss:.1f}% | {r.dloss:+.1f}%p | {r.ldm:+.1f}%p "
            f"[{r.ldm_lo:+.1f}, {r.ldm_hi:+.1f}] | {r.em:+.2f} | {r.edm:+.2f} [{r.edm_lo:+.2f}, {r.edm_hi:+.2f}] |")


L3 = ["| 범주 | n | 패배율 | 원 차이 | 날 뺀 패배율 [95%] | 평균 초과 | 날 뺀 초과 [95%] |", "|---|--:|--:|--:|--:|--:|--:|"]
for r in kept.head(12).itertuples():
    L3.append(fmt_row3(r))
rest = kept.iloc[12:]
L3_rest = " · ".join(f"{r.code} {r.cat}(n={int(r.n)}) 날 뺀 패배율 {r.ldm:+.1f}%p [{r.ldm_lo:+.1f}, {r.ldm_hi:+.1f}] · 날 뺀 초과 {r.edm:+.2f} [{r.edm_lo:+.2f}, {r.edm_hi:+.2f}]" for r in rest.itertuples())

# ---------- §6 반전 검사 ----------
L6 = ["| 범주(패배율 상위 3 · n≥30) | 패배 로트 중 비율 | 승리 로트 중 비율 | 전체 중 비율 | 0원 로트 |", "|---|--:|--:|--:|--:|"]
lose = d[d.profit_loss < 0]
win = d[d.profit_loss > 0]
for r in top_loss.itertuples():
    a = (lose[r.code] == r.cat).sum()
    b = (win[r.code] == r.cat).sum()
    t = (d[r.code] == r.cat).sum()
    z = ((d.profit_loss == 0) & (d[r.code] == r.cat)).sum()
    L6.append(f"| {r.code} {r.cat} (패배율 {r.loss:.1f}% · n={int(r.n)}) | {a / len(lose) * 100:.1f}% ({a}/{len(lose)}) | "
              f"{b / len(win) * 100:.1f}% ({b}/{len(win)}) | {t / N * 100:.1f}% ({t}/{N}) | {z} |")

# ---------- RESULTS.md ----------
def pct(a, b):
    return f"{a / b * 100:.1f}% ({a}/{b})"


t1, t2, t3 = [r for r in top_loss.itertuples()]
l1, l2 = list(low_loss.itertuples())[:2]
o = []
o.append("# 패배 로트의 특징 — 결과 (2026-10-30 밤 · 읽기 전용 연구 · 관측·기술 통계만 · 룰 변경 0)")
o.append("")
o.append(f"> 표본 = `virtual_trading_records` is_test 청산 로트 {N}(SELL↔BUY rid 1:1 · 06-01~10-30 · 매수일 {len(dates)}) · "
         f"산출 = `lots_features.csv`(열 사전 `FEATURES.md`) · 표 = `analyze.py` · 부트스트랩 = 매수일 블록 {B}회(seed {SEED}) · "
         f"† = n<{SMALL} · 「초과」 = 로트 gross % − 같은 기간 전 종목 중앙값(%p) · 「날 뺀」 = 로트 값 − 같은 매수일 로트 평균.")
o.append("")
o.append("## §0 결론(사실만 · 5줄)")
o.append(f"1. 전체 패배율 {base_loss:.1f}% ({nl}/{N}) · 손절률 {base_stop:.1f}% ({nstop}/{N}) · 평균 초과 {base_exc:+.2f}%p. "
         f"패배율이 가장 높은 범주(n≥30) = {t1.code} «{t1.cat}» {t1.loss:.1f}%(n={int(t1.n)}) · {t2.code} «{t2.cat}» {t2.loss:.1f}%(n={int(t2.n)}) · "
         f"{t3.code} «{t3.cat}» {t3.loss:.1f}%(n={int(t3.n)}) vs 전체 {base_loss:.1f}%.")
o.append(f"2. 가장 낮은 범주(n≥30) = {l1.code} «{l1.cat}» {l1.loss:.1f}%(n={int(l1.n)} · 평균 초과 {l1.em:+.2f}%p) · {l2.code} «{l2.cat}» {l2.loss:.1f}%(n={int(l2.n)} · 평균 초과 {l2.em:+.2f}%p) vs 전체 {base_loss:.1f}%.")
o.append(f"3. «매수일 평균» 이 설명하는 몫 = 초과 수익 분산 {r2_exc * 100:.1f}% · 패배 여부 분산 {r2_loss * 100:.1f}% · "
         f"KOSPI 종가 ≤−3% 매수일 {len(down)}일 로트 {pct(down_lots, N)} · ≥+3% 매수일 {len(up)}일 로트 {pct(up_lots, N)}.")
o.append(f"4. 날 효과를 뺀 뒤 패배율 또는 초과의 95% 구간이 0 을 안 걸치는 범주(n≥30 · F15 제외) = {len(kept)}개/{len(big)}개(§3 · 사후 탐색 · 다중 비교 보정 없음).")
o.append(f"5. 다변량(선형확률모형 · 참고)에서 구간이 0 을 안 걸치는 계수 = {n_excl0}개/{len(names) - 1}개(§5 ◆).")
o.append("")
o.append("## §1 표본·결과 변수")
o.append(f"- 로트 {N} · 승(gross>0) {nw} · 패(gross<0) {nl} · 0원 {nz}(같은 초 왕복 6 포함) · 손절 청산 {nstop}(reason `손절%`) · "
         f"평균 gross {d.gross_pct.mean():+.2f}% · 중앙 {d.gross_pct.median():+.2f}% · 평균 초과 {base_exc:+.2f}%p · 중앙 초과 {d.excess_pct.median():+.2f}%p · "
         f"같은 기간 시장 중앙값 평균 {d.mkt_med_pct.mean():+.2f}%.")
o.append("- 매도 사유: " + " · ".join(f"{k} {v}" for k, v in cat_cnt.items()) + " · 보유 거래일 중앙 "
         f"{d.hold_tdays.median():.0f}(당일 왕복 {int((d.hold_tdays == 0).sum())}) · 보유 시간 중앙 {d.hold_hours.median():.1f}h · 전략별 n: "
         + " · ".join(f"{k} {v}" for k, v in d.strat.value_counts().items()) + ".")
o.append(f"- 매수일별 로트 수: 최소 {per_day.min()} · 중앙 {per_day.median():.0f} · 평균 {per_day.mean():.1f} · 최대 {per_day.max()} · "
         f"상위 5일 = " + " · ".join(f"{k[5:]} {v}" for k, v in top5.items()) + f"(합 {pct(int(top5.sum()), N)}).")
_dn = d.buy_date.isin(down.index)
_up = d.buy_date.isin(up.index)
o.append(f"- 매수일 KOSPI 종가 등락(`daily_prices` 의사티커 close/전일 close−1): **≤−3% {len(down)}일 · 로트 {pct(down_lots, N)} · 패배율 {d[_dn].y_loss.mean() * 100:.1f}%** "
         f"(" + " ".join(k[5:] for k in down.index) + f") · ≥+3% {len(up)}일 · 로트 {pct(up_lots, N)} · 패배율 {d[_up].y_loss.mean() * 100:.1f}% · "
         f"|등락|<3% {len(dates) - len(crash)}일 · 로트 {pct(N - crash_lots, N)} · 패배율 {d[~(_dn | _up)].y_loss.mean() * 100:.1f}%. 10-13·10-15·10-30 매수 청산 로트 = 각 "
         f"{int((d.buy_date == '2026-10-13').sum())}·{int((d.buy_date == '2026-10-15').sum())}·{int((d.buy_date == '2026-10-30').sum())}건 · 10-23 은 종가 +0.30%(장중 −3.20%)라 «<3%» 쪽.")
o.append("")
o.append("## §2 특징별 1차원 표(F1~F15 · 특징마다 한 묶음 · 수익 단위 % / %p)")
o.extend(L2)
o.append(f"- F2 K 상향(09-18) 전후 패배율(n): " + " / ".join(f2p) + ". F11 섹터 = `stock_info.sector` 전부 NULL(0/2,115) → 시장만. "
         f"F9 = ① 지수 시가 갭만(`minute_candles` 지수 의사티커 0행) · F9·F11 «없음» = `stock_info` 에 없는 종목 {int((d.market == '없음').sum())}로트. F15 «날 뺀» = 0(요일·월은 매수일 안에서 상수).")
o.append("")
o.append("## §3 날 효과 분리")
o.append(f"매수일 고정 효과 몫(분산 비율) = 초과 {r2_exc * 100:.1f}% · 패배 {r2_loss * 100:.1f}%. 1차원 표 «날 뺀» 두 열 = 같은 매수일 로트끼리 비교한 값(매수일 로트 1개인 날은 0). "
         f"아래 = n≥30 범주 {len(big)}개(F15 요일·월 제외) 중 «날 뺀 패배율» 또는 «날 뺀 초과» 95% 구간(매수일 블록 {B}회)이 0 을 안 걸치는 {len(kept)}개(|날 뺀 패배율| 큰 순 12 + 나머지 한 줄).")
o.extend(L3)
o.append("")
o.append(f"- 나머지 {len(rest)}: " + L3_rest + ".")
o.append("")
o.append("## §4 전략 × 특징(칸 = 패배율 %·평균 초과 %p(n) · † n<30 · · = 0건)")
o.extend(L4)
o.append("")
o.append("## §5 다변량(참고) — 패배(①) 선형확률모형(OLS · sklearn/statsmodels 없음 → numpy lstsq) · 매수일 블록 부트스트랩 1,000회 백분위 구간")
o.append(f"n={N} · 기준 범주: F1 ma5 · F3 Q3 · F4a Q3 · F6 −1~+1 · F7 −2~0 · F8 09:10~10:00 · F9 = 연속(%p) + 없음 표식(0 대입) · ◆ = 구간이 0 안 걸침 · 계수 = 패배 확률 차(0.1 = 10%p).")
o.extend(L5)
o.append("")
o.append("## §6 반전 검사 — 패배율 상위 3 범주가 승리 로트에도 같은 비율로 있나")
o.extend(L6)
o.append("")
o.append("## §7 한계(고정)")
o.append(f"- 로트 {N} 이나 독립 단위는 매수일 {len(dates)} · 급락일 몇 개가 지배(§1 · §3 분산 몫) · 06-01~10-30 하락 국면 한 번뿐.")
o.append("- 사후 탐색: 특징 15 · 범주 약 90 · 구간 보정 없음 → 0 안 걸침 몇 개는 우연으로도 나옴 · 발견 = 다음 그림자 측정 «후보 가설».")
o.append(f"- 미청산 로트 {1304 - N}건 제외(SR1) → 오래 들고 있는 손실 로트가 빠지는 쪽 편향 가능 · 같은 초 왕복 0원 6건 포함.")
o.append("- 룰 변화 구간 섞임: 09-18 K 상향 · 10-08 하루 한도 «매수만» · 10-20 다른 전략 보유 매수 허용 · 10-27~29 dt 수정 · 시장방향성필터 차단일.")
o.append("- 초과 수익의 시장 중앙값 = 매수일 종가→매도일 종가 근사(로트는 장중 체결가) · 당일 왕복은 그날 returns_1d 중앙값.")
o.append("- 섹터 없음(NULL) · 시장 = `stock_info` 현재 스냅샷 · 시총·거래대금 분위 = D-1 전 종목 기준(유니버스 아님) · 전략마다 후보 조건이 달라 분위가 전략 구성과 얽힘(§4).")
o[-1] += " · 선형확률모형 = 예측값이 0~1 밖일 수 있음 · 부트스트랩 표본에서 빈 범주는 lstsq 최소노름 해."
o.append("")
o.append("## §8 「모른다」")
o.append("- 진입 직전 지수 장중 등락(F9 ②): `minute_candles` 지수 의사티커 없음 → 측정 못 함.")
o.append("- 섹터 효과: 데이터 없음. 뉴스·수급·호가(체결 강도) 같은 진입 시각 정보는 이 표에 없음.")
o.append("- 같은 특징이 상승 국면에서도 같은 방향인지: 표본 기간에 상승 국면 없음 → 모름.")
o.append("- 특징 차이가 «종목 선택» 몫인지 «청산 규칙(손절폭·보유기간)» 몫인지: 전략별 청산 규칙이 달라 분리 안 함.")
o.append("")
o.append("## §9 검증 레인이 재현할 핵심 수치 10개")
o.append("| # | 값 | 재현(SQL · csv 열) |")
o.append("|---|---|---|")
o.append(f"| 1 | 청산 로트 {N} · 승 {nw} · 패 {nl} · 0원 {nz} | `select count(*), sum((profit_loss>0)::int), sum((profit_loss<0)::int) from virtual_trading_records where is_test and action='SELL'` |")
o.append(f"| 2 | 손절 청산 {nstop} | 같은 표 `reason like '손절%'` · csv `y_stop` |")
o.append(f"| 3 | 매수일 {len(dates)} · 로트/일 최대 {per_day.max()} | csv `buy_date`(BUY timestamp KST 날짜) |")
o.append(f"| 4 | 평균 gross {d.gross_pct.mean():+.3f}% · 평균 초과 {base_exc:+.3f}%p | csv `gross_pct`=profit_loss/(BUY price×quantity)·100 · `excess_pct`=gross_pct−`mkt_med_pct` |")
o.append(f"| 5 | 급락일 로트 {crash_lots} | csv `kospi_d0_ret_pct` abs≥3 · daily_prices KOSPI close/전일 close−1 |")
o.append(f"| 6 | {t1.code} «{t1.cat}» 패배율 {t1.loss:.1f}% (n={int(t1.n)}) | csv `{t1.code}` 범주 = analyze.py 규칙 · `y_loss` 평균 |")
o.append(f"| 7 | {t2.code} «{t2.cat}» 패배율 {t2.loss:.1f}% (n={int(t2.n)}) | 같음 |")
o.append(f"| 8 | 재매수 로트 {int(d.rebuy.sum())} · 패배율 {d[d.rebuy == 1].y_loss.mean() * 100:.1f}% | csv `rebuy`(같은 종목 SELL · 매수 전 · 0~5거래일) · 정의 교차 = 10-23~10-30 BUY 36/98 |")
o.append(f"| 9 | 매수일 분산 몫 초과 {r2_exc * 100:.1f}% · 패배 {r2_loss * 100:.1f}% | 1 − var(`excess_dm`)/var(`excess_pct`) · 1 − var(`loss_dm`)/var(`y_loss`) (ddof=0) |")
o.append(f"| 10 | 순위 있는 로트 {int(d.snap_rank.notna().sum())} · 지수갭 있는 로트 {int(d.idx_gap_pct.notna().sum())} | `screener_snapshots` scan_date=D-1·strategy·stock_code · csv `snap_rank` · `idx_gap_pct` |")

o = [x for i, x in enumerate(o) if not (x == "" and i + 1 < len(o) and o[i + 1].startswith("## "))]
with open(RES, "w", encoding="utf-8") as fh:
    fh.write("\n".join(o) + "\n")

lines = len(o)
msg = [f"# analyze.py", f"csv 행 {N} · 범주 표 행 {len(one)} · 부트스트랩 {B}회 · RESULTS.md {lines}줄",
       f"top3 패배율: " + " / ".join(f"{r.code} {r.cat} {r.loss:.1f}%(n={int(r.n)}) 초과 {r.em:+.2f}" for r in top_loss.itertuples()),
       f"날 뺀 뒤 0 안 걸침 범주 {len(kept)}/{len(big)} · LPM 0 안 걸침 계수 {n_excl0}/{len(names) - 1}",
       f"analyze rc=0 · {time.time() - T0:.1f}초"]
print("\n".join(msg))
prev = open(LOG, encoding="utf-8").read() if os.path.exists(LOG) else ""
prev = prev.split("# analyze.py")[0]
with open(LOG, "w", encoding="utf-8") as fh:
    fh.write(prev + "\n".join(msg) + "\n")
