"""초안 §9 ⑬ — 운영 디렉토리에서 `minute_rules` 참조 0(`grep -rn minute_rules core bot framework strategies collectors
runners utils main.py` 의 파이썬판 · 리뷰 A6)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]   # …/RoboTrader_template
OPS_DIRS = ["core", "bot", "framework", "strategies", "collectors", "runners", "utils"]
OPS_FILES = ["main.py"]


def _ops_files():
    for d in OPS_DIRS:
        base = ROOT / d
        assert base.is_dir(), f"운영 디렉토리 없음: {base}"
        yield from (p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for f in OPS_FILES:
        p = ROOT / f
        assert p.is_file(), f"운영 파일 없음: {p}"
        yield p


def test_no_ops_reference_to_minute_rules():
    hits = []
    for p in _ops_files():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if "minute_rules" in line:
                hits.append(f"{p.relative_to(ROOT)}:{n}")
    assert hits == []
