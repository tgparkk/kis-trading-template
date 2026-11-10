"""minute_rules 단위 테스트 — 합성 분봉만(DB 스모크 1개는 `db` 마커 · 접속 안 되면 skip). 워크트리에서만 돌린다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]   # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
