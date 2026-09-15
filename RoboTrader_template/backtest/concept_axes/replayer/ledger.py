"""후보 원장 조립·출력 — 설계서 §3(스키마) · §4-4(진단).

🔴 **출력은 「기준일 D 이하」 정보뿐이다.** 전방 수익률·꼬리 값·PnL 은 여기에 없고,
   만들 경로도 없다(`BookBacktester` 를 import 하지 않는다 — §0-2 · §8-1).
조인 키 = `(stock_code, scan_date)`.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from backtest.concept_axes.replayer import flags as flg
from backtest.concept_axes.replayer import scan as scn

# §1-3-b — 판정 창 끝. 이후 행은 «판정 밖 · 게이트/인쇄 전용».
JUDGMENT_END = pd.Timestamp("2026-05-31")

LEDGER_COLUMNS = [
    "strategy", "scan_date", "stock_code", "rank", "in_top_k", "score", "reason",
    "market", "volatility_20d", "in_judgment_window", "flag_name_unknown",
    "flag_locked_limit", "flag_padding", "flag_cliff", "flag_corp_action",
    "flag_merge_suspect", "cliff_unknown_nprior", "cliff_unknown_adjstep",
    "ret_5d", "trading_value", "market_cap", "close", "open", "high", "low",
    "volume_adj", "n_bars", "universe_eff_date", "universe_fallback",
]

# 🔴 리뷰 M-5 — `run_id`·`git_sha`·`db_fingerprint_hash`·`replayer_params_hash` 는
#   **원장 밖 사이드카**(`ledger_meta.json`)로 뻐다. 원장 안에 두면 같은 입력·같은
#   코드로 돌려도 바이트가 달라져 **결정성을 원장으로 증명할 수 없다**.
META_COLUMNS = ["run_id", "git_sha", "db_fingerprint_hash", "replayer_params_hash"]


def git_sha(root: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
                              capture_output=True, text=True, timeout=10,
                              check=True).stdout.strip()
    except Exception as e:                    # noqa: BLE001
        return "(조회 실패: {})".format(type(e).__name__)


def build_ledger(matched: Sequence[Dict[str, Any]],
                 px: pd.DataFrame,
                 bar_flags: pd.DataFrame,
                 *,
                 strategy: str,
                 uni_info: Dict[Any, Dict[str, Any]],
                 names: Dict[str, str],
                 markets: Dict[str, str],
                 corp_events: Dict[Any, str],
                 max_candidates: int):
    """`(ledger_df, tie_counts)` — 날짜별 정렬·절단 후 §3 스키마로 조립."""
    by_date: Dict[Any, List] = {}
    for r in matched:
        by_date.setdefault(r["scan_date"], []).append(r)

    rows: List[Dict[str, Any]] = []
    tie_counts: Dict[Any, int] = {}
    for d, recs in by_date.items():
        scored = [(r["stock_code"], r["score"]) for r in recs]
        top, n_tie = scn.rank_and_truncate(scored, max_candidates=max_candidates,
                                           count_boundary_tie=True)
        tie_counts[d] = n_tie
        by_code = {r["stock_code"]: r for r in recs}
        for rank, (code, score) in enumerate(top, start=1):
            r = by_code[code]
            i = r["row_idx"]
            bar = px.loc[i]
            f = bar_flags.loc[i]
            nm = names.get(code)
            rows.append({
                "strategy": strategy,
                "scan_date": pd.Timestamp(d),
                "stock_code": code,
                "rank": rank,
                "in_top_k": rank <= scn.LIVE_K,
                "score": float(score),
                "reason": r["reason"],
                "market": markets.get(code),          # ⚠️ 현행 스냅샷 · PIT 아님
                "volatility_20d": (float(bar["volatility_20d"])
                                   if pd.notna(bar.get("volatility_20d")) else None),
                "in_judgment_window": pd.Timestamp(d) <= JUDGMENT_END,
                "flag_name_unknown": nm is None,
                "flag_locked_limit": bool(f["flag_locked_limit"]),
                "flag_padding": bool(f["flag_padding"]),
                "flag_cliff": bool(f["flag_cliff"]),
                "flag_corp_action": (code, pd.Timestamp(bar["date"])) in corp_events,
                "flag_merge_suspect": flg.is_merge_suspect(code),
                "cliff_unknown_nprior": bool(f["cliff_unknown_nprior"]),
                "cliff_unknown_adjstep": bool(f["cliff_unknown_adjstep"]),
                "ret_5d": (float(f["ret_5d"]) if pd.notna(f["ret_5d"]) else None),
                "trading_value": float(bar["close"]) * float(bar["volume"]),
                "market_cap": (float(bar["market_cap"])
                               if pd.notna(bar.get("market_cap")) else None),
                "close": float(bar["close"]), "open": float(bar["open"]),
                "high": float(bar["high"]), "low": float(bar["low"]),
                "volume_adj": float(bar["volume"]),
                "n_bars": int(r["n_bars"]),
                "universe_eff_date": uni_info.get(pd.Timestamp(d), {}).get("eff_date"),
                "universe_fallback": uni_info.get(pd.Timestamp(d), {}).get(
                    "universe_fallback", False),
            })
    df = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    if len(df):
        df = df.sort_values(["scan_date", "rank"], kind="mergesort").reset_index(drop=True)
    return df, tie_counts


def build_diag(diag: Dict[Any, Dict[str, int]],
               uni_info: Dict[Any, Dict[str, Any]],
               tie_counts: Dict[Any, int],
               ledger: pd.DataFrame) -> pd.DataFrame:
    """`ledger_diag.csv` — 날짜별 유니버스·적격·불가능봉·발화·선택·경계 동점."""
    n_sel = (ledger.groupby("scan_date").size().to_dict() if len(ledger) else {})
    rows = []
    for d in sorted(set(diag) | set(uni_info)):
        g = diag.get(d, {})
        u = uni_info.get(d, {})
        rows.append({
            "scan_date": pd.Timestamp(d),
            "universe_eff_date": u.get("eff_date"),
            "universe_fallback": u.get("universe_fallback", False),
            "n_universe": u.get("n_universe", g.get("n_universe", 0)),
            "n_universe_raw": u.get("n_universe_raw", 0),
            "n_eligible": u.get("n_eligible", g.get("n_eligible", 0)),
            "n_impossible": g.get("n_impossible", 0),
            "n_evaluated": g.get("n_evaluated", 0),
            "n_matched": g.get("n_matched", 0),
            "n_selected": int(n_sel.get(pd.Timestamp(d), 0)),
            "n_tie_at_20": int(tie_counts.get(d, 0)),
        })
    return pd.DataFrame(rows)


def write_outputs(ledger: pd.DataFrame, diag: pd.DataFrame, out_dir: Path,
                  stem: str = "ledger_candidates",
                  meta: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """parquet + csv + **`ledger_meta.json` 사이드카**.

    🔒 Q7 — 원장 자체는 `scratchpad/` 에 두고 커밋하지 않는다.
    🔴 리뷰 M-5 — 실행마다 바뀌는 메타(`run_id` 등)는 원장에 넣지 않는다.
       그래야 같은 날을 두 번 돌렸을 때 **원장 바이트가 같아질 수** 있다.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, str] = {}
    csv_p = out_dir / (stem + ".csv")
    ledger.to_csv(csv_p, index=False, encoding="utf-8")
    written["csv"] = str(csv_p)
    try:
        pq_p = out_dir / (stem + ".parquet")
        ledger.to_parquet(pq_p, index=False)
        written["parquet"] = str(pq_p)
    except Exception as e:                     # noqa: BLE001 - pyarrow 부재 등
        written["parquet"] = "(미생성: {})".format(type(e).__name__)
    diag_p = out_dir / "ledger_diag.csv"
    diag.to_csv(diag_p, index=False, encoding="utf-8")
    written["diag"] = str(diag_p)
    meta_p = out_dir / "ledger_meta.json"
    payload = dict(meta or {})
    payload.update({"stem": stem, "n_rows": int(len(ledger)),
                    "n_days": int(ledger["scan_date"].nunique()) if len(ledger) else 0,
                    "ledger_columns": list(LEDGER_COLUMNS)})
    meta_p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                      encoding="utf-8")
    written["meta"] = str(meta_p)
    return written
