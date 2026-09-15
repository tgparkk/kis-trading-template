# -*- coding: utf-8 -*-
"""`WRC-` 축 **판정** 실행 — 7번째 글 · 🔴🔴 **주 분모가 «구성»으로 0 ⇒ ⛔ 최소 n 미달**.

`run_wrc_post6.py` 를 **승계**한다. 분모 정의·문턱·시드는 **한 글자도 바꾸지 않고**
`run_wrc_explore.py` 에서 **import 해서** 쓴다(`WRC-R6` §5-1 · `WRC-X1` 4번
*「표·문턱·솔버를 복사해 다시 쓰지 않는다」*).

🔴🔴 **파일 선택의 근거 (INTAKE §5 7행의 문언과 «다른» 쪽을 고른 자리 — 명시한다)**

`INTAKE_2026-09-15_post7.md` §5 7행은 스크립트 칸에 *「`run_wrc_explore.py` → **post7 판정 모드**」*
라고 적었다. 그러나 **post6 전례가 그 자리를 이미 정해 두었다**:

  · `regen_gate.py` `PAIRS` — `"RESULTS_WRC_EXPLORE.md": "run_wrc_explore.py"`(**탐색** · 인자 없음)
    ↔ `"RESULTS_WRC_POST6_NUMBERS.md": "run_wrc_post6.py"`(**판정** · **별도 파일** · 인자 없음).
  · `run_wrc_explore.py` 에는 **argparse 가 아예 없다** — 「모드」를 받을 자리가 없다.
  · 그 산출물 `RESULTS_WRC_EXPLORE.md` 는 `FROZEN_STALE` 이고 사유가
    *「동결(FREEZE_WRC_2026-09-02) … 🔴 **재측정 금지**(탐색값이 post6 판정 문턱의 근거)」* 다.

⇒ **post7 판정은 새 파일 `run_wrc_post7.py` 가 한다. `run_wrc_explore.py` 는 «한 글자도» 바꾸지 않는다.**
🔑 ***동결본에 모드를 더하면, 그 파일의 sha 가 움직여 「동결 산출물이 낡았다」가 매번 뜬다.***
   (post6 이 `run_ranking.py`·`run_sector.py` 에서 겪은 자리이고, 그래서 `FROZEN_STALE` 에
   *「+ run_ranking.py 에 post6 모드를 더했다」* 라는 사유 줄이 따로 붙었다.)

사전등록·동결(값을 보기 «전»에 고정):
  · `PREREG_WEIGHTED_RECON.md` §4 예측표(`WRC-P1`·`N1`·`N2`·`G1`·`O1`·`V1`) ·
    §5-2 `WRC-R7` 실행 환경·창(🔴 **:678-680** — *「발행일이 토·일이면 창은 직전 거래일에서 끝난다」*
    = B-1 승계) · §6-1 `WRC-R11` 판정 분모 · §9 한계
  · `FREEZE_WRC_2026-09-02.md` — 주 모델 `WRC-A1` · 시드 `20260815` · 20,000회 · 밴드 3%p ·
    `G1` 1/3 · `N` 50%
  · `PREDECISION_2026-09-15_post7.md` PD-1(창 종료 **2026-09-11**) · PD-4(정밀도) ·
    PD-11 3번(축별 커버리지) · PD-13(체결 차수)
  · `INTAKE_2026-09-15_post7.md` §1(종목·코드·차수·레그) · §2-19 · §5 7행

🔴🔴 **주 분모가 구조적으로 «0» 이다.** `WRC` 판정 조건(`exact` ∧ `fill_n >= 2` ∧
   서로 «다른» 값 레그 >= 3)에 대해 `exact` **6**건 중 **5건이 1차 체결**(`fill_n = 1`)이고,
   남은 해치텍(`fill_n = 4`)은 **서로 다른 값 레그가 2 < 3** 이다 ⇒ **⛔ 최소 n 미달**.
   🔑 ***값을 보고 닫은 것이 아니라 «구성»으로 닫혔다*** — 저자의 체결 차수 분포(§2-12: 1차 **6건**)가
   닫은 것이고, 우리가 고른 것이 아니다.

🔴 창 = **2026-09-11**(PD-1 1·2번). `PREREG_WEIGHTED_RECON.md` §5-2 :679-680 이 B-1 을 승계하므로
   `WRC-` 레인도 다른 축과 **같은 창**이다. 🔴 초판이 적었던 *「09-15 병기 · 갈리면 「창 정의 의존」
   ⇒ 선언 금지」* 는 **삭제됐다** — 없는 충돌에 붙인 **새 민감도**였다(PD-1 2번).
   남는 것은 **표기 의무 하나**: 실행 시 `max(date)` 와 그 날짜 행수를 산출물에 **기록**(창으로 쓰지 않는다).

🔴 라이브 트리 import 0건 · DB 는 **SELECT 만** · `adj_factor` 산술 0건 · 원장은 «읽기»만 ·
   새 예측 0개 · 새 문턱 0개.
🔴 **라이브 채택 금지**(`PREREG.md` §0-2).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import psycopg2

from run_tests import DSN
# 🔴 분모 규칙·문턱·시드는 **동결본에서 import 한다**(복사 금지 · `WRC-X1` 4번).
#    `run_wrc_explore.py` 는 이 import 로 «읽히기만» 하고 수정되지 않는다.
from run_wrc_explore import (
    BAND_THR,      # 3.0 %p
    G1_THR,        # 1/3
    NREP,          # 20,000
    N_THR,         # 0.50
    SEED,          # 20260815
    THR,           # (0.020, 0.022)
    build_cases,   # §6-1 게이트 «그 자체» — 조건을 이 파일에서 다시 적지 않는다
    read_ledger,
)

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

POST_LOG = "224409404744"        # INTAKE_2026-09-15_post7.md 머리말
POST_DATE = "2026-09-12"         # 발행일(토) — 휴장
END = "2026-09-11"               # PD-1 · 창 종료 = 마지막 거래일(B-1)
LABEL = "post7"

# ── 7번째 글 종목코드 — `INTAKE_2026-09-15_post7.md` §1 표 «그대로» (13/13 해결 · PD-11) ──────
#    🔴 원장(`ledger_trades.csv`)에는 종목코드 컬럼이 «없다» ⇒ 이름→코드는 인테이크가 유일 출처다.
CODES7 = {
    "한전기술": "052690", "한전산업": "130660", "한라캐스트": "125490",
    "지투파워": "388050", "아난티": "025980", "우리기술투자": "041190",
    "서산": "079650", "강동씨엔앨": "198440", "로보티즈": "108490",
    "해치텍": "0155E0", "빛과전자": "069540", "한국화장품제조": "003350",
    "범한퓨얼셀": "382900",
}

# ── `INTAKE_2026-09-15_post7.md` §1 표 — 원장이 아직 append 되기 «전»에도 돌 수 있게 박아 둔다 ──
#    🔴 이건 «예측»이다. 원장이 들어오면 `main()` 이 원장으로 **다시 재고**(build_cases) 두 수가
#    같은지 대조한다. 다르면 **원장이 이긴다**(원장 = SSOT) — 그 사실을 인쇄한다.
#    (종목, 정밀도, fill_n, 레그)
INTAKE_ROWS = [
    ("한전기술",       "none",   4, [13.61, 10.80, 7.37, 4.91, 3.34, -1.70]),
    ("한전산업",       "none",   5, [15.55, 14.88, 12.70, 8.97, 5.78, -1.32]),
    ("한라캐스트",     "none",   5, [11.22, 3.50, 3.43, 3.30, 2.04, -5.30]),   # 후속
    ("지투파워",       "approx", 3, [20.11, 18.58, 17.50, 15.08, 12.72]),
    ("아난티",         "none",   1, [1.91]),                                    # 후속
    ("우리기술투자",   "none",   4, [3.28, 3.25, 3.08]),                        # 후속
    ("서산",           "exact",  1, [22.16, 16.09, 10.02]),
    ("강동씨엔앨",     "exact",  1, [24.28, 18.33, 18.31, 12.61]),
    ("로보티즈",       "exact",  1, [9.13]),
    ("해치텍",         "exact",  4, [4.06, 0.46]),
    ("빛과전자",       "exact",  1, [12.17]),
    ("한국화장품제조", "approx", 1, [22.70, 16.81, 10.85]),
    ("범한퓨얼셀",     "exact",  1, [18.89, 16.69, 14.55, 12.22, 10.8, 7.94]),
]

# 🔴 PD-11 3번 — 커버리지는 **축별로 «다른 수»다**. 한 수로 합치지 않는다(`exact` 분모 6 기준).
COVERAGE = [
    ("`SEL-`·`Q1-`·`REG-`·`RNK-`·`ANC-`·`LAD-`·`REC-`", "`daily_prices`", "6/6", "0", "0%", "미발동"),
    ("`SEC-`(`SEC-G1`)", "`stock_industry` 섹터코드", "5/6", "1(해치텍)", "16.7%", "미발동"),
    ("`S5`", "`dart_financials_asfiled` PIT", "5/6", "1(해치텍 — 재무 표 미수록)", "16.7%",
     "(판정 안 함 · PD-15)"),
    ("**`WRC-`(`WRC-G1`)**", "`fill_n >= 2` ∧ 서로 다른 값 레그 >= 3", "**0/6**", "—", "—",
     "🔴 **최소 n 미달로 ⛔**"),
]


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


def intake_cases():
    """`INTAKE_ROWS` 를 **원장과 같은 모양**으로 만들어 `build_cases` 에 그대로 먹인다.

    🔑 ***게이트 조건을 이 파일에서 다시 적지 않는다*** — 동결본 `build_cases` 가 그대로 판단한다
    (`WRC-X1` 4번 *「표·문턱·솔버를 복사해 다시 쓰지 않는다」*). 원장이 아직 append 되기 «전»에도
    이 경로로 구성 사실을 확인할 수 있다."""
    tr, legs = [], {}
    for i, (nm, prec, fill_n, ret) in enumerate(INTAKE_ROWS, start=1):
        item = str(i)
        tr.append(dict(post_log_no=POST_LOG, post_date=POST_DATE, prog_ver="",
                       item_no=item, stock_name=nm, n_legs=str(len(ret)), open_ended="0",
                       all_loss="0", reg_date="", reg_date_precision=prec,
                       fill_level="", fill_n=str(fill_n), preset="", narrative=""))
        legs[(POST_LOG, item)] = list(ret)
    cases = build_cases(tr, legs)
    for c in cases:
        c["code"] = CODES7.get(c["name"])      # CODEMAP 은 post4·5 이름만 안다 — 덮어쓴다
    return cases


def ledger_cases():
    """원장(`ledger_trades.csv`·`ledger_legs.csv`)에서 post7 행을 **다시 재서** 돌려준다.

    🔴 §1 표를 «복사하지 않는다» — post6 판이 `build_cases` 로 재측정한 것과 같은 경로다.
    원장에 post7 행이 아직 없으면 **빈 리스트**를 돌려준다(판단은 `main()` 이 한다)."""
    tr, legs = read_ledger()
    cases = [c for c in build_cases(tr, legs) if c["log_no"] == POST_LOG]
    for c in cases:
        c["code"] = CODES7.get(c["name"])
    return cases


def denom(cases):
    """§6-1 판정 분모 = `gate` 가 참인 건(동결 규칙 그대로)."""
    return [c for c in cases if c["gate"]]


def approx_branch(cases):
    """🔴 **민감도 갈래** — §6-1 의 세 조건 중 **정밀도 조건만** `approx` 로 바꾼 갈래.

    🔑 ***이건 게이트의 재정의가 «아니다»*** — `build_cases` 의 `gate` 는 `exact` 를 «하드»로 물고
    있어서 `approx` 건은 나머지 두 조건을 만족해도 `gate = False` 가 된다. 그 두 조건
    (`fill_n >= 2` ∧ 서로 다른 값 레그 >= 3)만 그대로 적용한 «갈래»를 따로 세어
    **민감도 줄에만** 인쇄한다(`RNK-D5`·`S5` §1-1·`ANC` §2-3 이 지시한 「의무 민감도」 자리).
    🔴 이 수로 **판정하지 않는다**(1 < 3 이라 열리지도 않는다)."""
    return [c for c in cases
            if c["prec"] == "approx" and c["fill_n"] and c["fill_n"] >= 2 and c["distinct"] >= 3]


def split_reasons(cases, prec):
    """정밀도 갈래 안에서 **탈락 사유별** 분해 — 「왜 0인가」를 값이 아니라 구성으로 보인다."""
    sub = [c for c in cases if c["prec"] == prec]
    first_only = [c for c in sub if c["fill_n"] == 1]
    few = [c for c in sub if c["fill_n"] and c["fill_n"] >= 2 and c["distinct"] < 3]
    passed = [c for c in sub if c["gate"]]
    return sub, first_only, few, passed


# 🔒 post6 «판정 회차»의 동결 인용값 — `RESULTS_WRC_POST6_NUMBERS.md` §1·§2 에서
#    **옮겨 적은 상수**이며 **재계산이 아니다**(동결 산출물 byte 불변).
#    🔴 `WRC-R11`(§6-1)의 «누적 규약»이 이 값을 요구한다:
#    *「누적 3건이 되는 즉시 한 번 판정한다」* + *「이후 글에서는 **누적 전체로 다시 계산**한다
#    (같은 검정의 갱신)」*(`PREREG_RANKING.md` §2-6 승계 — §6-1 이 명시적으로 그쪽을 승계한다).
P6_WRC = {"denom": 5, "g1_num_db_absent": 0, "g1_num_empty": 4, "g1_rate": 4 / 5,
          "src": "RESULTS_WRC_POST6_NUMBERS.md §1·§2"}


def main() -> int:
    t0 = time.time()
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    cur.execute("SELECT max(date) FROM daily_prices")
    max_date = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (max_date,))
    max_rows = int(cur.fetchone()[0])
    cur.close()
    conn.close()

    say("# RESULTS_WRC_POST7_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_wrc_post7.py` · 승계 `run_wrc_post6.py` · 재사용(=import) "
        "`run_wrc_explore.py`(`build_cases`·`read_ledger`·문턱 `SEED`·`NREP`·`THR`·"
        "`BAND_THR`·`G1_THR`·`N_THR`)")
    say("사전등록 `PREREG_WEIGHTED_RECON.md` §4·§5-2·§6-1 · 동결 `FREEZE_WRC_2026-09-02.md` · "
        "인테이크 [`INTAKE_2026-09-15_post7.md`](INTAKE_2026-09-15_post7.md) §1·§5 · "
        "결정 [`PREDECISION_2026-09-15_post7.md`](PREDECISION_2026-09-15_post7.md) PD-1·PD-4·PD-11\n")

    # ── §0. 실행 환경 · 동결 규약 ───────────────────────────────────────────
    say("## §0. 실행 환경 · 동결 규약\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 대상 | 7번째 글 `logNo={POST_LOG}` (발행 **{POST_DATE}** 토 · 휴장) |")
    say("| 🔴 창 종료 | **창 종료 2026-09-11 = 발행일(2026-09-12 토) 휴장 ⇒ 마지막 거래일 · "
        "B-1(`WRC-` 포함 전 축)** |")
    say(f"| 🔴 실행 시 `max(date)` | **{max_date}** · 그 날짜 행수 **{max_rows:,}** — "
        "🔴 **기록만 한다 · 창으로 쓰지 않는다**(PD-1 2번 · `WRC-D7` 표기 의무) |")
    say(f"| 판정 분모 정의 | `exact` ∧ `fill_n >= 2` ∧ **서로 «다른» 값 레그 >= 3** "
        "(§6-1 `WRC-R11` · 동결본 `build_cases` 를 **import 해서** 판단한다) |")
    say(f"| 시드 · 반복 | **{SEED}** · **{NREP:,}회** (동결값 그대로 · import) |")
    say(f"| 문턱 | 밴드 **{BAND_THR}%p** · `G1` **{G1_THR:.4f}**(1/3) · `N` **{N_THR:.2f}** · "
        f"잔차 `THR` **{THR}** (전부 import · 이 파일에서 만들지 않았다) |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다** (`PREREG.md` §0-2) |")
    say("")
    say("🔴 **초판의 「09-15 병기 · 갈리면 「창 정의 의존」 ⇒ 선언 금지」는 삭제됐다**(PD-1 2번) — "
        "`PREREG_WEIGHTED_RECON.md` §5-2 **:679-680** 이 `WRC-D7` **바로 다음 줄**에 "
        "*「발행일이 토·일이면 창은 직전 거래일에서 끝난다」*(B-1 승계)를 이미 못박아 두었으므로 "
        "**충돌이 없었다.** ***없는 충돌에 민감도를 붙이면 그것이 신설 규칙이다.***")
    say("🔴 **`run_wrc_explore.py` 를 «한 글자도» 바꾸지 않았다** — 그 파일의 산출물 "
        "`RESULTS_WRC_EXPLORE.md` 는 `FROZEN_STALE`(*「🔴 재측정 금지」*)이고 argparse 가 없다. "
        "post6 전례대로 **판정은 별도 파일**이 한다(`run_wrc_post6.py` → `run_wrc_post7.py`).")
    say("")

    # ── §1. 표본 구성 (원장 재측정 ↔ 인테이크 예측 대조) ────────────────────
    ic = intake_cases()
    lc = ledger_cases()
    say("## §1. 표본 — 원장 재측정 ↔ 인테이크 «계산 전» 구성 대조\n")
    if lc:
        say(f"- 원장 `post_log_no = {POST_LOG}` 행 **{len(lc)}건** 재측정 완료.")
        ic_key = sorted((c["name"], c["prec"], c["fill_n"], c["distinct"]) for c in ic)
        lc_key = sorted((c["name"], c["prec"], c["fill_n"], c["distinct"]) for c in lc)
        if ic_key == lc_key:
            say("- 🟢 **원장 ↔ 인테이크 §1 표가 전건 일치**(이름·정밀도·`fill_n`·서로 다른 값 레그 수).")
        else:
            say("- 🔴🔴 **원장 ↔ 인테이크 §1 표가 갈린다.** ***원장이 SSOT 다*** — 아래 판정은 "
                "**원장 기준**으로 서며, 갈린 자리를 그대로 인쇄한다:")
            for a, b in zip(ic_key, lc_key):
                if a != b:
                    say(f"  - 인테이크 `{a}` ↔ 원장 `{b}`")
        cases = lc
        src = "원장(`ledger_trades.csv`·`ledger_legs.csv`) 재측정"
    else:
        say(f"- 🔴 **원장에 post7(`{POST_LOG}`) 행이 아직 없다** — 원장 append 가 먼저다"
            "(`run_ranking.py` post6 전례 문형). ⇒ 이 실행은 **인테이크 §1 표(계산 «전» 동결)**로 "
            "구성 사실만 인쇄하고, 원장이 들어온 «뒤» 다시 돌려 대조해야 한다.")
        cases = ic
        src = "인테이크 `INTAKE_2026-09-15_post7.md` §1 표(원장 미도착)"
    say(f"- 표본 출처 = **{src}** · 총 **{len(cases)}건**(신규 10 + 후속 3).")
    say("")
    say("| 종목 | 코드 | 정밀도 | `fill_n` | 레그 수 | **서로 «다른» 값 레그** | 게이트 |")
    say("|---|---|---|---|---|---|---|")
    for c in cases:
        say(f"| {c['name']} | `{c['code']}` | {c['prec']} | {c['fill_n']} | {c['n_legs']} | "
            f"**{c['distinct']}** | {'🟢 통과' if c['gate'] else '탈락'} |")
    say("")

    # ── §2. 주 분모 — 구성상 0 ──────────────────────────────────────────────
    ex_all, ex_first, ex_few, ex_pass = split_reasons(cases, "exact")
    ap_all, ap_first, ap_few, _ap_gate = split_reasons(cases, "approx")
    ap_branch = approx_branch(cases)
    say("## §2. 판정 분모 — 🔴🔴 **0건 · «구성»으로 닫혔다**\n")
    say("| 갈래 | 건 | 1차 체결(`fill_n = 1`) | `fill_n >= 2` ∧ 다른 값 레그 < 3 | **나머지 두 조건 통과** |")
    say("|---|---|---|---|---|")
    say(f"| **`exact`(주 분모)** | {len(ex_all)} | **{len(ex_first)}** "
        f"({', '.join(c['name'] for c in ex_first) or '—'}) | **{len(ex_few)}** "
        f"({', '.join(c['name'] for c in ex_few) or '—'}) | 🔴 **{len(ex_pass)}** |")
    say(f"| `approx`(민감도 갈래) | {len(ap_all)} | {len(ap_first)} "
        f"({', '.join(c['name'] for c in ap_first) or '—'}) | {len(ap_few)} "
        f"({', '.join(c['name'] for c in ap_few) or '—'}) | {len(ap_branch)} "
        f"({', '.join(c['name'] for c in ap_branch) or '—'}) |")
    say("")
    say("- 🔴 **`approx` 줄의 마지막 칸은 「게이트 통과」가 «아니다».** 동결 게이트는 정밀도 `exact` 를 "
        "**하드로** 물고 있어 `approx` 건은 나머지 두 조건을 만족해도 통과하지 않는다. "
        "그 두 조건만 적용한 **민감도 갈래**를 따로 센 수이고, **판정에 쓰지 않는다**"
        "(`approx_branch()` · 게이트를 재정의한 것이 아니다).")
    n_main = len(denom([c for c in cases if c["prec"] == "exact"]))
    say(f"- 🔴🔴 **주 분모 = {n_main}건 ⇒ ⛔ 최소 n 미달.**")
    say("- 🔑 **값을 보고 닫은 것이 아니라 «구성»으로 닫혔다** — `exact` 6건 중 **5건이 1차 체결**"
        "(`fill_n = 1`)이고 남은 **해치텍**(`fill_n = 4`)은 **서로 다른 값 레그가 2 < 3**"
        "(레그 `[4.06, 0.46]`)이다. ***저자의 체결 차수 분포(§2-12: 1차 6건)가 닫은 것이고, "
        "우리가 고른 것이 아니다.***")
    say(f"- 🔴 **`approx` 민감도 갈래 {len(ap_branch)}건**"
        f"({', '.join(c['name'] for c in ap_branch) or '—'})은 **민감도로만** 인쇄한다 — "
        "`RNK-D5`·`S5` §1-1·`ANC` §2-3 세 동결본이 *「판정 분모 = `exact` 만」* 을 지시한다"
        "(PD-4 1번). 🔴 이 1건으로 축을 «열지» 않는다(1 < 3 이라 열리지도 않는다).")
    say("")

    # ── §3. 예측별 판정 — §6-1 «누적 규약» 적용 ─────────────────────────────
    # 🔴🔴 **분모는 post7 «단독»이 아니라 «누적»이다.**
    #    `WRC-R11`(`PREREG_WEIGHTED_RECON.md:748-753`)이 두 문장을 «둘 다» 못박는다:
    #      ① *「누적 3건이 되는 즉시 한 번 판정한다」*(`P6-L-누적` 승계)
    #      ② *「이후 글에서는 **누적 전체로 다시 계산**한다(같은 검정의 갱신)」*
    #         — §6-1 이 `PREREG_RANKING.md` §2-6 을 **명시적으로 승계**한다고 적었다.
    #    ⇒ post7 단독 0건을 근거로 「최소 n 미달」이라 쓰면 그건 ② 를 안 지킨 것이다.
    #    누적 분모 = post6 5 + post7 0 = 5 ≥ 3 ⇒ **게이트는 «열린다»**.
    #    열린 뒤 «먼저» 걸리는 것이 `WRC-G1` 이다(§4-6 · §7-B #24 — 가장 먼저 계산한다).
    cum_denom = P6_WRC["denom"] + n_main
    cum_g1_num = P6_WRC["g1_num_db_absent"] + P6_WRC["g1_num_empty"]      # post7 기여 0
    cum_g1 = (cum_g1_num / cum_denom) if cum_denom else None
    g1_fire = bool(cum_g1 is not None and cum_g1 >= G1_THR)
    min_n_ok = cum_denom >= 3

    say("## §3. `WRC-P1` · `N1`·`N2` · `G1` · `O1` · `V1` — **전부 ⛔** "
        "(사유 = `WRC-G1` 발동 · 🔴 **「최소 n 미달」이 아니다**)\n")
    say("🔒 **분모는 §6-1 `WRC-R11` 의 «누적 규약»대로 «누적»이다** — "
        f"post6 **{P6_WRC['denom']}** + post7 **{n_main}** = **{cum_denom}** "
        + ("(≥ 3 ⇒ 🟢 **게이트 열림**)" if min_n_ok else "(< 3 ⇒ ⛔ 미룸)")
        + ". 동결 문언 두 줄을 «둘 다» 지킨다: *「누적 3건이 되는 즉시 한 번 판정한다」* + "
          "*「이후 글에서는 **누적 전체로 다시 계산**한다(같은 검정의 갱신)」* "
          "(`PREREG_WEIGHTED_RECON.md` §6-1 — `PREREG_RANKING.md` §2-6 승계). "
        + f"post6 값은 `{P6_WRC['src']}` 에서 **옮겨 적은 상수**이고 **재계산이 아니다**.")
    say("")
    say(f"🔴 **post7 «단독» 분모는 {n_main}건이다 — 병기한다.** "
        "🔴 **그러나 그것으로 「최소 n 미달」을 선언하지 않는다**: 누적 규약이 "
        "***「표본을 모아 «한 번» 검정한다」***이므로 이 글의 0건은 **누적 표본에 0을 더한 것**이지 "
        "**분모를 0으로 만드는 것이 아니다.** "
        "🔑 ***「따로 낸 판정들을 더한다」와 「표본을 모아 한 번 검정한다」는 다른 동작이고, "
        "동결본은 후자다***(§6-1 말미 · `WRC-P2` 누계 인용 금지와 충돌하지 않는 유일한 읽기).")
    say("")
    say("🔴🔴 **그래서 이 회차의 ⛔ 사유는 `WRC-G1` 이다** — 누적 커버리지 "
        f"**{cum_g1_num}/{cum_denom} = {cum_g1 * 100:.1f}%** ≥ 문턱 **{G1_THR:.4f}** ⇒ "
        + ("🔴 **발동**" if g1_fire else "미발동")
        + ". §4-6·§7-B #24 가 *「`WRC-G1` 을 «가장 먼저» 계산한다 · 1/3 이상이면 나머지를 "
          "열지 않는다」*고 적었으므로 **게이트가 열린 뒤 첫 관문에서 닫힌 것**이다. "
          "🔑 ***「못 좁힌다」도 「잴 건이 없었다」도 아니라 「못 쟀다」다*** "
          "(`RESULTS_WRC_POST6_NUMBERS.md` §6 문형 승계 — post6 도 같은 사유로 ⛔ 였다).")
    say("")
    say("| 글 | 판정 분모 | ① DB부재 | ④ 해 0개 | **`WRC-G1`** | 게이트(≥ 1/3) |")
    say("|---|---|---|---|---|---|")
    say(f"| post6 (직전 · **옮겨 적은 값** · 재계산 아님) | {P6_WRC['denom']} | "
        f"{P6_WRC['g1_num_db_absent']} | {P6_WRC['g1_num_empty']} | "
        f"**{cum_g1_num}/{P6_WRC['denom']} = {P6_WRC['g1_rate'] * 100:.1f}%** | 🔴 발동 |")
    say(f"| post7 (단독 · **병기** · 판정 아님) | {n_main} | 0 | 0 | "
        "**—** (비율을 만들 수 없다) | — |")
    say(f"| 🔒 **누적 (§6-1 규약 · 이 회차의 판정 분모)** | **{cum_denom}** | "
        f"{P6_WRC['g1_num_db_absent']} | {P6_WRC['g1_num_empty']} | "
        f"**{cum_g1_num}/{cum_denom} = {cum_g1 * 100:.1f}%** | "
        + ("🔴 **발동**" if g1_fire else "미발동") + " |")
    say("")
    say("| 항목 | 가설(한 줄) | 문턱 | 판정 분모(누적) | **판정** | 대칭/반증 쌍 | ⛔ 경로 |")
    say("|---|---|---|---|---|---|---|")
    g1_path = (f"🔴 **누적 `WRC-G1` {cum_g1 * 100:.1f}% ≥ 1/3 ⇒ 발동**"
               if g1_fire else "미발동")
    rows = [
        ("`WRC-P1`", "가중 평단 복원의 `b_k` 밴드 폭이 3%p 미만",
         f"{BAND_THR}%p (`FREEZE_WRC` §3)", "`WRC-N2`", g1_path),
        ("`WRC-N1`", "(대칭) 판별력 — 대조군이 관측만큼 맞히면 무정보",
         f"{N_THR:.0%} (`RESULTS_D1_OOS_POST5.md` §9 W7 차용)", "`WRC-P1`", g1_path),
        ("`WRC-N2`", "(대칭) 밴드가 3%p 이상이면 `P1` 철회",
         f"{BAND_THR}%p", "`WRC-P1`", g1_path),
        ("`WRC-G1`", "커버리지 손실 — 게이트 탈락 비율",
         f"{G1_THR:.4f} (1/3)", "자신이 반증축",
         f"🔴 **자신이 ⛔ 조건이다** — {cum_g1_num}/{cum_denom} = {cum_g1 * 100:.1f}% ⇒ 발동"),
        ("`WRC-O1`", "훈련(탐색 post4·5) ↔ 검정(post6·7) 병기",
         "(병기 의무 · 문턱 없음)", "자신이 반증축",
         "post7 «단독» 열이 **비어 있다** ⇒ 병기만 하고 비교하지 않는다"),
        ("`WRC-V1`", "(대칭) 갈래를 바꾸면 답이 갈리나",
         "갈리면 **선언 금지**", "자신이 반증축",
         "🔴 **이 글이 더한 갈래가 없다** — post7 `exact` 0 · `approx` 1 "
         "(둘 다 이 글 단독으로는 갈래를 만들지 못한다) ⇒ 누적 갈래는 post6 것 그대로다"),
    ]
    for lbl, hyp, thr, pair, blk in rows:
        say(f"| {lbl} | {hyp} | {thr} | **{cum_denom}** | ⛔ **판정 불가"
            f"(`WRC-G1` 발동)** | {pair} | {blk} |")
    say("")
    say("⇒ **6개 항목 전부 ⛔.** 「불성립」도 「지지」도 «아니다». "
        "🔴🔴 **다만 ⛔ 의 «사유»가 다르다** — *「분모 0 ⇒ 최소 n 미달」*이 **아니라** "
        f"*「누적 분모 {cum_denom} ≥ 3 으로 게이트는 열렸는데 `WRC-G1` "
        f"{cum_g1 * 100:.1f}% 가 먼저 닫았다」*다. "
        "🔑 ***두 사유는 다음 글에서 «열리는 조건»이 다르다*** — 전자는 「건수가 늘면」, "
        "후자는 ***「커버리지가 좋아지면」***이다. **건수만 늘려서는 이 축이 열리지 않는다.**")
    say("")
    say("🔴 **문턱 `1/3` 을 올려 여는 것은 어느 경우에도 금지**(§4-6 · post6 회차 자기신고 승계). "
        "🔴 그리고 `WRC-G1` 발동 시 동결 문언은 *「나머지를 돌리지 않는다」*인데 이 실행은 "
        "post6 전례대로 **계산하되 판정 표기를 ⛔** 로 둔다 — ***아래 값은 전부 «관측»이며 "
        "어떤 지지·불성립도 «선언하지 않는다».***")
    say("")

    # ── §4. `WRC-G1` 60% 발동 위험 (누적 축) ────────────────────────────────
    say("### §4. `WRC-G1` — 탐색 동결값 **60% 발동**의 지위\n")
    say("- `FREEZE_WRC_2026-09-02.md` §4 탐색 동결값: **`G1` = 6/10 = 60.0% ⇒ 🔴 발동**"
        f"(문턱 {G1_THR:.4f}) — **인용이다. 재계산이 아니다.**")
    say(f"- 🔴 **post7 «단독»은 분모가 {n_main}** 이라 `G1` 의 «비율»을 만들 수 없다 — "
        f"누적 분자·분모에 **0 을 더한다**(post6 {cum_g1_num}/{P6_WRC['denom']} "
        f"→ 누적 {cum_g1_num}/{cum_denom} = {cum_g1 * 100:.1f}%). "
        "🔑 ***「비율을 못 만든다」는 「누적에서 «빠진다»」가 아니다*** — §6-1 은 "
        "«누적 전체로 다시 계산»하라고 했고, **0 을 더하는 것**이 그 계산이다. "
        "🔴 (초판의 *「누적 `G1` 에 post7 은 0/0 을 더하지 않는다」* 는 이 규약과 어긋나 "
        "삭제했다 — `TV` 축 0건 처리는 «누적 규약이 없는» 축의 잣대였다.)")
    say("- ⚠️ **그러나 「커버리지 손실이 없다」가 아니다** — 반대로 **전건 손실**이다. "
        "🔑 ***「비율을 못 만든다」와 「손실이 0이다」는 다른 말이다.*** 그래서 위 §2 표를 «건수»로 남긴다.")
    say("")

    # ── §5. 커버리지 — 🔴 축별로 «다른 수» ──────────────────────────────────
    say("## §5. 커버리지 가드 — 🔴 **축별로 «다른 수»다** (PD-11 3번 · 한 수로 합치지 않는다)\n")
    say("`exact` 신규 분모 = **6**.\n")
    say("| 축 | 필요한 자료 | 측정 가능 | 측정 불가 | 비율 | 문턱 1/3 |")
    say("|---|---|---|---|---|---|")
    for r in COVERAGE:
        say("| " + " | ".join(r) + " |")
    say("")
    say("- 🔴 위 네 줄을 **한 수로 합치지 않는다** — 같은 6건이라도 축마다 막히는 자리가 다르다.")
    say("- 🔴 `WRC-` 의 「0/6」은 **자료 결손이 아니라 «구성»** 이다(다른 세 축의 결손 사유와 종류가 다르다): "
        "해치텍은 `daily_prices`·코드 둘 다 있는데 **레그 값이 2개뿐**이라 탈락한다.")
    say("")

    # ── §6. 한계 ────────────────────────────────────────────────────────────
    say("## §6. 한계 (승계)\n")
    say("- 🔴 **분모 0 은 우리 가설의 증거가 아니다.** 저자가 이번 주에 1차 체결 위주로 등록한 이유를 "
        "우리는 모른다(장세 / 프리셋 / 우연 — 가르지 못한다).")
    say("- 🔴 **`WRC-` 는 post6 한 회차만 판정됐다** — post7 이 표본을 못 만났으므로 "
        "***「살아 있다」와 「검증됐다」는 여전히 다르다***(`RESULTS_D1_OOS_POST6_NUMBERS.md` §5 문형).")
    say("- 🔴 **`adj_factor` 를 곱하지도 나누지도 않는다** · DB 는 SELECT 만 · 원장은 읽기만.")
    say("- 🔴 이 분석은 **라이브 채택 대상이 아니다** (`PREREG.md` §0-2).")

    (BASE / "RESULTS_WRC_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    note("")
    note(f"[written] RESULTS_WRC_POST7_NUMBERS.md · 런타임 {time.time() - t0:.3f}s")
    note("🔴 `run_wrc_explore.py` 는 읽기(import)만 했다 — 수정 0줄.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
