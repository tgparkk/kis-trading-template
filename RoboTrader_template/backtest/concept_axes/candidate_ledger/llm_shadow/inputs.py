"""§2 시점 · §3 입력 계약 🔒 — 유니버스 · (A) 새 항목 · PIT 컷오프 · 공시/기사 제목 · 재무 · 가격 맥락.

- 순수 함수(컷오프·정리·서식·PIT)는 DB 없이 테스트한다. `PgInputs` 는 SELECT 만(§1).
- 🔴 `news_stock.news_id = news.id` (text `news.news_id` 조인 금지 · §3-6) · 날짜는 `rcept_dt` 만(§13-5).
- 🔴 PIT = `news.published_at < D+1 00:00` ∧ `news.created_at < T 08:30`(KST · 두 팔 공통 · §3-5).
  T = D 다음 거래일(보충 실행도 같은 T ⇒ 같은 입력).
- 12-31 휴장: `utils/korean_holidays` 정적 목록에 없어(KIS 동기화 캐시에만 있음) 여기서 로컬 보강한다(utils 는 안 고침).
"""
from __future__ import annotations

import calendar as _cal
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from backtest.concept_axes.candidate_ledger.dart_events import dart_tags as DT
from backtest.concept_axes.replayer.loader import CALENDAR_TICKER, STOCK_ONLY, classify_exclusions
from utils import korean_holidays as KH

from . import settings as S

CAL_START = "2026-01-01"
_WS = re.compile(r"\s+")
_LEAD_BRACKET = re.compile(r"^\[[^\]]*\]\s*")


# ── 거래일 ───────────────────────────────────────────────────────────────────────
def is_trading_day(d: date) -> bool:
    if d.month == 12 and d.day == 31:           # 로컬 보강(연말 휴장)
        return False
    return not KH.is_holiday(datetime(d.year, d.month, d.day))


def next_trading_day(d: date) -> date:
    x = d + timedelta(days=1)
    for _ in range(30):
        if is_trading_day(x):
            return x
        x += timedelta(days=1)
    raise RuntimeError(f"{d} 뒤 30일 안에 거래일 없음")


class Calendar:
    """KOSPI 달력(§1-3-b SSOT) — 과거 거래일 순번·창 계산."""

    def __init__(self, dates: Sequence[date]):
        self.dates = sorted(set(dates))
        self._i = {d: i for i, d in enumerate(self.dates)}

    def idx(self, d: date) -> int:
        return self._i[d]

    def has(self, d: date) -> bool:
        return d in self._i

    def prev(self, d: date) -> date:
        return self.dates[self._i[d] - 1]

    def back(self, d: date, n: int) -> date:
        """d 포함 최근 n 거래일 창의 첫날."""
        return self.dates[max(0, self._i[d] - (n - 1))]

    def between(self, a: date, b: date) -> List[date]:
        return [x for x in self.dates if a <= x <= b]


# ── §3-5 PIT 컷오프 ──────────────────────────────────────────────────────────────
def cutoffs(D: date, T: date) -> Tuple[datetime, datetime]:
    """(published_at 상한 = D+1 00:00, created_at 상한 = T 08:30) — 둘 다 «미만»."""
    return datetime.combine(D + timedelta(days=1), time(0, 0)), datetime.combine(T, time(*S.CUTOFF_HHMM))


def news_visible(published_at: datetime, created_at: datetime, D: date, T: date) -> bool:
    pub_end, cre_end = cutoffs(D, T)
    return published_at < pub_end and created_at < cre_end


def a_press_window(D_prev: date, D: date) -> Tuple[datetime, datetime]:
    """(A) 새 기사 창 = [D′+1 00:00, D+1 00:00)."""
    return (datetime.combine(D_prev + timedelta(days=1), time(0, 0)),
            datetime.combine(D + timedelta(days=1), time(0, 0)))


def new_item_codes(disc_rows: Iterable[Tuple[str, str, date, str]],
                   press_rows: Iterable[Tuple[str, datetime, datetime]],
                   D_prev: date, D: date, T: date, U: Set[str]) -> Tuple[Set[str], Set[str], Set[str]]:
    """(A) 자료 변경(§3-2) → (전체, 공시로, 기사로).

    공시 = `dart_disclosures` B·I · `rcept_dt ∈ (D′, D]` · ① `is_corr=False`(dart_tags 규칙 · 태그 무관).
    기사 = `source <> 'dart'` · `published_at ∈ [D′+1, D+1)` ∧ `created_at < T 08:30`.
    """
    disc: Set[str] = set()
    for code, report_nm, rcept_dt, ty in disc_rows:
        if code in U and ty in ("B", "I") and D_prev < rcept_dt <= D and not DT.tag_of(report_nm or "")[1]:
            disc.add(code)
    lo, hi = a_press_window(D_prev, D)
    _, cre_end = cutoffs(D, T)
    press = {code for code, pub, cre in press_rows if code in U and lo <= pub < hi and cre < cre_end}
    return disc | press, disc, press


# ── §3-6 · §3-7 · §3-8 제목 ─────────────────────────────────────────────────────
def clean_ws(t: str) -> str:
    return _WS.sub(" ", t or "").strip()


def clean_dart_title(t: str) -> str:
    """NewsQuant `[corp_name] report_nm` → 앞 `[…] ` 하나 떼고 공백 연속 → 1칸."""
    return clean_ws(_LEAD_BRACKET.sub("", (t or "").strip(), count=1))


def select_lines(rows: Iterable[Tuple[datetime, int, str, Optional[str]]], kind: str,
                 limit: int) -> Tuple[List[str], int]:
    """rows = (published_at, news.id, title, source). 같은 제목 중복 제거(최신 유지) · 최신순 · 상한 · 120자.

    반환 (줄 목록, 전체 건수 = 중복 제거 뒤 · 상한 전).
    """
    seen: Set[str] = set()
    out: List[Tuple[datetime, int, str, Optional[str]]] = []
    for pub, nid, title, src in sorted(rows, key=lambda r: (r[0], r[1]), reverse=True):
        t = clean_dart_title(title) if kind == "dart" else clean_ws(title)
        if not t or t in seen:
            continue
        seen.add(t)
        out.append((pub, nid, t, src))
    lines = []
    for pub, _, t, src in out[:limit]:
        t = t[:S.TITLE_MAX_CHARS]
        lines.append(f"- {pub:%m-%d} {t}" if kind == "dart" else f"- {pub:%m-%d} [{src or '-'}] {t}")
    return lines, len(out)


# ── §3-9 재무 · §3-10 가격 맥락 ─────────────────────────────────────────────────
FIN_FIELDS = ("stac_yymm", "sales_growth", "operating_income_growth", "net_income_growth",
              "roe_value", "liability_ratio", "reserve_ratio", "eps")


def fin_available_on(stac_yymm: str) -> Optional[date]:
    """월말 + 60일(03·06·09 · 그 밖 월도 60) / 100일(12) — pit_reader 연간 보수화(선언된 이탈)."""
    s = str(stac_yymm or "")
    if len(s) != 6 or not s.isdigit() or not 1 <= int(s[4:]) <= 12:
        return None
    y, m = int(s[:4]), int(s[4:])
    end = date(y, m, _cal.monthrange(y, m)[1])
    return end + timedelta(days=100 if m == 12 else 60)


def pick_financial(rows: Iterable[Dict[str, Any]], D: date) -> Optional[Dict[str, Any]]:
    ok = [r for r in rows if (fin_available_on(r.get("stac_yymm")) or date.max) <= D]
    return max(ok, key=lambda r: str(r["stac_yymm"])) if ok else None


def fmt_num(x: Any, digits: int = 2) -> str:
    if x is None:
        return "-"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    if v != v:
        return "-"
    s = f"{v:,.{digits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def fmt_int(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    return "-" if v != v else f"{round(v):,}"


def r20_text(px: Dict[date, Tuple[Optional[float], Optional[float]]], window: List[date]) -> str:
    """px = {date: (close, adj_factor)} · window = D−20…D(21 거래일). 창 안 adj_factor ≠ 1 이면 N/A."""
    if len(window) < 21:
        return "-"
    for d in window:
        adj = px.get(d, (None, None))[1]
        if adj is not None and abs(float(adj) - 1.0) > 1e-12:
            return "N/A"
    c0, c1 = px.get(window[0], (None, None))[0], px.get(window[-1], (None, None))[0]
    if not c0 or not c1 or c0 <= 0 or c1 <= 0:
        return "-"
    return f"{(float(c1) / float(c0) - 1.0) * 100:+.1f}%"


@dataclass
class StockCtx:
    name: str
    market: str
    mcap: Optional[float]
    r20: str
    fin: Optional[Dict[str, Any]]
    dart_rows: List[Tuple[datetime, int, str, Optional[str]]]
    press_rows: List[Tuple[datetime, int, str, Optional[str]]]


def block_fields(code: str, ctx: StockCtx, D: date, d10: date, d5: date) -> Dict[str, Any]:
    dl, nd = select_lines(ctx.dart_rows, "dart", S.DART_TITLE_MAX)
    pl, npr = select_lines(ctx.press_rows, "press", S.PRESS_TITLE_MAX)
    f = ctx.fin or {}
    return dict(name=clean_ws(ctx.name) or code, code=code, market=ctx.market or "-",
                mcap_eok=fmt_int(ctx.mcap / 1e8) if ctx.mcap else "-", r20=ctx.r20,
                stac_yymm=f.get("stac_yymm") or "-", sales_growth=fmt_num(f.get("sales_growth")),
                oi_growth=fmt_num(f.get("operating_income_growth")), ni_growth=fmt_num(f.get("net_income_growth")),
                roe=fmt_num(f.get("roe_value")), liab=fmt_num(f.get("liability_ratio")),
                reserve=fmt_num(f.get("reserve_ratio")), eps=fmt_int(f.get("eps")) if f.get("eps") is not None else "-",
                d10=d10.isoformat(), D=D.isoformat(), n_dart_all=nd, dart_lines="\n".join(dl) or "(없음)",
                d5=d5.isoformat(), n_press_all=npr, press_lines="\n".join(pl) or "(없음)")


def _d(x: Any) -> Optional[date]:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


# ── DB 입력(SELECT 만) ───────────────────────────────────────────────────────────
class PgInputs:
    def __init__(self, conn):
        self.conn = conn

    def _q(self, sql: str, params: Sequence[Any] = ()) -> List[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def latest_D(self, T: date) -> Optional[date]:
        r = self._q("SELECT max(date) FROM daily_prices WHERE stock_code = %s AND date < %s",
                    (CALENDAR_TICKER, T.isoformat()))
        return _d(r[0][0]) if r and r[0][0] else None

    def calendar(self, upto: date) -> Calendar:
        rows = self._q("SELECT DISTINCT date FROM daily_prices WHERE stock_code = %s AND date >= %s AND date <= %s",
                       (CALENDAR_TICKER, CAL_START, upto.isoformat()))
        return Calendar([d for d in (_d(r[0]) for r in rows) if d])

    def names(self) -> Dict[str, str]:
        return {str(c): str(n) for c, n in self._q("SELECT stock_code, stock_name FROM stock_info") if n is not None}

    def universe(self, D: date) -> List[str]:
        """U(D) = D 행 market_cap NOT NULL ∧ STOCK_ONLY ∧ classify_exclusions(① §6 과 같음)."""
        codes = sorted({str(r[0]) for r in self._q(
            "SELECT stock_code FROM daily_prices WHERE date = %s AND market_cap IS NOT NULL AND " + STOCK_ONLY,
            (D.isoformat(),))})
        cls = classify_exclusions(codes, self.names())
        return [c for c in codes if not cls[c]["excluded"]]

    def new_items(self, D_prev: date, D: date, T: date, U: Set[str]) -> Tuple[Set[str], Set[str], Set[str]]:
        disc = self._q("SELECT stock_code, report_nm, rcept_dt, pblntf_ty FROM dart_disclosures "
                       "WHERE rcept_dt > %s AND rcept_dt <= %s AND stock_code IS NOT NULL", (D_prev, D))
        lo, hi = a_press_window(D_prev, D)
        _, cre_end = cutoffs(D, T)
        press = self._q("SELECT ns.stock_code, n.published_at, n.created_at FROM news n "
                        "JOIN news_stock ns ON ns.news_id = n.id WHERE n.source <> 'dart' "
                        "AND n.published_at >= %s AND n.published_at < %s AND n.created_at < %s", (lo, hi, cre_end))
        return new_item_codes([(str(c), r, _d(dt), str(t)) for c, r, dt, t in disc],
                              [(str(c), p, cr) for c, p, cr in press], D_prev, D, T, U)

    def cand_strategies(self, D: date) -> Optional[Dict[str, List[str]]]:
        rows = self._q("SELECT strategy, stock_code FROM screener_snapshots "
                       "WHERE scan_date = %s AND strategy = ANY(%s)",
                       (D, list(S.CAND_STRATEGIES)))
        if not rows:
            return None
        out: Dict[str, List[str]] = {}
        for st, c in rows:
            out.setdefault(str(c), [])
            if st not in out[str(c)]:
                out[str(c)].append(st)
        return {c: sorted(v) for c, v in out.items()}

    def _titles(self, codes: List[str], dart: bool, lo: datetime, D: date, T: date) -> Dict[str, list]:
        pub_end, cre_end = cutoffs(D, T)
        rows = self._q("SELECT ns.stock_code, n.published_at, n.id, n.title, n.source, n.created_at FROM news n "
                       "JOIN news_stock ns ON ns.news_id = n.id WHERE n.source " + ("= 'dart'" if dart else "<> 'dart'")
                       + " AND ns.stock_code = ANY(%s) AND n.published_at >= %s AND n.published_at < %s "
                       "AND n.created_at < %s", (codes, lo, pub_end, cre_end))
        out: Dict[str, list] = {}
        for c, pub, nid, title, src, cre in rows:
            if pub >= lo and news_visible(pub, cre, D, T):
                out.setdefault(str(c), []).append((pub, int(nid), title or "", src))
        return out

    def stock_ctx(self, D: date, T: date, codes: List[str], cal: Calendar) -> Tuple[Dict[str, StockCtx], date, date]:
        codes = sorted(set(codes))
        d10, d5 = cal.back(D, S.DART_TITLE_TD), cal.back(D, S.PRESS_TITLE_TD)
        win = cal.dates[max(0, cal.idx(D) - 20): cal.idx(D) + 1]
        names = self.names()
        corp = dict((str(c), n) for c, n in self._q(
            "SELECT DISTINCT ON (stock_code) stock_code, corp_name FROM dart_disclosures WHERE stock_code = ANY(%s) "
            "ORDER BY stock_code, rcept_dt DESC, rcept_no DESC", (codes,)))
        mk = dict((str(c), m) for c, m in self._q(
            "SELECT stock_code, market FROM stock_market WHERE stock_code = ANY(%s)", (codes,)))
        mk2 = dict((str(c), m) for c, m in self._q(
            "SELECT stock_code, market FROM stock_info WHERE stock_code = ANY(%s)", (codes,)))
        px: Dict[str, Dict[date, Tuple[Optional[float], Optional[float]]]] = {}
        mcap: Dict[str, Optional[float]] = {}
        for c, d, close, adj, mc in self._q(
                "SELECT stock_code, date, close, adj_factor, market_cap FROM daily_prices "
                "WHERE stock_code = ANY(%s) AND date = ANY(%s)", (codes, [x.isoformat() for x in win])):
            dd = _d(d)
            px.setdefault(str(c), {})[dd] = (close, adj)
            if dd == D:
                mcap[str(c)] = mc
        fin: Dict[str, List[Dict[str, Any]]] = {}
        for row in self._q("SELECT stock_code, " + ", ".join(FIN_FIELDS) + " FROM kis_financial_ratio "
                           "WHERE div_cls = '1' AND stock_code = ANY(%s)", (codes,)):
            fin.setdefault(str(row[0]), []).append(dict(zip(FIN_FIELDS, row[1:])))
        dart = self._titles(codes, True, datetime.combine(d10, time(0, 0)), D, T)
        press = self._titles(codes, False, datetime.combine(d5, time(0, 0)), D, T)
        out = {}
        for c in codes:
            out[c] = StockCtx(name=names.get(c) or corp.get(c) or c, market=mk.get(c) or mk2.get(c) or "-",
                              mcap=mcap.get(c), r20=r20_text(px.get(c, {}), win),
                              fin=pick_financial(fin.get(c, []), D), dart_rows=dart.get(c, []),
                              press_rows=press.get(c, []))
        return out, d10, d5


# ── dry-run 가상 입력(§5-2 · §10 ⑤) ─────────────────────────────────────────────
class SyntheticInputs:
    """DB 없이 같은 코드 경로를 돈다. 코드 `0000xx` · 가상 이름 · 가상 제목(실존 정보 아님)."""

    def __init__(self, n_codes: int = 45, seed: int = 7):
        self.codes = [f"{i:06d}" for i in range(10, 10 + n_codes)]
        self.rnd = random.Random(seed)

    def latest_D(self, T: date) -> date:
        d = T - timedelta(days=1)
        while not is_trading_day(d):
            d -= timedelta(days=1)
        return d

    def calendar(self, upto: date) -> Calendar:
        ds, d = [], upto
        while len(ds) < 60:
            if is_trading_day(d):
                ds.append(d)
            d -= timedelta(days=1)
        return Calendar(ds)

    def universe(self, D: date) -> List[str]:
        return list(self.codes)

    def new_items(self, D_prev: date, D: date, T: date, U: Set[str]):
        a = {c for i, c in enumerate(sorted(U)) if (i + D.day) % 3 == 0}
        return a, a, set()

    def cand_strategies(self, D: date):
        return None

    def stock_ctx(self, D: date, T: date, codes: List[str], cal: Calendar):
        d10, d5 = cal.back(D, S.DART_TITLE_TD), cal.back(D, S.PRESS_TITLE_TD)
        out = {}
        for c in codes:
            pub = datetime.combine(D, time(15, 0))
            out[c] = StockCtx(name=f"가상종목{c[-2:]}", market="KOSDAQ", mcap=1.23e11, r20="+1.5%",
                              fin={"stac_yymm": "202606", "sales_growth": 3.1, "operating_income_growth": -2.0,
                                   "net_income_growth": 1.0, "roe_value": 5.5, "liability_ratio": 80.0,
                                   "reserve_ratio": 900.0, "eps": 120},
                              dart_rows=[(pub, 1, f"[가상종목{c[-2:]}] 가상 공시 제목(검증용)", "dart")],
                              press_rows=[])
        return out, d10, d5
