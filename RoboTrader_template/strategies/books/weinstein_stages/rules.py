"""Weinstein Stage Analysis — 주봉 룰 집합.

모든 룰은 주봉 DataFrame을 입력으로 받는다.
(run_weinstein_stages.py 단에서 일봉→주봉 변환 후 전달)

헬퍼:
- compute_ma30w_slope     : MA30(주) 4주 기울기 (비율)
- compute_mansfield_rs   : Mansfield RS (RP/SMA(RP,n)-1)*100
- stage_classifier       : 1/2/3/4 라벨 시리즈

룰:
- rule_stage2_initial_breakout     : Stage 1→2 돌파 (confidence 72)
- rule_stage2_continuation_pullback: Stage 2 MA30 되돌림 재진입 (confidence 68)
- rule_ma30w_bounce                : Stage 2 MA30 단순 반등 (confidence 60)

상수:
- ALL_RULES
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------

def compute_ma30w_slope(weekly_close: pd.Series, lookback: int = 4) -> pd.Series:
    """MA30(주) 4주 기울기 비율 시리즈를 반환한다.

    정의: (MA30(t) - MA30(t-lookback)) / MA30(t-lookback)
    임계값: >+0.001 상승 / |slope|<=0.001 평탄 / <-0.001 하락
    추후 데이터 누적 후 임계값 재검토.

    Args:
        weekly_close: 주봉 종가 시리즈 (index는 임의).
        lookback: 기울기 계산 기간 (주). 기본 4주.

    Returns:
        같은 index의 slope 시리즈. NaN = 데이터 부족.
    """
    ma30 = weekly_close.rolling(30).mean()
    slope = (ma30 - ma30.shift(lookback)) / ma30.shift(lookback)
    return slope


def compute_mansfield_rs(
    stock_weekly_close: pd.Series,
    market_weekly_close: pd.Series,
    n: int = 26,
) -> pd.Series:
    """Mansfield Relative Strength 시리즈를 반환한다.

    식 (stageanalysis.net 원본):
        RP(t)  = (stock(t) / market(t)) * 100
        MRS(t) = (RP(t) / SMA(RP, n) - 1) * 100

    n = 26 (주봉). 원본 52주 → 데이터 32주 한계로 축소.
    추후 데이터 1년+ 누적 후 n=52 복귀 검토.

    Args:
        stock_weekly_close : 종목 주봉 종가.
        market_weekly_close: 시장(universe 동일가중) 주봉 종가. 같은 index.
        n                  : Mansfield RS SMA 기간 (주봉). 기본 26.

    Returns:
        Mansfield RS 시리즈. NaN = warmup 부족.
    """
    # 인덱스 정렬 후 시장과 종목을 맞춤
    aligned = pd.concat(
        [stock_weekly_close.rename("stock"), market_weekly_close.rename("market")],
        axis=1,
    ).dropna()
    if aligned.empty:
        return pd.Series(dtype=float, name="mansfield_rs")

    rp = (aligned["stock"] / aligned["market"]) * 100.0
    sma_rp = rp.rolling(n).mean()
    mrs = (rp / sma_rp - 1.0) * 100.0
    mrs.name = "mansfield_rs"
    return mrs


def stage_classifier(
    price: pd.Series,
    ma30w: pd.Series,
    ma30w_slope: pd.Series,
    mansfield_rs: pd.Series,
) -> pd.Series:
    """주봉 기준 Stage 1/2/3/4 라벨 시리즈를 반환한다.

    분류 기준 (설계서 §2a):
    - Stage 2 (Advancing) : price > ma30w AND slope > +0.001
    - Stage 4 (Declining) : price < ma30w AND slope < -0.001
    - Stage 1 (Basing)    : |slope|<=0.001, 직전이 Stage 4이거나 가격이 ma30w 아래/혼재
    - Stage 3 (Top)       : |slope|<=0.001, 직전이 Stage 2이거나 가격이 ma30w 위/혼재

    Stage 1/3 구분: 직전 4주 평균 stage로 판단 (직전 Stage 4 → 1, 직전 Stage 2 → 3).
    NaN = 데이터 부족.

    추후 데이터 누적 후 임계값 0.001 재검토.
    """
    # 공통 index로 정렬
    combined = pd.concat([
        price.rename("price"),
        ma30w.rename("ma30w"),
        ma30w_slope.rename("slope"),
        mansfield_rs.rename("mrs"),
    ], axis=1)

    n = len(combined)
    labels = pd.Series(np.nan, index=combined.index, dtype=float)

    SLOPE_THRESHOLD = 0.001  # 추후 데이터 누적 후 재검토

    for i in range(n):
        row = combined.iloc[i]
        if any(pd.isna([row["price"], row["ma30w"], row["slope"]])):
            continue

        p = float(row["price"])
        ma = float(row["ma30w"])
        sl = float(row["slope"])

        if p > ma and sl > SLOPE_THRESHOLD:
            labels.iloc[i] = 2
        elif p < ma and sl < -SLOPE_THRESHOLD:
            labels.iloc[i] = 4
        else:
            # Stage 1 vs 3: 직전 4주 이력으로 구분
            lookback = 4
            if i >= lookback:
                prev_labels = labels.iloc[max(0, i - lookback): i].dropna()
                if len(prev_labels) > 0:
                    prev_mean = float(prev_labels.mean())
                    if prev_mean >= 3.0:
                        labels.iloc[i] = 3  # 직전에 Stage 3/4 → 3
                    elif prev_mean <= 2.0:
                        labels.iloc[i] = 1  # 직전에 Stage 1/2 → 1
                    else:
                        labels.iloc[i] = 1  # 기본값
                else:
                    labels.iloc[i] = 1
            else:
                labels.iloc[i] = 1

    return labels.astype("Int64")


# ---------------------------------------------------------------------------
# 룰 함수
# ---------------------------------------------------------------------------

@dataclass
class rule_stage2_initial_breakout(Rule):
    """Stage 1→2 전환 돌파 셋업 (설계서 §2b).

    조건:
    1. 직전 주 stage == 1 AND 현재 주 stage == 2
    2. weekly_close[-1] > ma30w[-1]
    3. weekly_close[-1] > rolling_max(weekly_close, 16 주).iloc[-2]  — 박스 저항선
    4. weekly_volume[-1] > rolling_mean(weekly_volume, 4).iloc[-2] * 1.5
    5. mansfield_rs[-1] >= 0

    박스 기간 16주: 설계서 확정값. 추후 데이터 누적 후 재검토.
    거래량 배수 1.5: 설계서 확정값. 추후 재검토.
    no-lookahead: 박스 저항선·평균 거래량은 .iloc[-2] (당주 제외 직전까지) 기준.
    """

    name: str = "stage2_initial_breakout"
    box_period: int = 16          # 박스 저항선 기간(주). 추후 데이터 누적 후 재검토.
    volume_multiplier: float = 1.5  # 돌파 거래량 배수. 추후 재검토.
    volume_avg_period: int = 4    # 거래량 평균 기간(주).

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        min_bars = self.box_period + self.volume_avg_period + 2
        if len(df) < min_bars:
            return RuleResult(triggered=False)

        close = df["close"].astype(float)
        volume = df["volume"].astype(float)

        # MA30W, 기울기, Mansfield RS는 ctx에서 주입
        ma30w_series: pd.Series = ctx.get("ma30w_series")
        slope_series: pd.Series = ctx.get("slope_series")
        mrs_series: pd.Series = ctx.get("mrs_series")
        stage_series: pd.Series = ctx.get("stage_series")

        if any(s is None for s in [ma30w_series, slope_series, mrs_series, stage_series]):
            return RuleResult(triggered=False)

        if len(stage_series) < 2:
            return RuleResult(triggered=False)

        # 현재(t)/직전(t-1) 값
        cur_close = float(close.iloc[-1])
        cur_ma30w = float(ma30w_series.iloc[-1]) if not pd.isna(ma30w_series.iloc[-1]) else None
        cur_mrs = float(mrs_series.iloc[-1]) if not pd.isna(mrs_series.iloc[-1]) else None
        cur_stage = int(stage_series.iloc[-1]) if not pd.isna(stage_series.iloc[-1]) else None
        prev_stage = int(stage_series.iloc[-2]) if not pd.isna(stage_series.iloc[-2]) else None

        if any(v is None for v in [cur_ma30w, cur_mrs, cur_stage, prev_stage]):
            return RuleResult(triggered=False)

        # 조건 1: Stage 1 → 2 전환
        if not (prev_stage == 1 and cur_stage == 2):
            return RuleResult(triggered=False)

        # 조건 2: 가격 > MA30W
        if cur_close <= cur_ma30w:
            return RuleResult(triggered=False)

        # 조건 3: 박스 저항선 돌파 (no-lookahead: iloc[-2] 기준)
        if len(close) < self.box_period + 1:
            return RuleResult(triggered=False)
        box_high = float(close.iloc[-(self.box_period + 1):-1].max())
        if cur_close <= box_high:
            return RuleResult(triggered=False)

        # 조건 4: 거래량 돌파 (no-lookahead: iloc[-2] 기준)
        if len(volume) < self.volume_avg_period + 1:
            return RuleResult(triggered=False)
        avg_vol = float(volume.iloc[-(self.volume_avg_period + 1):-1].mean())
        if avg_vol <= 0 or float(volume.iloc[-1]) <= avg_vol * self.volume_multiplier:
            return RuleResult(triggered=False)

        # 조건 5: Mansfield RS >= 0
        if cur_mrs < 0:
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True,
            side="buy",
            confidence=72.0,
            reasons=[
                f"stage2_initial_breakout close={cur_close:.0f} ma30w={cur_ma30w:.0f} "
                f"box_high={box_high:.0f} mrs={cur_mrs:.2f}"
            ],
            metadata={
                "stage": cur_stage,
                "prev_stage": prev_stage,
                "mansfield_rs": cur_mrs,
                "ma30w": cur_ma30w,
            },
        )


@dataclass
class rule_stage2_continuation_pullback(Rule):
    """Stage 2 중 MA30W 5% 이내 되돌림 후 회복 셋업 (설계서 §2b).

    조건:
    1. 현재 Stage 2 AND 직전 4주 모두 Stage 2
    2. 지난 4주 중 한 번이라도 MA30W 5% 이내 접근
    3. weekly_close[-1] > max(weekly_high[-5:-1]) — 직전 4주 swing high 재돌파
    4. weekly_volume[-1] > rolling_mean(weekly_volume, 4).iloc[-2] * 1.0
    5. Mansfield RS >= 0

    Pullback 범위 5%: 설계서 확정값. 추후 재검토.
    confidence: 68 (initial_breakout 72보다 낮음 — 재진입 셋업 보수 추정).
    """

    name: str = "stage2_continuation_pullback"
    stage2_lookback: int = 4      # Stage 2 연속 확인 기간(주).
    pullback_pct: float = 0.05    # MA30W 이내 접근 허용 범위. 추후 재검토.
    volume_avg_period: int = 4

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        min_bars = self.stage2_lookback + self.volume_avg_period + 2
        if len(df) < min_bars:
            return RuleResult(triggered=False)

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        volume = df["volume"].astype(float)

        ma30w_series: pd.Series = ctx.get("ma30w_series")
        mrs_series: pd.Series = ctx.get("mrs_series")
        stage_series: pd.Series = ctx.get("stage_series")

        if any(s is None for s in [ma30w_series, mrs_series, stage_series]):
            return RuleResult(triggered=False)

        n_needed = self.stage2_lookback + 1
        if len(stage_series) < n_needed:
            return RuleResult(triggered=False)

        # 조건 1: 현재 + 직전 4주 모두 Stage 2
        recent_stages = stage_series.iloc[-n_needed:]
        if any(pd.isna(recent_stages)):
            return RuleResult(triggered=False)
        if not all(int(s) == 2 for s in recent_stages):
            return RuleResult(triggered=False)

        cur_close = float(close.iloc[-1])
        cur_mrs = float(mrs_series.iloc[-1]) if not pd.isna(mrs_series.iloc[-1]) else None
        if cur_mrs is None:
            return RuleResult(triggered=False)

        # 조건 2: 지난 4주 중 MA30W 5% 이내 접근 여부
        recent_close = close.iloc[-n_needed:]
        recent_ma30w = ma30w_series.iloc[-n_needed:]
        valid_mask = ~pd.isna(recent_ma30w)
        if not valid_mask.any():
            return RuleResult(triggered=False)

        ratios = (recent_close[valid_mask].values - recent_ma30w[valid_mask].values) / recent_ma30w[valid_mask].values
        pullback_occurred = bool(np.any(ratios < self.pullback_pct))
        if not pullback_occurred:
            return RuleResult(triggered=False)

        # 조건 3: 직전 4주 swing high 재돌파 (no-lookahead: iloc[-5:-1])
        if len(high) < 5:
            return RuleResult(triggered=False)
        swing_high = float(high.iloc[-5:-1].max())
        if cur_close <= swing_high:
            return RuleResult(triggered=False)

        # 조건 4: 거래량 기준치 이상 (no-lookahead: iloc[-2] 기준)
        if len(volume) < self.volume_avg_period + 1:
            return RuleResult(triggered=False)
        avg_vol = float(volume.iloc[-(self.volume_avg_period + 1):-1].mean())
        if avg_vol <= 0 or float(volume.iloc[-1]) < avg_vol * 1.0:
            return RuleResult(triggered=False)

        # 조건 5: Mansfield RS >= 0
        if cur_mrs < 0:
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True,
            side="buy",
            confidence=68.0,
            reasons=[
                f"stage2_continuation_pullback close={cur_close:.0f} "
                f"swing_high={swing_high:.0f} mrs={cur_mrs:.2f}"
            ],
            metadata={"mansfield_rs": cur_mrs, "swing_high": swing_high},
        )


@dataclass
class rule_ma30w_bounce(Rule):
    """Stage 2 중 MA30W 단순 반등 셋업 (설계서 §2b, 셋업 #6).

    조건:
    1. 현재 Stage 2
    2. weekly_low[-1] <= ma30w[-1] * 1.03  AND  weekly_close[-1] > weekly_open[-1] (양봉)
    3. Mansfield RS >= 0

    swing high 조건 없음 — pullback의 완화 버전.
    confidence: 60 (가장 느슨한 셋업).
    MA 접근 허용 범위 3%: 추후 데이터 누적 후 재검토.
    """

    name: str = "ma30w_bounce"
    ma_touch_pct: float = 1.03    # MA30W × 이 배율 이내 저점 진입 허용. 추후 재검토.

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 32:
            return RuleResult(triggered=False)

        close = df["close"].astype(float)
        low = df["low"].astype(float)
        open_ = df["open"].astype(float)

        ma30w_series: pd.Series = ctx.get("ma30w_series")
        mrs_series: pd.Series = ctx.get("mrs_series")
        stage_series: pd.Series = ctx.get("stage_series")

        if any(s is None for s in [ma30w_series, mrs_series, stage_series]):
            return RuleResult(triggered=False)

        if len(stage_series) < 1:
            return RuleResult(triggered=False)

        cur_stage_val = stage_series.iloc[-1]
        if pd.isna(cur_stage_val) or int(cur_stage_val) != 2:
            return RuleResult(triggered=False)

        cur_close = float(close.iloc[-1])
        cur_open = float(open_.iloc[-1])
        cur_low = float(low.iloc[-1])
        cur_ma30w = float(ma30w_series.iloc[-1]) if not pd.isna(ma30w_series.iloc[-1]) else None
        cur_mrs = float(mrs_series.iloc[-1]) if not pd.isna(mrs_series.iloc[-1]) else None

        if cur_ma30w is None or cur_mrs is None:
            return RuleResult(triggered=False)

        # 조건 2: 저점이 MA30W 3% 이내 + 양봉
        if cur_low > cur_ma30w * self.ma_touch_pct:
            return RuleResult(triggered=False)
        if cur_close <= cur_open:
            return RuleResult(triggered=False)

        # 조건 3: Mansfield RS >= 0
        if cur_mrs < 0:
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True,
            side="buy",
            confidence=60.0,
            reasons=[
                f"ma30w_bounce close={cur_close:.0f} low={cur_low:.0f} "
                f"ma30w={cur_ma30w:.0f} mrs={cur_mrs:.2f}"
            ],
            metadata={"mansfield_rs": cur_mrs, "ma30w": cur_ma30w},
        )


# ---------------------------------------------------------------------------
# T4: ALL_RULES
# ---------------------------------------------------------------------------

ALL_RULES: List = [
    rule_stage2_initial_breakout,
    rule_stage2_continuation_pullback,
    rule_ma30w_bounce,
]
