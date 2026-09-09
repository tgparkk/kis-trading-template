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


# ════════════════════════════════════════════════════════════════════════════
# 2026-09-10 — regime 지수 소스 KIS 전환 + 신선도 경보 (설계 §3·§4·§6)
#
# W-idx2(07:40 · 15:35)도 W-idx1 과 «같은» 상류(FDR)를 타서 같이 멈췄다.
# 여기서 고정하는 계약: 소스 스위치 · 폴백 조건 · 반환 dict 형태 불변 · 신선도 로그.
# ════════════════════════════════════════════════════════════════════════════
from datetime import datetime


class _FakeKIS:
    """api.kis_market_api 대역 — get_index_daily_chart 만 흉내낸다(네트워크 0)."""

    def __init__(self, by_code=None, exc=None):
        self.by_code = by_code or {}
        self.exc = exc
        self.calls = []

    def get_index_daily_chart(self, index_code, start=None, end=None):
        self.calls.append((index_code, start, end))
        if self.exc is not None:
            raise self.exc
        return self.by_code.get(index_code)


def _kis_df(dates):
    return pd.DataFrame([{
        "stck_bsop_date": d, "bstp_nmix_oprc": "6900.00", "bstp_nmix_hgpr": "7100.00",
        "bstp_nmix_lwpr": "6800.00", "bstp_nmix_prpr": "7000.00", "acml_vol": "240446",
    } for d in dates])


class _FakeRepo:
    """save 는 기록만, get_daily_prices 는 지정한 날짜 목록으로 df 를 만든다."""

    def __init__(self, by_code=None):
        self.saved = []
        self.by_code = by_code or {}

    def save_daily_prices_batch(self, code, df, **kw):
        self.saved.append((code, df, kw))
        return True

    def get_daily_prices(self, stock_code, days=30):
        dates = self.by_code.get(stock_code)
        if dates is None:
            return pd.DataFrame()
        return pd.DataFrame({"date": list(dates), "close": [1.0] * len(dates)})


# 오라클 종목엔 «여러 날»이 있다 — cutoff 자르기는 «집계 전»에 걸려야 하므로
# 실제 표처럼 T−1 과 T 를 둘 다 준다(15:35 기준 D_ref = T−1 = 2026-09-09).
_FRESH = {
    "KOSPI": ["2026-09-09", "2026-09-10"], "KOSDAQ": ["2026-09-09", "2026-09-10"],
    "005930": ["2026-09-09", "2026-09-10"], "000660": ["2026-09-09", "2026-09-10"],
    "035420": ["2026-09-09", "2026-09-10"],
}


def _at(monkeypatch, ir, now=datetime(2026, 9, 10, 15, 35)):
    monkeypatch.setattr(ir, "now_kst", lambda: now)
    monkeypatch.setattr(ir.time, "sleep", lambda *a, **k: None)


import pytest


@pytest.fixture
def logcap():
    """모듈 logger 에 핸들러를 직접 붙여 메시지를 모은다.

    utils.logger.setup_logger 는 propagate=False 라 pytest 기본 로그 픽스처가
    이 로거의 줄을 «못 본다» — 캡처 장치도 가드다(2026-08 재사용 규칙).
    """
    import logging

    attached = []

    def _attach(lg):
        msgs = []

        class _H(logging.Handler):
            def emit(self, record):
                msgs.append(record.getMessage())

        h = _H()
        h.setLevel(logging.DEBUG)
        lg.addHandler(h)
        attached.append((lg, h))
        return msgs

    yield _attach
    for lg, h in attached:
        lg.removeHandler(h)


def test_kis_source_is_used_and_fdr_is_not_called(monkeypatch):
    """소스가 kis 면 KIS 스텁만 불리고 FDR 스텁은 «한 번도» 안 불린다."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)
    repo = _FakeRepo(_FRESH)
    kis = _FakeKIS({"0001": _kis_df(["20260909", "20260910"]),
                    "1001": _kis_df(["20260909", "20260910"])})
    fdr = _FakeFDR({"KS11": _fdr_df(), "KQ11": _fdr_df()})

    res = ir.refresh_regime_indices(repo, start="2026-09-01", fdr=fdr, kis=kis)

    assert res == {"KOSPI": 2, "KOSDAQ": 2}
    assert sorted(c[0] for c in kis.calls) == ["0001", "1001"]
    assert fdr.calls == []
    # 저장 df 는 기존과 «같은» 소문자 컬럼 계약
    df0 = repo.saved[0][1]
    assert {"date", "open", "high", "low", "close", "volume"} <= set(df0.columns)
    assert "index_code" not in df0.columns


def test_return_dict_has_exactly_two_keys(monkeypatch):
    """🔴 bot/system_monitor.py 가 min(res.values()) > 0 으로 판단한다 — 키 추가 금지."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)
    kis = _FakeKIS({"0001": _kis_df(["20260910"]), "1001": _kis_df(["20260910"])})

    res = ir.refresh_regime_indices(_FakeRepo(_FRESH), start="2026-09-01", kis=kis)

    assert set(res) == {"KOSPI", "KOSDAQ"}
    assert all(isinstance(v, int) for v in res.values())


def test_kis_exception_falls_back_to_fdr_retry_loop(monkeypatch):
    """KIS 예외 → 기존 FDR 3회 재시도 폴백이 «그대로» 돈다."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)
    repo = _FakeRepo(_FRESH)
    kis = _FakeKIS(exc=RuntimeError("KIS 지수 일봉 응답 없음"))
    fdr = _FlakyFDR({"KS11": 1, "KQ11": 1})   # 1회 실패 후 성공

    res = ir.refresh_regime_indices(repo, start="2026-09-01", fdr=fdr, kis=kis)

    assert res == {"KOSPI": 2, "KOSDAQ": 2}
    assert fdr.calls["KS11"] == 2 and fdr.calls["KQ11"] == 2


def test_kis_empty_result_does_not_fall_back(monkeypatch):
    """🔴 «빈 결과»는 폴백 사유가 아니다(설계 §3) — 0행으로 남기고 판정에 맡긴다."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)
    kis = _FakeKIS({"0001": pd.DataFrame(), "1001": pd.DataFrame()})
    fdr = _FakeFDR({"KS11": _fdr_df(), "KQ11": _fdr_df()})

    res = ir.refresh_regime_indices(_FakeRepo(_FRESH), start="2026-09-01", fdr=fdr, kis=kis)

    assert res == {"KOSPI": 0, "KOSDAQ": 0}
    assert fdr.calls == []


def test_one_index_kis_failure_isolated(monkeypatch):
    """한 지수의 KIS 실패가 다른 지수를 막지 않는다(기존 격리 계약 유지)."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)

    class _HalfKIS(_FakeKIS):
        def get_index_daily_chart(self, index_code, start=None, end=None):
            self.calls.append((index_code, start, end))
            if index_code == "1001":
                raise RuntimeError("kosdaq down")
            return _kis_df(["20260910"])

    repo = _FakeRepo(_FRESH)
    fdr = _FakeFDR({"KS11": _fdr_df(), "KQ11": _fdr_df()})

    res = ir.refresh_regime_indices(repo, start="2026-09-01", fdr=fdr, kis=_HalfKIS())

    assert res["KOSPI"] == 1        # KIS 로 성공
    assert res["KOSDAQ"] == 2       # FDR 폴백으로 성공
    assert [t for t, _ in fdr.calls] == ["KQ11"]


def test_save_is_not_called_with_past_rows_insert_only(monkeypatch):
    """W3 는 최근 10일 정정을 계속 받아야 한다 — (E′) 가드를 켜지 않는다."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)
    repo = _FakeRepo(_FRESH)
    kis = _FakeKIS({"0001": _kis_df(["20260910"]), "1001": _kis_df(["20260910"])})

    ir.refresh_regime_indices(repo, start="2026-09-01", kis=kis)

    for _code, _df, kw in repo.saved:
        assert "past_rows_insert_only" not in kw


def test_freshness_warning_when_index_lags(monkeypatch, logcap):
    """지수만 밀리면 [index-freshness] 가 잡힌다 — 반환 dict 는 그대로다."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)
    stale_repo = _FakeRepo({
        "KOSPI": ["2026-09-07"], "KOSDAQ": ["2026-09-07"],
        "005930": ["2026-09-09", "2026-09-10"], "000660": ["2026-09-09", "2026-09-10"],
        "035420": ["2026-09-09", "2026-09-10"],
    })
    kis = _FakeKIS({"0001": _kis_df(["20260907"]), "1001": _kis_df(["20260907"])})

    msgs = logcap(ir.logger)
    res = ir.refresh_regime_indices(stale_repo, start="2026-09-01", kis=kis)

    assert set(res) == {"KOSPI", "KOSDAQ"}
    assert any(m.startswith("[index-freshness] STALE axis=A table=daily_prices")
               and "src=kis" in m for m in msgs)


def test_no_freshness_warning_when_fresh(monkeypatch, logcap):
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)
    kis = _FakeKIS({"0001": _kis_df(["20260910"]), "1001": _kis_df(["20260910"])})

    msgs = logcap(ir.logger)
    ir.refresh_regime_indices(_FakeRepo(_FRESH), start="2026-09-01", kis=kis)

    assert not [m for m in msgs if "[index-freshness]" in m]


def test_premarket_0740_does_not_false_alarm(monkeypatch, logcap):
    """🔴 07:40 오탐 회귀 — 오라클엔 오늘 행(W1 훅)이 있고 지수는 T−1 뿐이어도 정상."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir, now=datetime(2026, 9, 10, 7, 40))
    repo = _FakeRepo({
        "KOSPI": ["2026-09-09"], "KOSDAQ": ["2026-09-09"],
        "005930": ["2026-09-09", "2026-09-10"],     # 장전 훅이 넣은 «오늘 행»
        "000660": ["2026-09-09", "2026-09-10"], "035420": ["2026-09-09", "2026-09-10"],
    })
    kis = _FakeKIS({"0001": _kis_df(["20260909"]), "1001": _kis_df(["20260909"])})

    msgs = logcap(ir.logger)
    ir.refresh_regime_indices(repo, start="2026-09-01", kis=kis)

    assert not [m for m in msgs if "[index-freshness]" in m]


def test_row_count_log_keeps_prefix_and_adds_src(monkeypatch, logcap):
    """`%d행 갱신` 줄 형식은 유지하고 src 만 덧붙인다(로그 grep 계약)."""
    import core.regime.index_refresh as ir
    _at(monkeypatch, ir)
    kis = _FakeKIS({"0001": _kis_df(["20260910"]), "1001": _kis_df(["20260910"])})

    msgs = logcap(ir.logger)
    ir.refresh_regime_indices(_FakeRepo(_FRESH), start="2026-09-01", kis=kis)

    assert "[regime-index] KOSPI(KS11) 1행 갱신 src=kis" in msgs
