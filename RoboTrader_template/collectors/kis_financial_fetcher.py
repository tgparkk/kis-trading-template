"""KIS 재무비율(분기) → kis_financial_ratio 행.

🔴 이 데이터에는 접수일이 없다 ⇒ PIT 앵커가 없다 ⇒ PIT 조회에 쓰면 안 된다.
   용도는 «교차검증 전용»이다 — DART 원시계정으로 계산한 비율과 대조한다.
   봉쇄는 3겹: ①날짜형 컬럼 없음 ②PIT 경로가 참조 안 함 ③테스트가 ②를 고정.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.kis_financial_api import get_financial_ratio  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


def _to_float_or_none(value):
    """None/blank/"-" → None, otherwise float (strip commas)."""
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def fetch_quarterly_ratio(stock_code: str) -> list:
    """div_cls='1'(분기) 명시 조회 → upsert_kis_ratio 용 행 리스트."""
    entries = get_financial_ratio(stock_code, div_cls="1")
    rows = []
    for e in entries or []:
        # stac_yymm: try raw first, fallback to e.statement_ym
        stac_yymm = str(e.raw.get("stac_yymm", "")).strip() if e.raw else ""
        if not stac_yymm:
            stac_yymm = e.statement_ym
        if not stac_yymm:
            logger.warning(f"⚠️ KIS 분기비율 조회: statement_ym 없음 — {stock_code}, raw stac_yymm={e.raw.get('stac_yymm') if e.raw else None}")
            continue

        # Extract numeric fields from raw with proper None handling
        roe_value = _to_float_or_none(e.raw.get("roe_val") if e.raw else None)
        per_raw = (
            (e.raw.get("per_pbr_rate")
             or e.raw.get("per")
             or e.raw.get("eps_per_rto")
             or e.raw.get("stk_per"))
            if e.raw
            else None
        )
        per = _to_float_or_none(per_raw)
        eps = _to_float_or_none(e.raw.get("eps") if e.raw else None)
        sps = _to_float_or_none(e.raw.get("sps") if e.raw else None)
        bps = _to_float_or_none(e.raw.get("bps") if e.raw else None)
        reserve_ratio = _to_float_or_none(e.raw.get("rsrv_rate") if e.raw else None)
        liability_ratio = _to_float_or_none(e.raw.get("lblt_rate") if e.raw else None)
        sales_growth = _to_float_or_none(e.raw.get("grs") if e.raw else None)
        operating_income_growth = _to_float_or_none(e.raw.get("bsop_prfi_inrt") if e.raw else None)
        net_income_growth = _to_float_or_none(e.raw.get("ntin_inrt") if e.raw else None)

        # Check if all numeric fields are None (tripwire for key rename)
        numeric_fields = [
            roe_value, per, eps, sps, bps,
            reserve_ratio, liability_ratio, sales_growth,
            operating_income_growth, net_income_growth
        ]
        if all(f is None for f in numeric_fields):
            raw_keys = sorted(e.raw.keys()) if e.raw else []
            logger.warning(
                f"⚠️ KIS 분기비율 조회: 모든 재무비율이 None — {stock_code}, "
                f"stac_yymm={stac_yymm}, raw_keys={raw_keys}"
            )

        rows.append({
            "stock_code": stock_code,
            "stac_yymm": stac_yymm,
            "div_cls": "1",
            "roe_value": roe_value,
            "per": per,
            "eps": eps,
            "sps": sps,
            "bps": bps,
            "reserve_ratio": reserve_ratio,
            "liability_ratio": liability_ratio,
            "sales_growth": sales_growth,
            "operating_income_growth": operating_income_growth,
            "net_income_growth": net_income_growth,
            "raw_json": json.dumps(e.raw, ensure_ascii=False),
        })
    return rows
