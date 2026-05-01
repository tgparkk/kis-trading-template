"""
테스트 환경용 외부 모듈 Mock
============================
psycopg2, telegram, websockets 등 설치되지 않은 모듈을 Mock합니다.
각 테스트 파일 최상단에서 import하세요:
    import tests._mock_modules  # noqa: F401
"""
import sys
import types
from unittest.mock import MagicMock


def _ensure_module(name, attrs=None):
    """모듈이 없으면 Mock 모듈 등록"""
    if name not in sys.modules:
        mod = types.ModuleType(name)
        if attrs:
            for k, v in attrs.items():
                setattr(mod, k, v)
        sys.modules[name] = mod
    return sys.modules[name]


# psycopg2 — only mock when not actually installed
try:
    import psycopg2  # noqa: F401
    import psycopg2.pool  # noqa: F401
    import psycopg2.extensions  # noqa: F401
except ImportError:
    _ensure_module('psycopg2')
    _ensure_module('psycopg2.pool')
    _ensure_module('psycopg2.extensions')

# telegram
_tg = _ensure_module('telegram', {
    'Bot': MagicMock,
    'Update': MagicMock,
    'InlineKeyboardButton': MagicMock,
    'InlineKeyboardMarkup': MagicMock,
    'ReplyKeyboardMarkup': MagicMock,
    'KeyboardButton': MagicMock,
})

_tg_error = _ensure_module('telegram.error', {
    'TelegramError': type('TelegramError', (Exception,), {}),
})

_tg_request = _ensure_module('telegram.request', {
    'HTTPXRequest': MagicMock,
})

_mock_context_types = MagicMock()
_mock_context_types.DEFAULT_TYPE = MagicMock()

_tg_ext = _ensure_module('telegram.ext', {
    'Application': MagicMock,
    'ApplicationBuilder': MagicMock,
    'CommandHandler': MagicMock,
    'CallbackQueryHandler': MagicMock,
    'MessageHandler': MagicMock,
    'ContextTypes': _mock_context_types,
    'filters': MagicMock(),
})

_ensure_module('telegram.constants')

# websockets
_ensure_module('websockets')
_ensure_module('websockets.client')

# yaml / dotenv (may or may not be installed)
_ensure_module('yaml', {'safe_load': lambda x: {}, 'dump': lambda *a, **kw: ''})
_ensure_module('dotenv', {'load_dotenv': lambda *a, **kw: None, 'find_dotenv': lambda: ''})
