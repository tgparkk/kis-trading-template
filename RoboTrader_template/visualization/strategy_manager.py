"""
거래 전략 관리 클래스
기존 TradingStrategyConfig를 개선하고 확장

전략 설정은 config/visualization_strategies.yaml에서 로드됨
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Any
from utils.logger import setup_logger

import yaml


@dataclass
class TradingStrategy:
    """거래 전략 설정"""
    name: str
    timeframe: str  # "1min", "3min", or "5min"
    indicators: List[str]
    description: str
    enabled: bool = True
    priority: int = 1  # 우선순위 (낮을수록 높은 우선순위)


@dataclass
class ChartData:
    """차트 데이터와 전략 정보"""
    stock_code: str
    stock_name: str
    timeframe: str
    strategy: TradingStrategy
    price_data: Any  # pd.DataFrame
    indicators_data: Dict[str, Any] = field(default_factory=dict)


class StrategyManager:
    """거래 전략 관리 클래스

    전략 설정은 config/visualization_strategies.yaml에서 로드됨
    """

    # 설정 파일 경로
    CONFIG_FILE = Path("config/visualization_strategies.yaml")

    # 기본 전략 (설정 파일 로드 실패 시 사용)
    DEFAULT_STRATEGIES = {
        "strategy1": TradingStrategy(
            name="가격박스+이등분선",
            timeframe="1min",
            indicators=["price_box", "bisector_line"],
            description="가격박스 지지/저항선과 이등분선을 활용한 매매",
            priority=1
        ),
        "strategy2": TradingStrategy(
            name="다중볼린저밴드+이등분선",
            timeframe="5min",
            indicators=["multi_bollinger_bands", "bisector_line"],
            description="다중 볼린저밴드와 이등분선을 활용한 매매 (5분봉)",
            priority=2
        ),
        "strategy3": TradingStrategy(
            name="다중볼린저밴드",
            timeframe="5min",
            indicators=["multi_bollinger_bands"],
            description="여러 기간의 볼린저밴드를 활용한 매매 (5분봉)",
            priority=3
        )
    }

    # 기본 지표 목록 (설정 파일 로드 실패 시 사용)
    DEFAULT_VALID_INDICATORS = [
        "price_box", "bisector_line", "bollinger_bands",
        "multi_bollinger_bands", "pullback_candle_pattern"
    ]

    # 기본 시간 프레임 (설정 파일 로드 실패 시 사용)
    DEFAULT_VALID_TIMEFRAMES = ["1min", "3min", "5min"]

    def __init__(self, config_path: Optional[Path] = None):
        """초기화

        Args:
            config_path: 설정 파일 경로 (기본: config/visualization_strategies.yaml)
        """
        self.logger = setup_logger(__name__)
        self.config_path = config_path or self.CONFIG_FILE

        # 설정 로드
        self._config: Dict[str, Any] = {}
        self.strategies: Dict[str, TradingStrategy] = {}
        self.strategy_aliases: Dict[str, str] = {}
        self.valid_indicators: List[str] = self.DEFAULT_VALID_INDICATORS.copy()
        self.valid_timeframes: List[str] = self.DEFAULT_VALID_TIMEFRAMES.copy()

        self._load_config()
        self.logger.info("전략 관리자 초기화 완료")

    def _load_config(self):
        """설정 파일에서 전략 로드"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {}

                # 전략 로드
                strategies_config = self._config.get('strategies', {})
                for strategy_id, strategy_data in strategies_config.items():
                    self.strategies[strategy_id] = TradingStrategy(
                        name=strategy_data.get('name', strategy_id),
                        timeframe=strategy_data.get('timeframe', '1min'),
                        indicators=strategy_data.get('indicators', []),
                        description=strategy_data.get('description', ''),
                        enabled=strategy_data.get('enabled', True),
                        priority=strategy_data.get('priority', 1)
                    )

                # 별칭 로드
                self.strategy_aliases = self._config.get('aliases', {})

                # 유효 지표 로드
                if 'valid_indicators' in self._config:
                    self.valid_indicators = self._config['valid_indicators']

                # 유효 시간 프레임 로드
                if 'valid_timeframes' in self._config:
                    self.valid_timeframes = self._config['valid_timeframes']

                self.logger.info(f"설정 파일 로드 완료: {self.config_path}")
                self.logger.info(f"  - 로드된 전략: {len(self.strategies)}개")
                self.logger.info(f"  - 별칭 매핑: {len(self.strategy_aliases)}개")
            else:
                self.logger.warning(f"설정 파일 없음: {self.config_path}, 기본 전략 사용")
                self.strategies = self.DEFAULT_STRATEGIES.copy()

        except Exception as e:
            self.logger.error(f"설정 파일 로드 오류: {e}, 기본 전략 사용")
            self.strategies = self.DEFAULT_STRATEGIES.copy()

    def get_strategy(self, strategy_name: str) -> Optional[TradingStrategy]:
        """전략 정보 조회

        Args:
            strategy_name: 전략 이름 또는 별칭

        Returns:
            TradingStrategy 또는 None
        """
        # 별칭 변환
        actual_name = self.strategy_aliases.get(strategy_name, strategy_name)
        return self.strategies.get(actual_name)

    def get_all_strategies(self) -> Dict[str, TradingStrategy]:
        """모든 전략 정보 조회"""
        return self.strategies

    def get_enabled_strategies(self) -> Dict[str, TradingStrategy]:
        """활성화된 전략들만 조회"""
        return {name: strategy for name, strategy in self.strategies.items()
                if strategy.enabled}

    def get_strategies_by_priority(self) -> List[tuple]:
        """우선순위 순으로 정렬된 전략 리스트 반환"""
        enabled_strategies = self.get_enabled_strategies()
        return sorted(enabled_strategies.items(), key=lambda x: x[1].priority)

    def enable_strategy(self, strategy_name: str) -> bool:
        """전략 활성화"""
        actual_name = self.strategy_aliases.get(strategy_name, strategy_name)
        if actual_name in self.strategies:
            self.strategies[actual_name].enabled = True
            self.logger.info(f"전략 활성화: {actual_name}")
            return True
        return False

    def disable_strategy(self, strategy_name: str) -> bool:
        """전략 비활성화"""
        actual_name = self.strategy_aliases.get(strategy_name, strategy_name)
        if actual_name in self.strategies:
            self.strategies[actual_name].enabled = False
            self.logger.info(f"전략 비활성화: {actual_name}")
            return True
        return False

    def add_custom_strategy(self, strategy_name: str, strategy: TradingStrategy) -> bool:
        """사용자 정의 전략 추가"""
        try:
            self.strategies[strategy_name] = strategy
            self.logger.info(f"사용자 정의 전략 추가: {strategy_name}")
            return True
        except Exception as e:
            self.logger.error(f"전략 추가 실패: {e}")
            return False

    def add_alias(self, alias: str, strategy_name: str) -> bool:
        """전략 별칭 추가

        Args:
            alias: 별칭
            strategy_name: 실제 전략 이름

        Returns:
            성공 여부
        """
        if strategy_name in self.strategies:
            self.strategy_aliases[alias] = strategy_name
            self.logger.info(f"별칭 추가: {alias} -> {strategy_name}")
            return True
        self.logger.warning(f"전략 없음: {strategy_name}")
        return False

    def remove_strategy(self, strategy_name: str) -> bool:
        """전략 제거"""
        actual_name = self.strategy_aliases.get(strategy_name, strategy_name)

        if actual_name in self.strategies:
            del self.strategies[actual_name]
            # 해당 전략을 가리키는 별칭도 제거
            aliases_to_remove = [k for k, v in self.strategy_aliases.items() if v == actual_name]
            for alias in aliases_to_remove:
                del self.strategy_aliases[alias]
            self.logger.info(f"전략 제거: {actual_name}")
            return True
        return False

    def update_strategy_priority(self, strategy_name: str, new_priority: int) -> bool:
        """전략 우선순위 변경"""
        actual_name = self.strategy_aliases.get(strategy_name, strategy_name)
        if actual_name in self.strategies:
            old_priority = self.strategies[actual_name].priority
            self.strategies[actual_name].priority = new_priority
            self.logger.info(f"전략 우선순위 변경: {actual_name} ({old_priority} -> {new_priority})")
            return True
        return False

    def get_strategy_summary(self) -> Dict[str, Any]:
        """전략 현황 요약"""
        total_strategies = len(self.strategies)
        enabled_strategies = len(self.get_enabled_strategies())

        strategy_list = []
        for name, strategy in self.strategies.items():
            strategy_list.append({
                'name': name,
                'display_name': strategy.name,
                'timeframe': strategy.timeframe,
                'indicators': strategy.indicators,
                'enabled': strategy.enabled,
                'priority': strategy.priority
            })

        return {
            'total_strategies': total_strategies,
            'enabled_strategies': enabled_strategies,
            'disabled_strategies': total_strategies - enabled_strategies,
            'strategies': strategy_list,
            'aliases': self.strategy_aliases.copy()
        }

    def validate_strategy(self, strategy: TradingStrategy) -> bool:
        """전략 유효성 검증"""
        try:
            # 필수 필드 검증
            if not strategy.name or not strategy.timeframe:
                return False

            # 시간프레임 검증
            if strategy.timeframe not in self.valid_timeframes:
                return False

            # 지표 검증
            if not strategy.indicators or not all(ind in self.valid_indicators for ind in strategy.indicators):
                return False

            return True

        except Exception as e:
            self.logger.error(f"전략 검증 오류: {e}")
            return False

    def reload_config(self):
        """설정 파일 다시 로드"""
        self.strategies.clear()
        self.strategy_aliases.clear()
        self._load_config()
        self.logger.info("설정 파일 다시 로드 완료")

    def reset_to_defaults(self):
        """기본 전략으로 리셋"""
        self.strategies = self.DEFAULT_STRATEGIES.copy()
        self.strategy_aliases.clear()
        self.valid_indicators = self.DEFAULT_VALID_INDICATORS.copy()
        self.valid_timeframes = self.DEFAULT_VALID_TIMEFRAMES.copy()
        self.logger.info("전략을 기본값으로 리셋")

    def save_config(self, config_path: Optional[Path] = None) -> bool:
        """현재 전략 설정을 YAML 파일로 저장

        Args:
            config_path: 저장할 경로 (기본: 원본 경로)

        Returns:
            성공 여부
        """
        save_path = config_path or self.config_path

        try:
            config_data = {
                'strategies': {},
                'aliases': self.strategy_aliases,
                'valid_indicators': self.valid_indicators,
                'valid_timeframes': self.valid_timeframes
            }

            for strategy_id, strategy in self.strategies.items():
                config_data['strategies'][strategy_id] = {
                    'name': strategy.name,
                    'timeframe': strategy.timeframe,
                    'indicators': strategy.indicators,
                    'description': strategy.description,
                    'enabled': strategy.enabled,
                    'priority': strategy.priority
                }

            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            self.logger.info(f"설정 파일 저장 완료: {save_path}")
            return True

        except Exception as e:
            self.logger.error(f"설정 파일 저장 실패: {e}")
            return False


# 하위 호환성을 위한 별칭
TradingStrategyConfig = StrategyManager
