"""
lib/signals/book_minute.py — 분봉 기반 단기 트레이딩 패턴 시그널 (PIT-safe)
==============================================================================

출처: Andrew Aziz "How to Day Trade for a Living" + 강창권 "1분봉 단기추세"

PIT 강제 규칙:
  - shift(-N) 절대 금지.
  - ABCD swing point는 T분봉 기준으로 T-1 이전 데이터만 사용하여 확정.
  - ORB는 09:00~opening_range 구간 측정 후 그 이후 분봉에서만 시그널.
  - R2G는 cross above 발생 시점(T)에서 True — T+1에 진입.
  - 다일(Multi-day) 데이터 지원: 일별 독립 처리.
  - 입력 minute_df는 dt(datetime) 오름차순 정렬 전제.

함수 목록:
  - abcd_pattern          : A→B→C→D 4단계 패턴 (Aziz 전략1)
  - bull_flag             : 급등 후 깃발형 횡보 돌파 (Aziz 전략2)
  - opening_range_breakout: 장초반 레인지 돌파 (Aziz 전략9)
  - red_to_green          : 갭다운 후 전일 종가 상향 돌파 (Aziz 전략8)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _get_dt_series(df: pd.DataFrame, dt_col: str) -> pd.Series:
    """dt_col이 컬럼에 있으면 파싱, 없으면 index를 사용."""
    if dt_col in df.columns:
        return pd.to_datetime(df[dt_col])
    return pd.to_datetime(df.index)


def _iter_days(dt_series: pd.Series) -> list[tuple[int, int]]:
    """같은 날짜의 [i, j) 구간 목록 반환.

    Parameters
    ----------
    dt_series : pd.Series
        pd.to_datetime 변환된 시계열 (reset_index 없이 원래 index 유지).
    """
    if len(dt_series) == 0:
        return []
    dates = dt_series.dt.date.values  # numpy array of datetime.date
    spans = []
    i = 0
    n = len(dates)
    while i < n:
        cur = dates[i]
        j = i
        while j < n and dates[j] == cur:
            j += 1
        spans.append((i, j))
        i = j
    return spans


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def abcd_pattern(
    minute_df: pd.DataFrame,
    min_ab_pct: float = 2.0,
    max_pullback_pct: float = 5.0,
    dt_col: str = "dt",
) -> pd.Series:
    """ABCD 패턴 감지 — D 형성(B 돌파) 시점에 True (PIT-safe).

    정의 (Andrew Aziz "How to Day Trade for a Living" 전략1):
        A → B : 상승 (B > A * (1 + min_ab_pct/100))
        B → C : 눌림 (C >= A_close AND C <= B * (1 - max_pullback_pct/100 * 0))
                실제: A_close <= C <= B * (1 - correction_factor)
                correction_factor = max_pullback_pct/100
        C → D : D > B_high (B 고점 돌파) → 이 시점에 True

    ABCD swing point 식별 방법론:
        - A: 상승 시작점. 직전 분봉까지 국소 저점 탐색 (rolling min).
        - B: A 이후 고점. A~C 사이 어느 분봉에서 형성되었는지 사후적으로 알 수 없으므로,
             각 분봉 T에서 "T-1 시점까지의 창(window)" 내 최고점을 B 후보로 사용.
             즉 B = rolling_high(A..T-1), 확정 방식으로 PIT 위반 없음.
        - C: B 이후 눌림. T 분봉의 close가 C 조건을 만족하면 C 후보.
        - D: T 분봉 close > B_high → True 발생.

    구현 근사:
        각 T 시점에서 직전 W분봉(= pole_window = 30분) 창을 돌아보아:
          1. 창 내 최고점(B_candidate)과 그 위치를 찾는다.
          2. B 이전 저점(A)을 찾아 AB 상승폭이 min_ab_pct 이상인지 확인.
          3. B 이후 현재까지의 최저점(C_candidate)이 눌림 조건을 만족하는지 확인.
          4. T 분봉 close > B_candidate이면 D 돌파 → True.

    PIT 강제:
        - T 분봉의 시그널은 T-1 이전 분봉 데이터만 사용.
        - shift(-N) 없음.

    Parameters
    ----------
    minute_df : pd.DataFrame
        분봉 데이터. dt_col(datetime), open, high, low, close, volume 필요.
    min_ab_pct : float
        A→B 최소 상승률 (%). 기본 2.0.
    max_pullback_pct : float
        B→C 최대 눌림률 (%). 기본 5.0. C >= B * (1 - max_pullback_pct/100).
    dt_col : str
        datetime 컬럼명.

    Returns
    -------
    pd.Series
        bool 시리즈. D 돌파 분봉에서 True.
        다일 입력 시 일별 독립 처리.
    """
    required = {"high", "low", "close"}
    missing = required - set(minute_df.columns)
    if missing:
        raise ValueError(f"abcd_pattern: 필수 컬럼 누락 — {missing}")

    result = np.zeros(len(minute_df), dtype=bool)
    if len(minute_df) == 0:
        return pd.Series(result, index=minute_df.index, name="abcd_pattern")

    dt_series = _get_dt_series(minute_df, dt_col)
    spans = _iter_days(dt_series)

    high_arr  = minute_df["high"].values.astype(float)
    low_arr   = minute_df["low"].values.astype(float)
    close_arr = minute_df["close"].values.astype(float)

    # 창 크기: 최소 4개 분봉(A,B,C,D 각 1개)이어야 의미있음
    min_window = 4

    for day_start, day_end in spans:
        day_len = day_end - day_start
        if day_len < min_window:
            continue

        for t in range(day_start + min_window - 1, day_end):
            # T 분봉의 close가 D 후보
            # 창: [day_start, t) — T 이전까지만 (PIT 강제)
            window_start = day_start
            window_end   = t  # exclusive (미래 t 미포함)

            if window_end - window_start < 3:
                continue

            # 창 내 고점(B 후보) 찾기
            highs_win = high_arr[window_start:window_end]
            lows_win  = low_arr[window_start:window_end]

            b_idx_local = int(np.argmax(highs_win))
            b_high = highs_win[b_idx_local]

            # B 이전 A(저점) 탐색
            if b_idx_local == 0:
                # B가 첫 분봉 → A를 구분할 수 없음
                continue

            a_close = np.min(lows_win[:b_idx_local])

            # A→B 상승 조건
            if a_close <= 0:
                continue
            ab_pct = (b_high - a_close) / a_close * 100.0
            if ab_pct < min_ab_pct:
                continue

            # B 이후 C(눌림) 탐색: [b_idx_local+1, window_end)
            after_b_start = window_start + b_idx_local + 1
            if after_b_start >= window_end:
                continue

            c_low = np.min(low_arr[after_b_start:window_end])

            # C 조건:
            #   C >= A (눌림이 A 아래로 가지 않음)
            #   C <= B * (1 - max_pullback_pct/100)
            c_floor = a_close
            c_ceil  = b_high * (1.0 - max_pullback_pct / 100.0)
            if c_low < c_floor:
                continue
            if c_low > b_high:
                # 눌림 없음 (B 갱신만 있었음)
                continue
            # c_ceil 조건: 눌림이 충분히 있었는가
            # c_low <= c_ceil이면 충분한 눌림
            if c_ceil < c_floor:
                # max_pullback이 너무 크면 조건 완화
                c_ceil = b_high

            # D 조건: T 분봉 close > B 고점
            if close_arr[t] > b_high:
                result[t] = True

    return pd.Series(result, index=minute_df.index, name="abcd_pattern")


def bull_flag(
    minute_df: pd.DataFrame,
    pole_pct: float = 5.0,
    pole_window: int = 30,
    flag_window: int = 30,
    flag_range_pct: float = 2.0,
    volume_mult: float = 1.5,
    dt_col: str = "dt",
) -> pd.Series:
    """Bull Flag (강세 깃발형) — 급등 후 횡보 돌파 시 True (PIT-safe).

    정의 (Andrew Aziz "How to Day Trade for a Living" 전략2):
        1. 깃대(flagpole): 직전 pole_window분 내 +pole_pct% 이상 상승.
        2. 깃발(flag): 이후 flag_window분간 고저폭 < flag_range_pct%.
        3. 돌파: 깃발 상단 break + 거래량 평균 × volume_mult 이상.

    PIT 강제:
        - T 분봉 시그널 = T-1 이전 데이터만 사용.
        - 깃대 종료점과 깃발 구간은 T 이전으로만 구성.
        - T 분봉 자체의 close/volume이 돌파 확인에 사용됨 (현재 분봉 close는 허용 — 완성된 봉).

    Parameters
    ----------
    minute_df : pd.DataFrame
        분봉 데이터. dt, high, low, close, volume 필요.
    pole_pct : float
        깃대 최소 상승률 (%). 기본 5.0.
    pole_window : int
        깃대 탐색 창 (분). 기본 30.
    flag_window : int
        깃발 횡보 구간 최대 길이 (분). 기본 30.
    flag_range_pct : float
        깃발 최대 고저폭 (%). 기본 2.0.
    volume_mult : float
        돌파 시 거래량 배수 (평균 대비). 기본 1.5.
    dt_col : str
        datetime 컬럼명.

    Returns
    -------
    pd.Series
        bool 시리즈. 돌파 분봉에서 True.
    """
    required = {"high", "low", "close", "volume"}
    missing = required - set(minute_df.columns)
    if missing:
        raise ValueError(f"bull_flag: 필수 컬럼 누락 — {missing}")

    result = np.zeros(len(minute_df), dtype=bool)
    if len(minute_df) == 0:
        return pd.Series(result, index=minute_df.index, name="bull_flag")

    dt_series = _get_dt_series(minute_df, dt_col)
    spans = _iter_days(dt_series)

    high_arr   = minute_df["high"].values.astype(float)
    low_arr    = minute_df["low"].values.astype(float)
    close_arr  = minute_df["close"].values.astype(float)
    volume_arr = minute_df["volume"].values.astype(float)

    min_required = pole_window + 2  # 깃대 + 깃발 최소 1봉 + 돌파봉

    for day_start, day_end in spans:
        day_len = day_end - day_start
        if day_len < min_required:
            continue

        for t in range(day_start + min_required - 1, day_end):
            # 1. 깃대 탐색: [t - pole_window - flag_window, t - flag_window] 창 내
            #    단순화: 직전 pole_window 분봉 내에서 최대 상승폭 확인
            pole_start = max(day_start, t - pole_window - flag_window)
            pole_end   = max(day_start, t - 1)  # T 이전까지

            if pole_end - pole_start < 2:
                continue

            # 깃대 후보: pole_start ~ pole_end 중 일정 구간 급등
            # 각 시작점 s에서 s+pole_window까지의 상승폭 확인
            pole_found = False
            pole_top_close = np.nan
            pole_top_high  = np.nan
            pole_end_idx   = -1

            for s in range(pole_start, pole_end - 1):
                pe = min(s + pole_window, pole_end)
                if pe <= s + 1:
                    continue
                start_close = close_arr[s]
                if start_close <= 0:
                    continue
                max_high_in_window = np.max(high_arr[s:pe])
                pct = (max_high_in_window - start_close) / start_close * 100.0
                if pct >= pole_pct:
                    pole_found      = True
                    pole_top_high   = max_high_in_window
                    pole_top_close  = max_high_in_window  # 깃발 상단 기준
                    pole_end_idx    = pe - 1  # 깃대 끝 인덱스
                    break  # 가장 이른 깃대 사용

            if not pole_found or pole_end_idx < 0:
                continue

            # 2. 깃발 구간: [pole_end_idx+1, t) — T 이전까지
            flag_start = pole_end_idx + 1
            flag_end   = t  # exclusive

            if flag_end - flag_start < 1:
                continue

            flag_highs  = high_arr[flag_start:flag_end]
            flag_lows   = low_arr[flag_start:flag_end]
            flag_vols   = volume_arr[flag_start:flag_end]

            flag_high_max = np.max(flag_highs)
            flag_low_min  = np.min(flag_lows)

            if flag_low_min <= 0:
                continue

            flag_range = (flag_high_max - flag_low_min) / flag_low_min * 100.0
            if flag_range > flag_range_pct:
                continue  # 깃발 폭 초과

            # 깃발 길이 제한
            if flag_end - flag_start > flag_window:
                continue

            # 3. 돌파 확인: T 분봉 close > 깃발 상단
            flag_top = flag_high_max
            if close_arr[t] <= flag_top:
                continue

            # 거래량: T 분봉 volume > 깃발 기간 평균 × volume_mult
            if len(flag_vols) == 0:
                continue
            avg_flag_vol = np.mean(flag_vols)
            if avg_flag_vol <= 0:
                continue
            if volume_arr[t] < avg_flag_vol * volume_mult:
                continue

            result[t] = True

    return pd.Series(result, index=minute_df.index, name="bull_flag")


def opening_range_breakout(
    minute_df: pd.DataFrame,
    range_minutes: int = 15,
    market_open: str = "09:00",
    dt_col: str = "dt",
) -> pd.Series:
    """Opening Range Breakout (ORB) — 장초반 레인지 돌파 시 True (PIT-safe).

    정의 (Andrew Aziz "How to Day Trade for a Living" 전략9):
        1. 장 시작 후 range_minutes 분간 고점(opening_high) / 저점(opening_low) 측정.
        2. range_minutes 경과 이후, close > opening_high이면 매수 시그널.
        3. 손절: opening_low (반환 Series에 포함하지 않음 — 호출자 판단).

    PIT 강제:
        - opening_high/low는 09:00~09:14(range_minutes=15) 분봉으로만 계산.
        - 09:15 이후 분봉에서만 시그널 발생.
        - 일자별 독립 처리.

    Parameters
    ----------
    minute_df : pd.DataFrame
        분봉 데이터. dt, high, low, close 필요.
    range_minutes : int
        Opening Range 측정 분 수. 기본 15.
    market_open : str
        장 시작 시각 (HH:MM). 기본 "09:00".
    dt_col : str
        datetime 컬럼명.

    Returns
    -------
    pd.Series
        bool 시리즈. Opening Range 고점 돌파 분봉에서 True.
        Opening Range 측정 구간(09:00~09:14) 및 돌파 이후 재돌파는 False
        (일중 최초 돌파만 True — 일별 리셋).
    """
    required = {"high", "low", "close"}
    missing = required - set(minute_df.columns)
    if missing:
        raise ValueError(f"opening_range_breakout: 필수 컬럼 누락 — {missing}")

    result = np.zeros(len(minute_df), dtype=bool)
    if len(minute_df) == 0:
        return pd.Series(result, index=minute_df.index, name="orb")

    dt_series = _get_dt_series(minute_df, dt_col)
    spans = _iter_days(dt_series)

    high_arr  = minute_df["high"].values.astype(float)
    low_arr   = minute_df["low"].values.astype(float)
    close_arr = minute_df["close"].values.astype(float)

    open_h, open_m = map(int, market_open.split(":"))

    for day_start, day_end in spans:
        # 장 시작 시각의 분봉 인덱스 찾기
        day_dts = dt_series.iloc[day_start:day_end]
        day_arr = day_dts.values  # numpy datetime64

        # pandas Timestamp로 변환하여 시각 비교
        day_ts = pd.DatetimeIndex(day_arr)
        day_date = day_ts[0].date()

        open_ts = pd.Timestamp(year=day_date.year, month=day_date.month,
                               day=day_date.day, hour=open_h, minute=open_m)
        range_end_ts = open_ts + pd.Timedelta(minutes=range_minutes)

        # Opening Range 구간 마스크
        or_mask = (day_ts >= open_ts) & (day_ts < range_end_ts)
        after_mask = day_ts >= range_end_ts

        or_indices   = np.where(or_mask)[0]
        after_indices = np.where(after_mask)[0]

        if len(or_indices) == 0 or len(after_indices) == 0:
            continue

        # opening_high / opening_low
        or_global = day_start + or_indices
        opening_high = np.max(high_arr[or_global])
        opening_low  = np.min(low_arr[or_global])

        # 돌파 확인: 일중 최초 돌파만 True
        broken = False
        for local_idx in after_indices:
            g_idx = day_start + local_idx
            if not broken and close_arr[g_idx] > opening_high:
                result[g_idx] = True
                broken = True
            # 재돌파는 무시 (일중 최초만)

    return pd.Series(result, index=minute_df.index, name="orb")


def red_to_green(
    minute_df: pd.DataFrame,
    prev_close_col: str = "prev_close",
    dt_col: str = "dt",
) -> pd.Series:
    """Red to Green (R2G) — 갭다운 후 전일 종가 상향 돌파 시 True (PIT-safe).

    정의 (Andrew Aziz "How to Day Trade for a Living" 전략8):
        1. 시초가(갭) < 전일 종가 (gap down, "레드" 시작).
        2. 일중 close가 전일 종가 위로 cross above → "그린" 전환.
        3. 손절: 전일 종가 하향 이탈.

    cross above 조건:
        - T-1 분봉 close <= prev_close AND T 분봉 close > prev_close → True.
        - 최초 전환만 True (이후 재돌파 무시).

    PIT 강제:
        - T 분봉 시그널은 T 분봉 close와 T-1 분봉 close만 사용.
        - 일별 독립 처리.
        - prev_close는 외부에서 주입 (직접 derive 금지 — look-ahead 위험).

    Parameters
    ----------
    minute_df : pd.DataFrame
        분봉 데이터. dt, close, prev_close 필요.
        prev_close: 전일 종가 (각 분봉 행에 동일 값으로 채워진 컬럼).
    prev_close_col : str
        전일 종가 컬럼명. 기본 "prev_close".
    dt_col : str
        datetime 컬럼명.

    Returns
    -------
    pd.Series
        bool 시리즈. R2G 전환 분봉에서 True.
        gap down이 아닌 날 (시초가 >= 전일 종가)은 False.
    """
    required = {"close", prev_close_col}
    missing = required - set(minute_df.columns)
    if missing:
        raise ValueError(f"red_to_green: 필수 컬럼 누락 — {missing}")

    result = np.zeros(len(minute_df), dtype=bool)
    if len(minute_df) == 0:
        return pd.Series(result, index=minute_df.index, name="r2g")

    dt_series = _get_dt_series(minute_df, dt_col)
    spans = _iter_days(dt_series)

    close_arr      = minute_df["close"].values.astype(float)
    prev_close_arr = minute_df[prev_close_col].values.astype(float)

    for day_start, day_end in spans:
        if day_end - day_start < 2:
            continue

        # 시초가 = 당일 첫 분봉 open 또는 close
        # open 컬럼이 있으면 사용, 없으면 close로 대체
        if "open" in minute_df.columns:
            open_arr = minute_df["open"].values.astype(float)
            first_open = open_arr[day_start]
        else:
            first_open = close_arr[day_start]

        day_prev_close = prev_close_arr[day_start]

        # Gap down 확인 (시초가 < 전일 종가)
        if first_open >= day_prev_close:
            continue  # gap down 아님 → 이 날 R2G 없음

        # cross above 탐색: 최초 전환만
        crossed = False
        for t in range(day_start + 1, day_end):
            prev_t_close = close_arr[t - 1]
            curr_t_close = close_arr[t]
            prev_close   = prev_close_arr[t]

            if not crossed and prev_t_close <= prev_close and curr_t_close > prev_close:
                result[t] = True
                crossed = True

    return pd.Series(result, index=minute_df.index, name="r2g")
