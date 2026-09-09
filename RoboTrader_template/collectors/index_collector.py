"""지수 일봉 수집 — KIS 업종 일봉(기본) / FDR KS11·KQ11(폴백) → index_daily.

usage:
  python -m collectors.index_collector
  python -m collectors.index_collector --start 2026-06-01

2026-08-17: `reconcile_index` 제거. 「새 DB index_daily vs 레거시
  robotrader_quant.daily_prices(KS11/KQ11)」 당일 대조였는데, 레거시는 2026-07-10
  동결이라 이미 휴면이었고 `KIS_DATA_SOURCE=legacy` 게이트 폐지 + `robotrader` DB
  삭제로 도달 불가가 됐다. (`collection_reconciliation` 표는 과거 이력이므로 유지.)

2026-09-10: 소스를 KIS 로 옮기고 «신선도 판정»을 붙였다(설계 §3·§4).
  09-08~09 에 FDR 이 죽었는데 «옛 6봉»을 정상 반환해 index_daily 가 09-07 에서
  2거래일 멈췄고 로그·EOD 요약은 전부 정상이었다 — fail-silent.
  🔑 「N행 갱신」은 「오늘 것이 들어왔다」의 증거가 아니다. 그래서 판정은 «행 수»가
     아니라 «날짜»(축 A 상대 · 축 B 절대)로 하고, 그 구분을 reconcile 행의
     real_rows / new_rows 두 칸으로 남긴다.
  🔴 폴백은 KIS 가 «장애»일 때만이다. KIS 의 «빈 결과»로 폴백하면 상류가 죽은 FDR 이
     옛 봉을 정상처럼 돌려줘 지금 잡으려는 fail-silent 가 그대로 재현된다.
  spec: docs/superpowers/specs/2026-09-10-index-kis-freshness-design.md
"""
import argparse
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import (  # noqa: E402
    INDEX_DAILY_SOURCE, INDEX_DAILY_SOURCES, INDEX_FRESHNESS_ORACLE_CODES,
)
from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.index_writer import (  # noqa: E402
    check_index_freshness, fdr_df_to_index_rows, freshness_cutoff, kis_df_to_index_rows,
    to_date, upsert_index_reconciliation, upsert_index_rows,
)
from utils.korean_time import now_kst  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
INDEX_TICKERS = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}
# KIS 업종코드. FDR 티커와 «다른 축»이라 표를 따로 둔다(0001 코스피 · 1001 코스닥).
INDEX_KIS_CODES = {"KOSPI": "0001", "KOSDAQ": "1001"}
_LOOKBACK_DAYS = 10

_SEL_INDEX_MAX = "SELECT index_code, max(date) FROM index_daily WHERE index_code IN %s GROUP BY index_code"
# 오라클 = daily_prices PK 앞자리를 타는 대형주. cutoff 이하로 잘라 07:40 오탐을 막는다.
_SEL_ORACLE_MAX = "SELECT max(date) FROM daily_prices WHERE stock_code = %s AND date <= %s"


# ── 외부 의존 이음매(테스트에서 갈아끼운다 · 지연 import 로 모듈 로드를 가볍게 유지) ──
def _kis_auth() -> bool:
    from api.kis_auth import auth
    return bool(auth())


def _kis_index_df(index_code: str, start_yyyymmdd: str, end_yyyymmdd: str):
    from api.kis_market_api import get_index_daily_chart
    return get_index_daily_chart(index_code, start_yyyymmdd, end_yyyymmdd)


def _fdr_index_df(ticker: str, start: str):
    import FinanceDataReader as fdr
    return fdr.DataReader(ticker, start)


def _fetch_rows(src: str, start: str, end: str):
    """(지수별 행 목록, «실제로 쓴» 소스). KIS «장애»만 FDR 폴백 — 빈 결과는 폴백 사유가 아니다."""
    if src == "kis":
        try:
            if not _kis_auth():
                raise RuntimeError("KIS 인증 실패")
            out = {}
            for name, code in INDEX_KIS_CODES.items():
                df = _kis_index_df(code, start.replace("-", ""), end.replace("-", ""))
                if df is None:
                    # 🔑 `_url_fetch` 는 404 에 «예외 대신 None» 을 준다(DEBUG 로그만).
                    #    None 은 장애다 — 빈 output2(=0행·판정 대상)와 구분한다.
                    raise RuntimeError(f"KIS 업종 일봉 응답 없음 ({name}/{code})")
                out[name] = kis_df_to_index_rows(name, df)
            return out, "kis"
        except Exception as e:  # noqa: BLE001 — 장애만 폴백
            logger.warning("[index] KIS 경로 실패 → FDR 폴백: %s", e)
    return ({name: fdr_df_to_index_rows(name, _fdr_index_df(ticker, start))
             for name, ticker in INDEX_TICKERS.items()}, "fdr")


def _index_max_dates(conn) -> dict:
    out = {name: None for name in INDEX_TICKERS}
    with conn.cursor() as cur:
        cur.execute(_SEL_INDEX_MAX, (tuple(INDEX_TICKERS),))
        for code, mx in cur.fetchall() or []:
            if code in out:
                out[code] = mx
    return out


def _oracle_dates(conn, cutoff_iso: str) -> list:
    dates = []
    with conn.cursor() as cur:
        for code in INDEX_FRESHNESS_ORACLE_CODES:
            cur.execute(_SEL_ORACLE_MAX, (code, cutoff_iso))
            row = cur.fetchone()
            if row and row[0]:
                dates.append(row[0])
    return dates


def _count_new_rows(rows_by_name: dict, prior_max: dict) -> int:
    """🔑 «직전 max(date) 보다 뒤»인 행만 센다 — 창 단위 UPSERT 의 반환행수와 다른 축이다."""
    n = 0
    for name, rows in (rows_by_name or {}).items():
        pm = to_date(prior_max.get(name))
        for r in rows or []:
            d = to_date(r.get("date"))
            if d is not None and (pm is None or d > pm):
                n += 1
    return n


def collect_index(start: str = None) -> dict:
    """지수 일봉 수집 + 신선도 판정.

    Returns:
        {"KOSPI": n, "KOSDAQ": n, "src": "kis"|"fdr", "stale": [지수코드…]}
        🔴 기존 두 키는 «그대로» 둔다 — EOD 요약(bot/system_monitor.py)이 f-string 으로 흘린다.
    """
    now = now_kst()
    if start is None:
        start = (now.date() - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    end = now.date().strftime("%Y-%m-%d")
    src = INDEX_DAILY_SOURCE if INDEX_DAILY_SOURCE in INDEX_DAILY_SOURCES else "fdr"

    rows_by_name, src = _fetch_rows(src, start, end)

    result = {}
    with KisDbConnection.get_connection() as conn:
        prior_max = _index_max_dates(conn)
        real_rows = 0
        for name in INDEX_TICKERS:
            rows = rows_by_name.get(name) or []
            result[name] = upsert_index_rows(conn, rows)
            real_rows += len(rows)
        new_rows = _count_new_rows(rows_by_name, prior_max)

        # 신선도는 «표에 실제로 있는» 최신 봉으로 판정한다(우리가 보낸 행 수가 아니라).
        # 🔴 이 판정은 소스 스위치 «밖»이다 — "fdr" 로 롤백해도 계속 돈다.
        stale = check_index_freshness(_index_max_dates(conn),
                                      _oracle_dates(conn, freshness_cutoff(now).strftime("%Y-%m-%d")),
                                      now, "index_daily", src, logger)
        stale_codes = sorted({r["index"] for r in stale})
        coverage = (len(INDEX_TICKERS) - len(stale_codes)) / float(len(INDEX_TICKERS))
        upsert_index_reconciliation(conn, now.date().strftime("%Y-%m-%d"), real_rows, new_rows,
                                    real_rows - new_rows, coverage,
                                    "FAIL" if stale_codes else "PASS")

    result["src"] = src
    result["stale"] = stale_codes
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    args = ap.parse_args()
    print(collect_index(args.start))
