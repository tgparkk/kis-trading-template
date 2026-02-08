"""
청산 핸들러 모듈
장 마감 시 포지션 청산 로직을 담당합니다.
"""
from typing import TYPE_CHECKING

from core.models import StockState
from utils.logger import setup_logger
from utils.korean_time import now_kst
from utils.price_utils import round_to_tick
from config.market_hours import MarketHours

if TYPE_CHECKING:
    from main import DayTradingBot


class LiquidationHandler:
    """장 마감 청산 담당 클래스"""

    def __init__(self, bot: 'DayTradingBot'):
        self.bot = bot
        self.logger = setup_logger(__name__)
        self._last_eod_liquidation_date = None

    async def liquidate_all_positions_end_of_day(self):
        """장 마감 직전 보유 포지션 전량 시장가 일괄 청산"""
        try:
            positioned_stocks = self.bot.trading_manager.get_stocks_by_state(StockState.POSITIONED)

            # 실제 매매 모드: 실제 포지션만 처리
            if not positioned_stocks:
                self.logger.info("장마감 일괄청산: 보유 포지션 없음")
                return

            self.logger.info(f"장마감 일괄청산 시작: {len(positioned_stocks)}종목")

            # 실제 포지션 매도
            for trading_stock in positioned_stocks:
                try:
                    if not trading_stock.position or trading_stock.position.quantity <= 0:
                        continue
                    stock_code = trading_stock.stock_code
                    quantity = int(trading_stock.position.quantity)

                    # 가격 산정: 가능한 경우 최신 분봉 종가, 없으면 현재가 조회
                    sell_price = 0.0
                    combined_data = self.bot.intraday_manager.get_combined_chart_data(stock_code)
                    if combined_data is not None and len(combined_data) > 0:
                        sell_price = float(combined_data['close'].iloc[-1])
                    else:
                        price_obj = self.bot.broker.get_current_price(stock_code)
                        if price_obj:
                            sell_price = float(price_obj.current_price)
                    sell_price = round_to_tick(sell_price)

                    # 상태 전환 후 시장가 매도 주문 실행
                    moved = self.bot.trading_manager.move_to_sell_candidate(stock_code, "장마감 일괄청산")
                    if moved:
                        await self.bot.trading_manager.execute_sell_order(
                            stock_code, quantity, sell_price, "장마감 일괄청산", market=True
                        )
                        self.logger.info(
                            f"장마감 청산 주문: {stock_code} {quantity}주 시장가 @{sell_price:,.0f}원"
                        )
                except Exception as se:
                    self.logger.error(f"장마감 청산 개별 처리 오류({trading_stock.stock_code}): {se}")

            self.logger.info("장마감 일괄청산 요청 완료")

        except Exception as e:
            self.logger.error(f"장마감 일괄청산 오류: {e}")

    async def execute_end_of_day_liquidation(self):
        """장마감 시간 모든 보유 종목 시장가 일괄매도 (동적 시간 적용)"""
        try:
            # 동적 청산 시간 가져오기
            current_time = now_kst()
            market_hours = MarketHours.get_market_hours('KRX', current_time)
            eod_hour = market_hours['eod_liquidation_hour']
            eod_minute = market_hours['eod_liquidation_minute']

            positioned_stocks = self.bot.trading_manager.get_stocks_by_state(StockState.POSITIONED)

            if not positioned_stocks:
                self.logger.info(f"{eod_hour}:{eod_minute:02d} 시장가 매도: 보유 포지션 없음")
                return

            self.logger.info(
                f"{eod_hour}:{eod_minute:02d} 시장가 일괄매도 시작: {len(positioned_stocks)}종목"
            )

            # 모든 보유 종목 시장가 매도
            for trading_stock in positioned_stocks:
                try:
                    if not trading_stock.position or trading_stock.position.quantity <= 0:
                        continue

                    stock_code = trading_stock.stock_code
                    stock_name = trading_stock.stock_name
                    quantity = int(trading_stock.position.quantity)

                    # 시장가 매도를 위해 현재가 조회 (시장가는 가격 0으로 주문)
                    current_price = 0.0  # 시장가는 0원으로 주문

                    # 상태를 매도 대기로 변경 후 시장가 매도 주문
                    moved = self.bot.trading_manager.move_to_sell_candidate(
                        stock_code, f"{eod_hour}:{eod_minute:02d} 시장가 일괄매도"
                    )
                    if moved:
                        await self.bot.trading_manager.execute_sell_order(
                            stock_code, quantity, current_price,
                            f"{eod_hour}:{eod_minute:02d} 시장가 일괄매도", market=True
                        )
                        self.logger.info(
                            f"{eod_hour}:{eod_minute:02d} 시장가 매도: "
                            f"{stock_code}({stock_name}) {quantity}주 시장가 주문"
                        )

                except Exception as se:
                    self.logger.error(
                        f"{eod_hour}:{eod_minute:02d} 시장가 매도 개별 처리 오류({trading_stock.stock_code}): {se}"
                    )

            self.logger.info(f"{eod_hour}:{eod_minute:02d} 시장가 일괄매도 요청 완료")

        except Exception as e:
            self.logger.error(f"장마감 시장가 매도 오류: {e}")

    def get_last_eod_liquidation_date(self):
        """마지막 장마감 청산 날짜 반환"""
        return self._last_eod_liquidation_date

    def set_last_eod_liquidation_date(self, date):
        """마지막 장마감 청산 날짜 설정"""
        self._last_eod_liquidation_date = date
