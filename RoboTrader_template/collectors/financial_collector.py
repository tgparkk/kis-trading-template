"""재무 수집 오케스트레이터 — DART as-filed 원장 + KIS 분기비율.

usage:
  python -m collectors.financial_collector                                  # 창 기반 증분
  python -m collectors.financial_collector --backfill --year 2026 --reprt 11013
  python -m collectors.financial_collector --reconcile-only 2026-08-17
  python -m collectors.financial_collector --sweep

🔴 DB 쓰기는 financial_writer.py 에서만 한다(plan File Structure 경계). 이 파일은
   창 판정·수집 오케스트레이션·reconcile 판정·백필 CLI·정정 스윕만 맡는다.

🔴 실행 중 정정(2026-09-06, Task 6 review): 사업보고서(11011) 창(04/03~05/10)에 접수되는
   보고서는 «전년도» 결산분이다 — `_bsns_year_for` 참조. 자세한 내용은
   docs/superpowers/plans/2026-08-13-financial-collector.md Task 6 「실행 중 정정」 절.
"""
import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.dart_corp_code import load_map  # noqa: E402
from collectors.dart_financial_fetcher import (  # noqa: E402
    DartFinancialFetcher, DartQuotaExceeded, DartBlocked, append_raw)
from collectors.kis_financial_fetcher import fetch_quarterly_ratio  # noqa: E402
from collectors import financial_writer as w  # noqa: E402
from collectors import financial_metrics as fm  # noqa: E402
from collectors.daily_collector import load_universe  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 2026-08-12 합의 창. 법정기한 +3일 여유.
# ⚠️ 창 시작은 반드시 영업일이어야 한다 — 08/15 는 토요일(광복절)이라 EOD 가 안 돈다.
WINDOWS = {
    "11011": ((4, 3), (5, 10)),    # 사업보고서 (기한 3/31)
    "11013": ((5, 18), (6, 20)),   # 1Q       (기한 5/15)
    "11012": ((8, 17), (9, 20)),   # 반기      (기한 8/14)
    "11014": ((11, 17), (12, 20)),  # 3Q       (기한 11/14)
}

_VALID_REPRT_CODES = frozenset(WINDOWS.keys())

RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scratchpad", "financials")

# Item 2c — 실행 시간 상한. EOD 파이프라인 전체를 물고 늘어지면 안 되니 45분에서 끊는다.
COLLECT_DEADLINE_SEC = 45 * 60

# I7(2026-09-06 사장님 결정) — 도달성 판정의 "소프트 실패" 허용 비율.
# 점검(800)·HTTP 실패 등은 그날 호출의 1% 까지 허용한다. 한도초과(020)·IP 차단은
# 비율과 무관하게 엄격(1건이라도 있으면 불허) — REACH_TOLERANCE 대상이 아니다.
REACH_TOLERANCE = 0.01


def active_reports(d: date) -> list:
    """그 날짜에 열려 있는 reprt_code 목록 (창 경계 포함)."""
    out = []
    for code, ((bm, bd), (em, ed)) in WINDOWS.items():
        if (d.month, d.day) >= (bm, bd) and (d.month, d.day) <= (em, ed):
            out.append(code)
    return sorted(out)


def _bsns_year_for(d: date, reprt_code: str) -> str:
    """사업연도(bsns_year) 파생 — reprt_code 별로 다르다.

    🔴 사업보고서(11011) 창은 04/03~05/10 에 열리지만, 거기 접수되는 보고서는
    «전년도(Y-1)» 결산분이다(법정기한 3/31이 그 전년도 실적 마감). 이걸
    `d.year` 그대로 쓰면 아직 존재하지 않는 당해년도 결산분을 조회해
    전 종목이 013(무자료)로 응답하고, 그게 다시 두드리면 안 되는 «확정»으로
    영구 기록돼 실제 데이터가 나온 뒤에도 다시 안 두드리는 결손이 생긴다.
    분기(1Q/3Q)·반기 창은 그 해 그대로다."""
    return str(d.year - 1) if reprt_code == "11011" else str(d.year)


def _to_iso(s: str) -> str:
    return s if "-" in s else f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _parse_dart_key_from_lines(lines) -> str:
    """정확히 'OPENDART_API_KEY' 만 매칭 (corp_events_collector.py 와 동일 규약).
    startswith 로 하면 'OPENDART_API_KEY_BACKUP' 같은 변형 키를 잘못 집는다."""
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
    key = (os.getenv("OPENDART_API_KEY") or "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            return _parse_dart_key_from_lines(f)
    except OSError:
        return ""


def _pending_targets(conn, codes, bsns_year: str, reprt_code: str) -> list:
    """아직 안 받은 (stock_code, corp_code). 이미 적재분과 «013 확정분»을 뺀다.

    🔑 013(무자료)을 기록하지 않으면 매일 같은 것을 두드린다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT stock_code FROM dart_financial_filings "
            "WHERE bsns_year=%s AND reprt_code=%s", (bsns_year, reprt_code))
        done = {r[0] for r in cur.fetchall()}
        cur.execute(
            "SELECT stock_code FROM dart_financial_nodata "
            "WHERE bsns_year=%s AND reprt_code=%s", (bsns_year, reprt_code))
        nodata = {r[0] for r in cur.fetchall()}
    return [(sc, cc) for sc, cc in codes if sc not in done and sc not in nodata]


def _kis_rotation(codes: list, daily_cap: int, day_of_year: int) -> list:
    """KIS 비율 조회 대상 회전 — 고정 접두(`codes[:daily_cap]`)는 무징후 절단이다.

    universe 가 daily_cap 보다 크면 매일 같은 앞쪽 종목만 영원히 조회되고 나머지는
    한 번도 안 돈다. 날짜(연중 일수) 기반으로 시작점을 돌리면 ⌈N/cap⌉ 회 안에
    전 종목이 최소 한 번씩 커버된다.
    """
    n = len(codes)
    if n == 0:
        return []
    offset = (day_of_year * daily_cap) % n
    order = codes[offset:] + codes[:offset]
    return order[:daily_cap]


def _summary_path(d: date) -> str:
    return os.path.join(RAW_DIR, f"dart_{d.strftime('%Y%m%d')}_summary.json")


def _build_summary(d: date, fetcher, n_filings: int, n_accounts: int, n_kis_ok: int,
                    n_kis_fail: int, quota_hit: bool, cap_hit: bool, blocked: bool,
                    targets_total: int, targets_processed: int, unmapped: int,
                    kis_empty: int = 0, aborted=None, deadline_hit: bool = False) -> dict:
    """reconcile_financials 의 spec §8 조건1(도달성)이 읽는 per-run 스냅샷."""
    return {
        "trade_date": d.isoformat(),
        "calls": fetcher.calls,
        "status_counts": dict(fetcher.status_counts),
        "filings": n_filings,
        "accounts": n_accounts,
        "kis_ok": n_kis_ok,
        "kis_fail": n_kis_fail,
        "kis_empty": kis_empty,
        "quota_hit": quota_hit,
        "cap_hit": cap_hit,
        "blocked": blocked,
        "targets_total": targets_total,
        "targets_processed": targets_processed,
        "unmapped_corp_code": unmapped,
        "aborted": aborted,
        "deadline_hit": deadline_hit,
    }


def _write_summary(d: date, summary: dict) -> None:
    path = _summary_path(d)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False)
    except OSError as e:
        logger.warning("[financials] summary 파일 기록 실패(비차단): %s", e)


def _read_summary(d: date):
    """오늘자 summary 를 읽는다. 없으면 None(reconcile 이 WARN 으로 처리)."""
    path = _summary_path(d)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def collect_financials(target_date: str = None, daily_cap: int = 800) -> dict:
    """창 안이면 미수집분을 daily_cap(=DART 호출 기준)까지 수집. 창 밖이면 no-op."""
    t0 = time.monotonic()  # Item 2c — 실행 시간 상한 기준점(함수 시작 시각).
    key = _load_dart_key()
    if not key:
        logger.warning("[financials] OPENDART_API_KEY 미설정 - 수집 스킵(EOD 비차단)")
        return {"skipped": "no_dart_key", "dart_calls": 0, "filings": 0, "accounts": 0}

    d = date.fromisoformat(_to_iso(target_date)) if target_date else now_kst().date()
    reports = active_reports(d)
    if not reports:
        logger.info("[financials] %s 는 수집 창 밖 - no-op", d)
        return {"skipped": "out_of_window", "dart_calls": 0, "filings": 0, "accounts": 0}

    fetcher = DartFinancialFetcher(key)
    n_filings = n_accounts = n_kis_ok = n_kis_fail = 0
    quota_hit = cap_hit = blocked = deadline_hit = False
    targets_total = targets_processed = 0
    unmapped = kis_empty = 0
    aborted = None
    http_fail_streak = 0
    raw_path = os.path.join(RAW_DIR, f"dart_{d.strftime('%Y%m%d')}.jsonl.gz")

    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        fm.ensure_view(conn)
        cmap = load_map(conn)
        universe = load_universe(conn)
        codes = []
        for sc in universe:
            cc = cmap.get(sc)
            if cc:
                codes.append((sc, cc))
            else:
                unmapped += 1
        # 무징후 절단 금지 — corp_code 매핑이 없어 대상에서 빠진 종목은 반드시 WARNING.
        if unmapped:
            logger.warning("[financials] corp_code 매핑 없는 종목 %d개 - 이번 실행 대상에서 제외",
                           unmapped)

        for reprt_code in reports:
            bsns_year = _bsns_year_for(d, reprt_code)
            targets = _pending_targets(conn, codes, bsns_year, reprt_code)
            targets_total += len(targets)
            logger.info("[financials] %s/%s 대상 %d종목 (cap %d)",
                        bsns_year, reprt_code, len(targets), daily_cap)
            for idx, (stock_code, corp_code) in enumerate(targets):
                if time.monotonic() - t0 > COLLECT_DEADLINE_SEC:
                    uncovered = len(targets) - idx
                    logger.warning(
                        "[financials] 실행 시간 상한 %d초 도달 - %s/%s 종목 %d개 오늘 미수집(내일 재개)",
                        COLLECT_DEADLINE_SEC, bsns_year, reprt_code, uncovered)
                    deadline_hit = True
                    break
                if fetcher.calls >= daily_cap:
                    uncovered = len(targets) - idx
                    logger.warning(
                        "[financials] 일일 상한 %d 도달 - %s/%s 종목 %d개 오늘 미수집(내일 재개)",
                        daily_cap, bsns_year, reprt_code, uncovered)
                    cap_hit = True
                    break
                try:
                    got = _fetch_and_store(conn, fetcher, raw_path,
                                           stock_code, corp_code, bsns_year, reprt_code)
                except DartQuotaExceeded:
                    logger.warning("[financials] DART 일일 한도 초과 - 중단(체크포인트는 DB 자체)")
                    quota_hit = True
                    break
                except DartBlocked as e:
                    # 🔴 quota_hit 과 다르다 — 차단은 EOD 가 에러로 봐야 한다.
                    # summary 를 먼저 기록해(부분 진척 보존) reconcile 이 읽을 수 있게 한 뒤 재발생시킨다.
                    logger.error("[financials] opendart 차단 - 중단: %s", e)
                    blocked = True
                    _write_summary(d, _build_summary(
                        d, fetcher, n_filings, n_accounts, n_kis_ok, n_kis_fail,
                        quota_hit, cap_hit, blocked, targets_total, targets_processed, unmapped,
                        kis_empty=kis_empty, aborted=aborted, deadline_hit=deadline_hit))
                    raise
                n_filings += got[0]
                n_accounts += got[1]
                targets_processed += 1
                # Item 2b — HTTP_FAIL 이 연속되면 opendart 가 사실상 응답 불능인데,
                # 남은 대상을 전부 무징후로 계속 두드리는 건 낭비고 신호도 못 남긴다.
                if got[2] == "HTTP_FAIL":
                    http_fail_streak += 1
                else:
                    http_fail_streak = 0
                if http_fail_streak >= 5:
                    uncovered = len(targets) - (idx + 1)
                    logger.warning(
                        "[financials] HTTP_FAIL 연속 %d회 도달 - %s/%s 종목 %d개 오늘 미수집(내일 재개)",
                        http_fail_streak, bsns_year, reprt_code, uncovered)
                    aborted = "http_fail_streak"
                    break
            if quota_hit or cap_hit or aborted or deadline_hit:
                break

        # KIS 는 DART 한도와 무관하다. DART 가 막혀도 돌린다.
        # 고정 접두(codes[:cap])는 매일 같은 앞쪽 800종목만 돌게 만드는 무징후 절단이다.
        # 날짜 기반 결정적 순환으로 바꿔 ⌈N/cap⌉ 회 안에 전 종목이 한 번씩 돈다.
        n_codes = len(codes)
        kis_uncovered = 0
        n_kis_fail_first = None
        kis_attempted = 0
        if n_codes:
            kis_batch = _kis_rotation(codes, daily_cap, d.timetuple().tm_yday)
            kis_uncovered = n_codes - len(kis_batch)
            kis_attempted = len(kis_batch)
            for stock_code, _ in kis_batch:
                try:
                    rows = fetch_quarterly_ratio(stock_code)
                except Exception as e:  # noqa: BLE001 - 종목 하나 실패가 전체를 막지 않는다
                    n_kis_fail += 1
                    if n_kis_fail_first is None:
                        n_kis_fail_first = e
                    continue
                # Item 4 — fetch_quarterly_ratio 는 "무자료"와 "호출 실패"를 둘 다 []로
                # 돌려준다(api/kis_financial_api.py 는 수정 대상 밖). 빈 응답을 그냥 성공으로
                # 세면 실패가 조용히 묻힌다 - 별도 카운트로 남긴다.
                if not rows:
                    kis_empty += 1
                n_kis_ok += w.upsert_kis_ratio(conn, rows)
            if kis_uncovered:
                logger.warning(
                    "[financials] KIS 비율 조회 상한 %d - 오늘 %d종목 미조회(내일 순환으로 커버)",
                    daily_cap, kis_uncovered)
        if n_kis_fail:
            detail = f" (예: {type(n_kis_fail_first).__name__}: {n_kis_fail_first})" \
                if n_kis_fail_first is not None else ""
            logger.warning("[financials] KIS 비율 조회 실패 %d건%s", n_kis_fail, detail)
        if kis_empty:
            ratio = (kis_empty / kis_attempted * 100) if kis_attempted else 0.0
            logger.warning(
                "[financials] KIS 비율 응답 빈 값 %d/%d건(%.1f%%) - 무자료/호출실패 구분 불가",
                kis_empty, kis_attempted, ratio)

        _recompute_amendment_flags(conn)
        try:
            coverage = fm.report_mapping_coverage(conn)
        except Exception as e:  # noqa: BLE001 - 커버리지 리포트 실패가 이미 커밋된 수집 결과를 막으면 안 된다
            logger.warning("[financials] mapping coverage 리포트 실패(비차단): %s", e)
            coverage = {}

    # 주 1회(월요일) 정정 스윕. 창과 무관하게 돈다 - 정정·지연공시는 창 밖에도 온다.
    # fetcher 를 재사용해 min_interval·calls·status_counts 를 한 곳에서 누적한다.
    sweep = None
    if d.weekday() == 0:
        try:
            sweep = sweep_amendments(fetcher=fetcher)
        except DartBlocked as e:
            # Item 1 — 스윕 중 차단도 본 수집 중 차단과 동일하게 다뤄야 한다.
            # quota 처럼 삼키면 IP 차단일에 reconcile 이 PASS 를 본다.
            logger.error("[financials] 정정 스윕 중 opendart 차단 - 중단: %s", e)
            blocked = True
            _write_summary(d, _build_summary(
                d, fetcher, n_filings, n_accounts, n_kis_ok, n_kis_fail,
                quota_hit, cap_hit, blocked, targets_total, targets_processed, unmapped,
                kis_empty=kis_empty, aborted=aborted, deadline_hit=deadline_hit))
            raise
        except Exception as e:  # noqa: BLE001 - 스윕 실패가 본 수집을 막지 않는다
            logger.warning("[financials] 정정 스윕 실패(비차단): %s", e)
            sweep = {"error": str(e)}

    summary = _build_summary(d, fetcher, n_filings, n_accounts, n_kis_ok, n_kis_fail,
                             quota_hit, cap_hit, blocked, targets_total, targets_processed,
                             unmapped, kis_empty=kis_empty, aborted=aborted,
                             deadline_hit=deadline_hit)
    _write_summary(d, summary)

    out = dict(summary)
    out["reports"] = reports
    out["dart_calls"] = fetcher.calls
    out["mapping_coverage"] = coverage
    out["sweep"] = sweep

    # 🔴 Minor — mapping_coverage.unmatched_stocks 는 종목 목록 전체다. INFO 로그에
    # 그대로 찍으면 로그가 부풀어 오른다. 반환값(out)에는 전체 목록을 남기고, 로그엔
    # 개수(matched/unmatched)만 남긴다.
    log_summary = dict(out)
    log_summary["mapping_coverage"] = {
        "matched": coverage.get("matched"),
        "unmatched_count": coverage.get("unmatched_count"),
    }
    logger.info("[financials] %s", log_summary)
    return out


def _fetch_and_store(conn, fetcher, raw_path, stock_code, corp_code, bsns_year, reprt_code):
    """CFS 시도 → 013 이면 OFS 재시도. 반환 (filings, accounts, last_status).

    last_status 는 Item 2b(HTTP_FAIL 연속 감지)가 「이 대상의 결과가 HTTP_FAIL 이었는가」를
    판별하는 데 쓴다 — fetcher.status_counts 는 누적치라 대상 단위 판별에 못 쓴다."""
    for fs_div in ("CFS", "OFS"):
        status, payload = fetcher.fetch(corp_code, bsns_year, reprt_code, fs_div)
        if status == "013":
            continue
        if status != "000":
            logger.warning("[financials] %s %s/%s/%s status=%s",
                           stock_code, bsns_year, reprt_code, fs_div, status)
            return 0, 0, status
        line_no = append_raw(raw_path, payload)
        filing, accounts = w.rows_from_dart_response(payload, stock_code, fs_div)
        if filing is None:
            return 0, 0, status
        filing["raw_path"] = f"{os.path.basename(raw_path)}#L{line_no}"
        filing["rcept_dt"] = _rcept_dt_from_no(filing["rcept_no"])
        w.upsert_filing(conn, filing)
        return 1, w.upsert_accounts(conn, accounts), status

    # CFS·OFS 둘 다 013 = 무자료 확정. 기록해서 내일 다시 안 두드린다.
    w.upsert_nodata(conn, stock_code, bsns_year, reprt_code)
    return 0, 0, "013"


def _rcept_dt_from_no(rcept_no: str):
    """접수번호 앞 8자리가 접수일이다 (DART 규약). 형식이 어긋나면 None."""
    s = (rcept_no or "").strip()
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    # rcept_dt 가 없으면 fn_financials_as_of(PIT 뷰)가 이 filing 을 절대 못 본다 — 무징후면 안 된다.
    logger.warning(
        "[financials] rcept_no 형식 이상 - rcept_dt 없음(PIT 뷰에서 이 filing 이 안 보인다): rcept_no=%r",
        rcept_no)
    return None


def _recompute_amendment_flags(conn) -> None:
    """is_amendment 재계산 — DB 쓰기는 financial_writer 로 위임한다."""
    w.recompute_amendment_flags(conn)


def _is_reachable(summary: dict):
    """도달성 판정 (spec §8 조건1) — I7(2026-09-06 사장님 결정): 소프트 실패 1% 허용.

    반환: (reachable: bool, reason_detail: str) — reason_detail 은 ERROR 로그용.

    - blocked 는 status_counts 와 무관하게 불허("blocked") — 엄격.
    - 020(한도초과)이 하나라도 있으면 비율과 무관하게 불허("quota") — 엄격.
    - 그 외 {000,013} 아닌 상태(점검 800·HTTP 실패 등 "소프트" 실패)는 그날 호출의
      REACH_TOLERANCE(1%) 까지는 허용한다. calls 가 0(호출 자체가 없었던 날)이면
      실패로 볼 근거가 없으므로 도달 가능으로 본다.
    """
    status_counts = summary.get("status_counts") or {}
    if summary.get("blocked"):
        return False, "blocked"
    if status_counts.get("020", 0) > 0:
        return False, "quota"
    soft = sum(count for status, count in status_counts.items()
               if status not in {"000", "013"})
    total = summary.get("calls") or sum(status_counts.values())
    if total == 0:
        return True, ""
    ratio = soft / total
    if ratio <= REACH_TOLERANCE:
        return True, ""
    return False, f"soft_fail_ratio={ratio:.3f} ({soft}/{total})"


def reconcile_financials(trade_date: str = None) -> dict:
    """창 밖은 PASS(out_of_window). 창 안은 spec §8 두 조건을 모두 본다.

    1. 도달성 — `_is_reachable()` 참조. I7(2026-09-06 사장님 결정)로 점검(800)·HTTP
       실패 등 "소프트" 실패는 그날 호출의 1%(REACH_TOLERANCE) 까지 허용한다.
       단 한도초과(020)·IP 차단(blocked)은 비율과 무관하게 엄격(1건이면 FAIL).
    2. 진척률 — 미수집 잔량이 3영업일 연속 안 줄면 FAIL.

    🔑 도달성만 보면 «호출은 성공하는데 잔량이 안 줄어드는» 상태를 못 잡는다.
       일봉 결손 49,252행이 2년 5개월간 무경보였던 게 정확히 그 형태다.

    🔴 Item 5 — WARN 경로(no_dart_key·no_summary)도 new_rows=0 을 박으면 stalled
    게이트가 영원히 못 뜬다. remaining 은 DART 키가 없어도 DB 읽기만으로 계산 가능하니
    WARN 경로에서도 «그 값»을 new_rows 로 써야 한다. 추가로, no_summary 가 3일 연속
    WARN 뒤에도 반복되면(=3일 연속 실행 안 됨) FAIL 로 격상한다.
    """
    d = date.fromisoformat(_to_iso(trade_date)) if trade_date else now_kst().date()
    iso = d.isoformat()
    reports = active_reports(d)
    if not reports:
        _write_recon(iso, 0, "PASS")
        return {"trade_date": iso, "verdict": "PASS", "reason": "out_of_window"}

    # remaining·prev 는 DART 키/summary 유무와 무관하게(DB 읽기만으로) 계산 가능하다.
    # WARN 조기반환 «전에» 구해야 WARN 경로도 이 값을 new_rows 로 쓸 수 있다.
    with KisDbConnection.get_connection() as conn:
        cmap = load_map(conn)
        universe = load_universe(conn)
        codes = [(sc, cmap[sc]) for sc in universe if sc in cmap]
        remaining = sum(len(_pending_targets(conn, codes, _bsns_year_for(d, rc), rc))
                        for rc in reports)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT new_rows, verdict FROM collection_reconciliation "
                "WHERE dataset='financials' AND trade_date < %s "
                "ORDER BY trade_date DESC LIMIT 3", (iso,))
            prev_rows = cur.fetchall()
    prev = [r[0] for r in prev_rows]
    prev_verdicts = [r[1] for r in prev_rows]

    key = _load_dart_key()
    if not key:
        _write_recon(iso, remaining, "WARN")
        return {"trade_date": iso, "verdict": "WARN", "reason": "no_dart_key",
                "remaining": remaining}

    summary = _read_summary(d)
    if summary is None:
        if len(prev_verdicts) == 3 and all(v == "WARN" for v in prev_verdicts):
            # 3일 연속 WARN(요약 없음) 뒤 오늘도 또 없다 - 「조용히 안 돌아감」이다.
            logger.error(
                "[financials] reconcile: 3일 연속 WARN(no_summary) 후 오늘도 summary "
                "없음 - FAIL 로 격상")
            _write_recon(iso, remaining, "FAIL")
            return {"trade_date": iso, "verdict": "FAIL", "reason": "no_summary_3d",
                    "remaining": remaining}
        _write_recon(iso, remaining, "WARN")
        return {"trade_date": iso, "verdict": "WARN", "reason": "no_summary",
                "remaining": remaining}

    reachable, reach_detail = _is_reachable(summary)

    stalled = len(prev) == 3 and remaining > 0 and all(p == remaining for p in prev)

    if not reachable:
        verdict, reason = "FAIL", "unreachable"
        logger.error(
            "[financials] reconcile: 도달성 실패(사유=%s) - "
            "status_counts=%s blocked=%s", reach_detail,
            summary.get("status_counts"), summary.get("blocked"))
    elif stalled:
        verdict, reason = "FAIL", "stalled"
        logger.error("[financials] 진척 정지 - 잔량 %d 가 3회 연속 동일. "
                     "호출은 성공하는데 데이터가 안 들어오고 있다", remaining)
    else:
        verdict, reason = "PASS", None

    _write_recon(iso, remaining, verdict)
    out = {"trade_date": iso, "verdict": verdict, "remaining": remaining, "prev": prev,
           "reachable": reachable}
    if reason:
        out["reason"] = reason
    return out


def _write_recon(trade_date: str, remaining: int, verdict: str) -> None:
    iso = _to_iso(trade_date)
    passed = 1.0 if verdict == "PASS" else 0.0
    with KisDbConnection.get_connection() as conn:
        w.upsert_reconciliation(conn, iso, "financials", remaining, passed, passed, verdict)


def backfill(year: str, reprt_code: str, interval: float = 0.34, cap: int = None) -> dict:
    """창을 무시하고 미수집분만 채운다. 수동 실행 전용.

    ⚠️ 평일 16:00 EOD 와 겹치면 안 된다 — corp_events_collector 가 같은 호스트다.
    """
    if not (isinstance(year, str) and len(year) == 4 and year.isdigit()):
        raise ValueError(f"year 는 4자리 숫자 문자열이어야 한다: {year!r}")
    if reprt_code not in _VALID_REPRT_CODES:
        raise ValueError(f"reprt_code 는 {sorted(_VALID_REPRT_CODES)} 중 하나여야 한다: {reprt_code!r}")

    key = _load_dart_key()
    if not key:
        return {"skipped": "no_dart_key"}
    fetcher = DartFinancialFetcher(key, min_interval=interval)
    raw_path = os.path.join(RAW_DIR, f"dart_backfill_{year}_{reprt_code}.jsonl.gz")
    n_f = n_a = 0
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        fm.ensure_view(conn)
        cmap = load_map(conn)
        codes = [(sc, cmap[sc]) for sc in load_universe(conn) if sc in cmap]
        targets = _pending_targets(conn, codes, year, reprt_code)
        logger.info("[backfill] %s/%s 대상 %d종목 interval=%.2f", year, reprt_code,
                    len(targets), interval)
        for i, (sc, cc) in enumerate(targets, 1):
            if cap is not None and fetcher.calls >= cap:
                logger.warning("[backfill] cap %d 도달 - 남은 %d종목 미수집",
                               cap, len(targets) - i + 1)
                break
            try:
                f_, a_, _status = _fetch_and_store(conn, fetcher, raw_path, sc, cc, year, reprt_code)
            except (DartQuotaExceeded, DartBlocked) as e:
                logger.warning("[backfill] 중단(%s) - 남은 %d종목. 자정 이후 재실행",
                               type(e).__name__, len(targets) - i + 1)
                break
            n_f += f_
            n_a += a_
            if i % 100 == 0:
                logger.info("[backfill] %d/%d calls=%d", i, len(targets), fetcher.calls)
        _recompute_amendment_flags(conn)
    return {"year": year, "reprt": reprt_code, "calls": fetcher.calls,
            "status_counts": fetcher.status_counts, "filings": n_f, "accounts": n_a}


def sweep_amendments(lookback_days: int = 14, cap: int = 200, fetcher=None) -> dict:
    """최근 lookback_days 의 정정보고서를 list.json 으로 찾아 그 접수건만 재수집.

    창과 «무관하게» 돈다. 주 1회 호출 상정.
    🔑 창 기반 증분은 정정·지연공시를 구조적으로 놓친다 —
       3월 외 접수 16.1%, 지연 p99 735일.

    `fetcher` 를 넘기면(collect_financials 의 월요일 자동 실행) 그 인스턴스를 재사용한다 —
    min_interval·calls·status_counts 가 한 곳에 누적돼야 daily_cap/dart_calls 집계가 맞는다.
    독립 실행(CLI `--sweep`)이면 새로 하나 만든다.
    """
    import requests
    key = _load_dart_key()
    if not key:
        return {"skipped": "no_dart_key"}

    end = now_kst().date()
    bgn = end - timedelta(days=max(1, min(lookback_days, 90)))
    if fetcher is None:
        fetcher = DartFinancialFetcher(key)
    raw_path = os.path.join(RAW_DIR, f"dart_sweep_{end.strftime('%Y%m%d')}.jsonl.gz")

    items, page, total_page = [], 1, 1
    last_call = 0.0
    while page <= total_page and page <= 100:
        # list.json 도 opendart 호스트다 — fnlttSinglAcntAll 과 같은 min_interval 로 순차 호출.
        gap = time.time() - last_call
        if gap < fetcher.min_interval:
            time.sleep(fetcher.min_interval - gap)
        last_call = time.time()
        try:
            r = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=15, params={
                "crtfc_key": key, "bgn_de": bgn.strftime("%Y%m%d"),
                "end_de": end.strftime("%Y%m%d"), "pblntf_ty": "A",  # A = 정기공시
                "page_count": 100, "page_no": page})
            r.encoding = "utf-8"
            js = r.json()
        except Exception as e:  # noqa: BLE001 - list.json 오류는 스윕만 중단(본 수집엔 무영향)
            logger.warning("[sweep] list.json 요청 실패 - 스윕 중단(부분 결과 반환): %s", e)
            break
        st = js.get("status")
        if st == "013":
            break
        if st != "000":
            logger.warning("[sweep] list.json status=%s msg=%s", st, js.get("message"))
            break
        total_page = int(js.get("total_page") or 1)
        items.extend(js.get("list") or [])
        page += 1
    # 무징후 절단 금지
    if total_page > 100:
        logger.warning("[sweep] 페이지 절단: total_page=%d > 100 - 창을 좁힐 것(누락 발생)",
                       total_page)

    # 정정본만: report_nm 에 '기재정정' 이 붙는다
    targets = []
    for it in items:
        nm = it.get("report_nm", "")
        sc = (it.get("stock_code") or "").strip()
        if "정정" not in nm or not sc:
            continue
        rc = _reprt_code_from_report_nm(nm)
        yr = _bsns_year_from_report_nm(nm)
        if rc and yr:
            targets.append((sc, rc, yr))

    dropped = max(0, len(targets) - cap)
    if dropped:
        logger.warning(
            "[sweep] 정정 후보 %d건 중 cap(%d) 초과 %d건 이번 실행 미처리(다음 스윕에서)",
            len(targets), cap, dropped)

    n_f = n_a = 0
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        cmap = load_map(conn)
        for sc, rc, yr in targets[:cap]:
            if sc not in cmap:
                continue
            try:
                f_, a_, _status = _fetch_and_store(conn, fetcher, raw_path, sc, cmap[sc], yr, rc)
            except DartQuotaExceeded as e:
                # Item 1 — DartBlocked 는 여기서 잡지 않는다. quota 처럼 삼키면 IP 차단일에도
                # collect_financials 가 EOD 성공으로 보고, reconcile 이 PASS 를 낸다.
                # DartBlocked 는 이 except 에 안 걸려 자연히 위(collect_financials)로 전파된다.
                logger.warning("[sweep] 중단(%s)", type(e).__name__)
                break
            n_f += f_
            n_a += a_
        _recompute_amendment_flags(conn)
    logger.info("[sweep] 정정 후보 %d건 -> filings=%d accounts=%d calls=%d",
                len(targets), n_f, n_a, fetcher.calls)
    return {"candidates": len(targets), "filings": n_f, "accounts": n_a,
            "calls": fetcher.calls}


def _reprt_code_from_report_nm(nm: str):
    """'[기재정정]분기보고서 (2026.03)' → 11013. 판별 불가면 None(추측하지 않는다)."""
    if "사업보고서" in nm:
        return "11011"
    if "반기보고서" in nm:
        return "11012"
    if "분기보고서" not in nm:
        return None
    # 분기보고서는 1Q/3Q 를 괄호 안 월로 가른다: (YYYY.03)=1Q, (YYYY.09)=3Q
    import re as _re
    m = _re.search(r"\((\d{4})\.(\d{2})\)", nm)
    if not m:
        return None
    return {"03": "11013", "09": "11014"}.get(m.group(2))


def _bsns_year_from_report_nm(nm: str):
    import re as _re
    m = _re.search(r"\((\d{4})\.\d{2}\)", nm)
    return m.group(1) if m else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--daily-cap", type=int, default=800)
    ap.add_argument("--reconcile-only", default=None)
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--year", default=None)
    ap.add_argument("--reprt", default=None)
    ap.add_argument("--interval", type=float, default=0.34)
    ap.add_argument("--cap", type=int, default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--sweep-lookback", type=int, default=14)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_financials(args.reconcile_only))
    elif args.backfill:
        if not (args.year and args.reprt):
            ap.error("--backfill 은 --year 와 --reprt 가 필요하다")
        print(backfill(args.year, args.reprt, args.interval, args.cap))
    elif args.sweep:
        print(sweep_amendments(args.sweep_lookback))
    else:
        print(collect_financials(args.date, args.daily_cap))
