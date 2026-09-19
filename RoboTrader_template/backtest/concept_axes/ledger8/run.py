"""ledger8 — 8전략 세 arm(A 라이브 · B1 로트 독립 · B2 평단 합산) 관측 원장 CLI.

    cd <worktree>/RoboTrader_template
    PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe
    $PY -m backtest.concept_axes.ledger8.run --stage signal       # ② 신호 충실도(B 계산 «전에» 본다)

🔴 DB 쓰기 0 · 라이브 코드 0줄 · 관측 원장이다 — 판정 근거로 쓰지 말 것.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import os
import subprocess
import tempfile
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap
from backtest.concept_axes.minervini.cap_skip_ledger import classify as C
from backtest.concept_axes.minervini.cap_skip_ledger import tradecal as T
from backtest.concept_axes.minervini.cap_skip_ledger import sim as S
from config.constants import PRICE_LIMIT_GUARD_RATE                  # noqa: E402  (bootstrap 뒤)
from core.models import TradingStock                                 # noqa: E402
from core.regime.market_classifier import resolve_regime_index       # noqa: E402

from . import arms as A
from . import exitsim8 as X
from . import fidelity8 as F
from . import livesignal8 as LS8
from . import logscan8 as L8
from . import registry as R
from . import sizing as Z
from . import sources8 as SRC8
from . import stages as ST
from .context8 import Ctx8

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "results"
BANNER = "관측 원장이다 — 판정 근거로 쓰지 말 것."


# ── 서식·I/O ─────────────────────────────────────────────────────────────
def _fmt(x: Any, nd: int = 4) -> str:
    if x is None:
        return ""
    if isinstance(x, bool):
        return "Y" if x else "N"
    if isinstance(x, float):
        return f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return str(x)


def _pct(x: Optional[float]) -> str:
    return "" if x is None else f"{x:+.2f}"


def _won_str(x: Optional[float]) -> str:
    return "" if x is None else str(int(round(x)))


def _yn(cond: Optional[bool]) -> str:
    return "" if cond is None else ("Y" if cond else "N")


def _atomic_write_csv(path: Path, cols: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
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


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(HERE),
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _resolve_log_dir(arg: Optional[str]) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("LEDGER8_LOG_DIR")
    if env:
        return Path(env)
    local = bootstrap.ROOT / "logs"
    if list(local.glob("robotrader_template_*.log")):
        return local
    return bootstrap.LIVE_LOG_DIR_DEFAULT


def _meta(days: Sequence[date], log_dir: Path, stage: str, warnings: Sequence[str]) -> Dict[str, Any]:
    return dict(banner=BANNER, run_ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), git_sha=_git_sha(),
                db=bootstrap.DB_NAME, log_dir=str(log_dir), stage=stage,
                window=f"{days[0]}~{days[-1]}", n_days=len(days), warnings=list(warnings))


# ── ② 신호 ────────────────────────────────────────────────────────────────
SIG_COLS = ["date", "strategy", "mode", "code", "list_pos", "slot_state", "slot_state_v2", "eval_v1",
            "signal_replay", "replay_reason", "signal_log", "signal_log_v1", "signal_log_v2", "n_evals", "first_ts",
            "last_ts", "outcome", "outcome_v1", "outcome_v2", "no_slot_but_log_y", "no_slot_but_log_y_v2",
            "reasons_equal", "ref_equal", "receipt_ref", "replay_ref", "signal_basis", "vol_ratio", "vol_threshold",
            "rule_margin_pct", "vintage_fragile"]
OFF_COLS = ["date", "strategy", "n_offlist", "codes"]


def evaluate_candidates(ctx: Ctx8, days: Sequence[date]
                        ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], Dict[str, Any]]:
    """(후보 행, E6 목록 밖 `[on_tick] 매수신호` 집계, 관측 빈티지). 후보 = D1 main + ext.

    «평가 가능» = `fidelity8.slot_verdict` v3(채택) ∧ 그날 `[캡]` 줄(3전략·09-16~) 없음. v1·v2 결과도 행에 남긴다(민감도).
    """
    cands: List[Dict[str, Any]] = []
    offlist: List[Dict[str, str]] = []
    for d in days:
        dl = ctx.log_for(d)
        for folder in R.ALL_FOLDERS:
            sd = dl.get(folder)
            cl, scan, ranks = ctx.candidates(folder, d)
            order = cl.main + cl.ext
            strat = ctx.strategies[folder]
            ran = sd.ontick_runs > 0
            off = sorted(set(sd.buysig) - set(cl.main))
            if off:
                offlist.append(dict(date=d.isoformat(), strategy=folder, n_offlist=str(len(off)), codes=",".join(off)))
            for tier, codes in ((R.TIER_MAIN, cl.main), (R.TIER_EXT, cl.ext)):
                for pos_, code in enumerate(codes, start=1):
                    data, _ = ctx.windows.get(code, d)
                    ev = LS8.evaluate8(strat, folder, code, d, data)
                    sv = ctx.slot_state(folder, code, d, order)
                    capblk = bool(sd.cap_blocking(code))
                    bs = sd.buysig.get(code) if tier == R.TIER_MAIN else None
                    rc = sd.receipt.get(code) if tier == R.TIER_MAIN else None
                    if tier == R.TIER_MAIN:
                        slog = F.signal_log_state(bs is not None, ran, sv.state in F.EVALUABLE_STATES and not capblk)
                        slog_v2 = F.signal_log_state(bs is not None, ran,
                                                     sv.state_v2 in F.EVALUABLE_STATES and not capblk)
                        slog_v1 = F.signal_log_state(bs is not None, ran, sv.eval_v1 and not capblk)
                    else:
                        slog = slog_v2 = slog_v1 = F.LOG_NA
                    used, basis = F.decide_signal(ev.signal, slog)
                    vm = LS8.volume_margin(folder, data, ev)
                    cands.append(dict(
                        d=d, folder=folder, code=code, tier=tier,
                        list_pos=pos_ if tier == R.TIER_MAIN else len(cl.main) + pos_,
                        snap_rank=ranks.get(code), list_src=cl.src, scan_date=scan, sector_mode=sd.sector_mode,
                        held=(sv.state == C.STATE_HELD), no_slot=(sv.state == C.STATE_NO_SLOT), slot_state=sv.state,
                        slot_state_v2=sv.state_v2, eval_v1=sv.eval_v1, slot_note=sv.note, ev=ev, buysig=bs,
                        receipt=rc, signal_log=slog, signal_log_v1=slog_v1, signal_log_v2=slog_v2,
                        signal_used=used, signal_basis=basis,
                        vol_ratio=vm[0] if vm else None, vol_threshold=vm[1] if vm else None,
                        reasons_equal=(_yn(bs.detail.get("reasons") == ev.reasons_str)
                                       if (bs is not None and ev.signal == "Y") else ""),
                        ref_equal=(_yn(abs(float(rc.detail["ref"]) - ev.ref) < 0.5)
                                   if (rc is not None and ev.ref is not None) else "")))
    # 관측 빈티지 — day 의 라이브 사유 `vol=a/b` 와 재현 사유를 맞대 D-1 거래량 재기록 폭을 잰다(데이터로 · 하드코딩 없음)
    pairs = [F.day_volume_vintage(c["buysig"].detail.get("reasons"), c["ev"].reasons_str) for c in cands
             if c["folder"] == LS8.DAY and c["buysig"] is not None and c["ev"].signal == "Y"]
    pairs = [x for x in pairs if x is not None]
    vintage = dict(n=len(pairs), vmin=min(pairs) if pairs else None, vmax=max(pairs) if pairs else None)
    for c in cands:
        bias = LS8.VOLUME_RULE_BIAS.get(c["folder"])
        c["vintage_fragile"] = (F.vintage_fragile(bias, c["ev"].signal, c["vol_ratio"], c["vol_threshold"],
                                                  vintage["vmax"]) if c["signal_basis"] == "replay" else "")
    return cands, offlist, vintage


def signal_fidelity_rows(cands: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for c in cands:
        if c["tier"] != R.TIER_MAIN:
            continue
        ev, bs, rc = c["ev"], c["buysig"], c["receipt"]
        margin = ((c["vol_ratio"] / c["vol_threshold"] - 1) * 100
                  if c["vol_ratio"] is not None and c["vol_threshold"] else None)
        rows.append(OrderedDict(
            date=c["d"].isoformat(), strategy=c["folder"], mode=R.corp_action_mode_for(c["folder"], c["d"]) or "",
            code=c["code"], list_pos=str(c["list_pos"]), slot_state=c["slot_state"],
            slot_state_v2=c["slot_state_v2"], eval_v1=_fmt(c["eval_v1"]), signal_replay=ev.signal,
            replay_reason=ev.reason[:60], signal_log=c["signal_log"], signal_log_v1=c["signal_log_v1"],
            signal_log_v2=c["signal_log_v2"], n_evals=str(bs.n) if bs else "", first_ts=bs.first if bs else "",
            last_ts=bs.last if bs else "", outcome=F.signal_outcome(ev.signal, c["signal_log"]),
            outcome_v1=F.signal_outcome(ev.signal, c["signal_log_v1"]),
            outcome_v2=F.signal_outcome(ev.signal, c["signal_log_v2"]),
            no_slot_but_log_y=_yn(c["slot_state"] == C.STATE_NO_SLOT and bs is not None),
            no_slot_but_log_y_v2=_yn(c["slot_state_v2"] == C.STATE_NO_SLOT and bs is not None),
            reasons_equal=c["reasons_equal"], ref_equal=c["ref_equal"],
            receipt_ref=_fmt(rc.detail.get("ref")) if rc else "", replay_ref=_fmt(ev.ref),
            signal_basis=c["signal_basis"], vol_ratio=_fmt(c["vol_ratio"]), vol_threshold=_fmt(c["vol_threshold"]),
            rule_margin_pct=_pct(margin), vintage_fragile=c["vintage_fragile"]))
    return rows


def fill_attribution_check(ctx: Ctx8, days: Sequence[date]) -> List[str]:
    """로그 `가상매수:` 줄의 전략 귀속(logscan8.attribute) ↔ 체결 원장 BUY — 귀속 규칙의 실데이터 검증."""
    out: List[str] = []
    for d in days:
        dl = ctx.log_for(d)
        if not dl.found:
            out.append(f"{d}: 로그 파일 없음")
            continue
        for folder in R.ALL_FOLDERS:
            log_codes = set(dl.get(folder).fills)
            vtr_codes = {t.code for t in ctx.buys_on(folder, d)}
            if log_codes != vtr_codes:
                out.append(f"{d} {folder}: 로그 가상매수 귀속 {sorted(log_codes)} ≠ 체결 원장 {sorted(vtr_codes)}")
    return out


def _print_signal_tables(sig_rows: Sequence[Dict[str, str]], vintage: Dict[str, Any]) -> None:
    """B 계산 «전에» 보는 표 — 방향별 일치 · 규칙 민감도(v1·v2·v3) · 재구성 모순 · 재현 비중."""
    def r_(x: Optional[float]) -> str:
        return "-" if x is None else f"{x * 100:.2f}%"
    print("\n== 신호 충실도 — 채택 규칙 v3 (E6 main ∩ `[on_tick] 매수신호`) · B 계산 전에 본다")
    print("group | 판정가능 | Y방향 둘다Y/로그Y | N방향 둘다N/로그N | 그중 bought | verdict | note")
    for g in F.signal_table(sig_rows):
        print(f"{g['group']} | {g['evaluable']} | {g['agree_Y']}/{g['y_n']} ({r_(g['y_rate'])}) | "
              f"{g['agree_N']}/{g['n_n']} ({r_(g['n_rate'])}) | {g['bought']} | {g['verdict']} | {g['verdict_note']}")
    print("\n== «평가 가능» 규칙 민감도 — v1 09:02 한 시점 · v2 classify_candidate · v3 v2+빈자리 구간 on_tick(채택)")
    t = {k: {g["group"]: g for g in F.signal_table(sig_rows, outcome_key=k)}
         for k in ("outcome_v1", "outcome_v2", "outcome")}
    for grp in t["outcome"]:
        cells = " | ".join(f"{k[-2:] if k != 'outcome' else 'v3'} {t[k][grp]['evaluable']}건 "
                           f"Y {r_(t[k][grp]['y_rate'])} N {r_(t[k][grp]['n_rate'])} {t[k][grp]['verdict']}"
                           for k in ("outcome_v1", "outcome_v2", "outcome"))
        print(f"{grp} | {cells}")
    n_v2 = sum(1 for r in sig_rows if r["no_slot_but_log_y_v2"] == "Y")
    n_v3 = sum(1 for r in sig_rows if r["no_slot_but_log_y"] == "Y")
    print(f"\n재구성 모순(no_slot 인데 로그 매수신호 있음): v2 {n_v2}건 → v3 {n_v3}건")
    rep = sum(1 for r in sig_rows if r["signal_basis"] == "replay")
    frag = sum(1 for r in sig_rows if r["vintage_fragile"] == "Y")
    print(f"main 후보 행 중 재현 신호 {rep}/{len(sig_rows)} · 빈티지 취약 {frag} · 관측 빈티지(day D-1 거래량) "
          f"n={vintage['n']} 범위 {r_(vintage['vmin'])}~{r_(vintage['vmax'])}")


# ── ③ 청산 · 익절손절 ──────────────────────────────────────────────────────
EARLY_FILL = time(9, 5, 0)     # 실제 매수 ≤ 09:05 면 진입일 고저를 쓴다(D_open 취급)
EXIT_COLS = ["buy_id", "strategy", "code", "buy_date", "buy_time", "buy_price", "entry_basis", "actual_reason",
             "actual_exit_date", "actual_ret_pct", "sim_reason", "sim_exit_date", "sim_ret_pct", "sim_hold_days",
             "sim_flags", "outcome", "same_day_actual", "tp_db", "sl_db", "tp_live", "sl_live", "tp_sl_match"]


def exit_fidelity_rows(ctx: Ctx8, since: date, until: date) -> List[Dict[str, str]]:
    """실제 매수(since~until)를 «실제 진입가·시각»으로 청산 시뮬에 통과 → 실제 청산과 사유·날짜 대조."""
    rows: List[Dict[str, str]] = []
    for folder in R.ALL_FOLDERS:
        rules, probe = ctx.rules[folder], ctx.probes[folder]
        for t in ctx.trades.get(folder, []):
            d = t.buy_ts.date()
            if not (since <= d <= until):
                continue
            extra = ctx.extras.get(t.buy_id)
            basis = X.BASIS_D_OPEN if t.buy_ts.time() <= EARLY_FILL else X.BASIS_ACTUAL
            pos = X.Pos(t.code, d, SRC8.aware(t.buy_ts), float(t.buy_price), extra.qty if extra else 1, basis)
            sim = X.simulate_lot(pos, rules, ctx.path(t.code, d), probe)
            ar = F.actual_reason(t.sell_reason) if t.sell_ts is not None else "open"
            ad = t.sell_ts.date() if t.sell_ts is not None else None
            tp_db = extra.tp_rate if extra else None
            sl_db = extra.sl_rate if extra else None
            match = (_yn(F.rates_equal(tp_db, rules.tp) and F.rates_equal(sl_db, rules.sl))
                     if tp_db is not None and sl_db is not None else "")
            rows.append(OrderedDict(
                buy_id=str(t.buy_id), strategy=folder, code=t.code, buy_date=d.isoformat(),
                buy_time=f"{t.buy_ts:%H:%M:%S}", buy_price=_fmt(t.buy_price), entry_basis=basis,
                actual_reason=ar, actual_exit_date=ad.isoformat() if ad else "",
                actual_ret_pct=_pct((t.sell_price / t.buy_price - 1) * 100) if t.sell_ts is not None else "",
                sim_reason=sim.reason, sim_exit_date=sim.exit_date.isoformat() if sim.exit_date else "",
                sim_ret_pct=_pct(sim.ret_pct), sim_hold_days=_fmt(sim.hold_days), sim_flags=" · ".join(sim.flags),
                outcome=F.exit_outcome(ar, ad, sim.reason, sim.exit_date if sim.closed else None),
                same_day_actual=_yn(ad == d) if ad else "", tp_db=_fmt(tp_db), sl_db=_fmt(sl_db),
                tp_live=_fmt(rules.tp), sl_live=_fmt(rules.sl), tp_sl_match=match))
    return rows


def _print_exit_tables(exit_rows: Sequence[Dict[str, str]]) -> None:
    print("\n== 청산 충실도 (실제 매수 → 실제 진입가로 시뮬 · 분모 = 실제 청산된 건)")
    print("strategy | n | closed | Y | reason_only | N | actual_only_closed | same_day | reason_rate | verdict")
    for g in F.exit_table(exit_rows):
        rate = "-" if g["reason_rate"] is None else f"{g['reason_rate'] * 100:.2f}%"
        print(f"{g['strategy']} | {g['n']} | {g['closed']} | {g['Y']} | {g['reason_only']} | {g['N']} | "
              f"{g['actual_only_closed']} | {g['same_day']} | {rate} | {g['verdict']}")
    print("\n== 익절·손절 비율 (엔진 경로 vs 체결 원장 BUY)")
    for g in F.tp_sl_table(exit_rows):
        print(f"{g['strategy']} | {g['match']}/{g['n']}")


# ── ④⑤ 원장 · 세 arm ─────────────────────────────────────────────────────
LEDGER_COLS = [
    "date", "strategy", "code", "tier", "list_pos", "snap_rank", "list_src", "scan_date", "sector_mode",
    "K", "held_live", "no_slot_live", "slot_state", "slot_state_v2", "eval_v1", "slot_note", "other_holder_live",
    "signal_replay", "replay_reason", "n_bars", "last_bar", "signal_log", "n_evals", "first_ts", "last_ts",
    "reasons_equal", "signal_used", "signal_basis", "vol_ratio", "vol_threshold", "rule_margin_pct",
    "vintage_fragile", "ref", "band_min", "band_max", "band_basis",
    "a_stop_stage", "a_stop_result", "a_stop_basis", "a_stop_detail", "a_per_stock", "a_per_stock_src",
    "a_qty_upper", "a_buy_time", "a_buy_price",
    "b_entry_status", "b_entry_basis", "b_entry_price", "b_entry_vs_ref_pct", "b_entry_note",
    "b_qty", "b_qty_basis", "b_notional_won", "crash_blocked", "crash_lifted_at", "lift_status", "lift_time",
    "lift_price", "lift_unknown", "ub_status", "ub_price", "limitup_possible", "d5_flags", "b1_lot_id", "b2_acct_id",
    "caveats",
]
FILL_COLS = ["date", "strategy", "code", "tier", "price", "basis", "qty", "qty_basis", "signal_basis",
             "crash_blocked", "other_holder_live", "entry_time", "lift_time", "touch_open", "touch_high", "touch_low",
             "touch_close", "d5"]
LOT_COLS = ["arm", "lot_id", "tier", "strategy", "code", "entry_date", "entry_basis", "entry_price", "qty",
            "qty_basis", "notional_won", "signal_basis", "crash_blocked", "lift_time", "d5_flags", "other_holder_live",
            "buy_id", "is_repeat_while_open", "open_lot_seq", "days_since_open_lot", "exit_status", "exit_reason",
            "exit_phase", "exit_date", "exit_price", "ret_pct", "hold_days", "pnl_won", "flags"]
ACCT_COLS = ["acct_id", "strategy", "code", "first_date", "n_fills", "n_adds", "fill_dates", "fill_tiers",
             "avg_price_path", "final_avg_price", "qty", "notional_won", "exit_status", "exit_reason", "exit_date",
             "exit_price", "ret_pct", "hold_days", "pnl_won", "hold_clock_reset_diff", "avg_flip", "flags"]
ACTUAL_COLS = ["buy_id", "strategy", "code", "buy_date", "buy_time", "buy_price", "qty", "notional_won", "in_list",
               "exit_status", "exit_reason", "exit_date", "exit_price", "ret_pct", "pnl_won"]
ASIM_ENTRY_COLS = ["buy_id", "strategy", "code", "date", "in_list", "band_basis", "sim_entry_status",
                   "sim_entry_basis", "sim_entry_price", "actual_buy_time", "actual_buy_price", "entry_diff_pct",
                   "first_tick"]
OUT_FILES = (("ledger8.csv", "ledger", LEDGER_COLS), ("funnel.csv", "funnel", ST.FUNNEL_COLS),
             ("fills_b.csv", "fills", FILL_COLS), ("lots_b1.csv", "lots", LOT_COLS),
             ("accounts_b2.csv", "accounts", ACCT_COLS), ("accounts_b2_ub.csv", "accounts_ub", ACCT_COLS),
             ("a_sim.csv", "a_sim", LOT_COLS),
             ("a_sim_entry.csv", "a_sim_entry", ASIM_ENTRY_COLS), ("a_actual.csv", "a_actual", ACTUAL_COLS))

FillKey = Tuple[date, str, str, str]      # (날짜, 전략, 종목, tier)


def lot_key(f: A.Fill) -> Tuple:
    """중복 체결 가드 키(과제 8 M1) — 로트: (날짜, 전략, 종목, tier, 원 체결 id · A_sim 같은 날 재매수 구분)."""
    return f.d, f.folder, f.code, f.tier, f.buy_id


def acct_key(f: A.Fill) -> Tuple:
    """B2 계좌 가드 키 — (날짜, 전략, 종목): tier 가 달라도 같은 날 두 체결은 겹치는 계좌가 된다(과제 8 M1)."""
    return f.d, f.folder, f.code


# D5 — 속도 조절 규칙은 B 에 적용하지 않는다(사장님 규칙 «후보 통과 종목은 전부 산다»). 라이브였다면 막혔을 건만 표시.
COOLDOWN_MIN = next(f.default for f in dataclasses.fields(TradingStock) if f.name == "buy_cooldown_minutes")
D5_THROTTLE = "throttle"          # [진입억제] 60초 쿨다운·사이클 3건(로그 · core/trading_context.py:484-515) — 라이브가 못 샀다
D5_THROTTLE_DELAY = "throttle_delay"   # 같은 줄이 있으나 라이브가 결국 샀다(A 단계 fill) — 막힘이 아니라 지연(A1)
D5_COOLDOWN_UNKNOWN = "buy_cooldown(관측 불가)"   # 25분 매수 쿨다운 — 어느 객체였는지 몰라 막혔는지 모른다(cooldown_flag)
D5_DAILY_LOSS = "daily_loss"      # 일일손실한도(로그 · core/trading_context.py:428-436)
# VI 매수 보류(trading_context.py:424-426)는 DEBUG 로그라 관측 불가 — 표시하지 않고 한계로 적는다.
# 25분 쿨다운의 «막힘 확정» 표시는 없다 — cooldown_flag 가 검증한 라이브 의미로는 확정할 수 있는 경우가 없다.


def per_stock_for(sd: L8.StratDay, strategy, folder: str, d: date) -> Tuple[float, str]:
    """arm A 종목당 금액 — 로그 복리 재산정(검증표 #12) → config paper_investment_per_stock(#13) → 자본/K."""
    if sd.per_stock:
        return float(sd.per_stock["new"]), "log(종목당 투자금액 재산정)"
    rm = (getattr(strategy, "config", None) or {}).get("risk_management", {})
    if rm.get("paper_investment_per_stock"):
        return float(rm["paper_investment_per_stock"]), "config(paper_investment_per_stock · 복리 미반영)"
    k, _ = R.k_for(folder, d)
    return R.VIRTUAL_CAPITAL_PER_STRATEGY / k, "fallback(자본/K · 복리 미반영)"


def crash_state(ctx: Ctx8, folder: str, code: str, d: date) -> Tuple[bool, str]:
    """D3 — 급락게이트 «유지». B 진입 시각(09:02) 그 지수의 로그 판정이 `차단` 이면 막힘 + 풀린 첫 시각(D3′ 에 쓴다)."""
    cfg, _ = R.regime_index_for(folder, d)
    idx = resolve_regime_index(cfg, code, strategy_name=None, count=False)
    if idx == "none":
        return False, ""
    names = ("KOSPI", "KOSDAQ") if idx == "both" else (idx,)
    dl = ctx.log_for(d)
    t = SRC8.FIRST_TICK.strftime("%H:%M:%S")
    blocked = [n for n in names if dl.index_state(n, t) == "차단"]
    if not blocked:
        return False, ""
    lifts = [dl.first_verdict_after(n, t, "허용") for n in blocked]
    return True, (max(lifts) if all(lifts) else "")


def cooldown_flag(day_buys: Sequence[Tuple[str, C.Trade]], folder: str, code: str, entry: datetime, own_slot: bool,
                  ambiguous: Sequence[str]) -> str:
    """D5 25분 매수 쿨다운 — 라이브였다면 이 B 진입(entry)을 막았나. 확정 «안 막힘»이면 "", 모르면 `관측 불가`.

    라이브 의미(코드 실측 2026-09-19): 쿨다운은 `TradingStock` 객체의 `last_buy_time`(core/models.py:195-196 ·
    :284-296)이고, 객체는 (종목, 소유 전략) 슬롯마다 따로다 — E6 후보는 전략별로 등록되고(bot/candidate_loader.py:231-245 ·
    core/trading/order_execution.py:86-120 · core/trading/stock_state_manager.py:95-106), 매수 경로는 «호출 전략 자기 슬롯»을
    쓴다(core/trading_context.py:88-109 · :376) → 전 전략 보유 확인(bot/trading_analyzer.py:127-130) → 그 객체 쿨다운(:132-136)
    → 체결 뒤 그 객체에 `set_buy_time`(:305). 재선정은 `last_buy_time` 을 지우지 않는다(order_execution.py:92-104) · 복원·전날
    포지션엔 설정 경로가 없다(봇은 매일 재기동).
    ⇒ 이 후보 자신의 라이브 매수(같은 날·전략·종목)는 B 진입 그 자체라 뺀다(09-10 053260 형 가짜 표시). 다른 전략의 매수는
    그 전략 슬롯 객체에 시계를 건다 — 이 전략 객체에 닿는 길은 코드 단독 폴백(trading_context.py:109)뿐이고, 이 전략이 자기
    슬롯을 가진 채(main) 폴백이 돌면 슬롯이 둘 이상이라 `[모호조회]` WARNING 이 남는다(stock_state_manager.py:347-351).
    판정: 다른 전략이 진입 25분 안에 사고 진입 시각 전에 판 매수만 본다(아직 보유면 보유 게이트가 먼저 — D2
    `other_holder_live` 몫). main 이고 진입 전 `[모호조회]` 가 없으면 이 전략 객체는 안 건드렸다 → 안 막힘(표시 없음).
    `[모호조회]` 가 있거나 자기 슬롯이 없는 ext(가정 매수 = 코드 단독 폴백)면 어느 객체였는지 모른다 → `관측 불가`."""
    hms = entry.strftime("%H:%M:%S")
    for f, t in day_buys:
        if f == folder or t.code != code:
            continue
        if not timedelta(0) <= entry - t.buy_ts < timedelta(minutes=COOLDOWN_MIN):
            continue
        if t.sell_ts is None or t.sell_ts > entry:
            continue
        if own_slot and not any(a <= hms for a in ambiguous):
            continue
        return D5_COOLDOWN_UNKNOWN
    return ""


def d5_flags(ctx: Ctx8, sd: L8.StratDay, folder: str, code: str, entry_naive: datetime, own_slot: bool,
             a_stage: str = "") -> List[str]:
    """D5 — 라이브였다면 이 B 진입을 막았을 속도 조절 규칙. 관측 가능한 것만(로그 줄 · 체결 원장).
    진입억제는 A 멈춘 단계가 fill(라이브가 결국 샀다)이면 «지연»으로 따로 적는다(A1) — A 단계가 없는 ext 는 관측 그대로."""
    g = sd.gates_for(code)
    out: List[str] = []
    if L8.G_THROTTLE in g:
        out.append(D5_THROTTLE_DELAY if a_stage == ST.STAGE_FILL else D5_THROTTLE)
    if L8.G_DAILY_LOSS in g:
        out.append(D5_DAILY_LOSS)
    d = entry_naive.date()
    day_buys = [(f, t) for f, ts in sorted(ctx.trades.items()) for t in ts if t.buy_ts.date() == d]
    cd = cooldown_flag(day_buys, folder, code, entry_naive, own_slot, ctx.log_for(d).ambiguous.get(code, []))
    if cd:
        out.append(cd)
    return out


def lift_fills(folder: str, code: str, d: date, minutes: Sequence[Tuple[str, X.Bar]], d_bar: Optional[X.Bar],
               lifted: str, band: Tuple[Optional[float], Optional[float], Optional[float]], common: Dict[str, Any]
               ) -> Tuple[X.LiftEntry, Optional[A.Fill], Optional[X.LiftEntry], Optional[A.Fill]]:
    """D3′ 급락 차단 행 → (해제 뒤 진입, 본 체결, 상한 진입, 상한 체결).

    본 = 게이트가 풀린 뒤 첫 밴드 안 분봉 가격(`exitsim8.lift_entry` · basis after_lift · entry_time = 그 분봉 시각).
    A3 — 분봉이 아예 없으면(`LIFT_NO_MINUTE`) «안 산 것»이 아니라 «모른다»: 본 체결은 만들지 않고, 상한 민감도 체결만
    D 일봉으로 만든다(`exitsim8.lift_upper_bound` · tier `lift_ub` · lift_time = 게이트 해제 시각 · entry_time None →
    진입일 탐침은 09:02 로 본다). 본 집계는 상한 체결을 넣지 않는다(build_arms)."""
    le = X.lift_entry(d, minutes, lifted, band[1], band[2])
    if le.status == X.LIFT_FILLED:
        q = Z.arm_b_qty(le.price)
        return le, A.Fill(folder, code, d, float(le.price), X.BASIS_LIFT, q.qty, q.basis, crash_blocked=True,
                          entry_time=SRC8.aware(datetime.combine(d, time.fromisoformat(le.time))),
                          touch_bar=le.touch_bar, lift_time=le.time, **common), None, None
    if le.status != X.LIFT_NO_MINUTE:
        return le, None, None, None
    ub = X.lift_upper_bound(d_bar, band[1], band[2])
    if ub.status != X.LIFT_FILLED:
        return le, None, ub, None
    q = Z.arm_b_qty(ub.price)
    return le, None, ub, A.Fill(folder, code, d, float(ub.price), ub.basis, q.qty, q.basis, crash_blocked=True,
                                lift_time=lifted, **dict(common, tier=R.TIER_LIFT_UB))


def unique_fills(fills: Sequence[A.Fill], key: Callable[[A.Fill], Tuple], what: str) -> List[A.Fill]:
    """arm 실행 입력의 중복 체결을 막는다(과제 8 M1) — 조용히 겹치는 로트·B2 계좌를 만들지 않고 멈춘다."""
    seen: Dict[Tuple, A.Fill] = {}
    for f in fills:
        k = key(f)
        if k in seen:
            raise ValueError(f"ledger8 {what}: 같은 키 체결 2건 {k} — 겹치는 로트/계좌를 만들지 않는다(과제 8 M1)")
        seen[k] = f
    return list(fills)


def _with_d5(ctx: Ctx8, sd: L8.StratDay, f: A.Fill, own_slot: bool, a_stage: str) -> A.Fill:
    """체결에 D5 표시를 붙인다 — 진입 시각 = 해제 뒤 체결 분봉 · 상한은 게이트 해제 시각(체결은 그 뒤) · 그 밖 09:02."""
    t_naive = (datetime.combine(f.d, time.fromisoformat(f.lift_time)) if f.lift_time else ctx.first_tick(f.d))
    return dataclasses.replace(f, d5=",".join(d5_flags(ctx, sd, f.folder, f.code, t_naive, own_slot, a_stage)))


def attach_rows(ctx: Ctx8, cands: Sequence[Dict[str, Any]], reuse: Optional[Dict[FillKey, A.Fill]] = None
                ) -> Tuple[List[Dict[str, str]], List[A.Fill], List[A.Fill], List[Dict[str, str]], List[A.Fill]]:
    """후보 행 → (원장 행, B 체결, D3 «게이트 없었다면» 09:02 체결(민감도), 접힌 단계 행, A3 상한 체결(민감도)).
    A 단계는 main 만.

    B 진입 = D 09:02 한 번(설계 판단 7). 그 시각 급락 게이트가 막고 있으면 D3′ — 게이트가 풀린 뒤 첫 밴드 안 분봉
    가격(`exitsim8.lift_entry`)에 산다. 분봉이 아예 없으면 «모른다»(A3) — 본 체결 없이 `lift_unknown=Y` 로 두고, main 행은
    D 일봉 상한 체결(tier `lift_ub`)을 따로 모은다(`lift_fills` · ext 는 그 자체가 별도 칸이라 상한을 만들지 않는다).
    속도 조절 규칙(D5)은 적용하지 않고 라이브였다면 막혔을 규칙만 `d5` 에 적는다(`d5_flags` — A1 진입억제 지연·쿨다운 관측 불가).
    """
    ledger: List[Dict[str, str]] = []
    fills: List[A.Fill] = []
    nogate: List[A.Fill] = []
    funnel: List[Dict[str, str]] = []
    upper: List[A.Fill] = []
    for c in cands:
        d, folder, code, tier, ev = c["d"], c["folder"], c["code"], c["tier"], c["ev"]
        strat = ctx.strategies[folder]
        sd = ctx.log_for(d).get(folder)
        others = ctx.others_at(folder, code, ctx.first_tick(d))
        bs = c["buysig"]
        caveats: List[str] = []
        margin = ((c["vol_ratio"] / c["vol_threshold"] - 1) * 100
                  if c["vol_ratio"] is not None and c["vol_threshold"] else None)
        row: Dict[str, str] = OrderedDict((k, "") for k in LEDGER_COLS)
        row.update(date=d.isoformat(), strategy=folder, code=code, tier=tier, list_pos=str(c["list_pos"]),
                   snap_rank=_fmt(c["snap_rank"]), list_src=c["list_src"], scan_date=_fmt(c["scan_date"]),
                   sector_mode=c["sector_mode"], K=str(R.k_for(folder, d)[0]), held_live=_fmt(c["held"]),
                   no_slot_live=_fmt(c["no_slot"]), slot_state=c["slot_state"], slot_state_v2=c["slot_state_v2"],
                   eval_v1=_fmt(c["eval_v1"]), slot_note=c["slot_note"], other_holder_live=",".join(others),
                   signal_replay=ev.signal, replay_reason=ev.reason[:80], n_bars=str(ev.n_bars),
                   last_bar=ev.last_bar, signal_log=c["signal_log"], reasons_equal=c["reasons_equal"],
                   signal_used=c["signal_used"], signal_basis=c["signal_basis"], vol_ratio=_fmt(c["vol_ratio"]),
                   vol_threshold=_fmt(c["vol_threshold"]), rule_margin_pct=_pct(margin),
                   vintage_fragile=c["vintage_fragile"])
        if bs is not None:
            row.update(n_evals=str(bs.n), first_ts=bs.first, last_ts=bs.last)
        band: Optional[Tuple[Optional[float], Optional[float], Optional[float]]] = None
        if c["signal_used"] == "Y":
            if ev.signal == "Y":
                band, row["band_basis"] = (ev.ref, ev.band_min, ev.band_max), "replay"
            else:
                data, _ = ctx.windows.get(code, d)
                band, row["band_basis"] = LS8.forced_band(strat, folder, code, d, data), "forced(로그 Y·재현 N)"
                if band is None:
                    caveats.append("밴드 산출 불가 — 강제 _check_buy 도 None(rs_leader live 배제·데이터 없음)")
        if band is not None:
            row.update(ref=_fmt(band[0]), band_min=_fmt(band[1], 2), band_max=_fmt(band[2], 2))
        a_stage = ""
        if tier == R.TIER_MAIN:
            buys = [t for t in ctx.buys_on(folder, d) if t.code == code]
            per_stock, ps_src = per_stock_for(sd, strat, folder, d)
            ref_px = band[0] if band is not None else ev.ref
            qa = Z.arm_a_qty(ref_px, per_stock, getattr(strat, "_max_per_stock_amount", None), ps_src)
            facts = ST.AFacts(d, folder, code, c["held"], c["no_slot"], c["slot_note"], sd.cap_blocking(code), bs,
                              sd.gates_for(code), buys[0] if buys else None, c["signal_log"], ev.signal,
                              qa.qty if ref_px else None)
            stop = ST.classify_a(facts)
            a_stage = stop.stage
            funnel.extend(ST.funnel_rows(facts))
            row.update(a_stop_stage=stop.stage, a_stop_result=stop.result, a_stop_basis=stop.basis,
                       a_stop_detail=stop.detail[:200], a_per_stock=_won_str(per_stock), a_per_stock_src=ps_src,
                       a_qty_upper=str(qa.qty) if ref_px else "")
            if buys:
                row.update(a_buy_time=f"{buys[0].buy_ts:%H:%M:%S}", a_buy_price=_fmt(buys[0].buy_price))
        fill: Optional[A.Fill] = None
        ub_fill: Optional[A.Fill] = None
        if reuse is not None:
            fill = reuse.get((d, folder, code, tier))
            if fill is not None:
                row.update(b_entry_status=S.ENTRY_FILLED, b_entry_note="reuse-fills")
            if tier == R.TIER_MAIN:
                ub_fill = reuse.get((d, folder, code, R.TIER_LIFT_UB))
                if ub_fill is not None:
                    row.update(crash_blocked="Y", lift_unknown="Y", ub_status=X.LIFT_FILLED, b_entry_note="reuse-fills")
        elif band is not None:
            ent = S.simulate_entry(ctx.bars_for(code).get(d), band[1], band[2])
            row.update(b_entry_status=ent.status, b_entry_basis=ent.basis, b_entry_note=ent.note)
            if ent.price is not None and band[0]:
                row["b_entry_vs_ref_pct"] = _pct((ent.price / band[0] - 1) * 100)
            common = dict(tier=tier, signal_basis=c["signal_basis"], other_holder_live=",".join(others))
            crash, lifted = crash_state(ctx, folder, code, d)
            if not crash:
                if ent.status == S.ENTRY_FILLED:
                    q = Z.arm_b_qty(ent.price)
                    fill = A.Fill(folder, code, d, float(ent.price), ent.basis, q.qty, q.basis, **common)
            else:
                row.update(crash_blocked="Y", crash_lifted_at=lifted)
                if ent.status == S.ENTRY_FILLED:           # D3 반대편 — 게이트가 없었다면 09:02 에 샀다(민감도)
                    q0 = Z.arm_b_qty(ent.price)
                    nogate.append(A.Fill(folder, code, d, float(ent.price), ent.basis, q0.qty, q0.basis,
                                         crash_blocked=True, **common))
                le, fill, ub, ub_fill = lift_fills(folder, code, d, ctx.minute_bars(code, d),
                                                   ctx.bars_for(code).get(d), lifted, band, common)
                row.update(lift_status=le.status, lift_time=le.time, lift_price=_fmt(le.price),
                           b_entry_status=f"crash→{le.status}")
                if ub is not None:                      # A3 — 분봉 없음 = 모른다(본 집계 밖)
                    row["lift_unknown"] = "Y"
                    if tier == R.TIER_MAIN:
                        row.update(ub_status=ub.status, ub_price=_fmt(ub.price))
                    else:
                        ub_fill = None
        if fill is not None:
            if reuse is None:
                fill = _with_d5(ctx, sd, fill, tier == R.TIER_MAIN, a_stage)
            fills.append(fill)
            row.update(b_entry_basis=fill.basis, b_entry_price=_fmt(fill.price), b_qty=str(fill.qty),
                       b_qty_basis=fill.qty_basis, b_notional_won=_won_str(fill.price * fill.qty),
                       crash_blocked=_fmt(fill.crash_blocked), d5_flags=fill.d5)
            if band is not None and band[0] and fill.price >= band[0] * (1 + PRICE_LIMIT_GUARD_RATE):
                row["limitup_possible"] = "Y"          # 상한가 +25% 게이트(trading_context.py:466-482) — 플래그만
        if ub_fill is not None:                        # 원장 d5_flags·b_* 칸은 본 체결만 — 상한은 fills_b·lots(B1_ub)에
            if reuse is None:
                ub_fill = _with_d5(ctx, sd, ub_fill, True, a_stage)
            upper.append(ub_fill)
            row["ub_price"] = _fmt(ub_fill.price)
        row["caveats"] = " | ".join(caveats)
        ledger.append(row)
    return ledger, fills, nogate, funnel, upper


def a_sim_fills(ctx: Ctx8, days: Sequence[date], in_list: Dict[Tuple[date, str], List[str]]
                ) -> Tuple[List[A.Fill], List[Dict[str, str]], List[str]]:
    """실제 매수 → B 와 같은 진입 시뮬(D 시가 · 밴드 복귀). 밴드 = 재현 Y 면 그 밴드, 아니면 강제 밴드. 수량 = 실제.
    체결 원장에 수량이 없으면 수량 0 으로 두되 «경고»로 남긴다(조용히 넣지 않는다)."""
    fills: List[A.Fill] = []
    rows: List[Dict[str, str]] = []
    warns: List[str] = []
    dayset = set(days)
    for folder in R.ALL_FOLDERS:
        strat = ctx.strategies[folder]
        for t in ctx.trades.get(folder, []):
            d = t.buy_ts.date()
            if d not in dayset:
                continue
            data, _ = ctx.windows.get(t.code, d)
            ev = LS8.evaluate8(strat, folder, t.code, d, data)
            if ev.signal == "Y":
                band, basis = (ev.ref, ev.band_min, ev.band_max), "replay"
            else:
                band, basis = LS8.forced_band(strat, folder, t.code, d, data), "forced"
            if band is None:
                band, basis = (None, None, None), "none(밴드 없음 → D 시가)"
            ent = S.simulate_entry(ctx.bars_for(t.code).get(d), band[1], band[2])
            listed = t.code in in_list.get((d, folder), [])
            extra = ctx.extras.get(t.buy_id)
            if extra is None:
                warns.append(f"A_sim {folder} {t.code} {d} buy_id={t.buy_id}: 체결 원장 수량 없음 → 수량 0(손익 0)")
            rows.append(OrderedDict(
                buy_id=str(t.buy_id), strategy=folder, code=t.code, date=d.isoformat(), in_list=_yn(listed),
                band_basis=basis, sim_entry_status=ent.status, sim_entry_basis=ent.basis,
                sim_entry_price=_fmt(ent.price), actual_buy_time=f"{t.buy_ts:%H:%M:%S}",
                actual_buy_price=_fmt(t.buy_price),
                entry_diff_pct=_pct((ent.price / t.buy_price - 1) * 100) if ent.price else "",
                first_tick=_yn(t.buy_ts.time() <= EARLY_FILL)))
            if ent.status == S.ENTRY_FILLED:
                fills.append(A.Fill(folder, t.code, d, float(ent.price), ent.basis, extra.qty if extra else 0,
                                    "actual", tier=R.TIER_MAIN if listed else R.TIER_OFFLIST, signal_basis=basis,
                                    buy_id=t.buy_id))
    return fills, rows, warns


def lot_rows(lots: Sequence[A.Lot], arm: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for lot in lots:
        f, e = lot.fill, lot.exit
        out.append(OrderedDict(
            arm=arm, lot_id=lot.lot_id, tier=f.tier, strategy=f.folder, code=f.code, entry_date=f.d.isoformat(),
            entry_basis=f.basis, entry_price=_fmt(f.price), qty=str(f.qty), qty_basis=f.qty_basis,
            notional_won=str(lot.notional_won), signal_basis=f.signal_basis, crash_blocked=_fmt(f.crash_blocked),
            lift_time=f.lift_time, d5_flags=f.d5, other_holder_live=f.other_holder_live, buy_id=_fmt(f.buy_id),
            is_repeat_while_open=_fmt(lot.is_repeat_while_open), open_lot_seq=str(lot.open_lot_seq),
            days_since_open_lot=_fmt(lot.days_since_open_lot), exit_status=e.status, exit_reason=e.reason,
            exit_phase=e.phase, exit_date=e.exit_date.isoformat() if e.exit_date else "",
            exit_price=_fmt(e.price, 2), ret_pct=_pct(e.ret_pct), hold_days=_fmt(e.hold_days),
            pnl_won=_fmt(lot.pnl_won), flags=" · ".join(e.flags)))
    return out


def acct_rows(accts: Sequence[A.Account]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for a in accts:
        e = a.exit
        out.append(OrderedDict(
            acct_id=a.acct_id, strategy=a.folder, code=a.code, first_date=a.first_date.isoformat(),
            n_fills=str(len(a.fills)), n_adds=str(a.n_adds), fill_dates=",".join(f.d.isoformat() for f in a.fills),
            fill_tiers=",".join(f.tier for f in a.fills),
            avg_price_path="→".join(_fmt(p, 2) for p in a.avg_path), final_avg_price=_fmt(a.avg_price, 2),
            qty=str(a.qty), notional_won=str(a.notional_won), exit_status=e.status, exit_reason=e.reason,
            exit_date=e.exit_date.isoformat() if e.exit_date else "", exit_price=_fmt(e.price, 2),
            ret_pct=_pct(e.ret_pct), hold_days=_fmt(e.hold_days), pnl_won=_fmt(a.pnl_won),
            hold_clock_reset_diff=a.hold_clock_reset_diff, avg_flip=a.avg_flip, flags=" · ".join(a.flags + e.flags)))
    return out


def actual_rows(rows: Sequence[A.ActualRow], in_list: Dict[Tuple[date, str], List[str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for r in rows:
        t, d = r.trade, r.trade.buy_ts.date()
        out.append(OrderedDict(
            buy_id=str(t.buy_id), strategy=r.folder, code=t.code, buy_date=d.isoformat(),
            buy_time=f"{t.buy_ts:%H:%M:%S}", buy_price=_fmt(t.buy_price), qty=str(r.qty),
            notional_won=str(r.notional_won), in_list=_yn(t.code in in_list.get((d, r.folder), [])),
            exit_status=r.exit_status, exit_reason=r.exit_reason,
            exit_date=r.exit_date.isoformat() if r.exit_date else "", exit_price=_fmt(r.exit_price, 2),
            ret_pct=_pct(r.ret_pct), pnl_won=_fmt(r.pnl_won)))
    return out


def fill_rows(fills: Sequence[A.Fill]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for f in fills:
        tb = f.touch_bar
        out.append(OrderedDict(
            date=f.d.isoformat(), strategy=f.folder, code=f.code, tier=f.tier, price=repr(f.price), basis=f.basis,
            qty=str(f.qty), qty_basis=f.qty_basis, signal_basis=f.signal_basis, crash_blocked=_fmt(f.crash_blocked),
            other_holder_live=f.other_holder_live, entry_time=f.entry_time.isoformat() if f.entry_time else "",
            lift_time=f.lift_time, touch_open=repr(tb.open) if tb else "", touch_high=repr(tb.high) if tb else "",
            touch_low=repr(tb.low) if tb else "", touch_close=repr(tb.close) if tb else "", d5=f.d5))
    return out


def read_fills(path: Path) -> Dict[FillKey, A.Fill]:
    """`fills_b.csv`(진입 집합 동결본) → 키별 Fill. 스펙 §4 「진입 집합 동결 후 청산만 재추적」."""
    out: Dict[FillKey, A.Fill] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            d = date.fromisoformat(r["date"])
            tb = (X.Bar(d, float(r["touch_open"]), float(r["touch_high"]), float(r["touch_low"]),
                        float(r["touch_close"])) if r["touch_open"] else None)
            key = (d, r["strategy"], r["code"], r["tier"])
            if key in out:
                raise ValueError(f"ledger8 {path.name}: 같은 키 체결 2건 {key} — 동결본이 깨졌다(과제 8 M1)")
            out[key] = A.Fill(
                r["strategy"], r["code"], d, float(r["price"]), r["basis"], int(r["qty"]), r["qty_basis"],
                tier=r["tier"], signal_basis=r["signal_basis"], crash_blocked=(r["crash_blocked"] == "Y"),
                other_holder_live=r["other_holder_live"],
                entry_time=datetime.fromisoformat(r["entry_time"]) if r["entry_time"] else None,
                touch_bar=tb, lift_time=r["lift_time"], d5=r["d5"])
    return out


def build_arms(ctx: Ctx8, days: Sequence[date], cands: Sequence[Dict[str, Any]],
               reuse: Optional[Dict[FillKey, A.Fill]] = None) -> Dict[str, Any]:
    """세 arm 실행. 🔑 본 집계(B1 · B2)는 main 체결만으로 돈다(과제 8 M3) — 민감도는 전부 따로 돈 별도 결과다:
    B1_nogate(D3 반대편 · 09:02) · B1_ext(D1 11~20위) · B1_ub/accounts_ub(A3 상한 = main + lift_ub 를 «함께» 돌린 판 —
    같은 (전략, 종목)의 본 체결과 한 시간선에 놓여야 B2 평단·B1 재신호가 맞다). 실행 입력마다 중복 체결은 멈춘다(M1)."""
    ledger, fills, nogate, funnel, upper = attach_rows(ctx, cands, reuse)
    in_list: Dict[Tuple[date, str], List[str]] = {}
    for c in cands:
        if c["tier"] == R.TIER_MAIN:
            in_list.setdefault((c["d"], c["folder"]), []).append(c["code"])
    probe_for = ctx.probes.__getitem__

    def lots(fs: Sequence[A.Fill], prefix: str) -> List[A.Lot]:
        return A.run_lots(unique_fills(fs, lot_key, prefix), ctx.rules, ctx.path, probe_for, ctx.calendar,
                          SRC8.as_of, prefix)

    def accounts(fs: Sequence[A.Fill], what: str) -> Tuple[List[A.Account], List[A.Account]]:
        fs = unique_fills(fs, acct_key, what)
        first = A.run_accounts(fs, ctx.rules, ctx.path, probe_for, SRC8.as_of, A.CLOCK_FIRST)
        return first, A.run_accounts(fs, ctx.rules, ctx.path, probe_for, SRC8.as_of, A.CLOCK_LAST_ADD)

    main_f = [f for f in fills if f.tier == R.TIER_MAIN]               # D3′: 해제 뒤 체결 포함 · 상한(lift_ub) 없음
    b1 = lots(main_f, "B1")
    b1g = lots([f for f in nogate if f.tier == R.TIER_MAIN], "B1G")     # D3 반대편 — 게이트 없었다면(09:02)
    b1x = lots([f for f in fills if f.tier == R.TIER_EXT], "B1X")       # D1: 11~20위 별도 칸
    b2, b2r = accounts(main_f, "B2")
    A.mark_clock_diff(b2, b2r)
    A.mark_avg_flip(b2, b1)
    b1u = lots(main_f + upper, "B1U")                                  # A3 상한 민감도(본 + 상한)
    b2u, b2ur = accounts(main_f + upper, "B2_ub")
    for a in b2u + b2ur:                                               # 본 B2 와 id 가 겹치지 않게
        a.acct_id = a.acct_id.replace("B2", "B2U", 1)
    A.mark_clock_diff(b2u, b2ur)
    A.mark_avg_flip(b2u, b1u)
    af, asim_entry, warns = a_sim_fills(ctx, days, in_list)
    asim = lots(af, "AS")
    aact = A.a_actual(ctx.trades, lambda i: ctx.extras[i].qty if i in ctx.extras else 0, days, ctx.last_close,
                      F.actual_reason)
    lot_id = {(lot.fill.d, lot.fill.folder, lot.fill.code, lot.fill.tier): lot.lot_id for lot in b1 + b1x}
    acct_id = {(f.d, f.folder, f.code): a.acct_id for a in b2 for f in a.fills}
    for r in ledger:
        d = date.fromisoformat(r["date"])
        r["b1_lot_id"] = lot_id.get((d, r["strategy"], r["code"], r["tier"]), "")
        if r["tier"] == R.TIER_MAIN:
            r["b2_acct_id"] = acct_id.get((d, r["strategy"], r["code"]), "")
    # B1 «열린 로트 위 재신호» 와 B2 «추가매수» 는 같은 시간선이라 대부분 같다. 남는 차이는 로트별 청산 vs 평단 청산이
    # 갈린 경우뿐이다(결함 아님) — 전략별로 적어 둔다.
    repeat_vs_adds = {f: dict(b1_repeat=sum(1 for x in b1 if x.fill.folder == f and x.is_repeat_while_open),
                              b2_adds=sum(a.n_adds for a in b2 if a.folder == f)) for f in R.ALL_FOLDERS}
    return dict(ledger=ledger, funnel=funnel, fills=fill_rows(fills + upper),
                lots=(lot_rows(b1, "B1") + lot_rows(b1g, "B1_nogate") + lot_rows(b1x, "B1_ext")
                      + lot_rows(b1u, "B1_ub")),
                accounts=acct_rows(b2), accounts_ub=acct_rows(b2u), a_sim=lot_rows(asim, "A_sim"),
                a_sim_entry=asim_entry, a_actual=actual_rows(aact, in_list), warnings=warns,
                repeat_vs_adds=repeat_vs_adds)


def _print_counts(res: Dict[str, Any]) -> None:
    print("\n== 규모 (전략별)")
    print("strategy | 후보(main) | 사용신호Y | B체결(main) | 그중 해제 뒤 | B1로트 | B2계좌 | B1 재신호/B2 추가 | A실제매수")
    for f in R.ALL_FOLDERS:
        led = [r for r in res["ledger"] if r["strategy"] == f and r["tier"] == R.TIER_MAIN]
        ra = res["repeat_vs_adds"][f]
        print(f"{f} | {len(led)} | {sum(1 for r in led if r['signal_used'] == 'Y')} | "
              f"{sum(1 for r in led if r['b_entry_price'])} | "
              f"{sum(1 for r in led if r['b_entry_basis'] == X.BASIS_LIFT)} | "
              f"{sum(1 for r in res['lots'] if r['strategy'] == f and r['arm'] == 'B1')} | "
              f"{sum(1 for r in res['accounts'] if r['strategy'] == f)} | {ra['b1_repeat']}/{ra['b2_adds']} | "
              f"{sum(1 for r in res['a_actual'] if r['strategy'] == f)}")
    crash = [r for r in res["ledger"] if r["crash_blocked"] == "Y" and r["tier"] == R.TIER_MAIN]
    st: Dict[str, int] = {}
    for r in crash:
        st[r["lift_status"] or "(밴드 없음)"] = st.get(r["lift_status"] or "(밴드 없음)", 0) + 1
    print(f"D3′ 급락 차단 main 행 {len(crash)} → " + " · ".join(f"{k} {v}" for k, v in sorted(st.items())))
    unk = [r for r in crash if r["lift_unknown"] == "Y"]
    ub: Dict[str, int] = {}
    for r in unk:
        ub[r["ub_status"]] = ub.get(r["ub_status"], 0) + 1
    print(f"A3 분봉 없음(모른다 · 본 집계 밖) main 행 {len(unk)} → 상한 " + " · ".join(f"{k} {v}" for k, v in sorted(ub.items()))
          + f" · B1_ub 로트 {sum(1 for r in res['lots'] if r['arm'] == 'B1_ub')}"
          f"(그중 상한 {sum(1 for r in res['lots'] if r['arm'] == 'B1_ub' and r['tier'] == R.TIER_LIFT_UB)})"
          f" · B2_ub 계좌 {len(res['accounts_ub'])}")
    b1 = [r for r in res["lots"] if r["arm"] == "B1"]
    d5 = (D5_THROTTLE, D5_THROTTLE_DELAY, D5_COOLDOWN_UNKNOWN, D5_DAILY_LOSS)
    print("D5 B1 로트 표시 — " + " · ".join(f"{k} {sum(1 for r in b1 if k in r['d5_flags'].split(','))}" for k in d5))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ledger8 — 8전략 세 arm 관측 원장")
    ap.add_argument("--start", default=R.LEDGER_START.isoformat())
    ap.add_argument("--end", default=R.LEDGER_END.isoformat())
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--log-dir", default=None, help="라이브 로그 폴더(읽기 전용)")
    ap.add_argument("--stage", choices=("signal", "exit", "all"), default="all")
    ap.add_argument("--exit-fid-since", default=R.EXIT_FID_SINCE.isoformat())
    ap.add_argument("--reuse-fills", default=None, help="진입 집합 동결 파일(fills_b.csv) — 청산만 재추적")
    a = ap.parse_args(argv)
    out = Path(a.out)
    log_dir = _resolve_log_dir(a.log_dir)
    reuse = read_fills(Path(a.reuse_fills)) if a.reuse_fills else None
    ctx = Ctx8.open(log_dir)
    try:
        ctx.attach_exit_probes()          # 🔴 _check_buy 보다 먼저(envelope 사본)
        days = T.days_in_range(ctx.calendar, date.fromisoformat(a.start), date.fromisoformat(a.end))
        if not days:
            print(f"거래일 없음: {a.start} ~ {a.end}")
            return 2
        print(f"로그 {log_dir} · 창 {days[0]}~{days[-1]} ({len(days)}거래일) · DB {bootstrap.DB_NAME}")
        warnings = fill_attribution_check(ctx, days)
        cands, offlist, vintage = evaluate_candidates(ctx, days)
        sig_rows = signal_fidelity_rows(cands)
        _atomic_write_csv(out / "fidelity_signal.csv", SIG_COLS, sig_rows)
        _atomic_write_csv(out / "offlist_signals.csv", OFF_COLS, offlist)
        _print_signal_tables(sig_rows, vintage)
        exit_rows: List[Dict[str, str]] = []
        if a.stage in ("exit", "all"):
            exit_rows = exit_fidelity_rows(ctx, date.fromisoformat(a.exit_fid_since), days[-1])
            _atomic_write_csv(out / "fidelity_exit.csv", EXIT_COLS, exit_rows)
            _print_exit_tables(exit_rows)
        res: Dict[str, Any] = {}
        if a.stage == "all":
            res = build_arms(ctx, days, cands, reuse)
            for name, key, cols in OUT_FILES:
                _atomic_write_csv(out / name, cols, res[key])
            _print_counts(res)
            warnings.extend(res["warnings"])
        for w in warnings:
            print(f"[경고] {w}")
        meta = _meta(days, log_dir, a.stage, warnings)
        meta["vintage"] = vintage
        meta["last_bar"] = ctx.calendar[-1].isoformat() if ctx.calendar else ""
        meta["reuse_fills"] = a.reuse_fills or ""
        meta["repeat_vs_adds"] = res.get("repeat_vs_adds", {})
        _atomic_write_text(out / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
