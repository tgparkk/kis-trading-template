"""B(1) 2021~2023 백필용 DART 주식수 수집 (순차 1req/s, 체크포인트 재개).

읽기 전용 + 외부 API. DB 쓰기 없음.

보고서 세트 (13종/종목):
  2020 11011  — 🔴 필수. 2021-01-04 를 감싸는 결산기는 2021-03-31 이고, SAFE_STRICT
                게이트가 요구하는 **직전 보고서**가 2020-12-31 이다. A(2) 의 LEAD
                202행이 이 누락의 징후였다.
  2021~2023 × (11013 11012 11014 11011) — 값 + 구간 내 사건 판정

2024+ 는 부르지 않는다. SAFE_STRICT 의 "이후 불변" 조건 중 **분할·병합**(= close 를
후방조정해 과거 행의 기준계를 오염시키는 유일한 사건 유형)은 DB 가격갭으로 탐지한다
(b3). 유상·무상증자는 과거 close 를 소급 변경하지 않으므로 그 시점 보고서 값이 옳다.

🔴 병렬 금지. 2026-08-06 에 4스레드로 opendart 에 IP 차단당했고, 그 동안 운영
   수집기(collectors/corp_events_collector.py)도 같은 호스트라 동작 불가가 된다.
🔴 차단 징후(연결 리셋) 감지 시 대기하지 않고 **즉시 중단**하고 보고한다.

usage:
  PYTHONUTF8=1 python scripts/dart_mcap_b1_collect.py            # 수집/재개
  PYTHONUTF8=1 python scripts/dart_mcap_b1_collect.py --limit 300
  PYTHONUTF8=1 python scripts/dart_mcap_b1_collect.py --status   # 진행상황만
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import (  # noqa: E402
    OUT_DIR, DartBlocked, DartClient, db_conn, load_dart_key,
)

MAP_JSON = os.path.join(OUT_DIR, "a1_corpcode_map.json")
CHECKPOINT = os.path.join(OUT_DIR, "b1_dart_checkpoint.jsonl")
FWD_CHECKPOINT = os.path.join(OUT_DIR, "b1_forward_checkpoint.jsonl")
UNIVERSE_TXT = os.path.join(OUT_DIR, "b1_universe.txt")

YEAR_REPRTS = [("2020", "11011")] + [
    (y, rc) for y in ("2021", "2022", "2023")
    for rc in ("11013", "11012", "11014", "11011")
]

# forward 세트 — SAFE_STRICT 의 W2("감싸는 보고서 == 최신 보고서")를 판정하려면
# 2024 이후 주식수를 알아야 한다. 2025년 분할이 close 를 후방조정해 2021~23 행의
# 기준계를 바꾸는 경우가 실측으로 존재하고(000860 adj_factor 2.0), 그 클래스는
# price-gap 으로 안 잡힌다(후방조정되면 갭이 사라진다) — DART 만이 유일한 신호다.
# 연 1회 스냅샷이면 충분하다(분할 후 같은 해 되돌리는 사례는 없다).
FORWARD_REPRTS = [("2024", "11011"), ("2025", "11011"), ("2026", "11013")]


def load_universe(reprts=YEAR_REPRTS):
    with open(MAP_JSON, encoding="utf-8") as f:
        cmap = json.load(f)
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT stock_code FROM daily_prices "
        "WHERE date >= '2021-01-01' AND date <= '2023-12-31'"
    )
    codes = sorted(r[0] for r in cur.fetchall())
    conn.close()
    # 매핑된 종목만 = 우선주 36종·지수 의사코드 자동 제외
    uni = [c for c in codes if c in cmap]
    with open(UNIVERSE_TXT, "w", encoding="utf-8") as f:
        f.write(f"# 2021~23 등장 {len(codes)} / 매핑 {len(uni)} / 보고서 {len(reprts)}종\n")
        for c in uni:
            f.write(f"{c}\t{cmap[c]}\n")
    return uni, cmap


def load_done(path):
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        done.add(json.loads(line)["stock_code"])
                    except (ValueError, KeyError):
                        continue
    return done


def checkpoint_stats(path):
    st = Counter()
    stocks = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            stocks += 1
            for e in rec["entries"]:
                st[e["status"]] += 1
    return stocks, st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="이번 실행에서 처리할 종목 수 상한")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--forward", action="store_true",
                    help="W2 판정용 2024~2026 스냅샷 수집(별도 체크포인트)")
    args = ap.parse_args()

    reprts = FORWARD_REPRTS if args.forward else YEAR_REPRTS
    ckpath = FWD_CHECKPOINT if args.forward else CHECKPOINT

    os.makedirs(OUT_DIR, exist_ok=True)
    uni, cmap = load_universe(reprts)
    done = load_done(ckpath)
    todo = [c for c in uni if c not in done]

    print(f"유니버스 {len(uni)}종목 x {len(reprts)}보고서 = "
          f"{len(uni)*len(reprts):,} 호출 (일일한도 20,000)")
    print(f"완료 {len(done)} / 남은 {len(todo)} "
          f"(남은 호출 {len(todo)*len(reprts):,})")
    if args.status:
        if os.path.exists(ckpath):
            s, st = checkpoint_stats(ckpath)
            print(f"체크포인트: {s}종목, status={dict(st)}")
        return
    if not todo:
        print("수집 완료 — 남은 종목 없음")
        return

    if args.limit:
        todo = todo[:args.limit]
        print(f"이번 실행 대상 {len(todo)}종목 ({len(todo)*len(reprts):,} 호출)")

    key = load_dart_key()
    if not key:
        raise SystemExit("OPENDART_API_KEY 없음")
    client = DartClient(key, min_interval=args.interval)

    ck = open(ckpath, "a", encoding="utf-8")
    processed = 0
    try:
        for i, sc in enumerate(todo, 1):
            entries = []
            for year, rc in reprts:
                try:
                    status, msg, rows = client.stock_totqy(cmap[sc], year, rc)
                except DartBlocked as e:
                    # 🔴 대기하지 않는다 — 운영 수집기와 같은 호스트다. 즉시 중단·보고.
                    print(f"\n🔴 차단 감지 — 즉시 중단. {sc} 처리 중, "
                          f"완료 {processed}종목, calls={client.calls}, "
                          f"resets={client.conn_resets}\n   {e}", flush=True)
                    return
                except RuntimeError as e:  # status 020 = 일일 한도 초과
                    print(f"\n🔴 {e} — 중단. 완료 {processed}종목, calls={client.calls}",
                          flush=True)
                    return
                entries.append({"year": year, "reprt": rc, "status": status,
                                "msg": msg, "rows": rows})
            ck.write(json.dumps({"stock_code": sc, "entries": entries},
                                ensure_ascii=False) + "\n")
            ck.flush()
            processed += 1
            if i % 25 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} 종목  calls={client.calls:,}  "
                      f"status={dict(client.status_counts)}  "
                      f"resets={client.conn_resets}", flush=True)
    finally:
        ck.close()
        print(f"\n종료: 이번 실행 {processed}종목, 호출 {client.calls:,}, "
              f"status={dict(client.status_counts)}, "
              f"연결리셋={client.conn_resets}, http오류={client.http_errors}")


if __name__ == "__main__":
    main()
