"""
포지션 모니터링 모듈

보유 종목 현재가 업데이트 및 손익절 모니터링
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, TYPE_CHECKING, Optional

from ..models import TradingStock, StockState
from strategies.base import SignalType
from utils.logger import setup_logger
from utils.rate_limited_logger import RateLimitedLogger
from utils.korean_time import now_kst, is_market_open
from config.constants import STALE_SELL_PROFIT_THRESHOLD, STALE_SELL_LOSS_THRESHOLD, COMMISSION_RATE, SECURITIES_TAX_RATE

# Circuit Breaker 상수
CB_MAX_FAILURES = 3           # 일반 오류 circuit breaker 활성화 실패 횟수
CB_COOLDOWN_MINUTES = 30      # circuit breaker 대기 시간 (분)
CB_SYSTEM_ALERT_THRESHOLD = 5 # 시스템 경고 임계값 (동시 활성 종목 수)

if TYPE_CHECKING:
    from .stock_state_manager import StockStateManager
    from .order_completion_handler import OrderCompletionHandler
    from ..intraday_stock_manager import IntradayStockManager
    from ..data_collector import RealTimeDataCollector


class PositionMonitor:
    """
    포지션 모니터링 관리자

    주요 기능:
    1. 종목 상태 모니터링 루프
    2. 포지션 현재가 업데이트
    3. 손익절 조건 체크
    4. 매도 실행
    """

    def __init__(self, state_manager: 'StockStateManager',
                 completion_handler: 'OrderCompletionHandler',
                 intraday_manager: 'IntradayStockManager',
                 data_collector: 'RealTimeDataCollector') -> None:
        """
        초기화

        Args:
            state_manager: 종목 상태 관리자
            completion_handler: 주문 체결 처리자
            intraday_manager: 장중 종목 관리자
            data_collector: 실시간 데이터 수집기
        """
        self.state_manager = state_manager
        self.completion_handler = completion_handler
        self.intraday_manager = intraday_manager
        self.data_collector = data_collector
        self.logger = RateLimitedLogger(setup_logger(__name__))

        # 모니터링 설정
        self.is_monitoring = False
        self.monitor_interval = 3  # 3초마다 상태 체크 (체결 확인 빠르게)

        # decision_engine은 나중에 설정됨 (순환 참조 방지)
        self.decision_engine = None

        # fund_manager (나중에 set_fund_manager로 설정)
        self.fund_manager = None

        # paper_trading 모드 캐싱
        self._paper_trading = False

        # 전략 (sell signal 생성용, 나중에 set_strategy로 설정)
        self._strategy = None

        # 로깅 플래그
        self._sell_check_logged = False

        # Circuit Breaker 상태
        self._sell_fail_counts: Dict[str, int] = {}      # 종목별 연속 실패 횟수
        self._sell_fail_times: Dict[str, datetime] = {}   # 종목별 circuit breaker 활성화 시각
        self._system_alert_fired = False                   # 시스템 경고 발송 여부 (1회만)

        # Emergency Sell Path: 재시도 타이밍 관리
        self._last_pending_retry_time: Optional[datetime] = None   # 마지막 retry 시각
        self._last_pending_summary_time: Optional[datetime] = None  # 마지막 요약 로그 시각
        self._RETRY_INTERVAL_MINUTES = 5    # 재시도 간격 (분)
        self._SUMMARY_INTERVAL_MINUTES = 30  # 요약 로그 간격 (분)

    def set_decision_engine(self, decision_engine: Any) -> None:
        """매매 판단 엔진 설정 (순환 참조 방지를 위해 별도 메서드)"""
        self.decision_engine = decision_engine

    def set_strategy(self, strategy: Any) -> None:
        """전략 설정 (매도 시그널 생성용)"""
        self._strategy = strategy

    async def start_monitoring(self) -> None:
        """종목 상태 모니터링 시작"""
        self.is_monitoring = True
        self.logger.info("종목 상태 모니터링 시작")

        while self.is_monitoring:
            try:
                if not is_market_open():
                    await asyncio.sleep(60)  # 장 마감 시 1분 대기
                    continue

                await self._monitor_stock_states()
                await asyncio.sleep(self.monitor_interval)

            except Exception as e:
                self.logger.error(f"종목 상태 모니터링 오류: {e}")
                await asyncio.sleep(10)

    async def check_positions_once(self) -> None:
        """보유종목 1회 체크 (현재가 업데이트 + 매도 판단, 메인루프에서 호출)"""
        try:
            await self._monitor_stock_states()
        except Exception as e:
            self.logger.error(f"보유종목 1회 체크 오류: {e}")

    async def _monitor_stock_states(self) -> None:
        """종목 상태 모니터링"""
        try:
            # 주문 완료 확인
            await self.completion_handler.check_order_completions()

            # 포지션 현재가 업데이트
            await self._update_position_prices()

            # 보유 종목 매도 판단 (손익절 체크)
            await self._check_positioned_stocks_for_sell()

            # Emergency Sell Path: 미저장 매도 기록 재시도 및 요약 로그
            await self._check_pending_sell_retries()

        except Exception as e:
            self.logger.error(f"종목 상태 모니터링 중 오류: {e}")

    async def _update_position_prices(self) -> None:
        """포지션 현재가 업데이트"""
        try:
            positioned_stocks = list(
                self.state_manager.stocks_by_state[StockState.POSITIONED].values()
            )

            for trading_stock in positioned_stocks:
                if trading_stock.position:
                    # 현재가 조회
                    price_data = self.data_collector.get_stock(trading_stock.stock_code)
                    if price_data and price_data.last_price > 0:
                        try:
                            current_price = float(price_data.last_price)
                            if current_price > 0:
                                trading_stock.position.update_current_price(current_price)
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"{trading_stock.stock_code} 현재가 변환 실패: {e}")

        except Exception as e:
            self.logger.error(f"포지션 현재가 업데이트 오류: {e}")

    async def _check_positioned_stocks_for_sell(self) -> None:
        """보유 종목 매도 판단 (손익절 체크)"""
        try:
            positioned_stocks = list(
                self.state_manager.stocks_by_state[StockState.POSITIONED].values()
            )

            if not positioned_stocks:
                return

            # 최초 1회만 로깅 (너무 많은 로그 방지)
            if not self._sell_check_logged:
                self.logger.info(
                    f"보유 종목 손익절 체크 시작: {len(positioned_stocks)}개 종목"
                )
                self._sell_check_logged = True

            for trading_stock in positioned_stocks:
                if not trading_stock.position:
                    continue

                # decision_engine이 설정되어 있어야 매도 판단 가능
                if not self.decision_engine:
                    continue

                try:
                    await self._analyze_sell_for_stock(trading_stock)
                except Exception as e:
                    self.logger.error(f"{trading_stock.stock_code} 매도 판단 오류: {e}")

        except Exception as e:
            self.logger.error(f"보유 종목 매도 판단 오류: {e}")

    async def _analyze_sell_for_stock(self, trading_stock: TradingStock) -> None:
        """개별 종목 매도 판단"""
        try:
            stock_code = trading_stock.stock_code

            # 현재가 조회 - 손익절 정확성을 위해 API 직접 호출 우선
            current_price = await self._get_current_price(stock_code)

            # 현재가 조회 실패 시 종료
            if current_price is None or current_price <= 0:
                self.logger.debug(f"{stock_code} 현재가 조회 실패 - 손익절 체크 스킵")
                return

            # 간단한 손익절 체크
            if trading_stock.position:
                buy_price = float(trading_stock.position.avg_price)
                current_price = float(current_price)
                profit_rate = (current_price - buy_price) / buy_price

                # 09:00~09:05 사이에는 손절 체크 안 함 (익절만)
                current_time = now_kst()
                is_before_rebalancing = (
                    current_time.hour == 9 and
                    current_time.minute < 5
                )

                # 장기보유 종목 우선 청산 (더 타이트한 임계값 적용)
                if getattr(trading_stock, 'is_stale', False) is True:
                    if profit_rate > STALE_SELL_PROFIT_THRESHOLD:
                        reason = (
                            f"장기보유 종목 우선 청산: 수익률 {profit_rate:.2%} "
                            f"(보유 {getattr(trading_stock, 'days_held', '?')}일)"
                        )
                        self.logger.info(
                            f"🕐 {stock_code} {reason}"
                        )
                        await self._execute_sell(trading_stock, current_price, reason)
                        return

                    if not is_before_rebalancing and profit_rate <= -STALE_SELL_LOSS_THRESHOLD:
                        reason = (
                            f"장기보유 종목 손절: 수익률 {profit_rate:.2%} "
                            f"(<= -{STALE_SELL_LOSS_THRESHOLD:.0%}, "
                            f"보유 {getattr(trading_stock, 'days_held', '?')}일)"
                        )
                        self.logger.info(
                            f"🕐 {stock_code} {reason}"
                        )
                        await self._execute_sell(trading_stock, current_price, reason)
                        return

                # 목표 익절률 체크
                if hasattr(trading_stock, 'target_profit_rate') and trading_stock.target_profit_rate:
                    if profit_rate >= trading_stock.target_profit_rate:
                        reason = (
                            f"목표 익절 도달 ({profit_rate:.2%} >= "
                            f"{trading_stock.target_profit_rate:.2%})"
                        )
                        self.logger.info(f"{stock_code} 익절 신호: {reason}")
                        await self._execute_sell(trading_stock, current_price, reason)
                        return

                # 손절률 체크 (리밸런싱 전에는 스킵)
                if not is_before_rebalancing:
                    if hasattr(trading_stock, 'stop_loss_rate') and trading_stock.stop_loss_rate:
                        if profit_rate <= -trading_stock.stop_loss_rate:
                            reason = (
                                f"손절 실행 ({profit_rate:.2%} <= "
                                f"-{trading_stock.stop_loss_rate:.2%})"
                            )
                            self.logger.info(f"{stock_code} 손절 신호: {reason}")
                            await self._execute_sell(trading_stock, current_price, reason)
                            return

                # 전략 매도 시그널 체크 (손익절 안 걸린 경우)
                if self._strategy and hasattr(self._strategy, 'generate_signal'):
                    try:
                        # 장중 데이터 조회 (intraday)
                        intraday_data = None
                        price_data = self.data_collector.get_stock(stock_code)
                        if price_data and hasattr(price_data, 'ohlcv_data') and len(price_data.ohlcv_data) > 0:
                            import pandas as pd
                            intraday_data = pd.DataFrame(price_data.ohlcv_data)

                        if intraday_data is not None and len(intraday_data) > 0:
                            signal = self._strategy.generate_signal(
                                stock_code, intraday_data, timeframe='intraday'
                            )
                            if signal and signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                                reason = ", ".join(signal.reasons) if signal.reasons else f"{self._strategy.name} 매도신호"
                                self.logger.info(f"{stock_code} 전략 매도 신호: {reason} (신뢰도: {signal.confidence}%)")
                                await self._execute_sell(trading_stock, current_price, reason)
                                return
                    except Exception as strategy_err:
                        self.logger.warning(f"{stock_code} 전략 매도신호 생성 오류: {strategy_err}")

        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매도 분석 오류: {e}")

    async def _get_current_price(self, stock_code: str) -> Optional[float]:
        """
        현재가 조회 (여러 소스에서 시도)

        Args:
            stock_code: 종목 코드

        Returns:
            현재가 또는 None
        """
        current_price = None

        # 1. API 직접 호출 (최신 가격, 손익절 판단에 가장 정확)
        try:
            current_price_info = self.intraday_manager.get_current_price_for_sell(stock_code)
            if current_price_info:
                current_price = current_price_info.get('current_price')
        except Exception as api_err:
            self.logger.warning(f"{stock_code} 현재가 API 조회 실패: {api_err}")

        # 2. 캐시된 현재가 폴백 (API 실패 시)
        if current_price is None:
            current_price_info = self.intraday_manager.get_cached_current_price(stock_code)
            if current_price_info:
                current_price = current_price_info.get('current_price')
                self.logger.debug(f"{stock_code} 캐시된 현재가 사용: {current_price:,.0f}원")

        # 3. data_collector fallback (최종 수단)
        if current_price is None:
            price_data = self.data_collector.get_stock(stock_code)
            if price_data and price_data.last_price > 0:
                current_price = price_data.last_price
                self.logger.debug(
                    f"{stock_code} data_collector 현재가 사용: {current_price:,.0f}원"
                )

        return current_price

    async def _execute_sell(self, trading_stock: TradingStock,
                           sell_price: float, reason: str) -> None:
        """매도 실행 (실패 시 재시도 포함, Circuit Breaker 적용)"""
        stock_code = trading_stock.stock_code
        max_retries = 3
        retry_delay = 2  # 초

        # Circuit Breaker 체크 (활성 상태이면 매도 시도 자체를 차단)
        if self._is_circuit_breaker_active(stock_code):
            remaining = self._sell_fail_times[stock_code] + timedelta(minutes=CB_COOLDOWN_MINUTES) - now_kst()
            self.logger.debug(
                f"{stock_code} Circuit Breaker 활성 중 - 매도 스킵 "
                f"(남은 시간: {remaining.total_seconds() / 60:.1f}분)"
            )
            return

        # 매도 타임아웃 복원 직후 쿨다운 체크 (10초)
        last_timeout = getattr(trading_stock, 'last_sell_timeout_time', None)
        if last_timeout:
            elapsed = (now_kst() - last_timeout).total_seconds()
            if elapsed < 10:
                self.logger.debug(f"{stock_code} 매도 타임아웃 쿨다운 중 ({elapsed:.0f}초 경과)")
                return

        for attempt in range(1, max_retries + 1):
            try:
                # 이미 매도 진행 중이면 중복 방지
                if trading_stock.is_selling:
                    self.logger.warning(f"{stock_code} 이미 매도 진행 중 (중복 방지)")
                    return

                # 매도 진행 플래그 설정
                trading_stock.is_selling = True

                # decision_engine을 통해 매도 실행
                if self.decision_engine:
                    if self._paper_trading:
                        # 매도 전 포지션 정보 저장 (execute_virtual_sell이 position을 클리어하므로)
                        _buy_price = trading_stock.position.avg_price if trading_stock.position else 0
                        _quantity = trading_stock.position.quantity if trading_stock.position else 0
                        success = await self.decision_engine.execute_virtual_sell(
                            trading_stock, sell_price, reason
                        )
                        if success:
                            trading_stock.is_selling = False
                            self._record_sell_success(stock_code)
                            # FundManager 자금 반환
                            if self.fund_manager:
                                try:
                                    invested = float(_buy_price) * int(_quantity)
                                    sell_amount = float(sell_price) * int(_quantity) if sell_price else invested
                                    buy_commission = invested * COMMISSION_RATE
                                    sell_commission = sell_amount * COMMISSION_RATE
                                    sell_tax = sell_amount * SECURITIES_TAX_RATE
                                    pnl = sell_amount - invested - buy_commission - sell_commission - sell_tax
                                    self.fund_manager.release_investment(invested, stock_code=stock_code)
                                    self.fund_manager.adjust_pnl(pnl)
                                    self.fund_manager.remove_position(stock_code)
                                    self.fund_manager.set_sell_cooldown(stock_code, reason)
                                except Exception as fm_e:
                                    self.logger.error(f"{stock_code} 매도 후 자금관리 업데이트 실패: {fm_e}")
                            self.logger.info(f"{stock_code} 가상 매도 완료: {reason}")
                            return
                        else:
                            trading_stock.is_selling = False
                            self.logger.warning(f"{stock_code} 가상 매도 실패: {reason}")
                            continue
                    else:
                        success = await self.decision_engine.execute_real_sell(
                            trading_stock, reason
                        )
                        if success:
                            self._record_sell_success(stock_code)
                            self.logger.info(f"{stock_code} 실제 매도 주문 완료: {reason}")
                            return

                # 매도 실패
                trading_stock.is_selling = False
                if attempt < max_retries:
                    self.logger.warning(
                        f"{stock_code} 매도 실패 (시도 {attempt}/{max_retries}), "
                        f"{retry_delay}초 후 재시도: {reason}"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 지수 백오프
                else:
                    self.logger.error(
                        f"🚨 {stock_code} 매도 {max_retries}회 실패! "
                        f"수동 확인 필요: {reason}"
                    )
                    self._record_sell_failure(stock_code)

            except (TypeError, ValueError) as e:
                # 코드 버그: 즉시 circuit breaker 활성화 (재시도 무의미)
                trading_stock.is_selling = False
                self.logger.error(
                    f"{stock_code} 매도 실행 코드 버그 ({type(e).__name__}): {e}"
                )
                self._record_sell_failure(stock_code, error=e)
                return  # 재시도 없이 즉시 중단

            except Exception as e:
                trading_stock.is_selling = False
                if attempt < max_retries:
                    self.logger.warning(
                        f"{stock_code} 매도 실행 오류 (시도 {attempt}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    self.logger.error(
                        f"🚨 {stock_code} 매도 실행 최종 실패: {e}"
                    )
                    self._record_sell_failure(stock_code, error=e)

    # =========================================================================
    # Circuit Breaker 관련 메서드
    # =========================================================================

    def _is_circuit_breaker_active(self, stock_code: str) -> bool:
        """
        해당 종목의 circuit breaker가 활성 상태인지 확인.
        쿨다운 시간이 경과했으면 자동으로 해제하고 False 반환.
        """
        if stock_code not in self._sell_fail_times:
            return False

        activated_at = self._sell_fail_times[stock_code]
        elapsed = now_kst() - activated_at

        if elapsed >= timedelta(minutes=CB_COOLDOWN_MINUTES):
            # 쿨다운 경과 → circuit breaker 해제
            self.logger.warning(
                f"⚡ {stock_code} Circuit Breaker 해제"
            )
            del self._sell_fail_times[stock_code]
            self._sell_fail_counts.pop(stock_code, None)
            # 시스템 경고 재발송 가능하도록 리셋 체크
            self._check_system_alert_reset()
            return False

        return True

    def _activate_circuit_breaker(self, stock_code: str) -> None:
        """종목의 circuit breaker를 활성화"""
        self._sell_fail_times[stock_code] = now_kst()
        self.logger.warning(
            f"⚡ {stock_code} 매도 Circuit Breaker 활성화 "
            f"- {self._sell_fail_counts.get(stock_code, 0)}회 연속 실패, "
            f"{CB_COOLDOWN_MINUTES}분 대기"
        )
        self._check_system_alert()

    def _record_sell_failure(self, stock_code: str, error: Optional[Exception] = None) -> None:
        """
        매도 실패를 기록하고, 임계값 도달 시 circuit breaker 활성화.
        TypeError/ValueError(코드 버그)이면 즉시 활성화.
        """
        # 코드 버그 (TypeError, ValueError)인 경우 즉시 circuit breaker 활성화
        if error is not None and isinstance(error, (TypeError, ValueError)):
            self._sell_fail_counts[stock_code] = CB_MAX_FAILURES
            self.logger.error(
                f"{stock_code} 코드 버그 감지 ({type(error).__name__}: {error}) "
                f"- 즉시 Circuit Breaker 활성화"
            )
            self._activate_circuit_breaker(stock_code)
            return

        # 일반 오류: 카운트 증가
        self._sell_fail_counts[stock_code] = self._sell_fail_counts.get(stock_code, 0) + 1

        if self._sell_fail_counts[stock_code] >= CB_MAX_FAILURES:
            self._activate_circuit_breaker(stock_code)

    def _record_sell_success(self, stock_code: str) -> None:
        """매도 성공 시 해당 종목의 실패 카운터 초기화"""
        if stock_code in self._sell_fail_counts:
            del self._sell_fail_counts[stock_code]
        if stock_code in self._sell_fail_times:
            del self._sell_fail_times[stock_code]
            self._check_system_alert_reset()

    def _check_system_alert(self) -> None:
        """동시에 5개 이상 종목 circuit breaker 활성 시 CRITICAL 경고 (1회만)"""
        active_count = len(self._sell_fail_times)
        if active_count >= CB_SYSTEM_ALERT_THRESHOLD and not self._system_alert_fired:
            self.logger.critical(
                f"🚨 시스템 경고: {active_count}개 종목 매도 불가 - 코드 점검 필요"
            )
            self._system_alert_fired = True

    def _check_system_alert_reset(self) -> None:
        """활성 circuit breaker 수가 임계값 아래로 내려가면 경고 플래그 리셋"""
        active_count = len(self._sell_fail_times)
        if active_count < CB_SYSTEM_ALERT_THRESHOLD and self._system_alert_fired:
            self._system_alert_fired = False

    def reset_circuit_breaker(self, stock_code: str) -> None:
        """특정 종목의 circuit breaker 수동 리셋"""
        removed = False
        if stock_code in self._sell_fail_counts:
            del self._sell_fail_counts[stock_code]
            removed = True
        if stock_code in self._sell_fail_times:
            del self._sell_fail_times[stock_code]
            removed = True

        if removed:
            self.logger.info(f"{stock_code} Circuit Breaker 수동 리셋 완료")
            self._check_system_alert_reset()
        else:
            self.logger.info(f"{stock_code} Circuit Breaker 활성 상태 아님 (리셋 불필요)")

    def reset_all_circuit_breakers(self) -> None:
        """모든 종목의 circuit breaker 리셋"""
        count = len(self._sell_fail_times)
        self._sell_fail_counts.clear()
        self._sell_fail_times.clear()
        self._system_alert_fired = False
        self.logger.info(f"전체 Circuit Breaker 리셋 완료 (활성 {count}개 해제)")

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        현재 circuit breaker 상태 반환

        Returns:
            Dict with keys:
                - active_breakers: 활성 circuit breaker 목록 (종목코드, 활성화시각, 남은시간)
                - failure_counts: 종목별 실패 횟수 (circuit breaker 미활성 포함)
                - system_alert_fired: 시스템 경고 발송 여부
        """
        current_time = now_kst()
        active_breakers: List[Dict[str, Any]] = []

        for stock_code, activated_at in self._sell_fail_times.items():
            elapsed = current_time - activated_at
            remaining = timedelta(minutes=CB_COOLDOWN_MINUTES) - elapsed
            remaining_seconds = max(0, remaining.total_seconds())

            active_breakers.append({
                'stock_code': stock_code,
                'activated_at': activated_at.isoformat(),
                'remaining_minutes': round(remaining_seconds / 60, 1),
                'fail_count': self._sell_fail_counts.get(stock_code, 0),
            })

        return {
            'active_breakers': active_breakers,
            'active_count': len(active_breakers),
            'failure_counts': dict(self._sell_fail_counts),
            'system_alert_fired': self._system_alert_fired,
        }

    # =========================================================================
    # Emergency Sell Path: 미저장 매도 기록 재시도
    # =========================================================================

    async def _check_pending_sell_retries(self) -> None:
        """
        미저장 매도 기록 재시도 및 주기적 요약 로그.

        - 재시도: 5분마다 실행
        - 요약 로그: 30분마다 출력 (장중, pending 건이 있을 때만)
        """
        try:
            # decision_engine → virtual_trading (VirtualTradingManager) 참조
            if not self.decision_engine or not hasattr(self.decision_engine, 'virtual_trading'):
                return

            vtm = self.decision_engine.virtual_trading
            if vtm is None:
                return

            current_time = now_kst()

            # 5분마다 재시도
            should_retry = (
                self._last_pending_retry_time is None
                or (current_time - self._last_pending_retry_time).total_seconds()
                >= self._RETRY_INTERVAL_MINUTES * 60
            )
            if should_retry and vtm.get_pending_sells_count() > 0:
                vtm.retry_pending_sells()
                self._last_pending_retry_time = current_time

            # 30분마다 요약 로그 (장중, pending 건이 있을 때)
            should_log = (
                self._last_pending_summary_time is None
                or (current_time - self._last_pending_summary_time).total_seconds()
                >= self._SUMMARY_INTERVAL_MINUTES * 60
            )
            if should_log and is_market_open() and vtm.get_pending_sells_count() > 0:
                vtm.log_pending_sells_summary()
                self._last_pending_summary_time = current_time

        except Exception as e:
            self.logger.debug(f"미저장 매도 기록 재시도 체크 오류: {e}")

    def stop_monitoring(self) -> None:
        """모니터링 중단"""
        self.is_monitoring = False
        self.logger.info("종목 상태 모니터링 중단")
