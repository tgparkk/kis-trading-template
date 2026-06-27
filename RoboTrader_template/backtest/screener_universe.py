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
from typing import Any, Callable, Dict, List, Optional

_LOGGER = logging.getLogger("backtest.screener_universe")


def _snapshot_to_universe(snapshot: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """get_universe_snapshot 결과를 base_filter 입력 dict 리스트로 매핑.

    RuleScreenerBase._load_universe 와 동일한 형태({code, name, market_cap, trading_value}).
    """
    return [
        {
            "code": it["stock_code"],
            "name": it["stock_code"],
            # 결측을 0 으로 위장하지 않는다 — base_filter 가 결측(None/0)을 fail-closed 제외.
            "market_cap": it.get("market_cap"),
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


# ---------------------------------------------------------------------------
# PIT(point-in-time) 게이팅 — 신호캐시를 진입봉 날짜의 스크리너 멤버십으로 거른다.
#
# 라이브 충실: EOD 스크리너가 scan_date 의 base_filter 통과집합을 만들고 *익일* 진입한다.
# 따라서 진입봉 d 의 PIT 판정은 "가장 최근 scan_date <= d 의 통과집합" 멤버십이다
# (date<= 폴백 = QuantDailyReader.get_universe_snapshot 의 방어 폴백과 같은 결).
#
# Step2 의 정적 union(기간 내 한 번이라도 통과)과 달리, PIT 는 진입일 시점 멤버십만
# 인정하므로 풀기간 union 퇴화(전체시장 ~97%)를 피한다. scan 빈도는 월별 근사
# (시총·거래대금이 완만 → 분기보다 정밀하면서 일별보다 가벼움).
# ---------------------------------------------------------------------------


def pit_gate_signal_cache(
    signal_cache: Dict[str, List[int]],
    data: Dict[str, "Any"],
    eligible_resolver: Callable[[str, Any], bool],
) -> Dict[str, List[int]]:
    """신호캐시를 PIT 게이팅한다.

    각 (code, bar_idx) 에 대해 그 봉의 날짜를 ``data[code].iloc[bar_idx]['datetime']`` 로
    구하고, ``eligible_resolver(code, bar_date)`` 가 False 면 그 신호 bar 를 제거한다.

    Args:
        signal_cache: {code: [bar_idx, ...]} (multiverse4 _precompute_signals 산출 형태).
        data: {code: DataFrame(datetime, open, high, low, close, volume)}.
        eligible_resolver: (code:str, d:date|Timestamp) -> bool. PIT 적격 판정.

    Returns:
        게이팅 후 {code: [bar_idx, ...]}. data 에 없는 종목은 빈 리스트(예외 없음).
    """
    gated: Dict[str, List[int]] = {}
    for code, bars in signal_cache.items():
        df = data.get(code)
        if df is None or len(df) == 0:
            gated[code] = []
            continue
        kept: List[int] = []
        for bar_idx in bars:
            try:
                bar_date = df.iloc[bar_idx]["datetime"]
            except (IndexError, KeyError):
                continue
            if eligible_resolver(code, bar_date):
                kept.append(bar_idx)
        gated[code] = kept
    return gated


def make_scan_eligible_resolver(
    strategy_name: str,
    scan_dates: List[str],
    *,
    broker=None,
    db_manager=None,
    config=None,
    reader=None,
) -> Callable[[str, Any], bool]:
    """월별 scan_date 들의 스크리너 통과집합을 미리 만들어 PIT resolver 를 반환한다.

    각 scan_date 에 대해 ``load_screener_universe(strategy_name, scan_date)`` 로 그 날의
    base_filter 통과 종목집합을 1회 조회·캐시한다(reader 는 날짜당 1회만 친다).
    반환 resolver(code, d) 는 ``가장 최근 scan_date <= d`` 의 통과집합 멤버십으로 PIT 판정.

    - d 가 두 scan_date 사이면 *직전* scan_date 집합을 쓴다(date<= 폴백).
    - d 가 첫 scan_date 보다 이르면 적용할 집합이 없어 False(미적격).
    - scan_dates 는 정렬되지 않아도 됨(내부 정렬).

    Args:
        strategy_name: 전략 폴더키.
        scan_dates: 'YYYY-MM-DD' 문자열 리스트(월별 등).
        broker/db_manager/config: 어댑터 생성에 그대로 주입.
        reader: get_universe_snapshot(scan_date) 제공 객체. 미지정 시 QuantDailyReader 생성.

    Returns:
        (code:str, d:date|Timestamp|str) -> bool.
    """
    sorted_dates = sorted(
        {(d if isinstance(d, str) else _to_date_str(d)) for d in scan_dates}
    )
    # scan_date 별 통과집합 캐시(지연 로딩 — 첫 조회 시 1회 DB 조회).
    passers: Dict[str, set] = {}

    def _passers_for(scan_date: str) -> set:
        if scan_date not in passers:
            codes = load_screener_universe(
                strategy_name,
                scan_date,
                broker=broker,
                db_manager=db_manager,
                config=config,
                reader=reader,
            )
            passers[scan_date] = set(codes)
        return passers[scan_date]

    def resolver(code: str, d: Any) -> bool:
        d_str = d if isinstance(d, str) else _to_date_str(d)
        # 가장 최근 scan_date <= d_str 찾기 (정렬 리스트 역순 스캔).
        chosen: Optional[str] = None
        for sd in reversed(sorted_dates):
            if sd <= d_str:
                chosen = sd
                break
        if chosen is None:
            return False
        return code in _passers_for(chosen)

    return resolver


def _to_date_str(d) -> str:
    """date/Timestamp/str → 'YYYY-MM-DD' (문자열 비교용 정규화)."""
    if isinstance(d, str):
        return d[:10]
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


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
