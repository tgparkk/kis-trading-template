"""
국내시장 데이터 수집기 (DI 패턴)

KIS API 의존성을 생성자 콜백 주입으로 격리하여,
단위 테스트와 모듈 독립성을 확보합니다.

사용 예:
    # KIS API 자동 바인딩
    collector = DomesticMarketCollector.from_kis_api()
    snapshot = collector.fetch_snapshot()

    # 테스트용 목 주입
    collector = DomesticMarketCollector(
        get_index_fn=my_mock_index,
        get_investor_flow_fn=my_mock_flow,
        get_volume_rank_fn=my_mock_rank,
    )
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

from .models import IndexData, InvestorFlow, RankedStock, DomesticMarketSnapshot

try:
    from utils.logger import setup_logger
except ImportError:
    import logging

    def setup_logger(name):
        return logging.getLogger(name)


# ---------------------------------------------------------------------------
# KIS 업종 현재지수 API (TR: FHPUP02100000) 응답 필드명
# ---------------------------------------------------------------------------
# bstp_nmix_prpr       : 업종지수 현재가
# bstp_nmix_prdy_vrss  : 업종지수 전일대비
# bstp_nmix_prdy_ctrt  : 업종지수 전일대비율 (%)
# acml_vol             : 누적 거래량
# acml_tr_pbmn         : 누적 거래대금
#
# KIS 거래량순위 API (TR: FHPST01710000) 응답 필드명 (DataFrame)
# data_rank            : 순위
# hts_kor_isnm         : 종목명
# mksc_shrn_iscd       : 종목코드 (6자리, 축약)
# stck_prpr            : 주식 현재가
# prdy_ctrt            : 전일대비율 (%)
# acml_vol             : 누적 거래량
#
# KIS 외국인/기관 매매종목가집계 API (TR: FHPTJ04400000) 응답 구조
# investor_summary     : list[dict] -- 투자자별 총계
#   - prsn_ntby_qty    : 개인 순매수수량
#   - frgn_ntby_qty    : 외국인 순매수수량
#   - orgn_ntby_qty    : 기관계 순매수수량
#   - prsn_ntby_tr_pbmn: 개인 순매수거래대금
#   - frgn_ntby_tr_pbmn: 외국인 순매수거래대금
#   - orgn_ntby_tr_pbmn: 기관계 순매수거래대금
# stock_details        : list[dict] -- 종목별 상세 (사용하지 않음)
# ---------------------------------------------------------------------------


def _safe_float(value: Any, default: float = 0.0) -> float:
    """안전한 float 변환. 변환 실패 시 default 반환."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """안전한 int 변환. 변환 실패 시 default 반환."""
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


class DomesticMarketCollector:
    """
    국내시장 데이터 수집기 (DI 패턴)

    생성자에 콜백 함수를 주입받아 KIS API 직접 import 없이 동작합니다.
    from_kis_api() 팩토리 메서드로 KIS API 함수를 자동 바인딩할 수 있습니다.
    TTL 캐시를 지원하며, API 호출 실패 시 빈 결과를 반환합니다.
    """

    def __init__(
        self,
        get_index_fn: Optional[Callable] = None,
        get_investor_flow_fn: Optional[Callable] = None,
        get_volume_rank_fn: Optional[Callable] = None,
        cache_ttl_seconds: int = 60,
    ):
        """
        Args:
            get_index_fn: 지수 조회 함수. 시그니처: (index_code: str) -> Optional[Dict]
            get_investor_flow_fn: 투자자 매매동향 조회 함수. 시그니처: () -> Optional[Dict]
            get_volume_rank_fn: 거래량 순위 조회 함수. 시그니처: (**kwargs) -> Optional[DataFrame]
            cache_ttl_seconds: 캐시 유효 시간 (초). 기본 60초.
        """
        self.logger = setup_logger(__name__)
        self._get_index_fn = get_index_fn
        self._get_investor_flow_fn = get_investor_flow_fn
        self._get_volume_rank_fn = get_volume_rank_fn
        self._cache_ttl = cache_ttl_seconds

        # TTL 캐시
        self._cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None

    # ------------------------------------------------------------------
    # 팩토리 메서드
    # ------------------------------------------------------------------

    @classmethod
    def from_kis_api(cls, cache_ttl_seconds: int = 60) -> "DomesticMarketCollector":
        """
        KIS API 함수를 자동 바인딩하는 팩토리 메서드.

        Returns:
            KIS API가 연결된 DomesticMarketCollector 인스턴스
        """
        from api import kis_market_api

        return cls(
            get_index_fn=kis_market_api.get_index_data,
            get_investor_flow_fn=kis_market_api.get_investor_flow_data,
            get_volume_rank_fn=kis_market_api.get_volume_rank,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    # ------------------------------------------------------------------
    # 캐시 관리
    # ------------------------------------------------------------------

    def _is_cache_valid(self) -> bool:
        """캐시가 유효한지 확인합니다."""
        if self._cache_time is None:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl

    def clear_cache(self) -> None:
        """캐시를 수동으로 초기화합니다."""
        self._cache.clear()
        self._cache_time = None

    # ------------------------------------------------------------------
    # 개별 데이터 조회
    # ------------------------------------------------------------------

    def fetch_index(self, index_code: str, name: str) -> Optional[IndexData]:
        """
        KIS 업종 현재지수 API 응답을 IndexData로 변환합니다.

        Args:
            index_code: 업종코드 ("0001": 코스피, "1001": 코스닥)
            name: 표시용 지수 이름 ("코스피", "코스닥")

        Returns:
            IndexData 또는 None (조회 실패 시)
        """
        if self._get_index_fn is None:
            self.logger.warning("지수 조회 함수가 설정되지 않았습니다")
            return None

        try:
            raw: Optional[Dict[str, Any]] = self._get_index_fn(index_code)
            if raw is None:
                self.logger.warning(f"{name}({index_code}) 지수 데이터 없음")
                return None

            # KIS API 응답 필드 -> IndexData 변환
            # TR: FHPUP02100000 (국내업종 현재지수)
            value = _safe_float(raw.get("bstp_nmix_prpr"))
            change = _safe_float(raw.get("bstp_nmix_prdy_vrss"))
            change_rate = _safe_float(raw.get("bstp_nmix_prdy_ctrt"))
            volume = _safe_int(raw.get("acml_vol"))
            # 거래대금: 원 단위 -> 억원 단위 변환
            trade_amount_raw = _safe_float(raw.get("acml_tr_pbmn"))
            trade_amount = round(trade_amount_raw / 100_000_000, 1) if trade_amount_raw else 0.0

            return IndexData(
                name=name,
                value=value,
                change=change,
                change_rate=change_rate,
                volume=volume,
                trade_amount=trade_amount,
                timestamp=datetime.now(),
            )

        except Exception as e:
            self.logger.error(f"{name}({index_code}) 지수 조회 오류: {e}")
            return None

    def fetch_investor_flow(self) -> Optional[InvestorFlow]:
        """
        KIS 투자자별 매매동향 API 응답을 InvestorFlow로 변환합니다.

        Returns:
            InvestorFlow 또는 None (조회 실패 시)
        """
        if self._get_investor_flow_fn is None:
            self.logger.warning("투자자 매매동향 조회 함수가 설정되지 않았습니다")
            return None

        try:
            raw: Optional[Dict[str, Any]] = self._get_investor_flow_fn()
            if raw is None:
                self.logger.warning("투자자 매매동향 데이터 없음")
                return None

            # investor_summary는 투자자 구분별 리스트
            # TR: FHPTJ04400000 응답에서 순매수거래대금(원) -> 억원 변환
            summary_list = raw.get("investor_summary", [])
            if not summary_list:
                self.logger.warning("투자자 매매동향: investor_summary 비어있음")
                return InvestorFlow(timestamp=datetime.now())

            # summary_list가 단일 dict인 경우와 list인 경우를 모두 처리
            # 일반적으로 list의 첫 번째 항목이 총계
            summary = summary_list[0] if isinstance(summary_list, list) else summary_list

            # 순매수거래대금 (원) -> 억원
            foreign_net_raw = _safe_float(summary.get("frgn_ntby_tr_pbmn"))
            institution_net_raw = _safe_float(summary.get("orgn_ntby_tr_pbmn"))
            individual_net_raw = _safe_float(summary.get("prsn_ntby_tr_pbmn"))

            foreign_net = round(foreign_net_raw / 100_000_000, 1) if foreign_net_raw else 0.0
            institution_net = round(institution_net_raw / 100_000_000, 1) if institution_net_raw else 0.0
            individual_net = round(individual_net_raw / 100_000_000, 1) if individual_net_raw else 0.0

            return InvestorFlow(
                foreign_net=foreign_net,
                institution_net=institution_net,
                individual_net=individual_net,
                timestamp=datetime.now(),
            )

        except Exception as e:
            self.logger.error(f"투자자 매매동향 조회 오류: {e}")
            return None

    def fetch_volume_rank(self, top_n: int = 10) -> List[RankedStock]:
        """
        KIS 거래량순위 API 응답을 RankedStock 리스트로 변환합니다.

        Args:
            top_n: 상위 N개 종목만 반환 (기본 10)

        Returns:
            RankedStock 리스트 (조회 실패 시 빈 리스트)
        """
        if self._get_volume_rank_fn is None:
            self.logger.warning("거래량순위 조회 함수가 설정되지 않았습니다")
            return []

        try:
            df = self._get_volume_rank_fn()
            if df is None or (hasattr(df, "empty") and df.empty):
                self.logger.warning("거래량순위 데이터 없음")
                return []

            results: List[RankedStock] = []
            # DataFrame 행을 순회하며 RankedStock 변환
            for idx, row in df.head(top_n).iterrows():
                row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)

                rank = _safe_int(row_dict.get("data_rank", idx + 1))
                # 종목코드: mksc_shrn_iscd 또는 stck_shrn_iscd
                stock_code = str(
                    row_dict.get("mksc_shrn_iscd")
                    or row_dict.get("stck_shrn_iscd", "")
                ).strip()
                stock_name = str(row_dict.get("hts_kor_isnm", "")).strip()
                current_price = _safe_float(row_dict.get("stck_prpr"))
                change_rate = _safe_float(row_dict.get("prdy_ctrt"))
                volume = _safe_int(row_dict.get("acml_vol"))

                results.append(
                    RankedStock(
                        rank=rank,
                        stock_code=stock_code,
                        stock_name=stock_name,
                        current_price=current_price,
                        change_rate=change_rate,
                        volume=volume,
                    )
                )

            return results

        except Exception as e:
            self.logger.error(f"거래량순위 조회 오류: {e}")
            return []

    # ------------------------------------------------------------------
    # 종합 스냅샷
    # ------------------------------------------------------------------

    def fetch_snapshot(self, use_cache: bool = True) -> DomesticMarketSnapshot:
        """
        국내시장 종합 스냅샷을 조회합니다.

        코스피/코스닥 지수, 투자자 매매동향, 거래량 상위 종목을
        한 번에 수집하여 DomesticMarketSnapshot으로 반환합니다.

        Args:
            use_cache: True이면 TTL 내 캐시된 결과를 재사용합니다.

        Returns:
            DomesticMarketSnapshot (일부 데이터가 없어도 항상 반환)
        """
        if use_cache and self._is_cache_valid():
            cached = self._cache.get("snapshot")
            if cached is not None:
                self.logger.debug("국내시장 스냅샷: 캐시 사용")
                return cached

        self.logger.debug("국내시장 스냅샷 수집 시작")

        kospi = self.fetch_index("0001", "코스피")
        kosdaq = self.fetch_index("1001", "코스닥")
        investor_flow = self.fetch_investor_flow()
        volume_rank = self.fetch_volume_rank(top_n=10)

        snapshot = DomesticMarketSnapshot(
            kospi=kospi,
            kosdaq=kosdaq,
            investor_flow=investor_flow,
            volume_rank=volume_rank,
            timestamp=datetime.now(),
        )

        # 캐시 갱신
        self._cache["snapshot"] = snapshot
        self._cache_time = datetime.now()

        self.logger.debug("국내시장 스냅샷 수집 완료")
        return snapshot
