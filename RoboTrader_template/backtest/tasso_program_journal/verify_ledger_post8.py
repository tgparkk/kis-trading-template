# -*- coding: utf-8 -*-
r"""원장 회수율 게이트 — 8번째 글(224416253270) 포함판.

🔴 `verify_ledger.py`·`verify_ledger_post5.py`·`verify_ledger_post6.py`·`verify_ledger_post7.py` 는
   **하나도 고치지 않는다**(옛 판의 게이트 거동을 그대로 둔다). 이 파일은 post7 판을 **그대로 승계**한다 —
   `verify_ledger` 에서 파서 조각(ITEM_MARK·NUM_RE·PCT_RE·load_csv)만 가져다 쓰고, post7 판의
   **글별 원문 경로 지도 · 산문 항목 선언 · 비표지행 선언 · 오기 정규화 선언 · P6-G-E** 를 그대로 둔 뒤
   **8번째 글 한 줄만 «더한다»**. 새 글의 평문 경로는 인자로도 줄 수 있다:
       python verify_ledger_post8.py --raw 224416253270=D:/archive/tasso-program-journal-20260918

게이트(원본과 같은 정의 · **이름도 판정 규칙도 바꾸지 않았다 · 새 게이트 0개**):
  G-A  저자 항목번호가 각 글에서 1..N 연속인가 (결번 = 누락)
  G-B  원문의 매매행 수 == ledger_trades 행 수 (양방향)
  G-C  원문의 모든 퍼센트 수치 == ledger_legs 수치 (다중집합 양방향)
  G-D  ledger_trades.n_legs == ledger_legs 실제 레그 수 (건별)
  P6-G-E  `fill_n == 1` ⟺ `fill_level == first_only` · `fill_level ∈ {first_only, partial, full, unknown}`
          (C-21 · `PREREG_POST6.md` §5-5-3 · backfill «후»의 전 행에 적용 · 위반 1건이면 실패)

8번째 글에서 «더한» 것은 `POSTS` 한 줄 + **글별 축자 선언 한 건**(`RAW_TYPO_FIX` 의 「17%,」)이다.
판정 규칙은 하나도 넓히지 않았다. `PREDECISION_2026-09-18_post8.md` PD-10 · `INTAKE_2026-09-18_post8.md`
§5 「원장」 행이 적은 **G-A 함정 4종**을 하나씩 어떻게 다뤘는지:

  · 산문 «항목» — post8 은 **0건**(`EXTRA_PROSE_ITEMS` 에 항목 없음).
    저자 항목번호 1..10 결번 0 · 번호 없는 산문 항목 0 (`INTAKE_2026-09-18_post8.md` 머리 · PD-10 11).

  · 비표지행 — post8 은 **0건**(`NON_ITEM_LINES` 에 항목 없음). 원문에서 `ITEM_MARK`(「통계기반 자동매매」)를
    품은 줄은 **항목 표지행 10줄뿐**이다(실측). 「▲ 태쏘 통계기반 트레이더 1.0.42 (업데이트 중)」(2번째 줄) ·
    「통계기반 트레이더 : 네이버 카페」 · 「통계기반 주식매매 프로그램 공식 카페입니다 …」는 「통계기반」 뒤가
    「자동매매」가 아니라서 `ITEM_MARK` 에 안 걸린다. 🔑 **선언을 비워 둔 것도 시험 대상이다** — 선언 없는
    `ITEM_MARK` 산문 줄을 넣으면 여전히 「구분자 분해 실패」가 나야 한다(N8 이 시험).

  ① 🔴 **`~` 5개 중 레그 표지는 1개**(PD-5 2 · PD-10 4)
     우리로 「0.54% ~」 만 레그 표지이고, 코데즈·우리기술 「1~4차」(차수 표기) · 산문 「상반기~하반기」·
     「2,000~3,000건」 은 아니다. 이 게이트는 `~` 를 **아예 세지 않고** `leg_open_ended` 열을 «읽기만» 하므로
     `~` 오분류 경로가 없다(post7 서산 「Q2~MAX」 와 같은 기제). 원장 쪽 값은 **서술 기준**(아래 규약).
     값 줄에 `~` 를 더 붙여도 게이트 결과가 한 글자도 안 바뀐다는 것을 P2 가 시험한다
     (= 「이 게이트는 `~` 를 판정하지 않는다」의 증거 · 규칙을 넓힌 것이 아니라 원래 그렇다).

  ② 🔴🔴 **우리로 「17%」 — 소수 0자리**(PD-10 1) ⇒ `RAW_TYPO_FIX` 문형의 **축자 정규화**
     `PCT_RE`(`-?\d+\.\d+`)는 「17%」 를 **못 읽고 지나친다**(실측: 그 항목에서 7이 아니라 6개만 잡힌다)
     ⇒ 원장의 17.00 이 「원장에만 있는 수치」로 G-C 에 걸린다.
     ⇒ 처리: post7 「4,91%.」 와 **같은 기제** — 글별로 문자열 「17%,」 를 축자 선언하고 «원문 1회»만
       「17.00%,」 로 치환한다. 「소수점 없는 정수 % 도 읽는다」 같은 **정규식 확장은 하지 않았다** —
       선언한 문자열이 원문에 정확히 1번 있지 않으면 실패한다(N7 이 시험).
     🔑 이것은 저자의 «오기»가 아니라 **비표준 표기**다. 사전 이름 `RAW_TYPO_FIX` 는 post7 기제를 그대로
       쓰려고 유지했다(이름을 새로 두면 같은 일을 하는 기제가 둘이 된다).
     🔑 **면제가 아니라 정규화**다: 정규화 후 17.0 은 G-C 다중집합에 «들어가» 원장과 대조된다
       (N3 이 17.00 → 17.01 로 깨뜨려 그 사실을 증명한다). 원 표기는 우리로 행 `narrative` 에 남겼다.

  ③ **「손실률」 인라인**(PD-10 5) — 헥토파이낸셜 값 줄이 *「수익률 5.84%, 2.98%, 1.39%, 손실률 -2.28%」* 다.
     「손실률 -2.28%」 는 같은 `/` 조각 안에 있어 `PCT_RE` 가 **부호째**(-2.28) 읽는다(실측) ⇒ **선언이 필요 없다**.
     레그인지 아닌지는 `INTAKE` §1 값 목록(「†−2.28」 = 레그)이 정했고, 원장은 레그 4 · `is_loss = 1` 로 적었다.
     부호까지 다중집합에 들어간다는 것을 N9 가 −2.28 → 2.28 로 깨뜨려 증명한다.
     🔴 html 에서는 「1.39%,」 와 「손실률 -2.28%」 가 **별도 텍스트 노드**다(PD-10 5 · 검수 G-3) — 이 게이트는
     평문(txt)만 읽으므로 그 함정 경로가 없다.

  ④ **값 개수 ≠ 서술된 매도 횟수 4건**(PD-10 3 · 우리로 7↔5 · JW신약 4↔3 · 헥토 4↔2 · 코데즈 5↔4 · + 불확정 2)
     이 게이트는 «값 줄»의 수치만 세고 서술의 매도 횟수는 읽지 않는다 ⇒ 원장은 **원문에 적힌 값 그대로** 레그로
     적었다(post7 범한퓨얼셀 「7분할 vs 6레그」 전례 · 규칙 신설 0). 불일치는 각 행 `narrative` 에 기록만 했다.

  · 🔑 **동률 레그 2쌍**(PD-10 2 · 범한퓨얼셀 20.99·20.99 · 우리기술 8.47·8.47) — G-C 는 원래 **다중집합**
    (`Counter`)이라 같은 값 두 레그를 하나로 접지 않는다. 원장도 두 행으로 적었다. N4 가 한 행을 지우고
    `n_legs` 까지 맞춰 G-D 를 비껴간 사본에서 G-C 가 걸리는지 본다(집합 비교였다면 통과했을 사본이다).

  · 🔑 **G-C 와 「비레그 퍼센트」** — post6·post7 판의 설명이 그대로 유효하다. post8 원문의 비레그 수치
    (「HDR 60%」 9곳)는 전부 항목 서술줄에 있어 `ITEM_MARK` 표지행 필터에서 걸러진다. 계좌 단위 자가보고 **0건**
    (INTAKE §4). **면제 목록을 새로 두지 않았다.**

  · 🔑 **`leg_open_ended` 규약 — «두 번째 예외»**(PD-5 1) — 이 게이트는 이 컬럼을 «판정»하지 않고 세기만 한다.
    규약은 **「`open_ended == 1` 인 건의 «마지막» 레그 하나만 1」** + post7 한전기술 −1.70 예외 1건이었다.
    post8 은 서술 기준 미완결 2건(코데즈컴바인 6.59 · 우리기술 4.75)의 마지막 레그 2개 + 🔴 **우리로 0.54 레그
    1개** = 3개가 1이다. 우리로는 값 줄에 `~` 가 있는데 서술이 「본전 위협에 **전량**매도 / … 분할매도 **완료**」라
    **주 판정은 완결**(`open_ended = 0`)이고 `~` 는 **레그 단위로만** 표기한다 — `PREDECISION_2026-09-18_post8.md`
    **PD-5 1**(*「`0.54` 레그만 `leg_open_ended = 1`(post7 한전기술 원장 표기 `ledger_legs.csv:223` 승계)」*) ·
    `~` 와 서술이 불일치한 **두 번째 사례**다.

  · 원장 인코딩은 PD-17 단일 축(`stoploss_plan` 10행 전부 0 · 라벨 SSOT = `narrative` 첫 토큰 「라벨 X」) ·
    `prog_ver = 1.0.42`(PD-8 — 「(업데이트 중)」 꼬리는 수준에 넣지 않고 `narrative` 에 보존) ·
    post4~post7 행 **불변**(순수 append). 이 게이트는 그 인코딩을 판정하지 않는다(새 게이트 0).

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
    "224416253270": ("2026-09-18", [Path(r"D:/archive/tasso-program-journal-20260918"), BASE, BASE / "raw"]),
}

# 표지행 없는 산문 «항목»: log_no -> [(종목, 위치 함의 item_no)]
# 🔴 post7(224409404744)·post8(224416253270)은 **0건** — 새 항목을 넣지 않는다(각 INTAKE 「번호 없는 산문 항목 0」).
EXTRA_PROSE_ITEMS = {
    "224385784257": [("솔트룩스", 7), ("빛과전자", 8)],
    "224393392105": [("SK아이이테크놀로지", 9)],
}

# `ITEM_MARK` 를 품었지만 «항목 표지행이 아닌» 줄 — 글별 축자 선언(위 docstring 참조).
# 옛 6글과 post8 은 0건이라 거동 불변.
NON_ITEM_LINES = {
    "224409404744": ["제가 쓰는 이 통계기반 자동매매 프로그램 은"],
}

# 저자 표기(오기·비표준 표기)의 축자 정규화 — 글별 (old, new) · 원문에 정확히 1번 있어야 한다.
#   post7 = 오기 「4,91%.」(PD-10 1) · post8 = 소수 0자리 「17%,」(PD-10 1)
RAW_TYPO_FIX = {
    "224409404744": [("4,91%.", "4.91%")],
    "224416253270": [("17%,", "17.00%,")],
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

        # (1) 선언된 저자 표기의 축자 정규화 — 원문에 정확히 1번이어야 한다.
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
    print("미완결 레그 %d (서술 기준 · `~` 와 서술이 어긋난 레그만 레그 단위로 더한 «예외» 2개 = "
          "post7 한전기술 -1.70 · post8 우리로 0.54 — PD-5 1)"
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
    print("=== post7·post8 축자 선언 (규칙 확장 0 · 선언 ↔ 원문 양방향) ===")
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
