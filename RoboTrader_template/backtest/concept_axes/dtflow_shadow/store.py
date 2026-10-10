"""저장 — 태쏘 shadow `store.py` 형태 복사(한 트랜잭션 · ON CONFLICT DO NOTHING · 충돌이면 롤백 · CSV 원장 + sha 덧붙임)."""
from __future__ import annotations

import configparser
import copy
import csv
import hashlib
import io
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

from . import settings as S

CAND_COLS = ["rule_v", "scan_date", "stock_code", "rank", "score", "run_at", "f1_orgn", "f2_prog", "f3_short",
             "f4_credit", "credit_deal_date", "credit_lag", "has_investor", "has_program", "has_short", "has_credit",
             "x_frgn", "x_prsn", "x_orgn5", "x_loan_gvrt", "x_ssts_amt_rlim", "acml_tr_pbmn", "late", "code_sha",
             "row_sha"]
RAW_COLS = ["rule_v", "scan_date", "stock_code", "kind", "vintage", "fetched_at", "rt_cd", "msg_cd", "body",
            "body_sha256"]
RUN_COLS = ["rule_v", "scan_date", "run_kind", "run_at", "status", "n_cands", "n_calls", "n_fail", "avail_investor",
            "avail_program", "avail_short", "avail_credit", "snapshot_match", "snapshot_n", "mine_n",
            "max_score_diff", "universe_date", "d_rows", "dprev_rows", "rows_sha256", "duration_ms", "code_sha",
            "error_text"]
PK = {"candidates": ("rule_v", "scan_date", "stock_code"),
      "raw": ("rule_v", "scan_date", "stock_code", "kind", "vintage"),
      "run": ("rule_v", "scan_date", "run_kind", "run_at")}
COLS = {"candidates": CAND_COLS, "raw": RAW_COLS, "run": RUN_COLS}


def table(phase: str, kind: str) -> str:
    if phase not in ("trial", "sealed") or kind not in COLS:
        raise ValueError(f"{phase}/{kind}")
    return f"{S.SCHEMA}.{'trial_' if phase == 'trial' else ''}{kind}"


def cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, float):
        return "" if v != v else repr(v)
    return str(v)


HASH_EXCLUDE = ("run_at", "code_sha", "row_sha")       # 실행 시각·코드 판·자기 sha — DB 왕복으로 모양이 바뀌거나 내용이 아님


def row_sha(row: Dict[str, Any], cols: List[str]) -> str:
    keys = sorted(c for c in cols if c not in HASH_EXCLUDE)
    return hashlib.sha256("\n".join(f"{c}={cell(row.get(c))}" for c in keys).encode("utf-8")).hexdigest()


def to_csv(rows: List[Dict[str, Any]], cols: List[str]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in sorted(rows, key=lambda r: tuple(cell(r.get(c)) for c in ("scan_date", "stock_code"))):
        w.writerow([cell(r.get(c)) for c in cols])
    return buf.getvalue().encode("utf-8")


def rows_sha256(cands: List[Dict[str, Any]]) -> str:
    """row_sha 와 같은 열 집합(run_at·code_sha·row_sha 제외) — DB 에서 읽어 와도 같은 값이 나온다."""
    return hashlib.sha256(to_csv(cands, [c for c in CAND_COLS if c not in HASH_EXCLUDE])).hexdigest()


class MemoryStore:
    def __init__(self) -> None:
        self.t: Dict[str, List[Dict[str, Any]]] = {}

    def _ins(self, t: Dict[str, List[Dict[str, Any]]], name: str, kind: str, row: Dict[str, Any]) -> None:
        key = tuple(cell(row.get(c)) for c in PK[kind])
        rows = t.setdefault(name, [])
        if any(tuple(cell(r.get(c)) for c in PK[kind]) == key for r in rows):
            raise RuntimeError(f"충돌 행 있음 {name} {key}")
        rows.append(dict(row))

    def write_day(self, phase, cands, raws, run) -> None:
        staged = copy.deepcopy(self.t)
        for r in cands:
            self._ins(staged, table(phase, "candidates"), "candidates", r)
        for r in raws:
            self._ins(staged, table(phase, "raw"), "raw", r)
        self._ins(staged, table(phase, "run"), "run", run)
        self.t = staged

    def write_raws(self, phase, raws) -> None:
        staged = copy.deepcopy(self.t)
        for r in raws:
            self._ins(staged, table(phase, "raw"), "raw", r)
        self.t = staged

    def write_run(self, phase, run) -> None:
        staged = copy.deepcopy(self.t)
        self._ins(staged, table(phase, "run"), "run", run)
        self.t = staged

    def runs(self, phase) -> List[Dict[str, Any]]:
        return list(self.t.get(table(phase, "run"), []))

    def cands(self, phase, D) -> List[Dict[str, Any]]:
        return [r for r in self.t.get(table(phase, "candidates"), []) if r["scan_date"] == D]


class PgStore:
    def __init__(self, conn) -> None:
        self.conn = conn

    def _insert(self, cur, phase, kind, row) -> int:
        cols = COLS[kind]
        vals = [json.dumps(row.get(c), ensure_ascii=False) if c == "body" and row.get(c) is not None else row.get(c)
                for c in cols]
        cur.execute(f"INSERT INTO {table(phase, kind)} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                    f"ON CONFLICT DO NOTHING", vals)
        return cur.rowcount

    def _tx(self, items) -> None:
        try:
            with self.conn.cursor() as cur:
                for phase, kind, row in items:
                    if self._insert(cur, phase, kind, row) != 1:
                        raise RuntimeError(f"충돌 행 있음 {table(phase, kind)}")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def write_day(self, phase, cands, raws, run) -> None:
        self._tx([(phase, "candidates", r) for r in cands] + [(phase, "raw", r) for r in raws] + [(phase, "run", run)])

    def write_raws(self, phase, raws) -> None:
        self._tx([(phase, "raw", r) for r in raws])

    def write_run(self, phase, run) -> None:
        self._tx([(phase, "run", run)])

    def _select(self, sql, params) -> List[Dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            names = [d[0] for d in cur.description]
            out = [dict(zip(names, r)) for r in cur.fetchall()]
        self.conn.rollback()
        return out

    def runs(self, phase) -> List[Dict[str, Any]]:
        return self._select(f"SELECT {', '.join(RUN_COLS)} FROM {table(phase, 'run')} WHERE rule_v = %s", (S.RULE_V,))

    def cands(self, phase, D) -> List[Dict[str, Any]]:
        return self._select(f"SELECT {', '.join(CAND_COLS)} FROM {table(phase, 'candidates')} "
                            f"WHERE rule_v = %s AND scan_date = %s", (S.RULE_V, D))


def export_ledger(rows: List[Dict[str, Any]], cols: List[str], root: Path, D: date, name: str) -> str:
    data = to_csv(rows, cols)
    sha = hashlib.sha256(data).hexdigest()
    d = Path(root) / D.isoformat()
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.{datetime.now().strftime('%Y%m%dT%H%M%S')}.csv"
    f.write_bytes(data)
    with open(Path(root) / "ledger_sha256.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{D.isoformat()}\t{name}\t{len(rows)}\t{sha}\t{f.name}\t{datetime.now().isoformat(timespec='seconds')}\n")
    return sha


def writer_password() -> str:
    cp = configparser.ConfigParser(interpolation=None)   # 비번의 `%` 를 보간하지 않는다(예외 메시지로 값이 새지 않게)
    cp.read(str(S.key_ini_path()), encoding="utf-8")
    if not cp.has_section("DTFLOW_SHADOW") or not cp.get("DTFLOW_SHADOW", "db_password", fallback=""):
        raise RuntimeError("key.ini [DTFLOW_SHADOW] db_password 없음")
    return cp.get("DTFLOW_SHADOW", "db_password").strip()


def connect_writer():
    import psycopg2
    from config.constants import resolve_daily_source_db
    return psycopg2.connect(host=os.getenv("TIMESCALE_HOST", "127.0.0.1"), port=int(os.getenv("TIMESCALE_PORT", "5433")),
                            dbname=resolve_daily_source_db(), user=S.WRITER_ROLE, password=writer_password())
