"""DB 읽기 — SELECT 만. 라이브가 day D 에 `generate_signal` 로 넘긴 일봉을 «라이브 코드로» 다시 만든다.

🔑 라이브 경로(2026-09-17 코드 실측 · 커밋 c565256):
   `BaseStrategy.on_tick` (strategies/base.py:662)
     → `TradingContext.get_daily_data(code)` (core/trading_context.py:176-199, days=None → OHLCV_LOOKBACK_DAYS=120 달력일)
       → `PriceRepository.get_daily_prices(code, days=120)` (db/repositories/price.py:145-180)
            SQL: date ≥ now_kst()−120일 · 상한 없음 · ORDER BY date · volume×COALESCE(adj_factor,1) · 가격 무조정
       → `TradingContext._drop_unconfirmed_today_bar` (core/trading_context.py:143-174) — 마지막 봉 날짜 == 오늘이면 제거
     → 길이 < get_min_data_length()(=40) 이면 스킵 (base.py:663)
     → `describe_impossible_drop(data)` 불가능봉 가드 (base.py:696)
     → `generate_signal(code, data, timeframe='daily')` (base.py:708) → 캡 체크 → `_check_buy` (strategy.py:167)
   ⇒ 마지막 봉 = D-1 확정봉(D 당일 부분봉은 드롭) · 길이 ≈ 80~85 · reader = PriceRepository(daily_prices).

재현: `PriceRepository.get_daily_prices` 와 `_drop_unconfirmed_today_bar` 를 «그대로» 부르되 두 모듈의
`now_kst` 만 D 09:02 KST 로 바꿔 끼운다(프로세스 안 monkeypatch · 파일 무수정). 그리고 «그 시각엔 없던»
D 이후 행을 먼저 잘라낸다(date > D). 🔴 D-1 이하 행의 «값»은 지금 DB 빈티지다(한계 — README).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
from unittest import mock

import pandas as pd
import psycopg2

from . import bootstrap  # noqa: F401  — 안전 설정을 먼저
from .sim import Bar

from backtest.concept_axes.replayer.loader import CALENDAR_TICKER, dsn   # noqa: E402  (재현기 SSOT 재사용)
from config.constants import OHLCV_LOOKBACK_DAYS                         # noqa: E402
import core.trading_context as _tc_mod                                   # noqa: E402
import db.repositories.price as _price_mod                               # noqa: E402

STRATEGY = "minervini_volume_dryup"
FIRST_TICK = time(9, 2, 0)      # 실측 첫 on_tick 평가 시각 ≈ 09:02~09:03 (로그 [캡]/매수 시그널)

try:
    from zoneinfo import ZoneInfo          # py3.9+
    _KST = ZoneInfo("Asia/Seoul")
except Exception:  # noqa: BLE001
    _KST = None


def connect():
    conn = psycopg2.connect(**dsn())
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _fetch(conn, sql: str, args: Sequence = ()) -> List[Tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def load_calendar(conn, start: date, end: date) -> List[date]:
    rows = _fetch(conn, "SELECT DISTINCT date FROM daily_prices WHERE stock_code = %s "
                        "AND date BETWEEN %s AND %s ORDER BY date",
                  (CALENDAR_TICKER, start.isoformat(), end.isoformat()))
    return [date.fromisoformat(str(r[0])[:10]) for r in rows]


def load_snapshot(conn, scan_date: date) -> List[Dict]:
    rows = _fetch(conn, "SELECT stock_code, rank_in_snapshot, score, params_hash, "
                        "(created_at AT TIME ZONE 'Asia/Seoul') FROM screener_snapshots "
                        "WHERE strategy = %s AND scan_date = %s ORDER BY rank_in_snapshot, stock_code",
                  (STRATEGY, scan_date.isoformat()))
    return [dict(code=str(c), rank=int(r) if r is not None else None, score=s,
                 params_hash=h, created_at=ca) for c, r, s, h, ca in rows]


def load_trade_rows_by_strategy(conn, until: date) -> Dict[str, List[Tuple]]:
    """페이퍼 체결 전부(전 전략 · until 포함) → {strategy: [(id, code, action, price, ts_kst, reason, buy_record_id)]}.

    전 전략을 읽는 이유: 라이브 `bot/trading_analyzer.py:126-129` 는 «어느 전략이든» POSITIONED 인 종목의
    매수 신호를 무시한다 → minervini 에 자리가 있어도 다른 전략이 들고 있으면 못 산다.
    """
    rows = _fetch(conn, "SELECT COALESCE(strategy, ''), id, stock_code, action, price::float8, "
                        "(timestamp AT TIME ZONE 'Asia/Seoul'), reason, buy_record_id "
                        "FROM virtual_trading_records "
                        "WHERE (timestamp AT TIME ZONE 'Asia/Seoul')::date <= %s ORDER BY timestamp, id",
                  (until.isoformat(),))
    out: Dict[str, List[Tuple]] = {}
    for strat, *rest in rows:
        out.setdefault(str(strat), []).append(tuple(rest))
    return out


def load_bars(conn, code: str, start: date) -> Dict[date, Bar]:
    """start 이후 OHLC(가격 무조정 — adj_factor 를 곱하지 않는다)."""
    rows = _fetch(conn, "SELECT date, open::float8, high::float8, low::float8, close::float8 "
                        "FROM daily_prices WHERE stock_code = %s AND date >= %s ORDER BY date",
                  (code, start.isoformat()))
    out: Dict[date, Bar] = {}
    for d, o, h, lo, c in rows:
        if None in (o, h, lo, c):
            continue
        dd = date.fromisoformat(str(d)[:10])
        out[dd] = Bar(dd, float(o), float(h), float(lo), float(c))
    return out


def _as_of(d: date) -> datetime:
    dt = datetime.combine(d, FIRST_TICK)
    return dt.replace(tzinfo=_KST) if _KST is not None else dt


def live_daily_window(code: str, d: date, repo=None) -> Tuple[pd.DataFrame, Dict]:
    """라이브가 day D 첫 틱에 `generate_signal` 로 넘겼을 일봉(재현).

    Returns: (data, diag) — diag = {n_raw, n_future_dropped, dropped_today, last_bar, start_date}
    """
    if repo is None:
        repo = _price_mod.PriceRepository()
    as_of = _as_of(d)
    with mock.patch.object(_price_mod, "now_kst", return_value=as_of), \
            mock.patch.object(_tc_mod, "now_kst", return_value=as_of):
        raw = repo.get_daily_prices(code, days=OHLCV_LOOKBACK_DAYS)
        n_raw = 0 if raw is None else len(raw)
        n_future = 0
        if raw is not None and not raw.empty:
            keep = raw["date"].dt.date <= d
            n_future = int((~keep).sum())
            raw = raw[keep].reset_index(drop=True)
        before = 0 if raw is None else len(raw)
        data = _tc_mod.TradingContext._drop_unconfirmed_today_bar(raw)
    after = 0 if data is None else len(data)
    diag = dict(
        n_raw=n_raw, n_future_dropped=n_future, dropped_today=int(before - after),
        start_date=(as_of - timedelta(days=OHLCV_LOOKBACK_DAYS)).date().isoformat(),
        last_bar=(str(data["date"].iloc[-1].date()) if data is not None and not data.empty else ""),
    )
    return data, diag
