"""청산 브래킷 짝 비교 단위 테스트 — 합성 데이터 · DB 없음.

사전등록 `docs/prereg_2026-09-26_exit_bracket_pair_comparison.md`(동결 dbea62a) §8 ② 목록:
ExitRules 두 값만 바뀜 · V1~V4 = 모문서 §4 표 · SellProbe 가 config tp/sl 무관 · ① 제외가 결과 열을 안 읽음 ·
v 룩어헤드 없음 · 에피소드 재계산 · CR1·CGM 손계산 · 가짜 중심화 · 시드 (w,s,v,j) · 1로트 × 5 브래킷 손계산.
"""
from __future__ import annotations

import copy
import dataclasses
import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.candidate_ledger import run as R
from backtest.concept_axes.candidate_ledger.exit_pair import run_exit_pair as P
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import sellprobe8 as SP
from backtest.concept_axes.ledger8 import sources8 as SRC8
from backtest.concept_axes.ledger8.livesignal8 import load8

MA20, MINV, DAYT = "book_pullback_ma20", "minervini_volume_dryup", "daytrading_3methods_breakout"


# ── 변형 값 · ExitRules ─────────────────────────────────────────────────────
def test_variant_values_equal_parent_prereg_section4_table():
    # 모문서 docs/prereg_2026-09-24_exit_path_diagnosis.md §4 표를 글자 그대로 옮긴 값 (tp, sl)
    want = {
        MA20: {"V1": (0.10, 0.06), "V2": (0.10, 0.10), "V3": (0.08, 0.08), "V4": (0.12, 0.08)},
        MINV: {"V1": (0.12, 0.06), "V2": (0.12, 0.10), "V3": (0.10, 0.08), "V4": (0.14, 0.08)},
        DAYT: {"V1": (0.10, 0.08), "V2": (0.10, 0.12), "V3": (0.08, 0.10), "V4": (0.12, 0.10)},
    }
    assert P.VARIANTS == want
    for f in want:                                   # 한쪽만 한 칸(0.02) · 원 값 = 원장 PREREG §6
        tp0, sl0 = R.STRATS[f]["tp"], R.STRATS[f]["sl"]
        for k, (tp, sl) in want[f].items():
            assert (round(abs(tp - tp0), 9) == 0.02) != (round(abs(sl - sl0), 9) == 0.02)
            assert (tp == tp0) or (sl == sl0)
        P.guard_variants(f, X.ExitRules(tp0, sl0, R.STRATS[f]["max_hold"], "x"))


def test_exit_rules_only_tp_sl_change():
    base = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=50, source="config(take_profit_pct/stop_loss_pct)")
    for k, (tp, sl) in P.VARIANTS[MA20].items():
        v = P.variant_rules(base, tp, sl)
        diff = {f.name for f in dataclasses.fields(X.ExitRules) if getattr(v, f.name) != getattr(base, f.name)}
        assert diff <= {"tp", "sl"} and diff
        assert (v.tp, v.sl) == (tp, sl) and v.max_hold_days == 50 and v.source == base.source


def test_guard_variants_stops_on_wrong_base():
    with pytest.raises(SystemExit):
        P.guard_variants(MA20, X.ExitRules(0.12, 0.08, 50, "x"))


# ── SellProbe 는 config tp/sl 과 무관 ───────────────────────────────────────
def _px_frame(n: int = 160) -> pd.DataFrame:
    days = [d.date() for d in pd.bdate_range("2025-01-02", periods=n)]
    x = np.arange(n, dtype=float)
    close = 10_000 * (1 + 0.30 * np.sin(x / 9.0) + 0.002 * x)
    return pd.DataFrame(dict(date=pd.to_datetime(days), open=close * 0.995, high=close * 1.02, low=close * 0.98,
                             close=close, volume=1_000_000.0))


@pytest.mark.parametrize("folder", [MA20, MINV, DAYT])
def test_sellprobe_output_independent_of_config_tp_sl(folder):
    px = _px_frame()
    days = px["date"].dt.date.tolist()

    def window_fn(code, day):
        g = px[px["date"] < pd.Timestamp(day)].reset_index(drop=True)
        return g, {"n": len(g)}

    base = load8(folder)
    probes = [SP.SellProbe(folder, base, window_fn)]
    for tp, sl in ((0.01, 0.01), (0.50, 0.45), (0.14, 0.12)):
        s = copy.deepcopy(base)
        s._take_profit_pct, s._stop_loss_pct = tp, sl
        (s.config.setdefault("risk_management", {})).update(take_profit_pct=tp, stop_loss_pct=sl)
        probes.append(SP.SellProbe(folder, s, window_fn))
    outs = []
    for pr in probes:
        o = []
        for e_i in (70, 90, 100):
            d1 = days[e_i]
            for ratio in (0.6, 0.95, 1.0, 1.3):
                E = float(px["close"].iloc[e_i - 1]) * ratio
                pos = X.Pos("000001", d1, SRC8.aware(datetime.combine(d1, R.ENTRY_TIME)), E, 10, X.BASIS_D_OPEN)
                for k in (0, 1, 3, 8, 12, 25, 55):
                    if e_i + k < len(days):
                        o.append(pr(pos, days[e_i + k]))
        outs.append(o)
    assert all(o == outs[0] for o in outs[1:])
    assert any(x is not None for x in outs[0])           # 무의미한 전부-None 비교 방지(보유기간·trail 발동)


# ── ① 제외 · 수평선 ─────────────────────────────────────────────────────────
def _cal(n: int = 30, start: date = date(2026, 8, 1)):
    days = [d.date() for d in pd.bdate_range(start, periods=n)]
    return days, {d: i for i, d in enumerate(days)}


def test_exclusions_do_not_read_result_columns_and_waterfall(monkeypatch):
    cal, cidx = _cal(30)
    monkeypatch.setattr(P, "HORIZON_MAX", cal[-1])
    lots = pd.DataFrame(dict(
        strategy=[DAYT, DAYT, DAYT, DAYT, MA20],
        stock_code=["A", "B", "C", "D", "A"],
        entry_date=[cal[5].isoformat(), cal[5].isoformat(), cal[5].isoformat(), cal[25].isoformat(),
                    cal[5].isoformat()],
        exit_reason=["tp", "sl", "max_hold", "tp", "sl"], exit_date=[cal[6].isoformat()] * 5,
        ret_pct=["1", "2", "3", "4", "5"], exit_price=["1"] * 5))
    corp = {"B": np.array([np.datetime64(pd.Timestamp(cal[12]))], dtype="datetime64[ns]")}
    imp = {"B": np.array([np.datetime64(pd.Timestamp(cal[13]))], dtype="datetime64[ns]"),
           "C": np.array([np.datetime64(pd.Timestamp(cal[15]))], dtype="datetime64[ns]")}
    mh = {DAYT: 10, MA20: 50}
    a = P.exclusions_123(lots, mh, cal, cidx, corp, imp)
    # A: 5+10=15 ≤ 29 · 흠 없음 / B: corp 먼저(폭포식) / C: imp 15 ∈ [5, 15] / D: 25+10 > 29 ⇒ ① / ma20 A: 5+50 ⇒ ①
    assert a["excl"].tolist() == ["", "②corp_event", "③impossible_bar", "①horizon", "①horizon"]
    assert a["hend"].tolist()[:3] == [cal[15].isoformat()] * 3
    scrambled = lots.assign(exit_reason="open", exit_date="2099-01-01", ret_pct="-99", exit_price="0")
    b = P.exclusions_123(scrambled, mh, cal, cidx, corp, imp)
    assert a.equals(b)
    c = P.exclusions_123(lots[["strategy", "stock_code", "entry_date"]], mh, cal, cidx, corp, imp)
    assert a.equals(c)                                    # 결과 열이 없어도 같다 = 읽지 않는다


def test_horizon_end_is_max_hold_trading_days_after_entry():
    cal, cidx = _cal(12)
    assert P.horizon_end(cal, cidx, cal[1], 10) == cal[11]
    assert P.horizon_end(cal, cidx, cal[2], 10) is None


# ── v 룩어헤드 없음 ──────────────────────────────────────────────────────────
def test_vol_v_uses_d_inclusive_and_ignores_later_bars():
    days = pd.bdate_range("2025-01-01", periods=40)
    d64 = days.to_numpy(dtype="datetime64[ns]")
    rng = np.random.default_rng(0)
    lo = 100 + rng.random(40)
    hi = lo * (1 + 0.01 + 0.05 * rng.random(40))
    oncal = np.ones(40, dtype=bool)
    i = 30
    v0, n0 = P.vol_v(d64, hi, lo, oncal, d64[i - 19], d64[i])
    assert n0 == 20 and v0 == pytest.approx(np.mean(np.log(hi[i - 19:i + 1] / lo[i - 19:i + 1])))
    hi2 = hi.copy()
    hi2[i + 1:] *= 3.0                                    # 진입일(D+1) 이후 봉 변경 ⇒ v 불변
    assert P.vol_v(d64, hi2, lo, oncal, d64[i - 19], d64[i])[0] == v0
    hi3 = hi.copy()
    hi3[i] *= 3.0                                         # D 봉은 포함
    assert P.vol_v(d64, hi3, lo, oncal, d64[i - 19], d64[i])[0] != v0
    off = oncal.copy()
    off[i - 19:i - 13] = False                            # 달력 밖 봉 6개 ⇒ 14 < 15 ⇒ 결측
    v4, n4 = P.vol_v(d64, hi, lo, off, d64[i - 19], d64[i])
    assert n4 == 14 and math.isnan(v4)


def test_layer_boundaries_right_closed():
    v = np.array([0.1, 0.2, 0.2000001, 0.3, 0.30001, np.nan])
    assert P.layer_of(v, 0.2, 0.3).tolist() == [1, 1, 2, 2, 3, 0]


# ── 에피소드 재계산 ──────────────────────────────────────────────────────────
def test_episodes_recomputed_per_window_and_after_exclusion():
    A = pd.DataFrame(dict(strategy=[MA20] * 6, stock_code=["A", "A", "A", "A", "B", "B"],
                          window=["E", "E", "C", "C", "C", "C"], ci=[10, 11, 12, 14, 12, 13]))
    first, eid = P._episodes(A, np.ones(6, dtype=bool))
    # A: E(10,11) 한 에피소드 · C 첫 행(12)은 E 와 연속이어도 새 에피소드 · 14 는 13 이 없어 새 에피소드 · B: 12,13 하나
    assert first.tolist() == [True, False, True, True, True, False]
    mask = np.array([True, True, True, True, True, False])
    first2, _ = P._episodes(A, mask)
    assert first2.tolist() == [True, False, True, True, True, False]
    mask3 = np.array([False, True, True, True, True, True])   # 첫 행이 ④ 로 빠지면 다음 행이 첫 행
    first3, eid3 = P._episodes(A, mask3)
    assert first3.tolist() == [False, True, True, True, True, False] and eid3[0] == -1


# ── CR1 · CGM 손계산 ─────────────────────────────────────────────────────────
def test_cr1_hand_calculation():
    d = np.array([1.0, 2.0, 3.0, 6.0])
    g = np.array([0, 0, 1, 2])
    # d̄ = 3 · 잔차 −2 −1 0 3 · 종목 합 −3 0 3 · Σ² = 18 · SE² = 3/2 × 18 / 16 = 1.6875
    c = P.cr1(d, g)
    assert c["mean"] == 3.0 and c["G"] == 3 and c["se"] == pytest.approx(math.sqrt(1.6875))
    p, up, down = P.p_norm(c["mean"], c["se"])
    z = 3.0 / math.sqrt(1.6875)
    assert up == pytest.approx(0.5 * math.erfc(z / math.sqrt(2))) and p == pytest.approx(2 * up)
    assert down == pytest.approx(1 - up)


def test_cgm_two_way_hand_calculation():
    d = np.array([1.0, 2.0, 3.0, 6.0])
    g = np.array([0, 0, 1, 2])
    b = np.array([0, 1, 1, 0])
    # V_종목 = 1.6875 · 블록 합 (−2+3, −1+0) = (1, −1) ⇒ V_블록 = 2/1 × 2 / 16 = 0.25
    # 교차 칸 (0,0) −2 · (0,1) −1 · (1,1) 0 · (2,0) 3 ⇒ Σ² 14 · G 4 ⇒ V = 4/3 × 14/16 = 1.1666…
    w = P.cgm2(d, g, b)
    assert w["Vs"] == pytest.approx(1.6875) and w["Vb"] == pytest.approx(0.25)
    assert w["Vsb"] == pytest.approx(14 / 12) and w["Gb"] == 2 and not w["neg"]
    assert w["se"] == pytest.approx(math.sqrt(1.6875 + 0.25 - 14 / 12))
    p, up, down = P.p_t(w["mean"], w["se"], 1)
    from scipy import stats as sst
    assert up == pytest.approx(sst.t.sf(3.0 / w["se"], 1)) and p == pytest.approx(2 * up)


def test_cgm_negative_variance_falls_back_to_max_one_way():
    d = np.array([2.0, -1.0, -1.0, 0.0])
    g = np.array([0, 0, 1, 1])
    b = np.array([0, 1, 0, 1])
    w = P.cgm2(d, g, b)                                   # V_종목 0.25 + V_블록 0.25 − V_교차 0.5 = 0 ⇒ max = 0.25
    assert w["Vs"] == pytest.approx(0.25) and w["Vb"] == pytest.approx(0.25) and w["Vsb"] == pytest.approx(0.5)
    assert w["neg"] and w["se"] == pytest.approx(math.sqrt(max(w["Vs"], w["Vb"])))


# ── 가짜 중심화 · 시드 ───────────────────────────────────────────────────────
def test_fake_is_centered_and_all_plus_signs_give_zero_mean():
    d = np.array([0.5, 1.5, 2.5, 7.5])
    e = P.centered(d)
    assert e.mean() == pytest.approx(0.0) and e.tolist() == pytest.approx([-2.5, -1.5, -0.5, 4.5])
    assert P.cr1(np.ones(4) * e, np.array([0, 1, 2, 3]))["mean"] == pytest.approx(0.0)


def test_fake_seed_is_prefix_t_w_s_v_j():
    got = P.fake_signs(2, 1, 0, 3, 7, 16)
    want = np.random.default_rng([20261003, 2, 1, 0, 3, 7]).choice([-1, 1], 16)
    assert got.tolist() == want.tolist()
    others = [P.fake_signs(*a, 16).tolist() for a in ((1, 1, 0, 3, 7), (2, 0, 0, 3, 7), (2, 1, 1, 3, 7),
                                                      (2, 1, 0, 4, 7), (2, 1, 0, 3, 8))]
    assert all(o != got.tolist() for o in others)
    assert set(np.unique(got)) <= {-1, 1}


def test_block_ids_and_counts():
    ci = np.arange(0, 314)
    assert P.block_ids(ci, 0).max() == 15 and P.n_blocks(314, 20) == 16
    s = P.block_ids(ci, 0, 20, 10)
    assert s[:10].tolist() == [0] * 10 and s[10] == 1 and s[29] == 1 and s[30] == 2
    assert s.max() + 1 == P.n_blocks(314, 20, 10) == 17
    assert P.n_blocks(303, 20) == 16 and P.n_blocks(303, 20, 10) == 16 and P.n_blocks(314, 40) == 8


# ── 판정 라벨 ────────────────────────────────────────────────────────────────
def _cell(mean, p, mde, up=None):
    up = p / 2 if up is None else up
    return dict(mean=mean, p=p, p_up=up if mean > 0 else 1 - up, p_down=up if mean < 0 else 1 - up,
                p2=p, p2_up=up, p2_down=up, mde_lab=mde)


def _cells(overrides):
    cells = {}
    for f in P.STRATS:
        for b in P.VNAMES:
            cells[(f, b)] = {"E": _cell(0.1, 0.5, 0.5), "C": _cell(0.1, 0.5, 0.5)}
    cells.update(overrides)
    return cells


def test_decide_direction_none_and_holds():
    tool = {"E": {f: "CR1" for f in P.STRATS}, "C": {f: "CR1" for f in P.STRATS}}
    cells = _cells({(MA20, "V1"): {"E": _cell(0.6, 1e-5, 0.2), "C": _cell(0.5, 0.01, 0.2, up=0.005)},
                    (MA20, "V2"): {"E": _cell(0.1, 0.4, 0.2), "C": _cell(-0.1, 0.4, 0.2)},
                    (MA20, "V3"): {"E": _cell(-0.5, 1e-5, 0.2), "C": _cell(0.1, 0.4, 0.2)}})
    dec = P.decide(cells, tool, {f: False for f in P.STRATS})
    assert dec[(MA20, "V1")]["label"] == P.LAB_UP and dec[(MA20, "V1")]["m_C"] == 2
    assert dec[(MA20, "V2")]["label"] == P.LAB_NONE
    assert dec[(MA20, "V3")]["label"] == P.LAB_HOLD and P.SUB_CONF in dec[(MA20, "V3")]["subs"]
    assert dec[(MINV, "V1")]["label"] == P.LAB_HOLD and dec[(MINV, "V1")]["subs"] == [P.SUB_POWER]
    tool["E"][MA20] = "fail"                              # E 게이트 탈락 ⇒ p = 1 · 보류(도구)
    dec2 = P.decide(cells, tool, {f: False for f in P.STRATS})
    assert dec2[(MA20, "V1")]["pE"] == 1.0 and dec2[(MA20, "V1")]["subs"] == [P.SUB_TOOL]
    dec3 = P.decide(cells, {"E": {f: "CR1" for f in P.STRATS}, "C": {f: "CR1" for f in P.STRATS}},
                    {MA20: True, MINV: False, DAYT: False})
    assert dec3[(MA20, "V1")]["subs"] == [P.SUB_SAMPLE]


# ── 1로트 × 5 브래킷 손계산 ──────────────────────────────────────────────────
def test_one_lot_five_brackets_hand_calculation():
    d0 = date(2025, 3, 3)
    cal = [d0 + timedelta(days=i) for i in range(8)]
    bars = [  # (open, high, low, close) · 진입가 E = 10,000(k=0 시가)
        (10000, 10200, 9700, 10000),    # k0: −3%·+2% 어느 장벽도 안 닿음
        (9900, 10000, 9350, 9500),      # k1: 저가 −6.5% ⇒ V1(sl 6%) 손절 9,400
        (9500, 10850, 9450, 10800),     # k2: 고가 +8.5% ⇒ V3(tp 8%) 익절 10,800
        (10800, 11100, 10700, 11000),   # k3: 고가 +11% ⇒ 원·V2(tp 10%) 익절 11,000 · 시가 +8% 는 tp 10% 미만
        (11000, 11000, 9100, 9200),     # k4: 저가 −9% ⇒ V4(tp 12% · sl 8%) 손절 9,200
        (9200, 9300, 9100, 9200), (9200, 9300, 9100, 9200), (9200, 9300, 9100, 9200)]
    px = pd.DataFrame(dict(stock_code="000001", date=pd.to_datetime(cal), open=[b[0] for b in bars],
                           high=[b[1] for b in bars], low=[b[2] for b in bars], close=[b[3] for b in bars],
                           volume=1.0))
    env = R.Env(cal=cal, book=R.build_book(px), uni={}, excl={}, imp_dates={}, corp_dates={}, bad_open=set(),
                minute_fn=lambda p: set())
    base = X.ExitRules(0.10, 0.08, 50, "t")
    want = {"orig": ("tp", 11000, 10.0, 3), "V1": ("sl", 9400, -6.0, 1), "V2": ("tp", 11000, 10.0, 3),
            "V3": ("tp", 10800, 8.0, 2), "V4": ("sl", 9200, -8.0, 4)}
    got = {}
    for b in P.BRACKETS:
        rules = base if b == "orig" else P.variant_rules(base, *P.VARIANTS[MA20][b])
        ex = P.sim_lot(env, lambda pos, day: None, rules, "000001", cal[0], 100)
        got[b] = (ex.reason, ex.price, ex.ret_pct, ex.hold_days)
        assert ex.closed and ex.exit_date == cal[want[b][3]]
    for b, (r, px_, ret, k) in want.items():
        assert got[b][0] == r and got[b][1] == pytest.approx(px_) and got[b][2] == pytest.approx(ret)
        assert got[b][3] == k
    d = {b: got[b][2] - got["orig"][2] for b in P.VNAMES}
    assert d == pytest.approx({"V1": -16.0, "V2": 0.0, "V3": -2.0, "V4": -18.0})


def test_guard_mismatch_fields():
    led = pd.DataFrame(dict(exit_reason=["tp", "sl", "tp"], exit_date=["2025-01-02"] * 3,
                            exit_price=["110", "92", "110"], ret_pct=["10", "-8", "10"]))
    bad = P.guard_mismatch(["tp", "sl", "sl"], ["2025-01-02"] * 3, ["110.0000001", "92", "110"], ["10", "-8.1", "10"],
                           led)
    assert bad.tolist() == [False, True, True]


# ── 분석·출력 끝까지(합성 · 스모크) ──────────────────────────────────────────
def test_analyze_end_to_end_synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "N_FAKE", 3)
    monkeypatch.setattr(P, "_LOG_PATH", [tmp_path / "run_log.txt"])
    cal = [d.date() for d in pd.bdate_range("2024-01-02", "2026-09-23")]
    cal_idx = {d: i for i, d in enumerate(cal)}
    codes = [f"{i:06d}" for i in range(12)]
    rng = np.random.default_rng(1)
    rows = []
    for c in codes:
        base_ = 10_000 * (1 + rng.random())
        for d in cal:
            rows.append(dict(stock_code=c, date=pd.Timestamp(d), open=base_, high=base_ * 1.03, low=base_ * 0.97,
                             close=base_, volume=1.0))
    book = R.build_book(pd.DataFrame(rows))
    scan_idx = [i for i, d in enumerate(cal) if "2024-03-13" <= d.isoformat() <= "2026-09-10"]
    recs = []
    for f in P.STRATS:
        for k in range(160):
            i = scan_idx[(k * 37 + P.S_IDX[f] * 11) % len(scan_idx)]
            sd, en = cal[i], cal[i + 1]
            recs.append(dict(strategy=f, scan_date=sd.isoformat(), stock_code=codes[k % 12], entry_date=en.isoformat(),
                             entry_price="10000", qty="100", ref_close="10000", band_ok="True"))
    L = pd.DataFrame(recs).drop_duplicates(["strategy", "scan_date", "stock_code"])
    L["_s"] = L["strategy"].map(P.S_IDX)
    L = L.sort_values(["_s", "scan_date", "stock_code"]).reset_index(drop=True)
    L["key"] = L["strategy"] + "|" + L["scan_date"] + "|" + L["stock_code"]
    L["window"] = L["scan_date"].map(P.window_of)
    L["excl"] = ["" if k % 25 else "②corp_event" for k in range(len(L))]
    L["hend"] = ""
    S = pd.DataFrame({"key": L["key"]})
    for b in P.BRACKETS:
        r = rng.normal(0, 5, len(L)) + (0.5 if b == "V1" else 0.0)
        S[f"{b}_reason"] = np.where(r > 0, "tp", "sl")
        S[f"{b}_exit_date"] = L["entry_date"]
        S[f"{b}_price"] = [str(10000 * (1 + x / 100)) for x in r]
        S[f"{b}_ret"] = [str(x) for x in r]
        S[f"{b}_hold"] = [str(int(x)) for x in rng.integers(0, 10, len(L))]
        S[f"{b}_flags"] = np.where(rng.random(len(L)) < 0.05, X.FLAG_SL_TP_BOTH, "")
        S[f"{b}_status"] = "closed"
    L["exit_reason"], L["exit_date"] = S["orig_reason"], S["orig_exit_date"]
    L["exit_price"], L["ret_pct"] = S["orig_price"], S["orig_ret"]
    bad = np.zeros(len(L), dtype=bool)
    bad[7] = True
    rules = {f: X.ExitRules(R.STRATS[f]["tp"], R.STRATS[f]["sl"], R.STRATS[f]["max_hold"], "t") for f in P.STRATS}
    guard = {f: dict(n=1, mismatch=0, rate=0.0, agree=1.0) for f in P.STRATS}
    ctx = dict(T0=0.0, tm={"load": 1.0, "sim": 1.0}, md5s=dict(ledger_worktree="x", scan_diag_worktree="y"),
               blobs11={}, blobs8={}, sha="0" * 40, fp=dict(sha256="59c14921" + "0" * 56, md5="m", n_stocks=12,
                                                             n_rows=1, window="w"),
               started="s", secs_sim={f: {b: 0.0 for b in P.BRACKETS} for f in P.STRATS},
               n_L={f: 1 for f in P.STRATS}, led=L.assign(exit_reason="tp"))
    assert P.analyze(L, S, bad, cal, cal_idx, book, rules, guard, ctx, tmp_path) == 0
    txt = (tmp_path / "RESULTS_exit_pair.md").read_text(encoding="utf-8")
    assert "## 3. 12셀 판정표" in txt and txt.count("| ma20 | V") >= 4
    log_ = (tmp_path / "run_log.txt").read_text(encoding="utf-8")
    assert log_.index("[게이트 확정]") < log_.index("[판정]")            # 게이트 «뒤»에 진짜 p·라벨
    lots = pd.read_csv(tmp_path / "pair_lots.csv", dtype=str, keep_default_na=False)
    assert len(lots) == len(L) and lots.loc[7, "excl"].startswith("④")
