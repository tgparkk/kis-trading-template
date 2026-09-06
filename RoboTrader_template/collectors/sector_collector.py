# collectors/sector_collector.py
"""섹터 수집 오케스트레이터 — 명부·성적표·이름표 + reconcile + 수동 CLI.

usage:
  python -m collectors.sector_collector                                # EOD 판(오늘)
  python -m collectors.sector_collector --bootstrap --date 2026-09-13 [--dry-run]
  python -m collectors.sector_collector --backfill --from 2021-01-04 --to 2026-09-12
  python -m collectors.sector_collector --regen --from D1 --to D2 [--taxonomy ksic3]
  python -m collectors.sector_collector --regen-map --from D1
  python -m collectors.sector_collector --delete-stats --from D1 --to D2
  python -m collectors.sector_collector --reconcile-only 2026-09-07

🔴 DB 쓰기는 sector_writer.py 한 곳뿐이다. 이 파일은 오케스트레이션·판정·CLI 만 맡는다.
🔴 KIS 호출 0 · 매매 룰 0줄 · 라이브 3표는 «읽기»만 한다.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import SQL_STOCK_ONLY  # noqa: E402
from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import krx_desc_cache as kdc  # noqa: E402
from collectors import sector_writer as w  # noqa: E402
from collectors.daily_collector import load_universe  # noqa: E402
from collectors.dart_company_fetcher import DartCompanyFetcher, append_company_raw  # noqa: E402
from collectors.dart_corp_code import load_map, refresh_from_dart  # noqa: E402
from collectors.dart_financial_fetcher import DartBlocked, DartQuotaExceeded  # noqa: E402
from collectors.financial_collector import _load_dart_key  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 🔑 보관 디렉토리는 «한 곳»에서만 정의한다(krx_desc_cache.ARCHIVE_DIR).
#    두 벌로 두면 한쪽만 고쳐 gz 와 summary 가 다른 디렉토리로 갈라진다.
SECTOR_DIR = kdc.ARCHIVE_DIR
DART_DAILY_CAP = 300          # ≈ 102초 (0.34s × 300)
RECHECK_MAX = 200             # 한 바퀴 ≈ 13~14 거래일 (대상 풀 ≈ 2,658)
NODATA_RETRY_DAYS = 30
CORP_CODE_REFRESH_DAYS = 7
BOOTSTRAP_VALID_FROM = date(2021, 1, 4)
_MIN_DT = datetime(1970, 1, 1)      # ksic_checked_at NULLS FIRST 정렬용 하한

_U_MARKET_SQL = "SELECT stock_code FROM stock_market WHERE " + SQL_STOCK_ONLY + " ORDER BY 1"


class SectorStageError(RuntimeError):
    """단계 실패 — 부분 집계(partial)를 들고 올라간다.

    🔴 summary 는 «어떤 경우에도» 써야 §8-5·§8-9 게이트가 그날을 볼 수 있다.
       예외만 던지면 그 날의 recheck_calls·written 이 통째로 사라진다.
    """

    def __init__(self, msg, partial=None):
        RuntimeError.__init__(self, msg)
        self.partial = partial or {}


def _to_iso(s: str) -> str:
    return s if "-" in s else "%s-%s-%s" % (s[0:4], s[4:6], s[6:8])


def load_u_market(conn) -> list:
    """U_market = stock_market ∩ SQL_STOCK_ONLY (커버리지 게이트의 분모)."""
    with conn.cursor() as cur:
        cur.execute(_U_MARKET_SQL)
        return [r[0] for r in cur.fetchall()]


def _fill_targets(open_rows: dict, nodata: dict, now) -> list:
    """(a) 채우기 대상 — corp_code 有 ∧ ksic_code 無 ∧ 부모복사 아님 ∧ nodata 30일 경과."""
    out = []
    for code in sorted(open_rows):
        r = open_rows[code]
        if w.is_blank(r.get("corp_code")) or not w.is_blank(r.get("ksic_code")):
            continue
        if (r.get("ksic_source") or "").startswith("parent:"):
            continue
        ck = nodata.get(code)
        if ck is not None and (now - ck).days < NODATA_RETRY_DAYS:
            continue
        out.append(code)
    return out


def _recheck_targets(open_rows: dict, exclude, limit: int) -> list:
    """(b) 재확인 대상 — ksic_source ∈ {dart, snapshot_20260807} · checked_at ASC NULLS FIRST.

    🔴 코드가 «쓰기 한 번»으로 굳지 않게 하는 장치다. 한 바퀴 ≈ 13~14 거래일.
    """
    exclude = set(exclude or ())
    cands = []
    for code, r in open_rows.items():
        if code in exclude:
            continue
        if r.get("ksic_source") not in ("dart", "snapshot_20260807"):
            continue
        # 🔴 corp_code 가 없으면 물을 수단이 없다 — 대상에 넣으면 예산만 먹고
        #    ksic_checked_at 커서만 전진해 «정말 물어야 할» 종목이 뒤로 밀린다.
        if w.is_blank(r.get("corp_code")):
            continue
        ck = r.get("ksic_checked_at")
        cands.append(((ck is not None), ck, code))
    cands.sort(key=lambda t: (t[0], t[1] or _MIN_DT, t[2]))
    return [c[2] for c in cands[:max(0, limit)]]


def maybe_refresh_corp_code(conn, key, days=CORP_CODE_REFRESH_DAYS) -> bool:
    """주 1회 corpCode.xml 1호출. 🔑 이 함수가 refresh_from_dart 의 «첫 호출자»다
    (지금까지 grep 0건 — 매핑이 2,556행에 얼어 있었다). 재무 「미매핑 239」도 같이 풀린다."""
    if not key:
        return False
    with conn.cursor() as cur:
        cur.execute("SELECT max(updated_at) FROM dart_corp_code")
        row = cur.fetchone()
    last = row[0] if row else None
    if last is not None and (now_kst().replace(tzinfo=None) - last).days < days:
        return False
    refresh_from_dart(conn, key)
    return True


def fill_ksic(conn, trade_date, fetcher=None, cap=DART_DAILY_CAP,
              recheck_max=RECHECK_MAX, key=None, raw_path=None) -> dict:
    """② KSIC 채우기(a) + 재확인 순환(b). 하루 총 상한 = cap(=300).

    반환 summary: fill_calls·recheck_calls·recheck_changed·filled·nodata·status_counts
    """
    out = {"fill_calls": 0, "recheck_calls": 0, "recheck_changed": 0, "filled": 0,
           "nodata": 0, "status_counts": {}, "quota_hit": False, "blocked": False,
           "rail_tripped": False, "skipped": None, "fill_targets": 0, "recheck_targets": 0}
    key = key if key is not None else _load_dart_key()
    if not key:
        logger.warning("[sector] OPENDART_API_KEY 미설정 - KSIC 채우기 스킵(EOD 비차단)")
        out["skipped"] = "no_dart_key"
        return out
    f = fetcher if fetcher is not None else DartCompanyFetcher(key)
    raw_path = raw_path or os.path.join(
        SECTOR_DIR, "dart_company_%s.jsonl" % trade_date.isoformat())

    open_rows = w.load_open_rows(conn)
    nodata = w.load_nodata(conn)
    now = now_kst().replace(tzinfo=None)

    def _ask(code, recheck):
        status, js = f.fetch(open_rows[code]["corp_code"])
        append_company_raw(raw_path, {"stock_code": code, "corp_code": open_rows[code]["corp_code"],
                                      "status": status, "payload": js})
        induty = ""
        if status == "000":
            induty = (js.get("induty_code") or "").strip()
        if induty and len(induty) > 5:
            logger.warning("[sector] %s induty_code 길이 %d(>5) - 저장은 하되 확인 필요: %s",
                           code, len(induty), induty)
        return {"stock_code": code, "ksic_code": induty or None, "recheck": recheck}

    # (a) 채우기
    targets_a = _fill_targets(open_rows, nodata, now)
    out["fill_targets"] = len(targets_a)
    resp_a = []
    for code in targets_a:
        if f.calls >= cap:
            logger.warning("[sector] DART 일일 상한 %d 도달 - 채우기 %d종목 오늘 미수집(내일 재개)",
                           cap, len(targets_a) - len(resp_a) - out["nodata"])
            break
        try:
            r = _ask(code, False)
        except DartQuotaExceeded:
            logger.warning("[sector] DART 일일 한도 초과 - KSIC 채우기 중단")
            out["quota_hit"] = True
            break
        except DartBlocked:
            logger.error("[sector] opendart 차단 - KSIC 채우기 중단")
            out["blocked"] = True
            break
        if r["ksic_code"]:
            resp_a.append(r)
        else:
            w.upsert_nodata(conn, code)
            out["nodata"] += 1
    calls_after_a = f.calls
    out["fill_calls"] = calls_after_a
    if resp_a:
        res = w.apply_ksic_updates(conn, resp_a, trade_date)
        out["filled"] = res["counts"]["filled"]

    # (b) 재확인 순환 — 잔여 예산으로
    resp_b = []
    if not (out["quota_hit"] or out["blocked"]):
        budget = min(recheck_max, max(0, cap - f.calls))
        targets_b = _recheck_targets(open_rows, set(targets_a), budget)
        out["recheck_targets"] = len(targets_b)
        for code in targets_b:
            try:
                resp_b.append(_ask(code, True))
            except DartQuotaExceeded:
                out["quota_hit"] = True
                break
            except DartBlocked:
                out["blocked"] = True
                break
    out["recheck_calls"] = f.calls - calls_after_a
    out["status_counts"] = dict(f.status_counts)
    if resp_b:
        try:
            res = w.apply_ksic_updates(conn, resp_b, trade_date, rail=True)
        except RuntimeError as e:
            out["rail_tripped"] = True
            out["error"] = str(e)
            logger.error("[sector] 재확인 레일 발동 - 그날 재확인분 전부 롤백: %s", e)
            raise SectorStageError(str(e), partial=out)
        out["recheck_changed"] = len(res["changed_codes"])
        if out["recheck_changed"] > 10:
            logger.warning("[sector] 재확인 값→값 %d건 - 레일 아래지만 이례적이다",
                           out["recheck_changed"])
    return out


def recopy_preferred(conn, trade_date, source="eod") -> dict:
    """(c) 우선주 재복사 — (a)(b) 로 부모가 바뀐 자식을 받는다.
    🔑 부트스트랩 3b 와 «같은 함수»다(정의가 둘로 갈리지 않게)."""
    open_rows = w.load_open_rows(conn)
    cands = {}
    for code in sorted(open_rows):
        p = w.parent_code(code)
        if p is None or p not in open_rows:
            continue
        prow = open_rows[p]
        c = {}
        if not w.is_blank(prow.get("ksic_code")):
            c["ksic_code"] = prow.get("ksic_code")
            c["ksic_source"] = "parent:%s" % p
            c["corp_code"] = prow.get("corp_code")
        if not w.is_blank(prow.get("ksic3_name")):
            c["ksic3_name"] = prow.get("ksic3_name")
        if c:
            cands[code] = c
    if not cands:
        return {"closed": 0, "inserted": 0, "updated": 0,
                "counts": {"changed": 0, "filled": 0, "new": 0, "unchanged": 0,
                           "skipped_past": 0}}
    plan = w.plan_map_changes(open_rows, cands, trade_date)
    res = w.write_map(conn, plan, source)
    res["counts"] = plan["counts"]
    return res
