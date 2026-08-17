import pytest
from scripts.feature_edge.timing import intraday_loader as L


def test_functions_exist():
    assert hasattr(L, "load_intraday_by_date")
    assert hasattr(L, "load_intraday_supplier")
    assert hasattr(L, "covered_stock_dates")


@pytest.mark.integration
def test_load_intraday_real(monkeypatch):
    """실 DB 조회 — **라이브 env 없이** 돌아야 한다.

    🔴 2026-08-17: 이 로더는 `dbname="robotrader"` 하드코딩이었다. 그 DB 는
      2026-07-10 동결 레거시이고 삭제 예정이라 resolver 경유로 바꿨다.
    🔑 `TIMESCALE_DB` 를 **일부러 지운 채** 돌린다 — 연구 읽기 경로가 라이브
      운영 env(gitignore 된 `.env` 전용)를 요구하면 clean checkout·워크트리·CI 에서
      죽는다. 그게 2026-07-16 통일이 고친 문제다.
    """
    monkeypatch.delenv("TIMESCALE_DB", raising=False)
    m = L.load_intraday_by_date("005930", "2026-06-12")
    assert m is None or "close" in m.columns


def test_conn_uses_minute_resolver_without_live_env(monkeypatch):
    """[음성 대조] 대상 DB 는 **분봉 resolver** 에서 온다 — env 없이도.

    resolver 를 sentinel 로 갈아끼워 「정말 그 값을 쓰는가」를 본다(연결은 안 한다).
    옛 계약 두 가지가 모두 회귀로 잡힌다:
      · 하드코딩 'robotrader'  → sentinel 이 아니므로 실패
      · TIMESCALE_DB 명시 필수 → env 를 지웠으므로 SystemExit 로 실패
    """
    monkeypatch.delenv("TIMESCALE_DB", raising=False)
    monkeypatch.setattr(L, "resolve_minute_source_db", lambda: "sentinel_minute")

    captured = []

    class _Boom(Exception):
        pass

    def _spy(**kwargs):
        captured.append(kwargs.get("dbname"))
        raise _Boom("연결까지 갈 필요 없음 — DB명만 확인")

    monkeypatch.setattr(L.psycopg2, "connect", _spy)
    with pytest.raises(_Boom):
        L.load_intraday_by_date("005930", "2026-06-12")

    assert captured == ["sentinel_minute"], (
        f"분봉 resolver 가 아니라 '{captured}' 로 붙었다"
    )
