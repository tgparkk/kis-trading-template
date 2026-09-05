# -*- coding: utf-8 -*-
"""`verify_ledger_post6.py` 의 «가드 시험» — 게이트가 실제로 실패를 내는지 본다.

🔑 계열 규칙: *캡처 장치도 가드다 — 가드를 시험하지 않으면 그것도 장식이다*
(`PREREG_POST6.md` §5-3 5번의 문형을 원장 게이트에 그대로 적용).
🔑 계열 규칙: *단독 단언은 판별력이 없다 → 대칭 단언* — 「통과했다」만 보이면
게이트가 항상 통과하는 장식일 수 있으므로 **일부러 깨뜨린 사본에서 실패가 나는지**도 본다.

실행: `python test_post6_ledger.py`  (시스템 python · 라이브 트리 import 0건)

  P  양성 대조 — 손대지 않은 원장 + 원문 ⇒ 종료코드 0 · 실패 0건
  N1 G-A  원문의 항목번호를 7 → 9 로 바꿔 결번·중복을 만든다
  N2 G-B  post6 매매행 1개를 지운다 (원문 12 != trades 11)
  N3 G-C  post6 레그 값 하나를 22.24 → 22.25 로 바꾼다 (다중집합 양방향)
  N4 G-D  post6 매매건의 `n_legs` 를 7 → 6 으로 바꾼다
  N5 P6-G-E  `fill_level=first_only` 인 행의 `fill_n` 을 3 으로 바꾼다

🔴 원본 파일은 하나도 건드리지 않는다 — 전부 임시 디렉토리 사본에서만 깨뜨린다.
"""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import verify_ledger as V
import verify_ledger_post6 as P6

BASE = Path(__file__).resolve().parent
LOG = "224401108114"
RAW_SRC = P6.raw_path(LOG, {})            # 실제 원문(보관소) 경로


def run_gate(csv_dir: Path, raw_file: Path):
    """게이트를 «사본» 위에서 한 번 돌린다. 반환 = (종료코드, 실패목록, 출력)."""
    old_base, old_failures = V.BASE, list(P6.failures)
    V.BASE = csv_dir
    P6.failures.clear()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = P6.main(["--raw", "%s=%s" % (LOG, raw_file)])
        return rc, list(P6.failures), buf.getvalue()
    finally:
        V.BASE = old_base
        P6.failures.clear()
        P6.failures.extend(old_failures)


def fresh(tmp: Path, tag: str):
    """원장 2종 + 원문 1종을 사본으로 깐다."""
    d = tmp / tag
    d.mkdir()
    for n in ("ledger_trades.csv", "ledger_legs.csv"):
        shutil.copyfile(BASE / n, d / n)
    shutil.copyfile(RAW_SRC, d / RAW_SRC.name)
    return d


def _write(path: Path, txt: str):
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(txt)


def edit(path: Path, old: str, new: str, expect: int = 1):
    with path.open(encoding="utf-8", newline="") as fh:
        txt = fh.read()
    assert txt.count(old) == expect, "치환 대상 %d건(기대 %d): %r" % (txt.count(old), expect, old)
    _write(path, txt.replace(old, new, expect))


def drop_line(path: Path, needle: str):
    with path.open(encoding="utf-8", newline="") as fh:
        lines = fh.read().splitlines(True)
    keep = [l for l in lines if needle not in l]
    assert len(keep) == len(lines) - 1, "지울 줄이 %d개" % (len(lines) - len(keep))
    _write(path, "".join(keep))


def main() -> int:
    bad = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ---- P: 양성 대조 -------------------------------------------------
        d = fresh(tmp, "P")
        rc, fails, _ = run_gate(d, d / RAW_SRC.name)
        ok = (rc == 0 and not fails)
        print("P  양성 대조                 rc=%d 실패 %d건  %s" % (rc, len(fails), "OK" if ok else "🔴"))
        if not ok:
            bad.append(("P", fails))

        # ---- N1~N5: 음성 대조 (일부러 깨뜨린 사본) --------------------------
        cases = []

        d = fresh(tmp, "N1")
        edit(d / RAW_SRC.name, "7. 현대약품 /", "9. 현대약품 /")
        cases.append(("N1", "G-A", d))

        d = fresh(tmp, "N2")
        drop_line(d / "ledger_trades.csv", "%s,2026-09-04,1.0.40,9,쿠콘," % LOG)
        cases.append(("N2", "G-B", d))

        d = fresh(tmp, "N3")
        edit(d / "ledger_legs.csv",
             "%s,2026-09-04,1.0.40,4,헥토파이낸셜,1,22.24,0,0" % LOG,
             "%s,2026-09-04,1.0.40,4,헥토파이낸셜,1,22.25,0,0" % LOG)
        cases.append(("N3", "G-C", d))

        d = fresh(tmp, "N4")
        edit(d / "ledger_trades.csv",
             "%s,2026-09-04,1.0.40,8,원익,7,0,0," % LOG,
             "%s,2026-09-04,1.0.40,8,원익,6,0,0," % LOG)
        cases.append(("N4", "G-D", d))

        d = fresh(tmp, "N5")
        edit(d / "ledger_trades.csv",
             "%s,2026-09-04,1.0.40,9,쿠콘,2,0,0,2026-08-28,exact,first_only,1," % LOG,
             "%s,2026-09-04,1.0.40,9,쿠콘,2,0,0,2026-08-28,exact,first_only,3," % LOG)
        cases.append(("N5", "P6-G-E", d))

        for tag, gate, d in cases:
            rc, fails, _ = run_gate(d, d / RAW_SRC.name)
            hit = [f for f in fails if f.startswith("[%s]" % gate)]
            ok = (rc == 1 and hit)
            print("%s 음성 대조 %-8s     rc=%d 실패 %d건 (그중 %s %d건)  %s"
                  % (tag, gate, rc, len(fails), gate, len(hit), "OK" if ok else "🔴"))
            for f in hit[:1]:
                print("     └ %s" % f)
            if not ok:
                bad.append((tag, fails))

    print("")
    if bad:
        print("🔴 가드 시험 실패 %d건" % len(bad))
        for tag, fails in bad:
            print("  %s: %s" % (tag, fails))
        return 1
    print("가드 시험 6/6 통과 — 게이트는 통과도 «실패도» 낸다 (장식이 아니다)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
