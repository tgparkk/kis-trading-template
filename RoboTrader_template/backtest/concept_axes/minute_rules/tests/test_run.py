"""run(2단계) — A1(k=0 탐침 1회 · simulate_lot 호환) · 로트 조립 · 체결 모델 a·b·c · 가드 · 캐시 · 같은 바이트.

합성 자료만(DB 0). 사전등록 §9 ⑫·⑭~⑳ 의 run 수준판은 `test_stage2_prereg.py`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.minute_rules import data as D
from backtest.concept_axes.minute_rules import engine as E
from backtest.concept_axes.minute_rules import rules as R
from backtest.concept_axes.minute_rules import run as RUN

from .synth import flat, path, put

DT = "daytrading_3methods_breakout"
RULES = X.ExitRules(0.10, 0.10, 10, "test")


def cal_from(start: date, n: int):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


CAL = cal_from(date(2025, 6, 2), 40)
D0, D1 = CAL[4], CAL[5]                       # 신호일 · 진입일
CTX = E.DayCtx("000001", D1, band_hi=10300.0, prev_close=10000.0, prev_day_volume=50_000.0)


def daily_flat(code="000001", px=10000.0, days=CAL, over=None):
    out = {d: X.Bar(d, px, px, px, px) for d in days}
    out.update(over or {})
    return {code: out}


def path_of(bars_d, entry=D1, end=None, max_hold=10):
    cal_idx = {d: i for i, d in enumerate(CAL)}
    return RUN.build_path(CAL, cal_idx, bars_d, entry, max_hold, end or CAL[-1])


class CountingProbe:
    def __init__(self, fire_on=None, reason="data_exit"):
        self.calls = []
        self.fire_on = set(fire_on or ())
        self.reason = reason

    def __call__(self, pos, day):
        self.calls.append(day)
        return self.reason if day in self.fire_on else None


# ── A1 ───────────────────────────────────────────────────────────────────
def test_a1_naive_simulate_lot_would_double_count_k0():
    """A1 재현 — 미청산 m_close Pos 를 그대로 simulate_lot 에 넘기면 k=0 플래그·탐침이 다시 붙는다(bridge 필요)."""
    pos = E.make_pos(CTX, 2, 10000.0)
    bd = daily_flat(over={D1: X.Bar(D1, 10000, 12000, 8000, 10000)})["000001"]
    ex = X.simulate_lot(pos, RULES, path_of(bd), CountingProbe(fire_on={D1}))
    assert X.FLAG_NO_D_TOUCH in ex.flags and X.FLAG_K0_DATA in ex.flags and ex.phase == X.PHASE_ENTRY


def test_a1_continue_daily_skips_k0_touch_and_probe():
    pos = E.make_pos(CTX, 2, 10000.0)
    bd = daily_flat(over={D1: X.Bar(D1, 10000, 12000, 8000, 10000)})["000001"]   # k=0 일봉 고저가 익절·손절선을 넘음
    probe = CountingProbe(fire_on={D1})
    ex = E.continue_daily(pos, RULES, path_of(bd), probe)
    assert X.FLAG_NO_D_TOUCH not in ex.flags and X.FLAG_K0_DATA not in ex.flags
    assert ex.phase != X.PHASE_ENTRY and ex.reason == X.EXIT_MAX_HOLD and ex.hold_days == 10
    assert D1 not in probe.calls and len(probe.calls) == 9            # k=1..9 탐침(k=10 은 open_phase 에서 닫힘)


def test_a1_pos_to_simulate_lot_compat_k1_touch_and_mtm():
    """미청산 `Pos → simulate_lot` 호환 1건 — k=1 장중 익절(선 가격) · 경로가 k=0 뿐이면 일봉 종가 마감 평가(G2)."""
    pos = E.make_pos(CTX, 30, 10000.0)
    assert (pos.entry_basis, pos.entry_time, pos.qty) == (E.BASIS_M_CLOSE, datetime.combine(D1, datetime.min.time())
                                                          .replace(hour=9, minute=30), 100)
    bd = daily_flat(over={CAL[6]: X.Bar(CAL[6], 10100, 11500, 10000, 11000)})["000001"]
    ex = E.continue_daily(pos, RULES, path_of(bd), RUN.never_probe)
    assert (ex.reason, ex.exit_date, ex.hold_days, ex.phase) == (X.EXIT_TP, CAL[6], 1, X.PHASE_AFTER)
    assert ex.price == pytest.approx(11000) and ex.ret_pct == pytest.approx(10.0)
    only_k0 = {D1: X.Bar(D1, 10000, 10500, 9900, 10400)}
    mtm = E.continue_daily(pos, RULES, path_of(only_k0, end=D1), RUN.never_probe)
    assert mtm.status == "open" and mtm.price == 10400 and mtm.ret_pct == pytest.approx(4.0) and X.FLAG_MTM in mtm.flags


def test_a1_continue_daily_gap_tp_at_open_k1():
    pos = E.make_pos(CTX, 2, 10000.0)
    bd = daily_flat(over={CAL[6]: X.Bar(CAL[6], 11200, 11300, 11100, 11200)})["000001"]
    ex = E.continue_daily(pos, RULES, path_of(bd), RUN.never_probe)
    assert ex.reason == X.EXIT_TP and ex.price == 11200 and ex.phase == X.PHASE_OPEN and X.FLAG_GAP_TP in ex.flags


def test_a1_continue_daily_requires_positive_tp_sl():
    with pytest.raises(ValueError):
        E.continue_daily(E.make_pos(CTX, 2, 10000.0), X.ExitRules(0.0, 0.1, 10), [], RUN.never_probe)


def test_a1_k0_probe_exactly_once_per_model_before_minute_exit():
    b = flat()
    put(b, 3, 10500, 10500, 10500, 10500)                  # 09:03 시가 밴드 밖 → 모델 b 결측
    probe = CountingProbe()
    bd = daily_flat()["000001"]
    out = RUN.arm_result(b, CTX, R.BASELINE, RULES, path_of(bd), probe, 10000.0)
    assert out["entered"] and out["b_missing"] and out["b_ret"] is None
    assert probe.calls.count(D1) == 2                      # 모델 a·c 각 1회(b 는 결측이라 체결 없음)
    probe2 = CountingProbe()
    RUN.arm_result(flat(), CTX, R.BASELINE, RULES, path_of(bd), probe2, 10000.0)
    assert probe2.calls.count(D1) == 3                     # a·b·c


def test_a1_k0_probe_fires_closes_at_entry_price_before_minute_exit():
    b = flat()
    put(b, 10, 10000, 11100, 10000, 10000)                 # 분 단위면 익절이었을 봉
    out = RUN.arm_result(b, CTX, R.BASELINE, RULES, path_of(daily_flat()["000001"]), CountingProbe(fire_on={D1}),
                         10000.0)
    assert out["exit_reason"] == "data_exit" and out["ret"] == 0.0 and out["exit_phase"] == X.PHASE_ENTRY
    assert out["k0_flags"] == X.FLAG_K0_DATA and out["exit_time"] == "090200"


# ── 체결 모델 · 청산 ───────────────────────────────────────────────────────
def test_models_a_b_c_and_k0_minute_exit():
    b = flat(10500.0)
    put(b, 4, 10500, 10500, 10290, 10500)                  # 09:04 저가만 상한 → 경계 모델 c 진입 10,300
    path(b, 8, [10200])                                    # 09:08 종가 진입(a) · 09:09 시가 10,200(b)
    put(b, 20, 10200, 11300, 10200, 11250)                 # 익절선 11,220 → a·b 익절 · c 는 11,330 미달
    out = RUN.arm_result(b, CTX, R.BASELINE, RULES, path_of(daily_flat()["000001"]), RUN.never_probe, 10000.0)
    assert out["entry_time"] == "090800" and out["px_tick"] == 10200 and out["exit_phase"] == "k0_minute"
    assert out["exit_reason"] == X.EXIT_TP and out["ret"] == pytest.approx(10.0)
    assert out["b_time"] == "090900" and out["b_px"] == 10200 and out["b_ret"] == pytest.approx(10.0)
    assert out["c_time"] == "090400" and out["c_px"] == 10300.0
    assert out["c_ret"] == pytest.approx((10000 / 10300 - 1) * 100)          # c = 일봉 경로 끝(만기 시가 10,000)
    assert out["close_ret"] == pytest.approx((10000 / 10200 - 1) * 100)


def test_cash_when_never_in_band():
    out = RUN.arm_result(flat(20000.0), CTX, R.BASELINE, RULES, path_of(daily_flat()["000001"]), RUN.never_probe,
                         20000.0)
    assert not out["entered"] and out["ret"] == 0.0 and out["skip_reason"] == E.SKIP_NO_ENTRY and out["c_ret"] == 0.0


def test_simulate_arms_filter_reuses_r0_0905_once(monkeypatch):
    calls = []
    real = RUN.arm_result

    def spy(bars, ctx, rule, *a, **k):
        calls.append(rule.rule_id)
        return real(bars, ctx, rule, *a, **k)

    monkeypatch.setattr(RUN, "arm_result", spy)
    res = RUN.simulate_arms(flat(), CTX, RUN.MAIN_ARMS, RULES, path_of(daily_flat()["000001"]), RUN.never_probe,
                            10000.0)
    assert calls.count("R0_0905") == 1 and "R4" not in calls and "R5" not in calls
    for f in ("R4", "R5"):
        assert {k: v for k, v in res[f].items() if k != "label"} == res["R0_0905"]
        assert res[f]["label"] in (E.LABEL_KEEP, E.LABEL_FILTER, E.LABEL_UNDETERMINED)


# ── 로트 조립 · 가드 ───────────────────────────────────────────────────────
def _ledger_row(**kw):
    r = dict(strategy=DT, scan_date=D0.isoformat(), stock_code="000001", rank="1", ref_close="10000", band_lo="",
             band_hi="10300", band_ok="True", entry_date=D1.isoformat(), exit_reason="sl", flags="survivor_universe")
    r.update(kw)
    return r


def test_lots_from_ledger_window_and_guards():
    rows = [_ledger_row(), _ledger_row(stock_code="000002", entry_date=CAL[30].isoformat()),
            _ledger_row(stock_code="000003", entry_date="")]
    lots = RUN.lots_from_ledger(rows, [DT], D1, CAL[20])
    assert [x.code for x in lots] == ["000001"] and lots[0].band_ok_open is True and lots[0].band_hi == 10300
    with pytest.raises(SystemExit):
        RUN.lots_from_ledger([_ledger_row(exit_reason="trail_ma")], [DT], D1, CAL[20])
    with pytest.raises(SystemExit):
        RUN.lots_from_ledger([_ledger_row(band_hi="10400")], [DT], D1, CAL[20])


def test_guard_spec_rejects_ma20_and_mismatched_rules():
    meta = {"exit_rules": {DT: {"tp": 0.1, "sl": 0.1, "max_hold_days": 10}}}
    RUN.guard_spec([DT], meta)
    with pytest.raises(SystemExit):
        RUN.guard_spec(["book_pullback_ma20"], meta)
    with pytest.raises(SystemExit):
        RUN.guard_spec([DT], {"exit_rules": {DT: {"tp": 0.1, "sl": 0.08, "max_hold_days": 10}}})


def test_corp_event_window_is_d_to_d1_inclusive():
    lots = [RUN.Lot("A", DT, D0, D1, c, "1", 1.0, None, 1.03) for c in ("A", "B", "C", "D")]
    RUN.corp_flags(lots, {"A": [D0], "B": [D1], "C": [CAL[3]], "D": [CAL[6]]})
    assert [x.corp_event for x in lots] == [True, True, False, False]


def test_era_tv_bucket_vi_suspect():
    assert RUN.era_of(date(2026, 6, 22)) == "m533" and RUN.era_of(date(2026, 6, 23)) == "top300"
    assert RUN.era_of(date(2026, 10, 6)) == "snap100"
    assert [RUN.tv_bucket(x) for x in (1, 300, 300.5, 600, 1000, 1001, None)] == \
        ["le300", "le300", "301_600", "301_600", "601_1000", "gt1000", ""]
    b = flat(10000.0)
    obs = np.ones(E.N_SLOTS, bool)
    assert not RUN.vi_suspect(b, obs)
    obs[10:12] = False                                     # 빈 분 2 뒤 시가 +3%
    put(b, 12, 10300, 10300, 10300, 10300)
    assert RUN.vi_suspect(b, obs)
    obs2 = np.ones(E.N_SLOTS, bool)
    obs2[10] = False                                       # 빈 분 1 은 아님
    assert not RUN.vi_suspect(b, obs2)


def test_gap_cache_fetches_once_persists_and_verifies(tmp_path, monkeypatch):
    fetched = []
    fp = {"n": 380}

    def fake_fetch(conn, days):
        days = sorted(days)
        fetched.append(days)
        return [(d.strftime("%Y%m%d"), "000002", [[0, 25]]) for d in days] + \
               [(d.strftime("%Y%m%d"), "000001", None) for d in days]

    monkeypatch.setattr(D, "fetch_market_gap_rows", fake_fetch)
    monkeypatch.setattr(RUN.GapCache, "fingerprints", lambda self, keys: {k: [fp["n"], 2] for k in keys})
    p = tmp_path / "gap.json"
    c = RUN.GapCache(None, p)
    rows = c.rows([D1, D0])
    assert len(fetched) == 1 and c.misses == 2 and rows[0] == (D0.strftime("%Y%m%d"), "000001", None)
    assert rows[1] == (D0.strftime("%Y%m%d"), "000002", [[0, 25]]) and c.verify() == []
    c2 = RUN.GapCache(None, p)
    assert c2.rows([D1]) == [(D1.strftime("%Y%m%d"), "000001", None), (D1.strftime("%Y%m%d"), "000002", [[0, 25]])]
    assert len(fetched) == 1 and c2.hits == 1
    fp["n"] = 381                                          # DB 재적재(백필) → 지문이 달라짐 = 낡음(A2)
    assert c2.verify() == [D1.strftime("%Y%m%d")]
    stats = D.market_gap_stats(rows, {"000001": "KOSDAQ", "000002": "KOSDAQ"})
    assert stats[(D0, "KOSDAQ")] == (1, 2)                 # 2종목 중 1 → 50% → market_gap_day(≥50%)


def test_gap_cache_ignores_other_version(tmp_path):
    p = tmp_path / "gap.json"
    p.write_text(json.dumps({"version": 1, "days": {"20250602": [["000001", None]]}}), encoding="utf-8")
    assert RUN.GapCache(None, p).days == {}


class FakeGit:
    """`git` 호출 흉내 — (인자 튜플 앞부분) → (returncode, stdout)."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, *args):
        self.calls.append(args)
        for k, (rc, out) in self.table.items():
            if args[: len(k)] == k:
                return subprocess.CompletedProcess(args, rc, out, "")
        return subprocess.CompletedProcess(args, 0, "", "")


def test_check_explore_requires_committed_unmodified_and_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(RUN, "REPO", tmp_path)
    doc = tmp_path / "RESULTS_explore.md"
    with pytest.raises(SystemExit):
        RUN.check_explore("00", FakeGit({}), doc)                        # 파일 없음
    doc.write_bytes(b"x")
    h = hashlib.sha256(b"x").hexdigest()
    with pytest.raises(SystemExit):
        RUN.check_explore(h, FakeGit({("ls-files",): (1, "")}), doc)      # 추적 안 됨(A6)
    with pytest.raises(SystemExit):
        RUN.check_explore(h, FakeGit({("diff",): (1, "")}), doc)          # 커밋 안 된 변경
    with pytest.raises(SystemExit):
        RUN.check_explore("00", FakeGit({}), doc)                        # 해시 불일치
    from backtest.concept_axes.minute_rules import analyze as A
    (tmp_path / "E").mkdir()
    (tmp_path / "E" / "run_meta.json").write_text("{}", encoding="utf-8")
    code = {"x.py": "1"}
    doc.with_suffix(".json").write_text(json.dumps(dict(
        spec_sha256=A.SPEC_SHA256, B=A.SPEC["B"], results_md_sha256=h,
        prov=dict(code_digest=A.code_digest(code), run_meta={"E": hashlib.sha256(b"{}").hexdigest()}))),
        encoding="utf-8")
    got = RUN.check_explore(h, FakeGit({("log",): (0, "abc123\n")}), doc, code_now=code, results_dir=tmp_path)
    assert got == {"sha256": h, "commit": "abc123"}
    with pytest.raises(SystemExit):                                       # G1 — 지금 코드와 E 코드가 다름
        RUN.check_explore(h, FakeGit({}), doc, code_now={"x.py": "2"}, results_dir=tmp_path)


def test_require_clean_tree_ignores_results_only():
    ok = (" M RoboTrader_template/backtest/concept_axes/minute_rules/results/E/lots_rule.csv\n"
          "?? RoboTrader_template/backtest/concept_axes/minute_rules/results/cache/market_gap_rows.json\n")
    RUN.require_clean_tree(FakeGit({("status",): (0, ok)}))
    with pytest.raises(SystemExit):
        RUN.require_clean_tree(FakeGit({("status",): (0, ok + "?? RoboTrader_template/backtest/x.py\n")}))
    assert RUN.dirty_paths('R  a.py -> "RoboTrader_template/b.py"\n') == ["RoboTrader_template/b.py"]


def test_sealed_dir_outside_repo(monkeypatch, tmp_path):
    monkeypatch.delenv(RUN.SEALED_ENV, raising=False)
    assert RUN.sealed_dir(None) == RUN.SEALED_DEFAULT.resolve()
    monkeypatch.setenv(RUN.SEALED_ENV, str(tmp_path / "s"))
    assert RUN.sealed_dir(None) == (tmp_path / "s").resolve()
    with pytest.raises(SystemExit):
        RUN.sealed_dir(str(RUN.RESULTS / "sealed"))                     # 레포 안 = 거부(B1)
    with pytest.raises(ValueError):
        RUN.SEALED_DEFAULT.resolve().relative_to(RUN.REPO.resolve())


def test_window_dates_pure():
    today = CAL[25]
    asof, cal2, pend, c2 = RUN.window_dates(CAL, today, None, [DT])
    assert asof == CAL[24] and cal2[-1] == CAL[24] and pend == {"A": RUN.A_END, "B": CAL[24]}
    assert c2 == {DT: CAL[14]}                              # asof 에서 10거래일 앞
    a2, _, _, c22 = RUN.window_dates(CAL, today, CAL[20].isoformat(), [DT, "minervini_volume_dryup"])
    assert a2 == CAL[20] and c22 == {DT: CAL[10], "minervini_volume_dryup": CAL[0]}
    with pytest.raises(SystemExit):
        RUN.window_dates(CAL, today, "2025-06-07", [DT])                 # 토요일 = 거래일 아님


def test_code_hashes_cover_minute_rules_and_deps():
    h = RUN.code_hashes()
    assert "backtest/concept_axes/minute_rules/run.py" in h and "backtest/concept_axes/minute_rules/analyze.py" in h
    assert all(d in h for d in RUN.CODE_DEPS) and all(len(v) == 64 for v in h.values())


def test_regime_cols_kospi20_and_day_ret():
    kospi = {d: 100.0 + i for i, d in enumerate(CAL)}
    lot = RUN.Lot("A", DT, CAL[24], CAL[25], "000001", "1", 1.0, None, 1.03)
    RUN.regime_cols([lot], CAL, kospi)
    assert lot.kospi20 == pytest.approx((124 / 104 - 1) * 100)
    assert lot.kospi_day_ret == pytest.approx((125 / 124 - 1) * 100)
    early = RUN.Lot("A", DT, CAL[3], CAL[4], "000001", "1", 1.0, None, 1.03)
    RUN.regime_cols([early], CAL, kospi)
    assert early.kospi20 is None and early.kospi_day_ret is not None


def test_windows_arm_sets_are_sealed_apart():
    for w in ("E", "C", "C2"):
        assert set(RUN.WINDOWS[w].arms) == {k for k, r in R.REGISTRY.items() if r.family != R.FAMILY_INDEPENDENT}
    assert set(RUN.WINDOWS["U"].arms) == {"R0"} | {k for k, r in R.REGISTRY.items()
                                                    if r.family == R.FAMILY_INDEPENDENT}
    assert RUN.WINDOWS["C"].sealed_after_explore and RUN.WINDOWS["C2"].sealed_after_explore
    assert RUN.WINDOWS["U"].sealed_after_explore and not RUN.WINDOWS["E"].sealed_after_explore   # 수정 1 4-나


def test_meta_json_dates_serialize():
    s = json.dumps({"d": D1, "m": {"A": D0}}, default=RUN._fmt)
    assert D1.isoformat() in s and D0.isoformat() in s


def test_fake_timing_fast_path_equals_run_day_with_pred():
    """가짜 시점 규칙 빠른 길(밴드 안 분 목록) = `run_day(pred = t ≥ u)` + 같은 청산."""
    rng = np.random.default_rng(4)
    bd = path_of(daily_flat()["000001"])
    for _seed in range(12):
        b = flat(10000.0)
        path(b, 0, np.round(10000.0 * np.cumprod(1 + rng.normal(0, 0.012, E.N_CONT)), -1))
        for u in (2, 7, 33, 60):
            def pred(view, _ctx, u=u):
                return len(view) - 1 >= u
            ref = E.run_day(b, CTX, pred, RULES.tp, RULES.sl)
            got = RUN.fake_timing_rets(b, CTX, u, RULES, bd, RUN.never_probe)
            assert got["entered"] == ref.entered
            if ref.entered:
                fin = RUN.finish(b, CTX, ref.entry.idx, ref.entry.px, ref.entry.idx, RULES, bd, RUN.never_probe,
                                 day_exit=ref.exit)
                assert got["entry_time"] == ref.entry.time and got["ret"] == fin["ret"]
