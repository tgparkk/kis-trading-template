# -*- coding: utf-8 -*-
"""재현 게이트 — 커밋된 `RESULTS_*.md` 가 커밋된 스크립트의 출력인지 검사한다.

## 왜 있나 (2026-08-15)

`RESULTS_COMMON_BAND.md` 가 `solve_common_band.py` 보다 **한 판 뒤처져 있었다.**
커밋 메시지·메모리는 `b₁ ≈ 12.0% · 귀무 0.5%` 라고 적었는데 저장소의 파일은
`b₁ ≈ 1.1% · 귀무 0.6%` 였다. 그 0.6% 는 changelog 가 *「내 귀무의 결함이었다」* 고
**이미 철회한 값**이다.

🔑 ***결과 파일이 스크립트보다 한 판 뒤처지면, 이미 철회한 숫자가 저장소에 남는다.***
   자기보고(커밋 메시지)와 산출물이 갈릴 때 **산출물이 옛것일 수 있다** — 자기보고를
   게이트로 쓰지 말라는 규칙의 산출물 쪽 대응물이다.

## 무엇을 검사하나

각 `RESULTS_*.md` 에 대해 **생성 스크립트 + 그 스크립트가 import 하는 로컬 모듈 전부**의
sha256 을 매니페스트와 대조한다. 의존 폐포까지 보는 이유는 `run_hdr.py` 가
`reconstruct_prices.py` 를 import 하기 때문이다 — 후자만 고치면 전자의 산출물도 낡는다.

이 게이트가 통과한다고 **숫자가 옳다**는 뜻은 아니다. *「그 스크립트로 만든 게 맞다」* 뿐이다.
숫자 자체는 `--rerun` 으로 실제 재실행해 byte-diff 해야 확인된다.

## 실행

    python regen_gate.py            # 빠른 검사 (해시 대조만, DB 불필요)
    python regen_gate.py --rerun    # 실제 재실행 + byte-diff (DB 필요, 느림)
                                   #   🟢 **검사 전용** — 결과가 다르면 산출물을 원상복구한다.
                                   #      동결 항목(FROZEN_STALE)은 아예 건너뛴다.
    python regen_gate.py --update   # 산출물을 재생성한 «뒤» 매니페스트 갱신

재현 가능성 전제: 모든 산출 스크립트가 결정적이거나 시드가 고정돼 있다
(`run_selection.py` 는 `np.random.default_rng(20260815)`, `solve_common_band.py` ·
`run_hdr.py` 는 `random.Random(20260815)`). 시드를 바꾸면 이 게이트가 깨진다 — 그게 의도다.

## 🔴 DB 지문 (2026-08-15 추가) — 이 전제엔 «구멍»이 있었다

위 전제는 **거짓이었다.** 이 스크립트들은 전부 DB 를 읽으므로 **「결정적」이 아니라
「DB 스냅샷이 고정될 때만」 결정적**이다. 실측 — 해시 대조가 **PASS** 인데
`--rerun` 은 **17개 중 4개**를 잡았고(`SELECTION`·`HDR`·`COMMON_BAND`·`raw`),
원인은 전부 **매드업(`0039P0`) 일봉을 같은 날 8 → 32행으로 백필한 것** 하나였다.
`t3`(60일 고가 대비)가 100.0% → 44.2% 로, 롤링 결측이 1/33 → 0/33 으로 바뀌었다.

🔑 ***재현 게이트가 「스크립트가 같은가」만 보면, 데이터가 움직인 날 저장소의 숫자가
조용히 낡는다.*** 그래서 매니페스트에 **DB 지문**(대상 테이블 슬라이스의 행수·종목수·max(date))을
함께 박고 `check()` 가 대조한다. DB 에 못 붙으면 **지문 검사만 건너뛰고 그 사실을 인쇄**한다
(clean checkout·CI 에서도 해시 검사는 돌아야 하므로).

## 🔴 C-19 (2026-08-30 · `PREREG_POST6.md` §5-3) — 지문 자신이 「죽은 가드」였다

1번 슬라이스가 `daily_prices[2026-04-01..2026-08-14]` 로 **상한 고정**이었다.
⚠️ **실측으로 정정한다** — 사전등록 §5-3 표는 *「`count`·`max(date)` 가 안 움직인다」*고 적었지만
2026-08-30 실측은 `[237,992 → 238,192, 2,785, '2026-08-14']` 였다: ***창 «안» 백필은 `count` 로
잡힌다.*** 못 잡는 것은 **`max(date)` 축 = 「스냅샷이 08-14 너머로 전진했다」**이다
(실제 DB 는 08-28 까지 가 있었는데 이 슬라이스는 계속 `'2026-08-14'` 를 보고했다).
나머지 4개 슬라이스는 상한이 없어 `max(date)` 로 이동을 잡는다. 상한을 없앴다
⇒ `daily_prices[>=2026-04-01]` = `[263,096, 2,791, '2026-08-28']`.
🔑 *가드를 시험하지 않으면 그것도 장식이다* — 지문 한 글자를 흔들면 `check()` 가 실패하는지를
`tests/test_s5_fixes.py` 가 단언한다.

또 매니페스트의 `artifacts` 가 17개인데 `PAIRS` 는 21개였다(= `--update` 가 post4 이후 안 돌았다).
post5 산출물 6종을 `PAIRS` 에, 문서 10종을 `MANUAL_DOCS` 에 등재했다.

## 🔴 C-23 (2026-09-05) — `--rerun` 이 «동결본을 덮어쓰는» 경로가 열려 있었다

`PAIRS` 의 값이 «스크립트 파일명 하나»뿐이라 `rerun()` 이 `python <script>` 를 **인자 없이**
불렀다. 그런데 두 스크립트는 한 파일이 두 산출물을 만든다:

  · `run_sector.py`  — 인자 없으면 `--mode both` ⇒ **`sector_dryrun/` 23파일 + 동결
    `RESULTS_SECTOR_DRYRUN_NUMBERS.md` 를 같이 덮어쓴다.**
  · `run_ranking.py` — 인자 없으면 `--stage train` ⇒ **동결 `RESULTS_RANKING_TRAIN_NUMBERS.md`
    를 덮어쓴다.**

`rerun()` 의 원상복구는 **`PAIRS` 의 키 파일 하나만** 되돌린다 ⇒ 같은 실행이 곁다리로 만진
*다른* 산출물(특히 `sector_dryrun/` 디렉토리)은 복구되지 않는다. `FROZEN_STALE` 건너뛰기도
«그 키가 스킵될 뿐», 같은 스크립트가 **다른 키를 통해** 호출되면 그대로 돈다.

🔑 ***「동결」을 산출물 이름에만 걸면, 그 이름을 곁다리로 쓰는 실행이 동결을 뚫는다.*** 셋을 고쳤다:

  1. `PAIRS` 값이 **인자를 포함**할 수 있다(`"run_sector.py --mode post6"`). `local_deps`·sha 는
     첫 토큰(스크립트 파일명)만 본다 — `script_file()`·`script_argv()`.
  2. `rerun()` 이 `FROZEN_STALE` 항목의 스크립트를 **실행하지 않고 그 사실을 인쇄**한다
     (이미 그랬으나, 이제 인자 분기 덕에 «다른 키를 통한 우회 실행»도 동결본을 안 건드린다).
  3. `ART_DIRS` — 산출물이 **디렉토리도 같이** 쓰면 그 디렉토리를 실행 «전» 스냅샷하고,
     달라졌으면 **바이트로 되돌린 뒤 FAIL** 시킨다. 단일 파일 byte-diff 만으로는 못 보던 축이다.
     ⚠️ **정정(2026-09-05)**: 이 «항목별» 스냅샷은 `FROZEN_STALE` 키에는 **도달하지 못한다**
       (그 키는 위 2번의 `continue` 로 먼저 빠진다) ⇒ `sector_dryrun/`·`wrc_explore/` 를
       실제로 지키는 것은 3번이 아니라 아래 **4번(루프 전체 tripwire)**이다.
  4. **루프 «전체» 앞뒤 tripwire** — `ART_DIRS` 에 선언된 «모든» 디렉토리를 `rerun()` 시작 전에
     한 번 스냅샷하고 끝난 뒤 대조한다. 어느 항목이 «곁다리로» 동결 디렉토리를 건드려도 잡힌다.
     🔑 ***항목별 가드는 「그 항목이 스킵되면」 같이 스킵된다 — 스킵되지 않는 자리에 하나 더 둔다.***

## 🔴 C-24 (2026-09-05 · verifier D) — 두 구멍이 더 있었다

**D1-B1 — 실행 «실패» 경로가 산출물을 되돌리지 않았다.** `returncode != 0` 이면 디렉토리만
복구하고 단일 파일 `before` 는 되쓰지 않은 채 `continue` 했다. 스크립트가 **산출물을 쓰고 나서**
죽으면(부분 출력 후 예외) 그 파일이 그대로 남는다 ⇒ `--rerun` 이 「검사 전용」이라는 계약이
**실패 경로에서만** 깨져 있었다. 🔑 ***되돌리기는 성공 경로가 아니라 «모든» 경로에 걸어야 한다.***

**D1-B3 — `sha()` 가 작업트리 바이트를 해시해 줄끝에 종속됐다.** 이 저장소는
`core.autocrlf=input` 이라 커밋된 블롭은 LF 인데 작업트리 산출물 14개는 CRLF 다(스크립트가
Windows 기본 줄끝으로 썼다). 그중 **추적 중인 5개**는 작업트리 sha 와 HEAD 블롭 sha 가 다르며
**차이는 전부 CRLF 뿐**이다(정규화하면 일치 — 실측). ⇒ 깨끗한 체크아웃(LF)에서 `check()` 가
그 5개를 **「산출물이 손으로 편집됐다」**로 오탐한다. `sha()` 를 `\r\n` → `\n` 정규화 후
해시하도록 바꿨다. **매니페스트 키 이름은 그대로**이고, 첫 `--update` 는 «구식 raw sha 와 같은»
항목을 **낡지 않은 것으로 보고 값만 교체**한다(흡수 표시 없음) — 표현 변경을 내용 변경으로
오기록하지 않기 위해서다.
🔑 ***지문의 «잣대»를 바꿀 때는, 바꾸는 그 순간에 전건이 「바뀐 것」으로 보인다 —
   마이그레이션 규칙을 같이 넣지 않으면 그 한 번이 모든 「낡았다」 신호를 덮어쓴다.***

가드 시험은 `tests/test_regen_gate_args.py` — 「인자 없는 `run_sector.py` 호출이 없다」,
「실패 경로도 되돌린다」, 「정규화 sha == `git show HEAD:<path>` 블롭 sha」를 단언한다.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
MANIFEST = BASE / "REGEN_MANIFEST.json"

# 🔴 C-24 — `--update` 가 「잣대 변경으로 값만 교체한」 항목을 여기 모아 인쇄한다(조용한 교체 금지).
MIGRATED: list[str] = []

# 산출물 → 생성 스크립트
PAIRS = {
    "RESULTS_RECONSTRUCT.md": "reconstruct_prices.py",
    "RESULTS_COMMON_BAND.md": "solve_common_band.py",
    "RESULTS_HDR.md": "run_hdr.py",
    "RESULTS_Q1_V2.md": "run_q1_v2.py",
    "RESULTS_SELECTION.md": "run_selection.py",
    "RESULTS_raw.md": "run_tests.py",
    "RESULTS_SELLTIMING.md": "run_selltiming.py",
    "RESULTS_MINUTE_ENTRY.md": "run_minute_entry.py",
    "RESULTS_MINUTE_SELLTIMING.md": "run_minute_selltiming.py",
    "RESULTS_SELECTION_FLOW.md": "run_selection_flow.py",
    "RESULTS_CONDITIONAL.md": "run_conditional.py",
    "RESULTS_GAPFILL.md": "run_gapfill.py",
    "RESULTS_LEG_STRUCTURE.md": "run_leg_structure.py",
    "RESULTS_CONDITIONAL_WIDE.md": "run_conditional_wide.py",
    "RESULTS_INTRADAY_PICK.md": "run_intraday_pick.py",
    "RESULTS_FLOW_NORM.md": "run_flow_norm.py",
    "RESULTS_SELECTION_ROBUST.md": "run_selection_robust.py",
    "RESULTS_D1_OOS_NUMBERS.md": "run_d1_oos.py",
    "RESULTS_EXIT_V2_POST4_NUMBERS.md": "run_exit_v2_post4.py",
    "RESULTS_SELECTION_POST4_NUMBERS.md": "run_selection_post4.py",
    "RESULTS_RECONSTRUCT_POST4_NUMBERS.md": "run_reconstruct_post4.py",
    # 🔴 C-19 (`PREREG_POST6.md` §5-3-2) — post5 산출물 6종이 어디에도 등재돼 있지 않았다
    #    (`--update` 가 post4 이후 안 돌았다). 등재 없이는 게이트가 그 파일들을 «안 본다».
    "RESULTS_D1_OOS_POST5_NUMBERS.md": "run_d1_oos_post5.py",
    "RESULTS_EXIT_V2_POST5_NUMBERS.md": "run_exit_v2_post5.py",
    "RESULTS_SELECTION_POST5_NUMBERS.md": "run_selection_post5.py",
    "RESULTS_REGDAY_POST5_NUMBERS.md": "run_regday_post5.py",
    "RESULTS_RECONSTRUCT_POST5_NUMBERS.md": "run_reconstruct_post5.py",
    "RESULTS_LADDER_TRANCHE_NUMBERS.md": "run_ladder_tranche.py",
    # 🔴 §5 작업이 «새로» 만든 기계 생성 산출물 — 등재하지 않으면 §5-3 이 지적한 결함
    #    (「post5 산출물이 어디에도 없다」)을 그 자리에서 다시 만드는 것이다.
    "RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md": "run_reconstruct_post4_exact.py",   # C-22
    "RESULTS_S5_SIDEBYSIDE.md": "run_s5_sidebyside.py",                               # C-17·18·20·21
    # 🔴 `RNK-` 후보 랭킹 축 (`PREREG_RANKING.md` §5-7 이 «문언으로» 요구한 등재).
    #    두 산출물이 같은 스크립트에서 나온다 — `--stage train` / `--stage post6`.
    #    🔴 C-23 — **인자를 반드시 적는다.** 인자를 비우면 `rerun()` 이 기본값(`--stage train`)으로
    #      돌아 동결본 `RESULTS_RANKING_TRAIN_NUMBERS.md` 를 덮어쓴다.
    "RESULTS_RANKING_TRAIN_NUMBERS.md": "run_ranking.py --stage train",
    "RESULTS_RANKING_POST6_NUMBERS.md": "run_ranking.py --stage post6",
    # 🔴 `WRC-` 가중 평단 복원 축 (`PREREG_WEIGHTED_RECON.md` §5-2 4번이 «문언으로» 요구한 등재).
    #    §0-3 의 3번(탐색 실행) 산출물이며 대상은 post4·post5 «만»이다 — post6 판정은 별도
    #    스크립트(`run_wrc_post6.py`)로 나온다. 탐색본은 2026-09-05 부로 `FROZEN_STALE`.
    "RESULTS_WRC_EXPLORE.md": "run_wrc_explore.py",
    # 🔴 `SEC-` 섹터 동반 상승 축 (`PREREG_SECTOR_COMOVE.md` §5 7번이 «문언으로» 요구한 등재).
    #    §0-4 의 4번(배선 점검) 산출물이며 대상은 post1~5 «만»이다.
    #    두 산출물이 같은 스크립트에서 나온다 — 🔴 C-23 으로 **모드를 명시**한다(기본값 `both` 가
    #    동결본 `RESULTS_SECTOR_DRYRUN_NUMBERS.md` + `sector_dryrun/` 23파일을 덮어썼다).
    "RESULTS_SECTOR_DRYRUN_NUMBERS.md": "run_sector.py --mode dryrun",
    "RESULTS_SECTOR_POST6_NUMBERS.md": "run_sector.py --mode post6",
    # 🔴 2026-09-04 6번째 글(`224401108114`) 산출물 7종 — §5-3 이 잡은 결함
    #    (「post5 산출물이 어디에도 등재돼 있지 않다」)을 이번 글에서 되풀이하지 않는다.
    #    각 축은 post5 판을 승계한 «별도 파일»이다(`run_*_post5.py` → `run_*_post6.py`).
    "RESULTS_SELECTION_POST6_NUMBERS.md": "run_selection_post6.py",
    "RESULTS_D1_OOS_POST6_NUMBERS.md": "run_d1_oos_post6.py",
    "RESULTS_REGDAY_POST6_NUMBERS.md": "run_regday_post6.py",
    "RESULTS_EXIT_V2_POST6_NUMBERS.md": "run_exit_v2_post6.py",
    "RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md": "run_ladder_tranche_post6.py",
    "RESULTS_RECONSTRUCT_POST6_NUMBERS.md": "run_reconstruct_post6.py",
    "RESULTS_WRC_POST6_NUMBERS.md": "run_wrc_post6.py",
}

# 🔴 C-23 — 산출물이 «파일 하나»가 아닌 것들. `--rerun` 이 이 디렉토리까지 스냅샷·대조하고,
#    달라지면 **바이트로 되돌린 뒤 FAIL** 시킨다. 등재하지 않으면 디렉토리 산출물은 게이트에
#    «안 보인다» — `PAIRS` 미등재와 같은 결함의 디렉토리 판이다.
ART_DIRS = {
    "RESULTS_SECTOR_DRYRUN_NUMBERS.md": ("sector_dryrun",),
    "RESULTS_SECTOR_POST6_NUMBERS.md": ("sector_post6",),
    "RESULTS_WRC_EXPLORE.md": ("wrc_explore",),
    "RESULTS_WRC_POST6_NUMBERS.md": ("wrc_post6",),
}


def script_file(spec: str) -> str:
    """`PAIRS` 값에서 **스크립트 파일명**만. 인자는 버린다(sha·의존 폐포의 축은 파일이다)."""
    return spec.split()[0]


def script_argv(spec: str) -> list[str]:
    """`PAIRS` 값을 실행 인자 리스트로. 🔴 인자를 흘리면 기본 모드가 동결본을 덮어쓴다(C-23)."""
    return spec.split()

# 🔴 «아직 만들어지지 않은» 산출물 — 등재는 §5-7 이 요구하는데, 그 파일은 그 글이 와야 생긴다.
#    ⇒ check() 가 「산출물이 없다」로 FAIL 하는 대신 **🟡 미생성(예정)** 으로 인쇄한다.
#    🔑 이건 게이트를 «약화»시키는 게 아니다 — 반대다. 등재를 미루면 그 파일은 게이트에 «안 보이고»
#      (§5-3 이 지적한 「post5 산출물이 하나도 등재돼 있지 않다」가 그 실패다), 등재만 하면
#      게이트가 «상시 FAIL» 이라 아무도 안 본다. 두 실패를 다 피하는 자리가 여기다.
#    ⚠️ 파일이 «생기면» 이 목록에서 빼야 한다 — 남겨 두면 그때부터 진짜 가드가 죽는다.
#       (check() 가 파일이 존재하는데 PENDING 인 항목을 발견하면 FAIL 시킨다.)
#    🟢 2026-09-05 — **비었다.** 6번째 글(`224401108114`)이 2026-09-04 18:50 에 도착해
#      `RESULTS_RANKING_POST6_NUMBERS.md`·`RESULTS_SECTOR_POST6_NUMBERS.md` 가 «생겼으므로»
#      위 ⚠️ 규칙대로 PENDING 에서 뺐다(남겨 두면 check() 가 「생겼는데 PENDING 이다」로 FAIL 한다).
#      🔑 비어 있다고 이 자리를 지우지 말 것 — 7번째 글의 산출물이 다시 여기로 들어온다.
PENDING: dict[str, str] = {}

# 🔴 `MANUAL_DOCS` 쪽의 같은 것 — 등재는 §5-7 이 요구하는데 파일은 그 글이 와야 생긴다.
#    ⚠️ `FREEZE_RANKING_<날짜>.md` 는 여기 넣지 «않는다» — 그건 4단계에서 «지금» 만드는 파일이라
#      없으면 진짜 FAIL 이어야 한다(이름 오타를 잡는 것이 G-1 의 목적이다).
#    🟢 2026-09-05 — **비었다.** 두 산문(`RESULTS_RANKING_POST6.md`·`RESULTS_SECTOR_POST6.md`)이
#      생겼다 ⇒ `MANUAL_DOCS` 의 존재 검사(G-1)가 그 두 이름에 «진짜로» 도는 자리로 돌아왔다.
PENDING_DOCS: dict[str, str] = {}

# 🔴 §5(C-17·C-20) 정정으로 «스크립트는 바뀌었으나 산출물은 재생성하지 않은» 것들.
#    `PREREG_POST6.md` §5-1-5(*「과거 산출물을 다시 재지 않는다」*) · §5-4-2(*「과거 발표값을
#    조용히 갱신하지 않는다」*)가 재생성을 금지한다. ⇒ 게이트가 이 사실을 «조용히» 삼키지 않도록
#    매니페스트에 사유를 박고 check() 가 매번 인쇄한다. 정정 반영값은 나란히 인쇄한 별도 산출물에 있다.
#    🔑 여기 등재해도 «이 사유로 기록된 판본»에서 또 바뀌면 그때는 정상 FAIL 이다(deps 대조는 계속).
FROZEN_STALE = {
    "RESULTS_SELECTION.md":
        "C-17(f9 NaN) — 정정 전 판본의 값. 재측정 금지(§5-1-5) · 전/후는 RESULTS_S5_SIDEBYSIDE.md",
    "RESULTS_SELECTION_POST4_NUMBERS.md":
        "C-17(f9 NaN)+med NaN 안전 — 재측정 금지(§5-1-5) · 전/후는 RESULTS_S5_SIDEBYSIDE.md",
    "RESULTS_SELECTION_POST5_NUMBERS.md":
        "C-17(f9 NaN) — post5 판정(`SEL-S3`=47.9 ✅)은 그대로 둔다(§5-1-5)",
    "RESULTS_D1_OOS_NUMBERS.md":
        "C-20(중앙값 관용구) — post4 `m` 중앙 2 는 분모 5(홀수)라 값 불변(§5-4-2)",
    "RESULTS_GAPFILL.md":
        "C-20(중앙값 관용구) — 옛 산출물. 재생성 금지(§5-4-2)",
    "RESULTS_MINUTE_ENTRY.md":
        "C-20(중앙값 관용구) — 옛 산출물. 재생성 금지(§5-4-2)",
    "RESULTS_RECONSTRUCT_POST4_NUMBERS.md":
        "C-20(중앙값 관용구) — 발표값 유지. 정확법 재계산은 RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md(C-22)",
    # 🔴 2026-09-05 추가 — post6 작업이 «입력 DB» 와 «스크립트» 를 둘 다 움직였는데, 아래 셋은
    #    이미 발표·동결된 판본이라 재측정하지 않는다(`PREREG_POST6.md` §5-1-5·§5-4-2 · 각 FREEZE 문서).
    #    ⇒ 사유를 매니페스트에 박고 check() 가 매번 인쇄한다(조용한 통과 금지).
    # 🔴 사유 정정(2026-09-05 · verifier D1-B2 · DB SELECT 로 직접 확인):
    #    ⓐ 「07-28 유니버스 2,572→2,574」는 **오기**였다. run_ranking.py:100 의
    #      `TRAIN_PROBE_COMPOSE` 는 «세 양»(그날 전 종목 / close>0 / 유니버스)이고 실측은
    #      (2572,2572,2570) → (2574,2574,2570) ⇒ 움직인 것은 앞 «두» 양이고
    #      **유니버스 2,570 은 불변**이다(`RESULTS_RANKING_TRAIN_NUMBERS.md`:83 이 세 양을 구분).
    #    ⓑ 원인이 하나 빠져 있었다 — 02826K 말고 **03473K 82행**도 들어왔다.
    #      실측 created_at: 03473K = 2026-09-02 09:00:38(82행 전건 동일 · 04-06~08-04)
    #                      02826K = 2026-09-04 09:01:06(81행 전건 동일 · 04-07~08-04)
    "RESULTS_RANKING_TRAIN_NUMBERS.md":
        "동결(FREEZE_RANKING_2026-08-31) — 입력 DB 가 이동했다: 09-04 W1 이 02826K 04-07~08-04 "
        "구멍 81행 · 09-02 W1 이 03473K 82행을 INSERT · 07-28 «그날 전 종목/close>0» "
        "2,572→2,574(유니버스 2,570 불변) · 08-05 코호트 191→189. "
        "+ run_ranking.py 에 post6 모드를 더했다(코드 변경은 훈련 수치에 0줄 영향 — 실증 완료). "
        "🔴 재측정 금지 · 선택 규칙 RNK-A1 은 이 동결본에서 왔다(홀드아웃의 근거)",
    "RESULTS_WRC_EXPLORE.md":
        "동결(FREEZE_WRC_2026-09-02) — run_wrc_explore.py 에 post6 제외 필터 +11줄 · 입력 DB 이동. "
        "원장 유래 값은 전건 동일함을 실증했다. 🔴 재측정 금지(탐색값이 post6 판정 문턱의 근거)",
    "RESULTS_SECTOR_DRYRUN_NUMBERS.md":
        "동결(FREEZE_SECTOR_2026-09-03) — run_sector.py 에 모드 분기가 들어갔고 DB 가 이동했으나 "
        "이동분은 조인 «전» 부기 열에만 닿아 측정값 0줄 불변임을 실증했다. "
        "🔴 **--rerun 금지** — 기본 모드(both)면 sector_dryrun/ 23파일까지 덮어쓴다(C-23)",
}

# 스크립트가 만들지 않는 문서 — 사람이 쓴 것. 게이트 대상 아님을 명시해 둔다.
MANUAL_DOCS = [
    "README.md", "RESULTS.md",
    "PREREG.md", "PREREG_Q1_V2.md", "PREREG_SELECTION.md", "PREREG_HDR.md",
    "PREREG_BUYLADDER.md", "PREREG_EXIT_V2.md", "FINDING_THEME_AXIS.md", "PREREG_SELLTIMING.md",
    "PREREG_MINUTE_FLOW.md", "PREREG_CONDITIONAL.md", "PREREG_LEG_STRUCTURE.md", "PREREG_INTRADAY_PICK.md",
    "PREREG_FLOW_NORM.md", "PREREG_SELECTION_ROBUST.md",
    # 2026-08-22 4번째 글 계열 — 산문은 사람이 쓴다. 숫자는 RESULTS_D1_OOS_NUMBERS.md 가 게이트 대상.
    "INTAKE_2026-08-22_post4.md", "RESULTS_D1_OOS.md", "LABELS_2026-08-22_post4.md", "RESULTS_EXIT_V2_POST4.md", "RESULTS_SELECTION_POST4.md", "RESULTS_RECONSTRUCT_POST4.md",
    "PREREG_D1_OOS.md", "PREREG_LADDER_TRANCHE.md", "PREREG_REGDAY_MEASURE.md",
    # 🔴 C-19 (`PREREG_POST6.md` §5-3-3) — 2026-08-29 5번째 글 계열 + 6번째 글 사전등록.
    "INTAKE_2026-08-29_post5.md", "LABELS_2026-08-29_post5.md", "PREDECISION_2026-08-29_post5.md",
    "RESULTS_D1_OOS_POST5.md", "RESULTS_EXIT_V2_POST5.md", "RESULTS_SELECTION_POST5.md",
    "RESULTS_REGDAY_POST5.md", "RESULTS_RECONSTRUCT_POST5.md", "RESULTS_LADDER_TRANCHE.md",
    "PREREG_POST6.md",
    # 🔴 `RNK-` 후보 랭킹 축 (`PREREG_RANKING.md` §5-7). 산문은 사람이 쓴다 —
    #    숫자는 RESULTS_RANKING_*_NUMBERS.md 가 PAIRS 대상이다.
    #    ⚠️ `FREEZE_RANKING_<날짜>.md` 와 `RESULTS_RANKING_POST6.md` 는 아직 «없다»
    #      (§0-3 의 4·6단계 산출물) — MANUAL_DOCS 는 존재를 검사하지 않으므로 미리 적어 둔다.
    "PREREG_RANKING.md", "RESULTS_RANKING_TRAIN.md",
    "FREEZE_RANKING_2026-08-31.md", "RESULTS_RANKING_POST6.md",
    # 🔴 `WRC-` 가중 평단 복원 축 (`PREREG_WEIGHTED_RECON.md` §5-2 4번). 산문·동결문은 사람이 쓴다 —
    #    숫자는 `RESULTS_WRC_EXPLORE.md`(PAIRS 대상)에 있다. 동결문은 §0-3 **4번** 산출물이다.
    "PREREG_WEIGHTED_RECON.md", "FREEZE_WRC_2026-09-02.md",
    # 🔴 `SEC-` 섹터 동반 상승 축 (`PREREG_SECTOR_COMOVE.md` §5 7번). 산문·동결문은 사람이 쓴다 —
    #    숫자는 `RESULTS_SECTOR_DRYRUN_NUMBERS.md`(PAIRS 대상)에 있다.
    #    🔒 `FREEZE_SECTOR_2026-09-03.md` 는 §0-4 의 **5단계** 산출물이며 **만드는 «순간» 등재**한다
    #      (`FREEZE_RANKING_2026-08-31.md`·`FREEZE_WRC_2026-09-02.md` 와 같은 G-1 전례).
    #      🔴 4단계에서는 «일부러» 등재하지 않았다 — 그때는 파일이 없었고, 이름만 먼저 박으면
    #      G-1(존재 검사)이 «없는 파일»로 상시 FAIL 해서 진짜 가드가 죽는다.
    "PREREG_SECTOR_COMOVE.md", "RESULTS_SECTOR_DRYRUN.md", "RESULTS_SECTOR_POST6.md",
    "FREEZE_SECTOR_2026-09-03.md",
    # 🔴 2026-09-05 — 2026-09-04 6번째 글(`224401108114`) 계열. 산문·인테이크·라벨은 사람이 쓴다 —
    #    숫자는 `RESULTS_*_POST6_NUMBERS.md` 가 `PAIRS` 대상이다(§5-3 이 잡은 「post5 산출물이
    #    어디에도 등재돼 있지 않다」를 이번 글에서 되풀이하지 않는다).
    #    ⚠️ `RESULTS_RANKING_POST6.md`·`RESULTS_SECTOR_POST6.md` 는 위 `RNK-`·`SEC-` 줄에 이미 있다.
    "INTAKE_2026-09-04_post6.md", "PREDECISION_2026-09-04_post6.md", "LABELS_2026-09-04_post6.md",
    "RESULTS_SELECTION_POST6.md", "RESULTS_D1_OOS_POST6.md", "RESULTS_REGDAY_POST6.md",
    "RESULTS_EXIT_V2_POST6.md", "RESULTS_LADDER_TRANCHE_POST6.md",
    "RESULTS_RECONSTRUCT_POST6.md", "RESULTS_WRC_POST6.md",
    # 🔴 `verify_ledger_post6.py` 는 **일부러 등재하지 않는다** — post5 판의 처리 전례를 따른다:
    #    실측으로 `verify_ledger_post5.py` 는 `PAIRS`·`MANUAL_DOCS`·어느 의존 폐포에도 **없다**.
    #    원장 검증기는 `RESULTS_*.md` 를 만들지 않아 재현 게이트의 대상축이 아니고, `MANUAL_DOCS` 는
    #    「사람이 쓴 «문서»」 목록이다(스크립트를 넣으면 그 목록의 뜻이 흐려진다).
    #    회귀는 `test_post6_ledger.py`·`tests/test_s5_fixes.py` 가 맡는다.
    # 🔴 2026-09-11 — 사람이 쓴 사전등록 2종. `PREREG_ANCHOR_REDESIGN.md` 는 §11 이 등재 의무를
    #    «신고»만 하고 미뤄 둔 빚이다(그 사이 G-1 에 «안 보였다») ⇒ 이 커밋에서 같이 갚는다.
    "PREREG_GRADE_TIERS.md", "PREREG_ANCHOR_REDESIGN.md",
]


# 🔴 DB 지문 — 이 디렉토리의 스크립트가 실제로 읽는 슬라이스만. 전 테이블 count(*) 는
#    `minute_candles`(4,900만 행)에서 느리므로 **범위를 좁혀 정확하게** 잰다.
#
# 🔴 C-19 (`PREREG_POST6.md` §5-3-1) — 1번 슬라이스의 **상한이 `2026-08-14` 로 고정**돼 있었다.
#    08-15 이후 행이 창 «밖»이라 스냅샷이 움직여도 `count`·`max(date)` 가 안 움직인다 ⇒ 그 축만
#    못 재는 「죽은 가드」였다. 하필 이 디렉토리가 «가장 많이 읽는 표»가 `daily_prices` 다.
#    ⇒ 상한을 없앤다. 스냅샷이 움직이면 **반드시** 지문이 움직인다.
FINGERPRINT_SQL = {
    "daily_prices[>=2026-04-01]":
        "SELECT count(*), count(DISTINCT stock_code), max(date) FROM daily_prices "
        "WHERE date >= '2026-04-01'",
    "minute_candles[>=20260701]":
        "SELECT count(*), count(DISTINCT stock_code), max(date) FROM minute_candles "
        "WHERE date >= '20260701'",
    "investor_trend_daily":
        "SELECT count(*), count(DISTINCT stock_code), max(date) FROM investor_trend_daily",
    "short_sale_daily":
        "SELECT count(*), count(DISTINCT stock_code), max(date) FROM short_sale_daily",
    "program_trade_daily":
        "SELECT count(*), count(DISTINCT stock_code), max(date) FROM program_trade_daily",
}


def db_fingerprint():
    """(지문, 건너뛴 사유). DB 에 못 붙으면 (None, 사유) — 해시 검사는 계속 돌게 한다."""
    try:
        import psycopg2  # noqa: PLC0415  (DB 없는 환경에서도 해시 검사는 돌아야 한다)

        from run_tests import DSN
        conn = psycopg2.connect(connect_timeout=5, **DSN)
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e).strip().splitlines()[0][:120]}"
    try:
        out = {}
        with conn.cursor() as cur:
            for k, q in FINGERPRINT_SQL.items():
                cur.execute(q)
                r = cur.fetchone()
                out[k] = [int(r[0] or 0), int(r[1] or 0), str(r[2])]
        return out, None
    finally:
        conn.close()


def sha(p: Path) -> str:
    """🔴 C-24(D1-B3) — **줄끝을 정규화한 뒤** 해시한다.

    `core.autocrlf=input` 이라 커밋 블롭은 LF 인데 작업트리 산출물 14개는 CRLF 다.
    작업트리 바이트를 그대로 해시하면 **깨끗한 체크아웃에서 「손으로 편집됐다」로 오탐**한다
    (추적 산출물 5개가 실제로 그 상태였고, 차이는 전부 CRLF 뿐임을 실측했다).
    🔑 *지문은 「내용이 같은가」를 물어야지 「어느 OS 가 썼는가」를 물으면 안 된다.*"""
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def sha_raw(p: Path) -> str:
    """C-24 이전의 «구식» 해시(작업트리 바이트 그대로). **마이그레이션 판정 전용**이다 —
    옛 매니페스트 값이 이것과 같으면 그 항목은 「낡은 것」이 아니라 「잣대가 바뀐 것」이다."""
    return hashlib.sha256(p.read_bytes()).hexdigest()


def local_deps(script: str, seen: set[str] | None = None) -> set[str]:
    """스크립트가 import 하는 **로컬 모듈**의 폐포 (자기 자신 포함)."""
    seen = seen if seen is not None else set()
    if script in seen:
        return seen
    seen.add(script)
    tree = ast.parse((BASE / script).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for n in names:
            cand = f"{n.split('.')[0]}.py"
            if (BASE / cand).exists():
                local_deps(cand, seen)
    return seen


def build(fp=None, old=None) -> dict:
    """`old` 를 주면(= `--update`) **재기준선 시점에 이미 어긋나 있던 항목**을 자동으로 기록한다.

    🔴 이게 없으면 `--update` 한 번이 그동안 쌓인 「낡았다」 신호를 **조용히 전부 지운다.**
       2026-08-30 실측: `--update` 직전 `PAIRS` 21개 중 **일치하는 항목이 0개**였다
       (13개는 의존 모듈이 바뀌었고 4개는 손으로 편집됐고 4개는 아예 미등재).
       ⇒ 흡수하되 **흡수했다는 사실을 매니페스트가 이고 간다.**"""
    MIGRATED.clear()
    entries = {}
    for out, spec in sorted(PAIRS.items()):
        # 🔴 C-23 — sha·의존 폐포는 **파일명**으로, 실행은 **인자 포함**으로. 둘을 섞으면
        #    `local_deps("run_sector.py --mode post6")` 가 파일을 못 찾아 게이트가 크래시한다.
        script = script_file(spec)
        deps = sorted(local_deps(script))
        e = {
            "script": spec,
            "deps": {d: sha(BASE / d) for d in deps},
            "results_sha256": sha(BASE / out) if (BASE / out).exists() else None,
        }
        if out in FROZEN_STALE:
            # 🔴 이 항목의 `deps` 는 「이 산출물을 만든 판본」이 **아니다.** 사유를 매니페스트에 박는다.
            e["frozen_reason"] = FROZEN_STALE[out]
        if old is not None:
            o = old.get(out)
            if o is None:
                e["absorbed_stale"] = {
                    "why": "이전 매니페스트에 «없었다» — 이번 재기준선에서 처음 등재. "
                           "재현 확인(`--rerun`)을 거치지 않았다.",
                    "deps_changed": [], "results_changed": False}
            else:
                # 🔴 C-24 마이그레이션 — 옛 값이 «구식 raw sha» 와 같으면 그 항목은 «안 낡았다».
                #    잣대(`sha()`)만 바뀐 것이므로 값만 새 정규화 sha 로 교체하고 흡수는 안 남긴다.
                def _same(old_h, path):
                    return old_h == sha(path) or (old_h is not None
                                                  and old_h == sha_raw(path))

                dc = [d for d, h in e["deps"].items()
                      if not _same(o["deps"].get(d), BASE / d)]
                rc = ((BASE / out).exists()
                      and not _same(o.get("results_sha256"), BASE / out))
                if not (BASE / out).exists():
                    rc = o.get("results_sha256") is not None
                migrated = ([d for d in e["deps"] if o["deps"].get(d) not in (None, e["deps"][d])
                             and o["deps"].get(d) == sha_raw(BASE / d)]
                            + ([out] if ((BASE / out).exists()
                                         and o.get("results_sha256") != e["results_sha256"]
                                         and o.get("results_sha256") == sha_raw(BASE / out))
                               else []))
                if migrated:
                    MIGRATED.extend(f"{out} :: {m}" for m in migrated)
                if o.get("absorbed_stale"):
                    # 🔴 재생성만으로는 «안» 지운다 — 지우는 유일한 길은 `--rerun` 성공이다.
                    #    (스크립트와 산출물을 같이 바꾸면 「고치고 재생성했다」와 구별이 안 된다.)
                    e["absorbed_stale"] = o["absorbed_stale"]
                elif dc or rc:
                    e["absorbed_stale"] = {
                        "why": "재기준선 시점에 **이미 낡아 있었다** — 재생성하지 않고 흡수했다"
                               "(`PREREG_POST6.md` §5-3-4). 🔴 「이 스크립트로 만들었다」의 증거가 아니다.",
                        "deps_changed": dc, "results_changed": rc,
                        "prev_results_sha256": o.get("results_sha256")}
        entries[out] = e
    return {"manual_docs": MANUAL_DOCS, "db_fingerprint": fp, "artifacts": entries}


def check() -> int:
    if not MANIFEST.exists():
        print("🔴 REGEN_MANIFEST.json 이 없다 — `--update` 로 먼저 만들 것.")
        return 2
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    old = man["artifacts"]
    new = build()["artifacts"]
    fails: list[str] = []
    notes: list[str] = []

    # ── DB 지문 대조 (해시가 못 잡는 축) ────────────────────────────────────
    fp_old = man.get("db_fingerprint")
    fp_new, why = db_fingerprint()
    if fp_new is None:
        print(f"  ⚠️ DB 지문 검사 건너뜀 — {why}")
        print("     (해시 검사만 돈다. 「스크립트가 같다」는 「숫자가 같다」가 아니다.)")
    elif fp_old is None:
        print("  ⚠️ 매니페스트에 DB 지문이 없다 — `--update` 로 기준선을 박을 것.")
    else:
        moved = [k for k in fp_new if fp_old.get(k) != fp_new[k]]
        if moved:
            for k in moved:
                fails.append(f"DB 지문: 🔴 **`{k}` 가 움직였다** — "
                             f"기준선 {fp_old.get(k)} → 현재 {fp_new[k]}")
            fails.append("⇒ 🔑 **DB 가 바뀌었으면 산출물은 스크립트와 일치해도 «낡았다».** "
                         "`--rerun` 으로 실제 재실행해 확인한 뒤 `--update`.")
        else:
            print(f"  ✅ DB 지문 일치 ({len(fp_new)}개 슬라이스)")
    for out in sorted(PAIRS):
        o, n = old.get(out), new[out]
        if o is None:
            fails.append(f"{out}: 매니페스트에 없음")
            continue
        if not (BASE / out).exists():
            if out in PENDING:
                notes.append(out)
                print(f"  🟡 {out}  ({n['script']}) — **미생성(예정)**")
                print(f"       🔴 {PENDING[out]}")
                continue
            fails.append(f"{out}: 산출물이 없다")
            continue
        if out in PENDING:
            # 🔴 파일이 «생겼는데» PENDING 에 남아 있으면 그때부터 이 항목은 진짜 죽은 가드다.
            fails.append(f"{out}: 🔴 **산출물이 생겼는데 `PENDING` 에 남아 있다** "
                         f"⇒ `regen_gate.py` 의 `PENDING` 에서 뺄 것")
            continue
        stale = [d for d, h in n["deps"].items() if o["deps"].get(d) != h]
        if stale:
            fails.append(
                f"{out}: 🔴 **산출물이 스크립트보다 뒤처졌다** — 바뀐 모듈 {stale} "
                f"⇒ `python {n['script']}` 로 재생성한 뒤 `--update`")
        elif o["results_sha256"] != n["results_sha256"]:
            fails.append(
                f"{out}: 🔴 산출물이 손으로 편집됐다(스크립트는 그대로) "
                f"⇒ 편집분을 스크립트에 넣고 재생성할 것")
        elif out in FROZEN_STALE or o.get("frozen_reason") or o.get("absorbed_stale"):
            notes.append(out)
            frz = o.get("frozen_reason") or FROZEN_STALE.get(out)
            ab = o.get("absorbed_stale")
            print(f"  🟡 {out}  ({n['script']} + deps {len(n['deps'])}개)")
            if frz:
                print(f"       🔴 정정 미반영(동결): {frz}")
            if ab:
                print(f"       🔴 흡수: {ab['why']}"
                      + (f" · 바뀐 모듈 {ab['deps_changed']}" if ab.get("deps_changed") else ""))
        else:
            print(f"  ✅ {out}  ({n['script']} + deps {len(n['deps'])}개)")
    # ── G-1: `MANUAL_DOCS` 존재 검사 ────────────────────────────────────────
    # 🔴 여태 `MANUAL_DOCS` 는 매니페스트에 «적히기만» 하고 아무도 안 봤다. 파일명을 틀리게 적거나
    #    (`FREEZE_RANKING_<날짜>.md` 처럼 날짜가 들어가는 이름이 특히 위험하다) 문서를 지워도
    #    게이트가 «조용히» 통과한다 ⇒ 「등재했다」가 「그 파일이 있다」를 뜻하지 않았다.
    #    🔑 이건 `PREREG_POST6.md` §5-3 이 잡은 「어디에도 등재돼 있지 않다」의 «쌍둥이» 결함이다.
    missing_docs = [d for d in MANUAL_DOCS if not (BASE / d).exists()]
    for d in sorted(set(PENDING_DOCS) & set(MANUAL_DOCS)):
        if (BASE / d).exists():
            # 🔴 PAIRS 쪽 PENDING 과 같은 반전 — 생겼는데 아직 예정으로 적혀 있으면 그때부터 죽은 가드다.
            fails.append(f"MANUAL_DOCS: 🔴 **`{d}` 가 생겼는데 `PENDING_DOCS` 에 남아 있다** "
                         f"⇒ `PENDING_DOCS` 에서 뺄 것")
    for d in missing_docs:
        if d in PENDING_DOCS:
            notes.append(d)
            print(f"  🟡 MANUAL_DOCS `{d}` — **미생성(예정)**")
            print(f"       🔴 {PENDING_DOCS[d]}")
            continue
        fails.append(f"MANUAL_DOCS: 🔴 **`{d}` 가 없다** — 등재된 이름과 실제 파일명이 "
                     f"어긋났거나 문서가 삭제됐다")
    if [d for d in missing_docs if d not in PENDING_DOCS]:
        fails.append("⇒ 🔑 **「등재했다」는 「그 파일이 있다」가 아니다.** 이름을 고치거나 "
                     "`MANUAL_DOCS` 에서 뺄 것.")
    elif not missing_docs:
        print(f"  ✅ MANUAL_DOCS {len(MANUAL_DOCS)}건 전부 존재")

    if fails:
        print("\n".join("  " + f for f in fails))
        print(f"\n🔴 재현 게이트 FAIL — {len(fails)}건")
        return 1
    print("\n🟢 재현 게이트 PASS — 모든 산출물이 현재 스크립트 판본과 일치한다.")
    print("⚠️ 단 이건 「그 스크립트로 만들었다」일 뿐 「숫자가 옳다」가 아니다. "
          "숫자 확인은 `--rerun`.")
    if notes:
        print(f"🟡 그중 **{len(notes)}건은 재생성되지 않은 채 기준선에 들어간 항목**이다 "
              "— 위 사유를 볼 것. 🔑 ***그 항목들에 대해서는 이 PASS 가 "
              "「이 스크립트로 만들었다」의 증거가 아니다.***")
    return 0


def clear_absorbed(verified: list) -> list:
    """`--rerun` 이 byte 단위로 확인한 항목의 `absorbed_stale` 을 지운다.

    🔑 **재현 확인이 「흡수」를 지우는 «유일한» 길이다.** 재생성만으로는 안 지운다 —
       스크립트와 산출물을 같이 바꾸면 「고치고 재생성했다」와 「낡은 채 흡수했다」가 구별되지 않는다."""
    if not verified or not MANIFEST.exists():
        return []
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cleared = [k for k in verified if man["artifacts"].get(k, {}).pop("absorbed_stale", None)]
    if cleared:
        MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    return cleared


def _dir_snapshot(names) -> dict:
    """C-23 — 디렉토리 산출물의 «바이트» 스냅샷 {상대경로: bytes}."""
    snap = {}
    for name in names:
        d = BASE / name
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file():
                snap[p.relative_to(BASE).as_posix()] = p.read_bytes()
    return snap


def _dir_restore(snap: dict, names) -> None:
    """스냅샷으로 되돌린다 — 실행이 «새로» 만든 파일은 지운다(원상복구가 목적이다)."""
    for name in names:
        d = BASE / name
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.relative_to(BASE).as_posix() not in snap:
                p.unlink()
    for rel, b in snap.items():
        p = BASE / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.read_bytes() != b:
            p.write_bytes(b)


def rerun() -> int:
    """실제 재실행 + byte-diff. 결정적/시드고정이므로 동일해야 한다."""
    fails = []
    verified = []
    # 🔴 C-23 4번(verifier D1-①) — 루프 «전체» tripwire. 항목별 스냅샷은 `FROZEN_STALE` 키에
    #    도달하지 못하므로(그 키는 아래에서 `continue` 로 먼저 빠진다) `sector_dryrun/`·
    #    `wrc_explore/` 를 실제로 지키는 것은 여기다. 어느 항목이 곁다리로 건드려도 잡힌다.
    all_dirs = tuple(sorted({d for ds in ART_DIRS.values() for d in ds}))
    loop_snap = _dir_snapshot(all_dirs)
    for out, spec in sorted(PAIRS.items()):
        script = script_file(spec)
        if out in FROZEN_STALE:
            # 🔴 `--rerun` 은 스크립트를 돌려 **산출물을 덮어쓴다.** 동결 항목은 재측정 금지
            #    (`PREREG_POST6.md` §5-1-5·§5-4-2)이므로 **스크립트를 아예 실행하지 않는다.**
            #    🔑 C-23 — 이 스킵이 실효를 가지려면 «다른 키»의 실행이 같은 동결본을 곁다리로
            #      건드리지 않아야 한다 ⇒ `PAIRS` 값에 모드 인자를 박아 둔 이유가 이것이다.
            print(f"  ⏭ {out}  재실행 건너뜀(스크립트 미실행) — 정정 미반영(동결): "
                  f"{FROZEN_STALE[out]}")
            continue
        if out in PENDING and not (BASE / out).exists():
            # 🔴 아직 «만들어지지 않은» 산출물. 건너뛰지 않으면 아래 `read_bytes()` 가
            #    FileNotFoundError 로 **게이트 자체를 죽인다**(검사가 아니라 크래시가 된다).
            print(f"  ⏭ {out}  재실행 건너뜀 — 미생성(예정): {PENDING[out]}")
            continue
        before = (BASE / out).read_bytes() if (BASE / out).exists() else None
        dirs = ART_DIRS.get(out, ())
        dsnap = _dir_snapshot(dirs)
        r = subprocess.run([sys.executable, *script_argv(spec)], cwd=BASE,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            # 🔴 C-24(D1-B1) — **실패 경로도 되돌린다.** 스크립트가 산출물을 쓴 «뒤» 죽으면
            #    부분 출력이 그대로 남는다 ⇒ `--rerun` 의 「검사 전용」 계약이 여기서만 깨져 있었다.
            if before is not None:
                (BASE / out).write_bytes(before)
            if dirs:
                _dir_restore(dsnap, dirs)
            fails.append(f"{out}: 실행 실패 ({spec}) — **산출물은 원상복구했다**"
                         f"\n{r.stderr[-800:]}")
            continue
        after = (BASE / out).read_bytes()
        # ── C-23: 디렉토리 산출물도 byte 로 대조한다(단일 파일만 보면 못 보는 축) ──
        dmoved = []
        if dirs:
            dnew = _dir_snapshot(dirs)
            dmoved = sorted(set(dsnap) ^ set(dnew)) + sorted(
                k for k in set(dsnap) & set(dnew) if dsnap[k] != dnew[k])
            if dmoved:
                _dir_restore(dsnap, dirs)
        if before is None:
            fails.append(f"{out}: 산출물이 없었다 — 새로 생성됨")
        elif before != after:
            # 🔴 **되돌린다.** `--rerun` 은 «검사»이지 갱신이 아니다 — 스크립트가 산출물을 덮어쓰므로
            #    되돌리지 않으면 이 명령 한 번이 발표된 post4·post5 판정 숫자를 «조용히» 갈아치운다
            #    (`PREREG_POST6.md` §5-1-5·§5-4-2 금지). 갱신은 사람이 스크립트를 직접 돌려서 한다.
            (BASE / out).write_bytes(before)
            if dirs:
                _dir_restore(dsnap, dirs)
            fails.append(f"{out}: 🔴 재실행 결과가 다르다 — 커밋된 값이 낡았거나 비결정적 "
                         f"(**파일은 원상복구했다**)")
        elif dmoved:
            fails.append(f"{out}: 🔴 **디렉토리 산출물이 달라졌다**(C-23) — "
                         f"{dmoved[:6]}{' 외' if len(dmoved) > 6 else ''} "
                         f"(**전부 원상복구했다**)")
        else:
            print(f"  ✅ {out}  재현 일치"
                  + (f"  (+ 디렉토리 {list(dirs)} {len(dsnap)}파일 불변)" if dirs else ""))
            verified.append(out)
    # ── C-23 4번(D1-①): 루프 «전체» tripwire 대조 ─────────────────────────
    loop_new = _dir_snapshot(all_dirs)
    loop_moved = sorted(set(loop_snap) ^ set(loop_new)) + sorted(
        k for k in set(loop_snap) & set(loop_new) if loop_snap[k] != loop_new[k])
    if loop_moved:
        _dir_restore(loop_snap, all_dirs)
        fails.append(f"🔴 **루프 전체 tripwire — `ART_DIRS` 디렉토리가 달라졌다**(C-23 4번): "
                     f"{loop_moved[:8]}{' 외' if len(loop_moved) > 8 else ''} "
                     f"(**전부 원상복구했다**) ⇒ 어느 항목이 «곁다리로» 동결 디렉토리를 썼다")
    else:
        print(f"  🟢 루프 전체 tripwire — `ART_DIRS` {len(all_dirs)}개 디렉토리 "
              f"{len(loop_snap)}파일 불변 (동결 `sector_dryrun/`·`wrc_explore/` 포함)")
    cleared = clear_absorbed(verified)
    if cleared:
        print(f"  🟢 재현 확인으로 「흡수」 기록을 지운 항목 {len(cleared)}건: {cleared}")
    if fails:
        print("\n".join("  " + f for f in fails))
        print(f"\n🔴 재현(--rerun) FAIL — {len(fails)}건")
        return 1
    print("\n🟢 재현(--rerun) PASS — 재실행 결과가 커밋본과 byte 단위로 같다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="매니페스트 갱신")
    ap.add_argument("--rerun", action="store_true", help="실제 재실행 + byte-diff (DB 필요)")
    a = ap.parse_args()
    if a.update:
        fp, why = db_fingerprint()
        prev = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
        if fp is None:
            # 🔴 DB 에 못 붙었다고 기준선을 «지우면» 안 된다 — 옛 지문을 그대로 물려준다.
            print(f"  ⚠️ DB 지문을 못 읽었다 ({why}) — 기존 지문을 그대로 유지한다.")
            fp = prev.get("db_fingerprint")
        man = build(fp, old=prev.get("artifacts", {}))
        MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        ab = {k: v["absorbed_stale"] for k, v in man["artifacts"].items() if "absorbed_stale" in v}
        print(f"[written] {MANIFEST.name}")
        if MIGRATED:
            # 🔴 C-24 — 잣대 변경(`sha()` 줄끝 정규화)으로 «값만» 교체한 항목. 흡수가 아니다.
            print(f"🔵 **줄끝 정규화로 값만 교체한 지문 {len(MIGRATED)}건**(C-24 · 내용 변경 아님):")
            for m in MIGRATED:
                print(f"   · {m}")
            print("🔑 ***잣대를 바꾼 순간 전건이 「바뀐 것」으로 보인다 — 마이그레이션 규칙이 "
                  "없으면 그 한 번이 「낡았다」 신호를 전부 덮어쓴다.***")
        if ab:
            print(f"🟡 **재생성 없이 흡수한 항목 {len(ab)}건** — 매니페스트에 사유가 박혔다:")
            for k, v in sorted(ab.items()):
                print(f"   · {k}: {v['why']}"
                      + (f" · 바뀐 모듈 {v['deps_changed']}" if v.get("deps_changed") else ""))
            print("🔑 ***`--update` 한 번이 「낡았다」 신호를 «조용히» 지우면 안 된다.*** "
                  "위 항목은 `--rerun` 으로 확인되기 전까지 증거가 아니다.")
        return 0
    if a.rerun:
        return rerun()
    return check()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
