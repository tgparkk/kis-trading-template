"""문병로 메트릭 스튜디오 rules + run-script 횡단면 순위 — 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def dummy_df():
    """룰은 ctx 순위만 읽으므로 df 내용은 무관 — 최소 1행."""
    return pd.DataFrame({
        "datetime": pd.date_range("2025-01-01", periods=3, freq="B"),
        "open": [10_000.0, 10_100, 10_200],
        "high": [10_100.0, 10_200, 10_300],
        "low": [9_900.0, 10_000, 10_100],
        "close": [10_000.0, 10_100, 10_200],
        "volume": [1_000_000, 1_000_000, 1_000_000],
    })


# ---------------------------------------------------------------------------
# T1: rule_low_pbr
# ---------------------------------------------------------------------------

class TestRuleLowPbr:
    def test_triggers_when_pbr_rank_in_top_n(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_low_pbr
        rule = rule_low_pbr(top_n=20, min_eligible=10)
        res = rule.evaluate(dummy_df, {"pbr_rank": 5, "n_eligible": 30})
        assert res.triggered is True
        assert res.side == "buy"
        assert res.confidence == pytest.approx(72.0)

    def test_fails_when_pbr_rank_none(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_low_pbr
        rule = rule_low_pbr()
        res = rule.evaluate(dummy_df, {"pbr_rank": None, "n_eligible": 30})
        assert res.triggered is False

    def test_fails_when_rank_beyond_top_n(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_low_pbr
        rule = rule_low_pbr(top_n=20, min_eligible=10)
        res = rule.evaluate(dummy_df, {"pbr_rank": 25, "n_eligible": 30})
        assert res.triggered is False

    def test_fails_when_n_eligible_below_min(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_low_pbr
        rule = rule_low_pbr(top_n=20, min_eligible=10)
        res = rule.evaluate(dummy_df, {"pbr_rank": 3, "n_eligible": 5})
        assert res.triggered is False

    def test_pbr_rank_independent_of_pcr_eligibility(self, dummy_df):
        """pbr_rank 는 n_eligible(5팩터 적격수)와 별개로 주어진다 — n_eligible 충분하면 트리거."""
        from strategies.books.moonbyungro_metric.rules import rule_low_pbr
        rule = rule_low_pbr(top_n=20, min_eligible=10)
        # pbr_rank 작고 n_eligible 충족 → PCR 적격 여부와 무관하게 트리거
        res = rule.evaluate(dummy_df, {"pbr_rank": 1, "n_eligible": 15})
        assert res.triggered is True


# ---------------------------------------------------------------------------
# T2: rule_value_composite_kr
# ---------------------------------------------------------------------------

class TestRuleValueCompositeKr:
    def test_triggers_when_vc_rank_in_top_n(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_value_composite_kr
        rule = rule_value_composite_kr(top_n=20, min_eligible=10)
        res = rule.evaluate(dummy_df, {"vc_rank": 8, "n_eligible": 40})
        assert res.triggered is True
        assert res.confidence == pytest.approx(75.0)

    def test_fails_when_vc_rank_none(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_value_composite_kr
        rule = rule_value_composite_kr()
        res = rule.evaluate(dummy_df, {"vc_rank": None, "n_eligible": 40})
        assert res.triggered is False

    def test_fails_when_n_eligible_below_min(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_value_composite_kr
        rule = rule_value_composite_kr(top_n=20, min_eligible=10)
        res = rule.evaluate(dummy_df, {"vc_rank": 1, "n_eligible": 9})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T3: rule_small_value
# ---------------------------------------------------------------------------

class TestRuleSmallValue:
    def test_triggers_when_smallvalue_rank_in_top_n(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_small_value
        rule = rule_small_value(top_n=20)
        res = rule.evaluate(dummy_df, {"smallvalue_rank": 12})
        assert res.triggered is True
        assert res.confidence == pytest.approx(78.0)

    def test_fails_when_rank_none(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_small_value
        rule = rule_small_value()
        res = rule.evaluate(dummy_df, {"smallvalue_rank": None})
        assert res.triggered is False

    def test_fails_when_rank_beyond_top_n(self, dummy_df):
        from strategies.books.moonbyungro_metric.rules import rule_small_value
        rule = rule_small_value(top_n=20)
        res = rule.evaluate(dummy_df, {"smallvalue_rank": 21})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T4: ALL_RULES + strategy + build
# ---------------------------------------------------------------------------

def test_all_rules_has_3_classes():
    from strategies.books.moonbyungro_metric import rules as rules_mod
    assert len(rules_mod.ALL_RULES) == 3
    names = [cls().name for cls in rules_mod.ALL_RULES]
    assert set(names) == {"low_pbr", "value_composite_kr", "small_value"}


def test_build_strategy_single_mode():
    from strategies.books.moonbyungro_metric.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="value_composite_kr")
    assert strat.name == "MoonByungroMetricStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "value_composite_kr"


def test_build_strategy_all_and_mode():
    from strategies.books.moonbyungro_metric.strategy import build_strategy
    strat = build_strategy(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 3


def test_book_meta():
    from strategies.books.moonbyungro_metric.strategy import BOOK_META
    assert BOOK_META["id"] == "moonbyungro_metric"
    assert BOOK_META["category"] == "fundamental_factor_rank_kr"
    assert BOOK_META["data_granularity"] == "daily"


def test_generate_signal_returns_none_without_ctx(dummy_df):
    """ctx_extra 없이 generate_signal 호출 → 순위 None → None 반환."""
    from strategies.books.moonbyungro_metric.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="value_composite_kr")
    sig = strat.generate_signal("TEST", dummy_df, "daily")
    assert sig is None


def test_generate_signal_with_extra_ctx_triggers(dummy_df):
    from strategies.books.moonbyungro_metric.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="low_pbr")
    sig = strat.generate_signal_with_extra_ctx(
        "TEST", dummy_df, "daily",
        {"pbr_rank": 2, "n_eligible": 20},
    )
    assert sig is not None
    assert sig.signal_type.name in ("BUY", "STRONG_BUY")


# ---------------------------------------------------------------------------
# T5: run-script 5팩터 fund 빌드 + 횡단면 순위 (no-lookahead)
# ---------------------------------------------------------------------------

def _make_daily_with_mc(n: int, mc_won: float) -> pd.DataFrame:
    dates = pd.date_range("2025-01-02", periods=n, freq="B")
    close = np.linspace(10_000, 12_000, n)
    return pd.DataFrame({
        "datetime": dates,
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.full(n, 1_000_000),
        "market_cap": np.full(n, mc_won),
    })


def _fs_row(report_date, op, ocf, per, pbr, revenue):
    from datetime import date as _date
    return {
        "report_date": report_date if isinstance(report_date, _date) else pd.to_datetime(report_date).date(),
        "operating_profit": op, "operating_cash_flow": ocf,
        "per": per, "pbr": pbr, "revenue": revenue,
    }


class TestBuildFundByIdx:
    def test_all_five_factors_present_when_valid(self):
        from scripts.run_moonbyungro_metric import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)  # 1000억원
        # report_date 2024-06-30 → effective 105일 후 ≈ 2024-10-13 ≤ 2025 거래일
        fs = [_fs_row("2024-06-30", op=50.0, ocf=40.0, per=10.0, pbr=1.2, revenue=500.0)]
        fund = _build_fund_by_idx(df, fs)
        last = fund[-1]
        assert last is not None
        assert last["eligible_value"] is True
        for k in ("pbr", "per", "psr", "por", "pcr"):
            assert last[k] is not None and last[k] > 0
        # 단위 검증: mc_eok=1000, psr=1000/500=2.0, por=1000/50=20, pcr=1000/40=25
        assert last["psr"] == pytest.approx(2.0, rel=1e-6)
        assert last["por"] == pytest.approx(20.0, rel=1e-6)
        assert last["pcr"] == pytest.approx(25.0, rel=1e-6)

    def test_pcr_none_when_ocf_nonpositive(self):
        from scripts.run_moonbyungro_metric import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)
        fs = [_fs_row("2024-06-30", op=50.0, ocf=-10.0, per=10.0, pbr=1.2, revenue=500.0)]
        fund = _build_fund_by_idx(df, fs)
        last = fund[-1]
        assert last["pcr"] is None
        assert last["eligible_value"] is False  # 5팩터 교집합 깨짐

    def test_no_lookahead_fund_none_before_effective_date(self):
        """report_date+105d 가 거래일보다 미래면 그 봉 fund=None (no-lookahead)."""
        from scripts.run_moonbyungro_metric import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)
        # report_date 2025-12-31 → effective ≈ 2026-04 → 모든 2025 거래일보다 미래
        fs = [_fs_row("2025-12-31", op=50.0, ocf=40.0, per=10.0, pbr=1.2, revenue=500.0)]
        fund = _build_fund_by_idx(df, fs)
        assert all(f is None for f in fund)


class TestCrossSectionalRanks:
    def _build(self):
        from scripts.run_moonbyungro_metric import _build_fund_by_idx, _build_cross_sectional_ranks
        n = 40
        # 12종목: market_cap 과 펀더멘털을 차등 → 적격 교집합 충분
        data = {}
        fund_map = {}
        for j in range(12):
            mc = (j + 1) * 1e10  # 100억 ~ 1200억
            df = _make_daily_with_mc(n, mc_won=mc)
            data[f"A{j:02d}"] = df
            fs = [_fs_row("2024-06-30", op=50.0 + j, ocf=40.0 + j,
                          per=8.0 + j, pbr=0.5 + j * 0.2, revenue=400.0 + j * 10)]
            fund_map[f"A{j:02d}"] = _build_fund_by_idx(df, fs)
        return _build_cross_sectional_ranks(data, fund_map), data

    def test_ranks_and_pcr_sample_present(self):
        (out, data) = self._build()
        (vc_map, pbr_map, sv_map, nelig_map, nelig_by_date,
         psr_all, por_all, pcr_all, n_eligible_with_pcr) = out
        # 적격 교집합 표본(PCR 반영) > 0
        assert n_eligible_with_pcr > 0
        assert len(pcr_all) > 0
        assert len(por_all) > 0
        # 마지막 거래일 기준 vc_rank/pbr_rank/smallvalue_rank 존재
        last_i = len(data["A00"]) - 1
        vc_last = [vc_map[c][last_i] for c in data]
        assert any(v is not None for v in vc_last)
        # n_eligible 마지막 거래일 == 12 (전 종목 5팩터 적격)
        assert nelig_map["A00"][last_i] == 12
        # smallvalue_rank: 하위 40% 게이트 → 일부만 부여(작은 시총 종목)
        sv_last = {c: sv_map[c][last_i] for c in data}
        assert sv_last["A00"] is not None  # 가장 작은 시총 → 게이트 통과
        assert sv_last["A11"] is None      # 가장 큰 시총 → 게이트 탈락

    def test_pbr_rank_lowest_pbr_is_rank_1(self):
        (out, data) = self._build()
        (vc_map, pbr_map, sv_map, nelig_map, nelig_by_date,
         psr_all, por_all, pcr_all, n_eligible_with_pcr) = out
        last_i = len(data["A00"]) - 1
        # A00 pbr=0.5 (최저) → pbr_rank==1
        assert pbr_map["A00"][last_i] == 1
