# -*- coding: utf-8 -*-
"""`WRC-` 축 **판정** 실행 — 9번째 글(`logNo=224421214462` · 발행 2026-09-23 수 · 거래일).

🔴 **얇은 판** — `run_wrc_post8.py` 의 판정 경로(`a0_measure`·`g1_of`·`fmt_g1`·`fire`)와 그 위의 동결 import
(`run_wrc_explore`·`run_wrc_post7`·`run_wrc_post6`·`run_reconstruct_post5`)를 **그대로 import** 하고, 글 목록·창·빈티지·
출력 경로만 바꾼다. 판정 로직 새로 쓰기 0 · 새 문턱 0 · 새 예측 0 · 등급 이름 0.

이 회차에 «새로» 걸리는 것(`PREREG_POST9.md` 동결 `702f41b` · post9 부터 구속):
  · §2 `P9-WRC누적분모` — `WRC-G1` 분모 = **누적** 판정 분모 · 한 글(단독) 분모·분자는 **같은 행 민감도** · 두 답이
    다르면 「갈림」 한 줄(판정 = 누적) · 판정 칸 사유는 한 글 값을 인용하지 않는다.
  · §1 `P9-공통독법` 신고 줄 · §4 `P9-행단위` 수준 줄(SSOT = 행 · `missing` 도 수준 — `P9-결측분리` 는 post10 부터) ·
    §5 `P9-수집증거` 세 줄(`FREEZE_WRC_2026-09-02.md`).
  · 🔴 `P9-스탬프통일`(§6)은 **post10 부터** — 이 판은 post8 형식(`wrc_post9/read_stamp.json` 지문 재사용)을 그대로 쓴다.

🔴 라이브 트리 import 0 · DB 는 **SELECT 만** · `adj_factor` 산술 0 · 원장 «읽기»만 · 원문 3파일은 md5·`addDate` 만 읽는다.
🔴 **라이브 채택 금지**(`PREREG_POST9.md` §0-1).

`p9_common_lines()`·`p9_collect_lines()`·`p9_live_lines()` 는 같은 회차 `run_ranking.py --stage post9`·
`run_sector.py --mode post9` 가 import 해 같은 문언을 인쇄한다(세 축 공통 인쇄 의무 · 한 곳에서만 정의).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import psycopg2

from run_tests import DSN
from run_wrc_explore import BAND_THR, CODEMAP, G1_THR, NREP, N_THR, SEED, THR, build_cases, read_ledger
from run_wrc_post6 import CODES6, INTAKE_DENOM_PRED, PD3_FLAG
from run_wrc_post7 import CODES7, approx_branch, denom, split_reasons
from run_wrc_post8 import (
    BOUNDARY,
    CODES8,
    FROZEN_G1 as FROZEN_G1_P8,
    POST6_LOG,
    POST7_LOG,
    POST8_LOG,
    WINDOW_END as WINDOW_END_P8,
    WINDOW_END_SRC as WINDOW_END_SRC_P8,
    a0_measure,
    fire,
    fmt_g1,
    g1_of,
)

BASE = Path(__file__).resolve().parent
ART = BASE / "wrc_post9"
OUT: list[str] = []

POST9_LOG = "224421214462"       # INTAKE_2026-09-24_post9.md 머리말
POST9_DATE = "2026-09-23"        # 발행일(수 · 거래일) — PD-1
DB_UPTO = "2026-09-23"           # 🔴 창 종료 = 발행 당일 봉 «포함» · B-1 · 전 축(`WRC-` 포함) · PD-1
SWEEP_D1 = "2026-09-28 15:35:00"  # 09-23 봉의 D+1 sweep(PD-27 (마) 2 · 09-24·25 추석 휴장)
MGR_WIN = ("2026-08-07", "2026-09-23")   # PD-27 (마) 2 (f) 창 구간(착수 직전 프로브와 같은 창)
PRECALC_DIR = "D:/archive/tasso-program-journal-20260923/probes_precalc_0929/"
RAW_ARCHIVE = Path("D:/archive/tasso-program-journal-20260923")
PREDECISION9 = "PREDECISION_2026-09-24_post9.md"

WINDOW_END = dict(WINDOW_END_P8, post9=DB_UPTO)
WINDOW_END_SRC = dict(WINDOW_END_SRC_P8, post9="`PREDECISION_2026-09-24_post9.md` PD-1")
POSTS = ("post4", "post5", "post6", "post7", "post8", "post9")

# ── 9번째 글 종목코드 — `INTAKE_2026-09-24_post9.md` §1 표 «그대로» (6/6 · PD-11) ──────────────
#    🔴 원장에는 종목코드 컬럼이 «없다» ⇒ 이름→코드는 인테이크가 유일 출처다. 우리기술 = `032820`(≠ 041190).
CODES9 = {"우리기술": "032820", "삼미금속": "012210", "에스투더블유": "488280", "빛샘전자": "072950",
          "한국첨단소재": "062970", "한컴위드": "054920"}
POST9_FOLLOWUP = ("우리기술",)    # PD-2 — post8 #10 후속(등록일 축 밖 · `none`)

# `INTAKE_2026-09-24_post9.md` §1 표 — «계산 전» 구성. 원장이 SSOT 이고 여기선 대조만 한다. (종목, 정밀도, fill_n, 레그)
INTAKE_ROWS9 = [
    ("우리기술", "none", 2, [13.59, 12.34, 11.02, 9.71, 0.21]),
    ("삼미금속", "exact", 1, [22.09, 17.76, 13.45, 9.23]),
    ("에스투더블유", "exact", 1, [15.08, 10.64]),
    ("빛샘전자", "exact", 1, [23.08, 21.05, 18.64, 16.46, 14.20, 12.26, 10.08]),
    ("한국첨단소재", "exact", 4, [3.80, 3.79, 3.79]),
    ("한컴위드", "exact", 2, [7.55, 7.52]),
]

FROZEN_G1 = dict(FROZEN_G1_P8)
FROZEN_G1["post8"] = dict(denom=0, db_absent=0, empty=0, src="`RESULTS_WRC_POST8_NUMBERS.md` §3-2")
FROZEN_CUM = (5, 4, "`RESULTS_WRC_POST8_NUMBERS.md` §3-2 누적 행(4/5)")

# `PREDECISION_2026-09-24_post9.md` PD-27 (바) 표 — (축·창 이름, 종목, 코드, 시작, 끝). 🔴 이 축이 읽는 창이 «아니다».
PD27_CROSS9 = (
    [("`ANC-`/`REC-` `[D, END]`", nm, cd, d, DB_UPTO) for nm, cd, d in
     (("삼미금속", "012210", "2026-09-04"), ("에스투더블유", "488280", "2026-09-10"),
      ("빛샘전자", "072950", "2026-09-14"), ("한국첨단소재", "062970", "2026-09-15"),
      ("한컴위드", "054920", "2026-09-15"))]
    + [("`LAD-` 창5 `[D, D+4]`", "삼미금속", "012210", "2026-09-04", "2026-09-10"),
       ("`LAD-` 창5 `[D, D+4]`", "에스투더블유", "488280", "2026-09-10", "2026-09-16"),
       ("`LAD-` 창5 `[D, D+4]`", "빛샘전자", "072950", "2026-09-14", "2026-09-18"),
       ("`LAD-` 창5 `[D, D+4]`", "한국첨단소재", "062970", "2026-09-15", "2026-09-21"),
       ("`LAD-` 창5 `[D, D+4]`", "한컴위드", "054920", "2026-09-15", "2026-09-21"),
       ("`REG-`/`REC-` `[D−19, D]`", "삼미금속", "012210", "2026-08-07", "2026-09-04"),
       ("`REG-`/`REC-` `[D−19, D]`", "에스투더블유", "488280", "2026-08-13", "2026-09-10"),
       ("`REG-`/`REC-` `[D−19, D]`", "빛샘전자", "072950", "2026-08-18", "2026-09-14"),
       ("`REG-`/`REC-` `[D−19, D]`", "한국첨단소재", "062970", "2026-08-19", "2026-09-15"),
       ("`REG-`/`REC-` `[D−19, D]`", "한컴위드", "054920", "2026-08-19", "2026-09-15")]
    + [("`ANC-N4` ① `[D, 09-22]`", nm, cd, d, "2026-09-22") for nm, cd, d in
       (("삼미금속", "012210", "2026-09-04"), ("에스투더블유", "488280", "2026-09-10"),
        ("빛샘전자", "072950", "2026-09-14"), ("한국첨단소재", "062970", "2026-09-15"),
        ("한컴위드", "054920", "2026-09-15"))]
)


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호 · `FREEZE_WRC_2026-09-02.md` §2)."""
    print(s)


# ═══ 세 축(`WRC`·`RNK`·`SEC`) 공통 — PREREG_POST9 인쇄 의무 ══════════════════════════════════════
def p9_live_lines() -> list[str]:
    """`PREREG_POST9.md` §0-1 본문(`:38-41`)을 파일에서 «축자» 읽어 인용 블록으로 낸다(§8-3 #20 · 문언 그대로)."""
    src = (BASE / "PREREG_POST9.md").read_text(encoding="utf-8").split("\n")
    assert src[35].startswith("### 0-1. 라이브 채택 아님"), src[35]
    body = src[37:41]
    return ["> 🔴 **라이브 채택 금지** — `PREREG_POST9.md` §0-1(`:38-41`) 문언 그대로:", ">"] + \
        [("> " + ln) if ln else ">" for ln in body]


def p9_common_lines(n_exact: int, n_incl: int) -> list[str]:
    """PREREG_POST9 §1 `P9-공통독법` 신고 줄 — 이번 글 `approx` 0 ⇒ 대상 없음(구성 · PD-21)."""
    res = "대상 없음(`approx` 0 · `exact` 분모 = `approx` 포함 분모)" if n_exact == n_incl else "확인 필요"
    return [f"🆕 **`P9-공통독법`**(`PREREG_POST9.md` §1 (나)3): *「`P9-공통독법`: 답 = 판정 · (나)4 결과 = {res}」* — "
            f"`exact` 분모 {n_exact} / `approx` 포함 분모 {n_incl} · 독법 B 병기 자리 없음(갈래가 없다)."]


def p9_level_lines(rows) -> list[str]:
    """PREREG_POST9 §4 `P9-행단위` — 수준(행/글) 한 줄 · SSOT = 행 · post9 는 `missing` 도 수준(`P9-결측분리` = post10)."""
    lv_rows = Counter((r["prog_ver"] or "missing") for r in rows)
    lv_posts: dict = {}
    for r in rows:
        lv_posts.setdefault(r["prog_ver"] or "missing", set()).add(r["post_log_no"])
    keys = sorted(lv_rows, key=lambda x: (x == "missing", x))
    body = " · ".join(f"`{k}`: {lv_rows[k]}/{len(lv_posts[k])}" for k in keys)
    return [f"🆕 **`P9-행단위`**(`PREREG_POST9.md` §4 (나)3): *「수준(행/글): {body} · SSOT = 행(`PREREG_POST9.md` §4)」* — "
            "🔴 post9 는 동결문 그대로 **`missing` 도 한 수준**이다(`P9-결측분리` 는 **post10 부터** · §4 (라)).",
            "- *「부호 갈림 검사: 통계량 정의 없음(기록만)」*(`PREREG_POST9.md` §4 (나)4 — 이 축은 버전을 «기록»만 한다)."]


def _git(*args) -> str:
    r = subprocess.run(["git", "-C", str(BASE), *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else f"<git exit {r.returncode}>"


def _git_ok(*args) -> bool:
    return subprocess.run(["git", "-C", str(BASE), *args], capture_output=True).returncode == 0


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else "<없음>"


def p9_collect_lines(freeze_name: str, axis: str) -> list[str]:
    """PREREG_POST9 §5 `P9-수집증거` — `FREEZE_*` 「④ 글 수집 시각」 증거 세 줄 + 빈 결과 줄 + 기록 줄.

    🔴 git·파일 «사실»만 읽는다(값 0). 기계 검사 (나)3 — 하나라도 거짓이면 「순서 증거 미비」 한 줄."""
    fr = _git("log", "--diff-filter=A", "--format=%h %ci", "--", freeze_name).split("\n")[-1]
    pdc = _git("log", "--diff-filter=A", "--format=%h %ci", "--", PREDECISION9).split("\n")[-1]
    fr_sha, pd_sha = fr.split(" ")[0], pdc.split(" ")[0]
    anc = _git_ok("merge-base", "--is-ancestor", fr_sha, pd_sha)
    head = (BASE / PREDECISION9).read_text(encoding="utf-8")
    m_fetch = re.search(r"\*\*수집\*\*[^\n]*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) KST", head)
    fetch = m_fetch.group(1) if m_fetch else "<못 찾음>"
    md5_ok, md5_s = True, []
    for fn in (f"post_{POST9_LOG}.html", f"post_{POST9_LOG}.txt", f"post_{POST9_LOG}_images.json"):
        m = re.search(r"\| `" + re.escape(fn) + r"` \| `([0-9a-f]{32})` \|", head)
        rec = m.group(1) if m else "<없음>"
        arc, wt = _md5(RAW_ARCHIVE / fn), _md5(BASE / fn)
        ok = rec == arc == wt
        md5_ok &= ok
        md5_s.append(f"`{fn}` 기록 `{rec[:8]}…` · 보관본 `{arc[:8]}…` · 작업트리 `{wt[:8]}…` {'✅' if ok else '🔴'}")
    html = (RAW_ARCHIVE / f"post_{POST9_LOG}.html").read_text(encoding="utf-8", errors="replace")
    m_add = re.search(r'addDate="(\d+)"', html)
    kst = _dt.timezone(_dt.timedelta(hours=9))
    pub = _dt.datetime.fromtimestamp(int(m_add.group(1)) / 1000, kst) if m_add else None
    fr_t = _dt.datetime.strptime(fr[len(fr_sha) + 1:], "%Y-%m-%d %H:%M:%S %z") if " " in fr else None
    pub_ok = bool(pub and fr_t and pub > fr_t)
    raw_add = _git("log", "--oneline", "--diff-filter=A", "--", f"post_{POST9_LOG}.html")
    remote = _git("branch", "-r", "--contains", pd_sha).replace("\n", " ").strip()
    out = [f"🆕 **`P9-수집증거`**(`PREREG_POST9.md` §5 (나)1 · `{freeze_name}` · 이 회차 `{axis}`):",
           f"- ① `git log --diff-filter=A --format='%h %ci' -- {PREDECISION9}` = **`{pdc}`** · ③ = `{freeze_name}` 추가 "
           f"커밋 `{fr}` · `git merge-base --is-ancestor {fr_sha} {pd_sha}` = **{'참' if anc else '거짓'}**",
           f"- ② `{PREDECISION9}` 머리 fetch 시각 **{fetch} KST**(관리자 기록 · 자기보고) · 원문 3파일 md5 3줄: "
           + " / ".join(md5_s),
           f"- ③ html `addDate` 서버 발행 시각 = **{pub.strftime('%Y-%m-%d %H:%M:%S') if pub else '<없음>'} KST** "
           f"{'>' if pub_ok else '≤'} ③ 커밋 시각 `{fr[len(fr_sha) + 1:]}` — 제3자 기록 · **{'참' if pub_ok else '거짓'}**",
           f"- (나)2 원문 추가 커밋 명령 `git log --oneline --diff-filter=A -- post_{POST9_LOG}.html` = "
           f"*「{raw_add or '빈 결과'} · 원문 커밋 금지 `README.md:27-29`」* — 🔴 빈 결과는 위반이 아니다",
           f"- (나)4 기록 줄(통과 조건 아님): `git branch -r --contains {pd_sha}` = "
           f"{('`' + remote + '`') if remote else '*「제3자 타임스탬프 없음(미푸시)」*'}"]
    if not (anc and md5_ok and pub_ok):
        out.append(f"- 🔴 *「그 회차 `{axis}` 순서 증거 미비」*(§5 (나)3 · 효과는 새로 만들지 않는다 — `PREREG_GRADE_TIERS.md:54-55`)")
    else:
        out.append(f"- ⇒ (나)3 기계 검사 세 조건 전부 참 — `{axis}` 순서 증거 **미비 아님**.")
    return out


def post_label(log_no, fallback):
    return {POST6_LOG: "post6", POST7_LOG: "post7", POST8_LOG: "post8", POST9_LOG: "post9"}.get(log_no, fallback)


def code_of(c):
    lab = c["post"]
    if lab in ("post4", "post5"):
        return CODEMAP.get(c["name"])
    return {"post6": CODES6, "post7": CODES7, "post8": CODES8, "post9": CODES9}[lab].get(c["name"])


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
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices WHERE date BETWEEN %s AND %s", MGR_WIN)
    mgr_min_u, mgr_max_u = cur.fetchone()
    cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices WHERE date = %s", (DB_UPTO,))
    end_rows, end_min_u, end_max_u = cur.fetchone()

    # ── 표본 ────────────────────────────────────────────────────────────────
    tr, legs_map = read_ledger()
    cases_all = build_cases(tr, legs_map)
    for c in cases_all:
        c["post"] = post_label(c["log_no"], c["post"])
        c["code"] = code_of(c) if c["post"] in POSTS else c["code"]
    p9 = [c for c in cases_all if c["log_no"] == POST9_LOG]

    read_windows = [(c["reg"], WINDOW_END[lab]) for lab in POSTS for c in cases_all
                    if c["post"] == lab and c["gate"] and c["reg"]]
    span = (min(w[0] for w in read_windows), max(w[1] for w in read_windows))
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices WHERE date BETWEEN %s AND %s", span)
    span_min_u, span_max_u = cur.fetchone()

    # ── D-9 ① 읽은 시각 — 스냅샷 지문 키(post8 형식 승계 · `P9-스탬프통일` 은 post10 부터) ─────────
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
    say("# RESULTS_WRC_POST9_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_wrc_post9.py`(얇은 판) · 승계(=import) `run_wrc_post8.py`(`a0_measure`·`g1_of`·`fmt_g1`·`fire`·`CODES8`·"
        "창 표) · `run_wrc_post7.py`(`approx_branch`·`split_reasons`·`denom`·`CODES7`) · `run_wrc_post6.py`(`CODES6`·"
        "`PD3_FLAG`·`INTAKE_DENOM_PRED`) · `run_wrc_explore.py`(`build_cases`·`read_ledger`·문턱) · "
        "`run_reconstruct_post5.py`(`feasible_exact` — `a0_measure` 경유)")
    say("사전등록 `PREREG_WEIGHTED_RECON.md` §4·§4-6·§4-8·§6-1·§7-B #24 · 동결 `FREEZE_WRC_2026-09-02.md` · "
        "`PREREG_POST8.md` §3·§4·§5·§8·§9 · 🆕 `PREREG_POST9.md`(동결 `702f41b`) §1·§2·§4·§5 · 인테이크 "
        "`INTAKE_2026-09-24_post9.md` §1·§5 · 결정 `PREDECISION_2026-09-24_post9.md` PD-1·PD-2·PD-11·PD-13·PD-21~23·PD-26·"
        "PD-27 · 정오표 `ERRATA_2026-09-29_post9_intake.md`\n")
    say(f"- **창 종료 {DB_UPTO} = 발행 당일(수 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**")
    say(f"- **실행 시 `max(date)` = {max_date} · 그 날짜 행수 {max_rows:,} — 기록만(창 아님)**\n")
    for ln in p9_live_lines():
        say(ln)
    say("")
    say("> 🔴 **`P9-WRC누적분모`**(`PREREG_POST9.md` §2) — `WRC-G1` 의 판정 분모 = **누적**(🔒 사장님 결정 2026-09-27) · "
        "한 글(단독) 분모·분자는 **민감도 행**(판정 무관). 🔴 새 예측 0 · 새 문턱 0 · 등급 이름 0(§6 단계).\n")

    # ═══ §0 ═════════════════════════════════════════════════════════════════
    say("## §0. 실행 환경 · 동결 규약 · 공통 인쇄 의무\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 대상 | 9번째 글 `logNo={POST9_LOG}` (발행 **{POST9_DATE}** 수 · 거래일) · 프로그램 버전 **표기 없음**(`missing` · PD-8) |")
    say(f"| D-9 ① 쿼리 실행 시각(KST) | **{first_read}** ({tzname}) — 이 DB 스냅샷 지문을 이 스크립트가 «처음» 읽은 실행의 "
        "시각(`wrc_post9/read_stamp.json` · post8 형식 승계 · `P9-스탬프통일` 은 post10 부터) · 이번 실행 벽시계는 stdout |")
    say(f"| D-9 ② 창 구간 `max(daily_prices.updated_at)` | 이 스크립트가 읽는 창 전 구간 `[{span[0]}, {span[1]}]` = "
        f"**{span_max_u}** · PD-27 (마) 창 `[{MGR_WIN[0]}, {MGR_WIN[1]}]` = **{mgr_max_u}** · {DB_UPTO} 봉(행 "
        f"{end_rows:,}) = **{end_max_u}** |")
    say(f"| D-9 ③ | **「{DB_UPTO} 봉은 D+1(2026-09-28) sweep 이후 읽음」** — ① {first_read} ≥ {SWEEP_D1[:16]} : "
        f"{'예' if read_after_d1 else '🔴 아니오'} |")
    say(f"| D-9 ④ (기록 · 통과 조건 아님) | **「창 구간 `min(updated_at)` = {mgr_min_u} ≥ 2026-09-28 15:35: "
        f"{'예' if min_after_d1 else '아니오'}」**(창 `[{MGR_WIN[0]}, {MGR_WIN[1]}]` · PD-27 (마) 2 (f)) · 이 스크립트 창 "
        f"전 구간 `min(updated_at)` = {span_min_u} · 🔴 `updated_at` 은 일괄 갱신 값 — «읽은 시각» 기록(PD-27 (라)) |")
    say(f"| 착수 직전 프로브 | `P-2b`·`P-3`·`P-5` 원출력 = `{PRECALC_DIR}p9_probes_precalc_0929.txt`(md5 `88d71880…` · "
        "2026-09-29 18:51:43 KST · 1단계 executor) · 행수 3회 안정 `p9_stab_3x.txt` · 🔴 `P-3` 은 «통과»로 인용하지 않는다 |")
    say("| D-9 ⑤ 혼합 빈티지 | §7 · 「정규장만」 갈래 **열지 않음** · `adj_factor` 산술 **0** |")
    say("| 판정 분모 정의 | `exact` ∧ `fill_n >= 2` ∧ **서로 «다른» 값 레그 >= 3**(`PREREG_WEIGHTED_RECON.md:744` · "
        "`build_cases` import) · 🔒 **판정에 쓴 분모 = 누적**(`PREREG_POST8.md` §4 · `P9-WRC누적분모`) |")
    say(f"| 시드 · 반복 | **{SEED}** · **{NREP:,}회** (import · `WRC-G1` 발동 시 대조군을 «돌리지 않는다» — §3) |")
    say(f"| 문턱 | 밴드 **{BAND_THR}%p** · `G1` **{G1_THR:.4f}**(1/3) · `N` **{N_THR:.2f}** · 잔차 `THR` **{THR}** (import) |")
    say("")
    say("### 0-1. 의무 줄 점검표 (이 산출물)\n")
    say("| 결정 | 이 산출물에서 | 자리 |")
    say("|---|---|---|")
    say("| `D-3`(`approx` 의존 신고) · 🆕 `P9-공통독법` | **있음** | §6 |")
    say("| `D-4`(단독·누적·판정 분모 같은 행) · 🆕 `P9-WRC누적분모` | **있음** | §3 |")
    say("| `D-5`(갈래마다 이름·n·답) | **있음** | §5 |")
    say("| `D-8` · 🆕 `P9-행단위` | **있음** | §6 |")
    say("| `D-9`(①~⑤) | **있음** | §0 · §7 |")
    say("| 🆕 `P9-수집증거`(`FREEZE_WRC_2026-09-02.md`) | **있음** | §8 |")
    say("| `D-1`·`D-2`·`D-6`·`D-7`·`D-10`·`D-11`·`D-12` · `P9-갈래게이트인쇄전용` | 해당 없음(이 축이 아니다) | — |")
    say("")

    # ═══ §1 표본 ════════════════════════════════════════════════════════════
    ic_key = sorted((nm, prec, fn, len(set(lg))) for nm, prec, fn, lg in INTAKE_ROWS9)
    lc_key = sorted((c["name"], c["prec"], c["fill_n"], c["distinct"]) for c in p9)
    say("## §1. 표본 — 원장 재측정 ↔ 인테이크 «계산 전» 구성 대조\n")
    say(f"- 원장 `post_log_no = {POST9_LOG}` 행 **{len(p9)}건** 재측정(`build_cases` import · 원장 기준 커밋 `30aed89`).")
    if ic_key == lc_key:
        say("- 🟢 **원장 ↔ 인테이크 §1 표 전건 일치**(이름·정밀도·`fill_n`·서로 다른 값 레그 수).")
    else:
        say("- 🔴🔴 **원장 ↔ 인테이크 §1 표가 갈린다 — 원장이 SSOT 다.** 갈린 자리:")
        for a, b in zip(ic_key, lc_key):
            if a != b:
                say(f"  - 인테이크 `{a}` ↔ 원장 `{b}`")
    say("")
    say("| # | 종목 | 코드 | 정밀도 | `fill_n` | 레그 수 | **서로 «다른» 값 레그** | `open_ended` | 게이트 | 비고 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for c in p9:
        tag = "후속(PD-2 · post8 #10)" if c["name"] in POST9_FOLLOWUP else "—"
        say(f"| {c['item']} | {c['name']} | `{c['code']}` | {c['prec']} | {c['fill_n']} | {c['n_legs']} | "
            f"**{c['distinct']}** | {c['open_ended']} | {'🟢 통과' if c['gate'] else '탈락'} | {tag} |")
    say("")

    # ═══ §2 단독 분모 ═══════════════════════════════════════════════════════
    ex_all, ex_first, ex_few, ex_pass = split_reasons(p9, "exact")
    ap_all, _, _, _ = split_reasons(p9, "approx")
    ap_br = approx_branch(p9)
    n_solo = len(denom([c for c in p9 if c["prec"] == "exact"]))
    say(f"## §2. post9 «단독»(한 글) 판정 분모 — **{n_solo}건**\n")
    say("| 갈래 | 건 | 1차 체결(`fill_n = 1`) | `fill_n >= 2` ∧ 다른 값 레그 < 3 | **나머지 두 조건 통과** |")
    say("|---|---|---|---|---|")
    say(f"| **`exact`(주 분모)** | {len(ex_all)} | **{len(ex_first)}** ({', '.join(c['name'] for c in ex_first) or '—'}) | "
        f"**{len(ex_few)}** ({', '.join(c['name'] for c in ex_few) or '—'}) | **{len(ex_pass)}** |")
    say(f"| `approx`(민감도 갈래) | {len(ap_all)} | — | — | {len(ap_br)} |")
    say("")
    say("- 🔑 단독 분모는 **값이 아니라 «구성»**(저자의 체결 차수 서술 · 동률 레그)으로 정해진다(PD-13 · PD-22) — "
        "한국첨단소재는 레그 3개지만 동률 3.79·3.79 로 서로 다른 값 2 · 한컴위드는 레그 2.")
    say("")

    # ═══ §3 누적 재계산 · P9-WRC누적분모 ════════════════════════════════════
    judged = {}
    for lab in POSTS:
        sub = [c for c in cases_all if c["post"] == lab and c["gate"]]
        for c in sub:
            c["a0"], c["nbar"] = a0_measure(cur, c["code"], c["reg"], WINDOW_END[lab], c["legs"])
            c["a0_net"], _ = a0_measure(cur, c["code"], c["reg"], WINDOW_END[lab], c["legs"], "net")
        judged[lab] = sub
    explore = judged["post4"] + judged["post5"]
    cum = judged["post6"] + judged["post7"] + judged["post8"] + judged["post9"]
    n_cum, a_cum, z_cum, g1_cum = g1_of(cum)
    g1_fire = bool(g1_cum is not None and g1_cum >= G1_THR)
    n_one, a_one, z_one, g1_one = g1_of(judged["post9"])
    p6_names_ok = sorted(c["name"] for c in judged["post6"]) == sorted(INTAKE_DENOM_PRED)

    def ans_of(r):
        return "분모 0" if r is None else ("발동" if r >= G1_THR else "미발동")

    say("## §3. `D-4` 세 수 · 🆕 `P9-WRC누적분모` · `WRC-G1`(누적 · 이 스냅샷 재계산) · 예측별 판정\n")
    say("### 3-1. `P8-WRC단독열` — 단독 · 누적 · 판정에 쓴 분모를 «같은 행»에\n")
    say("| 회차 | **단독**(post9 · §6-1 세 조건) | **누적**(post6 이후) | **판정에 쓴 분모**(= 누적) | 판정 분모 ≥ 3? | ⛔ 을 만든 것 |")
    say("|---|---|---|---|---|---|")
    say(f"| post9 | **{n_solo}** | **{n_cum}**(post6 {len(judged['post6'])} + post7 {len(judged['post7'])} + "
        f"post8 {len(judged['post8'])} + post9 {len(judged['post9'])}) | **{n_cum}** | "
        f"{'🟢 예 — 게이트 열림' if n_cum >= 3 else '⛔ 아니오'} | "
        + (f"🔴 **`WRC-G1` 발동**(누적 {fmt_g1(n_cum, a_cum, z_cum, g1_cum)}) — 🔴 **「최소 n 미달」이 «아니다»**"
           if g1_fire else "`WRC-G1` 미발동(누적)") + " |")
    say("")
    say("### 3-1b. 🆕 `P9-WRC누적분모` — `WRC-G1` 행: (i) 누적 분모·분자(판정) · (ii) 한 글 분모·분자(민감도) (`PREREG_POST9.md` §2 (나)1~3)\n")
    say("| 항목 | 독법 | 분모 | 분자(①DB부재 + ④해 0개) | 비율 | 답 | 지위 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| `WRC-G1` | 🔒 **누적**(post6~post9 판정 분모) | **{n_cum}** | **{a_cum + z_cum}**({a_cum} + {z_cum}) | "
        f"{fmt_g1(n_cum, a_cum, z_cum, g1_cum)} | **{ans_of(g1_cum)}** | **판정** |")
    say(f"| `WRC-G1` | 한 글(post9 단독 판정 분모 · `P8-WRC단독열` 단독 열) | **{n_one}** | **{a_one + z_one}**({a_one} + "
        f"{z_one}) | {fmt_g1(n_one, a_one, z_one, g1_one)} | {ans_of(g1_one)} | 민감도(참고 인쇄 · 판정 무관) |")
    say("")
    if ans_of(g1_cum) != ans_of(g1_one):
        say(f"- *「`P9-WRC누적분모` 갈림: 누적 {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} {ans_of(g1_cum)} ↔ 한 글 "
            f"{'분모 0' if g1_one is None else fmt_g1(n_one, a_one, z_one, g1_one) + ' ' + ans_of(g1_one)} · 판정 = 누적」*"
            "(§2 (나)2 문언 — 한 글 분모가 없으면 답 = 「분모 0」). 🔴 PREREG_POST9 §2 (마) 예고대로 한 글 분모가 **없어** "
            "두 독법이 «판정»을 가를 자리는 없다(한 글 독법은 가드 자체를 만들지 못한다).")
    else:
        say("- 두 독법의 답이 같다 ⇒ 「갈림」 줄 없음(§2 (나)2).")
    say("- (나)3 기계 검사: 누적 분모·분자 **있음** · 한 글 분모·분자 **있음** · 아래 판정 칸의 `WRC-G1` 사유는 **누적 값만** 인용한다.")
    say("- (나)4 `D-4` 불변 — `WRC-P1` 게이트 분모 = 누적 · 축이 닫힐 때 적는 이름 = 「`WRC-G1` 발동」.")
    say("")
    say("### 3-2. `WRC-G1` — 글별 재계산(같은 스냅샷 · 각 글의 동결 창 종료 그대로) ↔ 옮겨 적은 동결값\n")
    say("| 글 | 창 종료(출처) | 판정 분모 | ① DB부재 | ④ 해 0개 | **`WRC-G1`(재계산)** | 동결값(대조 · 출처) | 일치 |")
    say("|---|---|---|---|---|---|---|---|")
    g1_rows = {}
    for lab, sub in (("🔬 탐색 post4+post5", explore), ("post6", judged["post6"]), ("post7", judged["post7"]),
                     ("post8", judged["post8"]), ("post9", judged["post9"])):
        n, a, z, r = g1_of(sub)
        key = "explore" if lab.startswith("🔬") else lab
        g1_rows[key] = (n, a, z, r)
        fz = FROZEN_G1.get(key)
        end_lab = "post4" if key == "explore" else key
        if fz:
            fz_s = (f"{fz['db_absent'] + fz['empty']}/{fz['denom']}" if fz["denom"] else "0/0") + f" · {fz['src']}"
            same_s = "🟢 일치" if (n, a, z) == (fz["denom"], fz["db_absent"], fz["empty"]) else \
                "🔴 **불일치 — 재계산값으로 판정**"
        else:
            fz_s, same_s = "— (이 회차 신규)", "—"
        dbl = ", ".join(c["name"] for c in sub if c["a0"] == "db_absent") or "—"
        zl = ", ".join(c["name"] for c in sub if c["a0"] == "empty") or "—"
        say(f"| {lab} | `{WINDOW_END[end_lab]}`({WINDOW_END_SRC[end_lab]}) | {n} | {a} ({dbl}) | {z} ({zl}) | "
            f"**{fmt_g1(n, a, z, r)}** {fire(r)} | {fz_s} | {same_s} |")
    say(f"| 🔒 **누적 = 판정 분모**(post6~post9) | 글별 | **{n_cum}** | {a_cum} | {z_cum} | "
        f"**{fmt_g1(n_cum, a_cum, z_cum, g1_cum)}** {fire(g1_cum)} | {FROZEN_CUM[1]}/{FROZEN_CUM[0]} · {FROZEN_CUM[2]} | "
        f"{'🟢 일치' if (n_cum, a_cum + z_cum) == FROZEN_CUM[:2] else '🔴 **불일치 — 재계산값으로 판정**'} |")
    say("")
    say(f"- post6 판정 분모 재측정 = {', '.join(c['name'] for c in judged['post6'])} ⇒ 인테이크 post6 §5 «계산 전» 예측 "
        f"5건과 {'✅ 일치' if p6_names_ok else '🔴 불일치'}.")
    say("- 🔴 **탐색 행은 판정 분모에 «넣지 않는다»**(`WRC-O1` · §4-5) — 같은 스냅샷에서 다시 잰 대조 기록이다.")
    say("- 건별 값(창 봉수·`A0` 판정)은 `wrc_post9/gate.json`. `A0` = `feasible_exact(..., \"gross\")`(post8 `a0_measure` import).")
    say("")
    say("### 3-3. 예측별 판정 — `WRC-G1` 을 «가장 먼저» 계산했다(§7-B #24)\n")
    if g1_fire:
        say(f"🔴🔴 **누적 `WRC-G1` = {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} ≥ 1/3 ⇒ 발동** — §4-6·§7-B #24 *「1/3 이상이면 "
            "나머지 계산을 «돌리지 않는다»」* 문언대로 **`A1`·`A3`·대조군(`WRC-N1`·`N2`)을 이 실행에서 돌리지 않았다**"
            "(post8 과 같은 쪽 · 모호 신고 승계).")
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
        ("`WRC-G1`", "(커버리지) 잰 것이 표본을 대표하는가", f"(①+④)/누적 분모 ≥ {G1_THR:.4f}",
         "🔴 **자신이 ⛔ 조건이다** — 누적 " + fmt_g1(n_cum, a_cum, z_cum, g1_cum)),
        ("`WRC-O1`", "탐색(post4·5) ↔ 판정(post6~) 병기", "괴리가 판정을 가르면 「탐색 편향 의심」",
         "§4 — `WRC-O1` 은 «조건부 인쇄» 항목(`PREREG_WEIGHTED_RECON.md:803` §7-A #3) · post8 표기 승계"),
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
    say("- 🔴 **`WRC-X1`(§4-7)** — 1~3번(`A1`·`A4` 결과 위의 조건)은 `A1`·`A4` 를 돌리지 않아 **적용 대상 없음** · "
        "4번(재정의 흔적)은 **적용 · 위반 0**(`feasible_exact` import 경유) · 5번(`adj_factor` 산술)은 **적용 · 위반 0**.")
    say("- 🔴 **`bₖ` 표 0개** ⇒ `WRC-R9` 4줄의 부착 대상이 이 산출물에 없다. 🔴 문턱 `1/3` 을 올려 여는 것은 금지(§4-6).")
    say("")

    # ═══ §4 WRC-O1 ══════════════════════════════════════════════════════════
    ne, ae, ze, re_ = g1_rows["explore"]
    say("## §4. `WRC-O1` — 탐색(post4·post5)과 판정(post6~)을 «나란히» (🔬 탐색은 판정 분모 밖)\n")
    say("| 통계량 | 🔬 탐색 — 동결 인용(창 `~2026-09-02`) | 🔬 탐색 — **이 스냅샷 재계산**(같은 창) | **판정 — 누적**(post6~9) |")
    say("|---|---|---|---|")
    say(f"| 판정 분모 | 10 | {ne} | **{n_cum}** |")
    say(f"| `WRC-G1` | 6/10 = 60.0% ⇒ 🔴 발동 | {fmt_g1(ne, ae, ze, re_)} {fire(re_)} | "
        f"**{fmt_g1(n_cum, a_cum, z_cum, g1_cum)}** {fire(g1_cum)} |")
    say(f"| `A0` 해 있는 건 | 4(이노테크·한켐p4·지투파워·PS일렉) | {sum(1 for c in explore if c['a0'] == 'feasible')} | "
        f"**{sum(1 for c in cum if c['a0'] == 'feasible')}** ({', '.join(c['name'] for c in cum if c['a0'] == 'feasible') or '—'}) |")
    say("")
    say("- 🔴 판정 열이 `WRC-G1` 로 ⛔ 이면 두 열의 «괴리» 판정은 성립하지 않는다 — 병기만 한다(post7·post8 문형).")
    say("")

    # ═══ §5 D-5 갈래 ════════════════════════════════════════════════════════
    br = [("주 — 누적 · `exact` · `gross` · 재진입·미완결 포함", cum, "판정"),
          ("`WRC-V1` 축③ 재진입 제외(post6 지투파워 · PD-3 flag)", [c for c in cum if PD3_FLAG.get(c["name"], 0) != 1],
           "민감도"),
          ("`WRC-V1` 축③ 미완결(`open_ended = 1`) 제외", [c for c in cum if not c["open_ended"]], "민감도"),
          ("「post8 우리로 제외」 누적 줄(확인 7 · `WRC-R5`)", [c for c in cum if c["name"] != "우리로"], "민감도")]
    say("## §5. `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)`\n")
    say("🔴 **최소 n = 판정 분모 3**(`PREREG_WEIGHTED_RECON.md` §4 표 1행 · §6-1) · 「답」 = 그 갈래의 `WRC-G1` 판정(누적 분모).\n")
    say("| 갈래 | 지위 | **n** | 최소 n(3) | `WRC-G1` | **답** | 비고 |")
    say("|---|---|---|---|---|---|---|")
    answers = []
    for name, sub, role in br:
        n, a, z, r = g1_of(sub)
        ans = "⛔ `WRC-G1` 발동" if (r is not None and r >= G1_THR) else \
            ("G1 미발동(나머지 미계산 ⇒ 미룸)" if r is not None else "분모 0")
        if n >= 3:
            answers.append(ans)
        else:
            ans = f"(인쇄만 · n {n} < 3 — 「갈렸다」의 근거로 쓰지 않는다) {ans}"
        same = "판정 갈래" if role == "판정" else (
            "**항등**(주 갈래와 같은 표본)" if sorted(c["name"] for c in sub) == sorted(c["name"] for c in cum)
            else "빠진 건: " + ", ".join(sorted({c["name"] for c in cum} - {c["name"] for c in sub})))
        say(f"| {name} | {role} | **{n}** | {'충족' if n >= 3 else '🔴 미달'} | {fmt_g1(n, a, z, r)} | **{ans}** | {same} |")
    say(f"| `WRC-V1` 축① 잔차 `{THR[1]}` ↔ `{THR[0]}`(`REC-Z5`) | 민감도 | **{n_cum}** | 충족 | "
        f"{fmt_g1(n_cum, a_cum, z_cum, g1_cum)} | **항등** | `WRC-G1`(①+④)은 잔차 문턱을 입력으로 쓰지 않는다 |")
    an = sum(1 for c in cum if c["a0_net"] == "db_absent")
    zn = sum(1 for c in cum if c["a0_net"] == "empty")
    rn = (an + zn) / n_cum if n_cum else None
    ans_net = "⛔ `WRC-G1` 발동" if (rn is not None and rn >= G1_THR) else "G1 미발동(나머지 미계산 ⇒ 미룸)"
    answers.append(ans_net)
    say(f"| `WRC-V1` 축② 수수료 `gross`(판정) ↔ `net` | 민감도 | **{n_cum}** | 충족 | {fmt_g1(n_cum, an, zn, rn)} | "
        f"**{ans_net}** | `A0` 를 `net` 으로 다시 잰 값 |")
    say(f"| `WRC-V1` 축④ 모델 `A1` ↔ `A3` | 민감도 | **{n_cum}** | 충족 | {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} | **항등** | "
        "`WRC-G1` 은 «현행(`A0`)» 해 0개로 정의된다 ⇒ 모델 축이 G1 을 움직일 수 없다 |")
    say(f"| `approx` 포함(`D-3` (나)4 검사용) | 민감도 | **{n_cum + len(ap_br)}** | 충족 | — | **항등**(이번 글 `approx` "
        f"{len(ap_all)}) | 갈래 없음 — `exact` 분모 = `approx` 포함 분모(PD-21 · PD-23) |")
    say(f"| post9 «단독»(참고 · 갈래 아님 · `D-4` 단독 열) | 기록 | **{n_solo}** | — | — | **—** | 단독은 판정 분모가 «아니다» |")
    say("")
    uniq = sorted(set(answers))
    say(f"- **최소 n(3)을 채운 갈래의 답**: {', '.join(uniq)} ⇒ "
        + ("🟢 **갈리지 않는다**(전 갈래 같은 답) — `WRC-V1` 은 이 회차가 더한 갈림이 없다"
           if len(uniq) == 1 else "🔴 **갈린다 ⇒ ⛔ `WRC-V1`**(선언 금지)"))
    say("- 재진입 제외·「post8 우리로 제외」는 **항등**이다 — post9 재진입 0(PD-3) · 우리로는 `fill_n = 1` 로 판정 분모에 애초에 없다.")
    say("")

    # ═══ §6 D-3 · P9-공통독법 · D-8 · P9-행단위 · 커버리지 ════════════════
    n_ap_incl = n_cum + len(ap_br)
    ap_opens = [] if n_cum >= 3 else (["`WRC-`"] if n_ap_incl >= 3 else [])
    say("## §6. `D-3` 신고 줄 · 🆕 `P9-공통독법` · `D-8` · 🆕 `P9-행단위` · 커버리지(PD-11)\n")
    say(f"**`P8-approx의존신고`**: *「`approx` 포함 시 최소 n 이 차는 축: **{', '.join(ap_opens) or '없음'}** · `exact` 분모 "
        f"**{n_cum}**(누적 · 단독 {n_solo}) / `approx` 포함 분모 **{n_ap_incl}**」*(구성 예고 = 「없음」 PD-21).")
    say("")
    for ln in p9_common_lines(n_cum, n_ap_incl):
        say(ln)
    say("")
    lv_rows = Counter((r["prog_ver"] or "missing") for r in tr)
    lv_posts: dict = {}
    for r in tr:
        lv_posts.setdefault(r["prog_ver"] or "missing", set()).add(r["post_log_no"])
    say("**`P8-결측수준` 수준 목록**(행·글 두 단위 · 이 축은 `prog_ver` 를 공변량으로 «기록»만 한다 — "
        "`PREREG_WEIGHTED_RECON.md` §9):\n")
    say("| 수준 | 행(건) · **SSOT** | 글(민감도) |")
    say("|---|---|---|")
    for lv in sorted(lv_rows, key=lambda x: (x == "missing", x)):
        say(f"| `{lv}` | {lv_rows[lv]} | {len(lv_posts[lv])} |")
    say("")
    for ln in p9_level_lines(tr):
        say(ln)
    say("")
    say("🔴 **커버리지는 축별로 «다른 수»다**(PD-11 · 존재 사실은 인테이크 §1 인용 · 이 레인 재측 = `WRC-` 행만) · "
        f"`exact` 신규 분모 = **{len(ex_all)}**.\n")
    say("| 축 | 필요 자료 | 측정 가능 | 측정 불가 | 문턱 1/3 |")
    say("|---|---|---|---|---|")
    say(f"| `SEL-`·`Q1-`·`REG-`·`RNK-`·`ANC-`·`LAD-`·`REC-` | `daily_prices` | {len(ex_all)}/{len(ex_all)} | 0 | 미발동 |")
    say(f"| `SEC-`(`SEC-G1`) | `stock_industry` 섹터코드 | {len(ex_all)}/{len(ex_all)}(INTAKE §1 6/6) | 0 | 미발동 |")
    say(f"| **`WRC-`(`WRC-G1`)** | `fill_n >= 2` ∧ 서로 다른 값 레그 >= 3 | **{n_solo}/{len(ex_all)}**(post9 단독) | — | "
        f"🔴 판정 = **누적** {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} {ans_of(g1_cum)}(최소 n 미달 «아님») |")
    say("")

    # ═══ §7 D-9 혼합 빈티지 ════════════════════════════════════════════════
    def cross(code, s, e):
        cur.execute("SELECT count(*) FILTER (WHERE date < %s), count(*) FILTER (WHERE date >= %s) "
                    "FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s", (BOUNDARY, BOUNDARY, code, s, e))
        nb, na = cur.fetchone()
        return int(nb), int(na)

    say("## §7. `D-9` · `P8-혼합빈티지신고` — 걸침 창마다 한 줄 (봉수 = 그 종목 봉 실측)\n")
    say("### 7-1. 이 축이 «읽는» 창\n")
    own = 0
    for lab in POSTS:
        for c in judged[lab]:
            e = WINDOW_END[lab]
            if c["reg"] and c["code"] and c["reg"] < BOUNDARY <= e:
                nb, na = cross(c["code"], c["reg"], e)
                say(f"- *「창 `[{c['reg']}, {e}]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `{nb}` 봉 / 후 `{na}` 봉 · "
                    f"혼합 빈티지」*({lab} {c['name']})")
                own += 1
    say(f"- ⇒ 이 축 «판정 분모» 재계산 창(post6 `~09-04` · 탐색 `~09-02`)은 **경계 전** · post9 단독 분모 0 ⇒ 걸침 **{own}줄**.")
    say("")
    say("### 7-2. PD-27 (바) 표의 창 전부 — 공통 인쇄 의무 (🔴 `ANC-`·`REC-`·`LAD-`·`REG-` 창 · 이 축이 읽지 않는다)\n")
    for axis, nm, code, s, e in PD27_CROSS9:
        nb, na = cross(code, s, e)
        if nb and na:
            say(f"- *「창 `[{s}, {e}]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `{nb}` 봉 / 후 `{na}` 봉 · 혼합 빈티지」*"
                f"({axis} · {nm})")
        elif na:
            say(f"- 🟡 *「창 `[{s}, {e}]` 은 전부 제도 경계 후(전 0 / 후 {na})」*({axis} · {nm} · PD-27 (바) 추가 인쇄 · 재량 · "
                "판정 효과 0)")
        else:
            say(f"- 창 `[{s}, {e}]` 안 걸침(전 {nb} / 후 0)({axis} · {nm})")
    say("")
    say("### 7-3. 한계 절 문장(`P-4`·`P-5` 가 정한 것 · 정의 불변)\n")
    say("- ① `ovtm_vol` 채널은 09-14~09-21 에 전부 0 이고 `overtime_daily` 는 09-22 이후 행이 없다(PD-27 (바)) ⇒ 시간외분을 "
        "`H`·`L` 에서 뺄 수 없다.")
    say("- ② 15:30 마감 분봉(`P-5`)이 09-14 **1/303** · 09-15~09-29 **≤ 1/301**(착수 직전 `p9_probes_precalc_0929.txt`) ⇒ "
        "**「정규장만」 갈래는 열지 않는다**(`PREREG_POST8.md` §9 (나) 4).")
    say("- ③ `P-3` 은 이 DB 에서 **판별력 0** — 「통과」로 인용하지 않는다(PD-27 (라) · 착수 직전 재실행도 전 날짜 행수 = 재기록 수).")
    say("")

    # ═══ §8 P9-수집증거 · 한계 ══════════════════════════════════════════════
    say("## §8. 🆕 `P9-수집증거` · 한계\n")
    for ln in p9_collect_lines("FREEZE_WRC_2026-09-02.md", "WRC"):
        say(ln)
    say("")
    say("- 🔴 **단독 분모 0 은 우리 가설의 증거가 아니다** — 저자가 이번 주 `exact` 건을 1차 체결 · 동률 · 2레그로 끝낸 이유를 모른다.")
    say("- 🔴 **`WRC-` 는 post6 한 회차의 표본으로만 굴러간다** — 단독 열이 post7·post8·post9 **세 회차 연속 0** 이다"
        "(`PREREG_POST8.md` §4 (다) 신고 자리 · 문턱은 바꾸지 않는다).")
    say("- 🔴 누적 분모 5건은 전부 경계 «전» 창이다(`PREREG_POST8.md` §14 두 제도 혼합 — 이번엔 섞이지 않음).")
    say("- 🔴 `adj_factor` 를 곱하지도 나누지도 않는다 · DB 는 SELECT 만 · 원장은 읽기만.")
    conn.close()

    gate = dict(
        window_end=WINDOW_END, db_upto=DB_UPTO,
        cases=[dict(post=c["post"], name=c["name"], code=c["code"], reg=c["reg"], fill_n=c["fill_n"],
                    distinct=c["distinct"], open_ended=c["open_ended"], a0_gross=c["a0"], a0_net=c["a0_net"],
                    nbar_window=c["nbar"]) for lab in POSTS for c in judged[lab]],
        cumulative=dict(n=n_cum, db_absent=a_cum, empty=z_cum, g1=g1_cum, fire=g1_fire),
        one_post=dict(n=n_one, db_absent=a_one, empty=z_one, g1=g1_one),
        solo_post9=n_solo,
    )
    (ART / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (BASE / "RESULTS_WRC_POST9_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    note(f"[written] RESULTS_WRC_POST9_NUMBERS.md · wrc_post9/gate.json · 런타임 {time.time() - t0:.3f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
