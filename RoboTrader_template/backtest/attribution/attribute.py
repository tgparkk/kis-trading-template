# -*- coding: utf-8 -*-
"""06-01 이후 페이퍼가 전 종목 중앙값보다 뒤처진 몫의 4분해 (일회성 · 측정만 · 판정 없음).

대상 = 4전략(`book_envelope_200d`·`deep_mr_dev20`·`elder_ema_pullback`·`rs_leader`) 각각 + 4전략 equity 합.
기간 = 2026-06-01 → 2026-10-28 · 기준 = 06-01 equity(E0).

항등식(매 구간 k = 직전 equity 날짜 → 이번 equity 날짜):
    r_k − m_k = d_k + c_k + a_k   (정확히 성립 · 스크립트가 확인)
    d_k = PnL_pos,k / E_{k−1} − w_k·m_k          (종목 선택 · 보유 포지션 손익 − 투자비중×중앙값)
    c_k = (1 − w_k)·(0 − m_k)                    (현금 비중)
    a_k = −cost_k / E_{k−1}                      (비용 · cost_k = −(Δcash − (매도액 − 매수액)))
    PnL_pos,k = pv_k − pv_{k−1} + 매도액_k − 매수액_k · w_k = pv_{k−1}/E_{k−1}
헤드라인 a 는 브리프대로 −Σ(gross − net)/E0(net = 로그 `매매 손익 반영` · 없으면 가정 0.21%p).
잔차 = G − (a + c + d) 는 «복리 · 중앙값 합산 차 · 비용 기준 차» 3조각으로 다시 쪼개 찍는다.

반사실 b(항등식 밖) = 손절 SELL 의 「매도 뒤 10거래일 종가/매도가 − 1」×매도금액/E0 합.

🔴 SR1 봉인 4전략(ma20·minervini·daytrading·ma5)의 매도 뒤 가격은 조회하지 않는다 —
   가격 조회는 위 4전략 SELL 로만 한다. 8전략 equity 합은 대조(−23.03%)용으로만 읽는다.

라이브 트리 import 0 · DB 는 SELECT 만 · psycopg2 + pandas 만.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import psycopg2

BASE = Path(__file__).resolve().parent
DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
LOG_DIR = Path(os.environ.get("ATTR_LOG_DIR", "D:/GIT/kis-trading-template/RoboTrader_template/logs"))
START, END = "2026-06-01", "2026-10-28"
S4 = ("book_envelope_200d", "deep_mr_dev20", "elder_ema_pullback", "rs_leader")
PSEUDO = ("KOSPI", "KOSDAQ", "KOSPI200", "KRX100", "KOSDAQ150", "KTOP30")
FEE_BUY, FEE_SELL = 0.00015, 0.00015 + 0.0018   # 가정 비용 합 0.21%p
HORIZON = 10                                      # 반사실 b: 매도 뒤 거래일 수
PAIR_SEC = 5                                      # 로그 net ↔ DB SELL 시각 차 허용
ADJ_SUSPECT = 0.30                                # 매도가 vs 매도일 종가 괴리(기업행위 의심) 표시 기준
NET_RE = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \| core\.fund_manager \| INFO \| 매매 손익 반영: ([+-]?[\d,]+)원")

OUT: list[str] = []


def say(s: str = "") -> None:
    print(s)
    OUT.append(s)


def q(cur, sql: str, args=None) -> pd.DataFrame:
    cur.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def won(x: float) -> str:
    return f"{int(round(x)):,}"


def pp(x: float) -> str:
    return f"{x * 100:+.2f}%p"


# ── 데이터 ────────────────────────────────────────────────────────────────────
def load(cur):
    cal = q(cur, "SELECT date FROM daily_prices WHERE stock_code='KOSPI' AND date BETWEEN %s AND %s ORDER BY date",
            (START, END)).date.tolist()
    eq8 = q(cur, """SELECT trade_date::text AS d, strategy, cash::float8 AS cash, position_value::float8 AS pv,
                           equity::float8 AS "E"
                    FROM paper_strategy_equity WHERE trade_date BETWEEN %s AND %s""", (START, END))
    tr = q(cur, """SELECT s.id, (s.timestamp AT TIME ZONE 'Asia/Seoul')::date::text AS d,
                          (s.timestamp AT TIME ZONE 'Asia/Seoul') AS ts, s.strategy, s.action, s.stock_code,
                          s.quantity, s.price::float8 AS price, s.profit_loss::float8 AS gross, s.reason,
                          s.buy_record_id, b.price::float8 AS buy_price, b.quantity AS buy_qty
                   FROM virtual_trading_records s
                   LEFT JOIN virtual_trading_records b ON b.id = s.buy_record_id
                   WHERE s.is_test AND s.strategy IN %s
                     AND (s.timestamp AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
                   ORDER BY s.timestamp, s.id""", (S4, START, END))
    tr["amt"] = tr.price * tr.quantity
    return cal, eq8, tr


def interval_medians(cur, dates: list[str], cal: list[str]) -> dict:
    """구간 (s, t] 의 전 종목 중앙값. 연속 거래일이면 returns_1d · 건너뛰면 close_t/close_s − 1."""
    out = {}
    for s, t in zip(dates[:-1], dates[1:]):
        if cal.index(t) - cal.index(s) == 1:
            cur.execute("""SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY returns_1d) FROM daily_prices
                           WHERE date=%s AND volume>0 AND returns_1d IS NOT NULL AND stock_code NOT IN %s""",
                        (t, PSEUDO))
        else:
            cur.execute(MEDIAN_SQL, (s, PSEUDO, t, PSEUDO))
        out[t] = float(cur.fetchone()[0])
    return out


def path_medians(cur, dates: list[str]) -> dict:
    """보정안 벤치마크: I_t = 전 종목 (close_t/close_0 − 1) 중앙값(기간 중앙값과 같은 정의) · m_t = (1+I_t)/(1+I_{t−1}) − 1.
    곱하면 정확히 기간 중앙값이 된다(Π(1+m_t) = 1 + I_N)."""
    level = {dates[0]: 0.0}
    for t in dates[1:]:
        cur.execute(MEDIAN_SQL, (dates[0], PSEUDO, t, PSEUDO))
        level[t] = float(cur.fetchone()[0])
    return {t: (1 + level[t]) / (1 + level[s]) - 1 for s, t in zip(dates[:-1], dates[1:])}


MEDIAN_SQL = """
with s as (select stock_code, close from daily_prices where date=%s and volume>0 and stock_code not in %s),
     t as (select stock_code, close from daily_prices where date=%s and volume>0 and stock_code not in %s),
     r as (select s.stock_code, t.close/s.close-1 as ret from s join t using(stock_code) where s.close>0)
select percentile_cont(0.5) within group (order by ret), count(*), avg(case when ret>0 then 1 else 0 end) from r"""


# ── 로그 net 짝 맞추기 ────────────────────────────────────────────────────────
def log_costs(cur):
    """SELL id → (gross − net) 실측. 로그가 없거나 짝이 안 맞는 SELL 은 빠진다(가정 비용으로 채움)."""
    lines = defaultdict(list)
    files = sorted(LOG_DIR.glob("robotrader_template_2026*.log"))
    for f in files:
        day = f.name.split("_")[2]
        if not (START.replace("-", "") <= day <= END.replace("-", "")):
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                if "매매 손익 반영" not in ln:
                    continue
                m = NET_RE.match(ln)
                if m:
                    t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    lines[t.date().isoformat()].append((t, int(m.group(2).replace(",", ""))))
    # 짝은 그날 «전 전략» SELL 과 맞춘다(로그 줄이 전략명을 안 갖기 때문) — SELL 의 시각·gross·매도금액만 읽는다.
    # 같은 몇 초 안에 SELL 이 여럿이면 로그 순서 ≠ DB 순서인 날이 있어(단순 zip 은 19일에서 어긋남),
    # SELL 시각 순으로 ±PAIR_SEC 안의 안 쓴 로그 줄 중 «gross − net 이 0.21%×매도금액에 가장 가까운» 줄을 고른다.
    sells = q(cur, """SELECT id, (timestamp AT TIME ZONE 'Asia/Seoul') AS ts,
                             (timestamp AT TIME ZONE 'Asia/Seoul')::date::text AS d, profit_loss::float8 AS gross,
                             price::float8 * quantity AS amt
                      FROM virtual_trading_records
                      WHERE action='SELL' AND is_test AND (timestamp AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
                      ORDER BY timestamp, id""", (START, END))
    cost, multi, gap = {}, set(), {}
    n_lines = sum(len(v) for v in lines.values())
    for d, g in sells.groupby("d"):
        L = sorted(lines.get(d, []))
        used = set()
        for s in g.itertuples():
            ts = s.ts.replace(tzinfo=None)
            key = (FEE_BUY + FEE_SELL) * s.amt
            cand = [i for i, (t, _) in enumerate(L) if i not in used and abs((t - ts).total_seconds()) <= PAIR_SEC]
            if cand:
                i = min(cand, key=lambda i: abs(s.gross - L[i][1] - key))
                used.add(i)
                cost[s.id] = s.gross - L[i][1]
                gap[s.id] = abs((L[i][0] - ts).total_seconds())
                if len(cand) > 1:
                    multi.add(s.id)
    return cost, multi, gap, len(files), len(lines), n_lines, len(sells)


# ── 분해 ─────────────────────────────────────────────────────────────────────
def decompose(eqs: pd.DataFrame, trs: pd.DataFrame, med: dict, M: float):
    """eqs: d·cash·pv·E (한 전략 또는 합) · trs: 같은 범위 거래. 구간 단위 표 + 합계 성분."""
    e = eqs.sort_values("d").reset_index(drop=True)
    buy = trs[trs.action == "BUY"].groupby("d").amt.sum()
    sell = trs[trs.action == "SELL"].groupby("d").amt.sum()
    rows = []
    for k in range(1, len(e)):
        p, c = e.iloc[k - 1], e.iloc[k]
        in_k = lambda s: float(s[(s.index > p.d) & (s.index <= c.d)].sum())  # noqa: E731
        b_amt, s_amt = in_k(buy), in_k(sell)
        cost = -((c.cash - p.cash) - (s_amt - b_amt))
        pnl_pos = c.pv - p.pv + s_amt - b_amt
        w = p.pv / p.E
        m = med[c.d]
        r = c.E / p.E - 1
        rows.append(dict(d=c.d, r=r, m=m, w=w, cost=cost, pnl_pos=pnl_pos, pv_prev=p.pv,
                         dk=pnl_pos / p.E - w * m, ck=(1 - w) * (0 - m), ak=-cost / p.E,
                         dk_orig=(w * (pnl_pos / p.pv - m)) if p.pv > 0 else 0.0))
    x = pd.DataFrame(rows)
    err = (x.r - x.m - (x.dk + x.ck + x.ak)).abs().max()
    E0, EN = float(e.E.iloc[0]), float(e.E.iloc[-1])
    R = EN / E0 - 1
    # Carino 연결: k_t = (ln(1+r) − ln(1+m))/(r − m) · K = 같은 식(기간) · 성분_연결 = Σ (k_t/K)·성분_t
    # Π(1+m_t) = 1+M 일 때 Σ 연결(d+c+a_일별) = R − M 이 정확히 성립(보정안 전용 · 원안 m 에는 성립 안 함).
    lr, lm = (1 + x.r).map(math.log), (1 + x.m).map(math.log)
    k = ((lr - lm) / (x.r - x.m)).where((x.r - x.m).abs() > 1e-12, 1 / (1 + x.r))
    K = (math.log(1 + R) - math.log(1 + M)) / (R - M)
    wt = k / K
    return dict(x=x, err=err, E0=E0, EN=EN, R=R, G=R - M,
                c_link=(wt * x.ck).sum(), d_link=(wt * x.dk).sum(), a_link=(wt * x.ak).sum(),
                link_check=(R - M) - (wt * (x.dk + x.ck + x.ak)).sum(),
                c=x.ck.sum(), d=x.dk.sum(), d_orig=x.dk_orig.sum(),
                a_db=x.ak.sum(), cost_db=x.cost.sum(), sum_r=x.r.sum(), sum_m=x.m.sum(),
                n_flat=int(((x.pv_prev == 0) & (x.pnl_pos.abs() > 0.5)).sum()),
                flat_pnl=float(x.loc[x.pv_prev == 0, "pnl_pos"].sum()), w_mean=x.w.mean(), neg_cost=int((x.cost < -1).sum()))


# ── 반사실 b ─────────────────────────────────────────────────────────────────
def post_sell(cur, sells: pd.DataFrame, cal: list[str]) -> pd.DataFrame:
    """4전략 손절·익절 SELL 만: 매도 뒤 HORIZON 거래일 종가(10-28 에서 자름)."""
    last = len(cal) - 1
    rows = []
    for r in sells.itertuples():
        i = cal.index(r.d)
        tgt = cal[min(i + HORIZON, last)]
        op = ">=" if tgt == r.d else ">"   # 10-28 당일 매도 = 10-28 종가로 자름
        cur.execute(f"""SELECT date, close FROM daily_prices WHERE stock_code=%s AND date{op}%s AND date<=%s
                        ORDER BY date DESC LIMIT 1""", (r.stock_code, r.d, tgt))
        hit = cur.fetchone()
        cur.execute("SELECT close FROM daily_prices WHERE stock_code=%s AND date=%s", (r.stock_code, r.d))
        same = cur.fetchone()
        rows.append(dict(id=r.id, tgt=tgt, cut=i + HORIZON > last, px_date=hit[0] if hit else None,
                         px=float(hit[1]) if hit else None, close_sd=float(same[0]) if same else None))
    return sells.merge(pd.DataFrame(rows), on="id")


# ── 시총 기울기 ───────────────────────────────────────────────────────────────
def mcap_tilt(cur, buys: pd.DataFrame):
    cur.execute("""
        WITH lots AS (SELECT unnest(%s::text[]) AS d, unnest(%s::text[]) AS code, unnest(%s::text[]) AS st),
        u AS (SELECT date, stock_code, percent_rank() OVER (PARTITION BY date ORDER BY market_cap) AS pr
              FROM daily_prices WHERE date = ANY(%s::text[]) AND volume>0 AND market_cap>0 AND stock_code NOT IN %s)
        SELECT lots.st, least(5, floor(u.pr*5)::int + 1) AS qn
        FROM lots LEFT JOIN u ON u.date=lots.d AND u.stock_code=lots.code""",
                (list(buys.d), list(buys.stock_code), list(buys.strategy), sorted(set(buys.d)), PSEUDO))
    lots = pd.DataFrame(cur.fetchall(), columns=["st", "qn"])
    cur.execute("""
        WITH s AS (SELECT stock_code, close, market_cap FROM daily_prices WHERE date=%s AND volume>0 AND stock_code NOT IN %s),
             t AS (SELECT stock_code, close FROM daily_prices WHERE date=%s AND volume>0 AND stock_code NOT IN %s),
             r AS (SELECT stock_code, t.close/s.close-1 AS ret, s.market_cap FROM s JOIN t USING(stock_code) WHERE s.close>0),
             g AS (SELECT ret, CASE WHEN market_cap>0 THEN ntile(5) OVER (PARTITION BY market_cap>0 ORDER BY market_cap, stock_code)
                                END AS qn FROM r)
        SELECT qn, count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY ret) FROM g GROUP BY qn ORDER BY qn""",
                (START, PSEUDO, END, PSEUDO))
    univ = pd.DataFrame(cur.fetchall(), columns=["qn", "n", "med"])
    return lots, univ


def main() -> int:
    conn = psycopg2.connect(**DSN)
    conn.set_session(readonly=True)
    cur = conn.cursor()
    cal, eq8, tr = load(cur)
    eq_dates = sorted(eq8.d.unique())
    missing = [d for d in cal if d not in set(eq_dates)]

    cur.execute(MEDIAN_SQL, (START, PSEUDO, END, PSEUDO))
    M, M_n, M_up = (float(v) for v in cur.fetchone())
    med = interval_medians(cur, eq_dates, cal)
    med_path = path_medians(cur, eq_dates)

    say("# 4분해 — 06-01 이후 4전략이 전 종목 중앙값과 벌어진 몫\n")
    say(f"기간 {START} → {END} · 기준 = {START} equity(E0) · 대상 4전략 = {', '.join(S4)} · "
        "생성 = `python RoboTrader_template/backtest/attribution/attribute.py`\n")

    # ── 대조 ──
    e8 = eq8.groupby("d").E.sum()
    R8 = e8[END] / e8[START] - 1
    say("## 0. 자기 확인(관리자 수치 대조)\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 전 종목 중앙값 {START}→{END} | {M * 100:+.2f}% · {int(M_n):,}종목 · 상승 비율 {M_up * 100:.0f}% |")
    say(f"| 8전략 equity 합 {START} → {END} | {won(e8[START])}원 → {won(e8[END])}원 = **{R8 * 100:+.2f}%** |")
    say(f"| 8전략 포트−중앙값 | {pp(R8 - M)} |")
    e4 = eq8[eq8.strategy.isin(S4)].groupby("d")[["cash", "pv", "E"]].sum().reset_index()
    E40, E4N = float(e4.set_index("d").E[START]), float(e4.set_index("d").E[END])
    say(f"| 4전략 equity 합 {START} → {END} | {won(E40)}원 → {won(E4N)}원 = **{(E4N / E40 - 1) * 100:+.2f}%** |")
    say(f"| 4전략 G(포트−중앙값) | **{pp(E4N / E40 - 1 - M)}** |")
    say(f"| 거래일(KOSPI 행) | {len(cal)}일 · equity 날짜 {len(eq_dates)}일 · 결측 {len(missing)}일 = {', '.join(missing)} |")
    say()

    # ── 비용 실측 ──
    cost_log, multi, gap, n_files, n_logdays, n_lines, n_sells_all = log_costs(cur)
    sells = tr[tr.action == "SELL"].copy()
    sells["cost_log"] = sells.id.map(cost_log)
    sells["cost_assume"] = sells.buy_price * sells.buy_qty * FEE_BUY + sells.amt * FEE_SELL
    sells["measured"] = sells.cost_log.notna()
    sells["cost_used"] = sells.cost_log.where(sells.measured, sells.cost_assume)
    day_state = sells.groupby("d").measured.agg(["all", "any"])
    days_meas = int(day_state["all"].sum())
    days_assume = int((~day_state["any"]).sum())
    days_mixed = int(len(day_state) - days_meas - days_assume)

    # ── 반사실 b ──
    sells["cat"] = sells.reason.fillna("").map(
        lambda s: "손절" if s.startswith("손절") else ("익절" if s.startswith("목표 익절") else "기타"))
    ps = post_sell(cur, sells[sells.cat.isin(["손절", "익절"])][["id", "d", "stock_code", "price", "amt"]], cal)
    ps = ps.merge(sells[["id", "strategy", "cat"]], on="id")
    ps["ret_after"] = ps.px / ps.price - 1
    ps["adj_suspect"] = (ps.close_sd.notna()) & ((ps.price / ps.close_sd - 1).abs() > ADJ_SUSPECT)

    # ── 분해 ──
    res, res2 = {}, {}
    for st in S4:
        res[st] = decompose(eq8[eq8.strategy == st][["d", "cash", "pv", "E"]], tr[tr.strategy == st], med, M)
        res2[st] = decompose(eq8[eq8.strategy == st][["d", "cash", "pv", "E"]], tr[tr.strategy == st], med_path, M)
    res["4전략 합"] = decompose(e4, tr, med, M)
    res2["4전략 합"] = decompose(e4, tr, med_path, M)

    def bsum(st, cat):
        g = ps[(ps.cat == cat) & (ps.strategy.isin(S4 if st == "4전략 합" else [st]))]
        return float((g.ret_after * g.amt).sum()), g

    say("## 1. 한 표 — 원안(브리프 설계 그대로 · m_t = 그날 returns_1d 중앙값)\n")
    say("단위 = E0 대비 %p · 합계 행은 4전략 equity 합으로 다시 계산(평균 아님).\n")
    say("| 전략 | G(포트−중앙값) | a 비용 | c 현금 | d 선택 | 잔차 | b 손절회전(반사실) | 손절 n | 매도 n |")
    say("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    head = {}
    for st, o in res.items():
        sel = sells if st == "4전략 합" else sells[sells.strategy == st]
        a = -float(sel.cost_used.sum()) / o["E0"]
        b_won, _ = bsum(st, "손절")
        b = b_won / o["E0"]
        resid = o["G"] - (a + o["c"] + o["d"])
        head[st] = dict(a=a, b=b, b_won=b_won, resid=resid, sel=sel)
        name = f"**{st}**" if st == "4전략 합" else st
        say(f"| {name} | {pp(o['G'])} | {pp(a)} | {pp(o['c'])} | {pp(o['d'])} | {pp(resid)} | {pp(b)} | "
            f"{int((sel.cat == '손절').sum())} | {len(sel)} |")
    say()
    say(f"- 중앙값 = {M * 100:+.2f}% · G = (E_{END[5:]}/E_{START[5:]} − 1) − 중앙값 · a = −Σ(gross − net)/E0 · "
        "c = Σ(1 − w)(0 − m) · d = Σ(PnL_pos/E_prev − w·m) · 잔차 = G − (a + c + d) · b 는 항등식 밖.")
    say()

    say("## 1-B. 한 표 — 보정안(m_t = «기간 중앙값 경로»의 하루 변화 · Carino 연결)\n")
    say(f"원안 잔차가 큰 이유 = 일별 중앙값의 합 Σm({res['4전략 합']['sum_m'] * 100:+.2f}%)이 기간 중앙값"
        f"({M * 100:+.2f}%)과 다르기 때문(§2). 보정안은 m_t 를 «06-01 이후 누적 수익률의 전 종목 중앙값» I_t 의 하루 변화"
        "((1+I_t)/(1+I_{t−1}) − 1)로 바꿔 Π(1+m_t) = 1 + 기간 중앙값 이 정확히 맞게 하고, 일별 성분을 Carino 계수로 "
        "연결해 복리 차이를 없앴다. a 는 원안과 같은 값(로그 net · E0 기준)을 쓰고, 남는 잔차 = «연결된 일별 a(DB 현금·E_prev "
        "기준) − a» 하나뿐이다.\n")
    say("| 전략 | G(포트−중앙값) | a 비용 | c 현금 | d 선택 | 잔차 | b 손절회전(반사실) | 손절 n | 매도 n |")
    say("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for st, o in res2.items():
        h = head[st]
        resid2 = o["G"] - (h["a"] + o["c_link"] + o["d_link"])
        h["resid2"] = resid2
        name = f"**{st}**" if st == "4전략 합" else st
        say(f"| {name} | {pp(o['G'])} | {pp(h['a'])} | {pp(o['c_link'])} | {pp(o['d_link'])} | {pp(resid2)} | "
            f"{pp(h['b'])} | {int((h['sel'].cat == '손절').sum())} | {len(h['sel'])} |")
    say()
    say("- 보정안 잔차 = 연결 a_일별 − a: "
        + " · ".join(f"{st} {pp(o['a_link'] - head[st]['a'])}" for st, o in res2.items())
        + " · 연결 항등식 오차(G − Σ연결(d+c+a_일별)): "
        + " · ".join(f"{st} {o['link_check']:.1e}" for st, o in res2.items()))
    say(f"- 보정안 Σm(경로 일별 합) = {res2['4전략 합']['sum_m'] * 100:+.2f}% · Π(1+m) − 1 = "
        f"{(res2['4전략 합']['x'].m.add(1).prod() - 1) * 100:+.2f}%(= 기간 중앙값)")
    say()

    say("### 1-1. 원 환산(성분 × E0 · 원 단위 정수) — 원안\n")
    say("| 전략 | E0 | E_10-28 | 포트 손익 | G | a 비용 | c 현금 | d 선택 | 잔차 | b 손절회전 |")
    say("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for st, o in res.items():
        h, E0 = head[st], o["E0"]
        say(f"| {st} | {won(E0)} | {won(o['EN'])} | {won(o['EN'] - E0)} | {won(o['G'] * E0)} | {won(h['a'] * E0)} | "
            f"{won(o['c'] * E0)} | {won(o['d'] * E0)} | {won(h['resid'] * E0)} | {won(h['b_won'])} |")
    say()
    say("### 1-2. 원 환산 — 보정안\n")
    say("| 전략 | G | a 비용 | c 현금 | d 선택 | 잔차 |")
    say("|---|---:|---:|---:|---:|---:|")
    for st, o in res2.items():
        h, E0 = head[st], o["E0"]
        say(f"| {st} | {won(o['G'] * E0)} | {won(h['a'] * E0)} | {won(o['c_link'] * E0)} | {won(o['d_link'] * E0)} | "
            f"{won(h['resid2'] * E0)} |")
    say()

    say("## 2. 원안 잔차 분해 (잔차 = 복리 + 중앙값 합산 차 + 비용 기준 차 · 정확히 합해짐)\n")
    say("| 전략 | 잔차 | 복리 (R − Σr) | 중앙값 합산 차 (Σm − 기간 중앙값) | 비용 기준 차 (Σa_일별 − a) | Σm(일별 중앙값 합) | 평균 투자비중 w |")
    say("|---|---:|---:|---:|---:|---:|---:|")
    for st, o in res.items():
        h = head[st]
        p1, p2, p3 = o["R"] - o["sum_r"], o["sum_m"] - M, o["a_db"] - h["a"]
        say(f"| {st} | {pp(h['resid'])} | {pp(p1)} | {pp(p2)} | {pp(p3)} | {o['sum_m'] * 100:+.2f}% | "
            f"{o['w_mean'] * 100:.2f}% |")
    say()
    say("- 일별 항등식 `r − m = d + c + a_일별` 최대 오차: "
        + " · ".join(f"{st} {o['err']:.1e}" for st, o in res.items()))
    say("- 현금 대조: 구간마다 `cost = −(Δcash − (매도액 − 매수액))` 가 음수(현금 유입)인 구간 수 = "
        + " · ".join(f"{st} {o['neg_cost']}" for st, o in res.items()) + "(0 이면 자금 주입·회수 없음)")
    say()

    say("## 3. 비용 a — 실측(로그 net) · 가정 · DB 현금 잔차 대조\n")
    say(f"로그 = `{LOG_DIR.as_posix()}/robotrader_template_YYYYMMDD_*.log` {n_files}파일 · "
        f"net 줄이 있는 날 {n_logdays}일 · net 줄 {n_lines}개 vs 같은 기간 DB SELL(8전략) {n_sells_all}건 · "
        f"짝 = 그날 SELL 시각 ±{PAIR_SEC}초 안의 안 쓴 net 줄(여럿이면 gross − net 이 0.21%×매도금액에 가장 가까운 줄).\n")
    say("| 전략 | 매도 n | 실측 SELL | 가정 SELL | 실측 비용(원) | 가정 비용(원) | a(원안 · 로그+가정) | "
        "DB 현금 잔차 비용(원) | a′(DB · E0 기준) |")
    say("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for st, o in res.items():
        sel = head[st]["sel"]
        meas = sel[sel.measured]
        asm = sel[~sel.measured]
        say(f"| {st} | {len(sel)} | {len(meas)} | {len(asm)} | {won(meas.cost_log.sum())} | "
            f"{won(asm.cost_assume.sum())} | {pp(head[st]['a'])} | {won(o['cost_db'])} | {pp(-o['cost_db'] / o['E0'])} |")
    say()
    say(f"- 4전략 SELL 이 있는 날 {len(day_state)}일 중 **실측 {days_meas}일 · 가정 {days_assume}일 · 섞임 {days_mixed}일**"
        f"(가정 = 로그 짝 없음 → 수수료 {FEE_BUY * 100:.3f}%×매수액 + {FEE_SELL * 100:.3f}%×매도액).")
    if len(sells[~sells.measured]):
        say("- 가정 SELL 날짜: " + ", ".join(sorted(sells[~sells.measured].d.unique())))
    m_ = sells[sells.measured]
    say(f"- 실측 SELL {len(m_)}건의 (gross − net) vs 가정식 차이 합 = {won((m_.cost_log - m_.cost_assume).sum())}원 · "
        f"건당 최대 |차| = {won((m_.cost_log - m_.cost_assume).abs().max() if len(m_) else 0)}원 · "
        f"후보 net 줄이 2개 이상이던 SELL {int(sells.id.isin(multi).sum())}건 · 짝 시각 차 최대 "
        f"{max((gap[i] for i in m_.id), default=0):.0f}초")
    one = m_[~m_.id.isin(multi)]
    say(f"- 후보가 1개뿐이라 시각만으로 짝지어진 SELL {len(one)}건의 |gross − net − 가정식| 최대 = "
        f"{won((one.cost_log - one.cost_assume).abs().max() if len(one) else 0)}원(가정식을 짝 고르기에 안 쓴 건만의 대조).")
    say("- 🔑 페이퍼의 net 은 엔진이 «수수료 0.015%×2 + 거래세 0.18%» 식으로 빼 준 값이라, 여기서 «실측»은 "
        "엔진이 실제로 뺀 비용을 확인한 것이지 증권사 실제 비용이 아니다.")
    say("- DB 현금 잔차 비용 = equity 표 cash 변화에서 거래 금액을 뺀 값(매수 수수료 포함 · 기간 끝 미청산 로트의 매수 "
        "수수료까지 들어감). 원안 a 와의 차이는 §2 «비용 기준 차»에 들어간다.")
    say()

    say("## 4. d 선택 — 방법 메모\n")
    say("| 전략 | d(채택 · PnL_pos/E_prev − w·m) | d(브리프 원식 · w·(r_pos − m) · pv_prev>0 구간만) | 차이 | "
        "pv_prev=0 인데 포지션 손익 ≠0 구간 수 | 그 구간 포지션 손익 합(원) |")
    say("|---|---:|---:|---:|---:|---:|")
    for st, o in res.items():
        say(f"| {st} | {pp(o['d'])} | {pp(o['d_orig'])} | {pp(o['d'] - o['d_orig'])} | {o['n_flat']} | "
            f"{won(o['flat_pnl'])} |")
    say()
    say("- 방법 = 일별(구간별) 포트 방식. 로트 단위 대체는 쓰지 않았다. r_pos 는 브리프 식(pv 변화 + 매도 gross 회수액 − "
        "매수 지출액)을 그대로 쓰되, 전날 보유가 0 이고 그날 사고 판(또는 산) 손익은 w=0 이라 원식에서 빠지므로 "
        "PnL_pos/E_prev 로 d 에 넣었다(빠지면 잔차로 간다).")
    say(f"- 결측 equity 날짜({', '.join(missing)})는 앞뒤 equity 날짜를 한 구간으로 묶었다 — 그 구간 m = 양끝 "
        "volume>0 종목의 `close_t/close_s − 1` 중앙값(기간 중앙값과 같은 정의) · 그 구간 거래 0건.")
    say()

    say(f"## 5. 반사실 b — 손절 뒤 {HORIZON}거래일 (대조 = 익절 뒤)\n")
    say("| 전략 | 구분 | n | 10-28 에서 잘림 | 종가 대체(목표일 행 없음) | 종가 없음 | 매도 뒤 수익률 중앙 | 매도 뒤 수익률 평균 | "
        "매도금액 합(원) | 매도금액 합÷E0 | 합(원) | E0 대비 | 매도가−당일종가 괴리>30% n | 그 n 뺀 E0 대비 |")
    say("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for st, o in res.items():
        for cat in ("손절", "익절"):
            s_won, g = bsum(st, cat)
            ok = g[g.px.notna()]
            sub = (g.px_date.notna()) & (g.px_date != g.tgt)
            nadj = g[g.adj_suspect & g.px.notna()]
            ex = float((ok[~ok.adj_suspect].ret_after * ok[~ok.adj_suspect].amt).sum())
            say(f"| {st} | {cat} | {len(g)} | {int(g.cut.sum())} | {int(sub.sum())} | {int(g.px.isna().sum())} | "
                f"{(ok.ret_after.median() * 100 if len(ok) else 0):+.2f}% | {(ok.ret_after.mean() * 100 if len(ok) else 0):+.2f}% | "
                f"{won(g.amt.sum())} | {g.amt.sum() / o['E0']:.2f}배 | {won(s_won)} | {pp(s_won / o['E0'])} | {len(nadj)} | {pp(ex / o['E0'])} |")
    say()
    say(f"- 식 = Σ(매도 뒤 {HORIZON}거래일 종가 / 매도가 − 1) × 매도금액 / E0. + 면 그 {HORIZON}거래일 동안 들고 있었으면 "
        "평가액이 더 컸다는 뜻(비용·재매수 기회비용은 안 셈). 가격 조회는 위 4전략 SELL 만.")
    say(f"- 목표일 = 거래일 달력(KOSPI 행)에서 매도일 + {HORIZON} · {END} 를 넘으면 {END} 로 자름. 목표일에 그 종목 행이 "
        "없으면 매도일 다음 ~ 목표일 사이 마지막 종가.")
    say()

    say("## 6. 덤 — 시총 기울기\n")
    buys = tr[tr.action == "BUY"][["d", "stock_code", "strategy"]]
    lots, univ = mcap_tilt(cur, buys)
    say("매수 로트의 매수일 시총 5분위(그날 전 종목 · volume>0 · 의사티커 제외 · Q1 = 작음). 전 종목 분포는 정의상 각 20%.\n")
    say("| 전략 | 로트 | Q1 | Q2 | Q3 | Q4 | Q5 | 시총 없음 |")
    say("|---|---:|---:|---:|---:|---:|---:|---:|")
    for st in list(S4) + ["4전략 합"]:
        g = lots if st == "4전략 합" else lots[lots.st == st]
        n = len(g)
        cells = " | ".join(f"{(g.qn == k).sum() / n * 100:.0f}%" for k in range(1, 6))
        say(f"| {st} | {n} | {cells} | {int(g.qn.isna().sum())} |")
    say()
    say(f"전 종목 {START}→{END} 수익률 중앙값을 {START} 시총 5분위별로:\n")
    say("| 분위 | 종목 | 중앙값 |")
    say("|---|---:|---:|")
    for r in univ.itertuples():
        lab = "시총 없음" if pd.isna(r.qn) else f"Q{int(r.qn)}"
        say(f"| {lab} | {int(r.n):,} | {float(r.med) * 100:+.2f}% |")
    say()
    say("- 시총 = `daily_prices.market_cap`(날짜별 값 · 스냅샷 아님). 매수일 시총은 그날 종가 기준이다.")
    say()

    say("## 7. 데이터 처리 메모\n")
    say(f"- equity 결측 {len(missing)}일 = {', '.join(missing)} — 그날 4전략 거래 0건 · 로그 net 줄 0 · §4 처럼 한 구간으로 묶음.")
    say(f"- 비용: 4전략 SELL 이 있는 날 실측 {days_meas}일 / 가정 {days_assume}일 / 섞임 {days_mixed}일.")
    say("- 가격에 adj_factor 를 곱하지 않았다. 중앙값 정의 = 라이브 트리 `scratchpad/eod_20261029/eq_median.py` 와 같음.")
    say("- SR1 봉인 4전략: equity 합(대조)과 로그 net 짝 맞추기용 SELL 시각·gross 만 읽었다 — 매도 뒤 가격 조회 0.")
    conn.close()

    (BASE / "RESULTS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] RESULTS.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
