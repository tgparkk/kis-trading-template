"""산출물: 폴드 테이블, 파라미터 안정성, markdown 리포트."""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import pandas as pd


def build_fold_table(fold_results: List[dict]) -> pd.DataFrame:
    rows = []
    for fr in fold_results:
        b = fr["best"]
        row = {"train_start": fr["fold"]["train_start"], "test_start": fr["fold"]["test_start"],
               "test_end": fr["fold"]["test_end"],
               "train_worst_sharpe": b["worst_sharpe"], "train_dsr": b["dsr"],
               "train_n_trades": b["n_trades"],
               "oos_worst_sharpe": fr["oos_worst_sharpe"],
               "oos_total_return": fr["oos_total_return"], "oos_n_trades": fr["oos_n_trades"]}
        for k, v in b["params"].items():
            row[f"best_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def param_stability(best_params: List[dict]) -> Dict[str, dict]:
    """폴드 간 베스트 파라미터 분산. 고유값 2개 초과면 unstable(과최적화 신호)."""
    out = {}
    keys = set().union(*[p.keys() for p in best_params]) if best_params else set()
    for k in keys:
        vals = [p.get(k) for p in best_params]
        uniq = set(str(v) for v in vals)
        out[k] = {"values": vals, "n_unique": len(uniq), "unstable": len(uniq) > 2}
    return out


def _to_md_table(df: pd.DataFrame) -> str:
    """markdown 표. tabulate 가 있으면 to_markdown, 없으면 to_string fallback (의존성 회피)."""
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def write_strategy_report(name: str, fold_results: List[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = build_fold_table(fold_results)
    df.to_parquet(out_dir / f"{name}_grid.parquet", index=False)
    stab = param_stability([fr["best"]["params"] for fr in fold_results])
    md = [f"# {name} — 워크포워드 청산 최적화 결과\n",
          "## 폴드별 train 베스트 / OOS 성과\n", _to_md_table(df), "\n",
          "## 파라미터 안정성 (폴드 간)\n"]
    for k, v in stab.items():
        flag = "WARNING UNSTABLE(과최적화 의심)" if v["unstable"] else "안정"
        md.append(f"- **{k}**: {v['values']} -> {flag}")
    mean_oos = df["oos_worst_sharpe"].mean() if len(df) else 0.0
    md.append(f"\n## 종합\n- 평균 OOS 국면최악 Sharpe: **{mean_oos:.3f}**")
    if len(df):
        md.append(f"- 평균 OOS 수익률: **{df['oos_total_return'].mean():.2%}**")
    path = out_dir / f"{name}_walkforward.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path
