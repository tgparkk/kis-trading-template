"""daytrading 후보 복제 — 라이브 `screener.py`·`_rule_screener_base.py`·`rules.py`·`quant_daily_reader.py`·`data_sanity.py`
의 SQL·룰을 «그대로» 옮긴 판(라이브 import 0 · 원본 sha 는 guard 가 고정).

🔴 거래량 조정은 SQL 한 줄 안의 `volume * COALESCE(adj_factor, 1)` 뿐(레포 가드).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from . import settings as S

UNIVERSE_SQL = (
    "SELECT stock_code, COALESCE(market_cap,0), COALESCE((close * (volume * COALESCE(adj_factor, 1)))::numeric, 0) AS trading_value "
    "FROM daily_prices WHERE date = (SELECT max(date) FROM daily_prices WHERE date <= %s AND market_cap IS NOT NULL) "
    "AND market_cap IS NOT NULL"
)
UNIVERSE_DATE_SQL = "SELECT max(date) FROM daily_prices WHERE date <= %s AND market_cap IS NOT NULL"
DAILY_SQL = (
    "SELECT date, open, high, low, close, (volume * COALESCE(adj_factor, 1))::double precision AS volume "
    "FROM daily_prices WHERE stock_code = %s AND date <= %s ORDER BY date DESC LIMIT %s"
)
SNAPSHOT_SQL = ("SELECT stock_code, rank_in_snapshot, score FROM screener_snapshots "
                "WHERE strategy = %s AND scan_date = %s AND params_hash = %s ORDER BY rank_in_snapshot")


@dataclass(frozen=True)
class Cand:
    stock_code: str
    score: float
    rank: int


def base_filter(rows: List[Tuple[str, float, float]]) -> List[Tuple[str, float, float]]:
    out = []
    for code, mcap, tv in rows:
        if mcap is None or mcap <= 0 or mcap >= S.MAX_MCAP:
            continue
        if (tv or 0.0) < S.MIN_TV:
            continue
        out.append((code, mcap, tv))
    return out


def impossible(df: pd.DataFrame) -> bool:
    close = pd.to_numeric(df["close"], errors="coerce")
    close = close.where(close > 0)
    ret = close.pct_change(fill_method=None)
    return bool((ret < S.IMPOSSIBLE_RET).any())


def match(df: pd.DataFrame) -> Optional[float]:
    if len(df) < S.HIGH_WINDOW + 2:
        return None
    last = df.iloc[-1]
    prior_high = float(df["high"].iloc[-(S.HIGH_WINDOW + 1):-1].max())
    avg_vol = float(df["volume"].iloc[-(S.VOL_LOOKBACK + 1):-1].mean())
    close, vol, open_ = float(last["close"]), float(last["volume"]), float(last["open"])
    if not (close >= prior_high and avg_vol > 0 and vol >= avg_vol * S.VOL_MULT and close > open_):
        return None
    if not close > 0:
        return None
    return vol / (float(df["volume"].iloc[-21:-1].mean()) or 1.0)


def rank(scored: List[Tuple[str, float]]) -> List[Cand]:
    ordered = sorted(scored, key=lambda t: -t[1])          # 안정 정렬 = 동점은 유니버스(입력) 순서
    return [Cand(c, float(s), i + 1) for i, (c, s) in enumerate(ordered)]


def d_complete(cur, D: date, dprev: Optional[date]) -> Tuple[bool, Dict[str, Any]]:
    """D 가격 완결 = D 행수 / D′ 행수 ≥ 0.98 ∧ 유니버스 날짜 == D. D·D′ 은 러너가 달력(utils.korean_holidays)으로 정해
    넘긴다 — KOSPI 의사티커 적재 상태로 날짜를 정하지 않는다(늦게 적재된 날 엉뚱한 D 방지)."""
    q = "SELECT count(*) FROM daily_prices WHERE date = %s AND market_cap IS NOT NULL"
    cur.execute(q, (D.isoformat(),))
    n_d = int(cur.fetchone()[0])
    n_p = 0
    if dprev is not None:
        cur.execute(q, (dprev.isoformat(),))
        n_p = int(cur.fetchone()[0])
    cur.execute(UNIVERSE_DATE_SQL, (D.isoformat(),))
    ud = cur.fetchone()[0]
    info = {"d_rows": n_d, "dprev_rows": n_p, "universe_date": str(ud)[:10] if ud else None}
    ok = n_p > 0 and n_d / n_p >= S.D_ROWS_RATIO_MIN and info["universe_date"] == D.isoformat()
    return ok, info


def _daily(cur, code: str, D: date) -> pd.DataFrame:
    cur.execute(DAILY_SQL, (code, D.isoformat(), S.LOOKBACK_BARS))
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df[df["date"].dt.date <= D]


def compute(cur, D: date) -> List[Cand]:
    cur.execute(UNIVERSE_SQL, (D.isoformat(),))
    uni = [(str(c), float(m or 0), float(t or 0)) for c, m, t in cur.fetchall()]
    scored: List[Tuple[str, float]] = []
    for code, _m, _t in base_filter(uni):
        df = _daily(cur, code, D)
        if df.empty or impossible(df):
            continue
        s = match(df)
        if s is not None:
            scored.append((code, s))
    return rank(scored)


def load_snapshot(cur, D: date) -> List[Tuple[str, int, float]]:
    cur.execute(SNAPSHOT_SQL, (S.FOLDER, D, S.PARAMS_HASH))
    return [(str(c), int(r), float(s) if s is not None else float("nan")) for c, r, s in cur.fetchall()]


def compare(mine: List[Cand], snap: List[Tuple[str, int, float]]) -> Dict[str, Any]:
    m = {c.stock_code: c for c in mine}
    s = {c: (r, sc) for c, r, sc in snap}
    only_mine = sorted(set(m) - set(s))
    only_snap = sorted(set(s) - set(m))
    common = set(m) & set(s)
    diffs = [abs(m[c].score - s[c][1]) for c in common]
    rank_equal = all(m[c].rank == s[c][0] for c in common)
    max_diff = max(diffs) if diffs else 0.0
    ok = not only_mine and not only_snap and rank_equal and max_diff < 1e-9
    return {"match": ok, "mine_n": len(m), "snapshot_n": len(s), "max_score_diff": max_diff,
            "only_mine": only_mine, "only_snap": only_snap, "rank_equal": rank_equal}
