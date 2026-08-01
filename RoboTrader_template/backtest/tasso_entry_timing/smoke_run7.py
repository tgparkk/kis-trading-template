"""run7 전 경로 스모크. 소수 종목 + 정의 2개로 게이트·스키마만 본다.

⚠️ 여기서 나오는 Δ·p 는 판정이 아니다. 표본이 잘려 있다.
"""
import json
import os
import shutil
import tempfile
from pathlib import Path

import lab.run7 as run7
from lab.data import load_daily
from lab.run7 import DANAL

REAL = load_daily("2021-01-04", "2026-07-31")
CODES = sorted(REAL["stock_code"].unique())[:150]
if DANAL["code"] not in CODES:          # 게이트 C 가 의미를 가지려면 다날이 있어야 한다
    CODES.append(DANAL["code"])
SUB = REAL[REAL["stock_code"].isin(CODES)].reset_index(drop=True)
print(f"smoke universe: {len(CODES)} codes / {len(SUB):,} rows", flush=True)

run7.load_daily = lambda *a, **k: SUB
_full = run7.definitions()
run7.definitions = lambda: _full[:2]     # 정의 2개만

tmp = Path(tempfile.mkdtemp(prefix="run7smoke_"))
os.chdir(tmp)
run7.main()

print("\n--- artifacts ---")
for f in sorted((tmp / "out7").iterdir()):
    print(f"{f.name:30} {f.stat().st_size:>9,} B")
shutil.rmtree(tmp, ignore_errors=True)
