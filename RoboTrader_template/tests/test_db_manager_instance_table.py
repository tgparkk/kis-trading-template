import config.settings as settings
from db.repositories.trading import TradingRepository


def test_repo_default_uses_settings_table(monkeypatch):
    # 기본(default) 인스턴스 → real_trading_records
    repo = TradingRepository()
    assert repo._real_table == settings.REAL_TRADING_TABLE == "real_trading_records"
