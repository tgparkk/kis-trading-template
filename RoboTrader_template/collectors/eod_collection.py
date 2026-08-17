"""EOD 수집 오케스트레이터 — daily→minute→index 등 각 소스 수집.

각 단계는 예외 격리(한 단계 실패가 다른 단계·EOD 흐름 비차단).
수집 대상은 항상 kis_template 단일 DB.

2026-08-17: 레거시 교차비교(reconcile) 제거.
  `if KIS_DATA_SOURCE == "legacy"` 게이트 안에서만 돌던 「새 DB vs robotrader(_quant)」
  대조였다. 레거시 두 DB 는 2026-07-10 동결이라 이미 휴면이었고, `robotrader` DB
  삭제와 함께 롤백 스위치 자체가 폐지되면서 **도달 불가 코드**가 됐다.
  ⚠️ 반환 dict 의 ``"reconcile"`` 키는 **빈 dict 로 유지**한다 —
     bot/system_monitor.py 가 이 키를 읽어 로그 문구를 고른다(라이브 계약 불변).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.daily_collector import collect_daily  # noqa: E402
from collectors.minute_collector import collect_minute  # noqa: E402
from collectors.index_collector import collect_index  # noqa: E402
from collectors.stock_market_collector import collect_stock_market  # noqa: E402
from core.regime.market_classifier import reset_cache as reset_market_cache  # noqa: E402
from collectors.foreign_flow_collector import collect_foreign_flow  # noqa: E402
from collectors.corp_events_collector import collect_corp_events  # noqa: E402
# 🔴 수급 3축 — investor·program 은 공급 TR 이 «최근 30 거래일»만 주므로 거른 날이 영구 결손이
#    된다. 그래서 EOD 에 붙인다. 다만 매일 2,763종목을 때리면 과하므로 각 수집기가
#    **신선도 가드**(마지막 적재일이 5일 이상 낡았을 때만 실행)를 스스로 건다.
from collectors.investor_trend_collector import collect_investor_trend  # noqa: E402
from collectors.market_flow_collector import (  # noqa: E402
    collect_credit_balance, collect_overtime, collect_program_trade, collect_short_sale,
)
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001 — 단계 격리
        logger.error(f"EOD 수집 단계 실패 {getattr(fn, '__name__', fn)}: {e}")
        return {"error": str(e)}


def run_data_collection(trade_date: str = None) -> dict:
    out = {
        "daily": _safe(collect_daily, trade_date),
        "minute": _safe(collect_minute, trade_date),
        "index": _safe(collect_index),
        "stock_market": _safe(collect_stock_market),
        "foreign_flow": _safe(collect_foreign_flow, trade_date),
        "corp_events": _safe(collect_corp_events, trade_date),
        "investor_trend": _safe(collect_investor_trend, trade_date),
        "program_trade": _safe(collect_program_trade, trade_date),
        "short_sale": _safe(collect_short_sale, trade_date),
        "credit_balance": _safe(collect_credit_balance, trade_date),
        "overtime": _safe(collect_overtime, trade_date),
        # 레거시 교차비교 폐지 후에도 키는 유지 — system_monitor 가 읽는 계약이다.
        # 항상 비어 있으므로 EOD 로그는 "(전환완료 비교생략)" 으로 고정된다.
        "reconcile": {},
    }
    # 매핑이 실제로 갱신된 경우에만 프로세스 캐시를 무효화한다.
    # 실패했는데 리셋하면 다음 조회가 빈/낡은 테이블을 다시 읽어 매핑을 잃는다.
    if "error" not in out["stock_market"]:
        _safe(reset_market_cache)
    return out
