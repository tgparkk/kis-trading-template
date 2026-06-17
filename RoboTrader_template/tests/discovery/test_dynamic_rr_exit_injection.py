"""Task 4: eff_sl/eff_tp 청산 어댑터 배선 검증.

베이스라인(sl_pct/tp_pct 없음) 동작 보존 + 포지션 오버라이드 우선 적용.
"""
import pandas as pd
from scripts.book_portfolio_multiverse import _SLTPMHAdapter
from scripts.discovery.exit_adapters import MAReversionExitAdapter


def _df():
    close = [10000, 10100, 9000, 9500, 10000]  # idx2 close=9000 → -10% from 10000
    return pd.DataFrame({"datetime": range(5), "open": close, "high": close,
                         "low": close, "close": close, "volume": [1] * 5})


# ---------------------------------------------------------------------------
# _SLTPMHAdapter 테스트
# ---------------------------------------------------------------------------

def test_sltpmh_baseline_unchanged_when_no_override():
    df = _df()
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 100}
    pos = {"entry_idx": 1, "entry_price": 10000, "qty": 1}  # no sl_pct
    assert _SLTPMHAdapter.exit_reason(df, 2, pos, params) == "stop_loss"  # -10% <= -8%


def test_sltpmh_position_override_takes_precedence():
    df = _df()
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 100}
    pos = {"entry_idx": 1, "entry_price": 10000, "qty": 1, "sl_pct": 0.15, "tp_pct": 0.30}
    assert _SLTPMHAdapter.exit_reason(df, 2, pos, params) is None  # -10% not <= -15%, no tp, no mh


# ---------------------------------------------------------------------------
# MAReversionExitAdapter 테스트
# ---------------------------------------------------------------------------

def test_ma_reversion_baseline_unchanged_when_no_override():
    """sl_pct 없으면 params["stop_loss_pct"]=0.08 사용 → -10% 손절 트리거."""
    df = _df()
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 100}
    pos = {"entry_idx": 1, "entry_price": 10000, "qty": 1}  # no sl_pct
    adapter = MAReversionExitAdapter(ma=20, recovery_ratio=0.9)
    # ma=20, i=2 → i+1=3 < 20, MA recovery 미트리거. -10% <= -8% → stop_loss
    assert adapter.exit_reason(df, 2, pos, params) == "stop_loss"


def test_ma_reversion_position_override_takes_precedence():
    """sl_pct=0.15 오버라이드 → -10% 미트리거 → None."""
    df = _df()
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 100}
    pos = {"entry_idx": 1, "entry_price": 10000, "qty": 1, "sl_pct": 0.15, "tp_pct": 0.30}
    adapter = MAReversionExitAdapter(ma=20, recovery_ratio=0.9)
    assert adapter.exit_reason(df, 2, pos, params) is None
