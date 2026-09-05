# -*- coding: utf-8 -*-
"""C-21 · `ledger_trades.csv` 의 `fill_level` 축 분리 — 1회성 backfill (멱등).

🔴 **결함**(`PREREG_POST6.md` §5-5): `fill_level` **한 컬럼에 «두 축»이 섞여 있었다** —
   범주(`unknown`·`first_only`·`full`)와 **정수 차수**(`1`~`5`, post4·post5 행)가 같은 칸에 있다.
   그래서 「`first_only` 가 몇 건인가」라는 질문의 답이 **판독기마다 달랐다**
   (post5 삼양바이오팜은 `fill_level=1` 이라 «범주로 세면» 빠지는데,
   `RESULTS_RECONSTRUCT_POST5.md`·`RESULTS_LADDER_TRANCHE.md` 는 그 건을 `first_only` 라 불렀다).

**규약**(§5-5-1·2 그대로 · 기계적 · 사람 판단 0):

  · `fill_level == first_only`  ⇒ `fill_n = 1`            · `fill_level` 유지
  · `fill_level` 이 정수 `k`    ⇒ `fill_n = k`            · `fill_level = (k == 1 ? first_only : partial)`
  · `fill_level == full`        ⇒ `fill_n` 빈칸           · `fill_level = full`
  · `fill_level == unknown`     ⇒ `fill_n` 빈칸           · `fill_level = unknown`

`fill_n` 은 `fill_level` **바로 뒤**에 끼운다(§5-5-5). 원장 51행이 전부 정확히 16필드이고
따옴표가 0개라 위치 삽입이 안전하다 — 그래도 **모든 판독기는 이름 기준**(`csv.DictReader`)이다(실측).

검증은 이 스크립트가 아니라 **게이트**가 한다 — `verify_ledger_post5.py` 의 `P6-G-E`.

    python backfill_fill_n.py            # 적용 (이미 적용됐으면 무변경)
    python backfill_fill_n.py --dry-run  # 바뀔 내용만 인쇄

라이브 트리 import 0건(표준 라이브러리만). DB 미사용.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
LEDGER = BASE / "ledger_trades.csv"

CATEGORIES = ("first_only", "partial", "full", "unknown")


def convert(fill_level: str):
    """(fill_level, fill_n) — §5-5-2 규약. 사람 판단이 들어갈 자리가 없다."""
    v = (fill_level or "").strip()
    if v.isdigit():
        k = int(v)
        return ("first_only" if k == 1 else "partial"), str(k)
    if v == "first_only":
        return "first_only", "1"
    if v in ("full", "unknown"):
        return v, ""
    raise SystemExit("알 수 없는 fill_level 값: %r — 규약에 없다(§5-5-2)" % fill_level)


def main(argv) -> int:
    dry = "--dry-run" in argv
    with LEDGER.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        header = list(rows[0].keys()) if rows else []

    if "fill_n" in header:
        # 멱등 — 이미 적용됐다. **검증은 여기서 하지 않는다**(게이트가 한다: `P6-G-E`).
        print("이미 적용됨 (fill_n 컬럼 존재) · %d행 — 무변경. 검증은 verify_ledger_post5.py 의 P6-G-E."
              % len(rows))
        print("현재 (fill_level, fill_n) 분포:")
        for k, v in sorted(Counter((r["fill_level"], r["fill_n"]) for r in rows).items()):
            print("   %-12s %-3s %d" % (k[0], k[1] or "(빈칸)", v))
        return 0

    i = header.index("fill_level")
    new_header = header[:i + 1] + ["fill_n"] + header[i + 1:]
    changed = []
    out_rows = []
    for r in rows:
        lv, n = convert(r["fill_level"])
        if lv != r["fill_level"]:
            changed.append((r["post_log_no"], r["item_no"], r["stock_name"], r["fill_level"], lv, n))
        rec = dict(r)
        rec["fill_level"], rec["fill_n"] = lv, n
        out_rows.append(rec)

    print("행 %d · 컬럼 %d → %d (fill_level 바로 뒤에 fill_n 삽입)"
          % (len(rows), len(header), len(new_header)))
    print("이전 fill_level 분포: %s" % dict(Counter(r["fill_level"] for r in rows)))
    print("이후 (fill_level, fill_n) 분포:")
    for k, v in sorted(Counter((r["fill_level"], r["fill_n"]) for r in out_rows).items()):
        print("   %-12s %-3s %d" % (k[0], k[1] or "(빈칸)", v))
    print("범주 바뀐 행 %d:" % len(changed))
    for c in changed:
        print("   %s item %s %s: %s -> %s / fill_n=%s" % c)
    if dry:
        print("[dry-run] 파일을 쓰지 않았다.")
        return 0

    with LEDGER.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=new_header, lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)
    print("[written] %s" % LEDGER.name)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main(sys.argv[1:]))
