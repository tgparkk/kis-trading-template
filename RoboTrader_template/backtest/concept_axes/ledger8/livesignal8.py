"""«샀을 신호» 판정 — 8전략 라이브 인스턴스의 `_check_buy` 를 그대로 부른다(룰 복제 0).

라이브 `BaseStrategy.on_tick` 매수 루프(strategies/base.py:660-708) 순서:
  ① data 없음 / len < get_min_data_length() → 스킵        (:662-687)
  ② describe_impossible_drop(data) → 스킵                   (:693-707)
  ③ generate_signal 의 보유·일일체결·K 게이트 — 여기서는 «건너뛴다»(보유와 무관하게 룰만 본다 · 스펙 3-1).
     그 게이트는 stages.py 가 로그·체결 원장으로 따로 분류한다.
  ④ _check_buy(code, data)
하루 1회면 충분하다 — 창은 오늘 봉을 뺀 확정봉(core/trading_context.py:143-199)이고 8전략 `_check_buy` 는
`data` 의 마지막 확정봉(D-1)만 쓴다(스펙 3-6: 여러 틱을 하루 1회로 접는 것은 근사가 아니라 정확).

패치(프로세스 안 mock · 파일 무수정)
  - `config.market_hours.MarketHours.is_market_open` → True. 8전략 모두 같은 클래스를 import 한다.
  - rs_leader: `config.constants.RS_LEADER_CORP_ACTION_MODE` 를 그날 모드로(corp_action_guard.py:56-57 가 호출 시점에 읽는다).
  - envelope: 모듈 `now_kst` 를 D 09:02 로(`_fetch_entry_history` 캐시 키·end_date · strategy.py:231-249),
    호출 전후 `_entry_df_cache` 를 비운다.
상태 무변경 — registry.state_attrs(folder) 를 호출 전후 deepcopy 비교, 다르면 RuntimeError.
"""
from __future__ import annotations

import copy
import importlib
import re
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterator, Optional, Tuple
from unittest import mock

import pandas as pd

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저
from backtest.concept_axes.minervini.cap_skip_ledger import sources as _S

import config.constants as _CC                              # noqa: E402
from config.market_hours import MarketHours                 # noqa: E402
from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high   # noqa: E402
from strategies.books.minervini_vcp.rules import rule_volume_dryup               # noqa: E402
from strategies.config import StrategyLoader                # noqa: E402
from utils.data_sanity import describe_impossible_drop      # noqa: E402

from . import registry as R

ENVELOPE = "book_envelope_200d"
DAY = "daytrading_3methods_breakout"
MIN = "minervini_volume_dryup"
# 거래량 재기록(증가)이 재현 신호를 어느 쪽으로 기울이나 — day: 비율 ≥ 문턱이 Y ⇒ Y 쪽 · min: 비율 ≤ 문턱이 Y ⇒ N 쪽
VOLUME_RULE_BIAS = {DAY: "Y", MIN: "N"}
_VOL_RE = re.compile(r"vol=(\d+)/(\d+)")
_RATIO_RE = re.compile(r"recent/base=([0-9.]+)")


@dataclass
class SignalEval8:
    folder: str
    code: str
    d: date
    signal: str                          # Y | N
    reason: str                          # Y: 룰 사유 · N: no_daily_data | insufficient_data(n<m) | impossible_bar(…) | rule_not_met
    reasons_str: str = ""                # ', '.join(signal.reasons) — 라이브 `[on_tick] 매수신호 … 이유:` 와 같은 표기(base.py:722)
    n_bars: int = 0
    last_bar: str = ""
    ref: Optional[float] = None          # metadata[registry.ref_key]
    band_min: Optional[float] = None
    band_max: Optional[float] = None
    confidence: Optional[float] = None
    detail: Dict[str, Any] = field(default_factory=dict)


def load8(folder: str):
    """라이브와 같은 로더(StrategyLoader)로 config.yaml 을 읽어 인스턴스를 만든다. 브로커·API 없음."""
    s = StrategyLoader.load_strategy(folder)
    if not s.on_init(None, None, None):
        raise RuntimeError(f"{folder} on_init 실패")
    return s


def _module(strategy):
    return importlib.import_module(type(strategy).__module__)


def state_snapshot(strategy, folder: str) -> tuple:
    return tuple(copy.deepcopy(getattr(strategy, a, None)) for a in R.state_attrs(folder))


@contextmanager
def live_buy_patches(strategy, folder: str, d: date) -> Iterator[None]:
    mode = R.corp_action_mode_for(folder, d)
    with ExitStack() as st:
        st.enter_context(mock.patch.object(MarketHours, "is_market_open", return_value=True))
        if mode is not None:
            st.enter_context(mock.patch.object(_CC, "RS_LEADER_CORP_ACTION_MODE", mode))
            st.enter_context(mock.patch.object(_CC, "RS_LEADER_CORP_ACTION_MODE_INVALID", None))
        if folder == ENVELOPE:
            st.enter_context(mock.patch.object(_module(strategy), "now_kst", return_value=_S._as_of(d)))
            strategy._entry_df_cache.clear()
        try:
            yield
        finally:
            if folder == ENVELOPE:
                strategy._entry_df_cache.clear()


def _guard(folder: str, code: str, d: date, data: Optional[pd.DataFrame], min_len: int) -> Optional[SignalEval8]:
    if data is None or data.empty:
        return SignalEval8(folder, code, d, "N", "no_daily_data")
    n = len(data)
    last = str(pd.to_datetime(data["date"].iloc[-1]).date())
    if n < min_len:
        return SignalEval8(folder, code, d, "N", f"insufficient_data({n}<{min_len})", n_bars=n, last_bar=last)
    bad = describe_impossible_drop(data)
    if bad:
        return SignalEval8(folder, code, d, "N", f"impossible_bar({bad})", n_bars=n, last_bar=last)
    return None


def _call_check_buy(strategy, folder: str, code: str, d: date, data: pd.DataFrame):
    before = state_snapshot(strategy, folder)
    quant: Optional[pd.DataFrame] = None
    with live_buy_patches(strategy, folder, d):
        sig = strategy._check_buy(code, data)
        if folder == ENVELOPE:
            quant = strategy._entry_df_cache.get((code, d))
    if state_snapshot(strategy, folder) != before:
        raise RuntimeError(f"_check_buy 가 전략 상태를 바꿨다 — {folder} {code} {d}")
    return sig, quant


def evaluate8(strategy, folder: str, code: str, d: date, data: Optional[pd.DataFrame]) -> SignalEval8:
    early = _guard(folder, code, d, data, strategy.get_min_data_length())
    if early is not None:
        return early
    n, last = len(data), str(pd.to_datetime(data["date"].iloc[-1]).date())
    sig, quant = _call_check_buy(strategy, folder, code, d, data)
    detail: Dict[str, Any] = {}
    if quant is not None and not quant.empty:
        detail.update(quant_n=len(quant), quant_last=str(pd.to_datetime(quant["date"].iloc[-1]).date()))
    if sig is None:
        return SignalEval8(folder, code, d, "N", "rule_not_met", n_bars=n, last_bar=last, detail=detail)
    meta = dict(getattr(sig, "metadata", {}) or {})
    ref = meta.get(R.spec(folder).ref_key)
    reasons = list(sig.reasons or [])
    detail.update(signal_type=sig.signal_type.name, buy_stop_price=meta.get("buy_stop_price"))
    return SignalEval8(
        folder, code, d, "Y", "; ".join(reasons) or "buy", ", ".join(reasons) if reasons else "-", n, last,
        ref=float(ref) if ref is not None else None,
        band_min=getattr(sig, "entry_min_price", None), band_max=getattr(sig, "entry_max_price", None),
        confidence=float(sig.confidence), detail=detail)


def forced_band(strategy, folder: str, code: str, d: date, data: Optional[pd.DataFrame]
                ) -> Optional[Tuple[Optional[float], Optional[float], Optional[float]]]:
    """룰을 참으로 강제하고 라이브 `_check_buy` 를 불러 (기준가, 밴드) 만 얻는다 — 밴드·매수스톱 공식 복제 0.

    쓰는 곳: 라이브 로그는 Y 인데 재현이 N(빈티지)인 행, A_sim 의 실제 매수 중 재현 N 인 행.
    `evaluate_entry` 반환 길이 = registry.entry_eval_arity(테스트가 AST 로 대조). rs_leader live 배제면 None.
    """
    if data is None or data.empty:
        return None
    if R.spec(folder).entry_eval_arity == 3:
        fake = staticmethod(lambda *a, **k: (True, ["forced_band"], {}))
    else:
        fake = staticmethod(lambda *a, **k: (True, ["forced_band"]))
    with mock.patch.object(type(strategy), "evaluate_entry", fake):
        sig, _ = _call_check_buy(strategy, folder, code, d, data)
    if sig is None:
        return None
    ref = (sig.metadata or {}).get(R.spec(folder).ref_key)
    return (float(ref) if ref is not None else None,
            getattr(sig, "entry_min_price", None), getattr(sig, "entry_max_price", None))


def volume_margin(folder: str, data: Optional[pd.DataFrame], ev: SignalEval8) -> Optional[Tuple[float, float]]:
    """거래량 룰 전략의 (비율, 문턱) — 라이브 룰 클래스의 기본 문턱을 쓴다(공식 복제 0). 해당 없으면 None.

    day: `_check_buy` 사유 `vol=a/b`(룰이 Y 일 때만 사유가 있다) · 문턱 = rule_breakout_prev_high.vol_mult
         (strategies/books/daytrading_3methods/rules.py:280 · 비교 :293)
    min: rule_volume_dryup(ratio_max=∞) 사유 `recent/base=x` · 문턱 = rule_volume_dryup.ratio_max
         (strategies/books/minervini_vcp/rules.py:319 · 비교 :330)
    """
    if folder == DAY:
        m = _VOL_RE.search(ev.reasons_str or "")
        if not m or float(m.group(2)) <= 0:
            return None
        return float(m.group(1)) / float(m.group(2)), float(rule_breakout_prev_high.vol_mult)
    if folder == MIN:
        if data is None or data.empty:
            return None
        res = rule_volume_dryup(ratio_max=float("inf")).evaluate(data, {})
        m = _RATIO_RE.search(" ".join(getattr(res, "reasons", None) or []))
        return (float(m.group(1)), float(rule_volume_dryup.ratio_max)) if m else None
    return None
