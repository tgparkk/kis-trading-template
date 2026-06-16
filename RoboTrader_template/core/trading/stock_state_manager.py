"""
종목 상태 관리 모듈

종목의 등록/해제 및 상태 변경 관리
"""
import threading
from typing import Dict, List, Optional, Any, Tuple

from ..models import TradingStock, StockState
from utils.logger import setup_logger
from utils.korean_time import now_kst

# 유효한 상태 전이 맵: {현재 상태: [허용되는 다음 상태들]}
_VALID_TRANSITIONS: Dict[StockState, List[StockState]] = {
    StockState.SELECTED: [StockState.BUY_PENDING, StockState.COMPLETED, StockState.FAILED],
    StockState.BUY_PENDING: [StockState.POSITIONED, StockState.SELECTED, StockState.COMPLETED, StockState.FAILED],
    StockState.POSITIONED: [StockState.SELL_CANDIDATE, StockState.COMPLETED, StockState.FAILED],
    StockState.SELL_CANDIDATE: [StockState.SELL_PENDING, StockState.POSITIONED, StockState.COMPLETED, StockState.FAILED],
    StockState.SELL_PENDING: [StockState.COMPLETED, StockState.POSITIONED, StockState.SELL_CANDIDATE, StockState.FAILED],
    StockState.COMPLETED: [StockState.SELECTED],
    StockState.FAILED: [StockState.SELECTED, StockState.COMPLETED],
}


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

        # 종목 상태 관리 (안정 슬롯 키: owner 가변성에 견고 + 다owner 동일종목 지원)
        # 슬롯은 등록 시 1회 부여되어 owner 변경·상태 전이에도 불변. owner는 항상
        # 객체에서 직접(live) 읽어 비교하므로 키가 stale해지지 않는다.
        self._next_slot: int = 0
        self.trading_stocks: Dict[int, TradingStock] = {}            # slot -> ts
        self._slots_by_code: Dict[str, List[int]] = {}              # code -> [slot,...]
        self.stocks_by_state: Dict[StockState, Dict[int, TradingStock]] = {
            state: {} for state in StockState
        }

        # 동기화
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """Lock 객체 반환"""
        return self._lock

    def _slot_for(self, trading_stock: TradingStock) -> Optional[int]:
        """객체의 현재 슬롯을 identity로 조회 (lock 보유 가정)."""
        for slot in self._slots_by_code.get(trading_stock.stock_code, []):
            if self.trading_stocks.get(slot) is trading_stock:
                return slot
        return None

    def _remove(self, trading_stock: TradingStock) -> None:
        """슬롯 기준으로 모든 인덱스에서 객체 제거 (lock 보유 가정)."""
        slot = self._slot_for(trading_stock)
        if slot is None:
            return
        self.trading_stocks.pop(slot, None)
        self.stocks_by_state[trading_stock.state].pop(slot, None)
        slots = self._slots_by_code.get(trading_stock.stock_code)
        if slots and slot in slots:
            slots.remove(slot)
            if not slots:
                self._slots_by_code.pop(trading_stock.stock_code, None)

    def _find_by_code(self, stock_code: str, strategy: Optional[str] = None) -> List[TradingStock]:
        """종목 코드(+선택적 전략)로 TradingStock 목록 조회.

        owner_strategy_name을 객체에서 직접(live) 비교하므로 등록 후 owner가
        바뀌어도 안전하다. 호출자가 lock을 보유한 상태에서 호출되어야 한다.
        """
        slots = self._slots_by_code.get(stock_code, [])
        out = [self.trading_stocks[s] for s in slots if s in self.trading_stocks]
        if strategy is not None:
            out = [ts for ts in out if ts.owner_strategy_name == strategy]
        return out

    def register_stock(self, trading_stock: TradingStock) -> bool:
        """
        종목 등록

        동일 전략(owner)이 POSITIONED/BUY_PENDING 상태로 이미 보유 중이면 거부합니다.
        다른 전략이 같은 종목을 보유하는 것은 허용합니다(전략별 자본 독립).
        동일 owner의 그 외 상태(SELECTED, COMPLETED, FAILED 등)는 덮어쓰기 허용합니다.

        Args:
            trading_stock: 등록할 TradingStock 객체

        Returns:
            True: 등록 성공, False: 동일 전략 POSITIONED/BUY_PENDING 중복으로 거부
        """
        with self._lock:
            owner = trading_stock.owner_strategy_name
            same_owner = [
                ts for ts in self._find_by_code(trading_stock.stock_code)
                if ts.owner_strategy_name == owner
            ]
            for existing in same_owner:
                if existing.state in (StockState.POSITIONED, StockState.BUY_PENDING):
                    self.logger.info(
                        f"[중복등록거부] {trading_stock.stock_code} owner={owner} "
                        f"state={existing.state.name} — 동일 전략 중복"
                    )
                    return False
            # 동일 owner의 비활성 상태 엔트리는 덮어쓰기(제거 후 신규 슬롯 등록)
            for existing in same_owner:
                self._remove(existing)

            slot = self._next_slot
            self._next_slot += 1
            self.trading_stocks[slot] = trading_stock
            self._slots_by_code.setdefault(trading_stock.stock_code, []).append(slot)
            self.stocks_by_state[trading_stock.state][slot] = trading_stock
            return True

    def unregister_stock(self, stock_code: str, strategy: Optional[str] = None) -> None:
        """
        종목 등록 해제

        Args:
            stock_code: 해제할 종목 코드
            strategy: 소유 전략(미지정 시 종목 코드만으로 매칭)
        """
        with self._lock:
            matches = self._find_by_code(stock_code, strategy)
            if not matches:
                return
            if len(matches) > 1:
                self.logger.warning(
                    f"[모호해제] {stock_code} 다중 소유 — strategy 미지정, 첫 소유자 적용"
                )
            self._remove(matches[0])

    def change_stock_state(self, stock_code: str, new_state: StockState,
                           reason: str = "", strategy: Optional[str] = None) -> None:
        """
        종목 상태 변경

        Args:
            stock_code: 종목 코드
            new_state: 새로운 상태
            reason: 변경 사유
            strategy: 소유 전략(미지정 시 종목 코드만으로 매칭)
        """
        with self._lock:
            matches = self._find_by_code(stock_code, strategy)
            if not matches:
                return
            if len(matches) > 1:
                self.logger.warning(
                    f"[모호상태변경] {stock_code} 다중 소유 — strategy 미지정, 첫 소유자 적용"
                )
            trading_stock = matches[0]
            slot = self._slot_for(trading_stock)
            if slot is None:
                return
            old_state = trading_stock.state

            # 상태 전이 규칙 검증 (비정상 전이는 경고만, 차단하지 않음)
            valid_next_states = _VALID_TRANSITIONS.get(old_state, [])
            if new_state not in valid_next_states:
                self.logger.warning(
                    f"[비정상 상태전이] {stock_code} {old_state.value} → {new_state.value} "
                    f"(허용: {[s.value for s in valid_next_states]}) | 사유: {reason}"
                )

            # 기존 상태에서 제거 (슬롯 기준 — owner 변경에 무관하게 안정)
            self.stocks_by_state[old_state].pop(slot, None)

            # 새 상태로 변경
            trading_stock.change_state(new_state, reason)
            self.stocks_by_state[new_state][slot] = trading_stock

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

    def get_trading_stock(self, stock_code: str, strategy: Optional[str] = None) -> Optional[TradingStock]:
        """
        종목 정보 조회

        주의: 원본 TradingStock 객체의 참조를 반환합니다.
        반환된 객체의 state를 직접 수정하지 마세요.
        상태 변경은 반드시 change_stock_state()를 통해서만 수행해야
        stocks_by_state 인덱스와의 일관성이 보장됩니다.

        Args:
            stock_code: 종목 코드
            strategy: 소유 전략(미지정 시 종목 코드만으로 매칭)

        Returns:
            TradingStock 객체 또는 None
        """
        with self._lock:
            matches = self._find_by_code(stock_code, strategy)
            if not matches:
                return None
            if len(matches) > 1:
                self.logger.warning(
                    f"[모호조회] {stock_code} 다중 소유({len(matches)}) — strategy 인자 필요. "
                    f"첫 소유자 반환: {matches[0].owner_strategy_name}"
                )
            return matches[0]

    def update_current_order(self, stock_code: str, new_order_id: str,
                             strategy: Optional[str] = None) -> None:
        """
        정정 등으로 새 주문이 생성되었을 때 현재 주문ID를 최신값으로 동기화

        Args:
            stock_code: 종목 코드
            new_order_id: 새 주문 ID
            strategy: 소유 전략(미지정 시 종목 코드만으로 매칭)
        """
        try:
            with self._lock:
                matches = self._find_by_code(stock_code, strategy)
                if not matches:
                    return
                if len(matches) > 1:
                    self.logger.warning(
                        f"[모호주문갱신] {stock_code} 다중 소유 — strategy 미지정, 첫 소유자 적용"
                    )
                trading_stock = matches[0]
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
