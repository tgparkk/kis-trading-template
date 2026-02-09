"""
장중 종목 데이터 모델
"""
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import pandas as pd


@dataclass
class StockMinuteData:
    """종목별 분봉 데이터 클래스"""
    stock_code: str
    stock_name: str
    selected_time: datetime
    historical_data: pd.DataFrame = field(default_factory=pd.DataFrame)  # 오늘 분봉 데이터
    realtime_data: pd.DataFrame = field(default_factory=pd.DataFrame)    # 실시간 분봉 데이터
    daily_data: pd.DataFrame = field(default_factory=pd.DataFrame)       # 과거 29일 일봉 데이터 (가격박스용)
    current_price_info: Optional[Dict[str, Any]] = None                  # 매도용 실시간 현재가 정보
    last_update: Optional[datetime] = None
    data_complete: bool = False

    def __post_init__(self) -> None:
        """초기화 후 처리"""
        if self.last_update is None:
            self.last_update = self.selected_time
