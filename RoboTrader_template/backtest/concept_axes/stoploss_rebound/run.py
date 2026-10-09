"""손절 뒤 급반등 측정 러너 — 사전등록 `docs/prereg_2026-10-09_stoploss_rebound.md`(🔒 동결 e4d9ee2 · REGISTRY SR1)
+ 해석 부록 `docs/prereg_2026-10-09_stoploss_rebound_amendment_2026-10-09.md`(🔒 ceeff59 · §A 해석 · §B 개정 B1~B3).

    cd <worktree>/RoboTrader_template
    PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe
    $PY -X utf8 -m backtest.concept_axes.stoploss_rebound.run --stage preflight   # 개수·존재만(가격·손익 열 0)
    $PY -X utf8 -m backtest.concept_axes.stoploss_rebound.run --stage sealed      # §12-4 ③ → results/sealed_report.md
    $PY -X utf8 -m backtest.concept_axes.stoploss_rebound.run --stage open        # §12-4 ④ → results/RESULTS_<날짜>.md
    $PY -X utf8 -m backtest.concept_axes.stoploss_rebound.run --stage open --reopen-reason "<사유>"   # 부록 B3 1회

실행 전 확인(§12-4 ② · 부록 B2) — 하나라도 아니면 «통계 계산 전에» 거부(종료 코드·사유):
  동결 문서·부록 blob = 상수 · 가드 경로 미커밋 변경 0 · D_asof = 2026-10-16 · 미해결 해석 질문 0 ·
  tp/sl/보유기간 = 문서 §6-3 값 · KOSPI D_asof 행 ∧ D_asof 행 종목 수 ≥ 직전 거래일의 98%(적재 완료 · 대상 종목 중 행 없는
  것은 «영구 끊김» 목록) · 표본 N = 동결 SQL count(*) · 로트 id 중복 0. 개봉은 여기에 더해 봉인 산출물 커밋 · DB 지문 =
  봉인 때 지문 · 1회 실행 표식(부록 B3 — `[T3]` 줄 없이 중단됐을 때만 수정 커밋 뒤 1회 재개봉).
🔴 봉인 단계는 `stop_fill_price` 를 조인하지 않고(SQL 원문을 부분질의로 두고 바깥에서 열을 뺀다) · 이벤트 팔 R′/D′ ·
   ⓐ(`author_exit`)를 계산하지 않는다(대조 팔 p̂₀ · ⓑ 로트 수익률 집계 sd 만).
🔴 preflight 는 `guarded_fetch` 만 쓴다 — 결과 열에 가격·손익 열이 있으면 행을 받기 전에 중단.
🔴 DB SELECT 만(`bootstrap` = 읽기 전용 세션) · 라이브 모듈 import 만 · 재사용 모듈 수정 0줄 · KIS 0.
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import json                                                            # noqa: E402
import math                                                            # noqa: E402
import os                                                              # noqa: E402
import re                                                              # noqa: E402
import subprocess                                                      # noqa: E402
import sys                                                             # noqa: E402
import tempfile                                                        # noqa: E402
from bisect import bisect_right                                        # noqa: E402
from collections import Counter, defaultdict                           # noqa: E402
from dataclasses import dataclass, field                               # noqa: E402
from datetime import date, datetime, timedelta, timezone         # noqa: E402
from fractions import Fraction                                          # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple  # noqa: E402

import numpy as np                                                     # noqa: E402

from backtest.concept_axes.ledger8 import exitsim8 as X                # noqa: E402
from backtest.concept_axes.ledger8 import fidelity8 as F               # noqa: E402
from backtest.concept_axes.stoploss_rebound import author_exit as AE   # noqa: E402
from backtest.concept_axes.stoploss_rebound import lots as LT          # noqa: E402
from backtest.concept_axes.stoploss_rebound import stats as ST         # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                   # …/RoboTrader_template
PREREG = ROOT / "docs" / "prereg_2026-10-09_stoploss_rebound.md"
AMENDMENT = ROOT / "docs" / "prereg_2026-10-09_stoploss_rebound_amendment_2026-10-09.md"
RESULTS = HERE / "results"
SEALED_MD = RESULTS / "sealed_report.md"
META = RESULTS / "run_meta.json"
OPEN_LOG = RESULTS / "open_log.txt"

# ── 🔒 사전등록 값 ────────────────────────────────────────────────────────────
PREREG_FROZEN_BLOB = "c5f7c346285217898ca4060c703be6758aa6d82a"   # §12-2 동결본 `git hash-object`
PREREG_FROZEN_MD5 = "f981bd8664aae3228e62fae0e0f3f03c"            # 기록용(커밋 메시지·REGISTRY)
AMENDMENT_FROZEN_BLOB = "24514a0ddb7fd54aeed105b29d7fc657f98956df"  # 부록(ceeff59) `git hash-object`
AMENDMENT_FROZEN_MD5 = "aa3f8fb2ca9d6482588e4530f54b6232"         # 기록용
D_ASOF = date(2026, 10, 16)
START = date(2026, 8, 7)
SPLIT_DAY = date(2026, 8, 26)          # §3·§6-8 — 1810cd2 경계(분할 인쇄 · 충실도 분모)
INTEG_END = date(2026, 8, 16)          # §12-3·§12-4 ③ 원장 정합성 구간 08-07~08-16
CAL_START = date(2026, 1, 2)           # 달력·봉 읽기 시작(진입 − 60봉 · 정지 종목 SMA60 창(부록 A5) · 데이터 청산 창 120일)
STRATS = ("book_pullback_ma20", "minervini_volume_dryup", "daytrading_3methods_breakout", "book_pullback_ma5")
EXPECT_RULES = {"book_pullback_ma20": (0.10, 0.08, 50), "minervini_volume_dryup": (0.12, 0.08, 20),
                "daytrading_3methods_breakout": (0.10, 0.10, 10), "book_pullback_ma5": (0.15, 0.03, 30)}
HS = (5, 10, 20)                        # §4 · 주 h = 10
H_MAIN = 10
COST = 0.25                             # §6-6 비용 차감 인쇄(%p)
ASYM_MAX = Fraction(2, 100)             # §3 비대칭 경고(> 2%p)
FID_DATE_MIN = 0.70                     # §6-8 청산일 일치율
FID_DATE_TOL = 1                        # §6-8 ±1 KOSPI 거래일
LOAD_RATIO = Fraction(98, 100)          # 부록 B2 — D_asof 행 종목 수 ≥ 직전 거래일의 98% = 적재 완료
T3_TAG = "[T3]"                         # 부록 B3 — open_log 의 진짜 결과 줄 표지
REBUY_N = 5                             # §2 ⑨ N = 5 KOSPI 거래일
KST = timezone(timedelta(hours=9))

# 🔒 해석 질문 — 비어 있지 않으면 sealed/open 을 거부한다. Q1~Q11 은 부록(ceeff59) §A·§B 로 확정 → 비움.
UNRESOLVED: Tuple[str, ...] = ()

GUARD_PATHS = (HERE, PREREG, AMENDMENT, ROOT / "backtest" / "concept_axes" / "ledger8",
               ROOT / "backtest" / "concept_axes" / "minervini" / "cap_skip_ledger",
               ROOT / "backtest" / "concept_axes" / "candidate_ledger" / "exit_diag" / "run_random_entry.py")

# ── 🔒 SQL 원문(문서 §3·§5·§6 글자 그대로 · 테스트가 문서와 대조) ──────────────────────
EVENT_SQL = """-- 손절 이벤트 모집단 (E)
SELECT id, strategy, stock_code, "timestamp", buy_record_id, price AS stop_fill_price
FROM virtual_trading_records
WHERE action = 'SELL'
  AND reason LIKE '손절 실행%'
  AND strategy IN ('book_pullback_ma20','minervini_volume_dryup',
                   'daytrading_3methods_breakout','book_pullback_ma5')
  AND ("timestamp" AT TIME ZONE 'Asia/Seoul')::date >= DATE '2026-08-07'
  AND ("timestamp" AT TIME ZONE 'Asia/Seoul')::date <= DATE '2026-10-16'   -- D_asof 상한
  AND is_test = TRUE;"""

CONTROL_SQL = """SELECT DISTINCT b.stock_code
FROM virtual_trading_records b
WHERE b.action='BUY' AND b.strategy = :g
  AND (b.timestamp AT TIME ZONE 'Asia/Seoul')::date < :t   -- (:t <= D_asof 이므로 D_asof 상한 자동 충족)
  AND NOT EXISTS (SELECT 1 FROM virtual_trading_records s
                  WHERE s.action='SELL' AND s.buy_record_id = b.id
                    AND (s.timestamp AT TIME ZONE 'Asia/Seoul')::date <= :t)
  AND b.stock_code <> :c
  AND NOT EXISTS (SELECT 1 FROM virtual_trading_records s2
                  WHERE s2.action='SELL' AND s2.strategy = :g AND s2.stock_code = b.stock_code
                    AND s2.reason LIKE '손절 실행%'
                    AND (s2.timestamp AT TIME ZONE 'Asia/Seoul')::date = :t);"""

LOT_SQL = """-- T3 로트 모집단 (L) · 결과 열 없음
WITH cal AS (
  SELECT date::date AS d, row_number() OVER (ORDER BY date) AS rn
  FROM daily_prices
  WHERE stock_code = 'KOSPI' AND date >= '2026-08-07' AND date <= '2026-10-16'
)
SELECT b.id, b.strategy, b.stock_code, b."timestamp" AS buy_ts,
       s.id AS sell_id, s."timestamp" AS sell_ts, s.reason AS sell_reason
FROM virtual_trading_records b
JOIN cal cb ON cb.d = (b."timestamp" AT TIME ZONE 'Asia/Seoul')::date
LEFT JOIN virtual_trading_records s
       ON s.action = 'SELL' AND s.buy_record_id = b.id
      AND (s."timestamp" AT TIME ZONE 'Asia/Seoul')::date <= DATE '2026-10-16'  -- D_asof 뒤 SELL = 미청산
WHERE b.action = 'BUY' AND b.is_test = TRUE
  AND b.strategy IN ('book_pullback_ma20','minervini_volume_dryup',
                     'daytrading_3methods_breakout','book_pullback_ma5')
  AND (b."timestamp" AT TIME ZONE 'Asia/Seoul')::date >= DATE '2026-08-07'
  AND cb.rn + 20 <= (SELECT max(rn) FROM cal);   -- max(rn) = 위치(D_asof) — §12-4 ② 전제(10-16 KOSPI 행 존재)"""

LOT_CAP_LINE = "  AND cb.rn + 20 <= (SELECT max(rn) FROM cal);   -- max(rn) = 위치(D_asof) — §12-4 ② 전제(10-16 KOSPI 행 존재)"

# 결과에 나오면 안 되는 열(preflight `guarded_fetch`) — 가격·손익·수량·OHLCV·지표
FORBIDDEN_COLS = frozenset({"price", "stop_fill_price", "profit_loss", "profit_rate", "open", "high", "low", "close",
                            "volume", "trading_value", "market_cap", "returns_1d", "returns_5d", "returns_20d",
                            "volatility_20d", "adj_factor", "target_profit_rate", "stop_loss_rate", "quantity",
                            "amount"})

EXIT_OK, EXIT_STATIC, EXIT_DATA, EXIT_ORDER, EXIT_FINGERPRINT, EXIT_RULES = 0, 3, 4, 5, 6, 7


class Refuse(Exception):
    """실행 전 확인 실패 — 통계 계산 «전»에 멈춘다."""

    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


# ════════════════════════════════════════════════════════════════════════════
# 1. SQL 변환(원문은 그대로 두고 바깥에서만 감싼다)
# ════════════════════════════════════════════════════════════════════════════
def inner(sql: str) -> str:
    """원문 끝 `;` 만 떼어 부분질의로 쓸 수 있게 한다(주석·본문 불변)."""
    s = sql.rstrip()
    if s.endswith(";"):
        return s[:-1]
    idx = s.rfind(";")
    if idx >= 0 and s[idx + 1:].lstrip().startswith("--") and "\n" not in s[idx + 1:]:
        return s[:idx] + s[idx + 1:]          # 끝 줄이 `…;   -- 주석` 꼴
    return s


def wrap(sql: str, cols: str) -> str:
    return f"SELECT {cols} FROM (\n{inner(sql)}\n) q"


def lot_sql_uncapped() -> str:
    """§6-1 «전체 경로 평가판(진입일 상한 없음 · 인쇄만)» — 원문에서 진입일 상한 한 줄만 뺀다."""
    if LOT_SQL.count(LOT_CAP_LINE) != 1:
        raise ValueError("LOT_SQL 의 진입일 상한 줄을 찾지 못했다")
    return LOT_SQL.replace(LOT_CAP_LINE, "  ;")


def named(sql: str) -> str:
    """`:g`·`:t`·`:c` → psycopg2 `%(g)s` (원문 `%` 는 `%%` 로) — `::date` 는 건드리지 않는다."""
    return re.sub(r"(?<![:\w]):(g|t|c)\b", r"%(\1)s", inner(sql).replace("%", "%%"))


# ════════════════════════════════════════════════════════════════════════════
# 2. 정적 가드(git · 상수)
# ════════════════════════════════════════════════════════════════════════════
def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8")


def git_blob(path: Path) -> str:
    r = _git("hash-object", str(path))
    if r.returncode != 0 or not r.stdout.strip():
        raise Refuse(EXIT_STATIC, f"git hash-object 실패({path.name})")
    return r.stdout.strip()


def prereg_blob() -> str:
    return git_blob(PREREG)


def dirty_paths() -> List[str]:
    r = _git("status", "--porcelain", "--untracked-files=all", "--", *[str(p) for p in GUARD_PATHS])
    if r.returncode != 0:
        raise Refuse(EXIT_STATIC, "git status 실패")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def head_sha() -> str:
    r = _git("rev-parse", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def static_checks(stage: str, blob_of: Callable[[Path], str] = None, dirty_of: Callable[[], List[str]] = None,
                  d_asof: date = None, unresolved: Sequence[str] = None) -> List[Tuple[str, bool, str]]:
    """(항목, 통과, 설명) 목록 — preflight 는 인쇄만, sealed/open 은 하나라도 실패면 거부."""
    blob_of = blob_of or git_blob
    dirty_of = dirty_of or dirty_paths
    d_asof = D_ASOF if d_asof is None else d_asof
    unresolved = UNRESOLVED if unresolved is None else unresolved
    out: List[Tuple[str, bool, str]] = []
    for name, path, want in (("동결 blob", PREREG, PREREG_FROZEN_BLOB), ("부록 blob", AMENDMENT, AMENDMENT_FROZEN_BLOB)):
        try:
            b = blob_of(path)
            out.append((name, b == want, f"{b} vs 상수 {want}"))
        except Refuse as e:
            out.append((name, False, e.reason))
    try:
        dp = dirty_of()
        out.append(("미커밋 변경 0", not dp, "없음" if not dp else " | ".join(dp[:8])))
    except Refuse as e:
        out.append(("미커밋 변경 0", False, e.reason))
    out.append(("D_asof = 2026-10-16", d_asof == date(2026, 10, 16), str(d_asof)))
    out.append(("미해결 해석 질문 0", not unresolved, ",".join(unresolved) or "없음"))
    return out


def enforce(checks: Sequence[Tuple[str, bool, str]]) -> None:
    bad = [f"{n}: {d}" for n, ok, d in checks if not ok]
    if bad:
        raise Refuse(EXIT_STATIC, "실행 전 확인 실패 — " + " / ".join(bad))


def check_rules(rules: Dict[str, X.ExitRules]) -> None:
    for s, (tp, sl, mh) in EXPECT_RULES.items():
        r = rules[s]
        if (round(r.tp, 6), round(r.sl, 6), int(r.max_hold_days)) != (tp, sl, mh):
            raise Refuse(EXIT_RULES, f"{s}: tp/sl/보유기간 {r.tp}/{r.sl}/{r.max_hold_days} ≠ 문서 §6-3 {tp}/{sl}/{mh}")


# ════════════════════════════════════════════════════════════════════════════
# 3. DB(SELECT 전용)
# ════════════════════════════════════════════════════════════════════════════
def connect():
    from backtest.concept_axes.minervini.cap_skip_ledger import sources as CS
    conn = CS.connect()
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Asia/Seoul'")
    return conn


def fetch(conn, sql: str, args: Any = None) -> List[Tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def guarded_fetch(conn, sql: str, args: Any = None) -> List[Tuple]:
    """preflight 전용 — 결과 열 이름에 가격·손익 열이 있으면 행을 받기 전에 중단."""
    with conn.cursor() as cur:
        cur.execute(sql, args)
        names = {str(d[0]).lower() for d in (cur.description or [])}
        bad = names & FORBIDDEN_COLS
        if bad:
            raise Refuse(EXIT_STATIC, f"preflight 가 금지 열을 받으려 했다: {sorted(bad)}")
        return cur.fetchall()


def _kst(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    if ts.tzinfo is not None:
        ts = ts.astimezone(KST).replace(tzinfo=None)
    return ts


def _d(x: Any) -> date:
    return x if isinstance(x, date) and not isinstance(x, datetime) else date.fromisoformat(str(x)[:10])


# ════════════════════════════════════════════════════════════════════════════
# 4. 적재
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class Event:
    id: int
    strategy: str
    code: str
    ts: datetime
    brid: Optional[int]
    stop_px: Optional[float] = None

    @property
    def d(self) -> date:
        return self.ts.date()


@dataclass
class Data:
    cal: List[date]
    events: List[Event]
    lots: List[LT.LotIn]
    rows: Dict[str, LT.Rows]
    splits: Dict[str, List[date]]
    rights: Dict[str, List[date]]
    controls: Dict[int, List[str]]
    minutes: Dict[Tuple[str, date], List[Tuple[str, Any]]]
    rules: Dict[str, X.ExitRules]
    probes: Dict[str, Any]
    aware: Callable[[datetime], datetime] = lambda t: t
    lots_full: List[LT.LotIn] = field(default_factory=list)      # 인쇄만 — 진입일 상한 없는 판(§6-1)
    pos: Dict[date, int] = field(default_factory=dict)
    i_asof: int = -1

    def __post_init__(self) -> None:
        self.pos = {d: i for i, d in enumerate(self.cal)}
        if D_ASOF not in self.pos:
            raise Refuse(EXIT_DATA, f"KOSPI 달력에 D_asof {D_ASOF} 가 없다")
        self.i_asof = self.pos[D_ASOF]

    def tdist(self, a: date, b: date) -> int:
        return bisect_right(self.cal, b) - bisect_right(self.cal, a)


def load_calendar(conn) -> List[date]:
    rows = fetch(conn, "SELECT DISTINCT date FROM daily_prices WHERE stock_code = 'KOSPI' AND date >= %s "
                       "AND date <= %s ORDER BY date", (CAL_START.isoformat(), D_ASOF.isoformat()))
    return [_d(r[0]) for r in rows]


def load_events(conn, with_price: bool) -> List[Event]:
    cols = 'id, strategy, stock_code, "timestamp", buy_record_id' + (", stop_fill_price" if with_price else "")
    rows = fetch(conn, wrap(EVENT_SQL, cols) + " ORDER BY id")
    return [Event(int(r[0]), str(r[1]), str(r[2]), _kst(r[3]), int(r[4]) if r[4] is not None else None,
                  float(r[5]) if with_price and r[5] is not None else None) for r in rows]


def load_lots(conn, sql: str = LOT_SQL) -> List[LT.LotIn]:
    rows = fetch(conn, wrap(sql, "id, strategy, stock_code, buy_ts, sell_id, sell_ts, sell_reason") + " ORDER BY id")
    ids = [int(r[0]) for r in rows]
    dup = [i for i, n in Counter(ids).items() if n > 1]
    if dup:
        raise Refuse(EXIT_DATA, f"T3 로트 SQL 에 같은 로트 id 가 2행 이상(매도 2건?) {dup[:10]} — ⓑ 실제 청산을 정할 수 없다")
    px = dict((int(i), (float(p), int(q or 0))) for i, p, q in fetch(
        conn, "SELECT id, price::float8, quantity FROM virtual_trading_records WHERE id = ANY(%s)",
        ([int(r[0]) for r in rows] + [int(r[4]) for r in rows if r[4] is not None],)))
    out: List[LT.LotIn] = []
    for r in rows:
        bp, bq = px[int(r[0])]
        sp = px[int(r[4])][0] if r[4] is not None else None
        out.append(LT.LotIn(int(r[0]), str(r[1]), str(r[2]), _kst(r[3]), bp, bq,
                            int(r[4]) if r[4] is not None else None, _kst(r[5]), r[6], sp))
    return out


def load_controls(conn, events: Sequence[Event]) -> Dict[int, List[str]]:
    q = named(CONTROL_SQL)
    return {e.id: sorted(str(r[0]) for r in fetch(conn, q, dict(g=e.strategy, t=e.d, c=e.code))) for e in events}


def load_rows(conn, codes: Sequence[str]) -> Dict[str, LT.Rows]:
    out: Dict[str, LT.Rows] = defaultdict(dict)
    for c, d, o, h, lo, cl, v, vol in fetch(
            conn, "SELECT stock_code, date, open::float8, high::float8, low::float8, close::float8, volume::float8, "
                  "volatility_20d::float8 FROM daily_prices WHERE stock_code = ANY(%s) AND date >= %s AND date <= %s",
            (list(codes), CAL_START.isoformat(), D_ASOF.isoformat())):
        out[str(c)][_d(d)] = LT.DayRow(o, h, lo, cl, v, vol)
    return dict(out)


def load_corp(conn, codes: Sequence[str]) -> Tuple[Dict[str, List[date]], Dict[str, List[date]]]:
    """§3 X3 (ii) — 날짜 = COALESCE(meta->>'effective_date', event_date)(collectors/daily_adj.py:11-26)."""
    sp: Dict[str, List[date]] = defaultdict(list)
    ri: Dict[str, List[date]] = defaultdict(list)
    for c, t, d in fetch(conn, "SELECT stock_code, event_type, COALESCE((meta->>'effective_date')::date, event_date) "
                               "FROM corp_events WHERE stock_code = ANY(%s) "
                               "AND event_type IN ('split','bonus_issue','rights_issue')", (list(codes),)):
        (ri if t == "rights_issue" else sp)[str(c)].append(_d(d))
    return dict(sp), dict(ri)


def load_live_rules() -> Tuple[Dict[str, X.ExitRules], Dict[str, Any]]:
    from backtest.concept_axes.ledger8 import sellprobe8 as SP
    from backtest.concept_axes.ledger8 import sources8 as SRC8
    from backtest.concept_axes.ledger8.livesignal8 import load8
    win = SRC8.WindowCache()
    rules: Dict[str, X.ExitRules] = {}
    probes: Dict[str, Any] = {}
    for s in STRATS:
        st = load8(s)
        rules[s] = SP.resolve_live_tp_sl(s, st)
        probes[s] = SP.SellProbe(s, st, win.get)
    return rules, probes


def load_all(conn, stage: str) -> Tuple[Data, Dict[str, Any]]:
    from backtest.concept_axes.ledger8 import sources8 as SRC8
    cal = load_calendar(conn)
    events = load_events(conn, with_price=(stage == "open"))
    lots = load_lots(conn)
    n_ev = fetch(conn, wrap(EVENT_SQL, "count(*)"))[0][0]
    n_lot = fetch(conn, wrap(LOT_SQL, "count(*)"))[0][0]
    if n_ev != len(events) or n_lot != len(lots):
        raise Refuse(EXIT_DATA, f"표본 N 불일치 — 이벤트 {len(events)}/{n_ev} · 로트 {len(lots)}/{n_lot}")
    lots_full = load_lots(conn, lot_sql_uncapped())
    controls = load_controls(conn, events)
    codes = sorted({e.code for e in events} | {lt.code for lt in lots_full}
                   | {c for cs in controls.values() for c in cs})
    rows = load_rows(conn, codes)
    splits, rights = load_corp(conn, codes)
    minutes = {(lt.code, lt.d0): SRC8.minute_bars(lt.code, lt.d0) for lt in lots_full
               if lt.buy_ts.time() > LT.EARLY_FILL}
    rules, probes = load_live_rules()
    check_rules(rules)
    d = Data(cal, events, lots, rows, splits, rights, controls, minutes, rules, probes, SRC8.aware, lots_full)
    return d, dict(n_events=n_ev, n_lots=n_lot, codes=codes)


def require_asof_rows(conn, codes: Sequence[str]) -> Dict[str, Any]:
    """부록 B2(§12-4 ② 대체) — KOSPI D_asof 행 ∧ D_asof 행 종목 수 ≥ 직전 KOSPI 거래일의 98%(적재 완료).
    대상 종목 중 D_asof 행이 없는 것은 «영구 끊김» 목록(거부 사유 아님). 개수·종목코드만 읽는다(`guarded_fetch`)."""
    k = guarded_fetch(conn, "SELECT count(*) AS n FROM daily_prices WHERE stock_code = 'KOSPI' AND date = %s",
                      (D_ASOF.isoformat(),))[0][0]
    prev = guarded_fetch(conn, "SELECT max(date) AS d FROM daily_prices WHERE stock_code = 'KOSPI' AND date < %s",
                         (D_ASOF.isoformat(),))[0][0]
    n_asof = int(guarded_fetch(conn, "SELECT count(DISTINCT stock_code) AS n FROM daily_prices WHERE date = %s",
                               (D_ASOF.isoformat(),))[0][0])
    n_prev = int(guarded_fetch(conn, "SELECT count(DISTINCT stock_code) AS n FROM daily_prices WHERE date = %s",
                               (str(prev),))[0][0]) if prev is not None else 0
    have = {str(r[0]) for r in guarded_fetch(
        conn, "SELECT DISTINCT stock_code FROM daily_prices WHERE date = %s AND stock_code = ANY(%s)",
        (D_ASOF.isoformat(), list(codes)))}
    missing = sorted(set(codes) - have)
    loaded = n_prev > 0 and Fraction(n_asof, n_prev) >= LOAD_RATIO
    return dict(kospi=int(k) > 0, prev=str(prev) if prev is not None else None, n_asof=n_asof, n_prev=n_prev,
                loaded=loaded, ok=bool(int(k) > 0 and loaded), n_codes=len(set(codes)), missing=missing)


def asof_line(rq: Dict[str, Any]) -> str:
    return (f"D_asof {D_ASOF}: KOSPI 행 {'있음' if rq['kospi'] else '없음'} · 전체 종목 {rq['n_asof']} / 직전 거래일 "
            f"{rq['prev']} {rq['n_prev']}(≥98% {'충족' if rq['loaded'] else '미충족'}) · 대상 {rq['n_codes']} 중 D_asof 행 "
            f"없음 {len(rq['missing'])}" + (f" = «영구 끊김» {rq['missing']}" if rq['ok'] and rq['missing'] else ""))


def fingerprint(conn, codes: Sequence[str], minute_keys: Sequence[Tuple[str, date]]) -> Dict[str, str]:
    """데이터 소급 수정 감지 — 서버에서 md5 만 계산(값은 파이썬으로 오지 않는다)."""
    allc = sorted(set(codes) | {"KOSPI"})
    q = {
        "vtr": ("SELECT md5(string_agg(row(id, action, strategy, stock_code, \"timestamp\", price, quantity, reason, "
                "buy_record_id, is_test)::text, E'\\n' ORDER BY id)) FROM virtual_trading_records "
                "WHERE strategy = ANY(%s) AND (\"timestamp\" AT TIME ZONE 'Asia/Seoul')::date <= %s",
                (list(STRATS), D_ASOF)),
        "daily_prices": ("SELECT md5(string_agg(row(stock_code, date, open, high, low, close, volume, volatility_20d, "
                         "adj_factor)::text, E'\\n' ORDER BY stock_code, date)) FROM daily_prices "
                         "WHERE stock_code = ANY(%s) AND date >= %s AND date <= %s",
                         (allc, CAL_START.isoformat(), D_ASOF.isoformat())),
        "corp_events": ("SELECT md5(string_agg(row(stock_code, event_type, event_date, end_date, meta)::text, E'\\n' "
                        "ORDER BY stock_code, event_type, event_date, meta::text)) FROM corp_events "
                        "WHERE stock_code = ANY(%s)", (allc,)),
        "minute_candles": ("SELECT md5(string_agg(row(stock_code, trade_date, idx, time, open, high, low, close, "
                           "volume)::text, E'\\n' ORDER BY stock_code, trade_date, idx)) FROM minute_candles "
                           "WHERE stock_code = ANY(%s) AND trade_date = ANY(%s)",
                           (sorted({c for c, _ in minute_keys}) or ["-"],
                            sorted({d.strftime("%Y%m%d") for _, d in minute_keys}) or ["-"])),
    }
    return {k: str(fetch(conn, s, a)[0][0]) for k, (s, a) in q.items()}


# ════════════════════════════════════════════════════════════════════════════
# 5. 계산 — 이벤트(§3·§4·§5) · 로트(§6) · 공통
# ════════════════════════════════════════════════════════════════════════════
def period(d: date) -> str:
    return "08-07~08-25" if d < SPLIT_DAY else "08-26~"


@dataclass
class EvUnit:
    """이벤트 × h 처리 결과. 이벤트 팔 창(`win`)은 봉인 단계에서 극값을 계산하지 않는다(extremes=False)."""
    ev: Event
    h: int
    code: str                                  # 첫 탈락 규칙: '' = 포함 · X0·X4·X1·X2·X3·(X5 는 T1/T2 만)
    win: Optional[LT.Win]
    controls: List[str]
    cwins: Dict[str, LT.Win]
    usable: List[str]
    c_excl: Dict[str, str]
    base_t: Optional[float]                    # 이벤트 자신의 C_t — 봉인 단계(extremes=False)에서는 값을 담지 않는다
    base_ok: bool = False                      # 이벤트 자신의 C_t 존재(부록 A8 개수 인쇄)


def _row(D: Data, code: str, d: date) -> Optional[LT.DayRow]:
    return D.rows.get(code, {}).get(d)


def event_units(D: Data, h: int, extremes_event: bool) -> List[EvUnit]:
    """§3 X0 → X4(구조 규칙 · 데이터 무관) → X1 → X2 → X3(이벤트 팔) · 대조는 같은 창에 X2·X3 대칭 · X5 = 쓸 대조 없음."""
    x0 = {e.id for e in D.events if e.brid is None}
    base = [e for e in D.events if e.id not in x0]
    keep = LT.episode_keep([(e.id, e.strategy, e.code, e.ts) for e in base], D.pos)
    out: List[EvUnit] = []
    for e in sorted(D.events, key=lambda x: (x.d, x.strategy, x.code, x.id)):
        cs = D.controls.get(e.id, [])
        if e.id in x0:
            out.append(EvUnit(e, h, "X0", None, cs, {}, [], {}, None))
            continue
        if e.id not in keep:
            out.append(EvUnit(e, h, "X4", None, cs, {}, [], {}, None))
            continue
        i_t = D.pos[e.d]
        w = LT.window(D.rows.get(e.code, {}), D.cal, i_t, h, D.i_asof, D.splits.get(e.code, []),
                      D.rights.get(e.code, []), extremes=extremes_event)
        cw: Dict[str, LT.Win] = {}
        cx: Dict[str, str] = {}
        usable: List[str] = []
        if w.complete:
            for c in cs:
                wc = LT.window(D.rows.get(c, {}), D.cal, i_t, h, D.i_asof, D.splits.get(c, []), D.rights.get(c, []))
                cw[c] = wc
                r0 = _row(D, c, e.d)
                if wc.x2:
                    cx[c] = "X2"
                elif wc.x3:
                    cx[c] = "X3"
                elif r0 is None or r0.close is None:
                    cx[c] = "no_base"
                else:
                    usable.append(c)
        r_e = _row(D, e.code, e.d)
        base_ok = r_e is not None and r_e.close is not None
        base_t = float(r_e.close) if (base_ok and extremes_event) else None
        code = "X1" if not w.complete else "X2" if w.x2 else "X3" if w.x3 else ""
        out.append(EvUnit(e, h, code, w, cs, cw, usable, cx, base_t, base_ok))
    return out


def exclusion_summary(units: Sequence[EvUnit]) -> Dict[str, Any]:
    cnt = Counter(u.code or "포함" for u in units)
    ev_den = sum(1 for u in units if u.code in ("", "X2", "X3"))
    ev_x = sum(1 for u in units if u.code in ("X2", "X3"))
    pairs = [(u, c) for u in units if u.code in ("", "X2", "X3") for c in u.controls]
    c_x = sum(1 for u, c in pairs if u.c_excl.get(c) in ("X2", "X3"))
    ev_rate = ev_x / ev_den if ev_den else float("nan")
    c_rate = c_x / len(pairs) if pairs else float("nan")
    x5 = sum(1 for u in units if u.code == "" and not u.usable)
    x5_sql = sum(1 for u in units if u.code == "" and not u.controls)
    ev_jump = sum(1 for u in units if u.code == "X3" and u.win.jump)
    ev_corp = sum(1 for u in units if u.code == "X3" and u.win.corp)
    rights_ev = sum(1 for u in units if u.win is not None and u.win.complete and u.win.rights)
    rights_c = sum(1 for u, c in pairs if u.cwins.get(c) is not None and u.cwins[c].rights)
    no_base_c = sum(1 for u, c in pairs if u.c_excl.get(c) == "no_base")
    no_base_ev = sum(1 for u in units if u.code == "" and u.usable and not u.base_ok)
    diff = ev_rate - c_rate if ev_den and pairs else float("nan")
    warn = bool(ev_den and pairs and Fraction(ev_x, ev_den) - Fraction(c_x, len(pairs)) > ASYM_MAX)   # 경계 정확 비교
    return dict(counts=dict(cnt), ev_den=ev_den, ev_x=ev_x, ev_rate=ev_rate, c_den=len(pairs), c_x=c_x,
                c_rate=c_rate, diff=diff, warn=warn, x5=x5, x5_sql=x5_sql,
                ev_jump=ev_jump, ev_corp=ev_corp, rights_ev=rights_ev, rights_c=rights_c, no_base_c=no_base_c,
                no_base_ev=no_base_ev,
                n_t12=sum(1 for u in units if u.code == "" and u.usable))


def control_value(D: Data, u: EvUnit, c: str, kind: str) -> Optional[float]:
    """대조 팔 값(C_t 기준) — kind: 'R' = R′_h · 'D' = D′_h."""
    w = u.cwins[c]
    base = float(_row(D, c, u.ev.d).close)
    return LT.rise(w, base) if kind == "R" else LT.fall(w, base)


def event_blocks(D: Data, last: date) -> Dict[date, int]:
    return LT.blocks_of([d for d in D.cal if START <= d <= last])


def t12_units(D: Data, units: Sequence[EvUnit], kind: str, thr: float) -> List[ST.FakeUnit]:
    """§7 T1/T2 도구 게이트 재료 — X0~X5 뒤 · (t, 전략, 종목, id) 정렬 · |C(i)| ≥ 2 · 대조 이진 값(C_t 기준)."""
    blk = event_blocks(D, D.cal[D.i_asof - H_MAIN])
    out: List[ST.FakeUnit] = []
    for u in sorted(units, key=lambda x: (x.ev.d, x.ev.strategy, x.ev.code, x.ev.id)):
        if u.code or len(u.usable) < 2:
            continue
        y: Dict[str, float] = {}
        for c in sorted(u.usable):
            v = control_value(D, u, c, kind)
            y[c] = float(v >= thr) if kind == "R" else float(v <= thr)
        out.append(ST.FakeUnit(sorted(u.usable), y, blk[u.ev.d]))
    return out


def rebuy_count(conn, D: Data) -> Dict[str, int]:
    """§2 ⑨ 정의(N=5 KOSPI 거래일 · 같은 날 포함 · 가장 최근 손절에 1회 귀속 · distinct BUY) — 우리 모집단 귀속 건수."""
    rows = fetch(conn, "SELECT id, strategy, stock_code, action, \"timestamp\", (reason LIKE '손절 실행%%') AS ex "
                       "FROM virtual_trading_records WHERE strategy = ANY(%s) AND is_test = TRUE "
                       "AND (\"timestamp\" AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s "
                       "AND (action = 'BUY' OR (action = 'SELL' AND reason LIKE '손절%%'))",
                 (list(STRATS), START, D_ASOF))
    stops = [(int(i), s, c, _kst(t), bool(x)) for i, s, c, a, t, x in rows if a == "SELL"]
    buys = [(int(i), s, c, _kst(t)) for i, s, c, a, t, x in rows if a == "BUY"]
    ev_ids = {e.id for e in D.events}
    attrib: Dict[int, Tuple[int, datetime, bool]] = {}
    for sid, s, c, ts, ex in stops:
        for bid, bs, bc, bts in buys:
            if bs == s and bc == c and bts > ts and D.tdist(ts.date(), bts.date()) <= REBUY_N:
                if bid not in attrib or ts > attrib[bid][1]:
                    attrib[bid] = (sid, ts, ex)
    in_e = {b for b, (sid, _, _) in attrib.items() if sid in ev_ids}
    return dict(rebuy_buys_in_E=len(in_e), rebuy_buys_other_stop=len(attrib) - len(in_e),
                stops_E_with_rebuy=len({attrib[b][0] for b in in_e}), stop_ids=sorted({attrib[b][0] for b in in_e}))


def integrity_counts(conn) -> Dict[str, Dict[str, int]]:
    """§12-3 ②·§12-4 ③ — 08-07~08-16 SELL 원장 정합성(critic `d2.sql` 정의: 라벨·종목 불일치 · 선행 매도 · 중복)."""
    out: Dict[str, Dict[str, int]] = {}
    for name, filt in (("전 전략", ""), ("4전략", " AND s.strategy = ANY(%(st)s)")):
        a = dict(lo=START, hi=INTEG_END, st=list(STRATS))
        r = fetch(conn, "SELECT count(*), count(b.id), count(*) FILTER (WHERE s.strategy <> b.strategy), "
                        "count(*) FILTER (WHERE s.stock_code <> b.stock_code), "
                        "count(*) FILTER (WHERE s.\"timestamp\" < b.\"timestamp\") "
                        "FROM virtual_trading_records s LEFT JOIN virtual_trading_records b ON b.id = s.buy_record_id "
                        "WHERE s.action = 'SELL' AND (s.\"timestamp\" AT TIME ZONE 'Asia/Seoul')::date "
                        "BETWEEN %(lo)s AND %(hi)s" + filt, a)[0]
        dup = fetch(conn, "SELECT count(*) FROM (SELECT s.buy_record_id FROM virtual_trading_records s "
                          "WHERE s.action = 'SELL' AND (s.\"timestamp\" AT TIME ZONE 'Asia/Seoul')::date "
                          "BETWEEN %(lo)s AND %(hi)s" + filt + " GROUP BY 1 HAVING count(*) > 1) x", a)[0][0]
        out[name] = dict(sell=int(r[0]), linked=int(r[1]), label_mismatch=int(r[2]), code_mismatch=int(r[3]),
                         sell_before_buy=int(r[4]), dup_sell_per_buy=int(dup))
    return out


def side_counts(conn, D: Data) -> Dict[str, Any]:
    """§3 — `손절%` 이면서 `손절 실행%` 아닌 SELL(정의상 제외) · 같은 종목·같은 날 복수 전략 손절."""
    rows = fetch(conn, "SELECT strategy, count(*) FROM virtual_trading_records WHERE action = 'SELL' "
                       "AND reason LIKE '손절%%' AND reason NOT LIKE '손절 실행%%' AND strategy = ANY(%s) AND is_test = TRUE "
                       "AND (\"timestamp\" AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s GROUP BY 1 ORDER BY 1",
                 (list(STRATS), START, D_ASOF))
    by: Dict[Tuple[str, date], Set[str]] = defaultdict(set)
    for e in D.events:
        by[(e.code, e.d)].add(e.strategy)
    return dict(other_stop={str(s): int(n) for s, n in rows},
                multi_strategy_same_day=sum(1 for v in by.values() if len(v) > 1))


# ── 로트 ──────────────────────────────────────────────────────────────────
@dataclass
class LotPrep:
    lot: LT.LotIn
    i0: int
    path: LT.PathT
    basis: str
    touch: Any
    excl: Tuple[str, ...]
    rights: bool
    closes_before: List[float]
    below: Optional[bool]
    block: Optional[int] = None

    @property
    def day0(self) -> str:
        return LT.day0_class(self.lot, self.basis)


def lot_prep(D: Data, lot: LT.LotIn, horizon: Optional[int] = LT.H) -> LotPrep:
    rows = D.rows.get(lot.code, {})
    i0 = D.pos[lot.d0]
    path = LT.build_path(rows, D.cal, i0, D.i_asof)
    basis, touch = LT.day0_basis(lot, D.minutes.get((lot.code, lot.d0), []))
    i_end = D.i_asof if horizon is None else min(i0 + horizon, D.i_asof)
    excl, rights = LT.lot_exclusion(rows, D.cal, i0, i_end, D.splits.get(lot.code, []), D.rights.get(lot.code, []),
                                    LT.sma_first_date(rows, lot.d0))
    cb = LT.pre_closes(rows, lot.d0)
    bar0 = path[0][2]
    return LotPrep(lot, i0, path, basis, touch, excl, rights, cb,
                   AE.entry_below_sma(cb, bar0.close if bar0 is not None else None))


def run_b(D: Data, p: LotPrep, horizon: int = LT.H) -> LT.ArmOut:
    lt = p.lot
    return LT.b_arm(lt, D.rules[lt.strategy], p.path, D.probes[lt.strategy], p.basis, p.touch, D.aware, horizon)


def run_a(D: Data, p: LotPrep, b: LT.ArmOut, horizon: int = LT.H, no_react_k: int = AE.NO_REACT_K) -> LT.ArmOut:
    lt = p.lot
    return LT.a_arm(lt, D.rules[lt.strategy], p.path, D.probes[lt.strategy], p.basis, p.touch, D.aware,
                    p.closes_before, b, horizon, no_react_k)


def fidelity(D: Data, preps: Sequence[LotPrep], since: date, until: date) -> Tuple[List[Dict[str, Any]], Dict]:
    """§6-8 · 부록 B1 — T3 와 같은 ⓑ(H 로 자르지 않은 경로 · `exit_fidelity_rows` 미사용) vs DB 실제 SELL ·
    분모 = 원문 SQL L(진입일 상한) 로트 중 매수일 범위 ∧ 진입 당일 실제 청산(①) 제외 ·
    사유 매핑 `fidelity8.actual_reason`·`exit_outcome`·`exit_table` 그대로 · 청산일 일치 = |KOSPI 거래일 차| ≤ 1."""
    rows: List[Dict[str, Any]] = []
    for p in preps:
        lt = p.lot
        if not (since <= lt.d0 <= until) or LT.is_day0_live(lt):
            continue
        sim = LT.b_full(lt, D.rules[lt.strategy], p.path, D.probes[lt.strategy], p.basis, p.touch, D.aware)
        ar = F.actual_reason(lt.sell_reason) if lt.sell_ts is not None else "open"
        ad = lt.sell_ts.date() if lt.sell_ts is not None else None
        sd = sim.exit_date if sim.closed else None
        rows.append(dict(strategy=lt.strategy, actual_reason=ar, outcome=F.exit_outcome(ar, ad, sim.reason, sd),
                         same_day_actual="N",
                         date_ok=bool(ad is not None and sd is not None and abs(D.tdist(ad, sd)) <= FID_DATE_TOL)))
    table = {g["strategy"]: g for g in F.exit_table(rows)}
    for s, g in table.items():
        c = g["closed"]
        g["date_ok"] = sum(1 for r in rows if r["strategy"] == s and r["actual_reason"] != "open" and r["date_ok"])
        g["date_rate"] = g["date_ok"] / c if c else None
        g["pass"] = bool(c >= F.FID_MIN_N and g["reason_rate"] is not None and g["reason_rate"] >= F.EXIT_REASON_MIN
                         and g["date_rate"] is not None and g["date_rate"] >= FID_DATE_MIN)
    return rows, table


def t3_blocks(D: Data) -> Dict[date, int]:
    """§7 블록 — 08-07 부터 진입일 상한(위치(D_asof) − 20)까지의 KOSPI 달력을 연속 5거래일씩 · 마지막 <5 는 앞에 합침."""
    return event_blocks(D, D.cal[D.i_asof - LT.H])


def lot_stage(D: Data) -> Dict[str, Any]:
    """봉인·개봉 공통 — 로트 준비 · 데이터 제외 · 충실도 · T3 표본(ⓑ 만)."""
    preps = [lot_prep(D, lt) for lt in D.lots]
    blk = t3_blocks(D)
    for p in preps:
        p.block = blk.get(p.lot.d0)
    fid_rows, fid = fidelity(D, preps, SPLIT_DAY, D_ASOF)
    _, fid_early = fidelity(D, preps, START, SPLIT_DAY - timedelta(days=1))
    passing = {s for s, g in fid.items() if g["pass"]}
    sample = [p for p in preps if not p.excl and p.lot.strategy in passing]
    b = {p.lot.buy_id: run_b(D, p) for p in sample}
    return dict(preps=preps, fid=fid, fid_early=fid_early, fid_rows=fid_rows, passing=passing, sample=sample, b=b)


def sample_shape(sample: Sequence[LotPrep]) -> Dict[str, Any]:
    n = len(sample)
    G = len({p.lot.code for p in sample})
    bl = Counter(p.block for p in sample)
    return dict(n=n, G=G, B=len(bl), per_block=dict(sorted(bl.items())))


# ════════════════════════════════════════════════════════════════════════════
# 6. 서식
# ════════════════════════════════════════════════════════════════════════════
def f4(x: Any, nd: int = 4) -> str:
    if x is None:
        return "-"
    if isinstance(x, float):
        return "nan" if x != x else f"{x:.{nd}f}"
    return str(x)


def table(head: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(f4(c) if isinstance(c, float) else str(c) for c in r) + " |" for r in rows]
    return out


def write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def read_meta() -> Dict[str, Any]:
    if not META.exists():
        return {}
    return json.loads(META.read_text(encoding="utf-8"))


def say(msg: str, logf: Optional[Path] = None) -> None:
    print(msg, flush=True)
    if logf is not None:
        with open(logf, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S.%f} {msg}\n")


# ════════════════════════════════════════════════════════════════════════════
# 7. 단계
# ════════════════════════════════════════════════════════════════════════════
def run_preflight(conn) -> int:
    """개수·존재만 — `guarded_fetch` 만 쓴다(가격·손익 열 0). 지금(10-16 적재 전)은 «D_asof 행 없음 → 거부»가 정상."""
    say("== preflight (개수·존재만 · 가격·손익 열 조회 0)")
    checks = static_checks("preflight")
    for n, ok, d in checks:
        say(f"[{'통과' if ok else '실패'}] {n} — {d}")
    last = guarded_fetch(conn, "SELECT max(date) AS d FROM daily_prices WHERE stock_code = 'KOSPI' AND date <= %s",
                         (D_ASOF.isoformat(),))[0][0]
    say(f"KOSPI 마지막 행(≤ D_asof) = {last}")
    ev = guarded_fetch(conn, wrap(EVENT_SQL, "strategy, count(*) AS n") + " GROUP BY strategy ORDER BY strategy")
    say(f"이벤트(E · 동결 SQL) {sum(int(n) for _, n in ev)}건 — " + " · ".join(f"{s} {n}" for s, n in ev))
    lot_n = guarded_fetch(conn, wrap(LOT_SQL, "count(*) AS n, count(DISTINCT id) AS n_id"))[0]
    lot_by = guarded_fetch(conn, wrap(LOT_SQL, "strategy, count(*) AS n") + " GROUP BY strategy ORDER BY strategy")
    say(f"로트(L · 동결 SQL · 위치(D_asof) = KOSPI 마지막 행 기준 — 10-16 행 없으면 잠정) 행 {lot_n[0]} · "
        f"고유 id {lot_n[1]} — " + " · ".join(f"{s} {n}" for s, n in lot_by))
    codes = sorted({str(r[0]) for r in guarded_fetch(conn, wrap(EVENT_SQL, "DISTINCT stock_code"))}
                   | {str(r[0]) for r in guarded_fetch(conn, wrap(LOT_SQL, "DISTINCT stock_code"))})
    rq = require_asof_rows(conn, codes)
    say(asof_line(rq))
    if last is not None:
        have_last = guarded_fetch(conn, "SELECT count(DISTINCT stock_code) AS n FROM daily_prices WHERE date = %s "
                                        "AND stock_code = ANY(%s)", (str(last), codes))[0][0]
        say(f"(참고) KOSPI 마지막 행 {last} 에 행이 있는 대상 종목 {have_last}/{len(codes)}")
    bad = [n for n, ok, _ in checks if not ok]
    if not rq["ok"]:
        bad.append("D_asof 적재 미완료(KOSPI 행 또는 98%)")
    if bad:
        code = EXIT_DATA if not rq["ok"] else EXIT_STATIC
        say(f"→ 개봉 전제 미충족 — 거부(종료 코드 {code}): " + " · ".join(bad))
        return code
    say("→ 실행 전 확인 통과(개수·존재)")
    return EXIT_OK


def preconditions(conn, stage: str) -> Dict[str, Any]:
    """§12-4 ② · 부록 B2 — sealed/open 공통. 통계 계산 «전». 통과 시 D_asof 상태(«영구 끊김» 목록 포함)를 돌려준다."""
    enforce(static_checks(stage))
    codes = sorted({str(r[0]) for r in fetch(conn, wrap(EVENT_SQL, "DISTINCT stock_code"))}
                   | {str(r[0]) for r in fetch(conn, wrap(LOT_SQL, "DISTINCT stock_code"))})
    rq = require_asof_rows(conn, codes)
    if not rq["kospi"]:
        raise Refuse(EXIT_DATA, f"KOSPI {D_ASOF} 행 없음 — 적재 지연이면 보류(표본 규칙 불변)")
    if not rq["loaded"]:
        raise Refuse(EXIT_DATA, f"D_asof 적재 미완료 — 종목 {rq['n_asof']} < 직전 거래일 {rq['n_prev']} × 98% · 보류")
    return rq


def sealed_payload(conn, D: Data, LS: Dict[str, Any]) -> Dict[str, Any]:
    """봉인 산출물(§12-4 ③) — 🔴 이벤트 팔 R′/D′ · stop_fill_price · ⓐ 없음."""
    units = {h: event_units(D, h, extremes_event=False) for h in HS}
    exs = {h: exclusion_summary(units[h]) for h in HS}
    gates: Dict[str, Any] = {}
    p0: Dict[str, Any] = {}
    for name, kind, thr in (("U10", "R", 0.10), ("V10", "D", -0.10)):
        fu = t12_units(D, units[H_MAIN], kind, thr)
        g1 = ST.t12_fake_gate(fu)
        g = dict(cr1=g1, tool="CR1" if g1["passed"] else None)
        if not g1["passed"]:
            g2 = ST.t12_fake_gate(fu, two_way=True)
            g.update(cgm=g2, tool="CGM" if g2["passed"] else "도구 탈락")
        g["n_lt2"] = sum(1 for u in units[H_MAIN] if not u.code and len(u.usable) == 1)
        gates[name] = g
        ys: List[float] = []
        ws: List[float] = []
        n0 = 0
        inv = 0.0
        n1 = 0
        for u in units[H_MAIN]:
            if u.code or not u.usable:
                continue
            n1 += 1
            inv += 1.0 / len(u.usable)
            for c in u.usable:
                v = control_value(D, u, c, kind)
                ys.append(float(v >= thr) if kind == "R" else float(v <= thr))
                ws.append(1.0 / len(u.usable))
                n0 += 1
        ph = float(np.average(ys, weights=ws)) if ys else float("nan")
        se_plain = math.sqrt(ph * (1 - ph) * (1.0 / n1 + inv / n1 ** 2)) if n1 else float("nan")
        p0[name] = dict(n1=n1, n0=n0, p0=ph, mde_plain=ST.K_MDE * se_plain,
                        mde_tool=ST.K_MDE * g1["se_mean"] if g1["se_mean"] == g1["se_mean"] else float("nan"))
    preps: List[LotPrep] = LS["preps"]
    shape = sample_shape(LS["sample"])
    sd_b = b_sd(LS)
    cut_b = sum(1 for p in LS["sample"] if LS["b"][p.lot.buy_id].cut)
    day0 = Counter(p.day0 for p in preps)
    k0_data_b = sum(1 for p in LS["sample"] if X.FLAG_K0_DATA in LS["b"][p.lot.buy_id].flags)
    base = [(e.id, e.strategy, e.code, e.ts) for e in D.events if e.brid is not None]
    chain_diff = len(LT.episode_keep(base, D.pos) ^ LT.episode_keep_chain(base, D.pos))
    day0_stop = sum(1 for p in preps if LT.is_day0_live(p.lot) and F.actual_reason(p.lot.sell_reason) == X.EXIT_SL)
    return dict(
        units=units, exs=exs, gates=gates, p0=p0, rebuy=rebuy_count(conn, D), integrity=integrity_counts(conn),
        side=side_counts(conn, D), shape=shape, sd_b=sd_b, cut_b=cut_b, mde=ST.mde_t3(sd_b, shape["n"]),
        day0=dict(day0), day0_stop=day0_stop, k0_data_b=k0_data_b, chain_diff=chain_diff,
        excl=Counter("+".join(p.excl) for p in preps if p.excl), rights_lots=sum(1 for p in preps if p.rights),
        below=sum(1 for p in preps if p.below), below_na=sum(1 for p in preps if p.below is None),
        below_sample=sum(1 for p in LS["sample"] if p.below),
        lots_by=Counter((p.lot.strategy, period(p.lot.d0)) for p in preps),
        ev_by=Counter((e.strategy, period(e.d)) for e in D.events))


def render_sealed(meta: Dict[str, Any], D: Data, LS: Dict[str, Any], P: Dict[str, Any]) -> str:
    L: List[str] = ["# 봉인 산출물 — 손절 뒤 급반등 측정(SR1)", "",
                    f"- 사전등록 `docs/prereg_2026-10-09_stoploss_rebound.md` · 동결 blob `{PREREG_FROZEN_BLOB}` · "
                    f"md5 `{PREREG_FROZEN_MD5}`",
                    f"- 해석 부록 `docs/prereg_2026-10-09_stoploss_rebound_amendment_2026-10-09.md` · blob "
                    f"`{AMENDMENT_FROZEN_BLOB}` · md5 `{AMENDMENT_FROZEN_MD5}`",
                    f"- 개봉 전제(부록 B2): {asof_line(meta['asof']) if meta.get('asof') else '-'}",
                    f"- 코드 HEAD `{meta['head']}` · 실행 {meta['run_ts']} · D_asof {D_ASOF} · KOSPI 달력 "
                    f"{D.cal[0]}~{D.cal[-1]}",
                    "- 🔴 이 보고서에는 결과 열이 없다: `stop_fill_price` · 이벤트 팔 R′/D′ · ⓐ 결과 0 (대조 팔 p̂₀ · ⓑ 집계 sd 만).",
                    "- DB 지문(md5 · 개봉 때 같아야 한다): " + " · ".join(f"{k} `{v}`" for k, v in meta["fp"].items()), ""]
    L += ["## 1. 이벤트(E · §3)", ""]
    L += table(["전략", "08-07~08-25", "08-26~", "합"],
               [[s, P["ev_by"].get((s, "08-07~08-25"), 0), P["ev_by"].get((s, "08-26~"), 0),
                 sum(v for (s2, _), v in P["ev_by"].items() if s2 == s)] for s in STRATS])
    L += ["", f"- `손절%` 이지만 `손절 실행%` 아님(정의상 제외 · 개수만): {P['side']['other_stop'] or '0'}",
          f"- 같은 종목·같은 날 복수 전략 손절: {P['side']['multi_strategy_same_day']}",
          f"- ⑨ 정의(N=5 KOSPI 거래일 · distinct BUY) 재매수 — 이 모집단(E) 귀속 BUY {P['rebuy']['rebuy_buys_in_E']} · "
          f"그 손절 이벤트 {P['rebuy']['stops_E_with_rebuy']} · `손절%`⊃`손절 실행%` 차이로 E 밖 손절에 귀속된 BUY "
          f"{P['rebuy']['rebuy_buys_other_stop']}", ""]
    L += ["### 제외 규칙별 개수(첫 탈락 규칙 · X0→X4→X1→X2→X3 · X5 = T1/T2 만)", ""]
    rows = []
    for h in HS:
        e = P["exs"][h]
        c = e["counts"]
        rows.append([h, c.get("X0", 0), c.get("X4", 0), c.get("X1", 0), c.get("X2", 0),
                     f"{c.get('X3', 0)} (점프 {e['ev_jump']} · 분할/무상 {e['ev_corp']})", e["x5"], e["n_t12"],
                     f"{e['ev_x']}/{e['ev_den']} = {f4(e['ev_rate'])}", f"{e['c_x']}/{e['c_den']} = {f4(e['c_rate'])}",
                     f"{f4(e['diff'])}{' ⚠ 비대칭 경고' if e['warn'] else ''}", f"{e['rights_ev']} / {e['rights_c']}"])
    L += table(["h", "X0", "X4", "X1", "X2", "X3", "X5(대조 없음)", "T1/T2 n₁", "이벤트 X2+X3 율", "대조 X2+X3 율",
                "차(이벤트−대조)", "유상증자 이벤트/대조"], rows)
    L += ["", f"- X5 중 SQL 대조 후보 자체가 0 인 이벤트(h=10): {P['exs'][H_MAIN]['x5_sql']} · 대조 C_t 없음으로 뺀 대조 쌍: "
              f"{P['exs'][H_MAIN]['no_base_c']} · 이벤트 자신의 C_t 없음(T1/T2 C_t 표에서 빠짐 · 부록 A8): "
              + " · ".join(f"h={h} {P['exs'][h]['no_base_ev']}" for h in HS),
          f"- X4 해석 차이(부록 A4 — «남긴 이벤트부터» vs «직전 이벤트부터 연쇄»)로 갈리는 이벤트: {P['chain_diff']}", ""]
    L += ["### 이벤트 목록 · 대조 집합(h=10 처리)", ""]
    L += table(["id", "전략", "종목", "손절일", "buy_record_id", "처리(h=10)", "대조(SQL)", "대조(사용)"],
               [[u.ev.id, u.ev.strategy, u.ev.code, u.ev.d, u.ev.brid if u.ev.brid is not None else "NULL",
                 u.code or "포함", ",".join(u.controls) or "-", ",".join(u.usable) or "-"] for u in P["units"][H_MAIN]])
    L += ["", "## 2. 08-07~08-16 SELL 원장 정합성(§12-3 · critic d2.sql 정의)", ""]
    L += table(["범위", "SELL", "BUY 연결", "라벨 불일치", "종목 불일치", "선행 매도", "중복(BUY 당 SELL>1)"],
               [[k, v["sell"], v["linked"], v["label_mismatch"], v["code_mismatch"], v["sell_before_buy"],
                 v["dup_sell_per_buy"]] for k, v in P["integrity"].items()])
    L += ["", "## 3. T3 로트(L · §6)", ""]
    L += table(["전략", "08-07~08-25", "08-26~"],
               [[s, P["lots_by"].get((s, "08-07~08-25"), 0), P["lots_by"].get((s, "08-26~"), 0)] for s in STRATS])
    d0 = P["day0"]
    L += ["", f"- 진입 당일 기준(§6-2): ① 진입 당일 실제 청산 {d0.get(LT.DAY0_LIVE, 0)}(그중 손절 {P['day0_stop']}) · "
              f"② ≤09:05 `D_open` {d0.get(X.BASIS_D_OPEN, 0)} · ③ 분봉 `touch_bar` {d0.get(LT.BASIS_TOUCH, 0)} · "
              f"③ 분봉 없음 `actual`+플래그 {d0.get(X.BASIS_ACTUAL, 0)} · T3 표본 ⓑ 진입 당일 데이터 청산 "
              f"{P['k0_data_b']}(부록 A3 · ⓐ 는 개봉에서)",
          "- 데이터 처리(§6-7 · [진입−60봉, 진입+H]) 제외: " + (" · ".join(f"{k} {v}" for k, v in P["excl"].items())
                                                         or "0") + f" · 유상증자 있음(제외 안 함) {P['rights_lots']}",
          f"- 진입 시 SMA60 아래 로트: {P['below']}(L 전체 · 모름 {P['below_na']}) · T3 표본 안 {P['below_sample']}", ""]
    L += ["### 충실도 게이트(§6-8 · ⓑ 전체 경로 vs DB SELL · 매수일 ≥ 08-26 · ① 제외)", ""]
    frow = lambda g: [g["strategy"], g["closed"], f4(g["reason_rate"]), f4(g["date_rate"]), f4(g["full_rate"]),  # noqa: E731
                      "통과" if g.get("pass") else ("판정 불가(n<5)" if g["closed"] < F.FID_MIN_N else "미달")]
    L += table(["전략", "분모(실제 청산)", "사유 계열 일치율", "청산일 ±1 일치율", "정확 일치율(full_rate)", "게이트"],
               [frow(LS["fid"][s]) for s in STRATS if s in LS["fid"]])
    L += ["", "- 08-07~08-25 매수분(따로 인쇄 · 게이트 아님):", ""]
    L += table(["전략", "분모", "사유 계열", "청산일 ±1", "정확"],
               [frow(LS["fid_early"][s])[:5] for s in STRATS if s in LS["fid_early"]])
    sh = P["shape"]
    L += ["", f"- 충실도 통과 전략: {', '.join(sorted(LS['passing'])) or '없음 → T3 = 판정 불가'}",
          f"- **T3 n = {sh['n']} · G = {sh['G']} · B = {sh['B']}** · 블록별 로트 수 {sh['per_block']}", ""]
    L += ["## 4. T1/T2 도구 게이트(봉인 · 대조 팔 값만 · 인쇄용)", ""]
    grow = []
    for nm, g in P["gates"].items():
        c1 = g["cr1"]
        c2 = g.get("cgm")
        grow.append([nm, c1["n_units"], g["n_lt2"], f4(c1["rate"]), "합격" if c1["passed"] else "불합격",
                     f4(c2["rate"]) if c2 else "-", g["tool"]])
    L += table(["지표", "가짜 재료 이벤트(|C|≥2)", "|C|=1 제외", "CR1 p<0.10 비율", "CR1", "2원 CGM 비율", "도구"], grow)
    L += ["", "## 5. MDE 선인쇄(§8 · 결과 전)", ""]
    m = P["mde"]
    L += [f"- T3: n {sh['n']} · B {sh['B']} · G {sh['G']} · ⓑ 로트 수익률 집계 sd(판 M · H=20) **{f4(P['sd_b'])}**%p "
          f"(영구 끊김 ⓑ 로트 {P['cut_b']}) → MDE = 2.80·sd/√n = {f4(m['mde'])} · DEFF2 {f4(m['deff2'])} · DEFF4 "
          f"{f4(m['deff4'])} · «없음» 가능(MDE ≤ θ₃ 0.4) = {'예' if m['mde'] == m['mde'] and m['mde'] <= ST.THETA3 else '아니오'}"]
    for nm, v in P["p0"].items():
        L.append(f"- {nm}: n₁ {v['n1']} · n₀ {v['n0']} · 대조 팔 p̂₀ {f4(v['p0'])} → 소박판 MDE {f4(v['mde_plain'])} · "
                 f"도구판 MDE(2.80 × 가짜 SE 평균) {f4(v['mde_tool'])}")
    L += ["", "🔴 판정 언어 없음 — 개봉 전 산출물."]
    return "\n".join(L) + "\n"


def b_sd(LS: Dict[str, Any]) -> float:
    """ⓑ 로트 수익률(판 M · H=20) 집계 sd — 로트별 값은 인쇄하지 않는다(§8)."""
    rb = np.array([LS["b"][p.lot.buy_id].ret_M for p in LS["sample"]], dtype=float)
    return float(rb.std(ddof=1)) if len(rb) > 1 else float("nan")


def check_numbers(LS: Dict[str, Any]) -> Dict[str, Any]:
    """개봉 때 다시 계산해 봉인 값과 같아야 하는 값(DART V5 선례) — ⓐ·이벤트 팔 결과 없음."""
    sd = b_sd(LS)
    return json.loads(json.dumps(dict(
        shape=sample_shape(LS["sample"]), sd_b=round(sd, 9) if sd == sd else None, passing=sorted(LS["passing"]),
        fid={s: [g["closed"], g["reason_rate"], g["date_rate"], g["full_rate"]] for s, g in LS["fid"].items()}),
        default=str))


def sealed_numbers(LS: Dict[str, Any], P: Dict[str, Any]) -> Dict[str, Any]:
    return dict(check_numbers(LS), gates={k: v["tool"] for k, v in P["gates"].items()})


def run_sealed(conn) -> int:
    if "open" in read_meta():
        raise Refuse(EXIT_ORDER, "이미 개봉됨(run_meta.json open) — 봉인 단계를 다시 돌리지 않는다")
    rq = preconditions(conn, "sealed")
    D, cnt = load_all(conn, "sealed")
    fp = fingerprint(conn, cnt["codes"], list(D.minutes))
    LS = lot_stage(D)
    P = sealed_payload(conn, D, LS)
    meta = dict(head=head_sha(), run_ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fp=fp, asof=rq)
    write_lf(SEALED_MD, render_sealed(meta, D, LS, P))
    m = read_meta()
    m["sealed"] = dict(meta, numbers=sealed_numbers(LS, P), n_events=cnt["n_events"], n_lots=cnt["n_lots"],
                       prereg_blob=PREREG_FROZEN_BLOB, amendment_blob=AMENDMENT_FROZEN_BLOB)
    write_lf(META, json.dumps(m, ensure_ascii=False, indent=2, default=str) + "\n")
    print(f"봉인 산출물 → {SEALED_MD} (커밋 뒤 개봉)")
    return EXIT_OK


# ── 개봉 ──────────────────────────────────────────────────────────────────
def reopen_check(m: Dict[str, Any], log_text: str, head: str, reason: Optional[str]) -> Dict[str, Any]:
    """부록 B3 — 표식 뒤 중단된 개봉의 1회 재개봉 허용 조건. 허용이면 기록(dict), 아니면 Refuse."""
    o = m["open"]
    base = f"1회 실행 표식 있음(run_meta.json open = {o.get('started_at')})"
    if o.get("finished_at"):
        raise Refuse(EXIT_ORDER, f"{base} · 개봉 완료 — 두 번째 개봉 거부")
    if o.get("reopen"):
        raise Refuse(EXIT_ORDER, f"{base} · 재개봉 1회 이미 사용({o['reopen'].get('at')}) — 거부")
    if any(T3_TAG in ln for ln in log_text.splitlines()):
        raise Refuse(EXIT_ORDER, f"{base} · open_log 에 {T3_TAG} 결과 줄이 있다 — 결과를 본 뒤라 재개봉 금지(부록 B3)")
    if not reason:
        raise Refuse(EXIT_ORDER, f"{base} · {T3_TAG} 줄 없이 중단 — 수정 커밋 뒤 --reopen-reason 으로 1회 재개봉 가능(부록 B3)")
    if head == o.get("head"):
        raise Refuse(EXIT_ORDER, f"{base} · 수정 커밋이 없다(HEAD = 중단 때 {head[:10]}) — 재개봉 거부")
    return dict(reason=reason, interrupted_head=o.get("head"), fix_sha=head,
                at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def open_guard(conn, D: Data, cnt: Dict[str, Any], reopen_reason: Optional[str] = None
               ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """개봉 전용 확인 — 봉인 산출물 커밋 · 1회 실행 표식(부록 B3 재개봉 조건) · DB 지문 = 봉인 지문."""
    if not SEALED_MD.exists() or _git("ls-files", "--error-unmatch", str(SEALED_MD)).returncode != 0:
        raise Refuse(EXIT_ORDER, "results/sealed_report.md 가 없거나 커밋되지 않았다 — 봉인 단계와 그 커밋이 먼저(§12-4 ③)")
    m = read_meta()
    reopen: Optional[Dict[str, Any]] = None
    if "open" in m:
        log_text = OPEN_LOG.read_text(encoding="utf-8") if OPEN_LOG.exists() else ""
        reopen = reopen_check(m, log_text, head_sha(), reopen_reason)
    elif reopen_reason:
        raise Refuse(EXIT_ORDER, "중단된 개봉이 없다 — --reopen-reason 은 쓰지 않는다")
    if "sealed" not in m:
        raise Refuse(EXIT_ORDER, "run_meta.json 에 봉인 기록이 없다")
    fp = fingerprint(conn, cnt["codes"], list(D.minutes))
    if fp != m["sealed"]["fp"]:
        diff = [k for k in fp if fp[k] != m["sealed"]["fp"].get(k)]
        raise Refuse(EXIT_FINGERPRINT, f"DB 지문이 봉인 때와 다르다({diff}) — 데이터 소급 수정 · 통계 전 중단")
    return m, reopen


def mark_open(m: Dict[str, Any], reopen: Optional[Dict[str, Any]] = None) -> None:
    """1회 실행 표식 — 첫 개봉이면 새로 · 부록 B3 재개봉이면 원 표식에 재개봉 기록(사유·중단 HEAD·수정 SHA)을 더한다."""
    if reopen is not None:
        m["open"]["reopen"] = reopen
    else:
        m["open"] = dict(started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), head=head_sha())
    write_lf(META, json.dumps(m, ensure_ascii=False, indent=2, default=str) + "\n")


def _mean(xs: Sequence[float]) -> float:
    return float(np.mean(xs)) if len(xs) else float("nan")


def _q(xs: Sequence[float]) -> List[float]:
    if not len(xs):
        return [float("nan")] * 5
    return [float(x) for x in np.percentile(np.asarray(xs, float), [5, 25, 50, 75, 95])]


def t3_open(D: Data, LS: Dict[str, Any], logf: Path) -> Dict[str, Any]:
    """T3 — ⓐ 계산 → 판마다 게이트(로그) → 진짜 p·CI(로그) → 라벨."""
    sample: List[LotPrep] = LS["sample"]
    A = {p.lot.buy_id: run_a(D, p, LS["b"][p.lot.buy_id]) for p in sample}
    codes = [p.lot.code for p in sample]
    blocks = [int(p.block) for p in sample]
    deltas = {k: [getattr(A[p.lot.buy_id], f"ret_{k}") - getattr(LS["b"][p.lot.buy_id], f"ret_{k}") for p in sample]
              for k in ("L", "M")}
    panels: Dict[str, ST.T3Panel] = {}
    for k in ("L", "M"):
        say(f"[게이트] 판 {k} — 자기 표본 게이트 시작(진짜 p 보다 먼저)", logf)
        panels[k] = ST.t3_gate(deltas[k], codes, blocks, lambda s, k=k: say(f"  판 {k} {s}", logf))
    say("[게이트] 두 판 게이트 확정 — 이제 진짜 검정", logf)
    for k in ("L", "M"):
        ST.t3_test(panels[k], deltas[k], codes, blocks)
        t = panels[k].test
        if t is None:
            say(f"[T3] 판 {k}: 도구 탈락 · 검정 없음", logf)
        else:
            say(f"[T3] 판 {k}: tool {panels[k].tool} · Δ̄ {t['mean']:+.4f}%p · SE {t['se']:.4f} · p {t['p']:.4f} · "
                f"95% CI [{t['ci_lo']:+.4f}, {t['ci_hi']:+.4f}]", logf)
    shape = sample_shape(sample)
    v = ST.decide(panels, bool(LS["passing"]), shape["n"], shape["G"])
    say(f"[T3] 라벨: {v.label}{(' — ' + v.reason) if v.reason else ''}{(' — 「' + v.text + '」') if v.text else ''}",
        logf)
    return dict(A=A, deltas=deltas, panels=panels, verdict=v, shape=shape)


def render_t3_prints(D: Data, LS: Dict[str, Any], T: Dict[str, Any], extra: Dict[str, Any]) -> List[str]:
    sample: List[LotPrep] = LS["sample"]
    A, B = T["A"], LS["b"]
    L: List[str] = []

    def grp(key: Callable[[LotPrep], Any]) -> List[List[Any]]:
        g: Dict[Any, List[LotPrep]] = defaultdict(list)
        for p in sample:
            g[key(p)].append(p)
        return [[k, len(v), _mean([A[p.lot.buy_id].ret_M - B[p.lot.buy_id].ret_M for p in v]),
                 _mean([A[p.lot.buy_id].ret_L - B[p.lot.buy_id].ret_L for p in v])] for k, v in sorted(g.items(), key=str)]

    L += ["### 인쇄 항목(판정 언어 없음)", ""]
    ra = [A[p.lot.buy_id].ret_M for p in sample]
    rb = [B[p.lot.buy_id].ret_M for p in sample]
    L += [f"- 판 M 평균 r_a {f4(_mean(ra))} · r_b {f4(_mean(rb))} · 비용 차감(−{COST}) r_a {f4(_mean(ra) - COST)} · "
          f"r_b {f4(_mean(rb) - COST)} (%) · 영구 끊김 로트 ⓐ {sum(1 for p in sample if A[p.lot.buy_id].cut)} · "
          f"ⓑ {sum(1 for p in sample if B[p.lot.buy_id].cut)}",
          f"- ⓐ 가 더 오래 든 일수(평균 hold_a − hold_b): "
          f"{f4(_mean([(A[p.lot.buy_id].hold or 0) - (B[p.lot.buy_id].hold or 0) for p in sample]))}",
          "- ⓐ 트리거: " + " · ".join(f"{k} {v}" for k, v in sorted(Counter(
              t for p in sample for t in A[p.lot.buy_id].triggers).items())),
          f"- 진입 당일 데이터 청산(부록 A3) ⓐ {sum(1 for p in sample if X.FLAG_K0_DATA in A[p.lot.buy_id].flags)} · "
          f"ⓑ {sum(1 for p in sample if X.FLAG_K0_DATA in B[p.lot.buy_id].flags)}", ""]
    for title, key in (("전략별", lambda p: p.lot.strategy), ("구간별(08-26 경계)", lambda p: period(p.lot.d0)),
                       ("진입일 블록별", lambda p: p.block), ("ⓑ 청산 사유별", lambda p: B[p.lot.buy_id].reason),
                       ("ⓐ 청산 사유별", lambda p: A[p.lot.buy_id].reason)):
        L += [f"- {title}", ""] + table(["키", "n", "Δ̄ 판 M", "Δ̄ 판 L"], grp(key)) + [""]
    stop = [p for p in sample if B[p.lot.buy_id].reason == X.EXIT_SL]
    L += [f"- ⓑ 손절 로트 한정판: n {len(stop)} · Δ̄ 판 M "
          f"{f4(_mean([A[p.lot.buy_id].ret_M - B[p.lot.buy_id].ret_M for p in stop]))}"]
    for nm, v in extra.items():
        L.append(f"- {nm}: n {v['n']} · Δ̄ 판 M {f4(v['M'])} · 판 L {f4(v['L'])}")
    return L


def t3_variants(D: Data, LS: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """인쇄만 — (c) 5일판 · D_asof 전체 경로판(진입일 상한 없음 · 원문에서 상한 한 줄만 뺀 SQL = `D.lots_full`)."""
    out: Dict[str, Dict[str, Any]] = {}
    sample: List[LotPrep] = LS["sample"]
    a5 = [(run_a(D, p, LS["b"][p.lot.buy_id], no_react_k=5), LS["b"][p.lot.buy_id]) for p in sample]
    out["(c) 무반응 5일판"] = dict(n=len(a5), M=_mean([a.ret_M - b.ret_M for a, b in a5]),
                               L=_mean([a.ret_L - b.ret_L for a, b in a5]))
    full: List[Tuple[LT.ArmOut, LT.ArmOut]] = []
    for lt in D.lots_full:
        if lt.strategy not in LS["passing"] or lt.d0 not in D.pos:
            continue
        p = lot_prep(D, lt, horizon=None)
        if p.excl:
            continue
        hz = len(p.path) - 1
        b = run_b(D, p, hz)
        full.append((run_a(D, p, b, hz), b))
    out["D_asof 전체 경로판(진입일 상한 없음)"] = dict(n=len(full), M=_mean([a.ret_M - b.ret_M for a, b in full]),
                                             L=_mean([a.ret_L - b.ret_L for a, b in full]))
    return out


def _vol_prev(D: Data, code: str, d: date) -> Optional[float]:
    r = _row(D, code, D.cal[D.pos[d] - 1])
    return r.vol20 if r is not None else None


def vol_tertiles(D: Data, t12: Sequence[EvUnit]) -> List[str]:
    """§4 변동성 층 — volatility_20d 의 t−1 값 · 경계 = 이벤트+대조 합친 집합의 삼분위 · 층별 δ(U₁₀ · C_t 기준)."""
    ev = [(u, _vol_prev(D, u.ev.code, u.ev.d)) for u in t12 if u.win.hi is not None]
    cs = [(u, c, _vol_prev(D, c, u.ev.d)) for u in t12 for c in u.usable]
    vv = [v for _, v in ev if v is not None] + [v for _, _, v in cs if v is not None]
    if len(vv) < 3:
        return ["- 변동성 층: 값 부족"]
    q1, q2 = (float(x) for x in np.percentile(vv, [100 / 3, 200 / 3]))

    def tert(x: Optional[float]) -> Optional[int]:
        return None if x is None else (0 if x <= q1 else 1 if x <= q2 else 2)

    def ind(x: Optional[float], kind: str) -> float:
        return float(x >= 0.10) if kind == "R" else float(x <= -0.10)

    rows = []
    for nm, kind in (("U₁₀", "R"), ("V₁₀", "D")):
        for k in range(3):
            e1 = [ind(LT.rise(u.win, u.base_t) if kind == "R" else LT.fall(u.win, u.base_t), kind)
                  for u, v in ev if tert(v) == k]
            cy = [(ind(control_value(D, u, c, kind), kind), 1.0 / len(u.usable)) for u, c, v in cs if tert(v) == k]
            c_mean = float(np.average([y for y, _ in cy], weights=[w for _, w in cy])) if cy else float("nan")
            rows.append([nm, k + 1, len(e1), len(cy), f4(_mean(e1)), f4(c_mean), f4(_mean(e1) - c_mean)])
    return ([f"- 변동성 층(volatility_20d t−1 · 이벤트+대조 합친 삼분위 경계 {f4(q1)} / {f4(q2)})", ""]
            + table(["지표", "층", "이벤트 n", "대조 쌍", "이벤트 비율", "대조 비율(가중)", "δ"], rows))


def _dist_row(name: str, R_: Sequence[float], D_: Sequence[float], w: Optional[Sequence[float]] = None) -> List[Any]:
    """분위수(5·25·50·75·95% · 비가중) · 평균 · P(R≥10%) · P(R≥20%) · P(D≤−10%) — w 가 있으면 평균·비율은 가중."""
    def avg(xs: Sequence[float]) -> float:
        if not len(xs):
            return float("nan")
        return float(np.average(xs, weights=w)) if w is not None else float(np.mean(xs))
    return ([name, len(R_)] + [f4(x) for x in _q(R_)]
            + [f4(avg(R_)), f4(avg([float(x >= .10) for x in R_])), f4(avg([float(x >= .20) for x in R_])),
               f4(avg([float(x <= -.10) for x in D_]))])


DIST_HEAD = ["집합", "n", "q05", "q25", "q50", "q75", "q95", "평균", "P(R≥10%)", "P(R≥20%)", "P(D≤−10%)"]


def t12_open(D: Data, gates_sealed: Dict[str, str], rebuy_ids: Sequence[int], asym: Dict[int, bool]) -> List[str]:
    """T1/T2 기술통계(§4) — 판정 언어 금지 · p(원값)·95% CI·도구 게이트 상태만."""
    L: List[str] = ["## T1/T2 기술통계(인쇄만 · 라벨 없음)", ""]
    blk = event_blocks(D, D.cal[D.i_asof - H_MAIN])
    pers = ("08-07~08-25", "08-26~")
    groups = ([("합", lambda u: True)] + [(s, (lambda u, s=s: u.ev.strategy == s)) for s in STRATS]
              + [(pp, (lambda u, pp=pp: period(u.ev.d) == pp)) for pp in pers]
              + [(f"{s} · {pp}", (lambda u, s=s, pp=pp: u.ev.strategy == s and period(u.ev.d) == pp))
                 for s in STRATS for pp in pers])
    for h in HS:
        units = event_units(D, h, extremes_event=True)
        inc = [u for u in units if u.code == ""]
        warn = " · ⚠ 비대칭 경고(이벤트 X2+X3 제외율 − 대조 > 2%p)" if asym.get(h) else ""
        L += [f"### h = {h}{warn}", "", "- 이벤트 팔 `P_stop` 기준 R_h·D_h", ""]
        rows = []
        for gname, sel in groups:
            us = [u for u in inc if sel(u) and u.ev.stop_px]
            rows.append(_dist_row(gname, [x for x in (LT.rise(u.win, u.ev.stop_px) for u in us) if x is not None],
                                  [x for x in (LT.fall(u.win, u.ev.stop_px) for u in us) if x is not None]))
        L += table(DIST_HEAD, rows) + [""]
        t12 = [u for u in inc if u.usable and u.base_t]
        L += [f"- 이벤트 자신의 C_t 없어 아래 C_t 표에서 빠진 이벤트(부록 A8): "
              f"{sum(1 for u in inc if u.usable and not u.base_ok)}", ""]
        er = [LT.rise(u.win, u.base_t) for u in t12 if u.win.hi is not None]
        ed = [LT.fall(u.win, u.base_t) for u in t12 if u.win.lo is not None]
        cr = [(control_value(D, u, c, "R"), control_value(D, u, c, "D"), 1.0 / len(u.usable)) for u in t12
              for c in u.usable]
        L += ["- C_t 기준 — 이벤트 R′·D′ vs 대조(같은 날 같은 전략 미손절 보유 · 평균·비율은 1/|C(i)| 가중)", ""]
        L += table(DIST_HEAD, [_dist_row("이벤트(C_t)", er, ed),
                               _dist_row("대조(C_t)", [r for r, _, _ in cr], [d for _, d, _ in cr],
                                         [w for _, _, w in cr])]) + [""]
        rows2 = []
        for nm, kind, thr in (("U(R′≥+10%)", "R", 0.10), ("U20(R′≥+20%)", "R", 0.20), ("V(D′≤−10%)", "D", -0.10)):
            y1, c1, b1, y0, c0, b0, w0 = [], [], [], [], [], [], []
            for u in t12:
                ev = LT.rise(u.win, u.base_t) if kind == "R" else LT.fall(u.win, u.base_t)
                if ev is None:
                    continue
                y1.append(float(ev >= thr) if kind == "R" else float(ev <= thr))
                c1.append(u.ev.code)
                b1.append(blk.get(u.ev.d, -1))
                for c in u.usable:
                    v = control_value(D, u, c, kind)
                    y0.append(float(v >= thr) if kind == "R" else float(v <= thr))
                    c0.append(c)
                    b0.append(blk.get(u.ev.d, -1))
                    w0.append(1.0 / len(u.usable))
            if len(y1) < 2 or not w0:
                rows2.append([nm, len(y1), "-", "-", "-", "-", "-"])
                continue
            r = ST._p2(y1, c1, y0, c0, w0)
            ci = f"p {f4(ST.p2_two_sided(r))} · CI [{f4(r['delta'] - ST.Z975 * r['se'])}, {f4(r['delta'] + ST.Z975 * r['se'])}]"
            key = f"{'U' if kind == 'R' else 'V'}10" if (h == H_MAIN and thr in (0.10, -0.10)) else None
            gs = gates_sealed.get(key) if key else None
            if gs == "CGM":
                r2 = ST.p2_cgm(y1, c1, b1, y0, c0, b0, w0)
                crit = ST.t_crit(int(r2["Gb"]) - 1) if r2["Gb"] >= 2 else float("nan")
                ci += (f" · 2원 CGM p {f4(r2['p'])} · CI [{f4(r2['delta'] - crit * r2['se'])}, "
                       f"{f4(r2['delta'] + crit * r2['se'])}]")
            rows2.append([nm, len(y1), f4(float(np.mean(y1))), f4(float(np.average(y0, weights=w0))), f4(r["delta"]),
                          ci, gs or "(게이트 대상 아님)"])
        L += ["- δ = 이벤트 비율 − 대조 비율(C_t 기준) · p = P2 부품 CR1 원값(도구 CGM 이면 2원 병기)", ""]
        L += table(["지표", "n₁", "이벤트 비율", "대조 비율", "δ", "p · 95% CI", "도구 게이트(봉인)"], rows2)
        if h == H_MAIN:
            L += [""] + vol_tertiles(D, t12)
            ids = set(rebuy_ids)
            rb = [u for u in inc if u.ev.id in ids and u.ev.stop_px]
            Rr = [x for x in (LT.rise(u.win, u.ev.stop_px) for u in rb) if x is not None]
            L += ["", f"- «이미 본 값 — 인쇄만»(§10): ⑨ 재매수 있었던 손절 이벤트의 R₁₀(P_stop) n {len(Rr)} · 분위수 "
                      + " / ".join(f4(x) for x in _q(Rr)) + " (판정 불가)"]
        L += [""]
    return L


def render_results(meta: Dict[str, Any], T: Dict[str, Any], prints: List[str], t12: List[str]) -> str:
    v = T["verdict"]
    sh = T["shape"]
    ro = meta.get("reopen")
    L = ["# RESULTS — 손절 뒤 급반등 측정(SR1 · T3 단독 주 검정)", "",
         f"- 사전등록 blob `{PREREG_FROZEN_BLOB}` · 부록 blob `{AMENDMENT_FROZEN_BLOB}` · 코드 HEAD `{meta['head']}` · "
         f"개봉 {meta['run_ts']} · D_asof {D_ASOF}",
         "- 로그 순서(게이트 → 진짜 p) = `results/open_log.txt`",
         f"- 개봉 전제(부록 B2): {asof_line(meta['asof']) if meta.get('asof') else '-'}"]
    if ro:
        L.append(f"- ⚠ **이탈: 재개봉**(부록 B3) — 사유 「{ro['reason']}」 · 중단 때 HEAD `{ro['interrupted_head']}` · "
                 f"수정 커밋 `{ro['fix_sha']}` · {ro['at']}")
    L += ["",
         "## 1. 자기 표본 게이트(§7 · 진짜 p 보다 먼저)", ""]
    for k, pn in T["panels"].items():
        L.append(f"- 판 {k}: B = {pn.B} · " + (" · ".join(
            f"{g.tool} (S) {g.s_rate:.4f} {'합격' if g.s_pass else '불합격'} / (F) {g.f_count}/{g.f_total}(≤{g.f_max}) "
            f"{'합격' if g.f_pass else '불합격'}" for g in pn.gates) or "게이트 생략(B<5)") + f" → 도구 {pn.tool}")
    L += ["", "## 2. T3 검정 · 라벨(§9)", ""]
    rows = []
    for k, pn in T["panels"].items():
        t = pn.test or {}
        rows.append([k, sh["n"], sh["G"], pn.B, pn.tool, f4(t.get("mean")), f4(t.get("se")), f4(t.get("p")),
                     f"[{f4(t.get('ci_lo'))}, {f4(t.get('ci_hi'))}]", ST.panel_outcome(pn)[0]])
    L += table(["판", "n", "G", "B", "도구", "Δ̄(%p)", "SE", "p", "95% CI", "판 결과"], rows)
    L += ["", f"**라벨: {v.label}**" + (f" — {v.reason}" if v.reason else "") + (f"\n\n「{v.text}」" if v.text else ""),
          "", "- 룰 변경 근거 아님(§11-3) · 일봉 근사 · gross · 단일 국면.", ""]
    return "\n".join(L + prints + [""] + t12) + "\n"


def run_open(conn, reopen_reason: Optional[str] = None) -> int:
    rq = preconditions(conn, "open")
    D, cnt = load_all(conn, "open")
    m, reopen = open_guard(conn, D, cnt, reopen_reason)
    LS = lot_stage(D)
    sealed = m["sealed"]["numbers"]
    now = check_numbers(LS)
    for k in now:
        if now[k] != sealed.get(k):
            raise Refuse(EXIT_FINGERPRINT, f"봉인 값 {k} 가 개봉 재계산과 다르다 — 중단(표식 전)")
    mark_open(m, reopen)                                              # 1회 실행 표식 — ⓐ·통계 «전»
    logf = OPEN_LOG
    say(f"[개봉] {'재개봉(부록 B3)' if reopen else '시작'} · HEAD {head_sha()} · 봉인 지문 일치 · "
        "봉인 값(n·G·B·충실도·ⓑ sd) 재계산 일치", logf)
    T = t3_open(D, LS, logf)
    extra = t3_variants(D, LS)
    prints = render_t3_prints(D, LS, T, extra)
    asym = {h: exclusion_summary(event_units(D, h, extremes_event=False))["warn"] for h in HS}
    t12 = t12_open(D, sealed.get("gates", {}), rebuy_count(conn, D)["stop_ids"], asym)
    meta = dict(head=head_sha(), run_ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), asof=rq, reopen=reopen)
    out = RESULTS / f"RESULTS_{datetime.now():%Y-%m-%d}.md"
    write_lf(out, render_results(meta, T, prints, t12))
    m = read_meta()
    m["open"].update(finished_at=meta["run_ts"], results=out.name, label=T["verdict"].label)
    write_lf(META, json.dumps(m, ensure_ascii=False, indent=2, default=str) + "\n")
    say(f"[개봉] 끝 → {out.name}", logf)
    return EXIT_OK


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="손절 뒤 급반등 측정(SR1) 러너")
    ap.add_argument("--stage", choices=("preflight", "sealed", "open"), required=True)
    ap.add_argument("--reopen-reason", default=None, help="부록 B3 — [T3] 줄 없이 중단된 개봉의 1회 재개봉 사유")
    a = ap.parse_args(argv)
    try:
        conn = connect()
    except Exception as e:  # noqa: BLE001
        print(f"DB 접속 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_DATA
    try:
        if a.stage == "preflight":
            return run_preflight(conn)
        if a.stage == "sealed":
            return run_sealed(conn)
        return run_open(conn, a.reopen_reason)
    except Refuse as r:
        print(f"[거부 · 종료 코드 {r.code}] {r.reason}", file=sys.stderr)
        return r.code
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
