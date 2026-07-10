"""
lib/signals/trend.py — 추세 기반 PIT-safe 시그널 (차트 패턴 컨셉 26)
======================================================================

카탈로그 출처: reports/10pct_strategy/phase5_signals/01_chart_patterns.md
컨셉 26: 일봉 정배열 (Golden MA Alignment)

PIT 강제 규칙:
- 모든 rolling MA는 T 기준 과거 데이터만 사용
- shift(-N) 절대 금지 (forward leak)
- 입력 df는 종목별 날짜 오름차순 정렬 전제

Stage 매핑:
- 정배열 점수 0~1: Stage A (유니버스 필터) + Stage B (진입 조건)
  - Stage A: score >= 0.6 (3/5 이상) 로 유니버스 사전 필터링
  - Stage B: score == 1.0 (완전 정배열) 로 진입 시그널

No Look-Ahead 검증:
- "마지막 N행을 잘라내도 직전 행까지의 결과가 동일" 원칙 적용
- rolling(window).mean()은 인과적(causal) — 미래 참조 없음
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# 카탈로그 표준 MA 기간 (컨셉 26: 5>20>60>120>240)
# 주의: 한국투자교육원 기준은 5>10>20>60>120 이나,
# 카탈로그 컨셉 26 명시값 5>20>60>120>240 을 표준으로 사용
_DEFAULT_MAS = [5, 20, 60, 120, 240]


def ma_alignment_score(
    prices: pd.DataFrame,
    mas: list[int] | None = None,
    group_col: str = "stock_code",
    close_col: str = "close",
) -> pd.Series:
    """일봉 이동평균 정배열 점수 — 컨셉 26 (Golden MA Alignment).

    정의 (카탈로그 컨셉 26):
        정배열 = MA 단기→장기 순으로 위에서 아래 배열.
        완전 정배열 (5개): MA5 > MA20 > MA60 > MA120 > MA240
        부분 정배열: 인접 MA 쌍 중 조건 만족 비율

    계산:
        인접 쌍 N-1개 중 (MA_short > MA_long)을 만족하는 쌍의 비율.
        mas=[5,20,60,120,240] → 쌍: (5>20), (20>60), (60>120), (120>240) = 4쌍
        score = 만족 쌍 수 / 전체 쌍 수  →  0.0 ~ 1.0

        score == 1.0: 완전 정배열 (모든 조건 충족)
        score == 0.0: 완전 역배열
        score == 0.75: 4쌍 중 3쌍 충족 (예: MA5>MA20, MA20>MA60, MA60>MA120 충족, MA120≤MA240)

    PIT 강제:
        rolling(ma_period).mean()은 T 기준 과거만 참조 — causal.
        종목 경계: groupby로 종목 간 누출 차단.
        초기 데이터 부족 (max(mas)일 미만): NaN 반환.

    Parameters
    ----------
    prices : pd.DataFrame
        종목 시계열 데이터. 날짜 오름차순 정렬 필수.
        ``group_col``, ``close_col`` 컬럼 필요.
    mas : list[int] | None
        정배열 검사할 MA 기간 목록 (오름차순). 기본값: [5, 20, 60, 120, 240].
        카탈로그 컨셉 26 표준.
        커스텀: [5, 20, 60] → 3개 MA, 2쌍 검사.
    group_col : str
        종목 구분 컬럼. 기본값 ``"stock_code"``.
    close_col : str
        종가 컬럼. 기본값 ``"close"``.

    Returns
    -------
    pd.Series
        prices.index와 동일한 index의 정배열 점수 시리즈 (0.0 ~ 1.0).
        max(mas)일치 데이터가 없는 초기 구간은 NaN.

    Stage 매핑:
        Stage A 필터: score >= 0.6 (3/5 이상 정배열 → 유니버스 포함)
        Stage B 시그널: score == 1.0 (완전 정배열 → 진입 조건)

    예시
    ----
    >>> import pandas as pd
    >>> from lib.signals.trend import ma_alignment_score
    >>> n = 300
    >>> prices = pd.DataFrame({
    ...     "stock_code": ["A"] * n,
    ...     "date": pd.date_range("2023-01-01", periods=n, freq="B"),
    ...     "close": [100 + i * 0.1 for i in range(n)],  # 완만한 상승
    ... })
    >>> score = ma_alignment_score(prices)
    >>> score.iloc[-1]  # 상승 추세이므로 1.0에 가까워야 함
    1.0
    """
    if mas is None:
        mas = _DEFAULT_MAS

    if len(mas) < 2:
        raise ValueError(
            f"ma_alignment_score: mas={mas} 에는 최소 2개 기간이 필요합니다."
        )

    mas_sorted = sorted(mas)  # 오름차순 보장
    n_pairs = len(mas_sorted) - 1  # 인접 쌍 수

    def _score_single(grp: pd.DataFrame) -> pd.Series:
        close = grp[close_col]
        n = len(close)

        # 각 MA 기간별 rolling mean 계산 (PIT: min_periods=ma_period 강제)
        ma_series = {}
        for ma_p in mas_sorted:
            ma_series[ma_p] = close.rolling(ma_p, min_periods=ma_p).mean()

        # 정배열 점수 계산: 인접 쌍별 비교
        # 초기 구간 (max MA 미만): NaN
        pair_checks = []
        for i in range(n_pairs):
            short_ma = mas_sorted[i]
            long_ma  = mas_sorted[i + 1]
            # MA_short > MA_long이면 1, 아니면 0
            pair_ok = (ma_series[short_ma] > ma_series[long_ma]).astype(float)
            # 어느 한쪽이 NaN이면 이 쌍도 NaN
            any_nan = ma_series[short_ma].isna() | ma_series[long_ma].isna()
            pair_ok[any_nan] = np.nan
            pair_checks.append(pair_ok)

        # 점수 = 충족 쌍 수 / 전체 쌍 수
        # NaN 엄격 전파: 어느 한 쌍이라도 NaN이면 전체 점수 NaN
        # (PIT 강제: 가장 긴 MA 데이터 미충족 시 점수 없음)
        stacked = pd.concat(pair_checks, axis=1)
        score = stacked.mean(axis=1, skipna=False)  # NaN 하나라도 → NaN

        return score

    if group_col in prices.columns:
        parts = []
        for _, grp in prices.groupby(group_col, sort=False):
            parts.append(_score_single(grp))
        result = pd.concat(parts).sort_index()
        result = result.reindex(prices.index)
    else:
        result = _score_single(prices)

    return result
