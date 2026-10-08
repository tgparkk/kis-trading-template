"""실전 주문 접수·취소 1회성 시험 (체크리스트 §4-B · 2026-10-06 장전).

근거 문서
- docs/checklist_2026-10-05_real_daytrading_holiday_verification.md §4-B (사장님 10-02 확정)
- docs/audit_2026-10-04_real_daytrading_flow.md ① NEW-B1 (취소가 성공해도 cancel_order 가 «실패»를 돌려준다)

하는 일
- 체결 불가 가격(기준가(전일종가) x 0.75 를 호가단위로 «내림») 1주 지정가 매수
  → 미체결 조회 → cancel_order → 재조회 → (남으면 1회만 더 취소 → 재조회) → 당일 주문조회.
- 판정은 cancel_order 의 success 가 아니라 «재조회 결과 + KIS 원응답(rt_cd)» 으로 한다.
  NEW-B1 = «1차» 취소 TR 원응답 기준 3분류(재현 / 비재현 / 판정불가).
- 주문이 미체결 목록에 한 번도 안 보였거나(= cancel_order 가 취소를 안 보냄) 당일조회 원주문이 «잔량>0 ∧ 취소 흔적
  없음» 이면 CRITICAL + exit 4. 예외·Ctrl+C 중단 시 주문번호를 알면 그 주문 전량 취소를 1회 시도한다.

기본 = dry-run: 인증 → 현재가/기준가/하한가 → 주문가 계산 → 미체결 조회 → 가드 평가 → 계획 출력.
  주문·취소 TR(TTTC0012U·TTTC0011U·TTTC0013U)은 호출하지 않는다 — 코드 경로가 없고, HTTP 게이트도 막는다.
--live 일 때만 주문 1건. 가드가 하나라도 실패하면 주문 없이 종료. cwd 가 라이브 트리 아래면 무조건 종료.

봇 코드 파일은 수정하지 않는다. 래핑은 이 프로세스 안에서만 한다.
- api.kis_auth 모듈의 전역 이름 `requests` 를 HttpGate 로 교체 → KIS HTTP 호출 전부를 원응답째 기록(마스킹)하고
  POST 는 허용 목록(토큰 · live 의 hashkey · 계획과 «정확히» 같은 매수 1건 · 이 주문의 전량 취소)만 통과시킨다.
  KIS 외 호스트는 텔레그램 POST(장애 알림)만 · requests.Session 등 다른 경로는 차단.
- utils.logger 의 공유 핸들러를 probe 로그 파일로 교체 → 봇 로거 출력도 같은 파일로 간다(cwd 의 logs/ 미사용).

출력: 콘솔 + D:/tmp/real_cancel_probe_out/probe_YYYYMMDD_HHMMSS.log (원응답 JSON 은 파일에만 · 계좌·키·토큰 마스킹)

실행 (cwd = 워크트리 RoboTrader_template · bash):
  PYTHONPATH="$PWD:$PWD/.." PYTHONIOENCODING=utf-8 \
    D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe \
    scripts/real_order_cancel_probe.py --code 005930            # dry-run
  ... scripts/real_order_cancel_probe.py --code 005930 --live     # 10-06 08:30~08:50 KST 에만 통과
  (선택) --expect-base <원>: dry-run 으로 본 기준가를 넣으면 live 때 조회 기준가가 그 값이어야 진행
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import sys
import time as _time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# 상수 — 인자로 바꿀 수 없는 값들
# ---------------------------------------------------------------------------
DEFAULT_INSTANCE_DIR = "D:/GIT/kis-trading-template/RoboTrader_template/instances/daytrading"
EXPECTED_INSTANCE_ID = "daytrading"
DEFAULT_OUT_DIR = "D:/tmp/real_cancel_probe_out"
LIVE_TREE_ROOT = "D:/GIT/kis-trading-template"   # 이 아래에서 실행 금지(토큰 캐시·로그가 라이브 트리에 생김)

QTY = 1                       # 수량 고정(인자 없음)
PRICE_RATIO = 0.75            # 주문가 = 기준가 x 0.75 → 호가 내림
MAX_PRICE_RATIO = 0.80        # 가드: 주문가 ≤ 기준가 x 0.80 · 현재가 x 0.80
WINDOW_START = dtime(8, 30, 0)
WINDOW_END = dtime(8, 50, 0)  # 취소 재시도 최악 2분+ · 09:00 시가 결정 전 여유
WAIT_SEC = 2.0
EXTERNAL_POST_HOSTS = {"api.telegram.org"}   # KIS 외 허용 = kis_auth 장애 알림 POST 뿐

TR_BUY = "TTTC0012U"
TR_SELL = "TTTC0011U"
TR_CANCEL = "TTTC0013U"
PATH_TOKEN = "/oauth2/tokenP"
PATH_HASHKEY = "/uapi/hashkey"
PATH_ORDER_CASH = "/uapi/domestic-stock/v1/trading/order-cash"
PATH_ORDER_RVSECNCL = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
ORDER_PATHS = (PATH_ORDER_CASH, PATH_ORDER_RVSECNCL)

# 응답·요청에서 값을 지울 키(소문자 비교). 계좌·키·토큰·IP·연락처.
MASK_KEYS = {
    "cano", "acnt_prdt_cd", "access_token", "appkey", "appsecret", "authorization",
    "hash", "hashkey", "approval_key", "token", "inqr_ip_addr", "ctac_tlno", "ordr_empno",
    "hts_id", "usr_id",
}

DAILY_FIELDS = (
    "ord_dt", "ord_tmd", "odno", "orgn_odno", "sll_buy_dvsn_cd", "ord_dvsn_name", "pdno",
    "ord_qty", "ord_unpr", "tot_ccld_qty", "avg_prvs", "cncl_yn", "cncl_cfrm_qty", "rmn_qty",
    "rjct_qty", "excg_dvsn_cd",
)
PENDING_FIELDS = ("odno", "orgn_odno", "pdno", "sll_buy_dvsn_cd", "ord_qty", "ord_unpr", "psbl_qty", "ord_tmd")

Guard = Tuple[str, bool, str]   # (이름, 통과, 설명)


# ---------------------------------------------------------------------------
# 순수 함수 (KIS 호출 없음 · 단위 테스트 대상)
# ---------------------------------------------------------------------------
def tick_size(price: float) -> int:
    """봇과 같은 호가표(framework.utils.get_tick_size). 봇 get_order_cash 의 validate_tick 이 같은 표를 쓰므로
    이 표로 맞춘 가격은 봇이 «보정»(반올림 = 위로 갈 수 있음)하지 않는다."""
    from framework.utils import get_tick_size
    return get_tick_size(price)


def floor_to_tick(price: float) -> int:
    """호가단위로 내림(체결 불가 방향). 0 이하는 0."""
    if price <= 0:
        return 0
    t = tick_size(price)
    return int(math.floor(round(price / t, 6))) * t


def compute_order_price(base_price: float) -> int:
    return floor_to_tick(base_price * PRICE_RATIO)


def check_time_window(now: datetime) -> Guard:
    t = now.time()
    ok = WINDOW_START <= t <= WINDOW_END
    return (f"시간창 {WINDOW_START:%H:%M:%S}~{WINDOW_END:%H:%M:%S} KST", ok, f"지금 {now:%Y-%m-%d %H:%M:%S}")


def check_cwd(cwd: Path) -> Guard:
    """라이브 트리 아래에서 돌면 토큰 캐시(cwd 기준)·로그가 라이브 봇 것을 덮을 수 있다 → 거부."""
    root = os.path.normcase(os.path.normpath(LIVE_TREE_ROOT))
    c = os.path.normcase(os.path.normpath(str(cwd)))
    inside = c == root or c.startswith(root + os.sep)
    return ("실행 위치 = 라이브 트리 밖", not inside, f"cwd={cwd}")


def check_expect_base(expect: Optional[int], base: float) -> Optional[Guard]:
    """--expect-base 가 주어졌을 때만 가드(조회 기준가 == 기대값). 없으면 None."""
    if expect is None:
        return None
    return ("기준가 = --expect-base", base > 0 and int(round(base)) == int(expect),
            f"조회 {base:,.0f} vs 기대 {int(expect):,}")


def judge_new_b1(c1: Optional[Dict[str, Any]], c1_raw: Optional[Dict[str, Any]],
                 remain: Optional[bool]) -> Tuple[str, str]:
    """NEW-B1 판정 — «1차» cancel_order 반환 + 그 호출 중 나간 취소 TR 원응답 + 최종 잔존으로 3분류."""
    if not c1:
        return "판정불가", "취소 시도 없음"
    if not c1_raw:
        return "판정불가", "1차 cancel_order 가 취소 TR 을 보내지 않음(목록에서 못 찾음·조회 실패 등)"
    rt = c1_raw.get("rt_cd")
    if rt != "0":
        return "판정불가", f"1차 취소 TR 을 KIS 가 거부/무응답(rt_cd={rt})"
    if c1.get("success") is True:
        return "비재현", "원응답 rt_cd 0 + success True"
    if c1.get("message") == "Cancel failed: Unknown error" and remain is False:
        return "재현", "원응답 rt_cd 0 인데 success False·'Unknown error' · 최종 재조회 0건"
    return "판정불가", f"rt_cd 0 · success={c1.get('success')} · message={c1.get('message')!r} · 최종 잔존={remain}"


def check_trading_day(market_status: str, holiday: bool, kis_closed: Optional[bool]) -> Guard:
    """봇과 같은 경로(MarketHours.get_market_status · korean_holidays.is_holiday)의 결과를 받아 판정.
    kis_closed = 라이브 트리 holiday_kis_cache.json(KIS chk-holiday 동기화본)에 오늘이 휴장으로 있는지
    (None = 캐시 없음)."""
    ok = market_status == "pre_market" and not holiday and kis_closed is not True
    return ("거래일·장전(pre_market)", ok,
            f"market_status={market_status} · is_holiday={holiday} · KIS캐시휴장={kis_closed}")


def check_price_guards(price: int, base_price: float, cur_price: float, lower_limit: float) -> List[Guard]:
    g: List[Guard] = []
    g.append(("기준가(전일종가) > 0", base_price > 0, f"기준가 {base_price:,.0f}"))
    g.append(("현재가 > 0", cur_price > 0, f"현재가 {cur_price:,.0f}"))
    g.append(("하한가 > 0", lower_limit > 0, f"하한가 {lower_limit:,.0f}"))
    g.append(("주문가 ≤ 기준가 x 0.80", price > 0 and price <= base_price * MAX_PRICE_RATIO,
              f"{price:,} ≤ {base_price * MAX_PRICE_RATIO:,.1f}"))
    g.append(("주문가 ≤ 현재가 x 0.80", price > 0 and cur_price > 0 and price <= cur_price * MAX_PRICE_RATIO,
              f"{price:,} ≤ {cur_price * MAX_PRICE_RATIO:,.1f}"))
    g.append(("주문가 ≥ 하한가", price > 0 and lower_limit > 0 and price >= lower_limit,
              f"{price:,} ≥ {lower_limit:,.0f}"))
    g.append(("호가단위 정렬", price > 0 and price % tick_size(price) == 0,
              f"{price:,} % {tick_size(price) if price > 0 else 0}"))
    return g


def check_no_pending(pending: Optional[list]) -> Guard:
    if pending is None:
        return ("시작 시 미체결 0건", False, "미체결 조회 실패(None) — 확인 못 한 상태로는 주문하지 않는다")
    if len(pending) > 0:
        return ("시작 시 미체결 0건", False, f"미체결 {len(pending)}건 — 남의 주문을 건드리지 않기 위해 거부")
    return ("시작 시 미체결 0건", True, "0건")


def check_instance(instance_id: str, key_ini_exists: bool, base_url: str) -> List[Guard]:
    """dry-run 포함 «KIS 호출 전» 필수 조건(잘못된 계좌 키로 호출하지 않기 위해)."""
    return [
        ("인스턴스 = daytrading", instance_id == EXPECTED_INSTANCE_ID, f"INSTANCE_ID={instance_id}"),
        ("인스턴스 key.ini 존재", key_ini_exists, "KIS_INSTANCE_DIR/key.ini"),
        ("실전 도메인(openapivts 아님)", bool(base_url) and "openapivts" not in base_url, "KIS_BASE_URL(값 비공개)"),
    ]


def check_real_mode(load_ok: bool, paper_trading: Any) -> List[Guard]:
    return [
        ("trading_config.json 로드 성공", bool(load_ok), f"LAST_TRADING_CONFIG_LOAD_OK={load_ok}"),
        ("paper_trading = false (실전 설정)", paper_trading is False, f"paper_trading={paper_trading}"),
    ]


def normalize_odno(x: Any) -> str:
    return str(x if x is not None else "").strip().lstrip("0")


def find_rows(rows: Optional[List[dict]], odno: str, keys: Tuple[str, ...] = ("odno",)) -> List[dict]:
    target = normalize_odno(odno)
    if not target or not rows:
        return []
    return [r for r in rows if any(normalize_odno(r.get(k)) == target for k in keys)]


class GateState:
    """HTTP 게이트의 허용 상태. live 가 아니면 POST 주문 경로는 전부 막힌다."""

    def __init__(self, live: bool):
        self.live = live
        self.planned: Optional[Dict[str, str]] = None   # PDNO · ORD_QTY · ORD_UNPR · ORD_DVSN
        self.target_odno: str = ""
        self.buy_calls = 0


def gate_decision(state: GateState, method: str, path: str, tr_id: str, params: Dict[str, Any]) -> Tuple[bool, str]:
    """KIS 도메인 HTTP 1건의 허용 여부(상태 변경 없음 — 매수 횟수 증가는 호출자가 한다)."""
    if method.upper() not in ("GET", "POST"):
        return False, f"허용 밖 메서드 차단({method})"
    if method.upper() == "GET":
        return True, "읽기(GET)"
    if path == PATH_TOKEN:
        return True, "토큰 발급"
    if not state.live:
        return False, "dry-run: POST 차단"
    if path == PATH_HASHKEY:
        return True, "hashkey(live)"
    if path == PATH_ORDER_CASH:
        if tr_id != TR_BUY:
            return False, f"매수 외 주문 TR 차단({tr_id})"
        if state.planned is None:
            return False, "계획 미설정 상태의 매수 차단"
        if state.buy_calls >= 1:
            return False, "매수는 프로세스당 1회"
        for k, v in state.planned.items():
            if str(params.get(k, "")) != str(v):
                return False, f"계획과 다른 매수 차단({k}={params.get(k)!r} ≠ {v!r})"
        return True, "계획된 매수 1건"
    if path == PATH_ORDER_RVSECNCL:
        if tr_id != TR_CANCEL:
            return False, f"취소 외 TR 차단({tr_id})"
        if not state.target_odno:
            return False, "대상 주문번호 미설정"
        if str(params.get("RVSE_CNCL_DVSN_CD", "")) != "02":
            return False, "정정 차단(취소 02 만)"
        if str(params.get("QTY_ALL_ORD_YN", "")) != "Y":
            return False, "잔량전부(Y) 아닌 취소 차단"
        if normalize_odno(params.get("ORGN_ODNO")) != normalize_odno(state.target_odno):
            return False, "이 시험 주문이 아닌 주문의 취소 차단"
        return True, "이 시험 주문 전량 취소"
    return False, f"허용 목록 밖 POST 차단({path})"


class Masker:
    """키 이름 + 비밀 문자열(앱키·시크릿·계좌·HTS ID·토큰) 치환."""

    def __init__(self) -> None:
        self._secrets: List[str] = []

    def add(self, *values: Any) -> None:
        for v in values:
            s = str(v or "").strip().strip('"')
            if len(s) >= 4 and s not in self._secrets:
                self._secrets.append(s)
        self._secrets.sort(key=len, reverse=True)

    def text(self, s: str) -> str:
        for sec in self._secrets:
            if sec in s:
                s = s.replace(sec, "***")
        return s

    def obj(self, o: Any) -> Any:
        if isinstance(o, dict):
            return {k: ("***" if str(k).lower() in MASK_KEYS and v not in ("", None) else self.obj(v))
                    for k, v in o.items()}
        if isinstance(o, list):
            return [self.obj(x) for x in o]
        if isinstance(o, str):
            return self.text(o)
        return o


# ---------------------------------------------------------------------------
# 런타임 (KIS 호출)
# ---------------------------------------------------------------------------
class _MaskFilter(logging.Filter):
    def __init__(self, masker: Masker):
        super().__init__()
        self._m = masker

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._m.text(record.getMessage())
        record.args = ()
        # log.exception 의 traceback(마지막 줄 = 예외 메시지 포함)도 마스킹 — 포맷된 문자열로 바꿔 끼운다.
        if record.exc_info:
            record.exc_text = self._m.text(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self._m.text(record.exc_text)
        if record.stack_info:
            record.stack_info = self._m.text(record.stack_info)
        return True


class HttpGate:
    """api.kis_auth 모듈 안의 `requests` 자리에 들어가는 프록시. get/post 만 가로채고 나머지는 원본에 위임."""

    def __init__(self, real_requests: Any, state: GateState, kis_host: str,
                 log: logging.Logger, raw: logging.Logger, masker: Masker):
        self._real = real_requests
        self._state = state
        self._kis_host = kis_host
        self._log = log
        self._raw = raw
        self._m = masker
        self.calls: List[Dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        # 허용 = get·post·request(아래 정의) + 예외 클래스. Session·put·delete 등 다른 경로는 차단.
        if name == "exceptions":
            return self._real.exceptions
        raise AttributeError(f"[probe gate] requests.{name} 경로 차단(허용: get·post·request·exceptions)")

    def get(self, url: str, **kw: Any) -> Any:
        return self._call("GET", url, kw)

    def post(self, url: str, **kw: Any) -> Any:
        return self._call("POST", url, kw)

    def request(self, method: str, url: str, **kw: Any) -> Any:
        return self._call(str(method).upper(), url, kw)

    def _call(self, method: str, url: str, kw: Dict[str, Any]) -> Any:
        u = urlparse(url)
        if u.netloc != self._kis_host:            # URL 에 토큰이 있을 수 있으므로 host 만 기록
            if method == "POST" and u.netloc in EXTERNAL_POST_HOSTS:
                self._log.info(f"[HTTP] 외부 호출 {method} host={u.netloc} (허용 · 기록 생략)")
                return self._real.post(url, **kw)
            self._log.warning(f"[HTTP] 🛑 외부 호스트 차단 {method} host={u.netloc}")
            return _blocked_response(url, f"외부 호스트 차단({u.netloc})")
        headers = kw.get("headers") or {}
        tr_id = str(headers.get("tr_id", ""))
        if method == "GET":
            params = dict(kw.get("params") or {})
        else:
            try:
                params = json.loads(kw.get("data") or "{}")
            except (TypeError, ValueError):
                params = {}
        seq = len(self.calls) + 1
        rec: Dict[str, Any] = {"seq": seq, "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                               "method": method, "path": u.path, "tr_id": tr_id,
                               "tr_cont_req": headers.get("tr_cont", ""), "params": self._m.obj(params)}
        ok, reason = gate_decision(self._state, method, u.path, tr_id, params)
        if not ok:
            rec.update({"blocked": True, "reason": reason})
            self.calls.append(rec)
            self._log.warning(f"[HTTP#{seq}] 🛑 차단 {method} {u.path} tr_id={tr_id} — {reason}")
            self._raw.info("RAW_HTTP " + json.dumps(rec, ensure_ascii=False))
            return _blocked_response(url, reason)
        if u.path == PATH_ORDER_CASH:
            self._state.buy_calls += 1
        rec.update({"blocked": False, "reason": reason})
        try:
            resp = self._real.get(url, **kw) if method == "GET" else self._real.post(url, **kw)
        except Exception as e:  # 기록 후 원래 흐름(봇 재시도·오류 처리)으로 돌려보낸다
            rec["exception"] = f"{type(e).__name__}: {e}"
            self.calls.append(rec)
            self._log.error(f"[HTTP#{seq}] {method} {u.path} tr_id={tr_id} 예외 {type(e).__name__}")
            self._raw.info("RAW_HTTP " + self._m.text(json.dumps(rec, ensure_ascii=False)))
            raise
        rec["status"] = resp.status_code
        rec["tr_cont_resp"] = resp.headers.get("tr_cont", "")
        try:
            body = resp.json()
        except ValueError:
            body = {"_text": resp.text[:500]}
        rec["body"] = self._m.obj(body)
        if isinstance(body, dict):
            rec["rt_cd"], rec["msg_cd"], rec["msg1"] = body.get("rt_cd"), body.get("msg_cd"), body.get("msg1")
        self.calls.append(rec)
        # hashkey 호출엔 주문 tr_id 헤더가 붙어 온다 → 경로로 표기
        label = "hashkey" if u.path == PATH_HASHKEY else (tr_id or u.path)
        self._log.info(f"[HTTP#{seq}] {method} {label} status={resp.status_code} "
                       f"rt_cd={rec.get('rt_cd')} msg_cd={rec.get('msg_cd')} msg1={rec.get('msg1')}")
        self._raw.info("RAW_HTTP " + self._m.text(json.dumps(rec, ensure_ascii=False, default=str)))
        return resp

    def last(self, tr_id: str, since: int = 0) -> Optional[Dict[str, Any]]:
        """since 번째 기록 이후(= 그 시점 len(calls) 이후) 실제로 보낸 tr_id 호출 중 마지막."""
        for c in reversed(self.calls[since:]):
            if c.get("tr_id") == tr_id and not c.get("blocked") and c.get("path") != PATH_HASHKEY:
                return c
        return None


def _blocked_response(url: str, reason: str) -> Any:
    import requests
    from requests.structures import CaseInsensitiveDict
    r = requests.models.Response()
    r.status_code = 200
    r.url = url
    r.encoding = "utf-8"
    r.headers = CaseInsensitiveDict({"content-type": "application/json", "tr_cont": ""})
    r._content = json.dumps({"rt_cd": "1", "msg_cd": "PROBE_BLOCKED", "msg1": reason},
                            ensure_ascii=False).encode("utf-8")
    return r


def _setup_logging(log_path: Path, masker: Masker) -> Tuple[logging.Logger, logging.Logger]:
    fmt = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    flt = _MaskFilter(masker)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    ch = logging.StreamHandler(sys.stdout)
    for h in (fh, ch):
        h.setFormatter(fmt)
        h.addFilter(flt)
    # 봇 로거(utils.logger 싱글톤)가 cwd 의 logs/<id>/ 대신 이 파일·콘솔을 쓰게 한다.
    import utils.logger as ulog
    ulog._shared_file_handler = fh
    ulog._shared_console_handler = ch
    ulog._shared_file_path = str(log_path)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)
    log = logging.getLogger("probe")
    raw = logging.getLogger("probe.raw")
    for lg, hs in ((log, (fh, ch)), (raw, (fh,))):
        lg.setLevel(logging.INFO)
        lg.propagate = False
        for h in hs:
            lg.addHandler(h)
    return log, raw


def _f(row: Dict[str, Any], key: str) -> float:
    try:
        return float(str(row.get(key, "") or 0).replace(",", ""))
    except ValueError:
        return 0.0


def _pick(row: Dict[str, Any], fields: Tuple[str, ...]) -> Dict[str, Any]:
    return {k: row.get(k) for k in fields if k in row}


def _read_live_holiday_cache(instance_dir: Path, now: datetime) -> Optional[bool]:
    """라이브 트리의 KIS 휴장일 캐시를 «읽기만» 한다(쓰지 않음). 없거나 못 읽으면 None."""
    p = instance_dir.parents[1] / "holiday_kis_cache.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return now.strftime("%Y%m%d") in set(data.get("closed_days", []))
    except (OSError, ValueError):
        return None


def _print_guards(log: logging.Logger, title: str, guards: List[Guard]) -> None:
    log.info(f"── {title}")
    for name, ok, detail in guards:
        log.info(f"   [{'PASS' if ok else 'FAIL'}] {name} — {detail}")


def _ledger(log: logging.Logger, gate: HttpGate) -> List[Dict[str, Any]]:
    """HTTP 장부 요약 + 실제로 «보내진» 주문·취소 호출 목록 반환."""
    counts: Dict[str, int] = {}
    for c in gate.calls:
        label = "hashkey" if c["path"] == PATH_HASHKEY else (c.get("tr_id") or c["path"])
        key = f"{c['method']} {label}{' (차단)' if c.get('blocked') else ''}"
        counts[key] = counts.get(key, 0) + 1
    log.info("── HTTP 장부(KIS 도메인): " + " · ".join(f"{k} x{v}" for k, v in counts.items()))
    sent = [c for c in gate.calls if c["path"] in ORDER_PATHS and not c.get("blocked")]
    log.info(f"   주문·취소 경로로 «보내진» 호출 = {len(sent)}건 · 게이트 차단 = "
             f"{sum(1 for c in gate.calls if c.get('blocked'))}건")
    return sent


def run(args: argparse.Namespace, inst_dir: Path, log: logging.Logger, raw: logging.Logger,
        masker: Masker, log_path: Path) -> int:
    from config import settings
    masker.add(settings.APP_KEY, settings.SECRET_KEY, settings.ACCOUNT_NUMBER,
               (settings.ACCOUNT_NUMBER or "")[:8], settings.HTS_ID)
    import api.kis_auth as kis_auth

    mode = "LIVE" if args.live else "DRY-RUN"
    log.info(f"===== real_order_cancel_probe [{mode}] code={args.code} qty={QTY} =====")
    log.info(f"cwd={Path.cwd()} · log={log_path}")
    log.info(f"KIS_INSTANCE_DIR={inst_dir} · INSTANCE_ID={settings.INSTANCE_ID}")
    tok = Path(kis_auth.TOKEN_FILE_PATH)
    log.info(f"토큰 캐시 = {tok} (이미 있음={tok.exists()}) — 없거나 만료면 auth() 가 새로 발급해 이 경로에 저장")

    state = GateState(live=args.live)
    gate = HttpGate(kis_auth.requests, state, urlparse(settings.KIS_BASE_URL).netloc, log, raw, masker)
    kis_auth.requests = gate

    pre = [check_cwd(Path.cwd())] + check_instance(settings.INSTANCE_ID, settings.CONFIG_FILE.exists(),
                                                    settings.KIS_BASE_URL)
    _print_guards(log, "필수 전제(KIS 호출 전)", pre)
    if not all(ok for _, ok, _ in pre):
        log.error("🔴 필수 전제 실패 → KIS 호출 없이 종료")
        return 2

    cfg = settings.load_trading_config()
    real_mode = check_real_mode(settings.LAST_TRADING_CONFIG_LOAD_OK, getattr(cfg, "paper_trading", None))
    log.info(f"trading_config = {settings.LAST_LOADED_TRADING_CONFIG_PATH}")

    from framework.broker import KISBroker
    broker = KISBroker()
    if not asyncio.run(broker.connect()):
        log.error("🔴 broker.connect() 실패 → 종료")
        _ledger(log, gate)
        return 2
    env = kis_auth.getTREnv()
    if env is not None:
        masker.add(env.my_token, str(env.my_token).replace("Bearer ", ""), env.my_acct)

    from api import kis_market_api
    df = kis_market_api.get_inquire_price("J", args.code)
    if df is None or df.empty:
        log.error("🔴 현재가 조회 실패 → 종료")
        _ledger(log, gate)
        return 2
    q = df.iloc[0].to_dict()
    base, cur, llam, mxpr = _f(q, "stck_sdpr"), _f(q, "stck_prpr"), _f(q, "stck_llam"), _f(q, "stck_mxpr")
    name = q.get("hts_kor_isnm") or q.get("bstp_kor_isnm") or "?"
    price = compute_order_price(base)
    log.info(f"── 시세 {args.code}({name}): 현재가 {cur:,.0f} · 기준가(전일종가) {base:,.0f} · "
             f"전일대비 {q.get('prdy_vrss')} · 하한가 {llam:,.0f} · 상한가 {mxpr:,.0f} · "
             f"거래정지 {q.get('temp_stop_yn')} · 종목상태 {q.get('iscd_stat_cls_code')}")

    pending0 = broker.get_pending_orders()
    log.info(f"── 시작 시 미체결: {'조회 실패(None)' if pending0 is None else f'{len(pending0)}건'}")
    for r in pending0 or []:
        log.info(f"   {masker.obj(_pick(r, PENDING_FIELDS))}")

    from config.market_hours import MarketHours, now_kst
    from utils.korean_holidays import is_holiday
    now = now_kst()
    guards: List[Guard] = []
    guards.append(check_trading_day(MarketHours.get_market_status("KRX", now), is_holiday(now),
                                    _read_live_holiday_cache(inst_dir, now)))
    guards.append(check_time_window(now))
    guards += check_price_guards(price, base, cur, llam)
    eb = check_expect_base(args.expect_base, base)
    if eb is not None:
        guards.append(eb)
    guards.append(("수량 = 1 고정", QTY == 1, f"QTY={QTY}"))
    guards.append(check_no_pending(pending0))
    guards += real_mode
    _print_guards(log, "live 가드", guards)
    all_ok = all(ok for _, ok, _ in guards)

    log.info(f"── 계획: {args.code}({name}) 지정가 매수 {QTY}주 @ {price:,}원 "
             f"(기준가 {base:,.0f} 의 {price / base * 100 if base else 0:.2f}%) · 예상 금액 {price * QTY:,}원 · "
             f"→ {WAIT_SEC:.0f}초 → 미체결 조회 → cancel_order → {WAIT_SEC:.0f}초 → 재조회 → 당일 주문조회")

    if not args.live:
        sent = _ledger(log, gate)
        log.info(f"===== DRY-RUN 종료 — 주문·취소 TR 보낸 횟수 {len(sent)} (0 이어야 정상) · "
                 f"live 가드 {'전부 통과' if all_ok else '실패 있음(위 FAIL)'} =====")
        return 0 if not sent else 9

    if not all_ok:
        log.error("🔴 live 가드 실패 → 주문 없이 종료")
        _ledger(log, gate)
        return 3
    return _run_live(args, broker, gate, state, log, masker, price, now_kst)


def _remain_state(pend: Optional[List[dict]], hits: List[dict], ever_visible: bool) -> Optional[bool]:
    """True = 목록에 남음 · False = 한 번은 보였고 지금은 없음 · None = 미상(조회 실패 또는 한 번도 안 보임)."""
    if pend is None:
        return None
    if hits:
        return True
    return False if ever_visible else None


def _emergency_cancel(broker: Any, log: logging.Logger, masker: Masker, odno: str, code: str) -> None:
    """예외·Ctrl+C 중단 시 이 주문 전량 취소 1회 시도(게이트는 target_odno 전량 취소만 허용)."""
    try:
        log.critical(f"비상 취소 1회 시도 — 주문번호 {odno} · 종목 {code}")
        r = broker.cancel_order(odno, code)
        log.critical(f"비상 취소 반환(성공 여부는 HTS 로 확인): {masker.obj(r)}")
    except BaseException as e2:  # 두 번째 Ctrl+C 등 — 원래 예외를 살려 보낸다
        log.critical(f"비상 취소 중 예외 {type(e2).__name__}: {e2}")


def _run_live(args: argparse.Namespace, broker: Any, gate: HttpGate, state: GateState,
              log: logging.Logger, masker: Masker, price: int, now_kst: Any) -> int:
    from api import kis_order_api

    w = check_time_window(now_kst())       # 주문 직전 재확인
    if not w[1]:
        log.error(f"🔴 주문 직전 시간창 이탈({w[2]}) → 주문 없이 종료")
        _ledger(log, gate)
        return 3

    state.planned = {"PDNO": args.code, "ORD_QTY": str(QTY), "ORD_UNPR": str(int(price)), "ORD_DVSN": "00"}
    res: Dict[str, Any] = {"order": None, "odno": "", "visible": None, "ever_visible": False, "exact_fmt": None,
                           "cancel1": None, "cancel1_raw": None, "cancel2": None, "remain": None,
                           "daily_rows": [], "daily_ok": None}
    cleared = False
    try:
        order = broker.place_buy_order(args.code, QTY, int(price))
        res["order"] = order
        odno = str(order.get("order_id") or "")
        res["odno"] = odno
        state.target_odno = odno           # 비상 취소도 이 주문번호만 게이트를 통과한다
        log.info(f"① 주문 결과: {masker.obj(order)}")
        _time.sleep(WAIT_SEC)

        if not odno:
            pend = broker.get_pending_orders()
            ours = [r for r in pend or [] if str(r.get("pdno")) == args.code]
            log.info(f"② (주문번호 없음) 미체결 확인: {'조회 실패' if pend is None else f'{len(pend)}건'} · "
                     f"이 종목 {len(ours)}건")
            if pend is None or ours:
                log.critical(f"**🔴 HTS 에서 즉시 확인·수동 취소 — 종목 {args.code} "
                             f"(주문 응답은 실패인데 미체결이 있거나 확인 불가)**")
            else:
                cleared = True
        else:
            pend1 = broker.get_pending_orders()
            hit = find_rows(pend1, odno)
            res["visible"] = bool(hit)
            res["ever_visible"] = bool(hit)
            res["exact_fmt"] = any(str(r.get("odno")) == odno for r in pend1 or [])
            log.info(f"② 미체결 조회: {'조회 실패' if pend1 is None else f'{len(pend1)}건'} · "
                     f"이 주문 보임={bool(hit)} · 주문번호 문자열 완전일치={res['exact_fmt']} · "
                     f"{[masker.obj(_pick(r, PENDING_FIELDS)) for r in hit]}")

            n0 = len(gate.calls)
            c1 = broker.cancel_order(odno, args.code)
            res["cancel1"] = c1
            res["cancel1_raw"] = gate.last(TR_CANCEL, since=n0)   # «1차» 취소 TR 원응답(없으면 None = 안 보냄)
            if res["cancel1_raw"]:
                res["ever_visible"] = True     # cancel_order 내부 조회가 찾아서 취소 TR 을 보냈다
            log.info(f"③ cancel_order 반환(판정에 쓰지 않음): {masker.obj(c1)} · 1차 취소 TR 원응답 rt_cd="
                     f"{(res['cancel1_raw'] or {}).get('rt_cd', '미전송')}")
            _time.sleep(WAIT_SEC)
            pend2 = broker.get_pending_orders()
            hit2 = find_rows(pend2, odno)
            res["ever_visible"] = res["ever_visible"] or bool(hit2)
            remain = _remain_state(pend2, hit2, res["ever_visible"])
            log.info(f"④ 재조회: {'조회 실패' if pend2 is None else f'{len(pend2)}건'} · 이 주문 잔존="
                     f"{'미상' if remain is None else remain}")
            if remain is not False:            # 잔존 또는 미상 → 1회만 더
                n1 = len(gate.calls)
                c2 = broker.cancel_order(odno, args.code)
                res["cancel2"] = c2
                if gate.last(TR_CANCEL, since=n1):
                    res["ever_visible"] = True
                log.info(f"③′ 2차 cancel_order 반환: {masker.obj(c2)}")
                _time.sleep(WAIT_SEC)
                pend3 = broker.get_pending_orders()
                hit3 = find_rows(pend3, odno)
                res["ever_visible"] = res["ever_visible"] or bool(hit3)
                remain = _remain_state(pend3, hit3, res["ever_visible"])
                log.info(f"④′ 2차 재조회: {'조회 실패' if pend3 is None else f'{len(pend3)}건'} · "
                         f"이 주문 잔존={'미상' if remain is None else remain}")
            res["remain"] = remain
            if remain is True:
                log.critical(f"**🔴 HTS 에서 즉시 수동 취소 — 주문번호 {odno} · 종목 {args.code}**")
            elif remain is None:
                log.critical(f"**🔴 잔존 미상(미체결 목록에 한 번도 안 보였거나 조회 실패 → cancel_order 가 취소를 "
                             f"안 보냈을 수 있음) — HTS 에서 즉시 확인·취소 · 주문번호 {odno} · 종목 {args.code}**")
            else:
                cleared = True

        today = now_kst().strftime("%Y%m%d")
        daily = kis_order_api.get_inquire_daily_ccld_lst("01", today, today)
        res["daily_ok"] = daily is not None
        rows = daily.to_dict("records") if daily is not None and not daily.empty else []
        sel = find_rows(rows, res["odno"], keys=("odno", "orgn_odno")) if res["odno"] else \
            [r for r in rows if str(r.get("pdno")) == args.code]
        res["daily_rows"] = sel
        log.info(f"⑤ 당일 주문조회(TTTC0081R): {'조회 실패' if daily is None else f'{len(rows)}행'} · "
                 f"이 주문 관련 {len(sel)}행")
        for r in sel:
            log.info(f"   {masker.obj(_pick(r, DAILY_FIELDS))}")
    except BaseException as e:  # KeyboardInterrupt 포함 — 주문이 남았을 수 있다
        log.critical(f"**🔴 예외로 중단({type(e).__name__}: {e}) · 주문번호 {res.get('odno') or '없음/미상'}**")
        if state.target_odno and not cleared:
            _emergency_cancel(broker, log, masker, state.target_odno, args.code)
        log.critical(f"**🔴 HTS 에서 즉시 미체결 확인·수동 취소 — 주문번호 {res.get('odno') or '없음/미상'} · "
                     f"종목 {args.code}**")
        _ledger(log, gate)
        raise
    verified = _summary(log, gate, masker, args.code, res, cleared)
    return 0 if verified else 4


def _summary(log: logging.Logger, gate: HttpGate, masker: Masker, code: str,
             res: Dict[str, Any], cleared: bool) -> bool:
    """판정 요약 출력. 반환 = 재조회 0건 · 한 번은 보였음 · 당일조회 취소 흔적 · 원주문 잔량 미잔존 4중 확인."""
    sent = _ledger(log, gate)
    odno = res["odno"]
    c1 = res["cancel1"] or {}
    c1_data = c1.get("data") or {}
    raw1 = res["cancel1_raw"] or {}
    raw_last = gate.last(TR_CANCEL) or {}
    raw_out = (raw1.get("body") or {}).get("output")
    raw_out_keys = sorted(raw_out) if isinstance(raw_out, dict) else type(raw_out).__name__
    rows = res["daily_rows"]
    orig = [r for r in rows if normalize_odno(r.get("odno")) == normalize_odno(odno)]
    cancel_rows = [r for r in rows if odno and normalize_odno(r.get("orgn_odno")) == normalize_odno(odno)]
    orig_cancelled = any(str(r.get("cncl_yn", "")).upper() == "Y" or _f(r, "cncl_cfrm_qty") >= 1 for r in orig)
    cancel_evidence = bool(cancel_rows) or orig_cancelled
    orig_live = any(_f(r, "rmn_qty") > 0 for r in orig) and not cancel_evidence
    filled = sum(_f(r, "tot_ccld_qty") for r in orig)
    b1, b1_why = judge_new_b1(res["cancel1"], res["cancel1_raw"], res["remain"])
    verified = (bool(odno) and cleared and bool(res["ever_visible"]) and bool(res["daily_ok"])
                and cancel_evidence and not orig_live)

    def mk(v: Optional[bool]) -> str:
        return "✓" if v else ("?" if v is None else "✗")

    log.info("=" * 78)
    log.info("판정 요약")
    log.info(f" 주문 접수 {mk(bool(odno))} (ODNO={odno or '-'})")
    log.info(f" 미체결 조회에 보임 {mk(res['visible'])} (한 번이라도 보임={res['ever_visible']} · "
             f"주문번호 문자열 완전일치={res['exact_fmt']})")
    log.info(f" cancel_order(1차) 반환: success={c1.get('success')} · message={c1.get('message')!r} · "
             f"data 의 ODNO 있음={'ODNO' in c1_data} ({c1_data.get('ODNO', '-')})")
    log.info(f" 1차 취소 TR 원응답: rt_cd={raw1.get('rt_cd', '미전송')} · msg_cd={raw1.get('msg_cd')} · "
             f"msg1={raw1.get('msg1')} · output 키={raw_out_keys}")
    if res["cancel2"]:
        log.info(f" 2차 cancel_order 반환: {masker.obj(res['cancel2'])} · 마지막 취소 TR rt_cd={raw_last.get('rt_cd')}")
    log.info(f" 재조회 잔존 0 {mk(None if res['remain'] is None else not res['remain'])}"
             f"{' (미상)' if res['remain'] is None and odno else ''}{' (2차 취소 시도함)' if res['cancel2'] else ''}")
    log.info(f" 당일조회 취소 행 {mk(cancel_evidence) if res['daily_ok'] else '? (조회 실패)'} "
             f"(취소주문 행 {len(cancel_rows)} · 원주문 cncl_yn/cncl_cfrm_qty 취소 반영={orig_cancelled} · "
             f"원주문 잔량>0·취소흔적 없음={orig_live} · 체결수량 합 {filled:g})")
    for r in orig:
        log.info(f"   원주문: {masker.obj(_pick(r, DAILY_FIELDS))}")
    for r in cancel_rows:
        log.info(f"   취소주문: {masker.obj(_pick(r, DAILY_FIELDS))}")
    log.info(f" NEW-B1 = {b1} — {b1_why}")
    log.info(f" 주문·취소 경로로 보낸 HTTP {len(sent)}건: {[(c['tr_id'], c.get('rt_cd')) for c in sent]}")
    log.info(f" 교차 확인(재조회 0 · 한 번은 보임 · 당일조회 취소 흔적 · 원주문 잔량 미잔존) {mk(verified)}")
    log.info("사람이 할 일")
    if res["remain"] is True or (odno and res["remain"] is None) or (not odno and not cleared):
        log.critical(f"**🔴 HTS 에서 즉시 확인·수동 취소 — 주문번호 {odno or '미상'} · 종목 {code}**")
    if orig_live:
        log.critical(f"**🔴 당일조회 원주문 잔량>0 · 취소 흔적 없음 — HTS 에서 즉시 확인·취소 · 주문번호 {odno}**")
    elif cleared and not verified:
        log.warning(f"**⚠️ 재조회엔 없지만 교차 확인 불충분 — HTS 미체결 화면에서 주문번호 {odno or '미상'} 직접 확인**")
    if filled > 0:
        log.critical(f"**🔴 체결 {filled:g}주 발생 — 10-19 전 계좌 보유 0 으로 되돌릴 것(대사 abort 방지)**")
    log.info(" - HTS 미체결·당일 주문내역 화면으로 위 결과 눈으로 대조(미체결 0 · 체결 0)")
    log.info(" - 체크리스트 §4-B 에 ODNO · cncl_yn · rmn_qty · cncl_cfrm_qty · NEW-B1 판정 · 이 로그 경로 기록")
    log.info("=" * 78)
    return verified


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="실전 주문 접수·취소 1회성 시험(§4-B). 기본 dry-run.")
    p.add_argument("--code", required=True, help="종목코드 6자리(필수 · 기본값 없음)")
    p.add_argument("--live", action="store_true", help="실제 주문 1건(가드 전부 통과 시에만)")
    p.add_argument("--instance-dir", default=DEFAULT_INSTANCE_DIR, help="실전 인스턴스 폴더(읽기만)")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="probe 로그 폴더(워크트리·라이브 트리 밖)")
    p.add_argument("--expect-base", type=int, default=None,
                   help="(선택) 기대 기준가(원). 주어지면 조회 기준가와 같아야 live 진행")
    a = p.parse_args(argv)
    if not (len(a.code) == 6 and a.code.isdigit()):
        p.error("--code 는 숫자 6자리")
    return a


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    cg = check_cwd(Path.cwd())
    if not cg[1]:
        print(f"🔴 라이브 트리 아래에서 실행 금지({cg[2]}) — 워크트리 RoboTrader_template 에서 실행 → 종료",
              file=sys.stderr)
        return 2
    # config.settings 는 import 시점에 key.ini 를 읽는다 → 프로젝트 모듈 import «전»에 인스턴스를 고정한다.
    inst_dir = Path(args.instance_dir).resolve()
    prev = os.environ.get("KIS_INSTANCE_DIR")
    if prev and Path(prev).resolve() != inst_dir:
        print(f"KIS_INSTANCE_DIR({prev}) 가 --instance-dir({inst_dir}) 와 다름 → 종료", file=sys.stderr)
        return 2
    os.environ["KIS_INSTANCE_DIR"] = str(inst_dir)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"probe_{datetime.now():%Y%m%d_%H%M%S}.log"
    masker = Masker()
    log, raw = _setup_logging(log_path, masker)
    try:
        return run(args, inst_dir, log, raw, masker, log_path)
    except Exception as e:
        log.exception(f"예외로 종료: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
