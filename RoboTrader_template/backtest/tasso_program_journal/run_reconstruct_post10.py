# -*- coding: utf-8 -*-
"""평단 P 복원 — 10번째 글 (REC-Y1~Y4 · REC-Z1~Z5 · Q1-R3 · P6-R1' · first_only 관측) · post9 판 «얇은 판».

동결 준거(1순위 — 이 docstring 은 2차 출처다):
  사전등록  `PREREG_POST10.md`(동결 `522d6dc`) §1 `P10-S5기호`(이 레인 밖) · §3 (나) `P10-기업행위봉`(`F-3`) · §5 (나) `P10-앵커종결`(`F-5`) ·
            `PREREG_POST9.md` §1 `P9-공통독법` · §4 `P9-결측분리`(`prog_ver` 공변량 미사용 ⇒ 해당 없음) · §6 `P9-스탬프통일`(post10 부터 구속)
          · `PREREG_POST8.md`(`D-3` · `D-5` · `D-9`)
          · `PREREG_POST6.md` §1-4·§1-5·§1-6·§1-7·§2-6·§2-7(A-1~A-11)·§3-3·§3-6·§4 #38~#54
          · `PREREG_WEIGHTED_RECON.md` §2-7 `WRC-R5` · `PREREG_ANCHOR_REDESIGN.md` §2-1·§2-3 · `PREREG_Q1_V2.md` §3
  인테이크  `PREDECISION_2026-10-04_post10.md`(PD-1·3·13·21·23·33·35·36·43) · `INTAKE_2026-10-04_post10.md` §1·§5
            · `LABELS_2026-10-04_post10.md`
  원장      `ledger_trades.csv`·`ledger_legs.csv` post10 12행/34레그(원장 커밋 = 실행 시 `git log` 로 읽는다)

🔴 **승계 원칙** — 판정 로직은 `run_reconstruct_post8.py` 의 함수를 «그대로» import 한다(수정 금지 파일):
   `core`·`win_stats`·`d19_start`·`md5_file`·`d3_hit`·`gc_status`·`re_dep_status`·`a_y1`~`a_r1`·
   `raw_key`·`pct`·`overlap`·`sign_of` + post5/post6 통계 핵. post9 판(`run_reconstruct_post9.py`)에서는 `TARGETS`·`END` 만 import(누적 재계산용).
   🔴 **새로 쓴 것(이탈 자기신고)**: ① `win5_count`(post9 판 사본 · 창 종료 인자) ② `read_stamp_resolve`(PD-35 `P9-스탬프통일` 키
   `first_read_kst`·`timezone`·`fingerprint` — post8 `stamp_resolve` 와 같은 규칙 · 키 이름만 다르다) ③ 갈래 표에 「샌즈 제외」 열 한 개 ④ `P10-기업행위봉` 인쇄(ⓑ 집계 SQL).
   판정 식 새로 쓰기 0.

🔴 **계산 «전» 에 고정한 해석 결정** — A-1~A-11 은 **전부 승계**(`PREREG_POST6.md` §2-7) · A-1 창 종료일만 이번 글 값:
  A-1 창 종료일 = **2026-10-02** (발행 2026-10-02(금) = 거래일 ⇒ 발행 당일 봉 «포함» · B-1 · PD-1).
  A-9 「하나의 평단」 전제 — 재진입 4 · 항목 내 2 사이클 1(샌즈 · 🔒 #1 ⓐ 한 건) = 판정 분모 안(§1-5 「분모에 넣는다」) · 제외 값 병기.

🔴 **이번 회차 구성**(인테이크 문언 · 값 아님):
  - 판정 분모 = 신규 ∧ `exact` = **9건** · `approx` 0 · `none` 0 + 후속 3(코데즈 · 빛샘 · 한컴 · 등록일 축 밖).
  - 레그≥4 exact **4**(라온 6 · 샌즈 4 · 성호 4 · HT 5) ⇒ `REC-Y1` 열림 예고 · 「샌즈 제외」 3 · 재진입 제외 4.
  - 갈래: §1-5 재진입 제외 = 9 ↔ 5(🔴 항등 아님) · 「샌즈 제외」 9 ↔ 8 · 절단 제외 = 항등 · `approx` 없음 · 「기업행위 건 제외」 인쇄 의무.
  - 🔴 `HDR-D1` 종결(`F-5`) — 계산 0회 · `REC-Y3` 의 `HDR-D1` 적용 중단 부분 「귀결 대상 종결(`F-5`)」 · `Q1-R3` 적용 중단은 산다 ·
    `REC-Z3` 제도 경계 분리 조항 없음(결정 ⑤ 기록 보존).
  - 🔴 D-9 ① = `reconstruct_post10/read_stamp.json`(같은 지문이면 파일을 다시 쓰지 않는다 · PD-35).

🔴 **라이브 채택 금지**(`PREREG.md` §0 2번 · `PREREG_POST10.md`) · 라이브 트리 import 0건 · DB 는 SELECT 만 ·
   `adj_factor` 산술 0건 · **새 예측 없음** · 등급 이름을 쓰지 않는다(§6 단계).
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import psycopg2

import run_reconstruct_post4 as P4M
import run_reconstruct_post5 as P5M
import run_reconstruct_post6 as P6M
import run_reconstruct_post7 as P7M
import run_reconstruct_post8 as P8
import run_reconstruct_post9 as P9
from reconstruct_prices import gross_ret, tick
from run_reconstruct_post5 import (feasible_pointwise, iv_max, iv_measure, iv_min,  # post8 이 쓴 같은 객체
                                   min_residual, sigma20)
from run_reconstruct_post6 import dd_h, fmt_pct, med, win_bars
from run_reconstruct_post8 import (a_q1r3, a_r1, a_y1, a_y2, a_y3, a_y4, a_z1, a_z2, a_z3, a_z4,
                                   core, d19_start, d3_hit, gc_status, md5_file, overlap, pct, raw_key,
                                   re_dep_status, sign_of, win_stats)
from run_tests import DSN

BASE = Path(__file__).resolve().parent
LEDGER_BASE = BASE         # 원장 게이트 읽기 자리(시험이 BASE 를 임시 폴더로 바꿔도 원장은 저장소에서 읽는다)
OUT: list = []

POST10_LOG_NO = "224429747319"
POST10_POST_DATE = "2026-10-02"
DB_UPTO = "2026-10-02"      # PD-1 · 창 종료 = 발행 당일(금 · 거래일) 봉 «포함» · 전 축
END = DB_UPTO               # A-1
PROG_VER = None             # 이 레인은 `prog_ver` 를 공변량으로 쓰지 않는다
BOUNDARY = P8.BOUNDARY      # 2026-09-14 KRX 거래시간 연장 발효일(제도 경계) · post8 상수 재사용
SWEEP_D1 = "2026-10-06 15:35:00"   # 10-02 봉의 D+1 sweep(10-03 토 · 10-04 일 · 10-05 개천절 대체공휴일 · PD-1)
WIN_START = "2026-08-12"    # 가장 이른 `[D−19, D]` 시작(서산 09-09 → 08-12 · 브리프 A-1)
THR_MAIN = P8.THR_MAIN      # 0.022 — REC-Z5 판정
THR_SENS = P8.THR_SENS      # 0.020 — REC-Z5 의무 민감도
SEED = P8.SEED              # 계열 고정 시드 — 🔴 이번 회차에도 «쓰이지 않는다»(결정 ④)
NREP = P8.NREP
CLOSED_BY_DECISION4 = P8.CLOSED_BY_DECISION4

# (종목, 코드, 등록일, 정밀도, 레그, 체결차수, 프리셋, 라벨, first_only, §1-5 재진입)
# 출처 = INTAKE_2026-10-04_post10.md §1 (신규 9건) · LABELS_2026-10-04_post10.md · PD-3 · PD-13 · 원장(post10 12행/34레그)
# 🔴 레그 = 원장 전 레그(손실률 레그 포함 · 음수 · `leg_open_ended` 무관) · 샌즈 `fill_n` = 사이클 1 서술 3(🔒 #1 ⓐ)
TARGETS = [
    ("라온시큐어", "042510", "2026-09-15", "exact", [12.78, 9.52, 6.40, 2.33, 0.32, -0.49], 4, "HDR60", "MIX", False, False),
    ("범한퓨얼셀", "382900", "2026-09-16", "exact", [7.79, 0.38], 1, "HDR60", "TP", True, True),
    ("서산", "079650", "2026-09-09", "exact", [3.01, 0.38], 5, "QRT", "TP", False, True),
    ("샌즈랩", "411080", "2026-09-14", "exact", [5.24, 4.88, 0.29, -0.02], 3, "HDR60", "MIX", False, False),
    ("성호전자", "043260", "2026-09-14", "exact", [26.39, 17.92, 13.71, 9.28], 1, "HDR60", "TP", True, False),
    ("HT로보틱스", "396300", "2026-09-18", "exact", [16.93, 12.36, 7.65, 7.63, 7.62], 3, "HDR60", "TP", False, False),
    ("한켐", "457370", "2026-09-16", "exact", [10.37], 1, "HDR60", "TP", True, True),
    ("뷰노", "338220", "2026-09-29", "exact", [15.63, 2.18], 1, "HDR60", "TP", True, False),
    ("우리로", "046970", "2026-09-18", "exact", [19.47, 15.44, 11.58], 1, "HDR60", "TP", True, True),
]
NM, CODE, D0, PREC, LEGS, TR, PRESET, LABEL, FO, REENT = range(10)
SANDS = "샌즈랩"            # 🔒 #1 ⓐ — 항목 내 2 사이클(재등록 09-29) · `WRC-R5` 구조차단 표시 · 「샌즈 제외」 민감도
REREG_NOTE = "재등록(샌즈랩 9/29 · 한컴위드 9/23) 날짜 기록 — 🔒 #1 ⓐ 한 건으로 센다(분모 9)"

# 🔴 후속 3건(REC- 축 밖 · 기록만). (이름, 코드, 출처, 직전 글 레그, 이번 글 레그)
FOLLOWUPS = [
    ("한컴위드", "054920", "post9 #6 · 09-15 · CONTINUATION", [7.55, 7.52], [7.50, 5.48]),
    ("코데즈컴바인", "047770", "post8 #9 · CONTINUATION", [], [0.12]),
    ("빛샘전자", "072950", "post9 #4 · 09-14 · CONTINUATION", [23.08, 21.05, 18.64, 16.46, 14.20, 12.26, 10.08],
     [27.52, 25.34]),
]

# 🔴 `F-3` `P10-기업행위봉` — `REC-` 창 = `[D−19, D]` 하나(PREREG_POST10 §3 (나) 축별 표) · ⓐ = corp_events `split`(PD-36 0/9)
CORP_NOTE_REF = "PD-36 · PREREG_POST10.md §3 (나)"

# 🔴 post4~9 동결 «인쇄값» — 대조 열로만 쓴다(재계산 값이 주). post4~8 = post9 판 `FROZEN` 객체 그대로.
FROZEN = dict(P9.FROZEN)
FROZEN["post9"] = dict(y3="3/5", y4n="3/5", z1="2/5", z3="5/5",
                       src="`RESULTS_RECONSTRUCT_POST9_NUMBERS.md` Y3 `:184` · Y4 `:203` · Z1 `:207` · Z3 `:228`")
QUOTED_SOLTLUX = P8.QUOTED_SOLTLUX

# 관리자 착수 조건 실측 — 보관 파일의 md5 를 이 스크립트가 직접 잰다(브리프 A-1).
MGR_PROBE_DIR = Path("D:/archive/tasso-program-journal-20261004/probes_precalc_1007")
MGR_PROBE_FILES = ["run_time.txt", "p10_probes_precalc_1007.txt", "p10_stab_3x.txt",
                   "p10_probes_precalc.sql", "p10_stab.sql", "md5.txt"]

STAMP = BASE / "reconstruct_post10" / "read_stamp.json"   # PD-35 `P9-스탬프통일`
OUT_NAME = "RESULTS_RECONSTRUCT_POST10_NUMBERS.md"

# PREREG_POST10.md 라이브 채택 금지 문언(그대로) — `PREREG.md:15` 원문 + `PREREG_POST8.md:26`
LIVE_BAN = ("🔴 **라이브 채택 아님**(`PREREG_POST10.md` · `PREREG.md` 「§0 2번」 `:15` 원문) — *「🔴 **라이브 채택 금지.** "
            "저자가 *\"사람이 할 일은 종목 고르는 것까지\"* 라고 적었다. 후보 선정이 재량이면 규칙을 복원해도 자동화 대상이 "
            "아니다. 이 검정의 산출물은 **기록**이지 전략 후보가 아니다.」* ⇒ *「이 문서가 만드는 **어떤 조항·규약·범주도** "
            "라이브 전략·파라미터 변경의 근거가 아니다」*(`PREREG_POST8.md:26`) · 🔴 *등급이 「성립」이어도 라이브 채택 금지는 "
            "그대로다*(`PREREG_GRADE_TIERS.md:30`)")


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


def win5_count(cur, code, d0, end):
    """창5 `[D, D+4]` 봉수 — 창 종료(end) 이하 봉만 센다. 🔴 post8 판 `win5_count` 와 같은 SQL · `END` 를 인자로 받는 사본."""
    cur.execute("SELECT count(*), max(date) FROM (SELECT date FROM daily_prices WHERE stock_code=%s "
                "AND date >= %s AND date <= %s ORDER BY date LIMIT 5) t", (code, d0, end))
    return cur.fetchone()


def win_line(w):
    """`D-9` 창 분류 — 걸침 / 전부 경계 후 / 전부 경계 전."""
    if w["before"] > 0 and w["after"] > 0:
        return "cross"
    return "after" if w["after"] > 0 else "before"


def read_stamp_resolve(st, fp, wall, tzname):
    """PD-35 `P9-스탬프통일` — 같은 DB 지문이면 «처음 읽은 시각»(`first_read_kst`)을 유지하고 파일을 **다시 쓰지 않는다**.
    키 = `first_read_kst`·`timezone`·`fingerprint`(post8 `stamp_resolve` 와 같은 규칙 · 키 이름만 통일). 반환 = (stamp, 써야 하나)."""
    if st and st.get("fingerprint") == fp and st.get("first_read_kst") and st.get("timezone"):
        return st, False
    return dict(fingerprint=fp, first_read_kst=str(wall), timezone=tzname), True


def ledger_gate():
    """브리프 §A-1 — 원장에 post10 12행/34레그가 «커밋된 채로» 있어야 한다. 아니면 (None, 사유) 를 돌려준다.
    커밋 = `git log -1 -- ledger_trades.csv` 의 해시 · 작업트리가 그 커밋과 다르면(미커밋) 거부."""
    with open(LEDGER_BASE / "ledger_trades.csv", encoding="utf-8", newline="") as f:
        trades = [r for r in csv.DictReader(f) if r["post_log_no"] == POST10_LOG_NO]
    with open(LEDGER_BASE / "ledger_legs.csv", encoding="utf-8", newline="") as f:
        legs = [r for r in csv.DictReader(f) if r["post_log_no"] == POST10_LOG_NO]
    if len(trades) != 12 or len(legs) != 34:
        return None, f"원장 post10 행 {len(trades)}/12 · 레그 {len(legs)}/34"
    dirty = subprocess.run(["git", "diff", "--quiet", "--", "ledger_trades.csv", "ledger_legs.csv"], cwd=str(LEDGER_BASE))
    if dirty.returncode != 0:
        return None, "원장 작업트리가 커밋과 다르다(미커밋)"
    cm = subprocess.run(["git", "log", "-1", "--format=%h", "--", "ledger_trades.csv"], cwd=str(LEDGER_BASE),
                        capture_output=True, text=True).stdout.strip()
    return dict(trades=trades, legs=legs, commit=cm), None


def ledger_match(gate):
    """TARGETS 의 레그가 원장 레그와 «값·순서 그대로» 같은지(9건) — 다르면 이름 목록을 돌려준다."""
    by = {}
    for r in gate["legs"]:
        by.setdefault(r["stock_name"], []).append((int(r["leg_idx"]), float(r["ret_pct"])))
    bad = []
    for t in TARGETS:
        got = [v for _, v in sorted(by.get(t[NM], []))]
        if got != list(t[LEGS]):
            bad.append(t[NM])
    return bad


def corp_scan(cur, code, s19, d0):
    """`F-3` 정의 A — `[D−19, D]` 안 ⓐ `corp_events` `split` 날짜 · ⓑ `daily_prices.volume = 0` 봉 날짜 · 기록 줄 = 창 안 `corp_events` 전 행.
    🔴 `adj_factor` 산술 0 · 가격·거래량을 조정하지 않는다 — `volume = 0` «존재»만 센다."""
    cur.execute("SELECT event_date, event_type FROM corp_events WHERE stock_code=%s AND event_date BETWEEN %s AND %s "
                "ORDER BY event_date, event_type", (code, s19, d0))
    allrows = [(str(a), b) for a, b in cur.fetchall()]
    a_rows = [d for d, ty in allrows if ty == "split"]
    cur.execute("SELECT date FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s AND volume = 0 "
                "ORDER BY date", (code, s19, d0))
    b_rows = [str(r[0]) for r in cur.fetchall()]
    return a_rows, b_rows, allrows


def main() -> int:  # noqa: C901
    gate, why = ledger_gate()
    if gate is None:
        print(f"[준비 완료 · 원장 대기] 러너를 실행하지 않는다 — {why}")
        return 2
    bad_ledger = ledger_match(gate)
    if bad_ledger:
        print(f"[중단] TARGETS 레그가 원장과 다르다: {bad_ledger}")
        return 3
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_RECONSTRUCT_POST10_NUMBERS — 기계 생성 (수정 금지)\n")
    say(f"- 🔴 **창 종료 {END} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**")
    cur.execute("SELECT max(date) FROM daily_prices")
    snap = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (snap,))
    snap_rows = cur.fetchone()[0]
    say(f"- 🔴 **실행 시 `max(date)` = {snap} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)**")
    say(f"- {LIVE_BAN}\n")
    say("생성 `run_reconstruct_post10.py`(post9 판 얇은 판) · 재사용 `run_reconstruct_post8.py`"
        "(`core`·`win_stats`·`d19_start`·`d3_hit`·`gc_status`·`re_dep_status`·`a_y1`~`a_r1`·`raw_key`·"
        "`FROZEN`) + `run_reconstruct_post9.py`(`TARGETS`·`END`·`FROZEN` — 누적 재계산) + `run_reconstruct_post5.py`(`feasible_exact`·"
        "`feasible_pointwise`·`min_residual`·`sigma20`·`bars`) + `run_reconstruct_post6.py`(`win_bars`·`dd_h`·`med`·`fmt_pct`) + "
        "`run_reconstruct_post4~8.py`(`TARGETS` — 누적 재계산) + `reconstruct_prices.py`(`tick`·`gross_ret`) · "
        "🔴 새 함수 = `win5_count`(창 종료 인자 사본) · `read_stamp_resolve`(키 통일) · `corp_scan`(`F-3` 인쇄) · `ledger_gate`·`ledger_match`(착수 게이트)")
    say("사전등록 `PREREG_POST10.md`(동결 `522d6dc` · §3 (나) `P10-기업행위봉` · §5 (나) `P10-앵커종결`) · `PREREG_POST9.md`(`P9-공통독법` · "
        "`P9-결측분리`(해당 없음) · `P9-스탬프통일`(post10 부터 구속)) · `PREREG_POST8.md`(`D-3`·`D-5`·`D-9`) · `PREREG_POST6.md` "
        "§1-4·§1-5·§1-6·§1-7·§2-6·§2-7·§3-3·§3-6·§4(#38~#54) · `PREREG_WEIGHTED_RECON.md` §2-7(`WRC-R5`) · "
        "`PREREG_ANCHOR_REDESIGN.md` §2-1·§2-3 · `PREREG_Q1_V2.md` §3")
    say("인테이크 `PREDECISION_2026-10-04_post10.md` · `INTAKE_2026-10-04_post10.md` · `LABELS_2026-10-04_post10.md` · "
        f"원장 기준 커밋 `{gate['commit']}`(post10 12행/34레그 · 작업트리 = 커밋 · 값 대조 9/9 일치)\n")

    # ── 스냅샷 · 창 구간 지문 (D-9 ②·④) ─────────────────────────────────
    cur.execute("SELECT count(*), count(DISTINCT date), min(updated_at), max(updated_at) FROM daily_prices "
                "WHERE date BETWEEN %s AND %s", (WIN_START, END))
    g_n, g_dates, g_umin, g_umax = cur.fetchone()
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (END,))
    end_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (SWEEP_D1[:10],))
    d1_rows = cur.fetchone()[0]
    cur.execute("SELECT now()")
    wall = cur.fetchone()[0]
    cur.execute("SHOW TimeZone")
    tzname = cur.fetchone()[0]
    fp = dict(win=f"{WIN_START}~{END}", n=g_n, dates=g_dates, umin=str(g_umin), umax=str(g_umax),
              snap=str(snap), snap_rows=snap_rows, end_rows=end_rows)
    try:
        st = json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = None
    st, st_changed = read_stamp_resolve(st, fp, wall, f"{tzname} (DB 세션 · now() = {wall})")
    if st_changed:
        STAMP.parent.mkdir(exist_ok=True)
        STAMP.write_text(json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    note(f"[stdout 전용] 이번 실행 벽시계(DB now()) = {wall} · 지문 최초 읽기 = {st['first_read_kst']} · "
         f"stamp {'새로 씀(지문 변경)' if st_changed else '다시 쓰지 않음(지문 동일)'}")
    umin_ok = str(g_umin) >= SWEEP_D1

    exact = [t for t in TARGETS if t[PREC] == "exact"]

    say("## §0. 실행 환경 · 승계 선언 · `PREREG_POST8`·`PREREG_POST9`·`PREREG_POST10` 공통 인쇄 의무\n")
    say("| 칸 | 값 |")
    say("|---|---|")
    say("| 🔴 라이브 채택 | **대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST10.md`) — "
        "이 문서의 어떤 숫자도 매매 규칙으로 옮기지 않는다 |")
    say(f"| 창 종료 | 🔴 **창 종료 {END} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
        "전 축(`WRC-` 포함) · PD-1** · 창 = `[등록일, " + END + "]` · 스크립트 상수 `DB_UPTO` |")
    say(f"| 실행 시 `max(date)` | **실행 시 `max(date)` = {snap} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)** |")
    say(f"| D-9 ① 쿼리 실행 시각(KST) | **{st['first_read_kst']}** (`timezone` = {st['timezone']}) — 🔴 이 DB 지문(②·④·`max(date)`·행수)을 이 스크립트가 "
        "«처음» 읽은 실행의 DB `now()` · 같은 지문의 재실행은 같은 값을 인쇄한다(byte 결정론 · 재실행 벽시계 = **stdout 전용** · "
        "`reconstruct_post10/read_stamp.json` 키 `first_read_kst`·`timezone`·`fingerprint` = `P9-스탬프통일` · 지문이 같으면 **다시 쓰지 않는다**) |")
    say(f"| D-9 ② 창 구간 `max(daily_prices.updated_at)` | **{g_umax}** (창 구간 `{WIN_START}` ~ `{END}` · 전 종목 "
        f"{g_n:,}행 · 거래일 {g_dates}) — 종목별 창의 값은 §0-b |")
    say(f"| D-9 ③ | **10-02 봉은 D+1(10-06) sweep 이후 읽음** — 10-06 행 {d1_rows:,} 존재 · ④ 기록 |")
    say(f"| D-9 ④ (기록 · 통과 조건 아님) | **창 구간 `min(updated_at)` = {g_umin} ≥ {SWEEP_D1[:16]}: "
        f"{'예' if umin_ok else '아니오'}** — 🔴 `updated_at` 은 sweep 이 전 행을 일괄 갱신한 값이라 "
        "빈티지 «증거»가 아니라 「그 sweep 이 창 구간을 한 번 훑고 지나갔다」는 기록이다(PD-27 (라)·(마) 2 (f)) |")
    say(f"| 10-02 행수 | **{end_rows:,}** (인테이크 실측 2,768 · 관리자 착수 조건 관측 10-07 19:35:46/19:36:08/19:36:31 · 대조만) |")
    say("| `P-3` | 🔴 **판별력 0 — 「통과」로 인용하지 않는다**(`updated_at > created_at` 항등 참 · PD-27 (라)) · 인쇄만 |")
    say("| A-1~A-11 | **A-1 ~ A-11 전부 승계**(`PREREG_POST6.md` §2-7 · post8 판 docstring 문장) — "
        f"A-1 의 창 종료일만 이번 글 값 **{END}** 으로 바뀐다 |")
    say("| A-11 | **정확 구간법이 유일한 방법**(§3-6) · 점법은 **폐기** — 대조로만 인쇄하고 인용 시 **「하한」**이라 적는다 |")
    say("| D-9 빈티지 정의 | `P8-빈티지` = `daily_prices.high`/`low` 의 **«D+1 안정 빈티지»**(시간외분이 들어간 채로 · "
        "`PREREG_POST8.md:539-540`) — 🔴 **「정규장만」 갈래는 열지 않는다**(`:549-550`) · `adj_factor` 산술 **0**(`:551`) |")
    say(f"| 판정 분모 | 🔴 **신규 ∧ `exact` = {len(exact)}건**(" + "·".join(t[NM] for t in exact) + ") — "
        f"`REC-` 대상 **{len(exact)}/{len(exact)}** · 🔒 #1 ⓐ — {REREG_NOTE} · 재진입 {sum(1 for t in exact if t[REENT])}"
        f"(" + "·".join(t[NM] for t in exact if t[REENT]) + ") · 샌즈랩 = 항목 내 2 사이클(`WRC-R5` 구조차단 표시) |")
    say("| `approx`·`none` | **0건 · 0건**(PD-4) ⇒ `approx` 갈래 없음 · 「창 규약」 갈래 없음 |")
    say(f"| 등록일 축 밖 | 후속 **{len(FOLLOWUPS)}건**(" + "·".join(f[0] for f in FOLLOWUPS) +
        " · 원장 `reg_date` 비움·`none`) |")
    say(f"| `REC-Z5` | 판정 **{THR_MAIN:.3f}%p 단일** · **{THR_SENS:.3f}%p 의무 민감도**(갈리면 「문턱 민감」 인쇄 · "
        "판정은 0.022 로 선다 — §1-7) |")
    say("| 결정 ④ | 🔴🔴 `PREREG_BUYLADDER` 계열 **종결** ⇒ " + " · ".join(CLOSED_BY_DECISION4) +
        " **재개하지 않는다 · 기록 보존만**(§10) |")
    say("| 🔒 `F-5` `HDR-D1` | 🔴 **종결 · 계산 0회**(`PREREG_POST10.md` §5 (나) · `P10-앵커종결`) — §12 참조 |")
    say(f"| 시드 | `SEED` = {SEED} · `NREP` = {NREP:,} — 🔴 **이 스크립트는 귀무를 돌리지 않는다**(축 종결 · 시드 불변) |")
    say("| `prog_ver` | `1.0.43`(원 표기 「1.0.43V」) — 🔴 이 산출물은 `prog_ver` 를 공변량으로 **쓰지 않는다** ⇒ `D-8` 수준 목록 "
        "의무 대상 아님 · `P9-결측분리` 해당 없음(§0-c) |")
    say()
    say("**관리자 착수 조건 실측(2026-10-07 19:35:46~19:36:33 KST · 보관 파일 md5 = 이 스크립트가 직접 잰 값)**\n")
    say("| 보관 파일(`" + str(MGR_PROBE_DIR).replace("\\", "/") + "/`) | md5 |")
    say("|---|---|")
    for f in MGR_PROBE_FILES:
        m = md5_file(MGR_PROBE_DIR / f)
        say(f"| `{f}` | `{m if m else '없음(경로 미존재)'}` |")
    say()
    say("- 실측(옮겨 적음 · 대조용 · 브리프 A-1): 10-06 2,768행 ×3 · 10-07 2,767행 ×3 · 창 `[08-12, 10-02]` `min(updated_at)` = "
        "2026-10-07 15:45:21.82908 · `max(updated_at)` = 2026-10-07 15:46:38.364963 · `P-3` 판별력 0(인쇄만)")

    # ── §0-c. 인쇄 의무 체크 ─────────────────────────────────────────────
    say()
    say("## §0-c. 인쇄 의무 체크 — `PREREG_POST8` · `PREREG_POST9` · `PREREG_POST10` 구속(이 산출물)\n")
    say("| 의무 | 이 산출물 | 자리 |")
    say("|---|---|---|")
    say("| `D-9` ① 실행 시각(`read_stamp.json`) · ② `max(updated_at)` · ③ D+1 sweep 줄 · ④ `min(updated_at)` 기록 · ⑤ 혼합 빈티지 신고 | "
        "**적용** — 🔴 `REC-` 창 두 개(`[D−19, D]` · `[D, END]`) **둘 다** · 「전부 경계 후/전」 추가 인쇄(PD-27 (바)) | §0 · §0-b |")
    say("| `D-3` `P8-approx의존신고` 한 줄 | **적용** | §15 |")
    say("| `D-5` `P8-갈래계수` — 갈래마다 `(이름, n, 답)` | **적용**(항등 갈래도 인쇄 · 재진입 = 항등 아님) | §14 |")
    say("| `P9-공통독법`(`PREREG_POST9.md` §1 (나)3) | **적용 — 신고 줄** | §15 |")
    say("| `P9-행단위`·`P9-결측분리`(§4) | 해당 없음 — 이 산출물은 `prog_ver` 를 쓰지 않는다 · *「부호 갈림 검사: 통계량 정의 없음(기록만)」* | §0 |")
    say("| `P9-스탬프통일`(§6 · post10 부터 구속) | **적용** — `reconstruct_post10/read_stamp.json` 키 `first_read_kst`·`timezone`·`fingerprint` | §0 |")
    say("| `D-6` `ddof` | 해당 없음 — 이 산출물은 `n_up` sd 를 인쇄하지 않는다 | — |")
    say("| `D-1`·`D-2`·`D-4`·`D-7`·`D-11` | 해당 없음 — 다른 축(`ANC-`·`EXIT-`·`WRC-`·`LAD-`·`REG-`) | — |")
    say("| `D-10` 등급 열 | 이 산출물은 등급을 쓰지 않는다(§6 단계 · PD-16·PD-28) | — |")
    say("| 🆕 `F-3` `P10-기업행위봉`(§3 (나)) | **적용** — 신고 줄 + 「기업행위 건 제외」 갈래 값 의무 인쇄(답(참고) · 세지 않는다) | §0-b · §14 |")
    say("| 🆕 `F-5` `P10-앵커종결`(§5 (나)) | **적용** — `HDR-D1` 종결 · 계산 0회 · `REC-Y3` 귀결 대상 종결 줄 · `REC-Z3` 제도 경계 분리 조항 없음 | §5 · §8 · §12 |")
    say("| 🆕 감시 줄(PD-33 — `REC-Y3`) | **적용** | §5 |")

    # ── §0-b. D-9 창별 읽은 시각 · 혼합 빈티지 신고 ─────────────────────
    say()
    say("## §0-b. `D-9` — 종목별 창 · 읽은 시각(`updated_at`) · `P8-혼합빈티지신고` (🔴 `REC-` 창 두 개 다) · `F-3` 신고 줄\n")
    say("🔴🔴 **충돌 신고(§1-8 형식 · post8 정오표 ③ 승계 · PD-27 (바))** — `PREREG_POST8.md:546` 은 `REC-`/`REG-` = "
        "**`[D−19, D]`** 로 적고, `PREREG_ANCHOR_REDESIGN.md:115-124`(§2-1)는 `L`·`HI` 를 **`[D, END]`** 위에 정의한다. "
        "🔑 이 레인은 **둘 다 실제로 읽는다** — `[D, END]` = `L`·`HI`·feasible 봉(§1·§8) · `[D−19, D]` = `P6-R1'` 의 "
        "`H6`(§13) · 절단 가드(§16) · `F-3` 창. ⇒ **두 창 다 인쇄**한다.\n")
    say("| 종목 | 정밀도 | 창 | 구간 | 봉수 | 경계 전 | 경계 후 | 분류 | 창 `min(updated_at)` | 창 `max(updated_at)` |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    cross_lines, after_lines, before_lines = [], [], []
    vint = {}
    lab_a, lab_b = "`[D, END]`(ANC §2-1)", "`[D−19, D]`(POST8 :546)"
    for t in exact:
        s19, _n19 = d19_start(cur, t[CODE], t[D0])
        wa = win_stats(cur, t[CODE], t[D0], END)
        wb = win_stats(cur, t[CODE], s19, t[D0])
        vint[t[NM]] = (wa, wb)
        for lab, w in ((lab_a, wa), (lab_b, wb)):
            k = win_line(w)
            cls = {"cross": "🔴 **걸침**", "after": "🟡 **전부 경계 후**", "before": "전부 경계 전"}[k]
            say(f"| {t[NM]} | exact | {lab} | `[{w['first']}, {w['last']}]` | {w['n']} | {w['before']} | "
                f"{w['after']} | {cls} | {w['umin']} | {w['umax']} |")
            if k == "cross":
                cross_lines.append(f"- {t[NM]} {lab.split('(')[0]}: *「창 `[{w['first']}, {w['last']}]` 은 "
                                   f"제도 경계 2026-09-14 를 걸친다 — 경계 전 `{w['before']}` 봉 / 후 `{w['after']}` 봉 · "
                                   "혼합 빈티지」*")
            elif k == "after":
                after_lines.append(f"- {t[NM]} {lab.split('(')[0]}: *「창 `[{w['first']}, {w['last']}]` 은 전부 제도 경계 후"
                                   f"(전 {w['before']} / 후 {w['after']})」*")
            else:
                before_lines.append((t[NM], lab.split('(')[0]))
    say()
    say(f"**`P8-혼합빈티지신고`(의무 문장 · `PREREG_POST8.md:546-548` · 걸침 창 {len(cross_lines)}개)**\n")
    for ln in cross_lines:
        say(ln)
    say()
    say(f"**🆕 「전부 경계 후」 추가 인쇄(PD-27 (바) · 재량 · 판정 효과 0 · 신고 줄 대상 아님 · {len(after_lines)}개)**\n")
    for ln in after_lines:
        say(ln)
    say()
    cd_cross = [nm for nm, (wa_, wb_) in vint.items() if win_line(wb_) == "cross"]
    cd_before = [nm for nm, (wa_, wb_) in vint.items() if win_line(wb_) == "before"]
    say(f"- 🆕 **`[D−19, D]` 걸침 {len(cd_cross)}줄 ({', '.join(cd_cross) if cd_cross else '없음'}) + 「전부 경계 전」 "
        f"{len(cd_before)}줄 ({', '.join(cd_before) if cd_before else '없음'})**(`D-9` 추가 줄 · 서산 「전부 경계 전」 확인 대상 — "
        f"서산 `[D−19, D]` = {win_line(vint['서산'][1])})")
    # `F-3` — 기업행위 건 (`REC-` 창 = `[D−19, D]` 하나)
    corp = {}
    corp_all = {}
    for t in exact:
        s19, _n = d19_start(cur, t[CODE], t[D0])
        a_rows, b_rows, allrows = corp_scan(cur, t[CODE], s19, t[D0])
        corp_all[t[NM]] = (s19, allrows)
        if a_rows or b_rows:
            corp[t[NM]] = (a_rows, b_rows)
    CORP_SET = set(corp)
    k_corp = len(corp)
    reasons = " · ".join(
        f"{nm}: " + (f"ⓐ split {', '.join(a)}" if a else "") + (" / " if a and b else "") +
        (f"ⓑ `volume=0` {len(b)}봉 {', '.join(b)}" if b else "")
        for nm, (a, b) in corp.items()) or "건 없음"
    say(f"- 🆕 **`P10-기업행위봉`: 기업행위 건 {k_corp}/{len(exact)} — {reasons} · `adj_factor` 산술 0 · 처리 = (나)** "
        f"(`F-3` 정의 A · 창 = `[D−19, D]` 하나 · ⓐ `corp_events` `split` · ⓑ `daily_prices.volume = 0` 봉 · ⓒ dart 거래정지 공시 제목은 신고 줄에만 — "
        f"인테이크 PD-36 ⓐ 0/9 · ⓑ 는 이 레인이 착수 뒤 집계)")
    corp_rec = {nm: (s, r) for nm, (s, r) in corp_all.items() if r}
    say("- 🆕 **창 안 `corp_events` 전 행(기록 줄 · 분류 효과 0 · 모든 `event_type`)**: " +
        (" · ".join(f"{nm} `[{s}, ..]` " + ", ".join(f"{d} {ty}" for d, ty in r) for nm, (s, r) in corp_rec.items())
         if corp_rec else "없음"))
    say("- 참고(이 산출물은 봉수만 읽는다 · `H`·`L` 을 읽지 않는다): 창5 `[D, D+4]` 는 `LAD-` 축 창이다 — 걸침 신고는 "
        "`LAD-` 레인이 맡는다. §16 에 봉수만 적는다.")
    say("- post4~9 재계산 창(§17): post4~7 은 전부 종료 ≤ 2026-09-11(경계 «전») · post8 종료 09-18 · post9 종료 09-23(걸침 — 각 산출물이 "
        "이미 신고 줄을 인쇄했다 · 이 표는 `updated_at` 만 다시 적는다 · PD-27 (바) `:618` 문형).")
    say("- 🔴 **「정규장만」 값은 만들지 않았다** — 뺄 소스도 재구성 경로도 없다(한계 · `PREREG_POST8.md:549-550`) "
        "⇒ **「정규장만」 갈래는 열지 않는다**.")
    say("- 🔴 **방향 추론 인용 금지** — 「시간외분이 `H` 를 높이고 `L` 을 낮춘다」는 추론이다(`PREREG_POST8.md:586-589`).")

    # ── §1. feasible 원표 ────────────────────────────────────────────────
    say()
    say("## §1. feasible set 원표 (gross · A-11 정확 구간법) — 의무 인쇄 5칸\n")
    say("의무 인쇄(§3-6): **구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)**\n")
    say(f"🟢 **주 판정 분모 = `exact` {len(exact)}건**(PD-4) — 구조차단 0 · 재진입 0.\n")
    say("| 종목 | 차수 | 라벨 | 등록일 | 레그 | 등록일 봉 [저,시,고,종] | 되밀림 | "
        "**구간 개수** | **P 범위** | **총 측도(원)** | **`1-P/H` 범위** | **폭** | "
        "**폭/호가단위(칸)** | (대조·하한) 점법 개수/폭 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    R = {}
    for t in exact:
        nm = t[NM]
        v = core(cur, t[CODE], t[D0], END, t[LEGS])
        v.update(tr=t[TR], preset=t[PRESET], label=t[LABEL], fo=t[FO], reent=t[REENT])
        v["pts"] = feasible_pointwise(v["rows"], v["legs"], gross_ret)
        R[nm] = v
        pts = v["pts"]
        pw = f"{len(pts)} / {(max(pts) - min(pts)) / v['h0'] * 100:.2f}%p" if pts else "0 / —"
        bar = f"[{v['l0']:,.0f}, {v['o0']:,.0f}, {v['h0']:,.0f}, {v['c0']:,.0f}]"
        pull_s = "예" if v["pull"] else "아니오"
        if v["iv"]:
            say(f"| {nm} | {t[TR]}차 | {t[LABEL]} | {t[D0]} | {len(t[LEGS])} | {bar} | {pull_s} | "
                f"**{len(v['iv'])}** | {v['pmin']:,.2f}~{v['pmax']:,.2f} | **{v['measure']:,.2f}** | "
                f"{v['b1'][0]:+.2f}%~{v['b1'][1]:+.2f}% | **{v['w']:.2f}%p** | "
                f"**{v['cells']:.1f}칸**({tick(v['pmin'])}원) | {pw} |")
        else:
            say(f"| {nm} | {t[TR]}차 | {t[LABEL]} | {t[D0]} | {len(t[LEGS])} | {bar} | {pull_s} | "
                f"**0** | — | **0.00** | — | — | — | {pw} |")
    say()
    say(f"- 되밀림(A-3: 종가 < 고가) **{sum(1 for v in R.values() if v['pull'])}/{len(R)}** · "
        f"상한가마감(종가==고가) **{sum(1 for v in R.values() if not v['pull'])}/{len(R)}**")
    say("- 고가 대비 종가 되밀림 폭: " + " · ".join(
        f"{nm} {100 * (v['h0'] - v['c0']) / v['h0']:.2f}%" for nm, v in R.items()))
    live = [(nm, v) for nm, v in R.items() if v["iv"]]
    if live:
        say("- feasible 총 측도(정확법): " + " · ".join(f"{nm} {v['measure']:,.2f}원" for nm, v in live) +
            " — 🔑 *「범위 안에 든다」와 「해다」는 다른 진술이다*: 범위 대비 측도를 함께 본다.")
        dirs = " · ".join(f"{nm} {(max(v['pts']) - min(v['pts'])) / v['h0'] * 100:.2f}→{v['w']:.2f}%p"
                          for nm, v in live if v["pts"])
        say("- 🔴 **점법 대 정확법**(A-11 *「점법 값은 전부 하한」* 방향 확인): " +
            (dirs if dirs else "해가 있는 건에 점법 해 0개"))
    else:
        say("- feasible 총 측도(정확법): 해가 있는 건 **0** — 점법 대조도 대상 없음")

    dec_bad = [nm for nm, v in R.items() if any(round(x, 2) != x for x in v["legs"])]
    say(f"- 🟢 **소수 자릿수 한계 대상 {len(dec_bad)}건** — `exact` {len(R)}건의 레그는 전부 소수 2자리(0자리 레그 없음).")
    ties = [nm for nm, v in R.items() if len(set(v["legs"])) < len(v["legs"])]
    say("- 🔴 **동률 레그**: " + (", ".join(ties) if ties else "**없음**(레그 값이 전부 서로 다르다)") +
        " — 있으면 다중집합 그대로 푼다(같은 값 두 레그 = 같은 제약 두 번 · PD-10 2).")
    neg = [(nm, [x for x in v["legs"] if x < 0]) for nm, v in R.items() if any(x < 0 for x in v["legs"])]
    say("- 🔴 **손실률(음수) 레그**: " + ", ".join(f"{nm} {xs}" for nm, xs in neg) +
        " — 원장 `is_loss=1` 레그를 값 그대로(부호 포함) 푼다(원장 전 레그 · 레그 = 원장 전 레그). 사이클 귀속은 원문에 없다(LABELS).")
    multi_ = [nm for nm, v in R.items() if v["tr"] >= 2]
    say(f"- 🔴 **다차수 {len(multi_)}건**({', '.join(multi_)}) — 매도는 전부 매수 «뒤» 서술이라 A-9 「하나의 평단」 "
        "전제 깨짐 flag 는 **달지 않는다**(원문에 매도 사이 매수 서술 0) · 🔴 그 평단이 여러 체결의 합이고 레그 수익률이 어느 평단 "
        "기준인지 원문에 없다(LABELS · 해석 안 함). 🔴 샌즈랩 `fill_n` = 사이클 1 서술 3(🔒 #1 ⓐ · 대안 = 사이클 2 의 1 이면 다차수 4 → 3).")
    say(f"- 🔴 **샌즈랩 = 항목 내 2 사이클**(`WRC-R5` `구조차단` 표시 · 포함 + 「샌즈 제외」 민감도 · {REREG_NOTE}).")


    # ── §1-c. 등록일 축 밖 ───────────────────────────────────────────────
    say()
    say(f"## §1-c. 등록일 축 «밖» — 후속 {len(FOLLOWUPS)}건 (구성으로 빠진다 · `approx`·`none` 신규 0)\n")
    say("| 종목 | 코드 | 출처 | 직전 글 레그 | 이번 글 레그 | 연결 지점 | 왜 밖인가 |")
    say("|---|---|---|---|---|---|---|")
    for nm, code, why, lp, lc in FOLLOWUPS:
        if lp:
            link = f"{lp[-1]:.2f} → {lc[0]:.2f} {'🔴 **증가**' if lc[0] > lp[-1] else '감소/같음'}"
        else:
            link = "— (직전 글 레그 원장 대조 없음 · 기록만)"
        say(f"| {nm} | {code} | 🔁 **후속**({why}) | {lp if lp else '—'} | {lc} | {link} | PD-2 2번 **등록일 축 밖**"
            "(이중계상 금지 · 원장 `reg_date` 비움·`none`) |")
    say()
    say("- 🔴 **값을 보고 뺀 것이 아니라 «정의로» 빠진다**(PD-2 2) · 🔴 **연결 시퀀스는 `REC-` 어디에도 넣지 않는다**.")
    say("- 🔴 한컴위드 재등록 09-23 = 🔒 #1 ⓐ 로 어느 축에도 들어가지 않는다(비대칭 한 줄 · PD-43) · 후속 3 종목은 `corp_events` `split` 0(PD-36).")

    # ── §2. 해 0개 진단 · REC-Z5 ─────────────────────────────────────────
    say()
    say("## §2. 해 0개 진단 · `REC-Z5` — 판정 0.022 / 민감도 0.020\n")
    say("`Δr_min` = 서로 «다른» 인접 레그 수익률의 최소 간격(%p) · `res` = 호가 한 칸이 만드는 수익률 해상도 `100*tick(P)/P`\n")
    say("🔑 `Δr_min < res` 이면 **두 레그를 격자 위 서로 다른 매도가로 표현할 수 없다** ⇒ 산술적으로 해가 0개다.\n")
    say("| 종목 | 레그 | `Δr_min` | 후보 P 범위 | `res`(P 양끝) | **`Δr_min` < `res`?** | "
        "최소잔차 적합 P | **최대 오차** | **판정 @0.022** | (민감도) @0.020 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    split = []
    for nm, v in R.items():
        mr = min_residual(v["rows"], v["legs"], gross_ret)
        v["minres"] = mr
        diags = []
        for th in (THR_MAIN, THR_SENS):
            if v["iv"]:
                diags.append(f"해 {len(v['iv'])}구간 (진단 불필요)")
            elif mr is None:
                diags.append("🔴 적합 실패")
            elif mr[0] < th:
                diags.append("반올림으로 설명 가능")
            else:
                diags.append("🔴 **모델이 틀렸다**")
        v["diag"] = diags
        if not v["iv"] and mr is not None and diags[0] != diags[1]:
            split.append(nm)
        dm_s = "—" if v["dmin"] is None else f"{v['dmin']:.2f}%p"
        mr_p = "—" if mr is None else f"{mr[1]:,.0f}"
        mr_e = "—" if mr is None else f"**{mr[0]:.6f}%p**"
        say(f"| {nm} | {v['legs']} | {dm_s} | {v['pl']:,.0f}~{v['ph']:,.0f} | {v['r_hi']:.3f}~{v['r_lo']:.3f}%p | "
            f"{'🔴 **예**' if v['under'] else '아니오'} | {mr_p} | {mr_e} | {diags[0]} | {diags[1]} |")
    say()
    say(f"- 두 문턱에서 분류가 갈리는 건: **{len(split)}건** ({', '.join(split) if split else '없음'}) ⇒ "
        + ("🔴 **「문턱 민감」** — 판정은 0.022 로 서고 그 사실을 여기 인쇄한다."
           if split else "**문턱 민감 없음**(0.020·0.022 에서 분류 동일)"))
    say(f"- 격자 해상도 미달(`Δr_min` < `res`) 건: **{sum(1 for v in R.values() if v['under'])}/{len(R)}** ("
        + (", ".join(nm for nm, v in R.items() if v["under"]) or "없음") + ")")
    one_leg = [nm for nm, v in R.items() if v["dmin"] is None]
    say("- 🔑 서로 다른 값 레그가 **1개뿐인 건**은 `Δr_min` 이 «정의되지 않는다» — 격자 미달 판정에서 빠진다: "
        + (", ".join(one_leg) if one_leg else "이번 표본 **0건**"))

    say("- 🔑 `Δr_min` 은 서로 «다른» 값 사이 간격만 센다(post5~9 식 그대로 · 동률은 간격에 넣지 않는다 · 최소 간격 = 소수 2자리 표기의 최소 단위 0.01%p).")

    # ── §3. REC-Y1 ───────────────────────────────────────────────────────
    say()
    say("## §3. `REC-Y1`(핵심) — 레그 4개 이상인 건의 `b1` feasible 폭 < 3%p (전칭 · A-2)\n")
    say("| 종목 | 정밀도 | 레그 | 구간 개수 | 총 측도(원) | 폭 | < 3%p |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        if len(v["legs"]) < 4:
            continue
        if not v["iv"]:
            say(f"| {nm} | exact | {len(v['legs'])} | **0** | 0.00 | ⛔ **미정의**(해 0개) | ⛔ |")
        else:
            say(f"| {nm} | exact | {len(v['legs'])} | {len(v['iv'])} | {v['measure']:,.2f} | "
                f"**{v['w']:.2f}%p** | {'성립' if v['w'] < 3.0 else '위반'} |")
    y1n, y1ans, _, _ = a_y1(R)
    say()
    say(f"- 레그>=4 **`exact` 대상 {y1n}건**(" + ", ".join(nm for nm, v in R.items() if len(v["legs"]) >= 4) +
        f") · 최소 n **3**(#38) ⇒ **{'충족' if y1n >= 3 else '미달'}** (post7 2 < 3 닫힘 · post8 3 열림 · post9 2 < 3 닫힘)")
    say(f"- ⇒ **`REC-Y1` = {y1ans}**(판정 문형 = `run_reconstruct_post6.py:333-339` 승계 · 최소 n 미달이면 판정하지 않는다)")

    say("- 🔴 후속 3건(한컴위드 · 코데즈컴바인 · 빛샘전자)은 **등록일 축 밖**(PD-2 2) — 레그≥4 대상에 넣지 않는다 · `approx` 0 ⇒ `approx` 포함 분모 = "
        f"**{y1n}**(`D-3` 신고 대상 아님 · §15).")

    say("- 🔴 *「해가 없으니 폭 0 = 3%p 미만 = 성립」*으로 읽으면 규칙 완화다. **읽지 않았다.** 최소 n 미달 건의 폭은 **인쇄만** 한다.")
    say(f"- 🔴 **방향 자기신고**(PD-13 축자): 이번에 «열리는» 것은 **저자가 레그를 적은 수**(레그≥4 = {y1n}건 · 라온 6 · 샌즈 4 · 성호 4 · HT 5)가 만든 구성이다 — "
        "값을 보고 정한 규칙이 아니다.")
    S_sx = {k: v for k, v in R.items() if k != SANDS}
    say(f"- 🆕 **`REC-Y1` 열림 예고 검증**: 레그≥4 exact **{y1n}**(예고 4) · 「샌즈 제외」 **{sum(1 for v in S_sx.values() if len(v['legs']) >= 4)}**(예고 3) · "
        f"재진입 제외 **{sum(1 for k, v in R.items() if not v['reent'] and len(v['legs']) >= 4)}**(예고 4 · 재진입 4건 전부 레그 < 4).")

    # ── §4. REC-Y2 ───────────────────────────────────────────────────────
    say()
    say("## §4. `REC-Y2`(반증축 · 필수) — 폭을 «호가단위 배수»로도 인쇄\n")
    say("Y2: *「레그 수와 무관하게 폭이 좁으면 원인은 레그 수가 아니라 가격대(호가단위)다」*\n")
    say("| 종목 | 레그 | 가격대 | 호가단위(P 하단) | 폭(%p) | **폭 / 호가단위(칸)** | (대조·하한) 점법 칸 |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        if not v["iv"]:
            say(f"| {nm} | {len(v['legs'])} | {v['L']:,.0f}~{v['HI']:,.0f} | — | — | — | — |")
            continue
        pwc = ((max(v["pts"]) - min(v["pts"])) / tick(min(v["pts"]))) if v["pts"] else None
        say(f"| {nm} | {len(v['legs'])} | {v['L']:,.0f}~{v['HI']:,.0f} | {tick(v['pmin'])}원 | {v['w']:.2f}%p | "
            f"**{v['cells']:.1f}칸** | {'—' if pwc is None else f'{pwc:.1f}칸'} |")
    y2n, y2ans, _, _ = a_y2(R)
    say()
    say(f"- ⇒ **`REC-Y2` = {y2ans}** (좁은 폭 < 3%p 건 {y2n}) · 누적 대상: post6 1(지투파워) + post7 0 + post8 1(우리로) + "
        f"post9 1(빛샘전자) + post10 {y2n}")

    # ── §5. REC-Y3 ───────────────────────────────────────────────────────
    say()
    say("## §5. `REC-Y3`(중단 규칙) — feasible set 이 비는 비율\n")
    empty = [nm for nm, v in R.items() if not v["iv"]]
    frac = len(empty) / len(R)
    multi = [nm for nm, v in R.items() if v["tr"] >= 2]
    empty_multi = [nm for nm in empty if R[nm]["tr"] >= 2]
    say(f"- 해 0개(정확법 · `exact` {len(R)}건): **{pct(len(empty), len(R))}** "
        f"({', '.join(empty) if empty else '없음'})")
    say(f"- 사전등록 문턱 **>= 1/3 = 33.3%** ⇒ **{'🔴 발동' if frac >= 1 / 3 else '미발동'}**")
    say(f"- 다차수(2차 이상) 건 **{len(multi)}/{len(R)}** ({', '.join(multi) if multi else '없음'}) 중 해 0개 "
        f"**{len(empty_multi)}** ({', '.join(empty_multi) if empty_multi else '없음'})")
    if frac >= 1 / 3:
        say("- ⇒ 🔴🔴 **「다차수 건에서 평단이 매도 중 변한다」로 읽고, 복원 기반 축(`Q1-R3`·`HDR-D1`)을 «다차수 건»에 "
            "적용하는 것을 중단한다.** 🔴 **`HDR-D1` 적용 중단 부분 = 귀결 대상 종결(`F-5`)** · **`Q1-R3` 적용 중단은 산다**(`P10-앵커종결` (나)4). (`RESULTS_RECONSTRUCT_POST4.md` §6 Y3 동결 문언 — 값을 보고 정한 규칙이 아니다.) "
            "🔴 `P6-L3'`·`BUY-L5` 는 **결정 ④로 이미 종결**이라 중단 대상 목록에서 «자동으로» 빠진다.")
        say(f"- 🔑 중단은 «다차수 건»에만 걸린다 — 🆕 **이번 `exact` 는 다차수 {len(multi)}건** ⇒ 중단이 실제로 빼는 건 "
            f"**{len(multi)}건**(" + (", ".join(multi) if multi else "없음") + ") · post9 는 2건 · post8 은 0건(실효 0)이었다.")
    else:
        say("- ⇒ **중단 미발동** — 복원 기반 축을 다차수 건에도 적용한다.")
    if empty and all(R[nm]["tr"] == 1 for nm in empty):
        say("- 🔴 **해 0개 건이 전부 1차 체결이다** — 동결 해석문(「다차수 건에서 평단이 변한다」)과 이번 표본의 모양이 어긋난다"
            "(**발동은 문언대로 · 어긋남은 관측으로** · 해석문을 고치지 않는다).")
    say(f"- 🔴 **감시 줄**(PD-33 `:692` · 보고서 §6 할 일 5 「`REC-Y3` 2글 연속 문턱에 «정확히»」): post10 = **{pct(len(empty), len(R))}** · "
        f"문턱 1/3 에 «정확히» 닿았나 = **{'예' if len(empty) * 3 == len(R) else '아니오'}** · "
        f"한 건 더 비면 {pct(len(empty) + 1, len(R))} · 한 건 덜 비면 "
        f"{pct(max(len(empty) - 1, 0), len(R))} (산술만 · 판정 아님)")
    say(f"- 계열(같은 스냅샷 재계산 · §17): 이 문서의 post10 값 **{pct(len(empty), len(R))}** — "
        "post4~9 는 §17 표(동결 인쇄값 post4 1/6 → post5 4/6 → post6 5/10 → post7 2/6 → post8 1/4 → post9 3/5 와 나란히).")
    say("- 🔴 **분모 정의** — post6 까지 「신규 전건」 · post7 부터 「신규 ∧ `exact`」(PD-4) · post9·post10 도 「신규 ∧ `exact`」.")
    say("- 🔴 **`F-5` 귀결 대상 종결 줄**: `REC-Y3` 귀결 문장 중 `HDR-D1` 적용 중단을 가리키는 부분 = *「귀결 대상 종결(`F-5`)」* · `Q1-R3` 적용 중단은 그대로 산다.")

    # ── §6. REC-Y4 ───────────────────────────────────────────────────────
    say()
    say("## §6. `REC-Y4`(기록만) — net 기준(정확 구간법) 해 개수 비교\n")
    say("| 종목 | gross 구간 개수 | gross 폭 | **net 구간 개수** | net P 범위 | net 총 측도(원) | net 폭 |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        ivn = v["iv_net"]
        gws = fmt_pct(v["w"])
        if ivn:
            nw = (iv_max(ivn) - iv_min(ivn)) / v["h0"] * 100
            say(f"| {nm} | {len(v['iv'])} | {gws} | **{len(ivn)}** | "
                f"{iv_min(ivn):,.2f}~{iv_max(ivn):,.2f} | {iv_measure(ivn):,.2f} | {nw:.2f}%p |")
        else:
            say(f"| {nm} | {len(v['iv'])} | {gws} | **0** | — | 0.00 | — |")
    _, y4ans, _, _ = a_y4(R)
    say()
    say(f"- ⇒ **{y4ans}**")

    # ── §7. REC-Z1 · Z2 ──────────────────────────────────────────────────
    say()
    say("## §7. `REC-Z1`(핵심) · `REC-Z2`(반증축)\n")
    z1_n = sum(1 for v in R.values() if v["under"])
    z1_frac = z1_n / len(R)
    say(f"- **`REC-Z1`**: `Δr_min` < `res` 인 건 **{pct(z1_n, len(R))}** · "
        f"문턱 **>= 1/3 = 33.3%** ⇒ **{'✅ 성립' if z1_frac >= 1 / 3 else '⛔ 불성립'}** · 최소 n 3 ⇒ "
        f"{'충족' if len(R) >= 3 else '미달'}({len(R)}) (계열 §17)")
    ga = [nm for nm, v in R.items() if v["under"]]
    gb = [nm for nm, v in R.items() if not v["under"]]
    ga_z = [nm for nm in ga if not R[nm]["iv"]]
    gb_z = [nm for nm in gb if not R[nm]["iv"]]
    say()
    say("| 부류 | 건수 | 해 0개 | 비율 | 건 |")
    say("|---|---|---|---|---|")
    say((f"| 격자 미달군(`Δr_min` < `res`) | {len(ga)} | **{len(ga_z)}** | "
         f"{(100 * len(ga_z) / len(ga)):.1f}% | {', '.join(ga)} |") if ga else
        "| 격자 미달군(`Δr_min` < `res`) | 0 | — | — | — |")
    say((f"| 격자 충족군(`Δr_min` >= `res` 또는 미정의) | {len(gb)} | **{len(gb_z)}** | "
         f"{(100 * len(gb_z) / len(gb)):.1f}% | {', '.join(gb)} |") if gb else
        "| 격자 충족군(`Δr_min` >= `res` 또는 미정의) | 0 | — | — | — |")
    say()
    say("- **`REC-Z2`**: 두 부류의 해 0개 비율을 나란히 인쇄했다 — " +
        ("🔴 **격자 충족군에서도 해 0개가 나온다** ⇒ 원인이 격자만은 아니다(평단 변화 후보 잔존)."
         if gb_z else "격자 충족군에서 해 0개 **0건** ⇒ 「원인은 격자」쪽과 모순되지 않는다.") +
        " (계열 §17)")
    if len(ga) == 1:
        say("- ⚠️ **격자 미달군이 1건뿐**이라 그 비율은 **분모 1** 이다. 비율로 읽지 말 것.")

    # ── §8. REC-Z3 앵커 ──────────────────────────────────────────────────
    say()
    say("## §8. `REC-Z3` — `H`(등록일 고가) < 창 최고가 인 건의 비율 (건별 인쇄 의무)\n")
    say("🔴 `H`·`L`·`HI` = `P8-빈티지`(D+1 안정 빈티지) · 창 `[D, END]` · 읽은 시각 = §0 ① · 창별 `max(updated_at)` = §0-b "
        "· 🔴 이 창은 **걸침 2 · 전부 경계 후 3**(§0-b).\n")
    say("| 종목 | `H` = 등록일 고가 | 창 최고가 `[D, 종료]` | 창 최저가 | **`H` < 창최고?** | 초과폭 | 경계 전/후 봉 |")
    say("|---|---|---|---|---|---|---|")
    z3_hit = []
    for nm, v in R.items():
        broken = v["h0"] < v["HI"]
        if broken:
            z3_hit.append(nm)
        over = f"{100 * (v['HI'] - v['h0']) / v['h0']:.2f}%" if broken else "—"
        wa = vint[nm][0]
        say(f"| {nm} | {v['h0']:,.0f} | {v['HI']:,.0f} | {v['L']:,.0f} | "
            f"{'🔴 **예**' if broken else '아니오'} | {over} | {wa['before']}/{wa['after']} |")
    z3_frac = len(z3_hit) / len(R)
    say()
    say(f"- **`REC-Z3` = {pct(len(z3_hit), len(R))}** "
        f"({', '.join(z3_hit) if z3_hit else '없음'}) · 문턱 **>= 1/2 = 50.0%** ⇒ "
        f"**{'🔴🔴 발동' if z3_frac >= 0.5 else '미발동'}** · 최소 n 3 ⇒ {'충족' if len(R) >= 3 else '미달'}({len(R)}) "
        "(계열 = 동결 인쇄값 post5 3/6 → post6 6/10 → post7 6/6 → post8 3/4 → post9 5/5 · 같은 스냅샷 재계산 §17)")
    if z3_frac >= 0.5:
        say("- ⇒ 🔴🔴 **앵커 붕괴가 «또» 재현됐다.** 앵커 재설계 사전등록은 post6 에서 이미 **의무 발생**했고 "
            "`PREREG_ANCHOR_REDESIGN.md`(동결 `ef17c4f`)로 이행됐다 ⇒ 후보 앵커 검정은 "
            "ANC 레인은 post10 에서 **종결**(`F-5` (ㄱ) · `--mode post10` 없음)이다 — 이 산출물은 후보 앵커를 계산하지 않는다.")
        say("- 🔴 `HDR-D1` = **종결(`F-5`) · 계산 0회** — #52 대칭 쌍(무효) 적용도 하지 않는다(§12).")
    else:
        say("- ⇒ 이번 회차 `REC-Z3` 미발동 — `HDR-D1` = 종결(`F-5`) · 계산 0회(§12).")
    gz = [nm for nm in R if win_line(vint[nm][0]) == "cross"]
    az = [nm for nm in R if win_line(vint[nm][0]) == "after"]
    say(f"- 🔴 **창 분류별 인쇄(판정 아님 · 새 분모 아님)**: `[D, END]` 걸침 {len(gz)}건 중 `H` < 창최고 "
        f"**{sum(1 for nm in gz if nm in z3_hit)}/{len(gz)}** · 전부 경계 후 {len(az)}건 중 "
        f"**{sum(1 for nm in az if nm in z3_hit)}/{len(az)}** — 🔴 `PREREG_POST8.md` §9 (다) 「이 조항이 틀렸다면」 행이 "
        "`REC-Z3` 을 이름으로 지목했으나 「계통적」 여부를 가르는 판정 규칙은 **동결돼 있지 않다**(PD-33 `:689` 후보 ⓖ · "
        "`PREREG_POST9.md` §7 18번 이월) ⇒ 분모를 쪼개 판정하지 않는다(값만).")
    say("- 🔴 **`REC-Z3` 제도 경계 분리 조항 없음**(결정 ⑤ · 기록 보존 · `F-5` (나)5) — 이 산출물은 제도 경계 분모 분리를 만들지 않는다.")
    say("- 🔑 `h = (S-L)/(H-L)` 는 `H` 가 천장일 때만 「저점 대비 반등폭 비율」이다 — "
        "천장이 뚫린 건에서는 `h_max` 가 1 을 넘고 HDR 틀 자체가 성립하지 않는다.")

    # ── §9. REC-Z4 ───────────────────────────────────────────────────────
    say()
    say("## §9. `REC-Z4` — `first_only` ∧ 서로 «다른» 값 레그 >= 3 · 🔴 **관측 인쇄만**\n")
    say("🔴🔴 **이 항목은 «판정하지 않는다».** 동결 문언의 귀결(= 그 자리에서 `BUY-` 계열을 연다)은 "
        "🔒 **결정 ④「`PREREG_BUYLADDER` 계열 종결·기록 보존」**(`PREREG_GRADE_TIERS.md` §5 · 동결 "
        "`342f6f0`)으로 **소멸**했다(PD-13). **조건 충족 사실과 건수만 인쇄한다.**\n")
    say("| 종목 | 정밀도 | first_only | 레그 | 레그 수 | 서로 다른 값 개수 | 관행(서로 다른 값 ≥3) | 「정확히 3레그」 |")
    say("|---|---|---|---|---|---|---|---|")
    z4, z4x3 = [], []
    for nm, v in R.items():
        d = len(set(v["legs"]))
        if v["fo"] and d >= 3:
            z4.append(nm)
        if v["fo"] and len(v["legs"]) == 3:
            z4x3.append(nm)
        say(f"| {nm} | exact | {'예' if v['fo'] else '아니오(' + str(v['tr']) + '차)'} | {v['legs']} | {len(v['legs'])} | "
            f"**{d}** | {'🟢 **충족**' if (v['fo'] and d >= 3) else '아니오'} | "
            f"{'충족' if (v['fo'] and len(v['legs']) == 3) else '아니오'} |")
    fo_new = [nm for nm, v in R.items() if v["fo"]]
    say()
    say(f"- **`REC-Z4` 조건 충족(관측)**: 계수 관행(post8 PD-13 · `first_only` ∧ 서로 다른 값 레그 ≥3) **{len(z4)}건** "
        f"({', '.join(z4) if z4 else '없음'}) · 동결 문언 「first_only 3레그」(`PREREG_POST6.md:836` · PD-13 T6)를 "
        f"「정확히 3레그」로 읽으면 **{len(z4x3)}건** — 🔴 **판정 없음**(결정 ④) · 등급 이름을 미리 고르지 않는다(PD-16).")
    say(f"- `first_only` **`exact` {len(fo_new)}건** ({', '.join(fo_new)}) · `approx` 0.")
    say("- 🔴 **충돌 신고(§1-8 형식 · post7·post8 승계)**: `REC-Z4` 동결 문언 ↔ 결정 ④. **사장님 결정이 이긴다** — "
        "`PREREG_ANCHOR_REDESIGN.md` §5-2 가 *「④가 「종결」로 결정되면 `BUY-L5` 재개 조항은 **자동 소멸**한다」*고 "
        "**미리** 적어 두었고, 그 뒤 `342f6f0` 이 결정을 기록했다.")

    # ── §10. BUY 계열 종결 ───────────────────────────────────────────────
    say()
    say("## §10. 🔒 `PREREG_BUYLADDER` 계열 — **종결 · 기록 보존** (결정 ④ · 계산 0회)\n")
    say("| 항목 | 지위 | 이번 회차 처리 |")
    say("|---|---|---|")
    for lab in CLOSED_BY_DECISION4:
        say(f"| {lab} | 🔒 **종결**(결정 ④ · `342f6f0`) | **재개하지 않는다 · 계산 0회 · 기록 보존** |")
    say()
    say(f"- 🔴 **귀무 상수는 남겨 두되 돌리지 않았다** — `SEED` = **{SEED}** · `NREP` = **{NREP:,}** "
        "는 `P6-L1'-N`(죽은 가드 방지 장치)의 상수다. **축이 닫혀서** 안 돌린 것이지 시드를 바꾼 것이 아니다.")
    say("- `HDR-D2`/`BUY-L4`(#50): 〔HDR-D2〕 = 종결(`F-5` · 계산 0회) · `BUY-L4` 🔒 종결.")

    # ── §17 을 먼저 계산(§11 참조값 · 계열) ──────────────────────────────
    post_sets = [
        ("post4", [(t[0], t[1], t[2], t[3], t[4], t[5], "—", "—", False) for t in P4M.TARGETS]),
        ("post5", [(t[0], t[1], t[2], P5M.END, t[3], t[4], t[5], t[6], t[7]) for t in P5M.TARGETS]),
        ("post6", [(t[0], t[1], t[2], P6M.END, t[3], t[4], t[5], t[6], t[7]) for t in P6M.TARGETS]),
        ("post7", [(t[NM], t[CODE], t[D0], P7M.END, t[LEGS], t[TR], t[PRESET], t[LABEL], t[FO])
                   for t in P7M.TARGETS if t[PREC] == "exact"]),
        ("post8", [(t[NM], t[CODE], t[D0], P8.END, t[LEGS], t[TR], t[PRESET], t[LABEL], t[FO])
                   for t in P8.TARGETS if t[PREC] == "exact"]),
        ("post9", [(t[NM], t[CODE], t[D0], P9.END, t[LEGS], t[TR], t[PRESET], t[LABEL], t[FO])
                   for t in P9.TARGETS if t[PREC] == "exact"]),
    ]
    SR = {}
    for tag, items in post_sets:
        Rp = {}
        umax = None
        for nm, code, d0, d1, legs, tr, preset, label, fo in items:
            v = core(cur, code, d0, d1, legs)
            if v is None:
                continue
            v.update(tr=tr, preset=preset, label=label, fo=fo)
            Rp[nm] = v
            w = win_stats(cur, code, d0, d1)
            umax = w["umax"] if umax is None or w["umax"] > umax else umax
        SR[tag] = (Rp, umax)
    ref_post9 = [(f"post9 {nm}", v["b1"]) for nm, v in SR["post9"][0].items() if v["fo"] and v["iv"]]
    ref_old = [(f"post8 {nm}", v["b1"]) for nm, v in SR["post8"][0].items() if v["fo"] and v["iv"]]
    ref_old += [(f"post7 {nm}", v["b1"]) for nm, v in SR["post7"][0].items() if v["fo"] and v["iv"]]
    for tag, nm in (("post6", "아난티"), ("post5", "삼양바이오팜")):
        v = SR[tag][0].get(nm)
        if v is not None and v["iv"]:
            ref_old.append((f"{tag} {nm}", v["b1"]))

    # ── §11. Q1-R3 ───────────────────────────────────────────────────────
    say()
    say("## §11. `Q1-R3` — `b1` 구간이 직전 글 값과 부호·자릿수가 같은가 (구간 겹침 여부만)\n")
    say("A-6: 다차수 건의 `1-P/H` 는 「1차 밴드」가 아니라 「전 차수 평단」이다 ⇒ **범주 오류**(post4 §2 유지). "
        + ("`REC-Y3` 중단도 다차수 건에 겹친다. " if frac >= 1 / 3 else "") +
        "🔴 직전 글(post9)·그 전 참조값은 **같은 스냅샷에서 재계산**했다(§17 · 옮겨 적기 아님) · post8 우리로 = `구조차단`"
        "(post8 🔒 #1 · 참조 표에서도 표시) · 샌즈랩 = 이번 글 `구조차단`(🔒 #1 ⓐ) 이나 `fill_n` 3 이라 `first_only` 아님.\n")
    say("| 건 | 구분 | `b1` 구간 | 부호 | 자릿수(정수부) | 플래그 |")
    say("|---|---|---|---|---|---|")
    r3 = []
    for nm in fo_new:
        v = R[nm]
        if not v["iv"]:
            say(f"| {nm} | `first_only`(post10 `exact`) | ⛔ 해 0개 | — | — | — |")
            continue
        r3.append(nm)
        lo_b, hi_b = v["b1"]
        sg = sign_of(v["b1"])
        say(f"| {nm} | `first_only`(post10 `exact`) | **[{lo_b:+.2f}%, {hi_b:+.2f}%]** | "
            f"{'🔴 **부호 걸침**' if sg == '걸침' else sg} | {len(str(int(abs(hi_b))))} 자리 | — |")
    for lab, b in ref_post9 + ref_old:
        fl = "🔴 `구조차단`(post8)" if lab == "post8 우리로" else "—"
        say(f"| _{lab}_ | _`first_only`(같은 스냅샷 재계산)_ | _[{b[0]:+.2f}%, {b[1]:+.2f}%]_ | _{sign_of(b)}_ | "
            f"_{len(str(int(abs(b[1]))))} 자리_ | {fl} |")
    say(f"| 솔트룩스(인용) | `first_only` | [{QUOTED_SOLTLUX[0]:+.2f}%, {QUOTED_SOLTLUX[1]:+.2f}%] | 걸침 | 1 자리 | "
        "인용 — `RESULTS_RECONSTRUCT_POST7_NUMBERS.md:216`(표본 밖 · 점법 시대 값 · 재계산 안 함) |")
    say("| 케이엔알(인용) | `full` | `b_last` <= +36.76% | 양 | 2 자리 | 인용 — `RESULTS_RECONSTRUCT_POST7_NUMBERS.md:217` |")
    say()
    say(f"- 최소 n **3**(`PREREG_POST6.md` §4 #54) — 두 읽기: `first_only` **건수 {len(fo_new)}**"
        f"(⇒ {'충족' if len(fo_new) >= 3 else '미달'}) vs **측정 가능 {len(r3)}건**(⇒ {'충족' if len(r3) >= 3 else '미달'}) · "
        "🔴 ⛔ 조건 ②의 단위는 `PREREG_POST6.md:743-746`(2026-09-10 B-2)이 **「건」 단위로 못박았다** — "
        "측정 가능 읽기가 그 단위 규약의 귀결이다(건수 읽기는 병기).")
    if r3:
        for lab, b in ref_post9 + ref_old + [("솔트룩스(인용)", QUOTED_SOLTLUX)]:
            ov = sum(1 for nm in r3 if overlap(R[nm]["b1"], b))
            say(f"  - 구간 겹침: {lab} `[{b[0]:+.2f}, {b[1]:+.2f}]` 과 **{ov}/{len(r3)}**")
        say("- 부호·자릿수: " + ", ".join(
            f"{nm} {sign_of(R[nm]['b1'])}/{len(str(int(abs(R[nm]['b1'][1]))))} 자리({R[nm]['b1'][1]:+.2f}%)"
            for nm in r3))
    if len(r3) >= 3:
        say("- ⇒ 🟡 **`Q1-R3` = 겹침 여부 «기록»**(`PREREG_Q1_V2.md` §3 판정 규칙 = "
            "*「R3 은 구간 겹침 여부만」* — 지지/기각을 선언하는 항목이 아니다).")
    else:
        say(f"- ⇒ ⛔ **`Q1-R3` 판정 불가**(측정 가능 읽기 · 건 단위) — `first_only` **측정 가능 {len(r3)} < 3**. "
            "🟡 「건수 읽기」를 택하면 위 겹침 값이 R3 의 «기록»이 된다 — "
            "🔴 어느 쪽이든 **R3 은 지지/기각을 선언하는 항목이 아니라** 결론은 같다.")


    # ── §12. HDR-D1 (종결) ───────────────────────────────────────────────
    say()
    say("## §12. `HDR-D1` — 🔒 **종결 · 계산 0회** (`F-5` · `P10-앵커종결` (나)2 (가))\n")
    say("해당 없음 — 🔒 종결(2026-10-01 폐기 접수 · `PREREG_ANCHOR_REDESIGN.md:253` · 기록 보존) — 핵심 수: 계산 0회")
    say()
    say("- 🔴 `h_max`·`L`·중점·중앙값을 계산하지 않았다(판정용 계산 생략 · 종결 5항목 · 기록 보존). 판정 낱말 없음.")
    say("- `REC-Y3` 의 `HDR-D1` 적용 중단 부분 = 귀결 대상 종결(`F-5`) · `Q1-R3` 적용 중단은 산다 · `REC-Z3` 제도 경계 분리 조항 없음(결정 ⑤).")

    # ── §13. P6-R1' ──────────────────────────────────────────────────────
    say()
    say("## §13. `P6-R1'` — `first_only` DD < `full` DD (누적 · 양쪽 각 n >= 2)\n")
    say("`H4`=max(high) over `[D-4,D]` · `H5`=`[D-9,D]` · `H6`=`[D-19,D]` · "
        "`DD` = 1 - min(low over `[D, 종료]`) / H · 🔴 `H6` 창 = `[D−19, D]`(§0-b) · `L` 창 = `[D, END]`\n")
    say("| 건 | 구분 | 등록일 | 종료 | `DD(H4)` | `DD(H5)` | `DD(H6)` | `[D−19, D]` 분류 |")
    say("|---|---|---|---|---|---|---|---|")
    fo_dd = []
    for nm in fo_new:
        v = R[nm]
        row = [dd_h(cur, v["code"], v["d0"], END, k) for k in (5, 10, 20)]
        fo_dd.append((nm, row))
        k = win_line(vint[nm][1])
        say(f"| {nm} | `first_only`(신규 `exact`) | {v['d0']} | {END} | "
            f"{row[0]:.2f}% | {row[1]:.2f}% | {row[2]:.2f}% | "
            f"{dict(cross='🔴 걸침', after='전부 경계 후', before='전부 경계 전')[k]} |")
    knr = [dd_h(cur, "199430", "2026-07-28", "2026-08-14", k) for k in (5, 10, 20)]
    say(f"| 케이엔알시스템 | `full`(누적 · 직전 글들) | 2026-07-28 | 2026-08-14 | "
        f"{knr[0]:.2f}% | {knr[1]:.2f}% | {knr[2]:.2f}% | — |")
    say()
    say("- 🔴 **이번 글 신규 `full` = 0건**(PD-13 `:341` *「`full` 신규 **0**(「전 차수 체결」 서술 0 · 서산 「5차」·라온 「4차」도 사다리 전 "
        "차수인지 원문에 없다) ⇒ 관측만」*)")
    say(f"- 누적 n: `first_only` **{len(fo_dd)}**(신규 `exact`) · `full` **1**(케이엔알)")
    say("- 문턱 **양쪽 각 n >= 2**(`PREREG_POST6.md` §3-3) ⇒ `full` 1 < 2 ⇒ ⛔ **판정 안 함 · 관측만.**")
    dirn = sum(1 for _, row in fo_dd for a, b in zip(row, knr) if a < b)
    say(f"- (관측) 방향 일치(`first_only` DD < `full` DD) **{dirn}/{len(fo_dd) * 3}** — 신규 `exact` {len(fo_dd)}건 × 세 H 정의.")
    say(f"- 🟢 케이엔알 재계산 **{knr[0]:.2f}%** — 동결값 **36.76%** 와 "
        f"{'일치' if f'{knr[0]:.2f}' == '36.76' else '🔴 **불일치**'}(계기 점검).")
    say("- 🔴 `F-3`: `[D−19, D]` 기업행위 건 제외 값은 §14 끝 — `H6` 표는 건 단위로 빼지 않는다(인쇄만).")

    # ── §14. 갈래 (D-5) ──────────────────────────────────────────────────
    say()
    say("## §14. `D-5` `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (PD-23 `REC-` 갈래 전부 · 항등 포함)\n")
    say("규칙(`PREREG_POST8.md:337-342`): **최소 n 은 그 축의 동결문 값 그대로**(`PREREG_POST6.md` §4 #38~#54) · "
        "최소 n 미달 갈래는 **인쇄 의무 · 「갈렸다」의 근거로 쓰지 않는다** · 채운 갈래가 **2 이상이고 답이 갈리면** "
        "`:340` 「갈렸다」 · **1개면 그 답** · **0개면** `:341` · 동결문에 최소 n 이 **없는** 항목은 계수 대상 밖(`:338`). "
        "🔴 등급 칸은 §6 단계.\n")
    trunc = set()
    for nm, v in R.items():
        _s19, n19 = d19_start(cur, v["code"], v["d0"])
        n5, _ = win5_count(cur, v["code"], v["d0"], END)
        v["n19"], v["n5"] = n19, n5
        if n19 < 20:          # `REC-` 절단 = `[D−19, D]` 봉수 < 20 만(INTAKE §5 · 창5 절단 1(뷰노)은 `LAD-` 몫 · 아래 인쇄)
            trunc.add(nm)
    reent_ex = {nm for nm, v in R.items() if v["reent"]}
    t5set = {nm for nm, v in R.items() if v["n5"] < 5}
    B = [
        (f"주(`exact` {len(R)})", dict(R)),
        (f"§1-5 재진입 제외(exact {len(reent_ex)}건 ⇒ {'항등' if not reent_ex else '제외 · 🔴 항등 아님'})",
         {k: v for k, v in R.items() if k not in reent_ex}),
        (f"「샌즈 제외」(`WRC-R5` 구조차단 · 🔒 #1 ⓐ · 1건 ⇒ 제외)",
         {k: v for k, v in R.items() if k != SANDS}),
        (f"절단 제외(`[D−19,D]`<20 · {len(trunc)}건 ⇒ {'항등' if not trunc else '제외'})",
         {k: v for k, v in R.items() if k not in trunc}),
    ]
    refs_q = ref_post9
    ITEMS = [
        ("`REC-Y1`", "레그≥4 3건(#38)", lambda S: a_y1(S)),
        ("`REC-Y2`", "좁은 건 ≥1(#39)", lambda S: a_y2(S)),
        ("`REC-Y3`", "—(#40 · 계수 대상 밖)", lambda S: a_y3(S)),
        ("`REC-Y4`", "—(#41 · 기록)", lambda S: a_y4(S)),
        ("`REC-Z1`", "3(#42)", lambda S: a_z1(S)),
        ("`REC-Z2`", "3(#43)", lambda S: a_z2(S)),
        ("`REC-Z3`", "3(#44)", lambda S: a_z3(S)),
        ("`REC-Z4`", "—(#45 · 관측)", lambda S: a_z4(S)),
        ("`Q1-R3`(측정 가능 읽기)", "3(#54)", lambda S: a_q1r3(S, refs_q, "측정 가능")),
        ("`Q1-R3`(건수 읽기)", "3(#54)", lambda S: a_q1r3(S, refs_q, "건수")),
        ("`P6-R1'`", "양쪽 각 2(#53)", lambda S: a_r1(S)),
    ]
    NO_VERDICT = {"`REC-Y4`", "`REC-Z4`"}
    say("| 항목 | 최소 n(동결문) | 갈래 | n | 답 | 최소 n 충족? |")
    say("|---|---|---|---|---|---|")
    summary = []
    for lab, mn, fn in ITEMS:
        res = []
        for bname, S in B:
            n, ans, meets, cat = fn(S)
            res.append((bname, n, ans, meets, cat))
            say(f"| {lab} | {mn} | {bname} | {n} | {ans} | "
                f"{'— (대상 밖)' if meets is None else ('✅' if meets else '❌ 미달')} |")
        summary.append((lab, mn, res))
    say()
    say("**계수 결과**(항등 갈래는 주와 같은 답으로 센다 · `approx` 갈래 없음)\n")
    say("| 항목 | 최소 n 충족 갈래 수 | 충족 갈래의 답 | `P8-갈래계수`(「샌즈 제외」 계수 읽기 · 주) | `P8-갈래계수`(「샌즈 제외」 인쇄만 읽기 · 대조) | 주 ↔ §1-5 재진입 제외 | §1-5 「재진입 의존」 | 주 ↔ 「샌즈 제외」 | 「샌즈 의존」(구조차단) |")
    say("|---|---|---|---|---|---|---|---|---|")
    split_items, re_items, sands_items, alt_split = [], [], [], []
    for lab, mn, res in summary:
        q = [r for r in res if r[3]]
        qa = sorted(set(r[4] for r in q))
        gc, is_split = gc_status(res)
        if is_split:
            split_items.append(lab)
        res_alt = [res[0], res[1], res[3]]     # 「샌즈 제외」 를 계수에서 뺀 읽기(인쇄만)
        gc_alt, is_split_alt = gc_status(res_alt)
        if is_split_alt:
            alt_split.append(lab)
        re_dep, is_re = re_dep_status(res[:2], lab not in NO_VERDICT)
        if is_re:
            re_items.append(lab)
        sd, is_sd = re_dep_status([res[0], res[2]], lab not in NO_VERDICT)
        if is_sd:
            sands_items.append(lab)
        say(f"| {lab} | {len(q)} | {' · '.join(qa) if qa else '—'} | {gc} | {gc_alt} | {res[0][4]} ↔ {res[1][4]} | {re_dep} | "
            f"{res[0][4]} ↔ {res[2][4]} | {sd} |")
    say()
    say(f"- 🔴 **「갈렸다」 항목: {len(split_items)}개** ({', '.join(split_items) if split_items else '없음'}) — "
        "등급은 §6 단계에서 그 축 문언대로(PD-16).")
    say(f"- 🔴 **「갈렸다」 항목(「샌즈 제외」 계수 읽기 · 주): {len(split_items)}개** ({', '.join(split_items) if split_items else '없음'}) — "
        f"「샌즈 제외」 인쇄만 읽기: **{len(alt_split)}개**({', '.join(alt_split) if alt_split else '없음'}) — 등급은 §6 단계에서 그 축 문언대로(PD-16).")
    say(f"- 🔴 **§1-5 「재진입 의존」 항목: {len(re_items)}개** ({', '.join(re_items) if re_items else '없음'}) — "
        f"재진입 제외 갈래 = **{'항등' if not reent_ex else '제외 있음 · 🔴 항등 아님'}**(exact 안 재진입 {len(reent_ex)}: {', '.join(sorted(reent_ex))} · 9 ↔ {len(R) - len(reent_ex)} · PD-3) · "
        f"절단 제외 갈래(`[D−19,D]`<20) = **{'항등' if not trunc else '제외 있음'}**({len(trunc)}건) — **항등을 명시 인쇄**한다.")
    say(f"- 🔴 **「샌즈 의존」(`WRC-R5` 구조차단) 항목: {len(sands_items)}개** ({', '.join(sands_items) if sands_items else '없음'}) — "
        "`REC-` 에서는 판정 낱말이 아니라 값 병기(갈리면 ⛔ 는 `WRC-V1` 몫).")
    say(f"- 🔴 창5 절단(`n5 < 5`) 건 = {len(t5set)}({', '.join(sorted(t5set)) if t5set else '없음'}) — **`LAD-` 의 창5 절단 제외 갈래 몫**이며 `REC-` 절단 갈래에는 넣지 않았다"
        "(INTAKE §5 `REC-` = `[D−19, D]` 절단 0 · 항등).")
    say(f"- 🔴 `P6-PRIOR_CYCLE_IN_WINDOW` = **{len(reent_ex)}/{len(R)}**(PD-3 표 · `P6-M1′`·`Q1-R2` 산출물 의무 인쇄 — 참고 줄) · {REREG_NOTE}.")
    say()
    say(f"**🆕 `F-3` 「기업행위 건 제외」 갈래 값(의무 인쇄 · 🔴 `P8-갈래계수` 갈래 «아님» · 답 칸 낱말 = 「답(참고) · 세지 않는다」 · 판정 불변)**\n")
    say("| 항목 | 갈래 이름 | n | 답 |")
    say("|---|---|---|---|")
    S_ex = {k: v for k, v in R.items() if k not in CORP_SET}
    for lab, mn, fn in ITEMS:
        n, ans, meets, cat = fn(S_ex)
        say(f"| {lab} | 기업행위 건 제외(k={k_corp}) | {n} | 답(참고) · 세지 않는다 — _{raw_key(lab, S_ex, n, ans, cat)}_ |")
    say()
    say(f"- 「기업행위 건 제외」 계수(인쇄만 · 판정 언어 없음): 해 0개 "
        f"**{sum(1 for v in S_ex.values() if not v['iv'])}/{len(S_ex)}** · 격자 미달 "
        f"**{sum(1 for v in S_ex.values() if v['under'])}/{len(S_ex)}** · `H` < 창최고 "
        f"**{sum(1 for v in S_ex.values() if v['h0'] < v['HI'])}/{len(S_ex)}** · 레그≥4 "
        f"**{sum(1 for v in S_ex.values() if len(v['legs']) >= 4)}** — k = {k_corp} ⇒ "
        f"{'주 갈래와 같은 집합(항등)' if not k_corp else '제외 있음'} · **계수하지 않는다**(`F-3` (나) · `P8-갈래계수` 밖).")

    # ── §15. D-3 · P9-공통독법 ───────────────────────────────────────────
    say()
    say("## §15. `D-3` `P8-approx의존신고` (`PREREG_POST8.md:249` · 기계 검사 `:253`) · 🆕 `P9-공통독법`(`PREREG_POST9.md` §1)\n")
    rows_d3 = []
    for lab, mn, fn in ITEMS:
        mnv = {"`REC-Y1`": 3, "`REC-Z1`": 3, "`REC-Z2`": 3, "`REC-Z3`": 3, "`Q1-R3`(측정 가능 읽기)": 3,
               "`Q1-R3`(건수 읽기)": 3}.get(lab)
        if mnv is None:
            continue
        ne = fn(R)[0]
        ni = ne      # `approx` 0 ⇒ 포함 분모 = exact 분모(조합 없음)
        rows_d3.append((lab, mnv, ne, ni, d3_hit(mnv, ne, ni)))
    hit_axes = [r[0] for r in rows_d3 if r[4]]
    say(f"**「`approx` 포함 시 최소 n 이 차는 축: {', '.join(hit_axes) if hit_axes else '없음'} · "
        f"`exact` 분모 {y1n} / `approx` 포함 분모 {y1n}」**(`REC-Y1` · PD-21 표 행 `PREDECISION_2026-10-04_post10.md` PD-21)\n")
    say("| 항목 | 최소 n | `n_exact` | `n_incl` | `n_incl ≥ 최소 n > n_exact`? |")
    say("|---|---|---|---|---|")
    for lab, mnv, ne, ni, hit in rows_d3:
        say(f"| {lab} | {mnv} | {ne} | {ni} | {'🔴 **예** ⇒ 열지 않는다' if hit else '아니오'} |")
    say()
    say("- 🔴 **기계 검사 결과**: `n_incl ≥ 최소 n > n_exact` 인 항목 **" + (", ".join(hit_axes) if hit_axes else "0개") +
        "** ⇒ " + ("그 항목은 `approx` 로만 열리므로 **열지 않는다**(`:250`)." if hit_axes else
                   "신고 대상 없음 — 구성 예고(PD-21 「없음」)와 같다.") +
        " `approx` **0건**이라 전 항목 `n_incl = n_exact` · `REC-Y4`·`REC-Y3`·`REC-Z4`·`P6-R1'` 는 동결 최소 n 이 없거나(—) "
        "`full` 축이라 표 밖.")
    say("- 🔴 **`D-3` (나)4 검사**(`PREREG_POST8.md:250`): `approx` 포함 갈래가 **없다** ⇒ 대상 없음 · 판정 이동 0.")
    say("- 🆕 **`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)** — `PREREG_POST9.md` §1 (나)3 신고 줄 · "
        "독법 B(표본 수준 문턱 비교) 병기 대상 없음(갈래가 없어 두 독법이 가를 자리 0 · `:112`).")

    # ── §16. 봉수 정합 · 절단 가드 ───────────────────────────────────────
    say()
    say("## §16. 봉수 표기 정합 (N8 승계 — «직전/포함»을 반드시 붙인다) · 절단 가드\n")
    say("| 종목 | 등록일 | DB 최초 봉 | 등록일 «직전» 봉수(σ₂₀ 용 · 최대 21) | 등록일 «포함» 봉수 | "
        f"창 `[D, {END}]` 봉수 | `[D-19, D]` 봉수(등록일 포함) | 창 `[D-19, D+4]` 봉수 | 창5 `[D, D+4]` |")
    say("|---|---|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        cur.execute("SELECT min(date), count(*) FROM daily_prices WHERE stock_code=%s "
                    "AND date <= %s", (v["code"], v["d0"]))
        mn, inc = cur.fetchone()
        _s, n = sigma20(cur, v["code"], v["d0"])
        wbn = len(win_bars(cur, v["code"], v["d0"], 19, 4))
        say(f"| {nm} | {v['d0']} | {mn} | {n} | {inc} | {v['nbars']} | {v['n19']}/20 | {wbn} | "
            f"{'완전' if v['n5'] >= 5 else '🔴 **' + str(v['n5']) + '봉 = 절단**'} |")
    t19 = sum(1 for v in R.values() if v["n19"] < 20)
    t5 = sum(1 for v in R.values() if v["n5"] < 5)
    say()
    say(f"- 🔴 **`P6-절단가드-A`**(창 `[D-19, D]` 봉수 < 20) 분자 = **{t19}** ⇒ **{pct(t19, len(R))} "
        f"{'≥' if t19 / len(R) >= 1 / 3 else '<'} 1/3 ⇒ {'🔴 발동' if t19 / len(R) >= 1 / 3 else '미발동'}**(산술 인쇄 · PD-12).")
    say(f"- 🔴 **`P6-창5절단가드-A`**(창5 절단 건 / 이번 글 신규 건) = 주 분모 **{t5}/{len(R)}** · `exact` 갈래 **{t5}/{len(R)}** "
        f"⇒ {'둘 다 < 1/3 ⇒ **미발동 · 분모 갈래: 갈리지 않음**' if t5 / len(R) < 1 / 3 else '🔴 발동'}(PD-25 · `approx` 0 ⇒ 두 분모 같다) — "
        "🔴 이 가드는 `LAD-` 축 값이며 이 산출물 판정에 들어가지 않는다 · 2회 연속 계수는 `LAD-` 레인(`D-7`).")
    say(f"- 🔴 **혼동 방지**: `REC-` 축의 판정 창은 `[등록일, {END}]` **전체**라 **절단 개념이 다르다** — "
        "창5 열은 `LAD-`·`ANC-` 축이 쓰는 값이다.")
    say(f"- 🔴 `F-3`: `[D−19, D]` 봉수는 위 표 값 그대로(기업행위 건 {k_corp}/{len(R)} · `adj_factor` 산술 0 · 판정 규칙 불변).")

    # ── §17. post4~8 같은 스냅샷 재계산 ──────────────────────────────────
    say()
    say("## §17. 누적 계열 — post4~9 표본을 **같은 스냅샷에서 재계산** · 동결 인쇄값은 대조 열\n")
    say("🔴 **판정은 각 글의 동결 판정 그대로다** — 이 표는 소급 재판정이 아니라 **같은 잣대·같은 스냅샷의 계열**이다. "
        "창·대상·레그 = 각 글 스크립트의 동결 상수(`run_reconstruct_post4/5/6/7/8.py` `TARGETS`·`END` · post4 는 건별 종료일 · "
        "post7~9 는 `exact`).\n")
    say("| 글 | 창 종료 | 분모 | `REC-Y3` 재계산 | 동결 | `REC-Y4` net 재계산 | 동결 | `REC-Z1` 재계산 | 동결 | "
        "`REC-Z3` 재계산 | 동결 | 창 `max(updated_at)` |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|")

    def cmp(val, froz):
        if froz is None:
            return "—(당시 미정의)"
        return f"{froz} {'✅' if val == froz else '🔴 **다름**'}"

    def cnt(Rp):
        return (len(Rp), sum(1 for v in Rp.values() if not v["iv"]), sum(1 for v in Rp.values() if not v["iv_net"]),
                sum(1 for v in Rp.values() if v["under"]), sum(1 for v in Rp.values() if v["h0"] < v["HI"]))

    endv = {"post4": "건별(08-21)", "post5": P5M.END, "post6": P6M.END, "post7": P7M.END, "post8": P8.END, "post9": P9.END}
    for tag, (Rp, umax) in SR.items():
        n, e, en, z1, z3 = cnt(Rp)
        fz = FROZEN[tag]
        say(f"| {tag} | {endv[tag]} | {n} | **{e}/{n}** | {cmp(f'{e}/{n}', fz['y3'])} | {en}/{n} | "
            f"{cmp(f'{en}/{n}', fz['y4n'])} | {z1}/{n} | {cmp(f'{z1}/{n}', fz['z1'])} | "
            f"**{z3}/{n}** | {cmp(f'{z3}/{n}', fz['z3'])} | {umax} |")
    Rx8 = {k: v for k, v in SR["post8"][0].items() if k not in P8.STRUCT_BLOCK}
    n, e, en, z1, z3 = cnt(Rx8)
    say(f"| _post8 「우리로 제외」(인쇄만 · 확인 7 문형)_ | {P8.END} | {n} | _{e}/{n}_ | — | _{en}/{n}_ | — | _{z1}/{n}_ | — | "
        f"_{z3}/{n}_ | — | — |")
    n, e, en, z1, z3 = cnt(R)
    say(f"| **post10** | {END} | {n} | **{e}/{n}** | (이 문서) | {en}/{n} | (이 문서) | {z1}/{n} | (이 문서) | "
        f"**{z3}/{n}** | (이 문서) | {max(vint[nm][0]['umax'] for nm in R)} |")
    Rs10 = {k: v for k, v in R.items() if k != SANDS}
    n_, e_, en_, z1_, z3_ = cnt(Rs10)
    say(f"| _post10 「샌즈 제외」(인쇄만)_ | {END} | {n_} | _{e_}/{n_}_ | — | _{en_}/{n_}_ | — | _{z1_}/{n_}_ | — | _{z3_}/{n_}_ | — | — |")
    say()
    for tag, (Rp, _u) in SR.items():
        say(f"- {tag} 건별 — 해 0개: " + (", ".join(nm for nm, v in Rp.items() if not v["iv"]) or "없음") +
            " · 격자 미달: " + (", ".join(nm for nm, v in Rp.items() if v["under"]) or "없음") +
            " · `H` < 창최고: " + (", ".join(nm for nm, v in Rp.items() if v["h0"] < v["HI"]) or "없음"))
    say("- 동결 인쇄값 출처: " + " · ".join(f"{k}: {v['src']}" for k, v in FROZEN.items()))
    say("- 🔴 **「다름」이 있으면** 원인은 DB 스냅샷 이동(백필·재기록)이거나 잣대 차이다 — **맞추지 않는다**(계열 규칙: "
        "*숫자가 문서마다 다르면 «원인 규명»이 먼저다*). 동결 판정은 그대로 둔다.")
    say("- 🔴 **분모 정의가 글마다 다르다** — post4~6 「신규 전건」(= `exact`) · post7~10 「신규 ∧ `exact`」(PD-4).")
    say("- 🔴 **제도 경계**: post4~7 창은 전부 09-14 «전» · post8 창은 «걸침» · post9·post10 창은 «걸침»(§0-b) — "
        "***이 계열은 두 제도를 섞는다***(`PREREG_POST8.md` §14 · 분모를 쪼개지 않는다 — 쪼개려면 새 사전등록).")

    # ── §18. 처음 정한 문턱 · 모호 지점 · 충돌 ───────────────────────────
    say()
    say("## §18. 「처음 정한 문턱」에 걸렸나 · 모호 지점 · 충돌 신고\n")
    say("| 문턱 | 출처 | 이번 글에서 «걸렸나» |")
    say("|---|---|---|")
    say("| **n >= 2** (`P6-R1'` 양쪽 각) | `PREREG_POST6.md` §3-3 | "
        "🔴 **걸렸다** — `full` 누적 1건이라 이 문턱 «때문에» 판정을 안 한다(5글 연속) |")
    say("| `REC-Z5` **0.022** 판정 / 0.020 민감도 | `PREREG_EXIT_V2.md` §2 · `PREREG_POST6.md` §1-7 | "
        + (f"🔴 **걸렸다** — 두 문턱이 {len(split)}건에서 분류를 가른다(「문턱 민감」)"
           if split else "**안 걸렸다** — 두 문턱에서 분류 동일") + " |")
    say("| 최소 n **3** (`REC-Y1`) | `PREREG_POST6.md` §4 #38 | "
        + ("**안 걸렸다**" if y1n >= 3 else f"🔴 **걸렸다** — `exact` 레그>=4 가 {y1n} < 3 (`approx` 0 · 후속은 축 밖)") + " |")
    say("| **`frac_in` 0.5** · **A-7 0.25·과반** | `PREREG_POST6.md` §3-4·§3-5 | "
        "🔒 **해당 없음** — 결정 ④로 그 축들이 종결됐다(계산 0회) |")
    say()
    say("### 모호 지점 · 충돌 신고 (양쪽 인쇄 · 어느 쪽도 규칙으로 고르지 않는다)\n")

    cd_ = [nm for nm, (wa_, wb_) in vint.items() if win_line(wb_) == "cross"]
    ca_ = [nm for nm, (wa_, wb_) in vint.items() if win_line(wa_) == "cross"]
    say("1. 🔴🔴 **`REC-` 창이 두 문서에서 다르다**(§1-8 형식 · post8 정오표 ③ · `PREREG_POST9.md` §7 10번 이월) — "
        "`PREREG_POST8.md:546` `[D−19, D]` ↔ `PREREG_ANCHOR_REDESIGN.md:115-124` `[D, END]`. **읽기**: 두 창 다 인쇄(§0-b). "
        f"이번 걸침: `[D, END]` = {', '.join(ca_) if ca_ else '없음'} · `[D−19, D]` = {', '.join(cd_) if cd_ else '없음'} — 발동 여부 판정에 "
        "쓰는 창은 여전히 정하지 않는다(신고 의무는 둘 다 인쇄로 이행).")
    say("2. 🔴 **`D-9` ① ↔ byte 결정론**(§1-8 형식 · post8 §18 2번 승계) — 「이 DB 지문을 처음 읽은 실행의 시각」을 인쇄하고 지문이 "
        "같은 재실행은 그 값을 다시 쓴다(`reconstruct_post10/read_stamp.json` · 지문이 같으면 파일을 다시 쓰지 않는다) · "
        "🔴 **다음 sweep(10-08 이후 봉 적재) 뒤 재실행은 지문(`max(date)`·②)이 바뀌어 byte 불일치가 «반드시» 난다** — "
        "결함이 아니라 동결 규칙의 귀결이다(`PREREG_POST9.md` §6 (마)).")
    say("3. 🔴 **「전부 경계 후/전」 창의 신고 대상 여부**(PD-27 (바)) — `:546-548` 방아쇠는 「걸치면」 ⇒ 신고 줄 대상 아님 · 추가 인쇄 줄만(§0-b) · 판정 효과 0.")
    say("4. 🔴 **`F-3` 기업행위 건**(§0-b) — 건 단위 정의 A · ⓐ `split` · ⓑ `volume=0` · 규칙·갈래 신설 0 · 「기업행위 건 제외」 값은 §14 끝 인쇄(세지 않는다).")
    say("5. 🔴 **샌즈랩 「샌즈 제외」 의 지위(확인 필요)** — PD-23 `REC-` 행은 「(포함 + 구조차단)」 으로 적었고 등록일 축·`EXIT-E2` 행은 「인쇄만」 으로 적었다. "
        "이 산출물은 `P8-갈래계수` 를 **두 읽기로 모두** 인쇄했다(계수 읽기 = 주 · 인쇄만 읽기 = 대조 · §14) — 어느 쪽을 판정에 쓰는지는 §6 단계 · 관리자 몫.")
    say("6. 🔴 **`REC-` 절단 갈래의 정의(확인 필요)** — post9 판 코드는 절단 = `[D−19,D]`<20 **또는** 창5<5 였다. INTAKE §5 는 `REC-` = `[D−19, D]` 절단 0(항등) · "
        "창5 절단 1(뷰노)은 `LAD-` 몫이라 적었다 ⇒ 이 산출물은 `[D−19,D]`<20 만 절단으로 센다(창5 절단은 §14·§16 에 인쇄만).")
    say("7. 🔴 **`REC-Z4` 동결 문언 「first_only 3레그」**(PD-13 T6) — 관행(서로 다른 값 ≥3)과 「정확히 3레그」 두 계수를 "
        "인쇄했다(§9) · 귀결 소멸(결정 ④)이라 판정 이동 0.")
    say("8. 🔴 **`Q1-R3` 두 읽기** — 건 단위 규약(`PREREG_POST6.md:743-746`)이 있어 측정 가능 읽기가 주 · 건수 읽기는 병기(§11·§14).")
    say()
    say("🔴 **이 문서는 라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST10.md`). **새 예측을 만들지 않았다** — "
        "동결된 항목(`PREREG_POST6.md` §4 #38~#54 · `PREREG_POST8.md` `D-3`·`D-5`·`D-9` · `PREREG_POST9.md` §1 · `PREREG_POST10.md` `F-3`·`F-5`)만 계산·인쇄했다.")
    say()
    say("[[LABELS_2026-10-04_post10]] · [[INTAKE_2026-10-04_post10]] · [[PREDECISION_2026-10-04_post10]] · "
        "[[PREREG_POST10]] · [[PREREG_POST9]] · [[PREREG_POST8]] · [[PREREG_POST6]] · "
        "[[PREREG_WEIGHTED_RECON]] · [[PREREG_ANCHOR_REDESIGN]] · [[PREREG_GRADE_TIERS]] · [[RESULTS_RECONSTRUCT_POST9]]")

    (BASE / OUT_NAME).write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    note("\n[written] RESULTS_RECONSTRUCT_POST10_NUMBERS.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
