"""ledger8 — dt corp 가드 날짜별 모드 재현(⑮ · 2026-10-28) · match() 경로 가드 컨텍스트.

라이브 dt 가드는 스크리너 `scan()` 안에서만 `_ca_active=True` + `df.attrs["stock_code"]` 를 세팅한다
(`strategies/daytrading_3methods_breakout/screener.py:59-74`). 연구 원장이 `match()` 를 직접 부르면
가드는 구조적으로 꺼진다 → `livesignal8.dt_guarded_match` 가 연구 쪽에서 감싸 켠다(라이브 코드 무수정).
픽스처 = `tests/fixtures/dt_corp_action_368600_daily.csv`(DB 덤프 · 정지 24봉 → 10-22 재개 · 종가비 4.331).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from backtest.concept_axes.ledger8 import livesignal8 as LS8
from backtest.concept_axes.ledger8 import registry as R
import config.constants as CC
from strategies.daytrading_3methods_breakout import screener as dt_screener
from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter

ROOT = Path(__file__).resolve().parents[4]
FIXTURE_368600 = ROOT / "tests" / "fixtures" / "dt_corp_action_368600_daily.csv"
DAY = "daytrading_3methods_breakout"


def _frame_368600() -> pd.DataFrame:
    """10-26 까지 60봉(라이브 lookback) — 10-27 스캔이 본 프레임 꼴 · dt 룰 통과."""
    df = pd.read_csv(FIXTURE_368600, dtype={"date": str})
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] <= "2026-10-26"]
    return df.tail(Daytrading3MethodsBreakoutScreenerAdapter.lookback_days).reset_index(drop=True)


@pytest.fixture
def adapter():
    return Daytrading3MethodsBreakoutScreenerAdapter()


@pytest.fixture
def log(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr(dt_screener, "logger", m, raising=False)
    return m


# ── registry: 날짜별 모드 ─────────────────────────────────────────────────────

def test_dt_mode_by_date():
    assert R.DT_CORP_ACTION_LIVE_SINCE == date(2026, 10, 28)
    assert R.corp_action_mode_for(DAY, date(2026, 10, 27)) == "off"
    assert R.corp_action_mode_for(DAY, date(2026, 10, 28)) == "live"
    assert R.corp_action_mode_for(DAY, date(2026, 11, 2)) == "live"
    # rs 는 그대로 · 다른 전략은 None
    assert R.corp_action_mode_for("rs_leader", date(2026, 10, 27)) == "live"
    assert R.corp_action_mode_for("book_pullback_ma20", date(2026, 10, 28)) is None


# ── (a) 10-27 = off → 368600 통과 ─────────────────────────────────────────────

def test_a_before_live_since_368600_passes(adapter, log):
    df = _frame_368600()
    verdict, flagged = LS8.dt_guarded_match(adapter, "368600", df, adapter.default_params(), date(2026, 10, 27))
    assert verdict is not None, "off 날짜는 룰 판정 그대로(가드 발효 전 재현)"
    assert flagged == []
    assert log.warning.call_count == 0


# ── (b) 10-28 = live → 368600 제외 ────────────────────────────────────────────

def test_b_live_since_368600_excluded_and_flagged(adapter, log):
    df = _frame_368600()
    verdict, flagged = LS8.dt_guarded_match(adapter, "368600", df, adapter.default_params(), date(2026, 10, 28))
    assert verdict is None
    assert flagged == ["368600"]
    msgs = [c.args[0] % tuple(c.args[1:]) for c in log.warning.call_args_list]
    assert msgs == ["[daytrading_3methods_breakout] 368600: 미조정 병합 의심(정지 24봉 → "
                    "재개 2026-10-22, 종가비 4.331) — 후보 제외 (mode=live)"]


# ── (c) 함정 고정: 상수만 live 로 바꾸고 _ca_active 를 안 켜면 조용히 통과 ──────────

def test_c_constant_patch_alone_is_silent_trap(adapter, monkeypatch, log):
    df = _frame_368600()
    df.attrs["stock_code"] = "368600"
    monkeypatch.setattr(CC, "DT_CORP_ACTION_MODE", "live")
    monkeypatch.setattr(CC, "DT_CORP_ACTION_MODE_INVALID", None)
    # 컨텍스트 없이 match() 직접 — 가드가 «안 돈다»(라이브 설계: scan() 안에서만)
    assert adapter.match(df, adapter.default_params()) is not None
    assert log.warning.call_count == 0
    # 같은 상수·같은 프레임이라도 컨텍스트를 켠 경로에서만 제외된다
    verdict, flagged = LS8.dt_guarded_match(adapter, "368600", df, adapter.default_params(), date(2026, 10, 28))
    assert verdict is None and flagged == ["368600"]


def test_context_restores_state_and_constants(adapter):
    before = (CC.DT_CORP_ACTION_MODE, CC.DT_CORP_ACTION_MODE_INVALID)
    df = _frame_368600()
    with LS8.dt_corp_guard(adapter, date(2026, 10, 28)) as flagged:
        assert adapter._ca_active is True and CC.DT_CORP_ACTION_MODE == "live"
        assert adapter.match(LS8.with_stock_code(df, "368600"), adapter.default_params()) is None
    assert flagged == ["368600"]
    assert getattr(adapter, "_ca_active", False) is False
    assert (CC.DT_CORP_ACTION_MODE, CC.DT_CORP_ACTION_MODE_INVALID) == before
    assert "stock_code" not in df.attrs, "호출자 프레임 attrs 는 건드리지 않는다"


def test_dt_guard_rejects_other_folders(adapter):
    with pytest.raises(ValueError):
        with LS8.dt_corp_guard(adapter, date(2026, 10, 28), folder="rs_leader"):
            pass


def test_live_buy_patches_sets_dt_constant_not_rs():
    rs_before = CC.RS_LEADER_CORP_ACTION_MODE
    s = object()
    with LS8.live_buy_patches(s, DAY, date(2026, 10, 27)):
        assert CC.DT_CORP_ACTION_MODE == "off" and CC.RS_LEADER_CORP_ACTION_MODE == rs_before
    with LS8.live_buy_patches(s, DAY, date(2026, 10, 28)):
        assert CC.DT_CORP_ACTION_MODE == "live" and CC.RS_LEADER_CORP_ACTION_MODE == rs_before
