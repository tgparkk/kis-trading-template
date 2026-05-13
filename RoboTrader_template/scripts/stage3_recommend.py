# RoboTrader_template/scripts/stage3_recommend.py
"""
Stage 3 final_candidates.parquet → 라이브 bb_reversion/config.yaml diff 권고.

CLI:
    python -m RoboTrader_template.scripts.stage3_recommend \
        --candidates output/multiverse_bb_reversion_2026-05-13/stage3/final_candidates.parquet \
        --current-config RoboTrader_template/strategies/bb_reversion/config.yaml \
        --output output/multiverse_bb_reversion_2026-05-13/stage3/recommend_diff.md
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import pandas as pd
import yaml


def render_diff(top1: dict, current: dict) -> str:
    """후보 1위 vs 현재 config diff."""
    lines: list[str] = ["# 라이브 튜닝 권고 — config.yaml diff", ""]
    lines.append("## 최상위 후보 파라미터")
    for k, v in top1.items():
        if k.startswith(("parameters.", "risk_management.", "screening.")):
            lines.append(f"- `{k}` = {v}")
    lines.append("")
    lines.append("## 현재 config 대비 변경 권고")
    lines.append("")
    lines.append("```yaml")
    changes = []
    for k, v in top1.items():
        if not k.startswith(("parameters.", "risk_management.")):
            continue
        section, key = k.split(".", 1)
        cur_val = current.get(section, {}).get(key)
        if cur_val != v:
            changes.append((section, key, cur_val, v))
            lines.append(f"# {section}.{key}: {cur_val} → {v}")
    for section, key, cur_val, new_val in changes:
        lines.append(f"# (section: {section})")
        lines.append(f"#   {key}: {new_val}  # 기존 {cur_val}")
    lines.append("```")
    lines.append("")
    if not changes:
        lines.append("⚠ 변경 사항 없음 (라이브 default가 이미 최상위).")
    lines.append("")
    lines.append("## 백테스트 지표")
    for metric in ("calmar", "sharpe", "total_return", "total_trades", "wf_pass"):
        if metric in top1:
            lines.append(f"- {metric}: {top1[metric]}")
    return "\n".join(lines)


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", required=True)
    p.add_argument("--current-config", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def main() -> int:
    args = _parse()
    df = pd.read_parquet(args.candidates)
    if df.empty:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text("# ⚠ Stage 3 통과 후보 0건 — 라이브 권고 보류\n", encoding="utf-8")
        print("[stage3_recommend] no candidates passed gate", file=sys.stderr)
        return 1
    top1 = df.iloc[0].to_dict()
    current = yaml.safe_load(Path(args.current_config).read_text(encoding="utf-8"))
    body = render_diff(top1, current)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(body, encoding="utf-8")
    print(f"[stage3_recommend] diff written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
