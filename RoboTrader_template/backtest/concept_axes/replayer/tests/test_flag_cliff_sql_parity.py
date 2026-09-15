"""`flags.compute_bar_flags` 의 `flag_cliff` 가 **정본 SQL 과 같은 식**인지 대조.

정본 = `backtest/concept_axes/_defs/flag_cliff.sql`
      (= `FD1` §3-4-b 규약 1-b · sha256 4363258871679b23df9170c919d180e1cde8554ef317c04c1e97717460f2d0ea)

🔴 실 DB 가 필요하다(SELECT 전용). 없으면 skip.
🔑 전 종목 윈도우 스캔은 무거우므로 **종목 표본으로 범위만 좁힌다** — 식은 한 글자도 바꾸지 않는다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from backtest.concept_axes.replayer import flags, loader

DEFS = Path(__file__).resolve().parents[2] / "_defs" / "flag_cliff.sql"
SCOPE_ANCHOR = "WHERE stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')"

# 🔒 설계서 §10-1 · FD1 §3-4-b 가 인용하는 **커밋된 바이트**의 sha256.
#    인용문과 파일이 갈라지면 «어느 정의로 재었는지» 가 증명 불가능해진다 ⇒ 바이트로 묶는다.
FROZEN_SHA256 = "4363258871679b23df9170c919d180e1cde8554ef317c04c1e97717460f2d0ea"

# 리뷰 M-6 — parity 표본은 «액면 접두 120종목» 이 아니라
#   **조건 (1) `ret_1d <= -0.15` 행을 가진 종목 전수**로 고른다(문턱 -0.18 보다 느슨하게).
PRESCAN_RET = -0.15
MIN_SQL_HITS = 100          # 미달이면 하한을 내리지 말고 **실측 양성 수를 보고**한다.


def test_defs_file_is_the_frozen_quoted_source():
    """바이트 단위 동결 — 설계서·FD1 이 인용한 sha256 과 같아야 한다."""
    assert DEFS.is_file()
    txt = DEFS.read_bytes()
    got = hashlib.sha256(txt).hexdigest()
    assert got == FROZEN_SHA256, (
        "flag_cliff.sql 이 동결 바이트와 다르다: {} != {}".format(got, FROZEN_SHA256))
    assert b"-0.18" in txt and b"0.80 *" in txt and b"2.0 *" in txt
    assert b"adj_min_21 = adj_max_21" in txt
    assert b"n_prior = 20" in txt


@pytest.mark.db
def test_pandas_flag_cliff_matches_defs_sql(db_conn):
    sql = DEFS.read_text(encoding="utf-8")
    assert SCOPE_ANCHOR in sql
    # 리뷰 M-6 — «조건 (1) 을 만족하는 행을 가진 종목 전수» 프리스캔.
    #   접두 표본은 「절벽이 없는 구간」 을 골라 양쪽 다 0 이어도 통과할 수 있었다.
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT stock_code FROM (
              SELECT stock_code, close,
                     LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS pc
              FROM daily_prices WHERE {so}
            ) t
            WHERE pc IS NOT NULL AND pc > 0 AND close / pc - 1 <= %s
            ORDER BY stock_code
        """.format(so=loader.STOCK_ONLY), (PRESCAN_RET,))
        codes = [r[0] for r in cur.fetchall()]
    codes += ["196450", "297570", "332290", "083640", "001080"]
    codes = sorted(set(codes))
    in_list = ",".join("'{}'".format(c) for c in codes)

    scoped = sql.replace(
        SCOPE_ANCHOR,
        SCOPE_ANCHOR + " AND stock_code IN ({})".format(in_list))
    scoped = scoped.split(";")[0]        # 주석·동반 인쇄 의무 절 제거
    sql_hits = pd.read_sql(scoped, db_conn)
    sql_set = {(str(c), pd.Timestamp(d))
               for c, d in zip(sql_hits["stock_code"], sql_hits["d"])}

    px = pd.read_sql("""
        SELECT stock_code, date, open, high, low, close,
               (volume * COALESCE(adj_factor,1))::double precision AS volume,
               adj_factor, market_cap, volatility_20d
        FROM daily_prices
        WHERE stock_code IN ({codes})
        ORDER BY stock_code, date
    """.format(codes=in_list), db_conn)
    px = loader.normalize_prices(px)
    fl = flags.compute_bar_flags(px)
    py_set = {(str(c), pd.Timestamp(d))
              for c, d, h in zip(px["stock_code"], px["date"], fl["flag_cliff"]) if h}

    # 🔴 «표본에 절벽이 없어서 0 = 0» 으로 통과하는 걸 막는다.
    #    미달이면 하한을 내리지 말고 실측 양성 수를 그대로 보고한다.
    assert len(sql_set) >= MIN_SQL_HITS, (
        "정본 SQL 양성 {}건 < 하한 {}건 — 표본이 아니라 데이터가 바뀌었을 가능성을 "
        "먼저 확인한다(하한을 내리지 말 것)".format(len(sql_set), MIN_SQL_HITS))
    only_sql = sorted(sql_set - py_set)
    only_py = sorted(py_set - sql_set)
    print("종목 {} · SQL {} · pandas {} · SQL만 {} · pandas만 {}".format(
        len(codes), len(sql_set), len(py_set), len(only_sql), len(only_py)))
    # 🔴 「더 많다」≠「포함한다」 — 양방향 차분 둘 다 0 이어야 한다.
    assert only_sql == [] and only_py == [], (only_sql[:5], only_py[:5])
