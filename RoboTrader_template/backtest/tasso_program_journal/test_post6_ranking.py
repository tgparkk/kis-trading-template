# -*- coding: utf-8 -*-
"""`run_ranking.py --stage post6` 의 «가드 시험» — 훈련 모드 보호가 실제로 뭔가를 막는지 본다.

🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「훈련 표본이 50행이다」만 보이면
그 필터가 «있으나 마나»일 수 있다. 그래서 **필터를 일부러 무력화한 사본에서 오염이 나는지**도 본다.
🔑 계열 규칙: *캡처 장치도 가드다* — 원장 prefix md5 와 종목코드 대조를 여기서 못 박는다.

실행: `python test_post6_ranking.py`  (시스템 python · DB 접속 0건 · 라이브 트리 import 0건)

  P1  훈련 모드가 post6 행을 «제외»한다            (원장 62 → 50 · post6 0건 · `exact` 18)
  N1  (음성 대조) 동결 시점 상수를 미래로 밀면 «오염»된다 (62행 · `exact` 28) ⇒ 가드가 살아 있다
  P2  post6 모드는 전 행을 읽는다                  (62행 · post6 12건 = `exact` 10 + `none` 2)
  P3  동결 선택 라벨이 `FREEZE_RANKING_2026-08-31.md` 와 일치한다
  P4  `POST6_CODES` 가 `INTAKE_2026-09-04_post6.md` §1 표와 축자 일치 · 계열 코드와 충돌 0
  P5  원장 prefix 51줄 md5 = 동결본이 적은 값      (기존 행 byte 불변)

🔴 원본 파일은 하나도 건드리지 않는다 — 상수는 실행 중에만 되돌려 놓고 바꾼다.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import run_ranking as R

BASE = Path(__file__).resolve().parent
FROZEN_PREFIX_MD5 = "5d603de7d0ac1ed853eaaf960c1f0883"   # `FREEZE_RANKING_2026-08-31.md` §2
FAIL: list = []


def check(tag, cond, msg):
    print("%s %-4s %s" % ("🟢" if cond else "🔴", tag, msg))
    if not cond:
        FAIL.append(tag)


def counts(rows):
    ex = sum(1 for r in rows if r["reg_date_precision"] == "exact")
    p6 = sum(1 for r in rows if r["post_log_no"] == R.POST6_LOG_NO)
    return len(rows), ex, p6


def main():
    # ── P1 훈련 모드 ────────────────────────────────────────────────────────
    n, ex, p6 = counts(R.load_ledger("train"))
    check("P1", (n, ex, p6) == (50, 18, 0),
          "훈련 모드 = %d행 · `exact` %d · post6 %d건 (기대 50 · 18 · 0)" % (n, ex, p6))

    # ── N1 음성 대조 — 필터를 무력화하면 «오염»되는가 ────────────────────────
    keep = R.TRAIN_FREEZE_DATE
    try:
        R.TRAIN_FREEZE_DATE = "2099-12-31"          # 「거르지 않는다」와 같은 효과
        n2, ex2, p62 = counts(R.load_ledger("train"))
    finally:
        R.TRAIN_FREEZE_DATE = keep
    check("N1", (n2, ex2, p62) == (62, 28, 12) and (n2, ex2, p62) != (n, ex, p6),
          "필터 무력화 시 %d행 · `exact` %d · post6 %d건 ⇒ 가드가 «실제로» 막고 있다"
          % (n2, ex2, p62))

    # ── P2 post6 모드 ───────────────────────────────────────────────────────
    rows = R.load_ledger("post6")
    n3, ex3, p63 = counts(rows)
    p6rows = [r for r in rows if r["post_log_no"] == R.POST6_LOG_NO]
    prec = {k: sum(1 for r in p6rows if r["reg_date_precision"] == k)
            for k in ("exact", "approx", "after", "none")}
    check("P2", (n3, p63) == (62, 12) and prec == dict(exact=10, approx=0, after=0, none=2),
          "post6 모드 = %d행 · post6 %d건 %s (기대 62 · 12 · exact10/none2)" % (n3, p63, prec))

    # ── P3 동결 선택 라벨 ───────────────────────────────────────────────────
    fz = (BASE / "FREEZE_RANKING_2026-08-31.md").read_text(encoding="utf-8")
    m = re.search(r"선택된 규칙 = `(RNK-A\d)`", fz)
    check("P3", m is not None and m.group(1) == R.SELECTED_RULE,
          "`SELECTED_RULE` = %s ↔ 동결본 = %s" % (R.SELECTED_RULE, m.group(1) if m else "미검출"))

    # ── P4 종목코드 — `INTAKE` §1 표와 축자 대조 ────────────────────────────
    intake = (BASE / "INTAKE_2026-09-04_post6.md").read_text(encoding="utf-8").splitlines()
    tbl = {}
    for ln in intake:
        c = [x.strip() for x in ln.split("|")]
        if len(c) >= 5 and c[1].isdigit() and re.fullmatch(r"[0-9][0-9A-Z]{5}", c[3] or ""):
            tbl[c[2]] = c[3]
    missed = {k: (R.POST6_CODES[k], tbl.get(k)) for k in R.POST6_CODES
              if tbl.get(k) != R.POST6_CODES[k]}
    check("P4a", not missed, "`POST6_CODES` 10건 ↔ `INTAKE` §1 표 축자 일치 (불일치 %s)" % (missed or "0"))
    prior, _ = R.build_codes()
    clash = {k: (prior[k], v) for k, v in R.POST6_CODES.items()
             if k in prior and prior[k] != v}
    check("P4b", not clash and len(R.POST6_CODES) == 10,
          "계열 기존 코드와 충돌 %s · 목록 %d건" % (clash or "0건", len(R.POST6_CODES)))

    # ── P5 원장 prefix md5 (기존 행 byte 불변) ──────────────────────────────
    # 🔴 여기서 «통째» md5 를 고정하는 파일은 **없다** — 원장·`INTAKE`·`PREDECISION` 은 다른 레인이
    #    지금 쓰고 있어 통째 md5 를 박으면 «판정과 무관한» 편집이 이 시험을 깬다.
    #    prefix 51줄만은 예외다: 그건 **동결된 훈련 표본이 안 바뀌었다**는 증명이라 반드시 필요하다.
    raw = (BASE / "ledger_trades.csv").read_bytes().split(b"\n")
    prefix = b"\n".join(raw[:51]) + b"\n"
    got = hashlib.md5(prefix).hexdigest()
    check("P5", got == FROZEN_PREFIX_MD5,
          "원장 prefix 51줄 md5 = %s (동결본 %s)" % (got, FROZEN_PREFIX_MD5))

    # ── P6 PD-3 재진입 결정 — «문장 존재»로 확인한다(md5 고정 금지) ──────────
    pd = (BASE / "PREDECISION_2026-09-04_post6.md").read_text(encoding="utf-8")
    seg = pd.split("## PD-3")[1].split("## PD-4")[0] if "## PD-3" in pd else ""
    row = {nm: next((l for l in seg.splitlines() if l.startswith("| " + nm + " ")), "")
           for nm in ("지투파워", "현대약품")}
    ok = ("P6-PRIOR_CYCLE_IN_WINDOW" in seg and "**1**" in row["지투파워"]
          and "**0**" in row["현대약품"])
    check("P6", ok and set(R.POST6_REENTRY) == {"지투파워", "현대약품"}
          and R.POST6_PRIOR_CYCLE == {"지투파워": 1, "현대약품": 0},
          "PD-3 재진입 2건·플래그(지투파워 1 · 현대약품 0) 서술 ↔ 코드 상수 일치 "
          "(통째 md5 는 고정하지 «않는다»)")

    print("")
    print("실패 %d건 %s" % (len(FAIL), FAIL if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                     # noqa: BLE001
        pass
    sys.exit(main())
