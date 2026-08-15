"""adj_factor × volume 단위 정합 회귀 테스트 (2026-08-15 감사).

**문제**: `daily_prices` 는 close 를 «조정»해 저장하고(규약: `adj_close = raw_close / adj_factor`,
`collectors/adj_factors.py:16`) volume 은 **원본 그대로** 저장한다. 두 컬럼의 단위가 어긋난다.

그 결과 두 가지가 틀어진다:
  1. `close × volume`(거래대금)이 분할 «이전» 구간에서 `adj_factor` 배만큼 **과소**평가된다.
     실측: 카카오 035720 2021-04-08 저장값 1,004억 · 실제 5,020억 (5:1 분할, adj_factor=5)
  2. 거래량 «비율» 비교가 분할 경계에서 깨진다. `daytrading_3methods` 의
     「당일 거래량 ≥ 직전 20봉 평균 × 2」는 분할 직후 20봉 동안 평균이 5배 작게 잡혀
     **가짜 폭증 신호**가 뜬다. `minervini` dry-up 은 반대로 억제된다.

**수정**: 읽기 계층에서 `volume × COALESCE(adj_factor, 1)` 로 단위를 맞춘다.

🔑 ***close 에는 곱하면 «안 된다»*** — 곱하면 분할일 가짜 절벽(−78.5%)이 생긴다
   (`tests/test_adj_factor_no_split_cliff.py`). **방향이 정반대인 두 규칙이 공존한다:**
   가격은 이미 조정됐으니 그대로, 수량은 조정 안 됐으니 곱한다.

RED (수정 전): quant reader 가 2021-04-08 volume=912,514(raw) 를 그대로 반환 →
               close×volume = 1,004억
GREEN(수정 후): volume=4,562,570 (=912,514×5) → close×volume = 5,020억 = raw 거래대금
"""
from __future__ import annotations

import pandas as pd
import psycopg2
import pytest

SPLIT_STOCK = "035720"          # 카카오 — 2021-04-15 5:1 액면분할
PRE_SPLIT_DATE = "2021-04-08"   # adj_factor = 5 인 구간
POST_SPLIT_DATE = "2021-04-16"  # adj_factor = 1 인 구간

_DSN = dict(host="127.0.0.1", port=5433, user="robotrader",
            password="1234", dbname="kis_template")


def _raw_row(date_str: str) -> tuple[float, float, float]:
    """DB 원본 (close, volume, adj_factor). 읽기 계층을 «거치지 않고» 직접 본다."""
    try:
        conn = psycopg2.connect(**_DSN)
    except psycopg2.OperationalError as e:                      # pragma: no cover
        pytest.skip(f"kis_template 접속 불가: {e}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT close, volume, COALESCE(adj_factor, 1) FROM daily_prices "
                "WHERE stock_code = %s AND date = %s", (SPLIT_STOCK, date_str))
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:                                             # pragma: no cover
        pytest.skip(f"{SPLIT_STOCK} {date_str} 행 없음")
    return float(row[0]), float(row[1]), float(row[2])


def _quant_frame() -> pd.DataFrame:
    from db.quant_daily_reader import QuantDailyReader
    try:
        df = QuantDailyReader().get_daily_prices(SPLIT_STOCK, end_date="2021-04-20", days=20)
    except Exception as e:                                      # pragma: no cover
        pytest.skip(f"QuantDailyReader 사용 불가: {e}")
    if df is None or df.empty:                                  # pragma: no cover
        pytest.skip("일봉 없음")
    df = df.copy()
    df["d"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def test_precondition_split_stock_has_adj_factor():
    """전제 확인 — 이 종목·날짜가 실제로 분할 전후를 감싸고 있어야 테스트가 뜻을 가진다."""
    _, _, pre_f = _raw_row(PRE_SPLIT_DATE)
    _, _, post_f = _raw_row(POST_SPLIT_DATE)
    assert pre_f > 1, f"{PRE_SPLIT_DATE} adj_factor 가 1 이면 이 테스트는 무의미하다 (={pre_f})"
    assert post_f == 1, f"{POST_SPLIT_DATE} adj_factor 는 1 이어야 한다 (={post_f})"


def test_quant_reader_volume_is_split_adjusted():
    """QuantDailyReader(EOD 스크리너·envelope 진입평가 경로) 가 조정 volume 을 준다."""
    raw_close, raw_vol, factor = _raw_row(PRE_SPLIT_DATE)
    df = _quant_frame()
    got = df.loc[df["d"] == PRE_SPLIT_DATE, "volume"]
    if got.empty:                                               # pragma: no cover
        pytest.skip(f"{PRE_SPLIT_DATE} 행이 반환 창에 없음")
    assert float(got.iloc[0]) == pytest.approx(raw_vol * factor, rel=1e-9), (
        f"volume 이 adj_factor({factor}) 로 조정되지 않았다: "
        f"{float(got.iloc[0]):,.0f} != {raw_vol * factor:,.0f}")


def test_quant_reader_turnover_equals_raw_turnover():
    """close×volume 이 «원시» 거래대금과 같아야 한다(조정 close × 조정 volume = raw × raw)."""
    raw_close, raw_vol, factor = _raw_row(PRE_SPLIT_DATE)
    df = _quant_frame()
    row = df.loc[df["d"] == PRE_SPLIT_DATE]
    if row.empty:                                               # pragma: no cover
        pytest.skip(f"{PRE_SPLIT_DATE} 행이 반환 창에 없음")
    got_turnover = float(row["close"].iloc[0]) * float(row["volume"].iloc[0])
    raw_turnover = (raw_close * factor) * raw_vol
    assert got_turnover == pytest.approx(raw_turnover, rel=1e-9), (
        f"거래대금이 raw 와 다르다: {got_turnover:,.0f} != {raw_turnover:,.0f}")


def test_quant_reader_close_is_NOT_multiplied():
    """🔴 반대 방향 회귀 — close 에는 adj_factor 를 곱하면 안 된다(가짜 분할 절벽)."""
    raw_close, _, factor = _raw_row(PRE_SPLIT_DATE)
    df = _quant_frame()
    row = df.loc[df["d"] == PRE_SPLIT_DATE]
    if row.empty:                                               # pragma: no cover
        pytest.skip(f"{PRE_SPLIT_DATE} 행이 반환 창에 없음")
    assert float(row["close"].iloc[0]) == pytest.approx(raw_close, rel=1e-9), (
        "close 가 조정 전 값으로 바뀌었다 — adj_factor 를 close 에 곱하면 "
        "분할일 가짜 절벽이 생긴다")


def test_no_phantom_volume_collapse_at_split():
    """분할 경계에서 거래량이 «기계적으로» 급락해 보이지 않아야 한다.

    조정 전에는 분할 직전 봉의 volume 이 직후 대비 1/adj_factor 로 눌려 있어,
    직전 20봉 평균을 쓰는 비율 룰(daytrading)이 가짜 폭증을 만든다.
    조정 후에는 그 «기계적» 성분이 사라진다 — 실제 분할 후 거래 증가는 남는다.
    """
    df = _quant_frame().sort_values("d")
    df = df[df["volume"] > 0]
    pre = df[df["d"] <= PRE_SPLIT_DATE]["volume"]
    if len(pre) < 2:                                            # pragma: no cover
        pytest.skip("분할 전 봉 부족")
    _, _, factor = _raw_row(PRE_SPLIT_DATE)
    # 조정 전이면 분할 전 구간 전체가 raw 라 factor 배 눌려 있다.
    # 조정 후에는 분할 전 평균이 raw 평균의 factor 배여야 한다.
    conn = psycopg2.connect(**_DSN)
    try:
        raw = pd.read_sql(
            "SELECT date, volume FROM daily_prices WHERE stock_code=%s "
            "AND date <= %s AND date >= '2021-03-20' ORDER BY date",
            conn, params=(SPLIT_STOCK, PRE_SPLIT_DATE))
    finally:
        conn.close()
    raw_mean = pd.to_numeric(raw["volume"], errors="coerce").tail(len(pre)).mean()
    assert pre.mean() == pytest.approx(raw_mean * factor, rel=0.02), (
        f"분할 전 평균 거래량이 조정되지 않았다: {pre.mean():,.0f} vs "
        f"{raw_mean * factor:,.0f}")
