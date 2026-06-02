"""라이브 PIT 일봉 국면 게이트 — RegimeGate.

전략별 `regime_gate`(exclude_bear / bull_only)를 라이브(가상/실전)에서 강제하기 위한
얇은 어댑터. 핵심 분류 로직은 절대 재구현하지 않고 검증된 PIT 분류기
`core.regime.regime_classifier.classify_daily` 를 그대로 호출한다(룩어헤드 보장).

데이터 SSOT:
  - 지수 종가: daily_prices(stock_code='KOSPI' 또는 'KOSDAQ') 종가.
  - breadth 패널: daily_prices 유니버스(후보/거래종목)의 종가 패널(%above MA120).
  - ★미확정 당일봉 제외: TradingContext._drop_unconfirmed_today_bar 와 동일 규칙
    (KST 오늘 trailing row 배제) — 장중 부분봉이 국면계산을 오염시키지 않도록.

캐시:
  국면은 일봉이라 장중 불변 → (지수, KST날짜)당 1회만 classify_daily 호출.
  봇 시작/일 변경 시 자동 갱신(날짜 키가 바뀌면 재계산).

안전 디폴트(fail-open):
  데이터부족·예외 시 current_regime()=None → 게이트는 매수를 차단하지 않음.
  (실거래에서 데이터 문제로 전 전략이 멈추는 사고 방지.)
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Optional, Tuple

import pandas as pd

from utils.logger import setup_logger
from utils.korean_time import now_kst
from core.regime.regime_classifier import DailyRegimeParams, classify_daily

# breadth 패널 구성을 위해 조회할 유니버스 종목 수 상한(과도한 DB 부하 방지).
_BREADTH_UNIVERSE_LIMIT = 200
# 지수/종목 일봉 조회 깊이(달력일). MA120 + 기울기/디바운스 여유 확보(영업일 ≈ 0.69×달력일).
_INDEX_LOOKBACK_DAYS = 400
# 지원 지수 코드 → daily_prices stock_code 매핑.
_INDEX_CODE: Dict[str, str] = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}


class RegimeGate:
    """라이브 일봉 국면 판정 + 일 1회 캐시."""

    def __init__(self, db_manager=None, params: Optional[DailyRegimeParams] = None):
        self.logger = setup_logger("regime_gate")
        self._db = db_manager
        self._params = params or DailyRegimeParams()
        # 캐시: key=(index_name, asof_date) -> regime str | None
        self._cache: Dict[Tuple[str, date], Optional[str]] = {}

    # ------------------------------------------------------------------
    # 미확정 당일봉 제거 (TradingContext._drop_unconfirmed_today_bar 와 동일 규칙)
    # ------------------------------------------------------------------
    @staticmethod
    def _drop_unconfirmed_today_bar(data: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """KST 오늘(장중 형성 중) 미완성 일봉을 마지막 봉에서 제외(no-lookahead).

        일봉 국면 계산은 '마지막 행=확정 봉' 을 전제하는 classify_daily 를 타므로,
        daily_prices 에 장중 부분 거래량으로 존재할 수 있는 당일 row 를 배제한다.
        date 컬럼이 없으면 변형 없이 반환(합성/테스트 데이터 하위호환).
        """
        if data is None or getattr(data, "empty", True):
            return data
        if "date" not in data.columns or len(data) == 0:
            return data
        try:
            last_date = pd.to_datetime(data["date"].iloc[-1]).date()
        except (ValueError, TypeError):
            return data
        if last_date == now_kst().date():
            return data.iloc[:-1].reset_index(drop=True)
        return data

    # ------------------------------------------------------------------
    # 데이터 로딩 (SSOT = daily_prices, 미확정 당일봉 제외)
    # ------------------------------------------------------------------
    def _price_repo(self):
        repo = getattr(self._db, "price_repo", None)
        if repo is None or not hasattr(repo, "get_daily_prices"):
            return None
        return repo

    def _load_index_close(self, index_name: str) -> Optional[pd.Series]:
        """지수 종가 시계열(index=date Timestamp). 미확정 당일봉 제외. 없으면 None."""
        repo = self._price_repo()
        if repo is None:
            return None
        code = _INDEX_CODE.get(index_name)
        if code is None:
            return None
        try:
            df = repo.get_daily_prices(code, days=_INDEX_LOOKBACK_DAYS)
        except Exception as e:  # pragma: no cover - DB 예외 방어
            self.logger.debug(f"지수 일봉 조회 실패 ({code}): {e}")
            return None
        df = self._drop_unconfirmed_today_bar(df)
        if df is None or getattr(df, "empty", True) or "close" not in df.columns:
            return None
        if "date" in df.columns:
            idx = pd.to_datetime(df["date"])
        else:
            idx = pd.RangeIndex(len(df))
        s = pd.Series(df["close"].astype(float).values, index=idx, name=code).sort_index()
        return s

    def _load_breadth_panel(self, idx: pd.Index) -> Optional[pd.DataFrame]:
        """유니버스 종가 패널(index=date, columns=stock_code). 없으면 None(추세+기울기만).

        후보/거래 유니버스를 candidate repo 또는 daily_prices 에서 가져온다. 조회가
        불가하면 None 을 반환해 classify_daily 가 breadth 확정 단계를 생략하도록 한다.
        """
        repo = self._price_repo()
        if repo is None:
            return None
        codes = self._universe_codes()
        if not codes:
            return None
        cols: Dict[str, pd.Series] = {}
        for code in codes[:_BREADTH_UNIVERSE_LIMIT]:
            try:
                df = repo.get_daily_prices(code, days=_INDEX_LOOKBACK_DAYS)
            except Exception:
                continue
            df = self._drop_unconfirmed_today_bar(df)
            if df is None or getattr(df, "empty", True) or "close" not in df.columns:
                continue
            if "date" in df.columns:
                s = pd.Series(
                    df["close"].astype(float).values,
                    index=pd.to_datetime(df["date"]),
                    name=code,
                )
                cols[code] = s.sort_index()
        if not cols:
            return None
        panel = pd.DataFrame(cols).sort_index()
        return panel

    def _universe_codes(self) -> list:
        """breadth 계산용 유니버스 종목 코드. candidate repo 우선, 실패 시 빈 리스트."""
        try:
            cand_repo = getattr(self._db, "candidate_repo", None)
            if cand_repo is not None and hasattr(cand_repo, "get_all_candidate_codes"):
                codes = cand_repo.get_all_candidate_codes()
                if codes:
                    return list(codes)
        except Exception:
            pass
        return []

    # ------------------------------------------------------------------
    # 국면 판정 (일 1회 캐시)
    # ------------------------------------------------------------------
    def current_regime(self, index_name: str) -> Optional[str]:
        """오늘(KST) 기준 PIT 일봉 국면 라벨. {'bull','bear','sideways'} 또는 None(불명).

        None 은 데이터 부족/예외 안전 디폴트 — 호출측 게이트는 차단하지 않는다(fail-open).
        """
        today = now_kst().date()
        key = (index_name, today)
        if key in self._cache:
            return self._cache[key]

        regime = self._compute_regime(index_name)
        self._cache[key] = regime
        return regime

    def _compute_regime(self, index_name: str) -> Optional[str]:
        try:
            close = self._load_index_close(index_name)
            if close is None or len(close) == 0:
                self.logger.info(
                    f"[국면게이트] {index_name} 지수 일봉 없음 — 게이트 미적용(안전 디폴트)"
                )
                return None
            panel = self._load_breadth_panel(close.index)
            res = classify_daily(close, panel, self._params)
            if res is None or res.empty:
                return None
            regime = str(res["regime"].iloc[-1])
            self.logger.info(
                f"[국면게이트] {index_name} 현재 국면: {regime.upper()} "
                f"(close {len(close)}봉, breadth={'유' if panel is not None else '무'})"
            )
            return regime
        except Exception as e:  # pragma: no cover - 분류 예외 방어
            self.logger.warning(f"[국면게이트] {index_name} 국면계산 실패(게이트 미적용): {e}")
            return None
