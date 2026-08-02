"""산문 종목명 -> 종목코드 (v5). `resolve_codes_v4.py` 규약을 **그대로** 따른다.

- **정확 일치만.** 유사·접두 매칭 금지 (7차 교훈: 최소오차 채점은 정답이 없어도 조용히 매칭한다).
- 두 소스(네이버 / 로컬)가 어긋나면 자동 해소하지 않고 **CONFLICT 로 보고**.
- 경합(다중 코드)이면 매핑하지 않고 버린다 — 추측 매핑보다 라벨 1건 버리는 쪽이 싸다.
- 실패는 **전량 목록**으로 남긴다 (생존편향 지표).
- ⚠️ 기존 `code_map*.json` 은 **후보 생성기로 쓰지 않는다.** 전량 재조회하고,
  기존 사전은 **교차검증(CONFLICT 탐지)** 에만 쓴다.

두 번째 역할: `prose_recall_tokens.txt`(기계 추출이 뽑았고 사람 판독엔 없는 토큰)를
같은 정확일치로 훑어 **사람이 놓친 종목명**을 찾는다. 사전 없이 회수율을 재는 유일한 방법이다.
"""
import argparse
import csv
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
    """로컬 교차검증 소스: DB 이름맵 + KOSPI 마스터. (resolve_codes_v4.load_local 동일)"""
    local = {}
    if os.path.exists("namemap_v4.tsv"):
        for line in open("namemap_v4.tsv", encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 2 and p[0].strip() and p[1].strip():
                local.setdefault(norm(p[1]), p[0].strip())
    master = "D:/GIT/kis-trading-template/RoboTrader_template/stock_list.json"
    if os.path.exists(master):
        for s in json.load(open(master, encoding="utf-8"))["stocks"]:
            local.setdefault(norm(s["name"]), s["code"])
    return local


def load_prior():
    """기존 사전 — **교차검증 전용**. 후보 생성에 쓰지 않는다."""
    prior = {}
    for path, key in (("../code_map.json", "code"), ("code_map_v4.json", "code")):
        if os.path.exists(path):
            for k, v in json.load(open(path, encoding="utf-8")).items():
                prior.setdefault(norm(k), v[key])
    return prior


def sweep(names, local, prior, sleep, tag):
    resolved, conflicts, ambiguous, unresolved, req_fail = {}, [], [], [], []
    for i, n in enumerate(names, 1):
        hits = naver_lookup(n)
        if hits is None:
            req_fail.append(n)
            time.sleep(2.0)
            continue
        codes = sorted({h["code"] for h in hits})
        loc = local.get(norm(n))
        pri = prior.get(norm(n))
        if len(codes) == 1:
            for src_name, other in (("로컬", loc), ("기존사전", pri)):
                if other and other != codes[0]:
                    conflicts.append((n, codes[0], src_name, other))
            resolved[n] = {"code": codes[0], "market": hits[0].get("typeName", ""),
                           "src": "naver"}
        elif len(codes) > 1:
            ambiguous.append((n, codes))
        else:
            unresolved.append(n)
        if i % 25 == 0:
            print(f"  [{tag}] {i}/{len(names)} 확정 {len(resolved)}")
            sys.stdout.flush()
        time.sleep(sleep)
    return resolved, conflicts, ambiguous, unresolved, req_fail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--skip-recall", action="store_true")
    args = ap.parse_args()

    local, prior = load_local(), load_prior()
    rows = list(csv.DictReader(open("prose_names.csv", encoding="utf-8-sig")))
    names = sorted({r["name"] for r in rows})
    print(f"산문 고유 종목명 {len(names)}건 · 로컬 {len(local)} · 기존사전 {len(prior)}")

    res, conf, amb, unres, fail = sweep(names, local, prior, args.sleep, "names")
    json.dump(res, open("code_map_prose.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"unresolved": unres, "ambiguous": amb, "conflicts": conf,
               "request_failed": fail},
              open("unresolved_prose.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n확정 {len(res)}/{len(names)} ({len(res)/len(names)*100:.1f}%)")
    print(f"🔴 CONFLICT {len(conf)}건 (자동 해소하지 않음)")
    for n, c, s, o in conf:
        print(f"   {n}: 네이버 {c} / {s} {o}")
    print(f"🟡 경합(다중매칭) {len(amb)}건 — 매핑 안 함")
    for n, cs in amb:
        print(f"   {n}: {cs}")
    print(f"⚪ 미해결 {len(unres)}건 · 요청실패 {len(fail)}건")
    for n in unres:
        print(f"   {n}")

    if not args.skip_recall and os.path.exists("prose_recall_tokens.txt"):
        toks = [l.strip() for l in open("prose_recall_tokens.txt", encoding="utf-8")
                if l.strip()]
        print(f"\n=== 회수 대조: 기계 추출 토큰 {len(toks)}종 네이버 정확일치 ===")
        rres, _, ramb, _, rfail = sweep(toks, local, prior, args.sleep, "recall")
        json.dump({"hits": rres, "ambiguous": ramb, "request_failed": rfail},
                  open("prose_recall_hits.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"🔴 사람 판독에 없는데 **실재 종목명**인 토큰 {len(rres)}종 "
              f"(+경합 {len(ramb)}) -> prose_recall_hits.json")
        for n, v in sorted(rres.items()):
            print(f"   {n} -> {v['code']}")

    print("\n-> code_map_prose.json / unresolved_prose.json / prose_recall_hits.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
