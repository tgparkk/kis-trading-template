"""regime 게이트용 KOSPI/KOSDAQ 일봉 자동 갱신.

regime 게이트(RegimeGate)는 robotrader.daily_prices 의 stock_code='KOSPI'/'KOSDAQ'
일봉을 SSOT 로 읽는다. 이를 채우던 scripts/backfill_kospi_index.py 가 수동·미스케줄
이라 동결되면 게이트가 stale/fail-open 된다(2026-06-24 진단: KOSPI 05-29 동결,
KOSDAQ 부재). 본 모듈은 최근 일봉을 받아 daily_prices 에 멱등 upsert 한다.
EOD·장전 훅에서 매일 호출 → 자동 신선 유지.

게이트의 읽기 경로(price_repo.get_daily_prices)는 그대로 두고 데이터만 최신화하므로
게이트 로직 변경 위험이 없다.

2026-09-10: 소스를 KIS 업종 일봉으로 옮기고(롤백 = config.constants.INDEX_DAILY_SOURCE
  한 줄) 신선도 경보를 붙였다. 09-08~09 에 FDR 이 «옛 6봉»을 정상 반환해 이 경로도
  같이 멈췄는데 `%d행 갱신` 로그는 6을 찍었다 — 「N행 갱신」은 「오늘 것이 들어왔다」의
  증거가 아니다. 🔴 판정은 소스 스위치 «밖»이라 "fdr" 로 롤백해도 계속 돈다.
  spec: docs/superpowers/specs/2026-09-10-index-kis-freshness-design.md
"""
from __future__ import annotations

import time
from datetime import timedelta
from typing import Dict, Optional

from config.constants import (
    INDEX_DAILY_SOURCE, INDEX_DAILY_SOURCES, INDEX_FRESHNESS_ORACLE_CODES,
)
from utils.korean_time import now_kst
from utils.logger import setup_logger

logger = setup_logger(__name__)

# regime 게이트 stock_code → FDR 티커
INDEX_TICKERS: Dict[str, str] = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}
# regime 게이트 stock_code → KIS 업종코드 (0001 코스피 · 1001 코스닥)
INDEX_KIS_CODES: Dict[str, str] = {"KOSPI": "0001", "KOSDAQ": "1001"}
# 최근 며칠치를 받아 작은 공백도 함께 메운다(멱등 upsert).
_DEFAULT_LOOKBACK_DAYS = 10
# FDR 일시실패(EOD 15:48 데이터 lag·네트워크) 대비 재시도. 빈 df/예외면 재시도,
# 행>0 이면 즉시 성공. 3회 모두 실패면 현행처럼 0 으로 격리(2026-06-26).
_MAX_FDR_RETRIES = 3
_FDR_RETRY_SLEEP_SEC = 1.0
# 신선도 판정용 조회 창(달력일). 축 B 한계치(5일)보다 넉넉해야 「없다」와 「밀렸다」가 갈린다.
_FRESHNESS_LOOKBACK_DAYS = 40


def _fdr_to_daily_df(df):
    """FDR DataReader df(Date 인덱스·Open/High/Low/Close/Volume) →
    save_daily_prices_batch 가 읽는 date/open/high/low/close/volume 소문자 컬럼."""
    if df is None or getattr(df, "empty", True):
        return df
    out = df.reset_index()
    out.columns = [str(c).lower() for c in out.columns]
    if "date" not in out.columns:
        # reset_index 의 첫 컬럼(구 인덱스)을 date 로 사용
        out = out.rename(columns={out.columns[0]: "date"})
    return out


def _kis_to_daily_df(kis, name: str, start: str, end: str):
    """KIS 업종 일봉 → save_daily_prices_batch 가 읽는 소문자 컬럼 df.

    🔑 `collectors.index_writer` 는 «함수 안»에서 지연 import 한다 —
       collectors/eod_collection.py 가 이미 core.regime 를 import 하므로 모듈 수준
       상호 import 를 만들면 순환 위험이 있다.
    """
    import pandas as pd

    from collectors.index_writer import kis_df_to_index_rows

    df = kis.get_index_daily_chart(INDEX_KIS_CODES[name],
                                   start.replace("-", ""), end.replace("-", ""))
    if df is None:
        # `_url_fetch` 는 404 에 «예외 대신 None» 을 준다 — None 은 장애다(폴백 사유).
        raise RuntimeError(f"KIS 업종 일봉 응답 없음 ({name})")
    out = pd.DataFrame(kis_df_to_index_rows(name, df))
    if not out.empty:
        out = out.drop(columns=["index_code"])
    return out


def _max_date_from_repo(price_repo, code: str, days: int, cutoff_iso: Optional[str] = None):
    """(읽었나, 최신일 문자열|None). 「못 읽었다」와 「행이 없다」를 «구분»한다.

    구분하지 않으면 조회 실패가 곧 STALE 이 되어 경보가 자기 고장으로 울린다.

    cutoff_iso 를 주면 그 «이하» 날짜만 본다 — 오라클 종목에 필요하다. 장전 W1 훅이
    T 당일 07:40 에 넣는 «오늘 행»의 max 만 넘기면 cutoff 필터에서 전부 걸러져
    D_ref 가 none 이 된다(자르기는 «집계 전»에 해야 한다).
    """
    df = price_repo.get_daily_prices(code, days=days)
    if df is None:
        return False, None
    empty = getattr(df, "empty", None)
    if not isinstance(empty, bool):
        return False, None          # DataFrame 이 아니다 → 모른다
    if empty:
        return True, None
    try:
        vals = [str(v)[:10] for v in df["date"].tolist() if v is not None]
    except Exception:  # noqa: BLE001 — 스키마가 다르면 「모른다」
        return False, None
    if cutoff_iso is not None:
        vals = [v for v in vals if v <= cutoff_iso]
    return True, (max(vals) if vals else None)


def _warn_if_stale(price_repo, src: str, now) -> None:
    """daily_prices 의사티커 신선도 판정(설계 §4). 로그만 남기고 반환 dict 는 안 건드린다.

    🔴 반환 dict 에 키를 더하면 bot/system_monitor.py 의 `min(res.values()) > 0` 이 깨진다.
    """
    from collectors.index_writer import check_index_freshness, freshness_cutoff

    cutoff_iso = freshness_cutoff(now).strftime("%Y-%m-%d")
    index_max = {}
    for name in INDEX_TICKERS:
        known, mx = _max_date_from_repo(price_repo, name, _FRESHNESS_LOOKBACK_DAYS)
        if known:
            index_max[name] = mx
        else:
            logger.warning("[index-freshness] unknown table=daily_prices index=%s src=%s "
                           "— 일봉을 못 읽어 판정을 생략한다", name, src)
    oracle = []
    for code in INDEX_FRESHNESS_ORACLE_CODES:
        known, mx = _max_date_from_repo(price_repo, code, _FRESHNESS_LOOKBACK_DAYS, cutoff_iso)
        if known and mx:
            oracle.append(mx)
    check_index_freshness(index_max, oracle, now, "daily_prices", src, logger)


def refresh_regime_indices(price_repo, start: Optional[str] = None, fdr=None,
                           kis=None) -> Dict[str, int]:
    """KOSPI/KOSDAQ 일봉을 받아 daily_prices 에 멱등 upsert.

    Args:
        price_repo: PriceRepository (save_daily_prices_batch · get_daily_prices 보유).
        start: 조회 시작일 'YYYY-MM-DD'. None 이면 최근 _DEFAULT_LOOKBACK_DAYS.
        fdr: FinanceDataReader 모듈(테스트 주입용). None 이면 필요할 때 실제 import.
        kis: api.kis_market_api 모듈(테스트 주입용). None 이면 auth() 후 실제 import.

    Returns:
        {"KOSPI": n_rows, "KOSDAQ": n_rows}. 한 지수 실패는 0 으로 격리(예외 미전파).
        🔴 키를 «더하지 않는다» — system_monitor 가 min(res.values()) 로 판단한다.
    """
    now = now_kst()
    if start is None:
        start = (now.date() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    end = now.date().strftime("%Y-%m-%d")

    src = INDEX_DAILY_SOURCE if INDEX_DAILY_SOURCE in INDEX_DAILY_SOURCES else "fdr"
    kis_mod = kis
    if src == "kis" and kis_mod is None:
        try:
            import api.kis_market_api as _kis_api
            from api.kis_auth import auth
            if not auth():
                raise RuntimeError("KIS 인증 실패")
            kis_mod = _kis_api
        except Exception as e:  # noqa: BLE001 — 준비 실패는 폴백 사유
            logger.warning("[regime-index] KIS 준비 실패 → FDR 폴백: %s", e)
            kis_mod = None

    result: Dict[str, int] = {}
    used_src: Dict[str, str] = {}
    for name, ticker in INDEX_TICKERS.items():
        try:
            daily = None
            used = "fdr"
            if kis_mod is not None:
                try:
                    daily = _kis_to_daily_df(kis_mod, name, start, end)
                    used = "kis"    # 🔴 «빈 결과»여도 KIS 다 — 폴백 사유가 아니다(설계 §3)
                except Exception as e:  # noqa: BLE001 — 장애만 폴백
                    logger.warning("[regime-index] %s KIS 실패 → FDR 폴백: %s", name, e)
                    daily = None
            if used == "fdr":
                if fdr is None:
                    import FinanceDataReader as fdr  # noqa: N813
                for attempt in range(_MAX_FDR_RETRIES):
                    try:
                        df = fdr.DataReader(ticker, start)
                        daily = _fdr_to_daily_df(df)
                        if daily is not None and not getattr(daily, "empty", True):
                            break  # 행>0 성공 → 즉시 종료
                    except Exception as e:  # noqa: BLE001 - 일시실패는 재시도
                        daily = None
                        logger.warning(
                            "[regime-index] %s(%s) %d/%d차 시도 실패: %s",
                            name, ticker, attempt + 1, _MAX_FDR_RETRIES, e,
                        )
                    if attempt < _MAX_FDR_RETRIES - 1:
                        time.sleep(_FDR_RETRY_SLEEP_SEC)
            n = 0 if (daily is None or getattr(daily, "empty", True)) else len(daily)
            if n:
                price_repo.save_daily_prices_batch(name, daily)
            result[name] = n
            used_src[name] = used
            logger.info("[regime-index] %s(%s) %d행 갱신 src=%s", name, ticker, n, used)
        except Exception as e:  # noqa: BLE001 - 한 지수 실패가 다른 지수를 막지 않게 격리
            logger.warning("[regime-index] %s(%s) 갱신 실패: %s", name, ticker, e)
            result[name] = 0

    try:
        _warn_if_stale(price_repo, "+".join(sorted(set(used_src.values()))) or src, now)
    except Exception as e:  # noqa: BLE001 - 판정 실패가 갱신을 되돌리면 안 된다
        logger.warning("[index-freshness] daily_prices 판정 생략: %s", e)
    return result
