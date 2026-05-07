"""페르소나별 압축 ParamSet 그리드 정의 (Phase G1).

각 `expand_grid_*()` 함수는 해당 페르소나의 탐색 축을 열거하고,
유효한(validate() 통과) ParamSet 리스트를 반환한다.

목표 크기: 페르소나당 100~150셀, 4 페르소나 합 400~600셀.

보조 함수:
  _4_simplex_4()  — 균등 / value-tilt / momentum-tilt / quality-tilt (4개)
  _roe_pbr_weight_4() — 균등 / ROE-tilt / PBR-tilt / 성장-tilt (4개)

사용 예:
    from RoboTrader_template.multiverse.composable.personas._grid import (
        expand_grid_quant, expand_grid_long_term,
        expand_grid_swing, expand_grid_intraday,
    )
    grid = expand_grid_quant()   # ~144 ParamSet
"""
from __future__ import annotations

import logging
from dataclasses import replace

from RoboTrader_template.multiverse.composable.paramset import ParamSet

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 공통 baseline (4 페르소나가 공유하는 "안전한" 기본값)
# ──────────────────────────────────────────────────────────────────────────────

_BASELINE = ParamSet(
    # A: 팩터 가중치 (균등)
    w_value=0.25, w_quality=0.25, w_momentum=0.25, w_growth=0.25,
    # B: 팩터 유니버스
    factor_top_n=50,
    # C: 이동평균선
    ma_short=5, ma_mid=20, ma_long=60,
    ma_regime=200, ma_regime_filter_enabled=True, ma_alignment_mode="bullish_only",
    # D: 시그널 on/off (3개 True — 최소 2 만족)
    sig_trend_align=True, sig_pullback=True, sig_breakout=True,
    sig_volume=False, sig_flow=False, sig_bb_bounce=False, sig_macd=False,
    # E: 시그널 가중치
    sig_trend_weight=0.20, sig_pullback_weight=0.20, sig_breakout_weight=0.20,
    sig_volume_weight=0.10, sig_flow_weight=0.10,
    sig_bb_weight=0.10, sig_macd_weight=0.10,
    # F: 진입 스코어
    tech_score_threshold=0.5, final_score_factor_w=0.4,
    # G: 진입 거래량
    entry_vol_filter_enabled=True, entry_vol_min_ratio=1.5, entry_vol_ma_period=20,
    # H: 진입 캔들
    entry_candle_filter_enabled=False, entry_candle_body_ratio=0.3,
    entry_candle_upper_wick_max=0.5,
    entry_candle_type="any", entry_prev_candle_check="none",
    # I: 진입 일봉 추가
    entry_gap_filter="none", entry_close_position="none",
    entry_consecutive_down=0, entry_ma_distance_max=999,
    # J: 이평선 필터
    entry_above_ma_mid=False, entry_ma_cross="none", entry_ma_slope_check="none",
    # K: 전일 국내지수
    prev_kospi_return_filter="none",
    prev_kosdaq_return_filter="none",
    kospi_kosdaq_divergence="none",
    # L: 전일 해외지수
    prev_sp500_filter="none", prev_nasdaq_filter="none",
    prev_vix_filter="none", overnight_futures="none",
    # M: 지수 추세
    sp500_trend="none", global_risk_mode="none",
    # N: ATR 트레일링
    atr_period=14, atr_multiplier=2.0,
    # O: 하드 스톱
    hard_stop_pct=-0.07, portfolio_pause_pct=-0.03, portfolio_stop_pct=-0.05,
    # P: 시그널 청산
    exit_tech_score_threshold=0.3, exit_signal_count=2, exit_rsi_overbought=75,
    # Q: 청산 이평선
    exit_below_ma_mid=False, exit_ma_dead_cross="none",
    # R: 포지션 관리
    max_positions=7, max_weight_per_stock=0.25, sizing_method="equal",
    # S: 동적 손익비 (18개)
    dynamic_rr_enabled=False, initial_reward_atr_mult=2.0,
    vol_regime_adjustment="none", score_based_adjustment=False,
    breakeven_trigger=0.03, lock_step_1_trigger=0.07, lock_step_1_stop=0.02,
    lock_step_2_trigger=0.12, lock_step_2_stop=0.06,
    tech_score_target_adjust=False, volume_target_adjust=False,
    adx_trend_adjust=False, adx_exit_threshold=0,
    time_decay_enabled=False, time_decay_rate=0,
    partial_tp_enabled=False, partial_tp_trigger=0.07, partial_tp_ratio=0.5,
    # T: 리밸런싱 주기
    rebalance_frequency="weekly",
    # U: 보유기간 상한
    holding_max_days=20,
)


# ──────────────────────────────────────────────────────────────────────────────
# 보조: 4-simplex 가중치 조합
# ──────────────────────────────────────────────────────────────────────────────

def _4_simplex_4() -> list[tuple[float, float, float, float]]:
    """(w_value, w_quality, w_momentum, w_growth) 4개 조합 (합=1.0).

    - 균등:          (0.25, 0.25, 0.25, 0.25)
    - value-tilt:    (0.40, 0.20, 0.20, 0.20)
    - momentum-tilt: (0.20, 0.20, 0.40, 0.20)
    - quality-tilt:  (0.20, 0.40, 0.20, 0.20)
    """
    return [
        (0.25, 0.25, 0.25, 0.25),
        (0.40, 0.20, 0.20, 0.20),
        (0.20, 0.20, 0.40, 0.20),
        (0.20, 0.40, 0.20, 0.20),
    ]


def _roe_pbr_weight_4() -> list[tuple[float, float, float, float]]:
    """long_term용 (w_value, w_quality, w_momentum, w_growth) 4개 조합 (합=1.0).

    - 균등:       (0.25, 0.25, 0.25, 0.25)
    - ROE-tilt:   (0.20, 0.40, 0.20, 0.20)  — quality=ROE 강조
    - PBR-tilt:   (0.40, 0.20, 0.20, 0.20)  — value=1/PBR 강조
    - 성장-tilt:  (0.20, 0.20, 0.20, 0.40)  — growth 강조
    """
    return [
        (0.25, 0.25, 0.25, 0.25),
        (0.20, 0.40, 0.20, 0.20),
        (0.40, 0.20, 0.20, 0.20),
        (0.20, 0.20, 0.20, 0.40),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _try_build(**overrides) -> ParamSet | None:
    """baseline에 overrides를 적용한 ParamSet을 생성하고 validate() 통과 시 반환."""
    try:
        ps = replace(_BASELINE, **overrides)
        ps.validate()
        return ps
    except (ValueError, TypeError) as exc:
        logger.debug("ParamSet validate 실패 (스킵): %s | overrides=%s", exc, overrides)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# quant 그리드 (~144셀)
# ──────────────────────────────────────────────────────────────────────────────

def expand_grid_quant() -> list[ParamSet]:
    """quant 페르소나 압축 그리드.

    축:
      factor_top_n          : {30, 50, 100}       — 3
      tech_score_threshold  : {0.3, 0.5, 0.7}     — 3
      (w_value, w_quality, w_momentum, w_growth)  : 4-simplex 4개 — 4
      rebalance_frequency   : {weekly, monthly}   — 2
      holding_max_days      : {20, 60}             — 2

    이론 합: 3×3×4×2×2 = 144셀 (validate 실패 없으므로 ~144)
    """
    result: list[ParamSet] = []

    for factor_top_n in [30, 50, 100]:
        for tech_thresh in [0.3, 0.5, 0.7]:
            for w_v, w_q, w_m, w_g in _4_simplex_4():
                for rebalance_freq in ["weekly", "monthly"]:
                    for holding_max in [20, 60]:
                        ps = _try_build(
                            factor_top_n=factor_top_n,
                            tech_score_threshold=tech_thresh,
                            w_value=w_v,
                            w_quality=w_q,
                            w_momentum=w_m,
                            w_growth=w_g,
                            rebalance_frequency=rebalance_freq,
                            holding_max_days=holding_max,
                        )
                        if ps is not None:
                            result.append(ps)

    logger.info("expand_grid_quant: %d ParamSet 생성", len(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# long_term 그리드 (~144셀)
# ──────────────────────────────────────────────────────────────────────────────

def expand_grid_long_term() -> list[ParamSet]:
    """long_term 페르소나 압축 그리드.

    축:
      holding_max_days      : {None, 60, 120}       — 3
      rebalance_frequency   : {monthly, biweekly}   — 2
      tech_score_threshold  : {0.4, 0.5, 0.6}       — 3
      max_weight_per_stock  : {0.20, 0.25, 0.30}    — 3
      (w_value, w_quality, w_momentum, w_growth)    : ROE/PBR weight 4개 — 4

    이론 합: 3×2×3×3×4 = 216 → holding 2개(None,60)로 압축 → 2×2×3×3×4 = 144
    """
    result: list[ParamSet] = []

    for holding_max in [None, 60]:
        for rebalance_freq in ["monthly", "biweekly"]:
            for tech_thresh in [0.4, 0.5, 0.6]:
                for max_w in [0.20, 0.25, 0.30]:
                    for w_v, w_q, w_m, w_g in _roe_pbr_weight_4():
                        ps = _try_build(
                            holding_max_days=holding_max,
                            rebalance_frequency=rebalance_freq,
                            tech_score_threshold=tech_thresh,
                            max_weight_per_stock=max_w,
                            w_value=w_v,
                            w_quality=w_q,
                            w_momentum=w_m,
                            w_growth=w_g,
                        )
                        if ps is not None:
                            result.append(ps)

    logger.info("expand_grid_long_term: %d ParamSet 생성", len(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# swing 그리드 (~108셀)
# ──────────────────────────────────────────────────────────────────────────────

def expand_grid_swing() -> list[ParamSet]:
    """swing 페르소나 압축 그리드.

    5/2 거래 0건 문제 해결을 위해 tech_score_threshold를 기존 0.4→0.2/0.3으로 완화.

    축:
      tech_score_threshold  : {0.2, 0.3}        — 2  (완화 — 기존 0.4보다 낮춤)
      entry_vol_min_ratio   : {1.0, 1.2, 1.5}   — 3
      atr_multiplier        : {2.0, 3.0, 5.0}   — 3  (ATR exit 변형)
      holding_max_days      : {5, 10, 15}        — 3
      rebalance_frequency   : {daily, weekly}    — 2

    이론 합: 2×3×3×3×2 = 108셀
    """
    result: list[ParamSet] = []

    for tech_thresh in [0.2, 0.3]:
        for vol_min in [1.0, 1.2, 1.5]:
            for atr_mult in [2.0, 3.0, 5.0]:
                for holding_max in [5, 10, 15]:
                    for rebalance_freq in ["daily", "weekly"]:
                        ps = _try_build(
                            tech_score_threshold=tech_thresh,
                            entry_vol_filter_enabled=True,
                            entry_vol_min_ratio=vol_min,
                            atr_multiplier=atr_mult,
                            holding_max_days=holding_max,
                            rebalance_frequency=rebalance_freq,
                        )
                        if ps is not None:
                            result.append(ps)

    logger.info("expand_grid_swing: %d ParamSet 생성", len(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# intraday 그리드 (~144셀)
# ──────────────────────────────────────────────────────────────────────────────

def expand_grid_intraday() -> list[ParamSet]:
    """intraday 페르소나 압축 그리드.

    DSR 미통과 원인(거래비용 > 수익) 대응: 보수 진입 + 빠른 손절.
    intraday는 holding_max_days를 paramset에서 지정해도 내부 로직이 1일 강제이므로
    holding_max_days 탐색은 페르소나 동작 다양성보다 백테스트 엔진 레벨 다양성을 위해 포함.

    축:
      holding_max_days      : {1, 3}                 — 2
      entry_candle_body_ratio  : {0.3, 0.5, 0.7}     — 3  (진입 캔들 강도)
      hard_stop_pct         : {-0.005, -0.01, -0.015} — 3  (빠른 손절)
      exit_rsi_overbought   : {70, 75, 80, 85}        — 4  (익절 타이밍)
      entry_vol_min_ratio   : {1.5, 2.0}              — 2

    이론 합: 2×3×3×4×2 = 144셀
    """
    result: list[ParamSet] = []

    for holding_max in [1, 3]:
        for candle_body in [0.3, 0.5, 0.7]:
            for stop_pct in [-0.005, -0.01, -0.015]:
                for rsi_ob in [70, 75, 80, 85]:
                    for vol_min in [1.5, 2.0]:
                        ps = _try_build(
                            holding_max_days=holding_max,
                            entry_candle_filter_enabled=True,
                            entry_candle_body_ratio=candle_body,
                            hard_stop_pct=stop_pct,
                            exit_rsi_overbought=rsi_ob,
                            entry_vol_filter_enabled=True,
                            entry_vol_min_ratio=vol_min,
                            rebalance_frequency="daily",
                        )
                        if ps is not None:
                            result.append(ps)

    logger.info("expand_grid_intraday: %d ParamSet 생성", len(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# spike_precursor 그리드 (216셀)
# ──────────────────────────────────────────────────────────────────────────────

def expand_grid_spike_precursor() -> list[ParamSet]:
    """spike_precursor 압축 그리드.

    축:
      spike_vol_z_thresh:   {1.0, 1.5, 2.0, 2.5}        — 4
      spike_atr_max:        {0.02, 0.03, 0.04}           — 3
      spike_box_max:        {0.05, 0.08, 0.12}           — 3
      spike_vol_trend_min:  {1.2, 1.5, 2.0}              — 3
      spike_match_min:      {2, 3}                        — 2

    이론 합: 4×3×3×3×2 = 216셀
    PoC 100셀 슬라이싱은 호출측 책임.
    """
    result: list[ParamSet] = []

    for vol_z in [1.0, 1.5, 2.0, 2.5]:
        for atr_max in [0.02, 0.03, 0.04]:
            for box_max in [0.05, 0.08, 0.12]:
                for vol_trend_min in [1.2, 1.5, 2.0]:
                    for match_min in [2, 3]:
                        ps = _try_build(
                            holding_max_days=1,
                            rebalance_frequency="daily",
                            spike_vol_z_thresh=vol_z,
                            spike_atr_max=atr_max,
                            spike_box_max=box_max,
                            spike_vol_trend_min=vol_trend_min,
                            spike_match_min=match_min,
                        )
                        if ps is not None:
                            result.append(ps)

    logger.info("expand_grid_spike_precursor: %d ParamSet 생성", len(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# spike_precursor_inverse 그리드 (216셀)
# ──────────────────────────────────────────────────────────────────────────────

def expand_grid_spike_precursor_inverse() -> list[ParamSet]:
    """spike_precursor 반전 가설 그리드.

    가설: 원본 그리드(고점·고거래량 진입)가 100셀 전손 → 진짜 선행 시그널은
    반대 — 거래량 침체·MA20 아래·좁은 박스권에서 깨어나기 직전 종목.

    F1: spike_vol_z_thresh → 값의 의미 반전 (inverse 페르소나 SignalGen이 <= 비교)
        {-1.0, -0.5, 0.0, 0.5} (거래량 침체/평소 수준)
    F2: spike_ma20_dist_min / spike_ma20_dist_max → 음의 이격 범위
        min={-0.10, -0.08, -0.05}  max={-0.02} (MA20 아래)
    F3: spike_atr_max → 더 낮은 임계값 (매우 낮은 변동성)
        {0.015, 0.02, 0.025}
    F4: spike_box_max → 더 좁은 박스 임계값
        {0.03, 0.05, 0.07}
    F5: spike_vol_trend_min → 값의 의미 반전 (inverse SignalGen이 <= 비교)
        {0.6, 0.8, 1.0} (거래량 감소 추세)
    spike_match_min: {2, 3}

    이론 합: 4×3×3×3×3×2 = 648셀 (F2 ma20 범위 3쌍, F5 vol_trend 3개)
    PoC 100셀 슬라이싱은 호출측 책임.

    중요: inverse 페르소나(build_spike_precursor_inverse_strategy)는
    spike_vol_z_thresh를 <= 로, spike_vol_trend_min을 <= 로 비교한다.
    ParamSet hash는 원본과 다른 값이므로 충돌 없음.
    """
    result: list[ParamSet] = []

    # F2: (min, max) 쌍 — 음의 이격 범위
    ma20_ranges = [
        (-0.10, -0.02),
        (-0.08, -0.02),
        (-0.05, -0.02),
    ]

    for vol_z in [-1.0, -0.5, 0.0, 0.5]:          # F1 (inverse: <= 비교)
        for ma20_min, ma20_max in ma20_ranges:      # F2 (범위 그대로, 음수 영역)
            for atr_max in [0.015, 0.02, 0.025]:   # F3 (더 낮은 임계값)
                for box_max in [0.03, 0.05, 0.07]: # F4 (더 좁은 박스)
                    for vol_trend in [0.6, 0.8, 1.0]:  # F5 (inverse: <= 비교)
                        for match_min in [2, 3]:
                            ps = _try_build(
                                holding_max_days=1,
                                rebalance_frequency="daily",
                                spike_vol_z_thresh=vol_z,
                                spike_ma20_dist_min=ma20_min,
                                spike_ma20_dist_max=ma20_max,
                                spike_atr_max=atr_max,
                                spike_box_max=box_max,
                                spike_vol_trend_min=vol_trend,
                                spike_match_min=match_min,
                            )
                            if ps is not None:
                                result.append(ps)

    logger.info("expand_grid_spike_precursor_inverse: %d ParamSet 생성", len(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# trend_starter 그리드 v2 (270셀)
# ──────────────────────────────────────────────────────────────────────────────

def expand_grid_trend_starter() -> list[ParamSet]:
    """trend_starter 페르소나 압축 그리드 v2 — ATR 기반 손익비 재설계.

    데이터 분석(2023~2026 4년) 결과 기반:
      F3 atr_ratio>=0.06 AND F1 vol_zscore_20>=1.5 → 양성률 11.76% (3.74x lift).

    진입 필터 (고정, 데이터 분석 최적값):
      ts_atr_min  = 0.06
      ts_volz_min = 1.5
      ts_box_min  = 0.20

    그리드 축:
      ts_sl_atr_mult:       {1.0, 1.5, 2.0}     — 3
      ts_tp_atr_mult:       {2.0, 3.0, 4.0}     — 3
      ts_trail_trigger_atr: {0, 1.5, 2.0}        — 3 (0=트레일링 비활성)
      ts_trail_offset_atr:  {0.5, 1.0}           — 2 (trigger=0이면 0.5만 사용)
      ts_hold_days:         {2, 3, 5}            — 3
      max_positions:        {3, 5}               — 2

    유효 셀 계산 (ts_tp_atr_mult > ts_sl_atr_mult 제약 적용):
      유효 (sl, tp) 조합: 8쌍 (sl=2.0, tp=2.0 제외)
      trail_trigger=0:  8 × 1 × 1 × 3 × 2 =  48셀 (offset 무의미 → 0.5 고정)
      trail_trigger>0:  8 × 2 × 2 × 3 × 2 = 192셀
      합계: 240셀
    """
    result: list[ParamSet] = []

    # 진입 필터 (고정)
    atr_min = 0.06
    volz_min = 1.5
    box_min = 0.20

    for sl_mult in [1.0, 1.5, 2.0]:
        for tp_mult in [2.0, 3.0, 4.0]:
            for trail_trigger in [0.0, 1.5, 2.0]:
                # trail_trigger=0 이면 offset 탐색 불필요 (0.5 고정)
                offsets = [0.5] if trail_trigger == 0.0 else [0.5, 1.0]
                for trail_offset in offsets:
                    for hold_days in [2, 3, 5]:
                        for max_pos in [3, 5]:
                            ps = _try_build(
                                holding_max_days=hold_days,
                                rebalance_frequency="daily",
                                max_weight_per_stock=0.20,
                                max_positions=max_pos,
                                ts_atr_min=atr_min,
                                ts_volz_min=volz_min,
                                ts_box_min=box_min,
                                ts_sl_atr_mult=sl_mult,
                                ts_tp_atr_mult=tp_mult,
                                ts_trail_trigger_atr=trail_trigger,
                                ts_trail_offset_atr=trail_offset,
                                ts_hold_days=hold_days,
                            )
                            if ps is not None:
                                result.append(ps)

    logger.info("expand_grid_trend_starter: %d ParamSet 생성", len(result))
    return result
