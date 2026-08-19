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

        🔑 **「스냅샷이 없다」와 「조회가 고장났다」를 «갈라서» 돌려줍니다.**

        - 스냅샷 없는 날짜 → `[]` (**정상**. 그날 조건에 맞는 종목이 없었다는 뜻)
        - DB 조회 실패     → **예외를 그대로 올려보냅니다** (호출자가 판단한다)

        ⚠️ 2026-08-19 이전에는 예외를 삼키고 `[]` 를 돌려줬습니다. 그 결과
        `core/candidate_selector.py` 의 fail-closed `except` 가 **도달 불가**였고,
        DB 고장이 `[E6] ... 조건에 맞는 종목 없음, 금일 미진입` 이라는 **INFO(정상)**
        메시지로 보고됐습니다. 즉 ***폴백이 고장을 「대비」한 게 아니라 「감췄습니다」.***

        ⚠️ 백테스트(`backtest/engine.py:321`)도 이 콜백을 감싸지 않고 호출하므로,
        DB 고장 시 백테스트는 이제 **조용히 후보 0건으로 진행하지 않고 중단**됩니다.
        연구 산출물이 조용히 오염되는 것보다 시끄럽게 멈추는 편이 맞습니다.
    """
    # 조회 결과를 날짜별로 캐싱해 반복 DB 호출 방지
    _cache: Dict[str, List[str]] = {}

    def _provider(strategy: str, scan_date: str) -> List[str]:
        if scan_date in _cache:
            return _cache[scan_date]

        # 🔴 예외를 «삼키지 않는다». 여기서 [] 로 뭉개면 「없다」와 「고장」이
        #    같은 값이 되고, 호출자는 고장을 정상으로 보고하게 된다.
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
            # 빈 결과는 «정상» — 그날 스냅샷이 없었다는 뜻이다.
            codes = df["stock_code"].tolist() if not df.empty else []

        # 🔑 «성공만» 캐시한다. 실패를 캐시하면 순간 장애 한 번이
        #    프로세스 수명 동안 그 날짜를 통째로 죽여 재시도가 봉쇄된다.
        _cache[scan_date] = codes
        return codes

    return _provider
