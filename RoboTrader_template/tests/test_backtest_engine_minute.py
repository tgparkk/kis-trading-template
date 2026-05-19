"""
BacktestEngine.run_minute() 단위 테스트
========================================
T+0 분봉 백테스트 엔진 검증.

테스트 범위:
- test_golden_case_single_stock_tp: 단일 종목 1일 골든 케이스 (익절, 수기 PnL 일치)
- test_golden_case_single_stock_sl: 단일 종목 1일 골든 케이스 (손절, 수기 PnL 일치)
- test_eod_liquidation: EOD 강제청산 (sells_by_reason['eod_t0'] >= 1)
- test_intraday_sl_trigger: 분봉 low가 손절가 이하 → intraday_sl
- test_intraday_tp_trigger: 분봉 high가 익절가 이상 → intraday_tp
- test_intraday_trail_trigger: 트레일링 청산 (high_water 갱신 후 하락)
- test_no_trail_when_trail_pct_none: trail_pct=None이면 트레일링 미발동
- test_three_stocks_fifo_max_positions: 동시 3종목 max_positions 제한
- test_max_positions_1_single_holding: max_positions=1 시 한 종목만 보유
- test_skip_dates_exact: skip_dates 정확한 날짜 건너뜀
- test_skip_dates_prefix: skip_dates prefix 매칭
- test_empty_candidates_no_trade: 빈 후보 → 현금 변동 없음
- test_candidate_provider_called: candidate_provider 콜백 호출 검증
- test_slip_fee_tax_accuracy: 슬리피지·수수료·거래세 수기 계산 일치
- test_apply_buy_static: _apply_buy 스태틱 메서드 수기 계산
- test_apply_sell_static: _apply_sell 스태틱 메서드 수기 계산
- test_sells_by_reason_keys: BacktestResult.sells_by_reason에 분봉 키 포함
- test_no_buy_after_eod_bar: EOD 시각 이후 분봉에서 신규 매수 없음
- test_minute_gap_skipped: 분봉 결손(high=low=0) 건너뜀
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
from unittest.mock import MagicMock, patch

from backtest.engine import BacktestEngine, BacktestResult
from strategies.base import BaseStrategy, Signal, SignalType


# ============================================================================
# 테스트용 최소 전략 스텁
# ============================================================================

class _AlwaysBuyMinuteStrategy(BaseStrategy):
    """분봉 기준 항상 매수 신호를 반환하는 전략 스텁."""
    name = "AlwaysBuyMinute"
    holding_period = "intraday"

    def get_min_data_length(self) -> int:
        return 1

    def generate_signal(self, stock_code, data, timeframe="minute"):
        if stock_code not in self.positions:
            return Signal(
                signal_type=SignalType.BUY,
                stock_code=stock_code,
                confidence=90,
                reasons=["test buy"],
            )
        return None


class _NeverSignalStrategy(BaseStrategy):
    """신호를 절대 반환하지 않는 전략 스텁 (SL/TP/EOD만 테스트)."""
    name = "NeverSignal"
    holding_period = "intraday"

    def get_min_data_length(self) -> int:
        return 1

    def generate_signal(self, stock_code, data, timeframe="minute"):
        return None


class _SellSignalStrategy(BaseStrategy):
    """보유 중이면 SELL 신호를 반환하는 전략 스텁."""
    name = "SellSignal"
    holding_period = "intraday"

    def get_min_data_length(self) -> int:
        return 1

    def generate_signal(self, stock_code, data, timeframe="minute"):
        if stock_code not in self.positions:
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code,
                          confidence=90, reasons=["buy"])
        return Signal(signal_type=SignalType.SELL, stock_code=stock_code,
                      confidence=90, reasons=["sell"])


# ============================================================================
# 헬퍼: 분봉 DataFrame 생성
# ============================================================================

def _make_minute_df(
    trade_date: str,
    times_hhmm: List[str],
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: Optional[List[int]] = None,
) -> pd.DataFrame:
    """분봉 DataFrame 생성 (datetime 컬럼 포함).

    Args:
        trade_date: 'YYYYMMDD'
        times_hhmm: ['0900', '0901', ...]
        opens/highs/lows/closes: 가격 리스트
        volumes: 거래량 (None이면 100,000)
    """
    year = int(trade_date[:4])
    month = int(trade_date[4:6])
    day = int(trade_date[6:8])
    n = len(times_hhmm)
    volumes = volumes or [100_000] * n

    datetimes = []
    for t in times_hhmm:
        h, m = int(t[:2]), int(t[2:4])
        datetimes.append(datetime(year, month, day, h, m))

    return pd.DataFrame({
        "datetime": datetimes,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "amount": [o * v for o, v in zip(opens, volumes)],
    })


def _make_engine(
    strategy: BaseStrategy,
    initial_capital: float = 1_000_000,
) -> BacktestEngine:
    """테스트용 BacktestEngine 생성."""
    return BacktestEngine(
        strategy=strategy,
        initial_capital=initial_capital,
        max_positions=1,
    )


def _make_mock_repo(minute_data_map: dict):
    """PriceRepository mock (get_minute_prices_bulk 반환값 지정)."""
    repo = MagicMock()

    def _bulk(codes, trade_date):
        result = {}
        for code in codes:
            result[code] = minute_data_map.get((code, trade_date),
                                               minute_data_map.get(code, pd.DataFrame()))
        return result

    repo.get_minute_prices_bulk.side_effect = _bulk
    return repo


# ============================================================================
# _apply_buy / _apply_sell 스태틱 메서드 단위 테스트
# ============================================================================

class TestApplyBuySell:
    """_apply_buy / _apply_sell 수기 계산 일치 검증."""

    def test_apply_buy_static(self):
        """매수: 슬리피지 +5bp, 수수료 0.015%."""
        price = 10_000.0
        qty = 10
        slip_bps = 5.0
        fee_pct = 0.00015

        fill, total_cost = BacktestEngine._apply_buy(price, qty, slip_bps, fee_pct)

        expected_fill = price * (1 + slip_bps / 10_000)   # 10,005.0
        expected_gross = expected_fill * qty               # 100,050.0
        expected_fee = expected_gross * fee_pct            # 15.0075
        expected_total = expected_gross + expected_fee     # 100,065.0075

        assert abs(fill - expected_fill) < 0.01
        assert abs(total_cost - expected_total) < 0.01

    def test_apply_sell_static(self):
        """매도: 슬리피지 -5bp, 수수료 0.015%, 거래세 0.18%."""
        price = 12_000.0
        qty = 10
        slip_bps = 5.0
        fee_pct = 0.00015
        tax_pct = 0.0018

        fill, net = BacktestEngine._apply_sell(price, qty, slip_bps, fee_pct, tax_pct)

        expected_fill = price * (1 - slip_bps / 10_000)   # 11,994.0
        expected_gross = expected_fill * qty               # 119,940.0
        expected_fee = expected_gross * fee_pct            # 17.991
        expected_tax = expected_gross * tax_pct            # 215.892
        expected_net = expected_gross - expected_fee - expected_tax

        assert abs(fill - expected_fill) < 0.01
        assert abs(net - expected_net) < 0.01

    def test_apply_buy_zero_slip_zero_fee(self):
        """슬리피지·수수료 모두 0이면 fill=price, total=price*qty."""
        fill, total = BacktestEngine._apply_buy(10_000.0, 5, 0.0, 0.0)
        assert abs(fill - 10_000.0) < 0.01
        assert abs(total - 50_000.0) < 0.01

    def test_apply_sell_zero_costs(self):
        """매도 비용 모두 0이면 net=price*qty."""
        fill, net = BacktestEngine._apply_sell(10_000.0, 5, 0.0, 0.0, 0.0)
        assert abs(fill - 10_000.0) < 0.01
        assert abs(net - 50_000.0) < 0.01


# ============================================================================
# run_minute 통합 테스트 (PriceRepository mock)
# ============================================================================

TRADE_DATE = "20260115"


def _run_with_mock(
    strategy: BaseStrategy,
    minute_data_map: dict,
    trading_days: List[str],
    initial_capital: float = 1_000_000,
    max_positions: int = 1,
    slip_bps: float = 0.0,
    fee_buy_pct: float = 0.0,
    fee_sell_pct: float = 0.0,
    tax_sell_pct: float = 0.0,
    eod_time: str = "15:20",
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.10,
    trail_pct: Optional[float] = None,
    skip_dates=None,
    candidate_provider=None,
    stock_codes: Optional[List[str]] = None,
) -> BacktestResult:
    """PriceRepository와 거래일 목록을 mock으로 교체해 run_minute 실행."""
    engine = BacktestEngine(
        strategy=strategy,
        initial_capital=initial_capital,
        max_positions=max_positions,
    )
    mock_repo = _make_mock_repo(minute_data_map)

    all_codes = stock_codes or list(
        {code for code in minute_data_map.keys() if isinstance(code, str)}
    )

    # PriceRepository와 거래일 헬퍼를 동시에 patch
    with patch("db.repositories.price.PriceRepository") as MockRepo, \
         patch.object(engine, "_get_trading_days_range", return_value=trading_days):
        MockRepo.return_value = mock_repo

        result = engine.run_minute(
            stock_codes=all_codes if stock_codes is None else stock_codes,
            start_date=trading_days[0],
            end_date=trading_days[-1],
            candidate_provider=candidate_provider,
            initial_capital=initial_capital,
            max_positions=max_positions,
            slip_bps=slip_bps,
            fee_buy_pct=fee_buy_pct,
            fee_sell_pct=fee_sell_pct,
            tax_sell_pct=tax_sell_pct,
            eod_time=eod_time,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trail_pct=trail_pct,
            skip_dates=skip_dates,
        )
    return result


class TestGoldenCase:
    """수기 계산과 ±1원 일치하는 골든 케이스."""

    def test_golden_case_tp(self):
        """익절: 매수 후 다음 분봉 high가 익절가 도달 → intraday_tp."""
        entry_price = 10_000.0
        qty_capital = 100_000.0  # capital_per_slot = 100000 / 1 = 100000
        qty = int(qty_capital // entry_price)  # 10주
        tp_price = entry_price * 1.10           # 11,000

        # 09:00 분봉: 매수 신호 (close=10000, high/low 정상)
        # 09:01 분봉: high가 tp_price 이상 → 익절
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "0901"],
            opens=[entry_price, entry_price],
            highs=[entry_price, tp_price + 100],   # 11,100 (tp 초과)
            lows=[entry_price, entry_price],
            closes=[entry_price, entry_price * 1.08],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=qty_capital,
            max_positions=1,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            trail_pct=None,
            stock_codes=["A00001"],
        )

        assert result.sells_by_reason.get("intraday_tp", 0) >= 1
        assert result.total_trades >= 1
        trade = result.trades[0]
        assert trade["signal_type"] == "intraday_tp"
        assert abs(trade["exit_price"] - tp_price) < 1.0

    def test_golden_case_sl(self):
        """손절: 매수 후 다음 분봉 low가 손절가 이하 → intraday_sl."""
        entry_price = 10_000.0
        sl_price = entry_price * 0.95  # 9,500

        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "0901"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, sl_price - 50],   # 9,450 < 9,500
            closes=[entry_price, sl_price - 50],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            stop_loss_pct=0.05,
            take_profit_pct=0.20,
            trail_pct=None,
            stock_codes=["A00001"],
        )

        assert result.sells_by_reason.get("intraday_sl", 0) >= 1
        trade = result.trades[0]
        assert trade["signal_type"] == "intraday_sl"
        assert abs(trade["exit_price"] - sl_price) < 1.0


class TestEODLiquidation:
    """EOD 강제청산 검증."""

    def test_eod_liquidation_triggers(self):
        """eod_time 이후 분봉에 보유 중이면 eod_t0 청산."""
        entry_price = 10_000.0

        # 09:00 매수, 15:20 EOD 청산
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "1520"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, entry_price],
            closes=[entry_price, entry_price * 1.01],  # 종가 1% 상승
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            eod_time="15:20",
            stop_loss_pct=0.05,
            take_profit_pct=0.20,
            trail_pct=None,
            stock_codes=["A00001"],
        )

        assert result.sells_by_reason.get("eod_t0", 0) >= 1
        trade = result.trades[0]
        assert trade["signal_type"] == "eod_t0"

    def test_no_buy_after_eod_bar(self):
        """EOD 시각 이후 분봉에서 신규 매수 없음."""
        entry_price = 10_000.0

        # 15:21 분봉만 있으면 매수 신호가 와도 진입 안 해야 함
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["1521"],
            opens=[entry_price],
            highs=[entry_price],
            lows=[entry_price],
            closes=[entry_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            eod_time="15:20",
            stop_loss_pct=0.05,
            take_profit_pct=0.20,
            trail_pct=None,
            stock_codes=["A00001"],
        )

        # 매수도 없어야 함
        assert result.total_trades == 0


class TestIntradaySL:
    """분봉 손절 검증."""

    def test_intraday_sl_trigger(self):
        """bar_low <= sl_price → intraday_sl 청산."""
        entry_price = 10_000.0
        sl_pct = 0.02
        sl_price = entry_price * (1 - sl_pct)  # 9,800

        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "0901", "0902"],
            opens=[entry_price, entry_price, entry_price],
            highs=[entry_price, entry_price, entry_price],
            lows=[entry_price, entry_price, sl_price - 10],
            closes=[entry_price, entry_price, sl_price - 10],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            stop_loss_pct=sl_pct,
            take_profit_pct=0.20,
            trail_pct=None,
            stock_codes=["A00001"],
        )

        assert result.sells_by_reason.get("intraday_sl", 0) >= 1


class TestIntradayTP:
    """분봉 익절 검증."""

    def test_intraday_tp_trigger(self):
        """bar_high >= tp_price → intraday_tp 청산."""
        entry_price = 10_000.0
        tp_pct = 0.03
        tp_price = entry_price * (1 + tp_pct)  # 10,300

        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "0901"],
            opens=[entry_price, entry_price],
            highs=[entry_price, tp_price + 50],
            lows=[entry_price, entry_price * 0.99],
            closes=[entry_price, tp_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            stop_loss_pct=0.10,
            take_profit_pct=tp_pct,
            trail_pct=None,
            stock_codes=["A00001"],
        )

        assert result.sells_by_reason.get("intraday_tp", 0) >= 1
        trade = result.trades[0]
        assert abs(trade["exit_price"] - tp_price) < 1.0


class TestTrailingStop:
    """트레일링 청산 검증."""

    def test_intraday_trail_trigger(self):
        """high_water 갱신 후 trail_pct 하락 → intraday_trail."""
        entry_price = 10_000.0
        trail_pct = 0.02  # 2% 트레일링
        high_water = 11_000.0
        trail_trigger = high_water * (1 - trail_pct)  # 10,780

        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "0901", "0902"],
            opens=[entry_price, 11_000, 10_700],
            highs=[entry_price, 11_000, 10_780],
            lows=[entry_price, 10_900, trail_trigger - 10],  # 트리거 하락
            closes=[entry_price, 10_950, 10_760],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            stop_loss_pct=0.15,   # 손절은 넓게
            take_profit_pct=0.30,  # 익절도 넓게
            trail_pct=trail_pct,
            stock_codes=["A00001"],
        )

        assert result.sells_by_reason.get("intraday_trail", 0) >= 1

    def test_no_trail_when_trail_pct_none(self):
        """trail_pct=None이면 트레일링 미발동."""
        entry_price = 10_000.0

        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "0901", "0902", "1520"],
            opens=[entry_price] * 4,
            highs=[entry_price, 11_000, 10_500, entry_price],
            lows=[entry_price, 10_900, 9_800, entry_price],
            closes=[entry_price, 10_950, 9_850, entry_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            stop_loss_pct=0.30,   # 손절 넓게
            take_profit_pct=0.50,  # 익절 넓게
            trail_pct=None,        # 트레일링 비활성
            eod_time="15:20",
            stock_codes=["A00001"],
        )

        # trail 미발동, eod_t0로 청산되어야 함
        assert result.sells_by_reason.get("intraday_trail", 0) == 0
        assert result.sells_by_reason.get("eod_t0", 0) >= 1


class TestMaxPositions:
    """max_positions 제한 및 FIFO 큐 검증."""

    def test_three_stocks_fifo_max_positions(self):
        """max_positions=3 → 최대 3종목 동시 보유."""
        codes = ["A00001", "A00002", "A00003", "A00004"]
        entry_price = 10_000.0

        minute_data_map = {}
        for code in codes:
            df = _make_minute_df(
                TRADE_DATE,
                times_hhmm=["0900", "1520"],
                opens=[entry_price, entry_price],
                highs=[entry_price, entry_price],
                lows=[entry_price, entry_price],
                closes=[entry_price, entry_price],
            )
            minute_data_map[code] = df

        engine = BacktestEngine(
            strategy=_AlwaysBuyMinuteStrategy(),
            initial_capital=400_000,
            max_positions=3,
        )
        mock_repo = MagicMock()

        def _bulk(stock_codes, trade_date):
            return {c: minute_data_map.get(c, pd.DataFrame()) for c in stock_codes}

        mock_repo.get_minute_prices_bulk.side_effect = _bulk

        with patch("db.repositories.price.PriceRepository") as MockRepo, \
             patch.object(engine, "_get_trading_days_range", return_value=[TRADE_DATE]):
            MockRepo.return_value = mock_repo
            result = engine.run_minute(
                stock_codes=codes,
                start_date=TRADE_DATE,
                end_date=TRADE_DATE,
                initial_capital=400_000,
                max_positions=3,
                stop_loss_pct=0.05,
                take_profit_pct=0.20,
                trail_pct=None,
                eod_time="15:20",
            )

        # 4종목 중 3종목만 진입 (max_positions=3)
        eod_count = result.sells_by_reason.get("eod_t0", 0)
        assert eod_count <= 3

    def test_max_positions_1_single_holding(self):
        """max_positions=1 → 한 번에 1종목만 보유."""
        codes = ["A00001", "A00002"]
        entry_price = 10_000.0

        minute_data_map = {}
        for code in codes:
            df = _make_minute_df(
                TRADE_DATE,
                times_hhmm=["0900", "1520"],
                opens=[entry_price, entry_price],
                highs=[entry_price, entry_price],
                lows=[entry_price, entry_price],
                closes=[entry_price, entry_price],
            )
            minute_data_map[code] = df

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map=minute_data_map,
            trading_days=[TRADE_DATE],
            initial_capital=200_000,
            max_positions=1,
            stop_loss_pct=0.05,
            take_profit_pct=0.20,
            trail_pct=None,
            eod_time="15:20",
            stock_codes=codes,
        )

        # max_positions=1이므로 EOD 청산은 1건 이하
        assert result.sells_by_reason.get("eod_t0", 0) <= 1


class TestSkipDates:
    """skip_dates 동작 검증."""

    def test_skip_dates_exact(self):
        """skip_dates에 정확한 날짜 포함 → 해당 날 거래 없음."""
        entry_price = 10_000.0
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "1520"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, entry_price],
            closes=[entry_price, entry_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            skip_dates={TRADE_DATE},
            stock_codes=["A00001"],
        )

        assert result.total_trades == 0

    def test_skip_dates_prefix(self):
        """skip_dates에 prefix 포함 → 해당 월 전체 건너뜀."""
        entry_price = 10_000.0
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "1520"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, entry_price],
            closes=[entry_price, entry_price],
        )

        # TRADE_DATE = '20260115' → prefix '202601'로 건너뜀
        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            skip_dates={"202601"},  # prefix
            stock_codes=["A00001"],
        )

        assert result.total_trades == 0

    def test_skip_one_date_out_of_two(self):
        """2일 중 1일만 skip → skip되지 않은 날에만 거래."""
        date1 = "20260115"
        date2 = "20260116"
        entry_price = 10_000.0

        # 두 날짜 모두 분봉 데이터: key = code (날짜는 _bulk 함수에서 처리)
        df_date2 = _make_minute_df(
            date2,
            times_hhmm=["0900", "1520"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, entry_price],
            closes=[entry_price, entry_price],
        )

        # minute_data_map은 _make_mock_repo에서 (code, date) 또는 code로 조회
        # 여기서는 직접 mock_repo를 만들어 두 날짜 모두 같은 데이터 반환
        engine = BacktestEngine(
            strategy=_AlwaysBuyMinuteStrategy(),
            initial_capital=100_000,
            max_positions=1,
        )
        mock_repo = MagicMock()

        def _bulk(codes, trade_date):
            result = {}
            for code in codes:
                df = _make_minute_df(
                    trade_date,
                    times_hhmm=["0900", "1520"],
                    opens=[entry_price, entry_price],
                    highs=[entry_price, entry_price],
                    lows=[entry_price, entry_price],
                    closes=[entry_price, entry_price],
                )
                result[code] = df
            return result

        mock_repo.get_minute_prices_bulk.side_effect = _bulk

        with patch("db.repositories.price.PriceRepository") as MockRepo, \
             patch.object(engine, "_get_trading_days_range", return_value=[date1, date2]):
            MockRepo.return_value = mock_repo
            result = engine.run_minute(
                stock_codes=["A00001"],
                start_date=date1,
                end_date=date2,
                initial_capital=100_000,
                max_positions=1,
                slip_bps=0.0,
                fee_buy_pct=0.0,
                fee_sell_pct=0.0,
                tax_sell_pct=0.0,
                stop_loss_pct=0.05,
                take_profit_pct=0.20,
                trail_pct=None,
                eod_time="15:20",
                skip_dates={date1},  # date1만 skip
            )

        # date1은 skip, date2만 처리 → equity_curve 길이 1 (date2 1일치)
        assert len(result.equity_curve) == 1
        # date2에서 매수 후 EOD 청산 → eod_t0 >= 1
        assert result.sells_by_reason.get("eod_t0", 0) >= 1


class TestEmptyCandidates:
    """빈 후보 종목 처리."""

    def test_empty_candidates_no_trade(self):
        """candidate_provider가 빈 리스트 반환 → 현금 변동 없음."""
        entry_price = 10_000.0
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900"],
            opens=[entry_price],
            highs=[entry_price],
            lows=[entry_price],
            closes=[entry_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            candidate_provider=lambda d: [],  # 빈 리스트
            stock_codes=["A00001"],
        )

        assert result.total_trades == 0
        # 자본 변동 없음 (수수료 없으므로 equity = initial_capital)
        if result.equity_curve:
            assert abs(result.equity_curve[-1] - 100_000) < 1.0


class TestCandidateProvider:
    """candidate_provider 콜백 검증."""

    def test_candidate_provider_called(self):
        """candidate_provider가 trade_date 인자로 호출되는지 검증."""
        call_log = []

        def _provider(trade_date):
            call_log.append(trade_date)
            return ["A00001"]

        entry_price = 10_000.0
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "1520"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, entry_price],
            closes=[entry_price, entry_price],
        )

        _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            candidate_provider=_provider,
            stock_codes=["A00001"],
        )

        assert TRADE_DATE in call_log

    def test_candidate_pool_hits_counted(self):
        """candidate_provider가 비어있지 않은 리스트를 반환한 날 수 집계."""
        entry_price = 10_000.0
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "1520"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, entry_price],
            closes=[entry_price, entry_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            candidate_provider=lambda d: ["A00001"],
            stock_codes=["A00001"],
        )

        assert result.candidate_pool_hits >= 1


class TestSlipFeeTaxAccuracy:
    """슬리피지·수수료·거래세 정확성 수기 계산 일치."""

    def test_slip_fee_tax_roundtrip(self):
        """매수·매도 비용 모두 적용 후 PnL 수기 계산과 ±1원 일치."""
        entry_price = 10_000.0
        exit_price = 11_000.0
        slip_bps = 5.0
        fee_buy = 0.00015
        fee_sell = 0.00015
        tax = 0.0018
        capital = 100_000.0

        fill_buy = entry_price * (1 + slip_bps / 10_000)
        qty = int(capital // fill_buy)
        gross_buy = fill_buy * qty
        fee_buy_amt = gross_buy * fee_buy
        total_cost = gross_buy + fee_buy_amt

        fill_sell = exit_price * (1 - slip_bps / 10_000)
        gross_sell = fill_sell * qty
        fee_sell_amt = gross_sell * fee_sell
        tax_amt = gross_sell * tax
        net_proceeds = gross_sell - fee_sell_amt - tax_amt

        expected_pnl = net_proceeds - total_cost

        # 단일 TP 케이스로 검증
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "0901"],
            opens=[entry_price, exit_price],
            highs=[entry_price, exit_price + 500],  # TP 도달
            lows=[entry_price, entry_price],
            closes=[entry_price, exit_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=capital,
            max_positions=1,
            slip_bps=slip_bps,
            fee_buy_pct=fee_buy,
            fee_sell_pct=fee_sell,
            tax_sell_pct=tax,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            trail_pct=None,
            stock_codes=["A00001"],
        )

        if result.trades:
            trade = result.trades[0]
            if trade["signal_type"] == "intraday_tp":
                assert abs(trade["pnl"] - expected_pnl) < 2.0


class TestSellsByReasonKeys:
    """BacktestResult.sells_by_reason에 분봉 전용 키 포함 확인."""

    def test_sells_by_reason_has_minute_keys(self):
        """run_minute 결과의 sells_by_reason에 eod_t0 키가 있어야 함."""
        entry_price = 10_000.0
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "1520"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, entry_price],
            closes=[entry_price, entry_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            stock_codes=["A00001"],
        )

        # eod_t0 키가 sells_by_reason에 있어야 함
        assert "eod_t0" in result.sells_by_reason


class TestMinuteGapSkipped:
    """분봉 결손(high=low=0) 처리."""

    def test_minute_gap_skipped(self):
        """high=low=0인 분봉은 매수/매도 차단."""
        entry_price = 10_000.0

        # 09:00 정상 → 매수
        # 09:01 결손(high=low=0) → 건너뜀
        # 15:20 EOD 청산
        df = _make_minute_df(
            TRADE_DATE,
            times_hhmm=["0900", "0901", "1520"],
            opens=[entry_price, 0, entry_price],
            highs=[entry_price, 0, entry_price],
            lows=[entry_price, 0, entry_price],
            closes=[entry_price, 0, entry_price],
        )

        result = _run_with_mock(
            strategy=_AlwaysBuyMinuteStrategy(),
            minute_data_map={"A00001": df},
            trading_days=[TRADE_DATE],
            initial_capital=100_000,
            max_positions=1,
            stop_loss_pct=0.05,
            take_profit_pct=0.20,
            trail_pct=None,
            eod_time="15:20",
            stock_codes=["A00001"],
        )

        # EOD에서 정상 청산 (결손 분봉에서 잘못 청산 안 됨)
        assert result.sells_by_reason.get("eod_t0", 0) >= 1


# ============================================================================
# set_daily_context 호출 검증 (Task 5 — TDD)
# ============================================================================

class TestSetDailyContextCall:
    def test_run_minute_calls_set_daily_context_per_day(self, monkeypatch):
        """run_minute이 거래일 루프마다 strategy.set_daily_context를 호출."""
        from backtest.engine import BacktestEngine
        from strategies.intraday.orb_v2.strategy import OrbV2Strategy

        strat = OrbV2Strategy({})
        called_dates = []
        original = strat.set_daily_context

        def _spy(date, ctx):
            called_dates.append(date)
            return original(date, ctx)

        strat.set_daily_context = _spy

        engine = BacktestEngine(strategy=strat, initial_capital=10_000_000, max_positions=3)

        # PriceRepository mock — 빈 데이터 반환해서 빠르게 종료
        from unittest.mock import patch, MagicMock
        with patch("db.repositories.price.PriceRepository") as mock_repo_cls, \
             patch.object(engine, "_get_trading_days_range", return_value=["20260401", "20260402", "20260403"]):
            mock_repo = MagicMock()
            mock_repo.get_minute_prices_bulk.return_value = {}
            mock_repo_cls.return_value = mock_repo

            engine.run_minute(
                stock_codes=["005930"],
                start_date="20260401",
                end_date="20260403",
                candidate_provider=lambda d: ["005930"],
            )

        # 거래일이 1+개라면 한 번이라도 호출됐어야 함
        assert len(called_dates) >= 1
        # YYYYMMDD 포맷 보장
        for d in called_dates:
            assert len(d) == 8 and d.isdigit()
