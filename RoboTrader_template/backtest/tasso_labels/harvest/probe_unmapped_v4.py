"""미매핑 227 이름의 **성격 진단 전용** 조회. 🔴 매핑에 쓰지 않는다.

`resolve_codes_v4.py` 는 **정확일치만** 받는다(7차 교훈: 최소오차 채점은 정답이 없어도
조용히 아무 후보나 매칭한다). 이 스크립트는 그 규칙을 **깨지 않는다** — 대신
접두를 한 글자씩 줄여 가며 후보를 *수집만* 하고, 판정은 `classify_unmapped_v4.py` 가
**규칙을 명시한 채** 한다. 산출물은 진단 파일 하나뿐이고
`code_map*.json` · `labels_v*.csv` 를 **건드리지 않는다.**

측정한 API 성질 (2026-08-02 실측):
- `ac.stock.naver.com/ac` 는 **접두(prefix) 매칭만** 한다. 부분일치 없음
  (`석유화학` -> 0건, `금호석유` -> 금호석유화학).
- **최대 10건에서 잘린다.** `size`·`count` 파라미터로 못 늘린다(`대한` -> 정확히 10건).
  ⇒ 🔴 **「후보 없음」은 상폐의 증거가 아니다.** 잘림 여부를 `saturated` 로 기록한다.

절차: 이름 N 에 대해 접두 길이 L, L-1, ..., 2 를 차례로 조회하고
**모든 층의 후보를 합집합으로 남긴다**(층 정보 포함). 유사후보를 찾으면 조기 종료.
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

MIN_PREFIX = 2
CAP = 10          # 실측 상한


def probe(q):
    """이름 접두 q 의 KOR 후보. 요청 실패는 None (후보 0건과 구분한다)."""
    url = "https://ac.stock.naver.com/ac?q=" + urllib.parse.quote(q) + "&target=stock"
    r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace")).get("items", [])
    except Exception:
        return None
    return [{"name": it.get("name", ""), "code": it.get("code", ""),
             "market": it.get("typeName", "")}
            for it in items if it.get("nationCode") == "KOR"]


def edit_distance(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def looks_similar(name, cand):
    """조기 종료 판정용 **느슨한** 기준. 최종 분류는 classify 단계가 다시 한다."""
    if cand.startswith(name) or name.startswith(cand):
        return True
    return edit_distance(name, cand) <= 2 and len(os.path.commonprefix([name, cand])) >= 2


def load_names(args):
    names = []
    for d in json.load(open(args.names_json, encoding="utf-8")):
        names.append(d["name"])
    if args.include_v5:
        seen = set(names)
        for r in csv.DictReader(open(args.v5, encoding="utf-8-sig")):
            if not r["stock_code"] and r["stock_name"] not in seen:
                seen.add(r["stock_name"])
                names.append(r["stock_name"])
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names-json", default="unmapped_names_v4.json")
    ap.add_argument("--v5", default="../labels_v5.csv")
    ap.add_argument("--include-v5", action="store_true",
                    help="v5(산문 편입)에서 새로 생긴 미매핑 이름도 함께 진단")
    ap.add_argument("--out", default="probe_unmapped_v4.json")
    ap.add_argument("--sleep", type=float, default=0.9)
    args = ap.parse_args()

    names = load_names(args)
    done = json.load(open(args.out, encoding="utf-8")) if os.path.exists(args.out) else {}
    todo = [n for n in names if n not in done]
    print(f"이름 {len(names)} · 미조회 {len(todo)} (기존 {len(done)}건 재사용)")
    sys.stdout.flush()

    req_fail = 0
    for i, n in enumerate(todo, 1):
        rec = {"name": n, "levels": [], "candidates": [], "request_failed": False,
               "hit_level": None, "saturated_any": False}
        seen = set()
        L = len(n)
        for k in range(L, MIN_PREFIX - 1, -1):
            pre = n[:k]
            hits = probe(pre)
            time.sleep(args.sleep)
            if hits is None:                       # 요청 실패 — 1회 재시도
                time.sleep(1.5)
                hits = probe(pre)
                time.sleep(args.sleep)
            if hits is None:
                rec["request_failed"] = True
                req_fail += 1
                break
            sat = len(hits) >= CAP
            rec["levels"].append({"prefix": pre, "n": len(hits), "saturated": sat})
            rec["saturated_any"] = rec["saturated_any"] or sat
            for h in hits:
                if h["code"] not in seen:
                    seen.add(h["code"])
                    h = dict(h, level=k, prefix=pre)
                    rec["candidates"].append(h)
            if hits and rec["hit_level"] is None:
                rec["hit_level"] = k
            if any(looks_similar(n, h["name"]) for h in hits):
                break                              # 유사후보 확보 -> 더 내려갈 이유 없음
        done[n] = rec
        if i % 20 == 0 or i == len(todo):
            json.dump(done, open(args.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print(f"  ...{i}/{len(todo)}  (요청실패 {req_fail})")
            sys.stdout.flush()

    json.dump(done, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    nocand = sum(1 for v in done.values() if not v["candidates"] and not v["request_failed"])
    print(f"\n조회 완료 {len(done)}건 · 후보 0건 {nocand}건 · 요청실패 {req_fail}건")
    print("⚠️ 후보 0건 != 상폐. 접두 응답은 10건에서 잘리고, 네이버 색인 누락과 구분 못 한다.")
    print("->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
