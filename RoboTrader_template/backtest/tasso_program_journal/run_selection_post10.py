# -*- coding: utf-8 -*-
"""`PREREG_SELECTION.md` §7 + `PREREG_POST6.md` §2-1 실행 — 10번째 글 (out-of-sample, 7회차).

`run_selection_post9.py` 를 **승계**한다(원본은 손대지 않는다 · import 도 하지 않는다 — 그 모듈은 import 시점에 `P8.DB_UPTO` 를
09-23 으로 박는다). 특징·통계량·표 포맷·조회·로더·빈티지·걸침 문장은 post6/post7/post8 판을 **import 해 그대로 재사용**한다.
post8 로더(`load_raw_close`·`market_days`)는 모듈 전역 `DB_UPTO` 를 호출 시점에 읽으므로 이 실행 안에서만 `P8.DB_UPTO` 를
10-02 로 바꾼다(파일 불변). post9 판 대비 «차이» = ① post10 상수(글 목록 9 · 창 · 빈티지 · 출력 경로) ② §1-5 재진입 4/9 —
**항등 아님** ⇒ 재진입 제외 갈래(n 5)를 실제로 계산해 «판정이 갈리는가»를 인쇄 ③ 「샌즈 제외」(🔒 #1 ⓐ · 인쇄만) ④ `P10-기업행위봉`
신고 줄 + 「기업행위 건 제외」 갈래(의무 인쇄 · 답(참고) · 세지 않는다) ⑤ `SEL-S3` = 기각 유지 문형(`PREREG_POST10.md` §3 (나)7)
⑥ `P9-스탬프통일`(`selection_post10/read_stamp.json`) ⑦ `[D-19, D]`·`[D-4, D]` 걸침 줄 + 「전부 경계 전」 추가 줄.

동결 준거: `PREREG_SELECTION.md` §7 · `PREREG_POST6.md` §2-1·§4 #1~#6·#11·§1-4~§1-6·§5-1·§5-2 ·
`PREREG_POST8.md` §0-1·§0-5-1·D-3·D-5·D-6·D-9 · `PREREG_POST10.md`(동결 `522d6dc`) §0-1·§3 (나) ·
`PREDECISION_2026-10-04_post10.md` PD-1·3·12·21·23·24·27·33·35·36·43 · `INTAKE_2026-10-04_post10.md` §1·§5.
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
ART = BASE / "selection_post10"
OUT: list[str] = []
OUT_NAME = "RESULTS_SELECTION_POST10_NUMBERS.md"

DB_UPTO = "2026-10-02"          # PD-1: 창 종료 = 발행 당일(금 · 거래일) 봉 «포함» · 전 축(WRC- 포함)
DB_UPTO_CUT = "2026-09-29"      # 대조 적재 = 최대 등록일(뷰노) — 판정에 안 씀
SWEEP_D1 = "2026-10-06 15:35:00"  # 10-02 봉의 D+1 sweep (PD-27 (마) 1·2)
PROBE_WIN = ("2026-08-12", "2026-10-02")  # PD-27 (마) 2(b)(f) 창 시작 08-12 ~ 창 종료
MGR = dict(run="2026-10-07 19:35:46 / 19:36:08 / 19:36:31 KST(3회)", rows_1006=2768, rows_1007=2767,
           max_upd="2026-10-07 15:46:38.364963", min_upd="2026-10-07 15:45:21.82908",
           src="D:/archive/tasso-program-journal-20261004/probes_precalc_1007/")  # 관리자 관측 옮김(2차 출처)
P8.DB_UPTO = DB_UPTO            # post8 로더 2개가 호출 시점에 읽는 전역(이 프로세스 안에서만)

# ── 10번째 글 신규 9건 = 전부 `exact` (INTAKE_2026-10-04_post10 §1·§5 · PD-1·3·12) ──────
NEW10 = [("서산", "079650", "2026-09-09"), ("샌즈랩", "411080", "2026-09-14"), ("성호전자", "043260", "2026-09-14"),
         ("라온시큐어", "042510", "2026-09-15"), ("범한퓨얼셀", "382900", "2026-09-16"), ("한켐", "457370", "2026-09-16"),
         ("HT로보틱스", "396300", "2026-09-18"), ("우리로", "046970", "2026-09-18"), ("뷰노", "338220", "2026-09-29")]
FOLLOW10 = [("한컴위드", "054920", "post9 #6 · 09-15 재명시(재등록 09-23)"), ("코데즈컴바인", "047770", "post8 #9 · 재명시"),
            ("빛샘전자", "072950", "post9 #4 · 09-14 재명시")]
# 재진입 4(PD-3 표): 코드 → 직전 사이클 등록일(원장 실측) — `P6-PRIOR_CYCLE_IN_WINDOW` 계산용
REENTRY = {"382900": ["2026-09-09"], "079650": ["2026-09-03"], "457370": ["2026-08-12", "2026-08-20"],
           "046970": ["2026-09-11"]}
SANDS = "샌즈랩"                  # 🔒 #1 ⓐ — 항목 내 날짜 있는 재등록(09-29) · 「샌즈 제외」 = 인쇄만(계수 아님)
PD12_PRIOR = {"서산": 109, "샌즈랩": 112, "성호전자": 112, "라온시큐어": 113, "범한퓨얼셀": 114, "한켐": 114, "HT로보틱스": 116,
              "우리로": 116, "뷰노": 121}   # PD-12 표 「로드창(04-01~) 직전 봉」
PD3_FLAG = {nm: (1 if c in REENTRY else 0) for nm, c, _d in NEW10}   # PD-3 표(계산 전) — 대조용
# post9 판 대상(같은 스냅샷 재계산 · 참고) — `run_selection_post9.NEW9` 옮김(import 하지 않는다)
NEW9 = [("삼미금속", "012210", "2026-09-04"), ("에스투더블유", "488280", "2026-09-10"),
        ("빛샘전자", "072950", "2026-09-14"), ("한국첨단소재", "062970", "2026-09-15"),
        ("한컴위드", "054920", "2026-09-15")]
NEW8 = [(nm, c, d) for nm, c, d, _t in P8.EXACT8]      # post8 판정 표본 `exact` 4 (같은 스냅샷 재계산)

PUB = dict(P8.PUB)
PUB["post8_td5"] = (2, 4, 99.8, 47.1, 69.7)     # RESULTS_SELECTION_POST8_NUMBERS.md §2·§5 (09-24)
PUB["post9_td5"] = (3, 5, 99.5, 96.3, 56.9)     # RESULTS_SELECTION_POST9_NUMBERS.md §2·§5 (09-29)
PUB_H = dict(P8.PUB_H)
PUB_H["post8"] = (4, 4)                         # RESULTS_SELECTION_POST8_NUMBERS.md §3
PUB_H["post9"] = (3, 5)                         # RESULTS_SELECTION_POST9_NUMBERS.md §3
S1_CUM_PRIOR = (27, 44)                         # RESULTS_SELECTION_POST9_NUMBERS.md §2-1 누적(승계 셈법)
H_CUM_PRIOR = (20, 25)                          # 같은 문서 §3-1 판정 누적(post6~9)
NUP_SERIES = list(P8.NUP_SERIES) + [("post8", "75.5", "[62, 82]", "9.95"), ("post9", "64.0", "[58, 69]", "3.94")]
_PR10 = (BASE / "PREREG_POST10.md").read_text(encoding="utf-8").splitlines()
LIVE_BAN = (_PR10[55], _PR10[57])               # `PREREG_POST10.md:56`·`:58` §0-1 문언 그대로
assert LIVE_BAN[0].startswith("> *「🔴 **라이브 채택 금지.**") and LIVE_BAN[1].startswith("⇒ `PREREG_POST8.md:26`")
WINDOW_LINE = ("창 종료 2026-10-02 = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · `END` · "
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


def corp_scan(cur, code, lo, hi):
    """`P10-기업행위봉`(`PREREG_POST10.md` §3 (나)) 정의 A — 창 `[lo, hi]` 안: ⓐ `corp_events` `split` 행 · 기록 줄 = 전 행 ·
    ⓑ `daily_prices.volume = 0` 봉 · ⓒ(기록 줄 · 정의 아님) `news` 제목 거래정지 공시. 값 산술 0 · SELECT 만."""
    cur.execute("SELECT event_type, event_date, coalesce(meta->>'report_nm', '') FROM corp_events "
                "WHERE stock_code = %s AND event_date BETWEEN %s AND %s ORDER BY event_date, event_type", (code, lo, hi))
    allrows = [(t, str(d), str(r).strip()) for t, d, r in cur.fetchall()]
    cur.execute("SELECT date FROM daily_prices WHERE stock_code = %s AND date BETWEEN %s AND %s AND volume = 0 "
                "ORDER BY date", (code, lo, hi))
    vol0 = [str(r[0]) for r in cur.fetchall()]
    cur.execute("SELECT published_at::date, title FROM news WHERE related_stocks LIKE %s AND published_at::date BETWEEN %s "
                "AND %s AND title ~ '거래정지|매매정지|매매거래' ORDER BY published_at, id", ("%" + code + "%", lo, hi))
    halt = [(str(d), str(t).strip()) for d, t in cur.fetchall()]
    return dict(split=[r for r in allrows if r[0] == "split"], allrows=allrows, vol0=vol0, halt=halt)


def corp_reason(sc):
    """건별 사유 문자열(ⓐ/ⓑ · 날짜). k 분류 = ⓐ ∨ ⓑ."""
    parts = [f"ⓐ split {d}" for _t, d, _r in sc["split"]]
    if sc["vol0"]:
        parts.append(f"ⓑ `volume = 0` {len(sc['vol0'])}봉({sc['vol0'][0]}" + (f"~{sc['vol0'][-1]}" if len(sc["vol0"]) > 1 else "") + ")")
    return " + ".join(parts)


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
    n10 = len(NEW10)

    say("# RESULTS_SELECTION_POST10_NUMBERS — 기계 생성 (수정 금지)\n")
    say(f"- 🔴 **{WINDOW_LINE}**")
    say(f"- 🔴 **실행 시 `max(date)` = {snap_max} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)** · "
        f"창 종료일 {DB_UPTO} 행수 **{rows_upto:,}**")
    say(f"- 🔴 **D-9 ① 쿼리 실행 시각(KST) = {first_read}**(이 지문을 이 스크립트가 «처음» 읽은 실행 · "
        "`selection_post10/read_stamp.json` · 같은 지문 재실행은 이 값을 다시 쓴다 · 🆕 `P9-스탬프통일` 발효(post10 부터 · PD-35) · 키 "
        "`first_read_kst`·`timezone`·`fingerprint`)")
    say("- 🔴 라이브 채택 금지 — `PREREG_POST10.md` §0-1 문언 그대로(`:56`·`:58`):")
    say("")
    say(LIVE_BAN[0])
    say("")
    say(LIVE_BAN[1])
    say("")
    say("사전등록 `PREREG_SELECTION.md` §7(`9e53825`) + `PREREG_POST6.md` §2-1·§4 #1~#6·#11 + `PREREG_POST8.md`(동결 `04cd785`) + "
        "`PREREG_POST9.md`(동결 `702f41b`) + 🆕 `PREREG_POST10.md`(동결 `522d6dc` · 사전등록 «발행 후 · fetch 전») · 생성 "
        "`run_selection_post10.py`(`run_selection_post9.py` 승계 · 원본 불변)")
    say("계산 «전» 동결 = `PREDECISION_2026-10-04_post10.md` · `INTAKE_2026-10-04_post10.md` · `LABELS_2026-10-04_post10.md` "
        "(인테이크 커밋 `723779e` · 정오 `8e014ca`) · 원장(post10 12행/34레그 · `prog_ver` 1.0.43)")
    say("")
    say("## §0. 실행 환경 · 동결 규약 (값을 보기 «전»에 고정)\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| DB | `kis_template.daily_prices` — **SELECT 만** |")
    say(f"| 유니버스 창 | {UNIV_LO} ~ **{DB_UPTO}** (`market_cap > 0` ∧ `close > 0` ∧ 의사티커 제외) |")
    say(f"| 유니버스 | **{df.stock_code.nunique():,}종목** · **{df.date.nunique()}거래일** · 최신 봉 **{df.date.max().date()}** |")
    say(f"| 판정 창 | 동결 문언 `[D-4, D]` = **거래일 {W_TDAYS}일** (`PREREG_SELECTION.md` §2) · 대조 창 달력 {W_CAL_POST4}일(판정에 안 씀) |")
    say(f"| 🔴 판정 분모 | **신규 ∧ `exact` = {n10}건** ({' · '.join(r[0] for r in NEW10)} · 🔒 #1 ⓐ — 항목 내 재등록 "
        "(샌즈랩 9/29 · 한컴위드 9/23)은 등록 사건 아님 · 날짜만 기록) |")
    say("| 민감도 분모 | `approx` **0건** · `none`(신규) 0 · `after` 0 ⇒ **정밀도 갈래 없음**(PD-21) · 🔴 그러나 §1-5 재진입 **4/9 ⇒ 재진입 제외 갈래 n 5 = 항등 아님**(PD-3) |")
    say(f"| 축 밖 | 후속 **{len(FOLLOW10)}건**({' · '.join(r[0] for r in FOLLOW10)} — PD-2 · `none`) |")
    say(f"| 시드 · NREP | **{SEED}** · `NREP = {run_selection.NREP:,}`(상수) — 🔴 **귀무를 돌리지 않는다** ⇒ 이 문서에 「p 값」은 없다 |")
    say(f"| C-17 반영 | {'✅' if c17_ok else '🔴 **미반영 ⇒ 산출물 무효**'} `run_selection.py:{c17_line}` — `{c17_src}` |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1 · `PREREG_POST10.md` §0-1) |")
    say("")
    say("### 0-1. `D-9` 읽은 시각 · 빈티지 박제 (`PREREG_POST8.md` §9 (나)1·2 · PD-27 (마)(바))\n")
    say("| # | 의무 | 이 실행의 재측 | 관리자 실측(옮겨 적음 · 대조) |")
    say("|---|---|---|---|")
    say(f"| ① | 쿼리 실행 시각(KST) | **{first_read}**(스탬프) · 기계 검사: **> {SWEEP_D1}(D+1 sweep) = "
        f"{'예' if run_after_sweep else '🔴 아니오'}** · **> 창 구간 `max(updated_at)` = "
        f"{'예' if run_after_maxupd else '🔴 아니오'}** · 🔴 post8 자리(산문 §0 · stdout)도 유지 | {MGR['run']} |")
    say(f"| ② | 창 구간 `max(daily_prices.updated_at)` | `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` **{v_probe[1]}** · "
        f"적재 창 `[{RAW_LO}, {DB_UPTO}]` **{v_lane[1]}** | {MGR['max_upd']} |")
    say(f"| ③ | 「10-02 봉은 D+1(10-06) sweep 이후 읽음」 | **10-02 봉은 D+1(10-06) sweep 이후 읽음** "
        f"(① 기계 검사 {'예' if run_after_sweep else '🔴 아니오'}) | 같음 |")
    say(f"| ④ | 창 구간 `min(updated_at)` ≥ 10-06 15:35 (기록 · 통과 조건 아님) | `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` "
        f"**{v_probe[2]} ≥ 10-06 15:35: {'예' if min_ok else '아니오'}** · 적재 창 {v_lane[2]} ≥ 10-06 15:35: "
        f"{'예' if min_ok_lane else '아니오'} | {MGR['min_upd']} ≥ 10-06 15:35: 예 |")
    say("| ⑤ | `P8-혼합빈티지신고` | §11 (걸침 창마다 한 줄 + 「전부 경계 후/전」 추가 줄) | PD-27 (바) |")
    say(f"| 관측 보관 | 착수 조건 관측(옮겨 적음 · 2차 출처) | — | 10-06 행수 {MGR['rows_1006']:,}(×3) · 10-07 행수 {MGR['rows_1007']:,}(×3) · "
        f"보관 `{MGR['src']}` |")
    say("")
    say("- 🔴 **`updated_at` 은 sweep 이 전 표를 일괄 갱신한 값**이라 빈티지 «증거»가 아니라 **읽은 시각의 기록**이다"
        "(PD-27 (라) · `P-3` 판별력 0 — 「통과」로 인용하지 않는다) · 「정규장만」 갈래 없음(§9 (나)4) · `adj_factor` 산술 **0**.")
    say("- 🔴 착수 시각(`F-4`) = 첫 레인 실행 `now()` — 이 레인 스탬프가 «첫 실행»이면 그 값이 착수 시각이다 · 상한 10-08 23:59:59 안이면 "
        "초과 신고 줄은 쓰지 않는다(`P10-착수상한`).")
    say(f"- 창 구간 행수: `[{PROBE_WIN[0]}, {PROBE_WIN[1]}]` **{v_probe[3]:,}** · 적재 창 **{v_lane[3]:,}**.")
    say("")
    say("### 0-2. `D-3` · `D-6` · `D-8` · 🆕 `P9-공통독법` · `P9-행단위` 의무 줄\n")
    say(f"- **`D-3`**: *「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 {n10} / `approx` 포함 분모 {n10}」* "
        "(PD-21 구성 예고 「없음」과 일치 · `approx` 0).")
    say("- 🆕 **`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)** (`PREREG_POST9.md` §1 (나)3 · 독법 B 병기 자리 없음) — "
        "🔴 재진입 갈래(§8)는 `approx` 갈래가 아니다(항등 아님 · 별도 인쇄).")
    say("- **`D-6`**: `n_up` 표준편차는 **`ddof=1`(표본)** 이다(`PREREG_POST8.md` §6 SSOT) · 문턱은 **중앙값 ≥ 30** 이지 sd 가 아니다.")
    say("- **`D-8`** · 🆕 **`P9-행단위`·`P9-결측분리`: 해당 없음** — 이 레인은 `prog_ver` 를 공변량으로 쓰지 않는다(수준 목록 · "
        "결측 n 줄은 `WRC-`·`RNK-`·`SEC-` 소관 · 🔴 분모에서 `prog_ver` 로 빼지 않는다).")
    say("- `P9-WRC누적분모`·`P9-갈래게이트인쇄전용`·`P9-수집증거`: 해당 없음(다른 레인).")
    say("🔴 **값 보고 규칙을 바꾸지 않는다** · 새 예측 0(`PREREG_POST6.md` §7-B #11) · 등급 이름 0(§6 단계 · PD-16).")
    if not c17_ok:
        say("🔴🔴 **C-17 미반영 — `SEL-S3` 판정은 무효다.**")
    say("")

    # ── §1. 표본 ────────────────────────────────────────────────────────────
    say(f"## §1. 표본 — 10번째 글 **신규 {n10}건 = 판정 분모 `exact` {n10}건** (후속 {len(FOLLOW10)}건은 등록일 축 밖 · PD-2)\n")
    say(f"| # | 종목 | 코드 | 등록일 | 정밀도 | `[D-19, D]` 봉수(등록일 «포함») | 창 `[D-4, D]` 봉수 | "
        f"창 안 DB 행수(`date <= {DB_UPTO}`) | DB 최초일 | 등록일 봉 제도 경계 후? |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    win20 = {}
    for i, (nm, code, reg) in enumerate(NEW10, 1):
        cur.execute("SELECT count(*) FILTER (WHERE date <= %s), min(date) FROM daily_prices WHERE stock_code=%s",
                    (DB_UPTO, code))
        n_all, mn = cur.fetchone()
        nb20, wlen = win20_bars(cur, mdays, code, reg)
        win20[nm] = (nb20, wlen)
        _st, nb5 = stat_tdays(df, code, pd.Timestamp(reg), W_TDAYS)
        say(f"| {i} | {nm} | {code} | {reg} | `exact` | **{nb20}/{wlen}** | {nb5} | {n_all} | {mn} | "
            f"{'🟡 예(기록)' if reg >= REGIME else '아니오'} |")
    n_after = sum(1 for _n, _c, d in NEW10 if d >= REGIME)
    say("")
    say(f"🔁 **후속 {len(FOLLOW10)}건**(" + " · ".join(f"{nm} `{c}` {t}" for nm, c, t in FOLLOW10)
        + ")은 **등록일 축 분모에서 제외**한다(PD-2 · 이중계상 금지 · «정의»로 빠진다).")
    say(f"- 기록: 등록일 서로 다른 날 **{len(set(d for _n, _c, d in NEW10))}**(건 단위 인쇄: "
        + " · ".join(f"{d[5:]} {'+'.join(nm for nm, _c, dd in NEW10 if dd == d)}" for d in sorted(set(d for _n, _c, d in NEW10)))
        + " · INTAKE §5) · "
        f"등록일 봉이 제도 경계(09-14) «후»인 건 **{n_after}/{n10}**(PD-27 (바) — 신고 의무 대상 밖 · 재량 인쇄).")
    say("- 🔒 #1 ⓐ: 항목 안 «날짜 있는» 재등록은 한 건으로 센다 — **재등록(샌즈랩 9/29 · 한컴위드 9/23) 날짜 기록** · 이번 분모 밖 · "
        "「샌즈 제외」(8) = 인쇄만(PD-43).")
    say("")
    say("### 1-0. 🆕 `P10-기업행위봉`(`F-3` · `PREREG_POST10.md` §3 (나)) — 창 = 등록일 직전 60행 rolling 입력 구간\n")
    win60, corp = {}, {}
    for nm, code, reg in NEW10:
        m60 = df[(df.stock_code == code) & (df.date <= pd.Timestamp(reg))].tail(60)
        lo60 = str(m60.date.min().date())
        win60[nm] = (lo60, reg, len(m60))
        corp[nm] = corp_scan(cur, code, lo60, reg)
    corp_k = [nm for nm, _c, _d in NEW10 if corp[nm]["split"] or corp[nm]["vol0"]]
    say("| 종목 | 60행 창 | 봉수 | ⓐ `split` 행 | ⓑ `volume = 0` 봉 | 기록 줄 — 창 안 `corp_events` 전 행 | ⓒ(기록 줄) 거래정지 제목 |")
    say("|---|---|---|---|---|---|---|")
    for nm, _c, _d in NEW10:
        w, sc = win60[nm], corp[nm]
        say(f"| {nm} | `[{w[0]}, {w[1]}]` | {w[2]} | {len(sc['split'])} | {len(sc['vol0'])} | "
            + (" · ".join(f"{t} {d}" for t, d, _r in sc["allrows"]) or "—") + " | "
            + (" · ".join(f"{d} {t}" for d, t in sc["halt"]) or "0") + " |")
    say("")
    say(f"- 🔴 **`P10-기업행위봉`: 기업행위 건 {len(corp_k)}/{n10} — "
        + ("; ".join(f"{nm}: {corp_reason(corp[nm])}" for nm in corp_k) if corp_k else "ⓐ 0 · ⓑ 0(건별 사유 없음)")
        + " · `adj_factor` 산술 0 · 처리 = (나)**")
    say("- 인테이크 예고(PD-36): ⓐ **0/9** — 이번 측정 ⓐ " + str(sum(1 for nm, _c, _d in NEW10 if corp[nm]["split"])) + "/9 ⇒ "
        + ("🟢 일치" if not any(corp[nm]["split"] for nm, _c, _d in NEW10) else "🔴 다르다(조사 대상 · 값 불변 인쇄)")
        + " · ⓑ 는 «레인 · 착수 뒤» 집계(`F-3` (나)6 · 이 줄이 그 집계).")
    say("- 처리 = (나): 「기업행위 건 제외」 갈래 값을 **의무 인쇄**(§8 · §10) · 답 칸 낱말 「답(참고) · 세지 않는다」 · "
        "판정 불변 · `SEL-S3` 는 기각 유지 문형이라 (다)의 ⛔ 는 걸리지 않는다(`F-3` (나)3·7).")
    say("")
    say("### 1-1. 커버리지 — 축별로 «다른 수»다 (PD-11 · 의무 산술 인쇄)\n")
    say("| 축 | 필요한 자료 | 측정 가능 | 측정 불가 | 비율 | 문턱 1/3 |")
    say("|---|---|---|---|---|---|")
    say(f"| **이 레인**(`SEL-`) | `daily_prices` | **{n10}/{n10}** | 0 | 0.0% | 미발동 |")
    say("| (참고 · PD-11) `SEC-` | `stock_industry` 섹터코드 | 9/9 | 0 | 0.0% | 미발동 |")
    say("| (참고 · PD-11) `S5` | `dart_financials_asfiled` PIT | 행 보유 여부는 S5 레인이 확정(판정 가능 ≤ 9) | 0 | — | — |")
    say("| (참고 · PD-11) `WRC-` | `fill_n >= 2` ∧ 서로 다른 값 레그 >= 3 | 단독 3 · 누적 8(D-4) | — | — | 판정 분모 8 |")
    say("")

    # ── §2. SEL-S1 ──────────────────────────────────────────────────────────
    say("## §2. `SEL-S1` — 등록일 **종가** 전일대비 >= +15% (동결 문언 · 🔴 기각 «유지»)\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 종가 | **종가 등락** | 문턱 충족 |")
    say("|---|---|---|---|---|---|")
    s1_hits, s1_rows = 0, []
    for nm, code, reg in NEW10:
        r = s1_row(raw, code, reg)
        s1_rows.append((nm, reg, r))
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | (데이터 없음) |")
            continue
        ok = r["ret_c"] >= 0.15
        s1_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['close']:,.0f} | **{pct(r['ret_c'])}** | {'✅' if ok else '❌'} |")
    s1_pass = s1_hits * 2 >= n10
    say(f"\n⇒ **이번 판정 분모 = {s1_hits}/{n10} = {s1_hits/n10*100:.1f}%** · 문턱 **>= 절반**(= {-(-n10//2)}/{n10}) ⇒ "
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
                                          ("post8", NEW8), ("post9", NEW9))]
    rc = dict(rcs)
    say("### 2-1. `SEL-S1` 누적 — 발표값(승계 셈법) + 같은 스냅샷 재계산 나란히\n")
    say("| 글 | S1 발표값 | S1 **이 스냅샷 재계산** | 일치? | 분모 규약 |")
    say("|---|---|---|---|---|")
    say(f"| 1~3번째(33건 중 등록일 특정 7건) | {PUB_33[0]} | —(재계산 대상 아님) | — | 🔴 또 다른 창 |")
    for lbl, key, k2, nn in (("4번째 6건", "post4_cal10", "post4", 6), ("5번째 6건", "post5_td5", "post5", 6),
                             ("6번째 10건", "post6_td5", "post6", 10), ("7번째 `exact` 6건", "post7_td5", "post7", 6),
                             ("8번째 `exact` 4건", "post8_td5", "post8", 4),
                             ("9번째 `exact` 5건", "post9_td5", "post9", 5)):
        ph, c = PUB[key][0], rc[k2]
        say(f"| {lbl} | {ph}/{nn} = {ph/nn*100:.1f}% | {c[0]}/{c[1]} = {c[0]/max(c[1], 1)*100:.1f}% | "
            f"{'✅' if (c[0], c[1]) == (ph, nn) else '🔴 **다름**'} | 신규 = `exact`"
            + ("(post7·8 은 신규 ≠ `exact`)" if k2 in ("post7", "post8") else "") + " |")
    say(f"| **10번째 `exact` {n10}건** | — | **{s1_hits}/{n10} = {s1_hits/n10*100:.1f}%** | — | 신규 {n10} = `exact` {n10} |")
    cum_h, cum_n = S1_CUM_PRIOR[0] + s1_hits, S1_CUM_PRIOR[1] + n10
    rh = 6 + sum(c[0] for _k, c in rcs) + s1_hits
    rn = 7 + sum(c[1] for _k, c in rcs) + n10
    say(f"| **누적**(승계 셈법 = 발표값 {S1_CUM_PRIOR[0]}/{S1_CUM_PRIOR[1]} + 이번) | **{cum_h}/{cum_n} = "
        f"{cum_h/cum_n*100:.1f}%** | 재계산 셈법(33건 열 6/7 + 재계산 6글 + 이번) = **{rh}/{rn} = {rh/rn*100:.1f}%** | — | — |")
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
    h_pass = h_hits * 2 >= n10
    say(f"\n⇒ **`P6-S1h` = {h_hits}/{n10} = {h_hits/n10*100:.1f}%** · 문턱 **>= 1/2** · 최소 n = {MIN_N} ⇒ "
        + ("**🟡 문턱 충족 — 단, 단조 완화 축이라 «증거 아님»**" if h_pass
           else "**❌ 불성립(⛔ 경로 발동 — 완화 축에서도 떨어졌다)**"))
    say("")
    say("### 3-1. 🔬 발표값 · 같은 스냅샷 재계산 — post4·post5 는 탐색적 표기 전용(누적 분모에 넣지 않는다)\n")
    say("| 글 | 고가 +15% 발표값 | **이 스냅샷 재계산** | 일치? | 지위 |")
    say("|---|---|---|---|---|")
    for lbl, key, st in (("4번째 6건", "post4", "소급 · 탐색"), ("5번째 6건", "post5", "소급 · 탐색"),
                         ("6번째 10건", "post6", "판정"), ("7번째 `exact` 6건", "post7", "판정"),
                         ("8번째 `exact` 4건", "post8", "판정"),
                         ("9번째 `exact` 5건", "post9", "판정")):
        ph, c = PUB_H[key], rc[key]
        say(f"| {lbl} | {ph[0]}/{ph[1]} = {ph[0]/ph[1]*100:.1f}% | {c[2]}/{c[1]} = {c[2]/max(c[1], 1)*100:.1f}% | "
            f"{'✅' if (c[2], c[1]) == ph else '🔴 **다름**'} | {st} |")
    say(f"| **10번째 `exact` {n10}건 — 판정 대상** | — | **{h_hits}/{n10} = {h_hits/n10*100:.1f}%** | — | 판정 |")
    hc_h, hc_n = H_CUM_PRIOR[0] + h_hits, H_CUM_PRIOR[1] + n10
    say(f"| **판정 누적**(post6~ · 발표값 {H_CUM_PRIOR[0]}/{H_CUM_PRIOR[1]} + 이번) | — | **{hc_h}/{hc_n} = "
        f"{hc_h/hc_n*100:.1f}%** | — | 🔴 누적은 **기록**(누적 문턱 없음) |")
    say("")
    say("🔴 **`SEL-S1` 의 기각을 무르지 않는다** — `P6-S1h` 통과를 「S1 이 측정자만 틀렸던 것」으로 읽지 않는다(§2-1 ①).")
    say("")

    # ── §4. 특징 백분위 ─────────────────────────────────────────────────────
    say("## §4. 특징 9개 백분위 (창 안 일별 백분위의 «최댓값»)\n")

    def rows_t(items, dff=df):
        return [(nm, c, reg) + stat_tdays(dff, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in items]
    rows10_t = rows_t(NEW10)
    rows10_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg in NEW10]
    rows8_t, rows7_t, rows6_t = rows_t(NEW8), rows_t(NEW7), rows_t(NEW6)
    rows9p_t = rows_t(NEW9)
    rows5_t, rows4_t = rows_t(NEW5), rows_t(NEW4)
    rows4_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg in NEW4]
    feat_table(f"4-1. 10번째 글 `exact` {n10}건 — **판정 창**(거래일 {W_TDAYS}일)", rows10_t)
    feat_table(f"4-2. 10번째 글 `exact` {n10}건 — 대조 창(달력 {W_CAL_POST4}일)", rows10_c)
    feat_table(f"4-2b. 9번째 글 `exact` 5건 — 판정 창 · **이 스냅샷 재계산**", rows9p_t)
    feat_table(f"4-3. 8번째 글 `exact` 4건 — 판정 창 · **이 스냅샷 재계산**", rows8_t)
    feat_table(f"4-4. 7번째 글 `exact` 6건 — 판정 창 · **이 스냅샷 재계산**", rows7_t)
    feat_table(f"4-5. 6번째 글 10건 — 판정 창 · **이 스냅샷 재계산**", rows6_t)
    feat_table(f"4-6. 5번째 글 6건 — 판정 창 · **이 스냅샷 재계산**", rows5_t)
    feat_table(f"4-7. 4번째 글 6건 — 판정 창 · **이 스냅샷 재계산**", rows4_t)
    feat_table(f"4-8. 4번째 글 6건 — 대조 창(달력 {W_CAL_POST4}일) · **이 스냅샷 재계산**", rows4_c)

    # ── §5. S2·S3·S4 판정 ───────────────────────────────────────────────────
    a10t, a10c = aggs(rows10_t), aggs(rows10_c)
    ag = {"post9": aggs(rows9p_t), "post8": aggs(rows8_t), "post7": aggs(rows7_t), "post6": aggs(rows6_t), "post5": aggs(rows5_t),
          "post4": aggs(rows4_t), "post4c": aggs(rows4_c)}
    s2, s3, s4, s3_n, s3_nan = a10t
    say(f"## §5. `SEL-S2`·`SEL-S3`·`SEL-S4` 판정 (판정 창 = 거래일 {W_TDAYS}일 · 분모 = `exact` {n10})\n")
    say(f"| 예측 | 문언(동결) | 문턱 (출처) | 최소 n | **이번(`exact` {n10}건)** | 판정 | ⛔ 판정 불가 조건 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| **`SEL-S2`** | `거래대금/시총` 백분위 중앙 | >= 95 (값만 기록) · `PREREG_SELECTION.md` §7 | {MIN_N} | **{fmt(s2)}** | "
        f"{'✅ 충족' if s2 >= 95 else '🟡 미달'} | 판정 건 < 3 (이번 {n10} ⇒ 미발동) |")
    say(f"| **`SEL-S3`** | `60일 최고종가 갱신` 백분위 중앙 | **< 90** (핵심·위반 시 기각) · `PREREG_SELECTION.md` §7 | {MIN_N} | "
        f"**{fmt(s3)}** (분모 {s3_n}/{n10} · NaN {s3_nan}) | ❌ **기각 유지**(`PREREG_POST6.md:408` 문형 · 부활 경로 없음 · 이번 값 {'문턱 아래' if s3 < 90 else '문턱 위'}) | 판정 건 < 3 · "
        f"C-17 수정 전이면 무효 ⇒ {'반영 ✅' if c17_ok else '🔴 미반영'} |")
    say(f"| **`SEL-S4`** | `시가총액` 백분위 중앙 | 40~80 (값만 기록) · `PREREG_SELECTION.md` §7 | {MIN_N} | **{fmt(s4)}** | "
        f"{'✅ 구간 내' if 40 <= s4 <= 80 else '🟡 구간 밖'} | 판정 건 < 3 (이번 {n10} ⇒ 미발동) |")
    same_dir = ((a10c[0] >= 95) == (s2 >= 95) and (a10c[1] < 90) == (s3 < 90) and (40 <= a10c[2] <= 80) == (40 <= s4 <= 80))
    say(f"\n대조 창(달력 {W_CAL_POST4}일) 값: S2 **{fmt(a10c[0])}** · S3 **{fmt(a10c[1])}** · S4 **{fmt(a10c[2])}** — 판정 창과 "
        f"{'**같은 방향**' if same_dir else '🔴 **다른 방향 ⇒ 창 의존**'}. 🔴 **판정은 동결 문언(거래일 5일)으로 선다.**")
    say("")
    say("### 5-1. 누적 — 🔴 **열마다 창·분모 규약·스냅샷이 다르다. 「N연속 재현」이라고 쓰지 않는다.**\n")
    say("| 예측 | 1~3번째(33건) | 4번째 발표(달력10) | 4번째 재계산 | 5번째 발표 | 5번째 재계산 | 6번째 발표 | 6번째 재계산 | "
        f"7번째 발표 | 7번째 재계산 | 8번째 발표 | 8번째 재계산 | 9번째 발표 | 9번째 재계산 | **10번째**(`exact` {n10}) |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k, lbl in ((2, "S2"), (3, "S3"), (4, "S4")):
        j = k - 2
        say(f"| {lbl} | {PUB_33[k - 1]} | {PUB['post4_cal10'][k]:.1f} | {fmt(ag['post4'][j])} | {PUB['post5_td5'][k]:.1f} | "
            f"{fmt(ag['post5'][j])} | {PUB['post6_td5'][k]:.1f} | {fmt(ag['post6'][j])} | {PUB['post7_td5'][k]:.1f} | "
            f"{fmt(ag['post7'][j])} | {PUB['post8_td5'][k]:.1f} | {fmt(ag['post8'][j])} | {PUB['post9_td5'][k]:.1f} | {fmt(ag['post9'][j])} | **{fmt(a10t[j])}** |")
    say("")
    say("⚠️ 「33건」 열은 잣대가 또 다르다(달력 6일 + 최대 15거래일 · 방향 참고만) · 🔴 `PREREG_POST6.md` §2-1 이 금지한 표현 "
        "「N연속 재현」을 쓰지 않는다 — 표본·스냅샷·측정 장치(C-17)·분모 규약이 움직였고, 이번엔 등록일 봉 " + f"{n_after}/{n10} 가 제도 경계 «후»다.")
    say("")
    say("### 5-2. 🔴 재계산 대조 — 원 발표값 ↔ 이 스냅샷 재계산\n")
    say("| 표본 | 창 | 예측 | 원 발표값 | 재계산 | 차 | 일치? | 비고 |")
    say("|---|---|---|---|---|---|---|---|")
    for tag, pubkey, agg, cw in (("4번째 글", "post4_td5", ag["post4"], f"거래일{W_TDAYS}"),
                                 ("4번째 글", "post4_cal10", ag["post4c"], f"달력{W_CAL_POST4}"),
                                 ("5번째 글", "post5_td5", ag["post5"], f"거래일{W_TDAYS}"),
                                 ("6번째 글", "post6_td5", ag["post6"], f"거래일{W_TDAYS}"),
                                 ("7번째 글", "post7_td5", ag["post7"], f"거래일{W_TDAYS}"),
                                 ("8번째 글", "post8_td5", ag["post8"], f"거래일{W_TDAYS}"),
                                 ("9번째 글", "post9_td5", ag["post9"], f"거래일{W_TDAYS}")):
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
    say("🔴 **과거 산출물을 다시 재지 않는다**(`PREREG_POST6.md` §5-1 5번) — 값이 달라져도 post4~post9 판정은 그대로 둔다(「나란히 인쇄」 의무 이행).")
    say("")
    say("### 5-3. `approx` 갈래 — **대상 없음**(`approx` 0 · PD-4 · PD-21)\n")
    say("- 🆕 **`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0)** — `exact` 갈래와 `approx` 포함 갈래가 같은 표본"
        f"(n {n10} = {n10})이라 갈릴 수 없다 · 독법 B 병기 자리 없음.")
    say("- `P6-W10`(무작위 «창» 귀무 · §1-4 창 규약 용도)은 `run_regday_post10.py` 소관이고 이번엔 창 규약 **미발동**(`approx` 0) · "
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
    for nm, code, reg, st, nb in rows10_t:
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
    say(f"\n⇒ **`f9` 원값 = 1 인 건 {n_raw1}/{n10}** · **NaN {n_nan}/{n10}** ⇒ **`SEL-S3` 중앙값 분모 = {s3_n}/{n10}**")
    say("")
    say("### 6-1. 🔴 C-17 대상 **0 예고**(PD-12) 확인\n")
    rawp = {}
    for nm, code, reg in NEW10:
        cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code=%s AND date >= %s AND date < %s", (code, UNIV_LO, reg))
        rawp[nm] = int(cur.fetchone()[0])
    pd12_ok = n_nan == 0 and rawp == PD12_PRIOR
    say("| 항목 | 값 | PD-12 예고 |")
    say("|---|---|---|")
    say("| 로드창(04-01~) 안 등록일 «직전» **DB 원시 행** | " + " · ".join(f"{k} {v}" for k, v in rawp.items())
        + " | " + " · ".join(f"{k} {v}" for k, v in PD12_PRIOR.items()) + " (전건 ≥ 109) |")
    say("| 같은 구간 **특징 계산 행**(`market_cap > 0` ∧ `close > 0`) | " + " · ".join(f"{k} {v}" for k, v in priors.items())
        + " | (예고 없음) |")
    say(f"| `f9_newhigh` NaN(`exact`) | **{n_nan}건** | **0** |")
    say("")
    say("- " + ("🟢 PD-12 예고와 **계산이 일치** ⇒ C-17 NaN 규약 대상 **0** · `SEL-S3` 분모 = " f"{s3_n}/{n10}."
                if pd12_ok else "🔴 PD-12 예고와 **다르다** — 그 사실을 그대로 적고 규약을 고치지 않는다."))
    thin = [k for k, v in priors.items() if v < 60]
    say("- " + (f"🔴 특징 계산 행 60 미만: {' · '.join(thin)} — 짧은 계열로 계산됐다(기록 · 규약 불변)." if thin
                else "🟢 특징 계산 행이 전건 60 이상 — post8 액스비스 같은 «짧은 특징 계열» 없음."))
    say("- 🔴 기업행위 건·거래정지 봉은 §1-0 `P10-기업행위봉` 줄에 있다 — 이 레인은 가격을 조정하지 않는다(규칙 불변 · 신고만).")
    say("- 🔴 한계: C-17 은 「완전 결측」만 잡고 「부분 결손」은 못 잡는다 · 「60봉」 = DB 에 남은 60행(`market_cap > 0`).")
    say("")

    # ── §7. P6-S1h-N + §5-2 유니버스 5열 ────────────────────────────────────
    say("## §7. `P6-S1h-N` (희소성 대칭 단언) + §5-2 유니버스 5열\n")
    say("> 문턱 **`n_up` 중앙 >= 30 ⇒ `P6-S1h` 는 「선정 규칙」으로 인용 금지** — 출처 `PREREG_D1_OOS.md` §4 **N2**.\n")
    say("| 종목 | 등록일 | `universe_mcap` | `universe_test` | `dropped` | `drop_rate` | `prev_bar_date` | **`n_up`** | "
        "본인이 `n_up` 안에? | `n_up` 안 `f1` 순위 | 백분위 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    nups, drops, ranks = [], [], []
    for nm, code, reg in NEW10:
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
    say(f"\n⇒ **1위인 건 {len(top1)}/{n10}**{(' — ' + ' · '.join(top1)) if top1 else ''} · **`n_up` 집합 «밖»인 건 "
        f"{len(outset)}/{n10}**{(' — ' + ' · '.join(outset)) if outset else ''}")
    if len(top1) < n10:
        say("🔴 **저자 종목이 1위가 아닌 건이 있다** ⇒ ***「어느 급등주냐」는 여전히 미해결***(`PREREG_POST6.md` §2-1 의무 문구).")
    say("")
    say("### 7-3. 죽은 가드 실측 점검 (`PREREG_POST6.md` §7-B #10)\n")
    say(f"`n_up` 이 **{len(set(nv))}개의 서로 다른 값** (범위 [{min(nv)}, {max(nv)}] · sd {n_sd:.2f}) ⇒ "
        + ("**🟢 상수가 아니다 — 가드는 살아 있다**" if len(set(nv)) > 1 else "**🔴 상수다 — 죽은 가드 후보**")
        + f" · 🔑 등록일은 **{len(set(d for _n, _c, d in NEW10))}일**뿐이다(같은 날 등록 건은 같은 `n_up`).")
    say("")

    # ── §8. 재진입 (항등 아님 · 9 ↔ 5) · 「샌즈 제외」 · 「기업행위 건 제외」(인쇄만) ──────────────
    say("## §8. 🔂 §1-5 재진입 민감도 (**항등 아님** · 9 ↔ 5) + 「샌즈 제외」·「기업행위 건 제외」(**인쇄만**)\n")
    flags = {nm: prior_flag(raw, c, d, REENTRY.get(c, [])) for nm, c, d in NEW10}
    say("> 🔴🔴 **판정 분모 안 §1-5 재진입 = 4**(범한퓨얼셀 · 서산 · 한켐 · 우리로 · PD-3) ⇒ 재진입 제외 표본 **5** ≠ 주 판정 표본 **9** — "
        "post9(0/5 항등)와 달리 **두 값이 판정을 가르면 🔴 「재진입 의존」**(`PREREG_POST6.md` §1-5 2 · `:284`).\n")
    say("| 종목 | 이번 등록일 | 직전 사이클 등록일(원장 실측) | **`P6-PRIOR_CYCLE_IN_WINDOW`**(계산 · PD-3 표) |")
    say("|---|---|---|---|")
    for nm, c, d in NEW10:
        pv = REENTRY.get(c)
        say(f"| {nm} | {d} | {' · '.join(pv) if pv else '없음'} | **{flags[nm]}** · {PD3_FLAG[nm]} "
            f"{'🟢' if flags[nm] == PD3_FLAG[nm] else '🔴 불일치'} |")
    say(f"\n⇒ **`P6-PRIOR_CYCLE_IN_WINDOW` = 1 인 건 {sum(flags.values())}/{n10}**(PD-3 「4/9」 · 의무 인쇄 · §1-5 3) · "
        "🔑 「제외」가 아니라 「이 건은 규칙상 통과할 수 없다」를 판정과 같은 무게로 인쇄하는 장치다.")
    say("")
    all_nm = {nm for nm, _c, _d in NEW10}
    re_keep = {nm for nm, c, _d in NEW10 if c not in REENTRY}
    sa_keep = all_nm - {SANDS}
    co_keep = all_nm - set(corp_k)

    def branch(keep):
        rr = [r for r in rows10_t if r[0] in keep]
        ak_ = aggs(rr)
        return dict(n=len(keep), s1=sum(1 for nm, _r, r in s1_rows if nm in keep and r and r["ret_c"] >= 0.15),
                    h=sum(1 for nm, _r, r in s1_rows if nm in keep and r and r["ret_h"] >= 0.15),
                    s2=ak_[0], s3=ak_[1], s4=ak_[2], med=float(np.median([x[2] for x in nups if x[0] in keep])))
    b_main, b_re, b_sa, b_co = branch(all_nm), branch(re_keep), branch(sa_keep), branch(co_keep)
    assert b_main["n"] == n10 and b_re["n"] == 5 and b_sa["n"] == 8
    lab = {  # 문턱 «방향» 라벨 — 판정 낱말 아님(S1·S3 는 기각 유지 문형이라 판정 라벨 없음 · 표본 방향만)
        "S1": lambda b: "문턱 위" if b["s1"] * 2 >= b["n"] else "문턱 아래",
        "S1h": lambda b: "문턱 충족" if b["h"] * 2 >= b["n"] else "불성립",
        "S2": lambda b: "충족" if b["s2"] >= 95 else "미달",
        "S3": lambda b: "문턱 아래" if b["s3"] < 90 else "문턱 위",
        "S4": lambda b: "구간 내" if 40 <= b["s4"] <= 80 else "구간 밖",
        "N": lambda b: "발동" if b["med"] >= N_DEGRADE else "미발동"}
    num = {  # 값만(판정 낱말 없음) — 「샌즈 제외」·「기업행위 건 제외」 답 칸용
        "S1": lambda b: f"{b['s1']}/{b['n']} = {b['s1']/b['n']*100:.1f}%",
        "S1h": lambda b: f"{b['h']}/{b['n']} = {b['h']/b['n']*100:.1f}%",
        "S2": lambda b: fmt(b["s2"]), "S3": lambda b: fmt(b["s3"]), "S4": lambda b: fmt(b["s4"]),
        "N": lambda b: f"중앙 {b['med']:.1f}"}
    names = {"S1": "`SEL-S1`", "S1h": "`P6-S1h`", "S2": "`SEL-S2`", "S3": "`SEL-S3`", "S4": "`SEL-S4`", "N": "`P6-S1h-N`"}
    thr = {"S1": ">= 1/2", "S1h": ">= 1/2", "S2": ">= 95", "S3": "< 90", "S4": "40~80", "N": f">= {N_DEGRADE} ⇒ 강등"}
    fixed_items = ("S1", "S3")   # 기각 유지 문형 — 판정이 갈릴 수 없다(방향만 기록)
    re_split = {k: (lab[k](b_main) != lab[k](b_re)) and k not in fixed_items for k in lab}
    dir_split = {k: lab[k](b_main) != lab[k](b_re) for k in fixed_items}
    dep_items = [names[k] for k in ("S1h", "S2", "S4", "N") if re_split[k]]
    reent_dep = bool(dep_items)
    dep_tag = {k: (" ⇒ 🔴 **재진입 의존**(§1-5 2 · 9↔5 두 값이 판정을 가름)" if re_split[k] else "") for k in lab}
    say("| 항목 | 문턱 | **`exact` 9건**(주 판정) | **§1-5 재진입 제외**(n 5) | 판정이 갈리나 | 「샌즈 제외」(n 8 · 인쇄만) | "
        f"「기업행위 건 제외」(n {b_co['n']} · 답(참고) · 세지 않는다) |")
    say("|---|---|---|---|---|---|---|")
    for k in ("S1", "S1h", "S2", "S3", "S4", "N"):
        if k in fixed_items:
            gap = ("🟡 표본 방향만 다르다(기록 · 판정은 기각 유지 문형이라 불변)" if dir_split[k] else "아니오(방향 같음 · 판정은 기각 유지 문형)")
        else:
            gap = "🔴 **예 — 재진입 의존**" if re_split[k] else "아니오"
        say(f"| {names[k]} | {thr[k]} | {num[k](b_main)} · {lab[k](b_main)} | {num[k](b_re)} · {lab[k](b_re)} | {gap} | "
            f"{num[k](b_sa)} | {num[k](b_co)}{' · 항등(k=0)' if not corp_k else ''} |")
    say("")
    say("⇒ 🔴 재진입 제외 갈래 n **5** ≥ 최소 n 3 ⇒ **계수 갈래**(항등 아님) · "
        + (f"🔴 **판정을 가르는 항목 {len(dep_items)}건: {' · '.join(dep_items)}** ⇒ 해당 칸에 「재진입 의존」 병기(§12)"
           if reent_dep else "🟢 두 값이 **어느 판정 항목도 가르지 않는다**(실측 · 항등이 아니라 «같은 방향») ⇒ 「재진입 의존」 미발동")
        + " · 「샌즈 제외」(🔒 #1 ⓐ)·「기업행위 건 제외」(`F-3`)는 **인쇄만**(계수 아님).")
    say("")

    # ── §9. 절단 가드 ───────────────────────────────────────────────────────
    say("## §9. `P6-절단가드-A`/`B` (`PREREG_POST6.md` §1-6 · PD-12)\n")
    trunc = [(nm, v) for nm, v in win20.items() if v[0] < WIN20]
    frac = len(trunc) / n10
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 분모 | **`exact` {n10}건** |")
    say(f"| 분자 = 창 `[D-19, D]` 봉수 **< {WIN20}** 인 건 | **{len(trunc)}**"
        + (" — " + " · ".join(f"{nm} {v[0]}/{v[1]}" for nm, v in trunc) if trunc else "") + " |")
    say(f"| 비율 | **{len(trunc)}/{n10} = {frac*100:.1f}%** · 문턱 **>= 1/3 ⇒ ⛔** |")
    say(f"| **`P6-절단가드-A`** | **{'🔴 발동 ⇒ ⛔ 판정 불가' if frac >= TRUNC_GUARD else '🟢 미발동'}** |")
    say("")
    say("🟢 PD-12 예고(*「`P6-절단가드-A` 분자 **0/9**」*)와 **" + ("계산이 일치" if not trunc else "🔴 다르다") + "**한다 · "
        + ("절단 제외 표본 = 전 표본 = **항등** ⇒ `P6-절단가드-B` **미발동(구성상)**." if not trunc else "🔴 절단 건이 있다 — 값 불변 인쇄."))
    say("⚠️ 문턱 `1/3` = `REC-Y3` 에서 «차용»(절단 비율에 검증된 값 아님) · 🔑 봉수는 전부 「등록일 «포함»」.")
    say("")

    # ── §10. D-5 갈래 계수표 ─────────────────────────────────────────────────
    say("## §10. `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나)2 · PD-23)\n")
    say("> 최소 n = **3**(동결값) · 🔴 **재진입 갈래 = 항등 아님**(9 ↔ 5 · 계수 갈래) · 「샌즈 제외」(🔒 #1 ⓐ)·「기업행위 건 제외」(`F-3` (나))는 "
        "**인쇄만 — 계수에 넣지 않는다** · 항등 갈래도 「항등」으로 인쇄 · `approx` 포함 갈래 = **없음**(`approx` 0 — 주와 같은 표본).\n")
    say("| 예측 | 갈래 이름 | n | 답 | 계수에 넣나 |")
    say("|---|---|---|---|---|")

    def ans_full(k, b):
        if k == "S1":
            return f"기각 유지(표본 {num[k](b)} · {lab[k](b)})"
        if k == "S3":
            return f"기각 유지(값 {num[k](b)}(분모 {s3_n}/{n10}) · {lab[k](b)})"
        if k == "S1h":
            return ("문턱 충족(단조 완화 축 · 증거 아님)" if lab[k](b) == "문턱 충족" else "불성립") + f" {num[k](b)}"
        if k == "N":
            return f"{lab[k](b)} {num[k](b)}"
        return f"{lab[k](b)} {num[k](b)}"
    cal_dir = {"S2": fmt(a10c[0]), "S3": fmt(a10c[1]), "S4": fmt(a10c[2])}
    for k in ("S1", "S1h", "S2", "S3", "S4", "N"):
        lbl = names[k]
        say(f"| {lbl} | 주 판정(`exact`) | {n10} | **{ans_full(k, b_main)}** | ✅ |")
        say(f"| {lbl} | §1-5 재진입 포함↔제외 | {n10} ↔ {b_re['n']} | **{ans_full(k, b_re)}**"
            + (" — 🔴 **판정이 갈린다(재진입 의존)**" if re_split[k] else " — 판정 같음(항등 아님 · 값은 다를 수 있다)") + " | ✅(계수 갈래) |")
        say(f"| {lbl} | 창 절단 포함↔제외 | {n10} ↔ {n10 - len(trunc)} | **항등**(절단 0) | ✅(= 주) |")
        say(f"| {lbl} | `approx` 포함 | {n10} | **항등**(`approx` 0 · 갈래 없음) | ✅(= 주) |")
        say(f"| {lbl} | 「샌즈 제외」(🔒 #1 ⓐ) | {b_sa['n']} | {num[k](b_sa)} — 인쇄만 | ❌(🔒 #1 ⓐ 인쇄만) |")
        say(f"| {lbl} | 「기업행위 건 제외」(`F-3`) | {b_co['n']} | 답(참고) · 세지 않는다 — {num[k](b_co)}"
            + (" · 항등(k=0 ⇒ 주와 같은 표본)" if not corp_k else "") + " | ❌(계수 아님 · `F-3` (나)) |")
        if k in cal_dir:
            say(f"| {lbl} | 대조 창(달력 10일 · 판정에 안 씀) | {n10} | {cal_dir[k]} — {'같은 방향' if same_dir else '다른 방향'} | ❌(판정 창 아님) |")
    say("")
    say("⇒ **계수 결과**: 최소 n 을 채운 갈래(재진입 제외 n 5)에서 «판정» 답이 갈린 예측 = **"
        + (" · ".join(dep_items) if dep_items else "없음") + "** · 나머지 갈래는 전부 주와 같은 표본(항등) 또는 인쇄만.")
    say("")

    # ── §11. D-9 혼합 빈티지 신고 + 대조 적재 ─────────────────────────────────
    say("## §11. `D-9` · `P8-혼합빈티지신고` + 10-02 봉 영향 대조 (PD-27 (마) 4 · (바))\n")
    say(f"> 이 레인의 창 = 판정 창 `[D-4, D]` · 절단 가드 창 `[D-19, D]` · 유니버스 적재 창 `[{UNIV_LO}, {DB_UPTO}]` — **걸치는 창마다 한 줄** "
        "+ 「전부 경계 후」 창은 **추가 한 줄**(PD-27 (바) 재량 · 판정 효과 0).\n")
    say("| 건 | 창 | 시작 | 끝 | 경계 전 봉 | 경계 후 봉 | 걸침? |")
    say("|---|---|---|---|---|---|---|")
    cross_lines, after_lines, before_lines, x19 = [], [], [], {}
    for nm, c, d in NEW10:
        for wlab, n in (("`[D-4, D]`", W_TDAYS), ("`[D-19, D]`", WIN20)):
            s = own_split(raw, c, d, n)
            crossed = s[2] > 0 and s[3] > 0
            if crossed:
                cross_lines.append(mixed_line(s[0], s[1], s[2], s[3]) + f" ({nm} {wlab})")
                if n == WIN20:
                    x19[nm] = (s[2], s[3])
            elif s[2] == 0:
                after_lines.append(f"창 `[{s[0]}, {s[1]}]` 은 전부 제도 경계 후(전 0 / 후 {s[3]}) ({nm} {wlab})")
            elif s[3] == 0:
                before_lines.append(f"창 `[{s[0]}, {s[1]}]` 은 전부 제도 경계 전(전 {s[2]} / 후 0) ({nm} {wlab})")
            say(f"| {nm} | {wlab} | {s[0]} | {s[1]} | {s[2]} | {s[3]} | {'🔴 걸침' if crossed else ('🟡 전부 후' if s[2] == 0 else ('🟡 전부 전' if s[3] == 0 else '안 걸침'))} |")
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
    say("**추가 줄**(「전부 경계 후」·「전부 경계 전」 · PD-27 (바) 재량):\n")
    for ln in after_lines + before_lines or ["(해당 창 없음)"]:
        say(f"- {ln}")
    say("")
    x19_ok = len(x19) == 8 and "서산" not in x19 and any("서산 `[D-19, D]`" in ln for ln in before_lines)
    say(f"⇒ **`[D-19, D]` 걸침 = {len(x19)}건**(INTAKE §5 예고 = 걸침 8줄 + 서산 「전부 경계 전」 줄) — "
        + ("🟢 일치" if x19_ok else f"🔴 불일치 {x19}") + " · `[D-4, D]` 는 계산값 인쇄(예고 열 없음).")
    say(f"- 기록: 등록일 봉 자체가 제도 경계 «후»인 건 **{n_after}/{n10}** — `SEL-` 판정 창(등록일 봉)은 `:546` 이름 목록에 없어 "
        "신고 의무 대상 밖 · 재량 인쇄(PD-27 (바)).")
    df_cut = build_features(load_ext(DB_UPTO_CUT))
    r10_cut = rows_t(NEW10, df_cut)
    a_cut = aggs(r10_cut)
    maxdiff = 0.0
    for (_n1, _c1, _r1, st1, _b1), (_n2, _c2, _r2, st2, _b2) in zip(rows10_t, r10_cut):
        for f in FEATS:
            v1, v2 = st1[f], st2[f]
            if (v1 != v1) and (v2 != v2):
                continue
            maxdiff = max(maxdiff, abs(v1 - v2) if (v1 == v1 and v2 == v2) else float("inf"))
    same_cut = (a_cut[:3] == a10t[:3]) and maxdiff == 0.0
    say(f"- **10-02 봉 영향 대조**(PD-27 (마) 4 — 「`SEL-` 은 유니버스를 `DB_UPTO` 까지 적재」): 유니버스를 **{DB_UPTO_CUT}**(최대 등록일) "
        f"까지만 적재해 다시 쟀다 — 특징 백분위 최대 절대차 **{maxdiff:.4f}** · S2/S3/S4 = {fmt(a_cut[0])} / {fmt(a_cut[1])} / "
        f"{fmt(a_cut[2])} ↔ 주 {fmt(s2)} / {fmt(s3)} / {fmt(s4)} ⇒ "
        + ("**🟢 동일 — 09-30~10-02 봉은 이 레인의 판정값에 들어가지 않는다**" if same_cut else "**🔴 다르다 — 조사 대상(값 불변 인쇄)**")
        + " · 🔴 단 등록일 봉이 제도 경계 «후»인 건(위 기록 줄)의 봉은 **들어간다**.")
    say("- 🔴 방향 추론(「`H` 를 높이고 `L` 을 낮춘다」)은 실측으로 인용하지 않는다 · 한계(PD-27 (바) 옮김 · post9 판 계승): `ovtm_vol` 09-14~09-21 전부 0 · "
        "`overtime_daily` 09-22 이후 행 없음 · 15:30 분봉 ≤ 1/301 ⇒ **「정규장만」 갈래 없음**.")
    say("")

    # ── §12. 판정 요약 ──────────────────────────────────────────────────────
    say("## §12. 판정 요약 — `PREREG_POST6.md` §4 #1~#6·#11 형식 (등급 열 없음)\n")
    say(f"| # | 항목 | 문턱 (출처 파일) | 최소 n | 값(`exact` {n10}) | **판정** | 대칭/반증 쌍 | ⛔ 경로 · 민감도 |")
    say("|---|---|---|---|---|---|---|---|")
    def exs(k):
        return (f"재진입 제외 {num[k](b_re)} · 「샌즈 제외」 {num[k](b_sa)}(인쇄만) · 「기업행위 건 제외」 {num[k](b_co)}"
                "(답(참고) · 세지 않는다) · 절단·`approx` **항등**")
    cells = {}
    say(f"| 1 | `SEL-S1` | >= 1/2 · `PREREG_SELECTION.md` §7 | {MIN_N} | {s1_hits}/{n10} = {s1_hits/n10*100:.1f}% | "
        "❌ **기각 유지**(`PREREG_POST6.md` §2-1 · 부활 경로 없음) | `SEL-S3` | 판정 건 < 3(미발동) · " + exs("S1") + " |")
    v2_ = "🟡 **문턱 충족 — 단조 완화 축이라 «증거 아님»**" if h_pass else "❌ **불성립**"
    if degrade and h_pass:
        v2_ += " ⇒ #3 발동으로 **인용 금지 강등**"
    cells["S1h"] = v2_ + dep_tag["S1h"]
    say(f"| 2 | `P6-S1h` | >= 1/2 · `PREREG_SELECTION.md` §7(상속) | {MIN_N} | {h_hits}/{n10} = {h_hits/n10*100:.1f}% | {cells['S1h']} | "
        "`P6-S1h-N` | 🔴 통과는 증거 아님 · " + exs("S1h") + " |")
    v3_ = "🔴 **발동 ⇒ `P6-S1h` 인용 금지(강등)**" if degrade else "🟢 **미발동**"
    cells["N"] = v3_ + dep_tag["N"]
    say(f"| 3 | `P6-S1h-N` | >= {N_DEGRADE} → 인용 금지 · `PREREG_D1_OOS.md` §4 | — | 중앙 {n_med:.1f} · 범위 [{min(nv)}, {max(nv)}] · "
        f"sd(`ddof=1`) {n_sd:.2f} | {cells['N']} | 자신이 반증축 | `drop_rate >= 1%` {len(bad_days)}일 · " + exs("N") + " |")
    for no, key, lbl, th, val, ok_s, pair, extra in (
            (4, "S2", "`SEL-S2`", ">= 95 · `PREREG_SELECTION.md` §7", fmt(s2), "✅ **충족**" if s2 >= 95 else "🟡 **미달**", "`SEL-S4`", ""),
            (5, "S3", "`SEL-S3`", "**< 90** · `PREREG_SELECTION.md` §7", f"{fmt(s3)} (분모 {s3_n}/{n10})",
             "❌ **기각 유지**(`PREREG_POST6.md:408` 문형 · 부활 경로 없음 · (다) ⛔ 미적용)", f"`f9` 원값 1 건수 = **{n_raw1}/{n10}**",
             f"C-17 {'반영 ✅' if c17_ok else '🔴 미반영'} · "),
            (6, "S4", "`SEL-S4`", "40~80 · `PREREG_SELECTION.md` §7", fmt(s4), "✅ **구간 내**" if 40 <= s4 <= 80 else "🟡 **구간 밖**",
             "`SEL-S2`", "")):
        cells[key] = ok_s + dep_tag[key]
        say(f"| {no} | {lbl} | {th} | {MIN_N} | {val} | {cells[key]} | {pair} | {extra}{exs(key)} |")
    say(f"| 11 | `REG-M4` | 기록 · `PREREG_REGDAY_MEASURE.md` §4-4 | — | `n_up` 중앙 {n_med:.1f} · 범위 [{min(nv)}, {max(nv)}] | "
        "🟡 **기록만**(대칭 단언 · 판정 아님) | 자신이 반증축 | 이 표의 `n_up` 은 `P6-S1h-N` 과 **같은 계산**이다 |")
    say("")
    say("### 12-1. 🔴 배선 점검 — 발화한 가드가 판정 칸에 «실제로» 걸렸는가\n")
    say("| 가드 | 상태 | 걸려야 하는 판정 칸 | 칸에 반영됐나 |")
    say("|---|---|---|---|")
    wires = [
        ("`P6-S1h-N`(n_up 중앙 ≥ 30)", "발동" if degrade else "미발동", "#2 `P6-S1h`",
         (not degrade) or (not h_pass) or ("인용 금지 강등" in cells["S1h"])),
        ("`P6-절단가드-A`", "발동" if frac >= TRUNC_GUARD else "미발동", "#1~#6", frac < TRUNC_GUARD),
        ("`P6-절단가드-B`", "미발동(항등)" if not trunc else "확인 필요", "#1~#6", not trunc),
        ("`drop_rate ≥ 1%`", "발동" if bad_days else "미발동", "#3 비교 금지 문구", True),
        ("C-17 반영", "반영" if c17_ok else "미반영", "#5 `SEL-S3`", c17_ok),
        ("`D-3` (나)4 정밀도 의존 · `P9-공통독법`", "대상 없음(`approx` 0)", "없음", True),
        ("§1-5 재진입 의존(9↔5)", ("발동 — " + " · ".join(dep_items)) if reent_dep else "미발동(두 값이 판정을 가르지 않음)",
         "#2·#3·#4·#6", all(("재진입 의존" in cells[k]) == bool(re_split[k]) for k in ("S1h", "N", "S2", "S4"))),
        ("`SEL-S3` 기각 유지 문형(`F-3` (나)7)", "(가) 채택 · (다) ⛔ 미적용", "#5", "기각 유지" in cells["S3"] and "⛔" not in cells["S3"].replace("⛔ 미적용", "")),
        ("「샌즈 제외」(🔒 #1 ⓐ)·「기업행위 건 제외」(`F-3`)", "인쇄만", "없음(판정 효과 없음)", True),
    ]
    for g, s_, tgt, okw in wires:
        say(f"| {g} | {s_} | {tgt} | {'🟢 예' if okw else '🔴 **아니오 — 배선 결함**'} |")
    assert all(w[3] for w in wires), "배선 결함"
    say("")
    say(f"🔴 **이 문서에서 처음 정한 문턱에 걸렸는가**(`PREREG_POST6.md` §9): `drop_rate >= 1%` 가드 = **{'발동' if bad_days else '미발동'}**.")
    say("")

    # ── §13. 의무 체크리스트 ────────────────────────────────────────────────
    say("## §13. `PREREG_POST8.md`·`PREREG_POST9.md`·`PREREG_POST10.md` 인쇄 의무 체크리스트 (가분성 §0-5-1)\n")
    say("| 의무 | 이 레인 해당 | 자리 |")
    say("|---|---|---|")
    for a, b, c in (("`D-1`·`D-2`·`D-4`·`D-7`·`D-10`·`D-11`", "해당 없음(다른 레인 · 등급 없음 · `Q1-R2` 미인용)", "—"),
                    ("`D-3`(`P8-approx의존신고`)", "**해당**", "§0-2"), ("`D-5`(`P8-갈래계수` 세 쪽)", "**해당** — 재진입 갈래 항등 아님(9↔5)", "§8 · §10"),
                    ("`D-6`(`ddof=1` 표기)", "**해당**", "§0-2 · §7-1"), ("`D-8`(`prog_ver` 수준 목록) · `P9-결측분리`", "해당 없음(공변량 미사용)", "§0-2"),
                    ("`D-9`(①~⑤)", "**해당**", "머리 · §0-1 · §11"),
                    ("🆕 `P9-공통독법`(신고 줄)", "**해당** — 답 = 판정 · 대상 없음(`approx` 0)", "§0-2 · §5-3"),
                    ("🆕 `P9-행단위`", "해당 없음(수준 목록 없음) — 줄 인쇄", "§0-2"),
                    ("🆕 `P9-스탬프통일`(`selection_post10/read_stamp.json`)", "**해당**", "머리 · §0-1"),
                    ("🆕 `SEL-S3` 기각 유지 문형(`PREREG_POST10.md` §3 (나)7)", "**해당**", "§5 · §12"),
                    ("🆕 `P6-PRIOR_CYCLE_IN_WINDOW` 4/9 의무 인쇄", "**해당**", "§8"),
                    ("🆕 `P9-WRC누적분모`·`P9-갈래게이트인쇄전용`·`P9-수집증거`", "해당 없음", "§0-2"),
                    ("라이브 채택 금지(`PREREG_POST10.md` §0-1 문언 그대로)", "**해당**", "머리"),
                    ("🆕 `F-3` `P10-기업행위봉` 신고 줄 + 「기업행위 건 제외」 갈래", "**해당**", "§1-0 · §8 · §10")):
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
