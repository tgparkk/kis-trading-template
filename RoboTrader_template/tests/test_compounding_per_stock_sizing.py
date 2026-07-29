"""종목당 투자금액 복리 재산정 테스트 (2026-07-29).

배경:
    allocate_strategy_capital 이 기동 시 _strategy_investment_amounts[전략] =
    10,000,000/K 를 한 번 설정한 뒤 다시는 갱신되지 않았다. get_max_quantity 는
    min(per_stock, 전략 잔여 현금) 이므로 *총예산*은 손실을 반영하지만 *건당
    크기*는 첫날 값 그대로였다 = 부분적 복리 미작동.

    라이브 실측(2026-07-29, virtual_trading_records 재구성):
        book_pullback_ma20  자본비율 0.6280  ← 누적 −37.2%
        daytrading_3methods 자본비율 0.8875
    그럼에도 건당 매수는 각각 2,000,000원 그대로였다.

수정:
    기동 시 전략 원장 재구성 직후 per_stock 을 현재 자본 기준으로 재산정한다.
        per_stock = configured_base × (current_capital / initial_capital)
        current_capital = _strategy_balances + _strategy_invested (현금 + 포지션 원가)

검증 포인트:
- K분할 전략은 base = initial/K 이므로 결과가 current_capital/K 와 정확히 같다
  (사장님 지시 "현재 자본/K 로 매일 재산정"과 동일).
- yaml 튜닝 전략(deep_mr_dev20 = 2,000,000, base ≠ initial/K)의 상대 비율 보존.
- ★ 누적 축소 방지: 재산정은 항상 *최초 설정값*(_strategy_investment_base)에서
  계산한다. 어제 줄인 값에 또 비율을 곱하면 매일 기하급수적으로 쪼그라든다.
- 가드: initial<=0 / capital<=0 / base 미설정 / 원장 미활성 시 무변경.
"""
import asyncio
import pandas as pd
import pytest
from unittest.mock import Mock, patch


INITIAL = 10_000_000.0


def _make_vtm():
    with patch('core.virtual_trading_manager.setup_logger'):
        from core.virtual_trading_manager import VirtualTradingManager
        return VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)


def _set_capital(vtm, name, cash, invested=0.0):
    """원장 재구성 결과를 직접 주입 (재구성 산식은 별도 테스트가 검증)."""
    vtm._strategy_balances[name] = float(cash)
    vtm._strategy_invested[name] = float(invested)
    vtm._sync_aggregate_from_strategies()


# ---------------------------------------------------------------------------
# 1) 자본 비율 반영
# ---------------------------------------------------------------------------

class TestCapitalRatioScaling:
    def test_capital_down_35pct_gives_65pct_per_stock(self):
        """자본 −35% → per_stock 은 base 의 65%."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(2_000_000)

        _set_capital(vtm, "stratA", 6_500_000.0)
        vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(1_300_000)

    def test_k_split_equals_capital_over_k(self):
        """K분할 전략: base×(capital/initial) == capital/K (사장님 지시와 동일)."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("elder_ema_pullback", INITIAL, max_positions=20)

        _set_capital(vtm, "elder_ema_pullback", 3_252_809.80, invested=5_375_606.22)
        vtm.recalculate_investment_amounts()

        capital = 3_252_809.80 + 5_375_606.22
        assert vtm._strategy_investment_amounts["elder_ema_pullback"] == pytest.approx(
            capital / 20
        )

    def test_capital_increase_scales_up(self):
        """자본이 늘면 per_stock 도 늘어난다 (바닥값·상한 없음)."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)

        _set_capital(vtm, "stratA", 15_000_000.0)
        vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(3_000_000)

    def test_invested_counts_toward_capital(self):
        """자본 = 현금 + 포지션 원가. 현금만 보면 보유 중 전략이 과소 축소된다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)

        _set_capital(vtm, "stratA", 2_540.0, invested=8_416_101.23)
        vtm.recalculate_investment_amounts()

        capital = 2_540.0 + 8_416_101.23
        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(capital / 5)
        # 현금만 봤다면 508원이 됐을 것 — 그 값이면 안 된다
        assert vtm._strategy_investment_amounts["stratA"] > 1_000_000


# ---------------------------------------------------------------------------
# 2) ★ 누적 축소 방지 (가장 중요한 회귀)
# ---------------------------------------------------------------------------

class TestNoCompoundingShrink:
    def test_two_consecutive_calls_same_result(self):
        """같은 자본으로 두 번 재산정해도 결과가 같다 (base 에서 계산)."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        _set_capital(vtm, "stratA", 6_500_000.0)

        vtm.recalculate_investment_amounts()
        first = vtm._strategy_investment_amounts["stratA"]
        vtm.recalculate_investment_amounts()
        second = vtm._strategy_investment_amounts["stratA"]

        assert first == pytest.approx(1_300_000)
        assert second == pytest.approx(first)

    def test_ten_calls_do_not_shrink(self):
        """10회(=10일 기동) 반복해도 값이 유지된다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        _set_capital(vtm, "stratA", 6_500_000.0)

        for _ in range(10):
            vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(1_300_000)

    def test_base_is_preserved_not_mutated(self):
        """재산정은 base 를 건드리지 않는다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        _set_capital(vtm, "stratA", 6_500_000.0)
        vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_base["stratA"] == pytest.approx(2_000_000)

    def test_recovery_restores_full_size(self):
        """자본이 회복되면 per_stock 도 원래 크기로 돌아온다 (단조 축소 아님)."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)

        _set_capital(vtm, "stratA", 5_000_000.0)
        vtm.recalculate_investment_amounts()
        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(1_000_000)

        _set_capital(vtm, "stratA", INITIAL)
        vtm.recalculate_investment_amounts()
        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(2_000_000)


# ---------------------------------------------------------------------------
# 3) yaml 튜닝 전략 보존
# ---------------------------------------------------------------------------

class TestYamlTunedStrategy:
    def test_yaml_base_ratio_preserved(self):
        """deep_mr_dev20: yaml 2,000,000 (K=5 라 initial/K 와 우연히 같음)이 아닌
        임의 튜닝값에서도 상대 비율이 보존된다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("deep_mr_dev20", INITIAL, max_positions=5)
        vtm.set_strategy_investment_amount("deep_mr_dev20", 3_000_000.0)  # base ≠ initial/K

        _set_capital(vtm, "deep_mr_dev20", 5_199.05, invested=7_466_009.73)
        vtm.recalculate_investment_amounts()

        capital = 5_199.05 + 7_466_009.73
        expected = 3_000_000.0 * (capital / INITIAL)
        assert vtm._strategy_investment_amounts["deep_mr_dev20"] == pytest.approx(expected)
        # capital/K 를 직접 쓰면 yaml 튜닝값이 파괴된다 — 그 값이면 안 된다
        assert vtm._strategy_investment_amounts["deep_mr_dev20"] != pytest.approx(
            capital / 5
        )

    def test_yaml_override_after_allocate_updates_base(self):
        """allocate(K분할) → set(yaml) 순서일 때 base 는 yaml 값이어야 한다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("deep_mr_dev20", INITIAL, max_positions=5)
        vtm.set_strategy_investment_amount("deep_mr_dev20", 2_000_000.0)

        assert vtm._strategy_investment_base["deep_mr_dev20"] == pytest.approx(2_000_000)


# ---------------------------------------------------------------------------
# 4) 가드
# ---------------------------------------------------------------------------

class TestGuards:
    def test_ledger_inactive_is_noop(self):
        """원장 미활성(레거시/실전)이면 전체 no-op."""
        vtm = _make_vtm()
        before = dict(vtm._strategy_investment_amounts)
        vtm.recalculate_investment_amounts()
        assert vtm._strategy_investment_amounts == before
        assert vtm.virtual_investment_amount == 1_000_000  # 레거시 기본값 불변

    def test_zero_capital_skips_with_warning(self):
        """current_capital <= 0 이면 기존 값 유지 + WARNING."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        _set_capital(vtm, "stratA", 0.0)
        vtm.logger = Mock()

        vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(2_000_000)
        msgs = [str(c.args[0]) for c in vtm.logger.warning.call_args_list if c.args]
        assert any("stratA" in m for m in msgs), msgs

    def test_negative_capital_skips_with_warning(self):
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        _set_capital(vtm, "stratA", -1_000.0)
        vtm.logger = Mock()

        vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(2_000_000)
        assert vtm.logger.warning.called

    def test_zero_initial_skips_with_warning(self):
        """initial_capital <= 0 이면 0 나눗셈 대신 skip + WARNING."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        _set_capital(vtm, "stratA", 6_500_000.0)
        vtm._strategy_initial["stratA"] = 0.0
        vtm.logger = Mock()

        vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(2_000_000)
        assert vtm.logger.warning.called

    def test_strategy_without_base_is_skipped(self):
        """base 미설정(K 미지정·원장 재구성이 새로 만든 키)은 건너뛴다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("noK", INITIAL)   # max_positions 없음
        _set_capital(vtm, "noK", 5_000_000.0)

        vtm.recalculate_investment_amounts()

        assert "noK" not in vtm._strategy_investment_amounts
        # get_max_quantity 는 기존 virtual_investment_amount 폴백을 그대로 쓴다
        assert vtm.get_max_quantity(1_000.0, "noK") == 1_000

    def test_other_strategies_unaffected_by_one_skip(self):
        """한 전략이 skip 돼도 나머지는 정상 재산정된다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("bad", INITIAL, max_positions=5)
        vtm.allocate_strategy_capital("good", INITIAL, max_positions=5)
        _set_capital(vtm, "bad", 0.0)
        _set_capital(vtm, "good", 6_500_000.0)
        vtm.logger = Mock()

        vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_amounts["bad"] == pytest.approx(2_000_000)
        assert vtm._strategy_investment_amounts["good"] == pytest.approx(1_300_000)


# ---------------------------------------------------------------------------
# 5) 통합: get_max_quantity 가 재산정 값을 실제로 쓴다
# ---------------------------------------------------------------------------

class TestGetMaxQuantityUsesRecalculated:
    def test_quantity_shrinks_with_capital(self):
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        _set_capital(vtm, "stratA", 6_500_000.0)

        before = vtm.get_max_quantity(10_000.0, "stratA")
        vtm.recalculate_investment_amounts()
        after = vtm.get_max_quantity(10_000.0, "stratA")

        assert before == 200          # 2,000,000 / 10,000 (결함: 자본 무시)
        assert after == 130           # 1,300,000 / 10,000

    def test_quantity_still_capped_by_remaining_cash(self):
        """재산정 후에도 min(per_stock, 잔여 현금) 규칙은 유지."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        # 자본은 크지만(포지션에 묶임) 현금은 적음
        _set_capital(vtm, "stratA", 500_000.0, invested=8_000_000.0)
        vtm.recalculate_investment_amounts()

        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(1_700_000)
        assert vtm.get_max_quantity(10_000.0, "stratA") == 50   # 현금 500,000 한도


# ---------------------------------------------------------------------------
# 6) 기동 배선: state_restorer 가 원장 재구성 직후 호출한다
# ---------------------------------------------------------------------------

def _holdings_df():
    return pd.DataFrame([
        {
            'id': 1, 'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 100_000.0, 'buy_time': None,
            'strategy': 'stratA', 'target_profit_rate': None, 'stop_loss_rate': None,
        },
    ])


def _make_restorer(db, vtm):
    from bot.state_restorer import StateRestorer
    config = Mock()
    config.paper_trading = True
    restorer = StateRestorer(
        trading_manager=Mock(),
        db_manager=db,
        telegram_integration=Mock(),
        config=config,
        get_previous_close_callback=lambda code: 100_000.0,
        broker=None,
        fund_manager=None,
        virtual_trading_manager=vtm,
        strategies={},
    )

    async def _add(**kwargs):
        return True
    restorer.trading_manager.add_selected_stock.side_effect = _add
    stocks = {}

    def _get(code, strategy=None):
        return stocks.setdefault(code, Mock())
    restorer.trading_manager.get_trading_stock.side_effect = _get
    restorer.trading_manager._change_stock_state = Mock()
    restorer._resolve_owner_strategy = Mock(return_value=None)
    return restorer


class TestStateRestorerWiring:
    def test_recalc_called_after_reconstruction(self):
        """_reconstruct_strategy_ledger 가 재구성 *뒤에* 재산정을 호출한다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        order = []
        vtm.restore_strategy_ledger_from_records = Mock(
            side_effect=lambda *a, **k: order.append("restore"))
        vtm.recalculate_investment_amounts = Mock(
            side_effect=lambda *a, **k: order.append("recalc"))

        db = Mock()
        db.get_strategy_trade_sums.return_value = {}
        restorer = _make_restorer(db, vtm)
        restorer._reconstruct_strategy_ledger([])

        assert order == ["restore", "recalc"], order

    def test_flat_boot_path_recalculates(self):
        """보유 0건 기동에서도 재산정이 실행된다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        vtm.recalculate_investment_amounts = Mock()

        db = Mock()
        db.get_virtual_open_positions.return_value = pd.DataFrame()
        db.get_strategy_trade_sums.return_value = {}
        restorer = _make_restorer(db, vtm)
        asyncio.run(restorer._restore_holdings_from_db())

        vtm.recalculate_investment_amounts.assert_called_once()

    def test_holdings_path_recalculates(self):
        """보유 N건 기동에서도 재산정이 실행된다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)
        vtm.recalculate_investment_amounts = Mock()

        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df()
        db.get_strategy_trade_sums.return_value = {}
        restorer = _make_restorer(db, vtm)
        asyncio.run(restorer._restore_holdings_from_db())

        vtm.recalculate_investment_amounts.assert_called_once()

    def test_ledger_inactive_restorer_noop(self):
        """원장 미활성이면 state_restorer 도 재산정을 호출하지 않는다."""
        vtm = _make_vtm()   # 할당 없음
        vtm.recalculate_investment_amounts = Mock()

        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df()
        db.get_strategy_trade_sums.return_value = {}
        restorer = _make_restorer(db, vtm)
        asyncio.run(restorer._restore_holdings_from_db())

        vtm.recalculate_investment_amounts.assert_not_called()

    def test_end_to_end_per_stock_reflects_reconstructed_capital(self):
        """스텁 없이: 매매기록 → 재구성 → per_stock 이 실제로 줄어든다."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", INITIAL, max_positions=5)

        db = Mock()
        db.get_virtual_open_positions.return_value = pd.DataFrame()
        # 1,000만 매수 / 650만 매도 = 자본 약 −35%
        db.get_strategy_trade_sums.return_value = {
            'stratA': {'buy_gross': 10_000_000.0, 'sell_gross': 6_500_000.0}
        }
        restorer = _make_restorer(db, vtm)
        asyncio.run(restorer._restore_holdings_from_db())

        from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE
        capital = (INITIAL
                   - 10_000_000.0 * (1 + COMMISSION_RATE)
                   + 6_500_000.0 * (1 - COMMISSION_RATE - SECURITIES_TAX_RATE))
        assert vtm._strategy_investment_amounts["stratA"] == pytest.approx(capital / 5)
        assert vtm._strategy_investment_amounts["stratA"] < 1_400_000
