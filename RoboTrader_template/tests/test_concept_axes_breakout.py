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

    def test_histogram_is_reproduced_across_multiple_deciles(self):
        """arm 의 need 가 «여러 분위»에 걸치면 R_B 의 분위 도수분포도 그것과
        «정확히» 같아야 한다. 기존 픽스처(k=7, 전부 최상위 한 분위)는 이 단언을
        못 한다 — 「크기만 맞추고 층화 안 함」·「도수분포를 풀 모양으로 채움」
        변이가 그 9개를 전부 통과할 수 있었던 이유다."""
        n = 100
        pool_all = {"D1": [(f"C{i:03d}", float(1000 - i)) for i in range(n)]}
        dayret = {"D1": {f"C{i:03d}": i / 100.0 for i in range(n)}}
        arm_idx = [0, 1, 40, 41, 90, 91]           # 분위 0·4·9 에 걸쳐 2개씩
        arm_pool = {"D1": [(f"C{i:03d}", float(1000 - i)) for i in arm_idx]}
        sel, diag = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=5)
        picked = sel["D1"]
        assert len(picked) == 6
        assert diag["n_need"] == 6

        edges = np.quantile(list(dayret["D1"].values()), np.arange(1, 10) / 10.0)

        def _bin(x):
            return int(np.searchsorted(edges, x, side="right"))

        need_hist = {b: 0 for b in range(10)}
        for i in arm_idx:
            need_hist[_bin(dayret["D1"][f"C{i:03d}"])] += 1

        got_hist = {b: 0 for b in range(10)}
        for c in picked:
            got_hist[_bin(dayret["D1"][c])] += 1

        assert got_hist == need_hist, f"분위 도수분포 불일치: need={need_hist} got={got_hist}"

    def test_rb_is_not_identical_to_arm(self):
        """`R_B` 가 매 시드마다 arm 선택과 «똑같지» 않아야 한다 — 항상 같다면
        `select_random_matched` 이 그냥 arm 을 되돌려주는 최악의 오구현일 수 있다
        (리뷰어 변이 테스트에서 기존 9개 중 8개가 이 오구현을 통과시켰다)."""
        pool_all, arm_pool, dayret = self._fixture(n=100, k=7)
        arm_codes = sorted(c for c, _ in arm_pool["D1"])
        differs = False
        for seed in range(20):
            sel, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=seed)
            if sorted(sel["D1"]) != arm_codes:
                differs = True
                break
        assert differs, "20개 시드 전부 R_B == arm — 귀무가 arm 자신을 그대로 돌려주고 있다"

    def test_decile_edges_come_from_pool_not_arm(self):
        """분위 «경계»는 arm 이 아니라 «풀 전체»(cand) 에서 나와야 한다(§2-2 2단계).
        50종목을 5개씩 정확히 10등분해 최상위 분위(bin9) 의 «풀 전체 기준»
        진짜 구성원을 arm 요구치(5개)와 «정확히» 같게 만들면, 대체 없이 그
        5개 전부가 (시드와 무관하게) 뽑혀야 한다. edges 를 arm 자신의 값에서
        산출하면 이 등식이 깨진다(§2-2 2단계 정면 위반)."""
        n = 50
        pool_all = {"D1": [(f"C{i:02d}", float(1000 - i)) for i in range(n)]}
        dayret = {"D1": {f"C{i:02d}": i / 50.0 for i in range(n)}}
        top5 = [45, 46, 47, 48, 49]
        arm_pool = {"D1": [(f"C{i:02d}", float(1000 - i)) for i in top5]}
        expect = sorted(f"C{i:02d}" for i in top5)
        for seed in (0, 1, 2, 7):
            sel, diag = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=seed)
            assert sorted(sel["D1"]) == expect, f"seed={seed}: {sel['D1']}"
            assert diag["n_sub"] == 0


class TestGateRowsBreakout:
    def test_selected_and_truncation_and_gate_flag(self):
        pools = {
            "B": {"D1": [(f"C{i}", float(i)) for i in range(30)]},
            "D": {"D1": [(f"C{i}", float(i)) for i in range(5)]},
        }
        sels = {"B": {"D1": [f"C{i}" for i in range(10)]},
                "D": {"D1": [f"C{i}" for i in range(5)]}}
        dayret = {"D1": {f"C{i}": 0.01 * i for i in range(30)}}
        limitup = {"D1": {f"C{i}": (i == 29) for i in range(30)}}
        rows = RUN.gate_rows_breakout(pools, sels, dayret, limitup)
        by = {r["arm"]: r for r in rows}
        assert by["B"]["triggers"] == 30
        assert by["B"]["selected"] == 10
        assert abs(by["B"]["keep_pct"] - 100 * 10 / 30) < 1e-9
        assert by["B"]["gate_pass"] is False        # 10 < GATE_MIN_SELECTED
        assert by["D"]["selected"] == 5

    def test_limit_up_and_median_dayret(self):
        pools = {"B": {"D1": [("A", 1.0), ("B", 2.0), ("C", 3.0)]}}
        sels = {"B": {"D1": ["A", "B", "C"]}}
        dayret = {"D1": {"A": 0.01, "B": 0.05, "C": 0.09}}
        limitup = {"D1": {"A": False, "B": False, "C": True}}
        rows = RUN.gate_rows_breakout(pools, sels, dayret, limitup)
        r = rows[0]
        assert abs(r["med_dayret"] - 0.05) < 1e-9
        assert abs(r["limitup_pct"] - 100 / 3) < 1e-6

    def test_regap_le5_uses_bar_gaps_within_code(self):
        """같은 종목의 «연속 발화» 비율. 상태형(dryup)과 사건형(돌파)을 가른다."""
        pools = {"B": {"D1": [("A", 1.0)], "D2": [("A", 1.0)], "D9": [("A", 1.0)]}}
        sels = {"B": {}}
        dayret = {d: {"A": 0.0} for d in ("D1", "D2", "D9")}
        limitup = {d: {"A": False} for d in ("D1", "D2", "D9")}
        rows = RUN.gate_rows_breakout(pools, sels, dayret, limitup,
                                      date_index={"D1": 0, "D2": 1, "D9": 8})
        r = rows[0]
        # 간격 [1, 7] -> ≤5 는 1/2
        assert abs(r["regap_le5_pct"] - 50.0) < 1e-9


class TestGateExecRows:
    def _frames(self):
        import pandas as pd
        g = pd.DataFrame(dict(
            date=["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"],
            open=[100.0, 104.0, 100.0, 100.0, 100.0, 100.0, 100.0, 136.0],
            high=[100.0, 106.0, 101.0, 101.0, 101.0, 101.0, 140.0, 140.0],
            low=[99.0, 103.0, 99.0, 99.0, 99.0, 99.0, 99.0, 130.0],
            close=[100.0, 105.0, 100.0, 100.0, 100.0, 100.0, 135.0, 135.0],
            volume=[1.0] * 8,
        ))
        frames = {"AAA": g}
        im = {d: i for i, d in enumerate(g["date"])}
        im["__last__"] = len(g) - 1
        return frames, {"AAA": im}

    def test_band_ok_when_next_open_within_3pct(self):
        frames, idxmap = self._frames()
        pools = {"B": {"D3": [("AAA", 1.0)]}}      # 다음봉(D4) 시가 100 vs 종가 100 -> 0%
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["band_ok_pct"] == 100.0

    def test_band_blocked_when_next_open_above_band(self):
        frames, idxmap = self._frames()
        pools = {"B": {"D1": [("AAA", 1.0)]}}      # D1 종가 100 -> D2 시가 104 = +4% > 3%
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["band_ok_pct"] == 0.0

    def test_band_dead_when_next_low_also_above_band(self):
        """다음날 «저가»조차 밴드 위 = 그날 내내 체결 불가."""
        frames, idxmap = self._frames()
        pools = {"B": {"D1": [("AAA", 1.0)]}}      # D2 저가 103 > 103.0? 경계 확인
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["band_dead_pct"] == 0.0     # 103 <= 103.0 이므로 체결 가능

    def test_impossible_up_bar_counted(self):
        """KRX 한도(+30%) 초과 = 데이터 인공물. 가드는 «하락»만 보므로 여기서 센다."""
        frames, idxmap = self._frames()
        pools = {"B": {"D7": [("AAA", 1.0)]}}      # 100 -> 135 = +35% > 31%
        # 🔑 D8 이 있으므로 「다음 봉 없음」 가드에 걸리지 않는다
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["impossible_up"] == 1

    def test_vol5_median_is_finite(self):
        frames, idxmap = self._frames()
        pools = {"B": {"D1": [("AAA", 1.0)]}}
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["vol5_med"] == rows[0]["vol5_med"]   # not NaN


class TestGateOverlap:
    def test_jaccard_of_selected_pairs(self):
        sels = {
            "B": {"D1": ["A", "B"], "D2": ["C"]},
            "D": {"D1": ["B"], "D2": ["C", "E"]},
        }
        ov = RUN.gate_overlap(sels)
        # B = {(D1,A),(D1,B),(D2,C)} · D = {(D1,B),(D2,C),(D2,E)} -> 교집합 2 / 합집합 4
        # 🔴 판단 지점(task-7): 키 순서는 sels 삽입순이 아니라 ARM_RULE_B 의 고정 순서
        # (D,B,P,Q,DB) 를 따른다 — 브리프 원문은 ("B","D") 였으나 실제 산출 키는
        # ("D","B") 다(값 0.5 는 브리프와 동일, 순서만 정정). 상세: task-7-report.md.
        assert abs(ov[("D", "B")] - 0.5) < 1e-9

    def test_identical_arms_are_one(self):
        sels = {"B": {"D1": ["A"]}, "P": {"D1": ["A"]}}
        assert abs(RUN.gate_overlap(sels)[("B", "P")] - 1.0) < 1e-9
