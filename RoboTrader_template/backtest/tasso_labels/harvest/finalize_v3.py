"""v3 최종화 — 신규 종목명 코드 해소 -> (날짜,코드) 중복제거 -> DB 커버리지 검증."""
import collections
import csv
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"
FWD = 40

ALIAS = {
    "삼기에너지솔루션": "419050",   # = 삼기에너지솔루션즈
    "아이빔테크놀러지": "460470",   # = 아이빔테크놀로지 (본문 오타)
    "렙지노믹스": "084650",        # = 랩지노믹스 (한 글자 오타, 경합 후보 없음)
}


def naver(name):
    url = "https://ac.stock.naver.com/ac?q=" + urllib.parse.quote(name) + "&target=stock"
    r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0", url], capture_output=True)
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace")).get("items", [])
    except Exception:
        return []
    return sorted({i["code"] for i in items
                   if i.get("name") == name and i.get("nationCode") == "KOR"})


def sql(q):
    env = dict(os.environ, PGPASSWORD="1234")
    return subprocess.run([PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "robotrader",
                           "-d", "kis_template", "-tAF\t", "-c", q],
                          capture_output=True, env=env).stdout.decode("utf-8", "replace")


def main() -> int:
    cmap = {k: v["code"] for k, v in json.load(open("code_map.json", encoding="utf-8")).items()}
    cmap.update(ALIAS)
    rows = list(csv.DictReader(open("labels_v3_names.csv", encoding="utf-8-sig")))

    todo = sorted({r["stock_name"] for r in rows if r["stock_name"] not in cmap})
    print(f"신규 해소 대상 {len(todo)}건: {', '.join(todo)}")
    unresolved = []
    for n in todo:
        codes = naver(n)
        if len(codes) == 1:
            cmap[n] = codes[0]
            print(f"  ✓ {n} -> {codes[0]}")
        else:
            unresolved.append((n, codes))
            print(f"  ✗ {n} -> {codes or 'none'}  (매핑 안 함)")
        time.sleep(0.35)

    out, seen, dropped = [], set(), []
    for r in rows:
        code = cmap.get(r["stock_name"])
        if not code:
            dropped.append((r["post_date"], r["stock_name"]))
            continue
        k = (r["post_date"], code)
        if k in seen:      # 표기 변형으로 같은 거래가 두 번 (예: 아이빔테크놀로지/러지)
            continue
        seen.add(k)
        out.append({**r, "stock_code": code})

    # 커버리지
    vals = ",".join("('{}','{}'::date)".format(r["stock_code"], r["post_date"]) for r in out)
    q = ("WITH lab(code,d) AS (VALUES " + vals + ") "
         "SELECT lab.code, lab.d, "
         "count(*) FILTER (WHERE p.date BETWEEN to_char(lab.d-40,'YYYY-MM-DD') "
         "AND to_char(lab.d,'YYYY-MM-DD')) AS pre, "
         "count(*) FILTER (WHERE p.date > to_char(lab.d,'YYYY-MM-DD') "
         f"AND p.date <= to_char(lab.d+{FWD},'YYYY-MM-DD')) AS post "
         "FROM lab LEFT JOIN daily_prices p ON p.stock_code=lab.code "
         "AND p.date BETWEEN to_char(lab.d-40,'YYYY-MM-DD') "
         f"AND to_char(lab.d+{FWD},'YYYY-MM-DD') GROUP BY 1,2;")
    cov = {}
    for line in sql(q).strip().split("\n"):
        p = line.split("\t")
        if len(p) == 4:
            cov[(p[0], p[1])] = (int(p[2]), int(p[3]))

    for r in out:
        pre, post = cov.get((r["stock_code"], r["post_date"]), (0, 0))
        r["bars_pre"], r["bars_post"] = pre, post
        r["usable"] = pre >= 15 and post >= 15

    cols = ["post_date", "stock_code", "stock_name", "regime", "preset", "src",
            "bars_pre", "bars_post", "usable"]
    with open("labels_final_v3.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows([{c: r[c] for c in cols} for r in out])

    print(f"\n라벨 {len(out)} (표기중복 제거 {len(rows)-len(out)-len(dropped)}건, 미매핑 {len(dropped)}건)")
    print(f"{'체제':<10}{'라벨':>6}{'가용':>6}")
    for rg in ("2024단타", "스윙", "자동매매"):
        sub = [r for r in out if r["regime"] == rg]
        print(f"{rg:<10}{len(sub):>6}{sum(1 for r in sub if r['usable']):>6}")
    print(f"{'계':<10}{len(out):>6}{sum(1 for r in out if r['usable']):>6}")
    print(f"\n미매핑: {dropped}")
    print("제목전용 중 가용:",
          sum(1 for r in out if r["src"] == "title_only" and r["usable"]))
    print("-> labels_final_v3.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
