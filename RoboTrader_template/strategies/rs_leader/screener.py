"""횡보장 RS 리더 전략 EOD 스크리너 어댑터.

match 가 절대상승추세 통과 종목의 120일 수익률을 score 로 반환 → RuleScreenerBase.scan
의 정렬+topK 가 곧 횡단면 RS 랭킹(별도 패널 불요). 진입 추세 판정은 검증에서 쓴
strategies.rs_leader.rule.RSLeaderRule 단일 소스를 재사용(DRY).

2026-09-10 — 미조정 기업행위(합병) 의심 종목 배제(사장님 결정 (b), 기본 shadow).
spec: docs/superpowers/specs/2026-09-10-rsleader-corp-action-exclusion-design.md
배제는 정렬·topK «앞»이라 후보 수가 줄지 않는다(빠진 자리는 다음 순위가 백필).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.rs_leader import corp_action_guard as corp_action
from strategies.rs_leader.rule import RSLeaderRule
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RSLeaderScreenerAdapter(RuleScreenerBase):
    strategy_name = "rs_leader"
    lookback_days = 130  # MA60 + 120일 수익률 워밍업

    def __init__(self, config=None, broker=None, db_manager=None) -> None:
        super().__init__(config=config, broker=broker, db_manager=db_manager)
        self._ca_reset()

    def default_params(self) -> Dict[str, Any]:
        return {
            "ma_short": 20, "ma_long": 60, "abs_lb": 60, "rs_lb": 120,
            "min_trading_value": 1_000_000_000,
            "min_price": 1_000, "max_price": 500_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        out = []
        for u in universe:
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

    # ── 미조정 기업행위 배제 (2026-09-10) ───────────────────────────────────
    #
    # 왜 `match()` 안인가: 판정에 «일봉»이 필요하다. `base_filter` 는
    # {code, market_cap, trading_value} 만 받으므로(`_rule_screener_base.py:186-192`)
    # 일봉이 있는 가장 이른 지점이 `_prepare_frame` 다음 = `match` 진입 직후다.
    # (rs_leader 의 score 는 그 종목 «하나»의 120일 수익률이라 모집단을 줄여도 살아남은
    #  종목의 score 는 안 변한다 — 「RS 분모가 바뀐다」 우려는 여기 해당 없음. 그 우려가
    #  진짜인 곳은 minervini 의 `build_context` RS 백분위다.)

    def _ca_reset(self) -> None:
        self._ca_flagged: List[str] = []
        self._ca_kept: int = 0

    def _prepare_frame(self, code: str, scan_date: date,
                       stats: Dict[str, int]) -> Optional[pd.DataFrame]:
        """기존 동작 그대로 + 종목코드를 프레임에 실어 준다.

        `match(df, params)` 시그니처에는 종목코드가 없는데(공통 계약이라 안 바꾼다)
        배제 로그는 코드를 찍어야 한다 — 로드한 «그 프레임»에 붙여 전달한다.
        """
        df = super()._prepare_frame(code, scan_date, stats)
        if df is not None:
            df.attrs["stock_code"] = code
        return df

    def _rule_verdict(self, df: pd.DataFrame,
                      params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        """절대상승추세 룰 + 120일 수익률 score — 2026-09-10 이전과 «동일»."""
        rs_lb = int(params.get("rs_lb", 120))
        rule = RSLeaderRule(
            ma_short=int(params.get("ma_short", 20)),
            ma_long=int(params.get("ma_long", 60)),
            abs_lb=int(params.get("abs_lb", 60)),
        )
        close = df["close"].astype(float)
        last = float(close.iloc[-1])
        if last < params.get("min_price", 1_000) or last > params.get("max_price", 500_000):
            return None
        sig = rule.generate_signal("_", df, "daily")
        if sig is None:
            return None
        if len(close) <= rs_lb:
            return None
        ref = float(close.iloc[-1 - rs_lb])
        # RS 분모(과거 close) 0/NaN 가드: 손상된 일봉(과거 text-date 오염 등)이
        # ZeroDivisionError/NaN score 를 내지 않도록 방어. (rule.py 는 abs_lb 기준가만
        # 가드하고 screener 의 rs_lb 기준가는 미가드였음 — 감사 2026-06-23)
        if not (ref > 0):  # 0·음수·NaN 모두 차단(NaN 비교는 항상 False)
            return None
        rs_ret = last / ref - 1.0
        reason = f"RS리더: 절대상승추세 + {rs_lb}일수익률 {rs_ret * 100:+.1f}%"
        return (float(rs_ret), reason)  # score=RS수익률 → scan 정렬+topK = RS랭킹

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        mode, _invalid = corp_action.resolve_mode()
        if mode == "off":
            # 🔑 코드 진입 0 — 롤백이 「끄는 시늉」이 아니라 «실제로» 이전 경로다.
            return self._rule_verdict(df, params)

        hit = corp_action.detect(df.attrs.get("stock_code"), df)
        verdict = self._rule_verdict(df, params)
        if hit is None or verdict is None:
            # ⚠️ 룰에서 이미 떨어진 종목은 계기에 안 찍는다. `flagged` 는 「배제가 후보를
            #    실제로 몇 개 뺐나」여야 EOD 집합 차분이 성립한다(어차피 후보가 아닌
            #    종목까지 세면 사전등록 §6 P4 의 codes 집합과 어긋난다).
            if verdict is not None:
                self._ca_kept += 1
            return verdict

        code = str(df.attrs.get("stock_code") or "?")
        self._ca_flagged.append(code)
        tail = ("— 후보 제외 (mode=live)" if mode == "live"
                else f"— 후보 제외 «안 함»(mode={mode})")
        logger.warning("[%s] %s: %s %s",
                       self.strategy_name, code, corp_action.describe(hit), tail)
        if mode == "live":
            return None
        self._ca_kept += 1
        return verdict

    def finalize_scan(self, diag: Dict[str, Any]) -> None:
        """스캔당 1줄 — 이 줄의 유무·mode 값이 «발효일 계기»다.

        🔑 `flagged` 와 `kept` 를 한 줄에 둘 다 찍는다. 건수만 찍으면 「배제가 0건」과
           「스캔이 안 돌았다」가 구별되지 않는다(한 규칙의 두 축은 따로 판정한다).
        🔑 `codes=` 를 찍는 이유: EOD 점검이 «건수가 아니라 집합 차분»으로 돌기 때문이다.
        """
        mode, invalid = corp_action.resolve_mode()
        try:
            if invalid is not None:
                logger.warning("%s", corp_action.invalid_mode_message(invalid))
            if mode != "off":
                logger.info(
                    "[rs-corp-action] mode=%s scan_date=%s universe=%s evaluated=%s "
                    "flagged=%s kept=%s codes=%s",
                    mode, diag.get("scan_date"), diag.get("n_universe"),
                    diag.get("n_evaluated"), len(self._ca_flagged), self._ca_kept,
                    ",".join(self._ca_flagged))
        finally:
            self._ca_reset()
