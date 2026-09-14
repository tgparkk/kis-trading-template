"""실매매 최소 수정 집합 (2026-09-15) — TDD 회귀 고정.

지시서: `scratchpad/real_trading_audit_20260914/TASK_min_fix_set.md`
근거:   `docs/audit_2026-09-14_real_trading_switch.md` §6

원칙: **페이퍼 8전략 동작 0 변경**. 각 항목은 실전 인스턴스 모드
(`KIS_INSTANCE_DIR` 설정 / `INSTANCE_ID != "default"`)에서만 갈라지거나,
페이퍼가 애초에 도달하지 않는 실브로커 경로만 건드린다.
"""
import importlib
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# 공통 헬퍼
# =============================================================================
def _reload_settings(monkeypatch, instance_dir):
    """`KIS_INSTANCE_DIR` 을 바꾼 뒤 config.settings 를 재로딩해 돌려준다.

    `CONFIG_FILE` 은 import 시점 상수라, 「인스턴스 모드에서 어느 파일을 여는가」는
    재로딩 없이 관찰할 수 없다. 테스트 종료 시 원복은 호출자 책임(fixture 사용).
    """
    import config.settings as settings
    if instance_dir is None:
        monkeypatch.delenv("KIS_INSTANCE_DIR", raising=False)
    else:
        monkeypatch.setenv("KIS_INSTANCE_DIR", str(instance_dir))
    return importlib.reload(settings)


@pytest.fixture
def settings_env(monkeypatch):
    """config.settings 재로딩 테스트용 — 끝나면 env 원복 + 재재로딩."""
    import config.settings as settings
    yield settings
    monkeypatch.delenv("KIS_INSTANCE_DIR", raising=False)
    importlib.reload(settings)


def _capture_config_path(fn):
    """fn() 실행 중 `Path.exists()` 로 조회된 경로 목록을 돌려준다.

    파일을 만들지 않고 경로만 관찰하기 위한 장치다(실제 key.ini 를 워크트리에
    떨구지 않는다). 존재하지 않는다고 답하므로 호출부는 조기 반환한다.
    ⚠️ 패치값은 «함수» 여야 한다 — 클래스 인스턴스를 넣으면 디스크립터가 아니라
    바인딩이 안 되고, 호출부의 try/except 가 그 TypeError 를 삼켜 빈 목록이 된다.
    """
    seen = []

    def fake_exists(path_self):
        seen.append(Path(path_self))
        return False

    with patch.object(Path, "exists", fake_exists):
        fn()
    return seen


# =============================================================================
# A1 — core/telegram_integration.py: key.ini 하드코딩 → settings.CONFIG_FILE
# =============================================================================
class TestA1TelegramConfigPath:
    """P1-1: 실전 인스턴스가 «페이퍼 봇의» key.ini 를 읽어 텔레그램을 잘못 보내던 결함."""

    def _load(self):
        from core.telegram_integration import TelegramIntegration
        ti = TelegramIntegration.__new__(TelegramIntegration)
        ti.logger = MagicMock()
        return _capture_config_path(ti._load_telegram_config)

    def test_instance_mode_opens_instance_key_ini(self, settings_env, monkeypatch, tmp_path):
        inst = tmp_path / "instances" / "x"
        settings = _reload_settings(monkeypatch, inst)
        assert settings.INSTANCE_ID == "x"

        seen = self._load()
        assert seen, "key.ini 존재 검사가 한 번도 일어나지 않았다"
        assert seen[-1] == inst / "key.ini", (
            f"인스턴스 모드인데 {seen[-1]} 를 열었다 (기대: {inst / 'key.ini'})"
        )

    def test_default_mode_opens_repo_config_key_ini(self, settings_env, monkeypatch):
        settings = _reload_settings(monkeypatch, None)
        assert settings.INSTANCE_ID == "default"

        seen = self._load()
        assert seen, "key.ini 존재 검사가 한 번도 일어나지 않았다"
        assert seen[-1] == Path(settings.CONFIG_FILE)
        assert seen[-1].parent.name == "config" and seen[-1].name == "key.ini"


# =============================================================================
# A2 — api/kis_auth.py `_send_failure_telegram`: 동일 하드코딩
# =============================================================================
class TestA2AuthFailureTelegramConfigPath:
    """P1-1: 장애 알림도 같은 경로를 쓴다 — 인스턴스 봇의 경보가 엉뚱한 채팅방으로 갔다."""

    def _send(self):
        import api.kis_auth as kis_auth
        return _capture_config_path(lambda: kis_auth._send_failure_telegram("msg"))

    def test_instance_mode_opens_instance_key_ini(self, settings_env, monkeypatch, tmp_path):
        inst = tmp_path / "instances" / "y"
        _reload_settings(monkeypatch, inst)

        seen = self._send()
        assert seen, "key.ini 존재 검사가 한 번도 일어나지 않았다"
        assert seen[-1] == inst / "key.ini"

    def test_default_mode_opens_repo_config_key_ini(self, settings_env, monkeypatch):
        settings = _reload_settings(monkeypatch, None)

        seen = self._send()
        assert seen, "key.ini 존재 검사가 한 번도 일어나지 않았다"
        assert seen[-1] == Path(settings.CONFIG_FILE)


# =============================================================================
# A3 — bot/candidate_loader.py: 단일 전략 모드 owner 표기를 «폴더키» 로
# =============================================================================
class _FakeTradingManager:
    """add_selected_stock 이 실제로 받은 owner 를 기록하는 최소 대역.

    registry 키가 (code, owner) 라 「owner 표기가 갈리면 조회가 빈다」는 실제
    결함 구조를 그대로 재현한다(get_trading_stock 은 owner 완전일치만 반환).
    """

    def __init__(self):
        self.calls = []
        self._registry = {}

    async def add_selected_stock(self, stock_code, stock_name, selection_reason="",
                                 prev_close=0.0, owner_strategy=""):
        self.calls.append({"stock_code": stock_code, "owner_strategy": owner_strategy})
        ts = MagicMock()
        ts.stock_code = stock_code
        ts.strategy_name = None
        self._registry[(stock_code, owner_strategy)] = ts
        return True

    def get_trading_stock(self, stock_code, strategy=None):
        return self._registry.get((stock_code, strategy or ""))

    def get_stocks_by_state(self, state):
        return list(self._registry.values())


def _single_strategy_bot(folder_key, class_name):
    """단일 전략 봇 대역 — `strategies` dict 키는 폴더명, 인스턴스 `.name` 은 클래스명."""
    from core.candidate_selector import CandidateStock

    strategy_instance = MagicMock()
    strategy_instance.name = class_name

    bot = MagicMock()
    bot._candidates_loaded = False
    bot._candidate_load_retries = 0
    bot.liquidation_handler = None
    bot.config.strategy = None
    bot.strategy = strategy_instance
    bot.strategies = {folder_key: strategy_instance}
    bot.candidate_selector.load_from_screener.return_value = [
        CandidateStock(code="005930", name="삼성전자", market="KRX",
                       score=50.0, reason="테스트", prev_close=70000.0)
    ]
    bot.db_manager = None
    bot.trading_manager = _FakeTradingManager()
    return bot


class TestA3SingleStrategyOwnerKey:
    """P1-2: 단일 전략 모드가 owner 를 «클래스명» 으로 달아, 폴더키로 조회하는
    TradingContext 가 자기 후보를 못 찾아 무거래가 됐다."""

    @pytest.mark.asyncio
    async def test_owner_is_folder_key_not_class_name(self):
        from bot.candidate_loader import CandidateLoader

        bot = _single_strategy_bot("book_pullback_ma20", "BookPullbackMA20Strategy")
        await CandidateLoader(bot)._load_screener_candidates()

        assert bot.trading_manager.calls, "add_selected_stock 이 호출되지 않았다"
        owners = {c["owner_strategy"] for c in bot.trading_manager.calls}
        assert owners == {"book_pullback_ma20"}, (
            f"owner 가 폴더키가 아니다: {owners}"
        )

    @pytest.mark.asyncio
    async def test_context_with_folder_key_sees_the_candidate(self):
        """end-to-end 1건: 폴더키로 만든 TradingContext 가 그 종목을 돌려준다."""
        from bot.candidate_loader import CandidateLoader
        from core.trading_context import TradingContext

        bot = _single_strategy_bot("book_pullback_ma20", "BookPullbackMA20Strategy")
        await CandidateLoader(bot)._load_screener_candidates()

        ctx = TradingContext.__new__(TradingContext)
        ctx.logger = MagicMock()
        ctx._strategy_key = "book_pullback_ma20"
        ctx._trading_manager = bot.trading_manager

        codes = [s.stock_code for s in ctx.get_selected_stocks()]
        assert codes == ["005930"], f"폴더키 컨텍스트가 후보를 못 봤다: {codes}"

    @pytest.mark.asyncio
    async def test_no_strategies_dict_keeps_legacy_fallback(self):
        """`strategies` 가 비면 기존 폴백(클래스명 / "unknown") 유지 — 동작 변화 0."""
        from bot.candidate_loader import CandidateLoader

        bot = _single_strategy_bot("ignored", "BookPullbackMA20Strategy")
        bot.strategies = {}
        await CandidateLoader(bot)._load_screener_candidates()

        owners = {c["owner_strategy"] for c in bot.trading_manager.calls}
        assert owners == {"BookPullbackMA20Strategy"}

    @pytest.mark.asyncio
    async def test_multi_strategy_path_untouched(self):
        """전략 2개 이상이면 기존 다중 전략 경로로 그대로 빠진다(이번 수정 무관)."""
        from bot.candidate_loader import CandidateLoader

        bot = _single_strategy_bot("a", "A")
        bot.strategies = {"a": MagicMock(), "b": MagicMock()}
        loader = CandidateLoader(bot)
        with patch.object(loader, "_load_candidates_multi_strategy") as multi:
            async def _noop(*a, **k):
                return None
            multi.side_effect = _noop
            await loader._load_screener_candidates()
        assert multi.called, "다중 전략 경로가 안 탔다"
        assert not bot.trading_manager.calls
