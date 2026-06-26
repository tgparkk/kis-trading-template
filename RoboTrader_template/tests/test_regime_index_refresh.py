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


def test_one_index_failure_isolated(monkeypatch):
    import core.regime.index_refresh as ir
    monkeypatch.setattr(ir.time, "sleep", lambda *a, **k: None)  # 재시도 대기 제거(고속)
    repo = Mock()
    repo.save_daily_prices_batch = Mock(return_value=True)
    fdr = _FakeFDR({"KS11": _fdr_df(), "KQ11": RuntimeError("fdr down")})

    res = ir.refresh_regime_indices(repo, start="2026-06-15", fdr=fdr)

    assert res["KOSPI"] == 2   # KOSPI 정상
    assert res["KOSDAQ"] == 0  # KOSDAQ 실패해도 예외 전파 안 함
    # KOSPI 는 그래도 기록됨
    codes = [c.args[0] for c in repo.save_daily_prices_batch.call_args_list]
    assert "KOSPI" in codes


class _FlakyFDR:
    """티커별로 초기 N회는 실패(예외) 후 성공 df 반환 — 일시실패 재시도 검증용."""

    def __init__(self, fail_then_succeed):
        self.fail_then_succeed = fail_then_succeed  # ticker -> 초기 실패 횟수
        self.calls = {}

    def DataReader(self, ticker, start=None):
        self.calls[ticker] = self.calls.get(ticker, 0) + 1
        if self.calls[ticker] <= self.fail_then_succeed.get(ticker, 0):
            raise RuntimeError("transient fdr fail")
        return _fdr_df()


class _EmptyThenFullFDR:
    """티커별 1회차는 빈 df, 이후 정상 df — 빈 df 도 재시도 대상임을 검증."""

    def __init__(self):
        self.calls = {}

    def DataReader(self, ticker, start=None):
        self.calls[ticker] = self.calls.get(ticker, 0) + 1
        if self.calls[ticker] == 1:
            return _fdr_df().iloc[0:0]   # 빈 df
        return _fdr_df()


def test_refresh_retries_on_transient_failure(monkeypatch):
    """FDR 1회 실패 후 성공이면 재시도해 행을 받아온다(EOD 15:48 일시실패 보정)."""
    import core.regime.index_refresh as ir
    monkeypatch.setattr(ir.time, "sleep", lambda *a, **k: None)
    repo = Mock()
    repo.save_daily_prices_batch = Mock(return_value=True)
    fdr = _FlakyFDR({"KS11": 1, "KQ11": 1})

    res = ir.refresh_regime_indices(repo, start="2026-06-15", fdr=fdr)

    assert res["KOSPI"] == 2 and res["KOSDAQ"] == 2
    assert fdr.calls["KS11"] == 2 and fdr.calls["KQ11"] == 2  # 1실패+1성공


def test_refresh_retries_on_empty_df(monkeypatch):
    """빈 df 도 재시도 대상 — 1회차 빈 df, 2회차 정상 df 면 성공."""
    import core.regime.index_refresh as ir
    monkeypatch.setattr(ir.time, "sleep", lambda *a, **k: None)
    repo = Mock()
    repo.save_daily_prices_batch = Mock(return_value=True)
    fdr = _EmptyThenFullFDR()

    res = ir.refresh_regime_indices(repo, start="2026-06-15", fdr=fdr)

    assert res["KOSPI"] == 2 and res["KOSDAQ"] == 2
    assert fdr.calls["KS11"] == 2 and fdr.calls["KQ11"] == 2


def test_refresh_gives_up_after_three_failures(monkeypatch):
    """3회 모두 실패하면 현행처럼 0(예외 격리)·저장 미호출."""
    import core.regime.index_refresh as ir
    monkeypatch.setattr(ir.time, "sleep", lambda *a, **k: None)
    repo = Mock()
    repo.save_daily_prices_batch = Mock(return_value=True)
    fdr = _FlakyFDR({"KS11": 3, "KQ11": 3})

    res = ir.refresh_regime_indices(repo, start="2026-06-15", fdr=fdr)

    assert res["KOSPI"] == 0 and res["KOSDAQ"] == 0
    assert fdr.calls["KS11"] == 3 and fdr.calls["KQ11"] == 3  # 최대 3회
    repo.save_daily_prices_batch.assert_not_called()
