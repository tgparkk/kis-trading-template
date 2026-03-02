"""
종목 상태 관리 모듈

종목의 등록/해제 및 상태 변경 관리
"""
import threading
from typing import Dict, List, Optional, Any

from ..models import TradingStock, StockState
from utils.logger import setup_logger
from utils.korean_time import now_kst


class StockStateManager:
    """
    종목 상태 관리자

    주요 기능:
    1. 종목 등록/해제
    2. 상태 변경 관리
    3. 상태별 종목 조회
    """

    def __init__(self):
        """초기화"""
        self.logger = setup_logger(__name__)

        # 종목 상태 관리
        self.trading_stocks: Dict[str, TradingStock] = {}
        self.stocks_by_state: Dict[StockState, Dict[str, TradingStock]] = {
            state: {} for state in StockState
        }

        # 동기화
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """Lock 객체 반환"""
        return self._lock

    def register_stock(self, trading_stock: TradingStock) -> None:
        """
        종목 등록

        Args:
            trading_stock: 등록할 TradingStock 객체
        """
        stock_code = trading_stock.stock_code
        state = trading_stock.state

        self.trading_stocks[stock_code] = trading_stock
        self.stocks_by_state[state][stock_code] = trading_stock

    def unregister_stock(self, stock_code: str) -> None:
        """
        종목 등록 해제

        Args:
            stock_code: 해제할 종목 코드
        """
        if stock_code in self.trading_stocks:
            trading_stock = self.trading_stocks[stock_code]
            state = trading_stock.state

            del self.trading_stocks[stock_code]
            if stock_code in self.stocks_by_state[state]:
                del self.stocks_by_state[state][stock_code]

    def change_stock_state(self, stock_code: str, new_state: StockState, reason: str = "") -> None:
        """
        종목 상태 변경

        Args:
            stock_code: 종목 코드
            new_state: 새로운 상태
            reason: 변경 사유
        """
        if stock_code not in self.trading_stocks:
            return

        trading_stock = self.trading_stocks[stock_code]
        old_state = trading_stock.state

        # 기존 상태에서 제거
        if stock_code in self.stocks_by_state[old_state]:
            del self.stocks_by_state[old_state][stock_code]

        # 새 상태로 변경
        trading_stock.change_state(new_state, reason)
        self.stocks_by_state[new_state][stock_code] = trading_stock

        # 상세 상태 변화 로깅
        self._log_detailed_state_change(trading_stock, old_state, new_state, reason)

    def _log_detailed_state_change(self, trading_stock: TradingStock,
                                   old_state: StockState, new_state: StockState,
                                   reason: str):
        """
        상세 상태 변화 로깅

        Args:
            trading_stock: 종목 객체
            old_state: 이전 상태
            new_state: 새 상태
            reason: 변경 사유
        """
        try:
            current_time = now_kst().strftime('%H:%M:%S')

            # 수익률 계산 (condensed line용)
            profit_str = ""
            profit_rate = 0.0
            if trading_stock.position and trading_stock.position.current_price > 0 and trading_stock.position.avg_price > 0:
                profit_rate = (
                    (trading_stock.position.current_price - trading_stock.position.avg_price)
                    / trading_stock.position.avg_price
                ) * 100
                profit_str = f" | 수익률: {profit_rate:+.2f}%"

            # 단일 요약 INFO 라인
            reason_str = f" | {reason}" if reason else ""
            self.logger.info(
                f"[상태변경] {trading_stock.stock_code}({trading_stock.stock_name}) "
                f"{old_state.value} → {new_state.value}{reason_str}{profit_str}"
            )

            # 상세 정보는 DEBUG 레벨로
            log_parts = [
                f"[{current_time}] {trading_stock.stock_code}({trading_stock.stock_name})",
                f"상태변경: {old_state.value} -> {new_state.value}",
                f"사유: {reason}"
            ]

            # 포지션 정보
            if trading_stock.position:
                log_parts.append(
                    f"포지션: {trading_stock.position.quantity}주 "
                    f"@{trading_stock.position.avg_price:,.0f}원"
                )
                if trading_stock.position.current_price > 0:
                    log_parts.append(
                        f"현재가: {trading_stock.position.current_price:,.0f}원 ({profit_rate:+.2f}%)"
                    )
            else:
                log_parts.append("포지션: 없음")

            # 주문 정보
            if trading_stock.current_order_id:
                log_parts.append(f"현재주문: {trading_stock.current_order_id}")
            else:
                log_parts.append("현재주문: 없음")

            # 선정 사유 및 시간
            log_parts.append(f"선정사유: {trading_stock.selection_reason}")
            log_parts.append(f"선정시간: {trading_stock.selected_time.strftime('%H:%M:%S')}")

            # 상태별 특별 정보
            state_messages = {
                StockState.BUY_PENDING: "매수 주문 실행됨 - 체결 대기 중",
                StockState.POSITIONED: "매수 체결 완료 - 포지션 보유 중",
                StockState.SELL_CANDIDATE: "매도 신호 발생 - 주문 대기 중",
                StockState.SELL_PENDING: "매도 주문 실행됨 - 체결 대기 중",
                StockState.COMPLETED: "거래 완료",
            }

            if new_state in state_messages:
                log_parts.append(state_messages[new_state])

            # 상세 로그는 DEBUG
            self.logger.debug("\n".join(f"  {part}" for part in log_parts))

        except Exception as e:
            self.logger.debug(f"상세 상태 변화 로깅 오류: {e}")
            # 기본 로그는 여전히 출력
            self.logger.info(
                f"{trading_stock.stock_code} 상태 변경: {old_state.value} -> {new_state.value}"
            )

    def get_stocks_by_state(self, state: StockState) -> List[TradingStock]:
        """
        특정 상태의 종목들 조회

        Args:
            state: 조회할 상태

        Returns:
            해당 상태의 TradingStock 리스트
        """
        with self._lock:
            return list(self.stocks_by_state[state].values())

    def get_trading_stock(self, stock_code: str) -> Optional[TradingStock]:
        """
        종목 정보 조회

        Args:
            stock_code: 종목 코드

        Returns:
            TradingStock 객체 또는 None
        """
        return self.trading_stocks.get(stock_code)

    def update_current_order(self, stock_code: str, new_order_id: str) -> None:
        """
        정정 등으로 새 주문이 생성되었을 때 현재 주문ID를 최신값으로 동기화

        Args:
            stock_code: 종목 코드
            new_order_id: 새 주문 ID
        """
        try:
            with self._lock:
                if stock_code in self.trading_stocks:
                    trading_stock = self.trading_stocks[stock_code]
                    trading_stock.current_order_id = new_order_id
                    trading_stock.order_history.append(new_order_id)
                    self.logger.debug(f"{stock_code} 현재 주문ID 업데이트: {new_order_id}")
        except Exception as e:
            self.logger.warning(f"현재 주문ID 업데이트 실패({stock_code}): {e}")

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        포트폴리오 전체 현황 조회

        Returns:
            포트폴리오 요약 딕셔너리
        """
        try:
            with self._lock:
                summary = {
                    'total_stocks': len(self.trading_stocks),
                    'by_state': {},
                    'positions': [],
                    'pending_orders': [],
                    'current_time': now_kst().strftime('%Y-%m-%d %H:%M:%S')
                }

                # 상태별 종목 수
                for state in StockState:
                    count = len(self.stocks_by_state[state])
                    summary['by_state'][state.value] = count

                # 포지션 정보
                positioned_stocks = self.stocks_by_state[StockState.POSITIONED]
                total_value = 0
                total_pnl = 0

                for trading_stock in positioned_stocks.values():
                    if trading_stock.position:
                        position_value = (
                            trading_stock.position.current_price
                            * trading_stock.position.quantity
                        )
                        total_value += position_value
                        total_pnl += trading_stock.position.unrealized_pnl

                        summary['positions'].append({
                            'stock_code': trading_stock.stock_code,
                            'stock_name': trading_stock.stock_name,
                            'quantity': trading_stock.position.quantity,
                            'avg_price': trading_stock.position.avg_price,
                            'current_price': trading_stock.position.current_price,
                            'unrealized_pnl': trading_stock.position.unrealized_pnl,
                            'position_value': position_value
                        })

                summary['total_position_value'] = total_value
                summary['total_unrealized_pnl'] = total_pnl

                # 미체결 주문 정보
                for state in [StockState.BUY_PENDING, StockState.SELL_PENDING]:
                    for trading_stock in self.stocks_by_state[state].values():
                        if trading_stock.current_order_id:
                            summary['pending_orders'].append({
                                'stock_code': trading_stock.stock_code,
                                'stock_name': trading_stock.stock_name,
                                'order_id': trading_stock.current_order_id,
                                'state': state.value
                            })

                return summary

        except Exception as e:
            self.logger.error(f"포트폴리오 요약 생성 오류: {e}")
            return {}
