"""급락게이트(`check_market_direction`) 관측성 — 2026-08-07.

배경: 2026-08-07 EOD 에서 KOSDAQ 일중 저점이 -3.13%(임계 -3.0%)를 넘겼고
30분 대시보드가 10:41:01 에 -3.04% 를 실측했는데 차단은 0건이었다. 그런데
당시 코드는 **허용 경로에 로그가 없고**, `if not data: continue` 와 파싱 실패
`continue` 가 **무음**이라 "표본화로 놓쳤다" / "값을 읽었는데 정상이었다" /
"조회 실패로 조용히 허용됐다" 가 로그로 갈리지 않았다.

이 파일은 두 가지를 고정한다.

1) 관측성 — 실제 조회(캐시 미스)마다 읽은 값이 남고, 조회/파싱 실패가
   정상 허용과 **구별되는** 로그를 남긴다. 캐시 히트에는 로그가 없다.
2) 🔴 판정 불변 — 로깅 추가가 반환값(차단/허용)을 한 케이스도 바꾸지
   않았다. `TestVerdictUnchanged` 가 변경 전 판정 규칙 전수 표와 대조한다.
"""
from unittest.mock import Mock, patch

import pytest

import api.kis_market_api as kis_market_api
from core.trading_decision_engine import TradingDecisionEngine


KOSPI_THRESHOLD = -2.5
KOSDAQ_THRESHOLD = -3.0


def _make_engine():
    """캐시/로거만 갖춘 최소 엔진 — 기존 테스트(test_crash_gate_market_scope)와 동형."""
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.logger = Mock()
    engine._market_direction_cache = {}
    engine._market_direction_cache_time = {}
    engine._MARKET_DIRECTION_CACHE_TTL = 60
    return engine


def _info_lines(engine):
    return [c.args[0] for c in engine.logger.info.call_args_list]


def _gate_lines(engine):
    return [m for m in _info_lines(engine) if m.startswith("[시장방향성필터]")]


def _index_fn(values):
    """코드→응답 매핑. 값이 None 이면 falsy 응답(조회 실패)."""
    def fn(code):
        v = values.get(code)
        if v is None:
            return None
        return {"bstp_nmix_prdy_ctrt": v}
    return fn


class TestObservabilityOnAllowPath:
    """(a) 허용 경로에도 읽은 값이 남는다."""

    def test_allow_path_logs_the_value_it_read(self):
        engine = _make_engine()
        with patch.object(kis_market_api, "get_index_data", _index_fn({"1001": "-2.90"})):
            verdict = engine.check_market_direction(regime_index="KOSDAQ")

        assert verdict == (False, "")
        lines = _gate_lines(engine)
        assert len(lines) == 1
        line = lines[0]
        # 최소 필드: 지수명·지수코드·읽은 등락률·임계값·판정
        assert "지수=KOSDAQ" in line
        assert "코드=1001" in line
        assert "등락률=-2.90%" in line
        assert f"임계값={KOSDAQ_THRESHOLD}%" in line
        assert "판정=허용" in line

    def test_block_path_also_logs_the_value_it_read(self):
        engine = _make_engine()
        with patch.object(kis_market_api, "get_index_data", _index_fn({"1001": "-3.13"})):
            verdict = engine.check_market_direction(regime_index="KOSDAQ")

        assert verdict[0] is True
        lines = _gate_lines(engine)
        assert any("등락률=-3.13%" in m and "판정=차단" in m for m in lines)
        # 기존 집계 스크립트가 의존하는 원래 문구는 그대로 남아 있어야 한다.
        assert any(m.startswith("[시장방향성필터] 매수 차단: ") for m in lines)

    def test_both_logs_one_line_per_index_queried(self):
        engine = _make_engine()
        with patch.object(kis_market_api, "get_index_data",
                          _index_fn({"0001": "-0.10", "1001": "-2.90"})):
            engine.check_market_direction(regime_index="both")

        observed = [m for m in _gate_lines(engine) if "등락률=" in m]
        assert len(observed) == 2
        assert any("지수=KOSPI" in m and "등락률=-0.10%" in m for m in observed)
        assert any("지수=KOSDAQ" in m and "등락률=-2.90%" in m for m in observed)

    def test_every_line_keeps_the_existing_prefix(self):
        """기존 grep 패턴·집계 스크립트 호환 — 접두는 `[시장방향성필터]` 하나뿐."""
        engine = _make_engine()
        with patch.object(kis_market_api, "get_index_data",
                          _index_fn({"0001": "-0.10", "1001": None})):
            engine.check_market_direction(regime_index="both")

        assert _info_lines(engine) == _gate_lines(engine)
        assert len(_gate_lines(engine)) == 2


class TestFailureIsDistinguishableFromNormalAllow:
    """(b) 「못 읽어서 허용」과 「정상값이라 허용」이 로그만으로 갈린다."""

    def test_missing_response_is_logged_and_distinct(self):
        engine = _make_engine()
        with patch.object(kis_market_api, "get_index_data", _index_fn({"1001": None})):
            verdict = engine.check_market_direction(regime_index="KOSDAQ")

        assert verdict == (False, "")
        lines = _gate_lines(engine)
        assert len(lines) == 1
        assert "관측실패" in lines[0]
        assert "사유=응답없음" in lines[0]
        assert "지수=KOSDAQ" in lines[0] and "코드=1001" in lines[0]
        assert "판정=허용(무판정)" in lines[0]
        # 정상 허용 라인의 지문(등락률=)이 없어야 한다 — 두 경로가 섞이면 안 된다.
        assert "등락률=" not in lines[0]

    def test_unparsable_value_is_logged_with_the_raw_value(self):
        engine = _make_engine()
        with patch.object(kis_market_api, "get_index_data", _index_fn({"1001": "N/A"})):
            verdict = engine.check_market_direction(regime_index="KOSDAQ")

        assert verdict == (False, "")
        lines = _gate_lines(engine)
        assert len(lines) == 1
        assert "관측실패" in lines[0]
        assert "사유=파싱불가" in lines[0]
        assert "'N/A'" in lines[0]
        assert "등락률=" not in lines[0]

    def test_three_allow_reasons_have_three_distinct_signatures(self):
        """정상 허용 / 응답없음 / 파싱불가 — 반환값은 셋 다 (False, "") 이지만
        로그 지문은 서로 달라야 한다. 이 구별이 이번 작업의 전부다."""
        signatures = {}
        for label, payload in [
            ("normal", {"1001": "-0.50"}),
            ("no_data", {"1001": None}),
            ("unparsable", {"1001": "-"}),
        ]:
            engine = _make_engine()
            with patch.object(kis_market_api, "get_index_data", _index_fn(payload)):
                assert engine.check_market_direction(regime_index="KOSDAQ") == (False, "")
            lines = _gate_lines(engine)
            assert len(lines) == 1
            signatures[label] = lines[0]

        assert len(set(signatures.values())) == 3
        assert "등락률=" in signatures["normal"] and "관측실패" not in signatures["normal"]
        assert "사유=응답없음" in signatures["no_data"]
        assert "사유=파싱불가" in signatures["unparsable"]


class TestCacheHitStaysSilent:
    """캐시 히트는 조회를 안 하므로 로그도 남기지 않는다(시계열 오염 방지)."""

    def test_second_call_within_ttl_logs_nothing_extra(self):
        engine = _make_engine()
        calls = []

        def fn(code):
            calls.append(code)
            return {"bstp_nmix_prdy_ctrt": "-0.50"}

        with patch.object(kis_market_api, "get_index_data", fn):
            first = engine.check_market_direction(regime_index="KOSDAQ")
            after_first = len(_gate_lines(engine))
            for _ in range(20):
                assert engine.check_market_direction(regime_index="KOSDAQ") == first

        assert calls == ["1001"]                      # 실제 조회는 1회
        assert after_first == 1
        assert len(_gate_lines(engine)) == 1          # 로그도 1줄뿐

    def test_expired_cache_logs_again(self):
        """TTL 만료 후 재조회되면 새 값이 다시 남아야 시계열이 이어진다."""
        engine = _make_engine()
        seq = iter(["-0.50", "-3.20"])

        with patch.object(kis_market_api, "get_index_data",
                          lambda code: {"bstp_nmix_prdy_ctrt": next(seq)}):
            engine.check_market_direction(regime_index="KOSDAQ")
            engine._market_direction_cache_time["KOSDAQ"] -= 61  # TTL 만료 강제
            engine.check_market_direction(regime_index="KOSDAQ")

        observed = [m for m in _gate_lines(engine) if "등락률=" in m]
        assert len(observed) == 2
        assert "등락률=-0.50%" in observed[0] and "판정=허용" in observed[0]
        assert "등락률=-3.20%" in observed[1] and "판정=차단" in observed[1]


class TestVerdictUnchanged:
    """🔴 (c) 회귀 방지 — 로깅 추가 전 판정 규칙과 반환값이 전수 일치한다.

    아래 표는 변경 전 코드(:186-200)의 동작을 그대로 옮긴 것이다:
      · 응답 없음 → continue → 최종 (False, "")
      · 파싱 실패 → continue → 최종 (False, "")
      · change <= threshold → (True, "{name} {change:+.2f}% (임계값: {threshold}%)")
      · 그 외 → (False, "")
      · both 는 KOSPI 를 먼저 검사하므로 KOSPI 가 걸리면 KOSDAQ 은 조회조차 안 된다.
    """

    @pytest.mark.parametrize("idx,payload,expected", [
        # --- 단일 지수: 정상 허용 ---
        ("KOSPI",  {"0001": "-0.10"}, (False, "")),
        ("KOSDAQ", {"1001": "-2.90"}, (False, "")),          # 임계 -3.0 미달 → 허용
        # 2026-08-07 10:41:01 대시보드 실측값. -3.04 <= -3.0 이므로 규칙상 **차단**이
        # 정답이다 — 그날 차단이 0건이었다는 사실이 곧 "게이트가 이 값을 못 봤다"는
        # 뜻이고, 이번 로깅이 그것을 다음 급락일에 확정한다.
        ("KOSDAQ", {"1001": "-3.04"}, (True, "KOSDAQ -3.04% (임계값: -3.0%)")),
        # --- 단일 지수: 경계값(임계와 정확히 같으면 차단) ---
        ("KOSDAQ", {"1001": "-3.00"}, (True, "KOSDAQ -3.00% (임계값: -3.0%)")),
        ("KOSPI",  {"0001": "-2.50"}, (True, "KOSPI -2.50% (임계값: -2.5%)")),
        # --- 단일 지수: 차단 ---
        ("KOSDAQ", {"1001": "-3.13"}, (True, "KOSDAQ -3.13% (임계값: -3.0%)")),
        # --- fail-open 2 경로 ---
        ("KOSDAQ", {"1001": None},    (False, "")),          # 응답 없음
        ("KOSDAQ", {"1001": "N/A"},   (False, "")),          # 파싱 실패
        ("KOSPI",  {"0001": None},    (False, "")),
        # --- both: 순서·단락 ---
        ("both", {"0001": "-0.10", "1001": "-0.20"}, (False, "")),
        ("both", {"0001": "-5.29", "1001": "+2.45"}, (True, "KOSPI -5.29% (임계값: -2.5%)")),
        ("both", {"0001": "-0.10", "1001": "-3.13"}, (True, "KOSDAQ -3.13% (임계값: -3.0%)")),
        ("both", {"0001": None,    "1001": "-3.13"}, (True, "KOSDAQ -3.13% (임계값: -3.0%)")),
        ("both", {"0001": None,    "1001": None},    (False, "")),
        # --- 면제·폴백 ---
        ("none",  {}, (False, "")),
        ("Auto",  {"0001": "-0.10", "1001": "-0.20"}, (False, "")),   # 인식불가 → both 폴백
        ("Auto",  {"0001": "-5.29", "1001": "+2.45"}, (True, "KOSPI -5.29% (임계값: -2.5%)")),
    ])
    def test_verdict_matches_pre_change_behavior(self, idx, payload, expected):
        engine = _make_engine()
        with patch.object(kis_market_api, "get_index_data", _index_fn(payload)):
            assert engine.check_market_direction(regime_index=idx) == expected

    def test_api_exception_still_fails_open_with_warning(self):
        """외부 except 경로(API 예외)는 변경 대상이 아니다 — 그대로여야 한다."""
        engine = _make_engine()

        def boom(_code):
            raise RuntimeError("boom")

        with patch.object(kis_market_api, "get_index_data", boom):
            assert engine.check_market_direction(regime_index="KOSPI") == (False, "")

        assert engine.logger.warning.called
        assert "API 조회 실패" in engine.logger.warning.call_args.args[0]

    def test_short_circuit_skips_second_index_when_first_blocks(self):
        """both 에서 KOSPI 가 차단되면 KOSDAQ 은 조회되지 않는다(변경 전과 동일)."""
        engine = _make_engine()
        calls = []

        def fn(code):
            calls.append(code)
            return {"bstp_nmix_prdy_ctrt": {"0001": "-5.29", "1001": "+2.45"}[code]}

        with patch.object(kis_market_api, "get_index_data", fn):
            engine.check_market_direction(regime_index="both")

        assert calls == ["0001"]

    def test_cached_verdict_is_returned_verbatim(self):
        """캐시 저장/반환 동작 불변 — 조회 없이 같은 튜플이 그대로 나온다."""
        engine = _make_engine()
        with patch.object(kis_market_api, "get_index_data", _index_fn({"1001": "-3.13"})):
            first = engine.check_market_direction(regime_index="KOSDAQ")

        def boom(_code):
            raise AssertionError("캐시 히트인데 조회가 일어났다")

        with patch.object(kis_market_api, "get_index_data", boom):
            assert engine.check_market_direction(regime_index="KOSDAQ") == first
        assert engine._market_direction_cache["KOSDAQ"] == first
