"""실행 문맥 — DB(SELECT 전용)·달력·체결 원장·라이브 인스턴스·캐시와 시간선 질의.

🔴 DB 쓰기 0 — `bootstrap` 이 먼저 import 되어 PGOPTIONS=default_transaction_read_only=on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저
from backtest.concept_axes.minervini.cap_skip_ledger import classify as C
from backtest.concept_axes.minervini.cap_skip_ledger import tradecal as T
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

from . import fidelity8 as F
from . import livesignal8 as LS8
from . import logscan8 as L8
from . import registry as R
from . import sellprobe8 as SP
from . import sources8 as SRC8

CAL_START = date(2026, 6, 1)   # 달력·OHLC 읽기 시작(청산 충실도 창 08-26 보다 앞)


@dataclass
class TradeExtra:
    qty: int
    tp_rate: Optional[float]
    sl_rate: Optional[float]


@dataclass
class Ctx8:
    conn: Any
    calendar: List[date]
    log_dir: Path
    strategies: Dict[str, Any]
    trades: Dict[str, List[C.Trade]]
    extras: Dict[int, TradeExtra]
    windows: SRC8.WindowCache
    bars: Dict[str, Dict[date, Bar]] = field(default_factory=dict)
    logs: Dict[date, L8.DayLog] = field(default_factory=dict)
    snaps: Dict[Tuple[str, date], List[Dict]] = field(default_factory=dict)
    rules: Dict[str, Any] = field(default_factory=dict)     # folder → exitsim8.ExitRules
    probes: Dict[str, Any] = field(default_factory=dict)    # folder → sellprobe8.SellProbe

    @classmethod
    def open(cls, log_dir: Path) -> "Ctx8":
        conn = SRC8.connect()
        cal = SRC8.load_calendar(conn, CAL_START, date.today() + timedelta(days=1))
        strategies = {f: LS8.load8(f) for f in R.ALL_FOLDERS}
        raw = SRC8.load_trades8(conn, date.today())
        trades = {k: C.build_trades([r[:7] for r in v]) for k, v in raw.items()}
        extras = {int(r[0]): TradeExtra(int(r[7] or 0), r[8], r[9]) for v in raw.values() for r in v}
        return cls(conn, cal, Path(log_dir), strategies, trades, extras, SRC8.WindowCache())

    def attach_exit_probes(self) -> None:
        """라이브 청산 규칙(엔진 경로 tp/sl · 전략 매도 분기 탐침). 🔴 `_check_buy` 호출 «전»에 부른다
        (envelope 인스턴스가 QuantDailyReader 를 품기 전에 사본을 뜬다)."""
        for f in R.ALL_FOLDERS:
            self.rules[f] = SP.resolve_live_tp_sl(f, self.strategies[f])
            self.probes[f] = SP.SellProbe(f, self.strategies[f], self.windows.get)

    def close(self) -> None:
        self.conn.close()

    def log_for(self, d: date) -> L8.DayLog:
        if d not in self.logs:
            self.logs[d] = L8.scan_day(self.log_dir, d, R.ALL_FOLDERS, R.LOGGER_TO_FOLDER)
        return self.logs[d]

    def bars_for(self, code: str) -> Dict[date, Bar]:
        if code not in self.bars:
            self.bars[code] = SRC8.load_bars(self.conn, code, CAL_START)
        return self.bars[code]

    def snapshot(self, folder: str, scan_date: date) -> List[Dict]:
        key = (folder, scan_date)
        if key not in self.snaps:
            self.snaps[key] = SRC8.load_snapshot(self.conn, folder, scan_date)
        return self.snaps[key]

    def candidates(self, folder: str, d: date) -> Tuple[L8.CandList, Optional[date], Dict[str, Optional[int]]]:
        """(라이브 E6 목록 main/ext, 스캔일 D-1, 스냅샷 순위)."""
        scan = T.prev_trading_day(self.calendar, d)
        snap = self.snapshot(folder, scan) if scan else []
        dl = self.log_for(d)
        sd = dl.get(folder)
        cl = L8.live_candidate_list([r["code"] for r in snap], sd)
        if sd.e6 is not None and scan and sd.e6["d1"] != scan.isoformat():
            cl.src += f"·D-1_mismatch(log {sd.e6['d1']})"
        if not dl.found:
            cl.src += "·no_log_file"
        return cl, scan, {r["code"]: r["rank"] for r in snap}

    def path(self, code: str, d: date) -> List[Tuple[int, date, Optional[Bar]]]:
        """진입일 D(k=0)부터 달력(=DB KOSPI 최신 봉) 끝까지 [(k, 날짜, 봉|None)]."""
        bars = self.bars_for(code)
        days = [d] + T.days_after(self.calendar, d)
        return [(i, dd, bars.get(dd)) for i, dd in enumerate(days)]

    def first_tick(self, d: date) -> datetime:
        return datetime.combine(d, SRC8.FIRST_TICK)

    def slot_state(self, folder: str, code: str, d: date, list_order: List[str]) -> F.SlotVerdict:
        """그날 라이브가 이 종목을 `_check_buy` 까지 평가할 수 있었나 — 규칙은 `fidelity8.slot_verdict`(순수 ·
        v3 채택 · v1·v2 는 민감도). 이 메서드는 체결 원장·K 이력·그 전략 on_tick 완료 시각만 넘긴다."""
        k, _ = R.k_for(folder, d)
        mdt, _ = R.mdt_for(folder, d)
        return F.slot_verdict(self.trades.get(folder, []), d, k, mdt, code, list_order,
                              self.log_for(d).get(folder).ontick_times, SRC8.FIRST_TICK)

    def others_at(self, folder: str, code: str, t: datetime) -> List[str]:
        return C.other_holders(self.trades, code, t, exclude=folder)

    def buys_on(self, folder: str, d: date) -> List[C.Trade]:
        return [x for x in self.trades.get(folder, []) if x.buy_ts.date() == d]

    def last_close(self, code: str) -> Optional[Tuple[date, float]]:
        bars = self.bars_for(code)
        if not bars:
            return None
        d = max(bars)
        return d, float(bars[d].close)
