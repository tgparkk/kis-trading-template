# collectors/dart_company_fetcher.py
"""DART company.json 최소 클라이언트 (운영 EOD 경로).

🔴 DartFinancialFetcher(collectors/dart_financial_fetcher.py) 의 «미러»다 —
   min_interval=0.34(3 req/s · B1 20,241호출 동안 리셋 0 실측) · 020 은 예외로 올리고
   800(점검)·HTTP 실패는 백오프 재시도 · 전송 실패 3연속이면 DartBlocked.
🔴 예외 클래스는 재무 fetcher 것을 그대로 import 한다. 같은 호스트의 같은 상태코드에
   예외가 두 벌 있으면 호출측이 한쪽만 잡아 «차단»이 «성공»으로 흘러간다.
🔴 동시 요청 금지(2026-08-06 실측: 4스레드로 opendart 전 호스트가 리셋 상태).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from collectors.dart_financial_fetcher import DartBlocked, DartQuotaExceeded  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"
_MAX_TRIES = 6
_BACKOFF_START = 2.0
_BACKOFF_CAP = 30.0


class DartCompanyFetcher:
    def __init__(self, key: str, min_interval: float = 0.34):
        self.key = key
        self.session = requests.Session()
        self.min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        self.status_counts = {}
        self.http_errors = 0
        self.conn_resets = 0
        self.reset_streak = 0

    def _bump(self, status):
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def _throttle(self):
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.time()

    def fetch(self, corp_code: str):
        """→ (status, payload). 020 은 예외, 013(무자료)은 정상 반환."""
        url = "%s/company.json" % DART_BASE
        params = {"crtfc_key": self.key, "corp_code": corp_code}
        backoff = _BACKOFF_START
        for _ in range(_MAX_TRIES):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=25)
                self.calls += 1
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                self.conn_resets += 1
                self.reset_streak += 1
                if self.reset_streak >= 3:
                    logger.error("DartBlocked: 전송 실패 3연속 (corp_code=%s)", corp_code)
                    raise DartBlocked("전송 실패 3연속 - opendart IP 차단으로 판단")
                self.session.close()
                self.session = requests.Session()
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            except Exception:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue

            self.reset_streak = 0
            if r.status_code != 200:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            try:
                js = r.json()
            except ValueError:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue

            status = js.get("status")
            self._bump(status)
            if status == "020":
                logger.error("DartQuotaExceeded: 일일사용한도초과 (corp_code=%s)", corp_code)
                raise DartQuotaExceeded("DART 일일 사용한도 초과(status=020)")
            if status == "800":       # 시스템 점검
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            if status not in ("000", "013"):
                logger.warning("Unexpected DART status=%s (corp_code=%s, message=%s)",
                               status, corp_code, js.get("message", ""))
            return status, js

        self._bump("HTTP_FAIL")
        logger.warning("HTTP_FAIL: retry loop exhausted (corp_code=%s, attempts=%d)",
                       corp_code, _MAX_TRIES)
        return "HTTP_FAIL", {}


def append_company_raw(path: str, payload: dict) -> int:
    """원본 응답을 «비압축» JSONL 에 append 하고 1-based 줄 번호를 돌려준다.

    🔑 f2_raw 전례 — 원본을 남겨 뒀기 때문에 호출 0건으로 확장이 가능했다.
       여기 원본은 §5-4 `--regen-map` 이 ksic_code·ksic_source·ksic_checked_at 을
       되살리는 «유일한» 원료다(캐시 CSV 엔 코드 열이 없다).
    """
    abspath = os.path.abspath(path)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    n = 0
    if os.path.exists(abspath):
        with open(abspath, encoding="utf-8") as fh:
            for _ in fh:
                n += 1
    with open(abspath, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return n + 1
