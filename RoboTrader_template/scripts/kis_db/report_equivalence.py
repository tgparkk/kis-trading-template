"""시장데이터 정합 검증(오프라인, READ-only). kis_template vs 현 라이브 소스.

- daily: kis_template.daily_prices vs robotrader_quant.daily_prices
- minute: kis_template.minute_candles vs robotrader.minute_candles (표본 거래일)
게이트 = "모든 diff 가 설명됨"(분할조정 = kis 개선 = 통과 사유), "제로 diff" 아님.
미설명 diff 가 1건이라도 있으면 FAIL. 어떤 DB 에도 쓰지 않는다.

usage:
  python -m scripts.kis_db.report_equivalence                 # 최근 거래일 자동
  python -m scripts.kis_db.report_equivalence --date 2026-07-03
"""
import argparse
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402

# 분할/병합으로 설명 가능한 정수비 범위 (collectors/split_factor_infer.py 와 일관).
# 고정 배수 집합이 아니라 "정수에 가까운 비율"을 일반 검출한다 → 11(001130 검증된
# 1:11 분할), 15 등 임의 정수비와 2.5(단주/액면) 모두 설명 가능.
SPLIT_RATIO_MIN = 2
SPLIT_RATIO_MAX = 150
MAX_UNEXPLAINED_SAMPLES = 20


def classify_diff(legacy, new, tol: float = 0.005) -> str:
    """단일 종목 종가 diff 분류.

    match: 상대오차 < tol
    split_adjust: ratio=max/min 이 정수(2..150) 또는 2.5 에 상대오차 tol 이내로 근접
        (kis 가 분할조정을 정확히 반영한 개선 — 001130 1:11 등). split_factor_infer 와 일관.
    coverage_gap: 한쪽 값 없음(None/0)
    unexplained: 그 외(예: 1.23x 불규칙)
    """
    if legacy is None or new is None or legacy == 0 or new == 0:
        return "coverage_gap"
    legacy = float(legacy)
    new = float(new)
    if abs(new - legacy) / legacy < tol:
        return "match"
    hi = max(legacy, new)
    lo = min(legacy, new)
    ratio = hi / lo  # >= 1
    nearest = round(ratio)
    if SPLIT_RATIO_MIN <= nearest <= SPLIT_RATIO_MAX and abs(ratio - nearest) <= ratio * tol:
        return "split_adjust"
    if abs(ratio - 2.5) <= 2.5 * tol:  # 단주/액면 2.5 배 분할
        return "split_adjust"
    return "unexplained"


def build_equivalence_report(dataset: str, legacy_map: dict, new_map: dict,
                             tol: float = 0.005) -> dict:
    """순수 함수: 레거시/신규 {code: close} 맵을 분류 집계한 리포트를 반환."""
    counts = {"match": 0, "split_adjust": 0, "coverage_gap": 0, "unexplained": 0}
    unexplained_samples = []
    codes = set(legacy_map) | set(new_map)
    covered = 0
    for code in codes:
        lv = legacy_map.get(code)
        nv = new_map.get(code)
        if nv is not None and nv != 0:
            covered += 1
        verdict = classify_diff(lv, nv, tol)
        counts[verdict] += 1
        if verdict == "unexplained" and len(unexplained_samples) < MAX_UNEXPLAINED_SAMPLES:
            unexplained_samples.append((code, lv, nv))
    coverage = covered / len(codes) if codes else 1.0
    return {
        "dataset": dataset,
        "coverage": coverage,
        "counts": counts,
        "verdict": "PASS" if counts["unexplained"] == 0 else "FAIL",
        "unexplained_samples": unexplained_samples,
    }


def _legacy_conn(dbname: str):
    return psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"),
        port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname=dbname,
        user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"),
    )


def _latest_kis_daily_date() -> str:
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) FROM daily_prices")
            return cur.fetchone()[0]


def _column_presence(conn, trade_date, columns) -> dict:
    """지정 컬럼이 NULL 아닌 값을 가진 행 수(존재/충전 확인). date 는 바인드 파라미터."""
    out = {}
    with conn.cursor() as cur:
        for c in columns:
            cur.execute(
                f"SELECT COUNT(*) FROM daily_prices WHERE date = %s AND {c} IS NOT NULL",
                (trade_date,),
            )
            out[c] = cur.fetchone()[0]
    return out


def report_daily(trade_date: str) -> dict:
    legacy = _legacy_conn("robotrader_quant")
    try:
        with legacy.cursor() as lc:
            lc.execute("SELECT stock_code, close FROM daily_prices WHERE date = %s", (trade_date,))
            legacy_map = {sc: (float(c) if c is not None else None) for sc, c in lc.fetchall()}
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as nc:
                nc.execute("SELECT stock_code, close FROM daily_prices WHERE date = %s", (trade_date,))
                new_map = {sc: (float(c) if c is not None else None) for sc, c in nc.fetchall()}
            col_presence = _column_presence(conn, trade_date, ["market_cap", "trading_value"])
    finally:
        legacy.close()
    rep = build_equivalence_report(f"daily@{trade_date}", legacy_map, new_map)
    rep["column_presence"] = col_presence
    return rep


def _normalize_trade_date(s: str) -> str:
    """YYYY-MM-DD → YYYYMMDD 정규화(순수 함수, no DB).

    minute_candles.trade_date 컬럼은 YYYYMMDD 문자열, daily_prices.date 와 형식이 다르다
    — db/repositories/price.py 와 동일 패턴. 이미 압축형(YYYYMMDD)이면 그대로 반환.
    """
    if len(s) == 10 and s[4] == '-':
        return s.replace('-', '')
    return s


def report_minute(trade_date: str) -> dict:
    trade_date = _normalize_trade_date(trade_date)
    legacy = _legacy_conn("robotrader")
    try:
        # 표본: 당일 존재하는 (stock_code, idx) 최근 종가 대조 — 종목별 마지막 idx close
        q = ("SELECT stock_code, close FROM minute_candles "
             "WHERE trade_date = %s AND idx = ("
             "  SELECT MAX(idx) FROM minute_candles m2 "
             "  WHERE m2.stock_code = minute_candles.stock_code AND m2.trade_date = %s)")
        with legacy.cursor() as lc:
            lc.execute(q, (trade_date, trade_date))
            legacy_map = {sc: (float(c) if c is not None else None) for sc, c in lc.fetchall()}
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as nc:
                nc.execute(q, (trade_date, trade_date))
                new_map = {sc: (float(c) if c is not None else None) for sc, c in nc.fetchall()}
    finally:
        legacy.close()
    return build_equivalence_report(f"minute@{trade_date}", legacy_map, new_map)


def _print_report(r: dict) -> None:
    print(f"\n== {r['dataset']} ==")
    print(f"  coverage(new): {r['coverage']:.4f}")
    print(f"  counts: {r['counts']}")
    if "column_presence" in r:
        print(f"  column_presence(non-null rows): {r['column_presence']}")
    print(f"  VERDICT: {r['verdict']}")
    if r["unexplained_samples"]:
        print("  unexplained(top):")
        for code, lv, nv in r["unexplained_samples"]:
            print(f"    {code}: legacy={lv} new={nv}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="시장데이터 정합 리포트(오프라인, READ-only)")
    ap.add_argument("--date", default=None, help="대상 거래일(YYYY-MM-DD). 미지정=kis 최신 일봉일")
    args = ap.parse_args(argv)
    trade_date = args.date or _latest_kis_daily_date()
    daily = report_daily(trade_date)
    minute = report_minute(trade_date)
    _print_report(daily)
    _print_report(minute)
    overall = "PASS" if daily["verdict"] == "PASS" and minute["verdict"] == "PASS" else "FAIL"
    print(f"\n[GATE] 모든 diff 설명됨? → {overall}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
