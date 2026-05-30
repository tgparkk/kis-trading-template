"""
financial_statements.operating_cash_flow 백필 스크립트 (Book 11 문병로 Phase 0)

기능:
  1. DART corpCode.xml 다운로드 + 종목→corp_code 매핑 (backfill_corp_events 로직 차용)
  2. financial_statements의 (stock_code, report_date) universe(131종목 × 연도) 추출
  3. DART 단일회사 전체 재무제표(fnlttSinglAcntAll.json)에서 영업활동현금흐름 추출
     - sj_div='CF' AND account_id='ifrs-full_CashFlowsFromUsedInOperatingActivities' 우선
     - 실패 시 account_nm 부분일치('영업활동')로 fallback
  4. 멱등 UPDATE: operating_cash_flow가 NULL인 행만 채움

단위 (검증 완료):
  - DART thstrm_amount(당기금액)는 '원' 단위.
  - financial_statements의 revenue/operating_profit은 '억원'(1e8 원) 단위.
    (검증: 현대차005380 2023 revenue 저장값 1,626,636 = 162.66조원 = 162,663,600,000,000원 → /1e8)
  - 따라서 저장 시 DART 원금액 / 1e8 = 억원으로 환산해 저장한다.
  - 교차검증: Kia 000270 2023 OCF 11.30조(112,965억), SK하이닉스 000660 2022 OCF 14.78조(147,805억).

실행:
  python scripts/backfill_operating_cash_flow.py --pilot --apply
  python scripts/backfill_operating_cash_flow.py --stocks 005380,000270 --apply
  python scripts/backfill_operating_cash_flow.py --apply               # 전체 131종목
  python scripts/backfill_operating_cash_flow.py                       # dry-run (카운트만)
  python scripts/backfill_operating_cash_flow.py --years 2021,2022,2023,2024,2025 --apply

환경:
  .env 파일에 OPENDART_API_KEY 필요
  DB: 127.0.0.1:5433, robotrader / 1234, robotrader

절대 금지:
  - DELETE/TRUNCATE/retention 없음. operating_cash_flow NULL → 값 UPDATE만.
  - DART 부재(status 013)는 정상 — 해당 구간 NULL 유지하고 skip.
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional

import psycopg2
import requests

# ─────────────────────────────────────────────────────────────────────────────
# 프로젝트 루트를 sys.path에 추가 + .env 로드
# ─────────────────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_ROOT, ".env"))

# ─────────────────────────────────────────────────────────────────────────────
# 로깅
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
DART_THROTTLE = 0.3            # 호출 간 0.3초 (분당 200건, 한도 300건)
ANNUAL_REPORT_CODE = "11011"  # 사업보고서(연간)

# 영업활동현금흐름 account_id (DART IFRS 표준 — 가장 안정적)
OCF_ACCOUNT_IDS = (
    "ifrs-full_CashFlowsFromUsedInOperatingActivities",
    "ifrs_CashFlowsFromUsedInOperatingActivities",
)
# account_nm fallback 키워드 (부분일치)
OCF_NAME_KEYWORDS = ("영업활동현금흐름", "영업활동으로인한현금흐름", "영업활동으로 인한 현금흐름")

# 단위 환산: DART 원 → financial_statements 억원
DART_AMOUNT_DIVISOR = 1e8

PILOT_STOCKS = ["005380", "000270", "000660", "012330", "005490"]

_DB_DEFAULTS = dict(
    host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    port=int(os.getenv("TIMESCALE_PORT", "5433")),
    user=os.getenv("TIMESCALE_USER", "robotrader"),
    password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    database=os.getenv("TIMESCALE_DB", "robotrader"),
)


def _get_conn():
    return psycopg2.connect(**_DB_DEFAULTS)


# ─────────────────────────────────────────────────────────────────────────────
# DART corpCode.xml 매핑 (backfill_corp_events.build_corp_code_map 동일 로직)
# ─────────────────────────────────────────────────────────────────────────────

def build_corp_code_map() -> dict[str, str]:
    """DART corpCode.xml 다운로드 후 stock_code → corp_code 딕셔너리 반환."""
    if not DART_KEY:
        logger.error("[DART] OPENDART_API_KEY 미설정 — corpCode.xml 다운로드 불가")
        return {}

    url = f"{DART_BASE}/corpCode.xml"
    logger.info("[DART] corpCode.xml 다운로드 중...")
    try:
        resp = requests.get(url, params={"crtfc_key": DART_KEY}, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error("[DART] corpCode.xml 다운로드 실패: %s", e)
        return {}

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
# universe 추출
# ─────────────────────────────────────────────────────────────────────────────

def load_targets(
    target_stocks: Optional[list[str]],
    override_years: Optional[set[int]],
) -> list[tuple[str, str, int]]:
    """financial_statements에서 백필 대상 (stock_code, report_date, bsns_year) 추출.

    operating_cash_flow가 NULL인 행만 대상으로 한다(멱등).
    report_date 연도 = bsns_year로 매핑.
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            sql = (
                "SELECT stock_code, report_date FROM financial_statements "
                "WHERE operating_cash_flow IS NULL "
                "AND report_date ~ '^[0-9]{4}-' "
            )
            params: list = []
            if target_stocks:
                sql += "AND stock_code = ANY(%s) "
                params.append(target_stocks)
            sql += "ORDER BY stock_code, report_date"
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    targets: list[tuple[str, str, int]] = []
    for stock_code, report_date in rows:
        try:
            year = int(report_date[:4])
        except (ValueError, TypeError):
            continue
        if override_years and year not in override_years:
            continue
        targets.append((stock_code, report_date, year))
    return targets


# ─────────────────────────────────────────────────────────────────────────────
# DART 영업활동현금흐름 조회
# ─────────────────────────────────────────────────────────────────────────────

def _parse_amount(raw: Optional[str]) -> Optional[float]:
    """DART thstrm_amount 문자열 → float(원 단위). 빈값/파싱불가 시 None."""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if s in ("", "-"):
        return None
    # 괄호 음수 표기 (xxx) → -xxx
    neg = False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
        neg = True
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def fetch_ocf(corp_code: str, bsns_year: int) -> tuple[Optional[float], str]:
    """DART에서 해당 연도 영업활동현금흐름(원 단위) 조회.

    Returns: (ocf_원 or None, status_note)
      - CFS(연결) 우선, 없으면 OFS(별도) 재시도.
      - account_id 우선 매칭, 실패 시 account_nm 부분일치 fallback.
    """
    for fs_div in ("CFS", "OFS"):
        time.sleep(DART_THROTTLE)
        try:
            resp = requests.get(
                f"{DART_BASE}/fnlttSinglAcntAll.json",
                params={
                    "crtfc_key": DART_KEY,
                    "corp_code": corp_code,
                    "bsns_year": str(bsns_year),
                    "reprt_code": ANNUAL_REPORT_CODE,
                    "fs_div": fs_div,
                },
                timeout=20,
            )
            resp.encoding = "utf-8"
            data = resp.json()
        except Exception as e:
            logger.debug("[DART] 요청 실패 corp=%s year=%s fs=%s: %s", corp_code, bsns_year, fs_div, e)
            continue

        status = data.get("status")
        if status == "013":  # 조회된 데이터 없음 — 정상(이 fs_div 부재)
            continue
        if status != "000":
            logger.debug("[DART] status=%s msg=%s corp=%s year=%s fs=%s",
                         status, data.get("message"), corp_code, bsns_year, fs_div)
            continue

        rows = data.get("list", [])
        cf_rows = [r for r in rows if (r.get("sj_div") or "").strip() == "CF"]
        if not cf_rows:
            continue

        # 1) account_id 정확 매칭
        for r in cf_rows:
            aid = (r.get("account_id") or "").strip()
            if aid in OCF_ACCOUNT_IDS:
                amt = _parse_amount(r.get("thstrm_amount"))
                if amt is not None:
                    return amt, f"{fs_div}/account_id"

        # 2) account_nm 부분일치 fallback (공백 제거 비교)
        for r in cf_rows:
            nm = (r.get("account_nm") or "").replace(" ", "")
            if any(kw.replace(" ", "") in nm for kw in OCF_NAME_KEYWORDS):
                amt = _parse_amount(r.get("thstrm_amount"))
                if amt is not None:
                    return amt, f"{fs_div}/account_nm"

    return None, "not_found"


# ─────────────────────────────────────────────────────────────────────────────
# 백필 실행
# ─────────────────────────────────────────────────────────────────────────────

def run_backfill(
    targets: list[tuple[str, str, int]],
    corp_map: dict[str, str],
    apply: bool,
) -> dict:
    """대상 (stock_code, report_date, year)별로 OCF 조회 후 UPDATE(apply=True).

    연도/종목별 DART 호출 캐시로 중복 호출 방지.
    """
    stats = {
        "total": len(targets),
        "updated": 0,
        "found_no_apply": 0,
        "no_corp_code": 0,
        "dart_absent": 0,
        "parse_fail": 0,
    }
    samples: list[tuple] = []          # (stock, year, ocf_억원, note)
    absent_list: list[tuple] = []      # (stock, year)
    no_corp_stocks: set[str] = set()

    # (corp_code, year) → (ocf_원 or None, note) 캐시
    ocf_cache: dict[tuple[str, int], tuple[Optional[float], str]] = {}

    conn = _get_conn()
    try:
        for i, (stock_code, report_date, year) in enumerate(targets, 1):
            corp_code = corp_map.get(stock_code)
            if not corp_code:
                stats["no_corp_code"] += 1
                no_corp_stocks.add(stock_code)
                continue

            cache_key = (corp_code, year)
            if cache_key in ocf_cache:
                ocf_won, note = ocf_cache[cache_key]
            else:
                ocf_won, note = fetch_ocf(corp_code, year)
                ocf_cache[cache_key] = (ocf_won, note)

            if ocf_won is None:
                if note == "not_found":
                    stats["dart_absent"] += 1
                    absent_list.append((stock_code, year))
                else:
                    stats["parse_fail"] += 1
                logger.debug("[OCF] %s %s(year=%d) 없음: %s", stock_code, report_date, year, note)
                continue

            ocf_eok = round(ocf_won / DART_AMOUNT_DIVISOR, 2)  # 원 → 억원

            if len(samples) < 40:
                samples.append((stock_code, year, ocf_eok, note))

            if apply:
                with conn.cursor() as cur:
                    # 멱등: NULL인 경우만 UPDATE
                    cur.execute(
                        "UPDATE financial_statements SET operating_cash_flow = %s, updated_at = NOW() "
                        "WHERE stock_code = %s AND report_date = %s AND operating_cash_flow IS NULL",
                        (ocf_eok, stock_code, report_date),
                    )
                    if cur.rowcount > 0:
                        stats["updated"] += 1
                conn.commit()
            else:
                stats["found_no_apply"] += 1

            if i % 50 == 0:
                logger.info("[진행] %d/%d 처리 (updated=%d, absent=%d)",
                            i, stats["total"], stats["updated"], stats["dart_absent"])
    finally:
        conn.close()

    stats["samples"] = samples
    stats["absent_list"] = absent_list
    stats["no_corp_stocks"] = sorted(no_corp_stocks)
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="영업활동현금흐름(operating_cash_flow) 백필")
    parser.add_argument("--pilot", action="store_true", help=f"파일럿 종목만: {PILOT_STOCKS}")
    parser.add_argument("--stocks", type=str, default="", help="쉼표구분 종목코드 (--pilot보다 우선)")
    parser.add_argument("--years", type=str, default="", help="쉼표구분 연도 필터 (예: 2021,2022,2023)")
    parser.add_argument("--apply", action="store_true", help="실제 DB UPDATE (없으면 dry-run 카운트만)")
    args = parser.parse_args()

    if not DART_KEY:
        logger.error("OPENDART_API_KEY가 .env에 없습니다. 중단.")
        sys.exit(1)

    if args.stocks:
        target_stocks = [s.strip().zfill(6) for s in args.stocks.split(",") if s.strip()]
    elif args.pilot:
        target_stocks = PILOT_STOCKS
    else:
        target_stocks = None  # 전체 131종목

    override_years = None
    if args.years:
        override_years = {int(y.strip()) for y in args.years.split(",") if y.strip()}

    logger.info("=" * 60)
    logger.info("operating_cash_flow 백필 시작 (Book 11 문병로 Phase 0)")
    logger.info("모드: %s | apply=%s | years=%s",
                "파일럿" if args.pilot else ("지정종목" if args.stocks else "전체"),
                args.apply, override_years or "all")
    logger.info("=" * 60)

    # 1) corp_code 매핑
    corp_map = build_corp_code_map()
    if not corp_map:
        logger.error("corp_code 매핑 실패. 중단.")
        sys.exit(1)

    # 2) 대상 추출 (NULL 행만)
    targets = load_targets(target_stocks, override_years)
    n_stocks = len({t[0] for t in targets})
    logger.info("[대상] OCF NULL 행 %d건 (%d종목)", len(targets), n_stocks)
    if not targets:
        logger.info("백필 대상 없음 (이미 모두 채워졌거나 종목 없음).")
        return

    matched = sum(1 for t in targets if t[0] in corp_map)
    logger.info("[corp_code] 대상행 %d 중 매핑 %d건", len(targets), matched)

    # 3) 백필 실행
    stats = run_backfill(targets, corp_map, apply=args.apply)

    # 4) 보고
    logger.info("")
    logger.info("=" * 60)
    logger.info("백필 결과")
    logger.info("=" * 60)
    logger.info("  대상 행:            %d", stats["total"])
    if args.apply:
        logger.info("  UPDATE 성공:        %d", stats["updated"])
    else:
        logger.info("  DART 값 확보(미적용): %d  (dry-run)", stats["found_no_apply"])
    logger.info("  DART 부재(013):     %d", stats["dart_absent"])
    logger.info("  corp_code 없음:     %d (종목: %s)", stats["no_corp_code"], stats["no_corp_stocks"])
    logger.info("  파싱 실패:          %d", stats["parse_fail"])
    logger.info("")
    logger.info("  값 샘플 (stock, year, ocf_억원, source):")
    for s in stats["samples"][:20]:
        logger.info("    %s %d  %s억원  [%s]", s[0], s[1], f"{s[2]:,.2f}", s[3])


if __name__ == "__main__":
    main()
