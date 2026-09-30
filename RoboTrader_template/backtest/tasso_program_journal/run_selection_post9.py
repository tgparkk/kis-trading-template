# -*- coding: utf-8 -*-
"""`PREREG_SELECTION.md` §7 + `PREREG_POST6.md` §2-1 실행 — 9번째 글 (out-of-sample, 6회차).

`run_selection_post8.py` 를 **승계**한다(원본은 손대지 않는다). 특징·통계량·표 포맷·조회·로더·빈티지·걸침 문장은
post6/post7/post8 판을 **import 해 그대로 재사용**한다. post8 로더(`load_raw_close`·`market_days`)는 모듈 전역
`DB_UPTO` 를 호출 시점에 읽으므로 이 실행 안에서만 `P8.DB_UPTO` 를 09-23 으로 바꾼다(파일 불변).
새로 적은 것 = ① post9 상수(글 목록 · 창 · 빈티지 · 출력 경로) ② `_main` 인쇄 순서 — post8 `_main` 은 post8 글 전용
문구(우리로·헥토·액스비스)가 박혀 있어 import 할 수 없다 ⇒ **판정 줄은 post8 `_main` 에서 그대로 옮기고** post9 구성에서
대상이 없는 절(`approx` 갈래 · 「우리로 제외」)은 「대상 없음」 한 줄로 줄였다(이탈 자기신고 · 산문 §10)
③ `PREREG_POST9.md` 인쇄 의무(`P9-공통독법` · `P9-행단위` 해당 없음 줄 · §0-1 라이브 문구 축자)
④ D-9 ① 스탬프(`selection_post9/read_stamp.json` · 지문 같으면 재기록 안 함 — post8 ANC/WRC 형식 · `P9-스탬프통일` 아님).

동결 준거: `PREREG_SELECTION.md` §7 · `PREREG_POST6.md` §2-1·§4 #1~#6·#11·§1-4~§1-6·§5-1·§5-2 ·
`PREREG_POST8.md` §0-1·§0-5-1·D-3·D-5·D-6·D-8·D-9 · `PREREG_POST9.md`(동결 `702f41b`) §0-1·§1·§4 ·
`PREDECISION_2026-09-24_post9.md` PD-1·2·3·4·11·12·21·23·24·27·31 · `INTAKE_2026-09-24_post9.md` §1·§5 · 원장 `30aed89`.
🔴 등급 이름 0 · 새 예측 0 · `adj_factor` 산술 0 · DB SELECT 만 · 라이브 채택 대상이 아니다.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

import run_selection
from run_selection import FEATS, PSEUDO, build_features
import run_selection_post6 as P6
from run_selection_post6 import aggs, feat_table, fmt, s1_row, stat_cal, stat_tdays
from run_selection_post7 import load_universe_day, pct, snapshot_tail, universe_raw_count, win20_bars
import run_selection_post8 as P8
from run_selection_post8 import (DROP_GUARD, MIN_N, N_DEGRADE, NEW4, NEW5, NEW6, NEW7, PUB_33, RAW_LO, REGIME,
                                 SEED, TRUNC_GUARD, UNIV_LO, UP15, W_CAL_POST4, W_TDAYS, WIN20, load_ext,
                                 load_raw_close, market_days, mixed_line, own_split, prior_flag, vintage)
from run_tests import DSN

BASE = Path(__file__).resolve().parent
ART = BASE / "selection_post9"
OUT: list[str] = []
OUT_NAME = "RESULTS_SELECTION_POST9_NUMBERS.md"

DB_UPTO = "2026-09-23"          # PD-1: 창 종료 = 발행 당일(수 · 거래일) 봉 «포함» · 전 축(WRC- 포함)
DB_UPTO_CUT = "2026-09-15"      # 대조 적재 = 최대 등록일(post8 `DB_UPTO_CUT` = 최대 등록일 09-11 과 같은 구성) — 판정에 안 씀
SWEEP_D1 = "2026-09-28 15:35:00"  # 09-23 봉의 D+1 sweep (PD-27 (마) 2)
PROBE_WIN = ("2026-08-07", "2026-09-23")  # PD-27 (다) 창 시작 08-07 ~ 창 종료
MGR = dict(run="2026-09-29 18:51:43 KST", rows_0923=2765, max_upd="2026-09-29 15:46:37.573889",
           min_upd="2026-09-29 15:45:21.506031", max_date="2026-09-29", rows_max=2765)  # probes_precalc_0929 옮김
P8.DB_UPTO = DB_UPTO            # post8 로더 2개가 호출 시점에 읽는 전역(이 프로세스 안에서만)

# ── 9번째 글 신규 5건 = 전부 `exact` (INTAKE_2026-09-24_post9 §1 · PD-4 · 원장 `30aed89`) ──────
NEW9 = [("삼미금속", "012210", "2026-09-04"), ("에스투더블유", "488280", "2026-09-10"),
        ("빛샘전자", "072950", "2026-09-14"), ("한국첨단소재", "062970", "2026-09-15"),
        ("한컴위드", "054920", "2026-09-15")]
FOLLOW9 = [("우리기술", "032820", "post8 #10 · 09-09 재명시")]
CHEOM = "한국첨단소재"           # PD-31 신고 줄 · 「첨단 제외」 = 인쇄만(재량 ⓐ · 판정 효과 0 · 계수 금지 ⓑ)
NEW8 = [(nm, c, d) for nm, c, d, _t in P8.EXACT8]      # post8 판정 표본 `exact` 4 (같은 스냅샷 재계산)
PD3_FLAG = {nm: 0 for nm, _c, _d in NEW9}               # PD-3 표(계산 전) — 대조용
PD12_PRIOR = {"삼미금속": 106, "에스투더블유": 110, "빛샘전자": 112, "한국첨단소재": 113, "한컴위드": 113}
PD27_X19 = {"빛샘전자": (19, 1), "한국첨단소재": (18, 2), "한컴위드": (18, 2)}   # PD-27 (바) `[D−19, D]` 걸침
CHEOM_LINE = ("*「한국첨단소재(062970): `[D−19, D]` = `[08-19, 09-15]` 안 거래정지 공시(08-26 → 08-28 해제) · "
              "로드창 안 거래정지(07-13~) · 액면병합 변경상장(08-06) · `adj_factor` NULL — 계단·패딩 판별 불가"
              "(인테이크는 가격·거래량 값을 읽지 않았다) · 판정 규칙 불변」*")

PUB = dict(P8.PUB)
PUB["post8_td5"] = (2, 4, 99.8, 47.1, 69.7)     # RESULTS_SELECTION_POST8_NUMBERS.md §2·§5 (09-24)
PUB_H = dict(P8.PUB_H)
PUB_H["post8"] = (4, 4)                         # 같은 문서 §3
S1_CUM_PRIOR = (24, 39)                         # 같은 문서 §2-1 누적(승계 셈법)
H_CUM_PRIOR = (17, 20)                          # 같은 문서 §3-1 판정 누적(post6~8)
NUP_SERIES = list(P8.NUP_SERIES) + [("post8", "75.5", "[62, 82]", "9.95")]
_PR9 = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").splitlines()
LIVE_BAN = (_PR9[38], _PR9[40])                 # `PREREG_POST9.md:39`·`:41` §0-1 문언 그대로(§8-3 #20)
assert LIVE_BAN[0].startswith("> *「🔴 **라이브 채택 금지.**") and LIVE_BAN[1].startswith("⇒ `PREREG_POST8.md:26`")
WINDOW_LINE = ("창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
               "전 축(`WRC-` 포함) · PD-1")


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    print(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def read_stamp(cur, art, fp):
    """D-9 ① — 이 지문을 «처음» 읽은 실행의 KST 시각. 같은 지문이면 파일을 고치지 않고 그 값을 다시 쓴다."""
    cur.execute("SELECT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'), current_setting('TimeZone')")
    now_kst, tz = cur.fetchone()
    p = art / "read_stamp.json"
    prev = None
    if p.exists():
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = None
    if prev and prev.get("fingerprint") == fp:
        return prev["first_read_kst"], True, now_kst
    art.mkdir(exist_ok=True)
    p.write_bytes((json.dumps(dict(fingerprint=fp, first_read_kst=now_kst, timezone=tz),
                              ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return now_kst, False, now_kst


def main():
    prev_out = P6.OUT
    P6.OUT = OUT          # `feat_table` 은 post6 모듈의 `say` 로 쓴다 ⇒ 버퍼를 이 실행으로 잇는다(원본 불변)
    try:
        return _main()
    finally:
        P6.OUT = prev_out


def _main():  # noqa: C901
    t0 = time.time()
    src = (BASE / "run_selection.py").read_text(encoding="utf-8")
    c17_line = next((i + 1 for i, ln in enumerate(src.splitlines()) if "where(prev_max.notna())" in ln), None)
    c17_ok = c17_line is not None
    c17_src = src.splitlines()[c17_line - 1].strip() if c17_ok else "(없음)"

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    v_probe = vintage(cur, *PROBE_WIN)
    v_lane = vintage(cur, RAW_LO, DB_UPTO)
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (DB_UPTO,))
    rows_upto = int(cur.fetchone()[0])
    snap_max, snap_rows = snapshot_tail(cur)
    fp = dict(max_date=str(snap_max), max_rows=int(snap_rows), probe=list(PROBE_WIN), probe_min_u=str(v_probe[2]),
              probe_max_u=str(v_probe[1]), probe_n=int(v_probe[3]), lane=[RAW_LO, DB_UPTO],
              lane_min_u=str(v_lane[2]), lane_max_u=str(v_lane[1]), lane_n=int(v_lane[3]), end_rows=rows_upto)
    first_read, reused, now_kst = read_stamp(cur, ART, fp)
    note(f"[D-9 ①] 이번 실행 벽시계(DB now) = {now_kst} · 본문 ① = {first_read} "
         f"({'같은 지문 재사용' if reused else '새 지문 — 새 시각 기록'}) · vintage now = {v_probe[0]}")

    df = build_features(load_ext(DB_UPTO))
    raw = load_raw_close()
    mdays = market_days(cur)
    sweep = dt.datetime.fromisoformat(SWEEP_D1)
    run_after_sweep = first_read >= SWEEP_D1[:19]
    run_after_maxupd = first_read > str(v_probe[1])[:19] and first_read > str(v_lane[1])[:19]
    min_ok = v_probe[2] >= sweep
    min_ok_lane = v_lane[2] >= sweep
    n9 = len(NEW9)

    say("# RESULTS_SELECTION_POST9_NUMBERS — 기계 생성 (수정 금지)\n")
    say(f"- 🔴 **{WINDOW_LINE}**")
    say(f"- 🔴 **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)** · "
        f"창 종료일 {DB_UPTO} 행수 **{rows_upto:,}**")
    say(f"- 🔴 **D-9 ① 쿼리 실행 시각(KST) = {first_read}**(이 지문을 이 스크립트가 «처음» 읽은 실행 · "
        "`selection_post9/read_stamp.json` · 같은 지문 재실행은 이 값을 다시 쓴다 · 🔴 `P9-스탬프통일` 적용 아님 — post10 부터)")
    say("- 🔴 라이브 채택 금지 — `PREREG_POST9.md` §0-1 문언 그대로(`:39`·`:41`):")
    say("")
    say(LIVE_BAN[0])
    say("")
    say(LIVE_BAN[1])
    say("")
    say("사전등록 `PREREG_SELECTION.md` §7(`9e53825`) + `PREREG_POST6.md` §2-1·§4 #1~#6·#11 + `PREREG_POST8.md`(동결 `04cd785` · "
        "2번째 구속 회차) + 🆕 `PREREG_POST9.md`(동결 `702f41b` · 첫 구속 회차) · 생성 `run_selection_post9.py` "
        "(`run_selection_post8.py` 승계 · 원본 불변)")
    say("계산 «전» 동결 = `PREDECISION_2026-09-24_post9.md` · `INTAKE_2026-09-24_post9.md` · `LABELS_2026-09-24_post9.md` · "
        "정오표 `ERRATA_2026-09-29_post9_intake.md` · 원장 `30aed89`(post9 6행/23레그 · 인코딩 `9d3bbe1`)")
    say("")
    say("## §0. 실행 환경 · 동결 규약 (값을 보기 «전»에 고정)\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| DB | `kis_template.daily_prices` — **SELECT 만** |")
    say(f"| 유니버스 창 | {UNIV_LO} ~ **{DB_UPTO}** (`market_cap > 0` ∧ `close > 0` ∧ 의사티커 제외) |")
    say(f"| 유니버스 | **{df.stock_code.nunique():,}종목** · **{df.date.nunique()}거래일** · 최신 봉 **{df.date.max().date()}** |")
    say(f"| 판정 창 | 동결 문언 `[D-4, D]` = **거래일 {W_TDAYS}일** (`PREREG_SELECTION.md` §2) · 대조 창 달력 {W_CAL_POST4}일(판정에 안 씀) |")
    say(f"| 🔴 판정 분모 | **신규 ∧ `exact` = {n9}건** ({' · '.join(r[0] for r in NEW9)} · PD-4 1번) |")
    say("| 민감도 분모 | `approx` **0건** · `none`(신규) 0 · `after` 0 ⇒ **정밀도 갈래 없음**(PD-4 · PD-21) |")
    say(f"| 축 밖 | 후속 **{len(FOLLOW9)}건**({' · '.join(r[0] for r in FOLLOW9)} — PD-2 · `none`) |")
    say(f"| 시드 · NREP | **{SEED}** · `NREP = {run_selection.NREP:,}`(상수) — 🔴 **귀무를 돌리지 않는다** ⇒ 이 문서에 「p 값」은 없다 |")
    say(f"| C-17 반영 | {'✅' if c17_ok else '🔴 **미반영 ⇒ 산출물 무효**'} `run_selection.py:{c17_line}` — `{c17_src}` |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1 · `PREREG_POST9.md` §0-1) |")
    say("")
    say("### 0-1. `D-9` 읽은 시각 · 빈티지 박제 (`PREREG_POST8.md` §9 (나)1·2 · PD-27 (마)(바))\n")
    say("| # | 의무 | 이 실행의 재측 | 관리자 실측(옮겨 적음 · 대조) |")
    say("|---|---|---|---|")
    say(f"| ① | 쿼리 실행 시각(KST) | **{first_read}**(스탬프) · 기계 검사: **> {SWEEP_D1}(D+1 sweep) = "
        f"{'예' if run_after_sweep else '🔴 아니오'}** · **> 창 구간 `max(updated_at)` = "
        f"{'예' if run_after_maxupd else '🔴 아니오'}** · 🔴 post8 자리(산문 §0 · stdout)도 유지 | {MGR['run']} |")
    say(f"| ② | 창 구간 `max(daily_prices.updated_at)` | `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` **{v_probe[1]}** · "
        f"적재 창 `[{RAW_LO}, {DB_UPTO}]` **{v_lane[1]}** | {MGR['max_upd']} |")
    say(f"| ③ | 「09-23 봉은 D+1(09-28) sweep 이후 읽음」 | **09-23 봉은 D+1(09-28) sweep 이후 읽음** "
        f"(① 기계 검사 {'예' if run_after_sweep else '🔴 아니오'}) | 같음 |")
    say(f"| ④ | 창 구간 `min(updated_at)` ≥ 09-28 15:35 (기록 · 통과 조건 아님) | `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` "
        f"**{v_probe[2]} ≥ 09-28 15:35: {'예' if min_ok else '아니오'}** · 적재 창 {v_lane[2]} ≥ 09-28 15:35: "
        f"{'예' if min_ok_lane else '아니오'} | {MGR['min_upd']} ≥ 09-28 15:35: 예 |")
    say("| ⑤ | `P8-혼합빈티지신고` | §11 (걸침 창마다 한 줄 + 「전부 경계 후」 추가 줄) | PD-27 (바) |")
    say("")
    say("- 🔴 **`updated_at` 은 sweep 이 전 표를 일괄 갱신한 값**이라 빈티지 «증거»가 아니라 **읽은 시각의 기록**이다"
        "(PD-27 (라) · `P-3` 판별력 0 — 「통과」로 인용하지 않는다) · 「정규장만」 갈래 없음(§9 (나)4) · `adj_factor` 산술 **0**.")
    say(f"- 창 구간 행수: `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` **{v_probe[3]:,}** · 적재 창 **{v_lane[3]:,}**.")
    say("")
    say("### 0-2. `D-3` · `D-6` · `D-8` · 🆕 `P9-공통독법` · `P9-행단위` 의무 줄\n")
    say(f"- **`D-3`**: *「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 {n9} / `approx` 포함 분모 {n9}」* "
        "(PD-21 구성 예고 「없음」과 일치 · `approx` 0).")
    say("- 🆕 **`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)** (`PREREG_POST9.md` §1 (나)3 · 독법 B 병기 자리 없음).")
    say("- **`D-6`**: `n_up` 표준편차는 **`ddof=1`(표본)** 이다(`PREREG_POST8.md` §6 SSOT) · 문턱은 **중앙값 ≥ 30** 이지 sd 가 아니다.")
    say("- **`D-8`** · 🆕 **`P9-행단위`: 해당 없음** — 이 레인은 `prog_ver` 를 공변량으로 쓰지 않는다(수준 목록 없음 · "
        "*「부호 갈림 검사: 통계량 정의 없음(기록만)」* 대상도 아님) · post9 `prog_ver` = `missing`(6행) — 🔴 분모에서 빼지 않는다"
        "(§8 (나)4) · `P9-결측분리` 는 post10 부터(미적용).")
    say("- `P9-WRC누적분모`·`P9-갈래게이트인쇄전용`·`P9-수집증거`: 해당 없음(다른 레인).")
    say("🔴 **값 보고 규칙을 바꾸지 않는다** · 새 예측 0(`PREREG_POST6.md` §7-B #11) · 등급 이름 0(§6 단계 · PD-16).")
    if not c17_ok:
        say("🔴🔴 **C-17 미반영 — `SEL-S3` 판정은 무효다.**")
    say("")

    # ── §1. 표본 ────────────────────────────────────────────────────────────
    say(f"## §1. 표본 — 9번째 글 **신규 {n9}건 = 판정 분모 `exact` {n9}건** (후속 1건은 등록일 축 밖 · PD-2)\n")
    say(f"| # | 종목 | 코드 | 등록일 | 정밀도 | `[D-19, D]` 봉수(등록일 «포함») | 창 `[D-4, D]` 봉수 | "
        f"창 안 DB 행수(`date <= {DB_UPTO}`) | DB 최초일 | 등록일 봉 제도 경계 후? |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    win20 = {}
    for i, (nm, code, reg) in enumerate(NEW9, 1):
        cur.execute("SELECT count(*) FILTER (WHERE date <= %s), min(date) FROM daily_prices WHERE stock_code=%s",
                    (DB_UPTO, code))
        n_all, mn = cur.fetchone()
        nb20, wlen = win20_bars(cur, mdays, code, reg)
        win20[nm] = (nb20, wlen)
        _st, nb5 = stat_tdays(df, code, pd.Timestamp(reg), W_TDAYS)
        say(f"| {i} | {nm} | {code} | {reg} | `exact` | **{nb20}/{wlen}** | {nb5} | {n_all} | {mn} | "
            f"{'🟡 예(기록)' if reg >= REGIME else '아니오'} |")
    n_after = sum(1 for _n, _c, d in NEW9 if d >= REGIME)
    say("")
    say(f"🔁 **후속 {len(FOLLOW9)}건**(" + " · ".join(f"{nm} `{c}` {t}" for nm, c, t in FOLLOW9)
        + ")은 **등록일 축 분모에서 제외**한다(PD-2 · 이중계상 금지 · «정의»로 빠진다).")
    say(f"- 기록: 등록일 서로 다른 날 **{len(set(d for _n, _c, d in NEW9))}**(09-15 에 2건 · 건 단위 인쇄 · PD-4) · "
        f"등록일 봉이 제도 경계(09-14) «후»인 건 **{n_after}/{n9}**(PD-4 · PD-27 (바) — 신고 의무 대상 밖 · 재량 인쇄).")
    say(f"- 🔴 **PD-31 신고 줄**(확인 5 · 규칙·갈래 신설 0 · 현행대로 계산): {CHEOM_LINE} — 이 레인에서 닿는 자리 = "
        "60행 계열 특징(`f5`·`f6`·`f9` 등 · 로드창 07-13~08-06 정지 + 08-06 병합 포함) · `[D-19, D]` 절단 가드 창.")
    say("")
    say("### 1-1. 커버리지 — 축별로 «다른 수»다 (PD-11 · 의무 산술 인쇄)\n")
    say("| 축 | 필요한 자료 | 측정 가능 | 측정 불가 | 비율 | 문턱 1/3 |")
    say("|---|---|---|---|---|---|")
    say(f"| **이 레인**(`SEL-`) | `daily_prices` | **{n9}/{n9}** | 0 | 0.0% | 미발동 |")
    say("| (참고 · PD-11) `SEC-` | `stock_industry` 섹터코드 | 5/5 | 0 | 0.0% | 미발동 |")
    say("| (참고 · PD-11) `S5` | `dart_financials_asfiled` PIT | 행 보유 5/5(판정 가능 확정은 S5 레인) | 0 | — | — |")
    say("| (참고 · PD-11) `WRC-` | `fill_n >= 2` ∧ 서로 다른 값 레그 >= 3 | 0/5 | — | — | 단독 0 · 누적으로 판정 |")
    say("")

    # ── §2. SEL-S1 ──────────────────────────────────────────────────────────
    say("## §2. `SEL-S1` — 등록일 **종가** 전일대비 >= +15% (동결 문언 · 🔴 기각 «유지»)\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 종가 | **종가 등락** | 문턱 충족 |")
    say("|---|---|---|---|---|---|")
    s1_hits, s1_rows = 0, []
    for nm, code, reg in NEW9:
        r = s1_row(raw, code, reg)
        s1_rows.append((nm, reg, r))
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | (데이터 없음) |")
            continue
        ok = r["ret_c"] >= 0.15
        s1_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['close']:,.0f} | **{pct(r['ret_c'])}** | {'✅' if ok else '❌'} |")
    s1_pass = s1_hits * 2 >= n9
    say(f"\n⇒ **이번 판정 분모 = {s1_hits}/{n9} = {s1_hits/n9*100:.1f}%** · 문턱 **>= 절반**(= {-(-n9//2)}/{n9}) ⇒ "
        f"표본 자체로는 **{'문턱 위' if s1_pass else '문턱 아래'}**")
    say("")
    say("🔴 **판정 = ❌ 「기각 유지」.** `PREREG_POST6.md` §2-1 — *「6번째 글에서도 «같은 문턱(+15% 종가, >= 절반)»으로 계속 잰다. "
        "**부활 경로는 없다.**」* ⇒ **문턱을 낮추지도, 이번 표본으로 기각을 무르지도 않는다.**")
    say("🟡 **문언 모호 지점(인쇄 의무)**: 이번 표본이 문턱 «위»인데 동결 문언은 「부활 경로 없음」이다 — 양쪽 다 인쇄하고 새 결정을 "
        "만들지 않는다." if s1_pass else "🟢 이번 표본은 문턱 아래다 — 동결 문언(「기각 유지」)과 같은 방향이라 모호 지점이 없다.")
    say("")

    def s1_count(items):
        rr = [s1_row(raw, c, d) for _n, c, d in items]
        return (sum(1 for r in rr if r and r["ret_c"] >= 0.15), sum(1 for r in rr if r),
                sum(1 for r in rr if r and r["ret_h"] >= 0.15))
    rcs = [(k, s1_count(it)) for k, it in (("post4", NEW4), ("post5", NEW5), ("post6", NEW6), ("post7", NEW7),
                                          ("post8", NEW8))]
    rc = dict(rcs)
    say("### 2-1. `SEL-S1` 누적 — 발표값(승계 셈법) + 같은 스냅샷 재계산 나란히\n")
    say("| 글 | S1 발표값 | S1 **이 스냅샷 재계산** | 일치? | 분모 규약 |")
    say("|---|---|---|---|---|")
    say(f"| 1~3번째(33건 중 등록일 특정 7건) | {PUB_33[0]} | —(재계산 대상 아님) | — | 🔴 또 다른 창 |")
    for lbl, key, k2, nn in (("4번째 6건", "post4_cal10", "post4", 6), ("5번째 6건", "post5_td5", "post5", 6),
                             ("6번째 10건", "post6_td5", "post6", 10), ("7번째 `exact` 6건", "post7_td5", "post7", 6),
                             ("8번째 `exact` 4건", "post8_td5", "post8", 4)):
        ph, c = PUB[key][0], rc[k2]
        say(f"| {lbl} | {ph}/{nn} = {ph/nn*100:.1f}% | {c[0]}/{c[1]} = {c[0]/max(c[1], 1)*100:.1f}% | "
            f"{'✅' if (c[0], c[1]) == (ph, nn) else '🔴 **다름**'} | 신규 = `exact`"
            + ("(post7·8 은 신규 ≠ `exact`)" if k2 in ("post7", "post8") else "") + " |")
    say(f"| **9번째 `exact` {n9}건** | — | **{s1_hits}/{n9} = {s1_hits/n9*100:.1f}%** | — | 신규 {n9} = `exact` {n9} |")
    cum_h, cum_n = S1_CUM_PRIOR[0] + s1_hits, S1_CUM_PRIOR[1] + n9
    rh = 6 + sum(c[0] for _k, c in rcs) + s1_hits
    rn = 7 + sum(c[1] for _k, c in rcs) + n9
    say(f"| **누적**(승계 셈법 = 발표값 {S1_CUM_PRIOR[0]}/{S1_CUM_PRIOR[1]} + 이번) | **{cum_h}/{cum_n} = "
        f"{cum_h/cum_n*100:.1f}%** | 재계산 셈법(33건 열 6/7 + 재계산 5글 + 이번) = **{rh}/{rn} = {rh/rn*100:.1f}%** | — | — |")
    say("")
    say("⚠️ S1 은 창을 안 쓴다(등락률) · 🔴 **표본이 매번 통째로 바뀌므로 「같은 검정의 반복」이 아니다.**")
    say("")

    # ── §3. P6-S1h ──────────────────────────────────────────────────────────
    say("## §3. `P6-S1h` — 등록일 **고가** 전일대비 >= +15% (`PREREG_POST6.md` §2-1 · §4 #2)\n")
    say("> 🔴 **단조 완화 축이다 — 통과는 증거가 아니다**(`high >= close` 항등 ⇒ `P6-S1h` 비율 >= `SEL-S1` 비율이 «구성상» 성립). "
        "증거는 ① 비율 < 1/2 ⇒ 불성립 ② `P6-S1h-N` 미발동 두 방향뿐이다(§7).\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 고가 | **고가 등락** | 문턱 충족 |")
    say("|---|---|---|---|---|---|")
    h_hits = 0
    for nm, reg, r in s1_rows:
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | (데이터 없음) |")
            continue
        ok = r["ret_h"] >= 0.15
        h_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['high']:,.0f} | **{pct(r['ret_h'])}** | {'✅' if ok else '❌'} |")
    h_pass = h_hits * 2 >= n9
    say(f"\n⇒ **`P6-S1h` = {h_hits}/{n9} = {h_hits/n9*100:.1f}%** · 문턱 **>= 1/2** · 최소 n = {MIN_N} ⇒ "
        + ("**🟡 문턱 충족 — 단, 단조 완화 축이라 «증거 아님»**" if h_pass
           else "**❌ 불성립(⛔ 경로 발동 — 완화 축에서도 떨어졌다)**"))
    say("")
    say("### 3-1. 🔬 발표값 · 같은 스냅샷 재계산 — post4·post5 는 탐색적 표기 전용(누적 분모에 넣지 않는다)\n")
    say("| 글 | 고가 +15% 발표값 | **이 스냅샷 재계산** | 일치? | 지위 |")
    say("|---|---|---|---|---|")
    for lbl, key, st in (("4번째 6건", "post4", "소급 · 탐색"), ("5번째 6건", "post5", "소급 · 탐색"),
                         ("6번째 10건", "post6", "판정"), ("7번째 `exact` 6건", "post7", "판정"),
                         ("8번째 `exact` 4건", "post8", "판정")):
        ph, c = PUB_H[key], rc[key]
        say(f"| {lbl} | {ph[0]}/{ph[1]} = {ph[0]/ph[1]*100:.1f}% | {c[2]}/{c[1]} = {c[2]/max(c[1], 1)*100:.1f}% | "
            f"{'✅' if (c[2], c[1]) == ph else '🔴 **다름**'} | {st} |")
    say(f"| **9번째 `exact` {n9}건 — 판정 대상** | — | **{h_hits}/{n9} = {h_hits/n9*100:.1f}%** | — | 판정 |")
    hc_h, hc_n = H_CUM_PRIOR[0] + h_hits, H_CUM_PRIOR[1] + n9
    say(f"| **판정 누적**(post6~ · 발표값 {H_CUM_PRIOR[0]}/{H_CUM_PRIOR[1]} + 이번) | — | **{hc_h}/{hc_n} = "
        f"{hc_h/hc_n*100:.1f}%** | — | 🔴 누적은 **기록**(누적 문턱 없음) |")
    say("")
    say("🔴 **`SEL-S1` 의 기각을 무르지 않는다** — `P6-S1h` 통과를 「S1 이 측정자만 틀렸던 것」으로 읽지 않는다(§2-1 ①).")
    say("")

    # ── §4. 특징 백분위 ─────────────────────────────────────────────────────
    say("## §4. 특징 9개 백분위 (창 안 일별 백분위의 «최댓값»)\n")

    def rows_t(items, dff=df):
        return [(nm, c, reg) + stat_tdays(dff, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in items]
    rows9_t = rows_t(NEW9)
    rows9_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg in NEW9]
    rows8_t, rows7_t, rows6_t = rows_t(NEW8), rows_t(NEW7), rows_t(NEW6)
    rows5_t, rows4_t = rows_t(NEW5), rows_t(NEW4)
    rows4_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg in NEW4]
    feat_table(f"4-1. 9번째 글 `exact` {n9}건 — **판정 창**(거래일 {W_TDAYS}일)", rows9_t)
    feat_table(f"4-2. 9번째 글 `exact` {n9}건 — 대조 창(달력 {W_CAL_POST4}일)", rows9_c)
    feat_table(f"4-3. 8번째 글 `exact` 4건 — 판정 창 · **이 스냅샷 재계산**", rows8_t)
    feat_table(f"4-4. 7번째 글 `exact` 6건 — 판정 창 · **이 스냅샷 재계산**", rows7_t)
    feat_table(f"4-5. 6번째 글 10건 — 판정 창 · **이 스냅샷 재계산**", rows6_t)
    feat_table(f"4-6. 5번째 글 6건 — 판정 창 · **이 스냅샷 재계산**", rows5_t)
    feat_table(f"4-7. 4번째 글 6건 — 판정 창 · **이 스냅샷 재계산**", rows4_t)
    feat_table(f"4-8. 4번째 글 6건 — 대조 창(달력 {W_CAL_POST4}일) · **이 스냅샷 재계산**", rows4_c)

    # ── §5. S2·S3·S4 판정 ───────────────────────────────────────────────────
    a9t, a9c = aggs(rows9_t), aggs(rows9_c)
    ag = {"post8": aggs(rows8_t), "post7": aggs(rows7_t), "post6": aggs(rows6_t), "post5": aggs(rows5_t),
          "post4": aggs(rows4_t), "post4c": aggs(rows4_c)}
    s2, s3, s4, s3_n, s3_nan = a9t
    say(f"## §5. `SEL-S2`·`SEL-S3`·`SEL-S4` 판정 (판정 창 = 거래일 {W_TDAYS}일 · 분모 = `exact` {n9})\n")
    say(f"| 예측 | 문언(동결) | 문턱 (출처) | 최소 n | **이번(`exact` {n9}건)** | 판정 | ⛔ 판정 불가 조건 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| **`SEL-S2`** | `거래대금/시총` 백분위 중앙 | >= 95 (값만 기록) · `PREREG_SELECTION.md` §7 | {MIN_N} | **{fmt(s2)}** | "
        f"{'✅ 충족' if s2 >= 95 else '🟡 미달'} | 판정 건 < 3 (이번 {n9} ⇒ 미발동) |")
    say(f"| **`SEL-S3`** | `60일 최고종가 갱신` 백분위 중앙 | **< 90** (핵심·위반 시 기각) · `PREREG_SELECTION.md` §7 | {MIN_N} | "
        f"**{fmt(s3)}** (분모 {s3_n}/{n9} · NaN {s3_nan}) | {'✅ 지지' if s3 < 90 else '❌ 기각'} | 판정 건 < 3 · "
        f"C-17 수정 전이면 무효 ⇒ {'반영 ✅' if c17_ok else '🔴 미반영'} |")
    say(f"| **`SEL-S4`** | `시가총액` 백분위 중앙 | 40~80 (값만 기록) · `PREREG_SELECTION.md` §7 | {MIN_N} | **{fmt(s4)}** | "
        f"{'✅ 구간 내' if 40 <= s4 <= 80 else '🟡 구간 밖'} | 판정 건 < 3 (이번 {n9} ⇒ 미발동) |")
    same_dir = ((a9c[0] >= 95) == (s2 >= 95) and (a9c[1] < 90) == (s3 < 90) and (40 <= a9c[2] <= 80) == (40 <= s4 <= 80))
    say(f"\n대조 창(달력 {W_CAL_POST4}일) 값: S2 **{fmt(a9c[0])}** · S3 **{fmt(a9c[1])}** · S4 **{fmt(a9c[2])}** — 판정 창과 "
        f"{'**같은 방향**' if same_dir else '🔴 **다른 방향 ⇒ 창 의존**'}. 🔴 **판정은 동결 문언(거래일 5일)으로 선다.**")
    say("")
    say("### 5-1. 누적 — 🔴 **열마다 창·분모 규약·스냅샷이 다르다. 「N연속 재현」이라고 쓰지 않는다.**\n")
    say("| 예측 | 1~3번째(33건) | 4번째 발표(달력10) | 4번째 재계산 | 5번째 발표 | 5번째 재계산 | 6번째 발표 | 6번째 재계산 | "
        f"7번째 발표 | 7번째 재계산 | 8번째 발표 | 8번째 재계산 | **9번째**(`exact` {n9}) |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k, lbl in ((2, "S2"), (3, "S3"), (4, "S4")):
        j = k - 2
        say(f"| {lbl} | {PUB_33[k - 1]} | {PUB['post4_cal10'][k]:.1f} | {fmt(ag['post4'][j])} | {PUB['post5_td5'][k]:.1f} | "
            f"{fmt(ag['post5'][j])} | {PUB['post6_td5'][k]:.1f} | {fmt(ag['post6'][j])} | {PUB['post7_td5'][k]:.1f} | "
            f"{fmt(ag['post7'][j])} | {PUB['post8_td5'][k]:.1f} | {fmt(ag['post8'][j])} | **{fmt(a9t[j])}** |")
    say("")
    say("⚠️ 「33건」 열은 잣대가 또 다르다(달력 6일 + 최대 15거래일 · 방향 참고만) · 🔴 `PREREG_POST6.md` §2-1 이 금지한 표현 "
        "「N연속 재현」을 쓰지 않는다 — 표본·스냅샷·측정 장치(C-17)·분모 규약이 움직였고, 이번엔 등록일 봉 3/5 가 제도 경계 «후»다.")
    say("")
    say("### 5-2. 🔴 재계산 대조 — 원 발표값 ↔ 이 스냅샷 재계산\n")
    say("| 표본 | 창 | 예측 | 원 발표값 | 재계산 | 차 | 일치? | 비고 |")
    say("|---|---|---|---|---|---|---|---|")
    for tag, pubkey, agg, cw in (("4번째 글", "post4_td5", ag["post4"], f"거래일{W_TDAYS}"),
                                 ("4번째 글", "post4_cal10", ag["post4c"], f"달력{W_CAL_POST4}"),
                                 ("5번째 글", "post5_td5", ag["post5"], f"거래일{W_TDAYS}"),
                                 ("6번째 글", "post6_td5", ag["post6"], f"거래일{W_TDAYS}"),
                                 ("7번째 글", "post7_td5", ag["post7"], f"거래일{W_TDAYS}"),
                                 ("8번째 글", "post8_td5", ag["post8"], f"거래일{W_TDAYS}")):
        for k, lbl in ((2, "S2"), (3, "S3"), (4, "S4")):
            pub, now = PUB[pubkey][k], agg[k - 2]
            d = None if now is None or now != now else now - pub
            hit = d is not None and abs(d) < 0.05
            extra = "—"
            if lbl == "S3" and not hit:
                extra = (f"🔴 `f9` NaN **{agg[4]}건**이 분모에서 빠졌다" if agg[4] > 0
                         else "🔴 C-17 효과가 «아니다»(`f9` NaN 0) — 스냅샷/개별 백분위 이동")
            say(f"| {tag} | {cw} | {lbl} | {pub:.1f} | {fmt(now)} | {'—' if d is None else f'{d:+.1f}'} | "
                f"{'✅ 일치' if hit else '🔴 **다름**'} | {extra} |")
    say("")
    say("🔴 **과거 산출물을 다시 재지 않는다**(`PREREG_POST6.md` §5-1 5번) — 값이 달라져도 post4~post8 판정은 그대로 둔다(「나란히 인쇄」 의무 이행).")
    say("")
    say("### 5-3. `approx` 갈래 — **대상 없음**(`approx` 0 · PD-4 · PD-21)\n")
    say("- 🆕 **`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)** — `exact` 갈래와 `approx` 포함 갈래가 같은 표본"
        f"(n {n9} = {n9})이라 갈릴 수 없다 · 독법 B 병기 자리 없음.")
    say("- `P6-W10`(무작위 «창» 귀무 · §1-4 창 규약 용도)은 `run_regday_post9.py` 소관이고 이번엔 창 규약 **미발동**(PD-4 2) · "
        "🔴 `TV` 축의 `P6-W10` 미룸(PD-6)과 한 수로 합치지 않는다.")
    say("")

    # ── 유니버스 n_up ────────────────────────────────────────────────────────
    ucache = {}

    def nup_of(d):
        if d not in ucache:
            ucache[d] = (universe_raw_count(cur, d), load_universe_day(cur, d))
        raw_n, rowsu = ucache[d]
        up = [(sc, float(tv) / float(mc)) for sc, hi, _cl, tv, mc, pc_, _pdt in rowsu
              if hi is not None and pc_ and float(hi) >= float(pc_) * UP15 and tv is not None and mc]
        return raw_n, rowsu, up

    # ── §6. f9 원값·NaN ─────────────────────────────────────────────────────
    say("## §6. 🔴 `f9_newhigh` 원값·NaN — C-17 (`PREREG_POST6.md` §4 #5)\n")
    say("| 종목 | 창 봉수 | `f9` 원값(창 최대) | 갱신일 | 등록일 당일도 갱신? | `f9` 백분위 | 로드창 선행 특징 행수 | 상태 |")
    say("|---|---|---|---|---|---|---|---|")
    n_raw1 = n_nan = 0
    priors = {}
    for nm, code, reg, st, nb in rows9_t:
        m = df[(df.stock_code == code) & (df.date <= pd.Timestamp(reg))].tail(W_TDAYS)
        raw_v = m["f9_newhigh"].max() if not m.empty else None
        priors[nm] = int(((df.stock_code == code) & (df.date < pd.Timestamp(reg))).sum())
        is_nan = raw_v is None or raw_v != raw_v
        n_nan += int(is_nan)
        n_raw1 += int((not is_nan) and raw_v == 1.0)
        days = [str(d.date()) for d, v in zip(m.date, m.f9_newhigh) if v == 1.0]
        onD = "✅" if (len(m) and m.f9_newhigh.iloc[-1] == 1.0) else "—"
        pv = None if st is None else st["f9_newhigh"]
        say(f"| {nm} | {nb} | {'🔴 **NaN**' if is_nan else f'{raw_v:.0f}'} | {'·'.join(days) if days else '—'} | {onD} | "
            f"{'🔴 **NaN**' if (pv is None or pv != pv) else f'{pv:.1f}'} | {priors[nm]} | "
            f"{'🔴 **C-17 규약으로 `SEL-S3` 분모에서 빠진다**' if is_nan else '—'} |")
    say(f"\n⇒ **`f9` 원값 = 1 인 건 {n_raw1}/{n9}** · **NaN {n_nan}/{n9}** ⇒ **`SEL-S3` 중앙값 분모 = {s3_n}/{n9}**")
    say("")
    say("### 6-1. 🔴 C-17 대상 **0 예고**(PD-12) 확인\n")
    rawp = {}
    for nm, code, reg in NEW9:
        cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code=%s AND date >= %s AND date < %s", (code, UNIV_LO, reg))
        rawp[nm] = int(cur.fetchone()[0])
    cur.execute("SELECT min(date) FROM daily_prices WHERE stock_code='488280'")
    s2w_first = cur.fetchone()[0]
    pd12_ok = n_nan == 0 and rawp == PD12_PRIOR
    say("| 항목 | 값 | PD-12 예고 |")
    say("|---|---|---|")
    say("| 로드창(04-01~) 안 등록일 «직전» **DB 원시 행** | " + " · ".join(f"{k} {v}" for k, v in rawp.items())
        + " | " + " · ".join(f"{k} {v}" for k, v in PD12_PRIOR.items()) + " (전건 ≥ 106) |")
    say("| 같은 구간 **특징 계산 행**(`market_cap > 0` ∧ `close > 0`) | " + " · ".join(f"{k} {v}" for k, v in priors.items())
        + " | (예고 없음) |")
    say(f"| 에스투더블유 `488280` DB 첫 봉 | **{s2w_first}** | 2025-09-19(🔴 DB 첫 봉 ≠ 상장일 · PD-11) |")
    say(f"| `f9_newhigh` NaN(`exact`) | **{n_nan}건** | **0** |")
    say("")
    say("- " + ("🟢 PD-12 예고와 **계산이 일치** ⇒ C-17 NaN 규약 대상 **0** · `SEL-S3` 분모 = " f"{s3_n}/{n9}."
                if pd12_ok else "🔴 PD-12 예고와 **다르다** — 그 사실을 그대로 적고 규약을 고치지 않는다."))
    thin = [k for k, v in priors.items() if v < 60]
    say("- " + (f"🔴 특징 계산 행 60 미만: {' · '.join(thin)} — 짧은 계열로 계산됐다(기록 · 규약 불변)." if thin
                else "🟢 특징 계산 행이 전건 60 이상 — post8 액스비스 같은 «짧은 특징 계열» 없음."))
    say(f"- 🔴 **PD-31**: {CHEOM} 60행 계열 특징 창은 로드창 안 거래정지(07-13~)·액면병합(08-06)을 포함한다 — `adj_factor` NULL 이라 "
        "계단을 판별할 수 없다 · 이 레인은 가격을 조정하지 않는다(규칙 불변 · 신고만).")
    say("- 🔴 한계: C-17 은 「완전 결측」만 잡고 「부분 결손」은 못 잡는다 · 「60봉」 = DB 에 남은 60행(`market_cap > 0`).")
    say("")

    # ── §7. P6-S1h-N + §5-2 유니버스 5열 ────────────────────────────────────
    say("## §7. `P6-S1h-N` (희소성 대칭 단언) + §5-2 유니버스 5열\n")
    say("> 문턱 **`n_up` 중앙 >= 30 ⇒ `P6-S1h` 는 「선정 규칙」으로 인용 금지** — 출처 `PREREG_D1_OOS.md` §4 **N2**.\n")
    say("| 종목 | 등록일 | `universe_mcap` | `universe_test` | `dropped` | `drop_rate` | `prev_bar_date` | **`n_up`** | "
        "본인이 `n_up` 안에? | `n_up` 안 `f1` 순위 | 백분위 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    nups, drops, ranks = [], [], []
    for nm, code, reg in NEW9:
        raw_n, rowsu, up = nup_of(reg)
        drop = raw_n - len(rowsu)
        rate = drop / raw_n if raw_n else float("nan")
        pds = sorted(set(str(r[6]) for r in rowsu if r[6] is not None))
        j = mdays.index(reg) if reg in mdays else None
        mkt_prev = mdays[j - 1] if j else "—"
        pd_s = pds[0] if len(pds) == 1 else f"{min(pds)}~{max(pds)} ({len(pds)}종) · 시장 직전 거래일 **{mkt_prev}**"
        nup = len(up)
        nups.append((nm, reg, nup))
        drops.append((reg, rate))
        up_sorted = sorted(up, key=lambda x: (-x[1], x[0]))
        inset = [k for k, (sc, _v) in enumerate(up_sorted) if sc == code]
        if inset:
            rk = inset[0] + 1
            pctv = (nup - rk) / (nup - 1) * 100 if nup > 1 else 100.0
            rk_s, pct_s, in_s = f"**{rk} / {nup}**", f"{pctv:.1f}", "✅"
            ranks.append((nm, rk, nup, pctv))
        else:
            rk_s, pct_s, in_s = "—", "—", "🔴 **아니다**"
            ranks.append((nm, None, nup, None))
        rate_s = f"🔴 **{rate*100:.2f}%**" if rate >= DROP_GUARD else f"{rate*100:.2f}%"
        say(f"| {nm} | {reg} | {raw_n:,} | {len(rowsu):,} | {drop:,} | {rate_s} | {pd_s} | **{nup}** | {in_s} | {rk_s} | {pct_s} |")
    say("")
    bad_days = sorted(set((d, r) for d, r in drops if r >= DROP_GUARD))
    say((f"🔴 **`drop_rate >= 1%` 인 등록일 {len(bad_days)}건**: " + " · ".join(f"{d} ({r*100:.2f}%)" for d, r in bad_days)
         + " ⇒ 그날의 `n_up` 을 다른 날과 «직접 비교하지 말 것»(§5-2 가드).") if bad_days else
        f"🟢 **`drop_rate >= 1%` 인 등록일 0건**(최대 {max(r for _d, r in drops)*100:.2f}%) ⇒ §5-2 가드 **미발동**.")
    say("🔴 편향 방향(§5-2): 빠진 종목은 검정에서 빠진다 — *「빼면 더 커질 뿐 작아지지 않는다」* ⇒ `n_up` 결론은 강건 · 순위 진술은 과대일 수 있다.")
    say("")
    nv = [x[2] for x in nups]
    n_med = float(np.median(nv))
    n_sd = float(np.std(nv, ddof=1))
    degrade = n_med >= N_DEGRADE
    say("### 7-1. `P6-S1h-N` 판정\n")
    say("| 통계량 | 값 |")
    say("|---|---|")
    say(f"| `n_up` 중앙값 | **{n_med:.1f}** |")
    say(f"| `n_up` 범위 | **[{min(nv)}, {max(nv)}]** |")
    say(f"| `n_up` 표준편차(표본 · `ddof=1` · `PREREG_POST8.md` §6 SSOT) | **{n_sd:.2f}** |")
    say(f"| 문턱 | **>= {N_DEGRADE} ⇒ 인용 금지 강등** — 🔴 sd 는 문턱이 아니다 |")
    say("| **판정** | **" + ("🔴 발동 — `P6-S1h` 를 「선정 규칙」으로 «인용 금지»(판별력 없음으로 강등)" if degrade
                            else "🟢 미발동 — 희소성 단언이 살아 있다") + "** |")
    say("")
    say("계열 실측 대조(각 판 발표값 · sd `ddof=1`): " + " · ".join(f"{p} **중앙 {m} · 범위 {r} · sd {s}**" for p, m, r, s in NUP_SERIES)
        + f" ⇒ 이번 중앙 **{n_med:.1f}** · sd **{n_sd:.2f}**.")
    say("")
    say("### 7-2. 저자 종목의 `n_up` 안 위치\n")
    say("| 종목 | `n_up` 안 순위 | `n_up` | 백분위 |")
    say("|---|---|---|---|")
    for nm, rk, nup, pctv in ranks:
        say(f"| {nm} | {'**' + str(rk) + '위**' if rk else '🔴 집합 밖'} | {nup} | {'—' if pctv is None else f'{pctv:.1f}'} |")
    top1 = [nm for nm, rk, _n, _p in ranks if rk == 1]
    outset = [nm for nm, rk, _n, _p in ranks if rk is None]
    say(f"\n⇒ **1위인 건 {len(top1)}/{n9}**{(' — ' + ' · '.join(top1)) if top1 else ''} · **`n_up` 집합 «밖»인 건 "
        f"{len(outset)}/{n9}**{(' — ' + ' · '.join(outset)) if outset else ''}")
    if len(top1) < n9:
        say("🔴 **저자 종목이 1위가 아닌 건이 있다** ⇒ ***「어느 급등주냐」는 여전히 미해결***(`PREREG_POST6.md` §2-1 의무 문구).")
    say("")
    say("### 7-3. 죽은 가드 실측 점검 (`PREREG_POST6.md` §7-B #10)\n")
    say(f"`n_up` 이 **{len(set(nv))}개의 서로 다른 값** (범위 [{min(nv)}, {max(nv)}] · sd {n_sd:.2f}) ⇒ "
        + ("**🟢 상수가 아니다 — 가드는 살아 있다**" if len(set(nv)) > 1 else "**🔴 상수다 — 죽은 가드 후보**")
        + f" · 🔑 등록일은 **{len(set(d for _n, _c, d in NEW9))}일**뿐이다(같은 날 등록 건은 같은 `n_up`).")
    say("")

    # ── §8. 재진입 (항등) · 「첨단 제외」(인쇄만) ─────────────────────────────
    say("## §8. 🔂 §1-5 재진입 민감도 (**항등 명시**) + 「첨단 제외」(**인쇄만** · PD-31 재량 ⓐ)\n")
    flags = {nm: prior_flag(raw, c, d, []) for nm, c, d in NEW9}
    say("> 🔴🔴 **판정 분모 안 §1-5 재진입 = 0 · 항목 안 두 사이클 = 0**(PD-3) ⇒ 재진입 제외 표본 = 주 판정 표본(**항등**) · "
        "「재진입 의존」은 구성상 생길 수 없다(판별력 0 · 그 사실을 적는다).\n")
    say("| 종목 | 이번 등록일 | 직전 사이클 등록일 | **`P6-PRIOR_CYCLE_IN_WINDOW`**(계산 · PD-3 표) |")
    say("|---|---|---|---|")
    for nm, _c, d in NEW9:
        say(f"| {nm} | {d} | 없음 | **{flags[nm]}** · {PD3_FLAG[nm]} {'🟢' if flags[nm] == PD3_FLAG[nm] else '🔴 불일치'} |")
    say(f"\n⇒ **플래그 합 = {sum(flags.values())}**(PD-3 「0/5」) · 🔑 §1-5 3: 「제외」가 아니라 「규칙상 통과할 수 없다」를 인쇄하는 장치다.")
    say("")
    keep = [r for r in rows9_t if r[0] != CHEOM]
    ak = aggs(keep)
    nk = len(keep)
    s1_keep = sum(1 for nm, _r, r in s1_rows if nm != CHEOM and r and r["ret_c"] >= 0.15)
    h_keep = sum(1 for nm, _r, r in s1_rows if nm != CHEOM and r and r["ret_h"] >= 0.15)
    med_keep = float(np.median([x[2] for x in nups if x[0] != CHEOM]))
    say(f"| 항목 | 문턱 | **`exact` {n9}건**(주 판정) | **§1-5 재진입 제외** | 「첨단 제외」 {nk}건(인쇄만 · 판정 효과 0) | 문턱 반대편인가(기록) |")
    say("|---|---|---|---|---|---|")
    rows_sens = [
        ("`SEL-S1`(종가 +15%)", ">= 1/2", f"{s1_hits}/{n9} = {s1_hits/n9*100:.1f}%", f"{s1_keep}/{nk} = {s1_keep/nk*100:.1f}%",
         (s1_hits * 2 >= n9) != (s1_keep * 2 >= nk)),
        ("`P6-S1h`(고가 +15%)", ">= 1/2", f"{h_hits}/{n9} = {h_hits/n9*100:.1f}%", f"{h_keep}/{nk} = {h_keep/nk*100:.1f}%",
         (h_hits * 2 >= n9) != (h_keep * 2 >= nk)),
        ("`SEL-S2`", ">= 95", fmt(s2), fmt(ak[0]), (s2 >= 95) != (ak[0] >= 95)),
        ("`SEL-S3`", "< 90", fmt(s3), fmt(ak[1]), (s3 < 90) != (ak[1] < 90)),
        ("`SEL-S4`", "40~80", fmt(s4), fmt(ak[2]), (40 <= s4 <= 80) != (40 <= ak[2] <= 80)),
        ("`P6-S1h-N` `n_up` 중앙", f">= {N_DEGRADE} ⇒ 강등", f"{n_med:.1f}", f"{med_keep:.1f}",
         (n_med >= N_DEGRADE) != (med_keep >= N_DEGRADE)),
    ]
    other = []
    for lbl, thr, a, b, oth in rows_sens:
        if oth:
            other.append(lbl)
        say(f"| {lbl} | {thr} | {a} | **항등**(제외할 건 0) | {b} | {'🟡 예(기록만 — 판정 효과 없음)' if oth else '아니오'} |")
    say("\n🟢 **§1-5 재진입 민감도 = 항등** · 「첨단 제외」는 **인쇄만**(PD-31 ⓐ · 🔴 ⓑ 계수 갈래는 신설 규칙이라 쓰지 않는다)"
        + (f" · 🟡 문턱 반대편 기록 {len(other)}건: " + " · ".join(other) + "(판정 불변)" if other else "") + ".")
    say("")

    # ── §9. 절단 가드 ───────────────────────────────────────────────────────
    say("## §9. `P6-절단가드-A`/`B` (`PREREG_POST6.md` §1-6 · PD-12)\n")
    trunc = [(nm, v) for nm, v in win20.items() if v[0] < WIN20]
    frac = len(trunc) / n9
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 분모 | **`exact` {n9}건** |")
    say(f"| 분자 = 창 `[D-19, D]` 봉수 **< {WIN20}** 인 건 | **{len(trunc)}**"
        + (" — " + " · ".join(f"{nm} {v[0]}/{v[1]}" for nm, v in trunc) if trunc else "") + " |")
    say(f"| 비율 | **{len(trunc)}/{n9} = {frac*100:.1f}%** · 문턱 **>= 1/3 ⇒ ⛔** |")
    say(f"| **`P6-절단가드-A`** | **{'🔴 발동 ⇒ ⛔ 판정 불가' if frac >= TRUNC_GUARD else '🟢 미발동'}** |")
    say("")
    say("🟢 PD-12 예고(*「`P6-절단가드-A` 분자 **0/5**」*)와 **" + ("계산이 일치" if not trunc else "🔴 다르다") + "**한다 · "
        + ("절단 제외 표본 = 전 표본 = **항등** ⇒ `P6-절단가드-B` **미발동(구성상)**." if not trunc else "🔴 절단 건이 있다 — 값 불변 인쇄."))
    say("⚠️ 문턱 `1/3` = `REC-Y3` 에서 «차용»(절단 비율에 검증된 값 아님) · 🔑 봉수는 전부 「등록일 «포함»」.")
    say("")

    # ── §10. D-5 갈래 계수표 ─────────────────────────────────────────────────
    say("## §10. `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나)2 · PD-23)\n")
    say("> 최소 n = **3**(동결값) · 「첨단 제외」는 **인쇄만 — 계수에 넣지 않는다**(PD-31 ⓑ 금지) · 항등 갈래도 「항등」으로 인쇄 · "
        "`approx` 포함 갈래 = **없음**(`approx` 0 — 주와 같은 표본).\n")
    say("| 예측 | 갈래 이름 | n | 답 | 계수에 넣나 |")
    say("|---|---|---|---|---|")
    ans = {
        "`SEL-S1`": (f"기각 유지(표본 {s1_hits}/{n9} = {s1_hits/n9*100:.1f}% · {'문턱 위' if s1_pass else '문턱 아래'})",
                     f"{s1_keep}/{nk} = {s1_keep/nk*100:.1f}%"),
        "`P6-S1h`": (("문턱 충족(단조 완화 축 · 증거 아님)" if h_pass else "불성립") + f" {h_hits}/{n9}", f"{h_keep}/{nk}"),
        "`SEL-S2`": (("충족" if s2 >= 95 else "미달") + " " + fmt(s2), fmt(ak[0])),
        "`SEL-S3`": (("지지" if s3 < 90 else "기각") + " " + fmt(s3) + f"(분모 {s3_n}/{n9})", fmt(ak[1])),
        "`SEL-S4`": (("구간 내" if 40 <= s4 <= 80 else "구간 밖") + " " + fmt(s4), fmt(ak[2])),
        "`P6-S1h-N`": (("발동" if degrade else "미발동") + f" 중앙 {n_med:.1f}", f"중앙 {med_keep:.1f}"),
    }
    cal_dir = {"`SEL-S2`": fmt(a9c[0]), "`SEL-S3`": fmt(a9c[1]), "`SEL-S4`": fmt(a9c[2])}
    for lbl, (main_a, keep_a) in ans.items():
        say(f"| {lbl} | 주 판정(`exact`) | {n9} | **{main_a}** | ✅ |")
        say(f"| {lbl} | §1-5 재진입 포함↔제외 | {n9} ↔ {n9} | **항등**(재진입 0) | ✅(= 주) |")
        say(f"| {lbl} | 창 절단 포함↔제외 | {n9} ↔ {n9 - len(trunc)} | **항등**(절단 0) | ✅(= 주) |")
        say(f"| {lbl} | `approx` 포함 | {n9} | **항등**(`approx` 0 · 갈래 없음) | ✅(= 주) |")
        say(f"| {lbl} | 「첨단 제외」 | {nk} | {keep_a} — 인쇄만 | ❌(PD-31 ⓑ 금지) |")
        if lbl in cal_dir:
            say(f"| {lbl} | 대조 창(달력 10일 · 판정에 안 씀) | {n9} | {cal_dir[lbl]} — {'같은 방향' if same_dir else '다른 방향'} | ❌(판정 창 아님) |")
    say("")
    say("⇒ **계수 결과**: 최소 n 을 채운 갈래가 «판정» 답이 갈린 예측 = **없음** · 계수 갈래는 전부 주와 같은 표본(항등 3종).")
    say("")

    # ── §11. D-9 혼합 빈티지 신고 + 대조 적재 ─────────────────────────────────
    say("## §11. `D-9` · `P8-혼합빈티지신고` + 09-23 봉 영향 대조 (PD-27 (마) 4 · (바))\n")
    say(f"> 이 레인의 창 = 판정 창 `[D-4, D]` · 절단 가드 창 `[D-19, D]` · 유니버스 적재 창 `[{UNIV_LO}, {DB_UPTO}]` — **걸치는 창마다 한 줄** "
        "+ 「전부 경계 후」 창은 **추가 한 줄**(PD-27 (바) 재량 · 판정 효과 0).\n")
    say("| 건 | 창 | 시작 | 끝 | 경계 전 봉 | 경계 후 봉 | 걸침? |")
    say("|---|---|---|---|---|---|---|")
    cross_lines, after_lines, x19 = [], [], {}
    for nm, c, d in NEW9:
        for wlab, n in (("`[D-4, D]`", W_TDAYS), ("`[D-19, D]`", WIN20)):
            s = own_split(raw, c, d, n)
            crossed = s[2] > 0 and s[3] > 0
            if crossed:
                cross_lines.append(mixed_line(s[0], s[1], s[2], s[3]) + f" ({nm} {wlab})")
                if n == WIN20:
                    x19[nm] = (s[2], s[3])
            elif s[2] == 0:
                after_lines.append(f"창 `[{s[0]}, {s[1]}]` 은 전부 제도 경계 후(전 0 / 후 {s[3]}) ({nm} {wlab})")
            say(f"| {nm} | {wlab} | {s[0]} | {s[1]} | {s[2]} | {s[3]} | {'🔴 걸침' if crossed else ('🟡 전부 후' if s[2] == 0 else '안 걸침')} |")
    ud = [d for d in mdays if UNIV_LO <= d <= DB_UPTO]
    ub, ua = sum(1 for d in ud if d < REGIME), sum(1 for d in ud if d >= REGIME)
    say(f"| 유니버스(시장 달력) | 적재 창 | {ud[0]} | {ud[-1]} | {ub} | {ua} | {'🔴 걸침' if ub and ua else '안 걸침'} |")
    if ub and ua:
        cross_lines.append(mixed_line(ud[0], ud[-1], ub, ua) + " (유니버스 적재 창)")
    say("")
    say("**의무 문장**(`PREREG_POST8.md` §9 (나)3 · 걸침 칸마다):\n")
    for ln in cross_lines or ["(걸침 창 없음)"]:
        say(f"- {ln}")
    say("")
    say("**추가 줄**(「전부 경계 후」 · PD-27 (바) 재량):\n")
    for ln in after_lines or ["(해당 창 없음 — 이 레인의 창은 전부 등록일 이전 봉을 포함한다)"]:
        say(f"- {ln}")
    say("")
    say(f"⇒ **`[D-19, D]` 걸침 = {len(x19)}건** — PD-27 (바) `[D−19, D]` 열(빛샘 19/1 · 첨단 18/2 · 한컴 18/2)과 "
        + ("🟢 일치" if x19 == PD27_X19 else f"🔴 불일치 {x19}") + " · `[D-4, D]` 는 PD-27 (바) 표에 열이 없다(계산값 인쇄).")
    say(f"- 기록: 등록일 봉 자체가 제도 경계 «후»인 건 **{n_after}/{n9}** — `SEL-` 판정 창(등록일 봉)은 `:546` 이름 목록에 없어 "
        "신고 의무 대상 밖 · 재량 인쇄(PD-27 (바)).")
    df_cut = build_features(load_ext(DB_UPTO_CUT))
    r9_cut = rows_t(NEW9, df_cut)
    a_cut = aggs(r9_cut)
    maxdiff = 0.0
    for (_n1, _c1, _r1, st1, _b1), (_n2, _c2, _r2, st2, _b2) in zip(rows9_t, r9_cut):
        for f in FEATS:
            v1, v2 = st1[f], st2[f]
            if (v1 != v1) and (v2 != v2):
                continue
            maxdiff = max(maxdiff, abs(v1 - v2) if (v1 == v1 and v2 == v2) else float("inf"))
    same_cut = (a_cut[:3] == a9t[:3]) and maxdiff == 0.0
    say(f"- **09-23 봉 영향 대조**(PD-27 (마) 4 — 「`SEL-` 은 유니버스를 `DB_UPTO` 까지 적재」): 유니버스를 **{DB_UPTO_CUT}**(최대 등록일) "
        f"까지만 적재해 다시 쟀다 — 특징 백분위 최대 절대차 **{maxdiff:.4f}** · S2/S3/S4 = {fmt(a_cut[0])} / {fmt(a_cut[1])} / "
        f"{fmt(a_cut[2])} ↔ 주 {fmt(s2)} / {fmt(s3)} / {fmt(s4)} ⇒ "
        + ("**🟢 동일 — 09-16~09-23 봉은 이 레인의 판정값에 들어가지 않는다**" if same_cut else "**🔴 다르다 — 조사 대상(값 불변 인쇄)**")
        + " · 🔴 단 09-14·09-15 등록일 봉(제도 경계 후)은 **들어간다**(위 기록 줄).")
    say("- 🔴 방향 추론(「`H` 를 높이고 `L` 을 낮춘다」)은 실측으로 인용하지 않는다 · 한계(PD-27 (바) 옮김): `ovtm_vol` 09-14~09-21 전부 0 · "
        "`overtime_daily` 09-22 이후 행 없음 · 15:30 분봉 ≤ 1/301 ⇒ **「정규장만」 갈래 없음**.")
    say("")

    # ── §12. 판정 요약 ──────────────────────────────────────────────────────
    say("## §12. 판정 요약 — `PREREG_POST6.md` §4 #1~#6·#11 형식 (등급 열 없음)\n")
    say(f"| # | 항목 | 문턱 (출처 파일) | 최소 n | 값(`exact` {n9}) | **판정** | 대칭/반증 쌍 | ⛔ 경로 · 민감도 |")
    say("|---|---|---|---|---|---|---|---|")
    say(f"| 1 | `SEL-S1` | >= 1/2 · `PREREG_SELECTION.md` §7 | {MIN_N} | {s1_hits}/{n9} = {s1_hits/n9*100:.1f}% | "
        "❌ **기각 유지**(`PREREG_POST6.md` §2-1 · 부활 경로 없음) | `SEL-S3` | 판정 건 < 3(미발동) · 재진입·절단·`approx` 갈래 **항등** · "
        f"「첨단 제외」 {s1_keep}/{nk}(인쇄만) |")
    v2_ = "🟡 **문턱 충족 — 단조 완화 축이라 «증거 아님»**" if h_pass else "❌ **불성립**"
    if degrade and h_pass:
        v2_ += " ⇒ #3 발동으로 **인용 금지 강등**"
    say(f"| 2 | `P6-S1h` | >= 1/2 · `PREREG_SELECTION.md` §7(상속) | {MIN_N} | {h_hits}/{n9} = {h_hits/n9*100:.1f}% | {v2_} | "
        f"`P6-S1h-N` | 🔴 통과는 증거 아님 · 갈래 항등 · 「첨단 제외」 {h_keep}/{nk}(인쇄만) |")
    v3_ = "🔴 **발동 ⇒ `P6-S1h` 인용 금지(강등)**" if degrade else "🟢 **미발동**"
    say(f"| 3 | `P6-S1h-N` | >= {N_DEGRADE} → 인용 금지 · `PREREG_D1_OOS.md` §4 | — | 중앙 {n_med:.1f} · 범위 [{min(nv)}, {max(nv)}] · "
        f"sd(`ddof=1`) {n_sd:.2f} | {v3_} | 자신이 반증축 | `drop_rate >= 1%` {len(bad_days)}일 · 「첨단 제외」 중앙 {med_keep:.1f}(인쇄만) |")
    for num, lbl, thr, val, ok_s, pair, extra in (
            (4, "`SEL-S2`", ">= 95 · `PREREG_SELECTION.md` §7", fmt(s2), "✅ **충족**" if s2 >= 95 else "🟡 **미달**", "`SEL-S4`", ""),
            (5, "`SEL-S3`", "**< 90** · `PREREG_SELECTION.md` §7", f"{fmt(s3)} (분모 {s3_n}/{n9})",
             "✅ **지지**" if s3 < 90 else "❌ **기각**", f"`f9` 원값 1 건수 = **{n_raw1}/{n9}**",
             f"C-17 {'반영 ✅' if c17_ok else '🔴 미반영'} · "),
            (6, "`SEL-S4`", "40~80 · `PREREG_SELECTION.md` §7", fmt(s4), "✅ **구간 내**" if 40 <= s4 <= 80 else "🟡 **구간 밖**",
             "`SEL-S2`", "")):
        say(f"| {num} | {lbl} | {thr} | {MIN_N} | {val} | {ok_s} | {pair} | {extra}갈래 **항등** · 「첨단 제외」 {fmt(ak[num - 4])}(인쇄만) |")
    say(f"| 11 | `REG-M4` | 기록 · `PREREG_REGDAY_MEASURE.md` §4-4 | — | `n_up` 중앙 {n_med:.1f} · 범위 [{min(nv)}, {max(nv)}] | "
        "🟡 **기록만**(대칭 단언 · 판정 아님) | 자신이 반증축 | 이 표의 `n_up` 은 `P6-S1h-N` 과 **같은 계산**이다 |")
    say("")
    say("### 12-1. 🔴 배선 점검 — 발화한 가드가 판정 칸에 «실제로» 걸렸는가\n")
    say("| 가드 | 상태 | 걸려야 하는 판정 칸 | 칸에 반영됐나 |")
    say("|---|---|---|---|")
    wires = [
        ("`P6-S1h-N`(n_up 중앙 ≥ 30)", "발동" if degrade else "미발동", "#2 `P6-S1h`",
         (not degrade) or (not h_pass) or ("인용 금지 강등" in v2_)),
        ("`P6-절단가드-A`", "발동" if frac >= TRUNC_GUARD else "미발동", "#1~#6", frac < TRUNC_GUARD),
        ("`P6-절단가드-B`", "미발동(항등)" if not trunc else "확인 필요", "#1~#6", not trunc),
        ("`drop_rate ≥ 1%`", "발동" if bad_days else "미발동", "#3 비교 금지 문구", True),
        ("C-17 반영", "반영" if c17_ok else "미반영", "#5 `SEL-S3`", c17_ok),
        ("`D-3` (나)4 정밀도 의존 · `P9-공통독법`", "대상 없음(`approx` 0)", "없음", True),
        ("§1-5 재진입 의존", "구성상 불가(항등)", "#1~#6", True),
        ("「첨단 제외」(PD-31)", "인쇄만", "없음(판정 효과 없음)", True),
    ]
    for g, s_, tgt, okw in wires:
        say(f"| {g} | {s_} | {tgt} | {'🟢 예' if okw else '🔴 **아니오 — 배선 결함**'} |")
    assert all(w[3] for w in wires), "배선 결함"
    say("")
    say(f"🔴 **이 문서에서 처음 정한 문턱에 걸렸는가**(`PREREG_POST6.md` §9): `drop_rate >= 1%` 가드 = **{'발동' if bad_days else '미발동'}**.")
    say("")

    # ── §13. 의무 체크리스트 ────────────────────────────────────────────────
    say("## §13. `PREREG_POST8.md`·`PREREG_POST9.md` 인쇄 의무 체크리스트 (가분성 §0-5-1)\n")
    say("| 의무 | 이 레인 해당 | 자리 |")
    say("|---|---|---|")
    for a, b, c in (("`D-1`·`D-2`·`D-4`·`D-7`·`D-10`·`D-11`", "해당 없음(다른 레인 · 등급 없음 · `Q1-R2` 미인용)", "—"),
                    ("`D-3`(`P8-approx의존신고`)", "**해당**", "§0-2"), ("`D-5`(`P8-갈래계수` 세 쪽)", "**해당**", "§10"),
                    ("`D-6`(`ddof=1` 표기)", "**해당**", "§0-2 · §7-1"), ("`D-8`(`prog_ver` 수준 목록)", "해당 없음(공변량 미사용)", "§0-2"),
                    ("`D-9`(①~⑤)", "**해당**", "머리 · §0-1 · §11"),
                    ("🆕 `P9-공통독법`(신고 줄)", "**해당** — 답 = 판정 · 대상 없음(`approx` 0)", "§0-2 · §5-3"),
                    ("🆕 `P9-행단위`", "해당 없음(수준 목록 없음) — 줄 인쇄", "§0-2"),
                    ("🆕 `P9-WRC누적분모`·`P9-갈래게이트인쇄전용`·`P9-수집증거`", "해당 없음", "§0-2"),
                    ("라이브 채택 금지(`PREREG_POST9.md` §0-1 문언 그대로 · §8-3 #20)", "**해당**", "머리"),
                    ("PD-31 신고 줄(확인 5)", "**해당**", "§1 · §6-1")):
        say(f"| {a} | {b} | {c} |")
    say("")
    say(f"🔴 **{WINDOW_LINE}** · **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)**.")
    say("🔴 **라이브 채택 대상이 아니다** · 🔴 **`adj_factor` 를 곱하지도 나누지도 않았다**.")

    conn.close()
    (BASE / OUT_NAME).write_bytes(("\n".join(OUT) + "\n").encode("utf-8"))
    note(f"[written] {OUT_NAME} · 런타임 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
