"""ANCHOR_STRATEGY.md §2.1 재현 — 계산기 밴드 상대폭 `s` 가 이산인가.

입력은 git 추적 파일 `calc_table.csv` 하나뿐이다(공개 가능한 값).
METHOD.md §A.3 의 6프레임 수치는 비공개 이미지 원장이라 여기에 들어가지 않는다.

    python band_discreteness.py

⚠️ `s` 정의는 **edge** 다 — `band_hi`/`band_lo` 는 양 끝 center 에서 gap/2 만큼 더 나간 값이다.
   center 기준(1차/막차)으로 재면 중앙값이 14.39% 가 아니라 11.68% 가 나온다. 섞지 말 것.
⚠️ `s` 는 차수 개수에 의존한다(edge 폭 = n*gap). 이 표는 전부 5차수다.
"""
from __future__ import annotations

import csv
import io
import itertools
import os
import random
import statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "calc_table.csv")

TIE_EPS = 0.02      # pp — 동률로 볼 s 차이
CLUSTER_EPS = 0.15  # pp — 클러스터 경계
KDE_H = 1.0         # pp — 귀무를 매끄럽게 펴는 대역폭
N_SIM = 3000
SEED = 20260807


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load():
    """(s, date, stock, ver, preset, weights, centers) 목록. band 결측 행은 버린다."""
    out = []
    with io.open(CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            hi, lo = _f(r["band_hi"]), _f(r["band_lo"])
            if not (hi and lo):
                continue
            out.append(
                dict(
                    s=(hi - lo) / hi * 100.0,
                    date=r["date"],
                    stock=r["stock"],
                    ver=r["ver"],
                    preset=r["preset"],
                    weights=r["weights"],
                    centers=r["centers"],
                )
            )
    return out


def clusters(rows, eps=CLUSTER_EPS):
    """s 오름차순으로 인접 간격이 eps 미만이면 같은 클러스터."""
    rows = sorted(rows, key=lambda d: d["s"])
    if not rows:
        return []
    out = [[rows[0]]]
    for d in rows[1:]:
        if d["s"] - out[-1][-1]["s"] < eps:
            out[-1].append(d)
        else:
            out.append([d])
    return out


def tie_pairs(values, stocks, dates, eps, cross_date):
    """같은 종목 쌍은 세지 않는다(재게시 의존성). cross_date 면 같은 날짜 쌍도 제외."""
    n = 0
    for i, j in itertools.combinations(range(len(values)), 2):
        if stocks[i] == stocks[j]:
            continue
        if cross_date and dates[i] == dates[j]:
            continue
        if abs(values[i] - values[j]) < eps:
            n += 1
    return n


def null_test(rows, cross_date, rng):
    """귀무 = 관측값 리샘플 + 가우시안(KDE_H). 이산 구조만 지우고 주변분포는 보존한다."""
    vals = [d["s"] for d in rows]
    stocks = [d["stock"] for d in rows]
    dates = [d["date"] for d in rows]
    obs = tie_pairs(vals, stocks, dates, TIE_EPS, cross_date)
    counts = []
    for _ in range(N_SIM):
        sim = [rng.choice(vals) + rng.gauss(0, KDE_H) for _ in vals]
        counts.append(tie_pairs(sim, stocks, dates, TIE_EPS, cross_date))
    ge = sum(1 for c in counts if c >= obs)
    return obs, st.mean(counts), ge / N_SIM, ge


def main():
    rng = random.Random(SEED)
    rows = load()
    s_all = sorted(d["s"] for d in rows)

    print("== 정의 확인 (ANCHOR_STRATEGY.md §1 기재값과 대조)")
    print("   n=%d  중앙 %.2f%%  범위 %.2f~%.2f%%" % (len(s_all), st.median(s_all), s_all[0], s_all[-1]))
    print("   문서 기재값        n=49  중앙 14.39%  범위 4.68~36.98%")

    v13 = [d for d in rows if d["ver"] == "1.3"]
    cl = clusters(v13)
    multi = [g for g in cl if len({x["stock"] for x in g}) >= 2]
    print()
    print("== Ver 1.3 %d건 클러스터 (경계 %.2fpp)" % (len(v13), CLUSTER_EPS))
    for g in cl:
        stks = sorted({x["stock"] for x in g})
        pres = sorted({x["preset"] for x in g})
        print(
            "   %s s=%.3f~%.3f  건 %d  종목 %d  프리셋 %d (%s)  %s"
            % ("*" if len(stks) >= 2 else " ", g[0]["s"], g[-1]["s"], len(g), len(stks),
               len(pres), "/".join(pres), ", ".join(stks))
        )
    print("   => 클러스터 %d개 · 서로 다른 종목 2개 이상 %d개" % (len(cl), len(multi)))

    print()
    print("== 귀무 실측 (동률 문턱 %.2fpp · KDE h=%.1f · %d회)" % (TIE_EPS, KDE_H, N_SIM))
    for cross_date, label in ((False, "다른 종목"), (True, "다른 종목 AND 다른 날짜")):
        obs, mu, p, ge = null_test(rows, cross_date, rng)
        print("   %-24s 관측 %3d쌍 | 귀무 기대 %5.2f쌍 | p=%.4f (%d/%d)"
              % (label, obs, mu, p, ge, N_SIM))

    print()
    print("== 프리셋 -> 비중 (고정 사다리인가 통계기반인가)")
    by_preset = defaultdict(set)
    for d in rows:
        by_preset[d["preset"]].add(d["weights"])
    for p, ws in sorted(by_preset.items(), key=lambda kv: -len(kv[1])):
        print("   %-18s 서로 다른 비중 %2d종" % (p, len(ws)))

    print()
    print("== 프리셋만 다른 쌍 — 밴드(중심가)가 실제로 같은가  [1판 §5 직접 검정]")
    by_stock = defaultdict(list)
    for d in rows:
        by_stock[d["stock"]].append(d)
    same = diff = 0
    for stk, v in sorted(by_stock.items()):
        for a, b in itertools.combinations(v, 2):
            if a["preset"] == b["preset"]:
                continue
            eq_band = a["centers"] == b["centers"]
            same += eq_band
            diff += not eq_band
            print("   %-16s %s[%s] vs %s[%s]  중심가 %s / 비중 %s"
                  % (stk, a["date"], a["preset"], b["date"], b["preset"],
                     "동일" if eq_band else "다름",
                     "동일" if a["weights"] == b["weights"] else "다름"))
    print("   => 중심가 동일 %d쌍 / 다름 %d쌍 (다름은 전부 날짜도 다르다 = 앵커가 바뀐 경우)" % (same, diff))


if __name__ == "__main__":
    main()
