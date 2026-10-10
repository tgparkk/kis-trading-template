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
    monkeypatch.setattr(S, "LIVE_SOURCES", ("x.py",))
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
    monkeypatch.setattr(S, "LIVE_SOURCES", ("x.py",))
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "abc"})
    r = _repo(tmp_path)
    fr = G.write_frozen(r)
    subprocess.run(["git", "switch", "-q", "--detach", fr.code_sha], cwd=r, check=True)
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "zzz"})
    with pytest.raises(G.GuardError, match="원본 sha"):
        G.check_runtime(r, fr)


def _frozen_detached(monkeypatch, tmp_path, sources=("x.py",)):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(S, "LIVE_SOURCES", tuple(sources))
    monkeypatch.setattr(G, "_sources", lambda: {k: "abc" for k in sources})
    r = _repo(tmp_path)
    fr = G.write_frozen(r)
    subprocess.run(["git", "switch", "-q", "--detach", fr.code_sha], cwd=r, check=True)
    return r, fr


def test_runtime_refuses_empty_sources(monkeypatch, tmp_path):
    r, fr = _frozen_detached(monkeypatch, tmp_path)
    empty = G.Frozen(fr.code_sha, fr.rule_v, fr.frozen_at, {}, fr.credit_lag_k)
    with pytest.raises(G.GuardError, match="원본 목록"):
        G.check_runtime(r, empty)


def test_runtime_refuses_partial_sources(monkeypatch, tmp_path):
    r, fr = _frozen_detached(monkeypatch, tmp_path, sources=("x.py", "y.py"))
    partial = G.Frozen(fr.code_sha, fr.rule_v, fr.frozen_at, {"x.py": "abc"}, fr.credit_lag_k)
    with pytest.raises(G.GuardError, match="원본 목록.*y.py"):
        G.check_runtime(r, partial)


def test_runtime_refuses_extra_sources(monkeypatch, tmp_path):
    r, fr = _frozen_detached(monkeypatch, tmp_path)
    extra = G.Frozen(fr.code_sha, fr.rule_v, fr.frozen_at, {"x.py": "abc", "z.py": "q"}, fr.credit_lag_k)
    with pytest.raises(G.GuardError, match="원본 목록.*z.py"):
        G.check_runtime(r, extra)


def test_runtime_refuses_head_mismatch(monkeypatch, tmp_path):
    r, fr = _frozen_detached(monkeypatch, tmp_path)
    (r / "g.txt").write_text("n")
    subprocess.run(["git", "add", "."], cwd=r, check=True)
    subprocess.run(["git", "commit", "-qm", "d"], cwd=r, check=True)
    subprocess.run(["git", "switch", "-q", "--detach", "HEAD"], cwd=r, check=True)
    with pytest.raises(G.GuardError, match="HEAD"):
        G.check_runtime(r, fr)


def test_runtime_refuses_rule_v_mismatch(monkeypatch, tmp_path):
    r, fr = _frozen_detached(monkeypatch, tmp_path)
    old = G.Frozen(fr.code_sha, "v0", fr.frozen_at, fr.sources, fr.credit_lag_k)
    with pytest.raises(G.GuardError, match="rule_v"):
        G.check_runtime(r, old)


def test_runtime_refuses_credit_lag_k_mismatch(monkeypatch, tmp_path):
    r, fr = _frozen_detached(monkeypatch, tmp_path)
    monkeypatch.setattr(S, "CREDIT_LAG_K", 3)
    with pytest.raises(G.GuardError, match="credit_lag_k"):
        G.check_runtime(r, fr)


def test_write_frozen_refuses_dirty_tree(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "abc"})
    r = _repo(tmp_path)
    (r / "f.txt").write_text("dirty")
    with pytest.raises(G.GuardError, match="깨끗"):
        G.write_frozen(r)
    assert not S.frozen_path().exists()


def test_write_frozen_refuses_live_tree(monkeypatch, tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    monkeypatch.setattr(S, "LIVE_TREE", str(live).replace("\\", "/"))
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "abc"})
    r = _repo(live)
    with pytest.raises(G.GuardError, match="라이브"):
        G.write_frozen(r)
    assert not S.frozen_path().exists()


def test_write_frozen_appends_history(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "abc"})
    r = _repo(tmp_path)
    first = G.write_frozen(r)
    second = G.write_frozen(r)
    lines = (S.frozen_path().parent / "frozen_history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["code_sha"] == first.code_sha
    assert G.load_frozen() == second


def test_check_home_refuses_default_llm_home(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("KIS_LLM_SHADOW_HOME", raising=False)
    monkeypatch.delenv("KIS_TASSO_SHADOW_HOME", raising=False)
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "kis-llm-shadow"))
    with pytest.raises(G.GuardError, match="홈"):
        G.check_home()
