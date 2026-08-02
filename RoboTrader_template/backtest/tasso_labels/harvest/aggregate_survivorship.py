"""연도별 생존편향 손실률을 **A·B(복구 가능)를 걷어내고** 다시 잰다. 진단 전용.

원래 수치(PREREG §5.1)는 `1 - usable/라벨` 이고, `usable=False` 의 사유를 나누지 않았다:

    usable=False  =  (1) 매핑 실패          <- 여기에 **저자 표기 오류**가 섞여 있다
                   + (2) 매핑O·그해 DB 없음  <- 상폐·사명변경 + **DB 자체의 결측**
                   + (3) 매핑O·봉 부족

이 스크립트는 (1)을 A/B/C/D 로 갈라, **A·B 를 「손실 아님」으로 되돌린 보정 손실률**을 낸다.
🔴 라벨을 실제로 살리지는 않는다 — `labels_v*.csv` 를 **쓰지 않는다**. 표본 변경은 사장님 결정.

⚠️ 보정 손실률은 **하한**이다. (2)에도 사명변경분이 섞여 있을 수 있고(같은 코드가 그 해
   `daily_prices` 에 있는데 이름만 달랐던 경우는 이미 (1)에서 잡히지만, DB 결측은 못 가른다),
   C 에도 색인 누락이 섞여 있다.
"""
import argparse
import collections
import csv
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"
MIN_BARS = 15
YEARS = ["2021", "2022", "2023", "2024"]


def pct(a, b):
    return f"{a/b*100:.1f}%" if b else "-"


def first_dates():
    """코드별 `daily_prices` 최초일. 🔴 이 DB 는 백필이 **두 파도**로 들어왔다:
    1,740 코드가 2021-01, **473 코드가 2024-03** 부터 시작한다.
    ⇒ 「매핑O·그해 DB無」의 대부분은 상폐가 아니라 **백필 경계**다."""
    env = dict(os.environ, PGPASSWORD="1234")
    r = subprocess.run([PSQL, "-h", "127.0.0.1", "-p", "5433", "-U", "robotrader",
                        "-d", "kis_template", "-tAF\t", "-c",
                        "SELECT stock_code, min(date) FROM daily_prices GROUP BY 1;"],
                       capture_output=True, env=env)
    out = {}
    for line in r.stdout.decode("utf-8", "replace").strip().split("\n"):
        p = line.split("\t")
        if len(p) == 2:
            out[p[0]] = p[1]
    return out


def run(labels_path, cls, regime, years, title, firsts=None, min_conf="all"):
    firsts = firsts or {}
    rows = [r for r in csv.DictReader(open(labels_path, encoding="utf-8-sig"))
            if r["regime"] == regime]
    # 🔴 복구가 **새 관측**인지 **중복**인지 가른다 — 오타 33건 중 상당수는
    #    같은 글에 올바른 표기가 **이미 매핑돼 있다**(오스템임플란드/오스템임플란트).
    #    그런 행을 살리면 라벨이 느는 게 아니라 같은 (종목,날짜)가 두 번 세어진다.
    mapped_keys = {(r["stock_code"], r["post_date"]) for r in rows if r["stock_code"]}
    per = collections.defaultdict(collections.Counter)
    for r in rows:
        y = r["post_date"][:4]
        per[y]["lab"] += 1
        if r["usable"] == "True":
            per[y]["usable"] += 1
        if not r["stock_code"]:
            o = cls.get(r["stock_name"])
            k = o["cls"] if o else "?"
            per[y]["unmapped"] += 1
            per[y][k] += 1
            # 증거 등급 필터 — 복구를 어느 등급까지 인정할지 (사전등록용 밴드)
            if o and o["code"] and min_conf != "all":
                c = o.get("conf", "")
                if min_conf == "no-single-web" and c.startswith("mid(웹"):
                    o = dict(o, code="")
                elif min_conf == "multi-only" and not c.startswith("high"):
                    o = dict(o, code="")
            if o and o["code"]:
                pre, post = o.get("bars", {}).get(r["post_date"], (0, 0))
                ok = pre >= MIN_BARS and post >= MIN_BARS
                # 🔴 분해표가 이중계상되지 않도록 **A·B 만** 봉 회계에 넣는다.
                #    C(상폐)·D(불명)는 이미 자기 칸에서 세어졌다. C 가 데이터를 가진
                #    경우만 따로 센다(우리 DB 는 생존자 편향이라 사실상 드물다).
                if k in ("A", "AB", "B"):
                    if ok:
                        per[y]["recover"] += 1
                        per[y]["recover_" + k] += 1
                        if (o["code"], r["post_date"]) in mapped_keys:
                            per[y]["recover_dup"] += 1    # 이미 매핑된 (종목,날짜)
                        else:
                            per[y]["recover_new"] += 1
                    else:
                        # 이름은 찾았는데 그 코드의 데이터가 없다 -> 백필 경계인지 본다
                        per[y]["ab_nobars"] += 1
                        f = firsts.get(o["code"], "")
                        if f and f > r["post_date"]:
                            per[y]["ab_backfill"] += 1
                        else:
                            per[y]["ab_other"] += 1
                elif ok:
                    per[y]["c_has_data"] += 1             # 상폐인데 데이터가 남아 있다
        elif r["in_db_year"] != "True":
            per[y]["mapped_nodb"] += 1          # README 표의 「매핑O·그해 DB無」 열
        if r["stock_code"] and r["usable"] != "True":
            # 매핑은 됐는데 못 쓰는 행 — 백필 경계인지 아닌지 가른다
            f = firsts.get(r["stock_code"], "")
            per[y]["mapped_unusable"] += 1
            if f and f > r["post_date"]:
                per[y]["backfill_gap"] += 1
                if f[:7] == "2024-03":
                    per[y]["backfill_202403"] += 1
            else:
                per[y]["other_unusable"] += 1

    print(f"\n{'='*104}\n{title}   [{labels_path} · regime={regime}]\n{'='*104}")
    print(f"{'연도':<6}{'라벨':>6}{'usable':>8}{'원래손실':>9}{'미매핑':>7}"
          f"{'A':>5}{'B':>4}{'C':>5}{'D':>4}{'복구가능':>9}{'보정usable':>11}"
          f"{'보정손실':>9}{'Δ':>8}")
    tot = collections.Counter()
    for y in years:
        p = per[y]
        if not p["lab"]:
            continue
        loss = 1 - p["usable"] / p["lab"]
        cu = p["usable"] + p["recover"]
        closs = 1 - cu / p["lab"]
        for k in ("lab", "usable", "unmapped", "A", "B", "C", "D", "recover"):
            tot[k] += p[k]
        print(f"{y:<6}{p['lab']:>6}{p['usable']:>8}{loss*100:>8.1f}%{p['unmapped']:>7}"
              f"{p['A']:>5}{p['B']:>4}{p['C']:>5}{p['D']:>4}{p['recover']:>9}"
              f"{cu:>11}{closs*100:>8.1f}%{(closs-loss)*100:>7.1f}p")
    if tot["lab"]:
        loss = 1 - tot["usable"] / tot["lab"]
        cu = tot["usable"] + tot["recover"]
        closs = 1 - cu / tot["lab"]
        print(f"{'계':<6}{tot['lab']:>6}{tot['usable']:>8}{loss*100:>8.1f}%{tot['unmapped']:>7}"
              f"{tot['A']:>5}{tot['B']:>4}{tot['C']:>5}{tot['D']:>4}{tot['recover']:>9}"
              f"{cu:>11}{closs*100:>8.1f}%{(closs-loss)*100:>7.1f}p")

    # 🔑 핵심 질문 — A·B 비중이 연도에 따라 다른가
    print(f"\n  [연도 층화 근거 점검] 미매핑 중 A·AB·B 비중")
    print(f"  {'연도':<6}{'미매핑':>7}{'A':>5}{'AB':>5}{'B':>5}{'A+AB+B':>8}"
          f"{'/미매핑':>9}{'/라벨':>8}{'A만/미매핑':>11}{'복구/라벨':>10}")
    for y in years:
        p = per[y]
        if not p["lab"]:
            continue
        ab = p["A"] + p["AB"] + p["B"]
        print(f"  {y:<6}{p['unmapped']:>7}{p['A']:>5}{p['AB']:>5}{p['B']:>5}{ab:>8}"
              f"{pct(ab,p['unmapped']):>9}{pct(ab,p['lab']):>8}"
              f"{pct(p['A'],p['unmapped']):>11}{pct(p['recover'],p['lab']):>10}")

    # 🔴 나머지 손실(매핑O·못씀)의 정체 — 상폐인가 백필 결측인가
    print(f"\n  [README 표 재현 — 「합산 손실」 = (미매핑 + 매핑O·그해DB無) / 라벨]")
    print(f"  {'연도':<6}{'미매핑':>7}{'매핑O·DB無':>11}{'합산손실':>9}"
          f"{'A·AB·B 제외':>13}{'Δ':>8}")
    for y in years:
        p = per[y]
        if not p["lab"]:
            continue
        s = p["unmapped"] + p["mapped_nodb"]
        ab = p["A"] + p["AB"] + p["B"]
        print(f"  {y:<6}{p['unmapped']:>7}{p['mapped_nodb']:>11}{pct(s,p['lab']):>9}"
              f"{pct(s-ab,p['lab']):>13}{(s-ab)/p['lab']*100-s/p['lab']*100:>7.1f}p")

    # 🔑 원래 손실률을 사유별로 완전히 쪼갠다 (합이 원래 손실과 일치해야 한다)
    print(f"\n  [손실 완전 분해] — 원래 손실률의 정체. 합 = 원래 손실")
    print(f"  {'연도':<6}{'원래손실':>9}{'│':>2}{'C 진짜상폐':>11}{'D 불명':>8}"
          f"{'A·B(데이터有)':>14}{'A·B(백필결측)':>15}{'A·B(그외)':>11}"
          f"{'매핑O 백필':>11}{'매핑O 그외':>11}{'검산':>7}")
    for y in years:
        p = per[y]
        if not p["lab"]:
            continue
        parts = [p["C"], p["D"], p["recover"], p["ab_backfill"], p["ab_other"],
                 p["backfill_gap"], p["other_unusable"]]
        tot_loss = p["lab"] - p["usable"]
        chk = "OK" if sum(parts) == tot_loss else f"🔴{sum(parts)}≠{tot_loss}"
        print(f"  {y:<6}{(1-p['usable']/p['lab'])*100:>8.1f}%{'│':>2}"
              + "".join(f"{pct(x, p['lab']):>11}" if i in (0,) else ""
                        for i, x in enumerate(parts[:1]))
              + f"{pct(parts[1],p['lab']):>8}{pct(parts[2],p['lab']):>14}"
              f"{pct(parts[3],p['lab']):>15}{pct(parts[4],p['lab']):>11}"
              f"{pct(parts[5],p['lab']):>11}{pct(parts[6],p['lab']):>11}{chk:>7}")
    print("  (행수) " + " ".join(
        f"{y}:C{per[y]['C']}/D{per[y]['D']}/AB있{per[y]['recover']}/"
        f"AB백필{per[y]['ab_backfill']}/AB외{per[y]['ab_other']}/"
        f"매핑백필{per[y]['backfill_gap']}/매핑외{per[y]['other_unusable']}"
        for y in years if per[y]["lab"]))

    print(f"\n  [매핑됐는데 못 쓰는 행의 정체] — 이건 생존편향이 아니라 **우리 DB 결측**이다")
    print(f"  {'연도':<6}{'매핑O·못씀':>11}{'백필경계':>9}{'그중 2024-03':>13}{'그 외':>7}"
          f"{'백필/라벨':>10}")
    for y in years:
        p = per[y]
        if not p["lab"]:
            continue
        print(f"  {y:<6}{p['mapped_unusable']:>11}{p['backfill_gap']:>9}"
              f"{p['backfill_202403']:>13}{p['other_unusable']:>7}"
              f"{pct(p['backfill_gap'],p['lab']):>10}")
    return per


def main() -> int:
    ap = argparse.ArgumentParser()
    # 🔴 기본값이 `unmapped_classified_v4.json`(문자열 채널 단독)이었다. 그걸로 돌리면
    #    C 가 2.9% 가 아니라 14.9% 로 나오고 **양쪽 다 「검산 OK」를 찍는다**.
    #    보고한 수치는 3채널 병합본이므로 기본값을 그것으로 못 박는다.
    #    (독립 검토 지적: 「동결 문서 수치가 기본 실행으로 재현 불가」)
    ap.add_argument("--cls", default="unmapped_final_v4.json")
    ap.add_argument("--min-conf", default="all",
                    choices=["all", "no-single-web", "multi-only"],
                    help="복구를 인정할 증거 등급. 사전등록에는 밴드로 실어야 한다")
    ap.add_argument("--regime", default="검색기단타")
    args = ap.parse_args()
    cls = json.load(open(args.cls, encoding="utf-8"))
    firsts = first_dates()
    print(f"daily_prices 코드 {len(firsts)} · 최초일 2024-03 인 코드 "
          f"{sum(1 for v in firsts.values() if v[:7]=='2024-03')}")

    per4 = run("../labels_v4.csv", cls, args.regime, YEARS,
               "① v4 — PREREG §5.1 이 쓴 그 표본 (42.4/30.6/22.9/12.8 재현)",
               firsts, args.min_conf)

    # 🔑 증거 등급 민감도 — **계산했는데 안 싣는 사고**(6차 s-vs-C2)를 반복하지 않는다
    print("\n" + "=" * 104
          + "\n④ 증거 등급 민감도 — 「표본 결손률」이 근거를 깎으면 어디까지 되돌아가나\n"
          + "=" * 104)
    print(f"{'시나리오':<34}{'2021':>8}{'2022':>8}{'2023':>8}{'2024':>8}")
    import contextlib
    for mc, lab in [("all", "① 전부 채택 (보고값)"),
                    ("no-single-web", "② 단일 웹에이전트 제외"),
                    ("multi-only", "③ 다채널(>=2) 만 채택")]:
        with contextlib.redirect_stdout(io.StringIO()):
            p = run("../labels_v4.csv", cls, args.regime, YEARS, "", firsts, mc)
        print(f"{lab:<34}" + "".join(
            f"{(1-(p[y]['usable']+p[y]['recover'])/p[y]['lab'])*100:>7.1f}%" for y in YEARS))
    print(f"{'④ 보정 없음 (원래값)':<34}" + "".join(
        f"{(1-per4[y]['usable']/per4[y]['lab'])*100:>7.1f}%" for y in YEARS))
    print("⚠️ ①과 ②의 차이가 **교차검증 0인 단일 출처에 기댄 폭**이다.")
    run("../labels_v5.csv", cls, args.regime, YEARS,
        "② v5 — 산문 편입 후 현행 표본 (참고)", firsts, args.min_conf)

    print(f"\n{'='*104}\n③ 라벨 복구 시 늘어나는 처치군 행수 — **보고만 한다. 살리지 않았다.**\n{'='*104}")
    print(f"{'연도':<6}{'현 usable':>10}{'복구가능':>9}{'└새 관측':>10}{'└중복':>8}"
          f"{'복구후(새것만)':>15}{'증가율':>9}")
    t1 = t2 = t3 = 0
    for y in YEARS:
        p = per4[y]
        if not p["lab"]:
            continue
        t1 += p["usable"]
        t2 += p["recover"]
        t3 += p["recover_new"]
        print(f"{y:<6}{p['usable']:>10}{p['recover']:>9}{p['recover_new']:>10}"
              f"{p['recover_dup']:>8}{p['usable']+p['recover_new']:>15}"
              f"{p['recover_new']/p['usable']*100:>8.1f}%")
    print(f"{'계':<6}{t1:>10}{t2:>9}{t3:>10}{t2-t3:>8}{t1+t3:>15}{t3/t1*100:>8.1f}%")
    print("\n⚠️ **중복**은 같은 (종목코드, 날짜)가 이미 매핑돼 있는 행이다 — 살려도 새 관측이 아니라\n"
          "   같은 관측을 두 번 세는 것이다(같은 글에 오타·정타가 함께 있는 경우).")
    print("\n⚠️ 표본 변경은 사전등록 위반 소지가 있다 — 살릴지 말지는 사장님 결정.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
