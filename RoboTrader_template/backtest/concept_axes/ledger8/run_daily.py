"""매일 실행 — 날짜 하나로 「로그 복사 → 최근 N거래일 창 원장 → 3전략(focus3) B1 요약 `summary_daily.md`」.

    cd <worktree>/RoboTrader_template
    PYTHONPATH=$PWD:$PWD/.. PYTHONIOENCODING=utf-8 <venv python> -m backtest.concept_axes.ledger8.run_daily 2026-10-08

1. 로그 복사: `<src-logs>/robotrader_template_<YYYYMMDD>_*.log` → `--log-dir`(창 안 거래일 전부 · 같은 크기면 건너뜀).
2. 창 = DB 달력(KOSPI 일봉)에서 그 날짜까지 최근 `--n-days`(기본 5) 거래일(당일 포함) → `run --stage all` →
   `<out-root>/daily_<날짜>/`(원장 CSV·summary.md 전부 — 매번 창 전체를 다시 계산 · 같은 입력이면 같은 바이트).
3. `summary_daily.md` — `lots_b1.csv` 의 arm=B1·tier=main 중 3전략: 전략별 건수 · 손익 합(원 정수 · 미청산은 마지막 종가
   평가) · 명목가중%(손익 합 ÷ 매수금액 합) · 청산(승)/미청산 — 창 전체 표 + 당일 진입분 표 따로.

🔴 쓰기는 `--log-dir`·`--out-root` 뿐(라이브 트리 아래면 거절) · DB 는 SELECT 만(bootstrap 읽기 전용 세션) · KIS 호출 0.
   관측 원장이다 — 판정 근거로 쓰지 말 것. B1 은 자금한도·K·일일 한도가 없는 세계다(README §1).
"""
from __future__ import annotations

import argparse
import csv
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저(읽기 전용)

from . import registry as R
from . import run as RUN
from . import sources8 as SRC8

LIVE_ROOT = Path("D:/GIT/kis-trading-template")
SRC_LOGS = LIVE_ROOT / "RoboTrader_template" / "logs"
LOG_DIR = Path("D:/tmp/kis-wt-ledger-weekly-logs")
OUT_ROOT = Path("D:/tmp/kis-wt-ledger-weekly-out")
FOCUS3: Tuple[str, ...] = ("daytrading_3methods_breakout", "minervini_volume_dryup", "book_pullback_ma20")
RULE_KO = {R.CAP_COUNTS_BUY_SELL: "매수+매도 체결 합", R.CAP_COUNTS_BUY_ONLY: "매수 체결만"}


def _under(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def window(calendar: Sequence[date], d: date, n: int) -> List[date]:
    """d 까지 최근 n 거래일(d 포함). d 가 달력에 없으면(휴장·일봉 미수집) ValueError."""
    if d not in calendar:
        raise ValueError(f"{d} 는 DB 달력(KOSPI 일봉)에 없다 — 휴장일이거나 일봉 미수집")
    upto = [x for x in sorted(calendar) if x <= d]
    return upto[-n:]


def copy_logs(src: Path, dst: Path, days: Sequence[date]) -> List[str]:
    dst.mkdir(parents=True, exist_ok=True)
    notes: List[str] = []
    for d in days:
        found = sorted(src.glob(f"robotrader_template_{d:%Y%m%d}_*.log"))
        if not found:
            notes.append(f"{d} 로그 없음({src})")
            continue
        for f in found:
            t = dst / f.name
            if t.exists() and t.stat().st_size == f.stat().st_size:
                notes.append(f"{f.name} 같은 크기 — 건너뜀")
                continue
            shutil.copy2(f, t)
            notes.append(f"{f.name} 복사({f.stat().st_size:,}B)")
    return notes


def _agg(rows: Sequence[Dict[str, str]]) -> Dict[str, object]:
    known = [r for r in rows if r["pnl_won"] != ""]
    pnl = sum(int(r["pnl_won"]) for r in known)
    notional = sum(int(r["notional_won"]) for r in known)
    closed = [r for r in rows if r["exit_status"] == "closed"]
    return dict(n=len(rows), pnl=pnl, notional=notional, pct=(100.0 * pnl / notional) if notional else None,
                closed=len(closed), wins=sum(1 for r in closed if r["pnl_won"] != "" and int(r["pnl_won"]) > 0),
                open=len(rows) - len(closed), unknown=len(rows) - len(known))


def _table(title: str, groups: Sequence[Tuple[str, Sequence[Dict[str, str]]]]) -> List[str]:
    out = [f"### {title}", "", "| 전략 | 건수 | 손익 합(원) | 매수금액 합(원) | 명목가중 % | 청산(승) / 미청산 | 손익 불명 |",
           "|---|---:|---:|---:|---:|---|---:|"]
    for name, rows in groups:
        a = _agg(rows)
        pct = "—" if a["pct"] is None else f"{a['pct']:+.2f}%"
        out.append(f"| {name} | {a['n']} | {a['pnl']:+,} | {a['notional']:,} | {pct} | "
                   f"{a['closed']}({a['wins']}) / {a['open']} | {a['unknown']} |")
    return out + [""]


def render(d: date, days: Sequence[date], out: Path, lots_path: Path, copy_notes: Sequence[str]) -> str:
    lots = [r for r in csv.DictReader(lots_path.open(encoding="utf-8"))
            if r["arm"] == "B1" and r["tier"] == R.TIER_MAIN and r["strategy"] in FOCUS3]
    by = {s: [r for r in lots if r["strategy"] == s] for s in FOCUS3}
    today = {s: [r for r in rs if r["entry_date"] == d.isoformat()] for s, rs in by.items()}
    rule, why = R.daily_cap_rule_for(d)
    L = [f"# 원장 일일 요약 — {d} (3전략 B1 전수)", "",
         "> 관측 원장이다 — 판정 근거로 쓰지 말 것. B1 = 후보 통과 종목 전부 1로트(`qty = max(1, floor(1,000,000 / 주가))`) · "
         "자금한도·K·일일 한도 없음 · gross · 미청산은 마지막 종가 평가.", "",
         f"- 창: {days[0]} ~ {days[-1]}({len(days)}거래일) · 출력 `{out}` · 원천 `lots_b1.csv`(arm=B1 · tier=main)",
         f"- 그날 라이브 일일 한도 규칙: **{RULE_KO.get(rule, rule)}**({why}) — 라이브 A 쪽 «캡» 판정에만 쓰인다(B1 미적용)", ""]
    L += _table(f"창 전체({days[0]}~{days[-1]}) 진입", [(s, by[s]) for s in FOCUS3] + [("3전략 합", lots)])
    L += _table(f"당일 진입분({d})", [(s, today[s]) for s in FOCUS3]
                + [("3전략 합", [r for rs in today.values() for r in rs])])
    L += ["### 날짜별 진입 건수", "", "| 진입일 | " + " | ".join(FOCUS3) + " |", "|---|" + "---:|" * len(FOCUS3)]
    for x in days:
        L.append(f"| {x} | " + " | ".join(str(sum(1 for r in by[s] if r["entry_date"] == x.isoformat())) for s in FOCUS3)
                 + " |")
    L += ["", "### 로그 복사", ""] + [f"- {n}" for n in copy_notes] + [""]
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ledger8 매일 실행 — 로그 복사 → 최근 N거래일 원장 → 3전략 B1 요약")
    ap.add_argument("date", help="YYYY-MM-DD (창의 마지막 거래일)")
    ap.add_argument("--n-days", type=int, default=5)
    ap.add_argument("--src-logs", default=str(SRC_LOGS), help="라이브 로그 폴더(읽기만)")
    ap.add_argument("--log-dir", default=str(LOG_DIR))
    ap.add_argument("--out-root", default=str(OUT_ROOT))
    ap.add_argument("--skip-run", action="store_true", help="원장 재계산 없이 기존 출력으로 요약만")
    a = ap.parse_args(argv)
    d = date.fromisoformat(a.date)
    log_dir, out_root = Path(a.log_dir), Path(a.out_root)
    for p in (log_dir, out_root):
        if _under(p, LIVE_ROOT):
            print(f"거절: 쓰기 경로 {p} 가 라이브 트리 {LIVE_ROOT} 아래다")
            return 2
    conn = SRC8.connect()
    try:
        cal = SRC8.load_calendar(conn, d - timedelta(days=40), d + timedelta(days=1))
    finally:
        conn.close()
    try:
        days = window(cal, d, a.n_days)
    except ValueError as e:
        print(f"거절: {e}")
        return 2
    notes = copy_logs(Path(a.src_logs), log_dir, days)
    for n in notes:
        print(f"[로그] {n}")
    out = out_root / f"daily_{d.isoformat()}"
    if not a.skip_run:
        rc = RUN.main(["--start", days[0].isoformat(), "--end", days[-1].isoformat(), "--out", str(out),
                       "--log-dir", str(log_dir), "--stage", "all"])
        if rc != 0:
            print(f"run 실패 rc={rc}")
            return rc
    md = render(d, days, out, out / "lots_b1.csv", notes)
    RUN._atomic_write_text(out / "summary_daily.md", md)
    print(f"\n== {out / 'summary_daily.md'}\n{md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
