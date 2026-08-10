"""C(1) DART company.json 으로 업종분류(induty_code) 수집 — 순차 1req/s, 체크포인트 재개.

읽기 전용 + 외부 API. DB 쓰기 없음.

목적: 우리 DB 에 업종 분류가 없다(`stock_market` 은 KOSPI/KOSDAQ 시장구분뿐,
`financial_data.industry_code` 는 테이블이 0행). 「대장주 우선」류 후보선정 로직을
검토하려면 업종 축이 필요하므로 DART 표준산업분류를 받아온다.

유니버스: a1_corpcode_map.json 의 매핑된 종목(2,556). corpCode.xml 재수집 금지.

🔴 병렬 금지. 2026-08-06 에 4스레드로 opendart 에 IP 차단당했고(약 40분), 그 동안
   운영 수집기(collectors/corp_events_collector.py)도 같은 호스트라 동작 불가가 된다.
🔴 차단 징후(연결 리셋 3연속) 감지 시 대기하지 않고 **즉시 중단**하고 보고한다.
🔴 빈 응답·status != '000' 을 성공으로 처리하지 않는다. status 분포를 집계한다.

usage:
  PYTHONUTF8=1 python scripts/dart_industry_c1_collect.py            # 수집/재개
  PYTHONUTF8=1 python scripts/dart_industry_c1_collect.py --limit 50
  PYTHONUTF8=1 python scripts/dart_industry_c1_collect.py --status   # 진행상황만
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import (  # noqa: E402
    DART_BASE, OUT_DIR, DartBlocked, DartClient, load_dart_key,
)

MAP_JSON = os.path.join(OUT_DIR, "a1_corpcode_map.json")
CHECKPOINT = os.path.join(OUT_DIR, "c1_industry_checkpoint.jsonl")

# 저장할 응답 필드 — 종목 식별·분류에 쓸 만한 것만. 주소·전화·URL 등은 버린다.
KEEP_FIELDS = (
    "corp_code", "corp_name", "corp_name_eng", "stock_name", "stock_code",
    "corp_cls", "induty_code", "est_dt", "acc_mt", "jurir_no", "bizr_no",
)


class CompanyClient(DartClient):
    """company.json 전용. DartClient 의 스로틀·status 집계·리셋 감지를 그대로 쓴다."""

    def company(self, corp_code: str):
        """반환: (status, message, data_dict). data_dict 는 KEEP_FIELDS 만."""
        url = f"{DART_BASE}/company.json"
        params = {"crtfc_key": self.key, "corp_code": corp_code}
        reset_streak = 0
        backoff = 2.0
        for _ in range(6):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=25)
                self.calls += 1
            except requests.exceptions.ConnectionError:
                self.conn_resets += 1
                reset_streak += 1
                if reset_streak >= 3:
                    raise DartBlocked("연결 리셋 3연속 — opendart IP 차단으로 판단")
                self.session.close()
                self.session = requests.Session()
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            except Exception:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            reset_streak = 0
            if r.status_code != 200:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            try:
                js = r.json()
            except ValueError:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            status = js.get("status")
            self._bump(status)
            if status == "020":
                raise RuntimeError("DART 사용한도 초과(status=020) — 중단")
            if status == "800":
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            data = {k: js.get(k) for k in KEEP_FIELDS}
            return status, js.get("message", ""), data
        self._bump("HTTP_FAIL")
        return "HTTP_FAIL", "retries exhausted", {}


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
    n = 0
    with_induty = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            n += 1
            st[rec["status"]] += 1
            if (rec.get("data") or {}).get("induty_code"):
                with_induty += 1
    return n, st, with_induty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(MAP_JSON, encoding="utf-8") as f:
        cmap = json.load(f)
    uni = sorted(cmap)
    done = load_done(CHECKPOINT)
    todo = [c for c in uni if c not in done]

    print(f"유니버스 {len(uni)}종목 = {len(uni):,} 호출 (1req/s → 약 {len(uni)//60}분)")
    print(f"완료 {len(done)} / 남은 {len(todo)}")
    if args.status:
        if os.path.exists(CHECKPOINT):
            n, st, wi = checkpoint_stats(CHECKPOINT)
            print(f"체크포인트: {n}건, status={dict(st)}, induty_code 보유 {wi}")
        return
    if not todo:
        print("수집 완료 — 남은 종목 없음")
        return

    if args.limit:
        todo = todo[:args.limit]
        print(f"이번 실행 대상 {len(todo)}종목")

    key = load_dart_key()
    if not key:
        raise SystemExit("OPENDART_API_KEY 없음")
    client = CompanyClient(key, min_interval=args.interval)

    ck = open(CHECKPOINT, "a", encoding="utf-8")
    processed = 0
    try:
        for i, sc in enumerate(todo, 1):
            try:
                status, msg, data = client.company(cmap[sc])
            except DartBlocked as e:
                # 🔴 대기하지 않는다 — 운영 수집기와 같은 호스트다. 즉시 중단·보고.
                print(f"\n🔴 차단 감지 — 즉시 중단. {sc} 처리 중, "
                      f"완료 {processed}종목, calls={client.calls}, "
                      f"resets={client.conn_resets}\n   {e}", flush=True)
                return
            except RuntimeError as e:
                print(f"\n🔴 {e} — 중단. 완료 {processed}종목, calls={client.calls}",
                      flush=True)
                return
            ck.write(json.dumps(
                {"stock_code": sc, "corp_code": cmap[sc], "status": status,
                 "msg": msg, "data": data}, ensure_ascii=False) + "\n")
            ck.flush()
            processed += 1
            if i % 100 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  calls={client.calls:,}  "
                      f"status={dict(client.status_counts)}  "
                      f"resets={client.conn_resets}", flush=True)
    finally:
        ck.close()
        print(f"\n종료: 이번 실행 {processed}종목, 호출 {client.calls:,}, "
              f"status={dict(client.status_counts)}, "
              f"연결리셋={client.conn_resets}, http오류={client.http_errors}")


if __name__ == "__main__":
    main()
