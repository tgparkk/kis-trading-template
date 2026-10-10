import json
import subprocess

import pytest

from backtest.concept_axes.dtflow_shadow import guard as G
from backtest.concept_axes.dtflow_shadow import settings as S


def test_source_sha_normalizes_crlf(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    (tmp_path / "b.py").write_bytes(b"x = 1\ny = 2\n")
    assert G.source_sha("a.py", str(tmp_path)) == G.source_sha("b.py", str(tmp_path))


def test_refuse_live_tree():
    with pytest.raises(G.GuardError, match="라이브"):
        G.refuse_live_tree(S.LIVE_TREE + "/RoboTrader_template/scripts")


def test_check_home_collision(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "x"))
    monkeypatch.setenv("KIS_TASSO_SHADOW_HOME", str(tmp_path / "x"))
    with pytest.raises(G.GuardError, match="홈"):
        G.check_home()


def _repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    for a in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *a], cwd=r, check=True)
    (r / "f.txt").write_text("1")
    subprocess.run(["git", "add", "."], cwd=r, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=r, check=True)
    return r


def test_frozen_roundtrip_and_runtime_checks(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "abc"})
    r = _repo(tmp_path)
    fr = G.write_frozen(r)
    assert G.load_frozen() == fr and json.loads(S.frozen_path().read_text(encoding="utf-8"))["rule_v"] == S.RULE_V
    with pytest.raises(G.GuardError, match="브랜치"):
        G.check_runtime(r, fr)                       # 브랜치 위 = 거부(detached 만 허용)
    subprocess.run(["git", "switch", "-q", "--detach", fr.code_sha], cwd=r, check=True)
    assert G.check_runtime(r, fr) == fr.code_sha
    (r / "f.txt").write_text("2")
    with pytest.raises(G.GuardError, match="깨끗"):
        G.check_runtime(r, fr)


def test_runtime_refuses_changed_live_source(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "abc"})
    r = _repo(tmp_path)
    fr = G.write_frozen(r)
    subprocess.run(["git", "switch", "-q", "--detach", fr.code_sha], cwd=r, check=True)
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "zzz"})
    with pytest.raises(G.GuardError, match="원본 sha"):
        G.check_runtime(r, fr)
