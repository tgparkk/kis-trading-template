"""종목명 -> 종목코드 확정 (v4 전수판). **기존 code_map.json 을 덮어쓰지 않는다.**

원칙(7차 교훈 유지):
- **정확 일치만.** 유사·접두 매칭 금지. 최소오차/부분일치 채점은 정답이 없어도 조용히 아무 후보나 매칭한다.
- 두 소스(네이버 / 로컬)가 어긋나면 자동 해소하지 않고 **CONFLICT 로 보고**한다.
- 결과값(수익률·forward)은 계산하지 않는다.

v4 추가:
- 출력은 `code_map_v4.json` (신규 전용). 병합은 `build_labels_v4.py` 가 하고 **충돌은 그때 다시 보고**한다.
- 이미 아는 이름(기존 code_map.json + 이전 v4 실행분)은 건너뛰어 재실행이 싸다.
- 실패 이름을 전부 `unresolved_v4.json` 에 남긴다 — **버린 것도 산출물이다**
  (2021년에 고른 종목 중 지금 조회 안 되는 것 = 상폐·사명변경분 = 생존편향의 크기).
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def norm(name: str) -> str:
    return re.sub(r"\s+", "", name)


def naver_lookup(name: str):
    """네이버 종목검색. **정규화 후 이름이 정확히 같은 것만** 반환."""
    q = urllib.parse.quote(name)
    url = f"https://ac.stock.naver.com/ac?q={q}&target=stock"
    r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace")).get("items", [])
    except Exception:
        return None                                   # 요청 자체 실패 (미해결과 구분)
    return [it for it in items
            if norm(it.get("name", "")) == norm(name) and it.get("nationCode") == "KOR"]


def load_local():
    """로컬 교차검증 소스 2종: DB 이름 컬럼 전부 + KOSPI 마스터.

    `namemap_v4.tsv` 생성 SQL (kis_template, 127.0.0.1:5433) — 재현용:

        select stock_code, stock_name from (
          select stock_code, stock_name from candidate_stocks
            where stock_name is not null and stock_name<>'' and stock_name not like 'PRE\\_%'
          union select stock_code, stock_name from screener_snapshots
            where stock_name is not null and stock_name<>'' and stock_name not like 'PRE\\_%'
          union select stock_code, stock_name from virtual_trading_records where stock_name is not null and stock_name<>''
          union select stock_code, stock_name from real_trading_records   where stock_name is not null and stock_name<>''
          union select stock_code, stock_name from quant_portfolio        where stock_name is not null and stock_name<>''
        ) t;
    """
    local = {}
    if os.path.exists("namemap_v4.tsv"):
        for line in open("namemap_v4.tsv", encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 2 and p[0].strip() and p[1].strip():
                local.setdefault(norm(p[1]), p[0].strip())     # code \t name
    master = "D:/GIT/kis-trading-template/RoboTrader_template/stock_list.json"
    if os.path.exists(master):
        for s in json.load(open(master, encoding="utf-8"))["stocks"]:
            local.setdefault(norm(s["name"]), s["code"])
    return local


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="names_v4.txt")
    ap.add_argument("--out", default="code_map_v4.json")
    ap.add_argument("--sleep", type=float, default=0.35)
    args = ap.parse_args()

    known = {}
    if os.path.exists("../code_map.json"):
        known = {norm(k): v["code"] for k, v in
                 json.load(open("../code_map.json", encoding="utf-8")).items()}
    resolved = json.load(open(args.out, encoding="utf-8")) if os.path.exists(args.out) else {}
    local = load_local()

    names = [l.strip() for l in open(args.names, encoding="utf-8") if l.strip()]
    todo = [n for n in names if n not in resolved]
    print(f"이름 {len(names)} · 미해소 {len(todo)} (기존 v4 {len(resolved)}건 재사용)")

    conflicts, unresolved, ambiguous, req_fail = [], [], [], []
    for i, n in enumerate(todo, 1):
        hits = naver_lookup(n)
        if hits is None:
            req_fail.append(n)
            time.sleep(1.0)
            continue
        codes = sorted({h["code"] for h in hits})
        loc = local.get(norm(n)) or known.get(norm(n))

        if len(codes) == 1:
            if loc and loc != codes[0]:
                conflicts.append((n, codes[0], loc))            # 침묵시키지 않는다
            else:
                resolved[n] = {"code": codes[0],
                               "market": hits[0].get("typeName", ""),
                               "src": "naver+local" if loc else "naver"}
        elif len(codes) > 1:
            ambiguous.append((n, codes))
        elif loc:
            resolved[n] = {"code": loc, "market": "?", "src": "local_only"}
        else:
            unresolved.append(n)

        if i % 50 == 0:
            print(f"  ...{i}/{len(todo)}  확정 {len(resolved)}")
            sys.stdout.flush()
            json.dump(resolved, open(args.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        time.sleep(args.sleep)

    json.dump(resolved, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"unresolved": unresolved, "ambiguous": ambiguous,
               "conflicts": conflicts, "request_failed": req_fail},
              open("unresolved_v4.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n확정 {len(resolved)}/{len(names)} ({len(resolved)/len(names)*100:.1f}%)")
    for tag in ("naver+local", "naver", "local_only"):
        print(f"  {tag:<12}: {sum(1 for v in resolved.values() if v['src'] == tag)}")
    print(f"\n🔴 CONFLICT {len(conflicts)}건 (네이버 vs 로컬 불일치 — 자동 해소하지 않음)")
    for n, c, l in conflicts:
        print(f"   {n}: 네이버 {c} / 로컬 {l}")
    print(f"\n🟡 다중매칭 {len(ambiguous)}건 (매핑 안 함)")
    for n, cs in ambiguous[:40]:
        print(f"   {n}: {cs}")
    print(f"\n⚪ 미해결 {len(unresolved)}건 · 요청실패 {len(req_fail)}건")
    print("-> ", args.out, "/ unresolved_v4.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
