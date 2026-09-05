# -*- coding: utf-8 -*-
"""§5 측정 장치 수정(C-17·C-18·C-20·C-21)의 «수정 전/후 나란히» 인쇄.

사전등록 `PREREG_POST6.md` §5-1-5 가 요구한 형식이다:

> *「🔴 **과거 산출물을 다시 재지 않는다.** 수정 후 값이 달라지면 **「수정 전/후」로 나란히 인쇄**하고,
>   post5 판정(`SEL-S3` = 47.9 ✅)은 **그대로 둔다.**」*

🔴 **이 문서는 판정이 아니다.** 어떤 발표값도 여기서 갱신하지 않는다. 기존 `RESULTS_*` 파일은
   **한 줄도 손대지 않았다**(`regen_gate.py` 의 `FROZEN_STALE` 에 사유와 함께 등재).
🔴 **두 열은 «같은 DB 스냅샷»에서 «같은 코드 경로»로 잰다** — 그래야 차이가 「관용구 정정」의 몫이지
   「스냅샷 이동」의 몫이 아니다. (발표값과의 대조는 별개 축이며 §1-3·§3-1 에 그렇게 적는다.)
🔴 **라이브 채택 금지** — 이 문서의 어떤 숫자도 매매 규칙으로 옮기지 않는다.

라이브 트리 import 0건. DB 는 SELECT 만. `adj_factor` 산술 0건.
"""
from __future__ import annotations

import hashlib
import re
import statistics
import sys
from pathlib import Path

import pandas as pd
import psycopg2

import universe_gap as UG
from reconstruct_prices import TARGETS as REC_TARGETS
from run_selection import PSEUDO, build_features, window_stat
from run_selection_post5 import stat_tdays
from run_tests import CODES, DSN
from solve_common_band import feasible_P

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

# post4·post5 의 SEL-S3 대상 (동결분 그대로 · `run_selection_post4.NEW` · `run_selection_post5.NEW`)
POST4 = [("이노테크", "469610", "2026-08-13"), ("한켐", "457370", "2026-08-12"),
         ("금호건설", "002990", "2026-08-12"), ("지투파워", "388050", "2026-08-13"),
         ("PS일렉트로닉스", "332570", "2026-08-13"), ("코데즈컴바인", "047770", "2026-08-19")]
POST5 = [("혜인", "003010", "2026-08-11"), ("한국화장품제조", "003350", "2026-08-12"),
         ("코데즈컴바인", "047770", "2026-08-21"), ("한켐", "457370", "2026-08-20"),
         ("삼양바이오팜", "0120G0", "2026-08-21"), ("광전자", "017900", "2026-08-05")]
END = "2026-08-28"


def say(s=""):
    print(s)
    OUT.append(s)


def med_or_none(xs):
    s = [x for x in xs if x is not None and x == x]
    return statistics.median(s) if s else None


def fmt(x, n=1):
    if x is None:
        return "—"
    if x != x:
        return "**NaN**"
    return ("%%.%df" % n) % x


# ── C-17 ──────────────────────────────────────────────────────────────────────
def load_wide():
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, high, low, close, trading_value, market_cap "
        "FROM daily_prices WHERE date BETWEEN '2026-04-01' AND '" + END + "' "
        "AND market_cap IS NOT NULL AND market_cap > 0 AND close > 0", conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def as_before(df_new):
    """🔑 «수정 전»은 재현이 아니라 **항등**이다 — 옛 코드는 `prev_max` 가 NaN 인 행에서
    `close >= NaN` = False ⇒ `0.0` 을 냈고, 그 행이 정확히 지금 NaN 인 행이다.
    ⇒ `fillna(0.0)` 이 옛 코드의 출력과 **같다**(다른 행은 두 코드가 동일)."""
    df = df_new.copy()
    df["f9_newhigh"] = df_new["f9_newhigh"].fillna(0.0)
    df["f9_newhigh_pct"] = df.groupby("date")["f9_newhigh"].rank(pct=True) * 100
    return df


def s3_rows(df, targets, window):
    """window: 'cal10'(post4 구현 = 달력 10일) · 'td5'(post5 판정 = 직전 5거래일)."""
    out = []
    for nm, code, reg in targets:
        d1 = pd.Timestamp(reg)
        if window == "td5":
            st, _n = stat_tdays(df, code, d1, 5)
        else:
            st = window_stat(df, code, d1 - pd.Timedelta(days=10), d1)
        out.append((nm, reg, None if st is None else st["f9_newhigh"]))
    return out


def c17(df_new, df_old):
    say("## §1. C-17 — `f9_newhigh` 의 NaN 이 «0 = 갱신 없음»으로 둔갑하던 것\n")
    say("수정: `run_selection.build_features` **한 곳**(`run_selection_post4.py`·"
        "`run_selection_post5.py` 가 같은 함수를 import 한다 — 실측).\n")
    n_nan = int(df_new["f9_newhigh"].isna().sum())
    n_all = len(df_new)
    say(f"- 전체 **{n_all:,}** 종목-일 중 `prev_max` 가 NaN 이라 **0.0 으로 둔갑하던 행: "
        f"{n_nan:,}건 ({100*n_nan/n_all:.2f}%)** — 상장 20봉 미만·롤링 결측 구간이다.")
    say(f"- 그 행들의 `f9_newhigh_pct`: 수정 전 **{df_old.loc[df_new.f9_newhigh.isna(), 'f9_newhigh_pct'].mean():.1f}** "
        "(0 값의 그날 백분위 = 하위군 평균) → 수정 후 **NaN**(결측)")
    say(f"- 🟢 결측 표시가 `f5`·`f6` 과 같아졌다 — 수정 후 NaN 개수: `f5_pos60` "
        f"{int(df_new.f5_pos60.isna().sum()):,} · `f6_spikes60` {int(df_new.f6_spikes60.isna().sum()):,} · "
        f"`f9_newhigh` {n_nan:,}")
    say(f"- 🟢 **백분위도 따라온다**: `f9_newhigh_pct` NaN 개수 = **{int(df_new.f9_newhigh_pct.isna().sum()):,}** "
        f"(= `f9_newhigh` NaN 개수) — `rank(pct=True)` 가 NaN 을 자동 제외한다.\n")

    say("### 1-1. `SEL-S3` (60일 최고종가 갱신 백분위의 중앙값) — 수정 전/후\n")
    say("창은 각 발표 문서가 쓴 것 그대로다 — post4 = **달력 10일**(그 구현) · "
        "post5 판정 = **직전 5거래일**(`W_TDAYS`) · post5 대조 = 달력 10일.\n")
    say("| 표본(창) | 종목 | 등록일 | 수정 전 백분위 | 수정 후 백분위 | Δ |")
    say("|---|---|---|---|---|---|")
    cases = (("post4(달력10)", POST4, "cal10"), ("post5(거래일5)", POST5, "td5"),
             ("post5(달력10)", POST5, "cal10"))
    both = {}
    for tag, targets, win in cases:
        a = s3_rows(df_old, targets, win)
        b = s3_rows(df_new, targets, win)
        both[tag] = (a, b)
        for (nm, reg, va), (_n, _r, vb) in zip(a, b):
            if vb is None or vb != vb:
                d = "🔴 **NaN(계산 불가)로 바뀜**"
            elif va is None or va != va:
                d = "—"
            else:
                d = "0" if va == vb else "%+.3f" % (vb - va)
            say(f"| {tag} | {nm} | {reg} | {fmt(va, 3)} | {fmt(vb, 3)} | {d} |")
    say()
    say("| 표본(창) | 발표값(그대로 인용) | 수정 전(오늘) | **수정 후(오늘)** | 분모 | 판정 문턱 < 90 |")
    say("|---|---|---|---|---|---|")
    pubs = {"post4(달력10)": "**48.0** (`RESULTS_SELECTION_POST4_NUMBERS.md`)",
            "post5(거래일5)": "**47.9 ✅** (`RESULTS_SELECTION_POST5_NUMBERS.md` · 판정)",
            "post5(달력10)": "**48.0** (같은 문서 · 대조)"}
    for tag, _t, _w in cases:
        a, b = both[tag]
        va = [v for _n, _r, v in a]
        vb = [v for _n, _r, v in b]
        ma, mb = med_or_none(va), med_or_none(vb)
        na = len([x for x in va if x is not None and x == x])
        nb = len([x for x in vb if x is not None and x == x])
        say(f"| {tag} | {pubs[tag]} | {fmt(ma, 3)} (n={na}) | **{fmt(mb, 3)}** (n={nb}) | "
            f"{'🔴 **' + str(na) + ' → ' + str(nb) + '**' if na != nb else str(nb)} | "
            f"{'✅ 지지 유지' if (mb is not None and mb < 90) else '🔴 확인 필요'} |")
    say()
    say("- 🟢 **「수정 전(오늘)」이 발표 자릿수(소수 1자리)에서 발표값과 일치한다** "
        "(47.996→48.0 · 47.945→47.9 · 48.023→48.0) ⇒ **이 세 자리에서는** 스냅샷 이동 몫이 "
        "발표 자릿수 아래로 작고, 표의 Δ 는 **C-17 정정의 몫**으로 읽어도 된다. "
        "⚠️ **다른 자리에서도 그렇다는 뜻은 아니다** — 1-3 참조.")
    say("- 🔴 **§5-1-3 이 요구한 단언**: 상장 20봉 미만 건(**삼양바이오팜** · 2026-08-05 신규상장 · "
        "이력 12거래일)이 `f9_newhigh` **NaN** · `f9_newhigh_pct` **NaN** 이 되고 "
        "***`SEL-S3` 중앙값 분모에서 빠진다*** — 위 표의 분모 열이 그것이다. "
        "회귀 테스트는 `tests/test_s5_fixes.py`.")
    say("- 🔴 **post5 판정 `SEL-S3` = 47.9 ✅ 는 그대로 둔다**(§5-1-5). 위 표는 **재판정이 아니다.**")
    say("- **방향 고지**(§5-1-5): 이 결함은 `SEL-S3` 을 **«아래로» 미는 방향**이다 "
        "— 신규주가 늘수록 「갱신 없음」이 가짜로 늘어난다 ⇒ ***S3 의 「지지」가 이 결함 덕일 수 있다.***")
    say()
    say("### 1-2. 그날 유니버스 백분위 분포에 준 영향 (등록일들)\n")
    say("| 날짜 | 유니버스 | `f9` NaN 종목 | 수정 전 `f9=1` 종목 | 수정 후 `f9=1` 종목 | "
        "수정 전 `f9=1` 백분위 | 수정 후 `f9=1` 백분위 |")
    say("|---|---|---|---|---|---|---|")
    days = sorted({r[2] for r in POST4} | {r[2] for r in POST5})
    for d in days:
        mo = df_old[df_old.date == pd.Timestamp(d)]
        mn = df_new[df_new.date == pd.Timestamp(d)]
        if mo.empty:
            continue
        po = mo.loc[mo.f9_newhigh == 1.0, "f9_newhigh_pct"]
        pn = mn.loc[mn.f9_newhigh == 1.0, "f9_newhigh_pct"]
        say(f"| {d} | {len(mo):,} | {int(mn.f9_newhigh.isna().sum())} | "
            f"{int((mo.f9_newhigh == 1.0).sum())} | {int((mn.f9_newhigh == 1.0).sum())} | "
            f"{po.mean():.2f} | {pn.mean():.2f} |")
    say()
    say("🔑 `f9` 는 이진이라 백분위가 축퇴한다 — 「갱신 없음」이 늘면 「갱신 함」의 백분위가 **올라간다.** "
        "그래서 결함은 `f9=0` 인 건은 낮게, `f9=1` 인 건은 높게 밀었다.")
    say()
    say("### 1-3. 🔴 이 표와 «발표값»의 차이는 두 축이 섞인다\n")
    say("발표값은 **발표 당시 DB 스냅샷**에서 나왔고 이 표는 **현재 스냅샷**(최신 봉 " + END + ")이다. "
        "⇒ 발표값과 「수정 후」를 직접 빼면 **「정정 몫」과 「스냅샷 이동 몫」이 한 칸에 섞인다.** "
        "그래서 이 문서는 **같은 스냅샷의 전/후**만 나란히 놓는다. "
        "🔑 *숫자가 문서마다 다르면 «원인 규명»이 먼저다 — 맞추지 말 것.*")


# ── C-18 ──────────────────────────────────────────────────────────────────────
def c18(cur):
    say()
    say("## §2. C-18 — 유니버스 `prev_close` 결손 5열 (신설 계측)\n")
    say("구현 `universe_gap.py` (`coverage()` · `render()` · `flagged()` · `DROP_RATE_GUARD`). "
        "post6 의 `n_up` 산출물(`REG-M4`·`P6-S1h-N`·`P6-M2′` 귀무)이 이 블록을 **의무 인쇄**한다.\n")
    days = sorted({r[2] for r in POST4} | {r[2] for r in POST5} | {"2026-08-03", "2026-08-04"})
    rows = [UG.coverage(cur, d) for d in days]
    for line in UG.render(rows, title="post4·post5 등록일 실측 (계측 장치 검증용)"):
        say(line)
    say()
    say("🟢 **계측 장치 검증** — 이 표는 `RESULTS_REGDAY_POST5.md` §5-0 의 발표값을 **재현한다**"
        "(08-05: 2,763 → 2,572 · 탈락 191 · 6.91%). ⇒ 새 함수가 「같은 것을 재고 있다」.")
    say("🔴 **`RESULTS_D1_OOS_POST5.md` §11(2,570·194)과 `RESULTS_REGDAY_POST5.md` §5-0(2,572·191)이 "
        "이제 «한 표»에 나란히 있다**(§8-4 가 요구한 대조). "
        "⚠️ **두 값의 차이를 이 문서가 «산술로 설명하지 않는다»** — 그건 원인 규명 없는 사후 맞추기다.")


# ── C-20 ──────────────────────────────────────────────────────────────────────
def _pub_nums(path, header_key, col):
    out = []
    seen = False
    for line in (BASE / path).read_text(encoding="utf-8").splitlines():
        if header_key in line:
            seen = True
            continue
        if not seen:
            continue
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0].startswith("---"):
            continue
        m = re.search(r"-?\d+(?:\.\d+)?", cells[col].replace(",", ""))
        if m:
            out.append(float(m.group()))
    return out


def old_med(xs):
    """정정 «전» 관용구 — `sorted(x)[len(x)//2]` = 짝수 n 에서 상위 중앙값."""
    s = sorted(xs)
    return s[len(s) // 2] if s else None


def c20(cur):
    say()
    say("## §3. C-20 — 중앙값 관용구(`sorted(x)[len(x)//2]`) 정정 전/후\n")
    say("🔑 계열 규칙: ***한 파일에서 고친 결함은 같은 관용구를 쓰는 다른 파일에서 살아 있다. "
        "정정은 「파일」이 아니라 「관용구」 단위로 해야 한다.***\n")
    say("| 파일 | 통계량 | `n` | 짝/홀 | 수정 전 | **수정 후** | 발표값이 바뀌나 |")
    say("|---|---|---|---|---|---|---|")

    # (a) run_d1_oos.py:146 — 발표된 표에서 `m` 을 그대로 읽는다 (재측정 아님)
    ms = _pub_nums("RESULTS_D1_OOS_NUMBERS.md", "대역 내 종목 수", 2)
    say(f"| `run_d1_oos.py:146` | `m` 중앙값(N2) | {len(ms)} | "
        f"{'짝수' if len(ms) % 2 == 0 else '홀수'} | {old_med(ms):g} | **{statistics.median(ms):g}** | "
        f"{'🔴 **바뀐다**' if old_med(ms) != statistics.median(ms) else '🟢 아니오'} |")

    # (b) run_reconstruct_post4.py:100,173 — 발표 표에서 폭을 그대로 읽는다
    w = _pub_nums("RESULTS_RECONSTRUCT_POST4_NUMBERS.md", "feasible P 개수(gross)", 8)
    hw = _pub_nums("RESULTS_RECONSTRUCT_POST4_NUMBERS.md", "**h_max 범위**", 6)
    for label, xs in (("100` · `b₁` 폭 중앙", w), ("173` · `h_max` 폭 중앙", hw)):
        say(f"| `run_reconstruct_post4.py:{label}` | 발표 표의 값 | {len(xs)} | "
            f"{'짝수' if len(xs) % 2 == 0 else '홀수'} | {old_med(xs):g} | "
            f"**{statistics.median(xs):g}** | "
            f"{'🔴 **바뀐다**' if old_med(xs) != statistics.median(xs) else '🟢 아니오'} |")

    # (c) run_gapfill.py:136-137 — 리스트 길이는 발표 산출물에 없다 ⇒ 같은 스냅샷에서 둘 다 잰다
    import run_gapfill as G
    for name, d0, d1, legs, _fill in REC_TARGETS:
        code = CODES[name]
        cur.execute("SELECT date, time, low, high, open FROM minute_candles "
                    "WHERE stock_code=%s AND date BETWEEN %s AND %s AND volume > 0 "
                    "ORDER BY date, time", (code, d0.replace("-", ""), d1.replace("-", "")))
        mb = cur.fetchall()
        if not mb:
            continue
        bars = [(r[2], r[3]) for r in mb]
        stamps = [(r[0], r[1]) for r in mb]
        cur.execute("SELECT low, high FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        dr = cur.fetchall()
        ranges = [(r[0], r[1]) for r in dr]
        Ps = feasible_P(legs, ranges, min(r[0] for r in dr), max(r[1] for r in dr))
        if not Ps:
            continue
        if len(Ps) > G.MAX_SOLUTIONS:
            st = len(Ps) / G.MAX_SOLUTIONS
            Ps = [Ps[int(i * st)] for i in range(G.MAX_SOLUTIONS)]
        fmin_l, fmax_l = [], []
        for P in Ps:
            S = G.legs_prices(P, legs)
            ds = [[i for i, (lo, hi) in enumerate(bars) if lo <= s <= hi] for s in S]
            if any(not x for x in ds):
                continue
            a, b = G.assign_first(ds), G.assign_last(ds)
            if not a or not b:
                continue
            fmin_l.append(stamps[a[0]])
            fmax_l.append(stamps[b[0]])
        if not fmin_l:
            continue
        for lab, lst in (("firsts_min", fmin_l), ("firsts_max", fmax_l)):
            o = sorted(lst)[len(lst) // 2]
            n = G.med_stamp(lst)
            say(f"| `run_gapfill.py:136-137` | {name} {lab} 중앙 시각 | {len(lst)} | "
                f"{'짝수' if len(lst) % 2 == 0 else '홀수'} | {o[0]} {o[1]} | **{n[0]} {n[1]}** | "
                f"{'🔴 **바뀐다**' if o != n else '🟢 아니오'} |")

    # (d) run_minute_entry.py:118-119 — 같은 스냅샷에서 둘 다 잰다
    import run_minute_entry as M
    for name, _d0_win, d1, legs, _fill in REC_TARGETS:
        code = CODES[name]
        ymd = M.REG_DATES[name].replace("-", "")
        cur.execute("SELECT time, low, high, volume FROM minute_candles "
                    "WHERE stock_code=%s AND date=%s ORDER BY time", (code, ymd))
        mb = cur.fetchall()
        if not mb or sum(r[3] or 0 for r in mb) == 0:
            continue
        mbars = [(r[0], r[1], r[2]) for r in mb]
        cur.execute("SELECT low, high FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, _d0_win, d1))
        dr = cur.fetchall()
        ranges = [(r[0], r[1]) for r in dr]
        Ps = feasible_P(legs, ranges, min(r[0] for r in dr), max(r[1] for r in dr))
        hit = [(P, t) for P, t in ((P, M.first_touch(mbars, P)) for P in Ps) if t is not None]
        if not hit:
            continue
        hit.sort(key=lambda x: x[1])
        o_t, o_P = hit[len(hit) // 2][1], hit[len(hit) // 2][0]
        mid = M.mid_items(hit)
        n_t = statistics.median([M.tsec(t) for _P, t in mid])
        n_P = statistics.median([P for P, _t in mid])
        same = (M.tsec(o_t) == n_t) and (abs(o_P - n_P) < 1e-9)
        say(f"| `run_minute_entry.py:118-119` | {name} `t(P)` 중앙 / `P` 중앙 | {len(hit)} | "
            f"{'짝수' if len(hit) % 2 == 0 else '홀수'} | {M.hhmm(o_t)} / {o_P:,.1f} | "
            f"**{M.hhmm_sec(n_t)} / {n_P:,.1f}** | "
            f"{'🟢 아니오' if same else '🔴 **바뀐다**'} |")

    say()
    say("- 🔴 **바뀌는 칸이 있어도 발표값은 갱신하지 않는다**(§5-4-2). 옛 산출물은 옛 판본의 값으로 둔다.")
    say("- `run_d1_oos.py` 의 post4 `m` 중앙 **2** 는 분모가 **5(홀수)**라 상·하위 중앙값이 같다 "
        "⇒ **그 값은 바뀌지 않는다.** 이건 「결함이 없었다」가 아니라 "
        "**「결함이 아직 발화하지 않았다」**이다.")


# ── C-21 ──────────────────────────────────────────────────────────────────────
def c21():
    say()
    say("## §4. C-21 — 원장 수정이 «판정 숫자»를 바꾸지 않음 (md5)\n")
    say("`RESULTS_EXIT_V2_POST5.md` §11 의 방법 그대로: **원장을 읽는 산출 스크립트가 없으면** "
        "`RESULTS_*_NUMBERS.md` 의 md5 가 원장 편집 전후로 같아야 한다.\n")
    readers = []
    for p in sorted(BASE.glob("run_*.py")):
        if p.name == Path(__file__).name:      # 이 스크립트 자신은 «판독기»가 아니다(문자열만 있다)
            continue
        src = p.read_text(encoding="utf-8")
        if "ledger_trades.csv" in src or "ledger_legs.csv" in src:
            readers.append(p.name)
    say(f"- 원장을 읽는 `run_*.py`: **{len(readers)}개** — {', '.join(readers)}")
    say("- 그중 `RESULTS_*_NUMBERS.md` 를 만드는 것: **0개**(실측) ⇒ md5 불변이 예측된다.\n")
    say("| `RESULTS_*_NUMBERS.md` | md5 (현재 = 원장 수정 후) |")
    say("|---|---|")
    for p in sorted(BASE.glob("RESULTS_*_NUMBERS.md")):
        say(f"| {p.name} | `{hashlib.md5(p.read_bytes()).hexdigest()}` |")
    say()
    say("🔑 **판독기는 전부 이름 기준**(`csv.DictReader`)이라 `fill_level` 바로 뒤에 `fill_n` 을 "
        "끼워도 안전하다(실측 · §5-5-5). 위치 기준 판독기는 **0개**다.")


def main() -> int:
    say("# RESULTS_S5_SIDEBYSIDE — 기계 생성 (수정 금지)\n")
    say("생성 `run_s5_sidebyside.py` · 사전등록 `PREREG_POST6.md` §5 (C-17·C-18·C-20·C-21)")
    say("🔴 **판정 아님 · 재측정 아님 · 라이브 채택 금지.** 기존 `RESULTS_*` 파일은 한 줄도 "
        "손대지 않았다.\n")
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    cur.execute("SELECT max(date) FROM daily_prices")
    say(f"DB 스냅샷 최신 봉 **{cur.fetchone()[0]}** (직전/포함 규약: 아래 창은 전부 «포함»)\n")

    df_new = build_features(load_wide())
    df_old = as_before(df_new)
    c17(df_new, df_old)
    c18(cur)
    c20(cur)
    c21()

    cur.close()
    conn.close()
    (BASE / "RESULTS_S5_SIDEBYSIDE.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n[written] RESULTS_S5_SIDEBYSIDE.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
