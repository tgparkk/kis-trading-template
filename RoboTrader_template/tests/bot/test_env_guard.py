"""TDD tests for bot.env_guard — startup environment guard.

2026-06-30: template venv was a copy of sibling quant venv; this guard detects
wrong venv / stale finance-datareader at bot startup.
"""
import os
import sys
import pytest

import FinanceDataReader  # ensure cached in sys.modules before patching


# ---------------------------------------------------------------------------
# 1. wrong venv → problem mentioning "venv"
# ---------------------------------------------------------------------------

def test_wrong_venv_reported(monkeypatch, tmp_path):
    """sys.prefix != project_root/venv => problem list contains a 'venv' message."""
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "some_other_venv"))
    from bot.env_guard import check_environment
    problems = check_environment(str(tmp_path / "my_project"))
    assert problems, "Expected at least one problem"
    assert any("venv" in p for p in problems)


# ---------------------------------------------------------------------------
# 2. correct venv + FDR >= 0.9.202 → empty list
# ---------------------------------------------------------------------------

def test_correct_env_no_problems():
    """sys.prefix == project_root/venv AND FDR >= 0.9.202 => no problems."""
    # os.path.dirname(sys.prefix) + '/venv' reconstructs sys.prefix exactly
    project_root = os.path.dirname(sys.prefix)
    from bot.env_guard import check_environment
    problems = check_environment(project_root)
    assert problems == [], f"Unexpected problems: {problems}"


# ---------------------------------------------------------------------------
# 3. FDR version too low → FDR version problem reported
# ---------------------------------------------------------------------------

def test_fdr_version_too_low(monkeypatch):
    """finance-datareader.__version__ < 0.9.202 => problem reported."""
    monkeypatch.setattr(FinanceDataReader, "__version__", "0.9.102")
    # Use correct project_root so the venv path check passes
    project_root = os.path.dirname(sys.prefix)
    from bot.env_guard import check_environment
    problems = check_environment(project_root)
    assert any(
        "0.9.102" in p or "finance-datareader" in p.lower()
        for p in problems
    ), f"FDR problem not in: {problems}"


# ---------------------------------------------------------------------------
# 4a. assert_correct_environment raises SystemExit on bad env
# ---------------------------------------------------------------------------

def test_assert_exits_on_bad_env(monkeypatch, tmp_path):
    """assert_correct_environment calls sys.exit(1) when prefix is wrong."""
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "bad_venv"))
    monkeypatch.delenv("ALLOW_FOREIGN_VENV", raising=False)
    from bot.env_guard import assert_correct_environment
    with pytest.raises(SystemExit):
        assert_correct_environment(str(tmp_path / "project"))


# ---------------------------------------------------------------------------
# 4b. ALLOW_FOREIGN_VENV=1 suppresses exit, returns None
# ---------------------------------------------------------------------------

def test_assert_no_exit_with_override(monkeypatch, tmp_path):
    """ALLOW_FOREIGN_VENV=1 => no SystemExit, returns None."""
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "bad_venv"))
    monkeypatch.setenv("ALLOW_FOREIGN_VENV", "1")
    from bot.env_guard import assert_correct_environment
    result = assert_correct_environment(str(tmp_path / "project"))
    assert result is None
