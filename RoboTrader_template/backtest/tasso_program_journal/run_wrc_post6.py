# -*- coding: utf-8 -*-
"""`WRC-` 축 **판정** 실행 — 6번째 글(`PREREG_WEIGHTED_RECON.md` §0-3 **6번** · §6-1 판정 게이트).

🔴 **이 회차는 «판정»이다.** 탐색(`RESULTS_WRC_EXPLORE.md` · post4·post5)과 달리 이 산출물의 값은
`WRC-O1`(§4-5)이 말하는 **판정 분모**에서 나온다. 대상은 **post6(`logNo=224401108114`) «만»**이다.

사전등록·동결(값을 보기 «전»에 고정):
  · `PREREG_WEIGHTED_RECON.md`(2026-09-02 동결 · `WRC-D1`~`D7` 사장님 확정)
      §2-1 모델 `WRC-A0`·`A1`·`A3`(+공통 부가 제약 (가)(나)(다)(라)) · §2-4 부분집합 정리
      §2-7 `WRC-R5` 재진입·미완결 · §4 예측표(`P1`·`N1`·`N2`·`B1`·`G1`·`O1`·`X1`·`V1`)
      §5-1 `WRC-R6` 코드 재사용 · §5-2 `WRC-R7` 실행 환경·창 · §5-4 `WRC-R9` 표기 4줄
      §6-1 `WRC-R11` 판정 분모(= `exact` ∧ `fill_n ≥ 2` ∧ 서로 «다른» 값 레그 ≥ 3) · §9 한계
  · `FREEZE_WRC_2026-09-02.md` — 주 모델 `WRC-A1`(균등 `1/N`) · `A3` 는 무정보 상한 대조 ·
      **§3 `WRC-X1` 3번 «관대 읽기» 확정** ⇒ **대조군 (나)(셔플 레그)는 ⛔ 무정보 강등 ·
      판별력 검정은 (가) 갈래 «단독»** · 시드 `20260815` · 20,000회 · 밴드 3%p · G1 1/3 · N 50%
  · `PREDECISION_2026-09-04_post6.md` — PD-1(발행일 = 창 종료 = **2026-09-04** · 발행 당일 봉 «포함»)
      PD-2(후속 2건 = 등록일 축 분모 «밖») · PD-3(재진입 지투파워 flag 1 · 현대약품 0) ·
      PD-4(미완결 = «서술» 기준) · PD-12
  · `INTAKE_2026-09-04_post6.md` §1(종목·코드·등록일·차수·레그) · §5(WRC 분모 «예측» 5건)
  · `PREREG_POST6.md` §1-7 `REC-Z5`(잔차 판정 0.022 · 의무 민감도 0.020) · §2-6 `REC-Z3`(앵커)

🔴 **계산 «전» 에 고정한 해석 결정 (A-1 ~ A-11)** — `RESULTS_RECONSTRUCT_POST5.md` §1 동결분을
   `PREREG_WEIGHTED_RECON.md` §1-3 이 *「전부 승계하고 스크립트 docstring 에 같은 문장을 박는다」*
   고 요구한다. 아래는 `run_reconstruct_post5.py`·`run_wrc_explore.py` docstring 과 **같은 문장**이다:

  A-1 창 종료일 = 2026-08-28 (DB 스냅샷 최대). 발행일 08-29 는 토요일 = 휴장.
  A-2 Y1 은 «전칭»으로 읽는다 — 레그 4개 이상인 «모든» 건의 폭 < 3%p. 건수 비율도 병기.
  A-3 되밀림 = 등록일 종가 < 등록일 고가 · 상한가마감 = 종가 == 고가 (post4 §3 조작화 승계).
  A-4 D1 표본 = 프리셋 `HDR 60%` 인 건. 혜인(`사분위수 Q1~Q3`)은 분모 «밖» — D2/L4 관측으로 따로.
      `MANUAL`(한켐)은 post4 전례(이노테크 포함)대로 포함하되 제외 민감도 병기.
  A-5 R1: 이번 글은 `first_only` 有 · `full` 無 다. `PREREG_Q1_V2.md` §3 의 합침 조항은
      *「같은 글 안에 «둘 다» 없으면」* 이 조건이라 **이번 경우를 덮지 않는다**(사전등록 문언 «밖»).
      공백을 **보수적 방향(판정 안 함 · 관측만)** 으로 메운다. 직전 3글의 `full` 값은 대조로만 인쇄.
  A-6 R3 은 다차수 건의 `1−P/H` 가 「1차 밴드」가 아니라는 post4 §2 범주오류 판정을 유지한다.
      `first_only`(삼양) 1건만 진짜 `b₁` ⇒ n=1 관측.
  A-7 L3 실행 전제 = 「`b₁` 구간 폭 / σ₂₀ 이 사전등록 격자 `±0.25` 보다 좁은 건이 과반」.
      미달이면 공통해 탐색을 «돌리지 않고» 판정 불가.
      🔴 **이 게이트는 사전등록에 «없다»** — post4 §5 가 말로만 적은 중단 사유를 사전등록 자신의
      격자 폭에 붙여 수치화한 «추가 자유도»다. §10 에 그렇게 적는다.
  A-8 σ₂₀ = 등록일 직전 20거래일 로그수익률의 표본표준편차(연율화 안 함).
      수익률 20개 미만이면 그 건은 σ 축에서 제외.
  A-9 한켐(post5)은 한 항목 안에 두 사이클(본전매도 → 재진입)이 있다 — 「하나의 평단」 전제가
      원리적으로 깨질 수 있다. 항목 단위 라벨·차수는 그대로 두고 flag 만 단다.
  A-10 «해 0개» 진단의 잔차 문턱은 **사전등록에 없다.** 프로젝트가 가진 유일한 자체 근거는
      `PREREG_EXIT_V2.md` §1-2 의 *「복원이 측정한 gross 잔차는 0.010~0.022%p」* 와
      §2 의 *「복원 잔차 상한(0.022%p)」* 이다. ⇒ **0.020 과 0.022 «둘 다»로 분류를 인쇄**하고,
      분류가 갈리면 **「문턱 의존」으로 적는다**(어느 한쪽을 고르지 않는다).
  A-11 feasible set 은 **정확 구간법**으로 푼다. 제약은 `round(100·(S/P−1), 2) == r` 이므로
      `P` 는 «점»이 아니라 구간이다:  `P ∈ ( S/(1+(r+0.005)/100),  S/(1+(r−0.005)/100) ]`.
      레그별로 「봉 안에 있는 격자 매도가 S」 전부에 대한 구간들의 **합집합**을 만들고,
      레그 전체에 대해 **교집합**을 취한다.
      🔴 post4(`run_reconstruct_post4.py`)와 이 스크립트의 초판은 `S₁` 격자마다 `P` 를 **단일점**
      으로 잡았다 ⇒ 그 방식의 「개수·폭」은 **하한**이다. 대조로 함께 인쇄한다.

⚠️ **A-1 의 «값»에 대한 승계 고지**: `WRC-D7` 은 창 종료일을 *「실행 시 DB 스냅샷 최대일」* 로 동결했다.
   ⇒ **규칙을 승계하고 값은 실행 시점에서 다시 읽는다.** 이 실행의 값(= `2026-09-04`)은 §0 에 박는다.
   `PREDECISION_2026-09-04_post6.md` PD-1 이 **발행일 = 거래일 = DB 최대일**임을 «계산 전»에 못박았다
   ⇒ 이 회차는 「창 종료 = **발행 당일 봉 «포함»**」이다.

🔴 `WRC-R6`(§5-1) — 호가단위·격자·해찾기·모델은 **전부 기존 함수 import**:
   `reconstruct_prices.tick`·`.grid_prices` · `run_reconstruct_post5.leg_intervals`·`.feasible_exact`·
   `._merge`·`._intersect`·`.iv_measure`·`.iv_min`·`.iv_max`·`.iv_has`·`.min_residual` ·
   `run_wrc_explore.make_ctx`·`.a1_solve`(닫힌형+DP)·`.a3_set`·`.a3_bands`·`.bands_from_ext`·
   `.feasible_plo`·`.read_ledger`·`.build_cases`·`.med`·`.med_note`·`.sha_list`·`.NOTATION_4` ·
   문턱 상수(`SEED`·`NREP`·`THR`·`BAND_THR`·`G1_THR`·`N_THR`)도 **import 해서** 쓴다.
   **표·문턱·솔버를 복사해 다시 쓰지 않는다**(`WRC-X1` 4번).
   ⚠️ 예외 2개(«새 정의»가 아니라 «내부 헬퍼의 재조립»): `run_wrc_explore.main()` 안의 지역 함수
   `ctx_for`·`evaluate` 는 import 할 수 없어 **같은 본문으로** 이 파일에 다시 적었다. 그 사실을 §5 에 인쇄한다.

🔴 라이브 트리 import 0건 · DB 는 **SELECT 만** · `adj_factor` 산술 0건 · 원장은 «읽기»만 ·
   `git` 은 조회만(`rev-parse`·`merge-base`·`diff --quiet`·`status --porcelain`).
🔴 **HEAD 해시를 본문에 적지 않는다**(`FREEZE_WRC_2026-09-02.md` §2 규약) — stdout 전용.
🔴 **라이브 채택 금지**(`PREREG.md` §0-2) — 이 산출물의 어떤 `bₖ` 도 매매 규칙·파라미터가 아니다.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import psycopg2

from reconstruct_prices import gross_ret
from run_reconstruct_post5 import (
    _intersect,
    feasible_exact,
    iv_has,
    iv_max,
    iv_measure,
    iv_min,
    min_residual,
)
from run_selection import PSEUDO
from run_tests import DSN
from run_wrc_explore import (
    BAND_THR,
    CODEMAP,
    G1_THR,
    NOTATION_4,
    NREP,
    N_THR,
    SEED,
    THR,
    a1_solve,
    a3_bands,
    a3_set,
    bands_from_ext,
    build_cases,
    feasible_plo,
    make_ctx,
    med,
    med_note,
    read_ledger,
    sha_list,
)

BASE = Path(__file__).resolve().parent
ART = BASE / "wrc_post6"
OUT: list[str] = []

POST_LOG = "224401108114"        # INTAKE_2026-09-04_post6.md 머리말
POST_DATE = "2026-09-04"         # PD-1 (발행일 = 거래일 = DB 최대일)
LABEL = "post6"

# ── 6번째 글 종목코드 — `INTAKE_2026-09-04_post6.md` §1 표 «그대로» (12/12 DB 존재 · PD-9) ────────
#    🔴 원장(`ledger_trades.csv`)에는 종목코드 컬럼이 «없다» ⇒ 이름→코드는 인테이크가 유일 출처다.
#    `run_selection_post6.py`·`run_regday_post6.py` 의 표와 같은 값이어야 한다(§10 에서 대조 인쇄).
CODES6 = {
    "광전자": "017900", "삼양바이오팜": "0120G0", "한라캐스트": "125490",
    "헥토파이낸셜": "234340", "아난티": "025980", "아이티센글로벌": "124500",
    "현대약품": "004310", "원익": "032940", "쿠콘": "294570", "지투파워": "388050",
    "우리기술투자": "041190", "비에이치": "090460",
}

# INTAKE_2026-09-04_post6.md §5 「WRC」 행이 «계산 전»에 적은 판정 분모 «예측»
INTAKE_DENOM_PRED = ["한라캐스트", "원익", "지투파워", "우리기술투자", "비에이치"]

# PD-3 표가 «계산 전»에 못박은 재진입 플래그 (현대약품은 분모 밖일 수 있다 — 그대로 인쇄한다)
PD3_FLAG = {"지투파워": 1, "현대약품": 0}

# `FREEZE_WRC_2026-09-02.md` §2 md5 표 «그대로» — 탐색본 불변 증명의 «제3자» 기준값.
FREEZE_MD5 = {
    "run_wrc_explore.py": "b63f90349c7dcfcbfb6ccb1129b4cad0",
    "RESULTS_WRC_EXPLORE.md": "1280c0eeec1fa1a6b6de1679112e8718",
    "wrc_explore/bands.tsv": "7384df63ac6978a0496a10936b878733",
    "wrc_explore/controls_summary.json": "e855c53812181714ca7b66917231735b",
    "wrc_explore/universe_snapshot.json": "8e264fb37c5be6de1b33fc1ff4626bdf",
    "wrc_explore/remeasure_2_5.json": "dedd0981bd8fb97ba5a56b3c223c0b12",
    "PREREG_WEIGHTED_RECON.md": "827c6f7080f2e6ad1a132ce4f1dff16f",
    "regen_gate.py": "a614028767367eac0c800ba452d62576",
    "reconstruct_prices.py": "dc2d69d3c07cfb84147a3692bd16f13e",
    "run_reconstruct_post5.py": "11228c0bfc32f7136d9478656563aa32",
    "run_reconstruct_post4.py": "3ab144b4e3c46fa1c6c8824830b327a2",
    "run_selection.py": "fa366edf5f8beca0b22560e810fc5f34",
    "run_tests.py": "a122eecd3f17e7a8ded9af48d2fd6dfe",
}

# ── 🔴 원장은 «여러 레인이 동시에 쓰는» 공유 파일이다 — **통째 md5 를 박지 않는다** ──────────
#    (`run_ranking.py` §10 관용 승계: *「여러 레인이 같은 파일을 동시에 쓰는 동안에는 「파일 md5」가
#     재현성 장치가 아니라 «재현성 파괴 장치»다 — 박아야 할 것은 «내가 읽는 필드»의 지문이다」*)
#    🔴 실측 사유: post6 최종 레인이 한라캐스트 `narrative` 1줄을 정정하자 `ledger_trades.csv` 의
#      통째 md5 가 `624f5a97…` → `39cd83db…` 로 움직였다. **판정 수치는 한 자리도 안 움직였다** —
#      이 축은 `narrative` 를 «읽지 않기» 때문이다. 통째 md5 를 박았으면 그 편집만으로
#      이 산출물이 재현 불가가 됐을 것이다.
#    ⇒ 고정하는 것 둘: ① **prefix md5**(post6 «전» 행 = 동결 시점 바이트 그대로) ·
#      ② **판독 필드 지문**(이 축이 실제로 읽는 열만 뽑아 정렬해 해시 · `narrative` 제외).
LEDGER_PREFIX = {                      # 파일: (줄 수, 동결 md5) — 줄 수는 «post6 전» 행까지다
    "ledger_trades.csv": (51, "5d603de7d0ac1ed853eaaf960c1f0883"),    # 헤더 + post1~5 50행
    "ledger_legs.csv": (170, "f195e260587865ad2a36102412874897"),     # 헤더 + post1~5 169레그
}
# `run_ranking.py:1338-1341` 의 `_KEY` 와 **같은 컬럼 집합·같은 순서**(레인 간 대조 가능하게).
RNK_KEY = ("post_log_no", "post_date", "item_no", "stock_name",
           "reg_date", "reg_date_precision", "all_loss")
# 🔴 그런데 `RNK_KEY` 에는 **이 축의 분모를 정하는 `fill_n`·`open_ended` 가 없다** ⇒ 그것만 쓰면
#    내 의존을 «덜» 덮는다. RNK 와 같은 잣대를 «그대로» 인쇄하되, 이 축이 실제로 읽는 열의 지문을
#    **함께** 박는다(가드를 약화시키지 않으려면 둘 다 필요하다).
WRC_KEY = ("post_log_no", "post_date", "prog_ver", "item_no", "stock_name", "open_ended",
           "reg_date", "reg_date_precision", "fill_level", "fill_n", "preset")
LEG_KEY = ("post_log_no", "item_no", "leg_idx", "ret_pct")   # `read_ledger` 가 읽는 전부
# 동결 «후» 바뀌는 것이 «정상»인 파일과 그 사유(값을 보고 고른 목록이 아니라 작업 정의에서 나온다)
EXPECTED_CHANGE = {
    "run_wrc_explore.py": "이 회차가 **post6 «명시» 제외 필터**를 넣었다 — §0-2 에 전문 인쇄",
    "regen_gate.py": "post6 **최종 레인의 `C-23` 수리**(`PAIRS` 인자화 · `FROZEN_STALE` 스킵 · "
                     "`ART_DIRS` 스냅샷) — 이 축 «밖»의 작업이며 이 축의 판정 수치를 «입력으로 "
                     "쓰지 않는다**(`regen_gate.py` 는 산출물 등재·재현 게이트 전용이다). "
                     "🔴 이 회차는 그 파일의 **수정 금지** 대상이라 손대지 않았다",
}

# `FREEZE_WRC_2026-09-02.md` §4 탐색 동결값 (창 `~2026-09-02`) — `WRC-O1` 병기용 «인용»이다.
EXPLORE_FROZEN = {
    "G1": "6/10 = 60.0% (post4 20.0% 미발동 · post5 100% 발동) ⇒ 🔴 발동",
    "denominator": "10건(post4 5 · post5 5) · 게이트 통과율 10/18 = 55.6%",
    "A0_feasible": "4건(이노테크·한켐p4·지투파워·PS일렉) — 전부 post4",
    "A1_bands": "2건(이노테크·지투파워) — `A1` 격자 정합으로 2건이 공집합",
    "band_w": "이노테크 중앙 11.36%p · 지투파워 중앙 7.38%p · 전 건 전 차수 최소 6.83%p(> 3%p)",
    "P1": "0/2 (과반 미달) — 🔬 탐색 표기",
    "N1": "(가) 7.0% ⇒ 미발동 / (나) ⛔ 무정보",
    "N2": "(가) 10.8% ⇒ 미발동 / (나) ⛔ 무정보",
    "B1": "전건 1.0000 (측도 잣대 항등)",
    "Z3": "7/9 = 77.8% (창 `~2026-09-02`)",
}


def say(s=""):
    print(s)
    OUT.append(s)


def md5(p: Path):
    return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None


def prefix_md5(p: Path, n: int) -> str:
    """파일의 «앞 n 줄»까지(그 줄의 개행 포함) 바이트 prefix 의 md5.

    🔴 `run_ranking.py:1357-1359` 의 구현과 **같은 식**이다(`b"\\n".join(split(b"\\n")[:n]) + b"\\n"`)
    — 레인 간 값을 대조할 수 있어야 하므로 «같은 정의»를 쓴다."""
    return hashlib.md5(b"\n".join(p.read_bytes().split(b"\n")[:n]) + b"\n").hexdigest()


def csv_rows(fname: str) -> list[dict]:
    import csv
    return list(csv.DictReader((BASE / fname).open(encoding="utf-8")))


def field_key(rows, cols) -> str:
    """«판독 필드 지문» — 지정 열만 뽑아 정렬해 해시한다(`run_ranking.py:1340-1341` 과 같은 식).

    정렬하므로 **행 순서에 불변**이고, 열을 골랐으므로 **안 읽는 열(`narrative`)의 편집에 불변**이다."""
    return hashlib.md5("\n".join(sorted("|".join(r[c] for c in cols) for r in rows))
                       .encode("utf-8")).hexdigest()


def git(*a):
    try:
        return subprocess.run(["git", *a], cwd=str(BASE), capture_output=True,
                              text=True, encoding="utf-8", errors="replace").stdout.strip()
    except Exception:  # noqa: BLE001
        return "(git 실행 실패)"


def git_rc(*a):
    try:
        return subprocess.run(["git", *a], cwd=str(BASE), capture_output=True).returncode
    except Exception:  # noqa: BLE001
        return -1


def main() -> int:  # noqa: C901, PLR0912, PLR0915
    t_start = time.time()
    ART.mkdir(exist_ok=True)
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    # ══ §0. 실행 환경 ═══════════════════════════════════════════════════════
    head = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    anc = git_rc("merge-base", "--is-ancestor", "8d28e14", "HEAD") == 0
    cur.execute("SELECT max(date) FROM daily_prices")
    END = cur.fetchone()[0]
    cur.execute("SELECT count(*), count(DISTINCT stock_code) FROM daily_prices WHERE date=%s", (END,))
    end_rows, end_codes = cur.fetchone()

    say("# RESULTS_WRC_POST6_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_wrc_post6.py` · 사전등록 **`PREREG_WEIGHTED_RECON.md`**(§0-3 **6번** 판정) · "
        "동결 **`FREEZE_WRC_2026-09-02.md`** · 결정 **`PREDECISION_2026-09-04_post6.md`** · "
        "인테이크 **`INTAKE_2026-09-04_post6.md`** §1·§5")
    say("재사용 `reconstruct_prices.py`(`tick`·`grid_prices`) · `run_reconstruct_post5.py`"
        "(`leg_intervals`·`feasible_exact`·`_merge`·`_intersect`·`iv_*`·`min_residual`) · "
        "`run_wrc_explore.py`(`make_ctx`·`a1_solve`·`a3_set`·`a3_bands`·`bands_from_ext`·"
        "`feasible_plo`·`build_cases`·문턱 상수)\n")
    say("🔴🔴 **이 문서의 값은 «판정» 회차의 값이다** — 대상은 **post6 «만»**"
        f"(`logNo={POST_LOG}` · 발행 {POST_DATE}). 탐색값(post4·post5)은 `WRC-O1`(§4-5) 대로 "
        "**판정 분모에 넣지 않으며** §7 에 «나란히» 인용 표기로만 둔다.")
    say("🔴 **라이브 채택 금지** — 이 문서의 어떤 숫자도 매매 규칙·파라미터로 옮기지 않는다"
        "(`PREREG.md` §0-2 · `PREREG_WEIGHTED_RECON.md` §0-1 승계).")
    say("🔴 **이 문서는 새 예측·새 문턱을 만들지 않는다** — 쓰는 문턱은 전부 동결본에서 «import» 했다"
        f"(밴드 `< {BAND_THR:.0f}%p` · `WRC-G1` `≥ 1/3` · `WRC-N1`·`N2` `≥ {N_THR:.0%}` · "
        f"잔차 `{THR[1]}`/`{THR[0]}` · 시드 `{SEED}` · {NREP:,}회).\n")

    say("## §0. 실행 환경 (`WRC-R7` · §5-2)\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 브랜치 | `{branch}` {'✅' if branch == 'fix/tasso-post6-s5-fixes' else '🔴 **다르다**'} |")
    say(f"| `8d28e14` 가 조상인가 | {'✅ 예' if anc else '🔴 아니오'} |")
    say("| HEAD 해시 | 🔴 **이 파일에 적지 않는다** — stdout 전용"
        "(`FREEZE_WRC_2026-09-02.md` §2: *「커밋마다 바뀌는 값을 산출물에 적으면 그 산출물은 "
        "자기 자신을 재현할 수 없게 된다」*) |")
    say(f"| **DB 스냅샷 최신 봉** | **`{END}`** (그날 {end_rows:,}행 · {end_codes:,}종목) |")
    say(f"| 창 규약 | `[등록일, {END}]` — `WRC-D7`(실행 시 DB 스냅샷 최대일) |")
    say(f"| **창 종료 = 발행 당일 봉 «포함»** | 발행 {POST_DATE} = **거래일** = DB 최대일 ⇒ "
        f"{'✅ 세 값이 같다' if END == POST_DATE else '🔴 **다르다 — PD-1 전제가 깨졌다**'} "
        "(PD-1 · 주말 규약 `RESULTS_LADDER_TRANCHE.md` §1 `B-1` **발동 안 함**) |")
    say(f"| 시드 · 반복 | `{SEED}` · **{NREP:,}회** (`run_selection.py:22` 는 `NREP = 2000` — "
        f"**{NREP // 2000}배** · `PREREG_POST6.md` §3-1 동결분을 따른다) |")
    say(f"| 잔차 문턱 | 판정 `{THR[1]}%p` · 의무 민감도 `{THR[0]}%p` (`REC-Z5`) |")
    say(f"| 중앙값 관용구 | {med_note(2)} / {med_note(3)} — C-20 감사 결과 그대로 |")
    say()

    # ── 0-1. 탐색본 불변 증명 ────────────────────────────────────────────────
    say("### 0-1. 🔴🔴 탐색본(`RESULTS_WRC_EXPLORE.md` · `wrc_explore/`) **불변 증명**\n")
    say("**왜 여기 있나**: 이 회차는 원장에 post6 12행/47레그를 append 한 «뒤»에 돈다. "
        "탐색 산출물이 그 append 로 움직이면 `WRC-O1`(탐색/판정 분리)이 **사후적으로** 무너진다. "
        "⇒ 동결본 md5(`FREEZE_WRC_2026-09-02.md` §2 표)와 **커밋 대비 byte 동일 여부**를 둘 다 잰다.\n")
    say("🔴 **불일치는 «맞추지» 않는다 — 원인을 규명해 세 부류로 가른다**"
        "(`run_reconstruct_post4_exact.py` 관용: *「숫자가 문서마다 다르면 «원인 규명»이 먼저다」*): "
        "① 이 회차가 바꾼 것(선언된 것) · ② **이 축 «밖»의 커밋**이 바꾼 것(워킹트리 = HEAD) · "
        "③ 🔴 그 밖(= 설명되지 않는 로컬 변경). ***부류는 «값»이 아니라 «누가 바꿨나»로 가른다.***\n")
    say("| 파일 | 동결 md5 | 현재 md5 | 일치 | 부류·원인 |")
    say("|---|---|---|---|---|")
    md5_rows = []
    for f, want in FREEZE_MD5.items():
        got = md5(BASE / f)
        ok = (got == want)
        dirty = bool(git("status", "--porcelain", "--", f))
        kind = "same"
        if not ok:
            if f in EXPECTED_CHANGE:
                kind, note = "declared", "🟡 **① 이 회차가 바꿨다(선언됨)**: " + EXPECTED_CHANGE[f]
            elif not dirty:
                last = git("log", "-1", "--format=%h %s", "--", f)
                kind, note = "outside_commit", ("🟡 **② 이 축 «밖»의 커밋**이 바꿨다 — 워킹트리 = HEAD · "
                                                f"마지막 커밋 `{last}`")
            else:
                kind, note = "unexplained", "🔴🔴 **③ 설명되지 않는 로컬 변경**"
        else:
            note = "🟢 불변이어야 한다" if f not in EXPECTED_CHANGE else "🔴 **바뀌었어야 하는데 안 바뀌었다**"
        md5_rows.append(dict(file=f, frozen=want, now=got, match=ok, kind=kind,
                             expected_change=f in EXPECTED_CHANGE, dirty=dirty))
        say(f"| `{f}` | `{want[:12]}…` | {'`%s…`' % got[:12] if got else '⛔ **파일 없음**'} | "
            f"{'✅' if ok else '🔴 **다르다**'} | {note} |")
    say()
    outside = [r["file"] for r in md5_rows if r["kind"] == "outside_commit"]
    say(f"- 🟡 **② 이 축 밖의 커밋이 바꾼 파일 = {len(outside)}건** "
        f"({', '.join('`%s`' % f for f in outside) or '없음'}) — 동결 md5 표가 «그 커밋만큼» 낡았다는 뜻이며 "
        "**이 축의 산출물이 오염됐다는 뜻이 아니다**(워킹트리 = HEAD 로 확인). "
        "🔑 *동결 md5 표는 그 시점의 스냅샷이라 뒤 커밋이 같은 파일을 건드리면 «정상적으로» 어긋난다 — "
        "그래서 어긋남을 «누가 바꿨나»로 갈라야 한다.*")
    unexpected = [r["file"] for r in md5_rows if r["kind"] == "unexplained"]
    missing_expected = [r["file"] for r in md5_rows if r["match"] and r["expected_change"]]
    say(f"- 🔴 **③ 설명되지 않는 로컬 변경 = {len(unexpected)}건** "
        f"({', '.join('`%s`' % f for f in unexpected) or '없음'}) "
        "— 1건이라도 있으면 이 산출물의 `WRC-O1` 병기는 «다른 탐색본»을 인용하는 것이 된다.")
    say(f"- ⚠️ **바뀔 것으로 적었는데 안 바뀐 파일 = {len(missing_expected)}건** "
        f"({', '.join('`%s`' % f for f in missing_expected) or '없음'}) — "
        "0 이 아니면 원장 append 또는 필터 수정이 «실제로는 일어나지 않았다»는 뜻이다"
        "(가드가 양방향으로 서 있는지 확인하는 칸).")
    # ── 원장 «의존 지문» — 통째 md5 대신 (§0-1 이 인용하는 유일한 원장 지문) ───────────────
    tr_rows = csv_rows("ledger_trades.csv")
    lg_rows = csv_rows("ledger_legs.csv")
    p6_rows = [r for r in tr_rows if r["post_log_no"] == POST_LOG]
    p6_legs = [r for r in lg_rows if r["post_log_no"] == POST_LOG]
    fp = {}
    say()
    say("#### 0-1-1. 🔴 원장은 «공유 파일» — **통째 md5 를 박지 않는다**(`run_ranking.py` §10 관용 승계)\n")
    say("**실측 사유**: post6 최종 레인이 한라캐스트 `narrative` **1줄**을 정정하자 "
        "`ledger_trades.csv` 의 통째 md5 가 움직였다. 🔴 **이 축은 `narrative` 를 «읽지 않으므로» "
        "판정 수치는 한 자리도 안 움직인다** — 통째 md5 를 박았으면 *「남의 «판정과 무관한» 편집 "
        "때문에 내 산출물이 재현 불가가 된다」*(그 문장 그대로의 사례). "
        "⇒ **prefix md5**(post6 «전» 행 = 동결 시점 바이트)와 **판독 필드 지문**(내가 읽는 열만)을 박는다.\n")
    say("| 지문 | 정의 | 값 | 동결값 대조 |")
    say("|---|---|---|---|")
    for f, (n, want) in LEDGER_PREFIX.items():
        got = prefix_md5(BASE / f, n)
        fp[f + f":prefix{n}"] = got
        say(f"| `{f}` **prefix {n}줄** | 헤더 + post6 «전» 행까지의 바이트 prefix | `{got}` | "
            f"동결 `{want[:12]}…` ⇒ {'✅ **일치**(그 행들은 손대지 않았다)' if got == want else '🔴 **다르다 — 과거 행이 움직였다**'} |")
    fp["trades:RNK_KEY(post6)"] = field_key(p6_rows, RNK_KEY)
    fp["trades:WRC_KEY(post6)"] = field_key(p6_rows, WRC_KEY)
    fp["legs:LEG_KEY(post6)"] = field_key(p6_legs, LEG_KEY)
    say(f"| `ledger_trades.csv` **판독 필드 지문**(post6 {len(p6_rows)}행 · `RNK_KEY` 7열) | "
        f"{' · '.join('`%s`' % c for c in RNK_KEY)} | `{fp['trades:RNK_KEY(post6)']}` | "
        "🔵 `run_ranking.py:1338` 과 **같은 컬럼·같은 순서**(레인 간 대조용) |")
    say(f"| 〃 (post6 {len(p6_rows)}행 · **`WRC_KEY` {len(WRC_KEY)}열**) | "
        f"{' · '.join('`%s`' % c for c in WRC_KEY)} | `{fp['trades:WRC_KEY(post6)']}` | "
        "🔴 **이 축의 실제 의존** — `RNK_KEY` 에 없는 **`fill_n`·`open_ended`·`fill_level`·`preset`·"
        "`prog_ver`** 를 덮는다(분모를 정하는 열이다) |")
    say(f"| `ledger_legs.csv` **판독 필드 지문**(post6 {len(p6_legs)}레그 · `LEG_KEY` 4열) | "
        f"{' · '.join('`%s`' % c for c in LEG_KEY)} | `{fp['legs:LEG_KEY(post6)']}` | "
        "🔴 `read_ledger` 가 읽는 **전부** |")
    say()
    say("- 🔴 **`narrative` 는 어느 지문에도 «없다»** ⇒ 그 열의 정정으로 이 표는 **움직이지 않는다**. "
        "그게 이 표를 통째 md5 에서 바꾼 이유다.")
    say("- ⚠️ **`RNK_KEY` 하나만 박으면 이 축의 가드가 약해진다** — `fill_n`(분모 정의) · "
        "`open_ended`(민감도 축)가 그 7열에 «없다». 그래서 **두 지문을 다 박았다**. "
        "🔑 ***남의 지문 정의를 그대로 쓰는 것과 «내 의존»을 덮는 것은 다른 일이다 — 둘 다 해야 한다.***")
    say("- 🟢 **prefix 가 «양방향» 가드다**: 과거 행이 움직이면 prefix 가 깨지고(위 대조), "
        "post6 행이 움직이면 판독 필드 지문이 깨진다. 통째 md5 는 **둘을 구분하지 못한다**.")

    # 커밋 대비 byte 동일 — 제3자(커밋) 기준
    clean_expl = git_rc("diff", "--quiet", "HEAD", "--", "RESULTS_WRC_EXPLORE.md", "wrc_explore") == 0
    st = git("status", "--porcelain", "--", "RESULTS_WRC_EXPLORE.md", "wrc_explore",
             "ledger_trades.csv", "ledger_legs.csv", "run_wrc_explore.py")
    say(f"- 🟢 **커밋 대비 byte 동일**(`git diff --quiet HEAD -- RESULTS_WRC_EXPLORE.md wrc_explore`) = "
        f"{'✅ **동일**' if clean_expl else '🔴 **다르다**'} — "
        "md5 표에 «없는» 건별 JSON 11개까지 포함해 한 번에 재는 검사다"
        "(동결 표는 `bands.tsv`·`controls_summary.json`·`universe_snapshot.json`·`remeasure_2_5.json` "
        "4개만 적었다 — 그 공백을 이 줄이 덮는다).")
    say("- `git status --porcelain` (이 축이 만지는 5개 경로):\n")
    say("```")
    for ln in (st.splitlines() or ["(전부 커밋과 동일)"]):
        say(ln)
    say("```")
    say()
    say("#### 0-2. 🔴 `run_wrc_explore.py` 에 넣은 **post6 «명시» 제외 필터** (이 회차의 유일한 기존 파일 수정)\n")
    say("**증상**: 원장 append «후» 탐색 스크립트를 그대로 돌리면 `build_cases` 가 post6 5건을 "
        "**판정 분모에 그대로 통과**시킨다 — 실측 **원장 50 → 62행 · `exact` 18 → 28 · 분모 10 → 15**.")
    say("**원인**: `POST_LABEL` 은 날짜에 «이름을 붙이는 맵»일 뿐 **필터가 아니었다**. "
        "탐색 회차에는 post6 이 존재하지 않아 **증상이 없었을 뿐**이다.")
    say("**수정**(`main()` 안 · 5줄): `tr = [r for r in tr if r[\"post_date\"] <= \"2026-08-29\"]` "
        "(= post5 발행일까지 · post1~3 은 §1-4 의 「원장 전 글 50행」에 포함되므로 남긴다).")
    say("🔑 ***「그 날짜가 아직 없으니 안 걸린다」는 필터가 아니다 — 날짜는 오고, 그때 조용히 들어온다.***")
    say("🔴 이 수정으로 `run_wrc_explore.py` 의 md5 가 동결 표와 달라졌다(위 표) ⇒ "
        "**`regen_gate.py` 의 `RESULTS_WRC_EXPLORE.md` ↔ `run_wrc_explore.py` 쌍은 재기준선이 필요하다** — "
        "그 판단은 이 축이 «하지 않는다»(최종 레인 · `regen_gate.py` 는 이 회차의 수정 금지 대상).")
    say()

    # ══ §1. 판정 분모 게이트 (§6-1 `WRC-R11`) ═══════════════════════════════
    tr, legs_map = read_ledger()
    cases_all = build_cases(tr, legs_map)
    for c in cases_all:
        if c["log_no"] == POST_LOG:
            c["post"] = LABEL
            c["code"] = CODES6.get(c["name"])
    p6 = [c for c in cases_all if c["log_no"] == POST_LOG]
    # 🔴 탐색 «판정 분모» 10건 «만» 이다(§6-1 게이트를 통과한 건) — post4·post5 의 «전 행»이 아니다.
    #    전 행으로 두면 §7-1 이 동결본과 «다른 분모»를 재게 되어 병기가 성립하지 않는다.
    explore_cases = [c for c in cases_all if c["post"] in ("post4", "post5") and c["gate"]]
    gate_in = [c for c in p6 if c["gate"]]
    exact6 = [c for c in p6 if c["prec"] == "exact"]

    say("---\n")
    say("## §1. 판정 분모 — `WRC-R11`(§6-1) 게이트 **재측정**\n")
    say("**분모 정의(동결)** = `reg_date_precision = exact` ∧ `fill_n ≥ 2` ∧ **서로 «다른» 값의 레그 ≥ 3**. "
        "🔴 원장을 «다시 세어» 만든다 — 인테이크 표를 복사하지 않는다.\n")
    say("| # | 종목 | 코드 | 등록일 | `prec` | `fill_level`/`fill_n` | 레그 | 서로 다른 값 | "
        "`open_ended` | **분모?** | 밖이면 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in p6:
        why = ""
        if not c["gate"]:
            if c["prec"] != "exact":
                why = "`prec ≠ exact`(후속 건 — PD-2)"
            elif c["fill_n"] is None:
                why = "`fill_n` 빈칸 ⇒ `N` 미상 ⇒ `A1` 정의 불가(§2-7)"
            elif c["fill_n"] < 2:
                why = "`fill_n = 1`(`first_only`) — 다차수가 아니다"
            else:
                why = f"서로 다른 값 레그 **{c['distinct']} < 3**(`REC-Z4` 차용)"
        say(f"| {c['item']} | {c['name']} | {c['code'] or '⛔'} | {c['reg'] or '—'} | `{c['prec']}` | "
            f"`{c['fill_level']}`/{c['fill_n'] if c['fill_n'] is not None else '—'} | {c['n_legs']} | "
            f"{c['distinct']} | {c['open_ended']} | {'🟢 **안**' if c['gate'] else '밖'} | {why} |")
    say()
    got_names = [c["name"] for c in gate_in]
    match_intake = sorted(got_names) == sorted(INTAKE_DENOM_PRED)
    say(f"- ⇒ **판정 분모 = {len(gate_in)}건**: {', '.join(got_names)}")
    say(f"- 🔴 **인테이크 «예측»과 대조**(`INTAKE_2026-09-04_post6.md` §5 WRC 행 = "
        f"{', '.join(INTAKE_DENOM_PRED)} = **{len(INTAKE_DENOM_PRED)}건**) ⇒ "
        f"**{'✅ 일치' if match_intake else '🔴 불일치 — 실측을 쓴다'}** "
        "(인테이크는 계산 «전»에 적힌 문서다 ⇒ 이 일치는 **분모가 값을 보고 정해지지 않았다**는 증거다).")
    say(f"- 게이트 통과율(post6 `exact` 대비) = **{len(gate_in)}/{len(exact6)} = "
        f"{100*len(gate_in)/len(exact6):.1f}%** (§4-6 이 분모 정의의 일부로 따로 인쇄하라 한 값 · "
        "탐색 회차 값은 10/18 = 55.6%)")
    say(f"- **최소 표본 게이트**: 판정 분모 {len(gate_in)}건 "
        f"{'≥' if len(gate_in) >= 3 else '<'} **3건**(`PREREG_SELECTION.md` §7) ⇒ "
        f"{'🟢 **게이트 열림 — 이 글에서 판정한다**' if len(gate_in) >= 3 else '⛔ 미룬다'}")
    say(f"- `open_ended = 1` 이 분모 **{sum(c['open_ended'] for c in gate_in)}/{len(gate_in)}**"
        f"({', '.join(c['name'] for c in gate_in if c['open_ended'])}) — "
        "시퀀스가 열려 제약이 실제보다 «적다» ⇒ feasible 을 **넓히는** 방향(§9 · 증거력 약화).")
    say(f"- 재진입(PD-3): {' · '.join('%s flag %d' % (k, v) for k, v in PD3_FLAG.items())} — "
        f"🔴 **현대약품은 판정 분모 «밖»**(서로 다른 값 레그 2) ⇒ 이 축에서 다루는 재진입 건은 "
        f"**지투파워 1건**뿐이다(§8 민감도).")
    say(f"- `prog_ver` (§9 공변량) = post6 **{{{', '.join(sorted({c['prog_ver'] for c in p6}))}}}** · "
        f"원장 전체 **{{{', '.join(sorted({c['prog_ver'] for c in cases_all}))}}}** — "
        "부호가 버전별로 갈리면 통합 결론을 내지 않는다.")

    # ── 창·문맥 적재 ────────────────────────────────────────────────────────
    for c in gate_in:
        c["ctx"] = None
        c["nbar_pre"] = c["first_bar"] = c["win_lo"] = c["win_hi"] = None
        if not c["code"]:
            continue
        cur.execute("SELECT date, open, high, low, close FROM daily_prices "
                    "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date",
                    (c["code"], c["reg"], END))
        rows = cur.fetchall()
        if not rows:
            continue
        c["ctx"] = make_ctx(rows)
        cur.execute("SELECT count(*), min(date) FROM daily_prices WHERE stock_code=%s AND date < %s",
                    (c["code"], c["reg"]))
        c["nbar_pre"], c["first_bar"] = cur.fetchone()
        cur.execute("SELECT min(low), max(high) FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s", (c["code"], c["reg"], END))
        c["win_lo"], c["win_hi"] = cur.fetchone()

    # ══ §2. WRC-G1 — «가장 먼저» ═══════════════════════════════════════════
    for c in gate_in:
        c["a0"] = feasible_exact(c["ctx"]["rows"], c["legs"], "gross") if c["ctx"] else None
    say()
    say("---\n")
    say("## §2. `WRC-G1`(커버리지 가드) — **가장 먼저 계산한다** (§7-B #24)\n")
    say("**분자 = ①DB 종목코드 부재 + ④현행(`WRC-A0`) 해 0개** · 분모 = §1 의 판정 분모. "
        "🔴 ②(`fill_n` 빈칸)·③(서로 다른 값 레그 <3)은 **분모 정의의 일부라 분자가 될 수 없다**(§4-6 정정).\n")
    dbmiss = [c for c in gate_in if c["ctx"] is None]
    zero0 = [c for c in gate_in if c["ctx"] is not None and not c["a0"]]
    g1 = (len(dbmiss) + len(zero0)) / len(gate_in)
    say("| 글 | 판정 분모 | ① DB부재 | ④ 해 0개 | **`WRC-G1`** | 게이트(≥ 1/3) |")
    say("|---|---|---|---|---|---|")
    say(f"| **post6(판정)** | {len(gate_in)} | {len(dbmiss)} ({', '.join(c['name'] for c in dbmiss) or '—'}) | "
        f"{len(zero0)} ({', '.join(c['name'] for c in zero0) or '—'}) | "
        f"**{len(dbmiss)+len(zero0)}/{len(gate_in)} = {100*g1:.1f}%** | "
        f"{'🔴 **발동**' if g1 >= G1_THR else '🟢 **미발동**'} |")
    say(f"| 🔬 (탐색 인용 · 판정 아님) post4+post5 | 10 | 1 | 5 | **60.0%** | 🔴 발동 |")
    say()
    say(f"- **문턱 `1/3` = {G1_THR:.4f}** (`RESULTS_RECONSTRUCT_POST4.md` §6 `REC-Y3` «차용» · "
        "커버리지에 대해 검증된 적 없다는 고지 승계). 실측 **{:.4f}** ⇒ {}".format(
            g1, "🔴 **발동 — 판정 표기는 ⛔**" if g1 >= G1_THR else "🟢 **미발동 — 판정을 낸다**"))
    say("- 🔴 **편향 방향 신고**(§4-6 승계): ①은 신규 상장주에 몰리고 ④는 «레그 간격이 촘촘한 건»에 몰린다 "
        "⇒ ***측정 불가는 무작위가 아니다.*** ④는 §2-4 의 정리로 **계산 «전»에 확정**되는 부류이며 "
        "그래도 분자에 넣어 센다(빼면 커버리지가 좋아 보인다).")
    if g1 >= G1_THR:
        say("- 🔴🔴 **문언 대조·자기신고**: §4-6·§7-B #24 는 *「1/3 이상이면 나머지 계산을 «돌리지 않는다»」* 다. "
            "이 실행은 **관리자 지시로 나머지를 «계산하되 판정 표기를 ⛔»** 로 둔다. "
            "⇒ ***아래 값은 전부 «관측»이며 어떤 지지·불성립도 «선언하지 않는다».*** "
            "문턱 `1/3` 을 올려 여는 것은 어느 경우에도 금지다.")
    else:
        say("- 🟢 **게이트가 열렸다** — 탐색 표본(60.0%)과 갈린다. `WRC-G1` 은 죽은 가드가 아니었다"
            "(§7-C 4번의 열림 조건 = 「그 글의 분모에서 해 있는 건이 2/3 초과」).")

    # ══ §3. 건별 A0 / A1 / A3 · B1 ═════════════════════════════════════════
    for c in gate_in:
        c["a1"] = c["a3"] = c["a3b"] = c["bands"] = None
        if not c["ctx"] or not c["a0"]:
            continue
        c["a1"] = a1_solve(c["ctx"], c["fill_n"], c["a0"], cross=True)
        c["a3"] = a3_set(c["ctx"], c["a0"])
        c["a3b"] = a3_bands(c["ctx"], c["fill_n"])
        c["bands"] = bands_from_ext(c["a1"]["ext"], c["ctx"]) if (c["a1"] and c["a1"]["ext"]) else None
    say()
    say("---\n")
    say("## §3. 건별 `WRC-A0`(기준선) · `A1`(주 모델) · `A3`(무정보 상한) 와 `WRC-B1`\n")
    say("`m(·)` = feasible `P` 집합의 **측도(원)** — 🔑 *「범위」가 아니라 「측도」*"
        "(`RESULTS_RECONSTRUCT_POST5.md` §1 B4 승계).\n")
    say("| 종목 | `N` | 레그 | 창 봉수(등록일 «포함») | `G_win` | 격자 연속 | **`m(A0)`** | "
        "**`m(A1)`** | **`m(A3)`** | **`A1` 성립?** | `A1` 해 개수 | **`B1` 축소율(A1)** | 축소율(A3) |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    b1_bad, a1_killed = [], []
    for c in gate_in:
        if not c["ctx"]:
            say(f"| {c['name']} | {c['fill_n']} | {c['n_legs']} | ⛔ **DB 부재** | — | — | — | — | — | ⛔ | — | ⛔ | ⛔ |")
            continue
        ctx = c["ctx"]
        if not c["a0"]:
            say(f"| {c['name']} | {c['fill_n']} | {c['n_legs']} | {ctx['nbar_inc']} | {len(ctx['U'])} | "
                f"{'연속' if ctx['contiguous'] else '불연속'} | **0.00** | **0.00** | **0.00** | "
                "⛔ (`A0` 가 ∅) | 0 | ⛔ **정의 불가**(`m(A0)=0`) | ⛔ |")
            continue
        m0, m3, m1 = iv_measure(c["a0"]), iv_measure(c["a3"]), 0.0
        r1, r3 = 1 - m1 / m0, 1 - m3 / m0
        if r1 < -1e-12 or r3 < -1e-12:
            b1_bad.append(c["name"])
        ok1 = bool(c["a1"] and c["a1"]["feasible"])
        if not ok1:
            a1_killed.append(c["name"])
        say(f"| {c['name']} | {c['fill_n']} | {c['n_legs']} | {ctx['nbar_inc']} | {len(ctx['U'])} | "
            f"{'연속' if ctx['contiguous'] else '불연속'} | **{m0:,.2f}원** | **{m1:,.2f}원** | "
            f"**{m3:,.2f}원** | {'🟢 성립' if ok1 else '🔴 **∅**'} | "
            f"{c['a1']['n_means'] if c['a1'] else 0} | **{r1:.4f}** | {r3:.4f} |")
    say()
    band_cases = [c for c in gate_in if c.get("bands")]
    say(f"- 🔴 **`A0` 는 있는데 `A1` 이 «비는» 건 = {len(a1_killed)}건** "
        f"({', '.join(a1_killed) or '없음'}) — 탐색 회차의 §8 #0 과 같은 기전"
        "(`A1` 의 `P` 후보는 간격 `tick/N` 의 «이산점»이고 `A0` 는 성긴 «좁은 조각»이라 "
        "어긋나면 통째로 사라진다). 🔴 **이 손실은 `WRC-G1` 에 «안 잡힌다»** — G1 사유 ④ 는 "
        "«현행(`A0`) 해 0개»로 정의돼 있다.")
    say(f"- ⇒ **`A1` 로 밴드가 나온 건 = {len(band_cases)}/{len(gate_in)}건** "
        f"({', '.join(c['name'] for c in band_cases) or '없음'})")
    say("- 🔴 **`m(A1) = 0` 은 버그가 아니라 정의의 귀결**이다(격자값 `N` 개의 산술평균 ⇒ 유한 점집합 ⇒ "
        "르베그 측도 정확히 0) ⇒ `WRC-B1` 축소율은 `m(A0) > 0` 인 전 건에서 **1.0000 항등**이다. "
        "🔑 ***항등식은 어떤 가설도 시험하지 않는다*** — §4-4 가 예고한 대로 `B1` 은 «지지»를 만들지 않고, "
        "정리를 실제로 시험하는 것은 §9 의 `WRC-X1` 1·2번이다.")
    if b1_bad:
        say(f"- 🔴🔴 **`WRC-X1` 발동: 축소율 < 0 인 건 {b1_bad}** ⇒ 이 산출물은 **무효**다.")

    # ══ §4. REC-Z3 앵커 (판정 분모 전건) ═══════════════════════════════════
    say()
    say("---\n")
    say("## §4. `REC-Z3` 앵커 의무 인쇄 — **판정 분모 «전건»**\n")
    say("`H` = **등록일 고가**(§2-1 (라) · `PREREG_HDR.md`:25 정의) · `bₖ = 1 − Pₖ/H`. "
        "🔴 밴드가 나온 건만이 아니라 **분모 전건**에 건다(해가 없어도 앵커는 정의된다).\n")
    say("| 종목 | 등록일 | 창 첫 봉 | 첫 봉 = 등록일? | `H`(등록일 고가) | 창 최저 저가 | 창 최고가 | "
        "**`H < 창 최고가`?** | `H`/창최고 | `A1` 밴드 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    z3_bad, z3_den = [], []
    for c in gate_in:
        if not c["ctx"]:
            say(f"| {c['name']} | {c['reg']} | ⛔ | ⛔ | ⛔ **DB 부재** | ⛔ | ⛔ | ⛔ **측정 불가** | — | ⛔ |")
            continue
        z3_den.append(c)
        bad = c["ctx"]["h0"] < c["win_hi"]
        if bad:
            z3_bad.append(c["name"])
        same = c["ctx"]["d0"] == c["reg"]
        say(f"| {c['name']} | {c['reg']} | {c['ctx']['d0']} | {'✅' if same else '🔴 **아니다**'} | "
            f"{c['ctx']['h0']:,.0f} | {c['win_lo']:,.0f} | {c['win_hi']:,.0f} | "
            f"{'🔴 **예**' if bad else '아니오'} | {100*c['ctx']['h0']/c['win_hi']:.1f}% | "
            f"{'있음' if c.get('bands') else '없음'} |")
    z3_rate = len(z3_bad) / len(z3_den) if z3_den else float("nan")
    say()
    say(f"- 🔴🔴 **실측 = {len(z3_bad)}/{len(z3_den)} = {100*z3_rate:.1f}%** "
        f"(분모 = 판정 분모 {len(gate_in)}건 중 DB 봉이 있는 {len(z3_den)}건) · "
        f"해당 건: {', '.join(z3_bad) or '없음'}")
    say(f"- **문턱 = ≥ 1/2**(`RESULTS_RECONSTRUCT_POST5.md` §9 `REC-Z3` · `PREREG_POST6.md` §2-6 재동결) ⇒ "
        f"**{'🔴🔴 **발동**' if z3_rate >= 0.5 else '🟢 미발동'}**")
    if z3_rate >= 0.5:
        say("- 🔴🔴 **문언 그대로 적는다**(`PREREG_POST6.md` §2-6 · `PREREG_WEIGHTED_RECON.md` §9): "
            "*「`H` < 창 최고가 인 건의 비율이 **≥ 1/2 이면 `PREREG_HDR` 의 `h` 축과 "
            "`PREREG_LADDER_TRANCHE` 의 `DD` 축이 «같은 앵커 가정»에서 함께 무너진다** ⇒ "
            "앵커 재설계를 사전등록한다」* + *「6번째 글에서 한 건이라도 더 나오면 **앵커 재설계 "
            "사전등록이 의무 발생**한다」* + `WRC-` 축 조항 *「의무 발생 시 **이 축도 함께 멈춘다**」*(§2-1 (라)·§9).")
        say("  ⇒ ⛔ **`WRC-P1` 판정을 «선언하지 않는다». 앵커 재설계 사전등록 «전»에는 이 축의 "
            "`bₖ` 를 어떤 결론의 근거로도 쓰지 않는다.**")
        say("  ⚠️ **분모 고지**: 이 비율의 분모는 **`WRC-` 판정 분모**다. `REC-` 축(`run_reconstruct_post6.py`)은 "
            "**다른 분모**(레그 ≥4 신규 건 등)로 같은 `REC-Z3` 를 잰다 ⇒ **두 수를 한 수로 합치지 말 것.** "
            "의무 발생 여부는 그쪽 산출물이 자기 분모로 따로 판정한다.")
    say("- 🔴 그런 건에서 `bₖ` 는 「등록일 고점 대비 낙폭」이라는 **뜻을 잃는다**(`Pₖ > H` 가 가능해 "
        "`bₖ` 가 음수로 나온다). 🔑 *뜻이 흔들린 값은 넓은 폭보다 나쁘다 — 넓은 폭은 무정보이고 "
        "뜻이 흔들린 값은 «틀린 정보»다.*")
    say(f"- ⚠️ **탐색 회차 7/9 = 77.8%(창 `~2026-09-02`)와 «직접 비교 불가»** — 창이 다르고 "
        f"이 회차의 창은 종목마다 `[등록일, {END}]` 로 더 짧다(post6 등록일이 8월 하순~9월 초). "
        "창이 짧으면 창 최고가가 낮아져 이 비율은 **내려가는 방향**이다. ⇒ 잣대가 다른 두 수다.")

    # ══ §5. 밴드 bₖ ════════════════════════════════════════════════════════
    NOTE4 = [
        NOTATION_4[0],
        "2. 🔴 **「검정 안 된 «후보»다 — `WRC-P1` 판정 전이거나 강등 상태면 그 사실을 이 줄에 적는다」** → "
        + ("🔴 **이 회차는 `WRC-G1` 발동(측정 불가 ≥ 1/3)으로 «판정 표기 ⛔»**이다."
           if g1 >= G1_THR else "🟢 이 회차는 `WRC-G1` 미발동이라 판정을 낸다.")
        + (" 🔴 **그리고 `REC-Z3` 앵커가 ≥ 1/2 로 발동해 앵커 재설계 의무가 걸렸다 ⇒ 이 축도 함께 멈춘다.**"
           if z3_rate >= 0.5 else ""),
        NOTATION_4[2],
        NOTATION_4[3],
    ]
    say()
    say("---\n")
    say("## §5. 차수별 밴드 `bₖ = 1 − Pₖ/H` — `WRC-P1`\n")
    say("⚠️ 이 표의 분모는 §4 의 분모가 «아니다» — `A1` 이 해를 남긴 건뿐이고 그 배제는 무작위가 아니다.\n")
    say("| 종목 | `N` | `H` | `H < 창최고`? | 차수 | `Pₖ` 범위 | **`bₖ` 밴드** | **폭(%p)** | 폭(호가 칸) |")
    say("|---|---|---|---|---|---|---|---|---|")
    for c in band_cases:
        ctx = c["ctx"]
        bad = ctx["h0"] < c["win_hi"]
        for k, b in enumerate(c["bands"], start=1):
            head_ = (f"| {c['name']} | {c['fill_n']} | {ctx['h0']:,.0f} | "
                     f"{'🔴 **예**' if bad else '아니오'} " if k == 1 else "|  |  |  |  ")
            say(f"{head_}| {k}차 | {b['pmin']:,.0f}~{b['pmax']:,.0f} | "
                f"**{b['b_lo']:+.2f}% ~ {b['b_hi']:+.2f}%** | **{b['w']:.2f}%p** | {b['cells']:.1f}칸 |")
    if not band_cases:
        say("| — | — | — | — | ⛔ **밴드가 나온 건 0** | — | — | — | — |")
    say()
    for ln in NOTE4:
        say(ln)
    say()
    say("### 5-1. 건별 폭 중앙값과 `WRC-P1` 문턱 대조\n")
    say(f"통계량 = 건별 `N` 개 차수의 폭 **중앙값** · 문턱 **< {BAND_THR:.0f}%p** "
        "(`RESULTS_RECONSTRUCT_POST4.md` §6 `REC-Y1` «차용» — 🔴 그 값은 **평단 `b₁` 의 폭**을 "
        "재던 것이고 여기서는 **차수별 `bₖ`** 를 잰다).\n")
    say("| 종목 | 차수 수 | 중앙값 관용구 | **폭 중앙값** | 최소 폭 | 최대 폭 | < 3%p |")
    say("|---|---|---|---|---|---|---|")
    narrow_n = meas_n = 0
    for c in band_cases:
        ws = [b["w"] for b in c["bands"]]
        m = med(ws)
        meas_n += 1
        narrow_n += int(m < BAND_THR)
        say(f"| {c['name']} | {len(ws)} | {med_note(len(ws))} | **{m:.2f}%p** | {min(ws):.2f}%p | "
            f"{max(ws):.2f}%p | {'성립' if m < BAND_THR else '🔴 위반'} |")
    if not band_cases:
        say("| ⛔ 측정 가능 0건 | — | — | — | — | — | — |")
    need = math.ceil((meas_n + 1) / 2) if meas_n else 0
    allw = [b["w"] for c in band_cases for b in c["bands"]]
    say()
    say(f"- 측정 가능 **{meas_n}건** 중 폭 중앙값 < {BAND_THR:.0f}%p 인 건 **{narrow_n}건** · "
        f"「과반」 = `⌈(n+1)/2⌉` = **{need}건**")
    if g1 >= G1_THR or z3_rate >= 0.5 or meas_n == 0:
        why = []
        if g1 >= G1_THR:
            why.append("`WRC-G1` 발동")
        if z3_rate >= 0.5:
            why.append("`REC-Z3` 앵커 의무 발생")
        if meas_n == 0:
            why.append("측정 가능 0건")
        say(f"- ⛔ **`WRC-P1` 판정 = 「판정 불가」** — 사유: {' · '.join(why)}. "
            "***「못 좁힌다」가 아니라 「못 쟀다」다***(§7-C 4번: 둘은 다른 문장이다).")
    else:
        say(f"- **`WRC-P1`** = {narrow_n}/{meas_n} {'≥' if narrow_n >= need else '<'} {need} ⇒ "
            f"{'🟢 문턱 충족(단 `N1`·`N2` AND 뒤에만 지지로 인용)' if narrow_n >= need else '🔴 문턱 미달'}")
    if allw:
        say(f"- 🔴 **죽은 가드 실측 점검(§7-B #14)**: 관측된 «전 건 전 차수» 폭 최소 = **{min(allw):.2f}%p** · "
            f"최대 = **{max(allw):.2f}%p** ⇒ 3%p 는 이 표본에서 "
            f"**{'«달성 가능»하다' if min(allw) < BAND_THR else '«달성되지 않았다»'}**. "
            "🔴 **문턱을 3%p 에서 올리는 것은 어느 경우에도 금지**다(§4-1).")
    else:
        say("- 🔴 **죽은 가드 실측 점검(§7-B #14)**: 측정 가능한 밴드가 **0건**이라 3%p 의 달성 가능성 "
            "자체를 «못 쟀다».")
    say()
    say("### 5-2. `WRC-A3` 「무정보 상한」 (§2-6 `WRC-R4` — **지지로 인용 금지**)\n")
    say("| 종목 | 차수 | `A3` `Pₖ` 상한구간 | `A3` 밴드 폭(%p) | (대조) `A1` 폭 | `A1`/`A3` |")
    say("|---|---|---|---|---|---|")
    for c in band_cases:
        if not c.get("a3b"):
            continue
        H = c["ctx"]["h0"]
        for k, ((lo3, hi3), b) in enumerate(zip(c["a3b"], c["bands"]), start=1):
            w3 = 100 * (hi3 - lo3) / H
            say(f"| {c['name'] if k == 1 else ''} | {k}차 | {lo3:,.0f}~{hi3:,.0f} | {w3:.2f}%p | "
                f"{b['w']:.2f}%p | **{(b['w']/w3) if w3 else float('nan'):.3f}** |")
    if not band_cases:
        say("| ⛔ 해당 건 0 | — | — | — | — | — |")
    say()
    say("- 🔴 `A3` 는 가중치가 자유라 밴드가 사실상 격자 전체다 — **`WRC-P1` 의 분자·분모에 넣지 않는다**. "
        "쓸모는 *「`A1` 이 얼마나 좁혔는가」의 «분모»*뿐이며 **포함관계 방향의 «상한»**이다.")
    for ln in NOTE4:
        say(ln)

    # ══ §6. 대조군 ═════════════════════════════════════════════════════════
    say()
    say("---\n")
    say("## §6. `WRC-A4` 대조군 — `WRC-N1`(성립률) · `WRC-N2`(좁은 밴드율)\n")
    cur.execute("SELECT DISTINCT stock_code FROM daily_prices WHERE stock_code !~ '^[0-9]' ORDER BY 1")
    nonnum = [r[0] for r in cur.fetchall()]
    final_pseudo = sorted(set(PSEUDO) | set(nonnum))
    say("### 6-0. 의사티커 제외 목록 (§7-B #18 승계 · 이 스냅샷에서 재측정)\n")
    say("| 출처 | 개수 | 목록 |")
    say("|---|---|---|")
    say(f"| `run_selection.py` `PSEUDO`(**import**) | {len(PSEUDO)} | {', '.join('`%s`' % p for p in PSEUDO)} |")
    say(f"| DB 실측(숫자로 시작하지 않는 종목코드 전수) | {len(nonnum)} | {', '.join('`%s`' % p for p in nonnum)} |")
    say(f"| ⇒ **최종(코드 ∪ DB)** | **{len(final_pseudo)}** | {', '.join('`%s`' % p for p in final_pseudo)} |")
    say()
    dates = sorted({c["reg"] for c in gate_in})
    universe = {}
    for d in dates:
        cur.execute("SELECT stock_code FROM daily_prices WHERE date=%s AND market_cap IS NOT NULL "
                    "AND market_cap > 0 AND close > 0 AND NOT (stock_code = ANY(%s)) ORDER BY 1",
                    (d, final_pseudo))
        universe[d] = [r[0] for r in cur.fetchall()]
    uni_sha = {d: sha_list(v) for d, v in universe.items()}
    say("### 6-1. 유니버스 스냅샷 (§7-B #23 · `PREREG_RANKING.md` §2-1 판정 유니버스 승계)\n")
    say("| 등록일 | 종목수 | sha256(정렬 목록) 앞 16 |")
    say("|---|---|---|")
    for d in dates:
        say(f"| {d} | {len(universe[d]):,} | `{uni_sha[d][:16]}` |")
    say()
    say(f"- 목록 전체와 sha256 을 `wrc_post6/universe_snapshot.json` 에 박았다(DB 스냅샷 `{END}`).")

    t0 = time.time()
    cur.execute("SELECT stock_code, date, open, high, low, close FROM daily_prices "
                "WHERE date BETWEEN %s AND %s", (min(dates), END))
    byc: dict[str, list] = {}
    for sc, d, o, h, l, cl in cur.fetchall():
        byc.setdefault(sc, []).append((d, o, h, l, cl))
    for sc in byc:
        byc[sc].sort()
    t_load = time.time() - t0

    # 🔴 `run_wrc_explore.main()` 의 지역 함수 `ctx_for`·`evaluate` 를 **같은 본문으로** 재조립한다
    #    (import 불가) — 새 정의가 아니며 캐시 키에 레그 «순서»를 그대로 넣는 규약도 그대로다.
    def ctx_for(code, d0):
        rows = [r for r in byc.get(code, ()) if r[0] >= d0]
        return make_ctx(rows) if rows else None

    EVAL_CACHE: dict = {}
    nodata = [0]

    def evaluate(code, d0, legs, N, kind="gross"):
        key = (code, d0, tuple(legs), N, kind)
        r = EVAL_CACHE.get(key)
        if r is not None:
            return r
        ctx = ctx_for(code, d0)
        if ctx is None:
            nodata[0] += 1
            r = (None, None, None)
        else:
            iv = feasible_exact(ctx["rows"], legs, kind)
            if not iv:
                r = (False, False, None)
            else:
                sol = a1_solve(ctx, N, iv)
                if not sol or not sol["feasible"] or not sol["ext"]:
                    r = (True, False, None)
                else:
                    bs = bands_from_ext(sol["ext"], ctx)
                    r = (True, True, med([b["w"] for b in bs]))
        EVAL_CACHE[key] = r
        return r

    rng = np.random.default_rng(SEED)
    say()
    say("### 6-2. 대조군 명세 (`WRC-R10` §4-2 + `FREEZE_WRC_2026-09-02.md` §3)\n")
    say("| 갈래 | 방법 | 크기 정합 | 지위 |")
    say("|---|---|---|---|")
    say(f"| **(가) 무작위 종목** | 같은 등록일·같은 `N`·같은 레그 «값»을 그날 유니버스의 무작위 종목 "
        f"가격열에 건다 | 같은 날짜 집합 · 같은 건수(**{len(gate_in)}건/회**) | 🟢 **판별력 검정 = 이 갈래 «단독»** |")
    say("| (나) 셔플 레그 | 같은 종목·같은 창에 레그 «순서»를 셔플 | 〃 | ⛔ **무정보 강등**"
        "(`FREEZE_WRC_2026-09-02.md` §3 확정) — **대조군 자격 없음 · 이 회차는 돌리지 않는다** |")
    say()
    say("- 🔴 **(나) 를 «돌리지 않는» 근거**(동결 §3): `feasible_exact` 는 레그별 구간의 **교집합**이고 "
        "교집합은 **순서 불변**이며, `WRC-A1` 의 (가)(나)(다)(라)는 «매수» 사다리에만 걸려 "
        "**레그 순서를 참조하지 않는다** ⇒ 통계량이 셔플에 **항등적으로 불변**이다. "
        "재명세는 **별도 사전등록 개정**이며 이 문서 안에서 새 대조군을 정의하지 않는다.")
    say(f"- 반복 **{NREP:,}회** · 시드 `{SEED}`(`numpy.random.default_rng`) · "
        "레메디형(코드 부재)은 이번 분모에 **0건**이라 (가)의 분모 갈림이 없다.")

    t0 = time.time()
    ga_tot = ga_a0 = ga_feas = ga_narrow = 0
    ga_by_case = {c["name"]: [0, 0, 0, 0] for c in gate_in}
    ga_varies = {c["name"]: set() for c in gate_in}
    ga_codes = {c["name"]: set() for c in gate_in}
    uni_arr = {d: np.array(universe[d]) for d in dates}
    for _rep in range(NREP):
        for c in gate_in:
            arr = uni_arr[c["reg"]]
            code = str(arr[rng.integers(len(arr))])
            ok0, ok1, m = evaluate(code, c["reg"], c["legs"], c["fill_n"])
            ga_tot += 1
            k = c["name"]
            ga_by_case[k][2] += 1
            ga_varies[k].add((ok0, ok1, None if m is None else round(m, 6)))
            ga_codes[k].add(code)
            if ok0:
                ga_a0 += 1
                ga_by_case[k][0] += 1
            if ok1:
                ga_feas += 1
                ga_by_case[k][1] += 1
                if m is not None and m < BAND_THR:
                    ga_narrow += 1
                    ga_by_case[k][3] += 1
    t_ga = time.time() - t0
    ga_meas = ga_feas

    obs_tot = sum(1 for c in gate_in if c["ctx"])
    obs_a0 = sum(1 for c in gate_in if c["ctx"] and c["a0"])
    obs_feas = len(band_cases)
    n1_rate = ga_feas / ga_tot
    n2_rate = (ga_narrow / ga_meas) if ga_meas else float("nan")
    say()
    say("### 6-3. `WRC-N1` — feasible 성립률 (문턱 **≥ 50% ⇒ 「판별력 없음」 강등**)\n")
    say("🔴 **두 열로 나눠 인쇄한다** — `WRC-N1` 의 통계량은 **`A1` 성립률**이고 `A0` 성립률은 "
        "«그 앞 단계»라 참고로만 적는다(한 칸에 섞으면 「모델이 좁혔다」와 「창이 넓다」가 다시 붙는다).\n")
    say("| 갈래 | 분모(건·회) | `A0` 성립 | `A0` 성립률 | **`A1` 성립(=`WRC-N1`)** | **성립률** | 문턱 50% |")
    say("|---|---|---|---|---|---|---|")
    say(f"| **(가) 무작위 종목** | {ga_tot:,} | {ga_a0:,} | {100*ga_a0/ga_tot:.1f}% | {ga_feas:,} | "
        f"**{100*n1_rate:.1f}%** | {'🔴 **발동 — 강등**' if n1_rate >= N_THR else '🟢 미발동'} |")
    say("| (나) 셔플 레그 | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ **무정보** | ⛔ **대조군 자격 없음**(동결 §3) |")
    say(f"| (참고) 관측 — 같은 잣대 | {obs_tot} | {obs_a0} | {100*obs_a0/obs_tot:.1f}% | {obs_feas} | "
        f"**{100*obs_feas/obs_tot:.1f}%** | — |")
    say()
    say("| 종목 | (가) `A0` 성립률 | (가) **`A1` 성립률** | (가) 좁은밴드율 | 관측 `A0` | 관측 `A1` |")
    say("|---|---|---|---|---|---|")
    for c in gate_in:
        f0, f1, t_, nw = ga_by_case[c["name"]]
        o0 = "⛔ DB부재" if not c["ctx"] else ("성립" if c["a0"] else "🔴 해 0개")
        o1 = "⛔" if not c["ctx"] else ("성립" if c.get("bands") else "🔴 ∅")
        say(f"| {c['name']} | {100*f0/t_:.2f}% ({f0:,}) | **{100*f1/t_:.2f}%** ({f1:,}/{t_:,}) | "
            f"{('%.1f%%' % (100*nw/f1)) if f1 else '⛔ 분모 0'} | {o0} | {o1} |")
    say()
    say("### 6-4. `WRC-N2` — 대조군에서 `bₖ` 폭 중앙 < 3%p 인 비율 (문턱 ≥ 50% ⇒ 강등)\n")
    say("| 갈래 | 분모(= feasible 성립 건) | 좁은 밴드 | **비율** | 문턱 50% |")
    say("|---|---|---|---|---|")
    say(f"| (가) 무작위 종목 | {ga_meas:,} | {ga_narrow:,} | **{100*n2_rate:.1f}%** | "
        f"{'🔴 **발동 — 강등**' if ga_meas and n2_rate >= N_THR else '🟢 미발동'} |")
    say("| (나) 셔플 레그 | ⛔ | ⛔ | ⛔ **무정보** | ⛔ 동결 §3 |")
    say(f"| (참고) 관측 | {meas_n} | {narrow_n} | "
        f"**{(100*narrow_n/meas_n if meas_n else float('nan')):.1f}%** | — |")
    say()
    say("- 🔴 **분모를 명시한다** — `WRC-N2` 의 분모는 **feasible 이 성립한 대조군 건**이다"
        "(밴드는 해가 있어야 정의된다).")
    varies_a = sum(1 for v in ga_varies.values() if len(v) > 1)
    const_a = [k for k, v in ga_varies.items() if len(v) == 1]
    say(f"- 🟢 **`WRC-X1` 3번(대조군 상수 여부)**: (가) 갈래에서 건별로 «서로 다른» 종목 "
        f"{min(len(v) for v in ga_codes.values()):,}~{max(len(v) for v in ga_codes.values()):,}가지가 "
        f"뽑혔고, **결과가 갈리는 건 {varies_a}/{len(ga_varies)}** "
        f"(상수 건 {len(const_a)}: {', '.join(const_a) or '없음'} — 상수는 «무작위화 실패»가 아니라 "
        "그 레그 열이 어떤 종목에서도 성립하지 않는다는 뜻이며 **전 반복**에서 셌다).")

    # ══ §7. WRC-O1 ═════════════════════════════════════════════════════════
    say()
    say("---\n")
    say("## §7. `WRC-O1` — 탐색(post4·post5)과 판정(post6)을 **«항상» 나란히** (§4-5)\n")
    say("🔴 **탐색 성적은 판정 분모에 «넣지 않는다»**(`PREREG_POST6.md` §2-1 ③ 문형 승계). "
        "괴리가 판정을 가르면 **「탐색 편향 의심」**이라고 인쇄하고 **어느 쪽도 지지로 선언하지 않는다**.\n")
    say("| 통계량 | 🔬 탐색 — **동결 인용**(창 `~2026-09-02`) | **판정 — post6**(창 `~%s`) |" % END)
    say("|---|---|---|")
    say(f"| 판정 분모 | {EXPLORE_FROZEN['denominator']} | **{len(gate_in)}건** · "
        f"게이트 통과율 {len(gate_in)}/{len(exact6)} = {100*len(gate_in)/len(exact6):.1f}% |")
    say(f"| `WRC-G1` 커버리지 | {EXPLORE_FROZEN['G1']} | **{100*g1:.1f}%** ⇒ "
        f"{'🔴 발동' if g1 >= G1_THR else '🟢 미발동'} |")
    say(f"| `A0` 해 있는 건 | {EXPLORE_FROZEN['A0_feasible']} | **{obs_a0}/{obs_tot}건** |")
    say(f"| `A1` 밴드가 나온 건 | {EXPLORE_FROZEN['A1_bands']} | **{obs_feas}건** |")
    say(f"| 밴드 폭 | {EXPLORE_FROZEN['band_w']} | "
        f"**{('최소 %.2f%%p · 최대 %.2f%%p' % (min(allw), max(allw))) if allw else '⛔ 측정 0건'}** |")
    say(f"| `WRC-P1`(폭 중앙 < 3%p) | {EXPLORE_FROZEN['P1']} | **{narrow_n}/{meas_n}** "
        f"{'⛔ **판정 불가**' if (g1 >= G1_THR or z3_rate >= 0.5 or meas_n == 0) else ''} |")
    say(f"| `WRC-N1` | {EXPLORE_FROZEN['N1']} | (가) **{100*n1_rate:.1f}%** ⇒ "
        f"{'발동' if n1_rate >= N_THR else '미발동'} / (나) ⛔ |")
    say(f"| `WRC-N2` | {EXPLORE_FROZEN['N2']} | (가) **{100*n2_rate:.1f}%** ⇒ "
        f"{'발동' if ga_meas and n2_rate >= N_THR else '미발동'} / (나) ⛔ |")
    say(f"| `WRC-B1` 축소율 | {EXPLORE_FROZEN['B1']} | **전건 1.0000**(측도 잣대 항등) |")
    say(f"| `REC-Z3` 앵커 | {EXPLORE_FROZEN['Z3']} | **{len(z3_bad)}/{len(z3_den)} = {100*z3_rate:.1f}%** ⇒ "
        f"{'🔴 **≥ 1/2 발동**' if z3_rate >= 0.5 else '🟢 미발동'} |")
    say()
    say("### 7-1. 🔴 «같은 창»에서의 탐색 표본 재측정 — 창 효과와 표본 효과를 가른다\n")
    say("**왜**: 위 표의 탐색 열은 창 `~2026-09-02`, 판정 열은 창 `~%s` 다. 두 수를 나란히 두면 "
        "「표본이 달라서 갈렸다」와 「창이 달라서 갈렸다」가 붙는다. ⇒ **탐색 10건을 이 실행의 창으로 "
        "다시 재서** 세 번째 열로 둔다. 🔴 **이 열은 «판정 분모»가 아니다**(`WRC-O1` — 탐색은 탐색이다).\n"
        % END)
    say("🔴 **분모 = 탐색 회차의 «판정 분모» 10건**(§6-1 게이트 통과분) — post4·post5 의 전 행이 아니다.\n")
    say("| 글 | 종목 | `A0`(이 창) | `A1`(이 창) | 밴드 폭 중앙(이 창) | `H < 창최고`(이 창) |")
    say("|---|---|---|---|---|---|")
    ex_a0 = ex_a1 = ex_n = ex_z3 = 0
    ex_rows = []
    for c in explore_cases:
        code = CODEMAP.get(c["name"])
        if not code:
            say(f"| {c['post']} | {c['name']} | ⛔ DB 코드 부재 | ⛔ | ⛔ | ⛔ |")
            ex_rows.append(dict(post=c["post"], name=c["name"], code=None))
            continue
        cur.execute("SELECT date, open, high, low, close FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, c["reg"], END))
        rows = cur.fetchall()
        ctx = make_ctx(rows) if rows else None
        if ctx is None:
            say(f"| {c['post']} | {c['name']} | ⛔ 봉 없음 | ⛔ | ⛔ | ⛔ |")
            ex_rows.append(dict(post=c["post"], name=c["name"], code=code))
            continue
        ex_n += 1
        iv = feasible_exact(rows, c["legs"], "gross")
        sol = a1_solve(ctx, c["fill_n"], iv) if iv else None
        bs = bands_from_ext(sol["ext"], ctx) if (sol and sol.get("ext")) else None
        wm = med([b["w"] for b in bs]) if bs else None
        wh = max(r[2] for r in rows)
        z3 = ctx["h0"] < wh
        ex_a0 += int(bool(iv))
        ex_a1 += int(bool(bs))
        ex_z3 += int(z3)
        ex_rows.append(dict(post=c["post"], name=c["name"], code=code, a0=bool(iv), a1=bool(bs),
                            band_median_w=wm, anchor_below_window_high=bool(z3)))
        say(f"| {c['post']} | {c['name']} | {'성립' if iv else '🔴 해 0개'} | "
            f"{'성립' if bs else '🔴 ∅'} | {('%.2f%%p' % wm) if wm is not None else '—'} | "
            f"{'🔴 예' if z3 else '아니오'} |")
    say()
    say(f"- 같은 창(`~{END}`)에서 탐색 판정 분모 10건(DB 봉 있는 {ex_n}건): `A0` 성립 **{ex_a0}/{ex_n}** · `A1` 밴드 **{ex_a1}/{ex_n}** · "
        f"`H < 창최고` **{ex_z3}/{ex_n} = {100*ex_z3/ex_n:.1f}%**(동결 인용값 7/9 = 77.8% 와 "
        f"{'같다' if ex_z3 == 7 and ex_n == 9 else '**다르다 — 창이 2거래일 더 길어졌다**'})")
    say("- 🔴 **모호 지점 자기신고**: 「탐색값을 어느 창에서 인용할 것인가」에 대한 동결 문언이 «없다». "
        "⇒ **양쪽을 인쇄**하고(동결 인용 + 이 창 재측정) 어느 하나를 판정 근거로 고르지 않는다"
        "(`PREREG_POST6.md` §5-1-5 *「과거 산출물을 다시 재지 않는다」* 와 "
        "`run_selection_post6.py` 머리말 *「직전 문서 숫자를 그대로 옮겨 비교하지 않는다」* 가 "
        "**서로 다른 방향을 지시**한다 — 두 문언 다 인용하고 값은 둘 다 남긴다).")

    # ══ §8. WRC-V1 민감도 4축 ══════════════════════════════════════════════
    say()
    say("---\n")
    say("## §8. `WRC-V1` — 민감도 **4축을 «항상» 나란히** (갈리면 어느 쪽도 선언 금지)\n")
    say("### 8-1. 축① 잔차 문턱 `%s%%p`(판정) ↔ `%s%%p`(의무 민감도) — `REC-Z5`\n" % (THR[1], THR[0]))
    say("| 종목 | 최소잔차 적합 `P` | **최대 오차** | 진단 @%s | 진단 @%s | 갈리나 |" % (THR[0], THR[1]))
    say("|---|---|---|---|---|---|")
    thr_split = []
    for c in gate_in:
        if not c["ctx"] or c["a0"]:
            continue
        mr = min_residual(c["ctx"]["rows"], c["legs"], gross_ret)
        d = ["🔴 적합 실패" if mr is None else
             ("반올림으로 설명 가능" if mr[0] < t else "🔴 **모델이 틀렸다**") for t in THR]
        if mr is not None and d[0] != d[1]:
            thr_split.append(c["name"])
        say(f"| {c['name']} | {'—' if mr is None else f'{mr[1]:,.0f}'} | "
            f"{'—' if mr is None else f'**{mr[0]:.6f}%p**'} | {d[0]} | {d[1]} | "
            f"{'🔴 **예**' if mr is not None and d[0] != d[1] else '아니오'} |")
    if not zero0:
        say("| ⛔ 해 0개 건이 **0건** — 이 축은 대상이 없다 | — | — | — | — | 아니오 |")
    say()
    say(f"- 두 문턱에서 분류가 갈리는 건 **{len(thr_split)}건** ({', '.join(thr_split) or '없음'})")
    say("- 🔴 이 축은 `WRC-` 통계량을 «움직이지 않는다» — `WRC-G1`(①+④)·`B1`·밴드 폭은 잔차 문턱을 "
        "**입력으로 쓰지 않는다**(해 0개 여부는 정확 구간법이 정한다). 갈림은 **「해 0개의 «해석»」에만** 걸린다.")

    for c in gate_in:
        c["a0_net"] = feasible_exact(c["ctx"]["rows"], c["legs"], "net") if c["ctx"] else None
        c["bands_net"] = None
        if c["ctx"] and c["a0_net"]:
            s = a1_solve(c["ctx"], c["fill_n"], c["a0_net"])
            if s and s.get("ext"):
                c["bands_net"] = bands_from_ext(s["ext"], c["ctx"])
    net_zero = [c["name"] for c in gate_in if c["ctx"] and not c["a0_net"]]
    gross_zero = [c["name"] for c in gate_in if c["ctx"] and not c["a0"]]
    net_meas = [c for c in gate_in if c.get("bands_net")]
    net_narrow = sum(1 for c in net_meas if med([b["w"] for b in c["bands_net"]]) < BAND_THR)
    say()
    say("### 8-2. 축② 수수료 `gross`(판정) ↔ `net`(민감도) — `REC-Y4` 승계\n")
    say("| 잣대 | `A0` 해 0개 | 측정 가능(`A1` 밴드) | 폭 중앙 < 3%p 인 건 |")
    say("|---|---|---|---|")
    say(f"| **`gross`(판정)** | {len(gross_zero)}/{obs_tot} ({', '.join(gross_zero) or '없음'}) | "
        f"{meas_n} | {narrow_n} |")
    say(f"| `net`(민감도) | {len(net_zero)}/{obs_tot} ({', '.join(net_zero) or '없음'}) | "
        f"{len(net_meas)} | {net_narrow} |")
    say()
    say(f"- `A0` 해 0개 집합이 gross ↔ net 에서 "
        f"**{'같다' if set(net_zero) == set(gross_zero) else '🔴 다르다'}** · "
        f"측정 가능 분모 **{meas_n} → {len(net_meas)}** "
        f"({'이동 없음' if meas_n == len(net_meas) else '🔴 **이동했다**'})")

    say()
    say("### 8-3. 축③ 재진입·미완결 **포함**(판정) ↔ **제외**(민감도) — §2-7 `WRC-R5` · `WRC-D6`\n")
    oe = [c for c in gate_in if c["open_ended"] == 1]
    re_in = [c for c in gate_in if PD3_FLAG.get(c["name"]) is not None]
    say(f"- **미완결 `open_ended = 1`**: **{len(oe)}/{len(gate_in)}건** ({', '.join(c['name'] for c in oe)}) "
        "— 서술 기준(PD-4 「나머지 물량은 보유 중」)으로 원장에 인코딩된 값을 «읽기»만 했다.")
    say(f"- **재진입**: 판정 분모 안 **{len(re_in)}건** ({', '.join(c['name'] for c in re_in) or '없음'}) · "
        f"플래그 `P6-PRIOR_CYCLE_IN_WINDOW` = "
        f"{', '.join('%s %d' % (c['name'], PD3_FLAG[c['name']]) for c in re_in) or '—'} "
        "(현대약품 flag 0 은 **분모 밖**이라 이 축에 들어오지 않는다).")
    say()
    say("| 갈래 | 판정 분모 | `WRC-G1` | 측정 가능 | 폭 중앙 < 3%p | `REC-Z3` |")
    say("|---|---|---|---|---|---|")

    def slice_stats(sub):
        n = len(sub)
        if n == 0:
            return "—", "—", "—", None, "—"
        a = sum(1 for c in sub if c["ctx"] is None)
        z = sum(1 for c in sub if c["ctx"] is not None and not c["a0"])
        mm = [c for c in sub if c.get("bands")]
        nn = sum(1 for c in mm if med([b["w"] for b in c["bands"]]) < BAND_THR)
        r = (a + z) / n
        zd = [c for c in sub if c["ctx"]]
        zb = sum(1 for c in zd if c["ctx"]["h0"] < c["win_hi"])
        zr = (zb / len(zd)) if zd else None
        zs = f"{zb}/{len(zd)} = {100*zb/len(zd):.1f}%" + (" 🔴" if zd and zb / len(zd) >= 0.5 else " 🟢")
        return (f"{a+z}/{n} = {100*r:.1f}% · " + ("🔴 **발동**" if r >= G1_THR else "🟢 **미발동**"),
                f"{len(mm)}", f"{nn}", r, zs, zr)

    g1_slices = {}
    z3_slices = {}
    for lab, key, sub in [
            ("**포함(판정)**", "include", gate_in),
            ("제외 — `open_ended` 뺌", "no_oe", [c for c in gate_in if c["open_ended"] == 0]),
            ("제외 — 재진입 뺌", "no_re", [c for c in gate_in if PD3_FLAG.get(c["name"]) is None]),
            ("제외 — 둘 다 뺌", "no_both", [c for c in gate_in if c["open_ended"] == 0
                                       and PD3_FLAG.get(c["name"]) is None])]:
        gtxt, m_, nn, r, zs, zr = slice_stats(sub)
        g1_slices[key] = r
        z3_slices[key] = zr
        say(f"| {lab} | {len(sub)} | {gtxt} | {m_} | {nn} | {zs} |")
    say()
    flip = [k for k, r in g1_slices.items()
            if r is not None and k != "include" and (r >= G1_THR) != (g1_slices["include"] >= G1_THR)]
    z3_flip = [k for k, r in z3_slices.items()
               if r is not None and k != "include" and (r >= 0.5) != (z3_slices["include"] >= 0.5)]
    say(f"- 🔴🔴 **`REC-Z3` 앵커 판정이 뒤집히는 갈래 = {len(z3_flip)}개** ({', '.join(z3_flip) or '없음'}) — "
        f"포함(판정) 갈래 **{100*z3_slices['include']:.1f}%**"
        f"{'(미발동)' if z3_slices['include'] < 0.5 else '(발동)'} ↔ 제외 갈래에서 "
        f"**{'/'.join('%s %.0f%%' % (k, 100*z3_slices[k]) for k in ('no_oe', 'no_re', 'no_both') if z3_slices[k] is not None)}**. "
        "⇒ ***「앵커 재설계 의무가 발생하는가」가 민감도 갈래 선택에 종속된다.*** "
        "🔴 **동결 선택(«포함»이 판정)을 그대로 두고 제외 갈래로 의무를 «발생시키지도 «면제하지도» 않는다** — "
        "다만 `WRC-V1`(민감도 갈림 ⇒ 어느 쪽도 선언 금지)의 대상으로 여기 적어 둔다."
        if z3_flip else
        f"- 🟢 **`REC-Z3` 앵커 판정은 전 갈래에서 같다**(포함 {100*z3_slices['include']:.1f}%).")
    say(f"- 🔴 **`WRC-G1` 판정이 뒤집히는 갈래 = {len(flip)}개** ({', '.join(flip) or '없음'}) — "
        "`WRC-G1` 은 이 축을 «닫는» 게이트이므로 ***갈래를 고르는 것이 곧 「축을 여는가 닫는가」를 "
        "고르는 것***이다. 🔑 *「분모가 움직인다」로 적으면 이 사실이 안 보인다 — 움직이는 건 «결론»이다.*")
    say("- 🔴 **§2-7 `WRC-R5` 의 동결 선택(«포함»이 판정 · 제외는 민감도)을 그대로 둔다.** "
        "제외 갈래에서 가드가 미발동으로 뒤집혀도 판정 갈래를 바꾸지 않는다 — "
        "그건 ***가드를 통과하는 부분집합을 «골라» 축을 여는 동작***이다.")
    say("- 🔴 `open_ended` 의 방향: 제약이 실제보다 «적다» ⇒ feasible 을 **넓히는** 쪽이라 "
        "「해가 나왔다」의 증거력이 그만큼 약하다(§9 승계).")
    say()
    say("### 8-4. 축④ 모델 `WRC-A1`(판정) ↔ `WRC-A3`(무정보 상한) — §2-6\n")
    say("- §5-2 표가 그 병기다. `A3` 는 **지지로 인용 금지**이며 `WRC-P1` 의 분자·분모에 넣지 않는다.")
    say()
    say("### 8-5. 🔴 4축 종합\n")
    say("| 축 | 갈렸나 | 근거 |")
    say("|---|---|---|")
    say(f"| ① 잔차 문턱 | {'🔴 예' if thr_split else '아니오'} | §8-1 (단 `WRC-` 통계량엔 «입력이 아니다») |")
    ax2 = set(net_zero) != set(gross_zero) or net_narrow != narrow_n or len(net_meas) != meas_n
    say(f"| ② gross/net | {'🔴 예' if ax2 else '아니오'} | §8-2 |")
    ax3 = bool(flip or z3_flip)
    say(f"| ③ 재진입·미완결 | {'🔴 **예 — ' + (' · '.join(x for x in [('`WRC-G1`' if flip else ''), ('`REC-Z3`' if z3_flip else '')] if x)) + ' 판정이 뒤집힌다**' if ax3 else '아니오'} | §8-3 |")
    say("| ④ 모델 A1/A3 | 🔴 **항상 갈린다**(설계) | `A3` 는 무정보 상한이라 «비교 대상이 아니다» |")
    say()
    say("🔴 **`WRC-V1` 문언**: 하나라도 판정을 가르면 ⛔ **어느 쪽도 선언하지 않는다**. "
        "🔴 **`REC-Z5` 와의 차이 자기신고**(§4-8): `REC-Z5` 는 *「갈려도 0.022 로 «선다»」* 이고 "
        "`WRC-V1` 의 나머지 세 축은 *「갈리면 «안 선다»」* 다 — 한 산출물 안에 두 처리가 공존한다.")

    # ══ §9. WRC-X1 구현 점검 ═══════════════════════════════════════════════
    say()
    say("---\n")
    say("## §9. `WRC-X1` 구현 무효 조건 5개 (§4-7)\n")
    subs_ok = subs_n = plo_ok = plo_n = 0
    viol1 = []
    for c in gate_in:
        if not c["ctx"] or not c["a0"] or not c["a1"] or not c["a1"]["feasible"]:
            continue
        subs_n += 1
        ctx = c["ctx"]
        hull = (ctx["U"][0] >= ctx["lo"] and ctx["U"][-1] <= ctx["hi"])
        s_lo, s_hi = c["a1"]["srng"]
        p_lo = ctx["g"] * s_lo / c["fill_n"]
        p_hi = ctx["g"] * s_hi / c["fill_n"]
        inside = iv_has(c["a0"], p_lo) and iv_has(c["a0"], p_hi)
        if not (hull and inside):
            viol1.append(c["name"])
        subs_ok += int(hull and inside)
        plo_n += 1
        same = feasible_plo(ctx["rows"], c["legs"], ctx["lo"] * 0.7) == c["a0"]
        alt = _intersect(feasible_plo(ctx["rows"], c["legs"], ctx["U"][0]),
                         [(ctx["U"][0], ctx["U"][-1])])
        plo_ok += int(same and alt == c["a3"])
    n_viol2 = [c["name"] for c in gate_in
               if c["ctx"] and not c["a0"] and c.get("a1") and c["a1"]["feasible"]]
    cross = [(c["name"], c["a1"]["cross"]) for c in gate_in
             if c.get("a1") and c["a1"].get("cross") is not None]
    say(f"1. `feasible(A1) ⊄ feasible(A0)` 인 건: **{len(viol1)}건** ({', '.join(viol1) or '없음'}) — "
        f"산술(`[min G_win, max G_win] ⊆ [lo, hi] ⊂ [lo·0.7, hi]`) + `A1` 의 «실제» 최소·최대 평균을 "
        f"`iv_has` 로 **집합**에 대고 확인 ⇒ **{subs_ok}/{subs_n}건 통과**")
    say(f"   · 부수 점검: `leg_intervals`+`_merge`+`_intersect` 조립 경로가 `feasible_exact` 와 항등이고 "
        f"`A3` 를 «다른 경로»로도 재현하는가 ⇒ **{plo_ok}/{plo_n}건 일치**")
    say(f"2. `feasible(A0) = ∅` 인데 `feasible(A1) ≠ ∅` 인 건: **{len(n_viol2)}건** ⇒ "
        f"{'🟢 정리 위반 없음' if not n_viol2 else '🔴 **무효**'}")
    say(f"3. 대조군 상수 여부: (가) 갈림 **{varies_a}/{len(ga_varies)}** ⇒ "
        f"{'🟢 상수 아님' if varies_a else '🔴 **전건 상수**'} · (나)는 동결 §3 으로 **돌리지 않았다**"
        "(무정보 강등 — 이 회차는 그 조항을 «적용»할 대상이 없다)")
    say("4. `tick`/`grid_prices` 를 **import** 했다(표 재작성 0건) — `reconstruct_prices` 에서 직접.")
    say("5. `adj_factor` **산술 사용 0회** — 문자열은 이 고지문과 docstring 에만 등장한다.")
    say(f"- 🟢 **①(닫힌 형태) ↔ ②(비트셋 DP) 교차검증**: **{sum(1 for _, v in cross if v)}/{len(cross)}건 일치** "
        f"({', '.join(n for n, v in cross if v) or '없음'})")
    say(f"- ⇒ **`WRC-X1` 위반 합계 = {len(viol1) + len(n_viol2) + len(b1_bad)}건** "
        f"{'🟢 (산출물 유효)' if not (viol1 or n_viol2 or b1_bad) else '🔴 **산출물 무효**'}")

    # ══ §10. 봉수·코드 대조 ════════════════════════════════════════════════
    say()
    say("---\n")
    say("## §10. 봉수 표기(「등록일 «포함»/«직전»」)와 코드 대조 (`N8` 승계 · §5-2 3번)\n")
    say("| 종목 | 코드 | 등록일 | ① 등록일 «직전» 봉수(DB 전 이력) | ② **창 봉수(등록일 «포함»)** | "
        "③ DB 최초 봉 | 창 종료 |")
    say("|---|---|---|---|---|---|---|")
    for c in gate_in:
        if not c["ctx"]:
            say(f"| {c['name']} | {c['code'] or '⛔'} | {c['reg']} | ⛔ | ⛔ | ⛔ | — |")
            continue
        say(f"| {c['name']} | {c['code']} | {c['reg']} | {c['nbar_pre']:,} | "
            f"**{c['ctx']['nbar_inc']}** | {c['first_bar']} | {c['ctx']['dend']} |")
    say()
    say("- 🔑 *「직전」과 「포함」은 같은 사실의 두 표기다 — 반드시 붙인다*"
        "(`RESULTS_RECONSTRUCT_POST5.md` §10 `N8` 승계).")
    sel = (BASE / "run_selection_post6.py").read_text(encoding="utf-8") if (BASE / "run_selection_post6.py").exists() else ""
    code_ok = all((f'"{v}"' in sel) for k, v in CODES6.items() if k in [c["name"] for c in gate_in]) if sel else None
    say(f"- 🔴 **코드 대조**: 이 스크립트의 `CODES6`(출처 = `INTAKE_2026-09-04_post6.md` §1 표)가 "
        f"`run_selection_post6.py` 의 표에 **{'전건 존재 ✅' if code_ok else ('🔴 일부 없음' if code_ok is False else '⬜ 대조 불가(파일 없음)')}** "
        "— 원장에 종목코드 컬럼이 없어 이름→코드는 인테이크가 유일 출처다.")

    # ══ §11. 점검표·한계 ═══════════════════════════════════════════════════
    say()
    say("---\n")
    say("## §11. §7-B 실행 점검표 (판정 회차 판) · 모호 지점\n")
    say("| # | 점검 | 상태 | 증거 |")
    say("|---|---|---|---|")
    say(f"| 14 | 죽은 가드 실측 | {'✅' if allw else '⛔ 측정 0건'} | "
        f"3%p 최소 폭 {('%.2f%%p' % min(allw)) if allw else '—'}(§5-1) · 대조군 (가) 갈림 "
        f"{varies_a}/{len(ga_varies)} · `WRC-B1` 은 항등이라 증거가 «아니다»(§3) |")
    say(f"| 15 | 브랜치·`8d28e14` 조상 | {'✅' if branch == 'fix/tasso-post6-s5-fixes' and anc else '🔴'} | §0 표 |")
    say("| 17 | §2-5 재측정 | 🟡 **탐색 회차에서 완료**(`RESULTS_WRC_EXPLORE.md` §6 · 7/7행 재현) — "
        "이 회차는 post6 표본이라 §2-5 표의 대상이 아니다 |")
    say(f"| 18 | 의사티커 차분 | ✅ | §6-0 — 코드 {len(PSEUDO)} · DB 실측 {len(nonnum)} ⇒ 최종 {len(final_pseudo)} |")
    say(f"| 19 | DB 최신 봉 · 봉수 「포함/직전」 | ✅ | §0 `{END}` · §10 표 |")
    say("| 20 | 라이브 채택 금지 + §5-4 4줄 | ✅ | 머리말 · §5 · §5-2 · `wrc_post6/bands.tsv` 머리 주석 |")
    say("| 21 | `regen_gate.py` 등재 | 🔴 **미등재** | `PAIRS` 에 `RESULTS_WRC_POST6_NUMBERS.md` 가 «없다» · "
        "`MANUAL_DOCS` 에 `RESULTS_WRC_POST6.md` 도 «없다». 🔴 **이 회차는 `regen_gate.py` 수정 금지 대상**이라 "
        "등재하지 않았다 — **최종 레인이 등재해야 한다**(안 하면 §5-3 이 지적한 「어디에도 등재돼 있지 않다」 재발) |")
    say("| 22 | 순서 증거 | ✅ **대체 기제로 확인**(PD-0) | `PREDECISION_2026-09-04_post6.md` 를 추가한 커밋이 "
        "`88afe62`(WRC 동결)의 후손인가로 판정한다 — 원문 html 은 규약상 커밋 금지라 "
        "**#22 의 원래 증거는 처음부터 발생할 수 없었다**(PD-0 · 죽은 가드) |")
    say(f"| 23 | 유니버스 스냅샷 | ✅ | §6-1 + `wrc_post6/universe_snapshot.json` |")
    say(f"| 24 | `WRC-G1` 를 «먼저» 계산 | ✅ | §2 가 첫 계산 절 · 실측 **{100*g1:.1f}%** "
        f"{'🔴 발동 ⇒ 나머지는 «관측»이고 판정 표기는 ⛔(관리자 지시 · 문언은 「돌리지 않는다」)' if g1 >= G1_THR else '🟢 미발동'} |")
    say()
    say("### 11-1. 모호 지점 (양쪽 인쇄 · 어느 쪽도 고르지 않는다)\n")
    say("1. **`WRC-G1` 발동 시 「나머지를 돌리지 않는다」 ↔ 「계산하되 판정 표기 ⛔」** — "
        "사전등록 문언은 전자, 이 실행은 후자(관리자 지시). ⇒ **아래 값 전부가 «관측»이며 "
        "지지·불성립을 «선언하지 않는다».** 문턱은 올리지 않았다.")
    say("2. **탐색값 인용 창** — 동결 인용(`~2026-09-02`) ↔ 이 창 재측정(`~%s`). 양쪽 인쇄(§7·§7-1)." % END)
    say("3. **`REC-Z3` 분모** — 이 축의 분모(WRC 판정 분모)와 `REC-` 축의 분모가 «다르다». "
        "의무 발생 판정은 각 축이 자기 분모로 따로 낸다(§4).")
    say("4. **후속 2건(광전자·삼양)** — PD-2 대로 등록일 축 분모 «밖»이며 `reg_date` 가 비어 있어 "
        "창 자체가 정의되지 않는다(§1 표의 사유 열).")
    say()
    say("### 11-2. 한계 (§9 승계 · 값 무관)\n")
    say("- 🔴 이 축은 「해 0개」를 «원리적으로» 풀지 못한다(§2-4 산술 정리) — 가중 매수 모델은 "
        "`A0` 의 부분집합이다.")
    say("- 🔴 `WRC-A1`(균등 `1/N`)이 참이라는 근거가 «없다» — 저자는 차수별 비중을 적지 않았다(§2-2). "
        "⇒ 밴드가 좁아도 「저자가 균등 분할한다」가 아니라 「균등 가정에서 밴드가 좁게 결정된다」이다.")
    say("- 🔴 판정 대상이 «해가 있는» 건뿐이다 ⇒ **선택편향**이며, 그 배제는 무작위가 아니다"
        "(§5-3 2번의 두 문장 묶음).")
    say("- 🔴 표본이 저자가 «올리기로 고른» 매매다(`PREREG_SELECTION.md` §0) ⇒ 나온 `bₖ` 는 "
        "「저자의 주문 밴드」가 아니라 **「저자가 공개한 매매들의 밴드」**다.")
    say("- 🔴 `open_ended` 가 분모의 절반 이상이면 「해가 나왔다」의 증거력이 그만큼 약하다.")
    say("- 🔴 차용 문턱 넷(**3%p · 50% · 1/3 · 레그 ≥3**)은 전부 «다른 것을 재던» 값이며 이 대상에 "
        "대해 검증된 적이 없다. 그중 하나가 판정을 가르면 **「차용 문턱에 걸렸다」**고 적는다.")
    say("- 🔴 `adj_factor` 를 곱하지도 나누지도 않는다(프로젝트 SSOT) — 원주가 그대로 쓴다.")
    say("- 이 분석은 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).")

    say()
    say("---\n")
    say(f"결정성: 시드 `{SEED}` 고정 · DB 는 SELECT 만 ⇒ **같은 DB 스냅샷에서 재실행하면 byte 단위로 같다**. "
        "🔴 실행 시간·HEAD 해시는 **stdout 전용**이다.")
    say(f"평가 캐시 **{len(EVAL_CACHE):,}건** = 대조군에서 실제로 «다른» 계산의 수 · "
        f"창 데이터 없는 추첨 **{nodata[0]:,}건**")
    say()
    say("[[PREREG_WEIGHTED_RECON]] · [[FREEZE_WRC_2026-09-02]] · [[RESULTS_WRC_EXPLORE]] · "
        "[[PREREG_POST6]] · [[INTAKE_2026-09-04_post6]] · [[PREDECISION_2026-09-04_post6]]")

    # ══ 기계 산출물 ════════════════════════════════════════════════════════
    (ART / "universe_snapshot.json").write_text(json.dumps(
        {"db_snapshot_max_date": END, "pseudo_from_code": list(PSEUDO),
         "pseudo_nonnumeric_in_db": nonnum, "pseudo_final": final_pseudo,
         "universe": universe, "sha256": uni_sha}, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "explore_freeze_md5.json").write_text(json.dumps(
        {"rows": md5_rows, "explore_artifacts_clean_vs_HEAD": clean_expl,
         "git_status_porcelain": st.splitlines(),
         "expected_change": EXPECTED_CHANGE,
         "ledger_fingerprints": fp,
         "ledger_prefix_frozen": {f: {"lines": n, "frozen_md5": w}
                                  for f, (n, w) in LEDGER_PREFIX.items()},
         "ledger_key_columns": {"RNK_KEY": list(RNK_KEY), "WRC_KEY": list(WRC_KEY),
                                "LEG_KEY": list(LEG_KEY),
                                "note": "narrative 는 어느 지문에도 없다 — 이 축은 그 열을 읽지 않는다"}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "gate.json").write_text(json.dumps(
        {"post_log_no": POST_LOG, "post_date": POST_DATE, "window_end": END,
         "denominator": [c["name"] for c in gate_in],
         "intake_prediction": INTAKE_DENOM_PRED, "match": match_intake,
         "exact_rows": len(exact6), "gate_pass_rate": len(gate_in) / len(exact6),
         "rows": [{k: c[k] for k in ("item", "name", "code", "reg", "prec", "fill_level",
                                     "fill_n", "n_legs", "distinct", "open_ended", "gate")}
                  for c in p6]}, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "explore_same_window.json").write_text(json.dumps(
        {"window_end": END, "note": "🔬 탐색 표본(post4·post5)을 이 실행의 창에서 재측정한 값 — "
                                    "판정 분모가 아니다(WRC-O1)", "rows": ex_rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    for c in gate_in:
        rec = {k: c[k] for k in ("post", "log_no", "item", "name", "code", "reg", "prec",
                                 "fill_level", "fill_n", "legs", "n_legs", "distinct",
                                 "open_ended", "prog_ver", "gate")}
        rec["window_end"] = END
        if c["ctx"]:
            rec["window"] = dict(lo=c["ctx"]["lo"], hi=c["ctx"]["hi"], h0=c["ctx"]["h0"],
                                 l0=c["ctx"]["l0"], o0=c["ctx"]["o0"], c0=c["ctx"]["c0"],
                                 d0=c["ctx"]["d0"], bars_incl=c["ctx"]["nbar_inc"],
                                 bars_before=c["nbar_pre"], g_win=len(c["ctx"]["U"]),
                                 g_unit=c["ctx"]["g"], contiguous=c["ctx"]["contiguous"],
                                 win_low=c["win_lo"], win_high=c["win_hi"],
                                 anchor_below_window_high=bool(c["ctx"]["h0"] < c["win_hi"]))
            rec["A0"] = dict(n_intervals=len(c["a0"] or []),
                             measure=iv_measure(c["a0"]) if c["a0"] else 0.0,
                             pmin=iv_min(c["a0"]) if c["a0"] else None,
                             pmax=iv_max(c["a0"]) if c["a0"] else None)
            rec["A0_net"] = dict(feasible=bool(c["a0_net"]),
                                 measure=iv_measure(c["a0_net"]) if c["a0_net"] else 0.0)
            if c.get("a1"):
                rec["A1"] = dict(feasible=c["a1"]["feasible"], n_means=c["a1"]["n_means"],
                                 measure=0.0, path=c["a1"]["path"], cross_ok=c["a1"]["cross"])
            if c.get("a3"):
                rec["A3"] = dict(n_intervals=len(c["a3"]), measure=iv_measure(c["a3"]))
            if c.get("bands"):
                rec["bands"] = [dict(k=i + 1, **{kk: b[kk] for kk in
                                                 ("pmin", "pmax", "b_lo", "b_hi", "w", "cells", "tick")})
                                for i, b in enumerate(c["bands"])]
                rec["band_median_w"] = med([b["w"] for b in c["bands"]])
            rec["control_a"] = dict(zip(("a0", "a1", "trials", "narrow"), ga_by_case[c["name"]]))
        else:
            rec["A0"] = None
            rec["reason"] = "DB 종목코드 부재 (WRC-G1 사유 ①)"
        rec["_notation"] = NOTE4
        (ART / f"case_post6_{c['item']}_{c['name']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "controls_summary.json").write_text(json.dumps({
        "seed": SEED, "nrep": NREP, "note_nrep": "run_selection.py 는 NREP=2000",
        "db_snapshot_max_date": END,
        "branch_a_random_stock": {"trials": ga_tot, "a0_feasible": ga_a0, "a1_feasible": ga_feas,
                                  "N1_rate": ga_feas / ga_tot, "band_denominator": ga_meas,
                                  "narrow": ga_narrow,
                                  "N2_rate": (ga_narrow / ga_meas) if ga_meas else None,
                                  "per_case": {k: dict(a0=v[0], a1=v[1], trials=v[2], narrow=v[3])
                                               for k, v in ga_by_case.items()},
                                  "distinct_codes_per_case": {k: len(v) for k, v in ga_codes.items()},
                                  "constant_cases": const_a},
        "branch_b_shuffled_legs": {"status": "⛔ 무정보 강등 — FREEZE_WRC_2026-09-02.md §3 확정 "
                                             "(교집합은 순서 불변 · A1 제약은 매수 사다리에만 걸린다) ⇒ "
                                             "이 회차는 돌리지 않았다. 재명세는 별도 사전등록 개정."},
        "observed": {"cases": obs_tot, "a0_feasible": obs_a0, "a1_feasible": obs_feas,
                     "band_measurable": meas_n, "narrow": narrow_n},
        "guards": {"G1": g1, "G1_threshold": G1_THR, "G1_fired": g1 >= G1_THR,
                   "Z3": z3_rate, "Z3_threshold": 0.5, "Z3_fired": z3_rate >= 0.5,
                   "G1_by_slice": g1_slices, "G1_flip_slices": flip,
                   "Z3_by_slice": z3_slices, "Z3_flip_slices": z3_flip,
                   "P1_numerator": narrow_n, "P1_denominator": meas_n,
                   "P1_needed_majority": need, "P1_verdict": "판정 불가"
                   if (g1 >= G1_THR or z3_rate >= 0.5 or meas_n == 0) else
                   ("문턱 충족" if narrow_n >= need else "문턱 미달")},
        "thresholds": {"N1": N_THR, "N2": N_THR, "band_pp": BAND_THR, "G1": G1_THR,
                       "residual": list(THR), "Z3": 0.5},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    with (ART / "bands.tsv").open("w", encoding="utf-8") as f:
        f.write("# RESULTS_WRC_POST6 — bₖ 밴드 (기계 생성 · 판정 회차)\n")
        f.write(f"# 창 = [등록일, {END}] · gross · 시드 {SEED} · post6({POST_LOG}) «만»\n")
        for ln in NOTE4:
            f.write("# " + ln.replace("\n", " ") + "\n")
        f.write("#\n")
        f.write("post\tname\tcode\treg\tfill_n\tk\tP_min\tP_max\tb_lo_pct\tb_hi_pct\tw_pp\tcells\n")
        for c in band_cases:
            for k, b in enumerate(c["bands"], start=1):
                f.write(f"post6\t{c['name']}\t{c['code']}\t{c['reg']}\t{c['fill_n']}\t{k}\t"
                        f"{b['pmin']:.2f}\t{b['pmax']:.2f}\t{b['b_lo']:.4f}\t{b['b_hi']:.4f}\t"
                        f"{b['w']:.4f}\t{b['cells']:.2f}\n")

    (BASE / "RESULTS_WRC_POST6_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    print(f"\n[시간] 총 {time.time() - t_start:.1f}초 · 적재 {t_load:.1f}초 · 대조군 (가) {t_ga:.1f}초")
    print(f"[git] 브랜치 {branch} · HEAD {head} · `8d28e14` 조상 {anc}  — 해시는 stdout 전용")
    print("[written] RESULTS_WRC_POST6_NUMBERS.md + wrc_post6/*.json|tsv")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
