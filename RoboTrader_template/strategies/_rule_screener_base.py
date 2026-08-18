"""RuleScreenerBase — 전략 진입룰을 daily_prices 유니버스에 적용하는 공통 스크리너."""
from __future__ import annotations

from abc import abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies.screener_base import ScreenerBase
from core.candidate_selector import CandidateStock
from utils.data_sanity import describe_impossible_drop
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RuleScreenerBase(ScreenerBase):
    strategy_name: str = "rule_screener_base"
    lookback_days: int = 120

    def __init__(self, config=None, broker=None, db_manager=None) -> None:
        self._config = config
        self._broker = broker
        self._db_manager = db_manager
        self._quant = None

    def _quant_reader(self):
        if self._quant is None:
            from db.quant_daily_reader import QuantDailyReader
            self._quant = QuantDailyReader()
        return self._quant

    @staticmethod
    def _passes_market_cap(
        mcap: Optional[float],
        *,
        min_cap: Optional[float] = None,
        max_cap: Optional[float] = None,
        max_inclusive: bool = False,
    ) -> bool:
        """시총 가드 (fail-closed). 통과 시 True, 제외 시 False.

        결측(None)·0·음수면 전략 컨셉(대형/중소형) 검증이 불가능하므로 **무조건 제외**.
        라이브 경로는 ``COALESCE(market_cap,0)`` 로 결측이 0 으로 들어오므로 ``<=0`` 가
        실제 결측을 잡는다(None 은 방어). 시총이 채워진 종목엔 하한/상한 컷만 적용해
        기존(라이브) 동작을 그대로 보존한다.

        Args:
            mcap: 종목 시가총액(원). None/0/음수 = 결측 → 제외.
            min_cap: 하한(이상). ``mcap < min_cap`` 이면 제외.
            max_cap: 상한. ``max_inclusive=False``(기본)면 ``mcap >= max_cap`` 제외
                ('미만' 컨셉, daytrading). True 면 ``mcap > max_cap`` 제외('이하' 컨셉,
                ma5/ma20).
        """
        if mcap is None or mcap <= 0:
            return False
        if min_cap is not None and mcap < min_cap:
            return False
        if max_cap is not None:
            if max_inclusive:
                if mcap > max_cap:
                    return False
            elif mcap >= max_cap:
                return False
        return True

    @abstractmethod
    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """유니버스(dict 리스트)에서 전략 성격에 맞는 종목만 추린다."""

    @abstractmethod
    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        """진입룰 적용. 통과 시 (score, reason), 탈락 시 None."""

    def default_params(self) -> Dict[str, Any]:
        return {"max_candidates": 10}

    # ── 횡단면 컨텍스트 훅 (2026-08-18) ──────────────────────────────────────
    # 일부 진입 룰은 «그 종목 하나»의 일봉만으로는 평가할 수 없다. Minervini
    # Trend Template 의 8번째 조건(RS 백분위)이 그렇다 — 같은 날 유니버스 전체를
    # 줄 세워야 나오는 값이라, 종목별 루프 «안»에서는 원리적으로 계산이 안 된다.
    # 그래서 scan() 을 2패스로 나눈다: ①모든 적격 종목의 일봉을 먼저 모으고
    # ②그 집합으로 컨텍스트를 만든 뒤 ③룰을 평가한다.
    #
    # 🔑 기본값은 「컨텍스트 없음」이라 이 훅을 안 쓰는 어댑터의 동작은 «불변»이다.
    wants_context: bool = False

    # `describe_impossible_drop` 가 훑는 창. None 이면 로드한 일봉 전체.
    # 🔑 이게 필요한 이유: `lookback_days` 를 늘리면 위생 가드가 «더 넓은 구간»을
    #    보게 되어 제외 종목이 늘고, 그건 진입 룰을 안 건드렸는데도 후보 집합이
    #    바뀌는 것이다. 창을 늘리는 변경과 가드 범위를 넓히는 변경을 분리하려면
    #    가드 창을 명시적으로 고정해야 한다. (「한 번에 한 축만 움직인다」)
    sanity_window: Optional[int] = None

    def build_context(
        self, frames: Dict[str, pd.DataFrame], scan_date: date
    ) -> Dict[str, Dict[str, Any]]:
        """`{code: ctx}` 를 만든다. 기본은 빈 dict — 어댑터가 필요하면 override."""
        return {}

    def finalize_scan(self, diag: Dict[str, Any]) -> None:
        """스캔 1회가 끝난 뒤 호출되는 진단 훅. 기본 no-op."""

    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        merged = {**self.default_params(), **(params or {})}
        max_candidates = int(merged.get("max_candidates", 10))
        universe = self.base_filter(self._load_universe(scan_date))

        stats = {"n_no_data": 0, "n_impossible": 0}

        if self.wants_context:
            # 2패스 — 횡단면 컨텍스트가 필요한 어댑터만. 적격 종목의 일봉을 전부
            # 들고 있어야 하므로 메모리를 더 쓴다. 그래서 «필요한 어댑터만» 탄다.
            frames: Dict[str, pd.DataFrame] = {}
            meta: Dict[str, Dict[str, Any]] = {}
            for u in universe:
                df = self._prepare_frame(u["code"], scan_date, stats)
                if df is None:
                    continue
                frames[u["code"]] = df
                meta[u["code"]] = u
            ctxs = self.build_context(frames, scan_date) or {}
            pairs = ((code, df, meta[code], ctxs.get(code) or {})
                     for code, df in frames.items())
        else:
            # 기존 스트리밍 경로 — 동작·메모리 프로파일 «불변».
            pairs = ((u["code"], df, u, None) for u, df in (
                (u, self._prepare_frame(u["code"], scan_date, stats)) for u in universe
            ) if df is not None)

        scored: List[Tuple[float, CandidateStock]] = []
        n_evaluated = 0
        for code, df, u, ctx in pairs:
            n_evaluated += 1
            verdict = self.match(df, merged) if ctx is None else self.match(df, merged, ctx)
            if verdict is None:
                continue
            score, reason = verdict
            prev_close = float(df["close"].iloc[-1])
            if not (prev_close > 0):
                continue
            scored.append((score, CandidateStock(
                code=code, name=u.get("name", code), market=u.get("market", "KRX"),
                score=float(score), reason=reason, prev_close=prev_close,
            )))
        scored.sort(key=lambda t: t[0], reverse=True)
        selected = [c for _, c in scored[:max_candidates]]

        self.finalize_scan({
            "scan_date": scan_date,
            "n_universe": len(universe),
            "n_no_data": stats["n_no_data"],
            "n_impossible": stats["n_impossible"],
            "n_evaluated": n_evaluated,
            "n_matched": len(scored),
            "n_selected": len(selected),
        })
        return selected

    def _prepare_frame(
        self, code: str, scan_date: date, stats: Dict[str, int]
    ) -> Optional[pd.DataFrame]:
        """일봉 적재 + 날짜 컷 + 불가능봉 가드. 탈락이면 None."""
        df = self._load_daily(code, scan_date)
        if df is None or df.empty:
            stats["n_no_data"] += 1
            return None
        df = df[df["date"].dt.date <= scan_date]
        if df.empty:
            stats["n_no_data"] += 1
            return None
        # ★ 불가능봉 가드 (2026-08-15 감사) — KRX 한도(±30%)를 넘는 «하락» 봉은
        #   조정되지 않은 기업행위가 남긴 인공물이다. 그 창으로 지표를 계산하면
        #   가짜 폭락으로 오진한다(실측: deep_mr 후보 4건이 이 경로).
        #   ⚠️ 데이터 위생이지 전략 변경이 아니다 — utils/data_sanity.py 참조.
        sane_view = df if self.sanity_window is None else df.iloc[-self.sanity_window:]
        bad = describe_impossible_drop(sane_view)
        if bad:
            logger.warning("[%s] %s: %s — 미조정 기업행위 의심, 후보 제외",
                           self.strategy_name, code, bad)
            stats["n_impossible"] += 1
            return None
        return df

    def _load_universe(self, scan_date: date) -> List[Dict[str, Any]]:
        snapshot = self._quant_reader().get_universe_snapshot(scan_date)
        return [
            {"code": it["stock_code"], "name": it["stock_code"],
             "market_cap": it["market_cap"], "trading_value": it["trading_value"]}
            for it in snapshot
        ]

    def _load_daily(self, code: str, scan_date: date) -> Optional[pd.DataFrame]:
        return self._quant_reader().get_daily_prices(code, end_date=scan_date, days=self.lookback_days)
