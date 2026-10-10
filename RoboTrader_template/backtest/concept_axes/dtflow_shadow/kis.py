"""KIS 조회 TR 4개 최소 클라이언트 — 라이브 `api/kis_auth.py`·`api/kis_market_api.py` 의 경로·헤더·파라미터를 복제
(원본 sha 는 guard 가 고정). 🔴 토큰 발급 0 — 파일을 읽기만 하고, 만료·없음·만료 응답이면 `TokenUnavailable`."""
from __future__ import annotations

import configparser
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from . import settings as S


class TokenUnavailable(Exception):
    pass


def read_token(path: Path, now: datetime, min_left_s: int = S.TOKEN_MIN_LEFT_S) -> str:
    p = Path(path)
    if not p.exists():
        raise TokenUnavailable("토큰 파일 없음")
    tok, valid = None, None
    for line in p.read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition(":")
        if k.strip() == "token":
            tok = v.strip()
        elif k.strip() == "valid-date":
            try:
                valid = datetime.strptime(v.strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                valid = None
    if not tok or valid is None:
        raise TokenUnavailable("토큰 파일 형식 이상")
    if (valid - now).total_seconds() < min_left_s:
        raise TokenUnavailable("토큰 곧 만료")
    return tok


def read_kis_conf(path: Path) -> Dict[str, str]:
    cp = configparser.ConfigParser()
    cp.read(str(path), encoding="utf-8")
    sec = cp["KIS"]
    get = lambda k: str(sec.get(k, "")).strip().strip('"')   # noqa: E731
    return {"base_url": get("KIS_BASE_URL"), "appkey": get("KIS_APP_KEY"), "appsecret": get("KIS_APP_SECRET")}


def params_for(kind: str, code: str, D: date, T: date) -> Dict[str, str]:
    base = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    if kind == "investor":
        return base
    if kind == "program":
        return {**base, "FID_INPUT_DATE_1": T.strftime("%Y%m%d")}
    if kind == "short":
        return {**base, "FID_INPUT_DATE_1": (D - timedelta(days=S.SHORT_SPAN_DAYS)).strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": D.strftime("%Y%m%d")}
    if kind == "credit":
        return {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20476", "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": T.strftime("%Y%m%d")}
    raise ValueError(kind)


def _expired(body: Dict[str, Any]) -> bool:
    return body.get("msg_cd") == "EGW00123" or "기간이 만료된 token" in str(body.get("msg1", ""))


def _too_fast(body: Dict[str, Any]) -> bool:
    return body.get("msg_cd") == "EGW00201" or "초당 거래건수를 초과" in str(body.get("msg1", ""))


class Client:
    def __init__(self, base_url: str, token: str, appkey: str, appsecret: str, session=None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        if session is None:
            import requests
            session = requests.Session()
        self.base_url, self.token, self.appkey, self.appsecret = base_url.rstrip("/"), token, appkey, appsecret
        self.session, self.sleep, self.clock = session, sleep, clock
        self._last = -1e9
        self.calls = 0

    def _headers(self, tr_id: str) -> Dict[str, str]:
        return {"Content-Type": "application/json", "Accept": "text/plain", "charset": "UTF-8",
                "User-Agent": "StockBot/1.0", "authorization": f"Bearer {self.token}", "appkey": self.appkey,
                "appsecret": self.appsecret, "tr_id": tr_id, "custtype": "P", "tr_cont": ""}

    def get(self, kind: str, params: Dict[str, str]) -> Tuple[dict, str]:
        tr_id, path = S.TRS[kind]
        body: Dict[str, Any] = {}
        for attempt in range(S.RETRY_MAX + 1):
            wait = S.CALL_INTERVAL_S - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = self.clock()
            r = self.session.get(self.base_url + path, headers=self._headers(tr_id), params=params,
                                 timeout=S.HTTP_TIMEOUT)
            self.calls += 1
            try:
                body = r.json()
            except ValueError:
                body = {"rt_cd": "X", "msg_cd": f"HTTP{r.status_code}", "msg1": "JSON 아님"}
            if _expired(body):
                raise TokenUnavailable("만료 응답(EGW00123)")
            if _too_fast(body) and attempt < S.RETRY_MAX:
                self.sleep(S.RETRY_BASE_S * (2 ** attempt))
                continue
            break
        return body, datetime.now().isoformat(timespec="milliseconds")
