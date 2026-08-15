"""불가능봉 방어 가드 회귀 테스트 (2026-08-15 감사).

배경: `daily_prices` 에 **조정되지 않은 기업행위**가 남긴 가짜 절벽이 있다
(실측 119건, 그중 111건은 `corp_events` 에 대응 이벤트조차 없음. 표본 −96~−98%).
KRX 일일 가격제한은 ±30% 라 그보다 큰 하락은 정상 시세로 «불가능»하다.

🔴 이게 라이브를 물었다 — `deep_mr_dev20`(폭락 저격)이 가짜 절벽을 진짜 폭락으로 오인해
   46건 중 4건(8.7%)을 그렇게 샀고, 둘은 손절선을 뚫고 −12.4% · −16.2% 로 갭다운했다.

⇒ 룰이 «보는 창» 안에 불가능봉이 있으면 그 종목을 후보에서 제외한다.
   ⚠️ 데이터 위생이지 전략 변경이 아니다 — 성과 주장 없음.
"""
from __future__ import annotations

import pandas as pd
import pytest

from utils.data_sanity import (
    IMPOSSIBLE_DROP_PCT,
    KRX_DAILY_LIMIT_PCT,
    describe_impossible_drop,
    find_impossible_drops,
    has_impossible_drop,
)


def _df(closes, start="2026-01-02"):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"date": idx, "close": closes,
                         "open": closes, "high": closes, "low": closes,
                         "volume": [1000] * len(closes)})


# ── 탐지 ────────────────────────────────────────────────────────────────────
def test_detects_the_measured_artifacts():
    """실측된 인공물 폭(−44.9 / −56.2 / −75.5 / −97.9%)이 전부 잡혀야 한다."""
    for drop in (-0.449, -0.562, -0.755, -0.979):
        df = _df([10000, 10000, 10000 * (1 + drop), 10000 * (1 + drop)])
        assert has_impossible_drop(df), f"{drop:.1%} 하락을 못 잡았다"


def test_does_not_flag_legal_limit_down():
    """🔴 오탐 방지 — KRX 한도 내 급락(−29%·−30%)은 «정상»이라 건드리면 안 된다.

    `deep_mr` 은 진짜 폭락을 사는 전략이다. 한도 내 하락을 막으면 전략을 죽인다.
    """
    for drop in (-0.29, -0.30, -0.34):
        df = _df([10000, 10000, 10000 * (1 + drop), 10000 * (1 + drop)])
        assert not has_impossible_drop(df), f"{drop:.1%} 는 정상인데 잡혔다"


def test_threshold_sits_below_krx_limit():
    """문턱이 한도보다 «아래»여야 정상 하한가를 안 건드린다."""
    assert IMPOSSIBLE_DROP_PCT < -KRX_DAILY_LIMIT_PCT, (
        f"문턱 {IMPOSSIBLE_DROP_PCT} 가 KRX 한도 −{KRX_DAILY_LIMIT_PCT} 보다 위다 — 정상 하한가를 잡는다")


def test_upward_moves_are_not_flagged():
    """상승은 보지 않는다(신규상장일 ±60~400% 등 정상 사례가 섞임)."""
    df = _df([1000, 1000, 5000, 5000])          # +400%
    assert not has_impossible_drop(df)


# ── 창 한정 ─────────────────────────────────────────────────────────────────
def test_only_the_given_window_matters():
    """호출자가 넘긴 창«만» 본다 — 창 밖 과거 절벽은 룰을 오염시키지 않는다."""
    full = _df([10000, 200, 200, 205, 210, 208, 212])   # 0→1 에서 −98%
    assert has_impossible_drop(full)
    assert not has_impossible_drop(full.iloc[2:].reset_index(drop=True))


# ── 견고성 ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [None, pd.DataFrame(), pd.DataFrame({"close": [100]})])
def test_degenerate_input_is_safe(bad):
    """None·빈 프레임·1행이면 조용히 「정상」으로 본다(가드가 예외를 던지면 안 된다)."""
    assert not has_impossible_drop(bad)
    assert find_impossible_drops(bad) == []


def test_zero_and_negative_close_do_not_create_false_hits():
    """0·음수 종가(손상 행)가 −100% 로 계산돼 오탐을 만들면 안 된다."""
    df = _df([10000, 0, 10000, 10050])
    assert not has_impossible_drop(df), "0 종가가 가짜 −100% 를 만들었다"


def test_missing_close_column_is_safe():
    assert not has_impossible_drop(pd.DataFrame({"open": [1, 2, 3]}))


# ── 로그 문구 ───────────────────────────────────────────────────────────────
def test_describe_reports_worst_drop_and_is_empty_when_clean():
    df = _df([10000, 10000, 500, 500, 100])
    msg = describe_impossible_drop(df)
    assert "불가능봉" in msg and "-9" in msg, msg
    assert describe_impossible_drop(_df([100, 101, 102])) == ""


# ── 통합: 실제로 «그 4건»을 막는가 (실 DB) ─────────────────────────────────
_DSN = dict(host="127.0.0.1", port=5433, user="robotrader",
            password="1234", dbname="kis_template")

# 2026-06~08 라이브에서 deep_mr_dev20 이 «가짜 절벽 직후» 실제로 매수한 종목/시점.
#   (종목, 절벽일, 매수일)  — 절벽폭 −44.9 / −56.2 / −75.5%
_LIVE_CASES = [("476830", "2026-06-29", "2026-06-30"),
               ("356860", "2026-07-16", "2026-07-20"),
               ("025560", "2026-07-27", "2026-07-29")]


def _window(code: str, end_date: str, bars: int = 35):
    """deep_mr 이 보는 창(35봉, 매수 전일까지)을 실 DB 에서 가져온다."""
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        conn = psycopg2.connect(**_DSN)
    except psycopg2.OperationalError as e:                      # pragma: no cover
        pytest.skip(f"kis_template 접속 불가: {e}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT date, close FROM daily_prices WHERE stock_code=%s AND date < %s "
                "ORDER BY date DESC LIMIT %s", (code, end_date, bars))
            rows = cur.fetchall()
    finally:
        conn.close()
    if len(rows) < 5:                                           # pragma: no cover
        pytest.skip(f"{code} 일봉 부족")
    df = pd.DataFrame(rows, columns=["date", "close"])[::-1].reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df


@pytest.mark.parametrize("code,cliff,buy", _LIVE_CASES)
def test_guard_would_have_blocked_the_real_deep_mr_buys(code, cliff, buy):
    """🔴 이 가드가 없어서 실제로 산 4건 — 이제 창에서 불가능봉이 «검출»되어야 한다."""
    df = _window(code, buy)
    hits = find_impossible_drops(df)
    assert hits, (
        f"{code} (절벽 {cliff} → 매수 {buy}) 창에서 불가능봉을 못 잡았다 — "
        f"가드가 그 매수를 막지 못한다")
    assert min(r for _, r in hits) < -0.40, f"검출된 하락폭이 예상보다 얕다: {hits}"


def test_guard_does_not_block_a_normal_stock():
    """🔴 대조군 — 정상 대형주는 걸리면 안 된다(오탐이면 가드가 못 쓰게 된다)."""
    df = _window("005930", "2026-08-14", bars=120)   # 삼성전자
    assert not has_impossible_drop(df), "정상 종목이 걸렸다 — 오탐"
