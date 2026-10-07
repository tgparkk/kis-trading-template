"""실전 1주 «체결» 1회성 시험 — 체크리스트 §4-C (장중 · 현재가 지정가 매수 1주 → 체결 → 시장가 매도 1주).

■ exit 코드표 (고정 · 무인 실행기는 이 값 + 출력 폴더의 result_<YYYYMMDD_HHMMSS>.json 으로 판정한다)
  0  정상. live = 매수 체결 → 시장가 매도 체결 → 종료 확인(계좌 보유 0 · 미체결 0 · 당일 새 주문 매수 체결 1 · 매도 체결 1).
     dry-run = 주문·취소 TR 전송 0건(live 가드 통과 여부는 result json 의 guards_all_pass).
  1  예외 종료 — 주문·취소 TR 을 «하나도» 보내지 않은 상태(계좌 영향 없음 · 원인 확인 뒤 재실행 가능).
  2  필수 전제·사전 가드 FAIL(인자 오류·라이브 트리 실행 포함) → 주문 0건.
  3  매수가 체결 없이 끝남(시간 초과 → 취소, 또는 접수 거부) + 보유 0 · 미체결 0 확인 → 재시도 가능.
  4  CRITICAL «HTS 즉시 확인» — 보유가 남았거나 «남았는지 모름» · 미체결이 남았거나 모름 · 비상 처리(예외·Ctrl+C) 경로 ·
     종료 확인 불일치 · dry-run 인데 주문 TR 이 나감. «보유가 남았는지 모름»은 언제나 4 다.
  (이 밖의 값은 쓰지 않는다. argparse --help 만 0 으로 끝나고 결과 파일을 쓰지 않는다.)

근거
- docs/checklist_2026-10-05_real_daytrading_holiday_verification.md §4 표 C 줄(브랜치 docs/checklist-1005-results)
- docs/audit_2026-09-14_real_trading_switch.md P2-14(시장가 매도 order.price=0 · avg_prvs 빈값/'0' 이면 영원히 보류) · §8 Q2
- docs/audit_2026-10-04_real_daytrading_flow.md NEW-B1(취소 성공을 실패로 판정 — 이 스크립트는 취소 결과를 «재조회»로 판정)

흐름 (live)
  사전 가드 전부 PASS → 주문 직전 현재가 재조회·재검사 → ① 현재가 지정가 매수 1주(KISBroker.place_buy_order)
  → ② 체결 대기(--fill-wait 초 · 2.5초 간격 TTTC8036R 미체결 + TTTC0081R 당일 주문체결 폴링 · 원주문 행 전 필드 기록)
  → (미체결) 취소 → 재조회 → 보유 0 이면 exit 3 / 경합으로 보유 1 이면 매도로
  → ③ 잔고(TTTC8434R) 재조회로 보유 1 확인 → 시장가 매도 1주(KISBroker.place_sell_order(code, 1, 0, "01") = 봇 실전 시장가 매도와 같은 경로)
  → ④ 매도 체결 대기(60초 · avg_prvs 가 채워질 때까지 관측) → ⑤ 종료 확인 → 요약 md · 결과 json.

안전장치
- 기본 dry-run(읽기 TR 만). --live 일 때만 주문. 매수 HTTP 는 프로세스당 1회 · 매도 HTTP 도 프로세스당 1회(정상 또는 비상 중 하나).
  매도가 한 번 나간 뒤에는(응답이 실패·무응답이어도) 다시 매도하지 않는다(이중 매도 = 공매도 시도 방지).
- HTTP 게이트(api.kis_auth.requests 교체): 계획과 «정확히» 같은 매수 1건(지정가 00) · 매도 1건(시장가 01 · 0원 · 1주) ·
  이 시험 «매수» 주문의 전량 취소만 통과. 그 밖의 POST 는 차단. KIS 원응답은 전부 JSONL 로 기록(계좌·키·토큰 마스킹).
- 매수 HTTP 가 나간 뒤 예외·Ctrl+C 가 오면: 미체결 매수 취소 → 잔고 재조회 → 보유 1 이고 매도 미전송이면 시장가 매도 1회
  → CRITICAL · exit 4. 잔고를 못 읽으면 매도하지 않는다(보유 미상 = exit 4).
- 판정 불가(조회 실패)는 «미상»으로 남기고 «체결 0»으로 간주하지 않는다.

출력 (기본 D:/tmp/real_fill_probe_out/ · 같은 <ts> 로 묶임)
  fill_probe_<ts>.log  사람용 로그 · fill_probe_<ts>.jsonl  원응답·폴링 기록 · fill_probe_<ts>_summary.md  요약
  result_<ts>.json  기계용 결과(exit_code · verdict · 매수/매도 ODNO·체결·체결가 · 종료 보유·미체결 · 비상 매도 · CRITICAL 목록)

실행 (cwd = 워크트리 RoboTrader_template · bash):
  PYTHONPATH="$PWD:$PWD/.." PYTHONIOENCODING=utf-8 \
    D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe \
    scripts/real_order_fill_probe.py --code XXXXXX            # dry-run
  ... scripts/real_order_fill_probe.py --code XXXXXX --live     # 거래일 09:30~14:50 KST 에만 통과
  (선택) --max-price <원>(기본 30,000 · 상한 100,000) · --fill-wait <초>(기본 60 · 10~180)

봇 코드 파일은 수정하지 않는다. 공용 헬퍼(마스킹·게이트 골격·가드 일부)는 scripts/real_order_cancel_probe.py 에서 import 한다.
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
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

_RT_ROOT = Path(__file__).resolve().parents[1]          # RoboTrader_template — `scripts` 패키지 import 용
if str(_RT_ROOT) not in sys.path:
    sys.path.insert(0, str(_RT_ROOT))

from scripts import real_order_cancel_probe as cp  # noqa: E402  (stdlib 만 쓰는 모듈 · 부작용 없음)

# ---------------------------------------------------------------------------
# 상수 — 인자로 바꿀 수 없는 값들
# ---------------------------------------------------------------------------
DEFAULT_OUT_DIR = "D:/tmp/real_fill_probe_out"
LIVE_RT_ROOT = cp.LIVE_TREE_ROOT + "/RoboTrader_template"
QTY = 1                                 # 수량 고정(인자 없음)
WINDOW_START = dtime(9, 30, 0)          # 시가 변동 회피
WINDOW_END = dtime(14, 50, 0)           # 매도가 15:10 전에 끝나도록(15:20 종가 동시호가 회피)
BUY_HARD_STOP = dtime(15, 0, 0)         # 매수 체결 대기 중 이 시각을 넘으면 대기 중단 → 취소 경로
DEFAULT_MAX_PRICE = 30_000
MAX_PRICE_CEILING = 100_000             # --max-price 오타 방지 상한
DEFAULT_FILL_WAIT = 60
SELL_WAIT = 60                          # 매도 체결·avg_prvs 관측 최대(초)
EMERGENCY_SELL_WAIT = 20                # 비상 매도 뒤 짧은 관측(초)
POLL_SEC = 2.5                          # 폴링 간격(초) — 1회 = 8036R + 0081R 2건
WAIT_SEC = 2.0                          # 취소·매도 뒤 재조회 전 대기
EXTRA_POLLS_AFTER_FILL = 4              # 매수 체결 뒤 avg_prvs 를 기다리는 추가 폴링 수
CASH_MARGIN = 1.01                      # 주문가능금액 ≥ 매수가 x 1.01
MIN_TURNOVER = 1_000_000_000            # 누적 거래대금 ≥ 10억(유동성)
LIMIT_GAP = 0.05                        # 현재가가 상·하한가에서 5% 이상 떨어져 있어야
MAX_CANCEL_HTTP = 8                     # 취소 HTTP 상한(봇 _url_fetch 재시도 포함 여유)
SIDE_CD = {"buy": "02", "sell": "01"}   # sll_buy_dvsn_cd

TRACK_FIELDS = ("tot_ccld_qty", "avg_prvs", "tot_ccld_amt", "rmn_qty", "cncl_yn", "cnc_cfrm_qty", "rjct_qty",
                "ccld_unpr", "ord_qty", "ord_unpr", "ord_tmd", "ord_dvsn_name")
PENDING_TRACK = ("ord_qty", "ord_unpr", "psbl_qty", "tot_ccld_qty", "tot_ccld_amt", "ord_tmd")
QUOTE_FIELDS = ("stck_prpr", "stck_sdpr", "stck_mxpr", "stck_llam", "prdy_vrss", "prdy_ctrt", "acml_vol",
                "acml_tr_pbmn", "iscd_stat_cls_code", "temp_stop_yn", "vi_cls_code", "mang_issu_cls_code",
                "sltr_yn", "mrkt_warn_cls_code", "short_over_yn", "invt_caful_yn", "ssts_yn")
DECISIVE_QUOTE_FIELDS = ("mang_issu_cls_code", "sltr_yn", "invt_caful_yn", "ssts_yn")   # 빈껍데기 응답 판별(봇과 같음)
HOLD_FIELDS = ("pdno", "prdt_name", "hldg_qty", "ord_psbl_qty", "pchs_avg_pric", "pchs_amt", "prpr", "evlu_amt",
               "thdt_buyqty", "thdt_sll_qty")
COST_FIELDS_BAL = ("thdt_buy_amt", "thdt_sll_amt", "thdt_tlex_amt", "dnca_tot_amt", "nxdy_excc_amt",
                   "prvs_rcdl_excc_amt")
COST_FIELDS_DAILY = ("tot_ord_qty", "tot_ccld_qty", "tot_ccld_amt", "prsm_tlex_smtl", "pchs_avg_pric")

Guard = cp.Guard


# ---------------------------------------------------------------------------
# 순수 함수 (KIS 호출 없음 · 단위 테스트 대상)
# ---------------------------------------------------------------------------
def _s(v: Any) -> str:
    """KIS 문자열 값 정리(None·NaN → '')."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def num(v: Any) -> Optional[float]:
    """KIS 숫자 문자열 해석. 빈값·해석 불가 = None(«0» 으로 뭉개지 않는다)."""
    s = _s(v).replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def clean_row(r: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in r.items()}


def avg_state(row: Optional[Dict[str, Any]], key: str = "avg_prvs") -> str:
    """'행 없음' · '필드 없음' · '빈값' · '0' · '해석불가' · '값'."""
    if row is None:
        return "행 없음"
    if key not in row:
        return "필드 없음"
    if _s(row.get(key)) == "":
        return "빈값"
    n = num(row.get(key))
    if n is None:
        return "해석불가"
    return "값" if n > 0 else "0"


def implied_price(row: Optional[Dict[str, Any]]) -> Optional[float]:
    """tot_ccld_amt / tot_ccld_qty 역산(둘 다 > 0 일 때만)."""
    if not row:
        return None
    amt, q = num(row.get("tot_ccld_amt")), num(row.get("tot_ccld_qty"))
    if amt and q and amt > 0 and q > 0:
        return amt / q
    return None


def is_filled(row: Optional[Dict[str, Any]], qty: int = QTY) -> Optional[bool]:
    """당일 주문체결 행 기준 전량 체결 여부. 행·값이 없으면 None(미상)."""
    if row is None:
        return None
    q = num(row.get("tot_ccld_qty"))
    if q is None:
        return None
    return q >= qty


def fill_price(row: Optional[Dict[str, Any]]) -> Tuple[Optional[float], Optional[str]]:
    if row is None:
        return None, None
    if avg_state(row) == "값":
        return num(row.get("avg_prvs")), "avg_prvs"
    ip = implied_price(row)
    if ip is not None:
        return ip, "tot_ccld_amt/tot_ccld_qty"
    return None, None


def cancel_evidence(row: Optional[Dict[str, Any]], cancel_rows: List[Dict[str, Any]]) -> bool:
    if cancel_rows:
        return True
    if row is None:
        return False
    return _s(row.get("cncl_yn")).upper() == "Y" or (num(row.get("cnc_cfrm_qty")) or 0) >= 1


def new_rows(rows: Optional[List[Dict[str, Any]]], start_odnos: set, code: str, side_cd: str) -> List[Dict[str, Any]]:
    """시작 스냅샷에 없던 «원주문» 행(취소·정정 주문 행 = orgn_odno 있음 제외) 중 이 종목·이 방향."""
    out = []
    for r in rows or []:
        if _s(r.get("pdno")) != code or _s(r.get("sll_buy_dvsn_cd")) != side_cd:
            continue
        if cp.normalize_odno(r.get("orgn_odno")):
            continue
        if cp.normalize_odno(r.get("odno")) in start_odnos:
            continue
        out.append(r)
    return out


def emulate_get_order_status(pending: Optional[List[dict]], daily: Optional[List[dict]], odno: str) -> Dict[str, Any]:
    """framework.broker.KISBroker.get_order_status 와 같은 순서·같은 «문자열 완전일치» 판정(같은 두 TR 결과로)."""
    if pending:
        hit = [r for r in pending if r.get("odno") == odno]
        if hit:
            return {**hit[0], "_status": "pending"}
    if daily:
        hit = [r for r in daily if r.get("odno") == odno]
        if hit:
            return {**hit[0], "_status": "executed"}
    return {"odno": odno, "_status": "unknown", "status_unknown": True, "cncl_yn": "N"}


def bot_view(status: Optional[Dict[str, Any]], order_qty: int, order_price: float) -> Dict[str, Any]:
    """core/orders/order_monitor.py _process_order_status → _handle_full_fill 판정 흉내(코드 복사 · 실행 아님).
    시장가 매도는 봇에서 Order.price=0 → avg_prvs 가 빈값/'0' 이면 «체결가 비정상(0원) 보류» = P2-14."""
    if status is None:
        return {"code": "NONE", "price": None, "text": "get_order_status=None → 봇은 이번 사이클 건너뜀"}

    def _int(k: str) -> int:
        try:
            return int(str(status.get(k, 0)).replace(",", "").strip() or 0)
        except Exception:
            return 0

    filled, remaining = _int("tot_ccld_qty"), _int("rmn_qty")
    if status.get("cncl_yn", "N") == "Y":
        return {"code": "CANCELLED", "price": None, "text": "취소 확인"}
    if status.get("status_unknown"):
        return {"code": "UNKNOWN", "price": None, "text": "상태 불명(5분 유보)"}
    if status.get("actual_unfilled"):
        return {"code": "PENDING", "price": None, "text": "실제 미체결 플래그"}
    if remaining == 0 and filled == order_qty and filled > 0:
        api_ord_qty = _int("ord_qty")
        if api_ord_qty > 0 and api_ord_qty != order_qty:
            return {"code": "HOLD_QTY", "price": None, "text": f"API 주문수량 불일치 보류({api_ord_qty})"}
        price = float(order_price)
        try:
            avg = status.get("avg_prvs", status.get("ccld_unpr", ""))
            if avg and str(avg).replace(",", "").strip():
                price = float(str(avg).replace(",", "").strip())
        except (ValueError, TypeError):
            price = float(order_price)
        if price <= 0:
            return {"code": "P2-14", "price": price, "text": "체결가 비정상(0원) 보류 — 다음 사이클 재확인(P2-14)"}
        return {"code": "FILLED", "price": price, "text": f"체결 확정 @ {price:,.2f}"}
    if filled > 0 and remaining > 0:
        return {"code": "PARTIAL", "price": None, "text": f"부분체결 {filled}/{filled + remaining}"}
    return {"code": "PENDING", "price": None, "text": f"대기(체결 {filled} · 잔여 {remaining})"}


def avg_rule(polls: List[Dict[str, Any]]) -> Tuple[str, Optional[float]]:
    """폴링 기록(같은 방향)에서 «avg_prvs 채움 규칙» 판정 문장 + 처음 채워진 시각(주문 후 초)."""
    fp = [p for p in polls if p.get("daily_row") is not None and is_filled(p["daily_row"])]
    if not fp:
        return "판정 불가 — 전량 체결된 당일조회 행을 못 봄", None
    states = [avg_state(p["daily_row"]) for p in fp]
    vals = [_s(p["daily_row"].get("avg_prvs")) for p in fp]
    if all(s == "필드 없음" for s in states):
        return "avg_prvs 필드 자체가 응답에 없음(키 부재)", None
    first = next((p for p, s in zip(fp, states) if s == "값"), None)
    if states[0] == "값":
        return (f"체결이 보인 첫 조회(+{fp[0]['t']:.1f}s)부터 채워짐 = {vals[0]!r}", fp[0]["t"])
    if first is not None:
        k = states.index("값")
        return (f"체결 뒤 {k}회 {states[0]}({vals[0]!r}) → +{first['t']:.1f}s 에 채워짐 "
                f"(체결 확인 +{fp[0]['t']:.1f}s 뒤 {first['t'] - fp[0]['t']:.1f}s)", first["t"])
    uniq = sorted(set(zip(states, vals)))
    return (f"체결 뒤 끝까지 안 채워짐 {uniq} (관측 {len(fp)}회 · +{fp[0]['t']:.1f}s~+{fp[-1]['t']:.1f}s)", None)


# ── 가드 ────────────────────────────────────────────────────────────────────
def check_time_window(now: datetime) -> Guard:
    t = now.time()
    ok = WINDOW_START <= t <= WINDOW_END
    return (f"시간창 {WINDOW_START:%H:%M:%S}~{WINDOW_END:%H:%M:%S} KST", ok, f"지금 {now:%Y-%m-%d %H:%M:%S}")


def check_trading_day_open(market_status: str, holiday: bool, kis_closed: Optional[bool], can_order: bool) -> Guard:
    ok = market_status == "market_open" and not holiday and kis_closed is not True and bool(can_order)
    return ("거래일·정규장(market_open)·봇 주문 시간 게이트", ok,
            f"market_status={market_status} · is_holiday={holiday} · KIS캐시휴장={kis_closed} · "
            f"can_place_order={can_order}")


def quote_flags(q: Dict[str, Any]) -> List[str]:
    """현재가 응답의 이상 표식(봇 안전필터 실측 계약 + 보수적 추가). 하나라도 있으면 시험하지 않는다."""
    def u(k: str) -> str:
        return _s(q.get(k)).upper()

    out: List[str] = []
    if all(not u(k) for k in DECISIVE_QUOTE_FIELDS):
        out.append("빈껍데기 응답(판정 필드 전부 부재)")
    if u("iscd_stat_cls_code") == "58":
        out.append("거래정지(iscd_stat_cls_code=58)")
    if u("temp_stop_yn") == "Y":
        out.append("임시정지(temp_stop_yn=Y)")
    if u("vi_cls_code") != "N":
        out.append(f"VI 표식 vi_cls_code={q.get('vi_cls_code')!r}(N 아님)")
    if u("mang_issu_cls_code") == "Y":
        out.append("관리종목(mang_issu_cls_code=Y)")
    if u("sltr_yn") == "Y":
        out.append("정리매매(sltr_yn=Y)")
    if u("mrkt_warn_cls_code") not in ("", "00"):
        out.append(f"시장경고 mrkt_warn_cls_code={q.get('mrkt_warn_cls_code')!r}")
    if u("short_over_yn") == "Y":
        out.append("단기과열(short_over_yn=Y)")
    if u("invt_caful_yn") == "Y":
        out.append("투자유의(invt_caful_yn=Y)")
    return out


def check_quote(q: Dict[str, Any], max_price: int) -> List[Guard]:
    from framework.utils import validate_tick
    cur = num(q.get("stck_prpr")) or 0.0
    mx, ll = num(q.get("stck_mxpr")) or 0.0, num(q.get("stck_llam")) or 0.0
    turnover = num(q.get("acml_tr_pbmn")) or 0.0
    flags = quote_flags(q)
    tick = cp.tick_size(cur) if cur > 0 else 0
    return [
        ("현재가 > 0", cur > 0, f"현재가 {cur:,.0f}"),
        ("현재가 ≤ --max-price", 0 < cur <= max_price, f"{cur:,.0f} ≤ {max_price:,}"),
        ("주문가(=현재가)가 봇 호가표에 정렬(봇이 가격을 고치지 않음)",
         cur > 0 and cur == int(cur) and validate_tick(cur), f"{cur:,.0f} % {tick}"),
        ("상·하한가에서 5% 이상 떨어짐", mx > 0 and ll > 0 and cur <= mx * (1 - LIMIT_GAP) and cur >= ll * (1 + LIMIT_GAP),
         f"하한 {ll:,.0f} · 현재 {cur:,.0f} · 상한 {mx:,.0f}"),
        ("누적 거래대금 ≥ 10억(유동성)", turnover >= MIN_TURNOVER, f"acml_tr_pbmn={q.get('acml_tr_pbmn')!r}"),
        ("이상 표식 없음(거래정지·임시정지·VI·관리·정리매매·시장경고·단기과열·투자유의)", not flags,
         "; ".join(flags) or "정상"),
    ]


def check_cash(bot_avail: Optional[float], nrcvb: Optional[float], price: float) -> Guard:
    need = price * CASH_MARGIN
    ok = price > 0 and bot_avail is not None and nrcvb is not None and bot_avail >= need and nrcvb >= need
    return ("주문가능금액 ≥ 매수가 x 1.01", ok,
            f"봇 가용(TTTC8434R prvs_rcdl_excc_amt)={bot_avail} · 미수없는매수금액(TTTC8908R nrcvb_buy_amt)={nrcvb} "
            f"≥ {need:,.0f}")


def check_no_holdings(held: Optional[Dict[str, int]]) -> Guard:
    name = "시작 시 계좌 보유 종목 0"
    if held is None:
        return (name, False, "잔고 조회 실패(None) — 확인 못 한 상태로는 주문하지 않는다")
    pos = {k: v for k, v in held.items() if v > 0}
    if pos:
        return (name, False, f"보유 {pos} — 끝나고 «보유 0» 확인이 의미 없어지므로 거부")
    return (name, True, "0종목")


def check_real_instance_off(pid_files: List[str], procs: Optional[List[Dict[str, Any]]],
                            paper_pid: Optional[int], live_venv_exe: str) -> Guard:
    """실전 daytrading 인스턴스(main.py) 꺼짐. PID 파일 존재 · KIS_INSTANCE_DIR=…daytrading 프로세스 ·
    (환경 못 읽으면) 페이퍼 봇 밖의 kis-template venv main.py 프로세스 → FAIL. 프로세스 조회 실패도 FAIL."""
    name = "실전 daytrading 인스턴스 꺼짐"
    reasons = [f"PID 파일 있음 {p}" for p in pid_files]
    if procs is None:
        reasons.append("프로세스 조회 실패(psutil)")
        return (name, False, " / ".join(reasons))
    venv = os.path.normcase(os.path.normpath(live_venv_exe))
    exe_of = {p["pid"]: os.path.normcase(os.path.normpath(p.get("exe") or ".")) for p in procs}
    paper_parent = next((p.get("ppid") for p in procs if p["pid"] == paper_pid), None)
    for p in procs:
        inst = p.get("inst_dir")
        if inst is not None:
            if "daytrading" in str(inst).lower():
                reasons.append(f"KIS_INSTANCE_DIR=…daytrading 인 main.py pid={p['pid']}")
            continue
        related = exe_of.get(p["pid"]) == venv or exe_of.get(p.get("ppid")) == venv
        if related and p["pid"] not in (paper_pid, paper_parent):
            reasons.append(f"환경 못 읽은 kis-template venv main.py pid={p['pid']}(페이퍼 봇 {paper_pid} 밖)")
    return (name, not reasons, " / ".join(reasons) or f"main.py {len(procs)}개 · 페이퍼 pid={paper_pid}")


# ── HTTP 게이트 ──────────────────────────────────────────────────────────────
class FillGateState:
    """live 가 아니면 주문·취소 POST 는 전부 막힌다."""

    def __init__(self, live: bool):
        self.live = live
        self.planned_buy: Optional[Dict[str, str]] = None    # PDNO · ORD_QTY · ORD_UNPR · ORD_DVSN(00)
        self.planned_sell: Optional[Dict[str, str]] = None   # PDNO · ORD_QTY(1) · ORD_UNPR(0) · ORD_DVSN(01)
        self.target_odno = ""                                # 취소 허용 대상 = 이 시험의 «매수» 주문번호
        self.buy_calls = 0
        self.sell_calls = 0
        self.cancel_calls = 0


def fill_gate_decision(state: FillGateState, method: str, path: str, tr_id: str,
                       params: Dict[str, Any]) -> Tuple[bool, str]:
    """KIS 도메인 HTTP 1건 허용 여부(상태 변경 없음 — 횟수 증가는 게이트가 «보내기 직전»에 한다)."""
    m = method.upper()
    if m not in ("GET", "POST"):
        return False, f"허용 밖 메서드 차단({method})"
    if m == "GET":
        return True, "읽기(GET)"
    if path == cp.PATH_TOKEN:
        return True, "토큰 발급"
    if not state.live:
        return False, "dry-run: POST 차단"
    if path == cp.PATH_HASHKEY:
        return True, "hashkey(live)"
    if path == cp.PATH_ORDER_CASH:
        if tr_id == cp.TR_BUY:
            plan, used, what = state.planned_buy, state.buy_calls, "매수"
        elif tr_id == cp.TR_SELL:
            plan, used, what = state.planned_sell, state.sell_calls, "매도"
            if str(params.get("ORD_QTY", "")) != str(QTY):
                return False, f"매도 수량 {params.get('ORD_QTY')!r} ≠ {QTY} 차단"
        else:
            return False, f"허용 밖 주문 TR 차단({tr_id})"
        if plan is None:
            return False, f"계획 미설정 상태의 {what} 차단"
        if used >= 1:
            return False, f"{what} HTTP 는 프로세스당 1회(재전송·이중 {what} 차단)"
        for k, v in plan.items():
            if str(params.get(k, "")) != str(v):
                return False, f"계획과 다른 {what} 차단({k}={params.get(k)!r} ≠ {v!r})"
        return True, f"계획된 {what} 1건"
    if path == cp.PATH_ORDER_RVSECNCL:
        if tr_id != cp.TR_CANCEL:
            return False, f"취소 외 TR 차단({tr_id})"
        if not state.target_odno:
            return False, "대상(매수) 주문번호 미설정"
        if str(params.get("RVSE_CNCL_DVSN_CD", "")) != "02":
            return False, "정정 차단(취소 02 만)"
        if str(params.get("QTY_ALL_ORD_YN", "")) != "Y":
            return False, "잔량전부(Y) 아닌 취소 차단"
        if cp.normalize_odno(params.get("ORGN_ODNO")) != cp.normalize_odno(state.target_odno):
            return False, "이 시험 매수 주문이 아닌 주문의 취소 차단(매도 취소 포함)"
        if state.cancel_calls >= MAX_CANCEL_HTTP:
            return False, f"취소 HTTP 상한 {MAX_CANCEL_HTTP} 초과"
        return True, "이 시험 매수 주문 전량 취소"
    return False, f"허용 목록 밖 POST 차단({path})"


class FillHttpGate(cp.HttpGate):
    """cancel probe 의 HttpGate(get·post·request·차단 경로·last) 재사용 + _call 만 교체:
    결정 함수(매수 1 · 매도 1 · 매수 취소) · 방향별 횟수 · JSONL 기록 · KeyboardInterrupt 도 기록 뒤 재전파."""

    def _call(self, method: str, url: str, kw: Dict[str, Any]) -> Any:
        u = urlparse(url)
        if u.netloc != self._kis_host:            # URL 에 토큰이 있을 수 있으므로 host 만 기록
            if method == "POST" and u.netloc in cp.EXTERNAL_POST_HOSTS:
                self._log.info(f"[HTTP] 외부 호출 {method} host={u.netloc} (허용 · 기록 생략)")
                return self._real.post(url, **kw)
            self._log.warning(f"[HTTP] 🛑 외부 호스트 차단 {method} host={u.netloc}")
            return cp._blocked_response(url, f"외부 호스트 차단({u.netloc})")
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
        rec: Dict[str, Any] = {"kind": "http", "seq": seq, "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                               "method": method, "path": u.path, "tr_id": tr_id,
                               "tr_cont_req": headers.get("tr_cont", ""), "params": self._m.obj(params)}
        ok, reason = fill_gate_decision(self._state, method, u.path, tr_id, params)
        if not ok:
            rec.update({"blocked": True, "reason": reason})
            self.calls.append(rec)
            self._log.warning(f"[HTTP#{seq}] 🛑 차단 {method} {u.path} tr_id={tr_id} — {reason}")
            self._raw.info(json.dumps(rec, ensure_ascii=False, default=str))
            return cp._blocked_response(url, reason)
        if u.path == cp.PATH_ORDER_CASH:
            if tr_id == cp.TR_BUY:
                self._state.buy_calls += 1
            elif tr_id == cp.TR_SELL:
                self._state.sell_calls += 1
        elif u.path == cp.PATH_ORDER_RVSECNCL:
            self._state.cancel_calls += 1
        rec.update({"blocked": False, "reason": reason})
        try:
            resp = self._real.get(url, **kw) if method == "GET" else self._real.post(url, **kw)
        except BaseException as e:  # 기록 후 원래 흐름(봇 오류 처리 · Ctrl+C)으로 돌려보낸다
            rec["exception"] = f"{type(e).__name__}: {e}"
            self.calls.append(rec)
            self._log.error(f"[HTTP#{seq}] {method} {u.path} tr_id={tr_id} 예외 {type(e).__name__}")
            self._raw.info(self._m.text(json.dumps(rec, ensure_ascii=False, default=str)))
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
        label = "hashkey" if u.path == cp.PATH_HASHKEY else (tr_id or u.path)
        self._log.info(f"[HTTP#{seq}] {method} {label} status={resp.status_code} "
                       f"rt_cd={rec.get('rt_cd')} msg_cd={rec.get('msg_cd')} msg1={rec.get('msg1')}")
        self._raw.info(self._m.text(json.dumps(rec, ensure_ascii=False, default=str)))
        return resp

    def last_body(self, tr_id: str) -> Optional[Dict[str, Any]]:
        c = self.last(tr_id)
        return (c or {}).get("body") if c else None


# ---------------------------------------------------------------------------
# 실행 문맥 · 결과
# ---------------------------------------------------------------------------
def _new_side() -> Dict[str, Any]:
    return {"odno": "", "t0": None, "sent_at": "", "bot_price": 0.0, "t_fill": None, "t_avg": None, "t_bot": None,
            "response": None, "adopted": False, "polls": 0}


def new_result(args: argparse.Namespace, paths: Dict[str, str]) -> Dict[str, Any]:
    side = {"sent": False, "odno": "", "odno_adopted": False, "order_price": None, "filled": None,
            "fill_price": None, "fill_price_source": None, "fill_latency_sec": None, "bot_fill_confirm_sec": None,
            "avg_prvs_first_valid_sec": None, "avg_prvs_rule": None, "implied_price": None,
            "avg_matches_implied": None, "bot_view_last": None}
    return {
        "script": "real_order_fill_probe", "result_version": 1,
        "started_at": datetime.now().isoformat(timespec="seconds"), "ended_at": None,
        "mode": "live" if getattr(args, "live", False) else "dry-run", "code": getattr(args, "code", None),
        "stock_name": None, "exit_code": None, "verdict": None,
        "guards_all_pass": None, "guards_failed": [],
        "buy": {**side, "order_dvsn": "00", "cancel_tried": False, "cancels": []},
        "sell": {**side, "order_dvsn": "01", "order_price": 0, "p2_14_condition": None, "p2_14_polls": 0},
        "holding_after_buy": None, "end_holding_qty": None, "end_holding_total": None, "end_pending_count": None,
        "end_daily_new_buy_filled": None, "end_daily_new_sell_filled": None,
        "emergency_sell_tried": False, "emergency": None,
        "critical": [], "order_http": [], "files": dict(paths),
    }


class Ctx:
    def __init__(self, args: argparse.Namespace, inst_dir: Path, log: logging.Logger, raw: logging.Logger,
                 masker: Any, now_fn: Callable[[], datetime], paths: Dict[str, str]):
        self.args, self.code, self.inst_dir = args, args.code, Path(inst_dir)
        self.log, self.raw, self.masker, self.now = log, raw, masker, now_fn
        self.paths = paths
        self.res = new_result(args, paths)
        self.gate: Optional[FillHttpGate] = None
        self.state: Optional[FillGateState] = None
        self.broker: Any = None
        self.polls: List[Dict[str, Any]] = []
        self.guard_groups: List[Tuple[str, List[Guard]]] = []   # (제목, 가드들)
        self.start_odnos: set = set()
        self.today = ""
        self.quote: Dict[str, Any] = {}
        self.cash: Tuple[Optional[float], Optional[float]] = (None, None)
        self.rt = {"buy": _new_side(), "sell": _new_side()}
        self.buy_closed = False          # 매수 주문이 체결 또는 취소로 «닫힘» 확인
        self.emergency_done = False
        self.last_summary: Optional[Dict[str, Any]] = None   # 마지막 잔고 요약(output2)
        self.restore: List[Callable[[], None]] = []

    def crit(self, msg: str) -> None:
        self.log.critical(msg)
        self.res["critical"].append(self.masker.text(msg))

    def jsonl(self, obj: Dict[str, Any]) -> None:
        self.raw.info(json.dumps(self.masker.obj(obj), ensure_ascii=False, default=str))

    def order_touched(self) -> bool:
        st = self.state
        return bool(st and (st.buy_calls or st.sell_calls or st.cancel_calls))


def _ts(ctx: Ctx) -> str:
    return ctx.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# 런타임 조회 (봇과 같은 함수)
# ---------------------------------------------------------------------------
def _quote(ctx: Ctx) -> Optional[Dict[str, Any]]:
    from api import kis_market_api
    df = kis_market_api.get_inquire_price("J", ctx.code)
    if df is None or df.empty:
        return None
    q = clean_row(df.iloc[0].to_dict())
    ctx.jsonl({"kind": "quote", "ts": _ts(ctx), "fields": cp._pick(q, QUOTE_FIELDS + ("hts_kor_isnm",))})
    return q


def _daily_rows(ctx: Ctx) -> Optional[List[Dict[str, Any]]]:
    from api import kis_order_api
    df = kis_order_api.get_inquire_daily_ccld_lst("01", ctx.today, ctx.today)
    if df is None:
        return None
    return [] if df.empty else [clean_row(r) for r in df.to_dict("records")]


def read_holdings(ctx: Ctx) -> Tuple[Optional[Dict[str, int]], Optional[Dict[str, Any]]]:
    """잔고(TTTC8434R) — 봇 get_holdings→get_existing_holdings→get_account_balance 가 부르는 맨 아래 함수
    kis_market_api.get_stock_balance 를 직접 쓴다(윗단은 조회 실패를 [] 로 뭉갠다 = NEW-B2). 실패·해석불가 = None."""
    from api import kis_market_api
    r = kis_market_api.get_stock_balance()
    if r is None:
        ctx.jsonl({"kind": "holdings", "ts": _ts(ctx), "ok": False})
        return None, None
    df, summary = r
    rows = [] if df is None or df.empty else [clean_row(x) for x in df.to_dict("records")]
    held: Dict[str, int] = {}
    bad = False
    for row in rows:
        q = num(row.get("hldg_qty"))
        if q is None:
            bad = True
            continue
        code = _s(row.get("pdno"))
        held[code] = held.get(code, 0) + int(q)
    raw_sum = (summary or {}).get("raw_summary") or {}
    ctx.last_summary = raw_sum or ctx.last_summary
    ctx.jsonl({"kind": "holdings", "ts": _ts(ctx), "ok": not bad, "rows": [cp._pick(x, HOLD_FIELDS) for x in rows],
               "summary": cp._pick(raw_sum, COST_FIELDS_BAL)})
    return (None if bad else held), summary


def held_qty(ctx: Ctx, tries: int = 1,
             until: Optional[Callable[[int, int], bool]] = None) -> Tuple[Optional[int], Optional[int]]:
    """(이 종목 보유, 전체 보유 합). 조회 실패면 재시도 · 끝까지 실패면 (None, None) = 미상."""
    q = tot = None
    for i in range(max(1, tries)):
        held, _ = read_holdings(ctx)
        if held is not None:
            q, tot = held.get(ctx.code, 0), sum(v for v in held.values() if v > 0)
            if until is None or until(q, tot):
                return q, tot
        if i < tries - 1:
            _time.sleep(WAIT_SEC)
    return q, tot


def _psbl_cash(ctx: Ctx, price: float) -> Optional[float]:
    from api import kis_account_api
    if price <= 0:
        return None
    df = kis_account_api.get_inquire_psbl_order(ctx.code, int(price))
    if df is None or df.empty:
        return None
    row = clean_row(df.iloc[0].to_dict())
    ctx.jsonl({"kind": "psbl_order", "ts": _ts(ctx),
               "fields": cp._pick(row, ("ord_psbl_cash", "nrcvb_buy_amt", "nrcvb_buy_qty", "max_buy_amt", "max_buy_qty"))})
    return num(row.get("nrcvb_buy_amt"))


def scan_main_py_processes() -> Optional[List[Dict[str, Any]]]:
    """python …main.py 프로세스 목록(pid·ppid·exe·KIS_INSTANCE_DIR — 환경 못 읽으면 None). 조회 실패 = None."""
    try:
        import psutil
    except ImportError:
        return None
    out: List[Dict[str, Any]] = []
    try:
        for p in psutil.process_iter(["pid", "ppid", "name", "exe", "cmdline"]):
            info = p.info
            cmd = " ".join(info.get("cmdline") or [])
            if "python" not in (info.get("name") or "").lower() or "main.py" not in cmd:
                continue
            try:
                env = p.environ() or {}
                inst: Optional[str] = next((v for k, v in env.items() if k.upper() == "KIS_INSTANCE_DIR"), "")
            except Exception:
                inst = None
            out.append({"pid": info["pid"], "ppid": info.get("ppid"), "exe": info.get("exe") or "",
                        "cmdline": cmd, "inst_dir": inst})
    except Exception:
        return None
    return out


def _real_instance_guard() -> Guard:
    rt = Path(LIVE_RT_ROOT)
    pid_files = [str(p) for p in (rt / "robotrader_daytrading.pid",
                                  rt / "instances" / "daytrading" / "robotrader_daytrading.pid") if p.exists()]
    paper_pid: Optional[int] = None
    try:
        paper_pid = int((rt / "robotrader.pid").read_text().strip())
    except (OSError, ValueError):
        paper_pid = None
    return check_real_instance_off(pid_files, scan_main_py_processes(), paper_pid,
                                   str(rt / "venv" / "Scripts" / "python.exe"))


def poll_once(ctx: Ctx, side: str, phase: str) -> Dict[str, Any]:
    """1회 폴링 = 미체결(TTTC8036R · broker.get_pending_orders) + 당일 주문체결(TTTC0081R · get_inquire_daily_ccld_lst)."""
    r = ctx.rt[side]
    pend = ctx.broker.get_pending_orders()
    drows = _daily_rows(ctx)
    pend = None if pend is None else [clean_row(x) for x in pend]
    if not r["odno"]:                        # 주문 응답에 번호가 없었다 → 새로 생긴 이 종목·방향 원주문을 찾아 채택
        found = new_rows(pend, set(), ctx.code, SIDE_CD[side]) or new_rows(drows, ctx.start_odnos, ctx.code,
                                                                           SIDE_CD[side])
        if found:
            r["odno"], r["adopted"] = _s(found[0].get("odno")), True
            if side == "buy":
                ctx.state.target_odno = r["odno"]
            ctx.log.warning(f"[{side}] 주문 응답에 ODNO 없음 → 조회에서 새 주문 {r['odno']} 채택")
    odno = r["odno"]
    p_hit = cp.find_rows(pend, odno) if odno else new_rows(pend, set(), ctx.code, SIDE_CD[side])
    d_hit = cp.find_rows(drows, odno) if odno else []
    c_rows = [x for x in drows or [] if odno and cp.normalize_odno(x.get("orgn_odno")) == cp.normalize_odno(odno)
              and cp.normalize_odno(x.get("odno")) != cp.normalize_odno(odno)]
    view = bot_view(emulate_get_order_status(pend, drows, odno), QTY, r["bot_price"])
    r["polls"] += 1
    t = round(_time.monotonic() - r["t0"], 2) if r["t0"] is not None else None
    snap = {"kind": "poll", "side": side, "phase": phase, "n": r["polls"], "t": t, "ts": _ts(ctx),
            "pending_ok": pend is not None, "pending_count": None if pend is None else len(pend),
            "in_pending": None if pend is None else bool(p_hit), "daily_ok": drows is not None,
            "pending_row": p_hit[0] if p_hit else None, "daily_row": d_hit[0] if d_hit else None,
            "cancel_rows": c_rows, "bot_view": view,
            "odno_exact_in_daily": bool(odno) and any(x.get("odno") == odno for x in drows or [])}
    ctx.polls.append(snap)
    ctx.jsonl(snap)
    dr = snap["daily_row"]
    if dr is not None and t is not None:
        if is_filled(dr) and r["t_fill"] is None:
            r["t_fill"] = t
        if avg_state(dr) == "값" and r["t_avg"] is None:
            r["t_avg"] = t
    if view["code"] == "FILLED" and r["t_bot"] is None and t is not None:
        r["t_bot"] = t
    tracked = cp._pick(dr, TRACK_FIELDS) if dr is not None else "행 없음"
    ctx.log.info(f"[{side}·{phase} #{r['polls']} +{t}s] 8036R "
                 f"{'조회 실패' if pend is None else ('보임' if p_hit else '없음')}"
                 f"{' ' + str(cp._pick(p_hit[0], PENDING_TRACK)) if p_hit else ''} · 0081R "
                 f"{'조회 실패' if drows is None else tracked} · 봇 판정={view['code']}({view['text']})")
    return snap


def _wait_fill(ctx: Ctx, side: str, wait: float, phase: str = "wait") -> bool:
    """체결 대기. 끝 = 전량 체결 + avg_prvs 유효 + 봇 판정(get_order_status 흉내) «체결 확정».
    매수: 체결 뒤 위 조건이 안 되면 추가 4회까지 · 미체결은 wait 초 또는 15:00 에 중단.
    매도: wait 초까지 계속 관측(체결돼도 avg_prvs 가 빌 때 언제 채워지는지 = P2-14 실측)."""
    r = ctx.rt[side]
    max_polls = int(math.ceil(wait / POLL_SEC)) + EXTRA_POLLS_AFTER_FILL + 1
    n = post = 0
    filled = False
    while True:
        _time.sleep(POLL_SEC)
        snap = poll_once(ctx, side, phase)
        n += 1
        dr = snap["daily_row"]
        if dr is not None and is_filled(dr):
            filled = True
            if avg_state(dr) == "값" and snap["bot_view"]["code"] == "FILLED":   # 봇 판정까지 «체결 확정»이면 끝
                break
            post += 1
            if side == "buy" and post > EXTRA_POLLS_AFTER_FILL:
                break
        elapsed = _time.monotonic() - r["t0"]
        if side == "buy" and not filled and ctx.now().time() >= BUY_HARD_STOP:
            ctx.log.warning(f"매수 체결 대기 중 {BUY_HARD_STOP:%H:%M} 도달 → 대기 중단(취소 경로)")
            break
        if (elapsed >= wait and (side == "sell" or not filled)) or n >= max_polls:
            break
    return filled


def _final_snapshot(ctx: Ctx, tries: int = 1) -> Tuple[Optional[int], Optional[int], Optional[int],
                                                       Optional[float], Optional[float]]:
    """종료 시점 기록: (이 종목 보유, 전체 보유, 미체결 수, 당일 새 주문 매수 체결 합, 매도 체결 합). 미상 = None."""
    held, total = held_qty(ctx, tries=tries, until=lambda q, t: q == 0 and t == 0)
    pend = ctx.broker.get_pending_orders()
    rows = _daily_rows(ctx)

    def _sum(side: str) -> Optional[float]:
        if rows is None:
            return None
        tot = sum(num(x.get("tot_ccld_qty")) or 0 for x in new_rows(rows, ctx.start_odnos, ctx.code, SIDE_CD[side]))
        return int(tot) if float(tot).is_integer() else tot

    buys, sells = _sum("buy"), _sum("sell")
    npend = None if pend is None else len(pend)
    ctx.res.update({"end_holding_qty": held, "end_holding_total": total, "end_pending_count": npend,
                    "end_daily_new_buy_filled": buys, "end_daily_new_sell_filled": sells})
    ctx.jsonl({"kind": "final", "ts": _ts(ctx), "held": held, "held_total": total, "pending": pend,
               "daily_new_buy_filled": buys, "daily_new_sell_filled": sells})
    ctx.log.info(f"── 종료 상태: 보유 {held}(전체 {total}) · 미체결 {npend} · 당일 새 주문 체결 매수 {buys} · 매도 {sells}")
    return held, total, npend, buys, sells


# ---------------------------------------------------------------------------
# 흐름
# ---------------------------------------------------------------------------
def _record_guards(ctx: Ctx, title: str, guards: List[Guard]) -> bool:
    cp._print_guards(ctx.log, title, guards)
    ctx.guard_groups.append((title, list(guards)))
    failed = [n for n, ok, _ in guards if not ok]
    ctx.res["guards_failed"] += failed
    ctx.jsonl({"kind": "guards", "title": title, "guards": [{"name": n, "ok": ok, "detail": d} for n, ok, d in guards]})
    return not failed


def _preflight(ctx: Ctx) -> List[Guard]:
    """live 가드용 조회(읽기 TR 만): 현재가 · 미체결 · 잔고 · 매수가능 · 당일 주문체결 스냅샷 · 장 상태."""
    from config.market_hours import MarketHours
    from utils.korean_holidays import is_holiday
    now = ctx.now()
    ctx.today = now.strftime("%Y%m%d")
    guards: List[Guard] = []
    q = _quote(ctx)
    if q is None:
        guards.append(("현재가 조회 성공", False, "get_inquire_price 실패"))
        q = {}
    ctx.quote = q
    ctx.res["stock_name"] = _s(q.get("hts_kor_isnm")) or None
    cur = num(q.get("stck_prpr")) or 0.0
    ctx.log.info(f"── 시세 {ctx.code}({ctx.res['stock_name']}): {cp._pick(q, QUOTE_FIELDS)}")
    pending0 = ctx.broker.get_pending_orders()
    ctx.log.info(f"── 시작 시 미체결: {'조회 실패(None)' if pending0 is None else f'{len(pending0)}건'}")
    held, summary = read_holdings(ctx)
    bot_avail = num((summary or {}).get("prvs_rcdl_excc_amt")) if summary else None
    nrcvb = _psbl_cash(ctx, cur)
    ctx.cash = (bot_avail, nrcvb)
    rows = _daily_rows(ctx)
    ctx.start_odnos = {cp.normalize_odno(r.get("odno")) for r in rows or []}
    ctx.log.info(f"── 시작 시 잔고 {held} · 당일 주문체결 {'조회 실패' if rows is None else f'{len(rows)}행'}")
    guards.append(check_trading_day_open(MarketHours.get_market_status("KRX", now), is_holiday(now),
                                         cp._read_live_holiday_cache(ctx.inst_dir, now),
                                         MarketHours.can_place_order(ctx.code, "KRX", now)))
    guards.append(check_time_window(now))
    guards += check_quote(q, ctx.args.max_price)
    guards.append(check_cash(bot_avail, nrcvb, cur))
    guards.append(("수량 = 1 고정", QTY == 1, f"QTY={QTY}"))
    guards.append(cp.check_no_pending(pending0))
    guards.append(check_no_holdings(held))
    guards.append(("당일 주문체결조회(TTTC0081R) 성공", rows is not None, "새 주문 행 구분용 시작 스냅샷"))
    return guards


def _after_connect(ctx: Ctx) -> int:
    ok = _record_guards(ctx, "live 가드", _preflight(ctx))
    ctx.res["guards_all_pass"] = not ctx.res["guards_failed"]
    cur = num(ctx.quote.get("stck_prpr")) or 0
    ctx.log.info(f"── 계획: {ctx.code}({ctx.res['stock_name']}) 현재가 지정가 매수 {QTY}주 @ 주문 직전 현재가(지금 {cur:,.0f}) "
                 f"→ 최대 {ctx.args.fill_wait}초 체결 대기 → (미체결이면 취소) → 시장가 매도 {QTY}주 → 종료 확인")
    if not ctx.args.live:
        sent = _sent_orders(ctx)
        if sent:
            ctx.crit(f"**🔴 DRY-RUN 인데 주문·취소 TR {len(sent)}건 전송 — HTS 즉시 확인**")
            ctx.res["verdict"] = "CRITICAL — dry-run 인데 주문 TR 전송 · HTS 즉시 확인"
            return 4
        ctx.res["verdict"] = ("DRY-RUN — 주문·취소 TR 0건 · live 가드 "
                              + ("전부 통과" if ok else f"FAIL {ctx.res['guards_failed']}"))
        return 0
    if not ok:
        ctx.res["verdict"] = f"가드 FAIL — 주문 0건: {ctx.res['guards_failed']}"
        return 2
    return _run_live(ctx)


def _sent_orders(ctx: Ctx) -> List[Dict[str, Any]]:
    if ctx.gate is None:
        return []
    return [c for c in ctx.gate.calls if c.get("path") in cp.ORDER_PATHS and not c.get("blocked")]


def _run_live(ctx: Ctx) -> int:
    try:
        return _live_flow(ctx)
    except BaseException as e:   # Ctrl+C 포함
        if not ctx.order_touched():
            raise                # 주문 TR 0건 → execute() 가 exit 1 로 정리
        return _emergency_unwind(ctx, e)


def _live_flow(ctx: Ctx) -> int:
    log, st, code = ctx.log, ctx.state, ctx.code
    # 0) 주문 직전 재확인(시간창 · 현재가 재조회 · 가격/표식/현금)
    w = check_time_window(ctx.now())
    q2 = _quote(ctx)
    g2 = [w] + (check_quote(q2, ctx.args.max_price) if q2 else [("주문 직전 현재가 재조회", False, "조회 실패")])
    price = int(num((q2 or {}).get("stck_prpr")) or 0)
    g2.append(check_cash(ctx.cash[0], ctx.cash[1], price))
    if not _record_guards(ctx, "주문 직전 재확인", g2):
        ctx.res["guards_all_pass"] = False
        ctx.res["verdict"] = f"주문 직전 재확인 FAIL — 주문 0건: {[n for n, ok, _ in g2 if not ok]}"
        return 2
    # ① 매수 — 봇과 같은 함수(KISBroker.place_buy_order → get_order_cash("buy", …, "00") = TTTC0012U 지정가)
    b = ctx.rt["buy"]
    b["bot_price"] = float(price)
    ctx.res["buy"]["order_price"] = price
    st.planned_buy = {"PDNO": code, "ORD_QTY": str(QTY), "ORD_UNPR": str(price), "ORD_DVSN": "00"}
    log.info(f"① 매수: {code} 지정가 {QTY}주 @ {price:,}원(주문 직전 현재가)")
    b["t0"], b["sent_at"] = _time.monotonic(), _ts(ctx)
    order = ctx.broker.place_buy_order(code, QTY, price)
    b["response"] = order
    b["odno"] = _s(order.get("order_id"))
    st.target_odno = b["odno"]
    log.info(f"① 매수 반환: {ctx.masker.obj(order)}")
    if st.buy_calls == 0:
        ctx.res["verdict"] = "매수 TR 미전송(봇 함수가 HTTP 전에 거부했거나 게이트 차단) — 주문 0건"
        log.error(ctx.res["verdict"])
        return 2
    # ② 체결 대기
    if not _wait_fill(ctx, "buy", ctx.args.fill_wait):
        out = _cancel_buy_and_settle(ctx)
        if out == "unfilled_clear":
            ctx.res["verdict"] = "매수 미체결로 끝남(취소 또는 접수 거부) · 보유 0 · 미체결 0 확인 — 재시도 가능"
            return 3
        if out != "held":
            ctx.res["verdict"] = f"CRITICAL — 매수 정리 확인 실패({out}) · HTS 즉시 확인"
            _final_snapshot(ctx)
            return 4
    ctx.buy_closed = True
    ctx.res["buy"]["filled"] = True
    return _sell_and_verify(ctx)


def _cancel_buy_and_settle(ctx: Ctx) -> str:
    """미체결 매수 취소 → 재조회. 반환: unfilled_clear(보유 0·미체결 0) · held(경합 체결 → 매도로) ·
    remain(매수 잔존) · unknown(미상) · unexpected(보유 > 1)."""
    b, rb, log = ctx.rt["buy"], ctx.res["buy"], ctx.log
    snap: Optional[Dict[str, Any]] = None
    for attempt in (1, 2):
        if not b["odno"]:
            _time.sleep(WAIT_SEC)
            snap = poll_once(ctx, "buy", "cancel")           # 번호 채택 기회
            if not b["odno"]:
                log.warning("매수 주문번호 없음 · 조회에도 새 매수 주문 없음 → 취소 생략")
                break
        n0 = len(ctx.gate.calls)
        c = ctx.broker.cancel_order(b["odno"], ctx.code)
        raw = ctx.gate.last(cp.TR_CANCEL, since=n0)
        rb["cancel_tried"] = True
        rb["cancels"].append({"attempt": attempt, "success": c.get("success"), "message": c.get("message"),
                              "raw_rt_cd": raw.get("rt_cd") if raw else "미전송",
                              "raw_msg1": raw.get("msg1") if raw else None})
        log.info(f"③ {attempt}차 cancel_order 반환(판정에 쓰지 않음 · NEW-B1): {ctx.masker.obj(c)} · 취소 TR 원응답 "
                 f"rt_cd={(raw or {}).get('rt_cd', '미전송')}")
        _time.sleep(WAIT_SEC)
        snap = poll_once(ctx, "buy", "cancel")
        if snap["in_pending"] is False:
            break
    remain = snap["in_pending"] if snap else None
    dr = snap["daily_row"] if snap else None
    if dr is not None:
        filled: Optional[bool] = is_filled(dr)
    elif snap and snap["daily_ok"] and not b["odno"]:
        filled = False                                       # 접수 자체가 안 됨(새 주문 행 없음)
    else:
        filled = None
    held, total = held_qty(ctx, tries=3, until=(lambda q, t: q >= 1) if filled else None)
    pcount = snap["pending_count"] if snap else None
    ctx.res.update({"end_holding_qty": held, "end_holding_total": total, "end_pending_count": pcount})
    log.info(f"④ 취소 뒤: 매수 잔존={remain} · 당일조회 체결={filled} · 보유 {held}(전체 {total}) · 미체결 {pcount}")
    if held is None:
        ctx.crit(f"**🔴 잔고 조회 실패 — 매수 체결·보유 미상 · HTS 즉시 확인 · 종목 {ctx.code} · ODNO {b['odno'] or '미상'}**")
        return "unknown"
    if held >= 1:
        if held > QTY:
            ctx.crit(f"**🔴 보유 {held}주 > {QTY} — 이 시험 밖 보유 · 손대지 않음 · HTS 즉시 확인**")
            return "unexpected"
        log.warning("취소와 체결이 경합 — 결국 보유 1주 → 시장가 매도로 진행")
        rb["filled"] = True
        return "held"
    if remain is True:
        ctx.crit(f"**🔴 매수 미체결 잔존(취소 2회 뒤) — HTS 에서 즉시 수동 취소 · ODNO {b['odno']} · 종목 {ctx.code}**")
        return "remain"
    if remain is None:
        ctx.crit(f"**🔴 미체결 조회 실패 — 매수 잔존 미상 · HTS 즉시 확인 · ODNO {b['odno'] or '미상'}**")
        return "unknown"
    if filled is None:
        ctx.crit(f"**🔴 당일 주문체결조회로 «체결 0» 을 확인 못 함(미상) — HTS 즉시 확인 · ODNO {b['odno'] or '미상'}**")
        return "unknown"
    if filled:
        ctx.crit("**🔴 당일조회는 체결인데 잔고는 0 — 불일치 · HTS 즉시 확인**")
        return "unknown"
    if dr is not None and (num(dr.get("rmn_qty")) or 0) > 0 and not cancel_evidence(dr, snap["cancel_rows"]):
        ctx.crit(f"**🔴 당일조회 원주문 잔량>0 · 취소 흔적 없음 — HTS 즉시 확인·취소 · ODNO {b['odno']}**")
        return "remain"
    if pcount != 0 or total != 0:
        ctx.crit(f"**🔴 매수는 정리됐지만 계좌 미체결 {pcount} · 전체 보유 {total} — HTS 즉시 확인**")
        return "unknown"
    rb["filled"] = False
    ctx.buy_closed = True
    return "unfilled_clear"


def _place_market_sell(ctx: Ctx, qty: int, emergency: bool) -> bool:
    """봇 실전 시장가 매도와 같은 경로: KISBroker.place_sell_order(code, qty, 0, "01") → TTTC0011U ORD_DVSN 01 · 0원.
    반환 = 매도 HTTP 가 실제로 나갔는가(응답 성공 여부와 무관)."""
    s = ctx.rt["sell"]
    ctx.state.planned_sell = {"PDNO": ctx.code, "ORD_QTY": str(qty), "ORD_UNPR": "0", "ORD_DVSN": "01"}
    s["t0"], s["sent_at"], s["bot_price"] = _time.monotonic(), _ts(ctx), 0.0
    if emergency:
        ctx.res["emergency_sell_tried"] = True
    before = ctx.state.sell_calls
    r = ctx.broker.place_sell_order(ctx.code, qty, 0, "01")
    s["response"] = r
    s["odno"] = _s((r or {}).get("order_id"))
    ctx.log.info(f"{'🔴 비상 ' if emergency else '⑤ '}시장가 매도 반환: {ctx.masker.obj(r)}")
    return ctx.state.sell_calls > before


def _sell_and_verify(ctx: Ctx) -> int:
    held, total = held_qty(ctx, tries=3, until=lambda q, t: q >= 1)
    ctx.res["holding_after_buy"] = held
    ctx.log.info(f"── 매수 체결 뒤 잔고(TTTC8434R): 이 종목 {held} · 전체 {total}")
    if held is None:
        ctx.crit(f"**🔴 매도 전 잔고 조회 실패 — 보유 미상 → 매도 안 함(공매도 위험) · HTS 즉시 확인·매도 · 종목 {ctx.code}**")
        _final_snapshot(ctx)
        return 4
    if held != QTY:
        ctx.crit(f"**🔴 매수 체결 뒤 보유 {held}주(기대 {QTY}) — 매도 안 함 · HTS 즉시 확인 · 종목 {ctx.code}**")
        _final_snapshot(ctx)
        return 4
    if ctx.state.sell_calls:
        ctx.crit("**🔴 매도가 이미 전송된 상태 — 재매도 안 함 · HTS 즉시 확인**")
        _final_snapshot(ctx)
        return 4
    if not _place_market_sell(ctx, held, emergency=False):
        ctx.crit(f"**🔴 매도 TR 미전송 — 보유 {held}주 남음 · HTS 에서 즉시 매도 · 종목 {ctx.code}**")
        _final_snapshot(ctx)
        return 4
    _wait_fill(ctx, "sell", SELL_WAIT)
    return _final_verify(ctx)


def _final_verify(ctx: Ctx) -> int:
    _time.sleep(WAIT_SEC)
    held, total, npend, buys, sells = _final_snapshot(ctx, tries=4)
    if held == 0 and total == 0 and npend == 0 and buys == QTY and sells == QTY:
        ctx.res["verdict"] = "정상 — 매수 체결 → 시장가 매도 체결 → 보유 0 · 미체결 0 · 당일 매수 1·매도 1 확인"
        return 0
    ctx.crit(f"**🔴 종료 확인 불일치 — 보유 {held}(전체 {total}) · 미체결 {npend} · 당일 새 주문 체결 매수 {buys}·"
             f"매도 {sells} → HTS 즉시 확인 · 종목 {ctx.code}**")
    ctx.res["verdict"] = "CRITICAL — 종료 확인 불일치(보유·미체결 잔존 또는 미상) · HTS 즉시 확인"
    return 4


def _find_pending_buy(ctx: Ctx) -> str:
    pend = ctx.broker.get_pending_orders()
    rows = new_rows(pend, set(), ctx.code, SIDE_CD["buy"])
    return _s(rows[0].get("odno")) if rows else ""


def _emergency_unwind(ctx: Ctx, exc: BaseException) -> int:
    """비상 처리: ① 미체결 매수 취소 → ② 잔고 재조회 → ③ 보유 1 이고 매도 미전송이면 시장가 매도 1회 → ④ 짧은 관측.
    단계마다 따로 보호(두 번째 Ctrl+C 가 와도 다음 단계로). 반환은 항상 4."""
    ctx.emergency_done = True
    em: Dict[str, Any] = {"reason": f"{type(exc).__name__}: {exc}", "buy_cancel": None, "held_before_sell": None,
                          "sell": None}
    ctx.res["emergency"] = em
    ctx.crit(f"**🔴 예외로 중단({type(exc).__name__}: {exc}) — 비상 처리(미체결 매수 취소 → 잔고 재조회 → 보유분 시장가 매도 1회)**")
    try:
        if ctx.state.buy_calls and not ctx.buy_closed:
            odno = ctx.rt["buy"]["odno"] or _find_pending_buy(ctx)
            if odno:
                ctx.rt["buy"]["odno"] = ctx.state.target_odno = odno
                c = ctx.broker.cancel_order(odno, ctx.code)
                ctx.res["buy"]["cancel_tried"] = True
                em["buy_cancel"] = {"odno": odno, "success": c.get("success"), "message": c.get("message")}
                ctx.crit(f"비상 매수 취소 1회 시도 — ODNO {odno} · 반환(성공 여부는 재조회·HTS 로) {ctx.masker.obj(c)}")
                _time.sleep(WAIT_SEC)
            else:
                em["buy_cancel"] = "주문번호 미상 · 미체결 목록에도 없음 → 취소 생략"
    except BaseException as e2:
        ctx.crit(f"비상 매수 취소 중 예외 {type(e2).__name__}: {e2}")
    try:
        if ctx.state.sell_calls:
            em["sell"] = "매도 이미 전송 → 재매도 안 함"
            ctx.crit("매도 주문이 이미 전송됨 → 재매도 안 함(이중 매도 = 공매도 시도 방지)")
        else:
            held, _ = held_qty(ctx, tries=3)
            em["held_before_sell"] = held
            if held is None:
                ctx.crit(f"**🔴 잔고 조회 실패 → 보유 미상 → 매도 안 함(공매도 위험) · HTS 에서 {ctx.code} 보유 확인·매도**")
            elif held == 0:
                ctx.log.warning("비상: 이 종목 보유 0 → 매도 불필요")
            elif held != QTY:
                ctx.crit(f"**🔴 보유 {held}주 ≠ {QTY} → 손대지 않음 · HTS 즉시 확인**")
            else:
                sent = _place_market_sell(ctx, held, emergency=True)
                r = ctx.rt["sell"]["response"] or {}
                em["sell"] = {"sent": sent, "odno": ctx.rt["sell"]["odno"], "success": r.get("success"),
                              "message": r.get("message")}
                ctx.crit(f"비상 시장가 매도 1회 시도 — HTTP 전송={sent} · ODNO {ctx.rt['sell']['odno'] or '없음'}")
    except BaseException as e3:
        ctx.crit(f"비상 매도 단계 예외 {type(e3).__name__}: {e3}")
    try:
        if ctx.state.sell_calls and ctx.rt["sell"]["t0"] is not None:
            _wait_fill(ctx, "sell", EMERGENCY_SELL_WAIT, phase="emergency")
        _final_snapshot(ctx, tries=2)
    except BaseException as e4:
        ctx.crit(f"비상 종료 상태 조회 중 예외 {type(e4).__name__}: {e4}")
    ctx.crit(f"**🔴 HTS 에서 즉시 확인 — 종목 {ctx.code} 보유·미체결 (매수 ODNO {ctx.rt['buy']['odno'] or '미상'} · "
             f"매도 ODNO {ctx.rt['sell']['odno'] or '없음'})**")
    ctx.res["verdict"] = f"CRITICAL — 비상 처리 경로({type(exc).__name__}) · HTS 즉시 확인"
    return 4


# ---------------------------------------------------------------------------
# 종결 — 결과 json · 요약 md
# ---------------------------------------------------------------------------
DEFAULT_VERDICT = {0: "정상", 1: "예외 종료 — 주문·취소 TR 0건(계좌 영향 없음)", 2: "필수 전제·가드 FAIL — 주문 0건",
                   3: "매수 미체결로 끝남 — 재시도 가능", 4: "CRITICAL — HTS 즉시 확인"}


def _fill_side_result(ctx: Ctx, side: str) -> None:
    r, o = ctx.rt[side], ctx.res[side]
    o["odno"], o["odno_adopted"] = r["odno"], r["adopted"]
    st = ctx.state
    o["sent"] = bool(st and (st.buy_calls if side == "buy" else st.sell_calls))
    polls = [p for p in ctx.polls if p["side"] == side]
    rows = [p["daily_row"] for p in polls if p["daily_row"] is not None]
    frows = [x for x in rows if is_filled(x)]
    if frows:
        o["filled"] = True
    elif side == "sell" and o["sent"] and rows and is_filled(rows[-1]) is False:
        o["filled"] = False          # 마지막 관측 시점 미체결(매수의 False 는 취소 정리 확인 때만 흐름이 직접 넣는다)
    last = frows[-1] if frows else (rows[-1] if rows else None)
    o["fill_price"], o["fill_price_source"] = fill_price(frows[-1]) if frows else (None, None)
    o["implied_price"] = implied_price(last)
    a = num(last.get("avg_prvs")) if last is not None and avg_state(last) == "값" else None
    o["avg_matches_implied"] = (abs(a - o["implied_price"]) < 0.5) if a is not None and o["implied_price"] else None
    o["fill_latency_sec"], o["avg_prvs_first_valid_sec"], o["bot_fill_confirm_sec"] = r["t_fill"], r["t_avg"], r["t_bot"]
    o["avg_prvs_rule"] = avg_rule(polls)[0] if polls else None
    o["bot_view_last"] = polls[-1]["bot_view"] if polls else None
    if side == "sell":
        p2 = [p for p in polls if p["bot_view"]["code"] == "P2-14"]
        o["p2_14_polls"] = len(p2)
        o["p2_14_condition"] = True if p2 else (False if frows else None)


def finish(ctx: Ctx, rc: int) -> None:
    """모든 종결 경로에서 호출(execute 의 finally). 결과 json 은 반드시 쓴다 — 실패해도 예외를 밖으로 내지 않는다."""
    res = ctx.res
    res["exit_code"] = rc
    res["verdict"] = res["verdict"] or DEFAULT_VERDICT.get(rc, "?")
    res["ended_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        for side in ("buy", "sell"):
            _fill_side_result(ctx, side)
        res["order_http"] = [{"seq": c["seq"], "ts": c["ts"], "tr_id": c["tr_id"], "rt_cd": c.get("rt_cd"),
                              "msg_cd": c.get("msg_cd"), "msg1": c.get("msg1"), "exception": c.get("exception")}
                             for c in _sent_orders(ctx)]
    except Exception as e:
        res["result_build_error"] = f"{type(e).__name__}: {e}"
    try:
        Path(ctx.paths["summary_md"]).write_text(ctx.masker.text(build_summary_md(ctx)), encoding="utf-8")
    except Exception as e:
        res["summary_md_error"] = f"{type(e).__name__}: {e}"
    try:
        write_result(ctx.paths["result"], ctx.masker.obj(res))
    except Exception as e:
        ctx.log.error(f"결과 json 쓰기 실패 {type(e).__name__}: {e}")
    lvl = logging.CRITICAL if rc == 4 else logging.INFO
    ctx.log.log(lvl, f"===== 종료 exit={rc} · {res['verdict']} · 결과 {ctx.paths['result']} =====")


def write_result(path: str, payload: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, p)


def _cell(v: Any) -> str:
    return "—" if v is None else repr(v)


def _side_table(polls: List[Dict[str, Any]]) -> List[str]:
    head = ("| 단계 | # | +초 | 시각 | 8036R | " + " | ".join(TRACK_FIELDS[:8]) + " | 역산 | 봇 판정 |")
    out = [head, "|" + "---|" * (len(TRACK_FIELDS[:8]) + 7)]
    for p in polls:
        dr = p["daily_row"]
        pend = "실패" if not p["pending_ok"] else ("보임" if p["in_pending"] else "없음")
        cells = [(_cell(dr.get(k)) if k in dr else "(없음)") if dr is not None else "·" for k in TRACK_FIELDS[:8]]
        ip = implied_price(dr)
        out.append(f"| {p['phase']} | {p['n']} | {p['t']} | {p['ts']} | {pend} | " + " | ".join(cells)
                   + f" | {'' if ip is None else f'{ip:,.2f}'} | {p['bot_view']['code']} |")
    return out


def build_summary_md(ctx: Ctx) -> str:
    res = ctx.res
    b, s = res["buy"], res["sell"]
    L = [f"# 실전 1주 체결 시험 요약 — {res['code']}({res['stock_name']}) · {res['mode']}", "",
         f"- exit **{res['exit_code']}** — {res['verdict']}",
         f"- 시작 {res['started_at']} · 종료 {res['ended_at']}",
         f"- 파일: log `{ctx.paths['log']}` · jsonl `{ctx.paths['jsonl']}` · result `{ctx.paths['result']}`", ""]
    L.append("## 판정 줄")
    L.append(f"- 「avg_prvs 채움 규칙」 매도(시장가): {s['avg_prvs_rule'] or '관측 없음'}")
    L.append(f"- 「avg_prvs 채움 규칙」 매수(지정가): {b['avg_prvs_rule'] or '관측 없음'}")
    p2 = s["p2_14_condition"]
    L.append("- 「P2-14 진입 조건 발생 여부」: " + (
        f"**발생** — 매도 전량체결 행인데 avg_prvs 빈값/'0' 인 폴링 {s['p2_14_polls']}회(봇이면 «체결가 비정상(0원) 보류»)"
        if p2 else ("미발생 — 매도 체결 행 전부 avg_prvs > 0" if p2 is False else "미상 — 매도 체결 행을 못 봄")))
    L.append(f"- 역산(tot_ccld_amt/tot_ccld_qty) vs avg_prvs: 매수 {b['implied_price']} / 일치 {b['avg_matches_implied']} · "
             f"매도 {s['implied_price']} / 일치 {s['avg_matches_implied']}")
    L.append("")
    L.append("## 매수 · 매도")
    for name, o, r in (("매수(지정가 00)", b, ctx.rt["buy"]), ("매도(시장가 01)", s, ctx.rt["sell"])):
        L.append(f"- {name}: 전송 {o['sent']} · ODNO {o['odno'] or '-'}{' (조회에서 채택)' if o['odno_adopted'] else ''} · "
                 f"주문가 {o['order_price']} · 주문 시각 {r['sent_at'] or '-'} · 체결 {o['filled']} · 체결가 {o['fill_price']}"
                 f"({o['fill_price_source']}) · 주문→체결 확인 {o['fill_latency_sec']}s · avg_prvs 첫 유효 "
                 f"{o['avg_prvs_first_valid_sec']}s · 마지막 봇 판정 {(o['bot_view_last'] or {}).get('text')}")
    if b.get("cancels"):
        L.append(f"- 매수 취소: {b['cancels']}")
    L.append(f"- 매수 체결 뒤 보유(TTTC8434R) {res['holding_after_buy']} · 종료 보유 {res['end_holding_qty']}"
             f"(전체 {res['end_holding_total']}) · 미체결 {res['end_pending_count']} · 당일 새 주문 체결 매수 "
             f"{res['end_daily_new_buy_filled']} · 매도 {res['end_daily_new_sell_filled']}")
    L.append(f"- 비상 매도 시도 {res['emergency_sell_tried']} · 비상 처리 {res['emergency']}")
    L.append("")
    L.append("## 비용(응답에 있는 값 그대로 · 하루 합계일 수 있음)")
    bp, sp = b["fill_price"], s["fill_price"]
    L.append(f"- 매수 체결가 {bp} · 매도 체결가 {sp} · 차이 {None if bp is None or sp is None else round(sp - bp, 2)}원/주")
    L.append(f"- 잔고 요약(TTTC8434R output2): {cp._pick(ctx.last_summary or {}, COST_FIELDS_BAL)}")
    out2 = ctx.gate.last_body("TTTC0081R") if ctx.gate else None
    o2 = (out2 or {}).get("output2")
    o2 = o2[0] if isinstance(o2, list) and o2 else o2
    L.append(f"- 당일 주문체결 요약(TTTC0081R output2): {cp._pick(o2, COST_FIELDS_DAILY) if isinstance(o2, dict) else o2}")
    keys = sorted({k for p in ctx.polls if p["daily_row"] for k in p["daily_row"]})
    L.append(f"- 0081R output1 에서 본 필드 키({len(keys)}): {keys}")
    L.append(f"- `ccld_unpr` 키 존재: {'ccld_unpr' in keys} (없으면 봇 order_monitor 의 ccld_unpr 대체 경로는 죽은 코드)")
    L.append("")
    for name, side in (("매수", "buy"), ("매도", "sell")):
        polls = [p for p in ctx.polls if p["side"] == side]
        L.append(f"## {name} 폴링 필드 표(값은 문자열 그대로 · '·' = 행 없음 · '(없음)' = 키 없음) — {len(polls)}회")
        L += _side_table(polls) if polls else ["(폴링 없음)"]
        L.append("")
    L.append("## 가드")
    for title, gs in ctx.guard_groups:
        L.append(f"### {title}")
        L += [f"- [{'PASS' if ok else 'FAIL'}] {n} — {d}" for n, ok, d in gs]
    if not ctx.guard_groups:
        L.append("(가드 평가 전 종료)")
    L.append("")
    L.append("## CRITICAL")
    L += [f"- {m}" for m in res["critical"]] or ["(없음)"]
    L.append("")
    L.append("## 사람이 할 일")
    if res["exit_code"] == 4:
        L.append(f"- 🔴 **HTS 에서 즉시 {res['code']} 보유·미체결 확인 → 보유 있으면 매도 · 미체결 있으면 취소** (10-19 기동 대사 abort 방지)")
    L.append("- HTS 체결내역과 위 체결가·수량 대조 · 체크리스트 §4-C 에 avg_prvs 규칙 · P2-14 판정 · 이 파일 경로 기록")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# 진입
# ---------------------------------------------------------------------------
def run(ctx: Ctx) -> int:
    from config import settings
    ctx.masker.add(settings.APP_KEY, settings.SECRET_KEY, settings.ACCOUNT_NUMBER,
                   (settings.ACCOUNT_NUMBER or "")[:8], settings.HTS_ID)
    import api.kis_auth as kis_auth
    log = ctx.log
    log.info(f"===== real_order_fill_probe [{'LIVE' if ctx.args.live else 'DRY-RUN'}] code={ctx.code} qty={QTY} "
             f"max_price={ctx.args.max_price:,} fill_wait={ctx.args.fill_wait}s =====")
    log.info(f"cwd={_cwd()} · KIS_INSTANCE_DIR={ctx.inst_dir} · INSTANCE_ID={settings.INSTANCE_ID}")
    tok = Path(kis_auth.TOKEN_FILE_PATH)
    log.info(f"토큰 캐시 = {tok} (이미 있음={tok.exists()}) — 없거나 만료면 auth() 가 새로 발급해 이 경로에 저장")
    ctx.state = FillGateState(live=ctx.args.live)
    original = kis_auth.requests
    ctx.gate = FillHttpGate(original, ctx.state, urlparse(settings.KIS_BASE_URL).netloc, log, ctx.raw, ctx.masker)
    kis_auth.requests = ctx.gate
    ctx.restore.append(lambda: setattr(kis_auth, "requests", original))

    pre = ([cp.check_cwd(_cwd())] + cp.check_instance(settings.INSTANCE_ID, settings.CONFIG_FILE.exists(),
                                                     settings.KIS_BASE_URL) + [_real_instance_guard()])
    if not _record_guards(ctx, "필수 전제(KIS 호출 전)", pre):
        ctx.res["guards_all_pass"] = False
        ctx.res["verdict"] = f"필수 전제 FAIL — KIS 호출 없이 종료: {ctx.res['guards_failed']}"
        return 2
    cfg = settings.load_trading_config()
    log.info(f"trading_config = {settings.LAST_LOADED_TRADING_CONFIG_PATH}")
    if not _record_guards(ctx, "실전 설정", cp.check_real_mode(settings.LAST_TRADING_CONFIG_LOAD_OK,
                                                           getattr(cfg, "paper_trading", None))):
        ctx.res["guards_all_pass"] = False
        if ctx.args.live:
            ctx.res["verdict"] = f"실전 설정 FAIL — 주문 0건: {ctx.res['guards_failed']}"
            return 2
    from framework.broker import KISBroker
    ctx.broker = KISBroker()
    if not asyncio.run(ctx.broker.connect()):
        ctx.res["verdict"] = "broker.connect() 실패 — 주문 0건"
        log.error(ctx.res["verdict"])
        return 2
    env = kis_auth.getTREnv()
    if env is not None:
        ctx.masker.add(env.my_token, str(env.my_token).replace("Bearer ", ""), env.my_acct)
    return _after_connect(ctx)


def execute(ctx: Ctx, fn: Callable[[Ctx], int]) -> int:
    """main 과 테스트가 함께 쓰는 종결 틀: 어떤 경로로 끝나도 finish(결과 json · 요약 md)를 부른다."""
    rc = 1
    try:
        rc = fn(ctx)
    except BaseException as e:   # Ctrl+C 포함
        if ctx.order_touched():
            if not ctx.emergency_done:
                rc = _emergency_unwind(ctx, e)
            else:
                rc = 4
        else:
            ctx.log.error(f"예외로 종료(주문·취소 TR 0건): {type(e).__name__}: {e}")
            ctx.res["verdict"] = f"예외 종료 — 주문·취소 TR 0건(계좌 영향 없음): {type(e).__name__}: {e}"
            rc = 1
    finally:
        finish(ctx, rc)
    return rc


def _cwd() -> Path:
    return Path.cwd()


def _paths(out_dir: Path, stamp: str) -> Dict[str, str]:
    return {"log": str(out_dir / f"fill_probe_{stamp}.log"), "jsonl": str(out_dir / f"fill_probe_{stamp}.jsonl"),
            "summary_md": str(out_dir / f"fill_probe_{stamp}_summary.md"),
            "result": str(out_dir / f"result_{stamp}.json")}


def _setup_logging(paths: Dict[str, str], masker: Any) -> Tuple[logging.Logger, logging.Logger, Callable[[], None]]:
    fmt = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    flt = cp._MaskFilter(masker)
    fh = logging.FileHandler(paths["log"], encoding="utf-8")
    ch = logging.StreamHandler(sys.stdout)
    jh = logging.FileHandler(paths["jsonl"], encoding="utf-8")
    for h in (fh, ch):
        h.setFormatter(fmt)
        h.addFilter(flt)
    jh.setFormatter(logging.Formatter("%(message)s"))
    jh.addFilter(flt)
    # 봇 로거(utils.logger 싱글톤)가 cwd 의 logs/<id>/ 대신 이 파일·콘솔을 쓰게 한다.
    import utils.logger as ulog
    saved = (ulog._shared_file_handler, ulog._shared_console_handler, ulog._shared_file_path)
    ulog._shared_file_handler, ulog._shared_console_handler, ulog._shared_file_path = fh, ch, paths["log"]
    root = logging.getLogger()
    root_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)
    log, raw = logging.getLogger("fill_probe"), logging.getLogger("fill_probe.raw")
    for lg, hs in ((log, (fh, ch)), (raw, (jh,))):
        lg.setLevel(logging.INFO)
        lg.propagate = False
        lg.handlers = list(hs)

    def teardown() -> None:
        ulog._shared_file_handler, ulog._shared_console_handler, ulog._shared_file_path = saved
        root.removeHandler(fh)
        root.removeHandler(ch)
        root.setLevel(root_level)
        for lg in (log, raw):
            lg.handlers = []
        for h in (fh, jh):
            h.close()

    return log, raw, teardown


def _lenient_out_dir(argv: Optional[List[str]]) -> Path:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    a, _ = p.parse_known_args(argv)
    return Path(a.out_dir)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="실전 1주 체결 1회성 시험(§4-C). 기본 dry-run. exit 코드표는 모듈 docstring 맨 위.")
    p.add_argument("--code", required=True, help="종목코드 6자리(필수 · 기본값 없음)")
    p.add_argument("--live", action="store_true", help="실제 주문(가드 전부 통과 시에만)")
    p.add_argument("--max-price", type=int, default=DEFAULT_MAX_PRICE,
                   help=f"현재가 상한(원 · 기본 {DEFAULT_MAX_PRICE:,} · 최대 {MAX_PRICE_CEILING:,})")
    p.add_argument("--fill-wait", type=int, default=DEFAULT_FILL_WAIT, help="매수 체결 대기(초 · 기본 60 · 10~180)")
    p.add_argument("--instance-dir", default=cp.DEFAULT_INSTANCE_DIR, help="실전 인스턴스 폴더(읽기만)")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="출력 폴더(워크트리·라이브 트리 밖)")
    a = p.parse_args(argv)
    if not (len(a.code) == 6 and a.code.isdigit()):
        p.error("--code 는 숫자 6자리")
    if not (0 < a.max_price <= MAX_PRICE_CEILING):
        p.error(f"--max-price 는 1~{MAX_PRICE_CEILING:,}")
    if not (10 <= a.fill_wait <= 180):
        p.error("--fill-wait 는 10~180 초")
    return a


def _early_exit(out_dir: Path, stamp: str, args: Any, verdict: str) -> int:
    """프로젝트 모듈 import 전 종료(인자 오류·라이브 트리·인스턴스 불일치)도 결과 json 을 남긴다."""
    paths = _paths(out_dir, stamp)
    res = new_result(args or argparse.Namespace(), paths)
    res.update({"exit_code": 2, "verdict": verdict, "guards_all_pass": False,
                "ended_at": datetime.now().isoformat(timespec="seconds")})
    try:
        write_result(paths["result"], res)
    except OSError as e:
        print(f"결과 파일 쓰기 실패: {e}", file=sys.stderr)
    print(f"🔴 {verdict} → exit 2 · 결과 {paths['result']}", file=sys.stderr)
    return 2


def main(argv: Optional[List[str]] = None) -> int:
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    try:
        args = parse_args(argv)
    except SystemExit as e:
        if e.code in (0, None):
            raise                                    # --help
        return _early_exit(_lenient_out_dir(argv), stamp, None, f"인자 오류(exit {e.code}) — 주문 0건")
    out_dir = Path(args.out_dir)
    cg = cp.check_cwd(_cwd())
    if not cg[1]:
        return _early_exit(out_dir, stamp, args, f"라이브 트리 아래에서 실행 금지({cg[2]}) — 주문 0건")
    # config.settings 는 import 시점에 key.ini 를 읽는다 → 프로젝트 모듈 import «전»에 인스턴스를 고정한다.
    inst_dir = Path(args.instance_dir).resolve()
    prev = os.environ.get("KIS_INSTANCE_DIR")
    if prev and Path(prev).resolve() != inst_dir:
        return _early_exit(out_dir, stamp, args, f"KIS_INSTANCE_DIR({prev}) ≠ --instance-dir({inst_dir}) — 주문 0건")
    os.environ["KIS_INSTANCE_DIR"] = str(inst_dir)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths(out_dir, stamp)
    masker = cp.Masker()
    log, raw, teardown = _setup_logging(paths, masker)
    from config.market_hours import now_kst
    ctx = Ctx(args, inst_dir, log, raw, masker, now_kst, paths)
    try:
        return execute(ctx, run)
    finally:
        for fn in reversed(ctx.restore):
            try:
                fn()
            except Exception:
                pass
        teardown()


if __name__ == "__main__":
    sys.exit(main())
