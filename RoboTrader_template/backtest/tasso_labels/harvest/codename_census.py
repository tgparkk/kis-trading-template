"""`daily_prices` 전 종목코드의 **현재 종목명 / 상장 여부** 조사. 진단 전용.

🔴 이 스크립트가 생긴 이유 — 접두 조회가 낸 「후보 없음」이 상폐의 증거가 아님을 실증했다:

    효성첨단소재 -> 접두 `효성` 6건에도 없고 정확일치 0건.  그런데 `q=298050` 은 **HS효성첨단소재**.
    백광산업 -> `q=001340` 은 **PKC**.  LS전선아시아 -> `q=229640` 은 **LS에코에너지**.
    차백신연구소 -> `q=261780` 은 **아리바이오랩**.  퓨처켐 -> `q=220100` 은 **퓨쳐켐**(저자 오타였다).

즉 **접두 매칭은 이름 앞에 글자가 붙는 사명변경(HS·롯데·KG…)을 원리적으로 못 본다.**
반면 코드로 조회하면 (a) 살아 있으면 **현재 이름**을, (b) 상폐면 **0건**을 준다
(실측: 맘스터치 220630 · 소리바다 053110 · 넥슨지티 041140 전부 0건 / 수산세보틱스 017550 은 1건).

⇒ 코드 -> 현재이름 지도를 만들면
   ① 미매핑 이름을 **현재 이름 전체 집합**과 대조할 수 있고(접두의 사각지대 해소)
   ② 우리 DB 유니버스 자체의 **상폐 census** 가 부산물로 나온다.

⚠️ 한계: 「코드 조회 0건」도 상폐의 **직접 증거는 아니다** — 색인 누락과 구분 못 한다.
   그래서 `calibrate_naver_index.py` 로 누락률을 따로 잰다.
⚠️ 결과값(수익률·forward)은 계산하지 않는다. 이름과 상장여부만 본다.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

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


def by_code(code):
    """코드 조회. 살아 있으면 [(name, code)], 상폐/미색인이면 []. 요청 실패는 None."""
    url = "https://ac.stock.naver.com/ac?q=" + code + "&target=stock"
    r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace")).get("items", [])
    except Exception:
        return None
    return [{"name": i.get("name", ""), "code": i.get("code", ""),
             "market": i.get("typeName", "")}
            for i in items if i.get("nationCode") == "KOR" and i.get("code") == code]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="codename_census.json")
    ap.add_argument("--sleep", type=float, default=0.8)
    ap.add_argument("--since", default="2020-01-01",
                    help="이 날짜 이후 daily_prices 행이 있는 코드만 (라벨 시대)")
    args = ap.parse_args()

    # 🔴 `daily_prices` 에는 종목이 아닌 행이 섞여 있다 — **지수 4종**(`KOSPI`·`KOSDAQ`·`KS11`·`KQ11`).
    #    초판이 이걸 안 걸러서 「미색인 27」 중 4건이 지수였다(= 상폐율이 27/2606 이 아니라 23/2602).
    #    ⚠️ `daily_prices` 로 「종목 수」를 세는 코드는 전부 이 4행을 확인할 것.
    #    (`00088K` 같은 신형우선주 10종은 진짜 종목이라 남긴다.)
    q = ("SELECT DISTINCT stock_code FROM daily_prices "
         f"WHERE date >= '{args.since}' "
         "AND stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11') ORDER BY 1;")
    codes = [l.strip() for l in sql(q).strip().split("\n") if l.strip()]
    done = json.load(open(args.out, encoding="utf-8")) if os.path.exists(args.out) else {}
    todo = [c for c in codes if c not in done]
    print(f"코드 {len(codes)} · 미조회 {len(todo)} (기존 {len(done)}건 재사용)")
    sys.stdout.flush()

    fail = 0
    for i, c in enumerate(todo, 1):
        h = by_code(c)
        time.sleep(args.sleep)
        if h is None:
            time.sleep(1.5)
            h = by_code(c)
            time.sleep(args.sleep)
        if h is None:
            done[c] = {"listed": None, "name": "", "market": ""}   # 요청 실패
            fail += 1
        elif h:
            done[c] = {"listed": True, "name": h[0]["name"], "market": h[0]["market"]}
        else:
            done[c] = {"listed": False, "name": "", "market": ""}
        if i % 100 == 0 or i == len(todo):
            json.dump(done, open(args.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=0)
            live = sum(1 for v in done.values() if v["listed"] is True)
            print(f"  ...{i}/{len(todo)}  상장 {live} · 미색인 "
                  f"{sum(1 for v in done.values() if v['listed'] is False)} · 실패 {fail}")
            sys.stdout.flush()

    json.dump(done, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    live = sum(1 for v in done.values() if v["listed"] is True)
    gone = sum(1 for v in done.values() if v["listed"] is False)
    print(f"\n코드 {len(done)}  ·  현재 상장 {live}  ·  🔴 미색인(상폐 추정) {gone} "
          f"({gone/max(len(done)-fail,1)*100:.1f}%)  ·  요청실패 {fail}")
    print("⚠️ 「미색인」은 상폐의 **추정**이다. 색인 누락과 구분하지 못한다.")
    print("->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
