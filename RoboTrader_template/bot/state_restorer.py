"""상태 복원 모듈

시스템 재시작 시 DB에서 오늘의 후보 종목 및 보유 종목을 복원합니다.
"""
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.logger import setup_logger
from utils.korean_time import now_kst
from core.models import StockState
from config.constants import (
    DEFAULT_TARGET_PROFIT_RATE, DEFAULT_STOP_LOSS_RATE,
    STALE_POSITION_DAYS, STALE_DEFAULT_APPLY_DAYS,
    STALE_DEFAULT_TARGET_PROFIT, STALE_DEFAULT_STOP_LOSS,
)
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
        fund_manager=None,
        virtual_trading_manager=None,
    ) -> None:
        """
        Args:
            trading_manager: TradingStockManager 인스턴스
            db_manager: DatabaseManager 인스턴스
            telegram_integration: 텔레그램 통합
            config: 거래 설정
            get_previous_close_callback: 전날 종가 조회 콜백 함수
            broker: KISBroker (실전 모드에서 계좌 조회용)
            fund_manager: FundManager 인스턴스 (자금 동기화용)
            virtual_trading_manager: VirtualTradingManager 인스턴스 (가상 잔고 동기화용)
        """
        self.trading_manager = trading_manager
        self.db_manager = db_manager
        self.telegram = telegram_integration
        self.config = config
        self.get_previous_close = get_previous_close_callback
        self.broker = broker
        self.fund_manager = fund_manager
        self.virtual_trading_manager = virtual_trading_manager

        # 가상/실전 모드 플래그
        self.is_paper_trading = getattr(config, 'paper_trading', True) if config else True

    async def restore_todays_candidates(self) -> None:
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

    def _sync_fund_manager_for_position(self, stock_code: str, quantity: int, buy_price: float) -> float:
        """복원된 포지션에 대해 FundManager 자금을 동기화

        Args:
            stock_code: 종목코드
            quantity: 보유 수량
            buy_price: 매수 단가

        Returns:
            float: 동기화된 투자 금액
        """
        quantity = int(quantity)
        buy_price = float(buy_price)
        invested_amount = quantity * buy_price

        if not self.fund_manager:
            logger.warning(f"FundManager 미초기화 - {stock_code} 자금 동기화 스킵")
            return invested_amount

        try:
            with self.fund_manager._lock:
                self.fund_manager.invested_funds += invested_amount
                self.fund_manager.available_funds -= invested_amount

                # 가용자금이 음수가 되면 0으로 클램프
                if self.fund_manager.available_funds < 0:
                    logger.warning(
                        f"가용자금 음수 보정: {self.fund_manager.available_funds:,.0f}원 -> 0원 "
                        f"(총투자: {self.fund_manager.invested_funds:,.0f}원 > "
                        f"총자금: {self.fund_manager.total_funds:,.0f}원)"
                    )
                    self.fund_manager.available_funds = 0

            # 보유 종목 등록 (add_position은 내부에서 자체 lock 사용)
            self.fund_manager.add_position(stock_code)

        except Exception as e:
            logger.error(f"FundManager 동기화 오류 ({stock_code}): {e}")

        return invested_amount

    def _sync_virtual_balance_for_position(self, quantity: int, buy_price: float) -> None:
        """복원된 포지션에 대해 VirtualTradingManager 가상 잔고를 동기화

        Args:
            quantity: 보유 수량
            buy_price: 매수 단가
        """
        if not self.virtual_trading_manager:
            return

        try:
            quantity = int(quantity)
            buy_price = float(buy_price)
            invested_amount = quantity * buy_price
            self.virtual_trading_manager.update_virtual_balance(invested_amount, "매수")
        except Exception as e:
            logger.error(f"VirtualTradingManager 잔고 동기화 오류: {e}")

    def _apply_stale_position_check(
        self, trading_stock, buy_time, target_profit_rate: float, stop_loss_rate: float
    ) -> tuple:
        """복원된 포지션의 보유 기간을 계산하고 장기보유 여부를 판정

        Args:
            trading_stock: TradingStock 인스턴스
            buy_time: 매수 시각 (datetime 또는 timestamp)
            target_profit_rate: 현재 적용된 익절률
            stop_loss_rate: 현재 적용된 손절률

        Returns:
            tuple: (target_profit_rate, stop_loss_rate) - 필요 시 기본값이 적용된 값
        """
        try:
            today = now_kst()

            # buy_time을 datetime으로 변환
            if isinstance(buy_time, (int, float)):
                buy_date = datetime.fromtimestamp(buy_time, tz=timezone.utc)
            elif isinstance(buy_time, datetime):
                buy_date = buy_time
            else:
                # 변환 불가 시 스킵
                return target_profit_rate, stop_loss_rate

            days_held = (today - buy_date).days if buy_date.tzinfo else (today.replace(tzinfo=None) - buy_date).days
            trading_stock.days_held = max(0, days_held)

            stock_code = trading_stock.stock_code
            stock_name = trading_stock.stock_name

            # 30일 이상 보유: 장기보유 경고 + is_stale 마킹
            if days_held >= STALE_POSITION_DAYS:
                trading_stock.is_stale = True
                logger.warning(
                    f"⚠️ {stock_code}({stock_name}) 장기 보유 {days_held}일 - 청산 검토 필요"
                )

            # 7일 이상 보유 + 익절/손절 미설정: 방어적 기본값 적용
            if days_held >= STALE_DEFAULT_APPLY_DAYS:
                # 익절/손절이 DEFAULT_TARGET_PROFIT_RATE/DEFAULT_STOP_LOSS_RATE인 경우는
                # DB에 NULL이어서 기본값이 적용된 것이므로, 원래 NULL이었던 것을 체크
                # 여기서는 원래 값이 NaN/None이어서 기본값으로 대체된 경우를 처리
                # (이미 _restore_holdings_from_db에서 기본값 적용됨)
                # 별도로 stale 전용 기본값을 더 타이트하게 적용
                if target_profit_rate == DEFAULT_TARGET_PROFIT_RATE and stop_loss_rate == DEFAULT_STOP_LOSS_RATE:
                    target_profit_rate = STALE_DEFAULT_TARGET_PROFIT
                    stop_loss_rate = STALE_DEFAULT_STOP_LOSS
                    logger.warning(
                        f"⚠️ {stock_code} 익절/손절 미설정 - 기본값 적용 "
                        f"(익절 {STALE_DEFAULT_TARGET_PROFIT*100:.0f}%, "
                        f"손절 {STALE_DEFAULT_STOP_LOSS*100:.0f}%)"
                    )

        except Exception as e:
            logger.warning(f"장기보유 체크 오류 ({trading_stock.stock_code}): {e}")

        return target_profit_rate, stop_loss_rate

    def _log_stale_position_summary(self, stale_info: list) -> None:
        """장기보유 종목 요약 로그 출력

        Args:
            stale_info: list of dicts with keys:
                stock_code, stock_name, days_held, quantity, buy_price
        """
        try:
            if not stale_info:
                return

            stale_count = len(stale_info)
            total_invested = sum(s['quantity'] * s['buy_price'] for s in stale_info)
            avg_days = sum(s['days_held'] for s in stale_info) / stale_count

            logger.info(
                f"📊 장기보유 현황: {stale_count}개 종목 "
                f"({total_invested:,.0f}원), 평균 보유 {avg_days:.0f}일"
            )

            # 개별 종목 상세 (디버그 레벨)
            for s in stale_info:
                logger.debug(
                    f"  - {s['stock_code']}({s['stock_name']}): "
                    f"{s['days_held']}일, {s['quantity']}주 "
                    f"@{s['buy_price']:,.0f}원"
                )

        except Exception as e:
            logger.warning(f"장기보유 요약 로그 오류: {e}")

    def _log_fund_sync_summary(self, restored_count: int, total_invested: float, mode: str) -> None:
        """포지션 복원 후 자금 동기화 요약 로깅

        Args:
            restored_count: 복원된 종목 수
            total_invested: 총 투자 금액
            mode: 모드 문자열 (가상매매/실전매매)
        """
        if not self.fund_manager:
            logger.info(
                f"[{mode}] 포지션 복원 완료: {restored_count}개 종목, "
                f"투자금액: {total_invested:,.0f}원 (FundManager 미연결)"
            )
            return

        available = self.fund_manager.available_funds
        invested = self.fund_manager.invested_funds
        total = self.fund_manager.total_funds
        position_count = len(self.fund_manager.current_position_codes)
        max_positions = self.fund_manager.max_position_count

        logger.info(
            f"[{mode}] 포지션 복원 완료: {restored_count}개 종목, "
            f"투자금액: {invested:,.0f}원, 가용자금: {available:,.0f}원"
        )

        # 포지션 수 제한 초과 경고
        if position_count > max_positions:
            logger.warning(
                f"보유 종목 수({position_count})가 최대 한도({max_positions})를 "
                f"초과합니다. 기존 보유분이므로 모두 유지하지만, 신규 매수는 차단됩니다."
            )

        # 자금 정합성 검증
        expected_total = available + invested + self.fund_manager.reserved_funds
        discrepancy = abs(total - expected_total)
        if discrepancy > 1:  # 1원 이상 불일치
            logger.warning(
                f"자금 정합성 불일치: total_funds({total:,.0f}) != "
                f"available({available:,.0f}) + invested({invested:,.0f}) + "
                f"reserved({self.fund_manager.reserved_funds:,.0f}) = {expected_total:,.0f}"
            )

    async def _restore_candidates(self, today: str) -> None:
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

    async def _restore_holdings_from_db(self) -> None:
        """가상매매 모드: DB에서 보유 종목 복원"""
        try:
            holdings = self.db_manager.get_virtual_open_positions()
            if holdings.empty:
                logger.info("[가상매매] 보유 종목 없음")
                return

            logger.info(f"[가상매매] 보유 종목 {len(holdings)}개 복원 시작")
            holding_restored = 0
            total_invested = 0.0
            stale_info = []  # 장기보유 종목 정보 수집

            for _, holding in holdings.iterrows():
                stock_code = holding['stock_code']
                stock_name = holding['stock_name']
                quantity = int(holding['quantity'])
                buy_price = float(holding['buy_price'])
                buy_time = holding.get('buy_time')  # 매수 시각 (장기보유 체크용)
                raw_tp = holding.get('target_profit_rate')
                try:
                    tp_value = float(raw_tp) if raw_tp is not None else None
                    target_profit_rate = tp_value if (tp_value is not None and not math.isnan(tp_value)) else DEFAULT_TARGET_PROFIT_RATE
                except (ValueError, TypeError, OverflowError):
                    target_profit_rate = DEFAULT_TARGET_PROFIT_RATE
                raw_sl = holding.get('stop_loss_rate')
                try:
                    sl_value = float(raw_sl) if raw_sl is not None else None
                    stop_loss_rate = sl_value if (sl_value is not None and not math.isnan(sl_value)) else DEFAULT_STOP_LOSS_RATE
                except (ValueError, TypeError, OverflowError):
                    stop_loss_rate = DEFAULT_STOP_LOSS_RATE

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

                        # 가상매수 기록 ID 복원
                        buy_record_id = int(holding.get('id', 0)) if holding.get('id') else None
                        if buy_record_id:
                            trading_stock.set_virtual_buy_info(buy_record_id, buy_price, quantity)

                        # 장기보유 체크 및 기본값 적용
                        if buy_time is not None:
                            target_profit_rate, stop_loss_rate = self._apply_stale_position_check(
                                trading_stock, buy_time,
                                target_profit_rate, stop_loss_rate,
                            )

                        trading_stock.target_profit_rate = target_profit_rate
                        trading_stock.stop_loss_rate = stop_loss_rate

                        self.trading_manager._change_stock_state(
                            stock_code,
                            StockState.POSITIONED,
                            f"DB 복원: {quantity}주 @{buy_price:,.0f}원 "
                            f"(익절:{target_profit_rate*100:.1f}% 손절:{stop_loss_rate*100:.1f}%)"
                            f"{' [장기보유]' if getattr(trading_stock, 'is_stale', False) is True else ''}",
                        )
                        holding_restored += 1

                        # FundManager 자금 동기화
                        invested = self._sync_fund_manager_for_position(
                            stock_code, quantity, buy_price
                        )
                        total_invested += invested

                        # VirtualTradingManager 가상 잔고 동기화
                        self._sync_virtual_balance_for_position(quantity, buy_price)

                        # 장기보유 종목 정보 수집
                        ts_is_stale = getattr(trading_stock, 'is_stale', False) is True
                        ts_days_held = getattr(trading_stock, 'days_held', 0)
                        ts_days_held = ts_days_held if isinstance(ts_days_held, int) else 0

                        if ts_is_stale:
                            stale_info.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'days_held': ts_days_held,
                                'quantity': quantity,
                                'buy_price': buy_price,
                            })

                        logger.debug(
                            f"{stock_code} 포지션 복원: {quantity}주 @{buy_price:,.0f}원, "
                            f"익절가 {buy_price*(1+target_profit_rate):,.0f}원, "
                            f"손절가 {buy_price*(1-stop_loss_rate):,.0f}원"
                            f"{f', 보유 {ts_days_held}일' if ts_days_held > 0 else ''}"
                        )

            logger.info(f"[가상매매] 보유 종목 {holding_restored}/{len(holdings)}개 복원 완료")
            self._log_fund_sync_summary(holding_restored, total_invested, "가상매매")

            # 장기보유 종목 요약
            self._log_stale_position_summary(stale_info)

        except Exception as e:
            logger.error(f"[가상매매] 보유 종목 복원 실패: {e}")

    async def _restore_holdings_from_real_account(self) -> None:
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
                    raw_tp = row.get('target_profit_rate')
                    raw_sl = row.get('stop_loss_rate')
                    try:
                        tp_val = float(raw_tp) if raw_tp is not None else None
                        tp_rate = tp_val if (tp_val is not None and not math.isnan(tp_val)) else DEFAULT_TARGET_PROFIT_RATE
                    except (ValueError, TypeError, OverflowError):
                        tp_rate = DEFAULT_TARGET_PROFIT_RATE
                    try:
                        sl_val = float(raw_sl) if raw_sl is not None else None
                        sl_rate = sl_val if (sl_val is not None and not math.isnan(sl_val)) else DEFAULT_STOP_LOSS_RATE
                    except (ValueError, TypeError, OverflowError):
                        sl_rate = DEFAULT_STOP_LOSS_RATE
                    db_holdings_dict[row['stock_code']] = {
                        'stock_name': row['stock_name'],
                        'quantity': int(row['quantity']),
                        'buy_price': float(row['buy_price']),
                        'buy_time': row.get('buy_time'),
                        'target_profit_rate': tp_rate,
                        'stop_loss_rate': sl_rate,
                    }

            logger.info(f"📊 [실전매매] DB 보유 종목: {len(db_holdings_dict)}개")

            # 3. 불일치 감지 및 로깅
            await self._detect_holdings_mismatch(real_holdings, db_holdings_dict)

            # 4. 미체결 매도 주문 조회 (C7 fix: SELL_PENDING 중복 매도 방지)
            pending_sell_codes = set()
            try:
                if hasattr(self.broker, 'get_pending_orders'):
                    pending_orders = self.broker.get_pending_orders()
                    if pending_orders:
                        for po in pending_orders:
                            # 매도 미체결 주문의 종목코드 수집
                            order_type = po.get('order_type', '') if isinstance(po, dict) else getattr(po, 'order_type', '')
                            stock_code_po = po.get('stock_code', '') if isinstance(po, dict) else getattr(po, 'stock_code', '')
                            # 매도 주문 판별: "sell", "02" (KIS 매도코드), "SELL" 등
                            if str(order_type).lower() in ('sell', '02', 'sell_market'):
                                pending_sell_codes.add(stock_code_po)
                                logger.info(f"📋 [실전매매] 미체결 매도 주문 발견: {stock_code_po}")
            except Exception as pending_err:
                logger.warning(f"⚠️ [실전매매] 미체결 주문 조회 실패 (POSITIONED로 폴백): {pending_err}")

            # 5. 실제 계좌 기준으로 메모리에 복원
            holding_restored = 0
            total_invested = 0.0
            stale_info = []  # 장기보유 종목 정보 수집

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
                    logger.warning(f"[실전매매] {stock_code} DB에 없음 - 기본 익절/손절률 적용")

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

                        # 장기보유 체크: DB에 buy_time이 있으면 사용
                        buy_time = db_holdings_dict.get(stock_code, {}).get('buy_time') if stock_code in db_holdings_dict else None
                        if buy_time is not None:
                            target_profit_rate, stop_loss_rate = self._apply_stale_position_check(
                                trading_stock, buy_time,
                                target_profit_rate, stop_loss_rate,
                            )

                        trading_stock.target_profit_rate = target_profit_rate
                        trading_stock.stop_loss_rate = stop_loss_rate

                        # C7 fix: 매도 미체결이 있으면 SELL_PENDING으로 복원
                        if stock_code in pending_sell_codes:
                            restore_state = StockState.SELL_PENDING
                            state_label = "SELL_PENDING (미체결 매도 존재)"
                        else:
                            restore_state = StockState.POSITIONED
                            state_label = "POSITIONED"

                        ts_is_stale = getattr(trading_stock, 'is_stale', False) is True
                        ts_days_held = getattr(trading_stock, 'days_held', 0)
                        ts_days_held = ts_days_held if isinstance(ts_days_held, int) else 0

                        self.trading_manager._change_stock_state(
                            stock_code,
                            restore_state,
                            f"[실전] 계좌 복원: {quantity}주 @{avg_price:,.0f}원 "
                            f"(익절:{target_profit_rate*100:.1f}% 손절:{stop_loss_rate*100:.1f}%) "
                            f"[{state_label}]"
                            f"{' [장기보유]' if ts_is_stale else ''}",
                        )
                        holding_restored += 1

                        # FundManager 자금 동기화
                        invested = self._sync_fund_manager_for_position(
                            stock_code, quantity, avg_price
                        )
                        total_invested += invested

                        # 장기보유 종목 정보 수집
                        if ts_is_stale:
                            stale_info.append({
                                'stock_code': stock_code,
                                'stock_name': stock_name,
                                'days_held': ts_days_held,
                                'quantity': quantity,
                                'buy_price': avg_price,
                            })

                        logger.info(
                            f"[실전] {stock_code}({stock_name}) 복원({state_label}): {quantity}주 @{avg_price:,.0f}원, "
                            f"익절가 {avg_price*(1+target_profit_rate):,.0f}원, "
                            f"손절가 {avg_price*(1-stop_loss_rate):,.0f}원"
                            f"{f', 보유 {ts_days_held}일' if ts_days_held > 0 else ''}"
                        )

            if real_holdings:
                logger.info(f"[실전매매] 보유 종목 {holding_restored}/{len(real_holdings)}개 복원 완료")
                self._log_fund_sync_summary(holding_restored, total_invested, "실전매매")

                # 장기보유 종목 요약
                self._log_stale_position_summary(stale_info)
            else:
                logger.info("[실전매매] 보유 종목 없음")

        except Exception as e:
            logger.error(f"[실전매매] 보유 종목 복원 실패: {e}")
            logger.warning("DB 복원으로 대체합니다...")
            await self._restore_holdings_from_db()

    async def _detect_holdings_mismatch(self, real_holdings: List[Dict], db_holdings_dict: Dict[str, Dict]) -> None:
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
