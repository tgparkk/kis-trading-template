"""
매매 분석 모듈
매수/매도 판단 분석 로직을 담당합니다.
"""
from typing import TYPE_CHECKING, Optional

from core.models import StockState
from config.constants import CANDIDATE_MIN_DAILY_DATA

from utils.logger import setup_logger
from utils.rate_limited_logger import RateLimitedLogger

if TYPE_CHECKING:
    from main import DayTradingBot


class TradingAnalyzer:
    """매매 판단 분석 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self.bot = bot
        self.logger = RateLimitedLogger(setup_logger(__name__))

        # FundManager를 DecisionEngine에 연결 (main.py 수정 없이)
        if hasattr(bot, 'fund_manager') and hasattr(bot, 'decision_engine'):
            bot.decision_engine.set_fund_manager(bot.fund_manager)

    async def analyze_buy_decision(self, trading_stock, available_funds: float = None,
                                   signal=None) -> None:
        """매수 판단 분석 (일봉 데이터 사용)

        Args:
            trading_stock: 거래 대상 주식
            available_funds: 사용 가능한 자금 (미리 계산된 값)
            signal: Signal 객체 (TradingContext.buy()에서 전달, target_price/stop_loss 활용)
        """
        try:
            stock_code = trading_stock.stock_code
            stock_name = trading_stock.stock_name

            self.logger.debug(f"매수 판단 시작: {stock_code}({stock_name})")

            # 추가 안전 검증: 현재 보유 중인 종목인지 다시 한번 확인
            positioned_stocks = self.bot.trading_manager.get_stocks_by_state(StockState.POSITIONED)
            if any(pos_stock.stock_code == stock_code for pos_stock in positioned_stocks):
                self.logger.info(f"보유 중인 종목 매수 신호 무시: {stock_code}({stock_name})")
                return

            # 25분 매수 쿨다운 확인
            if trading_stock.is_buy_cooldown_active():
                remaining_minutes = trading_stock.get_remaining_cooldown_minutes()
                self.logger.debug(f"{stock_code}: 매수 쿨다운 활성화 (남은 시간: {remaining_minutes}분)")
                return

            # 일봉 데이터 가져오기 (daily_prices 테이블에서, PostgreSQL)
            daily_data = self.bot.db_manager.price_repo.get_daily_prices(stock_code, days=140)
            if daily_data is None or daily_data.empty:
                self.logger.warning(f"{stock_code} 일봉 데이터 없음 (daily_prices 테이블) - 매수 판단 불가")
                return

            if len(daily_data) < CANDIDATE_MIN_DAILY_DATA:
                self.logger.debug(f"{stock_code} 일봉 데이터 부족: {len(daily_data)}개 (최소 {CANDIDATE_MIN_DAILY_DATA}개 필요)")
                return

            self.logger.debug(f"{stock_code} 일봉 데이터 조회 완료: {len(daily_data)}건")

            # 매매 판단 엔진으로 매수 신호 확인 (일봉 데이터 사용)
            buy_signal, buy_reason, buy_info = await self.bot.decision_engine.analyze_buy_decision(
                trading_stock, daily_data
            )

            self.logger.debug(f"{stock_code} 매수 판단 결과: signal={buy_signal}, reason='{buy_reason}'")
            if buy_signal and buy_info:
                self.logger.debug(
                    f"{stock_code} 매수 정보: 가격={buy_info['buy_price']:,.0f}원, "
                    f"수량={buy_info['quantity']:,}주, 투자금={buy_info['max_buy_amount']:,.0f}원"
                )

            if buy_signal and buy_info.get('quantity', 0) > 0:
                self.logger.info(f"{stock_code}({stock_name}) 매수 신호 발생: {buy_reason}")

                # 매수 전 자금 확인 (전달받은 available_funds 활용)
                if available_funds is not None:
                    # 전달받은 가용 자금 기준으로 종목당 최대 투자 금액 계산 (10%)
                    fund_status = self.bot.fund_manager.get_status()
                    max_buy_amount = min(available_funds, fund_status['total_funds'] * 0.1)
                else:
                    # FundManager 기반 최대 매수 가능 금액 계산
                    max_buy_amount = self.bot.fund_manager.get_max_buy_amount(stock_code)

                required_amount = buy_info['buy_price'] * buy_info['quantity']

                if required_amount > max_buy_amount:
                    self.logger.warning(
                        f"{stock_code} 자금 부족: 필요={required_amount:,.0f}원, 가용={max_buy_amount:,.0f}원"
                    )
                    # 가용 자금에 맞게 수량 조정
                    if max_buy_amount > 0:
                        adjusted_quantity = int(max_buy_amount / buy_info['buy_price'])
                        if adjusted_quantity > 0:
                            buy_info['quantity'] = adjusted_quantity
                            required_amount = buy_info['buy_price'] * adjusted_quantity
                            self.logger.info(
                                f"{stock_code} 수량 조정: {adjusted_quantity}주 "
                                f"(투자금: {required_amount:,.0f}원)"
                            )
                        else:
                            self.logger.warning(f"{stock_code} 매수 포기: 최소 1주도 매수 불가")
                            return
                    else:
                        self.logger.warning(f"{stock_code} 매수 포기: 가용 자금 없음")
                        return

                # FundManager 자금 예약 (유니크 ID 사용)
                from utils.korean_time import now_kst as _now_kst
                _reserve_id = f"{stock_code}_{_now_kst().strftime('%H%M%S%f')}"
                reserve_ok = self.bot.fund_manager.reserve_funds(_reserve_id, required_amount)
                if not reserve_ok:
                    self.logger.warning(f"{stock_code} 자금 예약 실패 - 매수 스킵")
                    return

                # 매수 전 종목 상태 확인
                current_stock = self.bot.trading_manager.get_trading_stock(stock_code)
                if current_stock:
                    self.logger.debug(f"매수 전 상태 확인: {stock_code} 현재상태={current_stock.state.value}")

                # 가상/실전 매매 분기
                # Signal 우선순위: 엔진 재생성 신호 > 호출자 전달 신호
                effective_signal = buy_info.get('signal') or signal
                if self.bot.decision_engine.is_virtual_mode:
                    # 가상 매수
                    try:
                        await self.bot.decision_engine.execute_virtual_buy(
                            trading_stock, None, buy_reason,
                            buy_price=buy_info['buy_price'],
                            quantity=buy_info['quantity'],
                            signal=effective_signal
                        )
                        # 자금 확정 (가상매매는 즉시 체결로 간주)
                        self.bot.fund_manager.confirm_order(_reserve_id, required_amount)
                        # 보유 종목 추가 (FundManager current_position_codes 추적)
                        self.bot.fund_manager.add_position(stock_code)
                        # 매수 쿨다운 설정
                        trading_stock.set_buy_time(_now_kst())
                        # 상태를 POSITIONED로 반영하여 이후 매도 판단 루프에 포함
                        try:
                            self.bot.trading_manager._change_stock_state(
                                stock_code, StockState.POSITIONED, "가상 매수 체결"
                            )
                        except Exception as e:
                            self.logger.debug(f"가상 매수 상태 변경 실패: {stock_code} - {e}")
                        self.logger.info(f"가상 매수 완료 처리: {stock_code}({stock_name}) - {buy_reason}")
                    except Exception as e:
                        # 매수 실패 시 자금 예약 취소
                        self.bot.fund_manager.cancel_order(_reserve_id)
                        self.logger.error(f"가상 매수 처리 오류: {e}")
                else:
                    # 실전 매수
                    try:
                        success = await self.bot.decision_engine.execute_real_buy(
                            trading_stock, buy_reason,
                            buy_price=buy_info['buy_price'],
                            quantity=buy_info['quantity']
                        )
                        if success:
                            # 자금 확정은 체결 확인 시 OrderMonitor에서 처리 (이중 확정 방지)
                            self.logger.info(f"실전 매수 주문 접수: {stock_code}({stock_name}) - {buy_reason}")
                        else:
                            # 매수 실패 시 자금 예약 취소
                            self.bot.fund_manager.cancel_order(_reserve_id)
                            self.logger.warning(f"실전 매수 실패: {stock_code}({stock_name})")
                    except Exception as e:
                        self.bot.fund_manager.cancel_order(_reserve_id)
                        self.logger.error(f"실전 매수 처리 오류: {e}")

        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매수 판단 오류: {e}")
            import traceback
            self.logger.error(f"상세 오류 정보: {traceback.format_exc()}")

    async def analyze_sell_decision(self, trading_stock) -> None:
        """매도 판단 분석 (1분봉 고가/저가 기준 익절/손절 + 3분봉 기술적 분석)"""
        try:
            stock_code = trading_stock.stock_code
            stock_name = trading_stock.stock_name

            # 1분봉 데이터 조회 (백테스팅과 동일한 방식)
            combined_data = self.bot.intraday_manager.get_combined_chart_data(stock_code)

            # 매매 판단 엔진으로 매도 신호 확인 (1분봉 데이터 전달)
            sell_signal, sell_reason = await self.bot.decision_engine.analyze_sell_decision(
                trading_stock, combined_data
            )

            if sell_signal:
                # 매도 전 종목 상태 확인
                self.logger.debug(f"매도 전 상태 확인: {stock_code} 현재상태={trading_stock.state.value}")
                if trading_stock.position:
                    self.logger.debug(
                        f"포지션 정보: {trading_stock.position.quantity}주 "
                        f"@{trading_stock.position.avg_price:,.0f}원"
                    )

                # 가상/실전 매매 분기
                if self.bot.decision_engine.is_virtual_mode:
                    # 가상 매도
                    try:
                        # 매도가를 먼저 결정 (execute_virtual_sell과 PnL 계산에 동일 가격 사용)
                        sell_price = None
                        if trading_stock.position:
                            sell_price = trading_stock.position.avg_price  # fallback: 원가
                            try:
                                price_info = self.bot.intraday_manager.get_cached_current_price(stock_code)
                                if price_info and price_info.get('current_price', 0) > 0:
                                    sell_price = float(price_info['current_price'])
                            except Exception:
                                pass

                        # move_to_sell_candidate는 가상매도에서는 직접 호출
                        self.bot.trading_manager.move_to_sell_candidate(stock_code, sell_reason)
                        # 확정된 매도가를 execute_virtual_sell에 전달
                        sell_ok = await self.bot.decision_engine.execute_virtual_sell(
                            trading_stock, sell_price, sell_reason
                        )
                        # fund_manager 업데이트는 execute_virtual_sell() 내부에서 일원화 처리
                        if not sell_ok:
                            trading_stock.is_selling = False
                            # 매도 실패 시 POSITIONED로 복원
                            self.bot.trading_manager._change_stock_state(
                                stock_code, StockState.POSITIONED, "가상 매도 실패 복원"
                            )
                            self.logger.warning(f"{stock_code} 가상 매도 실패 - POSITIONED로 복원")
                        self.logger.info(f"가상 매도 완료 처리: {stock_code}({stock_name}) - {sell_reason}")
                    except Exception as e:
                        self.logger.error(f"가상 매도 처리 오류: {e}")
                else:
                    # 실전 매도 (execute_real_sell 내부에서 move_to_sell_candidate 호출)
                    try:
                        sell_ok = await self.bot.decision_engine.execute_real_sell(
                            trading_stock, sell_reason
                        )
                        if sell_ok:
                            self.logger.info(f"실전 매도 주문 접수: {stock_code}({stock_name}) - {sell_reason}")
                        else:
                            self.logger.warning(f"실전 매도 실패: {stock_code}({stock_name})")
                    except Exception as e:
                        self.logger.error(f"실전 매도 처리 오류: {e}")
        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매도 판단 오류: {e}")
