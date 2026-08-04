"""시장 매핑 캐시의 수명 규약 — 급락게이트 `auto` 활성화 선행조건 ①②.

`resolve_regime_index`(판정 규칙)는 `test_market_classifier.py`가,
호출부 배선은 `test_crash_gate_market_scope.py`가 검증한다. 이 파일은 그
아래층인 **캐시 상태기계**만 본다.

닫으려는 결함 2건:

① 빈 매핑 영구 메모이즈 — `_cache = mapping` 이 `{}` 도 확정 캐시로 굳혀,
   테이블이 나중에 채워져도 그 프로세스는 영영 다시 읽지 않았다. 전부
   "both" 폴백이라 위험하진 않지만, **「auto 가 정상 동작 중」과 「auto 가
   켜졌는데 매핑이 비어 사실상 아무것도 안 하는 중」이 구분되지 않았다.**
② 조회 실패에 음성 캐시 없음 — 예외 시 `_cache` 가 None 그대로라 **매수
   평가마다** DB 재접속을 시도했다(2026-08-03 기준 평가 2,909회).

⚠️ 이 파일의 어떤 테스트도 실제 DB·네트워크에 닿지 않는다. `KisDbConnection.
   get_connection` 을 접속 횟수를 세는 스텁으로 갈아끼우고, 각 테스트가 그
   **횟수를 직접 단언**한다(2026-08-03 미스텁 사고: 스텁 누락이 라이브 DB 에
   쓰면서도 `_safe()` 가 예외를 삼켜 계속 green 이었다 — 「로그에 안 보임」은
   증거가 아니다).
"""
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

import core.regime.market_classifier as mc
from db.kis_db_connection import KisDbConnection


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.sql = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)

    def commit(self):
        pass


class FakeDb:
    """DB 접속 스텁 — psycopg2 를 절대 부르지 않고 접속 횟수를 센다."""

    def __init__(self, rows=(), raises=None):
        self.rows = list(rows)
        self.raises = raises
        self.connects = 0

    @contextmanager
    def get_connection(self):
        self.connects += 1
        if self.raises is not None:
            raise self.raises
        yield _FakeConn(self.rows)


@pytest.fixture(autouse=True)
def _isolate_cache():
    """캐시는 모듈 전역이다 — 테스트 간 누수를 앞뒤로 차단한다."""
    mc.reset_cache()
    yield
    mc.reset_cache()


@pytest.fixture
def clock(monkeypatch):
    """단조시계 주입. 실제 sleep 없이 TTL 만료를 재현한다."""
    now = [1000.0]
    monkeypatch.setattr(mc, "_now", lambda: now[0], raising=False)
    return now


@pytest.fixture
def rec_logger(monkeypatch):
    """logger 를 Mock 으로 교체 — 로깅 설정에 의존하지 않고 호출을 단언한다."""
    logger = Mock()
    monkeypatch.setattr(mc, "logger", logger)
    return logger


def _install(monkeypatch, fake):
    monkeypatch.setattr(KisDbConnection, "get_connection", fake.get_connection)
    return fake


# =========================================================================
# ① 빈 매핑이 영구 메모이즈되면 안 된다
# =========================================================================

def test_empty_mapping_is_retried_after_ttl(monkeypatch, clock):
    """테이블이 비었다가 채워지면 TTL 만료 후 프로세스가 스스로 회복해야 한다.

    (구현 전) `_cache = {}` 가 확정 캐시로 굳어 재조회가 영영 없었다.
    """
    fake = _install(monkeypatch, FakeDb(rows=[]))
    monkeypatch.setattr(mc, "_NEGATIVE_TTL_SEC", 300, raising=False)

    assert mc.get_stock_market("005930") is None
    assert fake.connects == 1

    # 테이블이 채워졌다(EOD 수집 성공 등). TTL 만료 전에는 재조회하지 않는다.
    fake.rows = [("005930", "KOSPI")]
    clock[0] += 299
    assert mc.get_stock_market("005930") is None
    assert fake.connects == 1, "TTL 안에서는 재접속하면 안 된다"

    # TTL 만료 후 1회 재시도 → 회복
    clock[0] += 2
    assert mc.get_stock_market("005930") == "KOSPI"
    assert fake.connects == 2


def test_empty_mapping_does_not_reconnect_on_every_lookup(monkeypatch, clock):
    """빈 매핑 상태에서 평가가 2,909회 돌아도 접속은 TTL 당 1회여야 한다."""
    fake = _install(monkeypatch, FakeDb(rows=[]))
    monkeypatch.setattr(mc, "_NEGATIVE_TTL_SEC", 300, raising=False)

    for _ in range(50):
        assert mc.get_stock_market("005930") is None
    assert fake.connects == 1


def test_empty_mapping_warns_once_per_ttl_window(monkeypatch, clock, rec_logger):
    """판별 가능한 신호 — WARNING 이상이고, TTL 단위로 계속 남아야 한다.

    「auto 인데 매핑 0종목」은 설정과 데이터가 어긋난 상태이지 정상 폴백이
    아니다. 다만 평가마다 찍으면 2,909줄이 되므로 TTL 단위 1회로 억제한다.
    """
    fake = _install(monkeypatch, FakeDb(rows=[]))
    monkeypatch.setattr(mc, "_NEGATIVE_TTL_SEC", 300, raising=False)

    for _ in range(30):
        mc.get_stock_market("005930")
    assert rec_logger.warning.call_count == 1, "평가마다 찍으면 로그 폭주다"

    clock[0] += 301
    for _ in range(30):
        mc.get_stock_market("005930")
    assert rec_logger.warning.call_count == 2, "상태가 지속되면 TTL 단위로 계속 남아야 한다"
    assert fake.connects == 2

    # 사람이 원인을 알아볼 수 있어야 한다 — 빈 매핑임이 문구에 드러날 것.
    msg = " ".join(str(c.args[0]) for c in rec_logger.warning.call_args_list)
    assert "0종목" in msg or "비어" in msg


# =========================================================================
# ② 조회 실패에 음성 캐시
# =========================================================================

def test_lookup_failure_is_negatively_cached(monkeypatch, clock, rec_logger):
    """DB 장애 시 매수 평가마다 동기 재접속하면 안 된다.

    (구현 전) 예외 경로가 `_cache` 를 None 그대로 두어 매 호출이 재접속했다.
    """
    fake = _install(monkeypatch, FakeDb(raises=RuntimeError("db down")))
    monkeypatch.setattr(mc, "_NEGATIVE_TTL_SEC", 300, raising=False)

    for _ in range(50):
        assert mc.get_stock_market("005930") is None
    assert fake.connects == 1, "실패도 TTL 동안 기억해야 한다"
    assert rec_logger.warning.call_count == 1


def test_lookup_failure_recovers_after_ttl(monkeypatch, clock):
    """장애가 걷히면 TTL 만료 후 스스로 회복해야 한다(영구 실패 금지)."""
    fake = _install(monkeypatch, FakeDb(raises=RuntimeError("db down")))
    monkeypatch.setattr(mc, "_NEGATIVE_TTL_SEC", 300, raising=False)

    assert mc.get_stock_market("005930") is None
    assert fake.connects == 1

    fake.raises = None
    fake.rows = [("005930", "KOSPI")]
    clock[0] += 301
    assert mc.get_stock_market("005930") == "KOSPI"
    assert fake.connects == 2


# =========================================================================
# 성공 캐시의 수명은 바뀌지 않는다
# =========================================================================

def test_nonempty_mapping_is_cached_indefinitely(monkeypatch, clock):
    """정상 매핑은 현행 수명 유지 — TTL 과 무관하게 EOD `reset_cache()` 까지 산다."""
    fake = _install(monkeypatch, FakeDb(rows=[("005930", "KOSPI"), ("035720", "KOSDAQ")]))
    monkeypatch.setattr(mc, "_NEGATIVE_TTL_SEC", 300, raising=False)

    assert mc.get_stock_market("005930") == "KOSPI"
    clock[0] += 86400  # 하루
    assert mc.get_stock_market("035720") == "KOSDAQ"
    assert fake.connects == 1, "정상 매핑에 TTL 을 걸면 안 된다"


def test_mapping_codes_are_stringified(monkeypatch, clock):
    """DB 가 int/Decimal 을 줘도 종목코드 키는 문자열이어야 한다(기존 규약)."""
    _install(monkeypatch, FakeDb(rows=[(5930, "KOSPI")]))
    assert mc.get_stock_market(5930) == "KOSPI"
    assert mc.get_stock_market("5930") == "KOSPI"


# =========================================================================
# reset_cache() 는 음성 캐시도 함께 지워야 한다
# =========================================================================

def test_reset_cache_clears_negative_cache(monkeypatch, clock):
    """EOD 수집 성공 직후의 `reset_cache()` 가 음성 캐시에 막히면 안 된다.

    음성 캐시를 남겨두면 수집이 성공했는데도 TTL 이 끝날 때까지 빈 매핑을
    계속 반환한다 — 「고쳤는데 안 고쳐진」 상태가 조용히 생긴다.
    """
    fake = _install(monkeypatch, FakeDb(rows=[]))
    monkeypatch.setattr(mc, "_NEGATIVE_TTL_SEC", 300, raising=False)

    assert mc.get_stock_market("005930") is None
    assert fake.connects == 1

    fake.rows = [("005930", "KOSPI")]
    mc.reset_cache()  # EOD 수집 성공 → 캐시 무효화
    assert mc.get_stock_market("005930") == "KOSPI"
    assert fake.connects == 2


# =========================================================================
# 불변식: 결측은 언제나 "both"(보호 과잉) 쪽으로만 실패한다
# =========================================================================

@pytest.mark.parametrize("fake_kwargs", [
    {"rows": []},                              # 빈 테이블
    {"raises": RuntimeError("db down")},       # 조회 예외
])
def test_auto_still_falls_back_to_both(monkeypatch, clock, fake_kwargs):
    """음성 캐시를 도입해도 무방비 구간이 생기면 안 된다."""
    _install(monkeypatch, FakeDb(**fake_kwargs))
    monkeypatch.setattr(mc, "_NEGATIVE_TTL_SEC", 300, raising=False)

    for _ in range(3):
        assert mc.resolve_regime_index("auto", "005930") == "both"


def test_non_auto_never_touches_db_even_when_mapping_is_broken(monkeypatch, clock):
    """비활성(non-auto) 8전략은 캐시 변경의 영향을 받지 않는다 — 접속 0회."""
    fake = _install(monkeypatch, FakeDb(raises=RuntimeError("db down")))
    for cfg in ("KOSPI", "KOSDAQ", "both", "none"):
        assert mc.resolve_regime_index(cfg, "005930") == cfg
    assert fake.connects == 0


# =========================================================================
# ①-4 기동 시 1회 프리로드
# =========================================================================

def test_preload_skips_db_when_no_auto_strategy(monkeypatch, clock, rec_logger):
    """활성화 전에는 무해해야 한다 — DB 접속도, 캐시 상태 변경도 없다."""
    fake = _install(monkeypatch, FakeDb(rows=[("005930", "KOSPI")]))

    assert mc.preload_market_mapping(auto_active=False) == 0
    assert fake.connects == 0
    assert rec_logger.warning.call_count == 0


def test_preload_loads_mapping_when_auto_active(monkeypatch, clock, rec_logger):
    fake = _install(monkeypatch, FakeDb(rows=[("005930", "KOSPI"), ("035720", "KOSDAQ")]))

    assert mc.preload_market_mapping(auto_active=True) == 2
    assert fake.connects == 1
    assert rec_logger.warning.call_count == 0
    # 프리로드가 캐시를 데워 첫 매수 평가가 DB 를 기다리지 않는다.
    assert mc.get_stock_market("005930") == "KOSPI"
    assert fake.connects == 1


def test_preload_warns_when_auto_active_but_mapping_empty(monkeypatch, clock, rec_logger):
    """설정과 데이터가 어긋난 상태 — 기동 로그에서 바로 보여야 한다.

    ⚠️ `call_count >= 1` + `"auto" in msg` 로는 판별력이 없다(2026-08-04 실측):
       `_remember_failure` 의 1차 WARNING 에도 `regime_index="auto"` 가 들어 있어
       **프리로드 고유의 2차 WARNING 을 통째로 지워도 통과**했다. 두 WARNING 은
       서로 다른 사실을 말한다 — ① 조회가 비었다 ② 그런데 auto 가 켜져 있다.
       그래서 2차 고유 문구를 직접 매칭한다.
    """
    fake = _install(monkeypatch, FakeDb(rows=[]))

    assert mc.preload_market_mapping(auto_active=True) == 0
    assert fake.connects == 1

    msgs = [str(c.args[0]) for c in rec_logger.warning.call_args_list]
    # ① 캐시층: 조회 결과가 비었다는 사실
    assert any("0종목" in m or "비어" in m for m in msgs), f"1차 WARNING 없음: {msgs}"
    # ② 프리로드층: 설정(auto)과 데이터가 어긋났다는 **별개** 사실 + 조치 안내
    assert any(
        "전략이 있는데" in m and "collectors.stock_market_collector" in m
        for m in msgs
    ), f"프리로드 고유의 2차 WARNING 이 없다: {msgs}"
    assert len(msgs) >= 2, f"두 사실이 각각 남아야 한다: {msgs}"


def test_preload_does_not_raise_when_db_is_down(monkeypatch, clock, rec_logger):
    """프리로드 실패가 봇 기동을 막으면 안 된다."""
    _install(monkeypatch, FakeDb(raises=RuntimeError("db down")))
    assert mc.preload_market_mapping(auto_active=True) == 0
