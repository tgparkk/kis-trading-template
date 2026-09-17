"""cap_skip_ledger 단위 테스트 — DB·로그 없음. 워크트리에서만 돌린다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]   # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
