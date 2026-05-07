"""trend_starter PoC 결과 파라미터별 분해 분석."""
from __future__ import annotations
import sys
import os

sys.path.insert(0, "d:/GIT/kis-trading-template")
sys.path.insert(0, "d:/GIT/kis-trading-template/RoboTrader_template")

import pandas as pd
from RoboTrader_template.multiverse.composable.personas._grid import expand_grid_trend_starter

RESULTS_CSV = (
    "d:/GIT/kis-trading-template/RoboTrader_template/"
    "output/multiverse_trend_starter_poc_20260506_173457/results.csv"
)

# 1. 432 ParamSet 생성 + hash 매핑
psets = expand_grid_trend_starter()
id_to_params = {ps.config_hash(): ps for ps in psets}
print(f"총 ParamSet: {len(psets)}개")

# 2. results.csv 로드
df = pd.read_csv(RESULTS_CSV)
print(f"results.csv 행: {len(df)}")

# 3. paramset_id로 ParamSet 조회 → 6개 파라미터 컬럼 추가
def extract_params(pid):
    ps = id_to_params.get(pid)
    if ps is None:
        return pd.Series({
            "ts_target_pct": None, "ts_stop_pct": None, "ts_hold_days": None,
            "ts_atr_min": None, "ts_volz_min": None, "ts_box_min": None,
        })
    return pd.Series({
        "ts_target_pct": ps.ts_target_pct,
        "ts_stop_pct": ps.ts_stop_pct,
        "ts_hold_days": ps.ts_hold_days,
        "ts_atr_min": ps.ts_atr_min,
        "ts_volz_min": ps.ts_volz_min,
        "ts_box_min": ps.ts_box_min,
    })

param_df = df["paramset_id"].apply(extract_params)
df = pd.concat([df, param_df], axis=1)

matched = df["ts_target_pct"].notna().sum()
print(f"매칭: {matched}/{len(df)} ({len(df)-matched}개 누락)")

# 4. 매칭된 행만 분석
df_m = df.dropna(subset=["ts_target_pct"]).copy()

METRICS = ["m_sharpe", "expectancy", "precision", "m_mdd"]

for col in ["ts_target_pct", "ts_stop_pct", "ts_hold_days", "ts_atr_min", "ts_volz_min", "ts_box_min"]:
    print(f"\n=== {col} ===")
    tbl = df_m.groupby(col)[METRICS].mean().round(4)
    print(tbl.to_string())
