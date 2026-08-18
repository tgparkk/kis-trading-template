"""Minervini 거래량 건조 전략 EOD 스크리너 어댑터.

2026-08-18 — Trend Template(TT) 배선. 근거: `backtest/concept_axes/minervini/`
(사전등록 `PREREG.md` · 결과 `RESULTS.md`, 판정 `b6d3d89`).

    | Arm | 진입 룰                          | 거래당 평균 | 무작위 20회 최대(+1.03%) |
    |-----|----------------------------------|------------|--------------------------|
    | D   | dryup 만 (2026-08-18까지의 라이브) | +0.00%     | ❌ 못 넘음 (p=1.0000)     |
    | DT  | dryup ∧ TT                        | +1.54%     | ✅ 넘음   (p=0.0476)      |
    | T   | TT 만                             | +2.38%     | ✅ 넘음   (p=0.0476)      |

이 파일은 그중 **DT** 만 구현한다(사장님 승인 2026-08-18, 「1단계 — 추세조건 추가」).
`T`(dryup 제거)는 매매 빈도가 크게 바뀌므로 **빈도 실측 후 별도 결정**한다.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.minervini_vcp.rules import (
    compute_rs_percentile_12w,
    rule_trend_template,
    rule_volume_dryup,
)
from utils.logger import setup_logger

logger = setup_logger(__name__)

# ── TT 게이트 모드 ───────────────────────────────────────────────────────────
#   "off"    — TT 를 평가하지 않는다 (2026-08-18 이전 동작).
#   "shadow" — TT 를 평가해 «기록만» 한다. 후보 선정은 dryup 단독과 100% 동일.
#   "on"     — TT 를 통과한 종목만 후보가 된다 (= 백테스트 `DT` arm).
#
# 🔑 기본을 "shadow" 로 두는 이유: TT 는 220봉과 RS 백분위가 «둘 다» 있어야 하고,
#    하나라도 없으면 룰이 조용히 False 를 반환한다(rules.py:52, :66 — 로그 없음).
#    즉 배선이 틀리면 「후보 0건」이 되는데 아무 경보도 안 뜬다. shadow 로 며칠
#    돌려 배관이 실제로 값을 공급하는지 확인한 «뒤에» "on" 으로 올린다.
#    → 승격 조건은 이 폴더의 README.md 「TT 승격 체크리스트」 참조.
TT_FILTER_MODE = "shadow"

# 백테스트가 룰에 넘긴 창 길이(`backtest/concept_axes/minervini/run.py:81 LOOKBACK`).
# 🔴 라이브의 기존 `lookback_days=90` 으로는 TT 가 **항상 False** 다 — `rule_trend_template`
#    이 220봉을 요구하고 52주 고저에 `close.iloc[-252:]` 를 쓰기 때문. 260 은 그 요구를
#    채우면서 `rule_volume_dryup`(마지막 40봉)과 `score`(마지막 30봉)의 결과를 **바꾸지
#    않는다** — 두 계산 모두 창 길이에 불변이고, 260 ≥ 252 라 52주 창도 정확히 같다.
_TT_LOOKBACK = 260

# 창을 늘려도 데이터 위생 가드가 훑는 범위는 «기존 그대로» 90봉으로 고정한다.
# 안 그러면 진입 룰을 안 건드렸는데 후보 집합이 바뀐다(「한 번에 한 축만」).
_LEGACY_SANITY_WINDOW = 90


class MinerviniVolumeDryupScreenerAdapter(RuleScreenerBase):
    strategy_name = "minervini_volume_dryup"
    lookback_days = _TT_LOOKBACK
    sanity_window = _LEGACY_SANITY_WINDOW
    wants_context = True

    def __init__(self, config=None, broker=None, db_manager=None) -> None:
        super().__init__(config=config, broker=broker, db_manager=db_manager)
        # 🔑 `match()` 는 `scan()` 을 거치지 않고 «직접» 호출될 수 있다(단위 테스트가
        #    그렇게 부른다). 카운터를 scan() 에서만 만들면 그 경로가 AttributeError 로
        #    죽는다 — 기존 테스트가 이 결함을 잡았다. 생성 시점에 초기화한다.
        self._reset_counters()

    def _reset_counters(self) -> None:
        self._tally: Dict[str, Any] = {}
        self._rs_diag: Dict[str, Any] = {"n_input": 0, "n_rs": 0, "error": None}

    def default_params(self) -> Dict[str, Any]:
        return {
            "recent_window": 10,
            "base_window": 30,
            "ratio_max": 0.70,
            "min_market_cap": 300_000_000_000,
            "min_trading_value": 3_000_000_000,
            "max_candidates": 10,
            "tt_filter_mode": TT_FILTER_MODE,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        out = []
        for u in universe:
            # 시총 결측(0/None)이면 컨셉 검증 불가 → fail-closed 제외.
            if not self._passes_market_cap(u.get("market_cap"), min_cap=p["min_market_cap"]):
                continue
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

    # ── 횡단면 컨텍스트: RS 백분위 ──────────────────────────────────────────
    def build_context(
        self, frames: Dict[str, pd.DataFrame], scan_date: date
    ) -> Dict[str, Dict[str, Any]]:
        """`{code: {"rs_value": 0~99}}`.

        🔴 사전등록 §2-1 이 못박은 정의를 그대로 쓴다 — **유니버스 = 그날
        `base_filter` 통과 집합**이고 전체 시장이 아니다. `frames` 의 키가 바로
        그 집합이라 정의가 자동으로 맞는다. (`run.py:122` 의 경고와 같은 값)
        """
        self._rs_diag = {"n_input": len(frames), "n_rs": 0, "error": None}
        if len(frames) < 2:
            # compute_rs_percentile_12w 가 ValueError 를 던지는 조건.
            self._rs_diag["error"] = f"유니버스 {len(frames)}종목 (<2) — RS 산출 불가"
            return {}
        try:
            wide = pd.DataFrame({
                code: df.set_index("date")["close"].astype(float)
                for code, df in frames.items()
            }).sort_index()
            row = compute_rs_percentile_12w(wide).iloc[-1]
        except Exception as exc:  # noqa: BLE001 — 산출 실패는 TT fail-closed 로 흡수
            self._rs_diag["error"] = f"{type(exc).__name__}: {exc}"
            logger.error("[%s] RS 백분위 산출 실패 — TT 는 이번 스캔에서 전부 False 가 된다: %s",
                         self.strategy_name, exc)
            return {}
        ctxs: Dict[str, Dict[str, Any]] = {}
        for code, val in row.items():
            if pd.isna(val):
                continue
            ctxs[code] = {"rs_value": float(val)}
        self._rs_diag["n_rs"] = len(ctxs)
        return ctxs

    def match(
        self,
        df: pd.DataFrame,
        params: Dict[str, Any],
        ctx: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[float, str]]:
        mode = str(params.get("tt_filter_mode", TT_FILTER_MODE)).lower()
        # 🔑 진단이 «실제로 돈 모드»를 찍게 한다. `default_params()` 를 다시 읽으면
        #    호출자가 넘긴 오버라이드를 못 보고 «안 돈 모드»를 인쇄한다(자체검토에서 잡음).
        self._tally["mode"] = mode
        self._tally["n_eval"] = self._tally.get("n_eval", 0) + 1
        if len(df) >= 220:
            self._tally["n_bars_ok"] = self._tally.get("n_bars_ok", 0) + 1

        rule = rule_volume_dryup(
            recent_window=int(params.get("recent_window", 10)),
            base_window=int(params.get("base_window", 30)),
            ratio_max=float(params.get("ratio_max", 0.70)),
        )
        res = rule.evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        self._tally["n_dry"] = self._tally.get("n_dry", 0) + 1

        reason = "; ".join(getattr(res, "reasons", []) or ["volume_dryup"])
        base_window = int(params.get("base_window", 30))
        score = float(df["volume"].iloc[-base_window:].mean())  # 유동성 큰 쪽 우선(동률 깨기)

        if mode == "off":
            return (score, reason)

        # 🔴 파라미터 기본값 그대로 (사전등록 §2-1: 「한 글자도 고치지 않는다」).
        tt_res = rule_trend_template().evaluate(df, ctx or {})
        ok_tt = bool(getattr(tt_res, "triggered", False))
        if ok_tt:
            self._tally["n_tt"] = self._tally.get("n_tt", 0) + 1

        # 판정을 reason 에 «찍어» screener_snapshots 만으로 빈도 실측이 되게 한다.
        reason = f"{reason}; tt={int(ok_tt)}"

        if mode == "on" and not ok_tt:
            return None
        return (score, reason)

    # ── 진단: 「조용한 0건」을 소리나게 만든다 ───────────────────────────────
    def finalize_scan(self, diag: Dict[str, Any]) -> None:
        t = getattr(self, "_tally", {})
        rs = getattr(self, "_rs_diag", {})
        # 실제로 돈 모드. 평가가 한 건도 없었으면(유니버스 0) 알 수 없으므로 "?" 로 둔다 —
        # 「돌지 않았다」를 「기본 모드로 돌았다」로 인쇄하지 않기 위해서다.
        mode = str(t.get("mode", "?"))
        n_eval = t.get("n_eval", 0)
        n_bars_ok = t.get("n_bars_ok", 0)
        n_rs = rs.get("n_rs", 0)
        n_dry = t.get("n_dry", 0)
        n_tt = t.get("n_tt", 0)

        logger.info(
            "[%s] TT게이트 mode=%s · 유니버스 %d → 평가 %d "
            "(일봉부족제외 %d · 불가능봉 %d) · 220봉충족 %d · rs_value 확보 %d/%d · "
            "dryup %d · TT통과 %d · 최종후보 %d",
            self.strategy_name, mode, diag["n_universe"], n_eval,
            diag["n_no_data"], diag["n_impossible"], n_bars_ok,
            n_rs, rs.get("n_input", 0), n_dry, n_tt, diag["n_selected"],
        )

        # 🔑 죽은 가드 방지 — 배관이 끊기면 「후보 0건」이 조용히 나온다. 소리나게 한다.
        if mode != "off":
            if rs.get("error"):
                logger.error("[%s] TT 무효: RS 백분위 산출 실패 — %s",
                             self.strategy_name, rs["error"])
            elif n_bars_ok == 0 and n_eval > 0:
                logger.error(
                    "[%s] TT 무효: 220봉을 채운 종목이 «0개» — lookback_days=%d 가 "
                    "실제로 적재되는지 확인 필요(TT 는 전부 False 가 된다)",
                    self.strategy_name, self.lookback_days)
            elif n_rs == 0 and n_eval > 0:
                logger.error(
                    "[%s] TT 무효: rs_value 를 얻은 종목이 «0개» — TT 는 전부 False 가 된다",
                    self.strategy_name)
            elif n_dry > 0 and n_tt == 0:
                logger.warning(
                    "[%s] dryup %d건이 전부 TT 탈락 — mode=on 이면 후보 0건이 된다",
                    self.strategy_name, n_dry)

    def scan(self, scan_date, params):  # noqa: D102 — 스캔마다 카운터 초기화
        self._reset_counters()
        return super().scan(scan_date, params)
