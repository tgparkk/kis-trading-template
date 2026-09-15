"""통합 1건 — 라이브 `screener_snapshots` 하루를 재현해 M1~M4 를 «인쇄»한다.

🔴 **판정 언어를 쓰지 않는다**(「유의」·「기각」·「통과」). 이 테스트가 확인하는 것은
   **파이프라인이 끝까지 돌고 지표가 산출된다**는 것뿐이다. 판정은 `--gate` 리포트가 한다.
🔴 실 DB 필요(SELECT 전용). 없으면 skip.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.concept_axes.replayer import flags as flg
from backtest.concept_axes.replayer import gate as gt
from backtest.concept_axes.replayer import ledger as ldg
from backtest.concept_axes.replayer import loader as ldr
from backtest.concept_axes.replayer import run as rn
from backtest.concept_axes.replayer import scan as scn

D = "2026-08-20"          # 노출 구간(≤2026-09-02)의 평일 · 설계서 §4-4-c
HIST = "2026-01-02"       # 90봉 워밍업에 충분


@pytest.mark.db
@pytest.mark.parametrize("key", ["ma20", "daytrading"])
def test_replay_one_live_day_prints_m1_to_m4(db_conn, key, capsys):
    sname = rn.STRATEGIES[key]["name"]
    live = rn.load_live_snapshots(db_conn, sname, D, D)
    if live.empty:
        pytest.skip("{} 의 {} 스냅샷이 없다".format(sname, D))
    segs = rn.params_segments(live)
    assert len(segs) == 1, "하루짜리 대조에 params_hash 가 둘일 수 없다"
    params = segs[0]["params"]

    px = ldr.load_prices(db_conn, HIST, D)
    names = ldr.load_stock_names(db_conn)
    markets = ldr.load_market_labels(db_conn)
    corp = ldr.load_corp_events(db_conn)
    bar_flags = flg.compute_bar_flags(px)
    cls = ldr.classify_exclusions(sorted(px["stock_code"].astype(str).unique()), names)
    excluded = {c for c, v in cls.items() if v["excluded"]}

    r = rn.replay(px, bar_flags, key, scan_dates=[pd.Timestamp(D)], params=params,
                  excluded=excluded, names=names, markets=markets, corp_events=corp,
                  meta={"run_id": "test", "git_sha": "test", "db_fingerprint_hash": "test"},
                  max_candidates=int(params.get("max_candidates", 20)))
    led = r["ledger"]

    # 원장 자체의 최소 계약 — 스키마 · 순위 · 「후방만」
    assert list(led.columns) == ldg.LEDGER_COLUMNS
    assert led["rank"].tolist() == list(range(1, len(led) + 1))
    assert led["in_top_k"].sum() == min(scn.LIVE_K, len(led))
    assert (led["scan_date"] == pd.Timestamp(D)).all()
    assert "forward" not in " ".join(led.columns).lower()

    days = rn.build_day_pairs(r["live"] if "live" in r else live, led)
    if "live" not in r:
        days = rn.build_day_pairs(live, led)
    m = gt.compute_metrics(days)
    with capsys.disabled():
        print("\n[{} {}] 라이브 {} · 재현 {} · "
              "M1={:.4f} M2={} M3={:.4f} M4={:.4f}".format(
                  sname, D, len(live), len(led), m["M1"],
                  "n/a" if m["M2"] != m["M2"] else "{:.4f}".format(m["M2"]),
                  m["M3"], m["M4"]))
        only_live = sorted(set(days[0].live) - set(days[0].replay))
        only_replay = sorted(set(days[0].replay) - set(days[0].live))
        print("     live_only={} · replay_only={}".format(only_live, only_replay))

    # 🔑 지표가 «산출»됐다는 것만 확인한다 — 문턱 판정은 여기서 하지 않는다.
    assert 0.0 <= m["M1"] <= 1.0
    assert 0.0 <= m["M3"] <= 1.0


@pytest.mark.db
def test_ledger_is_byte_identical_when_replayed_twice(db_conn, capsys):
    """리뷰 M-5 — 같은 날을 두 번 돌리면 원장이 **완전히 같아야** 한다.

    🔴 메타 4컬럼(`run_id`·`git_sha`·`db_fingerprint_hash`·`replayer_params_hash`)을
    원장 안에 두면 `run_id` 때문에 항상 달라져 «결정성» 을 원장으로 증명할 수 없다
    ⇒ `ledger_meta.json` 사이드카로 분리했고, 이 테스트가 그 분리를 동결한다.
    """
    key = "ma20"
    px = ldr.load_prices(db_conn, HIST, D)
    names = ldr.load_stock_names(db_conn)
    markets = ldr.load_market_labels(db_conn)
    corp = ldr.load_corp_events(db_conn)
    bar_flags = flg.compute_bar_flags(px)
    cls = ldr.classify_exclusions(sorted(px["stock_code"].astype(str).unique()), names)
    excluded = {c for c, v in cls.items() if v["excluded"]}

    def once(run_id):
        return rn.replay(px, bar_flags, key, scan_dates=[pd.Timestamp(D)], params=None,
                         excluded=excluded, names=names, markets=markets,
                         corp_events=corp,
                         meta={"run_id": run_id, "git_sha": "test",
                               "db_fingerprint_hash": "test"},
                         max_candidates=20)

    a, b = once("run-A"), once("run-B")
    assert list(a["ledger"].columns) == ldg.LEDGER_COLUMNS
    for c in ldg.META_COLUMNS:
        assert c not in a["ledger"].columns          # 메타는 원장 밖 사이드카다
    pd.testing.assert_frame_equal(a["ledger"], b["ledger"])
    assert a["meta"]["run_id"] != b["meta"]["run_id"]
    with capsys.disabled():
        print("\n[결정성] {} 원장 {}행 × 2회 → assert_frame_equal 통과".format(
            D, len(a["ledger"])))
