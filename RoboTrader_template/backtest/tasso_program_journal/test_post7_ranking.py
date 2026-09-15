# -*- coding: utf-8 -*-
"""`POST7_CODES` 회귀 시험 — 7번째 글의 «종목코드 매핑»이 조용히 바뀌지 않는지 본다.

🔑 계열 규칙: *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다*
(`test_post6_ranking.py` 의 P4 문형을 그대로 승계한다. 새 문턱·새 정의 0건.)

🔴 **이 시험이 있는 이유** — `POST7_CODES` 는 **모듈 상수**이고, 이 축의 거의 모든
산출물이 그 한 사전을 통해 DB 를 읽는다. 코드가 한 글자 바뀌면 «다른 종목»을 재고도
스크립트는 조용히 성공한다. 그래서 **네 곳을 서로 대조**한다:

  R1  `POST7_CODES` 10건 ↔ `INTAKE_2026-09-15_post7.md` §1 표 **축자 일치**
  R2  계열 기존 코드(post1~6)와 **충돌 0** · 목록 **10건**
  R3  독립 매핑 4벌(`run_sector.POST7_NEW` · `run_selection_post7.NEW7` ·
      `run_anchor_redesign.POST7_EXACT` · `run_regday_post7.POST7_EXACT`)이
      `POST7_CODES` 와 **전건 일치**
      🔑 각 스크립트는 실행 «중»에 이 대조를 하지만, 실행하지 않으면 안 돈다 —
        여기서 **실행과 무관하게** 돈다.
  R4  `build_codes7()` 이 `POST7_CODES` 를 전부 담고 **post6 매핑을 덮어쓰지 않는다**
  R5  `POST7_REENTRY`·`POST7_PRIOR_CYCLE`·`POST7_NONE_NEW`·`POST7_FOLLOWUP` 의
      **모든 이름이 `POST7_CODES` 안에 있다**(오타 한 글자로 조용히 빈 집합이 되는 것을 막는다)
      ⚠️ `POST7_FOLLOWUP` 은 «후속» 3건이라 `POST7_CODES` 가 아니라 **계열 기존 코드**에 있어야 한다.

실행: `python test_post7_ranking.py`   (시스템 python · 라이브 트리 import 0건 · DB 접속 0건)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import run_ranking as R

BASE = Path(__file__).resolve().parent
INTAKE = "INTAKE_2026-09-15_post7.md"
CODE_RE = re.compile(r"[0-9][0-9A-Z]{5}")

failures: list[str] = []


def check(tag, ok, msg):
    print(("  ✅ " if ok else "  🔴 ") + tag + "  " + msg)
    if not ok:
        failures.append(tag)


def intake_table() -> dict:
    """§1 표에서 `{종목명: 코드}` — 코드 칸에 부기가 붙어도 **첫 코드**를 뽑는다.

    (실측: `198440(DB명 강동씨앤엘)` · ``**`0155E0`**(신규 상장 · 첫 봉 08-25)``)
    """
    out = {}
    for ln in (BASE / INTAKE).read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in ln.split("|")]
        if len(c) >= 5 and c[1].isdigit():
            m = CODE_RE.search(c[3] or "")
            if m:
                out[c[2]] = m.group(0)
    return out


def main() -> int:
    print("# `POST7_CODES` 회귀 시험 (R1~R5)\n")

    # ── R1 ────────────────────────────────────────────────────────────────
    tbl = intake_table()
    missed = {k: (v, tbl.get(k)) for k, v in R.POST7_CODES.items() if tbl.get(k) != v}
    check("R1", not missed and len(R.POST7_CODES) == 10,
          "`POST7_CODES` %d건 ↔ `%s` §1 표 축자 일치 (불일치 %s · 표에서 읽은 건수 %d)"
          % (len(R.POST7_CODES), INTAKE, missed or "0", len(tbl)))

    # ── R2 ────────────────────────────────────────────────────────────────
    prior, _ = R.build_codes(include_post6=True)
    clash = {k: (prior[k], v) for k, v in R.POST7_CODES.items()
             if k in prior and prior[k] != v}
    check("R2", not clash, "계열 기존 코드(post1~6)와 충돌 %s" % (clash or "0건"))

    # ── R3 ────────────────────────────────────────────────────────────────
    import run_anchor_redesign as A
    import run_regday_post7 as RG
    import run_sector as S
    import run_selection_post7 as SEL

    indep = {
        "run_sector.POST7_NEW": {t[0]: t[1] for t in S.POST7_NEW},
        "run_selection_post7.NEW7": {t[0]: t[1] for t in SEL.NEW7},
        "run_anchor_redesign.POST7_EXACT": {t[0]: t[1] for t in A.POST7_EXACT},
        "run_regday_post7.POST7_EXACT": {t[0]: t[1] for t in RG.POST7_EXACT},
    }
    bad = {}
    for src, m in indep.items():
        diff = {k: (v, R.POST7_CODES.get(k)) for k, v in m.items()
                if R.POST7_CODES.get(k) != v}
        if diff:
            bad[src] = diff
    check("R3", not bad, "독립 매핑 %d벌(%s) 전건 일치 (불일치 %s)"
          % (len(indep), " · ".join("%s %d건" % (k.split(".")[-1], len(v))
                                    for k, v in indep.items()), bad or "0"))

    # ── R4 ────────────────────────────────────────────────────────────────
    c7, _ = R.build_codes7()
    lost = {k: (v, c7.get(k)) for k, v in R.POST7_CODES.items() if c7.get(k) != v}
    p6lost = {k: (v, c7.get(k)) for k, v in prior.items() if c7.get(k) != v}
    check("R4", not lost and not p6lost,
          "`build_codes7()` 이 post7 %d건 전부 담고 post6 이하 %d건을 덮어쓰지 않는다 "
          "(post7 손실 %s · 기존 덮어씀 %s)"
          % (len(R.POST7_CODES), len(prior), lost or "0", p6lost or "0"))

    # ── R5 ────────────────────────────────────────────────────────────────
    names = set(R.POST7_CODES)
    stray = {
        "POST7_REENTRY": sorted(set(R.POST7_REENTRY) - names),
        "POST7_PRIOR_CYCLE": sorted(set(R.POST7_PRIOR_CYCLE) - names),
        "POST7_NONE_NEW": sorted(set(R.POST7_NONE_NEW) - names),
    }
    stray = {k: v for k, v in stray.items() if v}
    # 🔴 후속 3건은 «이 글의 신규»가 아니므로 `POST7_CODES` 가 아니라 계열 기존 코드에 있어야 한다.
    foll_bad = sorted(n for n in R.POST7_FOLLOWUP if n not in prior)
    check("R5", not stray and not foll_bad,
          "부수 집합의 이름이 전부 매핑 안에 있다 (이탈 %s) · "
          "`POST7_FOLLOWUP` 3건은 계열 기존 코드에 있다 (누락 %s)"
          % (stray or "0", foll_bad or "0"))

    print()
    if failures:
        print("🔴 FAIL %d건: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("🟢 PASS — R1~R5 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
