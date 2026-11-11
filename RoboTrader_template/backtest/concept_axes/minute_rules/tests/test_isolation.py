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


PKG = Path(__file__).resolve().parents[1]
OPS_TOP = {"core", "bot", "framework", "strategies", "collectors", "runners", "main", "api", "db", "signals", "tools"}
ALLOWED_OPS = {"utils.price_utils", "config.constants"}        # 초안 §1 import 방향 = 연구 → 이 둘만


def test_minute_rules_imports_only_allowed_ops_modules():
    """반대 방향 — minute_rules 소스가 직접 import 하는 운영 모듈은 `utils.price_utils`·`config.constants` 뿐.
    (⚠ `backtest/__init__.py` · `utils/price_utils.py` 가 끌어오는 전이 import 는 1단계부터 있던 것 — 세지 않는다.)"""
    import ast
    bad = []
    for p in sorted(PKG.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            for nm in names:
                top = nm.split(".")[0]
                if (top in OPS_TOP or top in ("utils", "config")) and nm not in ALLOWED_OPS:
                    bad.append(f"{p.name}: {nm}")
    assert bad == []


def test_stats_module_not_collected_by_pytest():
    """`test_stats.py`(사전등록 §9 이름의 통계 모듈)는 수집 제외 — conftest `collect_ignore` · 안에 test_ 이름 0."""
    import importlib

    conf = importlib.import_module("backtest.concept_axes.minute_rules.conftest")
    assert "test_stats.py" in conf.collect_ignore
    mod = importlib.import_module("backtest.concept_axes.minute_rules.test_stats")
    assert [n for n in dir(mod) if n.lower().startswith("test")] == []
