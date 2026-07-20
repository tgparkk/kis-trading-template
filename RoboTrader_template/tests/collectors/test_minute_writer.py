# tests/collectors/test_minute_writer.py
import logging

import pandas as pd

from collectors import minute_writer
from collectors.minute_writer import df_to_minute_rows


def test_df_to_minute_rows_builds_idx_and_fields():
    # datetime 은 봉의 자연키 — 신규 writer 는 datetime 없는 봉을 스킵하므로
    # 정상 경로 테스트 df 는 datetime 컬럼을 반드시 포함한다(의도적 업데이트).
    df = pd.DataFrame([
        {"date": "20260623", "time": "090100", "open": 100.0, "high": 101.0,
         "low": 99.0, "close": 100.5, "volume": 10.0, "amount": 1000.0,
         "datetime": pd.Timestamp("2026-06-23 09:01:00")},
        {"date": "20260623", "time": "090200", "open": 100.5, "high": 102.0,
         "low": 100.0, "close": 101.5, "volume": 20.0, "amount": 2000.0,
         "datetime": pd.Timestamp("2026-06-23 09:02:00")},
    ])
    rows = df_to_minute_rows("005930", df)
    assert len(rows) == 2
    assert rows[0]["stock_code"] == "005930"
    assert rows[0]["trade_date"] == "20260623"
    assert rows[0]["idx"] == 0
    assert rows[1]["idx"] == 1
    assert rows[0]["time"] == "090100"
    assert rows[1]["close"] == 101.5
    assert rows[0]["datetime"] == pd.Timestamp("2026-06-23 09:01:00").to_pydatetime()


def test_df_to_minute_rows_empty():
    assert df_to_minute_rows("005930", pd.DataFrame()) == []


def test_df_to_minute_rows_skips_nat_and_missing_datetime(caplog):
    # 자연키 없는(NaT / 누락) 봉은 적재되지 않고 경고가 남아야 한다.
    # (ON CONFLICT (stock_code, datetime) + UNIQUE 인덱스가 NULL 을 dedupe 못하는
    #  구멍 방지 — 조용한 드롭 금지.)
    df = pd.DataFrame([
        # 유효 봉
        {"date": "20260623", "time": "090100", "open": 100.0, "high": 101.0,
         "low": 99.0, "close": 100.5, "volume": 10.0, "amount": 1000.0,
         "datetime": pd.Timestamp("2026-06-23 09:01:00")},
        # NaT datetime → 스킵
        {"date": "20260623", "time": "090200", "open": 100.5, "high": 102.0,
         "low": 100.0, "close": 101.5, "volume": 20.0, "amount": 2000.0,
         "datetime": pd.NaT},
        # datetime=None → 스킵
        {"date": "20260623", "time": "090300", "open": 101.5, "high": 103.0,
         "low": 101.0, "close": 102.5, "volume": 30.0, "amount": 3000.0,
         "datetime": None},
    ])
    # setup_logger 는 propagate=False 라 caplog(root) 로 안 잡힌다 → 모듈 로거에
    # caplog 핸들러를 직접 붙여 이 로거의 경고를 캡처한다.
    minute_writer.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="collectors.minute_writer"):
            rows = df_to_minute_rows("005930", df)
    finally:
        minute_writer.logger.removeHandler(caplog.handler)
    # (a) 무효 두 봉은 적재되지 않음 — 유효 1봉만
    assert len(rows) == 1
    assert rows[0]["time"] == "090100"
    assert all(r["datetime"] is not None for r in rows)
    # (b) 스킵당 경고 2건, stock_code 포함
    warns = [rec for rec in caplog.records
             if rec.levelno == logging.WARNING and "datetime 누락/무효 봉 스킵" in rec.getMessage()]
    assert len(warns) == 2
    assert "005930" in warns[0].getMessage()


def test_df_to_minute_rows_all_missing_datetime_returns_empty():
    # datetime 컬럼 자체가 없으면 전 봉 스킵 → 빈 리스트(호출부 `if rows:` 로 무해).
    df = pd.DataFrame([
        {"date": "20260623", "time": "090100", "open": 100.0, "high": 101.0,
         "low": 99.0, "close": 100.5, "volume": 10.0, "amount": 1000.0},
    ])
    assert df_to_minute_rows("005930", df) == []
