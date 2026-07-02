import sys
sys.path.insert(0, '.')
import pandas as pd
from pathlib import Path

DIR = Path("reports/books_research/bellafiore_playbook")
for period in ["2025-10", "2026-04", "2026-05"]:
    p = DIR / f"results_single_fade_vwap_{period}_top_volume50_sl030_tp050_mh120.parquet"
    df = pd.read_parquet(p)
    print(f"\n=== {period} ===")
    print("columns:", list(df.columns))
    print("shape:", df.shape)
    if "side" in df.columns:
        print("side values:", df["side"].value_counts().to_dict())
    print(df.head(3).to_string())
