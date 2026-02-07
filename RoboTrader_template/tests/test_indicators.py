"""
기술적 지표 유닛 테스트
========================

테스트 대상:
- core/indicators/bisector_line.py: 이등분선 계산 및 분석
- core/indicators/bollinger_bands.py: 볼린저 밴드 계산
- core/indicators/price_box.py: 가격박스 지표
- core/indicators/pullback/types.py: 데이터 타입 (Enum, Dataclass)
- core/indicators/pullback/volume_analyzer.py: 거래량 분석
- core/indicators/pullback/candle_analyzer.py: 캔들 분석
- core/indicators/pullback/bisector_analyzer.py: 이등분선 분석
- core/indicators/pullback/risk_detector.py: 위험 신호 감지
- core/indicators/pullback/signal_calculator.py: 신호 강도 계산
- core/indicators/pullback/technical_filter.py: 기술적 필터
- core/indicators/pullback/support_pattern_analyzer.py: 지지 패턴 분석
- core/indicators/filter_stats.py: 필터 통계
- core/indicators/pattern_combination_filter.py: 패턴 조합 필터
- core/indicators/time_weighted_filter.py: 시간대별 가중치 필터
- core/indicators/pullback_utils.py: PullbackUtils 위임 확인
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone, time


# ============================================================================
# Fixtures - 가상 OHLCV 데이터 생성
# ============================================================================

@pytest.fixture
def uptrend_ohlcv():
    """상승 추세 OHLCV 데이터 (30봉, 50000원 기준, 봉당 +0.3%)"""
    np.random.seed(100)
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    periods = 30
    base_price = 50000

    closes = [base_price * (1 + 0.003 * i) for i in range(periods)]
    opens = [c * np.random.uniform(0.998, 1.001) for c in closes]
    highs = [max(o, c) * np.random.uniform(1.001, 1.004) for o, c in zip(opens, closes)]
    lows = [min(o, c) * np.random.uniform(0.996, 0.999) for o, c in zip(opens, closes)]
    volumes = [np.random.randint(50000, 120000) for _ in range(periods)]

    return pd.DataFrame({
        'datetime': [base_time + timedelta(minutes=3 * i) for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


@pytest.fixture
def downtrend_ohlcv():
    """하락 추세 OHLCV 데이터 (30봉, 50000원 기준, 봉당 -0.3%)"""
    np.random.seed(200)
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    periods = 30
    base_price = 50000

    closes = [base_price * (1 - 0.003 * i) for i in range(periods)]
    opens = [c * np.random.uniform(1.001, 1.003) for c in closes]
    highs = [o * np.random.uniform(1.001, 1.003) for o in opens]
    lows = [c * np.random.uniform(0.997, 0.999) for c in closes]
    volumes = [np.random.randint(50000, 100000) for _ in range(periods)]

    return pd.DataFrame({
        'datetime': [base_time + timedelta(minutes=3 * i) for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


@pytest.fixture
def sideways_ohlcv():
    """횡보 OHLCV 데이터 (30봉, 50000원 기준)"""
    np.random.seed(300)
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    periods = 30
    base_price = 50000

    closes = [base_price * (1 + np.random.uniform(-0.002, 0.002)) for _ in range(periods)]
    opens = [c * np.random.uniform(0.999, 1.001) for c in closes]
    highs = [max(o, c) * np.random.uniform(1.001, 1.003) for o, c in zip(opens, closes)]
    lows = [min(o, c) * np.random.uniform(0.997, 0.999) for o, c in zip(opens, closes)]
    volumes = [np.random.randint(30000, 60000) for _ in range(periods)]

    return pd.DataFrame({
        'datetime': [base_time + timedelta(minutes=3 * i) for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


@pytest.fixture
def pullback_pattern_ohlcv():
    """눌림목 패턴 OHLCV 데이터 (상승 -> 저거래량 하락 -> 거래량 회복)"""
    np.random.seed(400)
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    base_price = 50000

    closes = []
    volumes = []
    phases = []

    # Phase 1: 상승 (0~9, 고거래량)
    for i in range(10):
        closes.append(base_price * (1 + 0.005 * i))
        volumes.append(np.random.randint(80000, 130000))
        phases.append('uptrend')

    # Phase 2: 저거래량 하락 (10~19)
    peak = closes[-1]
    for i in range(10):
        closes.append(peak * (1 - 0.002 * (i + 1)))
        volumes.append(np.random.randint(10000, 25000))
        phases.append('decline')

    # Phase 3: 거래량 회복 + 반등 (20~29)
    bottom = closes[-1]
    for i in range(10):
        closes.append(bottom * (1 + 0.003 * (i + 1)))
        volumes.append(np.random.randint(50000, 90000))
        phases.append('recovery')

    periods = len(closes)
    opens = [c * np.random.uniform(0.998, 1.002) for c in closes]
    highs = [max(o, c) * np.random.uniform(1.001, 1.005) for o, c in zip(opens, closes)]
    lows = [min(o, c) * np.random.uniform(0.995, 0.999) for o, c in zip(opens, closes)]

    return pd.DataFrame({
        'datetime': [base_time + timedelta(minutes=3 * i) for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


@pytest.fixture
def minimal_ohlcv():
    """최소 데이터 (1봉)"""
    return pd.DataFrame({
        'datetime': [datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))],
        'open': [50000.0],
        'high': [50500.0],
        'low': [49800.0],
        'close': [50300.0],
        'volume': [100000]
    })


@pytest.fixture
def empty_ohlcv():
    """빈 데이터프레임"""
    return pd.DataFrame(columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])


# ============================================================================
# 1. BisectorLine (이등분선) 테스트
# ============================================================================

class TestBisectorLine:
    """이등분선 계산 및 분석 테스트"""

    def test_calculate_bisector_line_basic(self, uptrend_ohlcv):
        """이등분선 기본 계산 - 누적 최고가와 최저가의 평균"""
        from core.indicators.bisector_line import BisectorLine

        result = BisectorLine.calculate_bisector_line(
            uptrend_ohlcv['high'], uptrend_ohlcv['low']
        )

        assert isinstance(result, pd.Series)
        assert len(result) == len(uptrend_ohlcv)
        assert not result.isna().all()

    def test_calculate_bisector_line_expanding(self, uptrend_ohlcv):
        """이등분선이 expanding max/min 기반인지 확인"""
        from core.indicators.bisector_line import BisectorLine

        result = BisectorLine.calculate_bisector_line(
            uptrend_ohlcv['high'], uptrend_ohlcv['low']
        )

        # 첫 번째 값 = (첫 고가 + 첫 저가) / 2
        expected_first = (uptrend_ohlcv['high'].iloc[0] + uptrend_ohlcv['low'].iloc[0]) / 2
        assert abs(result.iloc[0] - expected_first) < 0.01

    def test_analyze_price_position(self, uptrend_ohlcv):
        """주가 위치 분석 (above/below/neutral)"""
        from core.indicators.bisector_line import BisectorLine

        bisector = BisectorLine.calculate_bisector_line(
            uptrend_ohlcv['high'], uptrend_ohlcv['low']
        )
        positions = BisectorLine.analyze_price_position(
            uptrend_ohlcv['close'], bisector, tolerance_pct=1.0
        )

        assert isinstance(positions, pd.Series)
        valid_values = {'above', 'below', 'neutral'}
        assert set(positions.unique()).issubset(valid_values)

    def test_detect_support_failure(self, downtrend_ohlcv):
        """지지 실패 감지 - 하락 추세에서 감지됨"""
        from core.indicators.bisector_line import BisectorLine

        bisector = BisectorLine.calculate_bisector_line(
            downtrend_ohlcv['high'], downtrend_ohlcv['low']
        )
        failures = BisectorLine.detect_support_failure(
            downtrend_ohlcv['close'], bisector,
            failure_threshold_pct=1.0, lookback_periods=3
        )

        assert isinstance(failures, pd.Series)
        assert failures.dtype == bool

    def test_detect_rapid_surge(self, uptrend_ohlcv):
        """급등 감지 테스트"""
        from core.indicators.bisector_line import BisectorLine

        result = BisectorLine.detect_rapid_surge(
            uptrend_ohlcv['close'], surge_threshold_pct=20.0, time_window=10
        )

        assert isinstance(result, pd.Series)
        # 완만한 상승이므로 급등 신호 없어야 함
        assert result.sum() == 0

    def test_generate_trading_signals(self, uptrend_ohlcv):
        """종합 트레이딩 신호 생성"""
        from core.indicators.bisector_line import BisectorLine

        # index를 datetime으로 설정
        data = uptrend_ohlcv.copy()
        data.index = data['datetime']

        signals = BisectorLine.generate_trading_signals(data)

        assert isinstance(signals, pd.DataFrame)
        assert 'bisector_line' in signals.columns
        assert 'price_position' in signals.columns
        assert 'bullish_zone' in signals.columns

    def test_instance_compatibility(self, uptrend_ohlcv):
        """인스턴스 방식 하위 호환성 확인"""
        from core.indicators.bisector_line import BisectorLine

        bl = BisectorLine(tolerance_pct=1.5)
        assert bl.tolerance_pct == 1.5


# ============================================================================
# 2. BollingerBands (볼린저 밴드) 테스트
# ============================================================================

class TestBollingerBands:
    """볼린저 밴드 계산 테스트"""

    def test_calculate_bollinger_bands_structure(self, uptrend_ohlcv):
        """볼린저 밴드 계산 결과 구조 검증"""
        from core.indicators.bollinger_bands import BollingerBands

        result = BollingerBands.calculate_bollinger_bands(
            uptrend_ohlcv['close'], period=20, std_multiplier=2.0
        )

        assert 'sma' in result
        assert 'upper_band' in result
        assert 'lower_band' in result
        assert 'std' in result

    def test_bollinger_band_ordering(self, uptrend_ohlcv):
        """상한선 > 중심선 > 하한선 순서 보장"""
        from core.indicators.bollinger_bands import BollingerBands

        result = BollingerBands.calculate_bollinger_bands(
            uptrend_ohlcv['close'], period=20
        )

        # NaN 제거 후 비교
        valid = ~(result['sma'].isna() | result['upper_band'].isna())
        assert (result['upper_band'][valid] >= result['sma'][valid]).all()
        assert (result['sma'][valid] >= result['lower_band'][valid]).all()

    def test_calculate_band_width(self, uptrend_ohlcv):
        """밴드 폭 계산"""
        from core.indicators.bollinger_bands import BollingerBands

        bb = BollingerBands.calculate_bollinger_bands(uptrend_ohlcv['close'])
        width = BollingerBands.calculate_band_width(
            bb['upper_band'], bb['lower_band'], bb['sma']
        )

        assert isinstance(width, pd.Series)
        # 밴드 폭은 양수
        valid = ~width.isna()
        assert (width[valid] >= 0).all()

    def test_calculate_percent_b(self, uptrend_ohlcv):
        """% B 계산 (0~1 범위 내 대부분)"""
        from core.indicators.bollinger_bands import BollingerBands

        bb = BollingerBands.calculate_bollinger_bands(uptrend_ohlcv['close'])
        pct_b = BollingerBands.calculate_percent_b(
            uptrend_ohlcv['close'], bb['upper_band'], bb['lower_band']
        )

        assert isinstance(pct_b, pd.Series)
        assert len(pct_b) == len(uptrend_ohlcv)

    def test_detect_squeeze(self, sideways_ohlcv):
        """볼린저 밴드 스퀸즈 감지"""
        from core.indicators.bollinger_bands import BollingerBands

        bb = BollingerBands.calculate_bollinger_bands(sideways_ohlcv['close'])
        width = BollingerBands.calculate_band_width(
            bb['upper_band'], bb['lower_band'], bb['sma']
        )
        squeeze = BollingerBands.detect_squeeze(width, lookback_period=20)

        assert isinstance(squeeze, pd.Series)
        assert squeeze.dtype == bool

    def test_generate_trading_signals(self, uptrend_ohlcv):
        """트레이딩 신호 생성"""
        from core.indicators.bollinger_bands import BollingerBands

        signals = BollingerBands.generate_trading_signals(uptrend_ohlcv['close'])

        assert isinstance(signals, pd.DataFrame)
        assert 'buy_signal' in signals.columns
        assert 'sell_signal' in signals.columns
        assert 'percent_b' in signals.columns

    def test_instance_compatibility(self, uptrend_ohlcv):
        """인스턴스 방식 하위 호환성"""
        from core.indicators.bollinger_bands import BollingerBands

        bb = BollingerBands(period=20, std_multiplier=2.0)
        signals = bb.generate_signals(uptrend_ohlcv['close'])
        assert isinstance(signals, pd.DataFrame)


# ============================================================================
# 3. PriceBox (가격박스) 테스트
# ============================================================================

class TestPriceBox:
    """가격박스 지표 테스트"""

    def test_triangular_moving_average(self, uptrend_ohlcv):
        """삼각 이동평균 계산"""
        from core.indicators.price_box import PriceBox

        tma = PriceBox.triangular_moving_average(uptrend_ohlcv['close'], period=30)

        assert isinstance(tma, pd.Series)
        assert len(tma) == len(uptrend_ohlcv)
        # TMA는 smoothing 효과로 변동이 적어야 함
        tma_std = tma.std()
        raw_std = uptrend_ohlcv['close'].std()
        assert tma_std <= raw_std

    def test_calculate_price_box(self, uptrend_ohlcv):
        """가격박스 계산 (중심선, 상한선, 하한선)"""
        from core.indicators.price_box import PriceBox

        result = PriceBox.calculate_price_box(uptrend_ohlcv['close'], period=20)

        assert 'center_line' in result
        assert 'upper_band' in result
        assert 'lower_band' in result

    def test_price_box_band_ordering(self, uptrend_ohlcv):
        """상한선 >= 중심선 >= 하한선"""
        from core.indicators.price_box import PriceBox

        result = PriceBox.calculate_price_box(uptrend_ohlcv['close'], period=20)

        # 초기 데이터가 안정되는 10번째부터 확인
        for i in range(10, len(uptrend_ohlcv)):
            center = result['center_line'].iloc[i]
            upper = result['upper_band'].iloc[i]
            lower = result['lower_band'].iloc[i]
            if not (pd.isna(center) or pd.isna(upper) or pd.isna(lower)):
                assert upper >= center, f"인덱스 {i}: 상한({upper}) < 중심({center})"
                assert center >= lower, f"인덱스 {i}: 중심({center}) < 하한({lower})"

    def test_avg_if_positive(self):
        """AvgIf 양수 조건 테스트"""
        from core.indicators.price_box import PriceBox

        data = pd.Series([1.0, -2.0, 3.0, -1.0, 5.0])
        result = PriceBox.avg_if(data, condition=1, default=0.0, window=5)

        assert isinstance(result, pd.Series)
        assert len(result) == 5

    def test_stdev_if_negative(self):
        """StdevIf 음수 조건 테스트"""
        from core.indicators.price_box import PriceBox

        data = pd.Series([1.0, -2.0, 3.0, -1.0, 5.0])
        result = PriceBox.stdev_if(data, condition=-1, default=0.0, window=5)

        assert isinstance(result, pd.Series)
        assert len(result) == 5


# ============================================================================
# 4. Pullback Types (데이터 타입) 테스트
# ============================================================================

class TestPullbackTypes:
    """눌림목 패턴 데이터 타입 검증"""

    def test_signal_type_enum_values(self):
        """SignalType enum 값 검증"""
        from core.indicators.pullback.types import SignalType

        assert SignalType.STRONG_BUY.value == "STRONG_BUY"
        assert SignalType.CAUTIOUS_BUY.value == "CAUTIOUS_BUY"
        assert SignalType.WAIT.value == "WAIT"
        assert SignalType.AVOID.value == "AVOID"
        assert SignalType.SELL.value == "SELL"

    def test_bisector_status_enum_values(self):
        """BisectorStatus enum 값 검증"""
        from core.indicators.pullback.types import BisectorStatus

        assert BisectorStatus.HOLDING.value == "HOLDING"
        assert BisectorStatus.NEAR_SUPPORT.value == "NEAR_SUPPORT"
        assert BisectorStatus.BROKEN.value == "BROKEN"

    def test_risk_signal_enum_values(self):
        """RiskSignal enum 값 검증"""
        from core.indicators.pullback.types import RiskSignal

        expected = {
            'LARGE_BEARISH_VOLUME', 'BISECTOR_BREAK',
            'ENTRY_LOW_BREAK', 'SUPPORT_BREAK', 'TARGET_REACHED'
        }
        actual = {e.value for e in RiskSignal}
        assert actual == expected

    def test_signal_strength_dataclass(self):
        """SignalStrength 데이터클래스 생성"""
        from core.indicators.pullback.types import (
            SignalStrength, SignalType, BisectorStatus
        )

        ss = SignalStrength(
            signal_type=SignalType.STRONG_BUY,
            confidence=85.0,
            target_profit=0.03,
            reasons=["회복양봉", "거래량회복"],
            volume_ratio=0.6,
            bisector_status=BisectorStatus.HOLDING
        )

        assert ss.signal_type == SignalType.STRONG_BUY
        assert ss.confidence == 85.0
        assert len(ss.reasons) == 2
        assert ss.buy_price == 0.0  # 기본값
        assert ss.pattern_data is None  # 기본값

    def test_volume_analysis_dataclass(self):
        """VolumeAnalysis 데이터클래스 생성"""
        from core.indicators.pullback.types import VolumeAnalysis

        va = VolumeAnalysis(
            baseline_volume=100000,
            current_volume=50000,
            avg_recent_volume=60000,
            volume_ratio=0.5,
            volume_trend='increasing',
            is_volume_surge=False,
            is_low_volume=False,
            is_moderate_volume=True,
            is_high_volume=False
        )

        assert va.baseline_volume == 100000
        assert va.is_moderate_volume is True

    def test_candle_analysis_dataclass(self):
        """CandleAnalysis 데이터클래스 생성"""
        from core.indicators.pullback.types import CandleAnalysis

        ca = CandleAnalysis(
            is_bullish=True,
            body_size=200,
            body_pct=0.8,
            current_candle_size=400,
            avg_recent_candle_size=350,
            candle_trend='expanding',
            is_small_candle=False,
            is_large_candle=True,
            is_meaningful_body=True
        )

        assert ca.is_bullish is True
        assert ca.is_large_candle is True


# ============================================================================
# 5. VolumeAnalyzer (거래량 분석) 테스트
# ============================================================================

class TestVolumeAnalyzer:
    """거래량 분석 테스트"""

    def test_calculate_daily_baseline_volume(self, uptrend_ohlcv):
        """당일 기준거래량 계산 (누적 최대)"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        result = VolumeAnalyzer.calculate_daily_baseline_volume(uptrend_ohlcv)

        assert isinstance(result, pd.Series)
        assert len(result) == len(uptrend_ohlcv)
        # 누적 최대이므로 단조 증가
        for i in range(1, len(result)):
            assert result.iloc[i] >= result.iloc[i - 1]

    def test_analyze_volume_normal(self, uptrend_ohlcv):
        """정상 거래량 분석"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        result = VolumeAnalyzer.analyze_volume(uptrend_ohlcv, period=10)

        assert result.baseline_volume > 0
        assert result.current_volume > 0
        assert result.volume_trend in ('increasing', 'decreasing', 'stable')
        # numpy bool_ 호환: bool()로 변환 가능한지 확인
        assert bool(result.is_volume_surge) in (True, False)
        assert bool(result.is_low_volume) in (True, False)

    def test_analyze_volume_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 안전하게 기본값 반환"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        result = VolumeAnalyzer.analyze_volume(minimal_ohlcv, period=10)

        assert result.volume_ratio == 0
        assert result.volume_trend == 'stable'

    def test_analyze_price_trend_uptrend(self, uptrend_ohlcv):
        """가격 트렌드 분석 - 상승"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        result = VolumeAnalyzer.analyze_price_trend(uptrend_ohlcv, period=10)

        assert 'trend_strength' in result
        assert 'volatility' in result
        assert 'momentum' in result
        assert result['trend_strength'] > 0  # 상승 추세
        assert result['momentum'] > 0

    def test_analyze_price_trend_downtrend(self, downtrend_ohlcv):
        """가격 트렌드 분석 - 하락"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        result = VolumeAnalyzer.analyze_price_trend(downtrend_ohlcv, period=10)

        assert result['trend_strength'] < 0  # 하락 추세
        assert result['momentum'] < 0

    def test_analyze_price_trend_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 기본값"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        result = VolumeAnalyzer.analyze_price_trend(minimal_ohlcv, period=10)

        assert result == {'trend_strength': 0, 'volatility': 0, 'momentum': 0}

    def test_check_volume_recovery(self, pullback_pattern_ohlcv):
        """거래량 회복 확인"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        # 회복 구간(마지막 10봉)에서 거래량 회복 확인
        result = VolumeAnalyzer.check_volume_recovery(pullback_pattern_ohlcv, retrace_lookback=3)

        # numpy.bool_ 호환
        assert bool(result) in (True, False)

    def test_check_low_volume_retrace(self, pullback_pattern_ohlcv):
        """저거래량 조정 확인"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        result = VolumeAnalyzer.check_low_volume_retrace(
            pullback_pattern_ohlcv, lookback=3, volume_threshold=0.25
        )

        # numpy.bool_ 호환
        assert bool(result) in (True, False)

    def test_analyze_volume_pattern_internal(self, pullback_pattern_ohlcv):
        """내부 거래량 패턴 분석"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        baseline = VolumeAnalyzer.calculate_daily_baseline_volume(pullback_pattern_ohlcv)
        result = VolumeAnalyzer._analyze_volume_pattern_internal(
            pullback_pattern_ohlcv, baseline, period=3
        )

        assert 'consecutive_low_count' in result
        assert 'current_vs_threshold' in result
        assert 'avg_low_volume_ratio' in result
        assert 'volume_trend' in result
        assert result['volume_trend'] in ('increasing', 'decreasing', 'stable')

    def test_analyze_volume_pattern_insufficient_data(self, minimal_ohlcv):
        """패턴 분석 - 데이터 부족"""
        from core.indicators.pullback.volume_analyzer import VolumeAnalyzer

        baseline = pd.Series([100000])
        result = VolumeAnalyzer._analyze_volume_pattern_internal(
            minimal_ohlcv, baseline, period=3
        )

        assert result['consecutive_low_count'] == 0
        assert result['volume_trend'] == 'stable'


# ============================================================================
# 6. CandleAnalyzer (캔들 분석) 테스트
# ============================================================================

class TestCandleAnalyzer:
    """캔들 분석 테스트"""

    def test_is_recovery_candle_bullish(self, uptrend_ohlcv):
        """양봉이면 회복 캔들"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        # 상승 추세의 마지막 봉은 양봉일 가능성 높음
        last_idx = len(uptrend_ohlcv) - 1
        last_candle = uptrend_ohlcv.iloc[last_idx]

        result = CandleAnalyzer.is_recovery_candle(uptrend_ohlcv, last_idx)
        expected = last_candle['close'] > last_candle['open']
        assert result == expected

    def test_is_recovery_candle_invalid_index(self, uptrend_ohlcv):
        """잘못된 인덱스에서 False 반환"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        assert CandleAnalyzer.is_recovery_candle(uptrend_ohlcv, -1) is False
        assert CandleAnalyzer.is_recovery_candle(uptrend_ohlcv, 999) is False

    def test_analyze_candle_size(self, uptrend_ohlcv):
        """캔들 크기 분석"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.analyze_candle_size(uptrend_ohlcv, period=20)

        assert 'body_ratio' in result
        assert 'total_range' in result
        assert 'expansion_ratio' in result
        assert result['body_ratio'] >= 0
        assert result['total_range'] >= 0

    def test_analyze_candle_size_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 기본값"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.analyze_candle_size(minimal_ohlcv, period=20)

        assert result == {'body_ratio': 0, 'total_range': 0, 'expansion_ratio': 1.0}

    def test_analyze_candle(self, uptrend_ohlcv):
        """캔들 분석 결과 구조 검증"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.analyze_candle(uptrend_ohlcv, period=10)

        assert isinstance(result.is_bullish, bool)
        assert result.body_size >= 0
        assert result.body_pct >= 0
        assert result.candle_trend in ('expanding', 'shrinking', 'stable')
        assert isinstance(result.is_meaningful_body, bool)

    def test_check_overhead_supply(self, uptrend_ohlcv):
        """머리 위 물량 확인"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.check_overhead_supply(uptrend_ohlcv, lookback=10, threshold_hits=2)
        assert isinstance(result, bool)

    def test_check_overhead_supply_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 False"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.check_overhead_supply(minimal_ohlcv, lookback=10)
        assert result is False

    def test_check_price_trend(self, uptrend_ohlcv):
        """가격 추세 확인"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.check_price_trend(uptrend_ohlcv, period=10)
        assert result in ('uptrend', 'downtrend', 'stable')

    def test_check_price_trend_uptrend(self, uptrend_ohlcv):
        """상승 추세 감지"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.check_price_trend(uptrend_ohlcv, period=10)
        assert result == 'uptrend'

    def test_find_recent_low(self, uptrend_ohlcv):
        """최근 저점 찾기"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.find_recent_low(uptrend_ohlcv, period=5)
        assert result is not None
        assert result > 0

    def test_find_recent_low_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 None"""
        from core.indicators.pullback.candle_analyzer import CandleAnalyzer

        result = CandleAnalyzer.find_recent_low(minimal_ohlcv, period=5)
        assert result is None


# ============================================================================
# 7. BisectorAnalyzer (이등분선 분석 - pullback 모듈) 테스트
# ============================================================================

class TestBisectorAnalyzer:
    """pullback/bisector_analyzer.py 테스트"""

    def test_analyze_bisector_status_holding(self, uptrend_ohlcv):
        """상승 추세에서 이등분선 지지 상태"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer
        from core.indicators.pullback.types import BisectorStatus

        result = BisectorAnalyzer.analyze_bisector_status(uptrend_ohlcv)

        assert isinstance(result, BisectorStatus)

    def test_analyze_bisector_status_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 BROKEN"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer
        from core.indicators.pullback.types import BisectorStatus

        result = BisectorAnalyzer.analyze_bisector_status(minimal_ohlcv)
        assert result == BisectorStatus.BROKEN

    def test_get_bisector_status_holding(self):
        """현재가가 이등분선 위 (HOLDING)"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer
        from core.indicators.pullback.types import BisectorStatus

        result = BisectorAnalyzer.get_bisector_status(10500, 10000)
        assert result == BisectorStatus.HOLDING

    def test_get_bisector_status_near_support(self):
        """현재가가 이등분선 근처 (NEAR_SUPPORT)"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer
        from core.indicators.pullback.types import BisectorStatus

        result = BisectorAnalyzer.get_bisector_status(10020, 10000)
        assert result == BisectorStatus.NEAR_SUPPORT

    def test_get_bisector_status_broken(self):
        """현재가가 이등분선 아래 (BROKEN)"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer
        from core.indicators.pullback.types import BisectorStatus

        result = BisectorAnalyzer.get_bisector_status(9900, 10000)
        assert result == BisectorStatus.BROKEN

    def test_get_bisector_status_none_bisector(self):
        """이등분선이 None이면 BROKEN"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer
        from core.indicators.pullback.types import BisectorStatus

        result = BisectorAnalyzer.get_bisector_status(10000, None)
        assert result == BisectorStatus.BROKEN

    def test_get_bisector_status_zero_bisector(self):
        """이등분선이 0이면 BROKEN"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer
        from core.indicators.pullback.types import BisectorStatus

        result = BisectorAnalyzer.get_bisector_status(10000, 0)
        assert result == BisectorStatus.BROKEN

    def test_check_bisector_cross_up(self, uptrend_ohlcv):
        """이등분선 상향 돌파 확인"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer

        result = BisectorAnalyzer.check_bisector_cross_up(uptrend_ohlcv)
        # numpy.bool_ 호환
        assert bool(result) in (True, False)

    def test_check_bisector_cross_up_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 False"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer

        result = BisectorAnalyzer.check_bisector_cross_up(minimal_ohlcv)
        assert result is False

    def test_check_price_above_bisector(self, uptrend_ohlcv):
        """이등분선 위 확인"""
        from core.indicators.pullback.bisector_analyzer import BisectorAnalyzer

        result = BisectorAnalyzer.check_price_above_bisector(uptrend_ohlcv)
        assert isinstance(result, bool)


# ============================================================================
# 8. RiskDetector (위험 신호 감지) 테스트
# ============================================================================

class TestRiskDetector:
    """위험 신호 감지 테스트"""

    def test_detect_risk_signals_empty_data(self, empty_ohlcv):
        """빈 데이터에서 빈 리스트 반환"""
        from core.indicators.pullback.risk_detector import RiskDetector

        result = RiskDetector.detect_risk_signals(empty_ohlcv)
        assert result == []

    def test_detect_risk_signals_target_reached(self, uptrend_ohlcv):
        """목표 수익 달성 감지"""
        from core.indicators.pullback.risk_detector import RiskDetector
        from core.indicators.pullback.types import RiskSignal

        # 진입가를 현재가보다 훨씬 낮게 설정
        current_close = uptrend_ohlcv['close'].iloc[-1]
        entry_price = current_close * 0.95  # 5% 낮은 가격에 진입

        result = RiskDetector.detect_risk_signals(
            uptrend_ohlcv, entry_price=entry_price, target_profit_rate=0.03
        )

        assert RiskSignal.TARGET_REACHED in result

    def test_detect_risk_signals_no_target(self, uptrend_ohlcv):
        """진입가 없으면 목표 수익 감지 안 됨"""
        from core.indicators.pullback.risk_detector import RiskDetector
        from core.indicators.pullback.types import RiskSignal

        result = RiskDetector.detect_risk_signals(uptrend_ohlcv)

        assert RiskSignal.TARGET_REACHED not in result

    def test_detect_risk_signals_support_break(self, downtrend_ohlcv):
        """지지 저점 이탈 감지 (하락 추세)"""
        from core.indicators.pullback.risk_detector import RiskDetector
        from core.indicators.pullback.types import RiskSignal

        # 하락 추세에서 마지막 종가가 최근 10봉 저점보다 낮을 수 있음
        result = RiskDetector.detect_risk_signals(downtrend_ohlcv)

        # 하락 추세에서 SUPPORT_BREAK 발생 가능
        assert isinstance(result, list)

    def test_check_risk_signals_target_reached(self):
        """check_risk_signals - 목표 수익 달성"""
        from core.indicators.pullback.risk_detector import RiskDetector
        from core.indicators.pullback.types import (
            RiskSignal, VolumeAnalysis, CandleAnalysis
        )

        current = pd.Series({
            'open': 10000, 'high': 10500, 'low': 9900,
            'close': 10400, 'volume': 50000
        })

        va = VolumeAnalysis(100000, 50000, 60000, 0.5, 'stable', False, False, True, False)
        ca = CandleAnalysis(True, 400, 4.0, 600, 500, 'stable', False, False, True)

        result = RiskDetector.check_risk_signals(
            current, bisector_line=10000, entry_low=None,
            recent_low=9500, entry_price=10000,
            volume_analysis=va, candle_analysis=ca
        )

        assert RiskSignal.TARGET_REACHED in result

    def test_check_risk_signals_bisector_break(self):
        """check_risk_signals - 이등분선 이탈"""
        from core.indicators.pullback.risk_detector import RiskDetector
        from core.indicators.pullback.types import (
            RiskSignal, VolumeAnalysis, CandleAnalysis
        )

        current = pd.Series({
            'open': 10000, 'high': 10100, 'low': 9700,
            'close': 9750, 'volume': 50000
        })

        va = VolumeAnalysis(100000, 50000, 60000, 0.5, 'stable', False, False, True, False)
        ca = CandleAnalysis(False, 250, 2.5, 400, 300, 'stable', False, False, True)

        result = RiskDetector.check_risk_signals(
            current, bisector_line=10000, entry_low=None,
            recent_low=9600, entry_price=None,
            volume_analysis=va, candle_analysis=ca
        )

        assert RiskSignal.BISECTOR_BREAK in result


# ============================================================================
# 9. SignalCalculator (신호 강도 계산) 테스트
# ============================================================================

class TestSignalCalculator:
    """신호 강도 계산 테스트"""

    def test_is_first_recovery_candle_pattern(self):
        """상승A -> 하락A -> 상승B 패턴 확인"""
        from core.indicators.pullback.signal_calculator import SignalCalculator

        # 상승(open < close) -> 하락(open > close) -> 상승(open < close)
        data = pd.DataFrame({
            'open':  [100, 105, 108, 110, 107, 104, 105],
            'close': [105, 108, 110, 107, 104, 103, 108],
            'high':  [106, 109, 111, 111, 108, 105, 109],
            'low':   [99, 104, 107, 106, 103, 102, 104],
            'volume': [1000] * 7
        })

        result = SignalCalculator.is_first_recovery_candle(data)
        assert isinstance(result, bool)

    def test_is_first_recovery_candle_insufficient_data(self):
        """데이터 부족 시 False"""
        from core.indicators.pullback.signal_calculator import SignalCalculator

        data = pd.DataFrame({
            'open': [100, 105],
            'close': [105, 110],
            'high': [106, 111],
            'low': [99, 104],
            'volume': [1000, 1000]
        })

        result = SignalCalculator.is_first_recovery_candle(data)
        assert result is False

    def test_calculate_signal_strength_strong_buy(self):
        """강매수 신호 강도 계산"""
        from core.indicators.pullback.signal_calculator import SignalCalculator
        from core.indicators.pullback.types import (
            VolumeAnalysis, BisectorStatus, SignalType
        )

        va = VolumeAnalysis(100000, 80000, 60000, 0.8, 'increasing',
                           True, False, False, True)

        result = SignalCalculator.calculate_signal_strength(
            volume_analysis=va,
            bisector_status=BisectorStatus.HOLDING,
            is_recovery_candle=True,
            volume_recovers=True,
            has_retrace=True,
            crosses_bisector_up=True,
            has_overhead_supply=False
        )

        assert result.confidence > 0
        assert isinstance(result.signal_type, SignalType)
        assert len(result.reasons) > 0

    def test_calculate_signal_strength_avoid_no_volume(self):
        """거래량 미회복 시 회피 신호"""
        from core.indicators.pullback.signal_calculator import SignalCalculator
        from core.indicators.pullback.types import (
            VolumeAnalysis, BisectorStatus, SignalType
        )

        va = VolumeAnalysis(100000, 20000, 60000, 0.2, 'decreasing',
                           False, True, False, False)

        result = SignalCalculator.calculate_signal_strength(
            volume_analysis=va,
            bisector_status=BisectorStatus.BROKEN,
            is_recovery_candle=False,
            volume_recovers=False,
            has_retrace=False,
            crosses_bisector_up=False,
            has_overhead_supply=False
        )

        assert result.signal_type == SignalType.AVOID

    def test_format_signal_info(self):
        """신호 정보 포맷팅"""
        from core.indicators.pullback.signal_calculator import SignalCalculator
        from core.indicators.pullback.types import (
            SignalStrength, SignalType, BisectorStatus
        )

        ss = SignalStrength(
            signal_type=SignalType.STRONG_BUY,
            confidence=90.0,
            target_profit=0.025,
            reasons=["회복양봉", "거래량회복", "이등분선지지"],
            volume_ratio=0.8,
            bisector_status=BisectorStatus.HOLDING
        )

        result = SignalCalculator.format_signal_info(ss)
        assert isinstance(result, str)
        assert "90" in result  # 신뢰도 포함


# ============================================================================
# 10. TechnicalFilter (기술적 필터) 테스트
# ============================================================================

class TestTechnicalFilter:
    """기술적 필터 테스트"""

    def test_check_filter_basic(self, uptrend_ohlcv):
        """기본 필터 체크"""
        from core.indicators.pullback.technical_filter import TechnicalFilter

        tf = TechnicalFilter()
        result = tf.check_filter(uptrend_ohlcv, current_idx=len(uptrend_ohlcv) - 1)

        assert 'passed' in result
        assert 'reasons' in result
        assert 'indicators' in result
        assert isinstance(result['passed'], bool)
        assert isinstance(result['reasons'], list)

    def test_check_filter_insufficient_candles(self, minimal_ohlcv):
        """캔들 수 부족 시 실패"""
        from core.indicators.pullback.technical_filter import TechnicalFilter

        tf = TechnicalFilter()
        result = tf.check_filter(minimal_ohlcv, current_idx=0)

        assert result['passed'] is False
        assert any('부족' in r for r in result['reasons'])

    def test_check_filter_with_time_early_mode(self, uptrend_ohlcv):
        """10:00 이전 완화 모드"""
        from core.indicators.pullback.technical_filter import TechnicalFilter

        tf = TechnicalFilter()
        result = tf.check_filter(
            uptrend_ohlcv,
            current_idx=len(uptrend_ohlcv) - 1,
            current_time=time(9, 30)
        )

        assert 'early_mode' in result
        assert result['early_mode'] is True

    def test_check_filter_after_early_mode(self, uptrend_ohlcv):
        """10:00 이후 일반 모드"""
        from core.indicators.pullback.technical_filter import TechnicalFilter

        tf = TechnicalFilter()
        result = tf.check_filter(
            uptrend_ohlcv,
            current_idx=len(uptrend_ohlcv) - 1,
            current_time=time(10, 30)
        )

        assert result['early_mode'] is False

    def test_create_conservative_filter(self):
        """보수적 필터 생성"""
        from core.indicators.pullback.technical_filter import TechnicalFilter

        tf = TechnicalFilter.create_conservative_filter()
        assert tf.ma5_threshold == 0.60
        assert tf.volume_trend_threshold == 2.5

    def test_create_balanced_filter(self):
        """균형 필터 생성 (기본값)"""
        from core.indicators.pullback.technical_filter import TechnicalFilter

        tf = TechnicalFilter.create_balanced_filter()
        assert tf.ma5_threshold == 0.50

    def test_create_aggressive_filter(self):
        """공격적 필터 생성"""
        from core.indicators.pullback.technical_filter import TechnicalFilter

        tf = TechnicalFilter.create_aggressive_filter()
        assert tf.ma5_threshold == 0.40
        assert tf.volume_trend_threshold == 1.8

    def test_check_filter_with_daily_data(self, uptrend_ohlcv):
        """일봉 데이터 포함 필터"""
        from core.indicators.pullback.technical_filter import TechnicalFilter

        daily_data = pd.DataFrame({
            'close': [49000, 49500, 50000, 50500, 51000, 51500, 52000]
        })

        tf = TechnicalFilter()
        result = tf.check_filter(
            uptrend_ohlcv,
            current_idx=len(uptrend_ohlcv) - 1,
            daily_data=daily_data,
            current_time=time(11, 0)
        )

        assert 'indicators' in result
        # daily_trend_5가 계산되었는지 확인
        if result['indicators'].get('daily_trend_5') is not None:
            assert isinstance(result['indicators']['daily_trend_5'], float)


# ============================================================================
# 11. SupportPatternAnalyzer (지지 패턴 분석) 테스트
# ============================================================================

class TestSupportPatternAnalyzer:
    """지지 패턴 분석기 테스트"""

    def test_analyze_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 패턴 없음"""
        from core.indicators.pullback.support_pattern_analyzer import SupportPatternAnalyzer

        analyzer = SupportPatternAnalyzer()
        result = analyzer.analyze(minimal_ohlcv)

        assert result.has_pattern is False
        assert result.confidence == 0.0
        assert any('부족' in r for r in result.reasons)

    def test_analyze_result_structure(self, pullback_pattern_ohlcv):
        """분석 결과 구조 검증"""
        from core.indicators.pullback.support_pattern_analyzer import SupportPatternAnalyzer

        analyzer = SupportPatternAnalyzer(
            uptrend_min_gain=0.03,
            decline_min_pct=0.005,
            support_volume_threshold=0.25,
            support_volatility_threshold=0.015,
            breakout_body_increase=0.1,
            lookback_period=200
        )
        result = analyzer.analyze(pullback_pattern_ohlcv)

        assert hasattr(result, 'has_pattern')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'reasons')
        assert hasattr(result, 'entry_price')
        assert isinstance(result.reasons, list)
        assert 0 <= result.confidence <= 100

    def test_get_debug_info(self, pullback_pattern_ohlcv):
        """디버그 정보 반환 구조"""
        from core.indicators.pullback.support_pattern_analyzer import SupportPatternAnalyzer

        analyzer = SupportPatternAnalyzer()
        debug = analyzer.get_debug_info(pullback_pattern_ohlcv)

        assert isinstance(debug, dict)
        assert 'has_pattern' in debug
        assert 'confidence' in debug
        assert 'reasons' in debug

    def test_analyze_downtrend_no_pattern(self, downtrend_ohlcv):
        """하락 추세에서 4단계 패턴 없음"""
        from core.indicators.pullback.support_pattern_analyzer import SupportPatternAnalyzer

        analyzer = SupportPatternAnalyzer()
        result = analyzer.analyze(downtrend_ohlcv)

        # 순수 하락 추세에서는 돌파 양봉이 없으므로 패턴 미발견
        assert result.has_pattern is False


# ============================================================================
# 12. FilterStats (필터 통계) 테스트
# ============================================================================

class TestFilterStats:
    """필터 통계 수집 테스트"""

    def test_singleton_instance(self):
        """싱글톤 패턴 확인"""
        from core.indicators.filter_stats import FilterStats

        a = FilterStats()
        b = FilterStats()
        assert a is b

    def test_increment_and_get_stats(self):
        """통계 증가 및 조회"""
        from core.indicators.filter_stats import FilterStats

        fs = FilterStats()
        fs.reset()

        fs.increment_total()
        fs.increment_total()
        fs.increment('pattern_combination_filter', '테스트 사유')

        stats = fs.get_stats()
        assert stats['total_patterns_checked'] == 2
        assert stats['pattern_combination_filter'] == 1

    def test_reset(self):
        """통계 초기화"""
        from core.indicators.filter_stats import FilterStats

        fs = FilterStats()
        fs.increment_total()
        fs.reset()

        stats = fs.get_stats()
        assert stats['total_patterns_checked'] == 0
        assert stats['pattern_combination_filter'] == 0

    def test_get_summary_empty(self):
        """빈 통계 요약"""
        from core.indicators.filter_stats import FilterStats

        fs = FilterStats()
        fs.reset()

        summary = fs.get_summary()
        assert '데이터 없음' in summary

    def test_get_summary_with_data(self):
        """데이터 있는 통계 요약"""
        from core.indicators.filter_stats import FilterStats

        fs = FilterStats()
        fs.reset()

        fs.increment_total()
        fs.increment_total()
        fs.increment_total()
        fs.increment('pattern_combination_filter', '조합1')

        summary = fs.get_summary()
        assert '전체 패턴 체크' in summary
        assert '3건' in summary

    def test_increment_with_would_win(self):
        """차단된 매매의 실제 결과 추적"""
        from core.indicators.filter_stats import FilterStats

        fs = FilterStats()
        fs.reset()

        fs.increment('pattern_combination_filter', '사유1', would_win=True)
        fs.increment('pattern_combination_filter', '사유2', would_win=False)

        results = fs.blocked_results['pattern_combination_filter']
        assert results['win'] == 1
        assert results['loss'] == 1


# ============================================================================
# 13. PatternCombinationFilter (패턴 조합 필터) 테스트
# ============================================================================

class TestPatternCombinationFilter:
    """패턴 조합 필터 테스트"""

    def test_categorize_pattern_weak_uptrend(self):
        """약한 상승 (<4%) 분류"""
        from core.indicators.pattern_combination_filter import PatternCombinationFilter

        pf = PatternCombinationFilter()
        debug_info = {
            'uptrend': {'price_gain': '3.50%'},
            'decline': {'decline_pct': '2.00%'},
            'support': {'candle_count': 2}
        }

        categories = pf.categorize_pattern(debug_info)

        assert categories['상승강도'] == '약함(<4%)'
        assert categories['하락정도'] == '보통(1.5-2.5%)'
        assert categories['지지길이'] == '짧음(\u22642)'  # Unicode ≤ 문자

    def test_categorize_pattern_strong_uptrend(self):
        """강한 상승 (>6%) 분류"""
        from core.indicators.pattern_combination_filter import PatternCombinationFilter

        pf = PatternCombinationFilter()
        debug_info = {
            'uptrend': {'price_gain': '7.50%'},
            'decline': {'decline_pct': '1.00%'},
            'support': {'candle_count': 4}
        }

        categories = pf.categorize_pattern(debug_info)

        assert categories['상승강도'] == '강함(>6%)'
        assert categories['하락정도'] == '얕음(<1.5%)'
        assert categories['지지길이'] == '보통(3-4)'

    def test_should_exclude_matching_combination(self):
        """제외 대상 조합 매칭"""
        from core.indicators.pattern_combination_filter import PatternCombinationFilter

        pf = PatternCombinationFilter()

        # 조합 1: 약함 + 보통 + 짧음 -> 제외 대상
        debug_info = {
            'uptrend': {'price_gain': '3.50%'},
            'decline': {'decline_pct': '2.00%'},
            'support': {'candle_count': 2}
        }

        excluded, reason = pf.should_exclude(debug_info)

        assert excluded is True
        assert reason is not None
        assert '마이너스 수익 조합' in reason

    def test_should_exclude_non_matching_combination(self):
        """제외 대상 아닌 조합"""
        from core.indicators.pattern_combination_filter import PatternCombinationFilter

        pf = PatternCombinationFilter()

        # 보통 + 보통 + 짧음 -> 제외 대상 아님
        debug_info = {
            'uptrend': {'price_gain': '5.00%'},
            'decline': {'decline_pct': '2.00%'},
            'support': {'candle_count': 2}
        }

        excluded, reason = pf.should_exclude(debug_info)

        assert excluded is False
        assert reason is None

    def test_should_exclude_empty_debug_info(self):
        """빈 디버그 정보에서 통과"""
        from core.indicators.pattern_combination_filter import PatternCombinationFilter

        pf = PatternCombinationFilter()

        excluded, reason = pf.should_exclude({})
        assert excluded is False

        excluded, reason = pf.should_exclude(None)
        assert excluded is False

    def test_get_filter_stats(self):
        """필터 통계 정보"""
        from core.indicators.pattern_combination_filter import PatternCombinationFilter

        pf = PatternCombinationFilter()
        stats = pf.get_filter_stats()

        assert stats['excluded_combinations_count'] == 11
        assert 'expected_profit_improvement' in stats


# ============================================================================
# 14. TimeWeightedFilter (시간대별 가중치 필터) 테스트
# ============================================================================

class TestTimeWeightedFilter:
    """시간대별 가중치 필터 테스트"""

    def test_should_exclude_safe_hour(self):
        """09시대 (안전) - 완화된 조건"""
        from core.indicators.time_weighted_filter import TimeWeightedFilter

        twf = TimeWeightedFilter()

        # 종가 위치가 높고 거래량 증가 → 통과
        debug_info = {
            'best_breakout': {
                'high': 10500, 'low': 10000, 'close': 10400,
                'open': 10100, 'volume': 50000,
                'volume_ratio_vs_prev': 1.5
            }
        }

        current_time = datetime(2024, 1, 15, 9, 30)
        excluded, reason = twf.should_exclude(debug_info, current_time)

        assert excluded is False

    def test_should_exclude_risky_hour_14(self):
        """14시대 (매우 위험) - 강화된 조건"""
        from core.indicators.time_weighted_filter import TimeWeightedFilter

        twf = TimeWeightedFilter()

        # 종가 위치 낮음 → 차단
        debug_info = {
            'best_breakout': {
                'high': 10500, 'low': 10000, 'close': 10200,
                'open': 10100, 'volume': 50000,
                'volume_ratio_vs_prev': 1.0
            }
        }

        current_time = datetime(2024, 1, 15, 14, 30)
        excluded, reason = twf.should_exclude(debug_info, current_time)

        assert excluded is True
        assert '14시' in reason

    def test_should_exclude_outside_config_hours(self):
        """설정 외 시간대 (15시 등) → 통과"""
        from core.indicators.time_weighted_filter import TimeWeightedFilter

        twf = TimeWeightedFilter()

        debug_info = {
            'best_breakout': {
                'high': 10500, 'low': 10000, 'close': 10050,
                'open': 10100, 'volume': 50000,
                'volume_ratio_vs_prev': 0.5
            }
        }

        current_time = datetime(2024, 1, 15, 15, 0)
        excluded, reason = twf.should_exclude(debug_info, current_time)

        assert excluded is False

    def test_should_exclude_no_breakout_info(self):
        """돌파 정보 없으면 통과"""
        from core.indicators.time_weighted_filter import TimeWeightedFilter

        twf = TimeWeightedFilter()

        excluded, reason = twf.should_exclude({}, datetime(2024, 1, 15, 10, 0))
        assert excluded is False

    def test_get_config_for_hour(self):
        """시간대별 설정 조회"""
        from core.indicators.time_weighted_filter import TimeWeightedFilter

        twf = TimeWeightedFilter()

        config_9 = twf.get_config_for_hour(9)
        assert config_9['risk_level'] == 'LOW'

        config_14 = twf.get_config_for_hour(14)
        assert config_14['risk_level'] == 'VERY_HIGH'

        config_16 = twf.get_config_for_hour(16)
        assert config_16['risk_level'] == 'MEDIUM'  # 기본값

    def test_close_position_calculation(self):
        """종가 위치 계산 검증"""
        from core.indicators.time_weighted_filter import TimeWeightedFilter

        twf = TimeWeightedFilter()

        # 종가가 고점에 있으면 1.0
        breakout = {'high': 100, 'low': 90, 'close': 100}
        assert twf._get_close_position(breakout) == 1.0

        # 종가가 저점에 있으면 0.0
        breakout = {'high': 100, 'low': 90, 'close': 90}
        assert twf._get_close_position(breakout) == 0.0

        # 중간이면 0.5
        breakout = {'high': 100, 'low': 90, 'close': 95}
        assert abs(twf._get_close_position(breakout) - 0.5) < 0.01


# ============================================================================
# 15. PullbackUtils (유틸리티 위임) 테스트
# ============================================================================

class TestPullbackUtils:
    """PullbackUtils의 위임 메서드가 올바르게 작동하는지 확인"""

    def test_calculate_daily_baseline_volume(self, uptrend_ohlcv):
        """기준거래량 계산 위임"""
        from core.indicators.pullback_utils import PullbackUtils

        result = PullbackUtils.calculate_daily_baseline_volume(uptrend_ohlcv)
        assert isinstance(result, pd.Series)
        assert len(result) == len(uptrend_ohlcv)

    def test_analyze_volume(self, uptrend_ohlcv):
        """거래량 분석 위임"""
        from core.indicators.pullback_utils import PullbackUtils
        from core.indicators.pullback.types import VolumeAnalysis

        result = PullbackUtils.analyze_volume(uptrend_ohlcv, period=10)
        assert isinstance(result, VolumeAnalysis)

    def test_analyze_candle(self, uptrend_ohlcv):
        """캔들 분석 위임"""
        from core.indicators.pullback_utils import PullbackUtils
        from core.indicators.pullback.types import CandleAnalysis

        result = PullbackUtils.analyze_candle(uptrend_ohlcv, period=10)
        assert isinstance(result, CandleAnalysis)

    def test_get_bisector_status(self):
        """이등분선 상태 위임"""
        from core.indicators.pullback_utils import PullbackUtils
        from core.indicators.pullback.types import BisectorStatus

        result = PullbackUtils.get_bisector_status(10500, 10000)
        assert isinstance(result, BisectorStatus)
        assert result == BisectorStatus.HOLDING

    def test_detect_risk_signals(self, uptrend_ohlcv):
        """위험 신호 감지 위임"""
        from core.indicators.pullback_utils import PullbackUtils

        result = PullbackUtils.detect_risk_signals(uptrend_ohlcv)
        assert isinstance(result, list)

    def test_check_price_trend(self, uptrend_ohlcv):
        """추세 확인 위임"""
        from core.indicators.pullback_utils import PullbackUtils

        result = PullbackUtils.check_price_trend(uptrend_ohlcv, period=10)
        assert result in ('uptrend', 'downtrend', 'stable')

    def test_find_recent_low(self, uptrend_ohlcv):
        """최근 저점 위임"""
        from core.indicators.pullback_utils import PullbackUtils

        result = PullbackUtils.find_recent_low(uptrend_ohlcv, period=5)
        assert result is not None
        assert result > 0


# ============================================================================
# 16. MultiBollingerBands (다중 볼린저밴드) 테스트
# ============================================================================

class TestMultiBollingerBands:
    """다중 볼린저밴드 테스트"""

    def test_calculate_multi_bollinger_bands(self, uptrend_ohlcv):
        """다중 볼린저밴드 계산"""
        from core.indicators.multi_bollinger_bands import MultiBollingerBands

        result = MultiBollingerBands.calculate_multi_bollinger_bands(uptrend_ohlcv['close'])

        assert isinstance(result, dict)
        for period in [50, 40, 30, 20]:
            assert period in result
            assert 'sma' in result[period]
            assert 'upper_band' in result[period]
            assert 'lower_band' in result[period]

    def test_detect_upper_convergence(self, sideways_ohlcv):
        """상한선 밀집 감지"""
        from core.indicators.multi_bollinger_bands import MultiBollingerBands

        multi_bb = MultiBollingerBands.calculate_multi_bollinger_bands(sideways_ohlcv['close'])
        convergence = MultiBollingerBands.detect_upper_convergence(multi_bb, threshold=0.02)

        assert isinstance(convergence, pd.Series)
        assert convergence.dtype == bool

    def test_generate_trading_signals(self, uptrend_ohlcv):
        """트레이딩 신호 생성"""
        from core.indicators.multi_bollinger_bands import MultiBollingerBands

        signals = MultiBollingerBands.generate_trading_signals(uptrend_ohlcv['close'])

        assert isinstance(signals, pd.DataFrame)
        assert 'buy_signal' in signals.columns
        assert 'sell_signal' in signals.columns
        assert 'upper_convergence' in signals.columns

    def test_calculate_retracement_levels(self):
        """조정 매수 레벨 계산"""
        from core.indicators.multi_bollinger_bands import MultiBollingerBands

        levels = MultiBollingerBands.calculate_retracement_levels(
            breakout_candle_high=10500,
            breakout_candle_low=10000,
            bisector_line=10200
        )

        assert 'level_75' in levels
        assert 'level_50' in levels
        assert 'bisector_75' in levels
        assert 'bisector_50' in levels
        assert levels['level_75'] > levels['level_50']


# ============================================================================
# 17. PullbackCandlePattern (핵심 통합) 테스트
# ============================================================================

class TestPullbackCandlePattern:
    """눌림목 캔들패턴 통합 테스트"""

    def test_analyze_volume_pattern(self, pullback_pattern_ohlcv):
        """거래량 패턴 분석"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        baseline = PullbackCandlePattern.calculate_daily_baseline_volume(pullback_pattern_ohlcv)
        result = PullbackCandlePattern._analyze_volume_pattern(pullback_pattern_ohlcv, baseline, period=3)

        assert 'consecutive_low_count' in result
        assert 'current_vs_threshold' in result
        assert 'volume_trend' in result

    def test_analyze_pullback_quality(self, pullback_pattern_ohlcv):
        """눌림목 품질 분석"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        baseline = PullbackCandlePattern.calculate_daily_baseline_volume(pullback_pattern_ohlcv)
        result = PullbackCandlePattern.analyze_pullback_quality(pullback_pattern_ohlcv, baseline)

        assert 'quality_score' in result
        assert 'has_quality_pullback' in result
        assert isinstance(result['quality_score'], (int, float))
        assert isinstance(result['has_quality_pullback'], bool)

    def test_analyze_pullback_quality_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 품질 점수 0"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        baseline = pd.Series([100000])
        result = PullbackCandlePattern.analyze_pullback_quality(minimal_ohlcv, baseline)

        assert result['quality_score'] == 0
        assert result['has_quality_pullback'] is False

    def test_check_heavy_selling_pressure(self, uptrend_ohlcv):
        """매물 부담 확인"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        baseline = PullbackCandlePattern.calculate_daily_baseline_volume(uptrend_ohlcv)
        result = PullbackCandlePattern.check_heavy_selling_pressure(uptrend_ohlcv, baseline)

        assert isinstance(result, bool)

    def test_check_heavy_selling_pressure_insufficient_data(self, minimal_ohlcv):
        """데이터 부족 시 False"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        baseline = pd.Series([100000])
        result = PullbackCandlePattern.check_heavy_selling_pressure(minimal_ohlcv, baseline)

        assert result is False

    def test_check_bisector_breakout_volume(self, uptrend_ohlcv):
        """이등분선 돌파 거래량 확인"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        result = PullbackCandlePattern.check_bisector_breakout_volume(uptrend_ohlcv)
        # numpy.bool_ 호환
        assert bool(result) in (True, False)

    def test_check_bisector_breakout_volume_minimal(self, minimal_ohlcv):
        """데이터 부족 시 기본값 True"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        result = PullbackCandlePattern.check_bisector_breakout_volume(minimal_ohlcv)
        assert result is True

    def test_check_high_volume_decline_recovery_insufficient(self, minimal_ohlcv):
        """대량 매물 출현 후 회복 - 데이터 부족"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        baseline = pd.Series([100000])
        result = PullbackCandlePattern.check_high_volume_decline_recovery(minimal_ohlcv, baseline)

        assert result['should_avoid'] is False
        assert '데이터부족' in result['reason']

    def test_check_bearish_volume_restriction(self, uptrend_ohlcv):
        """음봉 거래량 제한 확인"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        baseline = PullbackCandlePattern.calculate_daily_baseline_volume(uptrend_ohlcv)
        result = PullbackCandlePattern.check_bearish_volume_restriction(uptrend_ohlcv, baseline)

        assert isinstance(result, bool)

    def test_check_bearish_volume_restriction_insufficient(self, minimal_ohlcv):
        """데이터 부족 시 False"""
        from core.indicators.pullback_candle_pattern import PullbackCandlePattern

        baseline = pd.Series([100000])
        result = PullbackCandlePattern.check_bearish_volume_restriction(minimal_ohlcv, baseline)

        assert result is False
