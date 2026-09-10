"""rs_leader — 미조정 기업행위(합병) 의심 종목 매수 배제 (2026-09-10 사장님 결정 (b)).

spec: docs/superpowers/specs/2026-09-10-rsleader-corp-action-exclusion-design.md §4 테스트 계약

이 파일이 못박는 것 (T번호는 스펙 §4 표):
  T1  live  + flagged 프레임 → match() None                     (배제가 실제로 작동)
  T2  shadow+ 같은 프레임 → «원래 튜플» + 로그 1줄               (shadow 가 룰을 안 바꾼다)
  T3  🔴 회귀 게이트 — off 면 후보·순서·score 완전 일치 + scan_series 호출 0회
  T4  live  + max_candidates=20 → 20건 «백필»(11건으로 줄지 않는다)
  T5  live  + _check_buy(flagged) → None + [신호없음] 로그        (on_tick 2차 방어)
  T6  🔴 대칭 단언 — 같은 flagged 프레임으로 «보유» 종목은 매도 신호가 그대로 난다
  T7  🔴 대칭 단언 — 82봉 창 «밖» 사건은 on_tick 이 «못» 잡는다   (사정거리 한계 못박기)
  T8  다른 어댑터(ma20·ma5·daytrading·elder)는 판정 불변          (범위 = rs_leader 만)
  T9  새 코드에 3 · 0.69 · 1.45 리터럴 없음                       (문턱 이중선언 금지)
  T10 모르는 mode 값 → off + WARNING (배선 쪽)
  T11 close 0/NaN · volume 컬럼 결측 → 예외 없음 · 배제 없음      (판정 불가 = 통과)
  T12 3봉 미만 정지런 · 밴드 «안» 비 → flag 0                     (재사용 함수 계약)

⚠️ `setup_logger` 는 `propagate=False` 라 caplog 가 안 잡힌다 —
   선례 `tests/test_candidate_sector_news_wiring.py:226` 대로 logger 를 MagicMock 으로 바꿔 본다.
"""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
import yaml

import config.constants as C
import strategies.rs_leader.corp_action_guard as guard
import strategies.rs_leader.screener as screener_mod
from strategies.base import SignalType
from strategies.rs_leader.screener import RSLeaderScreenerAdapter
from strategies.rs_leader.strategy import RSLeaderStrategy

ROOT = Path(__file__).resolve().parents[3]
SCAN_DATE = date(2026, 12, 31)   # 모든 합성 프레임의 마지막 날보다 뒤 (룩어헤드 컷 무해)


# ── 합성 프레임 ──────────────────────────────────────────────────────────────

def _frame(closes, volumes=None, code=None) -> pd.DataFrame:
    n = len(closes)
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000.0] * n if volumes is None else volumes,
    })
    if code is not None:
        # 라이브 경로에서는 `_prepare_frame` 이 찍어 준다(screener.py).
        df.attrs["stock_code"] = code
    return df


def _clean_series(n=131, base=10000.0, growth=0.5):
    """단조상승 — 절대상승추세 룰 통과, 기업행위 흔적 없음."""
    return list(np.linspace(base, base * (1.0 + growth), n)), [1000.0] * n


def _flagged_series(n=131, base=10000.0, growth=0.5, halt_at=40, halt_bars=4, jump=1.5):
    """정지런(거래량 0) 뒤 밴드 밖 점프 = 미조정 병합 의심 — 실측 패턴의 합성판.

    정지봉 종가는 «직전 종가로 동결»된다(collectors/corp_action_watch.py:81 실측).
    """
    closes, volumes = _clean_series(n=n, base=base, growth=growth)
    frozen = closes[halt_at - 1]
    for i in range(halt_at, halt_at + halt_bars):
        closes[i] = frozen
        volumes[i] = 0.0
    for i in range(halt_at + halt_bars, n):
        closes[i] = closes[i] * jump
    return closes, volumes


def _flagged_frame(code="001290", **kw):
    closes, volumes = _flagged_series(**kw)
    return _frame(closes, volumes, code=code)


def _clean_frame(code="079650", **kw):
    closes, volumes = _clean_series(**kw)
    return _frame(closes, volumes, code=code)


@pytest.fixture
def adapter():
    return RSLeaderScreenerAdapter()


@pytest.fixture
def mode(monkeypatch):
    """RS_LEADER_CORP_ACTION_MODE 를 «호출 시점»에 읽는지까지 함께 시험한다."""
    def _set(value, invalid=None):
        monkeypatch.setattr(C, "RS_LEADER_CORP_ACTION_MODE", value)
        monkeypatch.setattr(C, "RS_LEADER_CORP_ACTION_MODE_INVALID", invalid)
    return _set


@pytest.fixture
def spy(monkeypatch):
    """scan_series 호출 횟수 계수기 (T3 의 「호출 0회」용)."""
    calls = []
    real = guard.scan_series

    def _wrapped(stock_code, bars):
        calls.append(stock_code)
        return real(stock_code, bars)

    monkeypatch.setattr(guard, "scan_series", _wrapped)
    return calls


# ── T1 / T2 : match() 층 ─────────────────────────────────────────────────────

def test_t1_live_mode_match_returns_none(adapter, mode, monkeypatch):
    """T1 — live 면 flagged 종목은 후보가 되지 못한다."""
    monkeypatch.setattr(screener_mod, "logger", MagicMock())
    mode("live")
    assert adapter.match(_flagged_frame(), adapter.default_params()) is None


def test_t1_live_mode_keeps_clean_stock(adapter, mode):
    """대칭 단언 — 같은 live 모드에서 «깨끗한» 종목은 그대로 통과한다."""
    mode("live")
    res = adapter.match(_clean_frame(), adapter.default_params())
    assert res is not None and res[0] > 0


def test_t2_shadow_mode_returns_original_tuple_and_logs(adapter, mode, monkeypatch):
    """T2 — shadow 는 «룰을 바꾸지 않는다». 반환값은 off 와 완전히 같아야 한다."""
    mock_logger = MagicMock()
    monkeypatch.setattr(screener_mod, "logger", mock_logger)

    mode("off")
    baseline = adapter.match(_flagged_frame(), adapter.default_params())
    assert baseline is not None

    mode("shadow")
    shadowed = adapter.match(_flagged_frame(), adapter.default_params())
    assert shadowed == baseline

    msgs = [str(c.args) for c in mock_logger.warning.call_args_list]
    assert any("«안 함»" in m and "shadow" in m for m in msgs), msgs


def test_t2_live_log_line_format(adapter, mode, monkeypatch):
    """§3-3 로그 문구 고정 — 태그 `[rs_leader]` · 정지봉수 · 재개일 · 종가비 · mode."""
    mock_logger = MagicMock()
    monkeypatch.setattr(screener_mod, "logger", mock_logger)
    mode("live")
    adapter.match(_flagged_frame(code="001290"), adapter.default_params())

    assert mock_logger.warning.call_args_list
    fmt = mock_logger.warning.call_args_list[-1].args
    rendered = fmt[0] % tuple(fmt[1:]) if len(fmt) > 1 else str(fmt[0])
    assert rendered.startswith("[rs_leader] 001290: ")
    assert "미조정 병합 의심(정지 4봉 → 재개 2026-02-14, 종가비 " in rendered
    assert rendered.endswith("— 후보 제외 (mode=live)")


# ── T3 / T4 : scan() 층 (회귀 게이트 + 백필) ─────────────────────────────────

_N_STOCKS = 34
_N_FLAGGED = 9


def _synthetic_universe():
    """flagged 9 + clean 25. flagged 는 점프 때문에 score 가 «더 높다»
    ⇒ off 면 상위 20 에 9개가 들어가고, live 면 그 자리를 clean 이 백필해야 한다.

    ⚠️ 스펙 §4 T4 는 「25종목 중 9 flagged → 20건」이라고 적었으나 25−9=16 < 20 이라
       원리적으로 20건이 나올 수 없다. 백필을 시험하려면 clean 이 20 이상이어야 하므로
       유니버스를 34 로 키웠다(주장은 동일: «후보 수가 줄지 않는다»).
    """
    universe, frames, flagged = [], {}, set()
    for i in range(_N_STOCKS):
        code = f"S{i:02d}"
        growth = 0.30 + 0.01 * i
        if i < _N_FLAGGED:
            closes, volumes = _flagged_series(growth=growth)
            flagged.add(code)
        else:
            closes, volumes = _clean_series(growth=growth)
        frames[code] = _frame(closes, volumes)
        universe.append({"code": code, "name": code, "market": "KOSPI",
                         "market_cap": 1e12, "trading_value": 2e9})
    return universe, frames, flagged


class _StubAdapter(RSLeaderScreenerAdapter):
    """DB 대신 합성 프레임을 먹인다. `_prepare_frame`·`match`·정렬은 «진짜» 경로."""

    def __init__(self, universe, frames):
        super().__init__()
        self._universe = universe
        self._frames = frames

    def _load_universe(self, scan_date):
        return self._universe

    def _load_daily(self, code, scan_date):
        return self._frames[code].copy()


def _expected_ranking(frames, exclude=()):
    """변경 «전» 알고리즘 그대로 — 룰 통과분을 rs_ret(120일 수익률) 내림차순."""
    scored = []
    for code, df in frames.items():
        if code in exclude:
            continue
        close = df["close"].astype(float)
        rs = float(close.iloc[-1]) / float(close.iloc[-1 - 120]) - 1.0
        scored.append((rs, code))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored


def test_t3_mode_off_is_bit_identical_and_never_scans(mode, spy, monkeypatch):
    """T3 🔴 회귀 게이트 — off 면 후보·순서·score 가 «변경 전»과 완전 일치하고,
    탐지 함수는 «한 번도» 불리지 않는다(코드 진입 0)."""
    monkeypatch.setattr(screener_mod, "logger", MagicMock())
    universe, frames, flagged = _synthetic_universe()
    mode("off")

    out = _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    expected = _expected_ranking(frames)[:20]

    assert [c.code for c in out] == [code for _, code in expected]
    assert [round(c.score, 12) for c in out] == [round(rs, 12) for rs, _ in expected]
    # flagged 종목이 off 에서는 «그대로» 후보에 남아 있어야 한다(스위치가 진짜 off).
    assert flagged & {c.code for c in out}
    assert spy == [], f"mode=off 인데 scan_series 가 {len(spy)}회 불렸다"


def test_t4_live_backfills_to_full_candidate_count(mode, monkeypatch):
    """T4 — 배제는 정렬·topK «앞»이라 후보 수가 줄지 않는다(20 → 20)."""
    monkeypatch.setattr(screener_mod, "logger", MagicMock())
    universe, frames, flagged = _synthetic_universe()

    mode("live")
    out = _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    codes = [c.code for c in out]

    assert len(codes) == 20
    assert not (flagged & set(codes)), f"flagged 가 후보에 남았다: {flagged & set(codes)}"
    assert codes == [code for _, code in _expected_ranking(frames, exclude=flagged)[:20]]


def test_t4_scan_line_prints_flagged_and_kept(mode, monkeypatch):
    """§3-3 — 스캔당 1줄에 flagged 와 kept 를 «둘 다» 찍는다.
    (건수만 찍으면 「배제 0건」과 「스캔이 안 돌았다」가 구별이 안 된다.)"""
    mock_logger = MagicMock()
    monkeypatch.setattr(screener_mod, "logger", mock_logger)
    universe, frames, flagged = _synthetic_universe()

    mode("live")
    _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})

    lines = []
    for call in mock_logger.info.call_args_list:
        fmt = call.args
        lines.append(fmt[0] % tuple(fmt[1:]) if len(fmt) > 1 else str(fmt[0]))
    scan_lines = [ln for ln in lines if ln.startswith("[rs-corp-action] ")]
    assert len(scan_lines) == 1, lines
    ln = scan_lines[0]
    assert "mode=live" in ln
    assert f"universe={_N_STOCKS}" in ln
    assert f"evaluated={_N_STOCKS}" in ln
    assert f"flagged={_N_FLAGGED}" in ln
    assert f"kept={_N_STOCKS - _N_FLAGGED}" in ln
    assert "codes=" in ln
    for code in flagged:
        assert code in ln.split("codes=", 1)[1]


def test_scan_line_absent_when_off(mode, monkeypatch):
    """대칭 단언 — off 면 계기 줄이 «없다»(발효일을 로그로 끊을 수 있다)."""
    mock_logger = MagicMock()
    monkeypatch.setattr(screener_mod, "logger", mock_logger)
    universe, frames, _ = _synthetic_universe()
    mode("off")
    _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    assert not any("[rs-corp-action]" in str(c.args) for c in mock_logger.info.call_args_list)


# ── T5 / T6 / T7 : on_tick 층 ────────────────────────────────────────────────

def _load_config():
    return yaml.safe_load(
        (ROOT / "strategies" / "rs_leader" / "config.yaml").read_text(encoding="utf-8"))


def _strategy(monkeypatch, market_open=True):
    monkeypatch.setattr(
        "strategies.rs_leader.strategy.MarketHours.is_market_open",
        staticmethod(lambda market="KRX": market_open),
    )
    s = RSLeaderStrategy(config=_load_config())
    s.on_init(None, None, None)
    s.logger = MagicMock()
    return s


def test_t5_live_check_buy_blocked_with_log(mode, monkeypatch):
    """T5 — on_tick 2차 방어. 스크리너를 안 거친 종목이 들어와도 막힌다
    (실측 전례: 스크리너가 제외한 003350 에 on_tick 이 매수 시그널을 냈다)."""
    s = _strategy(monkeypatch)
    mode("live")
    closes, volumes = _flagged_series()
    assert s._check_buy("001290", _frame(closes, volumes)) is None
    msgs = [str(c.args) for c in s.logger.warning.call_args_list]
    assert any("[신호없음] 001290" in m and "진입 제외" in m and "mode=live" in m for m in msgs), msgs


def test_t5_off_and_shadow_do_not_block_check_buy(mode, monkeypatch):
    """대칭 단언 — off/shadow 는 «같은» 프레임에서 매수 시그널을 그대로 낸다."""
    closes, volumes = _flagged_series()
    for m in ("off", "shadow"):
        s = _strategy(monkeypatch)
        mode(m)
        sig = s._check_buy("001290", _frame(closes, volumes))
        assert sig is not None and sig.signal_type == SignalType.BUY, m


def test_t6_held_stock_still_sells_on_flagged_frame(mode, monkeypatch):
    """T6 🔴 청산 룰 불변 — 배제 대상 프레임이어도 «보유» 종목의 매도 신호는 그대로 난다.
    (§2 Q7-1 「기존 보유 종목의 청산 룰은 건드리지 않는다」의 기계 단언)"""
    s = _strategy(monkeypatch)
    mode("live")
    closes, volumes = _flagged_series()
    closes[-1] = float(np.mean(closes[-21:-1])) * 0.9   # MA20 하향이탈 → ma_break
    s.positions["001290"] = {"quantity": 10, "entry_price": closes[-1], "entry_time": None}

    sig = s.generate_signal("001290", _frame(closes, volumes), timeframe="daily")
    assert sig is not None and sig.signal_type == SignalType.SELL
    assert sig.metadata.get("exit_reason") == "ma_break"


def test_t7_event_outside_82bar_window_is_not_blocked(mode, monkeypatch, adapter):
    """T7 🔴 사정거리 한계를 «못박는다» — 「on_tick 도 막았다」를 「전부 막았다」로 읽지 말 것.

    같은 사건, 다른 창:
      · 스크리너 130봉 프레임 → 잡는다 (1차 방어)
      · on_tick  82봉 프레임 → «못» 잡는다 (사건이 창 밖 — §2 Q3 실측 003350 유형)
    """
    monkeypatch.setattr(screener_mod, "logger", MagicMock())
    closes, volumes = _flagged_series(halt_at=10, halt_bars=4, jump=1.6)
    mode("live")

    # 1차: 130봉 창 «안» → 배제된다
    df130 = _frame(closes, volumes, code="003350")
    assert adapter.match(df130, adapter.default_params()) is None

    # 2차: 82봉 창 «밖»(사건은 index 10~14, 창 시작은 index 49) → 막지 못한다
    s = _strategy(monkeypatch)
    df82 = _frame(closes[-82:], volumes[-82:])
    sig = s._check_buy("003350", df82)
    assert sig is not None and sig.signal_type == SignalType.BUY


# ── T8 : 범위 (다른 전략 불변) ───────────────────────────────────────────────

def test_t8_other_adapters_unaffected(mode, spy):
    """T8 — 범위는 rs_leader «하나». 다른 어댑터는 mode 를 보지도 않는다."""
    from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter
    from strategies.book_pullback_ma5.screener import BookPullbackMa5ScreenerAdapter
    from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter
    from strategies.elder_ema_pullback.screener import ElderEmaPullbackScreenerAdapter

    closes, volumes = _flagged_series(n=170)
    df = _frame(closes, volumes, code="001290")

    for cls in (BookPullbackMa20ScreenerAdapter, BookPullbackMa5ScreenerAdapter,
                Daytrading3MethodsBreakoutScreenerAdapter, ElderEmaPullbackScreenerAdapter):
        a = cls()
        mode("off")
        base = a.match(df.copy(), a.default_params())
        mode("live")
        assert a.match(df.copy(), a.default_params()) == base, cls.__name__
    assert spy == [], f"다른 어댑터가 scan_series 를 {len(spy)}회 불렀다"


# ── T9 : 문턱 이중선언 금지 ──────────────────────────────────────────────────

def test_t9_no_duplicated_thresholds_in_new_code():
    """T9 — 임계·밴드는 `collectors/corp_action_watch` 단일 소스. 새 코드에 리터럴 금지.

    (「한 규칙을 두 곳에 적으면 한 곳만 고쳐진다」 — 기존 상수를 재사용만 한다.)
    """
    targets = [
        ROOT / "strategies" / "rs_leader" / "corp_action_guard.py",
        ROOT / "strategies" / "rs_leader" / "screener.py",
        ROOT / "strategies" / "rs_leader" / "strategy.py",
    ]
    for p in targets:
        src = p.read_text(encoding="utf-8")
        assert "0.69" not in src, p.name
        assert "1.45" not in src, p.name
        assert "_HALT_MIN_BARS =" not in src, p.name
        assert "_NORMAL_BAND" not in src.replace("corp_action_watch", ""), p.name

    # 가드 모듈은 «자기 문턱을 하나도 갖지 않는다»(모듈 전역 숫자 상수 0개).
    nums = {k: v for k, v in vars(guard).items()
            if not k.startswith("__") and isinstance(v, (int, float)) and not isinstance(v, bool)}
    assert nums == {}, nums
    assert "corp_action_watch" in (ROOT / "strategies" / "rs_leader" /
                                   "corp_action_guard.py").read_text(encoding="utf-8")


# ── T10 : 모르는 mode 값 (배선) ──────────────────────────────────────────────

def test_t10_invalid_mode_warns_and_behaves_as_off(mode, spy, monkeypatch):
    """T10 — `RS_LEADER_CORP_ACTION_MODE="banana"` → off 로 동작 + WARNING 1줄.
    (config.constants 가 이미 off 로 낮추고 원문을 …_INVALID 에 보관한다.)"""
    mock_logger = MagicMock()
    monkeypatch.setattr(screener_mod, "logger", mock_logger)
    universe, frames, flagged = _synthetic_universe()
    mode("off", invalid="banana")

    out = _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    assert flagged & {c.code for c in out}          # off 로 동작 = 배제 없음
    assert spy == []
    msgs = []
    for call in mock_logger.warning.call_args_list:
        fmt = call.args
        msgs.append(fmt[0] % tuple(fmt[1:]) if len(fmt) > 1 else str(fmt[0]))
    assert any("banana" in m and "모르는 값" in m and "off" in m for m in msgs), msgs


# ── T11 / T12 : 가드 함수 계약 ───────────────────────────────────────────────

def test_t11_corrupt_frames_never_raise_and_never_exclude(mode):
    """T11 — 「판정 불가 = 통과」(`utils/data_sanity.py:76-84` 규약).

    손상 데이터를 «근거»로 종목을 배제하지 않는다 — 배제의 근거는 항상 관측된 사건이다.
    """
    mode("live")
    n = 131
    closes, volumes = _clean_series(n=n)

    # (a) 종가에 0 과 NaN 이 섞였다
    bad = list(closes)
    bad[30] = 0.0
    bad[31] = float("nan")
    assert guard.detect("A", _frame(bad, volumes)) is None

    # (b) volume 컬럼 자체가 없다
    no_vol = _frame(closes, volumes).drop(columns=["volume"])
    assert guard.detect("A", no_vol) is None

    # (c) volume 이 NaN — 「거래정지인지 모른다」를 「거래정지다」로 접지 않는다
    nan_vol = [float("nan")] * n
    assert guard.detect("A", _frame(closes, nan_vol)) is None

    # (d) 빈 프레임 · None
    assert guard.detect("A", pd.DataFrame()) is None
    assert guard.detect("A", None) is None


def test_t12_guard_contract_short_halt_and_in_band(mode):
    """T12 — 재사용 함수의 계약: 정지런 3봉 «미만» 또는 밴드 «안» 이면 flag 0.

    (진짜 급등은 정지런이 없어 원리적으로 안 걸린다 — §2 Q5 위양성 「구조」 논거 1.)
    """
    # 정지 2봉 뒤 5배 점프 → 정지런 부족으로 미탐
    assert guard.detect("A", _flagged_frame(halt_bars=2, jump=5.0)) is None
    # 정지 6봉 뒤 밴드 «안»(1.4배) → 미탐 (014990 유형: 값이 고쳐지면 자동 해제)
    assert guard.detect("A", _flagged_frame(halt_bars=6, jump=1.4)) is None
    # 대칭 단언 — 같은 정지 6봉인데 1.5배면 잡힌다
    assert guard.detect("A", _flagged_frame(halt_bars=6, jump=1.5)) is not None


def test_guard_describe_format():
    """§3-3 문구의 가운데 토막 — 정지봉수 · 재개일 · 종가비."""
    hit = guard.detect("001290", _flagged_frame(halt_bars=4))
    assert hit is not None
    text = guard.describe(hit)
    assert text.startswith("미조정 병합 의심(정지 4봉 → 재개 ")
    assert "종가비 " in text and text.endswith(")")
