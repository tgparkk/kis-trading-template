# collectors/minute_universe.py
"""분봉 유니버스 — 거래대금순(fid_blng_cls_code=3) top300, 6가격밴드×2시장."""
import time
from api import kis_market_api

PRICE_BANDS = [
    ("5000", "15000"), ("15000", "30000"), ("30000", "60000"),
    ("60000", "120000"), ("120000", "250000"), ("250000", "500000"),
]
MARKETS = ["0001", "1001"]  # KOSPI, KOSDAQ


def parse_rank_codes(df) -> list:
    if df is None or len(df) == 0:
        return []
    out = []
    for _, row in df.iterrows():
        code = str(row.get("mksc_shrn_iscd", "")).strip()
        if len(code) == 6 and code.isdigit() and not code.endswith("5"):
            out.append(code)
    return out


def select_top_volume(top_n: int = 300) -> list:
    """거래대금순으로 6밴드×2시장 수집→등장순(=대금상위) dedup→top_n."""
    seen = []
    seen_set = set()
    for market in MARKETS:
        for lo, hi in PRICE_BANDS:
            df = kis_market_api.get_volume_rank(
                fid_input_iscd=market, fid_div_cls_code="1",
                fid_blng_cls_code="3", fid_input_price_1=lo, fid_input_price_2=hi)
            for code in parse_rank_codes(df):
                if code not in seen_set:
                    seen_set.add(code); seen.append(code)
            time.sleep(0.08)
    return seen[:top_n]
