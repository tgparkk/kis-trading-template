"""
주문 체결 처리 모듈

매수/매도 주문의 체결 확인 및 후속 처리
"""
from typing import Any, TYPE_CHECKING
import pandas as pd

from ..models import TradingStock, StockState, OrderStatus, OrderType
from utils.logger import setup_logger
from utils.korean_time import now_kst

if TYPE_CHECKING:
    from .stock_state_manager import StockStateManager
    from ..order_manager import OrderManager


class OrderCompletionHandler:
    """
    주문 체결 처리자

    주요 기능:
    1. 매수 주문 체결 확인
    2. 매도 주문 체결 확인
    3. 체결 콜백 처리
    """

    def __init__(self, state_manager: 'StockStateManager',
                 order_manager: 'OrderManager'):
        """
        초기화

        Args:
            state_manager: 종목 상태 관리자
            order_manager: 주문 관리자
        """
        self.state_manager = state_manager
        self.order_manager = order_manager
        self.logger = setup_logger(__name__)

        # 재거래 설정 (외부에서 설정됨)
        self.enable_re_trading = True

        # 전략 콜백 연결 (외부에서 set_strategy로 설정)
        self.strategy = None

    def set_strategy(self, strategy: Any) -> None:
        """전략 연결 (on_order_filled 콜백용)"""
        self.strategy = strategy
        if strategy:
            self.logger.info(f"OrderCompletionHandler에 전략 연결: {strategy.name}")

    def _notify_strategy_order_filled(self, order) -> None:
        """전략의 on_order_filled 콜백 호출"""
        try:
            if self.strategy and hasattr(self.strategy, 'on_order_filled'):
                order_info = {
                    'order_id': order.order_id,
                    'stock_code': order.stock_code,
                    'order_type': order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type),
                    'quantity': order.quantity,
                    'price': order.price,
                    'filled_at': now_kst(),
                }
                self.strategy.on_order_filled(order_info)
                self.logger.debug(f"전략 on_order_filled 콜백 호출: {order.stock_code}")
        except Exception as e:
            self.logger.warning(f"전략 on_order_filled 콜백 오류: {e}")

    async def check_order_completions(self) -> None:
        """주문 완료 확인 및 상태 업데이트"""
        try:
            # 매수 주문 중인 종목들 확인
            buy_pending_stocks = list(
                self.state_manager.stocks_by_state[StockState.BUY_PENDING].values()
            )
            for trading_stock in buy_pending_stocks:
                await self._check_buy_order_completion(trading_stock)

            # 매도 주문 중인 종목들 확인
            sell_pending_stocks = list(
                self.state_manager.stocks_by_state[StockState.SELL_PENDING].values()
            )
            for trading_stock in sell_pending_stocks:
                await self._check_sell_order_completion(trading_stock)

        except Exception as e:
            self.logger.error(f"주문 완료 확인 오류: {e}")

    async def _check_buy_order_completion(self, trading_stock: TradingStock) -> None:
        """매수 주문 완료 확인"""
        try:
            if not trading_stock.current_order_id:
                return

            # 주문 관리자에서 완료된 주문 확인
            completed_orders = self.order_manager.get_completed_orders()

            for order in completed_orders:
                if (order.order_id == trading_stock.current_order_id and
                        order.stock_code == trading_stock.stock_code):

                    if order.status == OrderStatus.FILLED:
                        # 매수 완료 - 포지션 상태로 변경
                        with self.state_manager.lock:
                            trading_stock.set_position(order.quantity, order.price)
                            trading_stock.clear_current_order()
                            # 매수 시간 기록
                            trading_stock.set_buy_time(now_kst())

                            # 가상매매 모드일 때 가상매매 기록 ID 설정
                            self._set_virtual_buy_info(trading_stock)

                            self.state_manager.change_stock_state(
                                trading_stock.stock_code,
                                StockState.POSITIONED,
                                f"매수 완료: {order.quantity}주 @{order.price:,.0f}원"
                            )

                        # 실거래 매수 기록 저장
                        self._save_real_buy_record(trading_stock, order)

                        # 전략 콜백 호출
                        self._notify_strategy_order_filled(order)

                        self.logger.info(f"{trading_stock.stock_code} 매수 완료")

                    elif order.status in [OrderStatus.CANCELLED, OrderStatus.FAILED]:
                        # 매수 실패 - 매수 후보로 되돌림
                        with self.state_manager.lock:
                            trading_stock.clear_current_order()
                            # 매수 실패 시 원래 상태로 복귀
                            original_state = (
                                StockState.COMPLETED
                                if "재거래" in trading_stock.selection_reason
                                else StockState.SELECTED
                            )
                            self.state_manager.change_stock_state(
                                trading_stock.stock_code,
                                original_state,
                                f"매수 실패: {order.status.value}"
                            )

                    break

        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매수 주문 완료 확인 오류: {e}")

    async def _check_sell_order_completion(self, trading_stock: TradingStock) -> None:
        """매도 주문 완료 확인"""
        try:
            if not trading_stock.current_order_id:
                return

            # 주문 관리자에서 완료된 주문 확인
            completed_orders = self.order_manager.get_completed_orders()
            for order in completed_orders:
                if (order.order_id == trading_stock.current_order_id and
                        order.stock_code == trading_stock.stock_code):

                    if order.status == OrderStatus.FILLED:
                        # 매도 완료 - 완료 상태로 변경
                        with self.state_manager.lock:
                            trading_stock.clear_position()
                            trading_stock.clear_current_order()
                            self.state_manager.change_stock_state(
                                trading_stock.stock_code,
                                StockState.COMPLETED,
                                f"매도 완료: {order.quantity}주 @{order.price:,.0f}원"
                            )

                        # 실거래 매도 기록 저장
                        profit_rate = self._save_real_sell_record(trading_stock, order)

                        # 전략 콜백 호출
                        self._notify_strategy_order_filled(order)

                        self.logger.info(
                            f"{trading_stock.stock_code} 매도 완료 (수익률: {profit_rate:.2f}%)"
                        )

                        # 매도 완료 후 즉시 재거래 준비 (COMPLETED 상태 유지)
                        if self.enable_re_trading:
                            self.logger.info(
                                f"{trading_stock.stock_code} 즉시 재거래 준비 완료 "
                                "(COMPLETED 상태 유지)"
                            )

                    elif order.status in [OrderStatus.CANCELLED, OrderStatus.FAILED]:
                        # 매도 실패 - 매도 후보로 되돌림
                        with self.state_manager.lock:
                            trading_stock.clear_current_order()
                            self.state_manager.change_stock_state(
                                trading_stock.stock_code,
                                StockState.SELL_CANDIDATE,
                                f"매도 실패: {order.status.value}"
                            )

                    break

        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매도 주문 완료 확인 오류: {e}")

    async def on_order_filled(self, order) -> None:
        """주문 체결 시 즉시 호출되는 콜백 메서드"""
        try:
            self.logger.info(
                f"주문 체결 콜백 수신: {order.order_id} - {order.stock_code} "
                f"({order.order_type.value})"
            )

            with self.state_manager.lock:
                if order.stock_code not in self.state_manager.trading_stocks:
                    self.logger.warning(f"체결 콜백: 관리되지 않는 종목 {order.stock_code}")
                    return

                trading_stock = self.state_manager.trading_stocks[order.stock_code]

                # 추가: 이미 POSITIONED 상태라면 중복 처리 방지
                if (order.order_type == OrderType.BUY and
                        trading_stock.state == StockState.POSITIONED):
                    self.logger.debug(
                        f"{order.stock_code} 이미 POSITIONED 상태 (중복 콜백 방지)"
                    )
                    return

                # 레이스 컨디션 방지: 이미 처리된 주문인지 확인
                if trading_stock.order_processed:
                    self.logger.debug(f"이미 처리된 주문 (중복 방지): {order.order_id}")
                    return

                if order.order_type == OrderType.BUY:
                    self._process_buy_fill_callback(trading_stock, order)
                elif order.order_type == OrderType.SELL:
                    self._process_sell_fill_callback(trading_stock, order)

        except Exception as e:
            self.logger.error(f"주문 체결 콜백 처리 오류: {e}")

    def _process_buy_fill_callback(self, trading_stock: TradingStock, order) -> None:
        """매수 체결 콜백 처리"""
        if trading_stock.state == StockState.BUY_PENDING:
            # 체결 처리 플래그 설정
            trading_stock.order_processed = True
            trading_stock.is_buying = False  # 매수 완료

            trading_stock.set_position(order.quantity, order.price)
            trading_stock.clear_current_order()
            # 매수 시간 기록 (콜백)
            trading_stock.set_buy_time(now_kst())

            # 가상매매 모드일 때 가상매매 기록 ID 설정
            self._set_virtual_buy_info(trading_stock)

            self.state_manager.change_stock_state(
                trading_stock.stock_code,
                StockState.POSITIONED,
                f"매수 체결 (콜백): {order.quantity}주 @{order.price:,.0f}원"
            )

            # 실거래 매수 기록 저장
            self._save_real_buy_record(trading_stock, order, source="콜백")

            # 전략 콜백 호출
            self._notify_strategy_order_filled(order)

            self.logger.info(f"매수 체결 처리 완료 (콜백): {trading_stock.stock_code}")
        else:
            self.logger.warning(
                f"예상치 못한 상태에서 매수 체결: {trading_stock.state.value}"
            )

    def _process_sell_fill_callback(self, trading_stock: TradingStock, order) -> None:
        """매도 체결 콜백 처리"""
        if trading_stock.state == StockState.SELL_PENDING:
            # 체결 처리 플래그 설정
            trading_stock.order_processed = True
            trading_stock.is_selling = False  # 매도 완료

            trading_stock.clear_position()
            trading_stock.clear_current_order()
            self.state_manager.change_stock_state(
                trading_stock.stock_code,
                StockState.COMPLETED,
                f"매도 체결 (콜백): {order.quantity}주 @{order.price:,.0f}원"
            )

            # 실거래 매도 기록 저장
            profit_rate = self._save_real_sell_record(trading_stock, order, source="콜백")

            # 전략 콜백 호출
            self._notify_strategy_order_filled(order)

            self.logger.info(
                f"매도 체결 처리 완료 (콜백): {trading_stock.stock_code} "
                f"(수익률: {profit_rate:.2f}%)"
            )

            # 매도 완료 후 즉시 재거래 준비 (COMPLETED 상태 유지)
            if self.enable_re_trading:
                self.logger.info(
                    f"{trading_stock.stock_code} 즉시 재거래 준비 완료 (COMPLETED 상태 유지)"
                )
        else:
            self.logger.warning(
                f"예상치 못한 상태에서 매도 체결: {trading_stock.state.value}"
            )

    def _set_virtual_buy_info(self, trading_stock: TradingStock) -> None:
        """가상매매 모드일 때 가상매매 기록 ID 설정"""
        try:
            from config.settings import load_config
            config = load_config()
            if getattr(config, 'paper_trading', False):
                from db.database_manager import DatabaseManager
                db = DatabaseManager()
                # 최근 가상매매 매수 기록 조회
                open_positions = db.get_virtual_open_positions()
                stock_positions = open_positions[
                    open_positions['stock_code'] == trading_stock.stock_code
                ]
                if not stock_positions.empty:
                    latest_position = stock_positions.iloc[0]
                    buy_record_id = latest_position['id']
                    buy_price = latest_position['buy_price']
                    quantity = latest_position['quantity']
                    trading_stock.set_virtual_buy_info(buy_record_id, buy_price, quantity)

                    # 목표 익절/손절률 로드
                    if ('target_profit_rate' in latest_position and
                            pd.notna(latest_position['target_profit_rate'])):
                        trading_stock.target_profit_rate = float(
                            latest_position['target_profit_rate']
                        )
                    if ('stop_loss_rate' in latest_position and
                            pd.notna(latest_position['stop_loss_rate'])):
                        trading_stock.stop_loss_rate = float(
                            latest_position['stop_loss_rate']
                        )

                    self.logger.debug(
                        f"가상매매 포지션 정보 설정: {trading_stock.stock_code} "
                        f"ID={buy_record_id} "
                        f"(익절: {trading_stock.target_profit_rate*100:.1f}%, "
                        f"손절: {trading_stock.stop_loss_rate*100:.1f}%)"
                    )
        except Exception as virtual_err:
            self.logger.warning(f"가상매매 포지션 정보 설정 실패: {virtual_err}")

    def _save_real_buy_record(self, trading_stock: TradingStock, order, source: str = "") -> None:
        """실거래 매수 기록 저장"""
        try:
            from db.database_manager import DatabaseManager
            db = DatabaseManager()
            reason = "체결" if not source else f"체결({source})"
            db.save_real_buy(
                stock_code=trading_stock.stock_code,
                stock_name=trading_stock.stock_name,
                price=float(order.price),
                quantity=int(order.quantity),
                strategy=trading_stock.selection_reason,
                reason=reason
            )
        except Exception as db_err:
            self.logger.warning(f"실거래 매수 기록 저장 실패: {db_err}")

    def _save_real_sell_record(self, trading_stock: TradingStock, order,
                               source: str = "") -> float:
        """
        실거래 매도 기록 저장

        Returns:
            float: 수익률
        """
        profit_rate = 0.0
        try:
            from db.database_manager import DatabaseManager
            db = DatabaseManager()
            buy_id = db.get_last_open_real_buy(trading_stock.stock_code)

            # 수익률 계산을 위해 매수가 조회
            buy_price = None
            if buy_id and trading_stock.position and trading_stock.position.avg_price:
                buy_price = trading_stock.position.avg_price
                profit_rate = ((float(order.price) - buy_price) / buy_price) * 100

            reason = "체결" if not source else f"체결({source})"
            db.save_real_sell(
                stock_code=trading_stock.stock_code,
                stock_name=trading_stock.stock_name,
                price=float(order.price),
                quantity=int(order.quantity),
                strategy=trading_stock.selection_reason,
                reason=reason,
                buy_record_id=buy_id
            )

        except Exception as db_err:
            self.logger.warning(f"실거래 매도 기록 저장 실패: {db_err}")

        return profit_rate
