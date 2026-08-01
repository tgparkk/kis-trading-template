"""상승구간(시작점 → 최고점) 탐지 3변형."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

VARIANTS = ("low", "surge_open", "prev_close")
SURGE_VOL_MULT = 3.0   # 급등봉 = 판정지표가 lookback 중앙값의 3배 이상
SURGE_METRICS = ("volume", "value")


@dataclass(frozen=True)
class Segment:
    code: str
    start_date: str
    start_px: float
    peak_date: str
    peak_px: float
    gain: float


def _surge_series(g: pd.DataFrame, surge_by: str) -> pd.Series:
    """급등봉 판정지표.

    ⚠️ `volume` 은 4~6차가 쓴 기존 축이다(재현용 기본값). 앵커 실측 메모 §2 는
       **거래대금**을 권고했다 — 다날 급등봉은 거래량이 아니라 거래대금이
       28.8배(28억→807억)였고 블로그 툴팁(830억)과 정합한다.
       `prev_close`·`surge_open` 두 변형이 **이 함수 하나에 함께 의존**하므로,
       지표가 틀리면 두 변형이 같이 틀린다(= `low` 만 무사하다).
    """
    if surge_by not in SURGE_METRICS:
        raise ValueError(f"unknown surge metric: {surge_by}")
    return g["volume"] if surge_by == "volume" else g["close"] * g["volume"]


def _surge_idx(g: pd.DataFrame, low_pos: int, surge_by: str = "volume") -> int | None:
    """최저가 이후 첫 급등봉 위치. 없으면 None."""
    s = _surge_series(g, surge_by)
    med = s.iloc[: low_pos + 1].median()
    if not med or med <= 0:
        med = s.median()
    for i in range(low_pos + 1, len(g)):
        if s.iat[i] >= SURGE_VOL_MULT * med:
            return i
    return None


def _start_price(w: pd.DataFrame, low_pos: int, variant: str,
                 surge_by: str = "volume") -> float | None:
    if variant == "low":
        return float(w["low"].iat[low_pos])
    s = _surge_idx(w, low_pos, surge_by)
    if s is None or s == 0:
        return None
    return float(w["open"].iat[s]) if variant == "surge_open" else float(w["close"].iat[s - 1])


def find_segments_local(df: pd.DataFrame, k_mult: float, horizon: int, min_gain: float,
                        med_window: int = 60, surge_by: str = "value") -> list[Segment]:
    """국지 상승구간 — **급등봉을 기준점으로** 잡는다. 신고가 조건이 없다.

    `find_segments` 는 「오늘이 창 신고가인 날」만 상승구간의 끝으로 인정한다.
    그 조건이 **태쏘의 다날 사례를 원천 배제**했다 — 2026-07-23 고가 5,100 은
    직전 60거래일 최고 8,640 에 한참 못 미치는 **국지 반등**이었다.

    여기서는 앵커 실측이 확정한 구조를 그대로 쓴다:
      시작점 = 급등봉 **직전봉 종가**  (다날 3,930 = 07-22 종가, 완전일치)
      최고점 = 급등봉부터 `horizon` 봉 내 **최고 고가** (다날 5,100 = 07-23 고가)
      급등봉 = **거래대금**이 직전 `med_window` 중앙값의 `k_mult` 배 이상
               (다날 28.8배 — 거래량이 아니라 거래대금이다)

    연속 급등봉은 첫 봉만 채택한다(근접 중복 방지).
    """
    out: list[Segment] = []
    for code, g in df.groupby("stock_code", sort=False):
        g = g.reset_index(drop=True)
        if len(g) < med_window + 2:
            continue
        val = _surge_series(g, surge_by)
        med = val.rolling(med_window).median().shift(1)
        is_surge = (val >= k_mult * med) & med.notna() & (med > 0)
        for s in range(1, len(g)):
            if not bool(is_surge.iat[s]) or bool(is_surge.iat[s - 1]):
                continue                       # 연속 급등봉은 첫 봉만
            start_px = float(g["close"].iat[s - 1])
            if start_px <= 0:
                continue
            w = g.iloc[s: s + horizon + 1]
            if w.empty:
                continue
            p = int(w["high"].idxmax())
            peak_px = float(g["high"].iat[p])
            gain = peak_px / start_px - 1.0
            if gain < min_gain:
                continue
            out.append(Segment(code=str(code), start_date=str(g["date"].iat[s - 1]),
                               start_px=start_px, peak_date=str(g["date"].iat[p]),
                               peak_px=peak_px, gain=gain))
    return out


def find_segments(df: pd.DataFrame, variant: str, lookback: int, min_gain: float,
                  surge_by: str = "volume") -> list[Segment]:
    """시간축을 훑으며 '새 고점을 찍은 날'마다 상승구간을 발생시킨다.

    ⚠️ 종목당 마지막 창 하나만 보면 5.6년 백테스트 표본이 종목당 1건으로
       붕괴해 MDE 게이트를 통과할 수 없다. 반드시 전 기간을 스캔한다.
    같은 (종목, 시작일) 조합은 최고 peak 하나로 접는다.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant: {variant}")
    out: list[Segment] = []
    for code, g in df.groupby("stock_code", sort=False):
        g = g.reset_index(drop=True)
        best: dict[tuple[str, str], Segment] = {}
        for t in range(lookback, len(g)):
            w = g.iloc[t - lookback : t + 1].reset_index(drop=True)
            if float(w["high"].iat[-1]) < float(w["high"].max()):
                continue                      # 오늘이 창 최고가가 아니면 발생시키지 않는다
            low_pos = int(w["low"].iloc[:-1].idxmin())
            start_px = _start_price(w, low_pos, variant, surge_by)
            if start_px is None or start_px <= 0:
                continue
            peak_px = float(w["high"].iat[-1])
            gain = peak_px / start_px - 1.0
            if gain < min_gain:
                continue
            seg = Segment(
                code=str(code),
                start_date=str(w["date"].iat[low_pos]),
                start_px=start_px,
                peak_date=str(w["date"].iat[-1]),
                peak_px=peak_px,
                gain=gain,
            )
            key = (seg.code, seg.start_date)
            if key not in best or seg.peak_px > best[key].peak_px:
                best[key] = seg
        out.extend(best.values())
    return out
