"""진입일 분봉 적재 + 데이터 가드 11(EXPERT_SYSTEM §4-1) — DB 는 SELECT 만.

가드(근거 = EXPERT_SYSTEM §4-1 Q번호)
  Q3·#7 달력 = `daily_prices` 의사티커 `KOSPI` 날짜만(replayer SSOT `CALENDAR_TICKER`). 달력에 없는 trade_date
        (유령 휴장일 20일 · 직전 거래일 복사본)는 **읽지 않는다**(쿼리에서 빼고 `excluded=phantom_day`).
        ⚠ «daily_prices 의 아무 날짜»는 2026-01-11(일) 같은 낱행이 섞여 있어 쓰지 않는다(11-10 실측 394 vs 393일).
  Q5   `time` = 'HHMMSS' 6자리 · 분 «시작» → 행 0..379 = 09:00..15:19 · '153000' → 행 380 · 그 밖은 `off_grid_rows`.
  Q6   15:30 봉 유무 = `has_1530`(2026-09 부터 대부분 없음 → 거래량 분모는 일봉).
  Q8   `amount` = 당일 «누적» 거래대금 → `vwap()` = amount_t ÷ Σvolume_≤t.
  Q10  0가격(open·high·low·close ≤ 0) 행이 하나라도 있으면 code-day 제외(`zero_price`) · volume=0 봉 = 거래 없는 분
        (빈 분과 같이 직전 종가로 평평하게 · `zero_volume_minutes`).
  §3-5 빈 분 = 직전 종가로 평평하게 채움(volume 0 · amount 누적값 유지) · `filled_minutes` · 첫 거래 전은 NaN.
  —    일봉 시가 vs 09:00 봉 시가 차 > 2% = `open_gap_flag`(분할 뒤 조정 일봉 등) · 09:00 봉 없으면 None/False.
  Q4·G5 `market_gap_day` = **시장 수준 사건**(`mark_market_gap_days`): 같은 날 같은 시장(KOSPI/KOSDAQ) 종목의 ≥50% 가
        **같은 20분 이상 창**에 봉(행)이 없음 → 그 날·시장 플래그(주 분석 제외는 2단계 run 몫). 🔒 분모 = 그날
        `minute_candles` **전 종목**(번들 후보 아님 · `fetch_market_gap_rows` SELECT 1개 · 리뷰 B2) · 시장 구분 원천 =
        `stock_market`(`load_market_of` · 현행 스냅샷 · PIT 아님) · `market_of` 필수(None → ValueError).
        11-10 실측: 11-06 KOSPI 243/243(09:04~ 창) · KOSDAQ 2/367 · 10-13 KOSPI 1/269 · KOSDAQ 5/542.
        종목 단위 최장 빈 구간(09:00 앞·15:19 뒤 경계 포함 · 행 존재 기준) = `long_gap_minutes`·`long_gap`(≥20분)
        = **정보 플래그만(제외 아님)** — 그날 미래 분까지 보고 로트를 빼는 룩어헤드성 선택을 막는다(리뷰 M3).
  Q7·#9 사용 code-day 체크섬 (행수 · Σvolume · Σclose) — 원행 기준 · `checksum_digest()` = sha256(run_meta 용).
  —    통째 결측 = 분봉 0행 → `excluded=no_minute_data`(일봉 대체 진입은 2단계).
전일 거래량 = 전 거래일 일봉 원값 × adj(전일)/adj(당일) — 진입일 주식 단위(분봉 volume 은 원값)로 맞춘다.
  🔒 adj NULL(또는 ≤0) = **1.0**(레포 읽기 규약 `COALESCE(adj_factor, 1)` · `db/repositories/price.py` · 관리자 재결정
  11-10) · `adj_null_prev`·`adj_null_entry` = 전일(D)·진입일(D+1) adj 가 NULL 이었음(초안 §8 열 · 정보 카운트만 ·
  판단 불가 사유 아님 · NULL 은 2026-07 부터 대부분) · `adj_changed` = 1.0 대체 뒤 adj(전일) ≠ adj(당일)(정보).
"""
from __future__ import annotations

import hashlib
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .engine import F_AMT, F_CLOSE, F_OPEN, F_VOL, IDX_1530, N_CONT, N_FIELDS, N_SLOTS, time_to_idx

Key = Tuple[str, date]
RawRow = Tuple[str, float, float, float, float, float, float]   # (time, open, high, low, close, volume, amount)

OPEN_GAP_LIMIT = 0.02
GAP_MINUTES = 20
MARKET_GAP_FRAC = 0.5
MARKET_UNKNOWN = "UNKNOWN"
BATCH = 1000

EXCL_PHANTOM = "phantom_day"
EXCL_NO_MINUTE = "no_minute_data"
EXCL_ZERO_PRICE = "zero_price"


@dataclass
class DayMeta:
    code: str
    day: date
    n_rows: int = 0
    has_1530: bool = False
    filled_minutes: int = 0
    zero_volume_minutes: int = 0
    first_trade_idx: Optional[int] = None
    long_gap_minutes: int = 0            # 종목 단위 최장 빈 구간(분) — 정보만(초안 G5)
    long_gap: bool = False               # long_gap_minutes ≥ 20 — 정보만(제외 아님 · 초안 G5)
    market_gap_day: bool = False         # 시장 수준 사건(`mark_market_gap_days`) — 제외는 2단계
    off_grid_rows: int = 0
    dup_rows: int = 0
    daily_open: Optional[float] = None
    open_gap_pct: Optional[float] = None
    open_gap_flag: bool = False
    prev_close: Optional[float] = None
    prev_day_volume: Optional[float] = None
    adj_null_prev: bool = False          # 전일(D) adj NULL(1.0 으로 봄) — 정보 카운트만(초안 §8)
    adj_null_entry: bool = False         # 진입일(D+1) adj NULL(1.0 으로 봄) — 정보 카운트만(초안 §8)
    adj_changed: Optional[bool] = None   # 1.0 대체 뒤 adj(전일) ≠ adj(당일) · 전일 일봉 없으면 None


@dataclass
class MinuteBundle:
    keys: List[Key]
    bars: np.ndarray                     # float32 [n, 381, 6]
    observed: np.ndarray                 # bool [n, 381] — 실제 거래(volume>0) 봉
    meta: List[DayMeta]
    excluded: Dict[Key, str] = field(default_factory=dict)
    checksums: Dict[Key, Tuple[int, float, float]] = field(default_factory=dict)
    unknown_market_codes: int = 0        # stock_market 에 없는 종목 수(UNKNOWN 군 · market_gap_day=False 고정)
    _pos: Dict[Key, int] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._pos = {k: i for i, k in enumerate(self.keys)}

    def index(self, key: Key) -> int:
        """키 → 행 번호(dict · 없으면 KeyError)."""
        return self._pos[key]


def _bad_price(r: RawRow) -> bool:
    return any(not (v is not None and float(v) > 0) for v in r[1:5])


def assemble_day(rows: Sequence[RawRow]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], DayMeta, str]:
    """원행(분봉 idx 순) → (bars float64 [381,6], observed bool [381], 통계, 제외 사유 '')."""
    meta = DayMeta(code="", day=date.min, n_rows=len(rows))
    if not rows:
        return None, None, meta, EXCL_NO_MINUTE
    if any(_bad_price(r) for r in rows):
        return None, None, meta, EXCL_ZERO_PRICE
    bars = np.full((N_SLOTS, N_FIELDS), np.nan)
    present = np.zeros(N_SLOTS, dtype=bool)
    for r in rows:
        i = time_to_idx(r[0])
        if i is None:
            meta.off_grid_rows += 1
            continue
        if present[i]:
            meta.dup_rows += 1          # 같은 분 두 행 — 뒤(idx 큰) 행이 이긴다
        bars[i] = [float(x) if x is not None else np.nan for x in r[1:7]]
        present[i] = True
    meta.has_1530 = bool(present[IDX_1530])
    observed = present & (np.nan_to_num(bars[:, F_VOL]) > 0)

    rows_at = np.flatnonzero(present[:N_CONT])
    edges = np.concatenate(([-1], rows_at, [N_CONT]))
    meta.long_gap_minutes = int((np.diff(edges) - 1).max())
    meta.long_gap = meta.long_gap_minutes >= GAP_MINUTES

    last_close: Optional[float] = None
    last_amt = np.nan
    for i in range(N_CONT):
        if observed[i]:
            last_close = float(bars[i, F_CLOSE])
            if np.isfinite(bars[i, F_AMT]):
                last_amt = float(bars[i, F_AMT])
            if meta.first_trade_idx is None:
                meta.first_trade_idx = i
            continue
        if last_close is None:
            bars[i] = np.nan            # 첫 거래 전 = 가격 없음
            continue
        if present[i]:
            meta.zero_volume_minutes += 1
        else:
            meta.filled_minutes += 1
        bars[i] = [last_close, last_close, last_close, last_close, 0.0, last_amt]
    return bars, observed, meta, ""


def vwap(bars: np.ndarray) -> np.ndarray:
    """VWAP_t = amount_t(당일 누적 대금) ÷ Σvolume_≤t — 누적 거래량 0 이면 NaN. 15:30 행 포함 [381]."""
    vol = np.nan_to_num(np.asarray(bars[:, F_VOL], dtype=np.float64))
    cum = np.cumsum(vol)
    amt = np.asarray(bars[:, F_AMT], dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(cum > 0, amt / cum, np.nan)
    return out


def raw_checksum(rows: Sequence[RawRow]) -> Tuple[int, float, float]:
    """(행수 · Σvolume · Σclose) — 원행 그대로(빈 분 채우기 전 · off-grid 포함)."""
    sv = float(sum(float(r[5] or 0) for r in rows))
    sc = float(sum(float(r[4] or 0) for r in rows))
    return len(rows), round(sv, 4), round(sc, 4)


def checksum_digest(checksums: Dict[Key, Tuple[int, float, float]]) -> str:
    """사용 code-day 체크섬 전체의 sha256(키 정렬) — 실행 전후 차분 = 0 이어야 한다."""
    h = hashlib.sha256()
    for (c, d) in sorted(checksums):
        n, sv, sc = checksums[(c, d)]
        h.update(f"{c}|{d.isoformat()}|{n}|{sv:.4f}|{sc:.4f}\n".encode())
    return h.hexdigest()


def apply_daily(meta: DayMeta, bars: np.ndarray, daily: Dict[Key, Tuple[Any, ...]], prev_day: Optional[date]) -> None:
    """일봉 기반 가드·문맥 — 09:00 봉 시가 차 플래그 · 전일 종가 · 전일 거래량(진입일 주식 단위)."""
    cur = daily.get((meta.code, meta.day))
    if cur is not None and cur[0] is not None and float(cur[0]) > 0:
        meta.daily_open = float(cur[0])
        o900 = float(bars[0, F_OPEN])
        if np.isfinite(o900) and o900 > 0:
            meta.open_gap_pct = (o900 / meta.daily_open - 1.0) * 100.0
            meta.open_gap_flag = abs(o900 / meta.daily_open - 1.0) > OPEN_GAP_LIMIT
    prv = daily.get((meta.code, prev_day)) if prev_day is not None else None
    if prv is not None:
        meta.prev_close = float(prv[1]) if prv[1] is not None else None
        raw_prev = prv[3]
        raw_cur = cur[3] if cur is not None else None
        meta.adj_null_prev, meta.adj_null_entry = raw_prev is None, raw_cur is None
        adj_prev = float(raw_prev) if raw_prev is not None and float(raw_prev) > 0 else 1.0   # COALESCE(adj, 1)
        adj_cur = float(raw_cur) if raw_cur is not None and float(raw_cur) > 0 else 1.0
        meta.adj_changed = adj_prev != adj_cur
        if prv[2] is not None:
            meta.prev_day_volume = float(prv[2]) * adj_prev / adj_cur


def market_gap_stats(rows: Iterable[Tuple[Any, Any, Any]], market_of: Mapping[str, str]
                     ) -> Dict[Tuple[date, str], Tuple[int, int]]:
    """(trade_date 'YYYYMMDD', code, [[lo, hi], …] 20분+ 빈 구간 행 번호) → (날짜, 시장) 마다
    (같은 20분 창이 빈 종목 수의 최댓값, 그날 분봉 종목 수). 순수 함수 — `fetch_market_gap_rows` 결과를 받는다."""
    totals: Dict[Tuple[date, str], int] = {}
    cover: Dict[Tuple[date, str], np.ndarray] = {}
    n_starts = N_CONT - GAP_MINUTES + 1                   # 창 시작 s = 0..360
    for td, code, gaps in rows:
        s = str(td)
        g = (date(int(s[:4]), int(s[4:6]), int(s[6:8])), market_of.get(str(code)) or MARKET_UNKNOWN)
        totals[g] = totals.get(g, 0) + 1
        for lo, hi in gaps or []:
            a, b = int(lo), int(hi) - GAP_MINUTES + 1     # [s, s+20) ⊂ [lo, hi] ⇔ lo ≤ s ≤ hi − 19
            if b >= a:
                diff = cover.setdefault(g, np.zeros(n_starts + 1, np.int64))
                diff[a] += 1
                diff[b + 1] -= 1
    return {g: (int(np.cumsum(cover[g])[:-1].max()) if g in cover else 0, n) for g, n in totals.items()}


def mark_market_gap_days(metas: Sequence[DayMeta], stats: Mapping[Tuple[date, str], Tuple[int, int]],
                         market_of: Optional[Mapping[str, str]]) -> Dict[Tuple[date, str], bool]:
    """G5 시장 수준 공백 — 그날 그 시장 **분봉 전 종목**(분모 · `market_gap_stats`)의 ≥50% 가 같은 20분 창에 봉 없음
    → 참 · `meta.market_gap_day` 설정. `market_of` 필수(None 이면 ValueError · 원천 = `load_market_of`)."""
    if market_of is None:
        raise ValueError("market_of 필수 — 시장 구분 없이 KOSPI·KOSDAQ 를 한 군으로 섞지 않는다(리뷰 B2)")
    # UNKNOWN(stock_market 에 없는 코드) 군 = 소집단이라 늘 False(3차 리뷰 U1) · 건수는 `unknown_market_codes`
    flags = {g: g[1] != MARKET_UNKNOWN and n > 0 and k >= MARKET_GAP_FRAC * n for g, (k, n) in stats.items()}
    for m in metas:
        m.market_gap_day = flags.get((m.day, market_of.get(m.code) or MARKET_UNKNOWN), False)
    return flags


# ── DB(SELECT 만) ─────────────────────────────────────────────────────────

def connect():
    """읽기 전용 연결 — `cap_skip_ledger/bootstrap.py`(PGOPTIONS read-only · resolver DB명)를 먼저 import."""
    from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401
    import psycopg2

    from backtest.concept_axes.replayer.loader import dsn
    conn = psycopg2.connect(**dsn())
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _fetch(conn, sql: str, args: Sequence = ()) -> List[Tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def load_market_of(conn) -> Dict[str, str]:
    """시장 구분 원천 = `stock_market`(code → 'KOSPI'|'KOSDAQ') · ⚠ 현행 스냅샷 1장
    (PIT 아님 · replayer `load_market_labels` 와 같은 표). 없는 코드 = 'UNKNOWN' 군."""
    return {str(c): str(m) for c, m in _fetch(conn, "SELECT stock_code, market FROM stock_market")}


GAP_SQL = """
WITH m AS (
  SELECT trade_date, stock_code, substr(time, 1, 2)::int * 60 + substr(time, 3, 2)::int - 540 AS i
  FROM minute_candles
  WHERE trade_date = ANY(%s) AND length(time) = 6 AND time >= '090000' AND time <= '151900'
    AND substr(time, 5, 2) = '00'
), s AS (
  SELECT trade_date, stock_code, i FROM m
  UNION ALL SELECT DISTINCT trade_date, stock_code, -1 FROM m
  UNION ALL SELECT DISTINCT trade_date, stock_code, 380 FROM m
), g AS (
  SELECT trade_date, stock_code, i, LAG(i) OVER (PARTITION BY trade_date, stock_code ORDER BY i) AS p FROM s
)
SELECT trade_date, stock_code, array_agg(ARRAY[p + 1, i - 1] ORDER BY i) FILTER (WHERE i - p - 1 >= %s)
FROM g GROUP BY trade_date, stock_code
"""
GAP_DAYS_BATCH = 20


def fetch_market_gap_rows(conn, days: Iterable[date]) -> List[Tuple[Any, Any, Any]]:
    """그날 `minute_candles` **전 종목**의 20분+ 빈 구간(행 번호 [lo, hi] · 09:00 앞·15:19 뒤 경계 포함 · 행 존재 기준)
    — 종목당 1행(빈 구간 없으면 None). SELECT 1개(날짜 묶음 단위). 11-10 실측 3일 ≈ 12초."""
    ds = sorted({d.strftime("%Y%m%d") for d in days})
    out: List[Tuple[Any, Any, Any]] = []
    for i in range(0, len(ds), GAP_DAYS_BATCH):
        out.extend(_fetch(conn, GAP_SQL, (ds[i: i + GAP_DAYS_BATCH], GAP_MINUTES)))
    return out


def load_calendar(conn, start: date, end: date) -> List[date]:
    from backtest.concept_axes.replayer.loader import CALENDAR_TICKER
    rows = _fetch(conn, "SELECT DISTINCT date FROM daily_prices WHERE stock_code = %s AND date BETWEEN %s AND %s "
                        "ORDER BY date", (CALENDAR_TICKER, start.isoformat(), end.isoformat()))
    return [date.fromisoformat(str(r[0])[:10]) for r in rows]


def _chunks(seq: Sequence[Key], n: int) -> Iterable[Sequence[Key]]:
    for i in range(0, len(seq), n):
        yield seq[i: i + n]


def fetch_minute_rows(conn, keys: Sequence[Key]) -> Dict[Key, List[RawRow]]:
    out: Dict[Key, List[RawRow]] = {k: [] for k in keys}
    for part in _chunks(list(keys), BATCH):
        codes = [c for c, _ in part]
        days = [d.strftime("%Y%m%d") for _, d in part]
        rows = _fetch(conn, "SELECT m.stock_code, m.trade_date, m.time, m.open, m.high, m.low, m.close, m.volume, "
                            "m.amount FROM minute_candles m JOIN unnest(%s::text[], %s::text[]) AS p(c, d) "
                            "ON m.stock_code = p.c AND m.trade_date = p.d ORDER BY m.stock_code, m.trade_date, m.idx",
                      (codes, days))
        for c, td, t, o, h, lo, cl, v, a in rows:
            k = (str(c), date(int(td[:4]), int(td[4:6]), int(td[6:8])))
            out[k].append((str(t), o, h, lo, cl, v, a))
    return out


def fetch_daily(conn, keys: Sequence[Key]) -> Dict[Key, Tuple[Any, ...]]:
    """(code, date) → (open, close, volume 원값, adj_factor)."""
    out: Dict[Key, Tuple[Any, ...]] = {}
    for part in _chunks(list(keys), BATCH):
        rows = _fetch(conn, "SELECT d.stock_code, d.date, d.open, d.close, d.volume, d.adj_factor FROM daily_prices d "
                            "JOIN unnest(%s::text[], %s::text[]) AS p(c, d) ON d.stock_code = p.c AND d.date = p.d",
                      ([c for c, _ in part], [d.isoformat() for _, d in part]))
        for c, ds, o, cl, v, adj in rows:
            out[(str(c), date.fromisoformat(str(ds)[:10]))] = (o, cl, v, adj)
    return out


def load_minute_days(conn, pairs: Iterable[Key], market_of: Mapping[str, str],
                     calendar: Optional[Sequence[date]] = None,
                     gap_rows: Optional[Callable[[Iterable[date]], List[Tuple[Any, Any, Any]]]] = None) -> MinuteBundle:
    """코드·날짜 집합 → `MinuteBundle`(float32 [n,381,6]) · 유령일은 읽지 않는다 · 제외 사유·체크섬 ·
    `market_gap_day`(분모 = 그날 분봉 전 종목 · `market_of` 필수 = `load_market_of(conn)`) 포함.
    `gap_rows(days)` = `fetch_market_gap_rows` 대신 쓸 공급자(2단계 run 의 날짜별 캐시 · 없으면 DB 직접)."""
    if market_of is None:
        raise ValueError("market_of 필수 — load_market_of(conn)")
    keys_all = sorted(set((str(c), d) for c, d in pairs))
    if not keys_all:
        return MinuteBundle([], np.zeros((0, N_SLOTS, N_FIELDS), np.float32), np.zeros((0, N_SLOTS), bool), [])
    if calendar is None:
        # 키는 (code, date) 정렬 — 첫 키 날짜 ≠ 최소 날짜(리뷰 B1) → 전체 최소 날짜에서 30일 앞부터
        calendar = load_calendar(conn, min(d for _, d in keys_all) - timedelta(days=30), max(d for _, d in keys_all))
    cal = sorted(calendar)
    cal_set = set(cal)
    excluded: Dict[Key, str] = {k: EXCL_PHANTOM for k in keys_all if k[1] not in cal_set}
    keys = [k for k in keys_all if k not in excluded]

    def prev_of(d: date) -> Optional[date]:
        i = bisect_left(cal, d)
        return cal[i - 1] if i > 0 else None

    raw = fetch_minute_rows(conn, keys)
    daily_keys = sorted(set(keys) | {(c, p) for c, d in keys for p in [prev_of(d)] if p is not None})
    daily = fetch_daily(conn, daily_keys)

    used: List[Key] = []
    arrs: List[np.ndarray] = []
    obs: List[np.ndarray] = []
    metas: List[DayMeta] = []
    checks: Dict[Key, Tuple[int, float, float]] = {}
    for k in keys:
        bars, observed, meta, why = assemble_day(raw[k])
        if why:
            excluded[k] = why
            continue
        meta.code, meta.day = k
        apply_daily(meta, bars, daily, prev_of(k[1]))
        used.append(k)
        arrs.append(bars.astype(np.float32))
        obs.append(observed)
        metas.append(meta)
        checks[k] = raw_checksum(raw[k])
    days_used = {m.day for m in metas}
    rows_gap = gap_rows(days_used) if gap_rows is not None else fetch_market_gap_rows(conn, days_used)
    mark_market_gap_days(metas, market_gap_stats(rows_gap, market_of), market_of)
    shape = (len(used), N_SLOTS, N_FIELDS)
    unknown = len({m.code for m in metas if not market_of.get(m.code)})
    return MinuteBundle(used, np.stack(arrs) if arrs else np.zeros(shape, np.float32),
                        np.stack(obs) if obs else np.zeros(shape[:2], bool), metas, excluded, checks, unknown)
