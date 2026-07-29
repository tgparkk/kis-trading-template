"""FundManager.max_position_count 를 로드된 전략들의 K 합계로 정정하는 회귀 테스트.

배경(2026-07-29):
    main.py 는 ``FundManager(max_daily_loss_ratio=...)`` 로만 생성해 동시 보유 한도가
    기본값 **20** 이었다. 이 20 은 단일전략 시절의 레거시이고, 현재는 8전략 독립 운영이라
    전략별 K(risk_management.max_positions) 합계가 58 이다. 07-29 실보유 40종목처럼
    한도 2배를 이미 넘겼으므로, 실전 전환 시 20 에서 매수가 막히는 사고가 난다.

범위(사장님 결정):
    **한도값만 ΣK 로 정정한다. 페이퍼 매수 경로에 결선하지 않는다.**
    전역 한도를 페이퍼에 결선하면 2026-06-16 채택한 전략별 완전독립 포지션(B안)과 충돌한다
    (먼저 채운 전략이 나머지 전략을 굶기는 교차 간섭). 아래 test_can_add_position_*
    가 그 불변을 지킨다.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.initializer import BotInitializer
from core.fund_manager import FundManager


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _strat(k=None, per_stock=None):
    """전략 스텁. k=None 이면 K 미상(yaml 에도 _max_positions 에도 없음)."""
    risk = {}
    if k is not None:
        risk["max_positions"] = k
    if per_stock is not None:
        risk["paper_investment_per_stock"] = per_stock
    return SimpleNamespace(config={"risk_management": risk})


def _make_bot(strategies, *, is_virtual=True, vtm=None, initial_limit=20):
    fm = FundManager(initial_funds=100_000_000, max_position_count=initial_limit)
    return SimpleNamespace(
        decision_engine=SimpleNamespace(
            virtual_trading=vtm, is_virtual_mode=is_virtual
        ),
        strategies=strategies,
        fund_manager=fm,
    )


def _run(bot):
    """_allocate_strategy_capital 실행 후 (로거 Mock) 반환."""
    init = BotInitializer(bot)
    init.logger = Mock()
    init._allocate_strategy_capital()
    return init.logger


def _log_text(logger_mock, level):
    return "\n".join(str(c.args[0]) if c.args else str(c)
                     for c in getattr(logger_mock, level).call_args_list)


# 라이브 8전략의 실제 K (strategies/*/config.yaml)
LIVE_K = {
    "elder_ema_pullback": 20,
    "rs_leader": 10,
    "minervini_volume_dryup": 3,
    "book_envelope_200d": 5,
    "daytrading_3methods_breakout": 5,
    "book_pullback_ma20": 5,
    "book_pullback_ma5": 5,
    "deep_mr_dev20": 5,
}


# ---------------------------------------------------------------------------
# 1. ΣK 산출
# ---------------------------------------------------------------------------

class TestTotalKSum:
    def test_eight_live_strategies_sum_to_58(self):
        """라이브 8전략(20/10/3/5×5) → max_position_count == 58."""
        bot = _make_bot({name: _strat(k) for name, k in LIVE_K.items()})
        _run(bot)
        assert bot.fund_manager.max_position_count == 58

    def test_sum_follows_added_strategy(self):
        """전략 추가 시 합계가 따라온다(58 하드코딩이 아님을 증명)."""
        strategies = {name: _strat(k) for name, k in LIVE_K.items()}
        strategies["new_strategy_k7"] = _strat(7)
        bot = _make_bot(strategies)
        _run(bot)
        assert bot.fund_manager.max_position_count == 65

    def test_sum_follows_removed_strategy(self):
        """전략 삭제 시에도 합계가 따라온다(단, 바닥 20 밑으로는 안 내려감)."""
        strategies = {name: _strat(k) for name, k in LIVE_K.items()
                      if name != "elder_ema_pullback"}  # ΣK = 38
        bot = _make_bot(strategies)
        _run(bot)
        assert bot.fund_manager.max_position_count == 38

    def test_k_from_max_positions_attribute_fallback(self):
        """yaml 에 없으면 _max_positions 속성을 쓴다(기존 K 읽기 규약 재사용)."""
        strat = SimpleNamespace(config={"risk_management": {}})
        strat._max_positions = 12
        bot = _make_bot({"attr_only": strat, "yaml": _strat(30)})
        _run(bot)
        assert bot.fund_manager.max_position_count == 42


# ---------------------------------------------------------------------------
# 2. 바닥 보장 — 어떤 경우에도 오늘보다 좁아지지 않는다
# ---------------------------------------------------------------------------

class TestFloorGuard:
    def test_small_total_k_keeps_existing_limit(self):
        """ΣK(7) < 기존값(20) → 기존 20 유지. 이 작업은 완화 방향이다."""
        bot = _make_bot({"a": _strat(3), "b": _strat(4)})
        _run(bot)
        assert bot.fund_manager.max_position_count == 20

    def test_floor_uses_existing_value_not_literal_20(self):
        """바닥은 리터럴 20 이 아니라 '기존값' 이다."""
        bot = _make_bot({"a": _strat(3)}, initial_limit=44)
        _run(bot)
        assert bot.fund_manager.max_position_count == 44

    def test_equal_total_k_is_noop(self):
        bot = _make_bot({"a": _strat(20)})
        _run(bot)
        assert bot.fund_manager.max_position_count == 20


# ---------------------------------------------------------------------------
# 3. K 미상 전략 — 합계 제외 + WARNING (조용히 0으로 세지 말 것)
# ---------------------------------------------------------------------------

class TestUnknownK:
    def test_unknown_k_excluded_and_warned(self):
        bot = _make_bot({
            "known_a": _strat(30),
            "known_b": _strat(15),
            "mystery": _strat(None),
        })
        logger = _run(bot)
        assert bot.fund_manager.max_position_count == 45  # 미상 전략은 합계 제외
        warns = _log_text(logger, "warning")
        assert "mystery" in warns, f"K 미상 전략명이 경고에 없음: {warns!r}"

    def test_zero_or_negative_k_treated_as_unknown(self):
        bot = _make_bot({"good": _strat(25), "zero": _strat(0), "neg": _strat(-3)})
        logger = _run(bot)
        assert bot.fund_manager.max_position_count == 25
        warns = _log_text(logger, "warning")
        assert "zero" in warns and "neg" in warns

    def test_non_numeric_k_treated_as_unknown(self):
        bot = _make_bot({"good": _strat(25), "bad": _strat("many")})
        logger = _run(bot)
        assert bot.fund_manager.max_position_count == 25
        assert "bad" in _log_text(logger, "warning")


# ---------------------------------------------------------------------------
# 4. 전략 0개 / total_k == 0 → 기존값 유지 + WARNING
# ---------------------------------------------------------------------------

class TestDegenerate:
    def test_no_strategies_keeps_existing_and_warns(self):
        bot = _make_bot({})
        logger = _run(bot)
        assert bot.fund_manager.max_position_count == 20
        assert _log_text(logger, "warning").strip(), "전략 0개인데 경고가 없음"

    def test_all_unknown_k_keeps_existing_and_warns(self):
        bot = _make_bot({"x": _strat(None), "y": _strat(None)})
        logger = _run(bot)
        assert bot.fund_manager.max_position_count == 20
        assert _log_text(logger, "warning").strip()

    def test_missing_fund_manager_does_not_raise(self):
        """fund_manager 미연결 봇(기존 테스트 하네스)에서도 폭발하지 않는다."""
        bot = SimpleNamespace(
            decision_engine=SimpleNamespace(virtual_trading=None, is_virtual_mode=True),
            strategies={"a": _strat(5)},
        )
        _run(bot)  # 예외 없이 통과하면 성공


# ---------------------------------------------------------------------------
# 5. 모드 무관 — 실전에서도 적용된다 (이 작업의 목적)
# ---------------------------------------------------------------------------

class TestModeIndependence:
    def test_applied_in_real_mode(self):
        """실전 모드(is_virtual_mode=False, vtm 없음)에서도 ΣK 가 적용된다.

        _allocate_strategy_capital 은 가상 전용 조기 return 을 갖고 있으므로,
        K 합산은 그 게이트 '바깥' 에 있어야 한다.
        """
        bot = _make_bot({name: _strat(k) for name, k in LIVE_K.items()},
                        is_virtual=False, vtm=None)
        _run(bot)
        assert bot.fund_manager.max_position_count == 58

    def test_applied_when_vtm_absent_in_virtual_mode(self):
        bot = _make_bot({name: _strat(k) for name, k in LIVE_K.items()},
                        is_virtual=True, vtm=None)
        _run(bot)
        assert bot.fund_manager.max_position_count == 58

    def test_info_log_reports_breakdown_and_transition(self):
        bot = _make_bot({"elder_ema_pullback": _strat(20), "rs_leader": _strat(10),
                         "minervini_volume_dryup": _strat(3)})
        logger = _run(bot)
        infos = _log_text(logger, "info")
        assert "elder_ema_pullback" in infos and "33" in infos, infos
        assert "20" in infos, infos


# ---------------------------------------------------------------------------
# 6. 페이퍼 동작 불변 회귀
# ---------------------------------------------------------------------------

_PROD_DIRS = ("bot", "core", "strategies", "utils", "config", "collectors")


def _prod_py_files():
    root = Path(__file__).resolve().parent.parent
    files = [root / "main.py"]
    for d in _PROD_DIRS:
        p = root / d
        if p.is_dir():
            files.extend(f for f in p.rglob("*.py")
                         if "__pycache__" not in f.parts)
    return [f for f in files if f.exists()]


class TestPaperBehaviourUnchanged:
    def test_can_add_position_only_wired_to_real_order_path(self):
        """전역 한도 게이트는 여전히 실주문 경로에만 결선돼 있어야 한다.

        B안(전략별 완전독립 포지션)과 충돌하므로 페이퍼 매수 경로에 결선 금지.
        주석·로그 문자열의 언급은 결선이 아니므로 AST 의 실제 호출 노드만 센다.
        """
        root = Path(__file__).resolve().parent.parent
        callers = set()
        for f in _prod_py_files():
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "can_add_position" not in text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = (fn.attr if isinstance(fn, ast.Attribute)
                        else fn.id if isinstance(fn, ast.Name) else None)
                if name == "can_add_position":
                    callers.add(f.relative_to(root).as_posix())
        assert callers == {"core/trading/order_execution.py"}, (
            f"can_add_position 호출처가 실주문 경로 밖으로 번짐: {sorted(callers)}"
        )

    def test_virtual_capital_allocation_still_applies_k_split(self):
        """가상 자금 K분할 할당(기존 동작)이 그대로 유지된다."""
        from core.virtual_trading_manager import VirtualTradingManager
        vtm = VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)
        bot = _make_bot({"elder_ema_pullback": _strat(20)}, is_virtual=True, vtm=vtm)
        _run(bot)
        # 10M / K20 = 50만 → 1만원 종목 50주
        assert vtm.get_max_quantity(10_000, strategy_name="elder_ema_pullback") == 50
        assert bot.fund_manager.max_position_count == 20  # ΣK=20 = 바닥

    def test_per_stock_override_still_applies(self):
        from core.virtual_trading_manager import VirtualTradingManager
        vtm = VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)
        bot = _make_bot({"deep_mr_dev20": _strat(5, per_stock=2_000_000)},
                        is_virtual=True, vtm=vtm)
        _run(bot)
        assert vtm.get_max_quantity(10_000, strategy_name="deep_mr_dev20") == 200

    def test_no_allocation_in_real_mode(self):
        """실전 모드에서는 가상 자금 할당이 여전히 일어나지 않는다."""
        vtm = Mock()
        bot = _make_bot({"a": _strat(5)}, is_virtual=False, vtm=vtm)
        _run(bot)
        vtm.allocate_strategy_capital.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
