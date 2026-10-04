"""
주문 실행 모듈

매수/매도 주문 실행 및 종목 선정 관리
"""
import asyncio
from typing import TYPE_CHECKING, Optional

from ..models import TradingStock, StockState
from utils.logger import setup_logger
from utils.korean_time import now_kst

if TYPE_CHECKING:
    from .stock_state_manager import StockStateManager
    from ..intraday_stock_manager import IntradayStockManager
    from ..data_collector import RealTimeDataCollector
    from ..order_manager import OrderManager
    from ..fund_manager import FundManager


class OrderExecution:
    """
    주문 실행 관리자

    주요 기능:
    1. 선정된 종목 추가
    2. 매수 주문 실행
    3. 매도 후보 전환
    4. 매도 주문 실행
    """

    def __init__(self, state_manager: 'StockStateManager',
                 intraday_manager: 'IntradayStockManager',
                 data_collector: 'RealTimeDataCollector',
                 order_manager: 'OrderManager') -> None:
        """
        초기화

        Args:
            state_manager: 종목 상태 관리자
            intraday_manager: 장중 종목 관리자
            data_collector: 실시간 데이터 수집기
            order_manager: 주문 관리자
        """
        self.state_manager = state_manager
        self.intraday_manager = intraday_manager
        self.data_collector = data_collector
        self.order_manager = order_manager
        self.logger = setup_logger(__name__)

        # FundManager 연결 (나중에 설정)
        self.fund_manager: Optional['FundManager'] = None

        # 재거래 설정
        self.enable_re_trading = True

        # 진행 중인 실전 주문 호출 태스크(NEW-A1 shield) — 종료 시 미체결 취소 «전에»
        # 끝나기를 기다려, 등록 전 주문을 취소 대상에서 놓치지 않게 한다(리뷰 사소3).
        self._inflight_order_tasks: set = set()

    def set_fund_manager(self, fund_manager: 'FundManager') -> None:
        """FundManager 설정"""
        self.fund_manager = fund_manager
        self.logger.debug("OrderExecution에 FundManager 연결 완료")

    async def add_selected_stock(self, stock_code: str, stock_name: str,
                                 selection_reason: str = "", prev_close: float = 0.0,
                                 owner_strategy: str = "") -> bool:
        """
        조건검색으로 선정된 종목 추가 (비동기)

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            selection_reason: 선정 사유
            prev_close: 전날 종가 (일봉 기준)
            owner_strategy: 소유 전략명. 지정 시 해당 전략 소유 인스턴스만 조회/등록
                            (전략별 자본 독립 → 같은 종목을 여러 전략이 각자 보유 가능).
                            미지정("") 시 종목코드 단독 매칭(레거시/단일전략).

        Returns:
            bool: 추가 성공 여부
        """
        try:
            # Lock 안에서는 동기 상태 변경만 수행하고, await는 Lock 밖에서 호출
            is_reentry = False
            is_already_managed = False
            owner = owner_strategy or None

            with self.state_manager.lock:
                current_time = now_kst()

                # 이미 존재하는 종목인지 확인 (owner 지정 시 해당 전략 소유분만)
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=owner)
                if trading_stock is not None:
                    # 재진입 허용: COMPLETED/FAILED -> SELECTED로 재등록
                    if trading_stock.state in (StockState.COMPLETED, StockState.FAILED):
                        # 상태 변경 및 메타 업데이트
                        trading_stock.selected_time = current_time
                        trading_stock.selection_reason = selection_reason
                        # 포지션/주문 정보 및 매매 플래그 정리
                        trading_stock.clear_position()
                        trading_stock.clear_current_order()
                        trading_stock.order_processed = False  # 재진입 시 체결 처리 플래그 리셋
                        trading_stock.is_buying = False   # 이전 사이클 잔존 플래그 초기화
                        trading_stock.is_selling = False   # 이전 사이클 잔존 플래그 초기화
                        self.state_manager.change_stock_state(
                            stock_code, StockState.SELECTED, f"재선정: {selection_reason}",
                            strategy=trading_stock.owner_strategy_name
                        )
                        is_reentry = True
                    else:
                        # 그 외 상태에서는 기존 관리 유지
                        is_already_managed = True
                else:
                    # 신규 등록 (owner 전략을 생성 시점에 바인딩 → 슬롯 등록부터 소유자 확정)
                    trading_stock = TradingStock(
                        stock_code=stock_code,
                        stock_name=stock_name,
                        state=StockState.SELECTED,
                        selected_time=current_time,
                        selection_reason=selection_reason,
                        prev_close=prev_close,
                        owner_strategy_name=owner_strategy or "",
                    )

                    # 등록
                    self.state_manager.register_stock(trading_stock)

            # 이미 관리 중인 종목이면 바로 반환
            if is_already_managed:
                return True

            # Lock 해제 후 비동기 호출 (재선정 및 신규 등록 공통)
            success = await self.intraday_manager.add_selected_stock(
                stock_code, stock_name, selection_reason
            )

            if success:
                # RealTimeDataCollector에도 후보 종목 등록 (실시간 현재가 모니터링)
                self.data_collector.add_candidate_stock(stock_code, stock_name)
                label = "재선정" if is_reentry else "선정"
                self.logger.info(
                    f"{stock_code}({stock_name}) {label} 완료 - "
                    f"시간: {current_time.strftime('%H:%M:%S')}"
                )
                return True
            else:
                if is_reentry:
                    self.logger.warning(f"{stock_code} 재선정 실패 - Intraday 등록 실패")
                else:
                    # 신규 등록 실패 시 제거 (해당 owner 소유분만)
                    with self.state_manager.lock:
                        self.state_manager.unregister_stock(stock_code, strategy=owner)
                return False

        except Exception as e:
            self.logger.error(f"{stock_code} 종목 추가 오류: {e}")
            return False

    async def execute_buy_order(self, stock_code: str, quantity: int,
                                price: float, reason: str = "",
                                strategy: Optional[str] = None) -> bool:
        """
        매수 주문 실행

        Args:
            stock_code: 종목코드
            quantity: 주문 수량
            price: 주문 가격
            reason: 매수 사유
            strategy: 소유 전략명. 지정 시 해당 전략 소유 인스턴스만 조회/변경한다
                      (다중소유 종목의 오귀속 방지). 미지정(None) 시 종목코드 단독
                      매칭 = 기존 폴백 동작 보존.

        Returns:
            bool: 주문 성공 여부
        """
        try:
            with self.state_manager.lock:
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if trading_stock is None:
                    self.logger.warning(f"{stock_code}: 관리 중이지 않은 종목")
                    return False

                # 중복 매수 방지: 이미 매수 진행 중인지 확인
                if trading_stock.is_buying:
                    self.logger.warning(f"{stock_code}: 이미 매수 진행 중 (중복 매수 방지)")
                    return False

                # 25분 매수 쿨다운 확인
                if trading_stock.is_buy_cooldown_active():
                    remaining_minutes = trading_stock.get_remaining_cooldown_minutes()
                    self.logger.warning(
                        f"{stock_code}: 매수 쿨다운 활성화 (남은 시간: {remaining_minutes}분)"
                    )
                    return False

                # FundManager 매도 후 재매수 쿨다운 확인
                if self.fund_manager and self.fund_manager.is_sell_cooldown_active(stock_code):
                    self.logger.warning(
                        f"{stock_code}: 매도 후 재매수 쿨다운 활성 (익절/손절 후 대기)"
                    )
                    return False

                # 동시 보유 종목 수 제한 확인
                if self.fund_manager and not self.fund_manager.can_add_position(stock_code):
                    self.logger.warning(
                        f"{stock_code}: 동시 보유 종목 수 초과로 매수 거부"
                    )
                    return False

                # 상태 검증 (SELECTED 또는 COMPLETED에서 직접 매수 가능)
                if trading_stock.state not in [StockState.SELECTED, StockState.COMPLETED]:
                    self.logger.warning(
                        f"{stock_code}: 매수 가능 상태가 아님 (현재: {trading_stock.state.value})"
                    )
                    return False

                # 매수 진행 플래그 설정
                trading_stock.is_buying = True
                trading_stock.order_processed = False  # 새 주문이므로 리셋

                # 주문에 실을 owner 표기는 **슬롯 객체**에서 읽는다(표기-불변).
                # 인자 strategy 는 None 폴백이 있어 무기명이 될 수 있고, 그러면
                # 체결 후처리가 다시 종목코드 단독 조회로 떨어진다.
                _owner_for_order = trading_stock.owner_strategy_name or ""

                # 매수 주문 중 상태로 변경
                self.state_manager.change_stock_state(
                    stock_code, StockState.BUY_PENDING, f"매수 주문: {reason}",
                    strategy=trading_stock.owner_strategy_name
                )

                # 데이터 수집기에 후보 종목으로 추가 (실시간 모니터링)
                self.data_collector.add_candidate_stock(stock_code, trading_stock.stock_name)

            # 매수 주문 실행 — NEW-A1(2026-10-04): 주문 호출(KIS 접수 → pending 등록 →
            # 예약 이전 → 접수 알림)을 별도 태스크로 돌리고 shield 로 기다린다. 바깥이
            # 취소돼도(on_tick 30초 타임아웃 등) 주문 호출은 끝까지 가서 스스로 등록되고,
            # 슬롯·예약 정리는 결과를 보고 콜백이 한다(_finish_buy_order_after_cancel).
            # 종전엔 취소가 KIS 응답 대기 중에 떨어져 «KIS 엔 접수됐는데 봇은 모르는 주문»
            # (손절 감시 없는 보유) · BUY_PENDING 고착 · 예약 누수가 생겼다.
            # 이 메서드는 실전 전용이다(호출자 = execute_real_buy · 페이퍼는 가상 매수 경로).
            place_task = asyncio.ensure_future(self.order_manager.place_buy_order(
                stock_code, quantity, price, owner_strategy=_owner_for_order
            ))
            self._track_inflight(place_task)
            try:
                order_id = await asyncio.shield(place_task)
            except asyncio.CancelledError:
                self.logger.error(
                    f"🚨 {stock_code} 매수 주문 대기 중 취소됨 — 주문 호출은 끝까지 진행하고 "
                    f"결과로 슬롯·예약을 정리한다(NEW-A1)"
                )
                place_task.add_done_callback(
                    lambda t: self._finish_buy_order_after_cancel(
                        t, stock_code, strategy, reason, _owner_for_order))
                raise

            return self._apply_buy_order_result(stock_code, strategy, reason, order_id)

        except Exception as e:
            self.logger.error(f"{stock_code} 매수 주문 오류: {e}")
            # 오류 시 원래 상태로 되돌림
            with self.state_manager.lock:
                _ts = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if _ts is not None:
                    _ts.is_buying = False
                    original_state = (
                        StockState.COMPLETED if "재거래" in reason else StockState.SELECTED
                    )
                    self.state_manager.change_stock_state(
                        stock_code, original_state, f"매수 주문 오류: {e}",
                        strategy=_ts.owner_strategy_name
                    )
            return False

    def _track_inflight(self, task: 'asyncio.Future') -> None:
        self._inflight_order_tasks.add(task)
        task.add_done_callback(self._inflight_order_tasks.discard)

    async def wait_inflight_orders(self, timeout: float = 40.0) -> int:
        """진행 중인 실전 주문 호출이 끝나기를 최대 timeout 초 기다린다(취소하지 않음).

        Returns: 시간 안에 끝나지 않은 건수(0 이면 전부 등록·실패 확정).
        """
        pending = [t for t in self._inflight_order_tasks if not t.done()]
        if not pending:
            return 0
        self.logger.info(f"진행 중인 주문 호출 {len(pending)}건 완료 대기(최대 {timeout:.0f}초)")
        _, not_done = await asyncio.wait(pending, timeout=timeout)
        if not_done:
            self.logger.error(
                f"🚨 주문 호출 {len(not_done)}건이 {timeout:.0f}초 안에 끝나지 않음 — "
                f"종료 시 미체결 취소 대상에서 빠질 수 있다 · HTS 미체결 확인 필요"
            )
        return len(not_done)

    def _apply_buy_order_result(self, stock_code: str, strategy: Optional[str],
                                reason: str, order_id: Optional[str]) -> bool:
        """매수 주문 호출 결과를 슬롯에 반영 — 성공=주문ID 연결, 실패=원래 상태 복귀."""
        if order_id:
            with self.state_manager.lock:
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if trading_stock is not None:
                    trading_stock.add_order(order_id)

            self.logger.debug(f"{stock_code} 매수 주문 성공: {order_id}")
            return True
        else:
            # 주문 실패 시 원래 상태로 되돌림 (SELECTED 또는 COMPLETED)
            with self.state_manager.lock:
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if trading_stock is not None:
                    # 매수 진행 플래그 리셋
                    trading_stock.is_buying = False

                    # 원래 상태 추정: 재거래면 COMPLETED, 신규면 SELECTED
                    original_state = (
                        StockState.COMPLETED if "재거래" in reason else StockState.SELECTED
                    )
                    self.state_manager.change_stock_state(
                        stock_code, original_state, "매수 주문 실패",
                        strategy=trading_stock.owner_strategy_name
                    )
            return False

    def _finish_buy_order_after_cancel(self, task: 'asyncio.Future', stock_code: str,
                                       strategy: Optional[str], reason: str,
                                       owner_for_order: str) -> None:
        """(NEW-A1) 호출자가 취소된 뒤 끝난 매수 주문 호출의 결과로 슬롯·예약을 정리한다.

        성공 → 정상 경로와 같이 주문ID 연결(체결·타임아웃은 주문 모니터가 처리).
        실패 → 슬롯 원복 + 호출자(trading_analyzer)가 하던 예약 해제를 대신 한다.
        호출 자체가 취소됐으면(종료 중) 결과를 알 수 없으므로 BUY_PENDING 을 둔다 —
        섣불리 SELECTED 로 돌리면 이미 접수된 주문 위에 재매수가 날 수 있다.
        """
        try:
            if task.cancelled():
                self.logger.error(
                    f"🚨 {stock_code} 매수 주문 호출 자체가 취소됨 — 접수 여부 불명, "
                    f"슬롯 BUY_PENDING 유지(HTS·다음 기동 대사로 확인)"
                )
                return
            order_id = None if task.exception() is not None else task.result()
            ok = self._apply_buy_order_result(stock_code, strategy, reason, order_id)
            if not ok and self.fund_manager is not None:
                from ..fund_manager import make_reserve_id
                reserve_id = make_reserve_id(stock_code, owner_for_order)
                if self.fund_manager.has_reservation(reserve_id):
                    self.fund_manager.cancel_order(reserve_id)
            self.logger.warning(
                f"{stock_code} 취소 뒤 매수 주문 결과 반영: "
                f"{f'접수 {order_id} (체결은 주문 모니터가 추적)' if ok else '실패 → 슬롯·예약 복구'}"
            )
        except Exception as e:
            self.logger.error(f"{stock_code} 취소 뒤 매수 주문 정리 오류: {e}")

    def move_to_sell_candidate(self, stock_code: str, reason: str = "",
                               strategy: Optional[str] = None) -> bool:
        """
        포지션 종목을 매도 후보로 변경

        Args:
            stock_code: 종목코드
            reason: 변경 사유
            strategy: 소유 전략명. 지정 시 해당 전략 소유 인스턴스만 조회/변경
                      (다중소유 오귀속 방지). 미지정(None) 시 기존 폴백 동작 보존.

        Returns:
            bool: 변경 성공 여부
        """
        try:
            with self.state_manager.lock:
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if trading_stock is None:
                    self.logger.warning(f"{stock_code}: 관리 중이지 않은 종목")
                    return False

                # 상태 검증 (POSITIONED 또는 SELL_CANDIDATE에서 매도 시도 가능)
                if trading_stock.state not in [StockState.POSITIONED, StockState.SELL_CANDIDATE]:
                    self.logger.warning(
                        f"{stock_code}: 매도 가능 상태가 아님 (현재: {trading_stock.state.value})"
                    )
                    return False

                # 포지션 확인
                if not trading_stock.position:
                    self.logger.warning(f"{stock_code}: 포지션 정보 없음")
                    return False

                # 상태 변경
                self.state_manager.change_stock_state(
                    stock_code, StockState.SELL_CANDIDATE, reason,
                    strategy=trading_stock.owner_strategy_name
                )

                self.logger.info(f"{stock_code} 매도 후보로 변경: {reason}")
                return True

        except Exception as e:
            self.logger.error(f"{stock_code} 매도 후보 변경 오류: {e}")
            return False

    async def execute_sell_order(self, stock_code: str, quantity: int,
                                 price: float, reason: str = "", market: bool = False,
                                 force: bool = False,
                                 strategy: Optional[str] = None) -> bool:
        """
        매도 주문 실행

        Args:
            stock_code: 종목코드
            quantity: 주문 수량
            price: 주문 가격
            reason: 매도 사유
            market: 시장가 주문 여부
            force: True이면 시간대 검사를 건너뜀 (EOD 청산 등)
            strategy: 소유 전략명. 지정 시 해당 전략 소유 인스턴스만 조회/변경
                      (다중소유 오귀속 방지). 미지정(None) 시 기존 폴백 동작 보존.

        Returns:
            bool: 주문 성공 여부
        """
        try:
            with self.state_manager.lock:
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if trading_stock is None:
                    self.logger.warning(f"{stock_code}: 관리 중이지 않은 종목")
                    return False

                # 상태 검증
                if trading_stock.state != StockState.SELL_CANDIDATE:
                    self.logger.warning(
                        f"{stock_code}: 매도 후보 상태가 아님 (현재: {trading_stock.state.value})"
                    )
                    return False

                # is_selling 설정 (매도 주문 진입점)
                # - 성공 시: order_completion_handler에서 해제 (체결/취소/실패)
                # - API 실패 시: 아래 except 블록에서 즉시 해제
                # - 타임아웃 시: handle_order_timeout에서 해제
                trading_stock.is_selling = True

                # 주문에 실을 owner 표기는 **슬롯 객체**에서 읽는다(표기-불변).
                _owner_for_order = trading_stock.owner_strategy_name or ""

                # 매도 주문 중 상태로 변경
                self.state_manager.change_stock_state(
                    stock_code, StockState.SELL_PENDING, f"매도 주문: {reason}",
                    strategy=trading_stock.owner_strategy_name
                )

            # 매도 주문 실행 — NEW-A1: 매수와 같이 주문 호출은 shield 로 보호한다
            # (취소돼도 끝까지 가서 등록 · 결과 정리는 _finish_sell_order_after_cancel).
            place_task = asyncio.ensure_future(self.order_manager.place_sell_order(
                stock_code, quantity, price, market=market, force=force,
                owner_strategy=_owner_for_order
            ))
            self._track_inflight(place_task)
            try:
                order_id = await asyncio.shield(place_task)
            except asyncio.CancelledError:
                self.logger.error(
                    f"🚨 {stock_code} 매도 주문 대기 중 취소됨 — 주문 호출은 끝까지 진행하고 "
                    f"결과로 슬롯을 정리한다(NEW-A1)"
                )
                place_task.add_done_callback(
                    lambda t: self._finish_sell_order_after_cancel(t, stock_code, strategy))
                raise

            return self._apply_sell_order_result(stock_code, strategy, order_id)

        except Exception as e:
            self.logger.error(f"{stock_code} 매도 주문 오류: {e}")
            # 오류 시 매도 후보로 되돌림 + is_selling 즉시 해제
            with self.state_manager.lock:
                _ts = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if _ts is not None:
                    _ts.is_selling = False
                    self.state_manager.change_stock_state(
                        stock_code, StockState.SELL_CANDIDATE, f"매도 주문 오류: {e}",
                        strategy=_ts.owner_strategy_name
                    )
            return False

    def _apply_sell_order_result(self, stock_code: str, strategy: Optional[str],
                                 order_id: Optional[str]) -> bool:
        """매도 주문 호출 결과를 슬롯에 반영 — 성공=주문ID 연결, 실패=매도 후보 복귀·is_selling 해제."""
        if order_id:
            with self.state_manager.lock:
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if trading_stock is not None:
                    trading_stock.add_order(order_id)

            self.logger.info(f"{stock_code} 매도 주문 성공: {order_id}")
            return True
        else:
            # 주문 실패 시 매도 후보로 되돌림 + is_selling 즉시 해제
            with self.state_manager.lock:
                _ts = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if _ts is not None:
                    _ts.is_selling = False
                self.state_manager.change_stock_state(
                    stock_code, StockState.SELL_CANDIDATE, "매도 주문 실패",
                    strategy=_ts.owner_strategy_name if _ts is not None else None
                )
            return False

    def _finish_sell_order_after_cancel(self, task: 'asyncio.Future', stock_code: str,
                                        strategy: Optional[str]) -> None:
        """(NEW-A1) 호출자가 취소된 뒤 끝난 매도 주문 호출의 결과로 슬롯을 정리한다.

        실패면 호출자(execute_real_sell)가 하던 POSITIONED 복원까지 대신 해서 손절
        감시(position_monitor 는 POSITIONED 만 본다)가 다시 잡게 한다. 호출 자체가
        취소됐으면(종료 중) 접수 여부를 모르므로 SELL_PENDING 을 둔다.
        """
        try:
            if task.cancelled():
                self.logger.error(
                    f"🚨 {stock_code} 매도 주문 호출 자체가 취소됨 — 접수 여부 불명, "
                    f"슬롯 SELL_PENDING 유지(HTS·다음 기동 대사로 확인)"
                )
                return
            order_id = None if task.exception() is not None else task.result()
            ok = self._apply_sell_order_result(stock_code, strategy, order_id)
            if not ok:
                with self.state_manager.lock:
                    _ts = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                    if _ts is not None and _ts.state == StockState.SELL_CANDIDATE:
                        self.state_manager.change_stock_state(
                            stock_code, StockState.POSITIONED, "매도 주문 실패(취소 뒤 정리)",
                            strategy=_ts.owner_strategy_name
                        )
            self.logger.warning(
                f"{stock_code} 취소 뒤 매도 주문 결과 반영: "
                f"{f'접수 {order_id} (체결은 주문 모니터가 추적)' if ok else '실패 → POSITIONED 복원'}"
            )
        except Exception as e:
            self.logger.error(f"{stock_code} 취소 뒤 매도 주문 정리 오류: {e}")

    def remove_stock(self, stock_code: str, reason: str = "",
                     strategy: Optional[str] = None) -> bool:
        """
        종목 제거

        Args:
            stock_code: 종목코드
            reason: 제거 사유
            strategy: 소유 전략명. 지정 시 해당 전략 소유 인스턴스만 조회/변경
                      (다중소유 오귀속 방지). 미지정(None) 시 기존 폴백 동작 보존.

        Returns:
            bool: 제거 성공 여부
        """
        try:
            with self.state_manager.lock:
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if trading_stock is None:
                    return False

                # 상태 변경 후 제거
                self.state_manager.change_stock_state(
                    stock_code, StockState.COMPLETED, f"제거: {reason}",
                    strategy=trading_stock.owner_strategy_name
                )

                # 관련 관리자에서도 제거
                self.intraday_manager.remove_stock(stock_code)
                self.data_collector.remove_candidate_stock(stock_code)

                self.logger.info(f"{stock_code} 거래 관리에서 제거: {reason}")
                return True

        except Exception as e:
            self.logger.error(f"{stock_code} 제거 오류: {e}")
            return False

    async def handle_order_timeout(self, order, strategy: Optional[str] = None) -> None:
        """
        OrderManager에서 타임아웃/취소된 주문 처리

        BUY_PENDING 상태인 종목을 다시 매수 가능한 상태로 복구합니다.

        Args:
            order: 타임아웃된 주문 객체 (Order)
            strategy: 소유 전략명. 지정 시 해당 전략 소유 인스턴스만 조회/변경
                      (다중소유 오귀속 방지). 미지정(None) 시 기존 폴백 동작 보존.
        """
        try:
            stock_code = order.stock_code

            with self.state_manager.lock:
                trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
                if trading_stock is None:
                    self.logger.warning(f"타임아웃 처리할 종목 없음: {stock_code}")
                    return

                # BUY_PENDING 상태인 경우 처리
                if trading_stock.state == StockState.BUY_PENDING:
                    # 매수 진행 플래그 해제
                    trading_stock.is_buying = False
                    trading_stock.current_order_id = None
                    trading_stock.order_processed = False

                    # 재거래가 활성화된 경우 COMPLETED로, 비활성화된 경우 SELECTED로 복구
                    if self.enable_re_trading:
                        self.state_manager.change_stock_state(
                            stock_code, StockState.COMPLETED,
                            "주문 타임아웃 복구 (재거래 가능)",
                            strategy=trading_stock.owner_strategy_name
                        )
                        self.logger.info(
                            f"{stock_code} 타임아웃 복구 완료: BUY_PENDING -> COMPLETED (재거래 가능)"
                        )
                    else:
                        self.state_manager.change_stock_state(
                            stock_code, StockState.SELECTED,
                            "주문 타임아웃 복구",
                            strategy=trading_stock.owner_strategy_name
                        )
                        self.logger.info(
                            f"{stock_code} 타임아웃 복구 완료: BUY_PENDING -> SELECTED (매수 재시도 가능)"
                        )

                # SELL_PENDING 상태인 경우 POSITIONED로 복원하여 재매도 가능하게
                elif trading_stock.state == StockState.SELL_PENDING:
                    trading_stock.current_order_id = None
                    trading_stock.order_processed = False
                    # is_selling 해제 (매도 타임아웃 경로 - 재매도 가능하게)
                    trading_stock.is_selling = False

                    # 매도 타임아웃 복원 후 즉시 재매도 방지 (10초 쿨다운)
                    trading_stock.last_sell_timeout_time = now_kst()

                    self.state_manager.change_stock_state(
                        stock_code, StockState.POSITIONED,
                        "매도 주문 타임아웃 복구 (10초 후 재매도 가능)",
                        strategy=trading_stock.owner_strategy_name
                    )
                    self.logger.info(
                        f"{stock_code} 타임아웃 복구 완료: SELL_PENDING -> POSITIONED (재매도 가능)"
                    )

                else:
                    self.logger.warning(
                        f"{stock_code} 예상치 못한 상태에서 타임아웃 처리: "
                        f"{trading_stock.state.value}"
                    )
                    return

        except Exception as e:
            self.logger.error(
                f"{order.stock_code if hasattr(order, 'stock_code') else 'Unknown'} "
                f"타임아웃 처리 오류: {e}"
            )

    async def on_partial_fill_timeout(self, order, filled_qty: int, filled_price: float,
                                      strategy: Optional[str] = None) -> Optional[TradingStock]:
        """
        부분 체결 타임아웃 처리 - 체결된 수량으로 포지션 설정

        Args:
            order: 부분 체결된 주문 객체 (Order)
            filled_qty: 체결된 수량
            filled_price: 체결 가격
            strategy: 소유 전략명. 지정 시 해당 전략 소유 인스턴스만 조회/변경
                      (다중소유 오귀속 방지). 미지정(None) 시 기존 폴백 동작 보존.

        Returns:
            POSITIONED 로 등록한 슬롯(전략 통보용 — facade 가 소유 전략에 체결을
            알린다, F5). 슬롯을 못 찾으면 None.
        """
        stock_code = order.stock_code

        with self.state_manager.lock:
            trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
            if trading_stock is None:
                self.logger.warning(f"부분 체결 포지션 등록 실패: {stock_code} 종목 없음")
                return None

            trading_stock.is_buying = False
            trading_stock.set_position(filled_qty, filled_price)
            trading_stock.clear_current_order()
            trading_stock.set_buy_time(now_kst())

            self.state_manager.change_stock_state(
                stock_code, StockState.POSITIONED,
                f"부분 체결 타임아웃: {filled_qty}주 @{filled_price:,.0f}원",
                strategy=trading_stock.owner_strategy_name
            )

        self.logger.info(f"부분 체결 포지션 등록 완료: {stock_code} {filled_qty}주 @{filled_price:,.0f}원")
        return trading_stock

    async def on_sell_partial_fill_timeout(self, order, filled_qty: int, filled_price: float,
                                           strategy: Optional[str] = None) -> None:
        """
        매도 부분 체결 타임아웃 처리 - 체결된 수량 반영, 잔량은 POSITIONED로 복구

        Args:
            order: 부분 체결된 매도 주문 객체 (Order)
            filled_qty: 체결된 수량
            filled_price: 체결 가격
            strategy: 소유 전략명. 지정 시 해당 전략 소유 인스턴스만 조회/변경
                      (다중소유 오귀속 방지). 미지정(None) 시 기존 폴백 동작 보존.
        """
        stock_code = order.stock_code

        with self.state_manager.lock:
            trading_stock = self.state_manager.get_trading_stock(stock_code, strategy=strategy)
            if trading_stock is None:
                self.logger.warning(f"매도 부분 체결 처리 실패: {stock_code} 종목 없음")
                return

            # is_selling 해제 (매도 부분 체결 타임아웃 경로)
            trading_stock.is_selling = False
            trading_stock.clear_current_order()

            # 기존 포지션 수량에서 체결 수량을 차감
            if trading_stock.position:
                remaining_qty = trading_stock.position.quantity - filled_qty
                if remaining_qty > 0:
                    # 잔량이 있으면 포지션 업데이트 후 POSITIONED로 복구 (재매도 가능)
                    trading_stock.position.quantity = remaining_qty
                    self.state_manager.change_stock_state(
                        stock_code, StockState.POSITIONED,
                        f"매도 부분 체결 타임아웃: {filled_qty}주 매도, {remaining_qty}주 잔량",
                        strategy=trading_stock.owner_strategy_name
                    )
                    self.logger.info(
                        f"{stock_code} 매도 부분 체결: {filled_qty}주 @{filled_price:,.0f}원, "
                        f"잔량 {remaining_qty}주 (재매도 대기)"
                    )
                else:
                    # 전량 매도 완료
                    trading_stock.clear_position()
                    self.state_manager.change_stock_state(
                        stock_code, StockState.COMPLETED,
                        f"매도 부분 체결 완료: {filled_qty}주 @{filled_price:,.0f}원",
                        strategy=trading_stock.owner_strategy_name
                    )
                    self.logger.info(
                        f"{stock_code} 매도 부분 체결 전량 완료: {filled_qty}주 @{filled_price:,.0f}원"
                    )
            else:
                # 포지션 정보 없으면 COMPLETED로
                self.state_manager.change_stock_state(
                    stock_code, StockState.COMPLETED,
                    f"매도 부분 체결 완료 (포지션 없음): {filled_qty}주",
                    strategy=trading_stock.owner_strategy_name
                )
                self.logger.warning(
                    f"{stock_code} 매도 부분 체결: 포지션 정보 없음 ({filled_qty}주 체결)"
                )

    def set_re_trading_config(self, enable: bool) -> None:
        """
        재거래 설정 변경

        Args:
            enable: 재거래 활성화 여부 (COMPLETED 상태에서 직접 매수 판단)
        """
        self.enable_re_trading = enable

        status = "활성화" if enable else "비활성화"
        self.logger.info(f"재거래 설정 변경: {status} (즉시 재거래 방식)")

    def get_re_trading_config(self) -> dict:
        """재거래 설정 조회"""
        return {
            "enable_re_trading": self.enable_re_trading
        }
