"""
analyze_morning_5pct_spikes.py
==============================
2026년 4~5월 장 시작 후 3시간 윈도우(09:00~12:00) 내에
running-min-low 대비 이후 고점이 5% 이상 상승한 케이스를 추출합니다.

"5% 이상 상승" 정의:
  - 09:00~12:00 윈도우에서 각 분봉마다 그 시점까지의 누적 최저가(running_min_low) 추적
  - 그 이후 any 분봉의 high / running_min_low >= 1.05 이면 포착

출력:
  - CSV: RoboTrader_template/reports/morning_5pct_spikes_aprmay/spikes.csv
  - 콘솔 요약 (총 케이스, 상위 30개 등)

사용법:
  cd RoboTrader_template
  python scripts/analyze_morning_5pct_spikes.py
"""

import csv
import os
import sys
import time
from pathlib import Path

import psycopg2

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPORT_DIR = PROJECT_ROOT / "reports" / "morning_5pct_spikes_aprmay"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_CSV = REPORT_DIR / "spikes.csv"

# ---------------------------------------------------------------------------
# DB 연결 설정 (db/connection.py 기본값과 동일)
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    "port": int(os.getenv("TIMESCALE_PORT", 5433)),
    "database": os.getenv("TIMESCALE_DB", "robotrader"),
    "user": os.getenv("TIMESCALE_USER", "robotrader"),
    "password": os.getenv("TIMESCALE_PASSWORD", "1234"),
}

# ---------------------------------------------------------------------------
# SQL 정의
# ---------------------------------------------------------------------------

# Step 1: 종목 × 거래일별 peak_ratio 계산 (running min low 기반)
# time 컬럼은 'HHMMSS' 형식이므로 문자열 비교로 필터
SQL_PEAKS = """
WITH win AS (
    SELECT
        stock_code,
        trade_date,
        time,
        open,
        high,
        low,
        close,
        MIN(low) OVER (
            PARTITION BY stock_code, trade_date
            ORDER BY time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_min_low
    FROM minute_candles
    WHERE trade_date BETWEEN '20260401' AND '20260523'
      AND time >= '090000'
      AND time < '120000'
),
ratios AS (
    SELECT
        stock_code,
        trade_date,
        time,
        high,
        running_min_low,
        CASE
            WHEN running_min_low > 0
            THEN high / running_min_low
            ELSE NULL
        END AS ratio
    FROM win
),
peaks AS (
    SELECT
        stock_code,
        trade_date,
        MAX(ratio) AS peak_ratio
    FROM ratios
    GROUP BY stock_code, trade_date
)
SELECT stock_code, trade_date, peak_ratio
FROM peaks
WHERE peak_ratio >= 1.05
ORDER BY trade_date ASC, peak_ratio DESC
"""

# Step 2: 각 케이스의 저점(running_min_low 최소 시점) 및 고점 시각·가격 상세
# peak_ratio를 달성한 케이스들의 low_time, low_price, high_time, high_price 추출
SQL_DETAILS = """
WITH win AS (
    SELECT
        stock_code,
        trade_date,
        time,
        open,
        high,
        low,
        close,
        MIN(low) OVER (
            PARTITION BY stock_code, trade_date
            ORDER BY time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_min_low
    FROM minute_candles
    WHERE trade_date BETWEEN '20260401' AND '20260523'
      AND time >= '090000'
      AND time < '120000'
),
ratios AS (
    SELECT
        stock_code,
        trade_date,
        time,
        high,
        low,
        open,
        close,
        running_min_low,
        CASE
            WHEN running_min_low > 0 THEN high / running_min_low
            ELSE NULL
        END AS ratio
    FROM win
),
-- 종목×날짜별 peak_ratio 행 (중복 있을 수 있으므로 DISTINCT ON 사용)
peak_rows AS (
    SELECT DISTINCT ON (stock_code, trade_date)
        stock_code,
        trade_date,
        time      AS high_time,
        high      AS high_price,
        ratio     AS peak_ratio
    FROM ratios
    WHERE ratio >= 1.05
    ORDER BY stock_code, trade_date, ratio DESC, time ASC
),
-- running_min_low 최솟값이 처음 나타나는 시각 = 저점 시각
-- (peak_ratio를 달성한 high_time 이전의 running_min_low와 같은 값)
-- 각 케이스별: running_min_low = peak_ratio 행의 high / peak_ratio
low_finder AS (
    SELECT
        r.stock_code,
        r.trade_date,
        pr.high_time,
        pr.high_price,
        pr.peak_ratio,
        -- running_min_low 값 = high_price / peak_ratio
        pr.high_price / pr.peak_ratio AS target_low,
        -- 저점 시각: running_min_low 가 target_low에 처음 도달한 시각
        -- (즉 실제 low가 target_low인 첫 번째 분봉)
        MIN(CASE
            WHEN ABS(r.running_min_low - pr.high_price / pr.peak_ratio) < 0.5
            THEN r.time
            ELSE NULL
        END) AS low_time_approx
    FROM ratios r
    JOIN peak_rows pr
      ON r.stock_code = pr.stock_code
     AND r.trade_date = pr.trade_date
     AND r.time <= pr.high_time
    GROUP BY r.stock_code, r.trade_date, pr.high_time, pr.high_price, pr.peak_ratio
),
-- 09:00 시가(첫 분봉 open)와 12:00 직전 close
open_close AS (
    SELECT
        stock_code,
        trade_date,
        FIRST_VALUE(open) OVER (
            PARTITION BY stock_code, trade_date ORDER BY time
        ) AS open_09,
        LAST_VALUE(close) OVER (
            PARTITION BY stock_code, trade_date ORDER BY time
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS close_12
    FROM win
)
SELECT DISTINCT ON (lf.stock_code, lf.trade_date)
    lf.stock_code,
    lf.trade_date,
    lf.low_time_approx                        AS low_time,
    ROUND((lf.target_low)::numeric, 0)        AS low_price,
    lf.high_time,
    lf.high_price,
    ROUND(((lf.peak_ratio - 1) * 100)::numeric, 2) AS rise_pct,
    oc.open_09,
    oc.close_12
FROM low_finder lf
JOIN open_close oc
  ON lf.stock_code = oc.stock_code
 AND lf.trade_date = oc.trade_date
ORDER BY lf.stock_code, lf.trade_date
"""

# Step 3: 종목명 조회 (candidate_stocks + screener_snapshots 합산)
SQL_NAMES = """
SELECT stock_code, stock_name
FROM (
    SELECT DISTINCT ON (stock_code) stock_code, stock_name
    FROM (
        SELECT stock_code, stock_name FROM candidate_stocks WHERE stock_name IS NOT NULL
        UNION ALL
        SELECT stock_code, stock_name FROM screener_snapshots WHERE stock_name IS NOT NULL
        UNION ALL
        SELECT stock_code, stock_name FROM virtual_trading_records WHERE stock_name IS NOT NULL
    ) combined
    ORDER BY stock_code
) deduped
"""

# Day-level open/close (full day: first open, last close)
SQL_DAY_OHLC = """
SELECT
    stock_code,
    trade_date,
    FIRST_VALUE(open) OVER (
        PARTITION BY stock_code, trade_date ORDER BY time
    ) AS day_open,
    LAST_VALUE(close) OVER (
        PARTITION BY stock_code, trade_date ORDER BY time
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS day_close
FROM minute_candles
WHERE trade_date BETWEEN '20260401' AND '20260523'
"""


def fmt_time(t: str) -> str:
    """'HHMMSS' -> 'HH:MM'"""
    if not t or len(t) < 4:
        return t or ""
    return f"{t[:2]}:{t[2:4]}"


def bar(count: int, total: int, width: int = 30) -> str:
    filled = int(width * count / total) if total else 0
    return "#" * filled + "-" * (width - filled)


def main() -> None:
    t0 = time.time()

    print("=" * 70)
    print("  장중 5% 상승 케이스 추출 (2026-04 ~ 2026-05, 09:00~12:00)")
    print("=" * 70)

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # 1) 종목명 사전 로드
    # ------------------------------------------------------------------
    print("[1/4] 종목명 사전 로드 중...")
    cur.execute(SQL_NAMES)
    name_map: dict[str, str] = {row[0]: row[1] for row in cur.fetchall()}
    print(f"      {len(name_map):,}개 종목명 로드 완료")

    # ------------------------------------------------------------------
    # 2) 케이스별 상세 추출 (running min + peak ratio + 저점/고점 시각)
    # ------------------------------------------------------------------
    print("[2/4] 케이스별 상세 분석 중... (수십 초 소요 예상)")
    cur.execute(SQL_DETAILS)
    rows = cur.fetchall()
    # cols: stock_code, trade_date, low_time, low_price, high_time, high_price,
    #       rise_pct, open_09, close_12
    print(f"      {len(rows):,}개 케이스 추출 완료")

    # ------------------------------------------------------------------
    # 3) 전일 open/close (day_open, day_close)
    #    minute_candles 전체 일자의 첫 open / 마지막 close
    # ------------------------------------------------------------------
    print("[3/4] 일별 전체 시가/종가 로드 중...")
    cur.execute(SQL_DAY_OHLC)
    day_ohlc: dict[tuple, tuple] = {}
    for r in cur.fetchall():
        key = (r[0], r[1])
        if key not in day_ohlc:
            day_ohlc[key] = (r[2], r[3])  # day_open, day_close

    conn.close()

    # ------------------------------------------------------------------
    # 4) 결과 조합 + CSV 저장
    # ------------------------------------------------------------------
    print("[4/4] CSV 저장 중...")

    CSV_COLS = [
        "trade_date", "stock_code", "stock_name",
        "open_09", "low_time", "low_price",
        "high_time", "high_price", "rise_pct",
        "close_12", "day_open", "day_close",
    ]

    records = []
    for row in rows:
        stock_code, trade_date, low_time, low_price, high_time, high_price, \
            rise_pct, open_09, close_12 = row

        stock_name = name_map.get(stock_code, "")
        day_open, day_close = day_ohlc.get((stock_code, trade_date), ("", ""))

        records.append({
            "trade_date": trade_date,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "open_09": round(float(open_09), 0) if open_09 else "",
            "low_time": fmt_time(low_time) if low_time else "",
            "low_price": round(float(low_price), 0) if low_price else "",
            "high_time": fmt_time(high_time) if high_time else "",
            "high_price": round(float(high_price), 0) if high_price else "",
            "rise_pct": round(float(rise_pct), 2) if rise_pct else "",
            "close_12": round(float(close_12), 0) if close_12 else "",
            "day_open": round(float(day_open), 0) if day_open else "",
            "day_close": round(float(day_close), 0) if day_close else "",
        })

    # 정렬: trade_date ASC, rise_pct DESC
    records.sort(key=lambda r: (r["trade_date"], -float(r["rise_pct"] or 0)))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLS)
        writer.writeheader()
        writer.writerows(records)

    elapsed = time.time() - t0

    # ------------------------------------------------------------------
    # 콘솔 요약
    # ------------------------------------------------------------------
    total_cases = len(records)
    unique_codes = len({r["stock_code"] for r in records})
    unique_dates = len({r["trade_date"] for r in records})

    print()
    print("=" * 70)
    print("  분석 결과 요약")
    print("=" * 70)
    print(f"  실행 시간    : {elapsed:.1f}초")
    print(f"  총 케이스    : {total_cases:,}건")
    print(f"  고유 종목 수 : {unique_codes:,}개")
    print(f"  거래일 수    : {unique_dates}일")
    print()

    # 일자별 케이스 수 막대 (텍스트)
    from collections import Counter
    date_counts = Counter(r["trade_date"] for r in records)
    max_cnt = max(date_counts.values()) if date_counts else 1
    print("  [일자별 케이스 수]")
    for d in sorted(date_counts):
        cnt = date_counts[d]
        formatted = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        b = bar(cnt, max_cnt, width=30)
        print(f"    {formatted}  {b}  {cnt}")
    print()

    # 상승률 분포
    def bucket(pct: float) -> str:
        if pct < 10:
            return "5~10%"
        elif pct < 20:
            return "10~20%"
        elif pct < 30:
            return "20~30%"
        else:
            return "30%+"

    dist: Counter = Counter()
    for r in records:
        pct = float(r["rise_pct"] or 0)
        dist[bucket(pct)] += 1

    print("  [상승률 분포]")
    for label in ["5~10%", "10~20%", "20~30%", "30%+"]:
        cnt = dist.get(label, 0)
        pct_share = cnt / total_cases * 100 if total_cases else 0
        print(f"    {label:<8}  {cnt:5,}건  ({pct_share:5.1f}%)")
    print()

    # 상위 30개 케이스
    top30 = sorted(records, key=lambda r: -float(r["rise_pct"] or 0))[:30]
    print("  [상위 30개 케이스 (상승률 기준)]")
    header = (
        f"  {'날짜':<10}  {'종목코드':<8}  {'종목명':<12}  "
        f"{'저점시각':<6}  {'저점가':>8}  {'고점시각':<6}  {'고점가':>8}  {'상승률':>7}"
    )
    print(header)
    print("  " + "-" * 78)
    for r in top30:
        name = r["stock_name"][:10] if r["stock_name"] else ""
        date_fmt = f"{r['trade_date'][:4]}-{r['trade_date'][4:6]}-{r['trade_date'][6:]}"
        print(
            f"  {date_fmt:<10}  {r['stock_code']:<8}  {name:<12}  "
            f"{r['low_time']:<6}  {r['low_price']:>8,.0f}  "
            f"{r['high_time']:<6}  {r['high_price']:>8,.0f}  "
            f"{r['rise_pct']:>6.2f}%"
        )

    print()
    print(f"  CSV 저장 위치: {OUTPUT_CSV}")
    print("=" * 70)


if __name__ == "__main__":
    main()
