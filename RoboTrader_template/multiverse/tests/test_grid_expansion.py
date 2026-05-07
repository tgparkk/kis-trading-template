"""Phase G1 — 4 페르소나 압축 그리드 + spike_precursor/inverse 단위 테스트."""
from __future__ import annotations

import pytest

from RoboTrader_template.multiverse.composable.personas._grid import (
    expand_grid_intraday,
    expand_grid_long_term,
    expand_grid_quant,
    expand_grid_swing,
    expand_grid_spike_precursor,
    expand_grid_spike_precursor_inverse,
    expand_grid_trend_starter,
    _4_simplex_4,
    _roe_pbr_weight_4,
)


# ──────────────────────────────────────────────────────────────────────────────
# 보조 헬퍼 테스트 (2건)
# ──────────────────────────────────────────────────────────────────────────────

def test_4_simplex_4_weights_sum_to_1():
    """_4_simplex_4: 4개 조합 모두 합=1.0."""
    for combo in _4_simplex_4():
        total = sum(combo)
        assert abs(total - 1.0) <= 0.01, f"합={total:.4f} — 1.0 아님: {combo}"


def test_roe_pbr_weight_4_weights_sum_to_1():
    """_roe_pbr_weight_4: 4개 조합 모두 합=1.0."""
    for combo in _roe_pbr_weight_4():
        total = sum(combo)
        assert abs(total - 1.0) <= 0.01, f"합={total:.4f} — 1.0 아님: {combo}"


# ──────────────────────────────────────────────────────────────────────────────
# quant 그리드 (3건)
# ──────────────────────────────────────────────────────────────────────────────

def test_quant_grid_size():
    """quant 그리드 크기 100~150."""
    grid = expand_grid_quant()
    assert 100 <= len(grid) <= 150, f"quant grid 크기={len(grid)} (기대 100~150)"


def test_quant_grid_validates():
    """quant 그리드 모든 ParamSet이 validate() 통과."""
    for ps in expand_grid_quant():
        ps.validate()  # ValueError 없으면 통과


def test_quant_grid_unique():
    """quant 그리드 ParamSet 중복 없음."""
    grid = expand_grid_quant()
    hashes = [ps.config_hash() for ps in grid]
    assert len(set(hashes)) == len(hashes), f"quant 중복 {len(hashes) - len(set(hashes))}건"


# ──────────────────────────────────────────────────────────────────────────────
# long_term 그리드 (3건)
# ──────────────────────────────────────────────────────────────────────────────

def test_long_term_grid_size():
    """long_term 그리드 크기 100~150."""
    grid = expand_grid_long_term()
    assert 100 <= len(grid) <= 150, f"long_term grid 크기={len(grid)} (기대 100~150)"


def test_long_term_grid_validates():
    """long_term 그리드 모든 ParamSet이 validate() 통과."""
    for ps in expand_grid_long_term():
        ps.validate()


def test_long_term_grid_unique():
    """long_term 그리드 ParamSet 중복 없음."""
    grid = expand_grid_long_term()
    hashes = [ps.config_hash() for ps in grid]
    assert len(set(hashes)) == len(hashes), f"long_term 중복 {len(hashes) - len(set(hashes))}건"


# ──────────────────────────────────────────────────────────────────────────────
# swing 그리드 (3건)
# ──────────────────────────────────────────────────────────────────────────────

def test_swing_grid_size():
    """swing 그리드 크기 100~150."""
    grid = expand_grid_swing()
    assert 100 <= len(grid) <= 150, f"swing grid 크기={len(grid)} (기대 100~150)"


def test_swing_grid_validates():
    """swing 그리드 모든 ParamSet이 validate() 통과."""
    for ps in expand_grid_swing():
        ps.validate()


def test_swing_grid_unique():
    """swing 그리드 ParamSet 중복 없음."""
    grid = expand_grid_swing()
    hashes = [ps.config_hash() for ps in grid]
    assert len(set(hashes)) == len(hashes), f"swing 중복 {len(hashes) - len(set(hashes))}건"


# ──────────────────────────────────────────────────────────────────────────────
# intraday 그리드 (3건)
# ──────────────────────────────────────────────────────────────────────────────

def test_intraday_grid_size():
    """intraday 그리드 크기 100~150."""
    grid = expand_grid_intraday()
    assert 100 <= len(grid) <= 150, f"intraday grid 크기={len(grid)} (기대 100~150)"


def test_intraday_grid_validates():
    """intraday 그리드 모든 ParamSet이 validate() 통과."""
    for ps in expand_grid_intraday():
        ps.validate()


def test_intraday_grid_unique():
    """intraday 그리드 ParamSet 중복 없음."""
    grid = expand_grid_intraday()
    hashes = [ps.config_hash() for ps in grid]
    assert len(set(hashes)) == len(hashes), f"intraday 중복 {len(hashes) - len(set(hashes))}건"


# ──────────────────────────────────────────────────────────────────────────────
# 합산 테스트 (1건)
# ──────────────────────────────────────────────────────────────────────────────

def test_total_grid_count():
    """4 페르소나 합 400~600셀."""
    total = sum(
        len(g)
        for g in [
            expand_grid_quant(),
            expand_grid_long_term(),
            expand_grid_swing(),
            expand_grid_intraday(),
        ]
    )
    assert 400 <= total <= 600, f"4 페르소나 합={total} (기대 400~600)"


# ──────────────────────────────────────────────────────────────────────────────
# spike_precursor 그리드 (4건)
# ──────────────────────────────────────────────────────────────────────────────

def test_spike_precursor_grid_size():
    """spike_precursor 그리드 크기 200~216."""
    grid = expand_grid_spike_precursor()
    assert 200 <= len(grid) <= 216, f"spike_precursor grid 크기={len(grid)} (기대 200~216)"


def test_spike_precursor_grid_validates():
    """spike_precursor 그리드 모든 ParamSet이 validate() 통과."""
    for ps in expand_grid_spike_precursor():
        ps.validate()


def test_spike_precursor_grid_unique():
    """spike_precursor 그리드 ParamSet 중복 없음."""
    grid = expand_grid_spike_precursor()
    hashes = [ps.config_hash() for ps in grid]
    assert len(set(hashes)) == len(hashes), (
        f"spike_precursor 중복 {len(hashes) - len(set(hashes))}건"
    )


def test_spike_precursor_grid_holding_max_days():
    """spike_precursor 모든 ParamSet의 holding_max_days=1 (1일 보유 강제)."""
    for ps in expand_grid_spike_precursor():
        assert ps.holding_max_days == 1, (
            f"holding_max_days={ps.holding_max_days} (기대 1)"
        )


# ──────────────────────────────────────────────────────────────────────────────
# spike_precursor_inverse 그리드 (5건)
# ──────────────────────────────────────────────────────────────────────────────

def test_spike_precursor_inverse_grid_size():
    """spike_precursor_inverse 그리드 크기 200~650.

    축: 4(vol_z) × 3(ma20_ranges) × 3(atr) × 3(box) × 3(vol_trend) × 2(match_min) = 648이론.
    validate 실패 셀 없으므로 ~648.
    """
    grid = expand_grid_spike_precursor_inverse()
    assert 200 <= len(grid) <= 650, (
        f"spike_precursor_inverse grid 크기={len(grid)} (기대 200~650)"
    )


def test_spike_precursor_inverse_grid_validates():
    """spike_precursor_inverse 그리드 모든 ParamSet이 validate() 통과."""
    for ps in expand_grid_spike_precursor_inverse():
        ps.validate()


def test_spike_precursor_inverse_grid_unique():
    """spike_precursor_inverse 그리드 ParamSet 중복 없음."""
    grid = expand_grid_spike_precursor_inverse()
    hashes = [ps.config_hash() for ps in grid]
    assert len(set(hashes)) == len(hashes), (
        f"spike_precursor_inverse 중복 {len(hashes) - len(set(hashes))}건"
    )


def test_spike_precursor_inverse_grid_holding_max_days():
    """spike_precursor_inverse 모든 ParamSet의 holding_max_days=1."""
    for ps in expand_grid_spike_precursor_inverse():
        assert ps.holding_max_days == 1, (
            f"holding_max_days={ps.holding_max_days} (기대 1)"
        )


def test_spike_precursor_inverse_no_overlap_with_normal():
    """inverse 그리드와 normal 그리드의 hash 교집합이 없어야 함 (독립 탐색 공간)."""
    normal_hashes = {ps.config_hash() for ps in expand_grid_spike_precursor()}
    inverse_hashes = {ps.config_hash() for ps in expand_grid_spike_precursor_inverse()}
    overlap = normal_hashes & inverse_hashes
    assert len(overlap) == 0, (
        f"normal/inverse 그리드 hash 중복 {len(overlap)}건 — 탐색 공간이 겹침"
    )


# ──────────────────────────────────────────────────────────────────────────────
# trend_starter 그리드 (4건)
# ──────────────────────────────────────────────────────────────────────────────

def test_trend_starter_grid_size():
    """trend_starter 그리드 크기 240 (v2 — ATR 기반 손익비 재설계).

    이론 합 270에서 ts_tp_atr_mult > ts_sl_atr_mult 제약으로
    sl=2.0, tp=2.0 조합(30셀)이 validate 실패로 제외 → 240셀.

    trail_trigger=0: (3sl×3tp-1invalid) × 1 × 1 × 3 × 2 =  48셀
    trail_trigger>0: (3sl×3tp-1invalid) × 2 × 2 × 3 × 2 = 192셀
    합계: 240셀 정확히.
    """
    grid = expand_grid_trend_starter()
    assert len(grid) == 240, (
        f"trend_starter grid 크기={len(grid)} (기대 240)"
    )


def test_trend_starter_grid_validates():
    """trend_starter 그리드 모든 ParamSet이 validate() 통과."""
    for ps in expand_grid_trend_starter():
        ps.validate()


def test_trend_starter_grid_unique():
    """trend_starter 그리드 ParamSet 중복 없음."""
    grid = expand_grid_trend_starter()
    hashes = [ps.config_hash() for ps in grid]
    assert len(set(hashes)) == len(hashes), (
        f"trend_starter 중복 {len(hashes) - len(set(hashes))}건"
    )


def test_trend_starter_no_overlap_with_spike_personas():
    """trend_starter 그리드 hash가 spike_precursor/inverse 그리드와 교집합 0."""
    ts_hashes = {ps.config_hash() for ps in expand_grid_trend_starter()}
    spike_normal_hashes = {ps.config_hash() for ps in expand_grid_spike_precursor()}
    spike_inverse_hashes = {ps.config_hash() for ps in expand_grid_spike_precursor_inverse()}
    overlap_normal = ts_hashes & spike_normal_hashes
    overlap_inverse = ts_hashes & spike_inverse_hashes
    assert len(overlap_normal) == 0, (
        f"trend_starter/spike_normal 그리드 hash 중복 {len(overlap_normal)}건"
    )
    assert len(overlap_inverse) == 0, (
        f"trend_starter/spike_inverse 그리드 hash 중복 {len(overlap_inverse)}건"
    )
