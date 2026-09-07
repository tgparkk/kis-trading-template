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
    #    🔴 그 원칙은 «taxonomy 수준»까지다 — 3자리 라벨만 있는 날처럼 한 taxonomy 만
    #    0버킷이면 그 taxonomy 의 keep 이 비고, 빈 keep 은 「그날 그 taxonomy 행 전부
    #    삭제」를 뜻한다. 계산하지 않은 것은 지우지 않는다 → 건너뛰고 None(미측정)+WARNING.
    stale = {}
    if stat_rows:
        for tax, _ in TAXONOMIES:
            if keep[tax]:
                stale[tax] = w.delete_stale_stats(conn, d, tax, keep[tax])
            else:
                stale[tax] = None
                logger.warning("[sector] %s %s taxonomy 계산 0행 - 삭제 건너뜀 · 기존 행 "
                               "보존(계산하지 않은 것은 지우지 않는다)", d, tax)
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
    🔴 write_map «뒤»에 오는 신선도 측정은 자체 try 다. 거기서 터져도 written=True 는
       그대로고 stale 만 None(미측정) + stale_error 로 남는다 — 쓴 것을 안 썼다고
       보고하면 §8 게이트가 통째로 어긋난다.
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

    # 🔴 여기는 w.write_map 이 «이미 커밋한 뒤»다. 신선도 측정이 터졌다고 예외를
    #    밖으로 내보내면 summary 가 map.written=False 로 «거짓 보고»를 하고(§8-5
    #    게이트가 「안 썼다」로 오발), partial 이 source_asof·null_rate·db 를 잃어
    #    나머지 게이트가 «무음으로» 건너뛴다 — 무징후 절단이다.
    # 🔑 실패는 stale=False 가 «아니라» None(미측정)이다. 「모른다」를 「안전」으로
    #    접으면 낡은 캐시를 그대로 통과시킨다.
    stale_error = None
    try:
        stale_days = _stale_trading_days(conn, desc["source_asof"], trade_date)
    except Exception as e:  # noqa: BLE001
        stale_days = None
        stale = None
        stale_error = str(e)
        logger.warning("[sector] 캐시 신선도 측정 실패(비차단) - stale 미측정: %s", e)
    else:
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
           "stale": stale, "stale_days": stale_days, "stale_error": stale_error,
           "db": res}
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


# ───────────────────────── ⑤ reconcile (§8 게이트 1~9) ─────────────────────────
COVERAGE_MIN = 0.98
G_FLOORS = {"ksic2": 40, "ksic3": 100, "ksic5": 200}
NO_PREV_FLOOR = 20


def _undef(summary, key, default=0):
    if not summary:
        return default
    u = ((summary.get("stats") or {}).get("undefined") or {})
    v = u.get(key)
    return default if v is None else v


def evaluate_gates(trade_date, today, prev_summaries, facts) -> dict:
    """§8 게이트 1~9. 순수 함수 — DB 를 만지지 않는다(테스트가 가짜 사실로 굴린다).

    prev_summaries: 직전 «거래일» summary 목록(최신순 · 없는 날은 None).

    🔴 무징후 절단 금지 — 「못 잰」 게이트는 반드시 notes 에 사유를 남긴다.
       키가 없다고 조용히 넘어가면 그 게이트는 「한 번도 발동 안 함」이 되고,
       그건 로그에서 「이상 없음」과 구별되지 않는다.
    """
    import statistics
    fails, warns, notes = [], [], []
    prev1 = prev_summaries[0] if prev_summaries else None
    if prev1 is None and prev_summaries:
        notes.append("직전 거래일 summary 없음 — 전일 대비 게이트(2 G 변동 · 3 no_label · "
                     "6 null_rate)는 판정하지 않았다")
    umkt = facts.get("u_market") or 0
    cov = (float(facts.get("ksic_code_nonnull", 0)) / umkt) if umkt else 0.0
    vmr = (float(facts.get("ksic3_name_nonnull", 0)) / umkt) if umkt else 0.0

    # 1. 커버리지 (U_market 소속 열린 줄만 — U_all 의 상폐 23 은 분자·분모 모두 제외)
    # 🔴 분모 0 은 «결측 키»가 아니라 «퇴화한 DB 사실»(stock_market 이 빈 표)이다.
    #    「모른다」를 「안전」으로 접으면 그 날 커버리지 게이트가 통째로 무음이 된다 — FAIL 이다.
    if not umkt:
        fails.append("gate1 U_market 0 — 커버리지 계산 불가(stock_market 이 비었다)")
    else:
        if cov < COVERAGE_MIN:
            fails.append("gate1 ksic_code 커버리지 %.4f < %.2f" % (cov, COVERAGE_MIN))
        if vmr < COVERAGE_MIN:
            fails.append("gate1 ksic3_name 커버리지 %.4f < %.2f" % (vmr, COVERAGE_MIN))

    # 2. 성적표 존재 · G 하한 · 전일 대비
    g = facts.get("g") or {}
    is_td = facts.get("is_trading_day")
    if is_td:
        if not facts.get("stats_rows"):
            fails.append("gate2 거래일인데 성적표 0행")
        for tax in sorted(G_FLOORS):
            if g.get(tax, 0) < G_FLOORS[tax]:
                fails.append("gate2 %s G=%d < %d (조인 붕괴 신호)"
                             % (tax, g.get(tax, 0), G_FLOORS[tax]))
        pg = ((prev1 or {}).get("stats") or {}).get("G") or {}
        if prev1 is not None and not pg:
            notes.append("gate2 전일 summary 에 stats.G 가 없다(③ 단계 실패?) — "
                         "±20% 변동은 판정하지 않았다")
        for tax in sorted(G_FLOORS):
            if pg.get(tax):
                if not (pg[tax] * 0.8 <= g.get(tax, 0) <= pg[tax] * 1.2):
                    warns.append("gate2 %s G %d 가 전일 %d 대비 ±20%% 밖"
                                 % (tax, g.get(tax, 0), pg[tax]))
    elif is_td is None:
        notes.append("gate2 is_trading_day 사실이 없다 — 성적표 게이트 판정 불가")
    else:
        notes.append("휴장일 — 성적표 게이트 생략")

    # 3. 미정 급증
    no_label = _undef(today, "no_label")
    no_prev = _undef(today, "no_prev")
    for tag, s in (("오늘", today), ("전일", prev1)):
        if s is not None and not ((s.get("stats") or {}).get("undefined")):
            notes.append("gate3 %s summary 에 stats.undefined 가 없다(③ 단계 실패?) — "
                         "미정 건수를 0 으로 뒀다" % tag)
    if prev1 is not None and no_label - _undef(prev1, "no_label") >= 50:
        warns.append("gate3 no_label 이 전일 대비 +%d" % (no_label - _undef(prev1, "no_label")))
    hist = [_undef(s, "no_prev") for s in prev_summaries if s]
    med = statistics.median(hist) if hist else 0
    thr = max(NO_PREV_FLOOR, 3 * med)
    if no_prev > thr:
        warns.append("gate3 no_prev %d > 문턱 %d (일봉 결손 신호 · 중앙값 %s)"
                     % (no_prev, thr, med))

    # 4. 정체 — 「3거래일 연속 동일」은 «오늘 포함» 3일이다(오늘 + 직전 2일).
    new_rows = facts.get("new_rows", 0)
    prev_nr = facts.get("prev_new_rows") or []
    if "new_rows" not in facts:
        notes.append("gate4 new_rows 사실이 없다 — 잔량 정체 판정 불가(0 으로 뒀다)")
    if new_rows > 0 and len(prev_nr) >= 2 and all(p == new_rows for p in prev_nr[:2]):
        warns.append("gate4 정체 — 잔량 %d 가 3거래일 연속 동일(오늘 포함)" % new_rows)
    elif new_rows > 0 and len(prev_nr) < 2:
        notes.append("gate4 직전 recon 행이 %d개뿐 — 3거래일 정체는 판정하지 않았다"
                     % len(prev_nr))
    if today is not None and "recheck_calls" not in ((today.get("ksic_fill") or {})):
        notes.append("gate4 오늘 ksic_fill 에 recheck_calls/recheck_changed 가 없다"
                     "(② 단계 실패?) — 재확인 게이트는 0 으로 뒀다")
    # 🔴 결측 summary 를 0 으로 «접지 않는다» — 접으면 rc_hist 길이가 항상 20 이라
    #    「이력 부족」 note 가 도달 불가가 되고, 이력이 «없는» 날이 「재확인이 멈췄다」로
    #    둔갑한다(「모른다」≠0). 관측 = non-None summary 의 실제 recheck_calls 값뿐이고,
    #    관측이 20 미만이면 판정을 «보류»한다.
    rc_hist = []
    for s in [today] + list(prev_summaries):
        if s is None:
            continue
        rc = (s.get("ksic_fill") or {}).get("recheck_calls")
        if rc is None:
            continue
        rc_hist.append(rc)
        if len(rc_hist) >= 20:
            break
    if len(rc_hist) >= 20 and all(c == 0 for c in rc_hist):
        warns.append("gate4 recheck_calls 가 20거래일 연속 0 — 재확인 순환 정지 의심")
    elif len(rc_hist) < 20:
        notes.append("gate4 재확인 이력 %d/20 — 판정 보류(20거래일 정지는 판정하지 않았다)"
                     % len(rc_hist))
    rchg = ((today or {}).get("ksic_fill") or {}).get("recheck_changed", 0) or 0
    if rchg > 10:
        warns.append("gate4 recheck_changed %d > 10 (레일 아래지만 이례적)" % rchg)

    # 5. 얼어붙은 명부
    def _written(s):
        return bool(((s or {}).get("map") or {}).get("written"))

    if today is not None and not _written(today):
        if prev1 is not None:
            if not _written(prev1):
                fails.append("gate5 map.written=false 가 2거래일 연속")
        else:
            notes.append("gate5 오늘 map.written=false 인데 전일 summary 가 없다 — "
                         "2거래일 연속은 판정하지 않았다")
    mls = facts.get("max_last_seen")
    dl = facts.get("last_seen_deadline")
    if mls is None or dl is None:
        notes.append("gate5 last_seen_at 최댓값(%s)·기준일(%s) 중 하나가 없다 — "
                     "명부 정체 판정 불가" % (mls, dl))
    else:
        mls_d = mls.date() if hasattr(mls, "date") else mls
        if mls_d < dl:
            fails.append("gate5 last_seen_at 최댓값 %s 가 %s 보다 오래됐다" % (mls_d, dl))

    # 6. 소스 이상
    map_today = (today or {}).get("map") or {}
    nr_today = map_today.get("null_rate") or {}
    nr_prev = ((prev1 or {}).get("map") or {}).get("null_rate") or {}
    for f in ("ksic_code", "ksic3_name"):
        v = nr_today.get(f)
        if v is None:
            if today is not None:
                notes.append("gate6 null_rate[%s] 가 없다(매칭 0 또는 ① 단계 실패) — "
                             "판정 불가" % f)
            continue
        p = nr_prev.get(f)
        if v > 0.10 or (p is not None and p > 0 and v > 2 * p):
            warns.append("gate6 null_rate[%s] %.4f (전일 %s)" % (f, v, p))
    # 🔴 map.stale 은 3상태다(Task 8) — True / False / None(«미측정»).
    #    None 을 False 로 접으면 낡은 캐시가 무음으로 통과한다.
    if "stale" not in map_today:
        if today is not None:
            notes.append("gate6 map.stale 키가 없다(① 단계 실패?) — 캐시 신선도 판정 불가")
    elif map_today["stale"] is None:
        warns.append("gate6 stale 미측정 — 신선도 프로브가 실패했다(%s)"
                     % (map_today.get("stale_error") or "사유 미기록"))
    elif map_today["stale"]:
        warns.append("gate6 stale=true — 캐시 게시일이 5거래일 넘게 낡았다")

    # 7. 게시 지연
    iso = trade_date.isoformat()
    delayed = []
    missing_asof = 0
    for s in [today] + list(prev_summaries)[:2]:
        sa = ((s or {}).get("map") or {}).get("source_asof")
        if not sa:
            missing_asof += 1
        delayed.append(bool(sa) and sa < iso)
    if len(delayed) == 3 and all(delayed):
        warns.append("gate7 게시 지연 — source_asof < trade_date 가 3거래일 연속")
    elif len(delayed) < 3:
        notes.append("gate7 최근 %d거래일치뿐 — 3거래일 연속 지연은 판정하지 않았다"
                     % len(delayed))
    elif missing_asof:
        notes.append("gate7 source_asof 가 없는 날이 %d개 — 3거래일 연속 지연 판정 불가"
                     % missing_asof)

    # 8. 명부 중복
    if "duplicates" not in facts:
        notes.append("gate8 duplicates 사실이 없다 — 명부 중복 판정 불가")
    elif facts["duplicates"]:
        fails.append("gate8 명부 중복 %d종목 — 유효기간이 겹친다(n_members 이중 계산)"
                     % facts["duplicates"])

    # 9. summary 부재 / 이력 부족 vs 유실
    if today is None:
        if len(prev_summaries) >= 2 and all(s is None for s in prev_summaries[:2]):
            fails.append("gate9 summary 가 3거래일 연속 없음")
        else:
            warns.append("gate9 오늘 summary 없음")
    # 🔴 「이력 부족」은 «파일이 하나도 없을 때»다 — `not prev_summaries` 로 재면
    #    [None]*20 이 참이 아니라서 사유가 영영 안 찍힌다.
    if not [s for s in prev_summaries if s]:
        notes.append("이력 부족 — 전일 대비 게이트는 판정하지 않았다(첫 EOD 면 정상)")
    # 「유실」은 «그 날짜의» recon 행이 있는데 «그 날짜의» summary 파일이 없을 때만이다
    # (아무 recon 행에나 발동하면 첫날부터 매일 WARN 이 뜬다).
    prev_days = facts.get("prev_days") or []
    recon_dates = set(facts.get("prev_recon_dates") or [])
    lost = [prev_days[i] for i, s in enumerate(prev_summaries)
            if s is None and i < len(prev_days) and prev_days[i] in recon_dates]
    if lost:
        warns.append("gate9 이력 유실 — recon 행은 있는데 summary 파일이 없는 날: %s" % lost[:3])

    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"verdict": verdict, "fails": fails, "warns": warns, "notes": notes,
            "real_rows": facts.get("stats_rows", 0), "new_rows": new_rows,
            "overlap": no_label, "coverage": cov, "value_match_rate": vmr}


_FACTS_COVERAGE_SQL = (
    "SELECT count(*) FILTER (WHERE ksic_code IS NOT NULL),"
    "       count(*) FILTER (WHERE ksic3_name IS NOT NULL),"
    "       count(*) FILTER (WHERE corp_code IS NOT NULL AND ksic_code IS NULL) "
    "FROM stock_sector_map "
    "WHERE valid_to IS NULL AND stock_code IN "
    "      (SELECT stock_code FROM stock_market WHERE " + SQL_STOCK_ONLY + ")")


def _prev_trading_days(conn, d, n) -> list:
    """직전 거래일 n개(최신순 · ISO 문자열). 🔴 daily_prices.date 는 TEXT 라 문자열로 잰다."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date < %s "
                    "ORDER BY date DESC LIMIT %s", (d.isoformat(), n))
        return [r[0] for r in cur.fetchall()]


def _db_facts(conn, d, prev_days) -> dict:
    """게이트가 볼 DB 사실을 «한 번에» 모은다.

    prev_days 는 호출측이 이미 구한 직전 거래일 20개(최신순 ISO)다 — 여기서 다시
    조회하면 같은 쿼리를 두 번 돌린다(경미 13).
    """
    iso = d.isoformat()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_market WHERE " + SQL_STOCK_ONLY)
        u_market = int(cur.fetchone()[0])
        cur.execute(_FACTS_COVERAGE_SQL)
        code_nn, name_nn, remaining = [int(x) for x in cur.fetchone()]
        cur.execute("SELECT count(*) FROM sector_daily_stats WHERE date=%s", (d,))
        stats_rows = int(cur.fetchone()[0])
        cur.execute("SELECT taxonomy, count(*) FROM sector_daily_stats WHERE date=%s "
                    "GROUP BY 1", (d,))
        g = dict((r[0], int(r[1])) for r in cur.fetchall())
        cur.execute("SELECT count(*) FROM (SELECT stock_code FROM fn_sector_map_as_of(%s) "
                    "GROUP BY 1 HAVING count(*) > 1) t", (d,))
        dups = int(cur.fetchone()[0])
        cur.execute("SELECT max(last_seen_at) FROM stock_sector_map WHERE valid_to IS NULL")
        max_ls = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM daily_prices WHERE date=%s", (iso,))
        is_td = int(cur.fetchone()[0]) > 0
        cur.execute("SELECT trade_date, new_rows FROM collection_reconciliation "
                    "WHERE dataset='sector' AND trade_date < %s "
                    "ORDER BY trade_date DESC LIMIT 3", (iso,))
        prev_recon = cur.fetchall()
    return {"u_market": u_market, "ksic_code_nonnull": code_nn,
            "ksic3_name_nonnull": name_nn, "new_rows": remaining,
            "stats_rows": stats_rows, "g": g, "duplicates": dups,
            "max_last_seen": max_ls, "is_trading_day": is_td,
            "last_seen_deadline": (date.fromisoformat(prev_days[2])
                                   if len(prev_days) >= 3 else None),
            "prev_days": list(prev_days),
            "prev_new_rows": [int(r[1] or 0) for r in prev_recon],
            "prev_recon_dates": [r[0] for r in prev_recon]}


def reconcile_sector(trade_date: str = None) -> dict:
    """§8 건강 판정. 결과는 collection_reconciliation(dataset='sector')에 남긴다."""
    d = date.fromisoformat(_to_iso(trade_date)) if trade_date else now_kst().date()
    iso = d.isoformat()
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        prev_days = _prev_trading_days(conn, d, 20)      # 한 번만 조회한다
        facts = _db_facts(conn, d, prev_days)
    today = _read_summary(d)
    prev_summaries = [_read_summary(date.fromisoformat(x)) for x in prev_days]
    out = evaluate_gates(d, today, prev_summaries, facts)
    with KisDbConnection.get_connection() as conn:
        w.upsert_reconciliation(conn, iso, out["real_rows"], out["new_rows"],
                                out["overlap"], out["coverage"], out["value_match_rate"],
                                out["verdict"])
    log = logger.error if out["verdict"] == "FAIL" else (
        logger.warning if out["verdict"] == "WARN" else logger.info)
    log("[sector] reconcile %s = %s · fails=%s · warns=%s · notes=%s",
        iso, out["verdict"], out["fails"], out["warns"], out["notes"])
    out["trade_date"] = iso
    return out


# ─────────────────── ⑥ 수동 CLI (§5-4 · §6.0 · §6.2 · T14) ───────────────────
def _guard_window(force=False, now=None) -> None:
    """§5-5 — 평일 15:30~17:00 은 EOD 와 겹치므로 수동 CLI 를 거부한다(--force 로만 통과).

    🔑 재무 백필이 EOD 와 겹치면 같은 opendart 호스트를 두 프로세스가 두드린다.
    """
    if force:
        return
    t = now or now_kst()
    if t.weekday() < 5 and (15, 30) <= (t.hour, t.minute) < (17, 0):
        raise RuntimeError(
            "평일 15:30~17:00 에는 실행할 수 없다(EOD 충돌). 야간/주말에 돌리거나 --force 를 쓸 것. "
            "현재 %s" % t)


def _trading_days_between(conn, d_from, d_to) -> list:
    """구간의 거래일(daily_prices 고유 날짜) — ISO 문자열 오름차순."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s "
                    "ORDER BY date", (d_from.isoformat(), d_to.isoformat()))
        return [r[0] for r in cur.fetchall()]


def _gz_fetcher():
    """보관 gz(`scratchpad/sector/krx_desc_*.csv.gz`)를 캐시 CSV 응답처럼 돌려준다.

    🔑 fetch_desc_csv 의 «7일 후퇴»가 그대로 동작하므로 그날 보관본이 없으면
       가장 가까운 이전 보관본을 쓴다(원래 수집이 그랬던 것과 같은 규칙).
    """
    import gzip as _gzip

    def _fn(url):
        key = url.rsplit("/", 1)[-1].replace(".csv", "")
        path = os.path.join(kdc.ARCHIVE_DIR, "krx_desc_%s.csv.gz" % key)
        if os.path.exists(path):
            with _gzip.open(path, "rb") as fh:
                return 200, fh.read()
        return 404, b""

    return _fn


def _report(name, lines) -> str:
    """리포트 파일 — 실행 근거를 파일로 남긴다(스펙 §6.0-5 · §6.2)."""
    os.makedirs(SECTOR_DIR, exist_ok=True)
    stamp = now_kst().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SECTOR_DIR, "%s_%s.txt" % (name, stamp))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(str(x) for x in lines) + "\n")
    logger.info("[sector] 리포트: %s", path)
    return path


def _live_three_table_counts(conn) -> dict:
    """라이브 3표 전후 대조 — 이 작업은 «읽기»만 한다는 증거."""
    out = {}
    with conn.cursor() as cur:
        for t in ("daily_prices", "minute_candles", "virtual_trading_records"):
            cur.execute("SELECT count(*) FROM " + t)
            out[t] = int(cur.fetchone()[0])
    return out


def backfill(d_from, d_to, dry_run=False, force=False) -> dict:
    """§6.2 — 거래일 순회 성적표 재계산. 라이브 3표는 «읽기»만 한다.

    첫날(2021-01-04)은 20일 창 안에 직전 봉이 없어 성적표가 비므로 결과는 거래일 − 1 이다.
    """
    _guard_window(force)
    t0 = now_kst()
    rows = 0
    days_with_rows = 0
    g_hist = {}
    undef_hist = []
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        before = _live_three_table_counts(conn)
        days = _trading_days_between(conn, d_from, d_to)
        logger.info("[sector] 백필 %s ~ %s · 거래일 %d일 (dry_run=%s)",
                    d_from, d_to, len(days), dry_run)
        if not dry_run:
            for i, iso in enumerate(days, 1):
                res = compute_stats(conn, date.fromisoformat(iso))
                rows += res.get("rows", 0)
                if res.get("rows"):
                    days_with_rows += 1
                for tax, n in (res.get("G") or {}).items():
                    g_hist.setdefault(tax, []).append(n)
                undef_hist.append(res.get("undefined") or {})
                if i % 100 == 0:
                    logger.info("[sector] 백필 %d/%d rows=%d", i, len(days), rows)
        after = _live_three_table_counts(conn)
    out = {"from": str(d_from), "to": str(d_to), "days": len(days), "rows": rows,
           "days_with_rows": days_with_rows, "dry_run": dry_run,
           "live_before": before, "live_after": after,
           "elapsed_sec": (now_kst() - t0).total_seconds()}
    out["report"] = _report("backfill_report", [
        "섹터 성적표 백필 리포트", str(out), "",
        "일자별 G 분포: " + str(dict((k, {"min": min(v), "max": max(v),
                                          "median": sorted(v)[len(v) // 2]})
                                     for k, v in g_hist.items())),
        "미정 종목 수 분포(마지막 5일): " + str(undef_hist[-5:]),
        "",
        "🔴 2021-01-04 ~ 구축일 구간의 업종 라벨은 «현재 스냅샷의 소급»이다(§5-2).",
        "🔴 2024-03-12 이전 성적표는 태쏘 SEC-M1 과 «대조되지 않았다» — 시총이 사실상",
        "   2024-03-13 부터라 태쏘 유니버스가 거의 비기 때문이다(§3.2).",
        "라이브 3표 전/후: %s / %s" % (before, after),
    ])
    if before != after:
        raise RuntimeError("🔴 라이브 3표 행수가 바뀌었다 — 즉시 보고: %s → %s" % (before, after))
    return out


def regen_stats(d_from, d_to, taxonomy=None, dry_run=False, force=False) -> dict:
    """§5-4 ③ — 성적표만 재계산(명부는 안 건드린다). taxonomy 지정 시 그것만 지우고 다시 쓴다.

    🔴 리포트는 «어느 분기에서도» 쓴다. 실경로는 구간을 «먼저 통째로 지운 뒤» 하루씩
       되살리므로, 중간에 죽으면 「무엇을 지웠고 어디까지 되살렸나」가 파일로 남지 않으면
       복구 근거가 사라진다 — 덜 지우는 delete_stats_cli 조차 리포트를 남긴다.
       그래서 실패 경로도 리포트를 «먼저» 쓰고 재전파한다(다른 op 와 같은 패턴).
    """
    _guard_window(force)
    t0 = now_kst()
    deleted = 0
    rows = 0
    days_with_rows = 0
    done = 0
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        days = _trading_days_between(conn, d_from, d_to)
        if dry_run:
            # 🔑 안 쟀으니 None 이다 — 「모른다」를 0 으로 접으면 「지울 게 없다」로 읽힌다.
            out = {"from": str(d_from), "to": str(d_to), "days": len(days),
                   "taxonomy": taxonomy, "dry_run": True,
                   "would_delete_taxonomy": taxonomy,
                   "deleted": None, "rows": None, "days_with_rows": None,
                   "elapsed_sec": (now_kst() - t0).total_seconds()}
            out["report"] = _report("regen_stats_report", [
                "성적표 재계산 dry-run (쓰기 0 · 삭제 0)", str(out), "",
                "구간: %s ~ %s · 거래일 %d일 · taxonomy=%s" % (d_from, d_to, len(days),
                                                              taxonomy),
                "deleted·rows·days_with_rows 는 dry-run 이라 «재지 않았다»(None).",
            ])
            return out
        failed_on = None
        try:
            deleted = w.delete_stats(conn, d_from, d_to, taxonomy)
            for iso in days:
                failed_on = iso
                n = compute_stats(conn, date.fromisoformat(iso)).get("rows", 0)
                rows += n
                if n:
                    days_with_rows += 1
                done += 1
                failed_on = None
        except Exception as e:  # noqa: BLE001 — 지운 뒤 죽으면 근거 없이 구멍만 남는다
            path = _report("regen_stats_report", [
                "🔴 성적표 재계산 «중간 실패» — 구간을 지운 «뒤» 되살리다 멈췄다",
                "구간: %s ~ %s · taxonomy=%s" % (d_from, d_to, taxonomy),
                "삭제한 행: %d" % deleted,
                "되살린 날: %d/%d · rows=%d · days_with_rows=%d" % (done, len(days), rows,
                                                                   days_with_rows),
                "실패한 날: %s" % failed_on,
                "오류: %s" % e,
                "elapsed_sec: %.1f" % (now_kst() - t0).total_seconds(),
                "",
                "🔴 남은 %d일은 성적표가 «없는» 상태다 — 같은 구간으로 다시 돌릴 것."
                % (len(days) - done),
            ])
            logger.error("[sector] 성적표 재계산 중간 실패 - %d/%d일 되살린 뒤 %s 에서 멈췄다"
                         "(삭제 %d행) · 리포트 %s: %s",
                         done, len(days), failed_on, deleted, path, e)
            raise
    out = {"from": str(d_from), "to": str(d_to), "days": len(days),
           "taxonomy": taxonomy, "deleted": deleted, "rows": rows,
           "days_with_rows": days_with_rows, "dry_run": False,
           "elapsed_sec": (now_kst() - t0).total_seconds()}
    out["report"] = _report("regen_stats_report", [
        "성적표 재계산", str(out), "",
        "삭제 %d행 → 재계산 %d행 (거래일 %d일 · days_with_rows %d일 · taxonomy=%s)"
        % (deleted, rows, len(days), days_with_rows, taxonomy),
        "🔴 성적표만 바꿨다 — 명부(stock_sector_map)는 손대지 않았다.",
    ])
    return out


def delete_stats_cli(d_from, d_to, taxonomy=None, dry_run=False, force=False) -> dict:
    """§6.2 데이터 롤백 — 건수를 리포트에 남기고 실행(승인 필수)."""
    _guard_window(force)
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        if dry_run:
            with conn.cursor() as cur:
                sql = "SELECT count(*) FROM sector_daily_stats WHERE date BETWEEN %s AND %s"
                params = [d_from, d_to]
                if taxonomy:
                    sql += " AND taxonomy=%s"
                    params.append(taxonomy)
                cur.execute(sql, params)
                n = int(cur.fetchone()[0])
            out = {"would_delete": n, "dry_run": True}
        else:
            out = {"deleted": w.delete_stats(conn, d_from, d_to, taxonomy), "dry_run": False}
    out["report"] = _report("delete_stats_report",
                            ["성적표 삭제", str(d_from), str(d_to), str(taxonomy), str(out)])
    return out


def bootstrap(trade_date, dry_run=False, force=False) -> dict:
    """§6.0 — 1회 · 머지 «전» 워크트리에서 · 야간/주말 · 사장님 승인 후.

    순서: 1)corp_code 2)명부(valid_from=2021-01-04) 3)DART 채우기 3b)우선주 재복사
          4)이름표 5)리포트 6)게이트(둘 다 ≥ 98%)
    ⚠️ --dry-run 은 «DB 쓰기 0 · DART 호출 0 · gz 0» 이다 — 대상 건수와 함께
       게이트가 볼 두 커버리지의 «예측치»(2단계 후 · 3b 후)를 인쇄한다.
    """
    _guard_window(force)
    d = date.fromisoformat(_to_iso(trade_date)) if isinstance(trade_date, str) else trade_date
    key = _load_dart_key()
    steps = {}
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        before = _live_three_table_counts(conn)
        umkt = set(load_u_market(conn))
        if dry_run:
            # 🔴 gz 도 쓰지 않는다(archive=False) — dry-run 이 파일을 남기면 「쓰기 0」이
            #    거짓이 되고 §5-4 재생성 원료에 «실제로는 안 쓴 날»이 섞인다.
            open_rows = w.load_open_rows(conn)
            desc = kdc.load_desc(d, kdc.fold_market_counts(w.open_market_counts(conn)),
                                 archive=False)
            snap = w.load_stock_industry(conn)
            cmap = load_map(conn)
            universe = set(load_universe(conn))
            by_code = dict((r["stock_code"], r) for r in desc["rows"])
            matched = [c for c in universe if c in by_code]
            would_dart = [c for c in sorted(universe)
                          if w.parent_code(c) is None and c not in snap and c in cmap]
            # 게이트가 볼 두 커버리지를 «예측»한다 — 안 내면 dry-run 이 98% 판정을 못 돕는다.
            pred_code, pred_name = set(), set()
            for c in universe:
                if w.parent_code(c) is None:
                    if c in snap or c in cmap:      # 스냅샷 시드 또는 DART 로 채워질 것
                        pred_code.add(c)
                    if by_code.get(c, {}).get("ksic3_name"):
                        pred_name.add(c)
            for c in universe:                       # 3b 우선주 재복사 예측
                p = w.parent_code(c)
                if p is None or p not in universe:
                    continue
                if p in pred_code:
                    pred_code.add(c)
                if p in pred_name:
                    pred_name.add(c)
            n = len(umkt) or 1
            # 2단계 «후»(= DART 채우기 전) 예측에서는 would_dart 로 채워질 종목뿐 아니라
            # 그 부모를 복사받는 «우선주 자식»도 빼야 한다(실제 사례 0220WL → 0220W0).
            not_yet = set(would_dart)
            for c in universe:
                p = w.parent_code(c)
                if p is not None and p in not_yet:
                    not_yet.add(c)
            steps = {"matched": len(matched),
                     "snapshot_hits": len([c for c in matched if c in snap]),
                     "would_dart_calls": len(would_dart), "open_rows": len(open_rows),
                     "predicted_coverage_after_2": {
                         "ksic_code": float(len((pred_code - not_yet) & umkt)) / n,
                         "ksic3_name": float(len(pred_name & umkt)) / n},
                     "predicted_coverage_after_3b": {
                         "ksic_code": float(len(pred_code & umkt)) / n,
                         "ksic3_name": float(len(pred_name & umkt)) / n},
                     "u_market": len(umkt)}
            after = _live_three_table_counts(conn)
            out = {"dry_run": True, "steps": steps, "live_before": before, "live_after": after}
            out["report"] = _report("bootstrap_report_dryrun", [
                "부트스트랩 dry-run (쓰기 0 · DART 0 · gz 0)", str(out), "",
                "⚠️ 예측치다 — DART 가 125건 전부 induty_code 를 준다는 가정에서 나온 값이고,",
                "   그 가정은 08-07 실행(다른 집합)에서 왔다. 본 실행 리포트가 실측으로 대체한다.",
                "⚠️ 예측은 «과대»일 수 있다 — 무자료(013) 응답·형식 이상 코드는 반영하지 않는다.",
            ])
            return out

        # 🔴 단계 1~4 는 «단계마다 커밋»된다. 중간에 죽으면 ①corp_code·②명부는 이미
        #    반영된 뒤이므로, 근거 없이 예외만 올리면 「어디까지 반영됐고 무엇이 남았나」를
        #    잃는다 → regen_stats 와 같은 「리포트 뒤 raise」.
        failed_on = None
        try:
            # 1) corp_code
            failed_on = "1) corp_code(maybe_refresh_corp_code)"
            steps["corp_code"] = maybe_refresh_corp_code(conn, key, days=0)
            # 2) 명부 (소급 · valid_from = 2021-01-04)
            failed_on = "2) 명부(update_map)"
            steps["map"] = update_map(conn, d, source="bootstrap_snapshot",
                                      use_snapshot=True, valid_from=BOOTSTRAP_VALID_FROM)
            failed_on = "2) 커버리지 측정(_coverage · 2단계 후)"
            steps["coverage_after_2"] = _coverage(conn, umkt)
            # 3) DART 채우기 (예상 125 < 상한 300)
            failed_on = "3) DART 채우기(fill_ksic)"
            steps["ksic_fill"] = fill_ksic(conn, d, cap=DART_DAILY_CAP, recheck_max=0, key=key)
            # 3b) 우선주 재복사 — 3 에서 부모(0220W0 등)가 채워진 자식을 받는다
            failed_on = "3b) 우선주 재복사(recopy_preferred)"
            steps["recopy"] = recopy_preferred(conn, d, source="bootstrap_snapshot")["counts"]
            failed_on = "3b) 커버리지 측정(_coverage · 3b 후)"
            steps["coverage_after_3b"] = _coverage(conn, umkt)
            # 4) 이름표
            failed_on = "4) 이름표(rebuild_ksic_names)"
            steps["names"] = w.rebuild_ksic_names(conn)
            failed_on = "4) 미라벨 목록(_unlabeled_list)"
            unlabeled = _unlabeled_list(conn, umkt)
            failed_on = "4) 라이브 3표 after(_live_three_table_counts)"
            after = _live_three_table_counts(conn)
            failed_on = None
        except Exception as e:  # noqa: BLE001 — 앞 단계는 이미 커밋됐다. 근거를 «먼저» 남긴다
            path = _report("bootstrap_report", [
                "🔴 섹터 명부 부트스트랩 «중간 실패» — 앞 단계는 이미 커밋된 뒤다",
                "기준일: %s" % d,
                "U_market: %d" % len(umkt),
                "완료한 단계: %s" % sorted(steps),
                "2단계 후 커버리지: %s" % steps.get("coverage_after_2"),
                "3b 후 커버리지: %s" % steps.get("coverage_after_3b"),
                "DART 응답: %s" % (steps.get("ksic_fill") or {}).get("status_counts"),
                "라이브 3표 전(before): %s" % before,
                "  · 후(after)는 «재지 못했다»(None) — 실패 지점에서 멈췄다.",
                "실패한 단계: %s" % failed_on,
                "오류: %s" % e,
                "",
                "🔴 명부·DART 채우기는 «부분 반영»일 수 있다 — 같은 기준일로 다시 돌릴 것.",
                "🔴 라이브 3표 after 를 못 쟀으므로 「불변」을 «주장하지 말 것» — 수동 대조 필요.",
            ])
            logger.error("[sector] 부트스트랩 중간 실패 - 단계 %s 에서 멈췄다(완료 %s) "
                         "· 리포트 %s: %s", failed_on, sorted(steps), path, e)
            raise

    cov = steps["coverage_after_3b"]
    out = {"dry_run": False, "steps": steps, "unlabeled": unlabeled,
           "live_before": before, "live_after": after}
    out["report"] = _report("bootstrap_report", [
        "섹터 명부 부트스트랩 리포트", "기준일: %s" % d, "",
        "U_market: %d" % len(umkt),
        "2단계 후 커버리지: %s" % steps["coverage_after_2"],
        "3b 후 커버리지: %s" % cov,
        "DART 응답: %s" % steps["ksic_fill"].get("status_counts"),
        "  · nodata(업종 없음): %s" % steps["ksic_fill"].get("nodata"),
        "  · 채운 종목: %s" % steps["ksic_fill"].get("filled"),
        "이름표 코드 수: %s · 점유율<0.8: %s" % (steps["names"].get("codes"),
                                                steps["names"].get("low_share")),
        "미라벨 종목 목록(%d): %s" % (len(unlabeled), unlabeled),
        "라이브 3표 전/후: %s / %s" % (before, after),
        "",
        "🔴 이 구간(2021-01-04 ~ 구축일)의 업종 라벨은 «현재 스냅샷의 소급»이다(§5-2).",
    ])
    if before != after:
        raise RuntimeError("🔴 라이브 3표 행수가 바뀌었다 — 즉시 보고: %s → %s" % (before, after))
    if cov["ksic_code"] < COVERAGE_MIN or cov["ksic3_name"] < COVERAGE_MIN:
        raise RuntimeError(
            "🔴 부트스트랩 게이트 미달 — 백필을 진행하지 말고 사장님께 보고할 것: %s" % cov)
    return out


def _coverage(conn, umkt) -> dict:
    with conn.cursor() as cur:
        cur.execute(_FACTS_COVERAGE_SQL)
        code_nn, name_nn, _rem = [int(x) for x in cur.fetchone()]
    n = len(umkt) or 1
    return {"ksic_code": float(code_nn) / n, "ksic3_name": float(name_nn) / n,
            "u_market": len(umkt)}


def _unlabeled_list(conn, umkt) -> list:
    """미라벨 = ①열린 줄은 있는데 코드/이름이 비었다 ②**열린 줄이 아예 없다**.

    🔴 ②를 빼면 「명부에 안 들어온 종목」이 목록에도 커버리지에도 안 보인다 —
       못 본 것을 없는 것으로 읽는 바로 그 형태다.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code FROM stock_sector_map WHERE valid_to IS NULL "
                    "AND (ksic_code IS NULL OR ksic3_name IS NULL)")
        partial = set(r[0] for r in cur.fetchall())
        cur.execute("SELECT stock_code FROM stock_sector_map WHERE valid_to IS NULL")
        have_row = set(r[0] for r in cur.fetchall())
    missing_row = set(umkt) - have_row
    if missing_row:
        logger.warning("[sector] 명부에 열린 줄이 «아예 없는» U_market 종목 %d개: %s",
                       len(missing_row), sorted(missing_row)[:10])
    return sorted((partial & set(umkt)) | missing_row)


def regen_map(d_from, dry_run=False, force=False) -> dict:
    """§5-4 ② — 그 날짜 «이후»의 SCD2 를 보관 gz + dart_company_*.jsonl 로 재생성한다.

    🔴 손 수정(SQL 직접 UPDATE/DELETE) 금지의 대체 경로다.
    🔴 하한 = 첫 EOD 날짜. 부트스트랩 행(valid_from=2021-01-04)은 재생성 대상이 아니다.
    🔴 캐시 CSV 엔 코드 열이 없으므로 ksic_code·ksic_source·ksic_checked_at 은 jsonl
       보관분으로만 재생성하고, 보관분이 없는 구간은 «보존»한다.
    🔴 DB 쓰기는 전부 sector_writer 를 거친다(reset_map_from·snapshot_map·restore_map).
    🔴 일자별 재구축은 단계마다 커밋된다 — 중간에 터지면 명부가 «잘린 채» 남는다.
       그래서 시작 전에 표 전체를 스냅샷 뜨고, 어디서든 터지면 통째로 되돌린다.

    ⚠️ **재생은 원본 실행과 완전히 같지 않다 — 두 가지가 다르다.**
    ① 원래 5% 급변 가드에 걸렸던 날을 재생하면 그 날 `update_map` 이 다시 RuntimeError 를
       내고 **재생 전체가 롤백**된다. 이건 의도다 — 「그날 왜 걸렸나」를 먼저 조사해야지
       재생이 조용히 통과시키면 안 된다. 조사 후 `--from` 을 그 다음 날로 올려 다시 돈다.
    ② 원래 `written=false` 였던 날(캐시 404 등)도 재생에서는 «7일 후퇴 gz»를 찾아
       **쓴다**. 즉 그날 명부가 원본보다 «더 채워진» 상태가 될 수 있다.
       리포트에 그 날짜 수를 남기고, 소급 라벨이 늘어난다는 점을 판정문에 인쇄한다.
    """
    _guard_window(force)
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT min(valid_from) FROM stock_sector_map WHERE source='eod'")
            first_eod = cur.fetchone()[0]
        if first_eod is None:
            raise RuntimeError("EOD 로 생긴 줄이 없다 — 재생성할 구간이 없다")
        if d_from < first_eod:
            raise RuntimeError("--from 은 첫 EOD 날짜(%s) 이상이어야 한다(부트스트랩 행은 "
                               "gz 가 아니라 stock_industry + 부트스트랩 날 gz 로 재현한다)"
                               % first_eod)
        days = [x for x in _trading_days_between(conn, d_from, now_kst().date())]
        jsonl_days = [x for x in days
                      if os.path.exists(os.path.join(SECTOR_DIR, "dart_company_%s.jsonl" % x))]
        if dry_run:
            return {"from": str(d_from), "days": len(days), "jsonl_days": len(jsonl_days),
                    "dry_run": True}

        snap_rows = w.snapshot_map(conn)
        logger.warning("[sector] 명부 스냅샷 %d행 — 실패하면 이걸로 되돌린다", snap_rows)
        try:
            reset = w.reset_map_from(conn, d_from)
            fetcher = _gz_fetcher()
            replayed = 0
            wrote_new = []            # 원본이 못 쓴 날인데 재생이 «쓴» 날
            for iso in days:
                day = date.fromisoformat(iso)
                res = update_map(conn, day, source="eod", fetcher=fetcher) or {}
                # 🔴 재생은 «7일 후퇴 gz» 를 찾으므로 원본이 캐시 404 로 못 썼던 날도
                #    쓴다 — 그 날 명부는 원본보다 «더 채워진» 상태가 된다(docstring ②).
                #    집계해서 내지 않으면 소급 라벨이 «조용히» 늘어난다 — 무징후 절단이다.
                #    🔑 summary 가 아예 없는 날(None)도 「원본이 썼다」로 접지 않는다.
                if res.get("written"):
                    prev = _read_summary(day) or {}
                    if not (prev.get("map") or {}).get("written"):
                        wrote_new.append(iso)
                path = os.path.join(SECTOR_DIR, "dart_company_%s.jsonl" % iso)
                if os.path.exists(path):
                    open_rows = w.load_open_rows(conn)
                    resp = []
                    with open(path, encoding="utf-8") as fh:
                        for line in fh:
                            rec = json.loads(line)
                            payload = rec.get("payload") or {}
                            induty = (payload.get("induty_code") or "").strip()
                            # 🔴 열린 줄이 없는 종목은 «건너뛴다» — 재생시 새 행을 만들면
                            #    부수 열이 전부 NULL 인 유령 행이 생긴다(M3).
                            if rec["stock_code"] not in open_rows:
                                continue
                            resp.append({"stock_code": rec["stock_code"],
                                         "ksic_code": induty or None, "recheck": False})
                    if resp:
                        w.apply_ksic_updates(conn, resp, day, create_missing=False)
                        replayed += len(resp)
                recopy_preferred(conn, day)
            w.rebuild_ksic_names(conn)
        except Exception as e:  # noqa: BLE001 — 중간 실패는 «잘린 명부»를 남긴다
            # 🔴 rollback 을 «먼저» — 실패한 문장이 트랜잭션을 abort 상태로 두면
            #    restore 의 DELETE 가 InFailedSqlTransaction 으로 즉시 죽는다.
            conn.rollback()
            restored = w.restore_map(conn)
            logger.error("[sector] 재생성 실패(%s) - 스냅샷 %d행으로 되돌렸다", e, restored)
            raise
        w.drop_map_snapshot(conn)
    # 🔴 보관 jsonl 이 없어 KSIC 계열(ksic_code·source·checked_at)을 «보존»한 날.
    #    문자열화된 dict 안에만 두면 「재생했다」와 구별되지 않는다.
    preserved_ksic_days = len(days) - len(jsonl_days)
    if wrote_new:
        logger.warning("[sector] 재생이 «원본이 못 쓴» 날 %d일을 새로 썼다 - 그 날의 소급 "
                       "라벨이 원본보다 늘어난다: %s", len(wrote_new), wrote_new[:10])
    if preserved_ksic_days:
        logger.warning("[sector] 보관 jsonl 이 없어 KSIC 계열을 «보존»한 날 %d일 - 그 구간의 "
                       "ksic_code/source/checked_at 은 재생 전 값 그대로다", preserved_ksic_days)
    out = {"from": str(d_from), "days": len(days), "jsonl_days": len(jsonl_days),
           "deleted": reset["deleted"], "reopened": reset["reopened"],
           "replayed_responses": replayed, "snapshot_rows": snap_rows, "dry_run": False,
           "regen_wrote_where_original_didnt": len(wrote_new),
           "regen_wrote_where_original_didnt_dates": wrote_new,
           "preserved_ksic_days": preserved_ksic_days}
    out["report"] = _report("regen_map_report", [
        "명부 재생성", str(out), "",
        "삭제(valid_from >= %s): %d행" % (d_from, reset["deleted"]),
        "다시 연 줄(valid_to >= %s): %d행" % (d_from - timedelta(days=1), reset["reopened"]),
        "jsonl 재생 응답: %d건 (보관분 없는 날의 KSIC 계열은 «보존»)" % replayed,
        "KSIC 계열을 «보존»한 날: %d일 (전체 %d일 − jsonl 보관 %d일)"
        % (preserved_ksic_days, len(days), len(jsonl_days)),
        "",
        "🔴 원본이 못 쓴 날인데 재생이 쓴 날: %d일 — 그 날은 명부가 "
        "원본보다 «더 채워졌다»(소급 라벨 증가)." % len(wrote_new),
        "   날짜: %s" % wrote_new,
    ])
    return out


_CLI_OPS = ("bootstrap", "backfill", "regen", "regen_map", "delete_stats")


def _check_cli_flags(args, error):
    """고른 작업 이름(없으면 None)을 돌려준다. 조용히 삼켜지는 조합은 error() 로 거부한다.

    🔴 --dry-run/--force 를 작업 플래그 없이 주면 마지막 else 가지(collect_sector =
       진짜 EOD 수집)로 떨어져 두 플래그가 «무시된 채» 실제 수집이 돌아간다 —
       「안 쓴다」·「가드를 넘긴다」고 믿고 부른 명령이 SCD2 를 쓰는 형태다.
    🔴 op 두 개를 같이 주면 elif 사슬이 앞의 하나만 돌고 나머지는 «조용히» 버려진다.
    """
    chosen = [n for n in _CLI_OPS if getattr(args, n, False)]
    if len(chosen) > 1:
        error("작업 플래그는 하나만 쓴다 — 동시에 주면 앞의 하나만 돌고 나머지는 "
              "조용히 버려진다: %s"
              % ", ".join("--" + n.replace("_", "-") for n in chosen))
    if not chosen:
        for flag in ("dry_run", "force"):
            if getattr(args, flag, False):
                error("--%s 플래그는 수동 작업(--bootstrap/--backfill/--regen/--regen-map/"
                      "--delete-stats)에만 쓴다 — EOD 판(기본)과 --reconcile-only 는 "
                      "그 플래그를 무시한다" % flag.replace("_", "-"))
    return chosen[0] if chosen else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--from", dest="d_from", default=None)
    ap.add_argument("--to", dest="d_to", default=None)
    ap.add_argument("--taxonomy", default=None, choices=["ksic2", "ksic3", "ksic5"])
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--regen-map", dest="regen_map", action="store_true")
    ap.add_argument("--delete-stats", dest="delete_stats", action="store_true")
    ap.add_argument("--reconcile-only", dest="reconcile_only", default=None)
    ap.add_argument("--dry-run", dest="dry_run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    _check_cli_flags(args, ap.error)

    def _need(v, name):
        if not v:
            ap.error("%s 가 필요하다" % name)
        return date.fromisoformat(_to_iso(v))

    if args.bootstrap:
        print(bootstrap(_need(args.date, "--date"), args.dry_run, args.force))
    elif args.backfill:
        print(backfill(_need(args.d_from, "--from"), _need(args.d_to, "--to"),
                       args.dry_run, args.force))
    elif args.regen:
        print(regen_stats(_need(args.d_from, "--from"), _need(args.d_to, "--to"),
                          args.taxonomy, args.dry_run, args.force))
    elif args.regen_map:
        print(regen_map(_need(args.d_from, "--from"), args.dry_run, args.force))
    elif args.delete_stats:
        print(delete_stats_cli(_need(args.d_from, "--from"), _need(args.d_to, "--to"),
                               args.taxonomy, args.dry_run, args.force))
    elif args.reconcile_only:
        print(reconcile_sector(args.reconcile_only))
    else:
        print(collect_sector(args.date))
