# -*- coding: utf-8 -*-
"""`S5` 재무·뉴스 OOS — **7번째 글** · 🔴🔴 **값 인쇄만 · 판정 선언 «없음»**.

사전등록: `PREREG_S5_FUND_NEWS_OOS.md` v0.3(`f3ff8bc` · 2026-09-15 09:47:05 KST · `origin/main`)
        §0(오염 고지) · §1(예측 한 줄 · PIT · 대조군) · §1-1(`reg_date` 정밀도) · §2(판정문) ·
        §3(승계) · §4(실행 기록)
인테이크: `INTAKE_2026-09-15_post7.md` §1·§5 · `PREDECISION_2026-09-15_post7.md` **PD-15**(이 레인의
        규약 전부) · PD-4(정밀도) · PD-11(해치텍 코드 해결 · 축별 커버리지)

🔴🔴 **판정문을 선언하지 않는다**(PD-15 1번). `(S5-성립)`·`(S5-이탈)`·`(S5-보류)` 중 **어느 라벨도**
   이 산출물에 나오지 않는다. 근거는 **동결 «선언»의 부재**다 —
   커밋 `f3ff8bc` 는 fetch(2026-09-15 15:36:49)보다 **앞서지만**, 그 커밋 메시지가
   *「… S5 사전등록 **초안 v0.3** … (C-8 · 27.0% 고지 · **미동결**)」* 이라 **「동결」이라는 선언이 없다.**
   대조: `PREREG_GRADE_TIERS.md` 의 `342f6f0` 은 *「사전등록 **«동결»** — post7 수집 전」* 을 명시했다.
   `PREREG_GRADE_TIERS.md` §0-3 1번이 *「이 문서를 **동결**·커밋한다」* 로 **동결과 커밋을 «같이»**
   요구하므로 **커밋만으로는 동결이 아니다.**
   🔑 ***값을 본 뒤 동결 선언을 붙이면 그 자체가 사후적합이다*** — 그래서 이번엔 인쇄만 한다.

🔴 **꼬리표 `[탐색]`**(`PREREG_GRADE_TIERS.md` §1-3) — 이 산출물의 모든 표에 붙는다.
🔴 **Holm 가족 +0** — 주 검정 수를 늘리지 않는다(§2 *「등록부 주 검정 +0」*).
🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2) — 등급이 무엇이든 라이브 채택 금지는 그대로다.

🔴 **이 스크립트가 만드는 산출물은 `RESULTS_S5_POST7_NUMBERS.md` «하나»다.**
   산문 `RESULTS_S5_POST7.md` 는 **사람이 쓰는 문서**이며 `regen_gate.py` 의 `MANUAL_DOCS` 자리다
   (`RESULTS_WRC_POST6.md` ↔ `RESULTS_WRC_POST6_NUMBERS.md` 의 분리 전례 그대로).
   🔑 ***스크립트가 산문까지 쓰면 `PAIRS`(기계) ↔ `MANUAL_DOCS`(사람)의 구분이 무너진다.***

🔴 라이브 트리 import 0건(표준 라이브러리 + pandas/psycopg2 + 같은 폴더 `run_tests.DSN`·`run_selection`) ·
   DB 는 **SELECT 만** · `adj_factor` 산술 0건 · 난수 0회(결정적) · 새 정의 0개.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2

from run_selection import PSEUDO          # ("KOSPI", "KOSDAQ", "KS11", "KQ11") — 유니버스 제외 축
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

# ── 동결 상수 (전부 인용 · 이 파일에서 고르지 않는다) ─────────────────────────
POST_LOG = "224409404744"       # INTAKE_2026-09-15_post7.md 머리말
POST_DATE = "2026-09-12"        # 글 게시일(토) — PIT 절단면
DB_UPTO = "2026-09-11"          # PD-1 · 창 종료 = 발행일 휴장 ⇒ 마지막 거래일(B-1)
PIT_CUTOFF = POST_DATE          # §1 PIT: `rcept_dt <= 글 게시일`
PIT_STATUS = "000"              # §1 PIT: `status='000'`
TOP_PCT = 99.0                  # §1 대조군: 거래대금/시총 백분위 **상위 1%** ⇒ pct >= 99.0
NEWS_BACK = 4                   # §0 뉴스 창 `[등록일−4, 등록일]` (탐색 인쇄 전용)
SEED = 20260815                 # 계열 고정 시드 — 🔴 이 레인은 난수를 쓰지 않는다(결정적)

# 🔴 판정 라벨 — **이 산출물에 나오면 안 되는 문자열**(PD-15 1번 · 가드가 직접 문다)
FORBIDDEN_LABELS = ("(S5-성립)", "(S5-이탈)", "(S5-보류)")

# ── 표본 (`INTAKE_2026-09-15_post7.md` §1 표 «그대로» · PD-4) ─────────────────
#    🔴 원장(`ledger_trades.csv`)에는 종목코드 컬럼이 «없다» ⇒ 이름→코드는 인테이크가 유일 출처다.
#    (종목, 코드, 등록일)
EXACT6 = [
    ("서산", "079650", "2026-09-03"),
    ("강동씨엔앨", "198440", "2026-09-03"),      # 🔴 DB 표기 「강동씨앤엘」 — PD-10 4번
    ("로보티즈", "108490", "2026-09-04"),
    ("해치텍", "0155E0", "2026-09-07"),           # PD-11 2번 — news 경유로 코드 해결
    ("빛과전자", "069540", "2026-09-08"),
    ("범한퓨얼셀", "382900", "2026-09-09"),
]
# `approx` 2건 — §1-1 *「민감도 인쇄만 · 판정 언어 금지」*. 갈래는 `PREREG_POST6.md` §1-4 창 규약.
#    (종목, 코드, 창 서술, 갈래 거래일 목록 — PD-4 2번 실측)
APPROX2 = [
    ("지투파워", "388050", "「9월 초」 = 09-01~09-10 의 거래일 8일",
     ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
      "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"]),
    ("한국화장품제조", "003350", "「8월 말」 = 08-21~08-31 의 거래일 7일",
     ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
      "2026-08-27", "2026-08-28", "2026-08-31"]),
]
# `none` 2 (한전기술·한전산업) + 후속 3 (한라캐스트·아난티·우리기술투자) = 등록일 축 **밖**(PD-4 3번).
NONE2 = [("한전기술", "052690"), ("한전산업", "130660")]
FOLLOWUP3 = [("한라캐스트", "125490"), ("아난티", "025980"), ("우리기술투자", "041190")]

# 🔴 PD-15 3번 · PD-11 2번 — 재무 표 «미수록» 종목(이름 매칭 실패가 «아니다»)
NO_FIN_CODES = {"0155E0"}

# §0 오염 고지 — `PREREG_S5_FUND_NEWS_OOS.md` §0 의 값을 «옮겨 적은 것»(재계산 아님)
CONTAM = dict(ledger_trades=62, ledger_legs=216, uniq_codes=47, posts=6,
              seen_loss="10/37 = 27.0%", seen_univ="25.1~30.6%",
              seen_news="11/27 = 40.74%", seen_news_base="29.71%",
              name_match="39/47 = 83.0%")
# PD-15 4번 — PIT 한계(존재 사실 · 2026-09-15 실측)
PIT_LIMIT = dict(rows=17892, max_rcept="2026-08-06")


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


def pct(a, b):
    return "—" if not b else f"{100.0 * a / b:.1f}%"


# ══════════════════════════════════════════════════════════════════════════════
# 가드 — 산출물을 쓰기 «전»에 이 스크립트가 스스로 문다
# ══════════════════════════════════════════════════════════════════════════════
def assert_no_verdict(lines):
    """🔴 PD-15 1번 — 판정 라벨이 하나라도 있으면 산출물을 쓰지 않는다.

    🔑 ***「안 쓰기로 했다」는 기억이고, 이 함수는 검사다.*** 둘은 다르다."""
    body = "\n".join(lines)
    hit = [lab for lab in FORBIDDEN_LABELS if lab in body]
    if hit:
        raise AssertionError(
            "🔴 PD-15 위반 — 판정 라벨이 산출물에 들어갔다: %s "
            "(동결 «선언» 부재로 이번 회차는 값 인쇄만 한다)" % ", ".join(hit))
    return True


def assert_both_n(lines):
    """🔴 §1-1 *「주 표본 n · 민감도 판 n 을 «둘 다» — 하나만 적으면 무효」*."""
    body = "\n".join(lines)
    miss = [k for k in ("주 표본 n", "민감도 판 n") if k not in body]
    if miss:
        raise AssertionError(
            "🔴 `PREREG_S5_FUND_NEWS_OOS.md` §1-1 위반 — 다음이 인쇄되지 않았다: %s "
            "(*「하나만 적으면 무효」*)" % ", ".join(miss))
    return True


# ══════════════════════════════════════════════════════════════════════════════
# 산문 블록 — DB 없이 만들어지는 부분 (가드 테스트가 이 함수들을 직접 문다)
# ══════════════════════════════════════════════════════════════════════════════
def header_lines(max_date, max_rows):
    L = []
    L.append("# RESULTS_S5_POST7_NUMBERS — 기계 생성 (수정 금지)\n")
    L.append("생성 `run_s5_post7.py` · 사전등록 [`PREREG_S5_FUND_NEWS_OOS.md`]"
             "(PREREG_S5_FUND_NEWS_OOS.md) v0.3(`f3ff8bc`) · "
             "인테이크 [`INTAKE_2026-09-15_post7.md`](INTAKE_2026-09-15_post7.md) §1·§5 · "
             "결정 [`PREDECISION_2026-09-15_post7.md`](PREDECISION_2026-09-15_post7.md) **PD-15**")
    L.append("")
    L.append("## §0. 실행 환경 · 동결 규약\n")
    L.append("| 항목 | 값 |")
    L.append("|---|---|")
    L.append("| 🔴 창 종료 | **창 종료 2026-09-11 = 발행일(2026-09-12 토) 휴장 ⇒ 마지막 거래일 · "
             "B-1(`WRC-` 포함 전 축)** |")
    L.append(f"| 🔴 실행 시 `max(date)` | **{max_date}** · 그 날짜 행수 **{max_rows:,}** "
             "— 🔴 **기록만 한다 · 창으로 쓰지 않는다**(PD-1 2번 표기 의무) |")
    L.append(f"| PIT 규약 | `dart_financials_asfiled` · `status = '{PIT_STATUS}'` ∧ "
             f"`rcept_dt <= {PIT_CUTOFF}`(글 게시일) · **가장 최근 사업연도 «하나»만** · "
             "🔴 실패해도 다른 해를 찾지 않는다(§1) |")
    L.append(f"| 대조군 | 같은 날 유니버스 `trading_value / market_cap` 백분위 **상위 1%**"
             f"(= `pct >= {TOP_PCT:.1f}`) — 태쏘 `f1` 축과 **같은 정의**"
             "(`run_selection.py:60` `f1_tv_mcap` · `:82-83` 일자별 `rank(pct=True)*100`) |")
    L.append("| 시드 | **%d** (계열 고정값) — 🔴 이 레인은 **난수를 쓰지 않는다**(결정적) |" % SEED)
    L.append("| Holm 가족 | 🔴 **+0** — 주 검정 수를 늘리지 않는다(§2) |")
    L.append("| 라이브 | 🔴 **라이브 채택 대상이 아니다** (`PREREG.md` §0-2) |")
    L.append("")
    L.append("🔴🔴 **이 문서에는 «판정»이 없다.** `(S5-` 로 시작하는 어떤 라벨도 선언하지 않는다"
             "(PD-15 1번). 근거는 **동결 «선언»의 부재**다 — 사전등록 커밋 `f3ff8bc`(2026-09-15 "
             "09:47:05)는 fetch(15:36:49)보다 **앞서지만** 그 메시지가 *「초안 v0.3 … **미동결**」* "
             "이다. `PREREG_GRADE_TIERS.md` §0-3 1번이 **동결과 커밋을 «같이»** 요구하므로 "
             "***커밋만으로는 동결이 아니다.*** 🔑 값을 본 뒤 동결 선언을 붙이면 그 자체가 사후적합이다.")
    L.append("🔴 **아래 모든 표의 꼬리표는 `[탐색]` 이다**(`PREREG_GRADE_TIERS.md` §1-3).")
    L.append("")
    return L


def contamination_lines():
    L = []
    L.append("## §0-1. 오염 고지 — **나는 이미 봤다** (§0 승계 · 재계산 아님)\n")
    L.append("| 이미 본 값 | 수 |")
    L.append("|---|---|")
    L.append(f"| 현재 원장 | **{CONTAM['ledger_trades']}건 / {CONTAM['ledger_legs']}레그 / "
             f"고유 {CONTAM['uniq_codes']}종목 / {CONTAM['posts']}글** |")
    L.append(f"| 영업적자(2026-09-14 패널) | **{CONTAM['seen_loss']}** "
             f"(대조 유니버스 {CONTAM['seen_univ']}) |")
    L.append(f"| 뉴스 보유(등록일 창) | **{CONTAM['seen_news']}** "
             f"vs 같은 날 유니버스 기준선 **{CONTAM['seen_news_base']}** |")
    L.append(f"| 이름→코드 매칭 **상한** | **{CONTAM['name_match']}** — 미매칭 8종목은 「모른다」로 남는다 |")
    L.append("")
    L.append("⇒ ***현재 62건에 대한 어떤 재무·뉴스 사전등록도 이제 사후적합이다*** — 그래서 예측은 "
             "**아직 «없는» 데이터(post7 이후 신규 건)에만** 걸려 있다(§0).")
    L.append("🔴 ***이름 매핑은 「비슷한 이름」에서 조용히 틀린다*** — 이 글에도 저자 표기 "
             "**「강동씨엔앨」** ↔ DB 표기 **「강동씨앤엘」**(`198440`)이 있다(PD-10 4번). "
             "코드는 인테이크 §1 표를 유일 출처로 쓴다.")
    L.append("")
    return L


def precision_lines():
    """🔴 §1-1 — 정밀도 분포 + **주 표본 n · 민감도 판 n 을 «둘 다»**(하나만 적으면 무효)."""
    n_main = len(EXACT6)
    n_sens = len(EXACT6) + len(APPROX2)
    L = []
    L.append("## §1. `reg_date` 정밀도 분포 · 표본 n **[탐색]**\n")
    L.append("| 정밀도 | 건 | 처리(§1-1 동결) |")
    L.append("|---|---|---|")
    L.append(f"| **`exact`** | **{len(EXACT6)}** | 🟢 **주 표본** — 인용은 이 건으로만 |")
    L.append(f"| `approx` | {len(APPROX2)} | ⚪ **민감도 인쇄만** · 🔴 판정 언어 금지 |")
    L.append(f"| `none`(신규) | {len(NONE2)} | 등록일 축 **밖**(PD-4 3번) |")
    L.append(f"| `none`(후속) | {len(FOLLOWUP3)} | 등록일 축 **밖**(PD-2) |")
    L.append(f"| `after` | 0 | 🔴 제외(§1-1 · 우측절단 관측) — 이번 글엔 없다 |")
    L.append("")
    L.append(f"- **주 표본 n = {n_main}** (신규 ∧ `exact`)")
    L.append(f"- **민감도 판 n = {n_sens}** (주 표본 + `approx` {len(APPROX2)})")
    L.append("- 🔴 §1-1 *「주 표본 n · 민감도 판 n 을 «둘 다» — **하나만 적으면 무효**」* ⇒ 위 두 줄은 "
             "**같이** 인쇄된다(이 스크립트의 `assert_both_n()` 가 쓰기 «전»에 검사한다).")
    L.append("- 🔴 `approx` 2건은 **갈래마다 등록일이 다르다**(`PREREG_POST6.md` §1-4 창 규약 첫 발동) ⇒ "
             "갈래별 값을 §4 에 그대로 인쇄하고, **한 수로 합치지 않는다**.")
    L.append("")
    return L


def no_fin_reason(code):
    """🔴 PD-15 2번 · PD-11 2번 — 「측정 불가」의 **사유를 문자로 가른다**.

    🔑 ***「이름 매칭 실패」와 「표 미수록」은 다른 고장이다*** — 앞은 우리 매핑의 문제이고
    뒤는 데이터의 문제다. 섞어 적으면 다음 사람이 엉뚱한 곳을 고친다."""
    if code in NO_FIN_CODES:
        return ("🔴 **`dart_financials_asfiled` «미수록»** — 이것은 «이름 매칭 실패»가 **아니다**. "
                "2026-08-25 신규 상장이고 그 표가 `max(rcept_dt) = %s` 에서 멈춰 있어 "
                "**행이 0개**다(PD-11 2번 · PD-15 2번). 코드 자체는 `%s` 로 **해결됐다**"
                % (PIT_LIMIT["max_rcept"], code))
    return "측정 불가(사유는 위 표)"


def pit_limit_lines():
    L = []
    L.append("## §2. 🔴 PIT 한계 — 표가 **멈춰 있다** (PD-15 4번 · 존재 사실)\n")
    L.append(f"- `dart_financials_asfiled` 전체 **{PIT_LIMIT['rows']:,}행** · "
             f"**`max(rcept_dt)` = {PIT_LIMIT['max_rcept']}** 에서 멈춰 있다.")
    L.append(f"- ⇒ *「`rcept_dt <= {PIT_CUTOFF}`(글 게시일)」* 조건은 **형식상 통과**하지만 "
             f"***표 자체가 {PIT_LIMIT['max_rcept']} 이후를 담지 않는다.*** "
             "「PIT 를 지켰다」와 「최신 공시를 봤다」는 **다른 말**이다.")
    L.append("- 🔴 그래서 이 축의 「최근 사업연도」는 **표가 가진 최근 연도**이지 "
             "「글 게시일 기준 최신 공시」가 아니다. 두 말을 섞지 않는다.")
    L.append("")
    return L


def sparsity_lines():
    L = []
    L.append("## §6. 희소성 가드 `P6-S1h-N` — ⚠️ **자동으로 발동하지 «않는다»** (§3 승계)\n")
    L.append("- 영업적자는 유니버스의 **25~31%**(하루 700~900종목)다. ⇒ ***같은 잣대를 적용하면*** "
             "「선정 규칙」 **인용 금지**가 된다(`P6-S1h-N` 과 같은 모양).")
    L.append("- ⚠️ **그러나 가드가 «자동으로» 발동한다고 쓰지 않는다** — **새 축에 같은 잣대를 "
             "«다시 등록»해야** 발동한다(CRITIC §2-3). 🔑 ***등록되지 않은 가드는 가드가 아니다.***")
    L.append("- 🔴 `f10`(재무·뉴스 축)은 **만들지 않는다**(C-8). 태쏘 고도화는 `f1`~`f9` 로 간다 — "
             "***「재봤다」는 기록만 남고 자유도는 실제로 쓴다.***")
    L.append("")
    return L


def news_defer_lines():
    L = []
    L.append("## §5. 뉴스 축 — **라벨 인쇄 «없음»** · 값만 `[탐색]` (§3 승계)\n")
    L.append("- §3 동결 문언: *「뉴스 「등록일 = 사건 후 τ일」 라벨 인쇄는 **`NW2` 곡선이 나온 뒤**로 "
             "줄 세운다」*(`docs/prereg_2026-09-14_news_event_curve.md`).")
    L.append(f"- ⇒ 이번 회차는 **τ 라벨을 하나도 인쇄하지 않는다.** 등록일 창 "
             f"`[등록일−{NEWS_BACK}, 등록일]` 의 **뉴스 보유 건수**만 `[탐색]` 꼬리표로 적는다.")
    L.append("- 🔴 이 수는 **검정이 아니다** — §0 이 이미 본 값(11/27 = 40.74% vs 29.71%)과 "
             "같은 축이라 **사후적합 구역**이다.")
    L.append("")
    return L


def limits_lines():
    L = []
    L.append("## §7. 한계 (승계 · 미리 적는다)\n")
    L.append("- 🔴 **검정력이 없다** — §2 동결 문언: `n=37 · p0=0.30` 에서 `z = −0.39 · p ≈ 0.35` 이고 "
             "뉴스 축 **MDE 24.6%p**(관측차 +11.0%p = **2.2배 미달**). ***애초에 기각도 지지도 "
             "못 한다*** — 그래서 「한 줄」이다.")
    L.append("- 🔴 **이름→코드 매칭 상한 83.0%** — 미매칭 종목의 재무는 「모른다」로 남고, 틀린 매핑은 "
             "**플래그 «값»으로** 전파된다(§0).")
    L.append("- 🔴 **해치텍의 「측정 불가」는 「적자 아님」이 아니다** — 분자·분모 어디에도 넣지 않는다.")
    L.append("- 🔴 **`adj_factor` 를 가격에 곱하지도 나누지도 않는다**(프로젝트 SSOT 규약).")
    L.append("- 🔴 이 분석은 **라이브 채택 대상이 아니다** (`PREREG.md` §0-2) — "
             "***등급이 무엇이든 라이브 채택 금지는 그대로다***(§3).")
    L.append("")
    return L


# ══════════════════════════════════════════════════════════════════════════════
# 측정 — §1 정의 그대로 (새 정의 0개)
# ══════════════════════════════════════════════════════════════════════════════
def pit_row(cur, code):
    """§1 PIT — `status='000'` ∧ `rcept_dt <= 게시일` 중 **가장 최근 사업연도 하나**.

    🔴 실패해도 다른 해를 찾지 않는다(동결 문언). 반환 = (bsns_year, rcept_dt, operating_income)
    또는 `None`(= 측정 불가)."""
    cur.execute(
        "SELECT bsns_year, rcept_dt, operating_income FROM dart_financials_asfiled "
        "WHERE stock_code = %s AND status = %s AND rcept_dt IS NOT NULL AND rcept_dt <= %s "
        "ORDER BY bsns_year DESC LIMIT 1", (code, PIT_STATUS, PIT_CUTOFF))
    r = cur.fetchone()
    if r is None or r[2] is None:
        return None
    return (r[0], r[1], int(r[2]))


def control_top1(cur, d):
    """§1 대조군 — 그날 유니버스의 `trading_value / market_cap` 백분위 **상위 1%** 종목코드.

    정의 출처 = `run_selection.py:60`(`f1_tv_mcap = trading_value / market_cap`) ·
    `:49-53`(유니버스 = `market_cap > 0` ∧ `close > 0` ∧ `PSEUDO` 제외) ·
    `:82-83`(일자별 `rank(pct=True) * 100`). **같은 관용구를 그대로 쓴다 — 새 정의가 아니다.**"""
    df = pd.read_sql(
        "SELECT stock_code, trading_value, market_cap FROM daily_prices "
        "WHERE date = %(d)s AND market_cap IS NOT NULL AND market_cap > 0 AND close > 0 "
        "AND trading_value IS NOT NULL", cur.connection, params={"d": d})
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    if df.empty:
        return [], 0
    df["f1_tv_mcap"] = df.trading_value / df.market_cap
    df["pct"] = df["f1_tv_mcap"].rank(pct=True) * 100
    top = sorted(df.loc[df["pct"] >= TOP_PCT, "stock_code"].tolist())
    return top, len(df)


def news_hits(cur, code, d):
    """등록일 창 `[D−NEWS_BACK, D]` 의 뉴스 건수 — 🔬 **탐색 인쇄 전용**(라벨 없음).

    조인 축 = `news_stock.news_id = news.id`(2026-09-15 실측 확인)."""
    cur.execute(
        "SELECT count(*) FROM news_stock ns JOIN news n ON n.id = ns.news_id "
        "WHERE ns.stock_code = %s AND n.published_at::date "
        "BETWEEN (%s::date - %s) AND %s::date", (code, d, NEWS_BACK, d))
    return int(cur.fetchone()[0])


def loss_rate(cur, codes):
    """(적자 건, 측정 가능 건, 측정 불가 코드) — 🔴 「모른다」를 「적자 아님」으로 접지 않는다."""
    loss, ok, unknown = 0, 0, []
    for c in sorted(set(codes)):
        r = pit_row(cur, c)
        if r is None:
            unknown.append(c)
            continue
        ok += 1
        if r[2] < 0:
            loss += 1
    return loss, ok, unknown


# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    t0 = time.time()
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    cur.execute("SELECT max(date) FROM daily_prices")
    max_date = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (max_date,))
    max_rows = int(cur.fetchone()[0])

    for ln in header_lines(max_date, max_rows):
        say(ln)
    for ln in contamination_lines():
        say(ln)
    for ln in precision_lines():
        say(ln)
    for ln in pit_limit_lines():
        say(ln)

    # ── §3. 선정 건(주 표본 `exact` 6) 건별 PIT ──────────────────────────────
    say("## §3. 선정 건 — `exact` 6 건별 PIT `[탐색]`\n")
    say("| 종목 | 코드 | 등록일 | 사업연도 | `rcept_dt` | `operating_income`(원) | 영업적자? |")
    say("|---|---|---|---|---|---|---|")
    sel_loss, sel_ok, sel_unknown = 0, 0, []
    news_tbl = []
    for nm, code, d in EXACT6:
        r = pit_row(cur, code)
        news_tbl.append((nm, code, d, news_hits(cur, code, d)))
        if r is None:
            sel_unknown.append((nm, code))
            say(f"| {nm} | `{code}` | {d} | — | — | — | 🔴 **측정 불가** |")
            continue
        sel_ok += 1
        neg = r[2] < 0
        if neg:
            sel_loss += 1
        say(f"| {nm} | `{code}` | {d} | {r[0]} | {r[1]} | {r[2]:,} | "
            f"{'🔴 **예**' if neg else '아니오'} |")
    say("")
    say(f"- **판정 가능 {sel_ok} / {len(EXACT6)}** · 측정 불가 **{len(sel_unknown)}**"
        + (f" ({', '.join(n for n, _ in sel_unknown)})" if sel_unknown else ""))
    say(f"- **선정 건 영업적자 비율 = {sel_loss}/{sel_ok} = {pct(sel_loss, sel_ok)}** `[탐색]`")
    for nm, code in sel_unknown:
        say(f"- {nm}(`{code}`) — {no_fin_reason(code)}")
    say("- 🔴 **측정 불가 건은 분자에도 분모에도 넣지 않는다** — 「모른다」를 「적자 아님」으로 접으면 "
        "그 건이 조용히 통과한다(재무 PIT 필터 계열 교훈 그대로).")
    say("")

    # ── §4. 대조군 (같은 날 상위 1%) ─────────────────────────────────────────
    say("## §4. 대조군 — 같은 날 `거래대금/시총` 상위 1% `[탐색]`\n")
    say("| 등록일 | 그날 유니버스 | 상위 1% 종목 수 | 측정 가능 | 영업적자 | 적자 비율 |")
    say("|---|---|---|---|---|---|")
    pool_loss, pool_ok = 0, 0
    for _nm, _code, d in EXACT6:
        top, n_univ = control_top1(cur, d)
        lo, ok, _unk = loss_rate(cur, top)
        pool_loss += lo
        pool_ok += ok
        say(f"| {d} | {n_univ:,} | {len(top)} | {ok} | {lo} | {pct(lo, ok)} |")
    say("")
    say(f"- **대조군 적자 비율(pooled · 종목-일) = {pool_loss}/{pool_ok} = "
        f"{pct(pool_loss, pool_ok)}** `[탐색]`")
    say("- 🔴 **구현 결정(인쇄 의무)**: §1 은 *「그날 … 대조군의 적자 비율」* 이라고만 적고 "
        "**여러 날을 어떻게 합칠지는 말하지 않는다.** ⇒ 주 수치는 **종목-일 pooled**(위 합계)로 두고 "
        "**날짜별 값을 같은 표에 병기**한다. 두 셈법 중 어느 쪽도 «고르지» 않았다 — 둘 다 인쇄한다.")
    if sel_ok and pool_ok:
        diff = 100.0 * sel_loss / sel_ok - 100.0 * pool_loss / pool_ok
        say(f"- **차이(선정 − 대조군) = {diff:+.1f}%p** `[탐색]` · "
            "🔴 §1 의 예측 문장(`±10%p`)과 **대조하지 않는다** — 판정 라벨을 선언하지 않기 때문이다"
            "(PD-15 1번). 값만 적는다.")
    say("")

    # ── §4-1. `approx` 민감도 (갈래별 · 판정 언어 금지) ───────────────────────
    say("### §4-1. `approx` 2건 — **민감도 인쇄만** · 갈래별 `[탐색]`\n")
    say("| 종목 | 코드 | 창 서술 | 갈래 수 | 사업연도 | 영업적자? | 대조군 적자 비율(갈래 범위) |")
    say("|---|---|---|---|---|---|---|")
    for nm, code, desc, days in APPROX2:
        r = pit_row(cur, code)
        rates = []
        for d in days:
            top, _n = control_top1(cur, d)
            lo, ok, _u = loss_rate(cur, top)
            if ok:
                rates.append(100.0 * lo / ok)
        rng = f"{min(rates):.1f}~{max(rates):.1f}%" if rates else "—"
        yr = r[0] if r else "—"
        neg = "🔴 **예**" if (r and r[2] < 0) else ("아니오" if r else "🔴 측정 불가")
        say(f"| {nm} | `{code}` | {desc} | {len(days)} | {yr} | {neg} | {rng} |")
    say("")
    say("- 🔴 §1-1 *「`approx` … **판정 언어 금지**」* ⇒ 위 표의 어떤 값도 판정에 쓰지 않는다.")
    say("- 🔴 갈래별 값을 **한 수로 합치지 않는다**(PD-4 2번 · `P6-W10` 두 용도 분리와 같은 잣대).")
    say("")

    # ── §5. 뉴스 (라벨 없음) ─────────────────────────────────────────────────
    for ln in news_defer_lines():
        say(ln)
    say(f"| 종목 | 코드 | 등록일 | 창 `[D−{NEWS_BACK}, D]` 뉴스 건수 |")
    say("|---|---|---|---|")
    for nm, code, d, k in news_tbl:
        say(f"| {nm} | `{code}` | {d} | {k} |")
    say("")
    say("- 🔬 **탐색 표기 · 판정 아님 · τ 라벨 없음**(§3).")
    say("")

    for ln in sparsity_lines():
        say(ln)
    for ln in limits_lines():
        say(ln)

    # ── 🔴 쓰기 «전» 자기 가드 ────────────────────────────────────────────────
    assert_no_verdict(OUT)
    assert_both_n(OUT)

    (BASE / "RESULTS_S5_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    note("")
    note("[guard] assert_no_verdict ✅ · assert_both_n ✅")
    note(f"[written] RESULTS_S5_POST7_NUMBERS.md · 런타임 {time.time() - t0:.3f}s")
    note("🔴 산문 `RESULTS_S5_POST7.md` 는 «사람이» 쓴다 — 이 스크립트는 만들지 않는다"
         "(`MANUAL_DOCS` 자리 · `RESULTS_WRC_POST6.md` 전례).")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
