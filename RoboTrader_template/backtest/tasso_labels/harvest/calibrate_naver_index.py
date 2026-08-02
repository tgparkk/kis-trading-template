"""네이버 종목검색 색인의 **누락률 실측** — 「후보 없음」을 「상폐」로 읽어도 되는가.

미매핑 이름을 상폐로 분류하려면 *"현재 상장돼 있으면 반드시 조회된다"* 가 참이어야 한다.
그게 참인지 **재 본다**: 최근 스크리너 스냅샷에 찍힌 종목명(= 그 시점 실제 거래 가능)을
무작위로 뽑아 네이버 정확일치가 되는지 센다.

- 실패율이 0 에 가까우면 「후보 없음」 -> 「현재 미상장」 추론이 선다(상폐인지 사명변경인지는 여전히 못 가른다).
- 실패율이 크면 C 분류 자체가 과대계상이다.

⚠️ 이 표본은 **상장 확인의 대리변수**다. 스냅샷 이후 상폐된 종목이 섞이면 실패율이 위로 편향된다
   (그래서 최근 N 일로 좁힌다).
"""
import argparse
import io
import json
import os
import random
import subprocess
import sys
import time
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"


def sql(q):
    env = dict(os.environ, PGPASSWORD="1234")
    r = subprocess.run([PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "robotrader",
                        "-d", "kis_template", "-tAF\t", "-c", q],
                       capture_output=True, env=env)
    err = r.stderr.decode("utf-8", "replace").strip()
    if err:
        print("SQL stderr:", err[:400])
    return r.stdout.decode("utf-8", "replace")


def probe_exact(name):
    url = "https://ac.stock.naver.com/ac?q=" + urllib.parse.quote(name) + "&target=stock"
    r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace")).get("items", [])
    except Exception:
        return None
    return [(i.get("name"), i.get("code")) for i in items
            if i.get("nationCode") == "KOR" and i.get("name", "").replace(" ", "")
            == name.replace(" ", "")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="calibration_naver_index.json")
    args = ap.parse_args()

    # ⚠️ `screener_snapshots.stock_name` 은 최근분이 **코드 문자열로 채워져 있다**(736 중 735).
    #    이름 소스로 쓰면 표본이 통째로 무의미해진다 -> `candidate_stocks` 를 쓴다.
    q = ("SELECT DISTINCT stock_code, stock_name FROM candidate_stocks "
         f"WHERE selection_date >= CURRENT_DATE - {args.days} "
         "AND stock_name IS NOT NULL AND stock_name <> '' "
         "AND stock_name !~ '^[0-9]+$' "
         # ⚠️ `PRE_` 말고 `WS_` 자리표시자도 있다 — 150일 창에서 표본 150 중 83건이 `WS_*` 였다.
         "AND stock_name NOT LIKE 'PRE\\_%' AND stock_name NOT LIKE 'WS\\_%';")
    pool = []
    for line in sql(q).strip().split("\n"):
        p = line.split("\t")
        if len(p) == 2 and p[0].strip() and p[1].strip():
            pool.append((p[0].strip(), p[1].strip()))
    print(f"최근 {args.days}일 스크리너 종목 {len(pool)}개 (= 그 시점 상장·거래 가능)")
    if not pool:
        print("🔴 표본 0 — 기간을 늘려야 한다")
        return 1

    random.Random(args.seed).shuffle(pool)
    sample = pool[:args.n]
    miss, hit, conflict, fail = [], 0, [], 0
    for i, (code, name) in enumerate(sample, 1):
        h = probe_exact(name)
        if h is None:
            fail += 1
        elif not h:
            miss.append((code, name))
        else:
            hit += 1
            if all(c != code for _, c in h):
                conflict.append((code, name, h))
        time.sleep(1.0)
        if i % 20 == 0:
            print(f"  ...{i}/{len(sample)}  누락 {len(miss)}")
            sys.stdout.flush()

    n = len(sample) - fail
    print(f"\n표본 {len(sample)} (요청실패 {fail} 제외 -> {n})")
    print(f"  정확일치 성공 {hit}  ·  🔴 색인 누락 {len(miss)} ({len(miss)/max(n,1)*100:.1f}%)")
    for c, nm in miss:
        print(f"     {nm} ({c})")
    print(f"  코드 불일치 {len(conflict)}건")
    for x in conflict:
        print("     ", x)
    json.dump({"sample": len(sample), "hit": hit, "miss": miss,
               "conflict": conflict, "request_failed": fail, "days": args.days,
               "seed": args.seed},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
