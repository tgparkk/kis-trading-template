"""
corp_events 백필 스크립트 (Phase 2)

기능:
  1. DART corpCode.xml 다운로드 + 종목→corp_code 매핑
  2. DART 공시 수집 (split / rights_issue / bonus_issue)
  3. KRX administrative 수집 (FinanceDataReader.StockListing('KRX-ADMIN'))
  4. KRX caution/warning/halt 수집 (KIND 크롤링)
  5. INSERT idempotent (ON CONFLICT DO NOTHING)

실행:
  python scripts/backfill_corp_events.py [--pilot] [--stocks 005930,000660,...]
  --pilot  : 파일럿 5종목만 (005930,000660,005380,035420,051910)
  --stocks : 쉼표로 구분된 종목코드 (--pilot보다 우선)

환경:
  .env 파일에 OPENDART_API_KEY 필요
  DB: 127.0.0.1:5433, robotrader / 1234, robotrader

절대 금지:
  - DELETE/UPDATE 없음 (INSERT ON CONFLICT DO NOTHING만)
  - 전 종목 본 적재는 --pilot 없이 실행 시 사장님 결재 후 진행
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Optional

import psycopg2
import psycopg2.extras
import requests

# ─────────────────────────────────────────────────────────────────────────────
# 프로젝트 루트를 sys.path에 추가
# ─────────────────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_ROOT))  # kis-trading-template 루트

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, ".env"))

# ─────────────────────────────────────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────────────────
DART_KEY = os.getenv("OPENDART_API_KEY", "")
DART_BASE = "https://opendart.fss.or.kr/api"
DART_THROTTLE = 0.3          # 분당 최대 200건 (한도 300건)
TODAY = date.today()
TODAY_STR = TODAY.strftime("%Y%m%d")


def _last_business_day(d: date) -> date:
    """주말이면 직전 금요일 반환 (공휴일 미고려)."""
    from datetime import timedelta
    while d.weekday() >= 5:  # 5=토, 6=일
        d -= timedelta(days=1)
    return d


_LAST_BIZ_DAY = _last_business_day(TODAY)
_LAST_BIZ_STR = _LAST_BIZ_DAY.strftime("%Y%m%d")

PILOT_STOCKS = ["005930", "000660", "005380", "035420", "051910"]

# report_nm 키워드 → event_type 매핑
DART_EVENT_MAP = [
    (["주식분할", "액면분할"], "split"),
    (["무상증자"], "bonus_issue"),
    (["유상증자"], "rights_issue"),
]

_DB_DEFAULTS = dict(
    host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    port=int(os.getenv("TIMESCALE_PORT", "5433")),
    user=os.getenv("TIMESCALE_USER", "robotrader"),
    password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    database=os.getenv("TIMESCALE_DB", "robotrader"),
)

# ─────────────────────────────────────────────────────────────────────────────
# DB 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(**_DB_DEFAULTS)


def _insert_event(
    cur,
    stock_code: str,
    event_type: str,
    event_date: date,
    end_date: Optional[date],
    meta: dict,
) -> bool:
    """INSERT ON CONFLICT DO NOTHING. True=신규, False=중복스킵."""
    cur.execute(
        """
        INSERT INTO corp_events (stock_code, event_type, event_date, end_date, meta)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (stock_code, event_type, event_date) DO NOTHING
        """,
        (stock_code, event_type, event_date, end_date, json.dumps(meta, ensure_ascii=False)),
    )
    return cur.rowcount > 0


def _get_stock_codes_from_db(target_codes: Optional[list[str]] = None) -> list[str]:
    """daily_prices에서 DISTINCT stock_code 추출. target_codes가 있으면 교집합."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT stock_code FROM daily_prices ORDER BY stock_code")
            db_codes = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    if target_codes:
        db_set = set(db_codes)
        return [c for c in target_codes if c in db_set]
    return db_codes


def _get_stock_date_range(stock_code: str) -> tuple[str, str]:
    """종목별 daily_prices의 최소/최대 date 반환 (YYYYMMDD 형식)."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MIN(date), MAX(date) FROM daily_prices WHERE stock_code = %s",
                (stock_code,),
            )
            row = cur.fetchone()
            if row and row[0]:
                min_dt = row[0].strftime("%Y%m%d")
                max_dt = row[1].strftime("%Y%m%d")
                return min_dt, max_dt
    finally:
        conn.close()
    return "20150101", TODAY_STR


# ─────────────────────────────────────────────────────────────────────────────
# 1. DART corpCode.xml 다운로드 + 종목→corp_code 매핑
# ─────────────────────────────────────────────────────────────────────────────

def build_corp_code_map() -> dict[str, str]:
    """DART corpCode.xml 다운로드 후 stock_code → corp_code 딕셔너리 반환."""
    if not DART_KEY:
        logger.warning("[DART] API 키 미설정 — corpCode.xml 다운로드 건너뜀")
        return {}

    url = f"{DART_BASE}/corpCode.xml"
    params = {"crtfc_key": DART_KEY}
    logger.info("[DART] corpCode.xml 다운로드 중...")
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error("[DART] corpCode.xml 다운로드 실패: %s", e)
        return {}

    # zip → XML 파싱
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            xml_filename = [n for n in z.namelist() if n.endswith(".xml")][0]
            xml_data = z.read(xml_filename)
    except Exception as e:
        logger.error("[DART] corpCode.xml 압축 해제 실패: %s", e)
        return {}

    root = ET.fromstring(xml_data)
    mapping: dict[str, str] = {}
    for item in root.findall("list"):
        corp_code = (item.findtext("corp_code") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        if stock_code and len(stock_code) == 6 and stock_code.isdigit():
            mapping[stock_code] = corp_code

    logger.info("[DART] corpCode.xml 파싱 완료: %d개 종목 매핑", len(mapping))
    return mapping


# ─────────────────────────────────────────────────────────────────────────────
# 2. DART 공시 수집 (split / rights_issue / bonus_issue)
# ─────────────────────────────────────────────────────────────────────────────

def _dart_list(corp_code: str, bgn_de: str, end_de: str) -> list[dict]:
    """DART list.json 조회 (타입 필터 없이 전체 조회, 키워드로 분류).

    pblntf_detail_ty 미지정 → 전체 공시 조회 후 report_nm 키워드로 event_type 분류.
    페이지가 100건 이상이면 다음 페이지도 조회.
    """
    all_items: list[dict] = []
    for page in range(1, 20):  # 최대 20페이지 (2000건)
        params = {
            "crtfc_key": DART_KEY,
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": 100,
            "page_no": page,
        }
        time.sleep(DART_THROTTLE)
        try:
            resp = requests.get(f"{DART_BASE}/list.json", params=params, timeout=15)
            resp.encoding = "utf-8"
            data = resp.json()
        except Exception as e:
            logger.debug("[DART] list.json 요청 실패 corp_code=%s page=%d: %s", corp_code, page, e)
            break

        if data.get("status") == "013":  # 데이터 없음
            break
        if data.get("status") != "000":
            logger.debug("[DART] list.json 오류 status=%s msg=%s", data.get("status"), data.get("message"))
            break

        items = data.get("list", [])
        all_items.extend(items)
        if len(items) < 100:
            break  # 마지막 페이지

    return all_items


def _quarter_windows(bgn: str, end: str) -> list[tuple[str, str]]:
    """bgn~end 기간을 3개월 단위 윈도우로 분할."""
    from datetime import datetime, timedelta
    bgn_dt = datetime.strptime(bgn, "%Y%m%d")
    end_dt = datetime.strptime(end, "%Y%m%d")
    windows = []
    cur = bgn_dt
    while cur <= end_dt:
        win_end = min(cur.replace(month=cur.month % 12 + 1, day=1) - timedelta(days=1)
                      if cur.month < 12 else cur.replace(year=cur.year + 1, month=1, day=1) - timedelta(days=1),
                      end_dt)
        # 실제로는 90일 단위로 분할
        win_end = min(cur + timedelta(days=89), end_dt)
        windows.append((cur.strftime("%Y%m%d"), win_end.strftime("%Y%m%d")))
        cur = win_end + timedelta(days=1)
    return windows


def collect_dart_events(
    stock_codes: list[str],
    corp_map: dict[str, str],
) -> dict[str, int]:
    """DART에서 split/rights_issue/bonus_issue 수집 후 DB INSERT.

    Returns: event_type → 적재 건수
    """
    if not DART_KEY:
        logger.warning("[DART] API 키 미설정 — DART 이벤트 수집 건너뜀")
        return {}

    counts: dict[str, int] = {"split": 0, "rights_issue": 0, "bonus_issue": 0}
    skipped_no_corp = 0

    conn = _get_conn()
    try:
        for stock_code in stock_codes:
            corp_code = corp_map.get(stock_code)
            if not corp_code:
                skipped_no_corp += 1
                logger.debug("[DART] %s corp_code 없음 — 건너뜀", stock_code)
                continue

            bgn_de, end_de = _get_stock_date_range(stock_code)
            windows = _quarter_windows(bgn_de, end_de)

            for w_bgn, w_end in windows:
                items = _dart_list(corp_code, w_bgn, w_end)
                for item in items:
                    report_nm = item.get("report_nm", "")
                    rcept_dt = item.get("rcept_dt", "")
                    rcept_no = item.get("rcept_no", "")

                    if not rcept_dt or len(rcept_dt) != 8:
                        continue

                    event_type = None
                    for keywords, etype in DART_EVENT_MAP:
                        if any(kw in report_nm for kw in keywords):
                            event_type = etype
                            break
                    if not event_type:
                        continue

                    try:
                        event_date = date(
                            int(rcept_dt[:4]),
                            int(rcept_dt[4:6]),
                            int(rcept_dt[6:8]),
                        )
                    except ValueError:
                        continue

                    meta = {
                        "source": "opendart",
                        "rcept_no": rcept_no,
                        "report_nm": report_nm,
                        "rcept_dt": rcept_dt,
                    }

                    with conn.cursor() as cur:
                        inserted = _insert_event(cur, stock_code, event_type, event_date, None, meta)
                    conn.commit()

                    if inserted:
                        counts[event_type] = counts.get(event_type, 0) + 1
                        logger.debug(
                            "[DART] INSERT %s %s %s %s", stock_code, event_type, event_date, report_nm
                        )
    finally:
        conn.close()

    logger.info(
        "[DART] 수집 완료 — split=%d, rights_issue=%d, bonus_issue=%d, corp_code없음=%d",
        counts["split"], counts["rights_issue"], counts["bonus_issue"], skipped_no_corp,
    )
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# 3. KRX administrative 수집 (FinanceDataReader)
# ─────────────────────────────────────────────────────────────────────────────

def collect_fdr_administrative(stock_codes: list[str]) -> int:
    """FinanceDataReader.StockListing('KRX-ADMIN') → administrative 적재.

    현재 시점 스냅샷만 → end_date=NULL (해제 시점 추적 불가).
    """
    try:
        import FinanceDataReader as fdr
    except ImportError:
        logger.error("[FDR] finance-datareader 미설치 — pip install finance-datareader")
        return 0

    logger.info("[FDR] KRX-ADMIN 관리종목 목록 조회 중...")
    try:
        df = fdr.StockListing("KRX-ADMIN")
    except Exception as e:
        logger.error("[FDR] KRX-ADMIN 조회 실패: %s", e)
        return 0

    if df is None or df.empty:
        logger.warning("[FDR] KRX-ADMIN 결과 없음")
        return 0

    logger.info("[FDR] KRX-ADMIN 조회 완료: %d건, 컬럼=%s", len(df), list(df.columns))

    # 종목코드 컬럼 탐색 (FDR 버전별 컬럼명 다를 수 있음)
    code_col = None
    for col in ["Code", "Symbol", "code", "symbol", "ticker", "Ticker"]:
        if col in df.columns:
            code_col = col
            break
    if code_col is None:
        logger.error("[FDR] KRX-ADMIN 종목코드 컬럼 없음. 컬럼 목록: %s", list(df.columns))
        return 0

    target_set = set(stock_codes)
    count = 0
    conn = _get_conn()
    try:
        for _, row in df.iterrows():
            # FDR Symbol: 숫자만 있으면 zfill(6), 이미 6자리면 그대로
            raw_val = str(row[code_col]).strip()
            if raw_val.isdigit():
                raw_code = raw_val.zfill(6)
            else:
                raw_code = raw_val
            if raw_code not in target_set:
                continue

            meta = {
                "source": "fdr",
                "snapshot_date": TODAY_STR,
                "listing": "KRX-ADMIN",
            }
            # 추가 컬럼이 있으면 meta에 포함
            for extra_col in ["Name", "name", "Market", "market"]:
                if extra_col in df.columns:
                    val = row.get(extra_col)
                    if val is not None:
                        meta[extra_col.lower()] = str(val)

            with conn.cursor() as cur:
                inserted = _insert_event(cur, raw_code, "administrative", TODAY, None, meta)
            conn.commit()
            if inserted:
                count += 1
                logger.debug("[FDR] INSERT administrative %s", raw_code)
    finally:
        conn.close()

    logger.info("[FDR] administrative 적재: %d건 (교집합)", count)
    return count


# ─────────────────────────────────────────────────────────────────────────────
# 4. KIND 크롤링 (caution / warning / halt)
# ─────────────────────────────────────────────────────────────────────────────

# KRX data.krx.co.kr POST API (Phase 1 파일럿에서 동작 확인)
_KRX_GEN_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
_KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
}

# bld 코드 → event_type 매핑 (Phase 1 파일럿 확인값)
_KRX_BLD_MAP = [
    ("dbms/MDC/STAT/standard/MDCSTAT30001", "administrative"),  # 관리종목
    ("dbms/MDC/STAT/standard/MDCSTAT30002", "warning"),         # 투자경고/위험
]

# KIND 투자주의/경고 페이지 (caution/warning/halt 보조 크롤링)
_KIND_URLS = {
    "caution": "https://kind.krx.co.kr/investwarn/investattentwarnriskyMain.do?currentPageSize=100",
    "halt": "https://kind.krx.co.kr/investwarn/adminissue.do",
}

_KIND_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://kind.krx.co.kr/",
    "Accept": "text/html,application/xhtml+xml",
}


def _krx_post(bld: str, trd_dd: str) -> list[dict]:
    """KRX data.krx.co.kr POST API 호출."""
    payload = {
        "bld": bld,
        "locale": "ko_KR",
        "mktId": "ALL",
        "trdDd": trd_dd,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    try:
        r = requests.post(_KRX_GEN_URL, data=payload, headers=_KRX_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("OutBlock_1", [])
    except Exception as e:
        logger.debug("[KRX POST] bld=%s 오류: %s", bld, e)
        return []


def _parse_krx_stock_code(rec: dict) -> Optional[str]:
    """KRX 레코드에서 종목코드 추출 (컬럼명 변형 대응)."""
    for key in ["ISU_SRT_CD", "isu_srt_cd", "shrt_isu_cd", "SHRT_ISU_CD", "stock_code"]:
        val = rec.get(key, "")
        if val and str(val).strip():
            code = str(val).strip()
            # 숫자 6자리 확인
            if len(code) == 6 and code.isdigit():
                return code
            # A005930 형식 처리
            if len(code) == 7 and code[0].isalpha() and code[1:].isdigit():
                return code[1:]
    return None


def collect_krx_events(stock_codes: list[str]) -> dict[str, int]:
    """KRX data.krx.co.kr POST API + KIND 크롤링으로 caution/warning/halt/administrative 수집.

    실패 시 자체 우회 없이 보고만.
    """
    target_set = set(stock_codes)
    counts: dict[str, int] = {}
    failures: list[str] = []

    conn = _get_conn()
    try:
        # 1) KRX POST API (관리종목, 투자경고) — 최근 영업일 기준
        for bld, event_type in _KRX_BLD_MAP:
            logger.info("[KRX POST] bld=%s event_type=%s 조회 중 (기준일=%s)...", bld, event_type, _LAST_BIZ_STR)
            block = _krx_post(bld, _LAST_BIZ_STR)
            if not block:
                logger.warning("[KRX POST] bld=%s 결과 없음 (기준일=%s)", bld, _LAST_BIZ_STR)
                failures.append(f"KRX POST {bld} 결과 없음 (기준일={_LAST_BIZ_STR})")
                continue

            logger.info("[KRX POST] %s: %d건 조회", event_type, len(block))
            cnt = 0
            for rec in block:
                code = _parse_krx_stock_code(rec)
                if not code or code not in target_set:
                    continue
                meta = {
                    "source": "krx_post",
                    "snapshot_date": TODAY_STR,
                    "bld": bld,
                    "raw": {k: v for k, v in rec.items() if k in [
                        "ISU_NM", "isu_nm", "DESIG_DT", "desig_dt", "MKT_NM", "mkt_nm"
                    ]},
                }
                with conn.cursor() as cur:
                    inserted = _insert_event(cur, code, event_type, TODAY, None, meta)
                conn.commit()
                if inserted:
                    cnt += 1
                    logger.debug("[KRX POST] INSERT %s %s", event_type, code)
            counts[event_type] = counts.get(event_type, 0) + cnt
            logger.info("[KRX POST] %s 적재: %d건", event_type, cnt)

        # 2) KIND 크롤링 (caution/halt)
        try:
            from bs4 import BeautifulSoup
            bs4_ok = True
        except ImportError:
            bs4_ok = False
            logger.warning("[KIND] beautifulsoup4 미설치 — KIND 크롤링 건너뜀")
            failures.append("beautifulsoup4 미설치로 KIND 크롤링 불가")

        if bs4_ok:
            for event_type, url in _KIND_URLS.items():
                logger.info("[KIND] %s 크롤링 중: %s", event_type, url)
                time.sleep(0.5)
                try:
                    r = requests.get(url, headers=_KIND_HEADERS, timeout=15)
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "html.parser")

                    # 종목코드 추출: td 중 6자리 숫자 패턴
                    import re
                    code_pattern = re.compile(r"^\d{6}$")
                    found_codes = set()
                    for td in soup.find_all("td"):
                        text = td.get_text(strip=True)
                        if code_pattern.match(text):
                            found_codes.add(text)

                    logger.info("[KIND] %s: 페이지에서 %d개 종목코드 발견", event_type, len(found_codes))
                    cnt = 0
                    for code in found_codes:
                        if code not in target_set:
                            continue
                        meta = {
                            "source": "kind_crawl",
                            "snapshot_date": TODAY_STR,
                            "url": url,
                        }
                        with conn.cursor() as cur:
                            inserted = _insert_event(cur, code, event_type, TODAY, None, meta)
                        conn.commit()
                        if inserted:
                            cnt += 1
                    counts[event_type] = counts.get(event_type, 0) + cnt
                    logger.info("[KIND] %s 적재: %d건", event_type, cnt)

                except Exception as e:
                    logger.warning("[KIND] %s 크롤링 실패: %s", event_type, e)
                    failures.append(f"KIND {event_type} 크롤링 실패: {e}")

    finally:
        conn.close()

    if failures:
        logger.warning("[KRX/KIND] 실패 항목 (자체 우회 없음, 보고만):")
        for f in failures:
            logger.warning("  - %s", f)

    return counts, failures


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="corp_events 백필 스크립트")
    parser.add_argument("--pilot", action="store_true", help="파일럿 5종목만 실행")
    parser.add_argument("--stocks", type=str, default="", help="쉼표로 구분된 종목코드")
    args = parser.parse_args()

    if args.stocks:
        target_stocks_raw = [s.strip().zfill(6) for s in args.stocks.split(",") if s.strip()]
    elif args.pilot:
        target_stocks_raw = PILOT_STOCKS
    else:
        # 전 종목 본 적재 — 사장님 결재 후 진행 확인
        print("=" * 60)
        print("경고: 전 종목 본 적재를 시도합니다.")
        print("사장님 결재 완료 후 진행하세요.")
        print("파일럿만 실행하려면 --pilot 옵션을 사용하세요.")
        print("=" * 60)
        confirm = input("계속하시겠습니까? (yes 입력): ").strip().lower()
        if confirm != "yes":
            print("취소됨.")
            return
        target_stocks_raw = None  # DB에서 전체 조회

    logger.info("=" * 60)
    logger.info("corp_events 백필 시작 (Phase 2)")
    logger.info("날짜: %s", TODAY)
    if args.pilot:
        logger.info("모드: 파일럿 (%s)", PILOT_STOCKS)
    elif args.stocks:
        logger.info("모드: 지정 종목 (%s)", target_stocks_raw)
    else:
        logger.info("모드: 전 종목 본 적재")
    logger.info("=" * 60)

    # 1) daily_prices에서 종목 추출 (target과 교집합)
    logger.info("[1/4] daily_prices에서 종목 목록 추출...")
    stock_codes = _get_stock_codes_from_db(target_stocks_raw)
    logger.info("  처리 대상: %d종목", len(stock_codes))

    if not stock_codes:
        logger.error("처리할 종목 없음 — daily_prices에 데이터가 있는지 확인하세요")
        return

    # 2) DART corpCode.xml → 매핑 구축
    logger.info("[2/4] DART corpCode.xml 매핑 구축...")
    corp_map = build_corp_code_map()
    matched = sum(1 for c in stock_codes if c in corp_map)
    logger.info("  종목 %d개 중 corp_code 매핑: %d개", len(stock_codes), matched)

    # 3) DART 공시 수집 (split / rights_issue / bonus_issue)
    logger.info("[3/4] DART 공시 수집 (split/rights_issue/bonus_issue)...")
    dart_counts = collect_dart_events(stock_codes, corp_map)

    # 4) KRX administrative + KIND caution/warning/halt
    logger.info("[4/4] KRX/KIND 수집 (administrative/caution/warning/halt)...")

    # 4a) FDR administrative
    fdr_count = collect_fdr_administrative(stock_codes)

    # 4b) KRX POST API + KIND 크롤링
    krx_counts, kind_failures = collect_krx_events(stock_codes)

    # ─── 최종 보고 ───
    logger.info("")
    logger.info("=" * 60)
    logger.info("corp_events 백필 완료 — 적재 결과")
    logger.info("=" * 60)
    logger.info("  [DART] split:        %d건", dart_counts.get("split", 0))
    logger.info("  [DART] rights_issue: %d건", dart_counts.get("rights_issue", 0))
    logger.info("  [DART] bonus_issue:  %d건", dart_counts.get("bonus_issue", 0))
    logger.info("  [FDR]  administrative: %d건", fdr_count)
    for etype, cnt in krx_counts.items():
        logger.info("  [KRX/KIND] %s: %d건", etype, cnt)
    if kind_failures:
        logger.warning("  [실패 항목] (자체 우회 없음, 보고만):")
        for f in kind_failures:
            logger.warning("    - %s", f)

    # DB corp_events 총 건수 확인
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT event_type, COUNT(*) FROM corp_events GROUP BY event_type ORDER BY event_type")
            rows = cur.fetchall()
        logger.info("")
        logger.info("[DB] corp_events 현재 총 건수:")
        for etype, cnt in rows:
            logger.info("  %s: %d건", etype, cnt)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
