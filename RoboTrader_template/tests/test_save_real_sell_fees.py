"""save_real_sell 의 profit_loss 가 수수료·세금을 반영하는지 회귀.

배경 (사전-실전 감사 #14, 2026-06-24):
  save_real_sell 이 profit_loss = (price - buy_price) * quantity 로 gross(수수료
  무시) 저장 → 실거래 손익 과대계상. 전량 체결 FundManager 경로는 매수/매도
  수수료 + 증권세를 차감하는데 DB 기록만 gross 였다. (현재 real_trading_records.
  profit_loss 를 읽는 리포팅은 없어 잠재였으나, 실테이블 기반 리더보드 도입 전
  교정.)

검증: 매수원가=매도가일 때 gross 손익 0 이지만 수수료/세금 차감으로 음수.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _repo_with_mock_conn(avg_buy_price):
    from db.repositories.trading import TradingRepository
    repo = TradingRepository(db_path=None, real_table_name="real_trading_records")

    cursor = MagicMock()
    cursor.fetchone.return_value = (avg_buy_price,)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    cm = MagicMock()
    cm.__enter__.return_value = conn
    cm.__exit__.return_value = False
    repo._get_connection = MagicMock(return_value=cm)
    return repo, cursor


def _insert_params(cursor):
    """cursor.execute 호출 중 INSERT 의 params 튜플 반환."""
    for call in cursor.execute.call_args_list:
        sql = call[0][0]
        if "INSERT INTO" in sql:
            return call[0][1]
    raise AssertionError("INSERT 호출을 찾지 못함")


def test_save_real_sell_profit_loss_includes_fees():
    repo, cursor = _repo_with_mock_conn(avg_buy_price=10_000.0)

    ok = repo.save_real_sell(
        stock_code="005930", stock_name="삼성전자",
        price=10_000.0, quantity=10, strategy="elder", reason="테스트",
    )
    assert ok is True

    params = _insert_params(cursor)
    # params: (code, name, qty, price, ts, strategy, reason, profit_loss, profit_rate, buy_record_id, created_at)
    profit_loss = params[7]
    profit_rate = params[8]
    # gross = 0, 수수료/세금 차감 → 음수
    assert profit_loss < 0, f"수수료/세금 차감으로 음수여야 함, got {profit_loss}"
    assert profit_rate < 0
