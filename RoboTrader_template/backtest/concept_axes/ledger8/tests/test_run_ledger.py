"""run — 원장 조립의 순수 부분(DB·로그 파일 없음): D5 표시(A1) · D3′ 분봉 없음 → 「모른다」+상한(A3) · 중복 체결 가드."""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade
from backtest.concept_axes.ledger8 import arms as A
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import logscan8 as L8
from backtest.concept_axes.ledger8 import registry as R
from backtest.concept_axes.ledger8 import run as RUN
from backtest.concept_axes.ledger8 import sizing as Z
from backtest.concept_axes.ledger8 import sources8 as SRC8
from backtest.concept_axes.ledger8 import stages as ST

D = date(2026, 9, 10)
MA20, MA5, RS = "book_pullback_ma20", "book_pullback_ma5", "rs_leader"


def _t(i, code, buy, sell=None):
    return Trade(buy_id=i, code=code, buy_ts=datetime.combine(D, buy), buy_price=100.0,
                 sell_ts=datetime.combine(D, sell) if sell else None, sell_price=101.0 if sell else None)


def _hm(h, m, s=0):
    return datetime(2026, 9, 10, h, m, s).time()


# ── D5 25분 매수 쿨다운(A1) ─────────────────────────────────────────────────
def test_cooldown_ignores_this_candidates_own_live_buy_053260():
    """09-10 053260 형 — 라이브가 09:01:38 에 산 «이 후보 자신»의 매수는 B 09:02 진입의 쿨다운이 아니다(팔았어도)."""
    buys = [(MA20, _t(1, "053260", _hm(9, 1, 38), _hm(9, 1, 50)))]
    assert RUN.cooldown_flag(buys, MA20, "053260", datetime(2026, 9, 10, 9, 2), True, []) == ""


def test_cooldown_other_strategy_on_its_own_slot_does_not_block():
    """다른 전략 매수는 «그 전략 슬롯 객체»에 시계를 건다(core/trading_context.py:88-109·:376) — 폴백 흔적
    (`[모호조회]`) 없으면 이 전략 객체는 안 건드렸다 → 막히지 않았다(확정 · 표시 없음)."""
    buys = [(MA5, _t(2, "005930", _hm(9, 40), _hm(9, 50)))]
    assert RUN.cooldown_flag(buys, MA20, "005930", datetime(2026, 9, 10, 10, 0), True, []) == ""


def test_cooldown_cross_strategy_with_fallback_trace_is_flagged_unobservable():
    """진짜 교차 전략 경우 — 다른 전략이 25분 안에 사고 팔았고 그날 그 종목 `[모호조회]`(코드 단독 폴백 = 이 전략 객체일
    수 있음)가 있으면 어느 객체였는지 모른다 → `관측 불가` 로 표시(추측으로 막힘/안 막힘을 적지 않는다)."""
    buys = [(MA5, _t(2, "005930", _hm(9, 40), _hm(9, 50)))]
    got = RUN.cooldown_flag(buys, MA20, "005930", datetime(2026, 9, 10, 10, 0), True, ["09:40:00"])
    assert got == RUN.D5_COOLDOWN_UNKNOWN
    # 폴백 흔적이 진입 뒤에만 있으면 진입 시각의 객체와 무관
    assert RUN.cooldown_flag(buys, MA20, "005930", datetime(2026, 9, 10, 10, 0), True, ["10:30:00"]) == ""


def test_cooldown_other_still_holding_is_the_held_gate_not_cooldown():
    """아직 보유 중이면 라이브는 보유 게이트(bot/trading_analyzer.py:127-130)가 먼저 막는다 — D2 `other_holder_live` 몫."""
    buys = [(MA5, _t(2, "005930", _hm(9, 40), _hm(10, 5))), (RS, _t(3, "005930", _hm(9, 45)))]
    assert RUN.cooldown_flag(buys, MA20, "005930", datetime(2026, 9, 10, 10, 0), True, ["09:40:00"]) == ""


def test_cooldown_window_is_25_minutes_from_the_buy():
    entry = datetime(2026, 9, 10, 10, 0)
    old = [(MA5, _t(2, "005930", _hm(9, 35), _hm(9, 36)))]          # 25분 전 = 끝남
    later = [(MA5, _t(2, "005930", _hm(10, 1), _hm(10, 2)))]         # 진입 뒤 매수
    other_code = [(MA5, _t(2, "000660", _hm(9, 50), _hm(9, 55)))]
    for buys in (old, later, other_code):
        assert RUN.cooldown_flag(buys, MA20, "005930", entry, True, ["09:00:00"]) == ""
    edge = [(MA5, _t(2, "005930", _hm(9, 35, 1), _hm(9, 36)))]       # 24분 59초 전
    assert RUN.cooldown_flag(edge, MA20, "005930", entry, True, ["09:00:00"]) == RUN.D5_COOLDOWN_UNKNOWN
    assert RUN.COOLDOWN_MIN == 25


def test_cooldown_ext_tier_has_no_own_slot_so_object_is_unknown():
    """ext(11~20위)는 라이브 SELECTED 에 이 전략 슬롯이 없다 — 가정 매수는 코드 단독 폴백이라 객체를 모른다."""
    buys = [(MA5, _t(2, "005930", _hm(9, 40), _hm(9, 50)))]
    assert RUN.cooldown_flag(buys, MA20, "005930", datetime(2026, 9, 10, 10, 0), False, []) == RUN.D5_COOLDOWN_UNKNOWN


# ── D5 진입억제 지연(A1) · d5_flags 배선 ─────────────────────────────────────
def _ctx(trades, ambiguous=None):
    dl = SimpleNamespace(ambiguous=ambiguous or {})
    return SimpleNamespace(trades=trades, log_for=lambda d: dl)


def _sd(code, *gates):
    sd = L8.StratDay()
    for g in gates:
        sd.gates.setdefault((code, g), L8.Fold()).hit("09:10:13")
    return sd


def test_throttle_on_a_row_live_bought_is_a_delay_not_a_block():
    sd = _sd("072990", L8.G_THROTTLE)
    ctx = _ctx({})
    t0 = datetime(2026, 9, 10, 9, 2)
    assert RUN.d5_flags(ctx, sd, MA20, "072990", t0, True, ST.STAGE_FILL) == [RUN.D5_THROTTLE_DELAY]
    assert RUN.d5_flags(ctx, sd, MA20, "072990", t0, True, ST.STAGE_GATE) == [RUN.D5_THROTTLE]
    assert RUN.d5_flags(ctx, sd, MA20, "072990", t0, False, "") == [RUN.D5_THROTTLE]     # ext — A 단계 없음 → 관측 그대로
    assert RUN.D5_THROTTLE_DELAY != RUN.D5_THROTTLE


def test_d5_flags_wires_daily_loss_and_cooldown_without_own_buy_false_positive():
    sd = _sd("053260", L8.G_DAILY_LOSS)
    own = _t(1, "053260", _hm(9, 1, 38), _hm(9, 1, 50))
    other = _t(2, "053260", _hm(9, 0, 30), _hm(9, 1))
    t0 = datetime(2026, 9, 10, 9, 2)
    assert RUN.d5_flags(_ctx({MA20: [own]}), sd, MA20, "053260", t0, True, ST.STAGE_FILL) == [RUN.D5_DAILY_LOSS]
    got = RUN.d5_flags(_ctx({MA20: [own], MA5: [other]}, {"053260": ["09:00:30"]}), sd, MA20, "053260", t0, True,
                       ST.STAGE_FILL)
    assert got == [RUN.D5_DAILY_LOSS, RUN.D5_COOLDOWN_UNKNOWN]


# ── D3′ 분봉 없음 → 「모른다」 + 상한 민감도(A3) ─────────────────────────────
BAND = (100.0, 98.0, 103.0)
COMMON = dict(tier=R.TIER_MAIN, signal_basis="replay", other_holder_live="")
DBAR = X.Bar(D, 104.0, 106.0, 99.0, 101.5)
OPEN = [("09:23:09", "")]


def test_no_minute_data_makes_no_main_fill_and_an_upper_bound_fill():
    le, main, ub, ubf, reblocked = RUN.lift_fills(MA20, "005930", D, [], DBAR, OPEN, BAND, COMMON)
    assert le.status == X.LIFT_NO_MINUTE and main is None and not reblocked
    assert ub.status == X.LIFT_FILLED and ub.price == 101.5
    q = Z.arm_b_qty(101.5)
    assert ubf == A.Fill(MA20, "005930", D, 101.5, X.BASIS_UPPER, q.qty, q.basis, tier=R.TIER_LIFT_UB,
                         signal_basis="replay", crash_blocked=True, other_holder_live="", lift_time="09:23:09")
    assert ubf.entry_time is None and ubf.touch_bar is None and ubf.tier != R.TIER_MAIN


def test_no_minute_data_without_daily_overlap_or_bar_has_no_upper_fill():
    far = X.Bar(D, 110.0, 112.0, 108.0, 111.0)
    for bar, status in ((far, X.LIFT_UNFILLABLE), (None, X.LIFT_NO_BAR)):
        le, main, ub, ubf, _ = RUN.lift_fills(MA20, "005930", D, [], bar, OPEN, BAND, COMMON)
        assert (le.status, main, ub.status, ubf) == (X.LIFT_NO_MINUTE, None, status, None)


def test_minute_fill_after_lift_is_main_and_has_no_upper_bound():
    mins = [("09:23:00", X.Bar(D, 100.0, 100.0, 100.0, 100.0)), ("09:24:00", X.Bar(D, 102.0, 102.5, 101.0, 101.5))]
    le, main, ub, ubf, reblocked = RUN.lift_fills(MA20, "005930", D, mins, DBAR, OPEN, BAND, COMMON)
    assert le.status == X.LIFT_FILLED and (ub, ubf, reblocked) == (None, None, False)
    assert (main.basis, main.price, main.tier, main.lift_time, main.crash_blocked) == \
        (X.BASIS_LIFT, 102.0, R.TIER_MAIN, "09:24:00", True)
    assert main.entry_time is not None and main.entry_time.time() == _hm(9, 24)


def test_minutes_present_but_out_of_band_stays_unfillable_without_upper_bound():
    mins = [("09:24:00", X.Bar(D, 110.0, 111.0, 109.0, 110.0))]
    le, main, ub, ubf, _ = RUN.lift_fills(MA20, "005930", D, mins, DBAR, OPEN, BAND, COMMON)
    assert (le.status, main, ub, ubf) == (X.LIFT_UNFILLABLE, None, None, None)


def test_not_lifted_is_not_unknown():
    le, main, ub, ubf, reblocked = RUN.lift_fills(MA20, "005930", D, [], DBAR, [], BAND, COMMON)
    assert (le.status, main, ub, ubf, reblocked) == (X.LIFT_NOT_LIFTED, None, None, None, False)


def test_reblocked_window_moves_the_entry_and_marks_the_row():
    """과제 9 I1 — 첫 해제만 보면 재차단 구간(09:33:50~09:35:03)에서 샀을 행: 다음 열린 구간 봉에 사고 재차단 표시."""
    wins = [("09:23:09", "09:33:50"), ("09:35:03", "")]
    mins = [("09:34:00", X.Bar(D, 101.0, 102.0, 100.0, 101.0)), ("09:36:00", X.Bar(D, 102.0, 102.5, 90.0, 95.0))]
    le, main, ub, ubf, reblocked = RUN.lift_fills(MA20, "005930", D, mins, DBAR, wins, BAND, COMMON)
    assert reblocked and (ub, ubf) == (None, None)
    assert (le.time, le.window, main.price, main.lift_time) == ("09:36:00", "09:35:03~", 102.0, "09:36:00")
    assert main.entry_time.time() == _hm(9, 36) and main.touch_bar.low == 90.0
    only_reblock = mins[:1]           # 재차단 구간 봉뿐 — 열린 구간 안 분봉 0개 = 모른다(A3 · 최종 검수 #15) + 재차단 표시
    le2, main2, ub2, ubf2, reblocked2 = RUN.lift_fills(MA20, "005930", D, only_reblock, DBAR, wins, BAND, COMMON)
    assert (le2.status, main2, ub2.status, ubf2.tier, reblocked2) == \
        (X.LIFT_NO_MINUTE, None, X.LIFT_FILLED, R.TIER_LIFT_UB, True)
    out_of_band = only_reblock + [("09:36:00", X.Bar(D, 110.0, 111.0, 109.0, 110.0))]   # 구간 안 봉 · 밴드 밖 → 미체결
    le3, main3, ub3, ubf3, reblocked3 = RUN.lift_fills(MA20, "005930", D, out_of_band, DBAR, wins, BAND, COMMON)
    assert (le3.status, main3, ub3, ubf3, reblocked3) == (X.LIFT_UNFILLABLE, None, None, None, True)


def test_upper_bound_keeps_first_lift_time_on_reblocked_days():
    wins = [("11:02:06", "13:11:00")]
    le, main, ub, ubf, reblocked = RUN.lift_fills(MA20, "005930", D, [], DBAR, wins, BAND, COMMON)
    assert (le.status, main, ub.status, ubf.lift_time, reblocked) == \
        (X.LIFT_NO_MINUTE, None, X.LIFT_FILLED, "11:02:06", False)
    assert RUN.reblocks(wins) == ["13:11:00"] and RUN.reblocks([("11:02:06", "")]) == []


# ── 과제 10 fix 1: 분봉 없음 + 라이브 실제 체결 = «아는 것은 안다»(live_fill) ─────────────
def _live(hms, price=101.0, i=7):
    return Trade(buy_id=i, code="005930", buy_ts=datetime.combine(D, hms), buy_price=price)


def test_no_minute_data_with_live_buy_after_lift_becomes_a_main_live_fill():
    live = _live(_hm(9, 25, 38))
    le, main, ub, ubf, reblocked = RUN.lift_fills(MA20, "005930", D, [], DBAR, OPEN, BAND, COMMON, [live])
    assert le.status == X.LIFT_NO_MINUTE and (ub, ubf, reblocked) == (None, None, False)   # 상한·모름에서 빠진다
    q = Z.arm_b_qty(101.0)
    assert (main.basis, main.price, main.qty, main.qty_basis, main.tier, main.crash_blocked, main.lift_time) == \
        (X.BASIS_LIVE_FILL, 101.0, q.qty, q.basis, R.TIER_MAIN, True, "09:23:09")        # lift_time = 게이트 해제
    assert main.entry_time.replace(tzinfo=None) == live.buy_ts and main.touch_bar is None  # entry_time = 라이브 체결


def test_live_buy_before_the_lift_or_none_leaves_the_row_unknown_with_upper_bound():
    for lives in ([_live(_hm(9, 1, 38))], [], None):
        args = (MA20, "005930", D, [], DBAR, OPEN, BAND, COMMON) + (() if lives is None else (lives,))
        le, main, ub, ubf, _ = RUN.lift_fills(*args)
        assert (le.status, main, ub.status, ubf.basis, ubf.tier) == \
            (X.LIFT_NO_MINUTE, None, X.LIFT_FILLED, X.BASIS_UPPER, R.TIER_LIFT_UB)


def test_live_buy_does_not_replace_a_minute_fill_after_lift():
    mins = [("09:24:00", X.Bar(D, 102.0, 102.5, 101.0, 101.5))]
    le, main, ub, ubf, _ = RUN.lift_fills(MA20, "005930", D, mins, DBAR, OPEN, BAND, COMMON, [_live(_hm(9, 30))])
    assert (le.status, main.basis, main.price, ub, ubf) == (X.LIFT_FILLED, X.BASIS_LIFT, 102.0, None, None)


def test_d5_entry_time_of_a_live_fill_is_the_live_buy_time_not_the_gate_lift():
    """다른 전략 09:10 매수·09:24 매도 + 폴백 흔적 — 진입이 09:25:38(라이브 체결)이면 25분 안·매도 뒤라 관측 불가,
    게이트 해제 09:23:09 로 보면 아직 보유라 표시 없음. 표시는 체결 시각으로 본다."""
    ctx = _ctx({MA5: [_t(2, "005930", _hm(9, 10), _hm(9, 24))]}, {"005930": ["09:10:00"]})
    f = A.Fill(MA20, "005930", D, 101.0, X.BASIS_LIVE_FILL, 9900, "amount", crash_blocked=True,
               entry_time=SRC8.aware(datetime.combine(D, _hm(9, 25, 38))), lift_time="09:23:09")
    assert RUN._with_d5(ctx, L8.StratDay(), f, True, ST.STAGE_FILL).d5 == RUN.D5_COOLDOWN_UNKNOWN


# ── 중복 체결 가드(과제 8 M1) ────────────────────────────────────────────────
def _f(tier=R.TIER_MAIN, code="005930", buy_id=None):
    return A.Fill(MA20, code, D, 100.0, X.BASIS_D_OPEN, 10, "amount", tier=tier, buy_id=buy_id)


def test_unique_guard_raises_instead_of_overlapping_lots_or_accounts():
    with pytest.raises(ValueError, match="005930"):
        RUN.unique_fills([_f(), _f()], RUN.lot_key, "B1")
    ok = [_f(), _f(R.TIER_LIFT_UB, "000660")]
    assert RUN.unique_fills(ok, RUN.acct_key, "B2") == ok
    RUN.unique_fills([_f(), _f(R.TIER_LIFT_UB)], RUN.lot_key, "B1_ub")          # 로트 키는 tier 를 본다
    with pytest.raises(ValueError, match="B2_ub"):                               # 계좌 키는 (날짜, 전략, 종목)
        RUN.unique_fills([_f(), _f(R.TIER_LIFT_UB)], RUN.acct_key, "B2_ub")
    RUN.unique_fills([_f(buy_id=1), _f(buy_id=2)], RUN.lot_key, "A_sim")        # A_sim — 같은 날 재매수는 buy_id 로 구분


# ── 최종 검수 I1: A_sim 도 B1 과 같은 D3′ 경로(급락일 실제 매수에 09:02 진입을 만들지 않는다) ──────────────────
ABAR = X.Bar(D, 101.0, 106.0, 99.0, 101.5)                 # 09:02 시뮬이면 D 시가 101(밴드 안)에 샀을 봉
MINS = [("09:24:00", X.Bar(D, 102.0, 102.5, 101.0, 101.5))]
WINS = [("09:23:09", "")]


def _asim(monkeypatch, trade, crash, minutes):
    monkeypatch.setattr(RUN.LS8, "evaluate8",
                        lambda *a: SimpleNamespace(signal="Y", ref=BAND[0], band_min=BAND[1], band_max=BAND[2]))
    monkeypatch.setattr(RUN, "crash_state", lambda ctx, f, c, d: (True, WINS[0][0], WINS) if crash else (False, "", []))
    ctx = SimpleNamespace(strategies={f: None for f in R.ALL_FOLDERS}, trades={MA20: [trade]},
                          windows=SimpleNamespace(get=lambda code, d: (None, None)), bars_for=lambda code: {D: ABAR},
                          minute_bars=lambda code, d: minutes, extras={trade.buy_id: SimpleNamespace(qty=7)})
    fills, rows, warns = RUN.a_sim_fills(ctx, [D], {(D, MA20): ["005930"]})
    assert warns == [] and len(rows) == 1
    return fills, rows[0]


def test_a_sim_crash_day_buy_enters_like_b1_after_the_lift_not_at_0902(monkeypatch):
    live = _live(_hm(9, 25, 38), price=102.0)
    fills, row = _asim(monkeypatch, live, True, MINS)
    _, b1, _, _, _ = RUN.lift_fills(MA20, "005930", D, MINS, ABAR, WINS, BAND, COMMON, [live])
    (f,) = fills
    assert (f.basis, f.price, f.entry_time, f.lift_time) == (b1.basis, b1.price, b1.entry_time, b1.lift_time)
    assert (f.basis, f.price, f.qty, f.qty_basis, f.buy_id, f.tier, f.crash_blocked) == \
        (X.BASIS_LIFT, 102.0, 7, "actual", 7, R.TIER_MAIN, True)                  # 수량 = 실제 · 09:02 D 시가 101 아님
    assert (row["sim_entry_status"], row["sim_entry_basis"], row["sim_entry_price"], row["entry_diff_pct"]) == \
        ("crash→" + X.LIFT_FILLED, X.BASIS_LIFT, "102", "+0.00")


def test_a_sim_crash_day_without_minutes_is_the_live_fill_and_not_an_entry_bias_sample(monkeypatch):
    live = _live(_hm(9, 25, 38), price=101.7)
    fills, row = _asim(monkeypatch, live, True, [])
    (f,) = fills
    assert (f.basis, f.price, f.qty, f.qty_basis, f.crash_blocked) == (X.BASIS_LIVE_FILL, 101.7, 7, "actual", True)
    assert f.entry_time.replace(tzinfo=None) == live.buy_ts
    # 시뮬이 아니라 실제 체결 그대로 — 진입가 차(§1-6) 표본이 아니다(0.00 으로 평균을 희석하지 않는다)
    assert (row["sim_entry_basis"], row["sim_entry_price"], row["entry_diff_pct"]) == (X.BASIS_LIVE_FILL, "101.7", "")


def test_a_sim_crash_day_buy_before_the_lift_without_minutes_stays_unknown_and_non_crash_is_0902(monkeypatch):
    fills, row = _asim(monkeypatch, _live(_hm(9, 1, 38)), True, [])           # B1 main 과 같이 «모른다» → 체결 없음
    assert fills == [] and row["sim_entry_status"] == "crash→" + X.LIFT_NO_MINUTE and row["entry_diff_pct"] == ""
    fills, row = _asim(monkeypatch, _live(_hm(9, 25, 38)), False, MINS)       # 게이트 안 막힘 → 09:02 D 시가 그대로
    (f,) = fills
    assert (f.basis, f.price, f.crash_blocked, row["sim_entry_status"]) == (X.BASIS_D_OPEN, 101.0, False, "filled")


# ── 최종 검수 M1(수정 목록 4): --reuse-fills 동결본의 출처 SHA ────────────────────────────────────────────
def test_reuse_source_sha_reads_the_frozen_runs_meta_and_follows_a_chain(tmp_path):
    fills = tmp_path / "fills_b.csv"
    assert RUN.reuse_source_sha(fills) == ""                                   # run_meta.json 없음 → 불명
    (tmp_path / "run_meta.json").write_text('{"git_sha": "09b951b", "reuse_fills": ""}', encoding="utf-8")
    assert RUN.reuse_source_sha(fills) == "09b951b"
    (tmp_path / "run_meta.json").write_text(                                  # 재추적 결과를 또 재추적 → 원 산출 SHA
        '{"git_sha": "aaaaaaa", "reuse_fills": "x/fills_b.csv", "reuse_fills_sha": "09b951b"}', encoding="utf-8")
    assert RUN.reuse_source_sha(fills) == "09b951b"
    (tmp_path / "run_meta.json").write_text(                                  # 원 산출 SHA 불명 → 재추적 SHA 로 안 채움
        '{"git_sha": "aaaaaaa", "reuse_fills": "x/fills_b.csv", "reuse_fills_sha": ""}', encoding="utf-8")
    assert RUN.reuse_source_sha(fills) == ""
    (tmp_path / "run_meta.json").write_text("{not json", encoding="utf-8")
    assert RUN.reuse_source_sha(fills) == ""
