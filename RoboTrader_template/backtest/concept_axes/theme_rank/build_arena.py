"""경기장 원장(스펙 §5-1) — daytrading 후보 원장 rank ≤ 20 행에 밴드 재현 체결·청산·순수익을 붙인다.

🔴 테마 신호를 읽지 않는다(신호와 결과의 결합은 동결 뒤 `run.py` 에서만) · DB SELECT 전용.

    python -X utf8 -m backtest.concept_axes.theme_rank.build_arena
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import hashlib                                                         # noqa: E402
import json                                                            # noqa: E402
import subprocess                                                      # noqa: E402
from collections import Counter                                        # noqa: E402
from datetime import date                                              # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Callable, Dict, List, Optional                 # noqa: E402

import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.candidate_ledger import run as CL           # noqa: E402
from backtest.concept_axes.theme_rank import bandfill as BF            # noqa: E402
from backtest.concept_axes.theme_rank.snapshot import norm_code        # noqa: E402

STRATEGY = "daytrading_3methods_breakout"
ARENA_MAX_RANK = 20                                  # 🔒 라이브 E6 가 읽는 범위
COST_PCT = 0.25                                      # 🔒 freq_scenarios COST_RATE 0.0025 × 100(왕복 %p)
LEDGER_CSV = CL.BASE / "results" / "ledger.csv"
LEDGER_MD5 = "980e58492a7ac2ed11d25526f4488dbc"
OUT = Path(__file__).resolve().parent / "results"
ARENA_COLS = ["scan_date", "stock_code", "rank", "score", "n_passed", "band_hi", "fill", "entry_date",
              "entry_price", "exit_date", "exit_reason", "hold_days", "ret_pct", "ret_net", "flags"]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def load_ledger() -> pd.DataFrame:
    got = md5(LEDGER_CSV)
    if got != LEDGER_MD5:
        raise SystemExit(f"ledger.csv md5 불일치 {got} ≠ {LEDGER_MD5} — 중단")
    led = pd.read_csv(LEDGER_CSV, dtype={"stock_code": str, "scan_date": str, "entry_date": str,
                                         "exit_date": str}, low_memory=False)
    return led[led["strategy"] == STRATEGY].reset_index(drop=True)


def _num(x: Any) -> Optional[float]:
    v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
    return None if pd.isna(v) else float(v)


def _txt(x: Any) -> str:
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)


def arena_rows(led: pd.DataFrame, low_of: Callable[[str, date], Optional[float]],
               resim: Callable[[str, date, float], Any]) -> List[Dict[str, Any]]:
    """순수 조립 — low_of(code, d1) = D+1 저가 · resim(code, d1, price) = 밴드 터치 로트 ExitOut."""
    out: List[Dict[str, Any]] = []
    for r in led.itertuples(index=False):
        if int(r.rank) > ARENA_MAX_RANK:
            continue
        code = norm_code(r.stock_code)
        open_, hi = _num(r.entry_price), _num(r.band_hi)
        d1 = date.fromisoformat(str(r.entry_date)) if _txt(r.entry_date) else None
        low = low_of(code, d1) if (open_ is not None and hi is not None and d1 is not None and open_ > hi) else None
        f = BF.band_fill(open_, low, hi)
        row: Dict[str, Any] = dict(scan_date=r.scan_date, stock_code=code, rank=int(r.rank), score=r.score,
                                   n_passed=int(r.n_passed), band_hi=_txt(r.band_hi), fill=f.status,
                                   entry_date=_txt(r.entry_date), entry_price="", exit_date="", exit_reason="",
                                   hold_days="", ret_pct="", ret_net="", flags=_txt(r.flags))
        if f.status == BF.FILL_OPEN:
            row.update(entry_price=open_, exit_date=_txt(r.exit_date), exit_reason=_txt(r.exit_reason),
                       hold_days=_txt(r.hold_days), ret_pct=_num(r.ret_pct) if _num(r.ret_pct) is not None else "")
        elif f.status == BF.FILL_BAND:
            ex = resim(code, d1, f.price)
            row.update(entry_price=f.price, exit_date=_txt(ex.exit_date), exit_reason=_txt(ex.reason),
                       hold_days=_txt(ex.hold_days), ret_pct=ex.ret_pct if ex.ret_pct is not None else "",
                       flags=";".join(ex.flags))
        if row["ret_pct"] != "":
            row["ret_net"] = float(row["ret_pct"]) - COST_PCT
        out.append(row)
    return out


def build_env(conn) -> Any:
    """`candidate_ledger.run.main` 과 같은 벌크 로드(재사용 모듈 수정 0줄)."""
    from backtest.concept_axes.replayer import flags as FL
    from backtest.concept_axes.replayer import loader as LD
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, CL.PX_START, CL.W_END)]
    px = LD.load_prices(conn, CL.PX_START, CL.W_END)
    book = CL.build_book(px)
    fl = FL.compute_bar_flags(px)
    m_imp = fl["flag_padding"] | fl["flag_locked_limit"] | fl["flag_cliff"]
    return CL.Env(cal=cal, book=book, uni=LD.build_universe(px),
                  excl=CL.excl_class_map(sorted(book), LD.load_stock_names(conn)),
                  imp_dates=CL._date_index(zip(px.loc[m_imp, "stock_code"], px.loc[m_imp, "date"])),
                  corp_dates=CL._date_index(LD.load_corp_events(conn).keys()),
                  bad_open=CL.load_bad_open(conn, CL.PX_START, CL.W_END), minute_fn=CL.make_minute_fn(conn))


def main() -> int:
    from backtest.concept_axes.ledger8 import sellprobe8 as SP
    from backtest.concept_axes.ledger8.livesignal8 import load8
    led = load_ledger()
    conn = CL._connect()
    env = build_env(conn)
    strategy = load8(STRATEGY)
    rules = SP.resolve_live_tp_sl(STRATEGY, strategy)
    if (rules.tp, rules.sl, rules.max_hold_days) != (0.10, 0.10, 10):
        raise SystemExit(f"청산 규칙이 스펙과 다르다: {rules}")
    probe = SP.SellProbe(STRATEGY, strategy, CL.make_window_fn(env.book))

    def low_of(code: str, d1: date) -> Optional[float]:
        b = env.bars(code).get(d1)
        return float(b.low) if b is not None else None

    rows = arena_rows(led, low_of, lambda code, d1, px: BF.resim_band_touch(code, d1, px, env, rules, probe))
    conn.close()
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=ARENA_COLS).to_csv(OUT / "arena.csv", index=False, encoding="utf-8")
    cnt = Counter(r["fill"] for r in rows)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = dict(git_sha=sha, ledger_md5=LEDGER_MD5, n_rows=len(rows), fill_counts=dict(cnt),
                n_days=len({r["scan_date"] for r in rows}), arena_md5=md5(OUT / "arena.csv"))
    (OUT / "arena_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"경기장 {len(rows):,}행 · {meta['n_days']}일 · 체결 {dict(cnt)} · md5 {meta['arena_md5']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
