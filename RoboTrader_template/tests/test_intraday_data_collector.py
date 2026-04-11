"""
IntradayDataCollector 유닛 테스트

테스트 대상: core/intraday/data_collector.py
- collect_daily_data_only: 리밸런싱 모드 일봉 수집
- collect_historical_data: 당일 전체 분봉 수집
- _filter_today_data: 당일 데이터 필터링
- _sort_and_filter_by_time: 시간순 정렬 및 선정 시점 이전 필터링
- collect_historical_data_fallback: 폴백 방식 수집
"""

import pytest
import asyncio
import threading
import pandas as pd
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

KST = timezone(timedelta(hours=9))


def _make_selected_time(hour=10, minute=30, second=0):
    """KST 기준 선정 시각 생성"""
    return datetime(2024, 1, 15, hour, minute, second, tzinfo=KST)


def _make_minute_df(n_rows=20, today_str="20240115", start_hour=9, start_min=0):
    """분봉 DataFrame 생성 (datetime 컬럼 포함)"""
    base = datetime(2024, 1, 15, start_hour, start_min)
    rows = []
    for i in range(n_rows):
        dt = base + timedelta(minutes=i)
        rows.append({
            'datetime': dt,
            'date': today_str,
            'time': dt.strftime('%H%M%S'),
            'open': 50000,
            'high': 50500,
            'low': 49500,
            'close': 50200,
            'volume': 10000,
        })
    return pd.DataFrame(rows)


def _make_daily_df(n_rows=30):
    """일봉 DataFrame 생성"""
    rows = []
    for i in range(n_rows):
        rows.append({
            'date': f'202401{i+1:02d}',
            'open': 50000,
            'high': 51000,
            'low': 49000,
            'close': 50500,
            'volume': 500000,
        })
    return pd.DataFrame(rows)


def _make_collector(broker=None, selected_stocks=None):
    """최소 의존성 IntradayDataCollector 생성"""
    from core.intraday.data_collector import IntradayDataCollector

    manager = Mock()
    manager._lock = threading.Lock()
    manager.broker = broker or Mock()
    manager.selected_stocks = selected_stocks or {}

    collector = IntradayDataCollector.__new__(IntradayDataCollector)
    collector.manager = manager
    collector.broker = manager.broker
    collector.logger = Mock()

    return collector, manager


def _make_stock_data(stock_code="005930", hour=10, minute=30):
    """StockMinuteData 인스턴스 생성"""
    from core.intraday.models import StockMinuteData
    return StockMinuteData(
        stock_code=stock_code,
        stock_name="삼성전자",
        selected_time=_make_selected_time(hour, minute),
    )


# ---------------------------------------------------------------------------
# collect_daily_data_only
# ---------------------------------------------------------------------------

class TestCollectDailyDataOnly:
    """collect_daily_data_only: 리밸런싱 모드 일봉 수집 테스트"""

    @pytest.mark.asyncio
    async def test_returns_true_when_daily_data_collected_successfully(self):
        """일봉 데이터 정상 수집 시 True 반환"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)
        daily_df = _make_daily_df(30)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data
        manager.broker.get_ohlcv_data.return_value = daily_df

        with patch.object(collector, '_save_daily_to_db', new=AsyncMock(return_value=True)):
            result = await collector.collect_daily_data_only(stock_code)

        assert result is True

    @pytest.mark.asyncio
    async def test_stores_daily_data_in_manager_memory(self):
        """수집 성공 시 manager.selected_stocks에 daily_data가 저장된다"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)
        daily_df = _make_daily_df(30)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data
        manager.broker.get_ohlcv_data.return_value = daily_df

        with patch.object(collector, '_save_daily_to_db', new=AsyncMock(return_value=True)):
            await collector.collect_daily_data_only(stock_code)

        assert not manager.selected_stocks[stock_code].daily_data.empty
        assert manager.selected_stocks[stock_code].data_complete is True

    @pytest.mark.asyncio
    async def test_returns_false_when_stock_not_in_selected_stocks(self):
        """selected_stocks에 없는 종목이면 False 반환"""
        collector, _ = _make_collector()
        result = await collector.collect_daily_data_only("999999")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_and_removes_stock_when_api_returns_none(self):
        """API가 None 반환 시 False 반환 및 종목 삭제"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data
        manager.broker.get_ohlcv_data.return_value = None

        result = await collector.collect_daily_data_only(stock_code)

        assert result is False
        assert stock_code not in manager.selected_stocks

    @pytest.mark.asyncio
    async def test_returns_false_and_removes_stock_when_api_returns_empty_dataframe(self):
        """API가 빈 DataFrame 반환 시 False 반환 및 종목 삭제"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data
        manager.broker.get_ohlcv_data.return_value = pd.DataFrame()

        result = await collector.collect_daily_data_only(stock_code)

        assert result is False
        assert stock_code not in manager.selected_stocks

    @pytest.mark.asyncio
    async def test_marks_historical_data_as_empty_dataframe(self):
        """리밸런싱 모드이므로 historical_data는 빈 DataFrame으로 설정된다"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)
        daily_df = _make_daily_df(30)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data
        manager.broker.get_ohlcv_data.return_value = daily_df

        with patch.object(collector, '_save_daily_to_db', new=AsyncMock(return_value=True)):
            await collector.collect_daily_data_only(stock_code)

        assert manager.selected_stocks[stock_code].historical_data.empty is True

    @pytest.mark.asyncio
    async def test_returns_false_when_exception_is_raised(self):
        """예외 발생 시 False 반환 및 종목 삭제"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data
        manager.broker.get_ohlcv_data.side_effect = RuntimeError("API 오류")

        result = await collector.collect_daily_data_only(stock_code)

        assert result is False
        assert stock_code not in manager.selected_stocks


# ---------------------------------------------------------------------------
# _filter_today_data
# ---------------------------------------------------------------------------

class TestFilterTodayData:
    """_filter_today_data: 당일 데이터만 필터링 테스트"""

    def test_filters_rows_by_date_column(self):
        """date 컬럼이 있을 때 오늘 날짜 행만 남긴다"""
        collector, _ = _make_collector()
        selected_time = _make_selected_time(10, 30)

        df = pd.DataFrame({
            'date': ['20240114', '20240115', '20240115', '20240116'],
            'close': [100, 200, 300, 400],
        })
        result = collector._filter_today_data(df, selected_time)

        assert len(result) == 2
        assert all(result['date'] == '20240115')

    def test_filters_rows_by_datetime_column_when_no_date_column(self):
        """date 컬럼 없이 datetime 컬럼으로 당일 필터링"""
        collector, _ = _make_collector()
        selected_time = _make_selected_time(10, 30)

        df = pd.DataFrame({
            'datetime': [
                datetime(2024, 1, 14, 9, 0),
                datetime(2024, 1, 15, 9, 0),
                datetime(2024, 1, 15, 10, 0),
            ],
            'close': [100, 200, 300],
        })
        result = collector._filter_today_data(df, selected_time)

        assert len(result) == 2

    def test_returns_empty_dataframe_when_no_matching_date(self):
        """당일 데이터가 없으면 빈 DataFrame 반환"""
        collector, _ = _make_collector()
        selected_time = _make_selected_time(10, 30)

        df = pd.DataFrame({
            'date': ['20240114', '20240113'],
            'close': [100, 200],
        })
        result = collector._filter_today_data(df, selected_time)

        assert result.empty


# ---------------------------------------------------------------------------
# _sort_and_filter_by_time
# ---------------------------------------------------------------------------

class TestSortAndFilterByTime:
    """_sort_and_filter_by_time: 시간순 정렬 및 선정 시점 이전 필터링 테스트"""

    def test_filters_datetime_column_before_selected_time(self):
        """datetime 컬럼 기준으로 선정 시각 이전 데이터만 남긴다"""
        collector, _ = _make_collector()
        selected_time = _make_selected_time(10, 30)  # KST 10:30

        df = pd.DataFrame({
            'datetime': [
                datetime(2024, 1, 15, 9, 0),
                datetime(2024, 1, 15, 10, 0),
                datetime(2024, 1, 15, 10, 30),   # 경계값 포함
                datetime(2024, 1, 15, 11, 0),    # 제외
            ],
            'close': [100, 200, 300, 400],
        })
        result = collector._sort_and_filter_by_time(df, selected_time)

        assert len(result) == 3
        assert 400 not in result['close'].values

    def test_filters_time_string_column_before_selected_time(self):
        """time 컬럼(HHMMSS 문자열) 기준 필터링"""
        collector, _ = _make_collector()
        selected_time = _make_selected_time(10, 30, 0)

        df = pd.DataFrame({
            'time': ['090000', '100000', '103000', '110000'],
            'close': [100, 200, 300, 400],
        })
        result = collector._sort_and_filter_by_time(df, selected_time)

        assert len(result) == 3

    def test_returns_sorted_dataframe_ascending(self):
        """결과가 시간 오름차순으로 정렬된다"""
        collector, _ = _make_collector()
        selected_time = _make_selected_time(15, 0)

        df = pd.DataFrame({
            'datetime': [
                datetime(2024, 1, 15, 11, 0),
                datetime(2024, 1, 15, 9, 0),
                datetime(2024, 1, 15, 10, 0),
            ],
            'close': [300, 100, 200],
        })
        result = collector._sort_and_filter_by_time(df, selected_time)

        assert list(result['close']) == [100, 200, 300]

    def test_returns_copy_of_data_when_no_time_column(self):
        """datetime/time 컬럼이 없으면 원본 복사본 반환"""
        collector, _ = _make_collector()
        selected_time = _make_selected_time(10, 30)

        df = pd.DataFrame({'close': [100, 200]})
        result = collector._sort_and_filter_by_time(df, selected_time)

        assert list(result['close']) == [100, 200]


# ---------------------------------------------------------------------------
# collect_historical_data_fallback
# ---------------------------------------------------------------------------

class TestCollectHistoricalDataFallback:
    """collect_historical_data_fallback: API 폴백 수집 테스트"""

    @pytest.mark.asyncio
    async def test_returns_false_when_stock_not_in_selected_stocks(self):
        """selected_stocks에 없는 종목 요청 시 False 반환"""
        collector, _ = _make_collector()
        result = await collector.collect_historical_data_fallback("999999")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_and_stores_data_when_api_succeeds(self):
        """API 성공 시 True 반환 및 데이터 저장"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)
        minute_df = _make_minute_df(20)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data

        summary_mock = Mock()
        chart_df = minute_df.copy()
        chart_df['datetime'] = [
            datetime(2024, 1, 15, 9, i) for i in range(20)
        ]

        with patch(
            'core.intraday.data_collector.get_div_code_for_stock', return_value='J'
        ), patch(
            'core.intraday.data_collector.get_inquire_time_itemchartprice',
            return_value=(summary_mock, chart_df)
        ):
            result = await collector.collect_historical_data_fallback(stock_code)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_with_empty_data_when_chart_df_is_empty(self):
        """차트 데이터가 비어있어도 data_complete=True로 처리하고 True 반환"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data

        summary_mock = Mock()

        with patch(
            'core.intraday.data_collector.get_div_code_for_stock', return_value='J'
        ), patch(
            'core.intraday.data_collector.get_inquire_time_itemchartprice',
            return_value=(summary_mock, pd.DataFrame())
        ):
            result = await collector.collect_historical_data_fallback(stock_code)

        assert result is True
        assert manager.selected_stocks[stock_code].data_complete is True

    @pytest.mark.asyncio
    async def test_returns_false_when_api_returns_none_and_retry_also_fails(self):
        """API 실패 및 재시도도 실패하면 False 반환"""
        stock_code = "005930"
        stock_data = _make_stock_data(stock_code)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data

        with patch(
            'core.intraday.data_collector.get_div_code_for_stock', return_value='J'
        ), patch(
            'core.intraday.data_collector.get_inquire_time_itemchartprice',
            return_value=None
        ):
            result = await collector.collect_historical_data_fallback(stock_code)

        assert result is False

    @pytest.mark.asyncio
    async def test_filters_chart_data_to_before_selected_time(self):
        """수집된 분봉 데이터는 선정 시각 이전 데이터만 저장된다"""
        stock_code = "005930"
        selected_time = _make_selected_time(10, 15)
        stock_data = _make_stock_data(stock_code, hour=10, minute=15)

        collector, manager = _make_collector()
        manager.selected_stocks[stock_code] = stock_data

        # 선정 시각(10:15) 이후 데이터 포함
        datetimes = [datetime(2024, 1, 15, 9, i * 5) for i in range(6)]
        # 09:00, 09:05, 09:10, 09:15, 09:20, 09:25 — 전부 이전
        chart_df = pd.DataFrame({
            'datetime': datetimes,
            'close': [100, 110, 120, 130, 140, 150],
        })

        summary_mock = Mock()
        with patch(
            'core.intraday.data_collector.get_div_code_for_stock', return_value='J'
        ), patch(
            'core.intraday.data_collector.get_inquire_time_itemchartprice',
            return_value=(summary_mock, chart_df)
        ):
            result = await collector.collect_historical_data_fallback(stock_code)

        assert result is True
        stored = manager.selected_stocks[stock_code].historical_data
        # 선정 시각(10:15) 이전 데이터만 남아야 함
        assert all(
            pd.to_datetime(stored['datetime']) <= pd.to_datetime(selected_time.replace(tzinfo=None))
        )
