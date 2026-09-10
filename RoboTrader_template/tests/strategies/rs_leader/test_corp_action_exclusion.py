"""rs_leader — 미조정 기업행위(합병) 의심 종목 매수 배제 (2026-09-10 사장님 결정 (b)).

spec: docs/superpowers/specs/2026-09-10-rsleader-corp-action-exclusion-design.md §4 테스트 계약
      (+ 「errata rev2」 절 — 코드리뷰 rev1 반영)

이 파일이 못박는 것 (T번호는 스펙 §4 표 · T13~T15 는 rev2 추가):
  T1  live  + flagged 프레임 → `scan()` 후보에서 빠진다             (배제가 실제로 작동)
  T2  shadow+ 같은 프레임 → «원래 후보» 그대로 + 로그 1줄            (shadow 가 룰을 안 바꾼다)
  T3  🔴 회귀 게이트 — off 면 후보·순서·score 완전 일치 + scan_series 호출 0회
  T4  live  + max_candidates=20 → 20건 «백필»(11건으로 줄지 않는다)
  T5  live  + _check_buy(flagged) → None + [신호없음] 로그          (on_tick 2차 방어)
  T6  🔴 대칭 단언 — 같은 flagged 프레임으로 «보유» 종목은 매도 신호가 그대로 난다
  T7  🔴 대칭 단언 — 82봉 창 «밖» 사건은 on_tick 이 «못» 잡는다     (사정거리 한계 못박기)
  T8  다른 어댑터(ma20·ma5·daytrading·elder)는 판정 불변            (범위 = rs_leader 만)
  T9  새 코드에 3 · 0.69 · 1.45 리터럴 없음                         (문턱 이중선언 금지)
  T10 모르는 mode 값 → off + WARNING (배선 쪽)
  T11 close 0/NaN · volume 컬럼 결측 → 예외 없음 · 배제 없음        (판정 불가 = 통과)
  T12 3봉 미만 정지런 · 밴드 «안» 비 → flag 0                       (재사용 함수 계약)
  T13 🔴 rev2 — `scan()` «밖»에서 `match()` 를 부르면 배제가 «안» 걸린다 + scan_series 0회
      (백테스트 러너 2본이 `match()` 를 직접 루프한다 — 연구 재현 오염 차단)
  T14 rev2 — `scan()` 중간 예외 뒤 재스캔해도 계기 줄이 «이중계수»되지 않는다
  T15 rev2 — `matched=` 는 모드와 무관하게 «불변», `kept` 는 실제 반환 수
      (shadow 로그를 발효 «전» 기준선으로 쓰려면 두 칸의 정의가 모드에 안 걸려야 한다)

⚠️ `setup_logger` 는 `propagate=False` 라 caplog 가 안 잡힌다 —
   선례 `tests/test_candidate_sector_news_wiring.py:226` 대로 logger 를 MagicMock 으로 바꿔 본다.
"""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import yaml

import config.constants as C
import strategies.rs_leader.corp_action_guard as guard
import strategies.rs_leader.screener as screener_mod
from strategies._rule_screener_base import RuleScreenerBase
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


def _prepend_halt(df: pd.DataFrame, halt_bars: int = 4, ratio: float = 2.0) -> pd.DataFrame:
    """어떤 프레임 «앞»에 정지런 + 밴드 밖 점프를 붙인다 (룰이 보는 꼬리는 그대로).

    T8 용 — 다른 전략 어댑터의 「룰이 실제로 통과하는」 프레임을 건드리지 않고
    기업행위 흔적만 심는다. 룰은 전부 trailing 창이라 앞에 붙이는 건 꼬리를 안 바꾼다.
    """
    first_close = float(df["close"].iloc[0])
    frozen = first_close / ratio          # 재개봉 종가비 = ratio (밴드 밖)
    head = pd.DataFrame({
        "date": pd.date_range(end=pd.Timestamp(df["date"].iloc[0]) - pd.Timedelta(days=1),
                              periods=halt_bars, freq="D"),
        "open": [frozen] * halt_bars, "high": [frozen] * halt_bars,
        "low": [frozen] * halt_bars, "close": [frozen] * halt_bars,
        "volume": [0.0] * halt_bars,
    })
    out = pd.concat([head, df], ignore_index=True)
    out.attrs["stock_code"] = df.attrs.get("stock_code", "TEST")
    return out


# ── 유니버스 / 스텁 어댑터 ───────────────────────────────────────────────────

_N_STOCKS = 34
_N_FLAGGED = 9


class _StubAdapter(RSLeaderScreenerAdapter):
    """DB 대신 합성 프레임을 먹인다. `scan`·`_prepare_frame`·`match`·정렬은 «진짜» 경로."""

    def __init__(self, universe, frames, boom_at=None):
        super().__init__()
        self._universe = universe
        self._frames = frames
        self._boom_at = boom_at       # n번째 `_load_daily` 에서 일부러 터뜨린다(T14)
        self._loads = 0

    def _load_universe(self, scan_date):
        return self._universe

    def _load_daily(self, code, scan_date):
        self._loads += 1
        if self._boom_at is not None and self._loads == self._boom_at:
            raise RuntimeError("합성 장애 — 스캔 중간 예외")
        return self._frames[code].copy()


def _synthetic_universe():
    """flagged 9 + clean 25. flagged 는 점프 때문에 score 가 «더 높다»
    ⇒ off 면 상위 20 에 9개가 들어가고, live 면 그 자리를 clean 이 백필해야 한다.

    ⚠️ 스펙 §4 T4 는 「25종목 중 9 flagged → 20건」이라고 적었으나 25−9=16 < 20 이라
       원리적으로 20건이 나올 수 없다. 백필을 시험하려면 clean 이 20 이상이어야 하므로
       유니버스를 34 로 키웠다(주장은 동일: «후보 수가 줄지 않는다»). → 스펙 errata rev2
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


def _scan_one(frame, code="001290", max_candidates=10):
    """단일 종목 유니버스로 «진짜» `scan()` 경로를 탄다.

    🔑 `match()` 직접 호출로는 배제를 시험할 수 없다 — rev2 부터 배제는 `scan()` 안에서만
       돈다(T13). 스크리너 층 계약은 전부 이 헬퍼를 거친다.
    """
    uni = [{"code": code, "name": code, "market": "KOSPI",
            "market_cap": 1e12, "trading_value": 2e9}]
    return _StubAdapter(uni, {code: frame}).scan(SCAN_DATE, {"max_candidates": max_candidates})


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


def _rendered(mock_calls):
    out = []
    for call in mock_calls:
        fmt = call.args
        out.append(fmt[0] % tuple(fmt[1:]) if len(fmt) > 1 else str(fmt[0]))
    return out


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
    """scan_series 호출 횟수 계수기 (T3·T13 의 「호출 0회」용)."""
    calls = []
    real = guard.scan_series

    def _wrapped(stock_code, bars):
        calls.append(stock_code)
        return real(stock_code, bars)

    monkeypatch.setattr(guard, "scan_series", _wrapped)
    return calls


@pytest.fixture
def log(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr(screener_mod, "logger", m)
    return m


# ── T1 / T2 : 스크리너 층 (scan 경로) ────────────────────────────────────────

def test_t1_live_mode_drops_flagged_candidate(mode, log):
    """T1 — live 면 flagged 종목은 후보가 되지 못한다."""
    mode("live")
    assert _scan_one(_flagged_frame()) == []


def test_t1_live_mode_keeps_clean_stock(mode, log):
    """대칭 단언 — 같은 live 모드에서 «깨끗한» 종목은 그대로 통과한다."""
    mode("live")
    out = _scan_one(_clean_frame(), code="079650")
    assert len(out) == 1 and out[0].code == "079650" and out[0].score > 0


def test_t2_shadow_mode_returns_original_candidate_and_logs(mode, log):
    """T2 — shadow 는 «룰을 바꾸지 않는다». 후보는 off 와 완전히 같아야 한다."""
    mode("off")
    baseline = _scan_one(_flagged_frame())
    assert len(baseline) == 1

    mode("shadow")
    shadowed = _scan_one(_flagged_frame())
    assert [(c.code, c.score, c.reason) for c in shadowed] == \
           [(c.code, c.score, c.reason) for c in baseline]

    assert any("«안 함»" in m and "shadow" in m for m in _rendered(log.warning.call_args_list))


def test_t2_live_log_line_format(mode, log):
    """§3-3 로그 문구 고정 — 태그 `[rs_leader]` · 정지봉수 · 재개일 · 종가비 · mode."""
    mode("live")
    _scan_one(_flagged_frame(code="001290"), code="001290")

    lines = [m for m in _rendered(log.warning.call_args_list) if m.startswith("[rs_leader] ")]
    assert len(lines) == 1, _rendered(log.warning.call_args_list)
    assert lines[0].startswith("[rs_leader] 001290: ")
    assert "미조정 병합 의심(정지 4봉 → 재개 2026-02-14, 종가비 " in lines[0]
    assert lines[0].endswith("— 후보 제외 (mode=live)")


def test_split_direction_wording(mode, log):
    """🟢-5 — `direction='split'` 이면 「미조정 «분할» 의심」으로 찍는다.

    §3-3 예시는 merge 사례라 「병합」으로 고정돼 있지만, split 종목까지 「병합」이라
    찍으면 운영 로그에 사실과 다른 말이 남는다. 태그·접미는 그대로라 grep 계약은 유지.

    🔑 split 쪽 «순증» 커버리지는 종가비 **[0.65, 0.69)** 띠뿐이다 — 더 깊은 하락은
       `_prepare_frame` 의 기존 불가능봉 가드(−35%)가 «먼저» 잘라 여기 오지도 않는다.
       그래서 이 테스트의 jump 는 0.67 이어야 한다(0.2 로 두면 가드에 먼저 걸려 공허해진다).
    """
    mode("live")
    _scan_one(_flagged_frame(code="001130", jump=0.67), code="001130")
    lines = [m for m in _rendered(log.warning.call_args_list) if m.startswith("[rs_leader] ")]
    assert lines and "미조정 분할 의심(" in lines[0], lines


# ── T13 : `scan()` 밖에서는 배제가 «안» 걸린다 (rev2 · 🟡-1) ─────────────────

def test_t13_match_outside_scan_is_untouched(adapter, mode, spy, log):
    """T13 🔴 `match()` 는 `scan()` 전용이 아니다 — 백테스트 러너 2본이 직접 루프한다
    (`backtest/live_universe_revalidation/run.py:214` · `backtest/universe_lookahead_ladder/run.py:203`).

    배제가 그 경로까지 발효하면 스펙 §3-5 5항(`evaluate_entry` 불변 = 연구 재현 오염 금지)이
    막으려던 것과 «같은 종류»의 결함이 된다. 그래서 배제는 `scan()` 안에서만 돈다.
    """
    mode("live")
    flagged = _flagged_frame()

    verdict = adapter.match(flagged, adapter.default_params())
    assert verdict is not None, "scan() 밖 match() 가 배제됐다 — 연구 재현이 조용히 바뀐다"
    assert spy == [], f"scan() 밖인데 scan_series 가 {len(spy)}회 불렸다"
    assert log.warning.call_args_list == []      # 종목당 WARNING 폭주도 없어야 한다

    # 대칭 단언 — «같은» 프레임이 scan() 안에서는 배제된다
    assert _scan_one(flagged) == []
    assert spy, "scan() 안에서는 판정이 돌아야 한다"


def test_t13_match_outside_scan_does_not_leak_counters(adapter, mode, log):
    """`match()` 직접 호출이 계기 카운터를 오염시키지 않는다(러너는 `scan()` 을 안 부른다)."""
    mode("live")
    for _ in range(5):
        adapter.match(_flagged_frame(), adapter.default_params())
    assert adapter._ca_flagged == []
    assert adapter._ca_kept == 0
    assert adapter._ca_matched == 0


# ── T3 / T4 / T15 : scan() 층 (회귀 게이트 · 백필 · 계기 줄) ─────────────────

def test_t3_mode_off_is_bit_identical_and_never_scans(mode, spy, log):
    """T3 🔴 회귀 게이트 — off 면 후보·순서·score 가 «변경 전»과 완전 일치하고,
    탐지 함수는 «한 번도» 불리지 않는다(코드 진입 0)."""
    universe, frames, flagged = _synthetic_universe()
    mode("off")

    out = _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    expected = _expected_ranking(frames)[:20]

    assert [c.code for c in out] == [code for _, code in expected]
    assert [round(c.score, 12) for c in out] == [round(rs, 12) for rs, _ in expected]
    # flagged 종목이 off 에서는 «그대로» 후보에 남아 있어야 한다(스위치가 진짜 off).
    assert flagged & {c.code for c in out}
    assert spy == [], f"mode=off 인데 scan_series 가 {len(spy)}회 불렸다"


def test_t4_live_backfills_to_full_candidate_count(mode, log):
    """T4 — 배제는 정렬·topK «앞»이라 후보 수가 줄지 않는다(20 → 20)."""
    universe, frames, flagged = _synthetic_universe()

    mode("live")
    out = _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    codes = [c.code for c in out]

    assert len(codes) == 20
    assert not (flagged & set(codes)), f"flagged 가 후보에 남았다: {flagged & set(codes)}"
    assert codes == [code for _, code in _expected_ranking(frames, exclude=flagged)[:20]]


def _scan_line(log_mock):
    lines = [ln for ln in _rendered(log_mock.info.call_args_list)
             if ln.startswith("[rs-corp-action] ")]
    assert len(lines) == 1, _rendered(log_mock.info.call_args_list)
    return lines[0]


def test_t4_scan_line_prints_matched_flagged_and_kept(mode, log):
    """§3-3 + 🟡-3 — 스캔당 1줄에 matched·flagged·kept 를 «전부» 찍는다.

    건수만 찍으면 「배제 0건」과 「스캔이 안 돌았다」가 구별되지 않고,
    `matched` 가 없으면 flagged/kept 만으로는 룰 통과 총수를 복원할 수 없다.
    """
    universe, frames, flagged = _synthetic_universe()
    mode("live")
    _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})

    ln = _scan_line(log)
    assert "mode=live" in ln
    assert f"universe={_N_STOCKS}" in ln
    assert f"evaluated={_N_STOCKS}" in ln
    assert f"matched={_N_STOCKS}" in ln
    assert f"flagged={_N_FLAGGED}" in ln
    assert f"kept={_N_STOCKS - _N_FLAGGED}" in ln
    for code in flagged:
        assert code in ln.split("codes=", 1)[1]


def test_t15_matched_is_mode_invariant_and_kept_is_actual(mode, log, monkeypatch):
    """T15 🟡-3 — `matched` 는 모드와 «무관»하고 `kept` 는 «실제 반환 수»다.

    shadow 로그를 발효 «전» 기준선으로 쓰려면(스펙 §3-2) 두 칸의 «정의»가 모드에
    걸리면 안 된다. 정의가 바뀌면 발효일에 가짜 계단이 생겨 P4 집합 차분이 흔들린다.
    """
    universe, frames, _ = _synthetic_universe()

    mode("shadow")
    _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    shadow_line = _scan_line(log)
    log.reset_mock()

    mode("live")
    _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    live_line = _scan_line(log)

    assert f"matched={_N_STOCKS}" in shadow_line and f"matched={_N_STOCKS}" in live_line
    assert f"flagged={_N_FLAGGED}" in shadow_line and f"flagged={_N_FLAGGED}" in live_line
    # kept = 실제로 후보가 된 수 → shadow 는 전부, live 는 flagged 만큼 적다
    assert f"kept={_N_STOCKS}" in shadow_line
    assert f"kept={_N_STOCKS - _N_FLAGGED}" in live_line


def test_t14_rescan_after_exception_does_not_double_count(mode, log):
    """T14 🟡-2 — 스캔 중간 예외 뒤 재스캔해도 계기 줄이 이중계수되지 않는다.

    `_ca_*` 리셋이 `finalize_scan` 에만 있으면 예외로 `finalize_scan` 을 못 거친 스캔의
    잔재가 다음 스캔 줄에 얹힌다 — §6 P4 EOD 집합 차분이 읽는 바로 그 줄이다.
    """
    universe, frames, flagged = _synthetic_universe()
    mode("live")

    boom = _StubAdapter(universe, frames, boom_at=15)
    with pytest.raises(RuntimeError):
        boom.scan(SCAN_DATE, {"max_candidates": 20})
    assert boom._ca_flagged == [] and boom._ca_kept == 0 and boom._ca_matched == 0

    log.reset_mock()
    boom._boom_at = None
    boom._loads = 0
    boom.scan(SCAN_DATE, {"max_candidates": 20})
    ln = _scan_line(log)
    assert f"matched={_N_STOCKS}" in ln
    assert f"flagged={_N_FLAGGED}" in ln
    codes = ln.split("codes=", 1)[1].split(",")
    assert len(codes) == len(set(codes)) == _N_FLAGGED, ln


def test_scan_line_absent_when_off(mode, log):
    """대칭 단언 — off 면 계기 줄이 «없다»(발효일을 로그로 끊을 수 있다)."""
    universe, frames, _ = _synthetic_universe()
    mode("off")
    _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    assert not any("[rs-corp-action]" in ln for ln in _rendered(log.info.call_args_list))


def test_finalize_scan_calls_super(mode, log):
    """🟢-3 — override 가 부모 훅을 삼키지 않는다(나중에 부모가 뭔가 하면 조용히 유실)."""
    mode("off")
    universe, frames, _ = _synthetic_universe()
    with patch.object(RuleScreenerBase, "finalize_scan") as base_hook:
        _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    assert base_hook.call_count == 1


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


def test_t7_event_outside_82bar_window_is_not_blocked(mode, monkeypatch, log):
    """T7 🔴 사정거리 한계를 «못박는다» — 「on_tick 도 막았다」를 「전부 막았다」로 읽지 말 것.

    같은 사건, 다른 창:
      · 스크리너 130봉 프레임 → 잡는다 (1차 방어)
      · on_tick  82봉 프레임 → «못» 잡는다 (사건이 창 밖 — §2 Q3 실측 003350 유형)
    """
    closes, volumes = _flagged_series(halt_at=10, halt_bars=4, jump=1.6)
    mode("live")

    # 1차: 130봉 창 «안» → 배제된다
    assert _scan_one(_frame(closes, volumes, code="003350"), code="003350") == []

    # 2차: 82봉 창 «밖»(사건은 index 10~14, 창 시작은 index 49) → 막지 못한다
    s = _strategy(monkeypatch)
    sig = s._check_buy("003350", _frame(closes[-82:], volumes[-82:]))
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_startup_log_prints_resolved_mode_once(mode, monkeypatch):
    """🟢-7 — 기동 시 resolved mode 를 1줄 남긴다.

    `[rs-corp-action]` 스캔 줄은 `SCREENER_SNAPSHOT_ENABLED=false` 면 통째로 사라져
    §6 실패 조건(「줄이 하루라도 없음」)이 «무관한 이유»로 발화한다. 기동 줄이 있으면
    「스위치가 어느 값이었나」와 「스크리너가 돌았나」를 따로 판정할 수 있다.
    """
    mode("live")
    monkeypatch.setattr(
        "strategies.rs_leader.strategy.MarketHours.is_market_open",
        staticmethod(lambda market="KRX": True))
    s = RSLeaderStrategy(config=_load_config())
    s.logger = MagicMock()
    s.on_init(None, None, None)
    msgs = [str(c.args) for c in s.logger.info.call_args_list]
    hits = [m for m in msgs if "[rs-corp-action]" in m and "(startup)" in m and "mode=live" in m]
    assert len(hits) == 1, msgs


# ── T8 : 범위 (다른 전략 불변) ───────────────────────────────────────────────

def _ma20_pullback_df():
    """`tests/test_screener_ma20.py::_ma20_pullback_df` 와 같은 구성(룰이 실제로 통과)."""
    closes = [1000.0] * 9 + [1000.0 + i * 60.0 for i in range(20)] + [2100.0, 2050.0, 2080.0]
    n = len(closes)
    ma20_val = float(pd.Series(closes, dtype=float).rolling(20).mean().iloc[-1])
    opens = [c - 30.0 for c in closes]
    opens[-1] = closes[-1] - 40.0
    highs = [c + 20.0 for c in closes]
    lows = [c - 40.0 for c in closes[:-1]] + [ma20_val * 1.005]
    return pd.DataFrame({"date": pd.date_range("2026-03-01", periods=n), "open": opens,
                         "high": highs, "low": lows, "close": closes, "volume": [1000.0] * n})


def _ma5_pullback_df():
    closes = [1000.0] * 5 + [1000.0 + i * 60.0 for i in range(15)] + [1900.0, 1870.0, 1890.0]
    n = len(closes)
    ma5_val = float(pd.Series(closes, dtype=float).rolling(5).mean().iloc[-1])
    opens = [c - 20.0 for c in closes]
    opens[-1] = closes[-1] - 30.0
    highs = [c + 15.0 for c in closes]
    lows = [c - 25.0 for c in closes[:-1]] + [ma5_val * 1.005]
    return pd.DataFrame({"date": pd.date_range("2026-03-01", periods=n), "open": opens,
                         "high": highs, "low": lows, "close": closes, "volume": [1000.0] * n})


def _breakout_df():
    closes = [1000.0 + (i % 5) * 20.0 for i in range(21)] + [1300.0]
    n = len(closes)
    return pd.DataFrame({"date": pd.date_range("2026-03-01", periods=n),
                         "open": [c - 5.0 for c in closes[:-1]] + [1250.0],
                         "high": [1100.0] * 21 + [1320.0],
                         "low": [c - 10.0 for c in closes], "close": closes,
                         "volume": [1000.0] * 21 + [3000.0]})


def _elder_pullback_df(n=90):
    closes = [1000.0 + i * 10.0 for i in range(n)]
    ema13 = float(pd.Series(closes, dtype=float).ewm(span=13, adjust=False).mean().iloc[-1])
    return pd.DataFrame({"date": pd.date_range("2026-01-01", periods=n),
                         "open": [c - 2.0 for c in closes],
                         "high": [c + 5.0 for c in closes],
                         "low": [c - 8.0 for c in closes[:-1]] + [ema13 * 1.005],
                         "close": closes, "volume": [1000.0] * n})


def test_t8_other_adapters_unaffected(mode, spy):
    """T8 — 범위는 rs_leader «하나». 다른 어댑터는 mode 를 보지도 않는다.

    🟡-4 — 「룰이 실제로 통과하는」 프레임을 쓰고 `base is not None` 을 먼저 단언한다.
    안 그러면 `None == None` 이 되어 이 테스트가 «공허하게» 통과한다.
    """
    from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter
    from strategies.book_pullback_ma5.screener import BookPullbackMa5ScreenerAdapter
    from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter
    from strategies.elder_ema_pullback.screener import ElderEmaPullbackScreenerAdapter

    cases = [
        (BookPullbackMa20ScreenerAdapter, _ma20_pullback_df()),
        (BookPullbackMa5ScreenerAdapter, _ma5_pullback_df()),
        (Daytrading3MethodsBreakoutScreenerAdapter, _breakout_df()),
        (ElderEmaPullbackScreenerAdapter, _elder_pullback_df()),
    ]
    for cls, plain in cases:
        df = _prepend_halt(plain)
        assert guard.detect("X", df) is not None, f"{cls.__name__}: 프레임에 기업행위 흔적이 없다"
        a = cls()
        mode("off")
        base = a.match(df.copy(), a.default_params())
        assert base is not None, f"{cls.__name__}: 룰이 통과하지 않는 프레임 — 공허한 테스트"
        mode("live")
        assert a.match(df.copy(), a.default_params()) == base, cls.__name__
    spy.clear()   # 위 `guard.detect` 자가검사분 제외
    for cls, plain in cases:
        mode("live")
        cls().match(_prepend_halt(plain), cls().default_params())
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

def test_t10_invalid_mode_warns_and_behaves_as_off(mode, spy, log):
    """T10 — `RS_LEADER_CORP_ACTION_MODE="banana"` → off 로 동작 + WARNING 1줄.
    (config.constants 가 이미 off 로 낮추고 원문을 …_INVALID 에 보관한다.)"""
    universe, frames, flagged = _synthetic_universe()
    mode("off", invalid="banana")

    out = _StubAdapter(universe, frames).scan(SCAN_DATE, {"max_candidates": 20})
    assert flagged & {c.code for c in out}          # off 로 동작 = 배제 없음
    assert spy == []
    msgs = _rendered(log.warning.call_args_list)
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

    # (d) date 컬럼 결측 · NaT — 재개일 표시만 비고 예외는 없다
    no_date = _flagged_frame().drop(columns=["date"])
    assert guard.detect("A", no_date) is not None

    # (e) 빈 프레임 · None
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


def _detect_rowwise(stock_code, df):
    """rev1 의 행별 구현 — 🟢-2 벡터화가 «결과를 안 바꿨는지» 대조할 기준."""
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")
    dates = pd.to_datetime(df["date"], errors="coerce")
    iso = ["" if pd.isna(d) else d.strftime("%Y-%m-%d") for d in dates]
    bars = []
    for i in range(len(df)):
        c, v = close.iat[i], volume.iat[i]
        bars.append((iso[i], 0.0 if pd.isna(c) else float(c),
                     -1.0 if pd.isna(v) else float(v)))
    hits = guard.scan_series(str(stock_code or ""), bars)
    return hits[-1] if hits else None


def test_vectorized_detect_matches_rowwise_reference():
    """🟢-2 — 벡터화는 «속도만» 바꾼다. 결과가 한 건이라도 갈리면 실패."""
    rng = np.random.default_rng(20260910)
    cases = [_flagged_frame(), _clean_frame(),
             _flagged_frame(halt_bars=6, jump=1.4), _flagged_frame(jump=0.2)]
    for _ in range(20):
        n = 140
        closes = list(np.abs(rng.normal(10000, 3000, n)))
        vols = list(rng.choice([0.0, 1000.0, 5000.0], n, p=[0.25, 0.5, 0.25]))
        cases.append(_frame(closes, vols))
    for df in cases:
        assert guard.detect("X", df) == _detect_rowwise("X", df)
