# -*- coding: utf-8 -*-
"""`WRC-` 축 **판정** 실행 — 8번째 글(`logNo=224416253270` · 발행 2026-09-18 금 · 거래일).

🔴🔴 **이번 회차의 갈림(값을 보기 «전»에 인테이크가 구성으로 적은 것)**
  · post8 «단독» 판정 분모 = **0** — `exact` 4건(우리로·JW신약·액스비스·우리기술)이 **전부 `fill_n = 1`**
    (`INTAKE_2026-09-18_post8.md` §2-10·§2-19 · PD-13 · PD-22). 🔑 값이 아니라 저자의 체결 차수 서술이 닫았다.
  · 판정 분모 = **누적**(`WRC-R11` · `PREREG_WEIGHTED_RECON.md:747-752`) = post6 5 + post7 0 + post8 0.
  · 🆕 `PREREG_POST8.md` §4 `D-4`(`P8-WRC단독열`) 첫 구속 — **단독 · 누적 · 판정에 쓴 분모 세 수를 «같은 행»**에
    인쇄한다. 「단독 0」을 「최소 n 미달」로 적지 않는다(`:297`) · 「최소 n 미달」 ≠ 「`WRC-G1` 발동」(`:299`).
  · 🔴 post7 은 누적 분모를 **옮겨 적은 상수**(post6 5 · G1 4/5)로 썼다(`run_wrc_post7.py:204` `P6_WRC`).
    이 회차는 공통 의무(*「post4~7 표본을 같은 스냅샷에서 재계산해 나란히 · 직전 문서 숫자 옮겨 적기 금지」*)와
    `WRC-R11` 의 *「이후 글에서는 누적 전체로 다시 계산한다(같은 검정의 갱신)」*에 따라 **누적 분모의 `WRC-G1`
    (① DB부재 + ④ 현행 `A0` 해 0개)을 이 스냅샷에서 다시 잰다** — 각 글의 «동결 창 종료»(post6 = 09-04 · 탐색 = 09-02)
    그대로. 옮겨 적은 값(post6 4/5 · 탐색 6/10)은 **대조 열**로만 둔다.
  · 🔴 `WRC-G1` 이 1/3 이상이면 *「나머지 계산을 «돌리지 않는다»」*(§4-6 · §7-B #24) — 이 실행은 그 문언대로
    `A1`·`A3`·대조군(`WRC-N1`·`N2`)을 **돌리지 않는다**(post6 은 관리자 지시로 «계산하되 ⛔»였다 · 모호 신고).
  · `approx` 1건(코데즈컴바인 · `fill_n = 2` · 서로 다른 값 레그 5)은 **민감도 갈래**다(`RNK-D5`·`ANC` §2-3·`S5` §1-1 ·
    `PREREG_POST8.md` §3 `D-3`). 「8월말」 창 규약 = 08-21~08-31 거래일 7일(PD-4 2번) — 갈래마다 `A0` 를 잰다.
  · 우리로(항목 내 2 사이클)는 `WRC-R5` 동결 문형 = 포함 + `구조차단` 플래그 + 「우리로 제외」 민감도(🔒 #1-(i)) —
    🔴 단 **`fill_n = 1` 로 판정 분모 조건에서 먼저 빠진다**(PD-3 ④ · 「두 평단」이 사유가 아니다) ⇒ 제외 갈래는 **항등**.

사전등록·동결(값을 보기 «전»에 고정 · 1순위 출처):
  · `PREREG_WEIGHTED_RECON.md` §4 예측표(`WRC-P1`·`N1`·`N2`·`G1`·`O1`·`V1`) · §2-7 `WRC-R5` · §4-6 `WRC-G1` 분자(①+④) ·
    §4-8 `WRC-V1` 4축 · §5-2 `WRC-R7`(:678-680 B-1 승계) · §6-1 `WRC-R11` · §7-B #24 · §9 한계
  · `FREEZE_WRC_2026-09-02.md` — 주 모델 `WRC-A1` · 시드 `20260815` · 20,000회 · 밴드 3%p · `G1` 1/3 · `N` 50% ·
    창 종료 `2026-09-02`(탐색) · §2 「HEAD 해시·벽시계는 본문에 적지 않는다」
  · `PREREG_POST8.md`(동결 `04cd785` · 머지 `729f28b`) §3 `D-3` · §4 `D-4` · §5 `D-5` · §8 `D-8` · §9 `D-9` · §0-5-1 가분성
  · `PREDECISION_2026-09-18_post8.md` PD-1(창 종료 **2026-09-18** · 발행 당일 봉 «포함» · `WRC-` 포함) ·
    PD-3 ④ · PD-4 · PD-11 커버리지 표 · PD-13 · PD-21 · PD-22 · PD-23 · PD-26 · PD-27 (라)(마)(바)
  · `INTAKE_2026-09-18_post8.md` §1(종목·코드·차수·레그) · §2-19 · §5 「WRC-」 행 · §5 공통 ⚠️
  · `LABELS_2026-09-18_post8.md` · 🔒 사장님 결정 #1-(i)(2026-09-18 20:3x KST)

재사용(= import · 새 정의 0 · `WRC-R6`·`WRC-X1` 4번): `run_wrc_explore`(`build_cases`·`read_ledger`·`make_ctx`·
`CODEMAP`·문턱 상수) · `run_reconstruct_post5.feasible_exact` · `run_wrc_post7`(`approx_branch`·`split_reasons`·
`denom`·`CODES7`) · `run_wrc_post6`(`CODES6`·`PD3_FLAG`·`INTAKE_DENOM_PRED`). 🔴 그 파일들은 **한 글자도 바꾸지 않는다.**

🔴 **읽은 시각(D-9 ①)과 바이트 결정론의 절충(재량 · 보고서에 신고)** — `PREREG_POST8.md` §9 (나) 2 는 쿼리 실행
   시각을 산출물에 인쇄하라 하고, `FREEZE_WRC_2026-09-02.md` §2 는 커밋·벽시계처럼 «매번 바뀌는 값»을 본문에
   적지 않는다. ⇒ 본문 ① 칸 = **이 DB 스냅샷 지문(②·④·`max(date)`·그 날 행수)을 이 스크립트가 «처음» 읽은
   실행의 KST 시각**(`wrc_post8/read_stamp.json` 에 지문과 함께 보관) · 같은 지문의 재실행은 그 값을 다시 쓰고
   **이번 실행의 벽시계 시각은 stdout** 으로 낸다. 지문이 바뀌면(= 다른 sweep 이후) 새 시각이 박힌다.

🔴 라이브 트리 import 0건 · DB 는 **SELECT 만** · `adj_factor` 산술 0건 · 원장은 «읽기»만 · 새 예측 0 · 새 문턱 0 ·
   등급 이름 0(§6 단계 · PD-16·PD-28).
🔴 **라이브 채택 금지**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import psycopg2

from run_reconstruct_post5 import feasible_exact
from run_tests import DSN
from run_wrc_explore import (
    BAND_THR,
    CODEMAP,
    G1_THR,
    NREP,
    N_THR,
    SEED,
    THR,
    build_cases,
    make_ctx,
    read_ledger,
)
from run_wrc_post6 import CODES6, INTAKE_DENOM_PRED, PD3_FLAG
from run_wrc_post7 import CODES7, approx_branch, denom, split_reasons

BASE = Path(__file__).resolve().parent
ART = BASE / "wrc_post8"
OUT: list[str] = []

POST8_LOG = "224416253270"       # INTAKE_2026-09-18_post8.md 머리말
POST8_DATE = "2026-09-18"        # 발행일(금 · 거래일) — PD-1
DB_UPTO = "2026-09-18"           # 🔴 창 종료 = 발행 당일 봉 «포함» · B-1 · 전 축(`WRC-` 포함) · PD-1
POST6_LOG = "224401108114"
POST7_LOG = "224409404744"
BOUNDARY = "2026-09-14"          # KRX 연장 제도 경계(`PREREG_POST8.md` §9 (나) 3)
SWEEP_D1 = "2026-09-21 15:35:00"  # 09-18 봉의 D+1 sweep(PD-27 (마) 2)
MGR_WIN = ("2026-07-24", "2026-09-18")   # PD-27 (다) 프로브 창(관리자 착수 증거와 같은 창)

# 글별 «동결 창 종료» — 재계산은 각 글이 판정(또는 탐색)된 그 창 그대로 한다(새 창을 고르지 않는다).
WINDOW_END = {
    "post4": "2026-09-02",       # FREEZE_WRC_2026-09-02.md §2 「창 종료일 2026-09-02」(탐색)
    "post5": "2026-09-02",       # 〃
    "post6": "2026-09-04",       # RESULTS_WRC_POST6_NUMBERS.md §0 「DB 스냅샷 최신 봉 2026-09-04」 = 발행일
    "post7": "2026-09-11",       # PREDECISION_2026-09-15_post7.md PD-1
    "post8": DB_UPTO,            # PREDECISION_2026-09-18_post8.md PD-1
}
WINDOW_END_SRC = {
    "post4": "`FREEZE_WRC_2026-09-02.md` §2", "post5": "`FREEZE_WRC_2026-09-02.md` §2",
    "post6": "`RESULTS_WRC_POST6_NUMBERS.md` §0", "post7": "`PREDECISION_2026-09-15_post7.md` PD-1",
    "post8": "`PREDECISION_2026-09-18_post8.md` PD-1",
}

# ── 8번째 글 종목코드 — `INTAKE_2026-09-18_post8.md` §1 표 «그대로» (10/10 · PD-11) ──────────────
#    🔴 원장에는 종목코드 컬럼이 «없다» ⇒ 이름→코드는 인테이크가 유일 출처다.
#    액스비스 = `0011A0`(news 경유) · 우리기술 = `032820`(≠ 우리기술투자 041190).
CODES8 = {
    "빛과전자": "069540", "로보티즈": "108490", "우리로": "046970", "범한퓨얼셀": "382900",
    "원익": "032940", "JW신약": "067290", "헥토파이낸셜": "234340", "액스비스": "0011A0",
    "코데즈컴바인": "047770", "우리기술": "032820",
}
POST8_FOLLOWUP = ("빛과전자", "로보티즈", "범한퓨얼셀")   # PD-2 — 기존 건 후속(등록일 축 밖)
POST8_NONE_NEW = ("원익",)                                # PD-4 🔒 #2 — `none`
POST8_APPROX = ("헥토파이낸셜", "코데즈컴바인")           # PD-4 — 「8월말」
POST8_TWO_CYCLE = ("우리로",)                             # PD-3 — 항목 내 2 사이클(`WRC-R5` `구조차단`)

# `INTAKE_2026-09-18_post8.md` §1 표 — «계산 전» 구성. 원장이 SSOT 이고 여기선 대조만 한다.
#    (종목, 정밀도, fill_n, 레그)
INTAKE_ROWS8 = [
    ("빛과전자", "none", 1, [23.47, 17.88]),
    ("로보티즈", "none", 1, [17.95, 16.74]),
    ("우리로", "exact", 1, [24.20, 19.94, 17.0, 16.26, 13.32, 12.44, 0.54]),
    ("범한퓨얼셀", "none", 1, [20.99, 20.99, 0.43]),
    ("원익", "none", 1, [19.49, 17.61, 15.54, 13.14]),
    ("JW신약", "exact", 1, [16.28, 12.68, 11.05, 10.78]),
    ("헥토파이낸셜", "approx", 1, [5.84, 2.98, 1.39, -2.28]),
    ("액스비스", "exact", 1, [11.64, 0.31]),
    ("코데즈컴바인", "approx", 2, [13.20, 11.05, 11.03, 8.71, 6.59]),
    ("우리기술", "exact", 1, [8.47, 8.47, 8.23, 4.75]),
]
APPROX_DAYS = ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
               "2026-08-27", "2026-08-28", "2026-08-31"]   # PD-4 2번 「8월 말」 거래일 7일(DB 달력으로 재확인)

# 옮겨 적은 동결값 — 🔴 **재계산 결과와의 «대조» 전용**(판정에 쓰지 않는다).
FROZEN_G1 = {
    "explore": dict(denom=10, db_absent=1, empty=5, src="`FREEZE_WRC_2026-09-02.md` §4 · `PREREG_WEIGHTED_RECON.md` §4-6"),
    "post6": dict(denom=5, db_absent=0, empty=4, src="`RESULTS_WRC_POST6_NUMBERS.md` §2"),
    "post7": dict(denom=0, db_absent=0, empty=0, src="`RESULTS_WRC_POST7_NUMBERS.md` §3"),
}

# `PREDECISION_2026-09-18_post8.md` PD-27 (바) 표의 「걸침」 칸 전부 — (축·창 이름, 종목, 코드, 시작, 끝).
#    🔴 이 축이 읽는 창이 «아니다»(ANC-·REC-·LAD- 창) — 공통 인쇄 의무라 전/후 봉수를 실측해 적는다.
PD27_CROSS = (
    [("`ANC-`/`REC-` `[D, END]`", nm, cd, d, DB_UPTO) for nm, cd, d in
     (("우리로", "046970", "2026-09-11"), ("액스비스", "0011A0", "2026-09-11"),
      ("우리기술", "032820", "2026-09-09"), ("JW신약", "067290", "2026-09-01"))]
    + [("`ANC-`/`REC-` `[D, END]`(approx)", nm, cd, d, DB_UPTO) for nm, cd in
       (("헥토파이낸셜", "234340"), ("코데즈컴바인", "047770")) for d in APPROX_DAYS]
    + [("`ANC-N4` ① `[D, 09-17]`", nm, cd, d, "2026-09-17") for nm, cd, d in
       (("우리로", "046970", "2026-09-11"), ("액스비스", "0011A0", "2026-09-11"),
        ("우리기술", "032820", "2026-09-09"), ("JW신약", "067290", "2026-09-01"))]
    + [("`LAD-` 창5 `[D, D+4]`", "우리로", "046970", "2026-09-11", "2026-09-17"),
       ("`LAD-` 창5 `[D, D+4]`", "액스비스", "0011A0", "2026-09-11", "2026-09-17"),
       ("`LAD-` 창5 `[D, D+4]`", "우리기술", "032820", "2026-09-09", "2026-09-15"),
       ("`LAD-` 창5(post7 대체)", "빛과전자", "069540", "2026-09-08", "2026-09-14"),
       ("`LAD-` 창5(post7 대체)", "범한퓨얼셀", "382900", "2026-09-09", "2026-09-15"),
       ("`LAD-` 창5(post7 대체 · approx)", "지투파워", "388050", "2026-09-08", "2026-09-14"),
       ("`LAD-` 창5(post7 대체 · approx)", "지투파워", "388050", "2026-09-09", "2026-09-15"),
       ("`LAD-` 창5(post7 대체 · approx)", "지투파워", "388050", "2026-09-10", "2026-09-16")]
)


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호 · `FREEZE_WRC_2026-09-02.md` §2)."""
    print(s)


def post_label(log_no, fallback):
    return {POST6_LOG: "post6", POST7_LOG: "post7", POST8_LOG: "post8"}.get(log_no, fallback)


def code_of(c):
    lab = c["post"]
    if lab in ("post4", "post5"):
        return CODEMAP.get(c["name"])
    return {"post6": CODES6, "post7": CODES7, "post8": CODES8}[lab].get(c["name"])


def a0_measure(cur, code, reg, end, legs, kind="gross"):
    """`WRC-G1` 분자 판정 — ① DB부재(코드 없음·봉 없음) / ④ 현행 `A0` 해 0개 / 해 있음.

    🔴 `run_wrc_post6.py:488-504` 와 **같은 경로**(창 `[등록일, 창 종료]` · `make_ctx` · `feasible_exact`)다."""
    if not code or not reg:
        return "db_absent", 0
    cur.execute("SELECT date, open, high, low, close FROM daily_prices "
                "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date", (code, reg, end))
    rows = cur.fetchall()
    ctx = make_ctx(rows) if rows else None
    if ctx is None:
        return "db_absent", len(rows)
    iv = feasible_exact(ctx["rows"], legs, kind)
    return ("feasible" if iv else "empty"), len(rows)


def g1_of(cases):
    n = len(cases)
    a = sum(1 for c in cases if c["a0"] == "db_absent")
    z = sum(1 for c in cases if c["a0"] == "empty")
    return n, a, z, ((a + z) / n if n else None)


def fmt_g1(n, a, z, r):
    return "—(분모 0 · 비율을 만들 수 없다)" if r is None else f"{a + z}/{n} = {100 * r:.1f}%"


def fire(r):
    if r is None:
        return "—"
    return "🔴 **발동**" if r >= G1_THR else "🟢 미발동"


def main() -> int:  # noqa: C901, PLR0912, PLR0915
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    # ── 스냅샷 지문(D-9 ②·④ · 기록) ─────────────────────────────────────────
    cur.execute("SELECT max(date) FROM daily_prices")
    max_date = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (max_date,))
    max_rows = int(cur.fetchone()[0])
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices WHERE date BETWEEN %s AND %s",
                MGR_WIN)
    mgr_min_u, mgr_max_u = cur.fetchone()
    cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices WHERE date = %s",
                (DB_UPTO,))
    end_rows, end_min_u, end_max_u = cur.fetchone()
    cur.execute("SELECT count(DISTINCT date) FROM daily_prices WHERE date BETWEEN %s AND %s",
                ("2026-08-21", "2026-08-31"))
    n_approx_days = int(cur.fetchone()[0])
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s ORDER BY 1",
                ("2026-08-21", "2026-08-31"))
    approx_days_db = [r[0] for r in cur.fetchall()]

    # ── 표본 ────────────────────────────────────────────────────────────────
    tr, legs_map = read_ledger()
    cases_all = build_cases(tr, legs_map)
    for c in cases_all:
        c["post"] = post_label(c["log_no"], c["post"])
        c["code"] = code_of(c) if c["post"] in ("post4", "post5", "post6", "post7", "post8") else c["code"]
    p8 = [c for c in cases_all if c["log_no"] == POST8_LOG]

    # 🔴 이 스크립트가 실제로 읽는 창의 전 구간(D-9 ② 「창 구간」) — 재계산 창 + approx 갈래
    read_windows = []
    for lab in ("post4", "post5", "post6", "post7", "post8"):
        for c in cases_all:
            if c["post"] == lab and c["gate"] and c["reg"]:
                read_windows.append((c["reg"], WINDOW_END[lab]))
    read_windows += [(d, DB_UPTO) for d in APPROX_DAYS]
    span = (min(w[0] for w in read_windows), max(w[1] for w in read_windows))
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices WHERE date BETWEEN %s AND %s",
                span)
    span_min_u, span_max_u = cur.fetchone()

    # ── D-9 ① 읽은 시각 — 스냅샷 지문 키(재량 · 모듈 docstring) ────────────────
    fp = dict(max_date=str(max_date), max_rows=max_rows, mgr_min_u=str(mgr_min_u), mgr_max_u=str(mgr_max_u),
              span=list(span), span_min_u=str(span_min_u), span_max_u=str(span_max_u),
              end_rows=int(end_rows), end_max_u=str(end_max_u))
    cur.execute("SELECT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'), current_setting('TimeZone')")
    now_kst, tzname = cur.fetchone()
    stamp_p = ART / "read_stamp.json"
    prev = None
    if stamp_p.exists():
        try:
            prev = json.loads(stamp_p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = None
    if prev and prev.get("fingerprint") == fp:
        first_read, reused = prev["first_read_kst"], True
    else:
        first_read, reused = now_kst, False
        stamp_p.write_text(json.dumps(dict(fingerprint=fp, first_read_kst=first_read, timezone=tzname),
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    note(f"[stdout] 이번 실행 벽시계(DB now) = {now_kst} {tzname} · 본문 ① = {first_read}"
         f" ({'같은 지문 재사용' if reused else '새 지문 — 새 시각 기록'})")
    read_after_d1 = first_read >= SWEEP_D1[:19]
    min_after_d1 = str(mgr_min_u) >= SWEEP_D1

    # ═══ 머리 ═══════════════════════════════════════════════════════════════
    say("# RESULTS_WRC_POST8_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_wrc_post8.py` · 승계 `run_wrc_post7.py`(`approx_branch`·`split_reasons`·`denom`·`CODES7` import) · "
        "`run_wrc_post6.py`(`CODES6`·`PD3_FLAG`·`INTAKE_DENOM_PRED` import) · 재사용(=import) "
        "`run_wrc_explore.py`(`build_cases`·`read_ledger`·`make_ctx`·`CODEMAP`·문턱 `SEED`·`NREP`·`THR`·`BAND_THR`·"
        "`G1_THR`·`N_THR`) · `run_reconstruct_post5.py`(`feasible_exact`)")
    say("사전등록 `PREREG_WEIGHTED_RECON.md` §4·§4-6·§4-8·§5-2·§6-1·§7-B #24 · 동결 `FREEZE_WRC_2026-09-02.md` · "
        "🆕 `PREREG_POST8.md` §3(`D-3`)·§4(`D-4`)·§5(`D-5`)·§8(`D-8`)·§9(`D-9`) · 인테이크 "
        "[`INTAKE_2026-09-18_post8.md`](INTAKE_2026-09-18_post8.md) §1·§2-19·§5 · 결정 "
        "[`PREDECISION_2026-09-18_post8.md`](PREDECISION_2026-09-18_post8.md) PD-1·PD-3·PD-4·PD-11·PD-13·PD-21~23·PD-26·PD-27\n")
    say("> 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) — 이 문서의 어떤 수도 "
        "매매 규칙·파라미터 변경의 근거가 아니다. 🔴 새 예측 0 · 새 문턱 0 · 등급 이름 0(§6 단계).")
    say("> 🔴 **판정 분모 = «누적»**(`WRC-R11`) — post8 «단독» 0 은 **병기**할 뿐 「최소 n 미달」의 근거가 아니다"
        "(`PREREG_POST8.md` §4 (나) 1). 🔴 누적은 **이 스냅샷에서 재계산**했다 — 옮겨 적은 동결값은 대조 열이다.\n")

    # ═══ §0 ═════════════════════════════════════════════════════════════════
    say("## §0. 실행 환경 · 동결 규약 · 🆕 `PREREG_POST8.md` 공통 인쇄 의무\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 대상 | 8번째 글 `logNo={POST8_LOG}` (발행 **{POST8_DATE}** 금 · 거래일) · 프로그램 `1.0.42` |")
    say(f"| 🔴 창 종료 | **창 종료 {DB_UPTO} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
        "전 축(`WRC-` 포함) · PD-1** |")
    say(f"| 🔴 실행 시 `max(date)` | **{max_date}** · 그 날짜 행수 **{max_rows:,}** — 🔴 **기록만(창 아님)**(PD-1 8번) |")
    say(f"| D-9 ① 쿼리 실행 시각(KST) | **{first_read}** ({tzname}) — 🔴 이 DB 스냅샷 지문(②·④·`max(date)`·행수)을 "
        "이 스크립트가 «처음» 읽은 실행의 시각(`wrc_post8/read_stamp.json`). 같은 지문의 재실행은 이 값을 다시 쓰고 "
        "이번 실행의 벽시계는 stdout 으로만 낸다(바이트 결정론 · `FREEZE_WRC_2026-09-02.md` §2 관용과의 절충 · 재량 신고) |")
    say(f"| D-9 ② 창 구간 `max(daily_prices.updated_at)` | 이 스크립트가 읽는 창 전 구간 `[{span[0]}, {span[1]}]` = "
        f"**{span_max_u}** · 관리자 프로브 창 `[{MGR_WIN[0]}, {MGR_WIN[1]}]` = **{mgr_max_u}** · "
        f"{DB_UPTO} 봉(행 {end_rows:,}) = **{end_max_u}** |")
    say(f"| D-9 ③ | **「{DB_UPTO} 봉은 D+1(2026-09-21) sweep 이후 읽음」** — ① {first_read} ≥ {SWEEP_D1[:16]} : "
        f"{'예' if read_after_d1 else '🔴 아니오'} |")
    say(f"| D-9 ④ (기록 · 통과 조건 아님) | **「창 구간 `min(updated_at)` = {mgr_min_u} ≥ 09-21 15:35: "
        f"{'예' if min_after_d1 else '아니오'}」**(창 `[{MGR_WIN[0]}, {MGR_WIN[1]}]` · PD-27 (마) 2 (f)) · "
        f"이 스크립트 창 전 구간 `min(updated_at)` = {span_min_u} · 🔴 `updated_at` 은 일괄 갱신 값이라 빈티지 "
        "«증거»가 아니라 «읽은 시각» 기록이다(PD-27 (라)) |")
    say("| D-9 ⑤ 혼합 빈티지 | §7 (걸침 창마다 한 줄 · 경계 전/후 봉수 실측) · 「정규장만」 갈래 **열지 않음** · "
        "`adj_factor` 산술 **0** |")
    say(f"| 판정 분모 정의 | `exact` ∧ `fill_n >= 2` ∧ **서로 «다른» 값 레그 >= 3**(§6-1 `WRC-R11` · 동결본 "
        "`build_cases` 를 **import 해서** 판단) · 🔒 **판정에 쓴 분모 = 누적**(`PREREG_POST8.md` §4) |")
    say(f"| 시드 · 반복 | **{SEED}** · **{NREP:,}회** (동결값 import · 🔴 이 회차는 대조군을 «돌리지 않는다» — §3) |")
    say(f"| 문턱 | 밴드 **{BAND_THR}%p** · `G1` **{G1_THR:.4f}**(1/3) · `N` **{N_THR:.2f}** · 잔차 `THR` **{THR}** "
        "(전부 import) |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) |")
    say("")
    say("### 0-1. 🆕 `PREREG_POST8.md` 의무 줄 점검표 (이 산출물)\n")
    say("| 결정 | 이 산출물에서 | 자리 |")
    say("|---|---|---|")
    say("| `D-1`(ANC·LAD 누적 세 수) | 해당 없음 — `ANC-P3`·`LAD-` 축이 아니다 | — |")
    say("| `D-2`(EXIT 세 수) | 해당 없음 — `EXIT-` 축이 아니다 | — |")
    say("| **`D-3`**(`approx` 의존 신고) | **있음** | §6 |")
    say("| **`D-4`**(단독·누적·판정 분모 같은 행) | **있음** | §3 |")
    say("| **`D-5`**(갈래마다 이름·n·답) | **있음** | §5 |")
    say("| `D-6`(`ddof`) | 해당 없음 — 이 산출물은 `n_up` sd 를 인쇄하지 않는다 | — |")
    say("| `D-7`(창5 절단 가드) | 해당 없음 — `LAD-` 축이 아니다 | — |")
    say("| **`D-8`**(버전 수준 목록 · 행·글 두 단위) | **있음**(`PREREG_WEIGHTED_RECON.md` §9 공변량 기록) | §6 |")
    say("| **`D-9`**(①~⑤) | **있음** | §0 · §7 |")
    say("| `D-10`·`D-11`·`D-12` | 해당 없음(등급·`Q1-R2`·`S5`) — 등급 이름은 **한 개도 적지 않는다** | — |")
    say("")

    # ═══ §1 표본 ════════════════════════════════════════════════════════════
    ic_key = sorted((nm, prec, fn, len(set(lg))) for nm, prec, fn, lg in INTAKE_ROWS8)
    lc_key = sorted((c["name"], c["prec"], c["fill_n"], c["distinct"]) for c in p8)
    say("## §1. 표본 — 원장 재측정 ↔ 인테이크 «계산 전» 구성 대조\n")
    say(f"- 원장 `post_log_no = {POST8_LOG}` 행 **{len(p8)}건** 재측정(`build_cases` import).")
    if ic_key == lc_key:
        say("- 🟢 **원장 ↔ 인테이크 §1 표 전건 일치**(이름·정밀도·`fill_n`·서로 다른 값 레그 수).")
    else:
        say("- 🔴🔴 **원장 ↔ 인테이크 §1 표가 갈린다 — 원장이 SSOT 다.** 갈린 자리:")
        for a, b in zip(ic_key, lc_key):
            if a != b:
                say(f"  - 인테이크 `{a}` ↔ 원장 `{b}`")
    say(f"- 총 **{len(p8)}건** = 신규 7(`exact` 4 · `approx` 2 · `none` 1) + 후속 3(`none` · PD-2).")
    say("")
    say("| # | 종목 | 코드 | 정밀도 | `fill_n` | 레그 수 | **서로 «다른» 값 레그** | `open_ended` | 게이트 | 비고 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for c in p8:
        tag = []
        if c["name"] in POST8_FOLLOWUP:
            tag.append("후속(PD-2)")
        if c["name"] in POST8_NONE_NEW:
            tag.append("신규 `none`(🔒 #2)")
        if c["name"] in POST8_TWO_CYCLE:
            tag.append("🔀 항목 내 2 사이클 · **`구조차단`**(`WRC-R5`) — `fill_n = 1` 로 분모 밖")
        say(f"| {c['item']} | {c['name']} | `{c['code']}` | {c['prec']} | {c['fill_n']} | {c['n_legs']} | "
            f"**{c['distinct']}** | {c['open_ended']} | {'🟢 통과' if c['gate'] else '탈락'} | "
            f"{' · '.join(tag) or '—'} |")
    say("")

    # ═══ §2 단독 분모 ═══════════════════════════════════════════════════════
    ex_all, ex_first, ex_few, ex_pass = split_reasons(p8, "exact")
    ap_all, ap_first, ap_few, _ = split_reasons(p8, "approx")
    ap_br = approx_branch(p8)
    n_solo = len(denom([c for c in p8 if c["prec"] == "exact"]))
    say("## §2. post8 «단독» 판정 분모 — 🔴🔴 **0건 · «구성»으로 닫혔다**\n")
    say("| 갈래 | 건 | 1차 체결(`fill_n = 1`) | `fill_n >= 2` ∧ 다른 값 레그 < 3 | **나머지 두 조건 통과** |")
    say("|---|---|---|---|---|")
    say(f"| **`exact`(주 분모)** | {len(ex_all)} | **{len(ex_first)}** "
        f"({', '.join(c['name'] for c in ex_first) or '—'}) | **{len(ex_few)}** "
        f"({', '.join(c['name'] for c in ex_few) or '—'}) | 🔴 **{len(ex_pass)}** |")
    say(f"| `approx`(민감도 갈래) | {len(ap_all)} | {len(ap_first)} ({', '.join(c['name'] for c in ap_first) or '—'}) | "
        f"{len(ap_few)} ({', '.join(c['name'] for c in ap_few) or '—'}) | {len(ap_br)} "
        f"({', '.join(c['name'] for c in ap_br) or '—'}) |")
    say("")
    say("- 🔴 **`approx` 줄의 마지막 칸은 「게이트 통과」가 «아니다»** — 동결 게이트는 `exact` 를 하드로 문다. "
        "나머지 두 조건만 적용한 **민감도 갈래** 수이고 **판정에 쓰지 않는다**(`approx_branch()` · 게이트 재정의 아님).")
    say(f"- 🔴🔴 **post8 «단독» 분모 = {n_solo}건** — `exact` {len(ex_all)}건이 **전부 1차 체결**이다. "
        "🔑 ***값을 보고 닫은 것이 아니라 저자의 체결 차수 서술이 «구성»으로 닫았다***(INTAKE §2-10 · PD-13).")
    say("- 🔴 **우리로가 빠지는 사유는 `fill_n = 1` 이다 — 「두 평단」이 아니다**(PD-3 ④ · `PREREG_WEIGHTED_RECON.md:744`). "
        "`WRC-R5` 는 이 모양을 «포함 + `구조차단` + 제외 민감도»로 적었고, 그 플래그는 위 표에 인쇄했다. "
        "🔴 **`구조차단`(항목 내 2 사이클 · 우리로 1)과 §1-5 `P6-PRIOR_CYCLE_IN_WINDOW`(우리로 0)는 다른 플래그다**(PD-3).")
    say("")

    # ═══ §3 누적 재계산 ═════════════════════════════════════════════════════
    judged = {}
    for lab in ("post4", "post5", "post6", "post7", "post8"):
        sub = [c for c in cases_all if c["post"] == lab and c["gate"]]
        for c in sub:
            c["a0"], c["nbar"] = a0_measure(cur, c["code"], c["reg"], WINDOW_END[lab], c["legs"])
            c["a0_net"], _ = a0_measure(cur, c["code"], c["reg"], WINDOW_END[lab], c["legs"], "net")
        judged[lab] = sub
    explore = judged["post4"] + judged["post5"]
    cum = judged["post6"] + judged["post7"] + judged["post8"]
    n_cum, a_cum, z_cum, g1_cum = g1_of(cum)
    g1_fire = bool(g1_cum is not None and g1_cum >= G1_THR)
    p6_names_ok = sorted(c["name"] for c in judged["post6"]) == sorted(INTAKE_DENOM_PRED)

    say("## §3. 🆕 `D-4` 세 수 · `WRC-G1`(누적 · **이 스냅샷 재계산**) · 예측별 판정\n")
    say("### 3-1. `P8-WRC단독열` — **단독 · 누적 · 판정에 쓴 분모를 «같은 행»에** (`PREREG_POST8.md` §4 (나))\n")
    say("| 회차 | **단독**(post8 · §6-1 세 조건) | **누적**(post6 이후) | **판정에 쓴 분모**(= 누적) | 판정 분모 ≥ 3? | ⛔ 을 만든 것 |")
    say("|---|---|---|---|---|---|")
    say(f"| post8 | **{n_solo}** | **{n_cum}**(post6 {len(judged['post6'])} + post7 {len(judged['post7'])} + "
        f"post8 {len(judged['post8'])}) | **{n_cum}** | "
        f"{'🟢 예 — 게이트 열림' if n_cum >= 3 else '⛔ 아니오'} | "
        + (f"🔴 **`WRC-G1` 발동**({fmt_g1(n_cum, a_cum, z_cum, g1_cum)}) — 🔴 **「최소 n 미달」이 «아니다»**"
           if g1_fire else "`WRC-G1` 미발동") + " |")
    say("")
    say("- 🔴 **단독 분모 0 이어도 「최소 n 미달」이라 적지 않는다** — 누적이 3 이상이면 게이트는 «열린» 것이다"
        "(`PREREG_POST8.md` §4 (나) 1). 닫은 것의 이름 = **`WRC-G1` 발동**.")
    say("- 🔴 **기호 분리** — 「최소 n 미달」(열리는 조건 = 건수) ≠ 「`WRC-G1` 발동」(열리는 조건 = 커버리지 · "
        "`PREREG_WEIGHTED_RECON.md:777` *「한 글의 판정 분모에서 ① DB부재 + ④ 해 0개가 1/3 미만」*). "
        "🔑 ***건수만 늘려서는 이 축이 열리지 않는다.***")
    say(f"- 판정에 쓴 분모(**{n_cum}**) = 누적(**{n_cum}**) ⇒ `PREREG_POST8.md` §4 (나) 3 기계 검사 조건 충족.")
    say("")
    say("### 3-2. `WRC-G1` — 글별 재계산(같은 09-24 스냅샷 · 각 글의 동결 창 종료 그대로) ↔ 옮겨 적은 동결값\n")
    say("| 글 | 창 종료(출처) | 판정 분모 | ① DB부재 | ④ 해 0개 | **`WRC-G1`(재계산)** | 동결값(대조 · 출처) | 일치 |")
    say("|---|---|---|---|---|---|---|---|")
    g1_rows = {}
    for lab, sub in (("🔬 탐색 post4+post5", explore), ("post6", judged["post6"]),
                     ("post7", judged["post7"]), ("post8", judged["post8"])):
        n, a, z, r = g1_of(sub)
        key = "explore" if lab.startswith("🔬") else lab
        g1_rows[key] = (n, a, z, r)
        fz = FROZEN_G1.get(key)
        end_lab = "post4" if key == "explore" else key
        if fz:
            fz_s = (f"{fz['db_absent'] + fz['empty']}/{fz['denom']}" if fz["denom"] else "0/0") + f" · {fz['src']}"
            same = (n, a, z) == (fz["denom"], fz["db_absent"], fz["empty"])
            same_s = "🟢 일치" if same else "🔴 **불일치 — 재계산값으로 판정**"
        else:
            fz_s, same_s = "— (이 회차 신규)", "—"
        dbl = ", ".join(c["name"] for c in sub if c["a0"] == "db_absent") or "—"
        zl = ", ".join(c["name"] for c in sub if c["a0"] == "empty") or "—"
        say(f"| {lab} | `{WINDOW_END[end_lab]}`({WINDOW_END_SRC[end_lab]}) | {n} | {a} ({dbl}) | {z} ({zl}) | "
            f"**{fmt_g1(n, a, z, r)}** {fire(r)} | {fz_s} | {same_s} |")
    say(f"| 🔒 **누적 = 판정 분모**(post6+post7+post8) | 글별 | **{n_cum}** | {a_cum} | {z_cum} | "
        f"**{fmt_g1(n_cum, a_cum, z_cum, g1_cum)}** {fire(g1_cum)} | 4/5(post7 산출물의 누적) | "
        f"{'🟢 일치' if (n_cum, a_cum + z_cum) == (5, 4) else '🔴 **불일치 — 재계산값으로 판정**'} |")
    say("")
    say(f"- post6 판정 분모 재측정 = {', '.join(c['name'] for c in judged['post6'])} ⇒ 인테이크 post6 §5 «계산 전» 예측 "
        f"5건과 {'✅ 일치' if p6_names_ok else '🔴 불일치'}.")
    say("- 🔴 **탐색 행은 판정 분모에 «넣지 않는다»**(`WRC-O1` · §4-5) — 같은 스냅샷에서 다시 잰 **대조 기록**이다.")
    say("- 🔴 건별 값(창 봉수·`A0` 판정)은 `wrc_post8/gate.json` 에 있다. `A0` = `feasible_exact(..., \"gross\")` "
        "(`run_wrc_post6.py:504` 와 같은 경로).")
    say("")
    say("### 3-3. 예측별 판정 — `WRC-G1` 을 «가장 먼저» 계산했다(§7-B #24)\n")
    if g1_fire:
        say(f"🔴🔴 **누적 `WRC-G1` = {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} ≥ 1/3 ⇒ 발동** — §4-6·§7-B #24 *「1/3 이상이면 "
            "나머지 계산을 «돌리지 않는다»」* 문언대로 **`A1`·`A3`·대조군(`WRC-N1`·`N2`)을 이 실행에서 돌리지 않았다.** "
            "🔴 post6 은 관리자 지시로 «계산하되 ⛔»였고 post7 은 새 표본이 없어 계산할 것이 없었다 — 이 회차는 "
            "**문언 쪽**을 택했다(모호 신고 · 두 읽기 모두 판정 표기는 ⛔ 로 같다).")
    else:
        say("🟢 **누적 `WRC-G1` 미발동** — 🔴 이 실행은 G1 만 계산했으므로 나머지 예측은 **미룸**(계산 필요)이다.")
    say("")
    say("| 항목 | 가설(한 줄) | 문턱 | 판정 분모(누적) | **판정** | ⛔ 경로 |")
    say("|---|---|---|---|---|---|")
    blk = f"🔴 **누적 `WRC-G1` {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} ≥ 1/3 ⇒ 발동**" if g1_fire else "—"
    verdict = "⛔ **판정 불가(`WRC-G1` 발동)**" if g1_fire else "⏸ **미룸(G1 미발동 · 나머지 미계산)**"
    rows = [
        ("`WRC-P1`", "`WRC-A1` 이 차수별 밴드를 정보 있는 폭으로 좁힌다", f"폭 중앙 < {BAND_THR}%p 인 건 과반", blk),
        ("`WRC-N1`", "(대칭) 무작위 대조와 구분되는가", f"`A4` 성립률 ≥ {N_THR:.0%} ⇒ 강등", blk),
        ("`WRC-N2`", "(대칭) 좁은 밴드가 모델 때문인가 창 때문인가", f"`A4` 폭 < {BAND_THR}%p 비율 ≥ {N_THR:.0%} ⇒ 강등", blk),
        ("`WRC-G1`", "(커버리지) 잰 것이 표본을 대표하는가", f"(①+④)/분모 ≥ {G1_THR:.4f}",
         "🔴 **자신이 ⛔ 조건이다** — " + fmt_g1(n_cum, a_cum, z_cum, g1_cum)),
        ("`WRC-O1`", "탐색(post4·5) ↔ 판정(post6~) 병기", "괴리가 판정을 가르면 「탐색 편향 의심」",
         "§4 — 판정 열이 ⛔ 라 «비교»가 성립하지 않는다(병기만) · `PREREG_WEIGHTED_RECON.md:803`(§7-A #3) — "
         "`WRC-O1` 은 «조건부 인쇄» 항목이라 ⛔ 열이 없다 · post7 선례 표기 = 「⛔ 판정 불가(`WRC-G1` 발동)」"
         "(`RESULTS_WRC_POST7_NUMBERS.md:75`) — 선언이 없다는 뜻은 같고 문언 쪽으로 옮겼다(정정 1차)"),
        ("`WRC-V1`", "(민감도) 판정이 잣대에 종속되나", "갈리면 선언 금지", "§5 갈래표"),
    ]
    for lbl, hyp, thr, why in rows:
        v = verdict
        if lbl == "`WRC-G1`" and g1_fire:
            v = "🔴 **발동**(⛔ 조건 자체)"
        if lbl == "`WRC-O1`" and g1_fire:
            v = ("**조건부 인쇄 불성립** — 판정 열이 ⛔(`WRC-G1` 발동)라 「괴리가 판정을 가른다」가 서지 않는다 ⇒ "
                 "「탐색 편향 의심」 인쇄 없음")
        say(f"| {lbl} | {hyp} | {thr} | **{n_cum}** | {v} | {why} |")
    say("")
    say("⇒ 🔴 **6항목 전부 «지지»가 아니다**(5항목 ⛔ · `WRC-O1` 은 인쇄 조건 불성립 — 인쇄할 것이 없다). "
        "🔑 ***「못 좁힌다」도 「잴 건이 없었다」도 아니라 「못 쟀다」다***"
        "(`PREREG_WEIGHTED_RECON.md` §7-C 4번). 🔴 **문턱 `1/3` 을 올려 여는 것은 금지**(§4-6).")
    say("- 🔴 **`WRC-X1`(§4-7 구현 무효 조건) — 적용과 충족을 나눠 적는다**(정정 1차): 1~3번(`A1`·`A4` 결과 위에 서는 조건)은 "
        "이 실행이 `A1`·`A4` 를 돌리지 않아 **적용 대상 없음** · 4번(`tick`·격자·해찾기를 import 하지 않고 다시 쓴 흔적)은 "
        "**적용 · 위반 0**(`feasible_exact` = `run_reconstruct_post5` import · 새 정의 0) · 5번(`adj_factor` 산술)은 "
        "**적용 · 위반 0**(SQL·산술 0건 — 시험 `test_no_adj_factor_in_sql`).")
    say("- 🔴 **`bₖ` 표 0개** ⇒ `WRC-R9` 4줄의 부착 대상이 이 산출물에 없다(밴드를 계산하지 않았다).")
    say("")

    # ═══ §4 WRC-O1 ══════════════════════════════════════════════════════════
    ne, ae, ze, re_ = g1_rows["explore"]
    say("## §4. `WRC-O1` — 탐색(post4·post5)과 판정(post6~)을 «나란히» (§4-5 · 🔬 탐색은 판정 분모 밖)\n")
    say("| 통계량 | 🔬 탐색 — 동결 인용(창 `~2026-09-02`) | 🔬 탐색 — **이 스냅샷 재계산**(같은 창) | **판정 — 누적**(post6~8 · 글별 동결 창) |")
    say("|---|---|---|---|")
    say(f"| 판정 분모 | 10 | {ne} | **{n_cum}** |")
    say(f"| `WRC-G1` | 6/10 = 60.0% ⇒ 🔴 발동 | {fmt_g1(ne, ae, ze, re_)} {fire(re_)} | "
        f"**{fmt_g1(n_cum, a_cum, z_cum, g1_cum)}** {fire(g1_cum)} |")
    say(f"| `A0` 해 있는 건 | 4(이노테크·한켐p4·지투파워·PS일렉) | {sum(1 for c in explore if c['a0'] == 'feasible')} "
        f"({', '.join(c['name'] + '(' + c['post'] + ')' for c in explore if c['a0'] == 'feasible') or '—'}) | "
        f"**{sum(1 for c in cum if c['a0'] == 'feasible')}** "
        f"({', '.join(c['name'] for c in cum if c['a0'] == 'feasible') or '—'}) |")
    say("")
    say("- 🔴 **판정 열이 `WRC-G1` 로 ⛔ 라 두 열의 «괴리» 판정은 성립하지 않는다** — 병기만 한다(post7 §3 문형).")
    say("- 🔴 **모호 지점(승계)** — 「탐색값을 어느 창·어느 스냅샷에서 인용할 것인가」의 동결 문언이 없다(post6 §7-1 · "
        "post7 §6 3번). ⇒ **양쪽 인쇄**(동결 인용 + 같은 창 재계산) · 어느 쪽도 판정 근거로 고르지 않는다.")
    say("")

    # ═══ §5 D-5 갈래 ════════════════════════════════════════════════════════
    cod = next((c for c in p8 if c["name"] == "코데즈컴바인"), None)
    cod_res = []
    if cod is not None:
        for d in APPROX_DAYS:
            st, nb = a0_measure(cur, cod["code"], d, DB_UPTO, cod["legs"])
            cod_res.append((d, st, nb))

    def branch_g1(sub):
        return g1_of(sub)

    br = []
    br.append(("주 — 누적 · `exact` · `gross` · 재진입·미완결 포함", cum, "판정"))
    re_ex = [c for c in cum if PD3_FLAG.get(c["name"], 0) != 1]
    br.append(("`WRC-V1` 축③ 재진입 제외(post6 지투파워 · PD-3 flag)", re_ex, "민감도"))
    oe_ex = [c for c in cum if not c["open_ended"]]
    br.append(("`WRC-V1` 축③ 미완결(`open_ended = 1`) 제외", oe_ex, "민감도"))
    ur_ex = [c for c in cum if c["name"] not in POST8_TWO_CYCLE]
    br.append(("「우리로 제외」(`WRC-R5` · 🔒 #1-(i))", ur_ex, "민감도"))
    say("## §5. 🆕 `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나) 2)\n")
    say("🔴 **최소 n = 판정 분모 3**(`PREREG_WEIGHTED_RECON.md` §4 표 1행 · §6-1) — 동결문 값 그대로. "
        "「답」 = 그 갈래의 `WRC-G1` 판정(⛔ 이면 그 갈래에서도 축이 닫힌다).\n")
    say("| 갈래 | 지위 | **n** | 최소 n(3) | `WRC-G1` | **답** | 비고 |")
    say("|---|---|---|---|---|---|---|")
    answers = []
    for name, sub, role in br:
        n, a, z, r = branch_g1(sub)
        ans = ("⛔ `WRC-G1` 발동" if (r is not None and r >= G1_THR) else
               ("G1 미발동(나머지 미계산 ⇒ 미룸)" if r is not None else "분모 0"))
        if n >= 3:
            answers.append(ans)
        else:
            ans = f"(인쇄만 · n {n} < 3 — 「갈렸다」의 근거로 쓰지 않는다) {ans}"
        if role == "판정":
            same = "판정 갈래"
        elif sorted(c["name"] for c in sub) == sorted(c["name"] for c in cum):
            same = "**항등**(주 갈래와 같은 표본)"
        else:
            same = "빠진 건: " + ", ".join(sorted({c["name"] for c in cum} - {c["name"] for c in sub}))
        say(f"| {name} | {role} | **{n}** | {'충족' if n >= 3 else '🔴 미달'} | {fmt_g1(n, a, z, r)} | "
            f"**{ans}** | {same} |")
    # 잔차 문턱 · 모델 · 수수료 — G1 에 들어가는지 여부까지 인쇄
    say(f"| `WRC-V1` 축① 잔차 `{THR[1]}` ↔ `{THR[0]}`(`REC-Z5`) | 민감도 | **{n_cum}** | 충족 | "
        f"{fmt_g1(n_cum, a_cum, z_cum, g1_cum)} | **항등** | 🔴 `WRC-G1`(①+④)은 잔차 문턱을 입력으로 쓰지 않는다"
        "(`RESULTS_WRC_POST6_NUMBERS.md` §8-1 문형) ⇒ 이 갈래는 G1 을 움직일 수 없다 |")
    nn, an, zn, rn = n_cum, sum(1 for c in cum if c["a0_net"] == "db_absent"), \
        sum(1 for c in cum if c["a0_net"] == "empty"), None
    rn = (an + zn) / nn if nn else None
    ans_net = "⛔ `WRC-G1` 발동" if (rn is not None and rn >= G1_THR) else "G1 미발동(나머지 미계산 ⇒ 미룸)"
    answers.append(ans_net)
    say(f"| `WRC-V1` 축② 수수료 `gross`(판정) ↔ `net` | 민감도 | **{nn}** | 충족 | {fmt_g1(nn, an, zn, rn)} | "
        f"**{ans_net}** | `A0` 를 `net` 으로 다시 잰 값 |")
    say(f"| `WRC-V1` 축④ 모델 `A1` ↔ `A3` | 민감도 | **{n_cum}** | 충족 | {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} | "
        "**항등** | 🔴 `WRC-G1` 은 «현행(`A0`)» 해 0개로 정의된다 ⇒ 모델 축이 G1 을 움직일 수 없다(A1·A3 미계산) |")
    # approx 포함 — 판정 분모 밖 · `D-3` (나)2(판정 언어 없음) · (나)4 검사(두 갈래 모두 최소 n 충족 ⇒ 갈림 여부)
    apx_same = []
    for d, st, nb in cod_res:
        sub_z = z_cum + (1 if st == "empty" else 0)
        sub_a = a_cum + (1 if st == "db_absent" else 0)
        n_i = n_cum + 1
        r_i = (sub_a + sub_z) / n_i
        apx_same.append((r_i >= G1_THR) == g1_fire)
        say(f"| `approx` 포함(코데즈컴바인 D={d} · 창 `[{d}, {DB_UPTO}]` {nb}봉(등록일 포함) · `A0` {st}) | "
            f"민감도(`D-3` (나)4 검사용 · 판정 분모 아님) | **{n_i}** | 충족(🔴 `approx` 로 채운 n — 판정 분모 아님) | "
            f"{sub_a + sub_z}/{n_i} = {100 * r_i:.1f}% | "
            f"— (비율만 · 주 갈래와 {'같은' if apx_same[-1] else '다른'} 쪽) | "
            "판정 언어 붙이지 않음(`PREREG_POST8.md` §3 (나) 2) |")
    say(f"| post8 «단독»(참고 · 갈래 아님 · `D-4` 단독 열) | 기록 | **{n_solo}** | — | — | **—** | "
        "단독은 판정 분모가 «아니다»(§3-1) |")
    say("")
    uniq = sorted(set(answers))
    say(f"- **최소 n(3)을 채운 갈래의 답**: {', '.join(uniq)} ⇒ "
        + ("🟢 **갈리지 않는다**(전 갈래 같은 답) — `P8-갈래계수` 상 「갈렸다」 없음 · `WRC-V1` 은 **이 회차가 더한 갈림이 없다**"
           if len(uniq) == 1 else "🔴 **갈린다 ⇒ ⛔ `WRC-V1`**(선언 금지)"))
    say("- 🔴 **「우리로 제외」는 항등이다** — 우리로는 `fill_n = 1` 로 판정 분모에 애초에 없다(PD-3 ④). "
        "`WRC-R5` 의 «제외 민감도 의무»는 위 행으로 이행했다.")
    say("- 🔴 **`approx` 갈래는 판정 분모에 «넣지 않는다»**(`RNK-D5`·`ANC` §2-3·`S5` §1-1 · `D-3`) — "
        "「모순 갈래」 없음(코데즈는 「추가」 등록 · 헥토의 「한번 더」 모순은 `fill_n = 1` 이라 이 축 갈래가 아니다).")
    say(f"- 🔴 **`D-3` (나)4 검사**(`PREREG_POST8.md:250`): `exact` 주 갈래 n {n_cum} ≥ 3 · `approx` 포함 갈래 "
        f"{len(apx_same)}개 모두 n {n_cum + 1} ≥ 3 ⇒ 두 갈래 최소 n 충족 · 주 갈래와 «다른 쪽» "
        f"**{sum(1 for x in apx_same if not x)}/{len(apx_same)}** ⇒ "
        + ("**갈리지 않는다 — 판정 이동 0**" if all(apx_same) else "🔴 **갈린다 ⇒ ⛔ 판정 불가(등록일 정밀도 의존)**")
        + " · 봉수는 전부 「등록일 포함」(`PREREG_WEIGHTED_RECON.md:681` · N8).")
    say("")

    # ═══ §6 D-3 · D-8 · 커버리지 ════════════════════════════════════════════
    n_ap_incl = n_cum + len(ap_br)
    ap_opens = [] if n_cum >= 3 else (["`WRC-`"] if n_ap_incl >= 3 else [])
    say("## §6. 🆕 `D-3` 신고 줄 · `D-8` 수준 목록 · 커버리지(PD-11)\n")
    say(f"🆕 **`P8-approx의존신고`**: *「`approx` 포함 시 최소 n 이 차는 축: **{', '.join(ap_opens) or '없음'}** · "
        f"`exact` 분모 **{n_cum}**(누적 · 단독 {n_solo}) / `approx` 포함 분모 **{n_ap_incl}**」* "
        "(`PREREG_POST8.md` §3 (나) 3 · 구성 예고 = 「없음」 PD-21 — `n_exact` 이 이미 최소 n 3 을 채운다).")
    say("")
    # D-8 — 행·글 두 단위
    lv_rows = Counter((r["prog_ver"] or "missing") for r in tr)
    lv_posts = {}
    for r in tr:
        lv_posts.setdefault(r["prog_ver"] or "missing", set()).add(r["post_log_no"])
    say("🆕 **`P8-결측수준` 수준 목록**(`PREREG_POST8.md` §8 (나) 3 · 🔒 #3 = **행·글 두 단위 인쇄 · 부호 갈림 판정은 "
        "다음 사전등록까지 보류**) — 이 축은 `prog_ver` 를 공변량으로 «기록»만 한다(`PREREG_WEIGHTED_RECON.md` §9):\n")
    say("| 수준 | 행(건) | 글 |")
    say("|---|---|---|")
    for lv in sorted(lv_rows, key=lambda x: (x == "missing", x)):
        say(f"| `{lv}` | {lv_rows[lv]} | {len(lv_posts[lv])} |")
    say("")
    say("🔴 **커버리지는 축별로 «다른 수»다**(PD-11 · 한 수로 합치지 않는다) · `exact` 신규 분모 = **4**.\n")
    say("| 축 | 필요 자료 | 측정 가능 | 측정 불가 | 비율 | 문턱 1/3 |")
    say("|---|---|---|---|---|---|")
    say("| `SEL-`·`Q1-`·`REG-`·`RNK-`·`ANC-`·`LAD-`·`REC-` | `daily_prices` | 4/4 | 0 | 0% | 미발동 |")
    say("| `SEC-`(`SEC-G1`) | `stock_industry` 섹터코드 | 3/4 | 1(액스비스) | 25.0% | 미발동 |")
    say("| `S5` | `dart_financials_asfiled` PIT | 3/4 | 1(액스비스 — 표 미수록) | 25.0% | — |")
    say(f"| **`WRC-`(`WRC-G1`)** | `fill_n >= 2` ∧ 서로 다른 값 레그 >= 3 | **{n_solo}/4**(post8 단독) | — | "
        f"— (누적 {fmt_g1(n_cum, a_cum, z_cum, g1_cum)}) | 🔴 **누적 `WRC-G1` 로 ⛔**(최소 n 미달 «아님») |")
    say("")
    say("- 🔴 `WRC-` 의 「0/4」는 **자료 결손이 아니라 «구성»**이다 — 네 건 모두 `daily_prices` 가 있고 **1차 체결**이라 "
        "탈락한다(다른 축의 결손 사유와 종류가 다르다).")
    say("")

    # ═══ §7 D-9 혼합 빈티지 ════════════════════════════════════════════════
    def cross_line(nm, code, s, e):
        cur.execute("SELECT count(*) FILTER (WHERE date < %s), count(*) FILTER (WHERE date >= %s) "
                    "FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s", (BOUNDARY, BOUNDARY, code, s, e))
        nb, na = cur.fetchone()
        return int(nb), int(na)

    say("## §7. 🆕 `D-9` · `P8-혼합빈티지신고` — 걸침 창마다 한 줄 (`PREREG_POST8.md` §9 (나) 3 · 봉수 = 그 종목 봉 실측)\n")
    say("### 7-1. 이 축이 «읽는» 창\n")
    own = 0
    for lab in ("post4", "post5", "post6", "post7", "post8"):
        for c in judged[lab]:
            e = WINDOW_END[lab]
            if c["reg"] and c["code"] and c["reg"] < BOUNDARY <= e:
                nb, na = cross_line(c["name"], c["code"], c["reg"], e)
                say(f"- *「창 `[{c['reg']}, {e}]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `{nb}` 봉 / 후 `{na}` 봉 · "
                    f"혼합 빈티지」*({lab} {c['name']} · 판정 분모 재계산 창)")
                own += 1
    if cod is not None:
        for d in APPROX_DAYS:
            nb, na = cross_line(cod["name"], cod["code"], d, DB_UPTO)
            say(f"- *「창 `[{d}, {DB_UPTO}]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `{nb}` 봉 / 후 `{na}` 봉 · "
                f"혼합 빈티지」*(코데즈컴바인 `approx` 갈래 D={d} · 민감도)")
            own += 1
    say(f"- ⇒ 이 축 «판정 분모» 재계산 창(post6 `~09-04` · 탐색 `~09-02`)은 **경계 전**이라 걸침 **0** · "
        f"걸침은 `approx` 민감도 갈래 창뿐이다(이 절 {own}줄).")
    say("")
    say("### 7-2. PD-27 (바) 표의 「걸침」 칸 전부 — 공통 인쇄 의무 (🔴 `ANC-`·`REC-`·`LAD-` 창 · 이 축이 읽지 않는다)\n")
    for axis, nm, code, s, e in PD27_CROSS:
        nb, na = cross_line(nm, code, s, e)
        say(f"- *「창 `[{s}, {e}]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `{nb}` 봉 / 후 `{na}` 봉 · 혼합 빈티지」*"
            f"({axis} · {nm})")
    say("- `REG-`/`REC-`(§9 문언) `[D−19, D]` 는 전건 **안 걸침**(PD-27 (바) 넷째 열 · 신규 등록일 최대 09-11).")
    say("")
    say("### 7-3. 한계 절 문장(`P-4`·`P-5` 가 정한 것 · 정의 불변)\n")
    say("- ① `ovtm_vol` 채널은 09-14 에 0/2,756 이고 09-15 이후 `overtime_daily` 행이 **없다** ⇒ 시간외분을 `H`·`L` 에서 뺄 수 없다.")
    say("- ② 15:30 마감 분봉(`P-5` c1530)이 09-14 **1** · 09-15~17 **0** · 09-18 **1** · 09-21 **0** · 09-22 **1** · 09-23 **0**"
        "(관리자 착수 증거 `D:/archive/tasso-program-journal-20260918/probes_precalc_0924/p8_probes_postfetch_0924.txt` · "
        "2026-09-24 00:07:44 KST) ⇒ `minute_candles` 로 정규장 상한을 만들 수 없다 ⇒ **「정규장만」 갈래는 열지 않는다**"
        "(`PREREG_POST8.md` §9 (나) 4).")
    say("- ③ `P-3`(`updated_at > created_at`)은 이 DB 에서 **판별력 0** — 「통과」로 인용하지 않는다(PD-27 (라)).")
    say("")

    # ═══ §8 한계 ════════════════════════════════════════════════════════════
    say("## §8. 한계 (승계)\n")
    say("- 🔴 **단독 분모 0 은 우리 가설의 증거가 아니다** — 저자가 이번 주 `exact` 건을 1차 체결로 끝낸 이유를 모른다.")
    say("- 🔴 **`WRC-` 는 post6 한 회차의 표본으로만 굴러간다** — 단독 열이 post7·post8 두 회차 연속 **0** 이다. "
        "`PREREG_POST8.md` §4 (다) *「「단독」 열이 여러 회차 연속 0 인데 누적 판정이 계속 갱신된다 ⇒ `WRC-P1` 이 옛 표본만으로 "
        "굴러간다는 뜻이고, 그 사실 자체를 신고해야 할 자리」* — **여기 신고한다**(문턱은 바꾸지 않는다).")
    say("- 🔴 **누적 분모가 «두 제도»를 섞을 수 있다**(`PREREG_POST8.md` §14) — 이번 누적 5건은 전부 경계 «전» 창이다.")
    say("- 🔴 **`adj_factor` 를 곱하지도 나누지도 않는다** · DB 는 SELECT 만 · 원장은 읽기만.")
    say("- 🔴 이 분석은 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1).")
    conn.close()

    # 기계 산출물 — 건별 재계산(판정 근거의 원자료)
    gate = dict(
        window_end=WINDOW_END, db_upto=DB_UPTO,
        cases=[dict(post=c["post"], name=c["name"], code=c["code"], reg=c["reg"], fill_n=c["fill_n"],
                    distinct=c["distinct"], open_ended=c["open_ended"], a0_gross=c["a0"], a0_net=c["a0_net"],
                    nbar_window=c["nbar"])
               for lab in ("post4", "post5", "post6", "post7", "post8") for c in judged[lab]],
        cumulative=dict(n=n_cum, db_absent=a_cum, empty=z_cum, g1=g1_cum, fire=g1_fire),
        solo_post8=n_solo,
        approx_codez=[dict(D=d, a0_gross=st, nbar=nb) for d, st, nb in cod_res],
        approx_days_db=approx_days_db, approx_days_db_n=n_approx_days,
    )
    (ART / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (BASE / "RESULTS_WRC_POST8_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    note("")
    note(f"[written] RESULTS_WRC_POST8_NUMBERS.md · wrc_post8/gate.json · 런타임 {time.time() - t0:.3f}s")
    if approx_days_db != APPROX_DAYS:
        note(f"🔴 「8월 말」 거래일 DB 재확인 불일치: {approx_days_db} ≠ {APPROX_DAYS}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
