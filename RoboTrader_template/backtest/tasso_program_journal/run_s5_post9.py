# -*- coding: utf-8 -*-
"""`S5` 재무·뉴스 OOS — **9번째 글** · **2번째 판정 회차** (post8 판 승계 · 얇은 판).

동결 준거(1순위 · 값 보기 «전»에 다시 읽었다):
  · `PREREG_S5_FUND_NEWS_OOS.md` v0.3 §1 · §1-1 · §2(라벨 3개 · Holm +0) · §3 — 이 스크립트는 그 파일을 읽지도 쓰지도 않는다
  · `FREEZE_S5_2026-09-16.md`(`96beddc`) §3 순서 증거 · §6 라벨 선언
  · `PREREG_POST9.md`(동결 `702f41b`) §0-1 · §1 `P9-공통독법` · §4 `P9-행단위` · §5 `P9-수집증거` · §6 (라)(스탬프 통일은 post10 부터)
  · `PREREG_POST8.md` §3(`D-3`) · §5(`D-5`) · §9(`D-9`) · §12(`D-12`) · :829 · §0-5-1(가분성)
  · `PREDECISION_2026-09-24_post9.md` PD-0 · PD-1 · PD-4 · PD-15 · PD-21 · PD-23 · PD-27 · PD-30 · PD-31
  · `INTAKE_2026-09-24_post9.md` §1(코드) · §2-19 · §5 「S5」 행 · 원장 `30aed89`(post9 6행 · 종목코드 열 없음 ⇒ 코드는 INTAKE §1 표)
승계(원본 불변 · import): `run_s5_post8.py` — `s5_label`·`final_label`·`ctrl_rate`·`CtrlCache`·`select_cases`·`fin_counts`·
  `pit_cutoff`·`assert_labels_only_in_verdict`·`assert_no_grade_names`·라벨 상수 / `run_s5_post7.py` — `pit_row`·`loss_rate`·
  `news_hits`·`assert_both_n`·`news_defer_lines`·`sparsity_lines`·`CONTAM`. 🔴 판정 로직 새로 쓰기 0.

이번 회차의 갈림(계산 «전»에 적는다 · 값 아님):
  S5-R9-1 판정 분모 = post9 신규 ∧ `exact` = **5**(삼미금속 · 에스투더블유 · 빛샘전자 · 한국첨단소재 · 한컴위드) ·
      `approx` 0 · `after` 0 · `none` 신규 0 · 후속 1(우리기술 · 등록일 축 밖 · PD-2).
  S5-R9-2 PIT = `status='000'` ∧ `rcept_dt <= 2026-09-23`(글 게시일) · 가장 최근 사업연도 «하나».
  S5-R9-3 대조군 셈법 네 개 전부 인쇄 · 네 라벨이 같으면 그 라벨 · 다르면 「판정 불가·모호」(post8 S5-R8-4 그대로 ·
      정본 셈법은 미결 이월 `PREREG_POST9.md` §7 #13 ㉯).
  S5-R9-4 `D-3` (나)4 = **대상 없음**(`approx` 0 ⇒ `approx` 포함 갈래가 생기지 않는다 · PD-21) · `P9-공통독법` 신고 줄.
  S5-R9-5 `P9-수집증거` — ①②③ 세 줄 + 빈 결과 줄 + 기록 줄을 git·원문 보관본에서 «읽어» 인쇄 · 기계 검사 거짓이면
      「그 회차 `S5` 순서 증거 미비」 ⇒ 판정 미개방(`PREREG_POST9.md` §5 (나)3 · `PREREG_POST8.md:829`).
  S5-R9-6 `D-9` ① = `s5_post9/read_stamp.json`(지문 같으면 다시 쓰지 않는다 · ANC post8 B-B1 관용) — 🔴 공통 지시에 따른
      «더 많이 인쇄» · `P9-스탬프통일`(post10 부터) 적용이 **아니다**(PREREG_POST9 §6 (라)). post8 판의 「실행일」 줄은 뺐다.
  S5-R9-7 post8 표본은 같은 스냅샷에서 **값만** 재계산(post8 행 = 재판정 안 함 · 소급 금지) · post8+post9 합산 0.

🔴 등급 이름 0 · 라이브 채택 아님 · 라이브 트리 import 0 · DB `SELECT` 만 · `adj_factor` 산술 0 · 난수 0.
🔴 산출물 = `RESULTS_S5_POST9_NUMBERS.md` + `s5_post9/read_stamp.json` — 산문 `RESULTS_S5_POST9.md` 는 사람이 쓴다.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path

import psycopg2

import run_s5_post7 as S7
import run_s5_post8 as S8
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
KST = timezone(timedelta(hours=9))
OUT_NAME = "RESULTS_S5_POST9_NUMBERS.md"
STAMP_DIR = "s5_post9"

# ── 이번 회차 상수 (INTAKE §1·§5 · PD-1 · PD-4 · PD-15 · PD-27 — 여기서 고르지 않는다) ─────
POST_LOG = "224421214462"
POST_DATE = "2026-09-23"        # 글 게시일(수 · 거래일) — PIT 절단면
DB_UPTO = "2026-09-23"          # PD-1 · 창 종료 = 발행 당일 봉 «포함» · 전 축
PIT_CUTOFF = POST_DATE
MIN_JUDGEABLE = S8.MIN_JUDGEABLE   # 3 (동결 · §1 `:15`)
BAND_PP = S8.BAND_PP               # 10 (동결 · §2)
VINTAGE_BOUNDARY = "2026-09-14"
DPLUS1_SWEEP = "2026-09-28 15:35"  # 09-23 봉의 D+1 sweep(PD-27 (마) 2)
WIN_START = "2026-08-07"           # PD-27 (다) 창 시작일(가장 이른 `[D−19, D]` 시작)
HOLIDAYS_NEAR = {"2026-09-24", "2026-09-25"}   # `utils/korean_holidays.py:69-75` 읽기 전용 참조(표기용)

# 🔴 `PREREG_POST9.md:39` 문언 «그대로»(§0-1 · §8-3 #20) — 시험이 그 줄과 byte 대조한다
LIVE_BAN = ("*「🔴 **라이브 채택 금지.** 저자가 *\"사람이 할 일은 종목 고르는 것까지\"* 라고 적었다. "
            "후보 선정이 재량이면 규칙을 복원해도 자동화 대상이 아니다. 이 검정의 산출물은 **기록**이지 "
            "전략 후보가 아니다.」*")
WINDOW_LINE = ("창 종료 2026-09-23 = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
               "전 축(`WRC-` 포함) · PD-1")

# ── 표본 (`INTAKE_2026-09-24_post9.md` §1 표 «그대로» · 항목 순서) ──────────────
EXACT5 = [
    ("삼미금속", "012210", "2026-09-04"),
    ("에스투더블유", "488280", "2026-09-10"),
    ("빛샘전자", "072950", "2026-09-14"),        # 등록일 = 연장 제도 첫날
    ("한국첨단소재", "062970", "2026-09-15"),    # PD-31 기업행위·거래정지 공시(확인 5 · 신고 줄)
    ("한컴위드", "054920", "2026-09-15"),
]
APPROX = []                                      # PD-4 — `approx` 0
FOLLOWUP1 = [("우리기술", "032820")]             # PD-2 — post8 #10 후속 · 등록일 축 밖

# ── `P9-수집증거` 입력 (PREREG_POST9 §5 (나) · PD-0) ─────────────────────────
FREEZE_FILE = "FREEZE_S5_2026-09-16.md"
PREDECISION_FILE = "PREDECISION_2026-09-24_post9.md"
RAW_FILES = ("post_224421214462.html", "post_224421214462.txt", "post_224421214462_images.json")
ARCHIVE = Path("D:/archive/tasso-program-journal-20260923")
REL = "RoboTrader_template/backtest/tasso_program_journal/"

LABELS = S8.LABELS
AMBIG = S8.AMBIG
VERDICT_BEGIN, VERDICT_END = S8.VERDICT_BEGIN, S8.VERDICT_END


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


pp, ppd = S8.pp, S8.ppd


# ══════════════════════════════════════════════════════════════════════════════
# 가드
# ══════════════════════════════════════════════════════════════════════════════
REQUIRED_MARKERS = (
    WINDOW_LINE, "실행 시 `max(date)`", LIVE_BAN,
    "D-9 ①", "D-9 ②", "D-9 ③", "D-9 ④", "D-9 ⑤",
    "`approx` 포함 시 최소 n 이 차는 축:", "D-5 갈래", "주 표본 n", "민감도 판 n",
    "`P9-공통독법`: 답 = 판정 · (나)4 결과 = ", "`P9-수집증거`", "`P9-행단위`",
    "Holm 가족", "max(rcept_dt)", "라이브 채택 대상이 아니다",
)


def assert_duties(lines):
    """🔴 인쇄 의무(`PREREG_POST8.md` §0-5-1 가분성 · `PREREG_POST9.md` §1 (나)3 · §5 · §8-3 #19·#20)."""
    body = "\n".join(lines)
    miss = [m for m in REQUIRED_MARKERS if m not in body]
    if miss:
        raise AssertionError("🔴 인쇄 의무 누락: %s" % miss)
    m = re.search(r"`P9-공통독법`: 답 = (\S+)", body)
    if not m or m.group(1) != "판정":
        raise AssertionError("🔴 `P9-공통독법` 기계 검사 — 「답 =」 뒤 낱말이 「판정」이 아니다(§1 (나)4)")
    return True


def ledger_rows(path=None):
    p = Path(path) if path else BASE / "ledger_trades.csv"
    with p.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r["post_log_no"] == POST_LOG]


def assert_ledger_matches(rows):
    """🔴 상수가 원장(`30aed89`)과 같은가 — 이름·등록일·정밀도·후속·프로그램 버전(빈 칸 = missing)."""
    ex = sorted((r["stock_name"], r["reg_date"]) for r in rows if r["reg_date_precision"] == "exact")
    errs = []
    if ex != sorted((n, d) for n, _c, d in EXACT5):
        errs.append(f"exact {ex}")
    if any(r["reg_date_precision"] in ("approx", "after") for r in rows):
        errs.append("approx/after 가 있다")
    no = sorted(r["stock_name"] for r in rows if r["reg_date_precision"] == "none")
    if no != sorted(n for n, _c in FOLLOWUP1):
        errs.append(f"none {no}")
    if len(rows) != 6 or {r["prog_ver"] for r in rows} != {""} or {r["post_date"] for r in rows} != {POST_DATE}:
        errs.append(f"rows {len(rows)} · prog_ver {sorted({r['prog_ver'] for r in rows})}")
    if errs:
        raise AssertionError("🔴 상수 ↔ 원장 불일치: " + " · ".join(errs))
    return True


# ══════════════════════════════════════════════════════════════════════════════
# `P9-수집증거` — git·원문 보관본에서 «읽는다» (쓰기 0 · 결정적)
# ══════════════════════════════════════════════════════════════════════════════
def git(*a):
    r = subprocess.run(["git", *a], cwd=str(BASE), capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout.strip()


def md5_file(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def collect_evidence():
    """`PREREG_POST9.md` §5 (나)1~4 — 반환 dict(rows=[(줄, 명령·출처, 실측, 검사)], ok, reasons)."""
    _rc, fz = git("log", "--diff-filter=A", "--format=%h %ci", "--", FREEZE_FILE)
    _rc, pdz = git("log", "--diff-filter=A", "--format=%h %ci", "--", PREDECISION_FILE)
    fz_sha, fz_time = (fz.split(" ", 1) + [""])[:2] if fz else ("", "")
    pd_sha, pd_time = (pdz.split(" ", 1) + [""])[:2] if pdz else ("", "")
    anc = bool(fz_sha and pd_sha) and git("merge-base", "--is-ancestor", fz_sha, pd_sha)[0] == 0
    _rc, head = git("show", f"{pd_sha}:{REL}{PREDECISION_FILE}") if pd_sha else (1, "")
    head12 = "\n".join(head.splitlines()[:12])
    mf = re.search(r"관리자 실행 \*\*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) KST\*\*", head12)
    fetch = mf.group(1) if mf else None
    md5_rows = {f: m.group(1) for f in RAW_FILES
                for m in [re.search(r"^\| `" + re.escape(f) + r"` \| `([0-9a-f]{32})` \|", head12, re.M)] if m}
    arch = {f: (md5_file(ARCHIVE / f) if (ARCHIVE / f).exists() else None) for f in RAW_FILES}
    md5_ok = len(md5_rows) == 3 and all(md5_rows[f] == arch[f] for f in RAW_FILES)
    html = ARCHIVE / RAW_FILES[0]
    ma = re.search(r'addDate="(\d+)"', html.read_text(encoding="utf-8", errors="replace")) if html.exists() else None
    pub = (datetime.fromtimestamp(int(ma.group(1)) / 1000, KST).strftime("%Y-%m-%d %H:%M:%S") if ma else None)
    fz_kst = fz_time[:19] if fz_time else ""
    pub_ok = bool(pub and fz_kst and pub > fz_kst)
    _rc, raw_add = git("log", "--oneline", "--diff-filter=A", "--", RAW_FILES[0])
    _rc, remote = git("branch", "-r", "--contains", pd_sha) if pd_sha else (1, "")
    rows = [
        ("③ FREEZE 추가 커밋", f"`git log --diff-filter=A --format='%h %ci' -- {FREEZE_FILE}`",
         f"`{fz or '—'}`", "—"),
        ("① PREDECISION 추가 커밋", f"`git log --diff-filter=A --format='%h %ci' -- {PREDECISION_FILE}`",
         f"`{pdz or '—'}`", f"`git merge-base --is-ancestor {fz_sha} {pd_sha}` = **{'참' if anc else '거짓'}**"),
        ("② fetch 시각 + md5 3줄", f"`git show {pd_sha}:…/{PREDECISION_FILE}` 머리 12줄(추가 커밋판)",
         f"fetch **{fetch or '—'} KST** · md5 줄 **{len(md5_rows)}/3** — "
         + " · ".join(f"`{f.split('_', 2)[-1]}` `{(md5_rows.get(f) or '—')[:8]}…`" for f in RAW_FILES),
         f"보관본 `{ARCHIVE.as_posix()}/` md5 와 **{'3/3 일치' if md5_ok else '불일치/부재'}**"),
        ("③ 서버 발행 시각", f"보관본 html `addDate`(md5 `{(arch[RAW_FILES[0]] or '—')[:8]}…`) 환산 KST",
         f"**{pub or '—'} KST**", f"> ③ 커밋 시각 {fz_kst or '—'} = **{'참' if pub_ok else '거짓'}**"),
        ("원문 추가 커밋 명령(`FREEZE_S5_2026-09-16.md:91`)",
         f"`git log --oneline --diff-filter=A -- {RAW_FILES[0]}`",
         "**빈 결과**" if not raw_add else f"🔴 비어 있지 않음 `{raw_add}`",
         "빈 결과 · 원문 커밋 금지 `README.md:27-29` — 🔴 **위반 아님**(§5 (나)2) · 통과로도 세지 않는다"),
        ("기록 줄(통과 조건 아님)", f"`git branch -r --contains {pd_sha}`",
         "원격 있음(비어 있지 않음)" if remote else "제3자 타임스탬프 없음(미푸시)", "— (§5 (나)4)"),
    ]
    reasons = [x for x, bad in (("① 후손 관계 거짓", not anc), ("② md5 3줄 부재/불일치", not md5_ok),
                                ("③ 발행 시각 ≤ ③ 커밋 시각", not pub_ok)) if bad]
    return dict(rows=rows, ok=not reasons, reasons=reasons, fetch=fetch, pub=pub, pd=(pd_sha, pd_time),
                fz=(fz_sha, fz_time))


# ══════════════════════════════════════════════════════════════════════════════
# `D-9` ① stamp (ANC post8 B-B1 관용 · 지문 같으면 다시 쓰지 않는다)
# ══════════════════════════════════════════════════════════════════════════════
def read_stamp(cur, read_dates, base=None):
    cur.execute("SELECT max(date) FROM daily_prices")
    mx = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (mx,))
    mx_rows = int(cur.fetchone()[0])
    cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices WHERE date BETWEEN %s AND %s",
                (WIN_START, DB_UPTO))
    w_n, w_min, w_max = cur.fetchone()
    cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices WHERE date = ANY(%s)",
                (sorted(set(read_dates)),))
    r_n, r_min, r_max = cur.fetchone()
    cur.execute("SELECT count(*), max(rcept_dt), max(created_at) FROM dart_financials_asfiled")
    f_n, f_rc, f_cr = cur.fetchone()
    fp = dict(max_date=str(mx), max_rows=mx_rows, win=[WIN_START, DB_UPTO], win_n=int(w_n), win_min_u=str(w_min),
              win_max_u=str(w_max), read_dates=sorted(set(read_dates)), read_n=int(r_n), read_min_u=str(r_min),
              read_max_u=str(r_max), fin_rows=int(f_n), fin_max_rcept=str(f_rc), fin_max_created=str(f_cr))
    cur.execute("SELECT to_char(now() AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')")
    now_kst = cur.fetchone()[0]
    d = (base or BASE) / STAMP_DIR
    p = d / "read_stamp.json"
    prev = None
    if p.exists():
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = None
    if prev and prev.get("fingerprint") == fp and prev.get("first_read_kst"):
        return prev["first_read_kst"], now_kst, True, fp
    d.mkdir(exist_ok=True)
    p.write_text(json.dumps(dict(fingerprint=fp, first_read_kst=now_kst, timezone="Asia/Seoul"),
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return now_kst, now_kst, False, fp


def next_sweep(max_date):
    d = datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=1)
    while d.weekday() >= 5 or d.strftime("%Y-%m-%d") in HOLIDAYS_NEAR:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d") + " 15:35 예정"


# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:      # noqa: C901, PLR0912, PLR0915
    t0 = time.time()
    run_dt = datetime.now(KST)
    if run_dt.strftime("%Y-%m-%d %H:%M") < DPLUS1_SWEEP:
        raise SystemExit("🔴 착수 조건 미충족 — 09-23 봉은 아직 D 빈티지다(PD-27 (마)). 계산하지 않는다.")
    assert_ledger_matches(ledger_rows())
    ev = collect_evidence()

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    read_dates = [d for *_x, d in EXACT5] + [d for *_x, d in S8.EXACT4]
    first_kst, now_kst, reused, fp = read_stamp(cur, read_dates)

    with S8.pit_cutoff(PIT_CUTOFF):
        sel = S8.select_cases(cur, EXACT5)
        fin_detail = {code: S8.fin_counts(cur, code, PIT_CUTOFF) for _n, code, _d in EXACT5}
        cc = S8.CtrlCache(cur)
        ctrl_main = [cc.get(d) for _n, _c, d in EXACT5]
        miss9 = {k: sorted(v) for k, v in cc.miss.items()}
        x_lo = x_ok = x_k = 0          # 자기 날짜 선정 코드를 뺀 (가) 대조군(인쇄만 · post8 A-2 승계)
        for (_n0, _c0, d_row), c in zip(EXACT5, ctrl_main):
            own = {cc_ for _n, cc_, dd in EXACT5 if dd == d_row}
            keep = [t for t in c["codes"] if t not in own]
            x_k += int(len(keep) != len(c["codes"]))
            lo_, ok_, _u, _k = S7.loss_rate(cur, keep)
            x_lo += lo_
            x_ok += ok_
    with S8.pit_cutoff(S8.POST_DATE):   # post8 표본 재계산 — post8 의 PIT 절단면(09-18) · 값만
        sel8 = S8.select_cases(cur, S8.EXACT4)
        cc8 = S8.CtrlCache(cur)
        ctrl8 = [cc8.get(d) for _n, _c, d in S8.EXACT4]
    news9 = [(nm, code, d, S7.news_hits(cur, code, d)) for nm, code, d in EXACT5]
    cur.close()
    conn.close()

    judge = [x for x in sel if x[3] is not None]
    unk = [(nm, code) for nm, code, _d, r in sel if r is None]
    s_loss, s_ok = sum(1 for *_x, r in judge if r[2] < 0), len(judge)
    s_pct = Fraction(100 * s_loss, s_ok) if s_ok else None

    # ═══ §0 ═══════════════════════════════════════════════════════════════
    say("# RESULTS_S5_POST9_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_s5_post9.py`(`run_s5_post8.py`·`run_s5_post7.py` import 승계 · 원본 불변) · 사전등록 "
        "[`PREREG_S5_FUND_NEWS_OOS.md`](PREREG_S5_FUND_NEWS_OOS.md) v0.3(본문 0바이트) · 동결 선언 "
        "[`FREEZE_S5_2026-09-16.md`](FREEZE_S5_2026-09-16.md) `96beddc` · [`PREREG_POST9.md`](PREREG_POST9.md)(동결 `702f41b`) · "
        "[`PREREG_POST8.md`](PREREG_POST8.md) §12(`D-12`) · 인테이크 [`INTAKE_2026-09-24_post9.md`](INTAKE_2026-09-24_post9.md) §1·§5 · "
        "결정 [`PREDECISION_2026-09-24_post9.md`](PREDECISION_2026-09-24_post9.md) **PD-15 · PD-30** · 원장 `30aed89`(post9 6행 · 23레그)")
    say("")
    say(f"> {LIVE_BAN}")
    say("> (`PREREG_POST9.md` §0-1 · `PREREG.md:15` 문언 그대로) — 🔴 이 분석은 **라이브 채택 대상이 아니다**.")
    say("")
    say("## §0. 실행 환경 · 동결 규약\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 🔴 창 종료 | **{WINDOW_LINE}** |")
    say(f"| 🔴 실행 시 `max(date)` | **실행 시 `max(date)` = {fp['max_date']} · 그 날짜 행수 {fp['max_rows']:,} — "
        "기록만(창 아님)** |")
    say(f"| 🔴 D-9 ① 쿼리 실행 시각(KST) | **{first_kst}** — 이 DB 지문(`max(date)`·그 날 행수·창 구간 "
        f"`[{WIN_START}, {DB_UPTO}]` 행수·`min/max(updated_at)`·읽은 날짜 {len(fp['read_dates'])}개 `min/max(updated_at)`·"
        "`dart_financials_asfiled` 행수·`max(rcept_dt)`·`max(created_at)`)을 이 스크립트가 «처음» 읽은 실행의 DB `now()` · "
        f"`{STAMP_DIR}/read_stamp.json`(같은 지문 재실행 = 같은 값 · 파일 다시 안 씀) · 🔴 공통 지시에 따른 «더 많이 인쇄» — "
        "`P9-스탬프통일`(post10 부터) 적용 아님(`PREREG_POST9.md` §6 (라)) · S5 는 `PREREG_POST8.md:544` 묶음 축이 아니다"
        "(`INTAKE_2026-09-18_post8.md:410`) |")
    say(f"| 🔴 D-9 ② 창 구간 `max(daily_prices.updated_at)` | **{fp['win_max_u']}** (`[{WIN_START}, {DB_UPTO}]` · "
        f"PD-27 (다) 창 시작일) · 이 축이 «실제로 읽은» 날짜의 `max(updated_at)` = **{fp['read_max_u']}** |")
    say("| 🔴 D-9 ③ | **09-23 봉은 D+1(09-28) sweep 이후 읽음** — 🔴 이 축은 09-23 봉을 읽지 않는다(읽은 날짜 최대 = "
        f"**{max(fp['read_dates'])}**) |")
    say(f"| 🔴 D-9 ④ (기록 · 통과 조건 아님 · PD-27 (마) 2 (f)) | 창 구간 `min(updated_at)` = **{fp['win_min_u']}** ≥ "
        f"{DPLUS1_SWEEP}: **{'예' if fp['win_min_u'] >= DPLUS1_SWEEP else '아니오'}** (`updated_at` 은 sweep 마다 일괄 "
        "갱신 값 — 빈티지 «증거»가 아니다 · PD-27 (라)) |")
    n_after = sum(1 for *_x, d in EXACT5 if d >= VINTAGE_BOUNDARY)
    say(f"| 🔴 D-9 ⑤ 혼합 빈티지 | **걸침 창 0** — 이 축의 `daily_prices` 읽기는 «날짜 한 개» 단위(등록일 `D` 의 대조군 "
        f"유니버스)라 창이 없다 ⇒ `P8-혼합빈티지신고` 문장 대상 없음(PD-27 (바) 표에 `S5` 행 없음) · 🟡 기록: 판정 분모 "
        f"등록일 중 제도 경계 {VINTAGE_BOUNDARY} «후» = **{n_after}/{len(EXACT5)}**(빛샘 09-14 · 첨단·한컴 09-15 · 창이 "
        "아니라 걸침·「전부 경계 후」 신고 대상 아님 · 그날 `trading_value` 가 연장 시간대를 포함하는지 이 축은 가르지 않는다) · "
        "「정규장만」 갈래 열지 않음 · `adj_factor` 산술 0 |")
    say(f"| PIT 규약 | `dart_financials_asfiled` · `status = '{S8.PIT_STATUS}'` ∧ `rcept_dt <= {PIT_CUTOFF}`(글 게시일) · "
        "**가장 최근 사업연도 «하나»만** · 🔴 실패해도 다른 해를 찾지 않는다(§1) |")
    say(f"| 대조군 | 같은 날 유니버스 `trading_value / market_cap` 백분위 **상위 1%**(= `pct >= {S8.TOP_PCT:.1f}`) — "
        "`run_s5_post7.control_top1` 그대로 |")
    say("| 판정 라벨 | 🟢 **선언 있음** — `FREEZE_S5_2026-09-16.md` §6(`96beddc` · post9 fetch «앞» · PD-0) · "
        "`PREREG_S5_FUND_NEWS_OOS.md:34-36` 세 라벨 · **2번째 판정 회차**(PD-15) |")
    say(f"| 최소 n | 신규 «판정 가능» 건 **{MIN_JUDGEABLE}** 미만이면 미룬다(§1 `:15` · §2 `:36`) |")
    say("| Holm 가족 | 🔴 **+0** — 주 검정 수를 늘리지 않는다(§2 `:37` · FREEZE §6) |")
    say(f"| 시드 | **{S8.SEED}** (계열 고정값) — 🔴 이 레인은 **난수를 쓰지 않는다** |")
    say("| 등급 | 🔴 이 산출물은 등급 이름을 **한 개도 적지 않는다**(§6 단계 · PD-16 · PD-28) |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST9.md` §0-1) |")
    say("| 착수 기록 | `D:/archive/tasso-program-journal-20260923/probes_precalc_0929/`(PD-27 (마) 2 (a)(b) · 행수 3회 안정 · "
        "`P-2b`·`P-3`·`P-5` 원출력 · `md5.txt`) — 🔴 `P-3` 은 판별력 0(통과로 인용하지 않는다) |")
    say("")
    say("🔴 **post8 은 소급 재판정하지 않는다** — post8 `S5` 판정(⛔ 판정 불가 · 정밀도 의존)은 그대로다"
        "(`PREREG_POST9.md` §1 (라)). §7 의 post8 재계산은 **값만**이다. 🔴 **검정력이 없다**(§2 `:38`) — 라벨이 무엇이든 "
        "***「재무를 본다/안 본다」의 증거가 아니다***.")
    say("")

    # ═══ §0-2 P9-수집증거 ════════════════════════════════════════════════════
    say("## §0-2. 🔴 `P9-수집증거` — `FREEZE_S5_2026-09-16.md` ④ 글 수집 시각의 증거 세 줄 "
        "(`PREREG_POST9.md` §5 (나) · `FREEZE_*` 본문 불변 · 이 절이 그 정오표의 적용)\n")
    say("| 줄 | 명령·출처 | 실측 | 검사 |")
    say("|---|---|---|---|")
    for a, b, c, d in ev["rows"]:
        say(f"| {a} | {b} | {c} | {d} |")
    say("")
    if ev["ok"]:
        say("- 🟢 **기계 검사(§5 (나)3) 통과** — ① 후손 참 ∧ ② md5 3줄 존재·보관본 일치 ∧ ③ 발행 시각 > ③ 커밋 시각 ⇒ "
            "순서 증거 미비 줄 **없음** ⇒ `S5` 판정 **개방**(`PREREG_POST8.md:829` — FREEZE 동결이 post9 fetch «앞»).")
    else:
        say(f"- 🔴 **그 회차 `S5` 순서 증거 미비** — {' · '.join(ev['reasons'])} ⇒ **이 회차 `S5` 판정 미개방**"
            "(`PREREG_POST9.md` §5 (나)3 · `PREREG_POST8.md:829`).")
    say("- 🔴 ② 의 fetch 시각은 **자기보고**다 — 제3자 증거는 ③ 발행 시각 하나다(§5 (다) 「틀렸다면」) · fetch 가 계산 «전»"
        "이었는지는 이 조항 밖(`PREREG_POST6.md:1072` §7-B #14).")
    say("- (대안 · 민감도 인쇄만 · §5 (나) 첫 줄) 대체 기제를 승인하지 않는 독법 = 위 「원문 추가 커밋 명령」 줄의 빈 결과를 "
        "그대로 «미비»로 읽는다 — 🔴 판정에 쓰지 않는다.")
    say("")

    # ═══ §1 표본 ═══════════════════════════════════════════════════════════
    say("## §1. `reg_date` 정밀도 분포 · 표본 n\n")
    say("| 정밀도 | 건 | 처리(§1-1 동결) |")
    say("|---|---|---|")
    say(f"| **`exact`** | **{len(EXACT5)}** | 🟢 **주 표본** — 판정은 이 건으로만 |")
    say(f"| `approx` | {len(APPROX)} | ⚪ 민감도 인쇄만(이번 글엔 없다 · PD-4) |")
    say("| `none`(신규) | 0 | — |")
    say(f"| `none`(후속) | {len(FOLLOWUP1)} | 등록일 축 **밖**(PD-2 · 우리기술 = post8 #10 후속) |")
    say("| `after` | 0 | 🔴 제외(§1-1) — 이번 글엔 없다 |")
    say("")
    say(f"- **주 표본 n = {len(EXACT5)}** (신규 ∧ `exact`) · 그중 **판정 가능 {s_ok}**")
    say(f"- **민감도 판 n = {len(EXACT5) + len(APPROX)}** (주 표본 + `approx` {len(APPROX)}) · 그중 판정 가능 {s_ok} — "
        "🔴 같은 수여도 **둘 다** 적는다(§1-1 *「하나만 적으면 무효」* · PD-15)")
    say("- 🔴 **§1-5 재진입 = 0**(PD-3) ⇒ 재진입 민감도 «항등»(5 ↔ 5) · 「우리로 제외」류 갈래 = 해당 없음"
        "(post9 신규에 항목 내 두 사이클 0).")
    say("")

    # ═══ §2 PIT 한계 ═══════════════════════════════════════════════════════
    say("## §2. 🔴 PIT 한계 — 표가 **멈춰 있다** (PD-15 · 재측정)\n")
    say(f"- `dart_financials_asfiled` 전체 **{fp['fin_rows']:,}행** · **`max(rcept_dt)` = {fp['fin_max_rcept']}** · "
        f"`max(created_at)` = {fp['fin_max_created']} (이 실행에서 다시 읽음)")
    same = fp["fin_rows"] == S8.PD11_RECORD["rows"] and fp["fin_max_rcept"] == S8.PD11_RECORD["max_rcept"]
    say(f"- PD-11/PD-15 기록({S8.PD11_RECORD['rows']:,}행 · {S8.PD11_RECORD['max_rcept']})과 같은가: "
        f"**{'예' if same else '아니오'}**")
    say(f"- ⇒ *「`rcept_dt <= {PIT_CUTOFF}`」* 는 **형식상 통과**하지만 ***표 자체가 {fp['fin_max_rcept']} 이후 접수분을 "
        "담지 않는다.*** 이 축의 「최근 사업연도」는 **표가 가진 최근 연도**다.")
    say("")

    # ═══ §3 선정 건 ═════════════════════════════════════════════════════════
    say(f"## §3. 선정 건 — 주 표본 `exact` {len(EXACT5)} 건별 PIT\n")
    say("| 종목 | 코드 | 등록일 | 표 전체 행 | PIT 통과 행 | 사업연도 | `rcept_dt` | `operating_income`(원) | 영업적자? |")
    say("|---|---|---|---|---|---|---|---|---|")
    for nm, code, d, r in sel:
        a, b = fin_detail[code]
        if r is None:
            say(f"| {nm} | `{code}` | {d} | {a} | {b} | — | — | — | 🔴 **측정 불가** |")
        else:
            say(f"| {nm} | `{code}` | {d} | {a} | {b} | {r[0]} | {r[1]} | {r[2]:,} | "
                f"{'🔴 **예**' if r[2] < 0 else '아니오'} |")
    say("")
    say(f"- **판정 가능 {s_ok} / {len(EXACT5)}** · 측정 불가 **{len(unk)}**"
        + (f" ({', '.join(n for n, _ in unk)})" if unk else ""))
    say(f"- **선정 건 영업적자 비율 = {s_loss}/{s_ok} = {pp(s_pct)}**")
    say("- 🔴 **측정 불가 건은 분자에도 분모에도 넣지 않는다**.")
    say("- 🔴 **PD-31 한국첨단소재**(창·로드창 안 액면병합·거래정지 공시 · 확인 5) — 이 축은 재무표와 등록일 유니버스만 읽는다 · "
        "INTAKE §5 `S5` 행의 신고 대상 목록에 없다 ⇒ **기록만**(규칙·갈래 신설 0 · 「첨단 제외」 갈래 계수 불가).")
    say("")

    # ═══ §4 대조군 ═════════════════════════════════════════════════════════
    say("## §4. 대조군 — 같은 날 `거래대금/시총` 상위 1%\n")
    say("| 건 | 등록일 | 그날 유니버스 | 상위 1% 종목 수 | 측정 가능 | 영업적자 | 적자 비율 | 선정 건 판정 가능? |")
    say("|---|---|---|---|---|---|---|---|")
    for (nm, _code, d, r), c in zip(sel, ctrl_main):
        say(f"| {nm} | {d} | {c['n_univ']:,} | {c['top']} | {c['ok']} | {c['lo']} | "
            f"{pp(Fraction(100 * c['lo'], c['ok']) if c['ok'] else None)} | "
            f"{'예' if r is not None else '🔴 아니오(측정 불가)'} |")
    say("")
    say(f"- 🔴 **대조군 「측정 불가」 두 종류** — ① PIT 행 0개 {len(miss9['no_row'])}종목 · ② 행은 있는데 "
        f"`operating_income` NULL {len(miss9['null_value'])}종목"
        + (f" · 분류 불명 {len(miss9['unknown'])}" if miss9['unknown'] else "")
        + " — 둘 다 분자·분모에서 뺀다(선정 건과 같은 잣대).")
    say("- 🔴 **같은 날짜가 두 줄**(09-15 = 한국첨단소재·한컴위드)인 것은 그날 등록 건이 2건이기 때문이다(post8 09-11 과 같은 구성).")
    say("")

    # ═══ §5 판정 ═══════════════════════════════════════════════════════════
    say(VERDICT_BEGIN)
    say("## §5. 🟢 판정 — `S5` 2번째 판정 (라벨 = `FREEZE_S5_2026-09-16.md` §6 선언 · `PREREG_S5_FUND_NEWS_OOS.md:34-36`)\n")
    say("> **S5**: *post7 이후 새 글의 «신규» 건의 **영업적자 비율**은, 그날 「거래대금/시총 상위 1%」 대조군의 "
        "적자 비율과 **±10%p 안에서 같다**.* (`PREREG_S5_FUND_NEWS_OOS.md:12` 원문)")
    say("")
    all_e = [(c["lo"], c["ok"]) for c in ctrl_main]
    jud_e = [(c["lo"], c["ok"]) for (_n, _c, _d, r), c in zip(sel, ctrl_main) if r is not None]
    variants = [
        ("(가) pooled 종목-일 × 전 `exact` 날짜 — post7 구현 승계(주 열)", all_e, True),
        ("(나) 날짜별 비율 평균 × 전 `exact` 날짜", all_e, False),
        ("(다) pooled 종목-일 × «판정 가능» 건의 날짜만", jud_e, True),
        ("(라) 날짜별 비율 평균 × «판정 가능» 건의 날짜만", jud_e, False),
    ]
    say("| 대조군 셈법(S5-R9-3 = S5-R8-4) | 날짜 줄 수 | 대조군 적자 비율 | 선정 적자 비율 | 차이(선정 − 대조군) | "
        "`abs ≤ 10%p`? | 라벨 |")
    say("|---|---|---|---|---|---|---|")
    labs = []
    for name, ents, pooled in variants:
        cr = S8.ctrl_rate(ents, pooled)
        lab = S8.s5_label(s_loss, s_ok, cr)
        labs.append(lab)
        diff = None if (cr is None or s_pct is None) else s_pct - cr
        inb = "—" if diff is None else ("예" if abs(diff) <= BAND_PP else "아니오")
        ctxt = (f"{sum(lo for lo, ok in ents if ok)}/{sum(ok for _l, ok in ents if ok)} = {pp(cr)}" if pooled else pp(cr))
        say(f"| {name} | {len(ents)} | {ctxt} | {s_loss}/{s_ok} = {pp(s_pct)} | {ppd(diff)} | {inb} | **{lab or '—'}** |")
    fin = S8.final_label(labs)
    say("")
    say(f"- 판정 가능 **{s_ok}** ≥ {MIN_JUDGEABLE} ⇒ `(S5-보류)` 조건 " + ("**불성립**" if s_ok >= MIN_JUDGEABLE else "**성립**"))
    say(f"- 🔴 **규칙(S5-R8-4 승계)**: 네 셈법의 라벨이 모두 같으면 그 라벨 · 하나라도 다르면 「{AMBIG}」 — 정본 셈법은 미결 "
        "이월(`PREREG_POST9.md` §7 #13 ㉯) · 🔴 이 규칙은 post8 에서 값 본 뒤 적힌 레인 규칙이고 post9 는 **바꾸지 않고** 잇는다.")
    say(f"- `exact` 갈래(주) 답 = **{fin}**")
    say("")
    say("**🔴 `D-3` (나)4 검사**(`PREREG_POST8.md:250`) — `approx` **0** ⇒ `approx` 포함 갈래가 **생기지 않는다**(PD-21) ⇒ "
        "검사 **대상 없음**.")
    say("")
    say("- `P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`approx` 0 — `approx` 포함 갈래가 생기지 않는다 · PD-21) — "
        "독법 B(표본 수준 문턱 비교)로 결과가 달라지는 자리 **없음**(비교할 갈래가 없다) · `PREREG_POST9.md` §1 (나)3")
    fin_final = fin if ev["ok"] else "⛔ 판정 미개방 — 순서 증거 미비(`P9-수집증거` · `PREREG_POST8.md:829`) · 기록: exact " + fin
    say(f"- ⇒ **최종: {fin_final}**" + ("" if fin != AMBIG else " — 셈법이 판정을 가른다(동결 문언이 셈법을 정하지 않았다)"))
    say("- 🔴 Holm 가족 **+0** · 🔴 이 라벨은 **검정이 아니다**(§2 `:35` · `:38` 검정력 없음).")
    say("")
    say("### 5-1. 🔴 D-5 갈래 — `(갈래 이름, n, 답)` 세 쪽 (`PREREG_POST8.md` §5 (나) 2 · PD-23)\n")
    say("| 갈래 | n(표본 · 판정 가능) | 답 |")
    say("|---|---|---|")
    say(f"| 주 갈래 — 신규 ∧ `exact` | {len(EXACT5)} · {s_ok} | **{fin}** |")
    say(f"| §1-5 재진입 포함 ↔ 제외 | {len(EXACT5)} ↔ {len(EXACT5)} | **항등** — 재진입 0(PD-3) |")
    say(f"| 창 절단 포함 ↔ 제외 | {len(EXACT5)} ↔ {len(EXACT5)} | **항등** — 이 축은 창을 쓰지 않는다(날짜 한 개 단위) |")
    say("| `approx` 포함(민감도 판) | 0 추가 | **없음** — `approx` 0(PD-4 · PD-21) |")
    say("| 대조군 셈법 (가)·(나)·(다)·(라) | 위 표 | 위 표의 라벨 열 그대로 |")
    say("")
    say(f"- 🔴 **D-3** — *「`approx` 포함 시 최소 n 이 차는 축: **없음** · `exact` 분모 **{len(EXACT5)}**(판정 가능 {s_ok}) / "
        f"`approx` 포함 분모 **{len(EXACT5) + len(APPROX)}**(판정 가능 {s_ok})」* (PD-21 예고 = 「없음」)")
    say("")
    say(VERDICT_END)
    say("")
    say("## §6. `approx` — **0건** · 민감도 절 없음 (PD-4 · §1-1 「두 값을 «둘 다»」는 §1 의 n 두 줄로 이행)\n")

    # ═══ §7 post8 재계산 ═══════════════════════════════════════════════════
    judge8 = [x for x in sel8 if x[3] is not None]
    l8 = sum(1 for *_x, r in judge8 if r[2] < 0)
    e8 = [(c["lo"], c["ok"]) for c in ctrl8]
    cr8 = S8.ctrl_rate(e8, True)
    s8p = Fraction(100 * l8, len(judge8)) if judge8 else None
    cr9 = S8.ctrl_rate(all_e, True)
    say("## §7. post8 표본 — **같은 스냅샷에서 재계산** · 값만 (post8 판정 = 재판정 안 함 · 소급 금지)\n")
    say(f"- PIT 절단면 = post8 게시일 **{S8.POST_DATE}** · 표본 = `run_s5_post8.EXACT4`(주 표본 {len(S8.EXACT4)})")
    say("")
    say("| 글 | 주 표본 n · 판정 가능 | 선정 적자 비율 | 대조군 (가) pooled | 차이 |")
    say("|---|---|---|---|---|")
    say(f"| post8(재계산) | {len(S8.EXACT4)} · {len(judge8)} | {l8}/{len(judge8)} = {pp(s8p)} | "
        f"{sum(lo for lo, ok in e8 if ok)}/{sum(ok for _l, ok in e8 if ok)} = {pp(cr8)} | "
        f"{ppd(None if (s8p is None or cr8 is None) else s8p - cr8)} |")
    say(f"| post9 | {len(EXACT5)} · {s_ok} | {s_loss}/{s_ok} = {pp(s_pct)} | "
        f"{sum(lo for lo, ok in all_e if ok)}/{sum(ok for _l, ok in all_e if ok)} = {pp(cr9)} | "
        f"{ppd(None if (s_pct is None or cr9 is None) else s_pct - cr9)} |")
    say("")
    say("- 🔴 **post8+post9 합산은 만들지 않는다** — 판정 분모는 post9 신규 건이다(PD-15 · 소급 금지).")
    say("")

    # ═══ §8 뉴스 [탐색] · §9 희소성 ════════════════════════════════════════
    for ln in S7.news_defer_lines():
        say(ln.replace("## §5.", "## §8."))
    say(f"| 종목 | 코드 | 등록일 | 창 `[D−{S7.NEWS_BACK}, D]` 뉴스 건수 |")
    say("|---|---|---|---|")
    for nm, code, d, k in news9:
        say(f"| {nm} | `{code}` | {d} | {k} |")
    say("")
    say("- 🔬 **탐색 표기 · 판정 아님 · τ 라벨 없음**(§3) · 요약통계 없음.")
    say("")
    for ln in S7.sparsity_lines():
        say(ln.replace("## §6.", "## §9."))

    # ═══ §10 의무 · §11 한계 ═══════════════════════════════════════════════
    say("## §10. 그 밖의 의무 — 이 축에 해당하는가\n")
    say("| 의무 | 이 축 |")
    say("|---|---|")
    say("| `D-1` · `D-2` · `D-4` · `D-7` · `D-11` | 해당 없음 — 이 축의 항목이 아니다 |")
    say("| `D-6` `ddof` | 해당 없음 — `n_up` 표준편차를 인쇄하지 않는다(SSOT = `ddof=1`) |")
    say("| `D-8` · `P9-행단위` | 해당 없음 — 이 산출물은 `prog_ver` 를 **공변량으로 쓰지 않는다**(PD-26) · post9 6행 = "
        "`missing`(빈 칸 · 원장 대조 가드 통과) · 수준 목록을 만들지 않으므로 행 단위 n 검사 대상 아님(`PREREG_POST9.md` §4 (나)5) |")
    say("| `D-10` 등급 열 형식 | §6 단계(이 산출물 밖) |")
    say("| `D-12` `S5` 동결 절차 | 🟢 이행 완료(`96beddc` · PD-30) — 순서 증거 = §0-2 `P9-수집증거` |")
    say("")
    say("## §11. 한계 (승계 · 미리 적는다)\n")
    say("- 🔴 **검정력이 없다** — §2 동결 문언: 뉴스 축 **MDE 24.6%p** · ***애초에 기각도 지지도 못 한다***.")
    say(f"- 🔴 **판정 가능 {s_ok}** — 한 건이 선정 비율을 {pp(Fraction(100, s_ok) if s_ok else None)}p 씩 옮긴다 · 건별 원표(§3)를 먼저 읽을 것.")
    say("- 🔴 **이름→코드 매칭 상한 83.0%**(§0 승계) · 코드는 인테이크 §1 표를 유일 출처로 쓴다(우리기술 `032820` ≠ 우리기술투자 `041190`).")
    say("- 🔴 **PIT 표가 멈춰 있다**(§2) — 「PIT 를 지켰다」와 「최신 공시를 봤다」는 다른 말이다.")
    say("- 🔴 **대조군 합치기 셈법 정본이 없다** — 네 셈법 전부 인쇄 · 하나로 고르지 않았다(미결 이월 §7 #13).")
    _xs = None if not (x_ok and s_ok) else s_pct - Fraction(100 * x_lo, x_ok)
    say(f"- 🔴 **선정 건이 자기 날짜 대조군 안에 있다** — 자기 등록일 상위 1% 에 선정 코드가 든 날짜 줄 **{x_k}/{len(EXACT5)}** · "
        f"자기 날짜 선정 코드를 뺀 (가) 대조군 = {x_lo}/{x_ok} = {pp(Fraction(100 * x_lo, x_ok) if x_ok else None)} · 차이 {ppd(_xs)} ⇒ "
        f"`±10%p` {'안' if (_xs is not None and abs(_xs) <= BAND_PP) else '밖'}(인쇄만 · post8 A-2 승계)")
    say("- 🔴 **`--rerun` 한계** — 다음 sweep(" + next_sweep(fp["max_date"]) + ")이 `updated_at` 을 일괄 갱신하면 D-9 ②·지문이 "
        f"바뀌어 `{STAMP_DIR}/read_stamp.json` 에 새 시각이 박히고 이 산출물은 byte 가 바뀐다 — 동결 규칙(D-9 인쇄)의 귀결이다.")
    say("- 🔴 **`adj_factor` 를 가격에 곱하지도 나누지도 않는다**(이 축은 가격을 쓰지 않는다).")
    say("- 🔴 이 분석은 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST9.md` §0-1) — "
        "***라벨이 무엇이든 라이브 채택 금지는 그대로다***.")
    say("")

    S7.assert_both_n(OUT)
    S8.assert_labels_only_in_verdict(OUT)
    S8.assert_no_grade_names(OUT)
    assert_duties(OUT)
    (BASE / OUT_NAME).write_bytes(("\n".join(OUT) + "\n").encode("utf-8"))
    note("")
    note(f"[D-9 ①] 이번 실행 벽시계(DB now · KST) = {now_kst} · 본문 ① = {first_kst} "
         f"({'stamp 재사용 — 지문 동일' if reused else 'stamp 새로 박음'}) · 창 max(updated_at) = {fp['win_max_u']}")
    note(f"[P9-수집증거] ok={ev['ok']} · PREDECISION 추가 {ev['pd']} · FREEZE {ev['fz']} · 발행 {ev['pub']}")
    note(f"[written] {OUT_NAME} · 런타임 {time.time() - t0:.3f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
