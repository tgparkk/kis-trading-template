"""
청산 핸들러 모듈
장 마감 시 포지션 청산 로직을 담당합니다.

EOD 청산 실패 복구:
- 청산 주문 실패 시 최대 3회 재시도
- 재시도 간 10초 대기
- 최종 실패 시 강제 COMPLETED 처리 + 자금 회수 + CRITICAL 텔레그램 알림
"""
import asyncio
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

from core.models import StockState
from utils.logger import setup_logger
from utils.korean_time import now_kst, get_previous_trading_day
from utils.price_utils import round_to_tick
from config.market_hours import MarketHours
from config.constants import SCREENER_SNAPSHOT_ENABLED, MAX_CANDIDATES_PER_STRATEGY

if TYPE_CHECKING:
    from main import DayTradingBot

# EOD 청산 재시도 설정
EOD_LIQUIDATION_MAX_RETRIES = 3
EOD_LIQUIDATION_RETRY_DELAY = 10  # 초

# EOD 청산 실패 항목의 키. **반드시 (종목코드, owner) 쌍이어야 한다.**
#
# 왜 쌍인가 (2026-07-29 독립 감사):
#   전략별 독립 포지션(B안, 2026-06-16) 이후 같은 종목을 2개 이상의 전략이
#   동시에 보유할 수 있다. 실패 추적을 stock_code 문자열로만 키잉하면
#   두 전략이 같은 종목의 청산에 실패했을 때 집합이 **한 항목으로 병합**되어
#   한쪽 소유자의 포지션이 강제완료·자금회수에서 통째로 누락된다.
#
# 왜 owner 를 슬롯 객체(owner_strategy_name)에서 읽는가:
#   owner 표기가 경로·상태별로 폴더키/클래스명으로 갈린 이력이 있다(01d336e).
#   문자열을 재구성하면 매칭이 깨지므로, 슬롯 객체가 들고 있는 값을 그대로
#   실어 보내고 그대로 비교한다(표기-불변 매칭).
#
# 동일 결함 클래스 이력: f4c3683(_position_owner) · 0eb4a5e(보유종목 레지스트리)
#   — 셋 다 "돈이 걸린 자료구조를 stock_code 단독으로 키잉"한 같은 실수다.
#   이 주석을 지우고 Set[str] 로 되돌리지 말 것.
EodFailedEntry = Tuple[str, Optional[str]]


class LiquidationHandler:
    """장 마감 청산 담당 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self.bot = bot
        self.logger = setup_logger(__name__)
        self._last_eod_liquidation_date = None
        # (종목코드, owner) 쌍 집합 — 다중 소유 종목의 실패를 병합하지 않는다.
        self._eod_failed_stocks: Set[EodFailedEntry] = set()
        self._eod_retry_count: int = 0
        self._snapshot_done_date = None  # 스크리너 스냅샷 중복 호출 방지

    # -----------------------------------------------------------------
    # EOD 실패 항목 헬퍼 (owner 인지)
    # -----------------------------------------------------------------

    @staticmethod
    def _slot_owner(trading_stock) -> Optional[str]:
        """슬롯 객체가 들고 있는 owner 표기를 그대로 읽는다(표기-불변).

        문자열을 재구성하지 않는다 — 폴더키/클래스명 분열 이력(01d336e).

        ⚠️ **3값을 구분해 보존한다. `or` 로 뭉개지 말 것**(2026-07-29 리뷰 HIGH):
          - named  : 전략 표기 문자열
          - 무기명 : ""   ← 버릴 정보가 아니다. `_find_by_code(code, "")` 는
                          **무기명 슬롯만** 정확 매칭하는 가장 정밀한 키다.
          - 미상   : None ← 속성 자체가 없을 때만. 필터가 해제되어 남의 슬롯이
                          후보에 들어오므로 폴백 경로로만 써야 한다.
        `or None` 을 쓰면 "" 가 None 으로 뭉개져, 무기명 슬롯의 실패 항목이
        삽입순 첫 슬롯(대개 남의 named 슬롯)을 집어 **정상 포지션을 파괴**한다.
        """
        owner = getattr(trading_stock, 'owner_strategy_name', None)
        if owner is None:
            return None
        return owner  # "" 포함, 있는 그대로

    @staticmethod
    def _normalize_failed_entry(item) -> EodFailedEntry:
        """실패 항목을 (종목코드, owner) 쌍으로 정규화.

        owner 의 3값(named/""/None)을 그대로 보존한다 — 여기서 뭉개면
        `_slot_owner` 를 고친 의미가 없다.
        구버전 표현(문자열 단독)만 owner=None(미상) 쌍으로 승격한다.
        """
        if isinstance(item, tuple):
            code, owner = item
            return (code, owner)
        return (item, None)

    def _normalized_failed_entries(self) -> List[EodFailedEntry]:
        """현재 실패 집합의 스냅샷을 쌍 리스트로 반환(순회 중 변경 대비)."""
        return [self._normalize_failed_entry(e) for e in list(self._eod_failed_stocks)]

    def _count_positioned(self, stock_code: str) -> Optional[int]:
        """POSITIONED 기준 동일 종목 슬롯 수(경고 문구용 진단값).

        진단 목적이므로 어떤 이유로든 실패하면 None 을 돌려주고 흐름을 막지 않는다
        — 자금 회수 경로가 로그 보조값 때문에 죽으면 안 된다.
        """
        try:
            positioned = self.bot.trading_manager.get_stocks_by_state(StockState.POSITIONED)
            return len([s for s in positioned if s.stock_code == stock_code])
        except Exception:
            return None

    def _warn_unknown_owner(self, stock_code: str, context: str,
                            candidate_count: Optional[int]) -> None:
        """owner 미상(None) 폴백 경고. 후보가 2개 이상이면 오귀속은 확정이다."""
        if candidate_count is None:
            severity = "후보 수 미상"
        elif candidate_count >= 2:
            severity = (
                f"후보 {candidate_count}개 = 다중 소유 확정 — 임의 슬롯 선택은 "
                f"오귀속이 **확정적이며 남의 정상 포지션을 파괴한다**"
            )
        else:
            severity = f"후보 {candidate_count}개 — 현재는 단일 소유라 오귀속 없음"
        self.logger.warning(
            f"[EOD소유미상] {stock_code} {context}: 실패 항목의 owner 가 미상(None)이라 "
            f"종목코드 단독으로 조회합니다. {severity}. "
            f"무기명 슬롯('')은 정확 매칭되므로 이 경로는 owner 정보 자체가 유실된 "
            f"경우다 — 항목 적재 경로를 확인할 것"
        )

    def _match_owned_slot(self, stocks, stock_code: str, owner: Optional[str]):
        """실패 항목의 owner 로 슬롯을 특정한다.

        owner 가 **미상(None)일 때만** 종목코드 단독 매칭으로 폴백한다.
        무기명("")은 `_slot_owner(slot) == ""` 로 정확 매칭되므로 폴백이 필요 없다.
        """
        candidates = [s for s in stocks if s.stock_code == stock_code]
        if not candidates:
            return None

        if owner is None:
            self._warn_unknown_owner(stock_code, "재시도 조회", len(candidates))
            return candidates[0]

        for slot in candidates:
            if self._slot_owner(slot) == owner:
                return slot

        # owner 슬롯이 POSITIONED 에 없다. 남의 슬롯을 대신 집지 않는다(fail-closed).
        # ⚠️ "이미 청산됨"이라고 단정하지 말 것 — 예외 경로가 SELL_CANDIDATE 등
        #    다른 상태의 슬롯에 대한 쌍을 적재할 수 있고, 이 루프는 POSITIONED 만 뒤진다.
        self.logger.info(
            f"EOD 실패 항목 {stock_code}(owner={owner!r}) 슬롯이 POSITIONED 에 없음 "
            f"— 재시도 대상에서 제외(청산 완료 또는 다른 상태). 상태 확인 필요"
        )
        return None

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

                    # trading_stock의 owner_strategy 우선 참조
                    owner = getattr(trading_stock, 'owner_strategy', None)
                    strategy_for_eod = owner or getattr(self.bot.decision_engine, 'strategy', None)

                    if strategy_for_eod and not strategy_for_eod.should_liquidate_eod(stock_code):
                        name = getattr(strategy_for_eod, 'name', 'unknown')
                        self.logger.info(f"EOD 청산 스킵 (전략 {name} 거부): {stock_code}")
                        continue

                    quantity = int(trading_stock.position.quantity)

                    # 가격 산정: 가능한 경우 최신 분봉 종가, 없으면 현재가 조회
                    sell_price = 0.0
                    combined_data = self.bot.intraday_manager.get_combined_chart_data(stock_code)
                    if combined_data is not None and len(combined_data) > 0:
                        sell_price = float(combined_data['close'].iloc[-1])
                    else:
                        price_obj = self.bot.broker.get_current_price(stock_code)
                        if price_obj is not None and price_obj > 0:
                            sell_price = float(price_obj)
                    sell_price = round_to_tick(sell_price)

                    # 가상/실전 모드 분기
                    is_virtual = getattr(self.bot.decision_engine, 'is_virtual_mode', False)
                    if is_virtual:
                        # 가상매매 - execute_virtual_sell 사용
                        result = await self.bot.decision_engine.execute_virtual_sell(
                            trading_stock, sell_price, "장마감 일괄청산"
                        )
                        # fund_manager 업데이트는 execute_virtual_sell() 내부에서 일원화 처리 (F4 fix 2026-05-04)
                        if result:
                            self.logger.info(
                                f"장마감 가상청산 완료: {stock_code} {quantity}주 @{sell_price:,.0f}원"
                            )
                        else:
                            self.logger.warning(f"장마감 가상청산 실패: {stock_code}")
                    else:
                        # 실매매 - 기존 실매도 로직
                        _owner = trading_stock.owner_strategy_name or None
                        moved = self.bot.trading_manager.move_to_sell_candidate(
                            stock_code, "장마감 일괄청산", strategy=_owner)
                        if moved:
                            await self.bot.trading_manager.execute_sell_order(
                                stock_code, quantity, sell_price, "장마감 일괄청산", market=True,
                                force=True, strategy=_owner
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
            else:
                self.logger.info(
                    f"{time_label} 시장가 일괄매도 시작: {len(positioned_stocks)}종목"
                )

                failed_stocks = []

                for trading_stock in positioned_stocks:
                    try:
                        if not trading_stock.position or trading_stock.position.quantity <= 0:
                            continue

                        stock_code = trading_stock.stock_code
                        # 실패 추적 키에 실을 owner — 슬롯 객체 필드를 그대로 읽는다.
                        owner_name = self._slot_owner(trading_stock)

                        # trading_stock의 owner_strategy 우선 참조
                        owner = getattr(trading_stock, 'owner_strategy', None)
                        strategy_for_eod = owner or getattr(self.bot.decision_engine, 'strategy', None)

                        if strategy_for_eod and not strategy_for_eod.should_liquidate_eod(stock_code):
                            name = getattr(strategy_for_eod, 'name', 'unknown')
                            self.logger.info(f"{time_label} EOD 청산 스킵 (전략 {name} 거부): {stock_code}")
                            continue

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
                                if price_obj is not None and price_obj > 0:
                                    eod_sell_price = float(price_obj)

                            result = await self.bot.decision_engine.execute_virtual_sell(
                                trading_stock, eod_sell_price,
                                f"{time_label} 시장가 일괄매도"
                            )
                            # fund_manager 업데이트는 execute_virtual_sell() 내부에서 일원화 처리 (F4 fix 2026-05-04)
                            if result:
                                self.logger.info(
                                    f"{time_label} 가상매도 완료: "
                                    f"{stock_code}({stock_name}) {quantity}주"
                                )
                            else:
                                self.logger.warning(
                                    f"{stock_code} 가상매도 실패 - 재시도 대상에 추가"
                                )
                                failed_stocks.append((stock_code, owner_name))
                        else:
                            # 실매매 - 기존 실매도 로직
                            moved = self.bot.trading_manager.move_to_sell_candidate(
                                stock_code, f"{time_label} 시장가 일괄매도", strategy=owner_name
                            )
                            if moved:
                                await self.bot.trading_manager.execute_sell_order(
                                    stock_code, quantity, current_price,
                                    f"{time_label} 시장가 일괄매도", market=True,
                                    force=True, strategy=owner_name
                                )
                                self.logger.info(
                                    f"{time_label} 시장가 매도: "
                                    f"{stock_code}({stock_name}) {quantity}주 시장가 주문"
                                )
                            else:
                                self.logger.warning(
                                    f"{stock_code} 매도 후보 전환 실패 - 재시도 대상에 추가"
                                )
                                failed_stocks.append((stock_code, owner_name))

                    except Exception as se:
                        self.logger.error(
                            f"{time_label} 시장가 매도 개별 처리 오류({trading_stock.stock_code}): {se}"
                        )
                        # 예외 경로에서도 owner 를 잃지 않는다(병합 방지).
                        failed_stocks.append(
                            (trading_stock.stock_code, self._slot_owner(trading_stock))
                        )

                self._eod_failed_stocks = set(failed_stocks)

                if failed_stocks:
                    self.logger.warning(f"{time_label} 청산 실패 종목: {failed_stocks}")
                else:
                    self.logger.info(f"{time_label} 시장가 일괄매도 요청 완료")

            # (스크리너 스냅샷 생성은 EOD 가 아니라 장전 최초 후보 로드 시점으로 이전됨:
            #  당일 일봉이 quant 에 ~15:35 적재되므로 15:00 EOD 시점엔 빈 유니버스가 된다.
            #  main._load_screener_candidates 가 run_screener_snapshot_hook 을 호출한다.)

            # EOD 잔고 이월: 가상매매 모드일 때 오늘 잔고를 DB에 저장
            self._save_paper_eod_balance_if_virtual()

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
            self.logger.critical(
                f"EOD 청산 재시도 한도 초과 ({EOD_LIQUIDATION_MAX_RETRIES}회): "
                f"실패 종목 {list(self._eod_failed_stocks)} - 강제 완료 처리 시작"
            )
            # 강제 완료 처리: 자금 회수 + 상태 전환
            await self._force_complete_failed_stocks()
            return False

        self.logger.info(
            f"EOD 청산 재시도 ({self._eod_retry_count}/{EOD_LIQUIDATION_MAX_RETRIES}): "
            f"{list(self._eod_failed_stocks)}"
        )

        still_failed = []
        for stock_code, owner_name in self._normalized_failed_entries():
            # 슬롯을 특정하면 그 슬롯의 owner 로 승격해 둔다. 이후 재적재(성공/실패/
            # 예외)는 전부 이 값을 쓴다 — 미상(None)으로 들어온 레거시 항목이
            # 1회 재시도만에 정확한 쌍으로 회복된다.
            resolved_owner = owner_name
            try:
                positioned_stocks = self.bot.trading_manager.get_stocks_by_state(StockState.POSITIONED)
                # 쌍으로 조회 — 종목코드 단독 매칭은 남의 슬롯을 집는다.
                target = self._match_owned_slot(positioned_stocks, stock_code, owner_name)
                if not target or not target.position or target.position.quantity <= 0:
                    continue  # 청산 완료 또는 POSITIONED 아님 (위 조회 로그 참조)

                resolved_owner = self._slot_owner(target)
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
                        if price_obj is not None and price_obj > 0:
                            retry_sell_price = float(price_obj)

                    result = await self.bot.decision_engine.execute_virtual_sell(
                        target, retry_sell_price,
                        f"EOD 청산 재시도 #{self._eod_retry_count}"
                    )
                    # fund_manager 업데이트는 execute_virtual_sell() 내부에서 일원화 처리 (F4 fix 2026-05-04)
                    if result:
                        self.logger.info(f"EOD 가상매도 재시도 성공: {stock_code} {quantity}주")
                    else:
                        self.logger.warning(
                            f"EOD 가상매도 재시도 실패: {stock_code} - 재시도 대상 유지"
                        )
                        still_failed.append((stock_code, resolved_owner))
                else:
                    # 실매매 - 기존 실매도 로직
                    moved = self.bot.trading_manager.move_to_sell_candidate(
                        stock_code, f"EOD 청산 재시도 #{self._eod_retry_count}",
                        strategy=resolved_owner
                    )
                    if moved:
                        await self.bot.trading_manager.execute_sell_order(
                            stock_code, quantity, 0.0,
                            f"EOD 청산 재시도 #{self._eod_retry_count}", market=True,
                            force=True, strategy=resolved_owner
                        )
                        self.logger.info(f"EOD 재시도 성공: {stock_code} {quantity}주")
                    else:
                        self.logger.warning(
                            f"EOD 재시도 매도 후보 전환 실패: {stock_code} - 재시도 대상 유지"
                        )
                        still_failed.append((stock_code, resolved_owner))
            except Exception as e:
                self.logger.error(f"EOD 재시도 실패 ({stock_code}): {e}")
                # 예외 경로도 승격된 owner 를 쓴다(다른 재적재 지점과 일관).
                still_failed.append((stock_code, resolved_owner))

        self._eod_failed_stocks = set(still_failed)
        return len(still_failed) == 0

    async def _force_complete_failed_stocks(self) -> None:
        """EOD 청산 최종 실패 종목을 강제 완료 처리하고 자금을 회수합니다.

        재시도 한도 초과 시 호출됩니다.
        실제 매도가 이루어지지 않았으므로 PnL은 0으로 처리합니다.
        """
        # {stock_code: {name, quantity, avg_price, invested}} 수동 매도용 정보 수집
        force_completed_details = []
        for stock_code, owner_name in self._normalized_failed_entries():
            try:
                # 쌍으로 조회한다. owner 없이 조회하면 삽입순 첫 슬롯이 잡혀
                # 남의 슬롯 원가를 남의 소유자에게서 회수하게 된다(2026-07-29 감사).
                # ⚠️ `is not None` 이어야 한다. 무기명("")도 strategy="" 로 정확
                #    매칭되므로 폴백 대상이 아니다 — truthiness 로 쓰면 "" 가
                #    폴백을 타서 남의 named 슬롯을 파괴한다(2026-07-29 리뷰 HIGH).
                if owner_name is not None:
                    trading_stock = self.bot.trading_manager.get_trading_stock(
                        stock_code, strategy=owner_name
                    )
                else:
                    self._warn_unknown_owner(
                        stock_code, "강제완료 조회", self._count_positioned(stock_code)
                    )
                    trading_stock = self.bot.trading_manager.get_trading_stock(stock_code)

                if not trading_stock:
                    # fail-closed: 남의 슬롯으로 대체 회수하지 않는다. 강제완료는
                    # DB 부작용이 0이고 invested_funds 는 영속되지 않으므로,
                    # 건너뛰어도 다음 기동 재구성 결과는 동일하다(2026-07-29 리뷰 실측).
                    # ⚠️ 여기에 `get_trading_stock(stock_code)` 코드 단독 폴백을
                    #    되살리지 말 것 — 남의 원가를 회수하고 정상 포지션을 파괴한다.
                    #    TestForceCompleteFailsClosed 가 이 금지를 고정한다.
                    self.logger.warning(
                        f"EOD 강제완료 건너뜀: {stock_code}(owner={owner_name!r}) "
                        f"소유 슬롯 없음 — 자금 회수/상태 전환 없음(남의 슬롯 보호)"
                    )
                    continue

                # 포지션 정보에서 투자 원금 계산
                buy_cost = 0.0
                quantity = 0
                avg_price = 0.0
                if trading_stock.position and trading_stock.position.quantity > 0:
                    quantity = int(trading_stock.position.quantity)
                    avg_price = float(trading_stock.position.avg_price)
                    buy_cost = avg_price * quantity

                # 1. FundManager 자금 회수 (PnL 0 - 실제 매도 없으므로 손익 불확정)
                #    owner 는 (재구성하지 않고) 조회로 특정된 슬롯 객체에서 읽는다
                #    (표기-불변) — 다중 소유 종목에서 남의 보유 엔트리를 지우지 않기 위함.
                fm_owner = self._slot_owner(trading_stock)
                if buy_cost > 0:
                    self.bot.fund_manager.release_investment(
                        buy_cost, stock_code=stock_code, owner=fm_owner
                    )
                self.bot.fund_manager.remove_position(stock_code, fm_owner)

                # 2. 상태 강제 전환 → COMPLETED
                #    여기는 원시값을 그대로 넘긴다. 상태 매니저는 owner 문자열을
                #    정확히 비교하므로 무기명 슬롯의 ""(빈 문자열)이 None 보다 정밀하다
                #    (None 은 필터 해제 = 남의 슬롯까지 후보에 들어온다).
                self.bot.trading_manager._change_stock_state(
                    stock_code, StockState.COMPLETED,
                    f"EOD 청산 {EOD_LIQUIDATION_MAX_RETRIES}회 실패 - 강제 완료",
                    strategy=trading_stock.owner_strategy_name
                )

                # 3. 포지션 및 플래그 클리어
                trading_stock.clear_position()
                trading_stock.is_selling = False

                force_completed_details.append({
                    'stock_code': stock_code,
                    'stock_name': trading_stock.stock_name,
                    'quantity': quantity,
                    'avg_price': avg_price,
                    'invested': buy_cost,
                })
                self.logger.critical(
                    f"EOD 강제완료: {stock_code}({trading_stock.stock_name}) "
                    f"{quantity}주 @{avg_price:,.0f}원 - 투자금 {buy_cost:,.0f}원 회수, "
                    f"PnL 0 처리 (실제 매도 미완료)"
                )

            except Exception as e:
                self.logger.error(
                    f"EOD 강제완료 처리 실패 ({stock_code}): {e}"
                )

        # 4. 텔레그램 CRITICAL 알림 (수동 매도 정보 포함)
        if force_completed_details:
            alert_msg = self._build_force_complete_alert(force_completed_details)
            if hasattr(self.bot, 'telegram') and self.bot.telegram:
                try:
                    await self.bot.telegram.notify_system_status(alert_msg)
                except Exception:
                    pass

        # 실패 목록 초기화
        self._eod_failed_stocks.clear()

    def _build_force_complete_alert(self, details: list) -> str:
        """강제완료 텔레그램 알림 메시지 구성 (수동 매도 안내 포함)"""
        n = len(details)
        total_invested = sum(d['invested'] for d in details)

        lines = [
            f"[CRITICAL] EOD 청산 {EOD_LIQUIDATION_MAX_RETRIES}회 실패 - 강제 완료 처리",
            "해당 종목은 실제 매도되지 않았습니다. 다음 영업일 수동 확인 필요.",
            "",
            "[수동 매도 대상 종목]",
        ]
        for d in details:
            line = (
                f"- {d['stock_code']} {d['stock_name']}: "
                f"{d['quantity']}주 @{d['avg_price']:,.0f}원 "
                f"(원금 {d['invested']:,.0f}원)"
            )
            lines.append(line)

        lines.append("")
        lines.append(f"총 {n}건, 원금 합계 {total_invested:,.0f}원")

        # 계좌번호 앞 4자리만 노출 (마스킹)
        try:
            from api.kis_auth import get_account_number
            acct = get_account_number()
            masked = f"{acct[:4]}-XX-**" if acct and len(acct) >= 4 else "알 수 없음"
        except Exception:
            masked = "알 수 없음"
        lines.append(f"계좌번호: {masked} (KIS)")

        return "\n".join(lines)

    async def run_screener_snapshot_hook(self) -> None:
        """EOD 완료 후 스크리너 스냅샷 수집 훅.

        SCREENER_SNAPSHOT_ENABLED=true 환경변수일 때만 실행.
        실패해도 메인 루프를 중단하지 않는다 (warning 로그만).
        하루 1회만 실행 (중복 호출 방지).
        """
        if not SCREENER_SNAPSHOT_ENABLED:
            return

        # 당일 이미 실행했으면 스킵 (15:00 재시도 루프에서 중복 호출 방지)
        today = now_kst().date()
        if self._snapshot_done_date == today:
            return
        self._snapshot_done_date = today

        try:
            from runners.screener_snapshot_collector import run_once, resolve_active_strategies
            # scan_date = 직전 거래일. 당일 일봉은 quant 에 ~15:35 적재되므로 당일을 쓰면
            # 빈 유니버스가 된다. 직전 거래일은 야간 적재 완료라 항상 채워진다(장전 생성 정합).
            scan_date = get_previous_trading_day(now_kst()).date()

            broker = getattr(self.bot, 'broker', None)
            db_manager = getattr(self.bot, 'db_manager', None)
            config = getattr(self.bot, 'config', None)

            summaries = run_once(
                strategies=resolve_active_strategies(config),
                scan_date=scan_date,
                max_candidates=MAX_CANDIDATES_PER_STRATEGY,
                dry_run=False,
                broker=broker,
                db_manager=db_manager,
                config=config,
            )

            # 텔레그램 알림
            ok_parts = [f"{s['strategy']} {s['count']}건" for s in summaries if s["ok"]]
            if ok_parts and hasattr(self.bot, 'telegram') and self.bot.telegram:
                msg = f"[스크리너 스냅샷] {', '.join(ok_parts)} 저장 완료 ({scan_date})"
                try:
                    await self.bot.telegram.notify_system_status(msg)
                except Exception:
                    pass

            failed = [s["strategy"] for s in summaries if not s["ok"]]
            if failed:
                self.logger.warning("스크리너 스냅샷 일부 실패: %s", failed)
            else:
                self.logger.info("스크리너 스냅샷 수집 완료: %s", ok_parts)

        except Exception as e:
            self.logger.warning("스크리너 스냅샷 훅 오류 (무시): %s", e)

    def _save_paper_eod_balance_if_virtual(self) -> None:
        """가상매매 모드일 때 현재 잔고를 paper_trading_state에 저장.

        실패해도 메인 루프를 중단하지 않는다 (warning 로그만).
        """
        try:
            is_virtual = getattr(self.bot.decision_engine, 'is_virtual_mode', False)
            if not is_virtual:
                return
            virtual_mgr = getattr(
                getattr(self.bot, 'decision_engine', None),
                'virtual_trading',
                None,
            )
            if virtual_mgr is None:
                self.logger.warning("paper EOD 잔고 저장 생략: virtual_trading_manager 참조 불가")
                return
            ok = virtual_mgr.save_paper_trading_state()
            if ok:
                virtual_mgr.log_cumulative_profit()
        except Exception as e:
            self.logger.warning(f"paper EOD 잔고 저장 훅 오류 (무시): {e}")

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
