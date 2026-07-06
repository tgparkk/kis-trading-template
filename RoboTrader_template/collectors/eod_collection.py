"""EOD 수집 오케스트레이터 — daily→minute→index 수집 + (grace) 교차비교.

각 단계는 예외 격리(한 단계 실패가 다른 단계·EOD 흐름 비차단).
수집은 항상 새 DB. 비교는 KIS_DATA_SOURCE=='legacy'(grace) 일 때만.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.daily_collector import collect_daily, reconcile_daily  # noqa: E402
from collectors.minute_collector import collect_minute, reconcile_minute  # noqa: E402
from collectors.index_collector import collect_index, reconcile_index  # noqa: E402
from collectors.foreign_flow_collector import collect_foreign_flow, reconcile_foreign_flow  # noqa: E402
from collectors.corp_events_collector import collect_corp_events, reconcile_corp_events  # noqa: E402
from config.constants import KIS_DATA_SOURCE  # noqa: E402
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
        "foreign_flow": _safe(collect_foreign_flow, trade_date),
        "corp_events": _safe(collect_corp_events, trade_date),
        "reconcile": {},
    }
    if KIS_DATA_SOURCE == "legacy" and trade_date:
        # reconcile_*는 'YYYY-MM-DD'(daily)·'YYYYMMDD'(minute) 형식차 주의 — 호출측이 맞춰 전달
        dash = trade_date if "-" in trade_date else f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        compact = trade_date.replace("-", "")
        out["reconcile"] = {
            "daily": _safe(reconcile_daily, dash),
            "minute": _safe(reconcile_minute, compact),
            "index": _safe(reconcile_index, dash),
            "foreign_flow": _safe(reconcile_foreign_flow, dash),
            "corp_events": _safe(reconcile_corp_events, dash),
        }
    return out
