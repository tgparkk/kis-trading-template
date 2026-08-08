"""DART as-filed 재무제표 수집용 클라이언트 (연구 스크립트 — 라이브 의존 0).

🔴 이 파일은 `scripts/dart_mcap_common.py`(2026-08-06~07 시총 백필에서 실전 검증됨)
   에서 파생했다. 그 파일은 git untracked 라 의존하지 않고 옮겼다.
   실측 근거: `--interval 0.34`(3 req/s)로 20,241 호출 동안 연결리셋 0.

🔴 병렬 요청 금지. 2026-08-06 에 4스레드로 opendart 에 IP 차단당했고, 그 동안
   운영 수집기(collectors/corp_events_collector.py)도 같은 호스트라 동작 불가가 됐다.
🔴 빈 응답을 성공으로 처리하지 않는다. 모든 호출의 status 를 집계한다.
"""
import os
import sys
import time

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
# _HERE = <root>/scripts/discovery/fundamental_risk_filter → dirname 3번이 <root> 다.
# ⚠️ 원본 scripts/dart_mcap_common.py 는 scripts/ 바로 아래라 1번이면 됐다.
#    두 단계 깊어졌으므로 2번이 아니라 3번이다 — 틀리면 OUT_DIR 이
#    scripts/scratchpad 가 되고 .env 도 못 찾는다(조용히 실패한다).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
assert os.path.basename(PROJECT_ROOT) == "RoboTrader_template", PROJECT_ROOT
OUT_DIR = os.path.join(PROJECT_ROOT, "scratchpad", "fund_pit")

DART_BASE = "https://opendart.fss.or.kr/api"

REPRT_FY = "11011"  # 사업보고서(연간)


class DartBlocked(RuntimeError):
    """opendart 호스트가 IP 단위로 연결을 리셋(WAF 차단)해 진행 불가."""


class DartQuotaExceeded(RuntimeError):
    """DART 일일 사용한도 초과(status=020). 즉시 중단하고 체크포인트를 보존한다."""


class DartUnexpectedStatus(RuntimeError):
    """000(성공)·013(무자료)·000_EMPTY(응답은 왔으나 빈 내용) 외의 status.

    010/011/012(키 불량·미등록·IP 차단)·100/101(필드 오류)·HTTP_FAIL(재시도 소진)이
    여기 해당한다. 이런 상태를 조용히 013 처럼 «기록»해 버리면 키·IP 문제 하나가
    작업목록 전체를 「수집 완료, 무자료」로 태우고 체크포인트에 영구히 박힌다.
    즉시 올려서 중단시키고 체크포인트를 보존해야 한다.
    """

    def __init__(self, status, stock_code, bsns_year):
        self.status = status
        self.stock_code = stock_code
        self.bsns_year = bsns_year
        super().__init__(
            f"예상 밖의 DART status={status!r} (stock_code={stock_code}, bsns_year={bsns_year})"
        )


def _parse_dart_key_from_lines(lines) -> str:
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
    """kis_template 읽기 전용 접속. read-only 트랜잭션으로 쓰기 원천 차단."""
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


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


class DartClient:
    def __init__(self, key: str, min_interval: float = 0.34, session_factory=None, sleep_fn=None):
        # 🔴 session_factory 는 테스트 이음매다. 리셋 복구가 세션을 «새로 만들기»
        #    때문에, 이 이음매가 없으면 테스트가 주입한 가짜 세션이 복구 순간
        #    진짜 requests.Session 으로 갈아치워지고 **실제 DART 로 호출이 나간다**
        #    (2026-08-08 에 실측으로 확인됨 — status=010 응답을 받았다).
        # 🔴 sleep_fn 도 테스트 이음매다. 재시도 경로 테스트가 실제로 수십초를 잔다.
        #    기본값은 time.sleep (프로덕션 동작 동일).
        self.key = key
        self._session_factory = session_factory or requests.Session
        self.session = self._session_factory()
        self._sleep = sleep_fn or time.sleep
        self.min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        self.status_counts = {}
        self.http_errors = 0
        self.conn_resets = 0

    def _bump(self, status):
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def _throttle(self):
        if self.min_interval <= 0:
            return
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            self._sleep(self.min_interval - gap)
        self._last_call = time.time()

    def fnltt_all(self, corp_code: str, bsns_year: str, reprt_code: str, fs_div: str):
        """단일회사 전체 재무제표. 반환 (status, message, rows).

        rows 의 각 원소에 `rcept_no` 가 들어 있고 앞 8자리가 접수일(YYYYMMDD)이다.
        """
        url = f"{DART_BASE}/fnlttSinglAcntAll.json"
        params = {
            "crtfc_key": self.key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        }
        reset_streak = 0
        backoff = 2.0
        for _ in range(6):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=30)
                self.calls += 1
            except requests.exceptions.ConnectionError:
                self.conn_resets += 1
                reset_streak += 1
                if reset_streak >= 3:
                    raise DartBlocked("연결 리셋 3연속 — opendart IP 차단으로 판단")
                self.session.close()
                self.session = self._session_factory()  # 오염된 커넥션 풀 폐기
                self._sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            except Exception:
                self.http_errors += 1
                self._sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            reset_streak = 0
            if r.status_code != 200:
                self.http_errors += 1
                self._sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            try:
                js = r.json()
            except ValueError:
                self.http_errors += 1
                self._sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            status = js.get("status")
            self._bump(status)
            if status == "020":
                raise DartQuotaExceeded("DART 사용한도 초과(status=020) — 즉시 중단")
            if status == "800":
                self._sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            return status, js.get("message", ""), js.get("list") or []
        self._bump("HTTP_FAIL")
        return "HTTP_FAIL", "retries exhausted", []
