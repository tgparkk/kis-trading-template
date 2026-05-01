"""84변수 ParamSet — Composable 전략 파라미터 직렬화.

변수 그룹 A~U (84개 필드).
frozen dataclass — 불변 보장, config_hash 안정성.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from typing import Literal, Optional


@dataclass(frozen=True)
class ParamSet:
    """Composable 전략의 84변수 파라미터셋.

    그룹 A~U 순서로 정의. validate() 호출로 제약 검증.
    """

    # ------------------------------------------------------------------ #
    # A. 팩터 가중치 (4, 합=1.0)
    # ------------------------------------------------------------------ #
    w_value: float
    w_quality: float
    w_momentum: float
    w_growth: float

    # ------------------------------------------------------------------ #
    # B. 팩터 유니버스 (1)
    # ------------------------------------------------------------------ #
    factor_top_n: int  # {30, 50, 70, 100}

    # ------------------------------------------------------------------ #
    # C. 이동평균선 (6, ma_short < ma_mid < ma_long)
    # ------------------------------------------------------------------ #
    ma_short: int   # {3, 5, 10}
    ma_mid: int     # {10, 20, 30}
    ma_long: int    # {40, 60, 90, 120, 200}
    ma_regime: int  # {120, 200}
    ma_regime_filter_enabled: bool
    ma_alignment_mode: Literal["bullish_only", "any", "contrarian"]

    # ------------------------------------------------------------------ #
    # D. 시그널 on/off (7, 최소 2개 True)
    # ------------------------------------------------------------------ #
    sig_trend_align: bool
    sig_pullback: bool
    sig_breakout: bool
    sig_volume: bool
    sig_flow: bool
    sig_bb_bounce: bool
    sig_macd: bool

    # ------------------------------------------------------------------ #
    # E. 시그널 가중치 (7)
    # ------------------------------------------------------------------ #
    sig_trend_weight: float    # {0.05, 0.10, 0.15, 0.20, 0.25}
    sig_pullback_weight: float  # {0.05, 0.10, 0.15, 0.20, 0.25}
    sig_breakout_weight: float  # {0.05, 0.10, 0.15, 0.20, 0.25}
    sig_volume_weight: float    # {0.05, 0.10, 0.15, 0.20, 0.25}
    sig_flow_weight: float      # {0.05, 0.10, 0.15, 0.20, 0.25}
    sig_bb_weight: float        # {0.05, 0.10, 0.15, 0.20}
    sig_macd_weight: float      # {0.05, 0.10, 0.15}

    # ------------------------------------------------------------------ #
    # F. 진입 스코어 (2)
    # ------------------------------------------------------------------ #
    tech_score_threshold: float    # {0.3, 0.4, 0.5, 0.6, 0.7}
    final_score_factor_w: float    # {0.2, 0.3, 0.4, 0.5, 0.6, 0.7}

    # ------------------------------------------------------------------ #
    # G. 진입 거래량 (3)
    # ------------------------------------------------------------------ #
    entry_vol_filter_enabled: bool
    entry_vol_min_ratio: float   # {1.0, 1.2, 1.5, 2.0}
    entry_vol_ma_period: int     # {10, 20}

    # ------------------------------------------------------------------ #
    # H. 진입 캔들 (5)
    # ------------------------------------------------------------------ #
    entry_candle_filter_enabled: bool
    entry_candle_body_ratio: float   # {0.0, 0.3, 0.5, 0.7}
    entry_candle_upper_wick_max: float  # {1.0, 0.5, 0.3}
    entry_candle_type: Literal["any", "bullish", "bullish_engulfing", "hammer", "morning_star"]
    entry_prev_candle_check: Literal["none", "bearish", "doji", "lower_shadow"]

    # ------------------------------------------------------------------ #
    # I. 진입 일봉 추가 (4)
    # ------------------------------------------------------------------ #
    entry_gap_filter: Literal["none", "gap_up", "no_gap_down"]
    entry_close_position: Literal["none", "upper_half", "upper_third"]
    entry_consecutive_down: int   # {0, 2, 3}
    entry_ma_distance_max: float  # {1.05, 1.10, 1.15, 1.20, 999}

    # ------------------------------------------------------------------ #
    # J. 이평선 필터 (3)
    # ------------------------------------------------------------------ #
    entry_above_ma_mid: bool
    entry_ma_cross: Literal["none", "short_cross_mid", "within_5days"]
    entry_ma_slope_check: Literal["none", "mid_rising", "long_rising"]

    # ------------------------------------------------------------------ #
    # K. 전일 국내지수 (3)
    # ------------------------------------------------------------------ #
    prev_kospi_return_filter: Literal["none", "positive_only", "not_crash_1pct", "not_crash_2pct"]
    prev_kosdaq_return_filter: Literal["none", "positive_only", "not_crash_1pct", "not_crash_2pct"]
    kospi_kosdaq_divergence: Literal["none", "same_direction", "kosdaq_stronger"]

    # ------------------------------------------------------------------ #
    # L. 전일 해외지수 (4)
    # ------------------------------------------------------------------ #
    prev_sp500_filter: Literal["none", "positive_only", "not_crash_1pct", "above_ma20"]
    prev_nasdaq_filter: Literal["none", "positive_only", "not_crash_1pct", "above_ma20"]
    prev_vix_filter: Literal["none", "below_20", "below_25", "below_30"]
    overnight_futures: Literal["none", "positive_only", "not_negative_1pct"]

    # ------------------------------------------------------------------ #
    # M. 지수 추세 (2)
    # ------------------------------------------------------------------ #
    sp500_trend: Literal["none", "above_ma50", "above_ma200"]
    global_risk_mode: Literal["none", "risk_on", "risk_off_avoid"]

    # ------------------------------------------------------------------ #
    # N. ATR 트레일링 (2)
    # ------------------------------------------------------------------ #
    atr_period: int        # {10, 14, 20}
    atr_multiplier: float  # {1.5, 2.0, 2.5, 3.0}

    # ------------------------------------------------------------------ #
    # O. 하드 스톱 (3, 음수 값)
    # ------------------------------------------------------------------ #
    hard_stop_pct: float         # {-0.05, -0.07, -0.10}
    portfolio_pause_pct: float   # {-0.02, -0.03}
    portfolio_stop_pct: float    # {-0.04, -0.05, -0.07}

    # ------------------------------------------------------------------ #
    # P. 시그널 청산 (3)
    # ------------------------------------------------------------------ #
    exit_tech_score_threshold: float  # {0.2, 0.3, 0.4}
    exit_signal_count: int            # {1, 2, 3}
    exit_rsi_overbought: int          # {70, 75, 80}

    # ------------------------------------------------------------------ #
    # Q. 청산 이평선 (2)
    # ------------------------------------------------------------------ #
    exit_below_ma_mid: bool
    exit_ma_dead_cross: Literal["none", "short_cross_mid_down", "mid_cross_long_down"]

    # ------------------------------------------------------------------ #
    # R. 포지션 관리 (3)
    # ------------------------------------------------------------------ #
    max_positions: int            # {5, 7, 10}
    max_weight_per_stock: float   # {0.20, 0.25, 0.30}
    sizing_method: Literal["equal", "score_proportional"]

    # ------------------------------------------------------------------ #
    # S. 동적 손익비 (18)
    # ------------------------------------------------------------------ #
    dynamic_rr_enabled: bool
    initial_reward_atr_mult: float  # {1.5, 2.0, 2.5, 3.0, 4.0}
    vol_regime_adjustment: Literal["none", "atr_pct_based", "vix_based"]
    score_based_adjustment: bool
    breakeven_trigger: float        # {0.02, 0.03, 0.05}
    lock_step_1_trigger: float      # {0.05, 0.07, 0.10}
    lock_step_1_stop: float         # {0.02, 0.03}
    lock_step_2_trigger: float      # {0.10, 0.12, 0.15}
    lock_step_2_stop: float         # {0.05, 0.06, 0.08}
    tech_score_target_adjust: bool
    volume_target_adjust: bool
    adx_trend_adjust: bool
    adx_exit_threshold: int         # {0, 15, 20}
    time_decay_enabled: bool
    time_decay_rate: float          # {0, 0.01, 0.02, 0.03}
    partial_tp_enabled: bool
    partial_tp_trigger: float       # {0.05, 0.07, 0.10}
    partial_tp_ratio: float         # {0.3, 0.5}

    # ------------------------------------------------------------------ #
    # T. 리밸런싱 주기 (1, 신규)
    # ------------------------------------------------------------------ #
    rebalance_frequency: Literal["daily", "weekly", "biweekly", "monthly"]

    # ------------------------------------------------------------------ #
    # U. 보유기간 상한 (1, 신규)
    # ------------------------------------------------------------------ #
    holding_max_days: Optional[int]  # None=무제한, {5, 10, 20, 60}

    # ------------------------------------------------------------------ #
    # 메서드
    # ------------------------------------------------------------------ #

    def validate(self) -> None:
        """제약 검증. 위반 시 ValueError raise.

        - A 팩터 가중치 합 = 1.0 (오차 ±0.01 허용)
        - D 시그널 on/off 최소 2개 True
        - C ma_short < ma_mid < ma_long
        """
        # A: 팩터 가중치 합
        w_sum = self.w_value + self.w_quality + self.w_momentum + self.w_growth
        if abs(w_sum - 1.0) > 0.01:
            raise ValueError(
                f"팩터 가중치 합이 1.0이 아닙니다: "
                f"w_value={self.w_value} + w_quality={self.w_quality} + "
                f"w_momentum={self.w_momentum} + w_growth={self.w_growth} = {w_sum:.4f}"
            )

        # D: 시그널 최소 2개 True
        sig_flags = [
            self.sig_trend_align,
            self.sig_pullback,
            self.sig_breakout,
            self.sig_volume,
            self.sig_flow,
            self.sig_bb_bounce,
            self.sig_macd,
        ]
        if sum(sig_flags) < 2:
            raise ValueError(
                f"시그널 on/off 중 최소 2개가 True여야 합니다 (현재 True: {sum(sig_flags)}개)"
            )

        # C: MA 순서
        if self.ma_short >= self.ma_mid:
            raise ValueError(
                f"ma_short({self.ma_short}) < ma_mid({self.ma_mid}) 조건 위반"
            )
        if self.ma_mid >= self.ma_long:
            raise ValueError(
                f"ma_mid({self.ma_mid}) < ma_long({self.ma_long}) 조건 위반"
            )

    def to_dict(self) -> dict:
        """asdict 호출, JSON 직렬화 가능 형태로 반환."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ParamSet":
        """dict → ParamSet 복원."""
        return cls(**d)

    def config_hash(self) -> str:
        """SHA256(json.dumps(to_dict, sort_keys=True))의 hex digest 16자리."""
        serialized = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    def paramset_id(self) -> str:
        """config_hash와 동일 (DB PK)."""
        return self.config_hash()
