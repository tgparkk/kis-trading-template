"""
SampleScreener 단위 테스트
============================

검증 항목:
  1. 후보 기준 — RSI < rsi_max  또는  (MA5 > MA20 AND RSI < rsi_trend_max)
  2. 룩어헤드 방지 — scan_date 당일 일봉을 사용하지 않고 D-1 까지만 본다
  3. 필터 — 거래대금 하한 미달 / ETF / 우선주 / 데이터 부족 종목 제외
  4. 어댑터 — ScreenerBase 인터페이스 준수, default_params 머지
  5. 실패 격리 — DB 조회 실패 시 raise 없이 빈 리스트 반환

외부 DB(strategy_analysis)에 접속하지 않도록 historical_data 헬퍼를 monkeypatch 한다.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.sample import screener as sample_screener
from strategies.sample.screener import (
    SampleScreener,
    SampleScreenerAdapter,
    _is_etf_or_etn,
    _is_preferred_stock,
)
from strategies.screener_base import ScreenerBase


# ============================================================================
# Helper — 합성 일봉 생성
# ============================================================================

def _make_candle_df(closes, volumes=None, trading_value=1e9, days=None):
    """종가 리스트로 일봉 DataFrame 생성 (open/high/low/close/volume/trading_value)."""
    n = len(closes)
    if volumes is None:
        volumes = [100_000] * n
    if days is None:
        days = pd.date_range("2026-01-01", periods=n).date.tolist()
    return pd.DataFrame({
        "date": days,
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": volumes,
        "trading_value": [trading_value] * n,
    })


def _downtrend_oversold(n=30):
    """지속 하락 → RSI 과매도 일봉 (RSI < 45 유도)."""
    return [10000 - i * 120 for i in range(n)]


def _uptrend_mild(n=30):
    """완만한 상승 → MA5>MA20, RSI 중간대 일봉."""
    return [10000 + i * 60 for i in range(n)]


def _flat_overbought(n=30):
    """급등 후 고RSI → 후보 제외 대상 (RSI 높음, MA 추세 약함)."""
    base = [10000] * 20 + [10000 + i * 300 for i in range(1, n - 19)]
    return base[:n]


# ============================================================================
# 1. 후보 기준
# ============================================================================

def test_oversold_stock_selected(monkeypatch):
    """RSI 과매도 종목은 후보로 선정된다."""
    meta = {"000001": {"name": "과매도주", "market": "KOSPI"}}
    candles = {"000001": _make_candle_df(_downtrend_oversold())}

    monkeypatch.setattr(SampleScreener, "_load_market_stocks", staticmethod(lambda: meta))
    monkeypatch.setattr(sample_screener, "get_daily_candles_range",
                        lambda codes, start, end: candles)

    result = SampleScreener().scan_candidates(date(2026, 5, 22))
    codes = [c.code for c in result]
    assert "000001" in codes, f"과매도 종목 누락: {result}"
    assert "과매도" in result[0].reason


def test_overbought_stock_excluded(monkeypatch):
    """RSI 높고 추세 약한 종목은 후보에서 제외된다."""
    meta = {"000009": {"name": "과열주", "market": "KOSPI"}}
    candles = {"000009": _make_candle_df(_flat_overbought())}

    monkeypatch.setattr(SampleScreener, "_load_market_stocks", staticmethod(lambda: meta))
    monkeypatch.setattr(sample_screener, "get_daily_candles_range",
                        lambda codes, start, end: candles)

    result = SampleScreener().scan_candidates(date(2026, 5, 22))
    assert "000009" not in [c.code for c in result], f"과열주가 후보에 포함됨: {result}"


def test_low_trading_value_excluded(monkeypatch):
    """거래대금 하한 미달 종목은 제외된다 (유동성 필터)."""
    meta = {"000002": {"name": "저유동성주", "market": "KOSPI"}}
    # RSI 과매도이지만 거래대금이 하한(5억) 미만
    candles = {"000002": _make_candle_df(_downtrend_oversold(), trading_value=1e7)}

    monkeypatch.setattr(SampleScreener, "_load_market_stocks", staticmethod(lambda: meta))
    monkeypatch.setattr(sample_screener, "get_daily_candles_range",
                        lambda codes, start, end: candles)

    result = SampleScreener().scan_candidates(date(2026, 5, 22))
    assert "000002" not in [c.code for c in result], "거래대금 미달 종목이 통과됨"


def test_insufficient_data_excluded(monkeypatch):
    """일봉이 부족한 종목(< MA20)은 제외된다."""
    meta = {"000003": {"name": "신규상장주", "market": "KOSPI"}}
    candles = {"000003": _make_candle_df(_downtrend_oversold(n=10))}  # 10봉만

    monkeypatch.setattr(SampleScreener, "_load_market_stocks", staticmethod(lambda: meta))
    monkeypatch.setattr(sample_screener, "get_daily_candles_range",
                        lambda codes, start, end: candles)

    result = SampleScreener().scan_candidates(date(2026, 5, 22))
    assert "000003" not in [c.code for c in result], "데이터 부족 종목이 통과됨"


def test_max_candidates_respected(monkeypatch):
    """max_candidates 상한이 적용된다."""
    meta = {f"00{i:04d}": {"name": f"종목{i}", "market": "KOSPI"} for i in range(20)}
    candles = {
        code: _make_candle_df(_downtrend_oversold())
        for code in meta
    }
    monkeypatch.setattr(SampleScreener, "_load_market_stocks", staticmethod(lambda: meta))
    monkeypatch.setattr(sample_screener, "get_daily_candles_range",
                        lambda codes, start, end: candles)

    result = SampleScreener().scan_candidates(date(2026, 5, 22), max_candidates=5)
    assert len(result) == 5, f"max_candidates 미적용: {len(result)}건"


# ============================================================================
# 2. 룩어헤드 방지 — D-1 cutoff
# ============================================================================

def test_lookahead_cutoff_is_d_minus_1(monkeypatch):
    """get_daily_candles_range 의 end_date 는 scan_date 가 아니라 직전 영업일이다."""
    captured = {}

    def _spy(codes, start, end):
        captured["start"] = start
        captured["end"] = end
        return {}

    monkeypatch.setattr(SampleScreener, "_load_market_stocks",
                        staticmethod(lambda: {"000001": {"name": "X", "market": "KOSPI"}}))
    monkeypatch.setattr(sample_screener, "get_daily_candles_range", _spy)

    # 2026-05-22 는 금요일 → 직전 영업일은 2026-05-21 (목)
    scan_date = date(2026, 5, 22)
    SampleScreener().scan_candidates(scan_date)

    assert captured["end"] < scan_date, (
        f"룩어헤드: end_date({captured['end']}) 가 scan_date({scan_date}) 이상"
    )
    assert captured["end"] == date(2026, 5, 21), (
        f"D-1 cutoff 오류: {captured['end']} (기대 2026-05-21)"
    )
    assert captured["start"] < captured["end"], "start 가 end 이후"


def test_lookahead_cutoff_skips_weekend(monkeypatch):
    """scan_date 가 월요일이면 cutoff 는 직전 금요일(주말 건너뜀)."""
    captured = {}
    monkeypatch.setattr(SampleScreener, "_load_market_stocks",
                        staticmethod(lambda: {"000001": {"name": "X", "market": "KOSPI"}}))
    monkeypatch.setattr(sample_screener, "get_daily_candles_range",
                        lambda codes, start, end: captured.update(end=end) or {})

    # 2026-05-25 는 월요일 → 직전 영업일은 2026-05-22 (금)
    SampleScreener().scan_candidates(date(2026, 5, 25))
    assert captured["end"] == date(2026, 5, 22), (
        f"주말 건너뛰기 실패: {captured['end']} (기대 2026-05-22)"
    )


# ============================================================================
# 3. 시장 필터 헬퍼
# ============================================================================

def test_etf_filter():
    """ETF/ETN 브랜드명은 _is_etf_or_etn 으로 걸러진다."""
    for name in ["KODEX 200", "TIGER 미국S&P500", "ACE 미국나스닥100", "삼성 ETF"]:
        assert _is_etf_or_etn(name), f"ETF 미감지: {name}"
    for name in ["삼성전자", "셀트리온", "카카오"]:
        assert not _is_etf_or_etn(name), f"일반종목 오감지: {name}"


def test_preferred_stock_filter():
    """우선주(코드 끝자리 비0 또는 '우' 접미)는 _is_preferred_stock 로 걸러진다."""
    assert _is_preferred_stock("005935", "삼성전자우")
    assert _is_preferred_stock("000001", "어떤종목우")
    assert not _is_preferred_stock("005930", "삼성전자")
    assert not _is_preferred_stock("000660", "SK하이닉스")


# ============================================================================
# 4. 어댑터 — ScreenerBase 인터페이스
# ============================================================================

def test_adapter_is_screener_base():
    """SampleScreenerAdapter 는 ScreenerBase 를 상속하고 strategy_name 을 갖는다."""
    adapter = SampleScreenerAdapter()
    assert isinstance(adapter, ScreenerBase)
    assert adapter.strategy_name == "sample"


def test_adapter_default_params():
    """default_params 는 후보 기준 키를 모두 포함한다."""
    params = SampleScreenerAdapter().default_params()
    for key in ("rsi_period", "rsi_max", "rsi_trend_max", "ma_short",
                "ma_long", "min_trading_value", "trading_value_lookback",
                "max_candidates"):
        assert key in params, f"default_params 에 {key} 누락"


def test_adapter_scan_merges_params(monkeypatch):
    """adapter.scan() 은 부분 params 를 default 와 머지해 스크리너에 전달한다."""
    captured = {}

    def _fake_scan(self, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(SampleScreener, "scan_candidates", _fake_scan)
    SampleScreenerAdapter().scan(date(2026, 5, 22), {"rsi_max": 30.0})

    assert captured["rsi_max"] == 30.0, "오버라이드 params 미반영"
    assert captured["ma_long"] == 20, "default params 미머지"


def test_adapter_build_from_factory():
    """build_adapter('sample') 로 어댑터를 생성할 수 있다."""
    from runners._adapter_factory import build_adapter
    adapter = build_adapter("sample")
    assert adapter is not None
    assert adapter.strategy_name == "sample"


def test_sample_in_all_strategies():
    """screener_snapshot_collector.ALL_STRATEGIES 에 sample 이 포함된다."""
    from runners.screener_snapshot_collector import ALL_STRATEGIES
    assert "sample" in ALL_STRATEGIES


# ============================================================================
# 5. 실패 격리 — raise 금지
# ============================================================================

def test_scan_returns_empty_on_db_failure(monkeypatch):
    """DB 조회가 실패해도 raise 하지 않고 빈 리스트를 반환한다."""
    def _boom(*args, **kwargs):
        raise RuntimeError("DB 연결 실패 시뮬레이션")

    monkeypatch.setattr(SampleScreener, "_load_market_stocks", staticmethod(_boom))
    result = SampleScreener().scan_candidates(date(2026, 5, 22))
    assert result == [], "DB 실패 시 빈 리스트가 아님"


def test_scan_returns_empty_when_no_stocks(monkeypatch):
    """대상 종목이 없으면 빈 리스트를 반환한다."""
    monkeypatch.setattr(SampleScreener, "_load_market_stocks", staticmethod(lambda: {}))
    result = SampleScreener().scan_candidates(date(2026, 5, 22))
    assert result == []


def test_scan_returns_empty_when_no_candles(monkeypatch):
    """일봉 데이터가 없으면 빈 리스트를 반환한다."""
    monkeypatch.setattr(SampleScreener, "_load_market_stocks",
                        staticmethod(lambda: {"000001": {"name": "X", "market": "KOSPI"}}))
    monkeypatch.setattr(sample_screener, "get_daily_candles_range",
                        lambda codes, start, end: {})
    result = SampleScreener().scan_candidates(date(2026, 5, 22))
    assert result == []


# ============================================================================
# 6. realtime 경로 — KIS 일봉 API 라이브 조회 (mock)
# ============================================================================

def _make_kis_daily_df(closes, dates, volumes=None, trading_values=None):
    """KIS 일봉 API output2 형식 DataFrame 생성.

    KIS 응답 컬럼: stck_bsop_date(YYYYMMDD), stck_clpr(종가),
    acml_vol(거래량), acml_tr_pbmn(거래대금). 값은 문자열(콤마 포함 가능).
    KIS 응답은 최신순일 수 있으므로 최신→과거 순으로 정렬해 반환한다.
    """
    n = len(closes)
    if volumes is None:
        volumes = [100_000] * n
    if trading_values is None:
        trading_values = [1_000_000_000] * n
    rows = []
    for i in range(n):
        rows.append({
            "stck_bsop_date": dates[i],
            "stck_clpr": str(closes[i]),
            "stck_oprc": str(closes[i]),
            "stck_hgpr": str(int(closes[i] * 1.01)),
            "stck_lwpr": str(int(closes[i] * 0.99)),
            "acml_vol": str(volumes[i]),
            "acml_tr_pbmn": str(trading_values[i]),
        })
    # KIS 응답은 최신순 — 역순으로 정렬해 정규화 로직의 정렬을 검증
    rows.reverse()
    return pd.DataFrame(rows)


def _kis_date_range(n, end_date_str="20260522"):
    """end_date_str 를 마지막 봉으로 하는 영업일(주말 제외) YYYYMMDD 리스트(오름차순)."""
    end = datetime.strptime(end_date_str, "%Y%m%d").date()
    days = []
    cur = end
    while len(days) < n:
        if cur.weekday() < 5:  # 평일만
            days.append(cur.strftime("%Y%m%d"))
        cur = cur - timedelta(days=1)
    days.reverse()
    return days


def test_realtime_oversold_stock_selected(monkeypatch):
    """realtime 경로: KIS API mock 으로 과매도 종목이 후보로 선정된다."""
    closes = _downtrend_oversold(30)
    # D-1 봉이 직전 영업일(05-21)이 되도록 마지막 봉을 05-21 로 설정
    dates = _kis_date_range(30, end_date_str="20260521")
    kis_df = _make_kis_daily_df(closes, dates)

    monkeypatch.setattr(SampleScreener, "_load_realtime_universe",
                        classmethod(lambda cls: {"000111": {"name": "과매도주", "market": "KOSPI"}}))

    import api.kis_market_api as kis_market_api
    monkeypatch.setattr(kis_market_api, "get_inquire_daily_itemchartprice",
                        lambda **kwargs: kis_df)
    monkeypatch.setattr(sample_screener.time, "sleep", lambda *a, **k: None)

    # 2026-05-22(금) 스캔 → realtime 경로
    result = SampleScreener().scan_candidates_realtime(date(2026, 5, 22))
    codes = [c.code for c in result]
    assert "000111" in codes, f"realtime 과매도 종목 누락: {result}"
    assert "과매도" in result[0].reason


def test_realtime_excludes_current_day_bar(monkeypatch):
    """realtime 룩어헤드 방지: KIS 응답에 당일(scan_date) 봉이 있어도 제외된다.

    D-1 까지는 지속 하락(과매도 RSI<45 → 후보)이고, 당일 봉에 비정상 폭등가를
    심어둔다. 당일 봉이 RSI 계산에 반영되면 RSI 가 급등해 과매도 조건을 깨고
    후보에서 탈락한다. 정규화가 당일 봉을 제거하면 D-1 까지의 과매도 패턴만
    남아 후보로 선정된다 — 이 차이로 룩어헤드 제거를 검증한다.
    """
    captured = {}

    # D-1 까지 30봉(지속 하락 → 과매도) + 당일(scan_date=05-22) 1봉(폭등)
    base_closes = _downtrend_oversold(30)
    base_dates = _kis_date_range(30, end_date_str="20260521")  # 마지막 = D-1(05-21)
    d1_close = base_closes[-1]
    # 당일 봉: D-1 종가의 5배로 폭등 (포함되면 RSI 급등 → 과매도 조건 붕괴)
    closes_with_today = base_closes + [d1_close * 5]
    dates_with_today = base_dates + ["20260522"]  # scan_date 당일 봉
    kis_df = _make_kis_daily_df(closes_with_today, dates_with_today)

    monkeypatch.setattr(SampleScreener, "_load_realtime_universe",
                        classmethod(lambda cls: {"000222": {"name": "과매도주", "market": "KOSPI"}}))

    def _spy_api(**kwargs):
        captured["called"] = True
        return kis_df

    import api.kis_market_api as kis_market_api
    monkeypatch.setattr(kis_market_api, "get_inquire_daily_itemchartprice", _spy_api)
    monkeypatch.setattr(sample_screener.time, "sleep", lambda *a, **k: None)

    result = SampleScreener().scan_candidates_realtime(date(2026, 5, 22))

    assert captured.get("called"), "KIS API 가 호출되지 않음"
    # 당일 폭등 봉이 제외되면 D-1 까지 과매도 → 후보 1건 선정
    assert len(result) == 1, f"룩어헤드 제외 후 후보 수 오류: {result}"
    cand = result[0]
    # prev_close 가 당일 폭등가가 아니라 D-1 정상 종가(d1_close)여야 함
    assert cand.prev_close == float(d1_close), (
        f"룩어헤드: 당일 봉이 prev_close 에 반영됨 ({cand.prev_close} != {d1_close})"
    )
    assert "과매도" in cand.reason


def test_realtime_with_today_bar_included_would_change_result(monkeypatch):
    """대조군: 당일 봉을 제거하지 않으면(룩어헤드 발생) 결과가 달라짐을 명시.

    _normalize_kis_daily 에 scan_date 를 미래로 넘기면 당일 봉이 포함된다.
    그 경우 RSI 가 폭등 봉 영향으로 과매도(RSI<45)를 벗어나 후보에서 탈락한다.
    이 테스트는 룩어헤드 차단 로직이 실제로 결과를 바꾼다는 것을 증명한다.
    """
    base_closes = _downtrend_oversold(30)
    base_dates = _kis_date_range(30, end_date_str="20260521")
    d1_close = base_closes[-1]
    closes_with_today = base_closes + [d1_close * 5]
    dates_with_today = base_dates + ["20260522"]
    kis_df = _make_kis_daily_df(closes_with_today, dates_with_today)

    # scan_date 를 미래(05-23 이후)로 넘기면 05-22 봉이 포함됨 → 룩어헤드 상태 재현
    norm_with_today = SampleScreener._normalize_kis_daily(kis_df, "20260525")
    norm_d1_only = SampleScreener._normalize_kis_daily(kis_df, "20260522")

    assert norm_with_today is not None and norm_d1_only is not None
    # 당일 봉 포함 시 1봉 더 많아야 함
    assert len(norm_with_today) == len(norm_d1_only) + 1, (
        "당일 봉 포함/제외 봉 수 차이가 1이 아님"
    )
    # 당일 봉 포함 시 최신 종가는 폭등가
    assert float(norm_with_today["close"].iloc[-1]) == float(d1_close * 5)
    # 당일 봉 제외 시 최신 종가는 D-1 정상 종가
    assert float(norm_d1_only["close"].iloc[-1]) == float(d1_close)


def test_normalize_kis_daily_drops_today_and_future(monkeypatch):
    """_normalize_kis_daily 는 scan_date 이상 봉을 모두 제거한다."""
    closes = [10000, 10100, 10200, 9999, 8888]
    dates = ["20260519", "20260520", "20260521", "20260522", "20260525"]
    kis_df = _make_kis_daily_df(closes, dates)

    # scan_date = 05-22 → 05-22, 05-25 봉 제거, 05-19~05-21 만 남음
    norm = SampleScreener._normalize_kis_daily(kis_df, "20260522")
    assert norm is not None
    assert len(norm) == 3, f"당일/미래 봉 미제거: {len(norm)}봉"
    # 마지막(최신) 봉 종가가 D-1(05-21) 종가여야 함
    assert float(norm["close"].iloc[-1]) == 10200.0, (
        f"D-1 cutoff 오류: 최신 봉 종가 {norm['close'].iloc[-1]}"
    )
    # 오름차순 정렬 확인
    assert float(norm["close"].iloc[0]) == 10000.0


def test_realtime_low_trading_value_excluded(monkeypatch):
    """realtime 경로: 거래대금 하한 미달 종목은 제외된다."""
    closes = _downtrend_oversold(30)
    dates = _kis_date_range(30, end_date_str="20260521")
    # 거래대금 1천만원 (하한 5억 미만)
    kis_df = _make_kis_daily_df(closes, dates, trading_values=[10_000_000] * 30)

    monkeypatch.setattr(SampleScreener, "_load_realtime_universe",
                        classmethod(lambda cls: {"000333": {"name": "저유동성주", "market": "KOSPI"}}))

    import api.kis_market_api as kis_market_api
    monkeypatch.setattr(kis_market_api, "get_inquire_daily_itemchartprice",
                        lambda **kwargs: kis_df)
    monkeypatch.setattr(sample_screener.time, "sleep", lambda *a, **k: None)

    result = SampleScreener().scan_candidates_realtime(date(2026, 5, 22))
    assert "000333" not in [c.code for c in result], "거래대금 미달 종목이 통과됨"


def test_realtime_returns_empty_on_api_failure(monkeypatch):
    """realtime 경로: KIS API 가 None 을 반환해도 raise 없이 빈 리스트."""
    monkeypatch.setattr(SampleScreener, "_load_realtime_universe",
                        classmethod(lambda cls: {"000444": {"name": "X", "market": "KOSPI"}}))

    import api.kis_market_api as kis_market_api
    monkeypatch.setattr(kis_market_api, "get_inquire_daily_itemchartprice",
                        lambda **kwargs: None)
    monkeypatch.setattr(sample_screener.time, "sleep", lambda *a, **k: None)

    result = SampleScreener().scan_candidates_realtime(date(2026, 5, 22))
    assert result == [], "API 실패 시 빈 리스트가 아님"


def test_realtime_returns_empty_when_no_universe(monkeypatch):
    """realtime 경로: universe 가 없으면 빈 리스트를 반환한다."""
    monkeypatch.setattr(SampleScreener, "_load_realtime_universe",
                        classmethod(lambda cls: {}))
    result = SampleScreener().scan_candidates_realtime(date(2026, 5, 22))
    assert result == []


# ============================================================================
# 7. 어댑터 realtime/historical 분기
# ============================================================================

def test_adapter_routes_today_to_realtime(monkeypatch):
    """adapter.scan(오늘) 은 _scan_realtime → scan_candidates_realtime 로 분기한다."""
    captured = {}

    def _fake_realtime(self, **kwargs):
        captured["path"] = "realtime"
        captured.update(kwargs)
        return []

    def _fake_historical(self, **kwargs):
        captured["path"] = "historical"
        return []

    monkeypatch.setattr(SampleScreener, "scan_candidates_realtime", _fake_realtime)
    monkeypatch.setattr(SampleScreener, "scan_candidates", _fake_historical)

    today = datetime.now().date()
    SampleScreenerAdapter().scan(today, {"rsi_max": 33.0})

    assert captured["path"] == "realtime", "오늘 날짜가 realtime 으로 분기되지 않음"
    assert captured["rsi_max"] == 33.0, "오버라이드 params 미반영"
    assert captured["ma_long"] == 20, "default params 미머지"


def test_adapter_routes_past_to_historical(monkeypatch):
    """adapter.scan(과거) 은 _scan_historical → scan_candidates 로 분기한다."""
    captured = {}

    def _fake_realtime(self, **kwargs):
        captured["path"] = "realtime"
        return []

    def _fake_historical(self, **kwargs):
        captured["path"] = "historical"
        return []

    monkeypatch.setattr(SampleScreener, "scan_candidates_realtime", _fake_realtime)
    monkeypatch.setattr(SampleScreener, "scan_candidates", _fake_historical)

    past = date(2025, 1, 6)
    SampleScreenerAdapter().scan(past, {})

    assert captured["path"] == "historical", "과거 날짜가 historical 로 분기되지 않음"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
