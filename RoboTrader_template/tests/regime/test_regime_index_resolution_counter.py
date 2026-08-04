"""급락게이트 지수 해석 카운터 — `auto` 활성화의 **양성 증거** 계층.

닫으려는 결함은 코드가 아니라 **증거의 부재**다. 지금 auto 를 켜면
"잘 돌아간다"의 근거가 「WARNING 이 안 뜬다」뿐인데, 이 프로젝트가 반복해서
데인 규칙이 정확히 그것이다 — **경보가 조용함은 증거가 아니다.**
2026-08-03 EOD 때 "KOSPI 종목을 무보호로 매수했는가"를 판정할 수 없었던 것도
같은 이유였다(그때는 시장 라벨 자체가 없었고, 지금은 있는데 세지 않는다).

이 파일이 단언하는 것:
  ① 해석 결과가 (전략, configured, resolved) 별로 **세어진다**
  ② 집계 실패가 **매수 판단을 절대 죽이지 않는다**(핫패스 2,909회)
  ③ 호출당 로깅이 없다(2,909줄 폭주 금지)
  ④ 요약이 **활성화 전(전부 non-auto)에도** 유의미한 줄을 낸다
  ⑤ non-auto 인데 configured≠resolved 면 **그 자체가 결함**으로 드러난다
  ⑥ 출력 후 리셋되고, 집계 창(window)이 줄에 드러난다

⚠️ DB·네트워크 미접촉: 모든 해석은 `market_lookup` 스텁으로 호출하거나
   `KisDbConnection.get_connection` 을 접속 횟수를 세는 스텁으로 갈아끼운다
   (2026-08-03 미스텁 사고: 스텁 누락이 라이브 DB 에 쓰면서도 예외가 삼켜져
   계속 green 이었다).
"""
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

import core.regime.market_classifier as mc
from db.kis_db_connection import KisDbConnection

MARKET_OF = {"005930": "KOSPI", "035720": "KOSDAQ"}


class _NoDb:
    """접속 시도 자체를 세는 스텁 — 0회를 직접 단언하기 위한 것."""

    def __init__(self):
        self.connects = 0

    @contextmanager
    def get_connection(self):
        self.connects += 1
        raise AssertionError("테스트가 실제 DB 에 접속하려 했다")
        yield  # pragma: no cover


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """캐시·카운터 모두 모듈 전역이다 — 앞뒤로 누수를 차단하고 DB 를 막는다."""
    fake = _NoDb()
    monkeypatch.setattr(KisDbConnection, "get_connection", fake.get_connection)
    mc.reset_cache()
    mc.reset_resolution_counts()
    yield fake
    mc.reset_cache()
    mc.reset_resolution_counts()


@pytest.fixture
def wall(monkeypatch):
    """벽시계 주입 — 집계 창 표기를 결정론적으로 만든다."""
    stamps = ["2026-08-04 09:00:11", "2026-08-04 15:36:02"]

    def _next():
        return stamps[0] if len(stamps) == 1 else stamps.pop(0)

    monkeypatch.setattr(mc, "_wall_now", _next, raising=False)
    return stamps


def _headline(levels_and_lines):
    return levels_and_lines[0][1]


def _joined(levels_and_lines):
    return " | ".join(m for _, m in levels_and_lines)


def _window(head):
    """헤드라인의 `집계창 시작~끝` 을 (시작, 끝) 로 **분해**한다.

    🔴 `assert "15:36:02" in head` 로 창 시작을 단언하면 안 된다 — 같은 문자열이
       **창 끝**에도 찍히므로, 리셋이 창을 안 비우거나 창 시작이 매 호출 갱신돼도
       통과한다(거짓 음성). 창 시작·끝을 분리해 각각 **정확히** 단언한다.

    시각 표기에 공백이 있어("2026-08-04 09:00:11") 공백 split 은 못 쓴다.
    """
    span = head.split("집계창 ")[1]
    start, rest = span.split("~", 1)
    return start, rest.split(" (")[0]


# =========================================================================
# ① 해석 결과가 세어진다
# =========================================================================

def test_non_auto_resolution_is_counted(_isolate):
    """활성화 전(non-auto)에도 세어야 한다 — 이 건수가 「카운터가 산다」는 증거다."""
    for _ in range(3):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")

    assert mc.get_resolution_counts() == {("elder", "KOSPI", "KOSPI"): 3}
    assert _isolate.connects == 0, "non-auto 는 DB 를 건드리면 안 된다"


def test_auto_splits_by_market_in_counts():
    """핵심 질문 — auto 가 실제로 시장별로 갈리는가."""
    for _ in range(5):
        mc.resolve_regime_index("auto", "005930", market_lookup=MARKET_OF.get,
                                strategy_name="s1")
    for _ in range(2):
        mc.resolve_regime_index("auto", "035720", market_lookup=MARKET_OF.get,
                                strategy_name="s1")
    mc.resolve_regime_index("auto", "999999", market_lookup=MARKET_OF.get,
                            strategy_name="s1")

    assert mc.get_resolution_counts() == {
        ("s1", "auto", "KOSPI"): 5,
        ("s1", "auto", "KOSDAQ"): 2,
        ("s1", "auto", "both"): 1,
    }


def test_strategy_name_is_optional_and_falls_back_to_placeholder():
    """전략명을 못 넘기는 호출부가 있어도 (configured, resolved) 축은 살아야 한다."""
    mc.resolve_regime_index("KOSDAQ", "035720")
    counts = mc.get_resolution_counts()
    assert list(counts.values()) == [1]
    (strat, cfg, res), = counts.keys()
    assert (cfg, res) == ("KOSDAQ", "KOSDAQ")
    assert strat, "빈 문자열이 키로 들어가면 요약이 읽히지 않는다"


def test_missing_configured_is_recorded_as_the_value_actually_used():
    """None/"" → "both" 규약. 원문 그대로 기록하면 configured≠resolved 오탐이 난다."""
    mc.resolve_regime_index(None, "005930", strategy_name="s1")
    mc.resolve_regime_index("", "005930", strategy_name="s1")
    assert mc.get_resolution_counts() == {("s1", "both", "both"): 2}


def test_lookup_exception_is_counted_as_both():
    """결측 3경로는 전부 both(보호 과잉)로 흡수된다 — 집계도 그 사실을 남긴다."""
    def boom(_code):
        raise RuntimeError("mapping down")

    assert mc.resolve_regime_index("auto", "005930", market_lookup=boom,
                                   strategy_name="s1") == "both"
    assert mc.get_resolution_counts() == {("s1", "auto", "both"): 1}


# =========================================================================
# ② 집계 실패가 매수 판단을 죽이면 안 된다 (핫패스 불변식)
# =========================================================================

class _BoomDict(dict):
    def __setitem__(self, k, v):
        raise RuntimeError("counter exploded")


@pytest.mark.parametrize("configured,code,expected", [
    ("KOSPI", "005930", "KOSPI"),
    ("none", "005930", "none"),
    ("auto", "005930", "KOSPI"),
    ("auto", "035720", "KOSDAQ"),
    ("auto", "999999", "both"),
])
def test_counter_failure_never_changes_return_value(monkeypatch, configured, code, expected):
    """집계가 터져도 원 반환값이 그대로 나와야 한다 — 매수 경로가 죽으면 안 된다."""
    monkeypatch.setattr(mc, "_resolution_counts", _BoomDict(), raising=False)
    assert mc.resolve_regime_index(configured, code,
                                   market_lookup=MARKET_OF.get) == expected


def test_counter_failure_in_clock_does_not_propagate(monkeypatch):
    """집계 창 시각 계산이 터져도 마찬가지 — **그리고 집계 자체는 살아야 한다.**

    🔴 반환값만 단언하면 구멍이 green 으로 덮인다. 창 도장이 증가보다 **먼저**면
       시계 예외가 바깥 except 로 튀어 `_resolution_counts` 증가에 도달하지
       못하고, 그날 **모든 호출이 통째로 미집계**된다. 반환값은 정상이라
       아무도 모르고, EOD 는 `총 0건` = 「auto 가 안 돈다」로 읽히는
       **거짓 음성**이 된다 — 이 기능이 없애려던 바로 그 오독이다.
    """
    def boom():
        raise RuntimeError("clock exploded")

    monkeypatch.setattr(mc, "_wall_now", boom, raising=False)
    for _ in range(7):
        assert mc.resolve_regime_index("KOSPI", "005930") == "KOSPI"

    counts = mc.get_resolution_counts()
    assert sum(counts.values()) == 7, f"시계가 터졌다고 집계가 죽었다: {counts}"


def test_unhashable_strategy_name_is_still_counted():
    """키가 unhashable 이어도 총 건수는 잃으면 안 된다.

    잃으면 「집계가 멈춘 것」과 구분되지 않는다. (실제 발생 가능성은 낮다 —
    `_strategy_key` 는 항상 str 이다. 그래도 조용한 0건은 만들지 않는다.)
    """
    for _ in range(3):
        assert mc.resolve_regime_index("KOSPI", "005930",
                                       strategy_name=["unhashable"]) == "KOSPI"

    counts = mc.get_resolution_counts()
    assert sum(counts.values()) == 3, f"unhashable 이 집계를 삼켰다: {counts}"


# =========================================================================
# ③ 호출당 로깅 금지 (2,909줄 폭주)
# =========================================================================

def test_counting_does_not_log_per_call(monkeypatch):
    rec = Mock()
    monkeypatch.setattr(mc, "logger", rec)
    for _ in range(300):
        mc.resolve_regime_index("auto", "005930", market_lookup=MARKET_OF.get,
                                strategy_name="s1")
    assert rec.info.call_count == 0
    assert rec.warning.call_count == 0
    assert mc.get_resolution_counts()[("s1", "auto", "KOSPI")] == 300


def test_key_cardinality_is_bounded(monkeypatch):
    """키가 무한 증식하면 안 된다.

    이 모듈은 이미 「종목코드를 키로 넣어 캐시를 오염시킨」 사고의 현장이다.
    전략명 자리에 종목코드가 들어오는 실수를 메모리 누수로 키우지 않는다.
    """
    monkeypatch.setattr(mc, "_MAX_RESOLUTION_KEYS", 10, raising=False)
    for i in range(500):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name=f"s{i}")
    counts = mc.get_resolution_counts()
    assert len(counts) <= 11, f"키가 {len(counts)}개까지 늘었다"
    assert sum(counts.values()) == 500, "상한에 걸려도 총 건수는 잃으면 안 된다"


def test_overflow_bucket_preserves_the_auto_axis(wall, monkeypatch):
    """🔴 넘침 버킷이 **전략 축만** 뭉개야 한다 — configured 를 함께 뭉개면
    요약부의 `if cfg == "auto"` 분기를 절대 안 타서 **auto 해석이 non-auto 로
    계상**된다. 총 건수는 보존되므로 「집계가 산다」는 통과하는데 헤드라인만
    `auto 0건` 이라고 거짓말한다 — 이 기능이 없애려던 바로 그 오독이다.

    (입력이 전부 non-auto 인 `test_key_cardinality_is_bounded` 는 이 축을
     구조적으로 못 본다. 그래서 auto 입력으로 상한을 넘긴다.)
    """
    monkeypatch.setattr(mc, "_MAX_RESOLUTION_KEYS", 5, raising=False)
    for i in range(100):
        mc.resolve_regime_index("auto", "005930", market_lookup=MARKET_OF.get,
                                strategy_name=f"s{i}")

    counts = mc.get_resolution_counts()
    assert sum(counts.values()) == 100, f"총 건수를 잃었다: {counts}"

    head = _headline(mc.format_resolution_summary())
    assert "총 100건" in head, head
    assert "auto 100건" in head, f"넘침 버킷이 auto 축을 파괴했다: {head}"
    assert "KOSPI 100" in head, f"시장 분해가 죽었다: {head}"
    assert "non-auto 0건" in head, f"auto 가 non-auto 로 계상됐다: {head}"


def test_overflow_bucket_is_itself_bounded(wall, monkeypatch):
    """넘침 버킷을 configured×resolved 로 쪼개도 그 축이 무한 증식하면 안 된다.

    실전에서 configured 는 설정값(전략 수만큼)이라 유계지만, 카디널리티 상한이
    **다른 인자가 얌전하다는 가정**에 의존하면 안 된다. 이 모듈은 이미
    「종목코드를 키로 넣어 캐시를 오염시킨」 사고의 현장이다.
    """
    monkeypatch.setattr(mc, "_MAX_RESOLUTION_KEYS", 5, raising=False)
    monkeypatch.setattr(mc, "_HARD_MAX_RESOLUTION_KEYS", 20, raising=False)
    for i in range(500):
        mc.resolve_regime_index(f"cfg{i}", "005930", strategy_name=f"s{i}")

    counts = mc.get_resolution_counts()
    assert len(counts) <= 21, f"넘침 버킷이 무한 증식했다: {len(counts)}개"
    assert sum(counts.values()) == 500, "총 건수는 잃으면 안 된다"


# =========================================================================
# ④ 활성화 전에도 유의미한 줄이 나와야 한다
# =========================================================================

def test_summary_is_meaningful_when_everything_is_non_auto(wall):
    """지금(8전략 전부 non-auto) 찍히는 줄 — 「카운터가 동작한다」의 증거다.

    "auto 가 없으니 아무것도 안 찍는다"로 만들면 활성화 첫날에 카운터의 첫
    노출이 겹친다(그날 처음 보는 줄은 검증된 줄이 아니다).
    """
    for _ in range(7):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    for _ in range(3):
        mc.resolve_regime_index("KOSDAQ", "035720", strategy_name="daytrading")

    head = _headline(mc.format_resolution_summary())
    # 🔴 `"10" in head` 는 거짓 음성이었다 — `non-auto 10건` 의 부분문자열로
    #    만족되므로, 총 건수가 auto 만 세도록 망가져도 통과했다. 라벨을 포함해
    #    단언한다.
    assert "총 10건" in head, f"총 건수가 없다: {head}"
    assert "auto 0건" in head, f"auto 0건이 명시돼야 한다: {head}"
    assert "non-auto 10건" in head, head


def test_summary_is_emitted_even_with_zero_resolutions(wall):
    """건수 0도 신호다(무거래 또는 배선 단절) — 침묵으로 만들면 안 된다."""
    lines = mc.format_resolution_summary()
    assert lines, "0건이라고 아무 줄도 안 내면 배선 단절과 구분되지 않는다"
    assert mc.RESOLUTION_LOG_TAG in _headline(lines)


def test_headline_carries_grep_tag_on_every_line(wall):
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    for _, msg in mc.format_resolution_summary():
        assert mc.RESOLUTION_LOG_TAG in msg


# =========================================================================
# ⑤ 무엇을 「양성 증거」로 볼 것인가 — 요약이 판정 가능해야 한다
# =========================================================================

def test_summary_breaks_auto_down_by_market_with_both_ratio(wall):
    for _ in range(6):
        mc.resolve_regime_index("auto", "005930", market_lookup=MARKET_OF.get,
                                strategy_name="s1")
    for _ in range(2):
        mc.resolve_regime_index("auto", "035720", market_lookup=MARKET_OF.get,
                                strategy_name="s1")
    for _ in range(2):
        mc.resolve_regime_index("auto", "999999", market_lookup=MARKET_OF.get,
                                strategy_name="s1")

    head = _headline(mc.format_resolution_summary())
    assert "KOSPI 6" in head and "KOSDAQ 2" in head and "both 2" in head, head
    # both 비율 = 매핑이 안 붙는 비율. 높으면 auto 가 사실상 안 도는 상태다.
    assert "20.0%" in head, f"both 비율이 없다: {head}"


def test_both_ratio_is_not_faked_when_there_is_no_auto(wall):
    """auto 0건에 both 0.0% 를 찍으면 「매핑 완벽」으로 오독된다."""
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    head = _headline(mc.format_resolution_summary())
    assert "0.0%" not in head, f"auto 가 0건인데 비율을 찍었다: {head}"


def test_non_auto_mismatch_is_reported_as_a_defect(wall, monkeypatch):
    """non-auto 는 configured==resolved 여야 한다 — 아니면 해석 규칙 결함이다."""
    monkeypatch.setattr(mc, "_resolution_counts", {
        ("elder", "KOSPI", "KOSPI"): 100,
        ("elder", "KOSPI", "both"): 3,   # 있을 수 없는 조합
    }, raising=False)

    lines = mc.format_resolution_summary()
    warns = [m for lvl, m in lines if lvl == "warning"]
    assert warns, f"불일치가 WARNING 으로 안 나왔다: {lines}"
    assert "3" in warns[0] and "KOSPI" in warns[0]
    assert "3" in _headline(lines), "헤드라인에도 불일치 건수가 보여야 한다"


def test_clean_non_auto_produces_no_warning(wall):
    """정상 상태에 WARNING 을 내면 경보가 무뎌진다."""
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    assert [m for lvl, m in mc.format_resolution_summary() if lvl == "warning"] == []


def test_summary_breaks_down_by_strategy(wall):
    """어느 전략이 무엇으로 갈렸는지 — 귀속이 안 되면 조치를 못 한다."""
    for _ in range(4):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    mc.resolve_regime_index("KOSDAQ", "035720", strategy_name="daytrading")

    joined = _joined(mc.format_resolution_summary())
    assert "elder" in joined and "daytrading" in joined
    assert "4" in joined


# =========================================================================
# ⑥ 집계 창(window) + 출력 후 리셋
# =========================================================================

def test_headline_shows_window_and_restart_caveat(wall):
    """장중 재기동 시 초기화된다는 한계가 줄에 드러나야 한다.

    조용히 과소집계되면 「auto 가 안 돌았다」와 구분되지 않는다.

    🔴 창 시작은 **첫 해석 시각에 고정**돼야 한다. 매 호출 갱신되면 창이
       실제보다 짧게 보여, 이월된 건수가 「방금 센 것」처럼 읽힌다. 시계가
       두 번째 호출부터 진행하도록 2회 해석한 뒤 시작·끝을 분해해 단언한다.
    """
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")

    head = _headline(mc.format_resolution_summary())
    start, end = _window(head)
    assert start == "2026-08-04 09:00:11", f"창 시작이 첫 해석 시각이 아니다: {head}"
    assert end == "2026-08-04 15:36:02", f"창 끝이 출력 시각이 아니다: {head}"
    assert "재기동" in head, f"재기동 시 초기화 한계가 안 적혔다: {head}"


def test_log_resolution_summary_emits_then_resets(wall):
    log = Mock()
    for _ in range(5):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")

    snapshot = mc.log_resolution_summary(log)
    assert snapshot == {("elder", "KOSPI", "KOSPI"): 5}
    assert log.info.call_count >= 1
    assert mc.RESOLUTION_LOG_TAG in str(log.info.call_args_list[0].args[0])

    # 출력 후 리셋 — 다음 거래일이 전날 건수를 물려받으면 안 된다.
    assert mc.get_resolution_counts() == {}
    log2 = Mock()
    mc.log_resolution_summary(log2)
    head2 = str(log2.info.call_args_list[0].args[0])
    assert "총 0건" in head2, f"리셋이 안 됐다: {head2}"


def test_window_restarts_after_emit(wall):
    """리셋 후 첫 해석이 새 창을 연다 — 창이 옛 시각에 고정되면 오독된다.

    🔴 `assert "15:36:02" in head` 는 **거짓 음성**이었다: 같은 문자열이 창 끝에도
       찍히므로, 리셋이 창을 안 비워 시작이 `09:00:11` 에 눌러앉아도 통과했다.
       창 시작을 분해해 정확히 단언한다.
    """
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    mc.log_resolution_summary(Mock())
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")

    start, _end = _window(_headline(mc.format_resolution_summary()))
    assert start == "2026-08-04 15:36:02", f"새 창이 안 열렸다(창 시작={start})"


def test_log_resolution_summary_never_raises(monkeypatch):
    """EOD 출력 실패가 EOD 흐름을 죽이면 안 된다."""
    monkeypatch.setattr(mc, "format_resolution_summary",
                        Mock(side_effect=RuntimeError("boom")), raising=False)
    log = Mock()
    mc.log_resolution_summary(log)  # 예외가 새면 안 된다


def test_log_resolution_summary_resets_even_when_formatting_fails(monkeypatch):
    """출력이 실패해도 리셋은 돼야 한다 — 안 그러면 다음날로 계속 이월된다."""
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    monkeypatch.setattr(mc, "format_resolution_summary",
                        Mock(side_effect=RuntimeError("boom")), raising=False)
    mc.log_resolution_summary(Mock())
    assert mc.get_resolution_counts() == {}


# =========================================================================
# 매핑 캐시 리셋이 집계를 지우면 안 된다 (EOD 수집이 캐시를 리셋한다)
# =========================================================================

def test_reset_cache_does_not_wipe_counts():
    """`eod_collection` 이 수집 성공 후 `reset_cache()` 를 부른다.

    그때 카운터까지 지워지면 그날의 증거가 출력 전에 증발한다.
    """
    for _ in range(3):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    mc.reset_cache()
    assert mc.get_resolution_counts() == {("elder", "KOSPI", "KOSPI"): 3}


def test_get_resolution_counts_returns_a_copy():
    """호출측이 내부 dict 를 변이시키면 핫패스 상태가 오염된다."""
    mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    snap = mc.get_resolution_counts()
    snap[("x", "y", "z")] = 999
    assert ("x", "y", "z") not in mc.get_resolution_counts()
