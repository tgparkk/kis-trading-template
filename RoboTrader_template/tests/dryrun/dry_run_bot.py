"""
DryRunBot - 모의 운영 봇
실제 시장 데이터로 전체 흐름을 시뮬레이션하되, 주문만 Mock으로 대체합니다.
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import setup_logger
from utils.korean_time import now_kst
from .mock_order_manager import MockOrderManager


class DryRunBot:
    """
    모의 운영 봇

    DayTradingBot을 상속하지 않고, 필요한 컴포넌트만 조립하여
    각 단계를 순차 실행합니다.
    """

    def __init__(self):
        self.logger = setup_logger("dryrun")
        self.mock_orders = MockOrderManager()
        self.api_manager = None
        self.db_manager = None
        self.anomalies: List[str] = []
        self.report_lines: List[str] = []

    def _log(self, msg: str):
        self.logger.info(msg)
        self.report_lines.append(f"[{now_kst().strftime('%H:%M:%S')}] {msg}")

    def _warn(self, msg: str):
        self.logger.warning(msg)
        self.anomalies.append(msg)
        self.report_lines.append(f"[{now_kst().strftime('%H:%M:%S')}] ⚠ {msg}")

    async def run(self):
        """전체 드라이런 실행"""
        self._log("=" * 60)
        self._log("  RoboTrader 드라이런 시작")
        self._log("=" * 60)

        # 1. API 인증
        if not self._step_api_init():
            self._warn("API 인증 실패 - 드라이런 중단")
            self._save_report()
            return False

        # 2. 계좌 잔고 조회
        balance = self._step_account_balance()

        # 3. 퀀트 스크리닝 (DB)
        portfolio = self._step_quant_screening()

        # 4. 리밸런싱 계획
        plan = self._step_rebalancing_plan(portfolio)

        # 5. 가격 검증
        if plan:
            self._step_price_validation(plan)

        # 6. 주문 시뮬레이션
        await self._step_order_simulation(plan)

        # 7. 보유 종목 손익절 판단
        self._step_pnl_check()

        # 8. 이상 감지
        self._step_anomaly_detection(balance, portfolio)

        # 9. 결과 출력 및 저장
        self._print_summary()
        self._save_report()
        return True

    def _step_api_init(self) -> bool:
        """1단계: API 인증"""
        self._log("[1/8] API 인증...")
        try:
            from api.kis_api_manager import KISAPIManager
            self.api_manager = KISAPIManager()
            if self.api_manager.initialize():
                self._log("  API 인증 성공")
                return True
            return False
        except Exception as e:
            self._warn(f"  API 초기화 오류: {e}")
            return False

    def _step_account_balance(self) -> Optional[Dict]:
        """2단계: 계좌 잔고"""
        self._log("[2/8] 계좌 잔고 조회...")
        try:
            balance = self.api_manager.get_account_balance()
            if balance:
                self._log(f"  잔고: {balance.account_balance:,.0f}원, "
                         f"가용: {balance.available_amount:,.0f}원")
                return {
                    'account_balance': balance.account_balance,
                    'available_amount': balance.available_amount,
                }
            self._warn("  잔고 조회 실패")
            return None
        except Exception as e:
            self._warn(f"  잔고 조회 오류: {e}")
            return None

    def _step_quant_screening(self) -> List[Dict]:
        """3단계: 퀀트 스크리닝"""
        self._log("[3/8] 퀀트 포트폴리오 조회...")
        try:
            from db.database_manager import DatabaseManager
            self.db_manager = DatabaseManager()
            portfolio = self.db_manager.get_latest_portfolio()
            if portfolio is not None and not portfolio.empty:
                self._log(f"  포트폴리오 종목수: {len(portfolio)}개")
                return portfolio.to_dict('records')
            self._warn("  포트폴리오 없음")
            return []
        except Exception as e:
            self._warn(f"  포트폴리오 조회 오류: {e}")
            return []

    def _step_rebalancing_plan(self, portfolio: List[Dict]) -> Optional[Dict]:
        """4단계: 리밸런싱 계획"""
        self._log("[4/8] 리밸런싱 계획 수립...")
        if not portfolio:
            self._log("  포트폴리오 없음 - 계획 없음")
            return None

        plan = {
            'buy_list': [],
            'sell_list': [],
            'hold_list': [],
        }

        # 간단한 계획: 포트폴리오의 모든 종목을 매수 대상으로 설정
        for item in portfolio:
            code = item.get('stock_code', '')
            name = item.get('stock_name', '')
            plan['buy_list'].append({'stock_code': code, 'stock_name': name})

        self._log(f"  매수: {len(plan['buy_list'])}종목, "
                 f"매도: {len(plan['sell_list'])}종목, "
                 f"유지: {len(plan['hold_list'])}종목")
        return plan

    def _step_price_validation(self, plan: Dict):
        """5단계: 가격 검증"""
        self._log("[5/8] 매수 대상 현재가 검증...")
        failed_codes = []

        for item in plan.get('buy_list', []):
            code = item['stock_code']
            try:
                price = self.api_manager.get_current_price(code)
                if price:
                    item['current_price'] = price.current_price
                    self._log(f"  {code} ({item.get('stock_name', '')}): "
                            f"{price.current_price:,.0f}원")
                else:
                    failed_codes.append(code)
                    self._warn(f"  {code} 현재가 조회 실패")
            except Exception as e:
                failed_codes.append(code)
                self._warn(f"  {code} 가격 조회 오류: {e}")

        if failed_codes:
            self._warn(f"  가격 조회 실패 종목: {len(failed_codes)}개")

    async def _step_order_simulation(self, plan: Optional[Dict]):
        """6단계: 주문 시뮬레이션"""
        self._log("[6/8] 주문 시뮬레이션...")
        if not plan:
            self._log("  계획 없음 - 주문 없음")
            return

        for item in plan.get('buy_list', []):
            price = item.get('current_price', 0)
            if price > 0:
                quantity = max(1, int(900_000 / price))
                await self.mock_orders.place_buy_order(
                    item['stock_code'], quantity, price
                )

        for item in plan.get('sell_list', []):
            await self.mock_orders.place_sell_order(
                item['stock_code'], item.get('quantity', 0), item.get('price', 0)
            )

        summary = self.mock_orders.get_summary()
        self._log(f"  매수 {summary['buy_count']}건 ({summary['total_buy_amount']:,.0f}원), "
                 f"매도 {summary['sell_count']}건")

    def _step_pnl_check(self):
        """7단계: 보유 종목 손익절 판단"""
        self._log("[7/8] 보유 종목 손익절 판단...")
        try:
            balance = self.api_manager.get_account_balance()
            if balance and hasattr(balance, 'positions') and balance.positions:
                for pos in balance.positions:
                    code = pos.get('stock_code', '')
                    pnl_rate = pos.get('profit_loss_rate', 0)
                    self._log(f"  {code}: 수익률 {pnl_rate:.2f}%")
            else:
                self._log("  보유 종목 없음")
        except Exception as e:
            self._warn(f"  손익 조회 오류: {e}")

    def _step_anomaly_detection(self, balance: Optional[Dict], portfolio: List[Dict]):
        """8단계: 이상 감지"""
        self._log("[8/8] 이상 감지 검사...")

        # 스크리닝 종목 부족
        if len(portfolio) < 15:
            self._warn(f"  스크리닝 종목 부족: {len(portfolio)}개 (기준: 15개)")

        # 가용 잔고 부족
        if balance and balance.get('available_amount', 0) < 100_000:
            self._warn(f"  가용 잔고 부족: {balance['available_amount']:,.0f}원")

        # 매도 비율 과다
        summary = self.mock_orders.get_summary()
        total_orders = summary['buy_count'] + summary['sell_count']
        if total_orders > 0 and summary['sell_count'] / max(1, total_orders) > 0.5:
            self._warn(f"  매도 비율 과다: {summary['sell_count']}/{total_orders}")

        if not self.anomalies:
            self._log("  이상 없음")

    def _print_summary(self):
        """결과 요약 출력"""
        print()
        print("=" * 60)
        print("  드라이런 결과 요약")
        print("=" * 60)

        summary = self.mock_orders.get_summary()
        print(f"  매수 주문: {summary['buy_count']}건 ({summary['total_buy_amount']:,.0f}원)")
        print(f"  매도 주문: {summary['sell_count']}건")

        if self.anomalies:
            print()
            print(f"  이상 감지: {len(self.anomalies)}건")
            for a in self.anomalies:
                print(f"    - {a}")
        else:
            print("  이상 감지: 없음")

        print()

    def _save_report(self):
        """리포트 파일 저장"""
        report_dir = PROJECT_ROOT / "reports"
        report_dir.mkdir(exist_ok=True)

        ts = now_kst().strftime("%Y%m%d_%H%M%S")
        report_path = report_dir / f"dryrun_{ts}.txt"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(self.report_lines))

        self._log(f"리포트 저장: {report_path}")
