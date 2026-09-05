"""DART fnlttSinglAcntAll 최소 클라이언트 (운영 EOD 경로).

🔴 scripts/dart_mcap_common.py 를 import 하지 않는다 — 연구 트리다.
   corp_events_collector.py 와 같은 규약으로 최소 재구현한다.
🔴 동시 요청 금지. 2026-08-06 실측: 4스레드 동시요청으로 opendart 전 호스트가
   리셋 상태가 됐고 루트 페이지조차 curl 로 reset 됐다.
"""
import gzip
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"
_MAX_TRIES = 6
_BACKOFF_START = 2.0
_BACKOFF_CAP = 30.0


class DartQuotaExceeded(RuntimeError):
    """status=020 — 일일 사용한도 초과. 자정에 리셋된다(2026-08-07 실측)."""


class DartBlocked(RuntimeError):
    """연결 리셋 연속 — opendart 가 IP 단위로 차단한 상태."""


class DartFinancialFetcher:
    def __init__(self, key: str, min_interval: float = 0.34):
        # 0.34s = 3 req/s. B1 시총 수집 20,241호출 동안 연결 리셋 0 을 실측한 안전값.
        self.key = key
        self.session = requests.Session()
        self.min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        self.status_counts = {}
        self.http_errors = 0
        self.conn_resets = 0

    def _bump(self, status):
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def _throttle(self):
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.time()

    def fetch(self, corp_code: str, bsns_year: str, reprt_code: str, fs_div: str):
        """→ (status, payload). 020 은 예외, 013 은 정상 반환."""
        url = f"{DART_BASE}/fnlttSinglAcntAll.json"
        params = {"crtfc_key": self.key, "corp_code": corp_code,
                  "bsns_year": bsns_year, "reprt_code": reprt_code, "fs_div": fs_div}
        backoff = _BACKOFF_START
        reset_streak = 0
        for _ in range(_MAX_TRIES):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=25)
                self.calls += 1
            except requests.exceptions.ConnectionError:
                self.conn_resets += 1
                reset_streak += 1
                if reset_streak >= 3:
                    raise DartBlocked("연결 리셋 3연속 — opendart IP 차단으로 판단")
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

            reset_streak = 0
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
                raise DartQuotaExceeded("DART 일일 사용한도 초과(status=020)")
            if status == "800":  # 시스템 점검
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            return status, js

        self._bump("HTTP_FAIL")
        return "HTTP_FAIL", {}


def append_raw(path: str, payload: dict) -> int:
    """원본 응답을 gzip JSONL 에 append 하고 «줄 번호»(1-based)를 돌려준다.

    🔑 f2_raw 전례: DB 엔 7컬럼만 뽑혀 있었는데 원본엔 계정 2,461종이 있었다.
       원본을 남겼기 때문에 호출 0건으로 확장이 가능했다. 파싱은 틀릴 수 있다.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    if os.path.exists(path):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for _ in fh:
                n += 1
    with gzip.open(path, "at", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return n + 1
