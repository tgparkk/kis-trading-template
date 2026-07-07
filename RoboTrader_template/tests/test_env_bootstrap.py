"""
config/env_bootstrap.py 단위 테스트

.env 파일을 stdlib만으로 파싱해 os.environ 에 주입하는 부트스트랩 검증.
DB/네트워크 미사용. tmp_path + monkeypatch 로 완전 격리.
"""
import os

from config.env_bootstrap import load_env_file


def _write_env(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_parses_simple_key_value(tmp_path, monkeypatch):
    monkeypatch.delenv("KIS_DATA_SOURCE", raising=False)
    path = _write_env(tmp_path, "KIS_DATA_SOURCE=new\n")
    setted = load_env_file(path)
    assert setted.get("KIS_DATA_SOURCE") == "new"
    assert os.environ["KIS_DATA_SOURCE"] == "new"


def test_ignores_comments_and_blanks(tmp_path, monkeypatch):
    monkeypatch.delenv("FOO", raising=False)
    text = "# 주석 라인\n\n   \nFOO=bar\n# 또 주석\n"
    path = _write_env(tmp_path, text)
    setted = load_env_file(path)
    assert setted == {"FOO": "bar"}
    assert os.environ["FOO"] == "bar"


def test_strips_surrounding_quotes(tmp_path, monkeypatch):
    monkeypatch.delenv("Q1", raising=False)
    monkeypatch.delenv("Q2", raising=False)
    path = _write_env(tmp_path, 'Q1="double"\nQ2=\'single\'\n')
    setted = load_env_file(path)
    assert setted["Q1"] == "double"
    assert setted["Q2"] == "single"


def test_handles_export_prefix(tmp_path, monkeypatch):
    monkeypatch.delenv("EXPORTED", raising=False)
    path = _write_env(tmp_path, "export EXPORTED=yes\n")
    setted = load_env_file(path)
    assert setted["EXPORTED"] == "yes"
    assert os.environ["EXPORTED"] == "yes"


def test_ignores_malformed_lines(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOD", raising=False)
    text = "this_line_has_no_equals\nGOOD=1\n=novaluekey\n"
    path = _write_env(tmp_path, text)
    setted = load_env_file(path)
    assert setted.get("GOOD") == "1"
    # 등호 없는 라인은 무시
    assert "this_line_has_no_equals" not in setted


def test_strips_whitespace_around_key_and_value(tmp_path, monkeypatch):
    monkeypatch.delenv("SPACED", raising=False)
    path = _write_env(tmp_path, "  SPACED  =   spaced_val   \n")
    setted = load_env_file(path)
    assert setted["SPACED"] == "spaced_val"


def test_does_not_overwrite_existing_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMESCALE_DB", "robotrader")
    path = _write_env(tmp_path, "TIMESCALE_DB=kis_template\n")
    setted = load_env_file(path)
    # 이미 존재하는 키는 건드리지 않음 (OS/명시 env 우선)
    assert "TIMESCALE_DB" not in setted
    assert os.environ["TIMESCALE_DB"] == "robotrader"


def test_missing_file_returns_empty_and_no_raise(tmp_path):
    missing = str(tmp_path / "does_not_exist.env")
    result = load_env_file(missing)
    assert result == {}


def test_integration_timescale_db_reaches_environ(tmp_path, monkeypatch):
    monkeypatch.delenv("TIMESCALE_DB", raising=False)
    path = _write_env(tmp_path, "TIMESCALE_DB=kis_template\n")
    load_env_file(path)
    assert os.getenv("TIMESCALE_DB") == "kis_template"


def test_idempotent_second_call_safe(tmp_path, monkeypatch):
    monkeypatch.delenv("IDEM", raising=False)
    path = _write_env(tmp_path, "IDEM=1\n")
    first = load_env_file(path)
    assert first == {"IDEM": "1"}
    # 두 번째 호출: 이미 environ 에 있으므로 아무 것도 새로 설정하지 않음
    second = load_env_file(path)
    assert second == {}
    assert os.environ["IDEM"] == "1"
