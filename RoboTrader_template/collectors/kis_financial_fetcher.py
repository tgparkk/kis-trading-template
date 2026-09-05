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


def fetch_quarterly_ratio(stock_code: str) -> list:
    """div_cls='1'(분기) 명시 조회 → upsert_kis_ratio 용 행 리스트."""
    entries = get_financial_ratio(stock_code, div_cls="1")
    rows = []
    for e in entries or []:
        if not e.statement_ym:
            continue
        rows.append({
            "stock_code": stock_code,
            "stac_yymm": e.statement_ym,
            "div_cls": "1",
            "roe_value": e.roe_value,
            "per": e.per,
            "eps": e.eps,
            "sps": e.sps,
            "bps": e.bps,
            "reserve_ratio": e.reserve_ratio,
            "liability_ratio": e.liability_ratio,
            "sales_growth": e.sales_growth,
            "operating_income_growth": e.operating_income_growth,
            "net_income_growth": e.net_income_growth,
            "raw_json": json.dumps(e.raw, ensure_ascii=False),
        })
    return rows
