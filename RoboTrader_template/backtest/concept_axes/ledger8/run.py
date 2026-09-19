"""ledger8 — 8전략 세 arm(A 라이브 · B1 로트 독립 · B2 평단 합산) 관측 원장 CLI.

    cd <worktree>/RoboTrader_template
    PY=D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe
    $PY -m backtest.concept_axes.ledger8.run --stage signal       # ② 신호 충실도(B 계산 «전에» 본다)

🔴 DB 쓰기 0 · 라이브 코드 0줄 · 관측 원장이다 — 판정 근거로 쓰지 말 것.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap
from backtest.concept_axes.minervini.cap_skip_ledger import classify as C
from backtest.concept_axes.minervini.cap_skip_ledger import tradecal as T

from . import fidelity8 as F
from . import livesignal8 as LS8
from . import registry as R
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ledger8 — 8전략 세 arm 관측 원장")
    ap.add_argument("--start", default=R.LEDGER_START.isoformat())
    ap.add_argument("--end", default=R.LEDGER_END.isoformat())
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--log-dir", default=None, help="라이브 로그 폴더(읽기 전용)")
    ap.add_argument("--stage", choices=("signal",), default="signal")
    a = ap.parse_args(argv)
    out = Path(a.out)
    log_dir = _resolve_log_dir(a.log_dir)
    ctx = Ctx8.open(log_dir)
    try:
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
        for w in warnings:
            print(f"[경고] {w}")
        meta = _meta(days, log_dir, a.stage, warnings)
        meta["vintage"] = vintage
        _atomic_write_text(out / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
