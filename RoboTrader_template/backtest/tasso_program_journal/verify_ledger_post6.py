# -*- coding: utf-8 -*-
"""원장 회수율 게이트 — 6번째 글(224401108114) 포함판.

🔴 `verify_ledger.py` 도 `verify_ledger_post5.py` 도 **고치지 않는다**(옛 판의 게이트 거동을 그대로 둔다).
   이 파일은 `verify_ledger` 에서 파서 조각(ITEM_MARK·NUM_RE·PCT_RE·load_csv)만 가져다 쓰고,
   post5 판의 **글별 원문 경로 지도 · 산문 항목 선언 · P6-G-E** 를 그대로 승계한 뒤
   **6번째 글 한 줄만 «더한다»**. 새 글의 평문 경로는 인자로도 줄 수 있다:
       python verify_ledger_post6.py --raw 224401108114=D:/archive/tasso-program-journal-20260904

게이트(원본과 같은 정의):
  G-A  저자 항목번호가 각 글에서 1..N 연속인가 (결번 = 누락)
  G-B  원문의 매매행 수 == ledger_trades 행 수 (양방향)
  G-C  원문의 모든 퍼센트 수치 == ledger_legs 수치 (다중집합 양방향)
  G-D  ledger_trades.n_legs == ledger_legs 실제 레그 수 (건별)
  P6-G-E  `fill_n == 1` ⟺ `fill_level == first_only` · `fill_level ∈ {first_only, partial, full, unknown}`
          (C-21 · `PREREG_POST6.md` §5-5-3 · backfill «후»의 전 행에 적용 · 위반 1건이면 실패)

6번째 글에서 «더한» 것은 `POSTS` 한 줄뿐이다. 규칙은 하나도 넓히지 않았다:

  · 산문 항목 — post6 은 **0건**(`EXTRA_PROSE_ITEMS` 에 항목 없음).
    저자 항목번호 1..12 결번 0 · 번호 없는 산문 항목 0 (`INTAKE_2026-09-04_post6.md` §1).

  · 🔑 **G-C 와 「비레그 퍼센트」** — post6 원문에는 레그가 아닌 소수점 수치가 둘 있다:
        2번째 줄 「▲ 태쏘 통계기반 트레이더 **1.0**.40」(프로그램 버전) ·
        66번째 줄 「이번주는 원금 대비 **8.3**% 수익률」(계좌 단위 자가보고 · `PREREG.md` §0-1 「기록만」).
    둘 다 **`ITEM_MARK`(「통계기반 자동매매」)가 없는 줄**에 있어 `parse_raw` 가 아예 읽지 않는다.
    ⇒ **면제 목록이 필요 없다** — 면제 기제는 원본 파서의 «항목 표지행 필터» 그 자체다.
    post5 도 같은 모양이었다(62번째 줄 「월 27% … 지난달은 20%」 · 78번째 줄 「손실률이 20%」가
    표지행 밖이라 G-C 분모에 안 들어갔다). **그 전례를 그대로 따르고 파서를 건드리지 않는다.**
    같은 이유로 항목 서술줄의 「HDR 60%」도 G-C 분모 밖이다.

  · 🔑 **`leg_open_ended` 규약(실측 승계)** — 이 게이트는 이 컬럼을 «판정»하지 않고 세기만 하지만,
    post6 행도 기존 169행과 같은 규약으로 적었다: **`open_ended == 1` 인 건의 «마지막» 레그 하나만 1**
    (post4 이노테크 4/4 · 금호건설 6/6 · post5 혜인 5/5 · 한국화장품제조 5/5 · 삼양바이오팜 2/2 ·
     광전자 5/5 — 예외 0). post6 은 미완결 4건(한라캐스트·아난티·지투파워·우리기술투자)의
    마지막 레그 4개만 1이다. 🔴 post6 의 미완결 판정은 `~` 문자가 아니라 **서술**이다(PD-4) —
    이 글에는 `~` 가 0건이므로 요약의 「미완결(~) 레그」 문구는 «서술 기준 미완결»을 센 값이다.

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
}

# 표지행 없는 산문 항목: log_no -> [(종목, 위치 함의 item_no)]
# 🔴 post6(224401108114)은 **0건** — 새 항목을 넣지 않는다(INTAKE §1 「번호 없는 산문 항목 0」).
EXTRA_PROSE_ITEMS = {
    "224385784257": [("솔트룩스", 7), ("빛과전자", 8)],
    "224393392105": [("SK아이이테크놀로지", 9)],
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

    🔑 `ITEM_MARK` 가 없는 줄은 아예 안 읽는다 — 이것이 「8.3% 주간 수익률」·「1.0.40」 같은
    **비레그 퍼센트의 면제 기제**다(면제 목록을 따로 두지 않는다 · post5 전례)."""
    out = {}
    for log_no in POSTS:
        rows = []
        for line in raw_path(log_no, override).read_text(encoding="utf-8").splitlines():
            if V.ITEM_MARK not in line:
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
    print("미완결 레그 %d (post6 은 `~` 0건 — 서술 기준 · PD-4)"
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
