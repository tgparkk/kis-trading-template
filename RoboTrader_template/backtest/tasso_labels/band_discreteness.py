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
import sys
from collections import defaultdict

# Windows 기본 콘솔(cp949)에서 죽지 않게 한다. 이 줄이 없으면 마지막 절 직전에
# UnicodeEncodeError 로 크래시한다(2026-08-08 독립 검증 2건이 각각 포착).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # py<3.7
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "calc_table.csv")

TIE_EPS = 0.02      # pp — 동률로 볼 s 차이 (판독·반올림 오차 한계 내 「구분 불가」)
KDE_H = 1.0         # pp — 귀무를 매끄럽게 펴는 대역폭
N_SIM = 3000
SEED = 20260807
MAIN_VER = "1.3"    # §6: 주 검정은 Ver1.3, Ver1.4 는 별도 보고(단일 배치라 층이 아니다)


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
            cs = [_f(x) for x in r["centers"].split("/")]
            if any(c is None for c in cs) or len(cs) < 2:
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
                    centers_num=cs,
                )
            )
    return out


def unique_bands(rows):
    """M1 — 재게시 중복 제거. 같은 (종목, 중심가 문자열)은 **같은 밴드 1건**이다.

    행으로 세면 한 종목이 클러스터에 2행 기여할 때 상대 종목과의 쌍이 곱해져
    효과크기가 부풀려진다(§6 「블록 = 포지션」과 같은 클래스).
    """
    seen, out = set(), []
    for d in rows:
        k = (d["stock"], d["centers"])
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return out


def s_interval(centers):
    """중심가가 정수 반올림(±0.5원)일 때 참 s 가 놓일 수 있는 구간.

    s = (c0 - c4 + gap) / (c0 + gap/2),  gap = c0 - c1   (calc_table.py 규약)
    c0·c1·c4 각각 ±0.5 이므로 8개 꼭짓점을 평가해 min/max 를 잡는다.
    """
    c0, c1, c4 = centers[0], centers[1], centers[-1]
    vals = []
    for d0 in (-0.5, 0.5):
        for d1 in (-0.5, 0.5):
            for d4 in (-0.5, 0.5):
                a0, a1, a4 = c0 + d0, c1 + d1, c4 + d4
                gap = a0 - a1
                hi = a0 + gap / 2.0
                vals.append((a0 - a4 + gap) / hi * 100.0)
    return min(vals), max(vals)


def clusters(rows):
    """🔧 2026-08-08 재작성 — 거리 문턱이 아니라 **구간 교집합**으로 묶는다.

    초판은 `CLUSTER_EPS=0.15pp 단일연결` 이었는데, 그건 동률 문턱(0.02pp)과 **다른 기준**이라
    표와 p값이 서로 다른 것을 말하게 만들었다(chaining 으로 폭이 0.156pp 까지 벌어진 행이 있었다).
    여기서는 「참 s 가 하나라는 가정과 양립 가능한 최대 집합」으로 정의한다 —
    자유모수가 없고, 그 자체가 더 강한 진술이다. (독립 검증 2026-08-08 지적)
    """
    iv = sorted(((s_interval(d["centers_num"]), d) for d in rows), key=lambda x: x[0][1])
    out = []
    cur, cur_lo, cur_hi = [], -1e18, 1e18
    for (lo, hi), d in iv:
        if cur and lo > cur_hi:            # 공통점 없음 → 새 그룹
            out.append(cur)
            cur, cur_lo, cur_hi = [], -1e18, 1e18
        cur.append(d)
        cur_lo, cur_hi = max(cur_lo, lo), min(cur_hi, hi)
    if cur:
        out.append(cur)
    return sorted(out, key=lambda g: min(x["s"] for x in g))


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


def multi_stock_clusters(intervals):
    """[(lo, hi, stock)] → 구간 교집합 그룹 중 **서로 다른 종목 2개 이상**인 그룹 수.

    주 통계량. 쌍(pair) 통계량은 큰 클러스터 하나가 지배하므로
    (관측 51쌍 중 최대 성분 하나가 37%) 클러스터 개수를 헤드라인으로 쓴다.
    """
    iv = sorted(intervals, key=lambda x: x[1])
    groups, cur, cur_hi = [], [], 1e18
    for lo, hi, stock in iv:
        if cur and lo > cur_hi:
            groups.append(cur)
            cur, cur_hi = [], 1e18
        cur.append(stock)
        cur_hi = min(cur_hi, hi)
    if cur:
        groups.append(cur)
    return sum(1 for g in groups if len(set(g)) >= 2), len(groups)


def main():
    rng = random.Random(SEED)
    rows = load()
    s_all = sorted(d["s"] for d in rows)

    print("== 정의 확인 (ANCHOR_STRATEGY.md §1 기재값과 대조)")
    print("   n=%d  중앙 %.2f%%  범위 %.2f~%.2f%%" % (len(s_all), st.median(s_all), s_all[0], s_all[-1]))
    print("   문서 기재값        n=49  중앙 14.39%  범위 4.68~36.98%")

    v13_all = [d for d in rows if d["ver"] == MAIN_VER]
    v13 = unique_bands(v13_all)
    print()
    print("== 표본 (M1 재게시 중복 제거)")
    print("   Ver%s 행 %d → **고유밴드 %d** (제거 %d) · Ver1.4 %d행(= 글 1개, 층 아님)"
          % (MAIN_VER, len(v13_all), len(v13), len(v13_all) - len(v13),
             len([d for d in rows if d["ver"] != MAIN_VER])))

    cl = clusters(v13)
    multi = [g for g in cl if len({x["stock"] for x in g}) >= 2]
    print()
    print("== Ver %s 고유밴드 %d건 클러스터 (구간 교집합 · 자유모수 없음)" % (MAIN_VER, len(v13)))
    for g in cl:
        stks = sorted({x["stock"] for x in g})
        pres = sorted({x["preset"] for x in g})
        lo = max(s_interval(x["centers_num"])[0] for x in g)
        hi = min(s_interval(x["centers_num"])[1] for x in g)
        print("   %s 참s∈[%.4f,%.4f]  건 %d  종목 %d  프리셋 %d (%s)  %s"
              % ("*" if len(stks) >= 2 else " ", lo, hi, len(g), len(stks),
                 len(pres), "/".join(pres), ", ".join(stks)))
    print("   => 클러스터 %d개 · **다종목 클러스터 %d개** (주 통계량)" % (len(cl), len(multi)))

    print()
    print("== 귀무 실측 — 주 통계량: 다종목 클러스터 수 (KDE h=%.1f · %d회)" % (KDE_H, N_SIM))
    base = [(s_interval(d["centers_num"]), d["stock"]) for d in v13]
    obs_mc, _ = multi_stock_clusters([(lo, hi, s) for (lo, hi), s in base])
    half = [(hi - lo) / 2.0 for (lo, hi), _ in base]
    vals = [d["s"] for d in v13]
    cnt = []
    for _ in range(N_SIM):
        sim = [rng.choice(vals) + rng.gauss(0, KDE_H) for _ in vals]
        cnt.append(multi_stock_clusters(
            [(sim[i] - half[i], sim[i] + half[i], base[i][1]) for i in range(len(sim))])[0])
    ge = sum(1 for c in cnt if c >= obs_mc)
    print("   다종목 클러스터  관측 %2d개 | 귀무 기대 %5.2f개 | p=%.4f (%d/%d)"
          % (obs_mc, st.mean(cnt), ge / N_SIM, ge, N_SIM))

    print()
    print("== 보조: 동률쌍 (0.02pp 이내 = 판독·반올림 한계 내 구분 불가)")
    print("   ⚠️ 쌍은 큰 클러스터 하나에 지배된다. 헤드라인으로 쓰지 말 것.")
    for label, subset in (("Ver1.3 고유밴드", v13), ("전체 49행(초판 기준·부풀림)", rows)):
        for cross_date, tag in ((False, "다른 종목"), (True, "＋다른 날짜")):
            obs, mu, p, ge2 = null_test(subset, cross_date, rng)
            print("   %-22s %-10s 관측 %3d쌍 | 귀무 %5.2f | p=%.4f"
                  % (label, tag, obs, mu, p))

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
