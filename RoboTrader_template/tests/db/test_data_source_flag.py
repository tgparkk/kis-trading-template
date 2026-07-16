"""가격 소스 resolver 플래그 회귀 테스트.

2026-07-16 연구 소스 통일로 기본값이 legacy → new(kis_template) 로 뒤집혔다.
근거: 라이브는 .env(KIS_DATA_SOURCE=new)로 이미 kis_template 을 보지만, .env 가
없는 연구 프로세스(clean checkout·워크트리·CI)는 코드 기본값으로 떨어져 2026-07-10
동결된 레거시 DB 를 읽고 있었다. 상세는 tests/test_research_data_source.py 참조.
"""
import importlib


def _reload(monkeypatch, **env):
    for k in ("KIS_DATA_SOURCE", "QUANT_DB", "MINUTE_DB"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import config.constants as c
    return importlib.reload(c)


def test_resolve_daily_defaults_to_kis_template(monkeypatch):
    """env 없음(=연구 기본 실행) → 일봉은 kis_template."""
    c = _reload(monkeypatch)
    assert c.resolve_daily_source_db() == "kis_template"


def test_resolve_minute_defaults_to_kis_template(monkeypatch):
    """env 없음(=연구 기본 실행) → 분봉은 kis_template."""
    c = _reload(monkeypatch)
    assert c.resolve_minute_source_db() == "kis_template"


def test_resolve_daily_legacy_rollback(monkeypatch):
    """롤백 경로 유지: KIS_DATA_SOURCE=legacy → robotrader_quant."""
    c = _reload(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_daily_source_db() == "robotrader_quant"


def test_resolve_minute_legacy_rollback(monkeypatch):
    """롤백 경로 유지: KIS_DATA_SOURCE=legacy → robotrader."""
    c = _reload(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_minute_source_db() == "robotrader"


def test_kis_data_source_module_constant_defaults_new(monkeypatch):
    """모듈 상수도 new 기본 — collectors reconcile 게이트가 이 값을 본다.

    (라이브 .env 는 new 를 명시하므로 교차비교는 이미 skip 중 = 동작 변화 없음.
     레거시 DB 가 2026-07-10 동결된 지금 교차비교는 거짓 불일치만 낳는다.)
    """
    c = _reload(monkeypatch)
    assert c.KIS_DATA_SOURCE == "new"


def test_explicit_new_still_points_to_kis_template(monkeypatch):
    """명시적 new(라이브 .env 와 동일 설정)도 kis_template."""
    c = _reload(monkeypatch, KIS_DATA_SOURCE="new")
    assert c.resolve_daily_source_db() == "kis_template"
    assert c.resolve_minute_source_db() == "kis_template"
