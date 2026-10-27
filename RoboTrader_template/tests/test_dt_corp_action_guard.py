"""daytrading_3methods_breakout 스크리너 — 미조정 기업행위(병합·분할) 의심 종목 제외 가드.

🔒 사장님 결정 2026-10-27 「㉯ 앞당겨 수정」(동결 예외 3번째 · 범위 최소).
배경: 10-27 실전 368600(09-30 주식병합 결정 → 24봉 거래정지 → 10-22 재개 · 일봉 미조정)이
dt 후보 2위로 매수 → 42분 뒤 손절. 같은 날 rs_leader 스크리너는 같은 가드로 제외했다.

가드 모듈은 rs_leader 것을 «재사용»한다(`strategies/rs_leader/corp_action_guard.py`) —
임계는 `collectors.corp_action_watch` 단일 소스. 모드만 dt 전용 env `DT_CORP_ACTION_MODE`.
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config.constants as C  # noqa: E402
from strategies.daytrading_3methods_breakout import screener as dt_screener  # noqa: E402
from strategies.daytrading_3methods_breakout.screener import (  # noqa: E402
    Daytrading3MethodsBreakoutScreenerAdapter,
)
from strategies.rs_leader import corp_action_guard as guard  # noqa: E402

FIXTURE_368600 = ROOT / "tests" / "fixtures" / "dt_corp_action_368600_daily.csv"


# ── 픽스처 ───────────────────────────────────────────────────────────────────

def _breakout_part(start_close=1000):
    """dt 룰이 통과하는 22봉(`tests/test_screener_daytrading.py::_breakout_df` 와 같은 꼴)."""
    closes = [start_close + (i % 5) * 20 for i in range(21)] + [start_close + 300]
    return pd.DataFrame({
        "open": [c - 5 for c in closes[:-1]] + [start_close + 250],
        "high": [start_close + 100] * 21 + [start_close + 320],
        "low": [c - 10 for c in closes],
        "close": closes,
        "volume": [1000] * 21 + [3000],
    })


def _frame(with_halt: bool) -> pd.DataFrame:
    """정상 5봉 + (정지 5봉 = 거래량 0 · 동결가) + 재개 점프(×4) 뒤 돌파 22봉."""
    pre = pd.DataFrame({"open": [250] * 5, "high": [255] * 5, "low": [245] * 5,
                        "close": [250] * 5, "volume": [1000] * 5})
    if with_halt:
        mid = pd.DataFrame({"open": [250] * 5, "high": [250] * 5, "low": [250] * 5,
                            "close": [250] * 5, "volume": [0] * 5})
    else:
        # 깨끗한 종목 — 거래 중 단계적 상승(정지런 없음 → 사건 아님)
        steps = [300, 400, 520, 680, 880]
        mid = pd.DataFrame({"open": steps, "high": steps, "low": steps,
                            "close": steps, "volume": [1000] * 5})
    df = pd.concat([pre, mid, _breakout_part()], ignore_index=True)
    df.insert(0, "date", pd.bdate_range("2026-08-03", periods=len(df)))
    return df


def _scan(frames, scan_date=None):
    """`scan()` 경로 — 유니버스/일봉 로더만 갈아 끼운다(DB 접근 0)."""
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    a._load_universe = lambda d: [
        {"code": code, "name": code, "market_cap": 1e11, "trading_value": 5e9}
        for code in frames
    ]

    def _load_daily(code, d):
        df = frames[code]
        df = df[df["date"].dt.date <= d]
        return df.tail(a.lookback_days).reset_index(drop=True)

    a._load_daily = _load_daily
    if scan_date is None:
        scan_date = max(f["date"].iloc[-1] for f in frames.values()).date()
    return [c.code for c in a.scan(scan_date, {})]


def _rendered(mock_calls):
    out = []
    for call in mock_calls:
        fmt = call.args
        out.append(fmt[0] % tuple(fmt[1:]) if len(fmt) > 1 else str(fmt[0]))
    return out


def _load_368600():
    df = pd.read_csv(FIXTURE_368600, dtype={"date": str})
    df["date"] = pd.to_datetime(df["date"])
    return df


@pytest.fixture
def mode(monkeypatch):
    def _set(value, invalid=None):
        monkeypatch.setattr(C, "DT_CORP_ACTION_MODE", value, raising=False)
        monkeypatch.setattr(C, "DT_CORP_ACTION_MODE_INVALID", invalid, raising=False)
    return _set


@pytest.fixture
def log(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr(dt_screener, "logger", m, raising=False)
    return m


@pytest.fixture
def spy(monkeypatch):
    calls = []
    real = guard.scan_series

    def _wrapped(stock_code, bars):
        calls.append(stock_code)
        return real(stock_code, bars)

    monkeypatch.setattr(guard, "scan_series", _wrapped)
    return calls


# ── ② DT_CORP_ACTION_MODE resolver 계약 ──────────────────────────────────────

def test_resolver_defaults_to_live():
    """기본 live — 사장님이 «즉시 발효»를 결정했다(rs 의 기본 shadow 와 다르다)."""
    assert C.resolve_dt_corp_action_mode(None) == ("live", None)
    assert C.resolve_dt_corp_action_mode("") == ("live", None)
    assert C.resolve_dt_corp_action_mode("  ") == ("live", None)


def test_resolver_accepts_case_and_whitespace():
    assert C.resolve_dt_corp_action_mode(" SHADOW ") == ("shadow", None)
    assert C.resolve_dt_corp_action_mode("Off") == ("off", None)
    assert C.resolve_dt_corp_action_mode("live") == ("live", None)


def test_resolver_invalid_falls_to_off_and_reports_raw():
    assert C.resolve_dt_corp_action_mode("banana") == ("off", "banana")
    assert C.resolve_dt_corp_action_mode("on") == ("off", "on")


def test_module_constants():
    assert C.DT_CORP_ACTION_MODES == ("off", "shadow", "live")
    assert C.DT_CORP_ACTION_MODE in C.DT_CORP_ACTION_MODES
    assert hasattr(C, "DT_CORP_ACTION_MODE_INVALID")


def test_guard_resolve_mode_prefix_reads_dt_and_default_stays_rs(monkeypatch, mode):
    """가드의 `resolve_mode` 일반화 — 인자 없으면 rs 그대로, "DT" 면 dt 상수."""
    monkeypatch.setattr(C, "RS_LEADER_CORP_ACTION_MODE", "shadow")
    monkeypatch.setattr(C, "RS_LEADER_CORP_ACTION_MODE_INVALID", None)
    mode("live")
    assert guard.resolve_mode() == ("shadow", None)
    assert guard.resolve_mode("DT") == ("live", None)
    mode("off", "banana")
    assert guard.resolve_mode("DT") == ("off", "banana")
    mode("weird")  # 모듈 값을 직접 이상하게 바꿔도 off 로 낮춘다
    assert guard.resolve_mode("DT") == ("off", "weird")
    msg = guard.invalid_mode_message("banana", prefix="DT")
    assert "DT_CORP_ACTION_MODE='banana'" in msg and "off" in msg


# ── ① 합성 일봉 — live 제외 · shadow 로그만 · off 통과 ──────────────────────

def test_synthetic_frame_has_event_and_rule_passes():
    """공허 테스트 방지 — 사건이 실제로 있고, 룰도 실제로 통과한다."""
    df = _frame(with_halt=True)
    assert guard.detect("SYN", df) is not None
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    assert a.match(df, a.default_params()) is not None
    assert guard.detect("CLN", _frame(with_halt=False)) is None


def test_live_excludes_flagged_and_logs_one_line(mode, log):
    mode("live")
    codes = _scan({"SYN": _frame(True), "CLN": _frame(False)})
    assert codes == ["CLN"]
    lines = [s for s in _rendered(log.warning.call_args_list) if "미조정" in s]
    assert len(lines) == 1
    assert lines[0].startswith("[daytrading_3methods_breakout] SYN: 미조정 병합 의심(정지 5봉 → 재개 ")
    assert lines[0].endswith("— 후보 제외 (mode=live)")


def test_shadow_logs_only_and_keeps_candidate(mode, log):
    mode("shadow")
    codes = _scan({"SYN": _frame(True), "CLN": _frame(False)})
    assert set(codes) == {"SYN", "CLN"}
    lines = [s for s in _rendered(log.warning.call_args_list) if "미조정" in s]
    assert len(lines) == 1
    assert lines[0].startswith("[daytrading_3methods_breakout] SYN: 미조정 병합 의심(")
    assert lines[0].endswith("— 후보 제외 «안 함»(mode=shadow)")


def test_off_passes_through_without_calling_guard(mode, log, spy):
    mode("off")
    codes = _scan({"SYN": _frame(True), "CLN": _frame(False)})
    assert set(codes) == {"SYN", "CLN"}
    assert spy == []
    assert not [s for s in _rendered(log.warning.call_args_list) if "미조정" in s]


def test_invalid_mode_is_off_with_warning(mode, log, spy):
    mode("off", "banana")
    codes = _scan({"SYN": _frame(True)})
    assert codes == ["SYN"]
    assert spy == []
    warns = _rendered(log.warning.call_args_list)
    assert any("DT_CORP_ACTION_MODE='banana'" in s for s in warns)


def test_scan_summary_line_lists_flagged_codes(mode, log):
    mode("live")
    _scan({"SYN": _frame(True), "CLN": _frame(False)})
    infos = [s for s in _rendered(log.info.call_args_list) if s.startswith("[dt-corp-action]")]
    assert len(infos) == 1
    assert "mode=live" in infos[0] and "flagged=1" in infos[0] and "codes=SYN" in infos[0]


def test_match_outside_scan_is_unchanged_even_in_live(mode, spy):
    """연구 러너(`backtest/concept_axes/*`)는 `match()` 를 직접 부른다 — 재현 불변."""
    mode("live")
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    df = _frame(True)
    assert a.match(df, a.default_params()) is not None
    assert spy == []


# ── ③ 368600 회귀 픽스처 (DB `kis_template` daily_prices 2026-06-01~10-26 덤프) ──

def test_368600_fixture_detect_event():
    hit = guard.detect("368600", _load_368600())
    assert hit is not None
    assert hit["resumption_date"] == "2026-10-22"
    assert hit["halt_last_date"] == "2026-10-21"
    assert hit["halt_bars"] == 24
    assert hit["direction"] == "merge"
    assert hit["prev_close"] == 956.0 and hit["resume_close"] == 4140.0
    assert hit["ratio"] == pytest.approx(4.331, abs=0.001)


def test_368600_fixture_60bar_frame_also_detects():
    """dt 스크리너 창(60봉)으로 잘라도 사건이 창 안에 있다."""
    df = _load_368600().tail(Daytrading3MethodsBreakoutScreenerAdapter.lookback_days)
    assert guard.detect("368600", df)["resumption_date"] == "2026-10-22"


def test_368600_scan_off_selects_live_excludes(mode, log):
    """10-26 장마감 데이터 기준 스캔: 가드 off 면 후보(=10-27 매수 경로) · live 면 제외."""
    frames = {"368600": _load_368600()}
    mode("off")
    assert _scan(frames, date(2026, 10, 26)) == ["368600"], "룰 통과 안 함 — 공허한 회귀 테스트"
    mode("live")
    assert _scan(frames, date(2026, 10, 26)) == []
    lines = [s for s in _rendered(log.warning.call_args_list) if "미조정" in s]
    assert lines == ["[daytrading_3methods_breakout] 368600: 미조정 병합 의심(정지 24봉 → "
                     "재개 2026-10-22, 종가비 4.331) — 후보 제외 (mode=live)"]
