# collectors/corp_events_collector.py
"""corp_events 증분 수집 + 헬스 reconcile — OpenDART list.json(발행공시).

운영 EOD 경로용 경량 수집기. 연구 트리(scripts/backfill_corp_events.py)를 import 하지
않고 최소 list.json 클라이언트를 재구현한다(corp_code 불필요 — list.json 은
corp_code 없이 기간+공시유형으로 전체 상장사 공시를 반환하며 각 항목에 stock_code 포함).

usage:
  python -m collectors.corp_events_collector                 # 최근 7일 수집
  python -m collectors.corp_events_collector --lookback 30
  python -m collectors.corp_events_collector --reconcile-only 2026-07-06
"""
import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.split_factor_infer import infer_and_stamp_split_factors  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"
DART_PBLNTF_TY = "B"  # 발행공시 (분할/증자류)
_MAX_WINDOW_DAYS = 90
_MAX_PAGES = 20
_PAGE_COUNT = 100
_BACKOFF_START = 0.5
_BACKOFF_CAP = 8.0

# report_nm 키워드 → event_type (scripts DART_EVENT_MAP 미러, import 금지)
DART_EVENT_MAP = [
    (["주식분할", "액면분할"], "split"),
    (["무상증자"], "bonus_issue"),
    (["유상증자"], "rights_issue"),
]


def _parse_dart_key_from_lines(lines) -> str:
    """.env 라인들에서 정확히 'OPENDART_API_KEY' 키만 매칭(변형 키 오인 방지).

    이전엔 startswith 로 매칭해 'OPENDART_API_KEY_BACKUP=...' 같은 변형 키까지
    잘못 집어올 수 있었다(2026-07-06 code review, R6). 'export ' 접두는 허용
    (쉘 소싱 가능한 .env 관례).
    """
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == "OPENDART_API_KEY":
            return v.strip().strip('"').strip("'")
    return ""


def _load_dart_key() -> str:
    """OPENDART_API_KEY — 환경변수 우선, 없으면 프로젝트 .env 최소 파싱(dotenv 의존 회피)."""
    key = (os.getenv("OPENDART_API_KEY") or "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            return _parse_dart_key_from_lines(f)
    except OSError:
        return ""


def _classify(report_nm: str):
    for keywords, etype in DART_EVENT_MAP:
        if any(kw in report_nm for kw in keywords):
            return etype
    return None


def _to_compact(d: str) -> str:
    return d.replace("-", "") if d else d


def _dart_list_page(key: str, bgn_de: str, end_de: str, page_no: int) -> dict:
    params = {
        "crtfc_key": key,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "pblntf_ty": DART_PBLNTF_TY,
        "page_count": _PAGE_COUNT,
        "page_no": page_no,
    }
    resp = requests.get(f"{DART_BASE}/list.json", params=params, timeout=15)
    resp.encoding = "utf-8"
    return resp.json()


def fetch_dart_events(key: str, bgn_de: str, end_de: str):
    """DART list.json 전체 페이지 수집. 반환 (items, last_status).

    status=='020'(사용한도/요청과다) → 지수 백오프 재시도(하드코딩 일일한도 없음).
    status=='013'(데이터 없음) → 정상 종료. '000' → 성공. 그 외 → 중단(last_status 보존).
    """
    items = []
    status = None
    page = 1
    total_page = 1
    backoff = _BACKOFF_START
    while page <= total_page and page <= _MAX_PAGES:
        data = _dart_list_page(key, bgn_de, end_de, page)
        status = data.get("status")
        if status == "020":  # rate limited → 백오프 후 같은 페이지 재시도
            if backoff > _BACKOFF_CAP:
                break
            time.sleep(backoff)
            backoff *= 2
            continue
        if status == "013":  # 조회 데이터 없음
            break
        if status != "000":
            logger.warning("[DART] list.json status=%s msg=%s", status, data.get("message"))
            break
        total_page = int(data.get("total_page") or 1)
        items.extend(data.get("list") or [])
        page += 1
    return items, status


def _rows_from_items(items: list) -> list:
    """DART 항목 → [(stock_code, event_type, event_date_iso, meta_dict)] (유효분류만)."""
    rows = []
    for it in items:
        code = (it.get("stock_code") or "").strip()
        if not (len(code) == 6 and code.isdigit()):
            continue
        report_nm = it.get("report_nm", "")
        etype = _classify(report_nm)
        if not etype:
            continue
        rcept_dt = (it.get("rcept_dt") or "").strip()
        if len(rcept_dt) != 8 or not rcept_dt.isdigit():
            continue
        event_date_iso = f"{rcept_dt[0:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}"
        meta = {
            "source": "opendart",
            "rcept_no": it.get("rcept_no", ""),
            "report_nm": report_nm,
            "rcept_dt": rcept_dt,
        }
        rows.append((code, etype, event_date_iso, meta))
    return rows


def _to_iso(d: str) -> str:
    return d if "-" in d else f"{d[0:4]}-{d[4:6]}-{d[6:8]}"


def _window(target_date: str, lookback_days: int):
    """수집 윈도우 (bgn_compact, end_compact) — end=target_date|오늘, <=90일."""
    end = date.fromisoformat(_to_iso(target_date)) if target_date else now_kst().date()
    span = min(max(int(lookback_days), 1), _MAX_WINDOW_DAYS)
    bgn = end - timedelta(days=span)
    return bgn.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def collect_corp_events(target_date: str = None, lookback_days: int = 7) -> dict:
    """최근 lookback_days(<=90) 발행공시를 DART 에서 수집→corp_events UPSERT(중복 무시)
    후 split_factor 추론 스탬프. OPENDART_API_KEY 부재 시 EOD 비차단(스킵 반환)."""
    key = _load_dart_key()
    if not key:
        logger.warning("[corp_events] OPENDART_API_KEY 미설정 — 수집 스킵(EOD 비차단)")
        return {"codes": 0, "rows": 0, "skipped": "no_dart_key"}

    bgn_de, end_de = _window(target_date, lookback_days)
    items, status = fetch_dart_events(key, bgn_de, end_de)
    rows = _rows_from_items(items)

    inserted = 0
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            for code, etype, event_date_iso, meta in rows:
                cur.execute(
                    "INSERT INTO corp_events (stock_code, event_type, event_date, end_date, meta) "
                    "VALUES (%s, %s, %s, NULL, %s::jsonb) "
                    "ON CONFLICT (stock_code, event_type, event_date) DO NOTHING",
                    (code, etype, event_date_iso, json.dumps(meta, ensure_ascii=False)),
                )
                inserted += cur.rowcount
        conn.commit()
        stamped = infer_and_stamp_split_factors(conn)

    codes = len({r[0] for r in rows})
    logger.info("[corp_events] window %s~%s status=%s 매칭=%d 신규=%d 스탬프=%d",
                bgn_de, end_de, status, len(rows), inserted, stamped)
    return {"codes": codes, "rows": inserted, "matched": len(rows),
            "status": status, "stamped": stamped}


def reconcile_corp_events(trade_date: str) -> dict:
    """corp_events 헬스 reconcile (Item 4) — 이벤트 0건은 정상(희소)이라 FAIL 하지 않는다.

    판정은 DART 도달성: 윈도우 조회가 성공(000/013)이면 PASS, 도달 실패/키 부재면 FAIL/WARN.
    collection_reconciliation(dataset='corp_events') 기록. 비차단.
    """
    key = _load_dart_key()
    if not key:
        v = {"verdict": "WARN", "reason": "no_dart_key", "new_rows": 0}
        _write_recon_row(trade_date, real_rows=0, new_rows=0, verdict="WARN")
        return v

    end_de = _to_compact(trade_date)
    bgn_de = (date.fromisoformat(_to_iso(trade_date)) - timedelta(days=7)).strftime("%Y%m%d")

    try:
        items, status = fetch_dart_events(key, bgn_de, end_de)
        reachable = status in ("000", "013")
        new_rows = len(_rows_from_items(items))
        verdict = "PASS" if reachable else "FAIL"
    except Exception as e:  # noqa: BLE001 — 도달 실패는 비차단, verdict 로 보고
        logger.warning("[corp_events] reconcile DART 도달 실패: %s", e)
        status, new_rows, verdict = "error", 0, "FAIL"

    _write_recon_row(trade_date, real_rows=0, new_rows=new_rows, verdict=verdict)
    return {"trade_date": trade_date, "status": status,
            "new_rows": new_rows, "verdict": verdict}


def _write_recon_row(trade_date: str, real_rows: int, new_rows: int, verdict: str) -> None:
    """collection_reconciliation UPSERT (corp_events 는 cross-DB 없음 → coverage/match=NULL 의미)."""
    passed = 1.0 if verdict == "PASS" else 0.0
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO collection_reconciliation "
                "(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict) "
                "VALUES (%s,'corp_events',%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (trade_date, dataset) DO UPDATE SET "
                "real_rows=EXCLUDED.real_rows, new_rows=EXCLUDED.new_rows, overlap=EXCLUDED.overlap, "
                "value_match_rate=EXCLUDED.value_match_rate, coverage=EXCLUDED.coverage, verdict=EXCLUDED.verdict",
                (trade_date, real_rows, new_rows, 0, passed, passed, verdict),
            )
        conn.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=7)
    ap.add_argument("--date", default=None)
    ap.add_argument("--reconcile-only", default=None)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_corp_events(args.reconcile_only))
    else:
        print(collect_corp_events(args.date, args.lookback))
