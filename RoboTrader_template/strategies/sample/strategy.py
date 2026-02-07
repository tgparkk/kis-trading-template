"""
Sample Strategy
===============

샘플 전략 템플릿입니다.
이 파일을 복사하여 자신만의 전략을 구현하세요.

전략 라이프사이클:
1. __init__() - 전략 인스턴스 생성 (config 로드)
2. on_init() - 브로커/데이터/실행기 초기화 (1회)
3. on_market_open() - 장 시작 시 호출 (09:00)
4. generate_signal() - 주기적으로 매매 신호 생성
5. on_order_filled() - 주문 체결 시 호출
6. on_market_close() - 장 마감 시 호출 (15:30)
"""

from typing import Any, Dict, Optional

import pandas as pd

from ..base import BaseStrategy, OrderInfo, Signal, SignalType


class SampleStrategy(BaseStrategy):
    """
    샘플 전략 클래스

    이 클래스를 상속받아 자신만의 전략을 구현하세요.
    모든 추상 메서드를 반드시 구현해야 합니다.
    """

    # ========================================================================
    # 전략 메타 정보 (클래스 속성)
    # ========================================================================

    name: str = "SampleStrategy"
    version: str = "1.0.0"
    description: str = "샘플 전략 템플릿 - 자신만의 전략 구현을 위한 기본 골격"
    author: str = "Your Name"

    # ========================================================================
    # 추상 메서드 구현 (반드시 구현 필요)
    # ========================================================================

    def on_init(self, broker, data_provider, executor) -> bool:
        """
        전략 초기화

        브로커, 데이터 제공자, 주문 실행기를 받아서 전략을 초기화합니다.
        API 연결 후 1회만 호출됩니다.

        이 메서드에서 수행할 작업:
        - 컴포넌트 참조 저장 (broker, data_provider, executor)
        - 과거 데이터 로드 (필요시)
        - 기술적 지표 초기화 (이동평균, RSI 등)
        - 전략 상태 변수 초기화

        Args:
            broker: 브로커 인스턴스 (계좌 정보, 포지션 조회)
            data_provider: 데이터 제공자 (시세 데이터 조회)
            executor: 주문 실행기 (매수/매도 주문)

        Returns:
            bool: 초기화 성공 여부 (True: 성공, False: 실패)
        """
        # TODO: 프레임워크 컴포넌트 저장
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        # TODO: 전략 상태 변수 초기화
        # 예시:
        # self.positions = {}  # 보유 포지션 추적
        # self.daily_trades = 0  # 일일 거래 횟수
        # self.watchlist = []  # 감시 종목 리스트

        # TODO: 과거 데이터 로드 (필요시)
        # 예시:
        # self.historical_data = data_provider.get_daily_ohlcv("005930", days=60)

        # TODO: 기술적 지표 초기화
        # 예시:
        # self._calculate_indicators()

        self._is_initialized = True
        self.logger.info(f"{self.name} v{self.version} 초기화 완료")
        return True

    def on_market_open(self) -> None:
        """
        장 시작 시 호출 (09:00 KST)

        매일 장이 시작될 때 1회 호출됩니다.

        이 메서드에서 수행할 작업:
        - 야간 데이터 로드 및 분석
        - 일일 카운터 초기화 (거래 횟수 등)
        - 감시 종목 리스트 갱신
        - 당일 전략 파라미터 설정

        Returns:
            None
        """
        # TODO: 일일 상태 초기화
        # 예시:
        # self.daily_trades = 0
        # self.daily_profit = 0.0

        # TODO: 감시 종목 스캔
        # 예시:
        # self.watchlist = self._scan_candidates()

        # TODO: 당일 전략 파라미터 설정
        # 예시:
        # self._set_daily_parameters()

        self.logger.info(f"장 시작 - {self.name} 전략 활성화")

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> Optional[Signal]:
        """
        매매 신호 생성

        주기적으로 호출되어 특정 종목에 대한 매매 신호를 생성합니다.
        신호가 없으면 None을 반환합니다.

        이 메서드에서 수행할 작업:
        - 데이터 유효성 검증
        - 기술적 지표 계산
        - 매수/매도 조건 분석
        - Signal 객체 생성 및 반환

        Args:
            stock_code: 종목 코드 (6자리, 예: "005930")
            data: OHLCV 데이터프레임
                  컬럼: ['datetime', 'open', 'high', 'low', 'close', 'volume']

        Returns:
            Signal: 매매 신호 객체, 또는 None (신호 없음)
        """
        # TODO: 데이터 유효성 검증
        if data is None or len(data) < 20:  # 최소 20개 봉 필요
            return None

        # TODO: 매수 조건 분석
        buy_signal, buy_reasons = self._analyze_buy_condition(stock_code, data)
        if buy_signal:
            # 포지션 크기 계산
            position_size = self._calculate_position_size(stock_code, data)

            current_price = data['close'].iloc[-1]
            return Signal(
                signal_type=SignalType.BUY,
                stock_code=stock_code,
                confidence=75.0,  # TODO: 신뢰도 계산 로직 구현
                target_price=current_price * 1.10,  # TODO: 목표가 계산 로직 구현
                stop_loss=current_price * 0.95,  # TODO: 손절가 계산 로직 구현
                reasons=buy_reasons,
                metadata={
                    'position_size': position_size,
                    # TODO: 추가 메타데이터
                }
            )

        # TODO: 매도 조건 분석
        sell_signal, sell_reasons = self._analyze_sell_condition(stock_code, data)
        if sell_signal:
            return Signal(
                signal_type=SignalType.SELL,
                stock_code=stock_code,
                confidence=75.0,  # TODO: 신뢰도 계산 로직 구현
                reasons=sell_reasons,
                metadata={
                    # TODO: 추가 메타데이터
                }
            )

        return None

    def on_order_filled(self, order: OrderInfo) -> None:
        """
        주문 체결 시 호출

        매수 또는 매도 주문이 체결되었을 때 호출됩니다.

        이 메서드에서 수행할 작업:
        - 포지션 정보 업데이트
        - 거래 통계 기록
        - 로그 기록
        - 후속 조치 (예: 손절/익절 주문 설정)

        Args:
            order: 체결된 주문 정보 (OrderInfo 객체)
                   - order.stock_code: 종목 코드
                   - order.side: 'buy' 또는 'sell'
                   - order.quantity: 체결 수량
                   - order.price: 체결 가격
                   - order.filled_at: 체결 시간

        Returns:
            None
        """
        if order.is_buy:
            # TODO: 매수 체결 처리
            # 예시:
            # self.positions[order.stock_code] = {
            #     'quantity': order.quantity,
            #     'entry_price': order.price,
            #     'entry_time': order.filled_at
            # }
            self.logger.info(
                f"매수 체결: {order.stock_code} "
                f"{order.quantity}주 @ {order.price:,.0f}원"
            )
        else:
            # TODO: 매도 체결 처리
            # 예시:
            # if order.stock_code in self.positions:
            #     entry_price = self.positions[order.stock_code]['entry_price']
            #     profit_rate = (order.price - entry_price) / entry_price * 100
            #     self.logger.info(f"매도 수익률: {profit_rate:.2f}%")
            #     del self.positions[order.stock_code]
            self.logger.info(
                f"매도 체결: {order.stock_code} "
                f"{order.quantity}주 @ {order.price:,.0f}원"
            )

    def on_market_close(self) -> None:
        """
        장 마감 시 호출 (15:30 KST)

        매일 장이 마감될 때 1회 호출됩니다.

        이 메서드에서 수행할 작업:
        - 일일 거래 리포트 생성
        - 통계 저장 (수익률, 거래 횟수 등)
        - 임시 데이터 정리
        - 다음 거래일 준비

        Returns:
            None
        """
        # TODO: 일일 통계 기록
        # 예시:
        # self.logger.info(f"일일 거래 횟수: {self.daily_trades}")
        # self.logger.info(f"일일 수익: {self.daily_profit:,.0f}원")

        # TODO: 리포트 생성
        # 예시:
        # self._generate_daily_report()

        # TODO: 임시 데이터 정리
        # 예시:
        # self._cleanup_temp_data()

        self.logger.info(f"장 마감 - {self.name} 전략 비활성화")

    # ========================================================================
    # 헬퍼 메서드 (전략 로직 구현용)
    # ========================================================================

    def _analyze_buy_condition(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> tuple[bool, list[str]]:
        """
        매수 조건 분석

        종목의 데이터를 분석하여 매수 조건 충족 여부를 판단합니다.

        구현 예시:
        - 이동평균 골든크로스
        - RSI 과매도 구간 탈출
        - 거래량 급증
        - 지지선 돌파

        Args:
            stock_code: 종목 코드
            data: OHLCV 데이터프레임

        Returns:
            tuple[bool, list[str]]: (매수 여부, 매수 사유 리스트)
        """
        reasons = []

        # TODO: 매수 조건 1 - 이동평균 골든크로스
        # 예시:
        # sma_short = data['close'].rolling(5).mean()
        # sma_long = data['close'].rolling(20).mean()
        # if sma_short.iloc[-1] > sma_long.iloc[-1] and sma_short.iloc[-2] <= sma_long.iloc[-2]:
        #     reasons.append("5일선이 20일선 골든크로스")

        # TODO: 매수 조건 2 - RSI 과매도 탈출
        # 예시:
        # rsi = self._calculate_rsi(data['close'], 14)
        # if rsi.iloc[-2] < 30 and rsi.iloc[-1] >= 30:
        #     reasons.append("RSI 과매도 구간 탈출")

        # TODO: 매수 조건 3 - 거래량 급증
        # 예시:
        # avg_volume = data['volume'].rolling(20).mean()
        # if data['volume'].iloc[-1] > avg_volume.iloc[-1] * 2:
        #     reasons.append("거래량 2배 이상 급증")

        # 조건 충족 여부 판단
        # TODO: 필요한 조건 개수 설정 (예: 2개 이상)
        is_buy = len(reasons) >= 2

        return is_buy, reasons

    def _analyze_sell_condition(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> tuple[bool, list[str]]:
        """
        매도 조건 분석

        종목의 데이터를 분석하여 매도 조건 충족 여부를 판단합니다.

        구현 예시:
        - 이동평균 데드크로스
        - RSI 과매수 구간 진입
        - 목표가 도달
        - 손절선 도달

        Args:
            stock_code: 종목 코드
            data: OHLCV 데이터프레임

        Returns:
            tuple[bool, list[str]]: (매도 여부, 매도 사유 리스트)
        """
        reasons = []

        # TODO: 매도 조건 1 - 이동평균 데드크로스
        # 예시:
        # sma_short = data['close'].rolling(5).mean()
        # sma_long = data['close'].rolling(20).mean()
        # if sma_short.iloc[-1] < sma_long.iloc[-1] and sma_short.iloc[-2] >= sma_long.iloc[-2]:
        #     reasons.append("5일선이 20일선 데드크로스")

        # TODO: 매도 조건 2 - RSI 과매수 진입
        # 예시:
        # rsi = self._calculate_rsi(data['close'], 14)
        # if rsi.iloc[-1] > 70:
        #     reasons.append("RSI 과매수 구간")

        # TODO: 매도 조건 3 - 익절/손절
        # 예시:
        # if stock_code in self.positions:
        #     entry_price = self.positions[stock_code]['entry_price']
        #     current_price = data['close'].iloc[-1]
        #     profit_rate = (current_price - entry_price) / entry_price
        #
        #     if profit_rate >= 0.10:  # 10% 익절
        #         reasons.append(f"목표 수익률 도달 ({profit_rate*100:.1f}%)")
        #     elif profit_rate <= -0.05:  # 5% 손절
        #         reasons.append(f"손절선 도달 ({profit_rate*100:.1f}%)")

        # 조건 충족 여부 판단
        is_sell = len(reasons) >= 1

        return is_sell, reasons

    def _calculate_position_size(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> int:
        """
        포지션 크기 계산

        리스크 관리 규칙에 따라 적절한 매수 수량을 계산합니다.

        고려 사항:
        - 계좌 잔고
        - 최대 포지션 비율 (config에서 설정)
        - 현재 보유 포지션 수
        - 종목 변동성

        Args:
            stock_code: 종목 코드
            data: OHLCV 데이터프레임

        Returns:
            int: 매수할 주식 수량
        """
        # TODO: 계좌 잔고 조회
        # 예시:
        # available_balance = self._broker.get_available_balance()

        # TODO: 최대 포지션 크기 계산
        # 예시:
        # max_position_pct = self.get_param('risk_management.max_position_size', 0.1)
        # max_position_amount = available_balance * max_position_pct

        # TODO: 현재가 기준 매수 가능 수량 계산
        # 예시:
        # current_price = data['close'].iloc[-1]
        # quantity = int(max_position_amount / current_price)

        # TODO: 최소/최대 수량 제한 적용
        # 예시:
        # quantity = max(1, min(quantity, 1000))

        # 임시 반환값 (실제 구현 필요)
        return 0
