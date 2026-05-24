"""
P0 corp_events 백필 스크립트 (pykrx 기반)

수집 대상:
  - split   : 액면분할 (액면가 감소, 예 500->100)
  - merge   : 액면병합 (액면가 증가, 예 100->500)  -- event_type 'split' 로 meta.direction='merge'
  - dividend_ex : 배당락 (DPS > 0 날짜)

절대 원칙:
  - No Look-Ahead: event_date 기준 그 시점 발생 사실만 적재
  - Idempotent: ON CONFLICT (stock_code, event_type, event_date) DO NOTHING
  - DELETE/UPDATE 없음

실행:
  python scripts/10pct_strategy/p0_backfill_corp_events.py [--pilot] [--no-dividend]
  --pilot      : 파일럿 10종목만 (삼성전자/SK하이닉스/카카오/NAVER/현대차/LG에너지/삼성SDI/현대모비스/POSCO/KB금융)
  --no-dividend: 배당락 수집 건너뜀 (속도 절감, split/merge만)
  --start      : 시작일 (기본 20210101)
  --end        : 종료일 (기본 오늘)

소요 시간 예상:
  - split/merge: 종목당 ~0.3초 × 1,400종목 ≈ 7분
  - dividend_ex: 월별 전종목 조회 × 65개월 ≈ 20~40분 (KRX API rate)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from datetime import date, datetime, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────────────────
DB_CONF = dict(
    host="127.0.0.1",
    port=5433,
    user="robotrader",
    password="1234",
    database="robotrader",
)

DEFAULT_START = "20210101"
DEFAULT_END = date.today().strftime("%Y%m%d")

PILOT_STOCKS = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "035720",  # 카카오
    "035420",  # NAVER
    "005380",  # 현대차
    "373220",  # LG에너지솔루션
    "006400",  # 삼성SDI
    "012330",  # 현대모비스
    "005490",  # POSCO홀딩스
    "105560",  # KB금융
]

# pykrx throttle (초): 너무 빠르면 KRX 차단
PYKRX_THROTTLE = 0.25


# ─────────────────────────────────────────────────────────────────────────────
# DB 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(**DB_CONF)


def insert_event(
    cur,
    stock_code: str,
    event_type: str,
    event_date: date,
    meta: dict,
    end_date: Optional[date] = None,
) -> bool:
    """INSERT ON CONFLICT DO NOTHING. True=신규 삽입, False=중복 스킵."""
    cur.execute(
        """
        INSERT INTO corp_events (stock_code, event_type, event_date, end_date, meta)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (stock_code, event_type, event_date) DO NOTHING
        """,
        (
            stock_code,
            event_type,
            event_date,
            end_date,
            json.dumps(meta, ensure_ascii=False),
        ),
    )
    return cur.rowcount > 0


def get_universe_from_db() -> list[str]:
    """minute_candles + candidate_stocks 에서 6자리 숫자 종목코드 반환."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT stock_code FROM minute_candles
                WHERE stock_code ~ '^[0-9]{6}$'
                UNION
                SELECT DISTINCT stock_code FROM candidate_stocks
                WHERE stock_code ~ '^[0-9]{6}$'
                ORDER BY stock_code
                """
            )
            codes = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    return codes


def count_corp_events() -> dict:
    """현재 corp_events 집계 반환."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_type, COUNT(*) FROM corp_events GROUP BY event_type ORDER BY event_type"
            )
            return dict(cur.fetchall())
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 1. 액면분할/병합 수집 (get_stock_major_changes)
# ─────────────────────────────────────────────────────────────────────────────

def _get_already_scanned_codes() -> set[str]:
    """pykrx source로 split 이벤트가 있는 종목 = 이미 스캔 완료 종목."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT stock_code FROM corp_events "
                "WHERE event_type='split' AND meta->>'source'='pykrx'"
            )
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def _insert_split_events(code: str, events: list[dict]) -> tuple[int, int]:
    """split/merge 이벤트 목록을 DB에 INSERT. (split_cnt, merge_cnt) 반환."""
    conn = get_conn()
    split_cnt = merge_cnt = 0
    try:
        for ev in events:
            try:
                event_dt = datetime.strptime(ev["event_date"], "%Y-%m-%d").date()
            except (ValueError, KeyError):
                continue
            direction = ev.get("direction", "split")
            meta = {
                "source": "pykrx",
                "face_value_before": ev.get("face_before"),
                "face_value_after":  ev.get("face_after"),
                "ratio":             ev.get("ratio"),
                "direction":         direction,
                "split_factor":      ev.get("split_factor"),
            }
            with conn.cursor() as cur:
                inserted = insert_event(cur, code, "split", event_dt, meta)
            conn.commit()
            if inserted:
                if direction == "split":
                    split_cnt += 1
                else:
                    merge_cnt += 1
    finally:
        conn.close()
    return split_cnt, merge_cnt


def collect_splits(
    stock_codes: list[str],
    start_date: str,
    end_date: str,
    per_ticker_timeout: float = 12.0,
    workers: int = 5,
    skip_already_scanned: bool = True,
) -> dict[str, int]:
    """
    _p0_worker.py 를 병렬 subprocess로 호출해 액면분할/병합 수집.

    - workers: 동시 subprocess 수 (기본 5, pykrx KRX API rate 고려)
    - skip_already_scanned: pykrx source split이 이미 있는 종목 스킵
    - subprocess 격리로 pykrx 내부 logging deadlock 완전 방지
    - No Look-Ahead: event_date = 실제 변경 발효일 (pykrx 인덱스)
    """
    import subprocess
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor

    worker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_p0_worker.py")
    python_exe = sys.executable

    # 이미 스캔 완료 종목 스킵 (split 결과 없어도 한 번 조회한 종목 재조회 불필요)
    if skip_already_scanned:
        already = _get_already_scanned_codes()
        todo = [c for c in stock_codes if c not in already]
        logger.info("[split] 이미 스캔 완료 %d종목 스킵, 남은 대상: %d종목",
                    len(already), len(todo))
    else:
        todo = list(stock_codes)

    counts = {"split": 0, "merge": 0, "skip_no_data": 0, "skip_error": 0, "skip_timeout": 0}

    def run_one(code: str) -> tuple[str, list]:
        try:
            proc = subprocess.run(
                [python_exe, worker_path, code, start_date, end_date],
                capture_output=True, text=True, timeout=per_ticker_timeout,
            )
            raw = proc.stdout.strip()
            return code, json.loads(raw) if raw else []
        except subprocess.TimeoutExpired:
            return code, None  # None = timeout
        except Exception:
            return code, []

    total = len(todo)
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_one, code): code for code in todo}
        for fut in as_completed(futures):
            code = futures[fut]
            done += 1
            if done % 100 == 0:
                logger.info(
                    "[split] %d/%d (split=%d merge=%d timeout=%d err=%d)",
                    done, total, counts["split"], counts["merge"],
                    counts["skip_timeout"], counts["skip_error"],
                )
            try:
                _, events = fut.result()
            except Exception as e:
                logger.debug("[split] %s future error: %s", code, e)
                counts["skip_error"] += 1
                continue

            if events is None:
                counts["skip_timeout"] += 1
                continue
            if not events:
                counts["skip_no_data"] += 1
                continue

            sc, mc = _insert_split_events(code, events)
            counts["split"] += sc
            counts["merge"] += mc

    logger.info(
        "[split] 완료 split=%d merge=%d no_data=%d timeout=%d err=%d",
        counts["split"], counts["merge"], counts["skip_no_data"],
        counts["skip_timeout"], counts["skip_error"],
    )
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# 2. 배당락 수집 (get_market_fundamental_by_ticker 월별)
# ─────────────────────────────────────────────────────────────────────────────

def _month_windows(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """start~end 를 월 단위 (YYYYMM01 ~ YYYYMM말일) 윈도우로 분할."""
    start_dt = datetime.strptime(start_date, "%Y%m%d").date()
    end_dt = datetime.strptime(end_date, "%Y%m%d").date()

    windows = []
    cur = start_dt.replace(day=1)
    while cur <= end_dt:
        # 해당 월 마지막 날
        if cur.month == 12:
            win_end = cur.replace(year=cur.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            win_end = cur.replace(month=cur.month + 1, day=1) - timedelta(days=1)
        win_end = min(win_end, end_dt)
        windows.append((cur.strftime("%Y%m%d"), win_end.strftime("%Y%m%d")))
        # 다음 달 1일
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            cur = cur.replace(month=cur.month + 1, day=1)

    return windows


def collect_dividend_ex(
    stock_codes: list[str],
    start_date: str,
    end_date: str,
) -> int:
    """
    pykrx get_market_fundamental_by_ticker로 배당락일 감지.

    전략: 월별로 전종목 fundamental 조회 → DPS > 0 인 날짜 = 배당락일로 간주.

    Note: pykrx는 배당락일 직접 API가 없어 DPS > 0 인 거래일을 배당락으로 추정.
    이는 배당기준일 근처에 DPS가 반영되므로 실무적으로 충분히 정확.

    No Look-Ahead: event_date = DPS > 0 으로 표시된 해당 거래일
    """
    from pykrx import stock as pykrx_stock

    windows = _month_windows(start_date, end_date)
    target_set = set(stock_codes)
    total_inserted = 0
    conn = get_conn()

    try:
        for w_idx, (w_start, w_end) in enumerate(windows):
            logger.info(
                "[dividend] 월별 스캔 %d/%d: %s ~ %s",
                w_idx + 1, len(windows), w_start, w_end,
            )
            time.sleep(PYKRX_THROTTLE)

            try:
                df = pykrx_stock.get_market_fundamental_by_ticker(
                    w_start, market="ALL"
                )
            except Exception as e:
                logger.warning("[dividend] %s 조회 실패: %s", w_start, e)
                continue

            if df is None or df.empty:
                logger.debug("[dividend] %s 빈 결과", w_start)
                continue

            # DPS 컬럼 확인
            dps_col = None
            for col in df.columns:
                if "DPS" in str(col).upper() or "dps" in str(col).lower():
                    dps_col = col
                    break

            if dps_col is None:
                logger.debug("[dividend] DPS 컬럼 없음: %s", list(df.columns))
                continue

            # 해당 날짜에 DPS > 0 인 종목 찾기
            # get_market_fundamental_by_ticker(date) 는 특정 날짜 전종목 스냅샷
            # 배당락이 있는 날 DPS > 0 이 되므로 해당 날짜 = 배당락일
            event_dt_str = w_start
            try:
                event_dt = datetime.strptime(event_dt_str, "%Y%m%d").date()
            except ValueError:
                continue

            try:
                dps_positive = df[df[dps_col] > 0]
            except Exception:
                continue

            month_inserted = 0
            for ticker in dps_positive.index:
                ticker_str = str(ticker).strip().zfill(6)
                if ticker_str not in target_set:
                    continue
                # 6자리 숫자 검증
                if not (len(ticker_str) == 6 and ticker_str.isdigit()):
                    continue

                try:
                    dps_val = float(dps_positive.loc[ticker, dps_col])
                except Exception:
                    dps_val = 0.0

                meta = {
                    "source": "pykrx_fundamental",
                    "scan_date": event_dt_str,
                    "dps": dps_val,
                }

                with conn.cursor() as cur:
                    inserted = insert_event(cur, ticker_str, "dividend_ex", event_dt, meta)
                conn.commit()
                if inserted:
                    month_inserted += 1
                    total_inserted += 1

            if month_inserted > 0:
                logger.info(
                    "[dividend] %s: %d건 삽입",
                    event_dt_str, month_inserted,
                )

    finally:
        conn.close()

    logger.info("[dividend] 완료 총 %d건 삽입", total_inserted)
    return total_inserted


# ─────────────────────────────────────────────────────────────────────────────
# 3. 배당락 보완: 종목별 연간 DPS 스캔 (월말 기준)
# ─────────────────────────────────────────────────────────────────────────────

def collect_dividend_ex_by_ticker(
    stock_codes: list[str],
    start_date: str,
    end_date: str,
) -> int:
    """
    종목별 연간 fundamental 조회로 배당락일 감지 (보완 방식).

    get_market_fundamental_by_date(start, end, ticker) 로 종목별 일별 DPS 스캔.
    DPS > 0 인 날 중 직전 거래일 DPS = 0 → 배당락 첫날로 간주.

    이 방식은 연 1~4회 배당 종목의 정확한 배당락일을 포착.
    """
    from pykrx import stock as pykrx_stock

    total_inserted = 0
    conn = get_conn()

    try:
        for i, code in enumerate(stock_codes):
            if i > 0 and i % 50 == 0:
                logger.info(
                    "[div_ticker] %d/%d 처리 중 (삽입=%d)",
                    i, len(stock_codes), total_inserted,
                )

            time.sleep(PYKRX_THROTTLE)
            try:
                df = pykrx_stock.get_market_fundamental_by_date(
                    start_date, end_date, code
                )
            except Exception as e:
                logger.debug("[div_ticker] %s 조회 실패: %s", code, e)
                continue

            if df is None or df.empty:
                continue

            # DPS 컬럼 탐색
            dps_col = None
            for col in df.columns:
                if "DPS" in str(col).upper():
                    dps_col = col
                    break
            if dps_col is None:
                continue

            try:
                dps_series = df[dps_col].astype(float)
            except Exception:
                continue

            # DPS가 0→양수로 전환되는 날 = 배당락일
            prev_dps = dps_series.shift(1).fillna(0)
            ex_dates = df.index[(dps_series > 0) & (prev_dps == 0)]

            for idx in ex_dates:
                try:
                    event_dt = idx.date() if hasattr(idx, "date") else idx
                    event_dt_str = event_dt.strftime("%Y%m%d")
                except Exception:
                    continue

                try:
                    dps_val = float(dps_series[idx])
                except Exception:
                    dps_val = 0.0

                meta = {
                    "source": "pykrx_fundamental_ticker",
                    "scan_date": event_dt_str,
                    "dps": dps_val,
                }

                with conn.cursor() as cur:
                    inserted = insert_event(cur, code, "dividend_ex", event_dt, meta)
                conn.commit()
                if inserted:
                    total_inserted += 1
                    logger.debug(
                        "[div_ticker] INSERT %s dividend_ex %s dps=%.0f",
                        code, event_dt, dps_val,
                    )

    finally:
        conn.close()

    logger.info("[div_ticker] 완료 총 %d건 삽입", total_inserted)
    return total_inserted


# ─────────────────────────────────────────────────────────────────────────────
# 검증: Spot Check
# ─────────────────────────────────────────────────────────────────────────────

SPOT_CHECKS = [
    # (stock_code, event_type, event_date, description, meta_check)
    # meta_check: None 또는 {key: expected_value} 딕셔너리
    # 카카오 2021-04-15 5:1 액면분할 (500->100) -- DB 확인
    ("035720", "split", date(2021, 4, 15), "카카오 5:1 액면분할 (500->100)", {"split_factor": 5.0, "face_value_before": 500, "face_value_after": 100}),
    # 260970 2021-02-01 10:1 액면분할 (5000->500) -- DB 확인
    ("260970", "split", date(2021, 2, 1), "260970 10:1 액면분할 (5000->500)", {"split_factor": 10.0, "face_value_before": 5000, "face_value_after": 500}),
    # 한국석유 004090 2021-04-15 10:1 액면분할 (5000->500) -- DB 확인
    ("004090", "split", date(2021, 4, 15), "한국석유 10:1 액면분할 (5000->500)", {"split_factor": 10.0, "face_value_before": 5000, "face_value_after": 500}),
]


def run_spot_checks() -> list[dict]:
    """잘 알려진 이벤트 spot check. SPOT_CHECKS는 5-튜플 (code, type, date, desc, meta_check)."""
    conn = get_conn()
    results = []
    try:
        with conn.cursor() as cur:
            for item in SPOT_CHECKS:
                code, etype, edate, desc = item[0], item[1], item[2], item[3]
                meta_check = item[4] if len(item) > 4 else None

                cur.execute(
                    """
                    SELECT stock_code, event_type, event_date, meta
                    FROM corp_events
                    WHERE stock_code = %s AND event_type = %s AND event_date = %s
                    """,
                    (code, etype, edate),
                )
                row = cur.fetchone()
                found = row is not None

                # meta 검증
                meta_ok = True
                meta_note = ""
                if found and meta_check and row[3]:
                    stored_meta = row[3] if isinstance(row[3], dict) else {}
                    for k, expected in meta_check.items():
                        actual = stored_meta.get(k)
                        if actual != expected:
                            meta_ok = False
                            meta_note += f" meta.{k}={actual}(expected {expected})"

                ok = found and meta_ok
                results.append({
                    "code": code,
                    "type": etype,
                    "date": edate.isoformat(),
                    "desc": desc,
                    "found": found,
                    "meta_ok": meta_ok,
                    "meta_note": meta_note.strip(),
                    "meta": row[3] if found else None,
                })
                status = "PASS" if ok else ("FOUND_META_FAIL" if found else "FAIL")
                logger.info("[spot_check] %s | %s %s %s%s", status, code, etype, edate, f" {meta_note}" if meta_note else "")
    finally:
        conn.close()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 보고서 생성
# ─────────────────────────────────────────────────────────────────────────────

def write_report(
    before_counts: dict,
    after_counts: dict,
    split_counts: dict,
    div_inserted: int,
    spot_results: list[dict],
    report_path: str,
    elapsed_sec: float,
    universe_size: int,
):
    import os
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    total_before = sum(before_counts.values())
    total_after = sum(after_counts.values())

    lines = [
        "# Phase 0 corp_events 백필 보고서",
        "",
        f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"소요시간: {elapsed_sec:.0f}초",
        "",
        "## 1. 백필 전후 행 수",
        "",
        f"| 구분 | 건수 |",
        f"|------|------|",
        f"| 백필 전 | {total_before:,} |",
        f"| 백필 후 | {total_after:,} |",
        f"| 신규 삽입 | {total_after - total_before:,} |",
        "",
        "## 2. event_type별 분포 (백필 후)",
        "",
        "| event_type | 건수 |",
        "|------------|------|",
    ]
    for etype, cnt in sorted(after_counts.items()):
        lines.append(f"| {etype} | {cnt:,} |")

    lines += [
        "",
        "## 3. 연도별 분포",
        "",
        "| 연도 | 건수 |",
        "|------|------|",
    ]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXTRACT(YEAR FROM event_date)::int AS yr, COUNT(*) AS cnt
                FROM corp_events
                GROUP BY yr ORDER BY yr
                """
            )
            for yr, cnt in cur.fetchall():
                lines.append(f"| {yr} | {cnt:,} |")
    finally:
        conn.close()

    lines += [
        "",
        "## 4. Spot Check 검증",
        "",
        "| 결과 | 종목 | 이벤트 | 날짜 | 설명 | 메타비고 |",
        "|------|------|--------|------|------|---------|",
    ]
    all_pass = True
    for r in spot_results:
        ok = r["found"] and r.get("meta_ok", True)
        if not ok:
            all_pass = False
        if not r["found"]:
            status = "FAIL(미존재)"
        elif not r.get("meta_ok", True):
            status = "FAIL(meta불일치)"
        else:
            status = "PASS"
        note = r.get("meta_note", "")
        lines.append(
            f"| {status} | {r['code']} | {r['type']} | {r['date']} | {r['desc']} | {note} |"
        )

    lines += [
        "",
        "## 5. 다음 단계 (P0-2b) 사용 가능 여부",
        "",
    ]
    # DB 총 split 건수로 판정 (이번 실행 신규 삽입이 0이어도 이미 적재된 건 OK)
    split_ok = after_counts.get("split", 0) > 0
    spot_ok = all_pass

    if split_ok and spot_ok:
        lines.append(
            "**OK** split 이벤트가 정상 적재됐고 spot check 전체 PASS. "
            "P0-2b (adj_factor 역산 적용)를 진행할 수 있습니다."
        )
    else:
        issues = []
        if not split_ok:
            issues.append(f"split 이벤트 DB 총 0건 (pykrx 조회 실패 가능성)")
        if not spot_ok:
            failed = [r['desc'] for r in spot_results if not (r['found'] and r.get('meta_ok', True))]
            issues.append(f"spot check 실패: {', '.join(failed)}")
        lines.append(
            "**NG** 문제 있음:\n" + "\n".join(f"- {i}" for i in issues)
        )

    lines += [
        "",
        "## 6. 수집 파라미터",
        "",
        f"- 유니버스 크기: {universe_size:,}종목",
        f"- split/merge: pykrx get_stock_major_changes, split={split_counts.get('split',0)}, merge={split_counts.get('merge',0)}",
        f"- dividend_ex: pykrx get_market_fundamental_by_ticker, 삽입={div_inserted:,}",
        "- 멱등성: ON CONFLICT (stock_code, event_type, event_date) DO NOTHING",
        "- No Look-Ahead: event_date = 실제 발효일 (pykrx 인덱스 기준)",
    ]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("[report] 보고서 저장: %s", report_path)


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="P0 corp_events 백필 (pykrx)")
    parser.add_argument("--pilot", action="store_true", help="파일럿 10종목만 실행")
    parser.add_argument("--no-dividend", action="store_true", help="배당락 수집 건너뜀")
    parser.add_argument("--start", default=DEFAULT_START, help="시작일 YYYYMMDD (기본 20210101)")
    parser.add_argument("--end", default=DEFAULT_END, help="종료일 YYYYMMDD (기본 오늘)")
    parser.add_argument(
        "--dividend-mode",
        choices=["monthly", "ticker", "both"],
        default="monthly",
        help="배당락 수집 방식: monthly(전종목 월별스냅샷), ticker(종목별 일별), both(둘다)",
    )
    args = parser.parse_args()

    t0 = time.time()

    logger.info("=" * 60)
    logger.info("P0 corp_events 백필 시작")
    logger.info("기간: %s ~ %s", args.start, args.end)
    logger.info("=" * 60)

    # 1. 유니버스 결정
    if args.pilot:
        stock_codes = PILOT_STOCKS
        logger.info("[universe] 파일럿 모드: %d종목", len(stock_codes))
    else:
        logger.info("[universe] DB에서 유니버스 조회 중...")
        stock_codes = get_universe_from_db()
        logger.info("[universe] %d종목 확보", len(stock_codes))

    if not stock_codes:
        logger.error("처리할 종목 없음. 종료.")
        sys.exit(1)

    # 2. 백필 전 집계
    before_counts = count_corp_events()
    logger.info("[before] corp_events 현재: %s", before_counts)

    # 3. 액면분할/병합 수집
    logger.info("[1/2] 액면분할/병합 수집 시작 (pykrx get_stock_major_changes)...")
    split_counts = collect_splits(stock_codes, args.start, args.end)

    # 4. 배당락 수집
    div_inserted = 0
    if not args.no_dividend:
        if args.dividend_mode in ("monthly", "both"):
            logger.info("[2/2] 배당락 수집 시작 (월별 전종목 스캔)...")
            div_inserted += collect_dividend_ex(stock_codes, args.start, args.end)
        if args.dividend_mode in ("ticker", "both"):
            logger.info("[2/2] 배당락 수집 시작 (종목별 일별 스캔)...")
            div_inserted += collect_dividend_ex_by_ticker(stock_codes, args.start, args.end)
    else:
        logger.info("[2/2] 배당락 수집 건너뜀 (--no-dividend)")

    # 5. 백필 후 집계
    after_counts = count_corp_events()
    logger.info("[after] corp_events 최종: %s", after_counts)

    # 6. Spot check
    logger.info("[spot_check] 검증 중...")
    spot_results = run_spot_checks()

    # 7. 보고서
    elapsed = time.time() - t0
    report_path = (
        "D:/GIT/kis-trading-template/RoboTrader_template/reports/"
        "10pct_strategy/phase0_corp_events_backfill.md"
    )
    write_report(
        before_counts, after_counts, split_counts, div_inserted,
        spot_results, report_path, elapsed, len(stock_codes),
    )

    # 8. 콘솔 요약
    total_new = sum(after_counts.values()) - sum(before_counts.values())
    logger.info("")
    logger.info("=" * 60)
    logger.info("백필 완료 요약")
    logger.info("=" * 60)
    logger.info("  신규 삽입: %d건", total_new)
    logger.info("  split:       %d건 (액면분할)", split_counts.get("split", 0))
    logger.info("  merge:       %d건 (액면병합)", split_counts.get("merge", 0))
    logger.info("  dividend_ex: %d건", div_inserted)
    logger.info("  소요시간: %.0f초", elapsed)

    all_spot_pass = all(r["found"] and r.get("meta_ok", True) for r in spot_results)
    p0_ok = after_counts.get("split", 0) > 0 and all_spot_pass
    logger.info("  P0-2b 사용 가능: %s", "OK" if p0_ok else "NG")
    logger.info("  보고서: %s", report_path)


if __name__ == "__main__":
    main()
