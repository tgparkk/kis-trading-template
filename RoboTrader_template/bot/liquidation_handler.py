"""
청산 핸들러 모듈
장 마감 시 포지션 청산 로직을 담당합니다.

EOD 청산 실패 복구:
- 청산 주문 실패 시 최대 3회 재시도
- 재시도 간 10초 대기
- 최종 실패 시 텔레그램 알림
"""
import asyncio
from typing import TYPE_CHECKING, Set

from core.models import StockState
from utils.logger import setup_logger
from utils.korean_time import now_kst
from utils.price_utils import round_to_tick
from config.market_hours import MarketHours
from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE

if TYPE_CHECKING:
    from main import DayTradingBot

# EOD 청산 재시도 설정
EOD_LIQUIDATION_MAX_RETRIES = 3
EOD_LIQUIDATION_RETRY_DELAY = 10  # 초


class LiquidationHandler:
    """장 마감 청산 담당 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self.bot = bot
        self.logger = setup_logger(__name__)
        self._last_eod_liquidation_date = None
        self._eod_failed_stocks: Set[str] = set()  # 청산 실패 종목 추적
        self._eod_retry_count: int = 0

    async def liquidate_all_positions_end_of_day(self) -> None:
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

                    # 가상/실전 모드 분기
                    is_virtual = getattr(self.bot.decision_engine, 'is_virtual_mode', False)
                    if is_virtual:
                        # 가상매매 - execute_virtual_sell 사용
                        result = await self.bot.decision_engine.execute_virtual_sell(
                            trading_stock, sell_price, "장마감 일괄청산"
                        )
                        if result:
                            buy_price = trading_stock.position.avg_price if trading_stock.position else 0
                            invested = float(buy_price) * int(quantity)
                            _sell_amount = float(sell_price) * int(quantity) if sell_price else invested
                            _buy_comm = invested * COMMISSION_RATE
                            _sell_comm = _sell_amount * COMMISSION_RATE
                            _sell_tax = _sell_amount * SECURITIES_TAX_RATE
                            _pnl = _sell_amount - invested - _buy_comm - _sell_comm - _sell_tax
                            self.bot.fund_manager.release_investment(invested, stock_code=stock_code)
                            if _pnl != 0:
                                self.bot.fund_manager.adjust_pnl(_pnl)
                            self.bot.fund_manager.remove_position(stock_code)
                            self.logger.info(
                                f"장마감 가상청산 완료: {stock_code} {quantity}주 @{sell_price:,.0f}원"
                            )
                        else:
                            self.logger.warning(f"장마감 가상청산 실패: {stock_code}")
                    else:
                        # 실매매 - 기존 실매도 로직
                        moved = self.bot.trading_manager.move_to_sell_candidate(stock_code, "장마감 일괄청산")
                        if moved:
                            await self.bot.trading_manager.execute_sell_order(
                                stock_code, quantity, sell_price, "장마감 일괄청산", market=True,
                                force=True
                            )
                            self.logger.info(
                                f"장마감 청산 주문: {stock_code} {quantity}주 시장가 @{sell_price:,.0f}원"
                            )
                except Exception as se:
                    self.logger.error(f"장마감 청산 개별 처리 오류({trading_stock.stock_code}): {se}")

            self.logger.info("장마감 일괄청산 요청 완료")

        except Exception as e:
            self.logger.error(f"장마감 일괄청산 오류: {e}")

    async def execute_end_of_day_liquidation(self) -> None:
        """장마감 시간 모든 보유 종목 시장가 일괄매도 (동적 시간 적용, 실패 시 재시도)"""
        try:
            current_time = now_kst()
            market_hours = MarketHours.get_market_hours('KRX', current_time)
            eod_hour = market_hours['eod_liquidation_hour']
            eod_minute = market_hours['eod_liquidation_minute']
            time_label = f"{eod_hour}:{eod_minute:02d}"

            positioned_stocks = self.bot.trading_manager.get_stocks_by_state(StockState.POSITIONED)

            if not positioned_stocks:
                self.logger.info(f"{time_label} 시장가 매도: 보유 포지션 없음")
                self._eod_failed_stocks.clear()
                return

            self.logger.info(
                f"{time_label} 시장가 일괄매도 시작: {len(positioned_stocks)}종목"
            )

            failed_stocks = []

            for trading_stock in positioned_stocks:
                try:
                    if not trading_stock.position or trading_stock.position.quantity <= 0:
                        continue

                    stock_code = trading_stock.stock_code
                    stock_name = trading_stock.stock_name
                    quantity = int(trading_stock.position.quantity)
                    current_price = 0.0  # 시장가

                    # 가상/실전 모드 분기
                    is_virtual = getattr(self.bot.decision_engine, 'is_virtual_mode', False)
                    if is_virtual:
                        # 가상매매 - execute_virtual_sell 사용
                        eod_sell_price = 0.0
                        combined_data = self.bot.intraday_manager.get_combined_chart_data(stock_code)
                        if combined_data is not None and len(combined_data) > 0:
                            eod_sell_price = float(combined_data['close'].iloc[-1])
                        else:
                            price_obj = self.bot.broker.get_current_price(stock_code)
                            if price_obj:
                                eod_sell_price = float(price_obj.current_price)

                        result = await self.bot.decision_engine.execute_virtual_sell(
                            trading_stock, eod_sell_price,
                            f"{time_label} 시장가 일괄매도"
                        )
                        if result:
                            buy_price = trading_stock.position.avg_price if trading_stock.position else 0
                            invested = float(buy_price) * int(quantity)
                            _sell_amount = float(eod_sell_price) * int(quantity) if eod_sell_price else invested
                            _buy_comm = invested * COMMISSION_RATE
                            _sell_comm = _sell_amount * COMMISSION_RATE
                            _sell_tax = _sell_amount * SECURITIES_TAX_RATE
                            _pnl = _sell_amount - invested - _buy_comm - _sell_comm - _sell_tax
                            self.bot.fund_manager.release_investment(invested, stock_code=stock_code)
                            if _pnl != 0:
                                self.bot.fund_manager.adjust_pnl(_pnl)
                            self.bot.fund_manager.remove_position(stock_code)
                            self.logger.info(
                                f"{time_label} 가상매도 완료: "
                                f"{stock_code}({stock_name}) {quantity}주"
                            )
                        else:
                            self.logger.warning(
                                f"{stock_code} 가상매도 실패 - 재시도 대상에 추가"
                            )
                            failed_stocks.append(stock_code)
                    else:
                        # 실매매 - 기존 실매도 로직
                        moved = self.bot.trading_manager.move_to_sell_candidate(
                            stock_code, f"{time_label} 시장가 일괄매도"
                        )
                        if moved:
                            await self.bot.trading_manager.execute_sell_order(
                                stock_code, quantity, current_price,
                                f"{time_label} 시장가 일괄매도", market=True,
                                force=True
                            )
                            self.logger.info(
                                f"{time_label} 시장가 매도: "
                                f"{stock_code}({stock_name}) {quantity}주 시장가 주문"
                            )
                        else:
                            self.logger.warning(
                                f"{stock_code} 매도 후보 전환 실패 - 재시도 대상에 추가"
                            )
                            failed_stocks.append(stock_code)

                except Exception as se:
                    self.logger.error(
                        f"{time_label} 시장가 매도 개별 처리 오류({trading_stock.stock_code}): {se}"
                    )
                    failed_stocks.append(trading_stock.stock_code)

            self._eod_failed_stocks = set(failed_stocks)

            if failed_stocks:
                self.logger.warning(f"{time_label} 청산 실패 종목: {failed_stocks}")
            else:
                self.logger.info(f"{time_label} 시장가 일괄매도 요청 완료")

        except Exception as e:
            self.logger.error(f"장마감 시장가 매도 오류: {e}")

    async def retry_failed_eod_liquidation(self) -> None:
        """EOD 청산 실패 종목 재시도

        Returns:
            True if all retries succeeded or no failures, False if still failing
        """
        if not self._eod_failed_stocks:
            return True

        self._eod_retry_count += 1
        if self._eod_retry_count > EOD_LIQUIDATION_MAX_RETRIES:
            self.logger.error(
                f"EOD 청산 재시도 한도 초과 ({EOD_LIQUIDATION_MAX_RETRIES}회): "
                f"실패 종목 {list(self._eod_failed_stocks)}"
            )
            # 텔레그램 긴급 알림
            if hasattr(self.bot, 'telegram') and self.bot.telegram:
                try:
                    await self.bot.telegram.notify_system_status(
                        f"🚨 EOD 청산 최종 실패: {list(self._eod_failed_stocks)}"
                    )
                except Exception:
                    pass
            return False

        self.logger.info(
            f"EOD 청산 재시도 ({self._eod_retry_count}/{EOD_LIQUIDATION_MAX_RETRIES}): "
            f"{list(self._eod_failed_stocks)}"
        )

        still_failed = []
        for stock_code in list(self._eod_failed_stocks):
            try:
                positioned_stocks = self.bot.trading_manager.get_stocks_by_state(StockState.POSITIONED)
                target = next((s for s in positioned_stocks if s.stock_code == stock_code), None)
                if not target or not target.position or target.position.quantity <= 0:
                    continue  # 이미 청산됨

                quantity = int(target.position.quantity)
                # 가상/실전 모드 분기
                is_virtual = getattr(self.bot.decision_engine, 'is_virtual_mode', False)
                if is_virtual:
                    # 가상매매 - execute_virtual_sell 사용
                    retry_sell_price = 0.0
                    combined_data = self.bot.intraday_manager.get_combined_chart_data(stock_code)
                    if combined_data is not None and len(combined_data) > 0:
                        retry_sell_price = float(combined_data['close'].iloc[-1])
                    else:
                        price_obj = self.bot.broker.get_current_price(stock_code)
                        if price_obj:
                            retry_sell_price = float(price_obj.current_price)

                    result = await self.bot.decision_engine.execute_virtual_sell(
                        target, retry_sell_price,
                        f"EOD 청산 재시도 #{self._eod_retry_count}"
                    )
                    if result:
                        buy_price = target.position.avg_price if target.position else 0
                        invested = float(buy_price) * int(quantity)
                        _sell_amount = float(retry_sell_price) * int(quantity) if retry_sell_price else invested
                        _buy_comm = invested * COMMISSION_RATE
                        _sell_comm = _sell_amount * COMMISSION_RATE
                        _sell_tax = _sell_amount * SECURITIES_TAX_RATE
                        _pnl = _sell_amount - invested - _buy_comm - _sell_comm - _sell_tax
                        self.bot.fund_manager.release_investment(invested, stock_code=stock_code)
                        if _pnl != 0:
                            self.bot.fund_manager.adjust_pnl(_pnl)
                        self.bot.fund_manager.remove_position(stock_code)
                        self.logger.info(f"EOD 가상매도 재시도 성공: {stock_code} {quantity}주")
                    else:
                        self.logger.warning(
                            f"EOD 가상매도 재시도 실패: {stock_code} - 재시도 대상 유지"
                        )
                        still_failed.append(stock_code)
                else:
                    # 실매매 - 기존 실매도 로직
                    moved = self.bot.trading_manager.move_to_sell_candidate(
                        stock_code, f"EOD 청산 재시도 #{self._eod_retry_count}"
                    )
                    if moved:
                        await self.bot.trading_manager.execute_sell_order(
                            stock_code, quantity, 0.0,
                            f"EOD 청산 재시도 #{self._eod_retry_count}", market=True,
                            force=True
                        )
                        self.logger.info(f"EOD 재시도 성공: {stock_code} {quantity}주")
                    else:
                        self.logger.warning(
                            f"EOD 재시도 매도 후보 전환 실패: {stock_code} - 재시도 대상 유지"
                        )
                        still_failed.append(stock_code)
            except Exception as e:
                self.logger.error(f"EOD 재시도 실패 ({stock_code}): {e}")
                still_failed.append(stock_code)

        self._eod_failed_stocks = set(still_failed)
        return len(still_failed) == 0

    def has_failed_eod_stocks(self) -> bool:
        """EOD 청산 실패 종목 존재 여부"""
        return len(self._eod_failed_stocks) > 0

    def reset_eod_state(self) -> None:
        """EOD 상태 초기화 (일일 리셋)"""
        self._eod_failed_stocks.clear()
        self._eod_retry_count = 0

    def get_last_eod_liquidation_date(self) -> None:
        """마지막 장마감 청산 날짜 반환"""
        return self._last_eod_liquidation_date

    def set_last_eod_liquidation_date(self, date) -> None:
        """마지막 장마감 청산 날짜 설정"""
        self._last_eod_liquidation_date = date
