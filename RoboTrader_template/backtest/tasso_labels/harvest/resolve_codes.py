"""종목명 -> 종목코드 확정.

원칙(7차 교훈 반영):
- **정확 일치만** 허용한다. 유사매칭 금지 — 최소오차/부분일치 채점은 정답이 없어도 조용히
  아무 후보나 매칭해 점수를 낸다(4~6차가 이 상태로 정의를 골랐다).
- 두 소스가 어긋나면 **자동 해소하지 않고 CONFLICT 로 보고**한다.
- 결과값(수익률·forward)은 일절 계산하지 않는다. 라벨 확정까지만.
"""
import io
import json
import subprocess
import sys
import time
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def naver_lookup(name: str) -> list:
    """네이버 종목검색. **이름이 정확히 같은 것만** 반환한다."""
    q = urllib.parse.quote(name)
    url = f"https://ac.stock.naver.com/ac?q={q}&target=stock"
    r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace")).get("items", [])
    except Exception:
        return []
    return [it for it in items
            if it.get("name") == name and it.get("nationCode") == "KOR"]


def main() -> int:
    # 소스 1: DB 스크리너 이력
    dbmap = {}
    for line in open("namemap.tsv", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 2 and p[1].strip():
            dbmap[p[0].strip()] = p[1].strip()
    # 소스 2: KOSPI 마스터
    master = json.load(open(
        "D:/GIT/kis-trading-template/RoboTrader_template/stock_list.json", encoding="utf-8"))
    kospi = {s["name"]: s["code"] for s in master["stocks"]}

    names = [l.strip() for l in open("names.txt", encoding="utf-8") if l.strip()]
    resolved, conflicts, unresolved, ambiguous = {}, [], [], []

    for i, n in enumerate(names, 1):
        hits = naver_lookup(n)
        codes = sorted({h["code"] for h in hits})
        local = dbmap.get(n) or kospi.get(n)

        if len(codes) == 1:
            code = codes[0]
            if local and local != code:
                conflicts.append((n, code, local))       # 침묵시키지 않는다
            else:
                resolved[n] = {"code": code,
                               "market": hits[0].get("typeName", ""),
                               "src": "naver+local" if local else "naver"}
        elif len(codes) > 1:
            ambiguous.append((n, codes))
        elif local:
            resolved[n] = {"code": local, "market": "?", "src": "local_only"}
        else:
            unresolved.append(n)

        if i % 20 == 0:
            print(f"  ...{i}/{len(names)}")
            sys.stdout.flush()
        time.sleep(0.35)

    json.dump(resolved, open("code_map.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n확정 {len(resolved)}/{len(names)} ({len(resolved)/len(names)*100:.0f}%)")
    print(f"  네이버+로컬 일치 : {sum(1 for v in resolved.values() if v['src']=='naver+local')}")
    print(f"  네이버 단독      : {sum(1 for v in resolved.values() if v['src']=='naver')}")
    print(f"  로컬 단독        : {sum(1 for v in resolved.values() if v['src']=='local_only')}")
    print(f"\n🔴 CONFLICT {len(conflicts)}건 (네이버 vs 로컬 불일치 — 수동 판정 필요)")
    for n, c, l in conflicts:
        print(f"   {n}: 네이버 {c} / 로컬 {l}")
    print(f"\n🟡 다중매칭 {len(ambiguous)}건")
    for n, cs in ambiguous:
        print(f"   {n}: {cs}")
    print(f"\n⚪ 미해결 {len(unresolved)}건: {', '.join(unresolved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
