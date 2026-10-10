"""dtflow_shadow 단위 테스트 — 합성 데이터 · 가짜 연결 · DB·KIS 없음. 워크트리에서만."""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]          # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if "backtest" not in sys.modules:                   # backtest/__init__ 의 엔진·전략 import 회피(태쏘 러너 선례)
    _pkg = types.ModuleType("backtest")
    _pkg.__path__ = [str(ROOT / "backtest")]
    sys.modules["backtest"] = _pkg
