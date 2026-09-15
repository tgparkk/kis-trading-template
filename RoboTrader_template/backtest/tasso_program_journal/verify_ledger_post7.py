# -*- coding: utf-8 -*-
r"""원장 회수율 게이트 — 7번째 글(224409404744) 포함판.

🔴 `verify_ledger.py`·`verify_ledger_post5.py`·`verify_ledger_post6.py` 는 **하나도 고치지 않는다**
   (옛 판의 게이트 거동을 그대로 둔다). 이 파일은 `verify_ledger` 에서 파서 조각
   (ITEM_MARK·NUM_RE·PCT_RE·load_csv)만 가져다 쓰고, post6 판의 **글별 원문 경로 지도 ·
   산문 항목 선언 · P6-G-E** 를 그대로 승계한 뒤 **7번째 글 한 줄만 «더한다»**.
   새 글의 평문 경로는 인자로도 줄 수 있다:
       python verify_ledger_post7.py --raw 224409404744=D:/archive/tasso-program-journal-20260915

게이트(원본과 같은 정의 · **이름도 판정 규칙도 바꾸지 않았다 · 새 게이트 0개**):
  G-A  저자 항목번호가 각 글에서 1..N 연속인가 (결번 = 누락)
  G-B  원문의 매매행 수 == ledger_trades 행 수 (양방향)
  G-C  원문의 모든 퍼센트 수치 == ledger_legs 수치 (다중집합 양방향)
  G-D  ledger_trades.n_legs == ledger_legs 실제 레그 수 (건별)
  P6-G-E  `fill_n == 1` ⟺ `fill_level == first_only` · `fill_level ∈ {first_only, partial, full, unknown}`
          (C-21 · `PREREG_POST6.md` §5-5-3 · backfill «후»의 전 행에 적용 · 위반 1건이면 실패)

7번째 글에서 «더한» 것은 `POSTS` 한 줄 + **글별 축자 선언 두 종**이다. 판정 규칙은 하나도 넓히지 않았다:

  · 산문 «항목» — post7 은 **0건**(`EXTRA_PROSE_ITEMS` 에 항목 없음).
    저자 항목번호 1..13 결번 0 · 번호 없는 산문 항목 0 (`INTAKE_2026-09-15_post7.md` §1 · PD-10 6).

  · 🔴🔴 **`NON_ITEM_LINES` — 이 계열 최초의 「표지행 아닌 ITEM_MARK 줄」**
    post1~post6 에서는 `ITEM_MARK`(「통계기반 자동매매」)가 **항목 표지행에만** 있었고, 그래서 post6 판
    docstring 이 *「면제 기제는 원본 파서의 «항목 표지행 필터» 그 자체다 — 면제 목록을 따로 두지 않는다」*
    라고 적을 수 있었다. **post7 에서 그 전제가 깨진다** — 본문 산문 48번째 줄
        「제가 쓰는 이 통계기반 자동매매 프로그램 은」
    이 `ITEM_MARK` 를 품고 있고 `/` 구분자가 없어 원판 파서는 **`[parse]` 실패**를 낸다(실측).
    ⇒ 처리: **글별로 그 줄을 축자 선언**해서만 건너뛴다. 「`/` 가 없으면 조용히 넘긴다」 같은
      **규칙 완화는 하지 않았다** — 선언에 없는 줄은 여전히 「구분자 분해 실패」로 걸린다(N6 가 시험).
      선언했는데 원문에 그 줄이 «없으면» 그것도 실패다(선언 ↔ 원문 양방향).
      옛 6글은 선언이 비어 있어 **거동이 한 글자도 안 바뀐다**.

  · 🔴🔴 **`RAW_TYPO_FIX` — 저자 오기 「4,91%.」의 축자 정규화**(PD-10 1)
    한전기술(#1) 값 줄이 *「7.37%, **4,91%.** 3.34%」* 다 — 쉼표를 소수점으로 쓰고 구분자에 마침표를 썼다.
    `PCT_RE`(`-?\d+\.\d+`)는 「4,91」을 **못 읽고 지나친다**(실측: 그 항목에서 6이 아니라 5개만 잡힌다)
    ⇒ 원장의 4.91 이 「원장에만 있는 수치」로 G-C 에 걸린다.
    ⇒ 처리: **글별로 오기 문자열을 축자 선언**하고 «원문 1회»만 치환한다. 「쉼표도 소수점으로 읽는다」
      같은 **정규식 확장은 하지 않았다** — 선언한 문자열이 원문에 정확히 1번 있지 않으면 실패한다(N7 이 시험).
      🔑 이것은 **면제가 아니라 정규화**다: 정규화 후 4.91 은 G-C 다중집합에 «들어가» 원장과 대조된다
        (N3 이 4.91 → 4.92 로 깨뜨려 그 사실을 증명한다).
    범한퓨얼셀의 「10.8%」(소수 1자리)는 `PCT_RE` 가 그대로 읽고 `round(...,2)` 양쪽이 10.8 이라
    **정규화가 필요 없다**(원장 표기 10.80 = 같은 값 · 원표기는 `narrative` 에 남겼다).

  · 🔑 **G-C 와 「비레그 퍼센트」** — post6 판의 설명이 그대로 유효하다. post7 원문의 비레그 수치
    (「HDR 60%」 등)는 전부 항목 서술줄·산문줄에 있어 `ITEM_MARK` 표지행 필터에서 걸러진다.
    이번 글은 계좌 단위 자가보고(post5 「27%」 · post6 「8.3%」)마저 **0건**이라 그 자리도 비었다.
    **면제 목록을 새로 두지 않았다.**

  · 🔴 **`~` 함정 — 이 게이트가 «세지 않는» 것**(PD-5 2 · PD-18)
    post7 본문의 `~` 는 2곳이고 그중 하나는 레그 표지가 **아니다**: 서산(#7)의 프리셋 이름
    「사분위수 **Q2~MAX**」. `~` 를 기계로 세면 서산이 미완결로 **오분류**된다.
    이 게이트는 `~` 를 아예 세지 않고 `leg_open_ended` 열을 «읽기만» 하므로 그 오분류 경로가 없다.
    원장 쪽 값은 **서술 기준**으로 넣었다(아래).

  · 🔑 **`leg_open_ended` 규약(실측 승계 + post7 의 «예외 1건»)** — 이 게이트는 이 컬럼을 «판정»하지 않고
    세기만 하지만, 기존 216레그의 규약은 **「`open_ended == 1` 인 건의 «마지막» 레그 하나만 1」**
    이고 62건 전수에서 **예외 0**이다(실측). post7 은 서술 기준 미완결 3건(로보티즈·빛과전자·범한퓨얼셀)의
    마지막 레그 3개 + 🔴 **한전기술 −1.70 레그 1개** = 4개가 1이다.
    한전기술은 값 줄에 `~` 가 있는데 서술이 「**전량** 분할 매도처리」라 **주 판정은 완결**(`open_ended=0`)
    이고, `~` 는 **레그 단위로만** 표기한다 — `PREDECISION_2026-09-15_post7.md` **PD-5 1번**
    (*「`~` 가 붙은 −1.70 레그는 `leg_open_ended = 1` 로 «레그 단위만» 표기한다」*)이 명시한
    **계열 최초의 예외**다(`~` 와 서술이 불일치한 첫 사례).

라이브 트리 import 0건(표준 라이브러리 + 같은 디렉토리 모듈만).
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import verify_ledger as V

BASE = Path(__file__).resolve().parent

# 글 -> (발행일, 원문 평문이 있는 디렉토리 후보들)
POSTS = {
    "224364189017": ("2026-07-31", [Path(r"D:/archive/tasso-program-journal-20260814"), BASE / "raw", BASE]),
    "224371400049": ("2026-08-07", [Path(r"D:/archive/tasso-program-journal-20260814"), BASE / "raw", BASE]),
    "224378680510": ("2026-08-14", [Path(r"D:/archive/tasso-program-journal-20260814"), BASE / "raw", BASE]),
    "224385784257": ("2026-08-22", [Path(r"D:/archive/tasso-program-journal-20260822"), BASE, BASE / "raw"]),
    "224393392105": ("2026-08-29", [Path(r"D:/archive/tasso-program-journal-20260829"), BASE, BASE / "raw"]),
    "224401108114": ("2026-09-04", [Path(r"D:/archive/tasso-program-journal-20260904"), BASE, BASE / "raw"]),
    "224409404744": ("2026-09-12", [Path(r"D:/archive/tasso-program-journal-20260915"), BASE, BASE / "raw"]),
}

# 표지행 없는 산문 «항목»: log_no -> [(종목, 위치 함의 item_no)]
# 🔴 post7(224409404744)은 **0건** — 새 항목을 넣지 않는다(INTAKE §1 「번호 없는 산문 항목 0」).
EXTRA_PROSE_ITEMS = {
    "224385784257": [("솔트룩스", 7), ("빛과전자", 8)],
    "224393392105": [("SK아이이테크놀로지", 9)],
}

# `ITEM_MARK` 를 품었지만 «항목 표지행이 아닌» 줄 — 글별 축자 선언(위 docstring 참조).
# 옛 6글은 0건이라 거동 불변.
NON_ITEM_LINES = {
    "224409404744": ["제가 쓰는 이 통계기반 자동매매 프로그램 은"],
}

# 저자 표기 오기의 축자 정규화 — 글별 (old, new) · 원문에 정확히 1번 있어야 한다(PD-10 1).
RAW_TYPO_FIX = {
    "224409404744": [("4,91%.", "4.91%")],
}

# P6-G-E — `fill_level` 이 가질 수 있는 «범주» 전부 (차수는 `fill_n` 으로 나갔다)
FILL_CATS = ("first_only", "partial", "full", "unknown")

failures: list = []


def parse_args(argv):
    """--raw LOGNO=PATH 를 여러 번 줄 수 있다. 옛 글 거동은 안 바꾼다."""
    over = {}
    it = iter(argv)
    for a in it:
        if a == "--raw":
            spec = next(it, "")
        elif a.startswith("--raw="):
            spec = a[len("--raw="):]
        else:
            raise SystemExit("알 수 없는 인자: %r (사용법: --raw LOGNO=PATH)" % a)
        if "=" not in spec:
            raise SystemExit("--raw 형식 오류: %r (LOGNO=PATH)" % spec)
        k, p = spec.split("=", 1)
        over[k.strip()] = Path(p.strip())
    return over


def raw_path(log_no, override):
    if log_no in override:
        cand = override[log_no]
        p = cand / ("post_%s.txt" % log_no) if cand.is_dir() else cand
        if not p.is_file():
            raise SystemExit("--raw 로 준 경로에 원문이 없다: %s" % p)
        return p
    for d in POSTS[log_no][1]:
        p = d / ("post_%s.txt" % log_no)
        if p.is_file():
            return p
    raise SystemExit("원문 평문을 못 찾았다: post_%s.txt (--raw 로 경로를 줄 것)" % log_no)


def parse_raw(override):
    """원문 -> {log_no: [(item_no|None, 종목, [pct...])]}. 파싱 규칙은 원본과 동일.

    🔑 `ITEM_MARK` 가 없는 줄은 아예 안 읽는다 — 이것이 「HDR 60%」·「8.3% 주간 수익률」 같은
    **비레그 퍼센트의 면제 기제**다(면제 목록을 따로 두지 않는다 · post5·post6 전례).
    🔴 post7 부터는 `ITEM_MARK` 가 «있는데» 표지행이 아닌 줄이 하나 있어(`NON_ITEM_LINES`)
    **축자 선언**으로만 건너뛴다 — 선언에 없는 줄은 그대로 `[parse]` 실패다."""
    out = {}
    for log_no in POSTS:
        text = raw_path(log_no, override).read_text(encoding="utf-8")

        # (1) 선언된 저자 오기의 축자 정규화 — 원문에 정확히 1번이어야 한다.
        for old, new in RAW_TYPO_FIX.get(log_no, []):
            n = text.count(old)
            if n != 1:
                failures.append("[parse] %s: 선언한 오기 %r 가 원문에 %d번 (기대 1번) "
                                "— 선언 ↔ 원문 불일치" % (log_no, old, n))
                continue
            text = text.replace(old, new, 1)

        # (2) 선언된 «비표지행» 이 실제로 원문에 있는지 (선언 ↔ 원문 양방향)
        lines = text.splitlines()
        stripped = [l.strip() for l in lines]
        skip = set()
        for decl in NON_ITEM_LINES.get(log_no, []):
            if decl not in stripped:
                failures.append("[parse] %s: 선언한 비표지행 %r 가 원문에 없다 "
                                "— 선언 ↔ 원문 불일치" % (log_no, decl))
            skip.add(decl)

        rows = []
        for line in lines:
            if V.ITEM_MARK not in line:
                continue
            if line.strip() in skip:
                continue
            parts = [p.strip() for p in line.split("/")]
            if len(parts) < 3:
                failures.append("[parse] %s: 구분자 분해 실패 -> %r" % (log_no, line))
                continue
            head = parts[0]
            m = V.NUM_RE.match(head)
            item_no = int(m.group(1)) if m else None
            stock = V.NUM_RE.sub("", head).strip()
            pcts = [float(x) for x in V.PCT_RE.findall(" / ".join(parts[2:]))]
            rows.append((item_no, stock, pcts))
        out[log_no] = rows
    return out


def gate_e(trades):
    """P6-G-E — `fill_n == 1` ⟺ `fill_level == first_only` + `fill_level` 값 집합.

    반환은 (fill_level, fill_n) 분포. 위반은 전역 `failures` 에 쌓는다."""
    if not trades:
        failures.append("[P6-G-E] trades 가 비었다")
        return Counter()
    if "fill_n" not in trades[0]:
        failures.append("[P6-G-E] `fill_n` 컬럼이 없다 — backfill 미적용 "
                        "(`python backfill_fill_n.py` · PREREG_POST6.md §5-5-2)")
        return Counter()
    for t in trades:
        lv = (t.get("fill_level") or "").strip()
        n = (t.get("fill_n") or "").strip()
        key = "%s item %s %s" % (t["post_log_no"], t["item_no"], t["stock_name"])
        if lv not in FILL_CATS:
            failures.append("[P6-G-E] %s: fill_level=%r 이 범주 %s 밖 (정수 차수는 fill_n 으로)"
                            % (key, lv, list(FILL_CATS)))
        if n and not n.isdigit():
            failures.append("[P6-G-E] %s: fill_n=%r 이 정수가 아니다" % (key, n))
        if (n == "1") != (lv == "first_only"):
            failures.append("[P6-G-E] %s: `fill_n==1 ⟺ fill_level==first_only` 위반 "
                            "(fill_level=%r · fill_n=%r)" % (key, lv, n))
    return Counter((t["fill_level"], t.get("fill_n") or "") for t in trades)


def main(argv):
    override = parse_args(argv)
    raw = parse_raw(override)
    legs = V.load_csv("ledger_legs.csv")
    trades = V.load_csv("ledger_trades.csv")

    # ---- G-A: 저자 항목번호 1..N 연속 (표지행 있는 항목만이 분모) ------------
    ga = {}
    for log_no, rows in raw.items():
        nums = [n for n, _, _ in rows if n is not None]
        n_total = len(rows)                       # 표지행 기준 = 저자 번호의 분모
        expected = set(range(1, n_total + 1))
        got = set(nums)
        missing = sorted(expected - got - {1})    # 1번은 번호 없이 쓰인 사례가 있다(가온칩스)
        dup = [k for k, v in Counter(nums).items() if v > 1]
        ga[log_no] = (n_total, sorted(got), missing, dup)
        if missing:
            failures.append("[G-A] %s: 항목번호 결번 %s (총 %d행)" % (log_no, missing, n_total))
        if dup:
            failures.append("[G-A] %s: 항목번호 중복 %s" % (log_no, dup))

    # ---- G-B: 매매행 수 양방향 (표지행 + 선언된 산문 항목) -------------------
    for log_no, rows in raw.items():
        extra = EXTRA_PROSE_ITEMS.get(log_no, [])
        n_raw = len(rows) + len(extra)
        n_led = sum(1 for t in trades if t["post_log_no"] == log_no)
        if n_raw != n_led:
            failures.append("[G-B] %s: 원문 %d행(표지 %d + 산문 %d) != trades %d행"
                            % (log_no, n_raw, len(rows), len(extra), n_led))
        for nm, no in extra:
            hit = [t for t in trades if t["post_log_no"] == log_no and t["item_no"] == str(no)]
            if not hit or hit[0]["stock_name"] != nm:
                failures.append("[G-B] %s: 선언된 산문 항목 %s(item_no=%d) 이 원장에 없다" % (log_no, nm, no))
            elif int(hit[0]["n_legs"]) != 0:
                failures.append("[G-B] %s: 산문 항목 %s 의 n_legs 가 0 이 아니다" % (log_no, nm))

    # ---- G-C: 퍼센트 다중집합 양방향 ---------------------------------------
    for log_no, rows in raw.items():
        raw_c = Counter(round(p, 2) for _, _, pcts in rows for p in pcts)
        led_c = Counter(round(float(l["ret_pct"]), 2) for l in legs if l["post_log_no"] == log_no)
        only_raw, only_led = raw_c - led_c, led_c - raw_c
        if only_raw:
            failures.append("[G-C] %s: 원문에만 있는 수치 %s" % (log_no, sorted(only_raw.elements())))
        if only_led:
            failures.append("[G-C] %s: 원장에만 있는 수치 %s" % (log_no, sorted(only_led.elements())))

    # ---- G-D: 건별 레그 수 --------------------------------------------------
    leg_cnt = defaultdict(int)
    for l in legs:
        leg_cnt[(l["post_log_no"], l["item_no"])] += 1
    for t in trades:
        key = (t["post_log_no"], t["item_no"])
        if leg_cnt.get(key, 0) != int(t["n_legs"]):
            failures.append("[G-D] %s %s: n_legs=%s != 실제 %d"
                            % (key, t["stock_name"], t["n_legs"], leg_cnt.get(key, 0)))

    # ---- 요약 ---------------------------------------------------------------
    print("글 %d개 / 매매건 %d / 매도레그 %d" % (len(raw), len(trades), len(legs)))
    for log_no, (date, _dirs) in POSTS.items():
        rows = raw[log_no]
        extra = EXTRA_PROSE_ITEMS.get(log_no, [])
        n_legs = sum(1 for l in legs if l["post_log_no"] == log_no)
        print("  %s %s: %d건(표지 %d + 산문 %d) %d레그  [원문 %s]"
              % (date, log_no, len(rows) + len(extra), len(rows), len(extra), n_legs,
                 raw_path(log_no, override)))
    loss = sum(1 for l in legs if l["is_loss"] == "1")
    print("손실 레그 %d / 익절 레그 %d" % (loss, len(legs) - loss))
    print("미완결 레그 %d (서술 기준 · post7 은 `~` 로 표기한 한전기술 -1.70 레그 1개가 «예외»로 더해진다 — PD-5 1)"
          % sum(1 for l in legs if l["leg_open_ended"] == "1"))

    # ---- P6-G-E: fill_level 축 분리 규약 (C-21) ----------------------------
    dist = gate_e(trades)

    print("")
    print("=== P6-G-E `fill_level`/`fill_n` 축 분리 (C-21) ===")
    for (lv, n), c in sorted(dist.items()):
        print("  %-12s fill_n=%-6s %d건" % (lv, n or "(빈칸)", c))
    print("  합 %d건 · 규약: fill_n==1 ⟺ fill_level==first_only" % sum(dist.values()))

    print("")
    print("=== G-A 저자 항목번호 결번 게이트 (글별) ===")
    for log_no, (n_total, got, missing, dup) in ga.items():
        print("  %s %s: 저자번호 %s / 표지행 %d / **결번 %d개**%s%s"
              % (POSTS[log_no][0], log_no,
                 ("%d..%d" % (got[0], got[-1])) if got else "없음",
                 n_total, len(missing),
                 (" %s" % missing) if missing else "",
                 (" / 중복 %s" % dup) if dup else ""))

    print("")
    print("=== post7 축자 선언 (규칙 확장 0 · 선언 ↔ 원문 양방향) ===")
    for log_no, decls in NON_ITEM_LINES.items():
        for d in decls:
            print("  [비표지행]     %s: %r" % (log_no, d))
    for log_no, fixes in RAW_TYPO_FIX.items():
        for old, new in fixes:
            print("  [오기 정규화]  %s: %r -> %r (원문 1회)" % (log_no, old, new))

    if failures:
        print("")
        print("=== 게이트 실패 ===")
        for f in failures:
            print(" ", f)
        return 1
    print("")
    print("모든 게이트 통과 (G-A/B/C/D + P6-G-E)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main(sys.argv[1:]))
