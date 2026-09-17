"""minervini 「자리 없어 못 산 후보」 원장 — CLI.

    cd RoboTrader_template   (워크트리)
    python -m backtest.concept_axes.minervini.cap_skip_ledger.run --start 2026-09-10 --end 2026-09-17
    python -m backtest.concept_axes.minervini.cap_skip_ledger.run --end 2026-09-18 --days 25   # 매일 EOD

출력(기본 `results/`): ledger.csv · fidelity_buys.csv · ledger_summary.md · run_meta.json
🔴 DB 쓰기 0 · 라이브 코드 수정 0 · 관측 원장이지 판정 근거가 아니다(README).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import bootstrap
from . import classify as C
from . import logscan as L
from . import sim as S
from . import tradecal as T

import pandas as pd  # noqa: E402

from . import livesignal as LS  # noqa: E402
from . import sources as SRC    # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "results"
FIDELITY_TRADING_DAYS = 30

ASSUMPTIONS = ("E=D시가(밴드안)|밴드경계(시가이탈·장중복귀)|불가; "
               "X=일봉고저터치·동일봉 손절우선·갭은 시가·보유기한 시가; %만(사이징·현금 무시)")

LEDGER_COLS = [
    "date", "scan_date", "code", "snap_rank", "list_pos", "list_src",
    "K", "n_open_0900", "restore_log_n", "slot_windows",
    "state", "state_ko", "state_note", "cap_log", "evidence", "other_holder",
    "signal", "signal_reason", "dryup_ratio", "near_threshold", "n_bars", "last_bar",
    "snap_score", "score_now_vs_snap", "vintage", "signal_used", "signal_basis",
    "ref_close", "band_max",
    "live_signal_log", "live_nosignal_log", "live_notes",
    "v_entry_status", "v_entry_basis", "v_entry_price", "v_entry_vs_ref_pct", "v_entry_note",
    "v_exit_status", "v_exit_reason", "v_exit_date", "v_exit_price", "v_ret_pct", "v_hold_days",
    "v_exit_note", "v_dup_of",
    "actual_buy_time", "actual_buy_price", "actual_exit_date", "actual_exit_price",
    "actual_exit_reason", "actual_ret_pct",
    "assumptions", "caveats",
]


def _fmt(x: Any, nd: int = 4) -> str:
    if x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{x:.0f}"
    return str(x)


def _pct(x: Optional[float]) -> str:
    return "" if x is None else f"{x:+.2f}"


def _actual_reason(reason: str) -> str:
    r = reason or ""
    if "익절" in r:
        return "tp"
    if "손절" in r:
        return "sl"
    if "보유기간" in r or "최대 보유" in r:
        return "max_hold"
    return r[:20]


@dataclass
class Ctx:
    conn: Any
    strategy: Any
    repo: Any
    calendar: List[date]
    trades_by_strategy: Dict[str, List[C.Trade]]
    log_dir: Path
    bars: Dict[str, Dict[date, S.Bar]] = field(default_factory=dict)
    logs: Dict[date, L.DayLog] = field(default_factory=dict)

    @property
    def trades(self) -> List[C.Trade]:
        return self.trades_by_strategy.get(SRC.STRATEGY, [])

    def others_at(self, code: str, t: datetime) -> List[str]:
        return C.other_holders(self.trades_by_strategy, code, t, exclude=SRC.STRATEGY)

    def bars_for(self, code: str) -> Dict[date, S.Bar]:
        if code not in self.bars:
            start = self.calendar[0] if self.calendar else date(2026, 1, 1)
            self.bars[code] = SRC.load_bars(self.conn, code, start)
        return self.bars[code]

    def log_for(self, d: date) -> L.DayLog:
        if d not in self.logs:
            self.logs[d] = L.scan_day(self.log_dir, d)
        return self.logs[d]


def _max_hold_fn(strategy, entry_price: float):
    def fn(k: int) -> bool:
        should, _, _ = type(strategy).evaluate_sell_conditions(
            df=pd.DataFrame(), entry_price=entry_price, hold_days=k,
            take_profit_pct=strategy._take_profit_pct, stop_loss_pct=strategy._stop_loss_pct,
            max_hold_days=strategy._max_hold_days)
        return bool(should)
    return fn


def build_day(ctx: Ctx, d: date) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    s = ctx.strategy
    scan_date = T.prev_trading_day(ctx.calendar, d)
    daylog = ctx.log_for(d)
    k, k_src = C.k_for(d)
    n0, windows = C.slot_windows_detail(ctx.trades, d, k, s._max_daily_trades)
    snap = SRC.load_snapshot(ctx.conn, scan_date) if scan_date else []
    snap_rank = {r["code"]: r["rank"] for r in snap}
    snap_score = {r["code"]: r["score"] for r in snap}
    codes, list_src = L.live_candidate_list([r["code"] for r in snap], daylog)
    if daylog.e6 is not None and scan_date and daylog.e6["d1"] != scan_date.isoformat():
        list_src += f"·D-1_mismatch(log {daylog.e6['d1']})"
    if not daylog.found:
        list_src += "·no_log_file"

    later_days = T.days_after(ctx.calendar, d)
    rows: List[Dict[str, str]] = []
    diag = dict(date=d, scan_date=scan_date, K=k, n_open_0900=n0, windows=windows,
                n_snapshot=len(snap), n_list=len(codes), list_src=list_src,
                restore=daylog.restore_minervini, e6=daylog.e6, evals={}, entries={}, states={})
    for pos, code in enumerate(codes, start=1):
        state, state_note = C.classify_candidate(code, d, ctx.trades, windows, list_order=codes)
        cap = C.cap_log_flag(d, code, daylog.cap)
        evidence = C.evidence_check(state, cap, windows)
        others = ctx.others_at(code, datetime.combine(d, SRC.FIRST_TICK))

        data, _wdiag = SRC.live_daily_window(code, d, repo=ctx.repo)
        ev = LS.evaluate(s, code, data)
        diag["evals"][code] = ev
        diag["states"][code] = state

        # 빈티지: 라이브 스캔 score(D 09:00) vs 지금 DB score
        sc_snap = snap_score.get(code)
        vint, vratio = "unknown", ""
        if sc_snap and ev.score_now:
            r_ = ev.score_now / float(sc_snap)
            vratio = f"{r_:.6f}"
            if abs(r_ - 1.0) <= 1e-6:
                vint = "same"
            elif abs(r_ - 1.0) <= 0.005:
                vint = f"minor({(r_ - 1) * 100:+.3f}%)"
            else:
                vint = f"changed({(r_ - 1) * 100:+.2f}%)"
        # 사용할 신호: 재현 Y → replay · 재현이 dryup 미충족인데 빈티지가 바뀌었으면 스냅샷 동등 Y
        sig_used, sig_basis = ev.signal, "replay"
        ref_used, band_min_used, band_max_used = ev.ref_close, ev.band_min, ev.band_max
        if ev.signal == "N" and ev.reason == "dryup_not_met" and vint not in ("same", "unknown"):
            sig_used, sig_basis = "Y", "snapshot_equiv"
            ref_used, band_min_used, band_max_used = LS.snapshot_equiv_band(s, data)
        diag.setdefault("used", {})[code] = (sig_used, sig_basis, ref_used, band_min_used, band_max_used)

        caveats: List[str] = []
        if sig_basis == "snapshot_equiv":
            caveats.append("재현은 dryup 미충족이나 D 09:00 라이브 스캔은 통과(빈티지 변경) → 라이브 시점 신호 Y 로 간주")
        elif vint.startswith("changed"):  # 0.5% 초과만 경고(minor 는 칸에만)
            caveats.append("D-1 이하 거래량이 라이브 스캔 뒤 재기록됨(score 불일치)")
        if ev.near_threshold:
            caveats.append("dryup 비율 0.68~0.72 경계 — 빈티지 차로 뒤집힐 수 있음")
        if others and state in (C.STATE_NO_SLOT, C.STATE_SLOT):
            caveats.append("다른 전략 보유 중 — 자리가 있어도 라이브는 매수 신호를 무시(bot/trading_analyzer.py:126-129)")
        if cap == "Y" and daylog.cap[code]["k"] != k:
            caveats.append(f"[캡] 로그 K={daylog.cap[code]['k']} ≠ 이력표 K={k}")

        row = OrderedDict((c, "") for c in LEDGER_COLS)
        row.update(
            date=d.isoformat(), scan_date=scan_date.isoformat() if scan_date else "", code=code,
            snap_rank=_fmt(snap_rank.get(code)), list_pos=str(pos), list_src=list_src,
            K=str(k), n_open_0900=str(n0),
            restore_log_n="" if daylog.restore_minervini is None else str(daylog.restore_minervini),
            slot_windows=C.fmt_windows(windows) or "(없음)",
            state=state, state_ko=C.STATE_LABEL_KO[state], state_note=state_note,
            cap_log=cap, evidence=evidence, other_holder=",".join(others),
            signal=ev.signal, signal_reason=ev.reason, dryup_ratio=ev.ratio_2dp,
            near_threshold="Y" if ev.near_threshold else "N",
            n_bars=str(ev.n_bars), last_bar=ev.last_bar,
            snap_score=_fmt(float(sc_snap), 2) if sc_snap is not None else "",
            score_now_vs_snap=vratio, vintage=vint, signal_used=sig_used, signal_basis=sig_basis,
            ref_close=_fmt(ref_used), band_max=_fmt(band_max_used, 2),
            live_signal_log=(lambda x: f"{x['time']} ref={x['ref']:g} ratio={x['ratio']}" if x else "")(
                daylog.signals.get(code)),
            live_nosignal_log=daylog.nosignal.get(code, ""),
            live_notes=" / ".join(daylog.notes.get(code, [])),
            assumptions=ASSUMPTIONS,
        )

        # 실제 체결(있으면)
        buys = [t for t in ctx.trades if t.code == code and t.buy_ts.date() == d]
        if buys:
            t = buys[0]
            row.update(actual_buy_time=f"{t.buy_ts:%H:%M:%S}", actual_buy_price=_fmt(t.buy_price))
            if t.sell_ts is not None:
                row.update(actual_exit_date=f"{t.sell_ts:%Y-%m-%d %H:%M:%S}",
                           actual_exit_price=_fmt(t.sell_price),
                           actual_exit_reason=_actual_reason(t.sell_reason),
                           actual_ret_pct=_pct((t.sell_price / t.buy_price - 1) * 100))
            else:
                row.update(actual_exit_reason="open")

        # 가상 진입·청산 — 샀을 신호 Y 이고 이미 보유가 아닌 행
        if sig_used == "Y" and state != C.STATE_HELD:
            bars = ctx.bars_for(code)
            ent = S.simulate_entry(bars.get(d), band_min_used, band_max_used)
            diag["entries"][code] = ent
            row.update(v_entry_status=ent.status, v_entry_basis=ent.basis,
                       v_entry_price=_fmt(ent.price), v_entry_note=ent.note)
            if ent.price is not None and ref_used:
                row["v_entry_vs_ref_pct"] = _pct((ent.price / ref_used - 1) * 100)
            if ent.status == S.ENTRY_FILLED:
                later = [(i + 1, bars.get(dd)) for i, dd in enumerate(later_days)]
                ex = S.simulate_exit(ent.price, ent.basis, bars.get(d), later,
                                     s._stop_loss_pct, s._take_profit_pct, _max_hold_fn(s, ent.price))
                row.update(v_exit_status=ex.status, v_exit_reason=ex.reason,
                           v_exit_date=ex.exit_date.isoformat() if ex.exit_date else "",
                           v_exit_price=_fmt(ex.price, 2), v_ret_pct=_pct(ex.ret_pct),
                           v_hold_days=_fmt(ex.hold_days), v_exit_note=" · ".join(ex.notes))
            if state == C.STATE_BOUGHT:
                caveats.append("실제 매수 행 — 가상값은 충실도 대조용")
        elif sig_used == "Y" and state == C.STATE_HELD:
            row.update(v_entry_status="n/a(이미 보유)")
        row["caveats"] = " | ".join(caveats)
        rows.append(row)
    return rows, diag


def predict_buys(ctx: Ctx, diag: Dict[str, Any]) -> List[str]:
    """«순위 순서 + 빈자리» 로 라이브가 샀을 종목을 예측(충실도 검증 전용).

    09:02 첫 틱: 빈자리만큼 목록 순서대로 [샀을신호 Y ∧ D 시가가 밴드 안] 종목.
    이후 기존 보유분 매도 시각마다 1자리씩: 목록 순서대로 [샀을신호 Y ∧ 체결 가능(시가 or 장중 복귀)].
    (쿨다운 60초·사이클 한도는 순서만 늦출 뿐 집합을 바꾸지 않는다고 본다.)
    """
    s = ctx.strategy
    d: date = diag["date"]
    k = diag["K"]
    t_open = datetime.combine(d, C.SESSION_OPEN)
    first = datetime.combine(d, SRC.FIRST_TICK)
    prior = [t for t in ctx.trades if t.buy_ts < t_open]
    n = len(C.open_at(prior, t_open))
    sells = sorted(t.sell_ts for t in prior if t.sell_ts is not None and t_open <= t.sell_ts < datetime.combine(d, C.SESSION_CLOSE))
    fills = 0
    order = [c for c in diag["states"] if diag["states"][c] != C.STATE_HELD]
    # 🔑 같은 날 이미 매도된 minervini 보유분은 COMPLETED 라 재매수 대상이 아니다(held 로 이미 빠짐).
    picked: List[str] = []

    def _ok(code: str, need_open: bool, t: datetime) -> bool:
        ent = diag["entries"].get(code)
        if diag["used"][code][0] != "Y" or ent is None or ent.status != S.ENTRY_FILLED:
            return False
        if ctx.others_at(code, t):          # 다른 전략 보유 → 라이브는 매수 신호 무시
            return False
        return (ent.basis == "D_open") if need_open else True

    for ts in [x for x in sells if x <= first]:
        n -= 1
        fills += 1
    for code in order:
        if n >= k or fills >= s._max_daily_trades:
            break
        if code not in picked and _ok(code, need_open=True, t=first):
            picked.append(code)
            n += 1
            fills += 1
    for ts in [x for x in sells if x > first]:
        n -= 1
        fills += 1
        for code in order:
            if n >= k or fills >= s._max_daily_trades:
                break
            if code not in picked and _ok(code, need_open=False, t=ts):
                picked.append(code)
                n += 1
                fills += 1
    return picked


# ────────────────────────────────────────────────────────────────────────────
# 원장 I/O — 날짜 단위 재생성(멱등)
# ────────────────────────────────────────────────────────────────────────────
def _atomic_write_csv(path: Path, cols: Sequence[str], rows: Sequence[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols), extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def merge_ledger(path: Path, new_rows: List[Dict[str, str]], regenerated: Sequence[date]) -> List[Dict[str, str]]:
    keep: List[Dict[str, str]] = []
    regen = {x.isoformat() for x in regenerated}
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as fh:
            keep = [r for r in csv.DictReader(fh) if r.get("date") not in regen]
    allrows = keep + list(new_rows)
    allrows.sort(key=lambda r: (r["date"], int(r["list_pos"] or 0), r["code"]))
    _mark_dups(allrows)
    _atomic_write_csv(path, LEDGER_COLS, allrows)
    return allrows


def _mark_dups(rows: List[Dict[str, str]]) -> None:
    """같은 종목의 앞선 «가상 진입»이 아직 열려 있는 날의 행에 `v_dup_of` 표시(합산 중복 방지)."""
    live: Dict[str, Tuple[str, str]] = {}
    for r in rows:
        r["v_dup_of"] = ""
        if r.get("v_entry_status") != S.ENTRY_FILLED or r.get("state") == C.STATE_BOUGHT:
            continue
        prev = live.get(r["code"])
        if prev is not None:
            p_date, p_exit = prev
            if p_exit == "" or r["date"] <= p_exit:
                r["v_dup_of"] = p_date
                continue
        live[r["code"]] = (r["date"], r.get("v_exit_date", "") if r.get("v_exit_status") == "closed" else "")


# ────────────────────────────────────────────────────────────────────────────
# 충실도 검증
# ────────────────────────────────────────────────────────────────────────────
FID_COLS = ["date", "code", "in_list", "list_pos", "state", "signal", "signal_reason",
            "live_log_ratio", "replay_ratio", "live_log_ref", "replay_ref", "log_match",
            "predicted", "v_entry_basis", "v_entry_price", "actual_buy_price", "entry_diff_pct",
            "v_exit_reason", "v_exit_date", "v_ret_pct", "actual_exit_reason", "actual_exit_date",
            "actual_ret_pct", "exit_match", "note"]


def fidelity(ctx: Ctx, days: Sequence[date]) -> Dict[str, Any]:
    buys_by_day: Dict[date, List[C.Trade]] = {}
    for t in ctx.trades:
        if t.buy_ts.date() in set(days):
            buys_by_day.setdefault(t.buy_ts.date(), []).append(t)
    rows: List[Dict[str, str]] = []
    day_rows: List[Dict[str, Any]] = []
    siglog = dict(n=0, replay_y=0, ratio_eq=0, ref_eq=0, mismatches=[])
    for d in days:
        built, diag = build_day(ctx, d)
        by_code = {r["code"]: r for r in built}
        daylog = ctx.log_for(d)
        # (a) 라이브 «매수 시그널» 로그 줄 vs 재현 — 목록 안 종목 전부(매수 여부 무관)
        for code, lg in daylog.signals.items():
            if code not in by_code:
                continue
            ev = diag["evals"][code]
            siglog["n"] += 1
            y = ev.signal == "Y"
            r_eq = y and ev.ratio_2dp == lg["ratio"]
            f_eq = y and ev.ref_close is not None and abs(ev.ref_close - lg["ref"]) < 0.5
            siglog["replay_y"] += int(y)
            siglog["ratio_eq"] += int(r_eq)
            siglog["ref_eq"] += int(f_eq)
            if not (y and r_eq and f_eq):
                siglog["mismatches"].append(
                    f"{d} {code}: live ratio={lg['ratio']} ref={lg['ref']:g} / replay {ev.signal} "
                    f"ratio={ev.ratio_2dp} ref={_fmt(ev.ref_close)} ({ev.reason[:40]})")
        actual = buys_by_day.get(d, [])
        if not actual:
            continue
        pred = predict_buys(ctx, diag)
        a_codes = [t.code for t in actual]
        t_open = datetime.combine(d, C.SESSION_OPEN)
        held_codes = {x.code for x in C.open_at(ctx.trades, t_open)}
        # 캡 미작동 증거: 이미 보유 중인 종목에 대해 minervini 가 «매수 시그널»을 냈다
        #   = 전략 `self.positions` 가 비어 있었다(보유면 `_check_sell` 로 가야 한다 · strategy.py:152)
        held_sig = sorted(c for c in daylog.signals if c in held_codes)
        day_rows.append(dict(date=d, actual=a_codes, predicted=pred,
                             both=sorted(set(a_codes) & set(pred)),
                             only_actual=sorted(set(a_codes) - set(pred)),
                             only_pred=sorted(set(pred) - set(a_codes)),
                             K=diag["K"], n_open=diag["n_open_0900"], windows=C.fmt_windows(diag["windows"]),
                             held_sig=held_sig))
        for t in actual:
            r = by_code.get(t.code)
            lg = daylog.signals.get(t.code)
            out = OrderedDict((c, "") for c in FID_COLS)
            out.update(date=d.isoformat(), code=t.code, actual_buy_price=_fmt(t.buy_price),
                       predicted="Y" if t.code in pred else "N")
            notes_ = []
            if t.buy_ts > datetime.combine(d, SRC.FIRST_TICK) + timedelta(minutes=3):  # 09:05 초과
                notes_.append(f"체결 {t.buy_ts:%H:%M}(첫 틱 이후) - D 시가 기준 가상 진입가와 구조적 차")
            if held_sig:
                notes_.append(f"캡 미작동일(보유종목 매수시그널 {len(held_sig)})")
            out["note"] = " · ".join(notes_)
            if t.sell_ts is not None:
                out.update(actual_exit_reason=_actual_reason(t.sell_reason),
                           actual_exit_date=f"{t.sell_ts:%Y-%m-%d}",
                           actual_ret_pct=_pct((t.sell_price / t.buy_price - 1) * 100))
            else:
                out.update(actual_exit_reason="open")
            if r is None:
                out.update(in_list="N", note=(out["note"] + " · " if out["note"] else "") + "라이브 E6 목록 재구성에 없음")
                rows.append(out)
                continue
            ev = diag["evals"][t.code]
            out.update(in_list="Y", list_pos=r["list_pos"], state=r["state"], signal=r["signal"],
                       signal_reason=r["signal_reason"][:40], replay_ratio=ev.ratio_2dp,
                       replay_ref=_fmt(ev.ref_close), v_entry_basis=r["v_entry_basis"],
                       v_entry_price=r["v_entry_price"], v_exit_reason=r["v_exit_reason"],
                       v_exit_date=r["v_exit_date"], v_ret_pct=r["v_ret_pct"])
            if lg:
                out.update(live_log_ratio=lg["ratio"], live_log_ref=_fmt(lg["ref"]),
                           log_match="Y" if (ev.ratio_2dp == lg["ratio"] and ev.ref_close is not None
                                             and abs(ev.ref_close - lg["ref"]) < 0.5) else "N")
            else:
                out.update(log_match="no_log")
            if r["v_entry_price"]:
                out["entry_diff_pct"] = _pct((float(r["v_entry_price"]) / t.buy_price - 1) * 100)
            ar, vr = out["actual_exit_reason"], r["v_exit_reason"]
            if ar == "open" and vr == "open":
                out["exit_match"] = "both_open"
            elif ar == "open" or vr in ("", "open"):
                out["exit_match"] = "N(한쪽만 종료)"
            else:
                same_reason = ar == vr
                same_date = out["actual_exit_date"] == r["v_exit_date"]
                out["exit_match"] = ("Y" if same_reason and same_date else
                                     "reason_only" if same_reason else "N")
            rows.append(out)
    return dict(rows=rows, days=day_rows, siglog=siglog)


# ────────────────────────────────────────────────────────────────────────────
# 요약 MD
# ────────────────────────────────────────────────────────────────────────────
def _md_table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |")
    return "\n".join(out)


def render_md(ledger: List[Dict[str, str]], fid: Dict[str, Any], meta: Dict[str, Any]) -> str:
    frows = fid["rows"]
    n_buy = len(frows)
    n_in = sum(1 for r in frows if r["in_list"] == "Y")
    n_sig = sum(1 for r in frows if r["signal"] == "Y")
    n_pred = sum(1 for r in frows if r["predicted"] == "Y")
    n_state = sum(1 for r in frows if r["state"] == C.STATE_BOUGHT)
    lm = [r for r in frows if r["log_match"] in ("Y", "N")]
    n_lm = sum(1 for r in lm if r["log_match"] == "Y")
    diffs = [abs(float(r["entry_diff_pct"])) for r in frows if r["entry_diff_pct"]]
    diffs_first = [abs(float(r["entry_diff_pct"])) for r in frows
                   if r["entry_diff_pct"] and "첫 틱 이후" not in r["note"]]
    closed = [r for r in frows if r["actual_exit_reason"] not in ("", "open")]
    ex_y = sum(1 for r in closed if r["exit_match"] == "Y")
    ex_reason = sum(1 for r in closed if r["exit_match"] in ("Y", "reason_only"))
    sl = fid["siglog"]
    days = fid["days"]
    n_actual_total = sum(len(x["actual"]) for x in days)
    n_both_total = sum(len(x["both"]) for x in days)
    n_pred_total = sum(len(x["predicted"]) for x in days)

    reprod = (n_both_total / n_actual_total) if n_actual_total else 0.0
    cap_ok_days = [x for x in days if not x["held_sig"]]
    n_act_ok = sum(len(x["actual"]) for x in cap_ok_days)
    n_both_ok = sum(len(x["both"]) for x in cap_ok_days)
    ok_rate = f" = {n_both_ok / n_act_ok:.0%}" if n_act_ok else ""
    split_line = (f"- 구간 분리: 캡 작동일(보유종목 매수시그널 0) {len(cap_ok_days)}일 재현 {n_both_ok}/{n_act_ok}{ok_rate}"
                  f" · 캡 미작동일 {len(days) - len(cap_ok_days)}일 "
                  f"재현 {n_both_total - n_both_ok}/{n_actual_total - n_act_ok} "
                  "(미작동일 = 전략 positions 가 비어 보유 종목에도 매수 시그널이 난 날 → K 캡이 매수를 막지 않았다)")
    sig_rate = (sl["ratio_eq"] / sl["n"]) if sl["n"] else 0.0
    low = reprod < 0.8 or sig_rate < 0.9 or (n_sig / n_buy if n_buy else 0) < 0.9
    L_ = []
    L_.append("# minervini 「자리 없어 못 산 후보」 관측 원장 — 요약")
    L_.append("")
    L_.append("> 관측 원장이다. **판정 근거로 쓰지 말 것.** 사이징·현금·장중 체결·빈티지를 무시한 일봉 근사이며 결과는 % 뿐이다.")
    L_.append(f"> 생성 {meta['run_ts']} · git `{meta['git_sha']}` · 원장 범위 {meta['ledger_range']} · "
              f"충실도 창 {meta['fidelity_range']}(최근 {FIDELITY_TRADING_DAYS}거래일)")
    L_.append("")
    if low:
        L_.append("## [원장 신뢰도 낮음]")
        L_.append("")
        L_.append(f"- 예측 매수 재현 {n_both_total}/{n_actual_total} = {reprod:.0%} (기준 80%) · "
                  f"라이브 신호로그 비율 일치 {sl['ratio_eq']}/{sl['n']} = {sig_rate:.0%} (기준 90%) · "
                  f"실제 매수의 샀을신호 재현 {n_sig}/{n_buy}")
        L_.append(split_line)
        L_.append("- 원인은 아래 §2 불일치 목록 참조. 원장 수치를 인용할 때 이 머리말을 함께 옮길 것.")
    else:
        L_.append("## 원장 신뢰도: 충실도 기준 통과(관측용)")
        L_.append("")
        L_.append(f"- 예측 매수 재현 {n_both_total}/{n_actual_total} = {reprod:.0%} · 라이브 신호로그 비율 일치 "
                  f"{sl['ratio_eq']}/{sl['n']} = {sig_rate:.0%} · 실제 매수의 샀을신호 재현 {n_sig}/{n_buy}")
        L_.append(split_line)
        L_.append("- 통과는 «후보·신호 재현»에 대한 것이다. 가상 청산은 일봉 근사라 실제와 다를 수 있다(§2-3).")
    L_.append("")

    # §1 원장 요약
    L_.append("## 1. 원장 — 날짜별")
    L_.append("")
    by_day: Dict[str, List[Dict[str, str]]] = OrderedDict()
    for r in ledger:
        by_day.setdefault(r["date"], []).append(r)
    trs = []
    for d, rs in by_day.items():
        cnt = lambda st: sum(1 for r in rs if r["state"] == st)  # noqa: E731
        nb = [r for r in rs if r["state"] in (C.STATE_NO_SLOT, C.STATE_SLOT)]
        sig_y = [r for r in nb if r["signal_used"] == "Y"]
        n_equiv = sum(1 for r in sig_y if r["signal_basis"] == "snapshot_equiv")
        filled = [r for r in sig_y if r["v_entry_status"] == S.ENTRY_FILLED]
        fresh = [r for r in filled if not r["v_dup_of"]]
        res: Dict[str, int] = {}
        for r in fresh:
            res[r["v_exit_reason"]] = res.get(r["v_exit_reason"], 0) + 1
        n_other = sum(1 for r in sig_y if r["other_holder"])
        trs.append([d, rs[0]["scan_date"], len(rs), rs[0]["K"], rs[0]["n_open_0900"], rs[0]["slot_windows"],
                    cnt(C.STATE_BOUGHT), cnt(C.STATE_HELD), cnt(C.STATE_NO_SLOT), cnt(C.STATE_SLOT),
                    f"{len(sig_y)}" + (f"(스냅샷동등 {n_equiv})" if n_equiv else ""), n_other,
                    f"{len(filled)}(신규 {len(fresh)})",
                    " ".join(f"{k}{v}" for k, v in sorted(res.items())) or "-"])
    L_.append(_md_table(["D", "스냅샷일", "목록", "K", "09:00 보유", "빈자리 구간", "실제매수", "이미보유",
                         "자리없음", "자리있었음", "샀을신호Y(미매수)", "그중 타전략보유", "가상체결",
                         "가상결과(신규)"], trs))
    L_.append("")
    L_.append("- `가상결과(신규)` = 같은 종목의 앞선 가상 포지션이 아직 열린 날의 행(`v_dup_of`)을 뺀 것 · "
              "`tp`/`sl`/`max_hold` 종료 · `open` 보유 중(마지막 종가 평가).")
    L_.append("")
    L_.append("### 1-1. 샀을 신호 Y 인데 매수 안 된 후보")
    L_.append("")
    drows = []
    for r in ledger:
        if r["state"] in (C.STATE_NO_SLOT, C.STATE_SLOT) and r["signal_used"] == "Y":
            drows.append([r["date"], r["code"], r["list_pos"], r["state_ko"], r["cap_log"],
                          r["other_holder"] or "-", r["signal_basis"], r["dryup_ratio"], r["vintage"],
                          r["near_threshold"], f"{r['v_entry_status']}/{r['v_entry_basis']}",
                          r["v_entry_price"], r["v_entry_vs_ref_pct"],
                          r["v_exit_reason"], r["v_exit_date"], r["v_ret_pct"], r["v_hold_days"],
                          r["v_dup_of"] or "-", (r["live_notes"] or r["evidence"])[:60]])
    L_.append(_md_table(["D", "종목", "순위", "상태", "[캡]", "타전략보유(09:02)", "신호근거", "비율(지금DB)", "빈티지", "경계", "가상진입", "진입가",
                         "ref대비%", "청산", "청산일", "수익률%", "보유일", "중복(앞선 진입일)", "메모"], drows)
              if drows else "(없음)")
    L_.append("")
    nrows = [[r["date"], r["code"], r["state_ko"], r["signal_reason"][:50], r["dryup_ratio"], r["vintage"],
              r["signal_used"], r["signal_basis"]]
             for r in ledger if r["signal"] == "N"]
    L_.append("### 1-2. 재현 신호 N — 지금 DB 기준 `_check_buy` 가 None (사용 신호·근거 병기)")
    L_.append("")
    L_.append(_md_table(["D", "종목", "상태", "재현 사유", "비율(지금DB)", "빈티지", "사용 신호", "근거"], nrows)
              if nrows else "(없음)")
    L_.append("")

    # §2 충실도
    L_.append("## 2. 충실도 검증 — 실제 매수일 재현")
    L_.append("")
    L_.append("### 2-1. 요약")
    L_.append("")
    L_.append(_md_table(["항목", "값"], [
        ["실제 minervini BUY(창 안)", n_buy],
        ["라이브 E6 목록 재구성에 포함", f"{n_in}/{n_buy}"],
        ["상태 분류 = 실제 매수됨", f"{n_state}/{n_buy}"],
        ["샀을 신호 재현(Y)", f"{n_sig}/{n_buy}"],
        ["라이브 신호로그와 비율·기준가 일치(매수 건 중 로그 있는 건)", f"{n_lm}/{len(lm)}"],
        ["라이브 신호로그 전체 대조(목록 안 모든 종목-일)", f"비율 {sl['ratio_eq']}/{sl['n']} · 기준가 {sl['ref_eq']}/{sl['n']} · 재현Y {sl['replay_y']}/{sl['n']}"],
        ["예측 매수 집합 = 실제(날짜 합)", f"교집합 {n_both_total} · 실제 {n_actual_total} · 예측 {n_pred_total}"],
        ["가상 진입가(D 시가) vs 실제 체결가 |차| 평균·최대 — 전체", (f"{sum(diffs)/len(diffs):.2f}% · {max(diffs):.2f}% (n={len(diffs)})" if diffs else "-")],
        ["같은 값 — 첫 틱(≤09:05) 체결 건만", (f"{sum(diffs_first)/len(diffs_first):.2f}% · {max(diffs_first):.2f}% (n={len(diffs_first)})" if diffs_first else "-")],
        ["실제 종료 건 중 가상 청산 사유·날짜 일치", f"{ex_y}/{len(closed)} (사유만 {ex_reason}/{len(closed)})"],
    ]))
    L_.append("")
    L_.append("### 2-2. 날짜별 예측 매수 vs 실제")
    L_.append("")
    L_.append(_md_table(["D", "K", "09:00 보유", "빈자리 구간", "실제", "예측", "실제만", "예측만",
                         "캡 미작동 증거(보유종목 매수시그널)"],
                        [[x["date"], x["K"], x["n_open"], x["windows"] or "(없음)", ",".join(x["actual"]),
                          ",".join(x["predicted"]) or "-", ",".join(x["only_actual"]) or "-",
                          ",".join(x["only_pred"]) or "-",
                          (f"{len(x['held_sig'])}: " + ",".join(x["held_sig"])) if x["held_sig"] else "0"]
                         for x in days]))
    L_.append("")
    L_.append("### 2-3. 실제 매수 건별")
    L_.append("")
    L_.append(_md_table(["D", "종목", "목록", "순위", "신호", "로그비율/재현", "로그일치", "예측", "가상진입(basis)",
                         "실제체결", "진입차%", "가상청산", "실제청산", "청산일치", "비고"],
                        [[r["date"], r["code"], r["in_list"], r["list_pos"], r["signal"],
                          f"{r['live_log_ratio'] or '-'}/{r['replay_ratio'] or '-'}", r["log_match"], r["predicted"],
                          f"{r['v_entry_price']}({r['v_entry_basis']})", r["actual_buy_price"], r["entry_diff_pct"],
                          f"{r['v_exit_reason']} {r['v_exit_date']} {r['v_ret_pct']}",
                          f"{r['actual_exit_reason']} {r['actual_exit_date']} {r['actual_ret_pct']}",
                          r["exit_match"], r["note"]] for r in frows]))
    L_.append("")
    if sl["mismatches"]:
        L_.append("### 2-4. 라이브 신호로그 불일치")
        L_.append("")
        for m in sl["mismatches"]:
            L_.append(f"- {m}")
        L_.append("")
    L_.append("## 3. 가정·한계")
    L_.append("")
    for line in meta["limits"]:
        L_.append(f"- {line}")
    L_.append("")
    return "\n".join(L_)


LIMITS = [
    "라이브 일봉 재현은 `PriceRepository.get_daily_prices`+`_drop_unconfirmed_today_bar` 를 시계만 D 09:02 로 바꿔 호출한다. "
    "D-1 이하 봉의 «값»은 지금 DB 빈티지다 — D 15:3x 이후 재기록(시간외 합산 등, replayer/TRACE_M4_channel_2026-09-15.md)이 있으면 "
    "거래량 비율이 라이브와 달라질 수 있다(경계 0.68~0.72 는 `near_threshold`).",
    "후보 목록 = `screener_snapshots`(scan_date=직전 거래일) 순위순 − 로그의 안전필터 제외 → 로그 `목표 N건`. "
    "섹터뉴스 재정렬은 기본 shadow(순서 불변) 가정.",
    "자리 = `virtual_trading_records` 체결 시각으로 그린 보유 수 시간선(K 이력표) + 체결 수 한도(max_daily_trades). "
    "`[캡]` 로그는 2026-09-16 부터만 있어 교차 증거로만 쓴다.",
    "샀을 신호 = 라이브 `_check_buy`(MarketHours 만 True 로 고정). 시장급락 게이트·국면 게이트·VI·상한가 접근·쿨다운·"
    "일일 손실 한도·현금/수량 부족은 «재현하지 않는다» → 샀을 신호 Y ≠ 살 수 있었다.",
    "다른 전략이 같은 종목을 들고 있으면(`other_holder`) 라이브는 minervini 에 자리가 있어도 매수 신호를 무시한다"
    "(bot/trading_analyzer.py:126-129). 원장은 표시만 하고 가상 진입은 그대로 계산한다(예측 매수에서는 제외).",
    "2026-08 초(충실도 창 앞부분)는 전략 `positions` 가 비어 K 캡이 매수를 막지 않은 날이 있다(보유 종목에도 매수 시그널). "
    "그날들은 «자리» 모델(체결 원장 시간선)이 라이브와 다르므로 §2-2 `캡 미작동 증거` 로 따로 센다.",
    "가상 진입 = D 일봉 시가(밴드 안) · 시가가 밴드 밖이고 장중 복귀면 밴드 경계값(시각 불명) · 장중 내내 밖이면 체결 불가. "
    "라이브는 첫 틱(≈09:02) 실시간가로 체결한다.",
    "가상 청산 = 일봉 고저 «터치». 라이브 position_monitor 는 주기 폴링이라 짧은 꼬리(예: 241710 2026-09-10 10:15 1분봉 저가)를 "
    "못 볼 수 있다 → 가상 손절이 실제보다 많을 수 있다. 같은 봉 손절·익절 동시 터치는 손절 우선. 체결가는 경계값(갭은 시가) — "
    "라이브는 넘어선 실시간가로 체결한다(예: 익절 +14.15%).",
    "2026-08-25 이전 매도는 전략 `_check_sell` 의 D-1 종가 sl/tp(1810cd2 로 제거)도 섞여 있어 청산 대조가 흐려진다. "
    "TT 게이트 on(86ff02d, 08-25) 전후로 스냅샷 크기가 20→2~11 로 바뀌었다.",
    "사이징·현금·자리 경쟁(가상 포지션끼리)·수수료·세금 무시 · 결과는 % 뿐(원화 환산 금지) · 같은 종목 연일 신호는 `v_dup_of` 로 표시만.",
    "생존편향·adj_factor 계열 결함(병합·감자 미조정·정지 패딩)은 그대로다.",
]


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(HERE),
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _resolve_log_dir(arg: Optional[str]) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("CAPLEDGER_LOG_DIR")
    if env:
        return Path(env)
    local = bootstrap.ROOT / "logs"
    if list(local.glob("robotrader_template_*.log")):
        return local
    return bootstrap.LIVE_LOG_DIR_DEFAULT


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="minervini 자리 없어 못 산 후보 원장")
    ap.add_argument("--start", help="YYYY-MM-DD (생략 시 --end 에서 --days 거래일 역산)")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=1, help="--start 생략 시 재생성할 거래일 수(기본 1)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--log-dir", default=None, help="라이브 로그 폴더(읽기 전용)")
    ap.add_argument("--no-fidelity", action="store_true", help="충실도 검증 생략(요약 §2 는 이전 결과 없음으로 표기)")
    a = ap.parse_args(argv)

    end = date.fromisoformat(a.end)
    out = Path(a.out)
    log_dir = _resolve_log_dir(a.log_dir)
    conn = SRC.connect()
    try:
        cal = SRC.load_calendar(conn, end - timedelta(days=400), date.today() + timedelta(days=1))
        if a.start:
            days = T.days_in_range(cal, date.fromisoformat(a.start), end)
        else:
            days = T.last_n_days(cal, end, a.days)
        if not days:
            print(f"거래일 없음: {a.start} ~ {end}")
            return 2
        strategy = LS.load_strategy()
        k_latest = sorted(C.K_HISTORY)[-1][1]
        warn = []
        if k_latest != strategy._max_positions:
            warn.append(f"K 이력표 최신값({k_latest}) ≠ config.yaml max_positions({strategy._max_positions}) — "
                        f"K 가 바뀌었으면 classify.K_HISTORY 에 발효일과 함께 추가할 것")
        tbs = {k_: C.build_trades(v) for k_, v in
               SRC.load_trade_rows_by_strategy(conn, date.today()).items()}
        ctx = Ctx(conn=conn, strategy=strategy, repo=SRC._price_mod.PriceRepository(),
                  calendar=cal, trades_by_strategy=tbs, log_dir=log_dir)
        print(f"로그 폴더: {log_dir} · 재생성 {days[0]}~{days[-1]} ({len(days)}거래일)")
        new_rows: List[Dict[str, str]] = []
        for d in days:
            rows, diag = build_day(ctx, d)
            new_rows += rows
            print(f"  {d} scan={diag['scan_date']} 목록 {diag['n_list']}({diag['list_src']}) K={diag['K']} "
                  f"09:00보유={diag['n_open_0900']}(로그 {diag['restore']}) 빈자리={C.fmt_windows(diag['windows']) or '-'}")
        ledger = merge_ledger(out / "ledger.csv", new_rows, days)

        fid_days = T.last_n_days(cal, end, FIDELITY_TRADING_DAYS)
        if a.no_fidelity:
            fid = dict(rows=[], days=[], siglog=dict(n=0, replay_y=0, ratio_eq=0, ref_eq=0, mismatches=[]))
        else:
            fid = fidelity(ctx, fid_days)
            _atomic_write_csv(out / "fidelity_buys.csv", FID_COLS, fid["rows"])
    finally:
        conn.close()

    all_dates = sorted({r["date"] for r in ledger})
    meta = dict(run_ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), git_sha=_git_sha(),
                ledger_range=f"{all_dates[0]}~{all_dates[-1]}" if all_dates else "-",
                fidelity_range=f"{fid_days[0]}~{fid_days[-1]}", log_dir=str(log_dir),
                db=bootstrap.DB_NAME, regenerated=[x.isoformat() for x in days],
                warnings=warn, limits=LIMITS)
    md = render_md(ledger, fid, meta)
    if warn:
        md = "\n".join(f"> [경고] {w}" for w in warn) + "\n\n" + md
    _atomic_write_text(out / "ledger_summary.md", md)
    _atomic_write_text(out / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))
    print(f"원장 {len(ledger)}행 → {out / 'ledger.csv'}")
    print(f"요약 → {out / 'ledger_summary.md'}")
    for w in warn:
        print(f"[경고] {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
