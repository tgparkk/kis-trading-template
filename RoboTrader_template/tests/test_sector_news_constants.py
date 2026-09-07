import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config.constants as C  # noqa: E402


def test_resolve_mode_defaults_to_shadow():
    assert C.resolve_sector_news_mode(None) == ("shadow", None)
    assert C.resolve_sector_news_mode("") == ("shadow", None)
    assert C.resolve_sector_news_mode("  ") == ("shadow", None)


def test_resolve_mode_accepts_case_and_whitespace():
    assert C.resolve_sector_news_mode(" LIVE ") == ("live", None)
    assert C.resolve_sector_news_mode("Off") == ("off", None)


def test_resolve_mode_invalid_falls_to_off_and_reports_raw():
    assert C.resolve_sector_news_mode("on") == ("off", "on")


def test_module_constants_defaults():
    assert C.SECTOR_NEWS_BOOST_MODES == ("off", "shadow", "live")
    assert C.SECTOR_NEWS_BOOST_MODE in C.SECTOR_NEWS_BOOST_MODES
    assert C.SECTOR_NEWS_MAX_SHIFT == 3 and C.SECTOR_NEWS_MIN_ABS == 0.2 and C.SECTOR_NEWS_STALE_MINUTES == 60
    assert C.SECTOR_NEWS_EXCLUDE_STRATEGIES == frozenset()
