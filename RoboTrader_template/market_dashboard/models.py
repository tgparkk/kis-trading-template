"""시장현황 대시보드 데이터 모델"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class IndexData:
    """주가지수 데이터"""
    name: str
    value: float
    change: float = 0.0
    change_rate: float = 0.0
    volume: int = 0
    trade_amount: float = 0.0  # 거래대금 (억원)
    timestamp: Optional[datetime] = None


@dataclass
class InvestorFlow:
    """투자자별 매매동향"""
    foreign_net: float = 0.0      # 외국인 순매수 (억원)
    institution_net: float = 0.0  # 기관 순매수 (억원)
    individual_net: float = 0.0   # 개인 순매수 (억원)
    timestamp: Optional[datetime] = None


@dataclass
class ExchangeRate:
    """환율 데이터"""
    pair: str
    rate: float
    change: float = 0.0
    change_rate: float = 0.0
    timestamp: Optional[datetime] = None


@dataclass
class RankedStock:
    """순위 종목"""
    rank: int
    stock_code: str
    stock_name: str
    current_price: float = 0.0
    change_rate: float = 0.0
    volume: int = 0


@dataclass
class PositionSummary:
    """보유 포지션 요약"""
    stock_code: str
    stock_name: str
    quantity: int
    avg_price: float
    current_price: float
    profit_loss: float = 0.0
    profit_loss_rate: float = 0.0
    state: str = ""


@dataclass
class GlobalMarketSnapshot:
    """해외 시장 스냅샷"""
    indices: List[IndexData] = field(default_factory=list)
    exchange_rates: List[ExchangeRate] = field(default_factory=list)
    timestamp: Optional[datetime] = None


@dataclass
class DomesticMarketSnapshot:
    """국내 시장 스냅샷"""
    kospi: Optional[IndexData] = None
    kosdaq: Optional[IndexData] = None
    investor_flow: Optional[InvestorFlow] = None
    volume_rank: List[RankedStock] = field(default_factory=list)
    timestamp: Optional[datetime] = None


@dataclass
class PremarketBriefing:
    """장전 브리핑 종합 데이터"""
    global_market: Optional[GlobalMarketSnapshot] = None
    domestic_prev_close: Optional[DomesticMarketSnapshot] = None
    briefing_time: Optional[datetime] = None


@dataclass
class MarketDashboardData:
    """장중 대시보드 종합 데이터"""
    domestic: Optional[DomesticMarketSnapshot] = None
    positions: List[PositionSummary] = field(default_factory=list)
    total_profit_loss: float = 0.0
    total_eval_amount: float = 0.0
    dashboard_time: Optional[datetime] = None
