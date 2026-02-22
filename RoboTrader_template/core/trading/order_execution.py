"""
주문 실행 모듈

매수/매도 주문 실행 및 종목 선정 관리
"""
from typing import TYPE_CHECKING, Optional

from ..models import TradingStock, StockState
from utils.logger import setup_logger
from utils.korean_time import now_kst

if TYPE_CHECKING:
    from .stock_state_manager import StockStateManager
    from ..intraday_stock_manager import IntradayStockManager
    from ..data_collector import RealTimeDataCollector
    from ..order_manager import OrderManager
    from ..fund_manager import FundManager


class OrderExecution:
    """
    주문 실행 관리자

    주요 기능:
    1. 선정된 종목 추가
    2. 매수 주문 실행
    3. 매도 후보 전환
    4. 매도 주문 실행
    """

    def __init__(self, state_manager: 'StockStateManager',
                 intraday_manager: 'IntradayStockManager',
                 data_collector: 'RealTimeDataCollector',
                 order_manager: 'OrderManager') -> None:
        """
        초기화

        Args:
            state_manager: 종목 상태 관리자
            intraday_manager: 장중 종목 관리자
            data_collector: 실시간 데이터 수집기
            order_manager: 주문 관리자
        """
        self.state_manager = state_manager
        self.intraday_manager = intraday_manager
        self.data_collector = data_collector
        self.order_manager = order_manager
        self.logger = setup_logger(__name__)

        # FundManager 연결 (나중에 설정)
        self.fund_manager: Optional['FundManager'] = None

        # 재거래 설정
        self.enable_re_trading = True

    def set_fund_manager(self, fund_manager: 'FundManager') -> None:
        """FundManager 설정"""
        self.fund_manager = fund_manager
        self.logger.debug("OrderExecution에 FundManager 연결 완료")

    async def add_selected_stock(self, stock_code: str, stock_name: str,
                                 selection_reason: str = "", prev_close: float = 0.0) -> bool:
        """
        조건검색으로 선정된 종목 추가 (비동기)

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            selection_reason: 선정 사유
            prev_close: 전날 종가 (일봉 기준)

        Returns:
            bool: 추가 성공 여부
        """
        try:
            with self.state_manager.lock:
                current_time = now_kst()

                # 이미 존재하는 종목인지 확인
                if stock_code in self.state_manager.trading_stocks:
                    trading_stock = self.state_manager.trading_stocks[stock_code]
                    # 재진입 허용: COMPLETED/FAILED -> SELECTED로 재등록
                    if trading_stock.state in (StockState.COMPLETED, StockState.FAILED):
                        # 상태 변경 및 메타 업데이트
                        trading_stock.selected_time = current_time
                        trading_stock.selection_reason = selection_reason
                        # 포지션/주문 정보는 정리
                        trading_stock.clear_position()
                        trading_stock.clear_current_order()
                        self.state_manager.change_stock_state(
                            stock_code, StockState.SELECTED, f"재선정: {selection_reason}"
                        )

                        # IntradayStockManager에 다시 추가 (비동기 대기)
                        success = await self.intraday_manager.add_selected_stock(
                            stock_code, stock_name, selection_reason
                        )
                        if success:
                            self.logger.info(
                                f"{stock_code}({stock_name}) 재선정 완료 - "
                                f"시간: {current_time.strftime('%H:%M:%S')}"
                            )
                            return True
                        else:
                            self.logger.warning(f"{stock_code} 재선정 실패 - Intraday 등록 실패")
                            return False

                    # 그 외 상태에서는 기존 관리 유지
                    return True

                # 신규 등록
                trading_stock = TradingStock(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    state=StockState.SELECTED,
                    selected_time=current_time,
                    selection_reason=selection_reason,
                    prev_close=prev_close
                )

                # 등록
                self.state_manager.register_stock(trading_stock)

            # IntradayStockManager에 추가 (비동기 대기)
            success = await self.intraday_manager.add_selected_stock(
                stock_code, stock_name, selection_reason
            )

            if success:
                self.logger.info(
                    f"{stock_code}({stock_name}) 선정 완료 - "
                    f"시간: {current_time.strftime('%H:%M:%S')}"
                )
                return True
            else:
                # 실패 시 제거
                with self.state_manager.lock:
                    self.state_manager.unregister_stock(stock_code)
                return False

        except Exception as e:
            self.logger.error(f"{stock_code} 종목 추가 오류: {e}")
            return False

    async def execute_buy_order(self, stock_code: str, quantity: int,
                                price: float, reason: str = "") -> bool:
        """
        매수 주문 실행

        Args:
            stock_code: 종목코드
            quantity: 주문 수량
            price: 주문 가격
            reason: 매수 사유

        Returns:
            bool: 주문 성공 여부
        """
        try:
            with self.state_manager.lock:
                if stock_code not in self.state_manager.trading_stocks:
                    self.logger.warning(f"{stock_code}: 관리 중이지 않은 종목")
                    return False

                trading_stock = self.state_manager.trading_stocks[stock_code]

                # 중복 매수 방지: 이미 매수 진행 중인지 확인
                if trading_stock.is_buying:
                    self.logger.warning(f"{stock_code}: 이미 매수 진행 중 (중복 매수 방지)")
                    return False

                # 25분 매수 쿨다운 확인
                if trading_stock.is_buy_cooldown_active():
                    remaining_minutes = trading_stock.get_remaining_cooldown_minutes()
                    self.logger.warning(
                        f"{stock_code}: 매수 쿨다운 활성화 (남은 시간: {remaining_minutes}분)"
                    )
                    return False

                # FundManager 매도 후 재매수 쿨다운 확인
                if self.fund_manager and self.fund_manager.is_sell_cooldown_active(stock_code):
                    self.logger.warning(
                        f"{stock_code}: 매도 후 재매수 쿨다운 활성 (익절/손절 후 대기)"
                    )
                    return False

                # 동시 보유 종목 수 제한 확인
                if self.fund_manager and not self.fund_manager.can_add_position(stock_code):
                    self.logger.warning(
                        f"{stock_code}: 동시 보유 종목 수 초과로 매수 거부"
                    )
                    return False

                # 상태 검증 (SELECTED 또는 COMPLETED에서 직접 매수 가능)
                if trading_stock.state not in [StockState.SELECTED, StockState.COMPLETED]:
                    self.logger.warning(
                        f"{stock_code}: 매수 가능 상태가 아님 (현재: {trading_stock.state.value})"
                    )
                    return False

                # 매수 진행 플래그 설정
                trading_stock.is_buying = True
                trading_stock.order_processed = False  # 새 주문이므로 리셋

                # 매수 주문 중 상태로 변경
                self.state_manager.change_stock_state(
                    stock_code, StockState.BUY_PENDING, f"매수 주문: {reason}"
                )

                # 데이터 수집기에 후보 종목으로 추가 (실시간 모니터링)
                self.data_collector.add_candidate_stock(stock_code, trading_stock.stock_name)

            # 매수 주문 실행
            order_id = await self.order_manager.place_buy_order(stock_code, quantity, price)

            if order_id:
                with self.state_manager.lock:
                    trading_stock = self.state_manager.trading_stocks[stock_code]
                    trading_stock.add_order(order_id)

                self.logger.info(f"{stock_code} 매수 주문 성공: {order_id}")
                return True
            else:
                # 주문 실패 시 원래 상태로 되돌림 (SELECTED 또는 COMPLETED)
                with self.state_manager.lock:
                    trading_stock = self.state_manager.trading_stocks[stock_code]
                    # 매수 진행 플래그 리셋
                    trading_stock.is_buying = False

                    # 원래 상태 추정: 재거래면 COMPLETED, 신규면 SELECTED
                    original_state = (
                        StockState.COMPLETED if "재거래" in reason else StockState.SELECTED
                    )
                    self.state_manager.change_stock_state(
                        stock_code, original_state, "매수 주문 실패"
                    )
                return False

        except Exception as e:
            self.logger.error(f"{stock_code} 매수 주문 오류: {e}")
            # 오류 시 원래 상태로 되돌림
            with self.state_manager.lock:
                if stock_code in self.state_manager.trading_stocks:
                    original_state = (
                        StockState.COMPLETED if "재거래" in reason else StockState.SELECTED
                    )
                    self.state_manager.change_stock_state(
                        stock_code, original_state, f"매수 주문 오류: {e}"
                    )
            return False

    def move_to_sell_candidate(self, stock_code: str, reason: str = "") -> bool:
        """
        포지션 종목을 매도 후보로 변경

        Args:
            stock_code: 종목코드
            reason: 변경 사유

        Returns:
            bool: 변경 성공 여부
        """
        try:
            with self.state_manager.lock:
                if stock_code not in self.state_manager.trading_stocks:
                    self.logger.warning(f"{stock_code}: 관리 중이지 않은 종목")
                    return False

                trading_stock = self.state_manager.trading_stocks[stock_code]

                # 상태 검증 (POSITIONED 또는 SELL_CANDIDATE에서 매도 시도 가능)
                if trading_stock.state not in [StockState.POSITIONED, StockState.SELL_CANDIDATE]:
                    self.logger.warning(
                        f"{stock_code}: 매도 가능 상태가 아님 (현재: {trading_stock.state.value})"
                    )
                    return False

                # 포지션 확인
                if not trading_stock.position:
                    self.logger.warning(f"{stock_code}: 포지션 정보 없음")
                    return False

                # 상태 변경
                self.state_manager.change_stock_state(
                    stock_code, StockState.SELL_CANDIDATE, reason
                )

                self.logger.info(f"{stock_code} 매도 후보로 변경: {reason}")
                return True

        except Exception as e:
            self.logger.error(f"{stock_code} 매도 후보 변경 오류: {e}")
            return False

    async def execute_sell_order(self, stock_code: str, quantity: int,
                                 price: float, reason: str = "", market: bool = False) -> bool:
        """
        매도 주문 실행

        Args:
            stock_code: 종목코드
            quantity: 주문 수량
            price: 주문 가격
            reason: 매도 사유
            market: 시장가 주문 여부

        Returns:
            bool: 주문 성공 여부
        """
        try:
            with self.state_manager.lock:
                if stock_code not in self.state_manager.trading_stocks:
                    self.logger.warning(f"{stock_code}: 관리 중이지 않은 종목")
                    return False

                trading_stock = self.state_manager.trading_stocks[stock_code]

                # 상태 검증
                if trading_stock.state != StockState.SELL_CANDIDATE:
                    self.logger.warning(
                        f"{stock_code}: 매도 후보 상태가 아님 (현재: {trading_stock.state.value})"
                    )
                    return False

                # 매도 주문 중 상태로 변경
                self.state_manager.change_stock_state(
                    stock_code, StockState.SELL_PENDING, f"매도 주문: {reason}"
                )

            # 매도 주문 실행
            order_id = await self.order_manager.place_sell_order(
                stock_code, quantity, price, market=market
            )

            if order_id:
                with self.state_manager.lock:
                    trading_stock = self.state_manager.trading_stocks[stock_code]
                    trading_stock.add_order(order_id)

                self.logger.info(f"{stock_code} 매도 주문 성공: {order_id}")
                return True
            else:
                # 주문 실패 시 매도 후보로 되돌림
                with self.state_manager.lock:
                    self.state_manager.change_stock_state(
                        stock_code, StockState.SELL_CANDIDATE, "매도 주문 실패"
                    )
                return False

        except Exception as e:
            self.logger.error(f"{stock_code} 매도 주문 오류: {e}")
            # 오류 시 매도 후보로 되돌림
            with self.state_manager.lock:
                if stock_code in self.state_manager.trading_stocks:
                    self.state_manager.change_stock_state(
                        stock_code, StockState.SELL_CANDIDATE, f"매도 주문 오류: {e}"
                    )
            return False

    def remove_stock(self, stock_code: str, reason: str = "") -> bool:
        """
        종목 제거

        Args:
            stock_code: 종목코드
            reason: 제거 사유

        Returns:
            bool: 제거 성공 여부
        """
        try:
            with self.state_manager.lock:
                if stock_code not in self.state_manager.trading_stocks:
                    return False

                # 상태 변경 후 제거
                self.state_manager.change_stock_state(
                    stock_code, StockState.COMPLETED, f"제거: {reason}"
                )

                # 관련 관리자에서도 제거
                self.intraday_manager.remove_stock(stock_code)
                self.data_collector.remove_candidate_stock(stock_code)

                self.logger.info(f"{stock_code} 거래 관리에서 제거: {reason}")
                return True

        except Exception as e:
            self.logger.error(f"{stock_code} 제거 오류: {e}")
            return False

    async def handle_order_timeout(self, order) -> None:
        """
        OrderManager에서 타임아웃/취소된 주문 처리

        BUY_PENDING 상태인 종목을 다시 매수 가능한 상태로 복구합니다.

        Args:
            order: 타임아웃된 주문 객체 (Order)
        """
        try:
            stock_code = order.stock_code

            with self.state_manager.lock:
                if stock_code not in self.state_manager.trading_stocks:
                    self.logger.warning(f"타임아웃 처리할 종목 없음: {stock_code}")
                    return

                trading_stock = self.state_manager.trading_stocks[stock_code]

                # BUY_PENDING 상태인 경우 처리
                if trading_stock.state == StockState.BUY_PENDING:
                    # 매수 진행 플래그 해제
                    trading_stock.is_buying = False
                    trading_stock.current_order_id = None
                    trading_stock.order_processed = False

                    # 재거래가 활성화된 경우 COMPLETED로, 비활성화된 경우 SELECTED로 복구
                    if self.enable_re_trading:
                        self.state_manager.change_stock_state(
                            stock_code, StockState.COMPLETED,
                            "주문 타임아웃 복구 (재거래 가능)"
                        )
                        self.logger.info(
                            f"{stock_code} 타임아웃 복구 완료: BUY_PENDING -> COMPLETED (재거래 가능)"
                        )
                    else:
                        self.state_manager.change_stock_state(
                            stock_code, StockState.SELECTED,
                            "주문 타임아웃 복구"
                        )
                        self.logger.info(
                            f"{stock_code} 타임아웃 복구 완료: BUY_PENDING -> SELECTED (매수 재시도 가능)"
                        )

                # SELL_PENDING 상태인 경우 POSITIONED로 복원하여 재매도 가능하게
                elif trading_stock.state == StockState.SELL_PENDING:
                    trading_stock.current_order_id = None
                    trading_stock.order_processed = False

                    self.state_manager.change_stock_state(
                        stock_code, StockState.POSITIONED,
                        "매도 주문 타임아웃 복구 (재매도 가능)"
                    )
                    self.logger.info(
                        f"{stock_code} 타임아웃 복구 완료: SELL_PENDING -> POSITIONED (재매도 가능)"
                    )

                else:
                    self.logger.warning(
                        f"{stock_code} 예상치 못한 상태에서 타임아웃 처리: "
                        f"{trading_stock.state.value}"
                    )
                    return

        except Exception as e:
            self.logger.error(
                f"{order.stock_code if hasattr(order, 'stock_code') else 'Unknown'} "
                f"타임아웃 처리 오류: {e}"
            )

    async def on_partial_fill_timeout(self, order, filled_qty: int, filled_price: float) -> None:
        """
        부분 체결 타임아웃 처리 - 체결된 수량으로 포지션 설정

        Args:
            order: 부분 체결된 주문 객체 (Order)
            filled_qty: 체결된 수량
            filled_price: 체결 가격
        """
        stock_code = order.stock_code

        with self.state_manager.lock:
            if stock_code not in self.state_manager.trading_stocks:
                self.logger.warning(f"부분 체결 포지션 등록 실패: {stock_code} 종목 없음")
                return

            trading_stock = self.state_manager.trading_stocks[stock_code]
            trading_stock.is_buying = False
            trading_stock.set_position(filled_qty, filled_price)
            trading_stock.clear_current_order()
            trading_stock.set_buy_time(now_kst())

            self.state_manager.change_stock_state(
                stock_code, StockState.POSITIONED,
                f"부분 체결 타임아웃: {filled_qty}주 @{filled_price:,.0f}원"
            )

        self.logger.info(f"부분 체결 포지션 등록 완료: {stock_code} {filled_qty}주 @{filled_price:,.0f}원")

    def set_re_trading_config(self, enable: bool) -> None:
        """
        재거래 설정 변경

        Args:
            enable: 재거래 활성화 여부 (COMPLETED 상태에서 직접 매수 판단)
        """
        self.enable_re_trading = enable

        status = "활성화" if enable else "비활성화"
        self.logger.info(f"재거래 설정 변경: {status} (즉시 재거래 방식)")

    def get_re_trading_config(self) -> dict:
        """재거래 설정 조회"""
        return {
            "enable_re_trading": self.enable_re_trading
        }
