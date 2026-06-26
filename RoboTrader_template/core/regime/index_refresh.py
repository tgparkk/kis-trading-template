"""regime 게이트용 KOSPI/KOSDAQ 일봉 자동 갱신.

regime 게이트(RegimeGate)는 robotrader.daily_prices 의 stock_code='KOSPI'/'KOSDAQ'
일봉을 SSOT 로 읽는다. 이를 채우던 scripts/backfill_kospi_index.py 가 수동·미스케줄
이라 동결되면 게이트가 stale/fail-open 된다(2026-06-24 진단: KOSPI 05-29 동결,
KOSDAQ 부재). 본 모듈은 FDR(KS11→KOSPI, KQ11→KOSDAQ)로 최근 일봉을 받아
daily_prices 에 멱등 upsert 한다. EOD 훅에서 매일 호출 → 자동 신선 유지.

게이트의 읽기 경로(price_repo.get_daily_prices)는 그대로 두고 데이터만 최신화하므로
게이트 로직 변경 위험이 없다.
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Dict, Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)

# regime 게이트 stock_code → FDR 티커
INDEX_TICKERS: Dict[str, str] = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}
# 최근 며칠치를 받아 작은 공백도 함께 메운다(멱등 upsert).
_DEFAULT_LOOKBACK_DAYS = 10
# FDR 일시실패(EOD 15:48 데이터 lag·네트워크) 대비 재시도. 빈 df/예외면 재시도,
# 행>0 이면 즉시 성공. 3회 모두 실패면 현행처럼 0 으로 격리(2026-06-26).
_MAX_FDR_RETRIES = 3
_FDR_RETRY_SLEEP_SEC = 1.0


def _fdr_to_daily_df(df):
    """FDR DataReader df(Date 인덱스·Open/High/Low/Close/Volume) →
    save_daily_prices_batch 가 읽는 date/open/high/low/close/volume 소문자 컬럼."""
    if df is None or getattr(df, "empty", True):
        return df
    out = df.reset_index()
    out.columns = [str(c).lower() for c in out.columns]
    if "date" not in out.columns:
        # reset_index 의 첫 컬럼(구 인덱스)을 date 로 사용
        out = out.rename(columns={out.columns[0]: "date"})
    return out


def refresh_regime_indices(price_repo, start: Optional[str] = None, fdr=None) -> Dict[str, int]:
    """KOSPI/KOSDAQ 일봉을 FDR 로 받아 daily_prices 에 멱등 upsert.

    Args:
        price_repo: PriceRepository (save_daily_prices_batch 보유).
        start: FDR 조회 시작일 'YYYY-MM-DD'. None 이면 최근 _DEFAULT_LOOKBACK_DAYS.
        fdr: FinanceDataReader 모듈(테스트 주입용). None 이면 실제 import.

    Returns:
        {"KOSPI": n_rows, "KOSDAQ": n_rows}. 한 지수 실패는 0 으로 격리(예외 미전파).
    """
    if start is None:
        start = (date.today() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    if fdr is None:
        import FinanceDataReader as fdr  # noqa: N813

    result: Dict[str, int] = {}
    for name, ticker in INDEX_TICKERS.items():
        try:
            daily = None
            for attempt in range(_MAX_FDR_RETRIES):
                try:
                    df = fdr.DataReader(ticker, start)
                    daily = _fdr_to_daily_df(df)
                    if daily is not None and not getattr(daily, "empty", True):
                        break  # 행>0 성공 → 즉시 종료
                except Exception as e:  # noqa: BLE001 - 일시실패는 재시도
                    daily = None
                    logger.warning(
                        "[regime-index] %s(%s) %d/%d차 시도 실패: %s",
                        name, ticker, attempt + 1, _MAX_FDR_RETRIES, e,
                    )
                if attempt < _MAX_FDR_RETRIES - 1:
                    time.sleep(_FDR_RETRY_SLEEP_SEC)
            n = 0 if (daily is None or getattr(daily, "empty", True)) else len(daily)
            if n:
                price_repo.save_daily_prices_batch(name, daily)
            result[name] = n
            logger.info("[regime-index] %s(%s) %d행 갱신", name, ticker, n)
        except Exception as e:  # noqa: BLE001 - 한 지수 실패가 다른 지수를 막지 않게 격리
            logger.warning("[regime-index] %s(%s) 갱신 실패: %s", name, ticker, e)
            result[name] = 0
    return result
