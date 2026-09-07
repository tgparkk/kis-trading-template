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
FETCH_FAIL_STREAK_MAX = 5     # 연속 실패가 이만큼이면 그날 재확인을 멈춘다(예산 보호)
BOOTSTRAP_VALID_FROM = date(2021, 1, 4)
_MIN_DT = datetime(1970, 1, 1)      # ksic_checked_at NULLS FIRST 정렬용 하한

_U_MARKET_SQL = "SELECT stock_code FROM stock_market WHERE " + SQL_STOCK_ONLY + " ORDER BY 1"

STATS_WINDOW_DAYS = 20        # 달력일(태쏘 load_day 와 같은 창)
UP_MULT = 1.15                # 태쏘 run_sector.py:123 «승계»(새 문턱 아님)
TAXONOMIES = (("ksic2", 2), ("ksic3", 3), ("ksic5", 5))

_STATS_SQL = (
    "WITH w AS ("
    "  SELECT stock_code, date, high, close,"
    "         LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close"
    "  FROM daily_prices"
    "  WHERE date BETWEEN %s AND %s AND close > 0 AND " + SQL_STOCK_ONLY +
    ") SELECT stock_code, high, close, prev_close FROM w WHERE date = %s ORDER BY stock_code")


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

    반환 summary: fill_calls·recheck_calls·recheck_changed·filled·nodata·
                  fetch_failed·fetch_fail_stop·cap_hit·status_counts

    🔴 실패(HTTP_FAIL·예상외 status)는 「없다」가 «아니다» — nodata 로 적으면 그 종목이
       30일간 조용해져 고장을 감춘다. 건수만 세고 행은 그대로 둔다(내일 다시 시도).
    🔴 summary 는 «어떤 경우에도» 올라간다 — 본문 전체를 try 로 감싸 어떤 예외든
       SectorStageError(partial=out) 로 승격한다(원인 예외는 chain 으로 보존).
    """
    out = {"fill_calls": 0, "recheck_calls": 0, "recheck_changed": 0, "filled": 0,
           "nodata": 0, "status_counts": {}, "quota_hit": False, "blocked": False,
           "rail_tripped": False, "skipped": None, "fill_targets": 0, "recheck_targets": 0,
           "fetch_failed": 0, "fetch_fail_stop": False, "cap_hit": False}
    try:
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
            """응답 dict, 또는 «실패»면 None. 🔴 실패와 「업종 없음」을 같이 처리하면
            고장이 nodata 로 묻힌다 — 013(무자료)·000+빈 induty 만 「없다」이다."""
            status, js = f.fetch(open_rows[code]["corp_code"])
            append_company_raw(raw_path, {"stock_code": code,
                                          "corp_code": open_rows[code]["corp_code"],
                                          "status": status, "payload": js})
            if status not in ("000", "013"):
                logger.warning("[sector] %s DART 응답 실패(status=%s) - 행 불변·내일 재시도",
                               code, status)
                return None
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
                out["cap_hit"] = True
                logger.warning("[sector] DART 일일 상한 %d 도달 - 채우기 %d종목 오늘 미수집(내일 재개)",
                               cap, len(targets_a) - len(resp_a) - out["nodata"]
                               - out["fetch_failed"])
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
            if r is None:                       # 실패 — 「없다」로 적지 않는다
                out["fetch_failed"] += 1
                continue
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
            streak = 0
            for i, code in enumerate(targets_b):
                # 🔴 예산은 «대상 수»로 잡았지만 fetch 하나가 내부 재시도로 최대 6호출을
                #    쓴다 — 매 호출 전 이 검사가 DART ≤300/일 의 최종 방어선이다.
                if f.calls >= cap:
                    out["cap_hit"] = True
                    logger.warning("[sector] DART 일일 상한 %d 도달 - 재확인 %d종목 오늘 미확인"
                                   "(내일 큐 앞에서 재개)", cap, len(targets_b) - i)
                    break
                try:
                    r = _ask(code, True)
                except DartQuotaExceeded:
                    logger.warning("[sector] DART 일일 한도 초과 - 재확인 중단")
                    out["quota_hit"] = True
                    break
                except DartBlocked:
                    logger.error("[sector] opendart 차단 - 재확인 중단")
                    out["blocked"] = True
                    break
                if r is None:
                    out["fetch_failed"] += 1
                    streak += 1
                    if streak >= FETCH_FAIL_STREAK_MAX:
                        out["fetch_fail_stop"] = True
                        logger.warning("[sector] DART 연속 실패 %d회 - 재확인 %d종목 남기고 중단"
                                       "(내일 재개)", streak, len(targets_b) - i - 1)
                        break
                    continue
                streak = 0
                resp_b.append(r)
        out["recheck_calls"] = f.calls - calls_after_a
        out["status_counts"] = dict(f.status_counts)
        if resp_b:
            try:
                res = w.apply_ksic_updates(conn, resp_b, trade_date, rail=True)
            except RuntimeError as e:
                out["rail_tripped"] = True
                out["error"] = str(e)
                logger.error("[sector] 재확인 레일 발동 - 그날 재확인분 전부 롤백: %s", e)
                raise SectorStageError(str(e), partial=out) from e
            out["recheck_changed"] = len(res["changed_codes"])
            if out["recheck_changed"] > 10:
                logger.warning("[sector] 재확인 값→값 %d건 - 레일 아래지만 이례적이다",
                               out["recheck_changed"])
        return out
    except SectorStageError:
        raise
    except Exception as e:
        # 🔴 여기서 예외만 던지면 그날의 fill_calls·nodata 가 통째로 사라져
        #    §8-5·§8-9 게이트가 그날을 «못 본다».
        out["error"] = str(e)
        logger.error("[sector] KSIC 채우기 중단(%s: %s) - 부분 집계를 들고 올라간다",
                     type(e).__name__, e)
        raise SectorStageError(str(e), partial=out) from e


def recopy_preferred(conn, trade_date, source="eod") -> dict:
    """(c) 우선주 재복사 — (a)(b) 로 부모가 바뀐 자식을 받는다.
    🔑 부트스트랩 3b 와 «같은 함수»다(정의가 둘로 갈리지 않게)."""
    open_rows = w.load_open_rows(conn)
    cands = {}
    for code in sorted(open_rows):
        p = w.parent_code(code)
        if p is None or p not in open_rows:
            continue
        # 🔴 복사 규칙은 sector_writer 헬퍼 «하나»다 — 필드 묶음이 두 곳에 있으면
        #    한쪽만 고쳐 자식이 부모와 다른 업종을 갖는다.
        #    부모가 바뀐 날의 재복사라 부모 값이 이긴다(fill_if_blank=False).
        c = w.copy_parent_values({}, open_rows[p], p, fill_if_blank=False)
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


def load_day_rows(conn, d) -> list:
    """그날 대상 행 — 창 «안»에 close>0 과 술어를 걸고 LAG 로 prev_close 를 구한 뒤
    date=d 만 남긴다(태쏘 load_day 와 «같은 순서»).

    🔴 daily_prices.date 는 TEXT(YYYY-MM-DD)라 비교는 문자열이다.
    🔴 태쏘의 market_cap > 0 조건은 «넣지 않는다» — 시총은 사실상 2024-03-13 부터라
       그 전 구간이 통째로 비어 버린다(§3.2).
    """
    lo = (d - timedelta(days=STATS_WINDOW_DAYS)).isoformat()
    hi = d.isoformat()
    with conn.cursor() as cur:
        cur.execute(_STATS_SQL, (lo, hi, hi))
        return cur.fetchall()


def sector_label(ksic_code, n):
    """앞 n 자리. 길이 < n 이거나 접두가 숫자가 아니면 None(그 taxonomy 에서 미정).

    🔑 3자리 코드의 left(,5) 는 «그 코드 자신»이라 ksic5 에선 미정이 맞다.
       비숫자는 실측 0건이지만 CHECK 위반으로 ③이 죽지 않게 여기서 거른다.
    """
    s = (ksic_code or "").strip()
    if len(s) < n:
        return None
    head = s[:n]
    if not head.isdigit():
        return None
    return head


def rank_and_pct(values):
    """세 통계량 각각의 섹터간 순위·백분위.

    rank = «자기 제외, 통계량이 좋거나 같은(≥) 다른 업종 수»(동률 포함) —
    태쏘 rank_pct 의 side="left" 와 동치다. pct = 100·(G−1−rank)/(G−1) · G<2 면 None.
    """
    import bisect
    srt = sorted(values)
    g = len(values)
    out = []
    for v in values:
        ge = g - bisect.bisect_left(srt, v)     # v 이상인 개수(자기 포함)
        rank = ge - 1
        pct = (100.0 * (g - 1 - rank) / (g - 1)) if g >= 2 else None
        out.append((rank, pct))
    return out


def compute_day_stats(rows, labels):
    """그날 행 + 라벨 → (성적표 행들, 미정 건수).

    미정 3종(no_prev · no_label · short_code)은 «항상» 세어 summary 로 올린다 —
    「0건」에 두 종류가 있다(안 돌았다 / 돌았는데 0).

    ⚠️ 스펙 §6.2 는 「pandas 벡터」라고 적었지만 여기서는 **순수 파이썬**(statistics)을
       쓴다. 하루 대상이 ~2,700행 · 그룹 ~550개라 벡터화 이득이 작고, 손계산 테스트(T6)와
       오라클(T9)이 읽어야 하는 코드라 «읽히는 쪽»을 택했다. 병목은 집계가 아니라 일자별
       20일 창 SQL 이다(1,392일 × ~55k행). **백필 예상 소요 = 수 분 ~ 15분**이며,
       15분을 넘기면 그때 창 SQL 을 한 번에 읽는 방식으로 바꾼다(집계는 그대로 둔다).
       ⚠️ 이 15분은 **측정치가 아니라 추정**이다(실측 근거 없음) — 백필 리포트의
       `elapsed_sec` 가 첫 실측이며, 크게 벗어나면 스펙 §6.2 와 함께 갱신한다.
    """
    import statistics
    undefined = {"no_prev": 0, "no_label": 0, "short_code": {}}
    recs = []
    for code, high, close, prev in rows:
        if prev is None or float(prev) <= 0 or close is None:
            undefined["no_prev"] += 1
            continue
        prev = float(prev)
        r = float(close) / prev - 1.0
        up = (high is not None) and (float(high) >= prev * UP_MULT)
        ks = labels.get(code)
        if w.is_blank(ks):
            undefined["no_label"] += 1
            continue
        recs.append((code, ks, r, up))

    out = []
    for tax, n in TAXONOMIES:
        buckets = {}
        short = 0
        for _code, ks, r, up in recs:
            key = sector_label(ks, n)
            if key is None:
                short += 1
                continue
            buckets.setdefault(key, []).append((r, up))
        undefined["short_code"][tax] = short
        if not buckets:
            continue
        keys = sorted(buckets)
        g = len(keys)
        med = [statistics.median([x[0] for x in buckets[k]]) for k in keys]
        mean = [statistics.mean([x[0] for x in buckets[k]]) for k in keys]
        upc = [sum(1 for x in buckets[k] if x[1]) for k in keys]
        pos = [float(sum(1 for x in buckets[k] if x[0] > 0)) / len(buckets[k]) for k in keys]
        rp_med = rank_and_pct(med)
        rp_up = rank_and_pct([float(u) for u in upc])
        rp_pos = rank_and_pct(pos)
        for i, k in enumerate(keys):
            out.append({
                "taxonomy": tax, "sector_key": k,
                "n_members": len(buckets[k]), "g_sectors": g,
                "ret_median": med[i], "ret_mean": mean[i],
                "up_count": upc[i], "pos_ratio": pos[i],
                "rank_median": rp_med[i][0], "pct_median": rp_med[i][1],
                "rank_up": rp_up[i][0], "pct_up": rp_up[i][1],
                "rank_pos": rp_pos[i][0], "pct_pos": rp_pos[i][1],
            })
    return out, undefined


def compute_stats(conn, d) -> dict:
    """③ 성적표. 그날 일봉 0행이면 스킵(휴장일 정상 · WARNING).

    재계산은 «교체»다(§5-4) — UPSERT 뒤에 이번 키 집합에 없는 옛 행을 지운다.
    반환: date · rows · universe(입력 행수) · G · undefined · stale_deleted.
    스킵 경로(일봉 0행 · 명부 0행)의 반환은 예전 형태 그대로다(universe·stale_deleted 없음).
    """
    rows = load_day_rows(conn, d)
    if not rows:
        logger.warning("[sector] %s 일봉 0행 - 성적표 스킵(휴장일이면 정상)", d)
        return {"date": d.isoformat(), "rows": 0, "skipped": "no_daily",
                "G": {}, "undefined": {}}
    labels = dict((r[0], r[1]) for r in w.map_as_of(conn, d))
    if not labels:
        logger.error("[sector] %s fn_sector_map_as_of 0행 - 성적표 스킵(부트스트랩 전인가)", d)
        return {"date": d.isoformat(), "rows": 0, "skipped": "empty_map",
                "G": {}, "undefined": {}}
    stat_rows, undefined = compute_day_stats(rows, labels)
    for r in stat_rows:
        r["date"] = d
    n = w.upsert_stats(conn, stat_rows)
    g = {}
    keep = {}
    for tax, _ in TAXONOMIES:
        rows_t = [r for r in stat_rows if r["taxonomy"] == tax]
        g[tax] = len(rows_t)
        keep[tax] = set(r["sector_key"] for r in rows_t)

    # 🔴 재계산은 «교체»다(§5-4). UPSERT 만 하면 키 집합이 «줄어든» 재실행에서 옛 행이
    #    유령으로 남고, 그 행의 g_sectors·rank_*·pct_* 는 옛 G 기준이라 그날 표가
    #    내부 불일치가 된다. 단 «계산이 0행이면 아무것도 지우지 않는다» — 일봉 결손 등으로
    #    계산이 빈 날 유효 행을 날리면 안 된다(빈 keep 은 「전부 삭제」를 뜻한다).
    stale = {}
    if stat_rows:
        for tax, _ in TAXONOMIES:
            stale[tax] = w.delete_stale_stats(conn, d, tax, keep[tax])
    else:
        logger.warning("[sector] %s 성적표 계산 0행 - 삭제를 «하지 않는다»(유효 행 보호) "
                       "· 입력 %d행 · 미정=%s", d, len(rows), undefined)

    # 🔴 미정은 «항상» 보이게 한다 — summary 에만 있으면 「유니버스 1/3 이 빠진 날」이
    #    INFO 에 묻힌다. 분모(입력 행수)를 같이 찍어야 921 이 큰지 작은지 알 수 있다.
    short = undefined.get("short_code") or {}
    if undefined.get("no_prev") or undefined.get("no_label") or any(short.values()):
        logger.warning("[sector] %s 미정 - no_prev=%d · no_label=%d · short_code=%s "
                       "/ 입력 %d행", d, undefined.get("no_prev", 0),
                       undefined.get("no_label", 0), dict(short), len(rows))
    if any(stale.values()):
        logger.warning("[sector] %s 유령 행 삭제 %s - 키 집합이 줄어든 재계산이다", d, stale)

    logger.info("[sector] %s 성적표 %d행/%d G=%s 미정=%s 삭제=%s",
                d, n, len(rows), g, undefined, stale)
    return {"date": d.isoformat(), "rows": n, "universe": len(rows), "G": g,
            "undefined": undefined, "stale_deleted": stale}


def _summary_path(d) -> str:
    return os.path.join(SECTOR_DIR, "sector_summary_%s.json" % d.isoformat())


def _write_summary(d, summary: dict) -> None:
    """🔴 §8 의 «전일 대비»·«N일 연속» 게이트는 이 파일들을 읽는다.
    저장이 없으면 그 게이트들은 「한 번도 발동 안 함」이 된다."""
    path = _summary_path(d)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, default=str)
    except OSError as e:
        logger.warning("[sector] summary 파일 기록 실패(비차단): %s", e)


def _read_summary(d):
    try:
        with open(_summary_path(d), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _stale_trading_days(conn, source_asof, trade_date) -> int:
    """source_asof «다음»부터 trade_date 까지의 거래일 수(daily_prices 고유 날짜)."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(DISTINCT date) FROM daily_prices "
                    "WHERE date > %s AND date <= %s",
                    (source_asof.isoformat(), trade_date.isoformat()))
        return int(cur.fetchone()[0])


def update_map(conn, trade_date, source="eod", fetcher=None,
               use_snapshot=False, valid_from=None) -> dict:
    """① 명부 갱신 — 캐시 CSV + 열린 줄 + corp_code + 우선주 규칙 → SCD2 쓰기.

    🔴 보통주 후보의 ksic_code 는 «열린 줄 값 승계»다(캐시엔 코드 열이 없다).
       부트스트랩(use_snapshot=True)에서만 stock_industry 스냅샷으로 시드한다.
    🔴 우선주 후보엔 열린 줄 값을 «승계하지 않는다» — 부모 규칙이 우선이라야
       부모가 바뀔 때 자식도 같이 바뀐다(§3.1).
    🔴 순회는 «캐시 CSV 행»이 아니라 «U_all» 이다. 캐시엔 없는데 U_all 엔 있는 종목이
       실재한다(실측: 상장목록 KOSPI 945 vs 캐시 943 · KOSDAQ 1,827 vs 1,822).
       CSV 행만 돌면 그 종목은 명부 행이 «영영» 안 생기고 stock_industry 스냅샷 KSIC 도
       버려져 부트스트랩 커버리지가 100% 에 못 닿는다 — 무징후 절단이다.
       캐시에 없으면 «아는 키만» 후보에 넣고 CSV 부수 열 키는 «생략»한다
       (plan_map_changes 의 `if f in cand` 가 기존 값을 보존한다 — NULL 로 덮지 않는다).
    """
    open_rows = w.load_open_rows(conn)
    universe = set(load_universe(conn))
    existing = kdc.fold_market_counts(w.open_market_counts(conn))
    desc = kdc.load_desc(trade_date, existing, fetcher=fetcher)
    cmap = load_map(conn)
    snap = w.load_stock_industry(conn) if use_snapshot else {}

    by_code = dict((r["stock_code"], r) for r in desc["rows"])
    cands = {}
    matched = 0                      # CSV ∩ U_all — null_rate 의 «분모»
    no_csv = []                      # U_all 에 있는데 CSV 에 없는 종목(건수로 남긴다)
    for code in sorted(universe):
        row = by_code.get(code)
        if row is None:
            no_csv.append(code)
            cand = {"source_asof": desc["source_asof"]}
        else:
            matched += 1
            cand = {"ksic3_name": row["ksic3_name"], "market": row["market"],
                    "kosdaq_dept": row["kosdaq_dept"], "products": row["products"],
                    "listing_date": row["listing_date"],
                    "settle_month": row["settle_month"],
                    "source_asof": desc["source_asof"]}
        if w.parent_code(code) is None:
            cur = open_rows.get(code) or {}
            ks = cur.get("ksic_code")
            src = cur.get("ksic_source")
            if w.is_blank(ks) and code in snap:
                ks, src = snap[code], "snapshot_20260807"
            cand["ksic_code"] = ks
            cand["ksic_source"] = src
            cand["corp_code"] = cmap.get(code) or cur.get("corp_code")
        if valid_from is not None:
            cand["valid_from"] = valid_from
        cands[code] = cand
    if no_csv:
        logger.warning("[sector] 캐시 CSV 에 없는 U_all 종목 %d개 - 아는 값만 넣고 "
                       "부수 열은 «보존»한다(예: %s)", len(no_csv), no_csv[:5])

    cands = w.apply_parent_rule(cands, universe)
    # §4 summary — null_rate 의 분모는 «U_all 과 매칭된 캐시 행» 이다(no_csv 는 뺀다).
    matched_codes = [c for c in cands if c in by_code]
    null_code = sum(1 for c in matched_codes if w.is_blank(cands[c].get("ksic_code")))
    null_name = sum(1 for c in matched_codes if w.is_blank(cands[c].get("ksic3_name")))

    plan = w.plan_map_changes(open_rows, cands, trade_date)   # 급변 가드가 여기서 터진다
    if plan["counts"]["skipped_past"]:
        logger.warning("[sector] valid_from > %s 인 열린 줄 %d종목 건너뜀(과거 날짜 재실행)",
                       trade_date, plan["counts"]["skipped_past"])
    res = w.write_map(conn, plan, source)

    stale_days = _stale_trading_days(conn, desc["source_asof"], trade_date)
    stale = stale_days > 5
    if stale:
        logger.warning("[sector] 캐시 게시일 %s 가 %s 보다 %d 거래일 낡았다",
                       desc["source_asof"], trade_date, stale_days)
    out = {"source_asof": desc["source_asof"].isoformat(),
           "open_rows": len(open_rows), "matched": matched,
           "changed": plan["counts"]["changed"], "filled": plan["counts"]["filled"],
           "new": plan["counts"]["new"], "skipped_past": plan["counts"]["skipped_past"],
           "null_rate": {
               "ksic_code": (float(null_code) / matched) if matched else None,
               "ksic3_name": (float(null_name) / matched) if matched else None},
           "guard": plan["guard"], "written": True,
           "counts_by_market": desc["counts"], "dropped": desc["dropped"],
           "archive": os.path.basename(desc["archive"]) if desc.get("archive") else None,
           "no_csv": len(no_csv), "universe": len(universe),
           "stale": stale, "stale_days": stale_days, "db": res}
    logger.info("[sector] 명부 갱신 %s", out)
    return out


def collect_sector(trade_date: str = None) -> dict:
    """EOD ①②③④. 🔴 한 단계가 터져도 나머지는 돌고 summary 는 «항상» 쓴다.

    `_safe`(eod_collection) 는 최후 방어선일 뿐이다 — 거기까지 올라가면 summary 가
    안 써져 §8-5·§8-9 가 그날을 못 본다.
    """
    d = date.fromisoformat(_to_iso(trade_date)) if trade_date else now_kst().date()
    summary = {"trade_date": d.isoformat(), "map": {"written": False},
               "corp_code_refreshed": False, "ksic_fill": {}, "stats": {}, "names": {}}
    try:
        # 🔴 키 읽기도 «안»에서 한다 — 밖에 두면 .env 디코딩 오류 하나로 예외가
        #    _safe 까지 올라가 그날 summary 가 통째로 안 써진다(§8-9 가 못 본다).
        key = _load_dart_key()
        with KisDbConnection.get_connection() as conn:
            w.ensure_tables(conn)
            try:
                summary["corp_code_refreshed"] = maybe_refresh_corp_code(conn, key)
            except Exception as e:  # noqa: BLE001 — 매핑 갱신 실패가 나머지를 막지 않는다
                logger.warning("[sector] corp_code 주간 갱신 실패(비차단): %s", e)
            try:
                summary["map"] = update_map(conn, d, source="eod")
            except Exception as e:  # noqa: BLE001
                logger.error("[sector] ① 명부 갱신 실패 - 어제 명부 유지: %s", e)
                partial = dict(getattr(e, "partial", None) or {})
                partial["written"] = False
                partial["error"] = str(e)
                summary["map"] = partial
            fill_out = None
            try:
                fill_out = fill_ksic(conn, d, key=key)
                summary["ksic_fill"] = fill_out
                summary["ksic_fill"]["recopy"] = recopy_preferred(conn, d)["counts"]
            except Exception as e:  # noqa: BLE001
                logger.error("[sector] ② KSIC 채우기 실패: %s", e)
                # 🔴 (c) 재복사가 터진 경우 fill 쪽 집계는 «이미 실측»이다(호출을 썼다).
                #    e.partial 만 보면 그 날의 fill_calls·nodata·cap_hit 이 통째로
                #    사라져 DART ≤300/일 회계와 §8 게이트가 그날을 못 본다.
                #    recopy 는 plan_map_changes 급변 가드로 «실제로» 던질 수 있는 경로다.
                partial = dict(fill_out or getattr(e, "partial", None) or {})
                partial["error"] = str(e)
                summary["ksic_fill"] = partial
            try:
                summary["stats"] = compute_stats(conn, d)
            except Exception as e:  # noqa: BLE001
                logger.error("[sector] ③ 성적표 실패: %s", e)
                summary["stats"] = {"date": d.isoformat(), "rows": 0, "error": str(e)}
            try:
                summary["names"] = w.rebuild_ksic_names(conn)
            except Exception as e:  # noqa: BLE001
                logger.error("[sector] ④ 이름표 실패: %s", e)
                summary["names"] = {"error": str(e)}
    except Exception as e:  # noqa: BLE001 — DB 연결 자체가 실패해도 summary 는 남긴다
        logger.error("[sector] 수집 실패(연결 계층): %s", e)
        summary["error"] = str(e)
    _write_summary(d, summary)
    logger.info("[sector] %s", summary)
    return summary
