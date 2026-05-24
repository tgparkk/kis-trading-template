"""
p0_backfill_corp_events.py 에서 호출하는 단일 종목 워커.

사용법: python _p0_worker.py <stock_code> <start_YYYYMMDD> <end_YYYYMMDD>
성공 시 stdout에 JSON 한 줄 출력.
실패/빈결과 시 빈 JSON 배열 출력.
"""
from __future__ import annotations
import json, sys, warnings
from datetime import datetime

warnings.filterwarnings("ignore")

def main():
    if len(sys.argv) < 4:
        print("[]")
        sys.exit(0)

    code = sys.argv[1]
    start_str = sys.argv[2]
    end_str = sys.argv[3]

    start_dt = datetime.strptime(start_str, "%Y%m%d").date()
    end_dt   = datetime.strptime(end_str,   "%Y%m%d").date()

    # pykrx 로깅을 완전히 비활성화 (deadlock 방지)
    import logging
    logging.disable(logging.CRITICAL)

    try:
        from pykrx import stock as pykrx_stock
        df = pykrx_stock.get_stock_major_changes(code)
    except Exception as e:
        print("[]")
        sys.exit(0)

    if df is None or df.empty:
        print("[]")
        sys.exit(0)

    cols = list(df.columns)
    face_before_col = None
    face_after_col  = None
    for col in cols:
        if "액면변경전" in col:
            face_before_col = col
        if "액면변경후" in col:
            face_after_col = col

    if face_before_col is None or face_after_col is None:
        print("[]")
        sys.exit(0)

    results = []
    for idx, row in df.iterrows():
        try:
            event_dt = idx.date() if hasattr(idx, "date") else idx
        except Exception:
            continue

        if event_dt < start_dt or event_dt > end_dt:
            continue

        try:
            before = int(row[face_before_col])
            after  = int(row[face_after_col])
        except (ValueError, TypeError):
            continue

        if before <= 0 or after <= 0:
            continue

        direction = "split" if before > after else "merge"
        if before > after:
            ratio_str = f"{before // after}:1"
            factor    = before / after
        else:
            ratio_str = f"1:{after // before}"
            factor    = after / before

        results.append({
            "event_date": event_dt.isoformat(),
            "face_before": before,
            "face_after":  after,
            "ratio":       ratio_str,
            "direction":   direction,
            "split_factor": factor,
        })

    print(json.dumps(results))
    sys.exit(0)

if __name__ == "__main__":
    main()
