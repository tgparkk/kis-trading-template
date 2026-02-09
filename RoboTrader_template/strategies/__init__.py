"""
Strategies Module
=================

전략 프레임워크 및 구현체 통합 모듈

Framework:
    - BaseStrategy: 전략 추상 기본 클래스
    - Signal: 매매 신호 데이터클래스
    - SignalType: 신호 타입 열거형
    - OrderInfo: 체결 정보 데이터클래스
    - StrategyConfig: 전략 설정 관리
    - StrategyLoader: 전략 동적 로더
    - StrategyConfigError: 전략 설정 오류

Implementations:
    - SampleStrategy: 샘플 전략 구현체

Utils:
    - load_yaml_config: YAML 설정 로드
    - merge_configs: 설정 병합
"""

# Framework imports
from .base import (
    BaseStrategy,
    Signal,
    SignalType,
    OrderInfo
)

from .config import (
    StrategyConfig,
    StrategyLoader,
    StrategyConfigError,
    load_yaml_config,
    merge_configs
)

# Implementation imports
from .sample import SampleStrategy
from .momentum import MomentumStrategy
from .mean_reversion import MeanReversionStrategy
from .volume_breakout import VolumeBreakoutStrategy

__all__ = [
    # Framework - Base
    'BaseStrategy',
    'Signal',
    'SignalType',
    'OrderInfo',

    # Framework - Config
    'StrategyConfig',
    'StrategyLoader',
    'StrategyConfigError',
    'load_yaml_config',
    'merge_configs',

    # Implementations
    'SampleStrategy',
    'MomentumStrategy',
    'MeanReversionStrategy',
    'VolumeBreakoutStrategy',
]

__version__ = '1.0.0'
