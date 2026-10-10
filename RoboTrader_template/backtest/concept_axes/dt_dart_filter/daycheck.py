"""DART 백필 완결 판정 — 스펙 §3-1.

`llm_shadow/dart_load.day_complete`(research/dart-events) 본문 규칙에서 «2026-09-23 이전이면 무조건 참» 지름길을
뺀 판. 하루×유형 칸이 완결 = (raw 전 페이지 status 000 ∧ 항목 합 = total_count ∧ DB 행 + 다른 유형 중복 = total_count)
또는 (013 무자료 증거 ∧ DB 행 0).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class RawDay:
    state: str                      # "ok" | "empty013" | "missing" | "bad"
    total_count: int
    rcept_nos: Tuple[str, ...]


def _has_013(call_log: Path, ds: str, ty: str) -> bool:
    if not call_log.exists():
        return False
    for line in call_log.read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        u = str(j.get("url", ""))
        if str(j.get("status")) == "013" and f"bgn_de={ds}" in u and f"pblntf_ty={ty}" in u:
            return True
    return False


def read_raw_day(out_dir: Path, ty: str, day: date) -> RawDay:
    ds = day.strftime("%Y%m%d")
    raw = Path(out_dir) / "raw"
    p1 = raw / f"{ds}_{ty}_p1.json"
    if not p1.exists():
        state = "empty013" if _has_013(Path(out_dir) / "call_log.jsonl", ds, ty) else "missing"
        return RawDay(state, 0, ())
    d1 = json.loads(p1.read_text(encoding="utf-8"))
    tc, tp = int(d1.get("total_count") or 0), int(d1.get("total_page") or 1)
    nos: List[str] = []
    for p in range(1, tp + 1):
        f = raw / f"{ds}_{ty}_p{p}.json"
        if not f.exists():
            return RawDay("missing", tc, ())
        dj = json.loads(f.read_text(encoding="utf-8"))
        if str(dj.get("status")) != "000":
            return RawDay("bad", tc, ())
        nos += [str(it.get("rcept_no", "")) for it in (dj.get("list") or [])]
    if len(nos) != tc:
        return RawDay("bad", tc, ())
    return RawDay("ok", tc, tuple(nos))


def judge(rd: RawDay, n_db: int, dup: int) -> bool:
    if rd.state == "empty013":
        return n_db == 0
    if rd.state != "ok":
        return False
    return n_db + dup == rd.total_count


def check(conn, out_dir: Path, start: date, end: date, types: Sequence[str]) -> Dict[str, Any]:
    bad: List[Dict[str, Any]] = []
    n = 0
    d = start
    with conn.cursor() as cur:
        while d <= end:
            for ty in types:
                rd = read_raw_day(out_dir, ty, d)
                cur.execute("SELECT count(*) FROM dart_disclosures WHERE rcept_dt = %s AND pblntf_ty = %s", (d, ty))
                n_db = int(cur.fetchone()[0])
                dup = 0
                if rd.rcept_nos:
                    cur.execute("SELECT count(*) FROM dart_disclosures WHERE rcept_no = ANY(%s) AND pblntf_ty <> %s",
                                (list(rd.rcept_nos), ty))
                    dup = int(cur.fetchone()[0])
                n += 1
                if not judge(rd, n_db, dup):
                    bad.append(dict(day=d.isoformat(), ty=ty, state=rd.state, tc=rd.total_count, n_db=n_db, dup=dup))
            d += timedelta(days=1)
    conn.rollback()
    return {"n_cells": n, "n_bad": len(bad), "bad": bad[:200], "complete": not bad}
