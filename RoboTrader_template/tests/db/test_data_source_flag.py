"""가격 소스 resolver 회귀 테스트.

이력:
  2026-07-16 — 연구 소스 통일로 기본값이 legacy → new(kis_template) 로 뒤집혔다.
    근거: 라이브는 .env(KIS_DATA_SOURCE=new)로 이미 kis_template 을 봤지만, .env 가
    없는 연구 프로세스(clean checkout·워크트리·CI)는 코드 기본값으로 떨어져
    2026-07-10 동결된 레거시 DB 를 읽고 있었다.

  🔴 2026-08-17 — **롤백 스위치 자체가 폐지**되면서 이 파일의 계약이 뒤집혔다.
    옛 계약: 「KIS_DATA_SOURCE=legacy → robotrader(_quant) 로 되돌아간다」
    새 계약: 「넣어도 무시된다 — resolver 는 항상 kis_template」
    이유 ① 레거시 두 소스는 2026-07-10 동결이라 되돌려도 죽은 데이터였고,
         ② `robotrader` DB 는 통합 후 삭제된다 ⇒ 남은 스위치는 「누르면 죽는 버튼」.
    옛 사실을 단언하는 테스트를 그대로 두면 폐기 작업이 「회귀」로 오탐되므로,
    테스트를 지우지 않고 **계약을 뒤집었다**. 상세는 tests/test_research_data_source.py.
"""
import importlib


def _reload(monkeypatch, **env):
    for k in ("KIS_DATA_SOURCE", "QUANT_DB", "MINUTE_DB", "CORP_EVENTS_DB"):
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


def test_resolve_daily_ignores_retired_legacy_switch(monkeypatch):
    """[계약 반전] KIS_DATA_SOURCE=legacy 를 넣어도 일봉은 kis_template.

    (이전: robotrader_quant 를 단언했다.)
    """
    c = _reload(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_daily_source_db() == "kis_template"


def test_resolve_minute_ignores_retired_legacy_switch(monkeypatch):
    """[계약 반전] KIS_DATA_SOURCE=legacy 를 넣어도 분봉은 kis_template.

    (이전: robotrader 를 단언했다.)
    """
    c = _reload(monkeypatch, KIS_DATA_SOURCE="legacy")
    assert c.resolve_minute_source_db() == "kis_template"


def test_kis_data_source_module_constant_is_gone(monkeypatch):
    """[계약 반전] 모듈 상수 KIS_DATA_SOURCE 는 **없어졌다**.

    이전엔 collectors/eod_collection.py 의 교차비교 게이트가 이 값을 읽었다.
    그 게이트와 reconcile_* 대조 함수들은 레거시 DB 폐기와 함께 제거됐으므로,
    상수가 남아 있으면 「죽은 스위치를 다시 읽는 코드」가 생길 자리를 남기는 셈이다.
    """
    c = _reload(monkeypatch)
    assert not hasattr(c, "KIS_DATA_SOURCE"), "폐지된 롤백 플래그 상수가 되살아났다"
    assert not hasattr(c, "_is_legacy_source"), "폐지된 롤백 판정 함수가 되살아났다"


def test_explicit_new_still_points_to_kis_template(monkeypatch):
    """명시적 new(라이브 .env 와 동일 설정)도 kis_template — 런타임 동작 불변 증거."""
    c = _reload(monkeypatch, KIS_DATA_SOURCE="new")
    assert c.resolve_daily_source_db() == "kis_template"
    assert c.resolve_minute_source_db() == "kis_template"
    assert c.resolve_corp_events_source_db() == "kis_template"


# ===========================================================================
# 수동 스크립트 대상 DB — 기본값을 「바꾸지」 않고 「없앴다」
# ===========================================================================

def test_require_explicit_target_db_returns_env_value(monkeypatch):
    import pytest  # noqa: F401  (아래 raises 와 대칭 유지용 import 위치)
    from config.constants import require_explicit_target_db
    monkeypatch.setenv("TIMESCALE_DB", "kis_template")
    assert require_explicit_target_db("테스트") == "kis_template"


def test_require_explicit_target_db_exits_when_unset(monkeypatch):
    """미지정이면 **중단** — 조용히 다른 DB 로 가지 않는다.

    🔑 기본값을 라이브 SSOT(kis_template)로 「바꾸지」 않고 「없앤」 이유:
      옛 기본값 'robotrader' 로 잘못 돌리면 죽은 DB 에 써서 무해했다. 기본값을
      라이브 SSOT 로 바꾸면 같은 실수가 「라이브에 실수로 쓰기」가 되어
      폭발 반경이 **반대로 커진다**.
    """
    import pytest
    from config.constants import require_explicit_target_db
    monkeypatch.delenv("TIMESCALE_DB", raising=False)
    with pytest.raises(SystemExit) as ei:
        require_explicit_target_db("XYZ 백필 적재 대상")
    msg = str(ei.value)
    assert "TIMESCALE_DB" in msg, "무엇을 설정해야 하는지 알려줘야 한다"
    assert "XYZ 백필 적재 대상" in msg, "무슨 작업이었는지 알려줘야 한다"


def test_require_explicit_target_db_rejects_blank(monkeypatch):
    """공백 문자열도 「미지정」으로 본다(빈 env 로 인한 조용한 오작동 차단)."""
    import pytest
    from config.constants import require_explicit_target_db
    monkeypatch.setenv("TIMESCALE_DB", "   ")
    with pytest.raises(SystemExit):
        require_explicit_target_db("테스트")
