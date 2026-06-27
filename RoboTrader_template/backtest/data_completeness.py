"""백테스트 데이터완전성 가드 — 측정 구간 market_cap 채움률 점검.

배경(2026-06-27): 스크리너 ``base_filter`` 의 시총 가드를 *fail-closed*(결측 종목 제외)로
고쳤다. 하지만 quant ``daily_prices`` 의 ``market_cap`` 채움률은 2021=0% / 2022=0% /
2023=0.3% / 2024=84.8% / 2025=99.6% / 2026=99.8% 로, 2021–23 구간 백테스트는
*모든 종목이 결측* 이라 시총컷이 사실상 전종목 제외(또는 과거 fail-open 시절엔 전부 통과)로
**조용히 왜곡**된다. 본 가드는 측정 구간 snapshot 의 market_cap 채움률을 점검해 임계 미만이면
경고/실패시켜, 오염 구간을 모르고 측정하는 사일런트 재발을 막는다.

라이브 경로는 ``get_universe_snapshot`` 이 ``COALESCE(market_cap,0)`` 을 돌려주므로
결측 = 0.0 으로 들어온다 → ``market_cap > 0`` 인 행을 '채워짐'으로 센다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger("backtest.data_completeness")


class DataCompletenessError(RuntimeError):
    """측정 구간 데이터완전성(market_cap 채움률)이 임계 미만일 때(strict)."""


@dataclass
class CoverageReport:
    n_snapshots: int                       # 실제 비어있지 않은 snapshot 수
    total_rows: int
    filled_rows: int                       # market_cap > 0 인 행 수
    coverage: float                        # filled_rows / total_rows (0~1), total=0 이면 0.0
    min_coverage: float
    ok: bool
    per_date: Dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"market_cap coverage={self.coverage:.1%} "
            f"({self.filled_rows}/{self.total_rows} rows, "
            f"{self.n_snapshots} snapshots) "
            f"min_required={self.min_coverage:.0%} -> {'OK' if self.ok else 'LOW'}"
        )


def _to_date_str(d: Any) -> str:
    if isinstance(d, str):
        return d[:10]
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def market_cap_coverage(
    reader,
    scan_dates: List[Any],
    *,
    min_coverage: float = 0.8,
) -> CoverageReport:
    """scan_dates 의 snapshot 을 모아 market_cap 채움률(>0)을 집계한다.

    Args:
        reader: ``get_universe_snapshot(scan_date)`` 를 제공하는 객체(QuantDailyReader 등).
        scan_dates: date/'YYYY-MM-DD' 리스트(월별 등).
        min_coverage: 합격 임계(0~1). 전체 채움률이 이 미만이면 ok=False.

    Returns:
        CoverageReport. snapshot 이 전혀 없으면 total_rows=0, coverage=0.0, ok=False.
    """
    total = 0
    filled = 0
    n_snap = 0
    per_date: Dict[str, float] = {}
    for d in scan_dates:
        d_str = _to_date_str(d)
        snap = reader.get_universe_snapshot(d) or []
        if not snap:
            per_date[d_str] = 0.0
            continue
        n_snap += 1
        n = len(snap)
        f = sum(1 for it in snap if (it.get("market_cap") or 0) > 0)
        total += n
        filled += f
        per_date[d_str] = (f / n) if n else 0.0
    coverage = (filled / total) if total else 0.0
    ok = total > 0 and coverage >= min_coverage
    return CoverageReport(
        n_snapshots=n_snap, total_rows=total, filled_rows=filled,
        coverage=coverage, min_coverage=min_coverage, ok=ok, per_date=per_date,
    )


def assert_market_cap_coverage(
    reader,
    scan_dates: List[Any],
    *,
    min_coverage: float = 0.8,
    strict: bool = False,
    logger: Optional[logging.Logger] = None,
) -> CoverageReport:
    """채움률을 점검하고, 임계 미만이면 strict=True 시 예외, 아니면 경고 로그.

    합격 시 조용히 통과(경고 없음). 측정 스크립트 진입부에서 호출해 오염 구간을 가시화한다.

    Raises:
        DataCompletenessError: strict=True 이고 채움률이 min_coverage 미만일 때.
    """
    log = logger or _LOGGER
    report = market_cap_coverage(reader, scan_dates, min_coverage=min_coverage)
    if not report.ok:
        msg = (
            "데이터완전성 경고 — 측정 구간 market_cap 채움률이 임계 미만입니다. "
            "이 구간 시총컷은 신뢰할 수 없습니다(오염 측정 위험). " + report.summary()
        )
        if strict:
            raise DataCompletenessError(msg)
        log.warning(msg)
    return report
