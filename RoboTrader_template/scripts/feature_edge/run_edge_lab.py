"""Feature Edge Lab 오케스트레이터. 패널→라벨→측정→리포트 (측정 전용)."""
from __future__ import annotations

import argparse
import os
from typing import List

import pandas as pd

from scripts.feature_edge import config
from scripts.feature_edge.metrics import (
    daily_ic, tercile_expectancy, coverage, oos_sign_consistent, bootstrap_ic_p05,
)


def build_edge_table(panel: pd.DataFrame, features: List[str],
                     labels: List[str]) -> pd.DataFrame:
    rows = []
    for label in labels:
        for feat in features:
            ic = daily_ic(panel, feat, label)
            te = tercile_expectancy(panel, feat, label)
            rows.append({
                "feature": feat, "label": label,
                "ic_mean": ic["ic_mean"], "ic_ir": ic["ic_ir"], "n_days": ic["n_days"],
                "spread": te["spread"],
                "coverage": coverage(panel, feat),
                "bootstrap_p05": bootstrap_ic_p05(panel, feat, label),
                "oos_consistent": oos_sign_consistent(panel, feat, label, config.OOS_SPLIT),
            })
    tbl = pd.DataFrame(rows)
    return tbl.sort_values(["label", "ic_mean"], ascending=[True, False]).reset_index(drop=True)


def _passes_gate(r) -> bool:
    return (pd.notna(r["bootstrap_p05"]) and r["bootstrap_p05"] > 0
            and bool(r["oos_consistent"]) and r["coverage"] >= config.COVERAGE_MIN)


def write_report(tbl: pd.DataFrame, path: str, note: str = "") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# Feature Edge Report (Phase 0 — 측정 전용)", "", note, "",
             "판정 게이트: bootstrap_p05>0 ∧ oos_consistent ∧ coverage≥%.2f" % config.COVERAGE_MIN,
             "", "## 엣지 후보 (게이트 통과)", ""]
    passed = tbl[tbl.apply(_passes_gate, axis=1)]
    lines.append(passed.to_markdown(index=False) if len(passed) else "_(통과 피처 없음)_")
    lines += ["", "## 전체 측정표", "", tbl.to_markdown(index=False),
              "", "## 다중검정 주의",
              f"- 측정 피처×라벨 조합 수: {len(tbl)} — 우연 통과 가능, p05·OOS 동시충족으로 보수화."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():  # pragma: no cover (통합 실행 경로)
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="테스트용 종목수 제한(0=전체)")
    ap.add_argument("--stage", choices=["singles", "interactions"], default="singles")
    args = ap.parse_args()

    from scripts.feature_edge import loaders
    from scripts.feature_edge.panel import assemble_panel
    from scripts.feature_edge.labelers import label_forward_returns

    codes = loaders.load_universe(config.PERIOD_END)
    if args.limit:
        codes = codes[: args.limit]
    daily = loaders.load_daily_supplier(codes, config.PERIOD_END)
    index_df = loaders.load_index_df()
    flow = loaders.load_flow_supplier(codes)
    events = loaders.load_event_supplier(codes)

    panel = assemble_panel(codes, daily, index_df, flow, events)
    os.makedirs(os.path.dirname(config.PANEL_PATH), exist_ok=True)
    panel.to_parquet(config.PANEL_PATH)

    lab_parts = []
    for c in codes:
        df = daily.get(c)
        if df is not None and len(df) > max(config.FWD_HORIZONS) + 2:
            lr = label_forward_returns(df, config.FWD_HORIZONS)
            lr["stock_code"] = c
            lab_parts.append(lr)
    labels_df = pd.concat(lab_parts, ignore_index=True)
    labels_df["date"] = pd.to_datetime(labels_df["date"])
    merged = panel.merge(labels_df, on=["date", "stock_code"], how="inner")

    feat_cols = [c for c in panel.columns if c not in ("date", "stock_code")]
    lab_cols = [f"fwd_{h}d" for h in config.FWD_HORIZONS]
    tbl = build_edge_table(merged, feat_cols, lab_cols)
    write_report(tbl, config.REPORT_PATH, note="전 패널 대상 선행수익률 IC 측정.")
    print(f"[edge-lab] 패널 {config.PANEL_PATH} / 리포트 {config.REPORT_PATH}")


if __name__ == "__main__":
    main()
