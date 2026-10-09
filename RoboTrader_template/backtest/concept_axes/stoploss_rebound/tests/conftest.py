"""stoploss_rebound 단위 테스트 — 합성(가짜) 데이터만 · DB 없음. 워크트리에서만 돌린다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]   # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
