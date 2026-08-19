"""문서 1(minervini PREREG.md) 실행 경로의 «동결» 잠금.

이후 문서 5(돌파 축)를 위해 run.py 에 코드가 «추가»되는데, 그 과정에서 문서 1의
arm·캐시·시드·상수가 바뀌면 판정 완료된 결과를 재현할 수 없게 된다.
🔑 이 파일은 「추가는 허용, 변경은 금지」를 기계로 강제한다.
"""
import importlib
import inspect

import pytest

RUN = importlib.import_module(
    "backtest.concept_axes.minervini.run"
)


class TestDoc1FrozenConstants:
    def test_window_and_thresholds(self):
        assert RUN.W0 == "2024-03-13"
        assert RUN.W1 == "2026-05-31"
        assert RUN.HIST0 == "2021-01-01"
        assert RUN.LOOKBACK == 260
        assert RUN.SCORE_WINDOW == 30
        assert RUN.MAX_CANDIDATES == 10
        assert RUN.N_SEEDS == 20
        assert RUN.EPS_ECON == 0.5
        assert RUN.MIN_TRIGGER_FRAC == 0.10


class TestDoc1FrozenArms:
    def test_arm_rule_keys_exact(self):
        assert set(RUN.ARM_RULE) == {"D", "DT", "DF", "DTF", "T"}

    def test_arm_rule_arity_is_three(self):
        for name, fn in RUN.ARM_RULE.items():
            sig = inspect.signature(fn)
            assert len(sig.parameters) == 3, f"{name} arity changed"

    def test_arm_rule_truth_table(self):
        # (dry, tt, f) -> 기대 발화
        cases = [
            ((True, False, False), {"D"}),
            ((True, True, False), {"D", "DT", "T"}),
            ((True, False, True), {"D", "DF"}),
            ((True, True, True), {"D", "DT", "DF", "DTF", "T"}),
            ((False, True, False), {"T"}),
            ((False, False, False), set()),
        ]
        for args, expect in cases:
            fired = {a for a, fn in RUN.ARM_RULE.items() if fn(*args)}
            assert fired == expect, f"{args} -> {fired}, expected {expect}"


class TestDoc1FrozenSignatures:
    def test_build_cache_signature(self):
        sig = inspect.signature(RUN.build_cache)
        assert list(sig.parameters) == ["px", "elig", "rs", "fin", "params"]

    def test_build_pools_signature(self):
        sig = inspect.signature(RUN.build_pools)
        assert list(sig.parameters) == ["cache", "elig"]

    def test_select_random_signature(self):
        sig = inspect.signature(RUN.select_random)
        assert list(sig.parameters) == ["pool", "seed"]

    def test_stage1_takes_no_args(self):
        assert list(inspect.signature(RUN.stage1).parameters) == []

    def test_stage2_takes_no_args(self):
        assert list(inspect.signature(RUN.stage2).parameters) == []


class TestDoc1CacheTupleShape:
    """build_cache 의 «값 튜플 길이 5» 를 못박는다.

    build_pools 가 `(score, dry, tt, f, _close)` 로 언패킹하므로 길이가 바뀌면
    문서 1 이 즉시 깨진다. 문서 5 는 «별도» 캐시를 쓰도록 설계됐다.
    """

    def test_build_pools_unpacks_five(self):
        src = inspect.getsource(RUN.build_pools)
        assert "(score, dry, tt, f, _close)" in src
