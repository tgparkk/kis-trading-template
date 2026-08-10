"""DART 시가총액 백필 검증용 공용 헬퍼 (연구 스크립트 — 라이브 의존 0).

A단계(매핑 확보 + 방식 검증) 전용. DB 쓰기 경로는 이 파일에 존재하지 않는다.
"""
import os
import re
import sys
import time

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_HERE)
OUT_DIR = os.path.join(PROJECT_ROOT, "scratchpad", "mcap_dart")

DART_BASE = "https://opendart.fss.or.kr/api"

# reprt_code → 라벨. 11013=1분기 11012=반기 11014=3분기 11011=사업보고서
REPRT_CODES = ("11013", "11012", "11014", "11011")
REPRT_LABEL = {
    "11013": "Q1",
    "11012": "H1",
    "11014": "Q3",
    "11011": "FY",
}


def _parse_dart_key_from_lines(lines) -> str:
    """정확히 'OPENDART_API_KEY' 키만 매칭 (collectors/corp_events_collector.py 방식 차용)."""
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == "OPENDART_API_KEY":
            return v.strip().strip('"').strip("'")
    return ""


def load_dart_key() -> str:
    key = (os.getenv("OPENDART_API_KEY") or "").strip()
    if key:
        return key
    env_path = os.path.join(PROJECT_ROOT, ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            return _parse_dart_key_from_lines(f)
    except OSError:
        return ""


def db_conn():
    """kis_template 읽기 전용 접속. autocommit + read-only 트랜잭션으로 쓰기 원천 차단."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        database="kis_template",
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


_NUM_RE = re.compile(r"^-?[\d,]+$")


def parse_num(v):
    """'5,969,782,550' → 5969782550. 파싱 실패는 None (0 으로 뭉개지 말 것)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    s = s.replace(",", "")
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return None


class DartBlocked(RuntimeError):
    """opendart 호스트가 IP 단위로 연결을 리셋(WAF 차단)해 진행 불가."""


class DartClient:
    """status 필드를 반드시 검사하는 최소 클라이언트.

    🔴 빈 응답을 성공으로 처리하지 않는다. 모든 호출의 status 를 집계한다.
    🔴 ConnectionReset(WAF IP 차단)은 '0건'이 아니라 '차단'으로 구분해 올린다.
       2026-08-06 실측: 4스레드 동시요청으로 opendart 전 호스트가 리셋 상태가 됐고
       루트 페이지(`https://opendart.fss.or.kr/`)조차 curl 로 reset 됐다.
       → 동시요청 금지. 순차 + 요청 간 간격 유지.
    """

    def __init__(self, key: str, min_interval: float = 1.0):
        self.key = key
        self.session = requests.Session()
        self.min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        self.status_counts = {}
        self.http_errors = 0
        self.conn_resets = 0
        self.block_waits = 0

    def _bump(self, status):
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def _throttle(self):
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.time()

    def probe(self) -> bool:
        """차단 해제 여부 확인. 루트 페이지 GET 성공이면 True."""
        try:
            r = self.session.get("https://opendart.fss.or.kr/", timeout=20)
            return r.status_code < 500
        except Exception:
            return False

    def stock_totqy(self, corp_code: str, bsns_year: str, reprt_code: str):
        """주식의 총수 현황. 반환: (status, message, list_of_rows).

        연결 리셋이 연속되면 DartBlocked 을 올린다 — 조용히 0건으로 넘기지 않는다.
        """
        url = f"{DART_BASE}/stockTotqySttus.json"
        params = {
            "crtfc_key": self.key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
        }
        reset_streak = 0
        backoff = 2.0
        for _ in range(6):
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
                backoff = min(backoff * 2, 30.0)
                continue
            except Exception:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            reset_streak = 0
            if r.status_code != 200:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            try:
                js = r.json()
            except ValueError:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            status = js.get("status")
            self._bump(status)
            if status == "020":  # 사용한도 초과
                raise RuntimeError("DART 사용한도 초과(status=020) — 중단")
            if status == "800":  # 시스템 점검
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            return status, js.get("message", ""), js.get("list") or []
        self._bump("HTTP_FAIL")
        return "HTTP_FAIL", "retries exhausted", []

    def wait_until_unblocked(self, max_wait_s: int = 5400, step: int = 60) -> bool:
        """차단이 풀릴 때까지 대기. 풀리면 True, 한도 초과면 False."""
        waited = 0
        while waited < max_wait_s:
            if self.probe():
                return True
            self.block_waits += 1
            time.sleep(step)
            waited += step
        return False


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)
