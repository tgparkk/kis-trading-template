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


# ---- final fix: I3 — 가드 예외는 전부 GuardError(+ 고정 reason 코드) ----
@pytest.mark.parametrize("text", ["{bad json", "[1, 2]", '{"x": 1}', b"\xff\xfe\x00bad",
                                  '{"code_sha": "a", "rule_v": "v1", "frozen_at": "t", "sources": 5}',
                                  '{"code_sha": "a", "rule_v": "v1", "frozen_at": "t", "sources": {}, "credit_lag_k": "3"}'])
def test_load_frozen_corrupt_is_guard_error(monkeypatch, tmp_path, text):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path))
    p = S.frozen_path()
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8")
    with pytest.raises(G.GuardError) as ei:
        G.load_frozen()
    assert ei.value.reason == "frozen_corrupt"


def test_load_frozen_missing_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path))
    with pytest.raises(G.GuardError) as ei:
        G.load_frozen()
    assert ei.value.reason == "frozen_missing"


def test_source_sha_missing_file_is_guard_error(tmp_path):
    with pytest.raises(G.GuardError) as ei:
        G.source_sha("strategies/gone.py", str(tmp_path))
    assert ei.value.reason == "source_unreadable"


def test_runtime_reason_codes(monkeypatch, tmp_path):
    r, fr = _frozen_detached(monkeypatch, tmp_path)
    monkeypatch.setattr(G, "_sources", lambda: {"x.py": "zzz"})
    with pytest.raises(G.GuardError) as ei:
        G.check_runtime(r, fr)
    assert ei.value.reason == "source_sha"
    with pytest.raises(G.GuardError) as ei:
        G.refuse_live_tree(S.LIVE_TREE + "/RoboTrader_template")
    assert ei.value.reason == "live_tree"


# ---- 개정 2: B-2 «경고만» 원본(API 2파일) vs «멈춤» 원본(스크리너 5파일) ----
import ast  # noqa: E402

_REAL_SOURCES = G._sources
_REAL_SOURCE_SHA = G.source_sha


def test_live_sources_split_stop_and_warn():
    assert S.LIVE_SOURCES == S.LIVE_SOURCES_STOP + S.LIVE_SOURCES_WARN
    assert S.LIVE_SOURCES_WARN == ("api/kis_market_api.py", "api/kis_auth.py")
    assert len(S.LIVE_SOURCES_STOP) == 5 and not set(S.LIVE_SOURCES_STOP) & set(S.LIVE_SOURCES_WARN)


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module)
    return out


def test_recorder_never_imports_warn_only_api_files():
    """«경고만» 의 전제: 기록기(패키지 + 러너)는 라이브 `api` 패키지를 import 하지 않는다 → 그 2파일이 바뀌어도 기록값 불변."""
    files = sorted(S.PKG.glob("*.py")) + [S.RT_ROOT / "scripts" / "dtflow_shadow_recorder.py"]
    assert len(files) >= 10
    for f in files:
        mods = _imported_modules(f)
        assert not any(m == "api" or m.startswith("api.") for m in mods), (f.name, mods)


def _frozen_stop_warn(monkeypatch, tmp_path):
    monkeypatch.setattr(S, "LIVE_SOURCES_STOP", ("s.py",))
    monkeypatch.setattr(S, "LIVE_SOURCES_WARN", ("api/w.py",))
    return _frozen_detached(monkeypatch, tmp_path, sources=("s.py", "api/w.py"))


def test_warn_only_source_changed_warns_and_continues(monkeypatch, tmp_path):
    r, fr = _frozen_stop_warn(monkeypatch, tmp_path)
    monkeypatch.setattr(G, "_sources", lambda: {"s.py": "abc", "api/w.py": "zzz"})
    warns = []
    assert G.check_runtime(r, fr, warns) == fr.code_sha
    assert warns == ["api/w.py:sha"]


def test_warn_only_source_unreadable_warns_and_continues(monkeypatch, tmp_path):
    r, fr = _frozen_stop_warn(monkeypatch, tmp_path)
    monkeypatch.setattr(G, "_sources", _REAL_SOURCES)

    def fake_sha(rel, root=None):
        if rel == "api/w.py":
            raise G.GuardError("gone", "source_unreadable")
        return "abc"
    monkeypatch.setattr(G, "source_sha", fake_sha)
    warns = []
    assert G.check_runtime(r, fr, warns) == fr.code_sha
    assert warns == ["api/w.py:unreadable"]


def test_stop_source_changed_refuses_even_with_warn_list(monkeypatch, tmp_path):
    r, fr = _frozen_stop_warn(monkeypatch, tmp_path)
    monkeypatch.setattr(G, "_sources", lambda: {"s.py": "zzz", "api/w.py": "zzz"})
    warns = []
    with pytest.raises(G.GuardError) as ei:
        G.check_runtime(r, fr, warns)
    assert ei.value.reason == "source_sha" and "s.py" in str(ei.value)


def test_stop_source_unreadable_refuses(monkeypatch, tmp_path):
    r, fr = _frozen_stop_warn(monkeypatch, tmp_path)
    monkeypatch.setattr(G, "_sources", _REAL_SOURCES)

    def fake_sha(rel, root=None):
        if rel == "s.py":
            raise G.GuardError("gone", "source_unreadable")
        return "abc"
    monkeypatch.setattr(G, "source_sha", fake_sha)
    with pytest.raises(G.GuardError) as ei:
        G.check_runtime(r, fr, [])
    assert ei.value.reason == "source_unreadable"


def test_warn_only_mismatch_without_warn_list_is_strict(monkeypatch, tmp_path):
    """호출자가 경고 목록을 받지 않으면(기본) 예전처럼 거부 — 닫힌 쪽 기본값."""
    r, fr = _frozen_stop_warn(monkeypatch, tmp_path)
    monkeypatch.setattr(G, "_sources", lambda: {"s.py": "abc", "api/w.py": "zzz"})
    with pytest.raises(G.GuardError) as ei:
        G.check_runtime(r, fr)
    assert ei.value.reason == "source_sha"


def test_write_frozen_requires_every_source_readable(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(S, "LIVE_SOURCES", ("s.py", "api/w.py"))
    monkeypatch.setattr(S, "LIVE_SOURCES_STOP", ("s.py",))
    monkeypatch.setattr(S, "LIVE_SOURCES_WARN", ("api/w.py",))

    def fake_sha(rel, root=None):
        if rel == "api/w.py":
            raise G.GuardError("gone", "source_unreadable")
        return "abc"
    monkeypatch.setattr(G, "source_sha", fake_sha)
    r = _repo(tmp_path)
    with pytest.raises(G.GuardError) as ei:
        G.write_frozen(r)
    assert ei.value.reason == "source_unreadable" and not S.frozen_path().exists()
