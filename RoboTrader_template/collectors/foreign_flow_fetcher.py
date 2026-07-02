"""네이버 금융 외국인 순매매량 fetch (scripts/backfill_foreign_flow.py 에서 승격).

라이브 EOD 수집기(collectors/foreign_flow_collector.py)가 사용 (2026-07-02 Phase1, 동작 무변경).
PIT 강제: T일 데이터를 T일로 저장, shift(-N) 절대 금지.
"""
from __future__ import annotations

import logging
import time
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.naver.com/",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    return s


def fetch_foreign_naver(
    code: str,
    max_pages: int = 40,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """네이버 금융에서 종목별 일별 외국인 순매매량 수집.

    PIT 강제:
        - 네이버 frgn.naver는 T일 장 마감 후 발표된 T일 실적값 제공
        - T일 데이터를 T일로 저장, 시그널 생성 시 shift(1) 사용
        - shift(-N) 절대 금지
    """
    if session is None:
        session = _make_session()

    all_rows: list[pd.DataFrame] = []
    for page in range(1, max_pages + 1):
        try:
            r = session.get(
                "https://finance.naver.com/item/frgn.naver",
                params={"code": code, "page": page},
                timeout=15,
            )
            if r.status_code != 200:
                logger.warning("[%s] HTTP %d (page=%d)", code, r.status_code, page)
                break

            tables = pd.read_html(StringIO(r.text), encoding="utf-8")
            if len(tables) <= 3:
                break

            t = tables[3]
            if isinstance(t.columns, pd.MultiIndex):
                t.columns = ["_".join(str(c) for c in col).strip("_") for col in t.columns]
            t = t.dropna(how="all")

            date_col = next((c for c in t.columns if "날짜" in str(c)), None)
            foreign_col = next(
                (c for c in t.columns if "외국인" in str(c) and "순매매" in str(c)), None
            )
            if not date_col or not foreign_col:
                if t.shape[1] >= 7:
                    cols = (
                        ["날짜", "종가", "전일비", "등락률", "거래량", "기관_순매매량", "외국인_순매매량"]
                        + [f"col{i}" for i in range(t.shape[1] - 7)]
                    )
                    t.columns = cols[:t.shape[1]]
                    date_col, foreign_col = "날짜", "외국인_순매매량"
                else:
                    logger.debug("[%s] p%d: 컬럼 파싱 실패 %s", code, page, list(t.columns))
                    break

            sub = t[[date_col, foreign_col]].copy()
            sub.columns = ["date", "foreign_net_vol"]
            sub = sub.dropna(subset=["date"])
            sub = sub[sub["date"].astype(str).str.match(r"^\d{4}\.\d{2}\.\d{2}$")]
            if sub.empty:
                break

            sub["date"] = pd.to_datetime(sub["date"], format="%Y.%m.%d").dt.date
            sub["foreign_net_vol"] = (
                sub["foreign_net_vol"]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("+", "", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
            )

            all_rows.append(sub)
            if len(sub) < 10:
                break
            time.sleep(0.2)

        except Exception as e:
            logger.warning("[%s] p%d: %s", code, page, e)
            break

    if not all_rows:
        return pd.DataFrame(columns=["date", "foreign_net_vol"])

    result = pd.concat(all_rows, ignore_index=True)
    result = result.drop_duplicates(subset=["date"]).sort_values("date")
    return result
