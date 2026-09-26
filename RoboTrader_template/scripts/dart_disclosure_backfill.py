"""DART 공시(list.json) 전체 백필 — 연구 전용 · dart_disclosures 테이블 신설.

`scripts/dart_backfill_dryrun.py` 의 dry-run(60회 · DB 쓰기 0)을 이어받아 실제
적재를 수행한다. 운영 수집기(`collectors/corp_events_collector.py`)의
`_fetch_one_type` 은 페이지 상한 100에서 «경고만 남기고 절단»하므로 여기서는
재사용하지 않고, 하루(일) 단위 창으로 전 페이지를 끝까지 읽는다
(scratchpad/dart_dryrun_20260924/DRYRUN_REPORT.md §5-1).

안전장치:
  - 키는 라이브 트리 .env 에서 «읽기»만(복사·출력·로그 금지) · 예외 메시지에서 키를 가린다.
  - DELETE/UPDATE/TRUNCATE 없음 · ON CONFLICT (rcept_no) DO NOTHING 만.
  - 다른 테이블은 건드리지 않는다. retention policy 설정 없음.
  - 외부 호출 하드캡(--limit-calls, 기본 5000, 재시도 포함) · 원자료 페이지 캐시로
    재실행 시 이미 받은 페이지는 재호출하지 않는다.
  - --create-table 없이 테이블이 없으면 즉시 실패(테이블을 암묵적으로 만들지 않는다).
  - 동시 실행 금지: 출력 폴더(--out)에 잠금 파일 `.lock`(PID 기록)이 없으면 만들고
    시작하며, 이미 있으면 즉시 중단한다. 정상 종료·예외 종료 모두 finally 에서
    잠금을 해제한다. 2026-09-26 두 인스턴스(full_run·full_run2)가 같은
    progress.json 에 동시에 os.replace 를 걸어 PermissionError(WinError 5)로
    한쪽이 죽은 사고(full_run2.err)의 재발 방지.

usage:
  python scripts/dart_disclosure_backfill.py --create-table --dry-run
  python scripts/dart_disclosure_backfill.py --bgn 2025-03-03 --end 2025-03-07 --limit-calls 120
  python scripts/dart_disclosure_backfill.py --resume --bgn 2024-03-13 --end 2026-09-23
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402
import requests  # noqa: E402

from collectors.corp_events_collector import (  # noqa: E402
    DART_BASE, _PAGE_COUNT, _parse_dart_key_from_lines)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_ENV = r"D:/GIT/kis-trading-template/RoboTrader_template/.env"
DEFAULT_BGN = "2024-03-13"
DEFAULT_END = "2026-09-23"
DEFAULT_TYPES = ("B", "I")
DEFAULT_LIMIT_CALLS = 5000
DEFAULT_SLEEP = 0.7
DEFAULT_LAST_REPRT_AT = "N"  # N=최종보고서 아닌 것 포함(원공시+정정 모두) · Y=최종본만
_BACKOFF_START = 0.5
_BACKOFF_CAP = 8.0
_PAGE_GUARD = 200  # 하루·유형당 이 이상 페이지가 나오면 경고하고 중단(무한루프 방지)
DB = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")

CORRECTION_MARKERS = ("정정",)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dart_disclosures (
    rcept_no TEXT PRIMARY KEY,
    corp_code TEXT,
    corp_name TEXT,
    stock_code TEXT NULL,
    corp_cls CHAR(1),
    report_nm TEXT,
    rcept_dt DATE NOT NULL,
    pblntf_ty CHAR(1) NOT NULL,
    is_correction BOOLEAN NOT NULL DEFAULT FALSE,
    rm TEXT,
    raw JSONB,
    fetched_at TIMESTAMPTZ DEFAULT now()
)
"""
CREATE_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_dart_disclosures_stock_dt "
    "ON dart_disclosures (stock_code, rcept_dt)",
    "CREATE INDEX IF NOT EXISTS idx_dart_disclosures_dt "
    "ON dart_disclosures (rcept_dt)",
]
UPSERT_SQL = """
INSERT INTO dart_disclosures
    (rcept_no, corp_code, corp_name, stock_code, corp_cls, report_nm,
     rcept_dt, pblntf_ty, is_correction, rm, raw)
VALUES %s
ON CONFLICT (rcept_no) DO NOTHING
"""


def is_correction(report_nm: str) -> bool:
    """report_nm 에 정정 표기(예 [기재정정]·[정정]·(정정))가 있으면 True."""
    if not report_nm:
        return False
    return any(marker in report_nm for marker in CORRECTION_MARKERS)


def redact(text: str, key: str) -> str:
    """예외 메시지·로그 한 줄에서 API 키 문자열을 가린다."""
    if not key:
        return text
    return text.replace(key, "<KEY>")


def load_key() -> str:
    """라이브 트리 .env 에서 OPENDART_API_KEY 를 읽기만 한다(복사·출력·로그 금지)."""
    with open(LIVE_ENV, encoding="utf-8") as f:
        return _parse_dart_key_from_lines(f)


def item_to_record(item: dict, pblntf_ty: str) -> Optional[dict]:
    """DART list.json 항목 → dart_disclosures 행(dict). rcept_no·rcept_dt 없으면 None."""
    rcept_no = (item.get("rcept_no") or "").strip()
    rcept_dt_raw = (item.get("rcept_dt") or "").strip()
    if not rcept_no or len(rcept_dt_raw) != 8 or not rcept_dt_raw.isdigit():
        return None
    rcept_dt = f"{rcept_dt_raw[0:4]}-{rcept_dt_raw[4:6]}-{rcept_dt_raw[6:8]}"
    stock_code = (item.get("stock_code") or "").strip() or None
    report_nm = item.get("report_nm") or ""
    return {
        "rcept_no": rcept_no,
        "corp_code": item.get("corp_code"),
        "corp_name": item.get("corp_name"),
        "stock_code": stock_code,
        "corp_cls": item.get("corp_cls"),
        "report_nm": report_nm,
        "rcept_dt": rcept_dt,
        "pblntf_ty": pblntf_ty,
        "is_correction": is_correction(report_nm),
        "rm": item.get("rm"),
        "raw": item,
    }


def daterange(bgn: date, end: date):
    d = bgn
    one = timedelta(days=1)
    while d <= end:
        yield d
        d += one


def atomic_write_json(path: str, obj) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


class Progress:
    """(type, date) 완료 여부를 진행 JSON 에 원자적으로(temp→os.replace) 기록."""

    def __init__(self, path: str):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    @staticmethod
    def _key(pblntf_ty: str, day: str) -> str:
        return f"{pblntf_ty}:{day}"

    def is_done(self, pblntf_ty: str, day: str) -> bool:
        entry = self.data.get(self._key(pblntf_ty, day))
        return bool(entry and entry.get("done"))

    def record(self, pblntf_ty: str, day: str, calls: int, rows: int, rows_inserted: int,
               pages: int, done: bool) -> None:
        self.data[self._key(pblntf_ty, day)] = {
            "calls": calls, "rows": rows, "rows_inserted": rows_inserted,
            "pages": pages, "done": done,
        }
        atomic_write_json(self.path, self.data)


@dataclass
class CallBudget:
    """외부 호출 하드캡(재시도 포함) 관리."""

    limit: int
    used: int = 0

    def check(self) -> None:
        if self.used >= self.limit:
            raise RuntimeError(f"호출 상한 {self.limit} 도달 — 중단")

    def bump(self) -> None:
        self.used += 1


@dataclass
class Warnings:
    items: list = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.items.append(msg)


class RawCache:
    """(pblntf_ty, day, page) → raw JSON 파일 캐시. 있으면 재호출하지 않는다."""

    def __init__(self, raw_dir: str):
        self.dir = raw_dir
        os.makedirs(raw_dir, exist_ok=True)

    def path(self, pblntf_ty: str, day: str, page: int) -> str:
        return os.path.join(self.dir, f"{day}_{pblntf_ty}_p{page}.json")

    def get(self, pblntf_ty: str, day: str, page: int) -> Optional[dict]:
        p = self.path(pblntf_ty, day, page)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return None

    def put(self, pblntf_ty: str, day: str, page: int, data: dict) -> None:
        path = self.path(pblntf_ty, day, page)
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)


class Fetcher:
    """list.json 호출자 — 캐시 우선, 상태 020 백오프, 하드캡, call_log.jsonl 기록."""

    def __init__(self, key: str, cache: RawCache, budget: CallBudget, call_log_path: str, sleep: float,
                 last_reprt_at: str = DEFAULT_LAST_REPRT_AT):
        self.key = key
        self.cache = cache
        self.budget = budget
        self.call_log_path = call_log_path
        self.sleep = sleep
        self.last_reprt_at = last_reprt_at

    def _log_call(self, url: str, status, rows: int, elapsed: float) -> None:
        line = {"url": url, "status": status, "rows": rows, "elapsed": round(elapsed, 3),
                "ts": datetime.now().isoformat()}
        with open(self.call_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def fetch_page(self, pblntf_ty: str, day: str, page: int, warnings: Warnings) -> Optional[dict]:
        """캐시에 없으면 호출. status 020 은 백오프 재시도, 그 외 실패는 None."""
        cached = self.cache.get(pblntf_ty, day, page)
        if cached is not None:
            return cached
        params = {"bgn_de": day, "end_de": day, "pblntf_ty": pblntf_ty,
                  "page_count": _PAGE_COUNT, "page_no": page,
                  "last_reprt_at": self.last_reprt_at}
        url_no_key = f"{DART_BASE}/list.json?" + "&".join(f"{k}={v}" for k, v in params.items())
        backoff = _BACKOFF_START
        while True:
            self.budget.check()
            self.budget.bump()
            t0 = time.time()
            try:
                r = requests.get(f"{DART_BASE}/list.json",
                                  params=dict(params, crtfc_key=self.key), timeout=20)
                r.encoding = "utf-8"
                data = r.json()
            except Exception as e:  # 키가 URL 에 실려 예외 문자열로 새지 않게 가린다
                raise RuntimeError(redact(str(e), self.key)) from None
            elapsed = time.time() - t0
            status = data.get("status")
            rows = len(data.get("list") or [])
            self._log_call(url_no_key, status, rows, elapsed)
            if status == "020":
                if backoff > _BACKOFF_CAP:
                    warnings.add(f"{day} {pblntf_ty} p{page}: status 020 backoff 초과 — 이 날 미완료")
                    return None
                time.sleep(backoff)
                backoff *= 2
                continue
            if status == "013":  # 무자료 = 정상
                return data
            if status != "000":
                warnings.add(f"{day} {pblntf_ty} p{page}: status={status} msg={data.get('message')}")
                return data
            self.cache.put(pblntf_ty, day, page, data)
            time.sleep(self.sleep)
            return data


def fetch_day(fetcher: Fetcher, pblntf_ty: str, day: str, warnings: Warnings):
    """하루·한 유형의 전 페이지를 total_page 까지(또는 짧은 페이지가 나올 때까지) 수집.

    반환 (items, calls_made_new, pages_read, done). done=False 면 020 백오프 초과나
    비정상 status 로 중단된 것 — progress 에 미완료로 남긴다.
    """
    items = []
    page = 1
    total_page = 1
    calls_before = fetcher.budget.used
    while page <= total_page:
        if page > _PAGE_GUARD:
            warnings.add(f"{day} {pblntf_ty}: 페이지 {_PAGE_GUARD} 초과 — 중단(가드)")
            return items, fetcher.budget.used - calls_before, page - 1, False
        data = fetcher.fetch_page(pblntf_ty, day, page, warnings)
        if data is None:
            return items, fetcher.budget.used - calls_before, page - 1, False
        status = data.get("status")
        if status == "013":
            return items, fetcher.budget.used - calls_before, page, True
        if status != "000":
            return items, fetcher.budget.used - calls_before, page, False
        page_items = data.get("list") or []
        items.extend(page_items)
        total_page = int(data.get("total_page") or 1)
        if len(page_items) < _PAGE_COUNT:
            # 마지막 페이지(짧은 페이지) — total_page 계산과 별개로 끝났다고 본다.
            return items, fetcher.budget.used - calls_before, page, True
        page += 1
    return items, fetcher.budget.used - calls_before, page - 1, True


def upsert_records(conn, records: list, chunk_size: int = 500) -> int:
    """ON CONFLICT (rcept_no) DO NOTHING 배치 upsert. 반환 = 실제 삽입된 행수.

    execute_values 는 내부적으로 page_size(기본 100)단위로 여러 execute 를 낼 수
    있고 cur.rowcount 는 «마지막 execute» 만 반영한다 — 100행을 넘는 날은 그대로
    쓰면 삽입 행수를 과소집계한다. page_size=len(chunk) 로 청크당 execute 를
    하나로 고정하고 청크별 rowcount 를 누적해 정확한 합을 낸다.
    """
    if not records:
        return 0
    values = [
        (r["rcept_no"], r["corp_code"], r["corp_name"], r["stock_code"], r["corp_cls"],
         r["report_nm"], r["rcept_dt"], r["pblntf_ty"], r["is_correction"], r["rm"],
         psycopg2.extras.Json(r["raw"]))
        for r in records
    ]
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(values), chunk_size):
            chunk = values[i:i + chunk_size]
            psycopg2.extras.execute_values(cur, UPSERT_SQL, chunk, page_size=len(chunk))
            inserted += cur.rowcount
    conn.commit()
    return inserted


def ensure_table(conn, create: bool) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.dart_disclosures')")
        exists = cur.fetchone()[0] is not None
    if exists:
        return
    if not create:
        raise RuntimeError(
            "테이블 dart_disclosures 가 없다 — 먼저 --create-table 로 생성할 것(암묵적 생성 금지)")
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        for idx_sql in CREATE_INDEX_SQL:
            cur.execute(idx_sql)
    conn.commit()


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bgn", default=DEFAULT_BGN)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--types", default=",".join(DEFAULT_TYPES))
    ap.add_argument("--create-table", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                     help="fetch+parse+count 만, DB 쓰기 0")
    ap.add_argument("--limit-calls", type=int, default=DEFAULT_LIMIT_CALLS)
    ap.add_argument("--resume", action="store_true",
                     help="progress.json 에 done 으로 표시된 (type,date) 는 건너뜀")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP)
    ap.add_argument("--last-reprt-at", default=DEFAULT_LAST_REPRT_AT, choices=["N", "Y"],
                     help="DART list.json last_reprt_at — N(기본)=원공시+정정 모두, Y=최종본만")
    ap.add_argument("--out", default=None,
                     help="기본 scratchpad/dart_backfill_<YYYYMMDD>/")
    return ap.parse_args(argv)


class LockHeld(RuntimeError):
    """출력 폴더에 다른 실행의 잠금 파일이 이미 있을 때."""


def acquire_lock(out_dir: str) -> str:
    """out_dir/.lock 를 원자적으로 생성(O_EXCL) — 이미 있으면 LockHeld."""
    lock_path = os.path.join(out_dir, ".lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            with open(lock_path, encoding="utf-8") as f:
                holder = f.read().strip()
        except OSError:
            holder = "?"
        raise LockHeld(f"동시 실행 금지 — 잠금 파일 존재(PID {holder}): {lock_path}") from None
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return lock_path


def release_lock(lock_path: str) -> None:
    try:
        os.remove(lock_path)
    except OSError:
        pass


def run(args) -> dict:
    bgn = datetime.strptime(args.bgn, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    types = tuple(t.strip() for t in args.types.split(",") if t.strip())
    out_dir = args.out or os.path.join(ROOT, "scratchpad", f"dart_backfill_{date.today().strftime('%Y%m%d')}")
    os.makedirs(out_dir, exist_ok=True)
    lock_path = acquire_lock(out_dir)
    raw_dir = os.path.join(out_dir, "raw")
    progress = Progress(os.path.join(out_dir, "progress.json"))
    call_log_path = os.path.join(out_dir, "call_log.jsonl")
    warnings = Warnings()

    conn = None
    try:
        key = load_key()
        if not key:
            sys.exit("OPENDART_API_KEY 없음(라이브 .env 확인)")

        budget = CallBudget(limit=args.limit_calls)
        cache = RawCache(raw_dir)
        fetcher = Fetcher(key, cache, budget, call_log_path, args.sleep, args.last_reprt_at)

        if not args.dry_run:
            conn = psycopg2.connect(**DB)
            ensure_table(conn, create=args.create_table)

        t_start = time.time()
        total_rows_fetched = 0
        total_rows_inserted = 0
        days_done = 0

        for d in daterange(bgn, end):
            day = d.strftime("%Y%m%d")
            for ty in types:
                if args.resume and progress.is_done(ty, day):
                    continue
                items, calls_made, pages, done = fetch_day(fetcher, ty, day, warnings)
                records = [r for it in items if (r := item_to_record(it, ty)) is not None]
                total_rows_fetched += len(records)
                inserted = 0
                if not args.dry_run and records:
                    inserted = upsert_records(conn, records)
                    total_rows_inserted += inserted
                progress.record(ty, day, calls_made, len(records), inserted, pages, done)
            days_done += 1
    finally:
        if conn is not None:
            conn.close()
        release_lock(lock_path)

    elapsed = time.time() - t_start
    summary = {
        "bgn": args.bgn, "end": args.end, "types": list(types),
        "dry_run": args.dry_run, "calls": budget.used,
        "rows_fetched": total_rows_fetched, "rows_inserted": total_rows_inserted,
        "days": days_done, "elapsed_sec": round(elapsed, 1),
        "warnings": warnings.items,
    }
    atomic_write_json(os.path.join(out_dir, "summary.json"), summary)
    with open(os.path.join(out_dir, "SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write(f"# DART 공시 백필 요약 ({args.bgn} ~ {args.end})\n\n")
        f.write(f"- 유형: {', '.join(types)} · dry_run={args.dry_run}\n")
        f.write(f"- 호출 {budget.used}회 · 일수 {days_done} · 경과 {summary['elapsed_sec']}s\n")
        f.write(f"- 수집 {total_rows_fetched}행 · 삽입 {total_rows_inserted}행\n")
        if warnings.items:
            f.write(f"\n## 경고 {len(warnings.items)}건\n")
            for w in warnings.items:
                f.write(f"- {w}\n")
    return summary


if __name__ == "__main__":
    _args = parse_args()
    _summary = run(_args)
    print(json.dumps(_summary, ensure_ascii=False, indent=1, default=str))
