"""유지윤 전고 돌파 전략 EOD 스크리너 어댑터.

2026-10-27 — 미조정 기업행위(병합·분할) 의심 종목 제외(사장님 결정 「㉯ 앞당겨 수정」).
계기: 10-27 실전 368600(주식병합 · 24봉 정지 → 10-22 재개 · 일봉 미조정)이 후보 2위 → 매수 → 손절.
가드는 rs_leader 모듈 «재사용»(`strategies/rs_leader/corp_action_guard.py` · 임계 단일 소스 =
`collectors.corp_action_watch`) · 모드 = `config.constants.DT_CORP_ACTION_MODE`(기본 live).
배제는 정렬·topK «앞»이라 빠진 자리는 다음 순위가 채운다.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.candidate_selector import CandidateStock
from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
from strategies.rs_leader import corp_action_guard as corp_action
from utils.logger import setup_logger

logger = setup_logger(__name__)


class Daytrading3MethodsBreakoutScreenerAdapter(RuleScreenerBase):
    strategy_name = "daytrading_3methods_breakout"
    lookback_days = 60

    def default_params(self) -> Dict[str, Any]:
        return {
            # high_window=15: 라이브 config.yaml/strategy 검증값과 일치(멀티버스 2026-06-02
            # rank1). 이전 20은 스크리너만 더 엄격해 후보-진입 정의 불일치였음(감사 2026-06-23).
            "high_window": 15,
            "vol_lookback": 20,
            "vol_mult": 2.0,
            "max_market_cap": 500_000_000_000,  # 5천억 미만
            "min_trading_value": 1_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # '중소형(5천억 미만)' 컨셉. 시총 결측(0/None)이면 검증 불가 → fail-closed 제외
        # (상한형은 `0 >= max` 가 False 라 과거엔 결측이 조용히 통과했음). 시장 라벨 게이트 없음.
        p = self.default_params()
        out = []
        for u in universe:
            if not self._passes_market_cap(u.get("market_cap"), max_cap=p["max_market_cap"]):
                continue
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

    # ── 미조정 기업행위 배제 (2026-10-27) ───────────────────────────────────
    # 🔑 «scan() 경로 안에서만» 돈다 — 연구 러너(`backtest/concept_axes/candidate_ledger`·
    #    `replayer`)는 `match()` 를 직접 부르므로 거기까지 켜지면 재현이 조용히 바뀐다
    #    (rs_leader `screener.py` scan() docstring 과 같은 이유 · 명시적 플래그로 가른다).

    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        self._ca_active = True
        self._ca_flagged: List[str] = []
        try:
            return super().scan(scan_date, params)
        finally:
            self._ca_active = False
            self._ca_flagged = []

    def _prepare_frame(self, code: str, scan_date: date,
                       stats: Dict[str, int]) -> Optional[pd.DataFrame]:
        """기존 동작 그대로 + 배제 로그용 종목코드를 프레임에 실어 준다."""
        df = super()._prepare_frame(code, scan_date, stats)
        if df is not None:
            df.attrs["stock_code"] = code
        return df

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        verdict = self._rule_verdict(df, params)
        if verdict is None or not getattr(self, "_ca_active", False):
            return verdict
        mode, _invalid = corp_action.resolve_mode("DT")
        if mode == "off":
            return verdict
        # 룰 통과 종목만 판정 — 로그 1줄 = «후보를 실제로 1개 뺐다(live)/뺄 뻔했다(shadow)».
        code = str(df.attrs.get("stock_code") or "?")
        hit = corp_action.detect(code, df)
        if hit is None:
            return verdict
        self._ca_flagged.append(code)
        tail = ("— 후보 제외 (mode=live)" if mode == "live"
                else f"— 후보 제외 «안 함»(mode={mode})")
        logger.warning("[%s] %s: %s %s", self.strategy_name, code, corp_action.describe(hit), tail)
        return None if mode == "live" else verdict

    def finalize_scan(self, diag: Dict[str, Any]) -> None:
        """스캔당 1줄 — 이 줄의 유무·mode 값이 발효 계기(「배제 0건」과 「안 돌았다」 구별)."""
        super().finalize_scan(diag)
        mode, invalid = corp_action.resolve_mode("DT")
        if invalid is not None:
            logger.warning("%s", corp_action.invalid_mode_message(invalid, prefix="DT"))
        if mode != "off":
            flagged = getattr(self, "_ca_flagged", [])
            logger.info("[dt-corp-action] mode=%s scan_date=%s kept=%s flagged=%s codes=%s",
                        mode, diag.get("scan_date"), diag.get("n_matched"),
                        len(flagged), ",".join(flagged))

    def _rule_verdict(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        """전고 돌파 룰 + 거래량 배수 score — 2026-10-27 이전 `match()` 와 «동일»."""
        rule = rule_breakout_prev_high(
            high_window=int(params.get("high_window", 20)),
            vol_lookback=int(params.get("vol_lookback", 20)),
            vol_mult=float(params.get("vol_mult", 2.0)),
        )
        res = rule.evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["breakout_prev_high"])
        last_vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].iloc[-21:-1].mean()) or 1.0
        score = last_vol / avg_vol
        return (score, reason)
