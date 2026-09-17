"""``max_per_stock_amount`` 사이징 결선 테스트 (2026-08-27).

배경 — 「선언만 있고 독자가 없는 한도」 계열:
    각 전략 config.yaml 의 ``risk_management.max_per_stock_amount`` (예: 3,000,000)
    는 지금까지 **사이징 경로에 아무 독자도 없었다**. 유일한 독자는
    strategies/*/strategy.py 의 ``recommended_qty`` = 표시용 메타데이터뿐이고,
    실제 페이퍼 매수 수량은 core/virtual_trading_manager.py::get_max_quantity 의
        qty = int(min(per_stock, budget) / price)
    로만 정해졌다 (per_stock = 10,000,000 / K).

수정:
    선언된 상한을 **같은 min() 안에** 넣는다.
        qty = int(min(per_stock, budget, cap) / price)
    cap 은 소유 전략의 max_per_stock_amount 가 선언돼 있고 > 0 일 때만.
    미선언/None/0 이면 상한 없음 = 기존 거동 그대로.

범위 가드:
- per_stock 의 산식(10,000,000/K, 복리 재산정)은 **건드리지 않는다**.
- 실전 경로(fund_manager.get_max_buy_amount)는 **건드리지 않는다**.
- (2026-08-27 결선 시점) 라이브 8전략 중 실제로 값이 바뀌는 건 minervini_volume_dryup
  하나뿐이었다(K=3 → per_stock 3,333,333 > cap 3,000,000). 나머지 7전략은 cap >= per_stock.

2026-09-17 갱신 — 기준 커밋 c565256 (집중 3전략 K 상향 · 사전등록
docs/prereg_2026-09-15_focus3_K_raise.md · 발효 2026-09-18 07:40):
    minervini K 3→6 으로 per_stock = 10,000,000/6 ≈ 1,666,667 < cap 3,000,000.
    ⇒ **초기자본 기준으로 상한이 물리는 라이브 전략은 0개**다(ΣK 71).
    TestLiveConfigs 는 (a) 이 라이브 설정 스냅샷을 고정하고, (b) 상한 배선이
    실제로 수량을 자르는지는 라이브 K 와 무관하게 합성 설정(K 작게)으로 계속 검증한다.
"""
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import yaml

from config.constants import VIRTUAL_CAPITAL_PER_STRATEGY


INITIAL = float(VIRTUAL_CAPITAL_PER_STRATEGY)
STRATEGIES_DIR = Path(__file__).resolve().parents[1] / "strategies"


def _make_vtm():
    with patch('core.virtual_trading_manager.setup_logger'):
        from core.virtual_trading_manager import VirtualTradingManager
        return VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)


def _vtm_with(cap, *, k=5, capital=INITIAL, name="stratA"):
    """K 분할 원장 + (선언 시) 상한이 설정된 VTM."""
    vtm = _make_vtm()
    vtm.allocate_strategy_capital(name, capital, max_positions=k)
    if cap is not None:
        vtm.set_strategy_max_per_stock(name, cap)
    return vtm


# ---------------------------------------------------------------------------
# 1) 상한이 물릴 때 — cap < per_stock
# ---------------------------------------------------------------------------

class TestCapBinds:
    def test_cap_below_per_stock_is_used(self):
        """K=3 → per_stock 3,333,333 · cap 3,000,000 → 수량은 cap 기준."""
        vtm = _vtm_with(3_000_000, k=3)
        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(
            INITIAL / 3)
        assert vtm.get_max_quantity(10_000, "stratA") == int(3_000_000 / 10_000)

    def test_cap_binds_at_non_round_price(self):
        """int() 절사 위치가 cap 기준인지 (per_stock 기준이면 1주 더 나온다)."""
        vtm = _vtm_with(3_000_000, k=3)
        price = 7_777.0
        assert vtm.get_max_quantity(price, "stratA") == int(3_000_000 / price)
        assert vtm.get_max_quantity(price, "stratA") < int((INITIAL / 3) / price)

    def test_cap_binds_logs_one_debug_line(self, caplog):
        """상한이 물릴 때만 DEBUG 1줄 (핫패스에 다른 로그 추가 금지)."""
        vtm = _vtm_with(3_000_000, k=3)
        vtm.logger = logging.getLogger("test_max_per_stock_cap")
        with caplog.at_level(logging.DEBUG, logger="test_max_per_stock_cap"):
            vtm.get_max_quantity(10_000, "stratA")
        debug_msgs = [r.message for r in caplog.records
                      if r.levelno == logging.DEBUG]
        assert len(debug_msgs) == 1, f"DEBUG 줄 수가 1이 아님: {debug_msgs!r}"
        assert "stratA" in debug_msgs[0]

    def test_no_debug_log_when_cap_does_not_bind(self, caplog):
        vtm = _vtm_with(5_000_000, k=5)  # per_stock 2,000,000 < cap
        vtm.logger = logging.getLogger("test_max_per_stock_nocap")
        with caplog.at_level(logging.DEBUG, logger="test_max_per_stock_nocap"):
            vtm.get_max_quantity(10_000, "stratA")
        assert [r.message for r in caplog.records
                if r.levelno == logging.DEBUG] == []


# ---------------------------------------------------------------------------
# 2) 상한이 안 물릴 때 — 기존 거동 불변
# ---------------------------------------------------------------------------

class TestCapDoesNotBind:
    def test_cap_above_per_stock_is_ignored(self):
        """K=5 → per_stock 2,000,000 < cap 3,000,000 → 기존과 동일."""
        vtm = _vtm_with(3_000_000, k=5)
        baseline = _vtm_with(None, k=5)
        assert vtm.get_max_quantity(10_000, "stratA") == 200
        assert vtm.get_max_quantity(10_000, "stratA") == baseline.get_max_quantity(
            10_000, "stratA")

    def test_cap_equal_to_per_stock_is_noop(self):
        vtm = _vtm_with(2_000_000, k=5)
        assert vtm.get_max_quantity(10_000, "stratA") == 200


# ---------------------------------------------------------------------------
# 3) 미선언 / None / 0 / 음수 → 상한 없음 (기존 거동)
# ---------------------------------------------------------------------------

class TestCapAbsent:
    @pytest.mark.parametrize("cap", [None, 0, 0.0, -1, -3_000_000])
    def test_missing_or_nonpositive_cap_is_no_cap(self, cap):
        vtm = _vtm_with(cap, k=3)
        assert vtm.get_max_quantity(10_000, "stratA") == int((INITIAL / 3) / 10_000)

    def test_unknown_strategy_key_is_no_cap(self):
        """다른 전략에 상한이 있어도 내 키가 아니면 안 물린다(키잉 격리)."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=3)
        vtm.allocate_strategy_capital("stratB", INITIAL, max_positions=3)
        vtm.set_strategy_max_per_stock("stratB", 3_000_000)
        assert vtm.get_max_quantity(10_000, "stratA") == int((INITIAL / 3) / 10_000)
        assert vtm.get_max_quantity(10_000, "stratB") == 300

    def test_legacy_no_ledger_path_unchanged(self):
        """원장 미활성(레거시 단일 잔고) = min(virtual_investment_amount, 잔고)."""
        vtm = _make_vtm()
        vtm.virtual_balance = 50_000_000.0
        vtm.virtual_investment_amount = 1_000_000.0
        assert vtm.get_max_quantity(10_000, "legacy") == 100


# ---------------------------------------------------------------------------
# 4) budget 이 더 작으면 budget 이 여전히 물린다 (min 3항)
# ---------------------------------------------------------------------------

class TestBudgetStillBinds:
    def test_budget_below_cap_below_per_stock(self):
        """budget 1,000,000 < cap 3,000,000 < per_stock 3,333,333 → budget."""
        vtm = _vtm_with(3_000_000, k=3)
        vtm._strategy_balances["stratA"] = 1_000_000.0
        vtm._sync_aggregate_from_strategies()
        assert vtm.get_max_quantity(10_000, "stratA") == 100

    def test_zero_budget_gives_zero_even_with_cap(self):
        vtm = _vtm_with(3_000_000, k=3)
        vtm._strategy_balances["stratA"] = 0.0
        vtm._sync_aggregate_from_strategies()
        assert vtm.get_max_quantity(10_000, "stratA") == 0

    def test_invalid_price_still_zero(self):
        vtm = _vtm_with(3_000_000, k=3)
        assert vtm.get_max_quantity(0, "stratA") == 0
        assert vtm.get_max_quantity(-1, "stratA") == 0


# ---------------------------------------------------------------------------
# 5) initializer 결선 — config.yaml 값이 같은 원장 키로 VTM 에 도달한다
# ---------------------------------------------------------------------------

def _strat(k=None, cap=None, per_stock=None):
    risk = {}
    if k is not None:
        risk["max_positions"] = k
    if cap is not None:
        risk["max_per_stock_amount"] = cap
    if per_stock is not None:
        risk["paper_investment_per_stock"] = per_stock
    return SimpleNamespace(config={"risk_management": risk})


def _run_initializer(strategies, *, is_virtual=True, vtm=None):
    from bot.initializer import BotInitializer
    bot = SimpleNamespace(
        decision_engine=SimpleNamespace(
            virtual_trading=vtm, is_virtual_mode=is_virtual),
        strategies=strategies,
        fund_manager=None,
    )
    init = BotInitializer(bot)
    init.logger = Mock()
    init._allocate_strategy_capital()
    return init.logger


class TestInitializerWiring:
    def test_cap_reaches_vtm_under_ledger_key(self):
        vtm = _make_vtm()
        _run_initializer({"minervini_volume_dryup": _strat(k=3, cap=3_000_000)},
                         vtm=vtm)
        assert vtm._strategy_max_per_stock["minervini_volume_dryup"] == 3_000_000
        # 같은 키로 사이징까지 도달
        assert vtm.get_max_quantity(10_000, "minervini_volume_dryup") == 300

    def test_missing_cap_leaves_no_entry(self):
        vtm = _make_vtm()
        _run_initializer({"nocap": _strat(k=3)}, vtm=vtm)
        assert "nocap" not in vtm._strategy_max_per_stock
        assert vtm.get_max_quantity(10_000, "nocap") == int((INITIAL / 3) / 10_000)

    def test_per_stock_override_and_cap_coexist(self):
        """paper_investment_per_stock 오버라이드와 상한이 함께 있어도 각자 동작."""
        vtm = _make_vtm()
        _run_initializer(
            {"deep": _strat(k=5, cap=2_000_000, per_stock=2_500_000)}, vtm=vtm)
        assert vtm._strategy_investment_amounts["deep"] == pytest.approx(2_500_000)
        assert vtm._strategy_max_per_stock["deep"] == 2_000_000
        assert vtm.get_max_quantity(10_000, "deep") == 200

    def test_real_mode_does_not_allocate_or_cap(self):
        """실전 모드에서는 자금 할당 자체를 안 하므로 상한도 설정되지 않는다."""
        vtm = _make_vtm()
        _run_initializer({"a": _strat(k=3, cap=3_000_000)},
                         is_virtual=False, vtm=vtm)
        assert vtm._strategy_max_per_stock == {}

    def test_non_numeric_cap_warns_and_does_not_raise(self):
        vtm = _make_vtm()
        logger = _run_initializer({"bad": _strat(k=3, cap="삼백만")}, vtm=vtm)
        assert "bad" not in vtm._strategy_max_per_stock
        warns = "\n".join(str(c.args[0]) if c.args else str(c)
                          for c in logger.warning.call_args_list)
        assert "bad" in warns


# ---------------------------------------------------------------------------
# 6) 라이브 8전략 — (a) 설정 스냅샷 고정 · (b) 라이브 상한값으로 배선 검증
#
# 기준 커밋 c565256 (2026-09-17 main · 집중 3전략 K 상향 ma20 5→10 ·
# minervini 3→6 · daytrading 5→10 · 발효 2026-09-18 07:40 ·
# 사전등록 docs/prereg_2026-09-15_focus3_K_raise.md).
# 라이브 K = elder 20 · rs_leader 10 · minervini 6 · envelope 5 · daytrading 10 ·
#            ma20 10 · ma5 5 · deep_mr 5 → ΣK 71.
#
# 원래(2026-08-27) 두 테스트는 두 의도를 한데 담고 있었다.
#   (a) 스냅샷 — 라이브 config 에서 초기자본 기준 상한이 물리는 전략 집합.
#       c565256 이전 = ["minervini_volume_dryup"] (K=3) → 이후 = [] (K=6).
#       config 를 바꾸면 여기서 깨지는 것이 정상이다(의도된 알림).
#   (b) 배선 — 라이브 yaml risk_management 를 그대로 initializer 에 넣었을 때
#       max_per_stock_amount 가 같은 원장 키로 VTM 에 도달하고, 상한이 물리는
#       K 에서는 실제로 수량을 자른다.
# K 상향으로 라이브 K 가 더는 상한에 닿지 않으므로 (b) 는 K 만 작게 덮어쓴
# 합성 설정으로 옮겨 유지한다(K=3 = c565256 이전 값이자 사전등록 §⑥ 6-2 P3
# 롤백 값 — 롤백되면 라이브에서 다시 상한이 물린다). 완전 합성 설정의 배선
# 검증은 위 TestCapBinds · TestInitializerWiring 에도 있다.
# ---------------------------------------------------------------------------

LIVE_STRATEGIES = [
    "elder_ema_pullback",
    "rs_leader",
    "minervini_volume_dryup",
    "book_envelope_200d",
    "daytrading_3methods_breakout",
    "book_pullback_ma20",
    "book_pullback_ma5",
    "deep_mr_dev20",
]


def _live_risk(name):
    with open(STRATEGIES_DIR / name / "config.yaml", encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("risk_management", {}) or {}


def _wire_live(names, *, k_override=None):
    """라이브 yaml risk_management 를 initializer 로 VTM 에 결선.

    k_override = {전략명: K} 이면 그 전략의 max_positions 만 덮어쓴다(합성 설정).
    """
    vtm = _make_vtm()
    strategies = {}
    for name in names:
        risk = dict(_live_risk(name))
        if k_override and name in k_override:
            risk["max_positions"] = k_override[name]
        strategies[name] = SimpleNamespace(config={"risk_management": risk})
    _run_initializer(strategies, vtm=vtm)
    return vtm


MINERVINI = "minervini_volume_dryup"
PRICE = 12_345.0


class TestLiveConfigs:
    # --- (a) 라이브 설정 스냅샷 (c565256) ----------------------------------

    def test_no_live_strategy_is_capped_at_initial_capital(self):
        """초기자본 기준 cap < 종목당 예산 인 라이브 전략 = 없음 (c565256 이후).

        종목당 예산은 initializer 결선 결과로 본다(= 10,000,000/K, yaml
        paper_investment_per_stock 이 있으면 그 값). deep_mr_dev20 은
        paper_investment_per_stock 2,000,000 = cap 2,000,000 (같음 → 안 물림).
        c565256 이전(minervini K=3 → 3,333,333 > 3,000,000)에는 minervini 하나였다.
        """
        vtm = _wire_live(LIVE_STRATEGIES)
        bound = []
        for name in LIVE_STRATEGIES:
            risk = _live_risk(name)
            k = int(risk.get("max_positions") or 0)
            assert risk.get("max_per_stock_amount") and k > 0, (
                f"{name}: cap/K 미선언 "
                f"({risk.get('max_per_stock_amount')!r}/{k!r})")
            # 상한 자체는 여전히 원장에 결선된다(안 물릴 뿐).
            cap = vtm._strategy_max_per_stock.get(name)
            assert cap == float(risk["max_per_stock_amount"]), (name, cap)
            per_stock = vtm._strategy_investment_amounts[name]
            if cap < per_stock:
                bound.append(name)
            else:
                # 안 물리면 수량은 종목당 예산 기준 그대로.
                assert vtm.get_max_quantity(PRICE, name) == int(per_stock / PRICE), name
        assert bound == [], bound

    def test_live_minervini_qty_uses_per_stock_not_cap(self):
        """라이브 config(K=6) 그대로: 상한은 결선되지만 수량은 10,000,000/6 기준.

        12,345원 기준 c565256 이전 int(3,000,000/12,345)=243주
        → 이후 int(1,666,667/12,345)=135주.
        """
        risk = _live_risk(MINERVINI)
        vtm = _wire_live([MINERVINI])
        cap = float(risk["max_per_stock_amount"])
        per_stock = INITIAL / int(risk["max_positions"])
        assert vtm._strategy_max_per_stock[MINERVINI] == cap
        assert vtm._strategy_investment_amounts[MINERVINI] == pytest.approx(per_stock)
        assert per_stock < cap, "스냅샷 전제 변경 — 라이브 minervini 에 상한이 다시 물린다"
        assert vtm.get_max_quantity(PRICE, MINERVINI) == int(per_stock / PRICE)

    # --- (b) 배선 검증 — 라이브 상한값 + 합성 K --------------------------------

    def test_live_minervini_cap_binds_with_small_k(self):
        """라이브 yaml(상한 3,000,000) + 합성 K=3: 상한이 실제로 수량을 자른다.

        per_stock 3,333,333 > cap 3,000,000 → 수량 = int(cap/price) = 243주
        (per_stock 기준이면 270주). 라이브 K 가 바뀌어도 이 검증은 남는다.
        """
        k_small = 3
        vtm = _wire_live([MINERVINI], k_override={MINERVINI: k_small})
        cap = float(_live_risk(MINERVINI)["max_per_stock_amount"])
        per_stock = vtm._strategy_investment_amounts[MINERVINI]
        assert per_stock == pytest.approx(INITIAL / k_small)
        assert vtm._strategy_max_per_stock[MINERVINI] == cap
        assert cap < per_stock, (
            "합성 설정 전제 붕괴 — 상한이 물리지 않는 K 로는 배선을 검증할 수 없다")
        qty = vtm.get_max_quantity(PRICE, MINERVINI)
        assert qty == int(cap / PRICE)
        assert qty < int(per_stock / PRICE)  # 상한이 min() 을 이겼다
