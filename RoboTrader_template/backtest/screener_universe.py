"""스크리너-정합 백테스트 유니버스 로더.

목적: 백테스트 유니버스를 라이브 EOD 스크리너 유니버스와 정합시킨다.
정본 harness(scripts/multiverse4_returns_export.py)는 거래량 상위N(대형주)로
유니버스를 만들지만, 라이브 스크리너는 전략별 ``base_filter``(시총·거래대금 필터)를
``QuantDailyReader.get_universe_snapshot(scan_date)`` 에 적용한다. 둘이 불일치하므로
전략을 *의도 유니버스*로 측정하려면 본 모듈로 스크리너 유니버스를 재현한다.

핵심 정합점(라이브 경로와 동일):
  - 어댑터는 ``runners._adapter_factory.build_adapter`` 로 얻는다.
  - 스냅샷 dict({stock_code, market_cap, trading_value})를
    ``strategies._rule_screener_base.RuleScreenerBase._load_universe`` 와 동일하게
    {code, name, market_cap, trading_value} 로 매핑한 뒤 ``base_filter`` 를 적용한다.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger("backtest.screener_universe")


def _snapshot_to_universe(snapshot: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """get_universe_snapshot 결과를 base_filter 입력 dict 리스트로 매핑.

    RuleScreenerBase._load_universe 와 동일한 형태({code, name, market_cap, trading_value}).
    """
    return [
        {
            "code": it["stock_code"],
            "name": it["stock_code"],
            "market_cap": it.get("market_cap", 0),
            "trading_value": it.get("trading_value", 0),
        }
        for it in snapshot
    ]


def load_screener_universe(
    strategy_name: str,
    scan_date,
    *,
    broker=None,
    db_manager=None,
    config=None,
    reader=None,
) -> List[str]:
    """scan_date 의 라이브 스크리너 유니버스(=base_filter 통과 종목코드)를 반환.

    runners._adapter_factory.build_adapter(strategy_name) 로 어댑터를 얻어 그 어댑터의
    base_filter 를 QuantDailyReader.get_universe_snapshot(scan_date) 에 적용한다.

    Args:
        strategy_name: 전략 폴더키(예: "daytrading_3methods_breakout").
        scan_date: date 또는 'YYYY-MM-DD' 문자열.
        broker/db_manager/config: 어댑터 생성에 그대로 주입.
        reader: get_universe_snapshot(scan_date) 를 제공하는 객체. 미지정 시
            QuantDailyReader 를 새로 만든다(의존성 주입 → 테스트 DB 불필요).

    Returns:
        base_filter 를 통과한 종목코드(str) 리스트. 어댑터/스냅샷 부재 시 빈 리스트.
    """
    from runners._adapter_factory import build_adapter

    adapter = build_adapter(strategy_name, broker=broker, db_manager=db_manager, config=config)
    if adapter is None:
        _LOGGER.warning("어댑터 생성 실패 — 빈 유니버스 반환 (%s)", strategy_name)
        return []

    base_filter = getattr(adapter, "base_filter", None)
    if not callable(base_filter):
        _LOGGER.warning(
            "어댑터에 base_filter 없음 — 빈 유니버스 반환 (%s)", strategy_name
        )
        return []

    if reader is None:
        # 라이브 스크리너와 동일 소스(quant SSOT). DB 미가용 환경에선 reader 주입 권장.
        from db.quant_daily_reader import QuantDailyReader
        reader = QuantDailyReader()

    snapshot = reader.get_universe_snapshot(scan_date) or []
    if not snapshot:
        _LOGGER.warning("빈 스냅샷 — 빈 유니버스 반환 (%s, %s)", strategy_name, scan_date)
        return []

    universe = _snapshot_to_universe(snapshot)
    filtered = base_filter(universe)
    return [u["code"] for u in filtered]


def load_screener_universe_range(
    strategy_name: str,
    start,
    end,
    *,
    broker=None,
    db_manager=None,
    config=None,
    reader=None,
) -> Dict[date, List[str]]:
    """[start, end] 거래일별 스크리너 유니버스. load_screener_universe 의 thin wrapper.

    각 scan_date 에 대해 load_screener_universe 를 호출한다. 캘린더 거래일 산정은
    하지 않고, reader 가 date<=scan_date 방어 폴백을 하므로 호출자가 넘긴 날짜 키를
    그대로 사용한다. 날짜 시퀀스는 reader 또는 호출자가 결정한다.
    """
    from db.quant_daily_reader import QuantDailyReader  # noqa: F401  (type ref / 일관성)

    dates = _resolve_trading_dates(start, end, reader)
    out: Dict[date, List[str]] = {}
    for d in dates:
        out[d] = load_screener_universe(
            strategy_name,
            d,
            broker=broker,
            db_manager=db_manager,
            config=config,
            reader=reader,
        )
    return out


def _resolve_trading_dates(start, end, reader) -> List:
    """[start, end] 의 거래일 시퀀스. reader 가 제공하면 사용, 아니면 빈 리스트.

    reader 에 get_trading_dates(start, end) 가 있으면 그 결과를 쓰고, 없으면
    경고 후 빈 리스트(호출자가 직접 날짜를 넘기는 패턴을 권장)를 반환한다.
    """
    getter = getattr(reader, "get_trading_dates", None) if reader is not None else None
    if callable(getter):
        return list(getter(start, end) or [])
    _LOGGER.warning(
        "reader.get_trading_dates 부재 — range 로더가 날짜를 산정할 수 없어 빈 결과 반환."
        " (start=%s end=%s)", start, end
    )
    return []
