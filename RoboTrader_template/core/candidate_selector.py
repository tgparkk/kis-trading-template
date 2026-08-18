"""
매수 후보 종목 선정 모듈 (템플릿)

사용자는 자신만의 종목 선정 전략을 구현할 수 있습니다.
예시: 거래량 급증, 신고가 돌파, 모멘텀/가치 팩터, 기술적 지표 등
"""
import json
from pathlib import Path
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

from .models import TradingConfig
from framework.broker import KISBroker
from utils.logger import setup_logger
from utils.korean_time import now_kst, get_previous_trading_day


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

    # ETF 브랜드 키워드 (대소문자 무시)
    ETF_KEYWORDS = [
        'KODEX', 'TIGER', 'KBSTAR', 'ARIRANG', 'HANARO', 'SOL',
        'ACE', 'KOSEF', 'SMART', 'TIMEFOLIO', 'PLUS', 'VITA',
        'ETF', 'ETN', 'FOCUS', 'BNK', 'WOORI',
    ]

    def __init__(self, config: TradingConfig, broker: KISBroker, db_manager=None) -> None:
        self.config = config
        self.broker = broker
        self.db_manager = db_manager
        self.logger = setup_logger(__name__)
        self.stock_list_file = Path(__file__).parent.parent / "stock_list.json"
        self.screener_data_dir = Path(__file__).parent.parent / "data"
        # 종목 안전정보 메모 캐시 (인스턴스 단위, 후보 선정 경로 전용).
        # 전략 8개가 같은 코드를 각각 조회하는 것을 막는다.
        self._safety_info_cache: Dict[str, Optional[Dict]] = {}
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
        일일 매수 후보 종목 선정 (거래량 순위 기반)

        KIS API 거래량순위에서 KOSPI+KOSDAQ 상위 종목을 수집하고,
        ETF/우선주/가격대 필터링 후 스코어 기반으로 상위 N개를 반환합니다.
        """
        try:
            self.logger.info("일일 매수 후보 종목 선정 시작 (거래량 순위 기반)")

            # 1. 거래량 순위 API에서 수집
            raw_candidates = self._fetch_volume_rank_candidates()
            if not raw_candidates:
                self.logger.warning("거래량 순위 데이터 없음")
                return []
            self.selection_stats['total_analyzed'] = len(raw_candidates)

            # 2. 필터링 (ETF/우선주/가격대)
            filtered = self._apply_volume_rank_filters(raw_candidates)
            self.selection_stats['passed_basic_filter'] = len(filtered)
            self.logger.info(f"필터링: {len(raw_candidates)}건 → {len(filtered)}건")

            # 3. 스코어 정렬
            # ⚠️ 여기서 max_candidates 로 자르지 않는다. 자른 뒤 안전필터를 걸면
            #    상위권에 거래정지·관리종목이 끼어 있을 때 슬롯이 그냥 사라진다.
            #    아래 5번에서 limit= 로 지연 필터링해 스코어 순서대로 채운다.
            filtered.sort(key=lambda x: x['score'], reverse=True)

            # 4. CandidateStock 변환
            candidates = []
            for item in filtered:
                candidate = CandidateStock(
                    code=item['code'],
                    name=item['name'],
                    market=item.get('market', 'KRX'),
                    score=item['score'],
                    reason=item['reason'],
                    prev_close=item.get('prev_close', 0.0),
                )
                candidates.append(candidate)

            # 5. 안전성 필터 (거래정지·VI·관리종목·정리매매) — 지연 필터링으로
            #    «안전한» 후보가 max_candidates 개 모일 때까지만 조회한다.
            candidates = self._filter_unsafe_stocks(candidates, limit=max_candidates)

            # 6. 손실 블랙리스트 (최근 5영업일 손실 + 연속 3회 손실)
            candidates = self._apply_loss_blacklist(candidates)

            self.selection_stats['passed_detailed_analysis'] = len(candidates)
            self.selection_stats['final_selected'] = len(candidates)
            self.selection_stats['last_selection_time'] = now_kst()

            for c in candidates:
                self.logger.info(f"  후보: {c.code}({c.name}): {c.score:.1f}점 - {c.reason}")

            return candidates

        except Exception as e:
            self.logger.error(f"후보 종목 선정 실패: {e}")
            return []

    # =========================================================================
    # 스크리너 JSON 기반 후보 로드
    # =========================================================================

    def load_from_screener(self, json_path: Optional[str] = None,
                           max_candidates: int = 10) -> List[CandidateStock]:
        """
        스크리너 결과 JSON 파일에서 후보 종목 로드

        Args:
            json_path: screener JSON 파일 경로. None이면 가장 최근 파일 자동 탐색
            max_candidates: 최대 후보 수

        Returns:
            CandidateStock 리스트 (ETF 제외, trading_amount 내림차순)
        """
        try:
            path = self._resolve_screener_path(json_path)
            if path is None:
                return []

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            results = data.get('results', [])
            self.logger.info(f"스크리너 파일 로드: {path.name} ({len(results)}종목)")
            self.selection_stats['total_analyzed'] = len(results)

            # ETF/ETN/우선주 필터링
            filtered = [r for r in results if not self._is_etf_or_etn_screener(r.get('name', ''))]
            filtered = [r for r in filtered if not self._is_preferred_stock(r.get('code', ''), r.get('name', ''))]
            self.selection_stats['passed_basic_filter'] = len(filtered)
            self.logger.info(f"ETF/우선주 제외 후: {len(filtered)}종목")

            # trading_amount 기준 내림차순 정렬
            filtered.sort(key=lambda x: x.get('trading_amount', 0), reverse=True)

            # 상위 N개 선정 (안전성 필터 전 여유분 확보)
            selected = filtered[:max_candidates * 2]
            self.selection_stats['last_selection_time'] = now_kst()

            candidates = []
            for item in selected:
                consecutive = item.get('consecutive_up_days', 0)
                close = item.get('close', 0)
                trading_amt = item.get('trading_amount', 0)
                score = consecutive * 10 + min(trading_amt / 1e10, 30)  # 간단 스코어

                candidate = CandidateStock(
                    code=item['code'],
                    name=item['name'],
                    market='KRX',
                    score=round(score, 2),
                    reason=f"{consecutive}일연속상승, 거래대금{trading_amt/1e8:.0f}억",
                    prev_close=float(close),
                )
                candidates.append(candidate)

            # 안전성 필터 (거래정지·VI·관리종목·단일가매매)
            candidates = self._filter_unsafe_stocks(candidates)
            # 손실 블랙리스트 (최근 5영업일 + 연속 3회 손실)
            candidates = self._apply_loss_blacklist(candidates)
            # 여유분 확보 후 실제 max_candidates로 최종 절삭
            candidates = candidates[:max_candidates]

            self.selection_stats['final_selected'] = len(candidates)

            for c in candidates:
                self.logger.info(f"  후보: {c.code}({c.name}) "
                                 f"score={c.score} - {c.reason}")

            return candidates

        except Exception as e:
            self.logger.error(f"스크리너 로드 실패: {e}")
            return []

    def _resolve_screener_path(self, json_path: Optional[str] = None) -> Optional[Path]:
        """스크리너 JSON 파일 경로 결정 (지정 또는 최신 파일 자동 탐색)"""
        if json_path:
            p = Path(json_path)
            if p.exists():
                return p
            self.logger.error(f"스크리너 파일 없음: {json_path}")
            return None

        # data/ 디렉토리에서 가장 최근 screener_*.json 찾기
        if not self.screener_data_dir.exists():
            self.logger.error(f"스크리너 데이터 디렉토리 없음: {self.screener_data_dir}")
            return None

        screener_files = sorted(self.screener_data_dir.glob("screener_*.json"), reverse=True)
        if not screener_files:
            self.logger.warning("스크리너 결과 파일 없음")
            return None

        # 최신 파일이 당일자가 아니면 None 반환 (자동 수집 fallback으로 이동)
        today_str = now_kst().strftime("%Y%m%d")
        latest = screener_files[0]
        if today_str not in latest.name:
            self.logger.warning(f"당일 스크리너 없음 (최신: {latest.name}) → 자동 수집 fallback")
            return None

        self.logger.info(f"최신 스크리너 파일 사용: {latest.name}")
        return latest

    def _is_etf_or_etn_screener(self, name: str) -> bool:
        """ETF/ETN 여부 확인 (스크리너용 — 브랜드명 포함)"""
        name_upper = name.upper()
        return any(kw in name_upper for kw in self.ETF_KEYWORDS)

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

    def update_candidate_stocks_in_config(self, candidates: List[CandidateStock]) -> None:
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
    # 거래량 순위 기반 후보 수집
    # =========================================================================

    def _fetch_volume_rank_candidates(self) -> List[Dict]:
        """거래량 순위 API에서 후보 수집 (KOSPI + KOSDAQ)"""
        from api.kis_market_api import get_volume_rank
        import time

        all_candidates = []

        # KOSPI 거래량 상위 (보통주만)
        try:
            kospi_df = get_volume_rank(
                fid_input_iscd="0001",
                fid_div_cls_code="1",
            )
            if kospi_df is not None and not kospi_df.empty:
                for _, row in kospi_df.iterrows():
                    parsed = self._parse_volume_rank_row(row, 'KOSPI')
                    if parsed:
                        all_candidates.append(parsed)
            self.logger.info(f"KOSPI 거래량 순위: {len([c for c in all_candidates if c.get('market') == 'KOSPI'])}건")
        except Exception as e:
            self.logger.error(f"KOSPI 거래량 순위 조회 실패: {e}")

        time.sleep(0.2)  # API rate limit

        # KOSDAQ 거래량 상위 (보통주만)
        try:
            kosdaq_df = get_volume_rank(
                fid_input_iscd="1001",
                fid_div_cls_code="1",
            )
            if kosdaq_df is not None and not kosdaq_df.empty:
                for _, row in kosdaq_df.iterrows():
                    parsed = self._parse_volume_rank_row(row, 'KOSDAQ')
                    if parsed:
                        all_candidates.append(parsed)
            self.logger.info(f"KOSDAQ 거래량 순위: {len([c for c in all_candidates if c.get('market') == 'KOSDAQ'])}건")
        except Exception as e:
            self.logger.error(f"KOSDAQ 거래량 순위 조회 실패: {e}")

        return all_candidates

    def _parse_volume_rank_row(self, row, market: str) -> Optional[Dict]:
        """거래량 순위 API 응답 행 파싱"""
        try:
            code = str(row.get('mksc_shrn_iscd', row.get('stck_shrn_iscd', ''))).strip()
            name = str(row.get('hts_kor_isnm', '')).strip()
            rank = int(row.get('data_rank', 99))
            current_price = float(row.get('stck_prpr', 0))
            change_rate = float(row.get('prdy_ctrt', 0))
            volume = int(row.get('acml_vol', 0))

            if not code or not name:
                return None

            # 스코어: 순위 역수(1위=30점) + 양봉 보너스(+5점)
            score = max(0, 31 - rank)
            if change_rate > 0:
                score += 5

            return {
                'code': code,
                'name': name,
                'market': market,
                'rank': rank,
                'current_price': current_price,
                'change_rate': change_rate,
                'volume': volume,
                'score': score,
                'reason': f"거래량{rank}위({market}), 등락{change_rate:+.1f}%",
                'prev_close': current_price,
            }
        except Exception as e:
            self.logger.debug(f"거래량 순위 행 파싱 실패: {e}")
            return None

    def _apply_volume_rank_filters(self, candidates: List[Dict]) -> List[Dict]:
        """거래량 순위 후보 필터링 (ETF/우선주/가격대)"""
        from config.constants import CANDIDATE_MIN_PRICE, CANDIDATE_MAX_PRICE

        filtered = []
        for c in candidates:
            # ETF/ETN 제외
            if self._is_etf_or_etn_screener(c['name']):
                continue
            # 우선주 제외
            if self._is_preferred_stock(c['code'], c['name']):
                continue
            # 가격대 필터
            if c['current_price'] < CANDIDATE_MIN_PRICE or c['current_price'] > CANDIDATE_MAX_PRICE:
                continue
            filtered.append(c)
        return filtered

    # =========================================================================
    # 손실 블랙리스트 (D2: 최근 손실 / 연속 손실 종목 제외)
    # =========================================================================

    def _apply_loss_blacklist(
        self,
        candidates: List[CandidateStock],
        trading_repo=None,
    ) -> List[CandidateStock]:
        """최근 손실 / 연속 손실 종목을 후보 풀에서 제거.

        config.candidate_filters.exclude_recent_losses 또는
        config.candidate_filters.exclude_persistent_losses 가 False이면
        해당 필터는 적용하지 않습니다.

        Args:
            candidates: 필터링 전 후보 리스트
            trading_repo: 테스트용 의존성 주입 (TradingRepository 인스턴스).
                          None이면 db_manager 경유 또는 새 인스턴스 생성 시도.

        Returns:
            블랙리스트 제외 후 후보 리스트.
        """
        cfg = getattr(self.config, 'candidate_filters', None)
        if cfg is None:
            return candidates

        exclude_recent = getattr(cfg, 'exclude_recent_losses', True)
        exclude_persistent = getattr(cfg, 'exclude_persistent_losses', True)

        if not exclude_recent and not exclude_persistent:
            return candidates

        if not candidates:
            return candidates

        # repo 획득
        repo = trading_repo
        if repo is None:
            try:
                from db.repositories.trading import TradingRepository
                from config.settings import REAL_TRADING_TABLE
                repo = TradingRepository(real_table_name=REAL_TRADING_TABLE)
            except Exception as e:
                self.logger.warning(f"TradingRepository 초기화 실패 → 블랙리스트 스킵: {e}")
                return candidates

        blacklist: set = set()

        if exclude_recent:
            days_back = getattr(cfg, 'recent_loss_days_back', 5)
            try:
                recent = repo.get_losing_stocks(days_back=days_back, min_losses=1)
                blacklist |= recent
            except Exception as e:
                self.logger.warning(f"최근 손실 종목 조회 실패 → 스킵: {e}")

        if exclude_persistent:
            loss_count = getattr(cfg, 'persistent_loss_count', 3)
            try:
                persistent = repo.get_persistently_failed_stocks(consecutive_losses=loss_count)
                blacklist |= persistent
            except Exception as e:
                self.logger.warning(f"연속 손실 종목 조회 실패 → 스킵: {e}")

        if not blacklist:
            return candidates

        safe: List[CandidateStock] = []
        for c in candidates:
            if c.code in blacklist:
                self.logger.info(f"손실 블랙리스트 제외: {c.code}({c.name})")
            else:
                safe.append(c)

        excluded = len(candidates) - len(safe)
        if excluded > 0:
            self.logger.info(f"손실 블랙리스트: {len(candidates)}건 → {len(safe)}건 ({excluded}건 제외)")

        return safe

    # =========================================================================
    # 안전성 필터 (거래정지·VI·관리종목·정리매매)
    #
    # 값 계약은 2026-08-09 에 KIS inquire-price(FHKST01010100) 를 전 유니버스
    # 2,574종목에 대해 실측한 결과다. 문서/기억이 아니라 이 실측이 SSOT.
    #
    #   거래정지 : iscd_stat_cls_code == '58'   (122종목 — 전건 거래량 0으로 교차확인,
    #                                            정상 대조군 400종목은 0/400)
    #   관리종목 : mang_issu_cls_code == 'Y'    (116종목)
    #   정리매매 : sltr_yn == 'Y'               (1종목, 043090)
    #   VI       : vi_cls_code == 'Y'           (🔴'N' 미발동만 2,574/2,574 관측.
    #                                            'Y'=발동은 **미관측 추정** — 아래 참조)
    #   임시정지 : temp_stop_yn == 'Y'
    #
    # ⚠️ 「고쳐서」 되돌리지 말 것 — 아래는 전부 실측으로 확인된 지뢰다:
    #   1. ssts_hot_yn 은 **존재하지 않는 필드**다. 이름이 비슷한 ssts_yn 은
    #      «공매도가능여부»로 2,566/2,574(삼성전자 포함)가 'Y' — 이걸 정리매매로
    #      쓰면 시장 거의 전체가 배제된다. 정리매매는 sltr_yn 이다.
    #   2. mang_issu_yn 도 존재하지 않는 필드다. 실재는 mang_issu_cls_code.
    #   3. iscd_stat_cls_code 는 비트마스크가 아니라 **단일 슬롯**이다.
    #      '51'(관리종목) 은 {mang_issu_cls_code=='Y'} 의 진부분집합(43 ⊊ 116)이라
    #      '51'로 관리종목을 판별하면 116 중 73을 놓친다. SSOT 는 mang_issu_cls_code.
    #   4. iscd_stat_cls_code != '55' 를 이상으로 보면 안 된다. 1,798/2,574 가
    #      '55'가 아니면서 정상 거래된다('57' 증거금100% 만 1,584종목).
    #
    # 배제 범위는 사장님 결정(2026-08-09)으로 «주문 가능 여부»에 한정한다.
    # 시장경고(mrkt_warn_cls_code)·투자유의(invt_caful_yn)는 알파 주장이지
    # 주문 적격성이 아니므로 **배제 사유가 아니다**(로그로만 남긴다).
    # =========================================================================

    #: 빈껍데기(판정불가) 응답 식별용 결정 필드. 실측상 비거래 5종목은 이 4개가
    #: 통째로 빠진 dict 를 돌려준다(name 도 ' ').
    _DECISIVE_INFO_FIELDS = ('mang_issu_cls_code', 'sltr_yn', 'invt_caful_yn', 'ssts_yn')

    #: 판정불가 비율이 이 값을 넘으면 «개별 종목 이상»이 아니라 응답 스키마 변경을
    #: 의심해야 한다. 작은 풀에서 오경보가 나지 않도록 최소 건수 조건을 함께 건다.
    _UNDECIDABLE_ALERT_RATIO = 0.2
    _UNDECIDABLE_ALERT_MIN = 3

    @staticmethod
    def _field(info: Dict, key: str) -> str:
        """응답 필드를 공백 제거·대문자 정규화한 문자열로 읽는다(부재/None → '').

        ⚠️ .strip() 과 .upper() 를 빼지 말 것. KIS 는 값에 공백을 붙여 보낸다
        (채록본의 빈껍데기 응답은 name 이 ' ' 다). 정규화를 지워도 오늘의 테스트가
        전부 통과하는 구멍이 있었으므로 tests 에 (\"Y\", \"Y \", \" Y\", \"y\") 파라미터
        테스트를 고정해 뒀다.

        NaN 도 «값 없음»으로 본다 — pandas 경유(df.iloc[0].to_dict())로 들어오면
        결측이 None 이 아니라 NaN 이라, 안 막으면 'NAN' 이라는 «판정 가능한 정상값»
        으로 읽혀 「모른다」가 「안전」으로 접힌다.
        """
        value = info.get(key)
        if value is None or value != value:  # None 또는 NaN
            return ''
        return str(value).strip().upper()

    def _get_stock_safety_info(self, code: str) -> Optional[Dict]:
        """KIS API 종목 기본정보 조회 (거래정지·VI·관리종목·정리매매 판별용).

        실패 시 None 반환 — 호출부에서 보수적 통과(false negative 허용) 처리.

        ⚠️ import 실패는 WARNING 으로 올린다. 이 함수가 부르는
        api.kis_market_api.get_stock_basic_info 가 **아예 없던 시절**에도
        try/except 가 ImportError 를 삼켜 필터 전체가 조용히 무효였다.
        보이지 않는 실패가 결함의 본체였으므로 debug 로 내리지 말 것.

        조회 **성공**만 인스턴스 메모 캐시에 남긴다(8개 전략이 같은 코드를 재조회하는
        것을 막는다 — 09:00 후보 적재에서 60~110회 호출된다). 캐시는 후보 선정
        경로 전용이며, 매수 시점 라이브 VI 가드(core.trading_context)는 캐시를
        거치지 않고 매번 실조회한다.

        ⚠️ 실패(None)는 캐시하지 말 것. 토큰 갱신·유량제한 같은 **일시적** 실패를
        캐시하면 그 종목은 하루 종일 «판정 불가 → 보수적 통과»로 굳는다. 그러면
        bot/candidate_loader 의 3회 재시도가 캐시된 None 만 읽어 무의미해지고,
        관리종목·정리매매는 매수 시점에 재조회하는 2차 방어선이 없어 그대로 통과한다.
        """
        if code in self._safety_info_cache:
            return self._safety_info_cache[code]

        info_dict: Optional[Dict] = None
        try:
            try:
                from api.kis_market_api import get_stock_basic_info
            except Exception as import_err:
                self.logger.warning(
                    f"안전필터 무효: api.kis_market_api.get_stock_basic_info import 실패 "
                    f"({import_err}) — 후보가 전건 통과한다"
                )
                raise

            info = get_stock_basic_info(code)
            if info is not None:
                if hasattr(info, 'to_dict') and callable(info.to_dict):
                    info_dict = info.to_dict()
                elif isinstance(info, dict):
                    info_dict = info
                elif hasattr(info, '__dict__'):
                    info_dict = info.__dict__
        except Exception as e:
            self.logger.warning(f"{code} 종목정보 조회 실패(보수적 통과): {e}")
            info_dict = None

        # 성공만 캐시한다(실패 캐시는 재시도를 무력화한다 — 위 docstring 참조).
        if info_dict is not None:
            self._safety_info_cache[code] = info_dict
        return info_dict

    def clear_safety_cache(self) -> None:
        """종목 안전정보 메모 캐시를 비운다.

        장중 후보 재로드(bot.candidate_loader.reload_candidates) 시 반드시 호출한다.
        비우지 않으면 09:00 에 내린 판정을 그대로 다시 내주게 되어, 그 사이 거래정지·
        관리종목 지정된 종목이 «재로드했는데도» 후보로 살아난다.
        """
        cached = len(self._safety_info_cache)
        self._safety_info_cache.clear()
        if cached:
            self.logger.info(f"안전정보 캐시 {cached}건 비움 (재판정)")

    def _is_undecidable(self, info: Dict) -> bool:
        """판정불가(빈껍데기 응답) 여부.

        실측(2026-08-09): 5종목(012510·057050 등)이 name=' ' 이면서
        mang_issu_cls_code/sltr_yn/invt_caful_yn/ssts_yn 이 전부 부재한 dict 를
        돌려줬다. 이들은 «안전»이 아니라 «거래되지 않는» 종목이다.

        info is None(API 실패)과는 다른 경우다 — 그쪽은 보수적 통과, 이쪽은 배제.
        """
        if not isinstance(info, dict):
            return False
        return all(not self._field(info, f) for f in self._DECISIVE_INFO_FIELDS)

    def _is_trading_halted(self, info: Dict) -> bool:
        """거래정지 여부 판별.

        실측 계약: iscd_stat_cls_code == '58'(거래정지) 또는 temp_stop_yn == 'Y'(임시정지).
        ❌ '09' 가 아니다(전 유니버스에서 관측되지 않는 값).
        ❌ '55'가 아닌 값 = 이상, 도 아니다('57' 증거금100%가 1,584종목으로 최다).
        """
        if not info:
            return False
        if self._field(info, 'iscd_stat_cls_code') == '58':
            return True
        return self._field(info, 'temp_stop_yn') == 'Y'

    def _is_vi_active(self, info: Dict) -> bool:
        """VI(변동성완화장치) 발동 중 여부 판별.

        관측 (2026-08-09, 일요일 채록이라 VI 사건이 있을 수 없는 시각):
        - vi_cls_code == 'N' 이 2,574/2,574. 즉 **미발동 값만 관측됐다**.
        - ❌ '1'/'2'/'3'(정적/동적) 코드는 **한 건도 나오지 않았다** — 옛 계약은
          이 관측으로 확실히 반증된다(그렇게 읽으면 항상 False 라 가드가 no-op).

        🔴 'Y' == 발동 은 **미관측 추정**이다. KIS 필드 명명(다른 _yn/_cls_code 가
        전부 Y/N)에서 온 추론이지 측정이 아니다. 장중 첫 VI 사건에서 확증할 것.
        (확증 전까지 이 술어는 «미발동을 미발동으로 판정»하는 것만 검증돼 있다.)
        """
        if not info:
            return False
        return self._field(info, 'vi_cls_code') == 'Y'

    def _is_managed_issue(self, info: Dict) -> bool:
        """관리종목 여부 판별.

        실측 계약: mang_issu_cls_code == 'Y' (116종목). 이것이 관리종목 SSOT 다.
        ❌ mang_issu_yn 은 존재하지 않는 필드.
        ❌ iscd_stat_cls_code == '51' 로 대신하면 안 된다 — {51}(43종목)은
           {mang_issu_cls_code=='Y'}(116종목)의 진부분집합이라 73종목을 놓친다.

        시장경고·투자유의는 여기 포함하지 않는다(사장님 결정: 배제 사유 아님).
        """
        if not info:
            return False
        return self._field(info, 'mang_issu_cls_code') == 'Y'

    def _is_liquidation_trading(self, info: Dict) -> bool:
        """정리매매(상장폐지 정리매매) 여부 판별.

        실측 계약: sltr_yn == 'Y' (1종목, 043090 — 이 종목은 mang_issu_cls_code 도 'Y').
        ⚠️ ssts_yn 을 쓰면 안 된다 — 그건 «공매도가능여부»로 2,566/2,574(삼성전자
           포함)가 'Y' 라서 시장 전체를 배제한다. 존재하지도 않는 ssts_hot_yn 을
           보던 옛 구현이 이 함정에 인접해 있었다.
        ❌ mrkt_trtm_cls_code 는 존재하지 않는 필드라 제거했다.
        """
        if not info:
            return False
        return self._field(info, 'sltr_yn') == 'Y'

    def _market_warning_note(self, info: Dict) -> str:
        """시장경고·투자유의를 **로그용 주석 문자열**로만 만든다(배제 사유 아님).

        실측 계약: mrkt_warn_cls_code '00'=없음 '01'=주의 '02'=경고 (44종목),
        invt_caful_yn 'Y'/'N'. 사장님 결정으로 주문 적격성과 분리했으므로
        이 값들로 후보를 빼지 않는다. 다만 통과 사실은 눈에 보여야 한다.
        """
        if not info:
            return ''
        notes = []
        warn = self._field(info, 'mrkt_warn_cls_code')
        if warn and warn != '00':
            notes.append({'01': '시장경고(주의)', '02': '시장경고(경고)'}.get(warn, f'시장경고({warn})'))
        if self._field(info, 'invt_caful_yn') == 'Y':
            notes.append('투자유의')
        return ', '.join(notes)

    def _filter_unsafe_stocks(
        self,
        candidates: List[CandidateStock],
        _get_info_fn: Optional[Callable[[str], Optional[Dict]]] = None,
        limit: Optional[int] = None,
    ) -> List[CandidateStock]:
        """후보 풀에서 거래정지·VI·관리종목·정리매매 종목 사전 제거.

        Args:
            candidates: 필터링 전 후보 리스트(랭크 순서 유지)
            _get_info_fn: 테스트용 의존성 주입 콜백 (기본: _get_stock_safety_info)
            limit: 지정하면 **지연 필터링** — 안전한 후보가 limit 개 모이는 즉시
                멈춘다. 그 뒤 종목은 조회조차 하지 않으므로 API 호출은
                (limit + 도중 제외된 수)로 최소화되고, 앞머리에 제외 종목이
                있어도 슬롯이 줄지 않는다. 풀이 먼저 소진되면 모인 만큼만 반환한다.

        Returns:
            안전한 종목만 포함한 리스트(입력 순서 보존, limit 지정 시 최대 limit 개).

        분기 3종을 구분한다:
        - info is None (API 실패)   → 보수적 통과. 단 INFO 로 남긴다.
        - 빈껍데기 dict (판정불가)  → **배제**. dict 를 받았다고 안전이 아니다.
        - 정상 dict                 → 술어 4종으로 판정.
        """
        if not candidates:
            return candidates

        get_info = _get_info_fn if _get_info_fn is not None else self._get_stock_safety_info
        safe: List[CandidateStock] = []
        consumed = 0
        undecidable = 0

        for c in candidates:
            if limit is not None and len(safe) >= limit:
                break  # 지연 필터링: 남은 종목은 조회하지 않는다.
            consumed += 1
            info = get_info(c.code)
            if info is None:
                # API 조회 실패 → 보수적 통과(false negative 허용).
                # ⚠️ debug 가 아니라 INFO 다 — 필터가 통째로 무효였는데도 로그에
                #    아무것도 안 보였던 것이 결함이 수개월간 산 이유다.
                self.logger.info(f"안전성 판정 스킵(조회 실패 → 보수적 통과): {c.code}({c.name})")
                safe.append(c)
                continue

            if self._is_undecidable(info):
                undecidable += 1
                self.logger.info(f"후보 제외: {c.code}({c.name}) — 판정불가(응답 필드 부재)")
                continue

            reasons = []
            if self._is_trading_halted(info):
                reasons.append("거래정지")
            if self._is_vi_active(info):
                reasons.append("VI발동")
            if self._is_managed_issue(info):
                reasons.append("관리종목")
            if self._is_liquidation_trading(info):
                reasons.append("정리매매")

            if reasons:
                self.logger.info(
                    f"후보 제외: {c.code}({c.name}) — {', '.join(reasons)}"
                )
            else:
                note = self._market_warning_note(info)
                if note:
                    # 배제하지 않는다 — 사장님 결정으로 주문 적격성과 분리된 항목.
                    self.logger.info(f"후보 통과(주의 표기): {c.code}({c.name}) — {note}")
                safe.append(c)

        excluded = consumed - len(safe)
        if excluded > 0 or limit is not None:
            self.logger.info(
                f"안전성 필터: {consumed}건 조회 → {len(safe)}건 통과 ({excluded}건 제외)"
            )

        # 판정불가는 종목당 fail-closed 라, 응답 스키마가 바뀌면 «전 종목 제외 →
        # 전략별 후보 0건» 이 되면서도 흔적은 종목별 INFO 뿐이다. 스키마 파손은
        # 전역 사건이므로 전역 사건처럼 보여야 한다.
        if (undecidable >= self._UNDECIDABLE_ALERT_MIN
                and undecidable > consumed * self._UNDECIDABLE_ALERT_RATIO):
            self.logger.warning(
                f"판정불가 {undecidable}/{consumed}건 "
                f"({undecidable / consumed:.0%}) — 개별 종목 이상이 아니라 KIS 응답 "
                f"스키마 변경을 의심할 것. 결정 필드: {', '.join(self._DECISIVE_INFO_FIELDS)}"
            )

        return safe

    # =========================================================================
    # 분석 메서드 (사용자 구현 필요)
    # =========================================================================

    async def _analyze_single_stock(self, stock: Dict) -> Optional[CandidateStock]:
        """
        개별 종목 분석 및 점수 계산

        stock dict에는 code, name, market, current_price, change_rate, volume 등이 포함됩니다.
        일봉 데이터(60일)를 조회해 거래량 추세·가격 추세·변동성·과매수 여부를 점수화하고,
        최소 30점 이상인 종목만 CandidateStock으로 반환합니다.
        """
        from framework.data_providers.data_standardizer import DataStandardizer

        code = stock.get('code', '')
        name = stock.get('name', '')
        market = stock.get('market', 'KRX')

        if not code:
            return None

        try:
            # 현재가 (volume rank 데이터에 이미 있으면 재사용)
            current_price = stock.get('current_price', 0.0)
            if not current_price:
                current_price = self.broker.get_current_price(code) or 0.0

            # 일봉 데이터 조회 (60일 — MA20 + RSI14 + 여유)
            raw_df = self.broker.get_ohlcv_data(code, "D", 60)
            if raw_df is None or raw_df.empty:
                self.logger.debug(f"{code}({name}): 일봉 데이터 없음 → score=0")
                return None

            # 컬럼 표준화 (stck_clpr→close, acml_vol→volume 등)
            daily_data = DataStandardizer.standardize_daily_data(raw_df)

            score = self._calculate_stock_score(current_price, daily_data)

            if score < 30.0:
                self.logger.debug(f"{code}({name}): score={score:.1f} < 30 → 제외")
                return None

            prev_close = float(daily_data['close'].iloc[-1]) if 'close' in daily_data.columns else current_price
            reason_parts = [f"종합점수{score:.0f}점"]
            change_rate = stock.get('change_rate', 0.0)
            if change_rate:
                reason_parts.append(f"등락{change_rate:+.1f}%")

            return CandidateStock(
                code=code,
                name=name,
                market=market,
                score=round(score, 1),
                reason=', '.join(reason_parts),
                prev_close=prev_close,
            )

        except Exception as e:
            self.logger.warning(f"{code}({name}) 분석 실패: {e}")
            return None

    def _calculate_stock_score(self, price_data, daily_data) -> float:
        """
        종목 점수 계산 (0~100)

        점수 체계:
        - 거래량 증가 추세 (최근 5일 평균 > 이전 15일 평균):  +25점
        - 가격 상승 추세 (MA5 > MA20):                        +25점
        - 적정 변동성 (ATR/가격 1~5%):                        +25점
        - 과매수 패널티 (RSI > 70):                           -25점
        """
        try:
            import pandas as pd

            if daily_data is None or daily_data.empty:
                return 0.0
            if 'close' not in daily_data.columns or 'volume' not in daily_data.columns:
                return 0.0

            close = daily_data['close'].astype(float)
            volume = daily_data['volume'].astype(float)
            n = len(close)

            score = 0.0

            # ── 거래량 추세 (+25) ──────────────────────────────────────────
            # 최근 5일 평균 거래량이 이전 15일 평균보다 크면 추세 상승
            if n >= 20:
                recent_vol = volume.iloc[-5:].mean()
                prev_vol = volume.iloc[-20:-5].mean()
                if prev_vol > 0 and recent_vol > prev_vol:
                    # 비율에 비례해 최대 25점 (2배 = 25점)
                    ratio = min(recent_vol / prev_vol, 2.0)
                    score += (ratio - 1.0) * 25.0
            elif n >= 6:
                recent_vol = volume.iloc[-3:].mean()
                prev_vol = volume.iloc[:-3].mean()
                if prev_vol > 0 and recent_vol > prev_vol:
                    ratio = min(recent_vol / prev_vol, 2.0)
                    score += (ratio - 1.0) * 25.0

            # ── 가격 상승 추세 (+25) ───────────────────────────────────────
            # MA5 > MA20 이면 정배열
            if n >= 20:
                ma5 = close.rolling(5).mean().iloc[-1]
                ma20 = close.rolling(20).mean().iloc[-1]
                if not (pd.isna(ma5) or pd.isna(ma20)) and ma20 > 0:
                    if ma5 > ma20:
                        score += 25.0
            elif n >= 5:
                # 데이터 부족 시 단순 최근 3일 상승 여부로 대체
                if close.iloc[-1] > close.iloc[-3]:
                    score += 15.0

            # ── 적정 변동성 (+25) ──────────────────────────────────────────
            # ATR(5) / 현재가가 1~5% 범위면 만점, 범위 밖은 선형 감소
            if n >= 6 and 'high' in daily_data.columns and 'low' in daily_data.columns:
                high = daily_data['high'].astype(float)
                low = daily_data['low'].astype(float)
                tr = (high - low).iloc[-5:]
                atr = tr.mean()
                ref_price = float(close.iloc[-1])
                if ref_price > 0:
                    vol_ratio = atr / ref_price
                    if 0.01 <= vol_ratio <= 0.05:
                        score += 25.0
                    elif vol_ratio < 0.01:
                        score += vol_ratio / 0.01 * 25.0
                    else:  # > 0.05: 변동성 과대
                        score += max(0.0, (0.10 - vol_ratio) / 0.05 * 25.0)
            else:
                # high/low 컬럼 없으면 부분 점수 부여
                score += 12.5

            # ── 과매수 패널티 (-25) ────────────────────────────────────────
            # Wilder RSI(14) > 70 이면 과매수
            if n >= 16:
                delta = close.diff()
                gain = delta.clip(lower=0)
                loss = (-delta).clip(lower=0)
                avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
                avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
                last_loss = float(avg_loss.iloc[-1])
                if last_loss > 0:
                    rs = float(avg_gain.iloc[-1]) / last_loss
                    rsi = 100.0 - (100.0 / (1.0 + rs))
                else:
                    rsi = 100.0
                if rsi > 70.0:
                    # RSI가 70~100 구간에서 선형으로 최대 25점 패널티
                    score -= (rsi - 70.0) / 30.0 * 25.0

            return max(0.0, min(100.0, score))

        except Exception as e:
            self.logger.debug(f"점수 계산 실패: {e}")
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

    # =========================================================================
    # 전략별 후보 풀 분리 (E6)
    # =========================================================================

    def select_candidates_per_strategy(
        self,
        strategies: Dict,
        max_per_strategy: int = 10,
    ) -> Dict[str, List[CandidateStock]]:
        """전략별 독립 후보 풀 반환 (E6).

        각 전략에 대해 screener_snapshots DB 스냅샷(오늘 날짜 기준)에서 후보를
        조회하고, 없으면 공통 스크리너 JSON → 거래량 순위 순서로 fallback합니다.

        종목 중복 처리: 전략별 자본이 독립이므로 동일 종목이 여러 전략의 후보에
        중복 포함되는 것을 허용합니다.

        Args:
            strategies: {strategy_name: BaseStrategy} 딕셔너리 (E1 에서 구축)
            max_per_strategy: 전략당 최대 후보 수 (기본 10)

        Returns:
            {strategy_name: List[CandidateStock]}
        """
        result: Dict[str, List[CandidateStock]] = {}

        # 전략별 자본이 독립이므로 종목 중복을 허용한다.
        # (과거 cross-strategy dedup은 공유 자본풀 시절의 잔재 — 독립 자본에선
        #  뒤 순서 전략의 신호를 부당하게 굶겨 성과 측정을 오염시켰다.)
        for strategy_name in strategies:
            raw = self._fetch_candidates_for_strategy(strategy_name, max_per_strategy)
            result[strategy_name] = raw
            self.logger.info(
                f"[E6] {strategy_name}: 후보 {len(raw)}종목"
            )

        return result

    def _fetch_candidates_for_strategy(
        self,
        strategy_name: str,
        max_candidates: int,
    ) -> List[CandidateStock]:
        """단일 전략의 후보를 **그 전략의 `screener_snapshots` 에서만** 조회한다.

        🔑 **대체 명단은 없다.** 후보가 0건이면 그 전략은 그날 매수하지 않는다.

        ## 왜 공통 스크리너 JSON 폴백을 없앴나 (2026-08-18)

        종전에는 스냅샷이 비면 공통 `data/screener_*.json` 에서 후보를 가져왔다.
        그 명단은 **전략과 무관**하다 — `"N일연속상승, 거래대금 N억"` 기준으로 뽑히고,
        받는 전략의 `base_filter`(시총·거래대금)조차 적용되지 않았다.

        1. **전략의 정체성은 진입 룰이다.** 룰을 안 거친 종목을 사면 그 전략이 아니다.
        2. **성과 측정이 오염된다.** 「전략 X 수익률」에 X 가 아닌 매매가 섞인다.
        3. 🔴 **`accepts_volume_fallback=False` 선언을 이 경로가 무시했다** —
           `deep_mr_dev20`(「희소조건 전략 — 후보 없으면 미진입이 정합」)이 그 피해자였다.
        4. 🔑 그런데도 «실제로» 새지 않은 이유는 설계가 아니라 **우연**이었다:
           `data/screener_*.json` 을 쓰는 유일한 주체가 수동 연구 스크립트
           (`scripts/run_screener.py`)뿐이라 파일이 4개월째 낡아 있었을 뿐이다
           (`_resolve_screener_path` 는 «당일자» 파일만 받는다).
           ⇒ ***연구 스크립트를 한 번 돌리면 라이브 후보가 바뀌는 구조였다.***
           ⇒ ***「한 번도 발동한 적 없다」는 「막혀 있다」가 아니다.***

        ⚠️ 단일/없음 전략 모드(backward compat)의 `load_from_screener` 경로는 그대로다
        (`bot/candidate_loader.py`). 그 경로에는 「전략 고유 룰」이라는 개념이 없다.
        """
        # 유일 경로: screener_snapshots DB (직전 영업일 — EOD 스냅샷은 D-1에 생성됨)
        #
        # 🔑 「조건에 맞는 종목이 없다」와 「조회가 고장났다」를 «갈라서» 처리한다.
        #    둘은 정반대 사건인데 2026-08-18 이전에는 똑같이 「다른 명단에서 사오기」로
        #    처리됐고, 고장 쪽 로그가 `debug` 라 라이브(INFO)에서는 «보이지도» 않았다.
        #    ⇒ 폴백은 고장을 «대비»한 게 아니라 «감추면서» 다른 종목을 사고 있었다.
        try:
            prev_trading_day = get_previous_trading_day(now_kst())
            prev_day_str = prev_trading_day.strftime("%Y-%m-%d")
            from core.screener_snapshot_provider import make_screener_snapshot_provider
            provider = make_screener_snapshot_provider(strategy_name)
            codes = provider(strategy_name, prev_day_str)
        except Exception as e:
            # 🔴 조회 «고장» — fail-closed. 다른 명단으로 대체하지 않는다.
            #    여기서 다른 종목을 사면 「전략이 오늘 쉬었다」와 구별이 안 되고,
            #    고장은 영원히 안 보인다.
            self.logger.error(
                f"[E6] {strategy_name}: screener_snapshots 조회 «실패» → 금일 이 전략 매수 중단 "
                f"(fail-closed, 다른 명단으로 대체하지 않는다): {e}"
            )
            return []

        if not codes:
            # 🟢 정상 — 그날 그 전략의 조건에 맞는 종목이 없었다는 뜻이다.
            #    「후보 0건 = 미진입」이 정합이다(선례: deep_mr_dev20).
            self.logger.info(
                f"[E6] {strategy_name}: screener_snapshots 0건 (D-1={prev_day_str}) "
                f"— 조건에 맞는 종목 없음, 금일 미진입"
            )
            return []

        # code 리스트 → CandidateStock 변환 (name/score는 미상).
        # ⚠️ 여기서 max_candidates 로 자르지 않는다. 자른 뒤 필터를 걸면
        #    앞머리에 제외 종목이 있을 때 슬롯이 그냥 사라진다(백필 없음).
        pool = [
            CandidateStock(
                code=code,
                name=code,  # 이름 정보 없음 — trading_stock 등록 시 갱신 가능
                market="KRX",
                score=50.0,
                reason=f"screener_snapshot({strategy_name})",
                prev_close=0.0,
            )
            for code in codes
        ]
        # 안전성 필터 (거래정지·VI·관리종목·정리매매).
        # 이 경로는 원래 무필터로 반환해 안전필터를 통째로 우회했다.
        #
        # 지연 필터링(limit): 스크리너 랭크 순서대로 «안전한» 후보가
        # max_candidates 개 모이면 즉시 멈춘다 → 슬롯이 줄지 않으면서
        # API 호출은 (max_candidates + 도중 제외된 수)로 끝난다.
        # (손실 블랙리스트는 사장님 보류 결정으로 여기 적용하지 않는다.)
        try:
            candidates = self._filter_unsafe_stocks(pool, limit=max_candidates)
        except Exception as e:
            self.logger.error(
                f"[E6] {strategy_name}: 안전성 필터 «실패» → 금일 이 전략 매수 중단 "
                f"(fail-closed): {e}"
            )
            return []

        self.logger.info(
            f"[E6] {strategy_name}: screener_snapshots {len(candidates)}건 확보 "
            f"(스냅샷 {len(codes)}건, 목표 {max_candidates}건, D-1={prev_day_str})"
        )
        return candidates
