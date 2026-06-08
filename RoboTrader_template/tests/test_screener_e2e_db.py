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


@pytest.mark.skipif(_db is None, reason="DB 불가")
def test_save_screener_snapshot_handles_trading_value_scale_score():
    """score 가 거래대금(수십억) 스케일이어도 저장에 성공해야 한다.

    elder/minervini/ma20/ma5/envelope 스크리너는 score=trading_value 를 쓴다.
    score 컬럼이 NUMERIC(10,4)(≈10^6 상한)이면 오버플로우로 저장이 조용히 실패하며,
    이는 EOD 스냅샷 시스템이 5개 전략에서 비어있던 원인이다(double precision 으로 확장).
    """
    from core.candidate_selector import CandidateStock
    from strategies.screener_base import ScreenerBase

    repo = _db.candidate_repo
    strategy = "__test_overflow_guard__"
    scan_date = date(2026, 6, 5)
    params = {"probe": "score-overflow"}
    params_hash = ScreenerBase.compute_params_hash(params)
    big_score = 5_300_000_000.0  # 53억 (거래대금 스케일) — NUMERIC(10,4) 초과

    cands = [CandidateStock(code="005930", name="삼성전자", market="KRX",
                            score=big_score, reason="probe", prev_close=70000.0)]
    try:
        ok = repo.save_screener_snapshot(
            strategy=strategy, scan_date=scan_date,
            params_hash=params_hash, params_json=params, candidates=cands,
        )
        assert ok is True, "거래대금 스케일 score 저장 실패 — score 컬럼 폭 부족(오버플로우)"

        rows = repo.get_screener_snapshot(strategy, scan_date, params_hash)
        assert len(rows) == 1
        assert rows[0]["stock_code"] == "005930"
        assert float(rows[0]["score"]) == pytest.approx(big_score, rel=1e-6)
    finally:
        # 테스트 행 정리
        try:
            with _db.candidate_repo._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM screener_snapshots WHERE strategy = %s",
                    (strategy,),
                )
                conn.commit()
        except Exception:
            pass
