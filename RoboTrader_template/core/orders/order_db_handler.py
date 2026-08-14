"""
주문 DB 저장 처리 모듈
- 실전 매매 거래 기록 DB 저장
"""
import inspect
from typing import TYPE_CHECKING

from ..models import OrderType

if TYPE_CHECKING:
    from .order_base import OrderManagerBase


class OrderDBHandlerMixin:
    """주문 DB 저장 관련 메서드들을 모아둔 Mixin 클래스"""

    def _get_owned_trading_stock(self: 'OrderManagerBase', order):
        """주문에 실린 owner 로 소유 슬롯을 조회한다.

        종목코드 단독 조회는 두 전략이 같은 종목을 보유할 때
        stock_state_manager:310-315 에서 [모호조회] 를 찍고 matches[0](임의
        소유자)을 돌려준다. owner 지정 조회를 먼저 하고, 미해석일 때만
        레거시 폴백으로 떨어진다(2026-08-14 Fix 2).
        """
        tm = self.trading_manager
        if not tm or not hasattr(tm, 'get_trading_stock'):
            return None
        owner = (getattr(order, 'owner_strategy', '') or '').strip()
        stock_code = order.stock_code
        for strategy in ([owner] if owner else []) + [None]:
            try:
                ts = tm.get_trading_stock(stock_code, strategy=strategy)
                # AsyncMock 등에서 coroutine이 반환될 수 있으므로 방어
                if inspect.iscoroutine(ts):
                    ts.close()  # 코루틴 GC 경고 방지
                    ts = None
            except Exception:
                ts = None
            if ts is not None:
                if strategy is None and owner:
                    self.logger.warning(
                        f"[{stock_code}] 주문 owner={owner!r} 슬롯 미발견 — "
                        f"종목코드 단독 폴백(다중소유면 임의 소유자다)"
                    )
                return ts
        return None

    def _get_strategy_name_for_order(self: 'OrderManagerBase', order) -> str:
        """주문 DB 저장 시 순수 전략 이름 조회

        우선순위:
        1. order.owner_strategy (주문 접수 시 슬롯에서 복사한 소유 전략 표기)
        2. trading_stock.strategy_name (owner 지정 조회 → 레거시 폴백)
        3. "unknown" + WARNING (다전략 환경에서 오귀속 방지)

        ⚠️ 종전 구현은 1번이 없고 2번을 **strategy 인자 없이** 조회해, 두 전략이
        같은 종목을 보유하면 임의 소유자의 이름으로 실전 체결을 기록했다.
        주문 자신이 owner 를 싣고 다니면 조회 자체가 필요 없다.

        Note: config.strategy.name fallback은 단일 전략 환경에서만 의미가 있어
              다전략 환경에서 잘못된 전략으로 기록될 수 있으므로 제거.
        """
        stock_code = order.stock_code

        # 1. 주문에 실린 소유 전략 표기 (SSOT)
        owner = (getattr(order, 'owner_strategy', '') or '').strip()
        if owner:
            return owner

        # 2. 슬롯 조회 (owner 미지정 레거시 주문)
        ts = self._get_owned_trading_stock(order)
        if ts is not None and getattr(ts, 'strategy_name', ''):
            return ts.strategy_name

        # 3. strategy_name 미설정 — 다전략 환경에서 오귀속 위험
        self.logger.warning(
            f"[{stock_code}] 주문 owner·trading_stock.strategy_name 모두 미설정. "
            f"DB 기록을 'unknown'으로 저장. 다전략 환경에서는 strategy_name을 명시적으로 설정하세요."
        )
        return "unknown"

    async def _save_real_trade_to_db(self: 'OrderManagerBase', order, filled_price: float) -> None:
        """
        실전 매매 시 DB에 거래 기록 저장

        Args:
            order: 체결된 Order 객체
            filled_price: 실제 체결가
        """
        try:
            # 가상매매 모드면 이미 저장됨 (place_buy_order/place_sell_order에서 처리)
            if getattr(self.config, "paper_trading", True):
                return

            if not self.db_manager:
                self.logger.warning("DB 매니저가 없어 실전 거래 기록을 저장할 수 없음")
                return

            stock_name = order.stock_name or f'Stock_{order.stock_code}'

            if order.order_type == OrderType.BUY:
                await self._save_real_buy_to_db(order, filled_price, stock_name)
            elif order.order_type == OrderType.SELL:
                await self._save_real_sell_to_db(order, filled_price, stock_name)

        except Exception as e:
            self.logger.error(f"실전 거래 DB 저장 오류: {e}")

    async def _save_real_buy_to_db(self: 'OrderManagerBase', order, filled_price: float, stock_name: str) -> None:
        """실전 매수 기록 DB 저장"""
        strategy_name = self._get_strategy_name_for_order(order)
        buy_record_id = self.db_manager.save_real_buy(
            stock_code=order.stock_code,
            stock_name=stock_name,
            price=filled_price,  # 실제 체결가 사용
            quantity=order.quantity,
            strategy=strategy_name,
            reason="실전매매"
        )
        if buy_record_id:
            # 받은 PK 를 **소유 슬롯**에 적재한다. 안 넣으면 실전 모드에서
            # _virtual_buy_record_id 가 영원히 None 이라(이 필드는 이름만
            # "virtual" 이고 실전 매도가 읽는 자리다) 매도 짝짓기가 전적으로
            # get_last_open_real_buy 종목코드 조회에 의존한다 — 다중소유에서
            # 남의 매수행에 붙는다(2026-08-14 리뷰 R3).
            ts = self._get_owned_trading_stock(order)
            if ts is not None and hasattr(ts, 'set_virtual_buy_info'):
                try:
                    ts.set_virtual_buy_info(buy_record_id, filled_price, order.quantity)
                except Exception as e:
                    self.logger.warning(f"매수 기록 ID 적재 실패({order.stock_code}): {e}")
            self.logger.info(f"실전 매수 기록 저장: {order.stock_code} {order.quantity}주 @{filled_price:,.0f}원 (ID: {buy_record_id})")
        else:
            self.logger.error(f"실전 매수 기록 저장 실패: {order.stock_code}")

    async def _save_real_sell_to_db(self: 'OrderManagerBase', order, filled_price: float, stock_name: str) -> None:
        """실전 매도 기록 DB 저장"""
        # 매수 기록 ID 조회 (주문 owner 소유 슬롯에서 — 다중소유 오귀속 방지)
        buy_record_id = None
        trading_stock = self._get_owned_trading_stock(order)
        if trading_stock is not None and hasattr(trading_stock, '_virtual_buy_record_id'):
            buy_record_id = trading_stock._virtual_buy_record_id

        # buy_record_id가 없으면 DB에서 조회 (재기동 후 — 복원은 id 를 안 채운다).
        # 반드시 owner 를 실어 남의 매수행에 붙지 않게 한다.
        if not buy_record_id:
            buy_record_id = self.db_manager.get_last_open_real_buy(
                order.stock_code,
                (getattr(order, 'owner_strategy', '') or '').strip() or None,
            )

        # 실전 매도 기록 저장
        strategy_name = self._get_strategy_name_for_order(order)
        success = self.db_manager.save_real_sell(
            stock_code=order.stock_code,
            stock_name=stock_name,
            price=filled_price,  # 실제 체결가 사용
            quantity=order.quantity,
            strategy=strategy_name,
            reason="실전매매",
            buy_record_id=buy_record_id
        )
        if success:
            self.logger.info(f"실전 매도 기록 저장: {order.stock_code} {order.quantity}주 @{filled_price:,.0f}원")
        else:
            self.logger.error(f"실전 매도 기록 저장 실패: {order.stock_code}")
