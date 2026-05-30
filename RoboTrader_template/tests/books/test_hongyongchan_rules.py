"""홍용찬 실전 퀀트투자 rules + run-script 횡단면 순위 — 단위 테스트.

4선 저밸류(PER+PBR+PCR+PSR) + 소형주 하위20% + 성장/마진/부채 게이트(hong_rank).
배당 전략은 사장님 방침으로 제외(테스트 없음).
"""
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
# T1: rule_value4_low
# ---------------------------------------------------------------------------

class TestRuleValue4Low:
    def test_triggers_when_v4_rank_in_top_n(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_value4_low
        rule = rule_value4_low(top_n=20, min_eligible=10)
        res = rule.evaluate(dummy_df, {"v4_rank": 8, "n_eligible": 40})
        assert res.triggered is True
        assert res.side == "buy"
        assert res.confidence == pytest.approx(73.0)

    def test_fails_when_v4_rank_none(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_value4_low
        rule = rule_value4_low()
        res = rule.evaluate(dummy_df, {"v4_rank": None, "n_eligible": 40})
        assert res.triggered is False

    def test_fails_when_rank_beyond_top_n(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_value4_low
        rule = rule_value4_low(top_n=20, min_eligible=10)
        res = rule.evaluate(dummy_df, {"v4_rank": 25, "n_eligible": 30})
        assert res.triggered is False

    def test_fails_when_n_eligible_below_min(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_value4_low
        rule = rule_value4_low(top_n=20, min_eligible=10)
        res = rule.evaluate(dummy_df, {"v4_rank": 1, "n_eligible": 9})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T2: rule_small_value4
# ---------------------------------------------------------------------------

class TestRuleSmallValue4:
    def test_triggers_when_smallv4_rank_in_top_n(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_small_value4
        rule = rule_small_value4(top_n=20)
        res = rule.evaluate(dummy_df, {"smallv4_rank": 12})
        assert res.triggered is True
        assert res.confidence == pytest.approx(78.0)

    def test_fails_when_rank_none(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_small_value4
        rule = rule_small_value4()
        res = rule.evaluate(dummy_df, {"smallv4_rank": None})
        assert res.triggered is False

    def test_fails_when_rank_beyond_top_n(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_small_value4
        rule = rule_small_value4(top_n=20)
        res = rule.evaluate(dummy_df, {"smallv4_rank": 21})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T3: rule_hong_combo
# ---------------------------------------------------------------------------

class TestRuleHongCombo:
    def test_triggers_when_hong_rank_in_top_n(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_hong_combo
        rule = rule_hong_combo(top_n=20)
        res = rule.evaluate(dummy_df, {"hong_rank": 5})
        assert res.triggered is True
        assert res.confidence == pytest.approx(80.0)

    def test_fails_when_rank_none(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_hong_combo
        rule = rule_hong_combo()
        res = rule.evaluate(dummy_df, {"hong_rank": None})
        assert res.triggered is False

    def test_fails_when_rank_beyond_top_n(self, dummy_df):
        from strategies.books.hongyongchan.rules import rule_hong_combo
        rule = rule_hong_combo(top_n=20)
        res = rule.evaluate(dummy_df, {"hong_rank": 21})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T4: ALL_RULES + strategy + build
# ---------------------------------------------------------------------------

def test_all_rules_has_3_classes():
    from strategies.books.hongyongchan import rules as rules_mod
    assert len(rules_mod.ALL_RULES) == 3
    names = [cls().name for cls in rules_mod.ALL_RULES]
    assert set(names) == {"value4_low", "small_value4", "hong_combo"}


def test_build_strategy_single_mode():
    from strategies.books.hongyongchan.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="value4_low")
    assert strat.name == "HongYongchanStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "value4_low"


def test_build_strategy_all_and_mode():
    from strategies.books.hongyongchan.strategy import build_strategy
    strat = build_strategy(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 3


def test_book_meta():
    from strategies.books.hongyongchan.strategy import BOOK_META
    assert BOOK_META["id"] == "hongyongchan"
    assert BOOK_META["category"] == "fundamental_multifactor_kr"
    assert BOOK_META["data_granularity"] == "daily"


def test_generate_signal_returns_none_without_ctx(dummy_df):
    """ctx_extra 없이 generate_signal 호출 → 순위 None → None 반환."""
    from strategies.books.hongyongchan.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="value4_low")
    sig = strat.generate_signal("TEST", dummy_df, "daily")
    assert sig is None


def test_generate_signal_with_extra_ctx_triggers(dummy_df):
    from strategies.books.hongyongchan.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="value4_low")
    sig = strat.generate_signal_with_extra_ctx(
        "TEST", dummy_df, "daily",
        {"v4_rank": 2, "n_eligible": 20},
    )
    assert sig is not None
    assert sig.signal_type.name in ("BUY", "STRONG_BUY")


# ---------------------------------------------------------------------------
# T5: run-script 4선 fund 빌드 + 횡단면 순위 (no-lookahead)
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


def _fs_row(report_date, ocf, per, pbr, revenue, op=50.0, ni=30.0,
            roe=None, opm=None, debt=None):
    from datetime import date as _date
    return {
        "report_date": report_date if isinstance(report_date, _date) else pd.to_datetime(report_date).date(),
        "operating_cash_flow": ocf,
        "per": per, "pbr": pbr, "revenue": revenue,
        "operating_profit": op, "net_income": ni,
        "roe": roe, "operating_margin": opm, "debt_ratio": debt,
    }


class TestBuildFundByIdx:
    def test_all_four_factors_present_when_valid(self):
        from scripts.run_hongyongchan import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)  # 1000억원
        fs = [_fs_row("2024-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=500.0)]
        fund = _build_fund_by_idx(df, fs)
        last = fund[-1]
        assert last is not None
        assert last["eligible_value"] is True
        for k in ("pbr", "per", "psr", "pcr"):
            assert last[k] is not None and last[k] > 0
        # 단위 검증: mc_eok=1000, psr=1000/500=2.0, pcr=1000/40=25
        assert last["psr"] == pytest.approx(2.0, rel=1e-6)
        assert last["pcr"] == pytest.approx(25.0, rel=1e-6)

    def test_pcr_none_when_ocf_nonpositive(self):
        from scripts.run_hongyongchan import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)
        fs = [_fs_row("2024-06-30", ocf=-10.0, per=10.0, pbr=1.2, revenue=500.0)]
        fund = _build_fund_by_idx(df, fs)
        last = fund[-1]
        assert last["pcr"] is None
        assert last["eligible_value"] is False  # 4선 교집합 깨짐

    def test_no_lookahead_fund_none_before_effective_date(self):
        """report_date+105d 가 거래일보다 미래면 그 봉 fund=None (no-lookahead)."""
        from scripts.run_hongyongchan import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)
        fs = [_fs_row("2025-12-31", ocf=40.0, per=10.0, pbr=1.2, revenue=500.0)]
        fund = _build_fund_by_idx(df, fs)
        assert all(f is None for f in fund)

    def test_gate_profitable_requires_positive_op_and_ni(self):
        """흑자 게이트: op<=0 또는 ni<=0 이면 gate_pass=False."""
        from scripts.run_hongyongchan import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)
        # 적자(op<0) + 성장 가능하더라도 profitable=False → gate_pass=False
        fs = [
            _fs_row("2023-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=400.0, op=-5.0, ni=-3.0),
            _fs_row("2024-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=500.0, op=-5.0, ni=-3.0),
        ]
        fund = _build_fund_by_idx(df, fs)
        last = fund[-1]
        assert last["profitable"] is False
        assert last["gate_pass"] is False

    def test_gate_growth_yoy_positive(self):
        """성장YoY: revenue 또는 net_income 전년 대비 증가 시 growth_pos=True."""
        from scripts.run_hongyongchan import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)
        fs = [
            _fs_row("2023-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=400.0, op=40.0, ni=20.0),
            _fs_row("2024-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=500.0, op=50.0, ni=30.0),
        ]
        fund = _build_fund_by_idx(df, fs)
        last = fund[-1]
        # 직전(2023) 대비 revenue 400→500 증가 → growth_pos
        assert last["growth_pos"] is True
        assert last["profitable"] is True
        assert last["gate_pass"] is True

    def test_gate_debt_ratio_over_max_blocks(self):
        """부채비율 상한 초과 시 gate_pass=False (debt 값 present)."""
        from scripts.run_hongyongchan import _build_fund_by_idx, DEBT_MAX
        df = _make_daily_with_mc(40, mc_won=1e11)
        fs = [
            _fs_row("2023-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=400.0, op=40.0, ni=20.0),
            _fs_row("2024-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=500.0, op=50.0, ni=30.0,
                    debt=DEBT_MAX + 100.0),
        ]
        fund = _build_fund_by_idx(df, fs)
        last = fund[-1]
        assert last["gate_pass"] is False

    def test_gate_skip_missing_passes_when_metrics_none(self):
        """skip-missing: roe/opm/debt None 이면 게이트 통과(흑자·성장만 충족하면 gate_pass)."""
        from scripts.run_hongyongchan import _build_fund_by_idx
        df = _make_daily_with_mc(40, mc_won=1e11)
        fs = [
            _fs_row("2023-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=400.0, op=40.0, ni=20.0),
            _fs_row("2024-06-30", ocf=40.0, per=10.0, pbr=1.2, revenue=500.0, op=50.0, ni=30.0,
                    roe=None, opm=None, debt=None),
        ]
        fund = _build_fund_by_idx(df, fs)
        last = fund[-1]
        assert last["gate_pass"] is True  # 게이트 지표 없어도 통과


class TestCrossSectionalRanks:
    def _build(self):
        from scripts.run_hongyongchan import _build_fund_by_idx, _build_cross_sectional_ranks
        n = 40
        data = {}
        fund_map = {}
        for j in range(12):
            mc = (j + 1) * 1e10  # 100억 ~ 1200억
            df = _make_daily_with_mc(n, mc_won=mc)
            data[f"A{j:02d}"] = df
            fs = [
                _fs_row("2023-06-30", ocf=40.0 + j, per=8.0 + j, pbr=0.5 + j * 0.2,
                        revenue=400.0 + j * 10, op=40.0 + j, ni=20.0 + j),
                _fs_row("2024-06-30", ocf=40.0 + j, per=8.0 + j, pbr=0.5 + j * 0.2,
                        revenue=450.0 + j * 10, op=45.0 + j, ni=25.0 + j),  # 성장(revenue↑)
            ]
            fund_map[f"A{j:02d}"] = _build_fund_by_idx(df, fs)
        return _build_cross_sectional_ranks(data, fund_map), data

    def test_ranks_and_pcr_sample_present(self):
        (out, data) = self._build()
        (v4_map, sv_map, hong_map, nelig_map, nelig_by_date, nhong_by_date,
         psr_all, pcr_all, n_eligible_with_pcr) = out
        assert n_eligible_with_pcr > 0
        assert len(pcr_all) > 0
        last_i = len(data["A00"]) - 1
        v4_last = [v4_map[c][last_i] for c in data]
        assert any(v is not None for v in v4_last)
        # n_eligible 마지막 거래일 == 12 (전 종목 4선 적격)
        assert nelig_map["A00"][last_i] == 12
        # smallv4_rank: 하위 20% 게이트 → 일부만 부여(작은 시총 종목)
        sv_last = {c: sv_map[c][last_i] for c in data}
        assert sv_last["A00"] is not None  # 가장 작은 시총 → 게이트 통과
        assert sv_last["A11"] is None      # 가장 큰 시총 → 게이트 탈락

    def test_smallcap_20pct_tighter_than_40pct(self):
        """소형주 게이트 20% → 12종목 중 약 하위 2~3종목만 통과(40%보다 타이트)."""
        (out, data) = self._build()
        (v4_map, sv_map, hong_map, nelig_map, nelig_by_date, nhong_by_date,
         psr_all, pcr_all, n_eligible_with_pcr) = out
        last_i = len(data["A00"]) - 1
        sv_passers = [c for c in data if sv_map[c][last_i] is not None]
        # 12종목의 20%ile 게이트 → 소수만 통과 (전체의 절반 미만)
        assert 0 < len(sv_passers) < 6

    def test_hong_rank_subset_of_smallcap(self):
        """hong_rank 부여 종목은 smallv4 게이트 통과 종목의 부분집합(게이트 추가 적용)."""
        (out, data) = self._build()
        (v4_map, sv_map, hong_map, nelig_map, nelig_by_date, nhong_by_date,
         psr_all, pcr_all, n_eligible_with_pcr) = out
        last_i = len(data["A00"]) - 1
        hong_passers = {c for c in data if hong_map[c][last_i] is not None}
        sv_passers = {c for c in data if sv_map[c][last_i] is not None}
        assert hong_passers.issubset(sv_passers)
        # 본 픽스처는 전 종목 흑자·성장 → 소형주 통과 종목은 모두 hong 통과
        assert hong_passers == sv_passers
