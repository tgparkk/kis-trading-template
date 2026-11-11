"""E1-lite — 실제 dt «매수» 체결 시각을 주고 «가격만» 분봉으로 재현해 체결 모델 오차를 잰다(사전등록 §3 · §9).

    python -X utf8 -m backtest.concept_axes.minute_rules.fill_lite --start 2026-06-10 --end 2026-11-10

모델(엔진 `engine.py` §3 과 같은 순서) — 체결 시각 T 가 든 분(분 «시작» 행)을 t 로:
  a = round_to_tick(t 분 종가)(주 모델) · b = round_to_tick(t+1 분 시가) · raw = t 분 종가 원값(반 호가 2.84% 대비).
  오차% = (모델가 ÷ 실제 체결가 − 1) × 100(+ 면 모델이 비싸다 · `fidelity8.entry_diff_stats` 와 같은 부호).
  `in_range` = 실제가가 그 분 [저가, 고가] 안(10-08 표본 15/15).
나눔: 호가표 시대(`round_to_tick` KRX 2023 표 = 10-19 07:40 발효 · 그 전 페이퍼 체결은 옛 표 · EXPERT_SYSTEM #3) ·
  시각대 09:00~05 / 05~10 / 10~(= 09:10~) · 출처(paper = `virtual_trading_records` · real = `real_trading_daytrading`).
🔴 판정 근거 아님 · 규칙 효과와 무관(체결가 모델 오차만) · DB SELECT 만 · 실전 매도·익절 오차는 이 모듈 밖.
🔒 출력 = 레포 밖(env `KIS_MINUTE_PRIVATE_DIR` · 기본 `D:/tmp/kis-minute-private/fill_lite.csv`) — 실전 계좌 매수 체결
   (종목·시각·가격)이 들어가고 레포는 공개라서(리뷰 A7) · 레포 안 경로를 주면 거부.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from backtest.concept_axes.ledger8.fidelity8 import entry_diff_stats
from utils.price_utils import round_to_tick

from . import data as D
from . import engine as E

KST = timezone(timedelta(hours=9))
TICK_TABLE_CUT = date(2026, 10, 19)
BUCKETS = (("0900_0905", 0, 5), ("0905_0910", 5, 10), ("0910_", 10, E.N_CONT))
STRATEGY = "daytrading_3methods_breakout"
PRIVATE_ENV = "KIS_MINUTE_PRIVATE_DIR"
PRIVATE_DEFAULT = Path("D:/tmp/kis-minute-private")   # 실전 계좌 체결이 들어가므로 레포 밖(리뷰 A7)
FILL_COLS = ["source", "stock_code", "trade_date", "ts", "price", "tick_era", "bucket", "minute_idx", "excl",
             "close_raw", "px_a", "px_b", "err_a", "err_b", "err_raw", "in_range"]


@dataclass(frozen=True)
class Fill:
    source: str                    # paper | real
    code: str
    ts: datetime                   # KST(naive 면 KST 로 본다)
    price: float


def _kst(ts: datetime) -> datetime:
    return ts.replace(tzinfo=KST) if ts.tzinfo is None else ts.astimezone(KST)


def minute_idx(ts: datetime) -> Optional[int]:
    """체결 시각 → 분 «시작» 행 번호(09:00:00~09:00:59 = 0) · 09:00~15:19 밖이면 None."""
    t = _kst(ts)
    i = t.hour * 60 + t.minute - 9 * 60
    return i if 0 <= i < E.N_CONT else None


def bucket_of(i: int) -> str:
    for name, lo, hi in BUCKETS:
        if lo <= i < hi:
            return name
    raise ValueError(i)


def tick_era(d: date) -> str:
    return "pre1019" if d < TICK_TABLE_CUT else "post1019"


def _err(model: Optional[float], actual: float) -> Optional[float]:
    return None if model is None or not actual > 0 else (model / actual - 1.0) * 100.0


def reproduce(fill: Fill, bars: Optional[np.ndarray]) -> Dict[str, Any]:
    """체결 1건 → 모델가 a·b·raw · 오차% · 나눔 열. 분봉 없음·장 밖·그 분 가격 없음 = `excl` 사유."""
    t = _kst(fill.ts)
    row: Dict[str, Any] = dict(source=fill.source, stock_code=fill.code, trade_date=t.date(),
                               ts=t.isoformat(timespec="seconds"), price=fill.price, tick_era=tick_era(t.date()))
    i = minute_idx(t)
    if i is None:
        return dict(row, excl="off_session")
    row.update(minute_idx=i, bucket=bucket_of(i))
    if bars is None:
        return dict(row, excl="no_minute_data")
    raw = float(bars[i, E.F_CLOSE])
    if not (np.isfinite(raw) and raw > 0):
        return dict(row, excl="no_price_at_minute")
    a = round_to_tick(raw)
    nxt = float(bars[i + 1, E.F_OPEN]) if i + 1 < E.N_CONT else float("nan")
    b = round_to_tick(nxt) if np.isfinite(nxt) and nxt > 0 else None
    lo, hi = float(bars[i, E.F_LOW]), float(bars[i, E.F_HIGH])
    return dict(row, excl="", close_raw=raw, px_a=a, px_b=b, err_a=_err(a, fill.price), err_b=_err(b, fill.price),
                err_raw=_err(raw, fill.price), in_range=bool(lo <= fill.price <= hi))


def summarize(rows: Sequence[Dict[str, Any]], model: str = "err_a") -> List[Dict[str, Any]]:
    """출처|호가표 시대|시각대 칸별 오차(부호 평균·절대 평균·양수 건수) — `fidelity8.entry_diff_stats` 재사용."""
    # entry_diff_stats 는 csv 문자열 행을 받는다(빈 문자열 = 없음) — 오차 0.0 이 빠지지 않게 문자열로 넘긴다
    keyed = [dict(strategy=f"{r['source']}|{r['tick_era']}|{r['bucket']}", entry_diff_pct=format(r[model], ".15g"))
             for r in sorted(rows, key=lambda x: (x["source"], x["tick_era"], x.get("bucket", ""), x["ts"]))
             if not r.get("excl") and r.get(model) is not None]
    return entry_diff_stats(keyed)


# ── DB(SELECT 만) ─────────────────────────────────────────────────────────
PAPER_SQL = ("SELECT stock_code, timestamp, price FROM virtual_trading_records WHERE strategy = %s AND action = 'BUY' "
             "AND timestamp >= %s AND timestamp < %s ORDER BY timestamp, id")
REAL_SQL = ("SELECT stock_code, timestamp, price FROM real_trading_daytrading WHERE action = 'BUY' "
            "AND timestamp >= %s AND timestamp < %s ORDER BY timestamp, id")


def load_fills(conn, start: date, end: date) -> List[Fill]:
    a, b = datetime.combine(start, datetime.min.time(), KST), datetime.combine(end + timedelta(days=1),
                                                                                datetime.min.time(), KST)
    out = [Fill("paper", str(c), ts, float(p)) for c, ts, p in D._fetch(conn, PAPER_SQL, (STRATEGY, a, b))]
    out += [Fill("real", str(c), ts, float(p)) for c, ts, p in D._fetch(conn, REAL_SQL, (a, b))]
    return out


def private_out(arg: Optional[str] = None) -> Path:
    """출력 경로 — 인자 > env > 기본 · 어떤 git 작업 트리 안이어도 거부(A7 · 재리뷰 D3)."""
    from .run import ensure_outside_git
    p = Path(arg) if arg else Path(os.environ.get(PRIVATE_ENV) or PRIVATE_DEFAULT) / "fill_lite.csv"
    ensure_outside_git(p.parent, "A7 fill_lite 출력")
    return p


def no_gap_rows(_days: Iterable[date]) -> List[Tuple[Any, Any, Any]]:
    """E1-lite 는 G5 시장 공백 판정이 필요 없다 — 공급자를 비워 전 종목 공백 조회(SELECT)를 건너뛴다."""
    return []


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="E1-lite 체결가 모델 오차(dt 매수)")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default=str(private_out()))
    a = ap.parse_args(argv)
    from .run import _atomic_write, csv_text      # 같은 연구 폴더(운영 import 0)
    conn = D.connect()
    try:
        fills = load_fills(conn, date.fromisoformat(a.start), date.fromisoformat(a.end))
        keys = sorted({(f.code, _kst(f.ts).date()) for f in fills})
        bundle = D.load_minute_days(conn, keys, D.load_market_of(conn), gap_rows=no_gap_rows)
    finally:
        conn.close()
    rows = []
    for f in fills:
        try:
            bars: Optional[np.ndarray] = np.asarray(bundle.bars[bundle.index((f.code, _kst(f.ts).date()))],
                                                    dtype=np.float64)
        except KeyError:
            bars = None
        rows.append(reproduce(f, bars))
    out = private_out(a.out)
    _atomic_write(out, csv_text(FILL_COLS, rows))
    for g in summarize(rows):
        print(f"{g['strategy']}: n={g['n']} 부호 평균 {g['signed_mean']:+.3f}% · 절대 평균 {g['abs_mean']:.3f}% · "
              f"양수 {g['positive']}")
    print(f"체결 {len(fills)} · 제외 {sum(1 for r in rows if r.get('excl'))} → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
