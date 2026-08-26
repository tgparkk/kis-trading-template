# -*- coding: utf-8 -*-
"""TT 게이트 반사실 원장 — 사전등록 `PREREG_TT_COUNTERFACTUAL.md` 실행부.

매 거래일 **D**(= 진입일)에 대해 **D-1 일봉**으로 minervini 스캔을 «라이브 스크리너 코드
그대로» 재현하고, 네 갈래 집합의 반사실 성과를 원장 CSV 에 1일 1블록으로 적재한다.

    U = dryup 통과 전체            (arm 으로는 쓰지 않는다 — P ∪ X 가 U 다)
    P = dryup ∧ TT 통과            (`on` 이 사는 것)
    X = U − P                      (`on` 이 «버린» 것 = 반사실의 핵심)
    R = U 에서 무작위 3종목, 시드 0..19  (귀무 — 「고르는 행위」 자체)
    L = 그날 라이브가 실제로 산 것   (참고 arm · `virtual_trading_records`)

🔴 **라이브 코드는 «읽기»만 한다.** 룰을 다시 구현하지 않는다 — dryup·TT·RS 백분위·
   유니버스·불가능봉 가드는 전부 `MinerviniVolumeDryupScreenerAdapter.scan()` 이 돌린다.
   이 파일이 하는 일은 (a) 그 결과를 `tt_filter_mode="shadow"` 로 «전부» 받아내고
   (b) 사전등록이 정한 반사실 성과식을 적용해 CSV 에 쓰는 것뿐이다.
   (2026-08-25 교훈: 룰이 두 벌이면 정합 논의가 헛돈다.)

🔑 **U 를 통째로 받는 방법.** `scan()` 은 `max_candidates` 로 잘린 상위만 돌려주고
   `mode="on"` 이면 TT 탈락을 버린다. 그래서 **`tt_filter_mode="shadow"` +
   `max_candidates` 무력화**로 부른다. 그러면 반환 `CandidateStock` 리스트가
   그대로 U 이고, 각 원소의 `reason` 끝에 `screener.py:match()` 가 찍은 `tt=0|1`
   이 붙어 있어 P/X 가 «라이브가 판정한 그 값»으로 갈린다. 룰 재평가 없음.

🔑 **유니버스**. `scan()` 내부의 `_load_universe()`+`base_filter()` 경로가 곧
   `backtest/screener_universe.load_screener_universe()` 가 감싸는 그 경로다
   (`strategies/_rule_screener_base.py:_load_universe` ↔ `screener_universe.py:65`).
   따로 부르면 같은 스냅샷을 두 번 조회할 뿐이라 `scan()` 한 경로로 통일한다.

🔴 **DB 는 SELECT 만. KIS API 0. 라이브 로그 파일에 쓰지 않는다**(아래 NullHandler 선주입).

CLI
---
    python run_ledger.py --from 2026-08-18 --to 2026-08-26      # 소급 적재
    python run_ledger.py --date 2026-08-26                      # 하루
    python run_ledger.py --date 2026-08-26 --dry-run            # DB 읽기만, 파일 0
    python run_ledger.py --summary                              # 집계만 인쇄
"""
from __future__ import annotations

import argparse
import csv
import glob
import logging
import os
import random
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # cp949 콘솔에서 '·'·이모지가 UnicodeEncodeError 를 내는 것을 막는다
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
except Exception:  # noqa: BLE001 — 구버전/리다이렉트 환경
    pass

BASE = Path(__file__).resolve().parent            # …/minervini/tt_counterfactual
ROOT = BASE.parents[3]                            # …/RoboTrader_template
sys.path.insert(0, str(ROOT))

# ── .env(있으면) → setdefault. 클린 체크아웃·워크트리엔 없어도 되고, 그 경우
#    아래 `_dsn()` 이 TIMESCALE_* env 와 그 기본값으로 떨어진다. -----------------
_ENVF = ROOT / ".env"
if _ENVF.exists():
    for _line in _ENVF.read_text(encoding="utf-8", errors="ignore").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# 🔴 라이브 로그 파일을 열지 않는다. `utils/logger.py` 의 공유 파일 핸들러는 첫
#    `setup_logger()` 호출 때 `logs/trading_YYYYMMDD.log` 를 RotatingFileHandler 로
#    «연다» — 봇이 도는 중에 연구 스크립트가 그 파일을 rotate 하면 라이브 로그가
#    깨진다. 핸들러 슬롯을 미리 NullHandler 로 채워 생성 분기를 통째로 건너뛴다
#    (`utils/logger.py:56` 의 `if _shared_file_handler is None:`).
import utils.logger as _utils_logger  # noqa: E402
_utils_logger._shared_file_handler = logging.NullHandler()

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")
logging.disable(logging.INFO)   # INFO 이하만 죽인다 — WARNING/ERROR 는 봐야 한다

import pandas as pd     # noqa: E402
import psycopg2         # noqa: E402

from config.constants import resolve_daily_source_db, resolve_minute_source_db  # noqa: E402
from db.quant_daily_reader import QuantDailyReader                              # noqa: E402
from strategies.minervini_volume_dryup.screener import (                        # noqa: E402
    MinerviniVolumeDryupScreenerAdapter,
)

# ────────────────────────────────────────────────────────────────────────────
# 사전등록 동결값 — **결과를 보고 바꾸지 않는다.**
# ────────────────────────────────────────────────────────────────────────────
STRATEGY = "minervini_volume_dryup"
ENTRY_TIME = "090500"          # D 09:05 분봉 «종가»
SL_PCT = 0.08                  # low ≤ entry×0.92 → 체결 entry×0.92
TP_PCT = 0.12                  # high ≥ entry×1.12 → 체결 entry×1.12
MAX_HOLD = 20                  # 거래일. 경과 시 그 봉 종가
COST_ROUND_TRIP = 0.0021       # 왕복 0.21%p
BUDGET = 3_333_333             # 금액가중용 균등 배분(정수 주수로 내림)
N_SEEDS = 20                   # R 시드 0..19
R_PICK = 3                     # R 은 U 에서 3종목
_HUGE = 10 ** 9                # max_candidates 무력화용

LEDGER_COLS = [
    "date", "scan_date", "arm", "seed", "code", "tt",
    "entry_price", "entry_src", "entry_ts",
    "exit_date", "exit_price", "exit_reason", "bars_held", "is_open",
    "ret_gross", "ret_net", "qty", "notional",
    "score", "prev_close",
    "n_dry", "n_tt", "log_dry", "log_tt", "log_final", "repro_ok",
    "run_ts",
]
_KEY = ("date", "code", "arm", "seed")

# `TT게이트 … dryup 84 · TT통과 1 · 최종후보 20` — 가운뎃점은 U+00B7.
_GATE_RE = re.compile(r"dryup\s+(\d+).{0,4}TT통과\s+(\d+).{0,4}최종후보\s+(\d+)")


# ────────────────────────────────────────────────────────────────────────────
# DB — resolver + TIMESCALE_* env. 읽기 전용.
# ────────────────────────────────────────────────────────────────────────────
def _dsn(dbname: str) -> Dict[str, Any]:
    """`QuantDailyReader._get_pool()` 과 «같은» env 규약(db/quant_daily_reader.py:36)."""
    return dict(
        host=os.getenv("TIMESCALE_HOST", "localhost"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        dbname=dbname,
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    )


def _connect(dbname: str):
    conn = psycopg2.connect(**_dsn(dbname))
    conn.set_session(readonly=True, autocommit=True)   # 쓰기를 «서버가» 막게 한다
    return conn


def _fetch(conn, sql: str, args: Sequence[Any] = ()) -> List[Tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def trading_days(conn, start: date, end: date) -> List[date]:
    """[start, end] 의 거래일. 「완전한 퀀트일」 정의는 유니버스 스냅샷과 동일하게
    `market_cap IS NOT NULL` (db/quant_daily_reader.py:get_universe_snapshot)."""
    rows = _fetch(conn,
                  "SELECT DISTINCT date FROM daily_prices "
                  "WHERE date BETWEEN %s AND %s AND market_cap IS NOT NULL ORDER BY date",
                  (start.isoformat(), end.isoformat()))
    return [date.fromisoformat(str(r[0])) for r in rows]


def prev_trading_day(conn, d: date) -> Optional[date]:
    rows = _fetch(conn,
                  "SELECT max(date) FROM daily_prices "
                  "WHERE date < %s AND market_cap IS NOT NULL", (d.isoformat(),))
    return date.fromisoformat(str(rows[0][0])) if rows and rows[0][0] else None


# ────────────────────────────────────────────────────────────────────────────
# 1. 스캔 재현 — 라이브 어댑터를 그대로 돌린다
# ────────────────────────────────────────────────────────────────────────────
def reproduce_scan(scan_date: date) -> Dict[str, Any]:
    """`scan_date`(=D-1) 일봉으로 라이브 스크리너를 돌려 U 와 TT 판정을 받는다.

    Returns:
        {"rows": [{"code","score","prev_close","tt"}...], "n_dry", "n_tt", "rs_error"}
        `rows` 가 U. `tt=1` 인 부분집합이 P, `tt=0` 이 X.
    """
    ad = MinerviniVolumeDryupScreenerAdapter()
    params = {**ad.default_params(), "tt_filter_mode": "shadow", "max_candidates": _HUGE}
    selected = ad.scan(scan_date, params)
    rows = []
    for c in selected:
        m = re.search(r"tt=([01])", c.reason or "")
        rows.append({
            "code": c.code,
            "score": float(c.score),
            "prev_close": float(c.prev_close),
            # `shadow` 면 match() 가 반드시 tt=0|1 을 찍는다. 못 찾으면 결측(-1)로
            # 남겨 「없는 값을 0 으로 위장」하지 않는다.
            "tt": int(m.group(1)) if m else -1,
        })
    return {
        "rows": rows,
        "n_dry": int(ad._tally.get("n_dry", 0)),
        "n_tt": int(ad._tally.get("n_tt", 0)),
        "rs_error": ad._rs_diag.get("error"),
    }


def parse_log_gate(trade_date: date) -> Optional[Tuple[int, int, int]]:
    """D 아침 09:00 스캔이 찍은 `TT게이트` 줄에서 (dryup, TT통과, 최종후보).

    🔑 스캔은 D 아침에 «D-1» 일봉으로 돈다(SHADOW_LOG.md) ⇒ 진입일 D 의 계기는
       **D 날짜 로그 파일**에 있다. `trading_*.log` 는 부분집합이라 쓰지 않는다.
    """
    pat = str(ROOT / "logs" / f"robotrader_template_{trade_date:%Y%m%d}_*.log")
    hits: List[Tuple[int, int, int]] = []
    for path in sorted(glob.glob(pat)):
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if "TT게이트" not in line:
                    continue
                m = _GATE_RE.search(line)
                if m:
                    hits.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if not hits:
        return None
    if len(hits) > 1:
        print(f"  ⚠️ {trade_date} 로그에 TT게이트 줄이 {len(hits)}개 — 첫 줄(09:00)을 쓴다")
    return hits[0]


# ────────────────────────────────────────────────────────────────────────────
# 2. 가격 — 진입(분봉 09:05) · 청산(일봉)
# ────────────────────────────────────────────────────────────────────────────
def minute_entry_prices(conn_min, d: date, codes: Sequence[str]) -> Dict[str, float]:
    """D 09:05 분봉 종가. 🔴 PK 는 `trade_date`('YYYYMMDD') — `date` 로 묶지 말 것."""
    if not codes:
        return {}
    rows = _fetch(conn_min,
                  "SELECT stock_code, close FROM minute_candles "
                  "WHERE trade_date = %s AND time = %s AND stock_code = ANY(%s)",
                  (f"{d:%Y%m%d}", ENTRY_TIME, list(codes)))
    return {str(c): float(p) for c, p in rows if p is not None and float(p) > 0}


class DailyBars:
    """종목별 일봉 캐시. 로더는 `QuantDailyReader`(resolver 경유).

    🔴 `volume × adj_factor` 는 로더가 «이미» 한다 — 다시 곱하지 않는다. 여기서는
       청산 판정에 OHLC 만 쓰므로 volume 을 아예 읽지 않는다.
    """

    def __init__(self, reader: QuantDailyReader, cap_end: date, days: int = 400) -> None:
        self._reader = reader
        self._cap_end = cap_end
        self._days = days
        self._cache: Dict[str, pd.DataFrame] = {}

    def get(self, code: str) -> pd.DataFrame:
        if code not in self._cache:
            df = self._reader.get_daily_prices(code, end_date=self._cap_end, days=self._days)
            if df is None or df.empty:
                df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            self._cache[code] = df
        return self._cache[code]

    def open_on(self, code: str, d: date) -> Optional[float]:
        df = self.get(code)
        if df.empty:
            return None
        hit = df[df["date"].dt.date == d]
        if hit.empty:
            return None
        v = float(hit.iloc[0]["open"])
        return v if v > 0 else None

    def after(self, code: str, d: date, n: int, include_d: bool) -> pd.DataFrame:
        df = self.get(code)
        if df.empty:
            return df
        mask = (df["date"].dt.date >= d) if include_d else (df["date"].dt.date > d)
        return df[mask].head(n)


def simulate_exit(entry: float, bars: pd.DataFrame) -> Dict[str, Any]:
    """사전등록 §성과: low ≤ entry×(1−SL) → sl · high ≥ entry×(1+TP) → tp ·
    같은 봉에서 둘 다면 **sl 우선** · MAX_HOLD 봉 경과 종가 · 미종료면 open."""
    sl_px, tp_px = entry * (1 - SL_PCT), entry * (1 + TP_PCT)
    for i in range(len(bars)):
        b = bars.iloc[i]
        if float(b["low"]) <= sl_px:
            return dict(exit_date=b["date"].date(), exit_price=sl_px,
                        exit_reason="sl", bars_held=i + 1, is_open=0)
        if float(b["high"]) >= tp_px:
            return dict(exit_date=b["date"].date(), exit_price=tp_px,
                        exit_reason="tp", bars_held=i + 1, is_open=0)
    if len(bars) >= MAX_HOLD:
        b = bars.iloc[MAX_HOLD - 1]
        return dict(exit_date=b["date"].date(), exit_price=float(b["close"]),
                    exit_reason="max_hold", bars_held=MAX_HOLD, is_open=0)
    return dict(exit_date=None, exit_price=None, exit_reason="open",
                bars_held=len(bars), is_open=1)


def live_buys(conn, d: date) -> List[Tuple[str, float, str]]:
    """arm L — 그날 minervini 가 «실제로» 산 것(페이퍼 원장). 가격·시각 그대로."""
    rows = _fetch(conn,
                  "SELECT stock_code, price, (timestamp AT TIME ZONE 'Asia/Seoul') "
                  "FROM virtual_trading_records "
                  "WHERE strategy = %s AND action = 'BUY' "
                  "AND (timestamp AT TIME ZONE 'Asia/Seoul')::date = %s "
                  "ORDER BY timestamp",
                  (STRATEGY, d.isoformat()))
    return [(str(c), float(p), str(t)) for c, p, t in rows if p is not None and float(p) > 0]


# ────────────────────────────────────────────────────────────────────────────
# 3. 하루치 블록
# ────────────────────────────────────────────────────────────────────────────
def build_day(conn, conn_min, bars: DailyBars, d: date, include_entry_day: bool,
              run_ts: str) -> List[Dict[str, Any]]:
    scan_date = prev_trading_day(conn, d)
    if scan_date is None:
        print(f"  ⚠️ {d}: 직전 거래일 없음 — 건너뜀")
        return []

    scan = reproduce_scan(scan_date)
    if scan["rs_error"]:
        print(f"  🔴 {d}: RS 백분위 실패 — TT 전부 False 다: {scan['rs_error']}")
    u_rows = scan["rows"]
    by_code = {r["code"]: r for r in u_rows}
    u_codes = sorted(by_code)
    p_codes = sorted(c for c in u_codes if by_code[c]["tt"] == 1)
    x_codes = sorted(c for c in u_codes if by_code[c]["tt"] == 0)

    gate = parse_log_gate(d)
    if gate is None:
        log_dry = log_tt = log_final = ""
        repro = "no_log"
    else:
        log_dry, log_tt, log_final = gate
        repro = "1" if (log_dry == scan["n_dry"] and log_tt == scan["n_tt"]) else "0"

    lv = live_buys(conn, d)
    print(f"  {d} (scan {scan_date}): U={len(u_codes)} P={len(p_codes)} X={len(x_codes)} "
          f"L={len(lv)} · tally dryup={scan['n_dry']} TT={scan['n_tt']} · "
          f"log={gate} · repro_ok={repro}")

    # 진입가 — 필요한 종목만 한 번에.
    need = set(u_codes) | {c for c, _, _ in lv}
    minute = minute_entry_prices(conn_min, d, sorted(need))

    def _row(arm: str, seed: Any, code: str,
             entry_override: Optional[float] = None,
             entry_src_override: str = "", entry_ts: str = "") -> Dict[str, Any]:
        meta = by_code.get(code, {})
        if entry_override is not None:
            entry, src = entry_override, entry_src_override
        elif code in minute:
            entry, src = minute[code], "minute_0905"
        else:
            op = bars.open_on(code, d)
            entry, src = (op, "daily_open") if op else (None, "none")

        base = dict.fromkeys(LEDGER_COLS, "")
        base.update(
            date=d.isoformat(), scan_date=scan_date.isoformat(), arm=arm,
            seed="" if seed is None else int(seed), code=code,
            tt=meta.get("tt", ""), entry_src=src, entry_ts=entry_ts,
            score=meta.get("score", ""), prev_close=meta.get("prev_close", ""),
            n_dry=scan["n_dry"], n_tt=scan["n_tt"],
            log_dry=log_dry, log_tt=log_tt, log_final=log_final,
            repro_ok=repro, run_ts=run_ts,
        )
        if entry is None:
            # 「진입가를 못 구했다」를 조용히 버리지 않는다 — 행으로 남긴다.
            base.update(exit_reason="no_entry", is_open="", bars_held="")
            return base

        ex = simulate_exit(entry, bars.after(code, d, MAX_HOLD, include_entry_day))
        qty = int(BUDGET // entry)
        if ex["is_open"]:
            rg = rn = ""
        else:
            rg = (ex["exit_price"] - entry) / entry
            rn = rg - COST_ROUND_TRIP
        base.update(
            entry_price=round(entry, 4), qty=qty, notional=round(qty * entry, 2),
            exit_date=ex["exit_date"].isoformat() if ex["exit_date"] else "",
            exit_price="" if ex["exit_price"] is None else round(ex["exit_price"], 4),
            exit_reason=ex["exit_reason"], bars_held=ex["bars_held"], is_open=ex["is_open"],
            ret_gross="" if rg == "" else round(rg, 6),
            ret_net="" if rn == "" else round(rn, 6),
        )
        return base

    out: List[Dict[str, Any]] = []
    out += [_row("P", None, c) for c in p_codes]
    out += [_row("X", None, c) for c in x_codes]
    for seed in range(N_SEEDS):
        rng = random.Random(seed)
        pick = rng.sample(u_codes, min(R_PICK, len(u_codes))) if u_codes else []
        out += [_row("R", seed, c) for c in sorted(pick)]
    out += [_row("L", None, c, entry_override=px, entry_src_override="live_fill",
                 entry_ts=ts) for c, px, ts in lv]
    return out


# ────────────────────────────────────────────────────────────────────────────
# 4. 원장 I/O — append · 중복 방지 (date+code+arm+seed)
# ────────────────────────────────────────────────────────────────────────────
def read_ledger(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def append_ledger(path: Path, rows: List[Dict[str, Any]]) -> int:
    existing = read_ledger(path)
    seen = {tuple(str(r.get(k, "")) for k in _KEY) for r in existing}
    fresh = []
    for r in rows:
        k = tuple(str(r.get(c, "")) for c in _KEY)
        if k in seen:
            continue
        seen.add(k)
        fresh.append(r)
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LEDGER_COLS, extrasaction="ignore")
            if new_file:
                w.writeheader()
            w.writerows(fresh)
    return len(fresh)


# ────────────────────────────────────────────────────────────────────────────
# 5. 집계
# ────────────────────────────────────────────────────────────────────────────
def _closed(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [r for r in rows if r.get("ret_net") not in ("", None)]


def _stats(rows: List[Dict[str, str]]) -> Tuple[int, float, float]:
    cl = _closed(rows)
    if not cl:
        return 0, float("nan"), float("nan")
    rets = [float(r["ret_net"]) for r in cl]
    per_trade = sum(rets) / len(rets)
    wts = [float(r["notional"] or 0) for r in cl]
    tot = sum(wts)
    amt = (sum(w * x for w, x in zip(wts, rets)) / tot) if tot > 0 else float("nan")
    return len(cl), per_trade, amt


def summarize(path: Path, only_repro: bool) -> None:
    rows = read_ledger(path)
    if not rows:
        print(f"원장이 비었다: {path}")
        return
    if only_repro:
        rows = [r for r in rows if r.get("repro_ok") == "1"]
        print("※ `repro_ok=1` 인 날만 집계한다 (--all-days 로 해제)")
    dates = sorted({r["date"] for r in rows})
    print(f"\n원장 {path}  ·  {len(rows):,}행  ·  거래일 {len(dates)}일 "
          f"({dates[0] if dates else '-'} ~ {dates[-1] if dates else '-'})")

    print("\n| arm | 종료 | 진행중 | 거래당 ret_net | 금액가중 ret_net |")
    print("|---|---:|---:|---:|---:|")
    per_arm: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        per_arm.setdefault(r["arm"], []).append(r)
    for arm in ("P", "X", "R", "L"):
        rs = per_arm.get(arm, [])
        n, pt, amt = _stats(rs)
        n_open = sum(1 for r in rs if r.get("is_open") == "1")
        print(f"| {arm} | {n} | {n_open} | "
              f"{'nan' if n == 0 else f'{pt*100:+.3f}%'} | "
              f"{'nan' if n == 0 else f'{amt*100:+.3f}%'} |")

    # 순열 p — R 의 시드별 평균이 귀무 분포다(시드 하나 = 순열 1회).
    seed_means: List[float] = []
    for seed in range(N_SEEDS):
        rs = [r for r in per_arm.get("R", []) if r.get("seed") == str(seed)]
        n, pt, _ = _stats(rs)
        if n:
            seed_means.append(pt)
    if seed_means:
        print(f"\nR 귀무 분포: 시드 {len(seed_means)}개 · "
              f"평균 {sum(seed_means)/len(seed_means)*100:+.3f}% · "
              f"최소 {min(seed_means)*100:+.3f}% · 최대 {max(seed_means)*100:+.3f}%")
        for arm in ("P", "X"):
            n, pt, _ = _stats(per_arm.get(arm, []))
            if not n:
                continue
            ge = sum(1 for m in seed_means if m >= pt)
            p = (ge + 1) / (len(seed_means) + 1)
            print(f"  {arm}: 거래당 {pt*100:+.3f}%  ·  "
                  f"R 시드 중 이상 {ge}/{len(seed_means)}  ·  순열 p = {p:.4f}")
    else:
        print("\nR 종료 포지션이 없어 순열 p 를 낼 수 없다.")

    bad = sorted({r["date"] for r in rows if r.get("repro_ok") == "0"})
    nolog = sorted({r["date"] for r in rows if r.get("repro_ok") == "no_log"})
    if bad:
        print(f"\n🔴 repro_ok=0 (재현 불일치): {', '.join(bad)}")
    if nolog:
        print(f"⚠️ 로그 없음(계기 부재): {', '.join(nolog)}")


# ────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="TT 게이트 반사실 원장")
    ap.add_argument("--from", dest="dfrom", help="시작 거래일 YYYY-MM-DD")
    ap.add_argument("--to", dest="dto", help="종료 거래일 YYYY-MM-DD")
    ap.add_argument("--date", help="하루만 YYYY-MM-DD")
    ap.add_argument("--out", default=str(BASE), help="원장 디렉토리(기본: 이 폴더)")
    ap.add_argument("--summary", action="store_true", help="집계 인쇄")
    ap.add_argument("--all-days", action="store_true",
                    help="집계에서 repro_ok=1 필터를 «끈다»")
    ap.add_argument("--dry-run", action="store_true", help="DB 읽기만 · 파일 쓰기 0")
    ap.add_argument("--include-entry-day", action="store_true",
                    help="청산 판정에 진입일 D 의 일봉을 «포함»한다. 기본은 D+1 부터 — "
                         "D 의 low/high 에는 09:05 진입 «이전» 구간이 섞여 있기 때문. "
                         "🔴 사전등록이 다르게 못박았으면 이 깃발을 켜라.")
    a = ap.parse_args()

    ledger = Path(a.out) / "ledger.csv"
    if not (a.dfrom or a.date):
        if a.summary:
            summarize(ledger, only_repro=not a.all_days)
            return 0
        ap.error("--from/--to 또는 --date 또는 --summary 중 하나는 필요하다")

    if a.date:
        d0 = d1 = date.fromisoformat(a.date)
    else:
        d0 = date.fromisoformat(a.dfrom)
        d1 = date.fromisoformat(a.dto) if a.dto else d0

    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect(resolve_daily_source_db())
    min_db = resolve_minute_source_db()
    conn_min = conn if min_db == resolve_daily_source_db() else _connect(min_db)
    try:
        days = trading_days(conn, d0, d1)
        if not days:
            print(f"거래일이 없다: {d0} ~ {d1}")
            return 2
        print(f"거래일 {len(days)}개: {days[0]} ~ {days[-1]}"
              f"{'  [DRY-RUN — 파일 쓰기 0]' if a.dry_run else ''}")
        bars = DailyBars(QuantDailyReader(), cap_end=d1 + timedelta(days=90),
                         days=420 + (d1 - d0).days)
        rows: List[Dict[str, Any]] = []
        for d in days:
            rows += build_day(conn, conn_min, bars, d, a.include_entry_day, run_ts)
    finally:
        conn.close()
        if conn_min is not conn:
            conn_min.close()

    if a.dry_run:
        print(f"\nDRY-RUN: {len(rows):,}행을 만들었고 «쓰지 않았다» → {ledger}")
    else:
        n_new = append_ledger(ledger, rows)
        print(f"\n적재: 신규 {n_new:,}행 / 생성 {len(rows):,}행 (중복 {len(rows)-n_new:,}) → {ledger}")

    if a.summary and not a.dry_run:
        summarize(ledger, only_repro=not a.all_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
