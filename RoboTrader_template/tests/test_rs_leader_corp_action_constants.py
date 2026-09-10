"""RS_LEADER_CORP_ACTION_MODE 상수 계약 (T10).

선례 `tests/test_sector_news_constants.py` 와 «같은 형식» —
`resolve_sector_news_mode` 규약(빈 값→기본, 모르는 값→off + 원문 반환)을 그대로 따른다.
spec: docs/superpowers/specs/2026-09-10-rsleader-corp-action-exclusion-design.md §3-2
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config.constants as C  # noqa: E402


def test_resolve_mode_defaults_to_shadow():
    """기본값은 shadow — 머지 시점엔 라이브 룰이 «안» 바뀐다(§3-2)."""
    assert C.resolve_rs_leader_corp_action_mode(None) == ("shadow", None)
    assert C.resolve_rs_leader_corp_action_mode("") == ("shadow", None)
    assert C.resolve_rs_leader_corp_action_mode("  ") == ("shadow", None)


def test_resolve_mode_accepts_case_and_whitespace():
    assert C.resolve_rs_leader_corp_action_mode(" LIVE ") == ("live", None)
    assert C.resolve_rs_leader_corp_action_mode("Off") == ("off", None)
    assert C.resolve_rs_leader_corp_action_mode("shadow") == ("shadow", None)


def test_resolve_mode_invalid_falls_to_off_and_reports_raw():
    """T10 — 모르는 값은 «가장 안전한» off 로 낮추고 원문을 돌려준다(호출자가 WARNING)."""
    assert C.resolve_rs_leader_corp_action_mode("banana") == ("off", "banana")
    assert C.resolve_rs_leader_corp_action_mode("on") == ("off", "on")


def test_module_constants_defaults():
    assert C.RS_LEADER_CORP_ACTION_MODES == ("off", "shadow", "live")
    assert C.RS_LEADER_CORP_ACTION_MODE in C.RS_LEADER_CORP_ACTION_MODES
    assert hasattr(C, "RS_LEADER_CORP_ACTION_MODE_INVALID")
