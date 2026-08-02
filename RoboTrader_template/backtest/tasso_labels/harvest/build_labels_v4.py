"""labels_v4 조립 — 본문라벨 ∪ 제목라벨 -> 코드매핑 -> DB 커버리지.

🔴 결과변수(forward 수익률·성과)는 계산하지 않는다. DB 조회는 두 가지만 허용:
   (a) 종목코드 존재 여부  (b) 게시일 전후 거래일 수(bars_pre/bars_post, 기존 usable 규약과 동일)

합집합인 이유는 회수율이 아니라 **편향**이다. 구조화 보고에서 빠지는 거래는 결과가
밋밋한 쪽으로 치우친다(*"이외 한화투자증권은 진입했으나 … 차트 미첨부 합니다"* 2021-12-20 ·
*"이외 그리드위즈 진입하였으나 본전으로 차트 미첨부"* 2024-08-20). 결과는 우리가 DB 에서 재므로
넣는 쪽이 맞다.

체제는 **날짜 블록**으로 나눈다. 경계는 전부 (a) 긴 휴재 공백 (b) 본문 마커의 계단식 변화
두 가지가 **같은 지점에서** 일치하는 곳으로 잡았다:

    초기        2017-01-13 ~ 2020-03-10   22글. 투매폭/계산기 기반 스윙·종가베팅 등 혼재
    검색기단타   2020-04-21 ~ 2024-08-30   813글(제목에 「검색기」가 든 것은 775). 검색기 → 일봉 구조
                                            → 이등분선 눌림 → 3%권 분할매도
    스윙박스권   2025-05-13 ~ 2025-10-18   12글. 「평균 고점대비 하락률 + 신뢰구간」을 박스권 하단으로
    스윙계산기   2026-01-10 ~ 2026-04-03   10글. 통계기반 계산기 5분할 + 프리셋 (7차가 모델링한 그 사다리)
    자동매매     2026-07-31 ~              1글. 「통계기반 트레이더 1.0.30」

실측 근거(`regime_markers.py`, 푸터 제거 후 · 본문 비율):
    이등분선  2020~2024 = 96~100%  /  2025~2026 = **0%**
    계산기    2017 = 38%(!) · 2019~2025 = 0%  /  2026-01~04 = **100%(10/10)**
    프리셋    2025 = 8%(1/12)      /  2026-01~04 = **100%**
계산기 캡처 51장도 **전부 2026-01~04** 이다(2025년분 0장).
⇒ 「스윙」을 2025~2026 한 덩어리로 두면 **도구가 다른 두 시기를 섞는다.**

⚠️ 제목의 검색기 이름(주도주/실시간검색순위/신고가/장초반)은 **체제 구분자가 아니다** —
   검색기 언급 글 812건 중 **639건(78.7%)이 본문에 2종 이상**을 함께 쓴다. `searcher` 컬럼은
   글 단위 표기일 뿐이며 라벨 단위로는 신뢰할 수 없다.
"""
import argparse
import collections
import csv
import datetime
import io
import json
import os
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"
FWD = 40
PRE = 40
MIN_BARS = 15

# finalize_v3.ALIAS 승계 — 본문 오타/표기변형. 이유를 개별 확인한 것만 넣는다.
ALIAS = {
    "삼기에너지솔루션": "419050",   # = 삼기에너지솔루션즈
    "아이빔테크놀러지": "460470",   # = 아이빔테크놀로지 (본문 오타)
    "렙지노믹스": "084650",        # = 랩지노믹스 (한 글자 오타, 경합 후보 없음)
}

REGIMES = [
    ("초기",       datetime.date(2017, 1, 1),  datetime.date(2020, 4, 20)),
    ("검색기단타",  datetime.date(2020, 4, 21), datetime.date(2024, 12, 31)),
    ("스윙박스권",  datetime.date(2025, 1, 1),  datetime.date(2025, 12, 31)),
    ("스윙계산기",  datetime.date(2026, 1, 1),  datetime.date(2026, 6, 30)),
    ("자동매매",    datetime.date(2026, 7, 1),  datetime.date(2099, 1, 1)),
]


def norm(s):
    return re.sub(r"\s+", "", s)


def regime_of(d):
    for name, lo, hi in REGIMES:
        if lo <= d <= hi:
            return name
    return "?"


def searcher_of(suffix):
    s = suffix or ""
    if "주도주" in s and "검색기" in s:
        return "주도주검색기"
    if "실시간 검색" in s or "실시간검색" in s or "실시간 종목순위" in s:
        return "실시간검색순위"
    if "신고가" in s:
        return "신고가검색기"
    if "장초반" in s:
        return "장초반검색기"
    if "검색기" in s:
        return "기타검색기"
    if "스윙" in s:
        return "스윙"
    return "기타"


def sql(query: str) -> str:
    env = dict(os.environ, PGPASSWORD="1234")
    path = "_q.sql"
    open(path, "w", encoding="utf-8").write(query)
    r = subprocess.run([PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "robotrader",
                        "-d", "kis_template", "-tAF\t", "-f", path],
                       capture_output=True, env=env)
    err = r.stderr.decode("utf-8", "replace").strip()
    if err:
        print("SQL stderr:", err[:800])
    os.remove(path)
    return r.stdout.decode("utf-8", "replace")


def load_codemap():
    """기존 code_map.json + 신규 code_map_v4.json 병합. **충돌은 자동 해소하지 않는다.**"""
    old, new, conflicts = {}, {}, []
    if os.path.exists("../code_map.json"):
        old = {k: v["code"] for k, v in
               json.load(open("../code_map.json", encoding="utf-8")).items()}
    if os.path.exists("code_map_v4.json"):
        new = {k: v["code"] for k, v in
               json.load(open("code_map_v4.json", encoding="utf-8")).items()}
    merged = {}
    for k, v in old.items():
        merged[norm(k)] = v
    for k, v in new.items():
        kk = norm(k)
        if kk in merged and merged[kk] != v:
            conflicts.append((k, merged[kk], v))
        else:
            merged[kk] = v
    for k, v in ALIAS.items():
        kk = norm(k)
        if kk in merged and merged[kk] != v:
            conflicts.append((k + " (ALIAS)", merged[kk], v))
        merged[kk] = v
    return merged, conflicts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../labels_v4.csv")
    args = ap.parse_args()

    titles = list(csv.DictReader(open("titles_labels.csv", encoding="utf-8-sig")))
    bodies = list(csv.DictReader(open("body_labels.csv", encoding="utf-8-sig")))

    suffix_of = {r["logNo"]: r["title_suffix"] for r in titles}
    trunc_of = {r["logNo"]: r["truncated"] == "True" for r in titles}

    T = {(r["post_date"], norm(r["stock_name"])): r for r in titles}
    B = {(r["post_date"], norm(r["stock_name"])): r for r in bodies}

    keys = sorted(set(T) | set(B))
    rows = []
    for k in keys:
        date_s, _ = k
        t, b = T.get(k), B.get(k)
        src = "both" if (t and b) else ("body" if b else "title_only")
        name = (b or t)["stock_name"]
        log_no = (b or t)["logNo"]
        d = datetime.date(*map(int, date_s.split("-")))
        rows.append({
            "post_date": date_s, "logNo": log_no, "stock_name": name,
            "regime": regime_of(d),
            "searcher": searcher_of(suffix_of.get(log_no, "")),
            # preset 은 **캡션 원문 그대로**(모드 수식어 포함). 층화용 파생은 별도 두 컬럼.
            "preset": (b or {}).get("preset", ""),
            "preset_base": (b or {}).get("preset_base", ""),
            "preset_mode": (b or {}).get("preset_mode", ""),
            "preset_mode_src": (b or {}).get("preset_mode_src", ""),
            "method": (b or {}).get("method", ""),
            "src": src,
            "title_truncated": trunc_of.get(log_no, False),
        })

    cmap, cmap_conflicts = load_codemap()
    print(f"🔴 code_map 병합 CONFLICT {len(cmap_conflicts)}건 (자동 해소하지 않음)")
    for n, a, b_ in cmap_conflicts:
        print(f"   {n}: 기존 {a} / 신규 {b_}")

    unmapped = collections.Counter()
    for r in rows:
        r["stock_code"] = cmap.get(norm(r["stock_name"]), "")
        if not r["stock_code"]:
            unmapped[r["stock_name"]] += 1

    # (날짜, 코드) 중복 제거 — 표기 변형으로 같은 거래가 두 번 들어오는 경우
    seen, dedup, dropped_dup = set(), [], 0
    for r in rows:
        if not r["stock_code"]:
            dedup.append(r)
            continue
        kk = (r["post_date"], r["stock_code"])
        if kk in seen:
            dropped_dup += 1
            continue
        seen.add(kk)
        dedup.append(r)
    rows = dedup

    # ---- DB 조회 (허용된 두 가지만) ----
    mapped = [r for r in rows if r["stock_code"]]
    vals = ",".join("('{}','{}'::date)".format(r["stock_code"], r["post_date"])
                    for r in mapped)
    q = (
        "WITH lab(code,d) AS (VALUES " + vals + ") "
        "SELECT lab.code, lab.d, "
        f"count(*) FILTER (WHERE p.date BETWEEN to_char(lab.d-{PRE},'YYYY-MM-DD') "
        "AND to_char(lab.d,'YYYY-MM-DD')) AS pre, "
        "count(*) FILTER (WHERE p.date > to_char(lab.d,'YYYY-MM-DD') "
        f"AND p.date <= to_char(lab.d+{FWD},'YYYY-MM-DD')) AS post "
        "FROM lab LEFT JOIN daily_prices p ON p.stock_code=lab.code "
        f"AND p.date BETWEEN to_char(lab.d-{PRE},'YYYY-MM-DD') "
        f"AND to_char(lab.d+{FWD},'YYYY-MM-DD') GROUP BY 1,2;"
    )
    cov = {}
    for line in sql(q).strip().split("\n"):
        p = line.split("\t")
        if len(p) == 4:
            cov[(p[0], p[1])] = (int(p[2]), int(p[3]))

    # 코드가 그 **연도**에 DB 에 존재하는가 (매핑 성공 != 그 시절 데이터 보유)
    codes = sorted({r["stock_code"] for r in mapped})
    q2 = ("SELECT stock_code, substr(date,1,4) AS y, count(*) FROM daily_prices "
          "WHERE stock_code IN (" + ",".join("'%s'" % c for c in codes) + ") "
          "GROUP BY 1,2;")
    have = collections.defaultdict(int)
    for line in sql(q2).strip().split("\n"):
        p = line.split("\t")
        if len(p) == 3:
            have[(p[0], p[1])] = int(p[2])

    for r in rows:
        pre, post = cov.get((r["stock_code"], r["post_date"]), (0, 0))
        r["bars_pre"], r["bars_post"] = pre, post
        r["in_db_year"] = have[(r["stock_code"], r["post_date"][:4])] > 0
        r["usable"] = bool(r["stock_code"]) and pre >= MIN_BARS and post >= MIN_BARS

    cols = ["post_date", "logNo", "stock_code", "stock_name", "regime", "searcher",
            "preset", "preset_base", "preset_mode", "preset_mode_src",
            "src", "title_truncated", "bars_pre", "bars_post",
            "in_db_year", "usable", "method"]
    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows([{c: r[c] for c in cols} for r in rows])

    # 실패한 이름은 **전부** 남긴다 — 버린 것도 산출물이다.
    # 2021년에 그가 고른 종목 중 지금 조회가 안 되는 것은 상폐·사명변경분이고,
    # 그 라벨은 아무 흔적 없이 사라진다. 그 크기가 곧 생존편향의 크기다.
    first_year = {}
    for r in rows:
        if not r["stock_code"]:
            first_year.setdefault(r["stock_name"], r["post_date"][:4])
    json.dump([{"name": n, "n": c, "first_year": first_year.get(n, "")}
               for n, c in unmapped.most_common()],
              open("unmapped_names_v4.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---- 보고표 ----
    print(f"\n라벨 {len(rows)} (표기중복 제거 {dropped_dup}건) · 매핑성공 {len(mapped)} "
          f"· 미매핑 {len(rows)-len(mapped)} (고유 {len(unmapped)}개)")
    print(f"\n{'연도':<6}{'라벨':>7}{'body':>7}{'both':>7}{'title':>7}"
          f"{'매핑':>7}{'DB보유':>8}{'usable':>8}")
    per = collections.defaultdict(list)
    for r in rows:
        per[r["post_date"][:4]].append(r)
    for y in sorted(per):
        g = per[y]
        print(f"{y:<6}{len(g):>7}"
              f"{sum(1 for r in g if r['src']=='body'):>7}"
              f"{sum(1 for r in g if r['src']=='both'):>7}"
              f"{sum(1 for r in g if r['src']=='title_only'):>7}"
              f"{sum(1 for r in g if r['stock_code']):>7}"
              f"{sum(1 for r in g if r['in_db_year']):>8}"
              f"{sum(1 for r in g if r['usable']):>8}")
    print(f"{'계':<6}{len(rows):>7}"
          f"{sum(1 for r in rows if r['src']=='body'):>7}"
          f"{sum(1 for r in rows if r['src']=='both'):>7}"
          f"{sum(1 for r in rows if r['src']=='title_only'):>7}"
          f"{sum(1 for r in rows if r['stock_code']):>7}"
          f"{sum(1 for r in rows if r['in_db_year']):>8}"
          f"{sum(1 for r in rows if r['usable']):>8}")

    print(f"\n=== 생존편향 지표: 연도별 매핑 실패율 + 「매핑됐지만 그 해 DB에 없음」 ===")
    print(f"{'연도':<6}{'라벨':>7}{'매핑실패':>9}{'실패율':>8}"
          f"{'매핑O·DB無':>11}{'그비율':>8}")
    for y in sorted(per):
        g = per[y]
        nomap = sum(1 for r in g if not r["stock_code"])
        mapped_g = [r for r in g if r["stock_code"]]
        nodb = sum(1 for r in mapped_g if not r["in_db_year"])
        print(f"{y:<6}{len(g):>7}{nomap:>9}{nomap/len(g)*100:>7.1f}%"
              f"{nodb:>11}{(nodb/len(mapped_g)*100 if mapped_g else 0):>7.1f}%")

    print(f"\n{'체제':<12}{'라벨':>7}{'매핑':>7}{'usable':>8}")
    for rg, _, _ in REGIMES:
        g = [r for r in rows if r["regime"] == rg]
        if g:
            print(f"{rg:<12}{len(g):>7}{sum(1 for r in g if r['stock_code']):>7}"
                  f"{sum(1 for r in g if r['usable']):>8}")
    # 층화 키가 실제로 층을 나누는지 — 모드가 「미표기」로 다 쏠려 있으면 층화가 불가능하다.
    print(f"\n=== preset_base × preset_mode (모드 = 깊이 분포 규격 Q 의 층화 키) ===")
    ct = collections.Counter((r["preset_base"], r["preset_mode"])
                             for r in rows if r["preset"] or r["preset_mode"] not in ("", "미표기"))
    print(f"{'preset_base':<14}{'preset_mode':<12}{'n':>5}   src")
    for (bs, md), n in sorted(ct.items(), key=lambda x: (-x[1], x[0])):
        srcs = {r["preset_mode_src"] for r in rows
                if r["preset_base"] == bs and r["preset_mode"] == md and r["preset_mode_src"]}
        print(f"{bs or '(없음)':<14}{md:<12}{n:>5}   {','.join(sorted(srcs)) or '-'}")

    print(f"\n-> {args.out} · unmapped_names_v4.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
