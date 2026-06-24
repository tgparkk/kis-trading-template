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
from config.constants import (
    ENTRY_COOLDOWN_SECONDS,
    MAX_NEW_ENTRIES_PER_CYCLE,
    ENTRY_CYCLE_WINDOW_SECONDS,
    OHLCV_LOOKBACK_DAYS,
)

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
        self._strategies_dict: Dict = strategies_dict or {}
        # strategy_name은 폴더명(dict 키)일 수 있음.
        # _strategy_key: _strategies_dict 조회용 키(폴더명) — dict lookup에는 항상 이 값을 사용.
        # _current_strategy_name: 표기명 — 전략 인스턴스의 .name 속성(클래스명)을 우선 사용해
        #   BUY/SELL DB 기록·로그가 동일한 표기로 통일되도록 함. dict 키로는 절대 사용 금지.
        self._strategy_key: str = strategy_name
        _strat_instance = self._strategies_dict.get(strategy_name)
        if _strat_instance and getattr(_strat_instance, 'name', None):
            self._current_strategy_name: str = _strat_instance.name
        else:
            self._current_strategy_name: str = strategy_name
        self.logger = setup_logger("trading_context")
        # 일봉 조회 실패 로그 쓰로틀: key=(stock_code, reason), value=마지막 로그 시각
        self._daily_log_cache: Dict[Tuple[str, str], datetime] = {}
        self._daily_log_interval = timedelta(minutes=10)
        # ── 장 시작 동시 진입 억제 (Entry Throttle) ──────────────────────────
        # 쿨다운/사이클 제한 설정 (constants.py에서 로드, 테스트에서 직접 override 가능)
        self._entry_cooldown_seconds: int = ENTRY_COOLDOWN_SECONDS
        self._max_new_entries_per_cycle: int = MAX_NEW_ENTRIES_PER_CYCLE
        self._entry_cycle_window_seconds: int = ENTRY_CYCLE_WINDOW_SECONDS
        # 런타임 상태
        self._last_new_entry_time: Optional[datetime] = None  # 마지막 신규 진입 시각
        self._cycle_start_time: Optional[datetime] = None     # 현재 사이클 시작 시각
        self._new_entries_this_cycle: int = 0                  # 현재 사이클 신규 진입 수

    def _get_strategy_regime_settings(self) -> Tuple[str, str]:
        """현재 전략의 (regime_index, regime_gate) 반환.

        전략 인스턴스에 설정이 없으면 기본값(both/none) — 미설정 전략은 기존 동작 불변.
        """
        strat = self._strategies_dict.get(self._strategy_key)
        regime_index = getattr(strat, "regime_index", "both") if strat else "both"
        regime_gate = getattr(strat, "regime_gate", "none") if strat else "none"
        return regime_index or "both", regime_gate or "none"

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

    @staticmethod
    def _drop_unconfirmed_today_bar(data: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """당일(장중 형성 중) 미완성 일봉을 마지막 봉에서 제외한다.

        daily_prices 에는 장중 부분 거래량으로 당일 row 가 존재할 수 있다(일봉 수집기가
        end_date=오늘로 KIS API 를 조회해 ON CONFLICT 로 upsert). 이 미완성 봉을
        그대로 두면 일봉 전략(거래량 게이트·Minervini dryup·양봉/눌림 판정)이
        df.iloc[-1] 을 '확정 일봉'으로 오인해 게이트가 망가진다. 모든 책 일봉 룰은
        '마지막 행 = 확정 봉(no-lookahead)' 을 전제(rules.py 주석)하므로, 단일 소스인
        이 로더에서 date == 오늘(KST) 인 trailing row 를 배제해 백테스트와 정합시킨다.

        - date/datetime 컬럼이 모두 없으면(합성/테스트 데이터) 변형 없이 그대로 반환한다.
        - 분봉/장중 데이터는 이 경로(get_daily_data)를 타지 않으므로 영향 없음.
        - EOD 에 확정 봉으로 재저장되면 다음 거래일 정상 마지막 봉이 된다.

        ※ no-lookahead 보증이 이 드롭 하나에 의존하므로(감사 2026-06-23), 일봉 소스가
          'date' 대신 'datetime' 만 주더라도 미확정봉이 새지 않도록 datetime 으로 폴백한다.
        """
        if data is None or getattr(data, "empty", True):
            return data
        if len(data) == 0:
            return data
        date_col = "date" if "date" in data.columns else (
            "datetime" if "datetime" in data.columns else None)
        if date_col is None:
            return data
        try:
            last_date = pd.to_datetime(data[date_col].iloc[-1]).date()
        except (ValueError, TypeError):
            return data
        if last_date == now_kst().date():
            return data.iloc[:-1].reset_index(drop=True)
        return data

    async def get_daily_data(self, stock_code: str, days: Optional[int] = None) -> Optional[pd.DataFrame]:
        """일봉 데이터 조회 (DB에서)

        Args:
            stock_code: 종목코드
            days: 조회 일수(달력일). 미지정 시 OHLCV_LOOKBACK_DAYS(=120)를 사용한다.
                  과거 기본값 60(달력일)은 영업일 ~40봉만 반환해 Elder(min_len=70)를
                  무력화시켰으므로, 설정 상수를 단일 소스로 따른다.

        반환 DataFrame 의 마지막 봉은 항상 '확정(전일까지) 일봉' 이다. daily_prices 에
        장중 부분 거래량으로 존재하는 당일 미완성 봉은 _drop_unconfirmed_today_bar 로
        제외해, 일봉 룰이 미확정 거래량/종가로 오동작하지 않도록 한다(no-lookahead).

        Returns:
            DataFrame or None
        """
        if days is None:
            days = OHLCV_LOOKBACK_DAYS
        try:
            if self._db_manager and hasattr(self._db_manager, 'price_repo'):
                data = self._db_manager.price_repo.get_daily_prices(stock_code, days=days)
                data = self._drop_unconfirmed_today_bar(data)
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

    def get_selected_stocks(self, owner: Optional[str] = None) -> List:
        """SELECTED 상태 종목 목록 반환 (owner 격리).

        owner 미지정 시 현재 전략(_strategy_key) 소유 + 소유자 미지정(공용) 종목만 반환.
        owner 지정 시 해당 전략 소유 종목만 반환. _strategy_key 없으면(레거시) 전체 반환.
        """
        from core.models import StockState
        try:
            stocks = self._trading_manager.get_stocks_by_state(StockState.SELECTED)
        except Exception as e:
            self.logger.debug(f"SELECTED 종목 조회 실패: {e}")
            return []
        target = owner if owner is not None else getattr(self, "_strategy_key", None)
        if not target:
            return stocks
        result = []
        for s in stocks:
            so = getattr(s, "strategy_name", None)
            if owner is not None:
                # owner 명시 호출은 정확히 그 전략 소유만 (공용 미포함) — 의도적
                if so == owner:
                    result.append(s)
            else:
                if so == target or not so:
                    result.append(s)
        return result

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

            # 전략별 국면 설정 조회 (regime_index/regime_gate). 미설정 전략은 기본값(both/none).
            regime_index, regime_gate = self._get_strategy_regime_settings()

            # 시장 방향성 필터: 전략별 지수 급락 시 매수 스킵
            is_crashing, crash_reason = self._decision_engine.check_market_direction(
                regime_index=regime_index
            )
            if is_crashing:
                self.logger.info(f"매수 판단 스킵: 시장급락 ({crash_reason})")
                return None

            # PIT 일봉 국면 게이트: 허용집합 밖 국면이면 매수 차단
            is_gated, gate_reason = self._decision_engine.check_regime_gate(
                regime_index=regime_index, regime_gate=regime_gate
            )
            if is_gated:
                self.logger.info(f"매수 판단 스킵: 국면게이트 ({gate_reason})")
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
                existing = stock_state_mgr.get_trading_stock(stock_code, strategy=self._current_strategy_name)
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

            # 매수 시점에 라이브 KIS 종목정보로 런타임 VI 상태를 arm한다.
            # (프로듀서 부재로 영구 no-op이던 VI/거래정지 가드를 발효 —
            #  선정 후 매수 시점에 VI 진입한 종목 차단. 사전-실전 감사 BLOCKER #6)
            try:
                from api.kis_market_api import get_stock_basic_info
                from config.market_hours import arm_circuit_breaker_from_info
                _vi_info = get_stock_basic_info(stock_code)
                if _vi_info is not None:
                    if hasattr(_vi_info, 'to_dict') and callable(_vi_info.to_dict):
                        _vi_info = _vi_info.to_dict()
                    elif hasattr(_vi_info, '__dict__'):
                        _vi_info = _vi_info.__dict__
                    arm_circuit_breaker_from_info(
                        stock_code, _vi_info if isinstance(_vi_info, dict) else None, cb_state
                    )
            except Exception as _vi_err:
                # 라이브 VI 조회 실패는 매수를 막지 않는다(보수적 통과)
                self.logger.debug(f"{stock_code} 라이브 VI 조회 실패(가드 스킵): {_vi_err}")

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

            # EOD 청산 시간 이후 intraday 전략 매수 차단 (안 C: F1 재매수 사고 방지)
            if MarketHours.is_eod_liquidation_time():
                current_strategy = self._strategies_dict.get(self._strategy_key)
                hp = getattr(current_strategy, 'holding_period', 'intraday') if current_strategy else 'intraday'
                if hp == 'intraday':
                    self.logger.info(
                        f"매수 차단: EOD 청산 시간 이후 intraday 전략 매수 불가 "
                        f"(전략={self._current_strategy_name or 'unknown'})"
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

            # ── 장 시작 동시 진입 억제 ─────────────────────────────────────────
            _now = now_kst()

            # 사이클 카운터 리셋: 윈도우가 경과했으면 새 사이클 시작
            if (self._cycle_start_time is None
                    or (_now - self._cycle_start_time).total_seconds()
                    >= self._entry_cycle_window_seconds):
                self._cycle_start_time = _now
                self._new_entries_this_cycle = 0

            # (나) 사이클당 신규 진입 개수 제한
            if (self._max_new_entries_per_cycle > 0
                    and self._new_entries_this_cycle >= self._max_new_entries_per_cycle):
                self.logger.info(
                    f"[진입억제] {stock_code} 매수 스킵 — "
                    f"이번 사이클 신규 진입 {self._new_entries_this_cycle}건 "
                    f"(한도 {self._max_new_entries_per_cycle}건)"
                )
                return None

            # (가) 종목간 진입 쿨다운
            if (self._entry_cooldown_seconds > 0
                    and self._last_new_entry_time is not None):
                elapsed = (_now - self._last_new_entry_time).total_seconds()
                if elapsed < self._entry_cooldown_seconds:
                    remaining = int(self._entry_cooldown_seconds - elapsed)
                    self.logger.info(
                        f"[진입억제] {stock_code} 매수 스킵 — "
                        f"쿨다운 {remaining}초 남음 "
                        f"(마지막 진입 {int(elapsed)}초 전)"
                    )
                    return None
            # ─────────────────────────────────────────────────────────────────

            # TradingAnalyzer를 통한 매수 판단 + 실행
            # _strategy_key(폴더키)를 전달 — VirtualTradingManager 전략별 자금
            # 격리 원장이 main.py 할당 시 사용한 폴더키와 일관되게 매칭되도록 함.
            executed = await self._trading_analyzer.analyze_buy_decision(
                trading_stock, signal=signal, strategy_name=self._strategy_key
            )

            # 실제 체결된 경우에만 쿨다운/사이클 카운터 갱신.
            # 거부·실패(이미 보유·자금부족·예약실패 등)한 시도가 쿨다운을 무장시키면
            # 60초마다 재무장돼 후속 진입을 영구히 굶긴다(2026-06-09 버그 수정).
            if not executed:
                return None

            self._last_new_entry_time = now_kst()
            self._new_entries_this_cycle += 1

            # 매수 성공 후 소유 전략 기록
            if self._current_strategy_name:
                trading_stock.owner_strategy_name = self._current_strategy_name
                trading_stock.owner_strategy = self._strategies_dict.get(self._strategy_key)

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
