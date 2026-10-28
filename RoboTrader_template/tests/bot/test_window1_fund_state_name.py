"""fund_state JSON 인스턴스 접미 (10-29 창구 묶음 A ⑫).

실측 10-28: 실전 인스턴스 15:4x 종료분 `fund_state_2026-10-28.json` 을 페이퍼 17:00 종료가 덮었다
(경로가 인스턴스 비분리). 실전(`KIS_INSTANCE_DIR` 설정 · instance_id != default) = 접미,
페이퍼(default) = 기존 이름 그대로(자동 닫기 스크립트가 그 이름을 복사).
"""


def test_paper_default_keeps_legacy_name():
    from bot.initializer import fund_state_file_name
    assert fund_state_file_name("2026-10-30", "default") == "fund_state_2026-10-30.json"


def test_real_instance_gets_suffix():
    from bot.initializer import fund_state_file_name
    assert fund_state_file_name("2026-10-30", "daytrading") == "fund_state_2026-10-30_daytrading.json"


def test_flush_uses_settings_instance_id(monkeypatch, tmp_path):
    """_flush_state_to_db 가 config.settings.INSTANCE_ID 를 읽어 파일명을 정한다."""
    from unittest.mock import Mock
    import bot.initializer as ini
    import config.settings as settings

    monkeypatch.setattr(settings, "INSTANCE_ID", "daytrading")
    monkeypatch.setattr(ini, "_fund_state_dir", lambda: tmp_path)
    bot = Mock()
    bot.trading_manager.trading_stocks = {}
    bot.fund_manager.total_funds = 5_000_000
    bot.fund_manager._daily_realized_loss = -45_956.0
    bot.fund_manager._daily_loss_date = "2026-10-30"
    init = ini.BotInitializer.__new__(ini.BotInitializer)
    init.bot = bot
    init.logger = Mock()
    init._flush_state_to_db()
    files = sorted(p.name for p in tmp_path.iterdir())
    assert len(files) == 1 and files[0].startswith("fund_state_") and files[0].endswith("_daytrading.json")

    monkeypatch.setattr(settings, "INSTANCE_ID", "default")
    for p in tmp_path.iterdir():
        p.unlink()
    init._flush_state_to_db()
    (name,) = [p.name for p in tmp_path.iterdir()]
    assert name.count("_") == 2 and not name.endswith("_daytrading.json")  # fund_state_YYYY-MM-DD.json
