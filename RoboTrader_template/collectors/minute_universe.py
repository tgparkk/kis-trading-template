# collectors/minute_universe.py
"""분봉 유니버스 — 거래대금순(fid_blng_cls_code=3) top300, 6가격밴드×2시장
+ 태쏘 shadow 후보(후보가 된 날부터 20거래일).

2026-09-29: 🔒 사장님 결정 — 분봉 저장 범위 = 「거래대금 top300 + 태쏘 shadow 후보」.
  후보는 `tasso_shadow.candidates` 의 `in_ra OR in_rb`(arm 무관) · `scan_date` 가
  오늘 기준 최근 20거래일 안. 이 표는 태쏘 러너(별도 워크트리)가 쓰고 여기선 SELECT 만 한다.

2026-10-01: 🔒 사전등록 `docs/prereg_2026-10-01_minute_universe_focus3_candidates.md` v1.0 —
  3전략(ma20·daytrading·minervini) 룰 통과 후보(`screener_snapshots` · SELECT 만)를 21거래일 창으로 추가.
  수집 루프는 `minute_collector.collect_minute` 의 focus3 전용 루프(보충 없음 · 태쏘와 섞지 않음).
"""
import time
from datetime import datetime

from api import kis_market_api
from utils.korean_holidays import get_previous_trading_day
from utils.logger import setup_logger

logger = setup_logger(__name__)

PRICE_BANDS = [
    ("5000", "15000"), ("15000", "30000"), ("30000", "60000"),
    ("60000", "120000"), ("120000", "250000"), ("250000", "500000"),
]
MARKETS = ["0001", "1001"]  # KOSPI, KOSDAQ

# 태쏘 후보를 분봉 저장에 붙여 두는 기간 — 후보가 된 날(scan_date)을 1일째로 센다.
TASSO_WINDOW_DAYS = 20

# 창 안에서 한 번이라도 후보(in_ra OR in_rb)였던 종목 — 첫 후보일과 함께.
# 순서 = 가장 최근 후보일 먼저 → 결손일 보충이 같은 날짜 안에선 새 후보부터 받는다.
_TASSO_SQL = """
SELECT stock_code, min(scan_date)
FROM tasso_shadow.candidates
WHERE (in_ra OR in_rb) AND scan_date BETWEEN %s AND %s
GROUP BY stock_code
ORDER BY max(scan_date) DESC, stock_code
"""

# 3전략 후보를 분봉 저장에 붙여 두는 기간 — 오늘을 1일째로 센다(tasso_window_start 재사용).
# 스냅샷 scan_date 는 T−1 이라 21 이면 매수일(scan_date 다음 거래일)부터 20거래일을 덮는다
# (minervini max_hold_days 20 · 사전등록 §7 결정 1(a)).
# 🔒 마스터 스위치 — 0 이면 focus3 조회·수집을 통째로 끈다(롤백 = 이 줄 하나 · 사전등록 §6).
FOCUS3_WINDOW_DAYS = 21

# 창 안에서 한 번이라도 룰 통과 후보였던 3전략 종목 — 첫 후보일과 함께(순서는 태쏘 SQL 과 같다).
# 3전략만(§7 결정 3(a)) — 나머지 5전략은 «관측만» 결정이라 넣지 않는다.
_FOCUS3_SQL = """
SELECT stock_code, min(scan_date)
FROM screener_snapshots
WHERE strategy IN ('book_pullback_ma20', 'daytrading_3methods_breakout', 'minervini_volume_dryup')
  AND scan_date BETWEEN %s AND %s
GROUP BY stock_code
ORDER BY max(scan_date) DESC, stock_code
"""


def parse_rank_codes(df) -> list:
    if df is None or len(df) == 0:
        return []
    out = []
    for _, row in df.iterrows():
        code = str(row.get("mksc_shrn_iscd", "")).strip()
        if len(code) == 6 and code.isdigit() and not code.endswith("5"):
            out.append(code)
    return out


def select_top_volume(top_n: int = 300) -> list:
    """거래대금순으로 6밴드×2시장 수집→등장순(=대금상위) dedup→top_n."""
    seen = []
    seen_set = set()
    for market in MARKETS:
        for lo, hi in PRICE_BANDS:
            df = kis_market_api.get_volume_rank(
                fid_input_iscd=market, fid_div_cls_code="1",
                fid_blng_cls_code="3", fid_input_price_1=lo, fid_input_price_2=hi)
            for code in parse_rank_codes(df):
                if code not in seen_set:
                    seen_set.add(code); seen.append(code)
            time.sleep(0.08)
    return seen[:top_n]


def tasso_window_start(today, n: int = TASSO_WINDOW_DAYS):
    """today 를 1일째로 세어 n 거래일째 되는 과거 날(창의 첫날). 휴장일은 건너뛴다."""
    d = datetime(today.year, today.month, today.day)
    for _ in range(n - 1):
        d = get_previous_trading_day(d)
    return d.date()


def select_tasso_codes(conn, today):
    """창 [today 기준 20거래일 첫날, today] 의 태쏘 후보 → (window_from, [(stock_code, 첫 후보일), ...]).

    🔑 실패(창 계산·스키마 없음·권한·연결)는 WARNING 한 줄 + 목록 자리에 ``None`` — 호출측은
       top300 만으로 계속한다(EOD 비차단). 빈 목록(후보 0)과 구분하려고 None 을 쓴다.
    🔑 코드는 거르지 않는다 — 태쏘 후보엔 영숫자 코드(예 ``0039P0``)가 있어
       top300 의 숫자 6자리 필터(parse_rank_codes)를 걸면 조용히 빠진다.
    """
    window_from = None
    try:
        window_from = tasso_window_start(today)
        with conn.cursor() as cur:
            cur.execute(_TASSO_SQL, (window_from, today))
            rows = cur.fetchall()
        conn.rollback()  # 읽기 전용 — 스냅샷을 쥔 채 수집 루프로 들어가지 않는다
        # strip 뒤엔 GROUP BY 가 가른 두 값이 같은 코드가 될 수 있다 — 순서 유지 dedup · 첫 후보일은 min.
        out = {}
        for code, first in rows:
            code = str(code).strip()
            out[code] = min(out[code], first) if code in out else first
        return window_from, list(out.items())
    except Exception as e:  # noqa: BLE001 — 태쏘 조회 실패가 top300 수집을 막으면 안 된다
        try:
            conn.rollback()  # 실패한 트랜잭션을 풀어야 같은 연결로 적재가 된다
        except Exception:  # noqa: BLE001
            pass
        logger.warning(f"[minute] 태쏘 후보 조회 실패 — top300 만 수집: {type(e).__name__}: {e}")
        return window_from, None


def select_focus3_codes(conn, today, n: int = FOCUS3_WINDOW_DAYS):
    """창 [today 기준 n거래일 첫날, today] 의 3전략 후보 → (window_from, [(stock_code, 첫 후보일), ...]).

    select_tasso_codes 와 같은 계약 — 실패는 WARNING 한 줄 + 목록 자리에 ``None``(호출측은 계속) ·
    읽기 전용(rollback) · 코드는 거르지 않는다(3전략 스냅샷에도 영숫자 코드 ``0004V0`` 등이 있다).
    scan_date=오늘 행은 내일 09:00 에야 생기므로 창 끝이 today 여도 0건이라 무해하다.
    """
    window_from = None
    try:
        window_from = tasso_window_start(today, n)
        with conn.cursor() as cur:
            cur.execute(_FOCUS3_SQL, (window_from, today))
            rows = cur.fetchall()
        conn.rollback()  # 읽기 전용 — 스냅샷을 쥔 채 수집 루프로 들어가지 않는다
        out = {}
        for code, first in rows:
            code = str(code).strip()
            out[code] = min(out[code], first) if code in out else first
        return window_from, list(out.items())
    except Exception as e:  # noqa: BLE001 — focus3 조회 실패가 top300·태쏘 수집을 막으면 안 된다
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning(f"[minute] focus3 후보 조회 실패 — top300·태쏘만 수집: {type(e).__name__}: {e}")
        return window_from, None
