"""
TradingContext - 전략에게 제공되는 안전한 도구 모음

전략의 on_tick() 메서드에서 사용하는 컨텍스트 객체입니다.
내부적으로 기존 컴포넌트들(trading_manager, decision_engine, fund_manager 등)을
래핑하여 전략에게 간결한 인터페이스를 제공합니다.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

import pandas as pd

from utils.logger import setup_logger
from utils.korean_time import now_kst, is_market_open
from config.market_hours import MarketHours, MarketPhase

if TYPE_CHECKING:
    from core.trading_stock_manager import TradingStockManager
    from core.trading_decision_engine import TradingDecisionEngine
    from core.fund_manager import FundManager
    from core.data_collector import RealTimeDataCollector
    from core.intraday_stock_manager import IntradayStockManager
    from core.models import TradingStock
    from bot.trading_analyzer import TradingAnalyzer
    from db.database_manager import DatabaseManager
    from utils.tick_tracer import TickTracer


class TradingContext:
    """전략이 on_tick()에서 사용하는 컨텍스트. 모든 안전장치 내장."""

    def __init__(
        self,
        trading_manager: 'TradingStockManager',
        decision_engine: 'TradingDecisionEngine',
        fund_manager: 'FundManager',
        data_collector: 'RealTimeDataCollector',
        intraday_manager: 'IntradayStockManager',
        trading_analyzer: 'TradingAnalyzer',
        db_manager: 'DatabaseManager',
        broker=None,
        is_running_check=None,
        tracer: Optional['TickTracer'] = None,
        strategy_name: str = "",
        strategies_dict: Optional[Dict] = None,
    ):
        self._trading_manager = trading_manager
        self._decision_engine = decision_engine
        self._fund_manager = fund_manager
        self._data_collector = data_collector
        self._intraday_manager = intraday_manager
        self._trading_analyzer = trading_analyzer
        self._db_manager = db_manager
        self._broker = broker
        self._is_running_check = is_running_check
        self.tracer: Optional['TickTracer'] = tracer
        self._current_strategy_name: str = strategy_name
        self._strategies_dict: Dict = strategies_dict or {}
        self.logger = setup_logger("trading_context")
        # 일봉 조회 실패 로그 쓰로틀: key=(stock_code, reason), value=마지막 로그 시각
        self._daily_log_cache: Dict[Tuple[str, str], datetime] = {}
        self._daily_log_interval = timedelta(minutes=10)

    # =========================================================================
    # a) 시장 상태
    # =========================================================================

    def is_market_open(self) -> bool:
        """장이 열려 있는지 확인 (MarketHours 래핑)"""
        return is_market_open()

    def get_market_phase(self) -> str:
        """현재 시장 단계 반환 (MarketPhase.value 문자열)"""
        phase = MarketHours.get_market_phase('KRX')
        return phase.value

    def get_current_time(self) -> datetime:
        """현재 한국 시간 반환"""
        return now_kst()

    # =========================================================================
    # b) 데이터 조회
    # =========================================================================

    async def get_daily_data(self, stock_code: str, days: int = 60) -> Optional[pd.DataFrame]:
        """일봉 데이터 조회 (DB에서)

        Args:
            stock_code: 종목코드
            days: 조회 일수 (기본 60일)

        Returns:
            DataFrame or None
        """
        try:
            if self._db_manager and hasattr(self._db_manager, 'price_repo'):
                data = self._db_manager.price_repo.get_daily_prices(stock_code, days=days)
                if data is not None and not data.empty:
                    return data
                # 데이터가 비어 있거나 None인 경우 10분에 1회 INFO 로그
                reason = "empty" if (data is not None) else "none"
                key = (stock_code, f"daily_{reason}")
                now = datetime.now()
                last = self._daily_log_cache.get(key)
                if last is None or now - last >= self._daily_log_interval:
                    self._daily_log_cache[key] = now
                    cnt = len(data) if data is not None else 0
                    self.logger.info(
                        f"[일봉조회] {stock_code}: DB 반환 {cnt}건 (days={days}) — 데이터 없음"
                    )
            else:
                key = (stock_code, "no_db")
                now = datetime.now()
                last = self._daily_log_cache.get(key)
                if last is None or now - last >= self._daily_log_interval:
                    self._daily_log_cache[key] = now
                    self.logger.info(f"[일봉조회] {stock_code}: db_manager 없음 — 스킵")
            return None
        except Exception as e:
            self.logger.debug(f"일봉 데이터 조회 실패 ({stock_code}): {e}")
            return None

    async def get_intraday_data(self, stock_code: str) -> Optional[pd.DataFrame]:
        """분봉(장중) 데이터 조회 (intraday_manager 래핑)

        Args:
            stock_code: 종목코드

        Returns:
            DataFrame or None
        """
        try:
            if self._intraday_manager:
                data = self._intraday_manager.get_combined_chart_data(stock_code)
                if data is not None and not data.empty:
                    return data
            return None
        except Exception as e:
            self.logger.debug(f"분봉 데이터 조회 실패 ({stock_code}): {e}")
            return None

    async def get_current_price(self, stock_code: str) -> Optional[float]:
        """현재가 조회

        1순위: intraday_manager 캐시
        2순위: broker API

        Args:
            stock_code: 종목코드

        Returns:
            현재가 or None
        """
        try:
            # 1순위: intraday_manager 캐시
            if self._intraday_manager and hasattr(self._intraday_manager, 'get_cached_current_price'):
                price_info = self._intraday_manager.get_cached_current_price(stock_code)
                if price_info and price_info.get('current_price', 0) > 0:
                    return float(price_info['current_price'])
            # 2순위: broker API
            if self._broker:
                price = self._broker.get_current_price(stock_code)
                if price is not None and isinstance(price, (int, float)) and price > 0:
                    return float(price)
        except Exception as e:
            self.logger.debug(f"현재가 조회 실패 ({stock_code}): {e}")
        return None

    # =========================================================================
    # c) 종목 관리
    # =========================================================================

    def get_selected_stocks(self) -> List:
        """SELECTED 상태 종목 목록 반환"""
        from core.models import StockState
        try:
            return self._trading_manager.get_stocks_by_state(StockState.SELECTED)
        except Exception as e:
            self.logger.debug(f"SELECTED 종목 조회 실패: {e}")
            return []

    def get_positions(self) -> List:
        """POSITIONED 상태 종목 목록 반환 (보유 중)"""
        from core.models import StockState
        try:
            return self._trading_manager.get_stocks_by_state(StockState.POSITIONED)
        except Exception as e:
            self.logger.debug(f"POSITIONED 종목 조회 실패: {e}")
            return []

    # =========================================================================
    # d) 주문 (기존 TradingAnalyzer 래핑)
    # =========================================================================

    async def buy(self, stock_code: str, quantity: int = None,
                  signal=None, **kwargs) -> Optional[str]:
        """매수 주문 (기존 TradingAnalyzer.analyze_buy_decision 래핑)

        내부적으로 decision_engine.analyze_buy_decision() + execute_virtual_buy()를 호출합니다.
        기존 안전장치(FundManager 한도, 중복 주문 방지 등)는 기존 코드가 처리합니다.

        Args:
            stock_code: 종목코드
            quantity: 매수 수량 (None이면 자동 계산)
            signal: Signal 객체 (generate_signal에서 반환된 값)
            **kwargs: 추가 파라미터

        Returns:
            주문 성공 시 stock_code, 실패 시 None
        """
        try:
            # 시장 전체 서킷브레이커 발동 시 매수 스킵
            from config.market_hours import get_circuit_breaker_state
            cb_state = get_circuit_breaker_state()
            if cb_state.is_market_halted():
                self.logger.info("매수 판단 스킵: 시장 전체 서킷브레이커 발동 중")
                return None

            # 시장 방향성 필터: 폭락장 매수 스킵
            is_crashing, crash_reason = self._decision_engine.check_market_direction()
            if is_crashing:
                self.logger.info(f"매수 판단 스킵: 시장급락 ({crash_reason})")
                return None

            trading_stock = self._trading_manager.get_trading_stock(stock_code)
            if trading_stock is None:
                self.logger.debug(f"매수 스킵: {stock_code} 종목 정보 없음")
                return None

            # 중복 소유권 가드: POSITIONED/BUY_PENDING 상태 종목은 다른 전략이 매수 불가
            from core.models import StockState
            from core.trading.stock_state_manager import StockStateManager
            stock_state_mgr = getattr(self._trading_manager, 'stock_state_manager', None)
            if stock_state_mgr is not None:
                existing = stock_state_mgr.trading_stocks.get(stock_code)
                if existing is not None and existing.state in (
                    StockState.POSITIONED, StockState.BUY_PENDING
                ):
                    existing_owner = existing.owner_strategy_name or "unknown"
                    self.logger.info(
                        f"매수 거부: {stock_code}는 이미 {existing_owner} 소유 "
                        f"(state={existing.state.name}), "
                        f"{self._current_strategy_name or 'unknown'} 매수 차단"
                    )
                    return None

            # 개별 종목 VI 발동 시 매수 스킵
            if cb_state.is_vi_active(stock_code):
                self.logger.debug(f"{stock_code} 매수 스킵: VI 발동 중")
                return None

            # 일일 손실 한도 초과 시 매수 차단
            if self._fund_manager and self._fund_manager.is_daily_loss_limit_hit():
                limit_pct = self._fund_manager.max_daily_loss_ratio * 100
                loss = self._fund_manager._daily_realized_loss
                self.logger.warning(
                    f"매수 차단: 일일 손실 한도 초과 "
                    f"(누적손실 {loss:,.0f}원 / 한도 {limit_pct:.1f}%)"
                )
                return None

            # 상한가 접근 시 매수 차단
            from config.constants import PRICE_LIMIT_GUARD_RATE
            prev_close = trading_stock.prev_close
            if prev_close <= 0 and self._intraday_manager and hasattr(self._intraday_manager, 'get_cached_current_price'):
                price_info = self._intraday_manager.get_cached_current_price(stock_code)
                if price_info:
                    prev_close = price_info.get('prev_close', 0.0)
            if prev_close > 0:
                current_price = await self.get_current_price(stock_code)
                if current_price and current_price > 0:
                    rate = (current_price - prev_close) / prev_close
                    if rate >= PRICE_LIMIT_GUARD_RATE:
                        self.logger.info(
                            f"매수 차단: 상한가 접근 "
                            f"(현재가 {current_price:,.0f} / 전일종가 {prev_close:,.0f} = +{rate * 100:.1f}%)"
                        )
                        return None

            # TradingAnalyzer를 통한 매수 판단 + 실행
            await self._trading_analyzer.analyze_buy_decision(trading_stock, signal=signal)

            # 매수 성공 후 소유 전략 기록
            if self._current_strategy_name:
                trading_stock.owner_strategy_name = self._current_strategy_name
                trading_stock.owner_strategy = self._strategies_dict.get(self._current_strategy_name)

            return stock_code

        except Exception as e:
            self.logger.error(f"매수 오류 ({stock_code}): {e}")
            return None

    async def sell(self, stock_code: str, quantity: int = None,
                   reason: str = "", **kwargs) -> Optional[str]:
        """매도 주문 (기존 TradingAnalyzer.analyze_sell_decision 래핑)

        내부적으로 decision_engine.execute_virtual_sell()을 호출합니다.
        기존 안전장치는 기존 코드가 처리합니다.

        Args:
            stock_code: 종목코드
            quantity: 매도 수량 (None이면 전량)
            reason: 매도 사유
            **kwargs: 추가 파라미터

        Returns:
            주문 성공 시 stock_code, 실패 시 None
        """
        try:
            trading_stock = self._trading_manager.get_trading_stock(stock_code)
            if trading_stock is None:
                self.logger.debug(f"매도 스킵: {stock_code} 종목 정보 없음")
                return None

            # 소유권 가드: 다른 전략 소유 종목 매도 거부
            owner_name = getattr(trading_stock, 'owner_strategy_name', '')
            if owner_name and self._current_strategy_name and owner_name != self._current_strategy_name:
                self.logger.info(
                    f"매도 거부: {stock_code}는 {owner_name} 소유, "
                    f"{self._current_strategy_name}이 호출"
                )
                return None

            # 이미 매도 진행 중이면 중복 방지
            if getattr(trading_stock, 'is_selling', False):
                self.logger.debug(f"매도 스킵: {stock_code} 이미 매도 진행 중")
                return None

            # 하한가 접근 시 경고 (매도는 차단하지 않음 — 손절 필요)
            from config.constants import PRICE_LIMIT_GUARD_RATE
            prev_close = trading_stock.prev_close
            if prev_close <= 0 and self._intraday_manager and hasattr(self._intraday_manager, 'get_cached_current_price'):
                price_info = self._intraday_manager.get_cached_current_price(stock_code)
                if price_info:
                    prev_close = price_info.get('prev_close', 0.0)
            if prev_close > 0:
                current_price = await self.get_current_price(stock_code)
                if current_price and current_price > 0:
                    rate = (current_price - prev_close) / prev_close
                    if rate <= -PRICE_LIMIT_GUARD_RATE:
                        self.logger.warning(
                            f"매도 경고: 하한가 접근 "
                            f"(현재가 {current_price:,.0f} / 전일종가 {prev_close:,.0f} = {rate * 100:.1f}%) — 매도 진행"
                        )

            # TradingAnalyzer를 통한 매도 판단 + 실행
            await self._trading_analyzer.analyze_sell_decision(trading_stock)
            return stock_code

        except Exception as e:
            self.logger.error(f"매도 오류 ({stock_code}): {e}")
            return None

    # =========================================================================
    # e) 자금
    # =========================================================================

    def get_available_funds(self) -> float:
        """가용 자금 조회"""
        try:
            if self._fund_manager:
                return self._fund_manager.available_funds
            return 0.0
        except Exception:
            return 0.0

    def get_max_buy_amount(self, stock_code: str) -> float:
        """종목별 최대 매수 가능 금액"""
        try:
            if self._fund_manager:
                return self._fund_manager.get_max_buy_amount(stock_code)
            return 0.0
        except Exception:
            return 0.0

    def get_total_funds(self) -> float:
        """총 자금 조회"""
        try:
            if self._fund_manager:
                return self._fund_manager.total_funds
            return 0.0
        except Exception:
            return 0.0

    # =========================================================================
    # f) 유틸리티
    # =========================================================================

    def log(self, msg: str, level: str = "info") -> None:
        """로그 출력

        Args:
            msg: 로그 메시지
            level: 로그 레벨 (debug, info, warning, error)
        """
        log_func = getattr(self.logger, level, self.logger.info)
        log_func(msg)
