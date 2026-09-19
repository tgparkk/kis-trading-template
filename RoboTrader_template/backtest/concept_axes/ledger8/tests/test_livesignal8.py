"""livesignal8 — 라이브 인스턴스 로드 · on_tick 가드 · 상태 무변경(rs 예외) · 라이브 밴드(합성 프레임 · DB 없음)."""
from __future__ import annotations

from datetime import date, datetime
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.ledger8 import livesignal8 as LS8
from backtest.concept_axes.ledger8 import registry as R

D = date(2026, 9, 17)


def _frame(n: int = 90, last_close: float = 118.0) -> pd.DataFrame:
    days = pd.bdate_range(end="2026-09-16", periods=n)
    close = np.linspace(100.0, 130.0, n)
    close[-1] = last_close
    return pd.DataFrame({"date": days, "open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": np.full(n, 1e5)})


def _forced(folder: str):
    if R.spec(folder).entry_eval_arity == 3:
        return staticmethod(lambda *a, **k: (True, ["forced"], {}))
    return staticmethod(lambda *a, **k: (True, ["forced"]))


@pytest.fixture(scope="module")
def strategies():
    return {f: LS8.load8(f) for f in R.ALL_FOLDERS}


def test_load8_all(strategies):
    assert set(strategies) == set(R.ALL_FOLDERS)
    assert all(s.positions == {} and s.daily_trades == 0 for s in strategies.values())


def test_on_tick_guards(strategies):
    s = strategies["book_pullback_ma20"]
    assert LS8.evaluate8(s, "book_pullback_ma20", "000001", D, None).reason == "no_daily_data"
    ev = LS8.evaluate8(s, "book_pullback_ma20", "000001", D, _frame(n=10))
    assert ev.signal == "N" and ev.reason.startswith("insufficient_data(10<")


@pytest.mark.parametrize("folder", [f for f in R.ALL_FOLDERS if f != "book_envelope_200d"])
def test_yes_path_returns_live_band(strategies, folder):
    s, df = strategies[folder], _frame()
    with mock.patch.object(type(s), "evaluate_entry", _forced(folder)):
        ev = LS8.evaluate8(s, folder, "000001", D, df)
    assert ev.signal == "Y" and ev.reasons_str == "forced"
    ref = float(df["close"].iloc[-1])
    assert ev.ref == pytest.approx(ref)
    if folder == "elder_ema_pullback":
        from strategies.books.elder_triple_screen.rules import krx_tick
        hi = float(df["high"].iloc[-1])
        stop = hi + krx_tick(hi)
        assert ev.band_min == pytest.approx(stop) and ev.band_max == pytest.approx(stop * (1 + s._entry_band_up_pct))
    else:
        assert (ev.band_min, ev.band_max) == s._entry_band(ref, down_pct=s._entry_band_down_pct,
                                                           up_pct=s._entry_band_up_pct)


def test_envelope_reads_own_frame_and_clears_cache(strategies):
    s = strategies["book_envelope_200d"]
    with mock.patch.object(s, "_fetch_entry_history", return_value=_frame(n=240)) as fetch, \
            mock.patch.object(type(s), "evaluate_entry", _forced("book_envelope_200d")):
        ev = LS8.evaluate8(s, "book_envelope_200d", "000001", D, _frame(n=8))   # on_tick 게이트는 min_gate_bars=5
    assert fetch.called and ev.signal == "Y" and s._entry_df_cache == {}


def test_envelope_now_kst_patch_reads_quant_up_to_d(strategies):
    """리뷰 1차: `_fetch_entry_history` 를 mock 하지 않고 quant 리더만 대체 — now_kst→D 09:02 패치(룩어헤드 가드)를 태운다."""
    s = strategies["book_envelope_200d"]
    hist = _frame(n=240)                                                   # 마지막 봉 2026-09-16(D-1)
    d_bar = hist.iloc[[-1]].assign(date=pd.Timestamp(D), close=999.0)      # D 당일 봉 — 라이브 코드가 지워야 한다
    reader = mock.Mock()
    reader.get_daily_prices.return_value = pd.concat([hist, d_bar], ignore_index=True)
    with mock.patch.object(s, "_quant_reader", return_value=reader), \
            mock.patch.object(type(s), "evaluate_entry", _forced("book_envelope_200d")):
        ev = LS8.evaluate8(s, "book_envelope_200d", "000001", D, _frame(n=8))
    reader.get_daily_prices.assert_called_once_with("000001", end_date=D, days=s._entry_lookback)   # 오늘이 아니라 D
    assert ev.signal == "Y"
    assert ev.detail["quant_n"] == 240 and ev.detail["quant_last"] == "2026-09-16"   # 캐시 키 (code, D) 로 읽힘 · D 봉 제거
    assert ev.ref == pytest.approx(float(hist["close"].iloc[-1]))                     # ref_close = D-1 종가(999 아님)
    assert s._entry_df_cache == {}


def test_state_change_raises_except_rs_leader_skip_log(strategies):
    def mutate(self, code, data):
        self._ontick_skip_log[(code, "probe")] = datetime(2026, 9, 17, 9, 2)
        return None
    for folder, raises in (("rs_leader", False), ("book_pullback_ma20", True)):
        s = strategies[folder]
        with mock.patch.object(type(s), "_check_buy", mutate):
            if raises:
                with pytest.raises(RuntimeError):
                    LS8.evaluate8(s, folder, "000001", D, _frame())
            else:
                assert LS8.evaluate8(s, folder, "000001", D, _frame()).signal == "N"
        s._ontick_skip_log.clear()


def test_positions_change_raises_even_for_rs_leader(strategies):
    def mutate(self, code, data):
        self.positions[code] = {}
        return None
    s = strategies["rs_leader"]
    with mock.patch.object(type(s), "_check_buy", mutate), pytest.raises(RuntimeError):
        LS8.evaluate8(s, "rs_leader", "000001", D, _frame())
    s.positions.clear()


def test_patches_restore(strategies):
    import config.constants as CC
    from config.market_hours import MarketHours
    before_mode, before_fn = CC.RS_LEADER_CORP_ACTION_MODE, MarketHours.is_market_open
    with LS8.live_buy_patches(strategies["rs_leader"], "rs_leader", date(2026, 9, 17)):
        assert CC.RS_LEADER_CORP_ACTION_MODE == "live" and MarketHours.is_market_open("KRX") is True
    with LS8.live_buy_patches(strategies["rs_leader"], "rs_leader", date(2026, 9, 16)):
        assert CC.RS_LEADER_CORP_ACTION_MODE == "shadow"
    assert CC.RS_LEADER_CORP_ACTION_MODE == before_mode and MarketHours.is_market_open == before_fn


def test_forced_band_is_live_band(strategies):
    folder = "book_pullback_ma5"
    s = strategies[folder]
    ref, lo, hi = LS8.forced_band(s, folder, "000001", D, _frame())
    assert (lo, hi) == s._entry_band(ref, down_pct=s._entry_band_down_pct, up_pct=s._entry_band_up_pct)
    assert s.positions == {}


def test_volume_margin_uses_live_rule_thresholds():
    from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
    from strategies.books.minervini_vcp.rules import rule_volume_dryup
    ev = LS8.SignalEval8(LS8.DAY, "000001", D, "Y", "x", reasons_str="breakout_prev_high close=1 prior20_high=1 vol=300/100")
    assert LS8.volume_margin(LS8.DAY, None, ev) == (3.0, float(rule_breakout_prev_high.vol_mult))
    df = _frame(n=40)
    df["volume"] = [100.0] * 30 + [60.0] * 10                   # recent10 / base30 = 0.60
    ratio, thr = LS8.volume_margin(LS8.MIN, df, LS8.SignalEval8(LS8.MIN, "000001", D, "N", "rule_not_met"))
    assert ratio == pytest.approx(0.60) and thr == float(rule_volume_dryup.ratio_max)
    assert LS8.volume_margin("rs_leader", df, ev) is None
