"""loader.py 단위 — 설계서 §1-2-b(배제) · §1-3-b(달력 SSOT) · §1-2(유니버스 폴백)."""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.concept_axes.replayer import loader


# ── §1-2-b 1·7 — 우선주 판별은 «종목코드 6번째 자리»가 SSOT ──────────────────

@pytest.mark.parametrize("code,expected", [
    ("005935", True),    # 구형 우선주
    ("00088K", True),    # 신형 전환우선주 (한화3우B)
    ("00104K", True),    # CJ4우(전환)
    ("00499M", True),    # [K-M] 상단
    ("005930", False),   # 삼성전자 보통주
    ("0001A0", False),   # 🔴 신형 코드 보통주 — 배제 금지
    ("0007C0", False),   # 🔴 아크릴
    ("0009K0", False),   # 🔴 에임드바이오 (K 가 5번째 자리)
])
def test_is_preferred_stock_code(code, expected):
    assert loader.is_preferred(code) is expected


def test_is_foreign_code_starts_with_nine():
    assert loader.is_foreign("900140") is True
    assert loader.is_foreign("090430") is False


def test_name_rules_are_marked_unknown_not_excluded():
    """이름 미상은 «배제»가 아니라 `flag_name_unknown` 표시다(§1-2-b 6)."""
    names = {"000001": "한국리츠", "000002": "KODEX 200", "000003": "대박스팩1호"}
    cls = loader.classify_exclusions(["000001", "000002", "000003", "000004"], names)
    assert cls["000001"]["excl_reit"] is True
    assert cls["000002"]["excl_etf"] is True
    assert cls["000003"]["excl_spac"] is True
    assert cls["000004"]["name_unknown"] is True
    assert cls["000004"]["excluded"] is False      # 모른다 ≠ 배제


def test_preferred_excluded_before_ledger():
    cls = loader.classify_exclusions(["005935"], {"005935": "삼성전자우"})
    assert cls["005935"]["excl_pref"] is True
    assert cls["005935"]["excluded"] is True


# ── §1-3-b — 거래일 달력 SSOT = `stock_code='KOSPI'` 행 ─────────────────────

def test_trading_calendar_uses_kospi_rows_only():
    """종목행의 DISTINCT date 를 쓰면 팬텀 세션(일요일 1행)이 섞인다."""
    px = pd.DataFrame({
        "stock_code": ["KOSPI", "KOSPI", "000001", "000001"],
        "date": pd.to_datetime(["2026-01-09", "2026-01-12", "2026-01-09", "2026-01-11"]),
    })
    cal = loader.trading_calendar_from_frame(px)
    assert list(cal) == [pd.Timestamp("2026-01-09"), pd.Timestamp("2026-01-12")]
    assert pd.Timestamp("2026-01-11") not in set(cal)     # 일요일 팬텀


# ── §0.2 — date text 손상값 ────────────────────────────────────────────────

def test_corrupt_date_text_is_coerced_and_dropped():
    raw = pd.DataFrame({
        "stock_code": ["000001"] * 3,
        "date": ["2024-01-02", "0024-0A-02", "2024-01-03"],
        "open": [1.0, 1.0, 1.0], "high": [1.0, 1.0, 1.0],
        "low": [1.0, 1.0, 1.0], "close": [1.0, 1.0, 1.0],
        "volume": [1.0, 1.0, 1.0], "adj_factor": [1.0, 1.0, 1.0],
        "market_cap": [1.0, 1.0, 1.0], "volatility_20d": [0.1, 0.1, 0.1],
    })
    out = loader.normalize_prices(raw)
    assert len(out) == 2
    assert out["date"].dtype.kind == "M"


def test_nonpositive_close_rows_dropped_and_ohl_backfilled():
    raw = pd.DataFrame({
        "stock_code": ["000001"] * 2,
        "date": ["2024-01-02", "2024-01-03"],
        "open": [0.0, 5.0], "high": [0.0, 6.0], "low": [0.0, 4.0],
        "close": [0.0, 5.0],
        "volume": [10.0, 10.0], "adj_factor": [1.0, 1.0],
        "market_cap": [1.0, 1.0], "volatility_20d": [0.1, 0.1],
    })
    out = loader.normalize_prices(raw)
    assert len(out) == 1
    assert out["close"].iloc[0] == 5.0


# ── §1-2 — 유니버스 «정확매칭이 아니라» date <= scan_date 폴백 ───────────────

def test_universe_falls_back_to_previous_complete_quant_day():
    px = pd.DataFrame({
        "stock_code": ["000001", "000002", "000001"],
        "date": pd.to_datetime(["2026-01-09", "2026-01-09", "2026-01-12"]),
        "close": [100.0, 200.0, 100.0],
        "volume": [10.0, 20.0, 10.0],
        "market_cap": [1e11, 2e11, None],     # 01-12 는 운영 부분일(market_cap NULL)
    })
    uni = loader.build_universe(px)
    snap = loader.universe_snapshot(uni, pd.Timestamp("2026-01-12"))
    assert snap["eff_date"] == pd.Timestamp("2026-01-09")
    assert set(snap["rows"]) == {"000001", "000002"}


def test_trading_value_is_computed_not_stored():
    """`close × (volume × COALESCE(adj_factor,1))` — 저장 컬럼을 쓰지 않는다."""
    px = pd.DataFrame({
        "stock_code": ["000001"],
        "date": pd.to_datetime(["2026-01-09"]),
        "close": [100.0], "volume": [7.0],       # volume 은 이미 adj 적용된 값
        "market_cap": [1e11],
    })
    uni = loader.build_universe(px)
    assert uni[pd.Timestamp("2026-01-09")]["000001"][1] == pytest.approx(700.0)
