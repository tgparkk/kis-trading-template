"""
Screener Snapshot Provider
===========================

screener_snapshots DB 테이블에서 날짜별 후보 코드 리스트를 반환하는
candidate_provider 콜백 팩토리.

승격 이력: `backtest/engine.py`의 `make_screener_snapshot_provider`(1334-1396)를
운영 코드(`core/candidate_selector.py`)가 지연 import로 참조하고 있던 것을
2026-07-02 Phase2(god-file-split)에서 이 모듈로 verbatim 승격했습니다.
`backtest/engine.py`는 하위호환을 위해 re-export만 유지합니다.
"""

from __future__ import annotations

import logging
from datetime import date as DateType
from typing import Callable, Dict, List, Optional

# CandidateRepository는 이 팩토리에서만 사용.
# DB 의존성이 없는 환경(순수 백테스트)에서는 import만 해두고 실제 호출은 provider 내부에서 발생.
try:
    from db.repositories.candidate import CandidateRepository as CandidateRepository
except ImportError:  # DB 패키지 없는 경량 환경
    CandidateRepository = None  # type: ignore[assignment,misc]


def make_screener_snapshot_provider(
    strategy_name: str,
    params_hash: Optional[str] = None,
) -> Callable[[str, str], List[str]]:
    """
    screener_snapshots DB 테이블에서 날짜별 후보 코드 리스트를 반환하는
    candidate_provider 콜백을 생성합니다.

    Usage:
        from core.screener_snapshot_provider import make_screener_snapshot_provider
        from backtest.engine import BacktestEngine  # 백테스트 엔진과 조합 시

        provider = make_screener_snapshot_provider("SampleStrategy")
        result = engine.run(
            stock_codes=all_codes,
            daily_data=data,
            candidate_provider=provider,
        )

    Args:
        strategy_name: screener_snapshots.strategy 컬럼값 (예: "SampleStrategy")
        params_hash: 특정 파라미터 해시로 한정할 경우 지정. None이면 해당 날짜의
                     모든 파라미터 해시 스냅샷을 합산해 후보 풀 구성.

    Returns:
        (strategy_name: str, scan_date: str) → List[str] 형태의 콜백.
        DB 조회 실패 또는 스냅샷 없는 날짜는 빈 리스트를 반환합니다.
    """
    # 조회 결과를 날짜별로 캐싱해 반복 DB 호출 방지
    _cache: Dict[str, List[str]] = {}

    def _provider(strategy: str, scan_date: str) -> List[str]:
        if scan_date in _cache:
            return _cache[scan_date]

        try:
            if CandidateRepository is None:
                raise ImportError("db.repositories.candidate 패키지를 사용할 수 없습니다")

            repo = CandidateRepository()
            parsed_date = DateType.fromisoformat(scan_date)

            if params_hash:
                rows = repo.get_screener_snapshot(strategy_name, parsed_date, params_hash)
                codes = [r["stock_code"] for r in rows]
            else:
                df = repo.get_snapshot_date_range(
                    strategy=strategy_name,
                    start_date=parsed_date,
                    end_date=parsed_date,
                    params_hash=None,
                )
                codes = df["stock_code"].tolist() if not df.empty else []

            _cache[scan_date] = codes
            return codes

        except Exception as e:
            logging.getLogger("backtest.screener_provider").warning(
                f"screener_snapshots 조회 실패 [{scan_date}]: {e}"
            )
            _cache[scan_date] = []
            return []

    return _provider
