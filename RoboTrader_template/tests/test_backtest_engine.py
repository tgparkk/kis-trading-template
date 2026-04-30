"""
BacktestEngine 단위 테스트
===========================
손절/익절/트레일링스톱/EOD 시뮬레이션 검증 (Phase A1)
screener_snapshots 후보 풀 필터링 검증 (Phase A2)

테스트 범위 (A1):
- test_stop_loss_triggered_by_low: low가 손절가 도달 → stop_loss 매도
- test_target_profit_triggered_by_high: high가 익절가 도달 → take_profit 매도
- test_trailing_stop_after_high: 고가 갱신 후 -3% 하락 → trailing 매도
- test_eod_for_intraday_strategy: holding_period=intraday → EOD 청산
- test_swing_strategy_no_eod: holding_period=swing → EOD 청산 안 함
- test_priority_stop_over_target: high·low 동일봉 도달 시 stop_loss 우선

테스트 범위 (A2):
- test_candidate_provider_filters_universe: candidate_provider가 한 종목만 반환 시 그 종목만 진입
- test_no_candidate_provider_uses_full_universe: candidate_provider 미제공 시 전체 universe 유지
- test_empty_candidate_pool_skips_entry: 후보 풀 비어있는 날 진입 안 함
- test_screener_snapshot_provider_helper: 헬퍼가 DB를 올바르게 호출하는지 (mock)
- test_candidate_pool_hits_counted: candidate_provider가 비공 반환한 일자 수 집계
"""
import pytest
import pandas as pd
from datetime import date
from unittest.mock import Mock, patch, MagicMock

from backtest.engine import BacktestEngine, BacktestResult, make_screener_snapshot_provider
from strategies.base import BaseStrategy, Signal, SignalType


# ============================================================================
# 최소 전략 스텁
# ============================================================================

class _BuyOnceStrategy(BaseStrategy):
    """첫 번째 날만 매수 신호 — 이후 매도는 엔진 리스크 로직에 의존.

    매수 후 positions에 등록되므로 재매수 안 함.
    get_min_data_length=1로 소량 테스트 데이터 허용.
    """
    name = "BuyOnce"
    holding_period = "swing"

    def get_min_data_length(self) -> int:
        return 1

    def generate_signal(self, stock_code, data, timeframe="daily"):
        # 보유 중이 아닐 때만 매수
        if stock_code not in self.positions:
            return Signal(
                signal_type=SignalType.BUY,
                stock_code=stock_code,
                confidence=90,
                reasons=["test buy"],
            )
        return None  # 보유 중 → 매도 신호 없음 → 손절/익절/트레일링에 의존


class _BuyOnceIntradayStrategy(_BuyOnceStrategy):
    """인트라데이 전략 — EOD 청산 대상"""
    name = "BuyOnceIntraday"
    holding_period = "intraday"


# ============================================================================
# 헬퍼
# ============================================================================

def _make_ohlcv(
    dates: list,
    opens: list = None,
    highs: list = None,
    lows: list = None,
    closes: list = None,
    volumes: list = None,
) -> pd.DataFrame:
    """OHLCV DataFrame 생성 헬퍼."""
    n = len(dates)
    closes = closes or [10_000] * n
    opens = opens or closes
    highs = highs or closes
    lows = lows or closes
    volumes = volumes or [100_000] * n
    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def _make_engine(strategy: BaseStrategy, **kwargs) -> BacktestEngine:
    """기본 파라미터로 BacktestEngine 생성."""
    defaults = dict(
        initial_capital=1_000_000,
        max_positions=1,
        position_size_pct=1.0,   # 자본 전체를 한 종목에
        commission_rate=0.0,
        tax_rate=0.0,
    )
    defaults.update(kwargs)
    return BacktestEngine(strategy=strategy, **defaults)


def _first_completed_trade(result: BacktestResult) -> dict:
    """강제청산(forced_exit) 제외한 첫 번째 완료 거래 반환."""
    for t in result.trades:
        if t["signal_type"] != "forced_exit":
            return t
    return result.trades[0]


# ============================================================================
# 테스트 클래스
# ============================================================================

class TestStopLossTriggeredByLow:
    """일봉 low가 손절가 도달 → stop_loss 매도 검증"""

    def test_stop_loss_triggered_by_low(self):
        strategy = _BuyOnceStrategy()
        # stop_loss_rate=5%, take_profit_rate=100% (익절 절대 안 걸리게)
        strategy._stop_loss_pct = 0.05
        strategy._take_profit_pct = 1.00
        engine = _make_engine(strategy)

        entry_price = 10_000
        stop_price = entry_price * 0.95  # 9,500

        # Day1: 매수 (close=10,000), high/low=entry_price → 리스크 트리거 없음
        # Day2: low가 손절가(9,500) 이하 → stop_loss 발동
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price],
            lows=[entry_price, stop_price - 1],   # 9,499 < 9,500
            closes=[entry_price, entry_price - 100],
        )

        result = engine.run(["A"], {"A": data})

        # 첫 번째 거래(stop_loss)가 존재해야 함
        assert result.sells_by_reason.get("stop_loss", 0) >= 1
        trade = _first_completed_trade(result)
        assert trade["signal_type"] == "stop_loss"
        assert abs(trade["exit_price"] - stop_price) < 1


class TestTakeProfitTriggeredByHigh:
    """일봉 high가 익절가 도달 → take_profit 매도 검증"""

    def test_target_profit_triggered_by_high(self):
        strategy = _BuyOnceStrategy()
        strategy._stop_loss_pct = 0.50  # 손절 절대 안 걸리게
        strategy._take_profit_pct = 0.10
        engine = _make_engine(strategy)

        entry_price = 10_000
        target_price = entry_price * 1.10  # 11,000

        # Day1: 매수 (close=10,000), high/low=entry_price → peak=entry_price
        # Day2: high=11,100 → peak=11,100, trailing_stop=11,100*0.97=10,767
        #       low=10,800 > trailing_stop(10,767) → trailing 미발동
        #       high >= target_price(11,000) → take_profit 발동
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03"],
            opens=[entry_price, entry_price],
            highs=[entry_price, target_price + 100],  # 11,100 >= 11,000
            lows=[entry_price, 10_800],                # 10,800 > 10,767 → trailing 미발동
            closes=[entry_price, 10_800],
        )

        result = engine.run(["A"], {"A": data})

        assert result.sells_by_reason.get("take_profit", 0) >= 1
        trade = _first_completed_trade(result)
        assert trade["signal_type"] == "take_profit"
        assert abs(trade["exit_price"] - target_price) < 1


class TestTrailingStopAfterHigh:
    """고가 갱신 후 최고가 대비 -3% 하락 → trailing 매도 검증"""

    def test_trailing_stop_after_high(self):
        strategy = _BuyOnceStrategy()
        strategy._stop_loss_pct = 0.50     # 손절 절대 안 걸리게
        strategy._take_profit_pct = 2.00   # 익절 절대 안 걸리게
        engine = _make_engine(strategy)

        entry_price = 10_000
        peak = 12_000  # 고가 갱신 (+20%)
        trailing_stop = peak * 0.97  # 11,640

        # Day1: 매수 (close=entry_price), high=entry_price → peak=entry_price
        # Day2: high=12,000 (고가 갱신 → peak=12,000)
        #       low=peak*0.97-1=11,639 → trailing 발동
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03"],
            opens=[entry_price, peak],
            highs=[entry_price, peak],
            lows=[entry_price, trailing_stop - 1],  # 11,639 < 11,640
            closes=[entry_price, trailing_stop - 1],
        )

        result = engine.run(["A"], {"A": data})

        assert result.sells_by_reason.get("trailing", 0) >= 1
        trade = _first_completed_trade(result)
        assert trade["signal_type"] == "trailing"
        assert abs(trade["exit_price"] - trailing_stop) < 1


class TestEodForIntradayStrategy:
    """holding_period=intraday → 매수 다음날 EOD 청산 검증.

    엔진은 날짜 루프에서 step1(매도) 후 step2(매수)를 처리하므로,
    매수 당일은 이미 step1이 지난 뒤 → 다음날 step1에서 EOD 처리됨.
    """

    def test_eod_for_intraday_strategy(self):
        strategy = _BuyOnceIntradayStrategy()
        strategy._stop_loss_pct = 0.50   # 손절 절대 안 걸리게
        strategy._take_profit_pct = 2.00  # 익절 절대 안 걸리게
        engine = _make_engine(strategy)

        entry_price = 10_000
        eod_close = 10_200

        # Day1: 매수 (step2에서 포지션 진입)
        # Day2: step1에서 EOD 청산 (intraday 전략)
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03"],
            opens=[entry_price, entry_price],
            highs=[entry_price, entry_price + 50],
            lows=[entry_price, entry_price - 50],
            closes=[entry_price, eod_close],
        )

        result = engine.run(["A"], {"A": data})

        assert result.sells_by_reason.get("eod", 0) >= 1
        trade = _first_completed_trade(result)
        assert trade["signal_type"] == "eod"
        assert trade["exit_price"] == eod_close


class TestSwingStrategyNoEod:
    """holding_period=swing → EOD 청산 없음 (기간 내 포지션 유지) 검증"""

    def test_swing_strategy_no_eod(self):
        strategy = _BuyOnceStrategy()  # holding_period="swing"
        strategy._stop_loss_pct = 0.50   # 손절 절대 안 걸리게
        strategy._take_profit_pct = 2.00  # 익절 절대 안 걸리게
        engine = _make_engine(strategy)

        entry_price = 10_000

        # 3일 데이터 — swing이므로 EOD 청산 없이 마지막 날 강제청산
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03", "2024-01-04"],
            opens=[entry_price] * 3,
            highs=[entry_price + 50] * 3,
            lows=[entry_price - 50] * 3,
            closes=[entry_price] * 3,
        )

        result = engine.run(["A"], {"A": data})

        # EOD 매도 0건
        assert result.sells_by_reason.get("eod", 0) == 0
        # 강제청산 1건 (백테스트 종료)
        assert result.sells_by_reason.get("forced_exit", 0) == 1
        assert result.total_trades == 1


class TestPriorityStopOverTarget:
    """같은 일봉에 high·low가 target·stop 모두 도달 시 stop_loss 우선 검증"""

    def test_priority_stop_over_target(self):
        strategy = _BuyOnceStrategy()
        strategy._stop_loss_pct = 0.05   # 손절가 = 9,500
        strategy._take_profit_pct = 0.10  # 익절가 = 11,000
        engine = _make_engine(strategy)

        entry_price = 10_000
        stop_price = entry_price * 0.95   # 9,500
        target_price = entry_price * 1.10  # 11,000

        # Day1: 매수 (close=entry_price, high/low=entry_price)
        # Day2: low=9,499 (손절 도달) AND high=11,100 (익절 도달)
        #       → 보수적으로 stop_loss 우선 (손실 최소화 원칙)
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03"],
            opens=[entry_price, entry_price],
            highs=[entry_price, target_price + 100],   # 11,100
            lows=[entry_price, stop_price - 1],        # 9,499
            closes=[entry_price, entry_price],
        )

        result = engine.run(["A"], {"A": data})

        # 손절이 익절보다 우선 (손실 최소화 원칙)
        assert result.sells_by_reason.get("stop_loss", 0) >= 1
        trade = _first_completed_trade(result)
        assert trade["signal_type"] == "stop_loss"
        # 같은 날에 익절도 조건 충족되었지만 stop_loss가 우선 처리됨
        assert result.sells_by_reason.get("take_profit", 0) == 0


# ============================================================================
# Phase A2: screener_snapshots 후보 풀 필터링 테스트
# ============================================================================

class TestCandidateProviderFiltersUniverse:
    """candidate_provider가 지정한 종목만 매수 진입하는지 검증."""

    def test_candidate_provider_filters_universe(self):
        """provider가 ['A']만 반환 → B는 진입하지 않음."""
        strategy = _BuyOnceStrategy()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy, max_positions=2)

        price = 10_000
        data = {
            "A": _make_ohlcv(["2024-01-02", "2024-01-03"], closes=[price, price]),
            "B": _make_ohlcv(["2024-01-02", "2024-01-03"], closes=[price, price]),
        }

        # provider: 항상 A만 허용
        def provider(strategy_name: str, scan_date: str):
            return ["A"]

        result = engine.run(["A", "B"], data, candidate_provider=provider)

        bought_codes = {t["stock_code"] for t in result.trades}
        assert "A" in bought_codes, "A는 후보 풀에 포함되어 진입해야 함"
        assert "B" not in bought_codes, "B는 후보 풀에 없으므로 진입하면 안 됨"


class TestNoCandidateProviderUsesFullUniverse:
    """candidate_provider 미제공 시 stock_codes 전체를 universe로 사용."""

    def test_no_candidate_provider_uses_full_universe(self):
        """provider 없음 → A, B 모두 진입 가능."""
        strategy = _BuyOnceStrategy()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy, max_positions=2, position_size_pct=0.5)

        price = 10_000
        data = {
            "A": _make_ohlcv(["2024-01-02", "2024-01-03"], closes=[price, price]),
            "B": _make_ohlcv(["2024-01-02", "2024-01-03"], closes=[price, price]),
        }

        # candidate_provider 없음 — 기본 동작
        result = engine.run(["A", "B"], data)

        bought_codes = {t["stock_code"] for t in result.trades}
        assert "A" in bought_codes, "A는 전체 universe에서 진입해야 함"
        assert "B" in bought_codes, "B도 전체 universe에서 진입해야 함"


class TestEmptyCandidatePoolSkipsEntry:
    """후보 풀이 빈 리스트인 날은 진입을 스킵한다."""

    def test_empty_candidate_pool_skips_entry(self):
        """provider가 빈 리스트 반환 → 해당 날 진입 없음."""
        strategy = _BuyOnceStrategy()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy)

        price = 10_000
        data = {"A": _make_ohlcv(["2024-01-02", "2024-01-03"], closes=[price, price])}

        # 항상 빈 리스트 반환
        def empty_provider(strategy_name: str, scan_date: str):
            return []

        result = engine.run(["A"], data, candidate_provider=empty_provider)

        # 진입이 없으므로 거래도 없어야 함
        assert result.total_trades == 0, "빈 후보 풀이면 거래가 발생하면 안 됨"
        assert result.candidate_pool_hits == 0, "빈 리스트는 hit으로 카운트하지 않음"


class TestScreenerSnapshotProviderHelper:
    """make_screener_snapshot_provider 헬퍼가 DB를 올바르게 호출하는지 mock 검증."""

    def test_provider_calls_get_snapshot_date_range(self):
        """params_hash 없을 때 get_snapshot_date_range를 호출하고 stock_code 반환."""
        mock_df = pd.DataFrame({
            "stock_code": ["005930", "000660"],
            "stock_name": ["삼성전자", "SK하이닉스"],
            "rank_in_snapshot": [1, 2],
        })

        with patch("backtest.engine.CandidateRepository") as MockRepo:
            mock_repo_instance = MagicMock()
            MockRepo.return_value = mock_repo_instance
            mock_repo_instance.get_snapshot_date_range.return_value = mock_df

            provider = make_screener_snapshot_provider("SampleStrategy", params_hash=None)
            codes = provider("SampleStrategy", "2024-04-30")

        assert codes == ["005930", "000660"]
        mock_repo_instance.get_snapshot_date_range.assert_called_once_with(
            strategy="SampleStrategy",
            start_date=date(2024, 4, 30),
            end_date=date(2024, 4, 30),
            params_hash=None,
        )

    def test_provider_calls_get_screener_snapshot_with_hash(self):
        """params_hash 지정 시 get_screener_snapshot을 호출하고 stock_code 반환."""
        mock_rows = [
            {"stock_code": "005930", "stock_name": "삼성전자", "rank_in_snapshot": 1, "score": 85.0, "metadata": None},
            {"stock_code": "000660", "stock_name": "SK하이닉스", "rank_in_snapshot": 2, "score": 78.0, "metadata": None},
        ]

        with patch("backtest.engine.CandidateRepository") as MockRepo:
            mock_repo_instance = MagicMock()
            MockRepo.return_value = mock_repo_instance
            mock_repo_instance.get_screener_snapshot.return_value = mock_rows

            provider = make_screener_snapshot_provider("SampleStrategy", params_hash="abc123")
            codes = provider("SampleStrategy", "2024-04-30")

        assert codes == ["005930", "000660"]
        mock_repo_instance.get_screener_snapshot.assert_called_once_with(
            "SampleStrategy", date(2024, 4, 30), "abc123"
        )

    def test_provider_caches_result(self):
        """동일 날짜 두 번 호출 시 DB를 한 번만 조회."""
        mock_df = pd.DataFrame({"stock_code": ["005930"]})

        with patch("backtest.engine.CandidateRepository") as MockRepo:
            mock_repo_instance = MagicMock()
            MockRepo.return_value = mock_repo_instance
            mock_repo_instance.get_snapshot_date_range.return_value = mock_df

            provider = make_screener_snapshot_provider("SampleStrategy")
            provider("SampleStrategy", "2024-04-30")
            provider("SampleStrategy", "2024-04-30")  # 두 번째 호출

        # DB 조회는 한 번만
        assert mock_repo_instance.get_snapshot_date_range.call_count == 1

    def test_provider_returns_empty_on_db_error(self):
        """DB 에러 시 빈 리스트를 반환하고 예외를 전파하지 않음."""
        with patch("backtest.engine.CandidateRepository") as MockRepo:
            MockRepo.side_effect = Exception("DB 연결 실패")

            provider = make_screener_snapshot_provider("SampleStrategy")
            codes = provider("SampleStrategy", "2024-04-30")

        assert codes == []


class TestCandidatePoolHitsCounted:
    """candidate_pool_hits가 후보 풀이 비지 않은 날만 카운트하는지 검증."""

    def test_hits_counted_correctly(self):
        """포지션 슬롯이 남아있는 날에만 provider가 호출되고 hit이 집계된다.

        구조:
        - max_positions=2, position_size_pct=0.5, 종목 A·B
        - Day1: available_slots=2 → provider 호출 → ["A","B"] 반환 → hit=1, A·B 매수
        - Day2, Day3: available_slots=0 → provider 호출 안 됨
        - 결과: candidate_pool_hits=1, provider call_count=1
        """
        strategy = _BuyOnceStrategy()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy, max_positions=2, position_size_pct=0.5)

        price = 10_000
        data = {
            "A": _make_ohlcv(["2024-01-02", "2024-01-03", "2024-01-04"], closes=[price] * 3),
            "B": _make_ohlcv(["2024-01-02", "2024-01-03", "2024-01-04"], closes=[price] * 3),
        }

        call_count = {"n": 0}

        def provider(strategy_name: str, scan_date: str):
            call_count["n"] += 1
            return ["A", "B"]  # 항상 비지 않은 풀 반환

        result = engine.run(["A", "B"], data, candidate_provider=provider)

        # Day1에만 available_slots>0 → provider 1회 호출, hit=1
        assert result.candidate_pool_hits == 1, (
            f"슬롯 있는 날(Day1)만 hit 카운트 기대=1, 실제={result.candidate_pool_hits}"
        )
        assert call_count["n"] == 1, (
            f"provider는 available_slots>0인 날만 호출 기대=1, 실제={call_count['n']}"
        )

    def test_hits_not_counted_for_empty_pool(self):
        """provider가 빈 리스트 반환하면 candidate_pool_hits에 포함 안 됨."""
        strategy = _BuyOnceStrategy()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy)

        price = 10_000
        data = {"A": _make_ohlcv(
            ["2024-01-02", "2024-01-03"],
            closes=[price, price],
        )}

        def empty_provider(strategy_name: str, scan_date: str):
            return []  # 항상 빈 풀

        result = engine.run(["A"], data, candidate_provider=empty_provider)

        assert result.candidate_pool_hits == 0, (
            f"빈 풀은 hit 카운트 안 함. 실제={result.candidate_pool_hits}"
        )
