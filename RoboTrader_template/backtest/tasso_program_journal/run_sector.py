# -*- coding: utf-8 -*-
"""`SEC-` 축 **배선 점검** 실행 — 섹터 동반 상승(`PREREG_SECTOR_COMOVE.md` §0-4 **4번**).

🔬 **탐색 표기 · 판정 아님 · 규칙 «선택» 없음.** 대상은 **post1~5 «만»** 이다(`SEC-O1` · §4-5).
post6 은 이 스크립트가 도는 시점에 **존재하지 않는다** — 어떤 post6 수치도 이 산출물에 없다.

사전등록: `PREREG_SECTOR_COMOVE.md`(동결 · `SEC-D1`~`D8` 사장님 확정 2026-09-02 · §0-6)
  §1 데이터 실측 · §2 설계 동결(`SEC-R1`~`R6`) · §3 예측 동결표 · §4 대칭 단언
  (`SEC-N1`·`B1`·`B2`·`G1`·`X1`·`O1`·`V1`) · §5 실행 전제 · §6 판정 불가 · §7-B 실행 점검표

🔒 **사장님 확정분(§0-6)** — 이 스크립트가 «판정 갈래»로 쓰는 것:
  `SEC-D1` 섹터 = `induty_code` 앞 **`N = 3`** 자리(주) · `N = 2`·`N = 5` 의무 민감도
  `SEC-D2` 측정자 = **`SEC-M1`**(섹터 중앙수익률의 당일 «섹터간» 백분위)(주) · `M2`·`M3` 의무 민감도
  `SEC-D3` 유니버스 = `PREREG_RANKING.md` §2-1 승계 ∩ **섹터코드 존재**
  `SEC-D4` 대칭 대조 풀 = 무작위 «급등» 종목(`n_up`) **채택**
  `SEC-D5` 분모 = `exact` 만 · `approx` 의무 민감도 · `after` 제외
  `SEC-D6` `SEC-X1`(섹터 라벨 순열 대조군) **채택** — 용도는 **귀무 «구현» 1종오류율 보정 하나뿐**
  `SEC-D7` 수익률 = `close / prev_close − 1`
  `SEC-D8` EOD 점검표 **미편입**

🔴 **계산 «전»에 고정한 구현 결정 (S-1 ~ S-8)** — 사전등록 문언의 «기계화»이며 새 잣대가 아니다:
  S-1 `prev_close` 는 `run_regday_post5.load_universe_day` 의 **20«일력»일 창 `LAG`** 를 글자 그대로
      복제한다(§1-3 이 *「그 정의를 «글자 그대로» 복제해 재현했다」*고 못 박았다). 복제본이 그 함수와
      **집합으로 같은지**를 매 등록일에 실측해 인쇄한다(§1-4 배선).
  S-2 백분위 = `100 × (G − 1 − sec_rank) / (G − 1)` · `sec_rank` = *「그날 `med` 가 저자 섹터보다
      «좋거나 같은» 섹터 수, 자기 섹터 제외」*(§2-2). ⇒ 저자 섹터가 그날 **1위**(동률 없음)면
      백분위 **100** 이고, 이는 §4-2 (가)가 *「관측 통계량의 천장은 100」*이라 적은 것과 «같은 눈금»이다.
      동률은 전부 «위»로 세므로 백분위를 **낮추는**(보수적) 방향이다(§4-1).
  S-3 자기 제외는 **두 곳 전부**(§2-3 M7): ①섹터 동료 집합 `P(D,s)` ②귀무·대조 추출 풀.
      저자 섹터의 통계량은 «자기 제외» 값이고, 다른 섹터의 통계량은 그 섹터 전원 값이다.
  S-4 중앙값 관용구(C-20 승계) = 분모가 **짝수면 두 가운데 값의 «평균»**. 섹터 내 중앙값·글 단위
      중앙값·풀 중앙값 전부 같은 규약이며, 짝·홀 여부를 인쇄한다.
  S-5 `p` = `mean(귀무 통계량 ≥ 관측 통계량)` — **등호 포함**(§4-1 *「동률은 `p` 를 «키우는» 쪽으로」*).
  S-6 측정 가능 = 「그 갈래에서 섹터 라벨이 정의되고(`length ≥ N`) 동료 `|P| ≥ 1` 이고 그날 섹터가
      2개 이상(`G ≥ 2`)」. 귀무·대조 풀도 **같은 조건으로 한정**하고 그 한정 손실을 인쇄한다(§2-3).
  S-7 `q_top` = §4-2 (가) 문언 *「그날 풀에서 «1위 섹터»가 차지하는 비율」* 그대로. 그 정의가
      «천장을 받을 확률」의 대리이므로 **직접 실측한 천장 점유율**(풀에서 백분위 = 100 인 비율)을
      나란히 인쇄하고, 두 값이 발화 판정을 가르면 그 사실을 적는다. **판정은 문언 정의로 한다.**
  S-8 `SEC-X1` 은 **주 갈래(`N=3` · `SEC-M1`)에 대해서만** 돌린다(§4-4 가 재는 것이 «귀무 구현»
      하나뿐이므로 갈래마다 돌릴 이유가 없다). 두 풀(`SEC-N1`·`SEC-B1`) 각각의 1종오류율을 낸다.

🔴 라이브 트리 import 0건 · DB 는 **SELECT 만** · `adj_factor` 산술 0건 · 원장은 «읽기»만 ·
   `stock_industry` 는 «읽기 전용»(이 축은 그 표를 채우거나 고치지 않는다 · §5 6번).
🔴 이 축은 `volume` 을 안 쓴다 — `close`·`prev_close`·`high` 만 쓴다(§5 5번).
🔴 `daily_prices.returns_1d` 를 쓰지 않는다 — 직접 계산한다(§2-2).

🔴 `SEC-R6`(§5 7번) 재사용 — 유니버스·의사티커·`n_up`·원장 판독은 **전부 기존 코드 import**:
   `run_selection.PSEUDO` · `run_regday_post5.load_universe_day`·`.universe_raw_count` ·
   `run_ranking.build_codes`·`.exact_items`·`.approx_items`·`.load_ledger` · `run_tests.DSN`.
   **표를 복사해 다시 쓰지 않는다.**

산출물 = `RESULTS_SECTOR_DRYRUN_NUMBERS.md`(기계 생성 · `regen_gate.py` `PAIRS` 대상) +
        `sector_dryrun/`(등록일별 JSON · `controls_summary.json` · `universe_snapshot.json` ·
        `sector_snapshot.json` · `cases.tsv`).
산문 = `RESULTS_SECTOR_DRYRUN.md`(사람이 쓴다 · `MANUAL_DOCS` 대상).

════════════════════════════════════════════════════════════════════════════════
🔒 **모드 (2026-09-04 추가 · post6 판정 단계 = §0-4 «7번»)**

`regen_gate.py` `PAIRS` 는 **두 산출물이 같은 스크립트에서 나온다**고 등재돼 있다
(`RESULTS_SECTOR_DRYRUN_NUMBERS.md` ↔ `run_sector.py` · `RESULTS_SECTOR_POST6_NUMBERS.md` ↔
`run_sector.py` · `FREEZE_SECTOR_2026-09-03.md` §5-1). 그래서 **새 스크립트를 만들지 않고**
같은 스크립트의 **모드 인자**로 나눈다.

  `python run_sector.py`                → 🔒 **둘 다**(`regen_gate.py --rerun` 이 인자 없이
                                          부르므로 기본값이 둘 다여야 두 `PAIRS` 항목이 «실제로»
                                          재생성돼 byte 비교가 성립한다)
  `python run_sector.py --mode dryrun`  → 배선 점검(post1~5 «만») 재생성
  `python run_sector.py --mode post6`   → 🔒 **post6 판정**(post6 신규 `exact` «만»)

🔴🔴 **원장이 자라도 배선 점검 산출물은 움직이면 안 된다** — `ledger_trades.csv` 에 post6 12행이
   append 됐으므로 `exact_items()` 는 이제 post6 건도 돌려준다. 그래서 **두 모드 «모두»에
   «명시적» 글 필터**를 건다(`TRAIN_POSTS` / `POST6_IDX`). 필터가 없으면 배선 점검 산출물이
   원장 추가만으로 조용히 바뀌고, 그건 **동결본 오염**이다.
   🔑 ***「post6 은 아직 없다」를 「필터가 필요 없다」로 읽으면, 글이 온 날 동결본이 깨진다.***

🔴 post6 판정 모드가 추가로 지키는 것(전부 사전등록 문언 · **새 잣대 0건**):
  · 분모 = **post6 신규 `exact` 10건**(PD-2 후속 2건은 `reg_date_precision = none` 이라
    `exact_items()` 가 «정의상» 빼고, 그것이 `SEC-` 축 분모 밖과 같은 처리다 · `SEC-D5`)
  · `SEC-G1` 사유 ①~⑤ 를 **갈래별·사유별·«종목명»까지** 인쇄(§4-3 1번)
  · `SEC-B1` 발화 조건 `q_top` 을 **판정 분모의 등록일에서 실측**(§4-2 (가) · §7-B #20)
  · `SEC-P1` = **3중 AND**(§3 1행) · `SEC-P2` 는 **기록만** · `SEC-V1` 은 **4축**(§4-6)
  · `SEC-O1` 훈련(post1~5 🔬) ↔ 검증(post6) **항상 나란히**(§4-5) — 훈련은 분모 «밖»
  · 재진입 2건(지투파워·현대약품) **제외 민감도**와 `P6-PRIOR_CYCLE_IN_WINDOW` 건수
    (`PREREG_POST6.md` §1-5 · `PREDECISION_2026-09-04_post6.md` PD-3)
산출물 = `RESULTS_SECTOR_POST6_NUMBERS.md` + `sector_post6/`.
산문 = `RESULTS_SECTOR_POST6.md`(사람이 쓴다 · `MANUAL_DOCS` 대상).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from math import comb
from pathlib import Path

import numpy as np
import psycopg2

from run_ranking import approx_items, build_codes, exact_items, load_ledger
from run_regday_post5 import load_universe_day, universe_raw_count
# 🔴 post6 신규 10건의 «종목코드·등록일»은 계열이 이미 확정한 것을 그대로 승계한다(새 매핑 0건).
#    `PREDECISION_2026-09-04_post6.md` PD-3 의 재진입 플래그도 같은 모듈에서 온다.
from run_regday_post6 import PD3_FLAG, POST6_NEW, REENTRY
from run_selection import PSEUDO
from run_tests import DSN

BASE = Path(__file__).resolve().parent
ART_DRYRUN = BASE / "sector_dryrun"
ART_POST6 = BASE / "sector_post6"
ART_POST7 = BASE / "sector_post7"     # 🔴 덧붙인 것 — 기존 두 디렉토리를 건드리지 않는다
ART_POST8 = BASE / "sector_post8"     # 🔴 덧붙인 것(2026-09-24) — 기존 세 디렉토리를 건드리지 않는다
OUT: list[str] = []

SEED = 20260815          # §2-3 · `PREREG_POST6.md` §3-1 동결분 승계
NREP = 20_000            # 〃 (🔴 `run_selection.py:22` 는 NREP = 2000 — 차이를 §0 에 인쇄한다)
X1_REP = 200             # §4-4 · `RESULTS_RANKING_TRAIN.md` §5 «승계»(독립 실현 200)
P_THR = 0.05             # `PREREG_REGDAY_MEASURE.md` §4-1 «차용»
B2_THR = 0.50            # `RESULTS_D1_OOS_POST5.md` §9 W7 «차용»
G1_THR = 1.0 / 3.0       # `RESULTS_RECONSTRUCT_POST4.md` §6 Y3 «차용»
QTOP_THR = 0.135         # §4-2 (가) — `3q²(1−q)+q³ = 0.05` 의 근 (§4-1 `t ≈ 0.865` 와 같은 근)
UP_MULT = 1.15           # `run_regday_post5.py:13`·`:327` 의 `n_up` 정의 «승계»(새 문턱 아님)
DROP_MARK = 0.01         # §5 6-1 — «표시» 문턱이지 «판정» 게이트가 아니다
NS = (2, 3, 5)           # `SEC-D1` 후보 (⚠️ `N = 4` 배제 사유는 §2-1 m1)
MEAS = ("SEC-M1", "SEC-M2", "SEC-M3")
MAIN_N, MAIN_M = 3, "SEC-M1"   # 🔒 사장님 확정 주 판정 갈래
MIN_EXACT = 3            # `PREREG_SELECTION.md` §7 «차용» — 3건 미만이면 판정을 미룬다

# 🔴🔴 **글 필터(명시)** — 원장이 자라도 각 모드의 분모가 «정의로» 고정되게 한다.
#     배선 점검은 post1~5 «만», 판정은 post6 «만». 값을 보고 고른 게 아니라 §0-4 의 단계 정의다.
TRAIN_POSTS = (1, 2, 3, 4, 5)
POST6_IDX = 6
POST6_LOG_NO = "224401108114"   # `INTAKE_2026-09-04_post6.md` 머리 — 필터의 «이중» 확인용

# ═══ post7 판정 모드 상수 (2026-09-15) — 🔴 **덧붙인 블록** · 위 상수를 한 글자도 고치지 않는다 ═══
POST7_IDX = 7
POST7_LOG_NO = "224409404744"   # `INTAKE_2026-09-15_post7.md` 머리 — 필터의 «이중» 확인용
# 🔴🔴 **창이 «상수»다.** 발행일 2026-09-12 가 **토요일 = 휴장**이라 `PREDECISION_2026-09-15_post7.md`
#    **PD-1** 이 창 종료를 **`2026-09-11`(금) 한 값**으로 못 박았다(`RESULTS_LADDER_TRANCHE.md` §1 **B-1** ·
#    `PREREG_WEIGHTED_RECON.md` §5-2 :678-680 · `PREREG_ANCHOR_REDESIGN.md` §2-1 — 세 동결 문언 일치).
#    실행 시 `max(date)` 는 **기록만** 한다. ⚠️ 이 축은 애초에 창을 안 쓰지만(등록일 당일만) 표기는 박는다.
DB_UPTO_POST7 = "2026-09-11"
# post7 신규 10건 — `INTAKE_2026-09-15_post7.md` §1 표를 **그대로 옮겨 적은 것**(새 매핑 0건).
#    `reg` 가 None 인 두 건은 **등록일 «문장»이 없는** 건이다(PD-4 · 급등일을 승격하지 않는다).
#    🔴 해치텍 = `0155E0`(이름 검색 불가 · `news` 경유 확정 · PD-11 2번) ·
#    🔴 「강동씨엔앨」은 저자 표기이고 DB 표기는 「강동씨앤엘」이다(PD-10 4번 · 코드는 일치).
POST7_NEW = [
    ("한전기술",         "052690", None),
    ("한전산업",         "130660", None),
    ("지투파워",         "388050", None),          # 「9월 초」 = approx
    ("서산",             "079650", "2026-09-03"),
    ("강동씨엔앨",       "198440", "2026-09-03"),
    ("로보티즈",         "108490", "2026-09-04"),
    ("해치텍",           "0155E0", "2026-09-07"),
    ("빛과전자",         "069540", "2026-09-08"),
    ("한국화장품제조",   "003350", None),          # 「8월 말」 = approx
    ("범한퓨얼셀",       "382900", "2026-09-09"),
]
# 재진입 3건 — PD-3. 직전 «사이클»의 등록일(없으면 None = 저자 미명시).
# 🔴 지투파워는 이 계열 최초의 **3번째 사이클**이다(직전 = post6 08-26 · 2 사이클 전 08-13 은 기록만).
# 🔴 빛과전자의 post4 행은 **등록 사건이 아니라 종료 기록**이라 직전 «등록일」은 post3 의 08-05 다(정정 ②).
REENTRY_P7 = {"388050": "2026-08-26",   # 지투파워 — post6 #10 (3번째 사이클)
              "003350": "2026-08-12",   # 한국화장품제조 — post5 #2
              "069540": "2026-08-05"}   # 빛과전자 — post3 #6
PD3_FLAG_P7 = {"388050": 1, "003350": 1, "069540": 0}   # PD-3 표가 «계산 전»에 못박은 값
# 🔴 위 3건 중 **판정 분모(`exact`) 안은 빛과전자 1건뿐**이고 그 값은 **0** 이다
#    ⇒ ***판정 분모 안 플래그 = 0*** · 글 전체 플래그 2건은 둘 다 `approx` 갈래다. 두 수를 합치지 않는다.
POST7_NONE_NEW = ("한전기술", "한전산업")                 # PD-4 — 신규이나 **등록일 문장 부재**
POST7_FOLLOWUP = ("한라캐스트", "아난티", "우리기술투자")   # PD-2 — 기존 건 후속(등록일 축 밖)
SEC_EXPECT_NOSEC = 1        # PD-11 — `exact` 6 중 섹터코드 **5/6**(해치텍만 `stock_industry` 미수록)
# 🆕 `SEC-P2` 누계 이어가기(🔒 결정 ⑥ · 보고서 §6 #6) — post6 산출물에서 **옮겨 적은 값**(재계산 아님).
SEC_P2_PRIOR = {"n_judgements": 1, "n_support": 0}

# ═══ post8 판정 모드 상수 (2026-09-24) — 🔴 **덧붙인 블록** · 위 상수를 한 글자도 고치지 않는다 ═══
POST8_IDX = 8
POST8_LOG_NO = "224416253270"   # `INTAKE_2026-09-18_post8.md` 머리 — 필터의 «이중» 확인용
# 🔴 창 = `PREDECISION_2026-09-18_post8.md` **PD-1** — 발행 2026-09-18(금)이 **거래일**이라 **발행 당일 봉 «포함»**
#    (B-1 · 전 축 · `WRC-` 포함). 실행 시 `max(date)` 는 **기록만**. ⚠️ 이 축은 등록일 당일만 쓴다(표기는 박는다).
DB_UPTO_POST8 = "2026-09-18"
# post8 신규 7건 — `INTAKE_2026-09-18_post8.md` §1 표를 **그대로 옮겨 적은 것**(새 매핑 0건 · 후속 3건은 신규가 아니다).
#    `reg` 가 None 인 건 = 등록일 «문장»이 없거나(원익 · 🔒 #2 `none`) `approx`(「8월말」 · 헥토 · 코데즈)다.
#    🔴 액스비스 = `0011A0`(이름 4표 0건 · `news` 경유 확정 · PD-11) · 🔴 우리기술 = `032820`(≠ 우리기술투자 041190).
POST8_NEW = [
    ("우리로",           "046970", "2026-09-11"),     # 항목 내 2 사이클 · 측정 등록 = 사이클 1(🔒 #1)
    ("원익",             "032940", None),             # `none`(🔒 #2) · 재진입(post6 #8)
    ("JW신약",           "067290", "2026-09-01"),
    ("헥토파이낸셜",     "234340", None),             # 「8월말」 = approx · 재진입(post6 #4)
    ("액스비스",         "0011A0", "2026-09-11"),
    ("코데즈컴바인",     "047770", None),             # 「8월말」 = approx · 재진입(3번째 사이클)
    ("우리기술",         "032820", "2026-09-09"),
]
# §1-5 재진입 3건 — PD-3. 직전 «사이클»의 등록일. 🔴 셋 다 판정 분모(`exact`) «밖»이다(원익 `none` · 헥토·코데즈 `approx`).
REENTRY_P8 = {"032940": "2026-08-31",   # 원익 — post6 #8
              "234340": "2026-08-28",   # 헥토파이낸셜 — post6 #4
              "047770": "2026-08-21"}   # 코데즈컴바인 — post5 #3 (그 전 post4 #6 08-19)
# `P6-PRIOR_CYCLE_IN_WINDOW`(PD-3 표) — 정수로 확정되는 것만 적는다(원익 = 계산 안 함 · 헥토 = 갈래별).
PD3_FLAG_P8 = {"047770": 1}
PD3_NOTE_P8 = ("원익 = 계산 안 함(`none`) · 헥토파이낸셜 = 갈래별 2/7 갈래 1 · 5/7 갈래 0(`approx`) · "
               "코데즈컴바인 = 7/7 갈래 1(`approx`) · 🔀 우리로 = 0(측정 등록일 = 사이클 1) ⇒ **판정 분모 안 = 0**")
POST8_TWO_CYCLE_CODE = "046970"                              # 우리로 — 🔒 #1-(ii) 「우리로 제외」 인쇄만
POST8_NONE_NEW = ("원익",)                                   # PD-4 🔒 #2 — 신규이나 등록일 미기재
POST8_FOLLOWUP = ("빛과전자", "로보티즈", "범한퓨얼셀")      # PD-2 — 기존 건 후속(등록일 축 밖)
SEC_EXPECT_NOSEC_P8 = 1     # PD-11 — `exact` 4 중 섹터코드 **3/4**(액스비스만 `stock_industry` 미수록)
# `SEC-P2` 누계 이어가기 — post6 «불성립» 1회 · post7 «판정 불가»(`SEC-V1`)는 누계 분모 밖 ⇒ 판정 1 · 성립 0.
#    🔴 **옮겨 적은 라벨**이다(동결 산출물). 같은 스냅샷 재계산은 `main_post8` §8-1 에 «나란히» 인쇄한다.
SEC_P2_PRIOR_P8 = {"n_judgements": 1, "n_support": 0}

# 🔒 동결 배선 점검값(`FREEZE_SECTOR_2026-09-03.md` §4-2 · DB 스냅샷 **2026-09-02**) —
#    `SEC-O1` 이 요구하는 「훈련 ↔ 검증 나란히」의 훈련 열이며 **판정 분모 «밖»**이다.
#    🔴 이 실행의 DB 스냅샷은 더 뒤이므로 재계산값이 이것과 다를 수 있다 ⇒ **괴리를 인쇄**한다.
FROZEN_TRAIN = {"main": 67.0, "pooled": 69.4, "N1": 0.0382, "B1": 0.3258,
                "B2": 0.60, "B2_wins": 9, "B2_n": 15, "G1": 3.0 / 18.0,
                "n_measurable": 15, "n_items": 18, "db_snapshot": "2026-09-02"}

# 🔴 §7-B #24 — 모든 산출물에 «그대로» 붙이는 의무 문언.
NOTATION = [
    "1. 🔴 **「라이브 채택 금지 · 성과·엣지 추정 금지」** — 이 문서가 만드는 어떤 섹터 지표도 "
    "라이브 전략·파라미터 변경의 근거가 아니다(`PREREG_SECTOR_COMOVE.md` §0-1 · `PREREG.md` §0). "
    "산출물은 **기록**이지 전략 후보가 아니다.",
    "2. 🔴 **「+15%」 문턱이 이 축 «안»에 남아 있다** — `n_up`(대조 풀)과 `SEC-M2` 가 "
    "`고가 ≥ 전일종가 × 1.15` 를 쓴다(`run_regday_post5.py:13`·`:327` 승계 · §2-2). "
    "**`SEL-S1` 기각은 그대로 유지된다** — 이 값은 «판정 문턱»이 아니라 «대조 풀·측정자 입력»이고, "
    "**등록일 당일 저자 종목에 걸지 않는다**(동료에게만 건다).",
    "3. 🔴 **`SEC-P1` 불성립을 「테마가 아니다」로 읽지 않는다** — 거짓 음성이 구조적이다"
    "(에코프로 4종목이 KSIC 에서 «세 칸»으로 흩어진다 · §0-2 · §9). "
    "성립도 「섹터 동반성이 존재한다」까지이며 「테마로 고른다」의 확증이 아니다.",
    "4. 🔴 **`SEC-N1` 은 «`SEC-B1` 없이는» 증거가 아니다** — 저자 종목은 정의상 급등주이고, "
    "급등주가 섹터 동반성이 높다면 `SEC-N1` 은 그 사실만 되비춘다(= `REG-M4` 재진술). "
    "**정보는 `SEC-B1`·`SEC-B2` 에 있다**(§4-1).",
    "5. 🔬 **여기 있는 값은 전부 «탐색적 표기»다**(`SEC-O1` · §4-5) — post1~5 값은 "
    "**판정 분모에 넣지 않는다.** 판정은 post6 부터 누적한다. "
    "그리고 이 축의 최대치는 **「기술」**이다(승/패 대조 2회 연속 미실시 · §0-2 ③).",
    "6. 🔴 **이 실행은 «훈련»이 아니라 «배선 점검»이다**(§0-4 4번) — 규칙 «선택»이 없다. "
    "잣대(`SEC-D1`·`D2`)는 이 실행 «전»에 동결됐다(§0-6 · 2026-09-02).",
]

# 🔴 post6 판정 모드 의무 문언 — 1~4 는 위와 «문언 그대로» 같고, 5·6 만 단계가 다르다.
NOTATION_POST6 = NOTATION[:4] + [
    "5. 🔒 **여기 있는 값이 «판정»이다**(`SEC-P1`·`SEC-P2` · §0-4 7번) — 분모는 "
    "**post6 신규 `exact` 건**이며, **훈련(post1~5) 값은 분모에 «넣지 않는다»**"
    "(`SEC-O1` · §4-5). 훈련 열은 🔬 «탐색적 표기»로 나란히 두기만 한다. "
    "그리고 이 축의 최대치는 **「기술」**이다(승/패 대조 3회 연속 미실시 · §0-2 ③).",
    "6. 🔴 **잣대는 이 실행 «전»에 동결됐다** — `SEC-D1`(`N = 3`)·`SEC-D2`(`SEC-M1`) 사장님 확정 "
    "2026-09-02(§0-6) · 배선 점검 2026-09-02 · 동결 커밋 `FREEZE_SECTOR_2026-09-03.md` · "
    "그 «뒤»인 2026-09-04 에 `fetch_post.py` 가 돌았다(`PREDECISION_2026-09-04_post6.md` PD-0). "
    "🔴 **이 실행은 잣대를 하나도 바꾸지 않는다** — 값을 보고 바꾸면 그게 사후적합이다.",
]


# 🔴 post7 판정 모드 의무 문언 — 1~4 는 위와 «문언 그대로» 같고, 5·6 만 글·시각이 다르다.
NOTATION_POST7 = NOTATION[:4] + [
    "5. 🔒 **여기 있는 값이 «판정»이다**(`SEC-P1`·`SEC-P2` · §0-4 7번) — 분모는 "
    "**post7 신규 `exact` 건**이며, **훈련(post1~5) 값은 분모에 «넣지 않는다»**"
    "(`SEC-O1` · §4-5). 훈련 열은 🔬 «탐색적 표기»로 나란히 두기만 한다. "
    "그리고 이 축의 최대치는 **「기술」**이다(승/패 대조 **4회 연속** 미실시 · §0-2 ③).",
    "6. 🔴 **잣대는 이 실행 «전»에 동결됐다** — `SEC-D1`(`N = 3`)·`SEC-D2`(`SEC-M1`) 사장님 확정 "
    "2026-09-02(§0-6) · 배선 점검 2026-09-02 · 동결 커밋 `FREEZE_SECTOR_2026-09-03.md` · "
    "그 «뒤»인 2026-09-15 15:36:49 KST 에 `fetch_post.py`(post7)가 돌았다"
    "(`PREDECISION_2026-09-15_post7.md` PD-0 표 · `git branch -r --contains` 6/6 `origin/main`). "
    "🔴 **이 실행은 잣대를 하나도 바꾸지 않는다** — 값을 보고 바꾸면 그게 사후적합이다.",
]

# 🔴 post8 판정 모드 의무 문언 — 1~4 는 위와 «문언 그대로» 같고, 5·6·7 만 글·시각이 다르다(덧붙인 것).
NOTATION_POST8 = NOTATION[:4] + [
    "5. 🔒 **여기 있는 값이 «판정»이다**(`SEC-P1`·`SEC-P2` · §0-4 7번) — 분모는 "
    "**post8 신규 `exact` 건**이며, **훈련(post1~5) 값은 분모에 «넣지 않는다»**"
    "(`SEC-O1` · §4-5). 훈련 열은 🔬 «탐색적 표기»로 나란히 두기만 한다. "
    "그리고 이 축의 최대치는 **「기술」**이다(승/패 대조 **5회 연속** 미실시 · §0-2 ③).",
    "6. 🔴 **잣대는 이 실행 «전»에 동결됐다** — `SEC-D1`(`N = 3`)·`SEC-D2`(`SEC-M1`) 사장님 확정 "
    "2026-09-02(§0-6) · 배선 점검 2026-09-02 · 동결 커밋 `FREEZE_SECTOR_2026-09-03.md` · "
    "그 «뒤»인 2026-09-18 19:04:05 KST 에 `fetch_post.py`(post8)가 돌았다"
    "(`PREDECISION_2026-09-18_post8.md` PD-0 표 · 10 SHA 전부 `origin/main`). "
    "🔴 **이 실행은 잣대를 하나도 바꾸지 않는다** — 값을 보고 바꾸면 그게 사후적합이다.",
    "7. 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) — "
    "🆕 `PREREG_POST8.md` 첫 구속 회차(`D-3`·`D-5`·`D-8`·`D-9` 의무 인쇄 · 등급 이름 0).",
]


def say(s=""):
    print(s)
    OUT.append(s)


def med(xs):
    """중앙값 — S-4(C-20 승계): **분모가 짝수면 두 가운데 값의 «평균»**."""
    if len(xs) == 0:
        return None
    s = sorted(xs)
    n = len(s)
    return float(s[n // 2]) if n % 2 else float((s[n // 2 - 1] + s[n // 2]) / 2.0)


def med_note(n):
    return "짝수 ⇒ 두 가운데 값의 «평균»" if n % 2 == 0 else "홀수 ⇒ 가운데 값"


def sha_list(xs):
    return hashlib.sha256(("\n".join(xs)).encode("utf-8")).hexdigest()


def fmt(v, nd=1):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"


# 🔴 난수 스트림 분리 (§2-3 «필수» 승계) — `RESULTS_RANKING_TRAIN.md` §5 가 실측으로 잡은
#    결함(같은 시드로 목적이 다른 두 계열을 만들어 얽힘)을 구조적으로 막는다.
#    ⚠️ 이름은 **끝에만 덧붙인다** — `spawn` 은 앞쪽 자식을 보존한다.
_STREAM_NAMES = ["sec_n1", "sec_b1", "sec_x1_perm", "sec_x1_null",
                 "sec_x1_bypass_perm", "sec_x1_bypass_null"]
_CHILDREN = dict(zip(_STREAM_NAMES, np.random.SeedSequence(SEED).spawn(len(_STREAM_NAMES))))


def stream(name):
    return np.random.default_rng(_CHILDREN[name])


# ══════════════════════════════════════════════════════════════════════════════
# 1. 하루치 섹터 통계 — 전 종목에 대해 «자기 제외» 통계량과 그 섹터간 백분위
# ══════════════════════════════════════════════════════════════════════════════
def day_stats(lab, r, up):
    """lab: int32 (>=0 유효 · -1 = 그 갈래에서 라벨 미정) · r: float64 · up: bool.

    반환(전 종목 길이의 배열) — S-2·S-3 그대로:
      peers   동료 수 `|P|` = m − 1 (라벨 미정이면 -1)
      m1..m3  자기 제외 «원값» (`med` · 급등 동료 수 · 상승 비율)
      p1..p3  그날 «모든 섹터»의 같은 통계량 분포 안에서의 백분위 (0~100)
      rank1..3 `sec_rank` = 그 통계량이 저자보다 «좋거나 같은» 섹터 수(자기 섹터 제외)
      ok      측정 가능 여부(S-6)
    """
    n = lab.shape[0]
    nan = np.full(n, np.nan)
    res = dict(peers=np.full(n, -1, dtype=np.int64), ok=np.zeros(n, dtype=bool),
               m1=nan.copy(), m2=nan.copy(), m3=nan.copy(),
               p1=nan.copy(), p2=nan.copy(), p3=nan.copy(),
               r1=np.full(n, -1, dtype=np.int64), r2=np.full(n, -1, dtype=np.int64),
               r3=np.full(n, -1, dtype=np.int64), G=0)
    idx = np.flatnonzero((lab >= 0) & np.isfinite(r))
    if idx.size == 0:
        return res
    l0 = lab[idx]
    r0 = r[idx]
    u0 = up[idx].astype(np.int64)
    pos0 = (r0 > 0).astype(np.int64)

    order = np.lexsort((r0, l0))          # 섹터별로 모으고 그 안에서 r 오름차순
    ls, rs = l0[order], r0[order]
    uniq, first, counts = np.unique(ls, return_index=True, return_counts=True)
    G = int(uniq.size)
    res["G"] = G
    seg = np.searchsorted(uniq, ls)
    start = first[seg]
    m = counts[seg]
    local = np.arange(idx.size) - start

    # ── 섹터 «전원» 통계량 (다른 섹터에 쓰는 값) ────────────────────────────
    half = counts // 2
    odd = (counts % 2) == 1
    med_full = np.where(odd, rs[first + half],
                        (rs[first + np.maximum(half - 1, 0)] + rs[first + half]) / 2.0)
    up_full = np.bincount(seg, weights=u0[order], minlength=G)
    pos_full = np.bincount(seg, weights=pos0[order], minlength=G)
    m3_full = pos_full / counts

    # ── 자기 제외 통계량 ────────────────────────────────────────────────────
    L = m - 1
    hi = idx.size - 1
    c = (m - 2) // 2                                    # L 이 홀수(m 짝수)일 때
    pick = np.clip(start + c + (local <= c).astype(np.int64), 0, hi)
    a = (m - 3) // 2                                    # L 이 짝수(m 홀수)일 때
    b = (m - 1) // 2
    pa = np.clip(start + a + (local <= a).astype(np.int64), 0, hi)
    pb = np.clip(start + b + (local <= b).astype(np.int64), 0, hi)
    med_loo = np.where((m % 2 == 0) & (L >= 1), rs[pick],
                       np.where((m % 2 == 1) & (L >= 2), (rs[pa] + rs[pb]) / 2.0, np.nan))
    up_loo = np.where(L >= 1, up_full[seg] - u0[order], np.nan)
    m3_loo = np.where(L >= 1, (pos_full[seg] - pos0[order]) / np.maximum(L, 1), np.nan)

    # ── 섹터간 백분위 (S-2) ─────────────────────────────────────────────────
    def rank_pct(stat_loo, stat_full):
        srt = np.sort(stat_full)
        # 저자보다 «좋거나 같은» 섹터 수 (자기 섹터 포함) → 자기 섹터를 뺀다
        ge = G - np.searchsorted(srt, stat_loo, side="left")
        own = (stat_full[seg] >= stat_loo).astype(np.int64)
        sr = ge - own
        with np.errstate(invalid="ignore", divide="ignore"):
            pct = 100.0 * (G - 1 - sr) / (G - 1) if G >= 2 else np.full_like(stat_loo, np.nan)
        return sr, pct

    r1s, p1s = rank_pct(med_loo, med_full)
    r2s, p2s = rank_pct(up_loo, up_full)
    r3s, p3s = rank_pct(m3_loo, m3_full)

    ok = (L >= 1) & (G >= 2) & np.isfinite(med_loo)
    inv = idx[order]
    res["peers"][inv] = L
    res["ok"][inv] = ok
    res["m1"][inv] = med_loo
    res["m2"][inv] = up_loo
    res["m3"][inv] = m3_loo
    for k, (rr, pp) in (("1", (r1s, p1s)), ("2", (r2s, p2s)), ("3", (r3s, p3s))):
        res["r" + k][inv] = np.where(ok, rr, -1)
        res["p" + k][inv] = np.where(ok, pp, np.nan)
    return res


def labels_for(induty, n):
    """`induty_code` 앞 `n` 자리 → 정수 라벨. 길이 < n 이면 -1(그 갈래에서 «미정» · 사유 ⑤)."""
    keys = [(s[:n] if (s is not None and len(s) >= n) else None) for s in induty]
    vocab = {k: i for i, k in enumerate(sorted({k for k in keys if k is not None}))}
    return np.array([vocab.get(k, -1) for k in keys], dtype=np.int64), vocab


# ══════════════════════════════════════════════════════════════════════════════
# 2. 귀무·대조 (§2-3 · §4-1 · §4-2)
# ══════════════════════════════════════════════════════════════════════════════
def aggregate(vals, posts):
    """글 단위 중앙 → 그 중앙(주 판정) · 건 pooled 중앙(의무 민감도). (§2-4)"""
    if len(vals) == 0:
        return None, None
    by = {}
    for v, p in zip(vals, posts):
        by.setdefault(p, []).append(v)
    per = [med(by[p]) for p in sorted(by)]
    return med(per), med(list(vals))


def null_matrix(rng, pools, posts, nrep):
    """각 건마다 그 날 풀에서 종목 1개씩 → (nrep, k) 백분위 행렬."""
    k = len(pools)
    mat = np.empty((nrep, k), dtype=np.float64)
    for j, arr in enumerate(pools):
        mat[:, j] = arr[rng.integers(0, arr.size, size=nrep)]
    return mat


def agg_matrix(mat, posts):
    """(nrep, k) → (글 단위 집계 (nrep,), pooled 집계 (nrep,))"""
    groups = {}
    for j, p in enumerate(posts):
        groups.setdefault(p, []).append(j)
    per = np.stack([np.median(mat[:, groups[p]], axis=1) for p in sorted(groups)], axis=1)
    return np.median(per, axis=1), np.median(mat, axis=1)


def binom_ge_half(k, q):
    """P(Binom(k, q) ≥ ⌈k/2⌉) — §4-2 (가) 의 산술 그대로."""
    need = -(-k // 2)
    return float(sum(comb(k, i) * q ** i * (1 - q) ** (k - i) for i in range(need, k + 1)))


def v1_axis_verdicts(EV, G1, MAIN, g1_main, NS, MEAS, MAIN_N, MAIN_M,
                     items, ap_items, b2r, full_eval):
    """§4-6 `SEC-V1` **4축** 판정 사전을 «인쇄와 분리»해서 계산한다.

    🔴 이 함수가 있는 이유 = **§3 의 `SEC-P1` 판정이 `SEC-V1` 을 참조해야 하기 때문**이다.
    `PREREG_SECTOR_COMOVE.md` §3 1행의 ⛔ 열이 `SEC-V1` 을 «판정 불가 조건»으로 열거하고
    (`:600`), §6 는 *「`SEC-V1` — 4축 중 하나가 갈림 ⇒ 갈리지 않는 글이 온다
    (잣대를 넓혀 열지 않는다)」*라고 못박는다(`:896`). 그런데 §7 은 §3 «뒤»에 인쇄되므로
    계산만 앞으로 끌어낸다. **값·문턱·갈래는 §7 과 완전히 같다**(같은 `verdict_of`).

    🔒 `SEC-V1` 의 적용 범위(`:819`)는 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」
    뿐이다 ⇒ **주 갈래의 3중 AND 가 거짓인 사건에는 관여하지 않는다**(그건 §3 이 판정).
    그래서 호출부는 `and_ok ∧ split` 일 때만 ⛔ 로 간다.
    """
    def verdict_of(E, g1r):
        if not E["vals"] or E["N1"] is None or E["B1"] is None or E["B2"]["rate"] is None:
            return None
        if g1r is not None and g1r >= G1_THR:
            return None
        return bool(E["N1"]["p_main"] < P_THR and E["B1"]["p_main"] < P_THR
                    and E["B2"]["rate"] > B2_THR)

    VD = {}
    for n in NS:                                            # 축 ① 섹터 깊이
        VD[(1, f"N={n}")] = verdict_of(EV[(n, MAIN_M)], G1[(n, MAIN_M)])
    for mk in MEAS:                                         # 축 ② 측정자
        VD[(2, mk)] = verdict_of(EV[(MAIN_N, mk)], G1[(MAIN_N, mk)])
    v_main = verdict_of(MAIN, g1_main)
    VD[(3, "글 단위 중앙")] = v_main                          # 축 ③ 집계
    p_pool_n1 = MAIN["N1"]["p_pool"] if MAIN["N1"] else None
    p_pool_b1 = MAIN["B1"]["p_pool"] if MAIN["B1"] else None
    v_pool = None
    if p_pool_n1 is not None and p_pool_b1 is not None and b2r is not None and g1_main < G1_THR:
        v_pool = bool(p_pool_n1 < P_THR and p_pool_b1 < P_THR and b2r > B2_THR)
    VD[(3, "건 pooled 중앙")] = v_pool
    VD[(4, "`exact` 만")] = v_main                           # 축 ④ 등록일 정밀도
    if ap_items:
        ap_all_items = items + ap_items
        E_ap = full_eval(ap_all_items, MAIN_N, MAIN_M)
        g1_ap = sum(1 for b in E_ap["bs"] if not b["ok"]) / len(ap_all_items)
        VD[(4, "`approx` 포함")] = verdict_of(E_ap, g1_ap)
    else:
        VD[(4, "`approx` 포함")] = v_main
    kinds = {str(v): v for v in VD.values()}
    return {"VD": VD, "kinds": kinds, "split": len(kinds) > 1}


def load_day(cur, d, SEC, final_pseudo):
    """등록일 `d` 한 날치 — 🔴 **두 모드가 «같은 함수»를 쓴다**(정의가 갈리지 않게).

    내용은 배선 점검판에서 «글자 그대로» 옮긴 것이며 계산은 하나도 바뀌지 않았다.
    """
    lo = (np.datetime64(d) - np.timedelta64(20, "D")).astype(str)
    cur.execute(
        "WITH u AS (SELECT stock_code, date, high, close, trading_value, market_cap, "
        "  LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close "
        "  FROM daily_prices WHERE date BETWEEN %s AND %s AND close > 0) "
        "SELECT stock_code, high, close, trading_value, market_cap, prev_close FROM u "
        "WHERE date = %s AND market_cap IS NOT NULL AND market_cap > 0 "
        "AND NOT (stock_code = ANY(%s)) ORDER BY stock_code",
        (lo, d, d, final_pseudo))
    raw = cur.fetchall()
    uni = [r[0] for r in raw]
    # S-1 배선 확인 — 복제본에 `prev_close` 필터를 걸면 동결 함수와 «집합으로» 같아야 한다
    frozen = {r[0] for r in load_universe_day(cur, d)}
    mine = {r[0] for r in raw if r[5] is not None and float(r[5]) > 0}
    joined = [c for c in uni if c in SEC]
    jset = set(joined)
    code_i = {c: i for i, c in enumerate(joined)}
    high = np.array([float(r[1]) if r[1] is not None else np.nan for r in raw if r[0] in jset])
    close = np.array([float(r[2]) for r in raw if r[0] in jset])
    prevc = np.array([float(r[5]) if r[5] is not None else np.nan for r in raw if r[0] in jset])
    with np.errstate(invalid="ignore", divide="ignore"):
        r_ = close / prevc - 1.0
        up_ = high >= prevc * UP_MULT
    up_ = np.where(np.isfinite(prevc) & np.isfinite(high), up_, False)
    rec = dict(
        uni=uni, joined=joined, code_i=code_i, r=r_, up=up_, high=high, close=close,
        prevc=prevc, induty=[SEC[c] for c in joined],
        raw_n=universe_raw_count(cur, d), frozen_n=len(frozen),
        s1_ok=(frozen == mine), s1_diff=len(frozen ^ mine),
        prev_miss_join=int(np.sum(~np.isfinite(prevc))),
        nup=[c for c in joined if up_[code_i[c]]])
    induty = rec["induty"]
    rec["lab"] = {n: labels_for(induty, n)[0] for n in NS}
    rec["vocab"] = {n: labels_for(induty, n)[1] for n in NS}
    rec["st"] = {n: day_stats(rec["lab"][n], r_, up_) for n in NS}
    rec["lab3"] = rec["lab"][MAIN_N]
    return rec


def measure_case(it, n, mkey, DAY, SEC):
    """건 하나의 갈래별 측정 — 측정 불가면 `SEC-G1` 사유 ①~⑤ 를 돌려준다(§4-3)."""
    c = it["code"]
    D = DAY[it["reg"]]
    if not c:
        return dict(reason="①", ok=False)
    if c not in D["code_i"]:
        return dict(reason=("③" if c in set(D["uni"]) else "②"), ok=False)
    i = D["code_i"][c]
    ind = SEC[c]
    if len(ind) < n:
        return dict(reason="⑤", ok=False)
    st = D["st"][n]
    if not st["ok"][i]:
        return dict(reason="④", ok=False, peers=int(st["peers"][i]))
    j = {"SEC-M1": "1", "SEC-M2": "2", "SEC-M3": "3"}[mkey]
    return dict(ok=True, reason="", pct=float(st["p" + j][i]), raw=float(st["m" + j][i]),
                rank=int(st["r" + j][i]), peers=int(st["peers"][i]), G=st["G"],
                sector=ind[:n])


def pools_for(kind, n, mk, bs, its, DAY):
    """추출 풀 (S-3·S-6): 측정 가능 종목만 · 저자 종목 «자기 제외»."""
    j = {"SEC-M1": "1", "SEC-M2": "2", "SEC-M3": "3"}[mk]
    out, loss = [], []
    for it, b in zip(its, bs):
        if not b["ok"]:
            continue
        D = DAY[it["reg"]]
        st = D["st"][n]
        base = D["joined"] if kind == "N1" else D["nup"]
        idxs = [D["code_i"][c] for c in base if c != it["code"]]
        idxs = np.array(idxs, dtype=np.int64)
        okm = st["ok"][idxs]
        out.append(st["p" + j][idxs][okm])
        loss.append((len(idxs), int(okm.sum())))
    return out, loss


def x1_run(rng_perm, rng_null, reps, dates, DAY, X1_BASE, broken=False):
    """섹터 라벨을 종목 사이에서 섞고(집단 크기 분포 보존) 같은 측정자·같은 귀무를 계산."""
    rows_ = []
    for _ in range(reps):
        perm_st = {}
        for d in dates:
            D = DAY[d]
            lab = D["lab3"]
            perm_st[d] = day_stats(lab[rng_perm.permutation(lab.size)], D["r"], D["up"])
        vals, posts, pools_n, pools_b, drop = [], [], [], [], 0
        for it, D, i, ixn, ixb in X1_BASE:
            st = perm_st[it["reg"]]
            if not st["ok"][i]:
                drop += 1
                continue
            vals.append(float(st["p1"][i]))
            posts.append(it["post"])
            for ix, store in ((ixn, pools_n), (ixb, pools_b)):
                pv = st["p1"][ix][st["ok"][ix]]
                if broken and pv.size:
                    # 🔴 «일부러 고장낸» 귀무 — 추출 풀에서 상위 절반 백분위를 통째로 뺀다.
                    #    (교환가능성 파괴 ⇒ `p` 가 체계적으로 작아진다)
                    cut = pv[pv <= np.median(pv)]
                    pv = cut if cut.size else pv
                store.append(pv)
        if not vals or any(p.size == 0 for p in pools_n) or any(p.size == 0 for p in pools_b):
            continue
        obs_main, _ = aggregate(vals, posts)
        out = dict(drop=drop)
        for kind, pools in (("N1", pools_n), ("B1", pools_b)):
            gm, _ = agg_matrix(null_matrix(rng_null, pools, posts, NREP), posts)
            out[kind] = float(np.mean(gm >= obs_main))
        rows_.append(out)
    return rows_


def x1_base_for(items, DAY):
    """라벨과 «무관»한 인덱스는 실현 밖에서 한 번만 만든다(결정성·속도 둘 다)."""
    base = []
    for it in items:
        D = DAY[it["reg"]]
        if not it["code"] or it["code"] not in D["code_i"]:
            continue
        base.append((it, D, D["code_i"][it["code"]],
                     np.array([D["code_i"][c] for c in D["joined"] if c != it["code"]],
                              dtype=np.int64),
                     np.array([D["code_i"][c] for c in D["nup"] if c != it["code"]],
                              dtype=np.int64)))
    return base


def db_context(cur):
    """두 모드가 공유하는 DB·원장 문맥. 🔴 **SELECT 만.**"""
    cur.execute("SELECT max(date) FROM daily_prices")
    END = str(cur.fetchone()[0])
    cur.execute("SELECT count(*), count(DISTINCT stock_code), count(induty_code) FROM stock_industry")
    si_rows, si_uniq, si_nonnull = cur.fetchone()
    cur.execute("SELECT max(updated_at) FROM stock_industry")
    si_upd = str(cur.fetchone()[0])
    cur.execute("SELECT stock_code, induty_code FROM stock_industry ORDER BY stock_code")
    si_pairs = cur.fetchall()
    SEC = {a: b for a, b in si_pairs}
    si_sha = sha_list([f"{a}\t{b}" for a, b in si_pairs])
    cur.execute("SELECT count(*), count(sector) FROM stock_info")
    info_rows, info_sector = cur.fetchone()
    cur.execute("SELECT length(induty_code), count(*) FROM stock_industry GROUP BY 1 ORDER BY 1")
    len_all = dict(cur.fetchall())
    cur.execute("SELECT DISTINCT stock_code FROM daily_prices WHERE stock_code !~ '^[0-9]' ORDER BY 1")
    nonnum = [r[0] for r in cur.fetchall()]
    final_pseudo = sorted(set(PSEUDO) | set(nonnum))

    # 🔴 원장은 **전 행**을 읽고(`stage="post6"`), 각 모드의 분모는 아래 «명시» 글 필터가 정한다.
    #    `run_ranking.load_ledger()` 의 기본값(`stage="train"`)은 `post_date <= TRAIN_FREEZE_DATE`
    #    로 잘라 주지만, 이 축은 **자기 필터를 «따로» 갖는다** — 두 겹이어야 한 겹이 바뀌어도 안 샌다.
    rows = load_ledger("post6")
    codes, _ = build_codes(include_post6=True)
    # 🔴 두 독립 매핑(`run_ranking.POST6_CODES` ↔ `run_regday_post6.POST6_NEW`)이 «같은지» 대조한다.
    #    다르면 즉시 멈춘다 — 조용한 덮어쓰기 금지(새 매핑 0건).
    for nm, c, _reg in POST6_NEW:
        if codes.get(nm, c) != c:
            raise SystemExit(f"🔴 종목코드 충돌: {nm} {codes[nm]} ↔ {c}")
        codes[nm] = c
    items_all, post_idx = exact_items(rows, codes)
    ap_all = approx_items(rows, codes, post_idx)
    return dict(END=END, si_rows=si_rows, si_uniq=si_uniq, si_nonnull=si_nonnull, si_upd=si_upd,
                si_sha=si_sha, info_rows=info_rows, info_sector=info_sector, len_all=len_all,
                nonnum=nonnum, final_pseudo=final_pseudo, SEC=SEC, rows=rows,
                items_all=items_all, ap_all=ap_all, post_idx=post_idx)


# ══════════════════════════════════════════════════════════════════════════════
# 3. 배선 점검 모드 (post1~5 «만» · §0-4 4번)
# ══════════════════════════════════════════════════════════════════════════════
def main(cur, ctx):                                           # noqa: PLR0912, PLR0915
    t_start = time.time()
    ART = ART_DRYRUN
    ART.mkdir(exist_ok=True)

    END = ctx["END"]
    si_rows, si_uniq, si_nonnull = ctx["si_rows"], ctx["si_uniq"], ctx["si_nonnull"]
    si_upd, si_sha = ctx["si_upd"], ctx["si_sha"]
    info_rows, info_sector, len_all = ctx["info_rows"], ctx["info_sector"], ctx["len_all"]
    nonnum, final_pseudo, SEC = ctx["nonnum"], ctx["final_pseudo"], ctx["SEC"]

    # 🔴🔴 **명시 필터** — 배선 점검의 분모는 **post1~5 «만»**이다(§0-4 4번 · `SEC-O1`).
    #     원장에 post6 행이 append 돼도 이 산출물은 움직이지 않는다.
    items = [it for it in ctx["items_all"] if it["post"] in TRAIN_POSTS]
    ap_items = [it for it in ctx["ap_all"] if it["post"] in TRAIN_POSTS]
    leaked = sorted({it["log_no"] for it in items + ap_items} & {POST6_LOG_NO})
    if leaked:
        raise SystemExit(f"🔴 배선 점검 분모에 post6 이 샜다: {leaked}")
    dates = sorted({it["reg"] for it in items})
    all_dates = sorted({it["reg"] for it in items + ap_items})

    # ── 등록일별 데이터 적재 ────────────────────────────────────────────────
    DAY = {d: load_day(cur, d, SEC, final_pseudo) for d in all_dates}

    # ══════════════════════════════════════════════════════════════════════
    # §0
    # ══════════════════════════════════════════════════════════════════════
    say("# `SEC-` 섹터 동반 상승 — **배선 점검** 수치 원본 (post1~5 «만»)")
    say()
    for ln in NOTATION:
        say("> " + ln)
    say()
    say("🔴 **이 파일에는 6번째 글에 대한 수치가 «하나도» 없다** — 실행 시점에 그 글은 "
        "존재하지 않는다(`PREREG_SECTOR_COMOVE.md` §0-4 4번).")
    say()
    say("## §0. 실행 문맥")
    say()
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 사전등록 | `PREREG_SECTOR_COMOVE.md` (동결 · `SEC-D1`~`D8` 확정 2026-09-02) |")
    say("| 단계 | `PREREG_SECTOR_COMOVE.md` §0-4 **4번(배선 점검)** — 🔴 훈련 아님·규칙 선택 없음 |")
    say("| 실행 브랜치 | `fix/tasso-post6-s5-fixes` (🔴 해시는 stdout 전용 — 본문에 박으면 `--rerun` 이 구조적으로 깨진다) |")
    say(f"| **DB 스냅샷 최신 봉** | **`{END}`** (`daily_prices` `max(date)`) |")
    say(f"| `stock_industry` 스냅샷 (§7-B #22) | **{si_rows:,}행** · 고유 `stock_code` {si_uniq:,} · "
        f"`induty_code` non-NULL {si_nonnull:,} · `max(updated_at)` **{si_upd}** |")
    say(f"| 〃 sha256(전체 `stock_code`↔`induty_code`) | `{si_sha[:32]}…` |")
    say("| 주 판정 갈래 | 🔒 **`N = 3` · `SEC-M1`** (`SEC-D1`·`D2` · 사장님 확정 2026-09-02) |")
    say(f"| 시드 · 반복 | `{SEED}` · **{NREP:,}회** — ⚠️ `run_selection.py:22` 는 `NREP = 2000` 이다"
        f"(§2-3 고지 · 이 축은 «더 큰 쪽»을 쓴다) |")
    say(f"| 시드 스트림 분리 | `SeedSequence({SEED}).spawn()` → `{'`·`'.join(_STREAM_NAMES)}` "
        "(§2-3 «필수» 승계) |")
    say(f"| `SEC-X1` 독립 실현 | **{X1_REP}** (`RESULTS_RANKING_TRAIN.md` §5 «승계») |")
    say(f"| 의사티커 제외 | **{len(final_pseudo)}종** {'·'.join('`%s`' % p for p in final_pseudo)} — "
        f"`run_selection.py:23` `PSEUDO`({len(PSEUDO)}) ∪ DB 실측(숫자로 시작하지 않는 `stock_code` "
        f"{len(nonnum)}종) ⇒ **같다**(§5 4번 · §7-B #19) |")
    say("| 유니버스 | `PREREG_RANKING.md` §2-1 승계(`market_cap > 0 ∧ close > 0` · 의사티커 제외) "
        "**∩ 섹터코드 존재**(`SEC-D3`) |")
    say(f"| `exact` 건 | **{len(items)}건** (post2 {sum(1 for i in items if i['post'] == 2)} · "
        f"post3 {sum(1 for i in items if i['post'] == 3)} · post4 {sum(1 for i in items if i['post'] == 4)} · "
        f"post5 {sum(1 for i in items if i['post'] == 5)}) · `approx` **{len(ap_items)}건**(민감도) · "
        "`after` **제외**(`SEC-D5`) |")
    say(f"| 등록일 | **{len(dates)}일** (`exact`) · `approx` 포함 {len(all_dates)}일 |")
    say()
    say("🔴 **`SEC-O1` 자유도 신고** — 잣대 선택(`SEC-D1` `N` 3후보 × `SEC-D2` 측정자 3후보 = **9 조합**)의 "
        "자유도가 이 축의 거의 전부이며, 그 결정은 **이 실행 «전»**(2026-09-02 §0-6)에 동결됐다. "
        "**9 조합을 다 인쇄하되 판정 갈래는 «동결된 하나»뿐이다.**")
    say()
    say("| 열 | 뜻 |")
    say("|---|---|")
    say("| 훈련(post1~5) | 🔬 **탐색적 표기** — 판정 분모에 **넣지 않는다** |")
    say("| 검증(post6~ 누적) | ⬜ **미존재** — 6번째 글은 이 실행 시점에 없다 |")

    # ══════════════════════════════════════════════════════════════════════
    # §1 실측 재현
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §1. 사전등록 §1 실측 «재현» — 값이 어긋나면 그 자리에 적는다")
    say()
    say("### 1-1. `stock_industry` 기본 (§1-1)")
    say()
    say("| 항목 | 문서값(2026-09-01) | 이 실행 | 일치 |")
    say("|---|---|---|---|")
    say(f"| 행 수 | 2,556 | **{si_rows:,}** | {'✅' if si_rows == 2556 else '🔴'} |")
    say(f"| 고유 `stock_code` | 2,556 | **{si_uniq:,}** | {'✅' if si_uniq == 2556 else '🔴'} |")
    say(f"| `induty_code` non-NULL | 2,556 / 2,556 | **{si_nonnull:,} / {si_rows:,}** | "
        f"{'✅' if si_nonnull == si_rows else '🔴'} |")
    say(f"| `stock_info.sector` non-NULL | **0** / 2,115 | **{info_sector:,} / {info_rows:,}** | "
        f"{'✅' if info_sector == 0 else '🔴'} |")
    say()
    say("⇒ 🔴 **대안 컬럼은 «없다»** — 이 축의 섹터 축은 `stock_industry.induty_code` 단일이며 "
        "**폴백이 없다**(§1-1 · §8-3).")
    say()
    say("### 1-2. `induty_code` 길이 분포 — `N = 5` 를 무너뜨리는 사실 (§1-2)")
    say()
    d21 = DAY["2026-08-21"]
    ln21 = {}
    for s in d21["induty"]:
        ln21[len(s)] = ln21.get(len(s), 0) + 1
    say("| 길이 | 표 전체(문서 / 이 실행) | 2026-08-21 조인 유니버스(문서 / 이 실행) |")
    say("|---|---|---|")
    for L, doc_a, doc_b in ((3, 1070, 1054), (4, 300, 299), (5, 1186, 1177)):
        say(f"| {L}자리 | {doc_a:,} / **{len_all.get(L, 0):,}** | {doc_b:,} / **{ln21.get(L, 0):,}** |")
    lt5_all = sum(v for k, v in len_all.items() if k < 5)
    lt5_21 = sum(v for k, v in ln21.items() if k < 5)
    say(f"| **5자리 미만 합** | 1,370 / **{lt5_all:,}** | 1,353 / **{lt5_21:,}** "
        f"(**{lt5_21 / len(d21['joined']) * 100:.1f}%**) |")
    say()
    say("🔴🔴 ***`left(induty_code, 5)` 는 3자리 코드에 «그 코드 자신»을 돌려준다*** — `N = 5` 는 "
        "분류 체계가 다른 두 깊이를 한 칸에 섞는다. 최소 길이가 3이므로 **`N ≤ 3` 만 «모든 코드에 대해 "
        "정의»된다**(§2-1 1번). ⇒ 구조가 주는 것은 **상한 `N ≤ 3`** 뿐이고 `N = 3` 채택은 «선택»이다(M1).")
    say()
    say("### 1-3. 유니버스 조인 커버리지 · `prev_close` · `n_up` — 등록일 11개 전수 (§1-3)")
    say()
    say("| 등록일 | 유니버스 | 섹터 조인 | 커버리지 | 🔴 조인 후 `prev_close` 없음 | `n_up` | `n_up` ∩ 조인 | S-1 동결함수 일치 |")
    say("|---|---|---|---|---|---|---|---|")
    doc13 = {"2026-07-28": (2570, 2533, 0, 54, 54), "2026-07-30": (2570, 2533, 0, 68, 66),
             "2026-08-05": (2763, 2533, 0, 99, 93), "2026-08-06": (2763, 2533, 0, 57, 53),
             "2026-08-11": (2761, 2531, 0, 92, 91), "2026-08-12": (2762, 2531, 0, 88, 86),
             "2026-08-13": (2763, 2531, 0, 66, 66), "2026-08-18": (2763, 2530, 0, 80, 76),
             "2026-08-19": (2763, 2530, 0, 53, 51), "2026-08-20": (2763, 2530, 0, 86, 79),
             "2026-08-21": (2764, 2530, 0, 47, 44)}
    mismatch13 = []
    for d in dates:
        D = DAY[d]
        rowsu = load_universe_day(cur, d)
        nup_full = [sc for sc, hi, cl, tv, mc, pc in rowsu
                    if hi is not None and pc and float(hi) >= float(pc) * UP_MULT
                    and tv is not None and mc]
        nup_all = len(nup_full)
        nup_j = sum(1 for c in nup_full if c in SEC)
        cov = len(D["joined"]) / len(D["uni"]) * 100
        doc = doc13[d]
        bad = [(nm, b, a) for nm, a, b in
               (("유니버스", len(D["uni"]), doc[0]), ("섹터 조인", len(D["joined"]), doc[1]),
                ("조인 후 `prev_close` 없음", D["prev_miss_join"], doc[2]),
                ("`n_up`", nup_all, doc[3]), ("`n_up` ∩ 조인", nup_j, doc[4])) if a != b]
        if bad:
            mismatch13.append((d, bad))
        say(f"| {d} | {len(D['uni']):,} | {len(D['joined']):,} | **{cov:.2f}%** | "
            f"**{D['prev_miss_join']}** | {'🔴 **' + str(nup_all) + '**' if bad else nup_all} | "
            f"{nup_j} | {'✅' if D['s1_ok'] else '🔴 차 %d' % D['s1_diff']} |")
        D["nup_full"] = nup_all
        D["nup_join"] = nup_j
    say()
    n_s1 = sum(1 for d in dates if DAY[d]["s1_ok"])
    n_pm = sum(1 for d in dates if DAY[d]["prev_miss_join"] == 0)
    say("- 🟢 **S-1 배선 확인**: 이 스크립트의 `prev_close` 복제본에 `prev_close IS NOT NULL AND > 0` 을 "
        "걸면 `run_regday_post5.load_universe_day`(동결 함수, **import 해서 호출**)와 **집합으로 같다** — "
        f"**{n_s1}/{len(dates)} 등록일**"
        f"{' ✅ 전부(차집합 크기 0)' if n_s1 == len(dates) else ' 🔴 어긋난 날이 있다'}. "
        "⇒ 20«일력»일 창 정의가 «글자 그대로» 복제됐다(§1-3).")
    say(f"- {'🟢' if n_pm == len(dates) else '🔴'} **`prev_close` 결손이 "
        f"{n_pm}/{len(dates)} 등록일에서 «전부 0»**(§1-4 재현) ⇒ `SEC-D7`(종가 대비 수익률)은 "
        "`RNK-N2` 가 겪은 ⛔ 경로를 «만들지 않는다».")
    if mismatch13:
        say()
        say("#### 🔴 정오 등재 — 사전등록 §1-3 표의 «재현되지 않는» 셀")
        say()
        say("🔒 **`PREREG_SECTOR_COMOVE.md` 는 동결본이므로 «고치지 않고» 여기 기록만 한다**"
            "(§8-A 가 `RESULTS_RANKING_TRAIN.md` 에 한 처리와 같은 형식).")
        say()
        say("| 등록일 | 어긋난 열 | 문서값 | 이 실행 | 판정 영향 |")
        say("|---|---|---|---|---|")
        for d, bad in mismatch13:
            for nm, doc_v, mine_v in bad:
                say(f"| {d} | {nm} | **{doc_v}** | **{mine_v}** | 🟢 **없음** — 아래 근거 |")
        say()
        say("- 🟢 **판정에 쓰는 양은 «`n_up` ∩ 조인»(= `SEC-B1` 추출 풀)이고 그 열은 11/11 재현된다.** "
            "사전등록 자신의 §2-3 이 풀을 *「실측 **44~93**」*으로, §4-2 (가) 표가 08-05 풀을 **93** 으로 "
            "적었는데 **둘 다 이 실행의 값과 일치**한다.")
        say("- 🔴 **그리고 동결 산출물 `RESULTS_REGDAY_POST5.md` §5 는 광전자 08-05 의 `n_up` 을 "
            "«93»으로 적었다** — 즉 어긋난 셀은 **사전등록 §1-3 의 그 한 칸뿐**이고, 계열의 다른 "
            "동결본·이 실행·사전등록의 나머지 인용이 전부 **93** 으로 일치한다.")
        say("- ⚠️ **어느 정의로도 99 가 나오지 않는다**(실측): 20일력일 창 `LAG` ⇒ **93** · "
            "전 기간 `LAG` ⇒ **98** · `2026-04-01` 이후 `LAG` ⇒ **93**. "
            "🔑 ***「분모가 다르다」가 아니라 「그 값이 재현되지 않는다」로 적는다.***")
    say()
    say("#### 07-30 → 08-05 코호트 넷 (§1-3 M4·M5) — 혼용 금지")
    say()
    u05 = set(DAY["2026-08-05"]["uni"])
    u30 = set(DAY["2026-07-30"]["uni"])
    cur.execute("SELECT stock_code, min(date) FROM daily_prices GROUP BY 1")
    firstbar = dict(cur.fetchall())
    A = {c for c in u05 if str(firstbar.get(c)) == "2026-08-05"}
    cur.execute("SELECT stock_code FROM daily_prices WHERE date=%s", ("2026-08-05",))
    B = u05 - {r[0] for r in load_universe_day(cur, "2026-08-05")}
    C = u05 - u30
    Dset = {c for c in u05 if c not in SEC}
    say("| 집합 | 정의 | 문서값 | 이 실행 |")
    say("|---|---|---|---|")
    say(f"| **A** | 전 기간 **첫 봉이 08-05** | 183 | **{len(A)}** |")
    say(f"| **B** | 🔴 `prev_close` 결손(20일력일 창) | 191 | **{len(B)}** |")
    say(f"| **C** | 07-30 대비 유니버스 **신규 진입** | 193 | **{len(C)}** |")
    say(f"| **D** | **섹터코드 부재** | 230 | **{len(Dset)}** |")
    say()
    inc = (A <= B) and (B <= C) and (C <= Dset)
    say(f"🔒 **포함 관계 `A ⊂ B ⊂ C ⊂ D`** — 양방향 차분 실측 ⇒ **{'✅ 성립' if inc else '🔴 불성립'}** "
        f"(`B∖A` = {len(B - A)}종목 · `C∖B` = {len(C - B)}종목 {sorted(C - B)} · `D∖C` = {len(Dset - C)}종목).")
    say(f"- 🟢 **`B ⊂ D`** ⇒ `prev_close` 결손 {len(B)}종목이 섹터 조인에서 **이미 전부 빠진다** "
        "⇒ 위 표의 「조인 후 결손 0」이 **두 창 정의 어느 쪽으로도** 성립한다.")
    say(f"- 🔴 **`D ⊋ C`**(차 {len(Dset - C)}종목) ⇒ ***「섹터 부재 = 신규 진입」은 «거짓»이다*** — "
        "포함이지 상등이 아니다(§1-3 정정 승계).")
    say(f"- 🔑 ***같은 이름의 「선행봉 결손」이 창 정의에 따라 {len(A)}(전 기간) / {len(B)}(20일력일)로 "
        "갈린다*** — 창을 안 적으면 재현이 안 된다.")
    if len(B) != 191:
        say()
        say(f"#### 🔴 `B` 가 191 → {len(B)} 로 움직였다 — **DB 가 움직인 것이다**(정오 아님 · `created_at` 실증)")
        say()
        DOC_BA = {"00104K", "00279K", "02826K", "03473K", "28513K", "33626K", "37550K", "37550L"}
        gone = sorted(DOC_BA - (B - A))
        added = sorted((B - A) - DOC_BA)
        say(f"사전등록 §1-3 이 적은 `B∖A` **{len(DOC_BA)}종목** 중 **{len(gone)}종목** {gone} 이 "
            f"이 실행에서는 `B` 에 «없다» (새로 들어온 종목 {added if added else '0건'}).")
        for c in gone:
            cur.execute("SELECT min(date), max(date), min(created_at), max(created_at) "
                        "FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s",
                        (c, "2026-07-16", "2026-08-04"))
            r0 = cur.fetchone()
            say(f"- `{c}` — 창 `2026-07-16`~`08-04` 봉 **존재**({r0[0]}~{r0[1]}) · "
                f"그 봉들의 `created_at` = **{r0[2]}** ⇒ ***사전등록 측정일(2026-09-01) «뒤»에 적재됐다.***")
        cur.execute("SELECT count(*), count(*) FILTER (WHERE updated_at >= '2026-09-02') "
                    "FROM daily_prices WHERE date='2026-08-05'")
        tot_u, upd_u = cur.fetchone()
        say(f"- ⚠️ **`updated_at` 은 포렌식에 못 쓴다**(실측): `2026-08-05` 의 **{tot_u:,}행 전부**"
            f"({upd_u:,}/{tot_u:,})가 `updated_at ≥ 2026-09-02` 다 — 전행 일괄 갱신이다. "
            "***`created_at` 만이 「언제 처음 들어왔나」를 말한다.***")
        say("- 🔑 계열 규칙 재확인 — ***섹터 표만 「자라는」 게 아니라 «가격 표»도 자란다.*** "
            "`PREREG_SECTOR_COMOVE.md` §2-6 이 *「매일 돌리면 … 같은 글의 값이 날마다 달라진다」*고 "
            "적은 그 사건이 **사전등록 작성 다음날에 실제로 일어났다.**")

    # 1-5 저자 종목 섹터 커버리지
    say()
    say("### 1-5. 저자 종목의 섹터 커버리지 (§1-5)")
    say()
    say("| 글 | 항목 | 종목 | `stock_code` | `induty_code` | 길이 | `N=3` 칸 | 유니버스 | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for it in items:
        c = it["code"]
        D = DAY[it["reg"]]
        ind = SEC.get(c) if c else None
        in_uni = bool(c) and c in set(D["uni"])
        reason = ("①" if not c else ("②" if not in_uni else ("③" if ind is None else "")))
        say(f"| {it['post']} | {it['item_no']} | {it['name']} | `{c or '—'}` | "
            f"`{ind or '—'}` | {len(ind) if ind else '—'} | `{ind[:3] if ind else '—'}` | "
            f"{'✅' if in_uni else '🔴'} | {reason or '—'} |")
    say()

    # ── 갈래별 측정 (9 조합) ───────────────────────────────────────────────
    BR = {}
    for n in NS:
        for mk in MEAS:
            BR[(n, mk)] = [measure_case(it, n, mk, DAY, SEC) for it in items]
            BR[("ap", n, mk)] = [measure_case(it, n, mk, DAY, SEC) for it in ap_items]

    say("### 1-6. 집단 크기 분포 (2026-08-21 · 조인 유니버스) — `N` 선택의 실측 배경 (§1-6)")
    say()
    say("🔴 「집단가중 중앙」은 «집단»을 하나씩 센 것이고 아래 저자 표의 「중앙」은 «종목»을 하나씩 "
        "센 것이다 — **두 「중앙」은 서로 다른 양이다**(M6 정정). 섞어 읽지 않는다.")
    say()
    say("🔴🔴 **`N = 5` 는 «정의가 둘»이다** — ①사전등록 §1-6 표는 `left(induty_code, 5)` 를 **글자 그대로** "
        "쓴 값이고(길이 3·4 코드가 «그 코드 자신»으로 한 칸이 된다) ②사전등록 §2-1 은 *「`N = 5` 를 "
        "정직하게 쓰려면 길이 5 미만 코드는 「그 층에서 미정」 = 측정 불가로 세야 한다」*고 못 박았다. "
        "🔴 ***이 스크립트의 측정은 ②를 쓴다***(§4-3 사유 ⑤가 그것을 요구한다). **둘 다 인쇄한다.**")
    say()
    say("| `N` | 정의 | 집단 수 | 최대 | 집단가중 중앙 | 🔴 동료 0 (측정 불가) | 동료 ≤ 1 | 동료 ≤ 4 | "
        "🔴 층에서 미정(길이 < `N`) | 문서값(§1-6) |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    NJ = len(d21["joined"])
    DOC16 = {2: "60 · 289 · 15.5 · 4 · 10 · 35", 3: "158 · 177 · 6 · 26 · 64 · 177",
             5: "524 · 94 · 2 · 217 · 401 · 811"}

    def size_row(keys):
        vocab = sorted({k for k in keys if k is not None})
        vi = {k: i for i, k in enumerate(vocab)}
        cnts = np.bincount([vi[k] for k in keys if k is not None], minlength=len(vocab))
        pv = np.array([cnts[vi[k]] - 1 for k in keys if k is not None])
        return (len(vocab), int(cnts.max()), med(list(cnts)),
                int(np.sum(pv == 0)), int(np.sum(pv <= 1)), int(np.sum(pv <= 4)),
                int(sum(1 for k in keys if k is None)))
    for n in NS:
        variants = [("🔒 이 실행(§2-1 정직 정의)",
                     [(s[:n] if len(s) >= n else None) for s in d21["induty"]])]
        if n == 5:
            variants.append(("(문서 §1-6) `left(,5)` 글자 그대로",
                             [s[:n] for s in d21["induty"]]))
        for lbl, keys in variants:
            g, mx, md_, p0, p1, p4, und = size_row(keys)
            doc = DOC16[n] if (n != 5 or "left" in lbl) else "—(문서는 아래 행)"
            say(f"| **{n}** | {lbl} | {g:,} | {mx:,} | **{md_:.1f}** | "
                f"{p0} (**{p0 / NJ * 100:.1f}%**) | {p1} ({p1 / NJ * 100:.1f}%) | "
                f"{p4} ({p4 / NJ * 100:.1f}%) | {und:,} ({und / NJ * 100:.1f}%) | {doc} |")
    say()
    say("⇒ 🟢 **`N = 2`·`N = 3` 은 문서값과 «전부» 일치**하고, **`N = 5` 는 «글자 그대로» 정의에서만 "
        "문서값(524 · 94 · 2 · 217 · 401 · 811)이 재현된다.** "
        "🔑 ***같은 이름(`N = 5`)이 문서 안에서 두 양을 가리킨다*** — §1-6 은 ①, §2-1·§4-3 은 ②. "
        "판정에 쓰는 것은 ②이고, 그래서 이 축의 `N=5` 갈래 측정 불가가 **61.1%** 다(§5).")
    say()
    say("#### 🟢 M6 — 귀무가 «자연히» 크기 정합인가 (§1-6 실측 재현)")
    say()
    say("| 잣대 | 문서값 | 이 실행 |")
    say("|---|---|---|")
    permed = [med([int(x) for x in DAY[d]["st"][3]["peers"][DAY[d]["st"][3]["peers"] >= 0]])
              for d in dates]
    say(f"| `SEC-N1` 풀(전 종목)의 **종목가중** 동료 중앙 (`N=3`) | **49.0** (11일 전부 동일) | "
        f"**{med(permed):.1f}** (등록일별 {min(permed):.0f}~{max(permed):.0f} · "
        f"{'전부 동일 ✅' if len(set(permed)) == 1 else '🔴 날짜별로 다르다'}) |")
    au_peers = [b["peers"] for b in BR[(3, "SEC-M1")] if b["ok"]]
    say(f"| **저자 {len(au_peers)}건**의 동료 중앙 (`N=3`) | **49** | **{med(au_peers):.0f}** "
        f"({med_note(len(au_peers))}) |")
    b1med = []
    for d in dates:
        st = DAY[d]["st"][3]
        pv = [int(st["peers"][DAY[d]["code_i"][c]]) for c in DAY[d]["nup"]
              if st["ok"][DAY[d]["code_i"][c]]]
        b1med.append(med(pv) if pv else np.nan)
    say(f"| `SEC-B1` 풀(`n_up`)의 종목가중 동료 중앙 | 날짜별 **27 ~ 70** · 날짜간 중앙 **50** | "
        f"날짜별 **{min(b1med):.0f} ~ {max(b1med):.0f}** · 날짜간 중앙 **{med(b1med):.1f}** |")
    say()
    say("⇒ 🟢 ***귀무 추출 종목의 동료 수 분포가 저자 종목의 그것과 «중앙에서 일치»하면*** "
        "「저자 종목이 유난히 큰/작은 섹터에 있어서 유리했다」가 **구조적으로 배제**된다 — "
        "🔑 이건 **추출 설계의 성질**이지 우리가 고른 변환이 아니다(§2-2 m9).")
    say()
    say("**저자 종목의 동료 수** (등록일 기준 · 섹터코드 있는 건 · **종목가중** · 🔬 탐색적)")
    say()
    say("| `N` | 정의 | 최소 | **중앙** | 최대 | 동료 0 인 건 | 측정 가능 건 | 문서값(§1-6) |")
    say("|---|---|---|---|---|---|---|---|")
    DOC_AU = {2: "30(코데즈컴바인) · 166 · 288", 3: "23(금호건설) · 49 · 176(마키나락스)",
              5: "6(코데즈컴바인) · 8 · 58(마키나락스)"}
    for n in NS:
        variants = [("🔒 §2-1 정직 정의", n, False)]
        if n == 5:
            variants.append(("(문서 §1-6) `left(,5)` 글자 그대로", n, True))
        for lbl, nn, literal in variants:
            pv = []
            for it in items:
                c = it["code"]
                D = DAY[it["reg"]]
                if not c or c not in D["code_i"]:
                    continue
                ind = SEC[c]
                key = ind[:nn] if (literal or len(ind) >= nn) else None
                if key is None:
                    continue
                cnt = sum(1 for s in D["induty"] if (s[:nn] if literal else
                          (s[:nn] if len(s) >= nn else None)) == key)
                pv.append((cnt - 1, it["name"]))
            if not pv:
                continue
            vals = [x for x, _ in pv]
            say(f"| {n} | {lbl} | {min(vals)} ({min(pv)[1]}) | **{med(vals):.0f}** | "
                f"{max(vals)} ({max(pv)[1]}) | **{sum(1 for x in vals if x == 0)}건** | "
                f"{len(vals)} | {DOC_AU[n] if (n != 5 or literal) else '—(아래 행)'} |")
    say()
    say("🔴 **이 표에는 «동반 상승 측정자 값»이 하나도 없다** — 잰 것은 **동료 수**뿐이다(§1-6 말미).")

    # ══════════════════════════════════════════════════════════════════════
    # §2 drop_rate 표기 가드 (§5 6-1)
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §2. `drop_rate` **표기 가드** (§5 6-1 · `PREREG_POST6.md` §5-2 «원 용도»)")
    say()
    say("🔴 **`1%` 는 «표시» 문턱이지 «판정» 게이트가 아니다.** "
        "🔑 ***0 이라서 안 재는 게 아니라, 0 임을 매회 «보여서» 이 조항이 살아 있음을 증명한다.***")
    say()
    say("| 등록일 | 그날 `market_cap>0` | 검정 유니버스 | 탈락 | 탈락률 | 🔴 섹터 조인 «후» 탈락 |")
    say("|---|---|---|---|---|---|")
    for d in dates:
        D = DAY[d]
        drop = D["raw_n"] - D["frozen_n"]
        rate = drop / D["raw_n"]
        say(f"| {d} | {D['raw_n']:,} | {D['frozen_n']:,} | "
            f"{'🔴 **' + format(drop, ',') + '**' if rate >= DROP_MARK else drop} | "
            f"{rate * 100:.2f}%{' 🔴' if rate >= DROP_MARK else ''} | **{D['prev_miss_join']}** |")
    say()
    marked = [d for d in dates if (DAY[d]["raw_n"] - DAY[d]["frozen_n"]) / DAY[d]["raw_n"] >= DROP_MARK]
    say(f"- 🔴 **표시가 붙은 날 {len(marked)}일**" +
        (" (" + " · ".join("`%s`" % x for x in marked) + ")" if marked else "") +
        " — 그날의 `n_up` 을 **다른 날과 직접 비교하지 말 것**(원 문언 그대로).")
    say("- 🟢 **섹터 조인 «후» 탈락은 11/11 등록일 0** ⇒ 이 축의 수익률 정의역에는 구멍이 없다.")

    # ══════════════════════════════════════════════════════════════════════
    # §3 건별 측정값
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §3. 건별 측정값 — 🔬 **탐색적 표기** · 주 판정 갈래 (`N = 3` · `SEC-M1`)")
    say()
    say("🔴 **§2-4 대로 «분모»를 매 건 인쇄한다** — `|P|`(동료 수) · `G`(그날 섹터 수) · "
        "`sec_rank`(자기 섹터 제외, 동률 전부 위) · **원값**(`med`).")
    say("🔴 **`sec_rank` 에 문턱을 «걸지 않는다»**(§2-2) — `RNK-N2` 의 **30** 은 ≈2,760종목을 재던 값이고 "
        "여기 섹터는 `N=3` 에서 158개 남짓뿐이다.")
    say()
    say("| 글 | 종목 | 등록일 | 섹터(`N=3`) | `|P|` | `G` | `sec_rank` | 원값 `med` | "
        "**`SEC-M1` 백분위** | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for it, b in zip(items, BR[(MAIN_N, MAIN_M)]):
        if b["ok"]:
            say(f"| {it['post']} | {it['name']} | {it['reg']} | `{b['sector']}` | {b['peers']} | "
                f"{b['G']} | {b['rank']} | {b['raw'] * 100:+.3f}% | **{b['pct']:.1f}** | — |")
        else:
            say(f"| {it['post']} | {it['name']} | {it['reg']} | — | "
                f"{b.get('peers', '—')} | — | — | — | ⛔ 측정 불가 | **{b['reason']}** |")
    say()
    say("### 3-1. 9 조합 전부 (`SEC-O1` §4-5 — 판정은 «동결된 하나»로만)")
    say()
    say("| `N` | 측정자 | 측정 가능 | 건별 백분위(글 순) | 글 단위 중앙 | **전체(글 단위 중앙의 중앙)** | 건 pooled 중앙 |")
    say("|---|---|---|---|---|---|---|")
    AGG = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            vals = [b["pct"] for b in bs if b["ok"]]
            posts = [it["post"] for it, b in zip(items, bs) if b["ok"]]
            main_v, pooled = aggregate(vals, posts)
            AGG[(n, mk)] = dict(vals=vals, posts=posts, main=main_v, pooled=pooled)
            by = {}
            for v, p in zip(vals, posts):
                by.setdefault(p, []).append(v)
            per = " / ".join(f"p{p}:{med(by[p]):.1f}" for p in sorted(by))
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {len(vals)}/{len(items)} | "
                f"{', '.join(f'{v:.1f}' for v in vals)} | {per} | "
                f"**{fmt(main_v)}** | {fmt(pooled)} |")
    say()
    say("🔒 **판정 갈래 = `N = 3` · `SEC-M1`**(🔒 표시). 나머지 8 조합은 `SEC-V1` 의 «입력»이며 "
        "**판정에 쓰지 않는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §4 귀무·대조
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §4. 귀무 `SEC-N1` · 대칭 대조 `SEC-B1`·`SEC-B2`")
    say()

    say("### 4-0. 추출 풀 한정 손실 (§2-3 — 🔴 «유리한 방향의 처리는 반드시 «크기»를 같이 적는다»)")
    say()
    say("| 갈래 | 풀 | 후보 합계 | 측정 가능 합계 | 한정으로 빠진 수 | 비율 |")
    say("|---|---|---|---|---|---|")
    for n in NS:
        for kind, nm in (("N1", "`SEC-N1` 전 종목"), ("B1", "`SEC-B1` `n_up`")):
            _, loss = pools_for(kind, n, MAIN_M, BR[(n, MAIN_M)], items, DAY)
            tot = sum(a for a, _ in loss)
            keep = sum(b for _, b in loss)
            say(f"| `N={n}` | {nm} | {tot:,} | {keep:,} | **{tot - keep:,}** | "
                f"{(tot - keep) / tot * 100:.1f}% |")
    say()
    say("🔴 이 한정은 **저자 쪽에 «유리»한 방향**이다(저자 종목은 전부 동료 ≥ 1). 그래서 크기를 적는다.")
    say()
    say("### 4-1. `SEC-N1` · `SEC-B1` · `SEC-B2` — 9 조합 (🔬 탐색적)")
    say()
    say(f"귀무 = 각 건의 등록일에 그 풀에서 **무작위 종목 1개** → 같은 측정자·같은 집계 · "
        f"**{NREP:,}회** · 시드 `{SEED}`(스트림 분리) · `p` = `mean(귀무 ≥ 관측)`(등호 포함 · S-5).")
    say()
    say("🔑 **갈래 사이에는 «공통난수(CRN)»를 쓴다** — 같은 스트림 이름(`sec_n1`·`sec_b1`)을 다시 부르면 "
        "같은 난수열이 나오므로 9 조합이 «같은 추첨»을 공유한다(`run_ranking.py` 의 같은 관용). "
        "🔴 목적이 «다른» 계열(`SEC-X1` 순열·그 안의 귀무)은 §0 대로 **다른 스트림**이다 — "
        "`RESULTS_RANKING_TRAIN.md` §5 가 잡은 얽힘 결함을 구조적으로 막는다.")
    say()
    say("| `N` | 측정자 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` 승률 | "
        "관측(pooled) | `SEC-N1` `p`(**건 pooled · `exact` 만**) | "
        "`SEC-B1` `p`(**건 pooled · `exact` 만**) |")
    say("|---|---|---|---|---|---|---|---|---|")
    RES = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            A = AGG[(n, mk)]
            if not A["vals"]:
                say(f"| {n} | `{mk}` | ⛔ 측정 가능 0건 | — | — | — | — | — | — |")
                RES[(n, mk)] = None
                continue
            pn, _ = pools_for("N1", n, mk, bs, items, DAY)
            pb, _ = pools_for("B1", n, mk, bs, items, DAY)
            rec = {}
            for kind, pools, sname in (("N1", pn, "sec_n1"), ("B1", pb, "sec_b1")):
                if any(p.size == 0 for p in pools):
                    rec[kind] = None
                    continue
                mat = null_matrix(stream(sname), pools, A["posts"], NREP)
                gm, gp = agg_matrix(mat, A["posts"])
                rec[kind] = dict(p_main=float(np.mean(gm >= A["main"])),
                                 p_pool=float(np.mean(gp >= A["pooled"])),
                                 ceil_main=float(np.mean(gm >= 100.0 - 1e-9)),
                                 null_med=float(np.median(gm)))
            # SEC-B2 — 건별로 그날 풀 중앙값 초과 (동률은 «못 넘은 것»)
            wins, nb2 = 0, 0
            for pool_v, v in zip(pb, A["vals"]):
                if pool_v.size == 0:
                    continue
                nb2 += 1
                if v > med(list(pool_v)):
                    wins += 1
            rec["B2"] = dict(wins=wins, n=nb2, rate=(wins / nb2 if nb2 else None))
            RES[(n, mk)] = rec
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | **{fmt(A['main'])}** | "
                f"{fmt(rec['N1']['p_main'], 4) if rec['N1'] else '⛔'} | "
                f"{fmt(rec['B1']['p_main'], 4) if rec['B1'] else '⛔'} | "
                f"**{fmt(rec['B2']['rate'] * 100 if rec['B2']['rate'] is not None else None)}%** "
                f"({rec['B2']['wins']}/{rec['B2']['n']}) | {fmt(A['pooled'])} | "
                f"{fmt(rec['N1']['p_pool'], 4) if rec['N1'] else '⛔'} | "
                f"{fmt(rec['B1']['p_pool'], 4) if rec['B1'] else '⛔'} |")
    say()
    say("🔴 **`SEC-P1` 은 «3중 AND»다** — `SEC-N1 < 5%` ∧ `SEC-B1 < 5%` ∧ `SEC-B2 > 50%`(§3 1행). "
        "🔴 **그러나 이 표는 «판정»이 아니다** — post1~5 는 판정 분모 «밖»이다(`SEC-O1`). "
        "여기서 어떤 조합이 문턱을 넘어도 **지지로 인용하지 않는다.**")
    say()
    say("⚠️ 🔴 **이 표의 `p` 는 전부 «`exact` 만» 분모다.** §7 4축 표의 «`approx` 포함» 행은 "
        "**분모가 다른(건수가 더 많은) 별개 검정**이며, 두 표에 **같은 숫자가 나와도 같은 양이 아니다.** "
        "🔑 ***같은 값이 두 곳에 있다고 같은 것을 잰 게 아니다*** — 각 `p` 는 «갈래 × 집계 × 분모»로만 식별된다.")

    # 4-2. q_top (SEC-B1 발화 가능성)
    say()
    say("### 4-2. 🔴🔴 `SEC-B1` **발화 가능성** — `q_top` 실측 (§4-2 (가) · §7-B #20)")
    say()
    say("🔑 ***「재추출이 성립한다」가 「가드가 발화한다」를 뜻하지 않는다***(§8-10). "
        "관측 통계량의 **천장은 100** 이고, 귀무가 그 천장에 **5% 이상**의 질량을 두면 "
        "***어떤 관측으로도 `p < 0.05` 가 나오지 않는다.***")
    say()
    say("🔴 **풀 정의가 둘이다** — ①사전등록 §4-2 (가) 표의 풀 = **`n_up` ∩ 조인**(그대로) · "
        "②이 스크립트가 «실제로 뽑는» 풀 = 그 위에 **측정 가능(동료 ≥ 1)** 한정(§2-3) + 건별 «자기 제외»(M7). "
        "**①로 문서표를 재현하고 ②로 실제 발화를 잰다.**")
    say()
    say("| 등록일 | ① 풀(`n_up`∩조인) | 고유 섹터 | 최대 섹터 | **최대 점유**(수익률 미사용 충분조건) | "
        "`< 0.135` ? | 문서 §4-2 (가) | ② 측정 가능 풀 | 🔒 **`q_top`**(1위 섹터 점유 · 문언 정의) | "
        "(대조) 천장 점유 실측 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    DOC42 = {"2026-07-28": (54, 30, 11, 0.204), "2026-07-30": (66, 32, 7, 0.106),
             "2026-08-05": (93, 30, 17, 0.183), "2026-08-06": (53, 26, 9, 0.170),
             "2026-08-11": (91, 46, 10, 0.110), "2026-08-12": (86, 39, 14, 0.163),
             "2026-08-13": (66, 32, 8, 0.121), "2026-08-18": (76, 40, 8, 0.105),
             "2026-08-19": (51, 37, 5, 0.098), "2026-08-20": (79, 40, 13, 0.165),
             "2026-08-21": (44, 29, 7, 0.159)}
    QT = {}
    n42_ok = 0
    for d in dates:
        D = DAY[d]
        st = D["st"][MAIN_N]
        lab = D["lab"][MAIN_N]
        # ① 문서 정의 풀
        ix1 = np.array([D["code_i"][c] for c in D["nup"]], dtype=np.int64)
        u1, c1 = np.unique(lab[ix1][lab[ix1] >= 0], return_counts=True)
        share = float(c1.max() / ix1.size)
        # ② 실제 추출 풀
        pool = [c for c in D["nup"] if st["ok"][D["code_i"][c]]]
        idxs = np.array([D["code_i"][c] for c in pool], dtype=np.int64)
        # 1위 섹터 = 그날 «전원» 중앙수익률 최대 섹터
        vidx = np.flatnonzero((lab >= 0) & np.isfinite(D["r"]))
        meds = {int(g): float(np.median(D["r"][vidx][lab[vidx] == g]))
                for g in np.unique(lab[vidx])}
        top = max(meds, key=lambda g: meds[g])
        qtop = float(np.sum(lab[idxs] == top) / idxs.size)
        ceil_share = float(np.mean(st["p1"][idxs] >= 100.0 - 1e-9))
        dc = DOC42[d]
        same = (ix1.size == dc[0] and int(u1.size) == dc[1] and int(c1.max()) == dc[2]
                and abs(share - dc[3]) < 0.0006)
        n42_ok += int(same)
        QT[d] = dict(pool_doc=int(ix1.size), sectors_doc=int(u1.size), maxsec_doc=int(c1.max()),
                     max_share=share, pool_eff=int(idxs.size), qtop=qtop, ceil_share=ceil_share,
                     doc_match=bool(same))
        say(f"| {d} | {ix1.size} | {u1.size} | {c1.max()} | **{share:.3f}** | "
            f"{'🟢 예' if share < QTOP_THR else '🔴 아니오'} | "
            f"{'✅' if same else '🔴 %d·%d·%d·%.3f' % dc} | {idxs.size} | "
            f"**{qtop:.3f}** | {ceil_share:.3f} |")
    say()
    say(f"- 🟢 **사전등록 §4-2 (가) 표 재현 = {n42_ok}/{len(dates)}행**(①정의 · 4열 전부 일치). "
        f"그중 **최대 점유 ≥ 0.135 인 날이 {sum(1 for d in dates if QT[d]['max_share'] >= QTOP_THR)}일** "
        "— 사전등록이 *「충분조건이 11개 중 «6개»에서 성립하지 않는다」*고 적은 그 값이다.")
    say("- 🔴🔴 **그러나 「충분조건 실패」는 「`q_top ≥ 0.135`」의 «증명»이 아니다**(§7-A #8-1). "
        f"실측 `q_top`(1위 섹터 점유)은 **11/11 등록일 전부 `< 0.135`** "
        f"(최대 {max(QT[d]['qtop'] for d in dates):.3f}) ⇒ ***이 표본에서 `SEC-B1` 은 «발화 가능»하다.*** "
        "🔑 ***과장하지 않은 것이 값으로 확인됐다*** — 문서는 *「구조만으로는 발화를 보장할 수 없다」*까지만 "
        "적었고, 실제로 재 보니 발화 가능했다.")
    say()
    kmain = len(AGG[(MAIN_N, MAIN_M)]["vals"])
    qmax = max(QT[d]["qtop"] for d in dates)
    qmax_d = max(dates, key=lambda d: QT[d]["qtop"])
    say("🔒 **발화 조건(동결 · §4-2 (가))** = `P(Binom(k, q_top) ≥ ⌈k/2⌉) < 0.05`. "
        "`q_top` 이 등록일마다 다르므로 **판정 분모의 등록일 중 «최대»**(= 가장 불리한 쪽, 보수적)를 쓴다.")
    say()
    say("| `k` | 뜻 | `q_top`(최대) | `P(Binom(k, q_top) ≥ ⌈k/2⌉)` | 판정 |")
    say("|---|---|---|---|---|")
    for k, lbl in ((3, "🔒 사전등록 최소 표본(`PREREG_SELECTION.md` §7)"),
                   (kmain, "이 실행의 측정 가능 `exact` 건수(pooled)"),
                   (len(set(AGG[(MAIN_N, MAIN_M)]["posts"])), "글 단위 집계의 글 수")):
        pv = binom_ge_half(k, qmax)
        say(f"| {k} | {lbl} | {qmax:.3f} (`{qmax_d}`) | **{pv:.4f}** | "
            f"{'🟢 발화 가능' if pv < P_THR else '🔴 **⛔ 발화 불가**'} |")
    say()
    ceil_obs = RES[(MAIN_N, MAIN_M)]["B1"]["ceil_main"] if RES[(MAIN_N, MAIN_M)] and RES[(MAIN_N, MAIN_M)]["B1"] else None
    say(f"- 🟢 **직접 실측(대조)**: 위 `SEC-B1` 귀무 {NREP:,}회에서 **집계 통계량이 천장(100)에 둔 질량 "
        f"= {fmt(ceil_obs, 4)}** — 문언 정의의 이항 산술과 **같은 방향인지**를 여기서 볼 수 있다. "
        "🔴 **판정은 문언 정의(위 표)로 한다**(S-7).")
    say("- 🔴 **`N = 2` 는 이 축에서 훨씬 나쁘다**(§4-2 (가) 예고) — 실측 재현 "
        "(**충분조건**은 ①풀 · **`q_top`**은 ②풀 기준 · 둘 다 11일 중 «최대»):")
    say()
    say("| `N` | 구조적 최대 점유(충분조건) | 그날 | 충분조건 `k=3` 발화? | 필요 최소 홀수 `k` | "
        "🔒 실측 `q_top` 최대 | `q_top` 기준 `k=3` 발화? |")
    say("|---|---|---|---|---|---|---|")
    QMAX_BY_N = {}
    for n in NS:
        best, qbest = [], []
        for d in dates:
            D = DAY[d]
            st = D["st"][n]
            lab = D["lab"][n]
            ix1 = np.array([D["code_i"][c] for c in D["nup"]], dtype=np.int64)
            l1 = lab[ix1][lab[ix1] >= 0]
            if l1.size:   # 🔴 분모 = «그 갈래에서 라벨이 정의된» 풀 원소 수(N=5 에서 ①과 갈린다)
                best.append((float(np.unique(l1, return_counts=True)[1].max() / l1.size), d))
            pool = [c for c in D["nup"] if st["ok"][D["code_i"][c]]]
            if not pool:
                continue
            ix2 = np.array([D["code_i"][c] for c in pool], dtype=np.int64)
            vidx = np.flatnonzero((lab >= 0) & np.isfinite(D["r"]))
            meds = {int(g): float(np.median(D["r"][vidx][lab[vidx] == g]))
                    for g in np.unique(lab[vidx])}
            top = max(meds, key=lambda g: meds[g])
            qbest.append((float(np.sum(lab[ix2] == top) / ix2.size), d))
        if not best or not qbest:
            say(f"| {n} | — | — | — | — | — | — |")
            continue
        sh, dd = max(best)
        kneed = next((k for k in range(3, 402, 2) if binom_ge_half(k, sh) < P_THR), None)
        qs = max(qbest)[0]
        QMAX_BY_N[n] = qs
        say(f"| {n} | **{sh:.3f}** | {dd} | "
            f"{'🟢 예' if binom_ge_half(3, sh) < P_THR else '🔴 아니오'} | "
            f"**{kneed if kneed else '> 401'}** | **{qs:.3f}** | "
            f"{'🟢 예' if binom_ge_half(3, qs) < P_THR else '🔴 아니오'} |")
    say()
    say("🔑 사전등록이 *「`N = 2` 는 08-05 최대 점유가 **0.409** 라 `k = 81` 이 필요하다」*고 적은 값이 "
        "**충분조건 열에서 그대로 재현**된다(분모는 «라벨이 정의된» 풀 원소 수 — `N=5` 에서만 ①과 갈린다).")
    say()
    say("#### 🔴 배선 점검이 잡은 것 — 사전등록 §2-1·§0-6 의 «강한 표현» 하나가 실측으로 지지되지 않는다")
    say()
    say("사전등록 §2-1 말미와 §0-6 「뒤집었을 때의 귀결」 표는 *「`N = 2` 에서는 `SEC-B1` 이 «사실상 "
        "영구 미발화»다」*·*「축 전체가 안 열린다」*로 적었다. **근거는 «충분조건»(최대 단일섹터 점유 0.409)이다.**")
    say("🔴 **충분조건은 `q_top` 의 «상한»이지 `q_top` 이 아니다.** 실측하면 `N = 2` 의 `q_top` 최대가 "
        f"**{QMAX_BY_N.get(2, float('nan')):.3f}** 로 `{QTOP_THR}` 을 한참 밑돌고, "
        f"위 표대로 **`k = 3` 에서 `P(Binom(3, {QMAX_BY_N.get(2, 0):.3f}) ≥ 2) = "
        f"{binom_ge_half(3, QMAX_BY_N.get(2, 0)):.4f} < 0.05` ⇒ 발화 가능**하다.")
    say("⇒ 🔒 **참인 것은 「구조만으로는 발화를 «보장»할 수 없다」까지다**(§7-A #8-1 이 스스로 적은 그 문장). "
        "*「사실상 영구 미발화」*는 **이 표본에서 «재현되지 않는다».**")
    say("🔴 **그래도 이 실행은 `SEC-D1`(`N = 3`)을 무르지 않는다** — 값을 보고 잣대를 바꾸면 그게 "
        "사후적합이다(§0-4 · `SEC-O1`). 이 항목은 **기록**이며, 되돌리려면 **새 사전등록**이 필요하다.")

    # ══════════════════════════════════════════════════════════════════════
    # §5 SEC-G1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §5. `SEC-G1` 커버리지 가드 — 측정 불가 **≥ 1/3 이면 판정 불가** (§4-3 · `Y3` «차용»)")
    say()
    say("⚠️ **`1/3` 은 «feasible set 공집합 비율»을 재던 문턱이며 커버리지에 대해 검증된 적이 없다** — "
        "`PREREG_POST6.md` §1-6 #6 · `PREREG_RANKING.md` §4-4 가 한 같은 차용의 고지를 승계한다.")
    say()
    say("| 사유 | 설명 | 갈래 의존 |")
    say("|---|---|---|")
    say("| ① | DB 종목코드 부재(레메디형) | 전 갈래 공통 |")
    say("| ② | 유니버스 밖(`market_cap>0 ∧ close>0` 미충족) | 전 갈래 공통 |")
    say("| ③ | 섹터코드 부재(매드업·삼양바이오팜형) | 전 갈래 공통 |")
    say("| ④ | 동료 0 (자기 제외 후 `|P| = 0`) | 🔴 `N` 마다 다르다 |")
    say("| ⑤ | 층에서 미정(`length(induty_code) < N`) | 🔴 `N = 5` 갈래 전용 |")
    say()
    say("| `N` | 측정자 | 글2 | 글3 | 글4 | 글5 | **합** | 비율 | `SEC-G1`(≥1/3) | 사유별 건수 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    G1 = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            per = {}
            reasons = {}
            for it, b in zip(items, bs):
                per.setdefault(it["post"], [0, 0])
                per[it["post"]][1] += 1
                if not b["ok"]:
                    per[it["post"]][0] += 1
                    reasons[b["reason"]] = reasons.get(b["reason"], 0) + 1
            bad = sum(v[0] for v in per.values())
            rate = bad / len(items)
            G1[(n, mk)] = rate
            cells = " | ".join(f"{per[p][0]}/{per[p][1]}" for p in sorted(per))
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {cells} | **{bad}/{len(items)}** | **{rate * 100:.1f}%** | "
                f"{'🔴 **발동**' if rate >= G1_THR else '미발동'} | "
                f"{', '.join(f'{k}:{v}' for k, v in sorted(reasons.items())) or '—'} |")
    say()
    say("- 🔴 **`k = 3` 에서는 «1건만 빠져도» 게이트가 열린다**(`1/3 ≥ 1/3`, 등호 발동). "
        "**훈련 표본에서 실제로 실현됐다** — post3 은 `exact` 3건 중 매드업이 사유 ③ 이라 "
        "**정확히 33.3%** 다. ⇒ ***이건 가정이 아니라 관측된 사건이다.***")
    g1_main = G1[(MAIN_N, MAIN_M)]
    say(f"- 🔬 **주 갈래 훈련 표본 미측정률 = {g1_main * 100:.1f}%** ⇒ `k = 3` 에서 3건 모두 측정 가능할 "
        f"확률 ≈ **{(1 - g1_main) ** 3:.2f}** — ***최소 표본에서 이 축이 닫힐 확률이 대략 "
        f"「열에 {round((1 - (1 - g1_main) ** 3) * 10)}」***(§4-3 3번 · 값 보기 전 산술).")
    say("- 🔴 **편향 방향**: 사유 ③ 은 **신규 상장주에 집중**되고 저자는 신규주를 자주 고른다(§1-5) "
        "⇒ ***측정 불가가 무작위가 아니다.*** 남은 분모를 「저자 표본」이라 부르면 이미 편향된 표본이다.")
    say(f"- 🔴 **`N = 5` 갈래**: 측정 불가 **{G1[(5, MAIN_M)] * 100:.1f}%** — 사전등록 §2-1 이 "
        "*「4개 글 중 3개에서 판정 불가 · 훈련 전체 61.1%」*로 **값 보기 «전»에 산술로 잡아 둔** 그 자리다.")

    # ══════════════════════════════════════════════════════════════════════
    # §6 SEC-X1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §6. `SEC-X1` 섹터 라벨 **순열 대조군** — 귀무 «구현»의 1종오류율 (§4-4 · `SEC-D6`)")
    say()
    say("🔴🔴 **이 가드가 재는 것은 «귀무 구현의 1종오류율 보정» 하나뿐이다** — "
        "*「칸막이가 정보인가」를 재는 검정이 «아니다»*(§4-4 B-2). "
        "라벨을 섞으면 저자 종목과 귀무 추출 종목의 섹터가 **교환 가능**해지므로, "
        "***참 분할이 정보를 담든 잡음이든 `P(p<0.05)` 는 «항상» 5% 다.***")
    say("🔴 **`SEC-X1` 통과를 「섹터가 의미 있다」로 인용하지 않는다.** "
        "「칸막이가 정보인가」는 **`SEC-B1`·`SEC-B2`** 가 잰다(§7-C 4번).")
    say()

    X1_BASE = x1_base_for(items, DAY)

    t_x1 = time.time()
    x1 = x1_run(stream("sec_x1_perm"), stream("sec_x1_null"), X1_REP, dates, DAY, X1_BASE)
    t_x1 = time.time() - t_x1
    say(f"**명세**: 그날 유니버스의 `induty_code` 를 종목 사이에서 무작위로 «섞고»(집단 크기 분포 보존) "
        f"같은 측정자(`SEC-M1` · `N=3`)·같은 귀무를 계산 — **독립 실현 {X1_REP}개** × 귀무 {NREP:,}회.")
    say()
    say("| 풀 | 실현 수 | `p` 평균 | `p` 중앙 | **`p < 0.05` 비율** | `p < 0.20` 비율 | "
        "명목 대비(SE ≈ 1.5%p) | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    x1sum = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        ok = abs(z) <= 2.0
        x1sum[kind] = dict(n=len(ps), mean=float(ps.mean()), median=float(np.median(ps)),
                           lt05=rate, lt20=float(np.mean(ps < 0.20)), z=float(z), pass_=bool(ok))
        say(f"| `SEC-{kind}` | {len(ps)} | {ps.mean():.4f} | {np.median(ps):.4f} | "
            f"**{rate * 100:.1f}%** | {np.mean(ps < 0.20) * 100:.1f}% | "
            f"`z = {z:+.2f}` | {'🟢 **보정됨**' if ok else '🔴 **⛔ 절차 무효**'} |")
    say()
    say(f"- 순열 하 `p` 는 이론상 `U(0,1)` 이므로 `p<0.05` 비율의 기대는 **5.0%**, "
        f"{X1_REP} 실현의 SE ≈ **1.5%p** 다(§4-4). `|z| ≤ 2` 를 «어긋나지 않음»으로 읽는다.")
    say(f"- 🔴 **순열 실현에서 저자 건이 «측정 불가»가 되는 일**(섞인 뒤 `|P| = 0`)이 있다 — "
        f"실현당 평균 **{np.mean([r['drop'] for r in x1]):.2f}건** 탈락. 크기 정합을 위해 그 건은 "
        "관측·귀무 «양쪽»에서 같이 빠진다.")
    say()
    say("### 6-1. 🔴 **가드를 «일부러» 켜서 발동을 실증한다** (§7-B #20 · `x1_bypass` 형식 승계)")
    say()
    say("🔑 ***「조항을 적었다」가 「그 조항이 발동한다」를 뜻하지 않는다*** — "
        "`FREEZE_RANKING_2026-08-31.md` §4 가 `x1_bypass` 로 한 실증을 이 축에서도 한다. "
        "**귀무 구현을 «고장내고»**(추출 풀에서 상위 절반 백분위를 통째로 제거 ⇒ 교환가능성 파괴) "
        "같은 순열 대조군을 돌린다. 가드가 살아 있다면 1종오류율이 5%에서 «어긋나야» 한다.")
    say()
    x1b = x1_run(stream("sec_x1_bypass_perm"), stream("sec_x1_bypass_null"), X1_REP, dates, DAY,
                 X1_BASE, broken=True)
    say("| 귀무 구현 | `p < 0.05` 비율 | `z` | `SEC-X1` 판정 |")
    say("|---|---|---|---|")
    say(f"| 🟢 정상(위 §6 `SEC-N1`) | **{x1sum['N1']['lt05'] * 100:.1f}%** | "
        f"`{x1sum['N1']['z']:+.2f}` | {'🟢 보정됨 ⇒ 절차 유효' if x1sum['N1']['pass_'] else '🔴 절차 무효'} |")
    bx = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1b])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        bx[kind] = dict(lt05=rate, z=float(z), fired=bool(abs(z) > 2.0))
        say(f"| 🔴 **일부러 고장낸 것**(`SEC-{kind}` 풀 상위 절반 제거) | **{rate * 100:.1f}%** | "
            f"`{z:+.2f}` | {'🔴 **⛔ 절차 무효 — 가드 발동 ✅**' if abs(z) > 2.0 else '🟡 미발동'} |")
    say()
    fired = bx["N1"]["fired"] or bx["B1"]["fired"]
    say(f"⇒ {'🟢 **`SEC-X1` 이 실제로 발동한다** — 죽은 가드가 아니다.' if fired else '🔴 **고장낸 구현에서도 발동하지 않았다** — 이 실증은 실패다.'} "
        "🔴 **그리고 이 발동은 「섹터가 무의미하다」와 무관하다** — 잰 것은 «우리 귀무 구현»이다(§4-4).")

    # ══════════════════════════════════════════════════════════════════════
    # §7 SEC-V1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §7. `SEC-V1` 민감도 **4축** (§4-6) — 🔴 «민감도 전용»")
    say()
    say("🔒 **적용 범위**: 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」에만 적용된다. "
        "🔴 **§3 의 3중 AND 안에서 한 항목이 미달하는 사건에는 «관여하지 않는다»** — "
        "그건 갈린 게 아니라 **AND 가 거짓인 것**이고 그 판정은 §3 이 한다(§3 우선순위표).")
    say()
    say("⚠️ **「귀무 풀(`SEC-N1` ↔ `SEC-B1`)」은 이 표에 «없다»** — 그건 민감도가 아니라 **판정 조건**이다(§4-6).")
    say()
    # approx 갈래
    ap_bs = BR[("ap", MAIN_N, MAIN_M)]
    both = [(it, b) for it, b in zip(items, BR[(MAIN_N, MAIN_M)]) if b["ok"]]
    ap_ok = [(it, b) for it, b in zip(ap_items, ap_bs) if b["ok"]]
    v_ex_main = AGG[(MAIN_N, MAIN_M)]["main"]
    v_ex_pool = AGG[(MAIN_N, MAIN_M)]["pooled"]
    ap_vals = [b["pct"] for _, b in both] + [b["pct"] for _, b in ap_ok]
    ap_posts = [it["post"] for it, _ in both] + [it["post"] for it, _ in ap_ok]
    v_ap_main, v_ap_pool = aggregate(ap_vals, ap_posts)
    # `approx` 포함 갈래의 귀무도 «실제로» 돌린다(문언: 「포함값을 의무 민감도로 인쇄」).
    ap_all_items = items + ap_items
    ap_all_bs = BR[(MAIN_N, MAIN_M)] + ap_bs
    ap_res = {}
    for kind, sname in (("N1", "sec_n1"), ("B1", "sec_b1")):
        pl, _ = pools_for(kind, MAIN_N, MAIN_M, ap_all_bs, ap_all_items, DAY)
        if pl and not any(p.size == 0 for p in pl):
            gm, gp = agg_matrix(null_matrix(stream(sname), pl, ap_posts, NREP), ap_posts)
            ap_res[kind] = dict(p_main=float(np.mean(gm >= v_ap_main)),
                                p_pool=float(np.mean(gp >= v_ap_pool)))
        else:
            ap_res[kind] = None
    ap_wins, ap_n = 0, 0
    for pool_v, v in zip(pools_for("B1", MAIN_N, MAIN_M, ap_all_bs, ap_all_items, DAY)[0], ap_vals):
        if pool_v.size == 0:
            continue
        ap_n += 1
        if v > med(list(pool_v)):
            ap_wins += 1
    say("| # | 축 | 갈래 | 값(글 단위 중앙) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | 판정 갈래 |")
    say("|---|---|---|---|---|---|---|---|")

    def cell(n, mk):
        r = RES[(n, mk)]
        if r is None:
            return "⛔", "⛔", "⛔"
        return (fmt(r["N1"]["p_main"], 4) if r["N1"] else "⛔",
                fmt(r["B1"]["p_main"], 4) if r["B1"] else "⛔",
                (f"{r['B2']['rate'] * 100:.1f}%" if r["B2"]["rate"] is not None else "⛔"))
    for n in NS:
        a, b_, c_ = cell(n, MAIN_M)
        note = " (🔴 구조적 미정 %.1f%% 병기)" % (G1[(5, MAIN_M)] * 100) if n == 5 else ""
        say(f"| 1 | 섹터 깊이 | `N = {n}`{note} | {fmt(AGG[(n, MAIN_M)]['main'])} | {a} | {b_} | {c_} | "
            f"{'🔒 **판정**' if n == MAIN_N else '민감도'} |")
    for mk in MEAS:
        a, b_, c_ = cell(MAIN_N, mk)
        say(f"| 2 | 측정자 | `{mk}` | {fmt(AGG[(MAIN_N, mk)]['main'])} | {a} | {b_} | {c_} | "
            f"{'🔒 **판정**' if mk == MAIN_M else '민감도'} |")
    rm = RES[(MAIN_N, MAIN_M)]
    say(f"| 3 | 집계 | 글 단위 중앙 | {fmt(v_ex_main)} | {fmt(rm['N1']['p_main'], 4)} | "
        f"{fmt(rm['B1']['p_main'], 4)} | {fmt(rm['B2']['rate'] * 100)}% | 🔒 **판정** |")
    say(f"| 3 | 집계 | 건 pooled 중앙 | {fmt(v_ex_pool)} | {fmt(rm['N1']['p_pool'], 4)} | "
        f"{fmt(rm['B1']['p_pool'], 4)} | 〃 | 민감도 |")
    say(f"| 4 | 등록일 정밀도 | `exact` 만 ({len(both)}건) | {fmt(v_ex_main)} | "
        f"{fmt(rm['N1']['p_main'], 4)} | {fmt(rm['B1']['p_main'], 4)} | "
        f"{fmt(rm['B2']['rate'] * 100)}% | 🔒 **판정** |")
    nap = len(both) + len(ap_ok)
    say(f"| 4 | 등록일 정밀도 | `approx` 포함 ({nap}건) | {fmt(v_ap_main)} | "
        f"{fmt(ap_res['N1']['p_main'], 4) if ap_res['N1'] else '⛔'} **(분모 {nap}건)** | "
        f"{fmt(ap_res['B1']['p_main'], 4) if ap_res['B1'] else '⛔'} **(분모 {nap}건)** | "
        f"{fmt(ap_wins / ap_n * 100) if ap_n else '—'}% ({ap_wins}/{ap_n}) | 민감도 |")
    say()
    say(f"⚠️ 🔴 **마지막 행의 `p` 는 «분모 {nap}건»(`exact`+`approx`)이다** — §4-1 표의 `p` 는 전부 "
        f"«분모 {len(both)}건»(`exact` 만)이다. **두 표에 같은 숫자가 나와도 같은 양이 아니다**"
        "(다른 건 집합 · 다른 검정). 🔑 ***`p` 는 「갈래 × 집계 × 분모」로만 식별된다.***")
    say(f"- `approx` **{len(ap_items)}건**: " + " · ".join(
        f"{it['name']}({it['reg']}) → " + (f"백분위 **{b['pct']:.1f}**" if b["ok"] else f"⛔ 사유 {b['reason']}")
        for it, b in zip(ap_items, ap_bs)) + ".")
    say("- 🔴 **`approx` 는 판정 분모에 «넣지 않는다»**(`SEC-D5` · §2-5) — 포함값은 의무 민감도이며 "
        "두 값이 갈리면 ⇒ ⛔ `SEC-V1`.")
    say()
    say("🔴 **이 실행에서는 «판정 자체가 없다»**(배선 점검 · `SEC-O1`) ⇒ ***`SEC-V1` 은 "
        "「갈렸다/안 갈렸다」를 «선언하지 않는다».*** 위 표는 **4축이 실제로 계산되고 «움직인다»는 "
        "배선 확인**이며, 판정에서의 `SEC-V1` 적용은 **post6 부터**다.")

    # ══════════════════════════════════════════════════════════════════════
    # §8 §7-B 점검표
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §8. 사전등록 §7-B 실행 점검표 — 이 실행이 닫은 항목")
    say()
    say("| # | 점검 | 상태 | 근거 |")
    say("|---|---|---|---|")
    say("| 17 | `SEC-` grep 재확인 | ✅ (작성 시점) | 사전등록 §0-5. ⚠️ 이 실행이 `run_sector.py`·"
        "`RESULTS_SECTOR_DRYRUN*.md`·`sector_dryrun/` 을 만들어 **`SEC-` 가 잡히는 파일이 늘어난다** — "
        "그건 오염이 아니라 이 축의 산출물이다 |")
    say("| 18 | 브랜치 확인·전환 | ✅ | `fix/tasso-post6-s5-fixes` 워크트리에서 실행(해시는 stdout) · "
        "🔴 라이브 트리에서 돌리지 않았다 |")
    say(f"| 19 | 의사티커 전수 재확인 | ✅ | §0 — 코드 {len(PSEUDO)}종 ∪ DB 실측 {len(nonnum)}종 = "
        f"**{len(final_pseudo)}종**(같다) |")
    say("| 20 | 죽은 가드 실측 점검 | ✅ | `SEC-B2` §4-1(비율이 상수가 아님) · `SEC-G1` §5(갈래별로 움직임) · "
        "🔴 **`SEC-B1` `q_top` 실측 §4-2** · **`SEC-X1` 일부러 켜서 발동 실증 §6-1** |")
    say(f"| 21 | DB 스냅샷 최신 봉을 박는다 | ✅ | §0 — **`{END}`**. 봉수 표기는 「직전 / 포함」 구분 "
        "규약(`RESULTS_LADDER_TRANCHE.md` N8)을 따르며, **이 축은 창을 쓰지 않고 «등록일 당일»만 쓴다** "
        "⇒ 「직전/포함」 구분이 걸리는 자리가 없다 |")
    say(f"| 22 | `stock_industry` 스냅샷을 박는다 | ✅ | §0 — {si_rows:,}행 · `max(updated_at)` `{si_upd}` · "
        "전체 sha256. 🔴 **이 표는 시간에 따라 «자란다»** — 매드업·삼양바이오팜이 나중에 편입되면 "
        "같은 글의 값이 달라진다(§8-5) |")
    say("| 23 | `SEC-D1`~`D8` 이 `fetch_post.py` «전»에 확정·커밋됐는지 | ⬜ **post6 수집 «후»에 확인** | "
        "`git log --diff-filter=A -- post_<logNo>.html` ↔ `FREEZE_SECTOR_<날짜>.md` 커밋 해시. "
        "🔴 아직 일어나지 않은 일을 ✅ 로 적지 않는다 |")
    say("| 24 | 라이브 채택 금지 문구 · 「+15%」 잔존 고지 | ✅ | 이 파일 머리 6줄(`NOTATION`) · "
        "`sector_dryrun/*.json` 의 `_notation` · `cases.tsv` 머리 주석 |")
    say("| 25 | `regen_gate.py` 등재 | ✅ **등재** / ⬜ **`--update` 는 동결 단계** | "
        "`PAIRS[\"RESULTS_SECTOR_DRYRUN_NUMBERS.md\"] = \"run_sector.py\"` · "
        "`PAIRS[\"RESULTS_SECTOR_POST6_NUMBERS.md\"]`(PENDING) · `MANUAL_DOCS` 4건. "
        "🔴 **`--update` 는 §0-4 5번(동결 커밋)의 동작이다** — 그때까지 "
        "`test_c19_manifest_covers_every_pair` 는 **실패한다**(§9) |")
    say(f"| 26 | 동료 수 하한을 «실측»으로 확정 | ✅ | §1-6 — 저자 {len(au_peers)}건 중 동료 0 인 건 "
        f"**{sum(1 for x in au_peers if x == 0)}건** · 귀무 풀 한정 크기 §4-0 |")

    # ══════════════════════════════════════════════════════════════════════
    # §9 자기점검
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §9. 이 실행의 «미해소»·«고지»")
    say()
    say("| 항목 | 상태 |")
    say("|---|---|")
    say("| `SEC-P1`·`SEC-P2` | ⛔ **판정 전** — post6 부터. 이 파일의 어떤 값도 지지·기각의 근거가 아니다 |")
    say(f"| `SEC-G1`(주 갈래) | 🔬 훈련 표본 **{g1_main * 100:.1f}%** — 판정 분모는 post6 신규 `exact` 이므로 "
        "이 비율은 **예보**이지 판정이 아니다 |")
    say("| 승/패 대조(`PREREG_SELECTION.md` §4) | ⛔ **2회 연속 미실시** — `exact` 건에 `all_loss=1` 이 0건. "
        "⚠️ **이 배선 점검은 「새 글」이 아니므로 횟수를 «올리지 않는다»**(post4 = 1회 · post5 = 2회) |")
    say("| `regen_gate.py --update`·`--rerun` | ⬜ **동결 단계(§0-4 5번)** — 그때까지 매니페스트 테스트 1건 실패 |")
    say("| 「테마로 고른다」 확증 | ⛔ **이 축에서는 «영구히» 열리지 않는다**(§0-2 · §9) |")
    say()
    say("🔑 **계열 규칙 재확인** — ***대조군을 달 때는 「그 대조군이 «무엇을 파괴하는가»」를 먼저 적어라.*** "
        "`SEC-X1` 의 순열은 **분할 구조**를 파괴하므로 분할에 대해 아무것도 못 말한다(§8-9).")
    say()
    say("---")
    say()
    say(f"결정성: 시드 `{SEED}` 고정 · 스트림 분리 · DB 는 SELECT 만 ⇒ **같은 DB 스냅샷에서 재실행하면 "
        f"byte 단위로 같다**(`regen_gate.py --rerun` 전제). "
        "🔴 그래서 이 파일에는 **실행 시간·커밋 해시를 적지 않는다** — 벽시계·`HEAD` 는 stdout 전용이다. "
        "🔑 ***커밋마다 바뀌는 값을 산출물에 적으면 그 산출물은 자기 자신을 재현할 수 없게 된다.***")
    say()
    say("[[PREREG_SECTOR_COMOVE]] · [[PREREG_RANKING]] · [[PREREG_POST6]] · [[FINDING_THEME_AXIS]] · "
        "[[RESULTS_RANKING_TRAIN]] · [[FREEZE_RANKING_2026-08-31]] · [[RESULTS_REGDAY_POST5]] · "
        "[[RESULTS_D1_OOS_POST5]] · [[RESULTS_RECONSTRUCT_POST4]] · [[PREREG_SELECTION]]")

    # ══════════════════════════════════════════════════════════════════════
    # 기계 산출물
    # ══════════════════════════════════════════════════════════════════════
    universe = {d: DAY[d]["uni"] for d in all_dates}
    joined = {d: DAY[d]["joined"] for d in all_dates}
    (ART / "universe_snapshot.json").write_text(json.dumps({
        "db_snapshot_max_date": END, "pseudo_from_code": list(PSEUDO),
        "pseudo_nonnumeric_in_db": nonnum, "pseudo_final": final_pseudo,
        "universe_sizes": {d: len(universe[d]) for d in all_dates},
        "joined_sizes": {d: len(joined[d]) for d in all_dates},
        "coverage_pct": {d: round(len(joined[d]) / len(universe[d]) * 100, 4) for d in all_dates},
        "universe": universe, "joined": joined,
        "sha256_universe": {d: sha_list(universe[d]) for d in all_dates},
        "sha256_joined": {d: sha_list(joined[d]) for d in all_dates},
        "_notation": NOTATION,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "sector_snapshot.json").write_text(json.dumps({
        "table": "stock_industry", "rows": si_rows, "distinct_stock_code": si_uniq,
        "induty_code_non_null": si_nonnull, "max_updated_at": si_upd,
        "sha256_code_to_induty": si_sha,
        "length_distribution_table": {str(k): v for k, v in sorted(len_all.items())},
        "stock_info_sector_non_null": info_sector, "stock_info_rows": info_rows,
        "warning": "이 표는 시간에 따라 «자란다» — 매드업·삼양바이오팜이 편입되면 같은 글의 값이 달라진다",
        "_notation": NOTATION,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for ci, it in enumerate(items):
        rec = {k: it[k] for k in ("post", "log_no", "item_no", "name", "code", "reg", "prec", "all_loss")}
        rec["db_snapshot_max_date"] = END
        rec["main_branch"] = {"N": MAIN_N, "measure": MAIN_M}
        rec["branches"] = {}
        for n in NS:
            for mk in MEAS:
                bb = BR[(n, mk)][ci]
                rec["branches"][f"N{n}_{mk}"] = {
                    kk: (round(vv, 6) if isinstance(vv, float) else vv)
                    for kk, vv in bb.items()}
        rec["_notation"] = NOTATION
        (ART / f"case_{it['post']}_{it['item_no']}_{it['name']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "controls_summary.json").write_text(json.dumps({
        "seed": SEED, "nrep": NREP, "note_nrep": "run_selection.py:22 는 NREP=2000",
        "streams": _STREAM_NAMES, "x1_realizations": X1_REP,
        "db_snapshot_max_date": END,
        "thresholds": {"p": P_THR, "B2": B2_THR, "G1": G1_THR, "q_top": QTOP_THR,
                       "n_up_multiplier": UP_MULT, "drop_mark": DROP_MARK},
        "observed": {f"N{n}_{mk}": {"main": AGG[(n, mk)]["main"], "pooled": AGG[(n, mk)]["pooled"],
                                    "n_measurable": len(AGG[(n, mk)]["vals"])}
                     for n in NS for mk in MEAS},
        "nulls": {f"N{n}_{mk}": (None if RES[(n, mk)] is None else {
            "SEC-N1": RES[(n, mk)]["N1"], "SEC-B1": RES[(n, mk)]["B1"], "SEC-B2": RES[(n, mk)]["B2"]})
            for n in NS for mk in MEAS},
        "G1_rate": {f"N{n}_{mk}": G1[(n, mk)] for n in NS for mk in MEAS},
        "q_top": QT,
        "SEC-X1": {"normal": x1sum, "deliberately_broken": bx,
                   "note": "재는 것은 «귀무 구현의 1종오류율» 하나뿐 — 분할의 정보량과 무관하다(§4-4)"},
        "_notation": NOTATION,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    with (ART / "cases.tsv").open("w", encoding="utf-8") as f:
        f.write("# RESULTS_SECTOR_DRYRUN — 건별 측정값 (기계 생성 · 🔬 탐색 표기 · 판정 아님)\n")
        f.write(f"# 주 판정 갈래 N={MAIN_N} · {MAIN_M} · DB 스냅샷 {END} · 시드 {SEED} · post1~5 «만»\n")
        for ln in NOTATION:
            f.write("# " + ln.replace("\n", " ") + "\n")
        f.write("#\n")
        f.write("post\titem\tname\tcode\treg\tN\tmeasure\tsector\tpeers\tG\tsec_rank\traw\tpct\treason\n")
        for n in NS:
            for mk in MEAS:
                for it, b in zip(items, BR[(n, mk)]):
                    f.write(f"{it['post']}\t{it['item_no']}\t{it['name']}\t{it['code'] or ''}\t"
                            f"{it['reg']}\t{n}\t{mk}\t{b.get('sector', '')}\t"
                            f"{b.get('peers', '')}\t{b.get('G', '')}\t{b.get('rank', '')}\t"
                            f"{('%.8f' % b['raw']) if b['ok'] else ''}\t"
                            f"{('%.6f' % b['pct']) if b['ok'] else ''}\t{b['reason']}\n")

    (BASE / "RESULTS_SECTOR_DRYRUN_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")

    print(f"[시간] 총 {time.time() - t_start:.1f}초 · SEC-X1 {t_x1:.1f}초")
    print("[written] RESULTS_SECTOR_DRYRUN_NUMBERS.md + sector_dryrun/*.json|tsv")
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. post6 판정 모드 (post6 신규 `exact` «만» · §0-4 7번)
# ══════════════════════════════════════════════════════════════════════════════
def main_post6(cur, ctx):                                     # noqa: PLR0912, PLR0915
    t_start = time.time()
    ART = ART_POST6
    ART.mkdir(exist_ok=True)

    END = ctx["END"]
    si_rows, si_uniq, si_nonnull = ctx["si_rows"], ctx["si_uniq"], ctx["si_nonnull"]
    si_upd, si_sha = ctx["si_upd"], ctx["si_sha"]
    info_rows, info_sector, len_all = ctx["info_rows"], ctx["info_sector"], ctx["len_all"]
    nonnum, final_pseudo, SEC = ctx["nonnum"], ctx["final_pseudo"], ctx["SEC"]

    # 🔴🔴 **명시 필터** — 판정 분모는 **post6 신규 `exact` «만»**(`SEC-D5` · §2-5).
    #     PD-2 후속 2건(광전자·삼양바이오팜)은 `reg_date_precision = none` 이라
    #     `exact_items()` 가 «정의로» 뺀다 — 값을 보고 뺀 것이 아니다.
    items = [it for it in ctx["items_all"] if it["post"] == POST6_IDX]
    ap_items = [it for it in ctx["ap_all"] if it["post"] == POST6_IDX]
    train = [it for it in ctx["items_all"] if it["post"] in TRAIN_POSTS]
    none_rows = [r for r in ctx["rows"]
                 if r["post_log_no"] == POST6_LOG_NO and r["reg_date_precision"] == "none"]
    bad_log = sorted({it["log_no"] for it in items} - {POST6_LOG_NO})
    if bad_log:
        raise SystemExit(f"🔴 post6 필터가 다른 글을 잡았다: {bad_log}")

    dates = sorted({it["reg"] for it in items})
    all_dates = sorted({it["reg"] for it in items + ap_items})
    train_dates = sorted({it["reg"] for it in train})
    DAY = {d: load_day(cur, d, SEC, final_pseudo)
           for d in sorted(set(all_dates) | set(train_dates))}

    # ── 갈래별 측정 · 귀무 (한 함수로 — 갈래·부분표본이 «같은 정의»를 쓰게) ────
    def full_eval(its, n, mk):
        bs = [measure_case(it, n, mk, DAY, SEC) for it in its]
        vals = [b["pct"] for b in bs if b["ok"]]
        posts = [it["post"] for it, b in zip(its, bs) if b["ok"]]
        main_v, pooled = aggregate(vals, posts)
        out = dict(bs=bs, vals=vals, posts=posts, main=main_v, pooled=pooled,
                   N1=None, B1=None, B2=dict(wins=0, n=0, rate=None))
        if not vals:
            return out
        for kind, sname in (("N1", "sec_n1"), ("B1", "sec_b1")):
            pl, _ = pools_for(kind, n, mk, bs, its, DAY)
            if pl and not any(p.size == 0 for p in pl):
                gm, gp = agg_matrix(null_matrix(stream(sname), pl, posts, NREP), posts)
                out[kind] = dict(p_main=float(np.mean(gm >= main_v)),
                                 p_pool=float(np.mean(gp >= pooled)),
                                 ceil_main=float(np.mean(gm >= 100.0 - 1e-9)),
                                 null_med=float(np.median(gm)))
        pb, _ = pools_for("B1", n, mk, bs, its, DAY)
        wins, nb2 = 0, 0
        # 🔴 **`SEC-B2` 의 비교점은 «그날 `n_up` 풀의 중앙값»이지 «50»이 아니다**(§3 5행).
        #    백분위 축이라 50 이 비교점처럼 보이지만, 문턱 50% 는 «승률»에 걸린 것이다.
        #    ⇒ 건별 (저자 값, 그날 풀 중앙값)을 인쇄용으로 남긴다.
        b2_detail = []
        _mnames = [it["name"] for it, b in zip(its, bs) if b["ok"]]
        for idx, (pool_v, v) in enumerate(zip(pb, vals)):
            if pool_v.size == 0:
                continue
            nb2 += 1
            pm = med(list(pool_v))
            if v > pm:     # 🔴 동률은 «못 넘은 것»(§4-2 · 보수적)
                wins += 1
            b2_detail.append(dict(name=(_mnames[idx] if idx < len(_mnames) else "?"),
                                  value=float(v), pool_med=float(pm),
                                  pool_n=int(pool_v.size), win=bool(v > pm)))
        out["B2"] = dict(wins=wins, n=nb2, rate=(wins / nb2 if nb2 else None),
                         detail=b2_detail)
        return out

    EV = {(n, mk): full_eval(items, n, mk) for n in NS for mk in MEAS}
    BR = {(n, mk): EV[(n, mk)]["bs"] for n in NS for mk in MEAS}
    MAIN = EV[(MAIN_N, MAIN_M)]

    # ══════════════════════════════════════════════════════════════════════
    # §0
    # ══════════════════════════════════════════════════════════════════════
    say("# `SEC-` 섹터 동반 상승 — **post6 판정** 수치 원본 (post6 신규 `exact` «만»)")
    say()
    for ln in NOTATION_POST6:
        say("> " + ln)
    say()
    say("🔴 **이 파일의 판정 분모는 post6 신규 `exact` 건 «뿐»이다** — 훈련(post1~5) 값은 "
        "`SEC-O1`(§4-5) 대로 **§8 에 «나란히»만** 두고 판정 분모에 넣지 않는다.")
    say()
    say("## §0. 실행 문맥")
    say()
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 사전등록 | `PREREG_SECTOR_COMOVE.md` (동결 · `SEC-D1`~`D8` 확정 2026-09-02) |")
    say("| 동결 | `FREEZE_SECTOR_2026-09-03.md` (§0-4 **5번**) · 배선 점검 `RESULTS_SECTOR_DRYRUN.md` |")
    say("| 단계 | `PREREG_SECTOR_COMOVE.md` §0-4 **7번(계산)** — 🔒 **이 값이 판정이다** |")
    say(f"| 대상 글 | `logNo` **{POST6_LOG_NO}** · 발행 **2026-09-04(금)** · 프로그램 1.0.40 |")
    say("| 실행 브랜치 | `fix/tasso-post6-s5-fixes` (🔴 해시는 stdout 전용 — 본문에 박으면 `--rerun` 이 구조적으로 깨진다) |")
    say(f"| **DB 스냅샷 최신 봉** | **`{END}`** (`daily_prices` `max(date)`) |")
    say("| 창 종료 표기 | **2026-09-04 = 발행 당일 봉 «포함»**(`PREDECISION_2026-09-04_post6.md` PD-1). "
        "⚠️ 🔴 **이 축은 창을 쓰지 않는다** — `close`·`prev_close`·`high` 를 **등록일 «당일»만** 쓴다"
        "(§7-B #21) ⇒ 「직전 / 포함」 구분이 걸리는 자리가 없다. **스냅샷 표기는 그대로 유지한다.** |")
    say(f"| `stock_industry` 스냅샷 (§7-B #22) | **{si_rows:,}행** · 고유 `stock_code` {si_uniq:,} · "
        f"`induty_code` non-NULL {si_nonnull:,} · `max(updated_at)` **{si_upd}** |")
    say(f"| 〃 sha256(전체 `stock_code`↔`induty_code`) | `{si_sha[:32]}…` |")
    say(f"| 〃 동결(2026-09-03) 대비 | "
        f"{'✅ **행 수·`max(updated_at)` 불변**' if (si_rows == 2556 and si_upd.startswith('2026-08-07')) else '🔴 **움직였다**'}"
        " — 🔴 이 표는 시간에 따라 «자란다»(§8-5) |")
    say("| 주 판정 갈래 | 🔒 **`N = 3` · `SEC-M1`** (`SEC-D1`·`D2` · 사장님 확정 2026-09-02) |")
    say(f"| 시드 · 반복 | `{SEED}` · **{NREP:,}회** — ⚠️ `run_selection.py:22` 는 `NREP = 2000` 이다"
        "(§2-3 고지 · 이 축은 «더 큰 쪽»을 쓴다) |")
    say(f"| 시드 스트림 분리 | `SeedSequence({SEED}).spawn()` → `{'`·`'.join(_STREAM_NAMES)}` "
        "(§2-3 «필수» 승계) |")
    say(f"| `SEC-X1` 독립 실현 | **{X1_REP}** (`RESULTS_RANKING_TRAIN.md` §5 «승계») |")
    say(f"| 의사티커 제외 | **{len(final_pseudo)}종** {'·'.join('`%s`' % p for p in final_pseudo)} — "
        f"`run_selection.py:23` `PSEUDO`({len(PSEUDO)}) ∪ DB 실측({len(nonnum)}종) ⇒ "
        f"**{'같다' if set(final_pseudo) == set(PSEUDO) else '🔴 다르다'}**(§5 4번 · §7-B #19) |")
    say("| 유니버스 | `PREREG_RANKING.md` §2-1 승계(`market_cap > 0 ∧ close > 0` · 의사티커 제외) "
        "**∩ 섹터코드 존재**(`SEC-D3`) |")
    say(f"| 🔒 **판정 분모** | post6 신규 `exact` **{len(items)}건** · 등록일 **{len(dates)}일** "
        f"({dates[0]} ~ {dates[-1]}) |")
    say(f"| `approx` (의무 민감도) | **{len(ap_items)}건**"
        + ("" if ap_items else " — 🟢 **0건이므로 「`approx` 포함」 갈래가 「`exact` 만」과 «구조적으로 같은 집합»이다**(모호 아님)")
        + " |")
    say(f"| `none`(PD-2 후속) | **{len(none_rows)}건** "
        + " · ".join(r["stock_name"] for r in none_rows)
        + " — 🔴 **등록일 축 분모 «밖»**(`exact_items()` 가 정의로 뺀다 · 이중계상 금지) |")
    say("| `after` | **0건**(post6) · 계열 누적 1건 제외 유지(`SEC-D5`) |")
    say(f"| 최소 표본 게이트 | `exact` **{len(items)} ≥ {MIN_EXACT}** ⇒ "
        f"{'🟢 **판정한다**' if len(items) >= MIN_EXACT else '⛔ **미룬다**'} "
        "(`PREREG_SELECTION.md` §7 «차용») |")
    say()
    say("🔴 **`SEC-O1` 자유도 신고** — 잣대 선택(`SEC-D1` `N` 3후보 × `SEC-D2` 측정자 3후보 = **9 조합**)의 "
        "자유도가 이 축의 거의 전부이며, 그 결정은 **2026-09-02**(§0-6)에 동결됐고 배선 점검(09-02)·"
        "동결 커밋(09-03)이 **`fetch_post.py`(09-04 18:50 KST) «전»**이다(PD-0). "
        "**9 조합을 다 인쇄하되 판정 갈래는 «동결된 하나»뿐이다.** "
        "🔴 **이 실행은 값을 보고 잣대를 하나도 바꾸지 않았다.**")
    say()
    say("| 열 | 뜻 |")
    say("|---|---|")
    say("| 훈련(post1~5) | 🔬 **탐색적 표기** — 판정 분모에 **넣지 않는다**(§8 에만) |")
    say("| 🔒 검증(post6) | **판정** — 이 파일의 §1~§7 전부 |")

    # ══════════════════════════════════════════════════════════════════════
    # §1 분모 · SEC-G1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §1. 분모 · 커버리지 `SEC-G1` (§2-5 · §4-3)")
    say()
    say(f"### 1-1. 건별 — post6 신규 `exact` {len(items)}건")
    say()
    say("| # | 종목 | `stock_code` | 등록일 | `induty_code` | 길이 | `N=3` 칸 | 유니버스 | 섹터표 | 재진입 | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    for it in items:
        c = it["code"]
        D = DAY[it["reg"]]
        ind = SEC.get(c) if c else None
        in_uni = bool(c) and c in set(D["uni"])
        reason = ("①" if not c else ("②" if not in_uni else ("③" if ind is None else "")))
        re_f = PD3_FLAG.get(c)
        re_s = "—" if re_f is None else f"🔂 `P6-PRIOR_CYCLE`={re_f}"
        say(f"| {it['item_no']} | {it['name']} | `{c or '—'}` | {it['reg']} | `{ind or '—'}` | "
            f"{len(ind) if ind else '—'} | `{ind[:3] if ind else '—'}` | {'✅' if in_uni else '🔴'} | "
            f"{'✅' if ind else '🔴 없음'} | {re_s} | {reason or '—'} |")
    say()
    n_nosec = sum(1 for it in items if not it["code"] or SEC.get(it["code"]) is None)
    say(f"- 🟢 **섹터코드 없는 건 = {n_nosec}건 / {len(items)}** — "
        "`PREDECISION_2026-09-04_post6.md` PD-9 가 계산 «전»에 적은 «12종목 중 11 존재 · "
        f"삼양바이오팜만 없음»과 {'일치한다' if n_nosec == 0 else '🔴 어긋난다'}"
        "(삼양은 후속이라 이 분모 밖이다).")
    say("- 🔂 **재진입 2건**(`PREREG_POST6.md` §1-5 · PD-3): "
        + " · ".join(f"{it['name']}(`{it['code']}`) 직전 사이클 "
                     f"{REENTRY.get(it['code']) or '**미명시**'} · `P6-PRIOR_CYCLE_IN_WINDOW` = "
                     f"**{PD3_FLAG[it['code']]}**"
                     for it in items if it["code"] in PD3_FLAG)
        + f" ⇒ 플래그 합 **{sum(PD3_FLAG.values())}/{len(items)}**. "
        "**분모 포함 + 제외 민감도 의무**(§7-2).")
    say()
    say("### 1-2. `SEC-G1` — 측정 불가 / `exact` 분모 · **≥ 1/3 ⇒ ⛔ 판정 불가** (§4-3 · `Y3` «차용»)")
    say()
    say("⚠️ **`1/3` 은 «feasible set 공집합 비율»을 재던 문턱이며 커버리지에 대해 검증된 적이 없다** — "
        "`PREREG_POST6.md` §1-6 #6 · `PREREG_RANKING.md` §4-4 의 같은 차용 고지를 승계한다.")
    say()
    say("| 사유 | 설명 | 갈래 의존 |")
    say("|---|---|---|")
    say("| ① | DB 종목코드 부재(레메디형) | 전 갈래 공통 |")
    say("| ② | 유니버스 밖(`market_cap>0 ∧ close>0` 미충족) | 전 갈래 공통 |")
    say("| ③ | 섹터코드 부재(매드업·삼양바이오팜형) | 전 갈래 공통 |")
    say("| ④ | 동료 0 (자기 제외 후 `|P| = 0`) | 🔴 `N` 마다 다르다 |")
    say("| ⑤ | 층에서 미정(`length(induty_code) < N`) | 🔴 `N = 5` 갈래 전용 |")
    say()
    say("| `N` | 측정자 | 측정 가능 | 측정 불가 | 비율 | `SEC-G1`(≥1/3) | 사유별 **건수 · 종목명** |")
    say("|---|---|---|---|---|---|---|")
    G1 = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            bad = [(it, b) for it, b in zip(items, bs) if not b["ok"]]
            rate = len(bad) / len(items)
            G1[(n, mk)] = rate
            by = {}
            for it, b in bad:
                by.setdefault(b["reason"], []).append(it["name"])
            cell = " · ".join(f"{k}:{len(v)}({', '.join(v)})" for k, v in sorted(by.items())) or "—"
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {len(items) - len(bad)}/{len(items)} | {len(bad)} | "
                f"**{rate * 100:.1f}%** | {'🔴 **발동 ⇒ ⛔**' if rate >= G1_THR else '미발동'} | {cell} |")
    say()
    g1_main = G1[(MAIN_N, MAIN_M)]
    say(f"- 🔒 **판정에 쓰는 비율 = 주 갈래(`N = 3` · `SEC-M1`) = {g1_main * 100:.1f}%** ⇒ "
        f"{'🔴 **⛔ `SEC-G1` 발동 — 판정 불가**' if g1_main >= G1_THR else '**미발동 ⇒ 게이트를 연다**'} "
        "(나머지 8 조합은 의무 인쇄 · §4-3 1번).")
    say(f"- 🔬 **훈련 표본 예보는 16.7%** 였다(`FREEZE_SECTOR_2026-09-03.md` §4-2) — 이번 실측 "
        f"**{g1_main * 100:.1f}%**. ⚠️ **예보와 판정은 다른 표본이다**(훈련 {len(train)}건 ↔ 판정 {len(items)}건).")
    say("- 🔴 **편향 방향(그대로 유지)**: 사유 ③ 은 **신규 상장주에 집중**되고 저자는 신규주를 자주 고른다"
        "(§1-5) ⇒ ***측정 불가가 무작위가 아니다.*** 이번 글에서 «빠진 것이 없다»고 그 편향이 사라진 게 "
        "아니다 — 섹터 표에 없는 삼양바이오팜이 **후속(PD-2)이라 애초에 분모 밖**이기도 하다.")
    say(f"- 🔴 **`N = 5` 갈래**: 측정 불가 **{G1[(5, MAIN_M)] * 100:.1f}%** "
        f"{'⇒ 🔴 **발동**' if G1[(5, MAIN_M)] >= G1_THR else '⇒ 미발동'} — 사전등록 §2-1 이 값 보기 «전»에 "
        "*「4개 글 중 3개에서 판정 불가 · 훈련 전체 61.1%」*로 적어 둔 그 갈래이며, "
        "**구조적 미정 비율을 «항상» 함께 박는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §2 drop_rate
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §2. `drop_rate` **표기 가드** (§5 6-1 · `PREREG_POST6.md` §5-2 «원 용도»)")
    say()
    say("🔴 **`1%` 는 «표시» 문턱이지 «판정» 게이트가 아니다.** "
        "🔑 ***0 이라서 안 재는 게 아니라, 0 임을 매회 «보여서» 이 조항이 살아 있음을 증명한다.***")
    say()
    # 🔴 「한 날에 여러 건」 예시는 **이번 분모에서 실측**한다(직전 글의 등록일을 옮겨 적지 않는다).
    _dupd = sorted(d for d in dates if sum(1 for it in items if it["reg"] == d) >= 2)
    say("⚠️ 🔴 **「5열」이라 적지 않는다 — 이 표는 4열이다.** `PREREG_POST6.md` §5-2 의 5번째 열은 "
        "`prev_bar_date` 인데, **이 축의 §2 표는 «등록일» 행**이고 `prev_close` 는 **종목별 `LAG`** 라 "
        "`prev_bar_date` 가 **행마다 유일하지 않다**"
        + (f"(이번 분모 등록일 {' · '.join('`%s`' % d for d in dates)} 중 한 날에 2건 이상인 날 = "
           + (" · ".join("`%s`(%d건)" % (d, sum(1 for it in items if it["reg"] == d))
                              for d in _dupd) if _dupd else "**없음** — 그래도 `prev_bar_date` 는 "
              "«종목별» 값이라 등록일 행과 1:1 이 아니다") + ")")
        + " ⇒ **4열만 인쇄한다.** 🔑 ***열을 못 채우면 「채운 척」하지 말고 "
          "「왜 못 채우는지」를 적는다.***")
    say()
    say("| 등록일 | 그날 `market_cap>0` | 검정 유니버스 | 탈락 | 탈락률 | 🔴 섹터 조인 «후» 탈락 | "
        "섹터 조인 | 커버리지 | `n_up` ∩ 조인 | S-1 동결함수 일치 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for d in dates:
        D = DAY[d]
        drop = D["raw_n"] - D["frozen_n"]
        rate = drop / D["raw_n"]
        cov = len(D["joined"]) / len(D["uni"]) * 100
        say(f"| {d} | {D['raw_n']:,} | {D['frozen_n']:,} | "
            f"{'🔴 **' + format(drop, ',') + '**' if rate >= DROP_MARK else drop} | "
            f"{rate * 100:.2f}%{' 🔴' if rate >= DROP_MARK else ''} | **{D['prev_miss_join']}** | "
            f"{len(D['joined']):,} | {cov:.2f}% | {len(D['nup'])} | "
            f"{'✅' if D['s1_ok'] else '🔴 차 %d' % D['s1_diff']} |")
    say()
    marked = [d for d in dates if (DAY[d]["raw_n"] - DAY[d]["frozen_n"]) / DAY[d]["raw_n"] >= DROP_MARK]
    n_s1 = sum(1 for d in dates if DAY[d]["s1_ok"])
    n_pm = sum(1 for d in dates if DAY[d]["prev_miss_join"] == 0)
    say(f"- 🔴 **표시가 붙은 날 {len(marked)}일**"
        + (" (" + " · ".join("`%s`" % x for x in marked) + ")" if marked else "")
        + " — 그날의 `n_up` 을 **다른 날과 직접 비교하지 말 것**(원 문언 그대로).")
    say(f"- {'🟢' if n_pm == len(dates) else '🔴'} **섹터 조인 «후» 탈락은 {n_pm}/{len(dates)} 등록일 0** "
        "⇒ `SEC-D7`(종가 대비 수익률)의 정의역에 구멍이 없다(§1-4 재현).")
    say(f"- 🟢 **S-1 배선 확인**: `prev_close` 복제본이 `run_regday_post5.load_universe_day`"
        f"(동결 함수 · **import 해서 호출**)와 **집합으로 같다** — **{n_s1}/{len(dates)} 등록일**"
        f"{' ✅ 전부(차집합 크기 0)' if n_s1 == len(dates) else ' 🔴 어긋난 날이 있다'}.")

    # ══════════════════════════════════════════════════════════════════════
    # §3 건별 측정값
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §3. 건별 측정값 — 🔒 주 판정 갈래 (`N = 3` · `SEC-M1`)")
    say()
    say("🔴 **§2-4 대로 «분모»를 매 건 인쇄한다** — `|P|`(동료 수) · `G`(그날 섹터 수) · "
        "`sec_rank`(자기 섹터 제외 · 동률 전부 위 = 보수적) · **원값**(`med`).")
    say("🔴 **`sec_rank` 에 문턱을 «걸지 않는다»**(§2-2) — `RNK-N2` 의 **30** 은 ≈2,760종목을 재던 값이다.")
    say()
    say("| # | 종목 | 등록일 | 섹터(`N=3`) | `|P|` | `G` | `sec_rank` | 원값 `med` | "
        "**`SEC-M1` 백분위** | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for it, b in zip(items, BR[(MAIN_N, MAIN_M)]):
        if b["ok"]:
            say(f"| {it['item_no']} | {it['name']} | {it['reg']} | `{b['sector']}` | {b['peers']} | "
                f"{b['G']} | {b['rank']} | {b['raw'] * 100:+.3f}% | **{b['pct']:.1f}** | — |")
        else:
            say(f"| {it['item_no']} | {it['name']} | {it['reg']} | — | {b.get('peers', '—')} | — | — | "
                f"— | ⛔ 측정 불가 | **{b['reason']}** |")
    say()
    mv = MAIN["vals"]
    if mv:
        pk = [b["peers"] for b in BR[(MAIN_N, MAIN_M)] if b["ok"]]
        say(f"- 백분위 범위 **{min(mv):.1f} ~ {max(mv):.1f}** · 동료 수 `|P|` **{min(pk)} ~ {max(pk)}** "
            f"· 동료 0 인 건 **{sum(1 for x in pk if x == 0)}건**(§7-B #26).")
        say(f"- 글 단위 중앙 = **{fmt(MAIN['main'])}** · 건 pooled 중앙 = **{fmt(MAIN['pooled'])}** "
            f"({med_note(len(mv))}).")
        say("- 🔴🔴 **이 글 하나로만 판정하므로 「글 단위 중앙」과 「건 pooled 중앙」이 «구조적으로 같은 양»이다** "
            "— 글이 하나면 「글별 중앙의 중앙」 = 「그 글의 중앙」이다. ⇒ §7 4축의 ③(집계)은 이 글에서 "
            "**«갈릴 수 없다»**(모호가 아니라 정의다). 다음 글부터 갈릴 수 있다.")
    say()
    say("### 3-1. 9 조합 전부 (`SEC-O1` §4-5 — 판정은 «동결된 하나»로만)")
    say()
    say("| `N` | 측정자 | 측정 가능 | 건별 백분위 | **전체(글 단위 중앙)** | 건 pooled 중앙 |")
    say("|---|---|---|---|---|---|")
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {len(E['vals'])}/{len(items)} | "
                f"{', '.join(f'{v:.1f}' for v in E['vals']) or '—'} | "
                f"**{fmt(E['main'])}** | {fmt(E['pooled'])} |")
    say()
    say("🔒 **판정 갈래 = `N = 3` · `SEC-M1`**(🔒 표시). 나머지 8 조합은 `SEC-V1` 의 «입력»이며 "
        "**판정에 쓰지 않는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §4 귀무·대조
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §4. 귀무 `SEC-N1` · 대칭 대조 `SEC-B1`·`SEC-B2`")
    say()
    say("### 4-0. 추출 풀 한정 손실 (§2-3 — 🔴 «유리한 방향의 처리는 반드시 «크기»를 같이 적는다»)")
    say()
    say("| 갈래 | 풀 | 후보 합계 | 측정 가능 합계 | 한정으로 빠진 수 | 비율 |")
    say("|---|---|---|---|---|---|")
    for n in NS:
        for kind, nm in (("N1", "`SEC-N1` 전 종목"), ("B1", "`SEC-B1` `n_up`")):
            _, loss = pools_for(kind, n, MAIN_M, BR[(n, MAIN_M)], items, DAY)
            tot = sum(a for a, _ in loss)
            keep_n = sum(b for _, b in loss)
            say(f"| `N={n}` | {nm} | {tot:,} | {keep_n:,} | **{tot - keep_n:,}** | "
                + (f"{(tot - keep_n) / tot * 100:.1f}%" if tot else "—") + " |")
    say()
    say("🔴 이 한정은 **저자 쪽에 «유리»한 방향**이다(저자 종목은 전부 동료 ≥ 1). 그래서 크기를 적는다.")
    say()
    say("### 4-1. `SEC-N1` · `SEC-B1` · `SEC-B2` — 9 조합")
    say()
    say(f"귀무 = 각 건의 등록일에 그 풀에서 **무작위 종목 1개** → 같은 측정자·같은 집계 · "
        f"**{NREP:,}회** · 시드 `{SEED}`(스트림 분리) · `p` = `mean(귀무 ≥ 관측)`(등호 포함 · S-5) · "
        "**두 풀 «모두»에서 저자 종목 자신을 뺀다**(M7).")
    say()
    say("🔑 **갈래 사이에는 «공통난수(CRN)»를 쓴다** — 같은 스트림 이름(`sec_n1`·`sec_b1`)을 다시 부르면 "
        "같은 난수열이 나오므로 9 조합이 «같은 추첨»을 공유한다. "
        "🔴 목적이 «다른» 계열(`SEC-X1` 순열·그 안의 귀무)은 §0 대로 **다른 스트림**이다.")
    say()
    say("| `N` | 측정자 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` 승률 | "
        "관측(pooled) | `SEC-N1` `p`(pooled) | `SEC-B1` `p`(pooled) |")
    say("|---|---|---|---|---|---|---|---|---|")
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            if not E["vals"]:
                say(f"| {n}{tag} | `{mk}`{tag} | ⛔ 측정 가능 0건 | — | — | — | — | — | — |")
                continue
            b2 = E["B2"]
            say(f"| {n}{tag} | `{mk}`{tag} | **{fmt(E['main'])}** | "
                f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
                f"**{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}%** "
                f"({b2['wins']}/{b2['n']}) | {fmt(E['pooled'])} | "
                f"{fmt(E['N1']['p_pool'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_pool'], 4) if E['B1'] else '⛔'} |")
    say()
    say("🔴 **매 산출물 의무 문언**(§4-1) — ***`SEC-N1` 은 «`SEC-B1` 없이는» 증거가 아니다.*** "
        "저자 종목은 정의상 급등주이고, 급등주가 섹터 동반성이 높다면 `SEC-N1` 은 그 사실만 되비춘다"
        "(= `REG-M4` 재진술). **정보는 `SEC-B1`·`SEC-B2` 에 있다.**")
    say("🔴 **`SEC-B2` 동률 처리** — 저자 값이 그날 풀 중앙값과 «같으면» **못 넘은 것**으로 센다(보수적).")
    say("")
    say("#### 🔴🔴 `SEC-B2` 의 «비교점» — **50 이 아니라 «그날 `n_up` 풀의 중앙값»이다**")
    say("")
    say("⚠️ 저자 값이 **백분위**라 「50 을 넘었나」로 읽기 쉽지만, `SEC-B2` 가 재는 것은 "
        "***「저자 값 > **그날** 급등주 풀의 중앙값」***이다(§3 5행 정의 축자). "
        "🔑 ***두 비교점은 같은 날에도 크게 다르다*** — 아래 표가 그 차이다.")
    say("")
    say("| 종목 | 등록일 | 저자 값(백분위) | **그날 `n_up` 풀 중앙값** | 풀 크기 | 넘었나 | "
        "(참고) 50 을 넘나 |")
    say("|---|---|---|---|---|---|---|")
    for _d, _it in zip(MAIN["B2"].get("detail", []),
                       [x for x, b in zip(items, MAIN["bs"]) if b["ok"]]):
        say(f"| {_d['name']} | {_it['reg']} | **{_d['value']:.1f}** | "
            f"**{_d['pool_med']:.1f}** | {_d['pool_n']} | "
            + ("🟢 예" if _d["win"] else "🔴 아니오") + " | "
            + ("예" if _d["value"] > 50.0 else "아니오") + " |")
    say("")
    say("🔴 **그러므로 «50 을 넘었다»를 `SEC-B2` 의 근거로 적지 않는다** — "
        "두 잣대가 같은 답을 내는 날도 있고 아닌 날도 있다. "
        "🔒 판정에 쓰는 것은 **그날 풀 중앙값** 쪽 하나뿐이다.")
    say()
    say("### 4-2. 🔴🔴 `SEC-B1` **발화 가능성** — `q_top` 실측 (§4-2 (가) · §7-B #20)")
    say()
    say("🔑 ***「재추출이 성립한다」가 「가드가 발화한다」를 뜻하지 않는다.*** "
        "관측 통계량의 **천장은 100** 이고, 귀무가 그 천장에 **5% 이상**의 질량을 두면 "
        "***어떤 관측으로도 `p < 0.05` 가 나오지 않는다.***")
    say()
    say("🔴 **풀 정의가 둘이다** — ①사전등록 §4-2 (가) 표의 풀 = **`n_up` ∩ 조인** · "
        "②이 표가 쓰는 풀 = 그 위에 **측정 가능(동료 ≥ 1)** 한정. "
        "**①로 구조적 상한(충분조건)을, ②로 실제 발화를 잰다.**")
    say()
    say("⚠️ 🔴 **②열과 `q_top` 은 «날 단위»다 — 건별 «자기 제외»(M7) «전»의 값이다.** "
        "자기 제외가 실제로 걸리는 곳은 **`SEC-B1` 의 추첨 풀**(`pools_for`)이고, 위 §4-1 의 `p` 는 "
        "그 «자기 제외된» 풀로 계산됐다. ⇒ ***이 표의 `q_top` 과 §4-1 의 `p` 는 «분모가 한 건씩 다르다».*** "
        "아래에 **자기 제외까지 넣어 다시 잰 `q_top`** 을 병기해 두 값이 판정을 가르는지 보인다.")
    say()
    say("| 등록일 | ① 풀(`n_up`∩조인) | 고유 섹터 | 최대 섹터 | **최대 점유**(수익률 미사용 충분조건) | "
        "`< 0.135` ? | ② 측정 가능 풀(날 단위) | 🔒 **`q_top`**(1위 섹터 점유 · 문언 정의 · 날 단위) | "
        "(대조) 천장 점유 실측 |")
    say("|---|---|---|---|---|---|---|---|---|")
    QT = {}
    for d in dates:
        D = DAY[d]
        st = D["st"][MAIN_N]
        lab = D["lab"][MAIN_N]
        ix1 = np.array([D["code_i"][c] for c in D["nup"]], dtype=np.int64)
        u1, c1 = np.unique(lab[ix1][lab[ix1] >= 0], return_counts=True)
        share = float(c1.max() / ix1.size)
        pool = [c for c in D["nup"] if st["ok"][D["code_i"][c]]]
        idxs = np.array([D["code_i"][c] for c in pool], dtype=np.int64)
        vidx = np.flatnonzero((lab >= 0) & np.isfinite(D["r"]))
        meds = {int(g): float(np.median(D["r"][vidx][lab[vidx] == g]))
                for g in np.unique(lab[vidx])}
        top = max(meds, key=lambda g: meds[g])
        qtop = float(np.sum(lab[idxs] == top) / idxs.size)
        ceil_share = float(np.mean(st["p1"][idxs] >= 100.0 - 1e-9))
        QT[d] = dict(pool_doc=int(ix1.size), sectors_doc=int(u1.size), maxsec_doc=int(c1.max()),
                     max_share=share, pool_eff=int(idxs.size), qtop=qtop, ceil_share=ceil_share,
                     top=int(top))
        say(f"| {d} | {ix1.size} | {u1.size} | {c1.max()} | **{share:.3f}** | "
            f"{'🟢 예' if share < QTOP_THR else '🔴 아니오'} | {idxs.size} | "
            f"**{qtop:.3f}** | {ceil_share:.3f} |")
    say()
    n_suff = sum(1 for d in dates if QT[d]["max_share"] >= QTOP_THR)
    qmax = max(QT[d]["qtop"] for d in dates)
    qmax_d = max(dates, key=lambda d: QT[d]["qtop"])
    say(f"- 구조적 **충분조건**(최대 단일섹터 점유 `< 0.135`)이 **{len(dates) - n_suff}/{len(dates)} 등록일**에서 "
        f"성립하고 **{n_suff}일**에서 실패한다. 🔴 **「충분조건 실패」는 「`q_top ≥ 0.135`」의 «증명»이 아니다**"
        "(§7-A #8-1 · `FREEZE_SECTOR_2026-09-03.md` §3 ②: ***상한으로 「불가능」을 선언하지 마라***).")
    say(f"- 🔒 **실측 `q_top` 최대 = {qmax:.3f}**(`{qmax_d}`) · "
        + ("🟢 **전 등록일 `< 0.135`**" if qmax < QTOP_THR else "🔴 **`≥ 0.135` 인 날이 있다**") + ".")
    say()
    # 🔴 자기 제외(M7)까지 넣은 `q_top` — `SEC-B1` 이 «실제로» 뽑는 풀과 같은 정의로 다시 잰다.
    qself = []
    for it, b in zip(items, BR[(MAIN_N, MAIN_M)]):
        if not b["ok"]:
            continue
        D = DAY[it["reg"]]
        st = D["st"][MAIN_N]
        lab = D["lab"][MAIN_N]
        pc = [c for c in D["nup"] if st["ok"][D["code_i"][c]] and c != it["code"]]
        if not pc:
            continue
        ix = np.array([D["code_i"][c] for c in pc], dtype=np.int64)
        qself.append((float(np.sum(lab[ix] == QT[it["reg"]]["top"]) / ix.size), it["name"]))
    qmax_self = max(q for q, _ in qself) if qself else float("nan")
    qmax_self_nm = max(qself)[1] if qself else "—"

    kmain = len(MAIN["vals"])
    kposts = len(set(MAIN["posts"])) if MAIN["posts"] else 0
    say("🔒 **발화 조건(동결 · §4-2 (가))** = `P(Binom(k, q_top) ≥ ⌈k/2⌉) < 0.05`. "
        "`q_top` 이 등록일마다 다르므로 **판정 분모의 등록일 중 «최대»**(= 가장 불리한 쪽, 보수적)를 쓴다.")
    say()
    say("| `k` | 뜻 | `q_top`(최대) | `P(Binom(k, q_top) ≥ ⌈k/2⌉)` | 판정 |")
    say("|---|---|---|---|---|")
    fire = {}
    for k, lbl in ((MIN_EXACT, "🔒 사전등록 최소 표본(`PREREG_SELECTION.md` §7)"),
                   (kmain, "🔒 **이 판정의 집계 표본 수**(측정 가능 `exact` 건 = 글 단위 중앙의 분모)"),
                   (kposts, "글 수 (⚠️ 글이 하나뿐이라 «집계의 표본 수»가 아니다 — 아래 주석)")):
        pv = binom_ge_half(k, qmax) if k > 0 else float("nan")
        fire[k] = bool(pv < P_THR)
        say(f"| {k} | {lbl} | {qmax:.3f} (`{qmax_d}`) | **{pv:.4f}** | "
            + ("🟢 발화 가능" if pv < P_THR else "🔴 **⛔ 발화 불가**") + " |")
    say()
    say("⚠️ 🔴 **모호 지점(양쪽 인쇄 · 값 보고 규칙 바꾸지 않는다)** — 사전등록 §4-2 (가)의 `k` 는 "
        "*「관측 통계량(중앙값)의 표본 수」*로 쓰였고 배선 점검은 세 값을 나란히 인쇄했다. "
        f"**이 글 하나로만 판정하는 지금, 글 단위 중앙값을 만드는 표본은 «건 수»({kmain})이지 "
        f"«글 수»({kposts})가 아니다.** 🔒 **판정은 «건 수» 행으로 한다.** "
        + ("🟢 **세 `k` 가 전부 같은 방향이라 이 모호는 판정을 가르지 않는다.**"
           if len(set(fire.values())) == 1 else
           "🔴 **세 `k` 가 갈린다 ⇒ 보수적(발화 불가) 쪽을 쓴다.**"))
    b1fire = fire[kmain] if kmain > 0 else False
    if len(set(fire.values())) > 1:
        b1fire = all(fire.values())
    # 🔴 자기 제외(M7) 정의로 다시 잰 `q_top` 을 «병기»한다 — 문턱도 판정 갈래도 바꾸지 않는다.
    fire_self = {k: binom_ge_half(k, qmax_self) < P_THR for k in (MIN_EXACT, kmain, kposts) if k > 0}
    say(f"- 🔴 **자기 제외(M7)까지 넣어 다시 잰 `q_top`(= `SEC-B1` 이 «실제로» 뽑는 풀과 같은 정의)** "
        f"= 건별 최대 **{qmax_self:.4f}**(`{qmax_self_nm}`) ↔ 위 표의 날 단위 최대 **{qmax:.4f}**. "
        f"자기를 빼면 분모가 하나 줄어 **약간 커진다**(보수적 방향). "
        f"🟢 **세 `k`(**{MIN_EXACT}·{kmain}·{kposts}**) 판정이 두 정의에서 «전부 동일»하다 — "
        f"{'전부 발화 가능' if all(fire_self.values()) and all(fire.values()) else '🔴 갈린다 ⇒ 보수적 쪽을 쓴다'}"
        f"**(`P(Binom({kmain}, {qmax_self:.4f}) ≥ {-(-kmain // 2)})` = "
        f"{binom_ge_half(kmain, qmax_self):.2e}). ⇒ ***이 구분은 발화 판정을 가르지 않는다.***")
    ceil_obs = MAIN["B1"]["ceil_main"] if MAIN["B1"] else None
    say(f"- 🟢 **직접 실측(대조)**: `SEC-B1` 귀무 {NREP:,}회에서 **집계 통계량이 천장(100)에 둔 질량 = "
        f"{fmt(ceil_obs, 4)}** — 문언 정의의 이항 산술과 같은 방향인지 여기서 볼 수 있다. "
        "🔴 **판정은 문언 정의(위 표)로 한다**(S-7).")
    say("- ⇒ 🔒 **`SEC-B1` 발화 " + ("가능**" if b1fire else "**불가** ⇒ ⛔**")
        + " — " + ("문턱을 낮춰 열지 않는다."
                   if b1fire else "🔴 **`SEC-P1` 도 열리지 않는다**(AND). 문턱을 낮춰 열지 않는다."))

    # ══════════════════════════════════════════════════════════════════════
    # §5 SEC-P1 / SEC-P2
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §5. 🔒 `SEC-P1` — **3중 AND** 판정 (§3 1행) · `SEC-P2`")
    say()
    say("🔴 **`SEC-P1` = `SEC-N1 < 5%` ∧ `SEC-B1 < 5%` ∧ `SEC-B2 > 50%`.** "
        "🔴 **모든 ✅ 에는 ⛔ 가 있다** — 아래 표는 성분마다 ⛔ 경로를 같이 적는다.")
    say()
    n1p = MAIN["N1"]["p_main"] if MAIN["N1"] else None
    b1p = MAIN["B1"]["p_main"] if MAIN["B1"] else None
    b2r = MAIN["B2"]["rate"]
    c_n1 = (n1p is not None) and (n1p < P_THR)
    c_b1 = (b1p is not None) and (b1p < P_THR)
    c_b2 = (b2r is not None) and (b2r > B2_THR)
    say("| 성분 | 문턱 (출처 파일) | 관측 | 통과 | ⛔ 경로 |")
    say("|---|---|---|---|---|")
    # 🔴 소수 넷째 자리로 반올림하면 `SEC-N1` 과 `SEC-B1` 이 «같아 보인다» —
    #    실제로는 다른 값이다. ⇒ **재추출 «횟수» 정수를 같이 인쇄**해 착시를 막는다.
    _n1_hits = None if n1p is None else int(round(n1p * NREP))
    _b1_hits = None if b1p is None else int(round(b1p * NREP))
    say(f"| `SEC-N1` | `p < 5%` · `PREREG_REGDAY_MEASURE.md` §4-1 | "
        f"**{fmt(n1p, 5)}** (= **{_n1_hits}**/{NREP:,}) | "
        + ("🟢 통과" if c_n1 else "🔴 미달")
        + " | ≥ 5% ⇒ 불성립 · 해석/재추출 갈림 ⇒ `SEC-V1` |")
    say(f"| `SEC-B1` | `p < 5%` · 〃 | **{fmt(b1p, 5)}** (= **{_b1_hits}**/{NREP:,}) | "
        + ("🟢 통과" if c_b1 else "🔴 미달")
        + " | ≥ 5% ⇒ 🔴 **「급등주 일반 성질과 구분 불가」로 강등** · `q_top ≥ 0.135` ⇒ 발화 불가"
        + f"(이번: {'발화 가능' if b1fire else '🔴 발화 불가'}) |")
    say(f"| `SEC-B2` | **> 50%** · `RESULTS_D1_OOS_POST5.md` §9 W7 «차용» | "
        f"**{fmt(b2r * 100 if b2r is not None else None)}%** ({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | "
        + ("🟢 통과" if c_b2 else "🔴 미달")
        + " | ≤ 50% ⇒ **즉시 「구분 불가」**(등호 포함 = 강등) |")
    say()
    say("| 선행 게이트 | 문턱 (출처) | 이번 | 판정 |")
    say("|---|---|---|---|")
    say(f"| `exact` 최소 표본 | ≥ {MIN_EXACT} · `PREREG_SELECTION.md` §7 | **{len(items)}** | "
        + ("🟢 열림" if len(items) >= MIN_EXACT else "⛔ 미룸") + " |")
    say(f"| `SEC-G1` 커버리지 | < 1/3 · `RESULTS_RECONSTRUCT_POST4.md` §6 Y3 | **{g1_main * 100:.1f}%** | "
        + ("🟢 열림" if g1_main < G1_THR else "🔴 ⛔ 판정 불가") + " |")
    say(f"| `SEC-B1` 발화 가능성 | `P(Binom) < 0.05` · §4-2 (가) | "
        f"**{binom_ge_half(kmain, qmax) if kmain else float('nan'):.4f}** | "
        + ("🟢 열림" if b1fire else "🔴 ⛔ 발화 불가") + " |")
    gates_ok = (len(items) >= MIN_EXACT) and (g1_main < G1_THR) and b1fire
    and_ok = bool(gates_ok and c_n1 and c_b1 and c_b2)
    # 🔴 §3 1행의 ⛔ 열이 `SEC-V1` 을 «판정 불가 조건»으로 열거한다
    #    (`PREREG_SECTOR_COMOVE.md:600`). §7 은 §3 «뒤»에 인쇄되므로 갈림 여부만 앞에서 계산한다.
    #    🔒 적용 범위(`:819`) = 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」뿐이므로
    #    주 갈래의 AND 가 «거짓»인 사건에는 관여하지 않는다 ⇒ `and_ok` 일 때만 ⛔ 로 간다.
    V1PRE = v1_axis_verdicts(EV, G1, MAIN, g1_main, NS, MEAS, MAIN_N, MAIN_M,
                             items, ap_items, b2r, full_eval)
    v1_split_pre = bool(V1PRE["split"])
    p1_blocked = bool(and_ok and v1_split_pre)
    p1_ok = bool(and_ok and not v1_split_pre)
    p1_label = "⛔ 판정 불가" if p1_blocked else ("✅ 성립" if p1_ok else "🔴 불성립")
    p1_word = "판정 불가" if p1_blocked else ("성립" if p1_ok else "불성립")
    say()
    say("### 🔒 판정 — `SEC-P1` : **"
        + ("⛔ 판정 불가(`SEC-V1` 발동)" if p1_blocked
           else ("✅ 성립" if p1_ok else "🔴 불성립(지지 아님)")) + "**")
    say()
    if p1_blocked:
        say("🔴 **3중 AND 는 주 갈래(`N = 3` · `SEC-M1` · 글 단위 중앙 · `exact` 만)에서 «통과»했다** — "
            f"`SEC-N1` **{fmt(n1p, 5)}** · `SEC-B1` **{fmt(b1p, 5)}** · "
            f"`SEC-B2` **{fmt(b2r * 100 if b2r is not None else None)}%** "
            f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}). "
            "🔴 **그러나 이것은 «기록»이지 «선언»이 아니다.**")
        say()
        say("🔒 `PREREG_SECTOR_COMOVE.md` §3 1행의 ⛔ 열이 `SEC-V1` 을 **판정 불가 조건**으로 "
            "열거하고(`:600`), §6 가 *「`SEC-V1` — **4축**(§4-6) 중 하나가 갈림 ⇒ "
            "**갈리지 않는 글이 온다**(잣대를 넓혀 열지 않는다)」*라고 못박는다(`:896`). "
            "그리고 §4-6 적용 범위(`:819`)는 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」이고 "
            "이번 갈림은 **바로 그 경우**다 — 주 갈래 AND 는 참인데 다른 잣대에서 판정이 다르다(§7 표). "
            "⇒ ***이번 글에서는 어느 쪽도 선언하지 않는다.***")
        say()
        say("🔴🔴 **「계열 최초 성립」이라고 쓰지 않는다** — 성립을 «선언»한 적이 없다. "
            "쓸 수 있는 문장은 ***「3중 AND 는 통과했으나 `SEC-V1` 때문에 선언 불가 — "
            "갈리지 않는 글이 오면 판정한다」*** 하나뿐이다. "
            "🔒 문턱을 낮추거나 갈래를 새로 만들어 여는 것은 §6 가 금지한다.")
        say()
        say("🔴 **판정 불가의 뜻도 「테마가 아니다」가 «아니다»**"
            "(§0-2 2번 · 거짓 음성이 구조적이다).")
    elif p1_ok:
        say("🔴 **성립의 뜻은 「섹터 동반성이 존재한다」까지다** — *「테마로 고른다」*의 **확증이 아니다**"
            "(§0-2 천장 · 에코프로 4종목이 KSIC 에서 «세 칸»으로 흩어진다). "
            "그리고 승/패 대조가 미실시이므로 **이 축의 최대치는 「기술」**이다(§0-2 ③).")
    else:
        miss = [nm for nm, ok in (("`SEC-N1`", c_n1), ("`SEC-B1`", c_b1), ("`SEC-B2`", c_b2)) if not ok]
        say("🔴 **AND 가 거짓이다** — 미달 성분: "
            + (" · ".join(miss) if miss else "선행 게이트")
            + ". ⇒ §3 우선순위표대로 **§3 이 판정한다(지지 아님)** · §4-2 는 «인쇄 문언» · "
              "§4-6 은 «민감도 전용»이다.")
        if c_n1 and not c_b1:
            say("🔴 **`SEC-N1` 만 통과한 것을 지지로 인용하지 않는다** — 그 조합의 뜻은 "
                "*「저자가 급등주를 고른다」*이고 그건 `REG-M4` 가 이미 말한 것이다(§2-3 · §4-1). "
                "🔒 인쇄 문언(§4-2) = ***「저자 종목의 섹터 동반성이 같은 날 다른 급등주와 다르지 않다」***.")
        say("🔴 **불성립의 뜻은 「KSIC 섹터 동반상승으로는 안 잡힌다」까지다 — 「테마가 아니다」가 아니다**"
            "(§0-2 2번 · 거짓 음성이 구조적이다).")
    say()
    say("### `SEC-P2` — 글을 넘는 반복 (**기록만** · 검정 통계량 아님)")
    say()
    say("| 글 | 판정 | 누계 |")
    say("|---|---|---|")
    say(f"| post6 (`{POST6_LOG_NO}`) | **{p1_word}** | 성립 "
        f"{1 if p1_ok else 0} / 판정 {0 if p1_blocked else 1} |")
    say()
    say("🔴 **누계를 검정 통계량으로 쓰지 않는다**(`RESULTS_D1_OOS_POST5.md` §8 승계) — "
        "**매 글 독립 판정 + 부호 누계**만 적고 **글별 `p` 를 곱하거나 더하지 않는다**(§2-6).")

    # ══════════════════════════════════════════════════════════════════════
    # §6 SEC-X1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §6. `SEC-X1` 섹터 라벨 **순열 대조군** — 귀무 «구현»의 1종오류율 (§4-4 · `SEC-D6`)")
    say()
    say("🔴🔴 **이 가드가 재는 것은 «귀무 구현의 1종오류율 보정» 하나뿐이다** — "
        "*「칸막이가 정보인가」를 재는 검정이 «아니다»*(§4-4 B-2). 라벨을 섞으면 저자와 귀무가 "
        "**교환 가능**해지므로 ***참 분할이 정보를 담든 잡음이든 `P(p<0.05)` 는 «항상» 5% 다.***")
    say("🔴 **`SEC-X1` 통과를 「섹터가 의미 있다」로 인용하지 않는다** — 그건 `SEC-B1`·`SEC-B2` 가 잰다.")
    say()
    X1_BASE = x1_base_for(items, DAY)
    t_x1 = time.time()
    x1 = x1_run(stream("sec_x1_perm"), stream("sec_x1_null"), X1_REP, dates, DAY, X1_BASE)
    t_x1 = time.time() - t_x1
    say(f"**명세**: 그날 유니버스의 `induty_code` 를 종목 사이에서 무작위로 «섞고»(집단 크기 분포 보존) "
        f"같은 측정자(`SEC-M1` · `N=3`)·같은 귀무를 계산 — **독립 실현 {X1_REP}개** × 귀무 {NREP:,}회.")
    say()
    say("| 풀 | 실현 수 | `p` 평균 | `p` 중앙 | **`p < 0.05` 비율** | `p < 0.20` 비율 | "
        "명목 대비(SE ≈ 1.5%p) | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    x1sum = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        ok = abs(z) <= 2.0
        x1sum[kind] = dict(n=len(ps), mean=float(ps.mean()), median=float(np.median(ps)),
                           lt05=rate, lt20=float(np.mean(ps < 0.20)), z=float(z), pass_=bool(ok))
        say(f"| `SEC-{kind}` | {len(ps)} | {ps.mean():.4f} | {np.median(ps):.4f} | "
            f"**{rate * 100:.1f}%** | {np.mean(ps < 0.20) * 100:.1f}% | "
            f"`z = {z:+.2f}` | " + ("🟢 **보정됨**" if ok else "🔴 **⛔ 절차 무효**") + " |")
    say()
    x1_ok = x1sum["N1"]["pass_"] and x1sum["B1"]["pass_"]
    say(f"- 순열 하 `p` 는 이론상 `U(0,1)` 이므로 `p<0.05` 비율의 기대는 **5.0%**, "
        f"{X1_REP} 실현의 SE ≈ **1.5%p** 다(§4-4). `|z| ≤ 2` 를 «어긋나지 않음»으로 읽는다.")
    if min(x1sum[k]["lt05"] for k in ("N1", "B1")) < P_THR:
        say("- 🔴 **경계값 해석 (비대칭 · 미리 적어 둔다)** — 이번 이탈은 **명목 5%보다 «아래»**"
            f"(**{x1sum['N1']['lt05'] * 100:.1f}%** · **{x1sum['B1']['lt05'] * 100:.1f}%**)다. "
            "그 방향은 ***거짓 «양성»을 만들 수 없고 검정력만 잃는다*** ⇒ "
            "🟢 **이번 «불성립» 판정을 위협하지 않는다**(과소기각은 「지지」를 만들어내지 못한다). "
            "🔴 **반대로 «통과»가 나온 회차에서 같은 부호가 나오면 그때는 위협이 된다** — "
            "그리고 «위쪽»으로 `|z| > 2` 면 그건 부호와 무관하게 ⛔ **절차 무효**다. "
            "🔑 ***가드의 이탈은 「크기」만이 아니라 「방향」까지 읽어야 판정에 대한 함의가 정해진다.***")
    say("- ⇒ 🔒 **`SEC-X1` : "
        + ("🟢 보정됨 ⇒ 절차 유효**" if x1_ok else "🔴 ⛔ 절차 무효 — 이 축을 닫는다**")
        + " (어긋나면 구현을 고친 뒤 **새 사전등록**으로만 연다 · §6).")
    say(f"- 🔴 순열 실현에서 저자 건이 «측정 불가»가 되는 일(섞인 뒤 `|P| = 0`)이 실현당 평균 "
        f"**{np.mean([r['drop'] for r in x1]):.2f}건** 있다. 크기 정합을 위해 그 건은 "
        "관측·귀무 «양쪽»에서 같이 빠진다.")
    say()
    say("### 6-1. 🔴 **가드를 «일부러» 켜서 발동을 실증한다** (§7-B #20 · `x1_bypass` 형식 승계)")
    say()
    say("🔑 ***「조항을 적었다」가 「그 조항이 발동한다」를 뜻하지 않는다*** — **귀무 구현을 «고장내고»**"
        "(추출 풀에서 상위 절반 백분위를 통째로 제거 ⇒ 교환가능성 파괴) 같은 순열 대조군을 돌린다. "
        "가드가 살아 있다면 1종오류율이 5%에서 «어긋나야» 한다.")
    say()
    x1b = x1_run(stream("sec_x1_bypass_perm"), stream("sec_x1_bypass_null"), X1_REP, dates, DAY,
                 X1_BASE, broken=True)
    say("| 귀무 구현 | `p < 0.05` 비율 | `z` | `SEC-X1` 판정 |")
    say("|---|---|---|---|")
    say(f"| 🟢 정상(위 §6 `SEC-N1`) | **{x1sum['N1']['lt05'] * 100:.1f}%** | "
        f"`{x1sum['N1']['z']:+.2f}` | "
        + ("🟢 보정됨 ⇒ 절차 유효" if x1sum["N1"]["pass_"] else "🔴 절차 무효") + " |")
    bx = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1b])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        bx[kind] = dict(lt05=rate, z=float(z), fired=bool(abs(z) > 2.0))
        say(f"| 🔴 **일부러 고장낸 것**(`SEC-{kind}` 풀 상위 절반 제거) | **{rate * 100:.1f}%** | "
            f"`{z:+.2f}` | "
            + ("🔴 **⛔ 절차 무효 — 가드 발동 ✅**" if abs(z) > 2.0 else "🟡 미발동") + " |")
    say()
    fired = bx["N1"]["fired"] or bx["B1"]["fired"]
    say("⇒ " + ("🟢 **`SEC-X1` 이 실제로 발동한다** — 죽은 가드가 아니다."
                if fired else "🔴 **고장낸 구현에서도 발동하지 않았다** — 이 실증은 실패다.")
        + " 🔴 **그리고 이 발동은 「섹터가 무의미하다」와 무관하다** — 잰 것은 «우리 귀무 구현»이다(§4-4).")

    # ══════════════════════════════════════════════════════════════════════
    # §7 SEC-V1 + 재진입 민감도
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §7. `SEC-V1` 민감도 **4축** (§4-6) — 🔴 «민감도 전용»")
    say()
    say("🔒 **적용 범위**: 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」에만 적용된다. "
        "🔴 **§3 의 3중 AND 안에서 한 항목이 미달하는 사건에는 «관여하지 않는다»** — "
        "그건 갈린 게 아니라 **AND 가 거짓인 것**이고 그 판정은 §3 이 한다(§3 우선순위표).")
    say()
    say("⚠️ **「귀무 풀(`SEC-N1` ↔ `SEC-B1`)」은 이 표에 «없다»** — 민감도가 아니라 **판정 조건**이다(§4-6).")
    say()

    def verdict_of(E, g1r):
        if not E["vals"] or E["N1"] is None or E["B1"] is None or E["B2"]["rate"] is None:
            return None
        if g1r is not None and g1r >= G1_THR:
            return None
        return bool(E["N1"]["p_main"] < P_THR and E["B1"]["p_main"] < P_THR
                    and E["B2"]["rate"] > B2_THR)

    def vshow(v):
        return "⛔ 판정 불가" if v is None else ("✅ 성립" if v else "🔴 불성립")

    say("| # | 축 | 갈래 | 값(글 단위 중앙) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | `SEC-P1` | 판정 갈래 |")
    say("|---|---|---|---|---|---|---|---|---|")
    VD = {}

    def vrow(axis, axis_name, label, E, g1r, is_main):
        v = verdict_of(E, g1r)
        VD[(axis, label)] = v
        b2 = E["B2"]
        say(f"| {axis} | {axis_name} | {label} | {fmt(E['main'])} | "
            f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
            f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
            f"{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}% | **{vshow(v)}** | "
            + ("🔒 **판정**" if is_main else "민감도") + " |")

    for n in NS:
        note = " (🔴 구조적 미정 %.1f%% 병기)" % (G1[(5, MAIN_M)] * 100) if n == 5 else ""
        vrow(1, "섹터 깊이", f"`N = {n}`{note}", EV[(n, MAIN_M)], G1[(n, MAIN_M)], n == MAIN_N)
    for mk in MEAS:
        vrow(2, "측정자", f"`{mk}`", EV[(MAIN_N, mk)], G1[(MAIN_N, mk)], mk == MAIN_M)
    v_main = verdict_of(MAIN, g1_main)
    VD[(3, "글 단위 중앙")] = v_main
    say(f"| 3 | 집계 | 글 단위 중앙 | {fmt(MAIN['main'])} | {fmt(n1p, 4)} | {fmt(b1p, 4)} | "
        f"{fmt(b2r * 100 if b2r is not None else None)}% | **{vshow(v_main)}** | 🔒 **판정** |")
    p_pool_n1 = MAIN["N1"]["p_pool"] if MAIN["N1"] else None
    p_pool_b1 = MAIN["B1"]["p_pool"] if MAIN["B1"] else None
    v_pool = None
    if p_pool_n1 is not None and p_pool_b1 is not None and b2r is not None and g1_main < G1_THR:
        v_pool = bool(p_pool_n1 < P_THR and p_pool_b1 < P_THR and b2r > B2_THR)
    VD[(3, "건 pooled 중앙")] = v_pool
    say(f"| 3 | 집계 | 건 pooled 중앙 | {fmt(MAIN['pooled'])} | {fmt(p_pool_n1, 4)} | "
        f"{fmt(p_pool_b1, 4)} | 〃 | **{vshow(v_pool)}** | 민감도 |")
    VD[(4, "`exact` 만")] = v_main
    say(f"| 4 | 등록일 정밀도 | `exact` 만 ({len(items)}건 · 측정 가능 {len(MAIN['vals'])}) | "
        f"{fmt(MAIN['main'])} | {fmt(n1p, 4)} | {fmt(b1p, 4)} | "
        f"{fmt(b2r * 100 if b2r is not None else None)}% | **{vshow(v_main)}** | 🔒 **판정** |")
    if ap_items:
        ap_all_items = items + ap_items
        E_ap = full_eval(ap_all_items, MAIN_N, MAIN_M)
        g1_ap = sum(1 for b in E_ap["bs"] if not b["ok"]) / len(ap_all_items)
        vrow(4, "등록일 정밀도", f"`approx` 포함 ({len(ap_all_items)}건)", E_ap, g1_ap, False)
    else:
        VD[(4, "`approx` 포함")] = v_main
        say(f"| 4 | 등록일 정밀도 | `approx` 포함 (**추가 0건**) | {fmt(MAIN['main'])} | "
            f"{fmt(n1p, 4)} | {fmt(b1p, 4)} | {fmt(b2r * 100 if b2r is not None else None)}% | "
            f"**{vshow(v_main)}** | 민감도(**구조적으로 동일**) |")
    say()
    if not ap_items:
        say("🟢 **축 ④ 는 이 글에서 «구조적으로» 갈릴 수 없다** — post6 의 `approx` 가 **0건**이라 "
            "「`approx` 포함」 집합이 「`exact` 만」과 **같은 집합**이다(모호가 아니라 정의다). "
            "🔴 그래서 이 축의 «불갈림»을 **잣대 강건성의 증거로 읽지 않는다.**")
    say("🟢 **축 ③ 도 이 글에서 «구조적으로» 갈릴 수 없다** — 글이 하나뿐이라 "
        "글 단위 중앙 = 건 pooled 중앙이다(§3 말미). "
        "⚠️ 다만 **귀무 집계는 다른 경로로 계산되므로 `p` 는 미세하게 다를 수 있다** — "
        "위 표에 두 `p` 를 «둘 다» 인쇄했다.")
    vals_v = list(VD.values())
    kinds = {str(v): v for v in vals_v}
    split = len(kinds) > 1
    # 🔒 §3 이 «앞에서» 쓴 값과 같아야 한다 — 같은 `verdict_of` · 같은 4축(§4-6).
    assert split == v1_split_pre, ("SEC-V1 배선 불일치", split, v1_split_pre)
    say()
    say("### 🔒 `SEC-V1` : **" + ("🔴 갈린다" if split else "🟢 갈리지 않는다") + "** "
        + f"({len(kinds)}종 판정 — "
        + " · ".join(f"{vshow(v)}:{sum(1 for x in vals_v if str(x) == k)}"
                     for k, v in sorted(kinds.items())) + ")")
    say()
    if split:
        say("🔴 **갈렸다 ⇒ §4-6 대로 «어느 쪽도 선언하지 않는다».** "
            "🔒 §3 1행의 ⛔ 열이 `SEC-V1` 을 **판정 불가 조건**으로 열거하므로"
            "(`PREREG_SECTOR_COMOVE.md:600`) 이 갈림은 §3 의 `SEC-P1` 을 ⛔ 로 만든다 — "
            "**위 §3 에 그렇게 인쇄돼 있다.** "
            "🔴 **단 적용 범위(`:819`)는 「같은 판정을 «다른 잣대»로 다시 계산했을 때 "
            "갈리는가」뿐이다** — 주 갈래의 3중 AND 가 «거짓»인 사건은 §3 이 판정하고 이 조항은 "
            "관여하지 않는다. ***어느 쪽이든 잣대를 넓혀 열지 않는다.***")
    else:
        say("🟢 **4축 어디서도 판정이 갈리지 않는다** ⇒ `SEC-V1` 은 발동하지 않는다. "
            "🔴 **그래도 이것을 「결론이 튼튼하다」로 읽지 않는다** — 갈릴 수 «없는» 축이 둘(③·④) 있다(위).")
    say()
    say("#### 🔴🔴 7-1A. 모호 지점 — **`SEC-V1` 의 «입력»이 4축인가 9 조합인가** (양쪽 인쇄)")
    say()
    say("사전등록이 두 곳에서 다르게 읽힌다. **어느 쪽으로도 고치지 않고 둘 다 인쇄한다.**")
    say()
    say("| 읽기 | 근거 문언 | 무엇을 세나 |")
    say("|---|---|---|")
    say("| **A**(위 표 · 이 스크립트의 판정) | §4-6 *「아래 **4축**을 «항상» 나란히 인쇄한다」* — 표가 "
        "**한 번에 한 축**만 흔든다(`N` 은 `SEC-M1` 에서 · 측정자는 `N=3` 에서) | 위 10행 |")
    say("| **B**(확장) | §4-5 *「**9 조합**을 다 인쇄하되 판정은 «동결된 하나»로만 한다. "
        "나머지는 `SEC-V1` 의 «입력»이다」* | 9 조합 «전부»(대각선 조합 포함) |")
    say()
    say("| `N` | 측정자 | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | `SEC-G1` | 3중 AND |")
    say("|---|---|---|---|---|---|---|")
    ext = {}
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            v = verdict_of(E, G1[(n, mk)])
            ext[(n, mk)] = v
            b2 = E["B2"]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | "
                f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
                f"{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}% | "
                f"{G1[(n, mk)] * 100:.1f}% | **{vshow(v)}** |")
    say()
    passers = [f"`N={n}` × `{mk}`" for (n, mk), v in ext.items() if v]
    ext_kinds = {str(v): v for v in ext.values()}
    say(f"- 🔴 **읽기 B 에서 3중 AND 를 통과하는 조합 = {len(passers)}개**"
        + (f": **{' · '.join(passers)}**" if passers else " — 없다") + ".")
    if passers and not p1_ok:
        say("- 🔴🔴 **그 조합은 판정 갈래가 «아니고», 읽기 A 의 4축 «어느 항목도» 아니다**"
            "(두 축을 «동시에» 흔든 대각선 조합이다). 🔒 **§4-5 문언 그대로 판정은 «동결된 하나»로만 "
            "한다** ⇒ ***이 통과를 `SEC-P1` 의 지지로 인용하는 것은 금지된다.*** "
            "🔑 ***값을 보고 갈래를 고르면 그게 사후적합이다.***")
        say(f"- 🟢 **그리고 두 읽기 «어느 쪽으로도» 결론이 같다** — 읽기 A 는 {len(kinds)}종, "
            f"읽기 B 는 {len(ext_kinds)}종 ⇒ **둘 다 「갈린다」**이고, 그래서 §4-6 의 "
            "「어느 쪽도 선언하지 않는다」가 **읽기를 고르는 것과 무관하게** 발동한다. "
            "주 갈래의 3중 AND 자체는 §3 이 «기록»으로 남긴다(§5).")
        say("- 🔴 **그래도 이 사실을 숨기지 않는다** — 이 축에서 「통과하는 잣대가 «존재»한다」는 것은 "
            "***다음 글에서 `SEC-D1`·`SEC-D2` 를 바꾸고 싶어지는 압력***이고, 그 압력이 곧 "
            "이 프로그램이 금지한 동작이다. **바꾸려면 새 사전등록이 필요하다.**")
    say()
    say("### 7-2. 🔂 재진입 2건 **제외** 민감도 (`PREREG_POST6.md` §1-5 · PD-3 — 의무)")
    say()
    keep = [it for it in items if it["code"] not in PD3_FLAG]
    E_re = full_eval(keep, MAIN_N, MAIN_M)
    g1_re = sum(1 for b in E_re["bs"] if not b["ok"]) / len(keep) if keep else None
    v_re = verdict_of(E_re, g1_re)
    say("| 갈래 | 분모 | 측정 가능 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | "
        "`SEC-G1` | `SEC-P1` |")
    say("|---|---|---|---|---|---|---|---|---|")
    say(f"| 🔒 **포함**(판정) | {len(items)} | {len(MAIN['vals'])} | {fmt(MAIN['main'])} | "
        f"{fmt(n1p, 4)} | {fmt(b1p, 4)} | {fmt(b2r * 100 if b2r is not None else None)}% "
        f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | {g1_main * 100:.1f}% | **{vshow(v_main)}** |")
    say(f"| 제외(민감도) | {len(keep)} | {len(E_re['vals'])} | {fmt(E_re['main'])} | "
        f"{fmt(E_re['N1']['p_main'], 4) if E_re['N1'] else '⛔'} | "
        f"{fmt(E_re['B1']['p_main'], 4) if E_re['B1'] else '⛔'} | "
        f"{fmt(E_re['B2']['rate'] * 100 if E_re['B2']['rate'] is not None else None)}% "
        f"({E_re['B2']['wins']}/{E_re['B2']['n']}) | "
        + (f"{g1_re * 100:.1f}%" if g1_re is not None else "—") + f" | **{vshow(v_re)}** |")
    say()
    say("- 🔒 **분모는 «포함»이다**(§1-5 1번) — 제외는 **의무 민감도**다. 두 갈래 판정 = **"
        + ("같다" if str(v_re) == str(v_main) else "🔴 다르다 ⇒ 「재진입 의존」으로 적는다") + "**.")
    say(f"- `P6-PRIOR_CYCLE_IN_WINDOW` 합 = **{sum(PD3_FLAG.values())}/{len(items)}** ("
        + " · ".join(f"`{c}`={v}" for c, v in sorted(PD3_FLAG.items()))
        + ") — PD-3 이 계산 «전»에 못박은 값이다.")

    # ══════════════════════════════════════════════════════════════════════
    # §8 SEC-O1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §8. `SEC-O1` — 훈련(post1~5 🔬) ↔ 검증(post6 🔒) **나란히** (§4-5)")
    say()
    say("🔴 **훈련 성적을 판정 분모에 절대 넣지 않는다**(§4-5 · `PREREG_POST6.md` §2-1 ③ 문형). "
        "아래 훈련 열은 **탐색적 표기**이며, 세 열의 뜻이 서로 다르다:")
    say()
    say("| 열 | 뜻 |")
    say("|---|---|")
    say(f"| 훈련(동결) | `FREEZE_SECTOR_2026-09-03.md` §4-2 — **DB 스냅샷 `{FROZEN_TRAIN['db_snapshot']}`** |")
    say(f"| 훈련(재계산) | 같은 post1~5 표본을 **이 실행의 DB 스냅샷 `{END}`** 로 다시 잰 값 |")
    say(f"| 🔒 검증(post6) | **판정** — 분모 post6 신규 `exact` {len(items)}건 |")
    say()
    E_tr = full_eval(train, MAIN_N, MAIN_M)
    g1_tr = sum(1 for b in E_tr["bs"] if not b["ok"]) / len(train)
    tr_n1 = E_tr["N1"]["p_main"] if E_tr["N1"] else None
    tr_b1 = E_tr["B1"]["p_main"] if E_tr["B1"] else None
    tr_b2 = E_tr["B2"]["rate"]

    def gap(a, b, nd=4):
        if a is None or b is None:
            return "—"
        return f"{b - a:+.{nd}f}"

    say(f"| 항목 | 훈련(동결 · {FROZEN_TRAIN['db_snapshot']}) | 훈련(재계산 · {END}) | "
        "🔴 훈련 괴리 | 🔒 검증 post6 | 🔴 **훈련↔검증 괴리** |")
    say("|---|---|---|---|---|---|")
    say(f"| 분모 `exact` | {FROZEN_TRAIN['n_items']} | {len(train)} | "
        + ("✅ 같다" if len(train) == FROZEN_TRAIN["n_items"] else "🔴 다르다")
        + f" | **{len(items)}** | — |")
    say(f"| 측정 가능 | {FROZEN_TRAIN['n_measurable']} | {len(E_tr['vals'])} | "
        + ("✅" if len(E_tr["vals"]) == FROZEN_TRAIN["n_measurable"] else "🔴")
        + f" | **{len(MAIN['vals'])}** | — |")
    say(f"| 관측(글 단위 중앙) | {FROZEN_TRAIN['main']:.1f} | {fmt(E_tr['main'])} | "
        f"{gap(FROZEN_TRAIN['main'], E_tr['main'], 1)} | **{fmt(MAIN['main'])}** | "
        f"**{gap(E_tr['main'], MAIN['main'], 1)}** |")
    say(f"| `SEC-N1` `p` | {FROZEN_TRAIN['N1']:.4f} | {fmt(tr_n1, 4)} | "
        f"{gap(FROZEN_TRAIN['N1'], tr_n1)} | **{fmt(n1p, 4)}** | **{gap(tr_n1, n1p)}** |")
    say(f"| `SEC-B1` `p` | {FROZEN_TRAIN['B1']:.4f} | {fmt(tr_b1, 4)} | "
        f"{gap(FROZEN_TRAIN['B1'], tr_b1)} | **{fmt(b1p, 4)}** | **{gap(tr_b1, b1p)}** |")
    say(f"| `SEC-B2` 승률 | {FROZEN_TRAIN['B2'] * 100:.1f}% "
        f"({FROZEN_TRAIN['B2_wins']}/{FROZEN_TRAIN['B2_n']}) | "
        f"{fmt(tr_b2 * 100 if tr_b2 is not None else None)}% ({E_tr['B2']['wins']}/{E_tr['B2']['n']}) | "
        f"{gap(FROZEN_TRAIN['B2'] * 100, tr_b2 * 100 if tr_b2 is not None else None, 1)}%p | "
        f"**{fmt(b2r * 100 if b2r is not None else None)}%** "
        f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | "
        f"**{gap(tr_b2 * 100 if tr_b2 is not None else None, b2r * 100 if b2r is not None else None, 1)}%p** |")
    say(f"| `SEC-G1` | {FROZEN_TRAIN['G1'] * 100:.1f}% | {g1_tr * 100:.1f}% | "
        f"{gap(FROZEN_TRAIN['G1'] * 100, g1_tr * 100, 1)}%p | **{g1_main * 100:.1f}%** | "
        f"**{gap(g1_tr * 100, g1_main * 100, 1)}%p** |")
    say()
    drift = [nm for nm, a, b in (
        ("관측", FROZEN_TRAIN["main"], E_tr["main"]),
        ("`SEC-N1`", FROZEN_TRAIN["N1"], tr_n1),
        ("`SEC-B1`", FROZEN_TRAIN["B1"], tr_b1),
        ("`SEC-B2`", FROZEN_TRAIN["B2"], tr_b2),
        ("`SEC-G1`", FROZEN_TRAIN["G1"], g1_tr))
        if a is not None and b is not None and abs(a - b) > 1e-9]
    # 🔴 「이 기간에 자란 종목」을 **하드코딩하지 않고 실측한다** — 동결 훈련 DB 스냅샷
    #    «뒤»에 첫 봉이 생긴 종목이 곧 「두 창 사이 신규」다(코드 상수 인용 금지).
    cur.execute("SELECT stock_code, min(date) FROM daily_prices GROUP BY 1 "
                "HAVING min(date) > %s ORDER BY 2, 1", (FROZEN_TRAIN["db_snapshot"],))
    grew = [(c, str(d)) for c, d in cur.fetchall()]
    si_absent = [c for c, _ in grew if c not in SEC]
    grew_txt = " · ".join("`%s`(첫 봉 %s)" % (c, d) for c, d in grew) if grew else "없음"
    say(f"- 🔴 **훈련 괴리(동결 ↔ 재계산) = {len(drift)}항목**"
        + (f": {' · '.join(drift)}" if drift else " — 🟢 **전부 일치**")
        + f". 🔴 **「DB 가 자라서」 가설은 «실측으로 기각»한다** — 동결 훈련 스냅샷"
          f"(`{FROZEN_TRAIN['db_snapshot']}`) «뒤»에 첫 봉이 생긴 종목은 **{len(grew)}종목**"
          f"({grew_txt})이고, 그 중 **`stock_industry` 에 없는 것 {len(si_absent)}/{len(grew)}** = "
          f"{'·'.join('`%s`' % c for c in si_absent) if si_absent else '없음'} ⇒ "
        + ("***조인 유니버스에 애초에 진입하지 못한다*** ⇒ `SEC-` 측정값을 움직일 «경로가 없다». "
           "🟢 **남는 설명은 하나뿐 — 동결본에 적힌 값이 «반올림 표기»라서다**"
           "(바로 아래 줄이 그 대조다)."
           if len(si_absent) == len(grew) else
           "🔴🔴 **일부는 조인 유니버스에 «들어온다» ⇒ 이 가설을 기각할 수 없다** — "
           "아래 반올림 대조와 «함께» 읽어야 한다."))
    # 🔴 위 «괴리» 판정은 «전정밀도 float ↔ 동결본의 «인쇄된» 반올림 값»을 비교한다.
    #    같은 대조를 **동결본이 인쇄한 정밀도로** 한 번 더 인쇄한다(양쪽 인쇄 · 규칙 변경 아님).
    same_print = [nm for nm, a, b, nd in (
        ("관측", FROZEN_TRAIN["main"], E_tr["main"], 1),
        ("`SEC-N1`", FROZEN_TRAIN["N1"], tr_n1, 4),
        ("`SEC-B1`", FROZEN_TRAIN["B1"], tr_b1, 4),
        ("`SEC-B2`", FROZEN_TRAIN["B2"], tr_b2, 2),
        ("`SEC-G1`", FROZEN_TRAIN["G1"], g1_tr, 3))
        if a is not None and b is not None and f"{a:.{nd}f}" == f"{b:.{nd}f}"]
    say(f"- 🟢 **같은 대조를 «동결본이 인쇄한 정밀도»로 하면 {len(same_print)}/5 항목이 일치한다**"
        + (f"({' · '.join(same_print)}). " if same_print else ". ")
        + "🔑 ***그러므로 위 「괴리 2항목」은 «DB 가 값을 움직였다»가 아니라 "
          "«동결본에 적힌 값이 반올림 표기»라서 생긴 것이다*** — 두 문장은 다르고, "
          "**둘 다 인쇄해야 어느 쪽인지 갈린다.**")
    say("- 🟢 **독립 확인**: 같은 실행의 배선 점검 모드 산출물에서도 `sector_dryrun/` 의 건별 JSON "
        "18건·`cases.tsv` 데이터 행이 동결본과 **byte 단위로 같다**(바뀐 것은 «DB 스냅샷 날짜 문자열»뿐). "
        "⇒ ***`SEC-` 측정값은 이번 DB 성장에 «불변»이었다.***")
    say("- 🔴 **훈련↔검증 괴리를 「악화/개선」으로 읽지 않는다** — 두 열은 **다른 표본**이고 훈련은 "
        "**판정 분모 «밖»**이다(§4-5). 나란히 두는 것은 *「잣대를 고른 것을 신고했나」*를 보이기 "
        "위해서지 두 열을 비교 검정하기 위해서가 아니다.")
    say("- 🔒 **`SEC-O1` 판정** = 잣대 결정(`SEC-D1`·`D2`) **2026-09-02** ↔ 배선 점검 **2026-09-02** ↔ "
        "동결 커밋 **2026-09-03** ↔ `fetch_post.py` **2026-09-04 18:50 KST** ↔ 이 계산 **그 «후»** "
        "⇒ 🟢 **결정이 §0-4 4번 «앞»이다 — 유효**(⛔ 경로 = 결정이 4번 «뒤»면 무효 · PD-0 이 증거).")

    # ══════════════════════════════════════════════════════════════════════
    # §9 미해소·한계
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §9. 판정 불가·미해소·한계")
    say()
    say("| 항목 | 상태 |")
    say("|---|---|")
    say("| `SEC-P1` | **" + p1_label + "**"
        + (" — 🔴 3중 AND 는 통과했으나 `SEC-V1`(4축 갈림)이 ⛔ 다(§3 1행 ⛔ 열 · §6). "
           "***「계열 최초 성립」이 아니다*** — 갈리지 않는 글이 오면 판정한다" if p1_blocked else
           " — 천장은 §0-2(성립 = 「섹터 동반성 존재」까지 · 불성립 = 「KSIC 섹터 동반상승으로는 "
           "안 잡힌다」까지)") + " |")
    say(f"| `SEC-P2` | 🔒 **기록만** — **이 글에서** 판정 {0 if p1_blocked else 1}회"
        + ("(⛔ 판정 불가라 누계 «분모»에 안 들어간다)" if p1_blocked else "")
        + f" · 성립 {1 if p1_ok else 0}회. 누계를 검정 통계량으로 쓰지 않는다 |")
    say("| `SEC-B1` 발화 | " + ("🟢 가능" if b1fire else "🔴 ⛔ 발화 불가")
        + f" (`q_top` 최대 {qmax:.3f} · 문턱 {QTOP_THR}) |")
    say("| `SEC-X1` | " + ("🟢 보정됨" if x1_ok else "🔴 ⛔ 절차 무효") + " · 고장 실증 "
        + ("✅ 발동" if fired else "🔴 미발동(실증 실패)") + " |")
    say("| `SEC-V1` | " + ("🔴 갈린다 ⇒ 선언 금지" if split else "🟢 갈리지 않는다")
        + " — 🔴 축 ③·④ 는 이 글에서 «구조적으로» 갈릴 수 없다 |")
    say("| 승/패 대조(`PREREG_SELECTION.md` §4) | ⛔ **3회 연속 미실시** — post6 `exact` 신규에 "
        "`all_loss = 1` 이 0건(`INTAKE_2026-09-04_post6.md` §2 7번) ⇒ "
        "***이 축의 최대치는 「기술」이다***(§0-2 ③) |")
    say("| 「테마로 고른다」 확증 | ⛔ **이 축에서는 «영구히» 열리지 않는다**(§0-2 · §9 · "
        "에코프로 4종목 → 3칸) |")
    say("| 「섹터 안 «누구»냐」 | ⛔ **미해결** — `RNK-` 축이 멈춘 그 공백이 한 층 위로 옮겨갈 뿐이다(§9) |")
    say("| 후속 2건(광전자·삼양바이오팜) | 🔒 **분모 밖**(PD-2 · `reg_date_precision = none` · "
        "이중계상 금지). 🔴 그중 삼양바이오팜은 **섹터 표에 없다** ⇒ 분모에 넣었다면 사유 ③ 이었다 |")
    say("| 표본이 저자가 «올리기로 고른» 매매 | 🔴 **그대로** — 결과 조건화 위협"
        "(`PREREG_SELECTION.md` §0) |")
    say("| `regen_gate.py` | ⬜ **관리자** — `PAIRS[\"RESULTS_SECTOR_POST6_NUMBERS.md\"]` 가 아직 "
        "`PENDING` 에 있어, 이 파일이 «생긴» 지금 `check()` 는 *「산출물이 생겼는데 `PENDING` 에 "
        "남아 있다」* 로 **FAIL 한다**. 🔒 **설계된 상태**이며 해소(=`PENDING` 에서 빼고 `--update`)는 "
        "동결·머지 레인의 동작이다 |")
    say(f"| 스냅샷 의존 | 🔴 **가격 표도 섹터 표도 자란다** — 이 글의 값은 `daily_prices` "
        f"`max(date)` = **`{END}`** · `stock_industry` **{si_rows:,}행** · `max(updated_at)` "
        f"**`{si_upd}`** 위에서만 재현된다(§2-6 · §8-5) |")
    say()
    say("🔴 **매 산출물 의무 문언 재확인**: 거짓 음성이 구조적이다 — 테마는 KSIC 축을 가로지른다"
        "(에코프로 4종목 → 3칸). ⇒ ***`SEC-P1` 불성립을 「테마가 아니다」로 읽지 않는다.***")
    say("🔴 **동반 상승은 «등록일 종가가 확정된 뒤»의 정보로 잰다** ⇒ ***이 축은 라이브에서 재현할 수 "
        "없는 지표다***(§9 · `REG-M5` 형 단서).")
    say("🔴 **이 실행은 새 예측을 만들지 않았다** — `SEC-P1`·`P2`·`N1`·`B1`·`B2`·`G1`·`X1`·`O1`·`V1` 은 "
        "전부 사전등록 §3 표의 항목이고, 새 문턱·새 측정자·새 갈래는 **0건**이다.")
    say()
    say("---")
    say()
    say(f"결정성: 시드 `{SEED}` 고정 · 스트림 분리 · DB 는 SELECT 만 ⇒ **같은 DB 스냅샷에서 재실행하면 "
        "byte 단위로 같다**(`regen_gate.py --rerun` 전제). "
        "🔴 그래서 이 파일에는 **실행 시간·커밋 해시를 적지 않는다** — 벽시계·`HEAD` 는 stdout 전용이다. "
        "🔑 ***커밋마다 바뀌는 값을 산출물에 적으면 그 산출물은 자기 자신을 재현할 수 없게 된다.***")
    say()
    say("[[PREREG_SECTOR_COMOVE]] · [[FREEZE_SECTOR_2026-09-03]] · [[RESULTS_SECTOR_DRYRUN]] · "
        "[[PREREG_POST6]] · [[PREDECISION_2026-09-04_post6]] · [[INTAKE_2026-09-04_post6]] · "
        "[[PREREG_RANKING]] · [[FINDING_THEME_AXIS]] · [[RESULTS_RANKING_TRAIN]] · "
        "[[RESULTS_REGDAY_POST5]] · [[RESULTS_D1_OOS_POST5]] · [[RESULTS_RECONSTRUCT_POST4]] · "
        "[[PREREG_SELECTION]]")

    # ══════════════════════════════════════════════════════════════════════
    # 기계 산출물
    # ══════════════════════════════════════════════════════════════════════
    universe = {d: DAY[d]["uni"] for d in all_dates}
    joined = {d: DAY[d]["joined"] for d in all_dates}
    (ART / "universe_snapshot.json").write_text(json.dumps({
        "db_snapshot_max_date": END, "post_log_no": POST6_LOG_NO, "post_date": "2026-09-04",
        "window_end_note": "창 종료 2026-09-04 = 발행 당일 봉 «포함»(PD-1) · "
                           "이 축은 창을 쓰지 않고 등록일 당일만 쓴다",
        "pseudo_from_code": list(PSEUDO),
        "pseudo_nonnumeric_in_db": nonnum, "pseudo_final": final_pseudo,
        "universe_sizes": {d: len(universe[d]) for d in all_dates},
        "joined_sizes": {d: len(joined[d]) for d in all_dates},
        "coverage_pct": {d: round(len(joined[d]) / len(universe[d]) * 100, 4) for d in all_dates},
        "universe": universe, "joined": joined,
        "sha256_universe": {d: sha_list(universe[d]) for d in all_dates},
        "sha256_joined": {d: sha_list(joined[d]) for d in all_dates},
        "_notation": NOTATION_POST6,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "sector_snapshot.json").write_text(json.dumps({
        "table": "stock_industry", "rows": si_rows, "distinct_stock_code": si_uniq,
        "induty_code_non_null": si_nonnull, "max_updated_at": si_upd,
        "sha256_code_to_induty": si_sha,
        "length_distribution_table": {str(k): v for k, v in sorted(len_all.items())},
        "stock_info_sector_non_null": info_sector, "stock_info_rows": info_rows,
        "warning": "이 표는 시간에 따라 «자란다» — 편입이 늘면 같은 글의 값이 달라진다",
        "_notation": NOTATION_POST6,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for ci, it in enumerate(items):
        rec = {k: it[k] for k in ("post", "log_no", "item_no", "name", "code", "reg", "prec", "all_loss")}
        rec["db_snapshot_max_date"] = END
        rec["main_branch"] = {"N": MAIN_N, "measure": MAIN_M}
        rec["reentry"] = ({"prior_cycle_reg_date": REENTRY.get(it["code"]),
                           "P6_PRIOR_CYCLE_IN_WINDOW": PD3_FLAG.get(it["code"])}
                          if it["code"] in PD3_FLAG else None)
        rec["branches"] = {}
        for n in NS:
            for mk in MEAS:
                bb = BR[(n, mk)][ci]
                rec["branches"][f"N{n}_{mk}"] = {
                    kk: (round(vv, 6) if isinstance(vv, float) else vv)
                    for kk, vv in bb.items()}
        rec["_notation"] = NOTATION_POST6
        (ART / f"case_{it['post']}_{it['item_no']}_{it['name']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "verdict.json").write_text(json.dumps({
        "post_log_no": POST6_LOG_NO, "post_date": "2026-09-04",
        "db_snapshot_max_date": END,
        "main_branch": {"N": MAIN_N, "measure": MAIN_M},
        "denominator_exact": len(items), "measurable": len(MAIN["vals"]),
        "excluded_none_rows": [r["stock_name"] for r in none_rows],
        "gates": {
            "min_exact": {"threshold": MIN_EXACT, "n": len(items),
                          "open": bool(len(items) >= MIN_EXACT)},
            "SEC-G1": {"threshold": G1_THR, "rate": g1_main, "open": bool(g1_main < G1_THR)},
            "SEC-B1_fire": {"q_top_max": qmax, "q_top_threshold": QTOP_THR, "k": kmain,
                            "p_ceiling": (binom_ge_half(kmain, qmax) if kmain else None),
                            "open": bool(b1fire)},
            "SEC-X1": {"lt05_N1": x1sum["N1"]["lt05"], "lt05_B1": x1sum["B1"]["lt05"],
                       "z_N1": x1sum["N1"]["z"], "z_B1": x1sum["B1"]["z"], "open": bool(x1_ok)},
        },
        "SEC-P1": {"components": {"SEC-N1": n1p, "SEC-B1": b1p, "SEC-B2": b2r},
                   "thresholds": {"SEC-N1": P_THR, "SEC-B1": P_THR, "SEC-B2": B2_THR},
                   "passed": {"SEC-N1": bool(c_n1), "SEC-B1": bool(c_b1), "SEC-B2": bool(c_b2)},
                   "and_passed": and_ok,
                   "SEC-V1_split": v1_split_pre,
                   "blocked_by_SEC-V1": p1_blocked,
                   "verdict": (None if p1_blocked else p1_ok),
                   "verdict_label": p1_word},
        "SEC-P2": {"note": "기록만 — 검정 통계량 아님", "n_judgements": 1,
                   "n_support": 1 if p1_ok else 0},
        "SEC-V1": {"split": bool(split),
                   "by_branch": {f"{a}|{b}": v for (a, b), v in VD.items()}},
        "reentry_sensitivity": {"excluded_codes": sorted(PD3_FLAG),
                                "P6_PRIOR_CYCLE_IN_WINDOW": PD3_FLAG,
                                "verdict_kept": v_main, "verdict_excluded": v_re,
                                "main_kept": MAIN["main"], "main_excluded": E_re["main"]},
        "SEC-O1": {"frozen_train": FROZEN_TRAIN,
                   "recomputed_train": {"main": E_tr["main"], "SEC-N1": tr_n1, "SEC-B1": tr_b1,
                                        "SEC-B2": tr_b2, "SEC-G1": g1_tr,
                                        "n_items": len(train), "n_measurable": len(E_tr["vals"])},
                   "drift_items": drift},
        "_notation": NOTATION_POST6,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "controls_summary.json").write_text(json.dumps({
        "seed": SEED, "nrep": NREP, "note_nrep": "run_selection.py:22 는 NREP=2000",
        "streams": _STREAM_NAMES, "x1_realizations": X1_REP,
        "db_snapshot_max_date": END,
        "thresholds": {"p": P_THR, "B2": B2_THR, "G1": G1_THR, "q_top": QTOP_THR,
                       "n_up_multiplier": UP_MULT, "drop_mark": DROP_MARK,
                       "min_exact": MIN_EXACT},
        "observed": {f"N{n}_{mk}": {"main": EV[(n, mk)]["main"], "pooled": EV[(n, mk)]["pooled"],
                                    "n_measurable": len(EV[(n, mk)]["vals"])}
                     for n in NS for mk in MEAS},
        "nulls": {f"N{n}_{mk}": {"SEC-N1": EV[(n, mk)]["N1"], "SEC-B1": EV[(n, mk)]["B1"],
                                 "SEC-B2": EV[(n, mk)]["B2"]}
                  for n in NS for mk in MEAS},
        "G1_rate": {f"N{n}_{mk}": G1[(n, mk)] for n in NS for mk in MEAS},
        "q_top": QT,
        "SEC-X1": {"normal": x1sum, "deliberately_broken": bx,
                   "note": "재는 것은 «귀무 구현의 1종오류율» 하나뿐 — 분할의 정보량과 무관하다(§4-4)"},
        "_notation": NOTATION_POST6,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    with (ART / "cases.tsv").open("w", encoding="utf-8") as f:
        f.write("# RESULTS_SECTOR_POST6 — 건별 측정값 (기계 생성 · 🔒 판정)\n")
        f.write(f"# 주 판정 갈래 N={MAIN_N} · {MAIN_M} · DB 스냅샷 {END} · 시드 {SEED} · "
                f"post6({POST6_LOG_NO}) 신규 exact «만»\n")
        for ln in NOTATION_POST6:
            f.write("# " + ln.replace("\n", " ") + "\n")
        f.write("#\n")
        f.write("post\titem\tname\tcode\treg\tN\tmeasure\tsector\tpeers\tG\tsec_rank\traw\tpct\treason\n")
        for n in NS:
            for mk in MEAS:
                for it, b in zip(items, BR[(n, mk)]):
                    f.write(f"{it['post']}\t{it['item_no']}\t{it['name']}\t{it['code'] or ''}\t"
                            f"{it['reg']}\t{n}\t{mk}\t{b.get('sector', '')}\t"
                            f"{b.get('peers', '')}\t{b.get('G', '')}\t{b.get('rank', '')}\t"
                            f"{('%.8f' % b['raw']) if b['ok'] else ''}\t"
                            f"{('%.6f' % b['pct']) if b['ok'] else ''}\t{b['reason']}\n")

    (BASE / "RESULTS_SECTOR_POST6_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")

    print(f"[시간] 총 {time.time() - t_start:.1f}초 · SEC-X1 {t_x1:.1f}초")
    print("[written] RESULTS_SECTOR_POST6_NUMBERS.md + sector_post6/*.json|tsv")
    print(f"[판정] SEC-P1 = {p1_word} · N1={fmt(n1p, 4)} B1={fmt(b1p, 4)} "
          f"B2={fmt(b2r * 100 if b2r is not None else None)}% · G1={g1_main * 100:.1f}% · "
          f"q_top_max={qmax:.3f} · X1(N1)={x1sum['N1']['lt05'] * 100:.1f}% · "
          f"V1={'갈림' if split else '불갈림'}")
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# 5. post7 판정 모드 (post7 «만» · §0-4 7번) — post6 판을 «승계»한다.
#    🔴 `main_post6()` 도 `db_context()` 도 한 글자 고치지 않는다(동결 모드 0줄 영향).
# ══════════════════════════════════════════════════════════════════════════════
def post7_context(cur, ctx):
    """post7 판정 모드의 원장 문맥.

    🔴 **`db_context()` 를 «고치지 않는다».** 그 함수는 두 동결 모드가 공유하므로 한 줄도
    건드리지 않고, **post7 코드 사전으로 원장을 «다시» 파싱한 결과만** 얹는다.
    🔑 ***공유 헬퍼에 인자를 하나 더 다는 순간, 그 헬퍼를 부르는 동결 경로가 「바뀐 코드」가 된다.***
    """
    from run_ranking import build_codes7      # 🔴 post7 전용 (기존 import 줄을 고치지 않는다)
    rows = ctx["rows"]                        # `load_ledger("post6")` = 전 행 (필터는 아래 글 필터)
    codes, _ = build_codes7()
    # 🔴 두 독립 매핑(`run_ranking.POST7_CODES` ↔ 이 모듈의 `POST7_NEW`)이 «같은지» 대조한다.
    #    다르면 즉시 멈춘다 — 조용한 덮어쓰기 금지(새 매핑 0건).
    for nm, c, _reg in POST7_NEW:
        if codes.get(nm, c) != c:
            raise SystemExit(f"🔴 종목코드 충돌: {nm} {codes[nm]} ↔ {c}")
        codes[nm] = c
    items_all, post_idx = exact_items(rows, codes)
    ap_all = approx_items(rows, codes, post_idx)
    out = dict(ctx)
    out.update(items_all=items_all, ap_all=ap_all, post_idx=post_idx)
    return out


def main_post7(cur, ctx):                                     # noqa: PLR0912, PLR0915
    t_start = time.time()
    ART = ART_POST7
    ART.mkdir(exist_ok=True)

    # 🔴🔴 **post6 과 «다른» 자리 — 창이 상수다.** post6 은 발행일이 거래일이라 `ctx["END"]`
    #    (= `daily_prices` `max(date)`)가 곧 창 종료였지만, post7 은 발행일(**2026-09-12**)이
    #    **토요일 = 휴장**이라 `PREDECISION_2026-09-15_post7.md` **PD-1** 이 창 종료를
    #    **`2026-09-11`(금) 한 값**으로 못 박았다(B-1 · 세 동결 문언 일치).
    #    ⇒ 실행 시 `max(date)` 와 그 날짜 행수는 **기록만** 하고 창으로 쓰지 않는다(PD-1 5번).
    #    ⚠️ 이 축은 애초에 창을 쓰지 않고 **등록일 «당일»만** 쓴다(§7-B #21) — 그래도 표기는 박는다.
    ctx = post7_context(cur, ctx)
    END = DB_UPTO_POST7
    SNAP_MAX = ctx["END"]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (SNAP_MAX,))
    SNAP_ROWS = int(cur.fetchone()[0])
    si_rows, si_uniq, si_nonnull = ctx["si_rows"], ctx["si_uniq"], ctx["si_nonnull"]
    si_upd, si_sha = ctx["si_upd"], ctx["si_sha"]
    info_rows, info_sector, len_all = ctx["info_rows"], ctx["info_sector"], ctx["len_all"]
    nonnum, final_pseudo, SEC = ctx["nonnum"], ctx["final_pseudo"], ctx["SEC"]

    # 🔴🔴 **명시 필터** — 판정 분모는 **post7 신규 `exact` «만»**(`SEC-D5` · §2-5).
    #     🔴 post7 의 `none` 은 **두 부류**다(post6 과 다르다 · PD-4 표):
    #       ① 신규이나 등록일 «문장»이 없는 2건(한전기술 · 한전산업) — 급등일을 등록일로 승격하지 않는다
    #       ② 기존 건 후속 3건(한라캐스트 · 아난티 · 우리기술투자) — PD-2 이중계상 금지
    #     둘 다 `reg_date_precision = none` 이라 `exact_items()` 가 «정의로» 뺀다 — 값을 보고 뺀 것이 아니다.
    P7IDX = ctx["post_idx"].get(POST7_LOG_NO, POST7_IDX)
    items = [it for it in ctx["items_all"] if it["post"] == P7IDX]
    ap_items = [it for it in ctx["ap_all"] if it["post"] == P7IDX]
    train = [it for it in ctx["items_all"] if it["post"] in TRAIN_POSTS]
    # 🔴 이 글의 «분모 안» 재진입만 센다 — 글 전체 재진입 3건 중 2건은 `approx` 라 여기 없다(PD-3).
    PD3_IN = {it["code"]: PD3_FLAG_P7[it["code"]] for it in items if it["code"] in PD3_FLAG_P7}
    none_rows = [r for r in ctx["rows"]
                 if r["post_log_no"] == POST7_LOG_NO and r["reg_date_precision"] == "none"]
    bad_log = sorted({it["log_no"] for it in items} - {POST7_LOG_NO})
    if bad_log:
        raise SystemExit(f"🔴 post7 필터가 다른 글을 잡았다: {bad_log}")

    dates = sorted({it["reg"] for it in items})
    all_dates = sorted({it["reg"] for it in items + ap_items})
    train_dates = sorted({it["reg"] for it in train})
    DAY = {d: load_day(cur, d, SEC, final_pseudo)
           for d in sorted(set(all_dates) | set(train_dates))}

    # ── 갈래별 측정 · 귀무 (한 함수로 — 갈래·부분표본이 «같은 정의»를 쓰게) ────
    def full_eval(its, n, mk):
        bs = [measure_case(it, n, mk, DAY, SEC) for it in its]
        vals = [b["pct"] for b in bs if b["ok"]]
        posts = [it["post"] for it, b in zip(its, bs) if b["ok"]]
        main_v, pooled = aggregate(vals, posts)
        out = dict(bs=bs, vals=vals, posts=posts, main=main_v, pooled=pooled,
                   N1=None, B1=None, B2=dict(wins=0, n=0, rate=None))
        if not vals:
            return out
        for kind, sname in (("N1", "sec_n1"), ("B1", "sec_b1")):
            pl, _ = pools_for(kind, n, mk, bs, its, DAY)
            if pl and not any(p.size == 0 for p in pl):
                gm, gp = agg_matrix(null_matrix(stream(sname), pl, posts, NREP), posts)
                out[kind] = dict(p_main=float(np.mean(gm >= main_v)),
                                 p_pool=float(np.mean(gp >= pooled)),
                                 ceil_main=float(np.mean(gm >= 100.0 - 1e-9)),
                                 null_med=float(np.median(gm)))
        pb, _ = pools_for("B1", n, mk, bs, its, DAY)
        wins, nb2 = 0, 0
        # 🔴 **`SEC-B2` 의 비교점은 «그날 `n_up` 풀의 중앙값»이지 «50»이 아니다**(§3 5행).
        #    백분위 축이라 50 이 비교점처럼 보이지만, 문턱 50% 는 «승률»에 걸린 것이다.
        #    ⇒ 건별 (저자 값, 그날 풀 중앙값)을 인쇄용으로 남긴다.
        b2_detail = []
        _mnames = [it["name"] for it, b in zip(its, bs) if b["ok"]]
        for idx, (pool_v, v) in enumerate(zip(pb, vals)):
            if pool_v.size == 0:
                continue
            nb2 += 1
            pm = med(list(pool_v))
            if v > pm:     # 🔴 동률은 «못 넘은 것»(§4-2 · 보수적)
                wins += 1
            b2_detail.append(dict(name=(_mnames[idx] if idx < len(_mnames) else "?"),
                                  value=float(v), pool_med=float(pm),
                                  pool_n=int(pool_v.size), win=bool(v > pm)))
        out["B2"] = dict(wins=wins, n=nb2, rate=(wins / nb2 if nb2 else None),
                         detail=b2_detail)
        return out

    EV = {(n, mk): full_eval(items, n, mk) for n in NS for mk in MEAS}
    BR = {(n, mk): EV[(n, mk)]["bs"] for n in NS for mk in MEAS}
    MAIN = EV[(MAIN_N, MAIN_M)]

    # ══════════════════════════════════════════════════════════════════════
    # §0
    # ══════════════════════════════════════════════════════════════════════
    say("# `SEC-` 섹터 동반 상승 — **post7 판정** 수치 원본 (post7 신규 `exact` «만»)")
    say()
    for ln in NOTATION_POST7:
        say("> " + ln)
    say()
    say("🔴 **이 파일의 판정 분모는 post7 신규 `exact` 건 «뿐»이다** — 훈련(post1~5) 값은 "
        "`SEC-O1`(§4-5) 대로 **§8 에 «나란히»만** 두고 판정 분모에 넣지 않는다.")
    say()
    say("## §0. 실행 문맥")
    say()
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 사전등록 | `PREREG_SECTOR_COMOVE.md` (동결 · `SEC-D1`~`D8` 확정 2026-09-02) |")
    say("| 동결 | `FREEZE_SECTOR_2026-09-03.md` (§0-4 **5번**) · 배선 점검 `RESULTS_SECTOR_DRYRUN.md` |")
    say("| 단계 | `PREREG_SECTOR_COMOVE.md` §0-4 **7번(계산)** — 🔒 **이 값이 판정이다** |")
    say(f"| 대상 글 | `logNo` **{POST7_LOG_NO}** · 발행 **2026-09-12(토 · 휴장)** · "
        "🔴 **프로그램 버전 표기 «없음»**(이 계열 최초 · PD-8 ⇒ 공변량 결측 · 추정 금지) |")
    say("| 실행 브랜치 | `intake/tasso-post7` (🔴 해시는 stdout 전용 — 본문에 박으면 `--rerun` 이 구조적으로 깨진다) |")
    say(f"| 🔴 **창 종료** | **`{END}`** = 발행일(**2026-09-12 토**) **휴장** ⇒ 마지막 거래일 · "
        "**B-1**(전 축 · `WRC-` 포함 · `PREDECISION_2026-09-15_post7.md` PD-1) |")
    say(f"| 🔴 실행 시 `max(date)` | **`{SNAP_MAX}`** · 그 날짜 행수 **{SNAP_ROWS:,}** — "
        "**기록만 한다**(창으로 «쓰지» 않는다 · PD-1 5번 표기 의무) |")
    say("| 창 사용 여부 | ⚠️ 🔴 **이 축은 창을 쓰지 않는다** — `close`·`prev_close`·`high` 를 "
        "**등록일 «당일»만** 쓴다(§7-B #21) ⇒ 「직전 / 포함」 구분이 걸리는 자리가 «없다». "
        "🔑 그래서 **`ANC-N4` ① 축이 이번 회차에 항등**(발행일 휴장 ⇒ 두 정의가 같은 봉)이라는 "
        "사실도 이 축의 값을 바꾸지 않는다 — 그래도 표기는 박는다. |")
    say(f"| `stock_industry` 스냅샷 (§7-B #22) | **{si_rows:,}행** · 고유 `stock_code` {si_uniq:,} · "
        f"`induty_code` non-NULL {si_nonnull:,} · `max(updated_at)` **{si_upd}** |")
    say(f"| 〃 sha256(전체 `stock_code`↔`induty_code`) | `{si_sha[:32]}…` |")
    say(f"| 〃 동결(2026-09-03) 대비 | "
        f"{'✅ **행 수·`max(updated_at)` 불변**' if (si_rows == 2556 and si_upd.startswith('2026-08-07')) else '🔴 **움직였다**'}"
        " — 🔴 이 표는 시간에 따라 «자란다»(§8-5) |")
    say("| 주 판정 갈래 | 🔒 **`N = 3` · `SEC-M1`** (`SEC-D1`·`D2` · 사장님 확정 2026-09-02) |")
    say(f"| 시드 · 반복 | `{SEED}` · **{NREP:,}회** — ⚠️ `run_selection.py:22` 는 `NREP = 2000` 이다"
        "(§2-3 고지 · 이 축은 «더 큰 쪽»을 쓴다) |")
    say(f"| 시드 스트림 분리 | `SeedSequence({SEED}).spawn()` → `{'`·`'.join(_STREAM_NAMES)}` "
        "(§2-3 «필수» 승계) |")
    say(f"| `SEC-X1` 독립 실현 | **{X1_REP}** (`RESULTS_RANKING_TRAIN.md` §5 «승계») |")
    say(f"| 의사티커 제외 | **{len(final_pseudo)}종** {'·'.join('`%s`' % p for p in final_pseudo)} — "
        f"`run_selection.py:23` `PSEUDO`({len(PSEUDO)}) ∪ DB 실측({len(nonnum)}종) ⇒ "
        f"**{'같다' if set(final_pseudo) == set(PSEUDO) else '🔴 다르다'}**(§5 4번 · §7-B #19) |")
    say("| 유니버스 | `PREREG_RANKING.md` §2-1 승계(`market_cap > 0 ∧ close > 0` · 의사티커 제외) "
        "**∩ 섹터코드 존재**(`SEC-D3`) |")
    say(f"| 🔒 **판정 분모** | post7 신규 `exact` **{len(items)}건** · 등록일 **{len(dates)}일** "
        f"({dates[0]} ~ {dates[-1]}) |")
    say(f"| `approx` (의무 민감도) | **{len(ap_items)}건**"
        + ("" if ap_items else " — 🟢 **0건이므로 「`approx` 포함」 갈래가 「`exact` 만」과 «구조적으로 같은 집합»이다**(모호 아님)")
        + (" — 🟢🟢 **이 축의 등록일 정밀도 갈래가 이 글에서 «처음» 살아난다**"
           "(지투파워 「9월 초」 · 한국화장품제조 「8월 말」 · PD-4 · `RNK-D5` 문형 승계: "
           "**판정 분모는 `exact` 만** · `approx` 는 의무 민감도)" if ap_items else "")
        + " |")
    say(f"| `none` | **{len(none_rows)}건** " + " · ".join(r["stock_name"] for r in none_rows)
        + " — 🔴 **등록일 축 분모 «밖»**(`exact_items()` 가 정의로 뺀다). "
        + f"🔴 **두 부류가 섞여 있다**(post6 과 다르다 · PD-4 표): "
        + f"① **신규이나 등록일 문장 부재** {' · '.join(POST7_NONE_NEW)} — "
          "「8월 26일」은 **급등 사유일**이고 등록 문장과 «다른 줄»이라 **승격하지 않는다** / "
        + f"② **기존 건 후속** {' · '.join(POST7_FOLLOWUP)} — 그 등록 사건은 **post6 신규 분모에서 "
          "이미 계상됐다**(이중계상 금지 · PD-2 2번) |")
    say("| `after` | **0건**(post7) · 계열 누적 1건 제외 유지(`SEC-D5`) |")
    say(f"| 최소 표본 게이트 | `exact` **{len(items)} ≥ {MIN_EXACT}** ⇒ "
        f"{'🟢 **판정한다**' if len(items) >= MIN_EXACT else '⛔ **미룬다**'} "
        "(`PREREG_SELECTION.md` §7 «차용») |")
    say()
    say("🔴 **`SEC-O1` 자유도 신고** — 잣대 선택(`SEC-D1` `N` 3후보 × `SEC-D2` 측정자 3후보 = **9 조합**)의 "
        "자유도가 이 축의 거의 전부이며, 그 결정은 **2026-09-02**(§0-6)에 동결됐고 배선 점검(09-02)·"
        "동결 커밋(09-03)이 **`fetch_post.py`(09-04 18:50 KST) «전»**이다(PD-0). "
        "**9 조합을 다 인쇄하되 판정 갈래는 «동결된 하나»뿐이다.** "
        "🔴 **이 실행은 값을 보고 잣대를 하나도 바꾸지 않았다.**")
    say()
    say("| 열 | 뜻 |")
    say("|---|---|")
    say("| 훈련(post1~5) | 🔬 **탐색적 표기** — 판정 분모에 **넣지 않는다**(§8 에만) |")
    say("| 🔒 검증(post7) | **판정** — 이 파일의 §1~§7 전부 |")

    # ══════════════════════════════════════════════════════════════════════
    # §1 분모 · SEC-G1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §1. 분모 · 커버리지 `SEC-G1` (§2-5 · §4-3)")
    say()
    say(f"### 1-1. 건별 — post7 신규 `exact` {len(items)}건")
    say()
    say("| # | 종목 | `stock_code` | 등록일 | `induty_code` | 길이 | `N=3` 칸 | 유니버스 | 섹터표 | 재진입 | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    for it in items:
        c = it["code"]
        D = DAY[it["reg"]]
        ind = SEC.get(c) if c else None
        in_uni = bool(c) and c in set(D["uni"])
        reason = ("①" if not c else ("②" if not in_uni else ("③" if ind is None else "")))
        re_f = PD3_FLAG_P7.get(c)
        re_s = "—" if re_f is None else f"🔂 `P6-PRIOR_CYCLE`={re_f}"
        say(f"| {it['item_no']} | {it['name']} | `{c or '—'}` | {it['reg']} | `{ind or '—'}` | "
            f"{len(ind) if ind else '—'} | `{ind[:3] if ind else '—'}` | {'✅' if in_uni else '🔴'} | "
            f"{'✅' if ind else '🔴 없음'} | {re_s} | {reason or '—'} |")
    say()
    n_nosec = sum(1 for it in items if not it["code"] or SEC.get(it["code"]) is None)
    nosec_names = [it["name"] for it in items if not it["code"] or SEC.get(it["code"]) is None]
    say(f"- **섹터코드 없는 건 = {n_nosec}건 / {len(items)}**"
        + (f" ({' · '.join(nosec_names)})" if nosec_names else "")
        + " — `PREDECISION_2026-09-15_post7.md` **PD-11** 이 계산 «전»에 적은 «`exact` 6 중 "
        f"섹터코드 5/6 · **해치텍(`0155E0`)만 `stock_industry` 미수록**»과 "
        f"{'🟢 일치한다' if n_nosec == SEC_EXPECT_NOSEC else '🔴 **어긋난다**'}.")
    say("- 🔴 **`SEC-G1` 은 *「`N`·«측정자별»」* 이다** — 위 수는 **섹터코드 «유무»만** 센 것이고, "
        "아래 §1-2 표가 `SEC-M1`/`M2`/`M3` × `N` **9 조합 각각으로 다시 센다**(PD-11 3번: "
        "***커버리지는 축별로 «다른 수»다***).")
    say("- 🔂 **재진입** — 글 전체 **3건**(지투파워 **3번째 사이클**(계열 최초) · 한국화장품제조 · "
        "빛과전자 · PD-3) 중 **판정 분모(`exact`) 안은 %d건**: " % len(PD3_IN)
        + (" · ".join(f"{it['name']}(`{it['code']}`) 직전 사이클 "
                      f"{REENTRY_P7.get(it['code']) or '**미명시**'} · `P6-PRIOR_CYCLE_IN_WINDOW` = "
                      f"**{PD3_FLAG_P7[it['code']]}**"
                      for it in items if it["code"] in PD3_FLAG_P7) or "—")
        + f" ⇒ **판정 분모 안 플래그 합 = {sum(PD3_IN.values())}/{len(items)}**. "
        "🔴 **글 전체 플래그 2건**(지투파워 · 한국화장품제조)은 **둘 다 `approx` 갈래**다 — "
        "***두 수를 한 수로 합치지 않는다.*** **분모 포함 + 제외 민감도 의무**(§7-2). "
        "⚠️ 재진입 3건 중 2건이 `approx` 라 **재진입 제외 민감도와 `approx` 제외 민감도가 겹친다** — "
        "두 민감도를 «따로» 인쇄한다(PD-3 말미).")
    say()
    say("### 1-2. `SEC-G1` — 측정 불가 / `exact` 분모 · **≥ 1/3 ⇒ ⛔ 판정 불가** (§4-3 · `Y3` «차용»)")
    say()
    say("⚠️ **`1/3` 은 «feasible set 공집합 비율»을 재던 문턱이며 커버리지에 대해 검증된 적이 없다** — "
        "`PREREG_POST6.md` §1-6 #6 · `PREREG_RANKING.md` §4-4 의 같은 차용 고지를 승계한다.")
    say()
    say("| 사유 | 설명 | 갈래 의존 |")
    say("|---|---|---|")
    say("| ① | DB 종목코드 부재(레메디형) | 전 갈래 공통 |")
    say("| ② | 유니버스 밖(`market_cap>0 ∧ close>0` 미충족) | 전 갈래 공통 |")
    say("| ③ | 섹터코드 부재(매드업·삼양바이오팜형 · **이번 글 = 해치텍**) | 전 갈래 공통 |")
    say("| ④ | 동료 0 (자기 제외 후 `|P| = 0`) | 🔴 `N` 마다 다르다 |")
    say("| ⑤ | 층에서 미정(`length(induty_code) < N`) | 🔴 `N = 5` 갈래 전용 |")
    say()
    say("| `N` | 측정자 | 측정 가능 | 측정 불가 | 비율 | `SEC-G1`(≥1/3) | 사유별 **건수 · 종목명** |")
    say("|---|---|---|---|---|---|---|")
    G1 = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            bad = [(it, b) for it, b in zip(items, bs) if not b["ok"]]
            rate = len(bad) / len(items)
            G1[(n, mk)] = rate
            by = {}
            for it, b in bad:
                by.setdefault(b["reason"], []).append(it["name"])
            cell = " · ".join(f"{k}:{len(v)}({', '.join(v)})" for k, v in sorted(by.items())) or "—"
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {len(items) - len(bad)}/{len(items)} | {len(bad)} | "
                f"**{rate * 100:.1f}%** | {'🔴 **발동 ⇒ ⛔**' if rate >= G1_THR else '미발동'} | {cell} |")
    say()
    g1_main = G1[(MAIN_N, MAIN_M)]
    say(f"- 🔒 **판정에 쓰는 비율 = 주 갈래(`N = 3` · `SEC-M1`) = {g1_main * 100:.1f}%** ⇒ "
        f"{'🔴 **⛔ `SEC-G1` 발동 — 판정 불가**' if g1_main >= G1_THR else '**미발동 ⇒ 게이트를 연다**'} "
        "(나머지 8 조합은 의무 인쇄 · §4-3 1번).")
    say(f"- 🔬 **훈련 표본 예보는 16.7%** 였다(`FREEZE_SECTOR_2026-09-03.md` §4-2) — 이번 실측 "
        f"**{g1_main * 100:.1f}%**. ⚠️ **예보와 판정은 다른 표본이다**(훈련 {len(train)}건 ↔ 판정 {len(items)}건).")
    say("- 🔴🔴 **편향 방향(그대로 유지) — 이번 글에는 그 편향의 «실물»이 분모 «안»에 있다**: "
        "사유 ③ 은 **신규 상장주에 집중**되고 저자는 신규주를 자주 고른다(§1-5) ⇒ "
        "***측정 불가가 무작위가 아니다.*** **해치텍(`0155E0`)은 2026-08-25 첫 봉의 신규 상장주**이고 "
        "`stock_industry` 스냅샷(`max(updated_at)` 2026-08-07)에 **아직 안 들어왔다** — "
        "🔑 ***이건 「그 종목에 섹터가 없다」가 아니라 「우리 표가 그 종목을 아직 모른다」다.*** "
        "post6 에서는 같은 부류(삼양바이오팜)가 **후속이라 분모 밖**이었는데, 이번엔 **분모 안**이다.")
    say(f"- 🔴 **`N = 5` 갈래**: 측정 불가 **{G1[(5, MAIN_M)] * 100:.1f}%** "
        f"{'⇒ 🔴 **발동**' if G1[(5, MAIN_M)] >= G1_THR else '⇒ 미발동'} — 사전등록 §2-1 이 값 보기 «전»에 "
        "*「4개 글 중 3개에서 판정 불가 · 훈련 전체 61.1%」*로 적어 둔 그 갈래이며, "
        "**구조적 미정 비율을 «항상» 함께 박는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §2 drop_rate
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §2. `drop_rate` **표기 가드** (§5 6-1 · `PREREG_POST6.md` §5-2 «원 용도»)")
    say()
    say("🔴 **`1%` 는 «표시» 문턱이지 «판정» 게이트가 아니다.** "
        "🔑 ***0 이라서 안 재는 게 아니라, 0 임을 매회 «보여서» 이 조항이 살아 있음을 증명한다.***")
    say()
    # 🔴 「한 날에 여러 건」 예시는 **이번 분모에서 실측**한다(직전 글의 등록일을 옮겨 적지 않는다).
    _dupd = sorted(d for d in dates if sum(1 for it in items if it["reg"] == d) >= 2)
    say("⚠️ 🔴 **「5열」이라 적지 않는다 — 이 표는 4열이다.** `PREREG_POST6.md` §5-2 의 5번째 열은 "
        "`prev_bar_date` 인데, **이 축의 §2 표는 «등록일» 행**이고 `prev_close` 는 **종목별 `LAG`** 라 "
        "`prev_bar_date` 가 **행마다 유일하지 않다**"
        + (f"(이번 분모 등록일 {' · '.join('`%s`' % d for d in dates)} 중 한 날에 2건 이상인 날 = "
           + (" · ".join("`%s`(%d건)" % (d, sum(1 for it in items if it["reg"] == d))
                              for d in _dupd) if _dupd else "**없음** — 그래도 `prev_bar_date` 는 "
              "«종목별» 값이라 등록일 행과 1:1 이 아니다") + ")")
        + " ⇒ **4열만 인쇄한다.** 🔑 ***열을 못 채우면 「채운 척」하지 말고 "
          "「왜 못 채우는지」를 적는다.***")
    say()
    say("| 등록일 | 그날 `market_cap>0` | 검정 유니버스 | 탈락 | 탈락률 | 🔴 섹터 조인 «후» 탈락 | "
        "섹터 조인 | 커버리지 | `n_up` ∩ 조인 | S-1 동결함수 일치 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for d in dates:
        D = DAY[d]
        drop = D["raw_n"] - D["frozen_n"]
        rate = drop / D["raw_n"]
        cov = len(D["joined"]) / len(D["uni"]) * 100
        say(f"| {d} | {D['raw_n']:,} | {D['frozen_n']:,} | "
            f"{'🔴 **' + format(drop, ',') + '**' if rate >= DROP_MARK else drop} | "
            f"{rate * 100:.2f}%{' 🔴' if rate >= DROP_MARK else ''} | **{D['prev_miss_join']}** | "
            f"{len(D['joined']):,} | {cov:.2f}% | {len(D['nup'])} | "
            f"{'✅' if D['s1_ok'] else '🔴 차 %d' % D['s1_diff']} |")
    say()
    marked = [d for d in dates if (DAY[d]["raw_n"] - DAY[d]["frozen_n"]) / DAY[d]["raw_n"] >= DROP_MARK]
    n_s1 = sum(1 for d in dates if DAY[d]["s1_ok"])
    n_pm = sum(1 for d in dates if DAY[d]["prev_miss_join"] == 0)
    say(f"- 🔴 **표시가 붙은 날 {len(marked)}일**"
        + (" (" + " · ".join("`%s`" % x for x in marked) + ")" if marked else "")
        + " — 그날의 `n_up` 을 **다른 날과 직접 비교하지 말 것**(원 문언 그대로).")
    say(f"- {'🟢' if n_pm == len(dates) else '🔴'} **섹터 조인 «후» 탈락은 {n_pm}/{len(dates)} 등록일 0** "
        "⇒ `SEC-D7`(종가 대비 수익률)의 정의역에 구멍이 없다(§1-4 재현).")
    say(f"- 🟢 **S-1 배선 확인**: `prev_close` 복제본이 `run_regday_post5.load_universe_day`"
        f"(동결 함수 · **import 해서 호출**)와 **집합으로 같다** — **{n_s1}/{len(dates)} 등록일**"
        f"{' ✅ 전부(차집합 크기 0)' if n_s1 == len(dates) else ' 🔴 어긋난 날이 있다'}.")

    # ══════════════════════════════════════════════════════════════════════
    # §3 건별 측정값
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §3. 건별 측정값 — 🔒 주 판정 갈래 (`N = 3` · `SEC-M1`)")
    say()
    say("🔴 **§2-4 대로 «분모»를 매 건 인쇄한다** — `|P|`(동료 수) · `G`(그날 섹터 수) · "
        "`sec_rank`(자기 섹터 제외 · 동률 전부 위 = 보수적) · **원값**(`med`).")
    say("🔴 **`sec_rank` 에 문턱을 «걸지 않는다»**(§2-2) — `RNK-N2` 의 **30** 은 ≈2,760종목을 재던 값이다.")
    say()
    say("| # | 종목 | 등록일 | 섹터(`N=3`) | `|P|` | `G` | `sec_rank` | 원값 `med` | "
        "**`SEC-M1` 백분위** | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for it, b in zip(items, BR[(MAIN_N, MAIN_M)]):
        if b["ok"]:
            say(f"| {it['item_no']} | {it['name']} | {it['reg']} | `{b['sector']}` | {b['peers']} | "
                f"{b['G']} | {b['rank']} | {b['raw'] * 100:+.3f}% | **{b['pct']:.1f}** | — |")
        else:
            say(f"| {it['item_no']} | {it['name']} | {it['reg']} | — | {b.get('peers', '—')} | — | — | "
                f"— | ⛔ 측정 불가 | **{b['reason']}** |")
    say()
    mv = MAIN["vals"]
    if mv:
        pk = [b["peers"] for b in BR[(MAIN_N, MAIN_M)] if b["ok"]]
        say(f"- 백분위 범위 **{min(mv):.1f} ~ {max(mv):.1f}** · 동료 수 `|P|` **{min(pk)} ~ {max(pk)}** "
            f"· 동료 0 인 건 **{sum(1 for x in pk if x == 0)}건**(§7-B #26).")
        say(f"- 글 단위 중앙 = **{fmt(MAIN['main'])}** · 건 pooled 중앙 = **{fmt(MAIN['pooled'])}** "
            f"({med_note(len(mv))}).")
        say("- 🔴🔴 **이 글 하나로만 판정하므로 「글 단위 중앙」과 「건 pooled 중앙」이 «구조적으로 같은 양»이다** "
            "— 글이 하나면 「글별 중앙의 중앙」 = 「그 글의 중앙」이다. ⇒ §7 4축의 ③(집계)은 이 글에서 "
            "**«갈릴 수 없다»**(모호가 아니라 정의다). 다음 글부터 갈릴 수 있다.")
    say()
    say("### 3-1. 9 조합 전부 (`SEC-O1` §4-5 — 판정은 «동결된 하나»로만)")
    say()
    say("| `N` | 측정자 | 측정 가능 | 건별 백분위 | **전체(글 단위 중앙)** | 건 pooled 중앙 |")
    say("|---|---|---|---|---|---|")
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {len(E['vals'])}/{len(items)} | "
                f"{', '.join(f'{v:.1f}' for v in E['vals']) or '—'} | "
                f"**{fmt(E['main'])}** | {fmt(E['pooled'])} |")
    say()
    say("🔒 **판정 갈래 = `N = 3` · `SEC-M1`**(🔒 표시). 나머지 8 조합은 `SEC-V1` 의 «입력»이며 "
        "**판정에 쓰지 않는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §4 귀무·대조
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §4. 귀무 `SEC-N1` · 대칭 대조 `SEC-B1`·`SEC-B2`")
    say()
    say("### 4-0. 추출 풀 한정 손실 (§2-3 — 🔴 «유리한 방향의 처리는 반드시 «크기»를 같이 적는다»)")
    say()
    say("| 갈래 | 풀 | 후보 합계 | 측정 가능 합계 | 한정으로 빠진 수 | 비율 |")
    say("|---|---|---|---|---|---|")
    for n in NS:
        for kind, nm in (("N1", "`SEC-N1` 전 종목"), ("B1", "`SEC-B1` `n_up`")):
            _, loss = pools_for(kind, n, MAIN_M, BR[(n, MAIN_M)], items, DAY)
            tot = sum(a for a, _ in loss)
            keep_n = sum(b for _, b in loss)
            say(f"| `N={n}` | {nm} | {tot:,} | {keep_n:,} | **{tot - keep_n:,}** | "
                + (f"{(tot - keep_n) / tot * 100:.1f}%" if tot else "—") + " |")
    say()
    say("🔴 이 한정은 **저자 쪽에 «유리»한 방향**이다(저자 종목은 전부 동료 ≥ 1). 그래서 크기를 적는다.")
    say()
    say("### 4-1. `SEC-N1` · `SEC-B1` · `SEC-B2` — 9 조합")
    say()
    say(f"귀무 = 각 건의 등록일에 그 풀에서 **무작위 종목 1개** → 같은 측정자·같은 집계 · "
        f"**{NREP:,}회** · 시드 `{SEED}`(스트림 분리) · `p` = `mean(귀무 ≥ 관측)`(등호 포함 · S-5) · "
        "**두 풀 «모두»에서 저자 종목 자신을 뺀다**(M7).")
    say()
    say("🔑 **갈래 사이에는 «공통난수(CRN)»를 쓴다** — 같은 스트림 이름(`sec_n1`·`sec_b1`)을 다시 부르면 "
        "같은 난수열이 나오므로 9 조합이 «같은 추첨»을 공유한다. "
        "🔴 목적이 «다른» 계열(`SEC-X1` 순열·그 안의 귀무)은 §0 대로 **다른 스트림**이다.")
    say()
    say("| `N` | 측정자 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` 승률 | "
        "관측(pooled) | `SEC-N1` `p`(pooled) | `SEC-B1` `p`(pooled) |")
    say("|---|---|---|---|---|---|---|---|---|")
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            if not E["vals"]:
                say(f"| {n}{tag} | `{mk}`{tag} | ⛔ 측정 가능 0건 | — | — | — | — | — | — |")
                continue
            b2 = E["B2"]
            say(f"| {n}{tag} | `{mk}`{tag} | **{fmt(E['main'])}** | "
                f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
                f"**{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}%** "
                f"({b2['wins']}/{b2['n']}) | {fmt(E['pooled'])} | "
                f"{fmt(E['N1']['p_pool'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_pool'], 4) if E['B1'] else '⛔'} |")
    say()
    say("🔴 **매 산출물 의무 문언**(§4-1) — ***`SEC-N1` 은 «`SEC-B1` 없이는» 증거가 아니다.*** "
        "저자 종목은 정의상 급등주이고, 급등주가 섹터 동반성이 높다면 `SEC-N1` 은 그 사실만 되비춘다"
        "(= `REG-M4` 재진술). **정보는 `SEC-B1`·`SEC-B2` 에 있다.**")
    say("🔴 **`SEC-B2` 동률 처리** — 저자 값이 그날 풀 중앙값과 «같으면» **못 넘은 것**으로 센다(보수적).")
    say("")
    say("#### 🔴🔴 `SEC-B2` 의 «비교점» — **50 이 아니라 «그날 `n_up` 풀의 중앙값»이다**")
    say("")
    say("⚠️ 저자 값이 **백분위**라 「50 을 넘었나」로 읽기 쉽지만, `SEC-B2` 가 재는 것은 "
        "***「저자 값 > **그날** 급등주 풀의 중앙값」***이다(§3 5행 정의 축자). "
        "🔑 ***두 비교점은 같은 날에도 크게 다르다*** — 아래 표가 그 차이다.")
    say("")
    say("| 종목 | 등록일 | 저자 값(백분위) | **그날 `n_up` 풀 중앙값** | 풀 크기 | 넘었나 | "
        "(참고) 50 을 넘나 |")
    say("|---|---|---|---|---|---|---|")
    for _d, _it in zip(MAIN["B2"].get("detail", []),
                       [x for x, b in zip(items, MAIN["bs"]) if b["ok"]]):
        say(f"| {_d['name']} | {_it['reg']} | **{_d['value']:.1f}** | "
            f"**{_d['pool_med']:.1f}** | {_d['pool_n']} | "
            + ("🟢 예" if _d["win"] else "🔴 아니오") + " | "
            + ("예" if _d["value"] > 50.0 else "아니오") + " |")
    say("")
    say("🔴 **그러므로 «50 을 넘었다»를 `SEC-B2` 의 근거로 적지 않는다** — "
        "두 잣대가 같은 답을 내는 날도 있고 아닌 날도 있다. "
        "🔒 판정에 쓰는 것은 **그날 풀 중앙값** 쪽 하나뿐이다.")
    say()
    say("### 4-2. 🔴🔴 `SEC-B1` **발화 가능성** — `q_top` 실측 (§4-2 (가) · §7-B #20)")
    say()
    say("🔑 ***「재추출이 성립한다」가 「가드가 발화한다」를 뜻하지 않는다.*** "
        "관측 통계량의 **천장은 100** 이고, 귀무가 그 천장에 **5% 이상**의 질량을 두면 "
        "***어떤 관측으로도 `p < 0.05` 가 나오지 않는다.***")
    say()
    say("🔴 **풀 정의가 둘이다** — ①사전등록 §4-2 (가) 표의 풀 = **`n_up` ∩ 조인** · "
        "②이 표가 쓰는 풀 = 그 위에 **측정 가능(동료 ≥ 1)** 한정. "
        "**①로 구조적 상한(충분조건)을, ②로 실제 발화를 잰다.**")
    say()
    say("⚠️ 🔴 **②열과 `q_top` 은 «날 단위»다 — 건별 «자기 제외»(M7) «전»의 값이다.** "
        "자기 제외가 실제로 걸리는 곳은 **`SEC-B1` 의 추첨 풀**(`pools_for`)이고, 위 §4-1 의 `p` 는 "
        "그 «자기 제외된» 풀로 계산됐다. ⇒ ***이 표의 `q_top` 과 §4-1 의 `p` 는 «분모가 한 건씩 다르다».*** "
        "아래에 **자기 제외까지 넣어 다시 잰 `q_top`** 을 병기해 두 값이 판정을 가르는지 보인다.")
    say()
    say("| 등록일 | ① 풀(`n_up`∩조인) | 고유 섹터 | 최대 섹터 | **최대 점유**(수익률 미사용 충분조건) | "
        "`< 0.135` ? | ② 측정 가능 풀(날 단위) | 🔒 **`q_top`**(1위 섹터 점유 · 문언 정의 · 날 단위) | "
        "(대조) 천장 점유 실측 |")
    say("|---|---|---|---|---|---|---|---|---|")
    QT = {}
    for d in dates:
        D = DAY[d]
        st = D["st"][MAIN_N]
        lab = D["lab"][MAIN_N]
        ix1 = np.array([D["code_i"][c] for c in D["nup"]], dtype=np.int64)
        u1, c1 = np.unique(lab[ix1][lab[ix1] >= 0], return_counts=True)
        share = float(c1.max() / ix1.size)
        pool = [c for c in D["nup"] if st["ok"][D["code_i"][c]]]
        idxs = np.array([D["code_i"][c] for c in pool], dtype=np.int64)
        vidx = np.flatnonzero((lab >= 0) & np.isfinite(D["r"]))
        meds = {int(g): float(np.median(D["r"][vidx][lab[vidx] == g]))
                for g in np.unique(lab[vidx])}
        top = max(meds, key=lambda g: meds[g])
        qtop = float(np.sum(lab[idxs] == top) / idxs.size)
        ceil_share = float(np.mean(st["p1"][idxs] >= 100.0 - 1e-9))
        QT[d] = dict(pool_doc=int(ix1.size), sectors_doc=int(u1.size), maxsec_doc=int(c1.max()),
                     max_share=share, pool_eff=int(idxs.size), qtop=qtop, ceil_share=ceil_share,
                     top=int(top))
        say(f"| {d} | {ix1.size} | {u1.size} | {c1.max()} | **{share:.3f}** | "
            f"{'🟢 예' if share < QTOP_THR else '🔴 아니오'} | {idxs.size} | "
            f"**{qtop:.3f}** | {ceil_share:.3f} |")
    say()
    n_suff = sum(1 for d in dates if QT[d]["max_share"] >= QTOP_THR)
    qmax = max(QT[d]["qtop"] for d in dates)
    qmax_d = max(dates, key=lambda d: QT[d]["qtop"])
    say(f"- 구조적 **충분조건**(최대 단일섹터 점유 `< 0.135`)이 **{len(dates) - n_suff}/{len(dates)} 등록일**에서 "
        f"성립하고 **{n_suff}일**에서 실패한다. 🔴 **「충분조건 실패」는 「`q_top ≥ 0.135`」의 «증명»이 아니다**"
        "(§7-A #8-1 · `FREEZE_SECTOR_2026-09-03.md` §3 ②: ***상한으로 「불가능」을 선언하지 마라***).")
    say(f"- 🔒 **실측 `q_top` 최대 = {qmax:.3f}**(`{qmax_d}`) · "
        + ("🟢 **전 등록일 `< 0.135`**" if qmax < QTOP_THR else "🔴 **`≥ 0.135` 인 날이 있다**") + ".")
    say()
    # 🔴 자기 제외(M7)까지 넣은 `q_top` — `SEC-B1` 이 «실제로» 뽑는 풀과 같은 정의로 다시 잰다.
    qself = []
    for it, b in zip(items, BR[(MAIN_N, MAIN_M)]):
        if not b["ok"]:
            continue
        D = DAY[it["reg"]]
        st = D["st"][MAIN_N]
        lab = D["lab"][MAIN_N]
        pc = [c for c in D["nup"] if st["ok"][D["code_i"][c]] and c != it["code"]]
        if not pc:
            continue
        ix = np.array([D["code_i"][c] for c in pc], dtype=np.int64)
        qself.append((float(np.sum(lab[ix] == QT[it["reg"]]["top"]) / ix.size), it["name"]))
    qmax_self = max(q for q, _ in qself) if qself else float("nan")
    qmax_self_nm = max(qself)[1] if qself else "—"

    kmain = len(MAIN["vals"])
    kposts = len(set(MAIN["posts"])) if MAIN["posts"] else 0
    say("🔒 **발화 조건(동결 · §4-2 (가))** = `P(Binom(k, q_top) ≥ ⌈k/2⌉) < 0.05`. "
        "`q_top` 이 등록일마다 다르므로 **판정 분모의 등록일 중 «최대»**(= 가장 불리한 쪽, 보수적)를 쓴다.")
    say()
    say("| `k` | 뜻 | `q_top`(최대) | `P(Binom(k, q_top) ≥ ⌈k/2⌉)` | 판정 |")
    say("|---|---|---|---|---|")
    fire = {}
    for k, lbl in ((MIN_EXACT, "🔒 사전등록 최소 표본(`PREREG_SELECTION.md` §7)"),
                   (kmain, "🔒 **이 판정의 집계 표본 수**(측정 가능 `exact` 건 = 글 단위 중앙의 분모)"),
                   (kposts, "글 수 (⚠️ 글이 하나뿐이라 «집계의 표본 수»가 아니다 — 아래 주석)")):
        pv = binom_ge_half(k, qmax) if k > 0 else float("nan")
        fire[k] = bool(pv < P_THR)
        say(f"| {k} | {lbl} | {qmax:.3f} (`{qmax_d}`) | **{pv:.4f}** | "
            + ("🟢 발화 가능" if pv < P_THR else "🔴 **⛔ 발화 불가**") + " |")
    say()
    say("⚠️ 🔴 **모호 지점(양쪽 인쇄 · 값 보고 규칙 바꾸지 않는다)** — 사전등록 §4-2 (가)의 `k` 는 "
        "*「관측 통계량(중앙값)의 표본 수」*로 쓰였고 배선 점검은 세 값을 나란히 인쇄했다. "
        f"**이 글 하나로만 판정하는 지금, 글 단위 중앙값을 만드는 표본은 «건 수»({kmain})이지 "
        f"«글 수»({kposts})가 아니다.** 🔒 **판정은 «건 수» 행으로 한다.** "
        + ("🟢 **세 `k` 가 전부 같은 방향이라 이 모호는 판정을 가르지 않는다.**"
           if len(set(fire.values())) == 1 else
           "🔴 **세 `k` 가 갈린다 ⇒ 보수적(발화 불가) 쪽을 쓴다.**"))
    b1fire = fire[kmain] if kmain > 0 else False
    if len(set(fire.values())) > 1:
        b1fire = all(fire.values())
    # 🔴 자기 제외(M7) 정의로 다시 잰 `q_top` 을 «병기»한다 — 문턱도 판정 갈래도 바꾸지 않는다.
    fire_self = {k: binom_ge_half(k, qmax_self) < P_THR for k in (MIN_EXACT, kmain, kposts) if k > 0}
    say(f"- 🔴 **자기 제외(M7)까지 넣어 다시 잰 `q_top`(= `SEC-B1` 이 «실제로» 뽑는 풀과 같은 정의)** "
        f"= 건별 최대 **{qmax_self:.4f}**(`{qmax_self_nm}`) ↔ 위 표의 날 단위 최대 **{qmax:.4f}**. "
        f"자기를 빼면 분모가 하나 줄어 **약간 커진다**(보수적 방향). "
        f"🟢 **세 `k`(**{MIN_EXACT}·{kmain}·{kposts}**) 판정이 두 정의에서 «전부 동일»하다 — "
        f"{'전부 발화 가능' if all(fire_self.values()) and all(fire.values()) else '🔴 갈린다 ⇒ 보수적 쪽을 쓴다'}"
        f"**(`P(Binom({kmain}, {qmax_self:.4f}) ≥ {-(-kmain // 2)})` = "
        f"{binom_ge_half(kmain, qmax_self):.2e}). ⇒ ***이 구분은 발화 판정을 가르지 않는다.***")
    ceil_obs = MAIN["B1"]["ceil_main"] if MAIN["B1"] else None
    say(f"- 🟢 **직접 실측(대조)**: `SEC-B1` 귀무 {NREP:,}회에서 **집계 통계량이 천장(100)에 둔 질량 = "
        f"{fmt(ceil_obs, 4)}** — 문언 정의의 이항 산술과 같은 방향인지 여기서 볼 수 있다. "
        "🔴 **판정은 문언 정의(위 표)로 한다**(S-7).")
    say("- ⇒ 🔒 **`SEC-B1` 발화 " + ("가능**" if b1fire else "**불가** ⇒ ⛔**")
        + " — " + ("문턱을 낮춰 열지 않는다."
                   if b1fire else "🔴 **`SEC-P1` 도 열리지 않는다**(AND). 문턱을 낮춰 열지 않는다."))

    # ══════════════════════════════════════════════════════════════════════
    # §5 SEC-P1 / SEC-P2
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §5. 🔒 `SEC-P1` — **3중 AND** 판정 (§3 1행) · `SEC-P2`")
    say()
    say("🔴 **`SEC-P1` = `SEC-N1 < 5%` ∧ `SEC-B1 < 5%` ∧ `SEC-B2 > 50%`.** "
        "🔴 **모든 ✅ 에는 ⛔ 가 있다** — 아래 표는 성분마다 ⛔ 경로를 같이 적는다.")
    say()
    n1p = MAIN["N1"]["p_main"] if MAIN["N1"] else None
    b1p = MAIN["B1"]["p_main"] if MAIN["B1"] else None
    b2r = MAIN["B2"]["rate"]
    c_n1 = (n1p is not None) and (n1p < P_THR)
    c_b1 = (b1p is not None) and (b1p < P_THR)
    c_b2 = (b2r is not None) and (b2r > B2_THR)
    say("| 성분 | 문턱 (출처 파일) | 관측 | 통과 | ⛔ 경로 |")
    say("|---|---|---|---|---|")
    # 🔴 소수 넷째 자리로 반올림하면 `SEC-N1` 과 `SEC-B1` 이 «같아 보인다» —
    #    실제로는 다른 값이다. ⇒ **재추출 «횟수» 정수를 같이 인쇄**해 착시를 막는다.
    _n1_hits = None if n1p is None else int(round(n1p * NREP))
    _b1_hits = None if b1p is None else int(round(b1p * NREP))
    say(f"| `SEC-N1` | `p < 5%` · `PREREG_REGDAY_MEASURE.md` §4-1 | "
        f"**{fmt(n1p, 5)}** (= **{_n1_hits}**/{NREP:,}) | "
        + ("🟢 통과" if c_n1 else "🔴 미달")
        + " | ≥ 5% ⇒ 불성립 · 해석/재추출 갈림 ⇒ `SEC-V1` |")
    say(f"| `SEC-B1` | `p < 5%` · 〃 | **{fmt(b1p, 5)}** (= **{_b1_hits}**/{NREP:,}) | "
        + ("🟢 통과" if c_b1 else "🔴 미달")
        + " | ≥ 5% ⇒ 🔴 **「급등주 일반 성질과 구분 불가」로 강등** · `q_top ≥ 0.135` ⇒ 발화 불가"
        + f"(이번: {'발화 가능' if b1fire else '🔴 발화 불가'}) |")
    say(f"| `SEC-B2` | **> 50%** · `RESULTS_D1_OOS_POST5.md` §9 W7 «차용» | "
        f"**{fmt(b2r * 100 if b2r is not None else None)}%** ({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | "
        + ("🟢 통과" if c_b2 else "🔴 미달")
        + " | ≤ 50% ⇒ **즉시 「구분 불가」**(등호 포함 = 강등) |")
    say()
    say("| 선행 게이트 | 문턱 (출처) | 이번 | 판정 |")
    say("|---|---|---|---|")
    say(f"| `exact` 최소 표본 | ≥ {MIN_EXACT} · `PREREG_SELECTION.md` §7 | **{len(items)}** | "
        + ("🟢 열림" if len(items) >= MIN_EXACT else "⛔ 미룸") + " |")
    say(f"| `SEC-G1` 커버리지 | < 1/3 · `RESULTS_RECONSTRUCT_POST4.md` §6 Y3 | **{g1_main * 100:.1f}%** | "
        + ("🟢 열림" if g1_main < G1_THR else "🔴 ⛔ 판정 불가") + " |")
    say(f"| `SEC-B1` 발화 가능성 | `P(Binom) < 0.05` · §4-2 (가) | "
        f"**{binom_ge_half(kmain, qmax) if kmain else float('nan'):.4f}** | "
        + ("🟢 열림" if b1fire else "🔴 ⛔ 발화 불가") + " |")
    gates_ok = (len(items) >= MIN_EXACT) and (g1_main < G1_THR) and b1fire
    and_ok = bool(gates_ok and c_n1 and c_b1 and c_b2)
    # 🔴 §3 1행의 ⛔ 열이 `SEC-V1` 을 «판정 불가 조건»으로 열거한다
    #    (`PREREG_SECTOR_COMOVE.md:600`). §7 은 §3 «뒤»에 인쇄되므로 갈림 여부만 앞에서 계산한다.
    #    🔒 적용 범위(`:819`) = 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」뿐이므로
    #    주 갈래의 AND 가 «거짓»인 사건에는 관여하지 않는다 ⇒ `and_ok` 일 때만 ⛔ 로 간다.
    V1PRE = v1_axis_verdicts(EV, G1, MAIN, g1_main, NS, MEAS, MAIN_N, MAIN_M,
                             items, ap_items, b2r, full_eval)
    v1_split_pre = bool(V1PRE["split"])
    p1_blocked = bool(and_ok and v1_split_pre)
    p1_ok = bool(and_ok and not v1_split_pre)
    p1_label = "⛔ 판정 불가" if p1_blocked else ("✅ 성립" if p1_ok else "🔴 불성립")
    p1_word = "판정 불가" if p1_blocked else ("성립" if p1_ok else "불성립")
    say()
    say("### 🔒 판정 — `SEC-P1` : **"
        + ("⛔ 판정 불가(`SEC-V1` 발동)" if p1_blocked
           else ("✅ 성립" if p1_ok else "🔴 불성립(지지 아님)")) + "**")
    say()
    if p1_blocked:
        say("🔴 **3중 AND 는 주 갈래(`N = 3` · `SEC-M1` · 글 단위 중앙 · `exact` 만)에서 «통과»했다** — "
            f"`SEC-N1` **{fmt(n1p, 5)}** · `SEC-B1` **{fmt(b1p, 5)}** · "
            f"`SEC-B2` **{fmt(b2r * 100 if b2r is not None else None)}%** "
            f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}). "
            "🔴 **그러나 이것은 «기록»이지 «선언»이 아니다.**")
        say()
        say("🔒 `PREREG_SECTOR_COMOVE.md` §3 1행의 ⛔ 열이 `SEC-V1` 을 **판정 불가 조건**으로 "
            "열거하고(`:600`), §6 가 *「`SEC-V1` — **4축**(§4-6) 중 하나가 갈림 ⇒ "
            "**갈리지 않는 글이 온다**(잣대를 넓혀 열지 않는다)」*라고 못박는다(`:896`). "
            "그리고 §4-6 적용 범위(`:819`)는 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」이고 "
            "이번 갈림은 **바로 그 경우**다 — 주 갈래 AND 는 참인데 다른 잣대에서 판정이 다르다(§7 표). "
            "⇒ ***이번 글에서는 어느 쪽도 선언하지 않는다.***")
        say()
        say("🔴🔴 **「계열 최초 성립」이라고 쓰지 않는다** — 성립을 «선언»한 적이 없다. "
            "쓸 수 있는 문장은 ***「3중 AND 는 통과했으나 `SEC-V1` 때문에 선언 불가 — "
            "갈리지 않는 글이 오면 판정한다」*** 하나뿐이다. "
            "🔒 문턱을 낮추거나 갈래를 새로 만들어 여는 것은 §6 가 금지한다.")
        say()
        say("🔴 **판정 불가의 뜻도 「테마가 아니다」가 «아니다»**"
            "(§0-2 2번 · 거짓 음성이 구조적이다).")
    elif p1_ok:
        say("🔴 **성립의 뜻은 「섹터 동반성이 존재한다」까지다** — *「테마로 고른다」*의 **확증이 아니다**"
            "(§0-2 천장 · 에코프로 4종목이 KSIC 에서 «세 칸»으로 흩어진다). "
            "그리고 승/패 대조가 미실시이므로 **이 축의 최대치는 「기술」**이다(§0-2 ③).")
    else:
        miss = [nm for nm, ok in (("`SEC-N1`", c_n1), ("`SEC-B1`", c_b1), ("`SEC-B2`", c_b2)) if not ok]
        say("🔴 **AND 가 거짓이다** — 미달 성분: "
            + (" · ".join(miss) if miss else "선행 게이트")
            + ". ⇒ §3 우선순위표대로 **§3 이 판정한다(지지 아님)** · §4-2 는 «인쇄 문언» · "
              "§4-6 은 «민감도 전용»이다.")
        if c_n1 and not c_b1:
            say("🔴 **`SEC-N1` 만 통과한 것을 지지로 인용하지 않는다** — 그 조합의 뜻은 "
                "*「저자가 급등주를 고른다」*이고 그건 `REG-M4` 가 이미 말한 것이다(§2-3 · §4-1). "
                "🔒 인쇄 문언(§4-2) = ***「저자 종목의 섹터 동반성이 같은 날 다른 급등주와 다르지 않다」***.")
        say("🔴 **불성립의 뜻은 「KSIC 섹터 동반상승으로는 안 잡힌다」까지다 — 「테마가 아니다」가 아니다**"
            "(§0-2 2번 · 거짓 음성이 구조적이다).")
    say()
    say("### `SEC-P2` — 글을 넘는 반복 (**기록만** · 검정 통계량 아님)")
    say()
    say("| 글 | 판정 | 누계 |")
    say("|---|---|---|")
    say(f"| post6 (직전 · 옮겨 적은 값 · 재계산 아님) | **{'성립' if SEC_P2_PRIOR['n_support'] else '불성립'}** | "
        f"성립 {SEC_P2_PRIOR['n_support']} / 판정 {SEC_P2_PRIOR['n_judgements']} |")
    n_judg_p7 = SEC_P2_PRIOR["n_judgements"] + (0 if p1_blocked else 1)
    say(f"| **post7 (`{POST7_LOG_NO}`)** | **{p1_word}**"
        + ("(`SEC-V1` 발동 · §3 1행 ⛔ 열)" if p1_blocked else "") + " | 성립 "
        f"**{SEC_P2_PRIOR['n_support'] + (1 if p1_ok else 0)}** / 판정 "
        f"**{n_judg_p7}** |")
    if p1_blocked:
        say()
        say("🔴 **post7 은 «판정»이 아니라 «판정 불가»이므로 누계 분모(판정 수)에 넣지 않는다** — "
            "3중 AND 통과는 위 §3 에 **기록**으로 남기되 `SEC-P2` 의 부호 누계에는 **성립으로도 "
            "불성립으로도 세지 않는다**(§6 *「갈리지 않는 글이 온다」*).")
    say()
    say("🆕 **누계를 «이어간다»**(🔒 결정 ⑥ · 보고서 §6 #6) — post6 값은 "
        "`RESULTS_SECTOR_POST6_NUMBERS.md` 에서 **옮겨 적은 상수**이고 **재계산이 아니다**"
        "(동결 산출물 byte 불변).")
    say("🔴 **누계를 검정 통계량으로 쓰지 않는다**(`RESULTS_D1_OOS_POST5.md` §8 승계) — "
        "**매 글 독립 판정 + 부호 누계**만 적고 **글별 `p` 를 곱하거나 더하지 않는다**(§2-6).")

    # ══════════════════════════════════════════════════════════════════════
    # §6 SEC-X1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §6. `SEC-X1` 섹터 라벨 **순열 대조군** — 귀무 «구현»의 1종오류율 (§4-4 · `SEC-D6`)")
    say()
    say("🔴🔴 **이 가드가 재는 것은 «귀무 구현의 1종오류율 보정» 하나뿐이다** — "
        "*「칸막이가 정보인가」를 재는 검정이 «아니다»*(§4-4 B-2). 라벨을 섞으면 저자와 귀무가 "
        "**교환 가능**해지므로 ***참 분할이 정보를 담든 잡음이든 `P(p<0.05)` 는 «항상» 5% 다.***")
    say("🔴 **`SEC-X1` 통과를 「섹터가 의미 있다」로 인용하지 않는다** — 그건 `SEC-B1`·`SEC-B2` 가 잰다.")
    say()
    X1_BASE = x1_base_for(items, DAY)
    t_x1 = time.time()
    x1 = x1_run(stream("sec_x1_perm"), stream("sec_x1_null"), X1_REP, dates, DAY, X1_BASE)
    t_x1 = time.time() - t_x1
    say(f"**명세**: 그날 유니버스의 `induty_code` 를 종목 사이에서 무작위로 «섞고»(집단 크기 분포 보존) "
        f"같은 측정자(`SEC-M1` · `N=3`)·같은 귀무를 계산 — **독립 실현 {X1_REP}개** × 귀무 {NREP:,}회.")
    say()
    say("| 풀 | 실현 수 | `p` 평균 | `p` 중앙 | **`p < 0.05` 비율** | `p < 0.20` 비율 | "
        "명목 대비(SE ≈ 1.5%p) | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    x1sum = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        ok = abs(z) <= 2.0
        x1sum[kind] = dict(n=len(ps), mean=float(ps.mean()), median=float(np.median(ps)),
                           lt05=rate, lt20=float(np.mean(ps < 0.20)), z=float(z), pass_=bool(ok))
        say(f"| `SEC-{kind}` | {len(ps)} | {ps.mean():.4f} | {np.median(ps):.4f} | "
            f"**{rate * 100:.1f}%** | {np.mean(ps < 0.20) * 100:.1f}% | "
            f"`z = {z:+.2f}` | " + ("🟢 **보정됨**" if ok else "🔴 **⛔ 절차 무효**") + " |")
    say()
    x1_ok = x1sum["N1"]["pass_"] and x1sum["B1"]["pass_"]
    say(f"- 순열 하 `p` 는 이론상 `U(0,1)` 이므로 `p<0.05` 비율의 기대는 **5.0%**, "
        f"{X1_REP} 실현의 SE ≈ **1.5%p** 다(§4-4). `|z| ≤ 2` 를 «어긋나지 않음»으로 읽는다.")
    if min(x1sum[k]["lt05"] for k in ("N1", "B1")) < P_THR:
        say("- 🔴 **경계값 해석 (비대칭 · 미리 적어 둔다)** — 이번 이탈은 **명목 5%보다 «아래»**"
            f"(**{x1sum['N1']['lt05'] * 100:.1f}%** · **{x1sum['B1']['lt05'] * 100:.1f}%**)다. "
            "그 방향은 ***거짓 «양성»을 만들 수 없고 검정력만 잃는다*** ⇒ "
            "🟢 **이번 «불성립» 판정을 위협하지 않는다**(과소기각은 「지지」를 만들어내지 못한다). "
            "🔴 **반대로 «통과»가 나온 회차에서 같은 부호가 나오면 그때는 위협이 된다** — "
            "그리고 «위쪽»으로 `|z| > 2` 면 그건 부호와 무관하게 ⛔ **절차 무효**다. "
            "🔑 ***가드의 이탈은 「크기」만이 아니라 「방향」까지 읽어야 판정에 대한 함의가 정해진다.***")
    say("- ⇒ 🔒 **`SEC-X1` : "
        + ("🟢 보정됨 ⇒ 절차 유효**" if x1_ok else "🔴 ⛔ 절차 무효 — 이 축을 닫는다**")
        + " (어긋나면 구현을 고친 뒤 **새 사전등록**으로만 연다 · §6).")
    say(f"- 🔴 순열 실현에서 저자 건이 «측정 불가»가 되는 일(섞인 뒤 `|P| = 0`)이 실현당 평균 "
        f"**{np.mean([r['drop'] for r in x1]):.2f}건** 있다. 크기 정합을 위해 그 건은 "
        "관측·귀무 «양쪽»에서 같이 빠진다.")
    say()
    say("### 6-1. 🔴 **가드를 «일부러» 켜서 발동을 실증한다** (§7-B #20 · `x1_bypass` 형식 승계)")
    say()
    say("🔑 ***「조항을 적었다」가 「그 조항이 발동한다」를 뜻하지 않는다*** — **귀무 구현을 «고장내고»**"
        "(추출 풀에서 상위 절반 백분위를 통째로 제거 ⇒ 교환가능성 파괴) 같은 순열 대조군을 돌린다. "
        "가드가 살아 있다면 1종오류율이 5%에서 «어긋나야» 한다.")
    say()
    x1b = x1_run(stream("sec_x1_bypass_perm"), stream("sec_x1_bypass_null"), X1_REP, dates, DAY,
                 X1_BASE, broken=True)
    say("| 귀무 구현 | `p < 0.05` 비율 | `z` | `SEC-X1` 판정 |")
    say("|---|---|---|---|")
    say(f"| 🟢 정상(위 §6 `SEC-N1`) | **{x1sum['N1']['lt05'] * 100:.1f}%** | "
        f"`{x1sum['N1']['z']:+.2f}` | "
        + ("🟢 보정됨 ⇒ 절차 유효" if x1sum["N1"]["pass_"] else "🔴 절차 무효") + " |")
    bx = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1b])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        bx[kind] = dict(lt05=rate, z=float(z), fired=bool(abs(z) > 2.0))
        say(f"| 🔴 **일부러 고장낸 것**(`SEC-{kind}` 풀 상위 절반 제거) | **{rate * 100:.1f}%** | "
            f"`{z:+.2f}` | "
            + ("🔴 **⛔ 절차 무효 — 가드 발동 ✅**" if abs(z) > 2.0 else "🟡 미발동") + " |")
    say()
    say("🆕 **`z` 부호 주시**(보고서 §6 #6 계열) — post6 의 정상 구현 `z` 는 **−1.95** 로 "
        "**경계(|z| > 2.0)에 붙어 있었다**. 이번 실측 정상 `z` = "
        f"**`{x1sum['N1']['z']:+.2f}`**(`SEC-N1`) · **`{x1sum['B1']['z']:+.2f}`**(`SEC-B1`) ⇒ "
        + ("🔴 **경계를 넘었다 — `SEC-X1` 이 정상 구현에서 발동한다**"
           if (abs(x1sum['N1']['z']) > 2.0 or abs(x1sum['B1']['z']) > 2.0)
           else "🟡 **아직 경계 안**") + ". "
        "🔴 **부호를 함께 적는다** — |z| 만 적으면 「보수적으로 어긋났다」와 「반보수적으로 "
        "어긋났다」를 구분할 수 없다(음수 = 명목보다 «덜» 기각 = 보수적).")
    say()
    fired = bx["N1"]["fired"] or bx["B1"]["fired"]
    say("⇒ " + ("🟢 **`SEC-X1` 이 실제로 발동한다** — 죽은 가드가 아니다."
                if fired else "🔴 **고장낸 구현에서도 발동하지 않았다** — 이 실증은 실패다.")
        + " 🔴 **그리고 이 발동은 「섹터가 무의미하다」와 무관하다** — 잰 것은 «우리 귀무 구현»이다(§4-4).")

    # ══════════════════════════════════════════════════════════════════════
    # §7 SEC-V1 + 재진입 민감도
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §7. `SEC-V1` 민감도 **4축** (§4-6) — 🔴 «민감도 전용»")
    say()
    say("🔒 **적용 범위**: 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」에만 적용된다. "
        "🔴 **§3 의 3중 AND 안에서 한 항목이 미달하는 사건에는 «관여하지 않는다»** — "
        "그건 갈린 게 아니라 **AND 가 거짓인 것**이고 그 판정은 §3 이 한다(§3 우선순위표).")
    say()
    say("⚠️ **「귀무 풀(`SEC-N1` ↔ `SEC-B1`)」은 이 표에 «없다»** — 민감도가 아니라 **판정 조건**이다(§4-6).")
    say()

    def verdict_of(E, g1r):
        if not E["vals"] or E["N1"] is None or E["B1"] is None or E["B2"]["rate"] is None:
            return None
        if g1r is not None and g1r >= G1_THR:
            return None
        return bool(E["N1"]["p_main"] < P_THR and E["B1"]["p_main"] < P_THR
                    and E["B2"]["rate"] > B2_THR)

    def vshow(v):
        return "⛔ 판정 불가" if v is None else ("✅ 성립" if v else "🔴 불성립")

    say("| # | 축 | 갈래 | 값(글 단위 중앙) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | `SEC-P1` | 판정 갈래 |")
    say("|---|---|---|---|---|---|---|---|---|")
    VD = {}

    def vrow(axis, axis_name, label, E, g1r, is_main):
        v = verdict_of(E, g1r)
        VD[(axis, label)] = v
        b2 = E["B2"]
        say(f"| {axis} | {axis_name} | {label} | {fmt(E['main'])} | "
            f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
            f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
            f"{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}% | **{vshow(v)}** | "
            + ("🔒 **판정**" if is_main else "민감도") + " |")

    for n in NS:
        note = " (🔴 구조적 미정 %.1f%% 병기)" % (G1[(5, MAIN_M)] * 100) if n == 5 else ""
        vrow(1, "섹터 깊이", f"`N = {n}`{note}", EV[(n, MAIN_M)], G1[(n, MAIN_M)], n == MAIN_N)
    for mk in MEAS:
        vrow(2, "측정자", f"`{mk}`", EV[(MAIN_N, mk)], G1[(MAIN_N, mk)], mk == MAIN_M)
    v_main = verdict_of(MAIN, g1_main)
    VD[(3, "글 단위 중앙")] = v_main
    say(f"| 3 | 집계 | 글 단위 중앙 | {fmt(MAIN['main'])} | {fmt(n1p, 4)} | {fmt(b1p, 4)} | "
        f"{fmt(b2r * 100 if b2r is not None else None)}% | **{vshow(v_main)}** | 🔒 **판정** |")
    p_pool_n1 = MAIN["N1"]["p_pool"] if MAIN["N1"] else None
    p_pool_b1 = MAIN["B1"]["p_pool"] if MAIN["B1"] else None
    v_pool = None
    if p_pool_n1 is not None and p_pool_b1 is not None and b2r is not None and g1_main < G1_THR:
        v_pool = bool(p_pool_n1 < P_THR and p_pool_b1 < P_THR and b2r > B2_THR)
    VD[(3, "건 pooled 중앙")] = v_pool
    say(f"| 3 | 집계 | 건 pooled 중앙 | {fmt(MAIN['pooled'])} | {fmt(p_pool_n1, 4)} | "
        f"{fmt(p_pool_b1, 4)} | 〃 | **{vshow(v_pool)}** | 민감도 |")
    VD[(4, "`exact` 만")] = v_main
    say(f"| 4 | 등록일 정밀도 | `exact` 만 ({len(items)}건 · 측정 가능 {len(MAIN['vals'])}) | "
        f"{fmt(MAIN['main'])} | {fmt(n1p, 4)} | {fmt(b1p, 4)} | "
        f"{fmt(b2r * 100 if b2r is not None else None)}% | **{vshow(v_main)}** | 🔒 **판정** |")
    if ap_items:
        ap_all_items = items + ap_items
        E_ap = full_eval(ap_all_items, MAIN_N, MAIN_M)
        g1_ap = sum(1 for b in E_ap["bs"] if not b["ok"]) / len(ap_all_items)
        vrow(4, "등록일 정밀도", f"`approx` 포함 ({len(ap_all_items)}건)", E_ap, g1_ap, False)
    else:
        VD[(4, "`approx` 포함")] = v_main
        say(f"| 4 | 등록일 정밀도 | `approx` 포함 (**추가 0건**) | {fmt(MAIN['main'])} | "
            f"{fmt(n1p, 4)} | {fmt(b1p, 4)} | {fmt(b2r * 100 if b2r is not None else None)}% | "
            f"**{vshow(v_main)}** | 민감도(**구조적으로 동일**) |")
    say()
    if not ap_items:
        say("🟢 **축 ④ 는 이 글에서 «구조적으로» 갈릴 수 없다** — post7 의 `approx` 가 **0건**이라 "
            "「`approx` 포함」 집합이 「`exact` 만」과 **같은 집합**이다(모호가 아니라 정의다). "
            "🔴 그래서 이 축의 «불갈림»을 **잣대 강건성의 증거로 읽지 않는다.**")
    say("🟢 **축 ③ 도 이 글에서 «구조적으로» 갈릴 수 없다** — 글이 하나뿐이라 "
        "글 단위 중앙 = 건 pooled 중앙이다(§3 말미). "
        "⚠️ 다만 **귀무 집계는 다른 경로로 계산되므로 `p` 는 미세하게 다를 수 있다** — "
        "위 표에 두 `p` 를 «둘 다» 인쇄했다.")
    vals_v = list(VD.values())
    kinds = {str(v): v for v in vals_v}
    split = len(kinds) > 1
    # 🔒 §3 이 «앞에서» 쓴 값과 같아야 한다 — 같은 `verdict_of` · 같은 4축(§4-6).
    assert split == v1_split_pre, ("SEC-V1 배선 불일치", split, v1_split_pre)
    say()
    say("### 🔒 `SEC-V1` : **" + ("🔴 갈린다" if split else "🟢 갈리지 않는다") + "** "
        + f"({len(kinds)}종 판정 — "
        + " · ".join(f"{vshow(v)}:{sum(1 for x in vals_v if str(x) == k)}"
                     for k, v in sorted(kinds.items())) + ")")
    say()
    if split:
        say("🔴 **갈렸다 ⇒ §4-6 대로 «어느 쪽도 선언하지 않는다».** "
            "🔒 §3 1행의 ⛔ 열이 `SEC-V1` 을 **판정 불가 조건**으로 열거하므로"
            "(`PREREG_SECTOR_COMOVE.md:600`) 이 갈림은 §3 의 `SEC-P1` 을 ⛔ 로 만든다 — "
            "**위 §3 에 그렇게 인쇄돼 있다.** "
            "🔴 **단 적용 범위(`:819`)는 「같은 판정을 «다른 잣대»로 다시 계산했을 때 "
            "갈리는가」뿐이다** — 주 갈래의 3중 AND 가 «거짓»인 사건은 §3 이 판정하고 이 조항은 "
            "관여하지 않는다. ***어느 쪽이든 잣대를 넓혀 열지 않는다.***")
    else:
        say("🟢 **4축 어디서도 판정이 갈리지 않는다** ⇒ `SEC-V1` 은 발동하지 않는다. "
            "🔴 **그래도 이것을 「결론이 튼튼하다」로 읽지 않는다** — 갈릴 수 «없는» 축이 둘(③·④) 있다(위).")
    say()
    say("#### 🔴🔴 7-1A. 모호 지점 — **`SEC-V1` 의 «입력»이 4축인가 9 조합인가** (양쪽 인쇄)")
    say()
    say("사전등록이 두 곳에서 다르게 읽힌다. **어느 쪽으로도 고치지 않고 둘 다 인쇄한다.**")
    say()
    say("| 읽기 | 근거 문언 | 무엇을 세나 |")
    say("|---|---|---|")
    say("| **A**(위 표 · 이 스크립트의 판정) | §4-6 *「아래 **4축**을 «항상» 나란히 인쇄한다」* — 표가 "
        "**한 번에 한 축**만 흔든다(`N` 은 `SEC-M1` 에서 · 측정자는 `N=3` 에서) | 위 10행 |")
    say("| **B**(확장) | §4-5 *「**9 조합**을 다 인쇄하되 판정은 «동결된 하나»로만 한다. "
        "나머지는 `SEC-V1` 의 «입력»이다」* | 9 조합 «전부»(대각선 조합 포함) |")
    say()
    say("| `N` | 측정자 | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | `SEC-G1` | 3중 AND |")
    say("|---|---|---|---|---|---|---|")
    ext = {}
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            v = verdict_of(E, G1[(n, mk)])
            ext[(n, mk)] = v
            b2 = E["B2"]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | "
                f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
                f"{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}% | "
                f"{G1[(n, mk)] * 100:.1f}% | **{vshow(v)}** |")
    say()
    passers = [f"`N={n}` × `{mk}`" for (n, mk), v in ext.items() if v]
    ext_kinds = {str(v): v for v in ext.values()}
    say(f"- 🔴 **읽기 B 에서 3중 AND 를 통과하는 조합 = {len(passers)}개**"
        + (f": **{' · '.join(passers)}**" if passers else " — 없다") + ".")
    if passers and not p1_ok:
        say("- 🔴🔴 **그 조합은 판정 갈래가 «아니고», 읽기 A 의 4축 «어느 항목도» 아니다**"
            "(두 축을 «동시에» 흔든 대각선 조합이다). 🔒 **§4-5 문언 그대로 판정은 «동결된 하나»로만 "
            "한다** ⇒ ***이 통과를 `SEC-P1` 의 지지로 인용하는 것은 금지된다.*** "
            "🔑 ***값을 보고 갈래를 고르면 그게 사후적합이다.***")
        say(f"- 🟢 **그리고 두 읽기 «어느 쪽으로도» 결론이 같다** — 읽기 A 는 {len(kinds)}종, "
            f"읽기 B 는 {len(ext_kinds)}종 ⇒ **둘 다 「갈린다」**이고, 그래서 §4-6 의 "
            "「어느 쪽도 선언하지 않는다」가 **읽기를 고르는 것과 무관하게** 발동한다. "
            "주 갈래의 3중 AND 자체는 §3 이 «기록»으로 남긴다(§5).")
        say("- 🔴 **그래도 이 사실을 숨기지 않는다** — 이 축에서 「통과하는 잣대가 «존재»한다」는 것은 "
            "***다음 글에서 `SEC-D1`·`SEC-D2` 를 바꾸고 싶어지는 압력***이고, 그 압력이 곧 "
            "이 프로그램이 금지한 동작이다. **바꾸려면 새 사전등록이 필요하다.**")
    say()
    say(f"### 7-2. 🔂 재진입 {len(PD3_IN)}건 **제외** 민감도 (`PREREG_POST6.md` §1-5 · PD-3 — 의무)")
    say()
    say("🔴 **제외 대상은 «판정 분모 안» 재진입뿐이다** — 글 전체 재진입은 3건이지만 그중 2건"
        "(지투파워 · 한국화장품제조)은 `approx` 라 애초에 이 분모에 없다. "
        "***두 민감도(재진입 제외 ↔ `approx` 제외)를 합치지 않는다***(PD-3 말미).")
    say()
    keep = [it for it in items if it["code"] not in PD3_FLAG_P7]
    E_re = full_eval(keep, MAIN_N, MAIN_M)
    g1_re = sum(1 for b in E_re["bs"] if not b["ok"]) / len(keep) if keep else None
    v_re = verdict_of(E_re, g1_re)
    say("| 갈래 | 분모 | 측정 가능 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | "
        "`SEC-G1` | `SEC-P1` |")
    say("|---|---|---|---|---|---|---|---|---|")
    say(f"| 🔒 **포함**(판정) | {len(items)} | {len(MAIN['vals'])} | {fmt(MAIN['main'])} | "
        f"{fmt(n1p, 4)} | {fmt(b1p, 4)} | {fmt(b2r * 100 if b2r is not None else None)}% "
        f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | {g1_main * 100:.1f}% | **{vshow(v_main)}** |")
    say(f"| 제외(민감도) | {len(keep)} | {len(E_re['vals'])} | {fmt(E_re['main'])} | "
        f"{fmt(E_re['N1']['p_main'], 4) if E_re['N1'] else '⛔'} | "
        f"{fmt(E_re['B1']['p_main'], 4) if E_re['B1'] else '⛔'} | "
        f"{fmt(E_re['B2']['rate'] * 100 if E_re['B2']['rate'] is not None else None)}% "
        f"({E_re['B2']['wins']}/{E_re['B2']['n']}) | "
        + (f"{g1_re * 100:.1f}%" if g1_re is not None else "—") + f" | **{vshow(v_re)}** |")
    say()
    say("- 🔒 **분모는 «포함»이다**(§1-5 1번) — 제외는 **의무 민감도**다. 두 갈래 판정 = **"
        + ("같다" if str(v_re) == str(v_main) else "🔴 다르다 ⇒ 「재진입 의존」으로 적는다") + "**.")
    say(f"- `P6-PRIOR_CYCLE_IN_WINDOW` **판정 분모 안 합 = {sum(PD3_IN.values())}/{len(items)}** ("
        + (" · ".join(f"`{c}`={v}" for c, v in sorted(PD3_IN.items())) or "—")
        + ") · 🔴 **글 전체 합 = %d/%d**(" % (sum(PD3_FLAG_P7.values()), len(PD3_FLAG_P7))
        + " · ".join(f"`{c}`={v}" for c, v in sorted(PD3_FLAG_P7.items()))
        + ") — PD-3 이 계산 «전»에 못박은 값이다. 🔑 **두 수를 한 수로 합치지 않는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §8 SEC-O1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §8. `SEC-O1` — 훈련(post1~5 🔬) ↔ 검증(post7 🔒) **나란히** (§4-5)")
    say()
    say("🔴 **훈련 성적을 판정 분모에 절대 넣지 않는다**(§4-5 · `PREREG_POST6.md` §2-1 ③ 문형). "
        "아래 훈련 열은 **탐색적 표기**이며, 세 열의 뜻이 서로 다르다:")
    say()
    say("| 열 | 뜻 |")
    say("|---|---|")
    say(f"| 훈련(동결) | `FREEZE_SECTOR_2026-09-03.md` §4-2 — **DB 스냅샷 `{FROZEN_TRAIN['db_snapshot']}`** |")
    say(f"| 훈련(재계산) | 같은 post1~5 표본을 **이 실행의 DB 스냅샷 `{END}`** 로 다시 잰 값 |")
    say(f"| 🔒 검증(post7) | **판정** — 분모 post7 신규 `exact` {len(items)}건 |")
    say()
    E_tr = full_eval(train, MAIN_N, MAIN_M)
    g1_tr = sum(1 for b in E_tr["bs"] if not b["ok"]) / len(train)
    tr_n1 = E_tr["N1"]["p_main"] if E_tr["N1"] else None
    tr_b1 = E_tr["B1"]["p_main"] if E_tr["B1"] else None
    tr_b2 = E_tr["B2"]["rate"]

    def gap(a, b, nd=4):
        if a is None or b is None:
            return "—"
        return f"{b - a:+.{nd}f}"

    say(f"| 항목 | 훈련(동결 · {FROZEN_TRAIN['db_snapshot']}) | 훈련(재계산 · {END}) | "
        "🔴 훈련 괴리 | 🔒 검증 post7 | 🔴 **훈련↔검증 괴리** |")
    say("|---|---|---|---|---|---|")
    say(f"| 분모 `exact` | {FROZEN_TRAIN['n_items']} | {len(train)} | "
        + ("✅ 같다" if len(train) == FROZEN_TRAIN["n_items"] else "🔴 다르다")
        + f" | **{len(items)}** | — |")
    say(f"| 측정 가능 | {FROZEN_TRAIN['n_measurable']} | {len(E_tr['vals'])} | "
        + ("✅" if len(E_tr["vals"]) == FROZEN_TRAIN["n_measurable"] else "🔴")
        + f" | **{len(MAIN['vals'])}** | — |")
    say(f"| 관측(글 단위 중앙) | {FROZEN_TRAIN['main']:.1f} | {fmt(E_tr['main'])} | "
        f"{gap(FROZEN_TRAIN['main'], E_tr['main'], 1)} | **{fmt(MAIN['main'])}** | "
        f"**{gap(E_tr['main'], MAIN['main'], 1)}** |")
    say(f"| `SEC-N1` `p` | {FROZEN_TRAIN['N1']:.4f} | {fmt(tr_n1, 4)} | "
        f"{gap(FROZEN_TRAIN['N1'], tr_n1)} | **{fmt(n1p, 4)}** | **{gap(tr_n1, n1p)}** |")
    say(f"| `SEC-B1` `p` | {FROZEN_TRAIN['B1']:.4f} | {fmt(tr_b1, 4)} | "
        f"{gap(FROZEN_TRAIN['B1'], tr_b1)} | **{fmt(b1p, 4)}** | **{gap(tr_b1, b1p)}** |")
    say(f"| `SEC-B2` 승률 | {FROZEN_TRAIN['B2'] * 100:.1f}% "
        f"({FROZEN_TRAIN['B2_wins']}/{FROZEN_TRAIN['B2_n']}) | "
        f"{fmt(tr_b2 * 100 if tr_b2 is not None else None)}% ({E_tr['B2']['wins']}/{E_tr['B2']['n']}) | "
        f"{gap(FROZEN_TRAIN['B2'] * 100, tr_b2 * 100 if tr_b2 is not None else None, 1)}%p | "
        f"**{fmt(b2r * 100 if b2r is not None else None)}%** "
        f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | "
        f"**{gap(tr_b2 * 100 if tr_b2 is not None else None, b2r * 100 if b2r is not None else None, 1)}%p** |")
    say(f"| `SEC-G1` | {FROZEN_TRAIN['G1'] * 100:.1f}% | {g1_tr * 100:.1f}% | "
        f"{gap(FROZEN_TRAIN['G1'] * 100, g1_tr * 100, 1)}%p | **{g1_main * 100:.1f}%** | "
        f"**{gap(g1_tr * 100, g1_main * 100, 1)}%p** |")
    say()
    drift = [nm for nm, a, b in (
        ("관측", FROZEN_TRAIN["main"], E_tr["main"]),
        ("`SEC-N1`", FROZEN_TRAIN["N1"], tr_n1),
        ("`SEC-B1`", FROZEN_TRAIN["B1"], tr_b1),
        ("`SEC-B2`", FROZEN_TRAIN["B2"], tr_b2),
        ("`SEC-G1`", FROZEN_TRAIN["G1"], g1_tr))
        if a is not None and b is not None and abs(a - b) > 1e-9]
    # 🔴 「이 기간에 자란 종목」을 **하드코딩하지 않고 실측한다** — 동결 훈련 DB 스냅샷
    #    «뒤»에 첫 봉이 생긴 종목이 곧 「두 창 사이 신규」다(코드 상수 인용 금지).
    cur.execute("SELECT stock_code, min(date) FROM daily_prices GROUP BY 1 "
                "HAVING min(date) > %s ORDER BY 2, 1", (FROZEN_TRAIN["db_snapshot"],))
    grew = [(c, str(d)) for c, d in cur.fetchall()]
    si_absent = [c for c, _ in grew if c not in SEC]
    grew_txt = " · ".join("`%s`(첫 봉 %s)" % (c, d) for c, d in grew) if grew else "없음"
    say(f"- 🔴 **훈련 괴리(동결 ↔ 재계산) = {len(drift)}항목**"
        + (f": {' · '.join(drift)}" if drift else " — 🟢 **전부 일치**")
        + f". 🔴 **「DB 가 자라서」 가설은 «실측으로 기각»한다** — 동결 훈련 스냅샷"
          f"(`{FROZEN_TRAIN['db_snapshot']}`) «뒤»에 첫 봉이 생긴 종목은 **{len(grew)}종목**"
          f"({grew_txt})이고, 그 중 **`stock_industry` 에 없는 것 {len(si_absent)}/{len(grew)}** = "
          f"{'·'.join('`%s`' % c for c in si_absent) if si_absent else '없음'} ⇒ "
        + ("***조인 유니버스에 애초에 진입하지 못한다*** ⇒ `SEC-` 측정값을 움직일 «경로가 없다». "
           "🟢 **남는 설명은 하나뿐 — 동결본에 적힌 값이 «반올림 표기»라서다**"
           "(바로 아래 줄이 그 대조다)."
           if len(si_absent) == len(grew) else
           "🔴🔴 **일부는 조인 유니버스에 «들어온다» ⇒ 이 가설을 기각할 수 없다** — "
           "아래 반올림 대조와 «함께» 읽어야 한다."))
    # 🔴 위 «괴리» 판정은 «전정밀도 float ↔ 동결본의 «인쇄된» 반올림 값»을 비교한다.
    #    같은 대조를 **동결본이 인쇄한 정밀도로** 한 번 더 인쇄한다(양쪽 인쇄 · 규칙 변경 아님).
    same_print = [nm for nm, a, b, nd in (
        ("관측", FROZEN_TRAIN["main"], E_tr["main"], 1),
        ("`SEC-N1`", FROZEN_TRAIN["N1"], tr_n1, 4),
        ("`SEC-B1`", FROZEN_TRAIN["B1"], tr_b1, 4),
        ("`SEC-B2`", FROZEN_TRAIN["B2"], tr_b2, 2),
        ("`SEC-G1`", FROZEN_TRAIN["G1"], g1_tr, 3))
        if a is not None and b is not None and f"{a:.{nd}f}" == f"{b:.{nd}f}"]
    say(f"- 🟢 **같은 대조를 «동결본이 인쇄한 정밀도»로 하면 {len(same_print)}/5 항목이 일치한다**"
        + (f"({' · '.join(same_print)}). " if same_print else ". ")
        + "🔑 ***그러므로 위 「괴리 2항목」은 «DB 가 값을 움직였다»가 아니라 "
          "«동결본에 적힌 값이 반올림 표기»라서 생긴 것이다*** — 두 문장은 다르고, "
          "**둘 다 인쇄해야 어느 쪽인지 갈린다.**")
    say("- 🟢 **독립 확인**: 같은 실행의 배선 점검 모드 산출물에서도 `sector_dryrun/` 의 건별 JSON "
        "18건·`cases.tsv` 데이터 행이 동결본과 **byte 단위로 같다**(바뀐 것은 «DB 스냅샷 날짜 문자열»뿐). "
        "⇒ ***`SEC-` 측정값은 이번 DB 성장에 «불변»이었다.***")
    say("- 🔴 **훈련↔검증 괴리를 「악화/개선」으로 읽지 않는다** — 두 열은 **다른 표본**이고 훈련은 "
        "**판정 분모 «밖»**이다(§4-5). 나란히 두는 것은 *「잣대를 고른 것을 신고했나」*를 보이기 "
        "위해서지 두 열을 비교 검정하기 위해서가 아니다.")
    say("- 🔒 **`SEC-O1` 판정** = 잣대 결정(`SEC-D1`·`D2`) **2026-09-02** ↔ 배선 점검 **2026-09-02** ↔ "
        "동결 커밋 **2026-09-03** ↔ `fetch_post.py`(post7) **2026-09-15 15:36:49 KST** ↔ "
        "이 계산 **그 «후»** "
        "⇒ 🟢 **결정이 §0-4 4번 «앞»이다 — 유효**(⛔ 경로 = 결정이 4번 «뒤»면 무효 · PD-0 이 증거).")

    # ══════════════════════════════════════════════════════════════════════
    # §9 미해소·한계
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §9. 판정 불가·미해소·한계")
    say()
    say("| 항목 | 상태 |")
    say("|---|---|")
    say("| `SEC-P1` | **" + p1_label + "**"
        + (" — 🔴 3중 AND 는 통과했으나 `SEC-V1`(4축 갈림)이 ⛔ 다(§3 1행 ⛔ 열 · §6). "
           "***「계열 최초 성립」이 아니다*** — 갈리지 않는 글이 오면 판정한다" if p1_blocked else
           " — 천장은 §0-2(성립 = 「섹터 동반성 존재」까지 · 불성립 = 「KSIC 섹터 동반상승으로는 "
           "안 잡힌다」까지)") + " |")
    say(f"| `SEC-P2` | 🔒 **기록만** — **이 글에서** 판정 {0 if p1_blocked else 1}회"
        + ("(⛔ 판정 불가라 누계 «분모»에 안 들어간다)" if p1_blocked else "")
        + f" · 성립 {1 if p1_ok else 0}회. 누계를 검정 통계량으로 쓰지 않는다 |")
    say("| `SEC-B1` 발화 | " + ("🟢 가능" if b1fire else "🔴 ⛔ 발화 불가")
        + f" (`q_top` 최대 {qmax:.3f} · 문턱 {QTOP_THR}) |")
    say("| `SEC-X1` | " + ("🟢 보정됨" if x1_ok else "🔴 ⛔ 절차 무효") + " · 고장 실증 "
        + ("✅ 발동" if fired else "🔴 미발동(실증 실패)") + " |")
    say("| `SEC-V1` | " + ("🔴 갈린다 ⇒ 선언 금지" if split else "🟢 갈리지 않는다")
        + " — 🔴 축 ③·④ 는 이 글에서 «구조적으로» 갈릴 수 없다 |")
    say("| 승/패 대조(`PREREG_SELECTION.md` §4) | ⛔ **3회 연속 미실시** — post7 `exact` 신규에 "
        "`all_loss = 1` 이 0건(`INTAKE_2026-09-15_post7.md` §2 7번) ⇒ "
        "***이 축의 최대치는 「기술」이다***(§0-2 ③) |")
    say("| 「테마로 고른다」 확증 | ⛔ **이 축에서는 «영구히» 열리지 않는다**(§0-2 · §9 · "
        "에코프로 4종목 → 3칸) |")
    say("| 「섹터 안 «누구»냐」 | ⛔ **미해결** — `RNK-` 축이 멈춘 그 공백이 한 층 위로 옮겨갈 뿐이다(§9) |")
    say(f"| 후속 3건({' · '.join(POST7_FOLLOWUP)}) | 🔒 **분모 밖**(PD-2 · "
        "`reg_date_precision = none` · 이중계상 금지) |")
    say(f"| 신규이나 등록일 문장 부재 2건({' · '.join(POST7_NONE_NEW)}) | 🔒 **분모 밖**(PD-4) — "
        "🔴 「값이 나빠서」가 아니라 **어느 날의 유니버스인지 정할 수 없어서**다. "
        "급등 사유일(08-26)을 등록일로 **승격하지 않는다** |")
    say("| 해치텍(`0155E0`) | 🔴 **분모 «안»인데 섹터 표에 없다** — `stock_industry` 스냅샷이 "
        "2026-08-07 에서 멈춰 있고 이 종목은 2026-08-25 상장이다 ⇒ 사유 ③. "
        "***이 자리가 이 축의 구조적 거짓 음성이 실제로 들어온 자리다*** |")
    say("| 표본이 저자가 «올리기로 고른» 매매 | 🔴 **그대로** — 결과 조건화 위협"
        "(`PREREG_SELECTION.md` §0) |")
    say("| `regen_gate.py` | ⬜ **관리자** — `PAIRS[\"RESULTS_SECTOR_POST7_NUMBERS.md\"]` 가 아직 "
        "`PENDING` 에 있어, 이 파일이 «생긴» 지금 `check()` 는 *「산출물이 생겼는데 `PENDING` 에 "
        "남아 있다」* 로 **FAIL 한다**. 🔒 **설계된 상태**이며 해소(=`PENDING` 에서 빼고 `--update`)는 "
        "동결·머지 레인의 동작이다 |")
    say(f"| 스냅샷 의존 | 🔴 **가격 표도 섹터 표도 자란다** — 이 글의 값은 `daily_prices` "
        f"`max(date)` = **`{END}`** · `stock_industry` **{si_rows:,}행** · `max(updated_at)` "
        f"**`{si_upd}`** 위에서만 재현된다(§2-6 · §8-5) |")
    say()
    say("🔴 **매 산출물 의무 문언 재확인**: 거짓 음성이 구조적이다 — 테마는 KSIC 축을 가로지른다"
        "(에코프로 4종목 → 3칸). ⇒ ***`SEC-P1` 불성립을 「테마가 아니다」로 읽지 않는다.***")
    say("🔴 **동반 상승은 «등록일 종가가 확정된 뒤»의 정보로 잰다** ⇒ ***이 축은 라이브에서 재현할 수 "
        "없는 지표다***(§9 · `REG-M5` 형 단서).")
    say("🔴 **이 실행은 새 예측을 만들지 않았다** — `SEC-P1`·`P2`·`N1`·`B1`·`B2`·`G1`·`X1`·`O1`·`V1` 은 "
        "전부 사전등록 §3 표의 항목이고, 새 문턱·새 측정자·새 갈래는 **0건**이다.")
    say()
    say("---")
    say()
    say(f"결정성: 시드 `{SEED}` 고정 · 스트림 분리 · DB 는 SELECT 만 ⇒ **같은 DB 스냅샷에서 재실행하면 "
        "byte 단위로 같다**(`regen_gate.py --rerun` 전제). "
        "🔴 그래서 이 파일에는 **실행 시간·커밋 해시를 적지 않는다** — 벽시계·`HEAD` 는 stdout 전용이다. "
        "🔑 ***커밋마다 바뀌는 값을 산출물에 적으면 그 산출물은 자기 자신을 재현할 수 없게 된다.***")
    say()
    say("[[PREREG_SECTOR_COMOVE]] · [[FREEZE_SECTOR_2026-09-03]] · [[RESULTS_SECTOR_DRYRUN]] · "
        "[[PREREG_POST6]] · [[PREDECISION_2026-09-15_post7]] · [[INTAKE_2026-09-15_post7]] · "
        "[[PREREG_RANKING]] · [[FINDING_THEME_AXIS]] · [[RESULTS_RANKING_TRAIN]] · "
        "[[RESULTS_REGDAY_POST5]] · [[RESULTS_D1_OOS_POST5]] · [[RESULTS_RECONSTRUCT_POST4]] · "
        "[[PREREG_SELECTION]]")

    # ══════════════════════════════════════════════════════════════════════
    # 기계 산출물
    # ══════════════════════════════════════════════════════════════════════
    # 🔴 `approx` 2건의 `reg_date` 가 원장에서 «비어 있다»(PD-4) — 어느 날의 유니버스인지 정할 수
    #    없으므로 **날짜 키가 아니다**. 측정에서는 이미 «측정 불가»로 들어가 `SEC-G1` 에 반영됐고
    #    (규칙·문턱·분모를 바꾸지 않았다), 아래 스냅샷 표에서는 «날짜»로 세지 않고 그 사실을 적는다.
    man_dates = [d for d in all_dates if d]
    undated_ap = sorted({it["name"] for it in ap_items if not it["reg"]})
    universe = {d: DAY[d]["uni"] for d in man_dates}
    joined = {d: DAY[d]["joined"] for d in man_dates}
    (ART / "universe_snapshot.json").write_text(json.dumps({
        "window_end": END, "db_snapshot_max_date": SNAP_MAX, "db_snapshot_rows_on_max_date": SNAP_ROWS,
        "post_log_no": POST7_LOG_NO, "post_date": "2026-09-12",
        "window_end_note": "창 종료 2026-09-11 = 발행일(2026-09-12 토) 휴장 ⇒ 마지막 거래일 · "
                           "B-1(전 축 · PD-1) · 실행 시 max(date) 는 기록만 하고 창으로 쓰지 않는다 · "
                           "이 축은 창을 쓰지 않고 등록일 당일만 쓴다",
        "pseudo_from_code": list(PSEUDO),
        "pseudo_nonnumeric_in_db": nonnum, "pseudo_final": final_pseudo,
        "universe_sizes": {d: len(universe[d]) for d in man_dates},
        "joined_sizes": {d: len(joined[d]) for d in man_dates},
        "coverage_pct": {d: round(len(joined[d]) / len(universe[d]) * 100, 4) for d in man_dates},
        "universe": universe, "joined": joined,
        "sha256_universe": {d: sha_list(universe[d]) for d in man_dates},
        "sha256_joined": {d: sha_list(joined[d]) for d in man_dates},
        "undated_approx_items": undated_ap,
        "undated_approx_note": "reg_date 가 비어 있어 등록일 유니버스를 정할 수 없다(PD-4) — "
                               "측정에서는 «측정 불가»로 SEC-G1 분모에 들어갔고, 이 표에는 날짜로 세지 않는다",
        "_notation": NOTATION_POST7,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "sector_snapshot.json").write_text(json.dumps({
        "table": "stock_industry", "rows": si_rows, "distinct_stock_code": si_uniq,
        "induty_code_non_null": si_nonnull, "max_updated_at": si_upd,
        "sha256_code_to_induty": si_sha,
        "length_distribution_table": {str(k): v for k, v in sorted(len_all.items())},
        "stock_info_sector_non_null": info_sector, "stock_info_rows": info_rows,
        "warning": "이 표는 시간에 따라 «자란다» — 편입이 늘면 같은 글의 값이 달라진다",
        "_notation": NOTATION_POST7,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for ci, it in enumerate(items):
        rec = {k: it[k] for k in ("post", "log_no", "item_no", "name", "code", "reg", "prec", "all_loss")}
        rec["window_end"] = END
        rec["db_snapshot_max_date"] = SNAP_MAX
        rec["main_branch"] = {"N": MAIN_N, "measure": MAIN_M}
        rec["reentry"] = ({"prior_cycle_reg_date": REENTRY_P7.get(it["code"]),
                           "P6_PRIOR_CYCLE_IN_WINDOW": PD3_FLAG_P7.get(it["code"])}
                          if it["code"] in PD3_FLAG_P7 else None)
        rec["branches"] = {}
        for n in NS:
            for mk in MEAS:
                bb = BR[(n, mk)][ci]
                rec["branches"][f"N{n}_{mk}"] = {
                    kk: (round(vv, 6) if isinstance(vv, float) else vv)
                    for kk, vv in bb.items()}
        rec["_notation"] = NOTATION_POST7
        (ART / f"case_{it['post']}_{it['item_no']}_{it['name']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "verdict.json").write_text(json.dumps({
        "post_log_no": POST7_LOG_NO, "post_date": "2026-09-12",
        "window_end": END, "db_snapshot_max_date": SNAP_MAX,
        "db_snapshot_rows_on_max_date": SNAP_ROWS,
        "main_branch": {"N": MAIN_N, "measure": MAIN_M},
        "denominator_exact": len(items), "measurable": len(MAIN["vals"]),
        "excluded_none_rows": [r["stock_name"] for r in none_rows],
        "gates": {
            "min_exact": {"threshold": MIN_EXACT, "n": len(items),
                          "open": bool(len(items) >= MIN_EXACT)},
            "SEC-G1": {"threshold": G1_THR, "rate": g1_main, "open": bool(g1_main < G1_THR)},
            "SEC-B1_fire": {"q_top_max": qmax, "q_top_threshold": QTOP_THR, "k": kmain,
                            "p_ceiling": (binom_ge_half(kmain, qmax) if kmain else None),
                            "open": bool(b1fire)},
            "SEC-X1": {"lt05_N1": x1sum["N1"]["lt05"], "lt05_B1": x1sum["B1"]["lt05"],
                       "z_N1": x1sum["N1"]["z"], "z_B1": x1sum["B1"]["z"], "open": bool(x1_ok)},
        },
        "SEC-P1": {"components": {"SEC-N1": n1p, "SEC-B1": b1p, "SEC-B2": b2r},
                   "thresholds": {"SEC-N1": P_THR, "SEC-B1": P_THR, "SEC-B2": B2_THR},
                   "passed": {"SEC-N1": bool(c_n1), "SEC-B1": bool(c_b1), "SEC-B2": bool(c_b2)},
                   "and_passed": and_ok,
                   "SEC-V1_split": v1_split_pre,
                   "blocked_by_SEC-V1": p1_blocked,
                   "verdict": (None if p1_blocked else p1_ok),
                   "verdict_label": p1_word},
        "SEC-P2": {"note": "기록만 — 검정 통계량 아님 · 누계 이어가기(결정 ⑥)",
                   "prior": SEC_P2_PRIOR,
                   "n_judgements": SEC_P2_PRIOR["n_judgements"] + (0 if p1_blocked else 1),
                   "n_support": SEC_P2_PRIOR["n_support"] + (1 if p1_ok else 0)},
        "SEC-V1": {"split": bool(split),
                   "by_branch": {f"{a}|{b}": v for (a, b), v in VD.items()}},
        "reentry_sensitivity": {"excluded_codes": sorted(PD3_IN),
                                "P6_PRIOR_CYCLE_IN_WINDOW_in_denominator": PD3_IN,
                                "P6_PRIOR_CYCLE_IN_WINDOW_whole_post": PD3_FLAG_P7,
                                "note": "글 전체 재진입 3건 중 2건은 approx 라 분모 밖 — 두 수를 합치지 않는다(PD-3)",
                                "verdict_kept": v_main, "verdict_excluded": v_re,
                                "main_kept": MAIN["main"], "main_excluded": E_re["main"]},
        "SEC-O1": {"frozen_train": FROZEN_TRAIN,
                   "recomputed_train": {"main": E_tr["main"], "SEC-N1": tr_n1, "SEC-B1": tr_b1,
                                        "SEC-B2": tr_b2, "SEC-G1": g1_tr,
                                        "n_items": len(train), "n_measurable": len(E_tr["vals"])},
                   "drift_items": drift},
        "_notation": NOTATION_POST7,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "controls_summary.json").write_text(json.dumps({
        "seed": SEED, "nrep": NREP, "note_nrep": "run_selection.py:22 는 NREP=2000",
        "streams": _STREAM_NAMES, "x1_realizations": X1_REP,
        # 🔴 두 값은 «다른 것»이다 — 섞어 쓰면 재현자가 창을 잘못 잡는다(PD-1 5번).
        #    `window_end`       = 판정 창 종료(= 발행일 09-12 토 휴장 ⇒ 09-11) — **판정에 쓴다**
        #    `db_snapshot_max_date` = 실행 시 `daily_prices` 의 실제 `max(date)` — **기록만** 한다
        "window_end": END,
        "db_snapshot_max_date": SNAP_MAX,
        "db_snapshot_rows_on_max_date": SNAP_ROWS,
        "thresholds": {"p": P_THR, "B2": B2_THR, "G1": G1_THR, "q_top": QTOP_THR,
                       "n_up_multiplier": UP_MULT, "drop_mark": DROP_MARK,
                       "min_exact": MIN_EXACT},
        "observed": {f"N{n}_{mk}": {"main": EV[(n, mk)]["main"], "pooled": EV[(n, mk)]["pooled"],
                                    "n_measurable": len(EV[(n, mk)]["vals"])}
                     for n in NS for mk in MEAS},
        "nulls": {f"N{n}_{mk}": {"SEC-N1": EV[(n, mk)]["N1"], "SEC-B1": EV[(n, mk)]["B1"],
                                 "SEC-B2": EV[(n, mk)]["B2"]}
                  for n in NS for mk in MEAS},
        "G1_rate": {f"N{n}_{mk}": G1[(n, mk)] for n in NS for mk in MEAS},
        "q_top": QT,
        "SEC-X1": {"normal": x1sum, "deliberately_broken": bx,
                   "note": "재는 것은 «귀무 구현의 1종오류율» 하나뿐 — 분할의 정보량과 무관하다(§4-4)"},
        "_notation": NOTATION_POST7,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    with (ART / "cases.tsv").open("w", encoding="utf-8") as f:
        f.write("# RESULTS_SECTOR_POST7 — 건별 측정값 (기계 생성 · 🔒 판정)\n")
        f.write(f"# 주 판정 갈래 N={MAIN_N} · {MAIN_M} · 창 종료 {END}(발행 2026-09-12 토 휴장 ⇒ "
                f"마지막 거래일 · B-1 · PD-1) · 실행 시 max(date) {SNAP_MAX}(행 {SNAP_ROWS}) · "
                f"시드 {SEED} · post7({POST7_LOG_NO}) 신규 exact «만»\n")
        for ln in NOTATION_POST7:
            f.write("# " + ln.replace("\n", " ") + "\n")
        f.write("#\n")
        f.write("post\titem\tname\tcode\treg\tN\tmeasure\tsector\tpeers\tG\tsec_rank\traw\tpct\treason\n")
        for n in NS:
            for mk in MEAS:
                for it, b in zip(items, BR[(n, mk)]):
                    f.write(f"{it['post']}\t{it['item_no']}\t{it['name']}\t{it['code'] or ''}\t"
                            f"{it['reg']}\t{n}\t{mk}\t{b.get('sector', '')}\t"
                            f"{b.get('peers', '')}\t{b.get('G', '')}\t{b.get('rank', '')}\t"
                            f"{('%.8f' % b['raw']) if b['ok'] else ''}\t"
                            f"{('%.6f' % b['pct']) if b['ok'] else ''}\t{b['reason']}\n")

    (BASE / "RESULTS_SECTOR_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")

    print(f"[시간] 총 {time.time() - t_start:.1f}초 · SEC-X1 {t_x1:.1f}초")
    print("[written] RESULTS_SECTOR_POST7_NUMBERS.md + sector_post7/*.json|tsv")
    print(f"[판정] SEC-P1 = {p1_word} · N1={fmt(n1p, 4)} B1={fmt(b1p, 4)} "
          f"B2={fmt(b2r * 100 if b2r is not None else None)}% · G1={g1_main * 100:.1f}% · "
          f"q_top_max={qmax:.3f} · X1(N1)={x1sum['N1']['lt05'] * 100:.1f}% · "
          f"V1={'갈림' if split else '불갈림'}")
    return 0


def post8_context(cur, ctx):
    """post8 판정 모드의 원장 문맥 — `post7_context` 와 같은 문형(🔴 `db_context()`·`post7_context()` 는 고치지 않는다).

    🔴 두 독립 매핑(`run_ranking.POST8_CODES` ↔ 이 모듈의 `POST8_NEW`)이 «같은지» 대조하고, 다르면 즉시 멈춘다
    (post7 `post7_context` 방식 · 조용한 덮어쓰기 금지 · 새 매핑 0건).
    """
    from run_ranking import POST8_CODES, build_codes8   # 🔴 post8 전용 (기존 import 줄을 고치지 않는다)
    rows = ctx["rows"]                        # `load_ledger("post6")` = 전 행 (필터는 아래 글 필터)
    codes, _ = build_codes8()
    for nm, c, _reg in POST8_NEW:
        if codes.get(nm, c) != c or POST8_CODES.get(nm) != c:
            raise SystemExit(f"🔴 종목코드 충돌: {nm} {codes.get(nm)} / POST8_CODES {POST8_CODES.get(nm)} ↔ {c}")
        codes[nm] = c
    items_all, post_idx = exact_items(rows, codes)
    ap_all = approx_items(rows, codes, post_idx)
    out = dict(ctx)
    out.update(items_all=items_all, ap_all=ap_all, post_idx=post_idx)
    return out


def main_post8(cur, ctx):                                     # noqa: PLR0912, PLR0915
    """🆕 post8 판정 모드 — `main_post7` 을 «복제해 덧붙인» 것이다(`main_post7` 본문은 한 글자도 안 바뀐다).

    post7 과 «다른» 자리(전부 동결 문언에서 나온다 — 값을 보고 고른 것이 아니다):
      ① 창 = `DB_UPTO_POST8` 2026-09-18 = **발행 당일(금 · 거래일) 봉 «포함»**(PD-1) · 이 축은 등록일 당일만 쓴다.
      ② 🆕 `PREREG_POST8.md` 의무 인쇄 — `D-3`(approx 의존 신고) · `D-5`(갈래마다 이름·n·답) · `D-8`(버전 수준) ·
         `D-9`(읽은 시각 · `max/min(updated_at)` · 혼합 빈티지 신고).
      ③ 🔴 **`SEC-P1` 판정 배선 전수 검사**(post7 교훈 ①) — §3 1행 ⛔ 열(`PREREG_SECTOR_COMOVE.md:600`)의
         판정 불가 조건 **6종 전부**(`SEC-G1` · `SEC-V1` · `SEC-X1` · `exact` < 3 · `SEC-B2 ≤ 50%` · `SEC-B1` 발화 불가)을
         `p1` 에 배선한다. 🔴 post6·post7 모드는 **`SEC-X1` 을 `p1` 에 배선하지 않았다**(두 회차 모두 `SEC-X1`
         보정됨이라 판정 이동 0 · 그 모드들은 고치지 않는다 · 이 모드에서만 배선) ⇒ `SEC-X1` 을 §5 «앞»에서 계산한다.
      ④ 🆕 `SEC-V1` 의 «갈렸다» 계수 = `P8-갈래계수`(`PREREG_POST8.md` §5 (나) 2·3 — «최소 n 을 채운 갈래만» 답으로 센다 ·
         모든 갈래 축에 적용). 최소 n = `exact` **3**(`PREREG_SECTOR_COMOVE.md` §3 1행). post7 방식(전 갈래) 읽기도 병기한다.
      ⑤ 우리로(항목 내 2 사이클) = 🔒 #1-(ii) — **포함 · 「우리로 제외」는 «인쇄만»**(판정 효과 없음).
      ⑥ 공통 의무 — post6·post7 판정 표본을 **같은 스냅샷에서 재계산해 나란히** 인쇄(`SEC-X1` 은 비용상 재계산하지 않고 표기).
    """
    t_start = time.time()
    ART = ART_POST8
    ART.mkdir(exist_ok=True)
    from run_ranking import (POST8_BOUNDARY, POST8_MGR_WIN, POST8_PD27_CROSS, P8_LIMIT_LINES, p8_cross_counts,
                             p8_cross_line, p8_d9_rows, p8_prog_levels, p8_read_stamp)

    ctx = post8_context(cur, ctx)
    END = DB_UPTO_POST8
    SNAP_MAX = ctx["END"]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (SNAP_MAX,))
    SNAP_ROWS = int(cur.fetchone()[0])
    si_rows, si_uniq, si_nonnull = ctx["si_rows"], ctx["si_uniq"], ctx["si_nonnull"]
    si_upd, si_sha = ctx["si_upd"], ctx["si_sha"]
    info_rows, info_sector, len_all = ctx["info_rows"], ctx["info_sector"], ctx["len_all"]
    nonnum, final_pseudo, SEC = ctx["nonnum"], ctx["final_pseudo"], ctx["SEC"]

    # 🔴🔴 **명시 필터** — 판정 분모는 **post8 신규 `exact` «만»**(`SEC-D5` · §2-5).
    #     `none` 4건 = ① 신규이나 등록일 미기재 1(원익 · 🔒 #2) ② 기존 건 후속 3(PD-2) — `exact_items()` 가 정의로 뺀다.
    P8IDX = ctx["post_idx"].get(POST8_LOG_NO, POST8_IDX)
    items = [it for it in ctx["items_all"] if it["post"] == P8IDX]
    ap_items = [it for it in ctx["ap_all"] if it["post"] == P8IDX]
    train = [it for it in ctx["items_all"] if it["post"] in TRAIN_POSTS]
    # 🆕 같은 스냅샷 재계산용 — post6·post7 판정 분모(각 글 신규 `exact`)
    P6IDX = ctx["post_idx"].get(POST6_LOG_NO, POST6_IDX)
    P7IDX = ctx["post_idx"].get(POST7_LOG_NO, POST7_IDX)
    prior_items = {6: [it for it in ctx["items_all"] if it["post"] == P6IDX],
                   7: [it for it in ctx["items_all"] if it["post"] == P7IDX]}
    prior_ap = {6: [it for it in ctx["ap_all"] if it["post"] == P6IDX],
                7: [it for it in ctx["ap_all"] if it["post"] == P7IDX]}
    # 🔴 이 글의 «분모 안» §1-5 재진입만 센다 — 글 전체 3건(원익 · 헥토 · 코데즈)은 전부 분모 «밖»(PD-3).
    PD3_IN = {it["code"]: PD3_FLAG_P8[it["code"]] for it in items if it["code"] in PD3_FLAG_P8}
    none_rows = [r for r in ctx["rows"]
                 if r["post_log_no"] == POST8_LOG_NO and r["reg_date_precision"] == "none"]
    bad_log = sorted({it["log_no"] for it in items} - {POST8_LOG_NO})
    if bad_log:
        raise SystemExit(f"🔴 post8 필터가 다른 글을 잡았다: {bad_log}")

    dates = sorted({it["reg"] for it in items})
    all_dates = sorted({it["reg"] for it in items + ap_items})
    train_dates = sorted({it["reg"] for it in train})
    prior_dates = sorted({it["reg"] for p in (6, 7) for it in prior_items[p] + prior_ap[p]})
    DAY = {d: load_day(cur, d, SEC, final_pseudo)
           for d in sorted(set(all_dates) | set(train_dates) | set(prior_dates))}

    # ── 갈래별 측정 · 귀무 (한 함수로 — 갈래·부분표본이 «같은 정의»를 쓰게) ────
    def full_eval(its, n, mk):
        bs = [measure_case(it, n, mk, DAY, SEC) for it in its]
        vals = [b["pct"] for b in bs if b["ok"]]
        posts = [it["post"] for it, b in zip(its, bs) if b["ok"]]
        main_v, pooled = aggregate(vals, posts)
        out = dict(bs=bs, vals=vals, posts=posts, main=main_v, pooled=pooled,
                   N1=None, B1=None, B2=dict(wins=0, n=0, rate=None))
        if not vals:
            return out
        for kind, sname in (("N1", "sec_n1"), ("B1", "sec_b1")):
            pl, _ = pools_for(kind, n, mk, bs, its, DAY)
            if pl and not any(p.size == 0 for p in pl):
                gm, gp = agg_matrix(null_matrix(stream(sname), pl, posts, NREP), posts)
                out[kind] = dict(p_main=float(np.mean(gm >= main_v)),
                                 p_pool=float(np.mean(gp >= pooled)),
                                 ceil_main=float(np.mean(gm >= 100.0 - 1e-9)),
                                 null_med=float(np.median(gm)))
        pb, _ = pools_for("B1", n, mk, bs, its, DAY)
        wins, nb2 = 0, 0
        b2_detail = []
        _mnames = [it["name"] for it, b in zip(its, bs) if b["ok"]]
        for idx, (pool_v, v) in enumerate(zip(pb, vals)):
            if pool_v.size == 0:
                continue
            nb2 += 1
            pm = med(list(pool_v))
            if v > pm:     # 🔴 동률은 «못 넘은 것»(§4-2 · 보수적)
                wins += 1
            b2_detail.append(dict(name=(_mnames[idx] if idx < len(_mnames) else "?"),
                                  value=float(v), pool_med=float(pm),
                                  pool_n=int(pool_v.size), win=bool(v > pm)))
        out["B2"] = dict(wins=wins, n=nb2, rate=(wins / nb2 if nb2 else None),
                         detail=b2_detail)
        return out

    EV = {(n, mk): full_eval(items, n, mk) for n in NS for mk in MEAS}
    BR = {(n, mk): EV[(n, mk)]["bs"] for n in NS for mk in MEAS}
    MAIN = EV[(MAIN_N, MAIN_M)]

    # 🆕 `SEC-X1` 를 §5 «앞»에서 계산한다(③ 배선) — 스트림은 이름으로 결정되므로 계산 순서가 값을 바꾸지 않는다.
    X1_BASE = x1_base_for(items, DAY)
    t_x1 = time.time()
    x1 = x1_run(stream("sec_x1_perm"), stream("sec_x1_null"), X1_REP, dates, DAY, X1_BASE)
    t_x1 = time.time() - t_x1
    x1b = x1_run(stream("sec_x1_bypass_perm"), stream("sec_x1_bypass_null"), X1_REP, dates, DAY,
                 X1_BASE, broken=True)

    def _x1_rate(x1r, kind):
        return float(np.mean(np.array([r[kind] for r in x1r]) < P_THR))

    def _x1_pass(x1r, kind):
        """§6 `x1sum[kind]["pass_"]` 와 «같은 식» — `|z| ≤ 2`(SE = √(p(1−p)/n)). 불일치는 §6 의 assert 가 잡는다."""
        ps = np.array([r[kind] for r in x1r])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        return abs((rate - P_THR) / se) <= 2.0

    # 🆕 `D-9` 읽은 시각 — 이 축이 읽는 창 = 각 등록일 `[D − 20일, D]`(`load_day` 의 `LAG` 창) 의 합집합
    _lo = min((np.datetime64(d) - np.timedelta64(20, "D")).astype(str) for d in DAY if d)
    _hi = max(d for d in DAY if d)
    d9 = p8_read_stamp(cur.connection, ART, (_lo, _hi))
    cross = p8_cross_counts(cur.connection, POST8_PD27_CROSS)
    own_cross = []
    for d in dates:
        _l = (np.datetime64(d) - np.timedelta64(20, "D")).astype(str)
        if _l < POST8_BOUNDARY <= d:
            own_cross.append(d)

    # 🆕 같은 스냅샷 재계산 — post6·post7 주 갈래 성분 · `SEC-V1`(전 갈래 · `P8-갈래계수` 둘 다) · `SEC-B1` 발화
    def qtop_max(ds):
        best = (-1.0, None)
        for d in ds:
            D = DAY[d]
            st = D["st"][MAIN_N]
            lab = D["lab"][MAIN_N]
            pool = [c for c in D["nup"] if st["ok"][D["code_i"][c]]]
            idxs = np.array([D["code_i"][c] for c in pool], dtype=np.int64)
            vidx = np.flatnonzero((lab >= 0) & np.isfinite(D["r"]))
            meds = {int(g): float(np.median(D["r"][vidx][lab[vidx] == g])) for g in np.unique(lab[vidx])}
            top = max(meds, key=lambda g: meds[g])
            q = float(np.sum(lab[idxs] == top) / idxs.size) if idxs.size else float("nan")
            if q > best[0]:
                best = (q, d)
        return best

    def branch_n_map(EVx, its, apx):
        """`P8-갈래계수` 용 갈래별 n(= 측정 가능 건수) — `v1_axis_verdicts` 의 키와 같은 이름."""
        m = {}
        for n in NS:
            m[(1, f"N={n}")] = len(EVx[(n, MAIN_M)]["vals"])
        for mk in MEAS:
            m[(2, mk)] = len(EVx[(MAIN_N, mk)]["vals"])
        m[(3, "글 단위 중앙")] = len(EVx[(MAIN_N, MAIN_M)]["vals"])
        m[(3, "건 pooled 중앙")] = len(EVx[(MAIN_N, MAIN_M)]["vals"])
        m[(4, "`exact` 만")] = len(EVx[(MAIN_N, MAIN_M)]["vals"])
        m[(4, "`approx` 포함")] = (len(full_eval(its + apx, MAIN_N, MAIN_M)["vals"]) if apx
                                   else len(EVx[(MAIN_N, MAIN_M)]["vals"]))
        return m

    def p8_split(VD, nmap):
        counted = {k: v for k, v in VD.items() if nmap.get(k, 0) >= MIN_EXACT}
        return len({str(v) for v in counted.values()}) > 1, counted

    prior_rec = {}
    for p in (6, 7):
        its, apx = prior_items[p], prior_ap[p]
        EVp = {(n, mk): full_eval(its, n, mk) for n in NS for mk in MEAS}
        G1p = {(n, mk): (sum(1 for b in EVp[(n, mk)]["bs"] if not b["ok"]) / len(its) if its else 1.0)
               for n in NS for mk in MEAS}
        Mp = EVp[(MAIN_N, MAIN_M)]
        b2p = Mp["B2"]["rate"]
        V1p = v1_axis_verdicts(EVp, G1p, Mp, G1p[(MAIN_N, MAIN_M)], NS, MEAS, MAIN_N, MAIN_M,
                               its, apx, b2p, full_eval)
        sp8, _cnt = p8_split(V1p["VD"], branch_n_map(EVp, its, apx))
        qm, qd = qtop_max(sorted({it["reg"] for it in its}))
        kp = len(Mp["vals"])
        firep = bool(kp > 0 and binom_ge_half(kp, qm) < P_THR)
        andp = bool(len(its) >= MIN_EXACT and G1p[(MAIN_N, MAIN_M)] < G1_THR and firep
                    and Mp["N1"] is not None and Mp["N1"]["p_main"] < P_THR
                    and Mp["B1"] is not None and Mp["B1"]["p_main"] < P_THR
                    and b2p is not None and b2p > B2_THR)
        prior_rec[p] = dict(n=len(its), k=kp, main=Mp["main"],
                            N1=(Mp["N1"]["p_main"] if Mp["N1"] else None),
                            B1=(Mp["B1"]["p_main"] if Mp["B1"] else None), B2=b2p,
                            B2w=Mp["B2"]["wins"], B2n=Mp["B2"]["n"], G1=G1p[(MAIN_N, MAIN_M)],
                            qtop=qm, qtop_d=qd, fire=firep, and_ok=andp,
                            split_all=bool(V1p["split"]), split_p8=bool(sp8))

    # ══════════════════════════════════════════════════════════════════════
    # §0
    # ══════════════════════════════════════════════════════════════════════
    say("# `SEC-` 섹터 동반 상승 — **post8 판정** 수치 원본 (post8 신규 `exact` «만»)")
    say()
    for ln in NOTATION_POST8:
        say("> " + ln)
    say()
    say("🔴 **이 파일의 판정 분모는 post8 신규 `exact` 건 «뿐»이다** — 훈련(post1~5) 값은 "
        "`SEC-O1`(§4-5) 대로 **§8 에 «나란히»만** 두고 판정 분모에 넣지 않는다.")
    say()
    say("## §0. 실행 문맥")
    say()
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 사전등록 | `PREREG_SECTOR_COMOVE.md` (동결 · `SEC-D1`~`D8` 확정 2026-09-02) |")
    say("| 동결 | `FREEZE_SECTOR_2026-09-03.md` (§0-4 **5번**) · 배선 점검 `RESULTS_SECTOR_DRYRUN.md` |")
    say("| 단계 | `PREREG_SECTOR_COMOVE.md` §0-4 **7번(계산)** — 🔒 **이 값이 판정이다** |")
    say(f"| 대상 글 | `logNo` **{POST8_LOG_NO}** · 발행 **2026-09-18(금 · 거래일)** · "
        "프로그램 **`1.0.42` (업데이트 중)**(PD-8 · 「(업데이트 중)」은 수준에 넣지 않는다) |")
    say("| 실행 브랜치 | `intake/tasso-post8` (🔴 해시는 stdout 전용 — 본문에 박으면 `--rerun` 이 구조적으로 깨진다) |")
    say(f"| 🔴 **창 종료** | **창 종료 `{END}` = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
        "전 축(`WRC-` 포함) · `PREDECISION_2026-09-18_post8.md` PD-1** |")
    say(f"| 🔴 실행 시 `max(date)` | **`{SNAP_MAX}`** · 그 날짜 행수 **{SNAP_ROWS:,}** — "
        "**기록만 한다**(창으로 «쓰지» 않는다 · PD-1 8번 표기 의무) |")
    for _ln in p8_d9_rows(d9):
        say(_ln)
    say("| 창 사용 여부 | ⚠️ 🔴 **이 축은 등록일 «당일»만 쓴다** — `close`·`high` 는 등록일 `D` 봉, `prev_close` 는 "
        "`[D − 20일, D]` 창의 `LAG`(`load_day`) ⇒ 창 종료(09-18)·`ANC-N4` ① 축(`END` 09-18 ↔ 09-17 · 이번 회차엔 "
        "«살아 있다»)이 이 축의 값을 바꾸지 않는다. 🔴 **09-18 봉은 이 축의 계산에 들어가지 않는다**(등록일 최대 "
        "09-11) — 그래도 `D-9` 표기는 박는다. |")
    say(f"| `stock_industry` 스냅샷 (§7-B #22) | **{si_rows:,}행** · 고유 `stock_code` {si_uniq:,} · "
        f"`induty_code` non-NULL {si_nonnull:,} · `max(updated_at)` **{si_upd}** |")
    say(f"| 〃 sha256(전체 `stock_code`↔`induty_code`) | `{si_sha[:32]}…` |")
    say(f"| 〃 동결(2026-09-03) 대비 | "
        f"{'✅ **행 수·`max(updated_at)` 불변**' if (si_rows == 2556 and si_upd.startswith('2026-08-07')) else '🔴 **움직였다**'}"
        " — 🔴 이 표는 시간에 따라 «자란다»(§8-5) |")
    say("| 주 판정 갈래 | 🔒 **`N = 3` · `SEC-M1`** (`SEC-D1`·`D2` · 사장님 확정 2026-09-02) |")
    say(f"| 시드 · 반복 | `{SEED}` · **{NREP:,}회** — ⚠️ `run_selection.py:22` 는 `NREP = 2000` 이다"
        "(§2-3 고지 · 이 축은 «더 큰 쪽»을 쓴다) |")
    say(f"| 시드 스트림 분리 | `SeedSequence({SEED}).spawn()` → `{'`·`'.join(_STREAM_NAMES)}` "
        "(§2-3 «필수» 승계) |")
    say(f"| `SEC-X1` 독립 실현 | **{X1_REP}** (`RESULTS_RANKING_TRAIN.md` §5 «승계») |")
    say(f"| 의사티커 제외 | **{len(final_pseudo)}종** {'·'.join('`%s`' % p for p in final_pseudo)} — "
        f"`run_selection.py:23` `PSEUDO`({len(PSEUDO)}) ∪ DB 실측({len(nonnum)}종) ⇒ "
        f"**{'같다' if set(final_pseudo) == set(PSEUDO) else '🔴 다르다'}**(§5 4번 · §7-B #19) |")
    say("| 유니버스 | `PREREG_RANKING.md` §2-1 승계(`market_cap > 0 ∧ close > 0` · 의사티커 제외) "
        "**∩ 섹터코드 존재**(`SEC-D3`) |")
    say(f"| 🔒 **판정 분모** | post8 신규 `exact` **{len(items)}건** · 등록일 **{len(dates)}일** "
        f"({dates[0]} ~ {dates[-1]}) |")
    say(f"| `approx` (의무 민감도) | **{len(ap_items)}건**"
        + ("" if ap_items else " — 🟢 **0건이므로 「`approx` 포함」 갈래가 「`exact` 만」과 «구조적으로 같은 집합»이다**(모호 아님)")
        + (" — 헥토파이낸셜 · 코데즈컴바인 **「8월말」**(PD-4 · `RNK-D5` 문형 승계: **판정 분모는 `exact` 만** · "
           "`approx` 는 의무 민감도) · 🔴 **원장 `reg_date` 가 비어 있어** 등록일 유니버스를 정할 수 없다 ⇒ "
           "측정에서는 «측정 불가»로 들어간다(post7 처리 그대로 · 규칙을 넓혀 날짜를 «만들지» 않는다)"
           if ap_items else "")
        + " |")
    say(f"| `none` | **{len(none_rows)}건** " + " · ".join(r["stock_name"] for r in none_rows)
        + " — 🔴 **등록일 축 분모 «밖»**(`exact_items()` 가 정의로 뺀다). "
        + f"🔴 **두 부류가 섞여 있다**(PD-4 표): "
        + f"① **신규이나 등록일 미기재** {' · '.join(POST8_NONE_NEW)} — 「9월 3일, 한 차례 매매 후, 다시 … 등록」의 "
          "날짜가 어느 사건에 붙는지 원문이 정하지 않는다 ⇒ **승격하지 않는다**(🔒 #2 · 약한 결정) / "
        + f"② **기존 건 후속** {' · '.join(POST8_FOLLOWUP)} — 그 등록 사건은 **post7 신규 분모에서 "
          "이미 계상됐다**(이중계상 금지 · PD-2 2번) |")
    say("| `after` | **0건**(post8) · 계열 누적 1건 제외 유지(`SEC-D5`) |")
    say(f"| 최소 표본 게이트 | `exact` **{len(items)} ≥ {MIN_EXACT}** ⇒ "
        f"{'🟢 **판정한다**' if len(items) >= MIN_EXACT else '⛔ **미룬다**'} "
        "(`PREREG_SELECTION.md` §7 «차용») |")
    say()
    say("🔴 **`SEC-O1` 자유도 신고** — 잣대 선택(`SEC-D1` `N` 3후보 × `SEC-D2` 측정자 3후보 = **9 조합**)의 "
        "자유도가 이 축의 거의 전부이며, 그 결정은 **2026-09-02**(§0-6)에 동결됐고 배선 점검(09-02)·"
        "동결 커밋(09-03)이 **`fetch_post.py`(post8 · 2026-09-18 19:04:05 KST) «전»**이다"
        "(`PREDECISION_2026-09-18_post8.md` PD-0 · 10 SHA 전부 `origin/main`). "
        "**9 조합을 다 인쇄하되 판정 갈래는 «동결된 하나»뿐이다.** "
        "🔴 **이 실행은 값을 보고 잣대를 하나도 바꾸지 않았다.**")
    say()
    say("| 열 | 뜻 |")
    say("|---|---|")
    say("| 훈련(post1~5) | 🔬 **탐색적 표기** — 판정 분모에 **넣지 않는다**(§8 에만) |")
    say("| 🔒 검증(post8) | **판정** — 이 파일의 §1~§7 전부 |")
    say()
    say("### 0-1. 🆕 `PREREG_POST8.md` 의무 줄 점검표 (이 산출물)")
    say()
    say("| 결정 | 이 산출물에서 | 자리 |")
    say("|---|---|---|")
    say("| `D-1`·`D-2`·`D-4`·`D-7` | 해당 없음 — `ANC-`·`LAD-`·`EXIT-`·`WRC-` 축이 아니다 | — |")
    say("| **`D-3`**(`approx` 의존 신고) | **있음** | §9 |")
    say("| **`D-5`**(갈래마다 이름·n·답) | **있음** — `P8-갈래계수` 로 `SEC-V1` 을 센다 | §7-3 |")
    say("| `D-6`(`ddof`) | 해당 없음 — `n_up` 은 **개수**만 인쇄하고 sd 를 인쇄하지 않는다 | — |")
    say("| **`D-8`**(버전 수준 목록 · 행·글 두 단위) | **있음**(`PREREG_SECTOR_COMOVE.md:1080-1081` 공변량 기록) | §9 |")
    say("| **`D-9`**(①~⑤) | **있음** | §0 · §10 |")
    say("| `D-10`·`D-11`·`D-12` | 해당 없음 — 등급 이름은 **한 개도 적지 않는다** | — |")

    # ══════════════════════════════════════════════════════════════════════
    # §1 분모 · SEC-G1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §1. 분모 · 커버리지 `SEC-G1` (§2-5 · §4-3)")
    say()
    say(f"### 1-1. 건별 — post8 신규 `exact` {len(items)}건")
    say()
    say("| # | 종목 | `stock_code` | 등록일 | `induty_code` | 길이 | `N=3` 칸 | 유니버스 | 섹터표 | 재진입 | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    for it in items:
        c = it["code"]
        D = DAY[it["reg"]]
        ind = SEC.get(c) if c else None
        in_uni = bool(c) and c in set(D["uni"])
        reason = ("①" if not c else ("②" if not in_uni else ("③" if ind is None else "")))
        re_f = PD3_FLAG_P8.get(c)
        re_s = ("—" if re_f is None else f"🔂 `P6-PRIOR_CYCLE`={re_f}")
        if c == POST8_TWO_CYCLE_CODE:
            re_s = "🔀 항목 내 2 사이클(`구조차단`) · §1-5 플래그 0 · 「우리로 제외」 인쇄만(🔒 #1-(ii))"
        say(f"| {it['item_no']} | {it['name']} | `{c or '—'}` | {it['reg']} | `{ind or '—'}` | "
            f"{len(ind) if ind else '—'} | `{ind[:3] if ind else '—'}` | {'✅' if in_uni else '🔴'} | "
            f"{'✅' if ind else '🔴 없음'} | {re_s} | {reason or '—'} |")
    say()
    n_nosec = sum(1 for it in items if not it["code"] or SEC.get(it["code"]) is None)
    nosec_names = [it["name"] for it in items if not it["code"] or SEC.get(it["code"]) is None]
    say(f"- **섹터코드 없는 건 = {n_nosec}건 / {len(items)}**"
        + (f" ({' · '.join(nosec_names)})" if nosec_names else "")
        + " — `PREDECISION_2026-09-18_post8.md` **PD-11** 이 계산 «전»에 적은 «`exact` 4 중 "
        f"섹터코드 3/4 · **액스비스(`0011A0`)만 `stock_industry` 미수록**»과 "
        f"{'🟢 일치한다' if n_nosec == SEC_EXPECT_NOSEC_P8 else '🔴 **어긋난다**'}.")
    say("- 🔴 **`SEC-G1` 은 *「`N`·«측정자별»」* 이다** — 위 수는 **섹터코드 «유무»만** 센 것이고, "
        "아래 §1-2 표가 `SEC-M1`/`M2`/`M3` × `N` **9 조합 각각으로 다시 센다**(PD-11 3번: "
        "***커버리지는 축별로 «다른 수»다***).")
    say("- 🔂 **§1-5 재진입** — 글 전체 **3건**(원익 · 헥토파이낸셜 · 코데즈컴바인 **3번째 사이클** · PD-3) 중 "
        "**판정 분모(`exact`) 안은 %d건**: " % len(PD3_IN)
        + (" · ".join(f"{it['name']}(`{it['code']}`) 직전 사이클 "
                      f"{REENTRY_P8.get(it['code']) or '**미명시**'} · `P6-PRIOR_CYCLE_IN_WINDOW` = "
                      f"**{PD3_FLAG_P8[it['code']]}**"
                      for it in items if it["code"] in PD3_FLAG_P8) or "—")
        + f" ⇒ **판정 분모 안 플래그 합 = {sum(PD3_IN.values())}/{len(items)}**. "
        f"🔴 **글 전체 플래그**: {PD3_NOTE_P8} — ***두 수를 한 수로 합치지 않는다.*** "
        "**분모 포함 + 제외 민감도 의무**(§7-2 · 이번엔 제외 대상 0 ⇒ **항등** 명시). "
        "⚠️ 헥토·코데즈는 재진입 ∧ `approx` 라 **두 민감도가 겹친다** — «따로» 인쇄한다(PD-3 말미). "
        "🔀 **우리로(항목 내 2 사이클 · 측정 등록일 = 사이클 1)** 는 §1-5 재진입이 «아니다»"
        "(`P6-PRIOR_CYCLE_IN_WINDOW` = 0) — 🔒 #1-(ii) **포함 · 「우리로 제외」는 인쇄만**(§7-3).")
    say()
    say("### 1-2. `SEC-G1` — 측정 불가 / `exact` 분모 · **≥ 1/3 ⇒ ⛔ 판정 불가** (§4-3 · `Y3` «차용»)")
    say()
    say("⚠️ **`1/3` 은 «feasible set 공집합 비율»을 재던 문턱이며 커버리지에 대해 검증된 적이 없다** — "
        "`PREREG_POST6.md` §1-6 #6 · `PREREG_RANKING.md` §4-4 의 같은 차용 고지를 승계한다.")
    say()
    say("| 사유 | 설명 | 갈래 의존 |")
    say("|---|---|---|")
    say("| ① | DB 종목코드 부재(레메디형) | 전 갈래 공통 |")
    say("| ② | 유니버스 밖(`market_cap>0 ∧ close>0` 미충족) | 전 갈래 공통 |")
    say("| ③ | 섹터코드 부재(매드업·삼양바이오팜형 · **이번 글 = 액스비스**) | 전 갈래 공통 |")
    say("| ④ | 동료 0 (자기 제외 후 `|P| = 0`) | 🔴 `N` 마다 다르다 |")
    say("| ⑤ | 층에서 미정(`length(induty_code) < N`) | 🔴 `N = 5` 갈래 전용 |")
    say()
    say("| `N` | 측정자 | 측정 가능 | 측정 불가 | 비율 | `SEC-G1`(≥1/3) | 사유별 **건수 · 종목명** |")
    say("|---|---|---|---|---|---|---|")
    G1 = {}
    for n in NS:
        for mk in MEAS:
            bs = BR[(n, mk)]
            bad = [(it, b) for it, b in zip(items, bs) if not b["ok"]]
            rate = len(bad) / len(items)
            G1[(n, mk)] = rate
            by = {}
            for it, b in bad:
                by.setdefault(b["reason"], []).append(it["name"])
            cell = " · ".join(f"{k}:{len(v)}({', '.join(v)})" for k, v in sorted(by.items())) or "—"
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {len(items) - len(bad)}/{len(items)} | {len(bad)} | "
                f"**{rate * 100:.1f}%** | {'🔴 **발동 ⇒ ⛔**' if rate >= G1_THR else '미발동'} | {cell} |")
    say()
    g1_main = G1[(MAIN_N, MAIN_M)]
    say(f"- 🔒 **판정에 쓰는 비율 = 주 갈래(`N = 3` · `SEC-M1`) = {g1_main * 100:.1f}%** ⇒ "
        f"{'🔴 **⛔ `SEC-G1` 발동 — 판정 불가**' if g1_main >= G1_THR else '**미발동 ⇒ 게이트를 연다**'} "
        "(나머지 8 조합은 의무 인쇄 · §4-3 1번).")
    say(f"- 🔬 **훈련 표본 예보는 16.7%** 였다(`FREEZE_SECTOR_2026-09-03.md` §4-2) — 이번 실측 "
        f"**{g1_main * 100:.1f}%**. ⚠️ **예보와 판정은 다른 표본이다**(훈련 {len(train)}건 ↔ 판정 {len(items)}건).")
    say("- 🔴🔴 **편향 방향(그대로 유지) — 이번 글에는 그 편향의 «실물»이 분모 «안»에 있다**: "
        "사유 ③ 은 **신규 상장주에 집중**되고 저자는 신규주를 자주 고른다(§1-5) ⇒ "
        "***측정 불가가 무작위가 아니다.*** **액스비스(`0011A0`)는 우리 DB 첫 봉이 2026-04-13** 이고 "
        "(상장일이 아니다 · PD-11) `stock_industry` 스냅샷(`max(updated_at)` 2026-08-07)·`stock_info`(02-10)에 "
        "**없다** — 🔑 ***이건 「그 종목에 섹터가 없다」가 아니라 「우리 표가 그 종목을 아직 모른다」다.*** "
        "post7 해치텍에 이어 **2회 연속 «분모 안»** 이다. 🔴 `stock_sector_map` PIT 백데이트 결함(2,795행)은 "
        "**기록만** 한다 — 이 축은 `stock_industry` 만 읽는다.")
    say(f"- 🔴 **`N = 5` 갈래**: 측정 불가 **{G1[(5, MAIN_M)] * 100:.1f}%** "
        f"{'⇒ 🔴 **발동**' if G1[(5, MAIN_M)] >= G1_THR else '⇒ 미발동'} — 사전등록 §2-1 이 값 보기 «전»에 "
        "*「4개 글 중 3개에서 판정 불가 · 훈련 전체 61.1%」*로 적어 둔 그 갈래이며, "
        "**구조적 미정 비율을 «항상» 함께 박는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §2 drop_rate
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §2. `drop_rate` **표기 가드** (§5 6-1 · `PREREG_POST6.md` §5-2 «원 용도»)")
    say()
    say("🔴 **`1%` 는 «표시» 문턱이지 «판정» 게이트가 아니다.** "
        "🔑 ***0 이라서 안 재는 게 아니라, 0 임을 매회 «보여서» 이 조항이 살아 있음을 증명한다.***")
    say()
    # 🔴 「한 날에 여러 건」 예시는 **이번 분모에서 실측**한다(직전 글의 등록일을 옮겨 적지 않는다).
    _dupd = sorted(d for d in dates if sum(1 for it in items if it["reg"] == d) >= 2)
    say("⚠️ 🔴 **「5열」이라 적지 않는다 — 이 표는 4열이다.** `PREREG_POST6.md` §5-2 의 5번째 열은 "
        "`prev_bar_date` 인데, **이 축의 §2 표는 «등록일» 행**이고 `prev_close` 는 **종목별 `LAG`** 라 "
        "`prev_bar_date` 가 **행마다 유일하지 않다**"
        + (f"(이번 분모 등록일 {' · '.join('`%s`' % d for d in dates)} 중 한 날에 2건 이상인 날 = "
           + (" · ".join("`%s`(%d건)" % (d, sum(1 for it in items if it["reg"] == d))
                              for d in _dupd) if _dupd else "**없음** — 그래도 `prev_bar_date` 는 "
              "«종목별» 값이라 등록일 행과 1:1 이 아니다") + ")")
        + " ⇒ **4열만 인쇄한다.** 🔑 ***열을 못 채우면 「채운 척」하지 말고 "
          "「왜 못 채우는지」를 적는다.***")
    say()
    say("| 등록일 | 그날 `market_cap>0` | 검정 유니버스 | 탈락 | 탈락률 | 🔴 섹터 조인 «후» 탈락 | "
        "섹터 조인 | 커버리지 | `n_up` ∩ 조인 | S-1 동결함수 일치 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for d in dates:
        D = DAY[d]
        drop = D["raw_n"] - D["frozen_n"]
        rate = drop / D["raw_n"]
        cov = len(D["joined"]) / len(D["uni"]) * 100
        say(f"| {d} | {D['raw_n']:,} | {D['frozen_n']:,} | "
            f"{'🔴 **' + format(drop, ',') + '**' if rate >= DROP_MARK else drop} | "
            f"{rate * 100:.2f}%{' 🔴' if rate >= DROP_MARK else ''} | **{D['prev_miss_join']}** | "
            f"{len(D['joined']):,} | {cov:.2f}% | {len(D['nup'])} | "
            f"{'✅' if D['s1_ok'] else '🔴 차 %d' % D['s1_diff']} |")
    say()
    marked = [d for d in dates if (DAY[d]["raw_n"] - DAY[d]["frozen_n"]) / DAY[d]["raw_n"] >= DROP_MARK]
    n_s1 = sum(1 for d in dates if DAY[d]["s1_ok"])
    n_pm = sum(1 for d in dates if DAY[d]["prev_miss_join"] == 0)
    say(f"- 🔴 **표시가 붙은 날 {len(marked)}일**"
        + (" (" + " · ".join("`%s`" % x for x in marked) + ")" if marked else "")
        + " — 그날의 `n_up` 을 **다른 날과 직접 비교하지 말 것**(원 문언 그대로).")
    say(f"- {'🟢' if n_pm == len(dates) else '🔴'} **섹터 조인 «후» 탈락은 {n_pm}/{len(dates)} 등록일 0** "
        "⇒ `SEC-D7`(종가 대비 수익률)의 정의역에 구멍이 없다(§1-4 재현).")
    say(f"- 🟢 **S-1 배선 확인**: `prev_close` 복제본이 `run_regday_post5.load_universe_day`"
        f"(동결 함수 · **import 해서 호출**)와 **집합으로 같다** — **{n_s1}/{len(dates)} 등록일**"
        f"{' ✅ 전부(차집합 크기 0)' if n_s1 == len(dates) else ' 🔴 어긋난 날이 있다'}.")

    # ══════════════════════════════════════════════════════════════════════
    # §3 건별 측정값
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §3. 건별 측정값 — 🔒 주 판정 갈래 (`N = 3` · `SEC-M1`)")
    say()
    say("🔴 **§2-4 대로 «분모»를 매 건 인쇄한다** — `|P|`(동료 수) · `G`(그날 섹터 수) · "
        "`sec_rank`(자기 섹터 제외 · 동률 전부 위 = 보수적) · **원값**(`med`).")
    say("🔴 **`sec_rank` 에 문턱을 «걸지 않는다»**(§2-2) — `RNK-N2` 의 **30** 은 ≈2,760종목을 재던 값이다.")
    say()
    say("| # | 종목 | 등록일 | 섹터(`N=3`) | `|P|` | `G` | `sec_rank` | 원값 `med` | "
        "**`SEC-M1` 백분위** | 사유 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for it, b in zip(items, BR[(MAIN_N, MAIN_M)]):
        if b["ok"]:
            say(f"| {it['item_no']} | {it['name']} | {it['reg']} | `{b['sector']}` | {b['peers']} | "
                f"{b['G']} | {b['rank']} | {b['raw'] * 100:+.3f}% | **{b['pct']:.1f}** | — |")
        else:
            say(f"| {it['item_no']} | {it['name']} | {it['reg']} | — | {b.get('peers', '—')} | — | — | "
                f"— | ⛔ 측정 불가 | **{b['reason']}** |")
    say()
    mv = MAIN["vals"]
    if mv:
        pk = [b["peers"] for b in BR[(MAIN_N, MAIN_M)] if b["ok"]]
        say(f"- 백분위 범위 **{min(mv):.1f} ~ {max(mv):.1f}** · 동료 수 `|P|` **{min(pk)} ~ {max(pk)}** "
            f"· 동료 0 인 건 **{sum(1 for x in pk if x == 0)}건**(§7-B #26).")
        say(f"- 글 단위 중앙 = **{fmt(MAIN['main'])}** · 건 pooled 중앙 = **{fmt(MAIN['pooled'])}** "
            f"({med_note(len(mv))}).")
        say("- 🔴🔴 **이 글 하나로만 판정하므로 「글 단위 중앙」과 「건 pooled 중앙」이 «구조적으로 같은 양»이다** "
            "— 글이 하나면 「글별 중앙의 중앙」 = 「그 글의 중앙」이다. ⇒ §7 4축의 ③(집계)은 이 글에서 "
            "**«갈릴 수 없다»**(모호가 아니라 정의다). 다음 글부터 갈릴 수 있다.")
    say()
    say("### 3-1. 9 조합 전부 (`SEC-O1` §4-5 — 판정은 «동결된 하나»로만)")
    say()
    say("| `N` | 측정자 | 측정 가능 | 건별 백분위 | **전체(글 단위 중앙)** | 건 pooled 중앙 |")
    say("|---|---|---|---|---|---|")
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | {len(E['vals'])}/{len(items)} | "
                f"{', '.join(f'{v:.1f}' for v in E['vals']) or '—'} | "
                f"**{fmt(E['main'])}** | {fmt(E['pooled'])} |")
    say()
    say("🔒 **판정 갈래 = `N = 3` · `SEC-M1`**(🔒 표시). 나머지 8 조합은 `SEC-V1` 의 «입력»이며 "
        "**판정에 쓰지 않는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §4 귀무·대조
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §4. 귀무 `SEC-N1` · 대칭 대조 `SEC-B1`·`SEC-B2`")
    say()
    say("### 4-0. 추출 풀 한정 손실 (§2-3 — 🔴 «유리한 방향의 처리는 반드시 «크기»를 같이 적는다»)")
    say()
    say("| 갈래 | 풀 | 후보 합계 | 측정 가능 합계 | 한정으로 빠진 수 | 비율 |")
    say("|---|---|---|---|---|---|")
    for n in NS:
        for kind, nm in (("N1", "`SEC-N1` 전 종목"), ("B1", "`SEC-B1` `n_up`")):
            _, loss = pools_for(kind, n, MAIN_M, BR[(n, MAIN_M)], items, DAY)
            tot = sum(a for a, _ in loss)
            keep_n = sum(b for _, b in loss)
            say(f"| `N={n}` | {nm} | {tot:,} | {keep_n:,} | **{tot - keep_n:,}** | "
                + (f"{(tot - keep_n) / tot * 100:.1f}%" if tot else "—") + " |")
    say()
    say("🔴 이 한정은 **저자 쪽에 «유리»한 방향**이다(저자 종목은 전부 동료 ≥ 1). 그래서 크기를 적는다.")
    say()
    say("### 4-1. `SEC-N1` · `SEC-B1` · `SEC-B2` — 9 조합")
    say()
    say(f"귀무 = 각 건의 등록일에 그 풀에서 **무작위 종목 1개** → 같은 측정자·같은 집계 · "
        f"**{NREP:,}회** · 시드 `{SEED}`(스트림 분리) · `p` = `mean(귀무 ≥ 관측)`(등호 포함 · S-5) · "
        "**두 풀 «모두»에서 저자 종목 자신을 뺀다**(M7).")
    say()
    say("🔑 **갈래 사이에는 «공통난수(CRN)»를 쓴다** — 같은 스트림 이름(`sec_n1`·`sec_b1`)을 다시 부르면 "
        "같은 난수열이 나오므로 9 조합이 «같은 추첨»을 공유한다. "
        "🔴 목적이 «다른» 계열(`SEC-X1` 순열·그 안의 귀무)은 §0 대로 **다른 스트림**이다.")
    say()
    say("| `N` | 측정자 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` 승률 | "
        "관측(pooled) | `SEC-N1` `p`(pooled) | `SEC-B1` `p`(pooled) |")
    say("|---|---|---|---|---|---|---|---|---|")
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            if not E["vals"]:
                say(f"| {n}{tag} | `{mk}`{tag} | ⛔ 측정 가능 0건 | — | — | — | — | — | — |")
                continue
            b2 = E["B2"]
            say(f"| {n}{tag} | `{mk}`{tag} | **{fmt(E['main'])}** | "
                f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
                f"**{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}%** "
                f"({b2['wins']}/{b2['n']}) | {fmt(E['pooled'])} | "
                f"{fmt(E['N1']['p_pool'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_pool'], 4) if E['B1'] else '⛔'} |")
    say()
    say("🔴 **매 산출물 의무 문언**(§4-1) — ***`SEC-N1` 은 «`SEC-B1` 없이는» 증거가 아니다.*** "
        "저자 종목은 정의상 급등주이고, 급등주가 섹터 동반성이 높다면 `SEC-N1` 은 그 사실만 되비춘다"
        "(= `REG-M4` 재진술). **정보는 `SEC-B1`·`SEC-B2` 에 있다.**")
    say("🔴 **`SEC-B2` 동률 처리** — 저자 값이 그날 풀 중앙값과 «같으면» **못 넘은 것**으로 센다(보수적).")
    say("")
    say("#### 🔴🔴 `SEC-B2` 의 «비교점» — **50 이 아니라 «그날 `n_up` 풀의 중앙값»이다**")
    say("")
    say("⚠️ 저자 값이 **백분위**라 「50 을 넘었나」로 읽기 쉽지만, `SEC-B2` 가 재는 것은 "
        "***「저자 값 > **그날** 급등주 풀의 중앙값」***이다(§3 5행 정의 축자). "
        "🔑 ***두 비교점은 같은 날에도 크게 다르다*** — 아래 표가 그 차이다.")
    say("")
    say("| 종목 | 등록일 | 저자 값(백분위) | **그날 `n_up` 풀 중앙값** | 풀 크기 | 넘었나 | "
        "(참고) 50 을 넘나 |")
    say("|---|---|---|---|---|---|---|")
    for _d, _it in zip(MAIN["B2"].get("detail", []),
                       [x for x, b in zip(items, MAIN["bs"]) if b["ok"]]):
        say(f"| {_d['name']} | {_it['reg']} | **{_d['value']:.1f}** | "
            f"**{_d['pool_med']:.1f}** | {_d['pool_n']} | "
            + ("🟢 예" if _d["win"] else "🔴 아니오") + " | "
            + ("예" if _d["value"] > 50.0 else "아니오") + " |")
    say("")
    say("🔴 **그러므로 «50 을 넘었다»를 `SEC-B2` 의 근거로 적지 않는다** — "
        "두 잣대가 같은 답을 내는 날도 있고 아닌 날도 있다. "
        "🔒 판정에 쓰는 것은 **그날 풀 중앙값** 쪽 하나뿐이다.")
    say()
    say("### 4-2. 🔴🔴 `SEC-B1` **발화 가능성** — `q_top` 실측 (§4-2 (가) · §7-B #20)")
    say()
    say("🔑 ***「재추출이 성립한다」가 「가드가 발화한다」를 뜻하지 않는다.*** "
        "관측 통계량의 **천장은 100** 이고, 귀무가 그 천장에 **5% 이상**의 질량을 두면 "
        "***어떤 관측으로도 `p < 0.05` 가 나오지 않는다.***")
    say()
    say("🔴 **풀 정의가 둘이다** — ①사전등록 §4-2 (가) 표의 풀 = **`n_up` ∩ 조인** · "
        "②이 표가 쓰는 풀 = 그 위에 **측정 가능(동료 ≥ 1)** 한정. "
        "**①로 구조적 상한(충분조건)을, ②로 실제 발화를 잰다.**")
    say()
    say("⚠️ 🔴 **②열과 `q_top` 은 «날 단위»다 — 건별 «자기 제외»(M7) «전»의 값이다.** "
        "자기 제외가 실제로 걸리는 곳은 **`SEC-B1` 의 추첨 풀**(`pools_for`)이고, 위 §4-1 의 `p` 는 "
        "그 «자기 제외된» 풀로 계산됐다. ⇒ ***이 표의 `q_top` 과 §4-1 의 `p` 는 «분모가 한 건씩 다르다».*** "
        "아래에 **자기 제외까지 넣어 다시 잰 `q_top`** 을 병기해 두 값이 판정을 가르는지 보인다.")
    say()
    say("| 등록일 | ① 풀(`n_up`∩조인) | 고유 섹터 | 최대 섹터 | **최대 점유**(수익률 미사용 충분조건) | "
        "`< 0.135` ? | ② 측정 가능 풀(날 단위) | 🔒 **`q_top`**(1위 섹터 점유 · 문언 정의 · 날 단위) | "
        "(대조) 천장 점유 실측 |")
    say("|---|---|---|---|---|---|---|---|---|")
    QT = {}
    for d in dates:
        D = DAY[d]
        st = D["st"][MAIN_N]
        lab = D["lab"][MAIN_N]
        ix1 = np.array([D["code_i"][c] for c in D["nup"]], dtype=np.int64)
        u1, c1 = np.unique(lab[ix1][lab[ix1] >= 0], return_counts=True)
        share = float(c1.max() / ix1.size)
        pool = [c for c in D["nup"] if st["ok"][D["code_i"][c]]]
        idxs = np.array([D["code_i"][c] for c in pool], dtype=np.int64)
        vidx = np.flatnonzero((lab >= 0) & np.isfinite(D["r"]))
        meds = {int(g): float(np.median(D["r"][vidx][lab[vidx] == g]))
                for g in np.unique(lab[vidx])}
        top = max(meds, key=lambda g: meds[g])
        qtop = float(np.sum(lab[idxs] == top) / idxs.size)
        ceil_share = float(np.mean(st["p1"][idxs] >= 100.0 - 1e-9))
        QT[d] = dict(pool_doc=int(ix1.size), sectors_doc=int(u1.size), maxsec_doc=int(c1.max()),
                     max_share=share, pool_eff=int(idxs.size), qtop=qtop, ceil_share=ceil_share,
                     top=int(top))
        say(f"| {d} | {ix1.size} | {u1.size} | {c1.max()} | **{share:.3f}** | "
            f"{'🟢 예' if share < QTOP_THR else '🔴 아니오'} | {idxs.size} | "
            f"**{qtop:.3f}** | {ceil_share:.3f} |")
    say()
    n_suff = sum(1 for d in dates if QT[d]["max_share"] >= QTOP_THR)
    qmax = max(QT[d]["qtop"] for d in dates)
    qmax_d = max(dates, key=lambda d: QT[d]["qtop"])
    say(f"- 구조적 **충분조건**(최대 단일섹터 점유 `< 0.135`)이 **{len(dates) - n_suff}/{len(dates)} 등록일**에서 "
        f"성립하고 **{n_suff}일**에서 실패한다. 🔴 **「충분조건 실패」는 「`q_top ≥ 0.135`」의 «증명»이 아니다**"
        "(§7-A #8-1 · `FREEZE_SECTOR_2026-09-03.md` §3 ②: ***상한으로 「불가능」을 선언하지 마라***).")
    say(f"- 🔒 **실측 `q_top` 최대 = {qmax:.3f}**(`{qmax_d}`) · "
        + ("🟢 **전 등록일 `< 0.135`**" if qmax < QTOP_THR else "🔴 **`≥ 0.135` 인 날이 있다**") + ".")
    say()
    # 🔴 자기 제외(M7)까지 넣은 `q_top` — `SEC-B1` 이 «실제로» 뽑는 풀과 같은 정의로 다시 잰다.
    qself = []
    for it, b in zip(items, BR[(MAIN_N, MAIN_M)]):
        if not b["ok"]:
            continue
        D = DAY[it["reg"]]
        st = D["st"][MAIN_N]
        lab = D["lab"][MAIN_N]
        pc = [c for c in D["nup"] if st["ok"][D["code_i"][c]] and c != it["code"]]
        if not pc:
            continue
        ix = np.array([D["code_i"][c] for c in pc], dtype=np.int64)
        qself.append((float(np.sum(lab[ix] == QT[it["reg"]]["top"]) / ix.size), it["name"]))
    qmax_self = max(q for q, _ in qself) if qself else float("nan")
    qmax_self_nm = max(qself)[1] if qself else "—"

    kmain = len(MAIN["vals"])
    kposts = len(set(MAIN["posts"])) if MAIN["posts"] else 0
    say("🔒 **발화 조건(동결 · §4-2 (가))** = `P(Binom(k, q_top) ≥ ⌈k/2⌉) < 0.05`. "
        "`q_top` 이 등록일마다 다르므로 **판정 분모의 등록일 중 «최대»**(= 가장 불리한 쪽, 보수적)를 쓴다.")
    say()
    say("| `k` | 뜻 | `q_top`(최대) | `P(Binom(k, q_top) ≥ ⌈k/2⌉)` | 판정 |")
    say("|---|---|---|---|---|")
    fire = {}
    for k, lbl in ((MIN_EXACT, "🔒 사전등록 최소 표본(`PREREG_SELECTION.md` §7)"),
                   (kmain, "🔒 **이 판정의 집계 표본 수**(측정 가능 `exact` 건 = 글 단위 중앙의 분모)"),
                   (kposts, "글 수 (⚠️ 글이 하나뿐이라 «집계의 표본 수»가 아니다 — 아래 주석)")):
        pv = binom_ge_half(k, qmax) if k > 0 else float("nan")
        fire[k] = bool(pv < P_THR)
        say(f"| {k} | {lbl} | {qmax:.3f} (`{qmax_d}`) | **{pv:.4f}** | "
            + ("🟢 발화 가능" if pv < P_THR else "🔴 **⛔ 발화 불가**") + " |")
    say()
    say("⚠️ 🔴 **모호 지점(양쪽 인쇄 · 값 보고 규칙 바꾸지 않는다)** — 사전등록 §4-2 (가)의 `k` 는 "
        "*「관측 통계량(중앙값)의 표본 수」*로 쓰였고 배선 점검은 세 값을 나란히 인쇄했다. "
        f"**이 글 하나로만 판정하는 지금, 글 단위 중앙값을 만드는 표본은 «건 수»({kmain})이지 "
        f"«글 수»({kposts})가 아니다.** 🔒 **판정은 «건 수» 행으로 한다.** "
        + ("🟢 **세 `k` 가 전부 같은 방향이라 이 모호는 판정을 가르지 않는다.**"
           if len(set(fire.values())) == 1 else
           "🔴 **세 `k` 가 갈린다 ⇒ 보수적(발화 불가) 쪽을 쓴다.**"))
    b1fire = fire[kmain] if kmain > 0 else False
    if len(set(fire.values())) > 1:
        b1fire = all(fire.values())
    # 🔴 자기 제외(M7) 정의로 다시 잰 `q_top` 을 «병기»한다 — 문턱도 판정 갈래도 바꾸지 않는다.
    fire_self = {k: binom_ge_half(k, qmax_self) < P_THR for k in (MIN_EXACT, kmain, kposts) if k > 0}
    say(f"- 🔴 **자기 제외(M7)까지 넣어 다시 잰 `q_top`(= `SEC-B1` 이 «실제로» 뽑는 풀과 같은 정의)** "
        f"= 건별 최대 **{qmax_self:.4f}**(`{qmax_self_nm}`) ↔ 위 표의 날 단위 최대 **{qmax:.4f}**. "
        f"자기를 빼면 분모가 하나 줄어 **약간 커진다**(보수적 방향). "
        f"🟢 **세 `k`(**{MIN_EXACT}·{kmain}·{kposts}**) 판정이 두 정의에서 «전부 동일»하다 — "
        f"{'전부 발화 가능' if all(fire_self.values()) and all(fire.values()) else '🔴 갈린다 ⇒ 보수적 쪽을 쓴다'}"
        f"**(`P(Binom({kmain}, {qmax_self:.4f}) ≥ {-(-kmain // 2)})` = "
        f"{binom_ge_half(kmain, qmax_self):.2e}). ⇒ ***이 구분은 발화 판정을 가르지 않는다.***")
    ceil_obs = MAIN["B1"]["ceil_main"] if MAIN["B1"] else None
    say(f"- 🟢 **직접 실측(대조)**: `SEC-B1` 귀무 {NREP:,}회에서 **집계 통계량이 천장(100)에 둔 질량 = "
        f"{fmt(ceil_obs, 4)}** — 문언 정의의 이항 산술과 같은 방향인지 여기서 볼 수 있다. "
        "🔴 **판정은 문언 정의(위 표)로 한다**(S-7).")
    say("- ⇒ 🔒 **`SEC-B1` 발화 " + ("가능**" if b1fire else "**불가** ⇒ ⛔**")
        + " — " + ("문턱을 낮춰 열지 않는다."
                   if b1fire else "🔴 **`SEC-P1` 도 열리지 않는다**(AND). 문턱을 낮춰 열지 않는다."))

    # ══════════════════════════════════════════════════════════════════════
    # §5 SEC-P1 / SEC-P2
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §5. 🔒 `SEC-P1` — **3중 AND** 판정 (§3 1행) · `SEC-P2`")
    say()
    say("🔴 **`SEC-P1` = `SEC-N1 < 5%` ∧ `SEC-B1 < 5%` ∧ `SEC-B2 > 50%`.** "
        "🔴 **모든 ✅ 에는 ⛔ 가 있다** — 아래 표는 성분마다 ⛔ 경로를 같이 적는다.")
    say()
    n1p = MAIN["N1"]["p_main"] if MAIN["N1"] else None
    b1p = MAIN["B1"]["p_main"] if MAIN["B1"] else None
    b2r = MAIN["B2"]["rate"]
    c_n1 = (n1p is not None) and (n1p < P_THR)
    c_b1 = (b1p is not None) and (b1p < P_THR)
    c_b2 = (b2r is not None) and (b2r > B2_THR)
    say("| 성분 | 문턱 (출처 파일) | 관측 | 통과 | ⛔ 경로 |")
    say("|---|---|---|---|---|")
    # 🔴 소수 넷째 자리로 반올림하면 `SEC-N1` 과 `SEC-B1` 이 «같아 보인다» —
    #    실제로는 다른 값이다. ⇒ **재추출 «횟수» 정수를 같이 인쇄**해 착시를 막는다.
    _n1_hits = None if n1p is None else int(round(n1p * NREP))
    _b1_hits = None if b1p is None else int(round(b1p * NREP))
    say(f"| `SEC-N1` | `p < 5%` · `PREREG_REGDAY_MEASURE.md` §4-1 | "
        f"**{fmt(n1p, 5)}** (= **{_n1_hits}**/{NREP:,}) | "
        + ("🟢 통과" if c_n1 else "🔴 미달")
        + " | ≥ 5% ⇒ 불성립 · 해석/재추출 갈림 ⇒ `SEC-V1` |")
    say(f"| `SEC-B1` | `p < 5%` · 〃 | **{fmt(b1p, 5)}** (= **{_b1_hits}**/{NREP:,}) | "
        + ("🟢 통과" if c_b1 else "🔴 미달")
        + " | ≥ 5% ⇒ 🔴 **「급등주 일반 성질과 구분 불가」로 강등** · `q_top ≥ 0.135` ⇒ 발화 불가"
        + f"(이번: {'발화 가능' if b1fire else '🔴 발화 불가'}) |")
    say(f"| `SEC-B2` | **> 50%** · `RESULTS_D1_OOS_POST5.md` §9 W7 «차용» | "
        f"**{fmt(b2r * 100 if b2r is not None else None)}%** ({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | "
        + ("🟢 통과" if c_b2 else "🔴 미달")
        + " | ≤ 50% ⇒ **즉시 「구분 불가」**(등호 포함 = 강등) |")
    say()
    say("| 선행 게이트 | 문턱 (출처) | 이번 | 판정 |")
    say("|---|---|---|---|")
    say(f"| `exact` 최소 표본 | ≥ {MIN_EXACT} · `PREREG_SELECTION.md` §7 | **{len(items)}** | "
        + ("🟢 열림" if len(items) >= MIN_EXACT else "⛔ 미룸") + " |")
    say(f"| `SEC-G1` 커버리지 | < 1/3 · `RESULTS_RECONSTRUCT_POST4.md` §6 Y3 | **{g1_main * 100:.1f}%** | "
        + ("🟢 열림" if g1_main < G1_THR else "🔴 ⛔ 판정 불가") + " |")
    say(f"| `SEC-B1` 발화 가능성 | `P(Binom) < 0.05` · §4-2 (가) | "
        f"**{binom_ge_half(kmain, qmax) if kmain else float('nan'):.4f}** | "
        + ("🟢 열림" if b1fire else "🔴 ⛔ 발화 불가") + " |")
    gates_ok = (len(items) >= MIN_EXACT) and (g1_main < G1_THR) and b1fire
    and_ok = bool(gates_ok and c_n1 and c_b1 and c_b2)
    # 🔴 §3 1행의 ⛔ 열이 `SEC-V1` 을 «판정 불가 조건»으로 열거한다
    #    (`PREREG_SECTOR_COMOVE.md:600`). §7 은 §3 «뒤»에 인쇄되므로 갈림 여부만 앞에서 계산한다.
    #    🔒 적용 범위(`:815-817`) = 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」뿐이고 «§3 AND 안 한 항목
    #    미달» 사건에는 관여하지 않는다. 🆕 정정 1차(S-2): 주 갈래 AND 가 거짓이어도 최소 n 을 채운 다른 잣대에서
    #    «성립»이 나오면 그건 AND 미달이 아니라 잣대 갈림이다 ⇒ `split ∧ (and_ok ∨ 성립 갈래 존재)` 이면 ⛔.
    V1PRE = v1_axis_verdicts(EV, G1, MAIN, g1_main, NS, MEAS, MAIN_N, MAIN_M,
                             items, ap_items, b2r, full_eval)
    v1_split_pre = bool(V1PRE["split"])                      # post7 방식 — 전 갈래
    NMAP = branch_n_map(EV, items, ap_items)
    v1_split_p8, V1_COUNTED = p8_split(V1PRE["VD"], NMAP)     # 🆕 `P8-갈래계수` — 최소 n 을 채운 갈래만
    v1_any_ok = any(v is True for v in V1_COUNTED.values())  # 🆕 정정 1차(S-2) — «성립» 갈래 존재
    # 🆕 `SEC-X1` 도 §3 1행 ⛔ 열의 판정 불가 조건이다(`:600`) — post6·post7 모드는 배선하지 않았다.
    x1_ok = x1_ok_pre = bool(_x1_pass(x1, "N1") and _x1_pass(x1, "B1"))
    p1_blocked_v1 = bool(v1_split_p8 and (and_ok or v1_any_ok))
    # 🆕 정정 1차(S-1) — `SEC-X1` 이탈은 AND 와 «무관하게» 축을 닫는다(`PREREG_SECTOR_COMOVE.md:797-798` ·
    #    `:895` 「`SEC-P1` 전체 · ⛔ 열리지 않는다」) — 초판 `and_ok ∧ ¬x1_ok` 는 동결보다 좁았다(이번 판정 이동 0).
    p1_blocked_x1 = bool(not x1_ok_pre)
    p1_blocked = bool(p1_blocked_v1 or p1_blocked_x1)
    p1_ok = bool(and_ok and not v1_split_p8 and x1_ok_pre)
    p1_label = "⛔ 판정 불가" if p1_blocked else ("✅ 성립" if p1_ok else "🔴 불성립")
    p1_word = "판정 불가" if p1_blocked else ("성립" if p1_ok else "불성립")
    say()
    say("#### 🆕 판정 배선 전수 검사 — §3 1행 ⛔ 열(`PREREG_SECTOR_COMOVE.md:600`)의 조건 6종 → `SEC-P1`")
    say()
    say("| ⛔ 조건 | 이번 값 | 가드 발화 | `SEC-P1` 에 배선 | 배선 자리 |")
    say("|---|---|---|---|---|")
    say(f"| `exact` < 3 | {len(items)} | {'🔴 발화' if len(items) < MIN_EXACT else '미발화'} | ✅ | `gates_ok` |")
    say(f"| `SEC-G1` ≥ 1/3 | {g1_main * 100:.1f}% | {'🔴 발화' if g1_main >= G1_THR else '미발화'} | ✅ | `gates_ok` |")
    say(f"| `SEC-B1` 발화 불가 | `P(Binom)` = {binom_ge_half(kmain, qmax) if kmain else float('nan'):.4f} | "
        f"{'🔴 발화' if not b1fire else '미발화'} | ✅ | `gates_ok` |")
    say(f"| `SEC-B2` ≤ 50% | {fmt(b2r * 100 if b2r is not None else None)}% | "
        f"{'🔴 발화' if not c_b2 else '미발화'} | ✅ | `and_ok`(성분) |")
    say(f"| `SEC-V1` 갈림(🆕 `P8-갈래계수`) | 전 갈래 {'갈림' if v1_split_pre else '불갈림'} · 최소 n 갈래 "
        f"{'갈림' if v1_split_p8 else '불갈림'} | {'🔴 발화' if v1_split_p8 else '미발화'}"
        + ("" if (p1_blocked_v1 or not v1_split_p8) else
           " — 🔒 **단 주 갈래 AND 가 거짓이고 «성립» 갈래가 없어 적용 범위 밖**(`:815-817` · §3 우선순위표)")
        + " | ✅ | `p1_blocked_v1 = split(P8) ∧ (and_ok ∨ 성립 갈래 존재)` |")
    say(f"| `SEC-X1` 절차 무효 | `p<0.05` N1 {_x1_rate(x1, 'N1') * 100:.1f}% · B1 {_x1_rate(x1, 'B1') * 100:.1f}% | "
        f"{'🔴 발화' if not x1_ok_pre else '미발화'} | ✅ 🆕 | `p1_blocked_x1 = ¬x1_ok`(AND 와 무관 · `:797-798`·`:895`) |")
    say()
    say("🔴 **post7 교훈 ① 적용** — 가드가 발화했는데 판정에 배선되지 않은 자리가 **없다**(위 6행 전부 ✅). "
        "🔴 **정직 신고**: post6·post7 모드는 `SEC-X1` 을 `SEC-P1` 에 배선하지 **않았다**(두 회차 모두 `SEC-X1` "
        "보정됨 — post6 `z` −1.95/−1.62 · post7 +0.32/+0.97 ⇒ **판정 이동 0**) — 그 모드들은 고치지 않는다(동결 산출물 "
        "byte 불변). 🔑 `SEC-V1` 은 갈림이 있고 «주 갈래 AND 참 ∨ 최소 n 갈래 중 «성립» 존재»일 때 ⛔ 로 간다"
        "(적용 범위 `:815-817` — AND 안 한 항목 미달엔 관여하지 않되, 다른 잣대의 «성립»은 잣대 갈림이다 · 정정 1차 S-2) · "
        "`SEC-X1` 은 AND 와 무관하게 ⛔ 로 간다(정정 1차 S-1).")
    say()
    say("### 🔒 판정 — `SEC-P1` : **"
        + ("⛔ 판정 불가(" + " · ".join(x for x, f in (("`SEC-V1` 발동", p1_blocked_v1), ("`SEC-X1` 절차 무효", p1_blocked_x1)) if f) + ")"
           if p1_blocked else ("✅ 성립" if p1_ok else "🔴 불성립(지지 아님)")) + "**")
    say()
    if p1_blocked and not and_ok:
        # 🆕 정정 1차 — S-1·S-2 로 AND 가 거짓인 사건도 ⛔ 로 갈 수 있다(이번 회차엔 미실행 분기)
        say("🔴 **3중 AND 는 주 갈래에서 «거짓»이다** — 그러나 아래 조건이 판정을 닫아 **«불성립»도 선언하지 않는다**: "
            + " · ".join(x for x, f in (("`SEC-V1`(다른 잣대에서 «성립» · 잣대 갈림)", p1_blocked_v1),
                                         ("`SEC-X1` 절차 무효", p1_blocked_x1)) if f) + ".")
        say()
    elif p1_blocked:
        say("🔴 **3중 AND 는 주 갈래(`N = 3` · `SEC-M1` · 글 단위 중앙 · `exact` 만)에서 «통과»했다** — "
            f"`SEC-N1` **{fmt(n1p, 5)}** · `SEC-B1` **{fmt(b1p, 5)}** · "
            f"`SEC-B2` **{fmt(b2r * 100 if b2r is not None else None)}%** "
            f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}). "
            "🔴 **그러나 이것은 «기록»이지 «선언»이 아니다.**")
        say()
        if p1_blocked_v1:
            say("🔒 `PREREG_SECTOR_COMOVE.md` §3 1행의 ⛔ 열이 `SEC-V1` 을 **판정 불가 조건**으로 "
                "열거하고(`:600`), §6 가 *「`SEC-V1` — **4축**(§4-6) 중 하나가 갈림 ⇒ "
                "**갈리지 않는 글이 온다**(잣대를 넓혀 열지 않는다)」*라고 못박는다(`:896`). "
                "이번 갈림은 🆕 **`P8-갈래계수`(최소 n 을 채운 갈래만)로 세어도** 갈린다(§7-3) — 주 갈래 AND 는 참인데 "
                "다른 잣대에서 판정이 다르다. ⇒ ***이번 글에서는 어느 쪽도 선언하지 않는다.***")
        if p1_blocked_x1:
            say("🔒 `SEC-X1`(순열 대조군 1종오류율)이 명목 5%와 어긋났다(`|z| > 2`) ⇒ §6 *「`SEC-X1` — 순열 대조군의 "
                "1종오류율 이탈 ⇒ ⛔ 열리지 않는다 · 구현을 고친 뒤 새 사전등록으로만」* ⇒ ***선언하지 않는다.***")
        say()
        say("🔴🔴 **「계열 최초 성립」이라고 쓰지 않는다** — 성립을 «선언»한 적이 없다. "
            "쓸 수 있는 문장은 ***「3중 AND 는 통과했으나 "
            + " · ".join(x for x, f in (("`SEC-V1`", p1_blocked_v1), ("`SEC-X1`", p1_blocked_x1)) if f)
            + " 때문에 선언 불가 — 조건이 풀리는 글이 오면 판정한다」*** 하나뿐이다. "
            "🔒 문턱을 낮추거나 갈래를 새로 만들어 여는 것은 §6 가 금지한다.")
        say()
        say("🔴 **판정 불가의 뜻도 「테마가 아니다」가 «아니다»**"
            "(§0-2 2번 · 거짓 음성이 구조적이다).")
    elif p1_ok:
        say("🔴 **성립의 뜻은 「섹터 동반성이 존재한다」까지다** — *「테마로 고른다」*의 **확증이 아니다**"
            "(§0-2 천장 · 에코프로 4종목이 KSIC 에서 «세 칸»으로 흩어진다). "
            "그리고 승/패 대조가 미실시이므로 **이 축의 최대치는 「기술」**이다(§0-2 ③).")
    else:
        miss = [nm for nm, ok in (("`SEC-N1`", c_n1), ("`SEC-B1`", c_b1), ("`SEC-B2`", c_b2)) if not ok]
        say("🔴 **AND 가 거짓이다** — 미달 성분: "
            + (" · ".join(miss) if miss else "선행 게이트")
            + ". ⇒ §3 우선순위표대로 **§3 이 판정한다(지지 아님)** · §4-2 는 «인쇄 문언» · "
              "§4-6 은 «민감도 전용»이다.")
        if c_n1 and not c_b1:
            say("🔴 **`SEC-N1` 만 통과한 것을 지지로 인용하지 않는다** — 그 조합의 뜻은 "
                "*「저자가 급등주를 고른다」*이고 그건 `REG-M4` 가 이미 말한 것이다(§2-3 · §4-1). "
                "🔒 인쇄 문언(§4-2) = ***「저자 종목의 섹터 동반성이 같은 날 다른 급등주와 다르지 않다」***.")
        say("🔴 **불성립의 뜻은 「KSIC 섹터 동반상승으로는 안 잡힌다」까지다 — 「테마가 아니다」가 아니다**"
            "(§0-2 2번 · 거짓 음성이 구조적이다).")
    say()
    say("### `SEC-P2` — 글을 넘는 반복 (**기록만** · 검정 통계량 아님)")
    say()
    say("| 글 | 판정 | 누계 |")
    say("|---|---|---|")
    say(f"| post6 (옮겨 적은 값) | **불성립** | 성립 0 / 판정 1 |")
    say(f"| post7 (옮겨 적은 값) | **판정 불가**(`SEC-V1` 발동 · 누계 분모 밖) | "
        f"성립 {SEC_P2_PRIOR_P8['n_support']} / 판정 {SEC_P2_PRIOR_P8['n_judgements']} |")
    n_judg_p8 = SEC_P2_PRIOR_P8["n_judgements"] + (0 if p1_blocked else 1)
    say(f"| **post8 (`{POST8_LOG_NO}`)** | **{p1_word}**"
        + ("(⛔ · §3 1행 ⛔ 열)" if p1_blocked else "") + " | 성립 "
        f"**{SEC_P2_PRIOR_P8['n_support'] + (1 if p1_ok else 0)}** / 판정 "
        f"**{n_judg_p8}** |")
    if p1_blocked:
        say()
        say("🔴 **post8 은 «판정»이 아니라 «판정 불가»이므로 누계 분모(판정 수)에 넣지 않는다** — "
            "3중 AND 통과는 위 §3 에 **기록**으로 남기되 `SEC-P2` 의 부호 누계에는 **성립으로도 "
            "불성립으로도 세지 않는다**(§6 *「갈리지 않는 글이 온다」*).")
    say()
    say("🆕 **누계를 «이어간다»**(🔒 결정 ⑥) — post6·post7 판정 «라벨»은 `RESULTS_SECTOR_POST6/7_NUMBERS.md` 에서 "
        "**옮겨 적은 상수**다(동결 산출물 byte 불변). 🔴 **같은 스냅샷 재계산 값은 §8-1 에 «나란히»** 둔다 — "
        "재계산이 라벨을 바꾸면 그 사실을 거기 인쇄한다(누계는 옮겨 적은 라벨로 잇는다 · 고쳐 쓰지 않는다).")
    say("🔴 **누계를 검정 통계량으로 쓰지 않는다**(`RESULTS_D1_OOS_POST5.md` §8 승계) — "
        "**매 글 독립 판정 + 부호 누계**만 적고 **글별 `p` 를 곱하거나 더하지 않는다**(§2-6).")

    # ══════════════════════════════════════════════════════════════════════
    # §6 SEC-X1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §6. `SEC-X1` 섹터 라벨 **순열 대조군** — 귀무 «구현»의 1종오류율 (§4-4 · `SEC-D6`)")
    say()
    say("🔴🔴 **이 가드가 재는 것은 «귀무 구현의 1종오류율 보정» 하나뿐이다** — "
        "*「칸막이가 정보인가」를 재는 검정이 «아니다»*(§4-4 B-2). 라벨을 섞으면 저자와 귀무가 "
        "**교환 가능**해지므로 ***참 분할이 정보를 담든 잡음이든 `P(p<0.05)` 는 «항상» 5% 다.***")
    say("🔴 **`SEC-X1` 통과를 「섹터가 의미 있다」로 인용하지 않는다** — 그건 `SEC-B1`·`SEC-B2` 가 잰다.")
    say()
    # 🔴 `x1`·`x1b` 는 §5 «앞»에서 이미 계산했다(판정 배선 ③ · 스트림 이름으로 결정 ⇒ 순서 무관).
    say(f"**명세**: 그날 유니버스의 `induty_code` 를 종목 사이에서 무작위로 «섞고»(집단 크기 분포 보존) "
        f"같은 측정자(`SEC-M1` · `N=3`)·같은 귀무를 계산 — **독립 실현 {X1_REP}개** × 귀무 {NREP:,}회.")
    say()
    say("| 풀 | 실현 수 | `p` 평균 | `p` 중앙 | **`p < 0.05` 비율** | `p < 0.20` 비율 | "
        "명목 대비(SE ≈ 1.5%p) | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    x1sum = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        ok = abs(z) <= 2.0
        x1sum[kind] = dict(n=len(ps), mean=float(ps.mean()), median=float(np.median(ps)),
                           lt05=rate, lt20=float(np.mean(ps < 0.20)), z=float(z), pass_=bool(ok))
        say(f"| `SEC-{kind}` | {len(ps)} | {ps.mean():.4f} | {np.median(ps):.4f} | "
            f"**{rate * 100:.1f}%** | {np.mean(ps < 0.20) * 100:.1f}% | "
            f"`z = {z:+.2f}` | " + ("🟢 **보정됨**" if ok else "🔴 **⛔ 절차 무효**") + " |")
    say()
    x1_ok = x1sum["N1"]["pass_"] and x1sum["B1"]["pass_"]
    assert x1_ok == x1_ok_pre, ("SEC-X1 배선 불일치", x1_ok, x1_ok_pre)
    say(f"- 순열 하 `p` 는 이론상 `U(0,1)` 이므로 `p<0.05` 비율의 기대는 **5.0%**, "
        f"{X1_REP} 실현의 SE ≈ **1.5%p** 다(§4-4). `|z| ≤ 2` 를 «어긋나지 않음»으로 읽는다.")
    if min(x1sum[k]["lt05"] for k in ("N1", "B1")) < P_THR:
        say("- 🔴 **방향은 근거로 쓰지 않는다**(정정 1차 S-3) — 이번 `p<0.05` 비율은 명목 5%보다 «아래»"
            f"(**{x1sum['N1']['lt05'] * 100:.1f}%** · **{x1sum['B1']['lt05'] * 100:.1f}%**)지만 `|z| ≤ 2` 라 "
            "**«보정됨»**이다 — 판정은 그것뿐이다. 음수 `z` 는 과소기각 = 검정력 손실 쪽이라 오히려 «불성립» 쪽 "
            "거짓 음성 위험이고, 다른 시드에서는 양수도 나온다(post7 `z` +0.32/+0.97) ⇒ ***부호로 판정의 안전을 말하지 "
            "않는다.*** 🔴 초판의 「이번 «불성립» 판정을 위협하지 않는다」는 방향 해석이 거꾸로였다.")
    say("- ⇒ 🔒 **`SEC-X1` : "
        + ("🟢 보정됨 ⇒ 절차 유효**" if x1_ok else "🔴 ⛔ 절차 무효 — 이 축을 닫는다**")
        + " (어긋나면 구현을 고친 뒤 **새 사전등록**으로만 연다 · §6).")
    say(f"- 🔴 순열 실현에서 저자 건이 «측정 불가»가 되는 일(섞인 뒤 `|P| = 0`)이 실현당 평균 "
        f"**{np.mean([r['drop'] for r in x1]):.2f}건** 있다. 크기 정합을 위해 그 건은 "
        "관측·귀무 «양쪽»에서 같이 빠진다.")
    say()
    say("### 6-1. 🔴 **가드를 «일부러» 켜서 발동을 실증한다** (§7-B #20 · `x1_bypass` 형식 승계)")
    say()
    say("🔑 ***「조항을 적었다」가 「그 조항이 발동한다」를 뜻하지 않는다*** — **귀무 구현을 «고장내고»**"
        "(추출 풀에서 상위 절반 백분위를 통째로 제거 ⇒ 교환가능성 파괴) 같은 순열 대조군을 돌린다. "
        "가드가 살아 있다면 1종오류율이 5%에서 «어긋나야» 한다.")
    say()
    say("| 귀무 구현 | `p < 0.05` 비율 | `z` | `SEC-X1` 판정 |")
    say("|---|---|---|---|")
    say(f"| 🟢 정상(위 §6 `SEC-N1`) | **{x1sum['N1']['lt05'] * 100:.1f}%** | "
        f"`{x1sum['N1']['z']:+.2f}` | "
        + ("🟢 보정됨 ⇒ 절차 유효" if x1sum["N1"]["pass_"] else "🔴 절차 무효") + " |")
    bx = {}
    for kind in ("N1", "B1"):
        ps = np.array([r[kind] for r in x1b])
        rate = float(np.mean(ps < P_THR))
        se = (P_THR * (1 - P_THR) / len(ps)) ** 0.5
        z = (rate - P_THR) / se
        bx[kind] = dict(lt05=rate, z=float(z), fired=bool(abs(z) > 2.0))
        say(f"| 🔴 **일부러 고장낸 것**(`SEC-{kind}` 풀 상위 절반 제거) | **{rate * 100:.1f}%** | "
            f"`{z:+.2f}` | "
            + ("🔴 **⛔ 절차 무효 — 가드 발동 ✅**" if abs(z) > 2.0 else "🟡 미발동") + " |")
    say()
    say("🆕 **`z` 부호 주시**(보고서 §6 #6 계열) — 정상 구현 `z` 는 post6 **−1.95**(`SEC-N1`)로 "
        "**경계(|z| > 2.0)에 붙어 있었고** post7 은 **+0.32**·**+0.97** 이었다. 이번 실측 정상 `z` = "
        f"**`{x1sum['N1']['z']:+.2f}`**(`SEC-N1`) · **`{x1sum['B1']['z']:+.2f}`**(`SEC-B1`) ⇒ "
        + ("🔴 **경계를 넘었다 — `SEC-X1` 이 정상 구현에서 발동한다**"
           if (abs(x1sum['N1']['z']) > 2.0 or abs(x1sum['B1']['z']) > 2.0)
           else "🟡 **아직 경계 안**") + ". "
        "🔴 **부호를 함께 적는다** — |z| 만 적으면 「보수적으로 어긋났다」와 「반보수적으로 "
        "어긋났다」를 구분할 수 없다(음수 = 명목보다 «덜» 기각 = 보수적).")
    say()
    fired = bx["N1"]["fired"] or bx["B1"]["fired"]
    say("⇒ " + ("🟢 **`SEC-X1` 이 실제로 발동한다** — 죽은 가드가 아니다."
                if fired else "🔴 **고장낸 구현에서도 발동하지 않았다** — 이 실증은 실패다.")
        + " 🔴 **그리고 이 발동은 「섹터가 무의미하다」와 무관하다** — 잰 것은 «우리 귀무 구현»이다(§4-4).")

    # ══════════════════════════════════════════════════════════════════════
    # §7 SEC-V1 + 재진입 민감도
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §7. `SEC-V1` 민감도 **4축** (§4-6) — 🔴 «민감도 전용»")
    say()
    say("🔒 **적용 범위**: 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」에만 적용된다. "
        "🔴 **§3 의 3중 AND 안에서 한 항목이 미달하는 사건에는 «관여하지 않는다»** — "
        "그건 갈린 게 아니라 **AND 가 거짓인 것**이고 그 판정은 §3 이 한다(§3 우선순위표).")
    say()
    say("⚠️ **「귀무 풀(`SEC-N1` ↔ `SEC-B1`)」은 이 표에 «없다»** — 민감도가 아니라 **판정 조건**이다(§4-6).")
    say()

    def verdict_of(E, g1r):
        if not E["vals"] or E["N1"] is None or E["B1"] is None or E["B2"]["rate"] is None:
            return None
        if g1r is not None and g1r >= G1_THR:
            return None
        return bool(E["N1"]["p_main"] < P_THR and E["B1"]["p_main"] < P_THR
                    and E["B2"]["rate"] > B2_THR)

    def vshow(v):
        return "⛔ 판정 불가" if v is None else ("✅ 성립" if v else "🔴 불성립")

    say("| # | 축 | 갈래 | 값(글 단위 중앙) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | `SEC-P1` | 판정 갈래 |")
    say("|---|---|---|---|---|---|---|---|---|")
    VD = {}

    def vrow(axis, axis_name, label, E, g1r, is_main):
        v = verdict_of(E, g1r)
        VD[(axis, label)] = v
        b2 = E["B2"]
        say(f"| {axis} | {axis_name} | {label} | {fmt(E['main'])} | "
            f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
            f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
            f"{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}% | **{vshow(v)}** | "
            + ("🔒 **판정**" if is_main else "민감도") + " |")

    for n in NS:
        note = " (🔴 구조적 미정 %.1f%% 병기)" % (G1[(5, MAIN_M)] * 100) if n == 5 else ""
        vrow(1, "섹터 깊이", f"`N = {n}`{note}", EV[(n, MAIN_M)], G1[(n, MAIN_M)], n == MAIN_N)
    for mk in MEAS:
        vrow(2, "측정자", f"`{mk}`", EV[(MAIN_N, mk)], G1[(MAIN_N, mk)], mk == MAIN_M)
    v_main = verdict_of(MAIN, g1_main)
    VD[(3, "글 단위 중앙")] = v_main
    say(f"| 3 | 집계 | 글 단위 중앙 | {fmt(MAIN['main'])} | {fmt(n1p, 4)} | {fmt(b1p, 4)} | "
        f"{fmt(b2r * 100 if b2r is not None else None)}% | **{vshow(v_main)}** | 🔒 **판정** |")
    p_pool_n1 = MAIN["N1"]["p_pool"] if MAIN["N1"] else None
    p_pool_b1 = MAIN["B1"]["p_pool"] if MAIN["B1"] else None
    v_pool = None
    if p_pool_n1 is not None and p_pool_b1 is not None and b2r is not None and g1_main < G1_THR:
        v_pool = bool(p_pool_n1 < P_THR and p_pool_b1 < P_THR and b2r > B2_THR)
    VD[(3, "건 pooled 중앙")] = v_pool
    say(f"| 3 | 집계 | 건 pooled 중앙 | {fmt(MAIN['pooled'])} | {fmt(p_pool_n1, 4)} | "
        f"{fmt(p_pool_b1, 4)} | 〃 | **{vshow(v_pool)}** | 민감도 |")
    VD[(4, "`exact` 만")] = v_main
    say(f"| 4 | 등록일 정밀도 | `exact` 만 ({len(items)}건 · 측정 가능 {len(MAIN['vals'])}) | "
        f"{fmt(MAIN['main'])} | {fmt(n1p, 4)} | {fmt(b1p, 4)} | "
        f"{fmt(b2r * 100 if b2r is not None else None)}% | **{vshow(v_main)}** | 🔒 **판정** |")
    if ap_items:
        ap_all_items = items + ap_items
        E_ap = full_eval(ap_all_items, MAIN_N, MAIN_M)
        g1_ap = sum(1 for b in E_ap["bs"] if not b["ok"]) / len(ap_all_items)
        vrow(4, "등록일 정밀도", f"`approx` 포함 ({len(ap_all_items)}건)", E_ap, g1_ap, False)
    else:
        VD[(4, "`approx` 포함")] = v_main
        say(f"| 4 | 등록일 정밀도 | `approx` 포함 (**추가 0건**) | {fmt(MAIN['main'])} | "
            f"{fmt(n1p, 4)} | {fmt(b1p, 4)} | {fmt(b2r * 100 if b2r is not None else None)}% | "
            f"**{vshow(v_main)}** | 민감도(**구조적으로 동일**) |")
    say()
    if not ap_items:
        say("🟢 **축 ④ 는 이 글에서 «구조적으로» 갈릴 수 없다** — post8 의 `approx` 가 **0건**이라 "
            "「`approx` 포함」 집합이 「`exact` 만」과 **같은 집합**이다(모호가 아니라 정의다). "
            "🔴 그래서 이 축의 «불갈림»을 **잣대 강건성의 증거로 읽지 않는다.**")
    say("🟢 **축 ③ 도 이 글에서 «구조적으로» 갈릴 수 없다** — 글이 하나뿐이라 "
        "글 단위 중앙 = 건 pooled 중앙이다(§3 말미). "
        "⚠️ 다만 **귀무 집계는 다른 경로로 계산되므로 `p` 는 미세하게 다를 수 있다** — "
        "위 표에 두 `p` 를 «둘 다» 인쇄했다.")
    vals_v = list(VD.values())
    kinds = {str(v): v for v in vals_v}
    split = len(kinds) > 1
    # 🔒 §3 이 «앞에서» 쓴 값과 같아야 한다 — 같은 `verdict_of` · 같은 4축(§4-6).
    assert split == v1_split_pre, ("SEC-V1 배선 불일치", split, v1_split_pre)
    assert split == bool(V1PRE["split"])
    say()
    say("### 🔒 `SEC-V1` : **" + ("🔴 갈린다" if split else "🟢 갈리지 않는다") + "** "
        + f"({len(kinds)}종 판정 — "
        + " · ".join(f"{vshow(v)}:{sum(1 for x in vals_v if str(x) == k)}"
                     for k, v in sorted(kinds.items())) + ")")
    say()
    say(("🔴 **(post7 방식 · 전 갈래 읽기) 갈린다.** " if split else "🟢 **(post7 방식 · 전 갈래 읽기) 갈리지 않는다.** ")
        + "🆕 **판정 배선은 `P8-갈래계수` 읽기(§7-3 · 최소 n 을 채운 갈래만)를 쓴다** — 그 읽기 = "
        + ("🔴 **갈린다**" if v1_split_p8 else "🟢 **갈리지 않는다**") + ". "
        "🔒 §3 1행의 ⛔ 열이 `SEC-V1` 을 판정 불가 조건으로 열거하므로(`:600`) 갈림은 `SEC-P1` 을 ⛔ 로 만든다 — "
        "🔴 **단 적용 범위(`:815-817`)는 「같은 판정을 «다른 잣대»로 다시 계산했을 때 갈리는가」뿐이다** — 주 갈래의 "
        "3중 AND 가 «거짓»인 사건은 §3 이 판정하고 이 조항은 관여하지 않는다(🆕 정정 1차: 단 최소 n 갈래 중 «성립»이 "
        "있으면 그건 잣대 갈림이라 ⛔ — S-2). ***어느 쪽이든 잣대를 넓혀 열지 않는다.***"
        + ("" if ap_items else " 🔴 축 ④ 는 이 글에서 구조적으로 갈릴 수 없다(`approx` 0건)."))
    say()
    say("#### 🔴🔴 7-1A. 모호 지점 — **`SEC-V1` 의 «입력»이 4축인가 9 조합인가** (양쪽 인쇄)")
    say()
    say("사전등록이 두 곳에서 다르게 읽힌다. **어느 쪽으로도 고치지 않고 둘 다 인쇄한다.**")
    say()
    say("| 읽기 | 근거 문언 | 무엇을 세나 |")
    say("|---|---|---|")
    say("| **A**(위 표 · 이 스크립트의 판정) | §4-6 *「아래 **4축**을 «항상» 나란히 인쇄한다」* — 표가 "
        "**한 번에 한 축**만 흔든다(`N` 은 `SEC-M1` 에서 · 측정자는 `N=3` 에서) | 위 10행 |")
    say("| **B**(확장) | §4-5 *「**9 조합**을 다 인쇄하되 판정은 «동결된 하나»로만 한다. "
        "나머지는 `SEC-V1` 의 «입력»이다」* | 9 조합 «전부»(대각선 조합 포함) |")
    say()
    say("| `N` | 측정자 | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | `SEC-G1` | 3중 AND |")
    say("|---|---|---|---|---|---|---|")
    ext = {}
    for n in NS:
        for mk in MEAS:
            E = EV[(n, mk)]
            v = verdict_of(E, G1[(n, mk)])
            ext[(n, mk)] = v
            b2 = E["B2"]
            tag = " 🔒" if (n, mk) == (MAIN_N, MAIN_M) else ""
            say(f"| {n}{tag} | `{mk}`{tag} | "
                f"{fmt(E['N1']['p_main'], 4) if E['N1'] else '⛔'} | "
                f"{fmt(E['B1']['p_main'], 4) if E['B1'] else '⛔'} | "
                f"{fmt(b2['rate'] * 100 if b2['rate'] is not None else None)}% | "
                f"{G1[(n, mk)] * 100:.1f}% | **{vshow(v)}** |")
    say()
    passers = [f"`N={n}` × `{mk}`" for (n, mk), v in ext.items() if v]
    ext_kinds = {str(v): v for v in ext.values()}
    say(f"- 🔴 **읽기 B 에서 3중 AND 를 통과하는 조합 = {len(passers)}개**"
        + (f": **{' · '.join(passers)}**" if passers else " — 없다") + ".")
    if passers and not p1_ok:
        say("- 🔴🔴 **그 조합은 판정 갈래가 «아니고», 읽기 A 의 4축 «어느 항목도» 아니다**"
            "(두 축을 «동시에» 흔든 대각선 조합이다). 🔒 **§4-5 문언 그대로 판정은 «동결된 하나»로만 "
            "한다** ⇒ ***이 통과를 `SEC-P1` 의 지지로 인용하는 것은 금지된다.*** "
            "🔑 ***값을 보고 갈래를 고르면 그게 사후적합이다.***")
        say(f"- 읽기 A 는 {len(kinds)}종, 읽기 B 는 {len(ext_kinds)}종 ⇒ "
            + ("**둘 다 「갈린다」**" if (len(kinds) > 1 and len(ext_kinds) > 1) else
               ("**둘 다 「갈리지 않는다」**" if (len(kinds) == 1 and len(ext_kinds) == 1) else "🔴 **두 읽기가 다르다**"))
            + " · 🔒 판정 배선은 §7-3 `P8-갈래계수` 읽기다. 주 갈래의 3중 AND 자체는 §3 이 «기록»으로 남긴다(§5).")
        say("- 🔴 **그래도 이 사실을 숨기지 않는다** — 이 축에서 「통과하는 잣대가 «존재»한다」는 것은 "
            "***다음 글에서 `SEC-D1`·`SEC-D2` 를 바꾸고 싶어지는 압력***이고, 그 압력이 곧 "
            "이 프로그램이 금지한 동작이다. **바꾸려면 새 사전등록이 필요하다.**")
    say()
    say("### 7-3. 🆕 `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` · `SEC-V1` 의 «갈렸다» 계수")
    say()
    say("🔴 **최소 n = `exact` 3**(`PREREG_SECTOR_COMOVE.md` §3 1행 — 동결문 값 그대로) · **n = 그 갈래에서 측정 가능한 "
        "건 수**(= 집계에 실제로 들어간 건) · 🔴 **최소 n 미달 갈래의 값은 인쇄하되 「갈렸다」의 근거로 쓰지 않는다**"
        "(`PREREG_POST8.md` §5 (나) 2) · 🔴 `approx` 로 최소 n 을 채우지 않는다(`D-3` 우선 · PD-23).")
    say()
    say("| # | 갈래 | **n** | 최소 n(3) | **답**(`SEC-P1` 3중 AND) | 「갈렸다」 계수에 | 비고 |")
    say("|---|---|---|---|---|---|---|")
    for (ax, lab), v in V1PRE["VD"].items():
        nn = NMAP.get((ax, lab), 0)
        say(f"| {ax} | {lab} | **{nn}** | {'충족' if nn >= MIN_EXACT else '🔴 미달'} | **{vshow(v)}** | "
            f"{'✅ 센다' if (ax, lab) in V1_COUNTED else '— 인쇄만'} | "
            + ("🔒 판정 갈래" if (ax, lab) in ((1, f"N={MAIN_N}"), (2, MAIN_M), (3, "글 단위 중앙"), (4, "`exact` 만"))
               else "민감도") + " |")
    say()
    _ap_key = (4, "`approx` 포함")
    if ap_items and V1PRE["VD"].get(_ap_key) is None and _ap_key in V1_COUNTED:
        _ap_all = items + ap_items
        _ap_bad = sum(1 for b in full_eval(_ap_all, MAIN_N, MAIN_M)["bs"] if not b["ok"])
        say(f"- 🔴 **`approx` 포함 갈래의 «판정 불가»의 출처** — 원장 `reg_date` 가 빈 `approx` {len(ap_items)}건이 "
            f"«측정 불가»로 `SEC-G1` 분모에 들어가 **{_ap_bad}/{len(_ap_all)} = {_ap_bad / len(_ap_all) * 100:.1f}% ≥ 1/3** 이 된 것이다"
            "(`v1_axis_verdicts` · post7 처리 그대로). 측정 가능 건(n)은 `exact` 만 갈래와 **같은 건**이다. "
            "🔴 **모호 신고**: 이 «판정 불가»를 `P8-갈래계수` 의 «답»으로 셀지, «답 없음»(최소 n 미달과 같은 취급)으로 볼지는 "
            "`PREREG_POST8.md` §5 (나) 2 가 정하지 않는다(그 절은 «최소 n»만 말한다) — **양쪽 인쇄** · 이 산출물(배선)은 셌다(보수).")
        _alt = {k: v for k, v in V1_COUNTED.items() if k != _ap_key}
        _alt_split = len({str(v) for v in _alt.values()}) > 1
        say(f"  - (가) 센다 = 센 갈래 {len(V1_COUNTED)}개 · 답 {len({str(v) for v in V1_COUNTED.values()})}종 ⇒ "
            f"{'🔴 갈린다' if v1_split_p8 else '🟢 갈리지 않는다'} · "
            f"(나) 세지 않는다 = 센 갈래 {len(_alt)}개 · 답 {len({str(v) for v in _alt.values()})}종 ⇒ "
            f"{'🔴 갈린다' if _alt_split else '🟢 갈리지 않는다'} ⇒ "
            + ("**두 읽기가 같다**." if _alt_split == v1_split_p8 else
               "🔴 **두 읽기가 다르다** — 🔒 단 `SEC-V1` 은 «주 갈래 AND 참 ∨ «성립» 갈래 존재»일 때만 `SEC-P1` 에 "
               "관여한다(`:815-817` · 정정 1차 S-2) · "
               f"이번 AND = {'참' if and_ok else '거짓'} · «성립» 갈래 {'있음' if v1_any_ok else '없음'} ⇒ "
               + ("**이 구분은 이번 판정을 가르지 않는다.**" if not (and_ok or v1_any_ok)
                  else "🔴 **이 구분이 판정을 가른다 — 판정 불가·모호.**")))
        say("  - 🔴 **`PREREG_POST8.md:250` (나)4 와의 관계**(정정 1차 · 인용) — *「`exact` 갈래와 `approx` 포함 갈래가 **둘 다 "
            "최소 n 을 채우고** 답이 갈리면 ⇒ ⛔ 판정 불가」*. 이 갈래는 `approx` 값이 **0건**(날짜 없음 · G1 분모에만 들어감)이라 "
            "«`approx` 포함 갈래의 답»이 서는지가 곧 위 모호다 — (가) 로 읽으면 (나)4 도 걸리고, (나) 로 읽으면(= `RNK-` 축의 "
            "「갈래 못 만듦」 처리) 걸리지 않는다. 🔴 **양쪽 인쇄 · 이 산출물은 판정을 옮기지 않는다**(값 본 뒤 읽기를 고르지 "
            "않는다 · 관리자 판단 사안으로 신고).")
    say(f"- ⇒ **`SEC-V1`(`P8-갈래계수`) = {'🔴 갈린다' if v1_split_p8 else '🟢 갈리지 않는다'}** "
        f"(센 갈래 {len(V1_COUNTED)}개 · 답 {len({str(v) for v in V1_COUNTED.values()})}종) · "
        f"post7 방식(전 갈래) = {'🔴 갈린다' if v1_split_pre else '🟢 갈리지 않는다'} ⇒ "
        + ("**`P8-갈래계수`(가) ↔ post7 방식, 두 읽기가 같다** — 이 구분은 이번 판정을 가르지 않는다." if v1_split_pre == v1_split_p8 else
           "🔴 **두 읽기가 다르다** — `PREREG_POST8.md` §5 (나) 3(「갈래를 갖는 모든 축에 같은 방식으로 적용」)이 "
           "post8 부터 구속하므로 **판정 배선은 `P8-갈래계수` 읽기**다. 🔴 모호 신고: `SEC-V1` 원문(§4-6)은 «하나라도 "
           "판정을 가르면»이고 최소 n 을 말하지 않는다 — 두 문언의 관계를 정한 줄은 없다(양쪽 인쇄)."))
    say()
    # 🔀 「우리로 제외」 — 🔒 #1-(ii) 인쇄만(판정 효과 없음)
    _ur = [it for it in items if it["code"] != POST8_TWO_CYCLE_CODE]
    E_ur = full_eval(_ur, MAIN_N, MAIN_M)
    g1_ur = sum(1 for b in E_ur["bs"] if not b["ok"]) / len(_ur) if _ur else None
    v_ur = verdict_of(E_ur, g1_ur)
    say("#### 7-3-1. 🔀 「우리로 제외」 — 🔒 사장님 결정 #1-(ii): **«인쇄만» · 판정 효과 없음 · 갈래로 세지 않는다**")
    say()
    say("| 갈래 | 분모 | 측정 가능 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | `SEC-G1` | 3중 AND | 판정 효과 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    say(f"| 🔒 포함(판정) | {len(items)} | {len(MAIN['vals'])} | {fmt(MAIN['main'])} | {fmt(n1p, 4)} | {fmt(b1p, 4)} | "
        f"{fmt(b2r * 100 if b2r is not None else None)}% | {g1_main * 100:.1f}% | **{vshow(verdict_of(MAIN, g1_main))}** | ✅ |")
    say(f"| 「우리로 제외」 | {len(_ur)} | {len(E_ur['vals'])} | {fmt(E_ur['main'])} | "
        f"{fmt(E_ur['N1']['p_main'], 4) if E_ur['N1'] else '⛔'} | {fmt(E_ur['B1']['p_main'], 4) if E_ur['B1'] else '⛔'} | "
        f"{fmt(E_ur['B2']['rate'] * 100 if E_ur['B2']['rate'] is not None else None)}% | "
        + (f"{g1_ur * 100:.1f}%" if g1_ur is not None else "—") + f" | **{vshow(v_ur)}** | 🔴 **없음 — 인쇄만** |")
    say()
    if len(E_ur["vals"]) < MIN_EXACT:
        say(f"- 🔴 「우리로 제외」 갈래의 측정 가능 건 = **{len(E_ur['vals'])} < 3**(최소 n 미달) — 판정 효과가 없는 갈래이기도 하다.")
    say("- 근거(🔒 #1-(ii) · PD-3 (ii)): 등록일 축의 재진입은 **등록 자체가 두 번째 사이클인 건**이고 우리로의 측정 등록은 "
        "**첫 사이클**(플래그 0)이다 ⇒ ***없는 충돌에 민감도를 붙이면 그것이 신설 규칙이다***(`PREDECISION_2026-09-15_post7.md:66`).")
    say()
    say(f"### 7-2. 🔂 §1-5 재진입 {len(PD3_IN)}건 **제외** 민감도 (`PREREG_POST6.md` §1-5 · PD-3 — 의무)")
    say()
    say("🔴 **제외 대상은 «판정 분모 안» 재진입뿐이다** — 글 전체 재진입 3건(원익 `none` · 헥토·코데즈 `approx`)은 "
        "전부 이 분모에 없다 ⇒ **제외 대상 0건 · 두 갈래가 «같은 표본» = 항등**(명시 인쇄 · 판별력 0). "
        "***두 민감도(재진입 제외 ↔ `approx` 제외)를 합치지 않는다***(PD-3 말미).")
    say()
    keep = [it for it in items if it["code"] not in PD3_FLAG_P8]
    E_re = full_eval(keep, MAIN_N, MAIN_M)
    g1_re = sum(1 for b in E_re["bs"] if not b["ok"]) / len(keep) if keep else None
    v_re = verdict_of(E_re, g1_re)
    say("| 갈래 | 분모 | 측정 가능 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | "
        "`SEC-G1` | `SEC-P1` |")
    say("|---|---|---|---|---|---|---|---|---|")
    say(f"| 🔒 **포함**(판정) | {len(items)} | {len(MAIN['vals'])} | {fmt(MAIN['main'])} | "
        f"{fmt(n1p, 4)} | {fmt(b1p, 4)} | {fmt(b2r * 100 if b2r is not None else None)}% "
        f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | {g1_main * 100:.1f}% | **{vshow(v_main)}** |")
    say(f"| 제외(민감도) | {len(keep)} | {len(E_re['vals'])} | {fmt(E_re['main'])} | "
        f"{fmt(E_re['N1']['p_main'], 4) if E_re['N1'] else '⛔'} | "
        f"{fmt(E_re['B1']['p_main'], 4) if E_re['B1'] else '⛔'} | "
        f"{fmt(E_re['B2']['rate'] * 100 if E_re['B2']['rate'] is not None else None)}% "
        f"({E_re['B2']['wins']}/{E_re['B2']['n']}) | "
        + (f"{g1_re * 100:.1f}%" if g1_re is not None else "—") + f" | **{vshow(v_re)}** |")
    say()
    say("- 🔒 **분모는 «포함»이다**(§1-5 1번) — 제외는 **의무 민감도**다. 두 갈래 판정 = **"
        + ("같다" if str(v_re) == str(v_main) else "🔴 다르다 ⇒ 「재진입 의존」으로 적는다") + "**.")
    say(f"- `P6-PRIOR_CYCLE_IN_WINDOW` **판정 분모 안 합 = {sum(PD3_IN.values())}/{len(items)}** ("
        + (" · ".join(f"`{c}`={v}" for c, v in sorted(PD3_IN.items())) or "—")
        + ") · 🔴 **글 전체 = PD-3 표 문형 그대로**(`PREDECISION_2026-09-18_post8.md:113-117`): " + PD3_NOTE_P8
        + " — PD-3 이 계산 «전»에 못박은 값이다(🆕 정정 1차: 초판 「글 전체 합 = 1/1」은 원익 «계산 안 함»과 헥토 «갈래별»을 "
        "지워 한 수로 접었다). 🔑 **두 수를 한 수로 합치지 않는다.**")

    # ══════════════════════════════════════════════════════════════════════
    # §8 SEC-O1
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §8. `SEC-O1` — 훈련(post1~5 🔬) ↔ 검증(post8 🔒) **나란히** (§4-5)")
    say()
    say("🔴 **훈련 성적을 판정 분모에 절대 넣지 않는다**(§4-5 · `PREREG_POST6.md` §2-1 ③ 문형). "
        "아래 훈련 열은 **탐색적 표기**이며, 세 열의 뜻이 서로 다르다:")
    say()
    say("| 열 | 뜻 |")
    say("|---|---|")
    say(f"| 훈련(동결) | `FREEZE_SECTOR_2026-09-03.md` §4-2 — **DB 스냅샷 `{FROZEN_TRAIN['db_snapshot']}`** |")
    say(f"| 훈련(재계산) | 같은 post1~5 표본을 **이 실행의 DB 스냅샷**(`max(date)` `{SNAP_MAX}` · 창 종료 `{END}`)으로 다시 잰 값 |")
    say(f"| 🔒 검증(post8) | **판정** — 분모 post8 신규 `exact` {len(items)}건 |")
    say()
    E_tr = full_eval(train, MAIN_N, MAIN_M)
    g1_tr = sum(1 for b in E_tr["bs"] if not b["ok"]) / len(train)
    tr_n1 = E_tr["N1"]["p_main"] if E_tr["N1"] else None
    tr_b1 = E_tr["B1"]["p_main"] if E_tr["B1"] else None
    tr_b2 = E_tr["B2"]["rate"]

    def gap(a, b, nd=4):
        if a is None or b is None:
            return "—"
        return f"{b - a:+.{nd}f}"

    say(f"| 항목 | 훈련(동결 · {FROZEN_TRAIN['db_snapshot']}) | 훈련(재계산 · 스냅샷 {SNAP_MAX}) | "
        "🔴 훈련 괴리 | 🔒 검증 post8 | 🔴 **훈련↔검증 괴리** |")
    say("|---|---|---|---|---|---|")
    say(f"| 분모 `exact` | {FROZEN_TRAIN['n_items']} | {len(train)} | "
        + ("✅ 같다" if len(train) == FROZEN_TRAIN["n_items"] else "🔴 다르다")
        + f" | **{len(items)}** | — |")
    say(f"| 측정 가능 | {FROZEN_TRAIN['n_measurable']} | {len(E_tr['vals'])} | "
        + ("✅" if len(E_tr["vals"]) == FROZEN_TRAIN["n_measurable"] else "🔴")
        + f" | **{len(MAIN['vals'])}** | — |")
    say(f"| 관측(글 단위 중앙) | {FROZEN_TRAIN['main']:.1f} | {fmt(E_tr['main'])} | "
        f"{gap(FROZEN_TRAIN['main'], E_tr['main'], 1)} | **{fmt(MAIN['main'])}** | "
        f"**{gap(E_tr['main'], MAIN['main'], 1)}** |")
    say(f"| `SEC-N1` `p` | {FROZEN_TRAIN['N1']:.4f} | {fmt(tr_n1, 4)} | "
        f"{gap(FROZEN_TRAIN['N1'], tr_n1)} | **{fmt(n1p, 4)}** | **{gap(tr_n1, n1p)}** |")
    say(f"| `SEC-B1` `p` | {FROZEN_TRAIN['B1']:.4f} | {fmt(tr_b1, 4)} | "
        f"{gap(FROZEN_TRAIN['B1'], tr_b1)} | **{fmt(b1p, 4)}** | **{gap(tr_b1, b1p)}** |")
    say(f"| `SEC-B2` 승률 | {FROZEN_TRAIN['B2'] * 100:.1f}% "
        f"({FROZEN_TRAIN['B2_wins']}/{FROZEN_TRAIN['B2_n']}) | "
        f"{fmt(tr_b2 * 100 if tr_b2 is not None else None)}% ({E_tr['B2']['wins']}/{E_tr['B2']['n']}) | "
        f"{gap(FROZEN_TRAIN['B2'] * 100, tr_b2 * 100 if tr_b2 is not None else None, 1)}%p | "
        f"**{fmt(b2r * 100 if b2r is not None else None)}%** "
        f"({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | "
        f"**{gap(tr_b2 * 100 if tr_b2 is not None else None, b2r * 100 if b2r is not None else None, 1)}%p** |")
    say(f"| `SEC-G1` | {FROZEN_TRAIN['G1'] * 100:.1f}% | {g1_tr * 100:.1f}% | "
        f"{gap(FROZEN_TRAIN['G1'] * 100, g1_tr * 100, 1)}%p | **{g1_main * 100:.1f}%** | "
        f"**{gap(g1_tr * 100, g1_main * 100, 1)}%p** |")
    say()
    drift = [nm for nm, a, b in (
        ("관측", FROZEN_TRAIN["main"], E_tr["main"]),
        ("`SEC-N1`", FROZEN_TRAIN["N1"], tr_n1),
        ("`SEC-B1`", FROZEN_TRAIN["B1"], tr_b1),
        ("`SEC-B2`", FROZEN_TRAIN["B2"], tr_b2),
        ("`SEC-G1`", FROZEN_TRAIN["G1"], g1_tr))
        if a is not None and b is not None and abs(a - b) > 1e-9]
    # 🔴 「이 기간에 자란 종목」을 **하드코딩하지 않고 실측한다** — 동결 훈련 DB 스냅샷
    #    «뒤»에 첫 봉이 생긴 종목이 곧 「두 창 사이 신규」다(코드 상수 인용 금지).
    cur.execute("SELECT stock_code, min(date) FROM daily_prices GROUP BY 1 "
                "HAVING min(date) > %s ORDER BY 2, 1", (FROZEN_TRAIN["db_snapshot"],))
    grew = [(c, str(d)) for c, d in cur.fetchall()]
    si_absent = [c for c, _ in grew if c not in SEC]
    grew_txt = " · ".join("`%s`(첫 봉 %s)" % (c, d) for c, d in grew) if grew else "없음"
    say(f"- 🔴 **훈련 괴리(동결 ↔ 재계산) = {len(drift)}항목**"
        + (f": {' · '.join(drift)}" if drift else " — 🟢 **전부 일치**")
        + f". 🔴 **「DB 가 자라서」 가설은 «실측으로 기각»한다** — 동결 훈련 스냅샷"
          f"(`{FROZEN_TRAIN['db_snapshot']}`) «뒤»에 첫 봉이 생긴 종목은 **{len(grew)}종목**"
          f"({grew_txt})이고, 그 중 **`stock_industry` 에 없는 것 {len(si_absent)}/{len(grew)}** = "
          f"{'·'.join('`%s`' % c for c in si_absent) if si_absent else '없음'} ⇒ "
        + ("***조인 유니버스에 애초에 진입하지 못한다*** ⇒ `SEC-` 측정값을 움직일 «경로가 없다». "
           "🟢 **남는 설명은 하나뿐 — 동결본에 적힌 값이 «반올림 표기»라서다**"
           "(바로 아래 줄이 그 대조다)."
           if len(si_absent) == len(grew) else
           "🔴🔴 **일부는 조인 유니버스에 «들어온다» ⇒ 이 가설을 기각할 수 없다** — "
           "아래 반올림 대조와 «함께» 읽어야 한다."))
    # 🔴 위 «괴리» 판정은 «전정밀도 float ↔ 동결본의 «인쇄된» 반올림 값»을 비교한다.
    #    같은 대조를 **동결본이 인쇄한 정밀도로** 한 번 더 인쇄한다(양쪽 인쇄 · 규칙 변경 아님).
    same_print = [nm for nm, a, b, nd in (
        ("관측", FROZEN_TRAIN["main"], E_tr["main"], 1),
        ("`SEC-N1`", FROZEN_TRAIN["N1"], tr_n1, 4),
        ("`SEC-B1`", FROZEN_TRAIN["B1"], tr_b1, 4),
        ("`SEC-B2`", FROZEN_TRAIN["B2"], tr_b2, 2),
        ("`SEC-G1`", FROZEN_TRAIN["G1"], g1_tr, 3))
        if a is not None and b is not None and f"{a:.{nd}f}" == f"{b:.{nd}f}"]
    say(f"- 🟢 **같은 대조를 «동결본이 인쇄한 정밀도»로 하면 {len(same_print)}/5 항목이 일치한다**"
        + (f"({' · '.join(same_print)}). " if same_print else ". ")
        + "🔑 ***그러므로 위 「괴리 2항목」은 «DB 가 값을 움직였다»가 아니라 "
          "«동결본에 적힌 값이 반올림 표기»라서 생긴 것이다*** — 두 문장은 다르고, "
          "**둘 다 인쇄해야 어느 쪽인지 갈린다.**")
    say("- 🟢 **독립 확인**: 같은 실행의 배선 점검 모드 산출물에서도 `sector_dryrun/` 의 건별 JSON "
        "18건·`cases.tsv` 데이터 행이 동결본과 **byte 단위로 같다**(바뀐 것은 «DB 스냅샷 날짜 문자열»뿐). "
        "⇒ ***`SEC-` 측정값은 이번 DB 성장에 «불변»이었다.***")
    say("- 🔴 **훈련↔검증 괴리를 「악화/개선」으로 읽지 않는다** — 두 열은 **다른 표본**이고 훈련은 "
        "**판정 분모 «밖»**이다(§4-5). 나란히 두는 것은 *「잣대를 고른 것을 신고했나」*를 보이기 "
        "위해서지 두 열을 비교 검정하기 위해서가 아니다.")
    say("- 🔒 **`SEC-O1` 판정** = 잣대 결정(`SEC-D1`·`D2`) **2026-09-02** ↔ 배선 점검 **2026-09-02** ↔ "
        "동결 커밋 **2026-09-03** ↔ `fetch_post.py`(post8) **2026-09-18 19:04:05 KST** ↔ "
        "이 계산 **그 «후»** "
        "⇒ 🟢 **결정이 §0-4 4번 «앞»이다 — 유효**(⛔ 경로 = 결정이 4번 «뒤»면 무효 · PD-0 이 증거).")
    say()
    say("### 8-1. 🆕 같은 스냅샷(이 실행) 재계산 — post6·post7 «판정» 표본을 나란히 (직전 문서 숫자 옮겨 적기 금지)")
    say()
    say("🔴 **각 글의 판정 분모(그 글 신규 `exact`)를 이 실행의 DB·섹터 스냅샷으로 다시 잰다** — 주 갈래 성분 · "
        "`SEC-B1` 발화(`q_top`) · `SEC-V1`(전 갈래 · `P8-갈래계수` 두 읽기). 🔴 `SEC-X1`(순열 200 × 20,000)은 **비용상 "
        "재계산하지 않았다** — 동결 산출물의 결과(post6·post7 둘 다 보정됨)를 **인용**한다(재계산 아님 · 표기). "
        "🔴 **글별 독립 판정 + 부호 누계만**(§2-6 · 합산 금지).")
    say()
    say("| 글 | `exact` | 측정 | 관측(글 단위) | `SEC-N1` `p` | `SEC-B1` `p` | `SEC-B2` | `SEC-G1` | `q_top` 최대 · 발화 | "
        "3중 AND | `SEC-V1` 전 갈래 / P8 | 발표 라벨(옮겨 적음) |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|")
    _pub = {6: "불성립(`RESULTS_SECTOR_POST6_NUMBERS.md` §5)", 7: "판정 불가 — `SEC-V1` 발동(`RESULTS_SECTOR_POST7_NUMBERS.md` §5)"}
    for p in (6, 7):
        r_ = prior_rec[p]
        say(f"| post{p} | {r_['n']} | {r_['k']} | {fmt(r_['main'])} | {fmt(r_['N1'], 4)} | {fmt(r_['B1'], 4)} | "
            f"{fmt(r_['B2'] * 100 if r_['B2'] is not None else None)}% ({r_['B2w']}/{r_['B2n']}) | {r_['G1'] * 100:.1f}% | "
            f"{r_['qtop']:.3f}(`{r_['qtop_d']}`) · {'발화 가능' if r_['fire'] else '🔴 발화 불가'} | "
            f"**{'✅ 통과' if r_['and_ok'] else '🔴 거짓'}** | {'갈림' if r_['split_all'] else '불갈림'} / "
            f"{'갈림' if r_['split_p8'] else '불갈림'} | {_pub[p]} |")
    say(f"| **post8(이 회차)** | {len(items)} | {len(MAIN['vals'])} | {fmt(MAIN['main'])} | {fmt(n1p, 4)} | {fmt(b1p, 4)} | "
        f"{fmt(b2r * 100 if b2r is not None else None)}% ({MAIN['B2']['wins']}/{MAIN['B2']['n']}) | {g1_main * 100:.1f}% | "
        f"{qmax:.3f}(`{qmax_d}`) · {'발화 가능' if b1fire else '🔴 발화 불가'} | **{'✅ 통과' if and_ok else '🔴 거짓'}** | "
        f"{'갈림' if v1_split_pre else '불갈림'} / {'갈림' if v1_split_p8 else '불갈림'} | **{p1_word}** |")
    say()
    _conf = []
    for p in (6, 7):
        r_ = prior_rec[p]
        lab_re = ("판정 불가" if (r_["and_ok"] and r_["split_all"]) else ("성립" if r_["and_ok"] else "불성립"))
        lab_pub = "불성립" if p == 6 else "판정 불가"
        _conf.append((p, lab_re, lab_pub))
    say("- 재계산 라벨(post7 방식 배선 = 전 갈래 V1 · X1 인용) ↔ 발표 라벨: "
        + " · ".join(f"post{p} {a} ↔ {b} {'🟢' if a == b else '🔴 **다르다**'}" for p, a, b in _conf)
        + ". 🔴 다르면 원인은 **입력 스냅샷 이동**이고 동결값을 고쳐 쓰지 않는다.")

    # ══════════════════════════════════════════════════════════════════════
    # §9 미해소·한계
    # ══════════════════════════════════════════════════════════════════════
    say()
    say("---")
    say()
    say("## §9. 판정 불가·미해소·한계")
    say()
    say("| 항목 | 상태 |")
    say("|---|---|")
    say("| `SEC-P1` | **" + p1_label + "**"
        + (" — 🔴 3중 AND 는 통과했으나 "
           + " · ".join(x for x, f in (("`SEC-V1`(`P8-갈래계수` 갈림)", p1_blocked_v1), ("`SEC-X1`", p1_blocked_x1)) if f)
           + " 이(가) ⛔ 다(§3 1행 ⛔ 열 · §6). ***「계열 최초 성립」이 아니다*** — 조건이 풀리는 글이 오면 판정한다"
           if p1_blocked else
           " — 천장은 §0-2(성립 = 「섹터 동반성 존재」까지 · 불성립 = 「KSIC 섹터 동반상승으로는 "
           "안 잡힌다」까지)") + " |")
    say(f"| `SEC-P2` | 🔒 **기록만** — **이 글에서** 판정 {0 if p1_blocked else 1}회"
        + ("(⛔ 판정 불가라 누계 «분모»에 안 들어간다)" if p1_blocked else "")
        + f" · 성립 {1 if p1_ok else 0}회. 누계를 검정 통계량으로 쓰지 않는다 |")
    say("| `SEC-B1` 발화 | " + ("🟢 가능" if b1fire else "🔴 ⛔ 발화 불가")
        + f" (`q_top` 최대 {qmax:.3f} · 문턱 {QTOP_THR}) |")
    say("| `SEC-X1` | " + ("🟢 보정됨" if x1_ok else "🔴 ⛔ 절차 무효") + " · 고장 실증 "
        + ("✅ 발동" if fired else "🔴 미발동(실증 실패)") + " |")
    say("| `SEC-V1` | 🆕 `P8-갈래계수`: " + ("🔴 갈린다" if v1_split_p8 else "🟢 갈리지 않는다")
        + " · post7 방식(전 갈래): " + ("갈린다" if split else "갈리지 않는다")
        + " — 🔴 축 ③ 은 이 글에서 «구조적으로» 갈릴 수 없다(글 하나) |")
    say("| 🆕 `SEC-V1` 배선 범위(모호 · 정정 1차 S-2) | `:815-817` 은 「AND 안 한 항목 미달 사건엔 관여하지 않는다」만 적고, "
        "«주 갈래 AND 거짓 ∧ 다른 잣대 «성립»» 사건을 따로 적지 않는다 ⇒ 이 산출물은 **⛔ 쪽(선언 금지)**으로 배선했다"
        "(`:817` 「하나라도 판정을 가르면 ⇒ ⛔」) · 초판은 `and_ok ∧ split` 이라 그 사건에서 «불성립»을 인쇄했을 것이다 · "
        + ("이번 회차 «성립» 갈래 **있음** ⇒ 🔴 이 배선이 판정을 닫았다" if v1_any_ok else
           "이번 회차 «성립» 갈래 **0** ⇒ 판정 이동 0") + " · 문언 정비는 다음 사전등록의 몫 |")
    say("| 승/패 대조(`PREREG_SELECTION.md` §4) | ⛔ **5회 연속 미실시** — post8 `exact` 신규에 "
        f"`all_loss = 1` 이 {sum(1 for it in items if str(it['all_loss']) == '1')}건 ⇒ "
        "***이 축의 최대치는 「기술」이다***(§0-2 ③) |")
    say("| 「테마로 고른다」 확증 | ⛔ **이 축에서는 «영구히» 열리지 않는다**(§0-2 · §9 · "
        "에코프로 4종목 → 3칸) |")
    say("| 「섹터 안 «누구»냐」 | ⛔ **미해결** — `RNK-` 축이 멈춘 그 공백이 한 층 위로 옮겨갈 뿐이다(§9) |")
    say(f"| 후속 3건({' · '.join(POST8_FOLLOWUP)}) | 🔒 **분모 밖**(PD-2 · "
        "`reg_date_precision = none` · 이중계상 금지) |")
    say(f"| 신규이나 등록일 미기재 1건({' · '.join(POST8_NONE_NEW)}) | 🔒 **분모 밖**(PD-4 · 🔒 #2) — "
        "🔴 「값이 나빠서」가 아니라 **어느 날의 유니버스인지 정할 수 없어서**다(대안 독법 exact 09-03 은 갈래로 "
        "계산하지 않는다) |")
    say("| 액스비스(`0011A0`) | 🔴 **분모 «안»인데 섹터 표에 없다** — `stock_industry` 스냅샷이 "
        "2026-08-07 에서 멈춰 있다 ⇒ 사유 ③ · `SEC-G1` 1/4 = 25.0% < 1/3(미발동 · 1건만 더 빠지면 발동). "
        "***이 자리가 이 축의 구조적 거짓 음성이 실제로 들어온 자리다*** — post7 해치텍에 이어 2회 연속 |")
    say(f"| 「우리로 제외」 | 🔒 **인쇄만**(🔒 #1-(ii)) — 판정 효과 없음 · §7-3-1 |")
    say("| 표본이 저자가 «올리기로 고른» 매매 | 🔴 **그대로** — 결과 조건화 위협"
        "(`PREREG_SELECTION.md` §0) |")
    say("| `regen_gate.py` | ⬜ **관리자** — `RESULTS_SECTOR_POST8_NUMBERS.md` ↔ `run_sector.py --mode post8` · "
        "`ART_DIRS` 에 `sector_post8` 등재는 관리자 단계다(이 레인은 `regen_gate.py` 를 건드리지 않는다) |")
    say(f"| 스냅샷 의존 | 🔴 **가격 표도 섹터 표도 자란다** — 이 글의 값은 `daily_prices` "
        f"실행 시 `max(date)` = **`{SNAP_MAX}`**(창 종료 `{END}`) · `stock_industry` **{si_rows:,}행** · `max(updated_at)` "
        f"**`{si_upd}`** 위에서만 재현된다(§2-6 · §8-5) |")
    say()
    say("🔴 **매 산출물 의무 문언 재확인**: 거짓 음성이 구조적이다 — 테마는 KSIC 축을 가로지른다"
        "(에코프로 4종목 → 3칸). ⇒ ***`SEC-P1` 불성립을 「테마가 아니다」로 읽지 않는다.***")
    say("🔴 **동반 상승은 «등록일 종가가 확정된 뒤»의 정보로 잰다** ⇒ ***이 축은 라이브에서 재현할 수 "
        "없는 지표다***(§9 · `REG-M5` 형 단서).")
    say("🔴 **이 실행은 새 예측을 만들지 않았다** — `SEC-P1`·`P2`·`N1`·`B1`·`B2`·`G1`·`X1`·`O1`·`V1` 은 "
        "전부 사전등록 §3 표의 항목이고, 새 문턱·새 측정자·새 갈래는 **0건**이다.")
    say("🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1).")
    say()
    say("### 9-1. 🆕 `D-3` 신고 줄 · `D-8` 수준 목록")
    say()
    say(f"🆕 **`P8-approx의존신고`**: *「`approx` 포함 시 최소 n 이 차는 축: **없음** · `exact` 분모 **{len(items)}** / "
        f"`approx` 포함 분모 **{len(items) + len(ap_items)}**」* (`PREREG_POST8.md` §3 (나) 3 · 구성 예고 PD-21 = 「없음」 — "
        "`exact` 가 이미 최소 n 3 을 채운다 · 🔴 `approx` 2건은 원장 날짜가 없어 측정 불가로만 들어간다).")
    say()
    say("🆕 **`P8-결측수준` 수준 목록**(행·글 두 단위 · 🔒 #3 = 부호 갈림 판정은 다음 사전등록까지 **보류**) — 이 축은 "
        "`prog_ver` 를 공변량으로 «기록»만 한다(`PREREG_SECTOR_COMOVE.md:1080-1081`):")
    say()
    say("| 수준 | 행(건) | 글 |")
    say("|---|---|---|")
    for _lv, _nr, _np in p8_prog_levels(ctx["rows"]):
        say(f"| `{_lv}` | {_nr} | {_np} |")
    say()
    say("---")
    say()
    say("## §10. 🆕 `D-9` · `P8-혼합빈티지신고` — 걸침 창마다 한 줄 (`PREREG_POST8.md` §9 (나) 3)")
    say()
    say("### 10-1. 이 축이 «읽는» 창")
    say()
    if own_cross:
        for d in own_cross:
            _l = (np.datetime64(d) - np.timedelta64(20, "D")).astype(str)
            say(f"- *「창 `[{_l}, {d}]` 은 제도 경계 2026-09-14 를 걸친다」*(판정 분모 등록일 {d})")
    else:
        say(f"- 이 축의 판정 창 = 등록일마다 `[D − 20일, D]`(`load_day` 의 `LAG` 창) · 판정 분모 등록일 "
            f"**{' · '.join(dates)}** ⇒ 전부 2026-09-14 «전» ⇒ **걸침 0**(혼합 빈티지 없음).")
    say()
    say("### 10-2. PD-27 (바) 표의 「걸침」 칸 전부 — 공통 인쇄 의무 (🔴 `ANC-`·`REC-`·`LAD-` 창 · 이 축이 읽지 않는다)")
    say()
    for _ax, _nm, _s, _e, _nb, _na in cross:
        say(p8_cross_line(_ax, _nm, _s, _e, _nb, _na))
    say("- `REG-`/`REC-`(§9 문언) `[D−19, D]` 는 전건 **안 걸침**(PD-27 (바) 넷째 열 · 신규 등록일 최대 09-11).")
    say()
    say("### 10-3. 한계 절 문장(`P-4`·`P-5` 가 정한 것 · 정의 불변)")
    say()
    for _ln in P8_LIMIT_LINES:
        say(_ln)
    say()
    say("---")
    say()
    say(f"결정성: 시드 `{SEED}` 고정 · 스트림 분리 · DB 는 SELECT 만 ⇒ **같은 DB 스냅샷에서 재실행하면 "
        "byte 단위로 같다**(`regen_gate.py --rerun` 전제). "
        "🔴 그래서 이 파일에는 **실행 시간·커밋 해시를 적지 않는다** — 벽시계·`HEAD` 는 stdout 전용이다. "
        "🔑 ***커밋마다 바뀌는 값을 산출물에 적으면 그 산출물은 자기 자신을 재현할 수 없게 된다.***")
    say()
    say("[[PREREG_SECTOR_COMOVE]] · [[FREEZE_SECTOR_2026-09-03]] · [[RESULTS_SECTOR_DRYRUN]] · "
        "[[PREREG_POST6]] · [[PREREG_POST8]] · [[PREDECISION_2026-09-18_post8]] · [[INTAKE_2026-09-18_post8]] · "
        "[[PREREG_RANKING]] · [[FINDING_THEME_AXIS]] · [[RESULTS_RANKING_TRAIN]] · "
        "[[RESULTS_REGDAY_POST5]] · [[RESULTS_D1_OOS_POST5]] · [[RESULTS_RECONSTRUCT_POST4]] · "
        "[[PREREG_SELECTION]]")

    # ══════════════════════════════════════════════════════════════════════
    # 기계 산출물
    # ══════════════════════════════════════════════════════════════════════
    # 🔴 `approx` 2건의 `reg_date` 가 원장에서 «비어 있다»(PD-4) — 어느 날의 유니버스인지 정할 수
    #    없으므로 **날짜 키가 아니다**. 측정에서는 이미 «측정 불가»로 들어가 `SEC-G1` 에 반영됐고
    #    (규칙·문턱·분모를 바꾸지 않았다), 아래 스냅샷 표에서는 «날짜»로 세지 않고 그 사실을 적는다.
    man_dates = [d for d in all_dates if d]
    undated_ap = sorted({it["name"] for it in ap_items if not it["reg"]})
    universe = {d: DAY[d]["uni"] for d in man_dates}
    joined = {d: DAY[d]["joined"] for d in man_dates}
    (ART / "universe_snapshot.json").write_text(json.dumps({
        "window_end": END, "db_snapshot_max_date": SNAP_MAX, "db_snapshot_rows_on_max_date": SNAP_ROWS,
        "post_log_no": POST8_LOG_NO, "post_date": "2026-09-18",
        "window_end_note": "창 종료 2026-09-18 = 발행 당일(금 · 거래일) 봉 포함 · B-1(전 축 · PD-1) · "
                           "실행 시 max(date) 는 기록만 하고 창으로 쓰지 않는다 · 이 축은 등록일 당일만 쓴다",
        "pseudo_from_code": list(PSEUDO),
        "pseudo_nonnumeric_in_db": nonnum, "pseudo_final": final_pseudo,
        "universe_sizes": {d: len(universe[d]) for d in man_dates},
        "joined_sizes": {d: len(joined[d]) for d in man_dates},
        "coverage_pct": {d: round(len(joined[d]) / len(universe[d]) * 100, 4) for d in man_dates},
        "universe": universe, "joined": joined,
        "sha256_universe": {d: sha_list(universe[d]) for d in man_dates},
        "sha256_joined": {d: sha_list(joined[d]) for d in man_dates},
        "undated_approx_items": undated_ap,
        "undated_approx_note": "reg_date 가 비어 있어 등록일 유니버스를 정할 수 없다(PD-4) — "
                               "측정에서는 «측정 불가»로 SEC-G1 분모에 들어갔고, 이 표에는 날짜로 세지 않는다",
        "_notation": NOTATION_POST8,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "sector_snapshot.json").write_text(json.dumps({
        "table": "stock_industry", "rows": si_rows, "distinct_stock_code": si_uniq,
        "induty_code_non_null": si_nonnull, "max_updated_at": si_upd,
        "sha256_code_to_induty": si_sha,
        "length_distribution_table": {str(k): v for k, v in sorted(len_all.items())},
        "stock_info_sector_non_null": info_sector, "stock_info_rows": info_rows,
        "warning": "이 표는 시간에 따라 «자란다» — 편입이 늘면 같은 글의 값이 달라진다",
        "_notation": NOTATION_POST8,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for ci, it in enumerate(items):
        rec = {k: it[k] for k in ("post", "log_no", "item_no", "name", "code", "reg", "prec", "all_loss")}
        rec["window_end"] = END
        rec["db_snapshot_max_date"] = SNAP_MAX
        rec["main_branch"] = {"N": MAIN_N, "measure": MAIN_M}
        rec["reentry"] = ({"prior_cycle_reg_date": REENTRY_P8.get(it["code"]),
                           "P6_PRIOR_CYCLE_IN_WINDOW": PD3_FLAG_P8.get(it["code"])}
                          if it["code"] in PD3_FLAG_P8 else None)
        rec["branches"] = {}
        for n in NS:
            for mk in MEAS:
                bb = BR[(n, mk)][ci]
                rec["branches"][f"N{n}_{mk}"] = {
                    kk: (round(vv, 6) if isinstance(vv, float) else vv)
                    for kk, vv in bb.items()}
        rec["_notation"] = NOTATION_POST8
        (ART / f"case_{it['post']}_{it['item_no']}_{it['name']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "verdict.json").write_text(json.dumps({
        "post_log_no": POST8_LOG_NO, "post_date": "2026-09-18",
        "window_end": END, "db_snapshot_max_date": SNAP_MAX,
        "d9_first_read_kst": d9["first"],
        "db_snapshot_rows_on_max_date": SNAP_ROWS,
        "main_branch": {"N": MAIN_N, "measure": MAIN_M},
        "denominator_exact": len(items), "measurable": len(MAIN["vals"]),
        "excluded_none_rows": [r["stock_name"] for r in none_rows],
        "gates": {
            "min_exact": {"threshold": MIN_EXACT, "n": len(items),
                          "open": bool(len(items) >= MIN_EXACT)},
            "SEC-G1": {"threshold": G1_THR, "rate": g1_main, "open": bool(g1_main < G1_THR)},
            "SEC-B1_fire": {"q_top_max": qmax, "q_top_threshold": QTOP_THR, "k": kmain,
                            "p_ceiling": (binom_ge_half(kmain, qmax) if kmain else None),
                            "open": bool(b1fire)},
            "SEC-X1": {"lt05_N1": x1sum["N1"]["lt05"], "lt05_B1": x1sum["B1"]["lt05"],
                       "z_N1": x1sum["N1"]["z"], "z_B1": x1sum["B1"]["z"], "open": bool(x1_ok)},
        },
        "SEC-P1": {"components": {"SEC-N1": n1p, "SEC-B1": b1p, "SEC-B2": b2r},
                   "thresholds": {"SEC-N1": P_THR, "SEC-B1": P_THR, "SEC-B2": B2_THR},
                   "passed": {"SEC-N1": bool(c_n1), "SEC-B1": bool(c_b1), "SEC-B2": bool(c_b2)},
                   "and_passed": and_ok,
                   "SEC-V1_split": v1_split_pre,
                   "SEC-V1_split_P8": v1_split_p8,
                   "SEC-V1_any_branch_ok": v1_any_ok,      # 🆕 정정 1차(S-2)
                   "SEC-X1_ok": x1_ok_pre,
                   "blocked_by_SEC-V1": p1_blocked_v1,
                   "blocked_by_SEC-X1": p1_blocked_x1,
                   "blocked": p1_blocked,
                   "verdict": (None if p1_blocked else p1_ok),
                   "verdict_label": p1_word},
        "SEC-P2": {"note": "기록만 — 검정 통계량 아님 · 누계 이어가기(결정 ⑥)",
                   "prior": SEC_P2_PRIOR_P8,
                   "n_judgements": SEC_P2_PRIOR_P8["n_judgements"] + (0 if p1_blocked else 1),
                   "n_support": SEC_P2_PRIOR_P8["n_support"] + (1 if p1_ok else 0)},
        "SEC-V1": {"split": bool(split),
                   "by_branch": {f"{a}|{b}": v for (a, b), v in VD.items()}},
        "reentry_sensitivity": {"excluded_codes": sorted(PD3_IN),
                                "P6_PRIOR_CYCLE_IN_WINDOW_in_denominator": PD3_IN,
                                "P6_PRIOR_CYCLE_IN_WINDOW_whole_post": PD3_FLAG_P8,
                                "note": "글 전체 §1-5 재진입 3건(원익 none · 헥토·코데즈 approx)은 전부 분모 밖 — 항등(PD-3)",
                                "verdict_kept": v_main, "verdict_excluded": v_re,
                                "main_kept": MAIN["main"], "main_excluded": E_re["main"]},
        "same_snapshot_recompute": {f"post{p}": prior_rec[p] for p in (6, 7)},
        "woori_ro_excluded_print_only": {"n": len(_ur), "main": E_ur["main"], "verdict": v_ur},
        "SEC-O1": {"frozen_train": FROZEN_TRAIN,
                   "recomputed_train": {"main": E_tr["main"], "SEC-N1": tr_n1, "SEC-B1": tr_b1,
                                        "SEC-B2": tr_b2, "SEC-G1": g1_tr,
                                        "n_items": len(train), "n_measurable": len(E_tr["vals"])},
                   "drift_items": drift},
        "_notation": NOTATION_POST8,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "controls_summary.json").write_text(json.dumps({
        "seed": SEED, "nrep": NREP, "note_nrep": "run_selection.py:22 는 NREP=2000",
        "streams": _STREAM_NAMES, "x1_realizations": X1_REP,
        # 🔴 두 값은 «다른 것»이다 — 섞어 쓰면 재현자가 창을 잘못 잡는다(PD-1 5번).
        #    `window_end`       = 판정 창 종료(= 발행 당일 09-18 금 · 거래일) — **판정에 쓴다**
        #    `db_snapshot_max_date` = 실행 시 `daily_prices` 의 실제 `max(date)` — **기록만** 한다
        "window_end": END,
        "db_snapshot_max_date": SNAP_MAX,
        "db_snapshot_rows_on_max_date": SNAP_ROWS,
        "thresholds": {"p": P_THR, "B2": B2_THR, "G1": G1_THR, "q_top": QTOP_THR,
                       "n_up_multiplier": UP_MULT, "drop_mark": DROP_MARK,
                       "min_exact": MIN_EXACT},
        "observed": {f"N{n}_{mk}": {"main": EV[(n, mk)]["main"], "pooled": EV[(n, mk)]["pooled"],
                                    "n_measurable": len(EV[(n, mk)]["vals"])}
                     for n in NS for mk in MEAS},
        "nulls": {f"N{n}_{mk}": {"SEC-N1": EV[(n, mk)]["N1"], "SEC-B1": EV[(n, mk)]["B1"],
                                 "SEC-B2": EV[(n, mk)]["B2"]}
                  for n in NS for mk in MEAS},
        "G1_rate": {f"N{n}_{mk}": G1[(n, mk)] for n in NS for mk in MEAS},
        "q_top": QT,
        "SEC-X1": {"normal": x1sum, "deliberately_broken": bx,
                   "note": "재는 것은 «귀무 구현의 1종오류율» 하나뿐 — 분할의 정보량과 무관하다(§4-4)"},
        "_notation": NOTATION_POST8,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    with (ART / "cases.tsv").open("w", encoding="utf-8") as f:
        f.write("# RESULTS_SECTOR_POST8 — 건별 측정값 (기계 생성 · 🔒 판정)\n")
        f.write(f"# 주 판정 갈래 N={MAIN_N} · {MAIN_M} · 창 종료 {END}(발행 당일 금 · 거래일 봉 포함 · "
                f"B-1 · PD-1) · 실행 시 max(date) {SNAP_MAX}(행 {SNAP_ROWS}) · "
                f"시드 {SEED} · post8({POST8_LOG_NO}) 신규 exact «만»\n")
        for ln in NOTATION_POST8:
            f.write("# " + ln.replace("\n", " ") + "\n")
        f.write("#\n")
        f.write("post\titem\tname\tcode\treg\tN\tmeasure\tsector\tpeers\tG\tsec_rank\traw\tpct\treason\n")
        for n in NS:
            for mk in MEAS:
                for it, b in zip(items, BR[(n, mk)]):
                    f.write(f"{it['post']}\t{it['item_no']}\t{it['name']}\t{it['code'] or ''}\t"
                            f"{it['reg']}\t{n}\t{mk}\t{b.get('sector', '')}\t"
                            f"{b.get('peers', '')}\t{b.get('G', '')}\t{b.get('rank', '')}\t"
                            f"{('%.8f' % b['raw']) if b['ok'] else ''}\t"
                            f"{('%.6f' % b['pct']) if b['ok'] else ''}\t{b['reason']}\n")

    (BASE / "RESULTS_SECTOR_POST8_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")

    print(f"[시간] 총 {time.time() - t_start:.1f}초 · SEC-X1 {t_x1:.1f}초")
    print("[written] RESULTS_SECTOR_POST8_NUMBERS.md + sector_post8/*.json|tsv")
    print(f"[판정] SEC-P1 = {p1_word} · N1={fmt(n1p, 4)} B1={fmt(b1p, 4)} "
          f"B2={fmt(b2r * 100 if b2r is not None else None)}% · G1={g1_main * 100:.1f}% · "
          f"q_top_max={qmax:.3f} · X1(N1)={x1sum['N1']['lt05'] * 100:.1f}% · "
          f"V1={'갈림' if split else '불갈림'}")
    return 0


def run(mode):
    global OUT
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    try:
        ctx = db_context(cur)
        rc = 0
        if mode in ("both", "dryrun"):
            OUT = []
            rc |= main(cur, ctx)
        if mode in ("both", "post6"):
            OUT = []
            rc |= main_post6(cur, ctx)
        # 🔴 **덧붙인 분기.** `both` 에는 넣지 «않는다» — `both` 의 뜻(동결 두 모드)을 바꾸면
        #    `regen_gate.py --rerun` 의 기존 계약이 조용히 달라진다. post7 은 «명시»로만 돈다.
        if mode == "post7":
            OUT = []
            rc |= main_post7(cur, ctx)
        # 🔴 **덧붙인 분기**(post8) — `both` 에 넣지 «않는다»(post7 과 같은 이유). «명시»로만 돈다.
        if mode == "post8":
            OUT = []
            rc |= main_post8(cur, ctx)
    finally:
        cur.close()
        conn.close()

    # ── stdout 전용 (본문에 넣으면 --rerun 이 구조적으로 깨진다) ───────────
    def git(*a):
        try:
            return subprocess.run(["git", *a], cwd=str(BASE), capture_output=True,
                                  text=True, timeout=20).stdout.strip()
        except Exception:  # noqa: BLE001
            return "?"
    print(f"\n[git] 브랜치 {git('rev-parse', '--abbrev-ref', 'HEAD')} · "
          f"HEAD {git('rev-parse', '--short', 'HEAD')}  "
          "— 🔴 해시는 stdout 전용(본문에 박으면 --rerun 이 구조적으로 깨진다)")
    return rc


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    # 🔴 **정정(2026-09-05 · verifier D1-③)** — 예전 주석은 *「기본값이 «둘 다»여야
    #    `regen_gate.py --rerun`(인자 «없이» 호출)이 두 `PAIRS` 항목을 재생성한다」*였다.
    #    그 전제는 **소멸했다**: `regen_gate.py` 의 `PAIRS` 는 이제 모드를 «명시»해 부른다
    #    (`"run_sector.py --mode dryrun"` / `"--mode post6"` · C-23).
    #    그런데 `default="both"` 를 남겨 두면 **맨손 실행 `python run_sector.py` 한 번이
    #    동결본 `RESULTS_SECTOR_DRYRUN_NUMBERS.md` + `sector_dryrun/` 23파일을 덮어쓴다.**
    #    ⇒ 기본값을 없애고 `required=True` 로 바꾼다. 모드를 안 적으면 «돌지 않는다».
    #    🔑 ***위험한 기본값을 「호출자가 늘 인자를 준다」로 막으면, 인자를 안 주는 사람이
    #       한 명만 있어도 뚫린다 — 기본값 자체를 없애는 것이 가드다.***
    ap.add_argument("--mode", choices=("dryrun", "post6", "both", "post7", "post8"), required=True,
                    help="dryrun(배선 점검 post1~5 · 🔴 동결본을 덮어쓴다) · post6(판정) · "
                         "both(둘 다 · 🔴 동결본을 덮어쓴다) · post7(판정 · 🆕 2026-09-15) · "
                         "post8(판정 · 🆕 2026-09-24)")
    raise SystemExit(run(ap.parse_args().mode))
