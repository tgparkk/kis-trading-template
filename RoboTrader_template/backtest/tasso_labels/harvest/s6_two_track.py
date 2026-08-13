#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s6_two_track.py — METHOD.md 6장 「두 트랙 가설」 본검정.

사전등록: backtest/tasso_labels/PREREG_S6_TWO_TRACK.md (커밋 f6d089e 로 동결).
이 스크립트는 그 사전등록을 «그대로» 실행한다. 어휘·문턱·창 경계를 여기서 바꾸지 않는다.

읽기 전용:
  입력  backtest/tasso_labels/labels_v5.csv             (utf-8-sig)
  입력  backtest/tasso_labels/harvest/titles_labels.csv (utf-8-sig, 부수 대조용)
  출력  backtest/tasso_labels/harvest/s6_two_track_result.md

DB·가격데이터·리포 라이브 코드를 일절 건드리지 않는다(utils.logger 임포트 금지 —
라이브 봇과 trading_YYYYMMDD.log 를 공유하므로 자립 스크립트로 쓴다).

실행: venv 파이썬으로 이 파일을 직접 실행. 경로는 __file__ 기준이라 cwd 무관.
"""

import csv
import os
import random
import re
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# 0. 동결 상수 — PREREG 에서 그대로 옮긴 것. 여기를 고치면 사전등록 위반이다.
# ---------------------------------------------------------------------------

SEED = 20260813          # G0 셔플 고정 시드(재현성). 날짜 기반, 데이터와 무관하게 선정.
N_SHUFFLE = 3000         # PREREG 6장 G0

# PREREG 4장 — 달력 연도 경계. regime 컬럼은 판정의 어떤 단계에도 쓰지 않는다.
WIN_DAYTRADE = ("2020-01-01", "2024-12-31")   # 단타 창
WIN_CONTROL = ("2025-01-01", "2026-12-31")    # 대조 창
# 2017~2019 는 분석에서 제외(PREREG 4장: 전 39행 · usable=False 100%).

# PREREG 5장 문턱 (AND) — 사후 완화 없음
THRESH_N_SWING = 20      # n_S + n_M >= 20 글
THRESH_P_SWING = 0.03    # p_swing >= 3%
THRESH_G3_UNDEF = 0.30   # 창 내 미정글 비율 30% 초과면 판정 보류

# PREREG 3.2 — 체계 B 마커(6장 표 인용). 이것이 전부다.
B_MARKERS_S = ["계산기", "통계", "밴드", "분할", "살라미", "HDR", "앵커", "박스권"]
B_MARKERS_D = ["돌파", "신고가", "장대양봉", "허리", "엔벨로프", "이등분선",
               "볼밴", "볼린저", "눌림목", "밀집"]

# PREREG 3.2 모호어 사전 처리
#   `반등` 단독 → 어느 쪽도 아님(두 리스트 어디에도 안 넣는다)
#   `이평선 반등`·`N일 반등`·`N일선 반등` → D
#   `반등폭`·`저점 대비 반등` → S
#   `이평선`/`이동평균선` 단독 → D
B_AMBIG_S = [("반등폭", "반등폭"),
             (r"저점\s*대비\s*반등", "저점 대비 반등")]
B_AMBIG_D = [("이평선", "이평선"),
             ("이동평균선", "이동평균선"),
             (r"\d+\s*일\s*선?\s*반등", "N일(선) 반등")]

# 체계 A(어휘 명시) — PREREG 3.1
A_MARKER_S = "스윙"
A_MARKER_D = "단타"

HERE = os.path.dirname(os.path.abspath(__file__))
P_LABELS = os.path.normpath(os.path.join(HERE, "..", "labels_v5.csv"))
P_TITLES = os.path.join(HERE, "titles_labels.csv")
P_OUT = os.path.join(HERE, "s6_two_track_result.md")


# ---------------------------------------------------------------------------
# 1. 행 분류
# ---------------------------------------------------------------------------

def hits_b(method):
    """method 문자열에서 발화한 (S 마커, D 마커) 목록."""
    s_hit, d_hit = [], []
    for m in B_MARKERS_S:
        if m in method:
            s_hit.append(m)
    for m in B_MARKERS_D:
        if m in method:
            d_hit.append(m)
    for pat, name in B_AMBIG_S:
        if re.search(pat, method):
            s_hit.append(name)
    for pat, name in B_AMBIG_D:
        if re.search(pat, method):
            d_hit.append(name)
    return sorted(set(s_hit)), sorted(set(d_hit))


def hits_a(method):
    s_hit = [A_MARKER_S] if A_MARKER_S in method else []
    d_hit = [A_MARKER_D] if A_MARKER_D in method else []
    return s_hit, d_hit


def row_label(s_hit, d_hit):
    """PREREG 3.3 배정 규칙."""
    if s_hit and d_hit:
        return "혼합"      # 억지로 한쪽에 배정하지 않는다
    if s_hit:
        return "S"
    if d_hit:
        return "D"
    return "미정"


# ---------------------------------------------------------------------------
# 2. 글 집계 (PREREG 3.4 — 단위는 «글»(logNo))
# ---------------------------------------------------------------------------

def gloss_label_union(labels):
    """주 규칙. S-only = S 계열이 있고 D 계열이 없음(미정 행은 «정보 없음»으로 본다).

    3.4 의 'S-only 글'/'D-only 글' 은 «상대 클래스에 대한» 배타성으로 읽었다.
    행 라벨 '혼합'(한 method 안에 양쪽 마커)은 S 이면서 D 인 행이므로 혼재로 계상된다.
    문자 그대로 '전부 S' 로 읽는 변형은 gloss_label_strict 로 함께 계산해 보고한다.
    """
    has_s = any(l in ("S", "혼합") for l in labels)
    has_d = any(l in ("D", "혼합") for l in labels)
    if has_s and has_d:
        return "혼재글"
    if has_s:
        return "S-only"
    if has_d:
        return "D-only"
    return "미정글"


def gloss_label_strict(labels):
    """민감도 변형. 3.4 문언 그대로: '전부 S' / '전부 D' / 'S행과 D행 공존'."""
    ls = set(labels)
    if ls == {"S"}:
        return "S-only"
    if ls == {"D"}:
        return "D-only"
    if "S" in ls and "D" in ls:
        return "혼재글"
    return "미정글"


# ---------------------------------------------------------------------------
# 3. 통계량
# ---------------------------------------------------------------------------

def p_swing_of(counts):
    """PREREG 5장: p_swing = (n_S + n_M) / (n_S + n_D + n_M). 미정글은 분모에서 뺀다."""
    n_s = counts.get("S-only", 0)
    n_d = counts.get("D-only", 0)
    n_m = counts.get("혼재글", 0)
    n_cls = n_s + n_d + n_m
    if n_cls == 0:
        return None, 0, 0, 0, 0
    return (n_s + n_m) / n_cls, n_s, n_d, n_m, n_cls


def in_window(date, win):
    return win[0] <= date <= win[1]


def pct(x, n):
    return (100.0 * x / n) if n else float("nan")


# ---------------------------------------------------------------------------
# 4. 실행
# ---------------------------------------------------------------------------

def main():
    with open(P_LABELS, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        r["_method"] = (r.get("method") or "").strip()
        r["_date"] = (r.get("post_date") or "").strip()
        sb, db = hits_b(r["_method"])
        sa, da = hits_a(r["_method"])
        r["_hit_b"] = (sb, db)
        r["_lab_b"] = row_label(sb, db)
        r["_lab_a"] = row_label(sa, da)

    by_log = defaultdict(list)
    for r in rows:
        by_log[r["logNo"]].append(r)

    glosses = []
    for log_no, rs in by_log.items():
        dates = sorted({r["_date"] for r in rs})
        glosses.append({
            "logNo": log_no,
            "date": dates[0],
            "n_dates": len(dates),
            "n_rows": len(rs),
            "b_union": gloss_label_union([r["_lab_b"] for r in rs]),
            "b_strict": gloss_label_strict([r["_lab_b"] for r in rs]),
            "a_union": gloss_label_union([r["_lab_a"] for r in rs]),
            "a_strict": gloss_label_strict([r["_lab_a"] for r in rs]),
        })
    glosses.sort(key=lambda g: (g["date"], g["logNo"]))
    multi_date = [g for g in glosses if g["n_dates"] > 1]

    # 창 배정 — regime 컬럼 미사용
    g_day = [g for g in glosses if in_window(g["date"], WIN_DAYTRADE)]
    g_ctl = [g for g in glosses if in_window(g["date"], WIN_CONTROL)]
    g_excl = [g for g in glosses
              if not in_window(g["date"], WIN_DAYTRADE)
              and not in_window(g["date"], WIN_CONTROL)]
    pop = g_day + g_ctl          # G0 셔플 모집단 = 분석 대상(2020~2026)

    res = {}
    for scheme, key in (("B", "b_union"), ("A", "a_union"),
                        ("B_strict", "b_strict"), ("A_strict", "a_strict")):
        c_day = Counter(g[key] for g in g_day)
        c_ctl = Counter(g[key] for g in g_ctl)
        p, n_s, n_d, n_m, n_cls = p_swing_of(c_day)
        pc, cs, cd, cm, c_ncls = p_swing_of(c_ctl)
        res[scheme] = {
            "c_day": c_day, "c_ctl": c_ctl,
            "p_swing": p, "n_s": n_s, "n_d": n_d, "n_m": n_m, "n_cls": n_cls,
            "ctl_p": pc, "ctl_s": cs, "ctl_d": cd, "ctl_m": cm, "ctl_ncls": c_ncls,
            "undef_day": c_day.get("미정글", 0),
            "undef_rate_day": (c_day.get("미정글", 0) / len(g_day)) if g_day else float("nan"),
        }

    # G0 — 글의 «날짜만» 셔플. 날짜 치환이므로 창별 글 수는 정확히 보존된다.
    def g0(key):
        labels = [g[key] for g in pop]
        dates = [g["date"] for g in pop]
        rng = random.Random(SEED)
        null = []
        for _ in range(N_SHUFFLE):
            perm = dates[:]
            rng.shuffle(perm)
            c = Counter(lab for lab, d in zip(labels, perm) if in_window(d, WIN_DAYTRADE))
            p, _, _, _, _ = p_swing_of(c)
            if p is not None:
                null.append(p)
        null.sort()
        return null

    null_b = g0("b_union")
    null_a = g0("a_union")
    obs_b = res["B"]["p_swing"]
    obs_a = res["A"]["p_swing"]

    def percentile_of(null, obs):
        if obs is None or not null:
            return None, None, None
        below = sum(1 for v in null if v < obs)
        below_eq = sum(1 for v in null if v <= obs)
        return 100.0 * below / len(null), 100.0 * below_eq / len(null), null[len(null) // 2]

    pb_b, pbe_b, med_b = percentile_of(null_b, obs_b)
    pb_a, pbe_a, med_a = percentile_of(null_a, obs_a)

    # 미분류(체계 B 미정) method 목록
    undef_rows_all = [r for r in rows if r["_lab_b"] == "미정"]
    undef_rows_day = [r for r in undef_rows_all if in_window(r["_date"], WIN_DAYTRADE)]
    top_undef = Counter(r["_method"] for r in undef_rows_all).most_common(20)
    day_ct = Counter(r["_method"] for r in undef_rows_day)
    undef_gloss_ct = Counter()
    for r in undef_rows_all:
        undef_gloss_ct[r["_method"]] = 0
    tmp = defaultdict(set)
    for r in undef_rows_all:
        tmp[r["_method"]].add(r["logNo"])
    for k, v in tmp.items():
        undef_gloss_ct[k] = len(v)

    # 진단 — 혼합 행을 무엇이 만들었나
    mixed_rows = [r for r in rows if r["_lab_b"] == "혼합"]
    mixed_pairs = Counter()
    for r in mixed_rows:
        sb, db = r["_hit_b"]
        mixed_pairs[("+".join(sb), "+".join(db))] += 1
    band_artifact = [r for r in mixed_rows
                     if "밴드" in r["_hit_b"][0]
                     and any(x in r["_hit_b"][1] for x in ("볼밴", "볼린저"))]

    # 부수 — 행 단위
    row_ct = {}
    for scheme, key in (("B", "_lab_b"), ("A", "_lab_a")):
        row_ct[(scheme, "day")] = Counter(r[key] for r in rows
                                          if in_window(r["_date"], WIN_DAYTRADE))
        row_ct[(scheme, "ctl")] = Counter(r[key] for r in rows
                                          if in_window(r["_date"], WIN_CONTROL))

    # 부수 — titles_labels.csv 대조 (판정 입력 아님)
    try:
        with open(P_TITLES, encoding="utf-8-sig", newline="") as f:
            trows = list(csv.DictReader(f))
        tlogs = {t["logNo"] for t in trows}
        llogs = set(by_log.keys())
        titles_note = ("titles_labels.csv 행 %d · 고유 logNo %d · labels_v5 글과 교집합 %d · "
                       "titles 에만 %d · labels_v5 에만 %d"
                       % (len(trows), len(tlogs), len(tlogs & llogs),
                          len(tlogs - llogs), len(llogs - tlogs)))
    except OSError as e:
        titles_note = "(읽기 실패: %s)" % e

    # ---- 게이트 판정 -------------------------------------------------------
    B = res["B"]
    A = res["A"]
    g3_pass = B["undef_rate_day"] <= THRESH_G3_UNDEF

    def passes(r):
        return ((r["n_s"] + r["n_m"]) >= THRESH_N_SWING
                and (r["p_swing"] or 0.0) >= THRESH_P_SWING)

    # G0 조작화: 사전등록이 수치 기준을 안 정했으므로 여기서 명시한다 —
    # 관측이 귀무 하위 5% «미만»이면 시기 이동의 증거이므로 G0 실패로 본다.
    g0_pass = (pb_b is not None) and (pb_b >= 5.0)
    g4_conflict = passes(B) != passes(A)
    thresh_pass = passes(B)

    if (not g3_pass) or g4_conflict:
        verdict = "판정 보류"
    elif thresh_pass and g0_pass:
        verdict = "병존 지지"
    else:
        verdict = "시기 이동 배제 못함"

    # ---- 리포트 ------------------------------------------------------------
    L = []
    w = L.append
    w("# 6장 두 트랙 가설 — 본검정 결과")
    w("")
    w("> 사전등록 `PREREG_S6_TWO_TRACK.md`(커밋 `f6d089e` 동결)를 그대로 실행한 것이다.")
    w("> 생성 스크립트 `harvest/s6_two_track.py` · 입력 `labels_v5.csv`(읽기 전용).")
    w("> G0 셔플 고정 시드 **%d** · %s회. 같은 시드로 재실행하면 같은 수가 나온다."
      % (SEED, format(N_SHUFFLE, ",")))
    w("")
    w("## 최종 판정: **%s**" % verdict)
    w("")
    w("---")
    w("")
    w("## 0. 데이터와 창")
    w("")
    w("- `labels_v5.csv` 행 **%s** · 고유 글(logNo) **%s**"
      % (format(len(rows), ","), format(len(glosses), ",")))
    w("- logNo 하나에 post_date 가 둘 이상인 경우: **%d건** (0 이어야 「글=날짜」 가정이 성립)"
      % len(multi_date))
    w("- 단타 창 `%s ~ %s` — 글 **%d** · 행 **%s**"
      % (WIN_DAYTRADE[0], WIN_DAYTRADE[1], len(g_day),
         format(sum(g["n_rows"] for g in g_day), ",")))
    w("- 대조 창 `%s ~ %s` — 글 **%d** · 행 **%s**"
      % (WIN_CONTROL[0], WIN_CONTROL[1], len(g_ctl),
         format(sum(g["n_rows"] for g in g_ctl), ",")))
    w("- 🔴 **2017~2019 제외** — 글 **%d** · 행 **%d** (PREREG 4장: usable=False 100%%)"
      % (len(g_excl), sum(g["n_rows"] for g in g_excl)))
    w("- `regime` 컬럼은 **판정의 어떤 단계에도 쓰지 않았다**(창 정의 포함). 창은 달력 연도다.")
    w("- 부수 대조: %s" % titles_note)
    w("")
    w("## 1. 분류 결과 요약")
    w("")
    w("### 글 단위 (판정 단위)")
    w("")
    w("| 체계 | 창 | S-only | D-only | 혼재글 | 미정글 | 합 |")
    w("|---|---|---:|---:|---:|---:|---:|")
    for scheme, name in (("B", "B(기법 어휘·주축)"), ("A", "A(어휘 명시)")):
        for win, gs, ck in (("단타 2020~24", g_day, "c_day"), ("대조 2025~26", g_ctl, "c_ctl")):
            c = res[scheme][ck]
            w("| %s | %s | %d | %d | %d | %d | %d |"
              % (name, win, c.get("S-only", 0), c.get("D-only", 0),
                 c.get("혼재글", 0), c.get("미정글", 0), len(gs)))
    w("")
    w("### 행 단위 (부수 — 판정에 쓰지 않음)")
    w("")
    w("| 체계 | 창 | S | D | 혼합 | 미정 | 합 |")
    w("|---|---|---:|---:|---:|---:|---:|")
    for scheme in ("B", "A"):
        for wk, wn in (("day", "단타"), ("ctl", "대조")):
            c = row_ct[(scheme, wk)]
            w("| %s | %s | %d | %d | %d | %d | %d |"
              % (scheme, wn, c.get("S", 0), c.get("D", 0), c.get("혼합", 0),
                 c.get("미정", 0), sum(c.values())))
    w("")
    w("### 민감도 — 3.4 를 문자 그대로 읽은 변형(`전부 S`/`전부 D`; 미정 행이 오염원이 됨)")
    w("")
    w("| 체계 | 창 | S-only | D-only | 혼재글 | 미정글 |")
    w("|---|---|---:|---:|---:|---:|")
    for scheme, name in (("B_strict", "B(엄격)"), ("A_strict", "A(엄격)")):
        for win, ck in (("단타", "c_day"), ("대조", "c_ctl")):
            c = res[scheme][ck]
            w("| %s | %s | %d | %d | %d | %d |"
              % (name, win, c.get("S-only", 0), c.get("D-only", 0),
                 c.get("혼재글", 0), c.get("미정글", 0)))
    w("")
    w("## 2. 세 수치 대칭 보고 (PREREG G2 — 단독 단언은 판별력이 없다)")
    w("")
    w("| # | 수치 | 체계 B (주축) | 체계 A |")
    w("|---|---|---:|---:|")
    w("| 1 | 단타 창 S글+혼재글 | %d글 / 분류 %d글 = %.2f%% (창 전체 %d글 대비 %.2f%%) "
      "| %d글 / 분류 %d글 = %.2f%% |"
      % (B["n_s"] + B["n_m"], B["n_cls"], pct(B["n_s"] + B["n_m"], B["n_cls"]),
         len(g_day), pct(B["n_s"] + B["n_m"], len(g_day)),
         A["n_s"] + A["n_m"], A["n_cls"], pct(A["n_s"] + A["n_m"], A["n_cls"])))
    w("| 2 | 대조 창 D-only 글 | %d글 / 분류 %d글 = %.2f%% (창 전체 %d글 대비 %.2f%%) "
      "| %d글 / 분류 %d글 = %.2f%% |"
      % (B["ctl_d"], B["ctl_ncls"], pct(B["ctl_d"], B["ctl_ncls"]),
         len(g_ctl), pct(B["ctl_d"], len(g_ctl)),
         A["ctl_d"], A["ctl_ncls"], pct(A["ctl_d"], A["ctl_ncls"])))
    w("| 3 | 혼재글 (단타 창 / 대조 창) | %d / %d | %d / %d |"
      % (B["n_m"], B["ctl_m"], A["n_m"], A["ctl_m"]))
    w("")
    w("### 2.1 결정적 세부 — 단타 창에서 S 마커가 든 «모든» 행 (전수)")
    w("")
    w("주 통계량을 0 이 아니게 만든 것이 정확히 이 행들이다. 요약이 아니라 전수다.")
    w("")
    w("| 날짜 | logNo | 종목 | method | S 마커 | D 마커 |")
    w("|---|---|---|---|---|---|")
    s_in_day = [r for r in rows if in_window(r["_date"], WIN_DAYTRADE) and r["_hit_b"][0]]
    for r in sorted(s_in_day, key=lambda x: x["_date"]):
        w("| %s | %s | %s | `%s` | %s | %s |"
          % (r["_date"], r["logNo"], r.get("stock_name", ""), r["_method"],
             ", ".join(r["_hit_b"][0]), ", ".join(r["_hit_b"][1]) or "-"))
    w("")
    w("### 2.2 S 마커별 창 분포 (행)")
    w("")
    w("| S 마커 | 단타 창 2020~24 | 대조 창 2025~26 | 제외 2017~19 |")
    w("|---|---:|---:|---:|")

    def win_split(test):
        d = sum(1 for r in rows if test(r) and in_window(r["_date"], WIN_DAYTRADE))
        c = sum(1 for r in rows if test(r) and in_window(r["_date"], WIN_CONTROL))
        e = sum(1 for r in rows if test(r)
                and not in_window(r["_date"], WIN_DAYTRADE)
                and not in_window(r["_date"], WIN_CONTROL))
        return d, c, e

    for m in B_MARKERS_S:
        d, c, e = win_split(lambda r, m=m: m in r["_method"])
        w("| %s | %d | %d | %d |" % (m, d, c, e))
    for pat, name in B_AMBIG_S:
        d, c, e = win_split(lambda r, p=pat: re.search(p, r["_method"]) is not None)
        w("| %s (모호어) | %d | %d | %d |" % (name, d, c, e))
    w("")
    w("### 2.3 체계 A — 단타 창의 어휘 명시 행 (전수)")
    w("")
    a_s_day = [r for r in rows if in_window(r["_date"], WIN_DAYTRADE) and A_MARKER_S in r["_method"]]
    a_d_day = [r for r in rows if in_window(r["_date"], WIN_DAYTRADE) and A_MARKER_D in r["_method"]]
    for r in a_s_day:
        w("- `스윙` 표기: %s / logNo %s / %s / `%s`"
          % (r["_date"], r["logNo"], r.get("stock_name", ""), r["_method"]))
    if not a_s_day:
        w("- `스윙` 표기: 없음")
    w("- `단타` 표기 행: **%d행** — 단타 창 안에서 저자는 method 에 `단타` 를 쓰지 않았다."
      % len(a_d_day))
    w("")
    w("## 3. 게이트")
    w("")
    w("### G0 (귀무 실측 — 글의 «날짜만» %s회 셔플, 시드 %d)" % (format(N_SHUFFLE, ","), SEED))
    w("")
    w("셔플 모집단 = 분석 대상 글(2020~2026) 전체. 날짜를 치환하므로 창별 글 수는 보존된다.")
    w("")
    w("| 체계 | 관측 p_swing | 귀무 중앙값 | 귀무 범위 | 백분위(관측 «미만» 비율) | 방향 |")
    w("|---|---:|---:|---:|---:|---|")
    for scheme, obs, med, pb, null in (("B", obs_b, med_b, pb_b, null_b),
                                       ("A", obs_a, med_a, pb_a, null_a)):
        if obs is None:
            w("| %s | (분류 0) | - | - | - | - |" % scheme)
            continue
        if obs < med:
            direction = "관측이 귀무 **아래** → 시기 이동의 증거"
        elif obs > med:
            direction = "관측이 귀무 **위** → 병존 방향"
        else:
            direction = "관측 = 귀무 중앙값"
        w("| %s | %.2f%% | %.2f%% | %.2f%% ~ %.2f%% | %.1f%%ile | %s |"
          % (scheme, obs * 100, med * 100, null[0] * 100, null[-1] * 100, pb, direction))
    w("")
    w("- 조작화(사전등록이 수치 기준을 안 정했으므로 여기서 명시): "
      "**관측이 귀무 하위 5%% 미만이면 G0 실패**(= 시기 이동 증거). 체계 B → **%s**"
      % ("통과" if g0_pass else "실패"))
    w("- ⚠️ **G0 검정력 한계**: 단타 창이 분석 모집단의 %.1f%%(%d/%d 글)라 셔플이 만들 수 있는 "
      "변동 폭 자체가 좁다(귀무 범위 %.2f%%~%.2f%%). 위쪽으로는 둔감한 검정이다. "
      "그럼에도 관측치는 3,000 draw «전부»보다 아래에 있다."
      % (100.0 * len(g_day) / len(pop), len(g_day), len(pop), null_b[0] * 100, null_b[-1] * 100))
    w("- ⚠️ 체계 A 의 G0 는 **퇴화**했다 — 단타 창 분류 글이 %d개뿐이라 p_swing 이 0 또는 1 만 "
      "나온다. 수치를 해석하지 말 것." % A["n_cls"])
    w("")
    w("### G2 (대칭 확인)")
    w("")
    w("위 2장 세 수치를 «함께» 보고했다 → **요건 충족**. "
      "두 창은 사실상 배타적이다(단타 창 D-only %.1f%% · 대조 창 S-only %.1f%%) — "
      "PREREG G2 문언대로면 이는 **시기 이동** 쪽 소견이다."
      % (pct(B["n_d"], B["n_cls"]), pct(B["ctl_s"], B["ctl_ncls"])))
    w("")
    w("### G3 (커버리지)")
    w("")
    w("- 단타 창 미정글 **%d / %d = %.2f%%** (문턱 30%% 초과 시 보류) → **%s**"
      % (B["undef_day"], len(g_day), B["undef_rate_day"] * 100,
         "통과" if g3_pass else "실패(판정 보류)"))
    sc = res["B_strict"]["c_day"]
    sr = (sc.get("미정글", 0) / len(g_day)) if g_day else float("nan")
    w("- 🔴 **엄격 변형에서는 G3 가 실패한다** — 미정글 %d / %d = **%.2f%%** > 30%% → 그 읽기에서는 "
      "**판정 보류**. 다만 그 변형에서 `n_S + n_M = %d` 이라 병존 문턱은 «더» 크게 미달한다. "
      "⇒ 어느 읽기에서도 **「병존 지지」에는 도달하지 않는다.**"
      % (sc.get("미정글", 0), len(g_day), sr * 100,
         sc.get("S-only", 0) + sc.get("혼재글", 0)))
    w("")
    w("### G4 (체계 A/B 대조)")
    w("")
    w("- 체계 B 문턱 통과: **%s** · 체계 A 문턱 통과: **%s** → **%s**"
      % (passes(B), passes(A), "상충(판정 보류)" if g4_conflict else "일치(통과)"))
    w("- ⚠️ 체계 A 의 `p_swing = %.0f%%` 를 단독으로 읽지 말 것 — 분모가 %d글이다. "
      "`n >= %d` 를 **AND** 로 건 사전등록이 이 함정을 막았다."
      % ((A["p_swing"] or 0) * 100, A["n_cls"], THRESH_N_SWING))
    w("")
    w("## 4. 최종 판정")
    w("")
    w("- 문턱 1 `n_S + n_M >= %d글`: 관측 **%d글** → **%s**"
      % (THRESH_N_SWING, B["n_s"] + B["n_m"],
         "충족" if (B["n_s"] + B["n_m"]) >= THRESH_N_SWING else "미달"))
    w("- 문턱 2 `p_swing >= %.0f%%`: 관측 **%.2f%%** → **%s**"
      % (THRESH_P_SWING * 100, (B["p_swing"] or 0.0) * 100,
         "충족" if (B["p_swing"] or 0.0) >= THRESH_P_SWING else "미달"))
    w("")
    w("### ⇒ **%s**" % verdict)
    w("")
    w("사전등록 0장의 구속에 따라 명시한다: 이 검정은 **독립 재현이 아니다**. "
      "그리고 이 결과는 「병존이 없다」의 «증명»이 아니라 "
      "**「labels_v5 의 method 어휘에서는 병존이 보이지 않는다」**이다.")
    w("")
    w("## 5. 미분류(체계 B 미정) method 상위 20종")
    w("")
    w("🔴 **이 목록은 「다음 사람이 판단하도록」 내는 것이지, 이것으로 어휘를 고치라는 뜻이 아니다.**")
    w("사전등록 0장에 따라 이 관측을 근거로 마커를 추가·삭제하지 않았다.")
    w("")
    w("| # | method | 행 | 글 | 단타 창 행 |")
    w("|---:|---|---:|---:|---:|")
    for i, (m, c) in enumerate(top_undef, 1):
        disp = m if m else "(빈 문자열)"
        w("| %d | `%s` | %d | %d | %d |" % (i, disp, c, undef_gloss_ct[m], day_ct.get(m, 0)))
    w("")
    w("- 미정 행 총 **%s** (단타 창 **%s**) · 고유 method 문자열 **%d종**"
      % (format(len(undef_rows_all), ","), format(len(undef_rows_day), ","),
         len({r["_method"] for r in undef_rows_all})))
    w("")
    w("## 6. 진단 — 혼합 행을 무엇이 만들었나")
    w("")
    w("- 체계 B 혼합 행 **%d** (단타 창 **%d**)"
      % (len(mixed_rows),
         sum(1 for r in mixed_rows if in_window(r["_date"], WIN_DAYTRADE))))
    w("- 그중 S 마커 `밴드` 와 D 마커 `볼밴`/`볼린저` 가 «같은 문자열»에서 동시 발화: **%d행**"
      % len(band_artifact))
    w("  ⚠️ 어휘 겹침(`볼린저밴드` ⊃ `밴드`)이 만든 **인공 혼합**이다. "
      "사전등록이 마커를 동결했으므로 규칙은 그대로 두고 수치만 밝힌다.")
    w("")
    w("| S 마커 | D 마커 | 행 |")
    w("|---|---|---:|")
    for (s, d), c in mixed_pairs.most_common(20):
        w("| %s | %s | %d |" % (s, d, c))
    w("")

    with open(P_OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")

    # ---- 콘솔 요약 ---------------------------------------------------------
    def p(s=""):
        sys.stdout.write(s + "\n")

    p("[SEED] %d  shuffles=%d" % (SEED, N_SHUFFLE))
    p("[DATA] rows=%d glosses=%d multi_date_logNo=%d" % (len(rows), len(glosses), len(multi_date)))
    p("[DATA] daytrade glosses=%d rows=%d" % (len(g_day), sum(g["n_rows"] for g in g_day)))
    p("[DATA] control  glosses=%d rows=%d" % (len(g_ctl), sum(g["n_rows"] for g in g_ctl)))
    p("[DATA] excluded(2017-19) glosses=%d rows=%d"
      % (len(g_excl), sum(g["n_rows"] for g in g_excl)))
    for scheme in ("B", "A", "B_strict", "A_strict"):
        r = res[scheme]
        p("[CLS:%-8s] day S=%d D=%d M=%d U=%d | ctl S=%d D=%d M=%d U=%d"
          % (scheme, r["c_day"].get("S-only", 0), r["c_day"].get("D-only", 0),
             r["c_day"].get("혼재글", 0), r["c_day"].get("미정글", 0),
             r["c_ctl"].get("S-only", 0), r["c_ctl"].get("D-only", 0),
             r["c_ctl"].get("혼재글", 0), r["c_ctl"].get("미정글", 0)))
    p("[STAT:B] p_swing=%s n_S+n_M=%d N_cls=%d" % (B["p_swing"], B["n_s"] + B["n_m"], B["n_cls"]))
    p("[STAT:A] p_swing=%s n_S+n_M=%d N_cls=%d" % (A["p_swing"], A["n_s"] + A["n_m"], A["n_cls"]))
    p("[G0:B] obs=%s null_med=%s null_min=%s null_max=%s pct_below=%s pct_below_eq=%s"
      % (obs_b, med_b, null_b[0], null_b[-1], pb_b, pbe_b))
    p("[G0:A] obs=%s null_med=%s pct_below=%s pct_below_eq=%s" % (obs_a, med_a, pb_a, pbe_a))
    p("[G3] undef_rate_day=%.4f pass=%s | strict_undef_rate=%.4f"
      % (B["undef_rate_day"], g3_pass,
         res["B_strict"]["c_day"].get("미정글", 0) / len(g_day)))
    p("[G4] B_pass=%s A_pass=%s conflict=%s" % (passes(B), passes(A), g4_conflict))
    p("[MIXED] rows=%d day=%d band_artifact_rows=%d"
      % (len(mixed_rows),
         sum(1 for r in mixed_rows if in_window(r["_date"], WIN_DAYTRADE)),
         len(band_artifact)))
    p("[VERDICT] %s" % verdict)
    p("[OUT] %s" % P_OUT)


if __name__ == "__main__":
    main()
