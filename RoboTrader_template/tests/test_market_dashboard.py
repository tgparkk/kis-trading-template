"""시장현황 대시보드 테스트"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date, timedelta
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from market_dashboard.models import (
    IndexData, InvestorFlow, ExchangeRate, RankedStock, PositionSummary,
    GlobalMarketSnapshot, DomesticMarketSnapshot,
    PremarketBriefing, MarketDashboardData,
)
from market_dashboard.global_market import GlobalMarketCollector
from market_dashboard.domestic_market import DomesticMarketCollector
from market_dashboard.formatters import ConsoleFormatter
from market_dashboard.dashboard import MarketDashboard


def _make_index_data(name="코스피", value=2500.0, change=15.0, change_rate=0.60,
                     volume=500000, trade_amount=45000.0):
    return IndexData(name=name, value=value, change=change, change_rate=change_rate,
                     volume=volume, trade_amount=trade_amount, timestamp=datetime(2026, 2, 22, 10, 0, 0))


def _make_investor_flow(foreign=1500.0, institution=-800.0, individual=-700.0):
    return InvestorFlow(foreign_net=foreign, institution_net=institution,
                        individual_net=individual, timestamp=datetime(2026, 2, 22, 10, 0, 0))


def _make_exchange_rate(pair="USD/KRW", rate=1350.50, change=-2.30, change_rate=-0.17):
    return ExchangeRate(pair=pair, rate=rate, change=change, change_rate=change_rate,
                        timestamp=datetime(2026, 2, 22, 10, 0, 0))


def _make_ranked_stock(rank=1, stock_code="005930", stock_name="삼성전자",
                       current_price=70000.0, change_rate=1.50, volume=12000000):
    return RankedStock(rank=rank, stock_code=stock_code, stock_name=stock_name,
                       current_price=current_price, change_rate=change_rate, volume=volume)


def _make_position_summary(stock_code="005930", stock_name="삼성전자",
                           quantity=10, avg_price=68000.0, current_price=70000.0,
                           profit_loss=20000.0, profit_loss_rate=2.94, state="POSITIONED"):
    return PositionSummary(stock_code=stock_code, stock_name=stock_name, quantity=quantity,
                           avg_price=avg_price, current_price=current_price,
                           profit_loss=profit_loss, profit_loss_rate=profit_loss_rate, state=state)


def _make_kis_index_response(value=2500.0, change=15.0, change_rate=0.60,
                             volume=500000, trade_amount_raw=4500000000000.0):
    return {"bstp_nmix_prpr": str(value), "bstp_nmix_prdy_vrss": str(change),
            "bstp_nmix_prdy_ctrt": str(change_rate), "acml_vol": str(volume),
            "acml_tr_pbmn": str(trade_amount_raw)}


def _make_kis_investor_response(foreign_raw=150000000000.0, institution_raw=-80000000000.0,
                                individual_raw=-70000000000.0):
    return {"investor_summary": [{"frgn_ntby_tr_pbmn": str(foreign_raw),
            "orgn_ntby_tr_pbmn": str(institution_raw), "prsn_ntby_tr_pbmn": str(individual_raw)}]}


def _make_volume_rank_dataframe(n=3):
    stocks = [("005930", "삼성전자", 70000, 1.5, 12000000),
              ("000660", "SK하이닉스", 130000, 2.1, 8000000),
              ("035420", "NAVER", 200000, -0.5, 5000000)]
    data = [{"data_rank": i+1, "mksc_shrn_iscd": s[0], "hts_kor_isnm": s[1],
             "stck_prpr": s[2], "prdy_ctrt": s[3], "acml_vol": s[4]}
            for i, s in enumerate(stocks[:n])]
    return pd.DataFrame(data)


class TestModels:
    def test_index_data_creation(self):
        idx = IndexData(name="코스피", value=2500.0)
        assert idx.name == "코스피" and idx.value == 2500.0
        assert idx.change == 0.0 and idx.change_rate == 0.0
        assert idx.volume == 0 and idx.trade_amount == 0.0 and idx.timestamp is None

    def test_investor_flow_creation(self):
        f = InvestorFlow()
        assert f.foreign_net == 0.0 and f.institution_net == 0.0
        assert f.individual_net == 0.0 and f.timestamp is None

    def test_exchange_rate_creation(self):
        er = ExchangeRate(pair="USD/KRW", rate=1350.0)
        assert er.pair == "USD/KRW" and er.rate == 1350.0
        assert er.change == 0.0 and er.change_rate == 0.0 and er.timestamp is None

    def test_ranked_stock_creation(self):
        s = RankedStock(rank=1, stock_code="005930", stock_name="삼성전자")
        assert s.rank == 1 and s.stock_code == "005930" and s.stock_name == "삼성전자"
        assert s.current_price == 0.0 and s.change_rate == 0.0 and s.volume == 0

    def test_position_summary_creation(self):
        p = PositionSummary(stock_code="005930", stock_name="삼성전자",
                            quantity=10, avg_price=68000.0, current_price=70000.0)
        assert p.stock_code == "005930" and p.quantity == 10
        assert p.profit_loss == 0.0 and p.profit_loss_rate == 0.0 and p.state == ""

    def test_global_market_snapshot_default_empty(self):
        s = GlobalMarketSnapshot()
        assert s.indices == [] and s.exchange_rates == [] and s.timestamp is None

    def test_domestic_market_snapshot_default_none(self):
        s = DomesticMarketSnapshot()
        assert s.kospi is None and s.kosdaq is None and s.investor_flow is None
        assert s.volume_rank == [] and s.timestamp is None

    def test_premarket_briefing_creation(self):
        b = PremarketBriefing()
        assert b.global_market is None and b.domestic_prev_close is None and b.briefing_time is None

    def test_market_dashboard_data_creation(self):
        d = MarketDashboardData()
        assert d.domestic is None and d.positions == []
        assert d.total_profit_loss == 0.0 and d.total_eval_amount == 0.0 and d.dashboard_time is None


class TestGlobalMarketCollector:
    def test_cache_initially_invalid(self):
        assert GlobalMarketCollector(cache_ttl_seconds=300)._is_cache_valid() is False

    def test_cache_becomes_valid_after_fetch(self):
        c = GlobalMarketCollector(cache_ttl_seconds=300)
        with patch.dict("sys.modules", {"yfinance": None}):
            c.fetch_snapshot(use_cache=False)
        assert c._is_cache_valid() is True
        assert c._cache.get("snapshot") is not None

    def test_fetch_global_indices_yfinance_not_installed(self):
        c = GlobalMarketCollector()
        with patch.dict("sys.modules", {"yfinance": None}):
            assert c.fetch_global_indices() == []

    def test_fetch_exchange_rates_yfinance_not_installed(self):
        c = GlobalMarketCollector()
        with patch.dict("sys.modules", {"yfinance": None}):
            assert c.fetch_exchange_rates() == []

    def test_fetch_snapshot_uses_cache(self):
        c = GlobalMarketCollector(cache_ttl_seconds=300)
        cached = GlobalMarketSnapshot(indices=[_make_index_data(name="S&P 500", value=5000.0)],
                                      timestamp=datetime.now())
        c._cache["snapshot"] = cached
        c._cache_time = datetime.now()
        result = c.fetch_snapshot(use_cache=True)
        assert result is cached and len(result.indices) == 1
        assert result.indices[0].name == "S&P 500"

    def test_fetch_snapshot_bypasses_cache(self):
        c = GlobalMarketCollector(cache_ttl_seconds=300)
        old = GlobalMarketSnapshot(indices=[_make_index_data(name="OLD", value=1.0)],
                                   timestamp=datetime.now())
        c._cache["snapshot"] = old
        c._cache_time = datetime.now()
        with patch.dict("sys.modules", {"yfinance": None}):
            result = c.fetch_snapshot(use_cache=False)
        assert result is not old and result.indices == []

    def test_fetch_global_indices_success(self):
        c = GlobalMarketCollector()
        mock_yf = MagicMock()
        fi = MagicMock()
        fi.last_price = 5000.0
        fi.previous_close = 4950.0
        t = MagicMock()
        t.fast_info = fi
        mock_yf.Ticker.return_value = t
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = c.fetch_global_indices()
        assert len(result) == 6
        for idx in result:
            assert isinstance(idx, IndexData) and idx.value == 5000.0
            assert idx.change == 50.0 and abs(idx.change_rate - 1.01) < 0.01


class TestDomesticMarketCollector:
    def test_fetch_index_success(self):
        fn = Mock(return_value=_make_kis_index_response())
        c = DomesticMarketCollector(get_index_fn=fn)
        r = c.fetch_index("0001", "코스피")
        assert r is not None and isinstance(r, IndexData)
        assert r.name == "코스피" and r.value == 2500.0
        assert r.change == 15.0 and r.change_rate == 0.60
        assert r.volume == 500000 and r.trade_amount == 45000.0
        fn.assert_called_once_with("0001")

    def test_fetch_index_api_failure(self):
        fn = Mock(return_value=None)
        assert DomesticMarketCollector(get_index_fn=fn).fetch_index("0001", "코스피") is None

    def test_fetch_index_no_function(self):
        assert DomesticMarketCollector().fetch_index("0001", "코스피") is None

    def test_fetch_investor_flow_success(self):
        fn = Mock(return_value=_make_kis_investor_response(150000000000.0, -80000000000.0, -70000000000.0))
        r = DomesticMarketCollector(get_investor_flow_fn=fn).fetch_investor_flow()
        assert r is not None and isinstance(r, InvestorFlow)
        assert r.foreign_net == 1500.0 and r.institution_net == -800.0 and r.individual_net == -700.0

    def test_fetch_investor_flow_failure(self):
        fn = Mock(return_value=None)
        assert DomesticMarketCollector(get_investor_flow_fn=fn).fetch_investor_flow() is None

    def test_fetch_volume_rank_success(self):
        fn = Mock(return_value=_make_volume_rank_dataframe(n=3))
        r = DomesticMarketCollector(get_volume_rank_fn=fn).fetch_volume_rank(top_n=10)
        assert len(r) == 3 and isinstance(r[0], RankedStock)
        assert r[0].rank == 1 and r[0].stock_code == "005930" and r[0].stock_name == "삼성전자"
        assert r[0].current_price == 70000.0 and r[0].change_rate == 1.5 and r[0].volume == 12000000
        assert r[1].stock_code == "000660" and r[2].stock_code == "035420"

    def test_fetch_volume_rank_empty(self):
        fn = Mock(return_value=pd.DataFrame())
        assert DomesticMarketCollector(get_volume_rank_fn=fn).fetch_volume_rank() == []

    def test_fetch_snapshot_combines_all(self):
        ifn = Mock(return_value=_make_kis_index_response())
        ffn = Mock(return_value=_make_kis_investor_response())
        rfn = Mock(return_value=_make_volume_rank_dataframe())
        c = DomesticMarketCollector(get_index_fn=ifn, get_investor_flow_fn=ffn, get_volume_rank_fn=rfn)
        s = c.fetch_snapshot(use_cache=False)
        assert isinstance(s, DomesticMarketSnapshot)
        assert s.kospi is not None and s.kospi.name == "코스피"
        assert s.kosdaq is not None and s.kosdaq.name == "코스닥"
        assert s.investor_flow is not None and len(s.volume_rank) == 3
        assert ifn.call_count == 2
        ffn.assert_called_once()
        rfn.assert_called_once()

    def test_cache_works(self):
        ifn = Mock(return_value=_make_kis_index_response())
        ffn = Mock(return_value=_make_kis_investor_response())
        rfn = Mock(return_value=_make_volume_rank_dataframe())
        c = DomesticMarketCollector(get_index_fn=ifn, get_investor_flow_fn=ffn,
                                    get_volume_rank_fn=rfn, cache_ttl_seconds=300)
        s1 = c.fetch_snapshot(use_cache=True)
        assert ifn.call_count == 2 and ffn.call_count == 1 and rfn.call_count == 1
        s2 = c.fetch_snapshot(use_cache=True)
        assert ifn.call_count == 2 and ffn.call_count == 1 and rfn.call_count == 1
        assert s1 is s2

    def test_from_kis_api_import_failure(self):
        with patch.dict("sys.modules", {"api": None, "api.kis_market_api": None}):
            with pytest.raises((ImportError, ModuleNotFoundError, TypeError)):
                DomesticMarketCollector.from_kis_api()


class TestConsoleFormatter:
    def test_format_premarket_briefing_full(self):
        gs = GlobalMarketSnapshot(
            indices=[_make_index_data(name="S&P 500", value=5000.0, change=25.0, change_rate=0.50),
                     _make_index_data(name="NASDAQ", value=16000.0, change=-50.0, change_rate=-0.31)],
            exchange_rates=[_make_exchange_rate(pair="USD/KRW", rate=1350.50, change=-2.30, change_rate=-0.17)])
        ds = DomesticMarketSnapshot(
            kospi=_make_index_data(name="코스피", value=2500.0, change=15.0, change_rate=0.60),
            kosdaq=_make_index_data(name="코스닥", value=800.0, change=-3.0, change_rate=-0.37))
        b = PremarketBriefing(global_market=gs, domestic_prev_close=ds,
                              briefing_time=datetime(2026, 2, 22, 8, 30, 0))
        r = ConsoleFormatter.format_premarket_briefing(b)
        assert "장전 브리핑" in r and "2026-02-22 08:30:00" in r
        assert "[해외시장]" in r and "S&P 500" in r and "NASDAQ" in r
        assert "[환율]" in r and "USD/KRW" in r
        assert "[전일 국내시장]" in r and "KOSPI" in r and "KOSDAQ" in r

    def test_format_premarket_briefing_empty(self):
        r = ConsoleFormatter.format_premarket_briefing(
            PremarketBriefing(briefing_time=datetime(2026, 2, 22, 8, 30, 0)))
        assert "장전 브리핑" in r
        assert "[해외시장]" not in r and "[환율]" not in r and "[전일 국내시장]" not in r

    def test_format_premarket_briefing_partial(self):
        gs = GlobalMarketSnapshot(
            indices=[_make_index_data(name="S&P 500", value=5000.0, change=25.0, change_rate=0.50)])
        r = ConsoleFormatter.format_premarket_briefing(
            PremarketBriefing(global_market=gs, briefing_time=datetime(2026, 2, 22, 8, 30, 0)))
        assert "[해외시장]" in r and "S&P 500" in r
        assert "[환율]" not in r and "[전일 국내시장]" not in r

    def test_format_dashboard_full(self):
        ds = DomesticMarketSnapshot(
            kospi=_make_index_data(name="코스피", value=2500.0, change=15.0,
                                   change_rate=0.60, trade_amount=45000.0),
            kosdaq=_make_index_data(name="코스닥", value=800.0, change=-3.0,
                                   change_rate=-0.37, trade_amount=12000.0),
            investor_flow=_make_investor_flow(1500.0, -800.0, -700.0),
            volume_rank=[_make_ranked_stock(1, "005930", "삼성전자", 70000.0, 1.50, 12000000),
                         _make_ranked_stock(2, "000660", "SK하이닉스", 130000.0, 2.10, 8000000)])
        pos = [_make_position_summary("005930", "삼성전자", 10, 68000.0, 70000.0, 20000, 2.94)]
        d = MarketDashboardData(domestic=ds, positions=pos,
                                total_profit_loss=20000.0, total_eval_amount=700000.0,
                                dashboard_time=datetime(2026, 2, 22, 10, 30, 0))
        r = ConsoleFormatter.format_dashboard(d)
        assert "시장현황 대시보드" in r and "2026-02-22 10:30:00" in r
        assert "[시장 지수]" in r and "KOSPI" in r and "KOSDAQ" in r
        assert "4.5조" in r
        assert "[투자자별 동향]" in r and "외국인" in r and "기관" in r and "개인" in r
        assert "[거래량 상위]" in r and "삼성전자" in r and "SK하이닉스" in r
        assert "[보유 포지션]" in r and "1종목" in r and "합계" in r

    def test_format_dashboard_empty(self):
        r = ConsoleFormatter.format_dashboard(
            MarketDashboardData(dashboard_time=datetime(2026, 2, 22, 10, 30, 0)))
        assert "시장현황 대시보드" in r and "[시장 지수]" not in r
        assert "[보유 포지션] 없음" in r

    def test_format_dashboard_no_positions(self):
        r = ConsoleFormatter.format_dashboard(
            MarketDashboardData(positions=[], dashboard_time=datetime(2026, 2, 22, 10, 30, 0)))
        assert "[보유 포지션] 없음" in r

    def test_format_negative_values(self):
        ds = DomesticMarketSnapshot(
            kospi=_make_index_data(name="코스피", value=2400.0, change=-50.0, change_rate=-2.04))
        r = ConsoleFormatter.format_dashboard(
            MarketDashboardData(domestic=ds, dashboard_time=datetime(2026, 2, 22, 10, 30, 0)))
        assert "-50.00" in r and "-2.04%" in r

    def test_format_large_trade_amount(self):
        ds = DomesticMarketSnapshot(
            kospi=_make_index_data(name="코스피", value=2500.0, trade_amount=45000.0))
        r = ConsoleFormatter.format_dashboard(
            MarketDashboardData(domestic=ds, dashboard_time=datetime(2026, 2, 22, 10, 30, 0)))
        assert "4.5조" in r


class TestMarketDashboard:
    def test_generate_premarket_briefing(self):
        md = Mock(spec=DomesticMarketCollector)
        md.fetch_snapshot.return_value = DomesticMarketSnapshot(
            kospi=_make_index_data(name="코스피", value=2500.0))
        mg = Mock(spec=GlobalMarketCollector)
        mg.fetch_snapshot.return_value = GlobalMarketSnapshot(
            indices=[_make_index_data(name="S&P 500", value=5000.0)])
        db = MarketDashboard(domestic_collector=md, global_collector=mg)
        r = db.generate_premarket_briefing()
        assert r != "" and "장전 브리핑" in r and "S&P 500" in r
        mg.fetch_snapshot.assert_called_once()
        md.fetch_snapshot.assert_called_once_with(use_cache=False)

    def test_briefing_once_per_day(self):
        md = Mock(spec=DomesticMarketCollector)
        md.fetch_snapshot.return_value = DomesticMarketSnapshot()
        mg = Mock(spec=GlobalMarketCollector)
        mg.fetch_snapshot.return_value = GlobalMarketSnapshot()
        db = MarketDashboard(domestic_collector=md, global_collector=mg)
        assert db.generate_premarket_briefing() != ""
        assert db.generate_premarket_briefing() == ""
        assert db.is_briefing_done_today() is True

    def test_generate_dashboard(self):
        md = Mock(spec=DomesticMarketCollector)
        md.fetch_snapshot.return_value = DomesticMarketSnapshot(
            kospi=_make_index_data(name="코스피", value=2500.0, trade_amount=45000.0),
            kosdaq=_make_index_data(name="코스닥", value=800.0, trade_amount=12000.0),
            investor_flow=_make_investor_flow(), volume_rank=[_make_ranked_stock()])
        pfn = Mock(return_value=[_make_position_summary("005930", "삼성전자", 10, 68000.0, 70000.0, 20000.0, 2.94)])
        db = MarketDashboard(domestic_collector=md, position_fn=pfn)
        r = db.generate_dashboard()
        assert r != "" and "시장현황 대시보드" in r and "KOSPI" in r
        assert "삼성전자" in r and "[보유 포지션]" in r and "1종목" in r
        md.fetch_snapshot.assert_called_once()
        pfn.assert_called_once()

    def test_dashboard_error_handling(self):
        db = MarketDashboard()
        with patch.object(ConsoleFormatter, "format_dashboard", side_effect=Exception("crash")):
            assert db.generate_dashboard() == ""

    def test_position_fn_callback(self):
        pos = [_make_position_summary("005930", "삼성전자", 10, 68000.0, 70000.0, 20000.0, 2.94),
               _make_position_summary("000660", "SK하이닉스", 5, 125000.0, 130000.0, 25000.0, 4.0)]
        pfn = Mock(return_value=pos)
        md = Mock(spec=DomesticMarketCollector)
        md.fetch_snapshot.return_value = DomesticMarketSnapshot()
        db = MarketDashboard(domestic_collector=md, position_fn=pfn)
        r = db.generate_dashboard()
        pfn.assert_called_once()
        assert "+45,000" in r and "1,350,000" in r

    def test_no_collectors(self):
        db = MarketDashboard()
        assert db._domestic is not None and db._global is not None and db._position_fn is None
        r = db.generate_dashboard()
        assert isinstance(r, str) and "시장현황 대시보드" in r and "[보유 포지션] 없음" in r
