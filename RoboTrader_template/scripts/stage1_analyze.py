# RoboTrader_template/scripts/stage1_analyze.py
"""
Stage 1 results.parquet → 분포 분석 + report.md 보강.

CLI:
    python -m RoboTrader_template.scripts.stage1_analyze \
        --results output/multiverse_bb_reversion_2026-05-13/stage1/results.parquet \
        --output output/multiverse_bb_reversion_2026-05-13/stage1/report.md
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd

_PROJ_ROOT = Path(__file__).parent.parent
if str(_PROJ_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT.parent))
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))


def signal_count_histogram(df: pd.DataFrame) -> Dict[str, int]:
    """total_trades 컬럼 → 4구간 히스토그램."""
    s = df["total_trades"]
    return {
        "0건": int((s == 0).sum()),
        "1~5건": int(((s >= 1) & (s <= 5)).sum()),
        "6~20건": int(((s >= 6) & (s <= 20)).sum()),
        "21+건": int((s >= 21).sum()),
    }


def zero_signal_param_analysis(df: pd.DataFrame) -> Dict[str, Dict[Any, float]]:
    """0건 셀들의 각 파라미터 축 값 분포 비율."""
    zero = df[df["total_trades"] == 0]
    if zero.empty:
        return {}
    result: Dict[str, Dict[Any, float]] = {}
    for col in df.columns:
        if not col.startswith(("parameters.", "risk_management.", "screening.")):
            continue
        counts = zero[col].value_counts(normalize=True).to_dict()
        result[col] = counts
    return result


def compare_live_default(df: pd.DataFrame, live_default: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """라이브 default 값 조합이 결과에 있는지 찾기."""
    mask = pd.Series([True] * len(df), index=df.index)
    for key, val in live_default.items():
        if key not in df.columns:
            return None
        mask &= (df[key] == val)
    matched = df[mask]
    if matched.empty:
        return None
    return matched.iloc[0].to_dict()


def render_report(df: pd.DataFrame, live_default: Dict[str, Any], top_n: int = 50) -> str:
    """전체 분석을 report.md 본문 문자열로."""
    hist = signal_count_histogram(df)
    zero_params = zero_signal_param_analysis(df)
    live = compare_live_default(df, live_default)
    top_df = df.nlargest(top_n, "calmar") if "calmar" in df.columns else df.nlargest(top_n, "total_return")

    lines: list = ["# Stage 1 분석 리포트", ""]
    lines.append(f"## 신호건수 분포 ({len(df)}셀)")
    for bucket, count in hist.items():
        pct = count / len(df) * 100 if len(df) else 0
        lines.append(f"- {bucket}: {count}셀 ({pct:.1f}%)")
    lines.append("")

    lines.append("## 신호 0건 셀 파라미터 집중도 (상위 3축)")
    for axis, dist in list(zero_params.items())[:3]:
        lines.append(f"### {axis}")
        for val, ratio in sorted(dist.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- {val}: {ratio:.1%}")
        lines.append("")

    lines.append("## 라이브 default 비교")
    if live is None:
        lines.append("⚠ 라이브 default 조합이 그리드 결과에 없음 (그리드 정의 미스매치).")
    else:
        lines.append(f"라이브 default ({live_default}) 결과:")
        for k, v in live.items():
            if k in ("total_trades", "total_return", "sharpe", "calmar"):
                lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append(f"## Top {top_n} (Calmar 정렬)")
    lines.append("")
    lines.append(top_df.to_markdown(index=False))
    return "\n".join(lines)


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--results", required=True, help="Stage 1 results.parquet 경로")
    p.add_argument("--output", required=True, help="report.md 저장 경로")
    p.add_argument("--top-n", type=int, default=50)
    return p.parse_args()


def main() -> int:
    args = _parse()
    df = pd.read_parquet(args.results)
    live_default = {
        "parameters.bb_period": 20,
        "parameters.bb_std": 2.0,
        "parameters.rsi_oversold": 40,
        "risk_management.stop_loss_pct": 0.03,
        "risk_management.take_profit_pct": 0.05,
    }
    body = render_report(df, live_default, args.top_n)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(body, encoding="utf-8")
    print(f"[stage1_analyze] report written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
