"""
Lynch 전략 매수후보 스크리닝 모듈

피터 린치 PEG 전략에 맞는 종목 선정:
  1차: 시장 필터 (KOSPI+KOSDAQ, 우선주/ETF 제외)
  2차: 재무 필터 (PEG≤0.3, 영업이익 YoY≥70%, 부채비율≤200%, ROE≥5%)
  3차: 기술적 필터 (RSI<35)
  최종: 복합 점수 정렬
"""

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import pandas as pd

from core.candidate_selector import CandidateSelector, CandidateStock
from core.models import TradingConfig
from framework.broker import KISBroker
from strategies.screener_base import ScreenerBase
from strategies.historical_data import get_fundamentals_at, get_daily_candles_range
from utils.logger import setup_logger
from utils.korean_time import now_kst
from utils.indicators import calculate_rsi_latest
from .strategy import LynchStrategy

logger = setup_logger(__name__)


class LynchCandidateSelector(CandidateSelector):
    """피터 린치 PEG 전략용 매수 후보 선정기"""

    API_CALL_DELAY = 0.15

    def __init__(self, config: TradingConfig, broker: KISBroker,
                 db_manager=None, strategy_params: Optional[Dict] = None) -> None:
        super().__init__(config, broker, db_manager)
        self.logger = setup_logger(__name__)

        params = strategy_params or {}
        self.peg_max = params.get("peg_max", 0.3)
        self.op_growth_min = params.get("op_income_growth_min", 70.0)
        self.debt_ratio_max = params.get("debt_ratio_max", 200.0)
        self.roe_min = params.get("roe_min", 5.0)
        self.rsi_oversold = params.get("rsi_oversold", 35)
        self.rsi_period = params.get("rsi_period", 14)

    def _apply_basic_filters(self, stocks: List[Dict]) -> List[Dict]:
        filtered = []
        for stock in stocks:
            code = stock.get('code', '')
            name = stock.get('name', '')
            market = stock.get('market', '')

            if market not in ('KOSPI', 'KOSDAQ'):
                continue
            if self._is_preferred_stock(code, name):
                continue
            if self._is_etf_or_etn(name):
                continue
            if self._is_etf_or_etn_screener(name):
                continue

            filtered.append(stock)

        self.logger.info(f"1차 시장 필터: {len(stocks)} → {len(filtered)}종목")
        return filtered

    def select_daily_candidates(self, max_candidates: int = 10) -> List[CandidateStock]:
        try:
            self.logger.info("=" * 60)
            self.logger.info("📊 Lynch 전략 매수 후보 스크리닝 시작")
            self.logger.info("=" * 60)

            all_stocks = self._load_stock_list()
            if not all_stocks:
                return []

            filtered = self._apply_basic_filters(all_stocks)
            if not filtered:
                return []

            # 재무 + 기술적 필터를 결합
            candidates = self._apply_lynch_filters(filtered)

            candidates.sort(key=lambda x: x.score, reverse=True)
            selected = candidates[:max_candidates]

            self.logger.info(f"📊 Lynch 최종 후보: {len(selected)}종목")
            for c in selected:
                self.logger.info(f"  {c.code}({c.name}): {c.score:.2f}점 — {c.reason}")

            return selected

        except Exception as e:
            self.logger.error(f"Lynch 후보 선정 실패: {e}", exc_info=True)
            return []

    def _apply_lynch_filters(self, stocks: List[Dict]) -> List[CandidateStock]:
        from api.kis_financial_api import get_financial_ratio
        from api.kis_market_api import get_inquire_daily_itemchartprice

        candidates = []

        for stock in stocks:
            code = stock.get('code', '')
            name = stock.get('name', '')
            market = stock.get('market', '')

            try:
                ratios = get_financial_ratio(code)
                if not ratios:
                    continue

                latest = ratios[0]
                fundamentals = {
                    "per": latest.per,
                    "op_income_growth": latest.operating_income_growth,
                    "debt_ratio": latest.debt_ratio,
                    "roe": latest.roe,
                }

                # 일봉에서 RSI 계산
                daily_df = get_inquire_daily_itemchartprice(
                    output_dv="2", itm_no=code,
                    inqr_strt_dt=(now_kst() - timedelta(days=40)).strftime("%Y%m%d"),
                    inqr_end_dt=now_kst().strftime("%Y%m%d"),
                )
                if daily_df is None or len(daily_df) < self.rsi_period + 2:
                    continue

                closes = daily_df['stck_clpr'].apply(lambda x: float(str(x).replace(',', '') or 0))
                current_price = float(closes.iloc[-1])
                if current_price <= 0:
                    continue

                rsi_val = calculate_rsi_latest(closes, self.rsi_period)
                if rsi_val is None:
                    continue

                should_buy, reasons = LynchStrategy.evaluate_buy_conditions(
                    current_price=current_price,
                    rsi_value=rsi_val,
                    fundamentals=fundamentals,
                    peg_max=self.peg_max,
                    op_growth_min=self.op_growth_min,
                    debt_ratio_max=self.debt_ratio_max,
                    roe_min=self.roe_min,
                    rsi_oversold=self.rsi_oversold,
                )

                if should_buy:
                    peg = fundamentals["per"] / fundamentals["op_income_growth"]
                    score = (1 / peg) * 10 + fundamentals["roe"] + fundamentals["op_income_growth"] / 10
                    candidate = CandidateStock(
                        code=code,
                        name=name,
                        market=market,
                        score=round(score, 2),
                        reason=", ".join(reasons),
                        prev_close=current_price,
                    )
                    candidates.append(candidate)

            except Exception as e:
                self.logger.warning(f"필터 오류 {code}: {e}")
                continue

            time.sleep(self.API_CALL_DELAY)

        self.logger.info(f"Lynch 필터: {len(stocks)} → {len(candidates)}종목")
        return candidates


class LynchScreenerAdapter(ScreenerBase):
    """LynchCandidateSelector 를 ScreenerBase 인터페이스로 감싸는 어댑터."""

    strategy_name = "lynch"

    def __init__(self, config: TradingConfig, broker: KISBroker, db_manager=None) -> None:
        self._config = config
        self._broker = broker
        self._db_manager = db_manager

    def default_params(self) -> Dict[str, Any]:
        return {
            "peg_max": 0.3,
            "op_income_growth_min": 70.0,
            "debt_ratio_max": 200.0,
            "roe_min": 5.0,
            "rsi_oversold": 35,
            "rsi_period": 14,
            "max_candidates": 10,
        }

    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        today = datetime.now().date()
        if scan_date >= today:
            return self._scan_realtime(params)
        return self._scan_historical(scan_date, params)

    def _scan_realtime(self, params: Dict[str, Any]) -> List[CandidateStock]:
        """현재 시점 데이터 기반 스캔 (기존 LynchCandidateSelector 래핑)."""
        merged = {**self.default_params(), **(params or {})}
        max_candidates = int(merged.pop("max_candidates", 10))
        selector = LynchCandidateSelector(
            self._config, self._broker,
            db_manager=self._db_manager,
            strategy_params=merged,
        )
        return selector.select_daily_candidates(max_candidates=max_candidates) or []

    def _scan_historical(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        """과거 특정일 기준 Lynch 후보 재구성.

        외부 DB(strategy_analysis.yearly_fundamentals + daily_candles)를 활용하여
        실시간 KIS API 호출 없이 과거 스크리닝 결과를 재현한다.
        """
        try:
            merged = {**self.default_params(), **(params or {})}
            peg_max: float = float(merged.get("peg_max", 0.3))
            op_growth_min: float = float(merged.get("op_income_growth_min", 70.0))
            debt_ratio_max: float = float(merged.get("debt_ratio_max", 200.0))
            roe_min: float = float(merged.get("roe_min", 5.0))
            rsi_oversold: float = float(merged.get("rsi_oversold", 35))
            rsi_period: int = int(merged.get("rsi_period", 14))
            max_candidates: int = int(merged.get("max_candidates", 10))

            # 1. 전체 종목 재무 데이터 조회 (벡터화)
            fund_df = get_fundamentals_at(None, scan_date)
            if fund_df.empty:
                logger.warning("Lynch historical scan: 재무 데이터 없음 (%s)", scan_date)
                return []

            # 2. 재무 필터 (pandas 벡터 연산)
            fund_df = fund_df.dropna(subset=["per", "roe", "debt_ratio", "revenue_growth"])
            fund_df = fund_df[
                (fund_df["revenue_growth"] >= op_growth_min) &
                (fund_df["debt_ratio"] <= debt_ratio_max) &
                (fund_df["roe"] >= roe_min) &
                (fund_df["per"] > 0) &
                (fund_df["revenue_growth"] > 0)
            ].copy()

            # PEG 근사: per / revenue_growth <= peg_max
            fund_df["peg"] = fund_df["per"] / fund_df["revenue_growth"]
            fund_df = fund_df[fund_df["peg"] <= peg_max]

            if fund_df.empty:
                logger.info("Lynch historical scan (%s): 재무 필터 통과 0건", scan_date)
                return []

            logger.info("Lynch historical scan (%s): 재무 필터 통과 %d종목", scan_date, len(fund_df))

            # 3. 직전 30일 일봉 로드 (RSI 계산용)
            stock_codes = fund_df["stock_code"].tolist()
            start = date.fromordinal(scan_date.toordinal() - 40)  # 여유분 포함
            candles = get_daily_candles_range(stock_codes, start, scan_date)

            # 4. RSI 필터 + 점수 계산
            candidates: List[CandidateStock] = []
            for _, row in fund_df.iterrows():
                code = str(row["stock_code"])
                df_c = candles.get(code)
                if df_c is None or len(df_c) < rsi_period + 2:
                    continue

                rsi_val = calculate_rsi_latest(df_c["close"].astype(float), rsi_period)
                if rsi_val is None or rsi_val > rsi_oversold:
                    continue

                per = float(row["per"])
                roe = float(row["roe"])
                rev_growth = float(row["revenue_growth"])
                peg = float(row["peg"])

                # 기존 LynchCandidateSelector 점수식과 동일
                score = (1 / peg) * 10 + roe + rev_growth / 10

                candidates.append(CandidateStock(
                    code=code,
                    name="",  # yearly_fundamentals 에 name 컬럼 없음
                    market="",
                    score=round(score, 2),
                    reason=f"PEG {peg:.3f}, ROE {roe:.1f}%, 매출성장 {rev_growth:.1f}%, RSI {rsi_val:.1f}, scan_date={scan_date}",
                ))

            candidates.sort(key=lambda x: x.score, reverse=True)
            selected = candidates[:max_candidates]
            logger.info(
                "Lynch historical scan (%s): 최종 후보 %d종목 (RSI 필터 후 %d→%d)",
                scan_date, len(selected), len(candidates), len(selected),
            )
            return selected

        except Exception as exc:
            logger.warning("Lynch historical scan 실패 (%s): %s", scan_date, exc)
            return []
