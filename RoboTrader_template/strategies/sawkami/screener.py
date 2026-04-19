"""
사와카미 전략 매수후보 스크리닝 모듈

사와카미 가치투자 전략에 맞는 종목 선정:
  1차: 시장 필터 (KOSPI+KOSDAQ, 우선주/ETF 제외)
  2차: 재무 필터 (영업이익 YoY 30%↑, PBR < 1.5) — 캐싱
  3차: 기술적 필터 (52주고점 -20%, RSI<30, 거래량 1.5x) — 매일 변동
  최종: 복합 점수 정렬
"""

import json
import time
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
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

logger = setup_logger(__name__)


@dataclass
class SawkamiFundamentalData:
    """재무 필터 통과 종목의 캐싱 데이터"""
    code: str
    name: str
    market: str
    op_income_growth: float  # 영업이익 YoY 성장률 (%)
    pbr: float               # PBR
    bps: float               # BPS
    cached_at: datetime = field(default_factory=now_kst)


class SawkamiCandidateSelector(CandidateSelector):
    """
    사와카미 가치투자 전략용 매수 후보 선정기

    CandidateSelector를 상속하여 사와카미 전략에 맞게 필터링/스코어링을 구현.
    """

    # 기술적 필터 기본값
    DEFAULT_HIGH52W_DROP_PCT = -20.0   # 52주 고점 대비 하락률
    DEFAULT_RSI_OVERSOLD = 30          # RSI 과매도 기준
    DEFAULT_RSI_PERIOD = 14
    DEFAULT_VOL_RATIO_MIN = 1.5        # 20일 평균 대비 거래량 배수
    DEFAULT_VOL_MA_PERIOD = 20
    DEFAULT_HIGH52W_PERIOD = 252       # 52주 ≈ 252 거래일

    # 재무 필터 기본값
    DEFAULT_OP_GROWTH_MIN = 30.0       # 영업이익 YoY 최소 성장률 (%)
    DEFAULT_PBR_MAX = 1.5

    # 캐시 유효 기간 (시간)
    FUNDAMENTAL_CACHE_HOURS = 24

    # API 호출 간격 (초)
    API_CALL_DELAY = 0.15

    def __init__(self, config: TradingConfig, broker: KISBroker,
                 db_manager=None, strategy_params: Optional[Dict] = None) -> None:
        super().__init__(config, broker, db_manager)
        self.logger = setup_logger(__name__)

        # 전략 파라미터 (strategy.py에서 주입 가능)
        params = strategy_params or {}
        self.op_growth_min = params.get("op_income_growth_min", self.DEFAULT_OP_GROWTH_MIN)
        self.pbr_max = params.get("pbr_max", self.DEFAULT_PBR_MAX)
        self.high52w_drop_pct = params.get("high52w_drop_pct", self.DEFAULT_HIGH52W_DROP_PCT)
        self.rsi_oversold = params.get("rsi_oversold", self.DEFAULT_RSI_OVERSOLD)
        self.rsi_period = params.get("rsi_period", self.DEFAULT_RSI_PERIOD)
        self.vol_ratio_min = params.get("volume_ratio_min", self.DEFAULT_VOL_RATIO_MIN)
        self.vol_ma_period = params.get("volume_ma_period", self.DEFAULT_VOL_MA_PERIOD)
        self.high52w_period = params.get("high52w_period", self.DEFAULT_HIGH52W_PERIOD)

        # 재무 데이터 캐시: {code: SawkamiFundamentalData}
        self._fundamental_cache: Dict[str, SawkamiFundamentalData] = {}
        self._fundamental_cache_file = Path(__file__).parent.parent / "data" / "sawkami_fundamental_cache.json"

        # 캐시 로드
        self._load_fundamental_cache()

    # =========================================================================
    # 1차 필터: 시장 필터 (KOSPI + KOSDAQ)
    # =========================================================================

    def _apply_basic_filters(self, stocks: List[Dict]) -> List[Dict]:
        """
        1차 기본 필터링 — KOSPI + KOSDAQ 전 시장, 우선주/ETF 제외

        오버라이드: 부모 클래스는 KOSPI만 허용하지만 사와카미는 전 시장 대상.
        """
        filtered = []
        for stock in stocks:
            code = stock.get('code', '')
            name = stock.get('name', '')
            market = stock.get('market', '')

            # KOSPI 또는 KOSDAQ만
            if market not in ('KOSPI', 'KOSDAQ'):
                continue
            # 우선주 제외
            if self._is_preferred_stock(code, name):
                continue
            # ETF/ETN 제외
            if self._is_etf_or_etn(name):
                continue
            # ETF 브랜드명 제외 (부모 클래스의 확장 키워드)
            if self._is_etf_or_etn_screener(name):
                continue

            filtered.append(stock)

        self.logger.info(f"1차 시장 필터: {len(stocks)} → {len(filtered)}종목 (KOSPI+KOSDAQ, 우선주/ETF 제외)")
        return filtered

    # =========================================================================
    # 2차 필터: 재무 필터 (영업이익 성장, PBR)
    # =========================================================================

    def _apply_fundamental_filters(self, stocks: List[Dict],
                                        batch_size: int = 20) -> List[SawkamiFundamentalData]:
        """
        2차 재무 필터링 — 영업이익 YoY 30%↑, PBR < 1.5

        캐시 활용: 재무 데이터는 분기 단위로 변경되므로 24시간 캐싱.
        Rate limit 고려: batch_size 단위로 처리 + delay.
        """
        from api.kis_financial_api import get_financial_ratio

        passed: List[SawkamiFundamentalData] = []
        api_calls = 0

        for i, stock in enumerate(stocks):
            code = stock.get('code', '')
            name = stock.get('name', '')
            market = stock.get('market', '')

            # 캐시 확인
            cached = self._fundamental_cache.get(code)
            if cached and self._is_cache_valid(cached):
                passed.append(cached)
                continue

            # API 조회
            try:
                ratios = get_financial_ratio(code)
                api_calls += 1

                if not ratios:
                    continue

                latest = ratios[0]
                op_growth = latest.operating_income_growth
                bps = latest.bps

                # 필터 적용
                if op_growth < self.op_growth_min:
                    continue
                if bps <= 0:
                    continue

                # PBR 계산을 위해 현재가 필요 — 여기서는 BPS만 캐시하고
                # PBR은 기술적 필터에서 현재가와 함께 계산
                fund_data = SawkamiFundamentalData(
                    code=code,
                    name=name,
                    market=market,
                    op_income_growth=op_growth,
                    pbr=0.0,  # 나중에 현재가로 계산
                    bps=bps,
                )
                self._fundamental_cache[code] = fund_data
                passed.append(fund_data)

                self.logger.debug(
                    f"✅ 재무 통과: {code}({name}) "
                    f"영업이익성장={op_growth:.1f}%, BPS={bps:,.0f}"
                )

            except Exception as e:
                self.logger.warning(f"재무 조회 실패 {code}: {e}")
                continue

            # Rate limit
            if api_calls > 0 and api_calls % batch_size == 0:
                self.logger.info(f"재무 필터 진행: {i+1}/{len(stocks)} (API {api_calls}건, 통과 {len(passed)}건)")
                time.sleep(1.0)  # 배치 간 1초 대기
            else:
                time.sleep(self.API_CALL_DELAY)

        self.logger.info(
            f"2차 재무 필터: {len(stocks)} → {len(passed)}종목 "
            f"(API 호출 {api_calls}건)"
        )

        # 캐시 저장
        self._save_fundamental_cache()

        return passed

    # =========================================================================
    # 3차 필터: 기술적 필터 (52주 고점, RSI, 거래량)
    # =========================================================================

    def _apply_technical_filters(
        self, fund_stocks: List[SawkamiFundamentalData]
    ) -> List[CandidateStock]:
        """
        3차 기술적 필터링 — 52주고점 -20%, RSI<30, 거래량 1.5x

        매일 변하는 데이터이므로 캐싱하지 않음.
        """
        from api.kis_market_api import get_inquire_price, get_inquire_daily_itemchartprice

        candidates: List[CandidateStock] = []

        for fund in fund_stocks:
            try:
                # 현재가 조회
                price_df = get_inquire_price(itm_no=fund.code)
                if price_df is None or price_df.empty:
                    continue

                row = price_df.iloc[0]
                current_price = self._safe_float(row.get('stck_prpr', '0'))
                if current_price <= 0:
                    continue

                # PBR 계산 (현재가 / BPS)
                if fund.bps <= 0:
                    continue
                pbr = current_price / fund.bps
                if pbr >= self.pbr_max:
                    continue

                # 52주 고점
                w52_high = self._safe_float(row.get('stck_dryy_hgpr', '0'))
                if w52_high <= 0:
                    # 연중 최고가가 없으면 일봉 데이터에서 계산
                    w52_high = self._get_52w_high(fund.code)
                    if w52_high <= 0:
                        continue

                drop_pct = (current_price - w52_high) / w52_high * 100
                if drop_pct > self.high52w_drop_pct:
                    continue

                # 일봉 데이터로 RSI, 거래량 비율 계산
                daily_df = get_inquire_daily_itemchartprice(
                    output_dv="2", itm_no=fund.code,
                    inqr_strt_dt=(now_kst() - timedelta(days=60)).strftime("%Y%m%d"),
                    inqr_end_dt=now_kst().strftime("%Y%m%d"),
                )
                if daily_df is None or len(daily_df) < self.rsi_period + 2:
                    continue

                # 가격/거래량 추출
                closes = daily_df['stck_clpr'].apply(self._safe_float)
                volumes = daily_df['acml_vol'].apply(self._safe_float)

                # RSI 계산
                rsi_val = self._calculate_rsi_value(closes)
                if rsi_val is None or rsi_val >= self.rsi_oversold:
                    continue

                # 거래량 비율
                vol_ma = float(volumes.tail(self.vol_ma_period).mean()) if len(volumes) >= self.vol_ma_period else 0
                current_vol = float(volumes.iloc[-1]) if len(volumes) > 0 else 0
                if vol_ma <= 0:
                    continue
                vol_ratio = current_vol / vol_ma
                if vol_ratio < self.vol_ratio_min:
                    continue

                # 모든 필터 통과 → 점수 계산
                score = self._calculate_sawkami_score(
                    op_growth=fund.op_income_growth,
                    drop_pct=drop_pct,
                    rsi=rsi_val,
                    pbr=pbr,
                    vol_ratio=vol_ratio,
                )

                reasons = (
                    f"영업이익YoY {fund.op_income_growth:+.1f}%, "
                    f"52주고점대비 {drop_pct:.1f}%, "
                    f"PBR {pbr:.2f}, "
                    f"RSI {rsi_val:.1f}, "
                    f"거래량 {vol_ratio:.1f}x"
                )

                candidate = CandidateStock(
                    code=fund.code,
                    name=fund.name,
                    market=fund.market,
                    score=round(score, 2),
                    reason=reasons,
                    prev_close=current_price,
                )
                candidates.append(candidate)

                self.logger.info(f"✅ 최종 후보: {fund.code}({fund.name}) score={score:.2f} — {reasons}")

            except Exception as e:
                self.logger.warning(f"기술적 필터 오류 {fund.code}: {e}")
                continue

            time.sleep(self.API_CALL_DELAY)

        self.logger.info(f"3차 기술적 필터: {len(fund_stocks)} → {len(candidates)}종목")
        return candidates

    # =========================================================================
    # 메인 진입점
    # =========================================================================

    def select_daily_candidates(self, max_candidates: int = 10) -> List[CandidateStock]:
        """
        사와카미 전략 일일 매수 후보 선정

        1차: 시장 필터 (KOSPI+KOSDAQ, ETF/우선주 제외)
        2차: 재무 필터 (영업이익 성장, BPS) — 캐싱
        3차: 기술적 필터 (52주고점, RSI, 거래량, PBR) — 매일 갱신
        최종: 점수 순 정렬
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("🏯 사와카미 전략 매수 후보 스크리닝 시작")
            self.logger.info("=" * 60)

            # 1. 종목 리스트 로드
            all_stocks = self._load_stock_list()
            if not all_stocks:
                self.logger.warning("종목 리스트 없음")
                return []
            self.selection_stats['total_analyzed'] = len(all_stocks)

            # 2. 1차 시장 필터
            filtered = self._apply_basic_filters(all_stocks)
            self.selection_stats['passed_basic_filter'] = len(filtered)
            if not filtered:
                return []

            # 3. 2차 재무 필터
            fund_passed = self._apply_fundamental_filters(filtered)
            if not fund_passed:
                self.logger.info("재무 필터 통과 종목 없음")
                return []

            # 4. 3차 기술적 필터 + 점수 계산
            candidates = self._apply_technical_filters(fund_passed)
            self.selection_stats['passed_detailed_analysis'] = len(candidates)

            # 5. 점수 순 정렬
            candidates.sort(key=lambda x: x.score, reverse=True)
            selected = candidates[:max_candidates]
            self.selection_stats['final_selected'] = len(selected)
            self.selection_stats['last_selection_time'] = now_kst()

            self.logger.info("=" * 60)
            self.logger.info(f"🏯 사와카미 최종 후보: {len(selected)}종목")
            for c in selected:
                self.logger.info(f"  {c.code}({c.name}): {c.score:.2f}점 — {c.reason}")
            self.logger.info("=" * 60)

            # DB에 후보 저장
            self._save_candidates_to_db(candidates)

            return selected

        except Exception as e:
            self.logger.error(f"사와카미 후보 선정 실패: {e}", exc_info=True)
            return []

    # =========================================================================
    # DB 저장
    # =========================================================================

    def _save_candidates_to_db(self, candidates: List[CandidateStock]) -> None:
        """스크리닝 결과를 DB에 저장"""
        try:
            from .db_manager import SawkamiDBManager
            db = SawkamiDBManager()
            today = now_kst().date()

            records = []
            for c in candidates:
                # reason 파싱: "영업이익YoY +35.0%, 52주고점대비 -25.3%, PBR 0.85, RSI 22.1, 거래량 2.3x"
                parts = {}
                for part in c.reason.split(", "):
                    if "영업이익" in part:
                        parts["op_income_growth"] = float(part.split()[-1].rstrip("%,"))
                    elif "52주" in part:
                        parts["drop_from_high"] = float(part.split()[-1].rstrip("%,"))
                    elif "PBR" in part:
                        parts["pbr"] = float(part.split()[-1].rstrip(","))
                    elif "RSI" in part:
                        parts["rsi"] = float(part.split()[-1].rstrip(","))
                    elif "거래량" in part:
                        parts["volume_ratio"] = float(part.split()[-1].rstrip("x,"))

                records.append({
                    "stock_code": c.code,
                    "stock_name": c.name,
                    "score": c.score,
                    "close_price": c.prev_close,
                    **parts,
                })

            saved = db.save_candidates(today, records)
            self.logger.info(f"📊 매수후보 {saved}건 DB 저장 완료")
            db.close()
        except Exception as e:
            self.logger.warning(f"매수후보 DB 저장 실패 (전략 동작에 영향 없음): {e}")

    # =========================================================================
    # 스코어링
    # =========================================================================

    def _calculate_sawkami_score(
        self,
        op_growth: float,
        drop_pct: float,
        rsi: float,
        pbr: float,
        vol_ratio: float,
    ) -> float:
        """
        사와카미 전략 복합 점수 (0~100)

        - 영업이익 성장률 높을수록 +점수 (max 25)
        - 52주 고점 대비 하락폭 클수록 +점수 (max 25)
        - RSI 낮을수록 +점수 (max 20)
        - PBR 낮을수록 +점수 (max 15)
        - 거래량 비율 높을수록 +점수 (max 15)
        """
        score = 0.0

        # 영업이익 성장률 (30%~200% → 0~25점)
        score += min(25.0, max(0.0, (op_growth - 30) / 170 * 25))

        # 52주 고점 대비 하락 (-20%~-60% → 0~25점)
        score += min(25.0, max(0.0, (abs(drop_pct) - 20) / 40 * 25))

        # RSI (0~30 → 25~0점, 낮을수록 높은 점수)
        score += min(20.0, max(0.0, (30 - rsi) / 30 * 20))

        # PBR (0~1.5 → 15~0점, 낮을수록 높은 점수)
        score += min(15.0, max(0.0, (1.5 - pbr) / 1.5 * 15))

        # 거래량 비율 (1.5x~5x → 0~15점)
        score += min(15.0, max(0.0, (vol_ratio - 1.5) / 3.5 * 15))

        return score

    # =========================================================================
    # 유틸리티
    # =========================================================================

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        if value is None or value == '':
            return default
        try:
            return float(str(value).replace(',', ''))
        except (ValueError, TypeError):
            return default

    def _calculate_rsi_value(self, closes) -> Optional[float]:
        """시리즈에서 최신 RSI 값 계산 (공용 유틸리티 사용)"""
        return calculate_rsi_latest(closes, self.rsi_period)

    def _get_52w_high(self, code: str) -> float:
        """일봉 연속조회로 52주 고점 산출"""
        from api.kis_market_api import get_inquire_daily_itemchartprice_extended
        try:
            df = get_inquire_daily_itemchartprice_extended(
                itm_no=code,
                inqr_strt_dt=(now_kst() - timedelta(days=365)).strftime("%Y%m%d"),
                inqr_end_dt=now_kst().strftime("%Y%m%d"),
                max_count=self.high52w_period,
            )
            if df is not None and not df.empty and 'stck_hgpr' in df.columns:
                return float(df['stck_hgpr'].apply(self._safe_float).max())
        except Exception as e:
            self.logger.warning(f"52주 고점 조회 실패 {code}: {e}")
        return 0.0

    # =========================================================================
    # 캐시 관리
    # =========================================================================

    def _is_cache_valid(self, cached: SawkamiFundamentalData) -> bool:
        diff = (now_kst() - cached.cached_at).total_seconds() / 3600
        return diff < self.FUNDAMENTAL_CACHE_HOURS

    def _load_fundamental_cache(self) -> None:
        try:
            if self._fundamental_cache_file.exists():
                with open(self._fundamental_cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item in data:
                    cached_at = datetime.fromisoformat(item['cached_at'])
                    # naive datetime → KST aware로 변환 (캐시 호환성)
                    if cached_at.tzinfo is None:
                        from utils.korean_time import KST
                        cached_at = cached_at.replace(tzinfo=KST)
                    fund = SawkamiFundamentalData(
                        code=item['code'],
                        name=item['name'],
                        market=item['market'],
                        op_income_growth=item['op_income_growth'],
                        pbr=item.get('pbr', 0.0),
                        bps=item['bps'],
                        cached_at=cached_at,
                    )
                    if self._is_cache_valid(fund):
                        self._fundamental_cache[fund.code] = fund
                self.logger.info(f"재무 캐시 로드: {len(self._fundamental_cache)}건")
        except Exception as e:
            self.logger.warning(f"재무 캐시 로드 실패: {e}")

    def _save_fundamental_cache(self) -> None:
        try:
            self._fundamental_cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for fund in self._fundamental_cache.values():
                data.append({
                    'code': fund.code,
                    'name': fund.name,
                    'market': fund.market,
                    'op_income_growth': fund.op_income_growth,
                    'pbr': fund.pbr,
                    'bps': fund.bps,
                    'cached_at': fund.cached_at.isoformat(),
                })
            with open(self._fundamental_cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"재무 캐시 저장: {len(data)}건")
        except Exception as e:
            self.logger.warning(f"재무 캐시 저장 실패: {e}")

    def clear_fundamental_cache(self) -> None:
        """재무 캐시 초기화"""
        self._fundamental_cache.clear()
        if self._fundamental_cache_file.exists():
            self._fundamental_cache_file.unlink()
        self.logger.info("재무 캐시 초기화 완료")


class SawkamiScreenerAdapter(ScreenerBase):
    """SawkamiCandidateSelector 를 ScreenerBase 인터페이스로 감싸는 어댑터."""

    strategy_name = "sawkami"

    def __init__(self, config: TradingConfig, broker: KISBroker, db_manager=None) -> None:
        self._config = config
        self._broker = broker
        self._db_manager = db_manager

    def default_params(self) -> Dict[str, Any]:
        return {
            "op_income_growth_min": 30.0,
            "pbr_max": 1.5,
            "high52w_drop_pct": -20.0,
            "rsi_oversold": 30,
            "rsi_period": 14,
            "volume_ratio_min": 1.5,
            "volume_ma_period": 20,
            "high52w_period": 252,
            "max_candidates": 10,
        }

    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        today = datetime.now().date()
        if scan_date >= today:
            return self._scan_realtime(params)
        return self._scan_historical(scan_date, params)

    def _scan_realtime(self, params: Dict[str, Any]) -> List[CandidateStock]:
        """현재 시점 데이터 기반 스캔 (기존 SawkamiCandidateSelector 래핑)."""
        merged = {**self.default_params(), **(params or {})}
        max_candidates = int(merged.pop("max_candidates", 10))
        selector = SawkamiCandidateSelector(
            self._config, self._broker,
            db_manager=self._db_manager,
            strategy_params=merged,
        )
        return selector.select_daily_candidates(max_candidates=max_candidates) or []

    def _scan_historical(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        """과거 특정일 기준 Sawkami 후보 재구성.

        외부 DB(strategy_analysis.yearly_fundamentals + daily_candles)를 활용하여
        실시간 KIS API 호출 없이 과거 스크리닝 결과를 재현한다.
        """
        try:
            merged = {**self.default_params(), **(params or {})}
            op_growth_min: float = float(merged.get("op_income_growth_min", 30.0))
            pbr_max: float = float(merged.get("pbr_max", 1.5))
            high52w_drop_pct: float = float(merged.get("high52w_drop_pct", -20.0))
            rsi_oversold: float = float(merged.get("rsi_oversold", 30))
            rsi_period: int = int(merged.get("rsi_period", 14))
            vol_ratio_min: float = float(merged.get("volume_ratio_min", 1.5))
            vol_ma_period: int = int(merged.get("volume_ma_period", 20))
            high52w_period: int = int(merged.get("high52w_period", 252))
            max_candidates: int = int(merged.get("max_candidates", 10))

            # 1. 재무 필터 (벡터화)
            fund_df = get_fundamentals_at(None, scan_date)
            if fund_df.empty:
                logger.warning("Sawkami historical scan: 재무 데이터 없음 (%s)", scan_date)
                return []

            fund_df = fund_df.dropna(subset=["revenue_growth", "pbr"])
            fund_df = fund_df[
                (fund_df["revenue_growth"] >= op_growth_min) &
                (fund_df["pbr"] > 0) &
                (fund_df["pbr"] <= pbr_max)
            ].copy()

            if fund_df.empty:
                logger.info("Sawkami historical scan (%s): 재무 필터 통과 0건", scan_date)
                return []

            logger.info("Sawkami historical scan (%s): 재무 필터 통과 %d종목", scan_date, len(fund_df))

            # 2. 52주 고점 + RSI + 거래량 계산을 위해 일봉 로드
            # high52w_period(252) + vol_ma_period(20) 여유분으로 약 300일
            lookback_days = high52w_period + vol_ma_period + 10
            start = date.fromordinal(scan_date.toordinal() - lookback_days)
            stock_codes = fund_df["stock_code"].tolist()
            candles = get_daily_candles_range(stock_codes, start, scan_date)

            # 3. 기술적 필터 + 점수 계산
            candidates: List[CandidateStock] = []
            for _, row in fund_df.iterrows():
                code = str(row["stock_code"])
                df_c = candles.get(code)
                if df_c is None or len(df_c) < rsi_period + 2:
                    continue

                closes = df_c["close"].astype(float)
                highs = df_c["high"].astype(float)
                volumes = df_c["volume"].astype(float)

                current_price = float(closes.iloc[-1])
                if current_price <= 0:
                    continue

                # 52주 고점 근접도
                w52_highs = highs.tail(high52w_period)
                if len(w52_highs) == 0:
                    continue
                w52_high = float(w52_highs.max())
                if w52_high <= 0:
                    continue
                drop_pct = (current_price / w52_high - 1) * 100
                # high52w_drop_pct = -20.0: -20% 이상 하락한 종목만 통과
                # drop_pct 가 -20% 보다 크면(덜 하락) 제외, -20% 이하(더 하락)면 통과
                if drop_pct > high52w_drop_pct:
                    continue

                # RSI
                rsi_val = calculate_rsi_latest(closes, rsi_period)
                if rsi_val is None or rsi_val > rsi_oversold:
                    continue

                # 거래량 비율: 최근 5일 평균 / 직전 vol_ma_period 평균
                if len(volumes) < vol_ma_period:
                    continue
                vol_ma = float(volumes.tail(vol_ma_period).mean())
                if vol_ma <= 0:
                    continue
                recent_vol = float(volumes.tail(5).mean())
                vol_ratio = recent_vol / vol_ma
                if vol_ratio < vol_ratio_min:
                    continue

                pbr = float(row["pbr"])
                rev_growth = float(row["revenue_growth"])

                # 사와카미 복합 점수 (기존 _calculate_sawkami_score 로직 재활용)
                score = 0.0
                score += min(25.0, max(0.0, (rev_growth - 30) / 170 * 25))
                score += min(25.0, max(0.0, (abs(drop_pct) - 20) / 40 * 25))
                score += min(20.0, max(0.0, (30 - rsi_val) / 30 * 20))
                score += min(15.0, max(0.0, (1.5 - pbr) / 1.5 * 15))
                score += min(15.0, max(0.0, (vol_ratio - 1.5) / 3.5 * 15))

                candidates.append(CandidateStock(
                    code=code,
                    name="",
                    market="",
                    score=round(score, 2),
                    reason=(
                        f"매출성장 {rev_growth:.1f}%, 52주고점대비 {drop_pct:.1f}%, "
                        f"PBR {pbr:.2f}, RSI {rsi_val:.1f}, 거래량 {vol_ratio:.1f}x, scan_date={scan_date}"
                    ),
                ))

            candidates.sort(key=lambda x: x.score, reverse=True)
            selected = candidates[:max_candidates]
            logger.info(
                "Sawkami historical scan (%s): 최종 후보 %d종목",
                scan_date, len(selected),
            )
            return selected

        except Exception as exc:
            logger.warning("Sawkami historical scan 실패 (%s): %s", scan_date, exc)
            return []
