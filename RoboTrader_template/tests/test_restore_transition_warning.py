"""복원 경로의 SELECTED → POSITIONED 가 매일 기동 로그에 [비정상 상태전이] 를 도배했다.

배경(2026-08-14 EOD): ``_VALID_TRANSITIONS[SELECTED]`` 는 ``[BUY_PENDING,
COMPLETED, FAILED]`` 로 POSITIONED 를 허용하지 않는다. 그런데 DB 복원 경로
(bot/state_restorer.py)는 ``add_selected_stock`` 으로 SELECTED 를 만든 직후
곧바로 POSITIONED 로 전이시키므로 **복원된 포지션 전부**가 기동 로그에 WARNING
한 줄씩을 남긴다(2026-08-14 부팅 로그 48줄 = 복원 포지션 48건). 순수 소음이다.

🔴 **허용 목록에 POSITIONED 를 더하는 수정은 금지**다. 그러면 정상 매매 경로에서
BUY_PENDING 을 건너뛴 채 POSITIONED 에 도달하는 경우 — 주문추적을 빠뜨린 체결,
즉 **이 가드가 존재하는 이유 그 자체** — 까지 함께 침묵한다. 그래서 «복원
호출자가 스스로를 선언»하는 방식(keyword-only ``restoring=True``)으로 그
호출에서만 경고 «출력»을 건너뛴다. 전이 자체와 ``_VALID_TRANSITIONS`` 는 불변.

⚠️ 이 프로젝트에는 «기본값이 falsy 인 keyword-only 가드 인자를 호출자가 안 넘겨
가드가 죽는» 결함 계열이 반복돼 왔다(2026-08-11 ``max_capital_pct``). 여기선
극성이 반대(기본 False = 경고 = 안전)라 배선이 끊겨도 «시끄러워질 뿐»이지만,
그래도 인자가 «존재하는지»가 아니라 **복원 호출열이 실제로 그 값을 끝까지
넘기는지**를 진짜 호출 사슬(state_restorer → TradingStockManager →
StockStateManager)로 확인하고, 방출된 로그 레코드 자체를 단언한다.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401,E402

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

# tests/bot/ 가 tests 디렉토리 경유로 ``bot`` 을 가려버리므로(테스트 전용
# 하위 패키지), 프로젝트 루트를 sys.path 맨 앞으로 되돌린 뒤 import 한다
# — tests/test_state_restorer.py 와 동일한 관례.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.state_restorer import StateRestorer  # noqa: E402
from core.models import StockState, TradingStock  # noqa: E402
from core.trading.stock_state_manager import StockStateManager  # noqa: E402
from core.trading_stock_manager import TradingStockManager  # noqa: E402

ABNORMAL_MARK = "[비정상 상태전이]"


class _RecordingHandler(logging.Handler):
    """StockStateManager 로거에 붙여 실제 방출된 레코드를 모은다.

    utils.logger.setup_logger 는 ``propagate = False`` 로 두므로 caplog(루트
    핸들러) 로는 잡히지 않는다. 로거 팩토리를 가짜로 바꾸면 «출력이 실제로
    일어났는지»가 아니라 «가짜 객체가 호출됐는지»를 보게 되므로, 진짜 로거에
    핸들러를 하나 더 붙여 방출 자체를 관측한다.
    """

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def abnormal_messages(self):
        return [r.getMessage() for r in self.records
                if ABNORMAL_MARK in r.getMessage()]


@pytest.fixture
def state_mgr_and_log():
    mgr = StockStateManager()
    handler = _RecordingHandler()
    mgr.logger.addHandler(handler)
    try:
        yield mgr, handler
    finally:
        mgr.logger.removeHandler(handler)


def _selected_stock(code="005930", name="삼성전자", owner="elder"):
    ts = TradingStock(
        stock_code=code,
        stock_name=name,
        state=StockState.SELECTED,
        selected_time=datetime.now(),
        selection_reason="테스트",
    )
    ts.owner_strategy_name = owner
    return ts


# ============================================================================
# 1) StockStateManager 단위 — 억제는 «복원 선언» 이 있을 때만
# ============================================================================

def test_restore_transition_emits_no_abnormal_warning(state_mgr_and_log):
    """복원 선언(restoring=True)이 붙은 SELECTED → POSITIONED 는 경고를 내지 않는다."""
    mgr, handler = state_mgr_and_log
    mgr.register_stock(_selected_stock())

    mgr.change_stock_state(
        "005930", StockState.POSITIONED, "DB 복원: 10주", strategy="elder",
        restoring=True,
    )

    assert handler.abnormal_messages() == [], (
        f"복원 경로인데 [비정상 상태전이] 경고가 남았다: {handler.abnormal_messages()}"
    )


def test_normal_path_transition_still_warns(state_mgr_and_log):
    """대칭 단언(핵심): 복원 선언이 «없는» 같은 전이는 여전히 경고해야 한다.

    이 전이는 BUY_PENDING(=주문추적)을 건너뛴 체결을 뜻하므로 정상 매매
    경로에서는 진짜 이상 신호다. ``_VALID_TRANSITIONS`` 를 넓혀 «고치면»
    이 단언이 깨진다 — 그것이 이 테스트의 목적이다.
    """
    mgr, handler = state_mgr_and_log
    mgr.register_stock(_selected_stock())

    mgr.change_stock_state(
        "005930", StockState.POSITIONED, "체결 완료", strategy="elder",
    )

    msgs = handler.abnormal_messages()
    assert len(msgs) == 1, f"정상 매매 경로의 비정상 전이 경고가 사라졌다: {msgs}"
    assert "005930" in msgs[0]


@pytest.mark.parametrize("restoring", [True, False])
def test_transition_itself_is_unchanged(state_mgr_and_log, restoring):
    """경고 억제는 «출력»만 건너뛴다 — 상태 전이·인덱스는 두 경우 모두 동일하다."""
    mgr, _handler = state_mgr_and_log
    mgr.register_stock(_selected_stock())

    kwargs = {"restoring": True} if restoring else {}
    mgr.change_stock_state(
        "005930", StockState.POSITIONED, "전이", strategy="elder", **kwargs
    )

    ts = mgr.get_trading_stock("005930", strategy="elder")
    assert ts.state == StockState.POSITIONED
    codes = {s.stock_code for s in mgr.get_stocks_by_state(StockState.POSITIONED)}
    assert codes == {"005930"}
    assert mgr.get_stocks_by_state(StockState.SELECTED) == []


def test_unrelated_abnormal_transition_still_warns(state_mgr_and_log):
    """복원과 무관한 진짜 비정상 전이(COMPLETED → SELL_CANDIDATE)는 계속 경고한다."""
    mgr, handler = state_mgr_and_log
    ts = _selected_stock(code="000660", name="SK하이닉스", owner="ma5")
    ts.state = StockState.COMPLETED
    mgr.register_stock(ts)

    mgr.change_stock_state(
        "000660", StockState.SELL_CANDIDATE, "이상", strategy="ma5",
    )

    msgs = handler.abnormal_messages()
    assert len(msgs) == 1, f"무관한 비정상 전이까지 침묵했다: {msgs}"
    assert "000660" in msgs[0]


# ============================================================================
# 2) 진짜 호출 사슬 — state_restorer 가 실제로 그 값을 끝까지 넘기는가
# ============================================================================

def _restorer_wired_to(state_mgr):
    """StateRestorer 를 «진짜» TradingStockManager._change_stock_state +
    «진짜» StockStateManager 에 결선한다.

    ``_change_stock_state`` 를 Mock 이나 손수 만든 람다로 두면 인자 전달을
    테스트가 스스로 발명하게 되어(순환 논리) 배선이 끊겨도 통과한다. 그래서
    래퍼 «함수 자체»를 스텁 인스턴스에 바인딩해, 시그니처와 전달까지 프로덕션
    코드가 책임지게 한다.
    """
    trading_manager = MagicMock()
    trading_manager._state_manager = state_mgr
    trading_manager.add_selected_stock = AsyncMock(return_value=True)
    trading_manager._change_stock_state = (
        TradingStockManager._change_stock_state.__get__(trading_manager)
    )

    db_manager = MagicMock()
    db_manager.get_virtual_open_positions = MagicMock(return_value=pd.DataFrame())

    config = MagicMock()
    config.paper_trading = True

    broker = MagicMock()
    broker.get_pending_orders.return_value = []

    telegram = AsyncMock()
    telegram.notify_urgent_signal = AsyncMock()

    return StateRestorer(
        trading_manager=trading_manager,
        db_manager=db_manager,
        telegram_integration=telegram,
        config=config,
        get_previous_close_callback=MagicMock(return_value=50000.0),
        broker=broker,
    ), trading_manager, db_manager


@pytest.mark.asyncio
async def test_paper_restore_chain_emits_no_abnormal_warning(state_mgr_and_log):
    """진짜 복원 호출열(state_restorer → TradingStockManager → StockStateManager)이
    끝까지 복원 선언을 전달해 경고가 0줄이어야 한다. 그리고 상태는 POSITIONED 다."""
    state_mgr, handler = state_mgr_and_log
    restorer, trading_manager, db_manager = _restorer_wired_to(state_mgr)

    ts = _selected_stock()
    state_mgr.register_stock(ts)
    trading_manager.get_trading_stock = MagicMock(return_value=ts)

    db_manager.get_virtual_open_positions.return_value = pd.DataFrame([{
        'stock_code': '005930',
        'stock_name': '삼성전자',
        'quantity': 10,
        'buy_price': 70000.0,
        'target_profit_rate': 0.05,
        'stop_loss_rate': 0.03,
    }])

    with patch('bot.state_restorer.DatabaseConnection'):
        await restorer._restore_holdings_from_db()

    assert handler.abnormal_messages() == [], (
        "복원 호출열이 restoring 을 끝까지 넘기지 못했다(가드 배선 끊김): "
        f"{handler.abnormal_messages()}"
    )
    assert ts.state == StockState.POSITIONED, "경고만 죽이고 전이가 사라졌다"


@pytest.mark.asyncio
async def test_real_account_restore_chain_emits_no_abnormal_warning(state_mgr_and_log):
    """실계좌 복원(_restore_holdings_from_real_account)도 같은 전이를 하므로
    같은 선언이 필요하다. 페이퍼 운영 중엔 잠자는 경로라 배선이 끊겨도 티가
    안 나므로 여기서 못박는다."""
    from tests.broker_contract import make_account_balance, make_holding

    state_mgr, handler = state_mgr_and_log
    restorer, trading_manager, db_manager = _restorer_wired_to(state_mgr)
    restorer.config.paper_trading = False

    ts = _selected_stock()
    state_mgr.register_stock(ts)
    trading_manager.get_trading_stock = MagicMock(return_value=ts)

    db_manager.get_real_open_positions.return_value = pd.DataFrame()
    restorer.broker.get_account_balance.return_value = make_account_balance(total_stocks=1)
    restorer.broker.get_holdings.return_value = [make_holding(
        stock_code='005930', stock_name='삼성전자', quantity=10, avg_price=70000.0,
    )]
    restorer._detect_holdings_mismatch = AsyncMock(return_value=[])
    restorer._sync_fund_manager_for_position = MagicMock(return_value=0.0)

    await restorer._restore_holdings_from_real_account()

    assert handler.abnormal_messages() == [], (
        "실계좌 복원 호출열이 restoring 을 넘기지 못했다: "
        f"{handler.abnormal_messages()}"
    )
    assert ts.state == StockState.POSITIONED
