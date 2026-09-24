"""D-1 게이트 관측 번들 사전등록 §6 기준선 재현 스크립트 (2026-09-24).

짝 문서: ``docs/prereg_2026-09-24_gate_observability_bundle.md`` §6.

읽기 전용이다 — 로그 파일(인자로 받음)을 파싱하고 DB 는 SELECT 만 한다(kis_template).
라이브 코드 import 0 · 파일 쓰기 0. 전략별 종목당 상한(cap)은 ``strategies/*/config.yaml`` 의
``max_per_stock_amount`` 를 정규식으로 읽는다(G1 ``core/virtual_trading_manager.py:611-612`` 와 같은 원천).

출력(날짜별)
  6-1 ``[캡]`` 줄 — 전략·사유별 줄/고유 · 매수루프/매도루프 추정(timeframe = 루프밖)
  6-2 계기 없는 전략의 포화(요약줄 파싱) — 포화 틱 · 매수루프 막힌 고유 · 매도루프 최대
  6-3 ``수량부족`` — 줄/고유 · 전략별 · ④ 3라벨 추정 · 억제(스로틀) 추정 · 실제 ≈
  6-4 기타 — 총 줄 · ``[on_tick]`` 요약 · ``[매수거절]`` · on_tick 타임아웃 · ``가상매수:``/``가상매도:`` vs VTR
  (+) ⑤ ``[shadow]`` 기대치 — 집중 3전략의 매수루프 막힌 고유(요약줄 기준)

추정 규칙(문서 §6 과 동일)
  - 매수루프 추정: ``[캡]`` 종목이 그날 그 전략의 매수루프 줄(``[신호없음] … generate_signal None`` ·
    ``[on_tick] 매수신호``)에 나오면 매수루프, 아니면 매도루프. 사유 timeframe 은 루프밖.
  - ④ 3라벨: budget = 전일 ``paper_strategy_equity.cash`` + 당일 VTR 체결 누적(매수 −금액×(1+0.015%),
    매도 +금액×(1−0.015%−0.18%)) · price = 그 종목의 직전 🧾 신호가 · per_stock = 직전
    ``종목당 투자금액 재산정`` 값 · eff = min(per_stock, cap) (cap 은 ``cap is not None and 0 < cap`` 일 때만).
    현금 = budget < price · 단가 = eff < price → 현금부족 / 단가초과 / 현금부족+단가초과.
  - 억제: ``전달 매수신호 사용`` 줄 뒤 3줄 안에 같은 종목 ``[매수거절]``·체결 줄이 없으면 억제로 보고,
    그 종목의 직전 로그 거절 사유에 귀속한다.

사용
  python prereg_2026-09-24_gate_observability_bundle_baseline.py LOG [LOG ...]
         [--db-host 127.0.0.1] [--db-port 5433] [--db-name kis_template] [--db-user robotrader] [--db-password 1234]
  LOG 파일명은 ``robotrader_template_YYYYMMDD_HHMMSS.log`` (날짜를 파일명에서 읽는다 · 상위집합 로그).

§6 재현 명령 (워크트리 ``D:/tmp/kis-wt-gate-obs`` 에서 · 라이브 트리 로그는 읽기만)
  D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe ^
    RoboTrader_template/docs/prereg_2026-09-24_gate_observability_bundle_baseline.py ^
    D:/GIT/kis-trading-template/RoboTrader_template/logs/robotrader_template_20260921_074007.log ^
    D:/GIT/kis-trading-template/RoboTrader_template/logs/robotrader_template_20260922_074007.log ^
    D:/GIT/kis-trading-template/RoboTrader_template/logs/robotrader_template_20260923_074008.log
  (Git Bash 에서는 ``^`` 대신 ``\\`` · 콘솔 인코딩 문제 시 ``PYTHONIOENCODING=utf-8``)

2026-09-24 실행 출력 (위 재현 명령 · venv Python 3.9.13 · 라이브 트리 로그 읽기만 · 문서 §6 과 전 항목 일치;
09-22 억제 산식 218 대 사유별 합 220 의 차 2 는 문서 §6-3 「±2」)
  ==== 2026-09-21  (robotrader_template_20260921_074007.log · 전일 cash = paper_strategy_equity 2026-09-18)
   6-1 [캡] 합 54
     ma20       daily_trades   줄=  44 고유= 44 매수루프(추정)=  6 매도루프(추정)= 38
     ma20       timeframe      줄=  10 고유= 10 루프밖
   6-2 요약줄 포화(전 전략) — 포화 틱/전체 · 사유: 매수루프 막힌 고유 · 매도루프 최대
     ma20        61/66  daily_trades: 매수 7 · 매도≤38
     ma5         65/66  daily_trades: 매수 9 · 매도≤44
     rs_leader   66/66  max_positions: 매수 5 · 매도≤37
     (+) ⑤ [shadow] 기대(집중 3전략 매수루프 막힌 고유 합) = 7 {'ma20': 7, 'minervini': 0, 'daytrading': 0}
   6-3 수량부족 줄=514 고유=26 전략별=daytrading 330, minervini 167, ma20 11, elder 6
     ④ 3라벨(추정) 현금부족 508/25, 단가초과 6/1  (줄/고유 · 현금부족+단가초과 없으면 0)
     억제(추정): 전달 매수신호 사용 1105 − 로그 거절 553 − VTR 매수 8 = 544 · 사유별 수량부족 509, 진입가 밴드 이탈 — 스킵 35
     수량부족 실제 ≈ 514 + 509 = 1023
   6-4 총 줄=11534 · [on_tick] 요약=528 · [매수거절]=553 · on_tick 타임아웃=0 · 가상매수:/가상매도: 8/12 vs VTR BUY/SELL 8/12
  ==== 2026-09-22  (robotrader_template_20260922_074007.log · 전일 cash = paper_strategy_equity 2026-09-21)
   6-1 [캡] 합 163
     ma20       daily_trades   줄=  49 고유= 49 매수루프(추정)=  7 매도루프(추정)= 42
     ma20       max_positions  줄=  51 고유= 51 매수루프(추정)=  7 매도루프(추정)= 44
     ma20       timeframe      줄=  10 고유= 10 루프밖
     daytrading daily_trades   줄=  53 고유= 53 매수루프(추정)=  7 매도루프(추정)= 46
   6-2 요약줄 포화(전 전략) — 포화 틱/전체 · 사유: 매수루프 막힌 고유 · 매도루프 최대
     ma20        60/62  max_positions: 매수 8 · 매도≤43 daily_trades: 매수 7 · 매도≤42
     ma5         58/61  max_positions: 매수 7 · 매도≤48 daily_trades: 매수 6 · 매도≤48
     daytrading  60/62  daily_trades: 매수 8 · 매도≤44
     rs_leader   60/61  daily_trades: 매수 4 · 매도≤45
     (+) ⑤ [shadow] 기대(집중 3전략 매수루프 막힌 고유 합) = 23 {'ma20': 15, 'minervini': 0, 'daytrading': 8}
   6-3 수량부족 줄=214 고유=8 전략별=minervini 213, elder 1
     ④ 3라벨(추정) 현금부족 213/7, 단가초과 1/1  (줄/고유 · 현금부족+단가초과 없으면 0)
     억제(추정): 전달 매수신호 사용 464 − 로그 거절 228 − VTR 매수 18 = 218 · 사유별 수량부족 215, 진입가 밴드 이탈 — 스킵 3, 현재가 미확보 — 진입 보류 2
     수량부족 실제 ≈ 214 + 215 = 429
   6-4 총 줄=12172 · [on_tick] 요약=492 · [매수거절]=228 · on_tick 타임아웃=0 · 가상매수:/가상매도: 18/16 vs VTR BUY/SELL 18/16
  ==== 2026-09-23  (robotrader_template_20260923_074008.log · 전일 cash = paper_strategy_equity 2026-09-22)
   6-1 [캡] 합 176
     ma20       max_positions  줄=  55 고유= 55 매수루프(추정)=  5 매도루프(추정)= 50
     ma20       timeframe      줄=  10 고유= 10 루프밖
     daytrading daily_trades   줄=  52 고유= 52 매수루프(추정)=  7 매도루프(추정)= 45
     daytrading max_positions  줄=  59 고유= 59 매수루프(추정)=  9 매도루프(추정)= 50
   6-2 요약줄 포화(전 전략) — 포화 틱/전체 · 사유: 매수루프 막힌 고유 · 매도루프 최대
     ma20        59/61  max_positions: 매수 6 · 매도≤47
     ma5         59/61  max_positions: 매수 8 · 매도≤52 daily_trades: 매수 7 · 매도≤52
     daytrading  61/61  max_positions: 매수 10 · 매도≤47 daily_trades: 매수 8 · 매도≤45
     rs_leader   58/61  daily_trades: 매수 6 · 매도≤49
     (+) ⑤ [shadow] 기대(집중 3전략 매수루프 막힌 고유 합) = 24 {'ma20': 6, 'minervini': 0, 'daytrading': 18}
   6-3 수량부족 줄=195 고유=7 전략별=minervini 186, elder 9
     ④ 3라벨(추정) 현금부족 186/6, 단가초과 9/1  (줄/고유 · 현금부족+단가초과 없으면 0)
     억제(추정): 전달 매수신호 사용 452 − 로그 거절 224 − VTR 매수 17 = 211 · 사유별 수량부족 180, 진입가 밴드 이탈 — 스킵 31
     수량부족 실제 ≈ 195 + 180 = 375
   6-4 총 줄=9004 · [on_tick] 요약=489 · [매수거절]=224 · on_tick 타임아웃=0 · 가상매수:/가상매도: 17/9 vs VTR BUY/SELL 17/9
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

COMMISSION_RATE = 0.00015      # config/constants.py:175
SECURITIES_TAX_RATE = 0.0018   # config/constants.py:176
FOCUS3 = ("book_pullback_ma20", "minervini_volume_dryup", "daytrading_3methods_breakout")

CLS2F = {
    "ElderEmaPullbackStrategy": "elder_ema_pullback",
    "BookEnvelope200dStrategy": "book_envelope_200d",
    "DayTrading3MethodsBreakoutStrategy": "daytrading_3methods_breakout",
    "MinerviniVolumeDryupStrategy": "minervini_volume_dryup",
    "BookPullbackMa20Strategy": "book_pullback_ma20",
    "BookPullbackMa5Strategy": "book_pullback_ma5",
    "RSLeaderStrategy": "rs_leader",
    "DeepMrDev20Strategy": "deep_mr_dev20",
}
SHORT = {
    "elder_ema_pullback": "elder", "book_envelope_200d": "envelope",
    "daytrading_3methods_breakout": "daytrading", "minervini_volume_dryup": "minervini",
    "book_pullback_ma20": "ma20", "book_pullback_ma5": "ma5", "rs_leader": "rs_leader",
    "deep_mr_dev20": "deep_mr",
}

RE_LINE = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) \| (\S+) \| (\w+) \| (.*)$")
RE_CAP = re.compile(r"\[캡\] (\S+) (\w{6}) 평가 스킵 사유=(\w+) 보유=(\d+)/(\d+) 일일매수=(\d+)/(\d+)")
RE_SUM = re.compile(r"\[on_tick\] 매수검토 (\d+)종목\(스킵 (\d+)\), 신호 (\d+)건 \| "
                    r"자리 (\S+)/(\S+)·일일 (\S+)/(\S+) \| 매도검토 (\d+)종목")
RE_NOSIG = re.compile(r"\[신호없음\] (\w{6}): generate_signal None")
RE_BUYSIG = re.compile(r"\[on_tick\] 매수신호: (\w{6})\(")
RE_PAPER = re.compile(r"매수 시그널: (\w{6}) @ ([\d,]+)")
RE_REJ = re.compile(r"\[매수거절\] (\w{6}) (.*)$")
RE_HAND = re.compile(r"(\w{6}) 전달 매수신호 사용")
RE_PS = re.compile(r"종목당 투자금액 재산정: (\S+) [\d,]+원 → ([\d,]+)원")
RE_FILE_DATE = re.compile(r"robotrader_template_(\d{8})_\d+\.log$")


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def read_caps(repo: Path) -> Dict[str, Optional[float]]:
    """strategies/<폴더>/config.yaml 의 max_per_stock_amount (없으면 None)."""
    caps: Dict[str, Optional[float]] = {}
    for folder in CLS2F.values():
        p = repo / "strategies" / folder / "config.yaml"
        cap = None
        if p.exists():
            m = re.search(r"^\s*max_per_stock_amount:\s*([\d_]+)", p.read_text(encoding="utf-8"), re.M)
            if m:
                cap = float(m.group(1).replace("_", ""))
        caps[folder] = cap
    return caps


def db_fetch(conn, day: dt.date) -> Tuple[Dict[str, float], List[tuple], dt.date]:
    """SELECT 만: 전일 전략별 cash · 당일 VTR 체결(KST 시각 순)."""
    with conn.cursor() as cur:
        cur.execute("SELECT max(trade_date) FROM paper_strategy_equity WHERE trade_date < %s", (day,))
        prev = cur.fetchone()[0]
        cur.execute("SELECT strategy, cash FROM paper_strategy_equity WHERE trade_date = %s", (prev,))
        cash0 = {s: float(c) for s, c in cur.fetchall()}
        cur.execute(
            "SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul', 'HH24:MI:SS'), strategy, action, price, quantity "
            "FROM virtual_trading_records "
            "WHERE (timestamp AT TIME ZONE 'Asia/Seoul')::date = %s ORDER BY timestamp",
            (day,))
        trades = [(t, s, a, float(p), int(q)) for t, s, a, p, q in cur.fetchall()]
    return cash0, trades, prev


def budget_at(cash0: Dict[str, float], trades: List[tuple], strat: str, hms: str) -> Optional[float]:
    b = cash0.get(strat)
    if b is None:
        return None
    for t, s, a, p, q in trades:
        if s != strat or t > hms:
            continue
        amt = p * q
        b += -amt * (1 + COMMISSION_RATE) if a == "BUY" else amt * (1 - COMMISSION_RATE - SECURITIES_TAX_RATE)
    return b


def qty_label(budget: float, price: float, per_stock: float, cap: Optional[float]) -> str:
    """④ 3라벨 — G1 과 같은 cap 규칙(cap is not None and 0 < cap)."""
    eff = min(per_stock, cap) if (cap is not None and 0 < cap) else per_stock
    cash_bind, unit_bind = budget < price, eff < price
    if cash_bind and unit_bind:
        return "현금부족+단가초과"
    if cash_bind:
        return "현금부족"
    if unit_bind:
        return "단가초과"
    return "라벨없음"


def analyze(path: Path, conn, caps: Dict[str, Optional[float]]) -> None:
    m = RE_FILE_DATE.search(path.name)
    if not m:
        raise SystemExit(f"파일명에서 날짜를 못 읽음: {path.name}")
    day = dt.datetime.strptime(m.group(1), "%Y%m%d").date()
    cash0, trades, prev = db_fetch(conn, day)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    cap_lines = collections.Counter()
    cap_codes: Dict[tuple, set] = collections.defaultdict(set)
    buyset: Dict[str, set] = collections.defaultdict(set)
    pending: Dict[str, list] = collections.defaultdict(list)
    sat_codes: Dict[str, Dict[str, set]] = collections.defaultdict(lambda: collections.defaultdict(set))
    sat_sell: Dict[str, Dict[str, int]] = collections.defaultdict(lambda: collections.defaultdict(int))
    sat_ticks = collections.Counter()
    n_sum = collections.Counter()
    last_sig_strat: Dict[str, str] = {}
    last_price: Dict[str, float] = {}
    per_stock: Dict[str, float] = {}
    rej = collections.Counter()
    rej_codes: Dict[str, set] = collections.defaultdict(set)
    last_rej_reason: Dict[str, str] = {}
    qty_by_strat = collections.Counter()
    labels = collections.Counter()
    label_codes: Dict[str, set] = collections.defaultdict(set)
    hand: List[Tuple[str, int]] = []
    n_ontick_sum = n_timeout = n_vbuy = n_vsell = 0

    for i, raw in enumerate(lines):
        mm = RE_LINE.match(raw)
        if not mm:
            continue
        _, hms, lg, _lvl, msg = mm.groups()
        if "on_tick 타임아웃" in msg:
            n_timeout += 1
        if msg.startswith("가상매수:"):
            n_vbuy += 1
        elif msg.startswith("가상매도:"):
            n_vsell += 1
        mc = RE_CAP.search(msg)
        if mc:
            f, code, reason = mc.group(1), mc.group(2), mc.group(3)
            cap_lines[(f, reason)] += 1
            cap_codes[(f, reason)].add(code)
            continue
        strat = CLS2F.get(lg.split(".", 1)[1]) if lg.startswith("strategy.") else None
        if strat:
            mn = RE_NOSIG.search(msg)
            if mn:
                buyset[strat].add(mn.group(1))
                pending[strat].append(mn.group(1))
                continue
            mb = RE_BUYSIG.search(msg)
            if mb:
                buyset[strat].add(mb.group(1))
                pending[strat].append(mb.group(1))
                last_sig_strat[mb.group(1)] = strat
                continue
            mp = RE_PAPER.search(msg)
            if mp:
                last_price[mp.group(1)] = _num(mp.group(2))
                continue
            ms = RE_SUM.search(msg)
            if ms:
                n_ontick_sum += 1
                n_sum[strat] += 1
                _nb, _sk, _ns, n, k, d, dd, nsell = ms.groups()
                try:
                    n, k, d, dd = int(n), int(k), int(d), int(dd)
                    reason = "daily_trades" if d >= dd else ("max_positions" if n >= k else None)
                except ValueError:
                    reason = None
                if reason:
                    sat_ticks[strat] += 1
                    sat_codes[strat][reason].update(pending[strat])
                    sat_sell[strat][reason] = max(sat_sell[strat][reason], int(nsell) - n)
                pending[strat] = []
                continue
        mps = RE_PS.search(msg)
        if mps:
            per_stock[mps.group(1)] = _num(mps.group(2))
        mh = RE_HAND.search(msg)
        if mh:
            hand.append((mh.group(1), i))
            continue
        mr = RE_REJ.search(msg)
        if mr:
            code, why = mr.group(1), mr.group(2).strip()
            head = why.split("(", 1)[0].strip()
            rej[head] += 1
            rej_codes[head].add(code)
            last_rej_reason[code] = head
            if head.startswith("수량부족"):
                s = last_sig_strat.get(code)
                qty_by_strat[s or "?"] += 1
                px = last_price.get(code)
                b = budget_at(cash0, trades, s, hms) if s else None
                if s is None or px is None or b is None or s not in per_stock:
                    lab = "?"
                else:
                    lab = qty_label(b, px, per_stock[s], caps.get(s))
                labels[lab] += 1
                label_codes[lab].add(code)

    supp = collections.Counter()
    for code, i in hand:
        nxt = lines[i + 1:i + 4]
        if any(("[매수거절] " + code) in x for x in nxt):
            continue
        if any(("매수" in x and ("체결" in x or "완료" in x or "주문" in x)) for x in nxt):
            continue
        supp[last_rej_reason.get(code, "?")] += 1

    vtr_buy = sum(1 for t in trades if t[2] == "BUY")
    vtr_sell = sum(1 for t in trades if t[2] == "SELL")
    n_rej = sum(rej.values())
    qty_lines = sum(c for h, c in rej.items() if h.startswith("수량부족"))
    qty_uniq = len(set().union(*[v for h, v in rej_codes.items() if h.startswith("수량부족")] or [set()]))
    qty_supp = sum(c for h, c in supp.items() if h.startswith("수량부족"))

    print(f"==== {day}  ({path.name} · 전일 cash = paper_strategy_equity {prev})")
    print(f" 6-1 [캡] 합 {sum(cap_lines.values())}")
    for (f, r), c in sorted(cap_lines.items()):
        codes = cap_codes[(f, r)]
        if r == "timeframe":
            print(f"   {SHORT.get(f, f):10s} {r:14s} 줄={c:4d} 고유={len(codes):3d} 루프밖")
        else:
            b = len([x for x in codes if x in buyset[f]])
            print(f"   {SHORT.get(f, f):10s} {r:14s} 줄={c:4d} 고유={len(codes):3d} "
                  f"매수루프(추정)={b:3d} 매도루프(추정)={len(codes) - b:3d}")
    print(" 6-2 요약줄 포화(전 전략) — 포화 틱/전체 · 사유: 매수루프 막힌 고유 · 매도루프 최대")
    for s in sorted(sat_ticks):
        parts = " ".join(f"{r}: 매수 {len(v)} · 매도≤{sat_sell[s][r]}" for r, v in sat_codes[s].items())
        print(f"   {SHORT.get(s, s):10s} {sat_ticks[s]:3d}/{n_sum[s]:<3d} {parts}")
    shadow = {SHORT[s]: sum(len(v) for v in sat_codes[s].values()) for s in FOCUS3}
    print(f"   (+) ⑤ [shadow] 기대(집중 3전략 매수루프 막힌 고유 합) = {sum(shadow.values())} {shadow}")
    print(f" 6-3 수량부족 줄={qty_lines} 고유={qty_uniq} 전략별="
          + ", ".join(f"{SHORT.get(k, k)} {v}" for k, v in qty_by_strat.most_common()))
    print("   ④ 3라벨(추정) " + ", ".join(f"{k} {v}/{len(label_codes[k])}" for k, v in labels.most_common())
          + "  (줄/고유 · 현금부족+단가초과 없으면 0)")
    print(f"   억제(추정): 전달 매수신호 사용 {len(hand)} − 로그 거절 {n_rej} − VTR 매수 {vtr_buy} = "
          f"{len(hand) - n_rej - vtr_buy} · 사유별 " + ", ".join(f"{k} {v}" for k, v in supp.most_common()))
    print(f"   수량부족 실제 ≈ {qty_lines} + {qty_supp} = {qty_lines + qty_supp}")
    print(f" 6-4 총 줄={len(lines)} · [on_tick] 요약={n_ontick_sum} · [매수거절]={n_rej} · "
          f"on_tick 타임아웃={n_timeout} · 가상매수:/가상매도: {n_vbuy}/{n_vsell} vs VTR BUY/SELL {vtr_buy}/{vtr_sell}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("--db-host", default=os.environ.get("PGHOST", "127.0.0.1"))
    ap.add_argument("--db-port", type=int, default=int(os.environ.get("PGPORT", "5433")))
    ap.add_argument("--db-name", default="kis_template")
    ap.add_argument("--db-user", default="robotrader")
    ap.add_argument("--db-password", default=os.environ.get("PGPASSWORD", "1234"))
    a = ap.parse_args(argv)
    import psycopg2  # 지연 import — --help 는 DB 드라이버 없이도 동작

    repo = Path(__file__).resolve().parents[1]      # RoboTrader_template/
    caps = read_caps(repo)
    conn = psycopg2.connect(host=a.db_host, port=a.db_port, dbname=a.db_name,
                            user=a.db_user, password=a.db_password)
    try:
        conn.set_session(readonly=True, autocommit=True)
        for p in a.logs:
            analyze(p, conn, caps)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
