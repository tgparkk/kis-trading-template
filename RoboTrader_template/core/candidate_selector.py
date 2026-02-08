"""
매수 후보 종목 선정 모듈 (템플릿)

사용자는 자신만의 종목 선정 전략을 구현할 수 있습니다.
예시: 거래량 급증, 신고가 돌파, 모멘텀/가치 팩터, 기술적 지표 등
"""
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from .models import TradingConfig
from framework.broker import KISBroker
from utils.logger import setup_logger
from utils.korean_time import now_kst


@dataclass
class CandidateStock:
    """후보 종목 정보"""
    code: str
    name: str
    market: str
    score: float      # 선정 점수
    reason: str       # 선정 이유
    prev_close: float = 0.0


class CandidateSelector:
    """
    매수 후보 종목 선정기

    사용자는 _analyze_single_stock(), _calculate_stock_score() 메서드를
    자신의 전략에 맞게 구현하면 됩니다.
    """

    def __init__(self, config: TradingConfig, broker: KISBroker, db_manager=None):
        self.config = config
        self.broker = broker
        self.db_manager = db_manager
        self.logger = setup_logger(__name__)
        self.stock_list_file = Path(__file__).parent.parent / "stock_list.json"
        self.selection_stats = {
            'total_analyzed': 0, 'passed_basic_filter': 0,
            'passed_detailed_analysis': 0, 'final_selected': 0,
            'last_selection_time': None
        }

    # =========================================================================
    # 메인 선정 로직
    # =========================================================================

    async def select_daily_candidates(self, max_candidates: int = 5) -> List[CandidateStock]:
        """
        일일 매수 후보 종목 선정

        TODO: 매수 후보 종목 선정 로직을 여기에 구현하세요

        예시 전략:
        - 거래량 급증 종목 (전일 대비 200% 이상)
        - 신고가 돌파 종목 (52주 신고가)
        - 모멘텀 상위 종목 (20일 수익률 상위)
        - 가치주 (PER, PBR 저평가)
        """
        try:
            self.logger.info("일일 매수 후보 종목 선정 시작")

            # 1. 종목 리스트 로드
            all_stocks = self._load_stock_list()
            if not all_stocks:
                return []
            self.selection_stats['total_analyzed'] = len(all_stocks)

            # 2. 1차 필터링
            filtered_stocks = await self._apply_basic_filters(all_stocks)
            self.selection_stats['passed_basic_filter'] = len(filtered_stocks)

            # 3. TODO: 2차 상세 분석 구현
            # candidate_stocks = []
            # for stock in filtered_stocks:
            #     candidate = await self._analyze_single_stock(stock)
            #     if candidate:
            #         candidate_stocks.append(candidate)
            candidate_stocks = []  # 플레이스홀더

            self.selection_stats['passed_detailed_analysis'] = len(candidate_stocks)

            # 4. 점수 기준 정렬 및 선정
            candidate_stocks.sort(key=lambda x: x.score, reverse=True)
            selected = candidate_stocks[:max_candidates]
            self.selection_stats['final_selected'] = len(selected)
            self.selection_stats['last_selection_time'] = now_kst()

            for c in selected:
                self.logger.info(f"  - {c.code}({c.name}): {c.score:.2f}점 - {c.reason}")

            return selected

        except Exception as e:
            self.logger.error(f"후보 종목 선정 실패: {e}")
            return []

    # =========================================================================
    # 유틸리티 메서드
    # =========================================================================

    def _load_stock_list(self) -> List[Dict]:
        """stock_list.json에서 종목 리스트 로드"""
        try:
            if not self.stock_list_file.exists():
                self.logger.error(f"종목 리스트 파일 없음: {self.stock_list_file}")
                return []
            with open(self.stock_list_file, 'r', encoding='utf-8') as f:
                return json.load(f).get('stocks', [])
        except Exception as e:
            self.logger.error(f"종목 리스트 로드 실패: {e}")
            return []

    def _is_preferred_stock(self, code: str, name: str) -> bool:
        """우선주 여부 확인 (코드 끝자리 5 또는 이름에 '우' 포함)"""
        return code.endswith('5') or '우' in name

    def _is_etf_or_etn(self, name: str) -> bool:
        """ETF/ETN 여부 확인"""
        return any(kw in name.upper() for kw in ['ETF', 'ETN'])

    def get_all_stock_list(self) -> List[Dict]:
        """전체 종목 리스트 반환"""
        return self._load_stock_list()

    def get_selection_statistics(self) -> Dict:
        """선정 통계 반환"""
        stats = self.selection_stats.copy()
        total = stats['total_analyzed'] or 1
        stats['basic_filter_rate'] = round(stats['passed_basic_filter'] / total * 100, 2)
        stats['detailed_analysis_rate'] = round(stats['passed_detailed_analysis'] / total * 100, 2)
        stats['final_selection_rate'] = round(stats['final_selected'] / total * 100, 2)
        if stats['last_selection_time']:
            stats['last_selection_time'] = stats['last_selection_time'].isoformat()
        return stats

    def update_candidate_stocks_in_config(self, candidates: List[CandidateStock]):
        """선정된 후보 종목을 설정에 업데이트"""
        try:
            self.config.data_collection.candidate_stocks = [c.code for c in candidates]
            self.logger.info(f"후보 종목 설정 업데이트: {len(candidates)}개")
        except Exception as e:
            self.logger.error(f"후보 종목 설정 업데이트 실패: {e}")

    # =========================================================================
    # 필터링 메서드
    # =========================================================================

    async def _apply_basic_filters(self, stocks: List[Dict]) -> List[Dict]:
        """
        1차 기본 필터링

        기본 제공: KOSPI만, 우선주 제외, ETF/ETN 제외

        TODO: 추가 필터링 조건을 구현하세요
        예시: 시가총액 1000억 이상, 거래대금 10억 이상, 특정 업종 제외
        """
        filtered = []
        for stock in stocks:
            code, name = stock.get('code', ''), stock.get('name', '')

            if stock.get('market') != 'KOSPI':
                continue
            if self._is_preferred_stock(code, name):
                continue
            if self._is_etf_or_etn(name):
                continue

            # TODO: 추가 필터 조건
            # if market_cap < 100_000_000_000: continue
            # if volume_amount < 1_000_000_000: continue

            filtered.append(stock)
        return filtered

    # =========================================================================
    # 분석 메서드 (사용자 구현 필요)
    # =========================================================================

    async def _analyze_single_stock(self, stock: Dict) -> Optional[CandidateStock]:
        """
        개별 종목 분석 및 점수 계산

        TODO: 종목 분석 로직을 여기에 구현하세요

        구현 가이드:
        1. API로 현재가, 일봉 데이터 조회
           price_data = self.broker.get_current_price(code)
           daily_data = self.broker.get_ohlcv_data(code, "D", 100)

        2. 점수 계산
           score = self._calculate_stock_score(price_data, daily_data)

        3. 최소 점수 기준 충족 시 CandidateStock 반환

        예시 조건:
        - 200일 신고가 돌파
        - 거래량 전일 대비 2배 이상
        - 양봉 (시가 < 종가)
        - 5일 평균 거래대금 50억 이상
        """
        # TODO: 구현 필요
        pass

    def _calculate_stock_score(self, price_data, daily_data) -> float:
        """
        종목 점수 계산 (0~100)

        TODO: 점수 계산 로직을 여기에 구현하세요

        예시 점수 체계:
        - 신고가 돌파: +25점
        - 거래량 급증: +20점
        - 양봉 형성: +10점
        - 이동평균선 정배열: +15점
        - RSI 적정 구간: +10점
        - 거래대금 충분: +10점
        """
        # TODO: 구현 필요
        return 0.0

    # =========================================================================
    # 퀀트/조건검색 메서드
    # =========================================================================

    async def get_quant_candidates(self, limit: int = 50) -> List[CandidateStock]:
        """
        퀀트 점수 기반 후보 종목 조회

        TODO: 퀀트 팩터 기반 종목 선정 로직을 구현하세요
        예시 팩터: PER, PBR, ROE, 모멘텀, 부채비율, 성장률
        """
        try:
            if self.db_manager:
                calc_date = now_kst().strftime('%Y%m%d')
                rows = self.db_manager.get_quant_portfolio(calc_date, limit)
                if rows:
                    name_map = {s['code']: s['name'] for s in self.get_all_stock_list()}
                    return [
                        CandidateStock(
                            code=r['stock_code'],
                            name=r['stock_name'] or name_map.get(r['stock_code'], ''),
                            market='KRX',
                            score=r.get('total_score', 0),
                            reason=r.get('reason', '퀀트 스크리닝')
                        ) for r in rows
                    ]
            return await self.select_daily_candidates(max_candidates=limit)
        except Exception as e:
            self.logger.error(f"퀀트 후보 조회 실패: {e}")
            return []

    def get_condition_search_results(self, seq: str) -> Optional[List[Dict]]:
        """
        HTS 종목조건검색 결과 조회

        Note: HTS에서 조건검색 설정 필요, config/key.ini에 HTS_ID 필요
        """
        try:
            from config.settings import HTS_ID
            from api.kis_market_api import get_psearch_result

            if not HTS_ID:
                self.logger.error("HTS_ID가 설정되지 않았습니다")
                return None

            result_df = get_psearch_result(user_id=HTS_ID, seq=seq)
            if result_df is None:
                return None
            if result_df.empty:
                return []
            return result_df.to_dict('records')
        except Exception as e:
            self.logger.error(f"종목조건검색 오류: {e}")
            return None

    def get_condition_search_candidates(self, seq: str, max_candidates: int = 10) -> Optional[List[Dict]]:
        """조건검색 결과 조회 (호환성 유지용 래퍼)"""
        return self.get_condition_search_results(seq)
