"""KRX 상장목록 캐시 CSV 를 «날짜 지정»으로 직접 읽는다. FDR 을 부르지 않는다.

🔑 fdr.StockListing('KRX-DESC') 는 결국 이 CSV 를 읽는다
   (venv/.../FinanceDataReader/data.py:175 KrxStockListingCache). FDR 을 거치면
   ①KRX 포털 bld 호출이 1건 붙고 ②응답에 «기준일»이 안 남는다. 직접 읽으면
   호출 0 + 파일명이 그대로 source_asof 다.
🔴 파일명은 «게시일»이지 «내용 기준일»이 아니다 — 토요일 파일은 금요일 파일과
   바이트 동일하다(실측 md5 874ee3c0…). 그래서 source_asof 의 의미는
   «내용 기준일 ≤ 게시일» 이고, 매일 뒤처지면 §8-7 이 WARN 한다.
🔴 KIS 를 쓰지 않는다(앱키당 토큰 1개 — 봇 가동 중 호출은 라이브 토큰을 무효화한다).
"""
import gzip
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

GITHUB_DESC_BASE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                    "refs/heads/master/data/listing/desc")
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "scratchpad", "sector")
MAX_BACKOFF_DAYS = 7
MIN_SCALE_RATIO = 0.8
# 시장 «묶음»별로 하한을 건다 — 합계로 걸면 한쪽 붕괴를 다른 쪽이 가려준다.
MARKET_GROUPS = {"KOSPI": ("KOSPI",), "KOSDAQ": ("KOSDAQ", "KOSDAQ GLOBAL")}
IGNORED_MARKETS = ("KONEX",)


def _default_fetcher(url):
    import requests
    r = requests.get(url, timeout=30)
    return r.status_code, r.content


def fetch_desc_csv(trade_date, fetcher=None, max_back_days=MAX_BACKOFF_DAYS):
    """{trade_date}.csv 부터 하루씩 최대 max_back_days 후퇴. → (source_asof, raw)."""
    fn = fetcher or _default_fetcher
    tried = []
    for back in range(0, max_back_days + 1):
        d = trade_date - timedelta(days=back)
        status, body = fn("%s/%s.csv" % (GITHUB_DESC_BASE, d.isoformat()))
        tried.append("%s:%s" % (d.isoformat(), status))
        if status == 200 and body:
            if back:
                logger.warning("[krx_desc] %s 캐시 없음 - %d일 후퇴해 %s 사용",
                               trade_date, back, d)
            return d, body
    raise RuntimeError("KRX desc 캐시 CSV 를 %d일 후퇴까지 못 찾음: %s"
                       % (max_back_days, " · ".join(tried)))


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def parse_desc_csv(raw: bytes):
    """→ (rows, dropped). Code 6자리 정규화 · KONEX 제외(U_all 밖) · 0건이면 RuntimeError."""
    import io
    import pandas as pd
    df = pd.read_csv(io.BytesIO(raw), dtype=str)
    rows = []
    dropped = {"konex": 0, "bad_code": 0}
    for rec in df.to_dict("records"):
        code = _s(rec.get("Code"))
        market = _s(rec.get("Market"))
        if not code:
            dropped["bad_code"] += 1
            continue
        if market in IGNORED_MARKETS:
            dropped["konex"] += 1
            continue
        rows.append({
            "stock_code": code.zfill(6),
            "market": market,
            "ksic3_name": _s(rec.get("Industry")),
            "kosdaq_dept": _s(rec.get("Sector")),
            "products": _s(rec.get("Products")),
            "listing_date": _s(rec.get("ListingDate")),
            "settle_month": _s(rec.get("SettleMonth")),
        })
    if not rows:
        raise RuntimeError("KRX desc 캐시 CSV 파싱 결과 0건 — 형식이 바뀌었거나 빈 응답이다")
    return rows, dropped


def fold_market_counts(raw_counts: dict) -> dict:
    """{시장: n} → {묶음: n}. 묶음 밖 시장(KONEX 등)은 버린다."""
    out = dict((g, 0) for g in MARKET_GROUPS)
    for m, n in (raw_counts or {}).items():
        for g, members in MARKET_GROUPS.items():
            if m in members:
                out[g] += int(n)
    return out


def market_counts(rows) -> dict:
    tally = {}
    for r in rows:
        tally[r["market"]] = tally.get(r["market"], 0) + 1
    return fold_market_counts(tally)


def check_scale_floor(existing: dict, collected: dict) -> None:
    """묶음별 규모 하한. 기존 0 은 면제(최초 수집). 미달이면 RuntimeError — 쓰기 «전»에 부른다.

    ⚠️ 기준선(열린 줄)은 상폐로 줄지 않으므로 약 6년 뒤엔 정상 수집도 거부될 수 있다.
       stock_market_collector 와 같은 «소리 나는» 한계다(그때 기준을 다시 잡는다).
    """
    short = []
    for g in sorted(MARKET_GROUPS):
        prev = int((existing or {}).get(g, 0))
        if prev <= 0:
            continue
        floor = prev * MIN_SCALE_RATIO
        n = int((collected or {}).get(g, 0))
        if n < floor:
            short.append("%s %d건 < 기존 %d건의 %.0f%%(%.0f건)"
                         % (g, n, prev, MIN_SCALE_RATIO * 100, floor))
    if short:
        raise RuntimeError("KRX desc 캐시 규모 하한 미달 — 한 행도 쓰지 않음"
                           "(어제 명부 유지): " + " · ".join(short))


def archive_raw(source_asof, raw: bytes) -> str:
    """원본 gz 보관 — §5-4 `--regen-map` 의 원료다. 같은 게시일 파일은 덮어쓰지 않는다."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    path = os.path.join(ARCHIVE_DIR, "krx_desc_%s.csv.gz" % source_asof.isoformat())
    if not os.path.exists(path):
        with gzip.open(path, "wb") as fh:
            fh.write(raw)
    return path


def load_desc(trade_date, existing_counts=None, fetcher=None, archive=True) -> dict:
    """읽기 → 파싱 → 규모 하한 → 보관. 검증은 «반드시» 보관·쓰기보다 먼저다.

    archive=False 는 `--dry-run` 전용이다 — dry-run 이 gz 를 남기면 「쓰기 0」이 거짓이 되고,
    §5-4 재생성 원료에 «실제로는 안 쓴 날»의 파일이 섞인다.
    """
    source_asof, raw = fetch_desc_csv(trade_date, fetcher=fetcher)
    rows, dropped = parse_desc_csv(raw)
    counts = market_counts(rows)
    check_scale_floor(existing_counts or {}, counts)
    path = archive_raw(source_asof, raw) if archive else None
    logger.info("[krx_desc] %s 게시분 %d행 (%s) 보관=%s",
                source_asof, len(rows), counts,
                os.path.basename(path) if path else "(dry-run)")
    return {"source_asof": source_asof, "rows": rows, "counts": counts,
            "dropped": dropped, "archive": path}
