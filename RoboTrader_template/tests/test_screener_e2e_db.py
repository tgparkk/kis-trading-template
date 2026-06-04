"""
Task 12: 실DB 스캔 스모크
==========================
MinerviniVolumeDryupScreenerAdapter 를 실 DB 에 연결해 scan() 호출이 예외 없이
완료되고 CandidateStock 리스트를 반환하는지 검증한다.

DB 를 사용할 수 없는 환경에서는 자동으로 skip 된다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from datetime import date

try:
    from db.database_manager import DatabaseManager
    _db = DatabaseManager()
except Exception:
    _db = None


@pytest.mark.skipif(_db is None, reason="DB 불가")
def test_minervini_scan_runs_on_real_db():
    from strategies.minervini_volume_dryup.screener import MinerviniVolumeDryupScreenerAdapter
    a = MinerviniVolumeDryupScreenerAdapter(db_manager=_db)
    out = a.scan(date(2026, 6, 4), a.default_params())
    assert isinstance(out, list)
    for c in out:
        assert c.code and c.reason
