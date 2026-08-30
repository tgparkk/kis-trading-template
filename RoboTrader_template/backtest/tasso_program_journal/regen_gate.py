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
}

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
    entries = {}
    for out, script in sorted(PAIRS.items()):
        deps = sorted(local_deps(script))
        e = {
            "script": script,
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
                dc = [d for d, h in e["deps"].items() if o["deps"].get(d) != h]
                rc = o.get("results_sha256") != e["results_sha256"]
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
            fails.append(f"{out}: 산출물이 없다")
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


def rerun() -> int:
    """실제 재실행 + byte-diff. 결정적/시드고정이므로 동일해야 한다."""
    fails = []
    verified = []
    for out, script in sorted(PAIRS.items()):
        if out in FROZEN_STALE:
            # 🔴 `--rerun` 은 스크립트를 돌려 **산출물을 덮어쓴다.** 동결 항목은 재측정 금지
            #    (`PREREG_POST6.md` §5-1-5·§5-4-2)이므로 아예 건너뛴다.
            print(f"  ⏭ {out}  재실행 건너뜀 — 정정 미반영(동결): {FROZEN_STALE[out]}")
            continue
        before = (BASE / out).read_bytes() if (BASE / out).exists() else None
        r = subprocess.run([sys.executable, script], cwd=BASE,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            fails.append(f"{out}: 실행 실패 ({script})\n{r.stderr[-800:]}")
            continue
        after = (BASE / out).read_bytes()
        if before is None:
            fails.append(f"{out}: 산출물이 없었다 — 새로 생성됨")
        elif before != after:
            # 🔴 **되돌린다.** `--rerun` 은 «검사»이지 갱신이 아니다 — 스크립트가 산출물을 덮어쓰므로
            #    되돌리지 않으면 이 명령 한 번이 발표된 post4·post5 판정 숫자를 «조용히» 갈아치운다
            #    (`PREREG_POST6.md` §5-1-5·§5-4-2 금지). 갱신은 사람이 스크립트를 직접 돌려서 한다.
            (BASE / out).write_bytes(before)
            fails.append(f"{out}: 🔴 재실행 결과가 다르다 — 커밋된 값이 낡았거나 비결정적 "
                         f"(**파일은 원상복구했다**)")
        else:
            print(f"  ✅ {out}  재현 일치")
            verified.append(out)
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
