# collectors/minute_collector.py
"""분봉 수집 오케스트레이터 — top300 + 태쏘 후보 → 당일 분봉 fetch → minute_candles.

usage:
  python -m collectors.minute_collector --limit 5
  python -m collectors.minute_collector

2026-08-17: `reconcile_minute`(+`_load_bars`/`minute_match_rate`) 제거. 「새 DB vs
  레거시 robotrader」 당일 분봉 대조였는데, 레거시는 2026-07-10 동결이라 이미
  휴면이었고 `KIS_DATA_SOURCE=legacy` 게이트 폐지 + `robotrader` DB 삭제로 도달
  불가가 됐다. (기록 테이블 `collection_reconciliation` 은 과거 이력이므로 유지.)

2026-09-29: 🔒 사장님 결정 — 분봉 저장 범위 = 「거래대금 top300 + 태쏘 shadow 후보
  (후보가 된 날부터 20거래일)」.
  ① 대상 = top300 ∪ 태쏘 후보(중복 제거 · top300 먼저). 태쏘 조회 실패 시 top300 만.
  ② 결손일 보충 — rt 후보는 15:50, stable 후보는 «다음 날» 16:25 에 써져 그날 EOD 분봉
     (≈15:46~15:49)을 놓친다. 그래서 창 안 태쏘 종목마다 [첫 후보일, 직전 거래일 P] 의 거래일 중
     분봉 0행인 날(거래정지일 제외)을 과거 분봉 API 로 받아 적재한다. 상한은 «종목-일» 하루 60
     (최근 날짜 먼저) — 못 채운 날·실패한 날은 여전히 0행이라 다음 EOD 가 자동으로 이어 받는다.
     과거 분봉 API 깊이: 코드·문서엔 「과거일자 분봉조회 가능」뿐 깊이 명시 없음. 선례 =
     scripts/backfill_minute_for_codes.py 로 0039P0 의 07-01~08-14(적재 시점 기준 30거래일 이상 전)를
     받았다 ⇒ 창(최대 19거래일 전)은 안쪽이다. 응답 0행·다른 날뿐인 날은 사유만 세고 적재하지 않으며
     창을 벗어날 때까지 상한 안에서 재시도한다(최근 날짜 우선이라 새 결손을 밀어내지 않는다).
  ③ 🔴 요청일과 «다른 날» 봉은 적재하지 않는다(당일 수집·보충 모두). 과거 분봉 API 는
     `input_hour` 로부터 뒤로 120봉이라 이른 시각·거래정지일엔 전날 봉이 섞이고,
     `get_full_trading_day_data` 는 데이터가 없으면 이전 날짜로 조용히 폴백한다.
     그 응답을 그대로 적재하면 replace_minute_day 가 «그 전날» 분봉을 DELETE 후
     부분 재적재한다(system_monitor 휴장일 게이트 주석의 「최대 위험」과 같은 기전).
     top300(당일 거래대금 순위)엔 거래정지 종목이 없지만 태쏘 후보엔 있을 수 있다.
  반환 dict 의 ``codes``(수집 대상 종목 수)·``rows``(당일 적재 행수) 의미는 그대로다.
"""
import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.minute_universe import select_tasso_codes, select_top_volume  # noqa: E402
from collectors.minute_writer import df_to_minute_rows, replace_minute_day  # noqa: E402
from api import kis_chart_api  # noqa: E402
from utils.korean_holidays import get_previous_trading_day  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 결손일 보충 상한(«종목-일» 단위)·호출 간격. 최악 60 × 4호출 × (≈0.12s + 0.1s) ≈ 53초.
# (09-29 실측: EOD 분봉 300종목 = 1,200호출 ≈ 2분 18초 ⇒ 호출당 ≈0.115초.)
TASSO_BACKFILL_MAX = 60
_BACKFILL_SLEEP = 0.1
# get_full_trading_day_data 와 같은 4구간의 끝 시각 — 호출마다 그 시각부터 뒤로 120봉.
_SEGMENT_ENDS = ("100000", "120000", "140000", "153000")

# 하루치 완전성 — 실측(09-29 top300) 첫 봉 09:00~09:02 · 마지막 봉 15:18~15:19 · 중앙 380봉.
# 첫 봉이 09:0x 가 아니거나 마지막 봉이 15:1x 미만이면 WARNING 만 남긴다(적재는 그대로).
_FULL_DAY_FIRST_BEFORE = "091000"
_FULL_DAY_LAST_FROM = "151000"

# 결손일 — 종목별 [첫 후보일, P] 안에서 일봉은 있고 분봉은 0행인 날 + 그날 일봉 거래량.
# 일봉 있는 날 = 그 종목의 거래일(휴장·상장 전 날은 자연히 빠진다). 거래량 0 = 거래정지 →
# 분봉이 «없는 게 정상»이라 호출하지 않는다.
# 🔑 minute_candles.trade_date 는 'YYYYMMDD', daily_prices.date 는 'YYYY-MM-DD' 텍스트다.
_MISSING_DAYS_SQL = """
SELECT d.stock_code, d.date, d.volume
FROM unnest(%(codes)s::text[], %(starts)s::text[]) AS c(code, start)
JOIN daily_prices d ON d.stock_code = c.code AND d.date BETWEEN c.start AND %(p_iso)s
WHERE NOT EXISTS (SELECT 1 FROM minute_candles m
                  WHERE m.stock_code = d.stock_code AND m.trade_date = replace(d.date, '-', ''))
"""


def _same_day(df, ymd: str):
    """요청일(ymd) 봉만 남긴다 — 폴백·교차일 응답을 한 번에 걸러낸다."""
    if df is None or len(df) == 0 or "date" not in df.columns:
        return pd.DataFrame()
    return df[df["date"].astype(str) == ymd]


def _warn_if_incomplete(code: str, ymd: str, rows: list) -> None:
    """적재하는 하루치의 첫·마지막 봉이 정상 범위 밖이면 WARNING 1줄(적재는 막지 않는다)."""
    times = [str(r["time"]).zfill(6) for r in rows]
    first, last = min(times), max(times)
    if first >= _FULL_DAY_FIRST_BEFORE or last < _FULL_DAY_LAST_FROM:
        logger.warning(f"[minute] {code} {ymd} 하루치 불완전 의심 — 첫 봉 {first} · 마지막 봉 {last}"
                       f" · {len(rows)}봉 (적재는 함)")


def _backfill_one(conn, code: str, ymd: str) -> tuple:
    """code 의 ymd 분봉을 과거 분봉 API(FHKST03010230)로 받아 적재 → (결과, 적재행).

    결과가 "ok" 가 아니면 아무것도 쓰지 않는다:
      api_fail   — 4구간 중 하나라도 응답 없음(부분 수신 적재 금지)
      empty      — 4구간 전부 빈 응답
      other_date — 봉은 왔는데 요청일 봉이 0(= API 쪽 폴백 · 교차일만)
      fewer      — 받은 행이 기존 행보다 적음(좋은 데이터를 부분 수신으로 지우지 않는다)
    """
    frames = []
    for end in _SEGMENT_ENDS:
        res = kis_chart_api.get_inquire_time_dailychartprice(
            div_code=kis_chart_api.get_div_code_for_stock(code), stock_code=code,
            input_date=ymd, input_hour=end, past_data_yn="Y")
        time.sleep(_BACKFILL_SLEEP)
        if res is None:
            return "api_fail", 0
        chart = res[1]
        if chart is not None and len(chart) > 0:
            frames.append(chart)
    if not frames:
        return "empty", 0
    same = _same_day(pd.concat(frames, ignore_index=True), ymd)
    if same.empty:
        return "other_date", 0
    # 구간 경계(10:00 등)와 겹치는 봉은 두 번 온다 — 봉의 자연키(datetime)로 dedup.
    same = same.sort_values("datetime").drop_duplicates(subset=["datetime"]).reset_index(drop=True)
    rows = df_to_minute_rows(code, same)
    if not rows:
        return "empty", 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM minute_candles WHERE stock_code=%s AND trade_date=%s",
                    (code, ymd))
        before = int(cur.fetchone()[0])
    if len(rows) < before:
        return "fewer", 0
    _warn_if_incomplete(code, ymd, rows)
    return "ok", replace_minute_day(conn, code, ymd, rows)


def _backfill_missing_days(conn, tasso: list, today, cap: int) -> dict:
    """창 안 태쏘 종목의 [첫 후보일, P] 결손일(분봉 0행 · 거래정지 제외)을 보충한다.

    상한 cap 은 «종목-일» 단위 · 최근 날짜 먼저(같은 날이면 최근 후보 종목 먼저). 넘친 날·실패한
    날은 적재하지 않으므로 0행 그대로 남고, 다음 EOD 의 같은 판정이 자동으로 다시 집는다.
    """
    p = get_previous_trading_day(datetime(today.year, today.month, today.day)).date()
    out = {"upto": p.strftime("%Y%m%d"), "target": 0, "codes": 0, "ok": 0, "rows": 0, "skip": {}}
    # 첫 후보일이 P 이후인 종목은 P 까지가 전부 «후보가 되기 전» 이라 대상이 아니다.
    eligible = [(c, first) for c, first in tasso if first <= p]
    if not eligible:
        return out
    rank = {c: i for i, (c, _) in enumerate(eligible)}
    with conn.cursor() as cur:
        cur.execute(_MISSING_DAYS_SQL, {"codes": [c for c, _ in eligible],
                                        "starts": [f.isoformat() for _, f in eligible],
                                        "p_iso": p.isoformat()})
        missing = cur.fetchall()
    conn.rollback()
    skip = Counter()
    targets = []
    for code, iso, vol in missing:
        if vol is not None and float(vol) == 0:
            skip["halt"] += 1  # 거래정지일 — 호출하지 않는다(정상을 실패로 세지 않는다)
            continue
        targets.append((str(iso).replace("-", ""), code))
    targets.sort(key=lambda t: (-int(t[0]), rank.get(t[1], len(rank))))
    out["target"] = len(targets)
    out["codes"] = len({c for _, c in targets})
    if len(targets) > cap:
        skip["cap"] = len(targets) - cap  # 다음 EOD 로 이월(여전히 0행이라 다시 집힌다)
        targets = targets[:cap]
    for ymd, code in targets:
        try:
            result, n = _backfill_one(conn, code, ymd)
        except Exception as e:  # noqa: BLE001 — 한 종목-일 실패가 나머지 보충을 막지 않게
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            logger.warning(f"[minute] 결손일 보충 오류 {code} {ymd}: {type(e).__name__}: {e}")
            result, n = "error", 0
        if result == "ok":
            out["ok"] += 1
            out["rows"] += n
        else:
            skip[result] += 1
            logger.debug(f"[minute] 결손일 보충 미적재 {code} {ymd}: {result}")
    out["skip"] = dict(skip)
    return out


def collect_minute(target_date: str = None, top_n: int = 300, limit: int = None) -> dict:
    ymd = (target_date or now_kst().strftime("%Y%m%d")).replace("-", "")
    today = datetime.strptime(ymd, "%Y%m%d").date()
    top = select_top_volume(top_n)
    total = 0
    date_rejected = 0
    with KisDbConnection.get_connection() as conn:
        window_from, tasso = select_tasso_codes(conn, today)
        top_set = set(top)
        extra = [c for c, _ in (tasso or []) if c not in top_set]
        codes = top + extra
        if limit:
            codes = codes[:limit]
        for code in codes:
            df = kis_chart_api.get_full_trading_day_data(code, ymd, "153000")
            if df is None or len(df) == 0:
                continue
            same = _same_day(df, ymd)
            if same.empty:
                date_rejected += 1
                logger.warning(f"[minute] {code} 요청일 {ymd} 봉 0 — 다른 날 응답이라 적재 안 함"
                               f"(폴백/거래정지 · {len(df)}봉)")
                continue
            rows = df_to_minute_rows(code, same)
            if rows:
                _warn_if_incomplete(code, ymd, rows)
                total += replace_minute_day(conn, code, rows[0]["trade_date"], rows)

        info = {"window": f"{window_from.isoformat() if window_from else '-'}~{today.isoformat()}",
                "codes": len(tasso or []), "extra": len(extra)}
        if tasso is None:
            info["error"] = "후보 조회 실패"
        else:
            try:
                cap = min(TASSO_BACKFILL_MAX, limit) if limit else TASSO_BACKFILL_MAX
                info["backfill"] = _backfill_missing_days(conn, tasso, today, cap)
            except Exception as e:  # noqa: BLE001 — 보충 실패가 당일 수집 결과를 지우면 안 된다
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
                logger.error(f"[minute] 결손일 보충 단계 실패: {type(e).__name__}: {e}")
                info["backfill"] = {"error": str(e)}
    bf = info.get("backfill", {})
    logger.info(
        f"[minute] 태쏘 후보 창 {info['window']} {info['codes']}종목(top300 밖 +{info['extra']})"
        f" · 결손일 보충(~{bf.get('upto', '-')}) 대상 {bf.get('target', 0)}종목-일({bf.get('codes', 0)}종목)"
        f" → 성공 {bf.get('ok', 0)}"
        f"({bf.get('rows', 0)}행) · 미적재 {bf.get('skip', {})}"
        + (f" · 🔴{info['error']}" if "error" in info else "")
        + (f" · 🔴보충 실패 {bf['error']}" if "error" in bf else "")
    )
    return {"codes": len(codes), "rows": total, "date_rejected": date_rejected, "tasso": info}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default=None)
    args = ap.parse_args()
    print(collect_minute(args.date, limit=args.limit))
