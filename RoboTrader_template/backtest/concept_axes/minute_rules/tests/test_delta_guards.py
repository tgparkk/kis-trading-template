"""재리뷰(stage2_delta) 반영 — D1 p⇔구간 동치 · D4 판정 변이 11종 · D5 경계 · NB1 레포 밖 · NB2 관문 · R1.

각 테스트 위 주석 = 잡는 변이 이름(재리뷰 §3 D4 목록). 확인 = scratchpad `mutants_check2.py`(원본 무수정 · 메모리 교체).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.minute_rules import analyze as A
from backtest.concept_axes.minute_rules import run as RUN
from backtest.concept_axes.minute_rules import test_stats as S

from .test_run import CAL, DT, FakeGit

C = A.SPEC["cost_roundtrip_pct"]


def mk_long(lots):
    """lots = [dict(meta…, arms={arm: {ret, entered, …}})] → 긴 표(`lots_rule.csv` 모양 · 문자열)."""
    rows = []
    for i, lot in enumerate(lots):
        lid = f"{DT}|{lot.get('scan', '2025-06-02')}|{lot.get('code', f'{i:06d}')}"
        meta = dict(lot_id=lid, window=lot.get("w", "E"),
                    strategy=DT, scan_date=lot.get("scan", "2025-06-02"), entry_date=lot.get("day", "2025-06-03"),
                    stock_code=lot.get("code", f"{i:06d}"), month=lot.get("month", "2025-06"),
                    band_ok_open=lot.get("band", "True"), main_excl=lot.get("main_excl", ""),
                    excl_reason=lot.get("excl", ""), print_only=lot.get("po", "False"),
                    tv_bucket_d=lot.get("bd", "le300"), tv_bucket_d1=lot.get("bd1", "le300"),
                    kospi20=str(lot.get("k20", 1.0)), kospi_day_ret=str(lot.get("kd", 0.0)), daily_fallback="False",
                    adj_null_prev="False", adj_null_entry="False", market_gap_day="False", open_gap_flag="False",
                    corp_event="False", filled_minutes=str(lot.get("fm", 0)), vintage_m4=lot.get("vint", "True"))
        for arm, v in lot["arms"].items():
            r = dict(meta, arm=arm)
            for k in A.ARMF:
                x = v.get(k, "")
                r[k] = "" if x is None else (("True" if x else "False") if isinstance(x, bool) else str(x))
            rows.append(r)
    return pd.DataFrame(rows).astype(str)


def W_of(lots):
    return A.wide(mk_long(lots))


def tl(d, month="2025-06", code=None, day="2025-06-03", r_ent=True, b_ent=True, base=0.0, **kw):
    """시점 로트 1개 — R1 ret = base + d · R0 ret = base(모델 b·c 도 같은 차)."""
    arms = {"R0": dict(ret=base, b_ret=base, c_ret=base, entered=b_ent, entry_time="090200"),
            "R1": dict(ret=base + d, b_ret=base + d, c_ret=base + d, entered=r_ent,
                       entry_time="090300" if r_ent else "")}
    out = dict(arms=arms, month=month, day=day, **kw)
    if code:
        out["code"] = code
    return out


def calc(W, rule="R1", kind="timing", B=60):
    mk = A.masks(W)
    return A.RuleCalc(W, mk["main"], rule, kind, 0, B, A.ipw_series(W, mk))


# ── D4 변이 ──────────────────────────────────────────────────────────────
# 변이 loo_in — 한 달 빼기를 «그 달만»으로
def test_loo_month_drops_each_month():
    lots = [tl(3, "2025-06") for _ in range(3)] + [tl(1, "2025-07")] + [tl(-5, "2025-08")]
    c = calc(W_of(lots))
    assert c.est == pytest.approx(1.0)
    assert c.out["loo_month_min_signed"] == pytest.approx(-2.0)        # 06 을 빼면 (1−5)/2


# 변이 net_sign — 시점 순 = δ − c·(진입_규칙 − 진입_기준)
def test_timing_net_cost_sign():
    lots = [tl(-1, r_ent=False, base=1.0), tl(0)]
    lots[0]["arms"]["R1"]["ret"] = 0.0                                  # 안 삼 = 현금 0 · 기준 1
    c = calc(W_of(lots))
    assert c.out["net_est"] == pytest.approx((-1 + C) / 2)


def fl(label, ret, day="2025-06-03", code=None, ent=True, **kw):
    arms = {"R0": dict(ret=ret, entered=ent, entry_time="090200"),
            "R0_0905": dict(ret=ret, b_ret=ret, c_ret=ret, entered=ent, entry_time="090500"),
            "R4": dict(ret=ret, entered=ent, entry_time="090500", label=label)}
    out = dict(arms=arms, day=day, **kw)
    if code:
        out["code"] = code
    return out


# 변이 net_filter_keep — 거르기 순 = filter 군 R0_0905 순 평균
def test_filter_net_uses_filter_group():
    c = calc(W_of([fl("keep", 2.0), fl("filter", -1.0)]), "R4", "filter")
    assert c.out["net_filter_mean"] == pytest.approx(-1.0 - C)


# 변이 top10_bottom — 상위 10종목(유리 방향 기여 큰 쪽)
def test_top10_share_takes_largest_contributors():
    lots = [tl(10, code="A00000")] + [tl(1, code=f"B{i:05d}") for i in range(11)]
    c = calc(W_of(lots))
    assert c.out["top10_share"] == pytest.approx(19 / 21)


# 변이 fake_base_r0 — 가짜 거르기 기준 = R0_0905(거르기 두 군 공통 진입)
def test_fake_filter_uses_r0_0905_base():
    lots = []
    for d in range(10):
        for s in range(10):
            lots.append(dict(code=f"{s:06d}", day=f"2025-06-{d + 2:02d}", scan=f"2025-05-{d + 2:02d}",
                             arms={"R0": dict(ret=10.0 * s, entered=True, entry_time="090200"),
                                   "R0_0905": dict(ret=0.0, entered=True, entry_time="090500")}))
    fk = A.fake_rates(W_of(lots), None, 40)
    assert fk["filter_rate"] == 0.0                                      # R0_0905 = 상수 → Δ 0 → p 1


# 변이 masks_no_po — 주 분석에서 print_only 제외
def test_main_mask_excludes_print_only():
    W = W_of([tl(1, po="True"), tl(1)])
    mk = A.masks(W)
    assert mk["main"].tolist() == [False, True] and mk["ref"].tolist() == [False, True]


# 변이 ci_fav_less_wrong — 단측 less(H②-hist) 의 유리한 쪽 = 상한 < 0
def test_ci_favorable_side_for_less_rule():
    rng = np.random.default_rng(1)
    boot = rng.normal(-1.0, 0.1, 2000)
    c = SimpleNamespace(rule="H2_HIST", kind="timing", dirn=S.LESS, est=-1.0, dist={"main_ci": boot},
                        out={"p_main": S.p_boot(-1.0, boot, S.LESS), "p_twoway": 1.0})
    A.holm_and_ci({"H2_HIST": c}, 2, {})
    assert c.out["holm_rejected"] and c.out["ci_hi"] < 0 and c.out["ci_fav"] is True


# 변이 pmain_filter_two — 거르기 p 는 선언 방향(단측 greater)
def test_filter_p_respects_declared_direction():
    lots = [fl("keep", -5.0 + 0.1 * i, day=f"2025-06-{d + 2:02d}", code=f"K{d}{i}") for d in range(8) for i in range(2)]
    lots += [fl("filter", 5.0 + 0.1 * i, day=f"2025-06-{d + 2:02d}", code=f"F{d}{i}")
             for d in range(8) for i in range(2)]
    c = calc(W_of(lots), "R4", "filter", B=200)
    assert c.est < 0 and c.out["p_main"] > 0.9                         # keep 이 나쁜 쪽 = 기각 방향 아님


# 변이 c2_theta_full — C2 시점 기준 = 유리 방향 ≥ θ/2
def test_c2_verdict_rules():
    th = A.SPEC["theta_timing"]
    assert A.c2_verdict("R1", "timing", 300, th * 0.6, 1, "통과") == "통과"
    assert A.c2_verdict("R1", "timing", 300, th * 0.4, 1, "통과") == "불통과"
    assert A.c2_verdict("R1", "timing", 299, 5.0, 1, "통과") == "판정 불가 · 연장"
    assert A.c2_verdict("R1", "timing", 500, 5.0, -1, "통과") == "불통과"
    assert A.c2_verdict("R1", "timing", 500, 5.0, 1, "불통과") == "해당 없음"
    assert A.c2_verdict("R4", "filter", 10, 0.1, 1, "통과") == "통과"


# 변이 criteria_models_ignore_c — 모델 a·b·c 셋 다 같은 부호
def test_criteria_requires_model_c_sign():
    W = W_of([tl(1) for _ in range(3)])
    c = calc(W)
    c.out.update(holm_rejected=True, ci_fav=True, est_b=0.5, est_c=-0.1, net_est=1.0, ipw_d=1.0,
                 loo_month_min_signed=1.0, top10_share=0.1)
    assert A.criteria(c, 0.1, 1)["models_abc"] is False
    c.out["est_c"] = 0.1
    assert A.criteria(c, 0.1, 1)["models_abc"] is True
    assert A.verdict_of({"a": True, "f_min": False}) == "판정 불가" and A.verdict_of({"a": False}) == "불통과"


# 변이 split_le · D5 — 09:10 분 진입 = «>09:10» 칸(H②-hist «≥09:10 = 늦음»과 같은 경계)
def test_two_cell_boundary_0910_goes_late():
    assert A.cell_of(True, "090900") == "le0910" and A.cell_of(True, "091000") == "gt0910"
    assert A.cell_of(False, "") == "cash" and A.cell_of(True, "090200") == "le0910"


# ── D1 — p 기각 ⇔ 구간이 0 밖(단측·양측) ─────────────────────────────────
@pytest.mark.parametrize("seed", range(6))
def test_p_and_basic_ci_agree_exactly(seed):
    rng = np.random.default_rng(seed)
    bad = []
    for _ in range(150):
        n = int(rng.integers(50, 600))
        boot = rng.gamma(rng.uniform(0.3, 3), 1.0, n) * rng.choice([-1, 1]) + rng.normal(0, 0.3, n)
        t = float(rng.normal(0, 1.2))
        a = float(rng.choice([0.05, 0.05 / 6, 0.05 / 5, 0.01, 0.1]))
        lo, hi = S.basic_ci(boot, t, a)
        two = S.p_boot(t, boot, S.TWO) <= a
        if two != (lo > 0 or hi < 0):
            bad.append(("two", n, t, a))
        if (S.compare_value(S.p_boot(t, boot, S.GREATER), True) <= a) != (lo > 0):
            bad.append(("greater", n, t, a))
        if (S.compare_value(S.p_boot(t, boot, S.LESS), True) <= a) != (hi < 0):
            bad.append(("less", n, t, a))
    assert bad == []


def test_two_sided_p_is_equal_tail():
    boot = np.array([0.0, 1.0, 2.0, 3.0, 10.0])
    pg, pl = S.p_boot(2.0, boot, S.GREATER), S.p_boot(2.0, boot, S.LESS)
    assert S.p_boot(2.0, boot, S.TWO) == pytest.approx(min(1.0, 2 * min(pg, pl)))


# ── D2 인쇄 항목 ─────────────────────────────────────────────────────────
def test_g9_g10_undetermined_and_holding_by_month():
    lots = [tl(1, fm=i, vint="False" if i % 2 else "True") for i in range(8)]
    lots[0]["arms"]["R1"]["undetermined_minutes"] = 3
    W = W_of(lots)
    c = calc(W)
    assert c.out["g9_n"] == 6 and c.out["post0703_n"] == 4                # q75 = 5.25 → fm ≤ 5
    assert c.out["undet_min_lots"] == 1 and c.out["undet_min_total"] == 3
    _, info = A.window_calc(W, "E", ["R1"], 20)
    assert "month" in info["holding"] and {"n_excl_g5", "n_excl_g7", "n_no_rank_d"} <= set(info)


def test_ret_missing_lot_excluded_and_counted():
    lots = [tl(1), tl(1)]
    lots[1]["arms"]["R1"]["ret"] = None
    c = calc(W_of(lots))
    assert c.n == 1 and c.out["n_ret_missing"] == 1 and c.est == pytest.approx(1.0)


# ── NB1 · D3 레포 밖 ────────────────────────────────────────────────────
def test_outside_any_git_tree(tmp_path):
    with pytest.raises(SystemExit):
        RUN.ensure_outside_git(RUN.RESULTS / "x", "t")                   # 이 워크트리
    other = tmp_path / "otherrepo"
    other.mkdir()
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    with pytest.raises(SystemExit):
        RUN.ensure_outside_git(other / "a" / "b", "t")                   # 다른 git 작업 트리(라이브·태쏘 같은 경우)
    assert RUN.ensure_outside_git(tmp_path / "plain" / "x", "t") == (tmp_path / "plain" / "x").resolve()
    with pytest.raises(SystemExit):
        RUN.private_dir(str(other / "p"))
    with pytest.raises(SystemExit):
        RUN.sealed_dir(str(other / "s"))


def test_results_csv_ignored_by_nested_gitignore():
    for name in ("E/lots_rule.csv", "E/fake_timing.csv", "C2/lots_rule.csv"):
        r = subprocess.run(["git", "check-ignore", "-q", str(RUN.RESULTS / name)], cwd=str(RUN.REPO))
        assert r.returncode == 0, name
    r = subprocess.run(["git", "check-ignore", "-q", str(RUN.RESULTS / "E" / "run_meta.json")], cwd=str(RUN.REPO))
    assert r.returncode == 1


# ── NB2 관문 ────────────────────────────────────────────────────────────
def _meta(tmp_path, csv_bytes=b"a,b\n", **over):
    p = tmp_path / "lots_rule.csv"
    p.write_bytes(csv_bytes)
    m = dict(window="C", plumbing=False, ok=True, code_sha256={"x": "1"}, analysis_spec_sha256=A.SPEC_SHA256,
             explore={"sha256": "e" * 64}, outputs={"lots_rule.csv": {"sha256": hashlib.sha256(csv_bytes).hexdigest()}})
    m.update(over)
    mp = tmp_path / "run_meta.json"
    mp.write_text(json.dumps(m), encoding="utf-8")
    return p, mp


def test_verify_run_output_checks(tmp_path):
    p, mp = _meta(tmp_path)
    A.verify_run_output(p, mp, "C", code_now={"x": "1"}, explore_sha="e" * 64)
    for over, kw in ((dict(ok=False), {}), (dict(plumbing=True), {}), (dict(window="E"), {}),
                     ({}, dict(code_now={"x": "2"})), ({}, dict(explore_sha="f" * 64)),
                     (dict(outputs={"lots_rule.csv": {"sha256": "0"}}), {}), (dict(analysis_spec_sha256="z"), {})):
        p, mp = _meta(tmp_path, **over)
        with pytest.raises(SystemExit):
            A.verify_run_output(p, mp, "C", **{**dict(code_now={"x": "1"}, explore_sha="e" * 64), **kw})


def test_verify_prior_requires_committed_and_md_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(RUN, "REPO", tmp_path)
    md, js = tmp_path / "RESULTS_explore.md", tmp_path / "RESULTS_explore.json"
    md.write_text("x", encoding="utf-8")
    js.write_text(json.dumps({"spec_sha256": A.SPEC_SHA256, "results_md_sha256": hashlib.sha256(b"x").hexdigest()}),
                  encoding="utf-8")
    got = A.verify_prior(js, md, FakeGit({("log",): (0, "c0ffee\n")}))
    assert got == {"RESULTS_explore.md": "c0ffee", "RESULTS_explore.json": "c0ffee"}
    with pytest.raises(SystemExit):
        A.verify_prior(js, md, FakeGit({("diff",): (1, "")}))             # 커밋 안 된 변경(손으로 만든 json)
    js.write_text(json.dumps({"spec_sha256": A.SPEC_SHA256, "results_md_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(SystemExit):
        A.verify_prior(js, md, FakeGit({}))                               # md 해시 불일치


# ── R1 순위 배선 ─────────────────────────────────────────────────────────
def test_attach_ranks_d_is_scan_date():
    lot = RUN.Lot("A", DT, CAL[0], CAL[1], "000001", "1", 1.0, None, 1.03)
    nr = RUN.attach_ranks([lot], {("000001", CAL[0]): 5.0, ("000001", CAL[1]): 9.0},
                          {("000001", CAL[0]): 7.0, ("000001", CAL[1]): 11.0})
    assert (lot.tv_rank_d, lot.tv_rank_d1, nr) == (5.0, 11.0, 0)
    lot2 = RUN.Lot("B", DT, date(2026, 10, 3), CAL[1], "000002", "1", 1.0, None, 1.03)
    assert RUN.attach_ranks([lot2], {}, {}) == 1                           # 비거래일 scan_date = D 순위 없음(R6)
