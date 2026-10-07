# -*- coding: utf-8 -*-
"""`WRC-` 축 **판정** 실행 — 10번째 글(`logNo=224429747319` · 발행 2026-10-02 금 · 거래일).

🔴 **얇은 판** — post9 판(`run_wrc_post9.py`) 이 import 한 동결 판정 경로(`a0_measure`·`g1_of`·`fmt_g1`·`fire`)와
공통 인쇄 함수를 «그대로» import 하고, 글 목록·창·빈티지·출력 경로와 post10 인쇄 의무만 더한다.
판정 로직 새로 쓰기 0 · 새 문턱 0 · 새 예측 0 · 등급 이름 0(§6 단계 아님).

이 회차에 «새로» 걸리는 것:
  · `P9-결측분리`(`PREREG_POST9.md` §4 (나)2·3·5 · post10 부터 구속 · PD-34) — 수준 목록(버전 적힌 행만) + 「결측 n」 줄.
  · `P9-스탬프통일`(PD-35) — `wrc_post10/read_stamp.json` 키 `first_read_kst`·`timezone`·`fingerprint`.
  · `P10-기업행위봉`(`PREREG_POST10.md` §3 (나) · `F-3`) — 신고 줄 + 「기업행위 건 제외」 갈래 값 의무 인쇄(답(참고) · 세지 않는다).
  · 🔒 #1 ⓐ(PD-43) 「샌즈 제외」(`WRC-R5` 구조차단 · 갈리면 ⛔ `WRC-V1`) · `D-4` 단독 3 · 누적 8 · 판정 분모 8(PD-22).

🔴 라이브 트리 import 0 · DB 는 **SELECT 만** · `adj_factor` 산술 0 · 원장 «읽기»만 · 원문 3파일은 md5 만 읽는다.
🔴 **라이브 채택 대상이 아니다.**

`p10_level_lines()`·`p10_collect_lines()` 는 같은 회차 `run_ranking.py --stage post10` 이 import 해 같은 문언을 인쇄한다.
"""
from __future__ import annotations

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
from run_wrc_post8 import BOUNDARY, CODES8, a0_measure, fire, fmt_g1, g1_of
from run_wrc_post9 import (
    CODES9,
    FROZEN_G1 as FROZEN_G1_P9,
    WINDOW_END as WINDOW_END_P9,
    WINDOW_END_SRC as WINDOW_END_SRC_P9,
    p9_common_lines,
    p9_live_lines,
    post_label as post_label_p9,
)

BASE = Path(__file__).resolve().parent
ART = BASE / "wrc_post10"
OUT: list[str] = []

POST10_LOG = "224429747319"      # INTAKE_2026-10-04_post10.md 머리말
POST10_DATE = "2026-10-02"       # 발행일(금 · 거래일) — PD-1
DB_UPTO = "2026-10-02"           # 🔴 창 종료 = 발행 당일 봉 «포함» · 전 축(`WRC-` 포함) · PD-1
SWEEP_D1 = "2026-10-06 15:35:00"  # 10-02 봉의 D+1 sweep(PD-27 (마) · 10-05 대체공휴일)
MGR_WIN = ("2026-08-12", "2026-10-02")   # PD-27 (마) 2 (f) 창 구간
START_CAP = "2026-10-08 23:59:59"        # `P10-착수상한`(F-4)
PRECALC_DIR = "D:/archive/tasso-program-journal-20261004/probes_precalc_1007/"
RAW_ARCHIVE = Path("D:/archive/tasso-program-journal-20261004")
PREDECISION10 = "PREDECISION_2026-10-04_post10.md"

WINDOW_END = dict(WINDOW_END_P9, post10=DB_UPTO)
WINDOW_END_SRC = dict(WINDOW_END_SRC_P9, post10="`PREDECISION_2026-10-04_post10.md` PD-1")
POSTS = ("post4", "post5", "post6", "post7", "post8", "post9", "post10")

# `INTAKE_2026-10-04_post10.md` §1 표 «그대로»(12/12 · 코드 12/12). HT로보틱스 = 396300(DB 이름 세아메카닉스).
CODES10 = {"한컴위드": "054920", "라온시큐어": "042510", "범한퓨얼셀": "382900", "서산": "079650",
           "코데즈컴바인": "047770", "샌즈랩": "411080", "빛샘전자": "072950", "성호전자": "043260",
           "HT로보틱스": "396300", "한켐": "457370", "뷰노": "338220", "우리로": "046970"}
POST10_FOLLOWUP = ("한컴위드", "코데즈컴바인", "빛샘전자")             # PD-2 · 등록일 축 밖(`none`)
POST10_REENTRY = ("범한퓨얼셀", "서산", "한켐", "우리로")                # PD-3 · 재진입 4(§1-5 항등 아님)
SANDS = "샌즈랩"                                                      # 🔒 #1 ⓐ · `WRC-R5` 구조차단

# `INTAKE_2026-10-04_post10.md` §1 표 — «계산 전» 구성. 원장이 SSOT 이고 여기선 대조만 한다. (종목, 정밀도, fill_n, 레그)
INTAKE_ROWS10 = [
    ("한컴위드", "none", 2, [7.50, 5.48]),
    ("라온시큐어", "exact", 4, [12.78, 9.52, 6.40, 2.33, 0.32, -0.49]),
    ("범한퓨얼셀", "exact", 1, [7.79, 0.38]),
    ("서산", "exact", 5, [3.01, 0.38]),
    ("코데즈컴바인", "none", 2, [0.12]),
    ("샌즈랩", "exact", 3, [5.24, 4.88, 0.29, -0.02]),
    ("빛샘전자", "none", 1, [27.52, 25.34]),
    ("성호전자", "exact", 1, [26.39, 17.92, 13.71, 9.28]),
    ("HT로보틱스", "exact", 3, [16.93, 12.36, 7.65, 7.63, 7.62]),
    ("한켐", "exact", 1, [10.37]),
    ("뷰노", "exact", 1, [15.63, 2.18]),
    ("우리로", "exact", 1, [19.47, 15.44, 11.58]),
]

FROZEN_G1 = dict(FROZEN_G1_P9)
FROZEN_G1["post9"] = dict(denom=0, db_absent=0, empty=0, src="`RESULTS_WRC_POST9_NUMBERS.md` §3-2")
FROZEN_CUM9 = (5, 4, "`RESULTS_WRC_POST9_NUMBERS.md` §3-2 누적 행(4/5)")   # post6~post9 누적(대조용)


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


# ═══ 세 축(`WRC`·`RNK`·`SEC`) 공통 — post10 인쇄 의무 ═══════════════════════════════════════════
def p10_level_lines(rows) -> list[str]:
    """`P9-행단위` + 🆕 `P9-결측분리`(PD-26 · PD-34) — 수준 목록(버전 적힌 행만 · `missing` 은 괄호 안 병기) + 「결측 n」 줄."""
    lv_rows: Counter = Counter()
    lv_posts: dict = {}
    for r in rows:
        k = r["prog_ver"] or "missing"
        lv_rows[k] += 1
        lv_posts.setdefault(k, set()).add(r["post_log_no"])
    keys = sorted(k for k in lv_rows if k != "missing")
    body = " · ".join(f"`{k}` {lv_rows[k]}/{len(lv_posts[k])}" for k in keys)
    miss = f"{lv_rows.get('missing', 0)}/{len(lv_posts.get('missing', ()))}"
    return [f"🆕 **`P9-결측분리`**(`PREREG_POST9.md` §4 (나)2·3·5 · PD-34): *「수준(행/글): {body} · SSOT = 행"
            f"(`PREREG_POST9.md` §4)(민감도 · `missing` 을 수준으로 둔 목록: 위 {len(keys)}수준 + `missing` {miss})」*",
            f"- *「결측 n = {miss}」*(`missing` 은 수준이 아니다 · post10 행은 버전 `1.0.43` 이 적혀 있어 결측 n 에 더해지지 않는다).",
            "- *「부호 갈림 검사: 통계량 정의 없음(기록만)」*(`PREREG_POST9.md` §4 (나)4 — 이 축은 버전을 «기록»만 한다)."]


def _git(*args) -> str:
    r = subprocess.run(["git", "-C", str(BASE), *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else f"<git exit {r.returncode}>"


def _git_ok(*args) -> bool:
    return subprocess.run(["git", "-C", str(BASE), *args], capture_output=True).returncode == 0


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else "<없음>"


def p10_collect_lines(freeze_name: str, axis: str) -> list[str]:
    """`P9-수집증거`(`PREREG_POST9.md` §5) post10 판 — 🔴 `addDate` 제3자 증거는 «빠진다»(PD-0 · 발행이 동결보다 먼저)."""
    fr = _git("log", "--diff-filter=A", "--format=%h %ci", "--", freeze_name).split("\n")[-1]
    pdc = _git("log", "--diff-filter=A", "--format=%h %ci", "--", PREDECISION10).split("\n")[-1]
    fr_sha, pd_sha = fr.split(" ")[0], pdc.split(" ")[0]
    anc = _git_ok("merge-base", "--is-ancestor", fr_sha, pd_sha)
    head = (BASE / PREDECISION10).read_text(encoding="utf-8")
    m_fetch = re.search(r"\*\*수집\*\*[^\n]*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?) KST", head)
    fetch = m_fetch.group(1) if m_fetch else "<못 찾음>"
    md5_ok, md5_s = True, []
    for fn in (f"post_{POST10_LOG}.html", f"post_{POST10_LOG}.txt", f"post_{POST10_LOG}_images.json"):
        m = re.search(r"\| `" + re.escape(fn) + r"` \| `([0-9a-f]{32})` \|", head)
        rec = m.group(1) if m else "<없음>"
        arc, wt = _md5(RAW_ARCHIVE / fn), _md5(BASE / fn)
        ok = rec == arc == wt
        md5_ok &= ok
        md5_s.append(f"`{fn}` 기록 `{rec[:8]}…` · 보관본 `{arc[:8]}…` · 작업트리 `{wt[:8]}…` {'✅' if ok else '🔴'}")
    raw_add = _git("log", "--oneline", "--diff-filter=A", "--", f"post_{POST10_LOG}.html")
    remote = _git("branch", "-r", "--contains", pd_sha).replace("\n", " ").strip()
    out = [f"🆕 **`P9-수집증거`**(`PREREG_POST9.md` §5 (나)1 · `{freeze_name}` · 이 회차 `{axis}`):",
           f"- ① `git log --diff-filter=A --format='%h %ci' -- {PREDECISION10}` = **`{pdc}`** · ③ = `{freeze_name}` 추가 "
           f"커밋 `{fr}` · `git merge-base --is-ancestor {fr_sha} {pd_sha}` = **{'참' if anc else '거짓'}**",
           f"- ② `{PREDECISION10}` 머리 fetch 시각 **{fetch} KST**(관리자 기록 · 자기보고) · 원문 3파일 md5 3줄: "
           + " / ".join(md5_s),
           "- ③ html `addDate` 제3자 증거 = **빠진다**(`PD-0` · 발행 10-02 20:49 이 동결 `522d6dc` 보다 먼저 — 기록 · 통과 조건 아님)",
           f"- (나)2 원문 추가 커밋 명령 `git log --oneline --diff-filter=A -- post_{POST10_LOG}.html` = "
           f"*「{raw_add or '빈 결과'} · 원문 커밋 금지 `README.md:27-29`」* — 🔴 빈 결과는 위반이 아니다",
           f"- (나)4 기록 줄(통과 조건 아님): `git branch -r --contains {pd_sha}` = "
           f"{('`' + remote + '`') if remote else '*「제3자 타임스탬프 없음(미푸시)」*'}"]
    out.append(f"- ⇒ (나)3 기계 검사 두 조건(순서 · md5) {'전부 참 — `' + axis + '` 순서 증거 **미비 아님**.' if (anc and md5_ok) else '🔴 *「그 회차 `' + axis + '` 순서 증거 미비」*'}")
    return out


def post_label(log_no, fallback):
    if log_no == POST10_LOG:
        return "post10"
    return post_label_p9(log_no, fallback)


def code_of(c):
    lab = c["post"]
    if lab in ("post4", "post5"):
        return CODEMAP.get(c["name"])
    return {"post6": CODES6, "post7": CODES7, "post8": CODES8, "post9": CODES9, "post10": CODES10}[lab].get(c["name"])


def corp_event_scan(cur, code, s, e):
    """`P10-기업행위봉` — ⓐ `corp_events` `split` 행 · ⓑ `daily_prices.volume = 0` 봉 · 창 안 `corp_events` 전 행(기록 줄)."""
    cur.execute("SELECT event_date, event_type, coalesce(meta->>'report_nm', '') FROM corp_events "
                "WHERE stock_code=%s AND event_date BETWEEN %s AND %s ORDER BY event_date, event_type", (code, s, e))
    ev = [(str(d), t, nm.strip()) for d, t, nm in cur.fetchall()]
    cur.execute("SELECT date FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s AND volume = 0 ORDER BY date",
                (code, s, e))
    vol0 = [str(r[0]) for r in cur.fetchall()]
    return [x for x in ev if x[1] == "split"], vol0, ev


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
    p10 = [c for c in cases_all if c["log_no"] == POST10_LOG]
    if not p10:
        print("🔴 원장에 post10(`%s`) 행이 없다 — 원장 append 가 먼저다." % POST10_LOG)
        return 2

    read_windows = [(c["reg"], WINDOW_END[lab]) for lab in POSTS for c in cases_all
                    if c["post"] == lab and c["gate"] and c["reg"]]
    span = (min(w[0] for w in read_windows), max(w[1] for w in read_windows))
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices WHERE date BETWEEN %s AND %s", span)
    span_min_u, span_max_u = cur.fetchone()

    # ── D-9 ① 읽은 시각 — `P9-스탬프통일`(PD-35): `wrc_post10/read_stamp.json` ───────────────
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
    say("# RESULTS_WRC_POST10_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_wrc_post10.py`(얇은 판) · 승계(=import) `run_wrc_post9.py`(`CODES9`·창 표·`p9_common_lines`·`p9_live_lines`) · "
        "`run_wrc_post8.py`(`a0_measure`·`g1_of`·`fmt_g1`·`fire`·`CODES8`) · `run_wrc_post7.py`·`run_wrc_post6.py`·"
        "`run_wrc_explore.py`(`build_cases`·`read_ledger`·문턱) · `run_reconstruct_post5.py`(`feasible_exact` — `a0_measure` 경유)")
    say("사전등록 `PREREG_WEIGHTED_RECON.md` §4·§4-6·§4-8·§6-1·§7-B #24 · 동결 `FREEZE_WRC_2026-09-02.md` · "
        "`PREREG_POST8.md` · `PREREG_POST9.md` `E-1`~`E-6` · 🆕 `PREREG_POST10.md`(동결 `522d6dc`) §3 (나) · 인테이크 "
        "`INTAKE_2026-10-04_post10.md` §1·§5 · 결정 `PREDECISION_2026-10-04_post10.md` PD-1·PD-13·PD-21·PD-22·PD-26·PD-27·"
        "PD-34·PD-35·PD-36·PD-43\n")
    say(f"- **창 종료 {DB_UPTO} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · `END` · 전 축(`WRC-` 포함) · PD-1**")
    say(f"- **실행 시 `max(date)` = {max_date} · 그 날짜 행수 {max_rows:,} — 기록만(창 아님)**\n")
    say("> 🔴 **이 산출물은 라이브 채택 대상이 아니다**(`PREREG_POST9.md` §0-1 · post10 도 승계).")
    for ln in p9_live_lines():
        say(ln)
    say("")
    say("> 🔴 **`P9-WRC누적분모`**(`PREREG_POST9.md` §2) — `WRC-G1` 의 판정 분모 = **누적** · 한 글(단독) 분모·분자는 **민감도 행**"
        "(판정 무관). 🔴 새 예측 0 · 새 문턱 0 · 등급 이름 0(§6 단계).\n")
    if first_read > START_CAP:
        say(f"- 🔴 *「`P10-착수상한`: 상한 {START_CAP} · 착수 {first_read} · 초과」*(`F-4` — 신고뿐 · 판정·등급 0)\n")

    # ═══ §0 ═════════════════════════════════════════════════════════════════
    say("## §0. 실행 환경 · 동결 규약 · 공통 인쇄 의무\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 대상 | 10번째 글 `logNo={POST10_LOG}` (발행 **{POST10_DATE}** 금 · 거래일) · 프로그램 버전 **1.0.43**(원 표기 「1.0.43V」) |")
    say(f"| D-9 ① 쿼리 실행 시각(KST) | **{first_read}** ({tzname}) — 이 DB 스냅샷 지문을 이 스크립트가 «처음» 읽은 실행의 "
        "시각(`wrc_post10/read_stamp.json` 키 `first_read_kst` · `P9-스탬프통일` · PD-35) · 이번 실행 벽시계는 stdout |")
    say(f"| D-9 ② 창 구간 `max(daily_prices.updated_at)` | 이 스크립트가 읽는 창 전 구간 `[{span[0]}, {span[1]}]` = "
        f"**{span_max_u}** · PD-27 (마) 창 `[{MGR_WIN[0]}, {MGR_WIN[1]}]` = **{mgr_max_u}** · {DB_UPTO} 봉(행 "
        f"{end_rows:,}) = **{end_max_u}** |")
    say(f"| D-9 ③ | **「{DB_UPTO} 봉은 D+1(2026-10-06) sweep 이후 읽음」** — ① {first_read} ≥ {SWEEP_D1[:16]} : "
        f"{'예' if read_after_d1 else '🔴 아니오'} |")
    say(f"| D-9 ④ (기록 · 통과 조건 아님) | **「창 구간 `min(updated_at)` = {mgr_min_u} ≥ 2026-10-06 15:35: "
        f"{'예' if min_after_d1 else '아니오'}」**(창 `[{MGR_WIN[0]}, {MGR_WIN[1]}]` · PD-27 (마) 2 (f)) · 이 스크립트 창 "
        f"전 구간 `min(updated_at)` = {span_min_u} · 🔴 `updated_at` 은 일괄 갱신 값 — «읽은 시각» 기록 |")
    say(f"| 착수 조건 관측(관리자 · 2차 출처) | 보관 `{PRECALC_DIR}` · 10-06 2,768행 ×3 · 10-07 2,767행 ×3 · 🔴 `P-3` 은 «통과»로 인용하지 않는다 |")
    say("| D-9 ⑤ 혼합 빈티지 | §7 · 「정규장만」 갈래 **열지 않음** · `adj_factor` 산술 **0** |")
    say("| 판정 분모 정의 | `exact` ∧ `fill_n >= 2` ∧ **서로 «다른» 값 레그 >= 3**(`PREREG_WEIGHTED_RECON.md:744` · "
        "`build_cases` import) · 🔒 **판정에 쓴 분모 = 누적**(`P9-WRC누적분모`) |")
    say(f"| 시드 · 반복 | **{SEED}** · **{NREP:,}회** (import · `WRC-G1` 발동 시 대조군을 «돌리지 않는다» — §3) |")
    say(f"| 문턱 | 밴드 **{BAND_THR}%p** · `G1` **{G1_THR:.4f}**(1/3) · `N` **{N_THR:.2f}** · 잔차 `THR` **{THR}** (import) |")
    say("")
    say("### 0-1. 의무 줄 점검표 (이 산출물)\n")
    say("| 결정 | 이 산출물에서 | 자리 |")
    say("|---|---|---|")
    say("| `D-3`(`approx` 의존 신고) · `P9-공통독법` | **있음** | §6 |")
    say("| `D-4`(단독·누적·판정 분모 같은 행) · `P9-WRC누적분모` | **있음** | §3 |")
    say("| `D-5`(갈래마다 이름·n·답 · 「기업행위 건 제외」 포함) | **있음** | §5 |")
    say("| `D-8` · `P9-행단위` · 🆕 `P9-결측분리` | **있음** | §6 |")
    say("| `D-9`(①~⑤) · 🆕 `read_stamp.json` | **있음** | §0 · §7 |")
    say("| 🆕 `P10-기업행위봉`(`F-3` 신고 줄) | **있음** | §5-1 |")
    say("| `P9-수집증거`(`FREEZE_WRC_2026-09-02.md`) | **있음** | §8 |")
    say("| `D-1`·`D-2`·`D-6`·`D-7`·`D-10`·`D-11`·`D-12` · `P10-갈래게이트자리` | 해당 없음(이 축이 아니다) | — |")
    say("")

    # ═══ §1 표본 ════════════════════════════════════════════════════════════
    ic_key = sorted((nm, prec, fn, len(set(lg))) for nm, prec, fn, lg in INTAKE_ROWS10)
    lc_key = sorted((c["name"], c["prec"], c["fill_n"], c["distinct"]) for c in p10)
    say("## §1. 표본 — 원장 재측정 ↔ 인테이크 «계산 전» 구성 대조\n")
    say(f"- 원장 `post_log_no = {POST10_LOG}` 행 **{len(p10)}건** 재측정(`build_cases` import).")
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
    for c in p10:
        tag = ("후속(PD-2)" if c["name"] in POST10_FOLLOWUP else
               ("재진입(PD-3)" if c["name"] in POST10_REENTRY else
                ("항목 내 2 사이클(🔒 #1 ⓐ · `WRC-R5` 구조차단)" if c["name"] == SANDS else "—")))
        say(f"| {c['item']} | {c['name']} | `{c['code']}` | {c['prec']} | {c['fill_n']} | {c['n_legs']} | "
            f"**{c['distinct']}** | {c['open_ended']} | {'🟢 통과' if c['gate'] else '탈락'} | {tag} |")
    say("")

    # ═══ §2 단독 분모 ═══════════════════════════════════════════════════════
    ex_all, ex_first, ex_few, ex_pass = split_reasons(p10, "exact")
    ap_all, _, _, _ = split_reasons(p10, "approx")
    ap_br = approx_branch(p10)
    n_solo = len(denom([c for c in p10 if c["prec"] == "exact"]))
    say(f"## §2. post10 «단독»(한 글) 판정 분모 — **{n_solo}건**\n")
    say("| 갈래 | 건 | 1차 체결(`fill_n = 1`) | `fill_n >= 2` ∧ 다른 값 레그 < 3 | **나머지 두 조건 통과** |")
    say("|---|---|---|---|---|")
    say(f"| **`exact`(주 분모)** | {len(ex_all)} | **{len(ex_first)}** ({', '.join(c['name'] for c in ex_first) or '—'}) | "
        f"**{len(ex_few)}** ({', '.join(c['name'] for c in ex_few) or '—'}) | **{len(ex_pass)}** "
        f"({', '.join(c['name'] for c in ex_pass) or '—'}) |")
    say(f"| `approx`(민감도 갈래) | {len(ap_all)} | — | — | {len(ap_br)} |")
    say("")
    say("- 🔑 단독 분모는 **값이 아니라 «구성»**(저자의 체결 차수 서술 · 동률 레그)으로 정해진다(PD-13 · PD-22) — "
        "예고 = 라온(fill 4)·샌즈(fill 3 · 🔒 #1 ⓐ 사이클 1 서술)·HT(fill 3) · 서산은 fill 5 이나 레그 2.")
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
    cum9 = judged["post6"] + judged["post7"] + judged["post8"] + judged["post9"]
    cum = cum9 + judged["post10"]
    n_cum, a_cum, z_cum, g1_cum = g1_of(cum)
    g1_fire = bool(g1_cum is not None and g1_cum >= G1_THR)
    n_one, a_one, z_one, g1_one = g1_of(judged["post10"])
    n_c9, a_c9, z_c9, _g1_c9 = g1_of(cum9)
    p6_names_ok = sorted(c["name"] for c in judged["post6"]) == sorted(INTAKE_DENOM_PRED)

    def ans_of(r):
        return "분모 0" if r is None else ("발동" if r >= G1_THR else "미발동")

    say("## §3. `D-4` 세 수 · `P9-WRC누적분모` · `WRC-G1`(누적 · 이 스냅샷 재계산) · 예측별 판정\n")
    say("### 3-1. `P8-WRC단독열` · `D-4` — 단독 · 누적 · 판정에 쓴 분모를 «같은 행»에\n")
    say("| 회차 | **단독**(post10 · §6-1 세 조건) | **누적**(post6 이후) | **판정에 쓴 분모**(= 누적) | 판정 분모 ≥ 3? | ⛔ 을 만든 것 |")
    say("|---|---|---|---|---|---|")
    say(f"| post10 | **{n_solo}** | **{n_cum}**(post6 {len(judged['post6'])} + post7 {len(judged['post7'])} + "
        f"post8 {len(judged['post8'])} + post9 {len(judged['post9'])} + post10 {len(judged['post10'])}) | **{n_cum}** | "
        f"{'🟢 예 — 게이트 열림' if n_cum >= 3 else '⛔ 아니오'} | "
        + (f"🔴 **`WRC-G1` 발동**(누적 {fmt_g1(n_cum, a_cum, z_cum, g1_cum)}) — 🔴 **「최소 n 미달」이 «아니다»**"
           if g1_fire else "`WRC-G1` 미발동(누적)") + " |")
    say("")
    say(f"- 🔑 `D-4` 예고(PD-22) = 단독 **3** · 누적 **8** · 판정 분모 **8** ↔ 실측 단독 **{n_solo}** · 누적 **{n_cum}** · 판정 분모 "
        f"**{n_cum}** — {'🟢 일치' if (n_solo, n_cum) == (3, 8) else '🔴 **어긋남 — 실측이 SSOT**'}.")
    say("")
    say("### 3-1b. `P9-WRC누적분모` — `WRC-G1` 행: (i) 누적 분모·분자(판정) · (ii) 한 글 분모·분자(민감도)\n")
    say("| 항목 | 독법 | 분모 | 분자(①DB부재 + ④해 0개) | 비율 | 답 | 지위 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| `WRC-G1` | 🔒 **누적**(post6~post10 판정 분모) | **{n_cum}** | **{a_cum + z_cum}**({a_cum} + {z_cum}) | "
        f"{fmt_g1(n_cum, a_cum, z_cum, g1_cum)} | **{ans_of(g1_cum)}** | **판정** |")
    say(f"| `WRC-G1` | 한 글(post10 단독 판정 분모) | **{n_one}** | **{a_one + z_one}**({a_one} + "
        f"{z_one}) | {fmt_g1(n_one, a_one, z_one, g1_one)} | {ans_of(g1_one)} | 민감도(참고 인쇄 · 판정 무관) |")
    say("")
    if ans_of(g1_cum) != ans_of(g1_one):
        say(f"- *「`P9-WRC누적분모` 갈림: 누적 {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} {ans_of(g1_cum)} ↔ 한 글 "
            f"{'분모 0' if g1_one is None else fmt_g1(n_one, a_one, z_one, g1_one) + ' ' + ans_of(g1_one)} · 판정 = 누적」*")
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
                     ("post8", judged["post8"]), ("post9", judged["post9"]), ("post10", judged["post10"])):
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
    say(f"| 대조 — post6~post9 누적(post10 «전») | 글별 | {n_c9} | {a_c9} | {z_c9} | "
        f"{fmt_g1(n_c9, a_c9, z_c9, _g1_c9)} | {FROZEN_CUM9[1]}/{FROZEN_CUM9[0]} · {FROZEN_CUM9[2]} | "
        f"{'🟢 일치' if (n_c9, a_c9 + z_c9) == FROZEN_CUM9[:2] else '🔴 **불일치 — 재계산값으로 판정**'} |")
    say(f"| 🔒 **누적 = 판정 분모**(post6~post10) | 글별 | **{n_cum}** | {a_cum} | {z_cum} | "
        f"**{fmt_g1(n_cum, a_cum, z_cum, g1_cum)}** {fire(g1_cum)} | — (이 회차 신규 누적) | — |")
    say("")
    say(f"- post6 판정 분모 재측정 = {', '.join(c['name'] for c in judged['post6'])} ⇒ 인테이크 post6 §5 «계산 전» 예측 "
        f"5건과 {'✅ 일치' if p6_names_ok else '🔴 불일치'}.")
    say("- 🔴 **탐색 행은 판정 분모에 «넣지 않는다»**(`WRC-O1` · §4-5) — 같은 스냅샷에서 다시 잰 대조 기록이다.")
    say("- 건별 값(창 봉수·`A0` 판정)은 `wrc_post10/gate.json`. `A0` = `feasible_exact(..., \"gross\")`(post8 `a0_measure` import).")
    say("")
    say("### 3-3. 예측별 판정 — `WRC-G1` 을 «가장 먼저» 계산했다(§7-B #24)\n")
    if g1_fire:
        say(f"🔴🔴 **누적 `WRC-G1` = {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} ≥ 1/3 ⇒ 발동** — §4-6·§7-B #24 *「1/3 이상이면 "
            "나머지 계산을 «돌리지 않는다»」* 문언대로 **`A1`·`A3`·대조군(`WRC-N1`·`N2`)을 이 실행에서 돌리지 않았다**.")
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
         "§4 — `WRC-O1` 은 «조건부 인쇄» 항목(`PREREG_WEIGHTED_RECON.md:803` §7-A #3)"),
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
    say("- 🔴 **`WRC-X1`(§4-7)** — 1~3번은 `A1`·`A4` 를 돌리지 않아 **적용 대상 없음** · 4번(재정의 흔적)은 **적용 · 위반 0**"
        "(`feasible_exact` import 경유) · 5번(`adj_factor` 산술)은 **적용 · 위반 0**.")
    say("- 🔴 **`bₖ` 표 0개** ⇒ `WRC-R9` 4줄의 부착 대상이 이 산출물에 없다. 🔴 문턱 `1/3` 을 올려 여는 것은 금지(§4-6).")
    say("")

    # ═══ §4 WRC-O1 ══════════════════════════════════════════════════════════
    ne, ae, ze, re_ = g1_rows["explore"]
    say("## §4. `WRC-O1` — 탐색(post4·post5)과 판정(post6~)을 «나란히» (🔬 탐색은 판정 분모 밖)\n")
    say("| 통계량 | 🔬 탐색 — 동결 인용(창 `~2026-09-02`) | 🔬 탐색 — **이 스냅샷 재계산**(같은 창) | **판정 — 누적**(post6~10) |")
    say("|---|---|---|---|")
    say(f"| 판정 분모 | 10 | {ne} | **{n_cum}** |")
    say(f"| `WRC-G1` | 6/10 = 60.0% ⇒ 🔴 발동 | {fmt_g1(ne, ae, ze, re_)} {fire(re_)} | "
        f"**{fmt_g1(n_cum, a_cum, z_cum, g1_cum)}** {fire(g1_cum)} |")
    say(f"| `A0` 해 있는 건 | 4(이노테크·한켐p4·지투파워·PS일렉) | {sum(1 for c in explore if c['a0'] == 'feasible')} | "
        f"**{sum(1 for c in cum if c['a0'] == 'feasible')}** ({', '.join(c['name'] for c in cum if c['a0'] == 'feasible') or '—'}) |")
    say("")
    say("- 🔴 판정 열이 `WRC-G1` 로 ⛔ 이면 두 열의 «괴리» 판정은 성립하지 않는다 — 병기만 한다.")
    say("")

    # ═══ §5 D-5 갈래 · F-3 ══════════════════════════════════════════════════
    scan = {}
    for lab in POSTS[2:]:
        for c in judged[lab]:
            scan[id(c)] = corp_event_scan(cur, c["code"], c["reg"], WINDOW_END[lab]) if c["code"] else ([], [], [])
    corp_cases = [c for c in cum if scan[id(c)][0] or scan[id(c)][1]]

    def reentry_flag(c):
        return (PD3_FLAG.get(c["name"], 0) == 1) if c["post"] == "post6" else \
            (c["post"] == "post10" and c["name"] in POST10_REENTRY)

    br = [("주 — 누적 · `exact` · `gross` · 재진입·미완결 포함", cum, "판정"),
          ("`WRC-V1` 축③ 재진입 제외(post6 지투파워 · post10 재진입 4 중 판정 분모 해당)", [c for c in cum if not reentry_flag(c)], "민감도"),
          ("`WRC-V1` 축③ 미완결(`open_ended = 1`) 제외", [c for c in cum if not c["open_ended"]], "민감도"),
          ("「post8 우리로 제외」 누적 줄(확인 7 · `WRC-R5`)", [c for c in cum if not (c["post"] == "post8" and c["name"] == "우리로")], "민감도"),
          ("「샌즈 제외」(🔒 #1 ⓐ · `WRC-R5` 구조차단 — 갈리면 ⛔ `WRC-V1`)", [c for c in cum if c["name"] != SANDS], "민감도")]
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
            "**항등**(주 갈래와 같은 표본)" if sorted((c["post"], c["name"]) for c in sub) == sorted((c["post"], c["name"]) for c in cum)
            else "빠진 건: " + ", ".join(sorted({f"{c['post']} {c['name']}" for c in cum} - {f"{c['post']} {c['name']}" for c in sub})))
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
    n_ap_incl = n_cum + len(ap_br)
    say(f"| `WRC-V1` `approx` 갈래(`D-3` (나)4 검사용 · `P10-approx누적범위` 미발효) | 민감도 | **{n_ap_incl}** | 충족 | — | "
        f"**항등**(이번 글 `approx` {len(ap_all)}) | 갈래 없음 — `exact` 분모 = `approx` 포함 분모(PD-21 · PD-23) |")
    cx = [c for c in cum if c not in corp_cases]
    n, a, z, r = g1_of(cx)
    say(f"| 「기업행위 건 제외」(`P10-기업행위봉` (나) · `F-3`) | 인쇄(참고) | **{n}** | {'충족' if n >= 3 else '🔴 미달'} | "
        f"{fmt_g1(n, a, z, r)} | **답(참고) · 세지 않는다** | " +
        ("**항등**(기업행위 건 0 — 주 갈래와 같은 표본)" if not corp_cases else
         "빠진 건: " + ", ".join(f"{c['post']} {c['name']}" for c in corp_cases)) + " |")
    say(f"| post10 «단독»(참고 · 갈래 아님 · `D-4` 단독 열) | 기록 | **{n_solo}** | — | — | **—** | 단독은 판정 분모가 «아니다» |")
    say("")
    uniq = sorted(set(answers))
    say(f"- **최소 n(3)을 채운 갈래의 답**(「기업행위 건 제외」 «제외» — 세지 않는다): {', '.join(uniq)} ⇒ "
        + ("🟢 **갈리지 않는다**(전 갈래 같은 답) — `WRC-V1` 은 이 회차가 더한 갈림이 없다"
           if len(uniq) == 1 else "🔴 **갈린다 ⇒ ⛔ `WRC-V1`**(선언 금지)"))
    n_re_p10 = sum(1 for c in judged["post10"] if c["name"] in POST10_REENTRY)
    say(f"- 재진입 제외: post10 재진입 4(범한·서산·한켐·우리로) 중 판정 분모 해당 **{n_re_p10}**건 · 「샌즈 제외」: 샌즈는 판정 분모에 "
        f"{'**있다**' if any(c['name'] == SANDS for c in cum) else '없다(항등)'}.")
    say("")
    say("### 5-1. 🆕 `P10-기업행위봉`(`PREREG_POST10.md` §3 (나) · `F-3`) — 창 = 그 축 동결 창(`[등록일, 글별 창 종료]`)\n")
    k = len(corp_cases)
    reasons = []
    for c in corp_cases:
        sp, v0, _ev = scan[id(c)]
        reasons += [f"{c['post']} {c['name']} ⓐ {d}" for d, _t, _nm in sp]
        reasons += [f"{c['post']} {c['name']} ⓑ {d}" for d in v0]
    say(f"*「`P10-기업행위봉`: 기업행위 건 {k}/{n_cum} — {' · '.join(reasons) if reasons else 'ⓐ 0 · ⓑ 0(건별 사유 없음)'} · "
        "`adj_factor` 산술 0 · 처리 = (나)」*")
    say("")
    n_a = sum(1 for c in cum if scan[id(c)][0])
    n_b = sum(1 for c in cum if scan[id(c)][1])
    say(f"- ⓐ(`corp_events` `event_type='split'` · 창 안) **{n_a}/{n_cum}** · ⓑ(`daily_prices.volume = 0` 봉 · 창 안 · 레인 집계 · 착수 뒤) "
        f"**{n_b}/{n_cum}** · 건 단위(정의 A) 합집합 **{k}/{n_cum}** · ⓒ(dart 거래정지 제목)는 신고 줄 밖(정의 아님 · 이 레인 미조회).")
    say("- 창 안 `corp_events` 전 행(기록 줄 · 분류 효과 0):")
    any_ev = False
    for lab in POSTS[2:]:
        for c in judged[lab]:
            for d, t, nm in scan[id(c)][2]:
                any_ev = True
                say(f"  - {lab} {c['name']} `{c['code']}` {d} `{t}` *「{nm}」*")
    if not any_ev:
        say("  - 없음.")
    say(f"- 「기업행위 건 제외」 갈래 `(이름, n, 답)` = `(기업행위 건 제외, {len(cx)}, 답(참고) · 세지 않는다)` — "
        "(나) 문언대로 계수에 «센다»로 들어가지 않았다(§5 표 · 위 `uniq` 에서 제외).")
    say("")

    # ═══ §6 D-3 · P9-공통독법 · D-8 · P9-결측분리 · 커버리지 ════════════════
    ap_opens = [] if n_cum >= 3 else (["`WRC-`"] if n_ap_incl >= 3 else [])
    say("## §6. `D-3` 신고 줄 · `P9-공통독법` · `D-8` · 🆕 `P9-결측분리` · 커버리지(PD-11)\n")
    say(f"**`P8-approx의존신고`**: *「`approx` 포함 시 최소 n 이 차는 축: {', '.join(ap_opens) or '없음'}」* — `exact` 분모 "
        f"**{n_cum}**(누적 · 단독 {n_solo}) / `approx` 포함 분모 **{n_ap_incl}**(구성 예고 = 「없음」 PD-21).")
    say("")
    for ln in p9_common_lines(n_cum, n_ap_incl):
        say(ln)
    say("")
    lv_rows = Counter(r["prog_ver"] for r in tr if r["prog_ver"])
    lv_posts: dict = {}
    for r in tr:
        if r["prog_ver"]:
            lv_posts.setdefault(r["prog_ver"], set()).add(r["post_log_no"])
    say("**`P8-결측수준` 수준 목록**(버전 적힌 행만 · 행·글 두 단위 · 이 축은 `prog_ver` 를 공변량으로 «기록»만 한다):\n")
    say("| 수준 | 행(건) · **SSOT** | 글(민감도) |")
    say("|---|---|---|")
    for lv in sorted(lv_rows):
        say(f"| `{lv}` | {lv_rows[lv]} | {len(lv_posts[lv])} |")
    say("")
    for ln in p10_level_lines(tr):
        say(ln)
    say("")
    say("🔴 **커버리지는 축별로 «다른 수»다**(PD-11 · 이 레인 재측 = `WRC-` 행만) · "
        f"`exact` 신규 분모 = **{len(ex_all)}**.\n")
    say("| 축 | 필요 자료 | 측정 가능 | 측정 불가 | 문턱 1/3 |")
    say("|---|---|---|---|---|")
    say(f"| **`WRC-`(`WRC-G1`)** | `fill_n >= 2` ∧ 서로 다른 값 레그 >= 3 | **{n_solo}/{len(ex_all)}**(post10 단독) | — | "
        f"🔴 판정 = **누적** {fmt_g1(n_cum, a_cum, z_cum, g1_cum)} {ans_of(g1_cum)}(최소 n 미달 «아님») |")
    say("")

    # ═══ §7 D-9 혼합 빈티지 ════════════════════════════════════════════════
    def cross(code, s, e):
        cur.execute("SELECT count(*) FILTER (WHERE date < %s), count(*) FILTER (WHERE date >= %s) "
                    "FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s", (BOUNDARY, BOUNDARY, code, s, e))
        nb, na = cur.fetchone()
        return int(nb), int(na)

    def cross_windows():
        out = []
        for c in p10:
            if c["prec"] != "exact" or not c["reg"]:
                continue
            d = c["reg"]
            cur.execute("SELECT date FROM daily_prices WHERE stock_code=%s AND date >= %s ORDER BY date LIMIT 5", (c["code"], d))
            d5 = [str(x[0]) for x in cur.fetchall()]
            cur.execute("SELECT date FROM daily_prices WHERE stock_code=%s AND date <= %s ORDER BY date DESC LIMIT 20", (c["code"], d))
            d20 = [str(x[0]) for x in cur.fetchall()]
            out.append(("`REC-` `[D, END]`", c["name"], c["code"], d, DB_UPTO))
            out.append(("`LAD-` 창5 `[D, D+4]`", c["name"], c["code"], d, min(d5[-1], DB_UPTO)))
            out.append(("`REG-`/`REC-` `[D−19, D]`", c["name"], c["code"], d20[-1], d))
        return out

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
    say(f"- ⇒ 이 축이 읽는 창 중 경계 걸침 **{own}줄**(post10 판정 분모 3건은 등록일이 09-14 이후라 `reg < 경계` 가 아니다).")
    say("")
    say("### 7-2. PD-27 (바) 표의 창 전부 — 공통 인쇄 의무 (🔴 `REC-`·`LAD-`·`REG-` 창 · 이 축이 읽지 않는다)\n")
    cnt = Counter()
    for axis, nm, code, s, e in cross_windows():
        nb, na = cross(code, s, e)
        if nb and na:
            cnt[axis, "걸침"] += 1
            say(f"- *「창 `[{s}, {e}]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `{nb}` 봉 / 후 `{na}` 봉 · 혼합 빈티지」*"
                f"({axis} · {nm})")
        elif na:
            cnt[axis, "후"] += 1
            say(f"- 🟡 *「창 `[{s}, {e}]` 은 전부 제도 경계 후(전 0 / 후 {na})」*({axis} · {nm} · PD-27 (바) 추가 인쇄 · 재량 · 판정 효과 0)")
        else:
            cnt[axis, "전"] += 1
            say(f"- 🟡 *「창 `[{s}, {e}]` 은 전부 제도 경계 전(전 {nb} / 후 0)」*({axis} · {nm} · 추가 인쇄 · 재량 · 판정 효과 0)")
    say("- 의무 문장 집계(예고 = `[D, END]` 1 · 창5 1 · `[D−19, D]` 8): "
        + " · ".join(f"{ax} 걸침 {cnt[ax, '걸침']}" for ax in ("`REC-` `[D, END]`", "`LAD-` 창5 `[D, D+4]`", "`REG-`/`REC-` `[D−19, D]`")))
    say("")
    say("### 7-3. 한계 절 문장(`P-4`·`P-5` 가 정한 것 · 정의 불변)\n")
    say("- ① `ovtm_vol` 채널은 09-14~09-21 에 전부 0 이고 `overtime_daily` 는 09-22 이후 행이 없다(PD-27 (바)) ⇒ 시간외분을 "
        "`H`·`L` 에서 뺄 수 없다.")
    say("- ② 15:30 마감 분봉 갈래(`P-5`)는 열지 않는다 ⇒ **「정규장만」 갈래는 열지 않는다**(`PREREG_POST8.md` §9 (나) 4).")
    say("- ③ `P-3` 은 이 DB 에서 **판별력 0** — 「통과」로 인용하지 않는다(PD-27 (라)).")
    say("")

    # ═══ §8 P9-수집증거 · 한계 ══════════════════════════════════════════════
    say("## §8. `P9-수집증거` · 한계\n")
    for ln in p10_collect_lines("FREEZE_WRC_2026-09-02.md", "WRC"):
        say(ln)
    say("")
    say("- 🔴 **단독 분모는 우리 가설의 증거가 아니다** — 구성(체결 차수 · 레그 동률)으로 정해지며 저자가 그렇게 끝낸 이유를 모른다.")
    say("- 🔴 누적 분모의 post6~post9 5건은 경계 «전» 창이고 post10 3건은 경계 걸침 «이후 등록»이다(`PREREG_POST8.md` §14 두 제도 혼합).")
    say("- 🔴 `adj_factor` 를 곱하지도 나누지도 않는다 · DB 는 SELECT 만 · 원장은 읽기만.")
    conn.close()

    gate = dict(
        window_end=WINDOW_END, db_upto=DB_UPTO,
        cases=[dict(post=c["post"], name=c["name"], code=c["code"], reg=c["reg"], fill_n=c["fill_n"],
                    distinct=c["distinct"], open_ended=c["open_ended"], a0_gross=c["a0"], a0_net=c["a0_net"],
                    nbar_window=c["nbar"]) for lab in POSTS for c in judged[lab]],
        cumulative=dict(n=n_cum, db_absent=a_cum, empty=z_cum, g1=g1_cum, fire=g1_fire),
        one_post=dict(n=n_one, db_absent=a_one, empty=z_one, g1=g1_one),
        solo_post10=n_solo,
        corp_actions=dict(k=k, n=n_cum, a=n_a, b=n_b),
    )
    (ART / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (BASE / "RESULTS_WRC_POST10_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    note(f"[written] RESULTS_WRC_POST10_NUMBERS.md · wrc_post10/gate.json · 런타임 {time.time() - t0:.3f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
