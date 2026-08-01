"""각 라벨의 게시일 ±40일에 실제 일봉이 있는지 검증. 존재 검증만 — 가격은 읽지 않는다."""
import csv
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"

rows = [r for r in csv.DictReader(open("labels.csv", encoding="utf-8-sig"))
        if r["in_db"] == "True"]
vals = ",".join("('{}','{}'::date)".format(r["stock_code"], r["post_date"]) for r in rows)

# daily_prices.date 는 text('YYYY-MM-DD'). 인덱스를 살리려고 date 캐스팅 대신
# 경계를 문자열로 만들어 text 끼리 비교한다.
q = """
WITH lab(code,d) AS (VALUES """ + vals + """)
SELECT lab.code, lab.d,
       count(*) FILTER (WHERE p.date BETWEEN to_char(lab.d - 40,'YYYY-MM-DD')
                                         AND to_char(lab.d,'YYYY-MM-DD')) AS pre,
       count(*) FILTER (WHERE p.date >  to_char(lab.d,'YYYY-MM-DD')
                          AND p.date <= to_char(lab.d + 40,'YYYY-MM-DD')) AS post
FROM lab LEFT JOIN daily_prices p ON p.stock_code = lab.code
     AND p.date BETWEEN to_char(lab.d - 40,'YYYY-MM-DD')
                    AND to_char(lab.d + 40,'YYYY-MM-DD')
GROUP BY 1,2 ORDER BY 3,4;"""

env = dict(os.environ, PGPASSWORD="1234")
r = subprocess.run([PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "robotrader",
                    "-d", "kis_template", "-tAF\t", "-c", q],
                   capture_output=True, env=env)
out = [l.split("\t") for l in r.stdout.decode("utf-8", "replace").strip().split("\n") if l.strip()]
if not out or len(out[0]) < 4:
    print("SQL 오류:", r.stderr.decode("utf-8", "replace")[:500])
    raise SystemExit(1)

pre = [int(x[2]) for x in out]
post = [int(x[3]) for x in out]
print(f"검사 {len(out)}쌍 (게시일 ±40 역일 내 거래일 수)")
print(f"  게시일 이전 : 최소 {min(pre)} · 중앙 {sorted(pre)[len(pre)//2]} · 0건 {sum(1 for v in pre if v==0)}건")
print(f"  게시일 이후 : 최소 {min(post)} · 중앙 {sorted(post)[len(post)//2]} · 0건 {sum(1 for v in post if v==0)}건")
bad = [x for x in out if int(x[2]) < 15 or int(x[3]) < 15]
print(f"  🟡 한쪽이 15거래일 미만: {len(bad)}건")
for x in bad[:10]:
    print(f"     {x[0]}  {x[1]}  pre={x[2]}  post={x[3]}")
