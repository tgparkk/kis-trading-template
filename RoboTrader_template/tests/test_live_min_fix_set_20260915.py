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
