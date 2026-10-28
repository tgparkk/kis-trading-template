"""네이버 테마 스냅샷(NewsQuant · kis_template) 조회 + EOD 표시 열 — 표준 라이브러리만 쓴다.

EOD 스크립트가 이 파일 하나를 경로로 읽어 쓰므로(`importlib.util.spec_from_file_location`) 패키지 안 다른
모듈을 import 하지 않는다. DB 접속은 호출자가 넘긴 DB-API 연결로만(SELECT 전용).
표: `theme_daily(snap_date, theme_no, theme_name, …)` · `theme_member_daily(snap_date, theme_no, stock_code, …)`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

FOOTER = "참고용 — 수동 개입 금지. 개입했다면 보고서에 기록."


def norm_code(code: object) -> str:
    """종목코드 6자리 문자열(앞자리 0 보존)."""
    return str(code).strip().zfill(6)


@dataclass(frozen=True)
class Snapshot:
    snap_date: date
    theme_name: Dict[int, str]
    members: Dict[int, FrozenSet[str]]


def invert(members: Mapping[int, FrozenSet[str]]) -> Dict[str, FrozenSet[int]]:
    """theme_no → 종목들 을 종목 → theme_no 들 로 뒤집는다."""
    out: Dict[str, Set[int]] = {}
    for t, codes in members.items():
        for c in codes:
            out.setdefault(c, set()).add(t)
    return {c: frozenset(ts) for c, ts in out.items()}


def pick_snap_date(available: Sequence[date], target: date) -> Optional[date]:
    """target 이하 가장 최근 snap_date(없으면 None)."""
    le = [d for d in available if d <= target]
    return max(le) if le else None


def load_snap_dates(conn) -> List[date]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT snap_date FROM theme_daily ORDER BY snap_date")
    return [r[0] for r in cur.fetchall()]


def load_snapshot(conn, snap_date: date, run_id: Optional[int] = None) -> Snapshot:
    """run_id 를 주면 두 표 모두 그 수집 회차로 고정한다(판정 입력 · R13). EOD 표시는 run_id 없이 부른다."""
    where, args = ("snap_date = %s", (snap_date,)) if run_id is None else \
        ("snap_date = %s AND run_id = %s", (snap_date, run_id))
    cur = conn.cursor()
    cur.execute("SELECT theme_no, theme_name FROM theme_daily WHERE " + where, args)
    names = {int(t): str(n) for t, n in cur.fetchall()}
    if not names:
        raise LookupError(f"theme_daily 에 snap_date={snap_date} run_id={run_id} 행이 없다")
    cur.execute("SELECT theme_no, stock_code FROM theme_member_daily WHERE " + where, args)
    mem: Dict[int, Set[str]] = {}
    for t, c in cur.fetchall():
        mem.setdefault(int(t), set()).add(norm_code(c))
    return Snapshot(snap_date, names, {t: frozenset(mem.get(t, ())) for t in names})


def shared_theme(code: str, themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]],
                 day_codes: FrozenSet[str]) -> Tuple[Optional[int], int]:
    """같은 날 후보와 공유 수(자기 제외)가 가장 많은 테마와 그 수.

    동점 = 테마 크기 작은 것 → 번호 작은 것. 공유 0 이면 같은 규칙으로 가장 작은 소속 테마(공유 0).
    소속 없음 = (None, 0).
    """
    ts = sorted(themes_of.get(code, ()))
    if not ts:
        return None, 0

    def key(t: int) -> Tuple[int, int, int]:
        return (-len((members[t] - {code}) & day_codes), len(members[t]), t)

    best = min(ts, key=key)
    return best, len((members[best] - {code}) & day_codes)


def theme_columns(codes: Sequence[object], snap: Snapshot) -> Dict[str, Dict[str, object]]:
    """EOD 「다음 거래일 후보」 표 열(동결 전 · 스펙 §7) — 코드별 {"theme": 이름|"-", "size": int|None, "shared": int}.

    `codes` = 그날 조건 통과 후보 «전체»(표에 찍는 상위 10 만이 아니다 — 공유 수를 전체 기준으로 센다).
    """
    norm = [norm_code(c) for c in codes]
    day = frozenset(norm)
    th = invert(snap.members)
    out: Dict[str, Dict[str, object]] = {}
    for c in norm:
        t, k = shared_theme(c, th, snap.members, day)
        out[c] = {"theme": snap.theme_name[t] if t is not None else "-",
                  "size": len(snap.members[t]) if t is not None else None, "shared": k}
    return out
