import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]          # backtest/paper_vs_real_compare
RT_ROOT = PKG.parents[1]                             # RoboTrader_template (운영 표 동일성 시험용)
for p in (PKG, RT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
