"""run5 전 경로 스모크. 소수 종목 + 정의 1개로 크래시·스키마만 본다.

⚠️ 여기서 나오는 Δ·p 는 판정이 아니다. 표본이 잘려 있다.
"""
import json
import os
import shutil
import tempfile
from pathlib import Path

import lab.run5 as run5
from lab.data import load_daily

REAL = load_daily("2021-01-04", "2026-07-31")
CODES = sorted(REAL["stock_code"].unique())[:150]
SUB = REAL[REAL["stock_code"].isin(CODES)].reset_index(drop=True)
print(f"smoke universe: {len(CODES)} codes / {len(SUB):,} rows", flush=True)

run5.load_daily = lambda *a, **k: SUB

tmp = Path(tempfile.mkdtemp(prefix="run5smoke_"))
(tmp / "out5").mkdir()
defs = json.loads((Path("out") / "selected_definitions.json").read_text(encoding="utf-8"))
(tmp / "out5" / "selected_definitions.json").write_text(
    json.dumps(defs[:1], ensure_ascii=False), encoding="utf-8")

os.chdir(tmp)
run5.main()

print("\n--- artifacts ---")
for f in sorted((tmp / "out5").iterdir()):
    print(f"{f.name:28} {f.stat().st_size:>9,} B")
print(json.dumps(json.loads((tmp / "out5" / "verdict5.json").read_text(encoding="utf-8")),
                 indent=2, ensure_ascii=False)[:1600])
shutil.rmtree(tmp, ignore_errors=True)
