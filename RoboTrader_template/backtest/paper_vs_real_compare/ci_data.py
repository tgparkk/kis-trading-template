# -*- coding: utf-8 -*-
"""페이퍼 vs 실전 daytrading 대조 — 데이터 적재 계층 (읽기 전용).

- DB: SELECT 만(세션 readonly) · DB명 = config.constants.resolve_daily_source_db() · KIS API 호출 0.
- 로그: 실전 `logs/daytrading/trading_YYYYMMDD.log`(§10-1 닫힘: 캡처 파일의 상위집합 확인됨) 읽기만.
- 비용: 비용 도구 CSV(TTTC8708R 하루 행 + 건별 매도 대조 행) 읽기만.
결과는 ci_stats.Dataset 하나로 돌려준다. 통계 계산은 하지 않는다.
"""
import csv
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from ci_stats import (CostDay, DayLog, Dataset, PaperBuy, PaperSell, RealBuy, RealSell)

PKG_DIR = Path(__file__).resolve().parent
RT_ROOT = PKG_DIR.parents[1]                      # .../RoboTrader_template (워크트리)
LIVE_RT = Path("D:/GIT/kis-trading-template/RoboTrader_template")   # 라이브 트리 — 로그·CSV 읽기만
DEFAULT_LOG_ROOT = LIVE_RT / "logs"
DEFAULT_COST_DIR = LIVE_RT / "scratchpad" / "eod_20261112" / "cost_1112"
DEFAULT_COST_DAILY = DEFAULT_COST_DIR / "cost_1019_1112.csv"
DEFAULT_COST_PAIRS = DEFAULT_COST_DIR / "cost_1019_1112_pairs.csv"
PAPER_STRATEGY = "daytrading_3methods_breakout"   # §2

# §6 M6 구조 변화일 — 운영 코드 머지만(문서·태쏘·연구 머지 제외) · 발효일 = 머지 커밋 뒤 첫 평일 07:40
STRUCT_CHANGES: List[Tuple[date, str, str]] = [
    (date(2026, 10, 19), "A", "9da1c45·417d442·aab5d26"),
    (date(2026, 10, 20), "A2 보유 가드 전략별", "dab76b7"),
    (date(2026, 10, 27), "A3 dt 자리 미체결 포함", "627271d"),
    (date(2026, 10, 28), "A4 dt 스크리너 기업행위 가드", "7f8684e"),
    (date(2026, 10, 29), "B 창구1 dt 한도 미체결", "3ae1355"),
    (date(2026, 11, 6), "C 창구2 재기동 한도 복원 외", "2214c44·8f2471c·bb23169·0526829"),
]

# §8 «운영 안정» — EOD 잔고 대사 불일치(MTS 수동 개입 의심) 등으로 사람이 정한 제외 키 (매수일, 종목) → 사유.
# 레인 R 19일 보고에 불일치 기록 0 → 비어 있음.
MANUAL_EXCLUSIONS: Dict[Tuple[date, str], str] = {}

_TS = r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)"
LINE_RE = re.compile(r"^" + _TS + r" \| (\S+) \| (\w+) \| (.*)$")
CODE_RE = re.compile(r"(?<![0-9A-Z])([0-9][0-9A-Z]{5})(?![0-9A-Z])")
MSG = {
    "signal": re.compile(r"^(\w+) 전달 매수신호 사용"),                                   # trading_decision_engine.py:482
    "try": re.compile(r"^매수 주문 시도: (\w+) (\d+)주 @([\d,]+)원"),                       # order_executor.py:83 (반올림 전 가격)
    "buy_ok": re.compile(r"^매수 주문 성공: (\S+) - (\w+)\("),                              # order_executor.py:253
    "stop": re.compile(r"^(\w+) 손절 신호: 손절 실행 \(([-\d.]+)% <= ([-\d.]+)%\)"),       # position_monitor.py:338
    "cap": re.compile(r"^\[캡\] \S+ (\w+) 평가 스킵 사유="),                                # strategies/base.py:611
    "shadow": re.compile(r"^\[shadow\] \S+ (\w+) 캡사유="),                                # strategies/base.py:655
    "cash1": re.compile(r"^(\w+) 자금 부족: 필요="),                                        # bot/trading_analyzer.py
    "cash2": re.compile(r"^자금 부족으로 매수 주문 거부: (\w+)"),                           # order_executor.py:144
    "block": re.compile(r"^매수 주문 차단: (.*)$"),                                         # order_executor.py:89-115
    "api_to": re.compile(r"^매수 주문 API 타임아웃: (\w+)"),                                # order_executor.py:217
    "to_proc": re.compile(r"^5분 타임아웃 처리: (\S+) \((\w+)\)"),                          # order_timeout.py:49
    "to_ok": re.compile(r"^타임아웃 취소 성공: (\S+)"),                                     # order_timeout.py:84
    "b2_fail": re.compile(r"^\[B2-실전\] (\w+) .*(?:주입 실패|해소 실패)"),                  # trading_decision_engine.py:612·651
    "partial": re.compile(r"^주문 부분 체결: \S+ \((\w+)\)"),                               # order_monitor.py:519
}


def _ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def parse_day_log_lines(lines, day: date) -> DayLog:
    """trading 로그 하루치 줄 → DayLog. 타임스탬프 머리가 없는 줄(Traceback 등)은 건너뛴다."""
    lg = DayLog(day=day)
    buy_oids: Dict[str, str] = {}
    to_seen: Dict[str, str] = {}
    for raw in lines:
        m = LINE_RE.match(raw.rstrip("\r\n"))
        if not m:
            continue
        ts = _ts(m.group(1))
        if lg.first_ts is None:
            lg.first_ts = ts
        lg.last_ts = ts
        msg = m.group(4)
        x = MSG["signal"].match(msg)
        if x:
            lg.signals.append((ts, x.group(1)))
            continue
        x = MSG["try"].match(msg)
        if x:
            lg.tries.append((ts, x.group(1), int(x.group(2)), float(x.group(3).replace(",", ""))))
            continue
        x = MSG["buy_ok"].match(msg)
        if x:
            buy_oids[x.group(1)] = x.group(2)
            continue
        x = MSG["stop"].match(msg)
        if x:
            lg.stops.append((ts, x.group(1), float(x.group(2)), float(x.group(3))))
            continue
        x = MSG["cap"].match(msg) or MSG["shadow"].match(msg)
        if x:
            lg.caps.append((ts, x.group(1)))
            continue
        x = MSG["cash1"].match(msg) or MSG["cash2"].match(msg)
        if x:
            lg.cash.append((ts, x.group(1)))
            continue
        x = MSG["block"].match(msg)
        if x:
            c = CODE_RE.search(x.group(1))
            if c:
                lg.blocks.append((ts, c.group(1)))
            continue
        x = MSG["api_to"].match(msg)
        if x:
            lg.api_timeouts.append((ts, x.group(1)))
            continue
        x = MSG["to_proc"].match(msg)
        if x:
            to_seen[x.group(1)] = x.group(2)
            continue
        x = MSG["to_ok"].match(msg)
        if x:
            oid = x.group(1)
            if oid in to_seen and oid in buy_oids:      # 매수 주문의 5분 타임아웃 → 취소 성공만
                lg.delayed_cancels.append((ts, buy_oids[oid]))
            continue
        x = MSG["b2_fail"].match(msg)
        if x:
            lg.b2_fail.append((ts, x.group(1)))
            continue
        x = MSG["partial"].match(msg)
        if x:
            lg.partial.append((ts, x.group(1)))
    return lg


def load_logs(log_root: Path, days: List[date]) -> Tuple[Dict[date, DayLog], List[date]]:
    logs, missing = {}, []
    for d in days:
        p = log_root / "daytrading" / f"trading_{d:%Y%m%d}.log"
        if not p.exists():
            missing.append(d)
            continue
        with open(p, encoding="utf-8", errors="replace") as fh:
            logs[d] = parse_day_log_lines(fh, d)
    return logs, missing


def restart_days_from_files(names_by_side: Dict[str, List[str]], days: List[date]) -> Dict[date, str]:
    """§6 장중 재기동일 = 그날 콘솔 캡처 파일 2개 이상 그리고 두 번째 시작이 09:00~15:30 (페이퍼 또는 실전)."""
    pat = re.compile(r"_(\d{8})_(\d{6})\.log$")
    out: Dict[date, str] = {}
    for side, names in names_by_side.items():
        by_day: Dict[str, List[str]] = {}
        for n in names:
            m = pat.search(n)
            if m:
                by_day.setdefault(m.group(1), []).append(m.group(2))
        for d in days:
            starts = sorted(by_day.get(f"{d:%Y%m%d}", []))
            if len(starts) >= 2 and "090000" <= starts[1] <= "153000":
                out[d] = (out.get(d, "") + f" {side} 두 번째 시작 {starts[1][:2]}:{starts[1][2:4]}").strip()
    return out


def load_restart_days(log_root: Path, days: List[date]) -> Dict[date, str]:
    paper = [n for n in os.listdir(log_root) if n.startswith("robotrader_template_")]
    real_dir = log_root / "daytrading"
    real = [n for n in os.listdir(real_dir) if n.startswith("robotrader_daytrading_")] if real_dir.exists() else []
    return restart_days_from_files({"페이퍼": paper, "실전": real}, days)


def load_cost(daily_csv: Path, pairs_csv: Path) -> Tuple[Dict[date, CostDay], Dict[Tuple[date, str, int], float]]:
    days: Dict[date, CostDay] = {}
    with open(daily_csv, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if not re.fullmatch(r"\d{8}", r["date"] or ""):
                continue                                   # TOTAL 행
            d = datetime.strptime(r["date"], "%Y%m%d").date()
            days[d] = CostDay(day=d, buy_amt=float(r["kis_buy_amt"]), sell_amt=float(r["kis_sell_amt"]),
                              fee=float(r["actual_fee"]), tax=float(r["actual_tax"]))
    rows: Dict[Tuple[date, str, int], float] = {}
    with open(pairs_csv, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if not r.get("kis_amount"):
                continue
            d = datetime.strptime(r["date"], "%Y%m%d").date()
            rows[(d, r["code"].strip(), int(r["qty"]))] = float(r["kis_amount"])
    return days, rows


# ---------------------------------------------------------------- DB (SELECT 만)
def connect():
    import psycopg2
    if str(RT_ROOT) not in sys.path:
        sys.path.insert(0, str(RT_ROOT))
    from config.constants import resolve_daily_source_db
    conn = psycopg2.connect(host=os.getenv("TIMESCALE_HOST", "127.0.0.1"), port=int(os.getenv("TIMESCALE_PORT", 5433)),
                            dbname=resolve_daily_source_db(), user=os.getenv("TIMESCALE_USER", "robotrader"),
                            password=os.getenv("TIMESCALE_PASSWORD", "1234"))
    conn.set_session(readonly=True)
    return conn


KST = "(timestamp at time zone 'Asia/Seoul')"


def load_db(conn, start: date, end: date) -> Dict[str, object]:
    cur = conn.cursor()
    cur.execute(f"""select id, stock_code, {KST}, price, quantity, stop_loss_rate from virtual_trading_records
        where source='kis_template' and strategy=%s and is_test=true and action='BUY'
          and {KST}::date between %s and %s order by timestamp, id""", (PAPER_STRATEGY, start, end))
    pb = [PaperBuy(r[0], r[1], r[2], float(r[3]), int(r[4]), None if r[5] is None else float(r[5])) for r in cur.fetchall()]
    ids = tuple(p.id for p in pb) or (-1,)
    cur.execute(f"""select id, stock_code, {KST}, price, quantity, buy_record_id, coalesce(reason,'') from virtual_trading_records
        where action='SELL' and buy_record_id in %s and {KST}::date <= %s order by timestamp, id""", (ids, end))
    psl = [PaperSell(r[0], r[1], r[2], float(r[3]), int(r[4]), r[5], r[6]) for r in cur.fetchall()]
    cur.execute(f"""select id, stock_code, {KST}, price, quantity from real_trading_daytrading
        where action='BUY' and {KST}::date between %s and %s order by timestamp, id""", (start, end))
    rb = [RealBuy(r[0], r[1], r[2], float(r[3]), int(r[4])) for r in cur.fetchall()]
    cur.execute(f"""select id, stock_code, {KST}, price, quantity, buy_record_id from real_trading_daytrading
        where action='SELL' and {KST}::date between %s and %s order by timestamp, id""", (start, end))
    rs = [RealSell(r[0], r[1], r[2], float(r[3]), int(r[4]), r[5]) for r in cur.fetchall()]
    cur.execute("""select date, close from daily_prices where stock_code='KOSPI' and date between %s and %s order by date""",
                (str(start - timedelta(days=14)), str(end)))        # daily_prices.date = text 'YYYY-MM-DD'
    kospi = [(r[0] if isinstance(r[0], date) else datetime.strptime(str(r[0]), "%Y-%m-%d").date(), float(r[1]))
             for r in cur.fetchall()]
    # 기계 점검(§10 · 위반 점검용 · 값 계산 아님)
    checks = {}
    cur.execute(f"""select coalesce(strategy,'(NULL)'), count(*) from real_trading_daytrading
        where {KST}::date between %s and %s group by 1""", (start, end))
    checks["실전 strategy 열 값(§10-3)"] = dict(cur.fetchall())
    cur.execute(f"""select count(*), sum(case when fee_amount is null and net_profit is null and net_profit_rate is null then 1 else 0 end),
        sum(case when timestamp = created_at then 1 else 0 end) from real_trading_daytrading where {KST}::date between %s and %s""",
                (start, end))
    n, nnull, nts = cur.fetchone()
    checks["실전 fee/net 열 NULL(§3-4)"] = f"{nnull}/{n}"
    checks["실전 timestamp = created_at(§10-2)"] = f"{nts}/{n}"
    checks["페이퍼 BUY stop_loss_rate NULL"] = f"{sum(1 for p in pb if p.stop_loss_rate is None)}/{len(pb)}"
    rb_ids = {r.id for r in rb}
    cur.execute(f"""select count(*) from real_trading_daytrading where action='BUY' and {KST}::date < %s
        and id in (select buy_record_id from real_trading_daytrading where action='SELL' and {KST}::date between %s and %s)""",
                (start, start, end))
    checks["기간 전 BUY 에 이어진 실전 SELL"] = cur.fetchone()[0]
    checks["실전 SELL buy_record_id 가 기간 BUY 밖"] = sum(1 for s in rs if s.buy_record_id not in rb_ids)
    cur.close()
    return {"paper_buys": pb, "paper_sells": psl, "real_buys": rb, "real_sells": rs, "kospi": kospi, "checks": checks}


def kospi_signs(kospi: List[Tuple[date, float]], start: date, end: date) -> Tuple[Dict[date, int], List[date]]:
    """§3 상승/하락일 = 그날 KOSPI 종가 − 전 거래일 종가 부호(임계 없음 · §11 반영 못 한 것 (4))."""
    signs, days = {}, []
    for (d0, c0), (d1, c1) in zip(kospi, kospi[1:]):
        if start <= d1 <= end:
            signs[d1] = (c1 > c0) - (c1 < c0)
            days.append(d1)
    if kospi and start <= kospi[0][0] <= end:
        days.insert(0, kospi[0][0])     # 전일 종가가 조회 창 밖 → 부호 없음(0)
        signs.setdefault(kospi[0][0], 0)
    return signs, days


def load_dataset(start: date, end: date, log_root: Path = DEFAULT_LOG_ROOT, cost_daily: Path = DEFAULT_COST_DAILY,
                 cost_pairs: Path = DEFAULT_COST_PAIRS, conn=None) -> Dataset:
    own = conn is None
    conn = conn or connect()
    try:
        db = load_db(conn, start, end)
    finally:
        if own:
            conn.close()
    signs, tdays = kospi_signs(db["kospi"], start, end)
    logs, missing = load_logs(log_root, tdays)
    cdays, crows = load_cost(cost_daily, cost_pairs)
    checks = db["checks"]
    checks["실전 로그 없는 거래일"] = [f"{d:%m-%d}" for d in missing] or "없음"
    checks["비용 CSV 기간"] = f"{min(cdays):%m-%d}~{max(cdays):%m-%d}" if cdays else "없음"
    return Dataset(start=start, end=end, paper_buys=db["paper_buys"], paper_sells=db["paper_sells"],
                   real_buys=db["real_buys"], real_sells=db["real_sells"], logs=logs, cost_days=cdays, cost_rows=crows,
                   kospi_sign=signs, trading_days=tdays, restart_days=load_restart_days(log_root, tdays),
                   manual_exclusions=dict(MANUAL_EXCLUSIONS), struct_changes=list(STRUCT_CHANGES),
                   meta={"checks": checks, "sources": {"log_root": str(log_root), "cost_daily": str(cost_daily),
                                                       "cost_pairs": str(cost_pairs)}})
