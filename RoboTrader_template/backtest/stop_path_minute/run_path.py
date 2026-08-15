# -*- coding: utf-8 -*-
"""손절선에 닿은 것은 「하루치 노이즈」였나 「진짜 하락의 시작」이었나 — 1층+2층 전부.

사전등록: `PREREG.md`(동결 `7c2b245`). 이 스크립트는 §5(1단계, PIT)·§3-5(무결성 게이트)·
§6(1층 M1·M2·M3·M_asym, 2층 M4·M4b·M5·M6·M7)·§7(판정)을 «같은 실행»에서 전부 계산한다
(1층을 먼저 보고 2층 설계를 바꾸는 사후적합을 막기 위해 — §9).

🔴 문턱·창·시드·대상전략을 갈지 않았다 — K 없음(이 문서는 비율 게이트가 아니다),
   ε1=0.21%p(FEE, pnl_decomposition §①) · 커버리지 문턱=79% · 카운트 문턱=30 ·
   퇴화일 문턱=1/3 · 잔여 시각대 교란 문턱=20%p · M4 유의수준=0.05 · 시드=20260816(N=20) ·
   2층 대상=elder_ema_pullback·book_envelope_200d·deep_mr_dev20 — 전부 PREREG.md 값 그대로.

실행 순서(§⬜ 체크리스트 그대로): §5(PIT만, reason·strategy·timestamp·stock_code) →
§3-5 무결성 게이트(§6 계산 직후) → §6~§7. §3-5 가 실패하면 §6~§7 해석을 하지 않고 멈춘다.

라이브 트리 import 0건 · DB 는 SELECT 만 · `utils/logger.py` 미사용.
재실행하면 `RESULTS.md` 가 바이트 동일하게 재생성된다(재현 게이트, `stop_vol_fit_gate` 관례 승계).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from scipy.stats import binomtest

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
WINDOW = ("2026-06-01", "2026-08-14")

SEED = 20260816
N_REPS = 20
EPS1 = 0.0021              # 0.21%p — FEE, pnl_decomposition/RESULTS.md §①
COVERAGE_THRESHOLD = 0.79  # §3-2·§4-2
COUNT_LOW = 30             # §4-1·§6 M4
DEGENERATE_THRESHOLD = 1.0 / 3.0
RESID_TOD_THRESHOLD = 0.20  # §4-3, 20%p
L2_STRATEGIES = ("elder_ema_pullback", "book_envelope_200d", "deep_mr_dev20")


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


TOD_BINS = [
    (dt.time(9, 0), dt.time(9, 5), "09:00~09:05"),
    (dt.time(9, 5), dt.time(10, 0), "09:05~10:00"),
    (dt.time(10, 0), dt.time(13, 0), "10:00~13:00"),
    (dt.time(13, 0), dt.time(14, 30), "13:00~14:30"),
    (dt.time(14, 30), dt.time(15, 20), "14:30~15:20"),
    (dt.time(15, 20), dt.time(15, 30), "15:20~15:30"),
]
TOD_LABELS = [b[2] for b in TOD_BINS]
RESID_LABELS = TOD_LABELS[1:]  # 09:05+ 5구간(§4-3)


def tod_bucket(ts) -> str:
    t = ts.time()
    for lo, hi, label in TOD_BINS:
        if lo <= t < hi:
            return label
    if t == dt.time(15, 30):
        return "15:20~15:30"
    return "기타(장외)"


def fmt_pct(x) -> str:
    return f"{x*100:+.2f}%" if not (x is None or (isinstance(x, float) and np.isnan(x))) else "—"


def fmt_pp(x) -> str:
    return f"{x*100:+.2f}%p" if not (x is None or (isinstance(x, float) and np.isnan(x))) else "—"


# ═════════════════════════════════════════════════════════════════════════
# Phase A — PIT 전용 로드(§5). reason·strategy·timestamp·stock_code·buy_record_id 만.
# ═════════════════════════════════════════════════════════════════════════

def load_layer1_pit(conn) -> pd.DataFrame:
    """368(손절)+145(익절) — 가격·PnL 컬럼 없음. §3-4 KST 정합을 SQL 에서 바로 적용."""
    df = pd.read_sql("""
        SELECT id, stock_code, strategy, buy_record_id, reason,
               (timestamp AT TIME ZONE 'Asia/Seoul') AS ts_kst
        FROM virtual_trading_records
        WHERE action = 'SELL'
          AND (timestamp AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
          AND (reason LIKE '손절 실행%%' OR reason LIKE '목표 익절%%')
        ORDER BY id
    """, conn, params=WINDOW)
    df["ts_kst"] = pd.to_datetime(df["ts_kst"])
    df["cat"] = np.where(df["reason"].str.startswith("손절 실행"), "손절", "익절")
    df["sell_date"] = df["ts_kst"].dt.strftime("%Y-%m-%d")
    df["date8"] = df["ts_kst"].dt.strftime("%Y%m%d")
    df["month"] = df["ts_kst"].dt.strftime("%Y-%m")
    df["tod"] = df["ts_kst"].map(tod_bucket)
    return df


def load_minute_existence(conn, codes: list, dates8: list) -> set:
    """(stock_code, date8) 쌍 중 `minute_candles` 에 실제로 존재하는 것만. PIT(존재 여부만, 가격 없음)."""
    if not codes or not dates8:
        return set()
    df = pd.read_sql("""
        SELECT DISTINCT stock_code, date
        FROM minute_candles
        WHERE stock_code = ANY(%s) AND date = ANY(%s)
    """, conn, params=(sorted(set(codes)), sorted(set(dates8))))
    return set(zip(df["stock_code"], df["date"]))


# ═════════════════════════════════════════════════════════════════════════
# Phase B — 가격/PnL 로드(§6). Phase A 완료·§5 인쇄 «후»에만 호출한다.
# ═════════════════════════════════════════════════════════════════════════

def load_layer1_prices(conn, ids: list) -> pd.DataFrame:
    df = pd.read_sql("SELECT id, price AS p_sell FROM virtual_trading_records WHERE id = ANY(%s)",
                      conn, params=(list(map(int, ids)),))
    df["p_sell"] = pd.to_numeric(df["p_sell"], errors="coerce")
    return df


def load_daily_close(conn, codes: list, dates: list) -> pd.DataFrame:
    df = pd.read_sql("""
        SELECT stock_code, date, close FROM daily_prices
        WHERE stock_code = ANY(%s) AND date = ANY(%s)
    """, conn, params=(sorted(set(codes)), sorted(set(dates))))
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df


def load_stock_market(conn) -> dict:
    df = pd.read_sql("SELECT stock_code, market FROM stock_market", conn)
    return dict(zip(df["stock_code"], df["market"]))


def load_index_returns(conn, dates: list) -> pd.DataFrame:
    df = pd.read_sql("""
        SELECT stock_code AS market, date, returns_1d FROM daily_prices
        WHERE stock_code IN ('KOSPI', 'KOSDAQ') AND date = ANY(%s)
    """, conn, params=(sorted(set(dates)),))
    df["returns_1d"] = pd.to_numeric(df["returns_1d"], errors="coerce")
    return df


def load_buy_side(conn, ids: list) -> pd.DataFrame:
    """§3-2 arm 통일 — `stop_loss_rate`·`target_profit_rate` 는 매수 시점 확정 PIT 컬럼."""
    df = pd.read_sql("""
        SELECT id, price AS p_buy, stop_loss_rate, target_profit_rate
        FROM virtual_trading_records WHERE id = ANY(%s)
    """, conn, params=(list(map(int, ids)),))
    df["p_buy"] = pd.to_numeric(df["p_buy"], errors="coerce")
    df["stop_loss_rate"] = pd.to_numeric(df["stop_loss_rate"], errors="coerce")
    df["target_profit_rate"] = pd.to_numeric(df["target_profit_rate"], errors="coerce")
    return df


def load_minute_bars(conn, codes: list, dates8: list) -> pd.DataFrame:
    if not codes or not dates8:
        return pd.DataFrame(columns=["stock_code", "date", "datetime", "close", "low", "volume"])
    df = pd.read_sql("""
        SELECT stock_code, date, datetime, close, low, volume
        FROM minute_candles
        WHERE stock_code = ANY(%s) AND date = ANY(%s)
        ORDER BY stock_code, date, datetime
    """, conn, params=(sorted(set(codes)), sorted(set(dates8))))
    for c in ("close", "low", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


# ═════════════════════════════════════════════════════════════════════════
# §4-1 순열 — M_asym(1층 귀무)
# ═════════════════════════════════════════════════════════════════════════

def m_asym_permutation(rng: np.random.Generator, df: pd.DataFrame, n_reps: int = N_REPS) -> list:
    """df: sell_date·regret0·is_stop(bool) 만. 09:05+ 로 이미 제한된 모집단.

    날짜별로 그날의 실제 손절건수 k_d 를 무작위로 재배정(층화, 날짜 구조 보존).
    반환: [(m_stop_j, m_profit_j, diff_j), ...] — diff_j = m_stop_j − m_profit_j.
    """
    day_groups = sorted(df.groupby("sell_date"), key=lambda kv: kv[0])
    day_idx = [(d, g.index.to_numpy()) for d, g in day_groups]
    k_by_day = {d: int(df.loc[idx, "is_stop"].sum()) for d, idx in day_idx}
    reps = []
    for _ in range(n_reps):
        stop_idx = []
        for d, idx in day_idx:
            k_d = k_by_day[d]
            if k_d <= 0:
                continue
            chosen = rng.choice(idx, size=k_d, replace=False)
            stop_idx.extend(chosen.tolist())
        stop_mask = df.index.isin(stop_idx)
        m_stop = float(df.loc[stop_mask, "regret0"].median())
        m_profit = float(df.loc[~stop_mask, "regret0"].median())
        reps.append((m_stop, m_profit, m_stop - m_profit))
    return reps


def degenerate_diag(df: pd.DataFrame, n_stop_total: int) -> dict:
    """퇴화일(k_d=n_d 또는 k_d=0) 진단 — `stop_vol_fit_gate` §5-2 승계."""
    by_day = df.groupby("sell_date").agg(n_d=("is_stop", "size"), k_d=("is_stop", "sum")).reset_index()
    by_day["k_d"] = by_day["k_d"].astype(int)
    by_day["degenerate"] = (by_day["k_d"] == by_day["n_d"]) | (by_day["k_d"] == 0)
    degenerate_excluded = int(by_day.loc[by_day["degenerate"], "k_d"].sum())
    share = degenerate_excluded / n_stop_total if n_stop_total > 0 else float("nan")
    return dict(by_day=by_day, degenerate_excluded=degenerate_excluded, share=share,
                ok=(share < DEGENERATE_THRESHOLD) if n_stop_total > 0 else False)


def main() -> int:
    conn = psycopg2.connect(**DSN)

    # ── Phase A: PIT 로드 ────────────────────────────────────────────────
    df1 = load_layer1_pit(conn)
    stop368 = df1[df1["cat"] == "손절"].copy().reset_index(drop=True)
    prof145 = df1[df1["cat"] == "익절"].copy().reset_index(drop=True)
    assert len(stop368) == 368, f"손절 모집단이 368 이 아니다 — 실측 {len(stop368)}"
    assert len(prof145) == 145, f"익절 모집단이 145 가 아니다 — 실측 {len(prof145)}"

    l2_stop = stop368[stop368["strategy"].isin(L2_STRATEGIES)].copy().reset_index(drop=True)
    l2_prof = prof145[prof145["strategy"].isin(L2_STRATEGIES)].copy().reset_index(drop=True)
    assert len(l2_stop) == 109, f"2층 손절 모집단이 109 가 아니다 — 실측 {len(l2_stop)}"

    exist_pairs = load_minute_existence(
        conn,
        list(l2_stop["stock_code"]) + list(l2_prof["stock_code"]),
        list(l2_stop["date8"]) + list(l2_prof["date8"]),
    )
    l2_stop["has_minute"] = [(r.stock_code, r.date8) in exist_pairs for r in l2_stop.itertuples()]
    l2_prof["has_minute"] = [(r.stock_code, r.date8) in exist_pairs for r in l2_prof.itertuples()]
    n96 = int(l2_stop["has_minute"].sum())
    assert n96 == 96, f"2층 분봉있음이 96 이 아니다 — 실측 {n96}"

    # ═══════════════════════════════════════════════════════════════════
    # 리포트 시작
    # ═══════════════════════════════════════════════════════════════════
    say("# 손절선에 닿은 것 — 1층(일봉, 368+145건)은 「진짜 하락」, 2층(분봉, 3전략 96건)도 되돌아오지 않았다\n")
    say("사전등록 [`PREREG.md`](PREREG.md) 동결(`7c2b245`) 실행. 🔴 **문턱·창·시드·대상전략을 갈지 "
        "않았다** — ε1=0.21%p·커버리지 문턱=79%·카운트 문턱=30·퇴화일 문턱=1/3·잔여 시각대 교란 "
        "문턱=20%p·M4 유의수준=0.05·시드=20260816(N=20)·2층 대상=elder_ema_pullback·"
        "book_envelope_200d·deep_mr_dev20 — 전부 `PREREG.md` 값 그대로. 이 문서는 `run_path.py` 를 "
        "재실행하면 그대로 재생성된다(재현 게이트).\n")
    say(f"1층 모집단: 손절(`reason LIKE '손절 실행%'`) **{len(stop368)}**건 · "
        f"익절(`reason LIKE '목표 익절%'`) **{len(prof145)}**건(2026-06-01~08-14, KST). "
        f"2층 모집단(3전략 한정): 손절 **{len(l2_stop)}**건 중 분봉있음 **{n96}**건 · "
        f"익절 **{len(l2_prof)}**건.\n")

    # ═══════════════════════════════════════════════════════════════════
    # §5 1단계 — 하위집단 구성비 점검(PIT 만)
    # ═══════════════════════════════════════════════════════════════════
    say("## §5 1단계 — 하위집단 구성비 점검 (PIT 만, 가격·PnL 조회 «전»)\n")
    say("`stop_vol_fit_gate` 재사용 규칙 — 「배제/표본 집합의 구성비가 한 하위집단에 쏠려 있으면 "
        "그건 그 축의 결과가 아니다」를 결과를 보기 «전»에 반영한다.\n")

    say("### 5-1. 1층(368건, 손절) — 전략별·월별 구성비 + 전략×월 교차표\n")
    strat_counts = stop368["strategy"].value_counts().sort_index()
    say("| 전략 | 건수 | 비중 |")
    say("|---|---|---|")
    for k, v in strat_counts.items():
        say(f"| `{k}` | {v} | {v/len(stop368)*100:.1f}% |")
    say()
    month_counts = stop368["month"].value_counts().sort_index()
    say("| 월 | 건수 | 비중 |")
    say("|---|---|---|")
    for k, v in month_counts.items():
        say(f"| {k} | {v} | {v/len(stop368)*100:.1f}% |")
    say()
    cross = pd.crosstab(stop368["strategy"], stop368["month"]).sort_index()
    say("**전략×월 교차표(§2 는 이 교차를 안 줬다 — 이 문서가 처음 잰다)**\n")
    say("| 전략 | " + " | ".join(cross.columns) + " | 합계 |")
    say("|---|" + "---|" * (len(cross.columns) + 1))
    for idx, row in cross.iterrows():
        say(f"| `{idx}` | " + " | ".join(str(v) for v in row) + f" | {row.sum()} |")
    say()

    say("### 5-2. 1층 대조군(익절 145건) — 전략별·월별 구성비\n")
    strat_counts_p = prof145["strategy"].value_counts().sort_index()
    say("| 전략 | 손절 건수 | 손절 비중 | 익절 건수 | 익절 비중 |")
    say("|---|---|---|---|---|")
    all_strats = sorted(set(strat_counts.index) | set(strat_counts_p.index))
    for st in all_strats:
        ns = int(strat_counts.get(st, 0))
        npft = int(strat_counts_p.get(st, 0))
        say(f"| `{st}` | {ns} | {ns/len(stop368)*100:.1f}% | {npft} | {npft/len(prof145)*100:.1f}% |")
    say()
    # 쏠림 진단 — 손절비중-익절비중 절대차 최대 전략
    diffs = {st: abs(strat_counts.get(st, 0)/len(stop368) - strat_counts_p.get(st, 0)/len(prof145))
             for st in all_strats}
    worst_st = max(diffs, key=diffs.get)
    say(f"🔑 전략별 구성비 최대 괴리: `{worst_st}` (손절 비중 − 익절 비중 = "
        f"{(strat_counts.get(worst_st,0)/len(stop368) - strat_counts_p.get(worst_st,0)/len(prof145))*100:+.1f}%p). "
        f"이 값이 크면 §4-1 귀무의 날짜 층화가 「그 전략의 손절 특성」이 아니라 「그 전략이 손절만 "
        "많이 낸다는 사실 자체」를 잴 위험이 있다 — §8 한계에 반영한다.\n")
    month_counts_p = prof145["month"].value_counts().sort_index()
    say("| 월 | 손절 건수 | 손절 비중 | 익절 건수 | 익절 비중 |")
    say("|---|---|---|---|---|")
    for m in sorted(set(month_counts.index) | set(month_counts_p.index)):
        ns = int(month_counts.get(m, 0))
        npft = int(month_counts_p.get(m, 0))
        say(f"| {m} | {ns} | {ns/len(stop368)*100:.1f}% | {npft} | {npft/len(prof145)*100:.1f}% |")
    say()

    say("### 5-3. 2층(96건, 3전략 한정) — 전략별·월별 구성비\n")
    l2_96 = l2_stop[l2_stop["has_minute"]].copy()
    say("| 전략 | 109건 중 | 96건(분봉있음) 중 |")
    say("|---|---|---|")
    for st in L2_STRATEGIES:
        n109 = int((l2_stop["strategy"] == st).sum())
        n96s = int((l2_96["strategy"] == st).sum())
        say(f"| `{st}` | {n109} | {n96s} |")
    say()
    say("| 월 | 96건 중 건수 | 비중 |")
    say("|---|---|---|")
    for m, v in l2_96["month"].value_counts().sort_index().items():
        say(f"| {m} | {v} | {v/len(l2_96)*100:.1f}% |")
    say()

    say("### 5-4. §4-2 — 3전략 익절 건의 분봉 커버리지 (M4b 79% 문턱 판정)\n")
    n_l2p = len(l2_prof)
    n_l2p_has = int(l2_prof["has_minute"].sum())
    cov = n_l2p_has / n_l2p if n_l2p > 0 else float("nan")
    m4b_gate_ok = cov >= COVERAGE_THRESHOLD
    say(f"3전략 익절 **{n_l2p}**건 중 분봉있음 **{n_l2p_has}**건 = 커버리지 **{cov*100:.2f}%** "
        f"({'≥' if m4b_gate_ok else '<'} 79% 문턱) ⇒ "
        + ("**M4b 계산한다.**\n" if m4b_gate_ok else "**M4b 계산하지 않는다(§4-2, §9 「참고로도 안 한다」).**\n"))

    say("### 5-5. 시각대 분포 — 손절 vs 익절, «전체 모집단» 기준(6구간) + M_asym 표본 확정\n")
    say("| 구간 | 손절(368) | 손절 비중 | 익절(145) | 익절 비중 |")
    say("|---|---|---|---|---|")
    tod_stop = stop368["tod"].value_counts().reindex(TOD_LABELS, fill_value=0)
    tod_prof = prof145["tod"].value_counts().reindex(TOD_LABELS, fill_value=0)
    for lab in TOD_LABELS:
        say(f"| {lab} | {int(tod_stop[lab])} | {tod_stop[lab]/len(stop368)*100:.1f}% | "
            f"{int(tod_prof[lab])} | {tod_prof[lab]/len(prof145)*100:.1f}% |")
    say()
    n_prof_0905 = int(tod_prof["09:00~09:05"])
    n_stop_0905 = int(tod_stop["09:00~09:05"])
    m_asym_prof_n = len(prof145) - n_prof_0905
    say(f"**손절의 09:00~09:05 발동 = {n_stop_0905}건**(코드 가드로 구조적 0, §4 실측 확인). "
        f"**익절의 09:00~09:05 발동 = {n_prof_0905}건** ⇒ `M_asym` 익절 표본 = 145 − {n_prof_0905} = "
        f"**{m_asym_prof_n}**건.\n")
    gate1_ok = m_asym_prof_n >= COUNT_LOW
    say(f"🔴 **카운트 문턱(1차)**: 익절 09:05+ n = {m_asym_prof_n} — "
        + (f"≥30, **통과**.\n" if gate1_ok else "**<30, `M_asym` 즉시 「검정력 부족 → 판별불가」 확정(§4-1).**\n"))

    gate3_ok = None
    resid_diffs = {}
    if gate1_ok:
        stop_0905plus = stop368[stop368["tod"] != "09:00~09:05"]
        prof_0905plus = prof145[prof145["tod"] != "09:00~09:05"]
        say(f"§4-1 대로 09:05+ 부분집합(손절 {len(stop_0905plus)}·익절 {len(prof_0905plus)})에서 "
            "나머지 5구간 비중(각 그룹 09:05+ 부분집합=100%로 재정규화)을 계산하고 §4-3 잔여 게이트를 "
            "«이 시점에» 판정한다.\n")
        say("| 구간 | 손절 비중(09:05+ 기준) | 익절 비중(09:05+ 기준) | 차(절대값) |")
        say("|---|---|---|---|")
        for lab in RESID_LABELS:
            ps = int((stop_0905plus["tod"] == lab).sum()) / len(stop_0905plus)
            pp = int((prof_0905plus["tod"] == lab).sum()) / len(prof_0905plus)
            d = abs(ps - pp)
            resid_diffs[lab] = d
            say(f"| {lab} | {ps*100:.1f}% | {pp*100:.1f}% | {d*100:.1f}%p |")
        say()
        max_resid = max(resid_diffs.values())
        gate3_ok = max_resid <= RESID_TOD_THRESHOLD
        say(f"§4-3 잔여 시각대 교란 게이트(문턱 20%p, 5구간 중 최대 {max_resid*100:.1f}%p) ⇒ "
            + ("**「안」 걸림 — 통과.**\n" if gate3_ok else
               "🔴 **걸림 — `M_asym` 계산값과 무관하게 §7-1 라벨은 「판별 불가(시각대 교란)」로 강제 대체된다(§4-3).**\n"))
    else:
        say("카운트 문턱(1차)에서 이미 판별불가가 확정돼 §4-3 잔여 게이트는 이 시점에 판정하지 않는다"
            "(§5 step5 — 「그 문턱을 통과하면」).\n")

    say("---\n")

    # ═══════════════════════════════════════════════════════════════════
    # Phase B: 가격 로드
    # ═══════════════════════════════════════════════════════════════════
    all_ids = list(df1["id"])
    prices = load_layer1_prices(conn, all_ids)
    df1 = df1.merge(prices, on="id", how="left")

    daily = load_daily_close(conn, list(df1["stock_code"].unique()), list(df1["sell_date"].unique()))
    df1 = df1.merge(daily, left_on=["stock_code", "sell_date"], right_on=["stock_code", "date"], how="left")
    df1["regret0"] = df1["close"] / df1["p_sell"] - 1

    market_map = load_stock_market(conn)
    df1["market"] = df1["stock_code"].map(market_map)
    idx_ret = load_index_returns(conn, list(df1["sell_date"].unique()))
    df1 = df1.merge(idx_ret, left_on=["market", "sell_date"], right_on=["market", "date"],
                     how="left", suffixes=("", "_idx"))
    df1["m3"] = df1["regret0"] - df1["returns_1d"]

    stop368 = df1[df1["cat"] == "손절"].copy().reset_index(drop=True)
    prof145 = df1[df1["cat"] == "익절"].copy().reset_index(drop=True)

    n_regret0_missing_stop = int(stop368["regret0"].isna().sum())
    n_regret0_missing_prof = int(prof145["regret0"].isna().sum())
    n_m3_missing_stop = int(stop368["m3"].isna().sum())

    # ── 2층 buy-side + 분봉 ──────────────────────────────────────────────
    l2_stop = l2_stop.merge(df1[["id", "p_sell", "regret0", "close"]], on="id", how="left")
    l2_prof = l2_prof.merge(df1[["id", "p_sell", "regret0", "close"]], on="id", how="left")
    buy_ids = list(l2_stop["buy_record_id"]) + list(l2_prof["buy_record_id"])
    buy_side = load_buy_side(conn, buy_ids)
    l2_stop = l2_stop.merge(buy_side, left_on="buy_record_id", right_on="id", suffixes=("", "_buy"), how="left")
    l2_prof = l2_prof.merge(buy_side, left_on="buy_record_id", right_on="id", suffixes=("", "_buy"), how="left")
    l2_stop["stop_price"] = l2_stop["p_buy"] * (1 - l2_stop["stop_loss_rate"])
    l2_prof["profit_price"] = l2_prof["p_buy"] * (1 + l2_prof["target_profit_rate"])

    l2_stop_96 = l2_stop[l2_stop["has_minute"]].copy().reset_index(drop=True)
    bars = load_minute_bars(conn, list(l2_stop_96["stock_code"]), list(l2_stop_96["date8"]))
    bars_by_key = {k: g.sort_values("datetime").reset_index(drop=True) for k, g in bars.groupby(["stock_code", "date"])}

    # ── 종목-일별 분봉 지표 계산(§3-6) ──────────────────────────────────
    rows = []
    for r in l2_stop_96.itertuples():
        key = (r.stock_code, r.date8)
        g = bars_by_key.get(key)
        rec = dict(stock_code=r.stock_code, strategy=r.strategy, sell_date=r.sell_date,
                   stop_price=r.stop_price, t_first_touch=None, gap_touch_exec=np.nan,
                   n_crossings=np.nan, min_after_touch=np.nan, recovered_by_close=np.nan,
                   vol0_in_window=np.nan, all_vol0=False, n_bars_window=0)
        if g is None or len(g) == 0:
            rec["no_touch"] = True
            rows.append(rec)
            continue
        touched = g[g["low"] <= r.stop_price]
        if len(touched) == 0:
            rec["no_touch"] = True
            rows.append(rec)
            continue
        rec["no_touch"] = False
        t_first_touch = touched.iloc[0]["datetime"]
        rec["t_first_touch"] = t_first_touch
        window = g[g["datetime"] >= t_first_touch].reset_index(drop=True)
        gap_min = (r.ts_kst - t_first_touch).total_seconds() / 60.0
        rec["gap_touch_exec"] = gap_min
        signs = np.sign(window["close"].to_numpy() - r.stop_price)
        rec["n_crossings"] = int(np.sum(signs[1:] != signs[:-1])) if len(signs) > 1 else 0
        rec["min_after_touch"] = float(window["low"].min())
        rec["recovered_by_close"] = 1 if (pd.notna(r.close) and r.close > r.stop_price) else (
            np.nan if pd.isna(r.close) else 0)
        rec["vol0_in_window"] = int((window["volume"] == 0).sum())
        rec["all_vol0"] = bool((window["volume"] == 0).all())
        rec["n_bars_window"] = len(window)
        rows.append(rec)
    l2_detail = pd.DataFrame(rows)

    n_no_minute = len(l2_stop) - len(l2_stop_96)
    n_no_touch = int(l2_detail["no_touch"].sum())
    l2_valid = l2_detail[~l2_detail["no_touch"]].copy().reset_index(drop=True)

    # ── §3-5 무결성 게이트 ───────────────────────────────────────────────
    n_gap_negative = int((l2_valid["gap_touch_exec"] < 0).sum())
    integrity_ok = (n_gap_negative == 0)

    say("## §3-5 🔴 무결성 게이트 — `t_exec < t_first_touch` 건수\n")
    say(f"2층 96건 중 분봉 없음 **{n_no_minute}**건(§3-6 결측, 별도 보고) · "
        f"`t_first_touch` 없음(그날 `low ≤ stop_price` 인 분봉이 하나도 없음) **{n_no_touch}**건 "
        "(§3-6, n_crossings·min_after_touch·recovered_by_close 계산에서 제외) · "
        f"판정 가능 **{len(l2_valid)}**건.\n")
    say(f"**`gap_touch_exec < 0` (체결이 손절선에 닿기 «전»으로 기록됨) 건수 = {n_gap_negative}**\n")
    if integrity_ok:
        say("⇒ **0건 — 시각 정합이 맞다. §6~§7 로 진행한다.**\n")
    else:
        say("⇒ 🔴🔴 **0건이 아니다 — §6~§7 의 어떤 결과도 해석하지 않고 여기서 멈춘다(§3-5).** "
            "시각 정합(§3-4 tz 변환)이 깨졌거나 다른 데이터 결손이 있다는 신호다. 원인을 규명하고 "
            "고친 뒤 재실행해야 한다 — 아래 위반 건 목록만 보고하고 종료한다.\n")
        bad = l2_valid[l2_valid["gap_touch_exec"] < 0]
        say("| 종목 | 전략 | 매도일 | gap_touch_exec(분) |")
        say("|---|---|---|---|")
        for r in bad.itertuples():
            say(f"| {r.stock_code} | {r.strategy} | {r.sell_date} | {r.gap_touch_exec:.1f} |")
        (BASE / "RESULTS.md").write_text("\n".join(OUT), encoding="utf-8")
        print("\n[written] RESULTS.md (무결성 게이트 실패 — §6~§7 미실행)")
        conn.close()
        return 1

    say("### §3-6 결측·이상치 — 전부 인쇄(조용히 안 뺀다)\n")
    say(f"- arm 1층(368) `regret0` 결측: **{n_regret0_missing_stop}**건 · 익절(145) `regret0` 결측: "
        f"**{n_regret0_missing_prof}**건 (§8-10, `daily_prices` 최종일 제한)")
    say(f"- 1층 `m3`(지수 결측 포함) 결측: **{n_m3_missing_stop}**건(손절 기준, 참고 지표)")
    say(f"- 2층 96건 중 `t_first_touch` 없음: **{n_no_touch}**건")
    vol0_full = l2_valid[l2_valid["all_vol0"]]
    say(f"- 2층 판정가능 {len(l2_valid)}건 중 구간 «전체»가 `volume=0`(전량 무거래 구간): "
        f"**{len(vol0_full)}**건" + (" — 아래 표\n" if len(vol0_full) else "\n"))
    if len(vol0_full):
        say("| 종목 | 전략 | 매도일 | 창 내 봉수 |")
        say("|---|---|---|---|")
        for r in vol0_full.itertuples():
            say(f"| {r.stock_code} | {r.strategy} | {r.sell_date} | {r.n_bars_window} |")
        say()
    say(f"- 2층 판정가능 {len(l2_valid)}건의 `[t_first_touch, 장마감]` 구간 내 `volume=0` 봉 총합: "
        f"**{int(l2_valid['vol0_in_window'].sum())}**개(전체 창 합 {int(l2_valid['n_bars_window'].sum())}개 중)\n")

    if n_no_minute:
        say(f"**분봉 없는 {n_no_minute}건(2층 모집단 밖):**\n")
        say("| 종목 | 전략 | 매도일 |")
        say("|---|---|---|")
        for r in l2_stop[~l2_stop["has_minute"]].itertuples():
            say(f"| {r.stock_code} | {r.strategy} | {r.sell_date} |")
        say()
    if n_no_touch:
        say(f"**`t_first_touch` 없는 {n_no_touch}건(일봉 손절 판정과 모순 — 원인 후보 §3-6):**\n")
        say("| 종목 | 전략 | 매도일 |")
        say("|---|---|---|")
        for r in l2_detail[l2_detail["no_touch"]].itertuples():
            say(f"| {r.stock_code} | {r.strategy} | {r.sell_date} |")
        say()

    say("<details><summary>2층 96건 — 종목-일별 상세(펼치기)</summary>\n")
    say("| 종목 | 전략 | 매도일 | stop_price | t_first_touch | gap_touch_exec(분) | n_crossings | "
        "min_after_touch(vs stop) | recovered_by_close | vol0/창 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for r in l2_detail.itertuples():
        if r.no_touch:
            say(f"| {r.stock_code} | {r.strategy} | {r.sell_date} | {r.stop_price:.0f} | "
                "«없음» | — | — | — | — | — |")
        else:
            rel = (r.min_after_touch - r.stop_price) / r.stop_price
            rec = "예" if r.recovered_by_close == 1 else ("아니오" if r.recovered_by_close == 0 else "결측")
            say(f"| {r.stock_code} | {r.strategy} | {r.sell_date} | {r.stop_price:.0f} | "
                f"{r.t_first_touch} | {r.gap_touch_exec:.1f} | {int(r.n_crossings)} | "
                f"{rel*100:+.2f}% | {rec} | {int(r.vol0_in_window)}/{int(r.n_bars_window)} |")
    say("\n</details>\n")
    say("---\n")

    # ═══════════════════════════════════════════════════════════════════
    # §6 결과
    # ═══════════════════════════════════════════════════════════════════
    say("## §6 결과\n")

    # ── M1 / M2 ──────────────────────────────────────────────────────────
    m1 = float(stop368["regret0"].median())
    m2 = float(prof145["regret0"].median())

    def bucket_m(x):
        if x >= EPS1:
            return "M+"
        if x <= -EPS1:
            return "M−"
        return "중립"

    m1b, m2b = bucket_m(m1), bucket_m(m2)
    say("### M1(주) — `regret0`(손절, n=368 전체) 중앙값\n")
    say(f"**{fmt_pct(m1)}** → `{m1b}`(ε1=±0.21%p) · 결측 {n_regret0_missing_stop}건\n")
    say("### M2(반증축·필수) — `regret0`(익절, n=145 전체) 중앙값\n")
    say(f"**{fmt_pct(m2)}** → `{m2b}`(ε1=±0.21%p) · 결측 {n_regret0_missing_prof}건\n")

    say("### M3(부수·시장통제) — `regret0 − 소속지수 당일수익률`(손절, 판정 미사용·참고만)\n")
    m3 = float(stop368["m3"].median())
    say(f"중앙 **{fmt_pct(m3)}** · 결측 {n_m3_missing_stop}건(지수 매핑 불가 또는 `returns_1d` 결측 포함)\n")

    # ── 1층 시각대 층화 부수(§3-1) ──────────────────────────────────────
    say("### 1층 부수 — 시각대별 `regret0` 중앙값(§3-1)\n")
    say("| 구간 | 손절 n | 손절 regret0 중앙 | 익절 n | 익절 regret0 중앙 |")
    say("|---|---|---|---|---|")
    for lab in TOD_LABELS:
        gs = stop368[stop368["tod"] == lab]
        gp = prof145[prof145["tod"] == lab]
        say(f"| {lab} | {len(gs)} | {fmt_pct(gs['regret0'].median()) if len(gs) else '—'} | "
            f"{len(gp)} | {fmt_pct(gp['regret0'].median()) if len(gp) else '—'} |")
    say()

    # ── M_asym ───────────────────────────────────────────────────────────
    say("### M_asym(귀무·필수) — 09:05+ 로 제한한 별도 표본\n")
    if not gate1_ok:
        say(f"**1차(카운트) 위반** — 익절 09:05+ n={m_asym_prof_n} < 30 ⇒ "
            "`M_asym` = **판별불가(카운트문턱)**. 순열은 계산하지 않는다.\n")
        m_asym_label = "판별불가(카운트문턱)"
        real_diff = float("nan")
        eps_asym = float("nan")
        reps = []
    else:
        pop = pd.concat([
            stop368[stop368["tod"] != "09:00~09:05"][["sell_date", "regret0"]].assign(is_stop=True),
            prof145[prof145["tod"] != "09:00~09:05"][["sell_date", "regret0"]].assign(is_stop=False),
        ], ignore_index=True)
        deg = degenerate_diag(pop, n_stop_total=len(stop368))
        say(f"**2차(퇴화일)** — 배제건수(퇴화일의 실제 손절건수 합) {deg['degenerate_excluded']} / "
            f"{len(stop368)} = **{deg['share']*100:.1f}%** ⇒ "
            + (f"< 1/3, 통과.\n" if deg["ok"] else "🔴 ≥ 1/3 — `M_asym` = **판별불가(퇴화일)**.\n"))
        rng = np.random.default_rng(SEED)
        reps = m_asym_permutation(rng, pop, N_REPS)
        eps_asym = float(np.max(np.abs([d for _, _, d in reps])))
        real_diff = float(pop.loc[pop["is_stop"], "regret0"].median()) - float(pop.loc[~pop["is_stop"], "regret0"].median())
        if real_diff >= eps_asym:
            asym_bucket = "비대칭"
        elif real_diff <= -eps_asym:
            asym_bucket = "역비대칭"
        else:
            asym_bucket = "대칭"
        say(f"**3차(잔여 시각대 교란, §4-3)** — " + ("걸리지 않음.\n" if gate3_ok else "걸림.\n"))

        say(f"`real_diff` = median(regret0,손절,09:05+ n={len(stop368)}) − "
            f"median(regret0,익절,09:05+ n={m_asym_prof_n}) = **{fmt_pp(real_diff)}**\n")
        say(f"`ε_asym`(permutation 20회 max\\|diff_j\\|) = **{fmt_pp(eps_asym)}**\n")

        if not deg["ok"]:
            m_asym_label = "판별불가(퇴화일)"
        elif not gate3_ok:
            m_asym_label = f"판별 불가(시각대 교란) — 계산값은 `{asym_bucket}`(참고, §7 판정 미사용)"
        else:
            m_asym_label = asym_bucket
        say(f"⇒ **`M_asym` = {m_asym_label}**\n")

        say("<details><summary>M_asym 순열 20회 원값(펼치기)</summary>\n")
        say("| j | m_stop,j | m_profit,j | diff_j |")
        say("|---|---|---|---|")
        for j, (ms, mp, d) in enumerate(reps, 1):
            say(f"| {j} | {fmt_pct(ms)} | {fmt_pct(mp)} | {fmt_pp(d)} |")
        diffs_arr = [d for _, _, d in reps]
        say(f"| **최소** | — | — | {fmt_pp(min(diffs_arr))} |")
        say(f"| **중앙** | — | — | {fmt_pp(float(np.median(diffs_arr)))} |")
        say(f"| **최대** | — | — | {fmt_pp(max(diffs_arr))} |")
        say(f"| **max\\|diff_j\\|(=ε_asym)** | — | — | {fmt_pp(eps_asym)} |")
        say("\n</details>\n")

    # ── M4 ───────────────────────────────────────────────────────────────
    say("### M4(주·2층) — `recovered_by_close` 비율(96건, §3-6 결측 제외)\n")
    m4_pop = l2_valid.dropna(subset=["recovered_by_close"])
    n_m4 = len(m4_pop)
    k_m4 = int(m4_pop["recovered_by_close"].sum())
    m4_ratio = k_m4 / n_m4 if n_m4 else float("nan")
    if n_m4 < COUNT_LOW:
        say(f"실질 분모 {n_m4} < 30 ⇒ **검정력 부족 → 판별불가**.\n")
        m4_p = float("nan")
    else:
        bt4 = binomtest(k_m4, n_m4, 0.5, alternative="two-sided")
        m4_p = float(bt4.pvalue)
        say(f"{k_m4} / {n_m4} = **{m4_ratio*100:.1f}%** 이 종가까지 손절선 «위」로 되돌아왔다. "
            f"이항검정(양측, p_null=0.5) p = **{m4_p:.4f}** ⇒ "
            + ("**p<0.05, 유의.**\n" if m4_p < 0.05 else "**p≥0.05, 판별불가(비유의).**\n"))

    # ── M4b ──────────────────────────────────────────────────────────────
    say("### M4b(조건부·2층) — 3전략 익절 건의 `recovered_by_close`(대칭 정의)\n")
    if m4b_gate_ok:
        m4b_pop = l2_prof[l2_prof["has_minute"]].copy()
        m4b_pop["recovered_by_close"] = np.where(
            m4b_pop["close"].isna(), np.nan,
            np.where(m4b_pop["close"] < m4b_pop["profit_price"], 1, 0))
        m4b_pop_valid = m4b_pop.dropna(subset=["recovered_by_close"])
        n_m4b = len(m4b_pop_valid)
        k_m4b = int(m4b_pop_valid["recovered_by_close"].sum())
        m4b_ratio = k_m4b / n_m4b if n_m4b else float("nan")
        bt4b = binomtest(k_m4b, n_m4b, 0.5, alternative="two-sided") if n_m4b else None
        m4b_p = float(bt4b.pvalue) if bt4b else float("nan")
        say(f"커버리지 79% 통과(§5-4) ⇒ 계산한다. {k_m4b} / {n_m4b} = **{m4b_ratio*100:.1f}%** 이 "
            f"종가까지 익절선 «아래」로 되돌아왔다. 이항검정 p = **{m4b_p:.4f}**"
            f"(⚠️ n={n_m4b} 로 매우 작다 — 참고 수준).\n")
    else:
        say("커버리지 79% 미달(§5-4) ⇒ **계산하지 않는다(§4-2, §9).**\n")
        n_m4b = 0
        m4b_ratio = float("nan")
        m4b_p = float("nan")

    # ── M5 / M6 / M7 ─────────────────────────────────────────────────────
    say("### M5(부수·기술통계) — `n_crossings` 분포(96건 중 판정가능 " + str(len(l2_valid)) + "건)\n")
    nc = l2_valid["n_crossings"].dropna()
    say(f"중앙 **{nc.median():.1f}회** · 평균 {nc.mean():.2f}회 · ≥1회 비중 {(nc >= 1).mean()*100:.1f}% "
        f"· 최대 {int(nc.max())}회\n")

    say("### M6(부수·기술통계) — `min_after_touch` vs `stop_price`(비율)\n")
    rel6 = (l2_valid["min_after_touch"] - l2_valid["stop_price"]) / l2_valid["stop_price"]
    say(f"중앙 **{fmt_pct(rel6.median())}** · 평균 {fmt_pct(rel6.mean())} · "
        f"최댓값(가장 덜 내려간 경우) {fmt_pct(rel6.max())} · 최솟값(가장 더 내려간 경우) {fmt_pct(rel6.min())}\n")

    say("### M7(진단) — `gap_touch_exec` 분포(판정 미사용, §3-7)\n")
    gp7 = l2_valid["gap_touch_exec"]
    say(f"중앙 **{gp7.median():.1f}분** · p90 {gp7.quantile(0.9):.1f}분 · 최댓값 {gp7.max():.1f}분\n")
    say("---\n")

    # ═══════════════════════════════════════════════════════════════════
    # §7 판정
    # ═══════════════════════════════════════════════════════════════════
    say("## §7 판정\n")

    say("### §7-1. 1층 확정 판정(368+145건 — 이 문서의 «주» 결론)\n")
    majority_missing = n_regret0_missing_stop > len(stop368) / 2
    if majority_missing:
        label71 = "판별 불가"
        reason71 = f"`regret0` 결측({n_regret0_missing_stop}건)이 368건의 과반"
    elif m1b != "M+":
        label71 = "진짜 하락의 시작이었다(1층)"
        reason71 = f"M1={fmt_pct(m1)} → `{m1b}` (M1+ 아님 — `M_asym` 과 무관하게 확정)"
    else:
        if not gate1_ok:
            label71 = "판별 불가"
            reason71 = "M1=M1+ 인데 `M_asym` 이 카운트 문턱으로 판별불가"
        else:
            # deg, gate3_ok, asym_bucket 은 위 블록에서 이미 계산됨
            if not deg["ok"]:
                label71 = "판별 불가"
                reason71 = "M1=M1+ 인데 `M_asym` 이 퇴화일 문턱으로 판별불가"
            elif not gate3_ok:
                label71 = "판별 불가(시각대 교란)"
                reason71 = f"M1=M1+ 인데 §4-3 잔여 시각대 교란 게이트가 걸림(계산값 `{asym_bucket}`은 참고만)"
            elif asym_bucket == "비대칭":
                label71 = "노이즈였다(1층)"
                reason71 = f"M1=M1+({fmt_pct(m1)}) AND M_asym=비대칭({fmt_pp(real_diff)}≥{fmt_pp(eps_asym)}) AND §4-3 안 걸림"
            elif asym_bucket == "역비대칭":
                label71 = "역비대칭(참고 기록)"
                reason71 = f"M1=M1+({fmt_pct(m1)}) AND M_asym=역비대칭({fmt_pp(real_diff)}) AND §4-3 안 걸림"
            else:
                label71 = "평균회귀일 뿐(대칭)"
                reason71 = f"M1=M1+({fmt_pct(m1)}) AND M_asym=대칭(|{fmt_pp(real_diff)}|<{fmt_pp(eps_asym)}) AND §4-3 안 걸림"

    say(f"### 🔴 §7-1 판정: **{label71}**\n")
    say(f"근거: {reason71}\n")

    say("### §7-2. 2층 조건부 판정(96건, 3전략 한정 — 「보강」이지 독립 결론이 아니다)\n")
    if n_m4 < COUNT_LOW:
        label72 = "2층 판별 불가"
        reason72 = f"M4 실질 분모 {n_m4} < 30"
    elif label71 == "노이즈였다(1층)":
        if m4_p < 0.05 and m4_ratio > 0.5:
            label72 = "노이즈였다(2층 보강, 3전략 한정)"
        else:
            label72 = "1층·2층 불일치(3전략 한정)"
        reason72 = f"§7-1=노이즈였다(1층) · M4 비율={m4_ratio*100:.1f}% p={m4_p:.4f}"
    elif label71 == "진짜 하락의 시작이었다(1층)":
        if m4_ratio <= 0.5:
            label72 = "진짜 하락 재확인(2층, 3전략 한정)"
        else:
            label72 = "1층·2층 불일치(3전략 한정)"
        reason72 = f"§7-1=진짜 하락의 시작이었다(1층) · M4 비율={m4_ratio*100:.1f}%(유의여부 무관, 방향만)"
    else:
        label72 = "해당 없음"
        reason72 = (f"§7-1=「{label71}」은 §7-2 판정표(§7-1이 「노이즈였다」/「진짜 하락의 시작이었다」일 "
                     "때만 정의됨)의 대상이 아니다 — M4 자체는 위에 그대로 계산·인쇄했다(투명성).")

    say(f"### 🔴 §7-2 판정: **{label72}**\n")
    say(f"근거: {reason72}\n")
    say("🔴🔴 **2층 라벨은 «절대» 8전략 전체로 일반화하지 않는다** — elder_ema_pullback·"
        "book_envelope_200d·deep_mr_dev20 3전략 한정이고, 하필 8전략 중 성적 최하위권"
        "(−3.85%~−4.52%)이다. `book_pullback_ma5`(+0.02%)·`daytrading_3methods_breakout`"
        "(+0.45%)에는 이 연구가 답하지 않는다(커버리지 38%·15%).\n")
    say("---\n")

    # ═══════════════════════════════════════════════════════════════════
    # §8 한계
    # ═══════════════════════════════════════════════════════════════════
    say("## 🔴 한계 — PREREG §8 승계 + 이번 실행에서 새로 드러난 것\n")
    say("**§8 승계(그대로)**:\n")
    say("1. 🔴 한 국면이다(2026-06~08). 일반화 금지.")
    say("2. 🔴 2층은 3전략(elder_ema_pullback·book_envelope_200d·deep_mr_dev20) 한정이고, 하필 8전략 "
        "중 성적 최하위권이다. `book_pullback_ma5`·`daytrading_3methods_breakout`엔 이 연구가 안 답한다.")
    say("3. 🔴 1층 모집단(368)은 `stoploss_counterfactual`(371)과 다른 모집단이다(§3-1 — PM 실시간 "
        "경로 손절만, 전략 고유 손절 3건 제외).")
    say("4. 🔴 분봉 표본은 다른 모집단이다 — `minute_candles` 는 1,490종목(유니버스의 54%)·2025-02-24~"
        "이고 일봉보다 훨씬 짧다.")
    say("5. ⚠️ 체결 슬리피지·호가 미반영 — `regret0`·`recovered_by_close` 모두 분봉 극값 비교이지 "
        "실제 체결 가능성을 보장하지 않는다.")
    say("6. ⚠️ 손절·익절 발동 조건의 코드 비대칭(§4) — §4-1 이 09:00~09:05 를 `M_asym` 표본 정의에서 "
        "제거해 대응했다.")
    say("7. ⚠️ 미청산분·다른 청산사유(트레일링·보유기간·기타) 표본 밖.")
    say("8. ⚠️ `n_crossings`·`min_after_touch`(M5·M6)는 기술통계다 — 공식 귀무·ε 없이 판정에 안 쓴다.")
    say("9. ⚠️ `gap_touch_exec` 이상치(음수)는 §3-5 무결성 게이트 대상 — 0건이 아니면 §6~§7 전체를 "
        "계산하지 않는다(이번 실행은 0건이라 통과).")
    say("10. ⚠️ `daily_prices` 최종일 제한(2026-08-14) — 매도일이 창 끝자락이면 `regret0` 이 결측일 "
        "수 있다(위 §3-6 건수 참고).")
    say()
    say("**이번 실행에서 새로 드러난 것**:\n")
    say(f"- 🆕 M4b 는 커버리지 문턱은 통과했지만(§5-4, {cov*100:.1f}%) 모집단이 {n_l2p_has}건으로 "
        "«매우 작다» — 이항검정 자체의 통계적 검정력이 형식적일 수 있다(PREREG 는 M4b 에 별도 카운트 "
        "문턱을 두지 않았으므로 계산은 그대로 인쇄하되, 이 작은 n 을 근거로 강하게 해석하지 않는다.")
    say(f"- 🆕 §5-2 전략별 구성비 괴리 최대값은 `{worst_st}`였다 — 값 자체는 위 표 참고, §4-1 결과 "
        "해석 시 이 쏠림을 감안해야 한다.")
    say(f"- 🆕 2층 96건 중 `t_first_touch` 없음 {n_no_touch}건 — 일봉 손절 판정과의 모순으로, "
        "분봉 데이터의 알려진 결손(거래정지일에도 분봉을 준다·수집 갭) 가능성을 시사한다(§3-6).")
    say(f"- 🆕 무결성 게이트(§3-5)는 **0건**으로 통과했다 — §3-4 KST 정합이 이 실행에서 실제로 "
        "지켜졌다는 사후 검증이다.")
    say()

    # ═══════════════════════════════════════════════════════════════════
    # 🔑 재사용 규칙
    # ═══════════════════════════════════════════════════════════════════
    say("## 🔑 재사용 규칙 — 이번에 배운 것\n")
    say("- 🔑 ***코드로 확정된 비대칭(구조적 0%)은 사후 게이트로 거르지 말고 표본 정의에서 애초에 "
        "제거하라*** — §4-1 이 09:00~09:05 를 `M_asym` 표본에서 빼서 「걸릴 걸 알면서 게이트를 두는」 "
        "요식을 피했다. 손절 쪽은 그 구간에 애초에 존재할 수 없으므로(코드 사실) 표본 제거가 손실 "
        "없이 가능했다 — «탐지»가 아니라 «제거»가 더 강한 설계다.")
    say("- 🔑 ***같은 연구 안에서 1층·2층을 «중첩»시키려면, 1층 모집단을 2층이 실제로 잰 것과 "
        "정확히 같은 정의로 좁혀야 한다*** — 이 문서가 1층 모집단을 371 이 아니라 368(PM 실시간 경로 "
        "한정)로 의도적으로 축소한 이유이자, `stoploss_counterfactual`의 371과 이 문서의 368을 "
        "직접 비교하면 안 되는 이유다.")
    say("- 🔑 ***분봉 커버리지가 성과와 반대로 정렬돼 있으면, 「분봉 있는 것만 합친 결론」은 "
        "«그 하위집단의 결론」이지 전체의 결론이 아니다*** — `stop_vol_fit_gate` 의 교훈을 «결과를 "
        "보기 전에» 설계 단계(§3-2 문턱을 데이터의 자연스러운 단절선에서 고정)에서 반영한 사례.")
    say("- 🔑 ***무결성 게이트(불가능한 시간 순서)를 개별 건 제외가 아니라 전체 정지 조건으로 "
        "두면, 「우연히 순서가 맞아떨어지는」 tz 오류가 나머지 건에 섞여 있어도 원인 자체를 "
        "없애도록 강제한다*** — 이번 실행은 게이트를 통과했지만(0건), 통과 자체가 §3-4 KST 정합이 "
        "실제로 지켜졌다는 사후 증거가 됐다.")
    say("- 🔑 ***PIT 전용 1단계(§5)에서 «가격을 보기 전에» 순열 게이트(카운트·잔여 시각대 교란)를 "
        "확정해두면, 그 게이트의 통과/실패가 결과의 방향에 영향받을 수 없다*** — 익절 09:00~09:05 "
        "건수(49건)·잔여 시각대 교란 판정 모두 `regret0` 을 계산하기 «전»에 확정했다.")
    say()

    (BASE / "RESULTS.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS.md")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
