"""문서 5(PREREG_BREAKOUT.md) — 돌파 축 실행기."""
import importlib

import numpy as np
import pytest

RUN = importlib.import_module("backtest.concept_axes.minervini.run")


def _series(n=30, high=100.0, vol=1000.0):
    return (np.full(n, high), np.full(n, vol), np.full(n, high - 1.0))


class TestBreakoutFlags:
    def test_frozen_params(self):
        assert RUN.PIVOT_WIN == 25
        assert RUN.RVOL_MIN == 1.5
        assert RUN.S_BREAKOUT == 100
        assert RUN.GATE_MIN_SELECTED == 1500

    def test_insufficient_bars_returns_false(self):
        h, v, c = _series(30)
        # i = 24 -> base 는 [-1, 24) 가 되어 26봉 미만. 사양 §2 가드.
        assert RUN.breakout_flags(h, v, c, 24) == (False, False)

    def test_exactly_26_bars_is_allowed(self):
        h, v, c = _series(30)
        h[:25] = 100.0
        c[25] = 101.0          # 돌파
        v[:25] = 1000.0
        v[25] = 1600.0         # RVOL 1.6
        assert RUN.breakout_flags(h, v, c, 25) == (True, True)

    def test_pivot_uses_base_high_excluding_current_bar(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        h[30] = 999.0          # «현재봉» 고가는 피벗에 들어가면 안 된다
        c[30] = 101.0
        v[:30] = 1000.0
        v[30] = 2000.0
        ok_p, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_p is True, "현재봉 high 가 피벗에 섞이면 돌파가 False 가 된다"

    def test_close_equal_to_pivot_is_not_breakout(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 100.0          # 초과가 아니라 «같음»
        v[:30] = 1000.0
        v[30] = 2000.0
        ok_p, _ = RUN.breakout_flags(h, v, c, 30)
        assert ok_p is False

    def test_rvol_boundary_is_inclusive(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0
        v[:30] = 1000.0
        v[30] = 1500.0         # 정확히 1.5배
        _, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_q is True

    def test_zero_base_volume_is_false(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0
        v[:30] = 0.0
        v[30] = 5000.0
        _, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_q is False

    def test_flags_are_independent(self):
        """P(돌파만)·Q(거래량만) 분해가 가능해야 한다."""
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0          # 돌파 O
        v[:30] = 1000.0
        v[30] = 1000.0         # RVOL 1.0 -> X
        assert RUN.breakout_flags(h, v, c, 30) == (True, False)


class TestBuildCacheBreakout:
    def _px(self):
        """2종목 × 40봉 합성 프레임. DB 미접속."""
        import pandas as pd
        rows = []
        for code in ("AAA111", "BBB222"):
            for i in range(40):
                rows.append(dict(
                    stock_code=code, date=f"2024-01-{i+1:02d}",
                    open=100.0, high=100.0, low=99.0, close=99.0, volume=1000.0,
                ))
        df = pd.DataFrame(rows)
        # AAA111 의 마지막 봉만 돌파 + 거래량 폭증
        m = (df["stock_code"] == "AAA111") & (df["date"] == "2024-01-40")
        df.loc[m, "close"] = 130.0   # 130/99 = 1.313 -> limit_up 성립
        df.loc[m, "volume"] = 3000.0
        return df

    def test_cache_tuple_order_and_types(self):
        px = self._px()
        elig = {d: {"AAA111", "BBB222"} for d in px["date"].unique()}
        params = dict(recent_window=10, base_window=30, ratio_max=0.70)
        cache, stats = RUN.build_cache_breakout(px, elig, params)
        val = cache["AAA111"]["2024-01-40"]
        assert len(val) == 6, "캐시 튜플 길이가 바뀌면 build_pools_breakout 이 깨진다"
        score, ok_dry, ok_p, ok_q, day_ret, limit_up = val
        assert isinstance(score, float)
        assert isinstance(ok_dry, bool) and isinstance(ok_p, bool)
        assert isinstance(ok_q, bool) and isinstance(limit_up, bool)
        assert ok_p is True and ok_q is True

    def test_day_ret_is_close_over_prev_close(self):
        px = self._px()
        elig = {d: {"AAA111"} for d in px["date"].unique()}
        params = dict(recent_window=10, base_window=30, ratio_max=0.70)
        cache, _ = RUN.build_cache_breakout(px, elig, params)
        _, _, _, _, day_ret, limit_up = cache["AAA111"]["2024-01-40"]
        assert abs(day_ret - (130.0 / 99.0 - 1.0)) < 1e-9
        assert limit_up is True

    def test_ineligible_pairs_are_skipped(self):
        px = self._px()
        elig = {d: {"BBB222"} for d in px["date"].unique()}   # AAA111 부적격
        params = dict(recent_window=10, base_window=30, ratio_max=0.70)
        cache, stats = RUN.build_cache_breakout(px, elig, params)
        assert "AAA111" not in cache
        assert stats["n_eval"] == 40

    def test_stats_keys(self):
        px = self._px()
        elig = {d: {"AAA111", "BBB222"} for d in px["date"].unique()}
        params = dict(recent_window=10, base_window=30, ratio_max=0.70)
        _, stats = RUN.build_cache_breakout(px, elig, params)
        for k in ("n_eval", "n_dry", "n_p", "n_q", "n_b", "n_short_bars", "secs"):
            assert k in stats


class TestArmRuleB:
    def test_keys_exact(self):
        assert set(RUN.ARM_RULE_B) == {"D", "B", "P", "Q", "DB"}

    def test_truth_table(self):
        cases = [
            ((True, True, True), {"D", "B", "P", "Q", "DB"}),
            ((False, True, True), {"B", "P", "Q"}),
            ((True, True, False), {"D", "P"}),
            ((True, False, True), {"D", "Q"}),
            ((False, False, False), set()),
        ]
        for args, expect in cases:
            fired = {a for a, fn in RUN.ARM_RULE_B.items() if fn(*args)}
            assert fired == expect, f"{args} -> {fired}"

    def test_doc1_arm_rule_untouched(self):
        assert set(RUN.ARM_RULE) == {"D", "DT", "DF", "DTF", "T"}


class TestBuildPoolsBreakout:
    def _cache(self):
        # (score, ok_dry, ok_p, ok_q, day_ret, limit_up)
        return {
            "AAA111": {"D1": (100.0, True, True, True, 0.07, False)},
            "BBB222": {"D1": (200.0, True, False, False, -0.01, False)},
            "CCC333": {"D1": (300.0, False, True, True, 0.30, True)},
        }

    def test_pools_and_all_key(self):
        elig = {"D1": {"AAA111", "BBB222", "CCC333"}}
        pools, dayret, limitup = RUN.build_pools_breakout(self._cache(), elig)
        assert {c for c, _ in pools["ALL"]["D1"]} == {"AAA111", "BBB222", "CCC333"}
        assert {c for c, _ in pools["B"]["D1"]} == {"AAA111", "CCC333"}
        assert {c for c, _ in pools["DB"]["D1"]} == {"AAA111"}
        assert {c for c, _ in pools["D"]["D1"]} == {"AAA111", "BBB222"}

    def test_dayret_and_limitup_maps(self):
        elig = {"D1": {"AAA111", "BBB222", "CCC333"}}
        _, dayret, limitup = RUN.build_pools_breakout(self._cache(), elig)
        assert abs(dayret["D1"]["AAA111"] - 0.07) < 1e-12
        assert limitup["D1"]["CCC333"] is True

    def test_nan_dayret_is_excluded(self):
        cache = {"AAA111": {"D1": (100.0, True, True, True, float("nan"), False)}}
        elig = {"D1": {"AAA111"}}
        _, dayret, _ = RUN.build_pools_breakout(cache, elig)
        assert "AAA111" not in dayret.get("D1", {})

    def test_ineligible_excluded(self):
        elig = {"D1": {"AAA111"}}
        pools, _, _ = RUN.build_pools_breakout(self._cache(), elig)
        assert {c for c, _ in pools["ALL"]["D1"]} == {"AAA111"}


class TestSelectRandomMatched:
    def _fixture(self, n=100, k=7):
        """1일치. 풀 n종목, arm 이 «상위 수익률» k종목을 고른 상황."""
        pool_all = {"D1": [(f"C{i:04d}", float(1000 - i)) for i in range(n)]}
        dayret = {"D1": {f"C{i:04d}": (n - i) / 1000.0 for i in range(n)}}
        arm_pool = {"D1": [(f"C{i:04d}", float(1000 - i)) for i in range(k)]}
        return pool_all, arm_pool, dayret

    def test_size_matches_arm_trigger_count(self):
        pool_all, arm_pool, dayret = self._fixture(n=100, k=7)
        sel, diag = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        # k=7 < MAX_CANDIDATES=10 이므로 절단 없이 7개
        assert len(sel["D1"]) == 7
        assert diag["n_need"] == 7

    def test_select_top_cap_applied(self):
        pool_all, arm_pool, dayret = self._fixture(n=100, k=40)
        sel, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        assert len(sel["D1"]) == RUN.MAX_CANDIDATES

    def test_stratification_matches_decile_histogram(self):
        """arm 이 최상위 분위에만 있으면 R_B 도 그 분위에서만 뽑혀야 한다."""
        pool_all, arm_pool, dayret = self._fixture(n=100, k=7)
        sel, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=3)
        picked = sel["D1"]
        vals = [dayret["D1"][c] for c in picked]
        # arm 7개는 전부 상위 10% 안. 뽑힌 것도 상위 10% 경계 위여야 한다.
        import numpy as np
        edge = np.quantile(list(dayret["D1"].values()), 0.9)
        assert all(v >= edge for v in vals), f"층화 실패: {vals}"

    def test_deterministic_for_same_seed(self):
        pool_all, arm_pool, dayret = self._fixture()
        a, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=11)
        b, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=11)
        assert a == b

    def test_different_seeds_differ(self):
        pool_all, arm_pool, dayret = self._fixture(n=200, k=15)
        a, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=1)
        b, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=2)
        assert a != b

    def test_arm_own_picks_are_not_excluded_from_pool(self):
        """§2-2 3단계 — arm 자신이 고른 종목을 빼면 «반대 방향»으로 편향된다."""
        pool_all = {"D1": [("X1", 10.0), ("X2", 9.0)]}
        dayret = {"D1": {"X1": 0.05, "X2": 0.05}}
        arm_pool = {"D1": [("X1", 10.0), ("X2", 9.0)]}
        sel, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        assert set(sel["D1"]) == {"X1", "X2"}

    def test_substitution_counted_when_bucket_short(self):
        """한 분위에 필요한 만큼 없으면 인접 분위로 대체하고 «센다»."""
        pool_all = {"D1": [(f"C{i}", float(i)) for i in range(10)]}
        dayret = {"D1": {f"C{i}": i / 100.0 for i in range(10)}}
        # arm 이 같은 분위에서 3개를 요구하지만 그 분위엔 1개뿐인 상황을 만든다
        arm_pool = {"D1": [("C9", 9.0), ("C9", 9.0), ("C9", 9.0)]}
        sel, diag = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        assert diag["n_sub"] >= 1
        assert len(sel["D1"]) == 3

    def test_no_dayret_codes_are_counted_and_skipped(self):
        pool_all = {"D1": [("A", 1.0), ("B", 2.0), ("C", 3.0)]}
        dayret = {"D1": {"A": 0.01}}          # B, C 는 수익률 없음
        arm_pool = {"D1": [("A", 1.0)]}
        sel, diag = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        assert diag["n_no_ret"] == 2
        assert sel["D1"] == ["A"]

    def test_empty_arm_day_produces_no_entry(self):
        pool_all = {"D1": [("A", 1.0)]}
        dayret = {"D1": {"A": 0.0}}
        sel, _ = RUN.select_random_matched(pool_all, {"D1": []}, dayret, seed=0)
        assert "D1" not in sel
