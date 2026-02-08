"""상태 복원 모듈

시스템 재시작 시 DB에서 오늘의 후보 종목 및 보유 종목을 복원합니다.
"""
from typing import Dict, List, Optional

from utils.logger import setup_logger
from utils.korean_time import now_kst
from core.models import StockState
from config.constants import DEFAULT_TARGET_PROFIT_RATE, DEFAULT_STOP_LOSS_RATE
from db.connection import DatabaseConnection

logger = setup_logger(__name__)


class StateRestorer:
    """상태 복원 헬퍼 (간소화 버전)

    기능:
    1. 오늘 날짜의 후보 종목을 DB에서 복원
    2. 보유 종목 복원 (가상매매: DB, 실전매매: 실제 계좌)
    3. 실전매매 시 계좌-DB 불일치 감지
    """

    def __init__(
        self,
        trading_manager,
        db_manager,
        telegram_integration,
        config,
        get_previous_close_callback,
        broker=None,
    ):
        """
        Args:
            trading_manager: TradingStockManager 인스턴스
            db_manager: DatabaseManager 인스턴스
            telegram_integration: 텔레그램 통합
            config: 거래 설정
            get_previous_close_callback: 전날 종가 조회 콜백 함수
            broker: KISBroker (실전 모드에서 계좌 조회용)
        """
        self.trading_manager = trading_manager
        self.db_manager = db_manager
        self.telegram = telegram_integration
        self.config = config
        self.get_previous_close = get_previous_close_callback
        self.broker = broker

        # 가상/실전 모드 플래그
        self.is_paper_trading = getattr(config, 'paper_trading', True) if config else True

    async def restore_todays_candidates(self):
        """DB에서 후보 종목 및 보유 종목 복원"""
        try:
            today = now_kst().strftime('%Y-%m-%d')

            # 1. 오늘 날짜의 후보 종목 복원
            await self._restore_candidates(today)

            # 2. 보유 종목 복원 (가상/실전 모드에 따라 다른 소스 사용)
            if self.is_paper_trading:
                await self._restore_holdings_from_db()
            else:
                await self._restore_holdings_from_real_account()

        except Exception as e:
            logger.error(f"❌ 종목 복원 실패: {e}")

    async def _restore_candidates(self, today: str):
        """DB에서 오늘 후보 종목 복원"""
        try:
            # TimescaleDB에서 오늘 후보 종목 직접 조회
            rows = []
            try:
                with DatabaseConnection.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT DISTINCT stock_code, stock_name, score, reasons
                        FROM candidate_stocks
                        WHERE DATE(selection_date) = %s
                        ORDER BY score DESC
                    ''', (today,))
                    rows = cursor.fetchall()
            except Exception as db_err:
                logger.error(f"❌ 후보 종목 DB 조회 실패: {db_err}")
                return

            if not rows:
                logger.info(f"📊 오늘({today}) 후보 종목 없음")
                return

            logger.info(f"🔄 오늘({today}) 후보 종목 {len(rows)}개 복원 시작")
            restored_count = 0

            for row in rows:
                stock_code = row[0]
                stock_name = row[1] or f"Stock_{stock_code}"
                score = row[2] or 0.0
                reason = row[3] or "DB 복원"

                prev_close = self.get_previous_close(stock_code)

                success = await self.trading_manager.add_selected_stock(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    selection_reason=f"DB복원: {reason} (점수: {score})",
                    prev_close=prev_close,
                )

                if success:
                    restored_count += 1

            logger.info(f"✅ 오늘 후보 종목 {restored_count}/{len(rows)}개 복원 완료")

        except Exception as e:
            logger.error(f"❌ 후보 종목 복원 실패: {e}")

    async def _restore_holdings_from_db(self):
        """가상매매 모드: DB에서 보유 종목 복원"""
        try:
            holdings = self.db_manager.get_virtual_open_positions()
            if holdings.empty:
                logger.info("📊 [가상매매] 보유 종목 없음")
                return

            logger.info(f"🔄 [가상매매] 보유 종목 {len(holdings)}개 복원 시작")
            holding_restored = 0

            for _, holding in holdings.iterrows():
                stock_code = holding['stock_code']
                stock_name = holding['stock_name']
                quantity = int(holding['quantity'])
                buy_price = float(holding['buy_price'])
                target_profit_rate = holding.get('target_profit_rate', DEFAULT_TARGET_PROFIT_RATE)
                stop_loss_rate = holding.get('stop_loss_rate', DEFAULT_STOP_LOSS_RATE)

                prev_close = self.get_previous_close(stock_code)

                success = await self.trading_manager.add_selected_stock(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    selection_reason=f"보유 종목 복원 ({quantity}주 @{buy_price:,.0f}원)",
                    prev_close=prev_close,
                )

                if success:
                    trading_stock = self.trading_manager.get_trading_stock(stock_code)
                    if trading_stock:
                        trading_stock.set_position(quantity, buy_price)
                        trading_stock.target_profit_rate = target_profit_rate
                        trading_stock.stop_loss_rate = stop_loss_rate

                        self.trading_manager._change_stock_state(
                            stock_code,
                            StockState.POSITIONED,
                            f"DB 복원: {quantity}주 @{buy_price:,.0f}원 "
                            f"(익절:{target_profit_rate*100:.1f}% 손절:{stop_loss_rate*100:.1f}%)",
                        )
                        holding_restored += 1
                        logger.debug(
                            f"📊 {stock_code} 포지션 복원: {quantity}주 @{buy_price:,.0f}원, "
                            f"익절가 {buy_price*(1+target_profit_rate):,.0f}원, "
                            f"손절가 {buy_price*(1-stop_loss_rate):,.0f}원"
                        )

            logger.info(f"✅ [가상매매] 보유 종목 {holding_restored}/{len(holdings)}개 복원 완료")

        except Exception as e:
            logger.error(f"❌ [가상매매] 보유 종목 복원 실패: {e}")

    async def _restore_holdings_from_real_account(self):
        """실전매매 모드: 실제 계좌에서 보유 종목 조회 → DB 동기화 → 메모리 복원"""
        try:
            if not self.broker:
                logger.error("❌ [실전매매] broker가 없어 계좌 조회 불가 - DB 복원으로 대체")
                await self._restore_holdings_from_db()
                return

            logger.info("🔄 [실전매매] 실제 계좌에서 보유 종목 조회 중...")

            # 1. 실제 계좌 보유 종목 조회
            account_info = self.broker.get_account_balance()

            if not account_info:
                logger.error("❌ [실전매매] 계좌 조회 실패 - DB 복원으로 대체")
                await self._restore_holdings_from_db()
                return

            real_holdings = account_info.get('positions', []) if isinstance(account_info, dict) else (
                account_info.positions if hasattr(account_info, 'positions') and account_info.positions else []
            )
            logger.info(f"📊 [실전매매] 실제 계좌 보유 종목: {len(real_holdings)}개")

            # 2. DB 보유 종목 조회
            db_holdings = self.db_manager.get_virtual_open_positions()
            db_holdings_dict = {}
            if not db_holdings.empty:
                for _, row in db_holdings.iterrows():
                    db_holdings_dict[row['stock_code']] = {
                        'stock_name': row['stock_name'],
                        'quantity': int(row['quantity']),
                        'buy_price': float(row['buy_price']),
                        'target_profit_rate': row.get('target_profit_rate', DEFAULT_TARGET_PROFIT_RATE),
                        'stop_loss_rate': row.get('stop_loss_rate', DEFAULT_STOP_LOSS_RATE),
                    }

            logger.info(f"📊 [실전매매] DB 보유 종목: {len(db_holdings_dict)}개")

            # 3. 불일치 감지 및 로깅
            await self._detect_holdings_mismatch(real_holdings, db_holdings_dict)

            # 4. 실제 계좌 기준으로 메모리에 복원
            holding_restored = 0

            for real_stock in real_holdings:
                stock_code = real_stock.get('stock_code', '')
                stock_name = real_stock.get('stock_name', f'Stock_{stock_code}')
                quantity = int(real_stock.get('quantity', 0))
                avg_price = float(real_stock.get('avg_price', 0))

                if quantity <= 0:
                    continue

                # DB에 해당 종목 정보가 있으면 익절/손절률 사용
                if stock_code in db_holdings_dict:
                    db_info = db_holdings_dict[stock_code]
                    target_profit_rate = db_info.get('target_profit_rate', DEFAULT_TARGET_PROFIT_RATE)
                    stop_loss_rate = db_info.get('stop_loss_rate', DEFAULT_STOP_LOSS_RATE)
                else:
                    target_profit_rate = DEFAULT_TARGET_PROFIT_RATE
                    stop_loss_rate = DEFAULT_STOP_LOSS_RATE
                    logger.warning(f"⚠️ [실전매매] {stock_code} DB에 없음 - 기본 익절/손절률 적용")

                prev_close = self.get_previous_close(stock_code)

                success = await self.trading_manager.add_selected_stock(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    selection_reason=f"[실전] 보유 종목 복원 ({quantity}주 @{avg_price:,.0f}원)",
                    prev_close=prev_close,
                )

                if success:
                    trading_stock = self.trading_manager.get_trading_stock(stock_code)
                    if trading_stock:
                        trading_stock.set_position(quantity, avg_price)
                        trading_stock.target_profit_rate = target_profit_rate
                        trading_stock.stop_loss_rate = stop_loss_rate

                        self.trading_manager._change_stock_state(
                            stock_code,
                            StockState.POSITIONED,
                            f"[실전] 계좌 복원: {quantity}주 @{avg_price:,.0f}원 "
                            f"(익절:{target_profit_rate*100:.1f}% 손절:{stop_loss_rate*100:.1f}%)",
                        )
                        holding_restored += 1
                        logger.info(
                            f"📊 [실전] {stock_code}({stock_name}) 복원: {quantity}주 @{avg_price:,.0f}원, "
                            f"익절가 {avg_price*(1+target_profit_rate):,.0f}원, "
                            f"손절가 {avg_price*(1-stop_loss_rate):,.0f}원"
                        )

            if real_holdings:
                logger.info(f"✅ [실전매매] 보유 종목 {holding_restored}/{len(real_holdings)}개 복원 완료")
            else:
                logger.info("📊 [실전매매] 보유 종목 없음")

        except Exception as e:
            logger.error(f"❌ [실전매매] 보유 종목 복원 실패: {e}")
            logger.warning("⚠️ DB 복원으로 대체합니다...")
            await self._restore_holdings_from_db()

    async def _detect_holdings_mismatch(self, real_holdings: List[Dict], db_holdings_dict: Dict[str, Dict]):
        """실제 계좌와 DB 간 보유 종목 불일치 감지"""
        try:
            mismatches = []
            real_codes = set()

            for real_stock in real_holdings:
                stock_code = real_stock.get('stock_code', '')
                real_qty = int(real_stock.get('quantity', 0))
                stock_name = real_stock.get('stock_name', stock_code)

                if real_qty <= 0:
                    continue

                real_codes.add(stock_code)

                if stock_code not in db_holdings_dict:
                    mismatches.append(
                        f"⚠️ {stock_code}({stock_name}): 실제 계좌에만 존재 ({real_qty}주) - 외부 매수 또는 DB 누락"
                    )
                else:
                    db_qty = db_holdings_dict[stock_code]['quantity']
                    if real_qty != db_qty:
                        mismatches.append(
                            f"⚠️ {stock_code}({stock_name}): 수량 불일치 (실제: {real_qty}주, DB: {db_qty}주)"
                        )

            for stock_code, db_info in db_holdings_dict.items():
                if stock_code not in real_codes:
                    mismatches.append(
                        f"⚠️ {stock_code}({db_info['stock_name']}): DB에만 존재 ({db_info['quantity']}주) - 외부 매도 또는 미체결"
                    )

            if mismatches:
                logger.warning(f"🚨 [실전매매] 계좌-DB 불일치 감지: {len(mismatches)}건")
                for m in mismatches:
                    logger.warning(m)

                if self.telegram:
                    alert_msg = f"🚨 계좌-DB 불일치 감지: {len(mismatches)}건\n\n"
                    for m in mismatches[:5]:
                        alert_msg += f"• {m}\n"
                    if len(mismatches) > 5:
                        alert_msg += f"... 외 {len(mismatches)-5}건"
                    await self.telegram.send_notification(alert_msg)
            else:
                logger.info("✅ [실전매매] 계좌-DB 보유 종목 일치 확인")

        except Exception as e:
            logger.error(f"❌ 불일치 감지 오류: {e}")
