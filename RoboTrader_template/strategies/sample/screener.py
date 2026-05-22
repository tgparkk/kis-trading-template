"""
Sample 전략 매수후보 스크리닝 모듈
====================================

SampleStrategy(MA5/20 크로스 + RSI 역추세 예제 전략) 전용 EOD 스크리너.

SampleStrategy 진입 철학(strategy.py `_check_buy`)에 맞춰 D-1 시점 일봉으로
실제 진입 가능한 과매도/완만한 추세 종목을 선정한다.

후보 기준 (D-1 확정 일봉 기준):
  1차: 시장 필터 (KOSPI+KOSDAQ, 우선주/ETF 제외)
  2차: 거래대금 필터 (직전 N영업일 평균 ≥ min_trading_value) — 유동성 확보
  3차: 기술적 필터 — RSI < rsi_max  또는  (MA5 > MA20 AND RSI < rsi_trend_max)
       즉 SampleStrategy 가 실제로 진입할 수 있는 과매도/완만한 추세 종목
  최종: 점수 순 정렬 (RSI 낮을수록·거래대금 클수록 가점)

realtime / historical 분기 (lynch/sawkami 스크리너 패턴 모방):
  - scan_date >= today  → `_scan_realtime`: KIS 일봉 API 라이브 조회
  - scan_date <  today  → `_scan_historical`: strategy_analysis.daily_candles DB 조회

  외부 DB(strategy_analysis.daily_candles)는 2026-02 까지만 적재되어 stale 하므로
  EOD 훅(scan_date=오늘)에서는 반드시 realtime 경로로 KIS API 라이브 일봉을
  조회해야 한다. historical 경로만 쓰면 영구히 0건을 반환한다.

룩어헤드 방지:
  realtime/historical 모두 스캔 기준일(scan_date)의 직전 영업일(D-1)까지의
  확정 일봉만 사용한다. 당일(scan_date) 일봉은 EOD 시점에 종가가 확정되더라도
  다음 영업일 매매를 위한 스크리닝이므로 사용하지 않는다.
  - historical: get_daily_candles_range 의 end_date 를 D-1 로 지정.
  - realtime:   KIS 일봉 API 응답에서 stck_bsop_date >= scan_date 인 봉을 제외.

기존 lynch/bb_reversion/sawkami 스크리너 패턴(ScreenerBase 어댑터, scan_realtime
/scan_historical 분기, 실패 시 빈 리스트 반환)을 그대로 따른다.
"""

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.candidate_selector import CandidateStock
from strategies.screener_base import ScreenerBase
from strategies.historical_data import get_daily_candles_range
from utils.indicators import calculate_rsi_latest
from utils.korean_time import get_previous_trading_day

logger = logging.getLogger(__name__)


# ETF/ETN 브랜드 키워드 (core.candidate_selector.CandidateSelector.ETF_KEYWORDS 재사용)
_ETF_KEYWORDS = [
    'KODEX', 'TIGER', 'KBSTAR', 'ARIRANG', 'HANARO', 'SOL',
    'ACE', 'KOSEF', 'SMART', 'TIMEFOLIO', 'PLUS', 'VITA',
    'ETF', 'ETN', 'FOCUS', 'BNK', 'WOORI',
]

# realtime KIS API 호출 간격 (초) — lynch/sawkami 의 API_CALL_DELAY 와 동일
_API_CALL_DELAY = 0.15


def _is_etf_or_etn(name: str) -> bool:
    """종목명에 ETF/ETN 브랜드 키워드가 있으면 True."""
    if not name:
        return False
    upper = name.upper()
    return any(kw in upper for kw in _ETF_KEYWORDS)


def _is_preferred_stock(code: str, name: str) -> bool:
    """우선주 판정 — 종목코드 끝자리가 0이 아니거나 종목명에 '우' 접미."""
    if code and len(code) == 6 and not code.endswith('0'):
        return True
    if name and (name.endswith('우') or name.endswith('우B') or name.endswith('우C')):
        return True
    return False


def _safe_float(value, default: float = 0.0) -> float:
    """KIS API 문자열 응답값을 float 으로 안전 변환 (콤마 제거)."""
    if value is None or value == '':
        return default
    try:
        return float(str(value).replace(',', ''))
    except (ValueError, TypeError):
        return default


class SampleScreener:
    """SampleStrategy 철학에 맞는 D-1 후보 스캐너 (stateless).

    historical 경로(과거 날짜)는 strategy_analysis.daily_candles DB 만 사용한다.
    realtime 경로(오늘/미래)는 KIS 일봉 API 로 라이브 일봉을 조회한다.
    SampleStrategy 의 지표는 모두 가격/거래량 파생값이므로 재무 데이터가 필요 없다.
    """

    def scan_candidates(
        self,
        scan_date: date,
        rsi_period: int = 14,
        rsi_max: float = 45.0,
        rsi_trend_max: float = 60.0,
        ma_short: int = 5,
        ma_long: int = 20,
        min_trading_value: float = 500_000_000,
        trading_value_lookback: int = 20,
        max_candidates: int = 10,
    ) -> List[CandidateStock]:
        """D-1(직전 영업일) 확정 일봉으로 SampleStrategy 후보를 스캔한다 (historical).

        과거 날짜 기준 스캔 — strategy_analysis.daily_candles DB 를 조회한다.
        오늘/미래 날짜는 SampleScreenerAdapter.scan() 이 _scan_realtime 으로 분기하므로
        이 메서드는 historical(과거) 경로 전용이다.

        Args:
            scan_date: 스캔 기준일. 실제 일봉은 D-1 까지만 사용 (룩어헤드 방지).
            rsi_period: RSI 계산 기간.
            rsi_max: 단독 과매도 진입 임계값 (RSI < rsi_max 면 후보).
            rsi_trend_max: MA5>MA20 추세 시 RSI 상한 (RSI < rsi_trend_max 면 후보).
            ma_short / ma_long: 이동평균 기간.
            min_trading_value: 직전 평균 거래대금 하한 (유동성 필터).
            trading_value_lookback: 거래대금 평균 산출 영업일 수.
            max_candidates: 최대 후보 수.

        Returns:
            CandidateStock 리스트 (점수 내림차순). 실패 시 빈 리스트.
        """
        try:
            # --- 룩어헤드 방지: D-1 까지만 ---------------------------------
            # scan_date 당일 일봉은 사용하지 않는다. 직전 영업일을 종료일로.
            cutoff = get_previous_trading_day(
                datetime(scan_date.year, scan_date.month, scan_date.day)
            ).date()

            # MA20 + RSI14 + 거래대금 lookback 을 모두 커버할 일봉 기간 확보.
            # 캘린더 여유분 포함 (주말·공휴일 고려해 넉넉히 2배 + 30일).
            need_bars = max(ma_long, rsi_period + 1, trading_value_lookback)
            lookback_days = need_bars * 2 + 30
            start = date.fromordinal(cutoff.toordinal() - lookback_days)

            # --- 1차: 대상 종목 + 일봉 로드 --------------------------------
            # daily_candles 에서 cutoff 까지의 종목별 일봉을 일괄 로드.
            # 전 종목 대상이므로 stock_codes 는 stock_sector 에서 취득.
            stock_meta = self._load_market_stocks()
            if not stock_meta:
                logger.warning(
                    "Sample screener: 대상 종목 목록 없음 (scan_date=%s)", scan_date
                )
                return []

            stock_codes = list(stock_meta.keys())
            candles = get_daily_candles_range(stock_codes, start, cutoff)
            if not candles:
                logger.warning(
                    "Sample screener: 일봉 데이터 없음 (cutoff=%s)", cutoff
                )
                return []

            # --- 2~3차: 거래대금 + 기술적 필터 + 점수 ----------------------
            candidates: List[CandidateStock] = []
            min_bars = max(ma_long, rsi_period + 1)

            for code, df in candles.items():
                if df is None or len(df) < min_bars:
                    continue

                closes = df["close"].astype(float)
                volumes = df["volume"].astype(float)
                tvals = df["trading_value"].astype(float)

                # 2차: 직전 평균 거래대금 (유동성) — D-1 까지의 마지막 N봉
                avg_tv = float(tvals.tail(trading_value_lookback).mean())
                if pd.isna(avg_tv) or avg_tv < min_trading_value:
                    continue

                # 기술적 지표 — 모두 D-1 종가까지로 산출
                ma_s = float(closes.tail(ma_short).mean())
                ma_l = float(closes.tail(ma_long).mean())
                rsi_val = calculate_rsi_latest(closes, rsi_period)
                if rsi_val is None:
                    continue

                # 3차: SampleStrategy 진입 가능 조건
                #   (a) 과매도:        RSI < rsi_max
                #   (b) 완만한 추세:   MA5 > MA20 AND RSI < rsi_trend_max
                is_oversold = rsi_val < rsi_max
                is_trend = (ma_s > ma_l) and (rsi_val < rsi_trend_max)
                if not (is_oversold or is_trend):
                    continue

                meta = stock_meta.get(code, {})
                candidate = self._build_candidate(
                    code=code,
                    name=meta.get("name", ""),
                    market=meta.get("market", ""),
                    rsi_val=rsi_val,
                    avg_tv=avg_tv,
                    is_oversold=is_oversold,
                    is_trend=is_trend,
                    ma_short=ma_short,
                    ma_long=ma_long,
                    prev_close=float(closes.iloc[-1]),
                    cutoff=cutoff,
                )
                candidates.append(candidate)

            candidates.sort(key=lambda c: c.score, reverse=True)
            selected = candidates[:max_candidates]
            logger.info(
                "Sample screener (scan_date=%s, cutoff=%s): 후보 %d종목 "
                "(필터 통과 %d → 상위 %d)",
                scan_date, cutoff, len(selected), len(candidates), len(selected),
            )
            return selected

        except Exception as exc:
            logger.warning("Sample screener scan 실패 (%s): %s", scan_date, exc)
            return []

    def scan_candidates_realtime(
        self,
        scan_date: date,
        rsi_period: int = 14,
        rsi_max: float = 45.0,
        rsi_trend_max: float = 60.0,
        ma_short: int = 5,
        ma_long: int = 20,
        min_trading_value: float = 500_000_000,
        trading_value_lookback: int = 20,
        max_candidates: int = 10,
    ) -> List[CandidateStock]:
        """KIS 일봉 API 라이브 조회로 SampleStrategy 후보를 스캔한다 (realtime).

        오늘/미래 날짜 기준 스캔. strategy_analysis.daily_candles DB 가 stale 하므로
        KIS 일봉 API(get_inquire_daily_itemchartprice)로 라이브 일봉을 조회한다.
        lynch._scan_realtime / sawkami._apply_technical_filters 와 동일하게 KIS API
        를 사용하되, 룩어헤드 방지를 위해 응답에서 당일(scan_date) 봉을 제외한다.

        룩어헤드 방지: KIS 일봉 API 응답(stck_bsop_date, YYYYMMDD)에서
        scan_date 이상인 봉은 모두 버리고 D-1(직전 영업일)까지의 확정 봉만 쓴다.

        Returns:
            CandidateStock 리스트 (점수 내림차순). 실패 시 빈 리스트.
        """
        try:
            from api.kis_market_api import get_inquire_daily_itemchartprice

            cutoff = get_previous_trading_day(
                datetime(scan_date.year, scan_date.month, scan_date.day)
            ).date()

            # --- 1차: universe 로드 (lynch/sawkami 와 동일하게 stock_list.json) ---
            stock_meta = self._load_realtime_universe()
            if not stock_meta:
                logger.warning(
                    "Sample screener realtime: universe 없음 (scan_date=%s)", scan_date
                )
                return []

            # KIS 일봉 API 조회 기간: MA20 + RSI14 + 거래대금 lookback 커버.
            # 캘린더 여유분 포함 (주말·공휴일 고려해 넉넉히 2배 + 30일).
            need_bars = max(ma_long, rsi_period + 1, trading_value_lookback)
            lookback_days = need_bars * 2 + 30
            inqr_strt_dt = (
                cutoff - timedelta(days=lookback_days)
            ).strftime("%Y%m%d")
            inqr_end_dt = scan_date.strftime("%Y%m%d")
            scan_date_str = scan_date.strftime("%Y%m%d")

            min_bars = max(ma_long, rsi_period + 1)
            candidates: List[CandidateStock] = []

            for code, meta in stock_meta.items():
                try:
                    daily_df = get_inquire_daily_itemchartprice(
                        output_dv="2", itm_no=code,
                        inqr_strt_dt=inqr_strt_dt, inqr_end_dt=inqr_end_dt,
                    )
                    if daily_df is None or daily_df.empty:
                        continue

                    df = self._normalize_kis_daily(daily_df, scan_date_str)
                    if df is None or len(df) < min_bars:
                        continue

                    closes = df["close"]
                    tvals = df["trading_value"]

                    # 2차: 직전 평균 거래대금 (유동성) — D-1 까지의 마지막 N봉
                    avg_tv = float(tvals.tail(trading_value_lookback).mean())
                    if pd.isna(avg_tv) or avg_tv < min_trading_value:
                        continue

                    # 기술적 지표 — 모두 D-1 종가까지로 산출
                    ma_s = float(closes.tail(ma_short).mean())
                    ma_l = float(closes.tail(ma_long).mean())
                    rsi_val = calculate_rsi_latest(closes, rsi_period)
                    if rsi_val is None:
                        continue

                    is_oversold = rsi_val < rsi_max
                    is_trend = (ma_s > ma_l) and (rsi_val < rsi_trend_max)
                    if not (is_oversold or is_trend):
                        continue

                    candidate = self._build_candidate(
                        code=code,
                        name=meta.get("name", ""),
                        market=meta.get("market", ""),
                        rsi_val=rsi_val,
                        avg_tv=avg_tv,
                        is_oversold=is_oversold,
                        is_trend=is_trend,
                        ma_short=ma_short,
                        ma_long=ma_long,
                        prev_close=float(closes.iloc[-1]),
                        cutoff=cutoff,
                    )
                    candidates.append(candidate)

                except Exception as exc:
                    logger.warning(
                        "Sample screener realtime 종목 처리 실패 %s: %s", code, exc
                    )
                    continue

                time.sleep(_API_CALL_DELAY)

            candidates.sort(key=lambda c: c.score, reverse=True)
            selected = candidates[:max_candidates]
            logger.info(
                "Sample screener realtime (scan_date=%s, cutoff=%s): 후보 %d종목 "
                "(필터 통과 %d → 상위 %d)",
                scan_date, cutoff, len(selected), len(candidates), len(selected),
            )
            return selected

        except Exception as exc:
            logger.warning("Sample screener realtime scan 실패 (%s): %s", scan_date, exc)
            return []

    @staticmethod
    def _normalize_kis_daily(
        daily_df: pd.DataFrame, scan_date_str: str
    ) -> Optional[pd.DataFrame]:
        """KIS 일봉 API output2 DataFrame 을 정규화한다 (룩어헤드 방지 포함).

        KIS 일봉 응답(output2)은 stck_bsop_date(YYYYMMDD), stck_clpr(종가),
        acml_vol(거래량), acml_tr_pbmn(거래대금) 컬럼을 갖는다.
        룩어헤드 방지: stck_bsop_date >= scan_date 인 봉(당일/미래 봉)을 제거한다.

        Returns:
            DataFrame[close, volume, trading_value] (날짜 오름차순). 실패 시 None.
        """
        if daily_df is None or daily_df.empty:
            return None
        if "stck_bsop_date" not in daily_df.columns:
            return None

        df = daily_df.copy()
        df["stck_bsop_date"] = df["stck_bsop_date"].astype(str)

        # --- 룩어헤드 방지: 당일(scan_date) 이상 봉 제거 ---
        df = df[df["stck_bsop_date"] < scan_date_str]
        if df.empty:
            return None

        # 날짜 오름차순 정렬 (KIS 응답은 최신순일 수 있음)
        df = df.sort_values("stck_bsop_date").reset_index(drop=True)

        close_col = "stck_clpr" if "stck_clpr" in df.columns else None
        vol_col = "acml_vol" if "acml_vol" in df.columns else None
        tval_col = "acml_tr_pbmn" if "acml_tr_pbmn" in df.columns else None
        if close_col is None:
            return None

        closes = df[close_col].apply(_safe_float)
        if vol_col is not None:
            volumes = df[vol_col].apply(_safe_float)
        else:
            volumes = pd.Series([0.0] * len(df))
        if tval_col is not None:
            tvals = df[tval_col].apply(_safe_float)
        else:
            # 거래대금 컬럼이 없으면 종가 x 거래량 으로 근사
            tvals = closes * volumes

        out = pd.DataFrame({
            "close": closes,
            "volume": volumes,
            "trading_value": tvals,
        }).reset_index(drop=True)
        # 종가 0 이하(거래정지 등) 행 제거
        out = out[out["close"] > 0].reset_index(drop=True)
        return out

    @staticmethod
    def _build_candidate(
        code: str,
        name: str,
        market: str,
        rsi_val: float,
        avg_tv: float,
        is_oversold: bool,
        is_trend: bool,
        ma_short: int,
        ma_long: int,
        prev_close: float,
        cutoff: date,
    ) -> CandidateStock:
        """필터 통과 종목을 CandidateStock 으로 변환 (점수·사유 동일 산식).

        realtime/historical 두 경로가 동일한 점수 산식을 쓰도록 공통화한다.
        점수: RSI 낮을수록 + 거래대금 클수록 가점 (0~100 근사).
        """
        rsi_score = max(0.0, (100.0 - rsi_val))          # 0~100
        liquidity_score = min(20.0, avg_tv / 1e9 * 2.0)  # 거래대금 가점 0~20
        trend_bonus = 10.0 if is_trend else 0.0
        score = round(rsi_score * 0.7 + liquidity_score + trend_bonus, 2)

        tag = []
        if is_oversold:
            tag.append(f"과매도 RSI {rsi_val:.1f}")
        if is_trend:
            tag.append(f"MA{ma_short}>MA{ma_long} 추세")
        reason = (
            f"{', '.join(tag)}, 거래대금 {avg_tv / 1e8:.1f}억, "
            f"cutoff={cutoff}"
        )

        return CandidateStock(
            code=code,
            name=name,
            market=market,
            score=score,
            reason=reason,
            prev_close=prev_close,
        )

    @staticmethod
    def _load_market_stocks() -> Dict[str, Dict[str, str]]:
        """KOSPI+KOSDAQ 대상 종목 메타 로드 (우선주/ETF 제외) — historical 경로.

        strategy_analysis.stock_sector 를 종목 universe 로 사용한다.
        bb_reversion 스크리너가 같은 테이블을 쓰므로 외부 DB 의존성 동일.
        반환: {stock_code: {"name": str, "market": str}}
        """
        from strategies.historical_data import get_sectors

        meta: Dict[str, Dict[str, str]] = {}
        try:
            df = get_sectors()  # 전 섹터
            if df.empty:
                return {}
            for _, row in df.iterrows():
                code = str(row["stock_code"])
                name = str(row.get("stock_name", "") or "")
                market = str(row.get("market", "") or "")
                if market not in ("KOSPI", "KOSDAQ"):
                    continue
                if _is_preferred_stock(code, name):
                    continue
                if _is_etf_or_etn(name):
                    continue
                meta[code] = {"name": name, "market": market}
        except Exception as exc:
            logger.warning("Sample screener: 종목 universe 로드 실패: %s", exc)
            return {}
        return meta

    # lynch/sawkami 의 CandidateSelector._load_stock_list() 가 읽는 종목 리스트 파일.
    # 같은 파일(stock_list.json)을 realtime 경로 universe 로 사용한다.
    _STOCK_LIST_FILE = Path(__file__).resolve().parents[2] / "stock_list.json"

    @classmethod
    def _load_realtime_universe(cls) -> Dict[str, Dict[str, str]]:
        """realtime 경로 universe 로드 — lynch/sawkami 와 동일하게 stock_list.json.

        lynch/sawkami 의 CandidateSelector._load_stock_list() 가 읽는 것과 같은
        stock_list.json 을 universe 로 쓴다. stock_sector 테이블의 market 컬럼이
        전부 "KOSPI"로 부정확하므로 realtime 경로는 이를 쓰지 않는다.
        우선주/ETF 는 제외한다.
        반환: {stock_code: {"name": str, "market": str}}
        """
        meta: Dict[str, Dict[str, str]] = {}
        try:
            if not cls._STOCK_LIST_FILE.exists():
                logger.warning(
                    "Sample screener realtime: 종목 리스트 파일 없음 (%s)",
                    cls._STOCK_LIST_FILE,
                )
                return {}
            with open(cls._STOCK_LIST_FILE, "r", encoding="utf-8") as f:
                stocks = json.load(f).get("stocks", [])
            for stock in stocks or []:
                code = str(stock.get("code", "") or "")
                name = str(stock.get("name", "") or "")
                market = str(stock.get("market", "") or "")
                if not code:
                    continue
                if _is_preferred_stock(code, name):
                    continue
                if _is_etf_or_etn(name):
                    continue
                meta[code] = {"name": name, "market": market}
        except Exception as exc:
            logger.warning("Sample screener realtime: universe 로드 실패: %s", exc)
            return {}
        return meta


class SampleScreenerAdapter(ScreenerBase):
    """SampleScreener 를 ScreenerBase 인터페이스로 감싸는 어댑터.

    lynch/sawkami 어댑터와 동일하게 scan() 에서 realtime/historical 을 분기한다.
      - scan_date >= today → _scan_realtime: KIS 일봉 API 라이브 조회
      - scan_date <  today → _scan_historical: strategy_analysis.daily_candles DB

    daily_candles DB 가 stale 하므로 EOD 훅(scan_date=오늘)은 반드시 realtime
    경로를 타야 후보를 반환할 수 있다.
    """

    strategy_name = "sample"

    def __init__(self, config=None, broker=None, db_manager=None) -> None:
        # SampleScreener 는 config/broker/db_manager 미사용 —
        # 어댑터 시그니처 통일을 위해 수용 (bb_reversion 어댑터와 동일).
        self._config = config
        self._broker = broker
        self._db_manager = db_manager
        self._screener = SampleScreener()

    def default_params(self) -> Dict[str, Any]:
        return {
            "rsi_period": 14,
            "rsi_max": 45.0,
            "rsi_trend_max": 60.0,
            "ma_short": 5,
            "ma_long": 20,
            "min_trading_value": 500_000_000,
            "trading_value_lookback": 20,
            "max_candidates": 10,
        }

    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        """scan_date 기준 후보 스캔. realtime/historical 을 분기한다.

        lynch/sawkami 어댑터와 동일하게 scan_date 가 오늘 이후면 realtime,
        과거면 historical 경로를 호출한다.
        """
        today = datetime.now().date()
        if scan_date >= today:
            return self._scan_realtime(scan_date, params)
        return self._scan_historical(scan_date, params)

    def _scan_realtime(
        self, scan_date: date, params: Dict[str, Any]
    ) -> List[CandidateStock]:
        """현재 시점(오늘/미래) — KIS 일봉 API 라이브 조회 경로.

        외부 DB 가 stale 하므로 KIS API 로 라이브 일봉을 조회한다.
        룩어헤드 방지는 SampleScreener.scan_candidates_realtime 가 D-1 까지만
        쓰도록(당일 봉 제외) 보장한다.
        """
        merged = {**self.default_params(), **(params or {})}
        return self._screener.scan_candidates_realtime(
            scan_date=scan_date,
            rsi_period=int(merged.get("rsi_period", 14)),
            rsi_max=float(merged.get("rsi_max", 45.0)),
            rsi_trend_max=float(merged.get("rsi_trend_max", 60.0)),
            ma_short=int(merged.get("ma_short", 5)),
            ma_long=int(merged.get("ma_long", 20)),
            min_trading_value=float(merged.get("min_trading_value", 500_000_000)),
            trading_value_lookback=int(merged.get("trading_value_lookback", 20)),
            max_candidates=int(merged.get("max_candidates", 10)),
        )

    def _scan_historical(
        self, scan_date: date, params: Dict[str, Any]
    ) -> List[CandidateStock]:
        """과거 특정일 — strategy_analysis.daily_candles DB 조회 경로.

        과거 시점은 외부 DB 에 확정 일봉이 적재되어 있으므로 DB 를 쓴다.
        """
        merged = {**self.default_params(), **(params or {})}
        return self._screener.scan_candidates(
            scan_date=scan_date,
            rsi_period=int(merged.get("rsi_period", 14)),
            rsi_max=float(merged.get("rsi_max", 45.0)),
            rsi_trend_max=float(merged.get("rsi_trend_max", 60.0)),
            ma_short=int(merged.get("ma_short", 5)),
            ma_long=int(merged.get("ma_long", 20)),
            min_trading_value=float(merged.get("min_trading_value", 500_000_000)),
            trading_value_lookback=int(merged.get("trading_value_lookback", 20)),
            max_candidates=int(merged.get("max_candidates", 10)),
        )
