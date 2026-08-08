"""F(2) DART as-filed 연간 재무제표 수집 (순차, 체크포인트 재개).

읽기 전용 + 외부 API. DB 쓰기 없음.

🔴 병렬 금지 — 2026-08-06 IP 차단 전례.
🔴 status=020 은 즉시 중단하고 체크포인트를 보존한다.
🔑 원본 응답을 gzip 으로 그대로 남긴다. 수집이 1~2일이라 필드를 골라 버리면
   나중에 계정 하나 때문에 전체 재수집이 된다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --limit 300
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --status
"""
import argparse
import gzip
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import (  # noqa: E402
    OUT_DIR, REPRT_FY, DartBlocked, DartClient, DartQuotaExceeded,
    eprint, load_dart_key,
)
from f1_worklist import WORKLIST_JSONL  # noqa: E402

RAW_GZ = os.path.join(OUT_DIR, "f2_raw.jsonl.gz")


def collect_one(client, item):
    """CFS 우선, 무자료면 OFS 로 재시도. 둘 다 없으면 013 을 기록한다."""
    last = (None, "")
    for fs_div in ("CFS", "OFS"):
        status, message, rows = client.fnltt_all(
            item["corp_code"], item["bsns_year"], REPRT_FY, fs_div,
        )
        if status == "000" and rows:
            return {
                "stock_code": item["stock_code"],
                "corp_code": item["corp_code"],
                "bsns_year": item["bsns_year"],
                "status": status,
                "fs_div": fs_div,
                "rows": rows,
            }
        last = (status, message)
    # 🔴 데이터 없음을 성공으로 기록하지 않는다. 리스크 필터가 조용히 깨끗하다고 답하면 최악이다.
    final_status = last[0]
    if final_status == "000":
        final_status = "000_EMPTY"
    return {
        "stock_code": item["stock_code"],
        "corp_code": item["corp_code"],
        "bsns_year": item["bsns_year"],
        "status": final_status,
        "fs_div": None,
        "rows": [],
    }


def load_done(path):
    """이미 수집한 (stock_code, bsns_year) 집합. 잘린 마지막 줄은 버린다.

    🔴 하드킬·전원차단으로 gzip 종료 마커가 없으면 EOFError 를 낸다.
       «디코딩된 만큼은 살려» 재개를 할 수 있게 한다.
    """
    done = set()
    if not os.path.exists(path):
        return done
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # 중단 시점의 잘린 줄 — 그 한 줄만 버린다
                done.add((rec["stock_code"], rec["bsns_year"]))
    except EOFError:
        # gzip 컨테이너가 정상 종료되지 않았으나 읽은 데이터는 유효하다.
        # 앞부분을 살리고 재개한다.
        pass
    return done


def load_worklist():
    items = []
    with open(WORKLIST_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--interval", type=float, default=0.34)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    items = load_worklist()
    done = load_done(RAW_GZ)
    todo = [i for i in items if (i["stock_code"], i["bsns_year"]) not in done]

    print(f"작업 {len(items)} / 완료 {len(done)} / 남음 {len(todo)}")
    if args.status:
        return

    key = load_dart_key()
    if not key:
        eprint("OPENDART_API_KEY 를 찾지 못했다 — 중단")
        sys.exit(1)

    client = DartClient(key, min_interval=args.interval)
    if args.offset:
        todo = todo[args.offset:]
    if args.limit:
        todo = todo[: args.limit]

    written = 0
    try:
        with gzip.open(RAW_GZ, "at", encoding="utf-8") as out:
            for item in todo:
                rec = collect_one(client, item)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                written += 1
                if written % 200 == 0:
                    print(f"  {written}/{len(todo)} · 호출 {client.calls} "
                          f"· status {dict(Counter(client.status_counts))}")
    except DartQuotaExceeded as e:
        eprint(f"🔴 {e} — 체크포인트 {written}건 보존. 자정 이후 재개할 것.")
        sys.exit(2)
    except DartBlocked as e:
        eprint(f"🔴 {e} — 체크포인트 {written}건 보존. 즉시 중단했다.")
        sys.exit(3)

    print(f"완료 {written}건 · 호출 {client.calls} · status {dict(client.status_counts)} "
          f"· 연결리셋 {client.conn_resets} · http오류 {client.http_errors}")


if __name__ == "__main__":
    main()
