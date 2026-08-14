"""
주문 체결 처리 모듈

매수/매도 주문의 체결 확인 및 후속 처리
"""
from typing import Any, TYPE_CHECKING
import pandas as pd

from ..models import TradingStock, StockState, OrderStatus, OrderType
from utils.logger import setup_logger
from utils.korean_time import now_kst
from strategies.base import OrderInfo

if TYPE_CHECKING:
    from .stock_state_manager import StockStateManager
    from ..order_manager import OrderManager


class OrderCompletionHandler:
    """
    주문 체결 처리자

    주요 기능:
    1. 매수 주문 체결 확인
    2. 매도 주문 체결 확인
    3. 체결 콜백 처리
    """

    def __init__(self, state_manager: 'StockStateManager',
                 order_manager: 'OrderManager') -> None:
        """
        초기화

        Args:
            state_manager: 종목 상태 관리자
            order_manager: 주문 관리자
        """
        self.state_manager = state_manager
        self.order_manager = order_manager
        self.logger = setup_logger(__name__)

        # 재거래 설정 (외부에서 설정됨)
        self.enable_re_trading = True

        # 전략 콜백 연결 (외부에서 set_strategy로 설정)
        self.strategy = None
        # 다중전략 맵 (폴더키 → 전략 인스턴스). 실매매 체결을 소유 전략으로 라우팅.
        self.strategies_by_key: dict = {}

    def set_strategy(self, strategy: Any) -> None:
        """전략 연결 (on_order_filled 콜백용)"""
        self.strategy = strategy
        if strategy:
            self.logger.info(f"OrderCompletionHandler에 전략 연결: {strategy.name}")

    def set_strategies(self, strategies_by_key: dict) -> None:
        """다중전략 맵 연결 — 실매매 체결 콜백을 소유 전략으로 라우팅.

        고정 self.strategy 통보는 전 전략 체결이 첫 전략(Elder)의
        daily_trades/positions를 오염시켜 매수 마비를 일으켰다(2026-06-11 진단).
        실매매 완료 핸들러에도 owner-aware 라우팅을 적용한다
        (사전-실전 감사 BLOCKER #2, 2026-06-24).
        """
        self.strategies_by_key = strategies_by_key or {}
        if self.strategies_by_key:
            self.logger.info(
                f"OrderCompletionHandler에 {len(self.strategies_by_key)}개 전략 맵 연결"
            )

    def _owner_aliases(self, owner_name) -> list:
        """owner 표기의 동치 후보(폴더키 ↔ 클래스명)를 순서대로 반환.

        같은 전략이 경로에 따라 폴더키('rs_leader')로도 클래스명
        ('RSLeaderStrategy')으로도 표기된다(trading_context:529 는 클래스명,
        DB 복원은 폴더키). 어느 표기로 들어와도 같은 슬롯을 찾게 한다.
        """
        if not owner_name:
            return []
        aliases = [owner_name]
        strat = self.strategies_by_key.get(owner_name)
        if strat is not None:
            cls_name = getattr(strat, 'name', None)
            if cls_name and cls_name != owner_name:
                aliases.append(cls_name)
        else:
            for key, s in self.strategies_by_key.items():
                if getattr(s, 'name', None) == owner_name and key != owner_name:
                    aliases.append(key)
                    break
        return aliases

    def _find_owned_stock(self, stock_code: str, owner_name):
        """주문 owner 로 소유 슬롯을 찾는다 (폴더키/클래스명 양쪽 허용).

        owner 를 지정했는데 그 슬롯이 없고 **다른 소유자가 2명 이상**이면
        None 을 돌려준다 — 남의 슬롯을 집으면 안 된다(2026-08-14 리뷰 F2).

        ⚠️ 종전 구현은 무조건 종목코드 단독 폴백이라 «다른 소유자의» 슬롯을
        돌려줬고, 그 결과 매도 체결이 **남의 보유 엔트리를 지웠다**(소유권
        역전: 그쪽 can_add_position 슬롯이 풀려 중복매수에 노출되고, 진짜
        소유자의 유령 엔트리는 세션 내내 슬롯을 점유). 매수원가도 남의
        평단에서 읽혔다. 베이스라인은 owner 미지정 제거였고 fund_manager 의
        [모호제거] 가드가 «보류» 했다 — 안전한 무동작을 위험한 오동작으로
        바꾼 셈이라 되돌린다. 모호하면 가드가 일하게 둔다.

        소유자가 하나뿐이면 표기가 어긋나도 모호하지 않으므로 종전 폴백 유지.
        """
        for key in self._owner_aliases(owner_name):
            ts = self.state_manager.get_trading_stock(stock_code, strategy=key)
            if ts is not None:
                return ts

        if owner_name:
            with self.state_manager.lock:
                others = self.state_manager._find_by_code(stock_code)
            if len(others) > 1:
                self.logger.error(
                    f"[{stock_code}] 주문 owner={owner_name!r} 슬롯 미발견 + "
                    f"다중소유({len(others)}) — 남의 슬롯을 집지 않고 보류한다 "
                    f"(보유 owner: {[o.owner_strategy_name for o in others]})"
                )
                return None

        ts = self.state_manager.get_trading_stock(stock_code)
        if ts is not None and owner_name:
            self.logger.warning(
                f"[{stock_code}] 주문 owner={owner_name!r} 슬롯 미발견 — "
                f"단일 소유라 종목코드 단독 폴백"
            )
        return ts

    def _strategy_by_class_name(self, name):
        """클래스명(strategy.name)으로 전략 인스턴스 조회 (보조 매핑).

        ⚠️ 캐시하지 않는다. main.py:234-235 가 on_init 실패 전략을 dict 에서
        **삭제**하는데 캐시는 그 변경을 못 본다 — 폴더키로는 None(올바름)인데
        클래스명으로는 «삭제된 인스턴스»가 나오고, 그 상태로
        apply_pending_strategy_positions 가 포지션을 주입하면 on_tick 을 영영
        못 받을 전략이 포지션을 갖는다(2026-08-14 리뷰 항목 6).
        맵은 8개짜리라 매번 만들어도 비용이 없다.
        """
        for s in self.strategies_by_key.values():
            if getattr(s, 'name', None) == name:
                return s
        return None

    def _resolve_owner_strategy(self, owner_name=None, owner_strategy=None):
        """체결을 통보할 소유 전략 인스턴스를 해석한다.

        전략 정체성 표기는 서로 바꿔 쓸 수 없는 세 키로 갈린다 —
        폴더키('rs_leader') / 클래스명('RSLeaderStrategy') / None. 해석 순서:

          0. owner_strategy — trading_stock 에 바인딩된 **인스턴스**
             (trading_context:530). 이름을 거치지 않으므로 표기 분열에 무관.
          1. strategies_by_key[owner_name] — 폴더키
          2. 클래스명 보조 매핑 (bot/state_restorer._resolve_owner_strategy 와 동일 2단)

        ⚠️ 종전 구현은 1단(폴더키)만 있었는데, 라이브 매수는
        trading_context:529 가 owner 를 **클래스명**으로 써 넣어 항상 miss →
        조용히 self.strategy(=config 첫 전략)로 폴백했다. 2전략 실매매에서
        그 폴백은 «첫 전략이 유령 포지션을 받고 진짜 owner 는 보유 사실을
        모른다» = 자기 전략 청산(trail/max_hold/trend_flip)이 영영 미발동
        (2026-08-14 실매매 전환 감사 Fix 1).

        미해석 시 self.strategy 폴백은 **전략이 1개 이하일 때만** 허용한다.
        다전략에서 추측은 오귀속이고, 오귀속은 무통보보다 나쁘다.
        """
        if owner_strategy is not None:
            return owner_strategy
        if self.strategies_by_key:
            if owner_name:
                target = self.strategies_by_key.get(owner_name)
                if target is not None:
                    return target
                target = self._strategy_by_class_name(owner_name)
                if target is not None:
                    return target
                self.logger.error(
                    f"[체결 owner 미해석] owner={owner_name!r} — 폴더키·클래스명 모두 불일치 "
                    f"(등록 전략: {list(self.strategies_by_key.keys())})"
                )
            else:
                # 무기명 체결. 종전에는 `if owner_name and ...` 가 이 블록 전체를
                # 감싸고 있어 «ERROR 한 줄 없이» self.strategy 로 떨어졌다 —
                # 다전략에서는 그게 곧 조용한 오귀속이다(2026-08-14 리뷰 R4).
                # 도달 경로: 복원 슬롯은 owner_strategy_name 만 세팅하고
                # owner_strategy(인스턴스)는 세팅하지 않으므로, DB 라벨이 공백인
                # 행이 이름도 인스턴스도 없이 여기로 온다.
                self.logger.error(
                    f"[체결 owner 미지정] 소유 전략 표기가 비어 있다 "
                    f"(등록 전략: {list(self.strategies_by_key.keys())})"
                )
            if len(self.strategies_by_key) > 1:
                return None
        return self.strategy

    def _notify_strategy_order_filled(self, order, owner_name=None,
                                      owner_strategy=None) -> None:
        """전략의 on_order_filled 콜백 호출 (소유 전략으로 라우팅)"""
        try:
            target = self._resolve_owner_strategy(owner_name, owner_strategy)
            if target and hasattr(target, 'on_order_filled'):
                # OrderInfo 객체로 변환하여 전달 (strategy.on_order_filled는 OrderInfo를 기대)
                order_type = order.order_type
                if hasattr(order_type, 'value'):
                    side = order_type.value  # "buy" or "sell"
                else:
                    side = str(order_type).lower()
                order_info = OrderInfo(
                    order_id=str(order.order_id),
                    stock_code=order.stock_code,
                    side=side,
                    quantity=int(order.quantity),
                    price=float(order.get_filled_price()),
                    filled_at=now_kst(),
                )
                target.on_order_filled(order_info)
                self.logger.debug(f"전략 on_order_filled 콜백 호출: {order.stock_code}")
        except Exception as e:
            self.logger.warning(f"전략 on_order_filled 콜백 오류: {e}")

    async def check_order_completions(self) -> None:
        """주문 완료 확인 및 상태 업데이트"""
        try:
            # 매수 주문 중인 종목들 확인
            buy_pending_stocks = list(
                self.state_manager.stocks_by_state[StockState.BUY_PENDING].values()
            )
            for trading_stock in buy_pending_stocks:
                await self._check_buy_order_completion(trading_stock)

            # 매도 주문 중인 종목들 확인
            sell_pending_stocks = list(
                self.state_manager.stocks_by_state[StockState.SELL_PENDING].values()
            )
            for trading_stock in sell_pending_stocks:
                await self._check_sell_order_completion(trading_stock)

        except Exception as e:
            self.logger.error(f"주문 완료 확인 오류: {e}")

    async def _check_buy_order_completion(self, trading_stock: TradingStock) -> None:
        """매수 주문 완료 확인"""
        try:
            if not trading_stock.current_order_id:
                return

            # 주문 관리자에서 완료된 주문 확인
            completed_orders = self.order_manager.get_completed_orders()

            for order in completed_orders:
                if (order.order_id == trading_stock.current_order_id and
                        order.stock_code == trading_stock.stock_code):

                    if order.status == OrderStatus.FILLED:
                        # 매수 완료 - 포지션 상태로 변경
                        with self.state_manager.lock:
                            trading_stock.set_position(order.quantity, order.get_filled_price())
                            trading_stock.clear_current_order()
                            # 매수 시간 기록
                            trading_stock.set_buy_time(now_kst())

                            # 가상매매 모드일 때 가상매매 기록 ID 설정
                            self._set_virtual_buy_info(trading_stock)

                            self.state_manager.change_stock_state(
                                trading_stock.stock_code,
                                StockState.POSITIONED,
                                f"매수 완료: {order.quantity}주 @{order.get_filled_price():,.0f}원",
                                strategy=trading_stock.owner_strategy_name,
                            )

                        # 실거래 매수 기록은 OrderMonitor._handle_full_fill()에서 저장 (중복 방지)

                        # 전략 콜백 호출
                        self._notify_strategy_order_filled(
                            order, trading_stock.owner_strategy_name,
                            owner_strategy=trading_stock.owner_strategy,
                        )

                        self.logger.info(f"{trading_stock.stock_code} 매수 완료")

                    elif order.status in [OrderStatus.CANCELLED, OrderStatus.FAILED]:
                        # 매수 실패 - 매수 후보로 되돌림
                        with self.state_manager.lock:
                            trading_stock.is_buying = False
                            trading_stock.clear_current_order()
                            # 매수 실패 시 원래 상태로 복귀
                            original_state = (
                                StockState.COMPLETED
                                if "재거래" in trading_stock.selection_reason
                                else StockState.SELECTED
                            )
                            self.state_manager.change_stock_state(
                                trading_stock.stock_code,
                                original_state,
                                f"매수 실패: {order.status.value}",
                                strategy=trading_stock.owner_strategy_name,
                            )

                    break

        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매수 주문 완료 확인 오류: {e}")

    async def _check_sell_order_completion(self, trading_stock: TradingStock) -> None:
        """매도 주문 완료 확인"""
        try:
            if not trading_stock.current_order_id:
                return

            # 주문 관리자에서 완료된 주문 확인
            completed_orders = self.order_manager.get_completed_orders()
            for order in completed_orders:
                if (order.order_id == trading_stock.current_order_id and
                        order.stock_code == trading_stock.stock_code):

                    if order.status == OrderStatus.FILLED:
                        # 매도 완료 - 완료 상태로 변경
                        with self.state_manager.lock:
                            # is_selling 해제 (매도 성공 정상 경로)
                            trading_stock.is_selling = False
                            # 수익률 계산을 위해 포지션 정보 먼저 저장
                            _buy_price = trading_stock.position.avg_price if trading_stock.position else 0
                            trading_stock.clear_position()
                            trading_stock.clear_current_order()
                            self.state_manager.change_stock_state(
                                trading_stock.stock_code,
                                StockState.COMPLETED,
                                f"매도 완료: {order.quantity}주 @{order.get_filled_price():,.0f}원",
                                strategy=trading_stock.owner_strategy_name,
                            )

                        # 실거래 매도 기록은 OrderMonitor._handle_full_fill()에서 저장 (중복 방지)
                        # 수익률 계산만 수행
                        profit_rate = 0.0
                        if _buy_price and _buy_price > 0:
                            profit_rate = ((float(order.get_filled_price()) - _buy_price) / _buy_price) * 100

                        # 전략 콜백 호출
                        self._notify_strategy_order_filled(
                            order, trading_stock.owner_strategy_name,
                            owner_strategy=trading_stock.owner_strategy,
                        )

                        self.logger.info(
                            f"{trading_stock.stock_code} 매도 완료 (수익률: {profit_rate:.2f}%)"
                        )

                        # 매도 완료 후 즉시 재거래 준비 (COMPLETED 상태 유지)
                        if self.enable_re_trading:
                            self.logger.debug(
                                f"{trading_stock.stock_code} 즉시 재거래 준비 완료 "
                                "(COMPLETED 상태 유지)"
                            )

                    elif order.status in [OrderStatus.CANCELLED, OrderStatus.FAILED]:
                        # 매도 실패 - 포지션 보유 상태로 되돌림
                        with self.state_manager.lock:
                            # is_selling 해제 (매도 취소/실패 정상 경로)
                            trading_stock.is_selling = False
                            trading_stock.clear_current_order()
                            self.state_manager.change_stock_state(
                                trading_stock.stock_code,
                                StockState.POSITIONED,
                                f"매도 실패: {order.status.value}",
                                strategy=trading_stock.owner_strategy_name,
                            )

                    break

        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매도 주문 완료 확인 오류: {e}")

    async def on_order_filled(self, order) -> None:
        """주문 체결 시 즉시 호출되는 콜백 메서드"""
        try:
            with self.state_manager.lock:
                # 복합키 전환(df32514): trading_stocks 키가 (owner, code)이므로
                # 종목 코드 단독 조회는 임의 소유자를 집는다. 주문이 싣고 온
                # owner 표기로 소유 슬롯을 먼저 찾는다(2026-08-14 Fix 2).
                trading_stock = self._find_owned_stock(
                    order.stock_code, getattr(order, 'owner_strategy', '')
                )
                if trading_stock is None:
                    self.logger.warning(f"체결 콜백: 관리되지 않는 종목 {order.stock_code}")
                    return

                # 추가: 이미 POSITIONED 상태라면 중복 처리 방지
                if (order.order_type == OrderType.BUY and
                        trading_stock.state == StockState.POSITIONED):
                    self.logger.debug(
                        f"중복 체결 콜백 무시: {order.order_id} ({order.stock_code}) "
                        f"- 이미 POSITIONED 상태"
                    )
                    return

                # 레이스 컨디션 방지: 이미 처리된 주문인지 확인
                if trading_stock.order_processed:
                    self.logger.debug(
                        f"중복 체결 콜백 무시: {order.order_id} ({order.stock_code}) "
                        f"- 이미 처리 완료"
                    )
                    return

                # 첫 번째 콜백만 INFO로 기록
                self.logger.info(
                    f"주문 체결 콜백 수신: {order.order_id} - {order.stock_code} "
                    f"({order.order_type.value})"
                )

                if order.order_type == OrderType.BUY:
                    self._process_buy_fill_callback(trading_stock, order)
                elif order.order_type == OrderType.SELL:
                    self._process_sell_fill_callback(trading_stock, order)

        except Exception as e:
            self.logger.error(f"주문 체결 콜백 처리 오류: {e}")

    def _process_buy_fill_callback(self, trading_stock: TradingStock, order) -> None:
        """매수 체결 콜백 처리"""
        if trading_stock.state == StockState.BUY_PENDING:
            # 체결 처리 플래그 설정
            trading_stock.order_processed = True
            trading_stock.is_buying = False  # 매수 완료

            trading_stock.set_position(order.quantity, order.get_filled_price())
            trading_stock.clear_current_order()
            # 매수 시간 기록 (콜백)
            trading_stock.set_buy_time(now_kst())

            # 가상매매 모드일 때 가상매매 기록 ID 설정
            self._set_virtual_buy_info(trading_stock)

            self.state_manager.change_stock_state(
                trading_stock.stock_code,
                StockState.POSITIONED,
                f"매수 체결 (콜백): {order.quantity}주 @{order.get_filled_price():,.0f}원",
                strategy=trading_stock.owner_strategy_name,
            )

            # 실거래 매수 기록은 OrderMonitor._handle_full_fill()에서 저장 (중복 방지)

            # 전략 콜백 호출
            self._notify_strategy_order_filled(
                order, trading_stock.owner_strategy_name,
                owner_strategy=trading_stock.owner_strategy,
            )

            self.logger.debug(f"매수 체결 처리 완료 (콜백): {trading_stock.stock_code}")
        else:
            self.logger.warning(
                f"예상치 못한 상태에서 매수 체결: {trading_stock.state.value}"
            )

    def _process_sell_fill_callback(self, trading_stock: TradingStock, order) -> None:
        """매도 체결 콜백 처리"""
        if trading_stock.state == StockState.SELL_PENDING:
            # 체결 처리 플래그 설정
            trading_stock.order_processed = True
            # is_selling 해제 (매도 체결 콜백 정상 경로)
            trading_stock.is_selling = False

            # 수익률 계산을 위해 포지션 정보 먼저 저장
            _buy_price = trading_stock.position.avg_price if trading_stock.position else 0
            trading_stock.clear_position()
            trading_stock.clear_current_order()
            self.state_manager.change_stock_state(
                trading_stock.stock_code,
                StockState.COMPLETED,
                f"매도 체결 (콜백): {order.quantity}주 @{order.get_filled_price():,.0f}원",
                strategy=trading_stock.owner_strategy_name,
            )

            # 실거래 매도 기록은 OrderMonitor._handle_full_fill()에서 저장 (중복 방지)
            # 수익률 계산만 수행
            profit_rate = 0.0
            if _buy_price and _buy_price > 0:
                profit_rate = ((float(order.get_filled_price()) - _buy_price) / _buy_price) * 100

            # 전략 콜백 호출
            self._notify_strategy_order_filled(
                order, trading_stock.owner_strategy_name,
                owner_strategy=trading_stock.owner_strategy,
            )

            self.logger.debug(
                f"매도 체결 처리 완료 (콜백): {trading_stock.stock_code} "
                f"(수익률: {profit_rate:.2f}%)"
            )

            # 매도 완료 후 즉시 재거래 준비 (COMPLETED 상태 유지)
            if self.enable_re_trading:
                self.logger.debug(
                    f"{trading_stock.stock_code} 즉시 재거래 준비 완료 (COMPLETED 상태 유지)"
                )
        else:
            self.logger.warning(
                f"예상치 못한 상태에서 매도 체결: {trading_stock.state.value}"
            )

    def _set_virtual_buy_info(self, trading_stock: TradingStock) -> None:
        """가상매매 모드일 때 가상매매 기록 ID 설정"""
        try:
            config = self.order_manager.config
            if getattr(config, 'paper_trading', False):
                db = self.order_manager.db_manager
                if not db:
                    self.logger.warning("가상매매 포지션 정보 설정 실패: db_manager 없음")
                    return
                # 최근 가상매매 매수 기록 조회
                open_positions = db.get_virtual_open_positions()
                stock_positions = open_positions[
                    open_positions['stock_code'] == trading_stock.stock_code
                ]
                if not stock_positions.empty:
                    latest_position = stock_positions.iloc[0]
                    buy_record_id = latest_position['id']
                    buy_price = latest_position['buy_price']
                    quantity = latest_position['quantity']
                    trading_stock.set_virtual_buy_info(buy_record_id, buy_price, quantity)

                    # 목표 익절/손절률 로드
                    if ('target_profit_rate' in latest_position and
                            pd.notna(latest_position['target_profit_rate'])):
                        trading_stock.target_profit_rate = float(
                            latest_position['target_profit_rate']
                        )
                    if ('stop_loss_rate' in latest_position and
                            pd.notna(latest_position['stop_loss_rate'])):
                        trading_stock.stop_loss_rate = float(
                            latest_position['stop_loss_rate']
                        )

                    self.logger.debug(
                        f"가상매매 포지션 정보 설정: {trading_stock.stock_code} "
                        f"ID={buy_record_id} "
                        f"(익절: {trading_stock.target_profit_rate*100:.1f}%, "
                        f"손절: {trading_stock.stop_loss_rate*100:.1f}%)"
                    )
        except Exception as virtual_err:
            self.logger.warning(f"가상매매 포지션 정보 설정 실패: {virtual_err}")

    def _get_strategy_name(self, trading_stock: TradingStock) -> str:
        """trading_stock에서 순수 전략 이름 추출 (DB strategy 컬럼용)

        우선순위:
        1. trading_stock.strategy_name (직접 설정된 전략명)
        2. self.strategy.name (연결된 전략 객체)
        3. "unknown" (최후 fallback)
        """
        # 1. trading_stock에 직접 설정된 전략명
        if trading_stock.strategy_name:
            return trading_stock.strategy_name
        # 2. 연결된 전략 객체의 name
        if self.strategy and hasattr(self.strategy, 'name') and self.strategy.name:
            return self.strategy.name
        # 3. fallback
        return "unknown"

    def _save_real_buy_record(self, trading_stock: TradingStock, order, source: str = "") -> None:
        """실거래 매수 기록 저장"""
        try:
            db = self.order_manager.db_manager
            if not db:
                self.logger.warning("실거래 매수 기록 저장 실패: db_manager 없음")
                return
            reason = "체결" if not source else f"체결({source})"
            db.save_real_buy(
                stock_code=trading_stock.stock_code,
                stock_name=trading_stock.stock_name,
                price=float(order.get_filled_price()),
                quantity=int(order.quantity),
                strategy=self._get_strategy_name(trading_stock),
                reason=reason
            )
        except Exception as db_err:
            self.logger.warning(f"실거래 매수 기록 저장 실패: {db_err}")

    def _save_real_sell_record(self, trading_stock: TradingStock, order,
                               source: str = "") -> float:
        """
        실거래 매도 기록 저장

        Returns:
            float: 수익률
        """
        profit_rate = 0.0
        try:
            db = self.order_manager.db_manager
            if not db:
                self.logger.warning("실거래 매도 기록 저장 실패: db_manager 없음")
                return profit_rate
            buy_id = db.get_last_open_real_buy(
                trading_stock.stock_code,
                trading_stock.owner_strategy_name or None)

            # 수익률 계산을 위해 매수가 조회
            buy_price = None
            if buy_id and trading_stock.position and trading_stock.position.avg_price:
                buy_price = trading_stock.position.avg_price
                profit_rate = ((float(order.get_filled_price()) - buy_price) / buy_price) * 100

            reason = "체결" if not source else f"체결({source})"
            db.save_real_sell(
                stock_code=trading_stock.stock_code,
                stock_name=trading_stock.stock_name,
                price=float(order.get_filled_price()),
                quantity=int(order.quantity),
                strategy=self._get_strategy_name(trading_stock),
                reason=reason,
                buy_record_id=buy_id
            )

        except Exception as db_err:
            self.logger.warning(f"실거래 매도 기록 저장 실패: {db_err}")

        return profit_rate
