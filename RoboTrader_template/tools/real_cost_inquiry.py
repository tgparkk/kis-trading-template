"""실전 수수료·세금 실측 조회 — 봇 밖 · 읽기 전용 · 일회 스크립트 (2026-11-05 창구 2회 「봇 밖」)

왜: 내부 손익은 `config/constants.py` 의 가정(수수료 0.015% 매수·매도 각각 + 거래세 0.18% 매도)으로
계산하고, 실전 원장 `real_trading_<id>.fee_amount` 는 비어 있다. 계좌가 실제로 낸 수수료·제세금을
KIS 에서 읽어 날짜별로 «수수료 ÷ (매수+매도 체결대금)» vs 가정 0.015% · «제세금 ÷ 매도 체결대금» vs 가정 0.18% 를
본다(한 비율로 합치면 그날 매수 수수료가 섞여 왜곡되므로 둘로 나눈다).

조회(GET 만 · 주문 TR 0):
  - TTTC8708R 기간별손익일별합산조회 (`api/kis_account_api.py:get_inquire_period_profit_lst` 와 같은 요청)
    → 날짜별 수수료·제세금. output1·output2 원본을 그대로 CSV 로 저장.
  - TTTC0081R 주식일별주문체결조회 3개월 이내 (`api/kis_order_api.py:get_inquire_daily_ccld_lst` 와 같은 요청)
    → 날짜·종목·매도/매수·체결수량·체결금액. 원본 그대로 CSV 저장 + 체결대금 합.
  - DB `real_trading_<id>` SELL 행(읽기 전용 세션 · SELECT 만) ↔ TTTC0081R 매도 체결을 (날짜·종목·수량)으로 짝짓기.

🔴 `api.kis_auth._url_fetch` 를 쓰지 않는 이유: 토큰 만료(EGW00123)·_TRENV 없음이면 그 안에서 `auth()` →
   `/oauth2/tokenP` 재발급을 부른다. 같은 appkey tokenP 는 1분당 1회 제한이라 봇 토큰과 충돌할 수 있다.
   이 도구는 `requests.get` 으로 직접 부르고 **tokenP 는 어떤 경로로도 부르지 않는다** (만료면 exit 3).
🔴 응답 필드명(수수료·제세금 등)은 공식 문서 확인 전이다 → 아래 `FIELDS` 상수로 분리했고, 못 찾은 필드는
   계산 칸을 비우고 `<out>_field_check.csv` 와 stdout 에 «미확인» 으로 남긴다(원본 CSV 는 항상 전부 저장).

가드(전부 네트워크·DB 접속 «전»):
  ① 봇 가동 중 → exit 2: `<root>/robotrader_<id>.pid` 또는 `<root>/instances/<id>/robotrader_<id>.pid` 가
     있고 그 PID 가 살아 있으면(판독 불가 PID 파일도 중단 — 수동 확인).
  ② 장중(평일 09:00~15:40 KST) → exit 4.
  ③ 토큰 = `<root>/token_info_<id>.json` **읽기만**. 없음·판독 불가·만료(10분 여유) → exit 3 (재발급 안 함).
     실전 토큰 파일은 «없을 수 있다»(11-05 09:00:10 재발급 스레드가 파일 삭제 뒤 403 · trading_20261105.log L212-214)
     → exit 3 이면 다음 거래일 07:45 실전 기동(토큰 발급) 뒤, 장 마감 후 다시 실행.

사용(장 마감 뒤 · 실전 봇 종료 확인 뒤):
  python tools/real_cost_inquiry.py --instance daytrading --start 20261019 --end 20261105 --out <csv>
  옵션: --root <RoboTrader_template 경로>(기본 = 이 파일의 상위 · 토큰·PID·instances 를 여기서 찾는다)

산출: <out>(날짜별 비교표 + 기간 합계 행) · <stem>_pairs.csv · <stem>_unmatched.csv · <stem>_field_check.csv ·
      <stem>_raw_8708_output1.csv · <stem>_raw_8708_output2.csv ·
      <stem>_raw_0081_output1.csv · <stem>_raw_0081_output2.csv
종료 코드: 0 성공 · 2 봇 가동 중 · 3 토큰 없음/만료 · 4 장중 · 5 설정·API·DB 오류
"""
import argparse
import configparser
import csv
import os
import re
import sys
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE  # noqa: E402  (settings import 없음)

EXIT_OK = 0
EXIT_BOT_RUNNING = 2
EXIT_TOKEN = 3
EXIT_MARKET_HOURS = 4
EXIT_ERROR = 5

KST = timezone(timedelta(hours=9))
MARKET_GUARD_START = dtime(9, 0)
MARKET_GUARD_END = dtime(15, 40)
TOKEN_EXPIRY_MARGIN = timedelta(minutes=10)
PAGE_SLEEP_SEC = 0.5
MAX_PAGES = 50
HTTP_TIMEOUT = (5, 30)

ASSUMED_FEE_RATE_PCT = COMMISSION_RATE * 100       # 0.015 (매수·매도 각각)
ASSUMED_TAX_RATE_PCT = SECURITIES_TAX_RATE * 100   # 0.18 (매도만)

TR_PERIOD_PROFIT = ("TTTC8708R", "/uapi/domestic-stock/v1/trading/inquire-period-profit")
TR_DAILY_CCLD = ("TTTC0081R", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld")

# 🔴 공식 문서 확인 전 «후보» 필드명. 논리명 → 후보 튜플(첫 번째로 응답에 있는 이름을 쓴다).
#    못 찾으면 그 계산 칸은 비고 field_check 에 «미확인» 으로 남는다. 확인되면 여기만 고친다.
FIELDS: Dict[str, Tuple[str, ...]] = {
    # TTTC8708R output1 (일별 합산)
    "8708.date": ("trad_dt",),
    "8708.fee": ("fee",),
    "8708.tax": ("tl_tax",),
    "8708.buy_amt": ("buy_amt",),
    "8708.sell_amt": ("sll_amt",),
    # TTTC0081R output1 (주문별 체결)
    "0081.date": ("ord_dt",),
    "0081.code": ("pdno",),
    "0081.side": ("sll_buy_dvsn_cd",),
    "0081.qty": ("tot_ccld_qty",),
    "0081.amt": ("tot_ccld_amt",),
    "0081.avg_price": ("avg_prvs",),
    "0081.odno": ("odno",),
}
SIDE_SELL = "01"
SIDE_BUY = "02"
TOKEN_EXPIRED_MSG_CODES = ("EGW00123", "EGW00121", "EGW00133")
TR_0081_MAX_DAYS = 90  # TTTC0081R = 3개월 이내 조회


class GuardStop(Exception):
    """가드 중단 — exit 코드와 사유."""

    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


class KisError(Exception):
    pass


# ---------------------------------------------------------------------------
# 가드
# ---------------------------------------------------------------------------
def _pid_alive(pid: int) -> bool:
    import psutil
    return psutil.pid_exists(pid)


def guard_bot_not_running(root: Path, instance: str, pid_alive: Callable[[int], bool] = _pid_alive) -> None:
    name = f"robotrader_{instance}.pid"
    for pid_file in (root / name, root / "instances" / instance / name):
        if not pid_file.exists():
            continue
        try:
            pid = int(pid_file.read_text().strip())
        except (OSError, ValueError):
            raise GuardStop(EXIT_BOT_RUNNING, f"PID 파일 판독 불가({pid_file}) — 봇 종료를 수동 확인하세요")
        if pid_alive(pid):
            raise GuardStop(EXIT_BOT_RUNNING,
                            f"실전 봇 가동 중(PID {pid} · {pid_file}) — 같은 appkey 호출 충돌 방지 위해 중단")


def guard_not_market_hours(now_kst: datetime) -> None:
    if now_kst.weekday() < 5 and MARKET_GUARD_START <= now_kst.time() <= MARKET_GUARD_END:
        raise GuardStop(EXIT_MARKET_HOURS,
                        f"장중({now_kst:%H:%M} KST · 평일 09:00~15:40) — 장 마감 뒤에 실행하세요")


def read_existing_token(token_path: Path, now_kst: datetime) -> str:
    """토큰 파일 «읽기만». 없음·판독 불가·만료면 GuardStop(3) — tokenP 재발급은 하지 않는다."""
    why = "같은 appkey tokenP 는 1분당 1회 제한 · 봇 토큰과 충돌 위험이라 재발급하지 않음"
    if not token_path.exists():
        raise GuardStop(EXIT_TOKEN, f"토큰 파일 없음({token_path}) — {why}")
    try:
        import yaml
        with open(token_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        token = str(data["token"]).strip()
        valid = data["valid-date"]
        if not isinstance(valid, datetime):
            valid = datetime.strptime(str(valid), "%Y-%m-%d %H:%M:%S")
    except Exception as e:  # noqa: BLE001 — 어떤 판독 실패든 같은 처리
        raise GuardStop(EXIT_TOKEN, f"토큰 파일 판독 불가({type(e).__name__}) — {why}")
    if not token:
        raise GuardStop(EXIT_TOKEN, f"토큰 값 비어 있음 — {why}")
    now_naive = now_kst.astimezone(KST).replace(tzinfo=None)
    if valid.replace(tzinfo=None) <= now_naive + TOKEN_EXPIRY_MARGIN:
        raise GuardStop(EXIT_TOKEN, f"토큰 만료(또는 10분 안 만료 · valid-date {valid}) — {why}")
    return token


# ---------------------------------------------------------------------------
# KIS 조회 (GET 만 · tokenP 경로 없음)
# ---------------------------------------------------------------------------
def load_kis_key(key_ini: Path) -> Dict[str, str]:
    if not key_ini.exists():
        raise KisError(f"key.ini 없음: {key_ini}")
    cp = configparser.ConfigParser()
    cp.read(key_ini, encoding="utf-8")
    sec = cp["KIS"]
    acct = sec.get("KIS_ACCOUNT_NO", "").strip('"').strip()
    out = {
        "base_url": sec.get("KIS_BASE_URL", "").strip('"').strip(),
        "appkey": sec.get("KIS_APP_KEY", "").strip('"').strip(),
        "appsecret": sec.get("KIS_APP_SECRET", "").strip('"').strip(),
        # kis_auth.changeTREnv 와 같은 분해(앞 8 + 뒤 2)
        "cano": acct[:8] if len(acct) >= 10 else acct,
        "prod": acct[8:10] if len(acct) >= 10 else "01",
    }
    missing = [k for k in ("base_url", "appkey", "appsecret", "cano") if not out[k]]
    if missing:
        raise KisError(f"key.ini [KIS] 값 없음: {missing}")
    return out


def kis_get_paged(http_get: Callable[..., Any], key: Dict[str, str], token: str, tr: Tuple[str, str],
                  params: Dict[str, str], sleep: Callable[[float], None] = time.sleep) -> Dict[str, List[dict]]:
    """페이징 GET. output1·output2 를 행 목록으로 모아 돌려준다(가공 0)."""
    tr_id, path = tr
    params = dict(params)
    tr_cont = ""
    out: Dict[str, List[dict]] = {"output1": [], "output2": []}
    for _ in range(MAX_PAGES):
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": key["appkey"],
            "appsecret": key["appsecret"],
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": "P",
        }
        resp = http_get(key["base_url"] + path, headers=headers, params=params, timeout=HTTP_TIMEOUT)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            raise KisError(f"{tr_id} 응답 JSON 아님(HTTP {getattr(resp, 'status_code', '?')})")
        if str(body.get("rt_cd")) != "0":
            # 표준 본문(msg_cd/msg1) 외에 비표준 오류 본문(error_code/error_description · 예 403 EGW00133)도 본다
            msg_cd = str(body.get("msg_cd") or body.get("error_code") or "")
            msg1 = str(body.get("msg1") or body.get("error_description") or "")
            if msg_cd in TOKEN_EXPIRED_MSG_CODES or "token" in msg1.lower() or "토큰" in msg1:
                raise GuardStop(EXIT_TOKEN, f"{tr_id} 토큰 거부({msg_cd} {msg1}) — 재발급하지 않고 중단")
            raise KisError(f"{tr_id} 실패: {msg_cd} {msg1}")
        for k in ("output1", "output2"):
            v = body.get(k)
            if isinstance(v, dict):
                v = [v]
            rows = [r for r in (v or []) if isinstance(r, dict) and r]
            if k == "output1":
                out[k].extend(rows)
            elif rows:
                out[k] = rows  # output2 = 조회 전체 합계라 페이지마다 반복 → 마지막(비지 않은) 페이지 것만
        nxt = str((getattr(resp, "headers", None) or {}).get("tr_cont", "")).strip()
        if nxt not in ("F", "M"):
            return out
        params["CTX_AREA_FK100"] = body.get("ctx_area_fk100", "")
        params["CTX_AREA_NK100"] = body.get("ctx_area_nk100", "")
        tr_cont = "N"
        sleep(PAGE_SLEEP_SEC)
    raise KisError(f"{tr_id} 페이지 {MAX_PAGES} 초과 — 중단")


def params_period_profit(key: Dict[str, str], start: str, end: str) -> Dict[str, str]:
    # = kis_account_api.get_inquire_period_profit_lst
    return {"CANO": key["cano"], "ACNT_PRDT_CD": key["prod"], "INQR_DVSN": "00", "SORT_DVSN": "00",
            "PDNO": "", "INQR_STRT_DT": start, "INQR_END_DT": end, "CBLC_DVSN": "00",
            "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}


def params_daily_ccld(key: Dict[str, str], start: str, end: str) -> Dict[str, str]:
    # = kis_order_api.get_inquire_daily_ccld_lst (dv="01", ccld_dvsn="00")
    return {"CANO": key["cano"], "ACNT_PRDT_CD": key["prod"], "INQR_STRT_DT": start, "INQR_END_DT": end,
            "SLL_BUY_DVSN_CD": "00", "INQR_DVSN": "01", "PDNO": "", "CCLD_DVSN": "00", "ORD_GNO_BRNO": "",
            "ODNO": "", "INQR_DVSN_3": "00", "INQR_DVSN_1": "", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}


# ---------------------------------------------------------------------------
# DB (SELECT 만 · 읽기 전용 세션)
# ---------------------------------------------------------------------------
def fetch_internal_sells(instance: str, start: str, end: str) -> List[dict]:
    import psycopg2
    from psycopg2 import sql
    # db/connection.py 기본값과 같은 env·기본값
    conn = psycopg2.connect(host=os.getenv("TIMESCALE_HOST", "localhost"),
                            port=int(os.getenv("TIMESCALE_PORT", 5433)),
                            dbname=os.getenv("TIMESCALE_DB", "kis_template"),
                            user=os.getenv("TIMESCALE_USER", "robotrader"),
                            password=os.getenv("TIMESCALE_PASSWORD", "1234"))
    try:
        conn.set_session(readonly=True, autocommit=True)
        q = sql.SQL(
            "SELECT id, stock_code, stock_name, quantity, price, "
            "to_char(timestamp AT TIME ZONE 'Asia/Seoul', 'YYYYMMDD') AS trade_date, "
            "to_char(timestamp AT TIME ZONE 'Asia/Seoul', 'HH24:MI:SS') AS trade_time, "
            "fee_amount, net_profit, profit_loss "
            "FROM {} WHERE action = 'SELL' "
            "AND to_char(timestamp AT TIME ZONE 'Asia/Seoul', 'YYYYMMDD') BETWEEN %s AND %s "
            "ORDER BY timestamp, id"
        ).format(sql.Identifier(f"real_trading_{instance}"))
        with conn.cursor() as cur:
            cur.execute(q, (start, end))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 가공 (최소)
# ---------------------------------------------------------------------------
def resolve_fields(rows: List[dict], prefix: str) -> Dict[str, Optional[str]]:
    present = set()
    for r in rows:
        present.update(r.keys())
    return {name: next((c for c in cands if c in present), None)
            for name, cands in FIELDS.items() if name.startswith(prefix + ".")}


def to_num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _get(row: dict, fmap: Dict[str, Optional[str]], name: str) -> Any:
    col = fmap.get(name)
    return row.get(col) if col else None


def pair_sells(internal: List[dict], ccld: List[dict], fmap: Dict[str, Optional[str]]
               ) -> Tuple[List[dict], List[dict]]:
    """내부 SELL ↔ KIS 매도 체결을 (날짜·종목·수량) 1:1 로 짝짓는다. 못 지은 행은 unmatched."""
    kis_sells = [r for r in ccld
                 if str(_get(r, fmap, "0081.side") or "") == SIDE_SELL and (to_num(_get(r, fmap, "0081.qty")) or 0) > 0]
    used = [False] * len(kis_sells)
    pairs: List[dict] = []
    unmatched: List[dict] = []
    for it in internal:
        idx = next((i for i, k in enumerate(kis_sells) if not used[i]
                    and str(_get(k, fmap, "0081.date")) == str(it["trade_date"])
                    and str(_get(k, fmap, "0081.code")) == str(it["stock_code"])
                    and to_num(_get(k, fmap, "0081.qty")) == float(it["quantity"])), None)
        internal_amt = float(it["price"]) * int(it["quantity"])
        if idx is None:
            unmatched.append({"side": "internal_only", "date": it["trade_date"], "code": it["stock_code"],
                              "qty": it["quantity"], "internal_id": it["id"], "amount": round(internal_amt, 2),
                              "kis_odno": ""})
            continue
        used[idx] = True
        k = kis_sells[idx]
        kis_amt = to_num(_get(k, fmap, "0081.amt"))
        pairs.append({
            "date": it["trade_date"], "code": it["stock_code"], "name": it.get("stock_name") or "",
            "qty": it["quantity"], "internal_id": it["id"], "internal_time": it.get("trade_time") or "",
            "internal_price": float(it["price"]), "internal_amount": round(internal_amt, 2),
            "kis_odno": _get(k, fmap, "0081.odno") or "", "kis_avg_price": to_num(_get(k, fmap, "0081.avg_price")),
            "kis_amount": kis_amt,
            "amount_diff": None if kis_amt is None else round(kis_amt - internal_amt, 2),
            "internal_fee_amount": it.get("fee_amount"),
        })
    for i, k in enumerate(kis_sells):
        if not used[i]:
            unmatched.append({"side": "kis_only", "date": _get(k, fmap, "0081.date"),
                              "code": _get(k, fmap, "0081.code"), "qty": _get(k, fmap, "0081.qty"),
                              "internal_id": "", "amount": to_num(_get(k, fmap, "0081.amt")),
                              "kis_odno": _get(k, fmap, "0081.odno") or ""})
    return pairs, unmatched


def build_daily(p8708: List[dict], f8708: Dict[str, Optional[str]], ccld: List[dict], f0081: Dict[str, Optional[str]],
                internal: List[dict], pairs: List[dict]) -> List[dict]:
    days: Dict[str, dict] = {}

    def day(d: Any) -> dict:
        d = str(d)
        if d not in days:
            days[d] = {"date": d, "kis_buy_amt": 0.0, "kis_sell_amt": 0.0, "actual_fee": None, "actual_tax": None,
                       "kis8708_buy_amt": None, "kis8708_sell_amt": None, "internal_sell_rows": 0,
                       "internal_sell_amt": 0.0, "internal_fee_amount_sum": None, "matched_rows": 0}
        return days[d]

    def add(rec: dict, k: str, v: Optional[float]) -> None:
        if v is not None:
            rec[k] = (rec[k] or 0.0) + v

    for r in p8708:
        d = _get(r, f8708, "8708.date")
        if not d:
            continue
        rec = day(d)
        add(rec, "actual_fee", to_num(_get(r, f8708, "8708.fee")))
        add(rec, "actual_tax", to_num(_get(r, f8708, "8708.tax")))
        add(rec, "kis8708_buy_amt", to_num(_get(r, f8708, "8708.buy_amt")))
        add(rec, "kis8708_sell_amt", to_num(_get(r, f8708, "8708.sell_amt")))
    for r in ccld:
        d = _get(r, f0081, "0081.date")
        amt = to_num(_get(r, f0081, "0081.amt"))
        if not d or not amt:
            continue
        side = str(_get(r, f0081, "0081.side") or "")
        if side == SIDE_SELL:
            day(d)["kis_sell_amt"] += amt
        elif side == SIDE_BUY:
            day(d)["kis_buy_amt"] += amt
    for it in internal:
        rec = day(it["trade_date"])
        rec["internal_sell_rows"] += 1
        rec["internal_sell_amt"] += float(it["price"]) * int(it["quantity"])
        add(rec, "internal_fee_amount_sum", to_num(it.get("fee_amount")))
    for p in pairs:
        day(p["date"])["matched_rows"] += 1

    rows = [days[d] for d in sorted(days)]
    total = {"date": "TOTAL"}
    for k in rows[0].keys() if rows else []:
        if k == "date":
            continue
        vals = [r[k] for r in rows if r[k] is not None]
        total[k] = sum(vals) if vals else None
    for rec in rows + ([total] if rows else []):
        _finish(rec)
    return rows + ([total] if rows else [])


def _finish(rec: dict) -> None:
    fee, tax = rec.get("actual_fee"), rec.get("actual_tax")
    actual = None if fee is None or tax is None else fee + tax
    assumed = rec["kis_buy_amt"] * COMMISSION_RATE + rec["kis_sell_amt"] * (COMMISSION_RATE + SECURITIES_TAX_RATE)
    rec["actual_cost"] = actual
    rec["assumed_cost"] = round(assumed, 2)
    rec["actual_minus_assumed"] = None if actual is None else round(actual - assumed, 2)
    buy, sell = rec["kis_buy_amt"], rec["kis_sell_amt"]
    rec["actual_fee_rate_pct"] = None if fee is None or not (buy + sell) else round(fee / (buy + sell) * 100, 5)
    rec["assumed_fee_rate_pct"] = round(ASSUMED_FEE_RATE_PCT, 5)
    rec["actual_tax_rate_pct"] = None if tax is None or not sell else round(tax / sell * 100, 5)
    rec["assumed_tax_rate_pct"] = round(ASSUMED_TAX_RATE_PCT, 5)
    for k in ("kis_buy_amt", "kis_sell_amt", "internal_sell_amt"):
        rec[k] = round(rec[k], 2)


DAILY_COLUMNS = ["date", "kis_buy_amt", "kis_sell_amt", "actual_fee", "actual_tax", "actual_cost", "assumed_cost",
                 "actual_minus_assumed", "actual_fee_rate_pct", "assumed_fee_rate_pct", "actual_tax_rate_pct",
                 "assumed_tax_rate_pct",
                 "kis8708_buy_amt", "kis8708_sell_amt", "internal_sell_rows", "matched_rows", "internal_sell_amt",
                 "internal_fee_amount_sum"]


def write_csv(path: Path, rows: List[dict], columns: Optional[List[str]] = None) -> None:
    if columns is None:
        columns = []
        for r in rows:
            for k in r.keys():
                if k not in columns:
                    columns.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="실전 수수료·세금 실측 조회(읽기 전용 · 장 마감 뒤 · 봇 종료 뒤)")
    ap.add_argument("--instance", required=True, help="실전 인스턴스 id (예: daytrading)")
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end", required=True, help="YYYYMMDD")
    ap.add_argument("--out", required=True, help="날짜별 비교표 CSV 경로(부속 CSV 는 같은 폴더에 stem_* 로)")
    ap.add_argument("--root", default=str(_ROOT), help="RoboTrader_template 경로(토큰·PID·instances 위치)")
    return ap.parse_args(argv)


def run(argv: Optional[Sequence[str]] = None, now: Optional[datetime] = None,
        http_get: Optional[Callable[..., Any]] = None,
        fetch_internal: Callable[[str, str, str], List[dict]] = fetch_internal_sells,
        pid_alive: Callable[[int], bool] = _pid_alive,
        sleep: Callable[[float], None] = time.sleep) -> int:
    args = _parse_args(argv)
    instance = args.instance.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]+", instance) or instance == "default":
        print(f"오류: 실전 인스턴스 id 가 아님: {args.instance!r}")
        return EXIT_ERROR
    try:
        start = datetime.strptime(args.start, "%Y%m%d").strftime("%Y%m%d")
        end = datetime.strptime(args.end, "%Y%m%d").strftime("%Y%m%d")
    except ValueError:
        print("오류: --start/--end 는 YYYYMMDD")
        return EXIT_ERROR
    if start > end:
        print("오류: --start > --end")
        return EXIT_ERROR
    root = Path(args.root)
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    if start < (now_kst - timedelta(days=TR_0081_MAX_DAYS)).strftime("%Y%m%d"):
        print(f"WARNING: --start {start} 가 오늘−{TR_0081_MAX_DAYS}일보다 앞 — "
              "TTTC0081R 은 3개월 이내만 조회(앞 구간 체결 누락 가능)")
    out = Path(args.out)

    try:
        guard_bot_not_running(root, instance, pid_alive)        # ① exit 2
        guard_not_market_hours(now_kst)                          # ② exit 4
        token = read_existing_token(root / f"token_info_{instance}.json", now_kst)  # ③ exit 3
        key = load_kis_key(root / "instances" / instance / "key.ini")
        if http_get is None:
            import requests
            http_get = requests.get
        r8708 = kis_get_paged(http_get, key, token, TR_PERIOD_PROFIT, params_period_profit(key, start, end), sleep)
        sleep(PAGE_SLEEP_SEC)
        r0081 = kis_get_paged(http_get, key, token, TR_DAILY_CCLD, params_daily_ccld(key, start, end), sleep)
        internal = fetch_internal(instance, start, end)
    except GuardStop as g:
        print(f"중단(exit {g.code}): {g.reason}")
        return g.code
    except Exception as e:  # noqa: BLE001
        print(f"오류(exit {EXIT_ERROR}): {type(e).__name__}: {e}")
        return EXIT_ERROR

    stem = out.with_suffix("")
    write_csv(Path(f"{stem}_raw_8708_output1.csv"), r8708["output1"])
    write_csv(Path(f"{stem}_raw_8708_output2.csv"), r8708["output2"])
    write_csv(Path(f"{stem}_raw_0081_output1.csv"), r0081["output1"])
    write_csv(Path(f"{stem}_raw_0081_output2.csv"), r0081["output2"])

    f8708 = resolve_fields(r8708["output1"], "8708")
    f0081 = resolve_fields(r0081["output1"], "0081")
    check = [{"field": n, "candidates": "|".join(FIELDS[n]), "resolved": c or "", "status": "ok" if c else "미확인"}
             for n, c in list(f8708.items()) + list(f0081.items())]
    write_csv(Path(f"{stem}_field_check.csv"), check)

    pairs, unmatched = pair_sells(internal, r0081["output1"], f0081)
    daily = build_daily(r8708["output1"], f8708, r0081["output1"], f0081, internal, pairs)
    write_csv(out, daily, DAILY_COLUMNS)
    write_csv(Path(f"{stem}_pairs.csv"), pairs)
    write_csv(Path(f"{stem}_unmatched.csv"), unmatched)

    print(f"기간 {start}~{end} · 8708R {len(r8708['output1'])}행 · 0081R {len(r0081['output1'])}행 · "
          f"내부 SELL {len(internal)}행 · 짝 {len(pairs)} · 못 지음 {len(unmatched)}")
    unknown = [c["field"] for c in check if c["status"] != "ok"]
    print("미확인 필드: " + (", ".join(unknown) if unknown else "없음") + "  (원본 열은 raw_*.csv 에 전부)")
    if daily:
        t = daily[-1]
        print(f"합계: 실제 비용 {t['actual_cost']} · 가정 {t['assumed_cost']} · 수수료율 {t['actual_fee_rate_pct']}% "
              f"vs {t['assumed_fee_rate_pct']}% · 제세금율 {t['actual_tax_rate_pct']}% vs {t['assumed_tax_rate_pct']}%")
    print(f"산출: {out}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run())
