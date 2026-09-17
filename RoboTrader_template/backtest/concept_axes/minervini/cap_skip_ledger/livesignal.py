"""«샀을 신호» 판정 — 라이브 전략 인스턴스를 config 로 로드해 `_check_buy` 를 그대로 부른다(룰 복제 0).

순서는 라이브 `BaseStrategy.on_tick` 매수 루프와 같다(strategies/base.py:661-708):
  ① data 없음/길이 < get_min_data_length() → 스킵
  ② describe_impossible_drop(data) → 스킵
  ③ (캡 체크 — 여기서는 «건너뛴다». 캡은 classify.py 가 따로 분류한다)
  ④ _check_buy(code, data)

🔑 `_check_buy` 첫 줄 `MarketHours.is_market_open("KRX")` 은 지금 시각을 보므로 장 밖 실행에선 항상 False 다
   → 호출 동안만 True 로 바꿔 끼운다(프로세스 안 mock · 파일 무수정).
🔑 상태 무변경 확인 — 호출 전후 `positions`·`daily_trades`·캡 로그 억제 집합을 비교하고, 달라지면 예외.
🔑 빈티지 탐지 — 라이브 스크리너 어댑터 `match()`(tt off · ratio_max=∞)로 «지금 DB» 의 score(=최근 30봉 평균 거래량)를
   얻어 `screener_snapshots.score`(D 09:00 라이브 스캔 값)와 비교한다. 다르면 D-1 이하 거래량이 그 뒤 재기록된 것.
🔑 스냅샷 동등 신호 — 스냅샷 종목은 D 09:00 에 라이브 스크리너가 **같은 룰·같은 파라미터**(recent 10·base 30·0.70)로
   dryup 을 통과시킨 종목이고, 라이브 `_check_buy` 는 그 뒤 2분 안에 같은 표를 읽는다. 따라서 재현이 `dryup_not_met`
   인데 빈티지가 바뀌었으면 «라이브 시점 신호 = Y» 로 본다(`signal_basis=snapshot_equiv`). 이때 밴드는 라이브
   `BaseStrategy._entry_band` 를 그대로 부른다.
🔑 비율 표시 — 룰이 미충족이면 사유 문자열이 없으므로, 라이브 룰 클래스 `rule_volume_dryup` 에
   `ratio_max` 만 바꿔(∞) 한 번 더 불러 `recent/base=` 문자열을 읽는다(공식 재구현 없음).
   경계 근접(near_threshold)은 ratio_max 0.68/0.72 두 번 호출 결과가 다르면 참.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from unittest import mock

import pandas as pd

from . import bootstrap  # noqa: F401

import strategies.minervini_volume_dryup.strategy as _strat_mod   # noqa: E402
from strategies.books.minervini_vcp.rules import rule_volume_dryup  # noqa: E402
from strategies.config import StrategyLoader                      # noqa: E402
from strategies.minervini_volume_dryup.screener import MinerviniVolumeDryupScreenerAdapter  # noqa: E402
from utils.data_sanity import describe_impossible_drop            # noqa: E402

FOLDER = "minervini_volume_dryup"
_RATIO_RE = re.compile(r"recent/base=([0-9.]+)")


@dataclass
class SignalEval:
    signal: str                    # Y | N
    reason: str                    # 사유 코드
    ratio_2dp: str = ""            # 룰 문자열의 소수 2자리(라이브 로그와 같은 표기)
    near_threshold: bool = False
    n_bars: int = 0
    last_bar: str = ""
    ref_close: Optional[float] = None
    band_min: Optional[float] = None
    band_max: Optional[float] = None
    score_now: Optional[float] = None       # 라이브 스크리너 match() score — 지금 DB 빈티지
    detail: Dict[str, Any] = field(default_factory=dict)


def load_strategy():
    """라이브와 같은 로더(StrategyLoader)로 config.yaml 을 읽어 인스턴스를 만든다. 브로커·API 없음."""
    s = StrategyLoader.load_strategy(FOLDER)
    if not s.on_init(None, None, None):
        raise RuntimeError("on_init 실패")
    return s


def _state(s) -> tuple:
    return (copy.deepcopy(getattr(s, "positions", None)), getattr(s, "daily_trades", None),
            frozenset(getattr(s, "_cap_skip_logged", set()) or set()),
            getattr(s, "_cap_skip_log_date", None), copy.deepcopy(s.config))


def _probe_ratio(data: pd.DataFrame, ratio_max: float) -> Optional[str]:
    res = rule_volume_dryup(ratio_max=ratio_max).evaluate(data, {})
    if not getattr(res, "triggered", False):
        return None
    m = _RATIO_RE.search(" ".join(res.reasons or []))
    return m.group(1) if m else None


def _triggered(data: pd.DataFrame, ratio_max: float) -> bool:
    return bool(getattr(rule_volume_dryup(ratio_max=ratio_max).evaluate(data, {}), "triggered", False))


def screener_score_now(data: pd.DataFrame) -> Optional[float]:
    """라이브 스크리너 `match()` 로 score 만 읽는다(dryup 문턱 ∞ · TT off → 판정 없이 score 반환)."""
    ad = MinerviniVolumeDryupScreenerAdapter()
    params = {**ad.default_params(), "tt_filter_mode": "off", "ratio_max": float("inf")}
    res = ad.match(data, params)
    return float(res[0]) if res else None


def snapshot_equiv_band(strategy, data: pd.DataFrame):
    """_check_buy 와 같은 기준가(마지막 확정봉 종가) + 라이브 `_entry_band` 호출."""
    ref = float(data["close"].astype(float).iloc[-1])
    lo, hi = strategy._entry_band(ref, down_pct=strategy._entry_band_down_pct, up_pct=strategy._entry_band_up_pct)
    return ref, lo, hi


def evaluate(strategy, code: str, data: Optional[pd.DataFrame]) -> SignalEval:
    if data is None or data.empty:
        return SignalEval("N", "no_daily_data")
    n = len(data)
    last = str(pd.to_datetime(data["date"].iloc[-1]).date())
    min_len = strategy.get_min_data_length()
    if n < min_len:
        return SignalEval("N", f"insufficient_data({n}<{min_len})", n_bars=n, last_bar=last)
    bad = describe_impossible_drop(data)
    if bad:
        return SignalEval("N", f"impossible_bar({bad})", n_bars=n, last_bar=last)

    ratio = _probe_ratio(data, float("inf")) or ""
    near = _triggered(data, 0.68) != _triggered(data, 0.72)
    score_now = screener_score_now(data)

    before = _state(strategy)
    with mock.patch.object(_strat_mod.MarketHours, "is_market_open", return_value=True):
        sig = strategy._check_buy(code, data)
    if _state(strategy) != before:
        raise RuntimeError(f"_check_buy 가 전략 상태를 바꿨다 — {code}")

    if sig is None:
        return SignalEval("N", "dryup_not_met", ratio, near, n, last, score_now=score_now)
    meta = dict(getattr(sig, "metadata", {}) or {})
    return SignalEval(
        "Y", "; ".join(sig.reasons or []) or "buy", ratio, near, n, last,
        ref_close=float(meta.get("close")) if meta.get("close") is not None else None,
        band_min=getattr(sig, "entry_min_price", None), band_max=getattr(sig, "entry_max_price", None),
        score_now=score_now, detail={"signal_type": sig.signal_type.name, "confidence": sig.confidence},
    )
