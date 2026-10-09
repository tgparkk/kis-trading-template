"""봉인 → 개봉 전체 흐름(합성 세계 · DB 없음) — 봉인은 ⓐ·이벤트 팔 극값을 만들지 않는다 · 게이트 로그가 p 보다 먼저 ·
1회 실행 표식 · 봉인 값 재계산 일치."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from backtest.concept_axes.stoploss_rebound import author_exit as AE
from backtest.concept_axes.stoploss_rebound import lots as LT
from backtest.concept_axes.stoploss_rebound import run as R
from backtest.concept_axes.stoploss_rebound.tests import synth as SY

FP = {"vtr": "a", "daily_prices": "b", "corp_events": "c", "minute_candles": "d"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    D = SY.world()
    monkeypatch.setattr(R, "RESULTS", tmp_path)
    monkeypatch.setattr(R, "SEALED_MD", tmp_path / "sealed_report.md")
    monkeypatch.setattr(R, "META", tmp_path / "run_meta.json")
    monkeypatch.setattr(R, "OPEN_LOG", tmp_path / "open_log.txt")
    monkeypatch.setattr(R, "preconditions", lambda conn, stage: None)
    monkeypatch.setattr(R, "fingerprint", lambda conn, codes, mk: dict(FP))
    monkeypatch.setattr(R, "rebuy_count", lambda conn, D: dict(rebuy_buys_in_E=1, rebuy_buys_other_stop=0,
                                                               stops_E_with_rebuy=1, stop_ids=[D.events[0].id]))
    monkeypatch.setattr(R, "integrity_counts", lambda conn: {"전 전략": dict(sell=1, linked=1, label_mismatch=0,
                                                                         code_mismatch=0, sell_before_buy=0,
                                                                         dup_sell_per_buy=0)})
    monkeypatch.setattr(R, "side_counts", lambda conn, D: dict(other_stop={}, multi_strategy_same_day=0))
    monkeypatch.setattr(R, "head_sha", lambda: "f" * 40)

    def load_all(conn, stage):
        if stage == "open":
            SY.set_stop_prices(D)
        return D, dict(n_events=len(D.events), n_lots=len(D.lots), codes=sorted(D.rows))

    monkeypatch.setattr(R, "load_all", load_all)
    monkeypatch.setattr(R, "_git", lambda *a: __import__("subprocess").CompletedProcess(a, 0, "", ""))
    return D, tmp_path


def test_sealed_stage_never_computes_author_exit_or_event_extremes(env, monkeypatch):
    D, tmp = env

    def boom(*a, **k):
        raise AssertionError("봉인 단계에서 ⓐ 계산 금지")

    monkeypatch.setattr(AE, "author_exit", boom)
    monkeypatch.setattr(LT, "a_arm", boom)
    assert R.run_sealed(None) == R.EXIT_OK
    LS = R.lot_stage(D)
    P = R.sealed_payload(None, D, LS)
    for h in R.HS:
        for u in P["units"][h]:
            if u.win is not None:
                assert u.win.hi is None and u.win.lo is None           # 이벤트 팔 R′/D′ 재료 없음
    assert all(e.stop_px is None for e in D.events)
    md = (tmp / "sealed_report.md").read_text(encoding="utf-8")
    assert "T3 n =" in md and "충실도 게이트" in md and "MDE" in md
    meta = json.loads((tmp / "run_meta.json").read_text(encoding="utf-8"))
    assert "sealed" in meta and "open" not in meta and meta["sealed"]["fp"] == FP


def test_full_flow_gate_logged_before_p_and_single_open(env):
    D, tmp = env
    assert R.run_sealed(None) == R.EXIT_OK
    (tmp / "sealed_report.md").write_text((tmp / "sealed_report.md").read_text(encoding="utf-8"), encoding="utf-8")
    assert R.run_open(None) == R.EXIT_OK
    log = (tmp / "open_log.txt").read_text(encoding="utf-8").splitlines()
    gate_idx = [i for i, ln in enumerate(log) if "[게이트]" in ln]
    t3_idx = [i for i, ln in enumerate(log) if "[T3]" in ln]
    assert gate_idx and t3_idx and max(gate_idx) < min(t3_idx)
    res = sorted(tmp.glob("RESULTS_*.md"))
    assert len(res) == 1 and "라벨:" in res[0].read_text(encoding="utf-8")
    meta = json.loads((tmp / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["open"]["label"] in ("ⓐ 우위", "ⓐ 우위 아님", "판정 불가")
    with pytest.raises(R.Refuse) as e:
        R.run_open(None)
    assert e.value.code == R.EXIT_ORDER and "1회 실행" in e.value.reason


def test_open_refuses_when_sealed_numbers_differ(env):
    D, tmp = env
    assert R.run_sealed(None) == R.EXIT_OK
    meta = json.loads((tmp / "run_meta.json").read_text(encoding="utf-8"))
    meta["sealed"]["numbers"]["shape"]["n"] += 1
    (tmp / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(R.Refuse) as e:
        R.run_open(None)
    assert e.value.code == R.EXIT_FINGERPRINT
    assert "open" not in json.loads((tmp / "run_meta.json").read_text(encoding="utf-8"))   # 거부는 표식 «전»


def test_day0_live_non_stop_lots_have_zero_delta(env):
    D, tmp = env
    LS = R.lot_stage(D)
    SY.set_stop_prices(D)
    T = R.t3_open(D, LS, tmp / "log.txt")
    hits = 0
    for p in LS["sample"]:
        lt = p.lot
        if LT.is_day0_live(lt) and not lt.sell_reason.startswith("손절 실행"):
            hits += 1
            a, b = T["A"][lt.buy_id], LS["b"][lt.buy_id]
            assert a.ret_M == b.ret_M and a.ret_L == b.ret_L
    assert hits > 0


def test_fidelity_denominator_excludes_day0_and_pre_0826(env):
    D, _ = env
    LS = R.lot_stage(D)
    n_den = sum(g["n"] for g in LS["fid"].values())
    want = sum(1 for lt in D.lots if lt.d0 >= R.SPLIT_DAY and not LT.is_day0_live(lt))
    assert n_den == want
    assert all(g["pass"] for g in LS["fid"].values())          # 합성 실제 청산 = ⓑ 시뮬 → 일치


def test_fidelity_failing_strategy_is_dropped_from_t3(env, monkeypatch):
    D, _ = env
    for lt in D.lots:
        if lt.strategy == "book_pullback_ma5" and lt.sell_ts is not None and lt.sell_ts.date() != lt.d0:
            lt.sell_reason = "EMA20 추세반전"
    LS = R.lot_stage(D)
    assert not LS["fid"]["book_pullback_ma5"]["pass"]
    assert all(p.lot.strategy != "book_pullback_ma5" for p in LS["sample"])


def test_t3_blocks_cover_entry_window_only(env):
    D, _ = env
    blk = R.t3_blocks(D)
    assert min(blk) == R.START and max(blk) == D.cal[D.i_asof - LT.H]
    LS = R.lot_stage(D)
    assert all(p.block is not None for p in LS["sample"])


def _shift_sells(D, strategy, n_days):
    """그 전략 실제 매도일을 KOSPI 거래일 n 일 뒤로 민다(사유는 그대로)."""
    pos = {d: i for i, d in enumerate(D.cal)}
    moved = 0
    for lt in D.lots:
        if (lt.strategy == strategy and lt.sell_ts is not None and lt.sell_ts.date() != lt.d0
                and lt.d0 >= R.SPLIT_DAY and pos[lt.sell_ts.date()] + n_days <= D.i_asof):
            lt.sell_ts = datetime.combine(D.cal[pos[lt.sell_ts.date()] + n_days], lt.sell_ts.time())
            moved += 1
    return moved


def test_fidelity_date_match_allows_one_kospi_day():
    D = SY.world()
    assert _shift_sells(D, "book_pullback_ma20", 1) > 0
    g = R.lot_stage(D)["fid"]["book_pullback_ma20"]
    assert g["date_rate"] == 1.0 and g["full_rate"] < 1.0           # ±1 은 허용 · 정확 일치율은 병기
    D2 = SY.world()
    assert _shift_sells(D2, "book_pullback_ma20", 2) > 0
    assert R.lot_stage(D2)["fid"]["book_pullback_ma20"]["date_rate"] < 1.0


def test_load_all_sealed_does_not_join_stop_price(monkeypatch):
    seen = []
    monkeypatch.setattr(R, "load_calendar", lambda conn: [R.D_ASOF])
    monkeypatch.setattr(R, "load_events", lambda conn, with_price: seen.append(with_price) or [])
    monkeypatch.setattr(R, "load_lots", lambda conn, sql=R.LOT_SQL: [])
    monkeypatch.setattr(R, "fetch", lambda conn, sql, args=None: [(0,)])
    monkeypatch.setattr(R, "load_controls", lambda conn, ev: {})
    monkeypatch.setattr(R, "load_rows", lambda conn, codes: {})
    monkeypatch.setattr(R, "load_corp", lambda conn, codes: ({}, {}))
    monkeypatch.setattr(R, "load_live_rules", lambda: ({s: R.X.ExitRules(*v[:2], v[2]) for s, v in R.EXPECT_RULES.items()},
                                                       {}))
    R.load_all(None, "sealed")
    R.load_all(None, "open")
    assert seen == [False, True]


def test_sealed_refuses_after_open(env):
    D, tmp = env
    (tmp / "run_meta.json").write_text(json.dumps({"open": {"started_at": "x"}}), encoding="utf-8")
    with pytest.raises(R.Refuse) as e:
        R.run_sealed(None)
    assert e.value.code == R.EXIT_ORDER
