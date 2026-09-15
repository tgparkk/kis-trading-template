"""가격·유니버스·배제·지문 로더 — 설계서 §1 · §4-4-b.

🔑 **`volume × COALESCE(adj_factor,1)` 은 여기서 «한 번만»** 적용한다
   (라이브 읽기계층 `db/quant_daily_reader.py::_SELECT_OHLCV` 와 같은 식).
   이후 어디에서도 다시 곱하지 않는다 — 이중조정 금지.
⚠️ 가격(open/high/low/close)에는 `adj_factor` 를 곱하지 않는다(가짜 절벽).
🔴 DB 는 SELECT 전용. DB명은 하드코딩하지 않고 resolver 를 경유한다.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from bisect import bisect_right
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]          # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.constants import resolve_daily_source_db          # noqa: E402

# 설계서 §1-1 — 의사티커 제외(`minervini/run.py:73-74` 승계).
STOCK_ONLY = ("stock_code ~ '^[0-9][0-9A-Z]{5}$' "
              "AND stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')")

# 설계서 §1-3-b — 거래일 달력 SSOT.
CALENDAR_TICKER = "KOSPI"

# 설계서 §1-2-b 5 — ETF/ETN 이름 1차 필터(히트 수를 인쇄한다).
ETF_NAME_RE = re.compile(
    r"KODEX|TIGER|KBSTAR|ARIRANG|HANARO|ACE |PLUS |SOL |RISE |KOSEF|레버리지|인버스|ETN")
REIT_NAME_RE = re.compile(r"리츠")
SPAC_NAME_RE = re.compile(r"스팩")

PRICE_COLS = ("open", "high", "low", "close", "volume")
# §4-4-b 3 — 스냅샷 해시에 들어가는 10컬럼(파생·메타 제외 · `adj_factor` 포함).
HASH_COLS = ("stock_code", "date", "open", "high", "low", "close",
             "volume", "trading_value", "market_cap", "adj_factor")


def dsn() -> Dict[str, Any]:
    """접속 정보. **DB명은 resolver 경유**, 나머지는 라이브와 같은 env 이름·기본값.

    필요한 env = `TIMESCALE_HOST`·`TIMESCALE_PORT`·`TIMESCALE_USER`·`TIMESCALE_PASSWORD`
    (전부 기본값이 있어 `.env` 없이도 로컬에서 동작한다). 앱키·계좌 등 비밀은 쓰지 않는다.
    """
    return dict(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", "5433")),
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
        dbname=resolve_daily_source_db(),
    )


# ────────────────────────────────────────────────────────────────────────────
# §1-2-b — 비주식 상품·우선주 배제 (원장 생성 «전» · 사후 필터 금지)
# ────────────────────────────────────────────────────────────────────────────
def is_preferred(code: str) -> bool:
    """우선주 판별 SSOT = **종목코드 6번째 자리** `[5-9]` ∨ `[K-M]`.

    🔴 `0001A0`·`0007C0`·`0009K0` 같은 **신형 코드 보통주를 배제하면 안 된다**
    — 6번째 자리가 `0` 이므로 이 술어에 걸리지 않는다(§1-2-b 7).
    """
    if not code or len(code) < 6:
        return False
    ch = code[5]
    return ("5" <= ch <= "9") or ("K" <= ch <= "M")


def is_foreign(code: str) -> bool:
    """외국주·외국지주 — `^9`(§1-2-b 3)."""
    return bool(code) and code.startswith("9")


def classify_exclusions(codes: Iterable[str],
                        names: Dict[str, str]) -> Dict[str, Dict[str, bool]]:
    """`{code: {excl_*, name_unknown, excluded}}`.

    🔴 **이름 미상은 배제하지 않는다** — 이름 기반 규칙(리츠·스팩·ETF)이 «작동하지
    않았다»는 표시(`flag_name_unknown`)로 남긴다. 「이름이 없어서 못 걸렀다」와
    「걸러 봤더니 아니었다」를 같은 칸에 넣지 않는다(§1-2-b 6).
    """
    out: Dict[str, Dict[str, bool]] = {}
    for c in codes:
        nm = names.get(c)
        unknown = nm is None
        nm_s = nm or ""
        rec = {
            "excl_pref": is_preferred(c),
            "excl_foreign": is_foreign(c),
            "excl_reit": bool(nm_s) and bool(REIT_NAME_RE.search(nm_s)),
            "excl_spac": bool(nm_s) and bool(SPAC_NAME_RE.search(nm_s)),
            "excl_etf": bool(nm_s) and bool(ETF_NAME_RE.search(nm_s)),
            "name_unknown": unknown,
        }
        rec["excluded"] = any(rec[k] for k in
                              ("excl_pref", "excl_foreign", "excl_reit",
                               "excl_spac", "excl_etf"))
        out[c] = rec
    return out


def exclusion_counts(cls: Dict[str, Dict[str, bool]]) -> Dict[str, int]:
    keys = ("excl_pref", "excl_reit", "excl_foreign", "excl_spac", "excl_etf",
            "name_unknown")
    return {"n_" + k: sum(1 for v in cls.values() if v[k]) for k in keys}


# ────────────────────────────────────────────────────────────────────────────
# 가격 로드 · 정규화
# ────────────────────────────────────────────────────────────────────────────
def normalize_prices(raw: pd.DataFrame) -> pd.DataFrame:
    """`date` text 손상값 coerce·dropna + 비양수 종가 제거 + OHL 보정.

    ⚠️ 리뷰 L-1 — **이 위생 처리는 라이브 읽기 계층에 «없다» · 설계서 근거도 없다.**
       (예전 도킹스트링의 `§0.2` 인용은 **설계서에 없는 절**이었다 — 삭제했다.)
       재현기가 임의로 넣은 방어이므로 «몇 행을 건드렸는지» 를 세서
       `df.attrs["normalize_counts"]` 에 남기고 `ledger_diag.csv` · 리포트에 인쇄한다.
       🔴 라이브가 안 하는 보정이므로 그 건수가 0 이 아니면 그만큼이 «재현기 고유의 차» 이다.
    """
    n_raw = len(raw)
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    df = df.dropna(subset=["date"])
    for c in PRICE_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("adj_factor", "market_cap", "volatility_20d"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    n_after_date = len(df)
    bad_close = df["close"].isna() | (df["close"] <= 0)
    n_dropped_close = int(bad_close.sum())
    df = df[~bad_close].copy()
    n_patched_ohl = 0
    for c in ("open", "high", "low"):
        if c in df.columns:
            m = df[c].isna() | (df[c] <= 0)
            n_patched_ohl += int(m.sum())
            df.loc[m, c] = df.loc[m, "close"]
    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0).clip(lower=0)
    out = (df.sort_values(["stock_code", "date"], kind="mergesort")
             .reset_index(drop=True))
    out.attrs["normalize_counts"] = {
        "n_rows_raw": int(n_raw),
        "n_dropped_bad_date": int(n_raw - n_after_date),
        "n_dropped_close": n_dropped_close,
        "n_patched_ohl": n_patched_ohl,
    }
    return out


def load_prices(conn, start: str, end: str) -> pd.DataFrame:
    """`start`~`end` 일봉(의사티커 제외). `volume` 은 **이미 adj 적용된** 값이다."""
    # 리뷰 L-6 — 날짜는 **파라미터 바인딩**(`STOCK_ONLY` 만 상수 조각이다).
    df = pd.read_sql("""
        SELECT stock_code, date, open, high, low, close,
               (volume * COALESCE(adj_factor, 1))::double precision AS volume,
               adj_factor, market_cap, volatility_20d
        FROM daily_prices
        WHERE {stock_only} AND date BETWEEN %s AND %s
        ORDER BY stock_code, date
    """.format(stock_only=STOCK_ONLY), conn, params=(start, end))
    return normalize_prices(df)


def load_trading_calendar(conn, start: str, end: str) -> List[pd.Timestamp]:
    """거래일 달력 SSOT = `stock_code='KOSPI'` 행(§1-3-b). 종목행을 쓰지 않는다."""
    df = pd.read_sql("""
        SELECT DISTINCT date FROM daily_prices
        WHERE stock_code = %s AND date BETWEEN %s AND %s
        ORDER BY date
    """, conn, params=(CALENDAR_TICKER, start, end))
    d = pd.to_datetime(df["date"], format="mixed", errors="coerce").dropna()
    return sorted(pd.Series(d).unique().tolist())


def trading_calendar_from_frame(px: pd.DataFrame) -> List[pd.Timestamp]:
    """이미 로드된 프레임에서 달력을 뽑는다(테스트·오프라인용)."""
    m = px["stock_code"] == CALENDAR_TICKER
    d = pd.to_datetime(px.loc[m, "date"], errors="coerce").dropna()
    return sorted(pd.Series(d).unique().tolist())


def load_stock_names(conn) -> Dict[str, str]:
    df = pd.read_sql("SELECT stock_code, stock_name FROM stock_info", conn)
    return {str(c): str(n) for c, n in zip(df["stock_code"], df["stock_name"])
            if n is not None}


def load_market_labels(conn) -> Dict[str, str]:
    """⚠️ `stock_market` 은 **현행 스냅샷 1장** — PIT 가 아니다(§1-4). 인쇄·층화 전용."""
    df = pd.read_sql("SELECT stock_code, market FROM stock_market", conn)
    return {str(c): str(m) for c, m in zip(df["stock_code"], df["market"])}


def load_corp_events(conn) -> Dict[Tuple[str, pd.Timestamp], str]:
    """`(code, event_date) -> event_type` — bonus_issue·split·rights_issue 만.

    ⚠️ 2026-06 27 → 07 219 로 **6배 점프**(수집 변경)라 2024~2025 에서는 «안 걸린다».
    그래서 `flag_cliff`(데이터 주도)와 **다른 칸**으로 남긴다(§8-10-b).
    """
    df = pd.read_sql("""
        SELECT stock_code, event_type, event_date FROM corp_events
        WHERE event_type IN ('bonus_issue','split','rights_issue')
    """, conn)
    d = pd.to_datetime(df["event_date"], errors="coerce")
    return {(str(c), pd.Timestamp(t)): str(e)
            for c, e, t in zip(df["stock_code"], df["event_type"], d)
            if pd.notna(t)}


# ────────────────────────────────────────────────────────────────────────────
# §1-2 — 유니버스 (라이브 `get_universe_snapshot` 의 «폴백»까지 재현)
# ────────────────────────────────────────────────────────────────────────────
def build_universe(px: pd.DataFrame) -> Dict[pd.Timestamp, Dict[str, Tuple[float, float]]]:
    """`{date: {code: (market_cap, trading_value)}}`.

    `market_cap IS NOT NULL` 행만 담는다 — 라이브 SQL 과 같은 조건이다. `trading_value`
    는 **저장 컬럼을 쓰지 않고** `close × (volume × COALESCE(adj_factor,1))` 로 계산한다
    (`quant_daily_reader.py:90-92`). `volume` 은 로더에서 이미 adj 적용됐다.
    """
    if "market_cap" not in px.columns:
        raise KeyError("market_cap 컬럼이 없다")
    m = px["market_cap"].notna()
    sub = px.loc[m, ["date", "stock_code", "market_cap", "close", "volume"]]
    tv = (sub["close"].astype(float) * sub["volume"].astype(float)).to_numpy()
    out: Dict[pd.Timestamp, Dict[str, Tuple[float, float]]] = {}
    for d, c, mc, t in zip(sub["date"].to_numpy(), sub["stock_code"].to_numpy(),
                           sub["market_cap"].to_numpy(), tv):
        out.setdefault(pd.Timestamp(d), {})[str(c)] = (
            float(mc) if mc == mc else 0.0, float(t))
    return out


def universe_snapshot(uni: Dict[pd.Timestamp, Dict[str, Tuple[float, float]]],
                      scan_date) -> Dict[str, Any]:
    """🔴 정확매칭이 아니라 **`date = max(date <= scan_date)` 폴백**(§1-2 · C2).

    당일 퀀트 적재가 안 끝났으면 라이브도 **직전 거래일 유니버스**를 쓴다.
    """
    keys = sorted(uni)
    d = pd.Timestamp(scan_date)
    i = bisect_right(keys, d) - 1
    if i < 0:
        return {"eff_date": None, "rows": {}}
    return {"eff_date": keys[i], "rows": uni[keys[i]]}


# ────────────────────────────────────────────────────────────────────────────
# §4-4-b — 스냅샷 지문 (행별 md5 → 종목별 md5 → 전체 SHA-256)
# ────────────────────────────────────────────────────────────────────────────
_HASH_SQL = r"""
SELECT stock_code,
       md5(string_agg(row_md5, '' ORDER BY d)) AS stock_md5,
       count(*) AS n
FROM (
  SELECT stock_code, date AS d,
         md5(
           coalesce(stock_code,   E'\\N') || '|' ||
           coalesce(date::text,   E'\\N') || '|' ||
           coalesce(open::text,   E'\\N') || '|' ||
           coalesce(high::text,   E'\\N') || '|' ||
           coalesce(low::text,    E'\\N') || '|' ||
           coalesce(close::text,  E'\\N') || '|' ||
           coalesce(volume::text, E'\\N') || '|' ||
           coalesce(trading_value::text, E'\\N') || '|' ||
           coalesce(market_cap::text,    E'\\N') || '|' ||
           coalesce(adj_factor::text,    E'\\N')
         ) AS row_md5
  FROM daily_prices
  WHERE {stock_only} AND date BETWEEN %s AND %s
) t
GROUP BY stock_code
ORDER BY stock_code
"""


def db_fingerprint(conn, start: str, end: str) -> Dict[str, Any]:
    """§4-4-b — 배제 «전» 전 종목행의 지문.

    🔑 행별 `md5` → 종목별 `md5` 는 **불일치를 종목 단위로 좁히는 장치**이고,
    전체 지문은 `SHA-256` 으로 뜬다. **한쪽만 남기면 「어디가 달라졌나」를 못 묻는다.**
    🔴 `created_at`·`updated_at` 은 해시에서 제외 — 판별력이 0 이다.
    🔴 `returns_*`·`volatility_20d` 는 파생이라 제외 — 별도 일관성 검사로 뺀다.
    🔴 **스냅샷 동결 «이전»에 일어난 값 변경은 어떤 컬럼으로도 판별할 수 없다.**
    """
    q = _HASH_SQL.format(stock_only=STOCK_ONLY)
    df = pd.read_sql(q, conn, params=(start, end))
    per_stock = {str(c): str(h) for c, h in zip(df["stock_code"], df["stock_md5"])}
    blob = "".join("{}:{};".format(c, per_stock[c]) for c in sorted(per_stock))
    return {
        "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "md5": hashlib.md5(blob.encode("utf-8")).hexdigest(),
        "n_stocks": int(len(per_stock)),
        "n_rows": int(df["n"].sum()) if len(df) else 0,
        "per_stock": per_stock,
        "cols": list(HASH_COLS),
        "window": "{}..{}".format(start, end),
    }
