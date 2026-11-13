# -*- coding: utf-8 -*-
"""합성 자료 시험 — 통계 계층(ci_stats). 실데이터 접근 0."""
from datetime import timedelta

import numpy as np
import pytest

import ci_stats as S
from synthetic import Builder, full_synthetic, weekdays

D0 = S.FIRST_DAY


# ---------------------------------------------------------------- (a) CI 가 참값을 덮는 비율
def _clustered_sample(rng, n_days, mu, day_sd, unit_sd):
    units = []
    for i in range(n_days):
        d = D0 + timedelta(days=i)
        shock = rng.normal(0, day_sd)
        for _ in range(int(rng.integers(1, 6))):
            units.append((d, mu + shock + rng.normal(0, unit_sd)))
    return units


def test_a_cluster_ci_coverage_near_nominal():
    """참 평균 mu 가 알려진 군집 자료(거래일 충격 공유)에서 «일평균의 평균» 95% CI 가 mu 를 덮는 비율.
    거래일 20 · 반복 400 · B=2,000(속도용 — 방법은 같음). percentile 부트스트랩은 군집 20 개에서 약간 좁다."""
    rng = np.random.default_rng(1)
    mu, reps, hit = 0.15, 400, 0
    for r in range(reps):
        u = _clustered_sample(rng, 20, mu, day_sd=0.3, unit_sd=0.2)
        lo, hi = S.cluster_bootstrap_ci(u, b=2000, seed=1000 + r)
        # 일평균의 평균의 기댓값 = mu (단위 수가 날마다 달라도 일평균은 mu 중심)
        hit += lo <= mu <= hi
    cov = hit / reps
    print(f"\n[a] cluster bootstrap coverage = {cov:.3f} (reps={reps})")
    assert 0.88 <= cov <= 0.99


def test_a_naive_iid_bootstrap_undercovers_with_day_shocks():
    """대조: 거래일 군집을 무시한 단위 i.i.d. 재표집은 같은 자료에서 덮는 비율이 더 낮다(군집 단위가 필요한 이유)."""
    rng = np.random.default_rng(2)
    mu, reps, hit_c, hit_n = 0.0, 300, 0, 0
    for r in range(reps):
        u = _clustered_sample(rng, 20, mu, day_sd=0.4, unit_sd=0.1)
        lo, hi = S.cluster_bootstrap_ci(u, b=1000, seed=r)
        hit_c += lo <= mu <= hi
        v = np.array([x for _, x in u])
        g = np.random.default_rng(r)
        bs = v[g.integers(0, v.size, size=(1000, v.size))].mean(axis=1)
        nlo, nhi = np.percentile(bs, [2.5, 97.5])
        hit_n += nlo <= mu <= nhi
    print(f"\n[a] cluster {hit_c / reps:.3f} vs naive iid {hit_n / reps:.3f}")
    assert hit_c / reps > hit_n / reps + 0.10


# ---------------------------------------------------------------- (b) 하루 안 평균 → 일평균의 평균
def test_b_daily_mean_first_not_pooled():
    d1, d2, d3 = D0, D0 + timedelta(1), D0 + timedelta(2)
    units = [(d1, 1.0)] * 10 + [(d2, 0.0), (d3, 0.0)]
    s = S.summarize(units, min_n=1)
    assert s["mean_daily"] == pytest.approx(1 / 3)
    assert s["pooled"] == pytest.approx(10 / 12)
    # 재표집 통계는 일평균 3개의 평균뿐 → CI 끝점은 {0, 1/3, 2/3, 1} 격자 위
    lo, hi = s["ci"]
    assert lo == pytest.approx(0.0) and hi == pytest.approx(1.0)


def test_b_ci_equals_ci_of_daily_means_one_unit_per_day():
    """CI 는 «일평균» 에만 의존 — 단위를 일평균 1개로 바꿔도 같은 값(쌍이 몰린 날이 더 무겁지 않음)."""
    rng = np.random.default_rng(3)
    units = []
    for i in range(18):
        d = D0 + timedelta(days=i)
        k = 1 if i % 3 else 12          # 어떤 날은 쌍 12개
        units += [(d, float(x)) for x in rng.normal(i * 0.01, 0.5, size=k)]
    dm = S.daily_means(units)
    collapsed = [(d, v) for d, v in dm.items()]
    assert S.cluster_bootstrap_ci(units) == S.cluster_bootstrap_ci(collapsed)


def test_b_pipeline_heavy_day_not_overweighted():
    """지표 경로 전체(쌍 → 집행 슬리피지)에서 쌍 5개가 몰린 날이 일평균 1표만 갖는다."""
    days = weekdays(D0, 3)
    b = Builder(days)
    for j in range(5):                  # 첫날 5쌍 · 집행 +1 틱(10,000 → 10,010 = +0.1%)
        code = f"20000{j}"
        t = b.at(days[0], 9, 10 + j)
        b.paper_buy(days[0], code, t, 10000)
        b.real_try(days[0], code, t, 10000)
        b.real_buy(days[0], code, t + timedelta(seconds=5), 10010)
    for d in days[1:]:                  # 다른 날 1쌍씩 · 집행 0
        t = b.at(d, 9, 30)
        b.paper_buy(d, "300000", t, 10000)
        b.real_try(d, "300000", t, 10000)
        b.real_buy(d, "300000", t + timedelta(seconds=5), 10000)
    res = S.build_summary(b.build())
    s = res["m2"]["exec"]["첫날 포함"]
    assert s["n"] == 7
    assert s["pooled"] == pytest.approx(0.5 / 7)
    assert s["mean_daily"] == pytest.approx(0.1 / 3)


# ---------------------------------------------------------------- (c) 최소 n 미달 → CI 미출력
@pytest.mark.parametrize("key", ["pair", "exit", "stop"])
def test_c_min_n_gate(key):
    m = S.MIN_N[key]
    below = [(D0 + timedelta(days=i), float(i)) for i in range(m - 1)]
    at = [(D0 + timedelta(days=i), float(i)) for i in range(m)]
    s1, s2 = S.summarize(below, m), S.summarize(at, m)
    assert s1["ci"] is None and s1["status"].startswith("표본 부족") and s1["median"] is not None
    assert s2["ci"] is not None and s2["status"] == "CI"


def test_c_small_dataset_renders_no_ci():
    days = weekdays(D0, 3)
    b = Builder(days)
    for d in days:
        t = b.at(d, 9, 30)
        b.paper_buy(d, "111111", t, 5000)
        b.real_try(d, "111111", t, 5000)
        b.real_buy(d, "111111", t + timedelta(seconds=3), 5005)
    res = S.build_summary(b.build())
    for name in ("timing", "exec", "total", "ticks"):
        assert res["m2"][name]["첫날 포함"]["ci"] is None
    assert res["m1"]["signal"]["첫날 포함"]["ci"] is None
    assert [v["거리"] for k, v in res["cells"].items() if k.startswith("③")] == [None]
    md = S.render_markdown(res)
    assert "표본 부족 · 점값만" in md


# ---------------------------------------------------------------- (d) seed 고정 재현성
def test_d_seed_reproducible_and_order_free():
    rng = np.random.default_rng(4)
    units = [(D0 + timedelta(days=int(i % 17)), float(x)) for i, x in enumerate(rng.normal(0, 1, 60))]
    a = S.cluster_bootstrap_ci(units)
    assert a == S.cluster_bootstrap_ci(units)                               # 같은 입력 → 같은 값(비트 단위)
    assert S.cluster_bootstrap_ci(list(reversed(units))) == pytest.approx(a, rel=1e-12)   # 순서 무관(합산 순서 오차만)
    # 사전등록 seed 로 직접 구현한 것과 같다
    m = np.array(list(S.daily_means(units).values()))
    g = np.random.default_rng(20261113)
    st = m[g.integers(0, m.size, size=(10_000, m.size))].mean(axis=1)
    assert a == tuple(float(x) for x in np.percentile(st, [2.5, 97.5]))
    assert S.cluster_bootstrap_ci(units, seed=1) != a


def test_d_full_summary_reproducible():
    r1 = S.build_summary(full_synthetic(seed=11))
    r2 = S.build_summary(full_synthetic(seed=11))
    assert S.render_markdown(r1) == S.render_markdown(r2)


# ---------------------------------------------------------------- (e) 첫날 포함/제외
def test_e_first_day_lines():
    units = [(D0, 5.0), (D0, 5.0)] + [(D0 + timedelta(days=i), 1.0) for i in range(1, 16)]
    lines = S.split_lines(units, {}, min_n=15)
    assert lines["첫날 포함"]["n"] == 17 and lines["첫날 포함"]["ci"] is not None
    assert lines["첫날 제외"]["n"] == 15 and lines["첫날 제외"]["mean_daily"] == pytest.approx(1.0)
    assert lines["첫날만"]["n"] == 2 and lines["첫날만"]["ci"] is None
    assert lines["첫날 포함"]["mean_daily"] == pytest.approx((5 + 15) / 16)


def test_e_up_down_split_by_kospi_sign():
    days = [D0 + timedelta(days=i) for i in range(4)]
    units = [(d, float(i)) for i, d in enumerate(days)]
    lines = S.split_lines(units, {days[0]: 1, days[1]: -1, days[2]: 1, days[3]: 0}, min_n=1)
    assert lines["상승일"]["n"] == 2 and lines["하락일"]["n"] == 1 and lines["보합·지수 없음"]["n"] == 1


# ---------------------------------------------------------------- (f) §6 규칙 · 결측 · 한쪽만 · 부분체결
def _one_day():
    days = weekdays(D0, 2)
    return days, Builder(days)


def test_f_time_ordered_one_to_one_pairing():
    days, b = _one_day()
    d = days[1]
    b.paper_buy(d, "123456", b.at(d, 9, 10), 1000)
    b.paper_buy(d, "123456", b.at(d, 11, 0), 1100)        # 같은 날 재매수 — 실전은 1번만
    b.real_try(d, "123456", b.at(d, 9, 11), 1000)
    b.real_buy(d, "123456", b.at(d, 9, 12), 1000)
    ps = S.match_pairs(b.build())
    assert len(ps.pairs) == 1 and ps.pairs[0].paper.price == 1000
    assert len(ps.paper_only) == 1 and ps.paper_only[0].price == 1100
    cu = S.coverage_units(b.build(), ps)
    assert [u.tried for u in cu] == [True, False] and cu[1].reason == "실전 시도 없음"


def test_f_reason_mapping_order():
    days, b = _one_day()
    d = days[1]
    lg = b.logs[d]
    codes =["100001", "100002", "100003", "100004", "100005", "100006", "100007"]
    for c in codes:
        b.paper_buy(d, c, b.at(d, 9, 30), 5000)
    t = b.at(d, 9, 31)
    lg.caps.append((t, "100001")); lg.api_timeouts.append((t, "100001"))   # ① 가 ④ 보다 먼저
    lg.cash.append((t, "100002")); lg.blocks.append((t, "100002"))         # ② > ③
    lg.blocks.append((t, "100003"))
    b.real_try(d, "100004", t, 5000); lg.api_timeouts.append((t, "100004"))
    b.real_try(d, "100005", t, 5000); lg.delayed_cancels.append((t, "100005"))
    b.real_try(d, "100007", t, 5000)                                       # 시도만 있고 사유 줄 없음 → 기타
    ds = b.build()
    cu = {u.paper.code: u for u in S.coverage_units(ds, S.match_pairs(ds))}
    assert [cu[c].reason for c in codes] == ["한도", "현금", "차단", "API", "지연 취소", "실전 시도 없음", "기타"]
    assert cu["100004"].tried and not cu["100004"].filled
    v = S.values_coverage(list(cu.values()))
    assert len(v["signal"]) == 7 and len(v["signal_ex_cap_cash"]) == 5     # 한도·현금 ㉯ 2 건 분모에서 뺌


def test_f_slippage_exclusions_keep_coverage():
    days, b = _one_day()
    d = days[1]
    # ① 주문가 로그 없음
    b.paper_buy(d, "200001", b.at(d, 9, 0), 5000); b.real_buy(d, "200001", b.at(d, 9, 1), 5000)
    # ② |Δt| > 10분 (601초)
    b.paper_buy(d, "200002", b.at(d, 9, 0), 5000); b.real_try(d, "200002", b.at(d, 9, 9), 5000)
    b.real_buy(d, "200002", b.at(d, 9, 10, 1), 5000)
    # ③ 격자 밖 체결가(5,002 · 5,000~20,000 은 10원 격자) → 체결가 폴백
    b.paper_buy(d, "200003", b.at(d, 9, 0), 5000); b.real_try(d, "200003", b.at(d, 9, 0, 5), 5000)
    b.real_buy(d, "200003", b.at(d, 9, 0, 9), 5002)
    # ④ 정상 · 경계 |Δt| = 600초 는 포함
    b.paper_buy(d, "200004", b.at(d, 9, 0), 5000); b.real_try(d, "200004", b.at(d, 9, 9), 5013)
    b.real_buy(d, "200004", b.at(d, 9, 10), 5020)
    ds = b.build()
    ps = S.match_pairs(ds)
    keep, excl = S.eligible_slippage(ps.pairs)
    assert [p.paper.code for p in keep] == ["200004"]
    assert {k: [p.paper.code for p in v] for k, v in excl.items()} == {
        "주문가 로그 없음": ["200001"], "|Δt| > 10분": ["200002"], "체결가 폴백(격자 밖)": ["200003"]}
    v = S.values_slippage(keep)
    # 주문가 = round_to_tick(5,013) = 5,010 (로그 가격은 반올림 전 · order_executor.py:83 vs :207)
    assert v["timing"][0][1] == pytest.approx((5010 - 5000) / 5000 * 100)
    assert v["exec"][0][1] == pytest.approx((5020 - 5010) / 5010 * 100)
    assert v["ticks"][0][1] == pytest.approx(2.0)
    assert len(S.coverage_units(ds, ps)) == 4                               # 커버리지엔 4 건 모두


def test_f_partial_fill_merged_and_fill_ratio():
    days, b = _one_day()
    d = days[1]
    b.paper_buy(d, "300001", b.at(d, 9, 0), 10000)
    b.real_try(d, "300001", b.at(d, 9, 0, 10), 10000, qty=10)
    r1 = b.real_buy(d, "300001", b.at(d, 9, 0, 20), 10000, qty=4)
    r2 = b.real_buy(d, "300001", b.at(d, 9, 1, 0), 10050, qty=2)
    ds = b.build()
    ps = S.match_pairs(ds)
    assert len(ps.pairs) == 1 and not ps.real_only
    f = ps.pairs[0].real
    assert f.qty == 6 and f.price == pytest.approx((4 * 10000 + 2 * 10050) / 6) and f.ts == r2.ts
    assert f.row_ids == (r1.id, r2.id)
    assert S.values_fill_ratio(ps.pairs)[0][1] == pytest.approx(60.0)


def test_f_real_only_excluded_and_not_running():
    days, b = _one_day()
    d = days[1]
    b.real_try(d, "400001", b.at(d, 9, 0), 3000); b.real_buy(d, "400001", b.at(d, 9, 0, 5), 3000)   # ㉰
    b.paper_buy(d, "400002", b.at(d, 7, 0), 3000)                                                    # 07:00 = 실전 로그 07:45 전
    b.paper_buy(days[0], "400003", b.at(days[0], 9, 0), 3000)
    ds = b.build()
    del ds.logs[days[0]]                                                                            # 그날 실전 로그 없음
    ps = S.match_pairs(ds)
    assert [f.code for f in ps.real_only] == ["400001"] and not ps.pairs
    assert sorted(p.code for p in ps.not_running) == ["400002", "400003"]
    assert S.coverage_units(ds, ps) == []
    res = S.build_summary(ds)
    assert res["exclusions"]["㉰ 실전만(표본 제외 · 건수만)"] == [(d, "400001")]


def test_f_restart_day_pairs_excluded():
    from ci_data import restart_days_from_files
    days, b = _one_day()
    names = {"페이퍼": [f"robotrader_template_{days[1]:%Y%m%d}_074007.log", f"robotrader_template_{days[1]:%Y%m%d}_101500.log",
                       f"robotrader_template_{days[0]:%Y%m%d}_074007.log", f"robotrader_template_{days[0]:%Y%m%d}_075500.log"],
             "실전": []}
    rd = restart_days_from_files(names, days)
    assert list(rd) == [days[1]]                       # 두 번째 시작 07:55 는 장중 아님 → 제외 아님
    for d in days:
        b.paper_buy(d, "500001", b.at(d, 9, 0), 2000)
        b.real_try(d, "500001", b.at(d, 9, 0, 3), 2000)
        b.real_buy(d, "500001", b.at(d, 9, 0, 6), 2000)
    ds = b.build(restart_days=rd)
    ps = S.match_pairs(ds)
    assert [p.day for p in ps.pairs] == [days[0]]
    assert len(ps.excluded) == 2 and all(e[2] == days[1] for e in ps.excluded)


def _stop_pair(b, d, code, real_sell_day, paper_sell_day, paper_sell_price):
    t = b.at(d, 9, 0)
    pb = b.paper_buy(d, code, t, 10000)
    b.real_try(d, code, t, 10000)
    rb = b.real_buy(d, code, t + timedelta(seconds=5), 10000)
    ts = b.at(real_sell_day, 10, 0)
    b.stop_log(real_sell_day, code, ts, -10.3)
    rs = b.real_sell(rb, ts + timedelta(seconds=3), 8960)
    b.paper_sell(pb, b.at(paper_sell_day, 10, 1), paper_sell_price, reason="손절 실행 (-10.40% <= -10.00%)")
    return rs


def test_f_sr1_same_day_rule_price_isolation():
    """§4: 청산일이 다른 쌍의 페이퍼 매도가는 어떤 결과에도 영향 주지 않는다 · 같은 날 쌍만 짝 줄에 들어간다."""
    days = weekdays(D0, 3)

    def run(price_other_day):
        b = Builder(days)
        _stop_pair(b, days[0], "600001", days[0], days[0], 8960)               # 같은 날
        _stop_pair(b, days[0], "600002", days[0], days[1], price_other_day)    # 청산일 다름
        return S.build_summary(b.build())

    r1, r2 = run(8960), run(1)
    assert r1["exit_pair_categories"] == {"같은 날": 1, "청산일 다름": 1}
    assert r1["m3_pair"]["페이퍼"]["합"]["첫날 포함"]["n"] == 1
    assert r1["m3_all"]["합"]["첫날 포함"]["n"] == 2                          # 실전 전체 줄엔 제한 없음
    assert S.render_markdown(r1) == S.render_markdown(r2)


class _SealedSell:
    """price 를 읽으면 실패하는 페이퍼 SELL 대역 — 집계 단계에서도 가격을 안 읽는지 확인."""

    def __init__(self, s):
        self.id, self.code, self.ts, self.qty, self.buy_record_id, self.reason = (
            s.id, s.code, s.ts, s.qty, s.buy_record_id, s.reason)

    @property
    def price(self):
        raise AssertionError("§4 위반: 같은 날 밖 페이퍼 청산가를 읽음")


@pytest.mark.parametrize("paper_day_idx, category", [(1, "청산일 다름"), (None, "페이퍼만 청산")])
def test_f_sr1_paper_price_not_read_even_in_aggregation(paper_day_idx, category):
    days = weekdays(D0, 3)
    b = Builder(days)
    _stop_pair(b, days[0], "610001", days[0], days[0], 8960)                    # 같은 날(가격 읽어도 됨)
    if paper_day_idx is None:                                                   # 실전 미청산 · 페이퍼만 청산
        pb = b.paper_buy(days[0], "610002", b.at(days[0], 9, 0), 10000)
        b.real_try(days[0], "610002", b.at(days[0], 9, 0), 10000)
        b.real_buy(days[0], "610002", b.at(days[0], 9, 0, 5), 10000)
        b.paper_sell(pb, b.at(days[1], 10, 0), 9000, reason="손절 실행 (-10.00% <= -10.00%)")
    else:
        _stop_pair(b, days[0], "610002", days[0], days[paper_day_idx], 9000)
    ds = b.build()
    sealed_id = [s.id for s in ds.paper_sells if s.code == "610002"][0]
    ds.paper_sells = [_SealedSell(s) if s.id == sealed_id else s for s in ds.paper_sells]
    eps = S.exit_pairs(ds, S.match_pairs(ds))
    x = [e for e in eps if e.pair.paper.code == "610002"][0]
    assert x.category == category and x.paper.price is None
    res = S.build_summary(ds)                                                   # 전체 경로도 가격을 안 읽음
    assert res["m3_pair"]["페이퍼"]["합"]["첫날 포함"]["n"] == 1


def test_cost_source_strict_leaves_cell_blank_and_reference_only():
    days, b = _one_day()
    d = days[0]
    rb = b.real_buy(d, "810001", b.at(d, 9, 0), 10000, qty=10)
    b.real_sell(rb, b.at(d, 14, 0), 10500, qty=10)
    b.cost_rows[(d, "810001", 10)] = 105000.0
    b.cost_day(d, 100000, 105000, 7, 210)
    ds = b.build()
    a = S.build_summary(ds, cost_source="allocated")
    s = S.build_summary(ds, cost_source="strict")
    assert a["m4_all"]["첫날 포함"]["n"] == 1 and a["m4_point_mean_all"] is not None
    assert s["m4_all"]["첫날 포함"]["n"] == 0 and s["m4_point_mean_all"] is None
    assert [v["통계량"] for k, v in s["cells"].items() if k.startswith("①")] == [None]
    assert len(s["m4_unmeasured"]) == 1 and s["m4_ref_allocated"]["측정된 청산의 단순 평균"] == a["m4_point_mean_all"]
    md = S.render_markdown(s)
    assert "5-1. 참고 — 비용 배분값" in md and "strict" in md
    with pytest.raises(ValueError):
        S.build_summary(ds, cost_source="x")


def test_report_fixed_violations_headers_and_few_cluster_mark():
    md = S.render_markdown(S.build_summary(full_synthetic()))
    for t in S.FIXED_VIOLATIONS:
        assert t in md
    assert "일평균의 평균의 95% CI" in md and "측정된 청산의 단순 평균" in md
    assert "중앙값(쌍 단위)" in md and "## 부록. 쌍 목록" in md
    assert "군집 적음 · CI 신뢰 낮음" in md                                     # 상승일/하락일 줄 등 거래일 < 10
    lines = S.split_lines([(D0 + timedelta(days=i), 1.0) for i in range(12)], {}, min_n=1)
    assert "군집 적음" not in S._line_row("x", "첫날 포함", lines["첫날 포함"])


def test_f_stop_values_and_earliest_trigger():
    days, b = _one_day()
    d = days[1]
    t = b.at(d, 9, 0)
    rb = b.real_buy(d, "700001", t, 10000)
    b.real_try(d, "700001", t - timedelta(seconds=2), 10000)
    b.stop_log(d, "700001", b.at(d, 10, 0), -10.2)
    b.stop_log(d, "700001", b.at(d, 10, 3), -10.9)          # 매도 재시도 중 반복 신호 — 쓰지 않음
    b.real_sell(rb, b.at(d, 10, 5), 8960)
    ds = b.build()
    m, unm = S.real_stop_map(ds, S.real_exits(ds))
    ev = list(m.values())[0]
    assert ev.trig_pct == -10.2 and not unm
    a, bb, tot = S.stop_values(ev)
    assert a == pytest.approx(-0.2)
    assert bb == pytest.approx((8960 / (10000 * 0.898) - 1) * 100)          # §8 예시와 같은 꼴(≈ −0.22%)
    assert tot == pytest.approx(a + bb)


def test_f_cost_unmeasured_not_filled_with_assumed():
    days, b = _one_day()
    for i, d in enumerate(days):
        t = b.at(d, 9, 0)
        rb = b.real_buy(d, f"80000{i}", t, 10000, qty=10)
        b.real_sell(rb, b.at(d, 14, 0), 10500, qty=10)
        if i == 0:
            b.cost_rows[(d, rb.code, 10)] = 105000.0
    b.cost_day(days[0], 100000, 105000, 7, 210)               # 둘째 날 KIS 행 없음 → 미측정
    ds = b.build()
    keep, miss = S.eligible_cost(ds, S.real_exits(ds))
    assert len(keep) == 1 and len(miss) == 1 and miss[0][1] == "매도일 KIS 행 없음"
    act, ass = S.cost_values(ds, keep[0])
    fee_rate = 7 / 205000
    assert act == pytest.approx((fee_rate * 100000 + fee_rate * 105000 + 210) / 100000 * 100)
    assert ass == pytest.approx((0.00015 * 100000 + 0.00015 * 105000 + 0.0018 * 105000) / 100000 * 100)
    res = S.build_summary(ds)
    assert res["m4_all"]["첫날 포함"]["n"] == 1 and len(res["m4_unmeasured"]) == 1


def test_f_latency_signal_before_matching_try():
    days, b = _one_day()
    d = days[1]
    b.paper_buy(d, "900001", b.at(d, 9, 0, 0), 4000)
    b.logs[d].signals.append((b.at(d, 8, 59, 0), "900001"))   # 앞 신호(쓰이지 않아야)
    b.real_try(d, "900001", b.at(d, 9, 5, 0), 4000, signal_lead_s=2)
    b.real_buy(d, "900001", b.at(d, 9, 5, 30), 4000)
    b.logs[d].signals.append((b.at(d, 9, 30, 0), "900001"))   # 뒤 신호(쓰이지 않아야)
    ps = S.match_pairs(b.build())
    v = S.values_latency(ps.pairs)
    assert v["a_internal"][0][1] == 32.0 and v["b_signal_lag"][0][1] == 298.0


# ---------------------------------------------------------------- 기타 고정
def test_tick_table_matches_production():
    pytest.importorskip("config.settings")
    from utils import price_utils as pu
    for p in (1, 1999, 2000, 4995, 5000, 19990, 20000, 49950, 50000, 199900, 200000, 499500, 500000, 1234567):
        assert S.tick_size(p) == pu._get_tick_size(p)
    for p in (1203.4, 4997.6, 12345.0, 54321.0, 250250.0):
        assert S.round_to_tick(p) == pu.round_to_tick(p)


def test_no_judgement_language_in_report():
    md = S.render_markdown(S.build_summary(full_synthetic()))
    for bad in ("PASS", "FAIL", "합격", "불합격", "실전 확인됨"):
        assert bad not in md
    assert "관측 · 판정 아님" in md and "거리" in md
