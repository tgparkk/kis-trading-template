# -*- coding: utf-8 -*-
"""매수 사다리 「체결 차수 ↔ 낙폭」 정렬 축 — **10번째 글 누적 재계산** (`LAD-T2`·`T3` · `LAD-P1`·`P3` · 🔴 `LAD-T1`·`LAD-P2` = 종결).

`run_ladder_tranche_post9.py` 의 얇은 승계판 — 판정 로직 신설 0.
  · 통계 핵(`pairset`·`statV`·`permute_null`·`run_axis`) = `run_ladder_tranche.py`
  · 가드 함수(`guard_a_fires`·`median`) = `run_ladder_tranche_post6.py` (🔴 `verdict_t1` 은 쓰지 않는다 — `LAD-T1` 종결)
  · 누적 목록 28건 · 건별 원표 함수 `build_rows` = `run_ladder_tranche_post7.py`
  · post8 `approx` 갈래 정의 · post7 「절단 시점 값」 인용 · 창 헬퍼(`cross_counts`·`window_bounds`) = `run_ladder_tranche_post8.py`
  · post9 누적 풀 37건 · post9 걸침 표 = `run_ladder_tranche_post9.py`(import 만 · `main` 은 부르지 않는다)
  🔴 다섯 파일 다 **수정하지 않는다**(import 만). ⚠️ `LAD.OUT` 재지정은 `main()` 안에서만 한다.

준거(전부 동결본 · 규칙 변경 0):
  · `PREREG_LADDER_TRANCHE.md` §4·§5 · `PREREG_POST6.md` §1-4·§1-5·§1-6·§2-4 · §4 #21~#24
  · `PREREG_POST8.md` `D-3`·`D-5`·`D-7`·`D-9`(3회차) · `PREREG_POST9.md` §1 `P9-공통독법` · §6 `P9-스탬프통일`(post10 부터 구속)
  · 🆕 `PREREG_POST10.md` — §0-1 라이브 채택 금지 · §3 `P10-기업행위봉`(`F-3`) · §5 `P10-앵커종결`(`F-5`) · §6 `P10-approx누적범위`(`F-6`)
  · `PREDECISION_2026-10-04_post10.md` PD-1 · PD-2 · PD-3 · PD-12 · PD-21 · PD-23(`LAD-` 행) · PD-25(`D-7` 3회차) · PD-27 (마)(바) ·
    PD-33 · PD-35 · PD-36 · PD-37(`F-5`) · PD-43(🔒 #1 ⓐ)

🔴 **`F-5`(🔒 2026-10-04)**: `LAD-T1` = 종결 · **`V`·`p` 계산 0**(2-a (ㄴ) 중단) · `LAD-P2` 조각 종결(계산 0) · `LAD-T3`·`P6-창5절단가드-B` 의
   귀결 문장 중 종결 항목을 가리키는 부분에 「귀결 대상 종결(`F-5`)」 · `LAD-T2` 는 계속(동결문대로 계산).
🔴 `D-9` ① = `ladder_post10/read_stamp.json`(키 `first_read_kst`·`timezone`·`fingerprint` · `P9-스탬프통일` · 같은 지문이면 재사용).
🔴 post8 verifier A-B2(`ff541cf`) 반복 금지 — `D-5` 표의 **모든 갈래 행에 `(이름, n, 답)` 세 쪽**을 인쇄한다.
🔴 라이브 채택 대상이 아니다(`PREREG_POST10.md` §0-1). 라이브 트리 import 0건 · DB 는 SELECT 만 · `adj_factor` 산술 0건 ·
   새 예측 0 · 등급 이름을 적지 않는다.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from math import factorial
from pathlib import Path

import psycopg2

from run_tests import DSN

import run_ladder_tranche as LAD
from run_ladder_tranche import DELTA, NPERM, NULL_SEED, PAIR_THRESHOLD, pairset, permute_null, run_axis, statV
from run_ladder_tranche_post6 import GUARD_A_DEN, GUARD_A_NUM, TRUNC5_MIN_BARS, guard_a_fires, median
import run_ladder_tranche_post6 as P6
import run_ladder_tranche_post7 as P7
from run_ladder_tranche_post7 import ITEMS as ITEMS_CUM28, build_rows
import run_ladder_tranche_post8 as P8
from run_ladder_tranche_post8 import (
    APPROX_BRANCHES as APPROX_BRANCHES_POST8,
    BOUNDARY,
    END7,
    HDR,
    POST7_TRUNC_ASOF,
    SEP,
    cross_counts,
    window_bounds,
)
import run_ladder_tranche_post9 as P9

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
NUMBERS = BASE / "RESULTS_LADDER_TRANCHE_POST10_NUMBERS.md"
STAMP_DIR = BASE / "ladder_post10"

END = "2026-10-02"          # 창 종료 (PD-1 · 발행 당일 봉 포함 · 전 축)
PUB10 = "2026-10-02"        # 10번째 글 발행일 = **금요일 = 거래일** (B-1 ⇒ 창A 는 발행 당일에서 끝난다)
END9 = P9.END               # post9 창 종료 — 계열 인용
SWEEP_D1 = "2026-10-06 15:35"   # 10-02 봉의 D+1 sweep (10-05 개천절 대체공휴일 · PD-27 (마))
WIN_LO = "2026-08-12"       # 착수 직전 프로브 창 시작(PD-27 (마) 2 (b))
LOG10 = "224429747319"
LAUNCH_CAP = "2026-10-08 23:59:59"   # `P10-착수상한` (`F-4`)

# 계열 인쇄값 (나란히 인쇄용 · 판정에 쓰지 않는다)
POST9_T3_P = 0.4091
POST9_T2_P = (0.3204, 0.6760)       # post9 §4 원축 · 정규화축(같은 쌍 집합)
POST8_T3_P = P9.POST8_T3_P
LAD_P2_LO, LAD_P2_HI = P8.LAD_P2_LO, P8.LAD_P2_HI   # 종결 — 인쇄하지 않는다(상수 승계 확인용)
POST9_GA_EXACT_REACHED = False          # post9 `D-7` 2회차 `exact` 1/… «미도달»(`RESULTS_LADDER_TRANCHE_POST9_NUMBERS.md` §1-1)

N_NEW_POST10 = 9            # 🔴 가드-A 분모 = 「이번 글 신규 건」(`PREREG_POST8.md` §7 (나) 1 · PD-25)
N_EXACT_POST10 = 9          # 주 표본 (`approx` 0 · `none` 0)

# (종목, 코드, 등록일, 차수 N, 글, 발행일, 두번째 사이클?, 비고) — `INTAKE_2026-10-04_post10.md` §1 순서(신규 9) · 원장 post10
ITEMS_POST10_NEW = [
    ("라온시큐어",   "042510", "2026-09-15", 4, "post10", PUB10, False, "`partial`/4·완결·`exact`·`MIX`"),
    ("범한퓨얼셀",   "382900", "2026-09-16", 1, "post10", PUB10, True,
     "first_only·`exact`·완결·🔂재진입(post7 #13 · post8 #4 뒤)"),
    ("서산",         "079650", "2026-09-09", 5, "post10", PUB10, True,
     "`partial`/5·`exact`·완결·🔂재진입(post7 #7 뒤)·🔀 창5 제도 경계 걸침"),
    ("샌즈랩",       "411080", "2026-09-14", 3, "post10", PUB10, False,
     "`partial`/3·`exact`·`MIX`·미완결(사이클 2)·🔀 항목 내 2 사이클(🔒 #1 ⓐ · 재등록 09-29 날짜 기록만)"),
    ("성호전자",     "043260", "2026-09-14", 1, "post10", PUB10, False, "first_only·`exact`·완결(⚠️ 약함)"),
    ("HT로보틱스",   "396300", "2026-09-18", 3, "post10", PUB10, False,
     "`partial`/3·`exact`·미완결·DB 이름 세아메카닉스(확인 6)"),
    ("한켐",         "457370", "2026-09-16", 1, "post10", PUB10, True,
     "first_only·`exact`·미완결·🔂재진입(post4 #2 · post5 #4 뒤)"),
    ("뷰노",         "338220", "2026-09-29", 1, "post10", PUB10, False,
     "first_only·`exact`·완결(⚠️ 약함)·🔴 창5 절단 4/5"),
    ("우리로",       "046970", "2026-09-18", 1, "post10", PUB10, True,
     "first_only·`exact`·미완결·🔂재진입(post8 #3 뒤)"),
]
ITEMS_POST9_POOL = list(P9.ITEMS)                       # post9 누적 37건(그 파일 목록 그대로)
ITEMS = ITEMS_POST9_POOL + ITEMS_POST10_NEW             # 46건

OUT_OF_REGDAY_AXIS = [
    ("한컴위드", "054920", 3, "`TP`",
     "후속(post9 #6) — PD-2 이중계상 금지 · 그 등록 사건(09-15)은 post9 행(주 표본 · N = 2)이 이미 들고 있다 · 🔀 재등록 09-23 은 "
     "🔒 #1 ⓐ 로 등록 사건이 아니다(날짜 기록만) · 원장 `partial`/3 = 서술 최대 차수(후속이라 판정 효과 0)"),
    ("코데즈컴바인", "047770", 2, "`TP`",
     "후속(post8 #9) — PD-2 · 그 등록 사건은 post8 행이 들고 있다 · 「1~4차 분할매도(지난주)」 뒤 본전 위협 전량매도"),
    ("빛샘전자", "072950", 1, "`TP`",
     "후속(post9 #4) — PD-2 · 그 등록 사건(09-14)은 post9 행이 들고 있다 · 「1~7차 → 8차」 연결"),
]
FIRST_ONLY_POST10_NEW = ["범한퓨얼셀", "성호전자", "한켐", "뷰노", "우리로"]
PRIOR_CYCLE_FLAG_POST10 = {"라온시큐어": "0", "범한퓨얼셀": "1", "서산": "1", "샌즈랩": "0", "성호전자": "0",
                           "HT로보틱스": "0", "한켐": "1", "뷰노": "0", "우리로": "1"}      # PD-3 · 4/9

# 🔴 PD-27 (바) 표 — `LAD-` 창5 칸(계산 «전» 구성 · 경계 전/후 봉수) + 누적 풀 옛 걸침 창(옛 산출물이 이미 인쇄 · 재인쇄)
PD27_CROSS5 = dict(P9.PD27_CROSS5)
PD27_CROSS5[("서산", "post10")] = (3, 2)
PD27_ALL_AFTER5 = dict(P9.PD27_ALL_AFTER5)
for _nm in ("라온시큐어", "범한퓨얼셀", "샌즈랩", "성호전자", "HT로보틱스", "한켐", "우리로"):
    PD27_ALL_AFTER5[(_nm, "post10")] = (0, 5)
PD27_ALL_AFTER5[("뷰노", "post10")] = (0, 4)

ADMIN_PROBE = [
    "보관 `D:/archive/tasso-program-journal-20261004/probes_precalc_1007/` — 착수 조건 관측 3회(2026-10-07 19:35:46 · 19:36:08 · "
    "19:36:31 KST)",
    "3/3 동일: 10-06 행수 **2,768** × 3 · 10-07 행수 **2,767** × 3 · 창 구간(08-12~10-02) `min(updated_at)` = "
    "**2026-10-07 15:45:21.82908** · `max` = **2026-10-07 15:46:38.364963**",
]

# 🔴 `PREREG_POST10.md` §0-1 문언 그대로(`:56`·`:58`) — 시험이 파일 줄과 축자 대조한다
LIVE_39 = ("> *「🔴 **라이브 채택 금지.** 저자가 *\"사람이 할 일은 종목 고르는 것까지\"* 라고 적었다. 후보 선정이 재량이면 "
           "규칙을 복원해도 자동화 대상이 아니다. 이 검정의 산출물은 **기록**이지 전략 후보가 아니다.」*")
LIVE_41 = ("⇒ `PREREG_POST8.md:26` 그대로 — *「이 문서가 만드는 **어떤 조항·규약·범주도** 라이브 전략·파라미터 변경의 근거가 "
           "아니다」*. 🔴 *등급이 「성립」이어도 라이브 채택 금지는 그대로다*(`PREREG_GRADE_TIERS.md:30`). `PREREG.md:14`"
           "(§0 1번 · 성과·엣지 추정 금지)도 그대로다. 라이브 8전략·페이퍼 전략과 **무관**하다(`PREREG_POST9.md:36-41` 축자 승계).")
LIVE_HEAD = "🔴 **라이브 채택 금지 — `PREREG_POST10.md` §0-1 문언 그대로**(`PREREG.md:15` 인용 · `:56`·`:58`):"
T1_CLOSED = ("해당 없음 — 🔒 종결(2026-10-01 폐기 접수 · `PREREG_ANCHOR_REDESIGN.md:253` · 기록 보존) — 핵심 수: 계산 0회")


def say(s=""):
    print(s)
    OUT.append(s)


def comp_of(ns, ps):
    """비교가능 쌍 수(N 이 서로 다른 쌍) — 🔴 `V` 는 세지 않는다(`LAD-T1` 종결 · `F-5` 2-a (ㄴ))."""
    return sum(1 for h, lo in ps if ns[h] != ns[lo])


def read_stamp(fp: dict, now_kst: str, stamp_dir: Path = STAMP_DIR):
    """`D-9` ① = 이 지문을 «처음» 읽은 실행의 KST 시각. 같은 지문이면 파일을 다시 쓰지 않는다.
    반환 = (① 시각, 재사용 여부)."""
    p = stamp_dir / "read_stamp.json"
    prev = None
    if p.exists():
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = None
    if prev and prev.get("fingerprint") == fp and prev.get("first_read_kst"):
        return prev["first_read_kst"], True
    stamp_dir.mkdir(exist_ok=True)
    p.write_text(json.dumps(dict(fingerprint=fp, first_read_kst=now_kst, timezone="Asia/Seoul"),
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return now_kst, False


def t2_stats(sub):
    """`LAD-T2`(동결문 · 계속) — `DD/sigma20` 정규화축. 반환 = 값 묶음(출력은 호출자가 한다)."""
    ns_s = [r["N"] for r in sub]
    nx_s = [r["dd5"] / (100 * r["sig"]) for r in sub]
    med_sig = statistics.median([r["sig"] for r in sub])
    ps_dd, drop_dd = pairset([r["dd5"] for r in sub], DELTA)
    v_o, c_o = statV(ns_s, ps_dd)
    vs_o, cs_o, z_o = permute_null(ns_s, ps_dd)
    p_o = float((vs_o <= v_o).mean())
    ps_same = [(h, lo) if nx_s[h] > nx_s[lo] else (lo, h) for h, lo in ps_dd]
    v_n, c_n = statV(ns_s, ps_same)
    vs_n, cs_n, z_n = permute_null(ns_s, ps_same)
    p_n = float((vs_n <= v_n).mean())
    dn = DELTA / (100 * med_sig)
    ps_n2, drop_n2 = pairset(nx_s, dn)
    v_n2, c_n2 = statV(ns_s, ps_n2)
    vs_n2, cs_n2, z_n2 = permute_null(ns_s, ps_n2)
    p_n2 = float((vs_n2 <= v_n2).mean())
    return dict(n=len(sub), med_sig=med_sig, dn=dn, drop_dd=drop_dd, drop_n2=drop_n2,
                o=(v_o, c_o, float(vs_o.mean()), p_o, z_o / len(vs_o), float(cs_o.mean())),
                s=(v_n, c_n, float(vs_n.mean()), p_n, z_n / len(vs_n), float(cs_n.mean())),
                d=(v_n2, c_n2, float(vs_n2.mean()), p_n2, z_n2 / len(vs_n2), float(cs_n2.mean())))


def main(numbers: Path = NUMBERS, stamp_dir: Path = STAMP_DIR):  # noqa: C901
    OUT.clear()
    LAD.OUT = OUT              # 🔴 표 행(`run_axis`)을 이 실행의 버퍼로 — 실행 시점에만 묶는다
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    # ── 읽은 시각 재료 (D-9) ────────────────────────────────────────────
    cur.execute("SELECT to_char(now() AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')")
    now_kst = cur.fetchone()[0]
    cur.execute("SELECT max(date) FROM daily_prices")
    db_max = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (db_max,))
    db_max_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (END,))
    end_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices WHERE date BETWEEN %s AND %s",
                (WIN_LO, END))
    w_n, w_umin, w_umax = cur.fetchone()
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices WHERE date = %s", (END,))
    e_umin, e_umax = cur.fetchone()
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN '2026-07-01' AND %s ORDER BY date", (END,))
    cal = [r[0] for r in cur.fetchall()]

    rows = build_rows(cur, ITEMS, cal, END)

    ax_umin = ax_umax = ax_lo = None
    ax_n = 0
    sig_lo = {}
    for r in rows:
        cur.execute("SELECT min(date) FROM (SELECT date FROM daily_prices WHERE stock_code=%s AND date < %s "
                    "ORDER BY date DESC LIMIT 21) t", (r["code"], r["d0"]))
        lo = cur.fetchone()[0] or r["d0"]
        sig_lo[(r["nm"], r["post"])] = lo
        cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices "
                    "WHERE stock_code=%s AND date BETWEEN %s AND %s", (r["code"], lo, END))
        n_, a_, b_ = cur.fetchone()
        ax_n += n_
        ax_umin = a_ if ax_umin is None or a_ < ax_umin else ax_umin
        ax_umax = b_ if ax_umax is None or b_ > ax_umax else ax_umax
        ax_lo = lo if ax_lo is None or lo < ax_lo else ax_lo

    fp = dict(max_date=str(db_max), max_rows=int(db_max_rows), end_rows=int(end_rows), win=[WIN_LO, END],
              win_n=int(w_n), win_min_u=str(w_umin), win_max_u=str(w_umax), axis_lo=str(ax_lo), axis_n=int(ax_n),
              axis_min_u=str(ax_umin), axis_max_u=str(ax_umax), end_min_u=str(e_umin), end_max_u=str(e_umax))
    stamp, reused = read_stamp(fp, now_kst, stamp_dir)
    print(f"[run] 이번 실행 시각(KST) = {now_kst} · 산출물 ① = {stamp} "
          f"({'read_stamp.json 재사용 — 지문 동일 · 파일 재기록 없음' if reused else '새로 박음'})")

    say("# RESULTS_LADDER_TRANCHE_POST10_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_ladder_tranche_post10.py` · 통계 핵·표 포맷 `run_ladder_tranche.py` · 가드 함수 "
        "`run_ladder_tranche_post6.py` · 누적 목록 28건·`build_rows` `run_ladder_tranche_post7.py` · post8 `approx` 갈래·post7 절단 인용·창 헬퍼 "
        "`run_ladder_tranche_post8.py` · post9 누적 풀 37건·걸침 표 `run_ladder_tranche_post9.py` 에서 import (**다섯 파일 다 수정하지 않았다**)")
    say("사전등록 `PREREG_LADDER_TRANCHE.md`(2026-08-22 동결) · `PREREG_POST6.md` §1-4·§1-5·§1-6·§2-4·§4 #21~#24 · "
        "`PREREG_POST8.md`(`D-3`·`D-5`·`D-7`·`D-9` · 3회차) · `PREREG_POST9.md`(§1 · §6) · 🆕 `PREREG_POST10.md`(동결 `522d6dc` · "
        "§3 `F-3` · §5 `F-5` · §6 `F-6`) · `PREDECISION_2026-10-04_post10.md` PD-1·PD-2·PD-3·PD-12·PD-21·PD-23·PD-25·PD-27·PD-33·PD-35·PD-36·PD-37·PD-43")
    say(f"`delta` = {DELTA}%p · `NULL_SEED` = {NULL_SEED} · 순열 표본 {NPERM:,} · "
        f"판정 문턱 = 누적 비교가능 쌍 {PAIR_THRESHOLD} — **넷 다 동결 그대로 손대지 않았다**")

    # ── §0 ──────────────────────────────────────────────────────────────
    say()
    say("## §0. 실행 환경 · 창 종료 규약 · 읽은 시각 박제 (PD-1 · `PREREG_POST8.md` §9 D-9 · `P9-스탬프통일`)\n")
    say(f"**창 종료 {END} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · `END` · 전 축(`WRC-` 포함) · PD-1**")
    say(f"**실행 시 `max(date)` = {db_max} · 그 날짜 행수 {db_max_rows:,} — 기록만(창 아님)** · "
        f"창 종료 {END} 행수 **{end_rows:,}**")
    say()
    say(LIVE_HEAD)
    say(LIVE_39)
    say(LIVE_41)
    say()
    say("| D-9 의무 | 값 |")
    say("|---|---|")
    say(f"| ① 쿼리 실행 시각(KST) | **{stamp}** — 이 DB 지문을 «처음» 읽은 실행의 DB `now()`(Asia/Seoul) · "
        "`ladder_post10/read_stamp.json` 키 `first_read_kst`·`timezone`·`fingerprint`(같은 지문 재실행은 같은 값 · 파일을 다시 쓰지 않는다) · "
        "이번 실행 벽시계는 stdout `[run]` 줄 |")
    say(f"| ② 창 구간 `max(daily_prices.updated_at)` | 공통 창 `[{WIN_LO}, {END}]`(전 종목 {w_n:,}행): `max` **{w_umax}** · "
        f"`min` **{w_umin}** · 이 축이 읽은 봉(누적 {len(rows)}건 × `[σ₂₀ 창 시작, {END}]` = `[{ax_lo}, {END}]` · 건별 합 "
        f"{ax_n:,}행(같은 종목 두 건은 두 번 센다)): `max` **{ax_umax}** · `min` **{ax_umin}** |")
    say(f"| ③ 10-02 봉의 빈티지 | **「10-02 봉은 D+1(10-06 · 10-05 개천절 대체공휴일) sweep 이후 읽음」** — 10-02 행 "
        f"`min(updated_at)` = **{e_umin}** ≥ {SWEEP_D1}: **{'예' if str(e_umin) >= SWEEP_D1 else '🔴 아니오'}** · `max` {e_umax} |")
    say(f"| ④ 창 구간 `min(updated_at)` | **「창 구간 `min(updated_at)` = {w_umin} ≥ 10-06 15:35: "
        f"{'예' if str(w_umin) >= SWEEP_D1 else '아니오'}」**(기록 · 통과 조건 아님 · `updated_at` 은 sweep 일괄 갱신값이라 "
        "빈티지 «증거»가 아니라 «읽은 시각» 기록 · PD-27 (라)) |")
    say("| ⑤ 혼합 빈티지 | §0-2 — `LAD-` 창5 걸침 칸마다 한 줄 + 「전부 경계 후」 줄(PD-27 (바) 표 실측 재계수) |")
    say("| 「정규장만」 갈래 | **열지 않음**(`PREREG_POST8.md` §9 (나) 4) · `adj_factor` 산술 **0건** · 라이브 트리 import 0건 · "
        "DB 는 SELECT 만 |")
    say()
    say("**착수 조건 충족 증거(관리자 실측 · 인용 — 이 레인은 ②③④ 를 위 표에서 직접 다시 읽었다)**:")
    for ln in ADMIN_PROBE:
        say(f"- {ln}")
    cur.execute("SELECT count(DISTINCT date) FROM daily_prices WHERE date > %s AND date <= %s",
                (LAUNCH_CAP[:10], str(stamp)[:10]))
    over_days = cur.fetchone()[0]
    if str(stamp) > LAUNCH_CAP:
        say(f"- 🔴 `P10-착수상한`: 상한 {LAUNCH_CAP} · 착수 {stamp} · 초과 {over_days} 거래일(DB 달력 기준) — 신고뿐 · 판정·등급 0")
    else:
        say(f"- `P10-착수상한`: 착수(첫 레인 실행 `now()` = `first_read_kst`) **{stamp}** ≤ 상한 {LAUNCH_CAP} ⇒ 초과 아님(신고 줄 해당 없음)")
    say()
    say("### §0-1. `PREREG_POST8/9/10` 인쇄 의무 대조\n")
    say("| 조항 | 이 산출물 | 자리 |")
    say("|---|---|---|")
    say("| `P9-공통독법`(§1 · `D-3` (나)4) | **해당** — 신고 줄 1줄 | §7-3 |")
    say("| `P9-스탬프통일`(§6) | **해당**(post10 부터 구속) — `ladder_post10/read_stamp.json` + 위 표 | §0 |")
    say("| `P9-결측분리` · `P9-행단위`(`D-8`) | 해당 없음(`WRC-`·`RNK-`·`SEC-` 몫) — 이 산출물은 `prog_ver` 를 공변량으로 쓰지 않는다 | — |")
    say("| `D-1`(비교가능 쌍 세 수) | 해당 없음 — `ANC-P3` 게이트 분모용(ANC 레인 종결 · `F-5` (ㄱ)) | — |")
    say("| `D-7`(`P6-창5절단가드-A` 분모 두 산술) | **해당**(3회차) | §1-1 |")
    say("| `D-9`(혼합 빈티지) | **해당** — 창5 걸침 1(서산) + 「전부 경계 후」 8 | §0-2 |")
    say("| `D-5` · `D-3` | **해당** — 전 행 세 쪽 · 신고 줄 | §7-3 · §7-4 |")
    say("| `F-3` `P10-기업행위봉` | **해당**(창 = 창5 `[D, D+4]`) — 신고 줄 + 「기업행위 건 제외」 갈래(인쇄만) | §7-5 |")
    say("| `F-5` `P10-앵커종결` | **해당** — `LAD-T1`·`LAD-P2` 종결 · `LAD-T3`·`P6-창5절단가드-B` 「귀결 대상 종결」 · `LAD-T2` 계속 | §2 · §5 · §6 · §8 |")
    say("| `F-6` `P10-approx누적범위` | 🔴 **미발효**(신규 `approx` 0) — 범위 칸 한 줄 + 참고 인쇄만 | §7-1 |")
    say()
    say("🔵 라벨 접두: `T1`·`T2`·`T3`·`P1`~`P3` 은 전부 **`LAD-`** · 플래그·가드 **`P6-`** · 규약 **`P8-`**·**`P9-`**·**`P10-`**.")
    say("🔴 **새 예측을 만들지 않았다** — δ·창5·게이트 40·시드·순열 표본 수 전부 동결값 그대로다. "
        "🔴 **등급 이름을 적지 않는다**(`INTAKE_2026-10-04_post10.md` §6 단계).")

    # ── §0-2 혼합 빈티지 ────────────────────────────────────────────────
    say()
    say("### §0-2. `P8-혼합빈티지신고` — `LAD-` 창5 `[D, D+4]` (PD-27 (바) · `PREREG_POST8.md` §9 (나) 3)\n")
    say("의무 문형 *「창 `[<시작>, <끝>]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `<n_before>` 봉 / 후 `<n_after>` 봉 · "
        "혼합 빈티지」* — 누적 풀 전 행을 실측으로 다시 셌다(그 종목의 봉 · B-8). 🟡 경계 전 봉 0 인 창은 «걸침»이 아니라 "
        "**「전부 제도 경계 후」 줄을 추가 인쇄**한다(PD-27 (바) 재량 · 판정 효과 0).\n")
    got5, after5 = {}, {}
    for r in rows:
        hi, _nb = window_bounds(cur, r["code"], r["d0"], 5, END)
        b, a = cross_counts(cur, r["code"], r["d0"], hi)
        if b and a:
            got5[(r["nm"], r["post"])] = (b, a)
            say(f"- {r['nm']}({r['post']} · 등록 {r['d0']}): 창 `[{r['d0']}, {hi}]` 은 제도 경계 2026-09-14 를 걸친다 — "
                f"경계 전 {b} 봉 / 후 {a} 봉 · 혼합 빈티지")
        elif a and not b:
            after5[(r["nm"], r["post"])] = (b, a)
            say(f"- 🟡 {r['nm']}({r['post']} · 등록 {r['d0']}): 창 `[{r['d0']}, {hi}]` 은 전부 제도 경계 후(전 0 / 후 {a})")
    ok27 = (got5 == PD27_CROSS5) and (after5 == PD27_ALL_AFTER5)
    say()
    say(f"- 걸침 **{len(got5)}줄**(post10 신규 {sum(1 for k in got5 if k[1] == 'post10')} + 누적 풀 옛 창 "
        f"{sum(1 for k in got5 if k[1] != 'post10')} — 옛 산출물이 이미 인쇄한 줄의 재인쇄) · 「전부 경계 후」 "
        f"**{len(after5)}줄**(post10 신규 {sum(1 for k in after5 if k[1] == 'post10')} + 옛 {sum(1 for k in after5 if k[1] != 'post10')}) ⇒ "
        f"PD-27 (바) 표와 **{'일치 ✅' if ok27 else '🔴 불일치 — 실측을 그대로 적는다'}**")
    say(f"- ⇒ **post10 의무 줄**: 창5 걸침 **{sum(1 for k in got5 if k[1] == 'post10')}**(서산) + 「전부 경계 후」 "
        f"**{sum(1 for k in after5 if k[1] == 'post10')}**(PD-27 (바) 표 = 1 + 8)")
    say("- 🔴 post7 지투파워 `approx` 갈래 창은 이 회차에서 **다시 읽지 않는다**(누적 풀 밖 · post8 §1-1b 민감도였다 · 그 신고 줄은 "
        "post8 산출물 §0-2 에 있다).")
    say("- 🔴 **참고 병기(의무 목록 밖 · 판정 창 아님)** — post10 신규의 민감도 창(창3 `[D, D+2]` · 창A `[D, 발행일]`):")
    for r in rows:
        if r["post"] != "post10":
            continue
        hi3, _ = window_bounds(cur, r["code"], r["d0"], 3, END)
        b3, a3 = cross_counts(cur, r["code"], r["d0"], hi3)
        ba, aa_ = cross_counts(cur, r["code"], r["d0"], r["pub"])
        say(f"  - {r['nm']}: 창3 `[{r['d0']}, {hi3}]` 전 {b3} / 후 {a3}"
            f"{' · 걸침' if b3 and a3 else ' · 안 걸침'} · 창A `[{r['d0']}, {r['pub']}]` 전 {ba} / 후 {aa_}"
            f"{' · 걸침' if ba and aa_ else ' · 안 걸침'}")
    say("- 🔴 **방향 추론은 인용하지 않는다** — 「`H` 를 높이고 `L` 을 낮춘다」는 `PREREG_POST8.md` §9 (마)의 **추론**이다.")

    # ── §1-0 표본 구성 ──────────────────────────────────────────────────
    new10 = [r for r in rows if r["post"] == "post10"]
    old = [r for r in rows if r["post"] != "post10"]
    trunc = [r for r in new10 if r["trunc5"]]
    trunc_all = [r for r in rows if r["trunc5"]]
    say()
    say("## §1-0. 표본 구성 — 「이번 글 신규 9」 = 「주 표본 9」 (PD-3 · PD-12 · PD-21)\n")
    say("| 구분 | 건 | 이 축에서의 지위 |")
    say("|---|---|---|")
    say(f"| 신규 ∧ `exact` | **{N_EXACT_POST10}** | 🟢 **주 표본** — 차수 `N` = {sorted(r['N'] for r in new10)} |")
    say("| 신규 ∧ `approx` | **0** | 갈래 없음(PD-21) |")
    say("| 신규 ∧ `none` | **0** | — |")
    say("| 기존 건 후속 | **3** | 🔴 등록일 축 밖 — PD-2 이중계상 금지 |")
    say(f"| **이번 글 신규 계** | **{N_NEW_POST10}** | 🔴 **가드-A 의 «분모»**(`PREREG_POST8.md` §7 (나) 1 · D-7) |")
    say("| 항목 계 | 12 | `INTAKE` §1 |")
    say()
    say("| 종목 | 코드 | N(원장) | 라벨 | 등록일 축 «밖»인 사유 |")
    say("|---|---|---|---|---|")
    for nm, code, N, lbl, why in OUT_OF_REGDAY_AXIS:
        say(f"| {nm} | {code} | {N} | {lbl} | {why} |")
    say()
    say("- 🔴 **재진입 4**(범한·서산·한켐·우리로 · PD-3) ⇒ 주 표본 안 §1-5 재진입 **항등 아님**(9 ↔ 5). `P6-PRIOR_CYCLE_IN_WINDOW` = **4/9** "
        "(§7).")
    say("- 🔴 **🔒 #1 ⓐ**: 샌즈랩 항목 내 재등록(09-29)은 등록 사건이 아니다(분모 9 · 날짜 기록 · 「샌즈 제외」 = 인쇄만 · §7-2) · "
        "한컴위드 재등록(09-23)은 후속이라 어느 행에도 들어가지 않는다.")
    say("- 🔴 **「post8 우리로 제외」 = 인쇄만**(확인 7 · post8 🔒 #1-(ii) 승계) — 누적 풀에 post8 행으로 있다.")
    say("- 🔴 **B-2 carve-out**: 이번 글 `MANUAL` **0** ⇒ 해당 0(`LABELS_2026-10-04_post10.md` · `TP` 10 · `MIX` 2) · `MIX` 2건(라온·샌즈)은 "
        "이 축에서 라벨로 빼지 않는다(등록일 축 · 라벨 무관).")

    # ── §1 건별 원표 ────────────────────────────────────────────────────
    say()
    say("## §1. 건별 원표 — `(종목, 글, N, H, min_low, DD)` (§4-5 의무 인쇄 4)\n")
    say(f"`H` = 등록일 고가 · `DD` = 1 - min(low over 창) / H · 창5 = `[D, D+4거래일]`(그 종목의 봉 · B-8) · "
        f"창A = `[D, 그 글의 발행일]`(post10 = **{PUB10}** 발행 당일 포함 · 옛 글은 그 글의 발행일 · B-1) · "
        "🔴 **post4~9 행도 이 실행(같은 스냅샷)에서 다시 읽은 값이다**.\n")
    say("| # | 종목 | 글 | N | 등록일 | H | 창3 봉수 / min_low / **DD3** | 창5 봉수 / min_low / **DD5** | "
        "창A 끝 / min_low / **DD_A** | 경과거래일 E | sigma20 | `P6-WIN5_TRUNC` | 비고 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        memo = r["memo"]
        if r["post"] == "post7" and r["nm"] in POST7_TRUNC_ASOF:
            memo += " → post8 회차에 값 대체 완료(`RESULTS_LADDER_TRANCHE_POST8_NUMBERS.md` §1-1b)"
        if r["post"] == "post6" and r["nm"] in P7.POST6_TRUNC_ASOF:
            memo += " → post7 회차에 값 대체 완료"
        sig_s = "—" if r["sig"] is None else f"{r['sig']:.4f}"
        say(f"| {r['i']} | {r['nm']} | {r['post']} | **{r['N']}** | {r['d0']} | {r['H']:,.0f} | "
            f"{r['n3']} / {r['l3']:,.0f} / **{r['dd3']:.2f}%** | {r['n5']} / {r['l5']:,.0f} / **{r['dd5']:.2f}%** | "
            f"{r['pub']} / {r['la']:,.0f} / **{r['dda']:.2f}%** | {r['E']} | {sig_s} | "
            f"{'**1**' if r['trunc5'] else '0'} | {memo} |")
    say()
    say(f"- 표본 **{len(rows)}건** = 기존 누적 {len(old)}(post4 6 + post5 6 + post6 10 + post7 6 + post8 4 + post9 5) + "
        f"**10번째 글 주 표본 {len(new10)}건**(신규 ∧ `exact`). 후속 3건은 **등록일 축 밖**(§1-0).")
    say(f"- 10번째 글 주 표본의 차수 다중집합 = {sorted(r['N'] for r in new10)} — N 이 서로 다른 건이 많아 그 글 «단독» 쌍이 **구성상 0 이 아니다**.")

    # ── §1-1 D-7 ────────────────────────────────────────────────────────
    say()
    say("### §1-1. 창5 절단 · `P6-창5절단가드-A` 분모 두 산술 (`PREREG_POST8.md` §7 D-7 · PD-25)\n")
    say(f"- **이번 글 신규 건 중 절단 = {len(trunc)}건**"
        + (": " + " · ".join(f"{r['nm']}(창5 {r['n5']}봉)" for r in trunc) if trunc else " — 주 표본 9건 전부 창5 **5봉 완전**")
        + f" · 누적 풀 전체 절단 = **{len(trunc_all)}건**")
    fire_main = guard_a_fires(len(trunc), N_NEW_POST10)
    fire_ex = guard_a_fires(len(trunc), N_EXACT_POST10)
    say()
    say("| 분모 갈래 | 산술 | 문턱 1/3 | 판정 |")
    say("|---|---|---|---|")
    say(f"| **주 — 이번 글 신규 건**(`PREREG_POST8.md` §7 (나) 1) | **{len(trunc)}/{N_NEW_POST10} = "
        f"{100*len(trunc)/N_NEW_POST10:.1f}%** | {100*GUARD_A_NUM/GUARD_A_DEN:.1f}% | **{'⛔ 발동' if fire_main else '미발동'}** |")
    say(f"| `exact` 분모 갈래(의무 민감도 · (나) 2) | **{len(trunc)}/{N_EXACT_POST10} = {100*len(trunc)/N_EXACT_POST10:.1f}%** | "
        f"{100*GUARD_A_NUM/GUARD_A_DEN:.1f}% | **{'⛔ 문턱 도달' if fire_ex else '미도달'}** |")
    say("| `approx` 갈래 포함(참고) | 이번 글 `approx` 0 ⇒ 분자 +0 · 분모 +0 | — | 주와 같다 |")
    say()
    say(f"- **분모 갈래 신고**((나) 3): *「주 분모 {len(trunc)}/{N_NEW_POST10} · `exact` 분모 {len(trunc)}/{N_EXACT_POST10} · "
        f"문턱 1/3」* — **분모 갈래: {'🔴 갈린다' if fire_main != fire_ex else '갈리지 않음'}**")
    reached2 = POST9_GA_EXACT_REACHED and fire_ex
    say(f"- **2회 연속 계수**((나) 4): post8 = 1회차 · post9 = 2회차(`exact` 갈래 «미도달») → **post10 = 3회차 · `exact` 갈래 "
        f"{'«도달»' if fire_ex else '«미도달»'}** ⇒ 「2회 연속 도달」 "
        f"**{'성립 — 재료로 올린다(자동 전환 아님)' if reached2 else '불성립 · 재료 올림 없음'}**(3회 연속 전부 미도달이면 재료 올림 없음).")
    say("- 문턱 1/3 은 `REC-Y3` 에서 **차용**한 값이다(`PREREG_POST6.md` §1-6 6번 고지 승계).")
    say(f"- **`P6-창5절단가드-B`**: 누적 풀 절단 건 = **{len(trunc_all)}** ⇒ 제외 표본 = "
        f"{'주 표본 **항등**' if not trunc_all else '절단 건(' + ' · '.join(r['nm'] for r in trunc_all) + ') 뺀 표본 — §6'}. "
        "🔴 귀결 문장 중 종결 항목을 가리키는 부분 = **「귀결 대상 종결(`F-5`)」**(제외 표본 `LAD-T1`·`LAD-P2` 재계산 대상이 종결 · "
        "`LAD-T2`·`T3` 는 §6 에서 재계산).")
    say("- 🔴 **방향 기록(선택 아님)**: 신규 절단 1(뷰노)은 등록일(09-29)이 발행일(10-02)보다 3거래일 앞선 구성이 만든다(PD-12 · PD-1 문언의 귀결). "
        "post7 이후 처음의 «신규» 절단이다(post8·post9 0) — 뷰노 창5 의 대체 여부는 **다음 회차 레인 몫**이다(이 문서는 정하지 않는다).")

    # ── §1-1b post7 대체 «전» 값 재현 (PD-23 LAD 행) ─────────────────────
    rows7_asof = build_rows(cur, ITEMS_CUM28, cal, END7)
    asof_by = {(r["nm"], r["post"]): r for r in rows7_asof}
    ns_all = [r["N"] for r in rows]
    dd5_after = [r["dd5"] for r in rows]
    dd5_before = [(asof_by[(r["nm"], r["post"])]["dd5"]
                   if (r["post"] == "post7" and r["nm"] in POST7_TRUNC_ASOF) else r["dd5"]) for r in rows]
    say()
    say("### §1-1b. post7 절단 건의 «대체 전» 갈래 — PD-23 `LAD-` 행 의무(갈래 · 이번 회차 새 대체 0)\n")
    say("post7 절단 2건(빛과전자·범한퓨얼셀)은 post8 회차에 값이 대체됐다(`RESULTS_LADDER_TRANCHE_POST8_NUMBERS.md` §1-1b). "
        "이번 회차의 새 대체는 **0**(뷰노 대체 여부는 다음 회차 레인 몫). PD-23 이 「post7 절단 대체 «전» 값」을 갈래로 적었으므로 "
        "같은 식(END 2026-09-11 로 다시 읽은 절단 시점 값)을 누적 풀에 넣은 표본의 «구성»(건 · 비교가능 쌍)만 센다 — "
        "🔴 `LAD-T1` 종결로 `V`·`p` 계산 0.\n")
    say("| 종목 | 등록일 | post7 「절단 시점 값」(인용) | END 2026-09-11 로 다시 읽음 | 이번 창5 봉수 / **DD5** |")
    say("|---|---|---|---|---|")
    for nm, ref in POST7_TRUNC_ASOF.items():
        cr = next((r for r in rows if r["nm"] == nm and r["post"] == "post7"), None)
        ar = asof_by.get((nm, "post7"))
        rep_ok = ar is not None and ar["n5"] == ref["n5_asof"] and f"{ar['dd5']:.2f}" == f"{ref['dd5_asof']:.2f}"
        say(f"| {nm} | {ref['d0']} | {ref['n5_asof']}봉 / **{ref['dd5_asof']:.2f}%** | "
            f"{ar['n5']}봉 / {ar['dd5']:.2f}% {'✅ 재현' if rep_ok else '🔴 불일치'} | {cr['n5']}봉 / **{cr['dd5']:.2f}%** |")

    # ── §1-2 [D-19, D] ──────────────────────────────────────────────────
    say()
    say("### §1-2. PD-12 재확인(참고) — 주 표본 9건의 `[D-19, D]` 창 봉수 (등록일 포함)\n")
    say("| 종목 | 등록일 | 창 시작(달력 D-19) | 그 종목 봉수 / 20 |")
    say("|---|---|---|---|")
    short20 = []
    for r in new10:
        cur.execute("SELECT min(date) FROM (SELECT DISTINCT date FROM daily_prices "
                    "WHERE date <= %s ORDER BY date DESC LIMIT 20) t", (r["d0"],))
        w_start = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s",
                    (r["code"], w_start, r["d0"]))
        nb = cur.fetchone()[0]
        if nb < 20:
            short20.append(r["nm"])
        say(f"| {r['nm']} | {r['d0']} | {w_start} | {'🔴 **' + str(nb) + '**' if nb < 20 else nb} / 20 |")
    say()
    say(f"- 20봉 미만 = **{len(short20)}건** ⇒ PD-12(9건 전부 20/20)와 "
        f"**{'일치 ✅' if not short20 else '🔴 불일치 — 그대로 적는다'}** · `P6-절단가드-A`(등록일 축) 산술 = "
        f"{len(short20)}/{N_EXACT_POST10} ⇒ **{'⛔ 발동' if guard_a_fires(len(short20), N_EXACT_POST10) else '미발동'}** "
        "(이 축의 판정에는 쓰지 않는다 — 이름만 같고 대상이 다르다)")

    # ── §1-3 / §1-4 ─────────────────────────────────────────────────────
    cnt = Counter(ns_all)
    distinct = factorial(len(ns_all))
    for m in cnt.values():
        distinct //= factorial(m)
    say()
    say("### §1-3. 귀무 배정 수 · 원리적 비교 불가 쌍\n")
    say(f"- 차수 다중집합 = {sorted(ns_all)} · 건수 **{len(ns_all)}**")
    say(f"- 서로 다른 배정 수 = **{distinct:,}** ⇒ {'200,000 초과 ⇒ **시드 고정 표본**' if distinct > NPERM else '전수 가능'} (B-5)")
    say(f"- N 동률로 «원리적으로» 비교 불가한 쌍 = **{sum(m*(m-1)//2 for m in cnt.values())}** / 전체 "
        f"{len(ns_all)*(len(ns_all)-1)//2}")
    v5 = sorted(r["dd5"] for r in rows)
    q5 = statistics.quantiles(v5, n=4, method="inclusive")
    say()
    say("### §1-4. 창5 `DD` 퍼짐 (계열 승계 · 「잡음 띠」 점검)\n")
    say("- 정렬: " + " · ".join(f"{x:.2f}" for x in v5))
    say(f"- 범위 **{v5[0]:.2f}~{v5[-1]:.2f}** · 폭 **{v5[-1] - v5[0]:.2f}%p** · 사분위 `Q1`={q5[0]:.2f} · `Q2`={q5[1]:.2f} · "
        f"`Q3`={q5[2]:.2f} ⇒ **IQR {q5[2]-q5[0]:.2f}%p** (post9 누적 37건: 범위 23.18%p · IQR 6.49%p — 출처 "
        "`RESULTS_LADDER_TRANCHE_POST9_NUMBERS.md` §1-4)")

    # ── §2 LAD-T1 종결 ──────────────────────────────────────────────────
    say()
    say("## §2. `LAD-T1` — 🔒 종결 (`F-5` · `P10-앵커종결` (가) · 2-a (ㄴ) 중단)\n")
    say(f"- **`LAD-T1`**: {T1_CLOSED}")
    say("- `V`·`p`·`P(V=0)` 는 **창3·창5·창A 세 창 모두 계산 0회**(`PREREG_LADDER_TRANCHE.md:104-105` §4-5 의무 인쇄는 종결(결정 ①)이 대체한다고 "
        "읽는다 · 🔒 사장님 2026-10-04 (ㄴ) 중단 · PD-37). 이 산출물에 `LAD-T1` 의 `V`·`p`·판정 낱말은 없다.")
    say("- §2-1 계열 재계산(post4~post9 풀을 이 스냅샷에서 다시 읽어 `V`·`p` 재현 확인) — **해당 없음**(`LAD-T1` 계산 0회의 귀결 · 소급 탐색도 하지 않는다).")
    say("- §3 게이트(누적 비교가능 쌍 ≥ 40) — **해당 없음**: 게이트는 `LAD-T1` 판정 문턱이다. 비교가능 쌍 수는 «구성»으로만 §7-3 `D-5` 의 `n` 칸에 센다(`V` 없음).")

    # ── §4 T2 ───────────────────────────────────────────────────────────
    say()
    say("## §4. `LAD-T2` (반증축 · 필수 · **계속**) — `DD/sigma20` 정규화\n")
    sub = [r for r in rows if r["sig"] is not None]
    drop = [r["nm"] for r in rows if r["sig"] is None]
    say(f"B-4: sigma20 없는 건은 T2 표본에서 통째로 제외. **표본 {len(sub)}건** "
        f"(제외 {len(drop)}건: {', '.join(drop) if drop else '없음'} — «구성»이다).\n")
    t2 = t2_stats(sub)
    say(f"- median(sigma20) = **{t2['med_sig']:.4f}** ⇒ 부수 민감도용 `delta_norm` = {DELTA}%p / (100*sigma) = "
        f"**{t2['dn']:.4f}**\n")
    say(HDR)
    say(SEP)
    vo, co, mo, po, zo, mc = t2["o"]
    say(f"| 원축 `DD`(같은 표본 · T2 대조행) | {vo} | {co} | {t2['drop_dd']} | {mo:.2f} | **{po:.4f}** | {zo:.5f} | {mc:.2f} |")
    vs_, cs_, ms_, ps_, zs_, mcs_ = t2["s"][0], t2["s"][1], t2["s"][2], t2["s"][3], t2["s"][4], t2["s"][5]
    say(f"| **정규화축 `DD/sigma20`(같은 쌍 집합)** | {vs_} | {cs_} | {t2['drop_dd']} | {ms_:.2f} | **{ps_:.4f}** | {zs_:.5f} | {mcs_:.2f} |")
    vd, cd, md, pd_, zd, mcd = t2["d"]
    say(f"| 정규화축 (부수: `delta_norm` 직접 적용) | {vd} | {cd} | {t2['drop_n2']} | {md:.2f} | **{pd_:.4f}** | {zd:.5f} | {mcd:.2f} |")
    say()
    say("- 🔴 위 「원축 `DD`」 행은 **`LAD-T2` 가 `p_n < p_o` 를 비교하기 위한 대조행**이다(T2 의 입력) — `LAD-T1` 의 판정 행이 아니다(종결 · "
        "판정 낱말 없음 · `확인 필요` 1).")
    if ps_ < po:
        say(f"- ⇒ 정규화축 `p`({ps_:.4f}) **<** 원축 `p`({po:.4f}) ⇒ 문언상 `PREREG_BUYLADDER.md` §3 **가설 B** 쪽. "
            "🔴 **부호뿐이다** · `PREREG_BUYLADDER` 계열은 🔒 결정 ④로 **종결** ⇒ **기록만**.")
    else:
        say(f"- ⇒ 정규화축 `p`({ps_:.4f}) **>=** 원축 `p`({po:.4f}) ⇒ **가설 B 는 지지 없음.**")
    say(f"- 계열 값 나란히(인쇄값): post5 원축 0.6767 · 정규화축 0.5562 → post6 0.5185 · 0.7626 → post7 0.3947 · 0.6361 → "
        f"post8 0.4338 · 0.7689 → post9 {POST9_T2_P[0]:.4f} · {POST9_T2_P[1]:.4f}")

    # ── §5 T3 ───────────────────────────────────────────────────────────
    say()
    say("## §5. `LAD-T3` (반증축 · 필수 · **계속**) — 축을 「등록일 → 발행일 경과 거래일」로\n")
    say("B-3: 경과일은 %p 가 아니므로 동률 대역 = **정확히 같은 값만 제외**(delta_E = 0).\n")
    say(HDR)
    say(SEP)
    a_t3 = run_axis("T3 `경과 거래일 E`", ns_all, [float(r["E"]) for r in rows], 0.0)
    say()
    say("- 경과일 분포(post10 주 표본): " + " · ".join(f"{r['nm']} {r['E']}" for r in new10))
    t3_cancel = a_t3["p"] < 0.05
    say(f"- 🔴 **감시 줄**(`LAD-T3` 0.05 밑이면 「`LAD-T1` 영구 취소」 — `PREREG_POST6.md:540` · 보고서 `docs/report_2026-09-24_tasso_post8_verdicts.md:350`): "
        f"이번 T3 `p` = **{a_t3['p']:.4f}** ⇒ 0.05 밑: **{'예' if t3_cancel else '아니오'}** "
        f"(post8 {POST8_T3_P:.4f} → post9 {POST9_T3_P:.4f} → 이번 {a_t3['p']:.4f} · 0.05 까지 **{a_t3['p'] - 0.05:+.4f}**)")
    say("- 🔴 **귀결 대상 종결(`F-5`)**: 위 「`LAD-T1` 영구 취소」 귀결은 `LAD-T1` 이 종결돼 **대상이 소멸**했다 — `T3` 의 `p` 는 계산·인쇄하되 "
        "취소 조항을 «발동/미발동»으로 선언하지 않는다(대상 종결). 이전 회차의 「부호 감시」(T3 `p` ↔ 창5 원축 `p`)는 창5 원축 `p` 가 없어 "
        "**비교 대상 종결**이다. `T3` `p` 계열만 기록: post5 0.2008 · post6 0.1909 · post7 0.1182 · "
        f"post8 {POST8_T3_P:.4f} · post9 {POST9_T3_P:.4f} · **post10 {a_t3['p']:.4f}**.")

    # ── §6 절단 제외 ────────────────────────────────────────────────────
    say()
    say("## §6. 민감도 — **창5 절단 제외** (`P6-창5절단가드-B` · 🆕 뷰노)\n")
    sub_c = [r for r in rows if not r["trunc5"]]
    if trunc_all:
        say(f"- 🔴 절단 건 {len(trunc_all)}건이 있다 — " + ", ".join(f"{r['nm']}({r['post']} · 창5 {r['n5']}봉)" for r in trunc_all)
            + f" ⇒ 제외 표본 **{len(sub_c)}건**")
    else:
        say(f"- 🟢 **누적 풀 {len(rows)}건 중 창5 절단 = 0** ⇒ 제외 표본 = 주 표본 **항등**.")
    say("- 🔴 **귀결 대상 종결(`F-5`)**: `P6-창5절단가드-B` 의 «재계산 대상» 중 `LAD-T1`·`LAD-P2` 는 종결(계산 0회) — 제외 표본에서 다시 계산하는 것은 "
        "`LAD-T2`·`LAD-T3` 뿐이다.\n")
    say(HDR)
    say(SEP)
    ns_c = [r["N"] for r in sub_c]
    c_t3 = run_axis(f"T3 `경과 거래일 E`(delta_E = 0 · 창5 절단 제외 {len(sub_c)}건)", ns_c, [float(r["E"]) for r in sub_c], 0.0)
    say()
    sub_c2 = [r for r in sub_c if r["sig"] is not None]
    t2c = t2_stats(sub_c2)
    say(f"- `LAD-T2`(창5 절단 제외 · 표본 {len(sub_c2)}건): 원축 `p` {t2c['o'][3]:.4f} · 정규화축(같은 쌍 집합) `p` {t2c['s'][3]:.4f} · "
        f"부수 `p` {t2c['d'][3]:.4f} (주 표본 {po:.4f} · {ps_:.4f} · {pd_:.4f})")
    say(f"- `LAD-T3`(창5 절단 제외) `p` = {c_t3['p']:.4f} (주 {a_t3['p']:.4f}) — 0.05 밑 여부: "
        f"**{'예' if c_t3['p'] < 0.05 else '아니오'}** · 취소 조항은 대상 종결(`F-5`) · 판정 낱말 없음")

    # ── §7 재진입 제외 ──────────────────────────────────────────────────
    say()
    say("## §7. 민감도 (B-7 + `PREREG_POST6.md` §1-5) — **같은 종목 2번째 사이클 제외** (🔴 누적 풀 기준 · **항등 아님**)\n")
    sub2 = [r for r in rows if not r["second"]]
    excl2 = [r for r in rows if r["second"]]
    say("- 제외 대상: " + " · ".join(f"{r['nm']}({r['post']} · {r['d0']})" for r in excl2) + f" ⇒ 표본 **{len(sub2)}건**")
    say("- **`P6-PRIOR_CYCLE_IN_WINDOW`** — 이번 글: " + " · ".join(f"{k} = **{v}**" for k, v in PRIOR_CYCLE_FLAG_POST10.items())
        + f" ⇒ **{sum(1 for v in PRIOR_CYCLE_FLAG_POST10.values() if v != '0')}/{len(PRIOR_CYCLE_FLAG_POST10)}**(INTAKE §5 · PD-3 = 4/9)")
    say("- 🔴 **주 표본(`exact` 9) 안의 §1-5 재진입 = 4** ⇒ 이번 글 몫 4건이 제외 대상에 더해진다 — 이 갈래는 **주와 항등이 아니다**"
        "(9 ↔ 5 · 누적 풀 옛 재진입 건도 있다 · PD-23 `LAD-` 행). `LAD-T1` 종결로 «답»은 `T3` 만 쓴다.\n")
    say(HDR)
    say(SEP)
    ns2 = [r["N"] for r in sub2]
    s_t3 = run_axis(f"T3 `경과 거래일 E`(delta_E = 0 · 재진입 제외 {len(sub2)}건)", ns2, [float(r["E"]) for r in sub2], 0.0)
    say()
    say(f"- T3 제외본 `p` = {s_t3['p']:.4f} (주 판정 {a_t3['p']:.4f}) · 🔴 `LAD-T1` 창3·창5·창A 제외본은 **계산 0회**(종결) ⇒ "
        "주 ↔ 재진입 제외의 `LAD-T1` «판정 비교» 줄은 없다(귀결 대상 종결 · `F-5`).")

    # ── §7-1 approx ─────────────────────────────────────────────────────
    say()
    say("## §7-1. 민감도 — `approx` 갈래 (PD-21) · 🆕 `P10-approx누적범위`(`F-6`)\n")
    say("- 🟢 **post10 신규 `approx` = 0** ⇒ 이번 글이 만드는 `approx` 갈래 **없음**(PD-21 · PD-23 `LAD-` 행).")
    say("- 🆕 *「`P10-approx누적범위`: 범위 = 🔒 (가) 누적 `approx` 전건(`PREREG_POST10.md` §6 (나)2) · 미발효라 이번엔 적용 안 함 · 신규 `approx` 0」* "
        "(발효 조건 = 신규 `approx` 건수 ≥ 1 · 이번 0 ⇒ 미발효 · 참고 인쇄만 · 현행).")
    say("- 🔴 **누적 풀의 옛 `approx` 갈래(참고)** — post8 §7-3 이 쓴 헥토·코데즈 「8월말」 7갈래의 **비교가능 쌍 수만** 센다(`LAD-T1` 종결 · "
        "`V`·`p` 계산 0 · 판정 언어 금지). post7 `approx`(지투파워·한국화장품제조)는 post8 도 넣지 않았다 — 같은 구성을 잇는다(§9 한계 7).\n")
    say("| 종목 | N | 갈래 `D` → **DD5** (창5 봉수) |")
    say("|---|---|---|")
    apx_dd5 = {}
    for nm, code, N, _label, lo, hi, _n_expect, _prev in APPROX_BRANCHES_POST8:
        cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s ORDER BY date", (lo, hi))
        days = [str(r_[0]) for r_ in cur.fetchall()]
        apx_dd5[nm] = []
        cells = []
        for d0 in days:
            cur.execute("SELECT date, high, low FROM daily_prices WHERE stock_code=%s AND date >= %s AND date <= %s "
                        "ORDER BY date", (code, d0, END))
            bars = cur.fetchall()
            w5 = bars[:5]
            dd5 = 100 * (1 - min(b[2] for b in w5) / bars[0][1])
            apx_dd5[nm].append((d0, dd5))
            cells.append(f"{d0[5:]} → **{dd5:.2f}**({len(w5)})")
        say(f"| {nm} | {N} | {' · '.join(cells)} |")
    apx_nm = [b[0] for b in APPROX_BRANCHES_POST8]
    apx_N = [b[2] for b in APPROX_BRANCHES_POST8]
    apx_comps = []
    for _dh, xh in apx_dd5[apx_nm[0]]:
        for _dk, xk in apx_dd5[apx_nm[1]]:
            ns_ = ns_all + apx_N
            ps_x, _drop = pairset(dd5_after + [xh, xk], DELTA)
            apx_comps.append(comp_of(ns_, ps_x))
    say()
    say(f"- 옛 `approx` 참고 조합 {len(apx_comps)}개: 비교가능 쌍 **{min(apx_comps)}~{max(apx_comps)}**(주 표본 {len(rows)}건 + 갈래 1개씩) — "
        "인쇄만(판정 언어 없음 · `V`·`p` 없음).")

    # ── §7-2 갈래 표본 (인쇄만) ─────────────────────────────────────────
    sub_w = [r for r in rows if not (r["post"] == "post8" and r["nm"] == "우리로")]
    sub_s = [r for r in rows if not (r["post"] == "post10" and r["nm"] == "샌즈랩")]
    say()
    say("## §7-2. 「post8 우리로 제외」 · 「샌즈 제외」 — **인쇄만 · 판정 효과 없음** (확인 7 · 🔒 #1 ⓐ)\n")
    say(f"- 「post8 우리로 제외」 표본 **{len(sub_w)}건**(post8 🔒 #1-(ii) 승계 · 누적 풀에 post8 행으로 있다) — 인쇄만.")
    say(f"- 「샌즈 제외」 표본 **{len(sub_s)}건**(🔒 #1 ⓐ · 항목 내 날짜 있는 재등록 · 샌즈랩 post10 행 한 건을 뺀다) — 인쇄만 · 갈래 계수 아님.")
    say("- 두 갈래 모두 `LAD-T1` 종결로 «답» 없음 — `n`(건 · 비교가능 쌍)만 §7-3 에 센다.")

    # ── §7-3 D-5 ────────────────────────────────────────────────────────
    def pairs_n(rs, vals):
        ps_, _d = pairset(vals, DELTA)
        return comp_of([r["N"] for r in rs], ps_)

    comp_main = pairs_n(rows, dd5_after)
    comp_sub2 = pairs_n(sub2, [r["dd5"] for r in sub2])
    comp_before = pairs_n(rows, dd5_before)
    comp_cut = pairs_n(sub_c, [r["dd5"] for r in sub_c])
    comp_w = pairs_n(sub_w, [r["dd5"] for r in sub_w])
    comp_s = pairs_n(sub_s, [r["dd5"] for r in sub_s])
    comp3 = pairs_n(rows, [r["dd3"] for r in rows])
    compA = pairs_n(rows, [r["dda"] for r in rows])

    # ── §7-5 F-3 (기업행위봉) — 판정 창 = 창5 `[D, D+4]` ─────────────────
    f3 = []
    f3_rec = []
    for r in new10:
        hi, _nb = window_bounds(cur, r["code"], r["d0"], 5, END)
        cur.execute("SELECT event_type, event_date FROM corp_events WHERE stock_code=%s AND event_date BETWEEN %s AND %s "
                    "ORDER BY event_date, event_type", (r["code"], r["d0"], hi))
        evs = cur.fetchall()
        cur.execute("SELECT date FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s AND volume = 0 "
                    "ORDER BY date", (r["code"], r["d0"], hi))
        v0 = [str(x[0]) for x in cur.fetchall()]
        a_hit = [str(d) for t_, d in evs if t_ == "split"]
        f3_rec.append((r["nm"], r["d0"], str(hi), [(t_, str(d)) for t_, d in evs], v0))
        if a_hit or v0:
            f3.append((r["nm"], a_hit, v0))
    k3 = len(f3)
    f3_names = {x[0] for x in f3}
    sub_f = [r for r in rows if not (r["post"] == "post10" and r["nm"] in f3_names)]
    comp_f = pairs_n(sub_f, [r["dd5"] for r in sub_f])

    say()
    say("## §7-3. `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나) 2 · PD-23 `LAD-` 행)\n")
    say(f"최소 n = **누적 비교가능 쌍 {PAIR_THRESHOLD}**(`PREREG_LADDER_TRANCHE.md` §5-1 동결값 · `LAD-T1` 문턱). 🔴 **`LAD-T1` 종결(`F-5`)로 이 축에는 "
        "«답»을 내는 판정 갈래가 없다** — 모든 행의 답 칸 = 「해당 없음(`LAD-T1` 종결 · 계산 0회)」, `n` 은 구성(건 · 비교가능 쌍)이다. "
        "🔴 **모든 행에 세 쪽을 인쇄한다**(`PREREG_POST8.md:342` · post8 A-B2 교훈). 「기업행위 건 제외」 답 칸 낱말 = 「답(참고) · 세지 않는다」(`F-3` (나)).\n")
    say("| 갈래 | n(건 · 비교가능 쌍) | 답(`LAD-T1` · 창5) | 계수 |")
    say("|---|---|---|---|")
    closed = "해당 없음(`LAD-T1` 종결 · 계산 0회)"
    say(f"| **주**(누적 · 창5) | {len(rows)}건 · **{comp_main}쌍** | {closed} | 계수 대상 없음(종결) |")
    say(f"| 창5 절단 제외(🆕 뷰노 · 누적 풀 절단 {len(trunc_all)}건 뺀 표본) | {len(sub_c)}건 · **{comp_cut}쌍** | {closed} | "
        f"{'🔴 **항등 아님** — 절단 ' + str(len(trunc_all)) + '건 제외(`T2`·`T3` 만 재계산 · §6)' if trunc_all else '🟢 **항등**(절단 0)'} |")
    say(f"| 재진입 제외(B-7 · 누적 풀 · 이번 글 몫 4) | {len(sub2)}건 · **{comp_sub2}쌍** | {closed} | 🔴 **항등 아님**(9 ↔ 5) · 계수 대상 없음(종결) |")
    say(f"| post7 대체 «전»(빛과전자·범한퓨얼셀 = 절단 시점 값) | {len(rows)}건 · **{comp_before}쌍** | {closed} | 계수 대상 없음(종결) |")
    say(f"| 「post8 우리로 제외」 | {len(sub_w)}건 · **{comp_w}쌍** | {closed} | 🔴 **인쇄만 — 계수하지 않는다**(확인 7) |")
    say(f"| 「샌즈 제외」(🔒 #1 ⓐ) | {len(sub_s)}건 · **{comp_s}쌍** | {closed} | 🔴 **인쇄만 — 계수하지 않는다**(🔒 #1 ⓐ) |")
    say(f"| 「기업행위 건 제외」(`F-3` · 이번 글 기업행위 건 {k3}/{N_NEW_POST10}) | {len(sub_f)}건 · **{comp_f}쌍** | "
        f"답(참고) · 세지 않는다 | 🔴 **인쇄만 — 계수하지 않는다**(`F-3` (나)){' · 🟢 항등(k = 0)' if k3 == 0 else ''} |")
    say(f"| `approx` 포함 — 이번 글 신규(`approx` 0) | {len(rows)}건 · **{comp_main}쌍**(주와 같은 표본) | {closed} · 주와 **항등** | "
        "🟢 **항등 — 갈래 없음**(PD-21 · PD-23) |")
    say(f"| `approx` 누적범위(`F-6` · 🔴 미발효 · 참고) | {len(rows) + len(apx_N)}건 · **{min(apx_comps)}~{max(apx_comps)}쌍**(옛 7×7 {len(apx_comps)}조합) | "
        f"{closed} | 🔴 인쇄만 — 미발효 · 범위 = 🔒 (가) 누적 전건(미적용) |")
    say(f"| (창 민감도) 창3 · 창A | {len(rows)}건 · {comp3}쌍 · {compA}쌍 | {closed} | 창 민감도(§4-5 1 의무 → 종결이 대체) |")
    say()
    say("- 최소 n 을 채운 계수 갈래 = **0개**(`LAD-T1` 판정 종결 — 답 낱말이 없다) ⇒ 갈래 간 «갈림»을 셀 대상이 없다(`P8-갈래계수` 3번째 줄 · 종결 경로).")
    say(f"- 🔴 **`D-3` (나)4 검사**: 이번 글 `approx` 0 ⇒ `approx` 포함 갈래 = `exact` 갈래 **항등** ⇒ **대상 없음**.")
    say("- 🆕 *「`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(이번 글 `approx` 0 · `LAD-T1` 종결 ⇒ 판정 갈래 없음)」* "
        "(`PREREG_POST9.md` §1 (나)3)")

    # ── §7-4 D-3 ────────────────────────────────────────────────────────
    say()
    say("### §7-4. `D-3` · `P8-approx의존신고` (`PREREG_POST8.md` §3 (나) 3 · PD-21)\n")
    say(f"「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 {N_EXACT_POST10} / `approx` 포함 분모 {N_EXACT_POST10}」 — "
        f"`LAD-` 의 최소 n(누적 쌍 40)은 `exact` 만으로 이미 {comp_main} {'≥' if comp_main >= PAIR_THRESHOLD else '<'} 40 이다(구성 · `LAD-T1` 종결).")

    # ── §7-5 F-3 출력 ───────────────────────────────────────────────────
    say()
    say("### §7-5. `F-3` · `P10-기업행위봉` (`PREREG_POST10.md` §3 (나) · 정의 A · 창 = 창5 `[D, D+4]`)\n")
    if f3:
        why = " · ".join("%s(%s)" % (nm, " · ".join(
            (["ⓐ " + " ".join(a_) ] if a_ else []) + (["ⓑ `volume = 0` " + " ".join(v_)] if v_ else []))) for nm, a_, v_ in f3)
    else:
        why = "없음(ⓐ `corp_events` `split` 행 0 · ⓑ `volume = 0` 봉 0)"
    say(f"*「`P10-기업행위봉`: 기업행위 건 {k3}/{N_NEW_POST10} — {why} · `adj_factor` 산술 0 · 처리 = (나)」*")
    say()
    say("| 종목 | 창5 `[D, D+4]` | ⓐ 창 안 `corp_events` 전 행(기록 줄 · 분류 효과 0) | ⓑ `volume = 0` 봉 |")
    say("|---|---|---|---|")
    for nm, d0, hi, evs, v0 in f3_rec:
        say(f"| {nm} | `[{d0}, {hi}]` | {' · '.join('%s %s' % (t_, d_) for t_, d_ in evs) or '없음'} | {' · '.join(v0) or '없음'} |")
    say()
    say("- ⓒ(기록 줄 · 정의 아님) 거래정지 공시 제목 = 이 레인은 `news` 를 읽지 않는다 — PD-36 인쇄(12종목 2026-05-01~10-04 제목 grep 거래정지 **0**) 인용.")
    say(f"- 「기업행위 건 제외」 갈래 = §7-3 행(`n` {len(sub_f)}건 · {comp_f}쌍 · 답(참고) · 세지 않는다). "
        + ("k = 0 ⇒ 주 표본과 **항등** · 판정 불변." if k3 == 0 else
           "k ≥ 1 ⇒ 갈래 값 의무 인쇄(판정 불변 · 계수 아님)."))

    # ── §8 P1~P3 ────────────────────────────────────────────────────────
    say()
    say("## §8. 개별 예측 `LAD-P1` · `P3` (§5-3 · **값 기록 · 기각 사유 아님**) · `LAD-P2` 종결 조각\n")
    say(f"- **`LAD-P1`** 「저자가 체결 차수를 명시」 — 10번째 글 **항목 12건 중 신규 {N_NEW_POST10}건 차수 명시 {N_NEW_POST10}건**(INTAKE §1 · 체결 차수). "
        f"후속 3건은 신규 분모 밖 ⇒ **분모 = 「DB 있는 신규 건」 = {N_NEW_POST10}건 ⇒ {N_NEW_POST10}/{N_NEW_POST10} = 100%** "
        "(`daily_prices` 존재 9/9 · PD-12) ⇒ ✅ **성립 · 7글 연속**(post4 6/6 → post5 6/6 → post6 10/10 → post7 10/10 → "
        "post8 7/7 → post9 5/5 → post10 9/9).")
    say(f"- **`LAD-P2`**(〔LAD-P2〕 조각): {T1_CLOSED} — 중앙값·구간 판정 **계산 0회**(`F-5` · #24 〔LAD-P2〕 조각 종결 · 〔LAD-P1〕·〔LAD-P3〕 는 계속).")
    say(f"- **`LAD-P3`** 「`first_only`(1차만 체결) 건 >= 1」 — 10번째 글 신규 **{len(FIRST_ONLY_POST10_NEW)}건**"
        f"({' · '.join(FIRST_ONLY_POST10_NEW)} · 전부 `exact`) ⇒ {'✅ **성립**' if FIRST_ONLY_POST10_NEW else '❌ 불성립'} "
        "(post4 0 → post5 1 → post6 3 → post7 6 → post8 6 → post9 3 → **post10 5**). `REC-Z4` 귀결은 🔒 결정 ④로 소멸(PD-13) ⇒ 「건 수」만 기록.")

    # ── §9 한계 ─────────────────────────────────────────────────────────
    say()
    say("## §9. 모호 지점 (양쪽 인쇄 · 「모호」 표기) · 한계\n")
    say("- 🔴 **`--rerun` 한계 — 다음 sweep 뒤** — 다음 D+1 sweep 이 창 구간 `updated_at` 을 일괄 갱신하면 D-9 ②·DB 지문이 "
        "**반드시** 바뀐다 ⇒ 그 뒤 재실행은 ① 에 새 시각이 박혀 이 산출물과 byte 가 달라진다 — 값이 틀렸다는 뜻이 아니라 동결 규칙"
        "(D-9 ② 인쇄 의무)의 귀결이다(byte 재현은 «같은 스냅샷» 안에서만 성립).")
    say("1. **읽은 시각 ①**(§0) — 벽시계라 재실행마다 다르다 ⇒ `ladder_post10/read_stamp.json` 에 «처음 읽은 시각»을 박고 같은 지문이면 잇는다"
        "(`P9-스탬프통일` · post10 부터 구속).")
    say("2. **post7 대체 «전» 갈래**(§1-1b) — 이번 회차 새 대체는 0 이지만 PD-23 이 갈래로 적어 구성(건 · 쌍)만 다시 셌다.")
    say("3. **후속 3건**(한컴위드·코데즈컴바인·빛샘전자) — 등록일 축 밖(PD-2 · 이중계상 금지) · 누적 풀 옛 행 그대로 · 한컴 원장 `fill_n` 3(서술 최대 차수) ↔ "
        "PD-43 의 「사이클 1 = 2」 표기는 후속이라 판정 효과 0(`확인 필요` 2).")
    say("4. **`H` = 등록일 고가는 가정** — `ANC-` 레인은 종결됐다(`F-5` (ㄱ)) · 이 산출물은 `H` 가정을 그대로 쓴다(`PREREG_POST6.md` §4 #44).")
    say("5. 🔴 **제도 경계(09-14)** — 누적 풀이 «두 제도»를 섞는다(§0-2 · post10 신규 창5 는 서산 1건만 걸치고 8건 전부 경계 후). 분모를 쪼개지 않았다"
        "(`PREREG_POST8.md` §14). 시간외분을 `H`·`L` 에서 뺄 수 없다 · 15:30 마감 분봉 소실(PD-27 (바) 한계 문장 인용).")
    say("6. `LAD-T1` 종결 — 이 축의 «판정»은 이제 `T2`·`T3`(반증축)와 `P1`·`P3`(기록)뿐이다 · `V` 는 개수이고 귀무에서 비교가능 쌍 수가 함께 흔들린다(`T2`·`T3`) · "
        "글 간 풀링이 국면을 섞는다(post4~post10 = 7주) · 표본은 저자가 올리기로 «고른» 매매다(「일부라도 매도된 종목」 · PD-32 · 기록).")
    say("7. **옛 `approx` 참고 행**(§7-1) — post8 구성(헥토·코데즈)만 잇는다. post7 `approx` 2건은 post8 도 넣지 않았다 — 누적 `approx` 갈래의 범위는 "
        "`P10-approx누적범위`(미발효)가 정한다(발효 시 (가) 누적 전건).")
    say("8. `N` 은 저자 서술 의존(「N차 매수 후」를 「N차까지 체결」로 읽었다) · 샌즈 `fill_n` = 사이클 1 서술 3(🔒 #1 ⓐ) — 사이클 2 의 1 로 읽으면 "
        "`LAD-` `N` 3 → 1(PD-43 교차 효과 · 인쇄만) · `n_up` sd 를 인쇄하지 않는다 ⇒ D-6 해당 없음.")
    say("9. **새 예측을 만들지 않았다** — δ·창5·게이트 40·시드·순열 표본 수 전부 동결값 그대로다.")
    say("10. 이 분석은 **라이브 채택 대상이 아니다**(`PREREG_POST10.md` §0-1).")

    numbers.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    print(f"\n[written] {numbers.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
