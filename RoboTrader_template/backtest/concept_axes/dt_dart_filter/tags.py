"""lag0 · W 창 표식 — 스펙 §3-3. 태그 판정은 09-26 동결 `dart_tags.tag_of` 그대로."""
from __future__ import annotations

import bisect
from datetime import date
from typing import Iterable, List, Optional, Sequence, Set, Tuple

from backtest.concept_axes.candidate_ledger.dart_events.dart_tags import tag_of

from . import settings as S


def _check_only(only: Optional[str]) -> None:
    if only is not None and only not in S.TAGS_LAG0:
        raise ValueError(f"only 는 {S.TAGS_LAG0} 중 하나여야 한다: {only!r}")


def is_lag0_tag(report_nm: str, only: Optional[str] = None) -> bool:
    """3태그 원공시(정정·자회사/종속회사 제외 · 소송·횡령 중 경영권분쟁 제외)면 참.

    only = `S.TAGS_LAG0` 중 하나면 그 태그만 참(태그별 표식 · critic B1). 나머지 규칙은 같다.
    """
    _check_only(only)
    tag, is_corr, flags = tag_of(report_nm or "")
    if is_corr or tag not in S.TAGS_LAG0 or (only is not None and tag != only):
        return False
    return not (tag == S.MGMT_TAG and bool(flags.get("mgmt_dispute")))


def window_marks(filings: Iterable[Tuple[str, date, str]], cal: Sequence[date], back: int,
                 only: Optional[str] = None) -> Set[Tuple[str, date]]:
    """rcept_dt ∈ [cal[i−back], cal[i]](달력일 · 주말 포함)인 3태그 원공시가 있는 (종목, 스캔일 cal[i]).

    back=0 = lag0(스캔일과 같은 «거래일» 접수만 · 주말 접수는 없음) · back=4 = W5 · back=19 = W20.
    only = 태그 하나로 한정(태그별 표식 · 세 태그 집합의 합집합 = only=None 결과).
    """
    _check_only(only)
    cal = list(cal)
    out: Set[Tuple[str, date]] = set()
    for code, d, nm in filings:
        if not code or not is_lag0_tag(nm, only):
            continue
        j = bisect.bisect_left(cal, d)            # cal[j] ≥ d 인 첫 거래일
        jl = bisect.bisect_right(cal, d) - 1      # cal[jl] ≤ d 인 마지막 거래일
        for i in range(j, min(len(cal), jl + back + 1)):
            out.add((str(code), cal[i]))
    return out


def load_filings(conn, start: date, end: date) -> List[Tuple[str, date, str]]:
    """`dart_disclosures` (stock_code, rcept_dt, report_nm) — 종목코드 있는 행만 · SELECT 전용."""
    return [(c, d, n) for c, d, n, _ in load_filings_typed(conn, start, end)]


def load_filings_cls(conn, start: date, end: date) -> List[Tuple[str, date, str, str, str]]:
    """(stock_code, rcept_dt, report_nm, pblntf_ty, corp_cls) — 생존자 누락률(코넥스 제외)용 · SELECT 전용."""
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code, rcept_dt, report_nm, pblntf_ty, corp_cls FROM dart_disclosures "
                    "WHERE rcept_dt BETWEEN %s AND %s AND stock_code IS NOT NULL", (start, end))
        rows = cur.fetchall()
    conn.rollback()
    return [(str(c), d, str(n or ""), str(t or ""), str(k or "")) for c, d, n, t, k in rows]


def load_filings_typed(conn, start: date, end: date) -> List[Tuple[str, date, str, str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code, rcept_dt, report_nm, pblntf_ty FROM dart_disclosures "
                    "WHERE rcept_dt BETWEEN %s AND %s AND stock_code IS NOT NULL", (start, end))
        rows = cur.fetchall()
    conn.rollback()
    return [(str(c), d, str(n or ""), str(t or "")) for c, d, n, t in rows]


def count_backfill_rows(conn, start: date, end: date, types: Sequence[str]) -> int:
    """build 멈춤 규칙 — `dart_disclosures` 중 rcept_dt ∈ [start, end] ∧ pblntf_ty ∈ types 행 수 · SELECT 전용."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dart_disclosures WHERE rcept_dt BETWEEN %s AND %s AND pblntf_ty = ANY(%s)",
                    (start, end, list(types)))
        n = int(cur.fetchone()[0])
    conn.rollback()
    return n
