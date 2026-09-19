"""DB 읽기(SELECT 전용) — 8전략판.

순수 SELECT·달력·OHLC·일봉 창 재현은 `cap_skip_ledger.sources` 가 이미 전략 무관이라 그대로 재사용한다
(그 파일은 minervini 원장이 쓰고 있어 수정하지 않는다). 새로 두는 것은 넷:
  1. `load_snapshot(conn, strategy, scan_date)` — 원본은 모듈 상수 `STRATEGY` 를 썼다(sources.py:35 · :64-70).
  2. `snapshot_strategies(conn, start, end)` — 창 안 스냅샷 보유 전략(run_meta 점검용).
  3. `load_trades8(conn, until)` — 원본 체결 원장(sources.py:73-87)에 수량·익절률·손절률 칸을 더한 판.
  4. `WindowCache` — `(code, D)` → 라이브 일봉 창. 8전략·매도 탐침이 같은 창을 공유한다.
envelope 의 자체 프레임은 여기서 읽지 않는다 — livesignal8 이 라이브 `_check_buy` 를 그대로 부른다.
🔴 DB 쓰기 0 — `bootstrap` 이 `PGOPTIONS=default_transaction_read_only=on` 으로 서버에서 막는다.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저
from backtest.concept_axes.minervini.cap_skip_ledger import sources as _S
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar  # noqa: F401  (재노출)

connect = _S.connect
load_calendar = _S.load_calendar
load_bars = _S.load_bars
FIRST_TICK = _S.FIRST_TICK      # 실측 첫 on_tick 평가 시각 ≈ 09:02
KST = _S._KST
as_of = _S._as_of               # date → D 09:02 KST(aware)
_fetch = _S._fetch


def aware(ts: datetime) -> datetime:
    """DB 의 `AT TIME ZONE 'Asia/Seoul'` naive 시각 → as_of 와 같은 tz(전략 hold_days 계산의 aware 비교용)."""
    if KST is not None and ts.tzinfo is None:
        return ts.replace(tzinfo=KST)
    return ts


def load_snapshot(conn, strategy: str, scan_date: date) -> List[Dict]:
    """`screener_snapshots` 한 전략·한 스캔일(순위순)."""
    rows = _fetch(conn, "SELECT stock_code, rank_in_snapshot, score, params_hash, "
                        "(created_at AT TIME ZONE 'Asia/Seoul') FROM screener_snapshots "
                        "WHERE strategy = %s AND scan_date = %s ORDER BY rank_in_snapshot, stock_code",
                  (strategy, scan_date.isoformat()))
    return [dict(code=str(c), rank=int(r) if r is not None else None, score=s, params_hash=h, created_at=ca)
            for c, r, s, h, ca in rows]


def snapshot_strategies(conn, start: date, end: date) -> Dict[str, int]:
    rows = _fetch(conn, "SELECT strategy, count(*) FROM screener_snapshots "
                        "WHERE scan_date BETWEEN %s AND %s GROUP BY strategy",
                  (start.isoformat(), end.isoformat()))
    return {str(s): int(n) for s, n in rows}


def load_trades8(conn, until: date) -> Dict[str, List[Tuple]]:
    """페이퍼 체결 전부(전 전략 · until 포함) → {strategy: [(id, code, action, price, ts_kst, reason,
    buy_record_id, quantity, target_profit_rate, stop_loss_rate)]}. `is_test=true` 가 정상이라 거르지 않는다."""
    rows = _fetch(conn, "SELECT COALESCE(strategy, ''), id, stock_code, action, price::float8, "
                        "(timestamp AT TIME ZONE 'Asia/Seoul'), reason, buy_record_id, quantity, "
                        "target_profit_rate::float8, stop_loss_rate::float8 "
                        "FROM virtual_trading_records "
                        "WHERE (timestamp AT TIME ZONE 'Asia/Seoul')::date <= %s ORDER BY timestamp, id",
                  (until.isoformat(),))
    out: Dict[str, List[Tuple]] = {}
    for strat, *rest in rows:
        out.setdefault(str(strat), []).append(tuple(rest))
    return out


_MINUTE_REPO = None


def minute_bars(code: str, d: date) -> List[Tuple[str, Bar]]:
    """D3′ 용 하루 분봉 — 라이브 `PriceRepository.get_minute_prices`(db/repositories/price.py:188-229 · `minute_candles`
    · 키 `trade_date` · SELECT 만)를 그대로 부른다 → [(분봉 시작 HH:MM:SS, Bar)]. 그날이 아닌 행(팬텀 세션)은 버린다.
    ⚠️ `minute_candles` 는 그날 선정 종목 위주로 ~300종목/일만 있다 — 없으면 [] (D3′ 상태 `no_minute_data`)."""
    global _MINUTE_REPO
    if _MINUTE_REPO is None:
        _MINUTE_REPO = _S._price_mod.PriceRepository()
    df = _MINUTE_REPO.get_minute_prices(code, d.strftime("%Y%m%d"))
    if df is None or df.empty:
        return []
    out: List[Tuple[str, Bar]] = []
    for ts, o, h, lo, c in zip(pd.to_datetime(df["datetime"]), df["open"], df["high"], df["low"], df["close"]):
        if ts.date() != d or any(pd.isna(x) for x in (o, h, lo, c)):
            continue
        out.append((ts.strftime("%H:%M:%S"), Bar(d, float(o), float(h), float(lo), float(c))))
    return out


class WindowCache:
    """`(code, D)` → 라이브가 D 첫 틱에 넘겼을 일봉 창(마지막 봉 = D-1). `cap_skip_ledger.sources.live_daily_window`."""

    def __init__(self, repo=None):
        self._repo = repo if repo is not None else _S._price_mod.PriceRepository()
        self._cache: Dict[Tuple[str, date], Tuple[Optional[pd.DataFrame], Dict]] = {}

    def get(self, code: str, d: date) -> Tuple[Optional[pd.DataFrame], Dict]:
        key = (code, d)
        if key not in self._cache:
            self._cache[key] = _S.live_daily_window(code, d, repo=self._repo)
        return self._cache[key]

    def __len__(self) -> int:
        return len(self._cache)
