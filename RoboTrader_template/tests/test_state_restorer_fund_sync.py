"""StateRestorer → FundManager 원장 재동기화 테스트 (2026-07-29).

배경(라이브 로그 실측):
    07:40:12  initializer._initialize_fund_manager 가
              update_total_funds(vtm.get_virtual_balance()) 호출 →
              이 시점 vtm 집계는 allocate_strategy_capital 직후의 80,000,000
    07:40:25  state_restorer 가 restore_strategy_ledger_from_records 로
              전략 현금을 매매기록에서 재구성 → vtm 집계 34,892,123 (정확)
    →         fund_manager 재동기화 없음 = 결함.
              "가용자금 51,832,290원"(=80,000,000−28,167,710)이 찍히지만
              실제 전략 현금 합계는 34,892,123원 (약 1,694만원 과대표시).

검증 포인트:
- 재구성 성공 직후 fund_manager.total_funds = ledger_cash + reserved + invested
  이고 available_funds == ledger_cash
- 정합성 등식 total == available + reserved + invested 보존
- invested_funds 는 절대 건드리지 않는다 (vtm 의 수수료 포함 기준 혼입 방지 —
  f22e16c 설계: fund_manager.invested_funds 는 순수 매수원가)
- ledger_cash 가 무효(None/0 이하)면 skip + WARNING
- 레거시(전략 원장 비활성)면 no-op
- 재동기화는 _log_fund_sync_summary 보다 먼저 실행되어 요약 로그가 교정값 출력
"""
import asyncio
import pandas as pd
import pytest
from unittest.mock import Mock, patch


# 라이브 실측값 (2026-07-29 07:40)
LEDGER_CASH = 34_892_123.0
INVESTED = 28_167_710.0          # = 830주 × 33,937원
INIT_TOTAL = 80_000_000.0        # 8전략 × 10M (allocate_strategy_capital 직후)
STALE_AVAILABLE = 51_832_290.0   # = 80,000,000 − 28,167,710 (결함 시 로그값)
EXPECTED_TOTAL = 63_059_833.0    # = 34,892,123 + 28,167,710


def _make_vtm():
    with patch('core.virtual_trading_manager.setup_logger'):
        from core.virtual_trading_manager import VirtualTradingManager
        return VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)


def _make_fm(initial_total=INIT_TOTAL):
    from core.fund_manager import FundManager
    fm = FundManager(initial_funds=0)
    fm.update_total_funds(initial_total)   # initializer._initialize_fund_manager 재현
    return fm


def _holdings_df():
    """단일 보유: 830주 @33,937원 = 28,167,710원 (라이브 invested 와 동일)."""
    return pd.DataFrame([
        {
            'id': 1, 'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 830, 'buy_price': 33_937.0, 'buy_time': None,
            'strategy': 'stratA', 'target_profit_rate': None, 'stop_loss_rate': None,
        },
    ])


def _wire_trading_manager(restorer):
    async def _add(**kwargs):
        return True
    restorer.trading_manager.add_selected_stock.side_effect = _add

    stocks = {}

    def _get(code, strategy=None):
        return stocks.setdefault(code, Mock())
    restorer.trading_manager.get_trading_stock.side_effect = _get
    restorer.trading_manager._change_stock_state = Mock()
    return stocks


def _make_restorer(db, vtm, fm):
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
        fund_manager=fm,
        virtual_trading_manager=vtm,
        strategies={},
    )
    _wire_trading_manager(restorer)
    restorer._resolve_owner_strategy = Mock(return_value=None)
    return restorer


def _stub_reconstruction(vtm, balances):
    """restore_strategy_ledger_from_records 를 재구성 결과로 대체.

    실제 재구성 산식(cash = initial − buy*(1+c) + sell*(1−c−t))은
    test_state_restorer_ledger.py 가 이미 검증한다. 여기서는 재구성 *결과*가
    fund_manager 로 전파되는지만 본다 → 라이브 실측 합계를 그대로 주입.
    """
    def _side_effect(initial_per_strategy, trade_sums, open_positions):
        vtm._strategy_balances = dict(balances)
        # vtm 의 invested 는 수수료 포함 기준 (fund_manager 와 기준이 다름)
        vtm._strategy_invested = {'stratA': INVESTED * 1.00015}
        vtm._sync_aggregate_from_strategies()
    vtm.restore_strategy_ledger_from_records = Mock(side_effect=_side_effect)


def _run_restore(vtm, fm, balances=None, allocate=True):
    """라이브 기동 시퀀스 재현 후 _restore_holdings_from_db 실행."""
    if allocate:
        for i in range(8):
            vtm.allocate_strategy_capital(f"strat{i}" if i else "stratA", 10_000_000)
    db = Mock()
    db.get_virtual_open_positions.return_value = _holdings_df()
    db.get_strategy_trade_sums.return_value = {}
    restorer = _make_restorer(db, vtm, fm)
    if balances is not None:
        _stub_reconstruction(vtm, balances)
    asyncio.run(restorer._restore_holdings_from_db())
    return restorer


# ---------------------------------------------------------------------------
# 1) 핵심: 재구성 결과가 fund_manager 로 전파된다
# ---------------------------------------------------------------------------

class TestFundManagerResync:
    def test_total_and_available_match_ledger(self):
        """total = ledger_cash + invested, available = ledger_cash (라이브 실측)."""
        vtm = _make_vtm()
        fm = _make_fm()
        _run_restore(vtm, fm, balances={'stratA': LEDGER_CASH})

        assert fm.invested_funds == pytest.approx(INVESTED)
        assert fm.reserved_funds == pytest.approx(0.0)
        assert fm.total_funds == pytest.approx(EXPECTED_TOTAL)
        assert fm.available_funds == pytest.approx(LEDGER_CASH)
        # 결함 시의 과대표시 값이 남아있으면 안 된다
        assert fm.available_funds != pytest.approx(STALE_AVAILABLE)

    def test_consistency_equation_preserved(self):
        """total == available + reserved + invested."""
        vtm = _make_vtm()
        fm = _make_fm()
        _run_restore(vtm, fm, balances={'stratA': LEDGER_CASH})

        assert fm.total_funds == pytest.approx(
            fm.available_funds + fm.reserved_funds + fm.invested_funds
        )

    def test_reserved_included_in_total(self):
        """reserved 가 있어도 available == ledger_cash 이고 등식 보존."""
        vtm = _make_vtm()
        fm = _make_fm()
        # 기동 직후 미체결 예약이 남아있는 상황 재현
        assert fm.reserve_funds("ORD1", 1_000_000.0) is True
        _run_restore(vtm, fm, balances={'stratA': LEDGER_CASH})

        assert fm.reserved_funds == pytest.approx(1_000_000.0)
        assert fm.available_funds == pytest.approx(LEDGER_CASH)
        assert fm.total_funds == pytest.approx(
            LEDGER_CASH + 1_000_000.0 + INVESTED
        )
        assert fm.total_funds == pytest.approx(
            fm.available_funds + fm.reserved_funds + fm.invested_funds
        )

    def test_invested_not_overwritten_by_vtm_basis(self):
        """invested_funds 는 vtm 의 수수료 포함 기준으로 덮이면 안 된다 (f22e16c 회귀)."""
        vtm = _make_vtm()
        fm = _make_fm()
        _run_restore(vtm, fm, balances={'stratA': LEDGER_CASH})

        vtm_invested = sum(vtm._strategy_invested.values())
        assert vtm_invested != pytest.approx(INVESTED)   # 기준이 다름을 확인
        assert fm.invested_funds == pytest.approx(INVESTED)  # 순수 매수원가 유지


# ---------------------------------------------------------------------------
# 2) 가드
# ---------------------------------------------------------------------------

class TestResyncGuards:
    def test_skip_when_ledger_cash_not_positive(self):
        """ledger_cash <= 0 이면 장부를 건드리지 않고 WARNING."""
        vtm = _make_vtm()
        fm = _make_fm()
        with patch('bot.state_restorer.logger') as mock_logger:
            _run_restore(vtm, fm, balances={'stratA': -5.0})

        assert fm.total_funds == pytest.approx(INIT_TOTAL)
        assert fm.available_funds == pytest.approx(STALE_AVAILABLE)
        assert fm.invested_funds == pytest.approx(INVESTED)
        msgs = [str(c.args[0]) for c in mock_logger.warning.call_args_list if c.args]
        assert any("재동기화 스킵" in m for m in msgs), msgs

    def test_legacy_ledger_inactive_is_noop(self):
        """전략 원장 비활성(레거시/단일전략/실전)이면 기존 동작 그대로."""
        vtm = _make_vtm()
        fm = _make_fm()
        _run_restore(vtm, fm, balances=None, allocate=False)

        assert fm.total_funds == pytest.approx(INIT_TOTAL)
        assert fm.available_funds == pytest.approx(STALE_AVAILABLE)
        assert fm.invested_funds == pytest.approx(INVESTED)

    def test_no_fund_manager_does_not_raise(self):
        """fund_manager 가 None 이어도 복원이 예외 없이 끝난다."""
        vtm = _make_vtm()
        _run_restore(vtm, None, balances={'stratA': LEDGER_CASH})
        assert vtm.get_virtual_balance() == pytest.approx(LEDGER_CASH)

    def test_skip_when_reconstruction_raises(self):
        """재구성이 예외로 실패하면 동기화하지 않는다."""
        vtm = _make_vtm()
        fm = _make_fm()
        for i in range(8):
            vtm.allocate_strategy_capital(f"strat{i}" if i else "stratA", 10_000_000)
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df()
        db.get_strategy_trade_sums.return_value = {}
        restorer = _make_restorer(db, vtm, fm)
        vtm.restore_strategy_ledger_from_records = Mock(
            side_effect=RuntimeError("boom"))

        asyncio.run(restorer._restore_holdings_from_db())

        assert fm.total_funds == pytest.approx(INIT_TOTAL)
        assert fm.available_funds == pytest.approx(STALE_AVAILABLE)


# ---------------------------------------------------------------------------
# 3) flat boot (보유 0건 기동) — F-1
# ---------------------------------------------------------------------------
# 조기 return(`if holdings.empty: return`)이 원장 재구성 블록까지 건너뛰면
# allocate_strategy_capital 이 쓴 8×10M 이 그대로 확정되어 누적손익이
# fund_manager·vtm 양쪽에서 통째로 소멸한다. 세션 로그 100개 중 40개가
# 진짜 flat boot("[가상매매] 보유 종목 없음", 최근 2026-06-10)이므로 드문 경로가
# 아니다. 아래 sums 는 실현손실 −5,053,250 을 재현한다(원장 현금 74,946,750).
FLAT_BUY_GROSS = 64_926_511.0
FLAT_SELL_GROSS = 60_000_000.0
FLAT_LEDGER_CASH = 74_946_750.0   # = 80,000,000 − 5,053,250 (±1원)


def _flat_boot_db(trade_sums):
    db = Mock()
    db.get_virtual_open_positions.return_value = pd.DataFrame()  # 보유 0건
    db.get_strategy_trade_sums.return_value = trade_sums
    return db


class TestFlatBoot:
    def test_ledger_reconstructed_and_fund_manager_synced(self):
        """보유 0건이어도 원장 재구성 + FundManager 동기화가 실행된다."""
        from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE
        vtm = _make_vtm()
        fm = _make_fm()
        for i in range(8):
            vtm.allocate_strategy_capital(f"strat{i}" if i else "stratA", 10_000_000)
        assert vtm.get_virtual_balance() == pytest.approx(INIT_TOTAL)

        db = _flat_boot_db({
            'stratA': {'buy_gross': FLAT_BUY_GROSS, 'sell_gross': FLAT_SELL_GROSS},
        })
        restorer = _make_restorer(db, vtm, fm)

        asyncio.run(restorer._restore_holdings_from_db())

        db.get_strategy_trade_sums.assert_called_once()

        expected_cash = (
            INIT_TOTAL
            - FLAT_BUY_GROSS * (1.0 + COMMISSION_RATE)
            + FLAT_SELL_GROSS * (1.0 - COMMISSION_RATE - SECURITIES_TAX_RATE)
        )
        # 원장: 매매기록만으로 flat 상태(현금만, invested 0) 재구성
        assert vtm.get_virtual_balance() == pytest.approx(expected_cash)
        assert vtm.get_virtual_balance() == pytest.approx(FLAT_LEDGER_CASH, abs=1.0)

        # FundManager: 누적손익이 승계되어야 한다
        assert fm.invested_funds == pytest.approx(0.0)
        assert fm.reserved_funds == pytest.approx(0.0)
        assert fm.total_funds == pytest.approx(FLAT_LEDGER_CASH, abs=1.0)
        assert fm.available_funds == pytest.approx(FLAT_LEDGER_CASH, abs=1.0)
        assert fm.total_funds == pytest.approx(
            fm.available_funds + fm.reserved_funds + fm.invested_funds
        )
        # 손익 소멸 회귀: 8×10M 이 그대로 남아있으면 안 된다
        assert fm.total_funds != pytest.approx(INIT_TOTAL)

    def test_flat_boot_legacy_is_noop(self):
        """레거시(원장 비활성) flat boot: 재구성 미호출, 장부 불변."""
        vtm = _make_vtm()   # allocate 없음
        fm = _make_fm()
        db = _flat_boot_db({})
        db.get_strategy_trade_sums = Mock()
        restorer = _make_restorer(db, vtm, fm)

        asyncio.run(restorer._restore_holdings_from_db())

        db.get_strategy_trade_sums.assert_not_called()
        assert fm.total_funds == pytest.approx(INIT_TOTAL)
        assert fm.available_funds == pytest.approx(INIT_TOTAL)

    def test_flat_boot_keeps_no_holdings_log(self):
        """운영자 신호인 '[가상매매] 보유 종목 없음' INFO 는 유지."""
        vtm = _make_vtm()
        fm = _make_fm()
        for i in range(8):
            vtm.allocate_strategy_capital(f"strat{i}" if i else "stratA", 10_000_000)
        db = _flat_boot_db({
            'stratA': {'buy_gross': FLAT_BUY_GROSS, 'sell_gross': FLAT_SELL_GROSS},
        })
        restorer = _make_restorer(db, vtm, fm)

        with patch('bot.state_restorer.logger') as mock_logger:
            asyncio.run(restorer._restore_holdings_from_db())

        msgs = [str(c.args[0]) for c in mock_logger.info.call_args_list if c.args]
        assert any("보유 종목 없음" in m for m in msgs), msgs

    def test_flat_boot_does_not_run_position_summaries(self):
        """범위 가드: 조기 return 이 건너뛰던 포지션 요약들은 여전히 미실행."""
        vtm = _make_vtm()
        fm = _make_fm()
        for i in range(8):
            vtm.allocate_strategy_capital(f"strat{i}" if i else "stratA", 10_000_000)
        db = _flat_boot_db({
            'stratA': {'buy_gross': FLAT_BUY_GROSS, 'sell_gross': FLAT_SELL_GROSS},
        })
        restorer = _make_restorer(db, vtm, fm)
        restorer._log_fund_sync_summary = Mock()
        restorer._log_stale_position_summary = Mock()
        restorer._sync_strategy_positions = Mock()

        asyncio.run(restorer._restore_holdings_from_db())

        restorer._log_fund_sync_summary.assert_not_called()
        restorer._log_stale_position_summary.assert_not_called()
        restorer._sync_strategy_positions.assert_not_called()


# ---------------------------------------------------------------------------
# 4) 순서: 재동기화가 요약 로그보다 먼저
# ---------------------------------------------------------------------------

class TestResyncOrdering:
    def test_summary_log_sees_corrected_values(self):
        vtm = _make_vtm()
        fm = _make_fm()
        for i in range(8):
            vtm.allocate_strategy_capital(f"strat{i}" if i else "stratA", 10_000_000)
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df()
        db.get_strategy_trade_sums.return_value = {}
        restorer = _make_restorer(db, vtm, fm)
        _stub_reconstruction(vtm, {'stratA': LEDGER_CASH})

        seen = {}

        def _capture(restored_count, total_invested, mode):
            seen['total'] = fm.total_funds
            seen['available'] = fm.available_funds
        restorer._log_fund_sync_summary = Mock(side_effect=_capture)

        asyncio.run(restorer._restore_holdings_from_db())

        assert seen['total'] == pytest.approx(EXPECTED_TOTAL)
        assert seen['available'] == pytest.approx(LEDGER_CASH)
