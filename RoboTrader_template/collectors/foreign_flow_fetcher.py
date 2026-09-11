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

# ── 실패 로그 억제 (2026-09-11) ──────────────────────────────────────────
# EOD 수집기는 유니버스 2,796 종목을 돈다. 실패 사유가 종목당 한 줄씩 나오면
# WARNING 2,796 줄이 되고, 그건 경보가 아니라 소음이다(읽는 사람이 본문을
# 스크롤로 넘겨버리면 경보는 «있는데 안 보인다»).
# ⇒ 사유 «종류»당 첫 1회만 WARNING, 이후는 DEBUG.
#   ⚠️ 억제는 「침묵」이 아니다 — 이후 줄도 DEBUG 로 남고, 첫 사유는
#      `get_first_fail_reason()` 으로 EOD 요약에 실려 나간다.
# 상태는 모듈 전역이고 프로세스 수명 동안 유지된다(EOD 는 1회성 실행이라 충분).
_FAIL_SEEN: dict[str, int] = {}
_FIRST_FAIL_REASON: str | None = None


def reset_fail_suppression() -> None:
    """억제 카운터·첫 사유 초기화 (수집 1회분 경계에서 호출)."""
    global _FIRST_FAIL_REASON
    _FAIL_SEEN.clear()
    _FIRST_FAIL_REASON = None


def get_first_fail_reason() -> str | None:
    """이번 수집에서 «처음» 만난 실패 사유 한 줄. 없으면 None.

    두 번째 이후 사유로 덮어쓰지 않는다 — 원인 추적은 처음이 중요하다
    (뒤 사유는 앞 사유의 결과일 때가 많다).
    """
    return _FIRST_FAIL_REASON


def _log_fail(kind: str, message: str) -> None:
    """사유 종류 `kind` 의 첫 줄만 WARNING, 이후는 DEBUG."""
    global _FIRST_FAIL_REASON
    seen = _FAIL_SEEN.get(kind, 0)
    _FAIL_SEEN[kind] = seen + 1
    if seen == 0:
        if _FIRST_FAIL_REASON is None:
            _FIRST_FAIL_REASON = message
        logger.warning("%s (이후 동일 사유는 DEBUG 로 억제)", message)
    else:
        logger.debug("%s (동일 사유 %d번째)", message, seen + 1)


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
            # allow_redirects=False: requests 기본값(True)은 302 를 따라가
            # 최종 200 으로 세탁한다 ⇒ 아래 status_code 가드를 못 지나가고
            # 「표를 못 찾음」으로 둔갑한다. 원인을 못 보는 게 아니라 **틀리게
            # 본다**. 리다이렉트 자체가 우리가 봐야 할 신호다.
            r = session.get(
                "https://finance.naver.com/item/frgn.naver",
                params={"code": code, "page": page},
                timeout=15,
                allow_redirects=False,
            )
            if r.status_code != 200:
                location = ""
                try:
                    loc = (r.headers or {}).get("Location")
                    if loc:
                        location = f" Location={loc}"
                except Exception:  # noqa: BLE001 — 목/비표준 응답 방어
                    location = ""
                _log_fail(
                    f"http_{r.status_code}",
                    f"[{code}] HTTP {r.status_code} (page={page}){location}",
                )
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
            # `Missing optional dependency 'lxml'` 같은 환경 결함도, 페이지
            # 구조 변경에 따른 파싱 실패도 여기로 온다. 종목마다 울리면
            # 2,796 줄이므로 같은 억제 규약을 쓴다.
            _log_fail(f"exc_{type(e).__name__}", f"[{code}] p{page}: {e}")
            break

    if not all_rows:
        return pd.DataFrame(columns=["date", "foreign_net_vol"])

    result = pd.concat(all_rows, ignore_index=True)
    result = result.drop_duplicates(subset=["date"]).sort_values("date")
    return result
