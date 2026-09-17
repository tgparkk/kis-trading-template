"""후보의 «그날 상태» 분류 — 순수 함수(DB·로그 없음).

상태 4종(우선순위 순):
  bought          실제 매수됨     — 그날 `virtual_trading_records` 에 minervini BUY 가 있다
  held            이미 보유       — 그날 09:00 에 minervini 가 이미 들고 있었다
                                    (라이브 `generate_signal` 은 보유 종목이면 `_check_sell` 로 간다 · strategy.py:152-153)
  no_slot         자리 없음       — 장 전체(09:00~15:30) 동안 minervini 보유 수 ≥ K
                                    (또는 체결 수 ≥ max_daily_trades) — 캡 체크가 매수 판단 «앞»에서 None 을 돌려준다
                                    (strategy.py:155-160)
  slot_available  자리 있었음     — 장중 한 번이라도 보유 수 < K 인 구간이 있었다

🔑 «자리» 는 **포지션 시간선**(매수/매도 체결 시각)으로 계산한다. 로그 `[캡] … 사유=max_positions`
   는 2026-09-16(커밋 e597c33) 부터만 있고 종목당 하루 1줄이라 «교차 증거» 칸(`cap_log`)으로만 쓴다.
🔑 K 는 날짜별 이력표로 준다 — 오늘 config.yaml 값(6)은 2026-09-18 07:40 발효라 과거 날짜에 쓰면 틀린다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Dict, List, Optional, Sequence, Tuple

STATE_BOUGHT = "bought"
STATE_HELD = "held"
STATE_NO_SLOT = "no_slot"
STATE_SLOT = "slot_available"
STATE_LABEL_KO = {
    STATE_BOUGHT: "실제 매수됨",
    STATE_HELD: "이미 보유",
    STATE_NO_SLOT: "자리 없음",
    STATE_SLOT: "자리 있었음",
}

# ── K 이력 (minervini_volume_dryup/config.yaml risk_management.max_positions) ──────────
#   (발효일, K, 근거). 발효일 = 봇이 그 값을 읽고 기동한 첫 거래일.
#   🔴 K 가 바뀌면 여기에 한 줄 추가한다 — 추가 안 하면 run.py 가 config 값과 대조해 경고한다.
K_HISTORY: Tuple[Tuple[date, int, str], ...] = (
    (date(2026, 6, 2), 3, "821fb80 Minervini K=3 집중"),
    (date(2026, 9, 18), 6, "bc7df66/c565256 K 3→6 · docs/prereg_2026-09-15_focus3_K_raise.md"),
)

# `[캡]` 계기(`BaseStrategy._log_cap_skip`) 발효일 — 커밋 e597c33(머지 36fe61c) · 09-16 07:40.
CAP_LOG_SINCE = date(2026, 9, 16)

SESSION_OPEN = time(9, 0, 0)
SESSION_CLOSE = time(15, 30, 0)


def k_for(d: date, history: Sequence[Tuple[date, int, str]] = K_HISTORY) -> Tuple[int, str]:
    """날짜 d 에 유효한 (K, 근거). 이력보다 이르면 ValueError."""
    best = None
    for eff, k, why in sorted(history):
        if eff <= d:
            best = (k, why)
    if best is None:
        raise ValueError(f"K 이력에 {d} 이전 항목이 없다")
    return best


@dataclass
class Trade:
    """minervini 한 포지션(매수 1건 + 대응 매도 0/1건)."""
    buy_id: int
    code: str
    buy_ts: datetime
    buy_price: float
    sell_ts: Optional[datetime] = None
    sell_price: Optional[float] = None
    sell_reason: str = ""
    link: str = "buy_record_id"     # 매도 연결 방식: buy_record_id | fifo | open


def build_trades(rows: Sequence[Tuple]) -> List[Trade]:
    """`virtual_trading_records` 행 → 포지션 목록.

    rows: (id, stock_code, action, price, ts_kst(naive datetime), reason, buy_record_id) — ts 오름차순 권장.
    매도는 `buy_record_id` 로 잇는다. 없으면 같은 종목의 열린 매수에 FIFO 로 잇고 `link='fifo'` 표시.
    """
    rows = sorted(rows, key=lambda r: (r[4], r[0]))
    by_id: Dict[int, Trade] = {}
    order: List[Trade] = []
    for rid, code, action, price, ts, reason, brid in rows:
        act = str(action).upper()
        if act == "BUY":
            t = Trade(buy_id=int(rid), code=str(code), buy_ts=ts, buy_price=float(price), link="open")
            by_id[int(rid)] = t
            order.append(t)
        elif act == "SELL":
            target = by_id.get(int(brid)) if brid is not None else None
            link = "buy_record_id"
            if target is None or target.sell_ts is not None:
                cands = [t for t in order if t.code == str(code) and t.sell_ts is None and t.buy_ts <= ts]
                target = cands[0] if cands else None
                link = "fifo"
            if target is not None:
                target.sell_ts, target.sell_price, target.sell_reason = ts, float(price), str(reason or "")
                target.link = link
    return order


def open_at(trades: Sequence[Trade], t: datetime) -> List[Trade]:
    """시각 t «직전»까지 열려 있던 포지션(매수 < t, 매도 없음 또는 매도 ≥ t)."""
    return [x for x in trades if x.buy_ts < t and (x.sell_ts is None or x.sell_ts >= t)]


def slot_windows_detail(trades: Sequence[Trade], d: date, k: int, max_daily_trades: int
                        ) -> Tuple[int, List[Tuple[time, time, str]]]:
    """(09:00 보유 수, [(시작, 끝, 닫힌 원인)]).

    자리 있음 = 보유 수 < K ∧ 그날 체결 수(매수+매도) < max_daily_trades
    (라이브 `on_order_filled` 는 매수·매도 모두 `daily_trades += 1` · strategy.py:170).
    닫힌 원인: `buy:CODE`(minervini 매수로 참) · `daily_cap`(체결 수 한도) · `session_end`.
    """
    t_open = datetime.combine(d, SESSION_OPEN)
    t_close = datetime.combine(d, SESSION_CLOSE)
    n = len(open_at(trades, t_open))
    fills = 0
    events: List[Tuple[datetime, int, str]] = []
    for x in trades:
        if t_open <= x.buy_ts < t_close:
            events.append((x.buy_ts, +1, x.code))
        if x.sell_ts is not None and t_open <= x.sell_ts < t_close:
            events.append((x.sell_ts, -1, x.code))
    events.sort()
    n0 = n
    windows: List[Tuple[time, time, str]] = []
    cur_start: Optional[datetime] = None

    def _free() -> bool:
        return n < k and fills < max_daily_trades

    if _free():
        cur_start = t_open
    for ts, delta, code in events:
        n += delta
        fills += 1
        now_free = _free()
        if cur_start is not None and not now_free:
            cause = f"buy:{code}" if (delta > 0 and n >= k) else "daily_cap"
            if ts > cur_start:
                windows.append((cur_start.time(), ts.time(), cause))
            cur_start = None
        elif cur_start is None and now_free:
            cur_start = ts
    if cur_start is not None and cur_start < t_close:
        windows.append((cur_start.time(), t_close.time(), "session_end"))
    return n0, windows


def slot_windows(trades: Sequence[Trade], d: date, k: int, max_daily_trades: int
                 ) -> Tuple[int, List[Tuple[time, time]]]:
    """(09:00 보유 수, 자리 있던 구간 목록) — 원인 없는 간이판."""
    n0, w = slot_windows_detail(trades, d, k, max_daily_trades)
    return n0, [(a, b) for a, b, _ in w]


def other_holders(trades_by_strategy: Dict[str, Sequence[Trade]], code: str, t: datetime,
                  exclude: str) -> List[str]:
    """시각 t 에 code 를 들고 있던 «다른» 전략 목록(`전략(매수일)`).

    라이브 `bot/trading_analyzer.py:126-129` — POSITIONED 종목(전략 무관)의 매수 신호는 무시된다.
    """
    out: List[str] = []
    for strat, trades in trades_by_strategy.items():
        if strat == exclude:
            continue
        for x in open_at(trades, t):
            if x.code == code:
                out.append(f"{strat}({x.buy_ts:%m-%d})")
    return sorted(out)


def fmt_windows(windows: Sequence[tuple]) -> str:
    return ",".join(f"{w[0]:%H:%M:%S}-{w[1]:%H:%M:%S}" for w in windows)


def classify_candidate(code: str, d: date, trades: Sequence[Trade],
                       windows: Sequence[tuple], list_order: Optional[Sequence[str]] = None
                       ) -> Tuple[str, str]:
    """(상태, 부가설명).

    windows 원소가 (시작, 끝, 원인) 이고 list_order 가 주어지면, **모든** 빈자리가 «이 종목보다 앞 순위»
    minervini 매수로 닫혔을 때 `no_slot`(상위 순위 매수로 소진)으로 본다 — 라이브 on_tick 은 목록 순서대로 평가한다.
    """
    day_buys = [x for x in trades if x.code == code and x.buy_ts.date() == d]
    if day_buys:
        return STATE_BOUGHT, f"매수 {day_buys[0].buy_ts:%H:%M:%S} @{day_buys[0].buy_price:g}"
    t_open = datetime.combine(d, SESSION_OPEN)
    held = [x for x in open_at(trades, t_open) if x.code == code]
    if held:
        h = held[0]
        note = f"보유 since {h.buy_ts:%Y-%m-%d}"
        if h.sell_ts is not None and h.sell_ts.date() == d:
            note += f" · 당일 매도 {h.sell_ts:%H:%M:%S}"
        return STATE_HELD, note
    if not windows:
        return STATE_NO_SLOT, "장 전체 보유수≥K(또는 체결수≥한도)"
    if list_order is not None and all(len(w) == 3 for w in windows):
        rank = {c: i for i, c in enumerate(list_order)}
        me = rank.get(code, len(rank))
        consumed = [w for w in windows
                    if w[2].startswith("buy:") and rank.get(w[2][4:], 10 ** 6) < me]
        if len(consumed) == len(windows):
            desc = ",".join(f"{w[2][4:]}@{w[1]:%H:%M:%S}" for w in consumed)
            return STATE_NO_SLOT, f"빈자리는 상위 순위 매수로 소진({desc})"
    return STATE_SLOT, f"첫 빈자리 {windows[0][0]:%H:%M:%S}"


def cap_log_flag(d: date, code: str, cap_codes: Dict[str, object]) -> str:
    """`Y`(그날 [캡] max_positions 줄 있음) · `N`(계기 있는데 줄 없음) · `NA`(계기 발효 전)."""
    if d < CAP_LOG_SINCE:
        return "NA"
    return "Y" if code in cap_codes else "N"


def evidence_check(state: str, cap_log: str, windows: Sequence[Tuple[time, time]]) -> str:
    """시간선 분류와 로그 계기의 교차 대조. `ok` 또는 `conflict:…`/`note:…`."""
    if cap_log == "NA":
        return "ok(계기없음)"
    full_session = [(SESSION_OPEN, SESSION_CLOSE)]
    if cap_log == "Y" and [tuple(w[:2]) for w in windows] == full_session:
        return "conflict:[캡]줄 있는데 시간선은 장 전체 빈자리"
    if cap_log == "N" and state == STATE_NO_SLOT:
        return "note:시간선은 자리없음인데 [캡]줄 없음(평가 전 스킵·로그 버퍼·다른 사유 가능)"
    return "ok"
