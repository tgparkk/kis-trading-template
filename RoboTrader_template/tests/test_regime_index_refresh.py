"""regime 게이트용 KOSPI/KOSDAQ 일봉 자동 갱신 회귀.

배경 (2026-06-24): regime 게이트(exclude_bear)는 robotrader.daily_prices 의
stock_code='KOSPI'/'KOSDAQ' 일봉을 읽는데, 이를 채우던 backfill_kospi_index.py
가 수동·미스케줄이라 05-29 동결됐고(게이트 stale), KOSDAQ 는 아예 부재였다.
근본 수정: FDR KS11→KOSPI / KQ11→KOSDAQ 를 daily_prices 에 매일 자동 upsert
(게이트 읽기경로 불변, KOSDAQ 포함). EOD 훅에서 호출.

검증:
  1. KOSPI·KOSDAQ 둘 다 daily_prices 에 기록(save_daily_prices_batch).
  2. FDR df(Date 인덱스·대문자 컬럼)를 date/open/.../close 소문자로 정규화.
  3. 한 지수 FDR 실패가 다른 지수 적재를 막지 않음(격리).
"""
import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fdr_df():
    """FDR DataReader 형태: Date 인덱스 + Open/High/Low/Close/Volume."""
    idx = pd.to_datetime(["2026-06-23", "2026-06-24"])
    idx.name = "Date"
    return pd.DataFrame(
        {"Open": [1, 2], "High": [1, 2], "Low": [1, 2],
         "Close": [3050.0, 3010.0], "Volume": [100, 200]},
        index=idx,
    )


class _FakeFDR:
    def __init__(self, by_ticker):
        self.by_ticker = by_ticker
        self.calls = []

    def DataReader(self, ticker, start=None):
        self.calls.append((ticker, start))
        val = self.by_ticker[ticker]
        if isinstance(val, Exception):
            raise val
        return val


def test_refresh_writes_both_indices_normalized():
    from core.regime.index_refresh import refresh_regime_indices
    repo = Mock()
    repo.save_daily_prices_batch = Mock(return_value=True)
    fdr = _FakeFDR({"KS11": _fdr_df(), "KQ11": _fdr_df()})

    res = refresh_regime_indices(repo, start="2026-06-15", fdr=fdr)

    codes = [c.args[0] for c in repo.save_daily_prices_batch.call_args_list]
    assert "KOSPI" in codes and "KOSDAQ" in codes
    assert res["KOSPI"] == 2 and res["KOSDAQ"] == 2
    # FDR 티커 매핑 확인
    assert ("KS11", "2026-06-15") in fdr.calls and ("KQ11", "2026-06-15") in fdr.calls
    # 정규화: 소문자 date/close 컬럼
    df0 = repo.save_daily_prices_batch.call_args_list[0].args[1]
    assert "date" in df0.columns and "close" in df0.columns


def test_one_index_failure_isolated():
    from core.regime.index_refresh import refresh_regime_indices
    repo = Mock()
    repo.save_daily_prices_batch = Mock(return_value=True)
    fdr = _FakeFDR({"KS11": _fdr_df(), "KQ11": RuntimeError("fdr down")})

    res = refresh_regime_indices(repo, start="2026-06-15", fdr=fdr)

    assert res["KOSPI"] == 2   # KOSPI 정상
    assert res["KOSDAQ"] == 0  # KOSDAQ 실패해도 예외 전파 안 함
    # KOSPI 는 그래도 기록됨
    codes = [c.args[0] for c in repo.save_daily_prices_batch.call_args_list]
    assert "KOSPI" in codes
