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


def test_defs_file_exists_and_is_the_quoted_source():
    assert DEFS.is_file()
    txt = DEFS.read_bytes()
    # 🔑 sha256 은 «커밋된 바이트» 기준(설계서 §10-1) — 여기서는 존재·식만 확인한다.
    assert b"-0.18" in txt and b"0.80 *" in txt and b"2.0 *" in txt
    assert b"adj_min_21 = adj_max_21" in txt
    assert b"n_prior = 20" in txt
    print("flag_cliff.sql sha256(작업트리) =", hashlib.sha256(txt).hexdigest())


@pytest.mark.db
def test_pandas_flag_cliff_matches_defs_sql(db_conn):
    sql = DEFS.read_text(encoding="utf-8")
    assert SCOPE_ANCHOR in sql
    # 표본 종목: 절벽이 실제로 있을 만한 구간을 포함하도록 코드 해시로 고르지 않고
    # 「adj 다치·merge 의심」 종목 + 임의 접두 표본을 함께 쓴다.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT stock_code FROM daily_prices "
            "WHERE {} AND date BETWEEN '2024-01-01' AND '2026-05-31' "
            "GROUP BY stock_code ORDER BY stock_code LIMIT 120".format(loader.STOCK_ONLY))
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

    only_sql = sorted(sql_set - py_set)
    only_py = sorted(py_set - sql_set)
    print("종목 {} · SQL {} · pandas {} · SQL만 {} · pandas만 {}".format(
        len(codes), len(sql_set), len(py_set), len(only_sql), len(only_py)))
    # 🔴 「더 많다」≠「포함한다」 — 양방향 차분 둘 다 0 이어야 한다.
    assert only_sql == [] and only_py == [], (only_sql[:5], only_py[:5])
