"""재현기 테스트 공용 설정 — 라이브 트리 밖(워크트리)에서만 돌린다."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]   # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    config.addinivalue_line("markers", "db: 실 DB(kis_template) 필요 — 없으면 skip")


@pytest.fixture(scope="session")
def db_conn():
    """SELECT 전용 커넥션. 접속 불가면 skip."""
    psycopg2 = pytest.importorskip("psycopg2")
    from backtest.concept_axes.replayer.loader import dsn
    try:
        conn = psycopg2.connect(**dsn())
    except psycopg2.Error as e:      # pragma: no cover - 환경 의존
        pytest.skip(f"DB 접속 불가: {e}")
    conn.set_session(readonly=True)
    yield conn
    conn.close()
