"""analyze(분석 생성기) — 합성 로트(`run.build_rows`)로 네 단계를 끝까지 돌린다(실자료 0) · SPEC 고정 · 봉인 분리."""
from __future__ import annotations

import hashlib
import json
from datetime import date

import numpy as np
import pytest

from backtest.concept_axes.minute_rules import analyze as A
from backtest.concept_axes.minute_rules import run as RUN
from backtest.concept_axes.minute_rules import test_stats as S

from .synth import flat, path
from .test_run import CAL, DT, daily_flat
from .test_stage2_prereg import bundle

B = 120


def _walk(seed):
    rng = np.random.default_rng(seed)
    b = flat(10000.0)
    path(b, 0, np.round(10000.0 * np.cumprod(1 + rng.normal(0.0005, 0.012, 380)), -1))
    return b


def _lots_csv(tmp_path, window, n=48, fakes=0, cal=CAL, codes=30):
    items, lots = [], []
    for i in range(n):
        d0, d1 = cal[2 + i % 12], cal[3 + i % 12]
        lot = RUN.Lot("A", DT, d0, d1, f"{i % codes:06d}", "1", 10000.0, None, 10300.0, i % 7 != 0, "")
        lot.tv_rank_d, lot.tv_rank_d1 = float(1 + (i * 37) % 1500), float(1 + (i * 53) % 1500)
        lot.kospi20, lot.kospi_day_ret = float((i % 5) - 2), float((i % 9) - 4)
        lots.append(lot)
        if i % 11 != 5:                                    # 몇 개는 분봉 없음(daily_fallback)
            items.append((lot, _walk(i), {"market_gap_day": i == 9}))
    daily = {}
    for c in {x.code for x in lots}:
        daily.update(daily_flat(code=c, days=cal))
    excl = {x.key: "no_minute_data" for x in lots if x.key not in {it[0].key for it in items}}
    rows, frows, _ = RUN.build_rows(window, RUN.WINDOWS[window], lots, bundle(items, excl), daily, cal,
                                    {"A": cal[-1], "B": cal[-1]}, {x.code: "KOSDAQ" for x in lots}, fakes=fakes)
    d = tmp_path / window
    d.mkdir(parents=True, exist_ok=True)
    (d / "lots_rule.csv").write_text(RUN.csv_text(RUN.LOT_COLS, rows), encoding="utf-8")
    if fakes:
        (d / "fake_timing.csv").write_text(RUN.csv_text(RUN.FAKE_COLS, frows), encoding="utf-8")
    return d


def test_spec_fixed_constants_and_hash():
    sp = A.SPEC
    assert sp["direction"] == {"R1": "greater", "R6": "greater", "R3": "two-sided", "R7": "two-sided",
                               "R4": "greater", "R5": "greater", "H2_HIST": "less", "H_PLUS2": "greater"}
    assert (sp["theta_timing"], sp["theta_filter"], sp["m_main"], sp["m_indep"], sp["B"]) == (0.754, 2.0, 6, 2, 10000)
    assert sp["population_main"] == "band_ok_open == True" and sp["rank_basis_main"] == "tv_bucket_d"
    want = hashlib.sha256(json.dumps(sp, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert A.SPEC_SHA256 == want and len(want) == 64


def test_masks_population_and_exclusions(tmp_path):
    d = _lots_csv(tmp_path, "E")
    W = A.wide(A.read_lots(d / "lots_rule.csv"))
    mk = A.masks(W)
    assert mk["main"].sum() < mk["ref"].sum()                       # 모집단(band_ok) 이 줄인다
    assert not (mk["main"] & ~A._true(W["band_ok_open"])).any()
    assert not (mk["main"] & (W["main_excl"] != "").to_numpy()).any()  # market_gap_day 로트 제외
    assert not (mk["main"] & (W["excl_reason"] != "").to_numpy()).any()


def test_four_stages_end_to_end_synthetic(tmp_path):
    e = _lots_csv(tmp_path, "E", fakes=3)
    c = _lots_csv(tmp_path, "C")
    u = _lots_csv(tmp_path, "U")
    out, sealed = tmp_path / "res", tmp_path / "sealed"
    ej = A.explore(e / "lots_rule.csv", e / "fake_timing.csv", out, B)
    text = (out / "RESULTS_explore.md").read_text(encoding="utf-8")
    assert A.SPEC_SHA256 in text and "판정 무효(시험용)" in text and "두 칸" not in text and "H2_HIST" not in text
    assert ej["fake"]["n_timing"] == 3 and ej["fake"]["n_filter"] == A.SPEC["fake_n"]
    assert set(ej["rules"]) == set(A.MAIN_RULES)
    cj = A.confirm(c / "lots_rule.csv", out / "RESULTS_explore.json", out, B)
    ctext = (out / "RESULTS_confirm.md").read_text(encoding="utf-8")
    assert "§6-A 조건" in ctext and all(r in ctext for r in A.MAIN_RULES)
    assert set(cj["rules"]["R4"]["criteria"]) >= {"holm_ci", "theta", "same_sign_E", "f_min", "top10"}
    c2dir = _lots_csv(tmp_path, "C2")
    A.c2(c2dir / "lots_rule.csv", out / "RESULTS_confirm.json", out, B)
    assert "해당 없음" in (out / "RESULTS_c2.md").read_text(encoding="utf-8")   # C 불통과 규칙 = 해당 없음(R4)
    sha = A.sealed(u / "lots_rule.csv", [e / "lots_rule.csv", c / "lots_rule.csv"], out / "RESULTS_explore.json",
                   sealed, out, B)
    stext = (sealed / "sealed_indep.md").read_text(encoding="utf-8")
    assert hashlib.sha256(stext.encode()).hexdigest() == sha
    assert (out / "sealed_indep.sha256").read_text(encoding="utf-8") == f"{sha}  sealed_indep.md\n"
    assert not (out / "sealed_indep.md").exists() and "두 칸" in stext and "H2_HIST" in stext
    assert A.SEALED_BANNER in stext


def test_generator_deterministic(tmp_path):
    e = _lots_csv(tmp_path, "E", fakes=2)
    a = A.explore(e / "lots_rule.csv", e / "fake_timing.csv", tmp_path / "o1", B)
    b = A.explore(e / "lots_rule.csv", e / "fake_timing.csv", tmp_path / "o2", B)
    assert a["results_md_sha256"] == b["results_md_sha256"]


def test_window_and_spec_guards(tmp_path):
    e = _lots_csv(tmp_path, "E")
    with pytest.raises(SystemExit):
        A.confirm(e / "lots_rule.csv", tmp_path / "nope.json", tmp_path, B)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"spec_sha256": "x"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        A._load_json(bad)
    W = A.wide(A.read_lots(e / "lots_rule.csv"))
    with pytest.raises(SystemExit):
        A._check_window(W, "C")


def test_holm_ci_uses_basic_interval_at_holm_level(tmp_path):
    d = _lots_csv(tmp_path, "E")
    W = A.wide(A.read_lots(d / "lots_rule.csv"))
    calcs, _ = A.window_calc(W, "E", A.MAIN_RULES, B)
    A.holm_and_ci(calcs, 6, {})
    for c in calcs.values():
        if "ci_lo" in c.out:
            lo, hi = S.basic_ci(c.dist["main_ci"], c.est, c.out["holm_threshold"])
            np.testing.assert_equal((c.out["ci_lo"], c.out["ci_hi"]), (lo, hi))
            assert c.out["ci_level"] == pytest.approx(1 - c.out["holm_threshold"])


def test_criteria_logic_hand_case(tmp_path):
    d = _lots_csv(tmp_path, "E")
    W = A.wide(A.read_lots(d / "lots_rule.csv"))
    c = A.RuleCalc(W, A.masks(W)["main"], "R1", "timing", 0, B, A.ipw_series(W, A.masks(W)))
    c.est = 1.0
    c.out.update(holm_rejected=True, ci_fav=True, est_b=0.5, est_c=0.2, net_est=0.8, ipw_d=0.3,
                 loo_month_min_signed=0.1, top10_share=0.2,
                 regime={"kospi20>=0": {"est": 1.0, "n": 150}, "kospi20<0": {"est": -0.5, "n": 99}})
    cd = A.criteria(c, 0.754, 1)
    assert all(cd.values())                                          # n<100 칸의 반대 부호는 보지 않는다
    c.out["regime"]["kospi20<0"]["n"] = 100
    assert A.criteria(c, 0.754, 1)["regime"] is False
    assert A.criteria(c, 1.5, 1)["theta"] is False and A.criteria(c, 0.754, -1)["same_sign_E"] is False
    assert A.criteria(c, 0.754, None)["same_sign_E"] is None
    assert A.fav("H2_HIST") == -1 and A.fav("R3") == 1


def test_two_cell_table_split_at_0910(tmp_path):
    d = _lots_csv(tmp_path, "E")
    lines = A.two_cell_lines(d / "lots_rule.csv")
    assert lines[0].startswith("### E 창") and len([x for x in lines if x.startswith("| R")]) == 4
    assert A.SPEC["split_0910"] == "090959" and "091000" > A.SPEC["split_0910"] >= "090900"


def test_ipw_uses_signal_day_bucket_main(tmp_path):
    d = _lots_csv(tmp_path, "E")
    W = A.wide(A.read_lots(d / "lots_rule.csv"))
    mk = A.masks(W)
    ip = A.ipw_series(W, mk)
    base = mk["pop"] & mk["not_po"]
    sub = W[base]
    held = mk["held"][base]
    ref = S.ipw_weights(held, sub["tv_bucket_d"].to_numpy(), sub["month"].to_numpy(), 20)
    assert ip["d"].to_numpy().tolist() == pytest.approx(ref.weights.tolist())
    assert date.fromisoformat(W["entry_date"].iloc[0])


def test_explore_outputs_hold_no_sealed_material(tmp_path):
    """NB1 — 탐색 문서·json 에 개별 가짜 규칙 값(u=10 = H②-hist)·두 칸 표·독립 가족이 찍히지 않는다."""
    e = _lots_csv(tmp_path, "E", fakes=3)
    out = tmp_path / "res"
    ej = A.explore(e / "lots_rule.csv", e / "fake_timing.csv", out, B)
    text = (out / "RESULTS_explore.md").read_text(encoding="utf-8") + (out / "RESULTS_explore.json").read_text(
        encoding="utf-8")
    for bad in ("u_idx", "fake_k", "≤09:10 / >09:10", "le0910", "gt0910", "H2_HIST", "H_PLUS2"):
        assert bad not in text, bad
    assert set(ej["fake"]) == {"filter_rate", "timing_rate", "n_filter", "n_timing", "switch_filter",
                               "switch_timing"}
