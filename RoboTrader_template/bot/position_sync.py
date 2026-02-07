"""
포지션 동기화 모듈
긴급 포지션 동기화 로직을 담당합니다.
"""
import asyncio
from typing import TYPE_CHECKING

from core.models import StockState
from utils.logger import setup_logger

if TYPE_CHECKING:
    from main import DayTradingBot


class PositionSyncManager:
    """포지션 동기화 관리 클래스"""

    def __init__(self, bot: 'DayTradingBot'):
        self.bot = bot
        self.logger = setup_logger(__name__)

    async def emergency_sync_positions(self):
        """긴급 포지션 동기화 - 매수가 기준 3%/2% 고정 비율"""
        try:
            self.logger.info("긴급 포지션 동기화 시작")

            # 실제 잔고 조회
            loop = asyncio.get_event_loop()
            balance = await loop.run_in_executor(
                None,
                self.bot.api_manager.get_account_balance
            )
            if not balance or not balance.positions:
                self.logger.info("보유 종목 없음")
                return

            held_stocks = {
                p['stock_code']: p for p in balance.positions
                if p.get('quantity', 0) > 0
            }

            self.logger.info(f"실제 계좌 보유 종목: {list(held_stocks.keys())}")
            self.logger.info(f"시스템 관리 종목: {list(self.bot.trading_manager.trading_stocks.keys())}")

            # 시스템에서 누락된 포지션 찾기
            missing_positions = []
            unmanaged_stocks = []
            for code, balance_stock in held_stocks.items():
                if code in self.bot.trading_manager.trading_stocks:
                    ts = self.bot.trading_manager.trading_stocks[code]
                    if ts.state != StockState.POSITIONED:
                        missing_positions.append((code, balance_stock, ts))
                        self.logger.info(f"{code}: 보유중이지만 상태가 {ts.state.value} (복구 필요)")
                    else:
                        self.logger.info(f"{code}: 정상 동기화됨 (상태: {ts.state.value})")
                else:
                    unmanaged_stocks.append((code, balance_stock))
                    self.logger.warning(f"{code}: 보유중이지만 시스템에서 관리되지 않음")

            # 미관리 보유 종목을 시스템에 추가
            if unmanaged_stocks:
                await self._add_unmanaged_stocks(unmanaged_stocks, missing_positions)

            if not missing_positions:
                self.logger.info("모든 포지션이 정상 동기화됨")
                return

            # 누락된 포지션들 복구
            await self._restore_missing_positions(missing_positions)

            self.logger.info(f"총 {len(missing_positions)}개 종목 긴급 복구 완료")

            # 텔레그램 알림
            if missing_positions:
                await self._send_sync_notification(missing_positions)

        except Exception as e:
            self.logger.error(f"긴급 포지션 동기화 실패: {e}")
            await self.bot.telegram.notify_error("Emergency Position Sync", e)

    async def _add_unmanaged_stocks(self, unmanaged_stocks: list, missing_positions: list):
        """미관리 보유 종목을 시스템에 추가"""
        self.logger.warning(f"미관리 보유 종목 발견: {[code for code, _ in unmanaged_stocks]}")
        for code, balance_stock in unmanaged_stocks:
            try:
                stock_name = balance_stock.get('stock_name', f'Stock_{code}')
                quantity = balance_stock['quantity']
                avg_price = balance_stock['avg_price']

                self.logger.info(
                    f"미관리 종목 시스템 추가: {code}({stock_name}) {quantity}주 @{avg_price:,.0f}"
                )

                # 거래 상태 관리자에 추가 (POSITIONED 상태로 즉시 설정)
                success = await self.bot.trading_manager.add_selected_stock(
                    stock_code=code,
                    stock_name=stock_name,
                    selection_reason=f"보유종목 자동복구 ({quantity}주 @{avg_price:,.0f})",
                    prev_close=avg_price  # 전날종가는 매수가로 대체
                )

                if success:
                    # 추가된 종목을 즉시 POSITIONED 상태로 설정
                    ts = self.bot.trading_manager.get_trading_stock(code)
                    if ts:
                        ts.set_position(quantity, avg_price)
                        ts.clear_current_order()
                        ts.is_buying = False
                        ts.order_processed = True

                        self.bot.trading_manager._change_stock_state(
                            code, StockState.POSITIONED,
                            f"미관리종목 복구: {quantity}주 @{avg_price:,.0f}원"
                        )

                        self.logger.info(f"{code} 미관리 종목 복구 완료")

                        # missing_positions에도 추가하여 통합 처리
                        missing_positions.append((code, balance_stock, ts))

            except Exception as e:
                self.logger.error(f"{code} 미관리 종목 복구 실패: {e}")

    async def _restore_missing_positions(self, missing_positions: list):
        """누락된 포지션 복구"""
        for code, balance_stock, ts in missing_positions:
            # 포지션 복원
            quantity = balance_stock['quantity']
            avg_price = balance_stock['avg_price']
            ts.set_position(quantity, avg_price)
            ts.clear_current_order()
            ts.is_buying = False
            ts.order_processed = True

            # 매수가 기준 고정 비율로 목표가격 계산 (로깅용 - config에서 읽기)
            buy_price = avg_price
            take_profit_ratio = self.bot.config.risk_management.take_profit_ratio
            stop_loss_ratio = self.bot.config.risk_management.stop_loss_ratio
            target_price = buy_price * (1 + take_profit_ratio)
            stop_loss = buy_price * (1 - stop_loss_ratio)

            # 상태 변경
            self.bot.trading_manager._change_stock_state(
                code, StockState.POSITIONED,
                f"잔고복구: {quantity}주 @{buy_price:,.0f}원, "
                f"목표: +{take_profit_ratio*100:.1f}%/-{stop_loss_ratio*100:.1f}%"
            )

            self.logger.info(
                f"{code} 복구완료: 매수 {buy_price:,.0f} -> "
                f"목표 {target_price:,.0f} / 손절 {stop_loss:,.0f}"
            )

    async def _send_sync_notification(self, missing_positions: list):
        """동기화 결과 텔레그램 알림"""
        message = f"포지션 동기화 복구\n"
        message += f"복구된 종목: {len(missing_positions)}개\n"
        for code, balance_stock, _ in missing_positions[:3]:  # 최대 3개만
            quantity = balance_stock['quantity']
            avg_price = balance_stock['avg_price']
            message += f"- {code}: {quantity}주 @{avg_price:,.0f}원\n"
        await self.bot.telegram.notify_system_status(message)
