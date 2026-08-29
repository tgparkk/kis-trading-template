# -*- coding: utf-8 -*-
"""원장 회수율 게이트 — 5번째 글(224393392105) 포함판.

🔴 `verify_ledger.py` 를 **고치지 않는다**(옛 글의 게이트 거동을 그대로 둔다).
   이 파일은 그 모듈에서 파서 조각(ITEM_MARK·NUM_RE·PCT_RE·load_csv)만 가져다 쓰고,
   **글별 원문 경로 지도**와 **번호 없는 산문 항목 선언**만 «더한다».
   새 글의 평문 경로는 인자로 준다:  --raw 224393392105=D:/archive/...

게이트(원본과 같은 정의):
  G-A  저자 항목번호가 각 글에서 1..N 연속인가 (결번 = 누락)
  G-B  원문의 매매행 수 == ledger_trades 행 수 (양방향)
  G-C  원문의 모든 퍼센트 수치 == ledger_legs 수치 (다중집합 양방향)
  G-D  ledger_trades.n_legs == ledger_legs 실제 레그 수 (건별)

번호 없는 산문 항목(EXTRA_PROSE_ITEMS)의 처리 — 두 전례를 갈라 쓴다:
  · 가온칩스(07-31) = 「통계기반 자동매매」 표지행이 **있는** 무번호 항목 ⇒ 파서가 잡고,
    G-A 는 원본대로 1번 결번만 면제한다(원본 `- {1}`).
  · SK아이이테크놀로지(08-29) = 표지행이 **없는** 본문 말미 산문 ⇒ 파서가 못 잡는다.
    위치 함의 번호(9)를 원장에 적되, **저자 번호가 아니므로 G-A 분모에서 뺀다**.
    G-B 분자에는 넣는다(원장에 행이 있으니까).

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
    "224393392105": ("2026-08-29", [Path(r"D:/archive/tasso-program-journal-20260829"), BASE, BASE / "raw"]),
}

# 🔴 원장에 «아직 없는» 글 — 게이트 실패가 아니라 사전 고지다(이 작업 범위 밖).
NOT_IN_LEDGER = {"224385784257": "2026-08-22 (4번째 글)"}

# 표지행 없는 산문 항목: log_no -> [(종목, 위치 함의 item_no)]
EXTRA_PROSE_ITEMS = {
    "224393392105": [("SK아이이테크놀로지", 9)],
}

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
    """원문 -> {log_no: [(item_no|None, 종목, [pct...])]}. 파싱 규칙은 원본과 동일."""
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
    print("미완결(~) 레그 %d" % sum(1 for l in legs if l["leg_open_ended"] == "1"))

    print("")
    print("=== G-A 저자 항목번호 결번 게이트 (글별) ===")
    for log_no, (n_total, got, missing, dup) in ga.items():
        print("  %s %s: 저자번호 %s / 표지행 %d / **결번 %d개**%s%s"
              % (POSTS[log_no][0], log_no,
                 ("%d..%d" % (got[0], got[-1])) if got else "없음",
                 n_total, len(missing),
                 (" %s" % missing) if missing else "",
                 (" / 중복 %s" % dup) if dup else ""))

    for log_no, label in NOT_IN_LEDGER.items():
        print("")
        print("[고지 · 게이트 아님] %s %s 는 **원장에 아직 없다** — 이번 작업 범위 밖." % (log_no, label))

    if failures:
        print("")
        print("=== 게이트 실패 ===")
        for f in failures:
            print(" ", f)
        return 1
    print("")
    print("모든 게이트 통과 (G-A/B/C/D)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main(sys.argv[1:]))
