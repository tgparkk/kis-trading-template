"""
VKOSPI 시그널 (S2-01)
======================

VKOSPI: 코스피200 옵션 기반 30일 내재변동성 (한국판 VIX).
2009년 4월 한국거래소 도입.

PIT 보장:
  - VKOSPI 일봉 종가는 한국 장 마감(15:30 KST) 후 확정
  - T일 종가 → T+1 시초가 의사결정에 사용 가능 (No Look-Ahead)
  - vkospi_at(scan_date) 호출 시 scan_date - 1일 데이터 반환

신호 해석:
  - VKOSPI > 30: 공포 국면
  - VKOSPI 20~30: 주의 구간
  - VKOSPI < 15: 안정 국면 (모멘텀 전략 유리)
  - spike (z-score > 2.0): 패닉 저점 가능성 → 단기 반등 검토

데이터 소스:
  - DB: robotrader.vkospi_daily (backfill_vkospi.py 사전 백필)
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import psycopg2

logger = logging.getLogger(__name__)

_DB_DEFAULTS = dict(
    host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    port=int(os.getenv("TIMESCALE_PORT", "5433")),
    user=os.getenv("TIMESCALE_USER", "robotrader"),
    password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    database=os.getenv("TIMESCALE_DB", "robotrader"),
)


def _get_conn():
    return psycopg2.connect(**_DB_DEFAULTS)


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼: 날짜 범위로 VKOSPI 히스토리 조회
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_vkospi_history(end_date: date, window: int = 60) -> pd.DataFrame:
    """end_date 이하 최근 window+5 거래일 VKOSPI 종가 조회.

    PIT 보장: end_date = T일 (= scan_date - 1).
    """
    lookback_from = end_date - timedelta(days=(window + 5) * 2)  # 충분한 여유
    sql = """
        SELECT trade_date, close
        FROM vkospi_daily
        WHERE trade_date >= %s
          AND trade_date <= %s
          AND close IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT %s
    """
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (lookback_from, end_date, window + 5))
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[VKOSPI] DB 조회 실패 end_date=%s: %s", end_date, exc)
        return pd.DataFrame(columns=["trade_date", "close"])

    if not rows:
        return pd.DataFrame(columns=["trade_date", "close"])

    df = pd.DataFrame(rows, columns=["trade_date", "close"])
    df["close"] = df["close"].astype(float)
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────

def vkospi_at(scan_date: date) -> float:
    """scan_date - 1일 기준 VKOSPI 종가 반환.

    PIT 보장: scan_date = T+1 의사결정일. 반환값 = T일 종가.

    Returns
    -------
    float
        VKOSPI 종가. 데이터 없으면 float('nan').
    """
    end_date = scan_date - timedelta(days=1)
    df = _fetch_vkospi_history(end_date, window=1)
    if df.empty:
        logger.debug("[VKOSPI] 데이터 없음 end_date=%s", end_date)
        return float("nan")

    # end_date 당일 값 우선, 없으면 가장 최근 값
    exact = df[df["trade_date"] == end_date]
    if not exact.empty:
        return float(exact.iloc[-1]["close"])
    return float(df.iloc[-1]["close"])


def vkospi_zscore(scan_date: date, window: int = 60) -> float:
    """scan_date - 1일 기준 VKOSPI 종가를 window 거래일 롤링으로 표준화한 z-score.

    PIT 보장: scan_date = T+1 의사결정일. 모든 데이터는 T일 이하.
    z-score = (현재값 - window 평균) / window 표준편차

    Parameters
    ----------
    scan_date : date
        의사결정일 (오늘 장 개시 시점).
    window : int
        표준화에 사용할 거래일 수 (기본 60일).

    Returns
    -------
    float
        z-score. 데이터 부족 시 float('nan').
    """
    end_date = scan_date - timedelta(days=1)
    df = _fetch_vkospi_history(end_date, window=window)

    if len(df) < 2:
        logger.debug("[VKOSPI] z-score 계산 불가: 데이터 %d건 (최소 2건 필요)", len(df))
        return float("nan")

    closes = df["close"].values
    current = closes[-1]
    hist = closes[:-1] if len(closes) > window else closes

    mu = float(pd.Series(hist).mean())
    sigma = float(pd.Series(hist).std(ddof=1))

    if sigma == 0:
        return 0.0

    z = (current - mu) / sigma
    logger.debug("[VKOSPI] z-score=%.3f (current=%.2f, mu=%.2f, sigma=%.2f)", z, current, mu, sigma)
    return float(z)


def vkospi_spike_signal(scan_date: date, threshold_z: float = 2.0) -> bool:
    """VKOSPI 스파이크 감지 — 시장 레짐 감지기.

    z-score > threshold_z 이면 패닉 국면으로 판단.
    단기 저점 가능성이 있으나, 추세 전략에서는 매수 회피 신호로도 사용.

    PIT 보장: scan_date = T+1 의사결정일. 내부적으로 T일 이하 데이터만 사용.

    Parameters
    ----------
    scan_date : date
        의사결정일.
    threshold_z : float
        스파이크 판단 z-score 임계값 (기본 2.0 = 2 표준편차 이상).

    Returns
    -------
    bool
        True = VKOSPI 스파이크 감지 (공포 국면).
    """
    z = vkospi_zscore(scan_date)
    if pd.isna(z):
        return False
    spike = z > threshold_z
    if spike:
        logger.info("[VKOSPI] 스파이크 감지 scan_date=%s z=%.3f > %.1f", scan_date, z, threshold_z)
    return spike
